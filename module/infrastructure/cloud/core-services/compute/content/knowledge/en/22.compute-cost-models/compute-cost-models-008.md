# Comparing Total Cost of Ownership Across VMs, Containers, and Serverless

When choosing a model to run an application on the cloud, hourly or per-request compute pricing is only one piece of the cost. A low-unit-price VM running continuously at near-zero load can still be expensive. Containers pack multiple services onto the same node, yet require paying for nodes, control planes, registries, storage, and platform operations capacity. Serverless reduces machine management effort and can scale to zero, yet costs rise with request volume, execution duration, memory, concurrency, and supporting services.

**Total Cost of Ownership (TCO)** is the total cost required to bring a workload into production, operate, secure, scale, and evolve it over a defined timeframe. Comparing TCO across VMs, containers, and serverless must use the exact same workload, SLOs, security requirements, and cost scope.

In **CLOUD_CORE_SERVICES_COMPUTE**, comparisons must account for compute, storage, network, licenses, observability, backups, control planes, labor, migration, fault tolerance, and cost scaling as workloads grow or shrink. The cheapest option on the raw compute bill may not yield the lowest cost per successful request or transaction.

## 1. How Does TCO Differ from Compute Price?

Compute price typically covers hourly vCPU/RAM charges, node container capacity, or function execution time. TCO includes all additional expenses required for the workload to run safely and meet business requirements.

A general model:

~~~text
Period TCO =
    Compute
  + Storage
  + Network and data transfer
  + Control plane and platform services
  + Licenses and software
  + Logging, monitoring, and tracing
  + Backups, DR, and reserve capacity
  + Security and compliance
  + Operations labor
  + Amortized migration and enablement
  + Estimated disruption or risk costs
  - Applicable discounts, credits, and benefits
~~~

Not every organization includes disruption costs in the same financial report. However, when making architectural decisions, factor in the impact of downtime, data loss, capacity limits, and vendor lock-in.

### 1.1. Defining the Comparison Scope

Before calculating, align on:

- Timeframe: monthly, annual, or a 3-year lifecycle.
- Workload: requests/sec, job count, data sizes, read/write ratios, and runtimes.
- SLOs: availability, p95/p99 latency, throughput, and error rates.
- Environments: production, staging, development, or all.
- Failure domains: single-zone vs. multi-zone, and whether a DR region is required.
- Security: encryption, identity, network isolation, auditing, and retention.
- Labor scope: infrastructure operations only, or including platform engineering and application support.
- How shared costs are allocated across multiple workloads.

Comparing a single-zone VM against multi-zone containers/serverless produces an unfair result. Likewise, an option with full backups and logging must not be compared against one that omits those requirements.

### 1.2. Measuring by Useful Units of Work

A low total bill does not guarantee efficiency if the system handles fewer requests or suffers high error rates. Supplement with metrics such as:

- Cost per successful request.
- Cost per completed job.
- Cost per transaction.
- Cost per GB processed.
- Cost per active user or workload unit.

Example:

~~~text
Cost per successful request =
    Period TCO / Completed successful requests in the period
~~~

When computing the denominator, exclude failed requests or retries that produce no business outcome. This surfaces the cost of retry storms, timeouts, and under-provisioned capacity.

## 2. Costs Common Across All Three Models

Certain costs exist regardless of whether an application runs on VMs, containers, or serverless.

| Cost Group | Components to Account For |
|---|---|
| Data | Databases, object storage, file storage, backups, and snapshots |
| Network | Load balancers/API gateways, NAT, private endpoints, egress, cross-zone, and cross-region transfer |
| Security | KMS/key management, secret managers, vulnerability scanning, WAF, and audits |
| Observability | Log ingestion/retention, metrics, tracing, alerting, and APM |
| Operations | On-call, incident response, patching, capacity planning, and cost management |
| Availability | Multi-zone, replicas, standby capacity, DR, and recovery drills |
| Software | OS, databases, runtimes, middleware, commercial licenses, and support |

Shared costs should be allocated using a fair driver, such as request count, stored GB, network bytes, CPU time, or actual consumption. Do not split evenly across all applications when usage varies dramatically.

## 3. TCO of the Virtual Machine Model

VMs provide virtualized machines with allocated vCPU, RAM, disks, and networking over time. The organization controls the OS, runtime, and most guest configuration.

### 3.1. VM Cost Components

