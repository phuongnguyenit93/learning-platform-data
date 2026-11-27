# Assessing Existing Systems and Selecting a Migration Strategy

Migrating a system to the cloud is not simply copying a server onto a new virtual machine. An application may depend on on-premises Active Directory, a database with specialized structures, a software license server, batch jobs, files on a NAS, and IP addresses integrated across many systems. Missing just one dependency can result in an application that boots on Azure but fails to work properly in practice.

In the **Hybrid Cloud and Migration to Azure** chapter of the **CLOUD_PROVIDERS_AZURE** track, we learn how to assess existing systems (*discovery/assessment*), quantify readiness, and select the right migration strategy for each workload. The topic is framed within the Microsoft Azure ecosystem: from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, data, monitoring, security, disaster recovery, and cost management.

The goal of this lesson is not to “move everything to Azure,” but to **gather sufficient evidence to decide what should be moved, how to move it, in what order, with what acceptance criteria, and with what rollback plan**.

> **Scope:** All workload names, figures, and configurations in this lesson are hypothetical examples. Actual Azure capabilities, support limits, pricing, and tools may vary depending on source type, OS version, database, licensing, region, and time. In a real project, always verify the support matrix and applicable terms for each workload.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Inventory servers, applications, databases, connections, data assets, identities, and dependencies of an existing system.
2. Collect baselines for performance, capacity, security, reliability, cost, and business requirements before migrating.
3. Use Azure Migrate and complementary discovery methods within their proper scope without treating automated results as the sole evidence.
4. Distinguish between **retain, retire, rehost, relocate, replatform, refactor/rearchitect, and repurchase**.
5. Select an Azure target and strategy based on technical factors, risk, cost, licensing, data constraints, and acceptable level of change.
6. Design the sequence of *migration waves* taking into account the dependency graph and landing zone preparation.
7. Establish test conditions, cutover, rollback, downtime windows, RTO/RPO, and migration completion criteria.
8. Author a **migration assessment** that can be jointly reviewed by architects, application owners, security teams, and operations.

## 2. Migration Is a System Decision, Not Just a Server Location Change

**Migration** is the process of moving an application, data, or system capability from an existing environment (on-premises, a colocated/hosted data center, or another cloud) to a target environment while maintaining required business outcomes. **Modernization** is improving architecture, platform, or development/operations practices; it can happen before, during, or after migration. **Disaster recovery** focuses on recovering from an outage and is not synonymous with moving the primary operating location.

Three different drivers can lead to three different decisions:

| Driver | Real Question | Impact on Strategy |
| --- | --- | --- |
| Data center lease expiring in 6 months | Can services be moved stably within the deadline? | Prioritize low-change rehost/replatform; defer deep modernization to a later phase |
| Monolith application hard to scale, deployments take hours | How much architectural change is actually needed? | Consider refactor/rearchitect, splitting by business capability |
| Legacy accounting software no longer supported | Should the legacy software be moved as-is? | Compare SaaS repurchase, replacement, or retire |
| Sensitive data restricted by processing location | Which data is permitted to move? | Retain/hybrid, encryption, region and regulatory controls |
| Want to reduce 3-year operating cost | How do actual TCO and risk change? | Need baseline metrics, pricing, licensing, operations, and migration cost |

A single project may apply **multiple strategies within the same application**: rehost a batch processing server, replatform the web frontend, refactor cache connections, retain an on-site industrial device, and retire an unused reporting service.

## 3. End-to-End Assessment Process

~~~mermaid
flowchart TD
    A["Define objectives and scope"] --> B["Inventory assets and owners"]
    B --> C["Discover dependencies and data flows"]
    C --> D["Baseline: performance, SLO, RTO/RPO, security, cost"]
    D --> E["Assess compatibility, readiness, and risk"]
    E --> F["Compare strategies and Azure targets"]
    F --> G["Select migration waves, landing zone, and cutover design"]
    G --> H["Pilot and validate"]
    H --> I{"Criteria met?"}
    I -->|"No"| E
    I -->|"Yes"| J["Approve migration plan"]
~~~

At every step, record **evidence**, not just opinions. An inventory file exported from a two-year-old CMDB is a starting point, but it must be cross-checked against current telemetry, DNS, scheduled jobs, live connections, users, and actual data.

### 3.1. Minimum Roles

| Role | Primary Responsibilities |
| --- | --- |
| **Business owner** | Business objectives, downtime schedule, mandatory functionality, and risk tolerance |
| **Application owner / developer** | Logical architecture, runtime, libraries, integrations, deployment process, business data |
| **Infrastructure/Network** | Servers, storage, DNS, IP, firewall, VPN/ExpressRoute, network performance |
| **Database/Data owner** | Database inventory, integrity, schema, backup, replication, cutover |
| **Security/Compliance** | Data classification, residency requirements, identity, encryption, audit, and permissions |
| **Cloud platform team** | Azure landing zone, subscription, policy, RBAC, capacity/quota, monitoring |
| **Finance/FinOps** | TCO, licensing, commitments, forecast, and budget |
| **Migration lead/SRE** | Waves, runbook, testing, go/no-go, rollback, hypercare |

The application owner **must be identified** before deciding to decommission an existing system. If no owner exists, mark the status as *unowned/pending validation* and investigate; do not treat the absence of an owner as proof that a resource can be deleted.

## 4. Inventorying the Existing System

### 4.1. Do Not Just List VMs

The goal is to catalog **workloads and every component affecting their correctness**, including:

- Physical servers, VMs, hypervisors, OS, CPU/RAM, disks, filesystems, middleware, and support lifecycle dates.
- Applications, versions, frameworks, runtimes, processes, containers, batch schedules, and manual tasks.
- Database engine/version/edition, size, transaction logs, jobs, replication, linked servers, extensions, and client applications.
- File shares, object storage, snapshots, backup repositories, long-term archival data, and search systems.
- DNS, static IPs, load balancers, firewalls, proxies, routing, certificates, LDAP/Kerberos/AD, NTP.
- Operational tooling: CI/CD, schedulers, monitoring, logging, backup/restore, patching, license management.
- Integrations with SaaS, partners, factory equipment, payment systems, SMTP, APIs, and endpoints restricted by IP allowlist.
- Data access rules, service accounts, secrets, encryption keys, HSMs, and responsible parties.
- Security, regulatory, data ownership, retention, disposal, and audit constraints.

**The primary unit of analysis is the business workload**, not the hostname. One application may span multiple machines and databases; one machine may also host multiple applications. A many-to-many mapping table is therefore required.

### 4.2. Inventory Template

| Field | Example Value | Why It Is Needed |
| --- | --- | --- |
| Workload ID | APP-ORD-01 | Stable identifier key |
| Business name | Orders Portal | Communication with business owner |
| Owner | Commerce application team | Approver for functionality and cutover |
| Environment | Production | Separate production and test scope |
| Components | web-01, api-01/02, sql-01, file-01 | Define the migration unit |
| Runtime/OS | .NET 6, Windows Server, SQL Server (example) | Check compatibility and support |
| Support status | Must verify actual lifecycle | Avoid moving EOL workloads to target and ignoring security |
| CPU/RAM/disk | 8 vCPU, 32 GiB, 1.2 TiB | Initial sizing |
| Data classification | Confidential | Design private connectivity, permissions, data protection |
| RPO/RTO | 15 minutes / 2 hours | Choose backup, replication, and migration solutions |
| Traffic and latency | 120 RPS peak, p95 350 ms | Benchmark and capacity sizing |
| Allowed downtime | 30 minutes on Sunday | Choose online/offline cutover |
| Dependencies | AD, payment gateway, NAS | Decide waves and hybrid design |
| License status | Contract review pending | Check BYOL, Software Assurance/Hybrid Benefit if eligible |
| Provisional proposal | Replatform API; DB needs assessment | Not yet an approved decision |

