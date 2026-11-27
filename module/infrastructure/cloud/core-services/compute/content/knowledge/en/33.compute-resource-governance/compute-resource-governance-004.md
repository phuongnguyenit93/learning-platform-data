# Quota Management and Growth-Based Capacity Planning

Quota and capacity are two distinct constraints that are frequently confused when scaling cloud infrastructure. Capacity describes how many resources the system actually has available to run workloads; quota sets a cap on the amount of resources or rate of usage an account, project, subscription, region, or service is permitted to request. An organization may have remaining quota while the provider lacks available capacity in the desired zone or instance family. Conversely, a region may have ample capacity while a workload still fails to deploy because vCPU, GPU, IP address, or load balancer quotas have hit their ceiling.

As workloads grow, teams must forecast demand over time, identify which resources will hit quotas first, reserve headroom for peaks and failures, and submit quota increase requests early enough. A solid plan combines actual usage data, forecasts, product release schedules, seasonality, availability targets, and cloud provider processing lead times. It must also tie into budgets, security, ownership, and approval workflows.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this lesson connects VM, container, Kubernetes, serverless, CPU, memory, network, and storage choices with resource limit governance. The focus is turning workload growth into verifiable, trackable, and adjustable quota and capacity plans.

After this lesson, you will be able to:

- Distinguish quota, capacity, allocation, reservation, usage, and rate limits.
- Classify quotas by scope, region, service, resource, and unit of measure.
- Identify quotas that can block VM, GPU, network, storage, Kubernetes, and serverless deployments.
- Forecast demand based on trends, seasonality, peaks, product roadmaps, and growth scenarios.
- Calculate headroom, N+1 capacity, quota runway, and when to submit quota increase requests.
- Plan capacity across multiple accounts, subscriptions, projects, and regions.
- Design workflows for quota requests, approvals, monitoring, alerts, and escalation.
- Combine autoscaling, reservations, fallbacks, and budget guardrails for controlled growth.

## 1. Quota, Capacity, and Related Concepts

### Quota

A quota is a limit enforced by a provider, platform, or organization on a resource or action. A quota can be a maximum resource count, total vCPUs, storage volume, requests within a time window, or concurrent connections.

Examples:

- Total vCPUs allowed to run in a region.
- Number of GPUs permitted in a project.
- Maximum public IPs or load balancers.
- Persistent disk capacity or volume count.
- Concurrent function invocations.
- API requests per second or per day.
- Pods, CPU requests, or memory requests in a Kubernetes namespace.

Quotas are typically administrative and platform-protection limits. Raising a quota does not mean the provider guarantees physical capacity in every zone at any moment.

### Capacity

Capacity is the amount of usable resources available to handle workloads. Capacity can be viewed at several layers:

- **Provider capacity:** physical/virtual resources the provider can provision in a region, zone, or instance family.
- **Account capacity:** resources within the account's quota and policy boundaries.
- **Cluster capacity:** CPU, memory, storage, network, and accelerators a cluster can schedule.
- **Workload capacity:** throughput or requests/jobs the system can handle within SLO bounds.
- **Dependency capacity:** capacity of databases, queues, APIs, NATs, storage, or downstream services.

Usable capacity is constrained by the narrowest bottleneck in the chain. For example, having 500 vCPU quota still leaves only 120 usable vCPUs in a node pool if GPU-compatible instances or zonal capacity are unavailable.

### Allocation, Reservation, and Usage

- **Allocation:** the portion of quota or capacity assigned to a project, team, namespace, or workload.
- **Reservation:** capacity held in advance through a provider or platform mechanism; reservations may carry fees or usage conditions.
- **Usage:** resources actively consumed at measurement time or usage over a period.
- **Limit:** runtime cap of a single workload or container; distinct from account quota.
- **Rate limit:** cap on action frequency, such as 100 requests/second, usually governed by a time window or token bucket.

| Concept | Question Answered | Example |
|---|---|---|
| Quota | How much are we allowed to request at most? | 200 vCPUs in one region |
| Capacity | How much can actually be provisioned/run? | 150 suitable vCPUs available |
| Allocation | Which share is assigned to the team? | Team A has an 80 vCPU budget |
| Reservation | How much capacity is reserved ahead of time? | 32 vCPU reservation in a zone |
| Usage | How much is currently in use? | 95 vCPUs running |
| Limit | What is the max a single workload can consume? | Container memory limit 2 GiB |
| Rate limit | How many actions are allowed per time unit? | 500 API calls/minute |

## 2. Why Quotas Become a Risk as Workloads Grow

A workload can run smoothly for months and then suddenly fail to scale upon hitting a threshold. Common symptoms include:

- New VMs fail to provision even when the autoscaler requests additional nodes.
- GPU jobs stay `Pending` because accelerator quota is exhausted.
- Functions get throttled when concurrency hits its cap.
- Kubernetes Pods fail to schedule due to namespace `ResourceQuota`.
- New load balancers or public IPs fail to provision.
- Automation APIs receive quota/rate-limit errors during bulk deployments.
- Storage expansion fails due to capacity or volume count quotas.
- DR environments cannot scale out when the primary region experiences an outage.

Quotas are often discovered late because monitoring tracks CPU utilization and memory usage rather than quota consumption. A cluster with low CPU utilization can still hit quota if many idle instances remain provisioned or if quota was consumed by another account/project in the same scope.

### Quotas Are Part of Production Readiness

Ahead of a major campaign, migration, launch, or DR drill, verify:

