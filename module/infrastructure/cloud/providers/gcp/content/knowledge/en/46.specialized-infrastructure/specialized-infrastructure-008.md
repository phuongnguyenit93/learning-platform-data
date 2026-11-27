# Google Cloud VMware Engine and Its Operational Model

An enterprise with hundreds of VMware virtual machines may want to exit its private datacenter without immediately refactoring every application into containers or cloud-native services. **Google Cloud VMware Engine** addresses part of that need by delivering a VMware environment on dedicated hardware in Google Cloud while keeping familiar vSphere, vCenter, vSAN, and NSX concepts. However, moving VMs to Google Cloud **does not mean Google automatically operates your guest operating systems, databases, and applications**.

This lesson belongs to the **Specialized Infrastructure** chapter in the **CLOUD_PROVIDERS_GCP** module. The module introduces Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases; through deployment scenarios, learners choose services, secure resources, automate releases, and track reliability and costs. For VMware Engine, the focus is on **picking the right responsibility model**, designing connectivity, and operating a stable VMware private cloud within the Google Cloud ecosystem.

After this lesson, you will be able to:

- Distinguish Google Cloud-managed VMware Engine from VMware solution on Google Cloud under the Bring Your Own License (BYOL) model.
- Describe ESXi, vCenter, vSAN, NSX, HCX, nodes, clusters, private clouds, and VMware Engine networks.
- Choose among standard, single-node, or stretched private clouds based on HA, lab, and cost goals.
- Design networking across on-premises, VPCs, and VMware Engine without CIDR overlaps, DNS breaks, or routing issues.
- Plan VM migrations using VMware HCX or alternatives, structured into migration waves and rollbacks.
- Separate permissions across Google Cloud IAM, VMware vCenter RBAC, NSX policies, and guest OS access.
- Operate Day 0/Day 1/Day 2: provisioning, capacity, autoscaling, lifecycle updates, backup/DR, monitoring, and FinOps.
- Know when to keep VMs on VMware Engine and when to modernize onto Compute Engine, GKE, or Cloud Run.

**Technical scope:** this content describes current public models and capabilities; VMware versions, node types, locations, pricing, quota limits, and licensing terms may change. Confirm availability in the Google Cloud Console and official documentation for your chosen location, contract, and deployment model.

## 1. What VMware Engine Is—and Is Not

VMware Engine runs VMware workloads on **dedicated bare-metal nodes** at Google Cloud locations. Enterprises continue managing many VM operations via vCenter and VMware tools while Google Cloud supplies the underlying physical infrastructure.

~~~mermaid
flowchart TD
    USER["VMware Administrator"]
    GC["Google Cloud console / VMware Engine API"]
    VC["vCenter Server"]
    NSX["NSX Manager"]
    CLUSTER["vSphere Cluster"]
    VM["Application VMs and data"]

    USER --> GC
    USER --> VC
    USER --> NSX
    GC --> CLUSTER
    VC --> CLUSTER
    NSX --> CLUSTER
    CLUSTER --> VM
~~~

Think of it in two layers:

- **Infrastructure/resource layer:** private clouds, nodes, clusters, VMware Engine networks, Google VPC connectivity, and hardware operations.
- **Workload layer:** VMs, guest OSes, applications, databases, user access, backups, antivirus, performance, and business data.

VMware Engine **is not**:

- Standard Compute Engine VMs: you do not create an equivalent Compute Engine instance and manage it via vCenter.
- A Kubernetes cluster: GKE fits containers, whereas VMware Engine preserves VMware virtualization infrastructure.
- An automatic zero-downtime lift-and-shift magic wand: migrations still require networking, data replication, software compatibility, and testing.
- A managed database service: PostgreSQL or SQL Server running inside a guest VM remains the workload team's responsibility.
- Automatic default backup for every VM: you must design data protection and test restores yourself.

### When Does It Deliver Value?

VMware Engine fits well when:

1. You have many VMware VMs and must exit a datacenter under tight deadlines.
2. Workloads are tied to VMs, drivers, OSes, or vendor products that cannot be refactored quickly.
3. You want to retain VMware operational tooling, VM policies, and existing vSphere team skills.
4. You need to burst or build a DR environment without purchasing physical servers.
5. You plan phased modernization, running legacy workloads in a private cloud while new workloads use native services.

## 2. Two VMware Operating Models on Google Cloud

Current Google Cloud documentation outlines **two options with distinct responsibility models**. Do not equate them merely because both run VMware on Google Cloud.

| Criterion | Google Cloud-managed VMware Engine | VMware solution on Google Cloud |
|---|---|---|
| Goal | Consume a Google-managed VMware private cloud | Self-manage VMware Cloud Foundation on Google bare metal |
| VMware licensing | Included in the service under the applicable model | Bring Your Own License (BYOL) VCF |
| VMware stack provisioning | Google deploys/configures the managed stack | Customer deploys and configures VCF |
| Patching VMware ESXi/vCenter/NSX | Google manages lifecycle per managed service | Customer schedules, tests, and executes |
| Hardware / datacenter | Google Cloud | Google Cloud |
| Primary management tools | Google Cloud console/API and vCenter/NSX | VMware SDDC Manager and vCenter alongside Google Cloud controls |
| VMware stack admin rights | Scoped with elevation mechanisms when needed | Customer manages broader privileges under BYOL |
| Guest VM/OS/database/app | Customer | Customer |
| Workload VM backups | Customer | Customer |
| Operations team complexity | Lower VMware stack operational burden | Requires dedicated VMware platform and license management team |

In the sections below discussing **managed private clouds**, "Google-managed" applies strictly to components within the published service boundary. Never infer that Google patches Windows/Linux guests, upgrades SQL Server, or restores in-VM data.

### 2.1. Which Model Should You Choose?

Choose Google Cloud-managed when:

- You prioritize rapid private cloud deployment and minimizing VMware lifecycle toil.
- You prefer an integrated service model including VMware licensing per contract terms.
- You have app/VM admins rather than a team wanting to operate a full VMware SDDC.

Consider VMware solution BYOL when:

- Your organization holds VCF licensing entitlements and a matching strategy.
- You need granular control over VMware stack versions, configs, and upgrade schedules.
- You have an SDDC team responsible for vSphere, NSX, vSAN, and lifecycle operations.

**No single model fits every enterprise.** Compare control, compatibility, licensing, total cost, responsibility splits, and migration goals.

## 3. Core VMware Components in a Managed Private Cloud

A VMware Engine private cloud comprises:

| Component | Role | What Workload Admins Must Understand |
|---|---|---|
| VMware ESXi | Hypervisor on dedicated bare-metal nodes | Hosts, VM placement, resource pools, guest compatibility |
| VMware vCenter Server | Manages VM inventory, clusters, permissions, and vSphere HA/DRS | VM creation, templates, resource pools, cluster monitoring |
| VMware vSAN | Software-defined storage using local cluster disks | Capacity, storage policies, fault tolerance, rebuilds |
| VMware NSX | Virtual networking, segments, gateways, firewall/security policies | VLANs/segments, routing, microsegmentation, NAT |
| VMware HCX | Supports migration, workload mobility, and network extension where supported | Migration methods, service mesh, network extension, cutovers |
| VMware Engine network | Network connecting private clouds to VPCs and external networks | Peering, route exchange, DNS |
| Google Cloud console/API | Manages private cloud resources, nodes, quotas, service operations | Provisioning, scaling, service-level changes, auditing |

