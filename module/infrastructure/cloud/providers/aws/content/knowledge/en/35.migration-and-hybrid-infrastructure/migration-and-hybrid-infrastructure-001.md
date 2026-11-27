# System Assessment and Migration Strategy Selection

Migrating a system to AWS is an architectural, operational, cost, and business decision. Before choosing Amazon EC2, Amazon RDS, or another managed service, an organization needs to understand which applications it operates, what those applications depend on, who uses them, where the data resides, what the actual load looks like, and what happens if cutover fails.

A migration assessment turns fragmented data about servers, databases, networks, software, and operational processes into an actionable workload portfolio. The output is not just a server list. It must answer: which workloads should move, which should be retained or retired, which of the 7 Rs strategy applies, what the appropriate target architecture is, what the costs and risks look like, and which wave each workload belongs to.

This lesson belongs to the **Migration and Hybrid Infrastructure** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects AWS Application Discovery Service, AWS Migration Hub, AWS Transform, Migration Evaluator, AWS Application Migration Service (MGN), AWS Database Migration Service (DMS), AWS DataSync, AWS Snow Family, AWS Direct Connect, AWS Site-to-Site VPN, and target AWS services.

> **Key principle:** Never choose a migration tool before understanding the workload. A server with low CPU utilization can still be a critical component of a payment system; a small database can still have dozens of consumers; a rarely used application may be retired rather than migrated at unnecessary cost.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain the purpose and scope of a migration assessment.
2. Build an inventory for applications, servers, databases, storage, network, licenses, and ownership.
3. Distinguish static configuration discovery from utilization metrics and dependency mapping.
4. Use AWS Application Discovery Service, Migration Hub, and AWS Transform in their proper roles.
5. Identify business drivers, technical constraints, compliance requirements, and migration readiness.
6. Evaluate application dependencies and group workloads into dependency groups.
7. Interpret CPU, memory, disk IOPS, throughput, and network utilization to right-size target resources.
8. Estimate TCO, migration cost, operational cost, and build a business case.
9. Distinguish the seven migration strategies: retire, retain, rehost, relocate, repurchase, replatform, and refactor.
10. Select target AWS services for compute, database, storage, network, and integration.
11. Distinguish AWS Application Migration Service (MGN) from AWS Elastic Disaster Recovery (DRS).
12. Choose DMS, DataSync, Transfer Family, or Snow Family for data movement.
13. Build migration waves, a cutover plan, and a rollback plan.
14. Define landing zone, security, network, and operational readiness.
15. Design a proof of concept (PoC), pilot, and acceptance criteria.
16. Establish deliverables and governance for a migration assessment.

## 2. Migration Assessment Starts with Business Goals

### 2.1. Identify Business Drivers

Do not start by asking "which server moves first?". Start with why the organization needs to change:

- **Data center exit:** expiring lease contracts, end-of-life hardware, or a requirement to close a data center.
- **Cost optimization:** reducing facility, licensing, operations, and infrastructure maintenance costs.
- **Resilience:** improving availability, backup, disaster recovery, and recoverability.
- **Agility:** shortening provisioning and application release lead times.
- **Modernization:** moving to managed databases, containers, serverless, or event-driven architectures.
- **Global expansion:** deploying applications closer to users across multiple Regions.
- **Compliance:** meeting data residency, audit, encryption, retention, and regulatory requirements.
- **M&A / divestiture:** consolidating or separating systems after a merger or acquisition.
- **Technology refresh:** replacing unsupported OS, database engine, middleware, or runtime versions.

Every driver must be translated into measurable outcomes. For example: exit the data center before lease expiration; reduce infrastructure costs by 25% within 12 months; achieve a 2-hour RTO; or reduce environment provisioning time from 10 days to 30 minutes.

### 2.2. Define Scope and Boundaries

The scope must clearly define:

| Dimension | Questions to Answer |
|---|---|
| Organization | Which business units, subsidiaries, and legal entities are involved? |
| Locations | Which data centers, colocation facilities, branch offices, and cloud accounts are in scope? |
| Applications | Which applications/services require assessment? |
| Infrastructure | Which physical servers, VMs, containers, appliances, and network devices are involved? |
| Data | Which databases, file shares, object storage, backups, and archives need to move? |
| Environments | Are production, staging, development, DR, and sandbox environments included? |
| Time | What are the deadlines, maintenance windows, blackout periods, and contract expirations? |
| Exclusions | Which systems are excluded from migration and why? |

Clearly define workload boundaries to avoid overlooking components outside the data center such as SaaS, DNS providers, identity providers, payment gateways, partner APIs, backup vaults, and license servers.

### 2.3. Classify Business Criticality

Use business criticality to prioritize discovery and design:

| Tier | Characteristics | Illustrative Examples |
|---|---|---|
| Tier 0 / Mission critical | Service outage severely impacts safety, revenue, or the entire enterprise | Payment core, identity, production ERP |
| Tier 1 / Critical | Directly impacts core business operations | Order management, customer portal |
| Tier 2 / Important | Short-term workarounds are acceptable | Reporting, internal workflows |
| Tier 3 / Non-critical | Can be deferred or retired | Legacy test server, temporary utility |

Do not infer criticality from CPU usage or login counts. Business owners must confirm impact, RTO/RPO, peak seasons, support hours, and acceptable downtime.

## 3. Collecting Inventory and Discovery Data

### 3.1. Build the Application Portfolio

Each application should have a unique identifier record and minimum baseline attributes:

| Data Group | Fields to Collect |
|---|---|
| Identity | Application ID, name, description, business unit, owner, technical contact |
| Business | Criticality, users, business process, revenue impact, SLA/SLO |
| Lifecycle | Vendor, version, support end date, license, contract renewal |
| Architecture | Runtime, OS, middleware, database, protocol, deployment model |
| Infrastructure | Server IDs, vCPU, RAM, disks, storage, hypervisor, network interfaces |
| Performance | CPU/memory percentiles, IOPS, throughput, latency, network utilization |
| Dependencies | Upstream/downstream applications, databases, DNS, AD, queues, external APIs |
| Security | Data classification, encryption, identity, vulnerabilities, access patterns |
| Operations | Monitoring, backup, patching, deployment, incident and change processes |
| Migration | Candidate 7R, target service, complexity, blockers, wave, downtime window |

Do not use hostname as an application ID. Hostnames can change, collide across environments, or be reused. Use a stable identifier and maintain mappings across the CMDB, discovery tools, cloud resource tags, and migration tracker.

### 3.2. Server and Infrastructure Inventory

Collect both static configuration and time-series utilization:

- CPU architecture, sockets, cores, vCPUs, and hypervisor allocation.
- Installed, used, and available memory, swap/pagefile, and memory pressure.
- Disk count, capacity, filesystem, free space, IOPS, read/write throughput, and latency.
- Network interfaces, IPs, VLAN/subnets, routes, firewall rules, bandwidth, and TCP connections.
- OS distribution/version, kernel, patch level, boot mode, and end-of-support date.
- Hypervisor, VM cluster, host affinity, HA/DR configuration, and licensing.
- Hardware appliances, HSMs, GPUs, dongles, serial devices, or specialized dependencies.

Collect peaks and percentiles, not just averages. A 10% average CPU can hide a 95% peak during a batch window. Memory pressure, disk latency, and network bursts can also determine the right EC2 instance family or storage class.

### 3.3. Database Inventory

For each database, record:

- Engine, edition, version, patch level, and license model.
- Database size, growth rate, table count, index size, LOBs, partitions, and schemas.
- Transaction rate, peak connections, read/write ratio, and query latency.
- Backup method, log retention, recovery model, and replication topology.
- Extensions, stored procedures, triggers, jobs, linked servers, and external integrations.
- Character set, collation, time zone, data types, and compatibility requirements.
- RPO/RTO, downtime allowance, and data consistency requirements.

Note especially that database migration is not just copying rows. Systems may rely on stored procedures, jobs, sequences, extensions, secondary indexes, foreign keys, grants, and application connection strings. AWS DMS can migrate data and support certain schema operations, but it does not automatically migrate every object or permission across all engine paths.

### 3.4. Application Dependency Mapping

An application may depend on:

- Identity: Active Directory, LDAP, IAM Identity Center, SAML/OIDC providers.
- Name resolution: DNS, private hosted zones, service discovery.
- Data: RDBMS, NoSQL, file shares, object storage, caches.
- Integration: MQ, Kafka, SMTP, FTP/SFTP, REST/SOAP APIs, payment gateways.
- Infrastructure: NTP, PKI/CA, HSM, license servers, proxies, firewalls.
- Operations: monitoring, logging, backup, vulnerability scanners, deployment agents.

A dependency map should capture call direction, protocol/port, frequency, criticality, and owner. An observed TCP connection does not automatically prove a business dependency; verify it against application owners, configurations, logs, and tracing.

### 3.5. Distinguishing Static Inventory from Utilization Data

