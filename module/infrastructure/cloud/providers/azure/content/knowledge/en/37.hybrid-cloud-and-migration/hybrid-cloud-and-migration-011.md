# Azure Resource Mover and Cross-Region Resource Migration Planning

A system running stably in one Azure region may need to move to another region due to data residency rules, user latency, infrastructure consolidation, architectural shifts, or plans to retire a deployment location. However, **moving across regions is not like moving across resource groups**: compute, networking, IP addresses, disks, data, and dependent services may need to be newly provisioned, synchronized, reconfigured, and cut over within a controlled outage window.

In the **Hybrid Cloud and Migration to Azure** chapter of the **CLOUD_PROVIDERS_AZURE** track, this lesson explains the role of **Azure Resource Mover**, how to assess support and dependencies, design targets, sequence migration stages, test, cut over, roll back, and clean up source resources. It connects concepts across Azure subscriptions, resource groups, Microsoft Entra ID, Virtual Networks, VMs, storage, databases, monitoring, security, reliability, and cost control.

**Core principle:** tooling can automate parts of infrastructure movement, yet **an application is only considered successfully migrated once data, connectivity, business functions, and operational criteria are verified**.

> **Scope note:** Azure Resource Mover capabilities depend on resource type, source/target regions, subscriptions, service status, and current limits at execution time. Resources, actions, timings, and costs in this lesson are illustrative examples. Before executing on live systems, verify supported features and prerequisites in your exact target tenant and subscription. This lesson does not require moving production resources.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **cross-region resource move**, **resource group/subscription move**, **replication**, **failover**, and **disaster recovery**.
2. Explain the roles of Azure Resource Mover, move collections, dependency validation, prepare, initiate move, commit, and cleanup.
3. Inventory compute, disks, networking, identity, data, backups, DNS, applications, and resources not directly supported by the tool.
4. Choose among **Resource Mover**, Infrastructure-as-Code redeployment, or service-native migration/failover mechanisms.
5. Design source/target regions, resource groups, network topology, quotas, RBAC, naming, monitoring, and data policies.
6. Plan data sync, migration waves, cutover runbooks, and safe rollback strategies.
7. Estimate bandwidth, copy duration, spare capacity, and parallel dual-region operating costs.
8. Design validation tests and **go/no-go** criteria before running the system in the new region.

## 2. Precisely Understanding “Cross-Region Resource Move”

An Azure region is a geographic area hosting infrastructure for Azure services. Not every service or SKU is available in every region, and not every resource supports changing its **location** property in-place after creation.

| Operation | Goal | What Never to Assume |
| --- | --- | --- |
| **Resource group move** | Change resource management grouping within supported scope | Does not move resources to a different region |
| **Subscription move** | Change management/billing boundary for supported resources | Does not alter location or automatically resolve all dependencies |
| **Cross-region move** | Move workloads/resources to a target region, typically creating target equivalents | Not an in-place metadata label change |
| **Replication** | Sync data or state between two locations | Does not automatically switch DNS/traffic or write ownership |
| **Failover / DR** | Restore service after an outage per designed RTO/RPO | Not automatically a permanent region-relocation plan |
| **Rebuild / redeploy** | Provision new infrastructure via IaC and load data | Does not automatically preserve state, identities, IPs, or data |

**Azure Resource Mover** focuses on planning, validating dependencies, and orchestrating select **cross-region Azure resource moves**. It cannot move every Azure service, nor does it replace backups, disaster recovery services, or multi-region architecture designs.

### 2.1. “Region Move” Differs from “High Availability”

A system can move cleanly to a new region yet still run on a single VM and single database—meaning it **still has single points of failure**. Fault tolerance requires Availability Zones, redundancy, backups, replication, and operations suited to the target service.

Conversely, an app using multi-region data services can **fail over** during an outage without calling Resource Mover to relocate VMs individually. Pick tools by objective; never mistake a tool feature for an architecture.

## 3. When Should You Consider Azure Resource Mover?

A typical scenario: a team operates several Azure VMs and dependent network resources and wants to move the workload from region A to an approved region B with less manual toil and step-by-step tracking.

**Consider Resource Mover when:**

- Workloads already live in Azure using resource types supported for cross-region moves.
- Source/target regions and subscriptions meet tool prerequisites.
- Dependent resources can be discovered, added, or handled via complementary methods.
- You have a cutover plan and control over when traffic switches.
- App owners accept preparation time, replication overhead, and planned downtime if needed.

**Do not default to Resource Mover for:**

- All data inside every PaaS service such as managed databases, Cosmos DB, or Storage Accounts.
- Workloads needing major architectural rewrites or OS/runtime transitions.
- Systems needing continuous automated failover with committed RTO/RPO.
- Moving resource groups without changing regions.
- Unsupported resource configurations or immovable dependencies.

In those cases, evaluate target services and dedicated mechanisms such as **redeploying with Bicep/Terraform**, native database replication/backup-restore, **Azure Site Recovery** where appropriate for DR/migration strategies, or specialized data transfer tools. Each mechanism has distinct scope and rules—never treat them as interchangeable.

## 4. Core Concepts of Resource Mover

| Concept | Meaning | Role in Plan |
| --- | --- | --- |
| **Source region** | Region currently hosting live resources | Defines source data, config, and traffic |
| **Target region** | Region planned to run workloads post-move | Check SKUs, quotas, security, networking, capacity |
| **Move collection** | Group of move metadata/resources managed in Resource Mover | Tracks scope, dependencies, and progress |
| **Move resource** | Representation of a resource added to the move plan | Tracks per-component operation state |
| **Dependency validation** | Checks related resources required by the move plan | Surfaces missing items, conflicts, or unmet prerequisites |
| **Target settings** | Target-region settings per resource type | Controls target naming, networking, or configuration |
| **Prepare** | Prepares target or data/replication where required by resource type | Sets prerequisites ahead of cutover |
| **Initiate move** | Executes moving eligible resources per resource mechanism | One of the key steps of region relocation |
| **Commit move** | Finalizes/confirms the move per supported workflow | Separates finalization from discard/rollback while still reversible |
| **Cleanup** | Disposes source resources, replicas, and temporary artifacts post-approval | Ends dual-run spend and removes orphan resources |

Displayed action/status names vary by resource type and UI version. **Not every resource shares the exact same Prepare → Initiate move → Commit sequence or state machine.** Follow live state and per-resource guidance rather than forcing one generic sequence onto every item.

### 4.1. Resource Mover Does Not “Delete Source Immediately”

Moving may create target resources or replicas while source resources remain intact. **Committing** and **deleting/cleaning up source resources** must be treated as distinct responsibilities per resource type and phase.

Key operational consequences:

- Both regions may generate **concurrent dual-run charges** temporarily.
- Unattached disks, NICs, IPs, backups, or temporary artifacts may linger.
- Deleting source too early destroys rollback paths or violates retention policies.
- Leaving source active unchecked risks **two systems accepting writes**, causing data conflicts.