1. Expected peak demand.
2. Current quota and utilization.
3. Provider capacity in target regions/zones.
4. Reservations/commitments and quota scopes.
5. Quota increase processing lead time.
6. Fallbacks if quota or capacity is denied.
7. Budget and approval authority.

Never wait until the autoscaler throws errors to submit a quota request.

## 3. Classifying Quotas by Scope

Quotas apply across multiple scopes. Understanding the right scope prevents submitting requests to the wrong level or under-forecasting.

| Scope | Boundary of Limit | Example |
|---|---|---|
| Organization/tenant | Entire organization or tenant | Total subscriptions, total spend, or policy cap |
| Account/project/subscription | Single account or project | Total vCPUs, VM count, GPUs |
| Region | Individual region | Regional vCPU quota, public IPs |
| Availability zone | Single zone or fault domain | Per-zone capacity/reservations |
| Service | Specific service | Serverless concurrency, database instances |
| Resource family | Resource type family | GPU family, compute-optimized vCPUs |
| Namespace/cluster | Kubernetes/platform scope | CPU/memory `ResourceQuota` |
| Principal/API client | Specific identity or client | API requests per minute |
| Resource instance | Specific resource | Connection limit, disk IOPS, or throughput |

Quotas can have both aggregate and child scopes. For example, regional total vCPU quota may be 300, while instance family A has a quota of 120 and GPU family B has a quota of 32. Raising total vCPUs to 500 does not automatically raise family A or GPU B quotas.

### Checking Quota Inheritance

Some platforms set default quotas at the organization level and specific quotas at the account/project level. Internal policies may also cap usage lower than provider quotas. The effective limit is the smallest limit currently enforced in the chain.

Example:

- Provider quota: 300 vCPU.
- Organization allocation: 220 vCPU.
- Project allocation: 120 vCPU.
- Workload budget: 80 vCPU.

The workload cannot consume 300 vCPUs on its own; its effective limit under the current allocation is 80 vCPUs.

## 4. Classifying Quotas by Resource

Compute quotas usually span multiple resource categories simultaneously.

| Category | Quota Examples | Risk When Threshold Is Hit |
|---|---|---|
| CPU/VM | Total vCPUs, VM count, instance family | Unable to scale nodes/VMs |
| GPU/accelerator | GPU count, accelerator family | ML/HPC jobs fail to schedule |
| Memory/compute shape | Memory-optimized VM count or total RAM per offering | Lack of suitable nodes for workload |
| Storage | Disk count, total GB, snapshots, IOPS/throughput | Cannot create/expand volumes or backups |
| Network | VPC/VNet, subnets, IPs, ENI/NIC, routes, NAT, load balancers | Cannot create network paths or scale interfaces |
| Serverless | Concurrent executions, function count, request rate | Throttling or invocation delays |
| Container/Kubernetes | Pods, CPU/memory requests, PVCs, node pools | Pods `Pending` or namespace creation blocked |
| Database | Instance count, storage, connections, IOPS | Cannot scale database or connection exhaustion |
| API/control plane | API rate, operation count, resource creation rate | Automation throttled |
| Observability | Log ingestion, metric series, trace volume | Telemetry loss or cost spike |

Not every limit is labeled "quota" in provider consoles. Some are called service limits, capacity limits, rate limits, soft limits, or subscription restrictions. Include every limit that can affect the workload in the same inventory.

## 5. Hard Quotas, Soft Quotas, and Runtime Limits

### Hard Quota

A hard quota blocks operations once exceeded. For example, the VM creation API returns an error when total vCPUs exceed the limit. You must obtain a quota increase or free resources before proceeding.

### Soft Quota

A soft quota acts as a warning threshold or internal policy limit. It allows exceeding under certain conditions but requires approval, budget exceptions, or governance controls.

### Runtime Limit

A runtime limit constrains a specific workload, such as a container memory limit or a function's max concurrency. Runtime limits can be lower than account quotas.

### Rate Limit

A rate limit caps action frequency. Automation may have plenty of VM quota remaining yet still fail to create 100 VMs within a few seconds due to API rate limits.

### Capacity Availability

A provider may reject an instance request even with spare quota due to a capacity shortage in a zone, host pool, or accelerator family. This is a capacity availability failure, resolved via zone/family selection, reservations, or fallbacks; raising quota alone will not fix it.

## 6. Building a Quota Inventory

A quota inventory is a structured catalog showing which limits apply, who owns them, and when action is needed.

Recommended fields:

| Field | Meaning |
|---|---|
| Provider/service | Cloud provider and service |
| Account/project/subscription | Account scope |
| Region/zone | Geographic scope |
| Resource/metric | Quota name and unit |
| Current limit | Current limit |
| Current usage | Current consumption |
| Peak usage | Highest observed usage |
| Allocated/committed | Portion allocated or committed |
| Forecast peak | Forecasted peak |
| Headroom | Remaining margin after forecast |
| Increase lead time | Time required to approve quota increase |
| Request owner | Responsible person/team |
| Approval owner | Approver |
| Criticality | Impact level |
| Last reviewed | Most recent review date |
| Evidence/link | Dashboard, ticket, or confirmation doc |

### Consistent Metric Naming

Standardizing resource names and units enables cross-provider comparison:

- `compute.vcpu.total`
- `compute.gpu.count`
- `network.ipv4.addresses`
- `network.load_balancers.count`
- `storage.block.capacity_gib`
- `serverless.concurrent_executions`
- `kubernetes.namespace.cpu_requests`

These names illustrate an internal schema, not provider API quota identifiers.

### When Should the Quota Inventory Be Updated?

