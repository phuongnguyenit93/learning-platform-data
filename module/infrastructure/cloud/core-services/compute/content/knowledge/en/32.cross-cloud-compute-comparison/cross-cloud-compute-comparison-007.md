# Analyzing Differences in Lifecycle, Quotas, and SLA Scope

Choosing a virtual machine service across cloud providers is not merely comparing vCPU counts, memory, or hourly rates. A workload is also shaped by the VM lifecycle, how data is retained during stop/delete, host maintenance timing, Spot/preemptible mechanics, quotas per account/project/region, and Service Level Agreement (SLA) eligibility conditions. Two VMs with nearly identical specs can behave differently during scaling, host replacement, or incident recovery.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this lesson compares the approaches of Amazon EC2, Azure Virtual Machines, and Google Compute Engine. The focus is on analyzing lifecycle, quotas, and SLA scope; details are presented in principle and must be cross-checked against current terms for your exact region, SKU, operating system, and deployment configuration before making commitments to customers.

## Learning Objectives

After this lesson, you will be able to:

- Describe the primary states in a VM lifecycle and the billing/data implications of each state.
- Compare stop, deallocate, reboot, redeploy, resize, delete, and host maintenance.
- Distinguish persistent disks from local/temporary/ephemeral disks.
- Analyze differences between On-Demand, Reserved/committed capacity, and Spot/preemptible VMs.
- Distinguish increasable quotas from system limits or actual available capacity.
- Identify quota scopes across account, subscription, project, region, zone, and VM family.
- Build capacity requests accounting for rolling deployments, failovers, and headroom.
- Explain which components, conditions, and exclusions a provider SLA covers.
- Distinguish provider SLAs, application SLOs, and end-to-end user SLAs.
- Calculate availability across series components and evaluate redundancy gains.
- Build a compute provider evaluation checklist for a specific workload.

## 1. Comparison Scope and Terminology

The three services compared:

| Provider | VM Service | Common VM Group Management Mechanism |
|---|---|---|
| Amazon Web Services | Amazon EC2 | EC2 Auto Scaling groups |
| Microsoft Azure | Azure Virtual Machines | Virtual Machine Scale Sets |
| Google Cloud | Compute Engine | Managed Instance Groups |

All three services provide on-demand VMs, images/templates, disks, networking, identity, monitoring, and autoscaling mechanisms. State names, control plane operations, quotas, and SLA terms are not completely identical.

### 1.1. VM Lifecycle

The lifecycle encompasses all states and operations from VM request, host allocation, guest OS boot, operation, stopping, restarting, and reconfiguring through deletion. The lifecycle has two sides:

- **Control plane:** the state reported by the provider's API/portal.
- **Guest/workload:** the state of the OS, processes, connections, filesystems, and applications inside the VM.

A VM may report Running in the control plane while the application is unhealthy. Conversely, a VM may be rebooting or deallocating in the control plane even though the application already received a shutdown signal earlier.

### 1.2. Quotas, Limits, and Capacity

- **Quota:** the resource budget allocated to a scope, such as the number of vCPUs or GPUs usable in a region.
- **Service limit/system limit:** a technical or policy limit of the service; it may not be increasable via standard quota requests.
- **Available capacity:** physical/SKU resources actually available to allocate in the requested zone/region at request time.
- **Reservation:** a mechanism to hold capacity ahead of time or commit to usage/spend; semantics depend on the provider's reservation type.

Remaining quota does not guarantee suitable hosts/SKUs exist in the desired zone. Conversely, a region may have physical capacity yet requests still fail if quotas, policies, or subnet IPs are exhausted.

### 1.3. SLA, SLO, and SLI

- **SLI (Service Level Indicator):** a measurable metric, such as successful request ratio or VM availability time.
- **SLO (Service Level Objective):** an internal target for an SLI over a time window.
- **SLA (Service Level Agreement):** a contractual commitment on service level, scope, measurement methodology, and remedies/service credits if conditions are missed.

A provider SLA does not automatically become the SLA of an application built on top of VMs.

## 2. VM Lifecycle from an Operational Perspective

A typical lifecycle includes these stages:

1. **Request/provision:** select image, machine type, disks, subnet, identity, zone, and quota.
2. **Boot/initialization:** host allocates, hypervisor initializes the VM, guest OS boots, and bootstrap runs.
3. **Running:** VM can accept workloads; health checks and application readiness must still be verified.
4. **Maintenance/recovery:** provider may announce maintenance, live migrate, reboot, redeploy, or require instance replacement depending on service/SKU.
5. **Stop/suspend:** stops compute while potentially retaining disks and certain other resources.
6. **Start/resume:** reallocates compute or restores the VM from saved state if supported by the feature.
7. **Delete/terminate:** deletes the VM; disks, IPs, snapshots, backups, and NICs may be kept or deleted per separate policies.

Never assume similarly named operations behave identically across clouds. In particular, distinguish stopping the guest OS, stopping a VM while retaining host allocation, deallocating/releasing compute, suspending with memory saved, and deleting an instance.

