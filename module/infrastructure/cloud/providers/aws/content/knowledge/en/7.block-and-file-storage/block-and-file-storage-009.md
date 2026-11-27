# Amazon FSx and Choosing a Managed File System

When deploying applications on AWS, not every storage requirement fits an EBS volume or an S3 bucket. A Windows application may require **SMB** folder shares and **NTFS ACL** permissions; Linux servers may need **NFS**; and an AI training cluster may need a parallel filesystem with massive throughput. **Amazon FSx** provides multiple AWS-managed file systems to meet those needs.

This lesson belongs to the **Block and File Storage** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects filesystem selection with Regions/AZs, IAM, VPC, compute services, databases, integration, and serverless. Learners will practice selecting services, designing secure deployments, monitoring, recovery, and cost control.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **block**, **file**, and **object storage** to know when Amazon FSx is needed.
2. Compare **FSx for Windows File Server**, **FSx for Lustre**, **FSx for NetApp ONTAP**, and **FSx for OpenZFS**.
3. Choose the right filesystem based on protocol, operating system, workload, shared data, IOPS, throughput, and latency.
4. Analyze availability, **Single-AZ/Multi-AZ**, backups, snapshots, replication, and RTO/RPO.
5. Design VPCs, hybrid connectivity, encryption, and file access permissions under the shared responsibility model.
6. Establish an evaluation process, AWS CLI inventory checks, data migration, and total cost of ownership estimation.

## 2. Block, File, and Object Storage: Distinguish Before Choosing

| Type | Access model | Common AWS services | Strengths / limitations |
|---|---|---|---|
| **Block storage** | Volume attached to an OS to build a filesystem | **Amazon EBS** | Drives for EC2, databases; does not natively provide multi-machine file shares |
| **File storage** | Directory/file paths, file permissions, SMB/NFS/Lustre protocols | **Amazon EFS, Amazon FSx** | Network-shared data with filesystem semantics |
| **Object storage** | Objects and keys accessed via HTTP APIs | **Amazon S3** | Data lakes, images, logs, artifacts, and object backups |

**S3 is not a standard POSIX/SMB filesystem.** Object keys may look like folders, yet operations such as file locking, atomic renames, random file writes, Windows ACLs, or POSIX permissions are not natively supported. If an application requires those behaviors, evaluate file storage solutions before rewriting code.

**Amazon EBS** provides block storage for EC2 with AZ constraints. Under specific conditions, certain volume types support **Multi-Attach**, though the application must handle concurrent access/clustered filesystems accordingly. EBS does not natively provide shared SMB/NFS file servers. **Amazon EFS** is elastic NFS file storage, usually well suited when multiple Linux apps need shared folders and prefer a simple operational model.

**Amazon FSx** serves applications needing a **specialized filesystem engine**, specific filesystem administration features, or a performance profile not met well by a general-purpose option.

## 3. Four Amazon FSx Engines

Amazon FSx is a family of managed services: AWS operates the file server infrastructure and handles supported maintenance, hardware replacement, backups, or failover. Customers remain responsible for choosing the engine, granting permissions, configuring networking, sizing capacity/performance, governing data, and testing restores.

| FSx engine | Primary protocols | When to use | Distinct capabilities |
|---|---|---|---|
| **FSx for Windows File Server** | **SMB**, Windows/NTFS, Active Directory | Windows apps, home directories, departmental shares | NTFS ACLs, Windows file shares, shadow copies, SSD/HDD, Single-AZ/Multi-AZ |
| **FSx for Lustre** | **Lustre** on Linux | HPC, ML/AI, parallel compute, video processing | High throughput, scratch/persistent deployments, S3 data repository integration per config |
| **FSx for NetApp ONTAP** | **NFS, SMB**, iSCSI, and NVMe/TCP where supported | Multi-protocol Windows/Linux, existing NetApp estates | SVMs, volumes, snapshots, clones, SnapMirror, SSD tier and capacity pool tier |
| **FSx for OpenZFS** | **NFS** | Linux/NFS, apps needing ZFS snapshots/clones | Compression, snapshots, clones, quotas, SSD/Intelligent-Tiering, HA options |

