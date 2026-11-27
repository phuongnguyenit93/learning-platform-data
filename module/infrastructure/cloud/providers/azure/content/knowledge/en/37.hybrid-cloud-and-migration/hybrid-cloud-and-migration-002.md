# Azure Migrate for Discovery, Assessment, and Dependency Mapping

## 1. From a Server List to an Evidence-Based Migration Plan

An enterprise wants to move applications from an on-premises data center (*on-premises*) to Microsoft Azure. The infrastructure team has a list of 40 virtual machines with total CPU and RAM, but does not yet know which servers are actually active, which ones only run at month-end, which applications connect to which databases, or whether a VM could be replaced by a PaaS service. Moving machines one by one based only on hostnames or allocated specs risks missing a critical dependency, over-sizing Azure VMs, or migrating a database before its application is ready.

**Azure Migrate** provides a central hub to **discover**, **assess**, and orchestrate the **migration** of supported workloads to Azure. In this lesson, we dive into the three pre-cutover activities:

1. **Discovery:** knowing which servers/resources exist, how they are running, and whether metadata is trustworthy.
2. **Assessment:** determining readiness, target options, recommended sizing, risks, and estimated costs under stated assumptions.
3. **Dependency mapping:** identifying communication relationships across servers, applications, and dependent systems so workloads move in logical groups rather than isolated machines.

Across the Azure learning path—from subscriptions, resource groups, Microsoft Entra ID, virtual networks, compute, storage, and data to security and cost—Azure Migrate is the bridge between the **existing environment** and a **governed target architecture**. It does not replace an Azure landing zone, hybrid connectivity design, or application testing.

### Lesson Objectives

After this lesson, you will be able to:

- Distinguish **Azure Migrate project**, *Discovery and assessment*, *Server Migration*, and specialized workload assessment tools.
- Plan discovery for VMware, Hyper-V, or physical/other supported sources; understand the roles of the appliance, credentials, and networking.
- Create an Azure VM assessment, explain **as-on-premises** vs. **performance-based** modes, and interpret readiness, sizing, confidence, and cost estimates.
- Interpret a dependency map by connection direction, IP/port, process, observation window, and data limitations.
- Group related machines into **application groups** and **migration waves**, pick a pilot, and handle dependencies remaining on-premises.
- Define acceptance criteria to move safely from discovery into test migration.

## 2. Azure Migrate Concepts and Components

~~~mermaid
flowchart TD
    S["Source: VMware / Hyper-V / physical / supported environment"] --> A["Azure Migrate appliance or corresponding discovery mechanism"]
    A --> P["Azure Migrate project"]
    P --> D["Discovery: inventory, metadata, performance"]
    D --> AS["Assessment: readiness, sizing, cost"]
    D --> DEP["Dependency analysis: connections, processes, IP/port"]
    AS --> PLAN["Application groups + migration waves"]
    DEP --> PLAN
    PLAN --> TEST["Pilot / test migration"]
    TEST --> CUT["Cutover per runbook"]
    CUT --> VAL["Validation and optimization on Azure"]
~~~

| Component | Role | What Not to Confuse It With |
| --- | --- | --- |
| **Azure Migrate project** | Central place holding tools, inventory, assessments, and data for a migration program | Creating a project does not connect or migrate servers |
| **Azure Migrate: Discovery and assessment** | Collects server inventory/usage and evaluates readiness, sizing, and cost for supported targets | Does not create target Azure VMs |
| **Azure Migrate appliance** | Component deployed in the source network to discover, collect, and send data to the project | Does not necessarily require an agent on every VM just for inventory; requirements vary by source and feature |
| **Assessment** | Configuration set and calculation results based on selected target and measurement assumptions | Not a guarantee that SKU quota is available or prices are fixed |
| **Dependency analysis / mapping** | Analyzes observed connections and interactions across systems | Not a complete diagram of all business flows |
| **Server Migration** | Separate toolset for replication, test migration, and cutover of supported servers | Distinct from discovery/assessment; viewing an assessment does not start migration |

Feature names, Azure Portal menu items, supported sources, assessment types, and dependency analysis mechanisms may change across service versions. Accordingly, the guidance below focuses on **stable principles and workflows**, while requiring you to verify support prerequisites for your actual source in the Azure Migrate interface in use.

### 2.1 Discovery, Assessment, and Mapping Answer Three Different Questions

| Question | Appropriate Data |
| --- | --- |
| How many servers exist, what OS do they run, and how much vCPU/RAM/disk do they have? | Inventory from discovery |
| Which Azure VMs can host the workload, and what is the estimated cost? | Assessment with target region, sizing, and pricing assumptions |
| Which SQL, file share, DNS, or SaaS endpoints does the web server connect to? | Dependency mapping combined with application owner confirmation |
| Can the database be moved without breaking remaining applications? | Dependency map, application diagram, test results, and cutover plan |
| When can source machines be powered off? | Post-migration runbook and sign-off, **not** an assessment result alone |