- When creating a new account/project/subscription.
- When adding a region or node pool.
- When launching a new workload.
- When changing instance families or accelerators.
- When a quota increase/decrease occurs.
- When a provider alters default limits or service behavior.
- When teams transfer workloads or ownership.
- When growth forecasts change.

## 7. Measuring Quota Consumption and Headroom

For concurrency-based resource quotas, utilization at time $t$ is:

\[
Usage\% = \frac{CurrentUsage}{QuotaLimit} \times 100\%
\]

Absolute headroom:

\[
Headroom = QuotaLimit - CurrentUsage
\]

Proportional headroom:

\[
Headroom\% = 1 - \frac{CurrentUsage}{QuotaLimit}
\]

For example, with a quota of 200 vCPUs and 130 vCPUs in use:

- Usage = 65%.
- Headroom = 70 vCPUs.
- Headroom rate = 35%.

If next month's forecasted peak is 185 vCPUs, the current quota leaves only 15 vCPUs of buffer. To preserve 20% headroom, the target quota must exceed 185 vCPUs.

### Distinguishing Current Usage and Peak Usage

Current usage may be low at night while daytime peak usage is high. Capacity planning must use peaks over appropriate time windows:

- 5-minute peak for bursts/concurrency.
- 1-hour peak for batch windows.
- Daily/weekly peak for seasonal workloads.
- Campaign or special-event peak.

For quotas tracking total provisioned resources, usage must include idle provisioned resources if the provider counts them toward quota. For throughput-based quotas, measure request rates or token consumption over the exact matching window.

### Headroom Does Not Always Equal Available Capacity

If 30% of quota remains while the provider has only 5% capacity left in the required zone, quota headroom does not equal real capacity. Track both metrics separately.

## 8. Forecasting Workload Growth

Quota forecasting starts from workload demand, not from an arbitrary desired quota figure.

### Growth Drivers

- Active users and tenant counts.
- Requests/transactions per user.
- Number of jobs, files, records, or events.
- Data volume and retention periods.
- Replica counts and availability targets.
- Deploy/test/preview environment frequency.
- Product launch and marketing schedules.
- Seasonality, month-end, quarter-end, or holidays.
- Increasing workload complexity.
- Retry rates, logging, and replication overhead.

For instance, a 20% increase in users does not necessarily mean a 20% increase in compute. If each user triggers more transactions or data processing scales quadratically due to joins/shuffles, demand can grow much faster.

### Linear Growth Model

When a workload adds roughly a constant amount each month:

\[
D(t) = D_0 + a \times t
\]

Where \(D_0\) is current demand, \(a\) is the per-period increment, and \(t\) is the number of periods.

### Exponential Growth Model

When a workload grows by a percentage each period:

\[
D(t) = D_0 \times (1+g)^t
\]

Where \(g\) is the growth rate per period.

For example, with current demand of 100 vCPUs growing 12% per month, after 6 months:

\[
D(6) = 100 \times 1.12^6 \approx 197.4\ vCPU
\]

Forecasting linearly by adding 12 vCPUs per month would severely underestimate demand.

### Seasonality and Peaks

Use a baseline model combined with a seasonal multiplier:

\[
D_{\text{peak}} = D_{\text{baseline}} \times S_{\text{season}}
\]

For example, a 180 vCPU baseline with a 1.4 peak factor yields ~252 vCPU peak demand. Base multipliers on historical data or business plans rather than arbitrary guesses.

### Growth Scenarios

Build at least three scenarios:

| Scenario | Assumptions | Purpose |
|---|---|---|
| Conservative | Slower growth, delayed launch | Baseline cost planning |
| Expected | Growth aligned with primary forecast | Routine operational planning |
| High growth | Successful launch, high peaks, or acquisition surge | Testing quota runway and fallbacks |

Add stress scenarios for failover events, region evacuations, or sudden campaigns.

## 9. Translating Workload Forecasts into Resource Demand

Workload demand must be converted into CPU, memory, storage, network, IP, GPU, and service-specific quotas.

### API Example

Suppose every 1,000 requests/second requires 4 vCPUs and 8 GiB RAM per benchmarks:

\[
CPU_{\text{required}} =
\frac{RPS_{\text{forecast}}}{1000} \times 4
\]

If forecasted peak is 8,000 RPS, ideal CPU demand is 32 vCPUs. Adding 30% headroom for bursts and failure reserves yields a target of ~42 vCPUs.

Benchmark at the target latency SLO. If each request depends on a database with low throughput, a pure CPU formula will be insufficient.

### Worker Queue Example

If each worker processes 50 messages/second and queue peak requires 2,000 messages/second:

\[
Workers_{\text{base}} = \frac{2000}{50} = 40
\]

To maintain 25% headroom, plan capacity for 50 workers. However, verify whether downstream databases/APIs can sustain 50 concurrent workers.

### Storage Example

Storage demand may include:

\[
Storage_{\text{required}} =
Data_{\text{active}} + Data_{\text{retained}} + Index + Backup + GrowthBuffer
\]

If data grows 2 TB/month with 12-month retention, account for ~24 TB of historical data before adding indexes, replication, and backups. Do not use logical TB as physical quota while ignoring replication factors or snapshot copies.

### Networking and IPs

Increasing VMs, Pods, or serverless connectors can increase:

- Private IPs/ENIs/NICs.
- NAT connections and port mappings.
- Load balancers/frontend IPs.
- Route/firewall rules.
- Cross-zone traffic and egress.
- DNS records/query volume.

Quota planning must account for supporting resources, not just CPU and RAM.

