# SAP on Google Cloud and Enterprise Infrastructure Requirements

SAP is the foundational platform running mission-critical processes such as finance, procurement, sales, supply chain, manufacturing, and management reporting. When deploying SAP on Google Cloud, a Linux VM that boots or a database that starts up **is not enough** to prove enterprise readiness. You must verify SAP certifications, sizing, storage, high availability, data protection, connectivity to existing systems, monitoring, licensing, and disaster recovery.

Google Cloud provides Compute Engine, VPC networking, block storage, Cloud Storage, Cloud Load Balancing, and management services tailored for SAP systems. The SAP-on-Google-Cloud ecosystem also includes tooling for deployment, metrics collection, and best-practice evaluations. However, **not every VM type, disk type, OS version, or architecture is SAP-certified**. Production designs must cross-check certification lists, SAP Notes, Google Cloud documentation, and organizational support contracts at design time.

This lesson focuses on SAP S/4HANA, SAP HANA, SAP NetWeaver/ABAP, and related enterprise systems. Learners will understand how to analyze workloads, design three-tier architectures, pick supported infrastructure, implement HA/DR, configure backups, enforce security, manage costs, and plan transitions with production-grade governance.

## 1. Understanding SAP Components in an Enterprise Landscape

A typical SAP landscape spans multiple systems and environments:

- **Development (DEV):** ABAP development, configuration changes, and unit testing.
- **Quality/Testing (QAS):** integration testing, regression testing, performance testing, and transports.
- **Pre-production (PRE-PROD):** production-like validation when required.
- **Production (PRD):** live business transactions and operational data.
- **DR environment:** recovery target when primary infrastructure or regions fail.

Common components inside an SAP system include:

| Component | Role | Infrastructure Notes |
|---|---|---|
| SAP S/4HANA | ERP suite running on SAP HANA | Verify 2-tier/3-tier layouts and certifications |
| SAP HANA | In-memory database persisting state to disk | Memory, CPU, storage I/O, and HA/DR are critical |
| SAP NetWeaver/ABAP Application Server | Processes business logic, dialog, and background jobs | Can scale across multiple application servers |
| ASCS/SCS | SAP Central Services, including enqueue/message services | Critical component typically requiring HA |
| ERS | Enqueue Replication Server | Pairs with ASCS to protect enqueue lock state |
| SAP Web Dispatcher | Routes HTTP(S) traffic to application servers | May require HA/load-balancing design |
| SAP HANA System Replication | Replicates HANA to a secondary system | Requires selecting replication mode and testing failover |
| SAP Host Agent and Google Cloud's Agent for SAP | Collects host/SAP telemetry for support and monitoring | Configure per supported versions and docs |

SAP BW/4HANA, SAP Business Suite/ECC, SAP Solution Manager, and other SAP products have distinct requirements. **Never apply an S/4HANA sizing sheet blindly to every SAP product.**

### Separating Application Tier and Database Tier

A **2-tier** architecture places SAP applications and the database close together or on the same host per certified models. A **3-tier** architecture separates application servers from the database server, simplifying horizontal scaling and HA designs.

Choosing between them depends on the SAP solution, scale, support rules, and certifications. Never claim 3-tier is universally superior for small workloads or products with different deployment guides.

## 2. Responsibility Model Across SAP, Google Cloud, and the Enterprise

Enterprises remain responsible for operating components running inside VMs and across the SAP application layer.

| Scope | Primary Responsibility |
|---|---|
| Google Cloud infrastructure | Compute Engine, regional/network infrastructure, storage, and Google Cloud services per SLAs |
| SAP software | Software binaries, certification rules, SAP Notes, and contractual software support |
| OS and cluster software | Configuration, patching, agents, filesystems, and HA clustering per responsibility model |
| SAP Basis / DBA | SAP instances, HANA, transports, backups, performance tuning |
| Cloud platform / SRE | VPC/IAM, capacity, logging, cloud HA/DR, automation, and FinOps |
| Security / compliance | Access controls, encryption, auditing, retention, access reviews |
| Business owners | SLOs, financial close calendars, recovery objectives, downtime sign-off |
| Managed service provider (if any) | Responsibilities explicitly defined in contract; never infer from package names |

Under commercial offerings like RISE with SAP or partner-managed services, infrastructure admin rights and operational ownership can differ. Always rely on official contracts and RACI matrices before designing IAM, backups, and change workflows.

### Foundational Architecture Questions

- Is this a lift-and-shift migration, an ECC-to-S/4HANA conversion, or a greenfield deployment?
- How high are SAPS requirements, HANA memory footprints, and peak transaction loads?
- Which environments require HA, and what are the exact RPO/RTO targets?
- How does the system connect to factories, banks, partners, and on-premises environments?
- Are there data residency or audit mandates?
- Are SAP, OS, HANA, and support licenses properly aligned?

## 3. SAP Certification Is a Prerequisite

SAP publishes certified/supported hardware, operating systems, and deployment topologies. On Google Cloud, only a specific subset of Compute Engine machine types and storage/OS configurations are supported for each SAP solution.

Never pick machines solely on price-per-vCPU or RAM while ignoring certification directories.

### Verification Matrix

| Item | What to Cross-Check |
|---|---|
| SAP product | S/4HANA, BW/4HANA, NetWeaver, HANA, or another database |
| Deployment model | Scale-up, scale-out, 2-tier/3-tier, HA, or DR |
| Machine type | Certified specifically for the target workload |
| CPU / memory | SAPS, vCPU counts, RAM, and configuration limits |
| Operating system | SLES for SAP, RHEL for SAP, or Windows if solution-supported |
| Storage type | Certified Persistent Disk/Hyperdisk types and layouts |
| Region / zone | Target machine type and capacity availability |
| SAP kernel / HANA revision | Within supported ranges per active SAP Notes |
| Network | Bandwidth, latency, and supported VIP/HA implementations |
| Licensing / support | Entitlements and official support escalation paths |