These engines **cannot be switched in place by editing an attribute**. Moving from SMB/Windows to Lustre, or from NFS/EFS to ONTAP, requires a data migration plan, remounting, permission testing, and verifying application file behavior.

### 3.1. Quick Selection Diagram

~~~mermaid
flowchart TD
    R["Application needs storage"] --> A{"What access model is needed?"}
    A -->|"Block disk for EC2"| EBS["Amazon EBS"]
    A -->|"Object API"| S3["Amazon S3"]
    A -->|"File share"| B{"Primary protocol/features"}
    B -->|"SMB, AD, NTFS"| WIN["FSx for Windows File Server"]
    B -->|"HPC/AI, Lustre"| LUS["FSx for Lustre"]
    B -->|"NFS + SMB, NetApp"| ONT["FSx for NetApp ONTAP"]
    B -->|"NFS + ZFS snapshots/clones"| ZFS["FSx for OpenZFS"]
    B -->|"Simple shared NFS"| EFS["Compare Amazon EFS"]
~~~

This diagram is only a starting point. **Regional availability, features, protocols, pricing, and real-world performance** must be verified for the specific application.

## 4. FSx for Windows File Server

### 4.1. Suitable Applications

FSx for Windows File Server provides a managed **Microsoft Windows** file server supporting **SMB**, **NTFS ACLs**, **Microsoft Active Directory**, and familiar Windows file server administration features. It fits migrating data-center file shares to AWS when apps must preserve Windows semantics and existing user permissions.

Examples:

- Departments sharing documents via network folders.
- Enterprise apps requiring SMB shares and Windows file-locking behavior.
- Home directories for users authenticated via Active Directory.
- Workloads on Windows EC2, Amazon WorkSpaces, or on-premises machines over Direct Connect/VPN when properly configured.

Windows **UNC** network paths take the form:

~~~text
\\server-name\share
~~~

In real deployments, use the **DNS name or DNS alias** of the FSx file system along with appropriate AD/SMB permissions.

### 4.2. How Do Active Directory, IAM, and NTFS ACLs Differ?

FSx for Windows integrates with **AWS Managed Microsoft AD** or **self-managed Microsoft AD** per configuration requirements. Permissions are evaluated across multiple layers:

| Layer | What does it govern? | Examples |
|---|---|---|
| **IAM** | Who can create, modify, back up, and describe the file system via AWS APIs? | fsx:DescribeFileSystems, fsx:CreateBackup |
| **Network/VPC** | Which hosts can reach the SMB/AD/DNS endpoints? | Security groups, route tables, firewalls |
| **AD, share permissions, NTFS ACLs** | Which users/groups can read, edit, or delete each file? | AD groups and folder ACLs |

**IAM Allow does not grant permission to read a Windows file share.** A user holding `fsx:DescribeFileSystems` must still authenticate and be authorized by share/NTFS ACLs to access data over SMB.

### 4.3. SSD/HDD and Single-AZ/Multi-AZ

AWS offers **SSD** and **HDD** options with configurable **throughput capacity** and IOPS. SSD fits low-latency workloads or many small files; HDD lowers costs for large, infrequently accessed datasets with modest IOPS demands. File server throughput, disk I/O, and caching jointly shape performance; provisioning large storage capacity does not automatically guarantee high throughput.

**Single-AZ** handles certain component failures within one AZ. **Multi-AZ** deploys a standby file server in another AZ within the same Region, reducing AZ-failure impact and supporting failover. It is **not** a full-Region DR solution. The service supports managed backups, and Windows shadow copies help restore prior file versions per supported mechanisms and configuration.

Checklist items to verify: AD setup, DNS, SMB ports, remote clients, post-migration ACLs, latency from on-premises, SSD/HDD selection, and end-to-end application recovery.

## 5. FSx for Lustre