~~~mermaid
flowchart TB
    subgraph PC["Managed VMware Engine private cloud"]
      VC["vCenter"]
      NSX["NSX Manager"]
      HCX["HCX Cloud Manager"]
      subgraph VSP["vSphere cluster: dedicated nodes"]
        E1["ESXi Node 1"]
        E2["ESXi Node 2"]
        E3["ESXi Node 3"]
      end
      SAN["vSAN datastore / policy"]
      SEG["NSX segments: application VMs"]
      VC --> VSP
      NSX --> SEG
      HCX --> VSP
      VSP --> SAN
      VSP --> SEG
    end
    SEG --> APP["Windows/Linux guest VM"]
~~~

### 3.1. Node, Cluster, Private Cloud

- **Node:** a dedicated bare-metal hardware unit providing CPU, RAM, and storage capacity per node type.
- **Cluster:** a group of ESXi hosts managed together via vCenter with shared compute and storage policies.
- **Private cloud:** an isolated VMware environment with a management domain that can contain multiple clusters.
- **Workload VM:** customer application virtual machine running on the cluster, not a Google-native Compute Engine instance.

Nodes within the same cluster must have compatible node types per service rules. Supporting mixed node families within one private cloud does not mean you can freely mix arbitrary node types inside a single cluster.

## 4. Standard, Single-Node, and Stretched Private Clouds

Choosing a private cloud type directly impacts availability, capacity, and cost.

| Type | Architecture | Best For | Caveats |
|---|---|---|---|
| Standard | VMware cluster running in one zone of a region | Production needing host-level HA, migrations, normal operations | May require separate DR for zone/region outages |
| Single-node | Dedicated single-node private cloud | Proof of concept, labs, restore or upgrade testing | No full vSphere HA/DRS, no vSAN multi-node redundancy, not covered by 3+ node production SLA |
| Stretched | Nodes split across two data zones plus a witness zone in one region | Workloads needing zone-failure tolerance at the VMware cluster layer | Minimum 3+3 data nodes, higher quota/cost, does not replace cross-region DR |

### 4.1. Standard Private Cloud

For standard clusters, documentation recommends **at least three nodes** for production workloads. vSphere HA restarts VMs when a host fails if the cluster has remaining headroom; vSAN protects data per storage policy. This provides cluster-scoped HA—**not a guarantee** of zero application interruption.

### 4.2. Single-Node Private Cloud

Single-node works well for PoCs, but never for critical workloads: vSAN policies may run at FTT=0, so losing one node can destroy unbacked-up data. Lifetimes, upgrades, SLAs, and expansion paths to multi-node clusters vary by program/product terms; verify current product guidance before scheduling labs.

Never treat single-node as a safe production cost-cutting shortcut just because VMs boot on it.

### 4.3. Stretched Private Cloud

A stretched cluster distributes data nodes across two zones with a dedicated witness zone in the **same region**. This architecture tolerates zonal failures, not multi-region disasters.

~~~mermaid
flowchart LR
    A["Zone A: 3 ESXi nodes"]
    W["Witness zone"]
    B["Zone B: 3 ESXi nodes"]
    A <-->|"vSAN stretched traffic"| B
    A --> W
    B --> W
~~~

- Illustrative minimum configuration: 3+3 data nodes.
- Must choose a region supporting stretched private clouds and the selected node type.
- Stretched clusters are designed to survive a single zone failure in supported topologies.
- Do not assume an existing standard private cloud can convert to stretched later; pick the right private cloud type upfront.
- Still requires backups and plans for whole-region outages, accidental deletion, or ransomware.

## 5. End-to-End Architecture from On-Premises to Google Cloud

~~~mermaid
flowchart LR
    ON["On-prem VMware vCenter + VMs"]
    VPN["Cloud VPN / Cloud Interconnect"]
    VPC["Google Cloud VPC"]
    VEN["Standard VMware Engine Network"]
    PC["VMware Engine private cloud"]
    NAT["Google-native services: Cloud SQL, Storage, Cloud Run"]
    ON <-->|"Hybrid connectivity"| VPN
    VPN <--> VPC
    VPC <-->|"VPC Network Peering"| VEN
    VEN --> PC
    VPC --> NAT
~~~

This environment spans **at least three administrative domains**:

1. On-premises: legacy ESXi/vCenter and unmigrated systems.
2. Google Cloud: VPCs, Cloud VPN/Interconnect, IAM, Cloud DNS, and native services.
3. VMware Engine private cloud: management network, NSX segments, vCenter, vSAN, and guest VMs.

Design **data paths** and **management paths** separately, and verify how DNS and routing serve both. Never expose management appliances publicly just for convenient vCenter access.

## 6. VMware Engine Networks: Standard vs. Legacy

**Standard VMware Engine Network** is the current networking model for new projects. It is a network resource linking one or more private clouds to Google Cloud VPCs or on-premises networks, using **VPC Network Peering** to connect with VPCs.

**Legacy VMware Engine Network** is a regional network model from older projects (prior to the 2023 architectural shift), using a private services access connection distinct from Standard. New deployments should never use Legacy unless maintaining an existing legacy environment.

| Aspect | Standard Network | Legacy Network |
|---|---|---|
| Scope | Global VMware Engine network | Regional VMware Engine network |
| VPC connection | VPC Network Peering | Private services access / private connection |
| Suitability | New environments | Existing legacy environments |
| Management | VMware Engine networks, peerings, DNS bindings | Legacy connections and corresponding DNS/routes |
| Traffic verification | Inspect peering routes and return paths | Inspect PSA/route import-export |

**Never mix commands or assumptions between Legacy and Standard**: a Legacy private connection is not equivalent to Standard VPC peering.

### 6.1. VPC Peering Is Not a Transit Router

VPC Network Peering does not automatically allow transitive routing across arbitrary chained peerings. When a VMware Engine network peers with a VPC, it will not automatically see every other VPC peered to that hub VPC.

To reach cloud services across multiple VPCs, Shared VPCs, private services access, or on-premises networks, explicitly design routing, peerings, custom route exchanges, and transit topologies per network documentation.

## 7. IP Planning, VLAN/NSX Segments, and DNS

### 7.1. Zero Overlapping CIDRs

Before creating a private cloud, map out an IP table:

| Scope | Illustrative CIDR | Purpose |
|---|---|---|
| On-prem workloads | 10.20.0.0/16 | Source guest VMs |
| GCP VPC | 10.40.0.0/16 | Cloud-native services |
| VMware management | 10.80.0.0/22 | vCenter, NSX, ESXi, vSAN management |
| VMware workload segment | 10.90.0.0/24 | Migrated VMs |
| HCX network if needed | Non-overlapping, per feature | Migration/interconnect services |

