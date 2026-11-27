# Calculating Reserve Capacity When Losing a Failure Domain

## 1. Why Must You Size Capacity After Losing a Failure Domain?

A system may look completely healthy while every availability zone (AZ), node, or deployment cell is running. Yet when one failure domain loses connectivity or shuts down, its load usually shifts onto the remaining infrastructure. If the survivors lack sufficient compute, database connections, storage throughput, network bandwidth, or queue consumer capacity, the system may stay "alive" at the infrastructure layer while failing to serve business load.

A **failure domain** is a scope of resources that can fail together from a single incident—such as a host, rack, AZ, region, deployment cell, cluster, or shared dependency. **Failure-domain capacity planning** determines the total capacity to provision so that after losing a chosen failure domain, surviving domains still meet workload SLOs.

Distinguish these terms:

- **Normal capacity:** capacity needed when all domains operate normally.
- **Failover capacity:** capacity remaining or allocatable after one domain fails.
- **Headroom:** unused capacity reserved to absorb fluctuations, bursts, and forecast error.
- **N+1:** extra capacity equivalent to one required unit/domain to survive a single failure under stated assumptions.
- **N+X:** redundancy for X failures or X capacity units; always specify whether X means nodes, zones, or load units.
- **Degraded mode:** a state that trims secondary features or quality to prioritize critical workloads post-incident.

In the **CLOUD_ARCHITECTURE** module, the **System Scaling** chapter treats reserve capacity as part of reliability and scalability, tied to SLOs, RTO/RPO, security, cost, and operations.

After this lesson, learners will be able to:

1. Identify failure domains and the failure assumptions the system must survive.
2. Calculate minimum remaining capacity after losing one or more domains.
3. Distinguish N+1 by node count from N+1 by effective capacity.
4. Add headroom for peak demand, bursts, failover amplification, and scale-up lag.
5. Evaluate compute, database, queue, network, storage, and dependency capacity together.
6. Design degraded modes, traffic shifting, admission control, and recovery.
7. Validate through load tests, fault injection, and failover drills.

## 2. Start From Failure Domains and Service Objectives

You cannot calculate redundancy without defining which failure types you want to survive. "Losing one failure domain" can mean very different things.

| Failure Domain | Example Incident | Scope Potentially Impacted |
| --- | --- | --- |
| Process/container | Crash, OOM, runtime failure | One instance or replica |
| Host/node | Physical host or VM halts | Workloads co-located on the host |
| Rack/power/network segment | Power loss or top-of-rack switch failure | Multiple hosts in the same physical segment |
| Availability zone | Zone outage or loss of connectivity to zone | Compute, storage, networking, and replicas inside the zone |
| Region | Regional outage or network partition | Entire geographic region and dependent services |
| Deployment cell | Misconfiguration or cell overload | Group of tenants/workloads inside the cell |
| Shared dependency | DNS, identity, KMS, control plane, message broker | Can impact multiple zones or regions |
| Provider/service control plane | Managed service control plane unavailable | Provisioning, scaling, failover, or config changes |

A design surviving a single host failure will not necessarily survive an AZ failure. Three AZs do not automatically survive a regional outage if data replication, identity, or DNS all depend on one region.

### 2.1. Write Explicit Failure Assumptions

Example requirements:

- Workloads must survive the complete loss of any one of three AZs.
- Simultaneous dual-AZ loss is excluded from the standard scenario; N+2 scenarios are evaluated separately.
- After losing one AZ, the system must sustain 100% of critical workloads and at least 60% of best-effort workloads.
- Critical APIs must keep p95 under 500 ms and error rates below the SLO threshold.
- Traffic must shift within 60 seconds; supplemental compute may take up to 5 minutes to launch.
- Never confirm bookings/payments if the datastore fails consistency requirements.

These are testable requirements. Saying "the system must be highly available" is not enough to size capacity.

### 2.2. Distinguish Availability, RTO, and RPO

- **Availability/SLO:** target service uptime or quality level to maintain.
- **RTO (Recovery Time Objective):** target time to restore service after an outage.
- **RPO (Recovery Point Objective):** acceptable data loss, typically expressed as time of data.
- **Capacity objective:** load level the system must carry in normal and failover states.

Having plenty of capacity yet taking 30 minutes to fail over still breaches RTO. Failing over rapidly onto a replica missing recent writes still breaches RPO. Capacity is only one piece of resilience.

## 3. Defining N, X, and Target Load

First define **N as true demand**, not necessarily current running instances. Express N in measurable workload units:

- Requests/second by route or cost unit.
- Concurrent requests or active sessions.
- Jobs/second and queue processing throughput.
- CPU cores, memory, IOPS, storage throughput.
- Database connections and query units.
- Ingress/egress network throughput.
- Bookings/payments or transactions/second.

