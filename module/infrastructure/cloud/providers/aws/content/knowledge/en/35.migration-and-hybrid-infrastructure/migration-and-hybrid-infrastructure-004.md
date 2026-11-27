# AWS Application Migration Service and Server Migration

Migrating servers to AWS is often one of the first steps when an organization relocates a data center or moves workloads from another cloud provider. The challenge goes beyond copying disks. The migration team must keep source systems running while data transfers, prepare networking and access permissions at the target, validate applications before moving users, and execute cutover within a predictable downtime window.

AWS Application Migration Service (AWS MGN) was renamed **AWS Transform MGN** in June 2026. The service retains its core APIs and replication technology while serving as the rehosting engine used by AWS Transform. Teams can operate directly in the AWS Transform MGN console or use AWS Transform's agentic workflows to assist with discovery, migration wave planning, network preparation, and rehosting. This lesson uses AWS Transform MGN when describing the current service and notes AWS Application Migration Service / AWS MGN when explaining legacy names in earlier documentation or interfaces.

AWS Transform MGN converts physical, virtual, or other cloud-hosted servers into Amazon EC2 instances by continuously replicating block-level data into an AWS staging area. Once initial data syncs, subsequent changes continue replicating. Teams can launch test instances to validate applications, then perform cutover to move workloads onto EC2 with much shorter downtime than a manual one-time copy.

This lesson falls within the CLOUD_PROVIDERS_AWS scope: selecting and deploying AWS infrastructure with operational readiness, security, resilience, and cost control. The focus is on preparing source servers, designing the staging area, configuring replication and launch settings, testing, cutover, troubleshooting common issues, and coordinating MGN with other migration services.

## 1. Learning Objectives

After completing this lesson, you will be able to:

- Explain the role of AWS Transform MGN in a server rehosting strategy.
- Distinguish MGN from AWS DMS, AWS DataSync, AWS Elastic Disaster Recovery, and migration tracking tools.
- Describe the architecture of the replication agent, replication server, staging area, and EC2 launch template.
- Verify OS, hardware, server identity, and network connectivity prerequisites before installing the agent.
- Design staging subnets, operational subnets, IAM permissions, encryption, and private connectivity.
- Configure replication settings, launch settings, and post-launch actions.
- Plan testing, cutover, rollback, and post-migration verification.
- Estimate MGN service costs, staging resources, and test/cutover instances.
- Organize migrations by application and wave to reduce risk in multi-server environments.

## 2. Rehosting and the Role of AWS Transform MGN

### 2.1. What Is Rehosting?

Rehosting, often called lift-and-shift, moves servers and workloads to target infrastructure with minimal changes to the application. Rather than rewriting the application or altering architecture in the initial move, teams bring the OS and block data to EC2, adjust necessary infrastructure settings, and verify the application operates properly.

Rehosting is appropriate when:

- A data center must close or a hosting contract is expiring.
- The business must migrate workloads quickly to eliminate reliance on aging hardware.
- Legacy applications are difficult to modify or lack time for refactoring.
- Teams prefer moving infrastructure first and modernizing applications in a later phase.
- Servers need to move across AWS Regions or AWS accounts under a validated plan.

Rehosting does not automatically make an application cloud-native. Migrated servers retain their prior configuration, dependencies, OS versions, and scaling limits. Once stabilized, teams can evaluate replatforming, refactoring, repurchasing, or retiring.

### 2.2. What Does AWS Transform MGN Do?

AWS Transform MGN automates server replication and target instance launches:

1. Install the AWS Replication Agent on supported source servers.
2. The agent tracks block-level changes and transmits data to AWS.
3. A replication server in the staging area writes data to staging EBS disks and creates snapshots per service mechanics.
4. MGN continuously syncs changed blocks to keep replication lag low.
5. On request, MGN launches a test or cutover instance using launch settings and the EC2 launch template.
6. After cutover completes, the target server operates as an AWS workload; teams optimize, monitor, and manage it like any EC2 instance.

MGN primarily solves server rehosting. It does not replace dependency assessment, VPC design, DNS cutover, license verification, application reconfiguration, database schema migration, or post-migration operational planning.

### 2.3. Service Naming and Current Access Methods

AWS Application Migration Service was renamed AWS Transform MGN on June 8, 2026. Its APIs remain in the `mgn` namespace, and older documentation may still refer to AWS Application Migration Service or AWS MGN. Recognize these as the same rehosting technology.

Two working modes are available:

- **AWS Transform MGN console:** teams directly control replication settings, launch settings, testing, and cutover per server.
- **AWS Transform workflow:** agentic workflows assist with discovery, migration waves, landing zones, network setup, and rehost preparation. During the rehosting phase, teams can still switch to the MGN console for manual control.

Both paths share the same replication engine. Using agentic workflows does not eliminate the need to verify inventory, permissions, networking, launch templates, and test outcomes.

### 2.4. What MGN Does Not Replace

| Need | Appropriate Tool or Activity |
|---|---|
| Rehosting OS and block disks to EC2 | AWS Transform MGN |
| Migrating database data and converting schemas | AWS Database Migration Service (AWS DMS) |
| Copying files and objects between storage systems | AWS DataSync or an appropriate file transfer tool |
| Disaster recovery and failback to source environment | AWS Elastic Disaster Recovery (AWS DRS) |
| Broader discovery, assessment, and migration planning | AWS Transform and appropriate discovery/assessment tools |
| VPC, subnet, routing, DNS, firewall, and hybrid connectivity design | Amazon VPC, Direct Connect, Site-to-Site VPN, and related networking services |

MGN is not a logical database migration tool. If an application uses a database with strict consistency requirements or requires an engine change, plan the database separately—often combining DMS or native database backup/restore workflows.

## 3. Replication Architecture

### 3.1. Core Components

**Source server** is the physical server, VM, or cloud instance running the application. It must run a supported OS and CPU architecture.

**AWS Replication Agent** is installed on the source server. It reads block-level changes, manages replication progress, and sends data to the staging area. Installation requires OS administrative privileges and proper network connectivity.

**Staging area subnet** is a subnet in the target VPC dedicated to replication servers and supporting resources. It serves as the intermediate zone receiving and storing data while source servers remain live. AWS recommends isolating a dedicated staging subnet for easier management, monitoring, and network control.

**Replication server** is an EC2 instance launched by MGN in the staging area to receive and process replication data. Instance sizing and count depend on workloads, throughput, and configuration settings.

**Staging EBS disks and snapshots** store replicated block data. Staging volume capacity and performance directly impact sync speed, completion time, and cost.

**EC2 launch template** defines how MGN creates test/cutover instances, including instance type, subnet, security groups, storage, and other EC2 attributes.

**Operational subnet** is the subnet where test and cutover instances run. It normally resides in the target application VPC, separate from the staging subnet.

### 3.2. Data Flow

~~~mermaid
flowchart LR
    A[Source server] -->|AWS Replication Agent| B[Protected transport]
    B --> C[Replication server]
    C --> D[Staging EBS disks]
    D --> E[Recovery snapshots]
    E --> F[MGN launch workflow]
    F --> G[Test EC2 instance]
    F --> H[Cutover EC2 instance]
    H --> I[Target application VPC]
~~~

Replication runs continuously while preparing for migration. When a test or cutover instance launches, MGN creates the target server from replicated data. The replication agent is removed from test/cutover instances during launch per service behavior; the target instance does not continue running as a source server.

### 3.3. Initial Sync and Continuous Replication

Once the agent is installed, MGN performs an initial sync to copy initial data from supported volumes. This is typically the heaviest data transfer phase and varies in duration based on volume size, block change rate, bandwidth, and source/target performance.

After initial sync, continuous replication transmits only changed blocks. This keeps the target copy close to source state without re-copying entire volumes. Operators monitor replication status and lag to determine when testing or cutover can begin.

Low replication lag does not mean the application is ready for cutover. Teams must still validate dependencies, network configuration, permissions, application data, and planned downtime windows.

### 3.4. Block Storage Boundaries

MGN replicates block devices visible to the operating system. SAN volumes presented as block devices can typically be replicated like local disks if service requirements are met. Network file shares such as NFS or SMB/CIFS are not transferred as directly attached block disks; use a file transfer tool or design a dedicated storage migration. If an NFS server stores data on local block disks, identify which server actually owns the storage and install the agent where replication is needed.

Never assume every mount point or storage appliance is protected by MGN. Inventory must distinguish local/block volumes, SAN LUNs, NFS shares, SMB shares, object storage, and database-managed storage.

## 4. Assessing and Preparing Source Servers

### 4.1. Pre-Agent Inventory

Collect at minimum:

- Hostname, IP address, DNS name, OS, and version.
- CPU, RAM, CPU architecture, kernel, and boot mode.
- Disk count, capacity, partitions, filesystems, and storage types.
- Used capacity and hourly/daily data change rates.
- Applications, services, processes, ports, and dependencies.
- Databases, file shares, licenses, certificates, and associated secrets.
- Domain membership, DNS, NTP, firewalls, and external system connections.
- Business owner, criticality, RPO/RTO, and cutover windows.

Group servers by application, dependencies, and startup order. A multi-tier application may require databases and identity services ready before application servers, followed by load balancers and user traffic.

### 4.2. Supported Operating Systems and Architectures

MGN supports many Windows and Linux distributions, though the list evolves over time. Check the **Supported Operating Systems** documentation at deployment time for the specific Region and kernel version. Never rely on an outdated OS list in an old runbook because AWS adds and deprecates versions.

General prerequisites to verify:

- OS is on the supported list.
- System uses x86 architecture; MGN does not support 32-bit OS or ARM sources per current agent requirements.
- Server hardware identifier is stable and unique. Cloned VMs must have distinct identifiers before installing the agent.
- Server has sufficient RAM and free disk space for the agent.
- Linux has matching kernel headers for the running kernel, bootloader, and distro-specific required packages.
- Installation requires `root` or `sudo` privileges; Windows requires Administrator privileges and version-specific prerequisites.
- Unsupported fully paravirtualized configurations are not used.

Specific prerequisites vary between Linux and Windows. For example, Linux requires `/tmp` to be writable and executable during agent installation; some distributions require `kernel-devel` or `linux-headers` matching the exact running kernel.

### 4.3. Capacity and Disk Size

Before installing the agent, confirm free space on the root filesystem, available RAM, and temporary installer space. Current installation prerequisites specify at least 2 GB free on root and 300 MB RAM for the agent; Linux also has specific requirements for `/tmp` and `/boot` depending on configuration.

Per November 2026 release notes, MGN expanded source disk support up to 64 TiB. Disks larger than 16 TiB require General Purpose SSD (`gp3`) or Provisioned IOPS SSD (`io2`) staging disks. Review the latest release notes and disk size documentation before migrating large volumes, as older guides may still reference a 16 TiB limit.

### 4.4. License and OS Dependency Checks

Migrating a server does not automatically transfer all software usage rights. Carefully review:

- Windows Server licensing and license-included vs. BYOL options.
- RHEL, SUSE, or Linux vendor subscriptions.
- Microsoft SQL Server licensing and license mobility where supported.
- Software with license keys bound to MAC address, hardware ID, or hostname.
- Drivers, kernel modules, antivirus, EDR, backup agents, and monitoring software.
- Certificates, secrets, service accounts, and hardcoded IP configurations.

Verify license agreements and vendor requirements before migrating production. Never treat a successful EC2 boot as proof of license compliance.

## 5. Preparing the AWS Target Environment

### 5.1. Selecting Region and Account

Initialize MGN in the target Region where servers will be migrated. Define:

- AWS account owning the workload.
- Migration management account if using AWS Organizations / delegated administrator.
- VPC, CIDRs, subnets, and Availability Zones.
- Staging area subnet and operational subnet.
- Connectivity to on-premises or source cloud during replication and hybrid operation.
- Target services such as EC2, EBS, FSx for NetApp ONTAP, or database targets per architecture.

MGN is a regional service. Do not assume settings, source servers, or staging areas in one Region appear automatically in another. For multi-Region migrations, plan each target Region separately and verify service availability.

### 5.2. Staging Subnet and Operational Subnet

Dedicate the staging subnet to replication servers and supporting resources. Isolating staging from application subnets helps:

- Restrict security groups and routes cleanly.
- Monitor replication traffic separately.
- Prevent impact on production workloads.
- Forecast staging resources and costs clearly.

The operational subnet hosts test and cutover instances. Select subnets aligned with the target VPC architecture, routing, load balancers, DNS, firewalls, directory services, and required dependencies.

If test instances share subnets and IP addresses with production sources, IP conflicts or unintended system connections can occur. Design isolated test VPCs/subnets or equivalent isolation controls. When testing Active Directory, strictly prevent test domain controllers from routing back to production networks where clients might authenticate against the wrong domain controller.

### 5.3. Network Connectivity and Firewalls

Required network flows per MGN documentation:

| Source | Destination | Protocol / Port | Purpose |
|---|---|---|---|
| Source server | Regional MGN API endpoint | TCP 443 | Replication control and registration |
| Source server | Staging area subnet / replication server | TCP 1500 | Block replication data transfer |
| Staging area subnet | MGN API endpoint | TCP 443 | Service communication and orchestration |
| Staging area subnet | Amazon S3 and EC2 endpoints | HTTPS / TCP 443 | Downloading components, packages, and API calls |

All traffic is encrypted with TLS per service design. Never apply SSL interception between source/replication servers and MGN API endpoints. Proxies or firewalls modifying TLS certificates or payloads can break the agent.

In environments without direct Internet access, use AWS Direct Connect, Site-to-Site VPN, or appropriate private connectivity for data transfer. Verify routing, DNS, MTU, bandwidth, latency, security groups, network ACLs, and firewalls on both ends.

### 5.4. Estimating Bandwidth

Required bandwidth depends on:

- Total volume needing initial sync.
- Block change rate during peak hours.
- Number of servers replicating concurrently.
- Migration window and deadline for completing initial sync.
- Remaining bandwidth after accounting for application traffic.

Initial transfer estimate:

\[
\text{Transfer time (seconds)} \approx \frac{\text{Data volume (bits)}}{\text{Effective throughput (bits/second)}}
\]

Effective throughput is lower than nominal bandwidth due to overhead, packet loss, disk I/O limits, throttling, and competing traffic. Test a small batch first, measure replication throughput and lag, then scale up the wave size.

### 5.5. IAM and Administrative Permissions

Separate MGN operator permissions from service role permissions and target EC2 instance permissions. Administrators need permissions to initialize MGN, configure replication/launch settings, view status, and launch test/cutover instances. MGN also requires permissions to create and manage replication resources via its service role/policies.

Principles:

- Use AWS managed policies or organization-controlled policies aligned with current documentation.
- Scope permissions strictly to the migration account and Region.
- Separate personnel allowed to configure settings from those authorized to approve production cutovers.
- Use IAM roles and temporary credentials instead of long-lived access keys.
- Scope target EC2 instance profiles per application.
- If using post-launch actions, configure AWS Systems Manager permissions and SSM document execution rights.
- Audit changes via CloudTrail and review permissions after migration completes.

Never copy an old IAM policy from historical docs without checking currently supported service names, actions, and trust relationships.

## 6. Configuring MGN

### 6.1. Initializing the Service

In the target Region:

1. Open the AWS Transform MGN console.
2. Initialize the service and accept required configurations/roles.
3. Review the account-level replication settings template.
4. Select the staging area subnet and default replication settings.
5. Review launch settings and post-launch settings templates.
6. Prepare EC2 launch templates, IAM roles, and VPC resources.

Account-level templates standardize configuration for new servers. Individual source servers may still require workload-specific overrides. After adding servers, verify effective settings before starting replication.

### 6.2. Installing the AWS Replication Agent

General process:

1. Confirm OS, kernel, disks, RAM, server identifier, and networking.
2. Download the installer per MGN instructions in the target Region.
3. Run the installer as `root`/`sudo` on Linux or Administrator on Windows.
4. Supply registration credentials per console guidance and confirm the Region.
5. Verify the source server appears in the MGN console.
6. Monitor agent health and initial sync progress.

Never install the agent on a cloned VM sharing the same hardware identifier as an already-registered server. MGN may treat it as the same source server, overwriting the record and interrupting replication for the original machine.

Effective October 2026, agentless replication is no longer available for new deployments; AWS recommends agent-based replication for new migrations. If an older environment used agentless replication, review transition guidance and support scope before making changes.

### 6.3. Replication Settings

Replication settings govern how data replicates into the staging area:

- Staging area subnet and Availability Zone.
- Replication server instance type or capacity selection mode.
- Staging disk type, IOPS, and throughput.
- Bandwidth throttling if needed to protect WAN links.
- Encryption configuration and KMS key per policy.
- Snapshot and replication behavior options.

Size staging disks with enough performance to keep pace with source write rates. Undersized staging servers or disks cause rising replication lag, prolonged initial syncs, or failed replication jobs. Over-provisioning capacity across hundreds of servers unnecessarily increases costs without commensurate benefit.

### 6.4. Launch Settings and EC2 Launch Templates

Launch settings define how test and cutover instances are created:

- Instance type or right-sizing mode.
- VPC and subnet.
- Security groups.
- Private IP and network interfaces.
- IAM instance profile.
- EBS volume type, size, IOPS, throughput, encryption, and delete-on-termination.
- Tenancy, licensing options, and other EC2 attributes.
- Boot mode and OS-related settings.