## 3. Comparing Lifecycle States and Operations

### 3.1. Amazon EC2

EC2 exposes common states such as pending, running, stopping, stopped, shutting-down, and terminated.

- On launch, an instance moves through pending to running if allocation and boot succeed.
- Reboot restarts the guest OS; the instance retains the same instance identity.
- Stop applies to instance types supporting stop, typically EBS-backed. Compute capacity is released; EBS volumes are retained per configuration.
- Start from stopped may allocate a new host. Auto-assigned public IPv4 addresses can change; Elastic IPs or corresponding network setups preserve stable addresses.
- Instance store is temporary host-attached storage; data on it is lost on stop/terminate or host replacement per instance type semantics.
- Terminate ends the instance lifecycle. EBS volumes may auto-delete or persist depending on delete-on-termination; snapshots and related resources must be managed separately.

Hibernation can save RAM contents to EBS for resuming, provided the instance, OS, volume, and configuration support it. Hibernation does not apply to every instance type or workload.

### 3.2. Azure Virtual Machines

Azure distinguishes allocation states such as starting/running/stopping/stopped/deallocating/deallocated and deleting/deleted across management views.

- Stopping from inside the guest OS can leave the VM in the stopped state while still holding host allocation; compute billing may continue.
- Stop/deallocate from the control plane releases compute allocation. Disks and certain related resources remain and may continue incurring charges.
- Starting from deallocated requires fresh compute allocation; allocation can be affected by zone/region quotas and capacity.
- Managed OS disks and data disks typically persist independently of the VM unless configured to delete with the VM.
- Temporary disks are transient storage; data may be lost during VM redeploy, host maintenance, or specific lifecycle actions.
- Deleting a VM does not automatically delete every disk, NIC, public IP, and snapshot; behavior depends on delete options and resource types.

Azure offers ephemeral OS disk options on eligible SKUs. Because ephemeral disks sit on local host storage, verify exact behavior during redeploy, reimage, deallocate, and host events before placing important data there.

### 3.3. Google Compute Engine

Compute Engine has states such as PROVISIONING, STAGING, RUNNING, STOPPING, SUSPENDING, SUSPENDED, and TERMINATED.

- When creating a VM, resources go through provisioning and staging before entering RUNNING.
- Stopping transitions the VM to TERMINATED; Persistent Disks typically remain and continue incurring storage charges.
- Suspend, where supported, saves memory state for resuming; not every machine type or attached device supports all cases.
- Local SSDs are host-attached storage with different durability semantics than Persistent Disks; data may not survive stop/terminate or host events depending on configuration and VM type.
- When deleting a VM, Persistent Disks can be kept or deleted based on auto-delete settings; ephemeral IPs and supporting resources also follow separate lifecycles.
- Maintenance can use live migration on supported machine types; some configurations require terminate/restart or follow a configured maintenance policy.

### 3.4. Operation Comparison Table

| Operation | Amazon EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| Reboot | Restarts guest OS on the instance | Restarts guest/VM per selected operation | Resets/restarts VM per selected operation |
| Stop/deallocate | Stop releases compute; EBS kept per config | Must distinguish stopped from deallocated; deallocated releases compute | Stop moves VM to TERMINATED; persistent disks generally remain |
| Suspend/hibernate | Hibernation saves RAM to EBS if supported | Suspend/hibernate depending on SKU and offered features | Suspend saves memory state if VM supports it |
| Local temporary storage | Host-attached instance store | Host-attached temporary disk | Host-attached Local SSD |
| Disks after VM deletion | EBS depends on delete-on-termination | Managed disks depend on delete options | Persistent Disks depend on auto-delete |
| Host maintenance | May involve retirement/replacement; behavior varies by instance | May live migrate/redeploy depending on VM/SKU | Live migration or maintenance action depending on machine type |

This conceptual summary does not replace per-VM-type lifecycle documentation. Before automating stop, suspend, or delete operations, verify exact final states, billing, disk retention, IPs, and data loss behavior.

## 4. Persistent Disks vs. Local/Ephemeral Disks

One of the highest-impact differences is where data lives and which operations it survives.

### 4.1. Persistent Storage

Persistent block disks are managed somewhat independently of compute lifecycles. VMs can stop or be replaced while disks remain, depending on deletion policies. Persistent disks suit OS/data disks that must endure, though they still require backups, snapshots, replication, and restore testing.

### 4.2. Local/Temporary Storage

Local/temporary disks typically offer low latency or high throughput and fit scratch data, regenerable caches, temporary files, or buffers. However, data can be lost when:

- The VM is stopped/deallocated.
- The host is replaced or undergoes maintenance.
- The instance is terminated/deleted.
- The VM is redeployed/reimaged.
- The provider performs recovery actions per machine type.

Never place primary databases, unique sessions, or sole user files on local ephemeral storage without replication and recovery protocols.

### 4.3. Design Rules

