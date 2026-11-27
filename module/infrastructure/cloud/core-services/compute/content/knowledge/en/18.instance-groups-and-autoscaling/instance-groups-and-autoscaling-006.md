# Minimum, Maximum, and Desired Capacity Limits and Resource Headroom

A machine group can automatically increase instance counts when load climbs, yet autoscaling operates safely only when the group has clearly engineered capacity bounds and baselines. If minimum capacity is too low, the system lacks capacity while waiting to scale out. If maximum capacity is too high, the autoscaler can launch too many machines, exhaust quotas, or overload databases. If desired capacity does not reflect true demand, the machine group can run under- or over-provisioned even with scaling policies enabled.

The three values—**minimum capacity**, **maximum capacity**, and **desired capacity**—form the control envelope for a machine group. They must be calculated alongside baseline load, peak load, instance startup times, fault tolerance, downstream dependency limits, and budgets. This lesson explains what each value means, how to estimate capacity, how to provision headroom, and how to validate configurations across instance groups, VM scale sets, and Kubernetes.

## 1. What is capacity?

Capacity is the processing capability a system can deliver over a period of time while still meeting latency, error, and availability targets.

Capacity is not simply a VM count. A group of 10 VMs can have very different effective capacities depending on:

- Machine type, vCPU count, and CPU generation.
- RAM size and workload memory limits.
- Storage IOPS, throughput, and latency.
- Network bandwidth, packet rate, and connection limits.
- Software, runtime, worker configuration, and thread pools.
- Database, message broker, and downstream API limits.
- Proportion of healthy instances and distribution across availability zones.
- Bootstrap, warm-up, and load balancer registration times.

A machine group delivers useful capacity only once instances are ready to serve. Instances that are provisioning, booting, warming up, or unhealthy may count toward certain management states without yet contributing real serving capacity.

### Capacity by instance count vs. resource units

Two common representations exist:

- **Instance count:** number of VMs or nodes.
- **Capacity unit:** weighted capacity assigned per instance, based on vCPU, memory, or custom system weights.

In groups mixing multiple instance types, 5 small machines are not equivalent to 5 large machines. Some services support weighted capacity to convert machine types into capacity units, allowing desired capacity to be expressed in capacity units rather than raw instance counts.

Read your autoscaling service's documentation carefully on how it computes desired capacity, particularly when using mixed instance types, instance weights, or heterogeneous node pools.

## 2. Distinguishing min, max, and desired capacity

The three values serve distinct roles:

| Value | Meaning | Operational role |
|---|---|---|
| Minimum capacity | Lowest capacity level the group is allowed to maintain | Preserves baseline capacity and prevents over-aggressive scale-in |
| Maximum capacity | Highest capacity level the group is allowed to provision | Caps cost, quota usage, and resource consumption |
| Desired capacity | Capacity level the group is currently instructed to reach | Current target set by an operator or autoscaler |

For example, a VM group has:

- Minimum = 3 instances.
- Desired = 6 instances.
- Maximum = 12 instances.

The group may fluctuate between 3 and 12 instances and is currently targeting 6 instances. If load rises, policies can raise desired to 8 or 10. When load drops, policies can lower desired, though never below minimum.

### Desired does not equal healthy

Distinguish additional lifecycle states:

- **Desired:** number of instances or capacity units the system wants.
- **Current/actual:** number of instances already created or existing.
- **Pending:** instances currently provisioning or booting.
- **In service:** instances that passed required management steps and entered the serving pool.
- **Healthy:** instances passing policy health checks.
- **Draining/terminating:** instances stopping new work and preparing for deletion.
- **Standby/warm:** instances kept ready but not serving normal traffic.

For example, desired may be 8 while only 6 instances are healthy and 2 are booting. The system does not yet have 8 instances of serving capacity. Dashboards showing only desired capacity can mislead operators into overestimating active capacity.

### Min and max constraints

Typically, desired must stay between min and max. Setting desired below min may cause the service to clamp it up to min or reject the request. Setting desired above max may reject the request or cap it according to service rules.

Exact field names and behaviors depend on the platform. Verify resulting states after updates rather than assuming the API applied your target as written.

## 3. Minimum capacity: preserving baseline capability

Minimum capacity is the lower bound of the machine group. When load drops, the autoscaler cannot shrink the group below this floor.

