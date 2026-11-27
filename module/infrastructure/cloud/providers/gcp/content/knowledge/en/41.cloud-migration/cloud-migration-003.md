# Choosing Rehost, Replatform, and Refactor Across GCP Services

Migrating an application to Google Cloud does not simply mean copying a server to another virtual machine. A system also depends on its operating system, runtime, database, network, identity, licensing, deployment processes, and business requirements. Some workloads need to move to the cloud quickly with minimal changes; others benefit from moving to a managed database; and some systems only truly unlock cloud benefits when redesigned into independently scalable and resilient components.

In the **Migrating to Google Cloud** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson builds a methodology for choosing between **rehost** (lift and shift), **replatform** (lift and optimize), and **refactor** (move and improve/modernize). Options are mapped to Compute Engine, Google Cloud VMware Engine, Cloud SQL, AlloyDB for PostgreSQL, Cloud Run, Google Kubernetes Engine (GKE), Pub/Sub, and other data services. Decisions are based not on an abstract notion of "cloud-native," but on objectives, constraints, acceptable change scope, and post-migration verifiability.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between rehost, replatform, and refactor; recognize when to retain, retire, repurchase, relocate, or rebuild.
- Survey workloads, measure dependencies, and identify business drivers, SLOs, RTO, RPO, and compliance requirements.
- Select target GCP products based on application traits, databases, data state, scalability, and team capabilities.
- Choose Migrate to Virtual Machines, Database Migration Service, or an appropriate application modernization path.
- Estimate timeline, cost, risk, technical debt, and long-term operational overhead for each option.
- Design migration waves, pilots, rehearsals, cutover, rollback, and validation.
- Avoid pitfalls around dual writes, data synchronization, access permissions, private networking, runtime versions, and software certification.
- Author a decision record with assumptions, rejected alternatives, acceptance criteria, and post-migration optimization work.

## 2. Three Core Strategies

### 2.1. Rehost: Lift and Shift

**Rehost** moves a workload from the source environment to a GCP runtime environment with little or no code/architectural modification. For example, a Java application VM on VMware is moved to **Compute Engine** with a similar OS, runtime, and service model.

Characteristics:

- Minimal changes; easy to apply when source code is unavailable or vendors forbid modifications.
- Migration timelines are generally shorter than rewriting functionality.
- Retains assumptions about VMs, state, processes, and deployments; existing operational tooling can often continue to be used.
- Delivers only partial cloud benefits: OS patching, middleware management, HA, and backups may remain the team's responsibility.
- VM, licensing, storage, and operational costs can be high if on-premises sizing is carried over without re-measurement.

Never call rehost "risk-free." IP configuration, DNS, database latency, OS drivers, firewalls, software licenses, and disk layouts can prevent a cloned VM from behaving like the source environment.

### 2.2. Replatform: Lift and Optimize

**Replatform** preserves most business logic while replacing one or more underlying platform layers to reduce operational toil or improve scalability. Examples:

- Self-managed PostgreSQL on a VM to **Cloud SQL for PostgreSQL**.
- MySQL on a VM to **Cloud SQL for MySQL**.
- A stateless HTTP application containerized and moved from a VM to **Cloud Run** without major domain model changes.
- An application server on a VM moved to **GKE** or App Engine when container/runtime management needs align.

Replatforming typically requires updating connection strings, secrets, service accounts, health checks, persistent storage, startup behavior, backups, or drivers. Choose this path when managed service benefits are high and the application can adapt to service limits without deep redesign.

Typical risks: compatibility of database extensions, versions, JDBC drivers, networking, connection pooling, temporary filesystems, runtime lifecycles, and OS features no longer directly accessible.

### 2.3. Refactor: Move and Improve

**Refactor** substantially changes code structure, deployment units, or business orchestration to leverage cloud-native mechanisms. Examples:

- Splitting a Java monolith into bounded contexts and independent services on Cloud Run/GKE.
- Replacing long-running synchronous processing with **Pub/Sub** and workers with retries/idempotency.
- Moving local files to Cloud Storage and local sessions to an appropriate external state/session store.
- Adopting CI/CD, progressive delivery, autoscaling, resilience, observability, and security by design.
- Converting batch jobs to Cloud Run Jobs/Workflows/Dataflow where appropriate.

Benefits can include independent scaling, faster releases, reduced coupling, and higher fault tolerance. In return, development effort, integration testing, API/event schema governance, distributed data handling, and operational complexity increase. Refactoring everything in one wave just because "microservices are more modern" is a risky decision.

### 2.4. Other Strategies and Naming Differences

Migration frameworks do not all use the exact same set of "R" labels. Google Cloud Architecture Center describes approaches such as rehost, replatform, refactor, re-architect, rebuild, and repurchase; planning guides often add retain and retire. Some documents also break out **relocate**.

| Strategy | Concise Meaning | Example |
|---|---|---|
| Rehost | Move runtime environment with minimal changes | VMware/AWS/Azure VM to Compute Engine |
| Replatform | Move platform layer with light optimization | PostgreSQL on VM to Cloud SQL |
| Refactor | Modify code/architecture structure for improvement | Monolith to independent modules/services |
| Re-architect | Redesign overall architecture | Synchronous point-to-point to event-driven |
| Rebuild | Reimplement functionality/application | Replace legacy system with new code |
| Repurchase | Replace product with SaaS/purchased solution | Replace self-hosted software with SaaS |
| Retain | Do not migrate in this phase | Keep systems with legal or vendor constraints |
| Retire | Decommission | Shut down batches or systems with no remaining users |
| Relocate | Move platform/infrastructure with minimal change, sometimes keeping VMware stack | VMware to Google Cloud VMware Engine |

**Do not force every workload into just three options.** Retiring a system can save far more than rehosting an application with no remaining value. Repurchasing can beat refactoring if a SaaS product fully meets functional needs.

