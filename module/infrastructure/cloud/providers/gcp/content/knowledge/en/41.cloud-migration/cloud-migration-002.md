# Migration Center and Migration Readiness Assessment

Migrating to Google Cloud begins before creating a VM, database, or Kubernetes cluster. An organization needs to know **what assets it owns, how they depend on one another, what their actual load looks like, which applications are easy to move, where risks lie, and whether post-migration costs make sense**. Skipping discovery can lead to sizing Compute Engine instances incorrectly, missing connectivity ports between applications, overlooking background services, or migrating a database before dependent systems are ready.

**Google Cloud Migration Center** supports the infrastructure discovery and assessment phase: collecting server, VM, and database information; organizing an asset inventory; grouping assets; modeling target scenarios; and generating Total Cost of Ownership (TCO) reports. The **Migration Center discovery client** and **mcdc CLI** handle data collection; some methods also produce offline assessment reports. The results serve as inputs for architectural decisions and migration planning—not a single command that automatically moves every workload to GCP.

This lesson walks through the journey from initial discovery to organizing applications into migration waves. Examples focus on an enterprise system running VMs, Java applications, and databases in an on-premises data center, evaluating Compute Engine, Cloud SQL, Cloud Run, and GKE as target options.

## Learning Objectives

After this lesson, you will be able to:

- Explain the purpose and boundaries of Migration Center in a cloud migration journey.
- Choose a discovery method: continuous collection, one-time scan, guest discovery, or manual data import.
- Understand the types of data collected, how to read an asset inventory, and which gaps must be filled manually.
- Walk through an illustrative `mcdc` CLI workflow to run discovery and generate an offline report.
- Organize asset groups, configure migration preferences, and interpret TCO reports.
- Assess readiness across technical, business, security, operational, and cost dimensions.
- Distinguish VM portability from Java application modernization feasibility.
- Build migration waves with dependencies, validation goals, and rollback plans.
- Identify risks related to collected data, access permissions, estimation accuracy, and actual costs.

## 1. Where Does Migration Center Fit?

A cloud migration program typically comprises the following phases:

~~~text
Program kickoff
        |
        v
Discovery / Inventory
        |
        v
Assessment / TCO / Readiness
        |
        v
Landing zone and target architecture design
        |
        v
Migration waves and pilot planning
        |
        v
Migration / Validation / Cutover
        |
        v
Operate / Optimize
~~~

Migration Center primarily supports **discovery** and **assessment**. Actual migration execution uses corresponding tools and workflows—for example, Migrate to Virtual Machines for supported VM migrations, Database Migration Service for supported databases, or CI/CD pipelines to redeploy Java applications.

### What Does Migration Center Provide?

| Capability | Question to Answer | Output |
|---|---|---|
| Discovery | Which servers, VMs, databases, and software exist? | Asset list and collected specifications |
| Inventory | How many assets exist, with what specs and locations? | Asset inventory, metadata, and statistics |
| Dependency insight | Which assets communicate and depend on each other? | Data supporting grouping and assessment |
| Grouping | Which components belong to the same app or migration scope? | Server/database groups |
| Migration preferences | What happens under different regions, machine types, or sizing strategies? | Assumptions per scenario |
| TCO reports | What might target infrastructure cost? | Estimates and comparisons by group/asset |
| Offline assessment | Is a workload suitable for specific migration targets? | Fit assessment, findings, and blockers based on tool rules |

These outputs are one part of a **migration assessment**. They do not replace application owner interviews, compatibility testing, compliance analysis, or architectural decisions.

### Distinguishing Assessment Tools from Migration Tools

| Need | Tool / Process Type |
|---|---|
| Server discovery and cost estimation | Migration Center |
| Offline assessment and blocker detection | `mcdc` CLI and supported assessment rule sets |
| Migrating VMs to GCP | VM migration tools matching source and target |
| Migrating database data | Database Migration Service or database migration workflows |
| Moving Java apps to containers | Refactoring, containerization, CI/CD, Cloud Run/GKE |
| Designing networking/IAM/project structure | Landing zone, networking, IAM, and IaC |
| Measuring post-cutover outcomes | Cloud Monitoring, Logging, SLOs, and application testing |

An assessment stating that a VM can run on Compute Engine does not prove that the application inside the VM can be split into microservices or run directly on Cloud Run.

## 2. Starting with Business Questions and Scope

Do not scan the entire infrastructure before knowing what decisions the results will inform.

Examples of business goals:

- Exit a data center before a lease expires.
- Reduce VM and licensing operational costs.
- Improve disaster recovery capabilities.
- Modernize select Java/Spring services into containers.
- Consolidate databases and adopt managed services such as Cloud SQL.
- Reduce hardware operational risk and increase release automation.
- Meet data residency, security, and audit requirements.

### Intake Questions

1. Which systems are in scope for migration?
2. What are the contractual, project, or compliance deadlines?
3. What is the maximum acceptable downtime?
4. Which data has specific residency, encryption, or access control requirements?
5. Who are the application owner and technical owner?
6. Is architectural change allowed, or must workloads move as-is?
7. What are the budget, licensing constraints, and cloud team readiness?
8. Is success measured by SLOs, RTO/RPO, cost, or release velocity?