MGN creates an EC2 launch template when a source server is added. Treat the launch template as a target configuration requiring review, not something to ignore. Automatic instance type selection to match OS/CPU/RAM can override the template's instance type depending on the selected right-sizing mode.

Updating launch settings generally affects only subsequent test/cutover launches. If a test instance is already running, updating the template does not modify the running instance; relaunch to validate new settings.

### 6.5. Post-Launch Actions

Post-launch actions automate tasks after test/cutover instances launch. The framework uses AWS Systems Manager documents and can include:

- Installing or configuring SSM Agent where supported by the OS.
- Installing CloudWatch Agent or security agents.
- Validating disks, processes, HTTP/HTTPS endpoints, and connectivity.
- Changing licenses or performing supported OS upgrades.
- Running custom application configuration scripts.

Post-launch actions must be enabled at the account template level or per source server. Check document versions, execution order, OS filters, parameters, and SSM permissions. An action targeting the wrong OS or lacking permissions may be skipped or fail.

Effective November 2026, MGN added source actions to execute scripts on source servers during migration via the MGN connector and scripts stored in Systems Manager Parameter Store. Source actions differ from post-launch actions: one runs on the source before/during migration, while the other runs after the target instance launches. Check release notes to verify feature availability, Regions, and connector permissions before use.

## 7. End-to-End Migration Workflow

### 7.1. Phase 1: Preparation

1. Identify applications and dependencies.
2. Group servers into migration waves.
3. Choose target Region, account, VPC, and subnets.
4. Prepare IAM, firewalls, staging area, and launch settings.
5. Verify OS support, disk layouts, licensing, and networking.
6. Define RPO/RTO, testing windows, and cutover windows.
7. Establish a rollback plan and approvers.

### 7.2. Phase 2: Replication

1. Initialize MGN in the target Region.
2. Install the agent on source servers.
3. Confirm source servers appear in the console.
4. Monitor initial sync through completion.
5. Verify continuous replication is active.
6. Monitor lag, replication servers, staging disks, and snapshots.
7. Resolve errors before moving to testing.

Never start cutover simply because a source server is registered. Initial sync must finish and replication must stabilize. For write-heavy workloads, measure lag during peak hours rather than only checking during quiet periods.

### 7.3. Phase 3: Test Launch

Once initial sync completes:

1. Review launch settings.
2. Verify subnet, security groups, instance type, disks, and IAM instance profile.
3. Launch a test instance.
4. Inspect boot behavior, system logs, disks, filesystems, and network interfaces.
5. Verify DNS, Active Directory, NTP, certificates, secrets, and dependency connectivity.
6. Run smoke, integration, performance, and critical business tests.
7. Verify data integrity and application ability to serve test traffic.
8. Log issues, fix configuration, and relaunch if needed.

Test instances should run in an isolated environment. Especially for domain controllers or systems sharing production hostnames/IPs, prevent test traffic from leaking into production networks unexpectedly. If an application needs a database or API to test against, stand up corresponding test dependencies or configure controlled routing.

After testing, finalize testing per MGN workflow and terminate unnecessary test instances. Test instances are not free; EC2, EBS, and associated resources incur standard charges.

### 7.4. Phase 4: Cutover Preparation

Before the cutover window:

- Every server in the application has passed testing.
- Replication lag is within acceptable thresholds with no open errors.
- Launch settings and post-launch actions are reviewed.
- DNS TTLs, load balancers, firewalls, and routes have transition plans.
- Application, database, network, security, and business owners confirm timing.
- Backups/snapshots and recovery plans meet workload policy.
- Checklists and go/no-go approvers are ready.

Do not wait until cutover night to discover that a target instance lacks permissions, cannot resolve DNS, or cannot reach a license server.

### 7.5. Phase 5: Cutover

A typical cutover sequence:

1. Enforce application change freeze as planned.
2. Announce the start of the maintenance window.
3. Stop write services or place the source application into maintenance mode.
4. Confirm replication lag meets the required threshold.
5. Launch cutover instances from MGN.
6. Verify target instances boot and post-launch actions succeed.
7. Validate final data, connectivity, and health checks.
8. Switch DNS, load balancers, or routing to target servers.
9. Open traffic incrementally and monitor errors/latency.
10. Obtain business owner confirmation that workflows operate normally.
11. Finalize cutover and archive source servers per procedure.