- **Compute instances:** rates by machine type, size, operating system, region, and runtime.
- **Boot/data disks:** capacity, volume type, IOPS/throughput, and snapshots.
- **Network:** public IPs, load balancers, NAT, egress, and inter-zone/region transfer.
- **Licenses:** Windows, commercial databases, or installed machine software if applicable.
- **Availability:** spare VMs, multi-zone, standbys, and capacity reservations.
- **Operations:** OS patching, hardening, backup agents, monitoring agents, image builds, and incident handling.
- **Capacity waste:** allocated but unused vCPU/RAM, idle hours, and headroom.

### 3.2. When VMs Have a Cost Advantage

VMs generally fit well when:

- Workloads run continuously with relatively steady utilization.
- Applications require control over the OS, kernel, drivers, or specialized software.
- Long-lived workloads can leverage commitments/Reserved Instances/Savings Plans.
- Multiple processes can share machine resources without complex orchestration.
- Teams already have VM management skills and tooling.
- Workloads require system-level access or specialized machine configurations.

If a VM runs steadily near expected capacity, fixed capacity pricing can be efficient. Still, factor in spare capacity for failover, maintenance, and peaks.

### 3.3. Common Sources of Waste

- Provisioning VMs larger than real demand.
- Leaving dev/test machines running overnight or on weekends.
- Running many small VMs when workloads could be consolidated.
- Failing to delete unused disks, snapshots, or public IPs.
- Holding high capacity for brief peaks without scaling back afterward.
- Skipping commitments for sufficiently steady baselines.
- Using Spot for interruption-intolerant workloads, forcing repeated reruns.

### 3.4. VM Labor Costs

VMs typically require OS and machine lifecycle workflows:

- Updating packages, kernels, and security patches.
- Building, testing, and releasing machine images.
- Managing configurations, agents, certificates, and secrets.
- Monitoring disk space, filesystems, backups, and I/O.
- Handling configuration drift across machines.
- Managing autoscaling groups and load balancers.

Automation and immutable images reduce effort, yet require investment in pipelines and skills. Do not assume labor cost is zero simply because VMs are provisioned automatically.

## 4. TCO of the Container Model

Containers package applications and dependencies into images running on a runtime or orchestrator like Kubernetes. Containers often improve node utilization by packing multiple workloads onto shared infrastructure.

### 4.1. Container Cost Components

- **Worker nodes:** VMs or physical hosts running containers.
- **Control plane:** cluster or management fees if billed separately.
- **System capacity:** CPU/RAM reserved for kubelet, runtime, networking, monitoring, daemons, and system pods.
- **Container registry:** image storage, replication, scanning, and data transfer.
- **Storage:** persistent volumes, CSI, snapshots, and backups.
- **Network:** load balancers, ingress, service meshes, NAT, cross-node, and cross-zone traffic.
- **Observability:** logs, metrics, tracing, and retention.
- **Platform engineering:** cluster administration, upgrades, policies, RBAC, admission controls, and capacity.
- **Licenses/support:** commercial add-ons, service meshes, or enterprise platforms if used.

### 4.2. Bin Packing and Node Utilization

Containers cut costs when multiple workloads share nodes. Schedulers place pods using resource requests, limits, affinity, taints/tolerations, and other constraints.

Benefits depend on bin-packing efficiency:

- Small pods fill spare capacity slices on nodes.
- Workloads with complementary load patterns share capacity.
- Autoscalers add/remove nodes based on demand.
- Multiple services share ingress, logging, and control planes.

However, total pod CPU/RAM requests cannot consume 100% of node resources. Headroom must remain for the OS, kubelet, runtime, daemons, and system workloads. Setting requests too high wastes node capacity; setting them too low risks contention or OOMs.

### 4.3. Idle Cluster Costs

Even a small cluster carries baseline costs:

- Control plane or cluster management fees.
- Minimum nodes needed to sustain availability.
- Always-running system pods and daemons.
- Load balancers, disks, and logs.
- Unpackable capacity caused by CPU/RAM fragmentation.

Scale-to-zero for container workloads does not mean the entire cluster scales to zero. If nodes or control planes stay up continuously, baseline costs persist.

### 4.4. When Containers Have a Cost Advantage

Containers generally fit well when:

- Many services or workloads share one platform.
- Services need independent scaling.
- Teams want standardized runtimes and deployments.
- Workloads efficiently utilize shared node pools.
- Teams have Kubernetes/container platform operating capability.
- Portability across environments or clouds within compatibility limits is desired.