### 5.1. Why Does Lustre Fit HPC and ML?

**Lustre** is a distributed filesystem built for workloads demanding **parallel I/O and ultra-high throughput**, such as scientific simulations, ML training, video processing, quantitative analytics, or engineering design. Linux compute nodes use a compatible **Lustre client** to mount the filesystem; apps interact normally through file paths.

For example, an EC2 cluster runs many workers reading training datasets. If the bottleneck is file counts, metadata operations, or aggregate bandwidth, benchmark FSx for Lustre with realistic worker counts, I/O sizes, and per-instance networking.

### 5.2. Scratch vs. Persistent

| Deployment type | Target use | Data protection |
|---|---|---|
| **Scratch** | Temporary data, recomputable jobs, short-lived processing | Not replicated like Persistent; file server failure can lose stored data |
| **Persistent** | Longer-running workloads where data must survive component failures | Includes data replication/file server replacement per supported Persistent type |

**Never store the sole copy of critical data on Scratch.** Nor does Persistent replace a proper backup/recovery plan.

### 5.3. Integration with S3 Data Repositories

In supported configurations, FSx for Lustre can link to **Amazon S3** to present objects as files to compute nodes, import updates, and export processing results. Understand the flow clearly:

1. **Import** metadata/file listings from S3.
2. **Load data** onto Lustre as needed for application execution.
3. **Export** files or results back to S3 using appropriate data repository/task commands.
4. Confirm export completion before deleting a short-lived filesystem.

~~~mermaid
flowchart LR
    S["S3: source data"] -->|"Import when supported"| F["FSx for Lustre"]
    F <--> C["EC2 / EKS / HPC workers<br/>Lustre client"]
    F -->|"Export results"| O["S3: durable data"]
~~~

**Important limitations:** not every storage class/deployment supports the exact same S3 repository features. Current AWS documentation notes **Lustre Intelligent-Tiering** does not support S3 data repository associations, and **file system backups are not supported for Lustre file systems linked to an S3 repository** under this mechanism. Verify your chosen tier, data protection, and recovery capabilities.

### 5.4. Measuring Lustre Performance

Inspect cluster-wide throughput, IOPS, file sizes and counts, concurrency, metadata operation timings, EC2 client network speeds, caching, and network bottlenecks. Service-advertised maximum throughput does not guarantee a single-threaded app achieves equivalent speed.

## 6. FSx for NetApp ONTAP

### 6.1. Multi-Protocol Support and Migrating NetApp Systems

**FSx for NetApp ONTAP** provides managed file storage built on ONTAP, supporting **NFS** for Linux and **SMB** for Windows. It also supports block access via **iSCSI** and **NVMe/TCP** on supported generations/configs. This fits organizations already running NetApp on-premises, sharing datasets across protocols, or needing advanced data management features.

Typical capabilities: **volumes, snapshots, cloning, data compression, deduplication, tiering**, and replication like **SnapMirror** under suitable designs.

### 6.2. File System, SVM, and Volumes

~~~mermaid
flowchart TB
    FS["FSx for NetApp ONTAP"] --> SVM["Storage Virtual Machine (SVM)"]
    SVM --> VOL1["Application A volume"]
    SVM --> VOL2["Dataset B volume"]
    W["Windows / SMB"] --> SVM
    L["Linux / NFS"] --> SVM
    VOL1 --> SSD["SSD tier: working set"]
    VOL2 --> POOL["Capacity pool tier: cold data"]
~~~

An **SVM** provides the logical file-serving environment/endpoints per protocol and config. A **Volume** is the logical unit organizing data and policies; logical volume sizes do not necessarily equate one-to-one with pre-allocated physical SSD capacity.

FSx for ONTAP uses an **SSD tier** for high-performance active data and an elastic **capacity pool** for infrequently accessed data governed by a **tiering policy**. Data moves between tiers based on conditions, access patterns, and policies, optimizing costs when hot data is only a fraction of total capacity.

### 6.3. Multi-Protocol Permissions and Backups