### Why is minimum capacity needed?

Minimum capacity is typically chosen to:

- Sustain baseline load serving capability.
- Keep enough replicas for high availability.
- Retain spare capacity if one instance fails.
- Avoid cold starts or lengthy bootstrap delays.
- Keep caches warm and connection pools initialized.
- Maintain enough nodes for essential background workloads or daemons.
- Prevent scaling from zero when latency requirements forbid it.

### Minimum does not guarantee all instances are healthy

If minimum is 3 yet 2 instances become unhealthy, the group still lacks capacity even though it cannot scale in further. Combine health replacement, alerts, quotas, and healthy instance checks.

Minimum is a scale floor, not a guarantee of always-ready machines. Availability still depends on replacing failed instances and underlying zone capacity.

### Choosing minimum based on baseline load

One approach:

1. Measure baseline load during off-peak and normal hours.
2. Measure per-instance capacity while meeting SLOs.
3. Calculate instances needed for baseline load.
4. Add reserve capacity for availability requirements.
5. Verify minimum suffices for mandatory workloads and operational tasks.

If workload traffic swings sharply by hour, set minimum to a safe baseline; scheduled scaling or target tracking will raise desired ahead of peak periods.

### Minimum capacity and scale-to-zero

Some batch or event-driven workloads allow a minimum of 0 to save costs. This works when durable queues exist, immediate responses are not required, and startup delays are acceptable.

For interactive APIs or low-latency services, scaling to zero introduces cold starts and high latency. Consider warm pools, provisioned capacity, or a minimum greater than 0.

## 4. Maximum capacity: bounding growth

Maximum capacity is the upper ceiling the autoscaler cannot cross. It protects budgets and downstream dependencies from unbounded growth.

### Reasons to enforce a maximum

- Budget limits.
- Quotas on vCPUs, instances, GPUs, or IP addresses.
- Real capacity availability in the region/availability zone.
- Database connection limits.
- API rate limits or consumer caps.
- Software licensing caps.
- Bandwidth, NAT, storage, or load balancer limits.
- Blast-radius containment during bugs or scaling loops.

### Maximum set too low

If max is lower than peak demand requires, the autoscaler hits the ceiling while the system remains overloaded. Symptoms:

- Desired stays pinned at maximum for extended periods.
- Queues and latency keep climbing.
- CPU, memory, or connection pools remain saturated.
- Requests get rejected despite active scaling policies.

When this happens, re-evaluate max, quotas, regional capacity, and dependencies. Never raise max blindly if databases or networks cannot handle extra load.

### Maximum set too high

A large maximum does not automatically yield useful capacity. It can:

- Spike costs when scaling signals misfire.
- Exhaust database connection limits.
- Exhaust subnet IPs or NAT ports.
- Overload storage and message brokers.
- Spin up excessive instances during retry storms or traffic anomalies.
- Prolong rollouts and increase monitoring overhead.

Maximum capacity must be validated via capacity tests and dependency budgets, not merely set to the highest limit the cloud provider permits.

### Maximum capacity and quotas

Before raising maximum capacity, check quotas at the exact scope: account/project/subscription, region, zone, and resource type. Total vCPU quotas may be shared across multiple machine groups. Quotas for GPUs, public IPs, disks, or network interfaces may enforce separate ceilings.

Leave quota headroom for:
- Instance replacement on machine failures.
- Deployment surges or rolling updates.
- Disaster recovery.
- Other machine groups in the same account/project.
- Operational tasks and staging environments if sharing quotas.

## 5. Desired capacity: the current target

Desired capacity is the target the machine group aims to maintain right now. It can be modified manually or updated by autoscaling policies.

### What modifies desired capacity?

- Operators setting desired during deployments or maintenance.
- Target tracking adjusting desired to hit a target metric.
- Step scaling adding/removing desired capacity by alarm tiers.
- Scheduled scaling setting desired or bounds at scheduled times.
- Orchestrators adjusting replica counts per policy.
- Deployment controllers temporarily requesting extra capacity during rollouts.

Avoid letting multiple independent controllers overwrite desired without coordination rules. For instance, a cron script setting a fixed desired count every minute will continually fight the autoscaler.

### Desired can differ from current temporarily