**X** must also be explicit: X failure domains, X nodes, X replicas, or X capacity units. Avoid writing "N+1" without stating how much load one redundant unit can carry.

### 3.1. Design Load Is Not the Daily Average

Use workload profiles instead of averages alone:

- Hourly, daily, seasonal, and event-driven peaks.
- Short bursts and ramp-up rates.
- Projected growth over the infrastructure lifecycle.
- Traffic mix between cheap APIs and resource-heavy APIs.
- Retry amplification when dependencies fail.
- Background and batch jobs overlapping interactive peaks.
- Post-failover surge traffic, such as client status polling or reconnect retries.

Define at least three load tiers:

| Load Tier | Meaning | Purpose |
| --- | --- | --- |
| Typical | Normal everyday traffic | Calculate steady-state utilization and cost |
| Design peak | Realistic high-probability peak and duration | Size minimum operational capacity |
| Stress/extreme | Unexpected bursts or extreme events | Define degraded modes and overload boundaries |

Failovers frequently happen right when external problems hit; never use low average traffic to claim adequate capacity.

## 4. Basic Formula for N+1

Suppose there are M identical failure domains, each providing capacity C. Losing one domain leaves:

```text
Remaining capacity after one-domain loss = (M - 1) × C
```

For survivors to carry design demand D plus headroom H:

```text
(M - 1) × C >= D × (1 + H)

C >= D × (1 + H) / (M - 1)
```

Where H is headroom expressed as a fraction of demand. For M=3 AZs, design demand D=900 request cost units/s, and headroom H=25%:

```text
C >= 900 × 1.25 / (3 - 1)
C >= 562.5 units/s per AZ

Total provisioned capacity >= 3 × 562.5
                               = 1,687.5 units/s
```

After losing one AZ, the remaining two AZs provide 1,125 units/s, matching demand plus headroom of 1,125 units/s. This is pure arithmetic—not yet accounting for skew, dependencies, or asymmetric capacity.

### 4.1. One Extra Node Is Not Enough If Survivors Lack Throughput

With 3 nodes each serving 400 RPS normally, total load is 1,200 RPS. If one node dies, the two surviving nodes can only handle 800 RPS at current sizing. Counting "three nodes" does not prove N+1; verify actual post-failure capacity.

To let two surviving nodes serve 1,200 RPS with 20% headroom, each node must handle:

```text
C >= 1,200 × 1.20 / 2
C >= 720 RPS
```

Capacity may be bounded by CPU, concurrency, or throughput; RPS only works as a proxy when request costs are fairly uniform.

## 5. General Formula for Heterogeneous Failure Domains

In practice, AZs or cells can differ in capacity, and workloads may be distributed unevenly.

Let:

- `C_i` be the usable capacity of domain `i`.
- `D_i` be the load currently running on domain `i`.
- `D` be total demand to serve.
- `L` be the set of domains lost in the scenario.
- `H` be target headroom.

Remaining capacity:

```text
C_remaining(L) = Σ C_i, for all i not in L

Feasibility condition:
C_remaining(L) >= D × (1 + H)
```

Summing total capacity is only a necessary condition when workloads can shift freely. If shards, partition keys, sessions, storage volumes, or tenants are pinned to a specific domain, aggregate capacity may look adequate while pinned workloads still cannot move.

Verify capacity per resource type and placement constraint; never add CPU in AZ A to database connections in AZ B as if they were interchangeable.

### 5.1. Usable Capacity vs. Nominal Capacity

To compute `C_i`, subtract portions unavailable during failover:

- Capacity reserved for OS, sidecars, daemons, monitoring, and system services.
- Nodes/instances undergoing maintenance or degraded.
- Resource caps imposed by account/region quotas.
- Capacity unreachable due to security/network policies.
- CPU/memory capped by container requests/limits.
- Database connections reserved for admin/maintenance or other workloads.
- Capacity consumed by recovery, replication, or rebalancing.

Use **usable capacity** measured under representative workloads, never advertised vCPU counts.

## 6. Calculating Headroom and Utilization Ceilings

Headroom is intentional slack reserved for variance and incidents. Not all "idle" resources can be safely consumed.

Given headroom H over design demand D:

```text
Required capacity = D × (1 + H)
Target utilization = D / Required capacity
                  = 1 / (1 + H)
```

For example, H=25% yields roughly 80% target utilization of provisioned capacity. Using a utilization ceiling U instead, the equivalent formula is:

```text
Required capacity >= D / U
```

Stay consistent with definitions. "25% headroom above demand" differs from "keep 25% of capacity free": the latter implies a 75% utilization ceiling and required capacity of `D/0.75`.

### 6.1. Do Not Apply One Utilization Ceiling to Every Resource

80% CPU may be fine for batch workloads, yet an 80% database connection pool is risky when query durations fluctuate. Network links need headroom for bursts and replication; storage IOPS can see sharp latency spikes near saturation.