MGN shortens transition time through prior replication, but it does not guarantee identical downtime for all workloads. Actual downtime depends on the application, database, final sync, DNS, networking, and verification steps.

### 7.6. Phase 6: Post-Migration Stabilization

After cutover:

- Monitor CPU, memory, disk I/O, network, processes, and application metrics.
- Inspect OS and application logs.
- Verify backups, monitoring, alerts, patching, and security agents.
- Review IAM permissions and security groups for least privilege.
- Validate DNS, certificates, licensing, and external integrations.
- Compare performance and costs against pre-migration baselines.
- Update CMDB, network diagrams, runbooks, and operational documentation.
- Decommission source servers only after the stabilization window and formal approval per policy.

## 8. Example: Migrating a Three-Tier Application

### 8.1. Current State

An internal system has three server tiers in a data center:

| Tier | Role | Key Dependencies |
|---|---|---|
| Web | Receives HTTPS requests and serves UI | DNS, load balancer, application tier |
| Application | Executes business logic and internal APIs | Database, Active Directory, message broker |
| Database | Stores transactional data | Storage, backup, DNS, and licensing |

The team wants to move servers to AWS first, then evaluate database engine changes or application refactoring later. Therefore, MGN fits OS and block storage rehosting; logical database migration, if changing engines, becomes a separate workstream.

### 8.2. Target Design

- Create a production VPC with private subnets across at least two AZs per availability requirements.
- Create a dedicated staging subnet for MGN replication resources.
- Create operational subnets for test/cutover EC2 instances.
- Establish Site-to-Site VPN or Direct Connect so replication and hybrid dependencies traverse private links.
- Create separate security groups for web, application, database, and staging.
- Prepare target DNS, Active Directory connectivity, load balancers, and monitoring.
- Define EC2 instance types, EBS volume types, and encryption keys.

### 8.3. Dividing into Migration Waves

A phased plan might look like:

1. Wave 0: test networking, domain, DNS, monitoring, and a non-critical server.
2. Wave 1: database test replica or database server under the dedicated data strategy.
3. Wave 2: application servers once database and identity dependencies are ready.
4. Wave 3: web servers, load balancer, and DNS cutover.

Actual sequencing must reflect dependencies and application compatibility. Databases do not have to migrate via MGN simultaneously with application servers; explicitly decide whether the database is rehosted as-is or migrated via DMS or backup/restore.

### 8.4. Testing and Cutover

During testing:

- Launch database and verify volumes, filesystems, services, and data.
- Launch application servers in a test subnet connected to the test database.
- Launch web tier and test end-to-end flows.
- Verify authentication, DNS, certificates, outbound APIs, and logging.
- Run performance tests to validate instance sizing.

During cutover:

- Stop writes on the source application.
- Wait for replication lag to reach threshold.
- Launch database cutover first and verify health.
- Launch application tier and verify connectivity.
- Switch web/load balancer and DNS.
- Monitor initial transactions and reconcile data.

If an issue occurs, rollback decisions depend on whether the target has accepted writes. Once both source and target have accepted writes, simply pointing DNS back to source will not preserve consistency. You need a reconciliation or compensation process before reopening source.

## 9. Security and Data Protection During Migration

### 9.1. Encryption and Transport

Replication data travels over TLS-encrypted connections. Staging data resides on AWS storage and must be configured with encryption per organizational policy. Verify KMS keys, key policies, and key usage permissions for service roles and replication resources.

When using private connectivity, verify routes and firewalls do not leak traffic onto unintended paths. If using proxies or inspection appliances, exempt AWS-required MGN endpoints from TLS interception.

### 9.2. Privileges on Source Servers

The agent reads block devices and operates at the OS level. Ensure you:

- Install agents using approved administrative accounts.
- Verify installers come from official AWS sources.
- Restrict outbound connectivity to required endpoints and ports.
- Monitor agent processes and logs.
- Uninstall the agent or clean up configuration after migration completes per procedure.

Never store source server admin credentials in unprotected inventory files or tickets.

### 9.3. Test Environments

Test instances may contain production data. Protect test VPCs and accounts with production-grade controls:

- Restrict inbound access.
- Avoid public IPs unless strictly required.
- Use masked data where workflows permit.
- Prevent test instances from sending real emails/SMS or calling production payment gateways.
- Prevent test instances from affecting production domain controllers, databases, or message brokers.
- Clean up test resources when finished.

### 9.4. Cutover and Sensitive Data