## 3. Pre-Selection Assessment

Migration decisions must start from discovery data, not a list of favorite services.

### 3.1. Inventory and Dependency Mapping

At a minimum, each application needs:

| Field | Question to Answer |
|---|---|
| Owner and business criticality | Who approves changes, and what is the impact of downtime? |
| Runtime/OS | Windows/Linux, version, CPU architecture, agents, licenses? |
| Compute | CPU p50/p95/peak, RAM working set, IOPS, throughput, GPU? |
| Storage | Local disk, network share, object storage, retention, backups? |
| Data | Engine, version, schema, size, change rate, CDC availability? |
| Dependencies | DNS, LDAP/AD, mail, APIs, payments, ERP, shared databases? |
| Network | Ingress/egress, private routes, NAT, ports, static IPs, mTLS? |
| Security | IAM, encryption, key ownership, data residency, audits? |
| SLO | Availability, p95/p99 latency, throughput, peak seasons? |
| Recovery | RTO, RPO, backups, restore tests, DR region? |
| Delivery | Are source/build pipelines available? Test coverage and release cadence? |
| Commercial | Licenses, support contracts, vendor certification, EOL? |
| Economics | Current TCO, staffing costs, data center lease expiration? |

A **dependency graph** must indicate connection direction and traffic volume, not just list machines in the same subnet. For example, API A depends on Database B with a 20 ms p99 budget and on LDAP C per request: moving A first while leaving B/C on-premises can spike latency or break authentication.

~~~mermaid
flowchart LR
    Users[Users] --> W[Web/API VM]
    W --> DB[(Source PostgreSQL)]
    W --> AD[Directory/LDAP]
    W --> File[File share]
    Batch[Batch VM] --> DB
    Batch --> Partner[Partner API]
~~~

Tag dependencies by severity: **hard dependency** on the request path, **soft dependency** tolerant of retries/queuing, and scheduled **batch dependency**. Group migration waves to keep latency-sensitive transactions close together.

### 3.2. Baseline Metrics to Measure Before Migrating

- Traffic by hour/day/week, spikes, and peak seasons.
- HTTP/API latency p50/p95/p99, error rates, timeouts, retries.
- CPU/RAM/GC, database connection counts, IOPS, disk latency, and capacity.
- Inter-system network flows, bandwidth, and peak throughput.
- Backup/restore times, RPO, and failover procedures.
- Deployment duration and incident frequency.
- Operational, licensing, monitoring, backup, and data transfer costs.

Capture a baseline across at least one representative usage cycle; a daytime average CPU snapshot is rarely enough to size VMs or databases.

### 3.3. Discovery and Assessment Tools

**Migration Center** helps collect and assess inventory/dependencies, supporting cost planning and migration path selection within supported scope. Assessment output is an input—it does not replace application validation, security review, licensing checks, and cutover testing.

For VMware or VMs from other clouds, also review the operating systems, disks, encryption, and configurations supported by **Migrate to Virtual Machines**. For databases, check **Database Migration Service (DMS)** supported source/destination versions alongside actual SQL features and extensions.

## 4. Criteria for Choosing Rehost, Replatform, or Refactor

### 4.1. Comparison Matrix

| Criterion | Rehost | Replatform | Refactor |
|---|---|---|---|
| Code changes | None or minimal | Low to moderate | Moderate to major |
| Initial delivery timeline | Usually short | Medium | Usually long |
| Risk of altering business logic | Lower | Medium | Higher |
| Technical debt addressed | Minimal | Partial | Can address substantially |
| Managed service adoption | Limited | Moderate to high | High if designed well |
| OS/runtime management effort | Retained | Can decrease | Can decrease significantly |
| Independent scaling | Similar to source | Better with the right platform | High when workloads are split cleanly |
| Testing complexity | Focused on environment/config | Adds compatibility testing | Contract, integration, event, resilience |
| Long-term TCO | Can remain high | Opportunity to reduce | Opportunity to optimize, must factor dev cost |
| Rollback feasibility | Depends on cutover | Depends on target writes | Harder if API/data semantics changed |

"Lower/higher" reflects general tendencies, not guarantees. A massive Oracle/Windows rehost can be far more complex than refactoring a small stateless service.

### 4.2. Decision Rules

**Prefer rehost** when:

- Data center exit deadlines are imminent, leaving no time for code changes.
- It is a vendor/black-box app with no source code or VM-only license certification.
- The application is stable, rarely changes, and the team can manage the OS/DB.
- You need to de-risk the initial move before optimizing in later waves.

**Prefer replatform** when:

- Core business logic works without a rewrite.
- The target managed database/runtime supports all critical features and extensions.
- Current infrastructure and operations generate significant toil.
- You can test data access paths, sessions, filesystems, networking, and startup.
- The organization wants early cloud benefits while keeping change scope controlled.

**Prefer refactor** when:

- The change scope delivers clear business value: release cadence, scale, reliability, or new capabilities.
- A monolith or synchronous batch job bottlenecks part of the system.
- Source code, test automation, and product ownership are ready.
- You can run old/new paths in parallel and govern data migration.
- You accept the design, distributed testing, SRE/observability, and schema evolution costs.

**Prefer retain/retire/repurchase** when compliance/vendor/hardware blocks migration, the product has reached end of value, or SaaS solves the problem better.

### 4.3. Do Not Decide by a Single Score

You can score options on timeline, cutover risk, 3-year cost, engineering effort, SLOs, security, and toil reduction. However, requirements like **data residency**, invalid licensing, or unmet RPO are **disqualifying constraints**—high cost scores cannot compensate for them.

A weighted table can support decision workshops, provided assumptions, data sources, evaluation dates, and unresolved risks are recorded.

## 5. Mapping Workloads to GCP Products