These CIDRs are **purely illustrative**. The management CIDR is carved into multiple subnets for vSphere/vSAN—it is not a general pool for application VMs. Managed private cloud docs require management prefixes between `/24` and `/20`; verify exact sizing rules and prohibited IP ranges.

Avoid any overlap with VPCs, on-premises ranges, services CIDRs, VM segments, private DNS/management ranges, or future connected networks.

### 7.2. Network Segments and NSX

NSX provides segments, firewalls, gateways, and network virtualization for VMs. For a three-tier app, separate segments cleanly:

- Web segment: accepts HTTPS solely from required proxies/load balancers.
- App segment: accepts traffic solely from web/worker tiers.
- DB segment: accepts PostgreSQL/SQL Server ports solely from the app tier.
- Management segment: restricted to admin networks, isolated from workloads.

Example policy:

| Source | Destination | Port | Action |
|---|---|---:|---|
| Controlled user/network ingress | Web | 443 | Allow |
| Web segment | App segment | 8080 | Allow |
| App segment | DB segment | 5432 | Allow |
| Any Internet | vCenter/NSX management | Any | Deny |
| DB segment | Any Internet | Any | Default Deny, open strictly as required |

Never drop all VMs into one flat L2 segment assuming the private cloud will enforce microsegmentation automatically.

### 7.3. DNS

Private clouds host a management DNS zone for vCenter, NSX, and HCX. Standard VMware Engine networks support DNS bindings with VPCs; on-premises DNS may require conditional forwarding to resolve management hostnames.

Verify:

1. vCenter FQDN resolution from admin workstations.
2. NSX Manager/HCX endpoints over the private network.
3. Guest VM hostname resolution to Google Cloud services.
4. Reverse DNS, domain controllers, NTP, and certificate hostnames.
5. DNS failover and cache TTLs during network changes.

Never test only by pinging IPs: if DNS breaks while TLS certificates bind to FQDNs, vCenter or HCX logins will fail.

## 8. Hybrid Connectivity via Cloud VPN or Cloud Interconnect

Migrating VMware VMs from on-premises to managed VMware Engine with HCX requires proper hybrid connectivity. Google Cloud guides recommend **Cloud VPN or Cloud Interconnect** as the hybrid connectivity layer.

Verify:

- Zero overlapping CIDRs across on-premises, VPCs, and VMware Engine.
- Accurate BGP route advertisements and return paths.
- Reachability to HCX, vCenter, vMotion, and management services across supported ports.
- DNS, NTP, MTU/MSS, bidirectional firewalls, and TLS/certificates.
- Link redundancy matching target RTO/RPO.
- Sufficient bandwidth for migration waves plus active VM delta churn during replication.

### 8.1. Bandwidth and Migration Duration

Suppose you need to transfer 4 TiB of data over a migration link achieving **500 Mbit/s effective throughput**, ignoring ongoing write churn during replication:

\[
4\ \text{TiB} = 4 \times 1024^4 \times 8\ \text{bits}
\]

\[
T_{\text{ideal}} \approx \frac{4 \times 1024^4 \times 8}{500,000,000}
\approx 70,369\ \text{seconds}
\]

Roughly 19.5 hours is an **idealized floor**. Real runs include delta changes, compression/protocol overhead, retransmissions, network contention, storage I/O, and final cutover pauses.

Never treat Interconnect's raw line rate as guaranteed replication speed. Run throughput tests and measure source data churn rates before committing to migration windows.

## 9. VMware HCX and VM Migration Methods

VMware HCX orchestrates migrations between source VMware environments and target private clouds. Managed private clouds include HCX Cloud Manager deployed alongside the VMware stack as part of the service.

Common options to weigh:

| Method | Characteristics | When to Use |
|---|---|---|
| HCX migration | Integrated VM orchestration and mobility | Migrating many VMs in waves over supported connectivity |
| HCX network extension | Preserves subnet/L2 during transition | Apps that cannot re-IP immediately |
| Backup/restore | Back up at source and restore into VMware Engine | Existing data protection tool supports the target |
| VMware PowerCLI | Automates vSphere/vCenter workflows | Custom tooling and runbook control |
| ISO/template import | Builds fresh VMs from templates or media | Rebuilding rather than migrating VMs in-place |
| NSX Layer 2 VPN | Extends L2 for migration in supported scenarios | Controlled network extension needs |

HCX offers multiple mobility modes, yet **no single mode fits every VM**. Choose based on guest OS, vSphere compatibility, storage, churn rate, bandwidth, and downtime tolerance.

### 9.1. Pre-HCX Assessment Checklist

- Full VM inventory, CPU/RAM/disk specs, and snapshot chains.
- vSphere/ESXi versions and the HCX compatibility matrix.
- VMware Tools, guest OSes, and virtual hardware versions.
- Network mappings, VLANs, DHCP/static IPs, DNS, and firewall rules.
- Database transaction rates, disk I/O, and delta change rates.
- Licenses bound to MAC addresses, hardware fingerprints, or IPs.
- Verified backups and restore points.
- VMs with USB/PCI passthrough, physical devices, or migration-restricted appliances.

If an app connects to an external database, moving only the app VM can raise database RTT. Trace the **entire application dependency graph**, not just whether the guest VM boots after migration.

## 10. Migration Waves and Cutover

Executing migrations in waves limits blast radius:

| Wave | Workload | Objective |
|---|---|---|
| 0 | Single test VM with no sensitive data | Validate HCX, DNS, networking, and monitoring |
| 1 | Non-critical internal VMs | Validate permissions, backup/restore, and rollback |
| 2 | Stateless or low-data web/app tiers | Assess performance and scaling |
| 3 | Database-backed apps with multiple integrations | Execute runbook cutover and data reconciliation |
| 4 | Business-critical / strictly governed workloads | Formal Go/No-Go and business sign-off |

### 10.1. Runbook for a Migration Wave

1. Lock inventory/owners, confirm RTO/RPO, and book the downtime window.
2. Verify backup/recovery points and run restore tests if needed.
3. Verify HCX site pairing, routes, DNS, IP plan, quotas, and target capacity.
4. Run a pilot migration on a non-critical VM.
5. Test the application inside an isolated target segment to prevent unintended side effects.
6. Freeze configs or drain traffic according to workload type.
7. Execute final sync/cutover via the chosen method.
8. Verify VM boot, guest services, latency, database consistency, and business transactions.
9. Cut over traffic/DNS and monitor error rates and latency.
10. Obtain business sign-off; retain source VMs per retention and rollback policies.

### 10.2. Avoiding Split-Brain

If source and target VMs run simultaneously and both write to a shared database or consume from a queue, data corruption or duplication will occur. Enforce a **single authoritative writer at cutover** via fencing and traffic controls.

Once the target accepts live writes, rolling back to source is never as simple as powering the source VM back on: you need data reconciliation or a tested reverse-replication/forward-fix procedure.

## 11. Shared Operational Responsibility: Who Does What?

### 11.1. Google Cloud-Managed VMware Engine