| Data Type | Recommended Location | Rationale |
|---|---|---|
| OS image and packages | Image/template or OS disk | Reproducible from standard images |
| Database data | Managed database or replicated persistent disk | Requires durability, backups, and recovery |
| User uploads/reports | Object storage or shared file service | Accessible across multiple VMs |
| Sessions/caches | Shared cache or TTL-backed store | Independent of a single instance |
| Build scratch/temp files | Local temporary disk | Recomputable if lost |
| Queues/events | Managed queue/stream or durable broker | Decouples producers/consumers and supports retries |

## 5. Maintenance, Resizing, and Host Changes

VMs run on physical infrastructure managed by the provider. Providers must patch hypervisors, replace hosts, update firmware, and maintain capacity. How maintenance is handled affects downtime and application self-healing.

### 5.1. Live Migration and Restart-Based Maintenance

Live migration moves a running VM to another host with minimal disruption when the machine type and workload support it. Certain host events still require reboots, stop/starts, or redeploys. Never assume every VM can always live migrate.

Design applications to tolerate:

- Unexpected guest reboots.
- Network connection resets.
- Small clock/time drifts during host transfers.
- Brief storage/network path interruptions.
- VM retirement requiring replacement instance creation.

### 5.2. Resizing

Resizing changes CPU/memory or machine family. The operation may require stop/deallocate, may not stay on the same host, or may alter NIC/NUMA/CPU features. Check:

- Whether OS and drivers support the new shape.
- Whether disk throughput/IOPS change.
- Network bandwidth and PPS limits.
- Licensing/CPU topology and application tuning.
- Reservation/Spot availability for the new shape.
- Downtime and rollback path.

### 5.3. Instance Replacement

With VM groups, prefer replacing instances from new templates/images rather than patching individual VMs. Rolling replacements should cap unavailable instances, use health checks, and verify readiness before draining old instances.

If workloads hold local state, replicate or checkpoint before termination. Autoscaling groups do not automatically transfer local data to new VMs.

## 6. Spot, Preemptible, and Interruptible Capacity

Providers offer lower-priced compute products that permit reclaiming instances when capacity is needed:

- AWS EC2 Spot Instances.
- Azure Spot Virtual Machines.
- Google Cloud Spot VMs (formerly Preemptible VMs).

Commonly, capacity availability is not guaranteed like On-Demand; instances can be reclaimed with notice/warning windows and behaviors depending on the provider.

### 6.1. Differences to Evaluate

| Criterion | AWS Spot | Azure Spot VM | Google Cloud Spot VM |
|---|---|---|---|
| Capacity | Based on spare EC2 capacity | Based on spare Azure capacity | Based on spare Compute Engine capacity |
| Reclamation | Interruption notice per service semantics; stop/hibernate/terminate per supported config | Eviction; policy can deallocate or delete | Can preempt/terminate; limited notice window |
| Pricing | Fluctuates by market/offer and instance pool | Spot pricing/max price policy per product | Spot pricing varies by resource type and time |
| Best suited for | Batch, stateless workers, CI, fault-tolerant fleets | Batch, scale sets, stateless/interruptible workloads | Batch, HPC workers, stateless/interruptible workloads |
| Risks | Capacity interruptions and pool shortages | Evictions, quotas/capacity by region/SKU | Preemption and availability constraints |

Do not infer a generic Spot SLA from these summaries. Read the exact product terms and current eviction configuration.

### 6.2. Suitable Workloads

- Checkpointed or retryable batch jobs.
- Rerun-safe CI builds/tests.
- Stateless queue workers pulling jobs from queues.
- Distributed compute with schedulers and task requeuing.
- Segmented checkpointed rendering/transcoding.

Do not place primary databases, unrestartable license servers, or non-idempotent transactions on Spot without dedicated redundancy designs.

### 6.3. Preparing for Interruptions

1. Listen for interruption events via the provider-supported metadata/notification channel.
2. Stop accepting new jobs.
3. Persist checkpoints or return leases/messages to the queue.
4. Flush outputs using a safe commit protocol.
5. Close connections and exit before the deadline if possible.
6. Let the scheduler spin up replacement capacity or requeue jobs.

Applications must still survive sudden instance loss; interruption notices do not guarantee enough time to finish work.

## 7. Comparing Quotas and Limits

Quotas are part of capacity planning. Each cloud organizes quotas and increase request interfaces differently.

### 7.1. AWS EC2 and Service Quotas

EC2 enforces quotas across multiple dimensions, including vCPU-based On-Demand quotas by instance family/region, Spot-related quotas, and limits on other resources. Some quotas appear in Service Quotas and can be requested for increases; some limits depend on resource type or policy.

When planning capacity, check:

- On-Demand vCPU quotas by family/region.
- Spot vCPU quotas and pool availability.
- GPU/accelerator quotas.
- EBS volume, snapshot, and throughput constraints.
- Elastic IP, ENI, security group, and subnet IP capacity.
- Auto Scaling group desired/max limits and API rates.