| Source Workload | Rehost | Replatform | Refactor |
|---|---|---|---|
| VMware VM running Java monolith | Compute Engine, or keep VMware stack on Google Cloud VMware Engine as needed | Lightly containerize to Cloud Run/GKE, separate DB to Cloud SQL | Split domain modules/services, event-driven, per-service deploy |
| PostgreSQL/MySQL on VM | DB VM on Compute Engine (short-term, still self-managed DB) | Cloud SQL or AlloyDB for PostgreSQL when compatible | Redesign data/read models, split transaction boundaries |
| Stateless .NET/Java/Node Web API | VM on Compute Engine | Cloud Run/App Engine/GKE | Cloud-native services, workflows/events, and caching |
| Cron-based batch job | VM with scheduler | Cloud Run Jobs, Cloud Scheduler/Workflows as appropriate | Event-driven fan-out via Pub/Sub/Dataflow |
| File server and file-writing apps | VM with appropriate disks or network file system | Cloud Storage/Filestore with app adapter | Separate metadata, object events, asynchronous processing |
| Self-managed data warehouse/ETL | VM/cluster on GCE | BigQuery/Dataflow based on compatibility | Incremental/streaming pipeline model and new governance |
| Vendor app requiring VMware | Compute Engine if OS/license supported; or VMware Engine | Only when vendor certifies managed platform | Usually evaluate replacing product (repurchase) over modifying it |

This table provides **evaluation directions**, not compatibility guarantees. Verify regions, quotas, licenses, managed service features, and connectivity options for each application.

## 6. Rehost in Detail: Migrate to Virtual Machines and Compute Engine

### 6.1. What Can Migrate to Virtual Machines Do?

**Migrate to Virtual Machines** supports migrating VMs/disks from Google-documented sources such as **on-premises VMware vSphere, AWS, Azure, and Google Cloud VMware Engine** to Compute Engine or Persistent Disk. It is a VM-level migration tool: it is not an automatic converter from monoliths to Cloud Run or databases to Cloud SQL.

A migration typically uses a host project managing orchestration and one or more target projects receiving VMs. Verify permissions, billing, APIs, destination regions, OS support, and source compatibility before starting.

### 6.2. VM Migration Lifecycle

~~~mermaid
flowchart LR
    A[Discovery + inventory] --> B[Configure source/target]
    B --> C[Initial replication]
    C --> D[Test clone + validation]
    D --> E{Pass gates?}
    E -- No --> F[Fix compatibility/config]
    F --> D
    E -- Yes --> G[Final sync + cutover]
    G --> H[Production validation]
    H --> I[Finalize + decommission source]
~~~

- **Replication:** copies disk data from source to Google Cloud, continuing while the source VM stays running.
- **Test clone:** creates a test VM from replicated data to verify OS boot, applications, networking, disks, and licenses; ensure clones cannot accidentally connect and write to production dependencies.
- **Cutover:** transitions the live workload to the target VM on schedule, controlling data/traffic state and rollback points.
- **Finalize:** complete and decommission the source machine only after acceptance criteria, backups, monitoring, and approval workflows pass.

VM disk replication does not automatically guarantee an **application-consistent cutover** for high-write databases. For databases needing transactional consistency and tight RPO, evaluate logical/physical DB replication, backup + restore, DMS, or engine-specific mechanisms rather than relying solely on snapshots/disk clones.

### 6.3. Designing the Target Landing Zone

Before migrating VMs, provision:

- Appropriate organization/folder/project hierarchy and billing.
- IAM for migration operators, VM runtime identities, and break-glass access.
- VPC/subnets, private DNS, and Cloud VPN/Interconnect if on-premises dependencies remain.
- Least-privilege ingress/egress firewall rules; do not expose everything to the Internet just to boot a VM.
- Images/OS/boot drivers, disk types/sizes, regions/zones, and quotas.
- Backup/DR, OS patching, logging/monitoring agents, and alerting.
- Baseline-driven sizing—do not copy source vCPU/RAM numbers blindly without measuring.

For Windows VMs or vendor software, verify licenses, activation, OS support, kernel/drivers, domain join configuration, and agent entitlements before creating a test clone.

### 6.4. When to Use Google Cloud VMware Engine?

Google Cloud VMware Engine provides a managed VMware environment running on Google Cloud infrastructure for teams that need to keep the VMware/vSphere stack. **Relocating** VMware workloads to VMware Engine reduces guest OS and operational tooling changes compared to moving straight to Compute Engine, though it carries distinct costs, licensing, capacity, and networking requirements.

If the long-term goal is removing VMware dependencies, plan a two-step path: relocate first, then migrate individual VMs from VMware Engine to Compute Engine/managed services when ready. Never call VMware Engine a "serverless replatform."

## 7. Application Replatform: Compute Engine to Cloud Run, GKE, and App Engine

### 7.1. Cloud Run for Stateless HTTP Services

Cloud Run fits HTTP/container applications that do not require OS-level privileges and can tolerate ephemeral instance lifecycles. A Java/Spring Boot application can retain most business logic, but usually requires changing:

- Binding the HTTP port from the `PORT` environment variable and listening on `0.0.0.0`.
- Avoiding persistent data storage on the container's ephemeral filesystem.
- Externalizing sessions and caches if previously stored locally.
- Reading secrets via Secret Manager/workload identity rather than bundled credential files.
- Writing structured logs to stdout/stderr, with appropriate tracing/metrics.
- Sizing connection pools and max instances so they do not overwhelm the database.
- Configuring startup/shutdown/health probes aligned with timeouts and autoscaling.

Example Spring Boot configuration:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

spring:
  datasource:
    hikari:
      maximum-pool-size: 10

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

If the service uses a port other than 8080, Spring configuration must read the `PORT` variable injected by Cloud Run. The YAML above is a simplified example and does not by itself solve Cloud SQL connectivity, identity, secrets, or readiness for every application.