| Area | Primary Google Cloud Responsibility | Primary Customer Responsibility |
|---|---|---|
| Datacenter, power, bare metal | Supplies and remediates physical infrastructure | Selects appropriate locations and capacity |
| ESXi host lifecycle | Manages supported VMware stack | Coordinates maintenance windows, understands VM impact |
| vCenter/NSX/HCX management appliances | Deploys and operates service components | Configures usage, RBAC, network segments, and integrations |
| Default vSAN setup | Establishes base platform | Chooses/adjusts workload storage policies and capacity |
| Private cloud resources/nodes | Service-level provisioning | Requests, quotas, scaling, and cost ownership |
| Guest VMs and OSes | Does not manage application OSes | OS hardening, security patches, anti-malware |
| In-VM databases | Does not manage data engines | SQL backups, patching, replication, consistency |
| Apps / business transactions | None | CI/CD, performance, availability, data integrity |
| Workload backups | Backs up service management components | Backs up/restores customer workloads and tests DR |
| IAM and guest network policies | Provides controls and capabilities | Assigns roles, rotates secrets, sets NSX/firewall rules, audits |
| Application compliance | Infrastructure per service commitments | Data classification, retention, compliant app design |

**Google managing the VMware environment does not mean Google manages your application VMs.** This misconception commonly leads to missing backups, unpatched guest OSes, and untested DR plans.

### 11.2. VMware Solution on Bare Metal (BYOL)

Under VMware solution on Google Cloud, the customer also owns:

- Supplying VCF licenses and tracking entitlements/renewals.
- Installing and configuring the SDDC stack, vSphere, vSAN, and NSX.
- Scheduling patches and upgrades across VMware software.
- Administering SDDC Manager, vCenter/NSX, and system configurations.
- Planning management-plane recovery and VCF lifecycle operations.

Google Cloud still manages physical datacenter, bare-metal, and underlying network infrastructure within service boundaries. Always consult the dedicated **BYOL shared responsibility** documentation rather than substituting the managed-service matrix.

## 12. Access Control: IAM vs. vCenter RBAC

Two parallel authorization planes exist:

| Layer | Authorization System | Examples |
|---|---|---|
| Google Cloud resource control | Google Cloud IAM | Creating private clouds, viewing nodes, calling VMware Engine API |
| VMware management | vCenter Single Sign-On / RBAC | Creating/editing VMs, vSphere inventory, resource pools |
| NSX networking | NSX roles and firewall/security policies | Creating segments, modifying gateways/firewalls |
| Guest OS | AD / Linux users / sudo / SSH / RDP | Logging into Windows/Linux VMs |
| Application data | Database / app authorization | `SELECT`/`UPDATE` privileges, data access |

### 12.1. Project IAM

Google Cloud provides predefined VMware Engine roles such as VMware Engine Service Viewer and Service Admin. Assign roles matched to need; avoid granting broad `Owner`/`Editor` roles merely to view private clouds.

IAM roles on the VMware Engine API **do not automatically grant** Windows VM login rights or vCenter inventory access.

### 12.2. CloudOwner in vCenter

Managed private clouds include the default user `CloudOwner@gve.local` with `Cloud-Owner-Role`. It covers most day-to-day VMware tasks, though it is not unrestricted root across Google-managed components. When advanced tasks require elevation, use the service's authorized elevation mechanism and time windows.

Never share a single admin account across engineers. Standardize on an identity source, group-based roles, MFA where supported, audit logging, and controlled break-glass accounts.

### 12.3. Securing the Management Plane

- Restrict access to vCenter/NSX/HCX over private networks or controlled VPNs.
- Isolate the management CIDR from workload segments.
- Monitor permission edits and NSX firewall changes.
- Rotate credentials and service accounts regularly.
- Enforce TLS/certificates, DNS, and synchronized time (NTP).
- Never commit management credentials to Git or logged CLI commands.

## 13. Day 0: Designing Before Creating a Private Cloud

Day 0 settles decisions that are **painful to change later**.

Checklist:

1. BIA and RTO/RPO targets for every workload.
2. Choose Managed vs. BYOL model; verify licenses and contracts.
3. Select supported regions/zones and node types.
4. Establish projects/folders, billing accounts, labels, quotas, and IAM.
5. Choose standard vs. stretched; size node counts for HA.
6. Design management CIDRs, workload NSX segments, and HCX networks.
7. Plan VPN/Interconnect, BGP, Cloud Router, routes, and DNS.
8. Size compute/RAM/vSAN capacity, VM counts, and host-failure headroom.
9. Choose storage policies and external NFS datastores where appropriate.
10. Plan backups, DR, and security baselines.
11. Estimate costs for on-demand/commitments, network egress, and licenses.
12. Verify supporting services like AD/DNS/NTP, monitoring, and log sinks.

**Overlapping CIDRs or picking the wrong private cloud type** costs far more effort to fix later than resizing vCPUs on a migrated VM.

## 14. Day 1: Provisioning and Onboarding Workloads

In the managed model, Day 1 typically follows:

1. Enable the VMware Engine API and confirm billing, quotas, and permissions.
2. Create a Standard VMware Engine network or attach an approved existing one.
3. Create the private cloud specifying location, cluster, node type, node count, and management range.
4. Wait for provisioning to finish; inspect vCenter/NSX/HCX and node health.
5. Establish VPC peering, DNS bindings, and hybrid routing.
6. Build NSX segments and application firewall policies.
7. Configure vCenter RBAC/identity sources, resource pools, and folders.
8. Configure backups, syslog, metrics, alerts, and capacity thresholds.
9. Test a small VM, networking, and backup/restore before bulk migration.
10. Migrate workloads in waves, validate, and hand over to operations.

### 14.1. Illustrative Google Cloud CLI Inspection

These **read-only** inventory commands can be run once permissions are granted:

~~~bash
PROJECT_ID="example-vmware-project"
LOCATION="asia-southeast1-a"
PRIVATE_CLOUD_ID="orders-vmware"

gcloud services list \
  --enabled \
  --project="$PROJECT_ID" \
  --filter="name:vmwareengine.googleapis.com"

gcloud vmware locations list \
  --project="$PROJECT_ID"

gcloud vmware private-clouds list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

gcloud vmware private-clouds clusters list \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --private-cloud="$PRIVATE_CLOUD_ID"
~~~

Use a zonal location for standard private clouds; stretched private clouds are regional resources. Match location type to actual resources and CLI docs. These commands do not create, delete, or modify resources.

### 14.2. Why Doesn't This Lab Create a Private Cloud?

A production private cloud provisions multiple dedicated bare-metal nodes, carrying substantial cost alongside quota and licensing requirements. Accordingly, this lesson provides **a reviewable design workflow and read-only inventory commands**, rather than requiring learners to launch three-node clusters in production.

Once approved, provision via the Google Cloud Console or `gcloud vmware` per organizational runbooks; double-check node types, CIDRs, quotas, and cost estimates **before clicking Create**.

## 15. Day 2: Ongoing Operations

Work does not end after cutover. Minimum operational cadence:

| Cadence | Tasks | Evidence |
|---|---|---|
| Daily | Check node, cluster, and vSAN health, alarms, and backup jobs | Dashboards, tickets, alerts |
| Weekly | Review guest OS patches, capacity trends, failed backups, NSX policy drift | Reports and action items |
| Monthly | Review VMware/Google security advisories, spend, utilization, inventory, quotas | Change reviews |
| Quarterly | Restore drills, failover tabletop exercises, IAM reviews, security assessments per policy | DR reports, sign-offs |
| Post-wave | Reconcile VM inventory, NSX routes, DNS, and backup policies | Migration evidence |
| Pre-major change | Snapshots/backups, rollback plans, maintenance windows | Approved change records |

Assign clear owners for the VMware platform, networking, guest OSes, apps/databases, security, monitoring, and FinOps. Never escalate guest VM failures to Google Cloud ops if the root cause sits inside the OS or application config.

## 16. Capacity Planning: vCPU, RAM, Storage, and HA Headroom

Assess source VMs using:

- Allocated vCPU/RAM vs. actual P95/P99 utilization.
- Peak CPU ready time and memory ballooning/swapping.
- Provisioned vs. used disk and IOPS/latency.
- VM reservations, resource pools, and affinity/anti-affinity rules.
- VM counts by tier and peak business hours.
- Core- or socket-bound software licenses.
- 6–24 month data growth projections.
- Capacity required to survive host failures or maintenance.

### 16.1. Never Treat Raw Storage as Usable Capacity

Suppose a private cloud has 3 nodes with 19.2 TB raw storage each (illustrative for one node type, not guaranteed in all locations). Total raw capacity is:

\[
3 \times 19.2 = 57.6\ \text{TB raw}
\]

Usable capacity is **smaller** due to vSAN FTT/RAID policies, metadata, dedup/compression ratios, slack/rebuild space, and management VM overhead. Never treat 57.6 TB as available application storage.

A sizing worksheet should capture:

| Demand | Illustrative Value | Must Verify |
|---|---:|---|
| 60 VMs | Current inventory | Boot order, reservations |
| P95 CPU | 900 GHz-hours or matching metric | Translate to real node type |
| Allocated RAM | 4 TiB | Active/consumed memory and headroom |
| Used disk | 20 TiB | FTT policy, usable vSAN capacity |
| P95 storage IOPS | From source telemetry | Node/storage policy latency |
| HA reserve | N+1 or approved policy | Survive 1-node failure |
| Growth | 20%/year | Quotas, storage expansion |

Never size CPU purely from vCPU counts, as overcommit ratios and workload profiles vary widely. Run assessments and validate performance post-migration.

## 17. Autoscaling and Cluster Expansion

Managed VMware Engine supports cluster autoscaling driven by CPU, RAM, and storage utilization when service conditions are met. You can configure min/max nodes, scale-out/scale-in thresholds, step counts, and cool-off periods.

Key constraints:

- Does not apply to **single-node clusters**.
- Does not apply to clusters with storage-only nodes per autoscale documentation limits.
- Scaling out remains constrained by **quotas and capacity in that location**.
- Cluster autoscale does not automatically horizontally autoscale guest VMs per request/second.
- Scale-in must respect vSAN rebuilds, DRS, and HA capacity; never trim right down to the edge solely to save money.

### 17.1. Illustrative Policy Example

| Parameter | Example Value | Explanation |
|---|---:|---|
| Min nodes | 3 | Floor to preserve standard HA |
| Max nodes | 6 | Budget ceiling |
| Scale-out threshold | Sustained 75% CPU | Avoid prolonged saturation |
| Scale-in threshold | Sustained < 40% CPU | Avoid shrinking while busy |
| Cool-off | Per policy and docs | Prevent node count thrashing |
| Failure reserve | N+1 | Preserve placement after node loss |

Thresholds are purely illustrative. Google Cloud autoscale evaluates sustained utilization per service algorithms, weighing CPU, memory, and storage differently for scale-out vs. scale-in. Test in a real environment and avoid running critical workloads in clusters lacking quota to scale out during incidents.

## 18. Storage: vSAN and External Datastores

vSAN aggregates ESXi node storage into workload datastores. Storage policies (FTT, layout, fault tolerance) govern usable capacity, performance, and rebuild behavior.

When storage grows faster than CPU/RAM demand, adding full compute nodes purely for disk space can be wasteful. VMware Engine also supports **external NFS datastores** backed by compatible services like Filestore or Google Cloud NetApp Volumes under product terms.

| Option | When to Consider | Notes |
|---|---|---|
| Default vSAN | VMs needing high performance / converged compute-storage | FTT, capacity headroom, vSAN health |
| Storage-only nodes (where supported) | Need extra storage without adding compute | Node family, cluster policy, autoscale limits |
| External NFS datastore | Separate storage scaling, tier-2/3 data, backups | Throughput/latency, networking, security, fault domains |
| Guest-level dedicated storage | Databases/apps needing distinct protocols | Managed inside OS/app with separate backups |

Not every Filestore or NetApp volume mounts directly to every cluster: confirm supported service tiers, regions, network peering, and NFS datastore capabilities.

## 19. Maintenance and VMware Software Lifecycle

In **Google Cloud-managed** VMware Engine, Google handles lifecycle updates and security patches for the service's VMware software. Updates include patches, minor updates, and major upgrades.

Customers still need to:

- Monitor maintenance notifications / Update Center and rollout schedules.
- Verify compatibility of agents, backup vendors, guest OSes, and applications.
- Coordinate maintenance windows for sensitive workloads.
- Ensure DRS/HA/vSAN hold enough headroom to evacuate VMs during host maintenance.
- Validate application health post-update.
- Maintain change records and support escalation paths.

Some critical security patches apply under service policy without indefinite customer deferral options. Never attempt to manually patch ESXi/vCenter on a managed private cloud using self-managed VMware procedures.

Under **BYOL VCF**, the customer owns patching/upgrading the VMware stack. Maintain dedicated schedules and tooling in your SDDC runbook.

## 20. Backup and Disaster Recovery for Workload VMs

Google manages backups/restores of **management services**, while workload VMs and business data remain the customer's responsibility.

Use Google Cloud Backup and DR or compatible VMware backup tools to protect:

- Guest VM configs and virtual disks.
- Database-aware backups (SQL Server, Oracle, PostgreSQL, etc.).
- Application state, transactions, and secrets.
- File shares and external datastores if used.
- Recovery runbooks targeting an alternate private cloud or region.

~~~mermaid
flowchart TD
    VM["Workload VMs<br/>managed VMware Engine"]
    BK["Backup product + backup policy"]
    REPO["Backup repository<br/>Cloud Storage / NFS / appropriate target"]
    TARGET["Restore target<br/>private cloud / standby infrastructure"]
    TEST["DR drill + business validation"]

    VM --> BK --> REPO
    REPO --> TARGET --> TEST
~~~

### 20.1. HA Is Not DR

- vSphere HA restarts VMs after a node failure, but cannot undo accidental data deletion.
- vSAN replication/FTT survives hardware faults, not logical corruption without clean historical backups.
- Stretched clusters survive single-zone outages within a region, not full-region unavailability.
- Only backups/restores or replication to an independent region cover regional disasters.
- RPO/RTO are targets proved via restore drills—not automatic perks of running multiple nodes.