## 3. Running Scenario: The On-Premises Orders Application

Suppose an ordering system has the following architecture:

| Machine / Component | Function | Illustrative Source Specs | Information to Confirm |
| --- | --- | --- | --- |
| `web-01`, `web-02` | Web frontend / reverse proxy | 2 VMs, 4 vCPU, 8 GiB RAM each | HTTPS, certificates, sessions, DNS |
| `api-01`, `api-02` | Ordering REST API | 2 VMs, 8 vCPU, 16 GiB RAM each | TLS, throughput, queues, outbound calls |
| `sql-01` | SQL Server holding transaction data | 1 VM, 16 vCPU, 64 GiB RAM | Version/edition, HA, logs, I/O, backups, RPO |
| `batch-01` | Reconciliation and report generation jobs | 1 VM, 4 vCPU, 8 GiB RAM | End-of-day/month runs, file shares |
| `files-01` | File share for reports | 1 server | SMB/NFS, access permissions, retention |
| `dns-ad-01` | DNS, Active Directory, and infrastructure services | 1 or more shared admin servers | Domain join, DNS, identity, site-to-site connectivity |
| `payment-partner` | External payment API | Not in VM inventory | Egress, firewall allowlist, certificates, response times |

All names and figures in the table are **hypothetical learning data**, not measurements from a real Azure environment.

~~~mermaid
flowchart LR
    U["Customers"] --> F["Source load balancer / DNS"]
    F --> W["web-01 / web-02"]
    W --> API["api-01 / api-02"]
    API --> DB["sql-01"]
    API --> PAY["External Payment API"]
    API --> I["DNS/AD/identity"]
    JOB["batch-01"] --> DB
    JOB --> FILE["files-01"]
~~~

This is a **hypothesis diagram** supplied by the application team before discovery. The goal of dependency mapping is to compare observed connections against this hypothesis, uncover undocumented relationships, and decide which machines must move in the same wave.

## 4. Preparing Scope, Permissions, and the Azure Foundation

### 4.1 Lock Down Business Objectives Before Collection

Confirm with stakeholders:

- **In scope:** which servers, apps, sites, VLANs, clusters, databases, data, and partners are planned for Azure?
- **Out of scope:** third-party-managed services, servers restricted from tooling, sensitive OT/legacy systems.
- **Objectives:** data center cost reduction, resilience, scalability, modernization, or exiting unsupported software?
- **Constraints:** data residency, security, compliance, license agreements, allowed downtime, RTO/RPO, and cutover deadlines.
- **Owners:** approvers for vCenter/Hyper-V access, network admins, app/database owners, security, finance, and migration coordinator.

### 4.2 Prepare the Azure Target

Azure Migrate helps evaluate targets, but a production migration also requires a **landing zone**: proper subscription, management groups/policies, resource groups, Microsoft Entra ID and RBAC, Azure Virtual Network, subnets, NSGs, routing, DNS, private endpoints if needed, logging, backup, budgets, and tagging.

If systems must stay connected to on-premises during a hybrid phase, design **site-to-site VPN** or **ExpressRoute** (per requirements/budget), latency and bandwidth, DNS resolution, identity, IP addressing, and firewalls. A “Ready” assessment does not prove these network paths and permissions are working.

Before creating a project or deploying an appliance, confirm **metadata storage region** requirements, regional feature support, quotas, and organizational permissions. **The Azure Migrate project region does not dictate every target region choice in assessments**, but must be selected based on support documentation and data compliance requirements.

### 4.3 Access Permissions and Data Protection

Apply *least privilege*:

1. Azure permissions should only cover creating/managing the project, reading assessments, and configuring scoped components; separate migration/cutover operator roles where possible.
2. Source credentials (e.g., vCenter, Hyper-V, or guest credentials needed for software inventory/dependencies) must follow exact prerequisites—never grant domain admin merely for convenience.
3. Store **project keys, credentials, and appliance configuration** securely; restrict who can view discovered machines, IPs, processes, and software.
4. Verify outbound connectivity to required Azure endpoints per appliance documentation; never open broad inbound access or disable network controls just to “discover faster.”
5. Follow personal data regulations, report access controls, and retention rules; dependency maps can expose sensitive topology and security systems.

## 5. Discovery: Finding Servers and Usage Data

### 5.1 Create an Azure Migrate Project and Choose the Source

General Azure Portal workflow:

1. Sign in to the correct tenant and subscription; verify the appropriate resource group and region.
2. Open **Azure Migrate**, create or select a **project** for the program (e.g., `migrate-orders-dc1`), picking a supported region aligned with data storage requirements.
3. Under **Discovery and assessment**, select the source type in use: VMware vSphere, Hyper-V, physical, or another supported source.
4. Review the corresponding discovery method, appliance requirements, server count, access accounts, network ports, and Azure connectivity.
5. Prepare an appliance matching the environment and **project key/registration** per the guided flow; do not reuse a VMware appliance image for Hyper-V if the tool requires a different package.

Crucially: **creating a project, registering an appliance, and starting discovery do not move workloads**. Discovery does not alter the target application's data plane, though the appliance does generate traffic, collect metadata, and require source credentials/connections.

### 5.2 Role of the Azure Migrate Appliance

The appliance is typically deployed **close to the source environment** so it can read metadata and required metrics, then send discovery data to the Azure Migrate project over supported connections.

| Source | Conceptual Approach | Items to Prepare |
| --- | --- | --- |
| **VMware vSphere** | Appliance contacts vCenter to discover VMs, specs, and performance; guest-level discovery may need separate credentials | vCenter version/permissions, connectivity, appliance limits, and VMware Tools per feature |
| **Hyper-V** | Hyper-V appliance or discovery mechanism gathers inventory/metrics from supported hosts | Hyper-V hosts/clusters, permissions, ports, and compatible versions |
| **Physical / other supported sources** | Server discovery method using different permissions/credentials and connectivity than vCenter inventory | Authentication mechanism, OS, firewalls, completeness of performance data |

**Agentless** in VMware inventory usually means no Azure Migrate agent is needed on every VM to gather hypervisor metadata. **It does not mean** every application, process, database, or dependency discovery capability works unconditionally inside the guest. Certain features or other sources may require agents or extra credentials/extensions per current product guidance.

### 5.3 Verifiable Setup Steps

1. **Deploy the appliance** matching the template/source type, meeting current CPU/RAM/disk, OS, and networking requirements.
2. **Register the appliance** with the project using the provided key and mechanism; verify healthy connection status.
3. **Configure sources**: vCenter/hosts/IP ranges and least-privilege credentials; verify no wrong site or domain entries.
4. **Discover inventory**: verify VM count, names, UUID/resource keys, OS, vCPU, RAM, disks, and network adapters.
5. **Collect performance**: performance-based assessments need sufficient duration and metrics; verify data collection status.
6. **Enable guest discovery/dependency features** where supported and approved; verify software inventory, processes, and TCP connections contain real data.
7. **Monitor appliance health**: connection alerts, expired credentials, unreachable servers, missing metrics, and unexpected shifts in discovered object counts.

Do not jump straight into assessment immediately after registering the appliance without adequate usage history. Some metrics only populate after sufficient collection cycles; “discovered” and “performance data usable” are **two distinct states**.

### 5.4 Discovery Verification Checklist

| Check | Passing Condition |
| --- | --- |
| Coverage | Discovered server count reconciled against CMDB/hypervisor inventory; missing or duplicate hosts explained |
| Identity | No confusion between two machines sharing a name across sites; stable key/ID confirmed |
| OS/architecture | OS/version/boot type, vCPU/RAM, and disk layout not inexplicably “unknown” |
| Performance | Data covers business hours, batches, and peaks; percentage of missing telemetry known |
| Application owner | Every server mapped to an application, owner, and criticality tier |
| Sensitive scope | No out-of-scope topology collected or exposed |
| Data freshness | Last update timestamp is recent enough for decision-making |

Example: CMDB lists 120 in-scope VMs, Azure Migrate discovers 116; **coverage = 116/120 × 100% ≈ 96.7%**. Before declaring data sufficient, account for the 4 missing VMs: powered off long-term, missing permissions, special VMs, or stale CMDB?

## 6. Assessment: From Inventory to Azure Choices

### 6.1 Creating Groups and Assessments

Once discovery is sufficient, group servers belonging to **a specific application** (e.g., `orders-app`), then create an Azure VM assessment if pursuing **rehost**. Certain workloads have specialized assessment tools (such as databases or web apps) depending on supported sources/targets; never use an Azure VM assessment to conclude SQL can move straight to Azure SQL Database or an app is definitely App Service-compatible.

An assessment should specify:

- **Target:** Azure VMs or tool-supported target options; target region and availability/zone needs.
- **Sizing criterion:** as-on-premises or performance-based, along with performance history window and percentile chosen.
- **Scope:** which machines are included, which are excluded, and why.
- **VM preferences:** allowed VM families/series, OS, storage/disk types, HA assumptions, reserved headroom, and workload specifics.
- **Cost assumptions:** target region, currency, licenses/benefits, pricing options, or discounts supported in the assessment view.
- **Business constraints:** RTO/RPO, latency, data residency, security, quotas, deadlines, and data confidence.