Therefore, **never delete source resources solely because the Portal shows move succeeded**. Require application testing, formal sign-off, and a dedicated cleanup plan.

## 5. Surveying Resources Before Moving

The most critical input is a **workload-centric inventory**, not merely a raw resource-group list.

| Category | What to Record | Pre-Move Questions |
| --- | --- | --- |
| **Subscription / Resource group** | IDs, names, RBAC, tags, policies, locks | Are target permissions and governance ready? |
| **Compute** | VM names, sizes, OS/images, zones/availability, extensions, boot diagnostics | Are sizes, images, and add-ons available in target region? |
| **Disks** | OS/data disks, sizes/tiers, encryption, snapshots, backups, throughput | Are performance, quotas, and data protection sufficient? |
| **Networking** | VNets, subnets, NSGs, route tables, NICs, load balancers, public IPs, gateways | Will CIDRs/DNS/routing collide or change? |
| **Identity** | Managed identities, service principals, RBAC, AD/Entra dependencies | Must principal IDs or role assignments be recreated? |
| **Secrets / Keys** | Key Vault, certificates, CMKs, secret references | Can workloads in the new region reach required keys? |
| **Data** | Databases, file shares, object storage, backups, logs | Which tool moves each data tier? |
| **Application** | URLs, webhooks, client allowlists, cron jobs, integration endpoints | Do clients and partners know the new endpoints? |
| **Observability** | Alerts, diagnostic settings, dashboards, logs, SLOs | Will issues surface immediately post-cutover? |
| **Business** | Owners, peak hours, downtime window, RTO/RPO, critical transactions | When can it move and what proves acceptance? |

### 5.1. Sample Inventory

~~~csv
workload,resource,source_region,type,owner,move_path,dependency_status
orders,orders-vm01,region-a,VirtualMachine,orders-team,resource-mover,candidate
orders,orders-vnet,region-a,VirtualNetwork,platform-team,resource-mover,review
orders,orders-osdisk,region-a,ManagedDisk,orders-team,resource-mover,review
orders,orders-db,region-a,ManagedDatabase,dba-team,service-native,pending
orders,orders-keyvault,region-a,KeyVault,security-team,separate-design,pending
orders,orders-dns,global-or-external,DNS,network-team,traffic-cutover,pending
~~~

This is an **illustrative planning catalog**, not a verified Resource Mover support list. The **move_path** column is an initial hypothesis to validate per resource type and source/target pair.

### 5.2. Gathering Info with Read-Only Commands

Azure CLI examples to confirm subscription context and fetch an initial inventory:

~~~bash
az account show \
  --query "{subscription:id,tenant:tenantId,name:name}" \
  -o json

az resource list \
  --resource-group rg-orders-source \
  --query "[].{name:name,type:type,location:location,id:id}" \
  -o table

az vm list \
  --resource-group rg-orders-source \
  --query "[].{name:name,size:hardwareProfile.vmSize,location:location}" \
  -o table
~~~

These commands assume you are signed in with read permissions and **rg-orders-source** exists. They **do not move resources** and do not capture full dependency graphs. Use exact approved resource group names and avoid mixing subscriptions across tenants.

Never record access keys, passwords, connection strings, or private keys in inventory files. Store reference identifiers and owners for verification via secure channels.

## 6. Checking Supportability and Prerequisites

Before building a move plan, compile a **compatibility matrix**. Check not just “can the VM move?” but **every configuration detail and dependency**.

### 6.1. Conditions to Verify

1. **Resource types:** are resource types, SKUs, sub-features, extensions, and states supported by Resource Mover?
2. **Source/target regions:** is the region pair supported, and does the target support chosen models, sizes, availability options, and features?
3. **Subscription:** required Resource Providers registered, subscription healthy, and operations within boundaries.
4. **RBAC:** does the executing identity hold least-privilege roles on source resources, move collection, resource groups, and target resources?
5. **Quotas / capacity:** vCPU quotas by VM family, disks, IPs, NICs, subnet IP space, and service-specific quotas.
6. **Policies / locks:** does Azure Policy block types/tiers/regions, or do delete/read-only locks block operations?
7. **Networking:** CIDRs, subnets, NSGs, UDRs, DNS, private endpoints, public IPs, firewalls/allowlists, and outbound paths.
8. **Data / security:** disk encryption, customer-managed keys, backups, replication, resource identities, and data residency rules at target.
9. **Operations:** readiness of monitoring, logging, data protection, patching, and post-move incident response.
10. **Rollback:** workload-specific recovery/cutback path, including handling new writes on target.

Never “fix” missing permissions by granting **subscription-wide Owner** when only a single permission is missing. Assign least-privilege roles under organizational approval workflows.

### 6.2. Checking Regions and Quotas

Suppose a source VM uses **Standard_D8s_v5** (illustrative size only). Before choosing the target, verify that VM size is available and has **live capacity** in the target region/zones. Pricing can also differ between regions.

**Quota differs from capacity availability:** holding a 32-vCPU quota does not guarantee Azure can allocate four VMs of that exact size at cutover time. Check early and prepare equivalent fallback SKUs where workload-compatible.

### 6.3. Data Residency and Compliance Policies

Moving workloads across regions can alter where data is processed or stored, including:

- Disks and temporary replicas during transit.
- Backups, snapshots, logs, diagnostic data, and key storage locations.
- Traffic paths to supporting services or secondary DR regions.
- How managed services process data internally.

**Never assume two regions in the same country or geography are automatically legally equivalent.** Base decisions on organizational policy, data classification, and target service documentation.

## 7. Dependency Graph: What Is Most Often Missed

A VM typically depends on NICs, subnets, VNets, NSGs, routes, disks, identities, and services outside its resource group. Selecting only the VM triggers validation errors for missing infra items, yet **never assume the tool detects all application-level dependencies**.

~~~mermaid
flowchart LR
    U["Users"] --> DNS["DNS / Front Door / Gateway"]
    DNS --> LB["Load balancer"]
    LB --> VM["Application VM"]
    VM --> DISK["OS + data disks"]
    VM --> NIC["NIC"]
    NIC --> SUB["Subnet / VNet"]
    SUB --> NSG["NSG / routing / firewall"]
    VM --> DB["PaaS Database"]
    VM --> KV["Key Vault / managed identity"]
    VM --> EXT["Partner API / IP allowlist"]
    VM --> MON["Monitoring / backup"]
~~~

### 7.1. Three Dependency Categories to Separate

| Category | Examples | How to Handle |
| --- | --- | --- |
| **Infrastructure dependencies** | VM → NIC → subnet/VNet; VM → disk | Confirm inclusion in move plan and target settings |
| **Service dependencies** | VM → Azure SQL, Storage, Key Vault, Service Bus | Define dedicated sync, networking, and RBAC plan |
| **Business / external dependencies** | VM → payment provider, DNS, identity, mail relay | Document runbook and coordinate with owners/partners |

