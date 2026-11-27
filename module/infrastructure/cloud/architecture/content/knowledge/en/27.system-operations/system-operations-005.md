# Managing Service Quotas and Capacity Planning

## 1. Why Are Quotas and Capacity Two Distinct Operational Problems?

A cloud application may be designed to scale horizontally, yet still fail to scale when an external limit blocks provisioning additional resources. For example, an autoscaler tries to add VMs but the subscription hits its vCPU quota; Kubernetes tries to schedule pods but the node pool runs out of IPs; a service needs more connections but the database caps connection counts; or a workload sends messages but the broker or account reaches its throughput quota.

A **service quota** is a limit imposed by a cloud provider or service on an account, region, resource, or operation. **Capacity** is the system's actual ability to process workload under defined conditions: requests per second, concurrent operations, throughput, storage, memory, connection pools, and other constraints.

Quotas may be higher or lower than an application's safe capacity. Increasing a quota does not automatically enable the system to handle more requests; conversely, passing capacity tests in the current environment does not guarantee production has enough quota to scale.

In the **CLOUD_ARCHITECTURE** module, quota management and capacity planning must connect business demand with compute, networking, storage, scaling, and operations. Designs must answer: what is current demand, how will it grow, which limit will be hit first, how much reserve is needed, and if a failure domain goes down, does enough capacity remain to serve critical load?

After this lesson, you will be able to:

- Distinguish service quotas, hard limits, soft limits, rate limits, and capacity.
- Build a quota and dependency inventory across accounts, regions, services, and resources.
- Forecast workload from demand drivers and traffic characteristics.
- Calculate capacity, headroom, safety margins, and bottlenecks across every tier.
- Design autoscaling, admission control, queueing, and graceful degradation.
- Plan quota increases, prepare supporting evidence, and track requests.
- Test peak load, bursts, failovers, and noisy neighbors.
- Evaluate cost, reliability, security, and operations under Well-Architected principles.

## 2. Distinguishing Quotas, Limits, and Capacity

### 2.1. Common Types of Limits

| Concept | Meaning | Example |
|---|---|---|
| Service quota | Threshold enforced by provider per account/region/resource | Total vCPUs allowed in a region |
| Hard limit | Threshold that cannot be exceeded by sending more requests | Maximum objects or connections for a tier |
| Soft limit | Threshold adjustable via support/request or plan change | Default account vCPU quota |
| Rate limit | Number of requests/operations per unit of time | API permits 1,000 requests/minute |
| Concurrency limit | Number of simultaneously executing operations | Maximum 200 database connections |
| Capacity | Throughput/volume the system truly handles within SLO | 4,000 booking requests/s at p95 under 300 ms |
| Allocation | Portion of capacity/quota reserved for a workload or tenant | 30% of worker slots reserved for payment |
| Headroom | Spare capacity relative to projected demand or current load | 25% unused CPU capacity |

Terminology and semantics vary across providers. Always verify the exact service, account scope, region scope, quota type, and how the quota is metered.

### 2.2. Example: Quota Does Not Equal Throughput

BookingCloud has a 500-vCPU quota in its region. The cluster currently uses 100 vCPUs and can scale up to 300 vCPUs via autoscaling. The database currently sustains 2,000 transactions/second before p99 breaches SLO.

Increasing the quota from 500 to 1,000 vCPUs will not make the database automatically handle 4,000 transactions/second. When the database is the bottleneck, adding application pods only increases connections and queueing, making latency worse.

### 2.3. Quotas by Scope

Quotas can apply at multiple scopes:

- Organization/organizational unit.
- Account, subscription, or project.
- Region or availability zone.
- Service or API.
- Resource type, instance family, or SKU.
- Per-tenant or per-user limits inside the application.
- Per-operation, per-minute, or concurrent requests.

A single resource may be blocked by multiple quotas simultaneously. For example, creating a VM requires vCPU quota, instance count, IP addresses, disks, NICs, regional capacity, and permissions. Checking one quota in isolation does not prove deployment will succeed.