Set ceilings per SLO-critical metric:

- CPU: utilization, throttling, run queues.
- Memory: working set, GC, page faults, OOM risk.
- Database: connections, active queries, lock waits, IOPS, replication lag.
- Network: throughput, packet drops, retransmits, connection tracking.
- Queue: age, depth, and drain rate.
- Storage: IOPS, throughput, latency, and free space.

## 7. Post-Failover Load Can Exceed Pre-Failover Load

When a domain drops, the system often absorbs extra indirect load:

- Client retries triggered by timeouts or connection resets.
- Load balancer health-check surges and reconnect storms.
- Users polling status of pending transactions.
- Replicas syncing data or rebuilding indexes.
- Cold caches driving extra database reads.
- Traffic routed over longer network paths.
- One region taking over extra authentication, routing, or orchestration.
- Queue backlogs accumulated during the outage draining all at once.

Model this explicitly:

```text
Failover demand =
    surviving normal demand
  + rerouted demand
  + retry / reconnect amplification
  + recovery / replication work
```

Without controlled load shedding or client retry policies, failover capacity sized purely on steady-state traffic will fall short.

### 7.1. Retry Budgets and Load Shedding

Retries require backoff, jitter, deadlines, and attempt caps. Gateways and services should:
- Shed low-priority workloads early as capacity tightens.
- Cap concurrency and queue depth.
- Shield dependencies with bulkheads and circuit breakers.
- Never stack uncoordinated retries across client, gateway, service, and worker layers without a shared budget.
- Prioritize in-flight transactions needing completion or reconciliation.
- Return `429`/`503` with clear retry guidance.

Capacity planning and traffic management policies must be designed together.

## 8. Compute Capacity in an AZ-Loss Scenario

Compute is the easiest tier to visualize, yet sizing goes beyond counting VMs or containers.

Account for:

- Truly usable vCPU and CPU throttling limits.
- Memory working sets, in-process caches, and GC headroom.
- Remaining instance-type/shape quotas in surviving AZs/regions.
- Pod requests/limits and scheduler placement constraints.
- Autoscaling maximums, node-group ceilings, and IP/subnet address space.
- Startup times, image pulls, initialization, and readiness checks.
- Placement spread/anti-affinity so replicas do not share a single failure domain.
- System workload and daemonset overhead.

### 8.1. Static Spare Capacity vs. Autoscaling

Static spare capacity absorbs load immediately upon failover, at higher steady-state cost. Autoscaling saves idle spend, yet incurs detection, provisioning, boot, image pull, warm-up, and readiness delays.

Scale-out lag:

```text
T_scale =
    detection delay
  + provisioning delay
  + boot / image pull
  + initialization / warm-up
  + readiness / traffic ramp
```

If workloads must survive from second zero, you cannot rely solely on autoscaling with a multi-minute `T_scale`. Pair it with baseline spare capacity, queue buffering, or a degraded mode during scale-up.

### 8.2. Kubernetes Topology Spread

On Kubernetes, verify:
- Pod replicas spread across zones, not merely across nodes.
- `topologySpreadConstraints` and pod anti-affinity rules.
- Whether `PodDisruptionBudget` supports rollouts and node drains properly.
- Node pool/cluster headroom in surviving zones.
- Persistent volume topology and whether volumes can reattach post-zone failure.
- Whether Cluster Autoscaler can spin up nodes in surviving zones.
- Subnets, CNI IPs, and cloud quotas do not block scale-out.

A `PodDisruptionBudget` does not protect against AZ failures—it governs voluntary disruptions, whereas a zone outage is an involuntary failure.

## 9. Stateful Capacity: Databases, Caches, and Storage

Stateless compute shifts across nodes easily. Stateful tiers are harder due to data placement, replication, quorums, and I/O throughput.

### 9.1. Database Capacity

Do not count database instances alone. Evaluate:
- Post-failover query throughput.
- Connection budgets and pooling limits.
- CPU, memory, lock contention, and IOPS.
- Replication lag and catch-up capability.
- Leader/quorum behavior upon losing an AZ.
- Whether read replicas are promotable and sized to handle primary load post-promotion.
- Storage write throughput and free capacity.
- Connection storms when clients reconnect.

If the primary fails, a promoted replica suddenly handles both writes and redirected reads. A replica sized purely for light reads will collapse immediately after promotion.

### 9.2. Quorums and Replica Placement

With 3 voting replicas across 3 AZs, consensus majority quorum is 2. Losing one AZ leaves two members to preserve quorum, depending on protocol and cluster health.

Even so, replica count and quorum do not guarantee performance. The two surviving replicas need enough CPU, IOPS, network, and disk; leader election and recovery still cause latency spikes. Never place two of three voting members in the same AZ if your goal is surviving an AZ outage.

### 9.3. Cache Capacity