### 7.2. Sample Dependency Matrix

| Source → Dependent Target | Critical? | Target-Region Plan | Verification |
| --- | --- | --- | --- |
| Orders VM → NIC/VNet | Yes | New or matching VNet/subnet | Routes, NSGs, DHCP/DNS, IPs |
| Orders VM → data disk | Yes | Target disk via supported method | Data integrity, performance, encryption |
| Orders API → database | Yes | Separate PaaS replica/migration | Transactions, consistency, failover |
| Orders API → Key Vault | Yes | Dedicated vault/secret/identity plan | RBAC, key access, private endpoints |
| Orders API → payment partner | Yes | Outbound HTTPS from new region | IP allowlist, certificates, idempotency |
| Users → API endpoint | Yes | DNS/gateway cutover | TTLs, DNS caching, TLS, health probes |
| VM → backup/monitoring | Yes | New or adjusted backups/alerts | Restore test, alerts, log routing |

If database and API execute many sequential queries, leaving the database in the source region after moving VMs can spike latency sharply. **Measure round-trip counts and real RTT** before splitting them across waves.

## 8. Designing the Target Architecture Before Taking Action

Do not create a move collection first and decide IP addressing, permissions, or data storage afterward. Start with an approved **target architecture**.

~~~mermaid
flowchart TB
    subgraph SRC["Source region"]
      S_APP["Orders VM + NIC + disks"]
      S_VNET["VNet, subnet, NSG"]
      S_DB["Source database and data"]
      S_APP --> S_VNET
      S_APP --> S_DB
    end
    subgraph DST["Target region"]
      T_APP["Target VM/compute"]
      T_VNET["VNet, subnet, NSG, firewall"]
      T_DB["Target database per separate plan"]
      T_MON["Monitor, backup, identity, Key Vault"]
      T_APP --> T_VNET
      T_APP --> T_DB
      T_APP --> T_MON
    end
    RM["Azure Resource Mover / move collection"] -. "Orchestrates eligible resources" .-> T_APP
    RM -. "Dependencies/target settings" .-> T_VNET
    S_APP -. "Move/replication per resource" .-> RM
    S_DB -. "DB native migration/replication" .-> T_DB
    IN["DNS / ingress / client routing"] -. "Approved cutover" .-> T_APP
~~~

### 8.1. Network Design

In the target region, define:

- VNet/subnet address spaces; avoid CIDR overlap with the source network if peering, VPN, or ExpressRoute will connect them.
- NSGs/UDRs/firewalls and public/private subnet separation.
- Private endpoints and private DNS zones; **never assume source-region private endpoints work unchanged at target**.
- Public ingress, WAF/gateways, health probes, certificates, and DNS.
- NAT/outbound IPs; check partner allowlists and egress limits.
- Temporary hybrid or cross-region connectivity during dual-run.

**Expect IP or endpoint changes.** Design cutover around DNS, routing, or load balancing rather than hardcoded source IPs. Never assume public IPs, private IPs, Resource IDs, or names survive a move unchanged; check exact behavior per resource type and target settings.

### 8.2. Identity and Secrets

Do not copy a VM and assume permissions carry over unchanged. When resources are recreated, **system-assigned managed identities**, principals, or RBAC bindings may need re-provisioning. User-assigned identities, role assignments, service principals, certificates, Key Vault references, and private network rules must be verified per resource support rules.

Minimum checks:

1. How does the workload authenticate, and are any secrets hardcoded?
2. Are Storage/database/Key Vault permissions scoped accurately at target?
3. Are keys/certificates still valid and reachable from the target network?
4. Do logs and audit trails reflect new identities as required?
5. Are temporary migration roles scheduled for revocation post-cutover?

Never export passwords or private keys into logs, portal screenshots, or inventory sheets.

## 9. Phased Resource Mover Workflow

A controlled process follows **discovery → add resources → validate dependencies → prepare → move → commit/cleanup**, though exact steps vary by resource type.

~~~mermaid
flowchart TD
    A["Inventory and verify support"] --> B["Pick source/target, create move collection"]
    B --> C["Add resources and validate dependencies"]
    C --> D{"Dependencies & target settings valid?"}
    D -->|"No"| E["Add missing resources / adjust config / choose alternate path"]
    E --> C
    D -->|"Yes"| F["Prepare where required by resource"]
    F --> G["Initiate move per resource state"]
    G --> H["Test target and cut over application"]
    H --> I{"Business & technical checks pass?"}
    I -->|"No"| J["Fix / roll back or roll forward per runbook"]
    I -->|"Yes"| K["Commit per supported workflow"]
    K --> L["Confirm stability, clean up source & artifacts"]
~~~

### 9.1. Step 1 — Set Up the Move Collection

In Azure Portal, locate **Azure Resource Mover** or the **Move → Move to another region** experience where available. Choose source, target, and subscription/resource group within supported scope, then create or select a move collection per UI guidance.

**Prerequisites before starting:** approved change ticket, validated resource list, owners, execution window, permissions, budget, and on-call staff. If the Portal blocks selecting a target or flags a resource as unsupported, treat that as a critical assessment finding—**never try to bypass checks with poorly understood workarounds**.

### 9.2. Step 2 — Add Resources and Validate Dependencies

Select workload resources and run **validate dependencies** to surface missing components detected by the tool. When a VM needs a VNet or supporting resource, add/map it per guidance and review target settings.

At this stage, record:

- Name/ID of every source resource.
- Resource type and support status.
- Target settings to be applied.
- Dependencies managed inside the tool.
- Dependencies **outside the tool's scope** with their corresponding runbooks.

**Passing dependency check does not mean application dependencies pass.** Independently test database calls, identity, external APIs, and infrequent batches.

### 9.3. Step 3 — Prepare

For resource types requiring it, **Prepare** establishes prerequisites for moving—which may involve provisioning target infrastructure, state checks, or replication setup. Other resource types may use different prep steps or skip this phase.

Before advancing:

- Inspect per-resource state and dependency errors.
- Confirm target region VM/disk/network capacity.
- Verify data synchronization under the chosen method.
- Record initial sync/backlog/replication health where applicable.
- Reconcile temporary dual-region/replica spend.

Never assume **Prepare succeeded = workload ready for users**. Apps, databases, DNS, and identities may not yet be cut over.

### 9.4. Step 4 — Initiate Move

**Initiate move** executes transitioning eligible resources per tool state. For stateful workloads, this step may require coordinated cutover or downtime depending on resource type and migration mechanics.

Operators must:

1. Confirm go/no-go before disruptive actions.
2. Confirm dependencies and data transfer paths are ready.
3. Execute steps in the exact order required by the tool/resource type.
4. Watch move status, Azure Activity Logs, and observability dashboards.
5. Never allow two systems to write concurrently to the same dataset without a valid dual-write design.