| Data Type | Examples | Used For |
|---|---|---|
| Static configuration | 8 vCPU, 32 GiB RAM, 2 TB disk, OS version | Compatibility checks and baseline capacity |
| Utilization time series | CPU p95, memory peak, IOPS, throughput | Right-sizing and performance planning |
| Network connections | Source/destination IP, port, process, timestamp | Dependency discovery and network design |
| Business metadata | Owner, criticality, SLA, license, cost center | 7R selection, prioritization, and governance |
| Application behavior | Request rate, latency, error rate, transaction volume | Target architecture design and acceptance criteria |

Utilization should be collected over a representative cycle, typically at least 2–4 weeks; workloads with seasonal peaks or quarter-end processing require a longer window. Taking only a snapshot on a quiet day can result in under-provisioned capacity during peaks.



## 4. AWS Discovery and Assessment Tools

### 4.1. AWS Application Discovery Service

AWS Application Discovery Service collects configuration and utilization data from on-premises servers and databases to support migration planning. Discovery data integrates with AWS Migration Hub and AWS DMS Fleet Advisor.

There are two primary collection methods:

| Method | How It Works | Best Suited When |
|---|---|---|
| Agentless Collector | Collector deployed in a VMware/vCenter environment to gather server profiles, utilization, and TCP network connections from the hypervisor | You want to discover many VMware VMs without installing an agent on each VM |
| Discovery Agent | Agent installed on individual physical/virtual servers to gather server profiles, utilization, processes, and network connections | You need detailed OS/process-level data or servers are outside a supported VMware vCenter |

Agentless Collector is suitable for quickly starting VMware inventory. Discovery Agent provides deeper process and connection detail. You can combine multiple sources such as CMDB exports, vCenter inventory, RVTools, and independently collected data; standardize identities before merging to avoid duplicate servers.

### 4.2. AWS Migration Hub

AWS Migration Hub provides a centralized view for tracking migration status and consolidating discovery/application groups from integrated tools. Before running discovery, you must set the Migration Hub home Region. Migration Hub discovery and tracking data is stored in that home Region.

Migration Hub helps you:

- View discovered inventory.
- Group servers into applications.
- Inspect network connections and application dependencies from discovery data.
- View EC2 recommendations/target suggestions when supported by the data source.
- Track migration status across integrated tools.

Migration Hub provides tracking and orchestration visibility; it does not replace an inventory owner, business case, or runbook. Maintain a migration tracker with agreed owners, waves, risks, targets, statuses, and cutover dates.

### 4.3. AWS Transform

AWS Transform is an agentic AI-powered workbench for migration and modernization. For server migrations, AWS Transform can assist with discovery, application grouping, dependency mapping, migration wave planning, landing zone creation, network migration, and server rehosting from supported environments such as VMware, Hyper-V, and physical/bare-metal servers.

AWS Transform assessments can analyze inventory to build a business case/TCO, evaluate feasibility and business value, suggest target AWS services, licensing options, and cost scenarios. Users can adjust assumptions, supplement inventory, and compare what-if scenarios.

Useful capabilities include:

- Recommending 7R strategies per server/application based on OS, utilization, and workload signals.
- Suggesting target services along with rationale and confidence levels.
- Grouping applications and sequencing dependency-aware migration waves.
- Assisting with translating network configurations into VPC designs.
- Generating deliverables for assessment and migration planning.

AI recommendations are inputs for specialist review, not automated decisions. Verify inventory completeness, confidence scores, business context, licensing, compliance, and real dependencies before approval.

### 4.4. Migration Evaluator and Supplementary Data Sources

Migration Evaluator helps build a business case/TCO from server inventory and utilization data, comparing on-premises costs against AWS. Organizations can supplement data from CMDBs, vCenter, Hyper-V, monitoring tools, and license records.

You can leverage:

- CMDB/asset management exports.
- VMware vCenter, RVTools, and Hyper-V inventory.
- AWS Application Discovery Service.
- AWS Transform assessments.
- AWS DMS Fleet Advisor / database metadata.
- Performance monitoring, APM, and logging systems.
- Network flow logs, firewall logs, and NetFlow.
- Procurement, facility, software licensing, and support invoices.

Never treat a single discovery tool as the sole source of truth. Cross-check server counts, CPU/memory, application owners, network connections, and database inventory against other source systems.

### 4.5. Controlled Discovery Process

1. Finalize the Migration Hub home Region, AWS accounts, and permissions.
2. Identify data owners, security approvals, and retention requirements.
3. Choose Agentless Collector, Discovery Agent, or inventory import based on the source environment.
4. Collect static configuration and utilization over a representative period.
5. Collect network connections and running processes when needed for dependency mapping.
6. Standardize hostnames, IPs, server IDs, application IDs, and timestamps.
7. Group servers into an application portfolio.
8. Interview business/application owners to validate dependencies.
9. Flag missing data, stale records, unknown owners, and unsupported systems.
10. Lock a discovery baseline with snapshot date and data confidence score.

Discovery agents/collectors can read sensitive system and network details. Deploy them under least privilege, change management, and security review. Define what data is sent to AWS, who can access it, the home Region, and the retention policy before collecting data.

## 5. Assessing Migratability and Readiness

### 5.1. Technical Readiness

Evaluate each application across the following areas:

| Category | Assessment Questions |
|---|---|
| OS/runtime | Are the OS, kernel, runtime, and middleware supported on the target? |
| Compute | Are CPU architecture, memory, GPU, special hardware, and licenses compatible? |
| Storage | Can block/file/object storage, IOPS, throughput, latency, and shared filesystem semantics be met? |
| Database | Are engine/version, extensions, schema, transaction rate, and CDC supported? |
| Network | Are IPs, CIDRs, routing, firewalls, DNS, latency, and bandwidth suitable? |
| Identity | How will AD/LDAP, Kerberos, SAML/OIDC, service accounts, and secrets operate? |
| Integration | Can external APIs, MQ, SMTP, SFTP, partner allowlists, and certificates be updated? |
| Security | Are data classification, encryption, keys, vulnerability management, and audit controls satisfied? |
| Operations | Are monitoring, patching, backup, deployment, incident response, and on-call ready? |
| Licensing | Do BYOL, license-included, core restrictions, mobility, and vendor support allow it? |

Compatibility assessment is more than checking whether EC2 runs a given OS. An application might rely on kernel drivers, USB/HSM devices, multicast, MAC addresses, static IPs, hardware-bound licenses, or appliance-specific behavior unsupported in the target cloud.

### 5.2. Business Readiness

Verify that:

- The business sponsor and application owner have signed off on scope.
- Business criticality, RTO/RPO, and downtime windows are approved.
- End users, partners, and vendors have been notified.
- Compliance and data residency have been reviewed.
- Contracts, licenses, support, and vendor certifications are verified.
- Training plans, operating model, and service ownership are in place.
- Budget, funding, and chargeback/showback are approved.
- Communication plans, change approvals, and hypercare are defined.

### 5.3. Migration Readiness Scorecard

A 0–3 scale can be used:

| Score | Meaning |
|---:|---|
| 0 | Unknown / no data available |
| 1 | Data exists but is unverified or has major blockers |
| 2 | Verified, with remediation plan and assigned owner |
| 3 | Tested / meets acceptance criteria |

Score inventory, dependencies, target architecture, networking, security, data migration, licensing, operations, testing, and cutover separately. Do not use an average score to hide a critical blocker. For example, network readiness = 3 with license legality = 0 is still a no-go.

### 5.4. Classifying Complexity and Risk

Assess complexity based on dependency count, data volume, downtime tolerance, database heterogeneity, OS support, external integrations, license constraints, and customization level. Classify as Low/Medium/High/Very High with supporting evidence.

Risks must have an owner, likelihood, impact, mitigation, and due date. Common risks include:

- Missing application owner or unsupported vendor software.
- Incomplete dependency map.
- End-of-support OS or database versions.
- Data volume or write rate exceeding available bandwidth or cutover window.
- Non-transferable licenses or physical-core-based licensing.
- IP/DNS changes breaking partner allowlists.
- Missing owners for encryption keys, certificates, or secrets.
- Insufficient quotas or EC2 capacity in the target account/Region.
- Untested backup/restore and rollback procedures.
- No operations team ready to run the target platform.

## 6. Business Case and Total Cost of Ownership (TCO)

### 6.1. On-Premises Costs

Do not just sum server hardware prices. On-premises TCO typically includes:

- Server, storage, and network hardware plus refresh cycles.
- Data center rack/space, power, cooling, and physical security.
- Hypervisor, OS, database, middleware, and application licenses.
- Maintenance, support contracts, spare parts, and warranties.
- Backup, DR site, replication links, and tape/archive systems.
- Network circuits, firewalls, load balancers, and security appliances.
- IT operations labor, patching, monitoring, and incident management.
- Migration project costs, downtime, vendor consulting, and decommissioning.

