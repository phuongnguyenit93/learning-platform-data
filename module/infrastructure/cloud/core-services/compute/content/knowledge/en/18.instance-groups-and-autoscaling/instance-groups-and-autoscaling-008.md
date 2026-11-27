# Distributing Capacity Across Multiple Zones and Machine Types

An instance group or autoscaling group typically runs multiple virtual machines to serve load, survive failures, and replace machines during maintenance. When a group spans multiple availability zones (AZs) and uses multiple instance types, the problem is no longer as simple as keeping a fixed machine count. The system must ensure every zone has sufficient capacity, select suitable alternate machine types if one type runs out, and keep total cost and performance within targets.

Good capacity distribution coordinates three decisions: **how much capacity to place in each zone**, **which machine types are permitted**, and **how much reserve capacity to maintain if a zone or machine type fails**. These decisions interact. A group might have enough total vCPUs yet lack RAM in one zone, or meet its instance count yet lack processing power when smaller machines substitute for larger ones.

## 1. What is capacity in an instance group?

Capacity is the compute capability a machine group can supply to a workload. In a group using a single instance type, operators commonly express capacity as machine count. When a group mixes multiple machine types, instance count no longer reflects true capability accurately.

For example, two 2-vCPU machines and one 8-vCPU machine both count differently as instances yet deliver very different CPU power. RAM, network throughput, IOPS, GPUs, and packet-per-second (PPS) limits can also differ. Pick a capacity unit suited to the workload.

Common representations include:

- **Instance count:** number of running VMs. Fits when all machines share one type or equivalent capability.
- **vCPU capacity:** total allocated vCPUs. Useful for CPU-bound workloads, though it does not capture performance differences across CPU generations.
- **Memory capacity:** total RAM. Important for memory-bound workloads, yet total RAM does not guarantee a task can run on any node if each individual node needs a minimum amount of RAM.
- **Weighted capacity units:** each machine type is assigned a weight representing relative capability. Larger instances contribute more units than smaller ones.
- **Application capacity:** measured capability such as requests/second, worker concurrency, jobs/hour, or concurrent sessions. This is usually the metric closest to service goals when backed by reliable benchmarks.

No single metric represents every workload. If an application is memory-constrained, weighting solely by vCPU can cause the group to substitute configurations lacking sufficient RAM. If an application requires GPUs or local NVMe, a machine without that resource cannot substitute merely because total vCPUs match.

## 2. Distinguishing regions, availability zones, and fault domains

A region is a geographic area composed of one or more zones. An availability zone is an infrastructure domain engineered to reduce shared failure correlation with other zones in the same region. Exact naming, isolation boundaries, and zone mapping vary across cloud providers.

A machine group spanning multiple zones can continue serving when one zone is disrupted, provided the workload and dependencies are also designed for fault tolerance. Spreading machines across zones reduces concentration risk, though by itself it does not guarantee high availability.

| Scope | Role in design |
|---|---|
| Region | Defines deployment geography, geographic latency, residency, and service scope |
| Availability zone | Spreads machines across failure domains within a region |
| Subnet/zone network | Supplies IP addresses, routes, and network policies for machines in the zone |
| Instance type | Defines CPU, RAM, networking, storage, and accelerator specs per machine |
| Instance group | Manages machine count/capacity, replacement, and group scaling |

Some services offer regional groups allowing multiple zones; others require per-zone groups or regional managed groups with distinct distribution behaviors. Before designing, verify resource scopes, limits, and terminology for your provider.

## 3. Distributing evenly across zones

A common strategy is spreading capacity roughly evenly across active zones. If a group has 300 capacity units across three zones, the normal target might be about 100 units per zone.

Benefits of even distribution:

- Reduces reliance on any single zone.
- Provides balanced capacity for load balancers distributing requests.
- Simplifies comparing utilization and spotting skewed zones.
- Enables continued serving during a zone outage if remaining capacity suffices.

