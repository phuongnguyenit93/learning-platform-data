# Calculating Idle Resources, Stopped Machines, and Associated Resource Costs

## Context: Bills Can Still Rise When CPU Is Nearly Idle

A VM can use only 3% CPU for hours yet still incur compute charges for its provisioned duration. When stopping a VM, CPU/compute charges may stop or decrease depending on the platform and stopped state; however, boot volumes, data disks, snapshots, IP addresses, load balancers, NAT gateways, logs, backups, licenses, or capacity commitments can continue accruing fees. A Kubernetes cluster may run few pods while still keeping many standby nodes. A rarely invoked serverless function may incur no execution-time compute charges, yet provisioned concurrency or minimum instances still create baseline costs.

Therefore, compute cost optimization must look at every resource provisioned to serve the workload, not just actively consumed CPU and RAM. You must distinguish **idle resources**, **stopped machines**, **deleted machines**, and **persisting auxiliary resources**, then determine which costs can be reduced without impacting availability, RTO/RPO, security, or user experience.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this topic helps engineers read bills across the resource lifecycle, detect charges incurred with no active workload, design start/stop schedules, manage attached storage and networking, and evaluate long-term commitments.

## 1. Cost Composition of a Compute Workload

Compute costs typically consist of multiple components:

| Cost Group | Examples | Can Charges Continue When VM Stops? |
|---|---|---|
| Compute capacity | vCPU, RAM, GPU, instance running time | Usually stops or drops in appropriate deallocated/stopped states; depends on service and state |
| License / software | Windows, commercial databases, security software, OS subscriptions | May continue billing per instance, core, host, or contract |
| Block storage | Boot disks, data volumes, provisioned IOPS/throughput | Usually continues billing while volumes exist |
| Snapshot / backup | Volume snapshots, backup vaults, retention copies | Usually billed by stored capacity, copy count, or tier |
| Network | Public IPs, NAT gateways, load balancers, firewalls, private endpoints, data transfer | Many charges persist independently of VM state |
| Observability | Log ingestion, metric retention, traces, monitoring agent services | Can continue accruing while logs/metrics are sent and stored |
| Commitment | Reserved capacity, savings plans, committed use, dedicated hosts | Payment obligations may continue even when workloads do not run |
| Orchestration | Kubernetes control plane, node pools, registries, service mesh | Some components carry separate fees or create baseline costs |

There is no single pricing table across all clouds. Billing units, stop-billing conditions, and state names vary by provider, region, instance type, operating system, license, and contract. Verify pricing and billing meters for the exact service in use.

### 1.1. Actual Cost Differs from List Price

Hourly or GiB-month list prices are only one part. Invoices can be affected by:

- Region, availability zone, and resource type.
- Operating system, licenses, CPU/GPU architecture, and instance type.
- On-demand, spot/preemptible, reserved capacity, or commitments.
- Minimum billing durations, rounding units, and billing schedules.
- Storage capacity, IOPS, throughput, and storage class.
- Intra-zone, inter-zone, inter-region, and Internet egress data transfer.
- Discounts, credits, taxes, support plans, and marketplace fees.

When comparing two architectures, use the same cost scope and load assumptions. For instance, comparing VMs to serverless must include load balancers, databases, logs, networking, and warm capacity costs if applicable.

## 2. Idle Resources and Idle Costs

A resource is considered idle when it is provisioned but produces little or no useful work over a period. Idle does not necessarily mean zero CPU usage: a VM may run agents, health checks, cron jobs, or background daemons even with zero application requests.

Common forms of idle:

- Production VMs running 24/7 while traffic concentrates in a few hours per day.
- Dev/test or demo machines not turned off after business hours.
- Instances sized too large for actual workloads.
- Kubernetes nodes with ample allocatable CPU/RAM yet low pod utilization.
- GPU instances held ready while jobs do not run continuously.
- Standby replicas with low utilization kept to meet RTO.
- Staging environments running continuously even though only needed during test windows.

### 2.1. Idle Utilization vs. Billed Time

For example, an 8-vCPU VM runs 730 hours per month at 5% average CPU. If the compute price is 0.40 USD/hour, compute cost is still approximately:

\[
730\times0.40=292\text{ USD/month}
\]

5% CPU usage does not mean the bill only charges 5% of the price. Under instance-hour billing, users pay for provisioned capacity during billable time. Some services bill by consumption or per second; check the actual meter.

### 2.2. Measuring Meaningful Idle

Do not conclude a VM is over-provisioned solely from low average CPU. Inspect:

- CPU p50/p95/p99, peaks, and run queues.
- Memory working set, available memory, swap, and OOM history.
- Network throughput, connection counts, and request rates.
- Disk IOPS, throughput, latency, and queue depth.
- Application throughput, latency, error rates, and queue backlogs.
- Scale-out time, warm-up time, and availability requirements.
- Batch schedules, seasonality, and rare peaks.

