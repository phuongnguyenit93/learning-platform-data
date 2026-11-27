# AWS Elastic Disaster Recovery and Server Recovery

An outage in a data center, cloud region, or operating system can bring servers offline and cause the loss of recent data. Disaster Recovery (DR) is the capability to restore workloads and data after a disruption to meet committed RPO and RTO objectives. A sound DR plan requires sufficiently current data copies, launch-ready target infrastructure, prepared network and application configurations, a clear recovery sequence, and periodic testing.

AWS Elastic Disaster Recovery (AWS DRS) provides block-level replication and recovery for physical servers, virtual machines, and cloud servers running supported operating systems. DRS continuously replicates changes from source servers into a staging area in AWS; when testing or recovering, the service converts the replicated copy into bootable EC2 instances in AWS. You can recover from the latest state or an earlier point-in-time snapshot, run non-disruptive recovery drills without impacting source servers, and fail back data to the original infrastructure once the incident is resolved.

This lesson belongs to the **Backup and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects DRS with Amazon EC2, EBS, VPC, IAM, AWS Systems Manager, CloudWatch, CloudTrail, Route 53, and AWS Backup to design, operate, and test server recovery.

> **Responsibility Boundary:** AWS DRS manages replication, launches drill/recovery instances, and assists with reverse replication/failback. Deciding when to fail over, switching traffic/DNS, validating application health, and coordinating business continuity remain part of the organization's plan. DRS does not automatically shift users to recovery instances.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain RPO, RTO, failover, recovery, recovery drills, and failback.
2. Describe AWS DRS architecture including source servers, replication agents, the staging area, and recovery instances.
3. Distinguish continuous replication from backups and long-term retention.
4. Evaluate source server OS, disk, architecture, and agent prerequisites.
5. Design network paths, staging subnets, security groups, and firewall rules for DRS.
6. Distinguish the roles of TCP 443 and TCP 1500 in the replication workflow.
7. Explain block-level replication, initial sync, continuous replication, and replication lag.
8. Configure replication settings, EBS encryption, and point-in-time retention.
9. Configure launch settings, EC2 launch templates, and post-launch actions.
10. Execute recovery drills without disrupting production sources.
11. Execute recovery/failover and controlled traffic cutover.
12. Use Recovery Plans to launch multiple servers in dependency order.
13. Execute failback to on-premises or AWS source environments.
14. Design IAM security, KMS/EBS encryption, snapshots, and auditing.
15. Monitor replication health, lag, launch results, and costs.
16. Troubleshoot agent, connectivity, bandwidth, conversion, and failback failures.
17. Build DR runbooks and run periodic tests against RPO/RTO.

## 2. DR Concepts and Recovery Objectives

### 2.1. RPO and RTO

| Concept | Question Answered | Meaning |
|---|---|---|
| RPO (Recovery Point Objective) | How much data loss can be tolerated? | Time span of potential data loss between the incident and the recovery point |
| RTO (Recovery Time Objective) | How long can the service remain unavailable? | Elapsed time from outage start until the workload operates at agreed levels |
| MTD (Maximum Tolerable Downtime) | How long can the business endure disruption? | Business limit guiding RTO and standby approaches |
| WRT (Work Recovery Time) | How much extra time is needed for business catch-up after systems come up? | Time to verify data, reconcile, and normalize business workflows |

Example: a payment system has a 1-minute RPO and a 30-minute RTO. When an outage hits, the business accepts losing at most roughly one minute of unreplicated transactions and needs payment flows restored within 30 minutes. These are design and testing targets, not guarantees that every recovery hits them automatically.

### 2.2. Failover, Recovery, Drills, and Failback

- **Replication:** synchronizing block-level changes from source servers to the AWS staging area.
- **Recovery drill:** launching test instances from replicated data to verify boot and operational readiness without disrupting production sources.
- **Recovery:** launching recovery instances in AWS during an actual recovery event.
- **Failover:** shifting users or traffic from the primary environment to the recovery environment. This is performed by the organization using DNS, load balancers, routing, or other traffic management mechanisms.
- **Failback:** returning workloads and data from the recovery environment back to primary infrastructure once repaired; DRS supports reverse replication and launching in the source environment.

Do not mistake an EC2 recovery instance booting for a successful application failover. Verify boot, networking, dependencies, database consistency, application health, and traffic cutover.

### 2.3. When Is AWS DRS Appropriate?

DRS fits when protecting full servers and recovering existing workloads onto EC2 without redesigning applications beforehand. Sources can be physical servers, VMware/Hyper-V virtual machines, or cloud-based servers running supported OSes. DRS can also assist migrations to AWS, though this lesson focuses on disaster recovery.

DRS does not replace all other forms of data protection:

- For database-native replication, evaluate consistency, transaction logs, cluster topology, and database-specific recovery.
- For serverless or managed services, use each service's built-in backup/replication/failover features.
- For long-term file/object backups, use AWS Backup, S3 Versioning/Object Lock, or archival tiers per retention policies.
- For multi-Region active-active architectures, design dedicated traffic routing, data consistency, and conflict resolution.

## 3. AWS Elastic Disaster Recovery Architecture

### 3.1. Components

| Component | Role |
|---|---|
| Source server | Physical server, VM, or cloud instance running the source workload and data |
| AWS Replication Agent | Agent installed on each source server tracking block writes and transmitting changes to AWS |
| AWS DRS service | Orchestrates replication, manages source servers, point-in-time states, launches, and failback workflows |
| Staging area subnet | Subnet in the target AWS Region hosting replication servers |
| Replication server | DRS-managed EC2 instance receiving and writing replicated blocks to EBS staging volumes |
| EBS staging volumes/snapshots | Stores replicated data copies and recovery points |
| EC2 launch template | Defines how drill/recovery instances launch: subnet, instance type, security groups, disks, IPs, and tags |
| Recovery instance | EC2 instance launched from replicated data to test or recover the workload |
| Post-launch actions | SSM commands/Automation documents executed after recovery instances boot |

### 3.2. Data Flow

~~~mermaid
flowchart LR
    SRC["Source server<br/>Physical / VM / Cloud"] --> AGENT["AWS Replication Agent<br/>Block-level tracking"]
    AGENT -->|"TCP 1500<br/>TLS 1.2, encrypted data"| REPL["Replication server<br/>Staging subnet"]
    AGENT -->|"TCP 443<br/>DRS API / control plane"| DRS["AWS DRS service"]
    REPL --> EBS["EBS staging volumes"]
    EBS --> PIT["Point-in-time snapshots"]
    PIT -->|"Drill / Recovery launch"| EC2["EC2 recovery instance"]
    EC2 --> APP["Application / dependencies"]
    DRS --> LAUNCH["Launch settings / recovery plan"]
    LAUNCH --> EC2
~~~

General workflow:

1. Initialize DRS in the target Region.
2. Configure the replication template and staging subnet.
3. Install the AWS Replication Agent on each source server.
4. The agent performs an initial sync, copying required blocks into the staging area.
5. Once initial sync finishes, DRS continuously replicates changed blocks.
6. DRS creates and maintains point-in-time recovery states per retention policy.
7. During a drill or recovery, DRS creates EBS volumes and EC2 instances from the chosen recovery point.
8. Instance conversion applies adjustments needed to boot on EC2, such as drivers, bootloader, and network configs.
9. The organization validates the application; for real failovers, traffic is cut over.
10. Once the primary environment is ready, reverse replication and failback run according to source type.

### 3.3. RPO and RTO with DRS

AWS describes typical DRS RPOs as sub-second when continuous replication is healthy and converged. This reflects achievable results under normal replication conditions, not a universal guarantee for every source server. If write rates exceed bandwidth, the agent disconnects, a replication server fails, or backlog builds up, recovery points become older.

RTO spans multiple steps: selecting a recovery point, creating EBS volumes, conversion, EC2 capacity availability, booting, post-launch actions, application startup, dependency readiness, and traffic cutover. AWS can launch recovery instances in minutes in many scenarios, yet actual end-to-end times must be measured in recovery drills.

Measure RPO/RTO at the application level. If a server boots cleanly while its database, DNS, Active Directory, or queues remain down, the business service has not recovered.

## 4. Source Servers and Support Prerequisites

### 4.1. Source Server Types

AWS DRS can replicate:

- Physical servers in data centers.
- Virtual machines on supported hypervisors.
- Servers running on other cloud providers.
- EC2 instances in AWS, including recovering to another Region or account under supported models.

DRS replicates at the server and block-volume level; if a source server runs containers, containers residing on that host replicate as part of the server. DRS is not a standalone Kubernetes/container migration tool: external volumes, managed databases, load balancers, and control planes require separate protection.

DRS treats block devices like local disks. With SAN storage, if a LUN is exposed as a block device on the source server, the agent can replicate it like any local disk. With network-mounted NAS/NFS shares, install the agent on the NFS server itself to replicate the underlying file system. DRS supports hardware RAID and LVM, though boot partitions spanned or software-mirrored across multiple physical disks are unsupported; inspect disk layouts before installing the agent.

### 4.2. Operating Systems and CPU Architectures