If Windows and Linux clients access the same dataset, design **identity mapping**, Windows ACLs, POSIX permissions, NFS export policies, and file locking per application needs. Having both NFS and SMB enabled does not automatically align permissions across both OS account systems.

ONTAP supports **Single-AZ/Multi-AZ** depending on config, backups, and snapshot/replication mechanisms. Snapshots enable fast point-in-time recovery yet **do not inherently protect against full-Region outages**. When using SnapMirror or another DR design, verify network paths, app recovery sequencing, and replication lag.

## 7. FSx for OpenZFS

### 7.1. NFS File Systems with ZFS Capabilities

**FSx for OpenZFS** provides file storage powered by OpenZFS, accessed primarily via **NFS**. It fits Linux applications requiring low-latency file operations, **snapshots/clones**, compression, quotas, and ZFS-style volume management.

Windows and macOS can connect via compatible NFS clients where supported, yet **OpenZFS is not an SMB/NTFS server equivalent to FSx for Windows File Server**. If native Windows shares and Active Directory integration are needed, evaluate Windows File Server or ONTAP.

### 7.2. Storage Classes and HA

Per current AWS documentation, FSx for OpenZFS offers:

- **SSD storage class:** provisions dedicated SSD capacity, prioritizing consistent low-latency performance across the entire dataset.
- **Intelligent-Tiering:** bills based on stored usage with an optional **SSD read cache** for hot data, suited to optimizing costs around the active working set.

Deployment types include **Multi-AZ (HA)**, **Single-AZ (HA)**, and **Single-AZ (non-HA)**. Multi-AZ replicates data across AZs within the Region; Single-AZ HA runs primary/standby inside one AZ; Single-AZ non-HA has different component recovery mechanics. Evaluate each option against RTO/RPO, fault tolerance, and price.

**Snapshots** serve as filesystem-level restore points; **managed backups** provide separate data protection. Even with snapshots, maintain backups and rehearse restores for accidental deletions, corruption, or Regional outages.

## 8. Comparing FSx with EFS, EBS, and S3 by Scenario

| Problem | Option to evaluate first | Reason |
|---|---|---|
| Windows shares, AD, NTFS ACLs | **FSx for Windows File Server** | Native Windows app and permission compatibility |
| Linux needing shared NFS without ZFS/ONTAP dependencies | **Amazon EFS** | Elastic NFS with simple management |
| Linux needing NFS, ZFS snapshots/clones, working-set tiering | **FSx for OpenZFS** | OpenZFS filesystem features |
| Windows/Linux sharing data, existing on-prem NetApp | **FSx for NetApp ONTAP** | NFS/SMB plus volume management and tiering |
| Parallel ML/HPC compute | **FSx for Lustre** | Built for high-performance parallel I/O |
| OS/application disks on EC2 | **Amazon EBS** | Block volumes for compute |
| Images, logs, data lakes, object payloads | **Amazon S3** | Object API and object storage model |

### 8.1. Why Doesn't "NFS" Always Mean the Same Service?

**EFS**, **FSx for OpenZFS**, and **FSx for ONTAP** can all serve NFS applications, yet they differ in provisioning models, performance limits, caching, scaling, snapshots, permissions, HA, replication, pricing, and operational complexity. Picking the right one depends on **file semantics and measured workload traits**, not protocol alone.

### 8.2. Where Can FSx Be Accessed From?

Depending on the engine, clients, and driver versions, these filesystems can be used from **EC2**, certain **ECS/EKS** environments, or **on-premises** networks. Verify Lustre clients, NFS/SMB clients, Kubernetes CSI drivers, DNS settings, and network reachability.

For on-premises access, design **Direct Connect or Site-to-Site VPN**, bidirectional routing, firewalls, DNS, and measure latency. Never assume FSx file servers are exposed directly to the public Internet.

## 9. Criteria to Measure Before Deciding