## 3. Building a Quota Inventory

You cannot manage what is not recorded. Build an inventory for every critical service and dependency.

### 3.1. Fields to Track

| Field | Purpose |
|---|---|
| Provider/service | Cloud provider and relevant service |
| Account/project/subscription | Quota scope |
| Region/zone | Geographic/failure-domain scope |
| Quota name/ID | Exact identifier of the limit |
| Current limit | Current enforced ceiling |
| Current usage | Current consumption |
| Peak usage | Highest usage within the observation window |
| Unit/reset window | vCPUs, requests/min, GB, connections, tokens... |
| Increase path | Console/API/support request/plan upgrade |
| Lead time | Time required for a quota increase to take effect |
| Owner | Accountable team |
| Critical date | Projected date of breaching the threshold |
| Dependency | Resources/workloads impacted if limit is hit |

Never store quota numbers as undated notes. Providers may change default quotas or calculation rules; the inventory must record verification timestamps and sources.

### 3.2. Quota Dependency Map

~~~mermaid
flowchart TB
    SCALE["Autoscaler requests more nodes"] --> VM["Compute quota"]
    VM --> CPU["Regional vCPU quota"]
    VM --> IP["Subnet IP availability"]
    VM --> DISK["Disk / volume quota"]
    VM --> NIC["NIC / network quota"]
    CPU --> DEPLOY["Workload capacity"]
    IP --> DEPLOY
    DISK --> DEPLOY
    NIC --> DEPLOY
    DEPLOY --> DB["Database connection / throughput"]
    DEPLOY --> MQ["Broker throughput / partitions"]
    DEPLOY --> LB["Load balancer / target quota"]
~~~

Scaling out may simultaneously require compute, IPs, disks, NICs, load balancer targets, database connections, and queue capacity. The inventory should capture these relationships so limits are not discovered only at deployment time.

### 3.3. How to Collect Quotas

- Use cloud quota APIs, service quota dashboards, or account inventories where supported by the provider.
- Cross-check IaC to see maximum designed resource counts.
- Read billing/usage and monitoring telemetry for actual consumption.
- Manually verify quotas lacking APIs or carrying special semantics.
- Assign owners and review dates to critical quotas.
- Set up periodic automated checks and pre-major-release checks.

Never assume documented defaults reflect your current account's actual quotas. Granted quotas may depend on usage history, region, tier, contracts, and approvals.

## 4. Demand Modeling: Where Does Demand Come From?

Capacity planning starts by quantifying business demand, then translating it into technical resources.

### 4.1. Demand Drivers

For BookingCloud, demand drivers include:

- Active customers and new tenants.
- Concurrent users.
- Hourly/daily/seasonal request rates.
- Read/write ratios and steps per workflow.
- Cache hit rates, queue fan-out, and retries.
- Batch exports, reporting, and import jobs.
- Payload sizes, file uploads, and retention.
- Daily/monthly data growth.
- Marketing campaigns, seasonal peaks, or events.

Do not rely only on daily averages. A workload whose peak is 8x its average requires a completely different plan.

### 4.2. Distinguishing Steady, Peak, and Burst

| Load Pattern | Characteristics | Preparation |
|---|---|---|
| Steady-state | Stable baseline demand | Baseline capacity and utilization targets |
| Peak | Predictable hourly/daily/seasonal rises | Pre-scaling, reservations/quota headroom |
| Burst | Very rapid short-lived spikes | Buffers, admission control, burst capacity |
| Growth trend | Month-over-month/quarter-over-quarter growth | Forecasts and capacity roadmaps |
| Failure load | Load concentrated when a dependency/zone fails | N+1/failover capacity and load shedding |

Burst scaling is not instantaneous if provisioning VMs, nodes, or databases takes several minutes. Forecast and pre-scale ahead of known events.