### Defining Scope

| Attribute | Example |
|---|---|
| Business unit | Commerce |
| Source environment | VMware vSphere in Data Center A |
| Estimated count | Roughly 120 VMs and 15 databases |
| Priority applications | Checkout, catalog, order processing |
| Out of scope | OT systems and dedicated network appliances |
| Deadline | Per approved project plan |
| Target regions | Selected after latency, compliance, and service availability review |
| Approvers | Application owner, platform, security, and finance |

Numbers are illustrative only. When declaring scope, explicitly document which assets remain unscanned and why—for example, due to firewalls, missing credentials, or unsupported operating systems.

## 3. How Do Discovery and Assessment Differ?

**Discovery** collects factual data: assets, operating systems, CPU/RAM, disks, networking, running processes, database configurations, and time-series utilization, depending on the method.

**Assessment** combines that data with assumptions to recommend target destinations, identify risks, and compare scenarios. Without sufficient discovery data, assessment results fall back to default estimates and carry lower confidence.

~~~text
Source infrastructure
  VMware / physical servers / AWS / Azure / databases
             |
             v
      Discovery methods
             |
             v
     Configuration + performance data
             |
             v
    Normalize inventory + asset groups
             |
             v
Migration preferences + constraints
             |
             v
    Assessment / TCO / Fit / Risks
             |
             v
  Decision register + migration waves
~~~

An inventory of 150 VMs without dependency and performance data may suffice for a preliminary report, but it is not enough to commit to a detailed cutover schedule or optimal sizing.

## 4. Choosing a Data Collection Method

Migration Center supports multiple methods to balance speed, depth, and security requirements.

| Method | Characteristics | When to Choose |
|---|---|---|
| `mcdc` CLI – one-time discovery | Single or batch scan; can run offline and export later | Pilots, small environments, long-running agents not yet approved |
| Discovery client – continuous collection | Installed discovery client, scheduled scans, accumulates time-series data | Large systems, cyclic loads, need representative performance samples |
| Guest discovery | Collects inside the OS: processes, services, network, and select databases | Need visibility into workloads inside VMs/physical servers |
| Inventory discovery | Pulls VM/asset data from hypervisors or cloud APIs | Want a fast asset list on supported platforms |
| IP range scan | Probes IP ranges and performs guest discovery when authorized | Incomplete CMDB or unclear what machines exist |
| Manual import | Upload templates or data from supported sources like RVTools | Cannot deploy collectors or existing reports are already available |

### One-Time Scans vs. Continuous Collection

A one-time scan is great for getting started quickly, but it can miss peak traffic, month-end batches, or backup windows. Continuous collection over several days or weeks better reflects actual load.

There is no fixed number of discovery days that fits every system. For applications with monthly or quarterly cycles, supplement with existing monitoring data if the discovery window does not cover peak load.

### Choosing Tools by Source

- **VMware vSphere:** `mcdc` can retrieve inventory via the vSphere API; guest discovery adds OS and application details.
- **Linux/Windows servers:** guest discovery can use SSH, WMI, or locally run collection scripts depending on connectivity.
- **AWS:** `mcdc` supports inventory for select assets such as EC2 and RDS within tool limits.
- **Azure:** some inventory discovery features are in Preview; verify support before planning around them.
- **Databases:** methods exist for Microsoft SQL Server, MySQL, and PostgreSQL per documentation.
- **Restricted-connectivity environments:** run an offline assessment first or use a controlled file export workflow.

Do not assume every AWS/Azure asset type or database engine is supported with the same level of detail.

## 5. Which Discovery Data Matters?

The assessment team needs enough data to answer three questions: **what is it, how much load does it handle, and who depends on it?**

### Basic Configuration

| Data | Value for Assessment |
|---|---|
| Asset ID/hostname | Identification, deduplication, and CMDB reconciliation |
| OS and version | Support/lifecycle checks and target compatibility |
| CPU architecture/vCPU | Machine family recommendations and portability |
| RAM | Memory sizing selection |
| Disk, filesystem, IOPS | Storage design and cost estimation |
| IP, network interface, ports | VPC, firewall, and connectivity planning |
| Hypervisor/cloud origin | Selecting the right migration method |
| Processes/services | Detecting application dependencies and runtimes |
| Database engine/version | Evaluating managed database migration feasibility |
| Uptime/maintenance | Determining migration windows and disruption risk |

### Time-Series Performance

- CPU utilization: average, peak, percentiles.
- Memory utilization and memory pressure.
- Disk capacity, disk throughput/IOPS, and data growth rate.
- Network throughput, network connections, and inter-host traffic.
- Traffic patterns by hour/day/month.
- Batch job, scheduler, queue, and peak load behavior.

Especially for sizing, do not rely solely on allocated vCPU/RAM. A 16-vCPU VM averaging 10% CPU most of the time may qualify for a smaller machine, but you must check peaks, licensing, burst workloads, and redundancy requirements before deciding.