Allocate costs per application/service rather than dividing evenly by server count. Shared storage, networking, database clusters, and license pools can make cost allocation complex.

### 6.2. Post-Migration AWS Costs

Estimate costs based on target architecture and usage profile:

- EC2 instance hours, and Savings Plans / Reserved Instances / Spot where appropriate.
- EBS volumes, snapshots, provisioned IOPS, and throughput.
- S3 storage classes, requests, retrieval, and data transfer.
- RDS/Aurora/other database compute, storage, I/O, backups, and Multi-AZ.
- ECS/EKS/Lambda and supporting services.
- Load balancers, NAT Gateway, Transit Gateway, Route 53, and Direct Connect.
- CloudWatch metrics/logs, CloudTrail, Config, Security Hub, and GuardDuty.
- KMS, Secrets Manager, Systems Manager, and backup services.
- Data transfer out, inter-AZ/inter-Region traffic, and internet egress.
- Support plans, AWS Marketplace software, licensing, and managed services.

Model multiple scenarios: conservative, expected, and growth. Do not price peak capacity for every hour if the workload can scale; likewise, do not use the lowest average as the baseline if peak demand must be served.

### 6.3. Migration and Transition Costs

Beyond ongoing AWS run costs, budget for:

- Discovery tool/collector deployment and assessment effort.
- Replication/transfer services, temporary storage, and data transfer.
- Migration tooling, conversion, refactoring, and testing.
- Parallel run: operating both on-premises and AWS simultaneously.
- Cutover weekend/overtime labor, vendor support, and business downtime.
- Training, operating model changes, and new skill enablement.
- Data reconciliation, audit evidence, and compliance sign-off.
- Decommissioning, secure wiping, contract termination, and facility exit.
- Contingency for rollbacks, rework, and migration wave delays.

### 6.4. Comparing TCO and Business Value

A simple model:

\[
TCO_{3y} = C_{migration} + \sum_{y=1}^{3}(C_{run,y} + C_{license,y} + C_{support,y})
\]

Net benefit:

\[
Benefit_{3y} = TCO_{on\text{-}prem,3y} - TCO_{AWS,3y}
\]

Payback period can be estimated as:

\[
Payback = \frac{C_{one\text{-}time\ migration}}{Annual\ net\ savings}
\]

These formulas are only a modeling framework. You must factor in discount rates, price changes, reserved capacity, utilization, growth, currency, taxes, downtime risk, and residual value. A migration with a higher TCO may still be justified if it improves resilience, time-to-market, compliance, or reduces data center exit risk.

### 6.5. Right-Sizing

Right-sizing is driven by utilization and application behavior:

- Select EC2 instance families based on CPU, memory, network, storage, and accelerator needs.
- Compute Optimized fits CPU-bound workloads; Memory Optimized fits in-memory/cache/databases; Storage Optimized fits high IOPS/throughput; General Purpose fits balanced workloads.
- Graviton/ARM can improve price-performance, but requires verifying OS, runtime, native libraries, and vendor support.
- Managed databases reduce operational overhead, though licensing, I/O, or Multi-AZ costs may increase.
- Auto Scaling, scheduled scaling, and serverless fit variable workloads.
- Choose EBS volume types and provisioned IOPS based on measured latency/throughput, not capacity alone.

Do not right-size from a single snapshot. Use p50/p95/p99 metrics, peak windows, memory pressure, disk latency, and concurrency. Retain headroom aligned with SLAs and real scaling capabilities.



## 7. The Seven Migration Strategies (7 Rs)

The 7 Rs provide a decision classification framework for each application/workload. Different components within a single application can use different strategies; do not force an entire portfolio into one approach.

| Strategy | Meaning | When Appropriate | Example |
|---|---|---|---|
| **Retire** | Decommission applications that no longer deliver value | No remaining business owner/users; redundant functionality; cost/risk of keeping exceeds value | Shutting down a replaced legacy reporting server |
| **Retain** | Keep in the current location or defer migration | Compliance, latency, hardware, or contract constraints, or not yet ready | Keeping an HSM/OT workload on-site |
| **Rehost** | Move workloads as-is to the cloud (lift and shift) | Need to exit data center quickly with minimal app changes; defer modernization | Migrating a VM to EC2 |
| **Relocate** | Move a workload/stack to a compatible cloud platform with minimal architectural change | Need to preserve current virtualization/stack closely | Moving a VMware stack to a compatible cloud VMware service while supported |
| **Repurchase** | Replace an existing application with another product/SaaS | SaaS meets business capabilities and reduces self-managed overhead | Replacing a self-hosted CRM with a SaaS CRM |
| **Replatform** | Move workloads with limited cloud optimization | Can adopt managed services without rewriting the entire application | Moving SQL Server on a VM to Amazon RDS for SQL Server |
| **Refactor / Re-architect** | Redesign applications to leverage cloud-native capabilities | Need major agility, scale, resilience, or product architecture changes | Re-architecting a monolith into microservices on ECS/EKS |

### 7.1. Retire

Retire is often the biggest cost saver when an application is no longer used. Before shutting down:

- Confirm with the business owner, data owner, and legal retention requirements.
- Check integrations, scheduled jobs, reports, and downstream consumers.
- Archive data according to retention and compliance policies.
- Revoke credentials, DNS records, firewall rules, certificates, and licenses.
- Decommission servers/storage/network and update the CMDB.
- Retain approval evidence and the decommission timestamp.

Do not retire a system solely because CPU is low or there are no interactive logins. Batch jobs, backend APIs, and disaster recovery systems may have low activity yet remain critical.

### 7.2. Retain

Retain does not mean forgetting about the workload. Document the reason for retaining, the owner, review date, and conditions for re-evaluation. Examples include data residency restrictions, hardware dependencies with no cloud equivalent, or active vendor contracts. Hybrid connectivity can be designed so retained workloads connect securely with AWS.

### 7.3. Rehost

Rehost fits when speed is critical and application changes must be minimized. AWS Application Migration Service (MGN) performs block-level replication to move source servers to EC2. Rehosting reduces code change time, but it does not automatically resolve technical debt, unsupported OS versions, license restrictions, poor architecture, or overprovisioning.

### 7.4. Relocate

Relocate typically applies to a stack or virtualization environment that can move to a compatible cloud platform with minimal changes. Carefully verify support status, contracts, licensing, and target service availability at planning time. Do not confuse relocate with rehost: relocate preserves many platform/stack characteristics, whereas rehost converts individual servers into cloud instances.

### 7.5. Repurchase

Repurchase replaces a self-managed system with SaaS or a commercial product. Evaluate data export/import, API integration, identity federation, customization, data residency, exit strategy, SLA, vendor lock-in, and subscription cost. Do not compare based solely on license fees; include integration, migration, training, and process redesign costs.

### 7.6. Replatform

Replatform moves workloads to more managed target services while keeping most business logic intact. Examples:

- Self-managed MySQL on EC2 to Amazon RDS for MySQL or Aurora MySQL.
- File servers to Amazon FSx or Amazon EFS.
- VM-based application runtimes to ECS/Fargate with moderate packaging changes.
- Internal object storage to Amazon S3.
- Oracle databases to RDS for Oracle where edition, features, and licensing align.

Replatforming can reduce operational burden, but requires validating feature compatibility, extensions, performance, maintenance windows, and the target operating model.

### 7.7. Refactor / Re-architect

Refactor is appropriate when long-term benefits outweigh the cost, duration, and risk of change. This may include:

- Decomposing a monolith into services or a modular architecture.
- Replacing synchronous coupling with event-driven patterns.
- Moving batch processing to managed queues and workflows.
- Moving stateful components to managed databases and caches.
- Containerizing applications or adopting serverless.
- Designing for statelessness, horizontal scaling, and Multi-AZ resilience.

Avoid migrating and rewriting all business behavior in the same cutover unless test coverage and rollback strategies are strong. Many programs choose to rehost/replatform first and modernize on a subsequent roadmap.

## 8. Process for Selecting a Strategy per Workload

### 8.1. Decision Sequence

1. **Does it still deliver business value?** If not, evaluate Retire.
2. **Can it move within legal, licensing, and technical boundaries?** If not yet, Retain or resolve blockers first.
3. **Is there a better SaaS replacement?** If yes, evaluate Repurchase.
4. **Must the underlying platform/virtualization stack remain intact?** If yes, evaluate Relocate.
5. **Do you need to move fast with minimal change?** Evaluate Rehost.
6. **Is there a suitable managed service with limited changes?** Evaluate Replatform.
7. **Do business outcomes demand a new architecture?** Evaluate Refactor.

The decision sequence only produces a shortlist. Compare 2–3 viable options on cost, timeline, risk, downtime, skills, and future operating model.

### 8.2. Driver-Based Selection Matrix