### 4.3. Workload Profile

Each workload should have a profile:

~~~yaml
workload: booking-api
criticality: tier-1
traffic:
  average_rps: 1200
  peak_rps: 4200
  burst_rps: 6000
  peak_duration_minutes: 20
mix:
  read_percent: 70
  write_percent: 30
latency_objective:
  p95_ms: 300
  p99_ms: 800
availability_target: "99.9%"
growth:
  monthly_percent: 8
  planning_horizon_months: 12
~~~

These figures are illustrative. Real profiles must come from access telemetry, business forecasts, load tests, and upcoming events. Never extrapolate peak from average RPS without knowing the temporal distribution.

## 5. Translating Demand into Capacity

### 5.1. Throughput and Processing Time

A foundational estimate comes from Little's Law:

\[
L = \lambda W
\]

Where:

- \(L\) is the average number of requests/operations currently in the system.
- \(\lambda\) is the average throughput (requests/second).
- \(W\) is the average time a request spends in the system (seconds).

If a service processes 1,000 requests/second and average residency time is 0.2 seconds, average in-flight requests are approximately 200.

This is a steady-state average relationship; do not plug p99 directly in for \(W\) without understanding queueing and distributions. As utilization approaches 100%, latency can grow nonlinearly due to queueing and contention.

### 5.2. Capacity per Instance

If one instance is benchmarked at 250 RPS within the target SLO, serving 4,200 RPS at a 65% target utilization requires:

\[
N = \left\lceil \frac{4200}{250 \times 0.65} \right\rceil = 26
\]

The result of 26 instances is an initial estimate before accounting for N+1, zone failures, rolling deployments, skew, background tasks, and quota constraints. If one zone fails, remaining instances must still cover committed load.

### 5.3. Capacity Chain and Bottlenecks

A request traverses multiple tiers. End-to-end throughput cannot exceed the smallest bottleneck:

~~~text
API gateway capacity       = 8,000 RPS
Booking service capacity   = 6,000 RPS
Inventory service capacity = 4,500 RPS
Database capacity          = 3,000 RPS
Payment provider quota     = 1,500 RPS

End-to-end throughput for payment flow <= 1,500 RPS
~~~

If not every booking request invokes payment immediately, separate the flows and provider call ratios. Do not treat Payment quota as the cap for all GET catalog calls; however, calculate total authorize/capture volume per business mix.

### 5.4. Utilization Targets and Headroom

Do not plan for 95–100% utilization under normal conditions. Systems need headroom to absorb bursts, failovers, rolling deployments, noisy neighbors, and forecast error.

Example:

| Resource | Usable Capacity | Target Utilization | Planning Headroom |
|---|---:|---:|---:|
| Application CPU | 1,000 vCPU | 65% | 35% |
| Database connections | 800 | 60% | 40% |
| Queue consumer slots | 500 | 70% | 30% |
| Storage throughput | 20,000 IOPS | 70% | 30% |

Targets are illustrative. Database connection pools may need lower caps; CPU targets depend on latency sensitivity and scaling speed.

## 6. N+1, Zone Failures, and Reserve Capacity

Capacity plans must specify how much load the system can still serve when a failure domain is lost.

### 6.1. Multi-Zone Example

Suppose three zones evenly host 30 instances, 10 per zone. If total demand is 4,500 RPS and each instance sustains 200 RPS at target SLO, steady-state capacity is 6,000 RPS.

If one zone is lost, the remaining 20 instances provide 4,000 RPS—below the 4,500 RPS demand. This design fails full-traffic N+1. Options include:

- Run higher baseline instances per zone.
- Maintain autoscaling/quota reserves sufficient to replace lost capacity.
- Shed load by priority during failover.
- Define explicit degraded-mode SLOs.

### 6.2. Quota Reserves for Failover

Additional quota must exist in target regions/zones, not only the primary region. If a DR region has never been scaled to production levels, failover may fail when creating VMs/IPs/database replicas due to insufficient quota.