### 4.3. Illustrative CSV Data

~~~csv
workload_id,component,owner,environment,source_platform,data_class,criticality,status
APP-ORD-01,orders-web,commerce,prod,VMware,internal,high,discovered
APP-ORD-01,orders-api,commerce,prod,VMware,confidential,high,discovered
APP-ORD-01,orders-db,commerce,prod,SQL-Server,confidential,critical,assessment-needed
APP-ORD-01,order-files,commerce,prod,NAS,confidential,high,assessment-needed
APP-REP-02,legacy-reporting,finance,prod,physical-server,internal,low,ownership-review
~~~

The CSV above is **learning data**, not actual Azure Migrate output. In real projects, avoid storing passwords, connection strings, or personal data in CSV files; use identifiers and references to appropriate secret management systems.

### 4.4. Distinguishing Data Confidence Levels

| Level | Evidence Source | Action |
| --- | --- | --- |
| **Verified** | Recent telemetry, owner confirmation, inspected configuration | Can be used as assessment input |
| **Observed** | Agent/logs/flows show a resource or connection exists | Needs owner confirmation of its purpose |
| **Declared** | CMDB, legacy docs, or interviews | Cross-check against reality |
| **Unknown** | Missing owner, metrics, or critical dependencies | Flag as blocker; do not finalize strategy |

Do not ignore low-traffic systems. A month-end batch or quarterly job can easily be absent during a one-week observation window.

## 5. Dependency Discovery and Data Flow Mapping

**Dependency mapping** identifies which services an application relies on to function, along with protocol, address, access direction, identity, and latency requirements. A graph helps determine which components must move together and which can remain behind temporarily.

~~~mermaid
flowchart LR
    U["Internal users"] --> DNS["On-prem DNS / proxy"]
    DNS --> W["Orders web"]
    W --> API["Orders API"]
    API --> DB["SQL Server"]
    API --> FILE["NAS / file share"]
    API --> PAY["Partner Payment API"]
    API --> ID["Internal Active Directory / DNS"]
    DB --> BACKUP["Backup repository"]
    API -. "Logs / metrics" .-> MON["On-prem monitoring"]
~~~

A diagram is only useful when every edge is annotated:

| From → To | Protocol/port | Direction | Functional Dependency | Latency/throughput | Owner | Confidence Level |
| --- | --- | --- | --- | --- | --- | --- |
| API → SQL | TCP/1433 (example) | Outbound from API | Transactional read/write | p95, IOPS, TPS | DBA | Verified |
| API → NAS | SMB/445 (example) | Outbound from API | Document attachments | MB/s, file count | Storage | Observed |
| API → AD | LDAP/Kerberos/DNS as configured | Bidirectional per service | Account authentication | Timeout, domain reachability | Identity | Declared |
| API → Payment | HTTPS/443 | Outbound from API | Payment creation | Rate limit, retry, idempotency | Integration | Verified |
| SQL → backup | Product-specific | Outbound from SQL | Failure recovery | RPO/retention | DBA | Verified |

**Do not guess ports from service names.** The numbers above are illustrative; real systems may use custom ports, TLS tunnels, proxies, or private endpoints.

### 5.1. Dependency Collection Methods

1. **Owner interviews** to obtain the intended architecture diagram.
2. **Network flow logs/firewall/proxy/DNS/host telemetry** to observe actual connections across different time windows.
3. **Application tracing** or logs with correlation IDs to see business-level calls.
4. **Database/job inventory** to identify scheduled tasks, linked servers, ETL, and replication.
5. **Runtime configuration inspection**: connection endpoints, queue names, certificates, service accounts; do not copy secrets into reports.
6. **Reconciliation with owners**, because an observed connection is not always a required dependency and a rarely used dependency may not appear in recent data.

**The measurement window must cover business cycles**: peak hours, weekends, month-end, periodic batches, and maintenance events. If a full cycle cannot yet be observed, document the gap and use targeted tests or supplemental verification.

### 5.2. Estimating Latency Sensitivity During Partial Migration

Moving an application to Azure while leaving SQL in the data center can introduce many round-trips across VPN/ExpressRoute. Hypothetical example:

- An API executes **20 sequential queries** against SQL.
- Round-trip latency increases by **12 ms** compared to before.
- Added overhead can reach roughly **20 × 12 = 240 ms** per request, unless masked by parallelization or protocol optimization.

This is a conceptual estimate, not an exact p95 prediction. Always benchmark against actual dependencies. If transactions involve many round-trips, moving the API and database in the same wave may be safer for latency than maintaining a prolonged hybrid link.

## 6. Collecting Pre-Migration Baselines

Without a baseline, it is difficult to prove whether the system performs better or worse after migration. Metrics should cover at least **performance, capacity, reliability, data state, and cost**.

### 6.1. Performance and Capacity

| Category | Required Metrics | How It Is Used |
| --- | --- | --- |
| **Workload traffic** | RPS, transactions/s, sessions, batch jobs/day | Capacity forecasting |
| **Latency** | p50, p95, p99 of APIs and dependencies | Setting post-migration SLOs |
| **Errors** | Timeouts, 5xx, business errors, retry counts | Quality comparison |
| **Compute** | Average/peak CPU, RAM working set, GC, threads | Compute sizing |
| **Disk/storage** | Capacity, growth, IOPS, throughput, latency | Selecting suitable managed disk/Storage |
| **Database** | TPS/QPS, CPU, memory, connections, log growth, query latency | Choosing target service/tier and migration method |
| **Network** | Inbound/outbound bandwidth, connection count, round-trip latency | Sizing hybrid connectivity and egress |
| **Async workload** | Queue depth, oldest-message age, completion rate | Worker sizing and backlog evaluation |
| **Availability** | SLI/SLO, downtime, past incidents/restores | Comparing targets and designing DR |

Collect both **normal and peak** figures. Taking a 20% average CPU from a single static snapshot to size target VMs can cause capacity exhaustion during month-end batch runs. Account for seasonality, short bursts, and cache warmup state.

### 6.2. Defining Post-Migration Acceptance Criteria

Hypothetical example for Orders API:

~~~yaml
workload: APP-ORD-01
measurementScope: production-business-transactions
baseline:
  peakRps: 120
  p95LatencyMs: 350
  businessSuccessPercent: 99.95
  databaseSizeTiB: 1.2
  dataGrowthGiBPerMonth: 50
acceptance:
  peakRpsAtLeast: 120
  p95LatencyMsAtMost: 400
  businessSuccessPercentAtLeast: 99.95
  criticalFeaturesPass: true
  maxCutoverDowntimeMinutes: 30
  dataLossToleranceMinutes: 0
~~~

This is an **acceptance contract template defined by this lesson**, not an Azure Migrate configuration format. For legally binding or payment-recording systems, “zero loss of confirmed transactions” must be engineered at the transaction and reconciliation level; it cannot be guaranteed solely by picking a replication tool.

### 6.3. RTO, RPO, and Downtime in Migration

- **RTO (Recovery Time Objective):** target time to restore service after a severe outage.
- **RPO (Recovery Point Objective):** acceptable limit of data loss measured in time.
- **Migration downtime window:** permitted outage duration during a planned cutover activity.
- **Cutover duration:** actual elapsed time from freezing changes/updating routes until the new system is verified.