Spare vCPU quota does not guarantee capacity for an instance type in a specific Availability Zone.

### 7.2. Azure Quotas and Subscription Limits

Azure quotas are typically scoped to subscription, region, and VM family/series; alongside total vCPU quotas, limits apply to related resources. Quota increases may require per-subscription/region requests and do not guarantee SKU availability in a zone.

When planning capacity, check:

- Regional vCPU quotas.
- Family-specific vCPU quotas.
- Spot vCPU quotas and eviction policies.
- GPU/accelerator family quotas.
- Managed disk, snapshot, NIC, and public IP limits.
- VM Scale Set maximum capacity and subnet address space.
- Azure Policy or subscription-level restrictions.

Quotas can differ across subscriptions even within the same tenant. Verify the exact target subscription.

### 7.3. Google Cloud Quotas

Compute Engine enforces quotas per project, region, and certain global scopes; quotas cover CPU, GPU, disks, IPs, snapshots, and other APIs/resources. Some limits are increasable quotas, while others are system limits or capacity-dependent.

When planning capacity, check:

- Regional CPU quotas and machine family constraints.
- GPU/accelerator quotas.
- Spot capacity/availability.
- Persistent Disk capacity/performance limits.
- External IP, network, forwarding rule, and subnet IP capacity.
- Managed Instance Group limits and API rates.
- Project-level policies and organization constraints.

Global or regional quotas do not guarantee capacity in a specific zone. Verify both zone availability and machine type availability.

### 7.4. Scope-Based Quota Matrix

| Dimension | AWS EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| Account scope | Account and region/service quotas | Subscription and region | Project and quota scopes |
| Compute CPU | vCPU quota by family/market | vCPU quota by region/family | CPU quota by region/project and type |
| Accelerators | GPU/accelerator quotas | GPU VM family quotas | GPU quotas by region/project |
| Networking | ENIs, IPs, security groups, subnets | NICs, public IPs, subnets | IPs, forwarding rules, network limits |
| Storage | EBS volumes/snapshots/throughput | Managed disks/snapshots | Persistent Disk/snapshot quotas |
| Group scaling | Auto Scaling group and API constraints | VM Scale Set and API constraints | Managed Instance Group and API constraints |

Quota names and display formats vary by service and over time. Before deploying, query quotas in the exact account/subscription/project and region.

## 8. Quotas Do Not Equal Guaranteed Capacity

This is a critical distinction when planning for peaks or disaster recovery:

- Quota is permission to request usage up to a threshold.
- Capacity is the physical resources actually allocatable at the requested time and location.
- Reservations/capacity reservations can hold a capacity type ahead of time under specific terms.
- Autoscaling merely calls APIs to launch instances; it cannot bypass quotas or conjure physical hosts when the provider has no capacity.

For example, a project might hold a 200-vCPU quota while a zone is out of capacity for a specific machine family; VM requests still fail. Conversely, a zone might have spare hosts while the subscription quota only allows 120 vCPUs; requests above that also fail.

### 8.1. Quota Headroom

When calculating quotas, include:

- Currently running capacity.
- Rolling deployment surge.
- Replacements for unhealthy VMs.
- Failover workloads from another zone.
- Autoscaling peaks and overlapping batch runs.
- Temporary VMs for migrations or restores.
- VMs/workers of other teams sharing the same quota.

Example: a workload runs 40 VMs at 2 vCPUs each and needs 25% surge during rolling updates:

~~~text
Baseline = 40 × 2 = 80 vCPU
Surge    = 80 × 25% = 20 vCPU
Peak     = 80 + 20 = 100 vCPU
~~~

If failover also demands another 20 vCPUs in a different region/zone, the quota/capacity plan must budget for that failure scenario separately. Never assume surge and failover cannot overlap if operational procedures allow them to coincide.

### 8.2. Pre-Scaling Process

1. Calculate desired capacity from load and SLOs.
2. Calculate vCPU/GPU/disk/network/IP needs per region/zone/family.
3. Check current quotas and usage by other workloads.
4. Check VM group max size and autoscaling policies.
5. Check zone/SKU availability and capacity reservations if needed.
6. Submit quota increases early—never wait until peak hits.
7. Test launching representative instances in each zone.
8. Alert when quota utilization nears thresholds and monitor allocation failures.

## 9. Comparing Compute Service SLA Scope

An SLA is a contractual commitment covering eligible services and configurations. You cannot conclude a cloud "has a 99.x% SLA" and apply that figure to every VM, disk, network, and application.

### 9.1. AWS EC2

EC2 has a dedicated Service Level Agreement defining monthly uptime percentage, eligibility conditions, and service credits. Read the exact instance/region scope, deployment topology, exclusions, downtime calculation, and claim filing deadlines in AWS Service Terms.

The EC2 SLA does not automatically cover every architectural component. EBS, load balancing, networking, and other managed services carry separate terms. A healthy EC2 instance does not guarantee successful application responses if EBS, databases, DNS, or application processes fail.