Losing a cache node/zone can cause:
- Lost data in cache replicas/shards.
- Key remapping to surviving nodes.
- Lower hit ratios driving higher database QPS.
- Rebuild/warm-up surges in network and CPU load.

Provision spare capacity for both the cache cluster and the origin database to survive cold-cache conditions. Cache replication does not replace a source of truth; durable data belongs in persistent storage.

### 9.4. Object/Block/File Storage

Verify:
- Does replication/erasure coding tolerate the targeted failure domain?
- Remaining storage throughput after losing a node group or zone.
- Can persistent volumes attach in another AZ?
- Are snapshots/backups stored inside or outside the failure domain?
- How long do data recovery and rehydration take?
- What are read/write semantics in degraded mode?

Never assume multi-AZ storage guarantees identical availability, RPO, and performance across every storage class.

## 10. Network Capacity and Failover Paths

Losing a zone concentrates traffic onto remaining paths. Networking is an often-overlooked bottleneck because compute and database dashboards still look green.

Account for:
- Load balancer capacity and new connection rate.
- NAT, firewall, and traffic inspection throughput.
- Transit gateway/router bandwidth and packet-processing rates.
- Cross-AZ and cross-region replication traffic.
- Internet egress bandwidth.
- DNS, service discovery, and connection tracking tables.
- Subnet/IP address capacity for pod/instance scale-out.
- TLS termination and certificate/handshake CPU.

### 10.1. Traffic Concentration

If traffic normally splits evenly across three AZs, each takes one-third. Losing one AZ forces the two survivors to carry total load. Worse, load balancer imbalances or client affinity can skew distribution further.

Example with 9 Gbit/s total traffic:
- Normally each AZ carries 3 Gbit/s.
- After losing one AZ, the two remaining AZs average 4.5 Gbit/s each, before accounting for retries or alternate paths.
- If each AZ only has a 4 Gbit/s usable link, combined 8 Gbit/s capacity fails even with spare compute.

### 10.2. Network Dependencies

Confirm failover paths do not share a single bottleneck with the failed domain. Two AZs with independent compute that funnel through one shared NAT Gateway, firewall appliance, or single transit link still share a common failure domain.

## 11. Queues and Background Processing

Queues absorb bursts and decouple intake from processing speed. Yet after losing a worker zone, surviving consumers need enough throughput to drain backlogs within target deadlines.

Given:
- `B`: message backlog.
- `λ`: incoming message arrival rate.
- `μ`: total surviving processing rate.

Backlogs shrink only when `μ > λ`. Approximate drain time at steady rates:

```text
Drain time ≈ B / (μ - λ)
```

For example, with a 120,000-message backlog, 200 msg/s arrival rate, and surviving workers processing 500 msg/s:

```text
Drain time ≈ 120,000 / (500 - 200)
           = 400 seconds
           ≈ 6.7 minutes
```

If `μ <= λ`, the backlog never drains. Initially shallow queue depths can hide a developing capacity shortfall; monitor oldest message age and processing lag, not just raw message counts.

### 11.1. Consumer Failover

- Consumer groups/partitions must rebalance cleanly post-failure.
- Message visibility/lease timeouts must match processing times.
- Consumers must be idempotent since messages can be redelivered.
- DLQs must have adequate capacity and redrive runbooks.
- Batch sizes must avoid causing timeouts or inflating retry blast radius.
- Concurrency caps must protect downstream dependencies.

## 12. Dependency Capacity and Shared Bottlenecks

Application capacity is bounded by the weakest dependency along the request path.

For example, an API serves 10,000 RPS, yet its database caps at 2,000 query units/s and the payment provider caps at 300 requests/s. If every request calls both dependencies, adding compute cannot push throughput past those budgets.

### 12.1. Service-Chain Capacity

```text
End-to-end throughput <= min(
    compute capacity,
    database capacity,
    queue/worker capacity,
    network capacity,
    external provider quota
)
```

This is a simplified view; when services use caching, fan-out, or varied workload costs, convert using request mixes and unit costs.

### 12.2. Shared Dependencies as Hidden Failure Domains

These components can undermine multi-AZ redundancy if deployed as single instances, endpoints, or shared quotas:
- Identity providers or token validation services.
- DNS resolvers or service discovery.
- KMS/secret managers bound by quotas or regional endpoints.
- Shared caches, message brokers, or schema registries.
- NAT gateways, firewalls, proxies, or observability collectors.
- Control planes driving scheduling and provisioning.

Not every dependency must run inside the data plane, but define cached credentials, local fallbacks, retry policies, and quota ceilings during outages.

## 13. Calculating N+1 by Workload Mix

RPS is an inadequate unit when request costs vary widely. Convert to workload units:

```text
Total workload units/s =
    Σ (request_rate_i × cost_weight_i)

Example:
  Search: 500 req/s × 1 unit = 500
  Booking: 100 req/s × 5 units = 500
  Export: 10 req/s × 20 units = 200
  Total = 1,200 units/s
```

If an AZ fails, remaining capacity must absorb the corresponding workload units. Under overload, you can prioritize bookings and throttle exports; size failover capacity against that defined degraded policy rather than assuming every route has equal priority.

### 13.1. Priority Allocation

| Priority | Example | During Failover |
| --- | --- | --- |
| Critical | Authentication, booking commits, payment states | Preserve full capacity per SLO |
| Important | Search, booking reads, profiles | Maintain majority of service |
| Best effort | Large exports, analytics backfills | Queue, throttle, or pause |
| Background maintenance | Reindexing, cleanup, compaction | Defer if contending for capacity |

Enforce tiered admission control so background jobs never starve critical paths.

## 14. N+1 vs. N+2 and Multi-Failure Targets

N+1 typically survives one assumed failure domain. When requirements demand surviving two simultaneous domain losses, design for N+2 or evaluate explicit failure sets.

With M identical domains needing to survive X lost domains:

```text
(M - X) × C >= D × (1 + H)

C >= D × (1 + H) / (M - X)
```

For example, with 4 AZs required to survive 2 simultaneous AZ losses at 600 units/s demand and 20% headroom:

```text
C >= 600 × 1.20 / (4 - 2)
C >= 360 units/s per AZ

Total = 4 × 360 = 1,440 units/s
```

Losing two AZs leaves two AZs providing 720 units/s—covering 600 units/s demand plus 20% headroom. However, dual-AZ failures are often correlated rather than independent. Regional, network-hub, or IAM outages can knock out multiple AZs simultaneously; AZ-level N+2 does not guarantee surviving region-wide outages.

### 14.1. Fault Combinations and Correlated Failures

Catalog plausible overlapping failure pairs:
- AZ loss while a database replica is under maintenance.
- AZ loss mid-deployment rollout.
- Regional outage during high cross-region replication lag.
- Network partition costing a zone quorum while compute stays up.
- Shared identity/KMS quota exhaustion during a traffic surge.
- Cache failover triggering database overload.

Capacity planning must test degraded states hit by a second fault, not just single faults from a pristine baseline.

## 15. Scale-Out Delay and Warm Spare Strategies

Three common strategies:

- **Active-active:** every domain serves live traffic normally; when one drops, survivors absorb shifted load.
- **Active-standby/warm standby:** backup domain stays partially provisioned, needing scale-up or promotion on failure.
- **Cold standby:** resources are provisioned post-incident; lower idle cost, yet long RTO and provisioning risks if control planes or quotas are impaired.

| Strategy | Normal Cost | Failover Speed | Main Risk |
| --- | --- | --- | --- |
| Active-active with N+1 capacity | Higher due to reserved headroom | Fast if traffic shifts cleanly | Must size all surviving domains adequately |
| Warm standby | Medium | Depends on promotion/scale-up speed | Stale resources or insufficient quotas |
| Cold standby | Lower when idle | Slower | Provisioning may fail mid-incident |

### 15.1. Where Does Spare Capacity Actually Come From?

If every customer relies on the same regional instance-type quota, "we can autoscale" does not mean quota exists. Reserves may require:
- Pre-approved cloud quotas.
- Provider capacity reservations/commitments where available.
- Benchmarked fallback instance families.
- Multi-AZ node pools.
- Pre-staged container images and packages in-region.
- Warm connection pools and cached secrets.
- Rehearsed DNS and service discovery failover paths.

## 16. Storage Growth and Recovery Bandwidth

Losing a domain can force replicas to rebuild or copy data across the network. Size capacity for recovery traffic alongside user workloads.

For example, suppose a replica must sync 2 TB post-failover over an ideal 500 MB/s link:

```text
2 TB ≈ 2,000,000 MB (decimal)
Transfer time ≈ 2,000,000 / 500
             = 4,000 seconds
             ≈ 66.7 minutes
```

Real durations run longer due to log replay, checksums, contention, encryption, and live traffic. If recovery shares bandwidth with user traffic, restores drag out or degrade SLOs.

Consider:
- Placing snapshots/backups close to the recovering region/zone.
- Replication lag and log retention windows.
- Throughput for rebuilds and reindexing.
- Priority order for restoring datasets.
- Whether restoration can proceed per partition or tenant first.
- Throttling recovery traffic to protect live user SLOs.

## 17. Cost Model for Reserve Capacity

Reserve capacity raises everyday bills, while under-provisioning triggers downtime, queue backlogs, lost revenue, and SLA penalties.

A comparison model:

```text
Monthly resilience cost =
    baseline active capacity
  + reserved / warm capacity
  + replication and network transfer
  + backup / snapshot / storage
  + monitoring and failover tests
  + operational overhead

Expected incident cost =
    failure probability
  × (downtime impact + data loss impact + recovery cost + SLA credits)
```