**RTO/RPO is not equal to the downtime window.** A system with a 2-hour RTO during a disaster may still only be allowed a 10-minute outage during a planned migration. In particular, a successful backup **does not prove** that restore meets RTO/RPO; an actual restore test is required.

## 7. Data Assessment: Often the Decisive Factor for Strategy

### 7.1. Database Inventory

Beyond engine, version, and size, inspect:

- Schemas, stored procedures, triggers, functions, cross-database queries, linked servers.
- Extensions/plugins, CLR, full-text search, collation, job schedulers, and engine-specific features.
- Transactions per second, write latency, log generation rate, indexes, partitioning, and backup/restore duration.
- Replication/HA, secondary nodes, transaction consistency, and maintenance windows.
- Users/logins, permissions, service accounts, keys/certificates, and secret management practices.
- Large BLOB/file data, ETL pipelines, and downstream systems reading data.
- Checksums, row counts, financial balance reconciliation, or business invariants.

A database feature supported on a VM **does not automatically mean it is identically supported** on Azure SQL Database or Azure SQL Managed Instance. Compatibility evaluation must be grounded in specific features, engine versions, and the target service.

### 7.2. Data Classification and Data Residency

Classify public, internal, confidential, personal, and regulated/compliance-bound data. Determine:

1. Which data is allowed in the cloud, which regions may be used, and whether backup/replication regions are permitted.
2. Who is permitted to read/write, data administration roles, and which party manages encryption keys.
3. Retention, deletion, recovery periods, and audit requirements.
4. Whether partner connections or local systems are permitted to traverse the public Internet.
5. Which data flows must traverse private networks or require additional encryption.

**Selecting an Azure region does not by itself guarantee compliance with every data residency requirement.** You must examine the specific service, where backups/logs/metadata are stored, replication mechanisms, legal policies, and organizational terms.

### 7.3. Data Transfer Time

A rough estimation formula:

\[
T_{\text{transfer}} \approx \frac{\text{Data to transfer (bits)}}{\text{Effective throughput (bits/second)}}
\]

Example: transferring **4 TiB** over a connection with a nominal speed of **200 Mbit/s**:

\[
T_{\text{ideal}} \approx
\frac{4\times 1024^4\times 8}{200\times10^6}
\approx 48.9\ \text{hours}
\]

If only **60%** of nominal bandwidth is achieved due to overhead or traffic contention, the estimated time increases to **about 81.5 hours**. This calculation excludes data churn during copying, checksums, retries, compression, tool overhead, and source read / target write limits.

For large datasets, consider offline transfer methods or suitable Azure data transfer services when eligible; verify current availability, support scope, security, and logistics lead time. Choosing between **online replication, staged copy, or offline** must align with actual RPO and downtime constraints.

## 8. Azure Tools for Discovery and Assessment

### 8.1. Azure Migrate

**Azure Migrate** is a centralized platform for discovering, assessing, and planning migrations of supported workloads to Azure. In supported scenarios, an appliance/collector or appropriate discovery mechanism can be deployed to gather server metadata and evaluate readiness and sizing. Actual assessment/migration capabilities vary across **VMware, Hyper-V, physical servers, other clouds, operating systems, databases, and tool versions**.

Conceptual workflow:

~~~text
Create Azure Migrate project (in an appropriate subscription/region)
    -> Define source environment and permission scope
    -> Discover assets via supported mechanism
    -> Collect performance data over a sufficient observation window
    -> Group machines by workload/dependency
    -> Run readiness, sizing, and estimated cost assessment
    -> Manually review findings and unsupported dependencies
    -> Build migration waves and pilot
~~~

**An “Azure ready” result does not mean the application is business-ready.** A machine may boot on an Azure VM yet still fail to reach a license server, local device, or database, or violate data constraints. Automated results must therefore be combined with technical and owner reviews.

### 8.2. Database and Application Assessment

For databases, use compatibility assessment and migration capabilities from the Azure ecosystem matching the engine/target—such as workflows for Azure SQL or **Azure Database Migration Service** where the scenario is supported. Tool names, online/offline modes, and features can change, so verify engine/version, source/target, and replication method support before committing.

For web applications, assess runtime/OS/framework, authentication, filesystem usage, session state, native dependencies, and target PaaS capabilities before proposing App Service, Container Apps, AKS, or Functions.

### 8.3. Azure Arc Is Not Azure Migrate

**Azure Arc** helps manage and govern certain resources running outside Azure using supported integration and policy capabilities. Arc can be valuable for operating a **hybrid** model and governing servers/Kubernetes elsewhere, but **onboarding a server into Arc does not migrate that server into Azure**.

Comparison:

| Tool / Capability Group | Good For | Does Not Automatically Do |
| --- | --- | --- |
| **Azure Migrate** | Discovery, assessment, and migration orchestration within supported scope | Does not guarantee every app/database is business-compatible |
| **Azure Database Migration tooling** | Migrating data/databases across supported sources/targets | Does not replace application testing or schema/permission review |
| **Azure Arc** | Governing hybrid environments within supported capabilities | Does not rehost workloads into Azure |
| **Azure Monitor / Application Insights** | Baselines, dependency tracing, and post-migration comparison | Does not decide the R-strategy |
| **Cost Management / Pricing Calculator** | Estimating, tracking, and managing costs under stated assumptions | Does not replace TCO modeling or contractual pricing |

Before collecting telemetry, verify access permissions, data sources, networking, tooling costs, and security of the appliance/agent.

## 9. The Seven Strategies Commonly Called the “7 Rs”

Different publications group and name “R strategies” slightly differently. The model below is a **decision framework**, not a fixed Azure feature list.

| Strategy | Meaning | Examples and When to Consider | Trade-offs |
| --- | --- | --- | --- |
| **Retain** | Keep the workload in its current environment for a period | Factory control equipment, data not yet permitted to move | Requires hybrid connectivity and governance; retains on-prem costs/issues |
| **Retire** | Decommission a system no longer delivering value | Reporting service confirmed to have zero active users | Must verify archival data, legal hold, and remaining integrations |
| **Rehost** (*lift and shift*) | Move systems with minimal application changes | Data center VM moved to Azure VM | Faster, but carries over legacy tech and limits PaaS optimization |
| **Relocate** | Move an environment/stack with platform continuity in a supported way | Certain scenarios moving VMware workloads to **Azure VMware Solution** | Depends on stack, licensing, capacity, and service cost |
| **Replatform** (*lift, tinker and shift*) | Adjust just enough to use a more managed platform | Web app to App Service; compatible database to managed service | Requires compatibility, connectivity, and operational testing |
| **Refactor / Rearchitect** | Change architecture/code structure to meet new goals | Splitting a monolith, externalizing state, event-driven design | Higher risk/duration; demands substantial testing and engineering |
| **Repurchase / Replace** | Replace with another product or SaaS | Replacing a legacy work management tool with SaaS | Data migration, process change, licensing, integrations, and lock-in |

**Common point of confusion:** moving on-prem SQL Server to **SQL Server on Azure VM** is closer to database rehost; moving to **Azure SQL Managed Instance** or **Azure SQL Database** is typically replatform if compatible, though required changes must still be evaluated. Switching to a new data model or decomposing transactional boundaries may constitute refactor. Real migrations often combine multiple Rs.

### 9.1. Ordered Screening Questions