## 10. Headroom and Failure-Domain Capacity

Headroom helps systems absorb bursts, while also providing sufficient capacity if a node or zone is lost.

### N+1 Planning

If a system must tolerate the loss of one node pool member, calculate remaining capacity after removing that node.

For example, three nodes with 32 vCPUs each total 96 vCPUs. If the workload needs 60 vCPUs and must survive losing one node, the two surviving nodes offer 64 nominal vCPUs. After deducting system reservations and headroom, that may not suffice. Increase node count or machine shape.

### Zone Failure

Across three evenly balanced zones, when one zone fails, the remaining two zones must carry the required workload. If the workload normally runs at 70% of total capacity, losing 1/3 of capacity pushes utilization to roughly 105%, exceeding limits. Design around surviving capacity, not just replica distribution.

### Headroom by Layer

- **Quota headroom:** quota remaining before hitting the limit.
- **Provider capacity headroom:** additional capacity available in the zone/family.
- **Cluster headroom:** allocatable resources remaining in node pools.
- **Workload headroom:** additional throughput possible before breaching SLOs.
- **Dependency headroom:** how much more load databases/networks/storage can handle.

Each layer needs its own metrics and owner.

## 11. Determining Target Quotas and When to Request Increases

The target quota must cover forecasted peak, headroom, and co-located resources sharing the same scope.

\[
Quota_{\text{target}} =
\frac{ForecastPeak}{1 - HeadroomTarget}
\]

For example, with a forecasted peak of 240 vCPUs and a 25% headroom target:

\[
Quota_{\text{target}} = \frac{240}{0.75} = 320\ vCPU
\]

If current quota is 250 vCPUs, request an increase of at least 70 vCPUs to reach the 320 vCPU target. More may be needed if growth forecasts or DR requirements increase.

### Quota Runway

For concurrency quotas, runway can be estimated from when forecasted usage hits the threshold. Under linear growth:

\[
Runway =
\frac{QuotaLimit - CurrentUsage}{ExpectedNetGrowthPerPeriod}
\]

For example, with 60 vCPUs remaining and demand growing by 15 vCPUs/month, runway is approximately 4 months absent seasonality or step changes.

For exponential growth, solve for time $t$ when forecasted demand equals the quota threshold. Do not use linear runway if growth compounds by percentage.

### Request Lead Time

If a provider typically takes 10 days to process a quota request, submit before remaining runway drops below 10 days plus a buffer. For GPUs or specialized quotas, processing/capacity sourcing lead times may be longer. Use historical lead times and confirm with the provider.

### Quota Requests Do Not Equal Capacity Reservations

A quota increase permits an account to request more resources up to the new cap. It does not necessarily reserve instances or GPUs. If a workload requires guaranteed capacity at a specific time, check capacity reservations/dedicated capacity or equivalent mechanisms.

## 12. Quotas for VMs and Instance Families

VM quotas may be tracked by total vCPUs, instance counts, families, regions, or workload types. Limits may overlap.

When planning:

- Calculate vCPUs per instance family.
- Separate general-purpose, compute-optimized, memory-optimized, and accelerator quotas.
- Identify required regions/zones.
- Account for VMs across production, staging, CI/CD, migrations, and DR.
- Account for node autoscaler maximum sizes.
- Check quotas for rare instance types or bare metal.
- Verify reservation and commitment scopes.

### Example

A system requires:

- 80 general-purpose vCPUs.
- 48 memory-optimized vCPUs.
- 16 GPU worker host vCPUs.
- 24 DR reserve vCPUs.

Nominal total vCPUs are 168, yet family-level quotas may impose separate limits. Do not merely submit a request to "raise total vCPUs to 168" if the accelerator family remains capped.

### Instance Family Fallbacks

Maintain a list of equivalent instance families per workload:

- Compatible CPU architecture.
- Sufficient RAM/vCPU ratio.
- Network bandwidth and disk throughput.
- Accelerator model/VRAM.
- Local NVMe or ephemeral storage.
- Licensing and software compatibility.

Autoscalers can leverage multiple families to reduce capacity-shortage risks, provided performance and cost are tested.

## 13. Quotas for Kubernetes and Container Platforms

Kubernetes enforces limits across multiple layers.

### ResourceQuota

`ResourceQuota` caps total resources or object counts in a namespace. Example:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-compute-quota
  namespace: team-a
spec:
  hard:
    requests.cpu: "40"
    requests.memory: 80Gi
    limits.cpu: "80"
    limits.memory: 160Gi
    pods: "100"
    persistentvolumeclaims: "30"
~~~

This quota limits total requests/limits and object counts within the namespace for the declared resources. It does not create node capacity or replace cloud account quotas.

### LimitRange

`LimitRange` sets default/min/max resources per container or Pod. It prevents containers from omitting requests or requesting above policy, but it is not a total namespace quota.

### Node Pool Quotas

The cluster autoscaler may attempt to add nodes yet be blocked by:

- Cloud vCPU quotas.
- Instance family quotas.
- GPU quotas.
- Subnet IP exhaustion.
- Node pool maximums.
- Regional capacity.
- Managed Kubernetes node quotas.

### Pod Quotas and IP Quotas

CNIs can impose Pod/IP limits per node or subnet. Scaling Pod counts consumes more than CPU/RAM; it can hit IP, ENI, route, or network policy scale limits.

### Namespace Allocation Design

Quotas should tie to owners and workload tiers. For example, production namespaces receive dedicated baselines and headroom; dev/test receive lower caps and may have capacity reclaimed. Avoid shared namespaces where one team can exhaust resources for another.