A machine with low CPU but near-full RAM or high disk I/O may still be heavily utilized. Conversely, a machine with persistently low CPU/RAM over weeks and no standby role is a candidate for rightsizing or scheduling.

### 2.3. Intentional Idle vs. Wasteful Idle

Some idle capacity is retained intentionally:

- HA replicas to survive node/zone failures.
- Warm standbys to achieve tight RTOs.
- Headroom to absorb bursts or autoscaling delays.
- Pre-allocated GPU/CPU capacity for deadline-bound jobs.
- Bastion hosts, monitoring, or security appliances requiring continuous availability.

Do not delete reserve capacity solely because of low utilization. Cross-check failure scenarios, RTO/RPO, peak demand, and downtime cost. Only idle capacity lacking an owner, purpose, or exceeding defined headroom should be targeted first for optimization.

## 3. VM States and Billing Impact

Platforms expose multiple lifecycle states. Names and billing behavior are not identical across providers.

| Conceptual State | Meaning | Compute Charge | Associated Resources |
|---|---|---|---|
| Running | VM is provisioned and executing | Usually billed via compute meter | Disks, IPs, network, monitoring, and licenses may bill separately |
| Stopped / powered off | Guest OS shut down, though instance may remain allocated | Some platforms still charge compute or partial capacity | Disks and many auxiliary resources keep billing |
| Stopped / deallocated | Compute capacity released from host per provider semantics | Usually stops instance compute billing; verify specific service | Disks, snapshots, IPs, LBs, NAT, backups, commitments may still bill |
| Suspended / hibernated | RAM or VM state saved to resume | May have specific billing; saved-state storage may be billed | Disks/snapshots and auxiliary resources may still bill |
| Terminated / deleted | Instance resource deleted | Instance compute meter ends per policy | Volumes, snapshots, IPs, NICs, backups, logs, or commitments may persist |

### 3.1. Stopping Inside the Guest OS Differs from Control-Plane Deallocation

A shutdown command inside Linux/Windows usually tells the guest OS to power off. Depending on the platform, the instance may enter a stopped state while retaining host allocation or auto-deallocate. On some services, stopping from the portal/API releases compute allocation; on others, stop and deallocate are two separate actions.

Do not infer billing status just because the console displays "Stopped". Inspect detailed state, billing documentation, and usage meters. If your goal is halting compute charges, confirm the instance reaches the provider's non-billable compute state.

### 3.2. What Can Be Lost Upon Deallocation?

When releasing compute, certain attributes can change:

- Physical host or placement may change on restart.
- Dynamic/public IPs may receive new addresses if static IPs are not retained.
- Local/ephemeral disks may be wiped.
- RAM and process state are not preserved without hibernation.
- Boot, bootstrap, and cache warm-up time recur on startup.
- Instance type or GPU quota/capacity may be unavailable when restarting.

Before automating stop/deallocate, persist important data to durable volumes or storage services, verify static IPs/DNS, confirm workloads restart cleanly, and define who is authorized to power machines back on.

### 3.3. Deleting a VM Does Not Guarantee Deleting All Resources

Many systems allow retaining boot disks, data disks, NICs, IPs, or snapshots upon instance deletion. This helps during recovery or VM recreation, yet easily leaves orphaned resources. Termination workflows must specify which resources are kept, their owner, retention period, and deletion conditions.

## 4. Storage Keeps Billing When Machines Stop

Storage typically has an independent lifecycle from VMs. When an instance stops or is deleted, volumes persist until properly detached/deleted. This is one of the most common reasons bills stay high after "turning off machines".

### 4.1. Boot Volumes and Data Volumes

Block storage costs may depend on:

- Provisioned capacity (GiB-month), not just written bytes.
- Volume type or storage tier.
- Provisioned IOPS/throughput above baseline.
- Service minimum sizes or rounding units.
- Snapshots, replication, and cross-region copies.

For example, a VM has a 100 GiB boot disk and a 500 GiB data disk. If the VM is deallocated while keeping both volumes, storage costs continue for their full capacity and performance tier. Reducing vCPUs or stopping the VM does not automatically shrink volume capacity.

### 4.2. Snapshots and Backups

Snapshots may be billed by stored snapshot data size, copy count, tier, region, or copy/restore operations. Some services use incremental snapshots while others bill differently; do not assume every snapshot only stores changed blocks.

Common cost sources:

- Old snapshots left after VMs or volumes were deleted.
- Backup policies retaining more recovery points than required.
- Cross-region backup copies.
- Backup vaults with management fees or minimum retention periods.
- Restore tests leaving temporary volumes/VMs behind after testing.