1. Does the workload still have users, retention obligations, or business value? If not, evaluate **retire**.
2. Are there constraints preventing immediate migration—legal, hardware, dependencies, or licensing? Consider **retain** under a hybrid plan with a scheduled re-evaluation date.
3. Is there a better-fitting SaaS/replacement product with feasible data migration and contract terms? Consider **repurchase**.
4. Do you need to exit the data center quickly with a stable application and compatible VM target? Consider **rehost/relocate**.
5. Can operational overhead be reduced with managed services without major changes? Consider **replatform**.
6. Is the primary goal agility, scale, reliability, or new business structure that the legacy architecture cannot support? Consider **refactor/rearchitect**.

Never choose an R purely by technology buzzwords. Weigh timeline, data, security, testability, team skills, budget, and operational correctness.

## 10. Evaluation Framework for Selecting a Strategy

### 10.1. Criteria and Evidence

| Criterion | Question | Evidence |
| --- | --- | --- |
| **Business value** | Does migrating reduce risk or advance business goals? | Deadlines, revenue, users, contractual obligations |
| **Technical compatibility** | Are OS/runtime/database/drivers supported on the target? | Compatibility assessment and PoC |
| **Dependency complexity** | How many components must move in lockstep? | Confirmed dependency graph |
| **Data risk** | What are volume, write rate, consistency, and residency? | Data inventory, RPO/RTO, replication tests |
| **Security/compliance** | Do the landing zone and processes satisfy requirements? | Control mapping, risk approval |
| **Operating model** | Can the team run AKS/PaaS, or is a managed service needed? | Skill matrix, support model |
| **Cost/TCO** | CAPEX/OPEX, licensing, egress, monitoring, dual run? | Baseline bills, pricing/quotes, assumptions |
| **Timeline/reversibility** | Can it meet the deadline and be rolled back? | Plan, cutover rehearsal, risk register |

An option that looks cost-optimal but **violates data residency or RTO** must be disqualified before scoring. Distinguish **hard constraints** (mandatory) from **trade-offs** (negotiable).

### 10.2. Component-Level Strategy Selection Matrix

| Workload / Component | Rehost | Replatform | Refactor | Retain/Repurchase | What Must Be Proven |
| --- | --- | --- | --- | --- | --- |
| Stateless web API, supported runtime | Possible | Strong candidate for App Service/Container Apps | When independent scaling is needed | Rarely retained permanently | Deployment, sessions, auth, OS dependencies |
| Legacy Windows app using COM/native DLLs | Possible if VM supports it | May be incompatible with PaaS | Requires rewriting dependent modules | May retain temporarily | Binary/driver and license testing |
| SQL Server with linked servers and SQL Agent jobs | Viable on VM | Managed Instance or alternative after assessment | Can split capabilities | Retain until requirements are met | Compatibility, HA, cutover, logins |
| Large file share, SMB with many small ops | Compatible VM/file service | Azure Files or suitable solution | Move to object storage | Retain temporarily if latency fails | ACLs, locks, throughput, latency |
| Independent scheduled batch | VM | Managed batch/containers/Functions when suitable | Event-driven if beneficial | Retire if no longer used | Scheduling, idempotency, deadlines |
| Industrial system with local hardware | VM near equipment | Depends on protocol/latency | Edge + cloud analytics | Retain/hybrid often warranted | Offline operation, latency, safety |
| Commercial off-the-shelf CRM | VM if licensed | PaaS difficult for closed-source apps | Poor fit without source code | Repurchase SaaS | Data export, contracts, integrations |

**These are illustrative guidelines, not final decisions.** Target services and supported versions must be verified via PoC and current documentation before finalizing.

## 11. Explainable Scoring for Workload Prioritization

Scoring can help select pilot and migration waves. Scores only support decision-making; they **do not override hard constraints** or dependency order.

A hypothetical model scoring each factor from 1–5, where higher means **better suited to move earlier**:

- **Business opportunity** (30%): benefit of moving early; not synonymous with damage if it fails.
- **Technical ease** (25%): ability to move with minimal changes and easy testing.
- **Dependency readiness** (25%): dependencies are understood and can be connected or moved.
- **Low-risk/reversibility** (20%): level of control and ease of rollback.

\[
Score=0.30B+0.25E+0.25D+0.20R
\]

| Workload | B | E | D | R | Score | Assessment |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Low-criticality internal portal | 2 | 5 | 5 | 5 | **4.10** | Suitable pilot, low blast radius |
| Independent catalog API | 4 | 4 | 4 | 4 | **4.00** | Early wave after pilot |
| Core payment system | 5 | 2 | 1 | 2 | **2.65** | Critical yet hard; needs dependency work and rehearsals |

Portal example: \(0.30×2+0.25×5+0.25×5+0.20×5=4.10\).

**A high score does not mean automatic migration.** If a portal depends on an unready identity service or has unmet data storage requirements, the order must change. These weights are hypothetical to illustrate the method; organizations may adjust them based on risk appetite.

## 12. Mapping Workloads to Azure Capabilities

Only after selecting the R strategy should specific services be chosen. Reference mappings:

| Assessed Need | Azure Target to Evaluate | Conditions to Verify |
| --- | --- | --- |
| Rehost Linux/Windows VM | **Azure Virtual Machines**, managed disks, availability design | OS support, image, VM sizing, drivers, licensing |
| Web/API app with supported runtime | **Azure App Service** | Runtime version, filesystem, auth, networking, session state |
| Container workload with complex orchestration | **Azure Kubernetes Service (AKS)** | Operational skills, networking, image registry, security, cluster/node cost |
| Container app suited for managed operations | **Azure Container Apps** | Scaling, networking, persistence, integrations |
| Functions/event-driven | **Azure Functions** | Triggers, timeouts, plan, concurrency, cold start, state |
| SQL Server needing high compatibility | **SQL Server on Azure VM**, evaluate **Azure SQL Managed Instance** | Engine features, SQL Agent, linked servers, networking, licensing |
| Need PaaS database within supported capabilities | **Azure SQL Database** or corresponding data service | Schema, SQL compatibility, HA, DR, performance |
| Object/file data | **Azure Blob Storage, Azure Files** | Protocol, ACLs, latency, throughput, lifecycle/retention |
| Queues/events | **Azure Service Bus, Event Hubs** by message pattern | Delivery semantics, ordering, retries, throughput |
| Identity for Azure workloads | **Microsoft Entra ID**, managed identities | Federation, legacy AD/Kerberos needs, authorization |
| Hybrid connectivity | **Site-to-Site VPN, ExpressRoute** as needed | Bandwidth, redundancy, routing, SLA, security, cost |
| Hybrid server governance | **Azure Arc** within supported scope | Governance, agents, identity, policy, logs |

Do not put a component using AD/Kerberos onto Entra ID and assume domain controllers can be retired immediately. **Entra ID is not a drop-in replacement for every Active Directory Domain Services capability.** For legacy apps, analyze domain join, LDAP, Kerberos, Group Policy, and an appropriate identity design.

### 12.1. Region Selection and HA/DR

Regions must satisfy data constraints, latency, SKU/service availability, networking, cost, and availability of dependent services. Distinguish:

- **Availability Zones** improve fault tolerance within a region where supported by the service and region.
- **Cross-region replication/DR** addresses broader outages but carries its own cost, latency, and data residency constraints.
- **Backup/restore** supports data recovery; restores must be tested and recovery points verified.

Never pick a region solely for proximity to users if it lacks required services or violates organizational data constraints.

## 13. Migration Cost and TCO: Apples-to-Apples Comparison

Monthly Azure fees **are not the entire cost of migration**. A TCO evaluation should include:

| Category | Cost Sources |
| --- | --- |
| **Current on-prem** | Hardware, depreciation/lease, power/cooling, racks, network, licenses, backup, DR, operations staff |
| **Azure target** | Compute/VM/PaaS, storage, snapshots/backups, databases, monitoring, network egress, support, licenses, reservations/savings plans if eligible |
| **One-time migration** | Discovery, testing, data transfer, code changes, training, cutover rehearsals, external specialists |
| **Dual run** | Two environments running in parallel, replication, VPN/ExpressRoute, logs, and temporary resources |
| **Risk/disruption** | Downtime, degraded performance, after-hours support, rollback, business risk |
| **Post-migration operations** | CI/CD, security, compliance, monitoring, incident response, operational skills |

### 13.1. Simple 36-Month TCO Example

**Hypothetical numbers** to illustrate the comparison method:

| Line Item | Keep On-Prem 36 Months | Move to Azure 36 Months |
| --- | ---: | ---: |
| Infrastructure/compute and related operations | 36,000 USD | 48,600 USD (1,350 USD/month × 36) |
| On-site hosting/power/network | 18,000 USD | Included in Azure assumption above |
| Other operations/backup/licenses | 12,000 USD | Included in 1,350 USD/month assumption |
| One-time migration project | 0 USD | 12,000 USD |
| Dual run and testing | 0 USD | 3,000 USD |
| **Hypothetical Total** | **66,000 USD** | **63,600 USD** |

The difference in this example is **2,400 USD** over three years (about **3.64%** of 66,000 USD). That margin can vanish completely if network egress, licensing, data growth, or operational assumptions shift. Therefore, **do not conclude Azure is guaranteed to be cheaper from an illustrative table**.

In real calculations, eliminate double counting, properly treat sunk costs vs. valid depreciation, evaluate actual hardware savings post-migration, and account for continuing costs. Public list prices from the Pricing Calculator may differ from actual contract rates. Reservations/savings plans or Azure Hybrid Benefit should only be factored in when eligibility and workload patterns fit.

### 13.2. Sensitivity Analysis

Vary three key variables to see if the decision holds up:

- Peak compute increases by 30% post-migration.
- Cross-region data transfer is 2× higher than expected.
- Dual run extends by 2 additional months due to a failed cutover.

An option with a low TCO in the best case that spikes sharply in a downside scenario may be riskier than a higher-estimate but stable option. Finance and business owners need the **range**, not just a single total.

## 14. Preparing the Azure Landing Zone Before Migration

A **landing zone** is the governance and operational foundation ensuring applications moved to Azure do not become fragmented, unmanaged resources.

### 14.1. Foundation Architecture Checklist

| Domain | Preparation Items |
| --- | --- |
| **Subscription/governance** | Environment boundaries, naming, tags, management groups/Policy if applicable |
| **Identity** | Microsoft Entra ID, permission groups, managed identities, service principals/federation, privileged access |
| **Network** | VNet/subnets, IP planning, routing, DNS, firewall, proxy, private endpoints, ingress/egress |
| **Hybrid connectivity** | VPN/ExpressRoute, redundancy, bandwidth, route overlap, bidirectional DNS resolution |
| **Security** | Policy, encryption, Key Vault, logging, segmentation, vulnerability/patch management |
| **Observability** | Azure Monitor, Application Insights, Log Analytics, alerts, SLO dashboards |
| **Operations** | Backup/restore, DR tests, incident runbooks, change management, IaC, CI/CD |
| **Cost** | Budgets, tags/cost centers, quotas, sizing reviews, regions, data transfer, shutdown policies |
| **Resilience** | Zone/region design, service health, failover capacity, restore tests |

Not every pilot needs full production complexity upfront, but a **production-bound pilot** still requires baseline security, cost, and data controls. Clearly separate minimum entry prerequisites from items deferred to later waves.

### 14.2. Hybrid Topology Example

~~~mermaid
flowchart LR
    subgraph DC["On-premises data center"]
      Legacy["Legacy app + database"]
      AD["AD/DNS"]
    end
    subgraph AZ["Azure landing zone"]
      HUB["Hub VNet / Firewall / DNS"]
      SPOKE["Workload Spoke VNet"]
      APP["App Service/VM/AKS"]
      DATA["Managed database / storage"]
      MON["Monitor + Key Vault"]
      HUB --- SPOKE
      SPOKE --> APP
      APP --> DATA
      APP --> MON
    end
    DC <-->|"VPN or ExpressRoute"| HUB
    APP -. "Temporary identity/dependency" .-> AD
    APP -. "Temporary source data access as needed" .-> Legacy
~~~

The diagram illustrates one hub-spoke pattern; actual use of private endpoints, DNS forwarders, routing, or inbound/outbound paths depends on design and services. Avoid CIDR overlap between on-prem and Azure. Crucially, verify **DNS resolution, MTU, outbound paths, port allowlists, and connection directionality**, not just successful pings.

## 15. Planning Migration Waves by Dependency

A *wave* is a group of workloads/components prepared, tested, and cut over within a governed window. Groupings should follow the **dependency graph** and **business windows**, rather than splitting servers into equal counts.

### 15.1. Reference Sequence

| Wave | Contents | Entry Criteria | Exit Criteria |
| --- | --- | --- | --- |
| **0 – Foundation** | Landing zone, identity, network, monitoring, backup, quota | Architecture and security approvals | Connectivity/access tested, policies, alerts, backups working |
| **1 – Pilot** | Low-criticality internal portal | Owner, inventory, dependencies, rollback ready | Stable operation, runbooks, real telemetry |
| **2 – Supporting services** | Low-dependency auxiliary or shared services | Pilot passed, shared services ready | Integration tests, latency, SLOs met |
| **3 – Business apps** | Medium-tier catalog/APIs | Database/network ready, cutover rehearsal | Function, data, performance, security approved |
| **4 – Critical flows** | Orders/payment within approved scope | Dependency chain resolved, DR/rollback rehearsed | Business sign-off, reconciliation, SLO and audit met |
| **5 – Optimization/decommission** | Rightsizing, tech debt cleanup, source teardown | Overlap period complete, no remaining dependencies | Data retained/deleted per policy, legacy costs ended |

This is an example structure, **not a mandatory order for every enterprise**. If a dependency serves applications remaining on-prem, maintain hybrid connectivity during transition or adjust waves to avoid disrupting legacy apps.

### 15.2. Do Not Blindly Move Web Before Database

If an API and database communicate chatty workloads tightly, moving the API first can inflate latency and severely degrade performance. In such cases:

- Move low-dependency components first to practice the process.
- For tightly coupled systems, treat API + DB as a single **migration unit** or use a well-engineered replication/connection plan.
- Split data/traffic by business capability where architecture supports it; do not split mechanically by machine.
- Verify that upstream and downstream consumers are not forgotten during cutover.

**The dependency graph must capture order and ownership**, not just look tidy. A missing network path or cross-environment dependency can cause an entire wave to fail.

## 16. Choosing Data Migration Approaches: Offline, Online, and Staged

### 16.1. Three Common Patterns

| Approach | Conceptual Mechanism | Best Suited When | Risks |
| --- | --- | --- | --- |
| **Offline migration** | Stop writes, copy data, verify, switch app | Downtime window is long enough; data size/speed fits | Extended outage if copy/restore runs slow |
| **Online migration/replication** | Initial sync, continuous change replication, cut over at low lag | Short downtime; tool and source/target support it | Lag, consistency, complex cutover and rollback |
| **Staged/hybrid migration** | Move data/capabilities in slices while keeping connectivity between sites | Application can be partitioned by domain or workload | Cross-site latency, distributed transactions, data ownership |