Verify the supported OS list before installing agents because supported versions and rules change across releases. End-of-life operating systems may lose AWS support even if older agents worked previously.

As of November 20, 2026:

- 64-bit x86_64 source servers are supported per the current OS matrix.
- Linux `arm64` on AWS Graviton EC2 is supported as of September 2026 for AWS-to-AWS recovery.
- `arm64` currently supports only EC2 Graviton sources and recovery/failback within AWS; on-premises/other cloud sources and Windows `arm64` are unsupported.
- Windows source servers support `x86_64`; Windows `arm64` is unsupported.
- 32-bit operating systems are unsupported.

Always review Supported Linux operating systems and Supported Windows operating systems before inventorying.

### 4.3. Agent Installation Prerequisites

Linux source servers typically require:

- Root or sudo privileges to install drivers and services.
- At least 300 MB free RAM for the AWS Replication Agent; Python 2.4+ or Python 3.x; a stable MAC address across reboots and network changes.
- Kernel headers matching the exact running kernel.
- `gcc`, `make`, and required build packages.
- At least 4 GB free on `/` and 500 MB on `/tmp`.
- If `/boot` is a separate partition, at least 50 MB free; bootloader must be GRUB 1 or 2, and Secure Boot is unsupported.
- `/tmp` must permit installer execution; mounting `/tmp` with `noexec` can fail installation.
- `dhclient` installed so recovery instances can use DHCP networking; source servers must not be paravirtualized.
- No conflicting disk filter drivers; Oracle ASM Filter Driver requires following AWS guidance, and PowerPath requires contacting Support.

Windows source servers require:

- Administrator privileges.
- .NET Framework compatible with the Windows version.
- At least 300 MB free RAM and a stable MAC address; `net.exe` and `sc.exe` must be on the system PATH.
- At least 1 GB free on drive C:.
- TLS 1.2 enabled.
- BitLocker must be disabled on volumes to replicate per DRS requirements.
- Run the installer from PowerShell following AWS guidance.

Verify OS-specific prerequisites and installer architecture before bulk rollout. Never use the x86_64 installer on Linux arm64.

### 4.4. Disk and Volume Limits

Per current agent prerequisites:

- Default maximum 16 TiB per volume; as of August 2026, DRS supports volumes up to 64 TiB when selecting gp3 staging disk types.
- Maximum 63 volumes per source server.
- Volumes exceeding limits are not replicated.
- Adding new disks after installing the agent requires checking auto-replicate-new-disks settings and replication configuration.

Inventory boot disks, data disks, mount points, file systems, LVM/RAID, database volumes, and disk dependencies. One omitted volume can allow a recovery instance to boot while the application is missing critical data.

## 5. Network Architecture and Firewall Requirements

DRS requires two distinct network flows. TCP 443 carries control-plane/API calls and agent downloads; TCP 1500 streams replicated blocks between source servers and replication servers.

| Source | Destination | Port | Purpose |
|---|---|---:|---|
| Source server | DRS regional endpoint `drs.<region>.amazonaws.com` | TCP 443 outbound | Agent registration, service communication, status, and metadata |
| Source server | Required S3 regional endpoints/buckets | TCP 443 outbound | Downloading agents/updates and service artifacts |
| Source server | EC2 regional endpoint | TCP 443 outbound | AWS API/control operations needed by agent/replication workflows |
| Source server | Replication server in staging subnet | TCP 1500 | Block-level replication stream |
| Replication server in staging subnet | DRS regional endpoint | TCP 443 outbound | Control plane and service coordination |
| Replication server in staging subnet | S3 and EC2 regional endpoints | TCP 443 outbound | Artifact downloads and AWS API operations |

All communications are encrypted. DRS uses end-to-end TLS 1.2 between the agent and replication server on port 1500. Do not allow intermediate firewalls, proxies, or SSL inspection appliances to decrypt or interrupt this TLS stream.

### 5.1. Staging Area Subnet

Create a dedicated subnet in your target-Region VPC to host replication servers. AWS recommends a dedicated staging subnet to isolate replication traffic and simplify routing/security.

Plan for:

- A CIDR large enough for replication server IPs based on total source disks and expected scale.
- Budget roughly one replication server per 15 source volumes; also reserve IPs for conversion servers during drill/recovery launches—typically one conversion server per launched source server.
- Routes to DRS, S3, and EC2 regional endpoints via NAT/Internet gateway or supported VPC endpoints.
- If using an S3 VPC endpoint, the endpoint policy must allow DRS service buckets and the Amazon Linux 2023 repository bucket `al2023-repos-<REGION>-de612dc2`; replication servers run Amazon Linux 2023 and require this bucket for packages and updates.
- Security groups on replication servers permitting inbound TCP 1500 from source networks and outbound TCP 443 to AWS endpoints.
- Network ACLs permitting bidirectional traffic and ephemeral return ports.
- Working DNS resolution and hostnames.
- Non-overlapping CIDRs with source networks if private IP routing is used.
- Separating the staging subnet from the operational subnet where recovery instances launch.

By default, DRS can launch replication servers in a public subnet with public IPv4 addresses. If choosing private IP data routing, source servers must have private connectivity and routes to the replication servers' private IPs. Never enable the private IP option when sources cannot route to that subnet.

### 5.2. Private and Public Connectivity

You can route control plane and replication traffic over the internet/NAT, or over private connectivity such as VPN, AWS Direct Connect, VPC peering, and other AWS-supported network topologies. Private paths reduce internet exposure and support isolation mandates, yet still require accurate routes, DNS, security groups, NACLs, and endpoint policies.

Never assume a VPN alone suffices. Verify TCP 443 to DRS/S3/EC2 endpoints, TCP 1500 between sources and replication servers, return paths, and MTU/path behavior. DRS replication traffic is already compressed and encrypted; intermediate TLS inspection breaks it.

### 5.3. Testing Connectivity

Linux source servers can test the DRS API endpoint:

~~~bash
curl -v https://drs.ap-southeast-1.amazonaws.com/
~~~

Windows source servers:

~~~powershell
Test-NetConnection drs.ap-southeast-1.amazonaws.com -Port 443
~~~

Test port 1500 to the replication server IP displayed in the DRS console:

~~~bash
nc -vz <replication-server-ip> 1500
~~~

These commands verify TCP reachability, not agent registration or replication health. After network verification, confirm the agent service is running and the source server appears in the DRS console.

## 6. Initializing DRS and Installing the AWS Replication Agent

### 6.1. Initializing the Target Region

DRS is initialized separately in each AWS Region intended as a recovery target. For AWS-to-AWS disaster recovery, initialize DRS in both the source Region and target Region before installing agents or replicating. Initialization creates the service configuration, replication template, and required service-linked role.

General workflow:

1. Select a target Region meeting latency, compliance, capacity, and disaster-isolation goals.
2. Open the AWS Elastic Disaster Recovery Console.
3. Initialize the service in that Region.
4. Select the staging area subnet and default replication settings.
5. Configure EBS encryption, EBS volume types, data routing, bandwidth throttling, and point-in-time retention.
6. Configure default launch settings and post-launch actions.
7. Confirm the service-linked role `AWSServiceRoleForElasticDisasterRecovery` was created.

The service-linked role is created automatically when configuring the replication template; you do not need to create a replacement manually. The initializing principal needs IAM permissions for DRS and permission to create service-linked roles.

### 6.2. Generating Agent Installation Credentials

The AWS Replication Agent needs IAM credentials to register source servers. Grant the installing principal `AWSElasticDisasterRecoveryAgentInstallationPolicy` per AWS documentation, used only during installation.

Principles:

- Prefer roles/temporary credentials where supported.
- Never embed long-term access keys inside AMIs or scripts committed to source control.
- Never share a single over-privileged credential across multiple teams.
- Revoke/rotate installation credentials immediately after rollout completes.
- Separate agent-installation permissions from recovery/failover permissions.
- Monitor CloudTrail to audit who registered source servers.

### 6.3. Installing the Agent on Linux/Windows

Install the agent on every source server to protect. Select the matching target Region and installer architecture.

General steps:

1. Confirm the OS/architecture is on the supported list.
2. Check disk space, kernel headers, packages, and administrator/root rights.
3. Verify TCP 443 and TCP 1500 per network design.
4. Download the installer from the AWS DRS console or designated regional S3 bucket.
5. Run the installer with appropriate IAM credentials/policies.
6. Select the initialized target Region.
7. Verify the agent service is running and the source server appears in the DRS console.
8. Monitor initial sync until completion and replication status turns Healthy.

On Linux, the service is typically managed via systemd. Check with:

~~~bash
sudo systemctl status aws-replication-agent
~~~

On Windows, use PowerShell:

~~~powershell
Get-Service AwsReplicationService
~~~

Service names and commands can vary by OS and agent release; follow the installer guide for your exact version.

### 6.4. Initial Sync and Continuous Replication

Initial sync reads required blocks from source disks and transfers them to the staging area. Initial sync duration depends on data volume, write rate, bandwidth, IOPS, and network health. Never mark a workload as DR-ready merely because agent installation finished.