Do not delete backups just to cut bills without verifying retention, legal holds, RPO/RTO, and recoverability. Assign lifecycle policies and owners to every backup group.

### 4.3. Local/Ephemeral Storage

Local NVMe or ephemeral disks are typically tied to the host/instance lifecycle and may be lost on stop/deallocate, termination, or migration depending on the service. Even without a separate storage line item, local storage cost may be baked into the instance price. If workloads need persistent data, move it to durable block/file/object storage or databases.

## 5. Associated Networking and IP Addresses

A VM may not be running while network components remain provisioned and independently billed.

### 5.1. Public IPs and Static Addresses

Public IPv4, static IPs, or elastic IPs may incur fees based on retention duration, attachment state, or provider policy. Some platforms charge even for attached addresses; others price attached vs. unattached IPs differently. Rates and conditions vary by region and date.

When stopping/deallocating or deleting a VM, check:

- Is the IP retained or automatically released?
- Do DNS records point to the old IP?
- Is the static IP still needed for allowlists, callbacks, or partners?
- Can unattached IPs be reclaimed?

Do not release an IP solely to save money if the system requires a fixed address. Consider private connectivity, load balancer endpoints, or DNS-based routing instead if suitable.

### 5.2. NAT Gateways, Firewalls, and Private Endpoints

NAT gateways, managed firewalls, VPN gateways, and some private endpoints incur hourly, capacity, or data-processed charges. If a VM stops while the NAT gateway still serves other workloads, charges continue. If a NAT was created solely for a retired dev/test environment, consider removing it or using a different network design.

Before deleting NATs/firewalls, inspect route tables and all dependent workloads. A cost-cutting change can break package update egress, API calls, log shipping, or external integrations.

### 5.3. Load Balancers and Health Checks

Load balancers often carry charges for uptime, capacity units, rules, connections, or processed bytes depending on the provider. When backend VMs stop, the load balancer may remain provisioned and keep billing. Continuous health checks also generate requests and logs.

If an environment is no longer in use, verify DNS, listeners, target groups, WAF policies, certificates, and clients before deleting the load balancer. If an HA endpoint must remain active, the load balancer charge is an intentional baseline cost.

### 5.4. Data Transfer and Inter-Zone/Region Traffic

Network costs can stem from:

- Internet egress.
- Traffic across availability zones.
- Traffic across regions or cloud providers.
- NAT processing or gateway data processing.
- Traffic via CDN, private links, or interconnects.
- Cross-zone load balancing and replication.

Idle VMs may not produce much egress, yet database replicas, backups, logs, or replication still transfer data. Examine byte transfers by source/destination, not just total VM network throughput.

## 6. Auxiliary Resources and Baseline Costs

### 6.1. Monitoring, Logging, and Security Agents

Agents on VMs can emit metrics, logs, traces, inventory, and security telemetry even with zero application traffic. Costs may scale with host count, ingest volume, retention, query count, or stored size.

To cut costs without losing observability:

- Drop unnecessary debug or duplicate logs.
- Set distinct retention periods for operational, audit, and security logs.
- Reduce metric cardinality and avoid labels with continuously changing values.
- Use policy-based trace sampling while keeping 100% of critical error traces if supported.
- Turn off telemetry for deleted environments once required evidence is archived.

Do not disable production audit/security logging just to save money. Optimize volume, retention, and sampling according to security requirements.

### 6.2. Licenses and Commercial Software

Some images bundle licenses into the VM price; others use BYOL (Bring Your Own License), per-core/socket/host licensing, or separate subscriptions. Licensing costs may depend on allocated vCPUs, host type, or subscription duration, and do not necessarily drop immediately when the guest OS powers off.

When stopping or resizing, check license terms, license mobility, minimum core rules, and marketplace contracts. Do not assume deleting a VM automatically terminates every license or subscription obligation.

### 6.3. Orchestration and Control Plane

Kubernetes clusters may have separate control plane/management fees, alongside nodes, load balancers, persistent volumes, NAT, registries, logs, and service meshes. An empty cluster can still generate bills if the control plane or auxiliary resources persist.

Components such as autoscalers, controllers, minimum node pools, daemonsets, and system pods create baseline consumption. Separate essential cluster operating overhead from capacity retained due to overly high settings.

### 6.4. Recovery and Redundancy Costs

Warm standbys, backups, replication, secondary regions, and reserved capacity may see little daily traffic yet form part of the HA/DR design. Include them in the cost model as resilience costs, and weigh them against potential losses without redundancy.

A standby replica handling zero traffic still holds value when fast failover is required. The right question is whether the redundancy level matches criticality, RTO/RPO, and risk.

## 7. Idle Costs in Containers and Kubernetes

Containers do not automatically eliminate compute costs. Costs depend on underlying nodes or compute services, minimum replica counts, requests/limits, node uptime, and supporting services.

