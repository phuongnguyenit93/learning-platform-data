# Diversifying Instance Types, Zones, and Capacity Sources

## Learning Objectives

In a cloud environment, capacity is not always available in the exact machine type, zone, and moment needed. This is especially critical for Spot or preemptible compute: one pool can run out of capacity or be reclaimed while another pool still has available resources. If a fleet depends on a single instance type or a single Availability Zone, scaling and recovery are severely constrained.

Capacity diversification means designing resource groups with multiple compatible choices across machine configurations, deployment zones, and capacity sources. The goal is to increase the odds of acquiring compute as demand shifts, soften the impact when a pool runs short or is disrupted, and keep performance and cost within bounds.

After this lesson, you will be able to:

- Explain capacity pools and the factors that define a pool.
- Select multiple interchangeable instance types.
- Spread workloads across multiple zones and weigh expanding to another region.
- Combine Spot, on-demand, and guaranteed capacity.
- Distinguish cost commitments from capacity commitments.
- Design fleet allocation, fallback, and budget limits.
- Use labels, taints, affinity, and topology spread in Kubernetes.
- Measure diversification effectiveness, provisioning fulfillment, and cost per unit of work.

## 1. Why Diversify Capacity?

Cloud providers partition infrastructure into resource groups with differing provisioning availability. A VM request typically depends on instance type, Availability Zone, CPU architecture, accelerator type, and purchase option. When one combination runs out of capacity, a launch request can fail even if the region has plenty of machines in other configurations.

With Spot or preemptible compute, the risk is sharper because the provider can reclaim capacity to meet higher-priority demand. If a fleet uses only one machine type in one zone, a single capacity crunch can impact most workers at once.

Diversification helps:

- Increase the number of capacity pools able to serve the workload.
- Reduce reliance on a single instance family, zone, or capacity source.
- Improve scale-out odds during sudden demand spikes.
- Dampen the impact when one pool experiences high interruption rates.
- Provide fallback options when Spot fails to provision enough machines.
- Balance cost, performance, and availability.

Diversification does not mean accepting every machine type. Choices must satisfy the same functional requirements, minimum performance, software architecture, networking, storage, and security policies.

~~~mermaid
flowchart TD
    W["Workload needs more capacity"] --> P["Capacity policy"]
    P --> T1["Instance family / size A"]
    P --> T2["Instance family / size B"]
    P --> T3["Instance family / size C"]
    T1 --> Z1["Zone 1"]
    T1 --> Z2["Zone 2"]
    T2 --> Z1
    T2 --> Z3["Zone 3"]
    T3 --> Z2
    T3 --> Z3
    Z1 --> S1["Spot pool"]
    Z2 --> S2["Spot pool"]
    Z3 --> S3["Spot pool"]
    P --> O["On-demand / reserved capacity"]
~~~

## 2. What Is a Capacity Pool?

A capacity pool is a set of resources a provider can allocate under a specific set of constraints. Exact definitions vary by service, though common dimensions include:

- Region and Availability Zone.
- Instance family, generation, and size.
- CPU architecture, such as x86-64 or Arm.
- CPU, RAM, GPU, or accelerator.
- Network bandwidth, NIC count, or enhanced networking support.
- Local storage, volume types, and IOPS/throughput limits.
- Operating system, hypervisor, tenancy, or placement requirements.
- Purchase option: on-demand, Spot, or another capacity class.

Two machines with identical vCPU and RAM counts are not guaranteed to sit in the same pool or deliver equivalent performance. Differences in CPU generation, memory bandwidth, baseline networking, local NVMe, or GPUs can substantially affect workloads.

### 2.1. Pools Can Exhaust Independently

Suppose a fleet requests a large compute-optimized family instance in a single zone. If that pool runs out of Spot capacity, launch requests may fail. Meanwhile, a memory-optimized machine or a different compute-optimized family in another zone might still provision cleanly.

