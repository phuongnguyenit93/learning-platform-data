# Designing Virtual Machine Scale Sets

## 1. Problem statement: why do we need VMSS?

An application on Microsoft Azure can run on a single virtual machine (VM), such as a user-facing Java API or a worker processing files in a queue. Deploying a single VM is easy to start with, but problems arise when traffic surges, a machine fails, or the application needs an upgrade without downtime.

Suppose an API is running on one VM. During a sales campaign, the request rate triples. An administrator could create two more VMs, install Java, copy the code, configure networking, and register them with a load balancer. However, when traffic drops, who checks which VMs can be deleted? If OS patching is needed, who ensures all VMs are running the same version? When one VM breaks, who replaces it?

**Azure Virtual Machine Scale Sets (VMSS)** help orchestrate a set of VMs to scale compute capacity up or down according to selected configurations and policies. The VM group can serve HTTP traffic, process independent messages, or execute batch workloads.

In the **Elastic Compute and Batch Processing** chapter, VMSS connects concepts from subscriptions, resource groups, Azure networking, images, Azure Monitor, security, and cost control into an architecture that can be operated in practice.

### Learning objectives

After this lesson, you will be able to:

1. Explain how VMSS differs from manually creating multiple VMs.
2. Distinguish between the two orchestration modes: **Uniform** and **Flexible**.
3. Design instance counts, VM SKUs, Availability Zones, networking, and load balancing.
4. Select images, startup configurations, and application state storage sources.
5. Design autoscale based on metrics or schedules, capacity bounds, and cooldowns.
6. Organize health probes, upgrades, rollbacks, scale-in, and failed instance handling.
7. Protect VMSS with identity, Azure RBAC, NSGs, secret management, and monitoring.
8. Create a lab VMSS, test scale-out/scale-in, and evaluate costs.

## 2. Core concepts of Virtual Machine Scale Sets

VMSS is an Azure resource that holds orchestration information for **VM instances**. Depending on the model, each instance is created from a shared VM profile or managed more flexibly. You manage **desired capacity** rather than treating every VM addition or removal as a separate infrastructure project.

| Concept | Meaning | Example |
|---|---|---|
| VMSS | Resource that manages a group of virtual machines | vmss-api-prod |
| Instance | A member VM of the group | Instance serving API in zone 1 |
| Capacity | Target number of VMs | 3 |
| VM size / SKU | CPU, RAM, network, and I/O limits | An SKU with 2 vCPUs and appropriate RAM |
| VM image | Operating system and initial configured platform | Linux image with Java runtime |
| Orchestration mode | How instances are orchestrated | Uniform or Flexible |
| Autoscale | Mechanism to change capacity | High CPU triggers adding VMs |
| Upgrade policy | How model/image changes are rolled out | Batched upgrades when supported |
| Health signal | Information indicating whether the VM/application is ready | HTTP /health/ready |
| Availability Zones | Distributing machines across fault zones in a region | Zones 1, 2, and 3 |

A VM in the **Running** state does not guarantee that the Java application on it is serving requests. A VMSS with capacity 4 does not guarantee 4 **healthy** backends either. Therefore, in operations, you must distinguish **orchestration target, VM provisioning state, and actual serving capacity**.

VMSS does not automatically back up databases, synchronize sessions, or guarantee that an application survives VM deletion. These requirements must be designed at the application and data layers.

## 3. Reference architecture of an application running on VMSS

~~~mermaid
flowchart TD
    USER[Clients or API callers] --> GATEWAY[Load Balancer or Application Gateway]
    subgraph VNET[Azure Virtual Network]
        GATEWAY --> I1[VMSS Instance 1]
        GATEWAY --> I2[VMSS Instance 2]
        GATEWAY --> I3[VMSS Instance N]
        I1 --> DB[(Shared Database)]
        I2 --> DB
        I3 --> DB
        I1 --> STORAGE[(Blob Storage / Queue)]
        I2 --> STORAGE
        I3 --> STORAGE
    end
    MON[Azure Monitor Autoscale] --> SCALE[VM Scale Set]
    SCALE --> I1
    SCALE --> I2
    SCALE --> I3
~~~

For example, a development team deploys a Java API onto a VMSS with an initial capacity of 2:

- Instances use the same application version and expose an HTTP endpoint.
- Azure Load Balancer or Application Gateway distributes requests to healthy backends.
- Databases and critical files do not reside solely on the OS disk of a single instance.
- Azure Monitor tracks metrics to increase capacity during sustained load.
- When one instance fails, the application can still serve traffic using other instances, provided redundancy is designed in.
- During scale-in, removed machines do not cause loss of transactions or durable data.

The diagram above is a logical model. Using multiple ingress tiers is not mandatory. For L4, **Azure Standard Load Balancer** is commonly considered; for HTTP/HTTPS routing and WAF, **Application Gateway**; for global application delivery, **Azure Front Door**.

## 4. Orchestration modes: Uniform and Flexible

This is a critical technical decision because instance behavior, upgrades, and management tool usage can differ.

### 4.1. Uniform orchestration

**Uniform** is designed around managing a set of VMs with a shared configuration. It is typically suitable when all instances need to use the same VM model, image, and operational workflow.

Strengths:

- Relatively uniform deployment model.
- Convenient when stateless applications are packaged into a single image.
- Supports VMSS lifecycle, monitoring, scaling, and upgrade capabilities according to the mode's features.

Points to verify:

- Model changes do not necessarily affect each existing instance immediately.
- Model/instance update workflows differ from standalone VMs.
- Certain networking, placement, and per-machine management capabilities are scoped by the orchestration mode.

### 4.2. Flexible orchestration

**Flexible** aims for more flexible management of member VMs and provides an operational experience closer to standard Azure VMs.

Strengths:

- Advantageous when individual member VMs need to be managed or observed.
- Supports designs that distribute across Availability Zones or combine VM sizes under conditions supported by Azure.
- Suitable for scenarios that combine capacity management with relatively independent VM lifecycles.

Points to verify:

- Not every Uniform command, API, extension, upgrade policy, or automatic repair applies identically to Flexible.
- Some operations may target member Azure VM resources directly rather than Uniform instance management syntax.
- Support must be verified for each VM SKU, region, mode, and tool version.

### 4.3. Comparison table

| Requirement | Uniform | Flexible |
|---|---|---|
| Many instances with nearly identical configuration | Usually suitable | Also suitable |
| Need instance management close to standalone VMs | Follows Uniform model capabilities | Usually more convenient |
| Flexibility in VM sizing/placement as supported | Not the primary goal | May be more suitable |
| Autoscale | Integrated per mode capabilities | Integrated per mode capabilities |
| Rolling upgrade | Follows supported policies/features | Must verify specific supported flows |
| Zone/fault domain distribution | Must be explicitly configured | Must be explicitly configured |

**There is no universal default choice for every product.** Choose a mode based on actual required behavior and features, not just the name. For a lab with a homogeneous web server group, Uniform is an easy model to demonstrate if supported by the environment.

## 5. Designing desired capacity and redundancy

For a VMSS to truly scale elastically, three questions must be answered:

1. What is the **minimum number of VMs** needed for the service to operate safely?
2. During peak hours, what is the **maximum number of VMs** that might be needed?
3. When scaling up or down, **how long does it take for an instance to actually receive traffic**?

Example:

| Parameter | Illustrative value | Reason |
|---|---:|---|
| Minimum | 2 | Keep two application instances during low load |
| Default | 2 | Starting level |
| Maximum | 8 | Autoscale scale limit |
| Increment | 1 VM | Step-by-step changes that are easy to observe |
| Baseline load | 150 requests/second | Assumed figure for design testing |
| Peak load | 600 requests/second | Scenario requiring scale-out |

Suppose load testing shows one VM handles **100 requests/second** at a latency meeting the SLO. A load of 600 requests/second might require at least 6 VMs under ideal conditions, plus an appropriate redundancy margin. However, capacity should not be estimated by simple division while ignoring the database, long requests, sessions, warm-up effects, or load skew.

### 5.1. Do not confuse desired with available

Azure may be creating a new VM without having finished installing the application. During that time, the dashboard shows a higher target capacity than before, yet the API is still bearing load on the old instances.

**Time-to-ready** is a metric to measure: from the moment autoscale decides to increase capacity until the new instance receives real requests and responds successfully.

### 5.2. Minimum does not equal HA

Two VMs reduce the risk of a single machine failure, but they can still sit in the same fault domain, share a non-redundant database, or all fail due to a bad image. Achieving HA requires layered design and failure drills.

## 6. Availability Zones and fault domains

### 6.1. Availability Zones

Some Azure regions support **Availability Zones**, infrastructure locations with independent components such as power, cooling, and networking. VMSS can distribute instances across multiple zones depending on the mode, VM SKU, configuration, and regional availability.

Design example:

~~~text
Region supporting multiple Availability Zones

Zone 1: API instances
Zone 2: API instances
Zone 3: API instances if configuration allows

Load balancing routes traffic to healthy instances.
~~~

Do not just set capacity=3 and assume there will be exactly one VM in each zone. You must configure and **verify actual placement**.

### 6.2. Fault domains

Fault domains describe how resource sets are partitioned to reduce risk from shared hardware/infrastructure failures. Fault domain distribution behavior can differ between Uniform and Flexible. Verify details from actual deployments rather than assuming VMSS automatically satisfies fault tolerance requirements.

### 6.3. Availability of downstream services

If all instances across three zones call a database served from only one zone, a database failure can still take down the API. Review all of the following:

- Database redundancy and backups.
- Appropriate Blob/Queue availability.
- DNS and load balancers.
- Identity, Key Vault, and networking.
- Capacity in the remaining zones.

**Multi-zone does not replace multi-region disaster recovery.** When RPO/RTO requirements exist for region-wide outages, data, applications, and global routing must be designed separately.

## 7. Choosing VM size and workload type

### 7.1. API/web tier

VMSS is typically suitable when API instances can process requests independently, the application exposes a health endpoint, and state is stored outside the VM.

### 7.2. Background workers

Multiple instances read messages from Queue Storage or Azure Service Bus. Adding VMs increases concurrent processing capacity, but consumer concurrency, retries, and job idempotency must be controlled.

### 7.3. Batch processing

Each instance executes a portion of a data processing workload. Tasks are easier to rerun or checkpoint during scale-in, machine replacement, or error handling.