| Criterion | Technical question | Evidence |
|---|---|---|
| **Protocol** | Are SMB, NFS, Lustre, or iSCSI block required? | How the app mounts, client versions |
| **File semantics** | Are locking, ACLs, renames, snapshots, or symlinks required? | Application integration test suite |
| **Throughput** | What aggregate MB/s do concurrent clients read/write? | Peak throughput benchmark |
| **IOPS** | How many ops/s, what I/O size, and read/write ratio? | Traces and live metrics |
| **Latency** | What are p95/p99 targets for critical operations? | Load test with representative data |
| **Metadata operations** | Are there millions of tiny files or heavy list/stat calls? | Profiling |
| **Capacity** | How fast does data grow; what is the hot vs. cold split? | Capacity history and working set |
| **Availability** | Single-AZ, Multi-AZ, or cross-Region DR? | RTO/RPO, failover tests |
| **Security** | Who accesses files and who administers FSx? | IAM, AD/POSIX, SG/KMS, auditing |
| **Cost** | Are throughput, tiers, backups, and networking all included? | Estimates for exact Region and engine |

**Throughput** is bytes/second; **IOPS** is I/Os/second; **latency** is operation completion time. Video processing may demand high throughput across few files, while an app storing millions of small receipts can hit IOPS/metadata limits even with modest total capacity.

## 10. Single-AZ, Multi-AZ, Snapshots, Backups, and DR

Each protection layer mitigates different failures:

| Mechanism | Value | Limitations |
|---|---|---|
| **HA/Multi-AZ** | Keeps service running across component or AZ failures as supported | Does not undo accidental user deletions or bad edits |
| **Snapshot** | Fast file system/volume restore point | Not inherently an isolated off-system/off-Region copy |
| **Managed backup** | Point-in-time copies with retention controls | Does not guarantee ultra-low RTO if restore takes time |
| **Replication** | Data copies serving secondary workflows or sites | Can replicate accidental deletes or corruption |
| **Restore drill** | Proves applications actually run after recovery | Must be repeated whenever architecture changes |

**RTO (Recovery Time Objective)** is the target service recovery duration; **RPO (Recovery Point Objective)** is the maximum tolerable data loss over time. A Multi-AZ filesystem still needs backups. If the system must survive a full-Region outage, build a cross-Region or approved-site DR architecture covering data, compute, DNS, IAM, KMS, and routing.

Snapshot/backup/replication support **varies across engines**. Specifically with Lustre Scratch or S3-linked Lustre data repositories, verify exact data protection constraints instead of assuming automatic backups work just like Windows File Server.

## 11. Security and Networking

### 11.1. VPC, Subnets, Security Groups, and DNS

FSx connects to your VPC via service-managed network interfaces. Design requires proper subnets/AZs, SGs, route tables, firewalls, DNS, filesystem endpoints, and protocol ports.

~~~mermaid
flowchart LR
    subgraph VPC["VPC"]
        EC2["EC2 / container client"]
        NET["Routing + SG + DNS"]
        FSX["FSx file system<br/>SMB / NFS / Lustre"]
        EC2 --> NET --> FSX
    end
    OP["On-premises"] -->|"DX / VPN"| NET
    API["AWS management API"] -->|"IAM control plane"| FSX
~~~

**Having network reachability does not grant file read permissions.** Clients must pass protocol and filesystem protections: SMB/AD ACLs, NFS UID/GID/export policies, ONTAP permissions, or equivalent rules.

### 11.2. Three Authorization Layers

| Layer | Examples | Scope |
|---|---|---|
| **IAM control plane** | fsx:DescribeFileSystems, fsx:CreateBackup | Resource administration via AWS APIs |
| **Network** | VPC routes, SGs, firewalls, DX/VPN | Controls whether clients can reach endpoints |
| **File data plane** | NTFS ACLs, AD, POSIX modes, NFS exports, ONTAP ACLs | Controls which accounts/processes can read, edit, or delete files |

Apply least privilege across all three layers, enable **encryption at rest** via each engine's KMS integration, and use **encryption in transit** per supported protocol settings. Never claim all NFS clients or SMB streams are automatically encrypted without verifying.