### 7.2. GKE When Kubernetes Capabilities Are Needed

GKE is suitable when you need sidecars, a service mesh, custom scheduling, policy enforcement, operators, or tightly coordinated workloads. Replatforming from a VM to containers on GKE requires addressing:

- Container images, non-root users, CPU/memory requests and limits.
- Readiness/liveness/startup probes and graceful shutdown.
- Pod/service identity using Workload Identity Federation for GKE.
- Horizontal Pod Autoscaler, node capacity, and quotas.
- PersistentVolume/StorageClass for any stateful workloads.
- Kubernetes manifests, Helm/GitOps, image security, and rollback.

GKE Autopilot reduces node management compared to Standard; choosing between them depends on required control, cost, and workload profile. **Do not pick GKE just because of "containers"**: for simple HTTP apps, Cloud Run usually entails less platform overhead.

### 7.3. Is App Engine Still Relevant?

App Engine standard/flexible can fit applications already aligned with App Engine's deployment model or supported runtimes. For new migrations, compare lifecycle, version/runtime support, OS customization, networking, and cost against Cloud Run and GKE. Do not treat App Engine as the default target for every Java app.

### 7.4. Containerization Is Not Refactoring by Default

Putting a monolith into a container, moving configuration to environment variables/secrets, and deploying on Cloud Run/GKE while **keeping domain logic intact** is generally classified as replatforming. Only when you substantially alter code structure, service boundaries, communication protocols, or data ownership is it refactoring/re-architecting.

## 8. Data Replatform: Cloud SQL, AlloyDB, and DMS

### 8.1. Selecting the Target Database

| Source | Target to Evaluate | Notes |
|---|---|---|
| Supported MySQL | Cloud SQL for MySQL | Verify version, charset/collation, engine features |
| Supported PostgreSQL | Cloud SQL for PostgreSQL | Verify extensions, logical replication, roles/permissions |
| PostgreSQL workloads needing specialized performance or HA | AlloyDB for PostgreSQL | Evaluate compatibility, SLA, sizing, cost |
| Supported SQL Server | Cloud SQL for SQL Server | Verify edition, SQL Agent, CLR, licensing, HA |
| Oracle or SQL Server moving to PostgreSQL | Cloud SQL/AlloyDB for PostgreSQL in DMS-supported scenarios | Heterogeneous migration; requires schema/code conversion and thorough testing |

**Database Migration Service** supported versions, sources, and destinations vary by engine and migration type. Consult the **Supported source and destination databases** page before planning; never assume all Oracle, MariaDB, or SQL Server sources follow identical paths. DMS for MySQL does not support MariaDB as an equivalent MySQL source.

### 8.2. Database Migration Service (DMS)

DMS supports homogeneous migrations (e.g., PostgreSQL to Cloud SQL for PostgreSQL) and select heterogeneous migrations (e.g., Oracle/SQL Server sources to PostgreSQL under documented scenarios). Depending on the engine/scenario, it performs an initial snapshot followed by **continuous replication/CDC** to minimize downtime.

A high-level flow:

~~~mermaid
flowchart LR
    S[(Source database)] -->|Initial copy| D[(Cloud SQL / AlloyDB)]
    S -->|Continuous change replication| D
    AppOld[Source app] --> S
    D --> Check[Data validation + lag checks]
    Check --> Gate{Ready to cut over?}
    Gate -- Yes --> Freeze[Quiesce writes / controlled cutover]
    Freeze --> AppNew[Target app]
    AppNew --> D
~~~

Mandatory checks:

- Source and destination version/feature support.
- Private/public connectivity requirements, firewalls, and replication access.
- Database privileges, replication slots/log retention, disk/IO, and impact on source.
- Data volume, change rate, apply throughput, and replication lag.
- Schemas, indexes, sequences, triggers, stored procedures, users, collations, and extensions.
- Data integrity alongside target application functional testing.

Never assume continuous replication equals **zero-downtime** cutover: you still need a write-freeze or write-coordination point, lag verification within acceptable thresholds, and safe connection/traffic switching.

### 8.3. Limits of Engine Changes

Migrating Oracle to PostgreSQL may require rewriting SQL dialects, stored procedures, sequence behavior, transaction semantics, and data types. Depending on the scope of change, this is typically a **heavy-conversion replatform** or close to a **data refactor**. Never treat it as "just swapping a connection string."

If an application depends on an extension unavailable on the managed database, you may need to keep a self-managed database temporarily or redesign around it. Never pick a managed database purely to save admin work while ignoring incompatibilities that could break the application.

## 9. Incremental Refactor: Strangler Pattern and Event-Driven

### 9.1. Why Avoid Big-Bang Rewrites?

Rewriting an entire monolith before migrating can drag out projects, lose undocumented business rules, and make it hard to tell whether a bug stems from migration or new code. The **strangler pattern** lets you extract functionality incrementally by value and risk, routing traffic gradually via a router/API facade while leaving the rest on the legacy system.

~~~mermaid
flowchart LR
    User[Client] --> Router[API facade / routing layer]
    Router -->|Legacy endpoints| Legacy[Monolith on VM]
    Router -->|New bounded context| New[Cloud Run / GKE service]
    Legacy --> DB[(Legacy DB)]
    New --> NewDB[(Owned datastore)]
    Legacy -.Integration events / outbox.-> Pub[Pub/Sub]
    Pub --> New
~~~

Initially, the new service can call the monolith's API for contract-governed reads/writes, then take over data ownership per bounded context once consistency is solved.

### 9.2. Selecting the First Slice

Prioritize capabilities that:

- Have clear domain boundaries with minimal cross-module transactions.
- Have available owners/SMEs to validate business rules.
- Can be tested end-to-end and run in parallel.
- Deliver clear value such as relieving bottlenecks, accelerating releases, or improving UX.
- Support rolling back routing to the legacy path.