**Moving infrastructure does not automatically complete DNS or application cutover.** Steps outside Resource Mover are usually needed to switch live traffic.

### 9.5. Step 5 — Commit and Finalize

Once the target is verified, **Commit** confirms the move per supported workflow. Carefully read the exact effects and **Discard/rollback** options for each resource's state before clicking.

**Never treat Commit as an automatic guarantee of instant rollback to the old state.** Post-commit, returning to the source region may require a reverse migration or rebuild/restore—especially once the target accepts new writes.

### 9.6. Step 6 — Cleanup

After hypercare and application owner sign-off, clean up:

- Unused compute, disks, NICs, public IPs, and VNet resources at source.
- Snapshots, recovery artifacts, staging storage, and temporary links.
- Obsolete backups/monitoring rules, alerts, and endpoints—preserving required audit trails.
- Temporary migration role assignments, permissions, and identities.
- Move collections and temporary metadata per tool lifecycle guidance.

**Never delete by guessing from names.** Verify exact Resource IDs, dependencies, and ownership. Keep source intact long enough for backup, retention, and rollback policies, then reclaim it to stop duplicate charges.

## 10. Distinguishing Tool-Moved Resources from Separate Migration Paths

Assessments must happen at the **resource type + configuration** level. The table below is a planning guide, not a fixed Azure Resource Mover support matrix:

| Component | Migration Path to Evaluate | Notes |
| --- | --- | --- |
| **Azure VMs and core infra dependencies** | Resource Mover if type/config/region are supported | Sizing, disks, NICs, VNets, availability, encryption |
| **VNet/subnets and network resources** | Resource Mover for eligible types or IaC redeployment | CIDRs, NSGs, UDRs, peering, private DNS, IPs |
| **Azure SQL Database / Managed Instance** | Service-native replication, failover, migration, or backup-restore | Compatibility, data, logins, downtime, failover |
| **Azure Storage** | Suitable copy, object replication, backup, or data migration tools | Namespace, consistency, ACLs, tiers, throughput, delta churn |
| **Azure Cosmos DB** | Native multi-region replication and migration per account/data model | Consistency, write regions, RU/s, failover strategy |
| **App Service / Functions** | Redeploy infra/apps with matching backup/migration workflows | Settings, secrets, custom domains, slots, plans, state |
| **AKS / Container Apps** | Provision new environment/cluster via IaC, deploy workloads, migrate data | Container registries, secrets, networking, ingress, PVs |
| **Key Vault / managed identities** | Dedicated target design and key/secret/RBAC migration plan | Private keys, principals, and roles do not auto-copy by default |
| **DNS / Front Door / APIM / third-party** | Controlled traffic/endpoint cutover and config deployment | TTLs, certs, custom domains, routing, IP allowlists |

Some capabilities evolve or vary across service tiers. Always verify current supportability before locking in an implementation path.

### 10.1. Why Not Dump an Entire PaaS Architecture into One Move Collection?

Databases mutate continuously, Storage carries specific consistency semantics, and identity/certificate services enforce strict access controls. These layers often need **service-tier replication**, integration testing, and cutover outside Resource Mover. A VM move can report success while APIs fail because connection strings still point to the old database.

Maintain two parallel lists:

1. **Resource Mover-managed items:** verified supported and tracked inside the move collection.
2. **Externally managed items:** databases, secrets, DNS, app deployments, network policies, and anything needing separate runbooks.

## 11. Data and Downtime Design

### 11.1. Moving the VM Does Not Mean the Database Moved

For stateful applications:

- Snapshot OS/data disks per policy.
- Separate data living on VM disks from data inside PaaS databases/storage.
- Measure initial sync time and ongoing data churn rate.
- Design **final sync / write quiesce** at cutover.
- Validate consistency with row counts, checksums, transaction IDs, and business invariants.
- Plan handling of in-flight requests, cron jobs, queue consumers, and background workers.

When using replication, monitor **actual replication lag and checkpoints**—never mistake a green “Healthy” badge for RPO = 0. If allowed downtime is only minutes, complete initial copy beforehand and rehearse cutover thoroughly.

### 11.2. RTO, RPO, and Cutover Downtime

| Metric | Meaning | Example Target |
| --- | --- | --- |
| **RTO** | Service recovery time after an outage | 2 hours |
| **RPO** | Acceptable data loss window during an outage | 15 minutes |
| **Planned downtime** | Permitted outage window during scheduled transition | 30 minutes |
| **Cutover execution time** | Actual duration to switch traffic/data and verify | Must be measured in rehearsal |
| **Hypercare** | Intensive post-cutover observation period | e.g., 48 hours depending on criticality |

DR RTO/RPO is not identical to planned migration downtime. A workload with a 2-hour DR RTO may still allow at most 10 minutes of planned downtime during business hours.

### 11.3. Single Writer and Post-Cutover Data

When switching databases or writable stores, specify explicitly **which side holds write authority at every moment**. If the new region records live transactions without syncing back to the old region, pointing DNS back to the old source **will not recover those transactions**.

If data rollback is needed after target accepts writes, you must have a tested **reverse replication, transaction replay, reconciliation, or roll-forward plan**. Where no safe reverse path exists, explicitly mark the **point of no simple rollback** prior to approving cutover.

## 12. Estimating Copy Time and Cross-Region Connectivity

Transfers can be bottlenecked by networking, source read / target write speeds, small-file counts, service throttling, encryption, and ongoing data churn.

Approximate formula:

\[
T_{\text{copy}} \approx
\frac{\text{Data to transfer (bits)}}{\text{Effective throughput (bits/second)}}
\]

### 12.1. Example: 2 TiB Over a 250 Mbit/s Link

Suppose **2 TiB** must be copied with **250 Mbit/s** nominal throughput allocated to copying:

\[
2\ \mathrm{TiB} = 2\times2^{40}\ \text{bytes}
\]

\[
T_{\text{ideal}} =
\frac{2\times2^{40}\times8}{250\times10^6}
\approx70{,}369\ \text{seconds}
\approx19.55\ \text{hours}
\]

If effective efficiency is **60%**:

\[
250\times60\%=150\ \text{Mbit/s}
\]

\[
T_{\text{estimated}}\approx19.55/0.6\approx32.58\ \text{hours}
\]

This is an **educational estimate**, not a timing guarantee from Resource Mover or Azure Site Recovery. Real transfers vary with replication engines, churn, read/write IOPS, bottlenecks, and concurrent workloads.

### 12.2. Data Churn During Replication

If the source writes **15 MiB/s** continuously during sync, an initial copy pass can leave a hefty delta backlog. Measure:

- Hourly and peak data churn rates.
- Effective replication throughput and source/target resource limits.
- Backlog/lag at planned cutover time.
- Final sync duration once writes freeze.
- Write consistency behavior across databases or filesystems.