### 20.2. Per-Workload RTO/RPO

Example targets for a VM-hosted Orders DB:

| Scenario | Target RPO | Target RTO | Option to Evaluate |
|---|---:|---:|---|
| Single ESXi node failure | At least per transaction durability | ≤ 30 min | vSphere HA + sufficient capacity |
| Accidental table drop | 15 min | 2 hours | Separate database PITR/backups |
| Single zone outage | Per policy | ≤ 1 hour | Stretched (if supported in region) or DR |
| Full region outage | ≤ 1 hour | ≤ 8 hours | Cross-region backups/replicas and runbook |

These values are business examples, not VMware Engine SLAs. Record actual recovery points and recovery times during drills with consistent datasets.

## 21. Observability and Incident Response

A solid dashboard spans Google Cloud, vCenter, and guest OS layers.

| Layer | Signals | Tools |
|---|---|---|
| Google Cloud project | Private cloud operations, node events, audit logs | Google Cloud Logging/Monitoring, Essential Contacts |
| VMware cluster | CPU/memory/vSAN capacity, HA/DRS events | vCenter, VMware Aria Operations |
| Network | NSX firewall drops, gateway health, latency | NSX Manager, syslog, network telemetry |
| HCX / migration | Migration tasks, transfer status, errors | HCX Manager/vCenter |
| Guest OS | CPU/memory/disk, patch level, antivirus | Guest monitoring agents and OS tooling |
| Application | 5xx, P95/P99 latency, throughput, transaction errors | Application tracing/APM, logs |
| Database | Connections, query latency, replication lag, backup status | DB-native metrics and backup dashboards |

Google Cloud VMware Engine emits service alerts/logs supporting log-based alerting. To ingest vCenter/VMware metrics into Cloud Monitoring, documentation describes integrating via a standalone agent/BindPlane; forwarding must be configured per private cloud and may incur metric ingestion fees.

### 21.1. Priority Alerts

- Node failures or vSAN health degradation.
- vSAN disk utilization and capacity/rebuild headroom.
- Prolonged CPU ready time or memory contention.
- HCX migration failures, stalled tasks, or network extension faults.
- DNS/routing/TLS failures to vCenter/NSX/HCX.
- Backup job failures or aging restore points.
- Full guest OS disks, crashed services, or patch drift.
- Application latency spikes, 5xx errors, or failed transactions.
- Costs or node counts breaching budget.

Separate Google-handled service-level incidents from customer-owned application failures. Every alert needs an explicit **owner and escalation path** in the runbook.

## 22. Connecting to Google Cloud-Native Services

A key benefit of VMware Engine is keeping legacy VMs while letting applications tap into modern Google Cloud services.

Example:

~~~mermaid
flowchart TD
    VM["VMware Engine: Java app VM"]
    VEN["VMware Engine network"]
    VPC["Google Cloud VPC"]
    SEC["Secret Manager / Cloud KMS"]
    CS["Cloud Storage"]
    SQL["Cloud SQL"]
    NATIVE["Cloud Run / GKE services"]

    VM --> VEN --> VPC
    VPC --> SEC
    VPC --> CS
    VPC --> SQL
    VPC --> NATIVE
~~~

Integration points to verify:

1. Ensure valid VPC routes and DNS; never assume every public API has a private path.
2. Establish workload identity / short-lived credentials for VMs instead of hardcoded JSON keys.
3. Grant least-privilege IAM roles to buckets, secrets, databases, or APIs.
4. For Cloud Storage, verify network egress, object operations, and access controls.
5. For Cloud SQL, evaluate latency, connection pooling, and network topology.
6. For private Cloud Run services, design proper authentication/ingress and routing—not just IP pings.
7. Attribute costs cleanly between VMware Engine and native services.

VMware Engine is a **strategic transition stage**, not a mandate to keep every workload in VMs forever. Modernize suitable apps incrementally.

## 23. Automation and Controlled Configuration

Operating multiple private clouds manually invites drift across IAM, networking, storage policies, and backups. Define desired state via organization-approved IaC/automation within supported API boundaries.

Automation domains:

| Component | Tooling / Approach | What to Avoid |
|---|---|---|
| VMware Engine resources | Google Cloud CLI / API / Terraform provider where supported | Destructive applies on live private clouds |
| vCenter inventory / VMs | VMware PowerCLI, vSphere automation | Creating VMs bypassing naming/backup policies |
| NSX segments / firewalls | NSX policy API or config management | Leaving `Any/Any` rules open post-migration |
| Guest OS | Ansible / SCCM / patch automation | Fleet-wide patching without canaries |
| Backups | Backup policy-as-code / scheduling | Mistaking backup job success for restore proof |
| Monitoring | Dashboards/alerts as code | Alerts without owners or notifications |
| DR | Runbooks, test workflows, recovery-site IaC | Two primaries accepting writes simultaneously |

**Crucial distinction:** applying Terraform to Google Cloud VMware Engine resources does not replace VMware APIs for configuring individual VMs or NSX objects. Clarify ownership boundaries and manage drift across control planes.

## 24. FinOps: Modeling Total Cost Beyond Node Price

VMware Engine spend is driven heavily by node type, node count, and duration, though full TCO spans far more items.

| Component | Cost Driver |
|---|---|
| VMware Engine nodes | Node-hours, node type, count, location |
| Pricing model | On-demand, commitments, license-included, or eligible portable/BYOL |
| HA headroom | Standby nodes or unallocated capacity buffer |
| Storage | vSAN capacity, external NFS datastores, backup repositories |
| Network | VPN/Interconnect, peering topology, data transfer, NAT |
| Backup / DR | Backup software, vault storage, replication, recovery drills |
| Logging / Monitoring | Custom metrics, log ingestion, retention |
| Guest OS / DB licenses | Windows Server, SQL Server, third-party vendor licenses |
| Operations staffing | VMware/OS/security/network on-call teams |
| Hybrid overlap | Running source datacenter and GCP in parallel during migration |

### 24.1. Hypothetical Node-Hour Calculation

Suppose a standard private cloud runs 3 nodes continuously for 730 hours/month at a **purely hypothetical** rate of $5 USD/node-hour:

\[
C_{\text{nodes}} = 3 \times 730 \times 5 = 10,950\ \text{USD/month}
\]

This excludes applicable licensing models, networking, backups, external storage, taxes, and discounts. Never treat $5 USD as an actual public price.

Adding one extra node for a full month:

\[
\Delta C = 730 \times 5 = 3,650\ \text{USD/month}
\]

This shows why casually "adding a node for more storage" may cost far more than evaluating storage-only nodes or external NFS datastores.

### 24.2. Commitments and Lifecycle

On-demand gives flexibility while migration timelines remain uncertain, yet becomes pricey for long-lived clusters. 1- or 3-year commitments lower rates per SKU/contract terms while reducing flexibility if node counts or workloads shrink.

Before committing:

- Run assessments measuring real CPU/RAM/storage and HA reserves.
- Segment VMs by likelihood of modernization within 6–24 months.
- Verify CUD terms, licensing, portability, and node family rules.
- Account for datacenter-cloud overlap costs.
- Model scale-up/scale-down scenarios alongside capacity and quotas.
- Attach budget alerts, billing labels, and owners.

**Never commit node counts based solely on currently allocated VM vCPUs**, as overprovisioning and headroom skew estimates.

## 25. Case Study: Three-Tier Application in VMware Engine

An enterprise runs:

- Web: 4 Windows/Linux VMs.
- App: 6 Java/Spring Boot VMs.
- Database: 2 SQL Server VMs.
- AD, DNS, NTP, and on-premises backup infrastructure.
- Business transaction requirement: 4-hour RTO, 30-minute RPO.

### 25.1. Target Architecture

~~~mermaid
flowchart LR
    USERS["Users"]
    EDGE["HTTPS edge / network firewall"]
    subgraph GCVE["VMware Engine private cloud"]
      WEB["Web VMs / NSX segment"]
      APP["Java app VMs / NSX segment"]
      DB["SQL Server VMs / NSX segment"]
      WEB --> APP --> DB
    end
    VPC["Google VPC / peering"]
    DC["On-prem AD/DNS + hybrid link"]
    BACKUP["Backup repository + DR plan"]
    USERS --> EDGE --> WEB
    GCVE --> VPC
    VPC <--> DC
    GCVE --> BACKUP
~~~

### 25.2. Migration Stages

1. Assessment: identify owners, CPU/RAM/IOPS, services, networking, and SQL dependencies.
2. Select managed private cloud and standard vs. stretched per RTO.
3. Design CIDRs, on-prem Cloud VPN/Interconnect, DNS/AD, and NSX segments.
4. Provision the private cloud, vCenter roles, backups, and monitoring.
5. Pilot-migrate two non-critical VMs and validate the application end-to-end.
6. Migrate web/app tiers in waves; never move the database without a transactional consistency plan.
7. Migrate SQL Server via backup/replication or appropriate tooling; enforce write freezes/cutovers as needed.
8. Verify authentication, order transactions, reports, failover, latency, and costs.
9. Cut over traffic, monitor through hypercare, and decommission source VMs after formal approval.

### 25.3. Key Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Overlapping CIDRs | Broken routing | Complete IP plan before provisioning |
| Overly permissive NSX segments | Lateral movement | Microsegmentation and policy reviews |
| App and DB separated, higher RTT | Slow SQL transactions | Dependency mapping and co-located waves |
| Missing HA reserve | Host failure exhausts capacity | N+1 headroom and stress testing |
| Untested backup restores | Data loss at cutover | Restore drills and recovery point validation |
| Per-core licensing shifts | Budget overrun | License inventory and vendor sign-off |
| Unreachable SSO/AD/DNS | Login failures | Test identity paths from target VMs |
| HCX migration stalls | Delayed cutover | Network preflight, checkpoints, rollbacks |

## 26. Recommended Lab Exercise: Design First Without Node Costs

This lab can be completed **without creating a new private cloud**, teaching design and operational mechanics safely.

### Step 1: Build an Inventory

Create an illustrative table:

| VM | Role | OS | vCPU | RAM | Used Disk | Target |
|---|---|---|---:|---:|---:|---|
| web-01 | Web | Linux | 4 | 8 GiB | 60 GiB | Web segment |
| app-01 | Java API | Linux | 8 | 16 GiB | 150 GiB | App segment |
| db-01 | DB | Windows | 16 | 64 GiB | 1 TiB | DB segment |
| ad-01 | Identity | Windows | 4 | 16 GiB | 80 GiB | Management/identity design |

Identify hard dependencies for each VM along with failover and backup requirements.

### Step 2: Select the Model

Answer:

- Managed or BYOL, and why?
- Standard or stretched?
- Minimum node count required for production HA policy?
- Can single-node be used for PoC?
- Which storage policy/FTT and how much headroom?

### Step 3: Design IPs and Routing

Diagram:

- Management CIDR non-overlapping with workloads, VPCs, and on-premises.
- Standard VMware Engine network and VPC peering.
- Cloud VPN/Interconnect to the datacenter.
- DNS forwarding/bindings and vCenter FQDN.
- NSX segments for Web/App/DB.
- Path from the web VM to a Google Cloud-native service.

### Step 4: Run Read-Only Inventory Commands (If Environment Exists)

~~~bash
gcloud vmware locations list --project=PROJECT_ID

gcloud vmware private-clouds list \
  --project=PROJECT_ID \
  --location=LOCATION

gcloud vmware private-clouds clusters list \
  --project=PROJECT_ID \
  --location=LOCATION \
  --private-cloud=PRIVATE_CLOUD_ID
~~~

Replace placeholders with authorized real project/location values. Without an active environment or permissions, record hypothetical outputs rather than provisioning billable resources.

### Step 5: Draft a Migration Runbook

Include columns: Wave, VM group, source/destination segments, HCX/migration method, downtime, rollback point, business owner, validation, and sign-off.

### Step 6: Readiness Check

You pass when you can clearly explain:

- Who patches ESXi/vCenter vs. who patches guest OSes?
- Who creates backups for database guest VMs?
- Why doesn't VPC peering automatically create transitive routes everywhere?
- Why is single-node unsuitable for production HA?
- How are RTO/RPO measured and how do rollbacks prevent split-brain?
- What is required for VMs to access Cloud SQL/Cloud Storage securely?

## 27. Operational Troubleshooting

| Symptom | Possible Cause | Checks |
|---|---|---|
| Cannot open vCenter URL | Missing VPN/peering/DNS/firewall or account issue | Test FQDN, routes, ACLs, identity source |
| GCP VM cannot reach VMware workload | Wrong VPC peering, custom route, or NSX policy | Check VPC routes, VEN peering, return path, NSX |
| On-prem cannot reach VMware Engine | BGP/Cloud VPN/Interconnect, DNS, or firewall issue | Check tunnel/BGP health, CIDRs, route import-export |
| HCX fails to connect | Blocked ports, bad site pairing, MTU/cert mismatch | Inspect HCX appliance logs, connectivity, compatibility |
| Migrated VM cannot reach DB | IP/segment/firewall change or hardcoded DB host | Check DNS, NSX rules, DB listener, app config |
| vSAN nearly full | Workload growth, FTT overhead, or rebuilds | Inspect vSAN capacity health, storage policy, node plan |
| High CPU ready time | Oversubscription, contention, or placement | Check vCenter performance, DRS, and capacity |
| Autoscale won't add nodes | Quota/capacity limit or policy threshold unmet | Check quotas, sustained usage, autoscale eligibility |
| Missing vCenter metrics in Cloud Monitoring | Unconfigured agent/forwarder | Check BindPlane/standalone agent, exports, permissions |
| Backup succeeds but restore fails | Untested recovery or missing credentials/target | Run restore drill on isolated target |
| Sudden cost spike | Node scale-out, expired commitment, egress, or logs | Audit Cloud Billing by SKU/node usage |
| Guest OS unpatched after host update | Misunderstood shared responsibility | Audit OS patch inventory and app owners |
| Network extension instability | Overly long L2 stretch, latency/broadcast loops | Review NSX/HCX design and cutover timeline |