Google Cloud maintains **SAP certifications** and **SAP HANA planning guide** pages; during design, also verify the SAP Certified and Supported SAP HANA Hardware Directory and active SAP Notes. Never reuse a configuration certified years ago without re-verifying current status.

### Never Infer Certification from a Machine Family

A machine family contains many variants. One high-RAM variant being certified does not mean every custom shape in that family is SAP HANA-certified. Even with custom machine types, only explicitly listed combinations qualify for production.

## 4. Sizing: From Business Demand to CPU, Memory, and I/O

SAP sizing must combine actual telemetry from existing systems with SAP-recognized methodologies such as SAP Quick Sizer or solution-specific sizing reports.

### Key Sizing Inputs

- Concurrent users and transaction profiles.
- Dialog step volumes or business transaction rates.
- Batch jobs, MRP runs, period-end closes, and month/quarter-end peaks.
- Current data volume and multi-year growth rate.
- HANA memory footprint, column store, row store, and working sets.
- Application-tier SAPS.
- Transaction log generation rates, backup windows, and replication bandwidth.
- Response time, throughput, and RTO/RPO targets.
- Expected workload shifts after migration or S/4HANA transformation.

### HANA Memory

Because HANA is an in-memory database, memory sizing is paramount. Never sum on-disk database size and assume that equals minimum RAM. Factor in compression ratios, working sets, intermediate query results, delta merges, headroom, and workload-specific sizing rules.

### CPU, SAPS, and Networking

SAPS is an SAP-defined benchmark unit; there is no universal fixed conversion ("1 vCPU equals X SAPS") across CPU generations and machine types. Pull figures directly from certification docs and sizing tools.

A HANA host may have ample CPU and memory yet starve for replication bandwidth or log write throughput. Sizing must satisfy compute, memory, storage, and network simultaneously.

### Sample Sizing Worksheet

| Workload | Peak Metric | Requirement | Verification |
|---|---|---|---|
| ABAP app | Concurrent users / dialog steps | SAPS and app-server capacity | Transaction load testing |
| HANA | Working memory + headroom | Certified host memory | HANA sizing and memory telemetry |
| Data volume | Capacity and IOPS | Certified block storage | Latency / read throughput |
| Log volume | Log write rate | Low-latency sustained writes | Log backups and benchmarks |
| Replication | Change rate | Network bandwidth/latency | HSR lag and failover tests |
| Backup | Data + log bytes | Backup throughput and buckets | Restore rehearsals |

Never hardcode CPU/RAM specs for an SAP solution without a completed workload assessment.

## 5. Reference Three-Tier SAP S/4HANA Architecture

A production design distributes SAP applications and databases across Compute Engine with isolated subnets, IAM, HA, and backups.

~~~mermaid
flowchart TD
    U[Business users and integration clients] --> W[Private or controlled access]
    W --> D[SAP Web Dispatcher or entry tier]
    D --> A1[ABAP app server zone A]
    D --> A2[ABAP app server zone B]
    A1 --> C[ASCS/ERS HA virtual endpoints]
    A2 --> C
    A1 --> H[HANA primary zone A]
    A2 --> H
    H --> S[HANA secondary zone B]
    H --> B[Backint backup to Cloud Storage]
    S --> B
    M[Cloud Monitoring and Workload Manager] -.-> A1
    M -.-> H
    N[Cloud VPN or Interconnect] --> W
~~~

This simplified diagram is for learning purposes, not a certified blueprint. VIPs, health checks, cluster resource groups, storage mounts, and connectivity must follow official Google Cloud deployment guides for your chosen OS and SAP version.

### Tier Boundaries

- **Presentation / entry:** SAP GUI connections, HTTP(S), integrations, and Web Dispatcher where used.
- **Application:** primary and additional application servers running dialog and background workloads.
- **Central services:** ASCS/SCS, ERS, and enqueue lock state.
- **Database:** SAP HANA, data/log storage, backups, and replication.
- **Shared services:** DNS, NTP, directory/identity, monitoring, automation, and secure connectivity.

### Why Separate Tiers?

Application servers scale horizontally with load and database capacity. Central services and databases are stateful, requiring fundamentally different HA mechanisms from stateless HTTP tiers.

## 6. Compute Engine Selection and Capacity Reservations

Chosen machine types must appear on the relevant SAP certification list before optimizing for region, zone, CPU generation, and cost.

Verify:

1. Instance shape meets vCPU/memory sizing and SAP certification.
2. Machine type is available in target regions/zones.
3. Quotas and capacity are approved.
4. Instance placement supports HA/anti-affinity per official guides.
5. Sole-tenant or bare-metal options used only when required by workload, certification, or policy.
6. Reservation/capacity plans exist if failover/rebuilds cannot tolerate stockouts.
7. Ability to launch secondary/DR capacity during regional events.

### Capacity Is Not Quota

Large quotas do not guarantee physical stock exists in a zone at every moment. For production SAP systems with strict recovery mandates, evaluate capacity reservations and DR architectures to mitigate stockout risk during incidents.

### Never Blindly Auto-Rightsize Production Machines

Generic FinOps rightsizing recommendations do not automatically apply to SAP HANA. Any new machine type must be verified as SAP-certified, evaluated for downtime/HA impact, and re-sized formally. A smaller VM may cut monthly bills while invalidating SAP support or breaking SLOs.

## 7. SAP HANA Storage Design

SAP HANA processes data in memory while persisting data and transaction logs durably to disk. Volumes serve distinct functions and I/O profiles.