### 9.2. Azure Virtual Machines

The Azure Virtual Machines SLA depends on the deployment configuration and designed availability level—such as single instance, availability sets, or availability zones where supported by SKU/region. Some commitments impose conditions on disk types, instance counts, placement, and configuration.

Verify:

- Whether VMs are properly distributed across availability sets/zones.
- Whether disk and network dependencies carry separate SLAs.
- Whether the chosen SKU/region/OS falls within commitment scope.
- How maintenance, customer actions, and exclusions are defined.
- Service credit terms and claim processes.

### 9.3. Google Compute Engine

Compute Engine provides an SLA per service and VM/zone deployment configuration. Scope may distinguish single instances, multiple instances in one zone, or multi-zone deployments per terms. Persistent Disks, load balancing, networking, and other managed services carry separate commitments.

Verify that the machine type, region/zone, disks, network dependencies, and deployment topology fall under the cited SLA scope. Never infer full-application SLA from a VM's RUNNING status.

### 9.4. Commitment Scope Comparison

| Question | AWS EC2 | Azure VM | Google Compute Engine |
|---|---|---|---|
| Primary SLA | EC2 service SLA | Virtual Machines SLA | Compute Engine SLA |
| Scope dependencies | Region, instance eligibility, topology, and terms | VM deployment model, zone/set, SKU, and terms | Instance/zone topology, machine type, and terms |
| Storage | EBS has separate terms | Managed Disks have separate terms | Persistent Disk has separate terms |
| Load balancing/networking | Review each service's separate SLA | Review each service's separate SLA | Review each service's separate SLA |
| Remedy | Service credits per AWS terms and claim process | Service credits per Microsoft SLA terms | Service credits per Google Cloud SLA terms |
| Pitfall to avoid | Treating EC2 SLA as end-to-end SLA | Applying VM SLA across all dependencies | Applying Compute Engine SLA to the entire application |

Terms and numerical thresholds can change. Before signing contracts or publishing availability targets, archive the SLA effective at purchase time and verify the exact SKU/region.

## 10. What SLAs Cover and Commonly Exclude

Read an SLA across these sections:

1. **Covered service:** which service/resources are covered.
2. **Eligibility:** region, SKU, OS, disks, topology, and minimum configuration.
3. **Measurement:** uptime calculation, measurement window, and data sources.
4. **Exclusions:** which events do not count toward compensable downtime.
5. **Remedy:** service credits, credit tiers, and caps.
6. **Claim process:** deadlines, evidence, resource IDs, and submission channels.

Common exclusions often involve:

- Errors caused by customer configuration or actions.
- Guest OS, application code, or third-party software.
- Customer-managed credentials, firewalls, DNS, or networking.
- Beta/preview services or ineligible instance types.
- Scheduled maintenance or events explicitly listed in terms.
- Force majeure, abuse, or other contractual exclusions.

This list is a reading guide only; it does not replace the exact wording in the provider's SLA.

### 10.1. Service Credits Are Not Full Damages Compensation

Service credits are typically a contractual remedy capped by published formulas and limits. They do not necessarily reimburse lost business revenue, staffing expenses, or indirect damages. Legal/procurement teams must review liability and credit clauses separately.

### 10.2. SLAs Differ from Support Response Times

An availability SLA is not the same as support ticket response times. A support plan defines response targets by severity, whereas a service SLA defines uptime and credits. Track both commitments separately.

## 11. From Provider SLA to Application SLO

A multi-tier application can fail even while every VM remains RUNNING. Set end-to-end SLOs based on successful requests and user-observed latency.

### 11.1. Components in Series

If requests traverse edge, load balancer, web, application, and database tiers in series, end-to-end availability depends on all components. Assuming independent failures:

\[
A_{end-to-end}=\prod_{i=1}^{n} A_i
\]

Example with three components in series, each at 99.9% availability:

~~~text
A = 0.999 × 0.999 × 0.999
  ≈ 0.997003
  ≈ 99.7003%
~~~

In reality, failures are not strictly independent; shared networking, identity, DNS, or control planes can induce correlated failures. This formula is a rough model demonstrating why chaining dependencies lowers end-to-end availability below that of individual components.

### 11.2. Redundancy and Failure Independence

With two independent instances, each with availability A, where a load balancer shifts traffic to the surviving instance, group availability can be estimated as:

\[
A_{group}=1-(1-A)^2
\]

Example with each instance at 99.9% availability under an independence assumption for two instances:

~~~text
A_group = 1 - (1 - 0.999)^2
        = 0.999999
        = 99.9999%
~~~

This figure holds only if failures are independent and failover actually works. If both VMs share a host/zone or depend on one failing database, VM redundancy will not achieve that availability.

### 11.3. Error Budgets

With a 99.9% SLO over a 30-day month, theoretical downtime budget is:

~~~text
30 × 24 × 60 × (1 - 0.999)
= 43.2 minutes
~~~