## 14. Quotas for Serverless and Managed Services

Serverless platforms may impose limits on concurrency, request rate, execution duration, memory, deployment package size, function count, or event source mappings.

As demand grows:

- Forecast peak concurrent executions, not just daily invocations.
- Calculate average execution time and tail duration.
- Evaluate reserved/provisioned concurrency if supported by the product.
- Check downstream connection limits.
- Check event source polling/partition/consumer limits.
- Factor in retries and DLQs multiplying invocations.
- Check API gateway, queue, and database quotas concurrently.

### Concurrency Example

By Little's Law, concurrency approximates throughput multiplied by processing duration:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

If a function receives 400 requests/second with an average duration of 0.25 seconds:

\[
Concurrency \approx 400 \times 0.25 = 100
\]

This is an average estimate; peak bursts and p95 durations may demand higher concurrency. Plan using peak-window arrival rates and latency distributions.

### Dependency Quotas

Raising function concurrency without raising database connection or API quotas can make the system fail faster. Plan capacity end-to-end.

## 15. Network and Storage Quotas

### Network Quotas

Inventory should include:

- VPC/VNet and subnet counts.
- Private IPs and public IPs.
- ENIs/NICs or network attachments.
- NAT gateways and connection/port capacity.
- Load balancers, listeners, and target counts.
- Route tables, peerings, and transit attachments.
- VPN tunnels and bandwidth.
- Firewall rule/policy counts.
- DNS zones, records, and query rates.

Scaling compute can exhaust subnet IPs before hitting vCPU limits. Especially with Kubernetes or serverless VPC integration, forecast IP/interface growth alongside service scaling patterns.

### Storage Quotas

Track:

- Total provisioned capacity.
- Volume counts and snapshot counts.
- Per-volume size limits.
- Provisioned IOPS/throughput.
- Object storage request rates.
- File share counts/throughput.
- Backup vault capacity/retention.
- KMS key/request quotas as workloads grow.

Free capacity does not guarantee sufficient IOPS/throughput. For databases, performance quotas often hit ceilings before GB quotas.

## 16. Capacity Planning Across Accounts, Projects, and Environments

An organization typically operates multiple accounts/projects/subscriptions and environments. Clarify where quotas live and who is accountable.

### Account Partitioning

Common layout:

- Production account/project.
- Non-production account/project.
- Shared platform/network account.
- Security/logging account.
- Data/analytics account.
- Disaster recovery account.

Separating accounts limits blast radius and aids cost governance, though quotas generally do not pool or auto-share across accounts. DR capacity must be planned separately in the target region/account.

### Allocation Models

Quotas can be allocated by:

- Team/owner.
- Environment.
- Workload criticality.
- Forecasted demand.
- Budget.
- Reservations/commitments.
- Growth plans.

For example, an organization with 500 vCPU provider quota might internally allocate 300 to production, 80 to staging, 40 to CI, 40 to data batch, and keep 40 as contingency. Total allocations do not exceed 500, yet family/region quotas and real capacity still require verification.

### Shared Platforms

Network gateways, observability, DNS, Kubernetes system pools, and shared databases also consume quota. Assign an owner for shared capacity and establish a cost-allocation model so workloads do not underestimate shared resource consumption.

### Do Not Allocate 100% of Quota

If 100% of quota is parceled out to teams, the platform has zero room for rollouts, recovery, migrations, or emergency scaling. Maintain a contingency pool and define who can authorize its use.

## 17. Governing Quota Requests and Approvals

Quota increases require a workflow for both the provider and organization to assess necessity, cost impact, and risk.

### Required Request Details

- Account/project/subscription and region.
- Exact service/resource/quota metric.
- Current limit and requested limit.
- Current usage, peak, and forecast.
- Workload/business driver.
- Target effective date.
- Impact scenario if denied.
- Estimated cost and budget owner.
- Capacity reservations/fallbacks if needed.
- Evidence from benchmarks, launch plans, or incident/DR mandates.
- Technical owner and approver.

### Workflow

1. Workload owner produces demand forecast.
2. Platform/FinOps verifies metric and quota scope.
3. SRE/architecture evaluates availability and capacity.
4. Finance checks budget/commitments.
5. Security/governance reviews scope if needed.
6. Authorized owner submits request to provider.
7. Track ticket and confirm new limit.
8. Update inventory, alert thresholds, and forecasts.
9. Verify live quota via API/console before deploying.

### Tiered Approvals

Classify as:

- Small increase within approved allocation: platform owner approves.
- Production capacity increase: SRE + budget owner.
- Expensive GPUs or dedicated capacity: architecture + finance.
- Emergency quota increase: incident commander/authorized approver, with post-incident review.

Do not let resource creators raise quotas or grant themselves unlimited budgets if policy requires separation of duties.

## 18. Monitoring, Alerts, and Quota Runway

Quota monitoring must inspect current usage, forecasted peaks, and lead times.

### Alert Thresholds

Use tiered severity thresholds:

| Level | Illustrative Condition | Action |
|---|---|---|
| Info | Usage exceeds 60% | Log and monitor trend |
| Warning | Forecasted peak exceeds 75% | Verify forecast and owner |
| Action | Usage/forecast exceeds 85% | Open quota request or free resources |
| Critical | Below lead-time buffer or hits 95% | Escalate, activate fallback |
| Exhausted | API returns quota exceeded | Trigger incident/runbook, shed or shift load |

Actual thresholds depend on lead time, growth rate, and criticality. GPU quotas with long lead times may require alerts below 70%.