### Ownership and Business Context

Most technical inventories do not automatically tell you:

- Which product does the application belong to?
- Who approves downtime?
- Which data is sensitive or subject to specific regulations?
- Are there integrations with out-of-scope systems?
- Do licenses permit running in public cloud?
- Does the system operate on monthly, quarterly, or fiscal closing cycles?

Enrich these fields from the CMDB, owner interviews, and architecture records. This is human analytical work and should not be treated as information automatically verified by Migration Center.

## 6. Preparing the Project and Enabling Migration Center

Before uploading discovery data, you need a Google Cloud project dedicated to assessment with appropriate IAM permissions.

Workflow in the Google Cloud Console:

1. Select or create a project for migration assessment.
2. Open Migration Center.
3. If prompted, enable the required APIs.
4. Choose a region to store and process Migration Center data.
5. Confirm default migration preferences or proceed to customize them later.
6. Complete activation and grant permissions to assessment operators.

**The Migration Center region is chosen during activation and cannot be changed directly afterward.** Verify residency, governance, and region availability before finalizing.

### Roles and Permissions

Discovery operators do not need administrative rights over the entire GCP project. Separate responsibilities:

- Migration Center and API administrator.
- Collector operator with access to source VMware/OS/database systems.
- Analyst viewing inventory and running reports.
- Security reviewer inspecting collected metadata and sharing permissions.
- Finance/architect consuming TCO and migration preferences.

To export `mcdc` data to Migration Center, Google Cloud documentation describes the Migration Center Admin role and permissions related to source/report frames. Check the exact permissions required for each method. Apply least privilege and avoid sharing static service account keys when safer authentication options exist.

## 7. Practicing with `mcdc` CLI: Discovering VMware VMs

The following example illustrates `mcdc` on a Linux host with connectivity to vCenter and read permissions for inventory. `VSPHERE_URL`, `VCENTER_USER`, and `PROJECT_ID` are placeholders.

### Step 1: Download the Tool

From Google Cloud's official documentation, download the `mcdc` version for Linux or Windows. Check OS requirements, disk space, network connectivity, and checksums if provided by the distribution source.

Do not commit collector binaries or credentials to Git. Use a dedicated assessment machine with minimal privileges and connectivity restricted to authorized source infrastructure.

### Step 2: Scan Inventory via vSphere API

~~~bash
./mcdc discover vsphere \
  --url https://VSPHERE_URL \
  -u VCENTER_USER
~~~

The tool will prompt for the corresponding credentials. Depending on permissions, you may need to scope the path by data center, cluster, or folder to avoid scanning out-of-scope resources.

Example scanning a specific folder:

~~~bash
./mcdc discover vsphere \
  --url https://VSPHERE_URL \
  -u VCENTER_USER \
  --path DATACENTER/vm/APPLICATION_FOLDER
~~~

Before running against production, confirm API scope, firewalls, and scan timing with the infrastructure team. If vCenter statistics settings have not retained sufficient performance metrics, sizing results may fall back to defaults.

### Step 3: Supplementary Guest Discovery

Hypervisor inventory shows that VMs exist, but not necessarily the processes, databases, or dependencies inside the guest OS. For Linux hosts allowing SSH:

~~~bash
./mcdc discover ssh HOSTNAME_OR_IP
~~~

For Windows guests, `mcdc` supports corresponding methods via WMI or local collection scripts; syntax and account requirements vary by method. Documentation also covers database discovery via engine-selection flags during guest discovery.

Guest discovery can capture process arguments, runtime environments, and sensitive network information. Review output file contents, permissions, and retention periods before exporting.

### Step 4: Generate an Offline Assessment

After discovery, generate a summary HTML report:

~~~bash
./mcdc report --format html --file assessment.html
~~~

`mcdc` supports other offline report formats depending on purpose, including HTML, JSON, CSV, and XLSX. Reports can present fit assessments along with findings/blockers for migration journeys supported by the tool.

Distinguish "offline assessment" from "online TCO": an offline report provides local rule-based analysis, whereas TCO reports in Migration Center incorporate asset groups and migration preferences to compare costs across multiple scenarios.

### Step 5: Export to Migration Center When Authorized

Once the project is enabled and credentials are configured, an illustrative command is:

~~~bash
./mcdc export mc --project PROJECT_ID
~~~

This command sends discovery data to Migration Center. **`mcdc` does not automatically upload data just because you ran discovery; export is a separate action that requires approval.**

If the environment does not permit direct uploads, keep the assessment offline or use an approved file-export and upload workflow.

### Step 6: Post-Export Verification

- Does the asset count in Migration Center match the scanned source?
- Are there duplicate, missing, or misnamed assets?
- Do VM CPU/RAM/disk values match vCenter?
- Does performance data cover a representative timeframe?
- Which databases were detected, and are their engines/versions accurate?
- Were any sources skipped due to missing permissions?
- Should any datasets be excluded from assessment as out of scope?

Do not jump straight to target design until the inventory has been cleaned.

## 8. Importing Data When a Discovery Client Cannot Be Installed