**Online does not mean zero downtime.** A point in time is still required to transfer write ownership, validate data, and reroute clients. Online/offline capability depends on the specific engine, version, and tooling.

### 16.2. Safe Data Cutover

A conceptual sequence:

1. Back up and **test restore** prior to a critical cutover.
2. Complete initial full sync and replay changes (if supported by the method).
3. Lower DNS TTL ahead of cutover when effective and with enough lead time for existing DNS caches to expire.
4. Put the source system into **read-only or paused-write mode** per the business agreement.
5. Wait for replication to meet lag/consistency thresholds; verify checksums/business totals.
6. Switch the application and connections to the target; allow only a **single writer**.
7. Run smoke tests, validate new transactions, and observe within a controlled window.
8. Open full writes only once the owner accepts the outcome; continue post-checks and status logging.

**Do not maintain ad-hoc dual-write** across two independent databases. If concurrent writes are required, a verified conflict resolution, transaction/idempotency, source-of-truth, and reconciliation design must be in place. Changing DNS alone also does not guarantee all clients switch immediately: DNS caching, connection pools, long-lived connections, and IP allowlists still apply.

## 17. Cutover and Rollback Runbook

A migration plan is incomplete if it merely says “run tool and switch DNS.” It needs a runbook with verification gates and named owners.

### 17.1. Sample Cutover Runbook

| Phase | Action | Evidence to Verify | Owner |
| --- | --- | --- | --- |
| **T−7 days** | Freeze scope, config changes, permissions, rehearsal results | Change ticket, dependency list, backup test | Migration lead |
| **T−1 day** | Confirm sync/replication, quota, capacity, keys/certificates | Lag, health, monitoring, contact list | DBA/Platform |
| **T−30 min** | Go/no-go, notify stakeholders, freeze changes | Approvals, no blocker incidents | Business/SRE |
| **T0** | Quiesce writes, capture required recovery point | No unplanned write transactions | App/DBA |
| **T+** | Final sync and consistency check | Row counts, checksums, business invariants | DBA/Data |
| **T+** | Switch traffic, health/smoke tests | Authentication, API, database, logs, payment sandbox | App/Network |
| **T+** | Monitor SLOs, errors, latency, cost, security | Dashboards and log checks | SRE/Owner |
| **Post-stabilization** | Owner sign-off, disable old write path, decommission plan | Acceptance report | Business/FinOps |

Timings are illustrative. Actual durations must be designed around measured **downtime windows and sync speeds**. Never make decisions by ticking off a checklist without real evidence.

### 17.2. Go/No-Go Rules

**Go** when: the landing zone is secure, dependency paths work, backup/restore is verified, replication lag meets threshold, support staff are present, fallback is clear, and rehearsal succeeded. **No-go** if any mandatory condition is unmet, for example:

- No backup with a tested restore exists.
- Traffic/identity path to the payment system is unproven.
- Database schema relies on unsupported features.
- Network bandwidth or quota is insufficient for expected load.
- No mechanism guarantees zero loss of confirmed transactions.
- Business approver is unavailable.

### 17.3. Rollback Is More Than “Pointing DNS Back”

Before the new target accepts writes, rollback is relatively straightforward (route traffic back to source). **Once the target has accepted new data**, rollback becomes complex: you must answer how new data moves back to the old source, how in-flight transactions are handled, and who validates the result.

For example, if 1,000 new orders are created in Azure after cutover:

- Simply switching DNS back to the old database causes those orders to **be missing** from the old system, even if the application starts up fine.
- A pre-designed reverse replication/reconciliation/transaction-replay mechanism is required, or else **roll forward** to fix issues on the target.
- If data cannot be rolled back safely, explicitly declare a **point of no return once writes open** and prepare a roll-forward plan thereafter.

Rollback triggers must be measurable—such as error rates exceeding a threshold for a defined period or loss of a core function. Do not trigger rollback on gut feeling when data stakes are high.

## 18. Security and Compliance Throughout Migration

Migrations often introduce extra access paths, temporary permissions, and data copies, requiring protection from discovery through source decommissioning.

### 18.1. Control Points

- **Least privilege:** discovery/migration accounts have only required permissions on source and Azure target; restrict broad subscription-wide roles.
- **Identity:** prefer appropriate identity mechanisms such as Microsoft Entra ID/managed identities or workload identity federation where supported by services and tools; avoid storing long-lived secrets in scripts.
- **Secrets/certificates:** store and rotate via an appropriate secret management mechanism; never commit passwords to Git or inventory files.
- **Encryption:** encrypt data in transit and at rest as required; verify key ownership and rotation.
- **Network security:** restrict ingress/egress, use private connectivity, NSGs/firewalls, DNS, and monitoring.
- **Data classification:** only transfer data to approved regions and services; do not use sensitive production data in pilots without approval.
- **Audit:** track who ran migration actions, permission changes, cutovers, and rollbacks and when.
- **Temporary resources:** appliances, agents, staging storage, backups, snapshots, public IPs, VPNs, and temporary credentials must have a cleanup schedule.

Never **disable logging, antivirus, database encryption, or firewalls** just to speed up copying without an assessment, compensating controls, and security approval. When temporary exceptions are needed, strictly bound scope and duration and enforce revocation.

### 18.2. Identity Migration

Legacy authentication setups may rely on AD DS, LDAP, Kerberos, service accounts, RADIUS servers, or custom SSO. Analyze:

1. Which users and service accounts authenticate against which systems.
2. Which groups/roles grant permissions, and whether delegations or trusts exist.
3. Whether applications hardcode domain names, SIDs, LDAP paths, or service principal names.
4. Whether identity sync is needed or on-prem AD must remain during a hybrid phase.
5. Whether migrating to Entra/OIDC/SAML or managed identities is feasible within acceptable change limits.

**Never replace IAM by sharing a single administrative account** across all new services. Migration is an opportunity to improve security, but major authentication changes require thorough end-to-end business flow testing.

## 19. Testing Migration Before Production Cutover

### 19.1. Testing Layers

| Category | Question | Examples |
| --- | --- | --- |
| **Functional** | Do business flows behave correctly? | Order creation, refunds, report export, file upload/download |
| **Integration** | Do dependencies still work? | Payment gateway, AD, SMTP, NAS, batch jobs |
| **Data integrity** | Is data complete and consistent? | Row counts, checksums, balances, foreign keys |
| **Performance** | Does it meet peak RPS, p95/p99, throughput? | Load tests using baseline request mix |
| **Security** | Are permissions, secrets, encryption, audits right? | Pentest/risk review within approved scope |
| **Resilience/DR** | How does instance/zone loss or backup restore behave? | Failover/restore rehearsal in a controlled environment |
| **Operations** | Are alerts, runbooks, backups, patching, deploy ready? | On-call simulation, test restore, rollback |
| **Financial** | Do costs align with forecast? | Cost Analysis, log ingestion, egress/dual-run |

**A server booting successfully** is not acceptance. An application might run on a new VM while month-end batches fail, new data lands in the wrong region, documents cannot be read, or outbound emails fail to send.

### 19.2. Before-and-After Baseline

Hypothetical acceptance table:

| Metric | Pre-Migration | Post-Migration Target | Test Result (Illustrative) | Verdict |
| --- | ---: | ---: | ---: | --- |
| Peak throughput | 120 RPS | At least 120 RPS | 135 RPS | Pass |
| API p95 | 350 ms | At most 400 ms | 370 ms | Pass |
| Business success | 99.95% | At least 99.95% | 99.98% | Pass on metric |
| Restore time | 90 minutes | At most 120 minutes | Not rehearsed | **Insufficient evidence** |
| Critical batch | 24 jobs/month | 24 jobs succeed | 22/24 tested | **Not accepted** |
| Data reconciliation | Zero lost transactions | 0 discrepancy per rules | 0 after reconciliation | Pass |