Internal SLOs can be stricter than provider SLAs or structured to reserve error budget for application bugs, deployments, networking, and dependencies. Track error budgets via request-based SLIs, not VM uptime alone.

## 12. Choosing Topologies to Meet SLAs

### 12.1. Single VM

Suits test environments or interruption-tolerant workloads. Provides no compute redundancy; host/guest failures stop the service.

### 12.2. Multiple VMs in One Zone

Reduces single-instance failure risk while remaining exposed to zone outages, zone network issues, or shared dependencies. SLAs/credits may differ from multi-zone topologies; verify exact terms.

### 12.3. Multi-Zone

Distributes VMs and load balancers across multiple zones; databases need matching replication/failover. This is standard for production needing zone-fault tolerance, though you must verify subnet/IPs, quotas, disk topology, and data replication.

### 12.4. Multi-Region

Supports disaster recovery or active-active setups. Requires solving replication lag, data consistency, global routing, identity, secrets, reserve quotas, and failback. Two regions do not automatically yield a higher composite SLA without proper application and operational architecture.

## 13. Example Analyzing a Workload Across Three Clouds

An API service needs 60 VMs, each with 4 vCPUs and 16 GiB of memory. The system spans three zones, uses a 20% rolling deployment surge, and must survive losing one zone.

### 13.1. Calculating Baseline and Surge

~~~text
Baseline vCPU = 60 × 4 = 240 vCPU
Baseline RAM  = 60 × 16 = 960 GiB

Surge VM      = 60 × 20% = 12 VM
Surge vCPU    = 12 × 4 = 48 vCPU
Peak rolling  = 240 + 48 = 288 vCPU
~~~

Quotas must cover rolling peak plus other workloads in the same scope. If a zone failure requires launching replacement VMs in the two surviving zones, model that extra capacity as well.

### 13.2. Per-Provider Verification

**AWS EC2**

- Select a supported instance family and region/zones.
- Check On-Demand vCPU quota for the family, and Spot quota if using interruptible workers.
- Verify EBS, ENI, subnet IP, and Auto Scaling group max limits.
- If guaranteed capacity is required, evaluate Capacity Reservations/appropriate placement.
- Review EC2 SLA alongside EBS, load balancer, and networking terms.

**Azure Virtual Machines**

- Check subscription regional vCPU quota and family-specific quota.
- Confirm the SKU is available in the chosen Availability Zones.
- Verify VM Scale Set max limits, NICs, managed disks, and subnet IPs.
- Clarify VM deallocation and temporary disk behavior in automation.
- Review SLAs by deployment model, zones, and disk tiers.

**Google Compute Engine**

- Check project regional CPU quota and machine family/accelerator quotas.
- Confirm the machine type has capacity in the target zones.
- Verify Managed Instance Group size, Persistent Disk, and IP quotas.
- Clarify Local SSD/maintenance behavior and reservations if needed.
- Review Compute Engine SLA alongside Persistent Disk and load balancing terms.

### 13.3. Selection Criteria

Do not pick a provider merely because one VM type has a lower price. Compare:

- Whether VM shapes meet CPU/memory/network/IOPS needs.
- Whether quotas are sufficient and increasable before deadlines.
- Whether capacity is allocatable in the required zones.
- Whether lifecycles fit stateful/ephemeral workloads.
- Whether SLAs cover the exact topology and resources.
- Existing operational skills, observability, identity, and automation.
- Costs across compute, disks, networking, backups, support, and idle headroom.

## 14. Workload-Based Decision Table

| Workload | Lifecycle Priority | Quotas to Watch | SLA/Topology to Verify |
|---|---|---|---|
| Stateless web/API | VM replacement, rolling updates, health checks | Family vCPUs, subnet IPs, LB targets | Multi-zone VMs + LB + data dependencies |
| Stateful database | Disk persistence, backups, failover | Disks, IOPS, storage, networking | Database/disk/replication SLAs |
| Batch workers | Spot interruptions, checkpoints, retries | Spot/CPU/GPU quotas | Do not rely on SLAs for interruptible compute |
| GPU inference | GPU lifecycle, drivers/images, capacity reservations | GPU family/zone quotas | Compute + accelerators + networking/storage |
| CI runners | Ephemeral VMs, post-job cleanup | Concurrent VM quotas, API rates | Demand-based SLA, queues, and artifact stores |
| HPC clusters | Placement, low-latency networking, coordinated shutdown | CPU/GPU, NICs, placement/capacity | Per-node SLA and shared fabric/storage |

## 15. Process for Reading and Comparing SLAs

1. Identify the exact service: VM compute, disk, load balancer, network, or database.
2. Specify the exact region, zone, SKU, OS, and deployment topology.
3. Download the SLA terms effective at evaluation time.
4. Read downtime/availability definitions and measurement windows.
5. Inspect exclusions, maintenance clauses, and customer responsibilities.
6. Inspect service credit tables, caps, and claim deadlines.
7. Archive URL/version/date and approvers in ADR/procurement records.
8. Map provider commitments into end-to-end application SLOs.
9. Test failover and collect actual SLIs.
10. Re-evaluate whenever changing region, SKU, disk tier, or topology.