Avoid starting with core payment or authorization flows if test coverage, auditing, and data readiness are lacking.

### 9.3. Pub/Sub, Cloud Tasks, and Workflows

- **Pub/Sub:** multiple consumers, event fan-out, and asynchronous integration; delivery can duplicate messages, requiring idempotent consumers.
- **Cloud Tasks:** HTTP task dispatch with retries, rate controls, and queue semantics; suited for background work directed at a specific handler.
- **Workflows:** multi-step orchestration across APIs and Google Cloud services, stateful execution, and error-branch handling.
- **Eventarc:** routes supported events from Google Cloud sources to services/handlers.

Do not convert every synchronous call into an event just to "modernize." When a business process needs immediate responses and clear transactionality, synchronous APIs remain appropriate. If splitting into a saga, design compensating actions, timeouts, poison-message handling, auditing, and idempotency.

### 9.4. Decoupling Data from the Monolith

A tough challenge is data ownership. If both the monolith and the new service write to the same table, business invariants can break as old and new code diverge.

A safe path:

1. Identify the system of record for each entity.
2. Define API/event contracts; distinguish commands from business facts.
3. Keep one side as the primary writer; the other reads via APIs/projections.
4. Use transactional outbox/CDC when reliable change publishing is needed.
5. Test duplicates, out-of-order delivery, replays, and consistency lag.
6. Transfer write ownership only after reconciliation and a rollback path exist.

**Dual writes** to two databases outside a single transaction must use reliable patterns; never assume "write DB A then publish to B" is atomic.

## 10. Foundational Infrastructure: IAM, VPC, Connectivity, and Security

### 10.1. Identity and Permissions

- Separate service accounts for migration operators, replication tools, workload runtimes, and CI/CD.
- Apply least-privilege IAM at the project/resource level; avoid Owner/Editor roles for runtimes.
- On Cloud Run/GKE/Compute Engine, prefer service/workload identities over long-lived JSON keys.
- Pull secrets from Secret Manager, use Cloud KMS encryption keys when required, and retain necessary audit logs.
- Verify engine-level database permissions separately from IAM service-access permissions.

### 10.2. Hybrid Networking

While migration is in progress, GCP and on-premises usually need hybrid connectivity via Cloud VPN or Cloud Interconnect sized for bandwidth, latency, VPC routing, and security.

Items to verify:

- Non-overlapping IP CIDRs and symmetric/clear return traffic paths.
- Source/destination firewall rules, protocols/ports, and private DNS.
- Bottlenecks at NAT, proxies, VPN throughput, and egress costs.
- TLS endpoints/certificates and hostname verification after IP changes.
- Zones/regions, VPC peering, or Private Service Connect where appropriate.
- Encryption in transit during replication; never open wide inbound ports.

If an app moves to GCP while its database stays on-premises, requests may make many trips over the WAN. Measure p95/p99 network RTT and round-trip counts per request path rather than estimating by geographic distance alone.

### 10.3. Compliance, Residency, and Licensing

Data residency, retention, and encryption rules may rule out certain regions or migration paths. Commercial software often ties licenses to CPU cores, hypervisors, cloud providers, or OS editions. Migrate only after confirming license terms and vendor support certifications, especially for databases, ERPs, and legacy agents.

Never copy sensitive data into test projects without data classification and guardrails. Generate synthetic or de-identified test fixtures per policy.

## 11. TCO, FinOps, and Operational Requirements

### 11.1. Modeling Lifecycle Costs

**Never compare options using hourly VM prices alone.** Total cost for each choice includes:

\[
TCO_{3y} =
C_{\text{migration}}+
C_{\text{compute}}+
C_{\text{storage}}+
C_{\text{network}}+
C_{\text{license}}+
C_{\text{operations}}+
C_{\text{risk}} .
\]

Here, $C_{\text{risk}}$ is an assumption-based estimate of downtime, data loss, or incident remediation effort—not a cloud invoice line item.

Cost categories to model:

| Line Item | Rehost | Replatform | Refactor |
|---|---|---|---|
| Migration engineering | Minimal code changes | Platform adjustments and testing | Redesign, testing, and data migration |
| Compute/runtime | 24/7 VMs or MIGs | Managed runtime/containers | Multiple independent autoscaling services |
| Database | Self-managed VM | Managed DB | Potentially multiple datastores/replicas |
| Network/data transfer | Hybrid links, egress, NAT | Still needs hybrid initially | Service-to-service traffic and events |
| Operations | OS, patching, backups, runbooks | Reduced partial toil | Different toil: events, distributed tracing, schemas |
| Licensing | May keep legacy licenses | Check managed compatibility | May replace or eliminate licenses |
| Parallel run | Source and target VMs running concurrently | DB replication + target app | Legacy and modernized run longer |

During migration, **double run** (operating both environments concurrently) creates temporary costs. Budget for log retention, backups, data transfer, support, and the rollback window.

### 11.2. Sizing and Spend Commitments

Rehosts often carry over over-provisioned on-premises sizing. Once stabilized, re-measure CPU/RAM, IOPS, networking, and autoscaling, then rightsize. Do not buy long-term committed use discounts for workloads whose optimal size is unknown or that may soon move to Cloud Run/managed services.

Replatforming and refactoring can cut idle compute while introducing new costs such as Cloud SQL HA/replicas, Pub/Sub, Cloud NAT, Artifact Registry, Cloud Logging, and BigQuery. Forecast against real traffic and verify budget alerts; remember that alerts are not hard spending caps.

### 11.3. Carbon and Sustainability Aspects

Shutting down idle resources, choosing efficient machine types/regions, and using autoscaling can reduce resource consumption. However, do not claim emissions drop proportionally with cost. To evaluate emissions, use Carbon Footprint within its supported scope alongside business units, latency, reliability, and cost.

## 12. Designing Migration Waves