Never declare **migration completed** simply because the first three metrics pass while DR or critical batch tests remain incomplete. “No evidence yet” must remain explicitly flagged and resolved.

## 20. Synthesis Example: Selecting a Strategy for the Orders System

### 20.1. Existing System

The enterprise operates:

- **Orders web:** frontend application redeployable via CI/CD.
- **Orders API:** runs on two Windows VMs, depends on local session state and a file share.
- **SQL Server:** 1.2 TiB database using SQL Agent jobs and one linked server.
- **NAS:** stores invoices/documents with heavy SMB operations.
- **Active Directory:** provides employee identity and serves other legacy systems.
- **Payment provider:** partner HTTPS API with IP allowlist and contractual idempotency support.
- **Batch reporting:** runs at month-end; load and dependencies not yet fully tested.

The business owner requires **planned downtime of at most 30 minutes**, zero loss of confirmed transactions, p95 latency at or below 400 ms at 120 RPS peak, and no payment architecture changes during peak season.

### 20.2. Preliminary Component Decisions

| Component | Preliminary Strategy | Azure Target to Evaluate | Rationale and Conditions |
| --- | --- | --- | --- |
| Orders web | **Replatform** | App Service or suitable container platform | Easy CI/CD; verify runtime/auth and static assets |
| Orders API | **Phased replatform** | App Service/Container Apps/VM depending on compatibility | Externalize sessions and file share first; if time-constrained, temporary rehost is possible |
| SQL Server | **Rehost first or replatform post-assessment** | SQL Server on Azure VM; evaluate Managed Instance/SQL Database | Linked server, jobs, schema/drivers need testing; 30-min downtime requires replication |
| NAS file share | **Replatform if compatible** | Azure Files or suitable solution | Verify SMB/ACLs, locking, latency, throughput |
| AD DS | **Retain/hybrid in early waves** | Hybrid connectivity; evaluate identity modernization | Other systems still depend on it; cannot retire immediately |
| Payment integration | **Retain external integration** | Controlled outbound HTTPS | Approve IP allowlist, retry/idempotency, and TLS |
| Batch reporting | **Assess, rehost, or refactor later** | VM or suitable batch processing service | Must assess month-end schedule and dependencies |

**These are conditional decisions**, not a production design. Do not assume Azure SQL Managed Instance supports every SQL Server feature in use; database assessment and PoC are mandatory.

### 20.3. Why Not Refactor Everything Immediately?

Decomposing a monolith and changing database engines can yield long-term benefits, yet doing so simultaneously increases moving parts within a tight cutover window. It can be staged:

1. **Wave 0:** landing zone, hybrid network, identity, backups, telemetry.
2. **Wave 1:** pilot non-critical reporting service, validate toolchain and runbook.
3. **Wave 2:** remediate session/file dependencies, rehearse API + DB.
4. **Wave 3:** migrate Orders as an assessed dependency group with measured data sync/cutover.
5. **Post-stabilization:** evaluate managed database/refactoring using real operational data.

This approach accepts temporary technical debt to lower cutover risk. If data center deadlines or compliance rules differ, the strategy may shift.

### 20.4. Blockers Before Go-Live

- No evidence yet that linked servers/SQL Agent jobs are target-compatible.
- SMB permissions and file locking post-migration remain unproven.
- Payment provider has not confirmed new endpoints/IPs.
- Under-30-minute downtime not yet rehearsed on the 1.2 TiB database.
- No design yet for handling **post-cutover transactions** if rollback is triggered.
- Month-end business batches not yet tested.
- Dual-run and hybrid egress costs not yet reconciled.

Every blocker requires an **owner, deadline, verification action, and a no-go trigger** if unresolved; never just write “risk accepted.”

## 21. Migration Assessment Report Template

A review-ready assessment should cover the following sections:

| Section | Questions That Must Be Answered |
| --- | --- |
| **Executive decision** | Recommend migrate, retain, replace, or retire—and why? |
| **Business context** | Objectives, deadlines, criticality, downtime, stakeholders |
| **Current state** | App inventory, versions, owners, OS, infrastructure, licenses |
| **Dependency graph** | Data flows, auth, network, schedulers, external systems |
| **Baseline** | RPS/p95, CPU/RAM/IOPS, DB growth, backup/restore, cost |
| **Constraints** | Data residency, compliance, unsupported features, budget |
| **R-strategy comparison** | Options, benefits, risks, disqualifying criteria |
| **Azure target architecture** | Region, landing zone, network, identity, compute, data |
| **Cost/TCO** | On-prem vs. Azure, migration/dual-run, sensitivity scenarios |
| **Migration waves** | Migration groups, dependency order, owners, go/no-go gates |
| **Data plan** | Online/offline, consistency, CDC/replication, reconciliation |
| **Cutover/rollback** | Runbook, read-only, traffic switch, fallback/roll forward |
| **Acceptance** | Functional, performance, security, DR, operations, cost |
| **Risks/actions** | Risk register, owners, mitigations, deadlines, residual risk |

### 21.1. Sample Risk Register

| ID | Risk | Likelihood | Impact | Verification / Mitigation | Owner |
| --- | --- | --- | --- | --- | --- |
| R-01 | App fails to reach SQL over hybrid link | Medium | High | Measure latency, test routes/DNS/ports, consider co-locating wave | Network/App |
| R-02 | Linked server incompatible with PaaS target | High until tested | High | Feature assessment, PoC, SQL VM fallback option | DBA |
| R-03 | Replication lag exceeds downtime window | Medium | Very High | Rehearse with large dataset, track lag stats, no-go threshold | DBA |
| R-04 | Insufficient quota/IPs during scaling | Medium | High | Capacity and quota check before wave | Platform |
| R-05 | Insufficient backup restore evidence | Medium | Very High | Restore test, record actual RTO/RPO | SRE |
| R-06 | Extended dual-run costs | Medium | Medium | Budget, review date, source shutdown trigger | FinOps |
| R-07 | Non-compliant data access permissions | Unverified | Very High | Security approval, data flow mapping, and access tests | Security |

Risk ratings must be grounded in evidence and the organization's risk framework. “Unverified” should never be rounded down to “low.”

## 22. Practice: Selecting a Strategy Using Evidence

**Scenario:** You are preparing a migration assessment for an application consisting of web, API, SQL Server, and a file share. The source infrastructure resides in a data center; the intended target is Microsoft Azure. The figures below are hypothetical and the exercise does not require provisioning live resources.

### Exercise A — Build the Inventory

1. Create an application table capturing owner, criticality, OS/runtime, database, storage, network, RTO/RPO, and batch schedules.
2. Tag each critical field with **verified/observed/declared/unknown**.
3. Identify at least 5 data gaps requiring owner follow-up or additional measurement.
4. Do not place secrets in the inventory table.

**Output:** an inventory table sufficient to plan follow-up discovery.

### Exercise B — Construct the Dependency Graph

1. Map the flow from users through web/API to database, files, identity, payment, and monitoring.
2. Record **protocol, direction, owner, peak traffic, latency, and confidence level** for each edge.
3. Highlight edges that would traverse hybrid VPN/ExpressRoute if only a subset moves.
4. Propose components that must move in the same wave due to latency or data consistency.