| Primary Driver | Commonly Considered Strategies | Validation Questions |
|---|---|---|
| Tight data center exit deadline | Rehost, Relocate, Retire | Can it move as-is and is capacity available? |
| Reduce operational overhead | Replatform, Repurchase | Does the managed service/SaaS meet features and compliance? |
| Accelerate feature delivery | Refactor, Replatform | Does the team have skills and test coverage for architectural change? |
| Cannot change immediately | Retain, Rehost | Can hybrid coexistence work during the transition phase? |
| Application end-of-life | Retire, Repurchase | Do any consumers still depend on it? |
| Database modernization | Replatform, Refactor | Can the engine be changed and schema/code converted? |
| VMware stack migration | Relocate or Rehost | What are the licensing, service availability, and portability constraints? |

### 8.3. Example Portfolio Classification

| Workload | Current State | Candidate 7R | Target / Next Action |
|---|---|---|---|
| Legacy report portal | Few users, overlaps with BI SaaS | Retire / Repurchase | Confirm consumers, archive data, move report users to SaaS |
| Internal Java monolith | Linux VM, Oracle DB, clear dependencies | Rehost first, Replatform later | EC2 first; evaluate RDS/containers in modernization wave |
| CRM | Custom app, vendor SaaS has equivalent features | Repurchase | PoC integration, data export, and identity federation |
| File share | SMB, large capacity, local latency sensitive | Replatform / Retain | Compare FSx for Windows File Server vs keeping local cache |
| ERP core | Complex licensing, vendor-certified stack | Retain / Rehost / Relocate | Vendor assessment, license review, and PoC |
| Stateless API | Bursty traffic, CI/CD already exists | Refactor / Replatform | ECS/Fargate or Lambda after workload profiling |

Document the candidate strategy, final decision, rationale, approver, and review date. A tool recommendation does not replace sign-off from the application owner or architecture board.

## 9. Selecting AWS Target Services by Workload

### 9.1. Compute and Application Hosting

| Requirement | Candidate AWS Targets | Evaluation Points |
|---|---|---|
| Keep OS/application largely as-is | Amazon EC2 | OS/AMI support, instance family, licensing, EBS, and patching |
| Container orchestration | Amazon ECS or Amazon EKS | Container readiness, state, networking, registry, and platform operations |
| Serverless containers | ECS on AWS Fargate | Startup time, CPU/memory sizing, networking, and pricing |
| Event-driven short-lived functions | AWS Lambda | Runtime compatibility, execution duration, state, concurrency, and cold starts |
| Managed Java/web app platform | AWS Elastic Beanstalk or App Runner by use case | Runtime support, deployment model, network access, and operational needs |
| Batch/HPC | AWS Batch or EC2-based scheduler | Queues, placement, compute environments, and data locality |
| GPU/ML | EC2 accelerated instances or managed AI services | Drivers, frameworks, GPU memory, quotas, and cost |

Do not choose containers or serverless solely because they are cloud-native. If an application depends on kernel modules, local persistent state, or hardware-bound licenses, rehosting may be a safer first step.

### 9.2. Databases and Data Stores

| Source / Requirement | Candidate AWS Targets | Key Questions |
|---|---|---|
| Self-managed MySQL/PostgreSQL | Amazon RDS or Aurora | Extensions, replication, storage, IOPS, HA, and version compatibility |
| SQL Server | Amazon RDS for SQL Server or EC2 | Edition, features, Windows/licensing, and SQL Agent dependencies |
| Oracle | RDS for Oracle or EC2 | Options/packs, RAC, Data Guard, BYOL, and vendor certification |
| Key-value/document | DynamoDB or DocumentDB | Data model, query patterns, consistency, and application changes |
| Cache | ElastiCache for Redis/Valkey or Memcached | Persistence, clustering, failover, and client compatibility |
| Data warehouse | Amazon Redshift or analytics services | Schema, ETL, concurrency, data volume, and workload patterns |
| Databases needing specific engine/OS features | Self-managed on EC2 | DBA operations, backup, patching, HA, and licensing |

Sharing the same engine name does not guarantee full compatibility. RDS/Aurora restrict OS access, superuser privileges, certain extensions, file system access, and specific engine features. Always review engine-specific feature matrices and run schema assessments/PoCs.

### 9.3. File, Block, and Object Storage

| Data Pattern | AWS Target | Metrics to Measure |
|---|---|---|
| Block storage for EC2 | Amazon EBS | Capacity, IOPS, throughput, latency, snapshots |
| Shared Linux POSIX file system | Amazon EFS | NFS semantics, throughput mode, access points, and lifecycle |
| Shared Windows SMB | Amazon FSx for Windows File Server | AD integration, SMB version, ACLs, throughput, and HA |
| High-performance parallel file system | Amazon FSx for Lustre | HPC/AI access patterns and data repository integration |
| Object storage | Amazon S3 | Object count, size, versioning, metadata, retention, and request patterns |
| Hybrid file access | AWS Storage Gateway | Cache sizing, bandwidth, local app semantics, and gateway availability |

Do not move a file share to S3 simply because storage is cheaper. S3 object semantics differ from POSIX/SMB: locking, rename operations, partial updates, and file handle behavior can differ completely.

### 9.4. Network, Identity, and Integration

- **Amazon VPC:** CIDRs, subnets, routes, security groups, NACLs, endpoints.
- **AWS Transit Gateway:** connecting multiple VPCs and on-premises networks in a hub-and-spoke topology.
- **AWS Direct Connect:** dedicated connectivity with appropriate bandwidth/latency characteristics.
- **AWS Site-to-Site VPN:** IPsec encrypted tunnels, suitable for rapid setup or backup paths.
- **Route 53:** public/private DNS, resolver endpoints, and health-based routing.
- **AWS Directory Service / AD Connector:** identity integration depending on domain architecture.
- **AWS IAM Identity Center:** workforce access and permission sets.
- **Amazon MQ, SQS, SNS, EventBridge:** messaging and event integration.
- **AWS Secrets Manager / Systems Manager Parameter Store:** secrets and configuration management.
- **AWS Certificate Manager:** TLS certificates for supported integrations.

Every endpoint, IP, and DNS change must be inventoried and communicated to firewall owners, partners, allowlist maintainers, monitoring teams, and certificate managers.



## 10. Selecting Migration and Data Movement Tools

### 10.1. AWS Application Migration Service (MGN)

AWS Application Migration Service is a rehost tool for migrating physical, virtual, and cloud-based servers to Amazon EC2. MGN uses block-level replication to keep target servers up to date while sources continue running, then launches test instances and cutover instances.

Suitable when:

- Migrating many servers with minimal OS/application changes.
- Minimizing downtime via continuous replication.
- Testing target instances before cutover.
- Standardizing server migrations into waves.

MGN does not automatically handle application refactoring, database schema conversion, or off-server dependencies. You still need target VPCs/subnets/security groups, IAM, EC2 quotas, licensing, DNS, and application validation.

### 10.2. How Does AWS Elastic Disaster Recovery (DRS) Differ from MGN?

| Criterion | AWS MGN | AWS DRS |
|---|---|---|
| Primary goal | Migration/rehost to EC2 | Disaster recovery and failback |
| Sources | Supported physical, VM, and cloud servers | Supported physical, VM, and cloud servers |
| Replication | Block-level replication within a migration workflow | Continuous block-level replication into a staging area |
| Testing | Test launches prior to cutover | Periodic recovery drills without disrupting sources |
| Cutover | Finalize migration and operate the target | Failover during disaster; traffic cutover managed by organization |
| Failback | Not a primary DR workflow | Includes reverse replication/failback workflows |
| Use case | Data center exit, server migration | Business continuity, post-incident recovery |

Both services may use similar replication technology, but their goals and lifecycles differ. Choose by outcome: permanently moving workloads points to MGN; protecting source systems and recovering from disasters points to DRS.

### 10.3. AWS Database Migration Service (DMS)

AWS DMS supports homogeneous and heterogeneous database migrations, including full load and Change Data Capture (CDC) to minimize downtime. DMS Schema Conversion helps convert schema/code objects for supported source-target combinations.

Use DMS when:

- Migrating data between supported database engines.
- Performing a full load followed by continuous change replication up to cutover.
- Moving databases to RDS/Aurora/Redshift or other supported targets.
- Validating data consistency between source and target.

DMS does not automatically migrate the entire database ecosystem in every migration. Assess schemas, stored procedures, functions, triggers, jobs, users/grants, secondary indexes, foreign keys, unsupported data types, and application connection strings. Some schema conversions require manual remediation.

### 10.4. AWS DataSync

AWS DataSync accelerates and automates data movement between on-premises storage and AWS storage services, or between supported AWS storage locations.

Use cases:

- NFS/SMB file shares to Amazon S3, EFS, or FSx.
- Moving large file datasets with repeated incremental syncs.
- Scheduled data copying with built-in transfer verification.
- Moving data between storage systems without custom copy scripts.

DataSync is built for file/object transfer; it does not replace database replication or server block replication. Evaluate metadata, POSIX permissions, ACLs, symlinks, hard links, file count, small-file overhead, and available bandwidth.