| Mount / Data Area | Purpose | Requirements |
|---|---|---|
| `/hana/data` | HANA data persistence | Capacity, throughput, and latency meeting SAP KPIs |
| `/hana/log` | Transaction log persistence | Low, consistent write latency and sufficient throughput |
| `/hana/shared` | Shared HANA architecture files | Shared filesystem or layout matching deployment model |
| `/usr/sap` | SAP binaries and instance directories | Proper OS protections and permissions |
| `/sapmnt` | Shared SAP application files where needed | NFS/shared service per SAP guides |
| Backup staging or `/hanabackup` | Temporary/target backup storage when used | Sized appropriately with safe cleanup rules |

Never assign identical disk sizes or classes to data, log, and shared volumes without checking requirements. Designs must follow **certified block storage** and SAP storage performance specifications.

### Persistent Disk, Hyperdisk, and NFS

Google Cloud supports multiple block storage offerings; disks used for SAP HANA must adhere to certification pages and planning guides. In HANA scale-out topologies, some configurations require NFS for shared volumes, where Filestore may fit if features and performance align. Never arbitrarily swap certified block storage for data/log volumes with NFS.

### RAID and Performance

Some layouts stripe multiple volumes to meet throughput/IOPS KPIs. Filesystem choices, RAID/LVM striping, and mount options must follow certified guides. Measure actual storage latency rather than trusting nominal datasheet bandwidth alone.

### Durability Is Not Backup

Zonal disks or synchronous replication do not replace point-in-time recovery. Accidental table drops, logical data corruption, or bad application writes replicate straight to secondaries; independent backups and restore drills remain mandatory.

## 8. Scale-Up vs. Scale-Out for SAP HANA

**Scale-up:** grows compute and memory on a single HANA host. Ideal when the workload fits within certified single-host limits and operational simplicity is prioritized.

**Scale-out:** distributes one HANA database across multiple hosts in a supported topology. Serves larger footprints at the cost of stricter storage, networking, host-role, and operational complexity.

| Dimension | Scale-Up | Scale-Out |
|---|---|---|
| Host count | One primary host (excluding HA secondary) | Multiple master/worker/standby roles per solution |
| Sizing | Pick a sufficiently large certified host | Aggregate sizing and data distribution |
| Networking | Important for clients and replication | Especially critical between HANA hosts |
| Shared filesystem | Per deployment guide | Typically mandates explicit shared storage |
| HA / DR | HSR + clustering per design | Includes host auto-failover and/or replication per option |
| Operations | Relatively simpler | More components and failure modes |

Never pick scale-out simply to use more servers. Evaluate the SAP application, database size, query patterns, product support matrices, and official scaling rules.

## 9. HA for SAP HANA: System Replication and Clustering

High availability (HA) minimizes downtime from single-host or single-zone failures. On Google Cloud, an HANA scale-up HA setup typically pairs two VMs across zones with SAP HANA System Replication (HSR), a Pacemaker OS HA cluster, health checks, and VIP failover routing.

~~~mermaid
flowchart LR
    A[ABAP application servers] --> V[HANA virtual IP]
    V --> L[Internal passthrough Network Load Balancer]
    L --> P[Primary HANA in zone A]
    L -.-> S[Secondary HANA in zone B]
    P -->|HSR| S
    C[Pacemaker and fencing] --> P
    C --> S
    H[Health checks] --> L
~~~

Google Cloud guides specify an **internal passthrough Network Load Balancer** for VIP/failover routing in many supported SAP HA architectures. Never try to port on-premises gratuitous-ARP floating IPs expecting them to work natively inside a VPC.

### Mandatory Components to Understand

- **HSR:** replicates database state from primary to secondary with defined modes and latency trade-offs.
- **Pacemaker:** monitors health and orchestrates failover via cluster resource agents.
- **Fencing / STONITH:** prevents two nodes from both claiming primary status during split-brain events.
- **VIP / Load balancer:** directs applications to whichever database holds the primary role.
- **Health checks:** must accurately reflect active/healthy primary status to prevent misrouting.
- **Quorum and failure policies:** govern when automated failover is permitted.

### Split-Brain Risk

If two HANA nodes both believe they are primary and accept independent writes, data diverges irreversibly. Never replace proper cluster fencing designs with homegrown DNS/VIP-flipping scripts.

### Validating Failover

In staging or approved production drills:

1. Confirm replication is healthy and secondary is in sync.
2. Record baseline requests/transactions.
3. Simulate node failure per certified runbook.
4. Observe fencing, promotion, and VIP rerouting.
5. Verify app reconnection, transaction integrity, and SLOs.
6. Measure RTO and any replication lag/data loss against RPO.
7. Rebuild replication topology and verify backups.

HA does not guarantee zero downtime, nor does it imply zero RPO across every replication mode and failure scenario.

## 10. HA for SAP NetWeaver: ASCS and ERS

At the application tier, SAP Central Services are critical because they host enqueue and message services. An HA design pairs ASCS/SCS with an Enqueue Replication Server (ERS) according to SAP and OS support models.

### Core Components

| Component | Function |
|---|---|
| ASCS | SAP Central Services for the ABAP stack |
| ERS | Protects enqueue lock table replication state |
| HA cluster software | Monitors and starts/moves roles per cluster rules |
| Virtual endpoints / VIP | Stable network addresses for applications |
| Internal load balancer | Routes traffic to the active instance via health checks |
| Shared filesystem | Stores shared profiles/files per deployment guide |

On Linux, certified RHEL/SLES HA cluster stacks are standard; on supported Windows-based SAP solutions, Windows Server Failover Clustering applies. Never apply Linux cluster templates to Windows or vice versa.

### Eliminating Single Points of Failure

Running two application servers behind a non-HA single ASCS still leaves a single point of failure. Likewise, clustering ASCS/ERS while relying on non-HA DNS, NFS, or identity services leaves residual single points of failure.

### Test Plan