Some organizations do not allow scanning tools on production systems or lack connectivity to every network segment. Migration Center offers manual import paths.

| Source | Available Method | Limitations to Note |
|---|---|---|
| VMs and servers | Template/tabular upload | Without performance metrics, sizing relies on assumptions |
| VMware | RVTools export and import in supported format | May lack in-guest processes, services, and dependencies |
| SQL Server/MySQL/PostgreSQL | Supported database discovery scripts | Permissions and granularity vary by database engine |
| Multi-source infrastructure | Combine collector results and CMDB | Requires ID reconciliation to eliminate duplicates |

Google Cloud documents per-project asset limits in its import/quota documentation. Check current limits before splitting assessment projects; avoid arbitrary splits that make whole-scope TCO comparisons difficult.

### Import Quality Warnings

A schema-valid file does not guarantee accurate data. Verify:

- Denominators: powered-on vs. powered-off VMs, test VMs, and templates.
- Units: GB/GiB, MHz/GHz, IOPS, and percentages.
- Time zones and observation windows.
- Unique resource IDs.
- Source and report export timestamp.
- Blank or mis-populated default values.
- Overlap between automated inventory discovery and manual imports.

For data templates, use Migration Center's official format. Do not guess column names or ordering based solely on sample CSVs in this lesson.

## 9. Building a Decision-Ready Asset Inventory

After discovery, the next step is enriching the inventory with business context and dependencies.

Example internal governance table:

| Asset ID | Role | Criticality | Owner | Source | Tentative Target |
|---|---|---|---|---|---|
| `vm-web-01` | Java web frontend | High | Commerce | VMware | Compute Engine, or Cloud Run after refactoring |
| `vm-api-01` | Spring Boot API | Critical | Commerce | VMware | Compute Engine first, Cloud Run later |
| `vm-db-01` | PostgreSQL | Critical | Data | VMware | Cloud SQL for PostgreSQL if compatible |
| `vm-batch-01` | Scheduled jobs | Medium | Operations | VMware | Cloud Run jobs / GKE / VM as needed |
| `vm-report-01` | Reporting service | Low | Analytics | VMware | Migrate after the pilot wave |

The table above is an example, not actual Migration Center output.

### Columns to Add

- Application and business capability.
- Environment: dev/test/staging/prod.
- Compliance classification.
- RTO/RPO and downtime tolerance.
- Peak seasons and maintenance windows.
- OS/runtime/JDK/database versions.
- External connectivity and firewall requirements.
- License owner and support expiration dates.
- Migration strategy and migration wave.
- Blockers, decision owners, and resolution deadlines.
- Confidence level of collected information.

Every decision should link to an evidence source: collector output, CMDB, logs, architecture docs, or owner confirmation.

## 10. Asset Groups and Dependency Analysis

The right migration unit is usually an **application group**, not an individual VM. A system may span a load balancer, web tier, application tier, database, queue, scheduler, and partner integrations.

~~~text
Customers
    |
    v
Web / API Gateway
    |
    v
Java Checkout Service
    |
    +----> PostgreSQL
    |
    +----> Inventory Service
    |
    +----> Message Broker
    |
    +----> Payment Provider (external)
~~~

If you move the Java Checkout Service while leaving the database and message broker in the old data center, latency and egress/connectivity costs can rise while cutover becomes harder.

### Creating Asset Groups

Migration Center lets you group assets to generate TCO reports. Groups should align with one or more boundaries:

- Business application.
- Network and data dependencies.
- Owning team and maintenance schedules.
- Sensitivity and compliance level.
- Target architecture or project/region.
- Planned migration wave.

An asset group in a cost report does not automatically prove that all business dependencies have been identified. Combine network observations, architecture diagrams, firewall logs, application configurations, and owner interviews.

### Dependency Matrix

| Source | Target | Protocol | Criticality | Planning Guidance |
|---|---|---|---|---|
| Checkout API | PostgreSQL | TCP/database | Critical | Move together or maintain stable connectivity |
| Checkout API | Inventory API | HTTPS | High | Test network paths and authentication |
| Checkout API | Payment Provider | HTTPS external | Critical | Check egress IP, TLS, and allowlists |
| Batch Worker | Database | TCP/database | Medium | Can follow the main app if compatible |
| Reporting | Data export | File/SQL | Low | Suitable for a later wave |

Retain the source and confidence level of every dependency. An observed connection does not always signify a mandatory dependency; conversely, connections that only appear at month-end can easily be missed.

## 11. Migration Preferences and Target Scenarios

Once asset groups exist, Migration Center lets you create **migration preferences** sets. These govern the assumptions used to generate TCO reports, such as region, target product, machine series, sizing, and select cost factors.

### Example Scenarios

| Scenario | Objective | Assumptions |
|---|---|---|
| A – Compatibility first | Move VMs with minimal changes | Compute Engine, no aggressive rightsizing |
| B – Cost-balanced | Use utilization metrics to suggest smaller VMs | Compute Engine, moderate sizing |
| C – Cost-optimized | Aggressively reduce over-provisioning | Compute Engine, aggressive sizing with peak checks |
| D – VMware continuity | Preserve the VMware model for suitable groups | Google Cloud VMware Engine |
| E – Managed database | Evaluate moving supported databases | Managed database targets per matching preferences |