For a single small-load application without complex orchestration needs, control plane and operational overhead can make containers costlier than VMs.

### 4.5. Kubernetes Operational Overhead

Kubernetes delivers strong orchestration while adding operational duties:

- Upgrading clusters, node images, and add-ons.
- Managing ingress, CNI, CSI, DNS, and policies.
- Tuning requests/limits and autoscaling.
- Securing the API server, RBAC, secrets, and network policies.
- Tracking node pressure, pod evictions, and scheduling failures.
- Managing version compatibility and incidents.

TCO must include platform engineering and on-call labor. When a platform serves multiple apps, allocate control plane and platform labor costs across workloads by usage rather than charging one service for everything.

## 5. TCO of the Serverless Model

Serverless runs code or workloads on events without direct VM/node management. The provider manages underlying infrastructure; customers typically pay by requests, execution duration, memory, or capacity configuration.

Serverless takes several forms:

- Function as a Service (FaaS).
- Container/serverless compute billed by vCPU-second and GB-second.
- Managed jobs or tasks triggered on demand.
- Event-driven integration and workflow orchestration.

Not every service labeled serverless uses the same pricing model.

### 5.1. Serverless Cost Components

- **Invocations/requests:** number of calls or processed events.
- **Execution duration:** runtime of each invocation/task.
- **Memory/CPU allocation:** resources assigned per execution.
- **Concurrency:** simultaneous invocations and account/service limits.
- **Provisioned/minimum capacity:** cost of keeping instances/functions warm or minimum capacity if configured.
- **API gateway/event routing:** requests, events, rules, and workflow steps.
- **Storage/network:** logs, objects, databases, egress, and private networking.
- **Observability:** log volume, tracing, and metric cardinality.
- **Retries/timeouts:** repeat executions from errors or timeouts.
- **Operations:** event design, concurrency limits, quotas, cold starts, and dependencies.

### 5.2. When Serverless Has a Cost Advantage

Serverless generally fits well when:

- Loads are intermittent or have long idle gaps.
- Workloads run briefly per request or event.
- Scale-to-zero is acceptable.
- Low-level OS or runtime control is unnecessary.
- Traffic spikes/drops rapidly and capacity management needs to be minimized.
- Teams want to focus on application logic.

At very high, steady baseline traffic, total invocation/duration charges can surpass an efficiently utilized VM or container fleet. Benchmark and calculate using real request/job data.

### 5.3. Drivers That Inflate Serverless Costs

- Long-running functions or high memory allocations.
- Repeated retries triggered by failing dependencies.
- Always-on provisioned concurrency or minimum instances.
- Cold starts inflating durations or forcing extra pre-provisioned capacity.
- Large payloads, excessive API gateway calls, or chatty workflow steps.
- Overly verbose logging/tracing generating huge observability volumes.
- Egress, NAT, private networking, and cross-zone transfers.
- Excessive database connections spawned during scale-out.

Serverless eliminates machine management without eliminating operational work. Event design, idempotency, retries, observability, and concurrency caps still require engineering effort.

## 6. Comparing the Three Models Across Identical Criteria

| Criterion | VM | Container | Serverless |
|---|---|---|---|
| Primary billing unit | VM by time, disks, network | Nodes/cluster, control plane, storage, network | Requests, duration, memory/CPU, concurrency |
| Idle cost | Usually billed while VM runs | Minimum nodes/control plane may keep billing | Very low at scale-to-zero; supporting services still bill |
| Resource utilization | Depends on per-VM utilization | Can bin-pack multiple workloads on nodes | Provider allocates resources per execution model |
| Scaling | VM/group/autoscaler | Pod and node autoscalers | Automatic per event/request within limits |
| OS control | High | Custom images, tied to node/runtime | Lower, mostly provider-managed |
| Operations | Patching, images, VMs, and fleet | Clusters, nodes, schedulers, images, and policies | Events, functions, quotas, concurrency, and dependencies |
| Startup/cold start | Relatively long VM boot | Faster container starts than VMs, dependent on nodes/images | Possible cold starts or provisioned capacity |
| Long-running workloads | Usually well-suited | Well-suited | May hit duration caps or lose cost efficiency |
| Intermittent workloads | Requires scaling/shutoff to cut idle | Can scale workloads, though cluster has base cost | Usually fits well with scale-to-zero |
| Portability | OS/images movable, cloud-dependent | Images more portable across compatible environments | Tied to provider runtimes, triggers, and services |
| Operational complexity | Operating system administration | Orchestration platform administration | Event, quota, and integrated service management |