## 28. Production Readiness Checklist

- [ ] Google Cloud-managed vs. BYOL VCF chosen with documented responsibilities.
- [ ] Supported location and node types verified alongside quotas and capacity.
- [ ] Standard/single-node/stretched matched to fault domains and RTO/RPO.
- [ ] Node counts include headroom to survive host failures per policy.
- [ ] Management CIDRs, workload segments, and on-prem/VPC CIDRs have zero overlap.
- [ ] VMware Engine network, VPC peering, and hybrid routing verified bidirectionally.
- [ ] DNS works for vCenter/NSX/HCX and guest workloads.
- [ ] NSX segmentation, firewalls, TLS, and identity access enforce least privilege.
- [ ] Google Cloud IAM and vCenter RBAC governed separately with auditing and break-glass access.
- [ ] VMware lifecycle/maintenance processes aligned with Managed or BYOL model.
- [ ] Guest OSes, databases, middleware, and apps have assigned owners and patching workflows.
- [ ] Capacity, FTT, usable vSAN size, IOPS, and storage policies properly sized.
- [ ] HCX/migration waves include testing, bandwidth checks, and rollback procedures.
- [ ] Cutovers prevent dual writers from corrupting data.
- [ ] Independent workload backups exist and restore drills PASS.
- [ ] Zone/region/data-corruption DR scenarios documented.
- [ ] Logs, metrics, alerts, syslog, and notification contacts have clear owners.
- [ ] Cloud Billing, commitments, licenses, networking, and backup spend covered by budget alerts.
- [ ] Clear roadmap exists for VMs slated to modernize onto GKE, Cloud Run, or Compute Engine.
- [ ] Business owners signed off on availability, data integrity, and performance.

## 29. Self-Check Questions

**1. How does Google Cloud VMware Engine differ from Compute Engine VMs?**

VMware Engine provides dedicated bare-metal hardware and a VMware stack (ESXi, vCenter, vSAN, NSX, HCX) to operate VMs with VMware tooling. Compute Engine provides Google Cloud-native virtual machines with a different management model.

**2. How do Google Cloud-managed and VMware solution BYOL differ?**

The managed service has Google manage the VMware stack lifecycle with service-included licensing; BYOL lets customers deploy/manage VCF and bring their own licenses on Google bare metal. Both models leave guest workload management to the customer.

**3. Why avoid single-node clusters for critical production?**

Single-node lacks full HA/DRS/vSAN multi-node redundancy and fault tolerance. It is meant for PoCs and labs.

**4. How does a Standard VMware Engine Network connect to a VPC?**

Via VPC Network Peering. Legacy networks use a separate private services access model for older environments; never mix configurations between the two.

**5. Does HCX eliminate network preparation for migrations?**

No. HCX requires connectivity between source VMware and VMware Engine, plus proper routing, ports, DNS, and stack compatibility. Cloud VPN/Interconnect provides the recommended hybrid connectivity layer.

**6. Does Google managing vCenter mean Windows VMs are backed up automatically?**

No. Workload and database guest VM backups/DR remain the customer's responsibility. Google manages management-plane services within the managed service boundary.

**7. Why doesn't 60 TB raw vSAN equal 60 TB usable storage?**

FTT, storage policies, metadata, overhead, management VMs, and rebuild slack reduce usable storage. Measure usable space under actual policies on the cluster.

**8. Can VPC peering act as a transit router across all VPCs?**

No. Peering is non-transitive by default. Verify network topology, route advertisements, and peering limits.

**9. How does stretched-cluster failover differ from multi-region DR?**

A stretched cluster tolerates a single-zone failure within one region under supported configurations. Multi-region DR requires standby infrastructure and data outside the region, traffic routing, and dedicated runbooks.

**10. When should you modernize onto Cloud Run or GKE?**

When applications can be stateless/containerized and benefit from cloud-native autoscaling/CI/CD, and when costs, migration risk, and compatibility align. VMware Engine is one tool in a broader strategy—not the permanent home for every VM.

## 30. References

- [VMware Engine documentation](https://cloud.google.com/vmware-engine/docs)
- [Google Cloud VMware Engine overview](https://cloud.google.com/vmware-engine/docs/overview)
- [Compare VMware Engine operating models](https://cloud.google.com/vmware-engine/docs/vmware-solution/compare-models)
- [VMware solution on Google Cloud BYOL overview](https://cloud.google.com/vmware-engine/docs/vmware-solution/overview)
- [VMware solution on Google Cloud shared responsibility](https://cloud.google.com/vmware-engine/docs/vmware-solution/shared-responsibility)
- [Managed VMware Engine shared responsibility](https://cloud.google.com/vmware-engine/docs/shared-responsibility)
- [About VMware Engine private clouds](https://cloud.google.com/vmware-engine/docs/concepts-private-cloud)
- [About private cloud VMware components](https://cloud.google.com/vmware-engine/docs/concepts-vmware-components)
- [Creating a VMware Engine private cloud](https://cloud.google.com/vmware-engine/docs/private-clouds/howto-create-private-cloud)
- [Stretched private clouds](https://cloud.google.com/vmware-engine/docs/concepts-stretched-private-cloud)
- [About VMware Engine networks](https://cloud.google.com/vmware-engine/docs/networking/vmware-engine-network)
- [Networking requirements](https://cloud.google.com/vmware-engine/docs/quickstart-networking-requirements)
- [VPC peering to VMware Engine](https://cloud.google.com/vmware-engine/docs/networking/peer-vpc-network)
- [Connecting on-premises networks](https://cloud.google.com/vmware-engine/docs/networking/howto-connect-to-onpremises)
- [Workload VM migration options](https://cloud.google.com/vmware-engine/docs/workloads/howto-migrate-workloads)
- [Migrating VMs using HCX](https://cloud.google.com/vmware-engine/docs/workloads/howto-migrate-vms-using-hcx)
- [vSphere permission model](https://cloud.google.com/vmware-engine/docs/concepts-permission-model)
- [Managing VMware Engine IAM roles](https://cloud.google.com/vmware-engine/docs/iam)
- [Managing autoscale](https://cloud.google.com/vmware-engine/docs/howto-autoscale)
- [Private cloud maintenance and updates](https://cloud.google.com/vmware-engine/docs/concepts-maintenance-updates)
- [Backup workload VMs](https://cloud.google.com/vmware-engine/docs/concepts-backup-vms)
- [VMware Engine data protection recommendations](https://cloud.google.com/vmware-engine/docs/data-protection-recommendations)
- [Monitoring VMware Engine](https://cloud.google.com/vmware-engine/docs/concepts-monitoring)
- [VMware Engine security best practices](https://cloud.google.com/vmware-engine/docs/best-practices-security)
- [VMware Engine storage practices](https://cloud.google.com/vmware-engine/docs/best-practices-storage)
- [Google Cloud VMware Engine pricing](https://cloud.google.com/vmware-engine/pricing)