Do not migrate individual VMs in an arbitrary order. Group waves by dependencies and criticality.

### 12.1. A Sample Wave Plan

| Wave | Workloads | Goal | Sample Strategy |
|---|---|---|---|
| 0 - Foundation | Landing zone, IAM, VPC, backups, monitoring | Infrastructure & guardrails ready | No workload migration yet |
| 1 - Pilot | Low-criticality app, simple dependencies | Validate tooling and process | Rehost |
| 2 - Core rehost | Legacy VMs with clear RTO/RPO | Meet data center exit deadline | Rehost |
| 3 - Managed data | Compatible databases | Reduce toil/backup/patching | Replatform |
| 4 - App modernization | Stateless APIs, standalone batches | Autoscale/CI/CD | Replatform or refactor |
| 5 - Domain refactor | Monolith modules with owners | Independent deploys, higher reliability | Refactor |

Adjust the order based on dependencies. If a database must sync ahead of the app, pre-stage data transfer and cut over together in one wave. Never force "database wave 3" after "app wave 2" if WAN calls will break the business flow.

### 12.2. Waves Can Mix Strategies

An ordering system might choose to **rehost the web VM** in 2 months to exit a data center, **replatform PostgreSQL to Cloud SQL** over the following 3 months, and **refactor the email module to Pub/Sub/Cloud Run** once stable. Using different strategies per component is normal; align on the target end-state architecture and avoid prolonging hybrid operation unnecessarily.

## 13. Cutover, RTO/RPO, and Rollback

### 13.1. Preparing the Cutover Runbook

Each runbook requires:

- Scope of apps/VMs/databases, owners, and cutover date.
- Change window, go/no-go approvers, and incident communication channel.
- Freeze policy, source of truth, and write volume during transition.
- How to measure replication/CDC lag and verify the last applied position.
- Steps to switch DNS/traffic/routers/connection strings.
- Smoke tests and critical business transactions.
- Rollback criteria, point of no return, and authorized decision-makers.
- Backup/restore verification, expected RTO/RPO, and handling of new writes on the target.

### 13.2. Data Is the Hardest Part to Roll Back

Rolling back web service infrastructure is usually far easier than rolling back a **database that has accepted new writes**. After cutover, if users have written to the target database, shifting traffic back to the source without reverse sync can lose transactions or create split-brain.

Approach:

1. Before cutover: keep source as primary, target as read-only replica, and validate.
2. At cutover: quiesce writes / place app in maintenance per approved RPO.
3. Wait for replication catch-up and verify checkpoints.
4. Switch endpoints/secrets/routers so only one valid writer exists.
5. Shift traffic via canary or wave while monitoring validation checks.
6. After cutover: never blindly "roll back DNS" once new writes exist; use forward-fix, pre-designed reverse replication, or data reconciliation.

For systems without dual-write reconciliation, explicitly define the **rollback window** and **point of no return**. Near-zero RPO requires proper DB replication/transaction strategies, never just VM snapshots.

### 13.3. DNS and Traffic

Lowering DNS TTL before cutover only reduces cache duration in resolvers that honor TTL; it does not produce instant network-wide switching. For multi-endpoint apps, test health probes, session stickiness, connection draining, client retries, and cached IPs. For microservices, load balancers/ingress can shift canary traffic and roll back revisions if data compatibility allows.

## 14. Validation: Don't Just Check "Does the VM Boot?"

A successful migration must satisfy **functional equivalence**, security posture, SLOs, and operability.

### 14.1. Layered Verification

| Layer | Required Evidence |
|---|---|
| Infrastructure | VM/container ready, disks, IPs, DNS, quotas |
| Identity | IAM/service accounts, secrets, directories, RBAC |
| Network | Routes/firewalls, TLS, private connectivity, latency |
| Data | Row counts, checksums/sampling, sequences/constraints, CDC lag |
| Function | Business workflows, integration/contract tests |
| Performance | p50/p95/p99, error rates, throughput, CPU/RAM/IOPS |
| Reliability | HA/failover, backup restores, RTO/RPO drills |
| Security | Audit logging, vulnerability scans, encryption, policies |
| Operations | Dashboards, alerts, SRE runbooks, incident access |
| Economics | Daily cost run-rate, dual-run costs, budget owner |

Matching row counts **are not sufficient** to prove data correctness; rows can be simultaneously missing and extra. Use partitioned hashes, checksums/canonical comparisons, business reconciliation, and transaction semantics checks—especially after DB engine conversions.

### 14.2. Pre-Defined Success Criteria

Example for an ordering API:

- 100% of critical business acceptance tests pass.
- p99 latency stays within the approved baseline/SLO during peak hours.
- Error rate remains within the allowed error budget.
- Zero lost database transactions per committed RPO; replication validated.
- Backup restore has been rehearsed, not merely reported as a green backup job.
- IAM is no broader than target policy; critical vulnerabilities are remediated.
- Rollback/forward-fix decision criteria and on-call incident owner are active.

Never invent thresholds for an application lacking a baseline. Derive them from product SLOs, compliance mandates, and concrete commercial requirements.

## 15. Case Study 1: Vendor ERP Without Source Code

**Source:** An ERP application running on VMware Windows VMs; the vendor supplies MSIs and backup instructions, and licensing is tied to OS/hypervisor. The customer must exit the data center before contract expiration.

**Assessment:**

- Without code access, refactoring is infeasible in the short term.
- Check vendor support on Compute Engine / Google Cloud VMware Engine.
- Check Windows licensing, domain controllers, SQL Server edition, and network ports.
- If Migrate to VMs supports the OS/source, pilot a test clone and performance test.
- If the VMware stack must stay intact, evaluate VMware Engine and model long-term total cost.

**Preliminary strategy:** controlled rehost/relocate, followed by rightsizing and evaluating replatforming if the vendor later allows it. Never force a vendor ERP onto Cloud Run just to look "serverless."