When desired increases, the platform must provision machines, boot the OS, run bootstrap, register agents, and wait for health checks. When desired decreases, the system must drain connections, finish tasks, and terminate instances.

Consequently:

\[
Desired\ Capacity \neq Healthy\ Capacity
\]

during transitions or failures. Measure convergence time from when desired changes until healthy capacity meets the target.

### Manual desired changes and autoscaling

If an autoscaler actively manages the group, manual desired edits may be short-lived. Policies may adjust it right back based on metrics.

Before making manual edits, check:
- Which policies control the group.
- Whether a scheduled action is about to fire.
- Whether cooldown or stabilization windows are active.
- Whether a deployment or lifecycle hook is in progress.
- Whether another controller will overwrite desired.

## 6. Calculating capacity from load and SLOs

Instance counts should be derived from how much load each instance handles while meeting SLOs, rather than applying a generic CPU percentage across every application.

### Measuring single-instance capacity

Use load tests or production telemetry to establish safe per-instance throughput:

- Ramp load gradually until latency or error rates approach the SLO.
- Record throughput at that point.
- Record CPU, memory, disk, network, and dependency metrics.
- Repeat on representative configurations.
- Choose a capacity level that leaves headroom for variance.

Let **Q_safe** denote the throughput per instance sustainable under tested conditions while meeting SLOs.

Required instance count can be estimated as:

\[
N_{required} = \left\lceil \frac{D_{peak}}{Q_{safe}} \right\rceil
\]

Where:
- \(D_{peak}\) is projected peak demand.
- \(Q_{safe}\) is safe throughput per instance.

If you only have near-saturation throughput \(Q_{sat}\), apply a target utilization factor \(U_{target}\):

\[
Q_{safe} = Q_{sat} \times U_{target}
\]

Do not apply both headroom reductions simultaneously if `Q_safe` was already measured at a safe operating margin.

### Sizing example

An API has a projected peak load of 1,800 requests/second. Load tests show one VM handles 500 requests/second at saturation, and the team chooses a 65% utilization target to preserve headroom.

\[
Q_{safe} = 500 \times 0.65 = 325
\]

\[
N_{required} = \lceil 1800 / 325 \rceil = 6
\]

The group needs at least 6 healthy instances to serve peak load under tested conditions. This is a baseline sizing figure; add fault-tolerance capacity according to availability requirements.

### Do not size by CPU alone

An instance may have free CPU yet run out of database connections, memory, network bandwidth, or IOPS. Workload capacity is bounded by whichever component saturates first.

Useful capacity can be conceptualized as the minimum across domains:

\[
C_{effective} = \min(C_{CPU}, C_{memory}, C_{storage}, C_{network}, C_{dependency})
\]

This is a mental model, not a direct measurement formula. Each domain requires its own units and measurements.

## 7. Headroom and resource reserves

Headroom is spare capacity above current or projected demand. It helps the system absorb bursts, failures, rollouts, and autoscaler provisioning lag.

### Operational headroom

If a workload uses 60% of provisioned capacity, simple proportional headroom is 40%. Yet CPU utilization alone does not reflect total headroom. Check RAM, storage, networking, queues, and dependencies.

Examples:
- 30% CPU free while only 2% memory remains: the system lacks memory headroom.
- VM has free CPU/RAM while the DB pool has zero free connections: requests still queue.
- Disk has free space while IOPS hit their ceiling: workload still slows down.
- Network throughput is low while NAT ports are exhausted: new outbound connections still fail.

### Headroom for autoscaling lag

Autoscaling does not add capacity instantaneously. Convergence time includes:

1. Metrics detecting rising load.
2. Policies evaluating and updating desired capacity.
3. Scheduler or cloud provider allocating capacity.
4. Instances launching and booting.
5. Bootstrap configuring agents and the application.
6. Cache/runtime warm-up.
7. Health checks passing and load balancer admitting traffic.

During this window, existing capacity must carry the load. Minimum and warm capacity should suffice to absorb load while scaling out.

### Headroom for rolling deployments

Rolling updates may temporarily create extra instances to replace old machines. Check:
- Max surge or batch size.
- Max unavailable.
- Desired/current counts during rollouts.
- Remaining quotas and zone capacity.
- Temporary spikes in database connections and network usage.
- Drain and health check durations.

