# Dedicated Hardware Models and Software Licensing Requirements

## 1. The Dedicated Hardware Problem in the Cloud

Most cloud platforms deliver compute capacity on shared infrastructure. Multiple customers can run virtual machines on the same cluster of physical servers, while the provider is responsible for partitioning resources and isolating workloads. The shared model is flexible and cost-effective. However, some workloads require stronger hardware isolation, control over VM placement, consistent performance, or verifiable evidence of the exact physical servers running the software.

This is where **dedicated instance**, **dedicated host**, **sole-tenant node**, or **bare metal** models are evaluated. They reserve part or all of a physical server for a single customer, depending on the provider's implementation. Exclusive use of physical hardware can help meet isolation, audit, compliance, or enterprise software licensing terms.

Dedicated hardware does not automatically solve every requirement. Each model offers different levels of control over the server, CPU, hypervisor, and VM placement. At the same time, software licenses may be metered per user, device, instance, vCPU, physical core, socket, server, or entire cluster. Choosing the wrong tenancy model or misunderstanding the licensing metric can leave an organization paying high hardware costs while still failing software contract compliance.

In this lesson, you will:

- Distinguish between shared infrastructure, dedicated instances, dedicated hosts, sole-tenant nodes, and bare metal.
- Understand isolation levels, control, and operational responsibilities for each model.
- Identify software licensing metrics and how they relate to CPUs, hosts, VMs, and users.
- Design placement, scaling, availability, and recovery to comply with licensing terms.
- Calculate total cost of ownership and build evidence for license audits.

## 2. Foundational Concepts

### 2.1. Physical Hosts, Hypervisors, VMs, and vCPUs

A physical host is an actual computer containing CPUs, memory, network devices, and storage devices. In a virtualized environment, a hypervisor divides server resources into multiple virtual machines. Each VM sees a virtual hardware configuration and runs its own guest operating system.

Several terms must be distinguished:

- **Socket:** a physical CPU slot on a motherboard. A server may have one or more sockets.
- **Core:** a physical processing core inside a CPU. One CPU contains multiple cores.
- **Hardware thread:** an execution thread supported by the CPU through technologies like simultaneous multithreading (SMT). Two hardware threads on the same core are not equivalent to two physical cores.
- **vCPU:** a virtual CPU unit provided by the platform to a VM or container. How vCPUs map to cores or hardware threads depends on the provider and instance type.
- **NUMA:** an architecture where a CPU accesses nearby memory regions faster than remote memory regions. Large or latency-sensitive workloads can be affected by how CPUs and memory span NUMA nodes.

Never assume one vCPU always equals one physical core. On some platforms, a vCPU corresponds to one hardware thread; on others, representation and scheduling differ. Similarly, the core count shown inside a guest OS does not necessarily reflect the physical core count used for licensing. Rely on definitions in the cloud provider's documentation and the software vendor's contract.

### 2.2. Tenancy and Hardware Isolation

Tenancy describes how physical resources are allocated across customers. In shared tenancy, the provider may place VMs from multiple customers on the same host while isolating them via the virtualization layer and related security controls. In dedicated models, a server or portion of physical infrastructure is reserved for one customer under service terms.

**Hardware isolation** means a customer's workloads do not share physical servers with other customers' workloads within the committed scope. That differs from merely having one VM on a host at a single moment by coincidence. Read the exact tenancy definition in the cloud service: the dedicated scope may be an instance, host, node group, rack, or specific resource zone.

Dedicated hardware also does not mean a server can run only a single workload. Customers can run many of their own VMs on a dedicated host. They can also install their own hypervisor on a bare-metal server if the service and contract permit.

## 3. Dedicated Hardware Models

### 3.1. Shared Infrastructure (Shared Tenancy)

In shared tenancy, multiple customers share a physical server cluster. The hypervisor and cloud control plane handle partitioning CPU, memory, networking, and storage. Customers usually manage only their provisioned VMs or compute services, without knowing which exact physical host a VM runs on.

Shared tenancy excels in easy provisioning, elastic scale-up/scale-down, and typically lower starting costs. Providers can pool resources across the cluster to maximize utilization. This is usually suitable for web apps, dev environments, internal services, and most standard workloads.

Limitations include low host control, lack of host IDs or exact physical hardware details, and potential exposure to shared-resource contention depending on instance type and provider policy. Shared tenancy may not satisfy software clauses requiring installation on designated servers or verifiable hardware boundaries.