Never apply one generic failure probability across every failure domain. Ground estimates in historical data, topology, and provider evidence, then run sensitivity analysis under higher-probability scenarios.

### 17.1. Cost per Unit of Resilience

Further comparison metrics:

```text
Incremental resilience cost =
    cost of N+1 design - cost of N-only design

Resilience premium per protected peak unit =
    incremental resilience cost / protected workload capacity
```

These are governance metrics for comparing options—never substitutes for evaluating downtime impact and data correctness.

### 17.2. Optimizing With Degraded Modes

If keeping full peak headroom for every workload is uneconomical, tier post-failure capacity:
- 100% capacity for critical transactions.
- 70% for interactive reads.
- 0–20% for exports/batches, pausing maintenance jobs.
- Controlled stale caches/replicas for display-only data.

Degraded modes must be approved product decisions with clear user messaging and zero violations of data invariants.

## 18. Autoscaling Does Not Replace Capacity Planning

Autoscaling adjusts resource counts from metrics; capacity planning ensures the underlying resource ceilings exist and can carry the load.

Autoscalers fail to save you when:
- Surviving zones lack quota or physical host capacity.
- Subnets run out of IP addresses.
- Max node/instance/pod bounds are set too low.
- Databases do not scale alongside compute.
- Schedulers cannot place pods due to volume topology or affinity rules.
- Metrics detect spikes late or miss queue age.
- Image pulls or initialization take too long.
- Regional control planes or service quotas degrade.
- Scale-out overloads downstream dependencies.

Test autoscaling during domain-loss scenarios, not only during traffic ramps in healthy environments.

## 19. Runbooks and Failover Coordination

A failover runbook should cover:

1. Confirm domain failure via multiple signals; avoid reacting to one flaky health check.
2. Check quorum/leadership and data ownership.
3. Stop or fence old workloads if split-brain risk exists.
4. Shift traffic and service discovery to surviving domains.
5. Activate warm capacity or scale in priority order.
6. Throttle or pause background workloads if needed.
7. Monitor CPU, DB, network, queue age, and SLOs while absorbing load.
8. Verify data consistency, duplicates, and pending transactions.
9. When the domain recovers, catch up replication, verify health, and rejoin safely.
10. Rebalance traffic back only once capacity and data state are verified healthy.

Failback is itself a high-load event. Never shift 100% of traffic back onto a newly recovered domain while replicas are still catching up or caches/nodes are cold.

## 20. Observability for Failover Capacity

Standard utilization dashboards are not enough; build views simulating each failure scenario.

| Category | Metrics | Meaning |
| --- | --- | --- |
| Demand | RPS/workload units, peaks, bursts | Actual vs design load |
| Compute | Usable CPU/memory, throttling, pending pods | Remaining compute capacity |
| Database | Query units, connections, IOPS, lag, failover time | Can the data tier hold the load? |
| Network | Throughput, packet loss, NAT/firewall utilization | Failover path capacity |
| Queues | Depth, oldest age, drain rate | Will backlogs clear within target? |
| Autoscaling | Detection/provision/ready times, quota errors | Is scale-out fast enough? |
| SLOs | p95/p99, errors, per-operation success rates | Are users still served properly? |
| Recovery | Replica catch-up, rebuild time, RTO/RPO | Can the system return to full state? |
| Cost | Idle headroom, reservations, inter-zone transfer | What does redundancy cost? |

Create a synthetic **remaining capacity ratio** metric:

```text
Remaining capacity ratio =
    usable capacity after failure / design demand

Ratio >= 1 is only a preliminary check before subtracting headroom and checking individual resources. Report ratios separately across CPU, DB, network, queues, and critical workloads.

### 20.1. Early Warning Alerts

- One AZ shows abnormally higher utilization than peers.
- Simulated single-AZ removal pushes remaining capacity ratio below target.
- Node pool or regional quotas approach limits.
- Database connections or replication lag near saturation.
- Oldest queue message age climbs sharply.
- Autoscaling ready time exceeds RTO budget.
- Network egress, NAT, or firewall approaches capacity.
- Warm standby drifts from baseline versions or configurations.

## 21. Testing and N+1 Game Days

A drill should prove **capacity**, **routing**, **data correctness**, and **recovery** together.

| Scenario | Execution | Pass Criteria |
| --- | --- | --- |
| Single node loss | Controlled drain/termination of a node | Surviving replicas absorb lost node's load |
| Single AZ loss | Isolate traffic or inject zone faults | SLOs and critical workloads hold targets |
| Peak + AZ loss | Drive design peak then isolate one AZ | Post-failure capacity stays within budget |
| Retry burst | Inject timeouts to trigger client retries | No retry storm forms |
| Cold cache | Flush/invalidate caches during failover test | Origin survives load or degraded policy engages |
| DB failover | Promote replica per runbook | Query/connection capacity and RPO hold |
| Queue backlog | Halt consumers in one zone then restore | Drain time stays inside recovery objective |
| Network bottleneck | Constrain bandwidth/NAT | No shared bottleneck breaks failover |
| Quota exhaustion | Cap instance/IP/subnet quotas | Runbook detects limit and fallback works |
| Correlated failure | Lose AZ mid-deploy or mid-backup | Targeted failure combination is survived |
| Failback | Rejoin recovered domain | Zero split-brain, zero overload |
| Degraded mode | Intentionally disable best-effort workloads | Critical paths hold SLOs |

### 21.1. What to Measure During Game Days

- Time to detect and confirm the failure.
- Time to shift traffic.
- Time until compute/data planes are ready.
- p95/p99 latency and error rates throughout the event.
- Peak queue backlog and drain duration.
- Database connection, query, and replication behavior.
- Lost, duplicate, or conflicting data.
- Actual remaining capacity vs projections.
- Failback and rebalancing duration.
- Incurred cost and operational incidents.

After each drill, update the capacity model with measured numbers. A test only passes if it meets pre-defined criteria—not merely because the service eventually recovered.

## 22. Reserve Capacity Calculation Process

1. **Select failure domain:** node, AZ, region, cell, or shared dependency.
2. **Define failure scenarios:** single-domain, multi-domain, or correlated failures.
3. **Build workload profiles:** typical, peak, burst, growth, and retry amplification.
4. **Define criticality/SLOs:** what stays at 100% vs what can degrade.
5. **Measure usable capacity:** compute, memory, databases, queues, networks, storage, and quotas.
6. **Compute remaining capacity:** remove failed domains from totals; never add mismatched resource types.
7. **Add headroom:** explicitly state whether relative to demand or total capacity.
8. **Calculate failover demand:** rerouted load, retries, cold caches, reconnects, and recovery traffic.
9. **Verify time-to-capacity:** static spares, warm standby, autoscaling, or cold provisioning.
10. **Audit shared dependencies:** IAM, DNS, KMS, NAT, brokers, and control planes.
11. **Set degraded/admission policies:** prioritize critical workloads and shield dependencies.
12. **Test, measure, iterate:** load + fault injection, game days, and model updates.

## 23. Practical Scenario: Booking API Across Three AZs

**Context:** A booking platform runs across three AZs. Design peak is 1,200 workload units/s, derived from search, booking, and payment flows. The goal is surviving one AZ loss while serving all critical workloads with 20% headroom. Each AZ benchmarks at 800 units/s of compute capacity; the database has 2,000 query units/s total, dropping to 1,400 usable query units/s when one AZ is lost. The payment provider caps at 250 calls/s. Cold caches can raise DB load by 25%. Client retries can add 10% ingress load without tight backoff.

### 23.1. Preliminary Compute Sizing

Accounting for 10% retry load:

```text
Failover demand = 1,200 × 1.10 = 1,320 units/s
With 20% headroom = 1,320 × 1.20 = 1,584 units/s
Two surviving AZs need 1,584 / 2 = 792 units/s each
```

At 800 units/s per AZ benchmark capacity, compute barely fits—leaving just 8 units/s of extra margin per AZ. That sits right on the edge; small benchmark errors or traffic skew will cause a miss.

### 23.2. Database Check

If normal demand generates 1,000 query units/s, and cold caches add 25% while retries add 10% independently:

```text
DB failover demand = 1,000 × 1.25 × 1.10
                   = 1,375 query units/s

With 20% headroom = 1,375 × 1.20
                  = 1,650 query units/s
```

Surviving DB capacity is only 1,400 query units/s, falling short of target. Adding compute will not solve this. Options include curbing cold-cache amplification, scaling DB capacity, using read replicas appropriately, or shedding best-effort workloads.

### 23.3. Payment Provider Check

If payments take 220 calls/s pre-failure, uncontrolled 10% retries push it to 242 calls/s; adding 20% headroom requires 290.4 calls/s, breaching the 250-call/s provider limit. Add queueing/rate caps, retry budgets, and pending/reconciliation states to avoid quota breaches or double charges.

### 23.4. Design Conclusion

Compute is tight while DB and payment provider are true bottlenecks. The plan should:
- Improve cache warm-up/replication and optimize read paths.
- Reserve dedicated budget for critical booking/payment paths.
- Defer exports/analytics during an AZ outage.
- Throttle payment queues below the provider rate cap.
- Raise DB capacity or cut query units per booking.
- Re-run peak + AZ-loss tests including cold caches and reconnect storms.

Never claim N+1 compliance merely because spare vCPUs exist; every critical dependency must pass simultaneously.

## 24. Sample ADR: Reserve Capacity for Single-AZ Failure

```text
ADR-104: Active-Active N+1 Capacity for Booking API Across Three AZs