### 7.4. Workloads unsuitable for direct scaling

An application that stores an exclusive database on the OS disk, uses non-shareable local sessions, or requires a single primary node may not be suitable for scaling out identical VMs. Before creating a VMSS, resolve the stateful architecture or choose a different compute platform.

### 7.5. Choosing an SKU

Consider simultaneously:

- vCPU/RAM relative to the load profile.
- IOPS, disk throughput, and network bandwidth.
- Availability in the target region and Availability Zones.
- vCPU quota for the subscription/VM family.
- OS disk, data disk, ephemeral OS disk, and NVMe/temp disk.
- Compute cost and appropriate purchasing models.

A VM SKU with high disk IOPS does not guarantee a faster database if the bottleneck is the connection pool, application code, or network.

## 8. Choosing OS disk, data disk, and state storage

VMSS instances have frequently changing lifecycles. This affects where data should be written.

| Data type | Where should it be stored? | Reason |
|---|---|---|
| OS and runtime | OS disk or ephemeral OS disk if suitable | Created from VM image |
| Non-secret config files | Image, versioned config, or centralized management | Consistent reproduction |
| User sessions | External cache/database per architecture | Not tied to one instance |
| Uploaded files | Blob Storage or appropriate durable service | Not lost on scale-in |
| Production database | Durable data service or dedicated cluster system | Independent of OS disk |
| Job checkpoints | Blob/Queue/database per application | Enables retries |
| Regenerable cache | Temporary/local disk if supported by VM | Does not need durable persistence |
| Important logs | Azure Monitor/Log Analytics or centralized destination | Retained when VM is deleted |

**Ephemeral OS disk** can be useful for stateless workloads and fast instance recreation, but it is unsuitable if changes on the OS disk must persist across reimage/replace/deallocate events under service constraints. Likewise, temporary disks must not be treated as storage for critical data.

Select VM size, image, and features based on actual support before enabling ephemeral OS disks.

## 9. Images and startup configuration

To scale out reliably, you need a consistent and fast way to create instances.

### 9.1. Image sources

- **Marketplace image:** prebuilt Linux/Windows, followed by application installation.
- **Custom image:** pre-baked runtime, packages, and configuration.
- **Azure Compute Gallery:** manages image definitions/versions, reuse, and distribution suitable for multi-environment systems.

### 9.2. Clearly versioned images

A good deployment pipeline:

1. Build the Java application artifact.
2. Create a tested, versioned image/package.
3. Run security and integration checks.
4. Update the VMSS model/deployment source.
5. Apply the upgrade using an appropriate workflow.
6. Verify application health.
7. Maintain a rollback plan to the previous version.

Do not SSH into an instance to edit files and treat that as the standard configuration. New instances created during scale-out or reimage may not receive manual changes.

### 9.3. cloud-init and extensions

On Linux, cloud-init can install packages or run commands at boot time.

Example for a lab environment, not a complete production configuration:

~~~yaml
#cloud-config
package_update: true
packages:
  - nginx
runcmd:
  - systemctl enable nginx
  - systemctl start nginx
~~~

VM extensions can be used to configure or install agents per supported capabilities. Consider startup duration, execution permissions, extension error logs, and compatibility with the orchestration mode.

**Do not embed production passwords, keys, or connection strings** inside images, cloud-init, or repositories. Use managed identity, Key Vault, and secure configuration delivery mechanisms.

## 10. Designing VNet, subnet, and load balancing

### 10.1. VNet and subnet

VMSS is typically deployed into a subnet within an Azure Virtual Network. The subnet's IP address space must accommodate the maximum number of instances, NICs, other resources, and growth margin.

Example:

~~~text
VNet: 10.30.0.0/16
Application subnet: 10.30.10.0/24
VMSS: min 2, max 8
~~~

Depending on the environment, account for Azure-reserved IPs and remaining allocatable IPs in the subnet. A subnet that is too small can cause scale-out failures even when VM quota is sufficient.

### 10.2. Choosing ingress

| Component | Purpose | Example |
|---|---|---|
| Azure Standard Load Balancer | L4 TCP/UDP | API on VMSS with TCP frontend |
| Application Gateway | L7 HTTP/HTTPS, host/path routing, WAF if configured | Web/app with TLS and complex routing |
| Azure Front Door | Global application delivery service at the edge | Multi-region HTTP/HTTPS |

You do not need to combine all three for a working VMSS. Base the choice on TLS, WAF, scale, and traffic patterns.

### 10.3. Backend pool and health probe

For load balancing to work:

1. Create a frontend (public or internal).
2. Create a backend pool for the VMSS instances.
3. Configure a valid health probe.
4. Create rules forwarding traffic to the application port.
5. Configure NSGs and firewalls.
6. Verify that backends are considered healthy before sending traffic.

A VM that has not started the application should not receive requests merely because VM provisioning succeeded.

### 10.4. Outbound traffic

VMSS instances may need to download packages, fetch secrets, connect to databases, or send telemetry. Design an explicit outbound path, such as NAT Gateway or a firewall as required. Avoid relying on implicit/default outbound access because behavior varies by network type and platform policies.

Individual public IPs per instance are not needed just to update packages. Unless there is a specific reason, administer VMs via Azure Bastion or controlled private access paths.