Before transferring data, review data classification, residency, retention, encryption, and access controls. If migrating to another Region, assess legal regulations and data owner requirements.

## 10. MGN Costs and Related Resources

### 10.1. Free Service Usage Period

Per current pricing FAQs, each source server receives 2,160 free hours of MGN service usage—equivalent to 90 days of continuous replication. The clock starts when the AWS Replication Agent is installed and the source server begins active replication. If replication continues beyond the free period, hourly service fees apply per current pricing.

### 10.2. Resources Charged During the Free Period

MGN's free service window does not mean migration is cost-free. AWS resources provisioned for replication and launches still incur standard charges:

- Replication server EC2 instances.
- Staging EBS disks and snapshots.
- Test and cutover EC2 instances.
- Target EBS volumes and storage.
- FSx for NetApp ONTAP if chosen as target storage.
- Data transfer and associated networking services.
- Enabled monitoring, logging, security, and backup services.

### 10.3. Cost Drivers

- Replication extending beyond 90 days.
- High initial sync volumes or high change rates requiring larger staging servers/disks.
- Launching test instances repeatedly and leaving them running.
- Replicating too many waves concurrently.
- Retaining unneeded snapshots, EBS volumes, or test resources.
- Selecting larger instance types than needed.
- Using unnecessary multiple AZs/staging subnets.

### 10.4. Cost Control

- Estimate storage capacity and change rates before migrating.
- Start with a pilot wave to measure real staging consumption.
- Schedule test windows and terminate test instances promptly afterward.
- Track replication start dates to avoid unintended overruns past the free window.
- Clean up obsolete staging resources, snapshots, and test launches per MGN procedures.
- Tag resources by application, wave, owner, and cost center for cost allocation.
- Check MGN pricing and AWS Pricing Calculator before scaling out.

Never delete staging resources while a source server still needs replication or cutover. Clean up only after migration state is confirmed and archive/finalize steps allow it.

## 11. Operating Migration at Scale

### 11.1. Applications and Migration Waves

An application typically comprises multiple interdependent source servers. A migration wave is a group of servers migrated within the same window or coordinated plan.

Plan waves based on:

- Dependencies across web, application, database, identity, and middleware tiers.
- Application criticality.
- Data volume and change rate.
- Testability and rollback feasibility.
- Downtime windows and owner availability.
- Target account, Region, VPC, and licensing.

Do not pack unrelated applications into one wave just to inflate server counts. Overly large waves complicate go/no-go decisions, testing, and rollback.

### 11.2. Migration Connector and AWS Transform

In multi-account environments, AWS Transform workflows and the MGN connector can automate inventory collection, permission setup, and source server actions. The connector can assist with agent installation and managing source actions under configured permissions.

Automation reduces repetitive manual work, but requires:

- Scoping connector permissions per account and server scope.
- Validating scripts and SSM Parameter Store entries before executing source actions.
- Logging outcomes of every action.
- Handling failed actions or unreachable source servers cleanly.
- Retaining manual approval gates for production cutovers.

### 11.3. Inventory Import and Export

For large server fleets, use inventory import/export to standardize configuration via service-supported CSV/templates. You can manage source server attributes, applications, waves, tags, launch settings, and replication settings per the current schema.

Before bulk importing:

1. Export a fresh template from the console.
2. Verify required columns, data types, and enum values.
3. Test importing a small batch.
4. Reconcile imported results against actual source servers.
5. Version-control the inventory and record approvers.

Never invent columns by guessing. Import/export schemas evolve across service updates.

## 12. Troubleshooting Common Issues

| Symptom | Possible Cause | Troubleshooting Steps |
|---|---|---|
| Agent fails to install | Unsupported OS/kernel, missing permissions, missing packages, or disk space | Check OS support, kernel headers, RAM, root, `/tmp`, and admin rights |
| Source server does not appear | Wrong Region, unregistered agent, networking, or duplicate identifier | Check MGN API 443, installer logs, and hardware identifier |
| Initial sync takes too long | Low bandwidth, high change rate, slow staging disks | Measure throughput, disk I/O, network, and staging capacity |
| Replication lag grows | Source writes faster than replication throughput | Check change rate, bandwidth throttling, and replication server sizing |
| Replication server cannot connect | Route, security group, NACL, or firewall blocking ports | Check TCP 1500, routes to staging subnet, and network ACLs |
| Test instance fails to boot | Boot mode, drivers, disk mapping, or OS conversion | Check EC2 system logs, launch settings, and source OS prerequisites |
| Instance boots but app fails | Incorrect DNS, AD, licensing, secrets, IP, or dependencies | Check network, DNS, identity, certificates, and application logs |
| Post-launch action fails | SSM Agent, IAM role, document version, or OS filter | Check SSM connectivity, execution history, and parameters |
| Cutover has missing data | Replication lag not low enough or source still receiving writes | Stop writes, verify final sync, and reconcile data |
| Unexpected cost spike | Long-running test instances, staging resources, or prolonged replication | Review billing, MGN lifecycle, EC2, EBS, snapshots, and FSx |