**Output:** an annotated dependency graph and proposed wave sequence.

### Exercise C — Choose R and Target

Evaluate four scenarios:

1. Low-criticality internal portal; existing Linux VM is compatible.
2. Unsupported legacy CRM; a business-approved SaaS product exists.
3. SQL Server with untested stored procedures and linked servers.
4. Factory control system requiring ultra-low latency and offline capability.

For each scenario, identify **at least two candidate Rs**, eliminate options violating hard constraints, and specify tests required before finalizing.

**Output:** a reasoned decision matrix, not merely a column of Azure service names.

### Exercise D — Calculate Transfer Time and TCO

1. Calculate minimum time to transfer 4 TiB over a nominal 200 Mbit/s link.
2. Recalculate at 60% effective throughput.
3. Review the 36-month TCO comparison in Section 13 and list at least three assumptions that could reverse the conclusion.

**Reference results:** roughly **48.9 hours** ideal; roughly **81.5 hours** at 60% throughput; illustrative TCO **66,000 USD vs. 63,600 USD**.

### Exercise E — Design Cutover/Rollback

Use targets of **at most 30 minutes downtime** and **zero loss of confirmed transactions**.

1. Write steps for backup/test restore, initial sync, final sync, and write freeze.
2. Specify the single-writer rule, data validation method, and smoke tests.
3. Define the last point at which traffic can roll back to source **without reverse sync**.
4. Once the target has accepted new transactions, propose either roll forward or a verified reverse data path.
5. Specify who makes the go/no-go decision and mandatory evidence.

**Output:** a rehearsal runbook with an acceptance criteria table and risk register.

## 23. Common Mistakes During Migration Assessment

| Mistake | Impact | How to Avoid |
| --- | --- | --- |
| Treating VM inventory as the whole app | Misses databases, AD, batches, external APIs | Build workload model and graph |
| Surveying for only 24 hours | Misses month-end jobs and peaks | Cover full business cycles and owner reviews |
| Sizing from average CPU | New VMs/DBs lack capacity | Use peaks, percentiles, and capacity tests |
| Treating tool “ready” as production ready | Business logic errors go undetected | Compatibility + functional/integration tests |
| Moving chatty web tier before DB | p95 spikes from hybrid latency | Measure round-trips, consider migration units |
| Picking PaaS solely for cost without feature checks | Unsupported SQL features/runtimes | PoC and feature matrix |
| Moving all machines but forgetting identity/DNS | Logins or connections fail | AD/Entra/DNS architecture + tests |
| Assuming online migration = zero downtime | Inconsistent cutover | Quiesce writes, final sync, validation |
| Treating rollback as just changing DNS | Loses transactions written on target | Design reverse sync/roll forward beforehand |
| Moving prod data to unapproved regions | Policy violation | Data classification and approvals |
| Ignoring dual-run/egress | TCO underestimated | Include one-time + operating + overlap |
| Opening firewalls wide to copy faster | Expands attack surface | Least privilege and time-bound exceptions |
| Decommissioning right after smoke tests | Loses recovery path / violates retention | Hypercare, sign-off, archive/deletion policy |
| Lifting legacy config to cloud and stopping | Preserves security debt and costly ops | Modernization roadmap and post-migration review |

## 24. Self-Check Questions

**Question 1.** Why is listing VMs alone insufficient for a migration decision?  
**Answer:** Because applications also depend on data, identity, networking, files, middleware, batches, external integrations, and business constraints that cannot be inferred from a VM list.

**Question 2.** Is “Azure ready” in an assessment tool enough to confirm an application can go live?  
**Answer:** No. You still must validate compatibility, business flows, data integrity, SLOs, security, networking, DR, and operations.

**Question 3.** When should retain be chosen?  
**Answer:** When regulatory, hardware, network latency, or dependency constraints prevent moving now, or keeping it is proven advantageous; a hybrid governance plan is required.

**Question 4.** How does rehost differ from replatform?  
**Answer:** Rehost moves the current state largely as-is onto similar infrastructure; replatform makes targeted adjustments to leverage a managed platform without requiring a full architectural rewrite.

**Question 5.** Does Azure Arc automatically convert an on-premises VM into an Azure VM?  
**Answer:** No. Arc is used to manage/govern non-Azure resources within supported scope; it does not perform workload migration.

**Question 6.** Why is a dependency graph needed before organizing migration waves?  
**Answer:** It shows which services must exist first, which components must move together, and which hybrid links risk latency spikes.

**Question 7.** Are RTO and the migration downtime window the same value?  
**Answer:** No. RTO is the recovery target during an incident; the downtime window is the planned outage limit during cutover.

**Question 8.** Roughly how long does 4 TiB of data take over 200 Mbit/s under ideal conditions?  
**Answer:** Roughly 48.9 hours, excluding overhead and data changes during copying.

**Question 9.** After cutover, the Azure database has accepted new transactions. Can you immediately roll back by pointing DNS back to the old database?  
**Answer:** It is unsafe because new data may not exist on the old source; a reverse data/reconciliation plan or roll forward is required.

**Question 10.** Why does meeting the RPS target alone not prove migration success?  
**Answer:** Untested batches, failing restores, broken features, wrong data permissions, or lost/duplicated transactions may still exist.

**Question 11.** Why must a TCO model include dual-run?  
**Answer:** During transition you may pay for both source and target, connectivity, replication, and staff operating both environments.

**Question 12.** Should migration waves be ordered solely by highest priority score?  
**Answer:** No. Hard constraints and dependency ordering can force a different sequence; scores assist decisions rather than granting automatic approval.

## 25. Pre-Approval Migration Checklist

- [ ] Business objectives, owner, downtime window, and success metrics are defined.
- [ ] Inventory covers servers, apps, databases, files, identity, network, integrations, batches, and licensing.
- [ ] Every key data point has a source and confidence level (verified/observed/declared/unknown).
- [ ] Dependency graph is confirmed by owners, with protocols, directions, and latency/throughput.
- [ ] Baselines exist for performance, peak capacity, errors, backup/restore, SLOs, RTO/RPO, and cost.
- [ ] Data classification, residency/compliance, encryption, secrets, and auditing are evaluated.
- [ ] Compatibility is verified for the Azure target, engine, OS, runtime, features, and licensing.
- [ ] Retain/retire/rehost/relocate/replatform/refactor/repurchase are compared with rationale.
- [ ] Azure landing zone has appropriate subscriptions, policies, RBAC, networking, DNS, monitoring, backup, quota, and budget.
- [ ] Migration waves reflect dependencies and the pilot is validated.
- [ ] Data migration includes integrity verification and single-writer/cutover rules.
- [ ] Runbook assigns owners, go/no-go gates, bounded rollback, and a roll-forward plan once new data exists.
- [ ] Functional, integration, performance, security, backup/DR, and operational tests are planned/executed.
- [ ] TCO accounts for Azure fees, licensing, staffing, transfer, dual-run, and schedule delay risk.
- [ ] Hypercare, acceptance sign-off, and source decommission criteria are defined.
- [ ] Unresolved blockers are explicitly reported, never silently marked as passed.

**Conclusion:** Migration assessment and strategy selection are evidence-driven decision processes. A solid infrastructure inventory must be paired with a dependency graph, baselines, data requirements, compatibility checks, TCO, and a rehearsable cutover plan. On Microsoft Azure, the right choice may be to migrate, modernize, repurchase, operate hybrid, or retire low-value systems. Only with **the right workload, right strategy, right sequence, and clear acceptance criteria** does migration deliver lasting value rather than merely relocating servers.