However, balancing instance counts does not guarantee balanced capacity when machines differ in size. If Zone A holds two 8-vCPU machines and Zone B holds two 4-vCPU machines, machine counts match while CPU power does not. For mixed instance groups, monitor instance counts alongside capacity units and actual hardware resources.

Some services automatically rebalance machine counts across zones after group changes; others only distribute best-effort or require enabling balance options. Capacity shortages in one zone can also leave the group temporarily skewed. Never treat "zone balanced" as a hard guarantee that every zone holds identical counts at every instant.

## 4. Calculating capacity needed when losing a zone

In multi-zone designs, calculate what happens when one zone becomes unavailable. If total peak demand is `D` and the group distributes evenly across `N` zones, each zone normally carries roughly `D/N`. When one zone is lost, the surviving zones must absorb all of `D`.

If redistributed evenly across the `N-1` surviving zones, each zone needs roughly:

\[
C_{zone,failover} = \frac{D}{N-1}
\]

Relative to normal load `D/N`, the load multiplier on each surviving zone is:

\[
F = \frac{N}{N-1}
\]

With three zones, this factor is `3/2 = 1.5`. That means each surviving zone must handle 50% higher load than normal under even distribution.

For example, a system requires 300 capacity units at peak across three zones:

| State | Zone A | Zone B | Zone C | Total capacity needed |
|---|---:|---:|---:|---:|
| Normal | 100 | 100 | 100 | 300 |
| Zone A lost | 0 | 150 | 150 | 300 |
| Zone B lost | 150 | 0 | 150 | 300 |
| Zone C lost | 150 | 150 | 0 | 300 |

In this example, each zone must be able to supply 150 units so any two surviving zones can carry peak load. Achieve this by holding spare capacity, enabling fast autoscaling with adequate quotas/capacity pools, or combining both.

Post-failure autoscaling helps only if replacement capacity can be provisioned in time. During regional capacity crunches or quota exhaustion, scale-out may fail to finish. For critical workloads, keep ready headroom in surviving zones or use appropriate capacity reservations. Size headroom around machine boot times, application bootstrap, warm-up, and traffic shift delays.

## 5. Distributing by demand, not just fixed ratios

Even distribution is a good starting point, yet some workloads require different placement:

- Workloads with large local data or caches may prefer placement close to data sources.
- Latency-sensitive workloads may need placement aligned with users or dependencies.
- Batch workloads may favor whichever zone has available capacity and lower cost.
- Workloads needing specialized licenses or hardware may be restricted to specific zones.
- Workloads needing anti-affinity may require replicas not to share a failure domain.

Forcing strict balance while ignoring data and dependency locality can increase cross-zone traffic latency and transfer fees. Conversely, packing too many machines into one convenient zone degrades fault tolerance. Prioritize among availability, latency, throughput, data locality, and cost, then test the trade-offs.

## 6. Using multiple instance types in the same group

Mixed instance groups allow a group to use multiple interchangeable machine types for a workload. This improves capacity acquisition odds when one instance type or zone faces supply shortages, while also optimizing costs.

Select machine types based on:

- vCPU count and benchmarked CPU performance.
- RAM and per-instance memory constraints.
- Network bandwidth, PPS, and connection limits.
- Storage types, IOPS, throughput, and local/ephemeral disk support.
- GPUs or accelerators if required by the workload.
- CPU architecture such as x86-64 or Arm and binary/runtime compatibility.
- Per-zone availability and account quotas.
- On-demand, committed, and Spot/preemptible pricing if used.

Do not lump every similarly named machine type into one group. Two instances with identical vCPU counts can differ substantially in CPU generation, RAM, networking, local storage, or sustained performance. Build a curated list of benchmarked, compatible instance types, then verify availability per zone.

## 7. Selecting equivalent machine type tiers

A mixed instance list should consist of machine types able to run the same workload without changing application logic. Organize them by capability tier:

| Workload | Candidate machine families | Equivalence criteria to verify |
|---|---|---|
| CPU-bound API | Compute-optimized of matching architecture or benchmarked generations | CPU throughput, clock behavior, sufficient network and memory |
| Memory-bound cache | Memory-optimized with suitable RAM/instance | RAM per node, memory bandwidth, network, and connection caps |
| General-purpose service | General-purpose within matching CPU/RAM ratio band | Balance of CPU, RAM, networking, and cost per workload unit |
| Independent batch jobs | Multiple compatible sizes | Throughput/job, completion time, and cost per job |
| GPU workload | GPU types supported by application and drivers | GPU model/count, VRAM, drivers, framework, and topology |
| Storage-intensive | Machine types with matching IOPS/throughput | Volume types, local NVMe, durability, and regenerable data |

CPU architecture is a strict constraint. Native binaries compiled for x86-64 will not run natively on Arm by default. Java bytecode is more portable, yet JNI libraries, native extensions, agents, drivers, and container images must still support the target architecture. For GPUs, drivers and framework versions must align with each instance type.

Avoid lists restricted to a single family or single size. Diversity across families, generations, and sizes increases capacity options, though excessive diversity complicates testing, images, drivers, and sizing. Validate a focused set of machine types before expanding.

## 8. Weighted capacity for differently sized instances

When mixing instance sizes, assign each type a capacity weight. The group manages desired capacity in units rather than raw machine counts. Illustrative example:

| Machine type | vCPU | RAM | Example capacity weight |
|---|---:|---:|---:|
| Small | 2 | 8 GiB | 2 |
| Medium | 4 | 16 GiB | 4 |
| Large | 8 | 32 GiB | 8 |

If desired capacity is 40 units, the group may run 10 Medium machines, 5 Large machines, or an equivalent weighted mix. These numbers illustrate representation only; real weights must come from benchmarks and workload traits.

Weighting by vCPU works only when CPU dominates and RAM/networking on every permitted type meet requirements. For a workload needing at least 12 GiB of RAM per worker, Small in the example above is invalid even though summing multiple Small machines reaches the same total RAM.

Practical rules:

- Define minimum per-instance requirements first (minimum RAM, GPU memory, local disk, or network).
- Exclude any machine type failing those minimums.
- Benchmark real throughput and derive weights from measured results.
- Check how the instance group rounds desired capacity when a machine's weight exceeds the remaining capacity gap.
- Confirm scale-in and instance replacement do not leave the group over- or under-capacity beyond acceptable bounds.

Never use weighted capacity to mask functional differences. If one instance type can handle only part of the workload, split it into a separate group or use explicit scheduling constraints.

## 9. Instance selection strategies during provisioning

When a group permits multiple machine types, the system needs a strategy for which type to request first. Common conceptual strategies:

- **Lowest price:** picks the cheapest compatible type.
- **Capacity availability:** picks types most likely to succeed in the current zone.
- **Diversified:** spreads allocations across multiple machine types to reduce reliance on one capacity pool.
- **Performance:** picks types offering the best benchmarked throughput or latency.
- **Balanced:** weighs price, allocation likelihood, and processing capacity together.

Exact names and algorithms vary by cloud provider. Some services offer capacity-optimized allocation for Spot, diversified allocation, or lowest-price; others provide distinct policies for regional managed groups. Clarify whether a strategy applies to On-Demand, Spot, or both, and how it falls back when a type cannot be provisioned.

For production workloads, avoid picking the cheapest type if it suffers high interruption rates or misses SLOs. True cost includes job re-runs, lost caches, restarts, cross-zone transfer charges, and operational overhead.

## 10. Combining On-Demand, Spot, and capacity reservations

Many machine groups combine purchasing models:

- **On-Demand:** suits baseline load requiring high availability and predictable uptime.
- **Spot/preemptible:** leverages spare capacity at lower cost, yet can be reclaimed under provider terms with limited warning.
- **Capacity reservations:** reserves capacity within a zone/machine-type scope or via service mechanisms, lowering allocation failure risk when needed.
- **Savings/commitment plans:** lower billing rates for committed usage, without necessarily guaranteeing physical capacity unless explicitly stated by the product.