## 11. Health checks: readiness and liveness

A VM may be running fine while the Java application has not started, is deadlocked, or cannot reach dependencies. Therefore, distinguish:

| Signal | Meaning |
|---|---|
| Provisioning state | Has Azure successfully provisioned the VM? |
| Liveness | Is the process/application still running? |
| Readiness | Is it qualified to receive new requests? |
| Load balancer health | Does the backend meet criteria to receive connections? |
| Application health for VMSS | Application signal used by supported repair/upgrade workflows |

An application can implement:

~~~text
GET /health/live  -> 200 when the process is still running
GET /health/ready -> 200 when the application is ready to receive traffic
~~~

During boot, readiness should report not ready until startup and essential dependencies complete.

**Do not make a health endpoint blindly return HTTP 200.** If the API loses its ability to handle core business logic, the health signal must allow the system to detect it. However, a slow non-critical secondary dependency should not cause all instances to become unhealthy simultaneously.

### 11.1. Application Health Extension and repair

VMSS can use the Application Health Extension or equivalent health mechanisms in supported configurations to assist rolling upgrades and automatic repairs. Restart/reimage/replace behaviors, grace periods, and prerequisites depend on the mode/OS/SKU.

For stateless workloads, replacing an unhealthy instance is usually appropriate. For workloads with unique data stored on the machine, repair can cause data loss or increased errors.

## 12. VMSS Autoscale

**Azure Monitor autoscale** can adjust capacity when metric or schedule conditions are met, depending on the VMSS type and supported features.

~~~mermaid
flowchart LR
    METRIC[CPU / queue metric / schedule] --> RULE[Autoscale rules]
    RULE --> DECIDE{Increase or decrease?}
    DECIDE -->|Scale-out| MORE[Create additional instances]
    DECIDE -->|Scale-in| LESS[Remove instances]
    MORE --> READY[Boot, initialize, and healthy]
    LESS --> DRAIN[Stop accepting work, terminate VM]
    READY --> BACKEND[Backend pool]
    DRAIN --> BACKEND
~~~

### 12.1. Capacity bounds

- **Minimum:** the lowest target instance count autoscale is configured to maintain for the environment.
- **Maximum:** upper limit for automatic capacity.
- **Default:** default capacity within the profile mechanism when corresponding conditions do not apply.

Actual instance counts may differ from desired capacity during upgrades or failures caused by quotas, disks, images, NICs, or zones.

### 12.2. Metric-based autoscale

Example policy:

- Average CPU exceeds **70% for 10 minutes** → add 1 VM.
- Average CPU falls below **30% for 20 minutes** → remove 1 VM.
- Wait for **cooldown** between actions so the system has time to stabilize.

These are only illustrative thresholds. When an application bottlenecks on a database, CPU may stay low even as request timeouts rise. Custom metrics or more meaningful metrics can be used if supported by the tooling.

### 12.3. Scheduled autoscale

When peak hours or batch runs are known in advance, schedules can be used to set target capacity or switch profiles over time. Verify timezones, holidays, actual utilization, and behavior when a schedule rule ends.

### 12.4. Manual capacity

Capacity can be increased or decreased manually via the Portal or CLI when permitted. If autoscale is active, manual values may be adjusted back by rules; do not treat manual operations as permanent configuration.

## 13. Designing autoscale rules to avoid oscillation

A poorly designed rule can create a loop: CPU rises → add VM → CPU drops → delete VM → CPU rises again. Continuous VM creation/deletion wastes money and disrupts sessions and caches.

Example target configuration:

| Property | Learning value |
|---|---|
| Min / Default / Max | 2 / 2 / 8 |
| Scale-out | CPU avg > 70% over 10 minutes |
| Scale-out action | +1 VM |
| Scale-in | CPU avg < 30% over 20 minutes |
| Scale-in action | -1 VM |
| Cooldown | 10 minutes |
| Protected instances | Define if special workloads exist |

To make rules more stable:

1. Separate scale-out and scale-in thresholds sufficiently.
2. Use meaningful observation windows.
3. Account for boot time and JVM warm-up.
4. Scale in more slowly than scaling out if long-running requests exist.
5. Maintain a minimum for baseline load.
6. Use health and error rates to confirm scale-out actually helps.
7. Monitor costs when capacity remains near maximum for extended periods.

Metrics can arrive late or have missing data; understand fallback/condition behavior in the actual profile before deploying to production.

## 14. Capacity planning for a Java API

Suppose one VM handles up to 120 requests/s within the application's acceptable latency limit.

~~~text
Actual traffic: 480 requests/s
Theoretical capacity per VM: 120 requests/s
Theoretical VM count: 480 / 120 = 4 VMs
~~~

The figure above has no redundancy margin. When one VM fails or an instance is upgrading, the remaining 3 VMs may not suffice. In addition:

- The database may not handle additional connections.
- JVM warm-up and caches take time.
- Requests do not have equal CPU cost.
- A client might hold connections open for a long time.
- The load balancer has distribution skew.
- The VM size has network and disk I/O limits.

Run **load tests** to measure throughput, p95/p99 latency, error rate, and resource usage. Then set min/max and thresholds based on SLOs, not simple theoretical arithmetic.