Once initial sync completes, DRS continuously tracks changed blocks and streams them to replication servers. Source servers remain online in production throughout replication. While the agent is lightweight and designed to be non-disruptive, monitor CPU, RAM, disk I/O, and replication lag on write-intensive hosts.

## 7. Replication Settings, EBS, and Point-in-Time Recovery

### 7.1. Replication Settings

DRS maintains default replication settings applied to source servers added after changes. Modifying default settings does not retroactively update existing source servers; edit individual replication settings when updating existing hosts.

Key parameters:

| Setting | Impact |
|---|---|
| Staging area subnet | Placement of replication servers inside the VPC |
| Replication server instance type | Compute capacity receiving and writing replicated data |
| EBS volume type | Cost, throughput, and IOPS of staging volumes |
| EBS encryption | Encryption of staging volumes and snapshots |
| Automatically replicate new disks | Automatically protects disks attached later to the source |
| Data routing / Use private IP | Routes replication traffic over public or private IPs |
| Network bandwidth throttling | Caps replication bandwidth to protect production networks |
| Point-in-time policy | Frequency and retention window of recovery points |
| Security groups | Network rules governing replication servers |

Dedicated replication servers can be configured per source server; not every setting is exposed in the default template. Changing certain replication settings can trigger agent reconnections or full rescans; review impact before modifying production sources.

### 7.2. Choosing EBS Volume Type and Throughput

DRS provisions staging volumes sized to match source disks. EBS types affect both cost and write throughput for incoming blocks. Auto volume type selection can choose appropriate types by size/throughput for large disks; disks under 125 GiB follow specific volume type behavior per DRS documentation.

One replication server can serve multiple staging disks, up to 15 disks per current pricing guidance. Required replication server counts depend on total disks and write throughput; write-heavy sources may need larger instance types or dedicated replication servers.

Do not swap volume types blindly just to pick faster SSDs. Measure source write throughput, replication lag, and staging disk IOPS first. Higher performance reduces lag at higher EBS expense.

### 7.3. Calculating Replication Bandwidth

Total available bandwidth must exceed the combined average write throughput of all source servers sharing the same network path. AWS recommends adding at least 20% headroom to absorb write bursts.

Design formula:

\[
B_{\min} \geq \sum_{i=1}^{n} W_i \times 1.2
\]

Where:

- \(B_{\min}\): minimum required bandwidth to provision.
- \(W_i\): average write throughput of the i-th source server.
- The 1.2 factor provides minimum recommended headroom; bursty workloads may need more.

Example with two servers averaging 5 MB/s and 7 MB/s over the same link:

\[
B_{\min} \geq (5+7)\times 1.2 = 14.4\ MB/s
\]

Measure write rates across at least 24 hours to capture both peaks and averages. If bandwidth falls below write rate, backlogs grow, replication fails to converge, and recovery points fall progressively behind.

### 7.4. Encryption at Rest and in Transit

DRS compresses and encrypts replicated data; the agent encrypts data before transmission and uses TLS 1.2 for agent-to-replication-server connections. EBS staging volumes and snapshots can be encrypted using AWS KMS per replication settings.

When using a customer managed KMS key:

- Choose a key residing in the target Region.
- Key policies/grants must allow the service and required principals.
- Restrict permissions for `kms:DisableKey`, `kms:ScheduleKeyDeletion`, and policy edits.
- Never delete keys while staging snapshots or recovery resources depend on them.
- Verify cross-account access if staging and recovery accounts are separate.

### 7.5. Point-in-Time Recovery (PIT)

DRS retains recovery points so you can select either the latest state or an earlier timestamp. Current PIT retention cadence includes:

- Snapshots every 10 minutes for the most recent hour.
- Hourly snapshots for the most recent 24 hours.
- Daily snapshots per retention policy.
- Daily retention is configurable from 1 to 365 days; longer retention increases EBS snapshot storage charges.

A PIT policy requires exactly three rules—MINUTE, HOUR, and DAY; MINUTE and HOUR intervals/retentions are fixed by AWS, while DAY retention is configurable. Inspect the current policy schema in the console/API as defaults and schemas can evolve.

PIT snapshots help roll back prior to corruption, accidental deletion, or ransomware propagating to staging. However, DRS replication is not an immutable backup: an attacker compromising the AWS account could attempt to delete snapshots or disable KMS keys. Protect snapshot, KMS, and DRS APIs with IAM least privilege, SCP/guardrails, separation of duties, and AWS Backup/Vault Lock when immutability is required.

### 7.6. Selecting a Recovery Point

- Choose **Use most recent data** when minimizing RPO and replication is Healthy.
- Choose a snapshot prior to a known timestamp to avoid replicated corruption or bad edits.
- Cross-reference event timelines, CloudTrail, application logs, and database consistency before selecting.
- Never pick a recovery point merely because it is newest if data was already encrypted, deleted, or corrupted earlier.
- Verify all servers within an application group restore to mutually compatible points in time to prevent database/application version drift.

## 8. Launch Settings and Post-Launch Actions

### 8.1. DRS Launch Settings and EC2 Launch Templates

Launch settings govern how DRS creates drill and recovery instances. They comprise DRS launch settings and an EC2 launch template. Each source server receives its own launch configuration automatically upon registration; it can be edited even before initial sync finishes.

Settings commonly reviewed:

| Setting | Purpose |
|---|---|
| Instance type right-sizing | Automatically selects an EC2 instance type matching source CPU/RAM/OS |
| Start instance upon launching | Boots recovery instances automatically or leaves them stopped |
| Copy private IP | Attempts to preserve source private IPs on recovery instances when topology permits |
| Operating system licensing | Selects AWS-provided licensing or BYOL per OS and contracts |
| Recovery mode | Chooses Optimal conversion or Fast mode in supported scenarios |
| EC2 launch template | Configures subnets, security groups, IAM instance profiles, instance types, EBS mappings, tags, and metadata options |

Note: when instance type right-sizing is enabled, DRS's calculated selection can override the instance type in the EC2 launch template. Edits to launch settings affect only subsequent drill/recovery launches; already-running instances are not updated retroactively.

As of August 2026, DRS preserves UEFI boot mode for Linux source servers booting via UEFI. EC2 launch templates also support passing `VolumeInitializationRate` inside block device mappings to accelerate EBS volume initialization during drills and recoveries.

### 8.2. Preparing Operational Subnets and Security Groups

Recovery instances typically launch in a dedicated operational subnet isolated from the staging subnet. Prepare in advance:

- VPCs and Multi-AZ subnets if the workload requires HA.
- Route tables, NAT/Internet egress, or private endpoints.
- Security groups for application tiers, databases, and administration.
- IAM instance profiles for Systems Manager, CloudWatch, and application needs.
- KMS permissions for encrypted EBS volumes.
- DNS, domain join, AD/DNS servers, license servers, and secrets access.
- Load balancer target groups, certificates, and routing.
- EC2 quotas, instance family capacity, and EBS volume quotas.

Never let drill recovery instances land accidentally inside production subnets. A drill could cause IP/hostname collisions, send live customer emails, connect to production databases, or execute production cron jobs. Use isolated drill subnets and test dependencies.

### 8.3. Recovery Modes: Optimal vs. Fast

DRS offers two recovery modes in launch settings:

- **Optimal (default):** runs full conversion prior to launch, including driver injection, boot adjustments, and file system updates. Use when unsure of EC2 compatibility or for cross-platform/on-premises/other-cloud recoveries.
- **Fast:** skips conversion and launches directly from replicated snapshots, reducing recovery time. Use for AWS-to-AWS when source servers already carry EC2-compatible drivers and configs. Fast mode requires AWS Replication Agent version 6.42.20 or later per current documentation.

Never pick Fast mode blindly just to lower RTO. Test each OS, instance family, and boot mode in drills—checking boot, networking, and disk integrity—before adopting it in production runbooks.

### 8.4. Post-Launch Actions

Post-launch actions automate tasks once recovery instances boot. DRS uses AWS Systems Manager (SSM) to run commands or Automation documents.

Predefined actions can include:

- Enabling SSM and installing the SSM Agent if needed.
- Installing the CloudWatch Agent.
- Creating an AMI from the instance.
- Configuring time synchronization.
- Validating disk space.
- Checking EC2 connectivity to defined hosts/ports.
- Verifying HTTP/HTTPS responses.
- Verifying tags.
- Validating volume integrity and process statuses.

You can add custom SSM documents to configure services, update endpoints, mount file systems, swap application configs, or run validation scripts. Post-launch actions execute with corresponding IAM permissions; verify instance profiles and automation caller roles. Never place plaintext passwords, tokens, or secrets in action scripts or logs.

Post-launch actions do not replace application acceptance testing. An HTTP 200 on a health check does not prove payment processing, database transactions, or queue consumers work properly.

## 9. Recovery Drills and Periodic Testing

### 9.1. Purpose of Recovery Drills

A recovery drill is a non-disruptive test leaving the source server and ongoing replication untouched. DRS uses the same launch workflow as live recovery to verify:

- Recovery instances boot and pass EC2 system/instance status checks.
- Disks/file systems mount cleanly and data is consistent.
- Network routes, DNS, security groups, and dependencies function.
- Application services start in the right sequence.
- Test users/clients can reach critical business functions.
- Actual RPO and RTO from drill start through passing business validation.
- Post-launch actions, monitoring, alerts, and runbooks function as designed.

AWS recommends drilling frequently, at least a few times per year; recovery drill guidance recommends quarterly drills at minimum. Actual cadence depends on compliance, business impact, change frequency, and RTO/RPO.

### 9.2. Running a Drill in the Console

1. Open the AWS Elastic Disaster Recovery Console in the target Region.
2. Go to **Source servers** and confirm initial sync is complete.
3. Review replication status, lag, launch settings, and post-launch actions.
4. Select one or more source servers and open **Initiate recovery job**.
5. Choose **Initiate recovery drill**.
6. Choose **Use most recent data** or a specific recovery point.
7. Launch the drill and monitor Recovery job history.
8. Connect via SSH/RDP or test endpoints per your test plan.
9. Validate applications, databases, dependencies, metrics, and logs.
10. Record timings, measured RPO/RTO, failures, decisions, and action items.
11. After finishing, terminate drill instances and temporary resources per cleanup procedures.

You can run a drill once initial sync completes even if a source server shows Lag or Stalled status, though that does not indicate production DR readiness. To certify DR readiness, resolve replication issues and maintain Healthy status.

### 9.3. Running a Drill with the AWS CLI

Example listing source servers:

~~~bash
aws drs describe-source-servers \
  --region ap-southeast-1
~~~

View recovery snapshots for a source server:

~~~bash
aws drs describe-recovery-snapshots \
  --source-server-id s-123456789abcdefgh \
  --region ap-southeast-1
~~~

Launch a drill from latest data:

~~~bash
aws drs start-recovery \
  --source-servers sourceServerID=s-123456789abcdefgh \
  --is-drill \
  --region ap-southeast-1
~~~

To target a specific recovery snapshot, include `recoverySnapshotID` in the source server entry per current AWS CLI syntax. Verify the exact source server ID and recovery point before executing.

### 9.4. Post-Drill Cleanup

DRS does not automatically terminate instances launched by a Recovery Plan when execution finishes, is canceled, or times out. Drill instances continue incurring EC2, EBS, and related charges until terminated. For individual drills, check Recovery instances and terminate them per cleanup procedures.

Before terminating:

- Confirm the target is a drill instance, never a live production recovery instance.
- Confirm application owners finished testing.
- Collect logs, screenshots, metrics, and test evidence.
- Remove temporary DNS/routing entries and auxiliary test resources.
- Confirm source servers remain replicating normally.

Leaving a successful drill instance running indefinitely skews cost budgets and introduces security exposure.

## 10. Recovery Plans and Multi-Server Application Recovery

### 10.1. Why Use Recovery Plans?

Applications often span multiple dependent tiers: Active Directory/DNS, databases, message brokers, application servers, batch workers, and web tiers. Launching everything simultaneously can cause app tiers to boot before databases or authentication are ready.

AWS DRS Recovery Plans were introduced in 2026 to define ordered launch sequences across multiple source servers. Plans execute in either Drill or Recovery mode with step-by-step execution tracking.

### 10.2. Recovery Plan Structure

A Recovery Plan belongs to one AWS account and Region with a unique name in that scope. Under current limits:

- Up to 20 ordered steps per plan.
- Up to 100 total source servers per plan.
- A server step can include multiple servers; DRS launches servers within a step in parallel and advances to the next step only after all finish.
- Wait steps pause between 1 and 120 minutes; a wait step cannot be the first step.
- Server failure impact can be set to Critical or Optional. Critical is the default; Critical failures fail the step/execution, whereas Optional failures allow the plan to continue.
- A source server can appear only once within a given plan, though it may belong to multiple plans.
- Only one execution per plan can run at a time; if a source server is currently part of another plan's execution, launching a new execution can be rejected until the active execution finishes.

### 10.3. Example Recovery Sequence

| Step | Type | Server/Wait | Purpose |
|---:|---|---|---|
| 1 | Server step | Domain controllers, DNS | Restore identity and name resolution |
| 2 | Wait step | 5 minutes | Allow AD/DNS initialization and replication/health stabilization |
| 3 | Server step | Database primary, message broker | Launch data tier |
| 4 | Wait step | 10 minutes | Allow database recovery and broker readiness |
| 5 | Server step | Application servers | Launch service layer |
| 6 | Wait step | 5 minutes | Allow health checks and dependency connections |
| 7 | Server step | Web/API tier, workers | Open user-facing services and background processing |

This is an example only. Base your actual sequence on your dependency graph, database recovery times, domain services, and application startup logic. A wait step is merely a fixed pause; it does not verify service health. Combine post-launch validations and operator checks before cutting over traffic.

### 10.4. Running Drills or Recoveries via a Plan

Workflow:

1. Create a Recovery Plan and add ordered server and wait steps.
2. Assign Critical or Optional impact levels to each server.
3. Review launch settings, recovery points, and post-launch actions across all servers.
4. Execute the plan in **Drill** mode to validate ordering and dependencies.
5. Monitor execution status, individual steps, and per-server progress.
6. Verify the application end-to-end before wrapping up the drill.
7. Terminate all drill instances and audit costs.
8. Run **Recovery** mode only upon formal incident declaration and runbook approval.

An execution captures a snapshot of the plan at launch time; editing the plan afterward does not alter an in-flight execution. DRS does not automatically shift DNS or traffic after a plan completes.
While an execution is active, operators can retry or skip failed steps, or cancel the execution. Canceling does not roll back already-completed steps; clean up manually per runbook if needed.

## 11. Recovery and Failover into AWS

### 11.1. Preconditions Before Recovery

Never trigger recovery merely because a source server drops a ping. Before deciding to fail over, the incident commander and application owner must:

- Confirm the incident and blast radius.
- Determine the primary environment cannot recover within RTO.
- Verify source servers completed initial sync with acceptable recovery readiness.
- Check replication lag, last successful drill, and recent recovery history.
- Pick a recovery point matching RPO and application consistency.
- Confirm recovery Region/account, VPC, subnets, security groups, IAM, KMS, and EC2 capacity.
- Verify dependency ordering and steps required outside DRS.
- Identify traffic cutover approvers and rollback plans if validation fails.

Never use the **Disconnect from AWS** action on a source server that launched recovery instances during a live incident. That action terminates replication resources and PIT recovery points, wiping out needed recovery and failback options.

Ideally, source servers are Healthy and Ready for recovery. If an incident cuts source connectivity, DRS can still recover from previously replicated data; understand the exact last recovery point and lag.

### 11.2. Launching Recovery Instances

1. Open the AWS DRS Console and select source servers or a Recovery Plan.
2. Choose **Initiate recovery** or run the plan in **Recovery** mode.
3. Select the latest recovery point or an earlier point-in-time snapshot.
4. Start the recovery job and monitor each server/job.
5. Verify recovery instances appear in EC2 and pass instance/system checks.
6. Verify volumes, file systems, hostnames, IPs, security groups, and IAM instance profiles.
7. Execute post-launch actions and application validation.
8. Enable EC2 termination protection once launch validation passes, prior to shifting traffic.
9. Record recovery instance IDs, IPs, timestamps, and the recovery point used.

DRS provisions recovery instances without shifting DNS or user traffic. Never shift traffic while instances are merely running without passing application checks.

### 11.3. Shifting Traffic (Failover)

Failover happens outside DRS using the organization's traffic management mechanisms, such as:

- Amazon Route 53 failover/weighted records.
- Application Load Balancer or Network Load Balancer target groups.
- AWS Global Accelerator endpoint weights.
- External DNS providers, BGP, or network routing outside AWS.
- Updating service discovery or API endpoints per application architecture.

Before opening traffic:

1. Fence/disable writers in the primary environment to prevent split-brain and concurrent writes.
2. Verify database primary roles and replication consistency.
3. Verify authentication, secrets, certificates, DNS, and external dependencies.
4. Shift traffic per plan, using canary/weighted shifts where appropriate.
5. Watch 4xx/5xx rates, latency, queue depth, database connections, and business transactions.
6. Notify stakeholders and update the incident timeline.

If the primary environment keeps accepting writes while the recovery environment also takes writes, data diverges. Define write authority and fencing clearly before cutover.

### 11.4. Post-Failover

- Confirm critical business flows operate cleanly.
- Check scheduled jobs, batch jobs, email/payment integrations, and downstream services.
- Scale capacity as needed while honoring quotas and budgets.
- Establish fresh backups of the recovery environment per policy.
- Preserve logs, snapshots, and event evidence per incident retention.
- Update DNS TTLs, runbooks, and contact trees if needed.
- Never terminate recovery instances while they serve as live production primary.

## 12. Failback to Original Infrastructure

### 12.1. When to Fail Back

Failback returns workloads running in the AWS recovery environment back to primary infrastructure once repaired or replaced. Fail back only when:

- The root cause is resolved and the primary environment is stable.
- Networking, compute, storage, security, and identity dependencies are ready.
- Authoritative data ownership and write-freeze timing are agreed.
- Sufficient bandwidth exists for reverse replication.
- A traffic cutover plan, rollback plan, and hold on deleting recovery instances are in place.

Do not fail back just to "go back to normal" if the recovery environment runs stably and the business does not require moving back. Reversing carries downtime and data risks unless thoroughly rehearsed.

### 12.2. Failback Mechanisms

| Original Source Infrastructure | Failback Mechanism |
|---|---|
| On-premises physical/virtual server | Use the AWS DRS Failback Client ISO or DRS failback automation per documentation |
| AWS same-account | Start reverse replication from the protected recovery instance |
| AWS cross-account | Start reverse replication from the recovery instance in the failover account using trusted account roles |
| Other cloud | Mechanism depends on provider and networking; consult specific guidance |

For on-premises targets, boot the Failback Client on the target server and connect to DRS to stream data back from the recovery instance. For AWS-to-AWS, reverse replication streams new changes from the recovery instance back to the source environment.

### 12.3. General Failback Workflow

1. Confirm source infrastructure is ready to receive data.
2. Verify connectivity, credentials, security groups, and ports 443/1500.
3. Initiate failback/reverse replication per source type.
4. Monitor reverse replication until Ready or Ready with lag per DRS status guidance.
5. Schedule and execute the write freeze on the recovery environment.
6. Wait for final synchronization to minimize data loss.
7. Launch failback instances or boot source servers per procedure.
8. Verify OS, volumes, applications, database consistency, and dependencies.
9. Shift traffic back to primary via DNS/routing outside DRS.
10. Monitor post-cutover operations and validate business transactions.
11. Re-enable replication from failed-back servers to AWS to restore DR protection.
12. Clean up recovery instances/resources only after confirming primary is live and ongoing DR replication works properly.

### 12.4. Networking and Common Failback Errors

Failback also requires TCP 443 to DRS endpoints and TCP 1500 between replication source and target. For the Failback Client or recovery instances, security groups and firewalls must permit traffic in the required direction per topology. In certain AWS failback flows, inbound TCP 1500 must be opened on the recovery instance security group. If the Failback Client connects over the public internet (without VPN/Direct Connect), the recovery instance needs a public IP; DRS's default EC2 launch template disables auto-assign public IP, so enable it explicitly when using public routing.

Common errors:

- Agent on the recovery instance cannot reach DRS.
- Failback Client fails to associate or obtain credentials.
- Port 1500 blocked by firewalls, security groups, or NACLs.
- TLS inspection breaking the replication stream.
- Clock skew causing credential validation failures.
- Source instance missing tags or launch settings needed to launch back into the source instance.
- Reverse replication failing to converge because write rates exceed bandwidth.

Never terminate a recovery instance before reverse replication completes. For recurring failures, gather DRS troubleshooting logs and open an AWS Support case with error codes, source server IDs, job IDs, and timestamps.

### 12.5. Post-Failback Cleanup

Once primary serves production and DRS replication is re-established:

- Confirm no duplicate source server records exist for the same workload.
- Verify the agent and replication status on the failed-back server.
- Delete unneeded recovery resources per inventory.
- Remove temporary security group and routing rules.
- Retain snapshots/logs per retention policies.
- Confirm KMS keys remain intact for data that may still need restoration.
- Update the CMDB, recovery plans, RTO/RPO measurements, and post-incident review.

## 13. Multi-Account, Multi-Region, and Large-Scale DR

### 13.1. Region Isolation

DRS is initialized separately per target Region. To survive a Regional outage, replicate sources to a different Region than primary. Target recovery resources—VPCs, subnets, security groups, KMS keys, AMIs, IAM roles, DNS, and dependencies—must also exist in the target Region.

Do not confuse Availability Zone redundancy with Region-level DR. The DRS target Region needs enough capacity and quotas to boot the entire recovery fleet simultaneously.

### 13.2. Multi-Account Staging and Target Accounts

DRS enforces a default quota of 300 concurrently replicating source servers per AWS account per Region. Larger environments can fan out across multiple staging accounts feeding one or more target accounts. AWS supports recovering up to 3,000 source servers into a single target account using multiple staging accounts.

This architecture enables:

- Separating replication infrastructure from the production recovery account.
- Dividing billing, ownership, and security boundaries.
- Scaling source server counts beyond one staging account's limit.
- Recovering multiple staging accounts into one centralized recovery account.
- Separating target accounts for production, testing, or business units.

Configure trusted accounts/roles, share EBS encryption keys appropriately, and provision network access. The target account assumes roles to read source server metadata/resources from staging accounts. Audit IAM trust policies, KMS key policies, EBS snapshot sharing, and resource ownership.

### 13.3. Quotas to Include in Capacity Planning

Key current DRS limits:

| Quota | Default Limit |
|---|---:|
| Concurrently replicating source servers/account/Region | 300 |
| Source servers in a single recovery job | 100 |
| Source servers across all active jobs | 500 |
| Concurrent jobs in progress/Region | 20 |
| Recovery Plan steps | 20 |
| Source servers in a single Recovery Plan | 100 |
| Volume size/source server | 64 TiB per volume when using gp3 staging disks; 16 TiB with other staging options |
| Volumes/source server | 63 |

Quotas can vary by API/resource type and evolve over time. Check AWS Service Quotas and DRS endpoints and quotas before deploying. Never assume EC2 quotas, EBS volume quotas, IP address capacity, and DRS quotas scale automatically together.

### 13.4. Disaster Recovery at Scale

With hundreds or thousands of servers:

- Group by application, dependency graph, and business criticality.
- Use Recovery Plans for dependent groups within plan limits.
- Define failover sequencing across multiple plans.
- Throttle concurrency so you do not exhaust EC2 capacity or EBS throughput.
- Monitor source servers showing Stalled, Disconnected, Lag, or overdue drills.
- Build centralized dashboards via AWS Organizations/cross-account IAM.
- Provision VPCs, subnets, security groups, route tables, IAM, and DNS with IaC.
- Verify quotas across all target Regions.
- Drill small cohorts before attempting full-scale recovery.

## 14. Security, IAM, and Protecting Recovery Data

### 14.1. Shared Responsibility

AWS secures the DRS service infrastructure and provides encryption and identity integrations. Customers are responsible for:

- Who can initialize DRS, install agents, modify replication settings, and launch recoveries.
- Network paths, firewalls, VPCs, security groups, and subnet isolation.
- IAM roles/instance profiles for recovery instances and post-launch actions.
- KMS key policies, EBS encryption, and key lifecycles.
- Protecting snapshots, logs, and recovery credentials.
- Post-recovery application security, patching, secrets, and data access controls.

### 14.2. IAM and Service-Linked Roles

DRS uses the service-linked role `AWSServiceRoleForElasticDisasterRecovery` trusting `drs.amazonaws.com` to perform required AWS actions on your behalf. It is created automatically when configuring the replication template.

Separate duties by role:

| Role | Recommended Permissions |
|---|---|
| DRS administrator | Initialize service, manage replication/launch settings, source servers, and recovery plans |
| Agent installer | Scoped strictly to the AWS Replication Agent installation policy |
| Recovery operator | Launch drills/recoveries and monitor jobs |
| Application validator | Access recovery instances/test endpoints to validate applications |
| Key administrator | Manage KMS policies/rotation/deletion without default data-read access |
| Auditor | Read CloudTrail, DRS state, and reports; cannot modify protection |

Use IAM Identity Center/role-based access, MFA, and temporary credentials. Gate `drs:StartRecovery`, `drs:StartFailback`, and EC2 termination behind approval workflows. Installing an agent can start billing charges as soon as a source server registers; control who holds this permission.

### 14.3. Encryption and KMS

Replication data is encrypted in transit. Staging EBS volumes and snapshots can use AWS managed keys or customer managed KMS keys. With CMKs, verify DRS/service roles and recovery principals hold required permissions.

AWS DRS stores only configuration and log data inside its encrypted service database; replicated data resides inside the customer's VPC in the staging area and is encrypted in transit. Consequently, customers must protect staging VPCs, EBS volumes/snapshots, and KMS keys just like other sensitive data.

When using cross-account staging/target accounts, share encryption keys following multi-account DRS guidance. Key policies in the key-owning account and identity policies in calling accounts must both permit required operations.

Never disable or schedule deletion of KMS keys still protecting staging snapshots, recovery volumes, or backups. Permanently deleted keys render ciphertext unrecoverable.

### 14.4. Protecting PIT Snapshots and Ransomware Defense

DRS continuously replicates block changes, so deleted files, corrupted databases, or ransomware-encrypted files replicate to staging too. PIT snapshots allow rolling back to a pre-incident recovery point within retention.

However, DRS PIT snapshots are not standalone immutable backups. An attacker compromising privileged AWS account access could delete snapshots, stop replication, or disable KMS keys. Therefore:

- Enforce least privilege across DRS, EC2, EBS snapshot, and KMS APIs.
- Separate DRS operational duties from snapshot/key deletion permissions.
- Use SCPs/permissions boundaries or guardrails to block unauthorized destructive actions.
- Keep independent backups in AWS Backup with vault policies/Backup Vault Lock when immutability is needed.
- Store off-account/off-Region copies matching your threat model.
- Test restores from independent backups rather than relying solely on replication health.

### 14.5. Hardening Recovery Instances

- Launch in private subnets whenever public ingress is unnecessary.
- Use minimal security groups allowing admin access only via bastion or SSM.
- Enforce IMDSv2 in EC2 launch templates where applications support it.
- Attach scoped instance profiles; never reuse broad admin roles.
- Protect secrets via Secrets Manager/Parameter Store with rotation.
- Isolate drill subnets from production to prevent accidental cross-connections.
- Enable termination protection on production recovery instances after launch validation.
- Log and monitor all edits to security groups, routes, IAM, and DNS.

## 15. Monitoring, CloudWatch, EventBridge, and CloudTrail

### 15.1. Tracking Source Server Status

On the Source servers page, track two primary indicators:

| Recovery Readiness | Meaning |
|---|---|
| Ready | Eligible to launch a drill/recovery from current state |
| Ready with lag | Can launch, though the recovery point lags; check lag duration |
| Initial sync | Performing initial copy; not yet DR-ready |
| Disconnected | Agent cannot reach DRS |
| Not ready | Critical issue such as stalled replication or failed launch prerequisites |

Data replication statuses include:

- **Initiating:** DRS is initializing replication setup.
- **Initial sync:** performing initial block copy.
- **Rescanning:** re-reading disks/blocks as triggered.
- **Healthy:** replication is steady and ready for recovery launches.
- **Lag:** replication is lagging; console displays lag duration.
- **Stalled:** replication halted due to an error requiring intervention.
- **Disconnected:** agent lost connectivity to DRS.

A source server can show Ready with lag while violating target RPO. Monitor lag duration and backlog rather than relying solely on Ready status.

### 15.2. CloudWatch Metrics

DRS emits metrics tracking replication and recovery readiness. Key metrics include:

| Metric | Meaning |
|---|---|
| `TotalSourceServerCount` | Total source servers |
| `LagDuration` | Age of the newest consistent snapshot, in seconds |
| `Backlog` | Unsynchronized data written at source not yet flushed to AWS, in bytes |
| `DurationSinceLastSuccessfulRecoveryLaunch` | Elapsed time since the last successful drill/recovery launch |
| `ElapsedReplicationDuration` | Cumulative time the source server has been replicating |

Build dashboards segmented by application, account, and Region. Alert when lag/backlog breaches RPO, replication turns stalled/disconnected, drill age grows overdue, or recovery launches fail.

### 15.3. EventBridge Events

DRS emits service events directly to EventBridge and API events via CloudTrail. Direct events include:

- `DRS Source Server Launch Result`
- `DRS Source Server Data Replication Stalled Change`
- `DRS PIT Snapshot Taken`
- `DRS Recovery Instance Failback State Change`
- `DRS Source Network Protection Status Change`
- `DRS Source Network Recovery Result`

Create EventBridge rules matching `source = aws.drs` and `detail-type` to route notifications to SNS, Lambda, SQS, or incident tooling. Event delivery is best effort; pair with API polling and dashboards when completeness is critical.

Example event pattern for stalled replication:

~~~json
{
  "source": ["aws.drs"],
  "detail-type": ["DRS Source Server Data Replication Stalled Change"]
}
~~~

Route matched events to an SNS topic for on-call paging. Never treat event notifications as the sole source of truth; re-verify source server state in the DRS console/API.

### 15.4. CloudTrail Auditing

CloudTrail logs DRS API calls from the Console, CLI, and SDKs. Audit:

- Who added/removed source servers or stopped/started replication.
- Who altered replication/launch settings or recovery plans.
- Who triggered drills, recoveries, or failbacks.
- Who modified IAM roles, KMS policies, security groups, route tables, and EC2 launch templates.
- Who terminated recovery instances or deleted snapshots.

Use an organization trail or multi-Region trail delivering logs to a dedicated audit account where needed. Enforce retention and access controls on CloudTrail logs.

## 16. Troubleshooting and Resolving Replication Errors

### 16.1. Symptoms and Causes Matrix

| Symptom | Common Cause | Remediation |
|---|---|---|
| Agent installer cannot connect | TCP 443 blocked, wrong Region, or wrong proxy | Check routes/firewalls/proxies and DRS endpoints |
| Source server Disconnected | Agent service stopped, network loss, or credential/identity failure | Check agent service, DNS, TCP 443, and logs |
| Replication server receives no data | TCP 1500 blocked or security group/NACL misconfigured | Check source outbound and staging inbound TCP 1500 |
| Replication Lag climbing | Write rate surged, insufficient bandwidth, or low disk IOPS | Measure write throughput, add bandwidth headroom, evaluate EBS type |
| NOT_CONVERGING | Data change rate exceeds replication capacity | Increase network capacity, staging throughput, or adjust throttling |
| Stalled | Agent, network, replication server, or storage fault | Read replication status details and agent logs |
| Recovery launch fails | Incompatible instance type/AMI/boot mode/license/subnet/SG | Review EC2 launch template, quotas, Marketplace licenses, and conversion mode |
| Instance boots but app fails | Missing dependencies, DNS, secrets, disk mounts, or startup order | Check post-launch actions, logs, Recovery Plan, and app validation |
| Failback Client cannot connect | Port 443/1500, credentials, or missing source server | Verify network, client pairing, IAM, and source server state |
| Reverse replication fails | Recovery agent down or missing network path | Check service on recovery instance, security groups, and routes |
| Credential retrieval failed | Clock skew or bad role/trust policy | Sync system clocks, verify trusted account roles and IAM |
| PIT recovery point missing | Retention too short or snapshots deleted | Inspect PIT policy, CloudTrail, and snapshot protections |

### 16.2. Resolving Non-Converging Replication

When status shows `NOT_CONVERGING` or lag climbs steadily:

1. Confirm the agent is running and the source server is connected.
2. Verify TCP 1500 from source to replication server.
3. Measure average and peak write throughput across all servers sharing the network path.
4. Compare against available bandwidth; ensure capacity meets total write rate plus headroom.
5. Check replication server CPU, memory, and EBS throughput/IOPS.
6. Inspect staging disk types; upgrade to a type with adequate throughput if needed.
7. Monitor lag and ETA after adjustments.
8. If unresolved, collect agent logs and open an AWS Support case.

After a reboot or agent/service restart, DRS may rescan disks and show a temporary lag spike. Never assume bandwidth is insufficient from a brief spike alone; watch whether the backlog trend shrinks afterward.

### 16.3. Port 1500 and TLS Inspection Failures

Errors like `Connection refused`, `connect timed out`, or `No route to host` usually point to firewalls, route tables, NACLs, or security groups. Inspect:

- Source server outbound TCP 1500.
- Replication server inbound TCP 1500.
- Network ACL inbound/outbound rules and ephemeral return ports.
- Private/public IP routing between source and replication servers.
- NAT gateways, DNS resolution, and VPC endpoint policies.
- Confirm no proxy or firewall decrypts or modifies TLS sessions on port 1500.

### 16.4. Recovery Launch Failures

When launches fail, inspect in order:

1. Recovery job history and exact error code.
2. Source server Ready/Healthy status and recovery point existence.
3. EC2 launch template: instance type, subnet, security group, IAM profile, disk mappings, metadata options.
4. EC2 quotas, instance capacity, EBS volume limits, and subnet IP capacity.
5. OS boot mode, driver compatibility, Marketplace licensing, and BYOL rules.
6. KMS key state and decryption permissions.
7. Post-launch actions/SSM permissions and SSM agent connectivity.

## 17. AWS Elastic Disaster Recovery Pricing

### 17.1. DRS Service Fee

Per AWS DRS pricing checked on November 20, 2026, the standard published rate is **$0.028 per source server per hour**. DRS uses usage-based pricing with no upfront fee and no minimum commitment. The DRS fee covers continuous replication, test launches, recovery launches, and point-in-time recovery per service pricing rules. The hourly DRS rate stays constant regardless of target Region, disk count, storage volume, or drill/recovery launch counts; auxiliary infrastructure like EBS/EC2 still bills by Region and configuration.

Published rates may be updated by AWS; currency, taxes, and underlying resource charges depend on billing setup and Region. Always verify AWS DRS Pricing and the AWS Pricing Calculator before budgeting.

### 17.2. Additional Infrastructure Charges

The per-source-server DRS fee does not cover underlying AWS resources consumed. Additional charges can include:

- Amazon EBS staging volumes sized to source disks.
- EBS snapshots for PIT retention and data churn.
- EC2 replication server instances in the staging area.
- EC2 conversion server instances spun up during drill/recovery launches; they run only during conversion yet still incur EC2 usage charges.
- EC2 drill/recovery instances while running.
- EBS volumes attached to drill/recovery instances.
- Data transfer/network charges across replication links and traffic.
- NAT Gateways, VPNs, Direct Connect, or other networking services.
- CloudWatch, EventBridge, CloudTrail, SSM, and service integrations per usage.
- Independent AWS Backup or archival storage if configured.