### 11.3. Does CloudTrail Log Every File Read?

**CloudTrail** logs supported AWS management API calls; that **does not mean every SMB/NFS/Lustre file read/write appears in CloudTrail**. When file-access auditing is required, configure each engine's native auditing/logging tools and verify log retention, destination, and read permissions. For instance, Windows provides file-access auditing mechanisms, and ONTAP includes logging features by design.

**Data residency** requirements must cover the primary filesystem, snapshots, backups, linked repositories, DR copies, and exports. Picking one Region does not automatically block every copy or export path out of that Region.

## 12. Selection and Deployment Workflow

### Step 1 — Characterize the Workload

Gather OS, protocol, client versions, file locking/renames, ACLs, client counts, file profiles, working set size, throughput/IOPS/latency targets, HA requirements, location, and budget.

**Output:** mandatory requirements—such as "SMB + AD" or "Lustre clients with high parallel throughput"—and optimization criteria.

### Step 2 — Eliminate Unsuitable Engines

If SMB/NTFS is mandatory, eliminate EFS/OpenZFS NFS as direct replacements. If Lustre clients are needed, evaluate FSx for Lustre. For NFS, compare EFS, OpenZFS, and ONTAP across features, performance, and cost. Confirm **the engine, storage class, and deployment type are available in your target Region**.

### Step 3 — Design Networking and Permissions

Define VPC, subnets, SGs, routes, DNS, AD/POSIX identities, KMS keys, and least-privilege access. For hybrid apps, inspect DX/VPN, latency, and bidirectional firewalls; pick matching container drivers/mounts.

### Step 4 — Size Capacity and Availability

Choose storage class, provisioned throughput, IOPS, SSD/HDD, or cold tiers per engine. Choose Single-AZ/Multi-AZ and backup/replication aligned with RTO/RPO. Never overbuy maximum throughput just to cut downtime: HA and performance are separate axes.

### Step 5 — Migrate Data and Test

Depending on the engine, evaluate **AWS DataSync**, SMB/NFS copy tools, NetApp tools, or Lustre's S3 data repository **where supported**. Verify:

- File lists, checksums, permissions, owners, ACLs, and timestamps.
- App behavior with locking, concurrency, renames, hidden files, and special files.
- DNS resolution and mounts in the target environment.
- Delta sync, cutover, write freeze, and rollback steps.

**Never assume migration tools preserve every permission/metadata attribute across engines or protocols.** Validate with representative application data.

### Step 6 — Rehearse Recovery and Operations

Test backup restores, link outages, deployment-appropriate failover, mount errors, and client reconnection. Configure CloudWatch alarms, backup policies, runbooks, owner tags, permission audits, and capacity review cadences.

## 13. Inventorying Amazon FSx via AWS CLI

These examples are read-only and require an AWS profile with matching permissions. Replace **Region** and **file system ID** with real authorized resources.

~~~bash
# Inventory file systems and engines in a Region.
aws fsx describe-file-systems \
  --region ap-southeast-1 \
  --query 'FileSystems[].{Id:FileSystemId,Type:FileSystemType,State:Lifecycle,CapacityGiB:StorageCapacity}' \
  --output table

# Inspect detailed configuration of one file system.
aws fsx describe-file-systems \
  --region ap-southeast-1 \
  --file-system-ids fs-0123456789abcdef0 \
  --output json

# List backups visible to the account.
aws fsx describe-backups \
  --region ap-southeast-1 \
  --query 'Backups[].{Id:BackupId,Type:Type,State:Lifecycle,Created:CreationTime}' \
  --output table

# View volumes exposed by the FSx API.
aws fsx describe-volumes \
  --region ap-southeast-1 \
  --query 'Volumes[].{Id:VolumeId,Name:Name,Type:VolumeType,State:Lifecycle}' \
  --output table
~~~