Hence, region-wide capacity does not mean every machine configuration can launch immediately. Track provisioning outcomes by instance type, zone, and purchase option combination rather than looking only at total regional VMs.

### 2.2. Useful Pool Count Matters More Than Options on Paper

A list of 30 instance types does not create 30 real options if most are incompatible with the application, exist in only one zone, or hit separate quota limits.

Evaluate each candidate by:

- Architecture and binary compatibility.
- Minimum CPU/RAM and CPU-to-memory ratio.
- Benchmark performance on real workloads.
- Required networking and storage.
- Per-zone availability.
- Pricing, interruption history, and capacity fulfillment.
- Quotas, licensing, and platform constraints.

## 3. Diversifying Instance Types

Instance types are commonly grouped by purpose and hardware profile.

| Machine class | Typical traits | Suitable workloads |
|---|---|---|
| General purpose | Balanced CPU, RAM, and network | Web/API, general-purpose services |
| Compute optimized | High CPU-to-RAM ratio | Compute batch, parallel processing |
| Memory optimized | Large RAM, high memory bandwidth | Caches, in-memory databases, analytics |
| Storage optimized | High local storage or I/O | Data processing, scratch caches, I/O workloads |
| Accelerated computing | Dedicated GPUs or accelerators | ML inference/training, rendering, HPC |

This is a broad grouping; exact family names and characteristics depend on the provider. Never swap one instance type for another solely because vCPU counts match. A workload may be sensitive to CPU clock, memory bandwidth, cache, network throughput, or local disk latency.

### 3.1. Building an Equivalent Instance Set

Before adding a new type to the fleet, define minimum requirements:

- vCPU count or equivalent processing capacity.
- RAM size and memory bandwidth.
- CPU architectures supported by the application.
- Network throughput and packet rate.
- Storage throughput, IOPS, and ephemeral capacity.
- GPU model, VRAM, and driver if the workload uses accelerators.
- Kernel, OS image, runtime, and license requirements.

Next, benchmark a representative subset. You can normalize capacity to a unit such as vCPUs, worker slots, or measured throughput, but never assume 1 vCPU performs identically across two families.

### 3.2. CPU Architecture Differences

Diversifying between x86-64 and Arm can expand capacity pools, provided you verify:

- Whether container images have multi-architecture manifests.
- Whether native libraries, JNI, and binaries have matching builds.
- Whether JDKs, runtimes, security agents, and monitoring tools support them.
- Performance and cost per request/job.
- Instruction sets or extensions the application depends on.

If an image only ships an x86-64 build, adding Arm instances to the fleet may allow launches to succeed while containers fail to start. Build and test multi-architecture images before placing both architectures into the same policy.

### 3.3. Matching Sizes and Equivalent Performance

Different sizes within the same family do not necessarily share identical network or storage profiles. Smaller sizes may have lower baseline throughput or burst limits. For workloads needing a specific capacity target, consider:

- Using weighted capacity by vCPU, worker slots, or benchmark units.
- Splitting jobs into task sizes suited to multiple machine types.
- Avoiding scheduling high-RAM tasks onto small instances.
- Configuring concurrency per instance size.
- Tracking actual throughput by instance type.

If a fleet measures desired capacity in instance counts, a 4-vCPU machine and a 32-vCPU machine each count as one unit. Actual capacity fluctuates wildly when the autoscaler picks different types. Use weighted capacity or workload-level metrics to reflect true capacity.

### 3.4. Avoiding Diversification That Breaks Consistency

Never add a machine type merely to inflate pool count if it forces bespoke workload configurations. For example, some machines carry local NVMe while others offer only network block storage; the application would have to handle differences in durability, mounting, and I/O. Limit the list to choices that share images, bootstrapping, and operations—or split them into separate workload pools.

## 4. Diversifying Availability Zones

An Availability Zone (AZ) is an independent deployment domain within a region, typically with isolated infrastructure and failure domains. Running workloads across multiple AZs reduces dependence on a single local infrastructure zone.