### 3.2. Dedicated Instance

A dedicated instance runs on hardware reserved for a single customer as defined by the provider. Customers may receive host-level isolation at the instance tier without necessarily being able to pick a specific host, inspect full socket/core metadata, or control placement relative to other instances in the same account.

A key characteristic is **higher isolation while host control remains limited**. The provider may choose which physical server hosts the instance and relocate it during maintenance. Some services support affinity or hardware metadata visibility; others do not. Do not infer those capabilities solely from the name "dedicated instance."

Dedicated instances fit when the main requirement is isolation from other customers. If the goal is tracking physical core counts, binding licenses per host, auditing host IDs, or pinning software to a specific server, verify whether the service exposes the required metadata and placement controls.

### 3.3. Dedicated Host

A dedicated host is a physical server reserved exclusively for one customer. Customers can usually place multiple VMs onto that host and receive details such as host ID, machine family, sockets, core counts, or remaining capacity. Depending on the service, customers can choose host sizes, compatible instance families, affinity, anti-affinity, or placement controls.

Dedicated hosts are particularly useful when software licenses are billed per physical core, socket, or whole server. Knowing exactly which host runs each VM and controlling placement makes building license maps and audit evidence much easier. Dedicated hosts also satisfy requirements not to share physical servers with other customers.

In return, customers generally pay per host or per allocation duration, even if using only part of the CPU and memory. Scaling depends on available hosts, quotas, host provisioning times, and machine family constraints. Factor in idle capacity costs, HA spares, and replacement hosts for maintenance.

### 3.4. Sole-Tenant Node or Dedicated Node

Some providers use the term sole-tenant node to refer to a physical node dedicated to a single customer within a VM orchestration environment. Customers can deploy multiple VMs onto the node and use node affinity or node group policies to steer placement. Exact naming, hardware visibility, and billing vary across providers.

Sole-tenant nodes fit workloads needing a dedicated physical boundary while retaining cloud VM workflows and tooling. When evaluating them, verify whether the node qualifies as a dedicated host under your software contract. Some license agreements define host, server, processor, or hardware partition in specific legal terms; cloud service naming does not dictate contract interpretation.

### 3.5. Bare Metal

Bare metal delivers a physical server directly to the customer, typically without a provider-managed hypervisor between the customer interface and hardware. Customers can install their own OS, hypervisor, or container platform if the service allows. This model provides deeper control over CPUs, memory, network devices, and certain I/O characteristics.

Bare metal suits workloads needing steady performance, specialized hardware access, licenses or software requiring dedicated server environments, large databases, HPC, or customer-managed virtualization platforms. However, high control brings responsibility for managing the OS, hypervisor, patching, security hardening, monitoring, and recovery.

Bare metal does not automatically mean you cannot virtualize. Customers can install their own hypervisor and run VMs on the physical server. When doing so, clarify whether the software contract licenses at the bare-metal, hypervisor, host, or per-VM level.

### 3.6. Model Comparison Table

| Criterion | Shared Tenancy | Dedicated Instance | Dedicated Host / Sole-Tenant | Bare Metal |
|---|---|---|---|---|
| Dedicated scope | Host shared across customers | Instance guaranteed to run on dedicated hardware per service terms | Physical server/node reserved for one customer | Physical server provisioned directly to customer |
| Physical host visibility | Usually very limited | Varies by service; usually more limited than dedicated host | Usually exposes host ID and hardware details | Usually provides detailed server specs |
| Placement control | Low | Usually low to moderate | Often supports affinity, anti-affinity, or placement controls | Customer controls OS/hypervisor and workloads on assigned machine |
| Hypervisor management | Provider | Provider | Provider usually manages hypervisor | Customer-installed/managed or per service model |
| Host-based license suitability | Must verify; often hard to prove | Must verify host scope and control | Often favorable if contract and metadata align | Can be favorable if terms accept server structure |
| Resource utilization efficiency | High due to pooling | May leave unused capacity | Customer pays for provisioned host capacity | Customer is responsible for utilizing machine capacity |
| Operational effort | Lower at hardware layer | Low to moderate | Moderate; adds host and placement management | Higher when self-managing OS/hypervisor |

Naming and technical commitments are not uniform across providers. Cross-check service docs, cloud contracts, and software vendor terms before deciding.

## 4. Common Software Licensing Models