## 15. How is a new VM created during scale-out?

General workflow:

~~~text
Azure Monitor decides to increase capacity
  -> Azure checks quota/zone capacity
  -> Provision VM, NIC, and disk
  -> Boot OS from image
  -> Run cloud-init/extensions/startup
  -> Application loads configuration and starts
  -> Readiness/health criteria met
  -> Load balancer places instance into backend to receive requests
~~~

The VM count may increase in the Azure Portal before the application serves requests. Common failure points:

- Insufficient vCPU quota.
- SKU out of capacity in the zone.
- Broken or inaccessible image version.
- Subnet out of IP addresses.
- VM lacks outbound access to download dependencies.
- Managed identity lacks permission to read Key Vault.
- Database/firewall blocks connections.
- Health probe has wrong path or port.
- Startup script fails silently without monitoring.

**Time-to-ready** is a milestone to measure. If provisioning takes several minutes, maintain buffer capacity and scale out early enough; scaling only after users experience errors will fail experience goals.

## 16. Safe scale-in and handling in-flight work

Scale-in reduces resources and cost, but it can terminate an instance currently processing work.

### 16.1. HTTP workloads

- Use connection draining/handling capabilities supported by the ingress.
- Instances scheduled for termination stop accepting new requests according to the designed plan.
- Sessions must not depend on a single instance's memory.
- Critical requests must have safe retry and idempotency mechanisms where needed.

### 16.2. Queue workers

- Stop picking up new jobs before shutting down.
- Allow in-flight jobs to finish within a valid grace period.
- Acknowledge/delete messages only after data has been durably written.
- If a worker stops abruptly, messages may be redelivered; workers must tolerate retries.
- For long jobs, checkpoint to durable storage.

### 16.3. Instance protection

Some VMSS modes/configurations support protecting instances from scale-in or specific operations. Use this only when genuinely needed; protecting too many machines can prevent autoscale from reducing capacity, increasing costs.

### 16.4. Local data

Do not store critical application data solely on the OS disk, ephemeral OS disk, or temporary disk of an instance that may be replaced. Scale-in, reimage, and replace can wipe local changes.

## 17. Stateless applications and stateful dependencies

A **stateless tier** can process requests on any instance. State that must persist is offloaded to appropriate services:

| State | Appropriate storage location |
|---|---|
| Sessions or critical caches | External cache or database depending on architecture |
| Transactional data | Azure SQL, managed database, or durable system |
| Uploaded files | Blob Storage or managed storage |
| Queues and retries | Queue Storage/Service Bus depending on features |
| Secrets | Azure Key Vault and appropriate identity |
| Logs/audit | Azure Monitor or centralized log destination |

If all VMs in the group depend on a single data service without HA, adding VMs only adds compute without making the overall application fault-tolerant.

A practical architecture must define **RPO, RTO, and failure domains** not only for VMSS, but also for databases, storage, networking, and identity.

## 18. Upgrades and version management

Changing the VMSS model/image does not mean every instance immediately changes in the same way. Behavior depends on orchestration mode and upgrade policy.

Common concepts:

- **Manual:** operators actively apply changes to instances.
- **Automatic:** Azure applies changes according to the corresponding automatic policy.
- **Rolling:** updates in groups/batches with associated health conditions and limits, when supported.

Do not assume all three modes have identical capabilities and behavior across Uniform, Flexible, all SKUs, and all regions.

### 18.1. Rollout process

1. Build the new application image/package.
2. Verify the new version in a staging environment.
3. Update the model using a compatible mechanism.
4. Apply the upgrade to small groups or batches if supported.
5. Check health, error rates, latency, and resource usage.
6. Proceed if criteria pass; halt/rollback if errors are detected.
7. Verify instance count and image version after rollout.

### 18.2. Rollback and database migrations

Rolling back code does not automatically roll back database schemas. If a new version makes incompatible data changes, running mixed old/new versions during a rolling upgrade can fail. Maintain a backward-compatible schema migration strategy and a separate data recovery plan.

### 18.3. Reimage/replace

Reimage and replace can wipe local changes and recreate the OS/application environment from the source configuration. Design workloads so these operations can run without losing data that must be preserved.

## 19. Automatic repairs and upgrades are two different things

| Goal | Tool/mechanism | Meaning |
|---|---|---|
| Scale with load | Autoscale | Increase/decrease capacity |
| Upgrade app/OS | Upgrade policy, deployment pipeline | Roll out a new version to the group |
| Handle unhealthy instances | Health and repair per supported capabilities | Recover failed instances |

A broken image can cause every new instance to fail; automatic repair by creating more instances from the same broken image will not solve the root cause. Similarly, autoscale may add VMs when a database is bottlenecked without helping process more requests.

Monitoring and runbooks are needed to distinguish infrastructure failures, image failures, application failures, and downstream service failures.

## 20. Securing VMSS

### 20.1. Identity and Azure RBAC

Prefer **managed identity** for applications needing to read Blob, access Key Vault, or call Azure APIs supporting Microsoft Entra authentication. Grant Azure RBAC roles following least privilege.

For example: an API that only downloads files from Blob Storage does not need Owner on the entire subscription.

### 20.2. Administrative access