If maximum equals normal desired capacity, deployments may be unable to launch replacement machines before deleting old ones. Some platforms enforce distinct rollout rules; budget surge into quotas and maximum limits accordingly.

## 8. Planning reserves for instance or availability zone failures

### Instance-level reserve

If a group must maintain 6 healthy instances whenever any single instance fails, you may need capacity above 6 for replacements or a standby reserve. Reserve size depends on replacement time and load levels.

Example:
- Serving capacity needed: 6 instances.
- Any single instance may fail at any time.
- Replacement takes 4 minutes to boot and warm up.
- During those 4 minutes, remaining instances must still meet SLOs.

Adding one reserve instance or equivalent headroom may be necessary for fault tolerance. No single reserve ratio fits every system.

### Availability zone reserve

Distributing instances across multiple AZs reduces single-zone outage risk. However, total instances must suffice for remaining zones to carry the load after losing one AZ.

To retain the equivalent of 6 instances after losing one of 3 AZs with even distribution:

\[
N_{total} \times \frac{2}{3} \geq 6
\]

\[
N_{total} \geq 9
\]

This assumes 3 AZs have equivalent capacity and uniform distribution. If AZs are uneven or per-zone quotas differ, calculate based on actual per-zone capacity.

### Capacity is more than instance count

During an AZ failure, verify:
- Remaining subnets/IPs can accommodate replacement or existing instances.
- vCPU quotas suffice in surviving zones.
- Target instance families have available capacity or reservations.
- Load balancer health checks and cross-zone routing work properly.
- Storage can attach or replicate in surviving zones.
- Databases and caches retain sufficient capacity after failover.

### On-demand, reserved, and spot

- **On-demand:** flexible on demand, yet still subject to regional capacity and quotas.
- **Reserved/committed capacity:** can reduce costs or reserve partial capacity depending on service terms.
- **Spot/preemptible:** low cost, yet revocable at any time; never rely on it as sole capacity for critical workloads.
- **Capacity reservations:** can explicitly reserve compute capacity within a scope depending on provider.

Groups using spot instances should maintain reliable baseline capacity and diversify across instance types and zones to reduce correlated interruptions.

## 9. Reserving capacity for dependencies and connection pools

Scaling out adds instances while also increasing load on downstream services.

### Database connections

If each instance opens up to 20 connections and the group has 12 instances, potential connections reach:

\[
12 \times 20 = 240
\]

This excludes admin, migration, monitoring, and other workload connections. Cap total connections at the system level.

When calculating maximum capacity, check:
- Pool size per instance.
- Maximum instance count.
- Number of pools per process.
- Connections reserved for background jobs.
- Database and connection proxy limits.
- Query durations and actual concurrency.

### APIs and message brokers

If each instance makes 50 concurrent calls to an external API, 12 instances generate up to 600 in-flight requests. Check quotas, rate limits, and concurrency caps on that external service.

For message brokers, consumer scaling may be bounded by partitions, throughput, and ordering constraints. Adding instances will not boost throughput if partition counts stay fixed.

### Storage and networking

Maximum instance counts can amplify:
- Aggregate IOPS and storage throughput.
- Network egress and NAT connection counts.
- File share client counts.
- Attached volume counts.
- IP addresses and network interfaces.

Capacity plans must budget for these dependencies before raising max.

## 10. Warm capacity, warm pools, and startup times

Warm capacity is pre-staged capacity able to take load faster. It can include live instances running with headroom, booted standby instances, or platform-managed warm pools.

### Warm pools

Warm pools keep partially or fully initialized instances ready to shorten the delay from scaling trigger to ready state. Readiness levels vary:

- Stopped: image and disks exist, but the machine is powered off.
- Running/ready: OS is booted; application warm-up may still be needed.
- In-service: actively serving normal traffic.

Exact state names and billing depend on the service. Clarify whether warm pool instances count against desired capacity, maximum limits, or quotas.

### When should you maintain warm capacity?

- Cold starts or bootstraps take too long.
- Workloads experience rapid traffic spikes.
- Latency SLOs are strict.
- Images must load large packages.
- Applications need warm caches or JIT compilation.
- Regions face tight compute capacity.

### Warm capacity has costs