Sizing downtime solely from disk capacity while ignoring write rate regularly produces unachievable cutover windows.

## 13. Quotas, Capacity, and Constraints Invisible on Diagrams

Every region has distinct capacity and limits. Verify:

- **vCPU quotas** per VM family and region, plus live VM size/zone availability.
- **Disk SKUs, performance tiers**, required IOPS/throughput, and per-VM limits.
- **IP address space** sufficient for concurrent NICs/VMs/Pods during overlap.
- **Network topology** routable over peering/hybrid without CIDR overlap.
- **Azure Policy** permissions for target resource types, SKUs, and regions.
- **Subscription limits** for public IPs, load balancers, and related resources.
- **Resource naming** for globally unique names or provider-specific rules.
- **Failover/scaling capacity**, not merely steady-state normal load.
- **Service concurrency/throttling limits** during bulk copying.

### 13.1. Sizing Example

Source runs **3 VMs × 8 vCPUs**. Target needs three equivalent VMs running concurrently—at least **24 vCPUs in the matching family**, before adding test infra, HA, and scaling headroom. With one 8-vCPU spare VM, budget **32 vCPUs** and check exact zone availability.

**vCPU math is necessary but insufficient.** Disk throughput, memory, database tiers, IPs, physical capacity, and SLOs can all bottleneck performance. If changing target SKUs, benchmark rather than assuming linear throughput scaling with vCPU count.

## 14. Estimating Migration and Dual-Run Costs

Project cost extends far beyond target VM pricing. Budget categories:

| Category | Potential Cost Drivers | How to Control |
| --- | --- | --- |
| **Dual-run compute** | VMs/apps running simultaneously in source and target | Bound overlap window, schedule cleanup |
| **Disks and snapshots** | Replica disks, snapshots, staging storage | Inventory, retention, and cleanup |
| **Replication / transfer** | Cross-region data movement, bandwidth, replication services | Verify exact service meters and rates |
| **Networking** | Cross-region traffic, gateways, NAT, public IPs, load balancers | Optimize topology and measure data flows |
| **Observability** | Dual-region log ingestion, duplicate streams, alerts | Tune sampling and retention |
| **Database dual-run** | Two active databases/replicas billed together | Time sync/scaling tightly and finalize cutover |
| **Backup / DR** | Vaults, backup storage, recovery points | Maintain safety without redundant copies |
| **Labor / risk** | Engineering hours, after-hours support, testing, downtime | TCO modeling and risk buffer |

Never assume a Resource Mover operation has “zero total cost.” Even when orchestration fees vary under current pricing, **source/target resources, replication, data transfer, and supporting services** still bill on actual meters.

### 14.1. Hypothetical Budget Model

Suppose source and target overlap for **7 days** with these hypothetical figures:

| Illustrative Line Item | Hypothetical Amount |
| --- | ---: |
| Source compute for 7 days | 420 USD |
| Target compute for 7 days | 455 USD |
| Extra disks/replicas/snapshots | 95 USD |
| Cross-region network/replication | 70 USD |
| Additional monitoring | 20 USD |
| **Subtotal** | **1,060 USD** |
| 20% contingency buffer | 212 USD |
| **Illustrative Budget** | **1,272 USD** |

These numbers are **not Azure quotes**—only a budgeting structure example. Substitute Azure Pricing Calculator estimates, contract rates, Cost Management actuals, and measured telemetry. Avoid double-counting meters already covered elsewhere.

### 14.2. Cost Is Not the Sole Criterion

An option saving a few hundred dollars while raising transaction-loss risk or stretching downtime is unacceptable for critical apps. Balance **cost, RTO/RPO, security, workload performance, and operational readiness**.

## 15. Migration Waves and Sequencing

Never move all VMs, networks, and databases at once without testing. Structure waves by **dependencies** and business criticality:

| Wave | Contents | Entry Criteria | Exit Criteria |
| --- | --- | --- | --- |
| **0 – Foundation** | Target subscription/RG, networking, identity, policies, quotas, backups, monitoring | Architecture approved | Connectivity, RBAC, alerts, restore test pass |
| **1 – Pilot** | Non-critical workload | Clear inventory/rollback | Moved and verified cleanly |
| **2 – Infrastructure dependencies** | Eligible supporting infra required at target | Validation and target settings pass | Target infra and dependencies ready |
| **3 – Application / data** | VMs/apps, separate DB migration, jobs | Data sync and cutover rehearsal pass | Functional/integration/data tests pass |
| **4 – Traffic cutover** | DNS/gateways, external allowlists, single writer | Go/no-go approved | SLOs and business flows pass |
| **5 – Stabilization & cleanup** | Hypercare, optimization, source teardown | Business sign-off and retention check | Zero source dependencies; dual-run spend ended |

**Infrastructure order can differ from business wave order.** A target VNet must exist before target VMs provision; databases must sync before APIs switch writes; DNS shifts only after services verify healthy. Resource Mover guides resource-level dependencies, while the **migration lead** owns end-to-end application dependencies.

### 15.1. Picking a Good Pilot

A strong pilot has a clear owner, synthetic or low-sensitivity data, tolerable recovery time, simple dependencies, and clean rollback. It must exercise **real mechanics**—resource move, target settings, DNS, monitoring, and cleanup—not just booting an empty VM.

## 16. Preparing Cutover: An Accountable Runbook Template

### 16.1. Pre-Cutover Checklist Table

| Milestone | Tasks | Evidence | Owner |
| --- | --- | --- | --- |
| **T−14 days** | Lock scope, target settings, compatibility, licensing | Assessment and owner sign-off | Migration lead |
| **T−7 days** | Finish landing zone, quotas, identity/network | Network, RBAC, and restore tests | Platform/Security |
| **T−3 days** | Baseline sync/Prepare for applicable resource types | Move state, replication lag, checks | Infra/DBA |
| **T−1 day** | Rehearsal test, backup and rollback verification | Measured downtime, data checks | App/DBA/SRE |
| **T−30 min** | Go/no-go, freeze changes, notify users | Approvals + contact roster | Business/Operations |
| **T0** | Quiesce/block writes, final sync per plan | Checkpoints, queue status, transaction state | App/DBA |
| **T+** | Initiate move/cutover per state and plan | Resource op status, functional smoke tests | Platform/App |
| **T+** | Switch DNS/gateways/traffic, observe | Endpoint health, TLS, API, auth | Network/SRE |
| **T+** | Verify data, batches, SLOs, external integrations | Reconciliation, dashboards, error rates | App/QA/Business |
| **Post-hypercare** | Commit/cleanup per support and policy | Sign-off, backups, inventory cleanup | Migration lead |

These timings are a **planning template**, not SLAs guaranteed by Azure Resource Mover. For resource types with specialized sequencing, follow tool documentation and UI state rather than forcing a rigid template.

### 16.2. Go / No-Go

**Go** when:

- Source/target regions, SKUs, quotas, networking, and security are verified.
- Move collection has zero unresolved dependency blockers.
- Separate database/data migration meets checkpoint and lag targets.
- Backups and restores are tested.
- SLOs, cutover duration, and rollback/roll-forward are rehearsed.
- App owner, DBA, Network, Security, and Operations confirm ownership.

**No-go** if:

- Any resource type/target is unsupported without an approved alternative.
- Unresolved VNet/DNS/IP errors or conflicts remain.
- Replication lag exceeds data-loss or downtime thresholds.
- No restorable backup exists or critical data remains unverified.
- Payment/webhook/AD/certificate dependencies are unproven.
- No plan exists to handle new data if forced back to source post-cutover.

## 17. Testing After Resources Appear in the New Region

An infrastructure move succeeding is not application acceptance. Testing requires metrics and owners:

| Test Type | Example Checks | Criterion |
| --- | --- | --- |
| **Infrastructure** | VM health, attached disks, NIC/VNet, DNS, availability | Target config accurate, resources healthy |
| **Network / security** | TLS, NSGs/firewalls, private endpoints, RBAC, managed identity | Exact paths work; zero overly broad permissions |
| **Functional** | Login, order creation, file read/write, background jobs | Critical flows pass |
| **Data integrity** | Row counts/checksums/transactional invariants | Zero lost or duplicated confirmed data |
| **Performance** | Peak RPS, p95/p99 latency, CPU, DB throughput | Meets agreed SLOs |
| **Operations** | Logs, alerts, backup jobs, restore rehearsal | SRE team can operate and respond |
| **Resilience** | Replica/zone loss, recovery, retries, failover | Meets HA/DR targets |
| **Business** | Payment sandbox, email/webhooks, report reconciliation | Owner confirms |
| **Cost** | Dual-run spend, orphan resources, egress | Within budget, cleanup scheduled |

### 17.1. Sample Acceptance Matrix

Suppose Orders API pre-move handles **120 RPS peak**, **350 ms** p95, zero data loss, and planned downtime at or under **30 minutes**.

| Metric | Target | Hypothetical Test Result | Status |
| --- | ---: | ---: | --- |
| Peak throughput | ≥120 RPS | 132 RPS | Pass |
| API p95 | ≤400 ms | 365 ms | Pass |
| Critical functional flows | 100% required flows | 100% | Pass |
| Lost confirmed transactions | 0 | 0 after reconciliation | Pass |
| Cutover downtime | ≤30 min | 24 min | Pass |
| Backup restore test | Mandatory | Incomplete | **Not accepted** |
| Partner outbound allowlist | Mandatory | Unconfirmed | **No-go** |

These numbers are examples. **Never declare success** while restore tests or critical integrations lack evidence, even if VMs and main APIs appear healthy.

## 18. Rollback, Discard, and Roll Forward

### 18.1. Three Distinct Actions

| Action | Purpose | Must Verify |
| --- | --- | --- |
| **Discard move** | Cancel an incomplete move where resource/state supports it | Is discard still possible? How are replicas/metadata cleaned up? |
| **Application rollback / cutback** | Route traffic or functionality back to source | Is source intact, and how is newly written data handled? |
| **Roll forward** | Remediate on target or execute next fix step so target operates | Are data integrity and blast radius protected? |

**Resource Mover's Discard is not a business-transaction undo button.** After Commit or once target accepts new writes, reverting to the source region may require a reverse migration or data recovery project—never assume an instant rollback button exists.

### 18.2. Phase-Dependent Recovery Options

1. **Before target accepts writes:** keeping source primary is usually simpler; still check how far infra commits or state changes progressed.
2. **During traffic switch:** pause mutating jobs, drain/account for in-flight requests, and ensure only one side is primary writer.
3. **After target accepts writes:** handle new transactions via reverse sync/replay or choose roll forward.
4. **After source deletion:** source-based cutback is gone; rely on backups/restores or a fresh migration.

If confirmed transactions cannot be preserved on rollback, **never label that plan a safe rollback**. Pre-approve the no-go cutoff or roll-forward decision criteria.

## 19. Monitoring During and After Cross-Region Move

### 19.1. Three Observation Layers

**Resource Mover layer:** move collection/resource states, dependency validation, operation errors, and execution durations. Use the tool UI, Azure Activity Log, and supported service diagnostics.

**Infrastructure layer:** VM availability, CPU, memory, disk latency/IOPS, VNet connectivity, network latency, load balancer probes, backups, and target resource health.

**Application / business layer:** request success rates, p95/p99 latency, payment callbacks, queue age, database replication lag, confirmed transaction counts, and data invariants.

Never substitute **Azure Resource Mover move status** for application SLOs. The tool can finish moving while HTTPS endpoints or databases remain broken.

### 19.2. Pre-Cutover Comparison Dashboard

| Metric | Source | Target | Threshold / Meaning |
| --- | --- | --- | --- |
| Request latency p95 | Baseline | Test/cutover | Must not exceed acceptance limit |
| Business success rate | Baseline | Live | Must not drop below threshold |
| Database replication lag | Per data engine | Per data engine | Must meet limit before final sync |
| Network RTT | Measured | Measured | Spot cross-region chatty calls |
| Disk latency | Peak baseline | Target measured | Validate SKU/IOPS |
| Errors / timeouts | Source history | Target live | Trigger rollback/no-go per policy |
| Backup / restore status | Source | Target | Evidence mandatory |
| Cost by region | Source cost | Target cost | Track dual-run and cleanup |

Use Azure Monitor/Application Insights/OpenTelemetry where possible, tagging version/region/instance for clean comparison. Never emit secrets, tokens, or sensitive transaction payloads into telemetry.

## 20. Synthesis Scenario: Moving Orders from Region A to Region B

### 20.1. Current State

An ordering system comprises:

- **2 Azure VMs** serving APIs, with NICs/data disks and a dedicated VNet.
- **Load balancer and public endpoint** receiving requests.
- **Managed PaaS database** storing transactions.
- **Key Vault** storing secrets; APIs use managed identities.
- **Log Analytics / Application Insights** for operational monitoring.
- A payment partner allowing traffic only from registered outbound IPs.

Goal: move the app to region B for data governance and lower latency to new users. Tolerated planned downtime is **at most 30 minutes**, zero lost confirmed transactions, sustaining **120 RPS** with p95 under **400 ms**.

### 20.2. Per-Component Strategy

| Component | Proposed Strategy | Pre-Deployment Conditions |
| --- | --- | --- |
| Eligible VMs, disks, and networking | Evaluate and use Resource Mover | Resource/region support, dependencies, target settings |
| Database | Supported native migration/replication path | Consistency, schema, write freeze, failover, data checks |
| Key Vault, identities, secrets | Dedicated target design/config per supported model | Permissions, key access, private networking |
| Public endpoint | Controlled DNS/gateway/traffic cutover | Certificates, health probes, rollback strategy |
| Partner IP allowlist | Coordinate change with partner | Target egress IPs approved |
| Monitoring / backups | Deploy/configure appropriately at target | Alerts, logging, restore test |