Verify:

- vCPUs and instance families.
- IP/subnet address space.
- Load balancers/listeners/targets.
- Database replicas/storage/IOPS.
- NAT gateways, private endpoints, and network throughput.
- KMS/API quotas and secret access.
- Queue partitions/throughput and worker capacity.

### 6.3. Degraded-Mode Capacity

Not every workload must retain 100% of features when a zone fails. Prioritize:

1. Authentication, booking status, and critical cancellations.
2. New bookings with safely verifiable inventory.
3. Payment status/reconciliation.
4. Deferred notification retries and batch reports.
5. Temporarily disabling recommendations, analytics refreshes, or secondary features.

Prioritization must reflect business impact and safety invariants, not just compute cost.

## 7. Autoscaling and Capacity Control

Autoscaling adjusts resources to demand or metrics, but does not replace quota planning.

### 7.1. Scaling Signals

- CPU/memory utilization.
- Request rate and latency.
- Active/in-flight requests.
- Queue depth and oldest message age.
- Worker utilization and processing time.
- Database pool wait and storage IOPS/throughput.
- Custom business metrics such as booking creation backlog.

Low CPU does not mean a service has spare capacity if it is waiting on a database or external provider. Queue age/latency is often a better worker scaling signal than CPU.

### 7.2. Horizontal and Vertical Scaling

| Type | Description | Limits |
|---|---|---|
| Horizontal scaling | Add/remove instances/pods/workers | Needs quota, IPs, scheduler capacity, and load distribution |
| Vertical scaling | Increase instance CPU/RAM/IOPS | SKU ceiling, may require restarts/downtime, creates single-node dependency |
| Scheduled scaling | Increase capacity before predicted peaks | Depends on forecast; wastes spend if load fails to arrive |
| Predictive scaling | Use patterns/history to pre-scale | Depends on data quality and pattern stability |

### 7.3. Scale-Out Latency

Provisioning nodes, pulling images, warming caches, attaching volumes, starting JVMs, or establishing connection pools takes time. Scale triggers must fire before the system hits saturation.

An overly sensitive autoscaler can oscillate continuously (flapping). Use hysteresis, stabilization windows, cooldowns, min/max replicas, and scale-down protection for stateful workloads.

### 7.4. Autoscaling and Quotas

When an autoscaler hits max replicas or a cloud API returns quota exceeded:

- Alert before projected thresholds.
- Log explicit scale-failure reasons.
- Do not retry provisioning infinitely.
- Protect healthy minimum capacity.
- Throttle admission or shed load under control.
- Maintain a quota request workflow and escalation owner.

## 8. Admission Control, Queueing, and Fairness

When demand exceeds capacity, continuing to accept every request overloads the system. **Admission control** decides which requests are accepted, deferred, or rejected.

### 8.1. Bounded Queues

Queues absorb short bursts and smooth load, but unbounded queues turn overload into latency, memory, and storage exhaustion. Bound queue depth, message age, retention, and consumer concurrency.

### 8.2. Rate Limits and Concurrency Limits

- Rate limits govern request rates per tenant/client/operation.
- Concurrency limits cap simultaneously executing operations.
- Bulkheads isolate budgets across dependencies or workload types.
- Retry budgets cap additional load generated by retries.

Together, these mechanisms stop one slow request from exhausting pools and prevent one tenant from stalling the whole system.

### 8.3. Multi-Tenant Fairness

In multi-tenant SaaS, quotas should enforce:

- Per-tenant request budgets.
- Concurrent job/export limits.
- Storage/egress budgets.
- Priority tiers or reserved capacity.
- Fair scheduling/weighted queues.
- Alerts and tier-upgrade workflows.

Never let a single tenant consume all shared capacity simply by sending more requests.

### 8.4. Graceful Degradation