No model is cheapest in all cases. Utilization, idle time, workload partitioning, and labor costs typically decide the winner.

## 7. Modeling TCO on an Identical Workload

To compare fairly, construct a reference workload:

- 30 million requests per month.
- 150 ms average processing duration.
- 512 MiB reference serverless memory per request.
- ~11.6 requests/sec average load, peaking at 100 requests/sec.
- Identical managed database and backup requirements.
- 100 GB egress per month.
- Identical API entry point and SLOs.
- Production requires reserve capacity aligned with availability requirements.

The price figures below are purely hypothetical to illustrate the methodology. They are not pricing from AWS, Azure, Google Cloud, or any provider. Real rates depend on region, service type, OS, discounts, billing units, and date.

### 7.1. Hypothetical Price Assumptions Used in the Example

- Equivalent VM/node: 0.12 USD per hour.
- Month assumed to be 730 hours.
- Disk: 0.08 USD/GB-month.
- Egress: 0.09 USD/GB.
- Serverless execution: 0.0000167 USD/GB-second.
- Serverless requests: 0.20 USD per million invocations.
- API gateway: 1 USD per million requests.
- Operations labor rate equivalent: 40 USD/hour.

Managed database, backup, API gateway, and egress are held constant across all three options to highlight that non-compute services must be included.

### 7.2. VM Option

Assume 3 VMs running to satisfy baseline and spread across failure domains:

| Line Item | Calculation | Monthly Cost |
|---|---|---:|
| VM compute | 3 × 0.12 × 730 | 262.80 USD |
| Boot disks | 3 × 40 GB × 0.08 | 9.60 USD |
| Load balancer | Assumed | 25.00 USD |
| API gateway | 30 million requests | 30.00 USD |
| Managed database | Assumed | 90.00 USD |
| Backup | Assumed | 6.00 USD |
| Egress | 100 GB × 0.09 | 9.00 USD |
| Logging/monitoring | Assumed | 18.00 USD |
| Operations labor | 6 hours × 40 USD | 240.00 USD |
| Migration amortization | Assumed | 20.00 USD |
| **Total** |  | **710.40 USD** |

### 7.3. Container Option

Assume the workload runs on a dedicated cluster with 3 worker nodes equivalent to the VMs above:

| Line Item | Calculation | Monthly Cost |
|---|---|---:|
| Worker node compute | 3 × 0.12 × 730 | 262.80 USD |
| Managed control plane | Assumed | 73.00 USD |
| Persistent/boot disks | 3 × 40 GB × 0.08 | 9.60 USD |
| Load balancer | Assumed | 25.00 USD |
| API gateway | 30 million requests | 30.00 USD |
| Managed database | Assumed | 90.00 USD |
| Backup | Assumed | 6.00 USD |
| Egress | 100 GB × 0.09 | 9.00 USD |
| Registry/scanning/logging | Assumed | 24.00 USD |
| Platform operations labor | 5 hours × 40 USD | 200.00 USD |
| Migration amortization | Assumed | 30.00 USD |
| **Total** |  | **759.40 USD** |

In this single-workload dedicated-cluster example, control plane and operational fees push containers above VMs. If the cluster is shared across many apps, control plane, idle node, and platform labor costs distribute across workloads, making per-app TCO significantly lower.

### 7.4. Serverless Option

With 30 million requests, 150 ms per request, and 0.5 GB memory:

~~~text
GB-second = 30,000,000 × 0.15 × 0.5
          = 2,250,000 GB-seconds

Execution cost = 2,250,000 × 0.0000167
               = 37.575 USD

Request cost = 30 × 0.20
             = 6.00 USD
~~~

Assume added provisioned concurrency for the traffic slice needing steady latency:

| Line Item | Calculation | Monthly Cost |
|---|---|---:|
| Execution | 2,250,000 GB-seconds × 0.0000167 | 37.58 USD |
| Invocations | 30 million × 0.20 USD/million | 6.00 USD |
| Provisioned concurrency | Assumed | 20.00 USD |
| API gateway | 30 million requests | 30.00 USD |
| Managed database | Assumed | 90.00 USD |
| Backup | Assumed | 6.00 USD |
| Egress | 100 GB × 0.09 | 9.00 USD |
| Logs/traces | Assumed | 15.00 USD |
| Operations labor | 2 hours × 40 USD | 80.00 USD |
| Migration amortization | Assumed | 25.00 USD |
| **Total** |  | **318.58 USD** |