No single scenario fits every asset. A critical application requiring headroom and strict RTO may not suit aggressive rightsizing.

### Parameters Typically Reviewed

- Deployment region.
- Machine series or machine type families.
- Tenancy preference.
- Sizing strategy: no rightsizing, moderate, aggressive, or custom where supported.
- CPU/memory utilization and percentiles.
- Storage sizing/multipliers.
- Uptime or monthly usage hours.
- Network egress estimates.
- Licensing/OS editions and associated costs.
- Target products for supported servers or databases.

Preferences for **servers** and **databases** have separate scopes. Do not assume a server sizing setting automatically applies to SQL Server/PostgreSQL/MySQL.

### Why Model Multiple Scenarios?

For example, for the same set of 20 VMs:

- Scenario A keeps vCPU/RAM roughly unchanged.
- Scenario B uses utilization data to select smaller VMs.
- Scenario C reserves greater memory headroom for batch peaks.

Comparing scenarios reveals projected cost differences and performance trade-offs. The architecture team must verify that recommended machines can handle peaks and satisfy licensing rules before locking them in.

## 12. Reading Total Cost of Ownership (TCO) Reports

Migration Center can generate TCO reports for asset groups based on preferences, alongside detailed pricing and asset inventory reports.

TCO typically helps provide:

- Summaries of assets and utilization levels.
- Recommended target products or configurations matching preferences.
- Estimated infrastructure costs per group/asset.
- Comparisons across target regions, sizing, and product options.
- Assumptions influencing the estimates.

### TCO Is Not a Fixed Quote

Actual costs also depend on:

- Pricing at deployment time and selected region.
- Actual post-cutover utilization.
- Egress, cross-region traffic, and connectivity back to on-premises.
- Storage, backups, snapshots, and logging/monitoring.
- Licensing and committed use discounts.
- One-time migration costs: staffing, tooling, testing, and downtime.
- Costs of running two environments in parallel during transition.
- Refactoring, training, and technical debt remediation costs.

Therefore, use TCO for **comparison and preliminary decision-making**, then build a fuller financial model for the business case.

### Watch Out for Servers and Databases Running on the Same Host

Google Cloud documentation notes that if a group contains both a database deployment and its underlying server, reports may estimate the server as a standalone VM and the database as a separate database service. This can cause **double counting** when the real plan is to migrate only the database to Cloud SQL and retire the source VM. Finance and architecture teams must inspect estimation boundaries.

### Checking Output Quality

| Question | Why Ask It |
|---|---|
| Is performance data sufficient? | Missing data can force estimate-based sizing |
| Are any assets double-counted? | Skews resource counts and costs |
| Does the region comply with policy? | Pricing and data residency differ |
| Are disks and IOPS accounted for? | Storage performance is easily overlooked |
| Is estimated egress realistic? | Network costs can be substantial |
| Are monthly runtime hours accurate? | 24/7 differs from scheduled workloads |
| How are SQL/Windows/VMware licenses treated? | Can significantly shift TCO |
| Are rightsizing rules too aggressive? | Risks under-provisioning capacity |
| Is parallel-run cost included? | Avoids overly optimistic savings projections |

## 13. Assessing Readiness: More Than Booting a VM

**Migration readiness** measures preparedness to migrate toward a specific target. It spans hardware/OS, applications, data, networking, security, operations, and business alignment.

| Dimension | Question | Required Evidence |
|---|---|---|
| OS/hardware | Are the OS, CPU architecture, and drivers supported on the target? | Inventory, compatibility matrix |
| Application | Are runtimes, native libraries, services, and schedulers suitable? | JDK/app-server versions, dependencies |
| Database | Are engine/version, extensions, size, replication, and downtime compatible? | Database assessment, migration tests |
| Network | How are DNS, routing, firewalls, latency, private links, and egress handled? | Dependency map, network design |
| Identity/security | Are IAM, service accounts, secrets, certificates, encryption, and audits covered? | Security review and policies |
| Availability | Are SLOs, RTO/RPO, failover, and backups achievable? | DR design and rehearsals |
| Operations | Are monitoring, logs, runbooks, on-call, and incident processes ready? | Operational readiness review |
| Business | Are owners, maintenance windows, downstream approvals, and deadlines aligned? | Stakeholder sign-off |
| Cost | Are target costs and migration effort acceptable? | TCO and business case |

An assessment result marking a VM as a "Good fit" does not guarantee all dimensions above pass. Fit results reflect only the data and rules available to the tool.

### Offline Fit Assessment

`mcdc` offline assessments categorize workloads into levels such as:

- Excellent fit.
- Good fit, with findings to note.
- Needs minimal work before migration.
- Needs moderate work.
- Needs major work.
- No fit.
- Insufficient data.

These labels come from offline evaluation for migration journeys supported by the tool. Read each finding/blocker and its associated rule. Do not convert results into a single percentage risk score if the tool does not define such a scale.