When resources approach limits, shed non-critical features, defer reports, lower refresh frequencies, return 429/503 with `Retry-After`, or serve stale data only where business rules allow. Never degrade by skipping authorization, skipping validation, or confirming bookings/payments without an authoritative source.

## 9. Forecasting and Capacity Roadmaps

### 9.1. Growth-Based Forecasting

If current demand is \(D_0\) and grows steadily at rate \(g\) per month, demand after \(t\) months is:

\[
D_t = D_0(1+g)^t
\]

For example, with \(D_0 = 4,000\) RPS and 8% monthly growth, after 12 months:

\[
D_{12} = 4000(1.08)^{12} \approx 10,072 \text{ RPS}
\]

This is only a simple exponential growth model. Real forecasts must distinguish user growth, per-user usage intensity, traffic seasonality, feature adoption, and architectural changes.

### 9.2. Scenario Planning

Develop at least three scenarios:

| Scenario | Assumptions | Used For |
|---|---|---|
| Base | Planned growth and traffic | Budgeting and normal operations |
| High | Higher-than-expected adoption or campaigns | Peak/quota preparation |
| Stress | Surges, provider outages, or zone loss | Reliability and degraded-mode planning |

Forecasts must include assumptions and confidence intervals. Avoid false precision with a single point number for a 12-month plan.

### 9.3. Capacity Roadmap

A roadmap may include:

- Current week/month: baseline workloads, quota inventory, load tests.
- Pre-campaign: request quotas, pre-scale, warm caches, check provider limits.
- Next quarter: shard databases, add regions, or change storage tiers for projected bottlenecks.
- Pre-renewal/major launch: review growth, reserved capacity, costs, and DR tests.

Tie milestones to owners, lead times, acceptance criteria, and due dates.

## 10. Load Testing and Capacity Validation

Capacity cannot be inferred solely from vCPU counts or instance-type marketing specs. Benchmark realistic workloads.

### 10.1. Test Types

| Test Type | Purpose |
|---|---|
| Baseline test | Measure latency/throughput under normal load |
| Load test | Verify target peak for expected duration |
| Stress test | Find saturation points and failure behavior |
| Spike test | Measure handling of sudden traffic surges |
| Soak test | Detect leaks, degradation, and resource accumulation over time |
| Failover test | Verify capacity when losing a zone/region/dependency |
| Quota test | Test scaling/deployment near account/service limits |

### 10.2. Designing Test Workloads

- Use a production-like traffic mix: reads/writes, payloads, tenant distributions, and cache hit rates.
- Simulate concurrency and ramp-up/ramp-down, not only fixed RPS.
- Include think time/user behavior when modeling sessions.
- Use large enough datasets to avoid misleadingly warm caches or tiny DB tables.
- Test against real dependencies or emulators with realistic capacity/latency.
- Avoid running load tests against production without approvals, isolation, and guardrails.
- Measure p50/p95/p99, errors, resource saturation, queue age, and cost.

### 10.3. Determining Safe Capacity

Safe capacity is the highest load that still meets SLOs with required headroom—not maximum throughput right before processes crash.

Test example:

| Load | p95 Latency | Error Rate | Conclusion |
|---:|---:|---:|---|
| 2,000 RPS | 180 ms | 0.02% | Pass |
| 3,000 RPS | 220 ms | 0.03% | Pass |
| 4,000 RPS | 280 ms | 0.05% | Near threshold pass |
| 4,500 RPS | 620 ms | 0.8% | Fails SLO |
| 5,000 RPS | 1,400 ms | 4.2% | Saturation |

With an SLO of p95 under 300 ms and errors under 0.1%, safe capacity may be set at 4,000 RPS or lower depending on headroom/failure requirements, even though the system processed some requests at 4,500 RPS.

## 11. Managing Quota Increase Requests

Quota increases take review time; some increase automatically, while others require support review or plan changes. Never wait until deployment day to open a request.

### 11.1. Preparing Evidence

A strong request includes:

- Quota name, account/region/service scope, and current limit.
- Current usage, peak usage, and trends.
- Proposed new limit and calculation.
- Workload/business justification.
- Date quota is needed and lead time.
- Architecture/capacity evidence: load tests, scaling plans, dependencies.
- Security/reliability controls proving the increase is governed.
- Owner and contact person.

### 11.2. Estimating Requested Quotas

Do not request barely enough to deploy. Calculate:

~~~text
required_limit =
    peak_planned_usage
  + failover_reserve
  + rollout_reserve
  + growth_buffer
~~~

Do not blindly add overlapping reserves. For example, a rolling deployment may need surge capacity for only a few minutes; failover reserves may share resource pools if the threat model treats scenarios as non-concurrent. If peak traffic must be sustained while a zone is down and a rollout is active, size for the combined scenario.

### 11.3. Tracking Request Status

Manage quota requests like a deadline-bound dependency:

- Proposed: demand calculated, evidence prepared.
- Submitted: provider acknowledged request.
- In review: awaiting info/approval.
- Approved: quota raised; verify scope and effective time.
- Rejected/partial: update capacity plan or escalate.
- Applied: scale/deploy tested successfully in target scope.

Approval does not guarantee the quota is active in every region/subscription. After approval, re-query the quota and run a safe deployment/scale check.

## 12. Capacity and Cost Optimization

Capacity above demand increases cost for always-on resources; too little capacity causes errors, latency, and lost revenue. Optimize based on total cost-to-serve.

### 12.1. Cost Categories

- Baseline compute, autoscaling, and standby capacity.
- Database CPU, storage, IOPS, and connection/throughput tiers.
- Network egress, NAT, private endpoints, and load balancers.
- Queue/broker partitions, throughput, and retention.
- Cache memory and replication.
- Observability ingestion/storage/querying.
- Backups, snapshots, and DR resources.
- License/support tiers or provider minimum commitments.

### 12.2. Reserved vs. On-Demand Capacity

Reserved capacity/commitments lower costs for steady-state loads; on-demand/flexible capacity suits bursts or uncertain demand. Weigh:

- Flexibility to change instance families/regions.
- Commitment duration and utilization.
- Scaling availability within zones/regions.
- Standby DR costs.
- Overprovisioning cost versus downtime risk.

### 12.3. Cost per Business Transaction

Instead of watching only the total bill, track:

\[
\text{Cost per booking} =
\frac{\text{Infrastructure + platform cost in period}}
{\text{Successful bookings in period}}
\]

This metric reveals the efficiency of caching, query, queue, or autoscaling optimizations. However, allocate shared costs consistently and never cut costs by sacrificing reliability or security.

## 13. Quotas and Capacity in Multi-Region Architectures

### 13.1. Active-Active

Multiple regions serve traffic simultaneously. Capacity and quotas must cover normal load distribution, cross-region traffic shifts, and a single-region failure. If failover shifts 100% of traffic to surviving regions, those regions must have quotas and resources ready or rapidly provisionable with high reliability.

### 13.2. Active-Passive

A DR region may run a smaller footprint, but you must know scale-up times, quotas, IPs, database restore/replication lag, KMS, and endpoint dependencies. Never use the primary region's quotas as proof the DR region has sufficient capacity.

### 13.3. Shared Quotas vs. Regional Quotas

Some limits apply globally across an account; others apply per region. Avoid confusing regional with global quotas or assuming headroom in one region implies headroom in another.

### 13.4. External Dependencies

Payment providers, email APIs, SMS gateways, identity providers, and other SaaS vendors enforce their own quotas. They may limit:

- Requests per second or per minute.
- Concurrent API calls.
- Daily transaction/message caps.
- Burst quotas.
- Tenant/account-level quotas.
- Separate sandbox and production quotas.

An end-to-end capacity plan must incorporate provider quotas, retry budgets, circuit breakers, and degraded-mode behaviors.