**Save assessment configurations with versioning** (name, timestamp, data source, and assumptions); two assessments on the same server group with different sizing criteria or performance histories **cannot be compared as equivalent calculations**.

### 6.2 As-On-Premises vs. Performance-Based

| Criterion | As-On-Premises Sizing | Performance-Based Sizing |
| --- | --- | --- |
| Primary data | Allocated source capacity: cores, RAM, disks | Actual consumption during the chosen collection window |
| Benefit | Produces an initial plan even with sparse telemetry | Opportunity to eliminate over-provisioned capacity |
| Limitation | Carries over on-premises over-allocation | Can under-size if peaks, batches, guest metrics, or history are missing |
| When to use | Baseline/conservative scenario | When data is trustworthy, headroom is included, and seasonality is understood |

Typical performance-based options include **performance history duration**, **percentile utilization**, and a **comfort factor** or headroom multiplier, depending on assessment type. Do not treat UI defaults as company policy; for instance, the 95th percentile drops the top 5% of samples, which will fail to protect a rare yet critical batch if it fell outside—or even in the top tail of—the window.

Illustrative **reasoning example** (not Azure Migrate's internal algorithm): a source server has 8 vCPUs with measured p95 CPU utilization of 30%, roughly equivalent to 2.4 vCPUs via naive scaling. Applying a 1.3 comfort factor yields ~3.12 vCPUs, suggesting testing at least a 4-vCPU SKU. **Actual assessment outputs** depend on compatibility, disk, RAM, network, SKUs, rounding, and current algorithms; never size VMs from this calculation alone.

### 6.3 Reading Outputs: Readiness, Sizing, Cost, Confidence

| Output | Question to Answer | Action |
| --- | --- | --- |
| **Readiness / suitability** | Are OS/boot/disk/architecture and resources suitable for target? | Inspect reasons for *Ready / Ready with conditions / Not ready / Unknown* or equivalent statuses |
| **Recommended size** | Which VM SKU and disk types are proposed? | Cross-check quotas, features, region/zones, vCPU/RAM/disk/network limits, and growth |
| **Estimated monthly cost** | What is the estimated target cost under stated assumptions? | Separate calculated compute/storage from networking, backup, monitoring, egress, licenses, and shared services |
| **Confidence / data quality** | Are there enough performance samples? | Extend collection if confidence is low, servers rebooted erratically, or telemetry has gaps |
| **Warnings / blockers** | Are there EOL OSes, special disks, or incompatible configs? | Log remediation, owner, deadline, and alternative targets |

**An assessment is not proof that deployment will succeed immediately.** Azure quotas, regional capacity at provisioning time, corporate policies, permissions, ports/firewalls, DNS, extensions, licensing, and drift between assessment and cutover can all affect deployment.

### 6.4 Analyzing Costs Properly

Completely **hypothetical learning prices**, not an Azure price sheet:

| Workload Group | Machine Count | Est. Compute + Disk / Machine / Month | Monthly Total |
| --- | ---: | ---: | ---: |
| Web | 2 | 140 USD | 280 USD |
| API | 2 | 210 USD | 420 USD |
| SQL VM | 1 | 720 USD | 720 USD |
| Batch | 1 | 170 USD | 170 USD |
| **Total assessed machines** | **6** | | **1,590 USD** |

Assuming another **220 USD/month** for VPN/egress, backup, monitoring, and scoped shared services brings the preliminary budget to **1,810 USD/month**. Even then, this does not replace **Cost Management pricing/calculator**, licensing reviews, or a tariff-based budget.

Gaps between **estimated cost** and **actual cost** arise from workload changes, reservations/savings plans, licensing, traffic, storage transactions, DR replicas, monitoring ingestion, and operating expenses. Estimates must explicitly document scope boundaries.

## 7. Dependency Mapping: Identifying Which Machines Truly Depend on One Another

An assessment answers “which machines can move to Azure VMs?” **Dependency mapping** answers “if I move this machine first, which connections might break?” It forms the basis for migration waves, firewall rules, DNS, traffic cutover, and test sequencing.

### 7.1 What Does an Observed Connection Tell Us?

Example relationship:

~~~text
Source:      api-01, IP 10.10.20.11
Destination: sql-01, IP 10.10.30.20
Protocol:    TCP
Port:        1433
Observed:    during order-processing test period
Owner:       Orders team
Interpretation: possible SQL Server database connection
~~~

A TCP/IP record **does not by itself prove** a critical SQL transaction, and port 1433 could be configured differently or used by another app. Combine **hostname, process, listener/service, connection string, app documentation, and owner confirmation**.

| Data Element | How It Is Used | Common Pitfalls |
| --- | --- | --- |
| Source and destination | Identifies initiating and receiving hosts | Do not infer business data flow direction solely from TCP initiation |
| IP, port, protocol | Designs NSGs, firewalls, routing, and connectivity tests | NAT, load balancers, dynamic ports, or changing hostnames |
| Process / application name (if available) | Maps network flows to workloads | Not all sources have permission or capability to read processes |
| Observation window | Shows when connections occur | No observed flow ≠ no dependency |
| Frequency/volume (if available) | Prioritizes heavy paths | A very rare flow may still be a mandatory month-end close step |
| Owner confirmation | Separates real dependencies from background noise/telemetry | Owners may be unaware of legacy jobs; verify further |

### 7.2 Agentless vs. Agent-Based Dependency Analysis

For **supported VMware vSphere environments**, Azure Migrate can provide **agentless dependency analysis** via the appliance, subject to guest discovery prerequisites, credentials, and source tooling. This is a major advantage when working across many VMs without deploying separate agents to every machine.

For other sources or features, **dependency analysis mechanisms and requirements for agents, extensions, credentials, or additional tools may differ**. Do not blindly apply an old agent-based procedure to every Hyper-V or physical server; verify support status and prerequisites for your Azure Migrate version. Some workflows depend on how guest data is collected, including privileges required for process/socket visibility.

Verify **before enabling**:

1. Does the source support agentless dependency mapping?
2. Does the appliance already collect **guest application/software/process** and connection data, or only VM metadata?
3. Are credentials properly scoped, and are VMware Tools/guest support or agents required?
4. Are firewalls and connectivity from the appliance to sources approved?
5. Are any machines or subnets absent from collected data due to policies, powered-off VMs, login errors, or missing permissions?

**Never collect outside approved scope.** Mapping can expose hostnames, processes, internal IPs, and security systems; treat access to it as sensitive topology data.

### 7.3 Cover Full Business Cycles

Before locking waves, capture/reconcile flows during at least:

- Peak and off-peak application hours.
- End-of-day, weekend, month-end, or financial close batches.
- Backups, antivirus/EDR, monitoring, and management services.
- Token/certificate rotations, logins, LDAP/Kerberos, DNS.
- Failover/switchover tests if source infrastructure uses HA and testing is permitted.
- Outbound flows to SaaS, payment gateways, email, and partner APIs that VM inventory **cannot reveal**.

A dependency that only runs monthly **cannot be excluded** from the plan simply because the team only collected 7 days of data. Where cycles are missing, mark them **unknown** or schedule supplemental capture; never turn “not observed” into “does not exist.”

## 8. Building an Application Map from Observed Dependencies

Suppose discovery and owner review for Orders reveal:

| Source | Destination / Type | Example Port/Protocol | Purpose | Criticality |
| --- | --- | --- | --- | --- |
| `web-01/02` | `api-01/02` | HTTPS 443 | Ordering API calls | Critical |
| `api-01/02` | `sql-01` | TCP 1433 | Read and write orders | Critical |
| `batch-01` | `sql-01` | TCP 1433 | Data reconciliation | Critical at end of day |
| `batch-01` | `files-01` | SMB TCP 445 | Report delivery | Important |
| Web/API/Batch | DNS/AD | DNS 53, Kerberos 88 (varies) | Name resolution, authentication | Critical |
| API | External Payment API | HTTPS 443 | Payment processing | Critical, outside inventory |
| All servers | Monitoring/backup/management | Per agent/tool | Monitoring and recovery | Operational |

Ports listed are **common default examples**, not verified configurations for your environment; check actual listeners and connection strings. Active Directory typically involves many more protocols/ports than two illustrative ones and may require dynamic RPC, LDAP, or other mechanisms. Never build an NSG from this abbreviated port list and expect domain join to work.

~~~mermaid
flowchart TD
    USER["User / DNS"] --> WEB["web-01 / web-02"]
    WEB --> API["api-01 / api-02"]
    API --> SQL["sql-01"]
    API --> PAYMENT["Payment partner / Internet"]
    API --> ID["DNS/AD: on-prem or hybrid"]
    BATCH["batch-01"] --> SQL
    BATCH --> FS["files-01"]
    WEB --> ID
    BATCH --> ID
~~~

### 8.1 Tying Dependencies to Migration Requirements

Examples:

- **Web and API** usually need working routing, certificates, and network paths simultaneously. Web can sometimes move first if hybrid connectivity to the source API is stable and latency is acceptable.
- **API and SQL** sit on the transactional write path. Placing them on opposite sides of a WAN link can increase latency, cost, and error risk. Test performance, firewalls, TLS, and RTO/RPO before splitting across waves.
- **Batch and file share** may not need to move during peak API hours, but end-of-day/start-of-month jobs and SMB permissions post-change must be verified.
- **Identity/DNS** is usually a shared service that cannot simply be “moved one VM at a time.” You need a proper hybrid name resolution, domain join, or identity design.
- **Payment API** may require outbound IP allowlist updates, certificates, DNS, and sandbox endpoint tests. It will not fully appear in on-prem inventory alone.

**Dependency maps raise the right questions; owners and testing confirm the answers.** Treat an automated map as engineering input with bounded confidence, never absolute truth.

### 8.2 Creating an Application Group Definition

The example below is a **team decision record**, not an Azure Migrate import file:

~~~yaml
# Illustrative document, NOT an ARM/Azure Migrate schema.
application: Orders
business_owner: "Orders Product"
technical_owner: "Platform + DB"
environment: production
servers:
  - web-01
  - web-02
  - api-01
  - api-02
  - sql-01
  - batch-01
  - files-01
external_dependencies:
  - "DNS/Active Directory - on-premises shared service"
  - "Payment partner HTTPS endpoint"
critical_paths:
  - "User -> Web -> API -> SQL"
  - "API -> Payment provider"
  - "Batch -> SQL -> File share"
open_questions:
  - "What is the allowed latency between API and SQL?"
  - "How will application identities resolve DNS after cutover?"
  - "Does payment partner require new outbound IP allowlist?"
acceptance:
  - "All critical ports tested in target network"
  - "Business transaction and batch reconciliation pass"
  - "RTO/RPO and rollback plan approved"
~~~

## 9. Turning Assessments and Dependency Maps into Migration Waves

A **migration wave** is a scheduled transition batch with defined scope, owners, entry criteria, and a recovery plan. Never group machines solely by count or size: prioritize **business coupling** and shared data paths.

### 9.1 Example Wave Grouping

| Wave | Workload | Purpose | Control Gate |
| --- | --- | --- | --- |
| 0 – Foundation | Azure landing zone, VPN/ExpressRoute, DNS, RBAC, monitoring, backups | Establish target and connectivity before moving apps | Security/network sign-off |
| 1 – Pilot | Low-dependency stateless workload or test clone | Validate tooling, replication throughput, monitoring | Zero production impact, measurable results |
| 2 – Orders test | Web/API/SQL clone or test environment | Test latency, dependencies, database restore, workflows | End-to-end tests, suitable cost/sizing |
| 3 – Orders production | Orders application group per approved runbook | Live business cutover | Change window, consistent data, rollback |
| 4 – Cleanup / optimize | Decommission source post-validation, rightsizing, governance | Remove duplicate spend and stabilize ops | Owner sign-off, retention/backups, decommission |

If API and database cannot tolerate WAN latency, they may need to **move within the same change window** or use replication/synchronization for a consistent cutover. If SQL must stay on-premises, gather performance and network proof for the hybrid design before releasing web/API on Azure.

### 9.2 Setting GO/NO-GO Criteria

A migration wave should only proceed when:

1. Inventory/discovery covers all in-scope servers and critical dependencies are owner-confirmed.
2. Assessments reflect the **exact target region, sizing, and pricing assumptions**, with not-ready/unknown machines resolved.
3. Azure VNet, NSGs/firewalls, DNS, identity, IPs, routes, private connectivity, and quotas are verified.
4. Backups, replication/test migrations, and data plans are ready; RTO/RPO has been measured or rehearsed per scenario.
5. Pre-cutover baseline SLIs/latency/throughput, error budgets, and on-call staffing are in place.
6. The runbook defines a **last safe rollback** point, consistent data source, and split-brain write prevention.
7. Communications, approvers, PASS/FAIL metrics, and deferral criteria are agreed upon.

A *Ready* status in an assessment satisfies only **part** of these conditions—it does not replace production readiness.

## 10. End-to-End Practice Workflow Without Touching Production

The safest hands-on lab uses a **VMware/Hyper-V lab or test servers** with authorized access. You do not need a live production cutover to practice discovery, assessment, and mapping.

### Step 1: Scope and Security

- Pick 3–6 test VMs with owners and documented IPs, OS, and specs.
- Pick an authorized Azure subscription, project, and compliant metadata storage location.
- Ensure source access and appliance outbound connectivity match guidance for that source type.
- Assign someone responsible for issuing/revoking credentials and cleaning up post-lab.

### Step 2: Discovery

- Create the project, select the source, and deploy/register the appliance or supported mechanism.
- Register sources and credentials, then run discovery; **avoid installing unnecessary agents**.
- Reconcile discovered inventory against the lab list: hostname/ID, OS, vCPU, RAM, disks, IPs.
- Document missing fields and causes; check last update timestamps.

### Step 3: Performance-Based Assessment

- Collect sufficient history including simulated load, then pick the window and sizing mode.
- Create one **as-on-premises** assessment as a baseline and one **performance-based** assessment for the same group.
- Compare recommended sizes, disks, readiness, and estimated costs; document differing settings.
- Inspect data sources, missing metrics, and confidence levels; do not pick SKUs purely because they are cheap.

### Step 4: Dependency Mapping

- Enable **supported** dependency analysis for the lab source per prerequisites/credentials.
- Generate test traffic from web → API → database, run a scheduled job, and call an external endpoint.
- Inspect discovered connections (source, target, port/process if shown) and note flows that do not appear.
- Verify using app configs, logs, authorized network traces, and owner interviews.

### Step 5: Wave Decisions

- Group VMs sharing a critical path; describe components staying on-premises and hybrid links.
- Write GO/NO-GO gates, smoke tests, data checks, RTO/RPO, and rollback steps.
- Report unclosed risks transparently rather than declaring readiness from a dashboard alone.

**Deliverables:** reconciled server list, two assessments with documented assumptions, dependency map with confidence levels, application group table, and a migration wave plan—not just a screenshot showing “Ready.”

## 11. Troubleshooting Discovery, Assessment, and Mapping

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Appliance fails to register | Wrong key/project, outbound network, proxy/TLS, tenant/permissions | Verify project and connectivity, sync system time, never expose keys publicly |
| Some VMs missing | Wrong source config, insufficient credential permissions, VM off, filters, or discovery limits | Cross-check vCenter/host inventory and scope; inspect appliance health |
| OS/guest software missing | Missing guest credentials, agentless guest discovery disabled, or unsupported source | Check prerequisites; use approved supplemental sources |
| Low performance-based confidence | Too little history, no peak data, sampling gaps | Collect longer, check metric quality |
| Recommended VM sizes too small | Low percentile chosen, batches missing, missing peak RAM/disk | Review sizing settings, comfort factor, workload owners, SLOs |
| Readiness Not ready/Unknown | Incompatible OS/boot/disk/architecture or missing metadata | Inspect reasons and remediation; consider modernization/alternate target |
| Assessment cost differs from forecast | Missing shared services, licensing, rates/discounts, network, DR, monitoring | Separate estimated scope and build a full business case |
| Dependency map shows very few links | Missing guest telemetry, observation window too short, app had no traffic | Extend/adjust collection, trigger authorized test traffic |
| Map shows many unfamiliar connections | Monitoring, patching, backups, admin tools, NAT/LB, or other processes | Classify infrastructure noise and verify ports/processes/owners |
| Post-migration DB connection fails | NSG/firewall/route/DNS, TLS, identity, connection string, latency, or SQL endpoint | Test connectivity along source→target path, not just VM ping |

### 11.1 Warning Signs That Data Is Insufficient for Decisions

- Only a VM list exists, with no application owners or critical paths.
- Assessments omit target region, sizing criteria, and data collection period.
- Dependency analysis ran for only a few minutes despite month-end batches.
- SaaS, DNS, identity, backup, or shared-service traffic is completely invisible.
- Unclassified VMs are still included in a production wave.
- No baseline exists for latency, error rate, database consistency, or recovery plans.

When these signs appear, the true status is **more evidence needed**, never “assessment complete.”

## 12. Post-Migration Cost, Operations, and Security Controls

Azure Migrate primarily supports **migration decisions and execution**; long-term operations require a post-migration plan:

- **Cost Management and budgets:** compare actual billing against estimates, enforce tags, and evaluate reservations/savings plans once workloads stabilize.
- **Azure Monitor and Application Insights:** track availability, CPU/memory, disk I/O, networking, dependency failures, SLIs/SLOs, and alerts.
- **Azure Policy, RBAC, Defender for Cloud:** enforce configuration compliance, access control, and threat detection in the new Azure environment.
- **Backup/DR:** verify restore tests, retention, RTO/RPO, and post-cutover data ownership; old source copies do not substitute for a long-term backup strategy.
- **Rightsizing:** after several real load cycles, revisit VM sizing, autoscaling, and storage; source performance assumptions may behave differently on Azure.
- **Safe decommissioning:** only shut down/delete source machines after owner sign-off, completed data reconciliation, and clear archival/rollback rules.

A successful migration is not measured merely by “VMs moved”; it must meet initial functional, performance, security, reliability, and cost criteria.

## 13. Per-Application Output Checklist

| Item | Mandatory Question |
| --- | --- |
| Scope | Are all servers/apps/data/source sites in the group accounted for? |
| Owner | Have technical and business owners signed off? |
| Discovery | Are inventory coverage, OS, vCPU/RAM/disk, freshness, and missing fields documented? |
| Performance | Are peaks/batches, aggregation method, gaps, and confidence adequate? |
| Assessment | Are target region, sizing criteria, readiness, SKUs/disks, costs, and assumptions saved? |
| Dependencies | Are source→target flows, ports/processes, external services, identity/DNS/backups confirmed? |
| Application groups | Are any machines split across waves contrary to critical paths or data coupling? |
| Landing zone | Are subscription, RBAC, VNet/NSG/DNS, policies, backups, monitoring, and cost controls ready? |
| Migration plan | Are pilot/test migration, replication, cutover, rollback, RTO/RPO, and GO/NO-GO defined? |
| Evidence | Are owner review notes, test measurements, warnings, and open issues recorded? |
| Post-migration | Are SLIs/latency, billing, data integrity, owner sign-off, and controlled decommission covered? |

## 14. Practice Exercises and Self-Check

### Exercise 1: Evaluating Coverage and Confidence

A group has **200 VMs** in scope. Azure Migrate discovers **190 VMs**. Of those, **171 VMs** have sufficient performance history for a performance-based assessment. Questions:

1. What is the discovery coverage?
2. What is the performance coverage across the entire scope?
3. Can the team claim all production VMs have enough data for sizing?

**Solution:**

\[
\mathrm{DiscoveryCoverage}=\frac{190}{200}\times100\%=95\%.
\]

\[
\mathrm{PerformanceCoverage}=\frac{171}{200}\times100\%=85.5\%.
\]

The team **cannot** claim all VMs have sufficient data: **10 VMs remain undiscovered** and **19 discovered VMs lack performance history**. Identify owners, root causes of gaps, load cycles, and criticality; never mechanically extrapolate the average of 171 machines across all 200.

### Exercise 2: Combining Assessment with the Dependency Map

The assessment for `api-01` is *Ready*, with low estimated compute cost. The dependency map shows `api-01` calling on-premises `sql-01` over frequent TCP connections; latency between the target Azure region and current site is **25 ms RTT** (assumed lab measurement), and each API request runs 10 sequential SQL queries.

**Question:** Should you migrate the API before the database just because the assessment says Ready? What is the main risk?

**Suggested answer:** Insufficient grounds. If ten SQL round-trips truly execute sequentially across the WAN, added network latency alone could reach roughly **10 × 25 ms = 250 ms** per request (a very rough estimate ignoring pooling, query execution, TLS, and actual protocol behavior). Measure end-to-end latency, analyze call patterns, hybrid connectivity, database co-location/migration, and SLOs. VM suitability assessments **do not prove** application architecture latency will meet requirements.

### Exercise 3: Wave Planning for Orders

Machines `web-01`, `web-02`, `api-01`, `api-02`, `sql-01`, `batch-01`, and `files-01` have the relationships listed in Section 8's dependency table. Do the following:

1. Identify critical business paths that must have working network routes during the hybrid phase.
2. Select a lower-risk pilot than cutting over production directly.
3. Write three GO/NO-GO conditions and one rollback measure for the main migration wave.

**Suggested answer:** Web/API/SQL must be treated as a critical path; outbound payment and DNS/identity must be verified. The pilot should use a test clone or stateless workload with an owner and test data. GO requires tested connectivity/VNet/NSG/DNS, verified replication/backup and data consistency, plus passing smoke/SLI checks after test migration. On failure, have a plan to halt traffic/writes, restore routing to source, and reconcile data before resuming writes.

### Self-Check Questions

1. How does discovery differ from assessment and dependency mapping?
2. Why might the Azure Migrate appliance in VMware collect inventory without yet showing process and TCP dependencies?
3. When should you use as-on-premises assessment, and when can you trust performance-based assessment?
4. Why is a Ready VM assessment insufficient to proceed straight to cutover?
5. Why does “no observed traffic between two VMs” not prove they are independent?
6. What dependencies outside VM inventory must be checked for an app using DNS/AD, a payment API, and month-end jobs?
7. Why is estimated compute/storage cost not total TCO?
8. When migrating an API to Azure while keeping SQL on-premises, what must you verify regarding networking, latency, and security?
9. What evidence is required before shutting down source VMs after cutover?
10. When assessment confidence is low or a group of servers is missing from the map, should you proceed or gather more data?

**Key takeaway:** Azure Migrate turns guesswork into **decisions grounded in inventory, performance, and dependency relationships**. Use discovery to learn *what exists*, assessment to learn *where it can go under what assumptions*, and dependency mapping to learn *what must move together*. Finally, validate the landing zone, connectivity, data, and business journeys before executing migration waves and cutover.