### Missing Data Is a Meaningful Status

When guest discovery is missing, never assume a workload is compatible. Identify missing information and plan follow-up actions:

- Run a guest scan with appropriate permissions.
- Interview the application owner.
- Inspect OS, processes, ports, runtimes, and libraries.
- Test migrating a copy during a pilot.

Assign a confidence level to each asset and do not use incomplete data to approve production cutover.

## 14. Dedicated Assessment for Java/Spring Applications on GCP

A VM running Java can move as-is to Compute Engine, whereas running on Cloud Run or GKE requires evaluating how the application is packaged and operated.

### Java Compatibility Checklist

| Item | Assessment Details |
|---|---|
| JDK/runtime | Version, vendor, LTS policy, native libraries |
| Application server | Tomcat, Jetty, WebLogic, JBoss, and configuration dependencies |
| Configuration | Environment variables, files, secrets, and profiles |
| Local filesystem | Uploads, logs, temp files, persistent data |
| Session state | In-memory/local-disk sessions vs. external store |
| Scheduling | Cron jobs, batches, background threads |
| Database | JDBC drivers, connection pools, transactions, schemas |
| Network | Private connectivity, IP allowlists, DNS, outbound TLS |
| Authentication | Service accounts, OAuth, mTLS, legacy LDAP |
| Observability | Structured logs, metrics, traces, health checks |
| Startup/shutdown | Cold starts, graceful shutdown, signal handling |
| Resilience | Timeouts, retries, idempotency, scaling behavior |

### Target Selection Examples

**Compute Engine:** suitable when you must preserve the OS, monolithic application, or VM configuration largely intact. It can shorten the migration path, though you still must design backups, networking, IAM, patching, and autoscaling.

**Cloud Run:** suitable for HTTP/container services that can run statelessly or rely on external state. Verify ports, startup times, concurrency, ephemeral local disk, and background work.

**GKE:** suitable when you need orchestration, sidecars, workloads with complex networking/operational requirements, or already have Kubernetes expertise. In return, the team must manage cluster operations, security, and releases.

**Cloud SQL:** suitable when the engine/version/features are supported and a data migration path meets RTO/RPO. Never assume every database extension or feature transfers directly.

**A target chosen in TCO** does not automatically imply a tool-supported migration path. The architecture team must independently validate that the application can operate on that target.

## 15. The 6R Framework: Per-Workload Strategies

The 6R strategy framework is a discussion aid, not a mandatory taxonomy imposed by Migration Center.

| Strategy | Meaning | Example |
|---|---|---|
| Rehost | Migrate largely as-is | Java VM to Compute Engine |
| Replatform | Change underlying platform with minimal logic changes | Database to Cloud SQL or Java app to a suitable managed runtime |
| Refactor / Rearchitect | Redesign architecture to leverage cloud capabilities | Split monolith, adopt Pub/Sub, Cloud Run/GKE |
| Repurchase | Switch to SaaS | Replace self-hosted tool with a SaaS service |
| Retire | Decommission systems no longer delivering value | Reporting VM with no remaining users |
| Retain | Keep temporarily on-premises/at source | Application with legal constraints or specialized hardware |

Do not pick a strategy based purely on CPU/RAM. Factor in deadlines, technical debt, application lifecycle, business criticality, and engineering capacity.

For instance, a legacy Java VM might be rehosted first to meet a data center exit deadline, then refactored service-by-service to Cloud Run during an optimization phase. A two-stage plan is often more sensible than attempting a major refactor right before cutover.

## 16. Prioritization Model: Quick Wins and Blockers

An organization must sequence migrations based on value, risk, and dependencies. A qualitative matrix can guide review meetings.

| Criterion | Easy to Migrate | Hard to Migrate |
|---|---|---|
| Technical compatibility | Supported OS/runtime | Legacy OS, native libraries, specialized devices |
| Dependencies | Few dependencies | Many out-of-scope systems |
| Data | Small, replicable | Very large, low downtime tolerance |
| Security/compliance | Clear regulations, approved target | Unresolved residency/licensing issues |
| Operations | Has tests/monitoring/runbooks | Lacks telemetry and clear owners |
| Business impact | Has maintenance windows | 24/7 transactions, strict SLAs |
| Team readiness | Has IaC/CI/CD and dedicated owners | Lacks cloud skills and access permissions |

Do not invent arbitrary numerical scores and present them as official Migration Center results. If the team uses internal scoring, document the formula, weights, owner, and evidence so results can be reviewed.

### Prioritizing a Pilot

A good pilot typically has:

- Clear business value.
- Small scope with well-understood dependencies.
- Feasible testing, cutover, and rollback.
- Low risk of data loss or widespread disruption.
- Opportunity to validate the landing zone, networking, IAM, telemetry, and migration process.

Do not necessarily pick the smallest VM if it has tangled dependencies. Pick a representative workload with controllable risk.

## 17. From Assessment to Migration Waves

A migration wave is a group of workloads moved in a scheduled batch with clear dependencies, timelines, and completion criteria.