### 4.1. Per-User or Per-Device Licensing

Licenses can be counted by authorized users or devices using the software. This model is common in enterprise apps, access platforms, admin tools, and client/server products.

In the cloud, clarify whether users are counted as named users, concurrent users, indirect users, or service accounts. For device licensing, track physical devices, virtual devices, or endpoints as defined in the contract. Moving an application onto VMs does not eliminate user or device licensing obligations.

### 4.2. Per-Instance or Per-VM Licensing

Some software licenses by instance count, virtual server, or installed environment. Terms may cap maximum VMs, enforce minimum specs, restrict multi-copy runs, or bound dev/test environments.

This model requires tracking VM creation, cloning, snapshots, and launches. A temporary VM spun up for migration, testing, or autoscaling may still count as a licensed instance depending on contract terms. Never assume stopped VMs or short-lived VMs are automatically exempt from licensing.

### 4.3. Per-vCPU or Per-Allocated-VM-Core Licensing

Under virtual-core licensing, the number of vCPUs assigned to a VM can serve as the license basis. Contracts may impose minimum cores per VM, rounding rules, vCPU caps, supported CPU types, or VM mobility restrictions across hosts.

When using autoscaling, adding VMs or increasing vCPUs increases license consumption. Synchronize compute provisioning workflows with entitlement checks. Retain records of vCPU counts, change timestamps, software versions, and placement history.

### 4.4. Per-Physical-Core, Socket, or Processor Licensing

Some enterprise products meter licenses by physical cores, sockets, or processors on a server. In this case, counting only vCPUs inside a VM can result in under-licensing. Contracts may require licensing all cores on a host, all cores capable of running the workload, or a subset under specific rules.

This is where dedicated hosts or bare metal become critical. Customers need to know how many sockets/cores a physical host has, which hosts are licensed to run the software, and whether VMs can move to other hosts. When licenses tie to a host, live migration, host replacement during maintenance, or cluster scaling can alter licensing scope.

There is no universal rule that every core-based license requires licensing all physical cores, nor a universal rule that licensing only assigned VM vCPUs suffices. Calculations depend on the specific contract, version, edition, licensing program, and vendor cloud policy.

### 4.5. Per-Host, Per-Cluster, or Capacity-Based Licensing

Some products are licensed per server, per cluster, per storage capacity, per managed data volume, or per another capacity unit. Certain contracts require licensing an entire cluster if software *can* run on any node in that cluster. Other contracts count only nodes where software is actually installed or pinned.

Distinguish **where software is installed**, **where software can run**, and **where the contract requires licensing**. Those three scopes can differ. A 10-node cluster running a database on only 2 nodes might not require only 2 node licenses; terms may account for failover capability or workload mobility rights.

### 4.6. License-Included vs. BYOL

Two purchasing models are common in the cloud:

- **License-included:** compute or managed service fees already include usage rights for specific software. The cloud provider generally manages licensing within the stated service scope.
- **Bring Your Own License (BYOL):** customers bring pre-purchased licenses or separate agreements into the cloud. Customers must verify cloud deployment rights along with host, region, virtualization, mobility, and audit terms.

BYOL does not mean licenses bought for on-premises servers are always valid in the cloud. Some licensing programs allow migration or reassignment under specific conditions; others restrict providers, hardware, or transfer intervals. Obtain written confirmation from the software vendor or an authorized licensing partner.

### 4.7. Rights and Exceptions to Check

Contracts may include specific clauses for:

- License mobility across servers and minimum cooldown intervals between moves.
- Passive standby servers, failover nodes, or disaster recovery sites.
- Development, testing, staging, sandbox, and training environments.
- Running multiple versions, multiple containers, or multiple instances of the software.
- Using software in specific cloud regions, countries, or providers.
- Temporary usage during maintenance, host replacement, or region migration.
- Renewal terms, software assurance/maintenance, subscriptions, support, and eligible versions.

Never assume standby servers, stopped VMs, snapshots, image templates, or DR environments are license-exempt. Apply exceptions only when explicitly stated with conditions and scope in the contract.

## 5. Matching Hardware Models to Licensing Models

### 5.1. Initial Decision Matrix