## 14. Monitoring and Alerting on Quotas and Capacity

### 14.1. Essential Metrics

| Metric | Meaning |
|---|---|
| `quota_limit` | Current limit value |
| `quota_used` | Current consumption |
| `quota_utilization` | Usage divided by limit |
| `peak_utilization` | Peak within observation window |
| `quota_exceeded_count` | Operations rejected due to quota |
| `scale_request_failed` | Times autoscaler failed to add resources |
| `desired_vs_ready_capacity` | Desired versus ready available capacity |
| `saturation/queue_age` | Contention level and wait time |
| `forecast_to_limit_days` | Projected days until hitting quota |
| `cost_per_transaction` | Cost-to-serve efficiency |

Not every provider exposes quota usage as real-time metrics. Scheduled inventory queries writing snapshots to an internal time-series/database may be required.

### 14.2. Alert Thresholds

A sample policy:

- 60%: monitor trends and confirm growth.
- 75%: alert owner, inspect forecasts and headroom.
- 85%: submit/decide quota increase if lead time is long.
- 95%: escalate and activate capacity mitigation plans.
- 100%/quota exceeded: declare incident proportional to impact.

Thresholds must reflect lead time and growth rate. If usage grows 5% per day and the provider needs 3 weeks to process requests, alerting at 85% is already too late.

### 14.3. Forecast to Limit

Simple estimate:

\[
\text{Days to limit} =
\frac{\text{limit} - \text{current usage}}
{\text{average daily net increase}}
\]

Use this only when growth is relatively steady. For bursts/seasonality, use time-series and scenario forecasts. Alerts should factor in uncertainty bounds and request lead times.

## 15. Capacity Review Process and Ownership

A recurring cycle:

1. Collect usage, demand, SLOs, and forecasts.
2. Update quota inventory and dependency maps.
3. Identify bottlenecks from load tests and telemetry.
4. Size capacity for base/peak/stress/failover scenarios.
5. Compare against current quotas and lead times.
6. Submit quota requests or optimize bottlenecks.
7. Approve budgets/reservations/dedicated tiers.
8. Run load and failover tests after changes.
9. Update runbooks, dashboards, and forecasts.

### 15.1. Example RACI

| Activity | Application Team | Platform/SRE | FinOps | Security |
|---|---|---|---|---|
| Business demand forecast | R | C | C | I |
| Quota inventory | C | R | C | I |
| Load/capacity testing | R | R | I | C |
| Quota requests | C | R | C | I |
| Cost/commitment review | C | C | R | I |
| Risk/access review | C | C | I | R |
| Failover capacity | C | R | C | C |

R = Responsible, C = Consulted, I = Informed. Actual assignments depend on the organization.

## 16. Well-Architected Review

| Perspective | Review Questions | Required Evidence |
|---|---|---|
| **Operational Excellence** | Do quotas have owners, inventory, alerts, request lead times, and runbooks? | Quota catalog, forecasts, support tickets, scale-failure alerts |
| **Security** | Do capacity increases widen permissions, public endpoints, or blast radius? | IAM reviews, network policies, tenant quotas, audits |
| **Reliability** | Do peak/failover/rolling deploys have sufficient quotas and headroom? | N+1 models, load tests, DR tests, dependency quota maps |
| **Performance Efficiency** | Are bottlenecks in compute, DB, network, or providers? | End-to-end load tests, p95/p99, queue/saturation metrics |
| **Cost Optimization** | Are headroom/reserves aligned with demand and criticality? | Cost forecasts, cost per transaction, utilization, commitment reviews |
| **Sustainability** | Is there overprovisioning, idle capacity, or wasteful retries/refreshes? | Idle resource inventory, autoscaling efficiency, utilization trends |

Too little capacity leaves the system unresponsive; too much capacity creates waste. The goal is sufficient capacity for committed workloads and failure scenarios with explicitly justified reserves and costs.