~~~text
Wave 0: Landing zone + connectivity + pilot
           |
           v
Wave 1: Low-dependency applications
           |
           v
Wave 2: Application groups + dependent databases
           |
           v
Wave 3: Mission-critical transactional systems
           |
           v
Wave 4: Optimization / decommission source systems
~~~

### What Must Each Wave Define?

- List of assets and application groups.
- Target product/region/project.
- Dependencies moving together or kept in hybrid mode.
- Migration method and responsible operators.
- Pre-cutover test plan.
- RTO/RPO, downtime window, and approvers.
- Data sync/replication and consistency verification.
- Cutover steps: DNS, load balancing, routing, secrets, config.
- Rollback triggers and rollback time cutoff.
- Acceptance criteria and sign-off owner.
- Plan to decommission old resources after an observation period.

Migration Center provides inventory, grouping, and planning data; actual orchestration and cutover rely on other organizational tools and processes.

## 18. Real-World Scenario: Assessing an Ordering Application

A retail company operates an ordering system on VMware:

- 2 VMs running Java/Spring Boot APIs.
- 1 VM running PostgreSQL.
- 1 VM running batch jobs and sending emails.
- An external payment service over HTTPS.
- An internal ERP system over VPN.

### Step 1 – Discovery

The team uses `mcdc` to inspect inventory, run guest discovery on approved VMs, and collect performance metrics across a full cycle. They discover PostgreSQL uses extensions that need verification, batch jobs only run overnight, and the API relies on persistent connectivity to the ERP.

### Step 2 – Grouping and Enrichment

Create an "Order Management" group containing the application and database VMs. Enrich with business metadata: SLOs, RTO/RPO, batch hours, ERP owner, partner access permissions, and data requirements.

### Step 3 – TCO Scenarios

- A: Both API/batch and DB stay on Compute Engine.
- B: API/batch on Compute Engine, database moved to Cloud SQL if compatible.
- C: API refactored to Cloud Run, batch to Cloud Run jobs, database on Cloud SQL.

Migration Center TCO primarily reflects target groups and costs supported by the tool; refactoring, database migration, and hybrid connectivity costs must be calculated outside the report. Do not present all three scenarios as if Migration Center fully models all of them automatically when features are unsupported.

### Step 4 – Readiness Review

| Component | Finding | Provisional Decision |
|---|---|---|
| Java API | Stateless HTTP, but uses in-memory sessions | Externalize sessions before autoscaling |
| PostgreSQL | Extension unverified on Cloud SQL | Run a compatibility proof of concept |
| Batch | Scheduled runs with temp files | Evaluate Cloud Run jobs and durable storage |
| ERP VPN | Latency and firewall rules unmeasured | Test hybrid connectivity |
| Payment API | Static IP allowlist | Design egress/NAT and request approval |

### Step 5 – Pilot

Deploy a replica of the API on Compute Engine or Cloud Run in staging, pointing to a test database. Measure:

- Request latency.
- Error rate and timeouts.
- Network latency over VPN.
- DB connectivity and connection pooling.
- Deploy/rollback behavior.
- Logs, metrics, traces, and alerts.
- Actual costs during the trial period.

### Step 6 – Migration Wave

Wave 0 builds the landing zone and connectivity; Wave 1 pilots low-criticality batch jobs; Wave 2 moves the API and database once data synchronization is planned; Wave 3 cuts over production traffic per the runbook. Shut down the old source only after verifying data consistency, passing business checks, and clearing the rollback window.

## 19. Data Security During Discovery

Discovery collects metadata about systems. It can include hostnames, IP addresses, processes, services, network dependencies, command-line arguments, and other values that may be sensitive depending on the collector and method.

You must:

1. Obtain approval from owners and the security team before scanning.
2. Restrict IP ranges, accounts, and privileges on source systems.
3. Review the data-collection documentation for the chosen method.
4. Store discovery data in locations protected by appropriate IAM.
5. Confirm authorization to export data to Google Cloud before uploading.
6. Never put credentials, private keys, or raw discovery data into Git/tickets/chat.
7. Set retention policies and delete exports that are no longer needed.
8. Document the intended use and report recipients.
9. Verify residency regions when activating Migration Center.
10. Use offline assessment if security policies do not yet permit uploads.

The fact that a tool does not intentionally read application payloads or data files does not eliminate risk from process arguments, environment variables, or network metadata. Google Cloud documentation notes that guest discovery can capture sensitive values in output on the collector host; treat output files as sensitive assets.

### IAM and Storage

- Separate collector/export service accounts from accounts running production applications.
- Do not grant project Owner solely for assessment when narrower roles suffice.
- Use organization-approved authentication mechanisms.
- Monitor audit logs for permission changes and related administrative actions.
- Review sharing permissions on TCO/inventory reports.
- If using VPC Service Controls for assessment data, design perimeters according to supported capabilities and test export paths.

## 20. Common Pitfalls in Migration Assessment