For Spot, each AZ can have distinct capacity pools and availability levels. If one AZ runs short on capacity, the fleet can still acquire machines in another AZ if configuration and application architecture permit.

### 4.1. Spreading Across Zones

A fleet can:

- Allow launches across multiple AZs.
- Distribute replicas or workers across AZs.
- Maintain minimum capacity across critical zones.
- Track interruptions and capacity fulfillment per AZ.
- Avoid placing all workers into a single zone solely for current spot price or capacity.

Even distribution is not always the optimal goal. One AZ may have smaller pools or differing network economics. Balance fault tolerance, latency, cross-AZ data transfer costs, and storage requirements.

### 4.2. How Storage and State Affect Zone Choices

Some block storage volumes are bound to a single AZ. If an instance is reclaimed and the replacement lands in another AZ, the volume may not attach directly. Options include:

- Using object storage or multi-AZ accessible databases.
- Replicating data across zones.
- Using storage with multi-AZ semantics if supported by the service.
- Keeping workers close to data partitions with a locality-aware scheduler.
- Designing checkpoints independent of local disks or single-zone volumes.

Do not expand workers into another AZ without checking data placement and reachability. Cross-AZ charges and latency can also alter total processing cost.

### 4.3. Topology and Availability

For multi-replica services, use topology spread or anti-affinity to avoid placing all replicas in the same zone or node. Combine this with minimum replicas, PodDisruptionBudgets, and sufficient headroom in remaining zones.

If an entire zone fails, remaining zones must be able to absorb the extra load. Even spread under normal conditions is insufficient; verify spare capacity after losing a zone.

## 5. When Is Region Diversification Needed?

Region diversification can improve resilience against wide-scale outages or capacity shortages. However, crossing regions introduces far heavier shifts than crossing AZs:

- Network latency and data transfer costs.
- Data residency, compliance, and data location constraints.
- Database/object storage replication capabilities.
- DNS, routing, load balancing, and failover.
- Differing quotas, service availability, and instance families.
- Multi-region operations for images, secrets, certificates, and observability.

For stateless Spot workers, running across multiple regions can work if inputs and outputs reside in securely reachable storage or replicated data. For workloads tied to a single-region database, placing workers in another region can raise latency and egress fees, wiping out compute savings.

Region diversification must be treated as a resilience and data architecture decision, not simply adding another instance option.

### 5.1. Order of Scope Expansion

A common progression:

1. Expand instance types within the same workload profile.
2. Enable multiple AZs within the same region.
3. Add on-demand or guaranteed capacity sources.
4. Consider a second region when data, networking, and operations allow.
5. Consider multi-cloud only with clear resilience, compliance, or platform strategy reasons.

Each step adds complexity. Expand scope when capacity and resilience gains outweigh networking, data, and operational costs.

## 6. Diversifying Capacity Sources

The capacity source governs how resources are provisioned, priced, and retained. Common sources:

| Source | Characteristics | Role in fleet |
|---|---|---|
| On-demand | Pay-as-you-go with no long-term commitment | Baseline capacity or flexible fallback |
| Spot/preemptible | Uses spare capacity; can be reclaimed | Supplementary capacity for fault-tolerant workloads |
| Capacity reservation | Pre-reserves specific capacity per service terms | Guarantees launchability for defined demand |
| Billing commitment (Savings Plans / Reserved Instances) | Usage or spend commitment for discounted rates; semantics vary by product | Cost optimization for steady demand |
| Dedicated host/instance | Dedicated physical infrastructure or tenancy per product | Special licensing, isolation, or placement requirements |
| Warm pool | Pre-initialized instances to shorten scale-out time | Cuts startup delay; may incur standing charges |

Not every source type can be mixed inside a single fleet policy. Verify service APIs and feature support.

### 6.1. Distinguishing Billing Discounts from Capacity Reservations