Running drill instances continue accruing EC2/EBS charges. Recovery Plans do not auto-terminate instances when executions finish; run manual or automated cleanup safely.

### 17.3. Cost Estimation

Example: 10 source servers replicating continuously for 30 days:

\[
10 \times 24 \times 30 \times 0.028 = 201.60\ USD
\]

This covers only the hourly DRS source-server fee; it excludes EC2 replication servers, EBS volumes/snapshots, data transfer, and drill/recovery resources.

A complete estimate must include:

1. Source server count and replication hours.
2. Disk sizes and disk counts per server.
3. Write/change rates driving snapshot growth.
4. PIT retention (1–365 days).
5. Replication server instance types and staging EBS types.
6. Drill frequency and drill instance runtimes.
7. EC2 recovery instance counts and runtime during failover.
8. Data transfer and private connectivity.
9. Multi-account/multi-Region overhead.
10. Separate immutable/long-term backup retention.

### 17.4. Safe Cost Optimization

- Use Auto EBS volume type selection where suitable to balance throughput and storage cost.
- Size PIT retention to business RPO/compliance rather than defaulting to the maximum.
- Throttle bandwidth only when necessary to shield production networks; over-throttling increases lag and breaks RPO.
- Terminate drill instances promptly after validation.
- Clean up temporary resources and security groups per inventory.
- Keep staging capacity matched to write rates; over-optimizing can prevent replication from converging.
- Size recovery instance costs around RTO and expected runtime in AWS.
- Use AWS Backup for independent long-term backups instead of stretching PIT snapshots unnecessarily.

**Stop Replication Warning:** stopping replication on a source server halts ongoing replication and staging infrastructure charges, while immediately deleting the server's saved PIT snapshots. Subsequent writes are unprotected and past recovery points are lost. Stop replication only when decommissioning workloads after confirming other backups exist.

## 18. Sample DR Runbook for a Three-Tier Application

Assume an application with databases, application servers, and a web/API tier. Sample targets: 1-minute RPO, 30-minute RTO. Actual targets must be signed off by business owners and verified in drills.

### 18.1. Pre-Incident

- All source servers show Healthy DRS replication status.
- Recovery readiness is Ready with a recent successful drill.
- PIT retention meets rollback requirements.
- Recovery Plan enforces order: database -> application -> web/API.
- Recovery VPC/subnets/security groups and IAM roles are prepared.
- Route 53/Global Accelerator/traffic management cutover procedures are ready.
- KMS keys, secrets, certificates, DNS, AD, and external dependencies are verified.
- On-call contacts, incident commander, and application owners are designated.

### 18.2. Upon Disaster Declaration

1. Incident commander confirms blast radius and declares failover.
2. Application owner selects recovery points aligned with RPO and any known corruption timestamp.
3. Network owner confirms recovery VPC and routing readiness.
4. DRS operator executes the Recovery Plan in Recovery mode.
5. Database tier launches first and passes consistency/readiness checks.
6. Application tier launches once the database is ready.
7. Web/API tier launches after service dependencies pass.
8. Enable termination protection on production recovery instances.
9. Application owner runs smoke tests and synthetic business transactions.
10. Network owner shifts traffic via DNS/Global Accelerator/traffic manager.
11. Incident commander confirms service restoration and monitors SLOs.

### 18.3. Post-Failover

- Designate the recovery environment as the authoritative writer.
- Fence writes on the old primary to prevent split-brain.
- Verify backups, monitoring, alerting, and scaling capacity.
- Track error rates, latency, database connections, queue depth, and data integrity.
- Log recovery timestamps, chosen recovery points, actual RPO/RTO, and deviations.
- Prepare the failback plan without executing until primary stabilizes.

### 18.4. During Failback

1. Repair/restore the primary environment and verify networking/security.
2. Initiate reverse replication from the recovery environment.
3. Wait for reverse replication Ready/Healthy status per source type mechanism.
4. Schedule a maintenance window and freeze writes.
5. Wait for final sync and verify data consistency.
6. Launch/boot the workload at primary and test.
7. Shift traffic back to primary.
8. Verify DR replication is re-established from primary back to AWS.
9. Clean up retired recovery resources and update CMDB/runbooks.

## 19. Hands-On Labs in an AWS Sandbox

Labs must use learner-managed accounts and test source servers. Never install agents on production servers or stop replication on live workloads during labs.

### 19.1. Lab A — Initialize DRS and Add a Source Server

1. Choose a DRS-supported AWS Region.
2. Initialize DRS and create a dedicated staging subnet.
3. Review default replication template, EBS encryption, and PIT policy.
4. Create an IAM principal scoped solely to the agent installation policy.
5. Prepare a compatible Linux or Windows test server.
6. Test TCP 443 and TCP 1500 before installing the agent.
7. Install the agent and confirm the source server appears in the DRS console.
8. Monitor initial sync until Healthy.

### 19.2. Lab B — Replication Lag and Bandwidth

1. Record the baseline average write rate of the source server.
2. Inspect replication lag, backlog, and ETA.
3. Generate controlled write activity within sandbox limits.
4. Observe lag and backlog climbing and draining with bandwidth.
5. Test network bandwidth throttling in the sandbox.
6. Restore sufficient bandwidth and verify replication converges.
7. Document effects on RPO and cost.

Do not generate excessive disk writes that impact shared hosts or accounts.

### 19.3. Lab C — Recovery Drill and Post-Launch Actions

1. Configure the launch template targeting an isolated drill subnet.
2. Select instance type, security groups, IAM profile, and IMDSv2.
3. Enable post-launch actions for SSM and CloudWatch Agent.
4. Launch a recovery drill from latest data.
5. Check EC2 status checks, disk mounts, SSH/RDP, and application health.
6. Measure launch and validation durations.
7. Terminate drill instances/resources after capturing results.
8. Confirm source replication stays Healthy.

### 19.4. Lab D — Recovery Plan for Database and Application

1. Register at least two test source servers in DRS.
2. Create a Recovery Plan with the database server step preceding the application server step.
3. Insert an appropriate wait step and configure Critical/Optional impact levels.
4. Run the plan in Drill mode.
5. Inspect launch order, dependencies, and execution history.
6. Test the application once all steps finish.
7. Terminate all drill instances since Recovery Plans do not auto-cleanup.
8. Refine the plan from drill findings and re-test.

### 19.5. Lab E — Failback Tabletop and Security Review

1. Use the source -> staging -> recovery diagram you built.
2. Walk through failover: selecting a recovery point, launching recovery, and cutting over traffic.
3. Walk through failback: source readiness, reverse replication, write freeze, and traffic return.
4. Review IAM roles, KMS key policies, snapshot deletion controls, and CloudTrail.
5. Create an EventBridge rule for DRS replication stalled events.
6. Route events to a test SNS topic and verify on-call alerting.
7. Document recovery gaps, owners, and remediation deadlines.

## 20. Pre-Production DR Readiness Checklist

### Source Inventory and Replication

- [ ] Are all source servers running supported OSes and architectures?
- [ ] Are disk/volume counts within 64 TiB/volume (gp3 staging disk) and 63 volumes/server?
- [ ] Are agents installed for the right Region, right architecture, and running?
- [ ] Is initial sync finished and replication status Healthy?
- [ ] Have average/peak write rates been measured across at least 24 hours?
- [ ] Does bandwidth include headroom without sustained lag/backlog growth?
- [ ] Are new disks auto-replicated or covered by an onboarding runbook?

### Networking and Staging

- [ ] Is outbound TCP 443 open to DRS/S3/EC2 endpoints?
- [ ] Is TCP 1500 open in the right direction between source and replication servers?
- [ ] Do firewalls/proxies avoid TLS-inspecting the replication stream?
- [ ] Does the staging subnet have proper CIDRs, routes, DNS, SG/NACL, and endpoint policies?
- [ ] Has private IP routing/VPN/Direct Connect been tested if used?
- [ ] Are operational/recovery subnets prepared separately?

### Recovery Launch and Orchestration

- [ ] Do EC2 launch templates specify proper subnets, SGs, IAM roles, instance types, and disk mappings?
- [ ] Does Optimal/Fast recovery mode match source architecture?
- [ ] Are KMS keys, IAM, licenses, and EC2 quotas verified?
- [ ] Are post-launch actions tested and free of plaintext secrets?
- [ ] Do Recovery Plans reflect dependency graphs and Critical/Optional flags?
- [ ] Are wait steps backed by health checks and validation?
- [ ] Was a recent drill successful and properly cleaned up?

### Failover and Failback

- [ ] Are RPO/RTO approved by business owners and measured in drills?
- [ ] Are recovery point selection and data consistency documented in runbooks?
- [ ] Are primary fencing and split-brain prevention clearly defined?
- [ ] Do external traffic cutover mechanisms have clear owners and procedures?
- [ ] Is termination protection enabled on production recovery instances?
- [ ] Has failback been rehearsed for the corresponding source types?
- [ ] Post-failback, is primary re-protected without duplicate server entities?

### Security, Monitoring, and Cost