- Perform a controlled stop of the active ASCS host.
- Observe enqueue lock preservation and recovery.
- Execute real SAP transactions rather than merely pinging the VIP.
- Cross-check cluster, application, and OS logs.
- Verify whether failback requires manual intervention or follows an approved procedure.

## 11. VPC Design, Subnets, and Enterprise Connectivity

SAP regularly integrates with MES, WMS, satellite ERPs, Active Directory, banking gateways, EDI partners, or reporting tools outside Google Cloud.

Networking requirements:

- Dedicated subnets for application, database, and management tiers where appropriate.
- Private IPs for databases and internal services.
- Cloud VPN or Cloud Interconnect sized to bandwidth and SLA needs.
- Consistent DNS and name resolution between on-premises and GCP.
- Firewall allowlists scoped by source, destination, port, and direction.
- Continuous monitoring of packet loss, jitter, latency, and throughput.
- Secure Google API access via Private Google Access or supported mechanisms.
- Clean CIDR planning with zero overlap between VPCs and datacenters.

~~~mermaid
flowchart TD
    O[On-prem SAP clients and integrations] --> H[Cloud VPN or Cloud Interconnect]
    H --> V[SAP VPC private subnets]
    V --> A[Application tier]
    A --> S[Central services]
    A --> D[HANA database tier]
    V --> M[Monitoring and secure management]
    B[Corporate DNS and identity] --> H
    D --> G[Approved Google APIs for backup and monitoring]
~~~

### Latency Directly Impacts SAP

A single SAP business step executes many round-trips between the application tier and database. Separating tiers across distant locations degrades response times regardless of VM CPU strength. For cross-zone HA, validate inter-zone latency and replication bandwidth against SAP/Google Cloud guidelines.

### Private Connectivity Availability

A single VPN tunnel is a single point of failure. Design redundant hybrid topologies and test failover across DNS, routing, and identity—not merely ping between two VMs.

## 12. DNS, NTP, OS, and Foundational Services

SAP is sensitive to hostnames, service discovery, timezones, and clock consistency.

Checklist:

- Hostnames/FQDNs aligned with SAP System IDs (SIDs) and naming standards.
- Bidirectional forward/reverse DNS resolution across apps, HANA, and ASCS/ERS.
- OS and cluster time synchronization using supported NTP setups.
- Kernel/OS packages, filesystems, swap/THP, and sysctl tuning per SAP Notes and Google guides.
- SAP-supported OS images and repository channels.
- Host firewalls, TLS/certificates, and credential hygiene.
- Linux UIDs/GIDs, ownership, and mount options matching SAP requirements.
- System logs, agent services, and access auditing.

Never grab a random OS tuning script off the Internet and apply it blindly across all HANA revisions. HANA, OS, machine generation, and memory layout must be evaluated together.

### Golden Images

Image pipelines can produce hardened, pre-tested base OS images. However, cloning a populated SAP instance containing SIDs, host keys, or persistent data requires a proper SAP system copy/refresh procedure. Never snapshot a production VM to spin up DEV without scrubbing identities and sensitive data.

## 13. Backing Up SAP HANA with Backint and Cloud Storage

Backups operate independently of HA. For SAP HANA, backups must capture data, transaction logs, and the backup catalog needed to recover to target points in time.

**Google Cloud's Agent for SAP** provides Backint capabilities integrating with SAP HANA's native backup/recovery engine to stream backups directly to Cloud Storage in supported setups. Exact support depends on agent and SAP HANA versions.

### Backup Design

| Component | Decisions Required |
|---|---|
| Data backups | Schedule and backup types suited to HANA |
| Log backups | Frequency aligned with point-in-time recovery goals |
| Backup catalog | Lifecycle management and metadata protection |
| Cloud Storage bucket | Location, storage class, IAM, retention policies |
| Encryption | Encryption in transit and at rest, CMEK if mandated |
| Access | Least-privilege service account; avoid static keys where possible |
| Retention | Align with legal and business retention policies |
| Restore drills | Measure RTO; verify data and catalog integrity |
| HA topology | Prevent two HANA nodes from colliding on backup roles |

Application/SAP backups do not schedule themselves simply because Backint is installed. Configure schedules via SAP mechanisms, monitor logs, and alert on failures.

### Permissions and Networking

The agent needs read/write object permissions on the target bucket and connectivity to Cloud Storage APIs. On Compute Engine, use host-attached service accounts or supported workload identity rather than dropping private key files into configs unless strictly unavoidable.

If VMs lack public IPs, configure Private Google Access or an approved Google APIs path. Never open broad Internet access just so Backint can push backups.

### Restore Is the True Measure of Success

A backup job reporting success does not prove restorability when:

- The log backup chain has a gap.
- The backup catalog is missing or corrupted.
- The CMEK key is inaccessible.
- Restore network throughput cannot meet RTO.
- The bucket location is unavailable during a regional outage.
- Operators lack restore permissions or run mismatched SAP/HANA versions.

Periodically restore into an isolated environment and compare actual data integrity and elapsed time against RTO/RPO.

## 14. Snapshots, Disk Backups, and Data Consistency

Block storage snapshots can play a role in SAP- and Google Cloud-supported backup/restore models. However, **raw infrastructure snapshots are not automatically SAP HANA application-consistent backups**.

To use snapshots safely:

1. Verify supported HANA, agent, and OS versions plus certified workflows.
2. Coordinate with HANA freeze/backup APIs or certified snapshot hooks.
3. Preserve data/log consistency and the backup catalog.
4. Track snapshot metadata, retention, and encryption keys.
5. Test restores and run SAP integrity checks.
6. Verify exact point-in-time recovery capabilities.

Never snapshot an arbitrary single disk and call it a DR strategy. For multi-volume HANA databases, cross-volume write consistency must be explicitly engineered and tested.