A commitment or Savings Plan can lower unit billing rates without automatically guaranteeing machines in a specific AZ or instance type. Reserved Instances can also carry different semantics by scope and product; some regional commitments are primarily billing benefits, while zonal commitments may bind capacity per provider terms.

When you need guaranteed launch capability, verify whether a reservation actually holds capacity or only applies a discount. Never plot a billing commitment on capacity diagrams as if it were always a pre-reserved pool.

### 6.2. On-Demand Baseline and Spot Burst

A common pattern maintains baseline capacity via on-demand or guaranteed sources, then adds Spot as load rises.

For example:

- Maintain minimum workers for baseline load using on-demand.
- Add Spot workers when queue backlog or request rate climbs.
- If Spot fails to provision, allow on-demand fallback up to a cap.
- When load drops, scale in Spot first per policy.
- Keep enough buffer capacity to absorb interruptions and replacement startup times.

The on-demand/Spot ratio must reflect SLOs, interruption rates, replacement times, and budgets. There is no universal 70/30 or 80/20 split valid for every system.

### 6.3. Fallback Must Be Bounded

Falling back to on-demand can protect SLOs when Spot pools dry up, but can also cause costs to spike rapidly. Define:

- Maximum on-demand level.
- Conditions triggering fallback.
- How long fallback may remain active.
- Budget alert thresholds.
- Which work gets priority when capacity is constrained.
- How to scale back in once Spot capacity recovers.

Without guardrails, a Spot shortage can shift the entire fleet onto on-demand and blow the budget.

## 7. Designing Fleet Allocation

Fleet allocation is how the controller chooses pools and distributes capacity across configured options, weights, and strategies.

A policy can weigh:

- Current Spot prices or discounts.
- Pool capacity fulfillment odds.
- Interruption history or risk signals if provided by the cloud.
- Available AZs and instance types.
- On-demand baseline and fallback.
- Weighted capacity and workload priority.

Strategies such as lowest price, capacity prioritized, or price/capacity balanced are common implementations. Exact names and algorithms differ across services; read the specific provider's documentation.

### 7.1. Using Weighted Capacity

When instance types vary in size, fleets should measure capacity in appropriate units:

- vCPUs if the workload is mostly CPU-bound.
- GiB RAM if the workload is memory-bound.
- GPUs or accelerator units if the workload needs GPUs.
- Worker slots or benchmark throughput if the workload has clear processing units.

For instance, an 8-vCPU instance gets weight 8 and a 16-vCPU instance gets weight 16 if the target is total vCPUs. However, if per-vCPU performance differs, assign weights based on benchmarked throughput. Pick a unit that is explainable and measurable.

Never collapse CPU, memory, and GPU weights into a single number if the workload faces multi-dimensional resource constraints. Split pools by profile or use a scheduler aware of multiple resource dimensions.

### 7.2. Provider-Agnostic Illustrative Policy

The example below is a conceptual configuration model, not an API schema directly applicable to any cloud provider:

~~~yaml
fleet:
  workload: batch-worker
  minimumCapacity:
    source: on-demand
    units: 8
  maximumCapacity:
    units: 64

  compatiblePools:
    - instanceFamily: compute-general
      sizes: [large, xlarge]
      architectures: [x86_64]
      zones: [zone-a, zone-b, zone-c]
      weightUnit: vcpu

    - instanceFamily: compute-alternative
      sizes: [large, xlarge]
      architectures: [x86_64]
      zones: [zone-a, zone-b, zone-c]
      weightUnit: vcpu

  allocation:
    spot:
      strategy: capacity-aware
      diversified: true
    onDemand:
      baselineUnits: 8
      fallback:
        enabled: true
        maximumUnits: 24

  interruption:
    checkpointRequired: true
    drainBeforeTerminate: true
~~~

A real policy must use the exact instance type names, zone IDs, allocation strategies, capacity units, and fields supported by the provider. This example solely illustrates the concept: hold baseline capacity, expand across compatible pools, and cap fallback.