Context:
- Design peak is 1,200 workload units/s.
- Must survive one AZ outage while preserving critical workloads.
- Database and payment provider have tighter limits than compute.

Options:
A. Run near normal demand and rely on autoscaling during failures.
B. Hold enough static capacity across three AZs for two survivors to carry peak + headroom.
C. Keep N+1 compute, degrade best-effort workloads, and throttle dependencies during failover.

Decision:
- Select Option C.
- Active-active compute benchmarked and spread across three AZs.
- Critical workloads retain full capacity; exports/maintenance face admission control.
- Database uses pooled/replica budgets with cold-cache testing.
- Payment workers rate-capped to provider quotas.
- Runbooks cover traffic shifting, queue draining, and pending-op reconciliation.

Trade-offs:
- Requires headroom and automation across every AZ.
- Background jobs slow down during failovers.
- DB/payment capacity must be tuned independently; spare compute cannot replace dependency capacity.

Verification:
- Peak + AZ loss test preserves critical SLOs.
- DB queries/connections and payment quotas stay within bounds.
- Queue age stays inside recovery objectives.
- Failback causes zero duplicates or split-brain.

Revisit Triggers:
- Peak workload or traffic mix shifts.
- Database or provider quotas change.
- SLO/RTO/RPO requirements change.
- Game days show remaining capacity below projections.
```

## 25. Common Mistakes

1. **Counting nodes instead of capacity:** spare nodes may lack sufficient throughput.
2. **Sizing for averages:** ignores peaks and post-failover bursts.
3. **Sizing only compute:** databases, networks, queues, and external providers bottleneck first.
4. **Treating autoscaling as instant backup:** provisioning and warm-up take time, and quotas may be exhausted.
5. **Summing capacity while ignoring placement:** shards, keys, and volumes may be pinned.
6. **Ignoring retry amplification:** load spikes right when capacity shrinks.
7. **Forgetting cold caches:** origin/databases get slammed by sudden read surges.
8. **Having quorum with underpowered survivors:** consistency holds while performance collapses.
9. **Overlooking subnet IPs and network appliances:** scale-out fails despite spare CPU.
10. **Assuming AZs are completely independent:** shared dependencies or regional failures still take down multiple zones.
11. **Writing N+1 without defining X:** unclear whether surviving one node, AZ, or resource unit.
12. **Skipping dedicated headroom for DB connections:** reconnect storms exhaust connections.
13. **Never testing failback:** returning nodes overload on replication/rebalancing.
14. **Giving all workloads equal priority:** batch jobs starve critical traffic.
15. **Trusting theoretical math alone:** skipping peak benchmarks and fault injection.
16. **Never testing quota exhaustion:** scale-out fails right when needed most.
17. **Ignoring recovery traffic:** replica rebuilds compete with user traffic.
18. **Lacking runbooks and owners:** paper capacity never activates cleanly during an incident.

## 26. Pre-Production Checklist

- [ ] Failure domains and target fault tolerance clearly defined.
- [ ] Workload profiles cover typical, design peak, burst, and growth.
- [ ] Criticality/SLOs and degraded modes approved by product.
- [ ] Capacity calculated in measurable workload/resource units.
- [ ] N+1/N+X explicitly specifies X and placement assumptions.
- [ ] Uses usable capacity, not merely nominal capacity.
- [ ] Headroom clearly defined relative to demand or total capacity.
- [ ] Failover demand includes reroutes, retries, reconnects, cold caches, and recovery traffic.
- [ ] Compute/nodes/IPs/quotas can scale in surviving domains.
- [ ] Database connections, queries, IOPS, and replication capacity hold post-failure.
- [ ] Storage durability, attach/restore, and recovery bandwidth meet requirements.
- [ ] Network, NAT, firewalls, and load balancers sustain shifted throughput.
- [ ] Queue consumers have explicit drain capacity and deadlines.
- [ ] Shared dependencies have fallbacks or independent capacity.
- [ ] Autoscaling ready time fits within RTO budgets or warm capacity covers the gap.
- [ ] Admission control, retry budgets, and priority policies configured.
- [ ] Monitoring tracks remaining capacity ratio per resource and failure scenario.
- [ ] Tested peak + AZ/region/cell loss, cold caches, quotas, and failback.
- [ ] Runbooks, owners, rollbacks, and game-day cadences established.
- [ ] Cost models include idle headroom, replication, networking, and operations.

---

**Key Takeaway:** N+1 redundancy only works when surviving infrastructure genuinely handles design peak, headroom, and failover-induced load. Size every resource and dependency individually while accounting for placement, autoscaling lag, quorums, queues, networking, and recovery traffic. Only benchmarks and failure-domain drills prove that paper redundancy translates into real-world SLOs.