### 20.3. Migration Waves

**Wave 0 — Foundation:** build VNet/subnets, routing, and security; verify quotas and target access; prepare monitoring/backups. Use IaC for resources unsuitable for Resource Mover, while avoiding creating duplicate resources that the tool expects to provision.

**Wave 1 — Pilot:** move a non-critical VM sharing similar connectivity patterns. Log exact operations, state transition times, and errors encountered.

**Wave 2 — Sync:** finalize move collection/validation and prep infra, alongside separate database replication. Measure replication lag, bandwidth, disk I/O, and verify secrets.

**Wave 3 — Cutover:** quiesce writes, run final sync and checks; transition VMs/apps and traffic per runbook; verify TLS, DNS, payments, data, and SLOs.

**Wave 4 — Hypercare & cleanup:** retain source for the approved window if needed while watching dual-run costs; after business sign-off, commit/clean up per tool state and data policy.

### 20.4. Blockers That Must Be Resolved

- Target VM SKUs and live quota/capacity not yet confirmed.
- Target database sync/failover not yet rehearsed.
- Target identities lack verified access to Key Vault or database.
- Target VNet/subnet CIDRs conflict with hybrid links.
- Payment partner has not yet approved new outbound IPs.
- Missing restore test and post-cutover transaction recovery plan.
- No explicit “single writer” gate during data sync.

If any data-integrity blocker remains unresolved, **do not approve production go-live**, even if the Resource Mover UI lets you click Initiate move.

## 21. Auditable Migration Plan Template

~~~yaml
planId: orders-cross-region-illustration
source:
  region: region-a
  resourceGroup: rg-orders-source
target:
  region: region-b
  resourceGroup: rg-orders-target
workloadOwner: commerce-team
migrationLead: platform-team
moveMethod:
  infrastructure: resource-mover-for-verified-supported-items
  database: separately-validated-service-native-migration
  dnsAndTraffic: controlled-cutover
goals:
  maxPlannedDowntimeMinutes: 30
  maxLostConfirmedTransactions: 0
  peakRpsAtLeast: 120
  latencyP95MsAtMost: 400
dependencies:
  - target-network
  - keyvault-and-identity
  - managed-database
  - payment-egress-allowlist
  - monitoring-and-backup
requiredEvidence:
  - dependency-validation
  - backup-restore-test
  - database-reconciliation
  - performance-rehearsal
  - business-approval
  - rollback-or-rollforward-plan
cleanup:
  sourceDeletionRequiresBusinessSignoff: true
  trackTemporaryResources: true
~~~

This is an **illustrative planning manifest** defined by this lesson—not JSON/YAML accepted directly by the Azure Resource Mover API. Populate real names/IDs, approvers, deadlines, runbooks, and verified support details in an actual project.

### 21.1. Sample Risk Register

| ID | Risk | Impact | Mitigation and Evidence | Owner |
| --- | --- | --- | --- | --- |
| RM-01 | Insufficient target VM SKU capacity | Delays or fails VM creation | Verify region/SKU/zone/quota; PoC | Platform |
| RM-02 | Missing VNet/NSG dependency | Move blocked or API loses network | Validate dependencies + routing tests | Network |
| RM-03 | Replication lags behind data churn | Downtime exceeds 30 minutes | Measure lag and final sync rehearsal | DBA |
| RM-04 | Managed identity/RBAC changes | App gets access denied | Test identities at target | Security/App |
| RM-05 | New DNS/IP untrusted by partner | Payments fail | Pre-register endpoints/IPs, integration test | Integration |
| RM-06 | Source deleted prematurely | Loss of rollback path, data loss | Business sign-off and cleanup gate | Migration lead |
| RM-07 | Both regions accept writes | Duplicates/conflicts | Single-writer protocol and reconciliation | DBA/App |
| RM-08 | Dual-run lasts longer than planned | Cost overrun | Budget, deadlines, cleanup owner | FinOps |

## 22. Common Troubleshooting

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Cannot pick target region | Unsupported region pair or resource type | Check compatibility and pick alternate path |
| Validation flags missing dependencies | Linked NIC, VNet, disk, or resource omitted | Add/resolve per guidance; never ignore |
| Target VM size fails to provision | Quota, SKU, or zone/capacity constraint | Check quotas, target SKU/zone, and live capacity |
| Prepare fails | Permissions, resource state, replication, policy/locks | Inspect per-item errors, RBAC, and source/target states |
| Initiate move errors | Resource in wrong state or unready dependencies | Inspect move status; avoid blind repeated destructive retries |
| Target VM boots yet app has no network | DNS, routes, NSGs, UDRs, firewalls, private endpoints | Trace hop-by-hop and outbound paths |
| App runs but database is slow | Cross-region latency and chatty round-trips | Measure RTT and query fan-out; move DB in same wave |
| 403 reading Storage/Key Vault | Wrong identity, role assignment, or private network | Check principal, scope, secret references, networking |
| Partner payment returns timeout/403 | Changed IP allowlist/certificate/endpoint | Coordinate with partner, verify egress IP |
| Resource move succeeds yet DNS unchanged | Traffic cutover is a separate step | Execute DNS/gateway runbook with health checks |
| Rollback loses transactions | Target accepted writes without reverse sync | Freeze changes, reconcile, execute data recovery plan |
| Source resources keep billing | Uncleaned disks, IPs, VMs, backups, artifacts | Inventory post-sign-off and delete cleanly |
| Cost spikes on move day | Dual-run, snapshots, data transfer, duplicate logging | Reconcile Cost Management across both regions |
| Monitoring misses target errors | Diagnostic settings/agents/alerts unconfigured | Test telemetry end-to-end before go-live |

**Never resolve errors by granting subscription-wide Owner or disabling Azure Policy, NSGs, or diagnostic logging.** If temporary exceptions are unavoidable, tightly scope and time-box them with formal approval.

## 23. Practice Exercise: Building a Safe Resource Mover Plan

Practice on a **hypothetical workload** of 2 VMs, VNet, NICs, disks, and a separate PaaS database. No destructive actions or live resource moves are required.

### Exercise A — Inventory and Classification

1. Build the resource table as in Section 5.
2. Flag which resources **need Resource Mover support verification**, which require service-native migration, and which need traffic cutover only.
3. Record owners, sensitive data, RBAC, VM sizes, disk capacities, networking, and endpoints.
4. Map the dependency graph from users through VMs, database, Key Vault, and payment provider.

**Passing criterion:** never assume every resource in a resource group is automatically supported by Resource Mover.

### Exercise B — Target Evaluation