### 7.1. Node Capacity and Pod Utilization

A node may be provisioned with 16 vCPUs and 64 GiB RAM while running only a few small pods. While the node stays in the node pool, compute charges typically continue for its allocated duration. The scheduler places pods based on resource requests and constraints; inflated requests can make a node appear "full" despite low actual usage, prompting the autoscaler to add more nodes.

Common sources of waste:

- Pod requests set higher than steady usage and actual peaks.
- Large fixed replica counts despite hourly traffic swings.
- Node pool minimum sizes higher than needed.
- DaemonSets or system workloads consuming capacity on every node.
- Pending pods due to affinity, taints, topology, or missing specific resource types.
- Nodes blocked from scale-in by PDBs, local storage, or non-evictable workloads.

Rightsizing must examine requests, limits, usage, and peaks. Cutting requests too aggressively increases packing density at the risk of contention, throttling, or OOMs. Test workloads and maintain headroom for node failures and rolling updates.

### 7.2. Autoscaling and Scale-to-Zero

Cluster autoscalers or node auto-provisioners can remove nodes as demand drops, yet may keep a minimum node count for availability or startup latency. Horizontal Pod Autoscalers can shrink replicas without freeing nodes if other pods remain scheduled there or the node pool enforces a minimum.

Scale-to-zero can cut compute spend during zero traffic, but evaluate:

- Node/pod startup time and image pull duration.
- Cold starts and cache warm-up time.
- Connections to databases, secret managers, and dependencies.
- Pod disruption, persistent volumes, and local state.
- First-request latency targets after idle periods.
- Ongoing control plane, LB, IP, storage, and logging costs.

For latency-sensitive workloads, keeping one replica or minimum node can be appropriate. For batch jobs or dev/test environments, scale-to-zero is easier to adopt.

### 7.3. Bin Packing and Node Pool Grouping

Placing compatible workloads on right-sized nodes improves utilization and lowers node counts. However, packing everything onto fewer nodes widens the blast radius on node failure and risks noisy neighbors. Balance bin packing against topology spread, anti-affinity, isolation, GPU/CPU families, and security boundaries.

Dedicated node pools for GPUs or memory-optimized workloads may cost more per node while avoiding paying for expensive resources on workloads that do not need them. Taints/tolerations and node affinity steer workloads to the right pools; empty nodes should scale in or be removed per policy.

## 8. Idle Costs in Serverless

Serverless typically charges per invocation, execution duration, allocated memory/CPU, request count, or provisioned resources. With zero invocations, execution compute fees may be tiny or zero in pay-per-use models, but that does not mean the entire architecture costs nothing.

Charges that can persist:

- Provisioned concurrency, minimum instances, or always-on containers.
- API gateways, load balancers, private endpoints, and NAT.
- Queues, event buses, databases, caches, or storage.
- Logs, traces, metrics, secrets, and key management.
- Workflow orchestration, schedulers, and state machines.
- Network egress or data processing.

### 8.1. Provisioned Concurrency and Warm Capacity

Provisioned concurrency or minimum instances keep execution environments ready to reduce cold starts. This capacity may be billed for the duration it is held, even under sparse requests. Measure cold start rates, latency targets, and traffic patterns to size warm capacity.

For time-of-day workloads, schedule provisioned capacity up and down. For unpredictable spikes, weigh warm-capacity cost against cold-start latency and timeout rates.

### 8.2. Comparing Serverless with VMs

VMs can be more economical when load is steady and utilization stays high most of the time; serverless can fit sparse, bursty, or unpredictable workloads. Compare based on goodput and full-architecture cost, including gateways, databases, logging, egress, and minimum capacity.

A short-running function that hammers a database can drive database costs up. High-concurrency serverless services can create connection bursts to databases; plan for connection pooling/proxies or concurrency caps.

## 9. Commitments, Reservations, and Non-Running Machines

Cloud providers offer discounts for term usage commitments or pre-reserved capacity, commonly named reserved instances, savings plans, committed use discounts, or dedicated host reservations.

Key point: **payment commitments and VM runtime state are separate**. Once an organization commits to a spend level or capacity, payment obligations can continue even if VMs are stopped or workloads under-consume. Stopping a VM does not automatically cancel a reservation or commitment.

### 9.1. Distinguishing Reservations and Usage

- Reservations may guarantee capacity or lower rates for eligible usage.
- Savings/committed spend plans apply discounts to eligible compute spend within a period.
- Dedicated host reservations may bill by host capacity and term.
- Spot/preemptible offers lower prices with reclamation risk and does not fit every workload.

Names, eligibility, and mechanics differ across providers. Read contracts and billing reports to distinguish usage, commitments, and unused commitment.

### 9.2. Risks of Over-Sizing Commitments