### 7.5. Comparing Illustrative Results

| Model | Monthly TCO | Cost per 1 Million Requests |
|---|---:|---:|
| VM | 710.40 USD | 23.68 USD |
| Dedicated container cluster | 759.40 USD | 25.31 USD |
| Serverless | 318.58 USD | 10.62 USD |

Under these assumptions, serverless costs less because executions are brief and scale with request count. Results cannot be applied mechanically to other workloads. If requests surge, durations lengthen, heavy provisioned concurrency is needed, or databases scale up, serverless costs rise. If a container cluster is shared across apps, allocated costs drop. If VMs run near full capacity continuously with commitments, VMs become much more competitive.

## 8. Break-Even Analysis

The break-even point depends on fixed versus variable cost components.

### 8.1. VMs and Containers

For VMs, compute costs scale with machine count and uptime. For containers, node costs follow a similar pattern, yet can be split across multiple workloads. Container break-even improves when:

- Enough workloads exist to utilize shared nodes.
- Resource requests/limits align closely with real demand.
- Cluster overhead spreads across multiple services.
- Platform engineering effort does not grow linearly with app count.
- Node utilization rises without causing contention.

For a single small workload, a dedicated cluster rarely achieves high enough utilization to offset control plane and operations overhead.

### 8.2. Serverless vs. Always-On Compute

General model:

~~~text
Serverless TCO =
    Fixed ancillary cost
  + Request count × Cost per request
  + Execution GB-seconds × Rate
  + Provisioned capacity
~~~

~~~text
VM/container TCO =
    Always-on capacity
  + Storage/network/platform overhead
  + Operations
~~~

When request volume is low or intermittent, serverless wins by avoiding full idle capacity charges. When requests are continuous, durations are long, or memory needs are high, variable charges can surpass well-utilized fixed capacity.

### 8.3. Variables That Shift the Break-Even Point

- Monthly request or job counts.
- Average duration and p95/p99 distributions.
- Memory/CPU allocations.
- Retry and timeout rates.
- Concurrency and provisioned capacity.
- Baseline load and idle duration.
- Node packing and utilization levels.
- Discounts/commitments and regional pricing.
- Network egress, gateways, and data transfer.
- Operations labor and platform complexity.

Never rely on average duration alone when a subset of requests runs much longer. Measure full duration distributions and payload sizes.

## 9. Hidden Costs and Commonly Missed Factors

### 9.1. Observability

Logs, metrics, and traces can become major expenses as traffic scales. Containers emit logs from nodes, sidecars, and system components. Serverless creates log streams across bursts of invocations and traces many spans. VMs retain agents and long-lived log volumes.

To control:

- Set retention per business and audit requirements.
- Eliminate duplicate or debug-level logs in production.
- Apply controlled trace sampling.
- Monitor metric cardinality.
- Tag logs and telemetry for cost allocation.

### 9.2. Network and Data Transfer

Multi-tier architectures introduce extra network hops:

- Containers via ingress, service meshes, and cross-node networking.
- Serverless via API gateways, NAT, private endpoints, and databases.
- VMs via load balancers, NAT, and inter-zone routes.

Placing compute close to databases lowers latency and transfer charges. However, never collapse everything into one zone if doing so lowers availability.

### 9.3. Licenses and Commercial Software

Licenses may bill per core, socket, VM, node, user, or usage tier. Moving from VMs to containers does not automatically cut licensing fees; some products bill per host/node, while others bill per vCPU or replica.

Before migrating, verify license terms, container usage rights, BYOL, OS images, database editions, and support contracts.

### 9.4. Security and Compliance

Security costs can include:

- Image scanning and vulnerability management.
- Runtime protection, EDR, and agents.
- KMS, key rotation, and secret managers.
- WAF, firewalls, policy engines, and audits.
- Data residency, encryption, and retention.
- Compliance assessments and audit evidence.

A cheaper compute model requiring many extra control layers can carry higher TCO. Conversely, managed services cut patching work while still requiring assessment of remaining customer security responsibilities.