Restrict SSH/RDP over the Internet; consider Azure Bastion, private networks, or secure machine management mechanisms. Accounts with permission to modify the VMSS model, image, or capacity can impact the entire system, so enforce permission controls/approval/PIM where appropriate.

### 20.3. Operating system protection

- Use updated images with a patching process.
- Configure NSGs and firewalls to open only necessary ports.
- Never hardcode secrets into images/cloud-init.
- Consider Defender for Cloud and Azure Policy for security assessment.
- Collect audit/guest logs centrally.
- Verify Storage/DB access via private endpoints and DNS where appropriate.

### 20.4. Secure outbound

Use NAT Gateway or a controlled egress solution if the application needs outbound connectivity. Do not casually attach public IPs to all instances for administrative convenience.

## 21. Monitoring performance and instance state

| Data type | Example metrics | Question answered |
|---|---|---|
| VMSS capacity | Desired vs running/provisioning/healthy | Does the group have enough serving machines? |
| Compute | CPU, guest RAM metrics, network, disk | Where are resources constrained? |
| Application | Request rate, latency, error rate, JVM metrics | Are users impacted? |
| Autoscale history | Scale decisions, cooldown, errors | Why did instances scale up/down? |
| Health/repair | Unhealthy instances, repair actions | Are VMs failing repeatedly? |
| Deployment | Image/extension errors, upgrade states | Did the release succeed? |
| Dependencies | DB latency, queue backlog, storage errors | Where is the bottleneck outside VMSS? |
| Cost | VMs by SKU/region, disks, IPs, NAT, logs | Are there unexpected costs? |

**Low CPU does not mean the system does not need scaling.** An API may be waiting on a database or network; queue backlogs may still grow. Conversely, high CPU caused by a code loop bug is not necessarily solved by adding VMs.

Azure Monitor alerts can be configured when:

- Healthy instance count drops below a safe threshold.
- Scale-out fails due to quota.
- Capacity repeatedly hits maximum.
- 5xx/error rate rises after an upgrade.
- An instance is repaired multiple times.
- Queue backlog or job latency exceeds SLO.

Guest memory or application metrics may require separate agents/instrumentation; do not assume the Azure Portal always provides them out of the box.

## 22. Cost control and quotas

The cost of a VMSS is not just the number of VMs.

| Category | Cost examples |
|---|---|
| Compute | VM SKU, instance count, runtime duration |
| OS/data disks | Managed disks by tier and capacity |
| Network | Load Balancer, Public IPs, NAT Gateway, Firewall, bandwidth |
| Images | Storing/replicating images in Azure Compute Gallery |
| Monitoring | Log ingestion, retention, and monitoring tools |
| Data | Databases, Blob, Queue, cache, backups |

Autoscale helps reduce idle VM runtime during low load, but **minimum capacity** and associated resources may still incur ongoing costs.

### 22.1. Quotas and actual capacity

Subscriptions have vCPU quotas per region and VM family. When hitting a quota or lacking capacity in a zone, scale-out requests can fail. Make sure to:

1. Check quotas before launch day.
2. Monitor scaling/provisioning failures.
3. Choose SKUs and regions with adequate supply.
4. Set maximums within budget plans.
5. Create Azure Cost Management alerts.
6. Consider appropriate pricing models for steady-state and batch workloads.

### 22.2. Spot VMs for batch

**Azure Spot VMs** can suit eviction-tolerant workloads, such as file conversion, rendering, or checkpointed batch processing. Do not use Spot as the sole compute for continuous services unless you have fault tolerance and replacement capacity plans.

Spot policies, mixing regular/Spot, pricing, and eviction behavior depend on the features supported by Azure in the mode/SKU used.

## 23. Azure Portal: creating a lab VMSS

**Prerequisites:** have a subscription and permissions to create VMSS/network/disks, remaining quota for the VM family, an approved lab budget, and do not use a production environment.

Procedure:

1. In the **Azure Portal**, open **Virtual Machine Scale Sets → Create**.
2. Select a subscription and a dedicated resource group, e.g. **rg-vmss-lab**.
3. Name it **vmss-api-lab**, choose the region and orchestration mode per design.
4. Select a supported Linux image and a budget-appropriate VM size.
5. Set initial instance count to **2**.
6. If supported by the region/SKU, configure Availability Zones distribution.
7. Configure an SSH key or secure administrative method.
8. Select a VNet/subnet with enough IPs for maximum capacity.
9. Choose appropriate ingress, connect the backend pool and health probe.
10. Set up cloud-init/extension with test application content.
11. Review networking, disks, identity, and estimated cost before creating.
12. Wait for deployment to complete and inspect instance statuses.
13. Verify that both backends are actually healthy and serving a test URL.

For an initial lab, Nginx can serve as a simple web server; when moving to a Java API, test JVM startup, health, and real dependencies.

## 24. Azure CLI: observing and changing capacity

Illustrative commands for an **existing** VMSS. Replace resource group/scale set names according to your lab.

~~~bash
az login
az account set --subscription "<subscription-id>"

az vmss show \
  --resource-group rg-vmss-lab \
  --name vmss-api-lab \
  --query "{name:name,capacity:sku.capacity,vmSize:sku.name,orchestrationMode:orchestrationMode}" \
  --output json
~~~

For modes supporting the VMSS instance management API:

~~~bash
az vmss list-instances \
  --resource-group rg-vmss-lab \
  --name vmss-api-lab \
  --output table
~~~

Change desired capacity with an illustrative command:

~~~bash
az vmss scale \
  --resource-group rg-vmss-lab \
  --name vmss-api-lab \
  --new-capacity 3
~~~

Note: commands and member VM management differ by orchestration mode. With Flexible, verify the appropriate CLI/API before operating; do not assume all Uniform commands are compatible.

**A command-level scaling success does not prove the new VM is healthy.** Monitor provisioning, health, backend status, and real requests afterward.

If autoscale is enabled, the controller may continue adjusting capacity according to its profile. When practicing manual scaling, note active rules to avoid confusion.

## 25. Illustrative autoscale policy

This is pseudoconfiguration expressing a learning policy, **not YAML that can be deployed directly to Azure**:

~~~yaml
autoscale:
  minInstances: 2
  defaultInstances: 2
  maxInstances: 8
  rules:
    - metric: "Percentage CPU"
      condition: "average > 70% during 10 minutes"
      action: "increase by 1 instance"
      cooldown: "10 minutes"
    - metric: "Percentage CPU"
      condition: "average < 30% during 20 minutes"
      action: "decrease by 1 instance"
      cooldown: "10 minutes"
  schedule:
    note: "Peak-hour profiles can be added"
~~~

To implement, use Azure Monitor Autoscale configuration in the Azure Portal, Bicep/ARM, or CLI according to the current version's real schema.

### 25.1. How to test rules

1. Verify that the source metric has data.
2. Generate bounded test load in a sandbox.
3. Wait for the full observation window.
4. Check autoscale history and scale actions.
5. Track the new VM from provisioning to application readiness.
6. Stop the load and observe cooldown/scale-in.
7. Record error rates and costs, not just VM counts.

Do not run uncontrolled stress tests on shared subscriptions. Cap max capacity, load duration, and budget.

## 26. Example of deploying a batch processing worker

An image processing system has thousands of input files:

~~~mermaid
flowchart TD
    SRC[Blob input] --> Q[Work queue]
    Q --> VMSS[VMSS workers]
    VMSS --> OUT[Blob output]
    VMSS --> MET[Queue backlog and processing metrics]
    MET --> AUTO[Autoscale]
    AUTO --> VMSS
~~~

### 26.1. Processing rules

- Each message contains a job ID and file reference.
- The worker receives the message, processes it, and writes output durably.
- Delete/ack the message only after writing results successfully.
- If an instance is interrupted, the message may be reprocessed.
- Workers must be idempotent so retries do not create erroneous duplicates.
- For long jobs, checkpoint and handle timeouts appropriately.

### 26.2. Scaling by backlog

CPU may not be suitable if workers wait heavily on I/O. Pending message count or message age may better reflect demand. If using custom metrics or an adapter component, verify the metric emission mechanism and Azure Monitor autoscale's ability to ingest that signal.

### 26.3. When to use Spot?

Suitable when jobs can restart; unsuitable if losing one VM loses all non-reproducible results. Retry workflows must tolerate sudden eviction.

## 27. Rolling upgrade operations checklist

Before an upgrade:

- Clearly versioned and tested image/package is ready.
- New instances have reliable startup/readiness.
- Load balancer excludes unhealthy backends from new traffic.
- Minimum capacity is sufficient to serve while a batch is being replaced.
- Database schema supports concurrent old and new versions.
- Stop conditions exist based on error rate/latency.
- Rollback plan and on-call owner are assigned.
- Rolling upgrade support is verified for the orchestration mode in use.

During the upgrade, monitor each batch and **do not continue automatically if health fails** under the configured policy.

After the upgrade, verify the actual image version and capacity/health of all instances. Document an incident if unexpected behavior occurred.

## 28. Common issues

### 28.1. VMSS does not increase the number of VMs

Rules may not have crossed thresholds, cooldown may still be active, maximum may be reached, quota may be insufficient, region/zone may lack capacity, subnet may be out of addresses, or image/extension may have failed. Inspect autoscale decisions and provisioning events.

### 28.2. New VMs do not receive requests

Often caused by the app not running, readiness not met, wrong backend pool, NSG blocking traffic, or health probe using the wrong port/path. Do not fix this by arbitrarily disabling the health probe.

### 28.3. Adding VMs makes the API even slower

A database with an exhausted connection pool or lock contention can become overloaded when more VMs access it concurrently. Check dependencies before scaling out further.

### 28.4. Scale-in causes data loss

The application stores critical files on local disk, jobs terminate without checkpointing, or messages are acknowledged before output is written. Fix state/retry workflows and drain design.

### 28.5. Model is updated but instances remain on the old version

Check the upgrade policy and rollout status. Updating the model does not necessarily update the image/software of existing VMs automatically.

### 28.6. Only one VM is healthy after a zone failure

Zone distribution was configured improperly or shared dependencies also failed. Inspect actual placement and the entire application path, not just VMSS.

### 28.7. Unexpected cost increase

Autoscale may keep capacity near maximum, unhealthy instances may be recreated in a loop, or disks/logs/NAT may incur charges. Track actual capacity, Azure Cost Management, and scale events.