## 8. Diversification in Kubernetes

Kubernetes can schedule Pods across multiple node pools. A cluster might contain:

- An on-demand node pool for control workloads or stability-sensitive services.
- Spot node pools for batch, CI, or fault-tolerant workers.
- Multiple instance families and sizes within compatible pools.
- Nodes across multiple zones.
- Dedicated pools for GPU, memory-intensive, or storage-intensive workloads.

### 8.1. Using Labels and Taints

Nodes can carry labels describing capacity type, zone, instance family, or architecture. Taints prevent unsuitable workloads from scheduling onto those pools automatically.

Example of a batch Pod tolerating Spot nodes and selecting x86-64 architecture:

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/arch: amd64
    capacity-type: spot
  tolerations:
    - key: capacity-type
      operator: Equal
      value: spot
      effect: NoSchedule
~~~

The `capacity-type` label is an illustrative convention; providers or node provisioners may use different label names. Check actual node labels before using them.

### 8.2. Node Affinity for Multiple Choices

If a workload accepts multiple families, use node affinity with an allowlist. The example below illustrates accepting one of several permitted families:

~~~yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: nodepool.example.com/instance-family
                operator: In
                values:
                  - compute-family-a
                  - compute-family-b
              - key: topology.kubernetes.io/zone
                operator: In
                values:
                  - zone-a
                  - zone-b
                  - zone-c
~~~

The instance-family and zone labels must match cluster metadata. If Pods require local storage, GPUs, or specific architectures, add matching expressions. Do not set affinity so strictly that the scheduler has zero qualifying pools left.

### 8.3. Spreading Replicas Across Zones

Topology spread constraints help distribute replicas across zones:

~~~yaml
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: ScheduleAnyway
      labelSelector:
        matchLabels:
          app: batch-worker
~~~

`ScheduleAnyway` prioritizes spread while still allowing scheduling if perfect balance is unavailable. For services requiring strict spread, choose `DoNotSchedule` after weighing capacity and Pending Pod risks. A hard policy can stall workloads when one zone runs short of capacity.

### 8.4. PDBs and Node Disruption

PodDisruptionBudgets help govern planned evictions. They do not block provider node reclamation or sudden host loss. When using Spot nodes:

- Maintain enough replicas and spread across nodes/AZs.
- Run a termination handler to receive notices and drain when possible.
- Use checkpoints/retries for workers.
- Ensure volumes and state do not depend on reclaimable nodes.
- Test sudden node loss, not only planned drains.

## 9. Routing Workloads by Compatibility Profile

Not every workload should run on every pool. Separating workloads by profile keeps policies clear:

| Profile | Constraints | Suggested capacity sources |
|---|---|---|
| Stateless API | Latency, network, minimum healthy replicas | On-demand baseline, Spot for expansion if SLOs permit |
| Batch worker | Retryable/checkpointable, clear CPU or memory profile | Multiple Spot pools and on-demand fallback |
| GPU inference | GPU model, VRAM, drivers, network | Compatible GPU pools; guaranteed baseline if SLOs require |
| Data processing | Data locality, storage throughput, partitions | Multiple equivalent pools, locality-aware scheduler |
| Stateful database | Quorum, storage, replication, and failover | Stable capacity, proper reservations, and controlled topology |
| CI runner | Independent tasks, durable caches and artifacts | Diversified Spot, fallback when queue exceeds threshold |

Separating pools also prevents one workload from exhausting capacity needed by another. For instance, batch workers can span multiple Spot families while latency-sensitive APIs stay on on-demand in guaranteed zones.

## 10. Measuring Diversification Effectiveness

The number of instance types listed in configuration does not prove a fleet is effectively diversified. Measure real provisioning outcomes and actual concentration.

Metrics and reports to maintain:

| Metric | Meaning |
|---|---|
| Pool count eligible | Pools that are genuinely compatible and permitted |
| Pool count fulfilled | Pools actively supplying capacity |
| Capacity share by type | Capacity share per instance type/family |
| Capacity share by zone | Capacity share per AZ |
| Capacity share by source | Share of on-demand, Spot, and other sources |
| Launch fulfillment rate | Percentage of launch requests satisfied |
| Launch latency | Time from request to instance running |
| Time to ready | Time until the workload can accept work |
| Interruption rate by pool | Interruption rate per type/zone/source |
| Fallback rate | Share of capacity shifted to on-demand |
| Pending workload | Count of Pods/jobs waiting on capacity |
| Cost per completed unit | Cost per completed request/job/record |

Use concentration ratios to detect over-reliance on a single pool. For example, if 90% of Spot capacity comes from one type in one AZ, config lists many options yet the live fleet remains concentrated.

### 10.1. Configured Diversity vs. Realized Diversity

**Configured diversity** is the number of pools permitted for selection.

**Realized diversity** is the number of pools actually supplying capacity and the distribution across them.

A pool may sit in policy yet never get picked due to high prices, missing quotas, or poor performance. Reports should display both eligible pools and fulfilled pools.

### 10.2. Setting Concentration Thresholds

Establish guardrails such as:

- Prevent a single AZ from holding more than a target share if the workload requires multi-zone resilience.
- Prevent a single Spot pool from holding the majority of workers.
- Alert when a family drops out of the fleet due to launch failures.
- Monitor abnormal spikes in on-demand fallback.
- Verify minimum healthy capacity under single-zone loss.

Thresholds should fit the SLO and infrastructure layout. Do not apply identical ratios to a 3-replica service and a 300-worker batch fleet.

## 11. Costs of Diversification

Diversification boosts resilience but also introduces costs and complexity:

- Cross-AZ or cross-region data transfer.
- Storage and database replication.
- Images, artifacts, and caches distributed across multiple zones/regions.
- Baseline capacity held across multiple AZs.
- Architecture-dependent licensing or software.
- More complex monitoring, policies, and automation.
- Benchmarking and testing multiple instance types.
- Spare capacity held to survive loss of a zone or pool.

Evaluate cost per completed workload:

~~~text
Total cost =
  compute
  + storage
  + network transfer
  + replication
  + retries and checkpoints
  + standby capacity
  + operations
~~~

Divide by completed units of work or successful requests. A fleet with low compute rates but heavy retries or cross-region transfer can cost more than a less-diversified, steadier fleet.

### 11.1. Avoid Optimizing Individual Machine Price

When comparing two pools, factor in:

- Actual hourly throughput.
- Startup and warmup time.
- Interruptions and rework.
- Storage and network costs.
- Ability to hit SLOs.
- Fallback and standby capacity costs.

If a cheaper instance type runs much slower, the cost for the same job can end up higher.

## 12. Workflow for Designing a Compatible Capacity List

A practical workflow:

1. **Classify the workload:** CPU-bound, memory-bound, I/O-bound, GPU, or latency-sensitive.
2. **Set constraints:** vCPU, RAM, architecture, storage, network, accelerator, and OS.
3. **Select candidates:** list interchangeable families/sizes.
4. **Benchmark:** measure throughput, latency, and memory across candidates.
5. **Check zones:** verify candidate types exist in target zones and storage/data are reachable.
6. **Pick sources:** determine required on-demand baseline, Spot burst, and reservations.
7. **Design fallback:** cap on-demand spillover and define job priorities.
8. **Configure the fleet:** apply weighted capacity and appropriate allocation strategies.
9. **Fault test:** drain a pool, zone, or Spot source in a test environment.
10. **Measure live:** track fulfillment, interruptions, concentration, SLOs, and cost per completed unit.
11. **Iterate:** prune underperforming candidates and add benchmarked pools.

You do not need to enable every option at once. Expand incrementally and observe effects before introducing more variables.

## 13. Testing Capacity Shortage Resilience