A common pattern keeps the baseline on On-Demand or reserved capacity while using Spot for interruptible load. Stateless batch workers with checkpointing and retries fit Spot far better than stateful apps holding sessions in RAM.

Never place a critical service's entire minimum capacity on Spot if the workload cannot survive interruptions. Likewise, never assume a capacity reservation for one machine type in one zone transfers to another type or zone; reservation scope depends on the product.

## 11. Designing autoscaling across multiple zones and machine types

Autoscaling decides when to add or remove capacity. When groups span multiple zones and instance types, define the scaling unit and desired capacity calculation clearly.

Core elements:

- **Minimum capacity:** floor kept for baseline load and availability requirements.
- **Desired capacity:** current group target, measured in instance counts or weighted units.
- **Maximum capacity:** ceiling imposed by quotas, budgets, and infrastructure limits.
- **Scaling metric:** CPU, requests per target, queue depth, latency, or business metrics.
- **Cooldown/warm-up:** time for new instances to boot, bootstrap, and start serving.
- **Scale-in policy:** how instances are selected for removal when shrinking capacity.

During scale-out, the group can spread new machines across zones and pick available instance types. During scale-in, preserve zone balance and fault-tolerance headroom. If scale-in simply terminates the cheapest or newest machine without checking zones, the group can inadvertently lose redundancy in one zone.

Group-wide average metrics can mask imbalances. For instance, average CPU may read 50% while one zone runs at 90% and another at 10%. Monitor metrics by zone, machine type, and individual instance, and inspect load balancer request distribution.

## 12. Ensuring capacity when a zone or instance type fails to provision

Cloud capacity is not infinitely available everywhere. One zone may temporarily run out of a given instance type even while another zone has plenty. Quotas can also cap total vCPUs, GPUs, IP addresses, or instance counts.

To reduce risk:

1. Include multiple compatible instance types instead of relying on a single size.
2. Span multiple zones within the region if the architecture permits.
3. Verify quotas per machine family, vCPU, GPU, Spot, and network addresses.
4. Use capacity reservations for critical baseline load when allocation guarantees are required.
5. Configure retries with backoff for transient allocation errors, avoiding tight retry loops.
6. Alert when desired capacity exceeds actual capacity past an acceptable threshold.
7. Test scenarios where an entire zone or machine family cannot provision.

If every listed machine type runs out of capacity in one zone, autoscaling cannot launch new machines there. The system may shift allocations to other zones if supported by the service and allowed by subnets, quotas, storage, and dependencies. Verify actual failover behavior when one zone is excluded from placement.

## 13. Preventing skewed distribution with mixed machine types

Imbalances can arise along two dimensions:

- **Zone skew:** one zone holds disproportionate capacity because another zone lacked supply or rebalancing has not finished.
- **Instance type skew:** one machine type dominates because selection strategies favored it, tying the workload to a single capacity pool or performance profile.

Control measures:

- Track instance counts and weighted capacity per zone and per family.
- Cap the maximum share of any single instance type when diversity is needed.
- Curate machine type lists into benchmarked equivalence tiers.
- Inspect capacity distribution after every scaling event and Spot interruption.
- Use rebalancing or instance replacement policies where supported.
- Ensure load balancers route traffic only to healthy, ready instances.

Do not enforce family ratios so rigidly that the group cannot provision enough capacity during an outage. Balance desired diversity against real allocation resilience.

## 14. Rebalancing and instance replacement

Rebalancing restores a group to its target distribution after zone availability or instance type composition shifts. A service may launch replacement machines before terminating old ones, or follow a different flow depending on policy and capacity limits.

During rebalancing, check:

- **Surge capacity:** do quotas and maximum limits permit launching new machines before removing old ones?
- **Connection draining:** has the load balancer stopped new requests and waited for in-flight requests to finish?
- **Stateful data:** does data reside on zone-pinned volumes or local ephemeral storage?
- **Bootstrap:** can new instances fetch artifacts, secrets, and configs within required windows?
- **Health/readiness:** new machines must receive traffic only once ready.
- **Scale-in protection:** do machines holding special roles need protection from automated termination?

For instances using local/ephemeral disks, termination wipes local data. Restrict ephemeral storage to regenerable data, caches, or checkpointed workloads. Durable data belongs on storage services with independent lifecycles and replication/backup plans.

## 15. Aligning multi-zone compute with data and dependencies

Compute may span multiple zones while a database or storage volume still lives in a single zone. When that single-zone dependency fails, surviving VMs in other zones still cannot serve traffic.

Inspect all dependencies:

- Do databases support multi-zone replication, failover, and routing endpoints?
- Are block volumes pinned to a single zone? Are snapshots, replication, or replacement volumes needed?
- Can caches rebuild and warm up in surviving zones?
- Are queues and message brokers zone-fault-tolerant?
- Are DNS, secret managers, container/image registries, and control planes reachable if one zone fails?
- Do NAT gateways, firewalls, egress paths, and routes contain single points of failure?

Cross-zone traffic incurs both cost and latency. If workloads frequently read data from another zone, calculate total data transfer costs and p99 latency impact. Consider placing data replicas closer to compute or adjusting placement to minimize cross-zone hops.

## 16. Design example: three-zone regional group with mixed instance types

Suppose a stateless API must serve peak load equivalent to 300 capacity units. The group spans three zones, each with its own subnet. The workload supports two benchmarked machine types: type M (weight 4) and type L (weight 8). Both meet minimum RAM requirements and runtime compatibility.

An initial design:

| Component | Illustrative design |
|---|---|
| Region | One region with three supported AZs |
| Normal capacity | 300 units, targeting roughly 100 units per AZ |
| Failover capacity | Two surviving AZs capable of reaching 150 units per AZ if one AZ fails |
| Instance types | M (weight 4), L (weight 8), benchmarked |
| Purchase model | On-Demand for baseline; Spot only for retry-safe stateless portion if appropriate |
| Scaling signal | Request count per target paired with latency and queue depth |
| Min/Max | Min covering baseline and N-1 requirements; Max bounded by quotas, budget, and capacity tests |
| Health | Readiness endpoints and load balancer health checks |
| Scale-in | Drain connections, protect needed state, maintain zone balance |

Because each AZ needs up to 150 units if one AZ fails, you can keep partial headroom pre-provisioned per AZ and rely on scale-out for the remainder. If provisioning new machines exceeds your RTO, retain more warm capacity rather than relying entirely on post-incident autoscaling.

When an AZ lacks capacity for type L, the group can provision multiple type M machines provided total weight hits target and each machine meets minimum RAM. If type M fails the application's memory floor per instance, you cannot substitute by summing weights; restrict the list to machine types meeting every minimum requirement.

## 17. Testing capacity distribution and failure scenarios

Testing must verify not only that the group launches the right machine count, but also real serving capacity and failure-domain behavior.

Recommended test scenarios:

1. **Steady state:** confirm capacity and zone/family balance under normal load.
2. **Scale-out:** ramp load and measure elapsed time from trigger until instances become healthy and serve traffic.
3. **Scale-in:** reduce load and verify draining and data handling behave cleanly.
4. **Zone impairment:** simulate or drill taking one zone out of service and verify N-1 capacity.
5. **Instance type unavailable:** confirm the group falls back to alternate types and reaches target capacity units.
6. **Spot interruption:** if using Spot, verify checkpointing, retries, replacement, and interruption notices.
7. **Rebalance:** verify surge capacity, quotas, and traffic impact.
8. **Dependency failure:** confirm live compute is not misreported as healthy serving when databases/storage fail.

Record desired capacity, actual capacity, pending instances, per-zone/per-family capacity, boot times, warm-up times, health states, request rates, latency, and error rates. A test passes only when SLOs and recovery objectives hold—not merely when instance creation APIs return success.