## 17. Exercise: Quota and Capacity Planning for BookingCloud

BookingCloud runs in one region with:

- Current Booking API peak of 4,000 RPS.
- One application instance sustains 250 RPS at target SLO.
- Application tier target utilization is 65%.
- Three availability zones.
- Database sustains 3,000 write transactions/second before exceeding its p95 latency objective.
- Payment provider caps requests at 1,500 requests/second.
- A campaign in 3 months is expected to raise peak traffic by 50%.
- Current vCPU quota is 400; peak usage is 240.
- Scaling out requires additional IPs, disks, and load balancer targets.

Complete the following:

**Task 1 — Demand model:** distinguish average, peak, burst, and campaign demand; state assumptions on traffic mix and read/write ratios.

**Task 2 — Application capacity:** estimate instances needed for 4,000 RPS at 65% utilization; add N+1 if one zone fails.

**Task 3 — Bottlenecks:** evaluate the database and Payment provider; show when scaling the application tier does not increase end-to-end throughput.

**Task 4 — Quota inventory:** list quotas to verify beyond vCPUs: IPs, NICs, disks, LB targets, DB, queues, NAT/private endpoints, and provider APIs.

**Task 5 — Forecast:** calculate post-campaign peak and growth buffer; determine quotas needed ahead of the campaign.

**Task 6 — Autoscaling/admission:** propose min/max replicas, scale triggers, queue/concurrency budgets, and degraded modes.

**Task 7 — Quota increase:** draft info required for provider requests, lead times, and owners; compute requested limits including rollout/failover reserves.

**Task 8 — Test plan:** design load, spike, soak, stress, and zone-failover tests with SLO pass criteria.

### Self-Check Analysis Framework

| Question | What Must Be Proven |
|---|---|
| How many instances for peak? | Use per-instance benchmark throughput and target utilization |
| What if one zone fails? | Surviving capacity still meets traffic or degraded policy |
| Is vCPU quota enough? | Include baseline, autoscale max, and rollout surge |
| Is the database a bottleneck? | Compare write demand against safe DB capacity |
| Does Payment provider have enough quota? | Compute share of bookings hitting payment vs. provider limit |
| Campaign +50% surge? | Pre-scale, approved quotas, and capacity tests beforehand |
| Autoscaler blocked by quota? | Alerts, admission control, and fallback/runbook |
| Quota request approved? | Re-query live limits and verify deployment/scaling |

## 18. Pre-Sign-Off Capacity Plan Checklist

- [ ] Quota inventory covers providers, accounts, regions, services, and resources.
- [ ] Owners, current limits, usage, peaks, units, lead times, and increase paths are recorded.
- [ ] Demand model separates steady, peak, burst, growth, and failure loads.
- [ ] Capacity derives from benchmarks at target SLO, not nominal resource specs alone.
- [ ] End-to-end bottlenecks are identified across every tier.
- [ ] Headroom and N+1/failover reserves match failure scenarios.
- [ ] Autoscaling defines min/max, stabilization, cooldowns, and quota-failure handling.
- [ ] Queue/concurrency/rate limits and fairness rules are defined.
- [ ] Degraded modes protect critical workflows.
- [ ] Forecasts include base/high/stress scenarios and uncertainty.
- [ ] Quota requests are opened ahead of deadlines per lead times.
- [ ] Approvals are verified in the exact target account/region/scope.
- [ ] Load, stress, spike, soak, and failover test results exist.
- [ ] Dashboards track utilization, forecast-to-limit, scale failures, saturation, and cost.
- [ ] Cost/headroom trade-offs are reviewed with an assigned owner.

Quota management ensures the cloud platform permits provisioning needed resources; capacity planning ensures those resources actually process workloads within latency, availability, and cost bounds. Combining inventory, demand forecasts, headroom, autoscaling, admission control, load testing, and lead-time-aware quota processes lets operations catch limits before they cause outages and scale reliably with verified business demand.