`FileSystemType` values are typically **WINDOWS**, **LUSTRE**, **ONTAP**, or **OPENZFS**. Engine-specific fields live in nested structures such as **WindowsConfiguration**, **LustreConfiguration**, **OntapConfiguration**, or **OpenZFSConfiguration** when returned by the API.

Output from one Region or account **does not represent the whole organization**. Seeing zero managed backups does not prove data lacks protection in another layer (such as S3 exports or replication). Cross-check actual policies and data flows.

### 13.1. Engine-Specific Performance Monitoring

| Engine | What to watch |
|---|---|
| **Windows File Server** | Throughput capacity, disk IOPS, SSD/HDD behavior, SMB session counts, shadow copies, latency |
| **Lustre** | Aggregate read/write throughput, metadata bottlenecks, client load, S3 export status |
| **ONTAP** | SSD tier utilization, volume quotas, capacity pool access, tiering activity, snapshots |
| **OpenZFS** | Free space, NFS latency, cache/working set hits, snapshots/clones, storage class |

Use **CloudWatch AWS/FSx** and engine-specific metrics per service docs. Never apply one generic metric name or alarm threshold across every filesystem engine. Increasing storage capacity will not resolve bottlenecks if the true limit is network throughput, server CPU, metadata, or clients.

## 14. Evaluating Total Cost

Total cost should account for:

| Category | Cost components to include |
|---|---|
| **Storage** | Provisioned SSD/HDD capacity, or consumed capacity per storage class |
| **Throughput/IOPS** | File server throughput capacity and billable IOPS in supporting engines |
| **Data tiering** | Capacity pool/tiers, read/write access charges, and caching per current pricing |
| **Data protection** | Backups/snapshots, retention storage, copies, DR environments, and drills |
| **Network** | Cross-AZ/Region transfer, DX/VPN, and intermediate gateways/services if incurred |
| **Identity and ops** | Active Directory, migration, auditing, monitoring, on-call effort, and downtime |

Never compare **USD/GB/month** alone. Low-cost storage with inadequate throughput can prolong batch runtimes and inflate compute bills. Conversely, over-provisioning SSD/IOPS for cold data wastes budget. Use pricing tables for your exact **Region/engine**, the AWS Pricing Calculator, and real load tests.

## 15. Practice Scenarios

### Scenario A — Migrating a Windows File Share

A company has employees using Windows network folders, logging in via AD, and wants to preserve NTFS ACLs when migrating to AWS.

**Question:** which engine should be evaluated, and what must be checked before cutover?

**Hint:** choose **FSx for Windows File Server**. Verify AD/DNS, networking/SMB, SSD/HDD for I/O needs, Single-AZ/Multi-AZ per RTO, ACL-preserving migration, login tests, and restore drills. OpenZFS NFS cannot directly replace SMB/NTFS shares.

### Scenario B — AI Training on an S3 Dataset

An ML team has a large S3 dataset and hundreds of EC2 workers needing parallel high-throughput reads. Outputs must be preserved long term after each training run.

**Question:** how should the working filesystem and durable store be designed?

**Hint:** evaluate **FSx for Lustre** with suitable storage/deployment options, linked to S3 where supported, mounted via the Lustre client and benchmarked under load. Keep source datasets and key outputs in S3; never use Scratch as the sole copy. Verify export completion and backup limitations.

### Scenario C — Multi-Protocol File Share

A Windows team needs SMB and a Linux team needs NFS over the same dataset, with most data rarely accessed. The company currently runs NetApp on-premises.

**Question:** what are ONTAP's strengths and risks?

**Hint:** evaluate **FSx for NetApp ONTAP** for NFS/SMB, volumes, SSD/capacity pool tiering, snapshots, and replication. Design identity mapping, permissions/locking, quotas, data tiering costs, and DR drills carefully.

### Scenario D — NFS Needing Snapshots and Clones

A Linux application needs fast dataset cloning for test environments, wants ZFS features, and requires NFS.

**Question:** EFS or OpenZFS?