## 15. Cross-Region Disaster Recovery

Intra-region HA mitigates host or zone outages, yet never replaces **cross-region DR**. DR enables recovery from severe regional failures or primary data loss.

### Reference Model

~~~mermaid
flowchart TD
    A[Primary SAP region] --> H[HANA primary and local HA]
    H --> R[Cross-region HANA replication or approved DR mechanism]
    R --> S[DR HANA region B]
    H --> B[Backups with approved location policy]
    B --> S
    C[SAP app servers and ASCS in region A] --> D[Infrastructure templates and recovery procedures]
    D --> E[DR application tier in region B]
    S --> E
    E --> F[Controlled DNS routing and validation]
~~~

### RPO and RTO

- **RPO (Recovery Point Objective):** maximum tolerable data loss measured in time.
- **RTO (Recovery Time Objective):** maximum tolerable time to restore service.

Suppose the business mandates a 15-minute RPO and 2-hour RTO. Your design must prove those thresholds during live drills—not merely state them in architecture slides.

### What DR Requires

- Certified HANA replication and/or cross-region backup mechanisms.
- Access permissions and encryption keys available in the DR region.
- Supported machine types, capacities, and quotas ready in the recovery region.
- Application/ASCS/ERS tiers provisioned or templated in DR per recovery tier.
- DNS, routing, load balancing, and private hybrid connectivity.
- Procedures to fence or cut over integrations to avoid duplicate writes.
- Failback plan once the primary region recovers.

**Replication dutifully copies logical errors** like accidental deletes; independent, immutable backups with retention remain essential.

## 16. Encryption and IAM for SAP Systems

SAP workloads routinely store sensitive financial and personal data. Security must span from Google Cloud resources down into the SAP application layer.

### Least-Privilege IAM by Role

| Principal | Typical Permissions |
|---|---|
| Cloud platform admins | Create/modify networks, IAM, and infrastructure within authorized scope |
| SAP Basis operators | Operate SAP VMs, logs, and backups via scoped roles |
| Backup service identity | Read/write backup buckets strictly as required |
| Monitoring identity | Read metrics and emit telemetry per function |
| Deployment service account | Runs IaC deployments; never used for app runtime |
| Auditor | Read audit evidence with zero production write rights |
| Break-glass operators | Controlled emergency privileges, logged and promptly revoked |

Never grant project `Owner` or `Editor` to every SAP administrator for convenience.

### Defense in Depth

- VPC segmentation and least-privilege firewall rules.
- No public IPs on VMs wherever architecture allows.
- OS Login/IAP or policy-controlled bastion access.
- SSH key/certificate lifecycles paired with MFA/SSO.
- SAP user roles/authorizations and SNC/TLS for SAP communications.
- Managed HANA database users, roles, and secrets.
- Audit logging across Google Cloud, OS, HANA, and SAP.
- Encryption at rest, in backups, and in transit.
- Security Command Center and compliance posture checks where applicable.

### CMEK and Key Rotation

If organizational policy mandates CMEK, verify product/resource support, key locations, and post-recovery key availability. Disabling or destroying a key improperly can halt VMs/storage or render backups undecryptable. Key management is an integral part of DR.

## 17. Observing SAP with Agent for SAP and Workload Manager

Compute Engine monitoring alone reveals only part of VM health. SAP requires OS, HANA, application, and HA cluster telemetry.

Google Cloud's Agent for SAP collects SAP metrics and feeds Workload Manager evaluations against best practices. Supported features depend on OS and agent versions; for instance, Workload Manager evaluation metrics and process monitoring largely target Linux.

### Observability Layers

| Layer | Signals |
|---|---|
| Compute Engine | Availability, CPU, networking, disk latency, VM events |
| OS | Memory, filesystems, disk queues, time sync, process health |
| SAP Host Agent | Host metrics supporting SAP monitoring and support |
| SAP HANA | Memory utilization, CPU, SQL/service health, log backups, replication lag |
| ASCS/ERS/Pacemaker | Cluster resources, VIP/health status, failover events |
| ABAP application | Dialog response times, work processes, ABAP dumps, background jobs |
| Network | VPN/Interconnect, firewall drops, latency, packet drops |
| Backup / DR | Backup success, latest recovery point, restore timings |
| Cost | Compute/storage/egress, CUDs, spend by SID/environment |

### Workload Manager

Workload Manager evaluates supported SAP configurations using agent telemetry against best practices. Its findings guide review—they **do not automatically certify a system or guarantee SLO compliance**.

### Designing Meaningful Alerts

Go beyond "CPU > 80%." Alert on actionable symptoms:

- HANA replication out of sync or secondary unhealthy.
- Consecutive log backup failures.
- Data or log filesystems nearing capacity.
- Abnormal database connection counts or SQL latency.
- SAP application service outage.
- Unexpected ASCS/ERS failover.
- Private network connectivity disruption.
- Critical business batch jobs missing schedules.
- Projected RTO/RPO drifting out of compliance.

Every alert needs an owner, severity priority, and runbook.

## 18. Change Management and Maintenance Operations

SAP production follows strict business calendars like financial close, inventory counts, or payroll runs. Maintenance demands cross-team coordination.

### Common Change Types

- OS security patches.
- SAP kernel and support package updates.
- SAP HANA revision upgrades.
- Machine type or disk resizes.
- Pacemaker/HA configuration updates.
- Network, firewall, or VIP changes.
- Backup and monitoring agent upgrades.
- Transports and application releases.

### Change Workflow

1. Define objective, blast radius, and impacted systems.
2. Verify certification and compatibility.
3. Prepare a rollback plan and verified recoverable backups.
4. Validate in QAS/PRE-PROD first.
5. Run regression and performance tests.
6. Schedule a maintenance window clear of sensitive business periods.
7. Execute layer by layer per approved runbook.
8. Verify health, batch jobs, interfaces, and data integrity.
9. Monitor post-change stability and close the ticket.