Running or standby instances still incur compute, disk, and IP costs. Weigh warm capacity costs against SLO violation penalties, queue backlogs, and recovery delays.

Avoid oversized warm pools when baseline load is low and cold starts are tolerable.

## 11. Applying to instance groups and VM scale sets

Cloud providers use different names for broadly similar models.

| Platform | Service | Common limits |
|---|---|---|
| AWS | EC2 Auto Scaling Group | Min size, desired capacity, max size; supports weighted capacity and warm pools |
| Microsoft Azure | Virtual Machine Scale Sets | Instance count/capacity; autoscale minimum/default/maximum per profile |
| Google Cloud | Managed Instance Group | Minimum/maximum or target size depending on autoscaler mode and MIG type |

Exact configurations depend on region, group type, autoscaling mode, and API version.

### Configuration workflow

1. Select instance types and capacity units.
2. Set minimum based on baseline load and availability targets.
3. Set desired to match current load or initial baseline.
4. Set maximum based on peak forecasts, quotas, and dependency budgets.
5. Configure zone distribution.
6. Set up health checks and automatic replacement.
7. Define lifecycle hooks, draining, and warm-up.
8. Verify rolling deployment surge limits.
9. Check quotas and capacity reservations.
10. Observe desired, current, pending, and healthy capacity after applying changes.

### Weighted capacity

If a group uses multiple VM sizes, weights map each instance to capacity units. For example, a large machine has weight 4 and a small machine has weight 1. A desired capacity of 12 units can be met by various combinations of instances.

Verify:
- Do weights accurately reflect real throughput?
- Do CPU/RAM ratios suit the workload?
- Are alternate instance types compatible with images and drivers?
- Does the autoscaler apply capacity units consistently across desired, max, and metrics?

Do not assign weights solely by vCPU count if the workload is constrained by RAM, storage, or networking.

## 12. Applying in Kubernetes

Kubernetes involves multiple capacity layers:

- **Pod replicas:** number of application instances.
- **HPA:** adjusts replica counts between `minReplicas` and `maxReplicas`.
- **VPA:** adjusts CPU/memory requests according to policy.
- **Node pools/managed node groups:** bound node counts.
- **Cluster autoscaler:** adds or removes nodes when Pods cannot schedule or nodes become underutilized.

### HPA min and max

HPA example:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

This example requires at least 3 Pods, allows up to 20 Pods, and targets 65% CPU utilization relative to requests. Ensure containers define accurate CPU requests; misconfigured requests distort utilization percentages relative to real load.

HPA changes replica counts, while a node autoscaler must supply nodes to host those Pods. If `maxReplicas` is high while node pool max is low, Pods remain `Pending`.

### Node pool min/max

Node pools enforce their own bounds. Total cluster capacity must account for:
- Node count min/max.
- Allocatable CPU/RAM after subtracting system reservations.
- Pod density and IP address limits.
- DaemonSet resource overhead.
- Zone topology and storage locality.
- Quotas and availability of underlying VM instance types.

### Desired replicas vs. healthy Pods

A Deployment may desire 10 replicas while only 7 Pods are `Ready`. Inspect `desired`/`current`/`ready`/`available`, `Pending` Pods, `CrashLoopBackOff`, and node capacity.

Replica counts do not equal serving capacity if Pods are unready or CPU-throttled. Monitor request latency, queues, CPU throttling, and dependency pools.

## 13. Serverless and concurrency limits

Serverless platforms typically enforce equivalents to min/max/desired via concurrency caps, reserved capacity, or provisioned capacity.

Key concepts include:
- Reserved concurrency: dedicated or capped maximum concurrency per configuration.
- Provisioned concurrency: pre-warmed execution environments to minimize cold starts on supported platforms.
- Maximum instances/concurrency: limits on concurrent execution environments or requests.
- Queue backlog: pending work waiting for function execution.

If a function scales rapidly, downstream systems can overload. Enforce concurrency caps on functions and protect databases/APIs using poolers, semaphores, queues, or rate limits.

Do not assume every serverless platform shares identical min/max semantics with instance groups. Verify your specific service and runtime documentation.

## 14. Costs and capacity budgets

Minimum, desired, and maximum define distinct cost profiles.