**Hint:** compare **FSx for OpenZFS** against **EFS** across snapshots/clones, storage classes, performance, cost, HA, and operational needs. EFS remains a strong fit if simple elastic NFS is all that is needed.

### Scenario E — Backups Exist, Yet Mounts Fail After Recovery

A team has filesystem backups, but after restoring, applications cannot connect because DNS, AD, and security groups in the recovery environment were never configured.

**Question:** can we claim RTO/RPO are met simply because backups exist?

**Hint:** not yet. You must validate end-to-end recovery: file data, clients, DNS, networking, IAM/ACLs, secrets, applications, traffic cutover duration, and data consistency.

## 16. File System Selection Checklist

- [ ] Distinguished **block/file/object** needs and confirmed mandatory file semantics.
- [ ] Selected protocol: **SMB/NFS/Lustre** or iSCSI block where supported.
- [ ] Verified engine, deployment type, and storage class availability in the target **Region**.
- [ ] Measured client counts, hot/cold capacity, throughput, IOPS, latency, and metadata operations.
- [ ] Selected Single-AZ/Multi-AZ and backup/DR design aligned with RTO/RPO.
- [ ] Designed VPC, subnets, SGs, routes, DNS, and hybrid connectivity if needed.
- [ ] Separated **IAM APIs**, network access, and file-level AD/ACL/POSIX permissions.
- [ ] Configured encryption, KMS, file auditing, and data residency per policy.
- [ ] Tested apps with real file permissions, renames/locking, multiple clients, and realistic jobs.
- [ ] Tested migration, cutover/rollback, backups, and restores.
- [ ] Configured CloudWatch alerts, owner tags, runbooks, and capacity review schedules.
- [ ] Estimated costs across storage, throughput, IOPS, tiering, backups, networking, and operations.

## 17. Key Takeaways

**Amazon FSx** is a family of managed file storage services with specialized engines: **Windows File Server** for SMB/AD/NTFS; **Lustre** for parallel HPC/AI compute; **NetApp ONTAP** for multi-protocol and deep data management features; and **OpenZFS** for NFS/ZFS, snapshots, and clones. **Amazon EFS** fits simple elastic shared NFS; **EBS** serves block storage; **S3** serves object storage.

Selection starts with **protocol and file semantics**, then optimizes **performance, HA/DR, security, networking, backups, and total cost**. Managed services remove hardware toil, yet do not eliminate the customer's responsibility for application design and recovery testing.

### Official AWS Documentation for Reference

- [Amazon FSx documentation](https://docs.aws.amazon.com/fsx/) — documentation for all FSx engines.
- [FSx for Windows File Server — What is](https://docs.aws.amazon.com/fsx/latest/WindowsGuide/what-is.html) — SMB, AD, Windows ACLs, and backups.
- [FSx for Windows — Performance](https://docs.aws.amazon.com/fsx/latest/WindowsGuide/performance.html) — storage types, throughput, and disk IOPS.
- [FSx for Lustre — What is](https://docs.aws.amazon.com/fsx/latest/LustreGuide/what-is.html) — HPC/ML, Scratch, and Persistent.
- [FSx for Lustre — Using data repositories](https://docs.aws.amazon.com/fsx/latest/LustreGuide/fsx-data-repositories.html) — S3 integration and limitations.
- [FSx for NetApp ONTAP — What is](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/what-is-fsx-ontap.html) — multi-protocol, tiering, and replication.
- [FSx for ONTAP — Volume storage capacity](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/volume-storage-capacity.html) — tiering policies and SSD/capacity pools.
- [FSx for OpenZFS — What is](https://docs.aws.amazon.com/fsx/latest/OpenZFSGuide/what-is-fsx.html) — NFS, SSD/Intelligent-Tiering, snapshots, and HA.
- [Amazon EFS — What is](https://docs.aws.amazon.com/efs/latest/ug/whatisefs.html) — elastic NFS.
- [Amazon FSx pricing](https://aws.amazon.com/fsx/pricing/) and [AWS Pricing Calculator](https://calculator.aws/) — cost estimation by engine and Region.