If commitments are sized to current usage yet workloads shrink, architectures change, or services migrate to serverless, the organization may pay for unused commitments. If commitments lack flexibility across family, region, platform, or OS, rightsizing may fail to utilize the discount.

Before committing:

1. Analyze historical usage long enough to capture seasonality and trends.
2. Separate steady baseline from peaks and temporary workloads.
3. Verify scope, family/region/OS rules, and flexibility.
4. Model costs if usage falls below forecast.
5. Leave part of demand on on-demand/spot if flexibility is needed.
6. Periodically review commitment utilization and coverage.

## 10. Formulas for Idle and Stopped Machine Costs

A simple estimation model for a VM workload:

```text
monthly_total_cost = compute_cost
                   + storage_cost
                   + snapshot_backup_cost
                   + public_ip_cost
                   + network_gateway_cost
                   + load_balancer_cost
                   + monitoring_logging_cost
                   + license_cost
                   + commitment_cost_not_covered_by_usage
```

Compute cost can be estimated as:

\[
C_{compute}=N_{instances}\times H_{billable}\times P_{hour}
\]

Where `H_billable` is the actual billed hours per provider state and policy—do not assume it equals VM existence time. Storage can be estimated as:

\[
C_{storage}=\sum_i Capacity_i\times P_{GiB-month,i}
\]

If storage adds IOPS, throughput, request, or snapshot charges, add those meters separately. Public IPs, NAT, LBs, and logs each follow their own billing formulas.

### 10.1. Comparing Running, Deallocated, and Deleted

Hypothetical illustrative example:

- VM: 0.40 USD/hour.
- Boot/data disks: 600 GiB total at 0.08 USD/GiB-month.
- Public IP: 0.005 USD/hour.
- Load balancer allocated to workload: 25 USD/month.
- Snapshots/backups: 12 USD/month.
- Assume 730 hours per month.

| State | Compute | Disk | IP | LB | Backup | Estimated Total |
|---|---:|---:|---:|---:|---:|---:|
| Running full month | 292.00 | 48.00 | 3.65 | 25.00 | 12.00 | 380.65 USD |
| Deallocated full month, keeping disk/IP/LB/backup | 0.00 | 48.00 | 3.65 | 25.00 | 12.00 | 88.65 USD |
| Deleted, removed disk/IP/LB, keeping backup | 0.00 | 0.00 | 0.00 | 0.00 | 12.00 | 12.00 USD |

Prices are entirely hypothetical to illustrate decomposition. In reality, public IPs may vary by attachment state, disks may bill by tier/IOPS, load balancers may be shared across workloads, and backups may bill by changed blocks. If commitments exist, cash outlay may not drop as shown because commitment obligations remain.

### 10.2. Scheduled On/Off Costs

If a dev/test environment only runs 10 hours/day across 22 workdays, billable compute time can drop from 730 hours to 220 hours/month assuming stop/deallocate genuinely halts the compute meter:

\[
Saving_{compute}=1-\frac{220}{730}\approx69.9\%
\]

This is theoretical compute savings before accounting for startup time, licenses, storage, IPs, gateways, LBs, and fixed charges. On/off schedules must include prep windows, automated test runs, and user access hours.

## 11. Allocating Costs for Idle Resources

To identify who owns idle costs, attach owner, application, environment, and purpose metadata to resources. Without metadata, FinOps teams struggle to separate valid reserve capacity from forgotten resources.

### 11.1. Tags/Labels and Cost Allocation

Commonly used attributes:

- `owner`: responsible team or individual.
- `application` / `service`: system using the resource.
- `environment`: production, staging, dev, test, or sandbox.
- `cost-center` / `business-unit`: billing entity.
- `lifecycle`: temporary, persistent, standby, or scheduled.
- `expires-at`: review/deletion date for temporary resources.
- `criticality`: importance level or service tier.

Tags should be enforced consistently via IaC and policy; resources like data transfer, shared NAT, or load balancers may need allocation rules instead of direct tags. Never place secrets, personal data, or sensitive information in tags.

### 11.2. Shared Resource Costs

One load balancer or NAT gateway may serve multiple applications. Allocate by:

- Share of actual bytes/requests.
- Connection counts or usage duration.
- Target/endpoint counts or reserved capacity shares.
- Workload weights under an agreed rule.

Publish the allocation methodology and retain a platform share if jointly operated. Poor allocation creates perverse incentives, such as charging one team for another team's traffic.

### 11.3. Idle Cost per Application

You can estimate compute cost associated with idle time by combining resource rates with intervals lacking useful work. However, utilization is not a billing meter, so this is a governance metric rather than an official invoice item.

For example, a 4-vCPU VM costs 0.20 USD/hour, runs 730 hours/month, and is assessed as idle 70% of the time. Estimated compute cost tied to idle time:

\[
C_{idle}=0.20\times730\times0.70=102.20\text{ USD}
\]

This number helps prioritize reviews. It does not mean all 102.20 USD can be saved: part of idle time may be headroom, HA, or capacity needed for peaks. Test rightsizing/scheduling and measure impact before claiming savings.

## 12. Detecting Orphaned and Forgotten Resources

Orphaned resources are resources that still exist without an active workload or clear owner. They often appear after incomplete VM/cluster deletions, finished tests, or manually created environments.

Items to audit:

- Disks/volumes unattached to any VM.
- Snapshots and backups lacking owners or exceeding retention.
- Unused public IPs/NICs.
- Load balancers, target groups, NAT gateways, or firewall rules from deleted environments.
- Unused GPU/VM reservations, dedicated hosts, or capacity commitments.
- Kubernetes node pools, persistent volumes, load balancer services, or registry artifacts with no active workloads.
- Log groups, trace stores, metric workspaces, and alert rules from ended projects.
- Static IPs, DNS zones/records, and certificates with no active endpoints.

### 12.1. Safe Cleanup Workflow

1. Locate resources lacking owners/tags or links to active workloads.
2. Inspect usage metrics, attachments, access logs, and dependencies over a representative window.
3. Contact the owner or platform team to confirm purpose.
4. Check retention, backups, legal holds, DNS, allowlists, and recoverability.
5. Mark as pending deletion with a notification grace period if policy requires.
6. Snapshot/export data worth keeping and verify restore capability.
7. Delete in dependency order and monitor for post-change errors.
8. Update inventory and record before/after costs.

Do not auto-delete a volume just because it is unattached; it could hold standby data or await failover. Automation should include allowlists/denylists, owner notifications, grace periods, and approval gates for stateful resources.

## 13. Measures to Reduce Idle Costs

### 13.1. Rightsizing

Select VM/instance types matching actual CPU, memory, network, storage, and GPU demand. Lower vCPU/RAM or switch families if workloads do not need current specs.

Before resizing:

- Analyze peaks and percentiles over a representative period.
- Check CPU steal/throttling, memory pressure, swap, and OOMs.
- Measure disk IOPS/throughput, network, and GPU if present.
- Check per-core/host licensing rules.
- Verify downtime, reboots, IPs, storage attachments, and compatibility.
- Benchmark post-resize and retain a rollback path.

Do not rightsize on average CPU alone. Machines with brief but critical peaks or fault-tolerance roles may need capacity above the average.

### 13.2. Scheduling and Auto-Stop

Dev/test environments, build agents, or demos often have predictable schedules. Automatically start before work hours and stop/deallocate afterward while notifying owners.

Scheduling rules need:

- Explicit time zones and holidays.
- Exclusions for production, databases, or SLA-bound workloads.
- Checks for running jobs, queue backlogs, and maintenance windows before stopping.
- Alerts if stop/start fails.
- Static IP retention or DNS updates if endpoints change.
- Post-start verification: health, agents, mounts, secrets, and application readiness.

Auto-stop must not be applied to HA/DR VMs or always-on endpoints without impact assessment.

### 13.3. Autoscaling and Scale-to-Zero

Autoscaling matches capacity to demand. Scale-in trims idle compute while scale-out preserves load handling. Set sensible min/max bounds, cooldowns, stabilization windows, and metric-driven policies.

For batch or event-driven workloads, scale-to-zero can fit well. For latency-sensitive APIs, keep baseline replicas or warm pools/provisioned capacity. Weigh idle costs against cold-start penalties and capacity-holding fees.

### 13.4. Decoupling Compute Schedules from Storage Lifecycles

Stopping a VM does not mean deleting disks. You can keep data disks while temporarily deleting compute, or snapshot data and delete volumes when fast access is unnecessary. Choose based on recovery time and retrieval/restore costs.

For instance, test environments can keep images and periodic snapshots, creating VMs only on demand. However, rebuilding VMs from images/snapshots takes time and may incur restore, data transfer, or bootstrapping costs.

### 13.5. Optimizing Networking and Shared Services

- Remove unused load balancers/NAT/private endpoints after verifying dependencies.
- Optimize placement to lower cross-zone data transfer where HA permits.
- Use caches/CDNs when they reduce overall egress or origin load.
- Choose NAT/egress architectures aligned with traffic patterns and security rules.
- Inspect log/data transfer from agents running on idle machines.

Do not collapse workloads into one zone solely to trim cross-zone fees if doing so breaks availability objectives. Quantify savings against added risk.

### 13.6. Managing Commitments

Buy commitments for steady baselines rather than brief peaks. Track commitment coverage and utilization; adjust portfolios when switching instance families, regions, OS, or architectures. Report unused commitments separately to avoid confusing them with idle VMs.