- Minimum sets your baseline floor cost.
- Desired reflects current active run-rate cost.
- Maximum is the potential upper cost ceiling, not the steady-state cost.
- Warm pools can incur costs even when serving zero traffic.
- Deployment surges temporarily raise costs.
- Cross-zone traffic, disks, IPs, NAT gateways, and licenses can scale alongside instance counts.

### Estimating costs

A simple cost model:

\[
Cost \approx \sum_{i=1}^{n} InstanceHours_i \times HourlyRate_i
+ Storage + Network + OtherServices
\]

For mixed instance types, calculate runtime hours per type separately. Add warm pool, snapshot, logging, load balancer, and dependency costs.

### Optimizing minimum while preserving SLOs

You can lower minimum capacity when:
- Baseline load is low and predictable.
- Scale-out completes fast enough.
- Queues can absorb bursts.
- The workload tolerates cold starts.
- Scale-to-zero or a small warm pool is viable.

Avoid lowering minimum when:
- The service enforces strict latency SLOs.
- A single AZ or instance failure causes capacity shortages.
- Bootstrap takes a long time.
- Workloads hold long-lived connections or large caches.
- Dependencies cannot survive startup spikes when many instances launch together.

### Budget guardrails

Use budget alerts or policies to catch unexpected spend spikes. However, never automatically slash desired capacity below safe operational levels solely on a budget alert if doing so causes an outage. Maintain separate policies for overload handling, cost governance, and SLO protection.

## 15. Workflow for calculating min, desired, and max

A practical sizing workflow:

1. **Define SLOs:** target throughput, latency, error rates, and availability.
2. **Measure per-instance capacity:** load-test using near-production configurations and dependencies.
3. **Forecast demand:** baseline, peak, bursts, seasonality, and growth rates.
4. **Compute required capacity:** use safe throughput per instance, not just average CPU.
5. **Set minimum:** enough for baseline load, warm-up, and availability targets.
6. **Set desired:** match current load or initial baseline.
7. **Set maximum:** enough for peaks and deployment surges without breaching quotas or dependency budgets.
8. **Factor AZ failures:** verify surviving capacity after losing one zone.
9. **Factor dependencies:** database connections, API quotas, storage, IPs, and networking.
10. **Account for scale lag:** detection, provisioning, bootstrap, and readiness times.
11. **Estimate costs:** calculate spend at min, desired, max, and warm pool levels.
12. **Validate with tests:** run load, stress, spike, and failover tests.
13. **Roll out via canary:** apply to a small group before expanding.
14. **Review periodically:** adjust for traffic growth, image changes, and SLO updates.

### Illustrative configuration example

An API group needs 3 instances for baseline load and 6 instances for peak load per capacity tests. The team wants to survive one instance failure during normal hours and scale up to 10 instances for bursts.

A starting configuration:

| Attribute | Illustrative value | Rationale |
|---|---:|---|
| Minimum | 4 | 3 instances for baseline load plus 1 reserve instance |
| Desired | 4 | Starts at a safe baseline |
| Maximum | 10 | Covers peak and partial bursts within quotas/dependencies |
| Warm capacity | 1 | Shortens reaction time when scaling is triggered |
| AZs | 3 | Distributes risk across zones |

This configuration is only a starting point. If the requirement is keeping 6 serving instances active after losing an entire AZ, recalculate total capacity according to zone distribution rather than relying on a minimum of 4.

## 16. Monitoring capacity and alerting

Track these metrics:

| Category | Metrics | Question |
|---|---|---|
| Group | Min, desired, max | Where is the group bounded? |
| Instances | Current, pending, in-service, healthy | Are enough machines actually ready? |
| Scaling | Scale events, cooldowns, warm-up duration | Is the autoscaler reacting properly? |
| Workload | Request rate, queues, p95/p99, errors | Does current capacity meet SLOs? |
| Compute | CPU, memory, throttling | Is the bottleneck inside machine resources? |
| Dependencies | DB connections, API rates, broker lag | Is scale-out overloading downstream systems? |
| Quotas | vCPUs, instances, IPs, GPUs, storage | Can more machines be provisioned when needed? |
| Cost | Instance hours, warm pools, network, disks | How much budget is capacity consuming? |

### Recommended alerts