| Need or Contract Term | Model to Evaluate | Evidence to Verify |
|---|---|---|
| Isolation from other customers only | Dedicated instance or dedicated host | Tenancy commitment, host scope, host replacement rules |
| License metered per physical core or socket | Dedicated host, sole-tenant node, or bare metal | Socket/core counts, host ID, CPU model, placement, and mobility rights |
| License metered per VM/vCPU | Shared or dedicated may fit | vCPU counts, minimums, VM history, and cloud eligibility |
| Need self-managed hypervisor | Bare metal or host service allowing custom hypervisor | Hypervisor install rights, firmware, drivers, devices, and vendor support |
| Need consistent CPU or I/O performance | Appropriately sized dedicated host or bare metal | Benchmarks, NUMA, CPU model, network bandwidth, and storage |
| Need host placement control for audits | Dedicated host or sole-tenant node with metadata | Host ID, inventory APIs, placement logs, and migration history |

This matrix is only for initial screening. Software terms and cloud service commitments are the basis for final decisions. For instance, a dedicated host may expose a host ID yet still fail to meet a contract's definition of a "designated server."

### 5.2. Example: Difference Between vCPU and Physical Cores

Suppose a system has 2 dedicated hosts, each with 2 sockets and 16 physical cores per socket—totaling 64 physical cores. On these hosts, a team runs 4 VMs, each assigned 8 vCPUs, totaling 32 vCPUs.

If a hypothetical contract requires licensing all physical cores of hosts where the software can run, the calculation base could be 64 cores. If another contract allows licensing per vCPU assigned to each VM, the base could be 32 vCPUs, after applying contractual minimums and rounding rules. Two formulas produce different license counts even though the application and VM specs stay identical.

This is purely an illustrative example to distinguish metering units. Do not use these numbers to determine licensing obligations for any real product. Always read the exact terms for your product, version, edition, licensing program, and cloud platform.

### 5.3. Placement, Affinity, and Anti-Affinity

Placement determines which host a VM runs on. When licenses bind to hosts, control placement to prevent software from running on unlicensed hosts.

- **Host affinity:** binds workloads to an authorized host or host group.
- **Host anti-affinity:** places workloads on separate hosts, usually to lower single-host failure risk.
- **Placement group/node group:** a physical or logical resource group used as a deployment and governance boundary.
- **Live migration:** moving a running VM from one host to another. This operation must be checked against license mobility rules, target hosts, and audit logs.
- **Host maintenance/replacement:** the provider replaces a host during maintenance or hardware faults. Verify whether the new host carries the same properties, host ID, and licensing scope.

If a contract allows running software only on a licensed host group, configure policies so workloads cannot fail over or drift automatically onto other hosts. For failover, pre-designate which standby hosts may receive workloads and verify licenses cover that scenario.

### 5.4. Clusters and Licensing Scope

When building a cluster, clearly define which nodes may run licensed workloads. If the scheduler can place VMs on any node, licensing scope may expand beyond currently active nodes. Separate node pools for software with specialized licensing, restrict deployment permissions, and enforce labels/taints or equivalent policies.

Node pool isolation requires multi-layer enforcement: IAM permissions, orchestration policies, deployment pipelines, quotas, and monitoring. Simply labeling nodes without blocking accidental scheduling or manual deployments is insufficient for compliance.

## 6. Designing Architecture with Licensing in Mind

### 6.1. Define Licensed Workload Boundaries

Classify software by licensing metric and criticality. Document which workloads need dedicated hardware, which can run on shared tenancy, and which use license-included models. Avoid putting every application onto dedicated hosts if only a few components carry special requirements.

A common partitioning layout:

```text
Cloud account / project
|
+-- Shared compute pool
|   +-- Web/APIs without host license constraints
|   +-- Workers and dev environments suited to shared tenancy
|
+-- Licensed dedicated pool
|   +-- Host A: workloads licensed per host/core
|   +-- Host B: standby host or workloads in same license scope
|
+-- Bare-metal pool (if needed)
    +-- Workloads needing custom hardware or hypervisor control
```

This is a logical organization. Exact resource names and enforcement mechanisms depend on the cloud service. Enforce boundaries through access controls, placement policies, and release workflows.

### 6.2. Map Licenses and Hardware Inventory

Every licensed software product needs a record linking contract entitlements to cloud resources. Capture at minimum:

- Product name, version, edition, vendor, and internal contract/entitlement ID.
- Licensing metric: user, device, VM, vCPU, physical core, socket, host, cluster, or other unit.
- Purchased licenses, allocated licenses, and remaining balance.
- Host ID, machine type, CPU model, socket count, physical core count, and deployment region where relevant.
- VM ID, vCPU, memory, installed software, create/delete timestamps, and host placement.
- Mobility, failover, DR, test rights, and other contractual constraints.
- Source evidence: contracts, vendor confirmations, cloud inventory reports, and change logs.