Never auto-install arbitrary OS package updates the moment they release if they remain uncertified for your SAP landscape.

## 19. Automation and Infrastructure as Code

Terraform can declare projects, VPCs, subnets, firewalls, service accounts, Compute Engine instances, disks, load balancers, and buckets. SAP/HANA software installation, clustering, and DB tuning should follow supported automation playbooks.

Reference module layout:

~~~text
sap-platform/
  environments/
    dev/
    qas/
    prod/
  modules/
    network/
    sap-compute/
    sap-storage/
    sap-ha-lb/
    sap-backup/
    observability/
  documentation/
    certified-build-matrix.md
    sizing-worksheet.md
    failover-runbook.md
~~~

This illustrates a repository structure, not files created in this task.

### Illustrative Terraform Snippet

~~~hcl
variable "project_id" { type = string }
variable "zone" { type = string }
variable "certified_machine_type" { type = string }
variable "sap_subnetwork_self_link" { type = string }
variable "sap_service_account_email" { type = string }

resource "google_compute_instance" "sap_app" {
  name         = "sap-app-lab"
  project      = var.project_id
  zone         = var.zone
  machine_type = var.certified_machine_type

  boot_disk {
    initialize_params {
      image = "PROJECT/APPROVED-SAP-OS-IMAGE"
    }
  }

  network_interface {
    subnetwork = var.sap_subnetwork_self_link
  }

  service_account {
    email  = var.sap_service_account_email
    scopes = ["cloud-platform"]
  }

  labels = {
    workload    = "sap"
    environment = "lab"
  }
}
~~~

**This HCL snippet is insufficient for production SAP deployment.** Machine type and image values are placeholders to be replaced with certified combinations; you must still add disks, reservations, HA, health checks, OS tuning, IAM, SAP installation, and governance controls. Never repurpose an app lab VM as an HANA database template simply by changing labels.

### Pipeline Guardrails

- Static analysis, security policy checks, and Terraform plan reviews.
- Automated checks validating machine types/regions/OSes against an organization-maintained certification allowlist.
- Independent approvals for disk destruction, machine replacement, or downtime.
- Protected state backends with strict permissions and versioning.
- Keep passwords, SAP licenses, and private keys out of Terraform state wherever avoidable.
- Test DR/restore and HA clustering after major infrastructure changes.

## 20. Cost and FinOps for SAP

Enterprise SAP infrastructure runs large-memory VMs, high-performance storage, and standby redundancy, driving substantial spend. VM hourly price is only one slice of TCO.

### Cost Components to Model

| Category | Cost Drivers |
|---|---|
| Compute | Certified machine types, CPU, RAM, HA nodes, reservations |
| Storage | Data/log volumes, shared filesystems, snapshots, backup buckets |
| Network | Cross-zone, cross-region, Interconnect/VPN, egress |
| Monitoring | Metrics, logs, traces, retention, Workload Manager usage |
| Licenses | SAP, HANA, OS, and HA cluster software per contracts |
| Support | Google Cloud, SAP, and managed-service partner fees |
| Operations | SAP Basis, DBA, patching, backup drills, on-call |
| DR | Secondary capacity, replication, backups, networking |
| Migration | Tooling, testing, parallel run overlap, cutover |

### Rightsizing Is Not Simple

For SAP HANA, certified VM shapes and memory headroom keep costs elevated—yet remain mandatory. Never shrink instance sizes based purely on average utilization if doing so breaks certification or SLOs.

### Commitments and Reservations

Committed use discounts and capacity reservations help control predictable spend. Cross-check eligible machine types, commitment durations, resize flexibility, and migration timelines. Financial discounts alone do not automatically reserve physical capacity.

### FinOps KPIs

- Cost by SID, environment, and business owner.
- Cost per SAP business transaction where telemetry exists.
- Memory/CPU utilization across representative business windows.
- Storage growth and backup/restore spend.
- Idle DEV/QAS runtimes outside approved business hours.
- DR cost relative to business-mandated RTO/RPO tiers.

For QAS/DEV, scheduled VM shutdowns save money, provided automation follows proper SAP/HANA stop/start sequences and respects batch/integration windows. Never abruptly power off VMs mid-job.

## 21. Planning SAP Migrations to Google Cloud

An SAP migration is simultaneously an infrastructure, application, and data transformation project—not merely moving VM images.

### Assessment Phase

- Inventory SAP systems, SIDs, landscapes, and interfaces.
- Verify versions, supportability, and prerequisite SAP Notes.
- Size compute and storage from real workloads and database footprints.
- Map onto certified Compute Engine/OS/storage combinations.
- Measure existing network dependencies and latencies.
- Lock RPO/RTO targets and acceptable downtime windows.
- Review licensing, security, compliance, and operational readiness.
- Select migration methods aligned with SAP guidance.

### Migration Strategy Options

| Strategy | Example | Risks |
|---|---|---|
| Homogeneous system copy | Same database/platform per supported model | Cutover duration, data consistency |
| HANA System Replication | Migration or DR via supported HSR topologies | Replication lag, switchover complexity |
| Backup / restore | Back up at source and restore on GCP | Transfer duration, backup integrity |
| Database Migration Option / SAP tools | Database migration or upgrade per SAP tooling | Compatibility, heavy testing effort |
| Rebuild / redeploy | Stand up fresh infrastructure and migrate configs/data | Complex integrations and dependencies |

No single method suits every database or SAP release. Tools like Software Provisioning Manager or SUM/DMO must match exact versions and scenarios.

### Migration Waves

1. Sandbox or low-impact systems.
2. DEV/QAS landscapes and integrations.
3. PRE-PROD rehearsal using representative data.
4. Approved production cutover.
5. Stabilization, monitoring, and hypercare.
6. Decommissioning source systems after the rollback window closes.