## 14. Calculating Real Savings and Post-Optimization Tracking

Savings are not just before list price minus after list price. Compare actual costs over identical scopes, time windows, and service levels.

```text
gross_saving = baseline_cost - optimized_cost
net_saving = gross_saving - migration_cost - operational_cost_change

cost_per_good_request = total_workload_cost / successful_requests
cost_per_job = total_workload_cost / jobs_completed_successfully
```

During optimization, simultaneously track:

- Total cost and cost by service/environment/owner.
- Running, stopped/deallocated, and commitment compute costs.
- Storage, snapshots, backups, IPs, NAT, LBs, and data transfer.
- Utilization, capacity headroom, latency, error rates, and availability.
- Cost per successful request/job.
- Ratio of unowned and orphaned resources.

A change only qualifies as good optimization if it cuts costs while maintaining SLOs, post-failure capacity, security, and recovery targets. If saving 20% on compute doubles RTO or spikes production errors, re-evaluate the trade-off.

## 15. Practical Example: Scheduled Dev/Test Environment

Suppose a team has 5 dev/test VMs. Each VM has a hypothetical compute price of 0.25 USD/hour running continuously for 730 hours/month. Each VM has a 200 GiB disk at 0.08 USD/GiB-month. A shared load balancer allocates 30 USD/month, and public IPs cost a hypothetical 0.005 USD/hour per VM.

### 15.1. Pre-Optimization Cost

| Component | Calculation | Monthly Cost |
|---|---|---:|
| Compute | 5 × 730 × 0.25 USD | 912.50 USD |
| Disk | 5 × 200 × 0.08 USD | 80.00 USD |
| Public IP | 5 × 730 × 0.005 USD | 18.25 USD |
| Load balancer | Hypothetical allocation | 30.00 USD |
| Total | | **1,040.75 USD** |

### 15.2. Scheduled Execution

If each VM only needs 10 hours/day for 22 workdays, compute time drops to 220 hours/month:

| Component | Calculation | Monthly Cost |
|---|---|---:|
| Compute | 5 × 220 × 0.25 USD | 275.00 USD |
| Disk | Unchanged 5 × 200 × 0.08 USD | 80.00 USD |
| Public IP | Assumed retained continuously | 18.25 USD |
| Load balancer | Remains provisioned | 30.00 USD |
| Total | | **403.25 USD** |

Hypothetical savings are 637.50 USD/month, roughly 61.3% of total scoped cost. If deallocation releases public IPs, IP fees can drop further, though DNS/allowlists must be handled upon restart. Removing the load balancer off-hours saves more but requires accounting for recreation time and access.

### 15.3. Operational Conditions

- Confirm no automated tests or long jobs run after hours.
- Notify developers prior to stopping.
- Stop VMs in proper order and verify filesystem/application shutdown.
- Retain disks if data is needed; use snapshots if environments are reproducible.
- Start early enough before work hours to finish booting, patch checks, and health checks.
- Verify IPs, DNS, VPN, secrets, agents, and database connectivity after startup.
- Provide a time-bounded temporary opt-out mechanism for teams running extended tests.

This example does not represent every pricing schedule. Disk, IP, LB, and license costs vary by provider; reconcile real savings against billing exports after several cycles.

## 16. Cost Dashboards and Alerts

A FinOps compute dashboard should separate spend by state and resource type:

| View | Recommended Metrics | Question Answered |
|---|---|---|
| Running compute | Instance-hours, vCPU-hours, GPU-hours, cost by family | Which workloads drive most compute spend? |
| Idle compute | Usage percentiles, billed hours, idle estimates | Which machines stay provisioned long with little work? |
| Stopped/deallocated | VM count, surviving disks/IPs/LBs, auxiliary costs | Once machines stop, what still accrues charges? |
| Orphaned resources | Unattached disks, unused IPs, idle LB/NAT, old snapshots | Which resources lack an owner/workload? |
| Commitments | Coverage, utilization, unused commitment | Are we paying for unused commitments? |
| Network/storage | Egress, cross-zone, IOPS, snapshot/backup growth | What drives auxiliary cost increases? |
| Unit economics | Cost/request, cost/job, cost/tenant | Are costs growing faster than delivered value? |

### 16.1. Useful Alerts

- Dev/test VMs running outside approved schedules.
- Instances idle beyond thresholds for multiple days without a standby tag.
- Unattached disks or unassociated public IPs.
- Snapshots/backups exceeding retention or growing abnormally.
- Load balancers/NAT gateways incurring fees with zero traffic.
- Low commitment utilization or sharp coverage shifts.
- Spend by service/cost center exceeding budget or spiking unexpectedly.
- Resources missing owner, environment, or expiration date.