Inventory needs timestamps and change history. A point-in-time snapshot today cannot prove which host ran a VM last month during a periodic audit.

### 6.3. Manage Host and VM Lifecycles

Provisioning workflows should include pre-deployment license checks before creating VMs or installing software. When scaling out, pipelines or approval gates must verify target hosts and available license entitlements. When deleting VMs, update inventory and reclaim licenses strictly per contract terms.

For dedicated hosts, track states: provisioned, available, in-use, maintenance, failed, replaced, and decommissioned. If the provider replaces a host, record old/new host IDs, timestamps, hardware specs, and how licensing applies. Do not assume a physical host swap is invisible to host-licensed software.

For VM templates, images, and snapshots, check pre-installed software and how clones or launches affect licensing. An inactive template may be treated differently from a running instance, depending on exact contract terms.

### 6.4. Security and Access Control

Dedicated hardware shrinks physical sharing surface, yet does not replace security controls. Continue enforcing:

- Least-privilege IAM; only authorized teams can create, modify, or delete hosts and VMs.
- Separation of duties across cloud admin, OS admin, and licensed software admin accounts.
- Encryption in transit and at rest; key management via dedicated KMS services.
- Secure boot, firmware/BIOS baselines, and timely patching per service capabilities.
- Network segmentation, ingress/egress controls, and restricted management access paths.
- Audit logging for host creation, host replacement, migration, software install/uninstall, and permission changes.
- Inventorying images, software, and libraries to prevent out-of-scope installations.

When compliance mandates isolation proof, retain service documentation and provider attestations. Do not treat a "dedicated" console badge as sole legal or audit evidence.

## 7. Availability, Scaling, and Recovery

### 7.1. Host Redundancy and Availability Zones

A single dedicated host is a physical single point of failure. If workloads need high availability, you need a second host or recovery mechanisms on another host/zone. However, standby hosts can incur charges even while idle and may require failover licensing.

HA design must address both hardware and software:

- Spread VMs across separate hosts using anti-affinity where appropriate.
- Spread across multiple availability zones if services, data, and license terms permit.
- Identify authorized standby hosts and license quantities needed during failover.
- Verify new host provisioning speed against targets; quotas and host stock can affect RTO.
- Test workload failover, data recovery, and failback to restored hosts.

Do not place two replica VMs on the same host and treat it as HA. Nor should you fail over VMs onto unlicensed hosts just to recover quickly if contracts forbid it.

### 7.2. Capacity Scaling

In shared tenancy, adding instances is usually quick while quota remains. With dedicated hosts, scaling may require provisioning extra hosts, checking compatible machine families, configuring network/storage, and allocating licenses. Host provisioning can take longer than scaling VMs on existing hosts.

During capacity planning, calculate:

- VMs, vCPUs, memory, and I/O needed at average and peak load.
- Remaining host capacity after reserving HA and maintenance headroom.
- CPU allocation rules, NUMA, and memory limits for large workloads.
- Host count required to satisfy anti-affinity and availability zone policies.
- Additional licenses needed when adding hosts, increasing vCPUs, or growing user counts.
- Quotas, host provisioning lead times, and hardware availability.

Autoscaling on dedicated pools needs strict bounds. If a scheduler spins up VMs on arbitrary hosts, it can trigger unexpected license liabilities or breach approved host boundaries. Bind autoscaling policies to licensed node pools/host groups and cap max limits based on both physical capacity and license entitlements.

### 7.3. Disaster Recovery and License Rights

DR design must answer: is software allowed to run in the DR region; can licenses transfer to that host or region; what is the cooldown before reassignment; can standby servers stay passive or must they be fully licensed; and what rules apply during DR drills?

Map licenses for both production and DR environments. If special failover rights apply, archive the contract language, scope, and proof that usage stays strictly within permitted conditions. Schedule drills to test both technical failover and inventory update workflows.

## 8. Calculating Total Cost of Ownership

Dedicated hosts generally cost more per resource unit than shared tenancy if utilization is low. However, for software licensed per physical core or per host, dedicated hardware can help organizations bound licensing scope and avoid licensing an oversized cluster. Compare total cost rather than instance price alone.