### Forecast-Based Alerts

Do not alert solely when current usage crosses 80%. If current usage is 40% while growth is accelerating, a 30-day forecast could hit 95%. Alerts based on projected exhaustion dates are far more actionable.

### Dashboard

A quota dashboard should display:

- Limit, current usage, and peak.
- 30/60/90-day forecasts.
- Headroom and runway.
- Account/region/service/family scope.
- Pending quota requests and expected approval dates.
- Capacity reservations and provider capacity status.
- Owner, budget, and criticality.
- Historical quota increases and post-increase utilization.

### Periodic Reviews

- Daily: critical quotas for autoscaling and production.
- Weekly: forecasted peaks and pending requests.
- Monthly: allocations by team and environment.
- Quarterly: growth plans, reservations, region strategy, and unused quotas.

## 19. Integrating Quotas with Autoscaling

Autoscalers react to demand, while quotas act as a hard ceiling. If an autoscaler is unaware of remaining quota, it may loop endlessly requesting resources that cannot be provisioned.

### Capacity Envelope

Define maximum scale as the minimum across all constraints:

\[
ScaleMax = \min(
QuotaAvailable,
ProviderCapacity,
SubnetCapacity,
BudgetCapacity,
DependencyCapacity,
PolicyLimit
)
\]

This is a conceptual model; each term must be normalized into the same unit of workload capacity before comparing.

### Quota-Aware Scaling

- Read remaining quota and node pool maximums.
- Set appropriate max replica counts.
- Prefer tested fallback instance families/zones.
- Detect quota errors and stop futile creation retries.
- Shed load or queue requests when unable to scale further.
- Preserve headroom for system/DR needs.
- Alert owners when autoscalers approach quota boundaries.

### Scale-In and Quota Reclamation

When demand drops, deleting unused resources frees quota. However, never delete standby resources or capacity reservations before verifying RTO/DR and policy compliance. TTLs/cleanups work well for dev/test, whereas production requires owner sign-off and approval.

## 20. Growth-Based Capacity Planning: Practical Example

An API platform currently runs 120 vCPUs in region A. Current peak usage is 150 vCPUs due to autoscaling. Business forecasts 15% monthly traffic growth over 4 months plus a quarter-end campaign with a 1.3 peak multiplier.

Baseline forecast after 4 months:

\[
D(4) = 150 \times 1.15^4 \approx 262.4\ vCPU
\]

Campaign peak:

\[
D_{\text{campaign}} = 262.4 \times 1.3 \approx 341.1\ vCPU
\]

To maintain 20% headroom:

\[
Quota_{\text{target}} = \frac{341.1}{0.8} \approx 426.4\ vCPU
\]

Rounding to instance shapes and quota units, the plan can target 432 vCPUs. With a current quota of 300 vCPUs, an increase of ~132 vCPUs should be requested.

Additional checks required:

- Does 432 vCPUs fit within the target instance family's quota?
- Do zones A/B/C have sufficient provider capacity?
- Do subnets have enough IPs for nodes and Pods?
- Can database connections and network throughput sustain the peak?
- Does the budget cover the 341 vCPU peak plus headroom?
- Does the DR region need matching capacity?
- Does the quota request lead time fall well ahead of the campaign?

If any single layer falls short, raising regional vCPU quota alone will not suffice.

## 21. Multi-Team Kubernetes Quota Planning Example

A cluster has 400 allocatable CPUs and 1 TiB of memory. Team allocations:

| Namespace | CPU requests quota | Memory requests quota | Pod quota | Owner |
|---|---:|---:|---:|---|
| production-api | 160 CPU | 320 GiB | 200 | API team |
| production-worker | 100 CPU | 256 GiB | 300 | Processing team |
| data-platform | 80 CPU | 256 GiB | 150 | Data team |
| staging | 30 CPU | 64 GiB | 100 | Platform |
| system | 20 CPU | 64 GiB | 100 | Platform |
| Contingency | 10 CPU | 64 GiB | — | SRE |

Total CPU allocation equals 400. However, namespace quotas do not guarantee the scheduler can place Pods if node affinity, zones, GPUs, taints, or volume topologies mismatch. Also subtract DaemonSet/system overhead from allocatable resources and check node pool scaling quotas.

When the API team requests an extra 40 CPUs:

1. Check forecasts and peak usage.
2. Identify whether any namespace can trim unused allocations.
3. Verify whether cluster allocatable space remains or node pool scale-out is required.
4. Check cloud vCPU quotas and subnet IPs.
5. Assess impact on worker/data teams.
6. Approve the allocation or request a cloud quota increase if needed.
7. Update `ResourceQuota` and alerts.

## 22. Strategies When Quotas Cannot Be Raised in Time

Quota requests may be denied or delayed. Prepare operational contingencies:

- Use benchmarked equivalent instance families.
- Shift workloads to another region/zone if data residency and latency permit.
- Pause non-priority dev/test or batch jobs.
- Reduce replicas on workloads tolerant of lower capacity.
- Use queues to absorb bursts and process asynchronously.
- Improve compute efficiency via code optimization, caching, and I/O batching.
- Reduce retention or clean up temporary data per policy.
- Leverage managed services with different capacity pools if appropriate.
- Offload a portion of work to serverless/other container/VM pools.
- Use reservations or dedicated capacity if viable and time permits.

Never bypass quotas by spinning up extra accounts or unapproved regions outside governance. Doing so breaks security, auditing, cost allocation, and data residency.

### Priority Policy

During capacity shortages, prioritize by business criticality:

1. Production transactions and essential control planes.
2. Workloads backed by SLAs/contracts.
3. Batch jobs with imminent deadlines.
4. Non-critical analytics.
5. Dev/test and preview environments.

Priorities must be agreed upon before an incident, not improvised after autoscaling fails.

## 23. Commitments, Reservations, and Quotas

Quotas and reservations are related yet distinct.

- Quotas allow an account to request resources up to a cap.
- Reservations hold or guarantee provisioning capacity for specific resources under provider terms.
- Commitments/discount plans lower rates based on usage or spend commitments without necessarily reserving capacity.
- Spot capacity may be cheaper yet carries no existence guarantee.

With steady growth, use commitments for baselines and on-demand/spot for bursts. When workloads require guaranteed capacity in specific zones/instance families, evaluate dedicated reservations. Ensure corresponding quotas remain large enough to consume those reservations.

### Avoiding Overcommitment

If commitments exceed actual demand, the organization pays for unused capacity. If reservations fail to match instance family/zone or scope, discounts or capacity guarantees may not apply as expected. Review utilization and coverage periodically.

## 24. Multi-Region and Disaster Recovery Quotas

DR is frequently overlooked in quota planning. When a primary region fails, the standby region may need to scale rapidly to multiples of its normal baseline.

Key questions:

- Is DR active-active, warm standby, or pilot light?
- Does the standby region hold enough quota for critical workloads?
- Are reservations or capacity guarantees in place?
- Are database replication and storage quotas sufficient?
- Are network/IP/NAT/load balancer quotas sufficient?
- Are DNS and certificates ready?
- Can the provider supply capacity during a regional incident?
- Do DR drills create temporary peak usage and quota consumption?

### Warm Standby

Warm standby keeps partial compute running continuously. Quotas must cover the current baseline plus failover scale-up. Measure capacity scale-up times.

### Pilot Light

Pilot light maintains minimal components. Quotas must cover full scale-out upon activation. Testing quotas only during live drills risks discovering shortages too late.

### Active-Active

Both regions serve live traffic simultaneously. Each region needs enough capacity to absorb redirected traffic when the other fails, or controlled load shedding. Never assume a 50/50 traffic split means each region only needs 50% capacity.

## 25. Governance and Ownership Responsibilities

Quotas are not solely a cloud admin's job. Workload owners understand demand; platform teams understand quota scopes and node pools; FinOps understands budgets; SRE understands SLOs and failure modes; security/governance oversees accounts and policies.

| Role | Responsibility |
|---|---|
| Workload owner | Forecast demand, benchmark, and justify business need |
| Platform/cloud team | Maintain quota inventory, check scopes, submit requests, and manage shared capacity |
| SRE | Headroom, N+1, availability, alerts, and fallbacks |
| FinOps/Finance | Budgets, cost forecasts, commitments, and allocation |
| Security/governance | Account boundaries, policies, region restrictions, and approvals |
| Provider support/account team | Confirm quota/capacity availability and lead times |

### Ownership Must Tie to Each Quota

Every critical quota needs a primary owner, backup owner, escalation path, and review cadence. Do not leave quota inventories listing only service names without accountable owners.

### Exceptions

If a team must exceed its internal allocation, require:

- Justification and duration.
- Impact on other teams.
- Budget owner sign-off.
- Plan to reclaim or reduce allocation.
- Audit trail and review date.

## 26. IaC and Automation for Quota Governance

Quota inventories, alerts, and resource allocations can be managed via code and policy-as-code.

### IaC

Infrastructure as Code can declare:

- Node pool min/max bounds.
- `ResourceQuota`/`LimitRange`.
- Autoscaling boundaries.
- Instance family allowlists.
- Region allowlists.
- Network/subnet capacity.
- Budget alerts and owner tags.

Provider quotas are sometimes managed via separate APIs/consoles and not every quota supports IaC. Verify provider resource support and do not assume Terraform/ARM/CloudFormation declarations automatically raise every quota.

### Policy-as-Code

Policies can reject deployments if:

- Node pool max exceeds approved allocation.
- Workloads lack owners/cost centers.
- GPU requests lack approval.
- Regions are disallowed.
- Resource requests exceed namespace quotas.
- Production workloads lack budgets or capacity plans.

### Automation

You can automate:

- Collecting quotas and usage via provider APIs.
- Calculating headroom and forecasts.
- Opening tickets when projected exhaustion nears lead time.
- Verifying quotas after requests are approved.
- Detecting idle/orphan resources.
- Updating dashboards and allocation reports.

Automation must be idempotent, audited, rate-limited, and least-privilege. Never auto-delete production resources solely on a single low-usage metric.

## 27. Monthly Capacity Review Process

An effective review connects forecasts directly to concrete actions.

1. Compare actual usage against the previous period's forecast.
2. Analyze forecast variance and root causes.
3. Update user, traffic, data, and release growth plans.
4. Check peaks/seasonality and upcoming events.
5. Calculate quota runway by scope/resource.
6. Check provider capacity and reservation utilization.
7. Identify quota requests to open in the cycle.
8. Review N+1 headroom and DR regions.
9. Evaluate budgets, commitments, and cost per workload.
10. Assign owners, due dates, and escalations for every action.

Review outputs should include demand forecasts, target quotas, gaps, cost estimates, request tickets, owners, and target completion dates.

## 28. Quota Exceeded Runbook

When deployments or autoscaling are blocked:

### Identify the Limit

- Read the API error code/message.
- Identify the exact metric, scope, region, and resource family.
- Check current quota and usage.
- Distinguish quota exceeded, rate limits, provider capacity shortages, and policy denials.