Alerts should include resource ID, owner, cost estimate, idle duration, and remediation steps. Never auto-delete stateful or HA resources solely on an idle threshold.

## 17. Guardrails and Resource Lifecycle Policies

To curb forgotten costs, place guardrails in creation and deletion workflows:

- Require owner, application, environment, and cost center tags.
- Mandate `expires-at` for temporary sandbox/test resources.
- Auto-stop non-production environments on agreed schedules.
- Cap instance types/GPUs or quotas by team and environment.
- Manage lifecycles via IaC to avoid unmanaged manual resources.
- Alert before deleting orphaned disks/snapshots/IPs.
- Enforce retention policies for logs, snapshots, and backups by data class.
- Monitor commitment utilization and require review before additional purchases.
- Reconcile cloud inventory periodically against CMDB/service catalogs.

Policies should allow exceptions for HA/DR, security appliances, forensic retention, and deadline-bound workloads. Owners must document rationale and review dates so exceptions do not become unmanaged permanent resources.

## 18. Common Misconceptions

**Near-0% CPU means zero cost.** For VMs billed by instance duration, compute still bills while running even when CPU is nearly idle.

**OS-level shutdown always stops compute billing.** Some platforms distinguish stopped from deallocated; verify actual state and billing meters.

**Stopping a VM stops disk billing.** Existing volumes usually continue billing for provisioned capacity and performance.

**Deleting a VM deletes all related resources.** Disks, snapshots, IPs, NICs, backups, logs, and commitments may remain.

**Zero traffic means zero network cost.** NAT, load balancers, IPs, endpoints, or gateways may charge hourly; replication and logs also transfer data.

**Serverless has no idle costs.** Provisioned concurrency, minimum instances, gateways, databases, storage, logs, and networking can still generate charges.

**Idle resources are always waste.** Headroom, standby capacity, and warm capacity may be necessary for HA, bursts, or RTO.

**Reserved capacity stops billing when a VM stops.** Commitments or reservations can keep creating payment obligations regardless of usage.

**Unattached disks can be deleted immediately.** Disks may hold recovery data or serve DR; verify owner, backups, and retention first.

**Lower cost always means good optimization.** Optimization must keep SLOs, post-failure capacity, security, and recovery within committed limits.

## 19. Checklist for Auditing Idle and Associated Resource Costs

### Inventory and Billing

- [ ] Inventoried VMs/instances, nodes, serverless, disks, snapshots, IPs, LBs, NAT, and gateways.
- [ ] Distinguished running, stopped, deallocated, suspended, and terminated per provider semantics.
- [ ] Verified billing meters per state rather than guessing from state names.
- [ ] Applied owner, application, environment, cost center, and lifecycle tags.
- [ ] Separated compute, storage, network, license, monitoring, and commitment charges.

### Idle and Scheduling

- [ ] Reviewed CPU/RAM/network/storage peaks and sufficiently long workload profiles.
- [ ] Separated intentional idle from ownerless/purposeless idle.
- [ ] Configured dev/test start/stop schedules with pre-stop job checks.
- [ ] Benchmarked rightsizing with rollback plans.
- [ ] Verified autoscaling/scale-to-zero does not breach SLOs or RTOs.
- [ ] Preserved standby capacity and headroom for defined failure scenarios.

### Auxiliary Resources

- [ ] Assigned owners, retention, and restore tests to disks, snapshots, and backups.
- [ ] Audited public IPs/NICs/DNS before release.
- [ ] Properly allocated LB, NAT, firewall, private endpoint, and data transfer costs.
- [ ] Configured appropriate log/metric/trace retention and sampling.
- [ ] Verified licenses and marketplace subscriptions against contracts.
- [ ] Tracked coverage and utilization of commitments/reservations.

### Governance and Improvement

- [ ] Configured alerts for orphaned resources, idle spend, and budget anomalies.
- [ ] Built deletion workflows with owner confirmation, grace periods, and backup checks.
- [ ] Calculated savings across identical scopes and comparison windows.
- [ ] Tracked cost per successful request/job alongside SLIs/SLOs.
- [ ] Documented rationale, owner, and review date for HA/DR and security exceptions.

## Conclusion

Compute costs stem from provisioned CPU/RAM/GPU duration combined with many associated resources. Idle VMs can still bill compute hourly; stopped/deallocated VMs can stop compute meters while disks, snapshots, IPs, load balancers, NAT, backups, monitoring, licenses, or commitments continue billing. Kubernetes and serverless also carry baseline costs from minimum nodes, warm capacity, provisioned concurrency, and supporting services. Sustainable optimization requires verifying provider billing behavior, separating intentional idle, managing per-resource lifecycles, rightsizing and scheduling to workload patterns, and preserving headroom, availability, and resilience. Owner-tagged dashboards and cost per successful workload measure real savings without sacrificing service quality.