Cost components to include:

1. **Compute:** host fees, bare-metal server fees, VMs, host retention duration, reservations, or committed use discounts.
2. **Licensing:** new licenses, subscriptions, maintenance, support, mobility rights, standby host licenses, and DR licenses.
3. **Auxiliary resources:** storage, snapshots, backups, image registries, load balancers, and network appliances.
4. **Networking:** cross-zone/region data transfer, egress, private links, and network security costs.
5. **Operations:** host management, patching, monitoring, auditing, contract management, and incident response.
6. **Idle capacity:** unused CPU/memory on hosts, HA reserve capacity, and pre-provisioned scaling headroom.

A general comparison formula:

```text
Period TCO =
    compute and host costs
  + license, subscription, and support costs
  + storage, backup, and network costs
  + operational and audit costs
  + spare/idle capacity costs
```

Build at least three scenarios: normal load, peak load, and host/zone failure. Compare shared tenancy, dedicated hosts, and bare metal using a consistent unit of work, such as cost per successful transaction or per data-processing hour.

### Qualitative Comparison Example

An organization runs database software licensed per physical core. Shared tenancy may be cheaper on compute, yet if it cannot identify hosts and core scopes as required by contract, it may not qualify for BYOL. Dedicated hosts carry higher compute fees but expose clear host IDs and core counts, simplifying license planning. Bare metal may fit if the workload needs deep hypervisor or I/O control, though it raises operational overhead.

Meanwhile, stateless APIs, workers without host licensing constraints, and dev environments can stay on shared tenancy. Separating workloads with special licensing requirements generally avoids paying dedicated hardware premiums across the entire estate.

## 9. Selection and Implementation Process

### Step 1: Gather Licensing Terms

Collect contracts, product use rights, license guides, cloud addenda, BYOL confirmations, and documentation for exact versions/editions in use. Identify metrics, quantities, host/VM scopes, mobility, failover, DR, and test environment rights. If contract wording is ambiguous, obtain written clarification from the software vendor or legal/procurement teams.

### Step 2: Profile Workloads and Hardware Requirements

Document CPU, memory, networking, storage, performance, availability, data residency, isolation requirements, and deployment methods. Determine whether a workload requires bare metal, dedicated hosts, or merely dedicated instances. Separate mandatory requirements from operational preferences.

### Step 3: Map License Metrics to Cloud Metadata

Check whether the cloud provider exposes enough data for license calculations: host ID, sockets, cores, CPU model, vCPUs, placement history, and host replacement events. If mandatory data is missing, choose a different service or secure formal agreement on calculation methods.

### Step 4: Design Host Groups and Placement Policies

Create host groups dedicated to licensed workloads. Configure affinity, anti-affinity, IAM, and deployment policies. Define standby hosts, DR regions, and migration rules. Ensure CI/CD pipelines cannot deploy workloads into unlicensed pools.

### Step 5: Build Inventory and Change Workflows

Link license entitlements to hosts, VMs, software, and owners. Automate inventory collection from cloud APIs or asset management tools. Every VM creation/deletion, vCPU resize, migration, or host swap should update historical records.

### Step 6: Test Performance, HA, and Auditability

Benchmark CPU, memory, NUMA, network, and storage under representative load. Test host failures, maintenance, migration, scale-out, and DR. Verify logs and inventory can prove where a workload ran at any past point in time.

### Step 7: Calculate TCO and Approve Architecture

Compare compute, licensing, redundancy, and operational costs. Document assumptions, risks, confirmed contract terms, and review triggers. Once approved, codify licensing constraints into IaC, policies, and release workflows for long-term governance.

## 10. Applied Examples

### Example 1: Enterprise Database Licensed per Physical Core

An organization operates a large database under a BYOL agreement metered per physical core. The team needs to know exact hosts running the database and restrict workload movement.

**Evaluated option:** dedicated hosts or sole-tenant nodes providing clear host IDs, core counts, and placement metadata. Create a dedicated host group for the database and set affinity so VMs run only on licensed hosts. Reserve a second host for HA and confirm failover licensing rights. Unconstrained APIs and workers remain on shared pools.

**Points to verify:** whether the contract counts all host cores or allocated cores; how SMT is treated; mobility rights; host replacements; failover; and whether standby nodes require full licenses.

### Example 2: Commercial Application Licensed per VM