### 9.5. Migration and Exit Costs

Migration may require:

- Rewriting bootstrap or build pipelines.
- Moving images and data.
- Refactoring sessions, files, and background jobs.
- Migrating monitoring, alerts, and deployments.
- Training teams.
- Running parallel environments during cutover.
- Keeping rollback paths and paying for two environments.

Exit costs also matter: leaving serverless platforms with proprietary events/APIs, transferring large datasets out of a region, or replacing Kubernetes platforms with custom operators can all be costly.

## 10. Impact of Availability and DR on TCO

You cannot compare the cost of a single VM against a multi-zone serverless service without normalizing availability targets.

Costs that rise with higher availability:

- VMs: extra instances in other zones, load balancers, disk replication, and reserve capacity.
- Containers: multi-zone node pools, HA control planes, extra replicas, and network transfer.
- Serverless: provisioned concurrency, regional deployments, event replication, database replicas, and quota/capacity planning.

Across all three models, DR may require backups, replication, recovery environments, capacity reservations, or warm standbys. Account for both steady-state costs and failover costs.

Compare under identical targets:

| Requirement | Questions to Quantify |
|---|---|
| Availability | How many failure domains and how many replicas? |
| RTO | Is pre-allocated capacity needed, or can it provision post-incident? |
| RPO | How much replication/backup cost is required? |
| Peak | Is capacity sufficient during spikes or losing a zone? |
| Recovery | How must images, disks, secrets, and quotas be held at the standby site? |

## 11. Selecting a Model by Workload Characteristics

| Workload Characteristic | VM | Container | Serverless |
|---|---|---|---|
| Steady 24/7 baseline | Often competitive | Strong when sharing nodes | Can be costly with continuous execution |
| Short burst loads | Needs autoscaling and headroom | Scales pods/nodes with startup delay | Usually fits well |
| Many microservices | Can multiply VMs and operations | Fits shared platforms well | Fits small services/events |
| Long-running jobs | Suitable | Suitable | May hit duration/cost limits |
| Intermittent event processing | Risks idle capacity | Scales workers | Usually fits well if triggers are supported |
| Custom OS/drivers needed | Suitable | Dependent on node/runtime | Usually constrained |
| Needs GPUs or accelerators | Wide instance choice | Supports accelerator node pools | Depends on specific serverless service |
| Team lacks orchestration platform | More familiar with VM skills | Can introduce heavy overhead | Cuts host admin, requires cloud/event skills |
| Deep runtime control needed | High | Medium to high | Lower |

This serves as initial guidance. Final choices must rely on benchmarks, SLOs, pricing calculators, and team capability.

## 12. TCO Modeling Workflow

1. **Define workload:** request rates, job counts, durations, payloads, read/write ratios, and seasonality.
2. **Define SLOs:** availability, latency, throughput, RPO/RTO, and security.
3. **Design equivalent options:** VM fleets, container platforms, and serverless services must all meet the same requirements.
4. **Calculate compute:** instance hours, node hours, GB-seconds, invocations, and provisioned capacity.
5. **Calculate storage/network:** disks, object storage, backups, egress, cross-zone, gateways, and NAT.
6. **Calculate platform:** control planes, registries, orchestration, managed integrations, and licenses.
7. **Calculate operations:** labor hours, on-call, patching, incidents, and platform engineering.
8. **Allocate shared costs:** databases, observability, security, and networks using sound drivers.
9. **Calculate migration and DR:** transition costs, dual-run, backups, replicas, and standbys.
10. **Model scenarios:** low load, normal, peak, growth, and failure.
11. **Normalize outputs:** cost per successful request/job and total TCO over the same period.
12. **Pilot and refine:** calibrate assumptions using real telemetry.

## 13. Sensitivity to Load and Scenarios

Never build only an average forecast. Use at least three scenarios:

| Scenario | Description | What to Watch |
|---|---|---|
| Low | Reduced load or many idle hours | Baseline costs, scale-to-zero, unused commitments |
| Expected | Normal load per forecast | Cost per request and utilization |
| Peak/growth | Heavy spikes or long-term growth | Scale-out, quotas, latency, egress, and variable costs |
| Failure/DR | Loss of a zone or primary site | Reserve capacity, replication, RTO, and DR costs |

Sensitive variables:

- Average and p95 function execution duration.
- Invocation and retry counts.
- Minimum node count and bin-packing ratio.
- VM idle hours.
- Discount/commitment utilization.
- Log cost per request.
- Inter-zone/region data transfer.
- Labor required as service or cluster count grows.

Sensitivity analysis reveals which variables affect TCO most. Focus optimization on large drivers instead of trimming minor invoice items.

## 14. Allocating Costs on Shared Platforms

Container platforms are often shared across teams; databases, API gateways, observability, and networking can also serve multiple workloads.

Allocation methods include:

- By CPU/memory requests or actual usage.
- By request or transaction count.
- By stored GB and transferred GB.
- By node count or namespace minimum capacity.
- By share of control plane or license consumption.
- By team/service owner via tags and labels.

Distinguish:

- **Direct cost:** tied directly to the workload.
- **Shared cost:** shared platform infrastructure costs.
- **Unallocated cost:** unowned items requiring investigation.

Do not allocate shared costs with static percentages if usage shifts sharply. Review allocation data periodically.

## 15. Common Mistakes When Comparing TCO

- Comparing only vCPU/hour prices while ignoring storage, network, and labor.
- Applying different workloads or SLOs to each option.
- Comparing multi-zone VMs with single-region serverless and concluding serverless is cheaper.
- Ignoring container control plane and node overhead.
- Assuming serverless costs nothing with zero invocations while gateways, databases, storage, or provisioned capacity keep running.
- Ignoring retries, timeouts, and duplicate executions.
- Ignoring per-core/node/host licensing.
- Ignoring platform team and on-call labor time.
- Failing to split shared clusters across multiple workloads.
- Ignoring migration, dual-run, and exit costs.
- Using one average utilization number to represent peaks and failures.
- Failing to normalize by successful requests/jobs.
- Treating illustrative prices as real quotes without checking regions and terms.

## 16. TCO Evaluation Checklist

**Workload and SLOs**

- [ ] Identical request/job mix and load levels across all three options.
- [ ] Low, average, peak, and seasonal data captured.
- [ ] Defined p95/p99 latency, availability, RPO, and RTO.
- [ ] Reserve capacity and multi-zone accounted for.

**Infrastructure Costs**

- [ ] Compute/instances/nodes/executions.
- [ ] Storage, snapshots, backups, and replication.
- [ ] Network, gateways, NAT, egress, and cross-zone.
- [ ] Control planes, registries, API gateways, and managed services.
- [ ] Licenses, support, and security tools.
- [ ] Logging, metrics, tracing, and retention.

**Organizational Costs**

- [ ] Build pipelines and migration.
- [ ] Patching, platform engineering, and on-call.
- [ ] Incident response and DR exercises.
- [ ] Training and ongoing skill maintenance.
- [ ] Shared cost allocation and cost ownership.
- [ ] Vendor lock-in, data egress, and exit costs.

**Outputs**

- [ ] Monthly and lifecycle TCO calculated.
- [ ] Cost per successful request/job calculated.
- [ ] Sensitivity analysis for low, normal, peak, and DR scenarios.
- [ ] Verified real pricing by provider/region/discounts.
- [ ] Benchmarked and validated SLOs before deciding.

## 17. Decision Principles

1. **Compare on equal terms:** same workload, SLOs, security, and failure domains.
2. **Account for full lifecycle:** compute, data, network, platform, people, migration, and DR.
3. **Normalize by successful work:** do not judge solely by total bill or compute rate.
4. **VMs suit steady loads and machine control needs:** especially with high utilization and commitment optimization.
5. **Containers win when platforms are shared efficiently:** sufficient workload density is needed to offset control plane and platform operations.
6. **Serverless fits intermittent loads and brief executions:** monitor invocations, duration, concurrency, and auxiliary services.
7. **Do not overlook hidden costs:** observability, licenses, security, on-call, and migration can flip rankings.
8. **Treat availability/DR as part of TCO:** reserve capacity and replication carry real costs.
9. **Model multiple scenarios:** low load, normal, peak, growth, and failure.
10. **Calibrate with real telemetry:** benchmarks and billing data must update assumptions.

VMs, containers, and serverless represent three ways to organize and consume compute capacity with distinct cost structures. VMs typically price capacity over time; containers add platform costs while letting multiple workloads share nodes; serverless shifts most compute charges to requests and execution duration. Only by bringing infrastructure, data, networking, operations, security, migration, and availability into a unified TCO model can an organization choose the option that best aligns with its load and business goals.