### 28.8. Managed identity cannot retrieve secrets

Check role assignments, Key Vault policies, Private Endpoints, DNS, outbound access, and startup ordering. Never embed secrets in images to bypass permission errors.

## 29. Phased hands-on lab

**Context:** a sample API/web service running on VMSS in a lab resource group. The goal is to observe scale-out, scale-in, and application serving behavior.

### Phase A: design

1. Draw a topology including VNet, subnet, VMSS, ingress, health endpoint, and a mock data service.
2. Choose Uniform/Flexible and state the reason.
3. Choose 2 initial instances, min 2, max 4.
4. Choose a common Linux image and a VM SKU suitable for the lab.
5. Define budget limits and a cleanup plan.

### Phase B: deployment

1. Create the VMSS in the Azure Portal.
2. Install and start the web service on all instances.
3. Connect the backend pool/probe properly.
4. Verify each instance is healthy and the shared endpoint returns content.
5. Verify no individual public IP is needed per VM when ingress is present.

### Phase C: manual scaling

1. Increase capacity from 2 to 3.
2. Record timestamps for the action, provisioning, and readiness.
3. Verify the third instance receives requests.
4. Scale back down to 2 when no critical jobs remain.
5. Verify the application still responds after scale-in.

### Phase D: autoscale

1. Enable autoscale configuration with min 2 and max 4.
2. Set a CPU metric and safe lab-appropriate thresholds.
3. Generate short, bounded load.
4. Monitor autoscale history, instance count, and health.
5. Stop load, wait for cooldown, and evaluate scale-in.

### Phase E: upgrade

1. Prepare a minor change to the web page/version.
2. Choose an update mechanism matching the active mode and configuration.
3. Observe versions across instances after rollout.
4. Document stop or rollback conditions if health fails.

### Phase F: reporting and resource cleanup

1. Record a table of target/actual capacity across timestamps.
2. Record time-to-ready, application errors, and probe status.
3. Evaluate quota and cost.
4. Clean up resources **belonging specifically to the lab** after checking ownership and dependencies.
5. Do not delete shared resources in the subscription.

**Completion criteria:** understand that VMSS orchestrates capacity, while load balancers and health determine whether instances actually receive traffic; applications must handle an instance disappearing.

## 30. Pre-production checklist

- [ ] Orchestration mode selected matches required features.
- [ ] Image/package has clear versioning and a rollback plan.
- [ ] VM SKU, quota, and zone capacity verified.
- [ ] Minimum capacity and autoscale thresholds based on load tests/SLOs.
- [ ] VNet/subnet has enough IPs for maximum scale.
- [ ] Ingress, NSGs, egress, and DNS properly designed.
- [ ] Health/readiness reflects actual serving capability.
- [ ] VM startup and time-to-ready measured.
- [ ] Scale-in has a safe plan to finish requests/jobs.
- [ ] Sessions and critical data do not reside solely on VMs.
- [ ] Managed identity and RBAC permissions follow least privilege.
- [ ] Monitoring covers autoscale, VMs, app, and downstream services.
- [ ] Tested losing an instance and zone-based HA plan.
- [ ] Upgrade policy, rolling health, and rollback tested.
- [ ] Alerts exist for scale failures, max capacity, unhealthy VMs, and 5xx errors.
- [ ] Budget, scale limits, snapshot/disk management, and cleanup plan exist.
- [ ] Separate DR strategy exists if region-wide fault tolerance is required.

## 31. Self-check questions

1. What capabilities does VMSS provide over manually creating three Azure VMs?
2. How do Uniform and Flexible differ in how instances are administered?
3. Why does capacity=3 not automatically guarantee one instance in each Availability Zone?
4. When a new VM is provisioned but health is not yet met, should it receive HTTP requests?
5. Why does high CPU not always mean adding more VMs is needed?
6. How do cooldown and the gap between scale-out/scale-in thresholds help?
7. When scaling in a queue worker, what mechanisms prevent losing jobs?
8. Where should a stateless API store sessions and uploaded files?
9. Why is manually editing files on one VMSS instance not a good application deployment practice?
10. If the deployment model has been updated but instances have not changed, what must be checked?
11. What roles do managed identity and Azure RBAC play when VMSS accesses Storage and Key Vault?
12. What risks does an API group using Spot VMs carry?
13. Which metrics and logs would you monitor to detect a scale-out failing to meet its goal?
14. When the database is the bottleneck, how can increasing the number of VMs make things worse?
15. To evaluate whether a VMSS truly has HA, besides instance count, what other components must be examined?

## 32. Summary

**Azure Virtual Machine Scale Sets** help orchestrate multiple virtual machines and adjust capacity to meet compute demand. However, **VMSS only manages infrastructure**: applications must be stateless or manage state properly; the system needs proper networking and ingress, reliable health signals, versioned images, safe scale-in/upgrade workflows, and tracking via Azure Monitor.

In Azure designs, combine **VMSS + load balancing + autoscale + Availability Zones + managed identity/RBAC + Storage/Database + monitoring + Cost Management**. Do not just check the count of created VMs; measure **time-to-ready**, serving capability when an instance is lost, application quality during scale-in/upgrades, and costs as load changes. That is the foundation for an elastic compute architecture that can be defended and operated reliably.