### 10.5. AWS Transfer Family

AWS Transfer Family provides managed SFTP, FTPS, FTP, and AS2 endpoints for exchanging files with partners and applications. It is often a replatform choice for legacy file transfer servers when you want to preserve existing partner protocols while replacing self-managed servers with a managed service.

Check authentication, user directories, SSH keys, certificates, IP allowlists, workflows, logging, endpoint types, and backend storage. Not all applications are compatible if they rely on local filesystem semantics or custom scripts on an old FTP server.

### 10.6. AWS Snow Family and Offline Transfer

When data volume is too large or network bandwidth is insufficient within the required timeframe, evaluate AWS Snow Family / offline data transfer options based on current availability in the target Region and country. AWS Snowball Edge can support offline data transfer/workflows where available; verify product availability, ordering, shipping, import/export, and supported features before including it in a plan.

Estimating online transfer duration:

\[
T_{days} = \frac{D_{TB}\times 8{,}000{,}000}{B_{Mbps}\times 86{,}400 \times U}
\]

Where \(D_{TB}\) is decimal TB capacity, \(B_{Mbps}\) is theoretical bandwidth, and \(U\) is effective utilization (0–1). This formula excludes protocol overhead, retries, contention, and ongoing writes during transfer.

Example: 100 TB over a 1 Gbps link at 70% effective utilization:

\[
T \approx \frac{100\times 8{,}000{,}000}{1000\times 86{,}400\times 0.7}
\approx 13.23\text{ days}
\]

For actively changing data, an initial copy followed by incremental sync or CDC before cutover is required. Offline seeding alone does not capture delta changes.

### 10.7. Migration Tool Selection Matrix

| Workload / Data | Primary Candidate Tool | Role |
|---|---|---|
| Server rehost to EC2 | AWS MGN | Replicate and launch target EC2 instances |
| Server disaster recovery | AWS DRS | Continuous replication, drills, recovery/failback |
| Database migration | AWS DMS / DMS Schema Conversion | Full load, CDC, schema conversion, and validation |
| File/NFS/SMB/object data | AWS DataSync | Transfer and incremental sync |
| Partner file transfer | AWS Transfer Family | Managed SFTP/FTPS/FTP/AS2 |
| Very large / offline datasets | Snow Family or supported offline method | Seed data when network transfer is impractical |
| Portfolio discovery | Application Discovery Service / AWS Transform | Inventory, utilization, dependency analysis |
| Migration tracking | AWS Migration Hub / AWS Transform workspace | Group workloads, track status, and wave visibility |

A single application may require multiple tools. For example: MGN for EC2 servers, DMS for databases, DataSync for file shares, Direct Connect/VPN for networking, and Migration Hub/AWS Transform for tracking.

## 11. Landing Zone and Hybrid Connectivity Before Migration

### 11.1. Landing Zone Readiness

A landing zone is the AWS foundation prepared before workloads move in. It requires:

- AWS Organizations and an account structure aligned to environments/business units.
- AWS Control Tower or an equivalent governance mechanism where appropriate.
- Centralized identity, IAM roles, permission sets, and break-glass access.
- Logging/audit accounts with CloudTrail, Config, and centralized log storage.
- Security services including GuardDuty, Security Hub, Inspector, and incident workflows.
- Network account, shared VPCs, Transit Gateway, DNS, and egress architecture.
- KMS key strategy, secrets, certificates, and encryption defaults.
- Backup policies, AWS Backup vaults, and cross-account/Region copies.
- Tagging, cost allocation, budgets, billing alerts, and showback.
- IaC/pipelines, patching, monitoring, SSM, AMI lifecycle, and operational runbooks.

Do not migrate production into an account without owners, logging, a security baseline, budgets, backups, and incident response. The landing zone must be tested before the first wave.

### 11.2. Network Discovery and Target Design

Before migration, inventory:

- CIDR ranges, VLANs, subnets, routing tables, and IP utilization.
- Firewall rules, ACLs, NAT, proxies, load balancers, and DNS.
- East-west traffic between applications and north-south traffic to users/partners.
- Private/public endpoints, multicast, static routes, and non-routable protocols.
- Bandwidth, latency, jitter, packet loss, and peak concurrency.
- Overlapping IP ranges across data centers, AWS VPCs, and partners.

Target network design must avoid CIDR overlap and define VPC segmentation, shared services, Transit Gateway attachments, inspection/egress, DNS resolution, and security controls. Do not simply replicate firewall rules as-is; review least privilege and actual application flows to eliminate obsolete access.

### 11.3. Direct Connect and Site-to-Site VPN

| Attribute | AWS Direct Connect | AWS Site-to-Site VPN |
|---|---|---|
| Connectivity | Dedicated private network connectivity via DX location/provider | IPsec tunnels over the Internet or supported transit |
| Encryption | DX does not encrypt traffic by default; use MACsec/IPsec when required and supported | IPsec encrypts the tunnel |
| Performance | More consistent bandwidth and latency when sized appropriately | Varies with Internet path conditions |
| Setup | Requires circuit/provider/cross-connect and provisioning | Can be deployed much faster |
| Use case | High-volume, steady, long-term hybrid traffic | Bootstrap, backup path, moderate traffic |
| Resilience | Design multiple DX connections/locations per requirements | Multiple tunnels and redundant design |

VPN can serve as a backup path for Direct Connect. For sensitive traffic, define encryption-in-transit requirements explicitly; private connectivity does not mean encrypted payloads.

### 11.4. DNS and Identity in Hybrid Environments

During phased migration, some components run on-premises while others run on AWS. Design:

- Route 53 Resolver inbound/outbound endpoints and forwarding rules.
- Private hosted zones and split-horizon DNS.
- AD trusts/domain controllers or Directory Service integration.
- Kerberos/SPN, LDAP, certificate authorities, and time synchronization.
- Identity federation, IAM roles, and service-to-service credentials.
- DNS TTLs and rollback records for cutover.
- Partner/third-party allowlists updated with new IPs.

DNS changes may not propagate immediately due to resolver caching. Lower TTLs ahead of cutover by an appropriate lead time, verify resolver paths, and keep a plan to restore previous records.

### 11.5. Hybrid Operating Model

During coexistence, agree on:

- Who manages the on-premises network and who manages AWS VPCs.
- Who approves firewall, DNS, and routing changes.
- Who handles incidents involving cross-environment dependencies.
- Monitoring/logging with consistent correlation IDs and timestamps.
- Patching, vulnerability scanning, and configuration compliance across both environments.
- Backup/DR responsibilities for replicating or remaining on-premises data.
- CMDB/asset inventory updates for ownership and lifecycle.



## 12. Migration Wave Planning

### 12.1. Why Use Waves?

A migration wave is a group of applications/workloads migrated within the same timeframe or deployment cycle. Dividing into waves limits blast radius, allocates team capacity, controls cutover windows, and lets you apply lessons learned from earlier waves.

Do not group workloads solely by subnet, OS, or server rack. Group by application boundaries and dependency graphs first, then optimize by technical complexity, business criticality, target architecture, and change calendars.

### 12.2. Factors Shaping Waves

- **Dependency group:** applications/servers that must move together or require a dependency bridge.
- **Business criticality:** avoid putting all Tier 0 workloads into one wave.
- **Technical complexity:** OS, database, network, licensing, data volume, and vendor constraints.
- **Migration strategy:** rehost, replatform, repurchase, retire, etc.
- **Data transfer:** volume, change rate, bandwidth, and replication duration.
- **Cutover window:** business hours, blackout periods, quarter-end, peak seasons.
- **Team capacity:** application owners, network, security, DBA, cloud platform, vendors.
- **Landing zone readiness:** accounts, VPC, IAM, logging, backup, monitoring.
- **Rollback feasibility:** can you return to source, and how fast?
- **Business value:** data center exit deadlines, cost savings, or modernization priorities.

### 12.3. Organizing Waves by Risk Level

A commonly used structure:

| Wave | Scope | Objective |
|---|---|---|
| Wave 0 — Foundation | Landing zone, network, security, tooling, monitoring | Prepare the platform and validate processes |
| Wave 1 — Pilot | Simple, non-critical workloads with few dependencies | Validate tools, runbooks, estimates, and team collaboration |
| Wave 2 — Repeatable | Similar workloads with low/medium complexity | Standardize the migration factory |
| Wave 3 — Complex | Complex dependencies, specialized databases/licenses/networks | Apply experience and control risks |
| Wave N — Critical | Tier 0/Tier 1 or workloads with strict business constraints | Execute only after patterns, rollback, and owners prove readiness |

Do not pick a pilot consisting only of empty servers with no user paths. A pilot should represent real-world patterns while keeping blast radius small.

### 12.4. Dependency Grouping

Build a graph where nodes are applications/servers/databases/shared services and edges represent dependencies. Attach direction, protocol/port, criticality, owner, and latency sensitivity.