1. Select organization-approved source and target regions.
2. Check SKU/availability, vCPU quotas, disk performance, policies, and network CIDRs.
3. Design target VNets/subnets/NSGs/routes, DNS, TLS, and outbound allowlists.
4. Propose Key Vault/managed identity and monitoring configurations.

**Passing criterion:** produce a compatibility matrix with **verified, pending, and unsupported** columns without hiding blockers.

### Exercise C — State-Driven Runbook

1. Separate Resource Mover-managed items from externally runbook-managed items.
2. Describe move collection, dependency validation, target settings, and Prepare/Initiate move/Commit **according to each resource type's behavior**.
3. Distinguish service-mutating steps from read-only/prep steps.
4. Mark write-quiesce and DNS/gateway cutover points.
5. State exact conditions permitting source cleanup.

**Passing criterion:** never equate “Move completed” with “Application accepted” or “Source safe to delete.”

### Exercise D — Time and Capacity Math

Assume 2 TiB to copy over 250 Mbit/s at 60% effective efficiency. Calculate ideal transfer time, efficiency-adjusted time, and list at least four factors that can skew reality.

**Reference results:** **19.55 hours** ideal and **32.58 hours** at 60% efficiency. Factor in IOPS, replication lag, ongoing writes, and service limits.

### Exercise E — Rehearsing Against Reckless Rollback

Suppose 15 minutes post-cutover, the target has recorded **500 confirmed orders** with no reverse sync to source, and target 5xx errors spike.

1. Why would flipping DNS straight back to source hide those 500 orders?
2. What evidence must be gathered before freezing writes or choosing roll forward?
3. What reverse sync/replay options exist, and what prerequisites must be tested beforehand?
4. Who holds authority to call no-go or execute recovery per runbook?

**Passing criterion:** solution neither drops nor duplicates confirmed transactions and separates infrastructure rollback from data-state rollback.

### Exercise F — Go / No-Go Report

Tabulate criteria across:

- Target region/SKU/quotas.
- Dependency validation and target settings.
- Database consistency and replication lag.
- Identity, DNS, payment allowlist, security.
- Functional, performance, backup restore, and cost budget.
- Rollback/roll-forward readiness and approvers.

Flag every item **lacking evidence**. “Go” is permitted only when all hard gates pass under organizational governance.

## 24. Self-Check Questions

**Question 1.** Can Azure Resource Mover change the location of every Azure service with a single click?  
**Answer:** No. Check resource type, regions, and dependencies; many services require separate migration or redeployment.

**Question 2.** Does moving a resource group mean moving across regions?  
**Answer:** No. That changes organizational/management grouping; cross-region relocation is a distinct operation.

**Question 3.** What does a move collection do?  
**Answer:** Organizes eligible resources, dependency checks, and operational state across a move workflow.

**Question 4.** Does passing dependency validation guarantee the API can call the payment provider?  
**Answer:** No. Tool checks do not validate every business dependency; verify DNS, certificates, outbound IPs, networking, and API behavior.

**Question 5.** Why shouldn't you delete the source immediately upon seeing Move completed?  
**Answer:** Applications, data, backups, and integrations still require acceptance, source may still anchor rollback, and cleanup requires retention/owner approval.

**Question 6.** Must a PaaS database travel inside the same Resource Mover collection as VMs?  
**Answer:** No. Use the database service's supported migration/replication mechanism and test consistency/cutover separately.

**Question 7.** Why can provisioning a target VM still fail even with sufficient vCPU quota?  
**Answer:** Quota does not guarantee live SKU/zone capacity or policy/service-limit compliance.

**Question 8.** Why track planned downtime target and replication lag threshold separately?  
**Answer:** Downtime measures user outage; lag measures unsynced data. Both differ yet jointly govern safe cutover timing.

**Question 9.** Is reverting DNS after the target accepted writes a safe rollback?  
**Answer:** No, if the source lacks the new data. You need a verified reverse-data strategy or roll-forward plan.

**Question 10.** Does Commit automatically delete all source resources and guarantee recovery of every business transaction?  
**Answer:** No. Inspect resource/state semantics; source cleanup and business data consistency remain separate responsibilities.

**Question 11.** Roughly how long does 2 TiB take over 250 Mbit/s under ideal conditions?  
**Answer:** About 19.55 hours, excluding overhead and ongoing data churn.

**Question 12.** Why budget for dual-run?  
**Answer:** Source and target coexisting generate compute, disk, replication, network, and logging fees; delayed cleanup prolongs spend.

**Question 13.** What should you do if Azure Resource Mover does not support a resource?  
**Answer:** Log a blocker and evaluate service-native migration, redeployment, replication, or architectural changes rather than trying to bypass support constraints.

**Question 14.** Target VMs pass health checks, yet target backup restore hasn't been tested. Is the migration accepted?  
**Answer:** No, if restore testing is mandatory for that workload; infrastructure status and operational readiness are two different bars.

## 25. Pre-Region-Move Production Checklist

- [ ] Region-move objective, owner, RTO/RPO, downtime window, and SLOs are approved.
- [ ] Resource types, source/target regions, and Azure Resource Mover support are verified.
- [ ] Inventory covers VMs, disks, NICs, VNets, NSGs, routes, IPs, databases, secrets, identities, DNS, monitoring, and backups.
- [ ] Dependency graph is owner-confirmed with non-Resource-Mover items listed separately.
- [ ] Target architecture covers naming, subnets/CIDRs, DNS, routing, firewalls, and private connectivity.
- [ ] Quotas, SKUs, live capacity, zone availability, Azure Policies, and permissions are verified.
- [ ] Data, backups/logs/keys, and target region align with data classification/compliance.
- [ ] Stateful databases/data have supported service-native migration/replication plans.
- [ ] Move collection, dependency validation, and target settings are verified.
- [ ] Prepare/Initiate move/Commit steps match each resource type's exact state model.
- [ ] Rehearsal, replication lag tracking, single-writer rules, and final sync checkpoint are ready.
- [ ] Runbook covers DNS/gateways/partner allowlists, identity/RBAC, health probes, and TLS.
- [ ] Restorable backups and data-preserving rollback/roll-forward plans are verified.
- [ ] Functional, integration, performance, security, business, and DR checks pass.
- [ ] Azure Monitor/Application Insights dashboards and on-call staffing are ready.
- [ ] Dual-run budget, replication/egress controls, and cleanup schedule exist.
- [ ] Commit and source deletion happen only when tool state, acceptance, and retention allow.
- [ ] Business sign-off, change ticket, monitoring evidence, and post-migration report are archived.

**Conclusion:** Azure Resource Mover helps organize and orchestrate moving **eligible Azure resources** across regions, but it never replaces dependency discovery, data transfer engineering, traffic cutover, or transaction protection. A successful plan combines **compatibility assessment, target architecture, dependency validation, migration waves, testing, rollback, and approved cleanup**. Treating Resource Mover as one component inside an overarching hybrid/migration architecture lets operations relocate regions safely while protecting availability, data, security, and cost.