## 22. Cutover and Business Validation

A cutover plan must define an exact timeline, owners, and clear abort criteria.

### Pre-Cutover

- Complete full backups and test restoration.
- Confirm HANA replication or data transfer sync state.
- Verify firewalls, DNS, routes, AD/SSO, and integrations.
- Measure queue backlogs and batch job states.
- Freeze unnecessary configuration changes.
- Verify GCP quotas, regional capacity, and IAM.
- Rehearse rollback to source systems if permitted.

### During Cutover

1. Announce downtime and business freeze.
2. Stop or isolate source writers per runbook.
3. Finish data sync/restore and validate consistency.
4. Switch SAP application endpoints, DNS, or routing.
5. Start application tiers in dependency order.
6. Run smoke tests and core business transactions.
7. Verify interfaces, batch jobs, printers, and external integrations.
8. Re-open access to users upon business owner approval.

### Post-Cutover

- Reconcile document/record totals across core business processes.
- Inspect queues, transports, batch jobs, and error logs.
- Monitor performance and database growth.
- Verify fresh backups run cleanly and restore paths work.
- Maintain the planned rollback/forward-fix window.
- Never decommission source systems prior to formal business sign-off.

## 23. Performance and Reliability Testing

An SAP load test must exercise real business transactions—not just ping an HTTP endpoint on a VM.

### Workloads to Simulate

- Dialog transactions with representative concurrent user counts.
- Peak-hour background jobs.
- Mass data loads, payroll, or financial close processes where in scope.
- SAP Fiori/UI and backend calls where applicable.
- HANA SQL queries against realistically sized datasets.
- Third-party and on-premises integration traffic.
- Concurrent backups, delta merges, and housekeeping during load.

### Metrics and Criteria

| Layer | Indicators |
|---|---|
| SAP business | End-to-end transaction times, error rates, job deadlines |
| ABAP / application | Response times, work process availability, queues, ABAP dumps |
| HANA | Memory, expensive SQL statements, CPU, log write rates, replication lag |
| Storage | Data/log latency and throughput |
| Network | RTT, packet loss, throughput, failover timings |
| HA | Detection, fencing, promotion, and reconnection times |
| DR | Actual RPO/RTO and business recovery verification |

A system showing low CPU can still crawl due to disk log latency or enqueue lock contention. Analyze end-to-end.

### Controlled Failure Testing

In a safe environment:

- Simulate stopping an application VM to verify load balancing.
- Fail over ASCS/ERS per runbook.
- Test HANA HSR switchover.
- Drop one VPN/Interconnect link.
- Restore a database from backup into an isolated environment.

Every test needs explicit rollback/abort triggers and owner approval. Never run destructive chaos tests during live production period-end closes.

## 24. Operating SAP with SLOs and Incident Workflows

Critical SAP systems need SLOs understandable by business owners:

- Availability of core business transactions.
- Response times by transaction class.
- Background job completion success rates.
- HANA replication health.
- Backup success and proven restorability.
- Data freshness in integrated reports.
- Rehearsed RTO/RPO compliance.

Illustrative SLO:

> During business hours, at least 99.9% of standard order-creation transactions succeed; p95 response time stays below business-approved thresholds; log backups never exceed the defined consecutive failure limit.

These figures are examples, not default SAP SLAs. Compute Engine, storage, or network SLAs alone do not equal end-to-end SAP application availability.

### Incident Runbook

A strong runbook documents:

1. How to confirm the incident and isolate the failing layer.
2. Contacts for SAP Basis, DBA, cloud SRE, and networking.
3. Cluster, VIP, and replication states to inspect first.
4. Permitted and strictly prohibited actions.
5. Escalation procedures to SAP, Google Cloud, or OS vendors.
6. Explicit conditions for failover and failback.
7. Preserving logs and audit evidence.
8. Business validation steps post-recovery.

## 25. Case Study: Designing Production SAP S/4HANA

Suppose a manufacturing enterprise runs:

- Production S/4HANA supporting finance, procurement, and warehousing.
- Three-year projected data growth.
- Heavy transaction spikes during month-end financial close.
- ERP connected to factories over private networking.
- Intra-region two-zone HA plus cross-region DR.
- QAS closely matching production for transport validation.

### Step 1 — Verify Inputs

Gather SAPS, HANA memory sizing, peak transactions, database growth, retention, RPO/RTO, integration maps, and licensing. Identify every component requiring SAP certification.

### Step 2 — Architecture Selection

- Application servers on certified Compute Engine configurations.
- ASCS/ERS HA per supported OS/SAP model.
- HANA scale-up primary/secondary with HSR/Pacemaker if sizing fits.
- Certified shared filesystems and data/log volumes.
- Internal passthrough load balancing for VIPs where required by guides.
- Redundant Cloud Interconnect/VPN links to manufacturing plants.

Never finalize exact machine types or disk sizes before sizing completes.

### Step 3 — Data Protection Design

- Backint data/log/catalog backups to least-privilege buckets.
- Backup schedules aligned with RPO and retention.
- Restore validation into QAS or an isolated restore lab.
- Cross-region HANA DR via replication and/or cross-region backups as required.
- Plan to keep encryption keys and DNS operational if the primary region fails.

### Step 4 — Security and Operations

- Separate service accounts for deployment, runtime agents, monitoring, and backups.
- Private connectivity and least-privilege firewalls.
- Shared runbooks bridging SAP Basis and cloud SRE teams.
- Workload Manager / Agent for SAP and Cloud Monitoring configured end-to-end.
- Patching workflow enforcing QAS testing and formal approvals.

### Step 5 — Acceptance Testing