Example:

~~~mermaid
flowchart TD
    DNS["DNS / Identity"] --> DB["Database"]
    DB --> API["Application API"]
    MQ["Message Broker"] --> API
    API --> WEB["Web frontend"]
    API --> EXT["External payment API"]
    FILE["Shared file service"] --> API
    OBS["Monitoring / Logging"] -.-> DB
    OBS -.-> API
    OBS -.-> WEB
~~~

When a required dependency cannot move in the same wave, design a connectivity bridge and test latency and authentication. An application may temporarily call an on-premises database over Direct Connect/VPN, but this transitional state requires an owner, performance testing, and an end date.

### 12.5. Wave Plan Deliverables

Each wave requires at minimum:

- List of applications, source assets, and dependency groups.
- 7R decisions, target architectures, and architecture approvals.
- Detailed assessment and inventory confidence scores.
- Data transfer plan, migration tooling, and replication estimates.
- Landing zone/account/VPC/subnet/security designs.
- License, compliance, and security approvals.
- Test plan, acceptance criteria, and business sign-off.
- Cutover runbook, rollback runbook, and communications plan.
- Owners/approvers, timeline, maintenance windows, and escalation contacts.
- Hypercare plan, cost estimate, and decommission criteria.

AWS Prescriptive Guidance generally recommends waves covering assessment, readiness, infrastructure build/test, data transfer, cutover, and wave closure. Wave duration can span several weeks depending on the portfolio; do not impose a fixed week count across every organization.

## 13. Cutover, Validation, and Rollback Planning

### 13.1. Defining the Cutover Strategy

Cutover is the point where user traffic and write authority transition from source to target. Choose the approach based on downtime tolerance, consistency, and architecture:

- **Big bang:** move the entire application/dependency group in a single maintenance window.
- **Phased:** migrate component by component, tenant by tenant, or user group by user group.
- **Blue/green:** keep source and target running concurrently, shifting traffic via load balancer/DNS once target passes validation.
- **Canary/weighted:** shift a small percentage of traffic first, observe, and gradually increase.
- **Read-only transition:** target serves read traffic first, then writes are frozen and cut over.

Not every application supports canary or blue/green. Stateful databases, batch jobs, and external integrations may require write freezes and coordinated cutover.

### 13.2. Cutover Runbook

A runbook must specify sequence, owner, expected duration, commands/actions, expected results, and abort criteria.

Example:

1. Send change notice, confirm incident bridge, and verify approvers.
2. Freeze code and configuration changes before the cutover window.
3. Verify target infrastructure, security, DNS, monitoring, and backups.
4. Confirm replication lag is below the allowed threshold.
5. Run pre-cutover smoke tests and readiness checks.
6. Put the source application into maintenance/read-only mode.
7. Stop background jobs/consumers and block writes per runbook.
8. Perform final data sync / CDC catch-up.
9. Run data validation, row counts, checksums, or business reconciliation.
10. Update connection strings, secrets, and service discovery.
11. Switch DNS, load balancer, Global Accelerator, or traffic routes.
12. Start target services in dependency order.
13. Run application smoke tests and end-to-end business transactions.
14. Open traffic incrementally and monitor SLOs.
15. Obtain business sign-off, record cutover timestamp, and keep source rollback-ready for the agreed retention window.

### 13.3. Acceptance Criteria

Acceptance criteria must be quantifiable. Examples:

| Category | Sample Criteria |
|---|---|
| Availability | Health checks pass; no critical component unavailable |
| Performance | p95 latency does not exceed baseline + agreed threshold |
| Data | Row counts/checksums/reconciliation pass; zero unexpected data loss |
| Functionality | Critical business journeys pass |
| Security | IAM, encryption, vulnerability, logging, and network tests pass |
| Integration | Partner APIs, SFTP, payments, email, and queues operate properly |
| Operations | Monitoring, alerts, backups, patching, and incident workflows function |
| Cost | Actual usage is within expected range or has an action plan |
| Business | Product/business owner signs off acceptance |

Do not rely solely on "server running" or "HTTP 200" as acceptance criteria. Validate end-to-end transactions and data integrity.

### 13.4. Data Validation

For database migrations, AWS DMS data validation can be used when supported by the source-target path. DMS compares source and target data row by row and reports mismatches. However, validation can be affected if the application writes to the target while validation runs, rows change continuously, primary keys are missing, or data types are unsupported.

In addition to DMS validation, use:

- Row counts per table/partition.
- Batch checksums/hashes.
- Referential integrity checks.
- Aggregate business totals: balances, order counts, inventory quantities.
- Sampled record comparisons.
- File count/size/hash and metadata checks for file transfers.
- Application-level reconciliation and audit reports.

Define clear tolerances: zero mismatch for financial data, or a business-owner-approved threshold for analytics/eventually consistent data.

### 13.5. Rollback Strategy

A rollback plan must answer:

- When must we abort? For example: critical data mismatch, security control failure, p95 latency exceeding threshold, payment transaction failures.
- Who has authority to trigger a rollback?
- Does the source still hold authoritative data?
- Can traffic be shifted back without losing writes committed on the target?
- Is reverse replication or dual-write reconciliation required?
- How will DNS TTLs, load balancer weights, and connection pools be reverted?
- Must external partners revert IP allowlists or endpoints?
- Is source infrastructure intact and are licenses/contracts still valid?

**The hardest challenge is post-cutover data.** Once the target accepts new writes, reverting traffic to the source without syncing those writes causes data loss. You need write freezing, reverse sync, or reconciliation aligned with database and application design. Never promise "one-click" rollback without a tested reverse synchronization mechanism.

### 13.6. Go / No-Go Decision

Hold a readiness review before cutover. Declare No-Go if any critical blocker remains:

- Replication/data transfer has not caught up.
- Backup/restore or rollback has not been tested.
- Network/DNS/security rules are unapproved.
- Licensing/compliance status is unclear.
- Application owner or incident commander is unavailable.
- EC2/service quotas or target capacity are insufficient.
- Acceptance tests have not passed.
- Data consistency or write fencing lacks a plan.

A Go decision must record approver names, timestamp, scope, and assumptions.

## 14. Governance, Ownership, and Migration Operating Model

### 14.1. Key Roles

| Role | Responsibilities |
|---|---|
| Executive sponsor | Business outcomes, funding, risk acceptance, and escalation |
| Migration program lead | Scope, timeline, waves, governance, and status reporting |
| Application owner | Business requirements, dependencies, testing, and sign-off |
| Infrastructure/platform team | Landing zone, accounts, VPC, compute, storage, and automation |
| Network team | Connectivity, routing, DNS, firewalls, and partner paths |
| Security/compliance | IAM, encryption, audit, data residency, and approvals |
| DBA/data team | Schemas, data migration, CDC, validation, and consistency |
| Operations/SRE | Monitoring, backups, patching, incident response, and hypercare |
| Vendor/partner | Product support, licensing, migration assistance, and certification |

One person may hold multiple roles in smaller programs, but accountability must remain unambiguous. Avoid situations where the application owner and technical owner each assume the other is signing off.

### 14.2. RACI for Key Activities

| Activity | Responsible | Accountable | Consulted |
|---|---|---|---|
| Inventory/discovery | Migration team | Migration lead | Application/infrastructure owners |
| 7R decision | Solution architect | Application/business owner | Security, finance, operations |
| Target architecture | Cloud/platform team | Architecture board | Network, security, DBA |
| TCO/business case | FinOps/finance | Executive sponsor | Platform, application owner |
| Data migration | DBA/data team | Application owner | Network, security |
| Cutover | Migration lead + application team | Change authority | Operations, business, vendor |
| Rollback | Technical owners | Incident/change commander | Business owner |
| Decommission | Infrastructure team | Application owner | Security, compliance, finance |

### 14.3. Migration Factory

A migration factory standardizes repeatable work across waves:

- Standard discovery templates and inventory schemas.
- Reusable 7R decision records.
- Standard landing zone patterns and IaC modules.
- Migration runbooks for MGN/DMS/DataSync.
- Standard test and validation scripts.
- Cutover/rollback templates.
- Central dashboard and issue/risk log.
- Wave retrospectives and continuous improvement.

A factory does not mean every workload is identical. Standardize what repeats, while requiring documented evidence, owners, and approvals for exceptions.

### 14.4. FinOps and Cost Governance

Before and after migration:

- Tag resources by application, owner, environment, cost center, and migration wave.
- Enable AWS Budgets and Cost Anomaly Detection.
- Track data transfer, NAT, inter-AZ traffic, logging, and storage growth.
- Compare forecast vs. actual spend after each wave.
- Purchase Savings Plans/Reserved Instances only after usage stabilizes under a commitment strategy.
- Review idle resources, unattached EBS volumes, snapshots, test instances, and duplicate environments.
- Confirm actual on-premises decommissioning so projected savings are realized.