- [ ] Are IAM least privilege, agent credentials, and service-linked roles governed?
- [ ] Are EBS encryption/KMS policies and snapshot deletion controls reviewed?
- [ ] Are independent immutable backups kept where required?
- [ ] Are CloudWatch metrics, EventBridge events, and CloudTrail audits integrated?
- [ ] Do alarms cover Lag, Backlog, Stalled, Disconnected, and failed launches?
- [ ] Are DRS hourly fees estimated alongside EC2/EBS/networking costs?
- [ ] Is PIT retention appropriate with a designated owner?
- [ ] Does stopping replication or decommissioning require approval and backup verification?

## 21. Self-Assessment Questions

1. What problem does AWS DRS solve in disaster recovery?
2. How do RPO and RTO differ?
3. How does failover differ from a recovery launch?
4. Why does DRS not automatically switch DNS or traffic?
5. Do recovery drills disrupt the source server or ongoing replication?
6. What roles do the source server, replication agent, and staging area play?
7. Which flows use TCP 443 versus TCP 1500?
8. Why must you never TLS-inspect the TCP 1500 replication stream?
9. How does initial sync differ from continuous replication?
10. Why must write throughput remain below available bandwidth?
11. Why does AWS recommend 20% extra bandwidth headroom?
12. What is DRS's typical RPO, and what factors affect it?
13. Does DRS replace AWS Backup or immutable backups?
14. What schedule does a PIT policy use to retain recovery points?
15. What is the configurable range in days for daily PIT retention?
16. Why can DRS snapshots be endangered if an AWS account is compromised?
17. Do changes to default replication settings automatically update existing source servers?
18. How do EBS volume types affect replication cost and performance?
19. How do DRS launch settings and EC2 launch templates fit together?
20. How do Optimal and Fast recovery modes differ?
21. When is Fast mode appropriate, and what minimum agent version does it require?
22. What do post-launch actions use AWS Systems Manager for?
23. What problem do Recovery Plans solve for applications with multi-server dependencies?
24. What are the limits on steps, servers, and wait durations in a Recovery Plan?
25. How do Critical and Optional impact levels differ?
26. Why must Recovery Plan drill instances be terminated manually?
27. How does on-premises failback differ from AWS-to-AWS failback?
28. Why is freezing writes necessary before final failback sync?
29. How many concurrently replicating source servers does DRS support per account/Region?
30. How do multiple staging accounts enable scaling?
31. Which CloudWatch metrics expose replication lag and backlog?
32. Which DRS service events can EventBridge capture?
33. What steps resolve a `NOT_CONVERGING` replication status?
34. Why should you never stop replication purely to save fees without alternate backups?
35. Which steps belong in failover and failback runbooks?
36. Why must RPO/RTO be measured via recovery drills rather than trusting service marketing specs?

### Answer Key Guidance

- **RPO/RTO:** RPO is acceptable data loss; RTO is service recovery time. DRS can achieve sub-second RPO when replication is healthy, but must be measured empirically.
- **Architecture:** The agent streams block changes to replication servers in the staging subnet; EBS volumes/PIT snapshots hold recovery data; DRS launches EC2 instances.
- **Ports:** TCP 443 handles DRS/S3/EC2 APIs and control plane; TCP 1500 handles the TLS 1.2 encrypted replication stream.
- **Recovery:** Drills test non-disruptively; Recovery launches live recovery instances; failover/traffic cutover is executed by the organization outside DRS.
- **Recovery Plans:** Server steps run in parallel within a step and sequentially across steps; wait steps add pauses; Critical/Optional control failure handling.
- **Failback:** Reverse replication sends recovery changes back to source; write freezes and final sync avoid data loss; post-cutover, re-enable protection on primary.
- **Security/cost:** DRS snapshots do not replace immutable backups; IAM/KMS/CloudTrail must be protected; the DRS hourly fee excludes EC2/EBS/network usage.

## 22. Official AWS Documentation

1. [What is AWS Elastic Disaster Recovery?](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html) — Overview of architecture, replication, and recovery.
2. [Getting started with AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/getting-started.html) — Region initialization, agent installation, initial sync, drills, and recovery.
3. [AWS DRS best practices](https://docs.aws.amazon.com/drs/latest/userguide/best_practices_drs.html) — Planning, drilling, monitoring, recovery, failback, and security.
4. [AWS DRS network requirements](https://docs.aws.amazon.com/drs/latest/userguide/Network-Requirements.html) — TCP 443/1500, TLS, and network paths.
5. [Verifying network connectivity](https://docs.aws.amazon.com/drs/latest/userguide/verifying-network-connectivity.html) — Checking ports, routes, security groups, and NACLs.
6. [Agent installation prerequisites](https://docs.aws.amazon.com/drs/latest/userguide/agent-install-prerequisites.html) — Linux/Windows prerequisites and disk/architecture limits.
7. [Supported Linux operating systems](https://docs.aws.amazon.com/drs/latest/userguide/Supported-Operating-Systems-Linux.html) — Linux OS and Graviton support.
8. [Supported Windows operating systems](https://docs.aws.amazon.com/drs/latest/userguide/Supported-Operating-Systems-Windows.html) — Windows OS and architecture support.
9. [Using service-linked roles for AWS DRS](https://docs.aws.amazon.com/drs/latest/userguide/using-service-linked-roles.html) — Service-linked role and permissions.
10. [Replication settings](https://docs.aws.amazon.com/drs/latest/userguide/settings.html) — Default/individual replication, launch, and post-launch settings.
11. [Point-in-time policy](https://docs.aws.amazon.com/drs/latest/userguide/point-in-time.html) — Snapshot intervals and 1–365 day retention.
12. [Replication bandwidth requirements](https://docs.aws.amazon.com/drs/latest/userguide/comm-bandwidth-planning.html) — Calculating write rates, bandwidth, and headroom.
13. [Configuring launch settings](https://docs.aws.amazon.com/drs/latest/userguide/launching-target-servers.html) — EC2 launch templates and recovery instance preparation.
14. [DRS launch settings](https://docs.aws.amazon.com/drs/latest/userguide/launch-general-settings.html) — Right-sizing, start behavior, licensing, and recovery modes.
15. [Post-launch actions](https://docs.aws.amazon.com/drs/latest/userguide/post-launch-action-settings-overview.html) — SSM, validation, and custom automation.
16. [Preparing for recovery and performing drills](https://docs.aws.amazon.com/drs/latest/userguide/preparing-failover.html) — Drill objectives, steps, and cleanup.
17. [Using DRS for recovery and failback](https://docs.aws.amazon.com/drs/latest/userguide/failback.html) — Recovery, failover distinction, and failback mechanisms.
18. [Failback to on-premises](https://docs.aws.amazon.com/drs/latest/userguide/failback-performing.html) — Failback Client and source server recovery.
19. [Recovery Plans concepts](https://docs.aws.amazon.com/drs/latest/userguide/recovery-plans-concepts.html) — Recovery plans, server steps, wait steps, and impact levels.
20. [Adding and ordering Recovery Plan steps](https://docs.aws.amazon.com/drs/latest/userguide/recovery-plans-steps.html) — Step limits and wait durations.
21. [Running a Recovery Plan](https://docs.aws.amazon.com/drs/latest/userguide/recovery-plans-executing.html) — Drill/recovery execution and cleanup.
22. [Using multiple staging accounts](https://docs.aws.amazon.com/drs/latest/userguide/multi-account.html) — Multi-account architecture and scaling beyond one staging account.
23. [AWS DRS quotas](https://docs.aws.amazon.com/general/latest/gr/drs.html) — Service quotas and API limits.
24. [Monitoring DRS with CloudWatch metrics](https://docs.aws.amazon.com/drs/latest/userguide/monitoring-event-bridge-metrics.html) — LagDuration, Backlog, and recovery metrics.
25. [AWS DRS events in EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-drs.html) — Service events and CloudTrail events.
26. [Troubleshooting replication errors](https://docs.aws.amazon.com/drs/latest/userguide/troubleshooting-replication.html) — Agent, network, performance, and replication errors.
27. [Replication performance errors](https://docs.aws.amazon.com/drs/latest/userguide/replication-performance-errors.html) — NOT_CONVERGING, lag, and backlog.
28. [AWS DRS pricing](https://aws.amazon.com/disaster-recovery/pricing/) — Hourly source server pricing and additional resource charges.
29. [AWS DRS FAQ](https://aws.amazon.com/disaster-recovery/faqs/) — RPO, security, failback, multi-account, and service behavior.
30. [AWS DRS service release notes](https://docs.aws.amazon.com/drs/latest/userguide/drs-service-release-notes.html) — Updates to OS support, Graviton, and Recovery Plans.

> **Final Takeaway:** AWS DRS maintains block-level replication into a staging area, retains point-in-time recovery states, and launches EC2 instances for drills and recoveries. Achieving RPO/RTO requires converging replication, accurate launch settings, clear dependency ordering, controlled traffic cutover, and rehearsed failback. DRS is one piece of a DR strategy; immutable backups, security controls, observability, quotas, and cost planning must still be designed separately.