A commercial application is licensed per VM where the software is installed, subject to contractual vCPU caps and minimums. The app does not need dedicated hosts and the vendor permits deployment on approved cloud virtualization platforms.

**Evaluated option:** shared tenancy can fit if security and cloud terms are satisfied. Track VM counts, vCPU sizes, templates, and autoscaling to avoid exceeding license counts. Pipelines should verify entitlements before increasing instance counts.

**Points to verify:** whether stopped VMs count; whether clones or snapshots count as separate instances; minimum vCPUs; multi-region deployment rights; and DR licensing rules.

### Example 3: Analytics Platform Needing Consistent Performance and I/O

An analytics workload processes large datasets and is sensitive to memory bandwidth, NUMA, and I/O. Engineering wants OS or hypervisor control and reduced performance variance.

**Evaluated option:** benchmark dedicated hosts and bare metal on representative data. Compare CPU models, core counts, NUMA topology, network speeds, storage types, and scaling. If a custom hypervisor or specialized device access is required, bare metal fits well. If host isolation plus cloud VM management suffices, dedicated hosts may be simpler.

**Points to verify:** actual performance, provisioning times, firmware patching workflows, host replacement, HA, analytics software licensing, and idle capacity cost.

## 11. Common Mistakes

- **Assuming dedicated instances equal dedicated hosts:** host visibility and placement control can differ. Verify exact service commitments.
- **Assuming dedicated hardware automatically qualifies for BYOL:** software contract terms govern usage rights. Cloud service names do not override contracts.
- **Equating vCPUs with physical cores:** virtual CPU mapping varies by platform and contract. Using the wrong unit leads to under- or over-licensing.
- **Licensing only running VMs:** standby VMs, failover clusters, DR sites, templates, or stopped VMs may have separate contractual rules.
- **Overlooking migrations and host replacements:** workloads can shift onto unlicensed hosts or alter audit boundaries.
- **Putting all workloads on dedicated hosts:** idle resources and license costs can balloon. Dedicate hardware only where truly required.
- **Failing to keep placement history:** current inventory alone cannot prove historical software locations.
- **Treating hardware isolation as complete security:** IAM, network policies, patching, encryption, logging, and OS management remain essential.
- **Forgetting HA/DR licenses:** standby hosts can trigger licensing obligations even when used only during outages.
- **Leaving autoscaling unchecked:** schedulers can place workloads on other hosts or spin up more VMs than current entitlements cover.

## 12. Checklist Before Moving Workloads onto Dedicated Hardware

- [ ] Confirmed whether workloads require physical isolation, performance, or specific licensing terms.
- [ ] Distinguished dedicated instances, dedicated hosts, sole-tenant nodes, and bare metal per provider specs.
- [ ] Read license terms for the exact product, version, and edition.
- [ ] Identified the metric: user, device, VM, vCPU, physical core, socket, host, cluster, or other unit.
- [ ] Verified BYOL, license mobility, failover, DR, test rights, and reassignment cooldowns.
- [ ] Confirmed how vCPUs map to hardware and which host metadata must be retained.
- [ ] Designed host groups, affinity, anti-affinity, and placement boundaries.
- [ ] Defined standby hosts, deployment regions, and handling for provider host replacements.
- [ ] Built inventory linking entitlements to hosts, VMs, software, and change history.
- [ ] Enforced IAM, networking, encryption, patching, and audit logging.
- [ ] Tested performance, scaling, host failure, and DR.
- [ ] Calculated TCO covering compute, licenses, networking, storage, operations, and idle capacity.
- [ ] Archived written confirmations from software/cloud vendors for any ambiguous terms.

## 13. Conclusion

Dedicated instances, dedicated hosts, sole-tenant nodes, and bare metal provide different levels of hardware isolation and control. Dedicated instances generally focus on instance-level isolation; dedicated hosts or sole-tenant nodes allow managing workloads on reserved servers/nodes; bare metal offers deeper control over physical servers and may allow customer-managed hypervisors.

Choosing properly depends on workload requirements and software licensing terms. Know whether licenses count users, devices, VMs, vCPUs, physical cores, sockets, hosts, or clusters, alongside BYOL, mobility, failover, and DR rights. Once a model is chosen, enforce constraints through placement policies, IAM, inventory, and change workflows. Finally, evaluate lifecycle TCO—including licenses, standby hosts, and idle capacity—so the architecture meets technical goals while remaining audit-ready.