- Desired stays pinned at maximum for an extended period.
- Healthy capacity drops below desired capacity.
- Instances stay pending for too long.
- Scale events fail due to quotas or capacity shortages.
- CPU/memory or queues breach SLOs while the group sits at max.
- Minimum capacity proves insufficient after an AZ or instance failure.
- Database connections or API quotas approach limits.
- Warm pools run empty or bootstrap duration climbs.
- Costs rise disproportionately relative to workload traffic.

Do not alert merely because desired differs from current for a few seconds. Account for normal convergence and startup durations.

## 17. Common issues and remediation

| Symptom | Possible causes | Remediation |
|---|---|---|
| Desired rises yet healthy stays flat | Quotas, zone capacity, bad image, or bootstrap failure | Check scaling activities, provisioning events, quotas, and bootstrap logs |
| Desired pinned at max | High load, target set too low, or max set too low | Review SLOs, capacity tests, dependencies, and budgets before raising max |
| Scale-in causes request errors | Minimum too low or incomplete draining | Raise min, configure lifecycle/draining hooks, and check termination policies |
| Added instances yield no throughput gain | DB, broker, storage, or APIs already saturated | Cap concurrency, optimize dependencies, or scale downstream capacity |
| Pods Pending despite HPA scaling replicas | Node pool max, quotas, or oversized resource requests | Inspect scheduler events, allocatable capacity, and node autoscaler |
| Sluggish autoscaling response | Slow bootstrap, image pulls, warm-up, or metric lag | Use warm capacity, optimize images, and switch to leading signals |
| Sudden cost spikes | Scaling loops, wrong metrics, retry storms, or high max | Inspect policies, cooldowns, alarms, and dependency errors |
| Losing an AZ breaks SLOs | Insufficient capacity distributed in surviving zones | Recalculate N-1 zone capacity and reserve quotas |
| Scale-out causes database timeouts | Total connections exceed DB limits | Budget system-wide pools, add proxies/poolers, and cap concurrency |

### Investigation workflow

1. Compare min, desired, max, and current capacity.
2. Check counts of healthy, pending, and draining instances.
3. Inspect recent scaling activities or cluster events.
4. Verify quotas and regional/zonal capacity.
5. Read bootstrap, health check, and load balancer target logs.
6. Correlate request rates, queues, latency, and error rates.
7. Check databases, brokers, networking, and storage.
8. Identify the true bottleneck before raising max or desired.
9. Test changes in staging/canary.
10. Monitor SLOs and costs after applying changes.

## 18. Checklist before promoting capacity bounds to production

- [ ] Distinguished minimum, maximum, and desired capacity.
- [ ] Distinguished desired from current, healthy, and available capacity.
- [ ] Clarified whether capacity uses instance counts or weighted units.
- [ ] Measured safe per-instance throughput via load testing.
- [ ] Sized minimum for baseline load and availability requirements.
- [ ] Sized maximum for peak load, bursts, and deployment surges.
- [ ] Verified quotas, reservations, and per-zone capacity.
- [ ] Accounted for N-1 instance or AZ failure requirements.
- [ ] Budgeted database connections and dependency limits system-wide.
- [ ] Sized headroom for autoscaling lag and warm-up.
- [ ] Configured health checks, automatic replacement, and graceful draining.
- [ ] Evaluated warm pools or provisioned capacity where needed.
- [ ] Checked rolling deployment surges and lifecycle hooks.
- [ ] Monitored desired, current, healthy, and pending counts.
- [ ] Configured alerts when hitting max or when healthy capacity falls short.
- [ ] Estimated costs at min, desired, max, and warm pool levels.
- [ ] Tested load, spikes, failover, and scale-in.
- [ ] Prepared rollback plans and scheduled periodic capacity reviews.

## Conclusion

Minimum capacity preserves baseline readiness, maximum capacity caps scale, and desired capacity expresses the current target. These three bounds are meaningful only when derived from safe throughput, SLOs, scale-out lag, availability zones, quotas, and dependency limits. Real serving capacity must count healthy instances rather than merely requested machines. Leaving headroom across CPU, RAM, storage, networking, database connections, and bootstrap times helps systems survive bursts and outages. By monitoring desired/current/healthy counts, scaling activity, queues, SLOs, and costs, operations teams can set sound min/max bounds, maintain headroom, and prevent autoscaling from overloading the wider system.