**Acceptance:** login/SSO, accounting close reports, printing, import/export, partner integrations, backup/restore, and license compliance all pass.

## 16. Case Study 2: Java REST API and PostgreSQL on Two VMs

**Source:** A Spring Boot API on a Linux VM and self-managed PostgreSQL on another VM, with traffic varying hourly. The team owns the source code and integration tests, but spends heavy effort patching the OS and DB.

**Option A - Rehost:** move both VMs to Compute Engine using Migrate to VMs. Pros: fast, minimal code changes. Cons: still manages database/OS and pays for idle capacity.

**Option B - Replatform:** migrate PostgreSQL via DMS to Cloud SQL for PostgreSQL; containerize the API and deploy on Cloud Run. Requirements:

- Verify PostgreSQL extensions/versions/roles and replication permissions.
- Provision Cloud SQL instance, HA/backups/PITR, and private connectivity.
- Move config files/credentials to environment variables and Secret Manager.
- Externalize local sessions if any; check Cloud Run request timeouts/ports.
- Tune HikariCP pool sizing against max instances; use Cloud SQL connector or appropriate private path.
- Test peak traffic, cutover lag, and data rollback policy.

**Option C - Refactor:** add Pub/Sub and dedicated workers for PDF/email generation, extracting a bounded context that scales independently. Pursue this only once bottlenecks/value are proven and idempotency tests exist.

**Sample choice:** Option B if DMS and Cloud Run are compatible; Option C incrementally once the replatformed system stabilizes. Avoid bundling DB migration, containerization, and event-driven rewrites into a single cutover if doing so pushes risk beyond control.

### 16.1. Example Cloud Run Configuration for the API

~~~bash
gcloud run deploy orders-api \
  --image="REGION-docker.pkg.dev/PROJECT_ID/apps/orders-api:VERSION" \
  --region="REGION" \
  --service-account="orders-api-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --memory="1Gi" \
  --cpu="1" \
  --concurrency="40" \
  --max-instances="20"
~~~

This is an **illustrative example only**. Before running in reality, replace placeholders and verify images, permissions, ingress/IAM, Cloud SQL connectivity, secrets, regions, and quotas. Never pass `--allow-unauthenticated` if the API requires authentication. Concurrency, CPU/memory, and max instances must be sized from real load tests; never treat sample values as production defaults.

### 16.2. Connection Pool Sizing

If Cloud Run `max-instances` is 20 and each instance opens up to 10 DB connections, the API alone can open roughly 200 connections, excluding other services. Size total pools against Cloud SQL max connections and peak demand so Cloud Run autoscaling does not accidentally exhaust database connections.

## 17. Case Study 3: Reporting Monolith and File-Processing Batch

**Source:** A Java monolith runs a nightly cron job reading tens of GB of CSV files, updating PostgreSQL, and generating reports. Long batch runs often starve the web API of CPU.

**Rehost:** move the VM and keep cron as-is—suitable under tight deadlines.

**Replatform:** extract the cron job into a Cloud Run Job, move source files to Cloud Storage, and move the database to Cloud SQL while keeping most Java transformation logic intact.

**Refactor:** when volume and analytics demand justify it, build a Pub/Sub/Dataflow pipeline feeding BigQuery for aggregations, while business APIs query published read models. Design retries/idempotency, checkpoints, schema validation, and late-data handling. Never assume BigQuery replaces OLTP transactions in all cases.

**Decision:** measure data volume, completion deadlines, job parallelism, I/O/egress, transformation effort, and consistency needs. If the batch finishes in minutes overnight, a Cloud Run Job may suffice; Dataflow is justified only when data scale and computation warrant the extra operational complexity.

## 18. Practicing the Migration Decision Record

An Architecture Decision Record (ADR) prevents strategy shifts driven by personal opinion or unverified assumptions.

### 18.1. Workload Classification YAML Template

~~~yaml
workload:
  id: order-api
  owner: team-commerce
  criticality: high
  source:
    compute: linux-vm
    database: postgresql-self-managed
    dependencies:
      - identity-provider
      - payment-gateway
  requirements:
    availability_slo: "defined-by-product-team"
    p99_latency_slo: "defined-by-product-team"
    rto: "approved-target"
    rpo: "approved-target"
    data_residency: "approved-regions"
  options:
    rehost:
      target: compute-engine
      risk: operating-system-and-database-toil
    replatform:
      target: cloud-run-and-cloud-sql
      risk: database-compatibility-and-cutover
    refactor:
      target: cloud-run-services-and-pubsub
      risk: distributed-consistency-and-delivery
  selected: replatform
  assumptions:
    - supported-postgresql-version
    - app-is-stateless-or-session-can-be-externalized
  gates:
    - dms-compatibility-verified
    - private-connectivity-tested
    - load-tests-pass
    - replication-lag-within-rpo
    - rollback-runbook-approved
~~~

Values like `defined-by-product-team` and `approved-target` must be replaced with actual SLOs/RTO/RPO before migration approval. The file above is a **documentation template**, not a Terraform config or an executable deployment manifest.

### 18.2. 90-Minute Workshop Agenda

1. **15 min - Outcome:** align on business drivers, deadlines, RTO/RPO, compliance, and cost targets.
2. **20 min - Inventory:** review dependency graph, runtimes/DBs, traffic, and bottlenecks.
3. **20 min - Options:** populate rehost, replatform, refactor, and retain/retire/repurchase as applicable.
4. **15 min - Risks:** eliminate options violating hard constraints; log unverified assumptions.
5. **10 min - Validation:** define PoCs, tests, and go/no-go gates.
6. **10 min - Decision:** select direction, owner, wave, budget, and re-evaluation date.

If critical facts such as license support or real RPO remain missing after the workshop, mark **DECISION_PENDING** with an owner to verify them. Never mark an option approved without evidence.