### Mitigate Impact

- Stop infinite retries from autoscalers/automation.
- Keep existing workloads stable.
- Prioritize critical workloads.
- Pause non-urgent dev/test or batch jobs.
- Switch to tested fallback instance families/zones.
- Throttle queues and concurrency if dependencies are affected.

### Recover

- Open a quota request or escalation.
- Check capacity availability and reservations.
- Confirm the new limit via API/console.
- Test creating a small resource in the target scope.
- Resume autoscalers/rollouts incrementally.
- Monitor errors, usage, and budgets.

### Post-Incident

- Update inventory and forecasts.
- Determine why alerts failed to catch it earlier.
- Adjust thresholds/lead times.
- Update runbooks and owners.
- Evaluate whether allocation or architectural changes are needed.

## 29. Common Mistakes

**Looking only at aggregate quotas.** Family, GPU, IP, storage, or regional quotas can hit limits first. Track each metric with its exact scope.

**Assuming a quota increase guarantees capacity.** Providers may lack hosts or accelerators in a zone. Check availability/reservations separately.

**Forecasting with averages.** Peaks, seasonality, and failure reserves push demand far higher. Use p95/peaks and scenarios.

**Waiting until quota is nearly full to request increases.** Processing lead times may exceed remaining runway. Forecast projected exhaustion dates.

**Raising quotas without checking budgets.** Higher quotas enable larger scaling and higher bills. Pair quota requests with cost estimates and guardrails.

**Raising concurrency while forgetting dependencies.** Databases, NATs, APIs, and storage can overload before compute. Plan end-to-end.

**Allocating 100% of quota to teams.** Leaves no headroom for rollouts, migrations, recovery, and incidents. Keep a contingency pool.

**Creating multiple accounts to evade quotas.** Breaks governance, auditing, networking, and cost allocation. Design account boundaries intentionally.

**Ignoring DR.** Standby regions may lack quota when failover is needed. Audit and rehearse DR quotas.

**Letting autoscalers retry endlessly on exhausted quotas.** Causes API throttling and log noise. Distinguish quota errors from transient errors, halt retries, and trigger the runbook.

## 30. Growth-Based Quota and Capacity Checklist

### Inventory and Scope

- [ ] Quota inventory exists by provider, account, project, subscription, region, and service.
- [ ] Units, current limits, usage, peaks, and owners are recorded.
- [ ] Quotas, rate limits, runtime limits, and provider capacity are clearly distinguished.
- [ ] Aggregate, family, and supporting quotas are all checked.
- [ ] Inventory covers CPU, GPU, memory shapes, storage, networking, IPs, serverless, and APIs.

### Forecast and Capacity

- [ ] Workload drivers and 30/60/90-day (or appropriate horizon) forecasts exist.
- [ ] Conservative, expected, and high-growth scenarios are modeled.
- [ ] Seasonality, launches, migrations, and DR are factored in.
- [ ] Benchmarks translate workload demand into resource demand.
- [ ] Peaks, headroom, and N+1/failure-domain capacity are calculated.
- [ ] Provider capacity and reservations are checked separately from quotas.
- [ ] Quota runway and request lead times are tracked.

### Governance and Cost

- [ ] Every critical quota has an owner and approver.
- [ ] Quota requests include forecasts, business drivers, costs, and fallbacks.
- [ ] Team/environment allocations maintain a contingency pool.
- [ ] Budget alerts and maximum scale guardrails are in place.
- [ ] Commitments/reservations are reviewed for utilization.
- [ ] Audit trails exist for exceptions and quota changes.

### Monitoring and Operations

- [ ] Dashboards display usage, peaks, headroom, forecasts, and runway.
- [ ] Alerts trigger based on projected exhaustion dates.
- [ ] Autoscalers respect quota limits and node pool maximums.
- [ ] Fallbacks exist for instance families/zones or workload priority.
- [ ] A quota-exceeded runbook exists and halts futile retries.
- [ ] DR region quotas and capacity are verified.
- [ ] Forecasts vs. actuals are reviewed periodically.

## 31. Self-Check

1. How does quota differ from capacity, allocation, and reservation?
2. Why does raising vCPU quota not guarantee you can launch a GPU instance in a zone?
3. How do account, region, resource-family, and namespace quotas differ?
4. Distinguish hard quotas, soft quotas, runtime limits, and API rate limits.
5. Which fields belong in a quota inventory to support forecasting and ownership?
6. With current demand of 100 vCPUs growing 12% per month, roughly what will demand be in 6 months?
7. If forecasted peak is 240 vCPUs and you want to preserve 25% headroom, what target quota is needed?
8. Why does low current usage not guarantee a long quota runway?
9. How do you calculate N+1 capacity when losing one node or one zone?
10. What do Kubernetes `ResourceQuota` and `LimitRange` control?
11. Why does raising serverless concurrency require checking database connections and downstream quotas?
12. What details must a quota request contain for the provider and budget owner to evaluate?
13. How should an autoscaler react when quotas are exhausted without retrying endlessly?
14. Draft a 90-day quota plan for a workload growing 15% per month with seasonal peaks and a DR region.

Quota and capacity planning for growth is a continuous loop: inventory limits, measure usage, forecast demand, calculate headroom, verify provider capacity, submit quota requests ahead of lead times, and monitor outcomes. When quotas tie into workload owners, forecasts, budgets, autoscaling, and DR plans, organizations can scale compute controllably and minimize the risk of failing to scale when it matters most.