Running both source and target for extended periods can increase overall costs rather than reduce them. Assign deadlines and owners to parallel-run exit criteria.

### 14.5. Post-Migration Hypercare and Decommissioning

After cutover, run hypercare for an agreed duration:

- Monitor SLOs, incidents, support tickets, and user feedback.
- Resolve performance regressions and capacity issues.
- Verify backup/restore, DR, patching, and monitoring.
- Optimize EC2/EBS/database sizing once production metrics stabilize.
- Close migration issues and update architecture diagrams/CMDB.
- Archive required logs/data and purge temporary migration data per policy.
- Decommission source resources after business owner and compliance sign-off.
- Terminate contracts/licenses and update asset records.



## 15. Case Study: Assessing and Selecting a Strategy for an E-Commerce System

### 15.1. Current State

A retail enterprise operates an e-commerce platform in an on-premises data center:

| Component | Current State | Dependencies |
|---|---|---|
| Web tier | 4 Linux VMs, Java web application | API tier, DNS, TLS |
| API tier | 6 Linux VMs, Java/Spring Boot | PostgreSQL, Redis, SQS-compatible internal broker |
| Database | PostgreSQL 2 TB, internal streaming replication | API, reporting, backup |
| File service | SMB share 8 TB | API, batch jobs |
| Identity | Active Directory 2 domain controllers | Web/API, admin access |
| Reporting | 2 VMs running nightly batch jobs | PostgreSQL, SMB share |
| External | Payment gateway, email, logistics partner SFTP | API tier, DNS, allowlists |

Business requirements: data center lease expires in 9 months; peak traffic increases 4x during sales events; RTO target 2 hours, RPO 5 minutes for the order database; maximum maintenance window 2 hours.

### 15.2. Discovery Findings

The assessment collected 4 weeks of p95 CPU/memory, disk IOPS, database write rates, network flows, and application owner interviews. Findings:

- Web/API tiers exhibit highly variable utilization and need horizontal scaling.
- PostgreSQL is a critical data tier with multiple extensions and stored procedures.
- The SMB share has complex ACLs and many small files.
- Reporting batch jobs run only overnight and can be decoupled from the web/API cutover.
- The payment gateway enforces IP allowlists; partner SFTP has a separate maintenance window.
- A legacy report server has zero remaining users and can be retired after archival.

### 15.3. 7R Decisions

| Component | Strategy | Target / Next Step | Rationale |
|---|---|---|---|
| Web tier | Replatform | ECS on Fargate or EC2 Auto Scaling after PoC | Stateless candidate needing traffic-based scaling |
| API tier | Replatform per service | ECS/Fargate; keep some workers on EC2 initially | Improves elasticity with limited packaging changes |
| PostgreSQL | Replatform | Amazon RDS for PostgreSQL or Aurora PostgreSQL after compatibility check | Managed backups/HA, but requires checking extensions and query behavior |
| SMB share | Replatform | Amazon FSx for Windows File Server | Preserves SMB/ACL semantics closely |
| Active Directory | Retain/extend first | Hybrid AD connectivity; evaluate AWS Managed Microsoft AD later | Avoid changing identity simultaneously with app cutover |
| Reporting batch | Rehost first, modernize later | EC2 or AWS Batch depending on scheduler/data access | Reduces initial wave scope |
| Legacy report server | Retire | Archive reports/data, decommission | No remaining business usage |

### 15.4. Wave Proposal

- **Wave 0:** landing zone, Direct Connect/VPN, DNS Resolver, identity integration, centralized logging, backup, CI/CD, and security baseline.
- **Wave 1:** non-critical reporting server and an internal service to validate MGN and observability.
- **Wave 2:** file service and batch workloads, validating FSx ACLs, DataSync, and schedules.
- **Wave 3:** API/web tiers by dependency group, canary traffic, and load testing.
- **Wave 4:** PostgreSQL migration via DMS/native tooling, CDC, data validation, and write freeze during cutover.
- **Wave 5:** retire old report server, decommission source resources, and optimize AWS usage.

### 15.5. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| PostgreSQL extension incompatible with target | Query/application failure | DMS Schema Conversion / compatibility assessment and PoC |
| DataSync fails to preserve ACLs/metadata | Incorrect user access | Pilot file sample, ACL validation, and owner sign-off |
| Partner allowlist not updated | Payment/SFTP failure | Early endpoint testing, coordinated change, and rollback path |
| Insufficient capacity during 4x peak sale | Latency/error spikes | 4x peak load testing, autoscaling, and quota review |
| Prolonged DNS caching | Delayed cutover | Lower TTL early; verify resolver and partner caching |
| Hybrid AD latency | Slow login/service auth | Test DNS/Kerberos/LDAP over private connectivity |
| New writes on target post-cutover | Rollback causes data loss | Write freeze/fencing and reverse sync/reconciliation plan |

### 15.6. Final Decision

Do not move the entire stack in a single cutover. Migrate the foundation and low-risk components first, followed by web/API, and finally the database and high-business-risk components. Each wave has dedicated acceptance criteria, owners, and a rollback plan. Decommission the data center only after all workloads, backups, networking, identity, audit, and operational responsibilities are signed off.

## 16. Hands-on Labs in an AWS Sandbox

Labs use simulated inventory or test workloads managed by the learner. Never install discovery agents, migration agents, or modify production routes/firewalls without formal approval.

### 16.1. Lab A — Build an Application Portfolio Inventory

1. Create a spreadsheet/CSV inventory with application ID, owner, business criticality, server IDs, OS, CPU, RAM, disks, database, and dependencies.
2. Add p50/p95 utilization, disk IOPS, and sample network traffic.
3. Flag unknown, stale, or unverified data.
4. Group servers by application boundaries.
5. Identify the data owner, business owner, and technical owner.
6. Build a dependency map for one application.
7. Review inventory completeness and assign a confidence score.

Deliverable: application inventory, dependency map, and list of assessment gaps.

### 16.2. Lab B — Compare Discovery Methods

1. Review the requirements of AWS Application Discovery Service.
2. Distinguish Agentless Collector from Discovery Agent.
3. Build a sample inventory from a CMDB/vCenter export or simulated dataset.
4. Tag which fields represent static configuration, utilization, processes, and network connections.
5. Identify which data points require verification with the application owner.
6. Diagram discovery → Migration Hub/AWS Transform → portfolio assessment.
7. Document data access and retention assumptions.

Deliverable: discovery method decision record and data quality report.

### 16.3. Lab C — Classify 7Rs and Target AWS Services

1. Select at least 8 sample workloads: VM, database, file share, SaaS candidate, legacy app, batch job, stateless API, and unused server.
2. Propose a candidate 7R for each workload.
3. Identify at least two options for complex workloads.
4. Map target services: EC2, ECS, EKS, Lambda, RDS, Aurora, DynamoDB, FSx, EFS, S3.
5. Document rationale, assumptions, blockers, licensing, and business approvals.
6. Compare time-to-migrate, cost, risk, and operational complexity.

Deliverable: 7R decision matrix and target service mapping.

### 16.4. Lab D — Calculate Data Transfer and TCO

1. Choose a 20 TB dataset and 500 Mbps bandwidth.
2. Calculate theoretical transfer duration and adjust for effective utilization.
3. Add a delta change rate and incremental sync window.
4. Build a 1-year/3-year on-premises vs. AWS cost model.
5. Estimate EC2, EBS, RDS, DataSync/network, backups, and support.
6. Build conservative/expected/growth scenarios.
7. Identify the top 5 assumptions impacting TCO.

Deliverable: transfer estimate, TCO model, and sensitivity analysis.

### 16.5. Lab E — Build a Migration Wave and Cutover Plan

1. Create a dependency graph for a three-tier application.
2. Divide into foundation, pilot, repeatable, and complex waves.
3. Assign MGN/DMS/DataSync per component.
4. Prepare a cutover runbook with owners, durations, and expected results.
5. Define acceptance criteria for data, performance, security, and business flows.
6. Write a rollback decision tree and data reconciliation approach.
7. Run a tabletop exercise for a scenario where the target database fails validation.

Deliverable: wave plan, cutover/rollback runbook, and Go/No-Go checklist.

## 17. Migration Assessment Review Checklist

### Business and Portfolio

- [ ] Are business drivers and measurable outcomes agreed upon?
- [ ] Are scope, exclusions, locations, and deadlines clear?
- [ ] Does every application have a business owner and technical owner?
- [ ] Are criticality, SLA/SLO, RTO/RPO, and downtime tolerance confirmed?
- [ ] Have licensing, vendor support, and end-of-life constraints been checked?

### Discovery and Dependencies

- [ ] Is server/database/storage inventory complete and timestamped?
- [ ] Does utilization data reflect peak/seasonal workloads?
- [ ] Were network connections and processes collected where needed?
- [ ] Are dependencies, protocols, ports, and owners verified?
- [ ] Do unknown/stale/duplicate records have remediation owners?
- [ ] Are data classification, residency, and retention defined?