## 19. Anti-Patterns to Avoid

1. **Trend-driven target selection:** forcing every app onto GKE/microservices when Cloud Run or a VM suffices.
2. **Equating replatform with zero code/config changes:** managed runtimes still require config, secret, filesystem, networking, and health-check updates.
3. **Assuming VM disk replication guarantees transactional DB consistency:** high-write databases require engine-specific plans.
4. **Big-bang migration:** moving everything at once without pilots, waves, or rollback paths.
5. **Skipping dependency discovery:** leaving DNS/LDAP/databases or partner APIs on-premises and suffering latency spikes.
6. **Overprovisioning VMs:** copying physical/legacy sizing without measuring actual utilization.
7. **Changing DB engines without dialect/extension testing:** business-logic bugs surface only after cutover.
8. **Uncontrolled concurrent old and new writers:** causes split-brain, divergent data, and missed RPO.
9. **Ignoring vendor licensing:** technically successful migration that is non-compliant or unsupported.
10. **No post-migration optimization:** rehosting and then neglecting patching, DR, FinOps, and rightsizing.
11. **Treating "it deploys" as "production ready":** lacking SLOs, HA, restore tests, and alerting.
12. **Decommissioning source too early:** eliminating rollback options before stability and data reconciliation.
13. **Using shared Editor service accounts:** expands blast radius and breaks auditability.
14. **Omitting double-run costs:** causes migration budgets to overrun.
15. **Big refactor with no test coverage:** makes it impossible to isolate migration bugs from rewrite bugs.

## 20. Pre-Strategy-Lock Checklist

### Discovery and Design

- [ ] Workload owner, business criticality, deadline, and scope are clear.
- [ ] Inventory covers VMs/OS/runtime/database/storage/identity/networking.
- [ ] Dependency graph exists with hard/soft/batch classifications.
- [ ] Baseline traffic, p99, CPU/RAM/IOPS, database lag, and costs are measured.
- [ ] Licensing/vendor support and data residency are verified.
- [ ] Rehost/replatform/refactor options are evaluated alongside retain/retire/repurchase.
- [ ] Hard constraints, risks, assumptions, and target architecture are documented.

### GCP Compatibility

- [ ] Source/OS/disk/region are supported by Migrate to Virtual Machines if used.
- [ ] Database source/destination/version/extensions are supported by DMS or alternative plan.
- [ ] Compute Engine/Cloud Run/GKE fit the workload and OS-control needs.
- [ ] Landing zone, billing, IAM, VPC, private DNS, and VPN/Interconnect are ready.
- [ ] Projects and resource identities separate staging/prod; secrets, KMS, and firewalls comply with policy.
- [ ] Quotas, machine availability, managed service regions, and costs are checked.

### Migration and Cutover

- [ ] Waves and pilot have owners, schedules, and playbooks.
- [ ] Realistic or production-like test data and environments exist.
- [ ] Test clones, database migrations, networking, and cutover have been rehearsed.
- [ ] Validation covers data integrity, business workflows, p99, and error rates.
- [ ] Go/no-go gates, rollback plan, point of no return, and RTO/RPO are clear.
- [ ] Single-writer enforcement at cutover time is established.
- [ ] Post-cutover alerts/logs/traces/backup/restore and incident response are ready.
- [ ] Source decommissioning and post-stabilization cost reconciliation plans exist.

## 21. Official References

- [Google Cloud Architecture Center - Migrate to Google Cloud: Get started](https://cloud.google.com/architecture/migration-to-gcp-getting-started)
- [Migration and modernization overview](https://cloud.google.com/docs/migration/overview/migrate-modernize-overview)
- [Migration Center documentation](https://cloud.google.com/migration-center/docs)
- [Migrate to Virtual Machines documentation](https://cloud.google.com/migrate/virtual-machines/docs/5.0)
- [Migrate to Virtual Machines - Architecture](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/architecture)
- [Migrate to Virtual Machines - VM migration lifecycle](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/lifecycle)
- [Migrate to Virtual Machines - Supported operating systems](https://cloud.google.com/migrate/virtual-machines/docs/5.0/discover/supported-os-versions)
- [Google Cloud VMware Engine documentation](https://cloud.google.com/vmware-engine/docs)
- [Database Migration Service - Supported source and destination databases](https://cloud.google.com/database-migration/docs/supported-databases)
- [Database Migration Service documentation](https://cloud.google.com/database-migration/docs)
- [Cloud SQL documentation](https://cloud.google.com/sql/docs)
- [AlloyDB documentation](https://cloud.google.com/alloydb/docs)
- [Cloud Run documentation](https://cloud.google.com/run/docs)
- [Google Kubernetes Engine documentation](https://cloud.google.com/kubernetes-engine/docs)
- [Cloud VPN documentation](https://cloud.google.com/network-connectivity/docs/vpn)
- [Cloud Interconnect documentation](https://cloud.google.com/network-connectivity/docs/interconnect)
- [Cloud Architecture Framework - Reliability](https://cloud.google.com/architecture/framework/reliability)
- [Cloud Architecture Framework - Cost optimization](https://cloud.google.com/architecture/framework/cost-optimization)

## 22. Summary

**Rehost** fits when you need low-change migration, face source-code constraints, or have tight deadlines; **replatform** fits when core business logic is sound and you want lower operational toil via managed databases and runtimes; **refactor** fits when scaling, reliability, or release velocity demands architectural change and the organization has the testing and distributed-operations maturity to support it.

A single workload can progress through multiple strategies over time. A sound decision requires **clear inventory and dependencies, confirmed hard constraints, measurable TCO and SLOs, tested and rehearsed migration waves, safe data cutover, and a bounded rollback plan**. Google Cloud provides the services and tooling to execute these paths; choosing the right route and proving the outcome remain the responsibility of architecture, product, and operations teams.