| Pitfall | Consequence | How to Avoid |
|---|---|---|
| Single scan during off-peak hours | Under-sized target recommendations | Collect across full cycles and peaks |
| Relying solely on hypervisor data | Misses apps/databases and dependencies | Combine guest scans with owner interviews |
| Treating VM count as app count | Wrong waves and broken dependencies | Group by business application |
| Believing "Good fit" guarantees success | Overlooks networking, compliance, data, and ops | Review blockers and run a pilot |
| Comparing TCO without recording preferences | Cannot explain cost differences | Version assumptions and scenarios |
| Counting server and DB as independent workloads | Double counting costs | Review target model boundaries per group |
| Moving DB before checking compatibility | Outages or data errors | Test engine, extensions, and replication |
| Using default utilization despite critical peaks | Capacity shortages | Supplement with performance time-series |
| Ignoring downtime/RTO/RPO | Cutover violates business SLAs | Obtain owner sign-off and rehearse rollback |
| Uploading unapproved discovery data | Governance and privacy risk | Run offline first; approve exported data |
| Treating Migration Center as a cutover tool | Migration plan lacks execution steps | Pair with migration tooling and runbooks |
| Failing to track out-of-scope assets | Missing dependent systems | Document exclusions and assumptions clearly |

## 21. Output Checklist Before Locking the Migration Plan

### Scope and Data

- [ ] Business objectives and owners are defined.
- [ ] In-scope and out-of-scope boundaries are agreed upon.
- [ ] Discovery methods match each source environment.
- [ ] Representative performance metrics have been collected.
- [ ] Inventory is reconciled with the CMDB and source systems.
- [ ] Duplicates are removed and missing data is logged.
- [ ] Critical dependencies and external systems are cataloged.

### Assessment and Cost

- [ ] Asset groups reflect applications, databases, and dependencies.
- [ ] Migration preferences are versioned per scenario.
- [ ] TCO is checked for region, sizing, egress, licensing, and uptime.
- [ ] Potential server/database double counting has been checked.
- [ ] Migration effort, parallel-run costs, and operational costs are added.
- [ ] Fit assessments are reviewed per finding/blocker.
- [ ] A readiness matrix exists with owners and evidence.

### Planning and Operations

- [ ] Compute Engine/Cloud SQL/Cloud Run/GKE targets are validated individually.
- [ ] Java apps are reviewed for JDK/runtime, state, filesystem, and connectivity.
- [ ] Suitable landing zone, VPC, IAM, logging, and backups are in place.
- [ ] Migration waves align with dependencies and business priorities.
- [ ] Every wave has testing, downtime, cutover, rollback, and sign-off plans.
- [ ] A verifiable pilot workload is selected.
- [ ] A mechanism exists to refresh inventory/assessment when source systems change.
- [ ] Discovery records and reports are protected under governance controls.

## Conclusion

Migration Center provides the data foundation for Google Cloud migration decisions: identifying assets, collecting configuration and performance data, grouping workloads, comparing preferences, and calculating TCO. The `mcdc` CLI enables one-time discovery or offline assessments, while the discovery client suits continuous collection over time. However, true migration readiness is only confirmed when tool outputs are combined with **dependencies, application/data compatibility, security, operations, downtime requirements, and a real pilot**. A strong assessment not only projects costs, but also highlights missing data, risks to mitigate, migration wave ordering, and how success will be verified.

## References

- [Google Cloud Migration Center – Discovery and assessment overview](https://docs.cloud.google.com/migration-center/docs/discovery-and-assessment-overview)
- [Get started with Migration Center](https://docs.cloud.google.com/migration-center/docs/get-started-with-migration-center)
- [Start an asset discovery](https://docs.cloud.google.com/migration-center/docs/start-asset-discovery)
- [Migration Center discovery client CLI overview](https://docs.cloud.google.com/migration-center/docs/discovery-client-cli-overview)
- [Migration Center discovery client overview](https://docs.cloud.google.com/migration-center/docs/discovery-client-overview)
- [Run an inventory discovery](https://docs.cloud.google.com/migration-center/docs/run-inventory-discovery)
- [Run a guest discovery](https://docs.cloud.google.com/migration-center/docs/run-guest-discovery)
- [Run an IP range scan](https://docs.cloud.google.com/migration-center/docs/run-ip-range-scan)
- [Manual data import overview](https://docs.cloud.google.com/migration-center/docs/manual-import-overview)
- [Generate an offline assessment](https://docs.cloud.google.com/migration-center/docs/run-offline-assessment)
- [Offline assessment rules](https://docs.cloud.google.com/migration-center/docs/assessment-rules)
- [Export data to Migration Center](https://docs.cloud.google.com/migration-center/docs/export-collected-data)
- [Create migration preferences](https://docs.cloud.google.com/migration-center/docs/migration-preferences)
- [Migration preferences for servers](https://docs.cloud.google.com/migration-center/docs/server-preferences)
- [Generate TCO reports](https://docs.cloud.google.com/migration-center/docs/generate-tco-report)
- [Migration Center report types](https://docs.cloud.google.com/migration-center/docs/migration-center-reports)
- [Discovery client data and security](https://docs.cloud.google.com/migration-center/docs/discovery-client-data-and-security)