## 18. Monitoring and alerting

An instance group dashboard should display at least:

- Desired, actual, minimum, and maximum capacity.
- Instance counts and weighted capacity by zone.
- Capacity by instance family/size and purchase model.
- Pending, unhealthy, terminating, and interrupted instances.
- Request distribution, CPU, memory, network, and disk utilization by zone/type.
- Time from scaling trigger to healthy capacity.
- Provisioning errors caused by quotas, capacity exhaustion, or invalid config.
- Cost broken down by zone, machine type, and purchase model.

Critical alerts:

- Actual capacity remains below desired past allowed convergence windows.
- Any zone shows abnormally low or high capacity share.
- The group lacks sufficient capacity for an N-1 failure scenario.
- A single instance type's share grows excessive or incompatible substitutes appear.
- Prolonged scale-outs, stuck pending instances, or failing health checks.
- Quotas approach limits or capacity reservations no longer match deployment needs.
- Rising Spot interruptions or jobs failing to checkpoint in time.

Never alert solely on instance counts. In mixed groups, monitor weighted capacity and enforce per-machine minimum resource checks.

## 19. Common design mistakes

- **Counting instances instead of capacity:** the group meets its machine count yet lacks processing power. Use weights or benchmarked application throughput.
- **Summing vCPUs while ignoring RAM:** substitute machines fail to run the workload due to insufficient per-node memory. Enforce minimum per-instance specs.
- **Running in a single zone:** a single zone outage takes down all compute. Spread across appropriate failure domains.
- **Assuming autoscaling can always find machines:** zones or families can run out of capacity, and quotas can block launches. Diversify machine types and test allocation failures.
- **Omitting N-1 headroom:** losing one zone overloads surviving zones before scale-out finishes. Size failover capacity for peak load.
- **Putting non-interruptible load on Spot:** interruptions drop requests or lose state. Keep baselines on On-Demand and reserve Spot for checkpointed/retryable work.
- **Making the mixed instance list too broad:** incompatible images, CPU architectures, drivers, or RAM sneak in. Stick to verified types.
- **Terminating before launching replacements during rebalance:** causes capacity dips or local data loss. Verify surge and termination policies.
- **Watching only group-wide metrics:** zone or instance-type skew goes unnoticed. Break telemetry down across every dimension.
- **Ignoring multi-zone dependencies:** compute survives while a single-zone database or storage volume becomes the single point of failure. Engineer end-to-end resilience.

## 20. Design checklist

- [ ] Defined capacity units matching the workload plus per-instance minimum resource bounds.
- [ ] Selected zones supporting required instance types, subnets, and dependencies.
- [ ] Sized peak capacity and N-1 zone-loss scenarios.
- [ ] Provisioned headroom, quotas, or reservations aligned with recovery time targets.
- [ ] Benchmarked all candidate instance types across CPU, RAM, network, storage, and accelerators.
- [ ] Verified CPU architecture, runtime, native libraries, and drivers across every type in the group.
- [ ] Verified weighted capacity reflects measured throughput and handles large-weight rounding cleanly.
- [ ] Separated purchase models between stable baseline and interruptible workload capacity.
- [ ] Configured autoscaling min/desired/max, metrics, warm-up, and scale-in policies clearly.
- [ ] Planned surge capacity, connection draining, and data protection for rebalancing.
- [ ] Verified dependencies (databases, storage, queues, NAT, DNS) are also zone-resilient.
- [ ] Built dashboards tracking capacity by zone, instance type, health, and purchase model.
- [ ] Tested zone impairment, allocation failures, Spot interruptions, scale-in, and N-1 scenarios.

Distributing capacity across multiple zones and machine types gives instance groups both fault tolerance and flexibility as cloud supply shifts. When capacity reflects real workload capability, machine types are vetted for compatibility, zones retain failover headroom, and autoscaling is tested against capacity shortages, systems maintain SLOs with far more predictable cost and risk.