### 7Rs and Target Architecture

- [ ] Does each workload have a candidate 7R and rationale?
- [ ] Were retire/retain considered rather than defaulting everything to migrate?
- [ ] Were rehost/replatform/refactor compared where appropriate?
- [ ] Were target services checked for compatibility, quotas, Region, and pricing?
- [ ] Were database schemas, extensions, and licenses evaluated?
- [ ] Were shared file/object semantics and integration behaviors evaluated?

### Cost and Readiness

- [ ] Does on-premises TCO include facilities, licenses, support, and labor?
- [ ] Does the AWS estimate cover compute, storage, database, network, security, and support?
- [ ] Are migration, parallel-run, training, downtime, and decommission costs included?
- [ ] Are utilization/right-sizing assumptions and growth scenarios explicit?
- [ ] Are landing zone, network, identity, security, and operations ready?
- [ ] Are FinOps tagging, budgets, and cost ownership defined?

### Waves, Cutover, and Rollback

- [ ] Are dependency groups and wave sequencing sound?
- [ ] Does the pilot represent real patterns while keeping blast radius small?
- [ ] Does each data/server component have the right migration tool?
- [ ] Are cutover windows, runbooks, owners, and approvers clear?
- [ ] Are acceptance criteria quantifiable and backed by business sign-off?
- [ ] Does the rollback plan address post-cutover writes?
- [ ] Have DNS, partner allowlists, and hybrid dependencies been tested?
- [ ] Do hypercare, source decommission, and lessons learned have assigned owners?

## 18. Self-Assessment Questions

1. What decisions must a migration assessment answer?
2. Why should you start from business drivers instead of picking servers to move?
3. How does an application portfolio differ from an infrastructure inventory?
4. How does static configuration differ from utilization time series?
5. Why is average CPU insufficient for right-sizing EC2?
6. What attributes should an application dependency map capture?
7. What discovery methods does AWS Application Discovery Service provide?
8. How does Agentless Collector differ from Discovery Agent?
9. What is the purpose of the AWS Migration Hub home Region?
10. Which parts of migration assessment and planning does AWS Transform support?
11. How should AI recommendations be validated?
12. What cost categories should a Migration Evaluator/TCO analysis include?
13. What are the seven migration strategies (7 Rs)?
14. How does Retire differ from Retain?
15. How does Rehost differ from Relocate?
16. When is Repurchase appropriate?
17. How does Replatform differ from Refactor/Re-architect?
18. Why should you avoid refactoring every application during a large migration wave?
19. When should AWS Application Migration Service (MGN) be used?
20. How does MGN differ from AWS Elastic Disaster Recovery (DRS) in primary objective?
21. How does AWS DMS support full load and CDC?
22. Why doesn't DMS automatically migrate every schema object and permission?
23. Which data movement patterns suit AWS DataSync?
24. What use case does AWS Transfer Family address?
25. When should offline data transfer be evaluated?
26. What controls should a landing zone have before production migration?
27. How does Direct Connect differ from Site-to-Site VPN?
28. Why does Direct Connect not equate to encryption?
29. What factors should guide migration wave grouping?
30. What steps and owners does a cutover runbook need?
31. Which dimensions should acceptance criteria measure?
32. Why is rolling back after the target receives writes harder than rolling back before cutover?
33. Why is a data reconciliation/reverse sync plan required?
34. What work does a migration factory standardize?
35. What roles do hypercare and decommission criteria play?
36. What elements should be included in a 3-year TCO and business case?

### Answer Key Guidance

- **Assessment:** starts with business outcomes, portfolio scope, inventory, dependencies, performance, compliance, and operating model.
- **Discovery:** combines static configuration, utilization, process/network connections, and owner interviews; standardizes identities and data confidence.
- **7 Rs:** Retire, Retain, Rehost, Relocate, Repurchase, Replatform, Refactor/Re-architect; selected based on business and technical constraints.
- **Tool selection:** MGN for server rehosting; DRS for disaster recovery; DMS for databases; DataSync for files/objects; Transfer Family for partner protocols; Snow/offline transfer for very large datasets where supported.
- **TCO:** includes on-premises costs, AWS run costs, licensing, networking, security, migration effort, parallel runs, training, and decommissioning.
- **Waves:** grouped by dependencies, criticality, complexity, data transfer, downtime, and team capacity; pilot before scaling.
- **Cutover:** final sync, freeze writes, validate, traffic cutover, business sign-off; rollback must handle data generated after the target began accepting writes.

## 19. Official AWS Documentation

1. [About AWS Cloud migration strategies (7 Rs)](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/migration-strategies.html) — Definitions and use cases for the seven migration strategies.
2. [Detailed portfolio discovery](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-migration/detailed-portfolio-discovery.html) — Portfolio inventory, 7R rationalization, and migration planning.
3. [Application portfolio assessment strategy](https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-application-portfolio-assessment-migration/portfolio-analysis-migration-planning.html) — Assessment outcomes, dependency groups, and wave planning.
4. [AWS Application Discovery Service](https://docs.aws.amazon.com/application-discovery/latest/userguide/what-is-appdiscovery.html) — Discovery concepts, data collection, and Migration Hub integration.
5. [Agentless Collector](https://docs.aws.amazon.com/application-discovery/latest/userguide/agentless-collector.html) — VMware discovery, server utilization, and database/analytics data collection.
6. [Discovery Agent](https://docs.aws.amazon.com/application-discovery/latest/userguide/discovery-agent.html) — Agent-based inventory, processes, and network connections.
7. [AWS Migration Hub](https://docs.aws.amazon.com/migrationhub/latest/ug/whatishub.html) — Central migration tracking and home Region.
8. [AWS Transform migration assessments](https://docs.aws.amazon.com/transform/latest/userguide/transform-app-assessments.html) — TCO/business case, feasibility, and scenario comparison.
9. [AWS Transform migrations including VMware](https://docs.aws.amazon.com/transform/latest/userguide/transform-app-vmware.html) — Discovery, dependency mapping, wave planning, landing zone, and rehosting.
10. [AWS Transform 7R recommendations](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-r-strategy-report.html) — Strategy recommendations by server/application.
11. [Migration Evaluator business case](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-tools/business-case-migration-evaluator.html) — TCO inputs and cost modeling.
12. [AWS Application Migration Service](https://docs.aws.amazon.com/mgn/latest/ug/what-is-application-migration-service.html) — Rehosting server workloads to EC2.
13. [AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html) — DR replication/recovery, distinguished from migration.
14. [AWS Database Migration Service best practices](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_BestPractices.html) — Database assessment, PoC, performance, and data validation.
15. [AWS DMS data validation](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Validating.html) — Comparing source/target data and validation limitations.
16. [AWS DMS Schema Conversion](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_SchemaConversion.html) — Schema/code conversion for database migration.
17. [AWS DataSync User Guide](https://docs.aws.amazon.com/datasync/latest/userguide/what-is-datasync.html) — File/object data transfer and supported locations.
18. [AWS Transfer Family](https://docs.aws.amazon.com/transfer/latest/userguide/what-is-aws-transfer-family.html) — Managed SFTP, FTPS, FTP, and AS2.
19. [AWS Snow Family](https://docs.aws.amazon.com/snowball/latest/developer-guide/whatisedge.html) — Offline data transfer options and device workflows; verify current availability.
20. [AWS Direct Connect](https://docs.aws.amazon.com/directconnect/latest/UserGuide/Welcome.html) — Dedicated hybrid connectivity and resilience.
21. [AWS Site-to-Site VPN](https://docs.aws.amazon.com/vpn/latest/s2svpn/VPC_VPN.html) — IPsec tunnels and hybrid networking.
22. [AWS Control Tower](https://docs.aws.amazon.com/controltower/latest/userguide/what-is-control-tower.html) — Multi-account landing zone and governance.
23. [AWS Prescriptive Guidance: Wave planning](https://docs.aws.amazon.com/prescriptive-guidance/latest/application-portfolio-assessment-guide/wave-planning.html) — Dependency groups, wave phases, cutover, and rollback.
24. [Guidelines for a successful migration](https://docs.aws.amazon.com/prescriptive-guidance/latest/migration-program-implementation/guidelines.html) — Program governance, landing zone, and operating model.
25. [AWS Migration Hub large migration guide](https://docs.aws.amazon.com/prescriptive-guidance/latest/large-migration-guide/welcome.html) — Portfolio, waves, migration factory, and large-scale migration.

> **Lesson takeaway:** A thorough system assessment turns inventory and dependency data into verifiable decisions: which workloads to retire or retain, which 7R strategy to apply, which target AWS services fit, what costs and risks look like, and which wave to migrate in. Successful migration requires a ready landing zone, the right data movement tools, owned cutover/rollback plans, quantifiable acceptance criteria, and a post-migration operating model. Never consider "server running on AWS" complete until business flows, data, security, monitoring, backups, and costs have been signed off.