| Check | Criterion |
|---|---|
| Certification | Machine/OS/storage/SAP versions fully supported |
| Functional | Finance and procurement transactions accurate |
| Performance | Month-end peak meets approved targets |
| HA | HANA and ASCS/ERS failovers meet SLOs |
| Backup | Restores from Cloud Storage succeed |
| DR | Cross-region drills meet RPO/RTO |
| Security | IAM, SAP roles, auditing, and encryption compliant |
| Cost | Spend and capacity remain within forecast |

### Step 6 — Go-Live

Finalize the cutover checklist and rollback go/no-go checkpoints, monitor stability throughout hypercare, benchmark performance against baseline, and hand over to steady-state operations. Close the project only after business owners sign off.

## 26. Design Pitfalls to Avoid

| Pitfall | Consequence | Solution |
|---|---|---|
| Picking VMs by cheapest RAM | May lack SAP certification | Verify machine types and SAP Notes |
| Sizing HANA from disk capacity | Memory/CPU miss real demand | Use SAP sizing and real telemetry |
| Using uncertified storage layouts | High log latency and support risk | Follow SAP HANA planning guides |
| Treating zonal disks as backups | Data loss on accidental delete or corruption | HANA Backint and restore drills |
| Enabling HSR without fencing | Split-brain and data corruption | Configure Pacemaker/fencing per guides |
| Using on-prem gratuitous-ARP VIPs | Failover routing breaks in VPC | Use Google Cloud-supported VIP mechanisms |
| Implementing HA without DR | Vulnerable to regional outages | Maintain a cross-region recovery plan |
| Skipping DR capacity reservations | No capacity available during disaster | Plan capacity and reservations |
| Public IPs and Owner IAM on all SAP VMs | Expanded attack surface | Private networking and least-privilege IAM |
| Monitoring only VM CPU | Misses SAP/HANA failures | Deploy agents, app/DB metrics, and SLOs |
| Auto-patching without SAP version checks | Incompatibilities / lost support | Check certifications, test QAS, use change control |
| Relying on unverified disk snapshots for HANA | Restores can fail silently | Use HANA-aware backup/recovery workflows |
| Ignoring licensing and support alignment | Wrong TCO and support gaps | Clarify RACI, licensing, and contracts |
| Skipping business validation at cutover | SAP boots while business logic fails | Reconcile financials/data and get sign-off |

## 27. Production Readiness Checklist

### Architecture and Certification

- [ ] SAP solutions and DEV/QAS/PRD/DR landscapes clearly defined.
- [ ] Machine types, OSes, storage, and software versions verified as certified/supported.
- [ ] SAPS, HANA memory, IOPS, throughput, and network sizing verified.
- [ ] Regions, zones, capacity, and quotas sufficient for failure and recovery scenarios.
- [ ] Clear RACI and support paths across SAP, Google Cloud, and partners.

### Networking and Security

- [ ] Private connectivity, DNS, and time sync meet requirements.
- [ ] Firewalls and service identities enforce least privilege.
- [ ] SAP authorizations, HANA roles, and admin access strictly controlled.
- [ ] Logging, auditing, backup encryption, and CMEK (if required) have runbooks.
- [ ] Passwords and keys kept out of source code and Terraform state wherever avoidable.

### HA and Data Protection

- [ ] HANA HSR, clustering, fencing, VIPs, and health checks tested end-to-end.
- [ ] ASCS/ERS HA verified per SAP guides.
- [ ] Data/log mounts meet KPIs and emit telemetry.
- [ ] Data/log/catalog backups scheduled and monitored for failures.
- [ ] Restore tests and DR drills meet actual RPO/RTO targets.

### Operations and Cost

- [ ] SAP Host Agent / Google Cloud's Agent for SAP configured on supported versions.
- [ ] Dashboards cover SAP/HANA/OS/VM/networking with business-aligned alerts.
- [ ] Incident, patching, and change workflows define owners, escalation, and rollbacks.
- [ ] DEV/QAS/PRD isolated by IAM and data boundaries.
- [ ] Compute, storage, licensing, support, and DR costs forecasted.
- [ ] Hypercare plan and business sign-off established for go-live.

## 28. Official Documentation to Cross-Reference

Key references (contents and certification lists evolve over time):

- [Overview of SAP on Google Cloud](https://docs.cloud.google.com/sap/docs/overview-of-sap-on-google-cloud)
- [SAP certifications for Google Cloud](https://docs.cloud.google.com/sap/docs/sap-certifications)
- [SAP HANA planning guide](https://docs.cloud.google.com/sap/docs/sap-hana-planning-guide)
- [SAP HANA high-availability planning guide](https://docs.cloud.google.com/sap/docs/sap-hana-ha-planning-guide)
- [SAP NetWeaver HA planning guide](https://docs.cloud.google.com/sap/docs/netweaver-ha-planning-guide)
- [Google Cloud's Agent for SAP](https://docs.cloud.google.com/sap/docs/agent-for-sap/latest)
- [Backup and recovery with Backint](https://docs.cloud.google.com/sap/docs/agent-for-sap/latest/backint-backup-recovery)
- [Workload Manager for SAP workloads](https://docs.cloud.google.com/workload-manager/docs/evaluate/set-up-agent-for-sap)

Also consult relevant **SAP Notes** and the **SAP Certified and Supported SAP HANA Hardware Directory** matching your exact application, HANA, OS, and hardware versions. Never substitute illustrative examples from this lesson for certified deployment guides.

**Conclusion:** Architecting SAP on Google Cloud means aligning SAP software with Compute Engine, storage, VPC networking, security, and enterprise operations. Sound architectures start with workload sizing and certification, protect data through HANA-aware backups, implement HA/DR with tested fencing and failover, monitor down to business transactions, and govern changes through formal approvals. Only when every layer is validated through real testing can an enterprise run SAP reliably and cost-effectively on Google Cloud.