A fleet is well-diversified only if it keeps operating when a subset of pools cannot provision machines.

Scenarios to test:

- One instance type runs out of capacity.
- One AZ cannot launch new machines.
- Spot capacity is insufficient while on-demand remains available.
- Quota for one family is hit.
- A CPU architecture is incompatible with the image.
- New nodes exist, yet Pods fail to schedule due to affinity or taints.
- Storage fails to attach in an alternate zone.
- Cross-zone networking or dependencies degrade.
- An interruption wave hits multiple workers simultaneously.
- Fallback triggers and hits budget limits.

Measure whether the fleet finds replacement pools, time until capacity turns healthy, how high backlogs climb, and whether SLOs break. After tests, verify no data or work was lost.

## 14. Common Mistakes

**Configuring only a single instance type:** when that pool exhausts capacity, the fleet stops scaling. Expand to benchmarked equivalent types.

**Adding types across different architectures:** images or native dependencies may fail to run. Verify multi-architecture builds and runtimes.

**Diversifying sizes while counting capacity by machine count:** small and large machines get counted identically. Use weighted capacity or workload-level metrics.

**Using a single AZ:** one zone shortage or outage hits the whole fleet. Spread across multiple AZs when data and apps support it.

**Expanding regions without data design:** workers cannot reach data or incur high latency/egress fees. Check replication and data locality.

**Confusing commitments with reservations:** billing discounts do not automatically reserve capacity. Verify product semantics.

**Running 100% Spot capacity:** a single reclamation wave can wipe out most capacity. Maintain an on-demand baseline or appropriate fallback.

**Unbounded fallback:** Spot shortages can cause on-demand spend to surge. Set caps and budget alerts.

**Overly rigid topology constraints:** scheduler finds zero eligible nodes when a zone lacks capacity. Balance resilience requirements against schedulability.

**Treating PDBs as anti-reclamation guarantees:** PDBs do not stop abrupt node loss. Design retries, checkpoints, and replicas.

**Not measuring concentration:** config lists many choices yet most live capacity comes from one pool. Track shares by type, zone, and source.

**Looking only at hourly prices:** ignores networking, retries, warmup, and throughput. Measure cost per completed unit.

## 15. Compute Diversification Checklist

- [ ] Workload resource profile and constraints are defined.
- [ ] Instance type list includes multiple benchmarked compatible options.
- [ ] CPU architectures, images, runtimes, and native dependencies are verified.
- [ ] Actual CPU, RAM, network, storage, and accelerators are compared.
- [ ] Fleet uses weighted capacity or suitable capacity units.
- [ ] Multiple AZs are enabled when applications and data permit.
- [ ] Storage locality and cross-AZ/region network costs are checked.
- [ ] Secondary region has a data replication, routing, and failover plan.
- [ ] On-demand, Spot, reservations, and billing commitments are clearly distinguished.
- [ ] On-demand baseline or guaranteed capacity covers essential needs.
- [ ] Spot allocation uses an explicit strategy and compatible pool list.
- [ ] On-demand fallback is bounded by capacity and budget limits.
- [ ] Kubernetes labels, taints, affinity, and topology spread are configured properly.
- [ ] PDBs and termination handlers are scoped appropriately.
- [ ] Metrics track fulfillment, interruptions, concentration, and time-to-ready.
- [ ] Dashboards show capacity share by instance type, zone, and source.
- [ ] Tested exhaustion of a pool, a zone, and Spot capacity.
- [ ] Cost per completed unit of work is measured.

Diversifying instance types, zones, and capacity sources gives fleets multiple alternatives when a capacity pool runs short or suffers disruptions. Start from real workload requirements, benchmark equivalent configurations, spread across multiple failure domains, and combine Spot with stable capacity. Clearly separating guaranteed capacity from billing discounts, bounding fallback, and measuring realized concentration enable flexible scaling while keeping SLOs, data, and costs under control.