### 15.1. Questions to Answer Before Signing

- Does the SLA cover a single VM or require multiple VMs/zones?
- Does it mandate specific load balancers or managed disk tiers?
- Are the chosen instance type/OS/region eligible?
- Do stop/deallocate or maintenance events count as downtime?
- How are outages from customer networking/configuration treated?
- Are there separate SLAs for disks, networking, IPs, DNS, and load balancers?
- What are the claim deadline and required evidence?
- Do service credits cap remedies and exclude indirect damages?

## 16. Controlling Quotas Across the Workload Lifecycle

Manage quotas like a production dependency:

- Put current quotas, usage, and headroom on dashboards.
- Track quotas per region/family rather than total vCPUs alone.
- Alert before reaching autoscaling max bounds.
- Fold quota increases into change/capacity review workflows.
- Verify quotas before disaster recovery exercises.
- Clean up orphaned resources like disks, IPs, snapshots, and NICs to cut waste.
- Watch API rate limits when provisioning large VM batches.
- Build capacity plans for rolling deployments and blue-green releases.

### 16.1. Quota Increases Are Not Capacity Reservations

A quota increase raises your permitted usage ceiling. It does not reserve physical hosts ahead of time. When capacity must be guaranteed for peaks or failovers, evaluate reservations/capacity guarantees under separate products and contracts.

### 16.2. Testing Quota Exhaustion

In a test environment, simulate approaching quota limits or set a low group max to verify:

- Autoscalers surface clear errors.
- Alerts fire reliably.
- Workloads do not enter infinite retry loops.
- Queues/backpressure keep load bounded safely.
- Runbooks identify the exact quota scope to raise.
- Once quotas increase, scaling resumes without creating duplicate instances.

Never intentionally exhaust production quotas shared with critical workloads.

## 17. Risks During Cross-Cloud Migration

### 17.1. Lifecycle Mismatches

Automation scripts may assume stop always releases compute, disks always survive deletion, or public IPs never change. These assumptions break across providers. Standardize lifecycles behind abstractions while maintaining provider-specific adapters and integration tests.

### 17.2. Quota Mismatches

A region may have generous vCPU quotas yet tight GPU/NIC/IP quotas. Mapping an equivalent instance type does not guarantee equivalent quotas. Before migration, build a resource table by family and scope, submit quota requests early, and test capacity allocation.

### 17.3. SLA Mismatches

A multi-zone setup on provider A may satisfy different SLA terms than a single-zone setup on provider B. Never compare SLA figures across differing topologies and covered service scopes.

### 17.4. Data Durability Mismatches

Local SSDs, temporary disks, and persistent disks exhibit distinct durability behavior. Migration plans must specify which data to copy, replicate, back up, or regenerate; never map disk configs by name similarity while ignoring semantics.

### 17.5. Operational Mismatches

Monitoring events, maintenance notifications, identity, image lifecycles, autoscaling APIs, and shutdown hooks differ. Maintain one unified process-level runbook alongside provider-specific steps for commands, events, and resource identifiers.

## 18. Official Tools and Reference Documentation

### AWS

- EC2 instance lifecycle: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html
- EC2 instance store: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/InstanceStorage.html
- Service Quotas: https://docs.aws.amazon.com/servicequotas/latest/userguide/intro.html
- AWS Service Level Agreements: https://aws.amazon.com/legal/service-level-agreements/

### Microsoft Azure

- VM states and billing: https://learn.microsoft.com/azure/virtual-machines/states-billing
- VM quotas and limits: https://learn.microsoft.com/azure/azure-resource-manager/management/azure-subscription-service-limits
- Azure Service Level Agreements: https://azure.microsoft.com/support/legal/sla/
- Ephemeral OS disks: https://learn.microsoft.com/azure/virtual-machines/ephemeral-os-disks

### Google Cloud

- VM instance lifecycle: https://cloud.google.com/compute/docs/instances/instance-lifecycle
- Compute Engine quotas: https://cloud.google.com/compute/quotas
- Compute Engine SLA: https://cloud.google.com/compute/sla
- Local SSD: https://cloud.google.com/compute/docs/disks/local-ssd

These links are reference starting points. Before deploying, consult current documentation for your exact region, SKU, and features; quotas, states, and SLAs are subject to updates.