## 13. Server Migration Checklist

### Pre-Migration

1. Identify application owners, source servers, and dependencies.
2. Verify OS support, CPU architecture, kernel, disk layout, and licenses.
3. Confirm unique hardware identifiers.
4. Assess change rates, storage volume, and bandwidth.
5. Select Region, account, VPC, staging subnet, and operational subnet.
6. Configure IAM, KMS, security groups, routes, and firewalls.
7. Define waves, RPO/RTO, test plans, cutover windows, and rollback plans.
8. Estimate MGN service fees and AWS infrastructure costs.

### During Replication

1. Install AWS Replication Agent.
2. Confirm source servers register properly.
3. Monitor initial sync.
4. Verify continuous replication and lag.
5. Monitor staging servers, EBS disks, and snapshots.
6. Adjust bandwidth/capacity as needed.
7. Proceed to testing only after replication stabilizes.

### During Testing

1. Review EC2 launch templates.
2. Launch test instances in an isolated environment.
3. Verify OS, disks, network, DNS, AD, and licensing.
4. Verify applications, databases, and dependencies.
5. Execute smoke, integration, and performance tests.
6. Log defects and retest after fixes.
7. Finalize tests and clean up test resources.

### During Cutover

1. Confirm go/no-go status and approvers.
2. Freeze changes and stop writes on source.
3. Confirm replication lag meets requirements.
4. Launch cutover instances.
5. Verify post-launch actions and health checks.
6. Switch DNS, load balancers, and routing.
7. Validate business flows and reconcile data.
8. Monitor systems and decide finalize or rollback.

### Post-Migration

1. Update monitoring, backups, patching, and security controls.
2. Review IAM roles, security groups, and network routes.
3. Optimize instance sizes and EBS storage using production metrics.
4. Update CMDB, architecture diagrams, and runbooks.
5. Control costs of staging/test resources.
6. Decommission source servers only after owner sign-off and retention policy compliance.

## 14. Conclusion

AWS Transform MGN—renamed from AWS Application Migration Service in June 2026—rehosts servers through continuous block-level replication. An agent on the source server streams data to an AWS staging area; once initial sync completes, teams can validate test instances, prepare cutover, and launch target EC2 instances according to launch settings.

A successful migration starts with inventory and dependency mapping, followed by OS, network, IAM, staging subnet, and launch template preparation. Teams must monitor replication lag, test applications in isolation, coordinate write freezes and final sync before cutover, and validate data and business flows after switching traffic. MGN handles the rehost mechanics; DNS, database logic, licensing, security, monitoring, backups, and ongoing operations still require dedicated planning.

At scale, grouping applications into migration waves coordinates dependencies and downtime windows. Combining MGN in its proper role alongside AWS Transform, DMS, DataSync, Direct Connect, VPN, and other AWS services reduces risk, controls cost, and delivers workloads onto AWS in verifiable increments.

## 15. Official References

- [AWS Transform MGN – Service page](https://aws.amazon.com/application-migration-service/)
- [Announcement renaming AWS Application Migration Service to AWS Transform MGN](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-transform-mgn-rebrand/)
- [Migration workflow](https://docs.aws.amazon.com/mgn/latest/ug/migration-workflow-gs.html)
- [Installation requirements](https://docs.aws.amazon.com/mgn/latest/ug/installation-requirements.html)
- [Network requirements](https://docs.aws.amazon.com/mgn/latest/ug/preparing-environments.html)
- [Launch settings](https://docs.aws.amazon.com/mgn/latest/ug/launch-settings.html)
- [Post-launch settings](https://docs.aws.amazon.com/mgn/latest/ug/post-launch-settings.html)
- [Release notes](https://docs.aws.amazon.com/mgn/latest/ug/mgn-release-notes.html)
- [Pricing and pricing FAQ](https://aws.amazon.com/application-migration-service/pricing/)