## 19. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Treating stop and deallocate as identical | Misestimated compute billing | Verify provider state and billing semantics |
| Storing critical data on local disks | Data loss on host/VM replacement | Use persistent storage, replication, and backups |
| Assuming VM deletion handles all disks identically | Data loss or orphaned disks | Check delete/auto-delete policies per resource |
| Assuming spare quota guarantees VM launch | Scale-out fails due to zone/SKU capacity | Verify quotas and physical capacity separately |
| Checking only total vCPU quota | Shortages in family/GPU/IP/disk quotas | Build a quota matrix by resource and scope |
| Setting autoscaling max equal to absolute quota | Zero headroom for rollouts/failover | Reserve quota for surge and recovery |
| Running stateful primaries on Spot | Sudden capacity loss causes outages/data corruption | Use Spot only for checkpointed interruptible workloads |
| Treating provider SLA as application SLA | Commitments to users exceed covered scope | Build and test end-to-end SLOs |
| Comparing SLAs across different topologies | False conclusions about availability | Normalize zones, instance counts, and dependencies |
| Ignoring exclusions/claim deadlines | Ineligible for service credits | Archive terms and claim procedures |
| Skipping restore/failover tests | Unknown actual RTO/RPO | Run periodic drills and measure results |
| Assuming maintenance always live migrates | Workloads break on reboot/retirement | Test restarts/replacements and graceful shutdown |

## 20. Provider Evaluation and Production Readiness Checklist

**Lifecycle**

- [ ] Understood create, run, stop, deallocate, suspend, reboot, and delete states.
- [ ] Verified billing behavior for each state.
- [ ] Classified persistent disks vs. local/temporary disks.
- [ ] Verified public IP, NIC, and disk behavior across stop/start/delete.
- [ ] Understood host maintenance, live migration, and retirement events.
- [ ] Verified workloads recover cleanly after VM replacement.

**Quotas and Capacity**

- [ ] Checked quotas per account/subscription/project and region.
- [ ] Checked quotas per VM family, GPU, disk, IP, and API.
- [ ] Verified SKU/zone availability.
- [ ] Accounted for rolling surge, failover, and DR capacity.
- [ ] Configured headroom and quota usage alerts.
- [ ] Distinguished quota increases from capacity reservations.

**SLAs and SLOs**

- [ ] Archived effective SLA version and URL.
- [ ] Verified covered service, region, SKU, and topology.
- [ ] Read measurement rules, exclusions, remedies, and claim deadlines.
- [ ] Checked separate SLAs for disks, networking, load balancers, and databases.
- [ ] Defined application SLOs and error budgets independent of provider SLAs.
- [ ] Tested multi-zone failover, backup restores, and recovery.

**Migration and Operations**

- [ ] Lifecycle automation includes adapter/provider-specific tests.
- [ ] Disks/data migrated according to durability semantics.
- [ ] Quota requests completed prior to migration cutover.
- [ ] Autoscaling and replacement tested in each region.
- [ ] Runbooks for maintenance, interruptions, and rollbacks have assigned owners.
- [ ] Cost model includes idle headroom, disks, networking, and support.

## 21. Conclusion

VM lifecycle, quotas, and SLAs are interconnected yet non-interchangeable dimensions. Lifecycle dictates how VMs and data behave across create, stop, resize, maintenance, and delete. Quotas bound what resources you are permitted to request within a scope; actual capacity still hinges on zone, SKU, and timing. SLAs define contractually covered services, measurement rules, and remedies.

When comparing AWS EC2, Azure Virtual Machines, and Google Compute Engine, normalize workloads, topologies, disks, quota scopes, and SLA eligibility. Budget quotas for both rolling deployments and failovers, design workloads to survive VM replacements, separate durable data from local disks, and establish independent end-to-end SLOs. Provider selection should rest on operational evidence, capacity availability, lifecycle semantics, and effective contractual terms—never on raw VM pricing or a single headline SLA figure alone.

## Key Terms to Remember

| Term | Meaning |
|---|---|
| VM lifecycle | States and operations from provisioning through termination/deletion. |
| Deallocate | Releases compute allocation; disks and other resources may remain and incur charges. |
| Hibernate/suspend | Saves memory state to resume if supported by the VM type. |
| Persistent Disk | Managed block storage decoupled to a degree from the VM lifecycle. |
| Local/ephemeral disk | Host-attached storage typically for temporary data that may be lost on VM replacement. |
| Spot/preemptible VM | Lower-cost compute capacity reclaimable by the provider. |
| Quota | Maximum resources permitted to be requested within a scope. |
| System limit | Technical/policy limit not necessarily raisable via quota requests. |
| Available capacity | Physical resources actually allocatable in a zone/region at request time. |
| Capacity reservation | Mechanism to hold capacity ahead of time per provider semantics and terms. |
| SLA | Contractual commitment on service level, scope, measurement, and remedies. |
| SLO | Internal service quality target. |
| SLI | Measured metric used to evaluate an SLO. |
| Error budget | Acceptable downtime/errors within an SLO window. |
| Service credit | Credit issued under SLA terms when claim conditions are met. |
| Availability Zone | Fault domain within a region. |
| Live migration | Moving a VM between hosts with minimal disruption when supported by workload/platform. |
| Connection draining | Stopping new requests and waiting for in-flight requests before removing a backend. |
| Quota headroom | Spare quota buffered for surge, replacements, and failover. |
