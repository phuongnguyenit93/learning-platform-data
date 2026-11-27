# Distinguishing Block Storage, File Storage, and Object Storage

> **Chapter:** Block and File Storage  
> **Module:** CLOUD_PROVIDERS_AWS — explore the AWS ecosystem from Regions/Availability Zones (AZs), IAM, and VPC to compute, storage, databases, integration, and serverless; practice selecting services and building secure, monitored, resilient, and cost-controlled systems.

## Learning Objectives

After this lesson, you will be able to:

1. Explain how **block storage**, **file storage**, and **object storage** organize, identify, and provide access to data.
2. Choose the right AWS service: **Amazon EBS** (block), **Amazon EFS / Amazon FSx** (file), or **Amazon S3** (object) based on application interface and business requirements.
3. Compare IOPS, throughput, latency, shareability, AZ/Region availability, durability, backup, and RPO/RTO.
4. Design authorization and data protection using IAM, encryption/KMS, filesystem permissions, Security Groups, and bucket policies.
5. Identify costs across capacity, performance, requests, retrieval, data transfer, and backups.
6. Read AWS configurations using the CLI in read-only mode and troubleshoot common storage issues.

## 1. Where Do the Three Storage Models Differ?

You should not choose storage simply by asking "how many GB do I need?" You need to determine how the application wants to **interact with data**.

- **Block storage** provides a block-level storage device, similar to a disk drive that the operating system can partition, format with a filesystem, and read/write blocks on. Applications typically operate on files within the filesystem sitting on top of this drive.
- **File storage** provides a filesystem with a directory tree, files, metadata, and access permissions. Clients can mount it over protocols such as NFS or SMB, and multiple machines can share the same namespace when supported by the service.
- **Object storage** stores objects consisting of content, a key, and metadata. Applications access objects by bucket/key through APIs such as GET, PUT, LIST, and DELETE rather than mounting a standard POSIX filesystem.

The same report file can be stored in three ways:

| Type | How the application sees it | Typical AWS service |
| --- | --- | --- |
| **Block** | File **/data/reports/q4.pdf** in an ext4/XFS filesystem placed on a block volume. | Amazon EBS attached to EC2. |
| **File** | File **/mnt/shared/reports/q4.pdf** in a shared filesystem mounted via NFS/SMB. | Amazon EFS or an Amazon FSx variant. |
| **Object** | Object with a bucket and key, e.g. **s3://example-reports/reports/q4.pdf**, read via SDK/API. | Amazon S3. |

**Key takeaway:** Although all three can store PDF content, the three types carry **different interfaces, semantics, and operational responsibilities**. Replacing a filesystem path with an S3 URI does not automatically make a POSIX application compatible with object storage.

~~~mermaid
flowchart TD
    A["Application needs to store data"] --> Q{"How does the application access data?"}
    Q -->|"Block device / OS filesystem"| B["Block storage — EBS"]
    Q -->|"File / directory / shared mount"| F["File storage — EFS or FSx"]
    Q -->|"Bucket + key via API"| O["Object storage — S3"]
~~~

## 2. Block Storage and Amazon EBS

### 2.1. How Does a Block Device Work?

A block device provides storage space divided into addressable blocks. The OS manages I/O operations and typically creates a filesystem such as **ext4** or **XFS**. Above the filesystem, applications can read/write files, database data pages, or transaction logs.

~~~mermaid
flowchart LR
    APP["Application / Database"] --> FS["ext4 / XFS Filesystem"]
    FS --> OS["Linux block I/O"]
    OS --> VOL["EBS volume"]
    VOL --> AZ["Infrastructure within one Availability Zone"]
~~~

Block storage fits when a workload needs:

- A virtual machine's boot disk or data disk.
- Random access (**random I/O**) with small blocks of data.
- Control over filesystem, capacity, IOPS, and throughput per workload.
- Compatibility with software that assumes a local drive or block device.

**Block storage does not mean applications do not use files.** Files on EBS are typically managed by the operating system's filesystem. "Block" refers to the **interface that the storage service exposes**.

### 2.2. What Is EBS?

**Amazon Elastic Block Store (EBS)** provides managed block volumes for EC2. An EBS volume resides in **one specific AZ**; typically it is attached to a compatible EC2 instance in the **same AZ**. An instance can have a root volume and multiple data volumes subject to resource limits.

Examples:

- **Root volume** containing the EC2 operating system.
- **Data volume** containing application files or self-managed database data.
- **Scratch/work volume** storing data requiring block I/O, with retention/backup policies depending on its nature.

### 2.3. Can EBS Be Shared Across Multiple EC2 Instances?

The standard model is **one EBS volume attached to one EC2 instance** at a time. **EBS Multi-Attach** supports certain volume types such as io1/io2 under documented conditions, allowing multiple EC2 instances in the **same AZ** to attach a single volume.

However, Multi-Attach **does not automatically turn EBS into an NFS/SMB shared filesystem**. If multiple instances write concurrently on a filesystem that does not support cluster access and lacks coordination/locking mechanisms, data can become corrupted. When multiple EC2 instances across multiple AZs need the same file namespace, evaluate **EFS** or the appropriate **FSx** option first.

### 2.4. EBS Volume Types and Performance Metrics

| Metric | Meaning | Workloads sensitive to this metric |
| --- | --- | --- |
| **IOPS** | Number of read/write I/O operations per second. | Transactional databases, random access. |
| **Throughput** | Amount of data transferred per second (MiB/s). | Sequential reads/writes and large files. |
| **Latency** | Time to complete a single I/O operation. | Latency-sensitive applications needing fast response. |

Common EBS volume families:

- **gp3**: General-purpose SSD, allowing independent configuration of capacity, IOPS, and throughput within volume limits.
- **io1/io2**: SSDs for workloads requiring provisioned IOPS and other performance/durability characteristics depending on volume type.
- **st1/sc1**: HDDs for suitable sequential or infrequently accessed workloads; cannot be boot volumes in supported configurations.

Volume specs are not guaranteed end-to-end application performance. **EC2 EBS bandwidth** limits, queue depth, I/O size, the filesystem, and the database also affect results.

### 2.5. AZ Scope and Snapshots in EBS

EBS volumes are designed with redundancy within an AZ, but **a volume does not automatically move or attach across multiple AZs** when an AZ experiences an outage. To recover in another AZ, you can create an **EBS snapshot**, then create a new volume from the snapshot in the target AZ and execute application recovery steps.

EBS snapshots are AWS-managed, incremental, and do not appear as regular objects in an S3 bucket of your choice. A snapshot can capture data at a point in time, but recovering a consistent database may require coordination with the database engine, flush/quiesce, or the application.

**EBS does not inherently provide HA for a database.** If an always-available database is required, you must design replication and failover or consider Amazon RDS/Aurora depending on requirements.

## 3. File Storage: Shareable Filesystems

### 3.1. Characteristics of File Storage

File storage represents data using **files**, **directories**, paths, metadata, read/write permissions, and filesystem semantics. Applications open files by path, perform reads/writes, renames, directory creation, or locking according to **the capabilities of the protocol and filesystem**.

Example:

~~~text
/projects/
  finance/2026/report.pdf
  uploads/avatar-001.png
  processing/jobs/2026-11-20/input.csv
~~~

Shared file storage is typically accessed over the network:

- **NFS**: common with Linux/Unix.
- **SMB**: common with Windows, file sharing, and Active Directory integration.
- Other specialized protocols depending on the filesystem.

**File storage is not synonymous with "having a file path in the OS."** EBS can also hold a filesystem; the difference is that a file storage service presents a **network-accessible filesystem** to authorized clients that mount it.

### 3.2. Amazon EFS for Shared Linux Filesystems

**Amazon Elastic File System (EFS)** provides a managed filesystem over **NFS**, enabling multiple Linux clients/workloads to share a common namespace. EFS is suitable when EC2 instances or containers need to see the same data via filesystem paths.

~~~mermaid
flowchart TB
    subgraph AZ1["Availability Zone A"]
        A["EC2/App A"]
        MA["Mount target A"]
    end
    subgraph AZ2["Availability Zone B"]
        B["EC2/App B"]
        MB["Mount target B"]
    end
    EFS[("Amazon EFS Regional")]
    A -->|"NFS TCP/2049"| MA
    B -->|"NFS TCP/2049"| MB
    MA --> EFS
    MB --> EFS
~~~

With **EFS Regional**, data is designed to be stored across multiple AZs, and mount targets can be created in the appropriate AZs. **EFS One Zone** stores data in a single AZ and carries single-AZ risk characteristics. Do not assume every EFS deployment is Multi-AZ.

Key EFS characteristics to know:

- Storage scales up/down automatically based on the amount of stored data under the service model.
- Multiple clients can access concurrently with supported NFS semantics.
- **EFS Access Points** are available to enforce root directories and set POSIX identities for workloads using the access point.
- Performance depends on **throughput mode**, storage class, metadata access patterns, network, and concurrency.
- Requires mount targets, DNS, Security Groups, NFS port **2049**, POSIX permissions, and TLS/IAM where applicable.

EFS is not directly an **SMB share for Windows**. For Windows applications relying on SMB/NTFS/Active Directory, consider FSx for Windows File Server.

### 3.3. Amazon FSx for Specialized Filesystems

**Amazon FSx** is not a single filesystem. It is a family of managed services selected based on operating system, protocol, and workload characteristics.

| Service | Characteristics | Suitable use cases |
| --- | --- | --- |
| **FSx for Windows File Server** | SMB, Windows ACLs, and Active Directory integration as supported. | Windows file servers/applications needing shared folders. |
| **FSx for Lustre** | High-performance filesystem supporting S3 integration for HPC/ML workflows. | High-performance computing, training/analytics requiring high throughput. |
| **FSx for NetApp ONTAP** | Supports enterprise storage features and protocols such as NFS, SMB, and iSCSI. | Enterprise NAS, applications needing ONTAP capabilities. |
| **FSx for OpenZFS** | Filesystem built on OpenZFS, supporting NFS and related features. | Linux applications wanting the OpenZFS filesystem model. |

Some FSx offerings, particularly FSx for NetApp ONTAP, can support **block access via iSCSI**. Therefore, the service name does not always dictate a single access model; check the **enabled protocols**.

Multi-AZ options, backups, replication, endpoints, throughput capacity, and IOPS in FSx vary by variant/deployment. Do not use Lustre specs to infer Windows File Server costs or semantics.

### 3.4. A Mounted EBS Volume and EFS Both Have Paths: What Is the Difference?

~~~text
/data/orders.db               # Can reside in a filesystem on EBS
/mnt/shared/orders/export.csv # Can reside in EFS NFS
~~~

In the first example, the **EC2/OS** manages the filesystem on the EBS volume; if the machine is replaced or another instance needs the data, you must design an appropriate attach/restore/replication workflow.

In the second example, **EFS** provides a shared filesystem; multiple clients can mount it and see the shared namespace without moving an EBS volume between machines. In return, you must ensure network mounting, NFS semantics, and client permissions are properly configured.

## 4. Object Storage and Amazon S3

### 4.1. What Makes Up an Object?

An **object** consists of content (body), a **key**, and metadata/attributes. In Amazon S3, objects live inside a **bucket**. Applications call APIs such as **PutObject**, **GetObject**, **ListObjectsV2**, or **DeleteObject** to interact with them.

~~~mermaid
flowchart LR
    APP["Application / AWS SDK"] -->|"HTTPS API"| S3["Amazon S3"]
    S3 --> BUCKET[("Bucket example-assets")]
    BUCKET --> O1["images/avatar.png"]
    BUCKET --> O2["reports/2026/q4.pdf"]
    BUCKET --> O3["logs/app/event.json"]
~~~

An object key like **reports/2026/q4.pdf** looks like a path, but the slashes are simply part of the key/prefix in the S3 general-purpose bucket model. It does not automatically provide full POSIX directory semantics such as inodes, atomic renames, or NFS file locking.

### 4.2. What Types of Data Is S3 Suited For?

- Images, videos, PDFs, and user attachments.
- Data lakes, analytics datasets, and batch ETL inputs/outputs.
- Backups, archives, versioned objects, and long-term logs.
- Static assets distributed via Amazon CloudFront.
- Data accessed by multiple applications via SDK/HTTP APIs.

S3 offers multiple storage classes. **S3 Standard** is designed to store data across multiple AZs, whereas classes like **S3 One Zone-IA** or **S3 Express One Zone** have single-AZ characteristics. Do not assume **all S3 objects share the same AZ distribution, latency, retrieval behavior, and fees**.

### 4.3. How S3 Differs from a POSIX Filesystem

A traditional filesystem allows applications to open a file and manipulate it at arbitrary offsets, rename, chmod, and use filesystem locking and metadata. **The S3 object API does not guarantee all of those behaviors.**

- Objects are typically created/overwritten via PUT or supported upload mechanisms.
- GET can read an object or an appropriate byte range, but it is not a block device for applications performing random sector-level writes.
- S3 does not turn multiple object updates into a single ACID transaction.
- Some gateways/mount adapters for S3 expose file paths, but have **consistency, rename, locking, caching, or performance limitations** that differ from a POSIX filesystem.

Therefore, **do not place self-managed MySQL/PostgreSQL data files directly on an "S3 mount" as if it were EBS** simply because a driver presents a directory.

### 4.4. S3 Consistency

S3 provides **strong read-after-write consistency** for documented object operations such as PUT, GET, LIST, and DELETE. After a successful object write, subsequent requests observe the data according to the published consistency model.

This does not mean multiple objects update in an ACID transaction, does not replace database transaction locks, and does not turn S3 into an NFS filesystem.

### 4.5. Bucket/Key and Versioning

Example:

~~~text
Bucket: example-course-assets
Key:    uploads/2026/contract.pdf
S3 URI: s3://example-course-assets/uploads/2026/contract.pdf
~~~

If **versioning** is enabled, the same key can retain multiple versions to recover from overwrites/deletes under configured rules. Versioning alone does not make an application safe from all logic bugs or replace backup/retention policies.

## 5. Comparison Table of the Three Storage Types

| Attribute | **Block** | **File** | **Object** |
| --- | --- | --- | --- |
| Interface | Block device; OS creates filesystem if needed. | Filesystem, file path, NFS/SMB/specialized features. | Bucket, key, HTTP API/SDK. |
| Typical AWS service | **EBS**. | **EFS**, **FSx**. | **S3**. |
| Access unit | Device I/O block. | File/directory. | Object. |
| Random read/write | Suitable for supported workloads/FS. | According to filesystem and protocol semantics. | Not a byte-offset random write API like a disk drive. |
| Multi-machine sharing | Standard EBS limited to one instance; Multi-Attach conditional. | Designed for multi-client filesystem access. | Multiple independent clients via API with appropriate permissions. |
| Access pattern | OS/app sees block volume. | OS/app sees mount/share. | Application uses SDK/API. |
| Typical data | Boot volumes, self-managed databases, local data. | Shared workspaces, SMB shares, HPC files. | Images, videos, logs, backups, data lakes. |
| AZ scope | EBS volume belongs to one AZ. | EFS Regional/One Zone; FSx depends on deployment. | S3 Standard multi-AZ; other classes may be single-AZ. |
| Scaling | Provision volume and resize FS accordingly. | EFS scales elastically with data; FSx per its own capacity/provisioning. | Scales object count within service limits. |
| Performance | Volume IOPS, throughput, EC2 EBS bandwidth. | Throughput, metadata operations, network, concurrency. | Request rate, size, concurrency, data processing. |
| Access control | IAM for AWS actions, OS/filesystem permissions. | IAM/network, POSIX/SMB/ACLs, and applicable resource policies. | IAM, bucket/object policies, Block Public Access, KMS. |
| Backup | EBS snapshots, AWS Backup, app-consistent backups. | Backup/replication/lifecycle per EFS or FSx. | Versioning, replication, Object Lock, lifecycle where supported. |
| Cost | Provisioned GB, additional IOPS/throughput, snapshots. | Stored/provisioned GB, throughput, backups, protocol/deployment. | Storage class, requests, retrieval, data transfer, retention. |

**Note:** Data protection quality cannot be reduced to a chart claiming "block is less durable than object." Durability, availability, and recoverability must be evaluated against **each specific service, configuration, storage class, backup strategy, and RPO/RTO requirements**.

## 6. How to Choose a Service for AWS Workloads

### 6.1. Decision Matrix

| Requirement | Service to evaluate first | Reason |
| --- | --- | --- |
| Boot disk for EC2. | **EBS**. | EC2 requires a block volume for the root filesystem. |
| Self-managed PostgreSQL/MySQL on EC2. | **EBS SSD** plus DB backup/replication design. | Database requires block/filesystem access and appropriate latency/IOPS. |
| Multiple Linux EC2 instances across AZs needing a shared folder. | **EFS Regional**. | Shared NFS filesystem for multiple clients. |
| Windows applications needing SMB and Active Directory. | **FSx for Windows File Server**. | Windows shares and permissions. |
| ML/HPC needing a high-throughput filesystem. | **FSx for Lustre** per workload needs. | High-performance computing FS with data workflow integration. |
| Avatars/images, web assets, videos, SDK file uploads. | **S3**. | Object storage, lifecycle, API, and CloudFront integration. |
| Storing logs/data lakes/archives. | **S3** with an appropriate class. | Object access, large-scale data, and long-term retention. |
| Need NFS/SMB with specialized enterprise storage capabilities. | **FSx for NetApp ONTAP** or suitable variant. | Protocol support and specific enterprise features. |
| Temporary data near compute with durable source of truth. | **EBS/EFS/FSx combined with S3**. | Separate working space from the object source of truth. |

Running a self-managed database on EBS is not always optimal. **Amazon RDS/Aurora** can offload database administration, backups, and certain HA tasks when aligned with requirements. This lesson compares storage interfaces; choosing a managed database is a related architectural decision.

### 6.2. Decision Tree

~~~mermaid
flowchart TD
    A["Workload needs data storage"] --> B{"Needs POSIX/Windows filesystem and paths?"}
    B -->|"No, app uses object API"| S3["Evaluate Amazon S3"]
    B -->|"Yes"| C{"One or multiple clients sharing namespace?"}
    C -->|"One client / disk for EC2"| EBS["Evaluate Amazon EBS"]
    C -->|"Multiple clients"| D{"Protocol and workload?"}
    D -->|"Standard Linux NFS"| EFS["Evaluate Amazon EFS"]
    D -->|"Windows SMB / HPC / ONTAP / OpenZFS"| FSX["Evaluate Amazon FSx"]
    S3 --> V["Check performance, AZ, backup, security, total cost"]
    EBS --> V
    EFS --> V
    FSX --> V
~~~

When software needs both a **POSIX filesystem** for temporary processing and **object storage** for long-term data, the right solution often combines both models.

## 7. Example Architecture: Document Processing Application

Suppose an application receives images/PDFs, processes files, and returns results, serving traffic across multiple AZs:

- **ALB** distributes requests to two EC2 instances in two AZs.
- Each EC2 instance has **EBS** for its root volume and local temporary files.
- Both EC2 instances mount **EFS Regional** if the workflow truly needs a shared processing path.
- Original uploads and results are placed in **S3** via SDK.
- **Lambda** can process S3 events in an integrated architecture; transaction metadata is stored in an appropriate database.

~~~mermaid
flowchart TB
    U["User"] -->|"HTTPS"| ALB["Application Load Balancer"]
    subgraph AZ1["AZ A"]
      A["EC2 App A"]
      VA[("EBS A")]
      A --- VA
    end
    subgraph AZ2["AZ B"]
      B["EC2 App B"]
      VB[("EBS B")]
      B --- VB
    end
    ALB --> A
    ALB --> B
    EFS[("EFS Regional — shared workspace")]
    S3[("S3 — originals/results")]
    A <-->|"NFS"| EFS
    B <-->|"NFS"| EFS
    A <-->|"S3 API"| S3
    B <-->|"S3 API"| S3
    S3 -->|"S3 event when configured"| L["Lambda processor"]
~~~

This diagram shows the **logical** flow and omits full VPCs, subnets, mount targets, routes, endpoints, Security Groups, IAM, databases, health checks, or recovery mechanisms. High availability must be **validated through design and failover testing**, not assumed just because two EC2 instances exist.

| Data category | Storage location | Reason |
| --- | --- | --- |
| EC2 operating system | Dedicated EBS per instance. | Boot and OS filesystem management. |
| Local temporary cache | EBS or instance store depending on data loss tolerance. | Avoid pushing short-lived data over the network unnecessarily. |
| Workspace shared by multiple workers | EFS Regional. | Shared NFS namespace. |
| Long-term originals and results | S3. | Object API, lifecycle, and event integration. |
| Business transactions and metadata | RDS/Aurora or suitable database. | Queries/transactions; do not replace a DB with file/object storage merely because it can store data. |

### 7.1. Processing Flow

1. User uploads a document; app authenticates/authorizes and validates file size/type.
2. App writes temporarily to EBS or EFS depending on synchronization needs with other workers.
3. App stores the original in S3 under a managed object key with least-privilege IAM permissions.
4. System records metadata in the database and emits processing events/orchestration as appropriate.
5. Worker writes output to S3; app returns a URL or retrieves content via access-controlled mechanisms.

**If EC2 in AZ A is replaced**, EC2 in AZ B will not automatically have data written **only to EBS A**. Ensure critical data is placed in a shared filesystem, S3, or an appropriately resilient datastore.

## 8. Performance: Do Not Compare Using a Single Number

### 8.1. IOPS, Throughput, Latency, and Concurrency

| Dimension | Question |
| --- | --- |
| **IOPS** | How many small I/Os per second? |
| **Throughput** | How many MiB/s need to be processed? |
| **Latency** | How long does each operation take, especially tail latency? |
| **Concurrency** | How many simultaneous clients/requests? |
| **Operation pattern** | Random reads/writes, sequential, many small files, or large objects? |

Examples:

- Databases on EC2 typically care about EBS IOPS/latency and EC2 bandwidth limits.
- EFS/FSx must account for metadata operations, throughput mode/provisioning, and network latency.
- S3 workloads uploading large files can optimize with multipart upload and concurrency; many small objects can generate high request volume and cost.
- Cross-AZ/cross-Region access can impact latency and data transfer costs.

### 8.2. Why May S3 Be Unsuitable for Random Writes?

Filesystems on block/file storage allow applications to open a file and modify part of the data at an offset. S3 primarily provides **object** APIs, so updating content typically involves uploading/overwriting the object or using supported API mechanisms. Byte-range GET only reads a slice of an object; it does not turn S3 into a POSIX-writable block volume.

Certain specialized S3 features or storage classes add specific behaviors, but you should not rely on exceptions to assume S3 is compatible with every filesystem workload.

### 8.3. Filesystems Have Limits Too

EFS/FSx does not guarantee business-level consistency across multi-machine applications automatically. File locking, caching, metadata, POSIX/Windows semantics, and concurrent write rules must be properly designed in the application. Two processes modifying the same file without coordination can still corrupt data at the business logic level.

## 9. Availability, Durability, and Recovery

Three distinct concepts:

- **Availability:** can the system read/write data when needed?
- **Durability:** how well is written data protected against designed service/infrastructure failures?
- **Recoverability:** can the right version of data be restored after accidental deletion, bad overwrites, or major incidents within target objectives?

### 9.1. EBS: AZ-Scoped, Backed Up via Snapshots

An EBS volume exists in a single AZ with service-level redundancy inside that AZ. To protect against data loss from logic errors or major failures, **snapshots**/backups and recovery designs are required. Snapshots enable creating new volumes in another AZ, but do not automatically fail over a live running database.

If a snapshot is taken while a database is actively writing, evaluate whether the system requires **crash consistency** or **application consistency**.

### 9.2. EFS and FSx

**EFS Regional** is designed to store data across multiple AZs; **EFS One Zone** is a single-AZ option. Backup, lifecycle, and replication must be configured per requirements and filesystem type.

FSx provides single-AZ/multi-AZ/backup options varying across **Windows, Lustre, ONTAP, OpenZFS** and the chosen deployment. When HA is required, verify the exact variant. Do not assume "using FSx" automatically includes multi-AZ failover.

### 9.3. S3: Classes, Versioning, Replication, and Object Lock

- **S3 Standard** is designed to store objects across multiple AZs.
- Some storage classes like **One Zone-IA** or **Express One Zone** have single-AZ characteristics.
- **Versioning** retains object versions according to configuration.
- **Replication** copies objects per selected rules/buckets/Regions; scope and replication latency must be understood.
- **S3 Object Lock** supports retention/WORM where appropriate, requiring exact configuration and permissions.
- **Lifecycle** manages class transitions and expiration; misconfigured policies can cause unintended data loss.

Having versioning/replication **does not automatically replace independent backups and restore testing**; valid deletes/overwrites, overly broad permissions, or application bugs can still compromise data relative to business requirements.

### 9.4. RPO and RTO

- **RPO (Recovery Point Objective)**: maximum acceptable data loss, typically expressed in time.
- **RTO (Recovery Time Objective)**: maximum acceptable recovery duration.

For example, suppose a requirement specifies a **15-minute** RPO and **1-hour** RTO. Taking an EBS snapshot **once per day** is not enough to prove a 15-minute RPO. You must select appropriate backup/replication strategies and **rehearse recovery** to measure actual RPO/RTO.

Do not confuse **service-designed data durability** with the ability to recover from every user or application error.

## 10. Security by Storage Model

### 10.1. EBS

- **IAM** controls actions to create/attach/detach/snapshot/copy/share volumes via AWS permissions.
- **OS filesystem permissions** and the application determine which users/processes can read data once EC2 uses the volume.
- **EBS encryption** uses AWS KMS as configured; check encryption by default where required.
- Protect snapshots and KMS permissions, because snapshots can contain sensitive data.

An EBS volume is not an NFS server requiring inbound TCP/2049 on a volume SG. SGs protect EC2 network traffic; EBS operates at a separate block layer.

### 10.2. EFS

For a client to mount EFS, the following are typically required simultaneously:

1. An appropriate **mount target** in the VPC with working DNS/routing.
2. Mount target **Security Group** allowing TCP/**2049** from authorized clients, plus matching outbound/NACL rules.
3. OS with an NFS client or EFS mount helper.
4. Appropriate **POSIX UID/GID/mode** permissions or an EFS Access Point.
5. When using **IAM authorization**, policies granting permissions such as **elasticfilesystem:ClientMount** and **ClientWrite** if needed; configure TLS and the EFS mount helper per documentation.

Mount timeouts typically point to network/mount target issues. Permission denied errors may relate to POSIX permissions, IAM policies, or mount options. Never open TCP/2049 to the Internet just to troubleshoot errors.

### 10.3. FSx

Security mechanisms depend on the variant:

- **FSx Windows:** SMB, Active Directory, NTFS/SMB share ACLs, and Security Groups.
- **FSx Lustre:** permissions/mounts/compute clients per Lustre mechanisms.
- **FSx ONTAP/OpenZFS:** NFS/SMB/iSCSI, export/share permissions, and relevant connectivity constraints.

IAM manages AWS resources, but usually **does not replace protocol-level file/user permissions**.

### 10.4. S3

- **IAM identity policies**, **bucket policies**, S3 Access Point policies (if used), and other constraints govern API access.
- **Block Public Access** helps prevent unintended public exposure; check both account and bucket levels.
- **SSE-S3** is applied by default by S3 for new objects; if SSE-KMS is needed, manage key policies/KMS permissions accordingly.
- **S3 Object Ownership**, versioning, presigned URLs, and lifecycle rules must align with permissions, data sensitivity, and retention requirements.
- **HTTPS/TLS** protects data in transit; VPC endpoints/endpoint policies can participate in private access architectures.

Distinguish the ARNs:

~~~text
Bucket ARN: arn:aws:s3:::example-private-reports
Object ARN: arn:aws:s3:::example-private-reports/reports/*
~~~

**s3:ListBucket** operates at the bucket level, whereas **s3:GetObject** typically requires an object-level ARN. When objects are encrypted with KMS, S3 permissions alone may not suffice; **kms:Decrypt** and appropriate key policy permissions may also be required.

### 10.5. Logging and Shared Responsibility

AWS operates the storage infrastructure, but customers decide access controls, backup configurations, logging, and recoverability. Depending on needs:

- EBS: monitor volume metrics, snapshot policies, CloudTrail API calls, and OS/DB logs.
- EFS/FSx: filesystem metrics, client/mount errors, service-specific auditing, and app logs.
- S3: CloudTrail **data events** when configured, access logging/metrics/CloudWatch, and app logs.

Do not equate a service **having logging capability** with logging actually being enabled and complete.

## 11. Cost: Total Cost Depends on Access Patterns

| Type | Cost components to evaluate | Common pitfalls |
| --- | --- | --- |
| **EBS** | **Provisioned** GB, IOPS/throughput per volume type, snapshots, data transfer, and other applicable operations. | Provisioning more capacity than used still incurs volume charges. |
| **EFS** | Stored GB per class, throughput mode, requests/access, backups, and configuration-dependent fees. | Comparing only per-GB prices while ignoring throughput, class, and access patterns. |
| **FSx** | Capacity, throughput capacity, IOPS, backups, deployment type, and variant-specific fees. | Using pricing from one FSx variant to estimate another. |
| **S3** | Storage class, PUT/GET/LIST requests, retrieval, transfer, replication, lifecycle transitions, logging. | Low-cost storage class becoming expensive due to retrieval/early deletion/requests/egress for actual access patterns. |

For example, a **100 GiB provisioned** EBS volume can be billed for 100 GiB even if the filesystem currently stores only 15 GiB of data. Conversely, moving everything to S3 solely for low storage-per-GB pricing can raise costs if the application performs frequent reads/writes and requires a filesystem translation layer.

Before choosing, gather:

1. Current capacity, growth forecast, and retention.
2. Client count, I/O rate, object/file size, and concurrency.
3. Required latency/IOPS/throughput targets.
4. RPO/RTO, AZ/Region scope, backup, and recovery requirements.
5. Data paths, egress, cross-AZ/cross-Region traffic, NAT/VPC endpoints.
6. Encryption, KMS, audit logging, and data retention regulations.

For estimates, use official AWS pricing tables and the Pricing Calculator for the **Region, storage class, and current configuration**; never treat one per-GB rate as universal across environments.

## 12. Read-Only AWS CLI Examples

The commands below **do not create, format, write, delete, or mount resources**. They require a configured AWS CLI and a principal with read permissions. IDs and buckets are examples; replace them with values from an environment you are authorized to access.

### 12.1. Identify Caller Identity and Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

For EBS/EFS/FSx, setting the right Region in the CLI is critical. S3 buckets have their own Regions that should be verified upon access.

### 12.2. EBS

~~~bash
aws ec2 describe-volumes \
  --region ap-southeast-1 \
  --query "Volumes[].{Volume:VolumeId,AZ:AvailabilityZone,Type:VolumeType,SizeGiB:Size,Iops:Iops,Throughput:Throughput,State:State}"

aws ec2 describe-volumes \
  --filters Name=attachment.instance-id,Values=i-0123456789abcdef0 \
  --region ap-southeast-1

aws ec2 describe-snapshots \
  --owner-ids self \
  --region ap-southeast-1 \
  --query "Snapshots[].{Snapshot:SnapshotId,Volume:VolumeId,Time:StartTime,State:State}"
~~~

Check **AvailabilityZone**, volume type, IOPS, throughput, snapshot timestamps, and attachment states. Snapshot lists can be very long; in large environments use appropriate filters/pagination.

### 12.3. EFS

~~~bash
aws efs describe-file-systems \
  --region ap-southeast-1

aws efs describe-mount-targets \
  --file-system-id fs-0123456789abcdef0 \
  --region ap-southeast-1

aws efs describe-mount-target-security-groups \
  --mount-target-id fsmt-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Inspect **LifeCycleState**, performance/throughput settings, mount target AZ/subnet/IP, and Security Groups; check resource backup/lifecycle policies separately if needed.

### 12.4. FSx

~~~bash
aws fsx describe-file-systems \
  --region ap-southeast-1 \
  --query "FileSystems[].{Id:FileSystemId,Type:FileSystemType,StorageGiB:StorageCapacity,State:Lifecycle}"
~~~

To inspect deployment type, endpoints, throughput, or security settings for a specific variant, run `describe-file-systems` with full output and match it to that exact filesystem; do not assume all FSx systems share the same attributes.

### 12.5. S3

~~~bash
aws s3api list-buckets --query "Buckets[].Name"

aws s3api get-bucket-location \
  --bucket example-private-reports

aws s3api get-public-access-block \
  --bucket example-private-reports

aws s3api get-bucket-versioning \
  --bucket example-private-reports

aws s3api get-bucket-encryption \
  --bucket example-private-reports

aws s3api list-objects-v2 \
  --bucket example-private-reports \
  --prefix reports/2026/ \
  --max-items 10
~~~

If you receive **AccessDenied**, do not assume the bucket does not exist. If Block Public Access is unconfigured or a command does not return the expected output, review actual policies and permissions; do not treat that alone as proof of security.

### 12.6. Linux EC2: Inspect Filesystems Without Modifying Data

~~~bash
lsblk -f
findmnt
df -hT
mount | grep -E "nfs|efs|xfs|ext4"
~~~

EBS volumes may appear under NVMe device names rather than the device name specified during attachment. An NFS mount could be EFS or another NFS server, so verify the source, mount options, and related configuration before drawing conclusions.

## 13. Layered Troubleshooting

### 13.1. EC2 Cannot See an EBS Volume

Verify whether the EBS volume and EC2 instance are in the **same AZ**, check attachment status, NVMe naming in the OS, existing partitions/filesystems, and permissions/KMS where applicable. **Do not reformat/reinitialize a filesystem on a volume containing data you need to keep.**

### 13.2. EFS Mount Fails

- **Timeout:** check DNS, mount targets, Security Group TCP/2049, NACLs/routes, and client network status.
- **Permission denied:** inspect POSIX UID/GID, directory mode, EFS Access Point, IAM authorization/resource policy, and mount options.
- **Slow performance:** inspect metadata workload, NFS caching, client network, throughput mode, and operation volume.

Do not open NFS SG to 0.0.0.0/0 as a "quick fix" without identifying the client source and root cause.

### 13.3. FSx Connection Fails

Troubleshoot according to the active protocol: Windows requires DNS/Active Directory/SMB/NTFS permissions; Lustre requires client/mount and HPC path verification; ONTAP/OpenZFS require checking NFS/SMB/iSCSI, export policies, and networking. Avoid applying one FSx variant's troubleshooting guide to another variant.

### 13.4. S3 Returns AccessDenied

1. Verify the actual principal with **aws sts get-caller-identity** in the application environment.
2. Check the action and exact bucket/object ARN.
3. Review identity-based policies, bucket/resource policies, Block Public Access, SCPs/permission boundaries, and conditions.
4. For SSE-KMS, check KMS key policies/permissions.
5. If a policy requires a VPC endpoint, verify requests route through that endpoint.
6. For presigned URLs, verify expiration, HTTP method, request headers, and the signer's permissions.

HTTP **403 AccessDenied** is typically a permissions/condition issue evaluated after the request reaches the endpoint, unlike a network **timeout**.

### 13.5. Unexpected Spike in S3 Costs

Inspect object sizes, PUT/GET/LIST counts, storage class selection, retrieval/early deletion charges, data transfer, replication, and logging. A bucket with many small objects and high request counts can have a very different cost profile than a bucket with fewer large objects totaling the same GB.

## 14. Misconceptions to Avoid

| Misconception | Correct understanding |
| --- | --- |
| "Block storage cannot store files." | The OS usually creates a filesystem on top of a block device to store files. |
| "EBS is a shared filesystem for EC2 across multiple AZs." | An EBS volume belongs to one AZ; Multi-Attach has strict conditions within the same AZ and requires higher-layer coordination. |
| "EFS is just like an EBS block device." | EFS provides an NFS filesystem; clients mount it over the network. |
| "EFS is an SMB share for Windows." | EFS is NFS; Windows SMB usually uses FSx for Windows File Server. |
| "All FSx services use the same protocol." | FSx includes Windows, Lustre, ONTAP, and OpenZFS with different protocols and features. |
| "An S3 key with / is a POSIX directory." | Prefixes/keys do not provide full POSIX semantics. |
| "With an S3 mount tool, S3 can replace EBS for databases." | Mount adapters do not guarantee the block/random write/locking semantics databases require. |
| "S3 always spans multiple AZs." | Some storage classes are One Zone. |
| "Having snapshots means RPO/RTO targets are met." | Backup frequency, consistency, restore plans, and testing are still required. |
| "IAM Allow is enough to mount EFS." | NFS TCP/2049, POSIX, mount targets, TLS, and networking still matter. |
| "S3 server-side encryption is enough security." | IAM/bucket policies, KMS, access paths, versioning, auditing, and application security also matter. |
| "Lowest cost per GB is always cheapest overall." | Total cost also depends on IOPS, requests, retrieval, data transfer, backups, and retention duration. |

## 15. Practice Scenarios and Solutions

### Scenario A — Avatars on an Auto Scaling Website

**Context:** A website runs multiple EC2 instances across two AZs; user images must be available to every instance.

**Solution:** If the application handles images via SDK/API, **S3** is ideal for original objects, optionally paired with CloudFront. If existing software strictly requires sharing the same filesystem path over NFS, consider **EFS Regional**. Do not use a single instance's local EBS as the sole location for important images.

### Scenario B — Database on EC2

**Context:** Self-managed MySQL requiring transactional reads/writes and logs with low latency.

**Solution:** Evaluate **EBS SSD** based on IOPS/latency and EC2 bandwidth; implement database backup/HA mechanisms. To reduce management overhead and gain managed features where suitable, compare with **Amazon RDS**. Do not point `datadir` directly at the S3 object API.

### Scenario C — Windows File Server for Accounting Team

**Context:** Application requires SMB, Windows ACLs, and Active Directory.

**Solution:** **FSx for Windows File Server** is the appropriate candidate. Verify networking, AD/SMB permissions, HA options, backups, throughput, and cost. EFS NFS does not directly replace a Windows share.

### Scenario D — Multi-Year Audit File Retention

**Context:** Logs and PDFs stored long term, rarely read, requiring protection against accidental deletion.

**Solution:** **S3** with an appropriate storage class/lifecycle; evaluate Object Lock/retention where required, versioning, bucket permissions, and retrieval/minimum storage duration fees. Plan restore testing if data integrity must be proven.

### Scenario E — Losing an Availability Zone

**Context:** Application with one EC2 instance and one EBS volume in AZ A; target RPO 15 minutes, RTO 1 hour.

**Solution:** A single-AZ EBS volume cannot meet targets if that AZ becomes unavailable. You need sufficiently frequent replication/backups, the ability to create volumes/launch instances in another AZ, consistent database recovery, and real-world duration testing. Depending on the data, EFS Regional or S3 can decouple critical data from a single EC2 instance, though recovery still must be designed.

## 16. Self-Check Questions

**Question 1.** How does block storage differ from object storage?  
**Answer:** Block storage provides blocks/devices for the OS or application to handle I/O, whereas object storage is accessed via buckets/keys and APIs without default POSIX filesystem semantics.

**Question 2.** Can one EBS volume be attached as a shared drive to EC2 instances in two different AZs?  
**Answer:** No. An EBS volume belongs to one AZ; Multi-Attach has specific conditions within the same AZ and requires synchronization management at a higher layer.

**Question 3.** Which service should be evaluated when two Linux EC2 instances in two AZs need to read/write a shared directory?  
**Answer:** Amazon EFS Regional with mount targets, NFS, and appropriate permissions.

**Question 4.** Which service should be evaluated for a Windows application requiring SMB and AD?  
**Answer:** Amazon FSx for Windows File Server.

**Question 5.** Does an S3 key **photos/2026/a.jpg** create a POSIX directory like Linux?  
**Answer:** No. That is an object key; `/` acts as a prefix/naming delimiter within the object namespace.

**Question 6.** Why can't we conclude that all S3 storage classes are multi-AZ?  
**Answer:** Some storage classes are designed for a single AZ, so availability, durability, and recovery must be evaluated per class.

**Question 7.** Do an EFS mount timeout and an EFS permission denied error have the same root cause?  
**Answer:** Not necessarily. Timeouts usually relate to DNS/network/SG/NFS; permission denied usually relates to POSIX/IAM/resource policy or mount options.

**Question 8.** An SSE-KMS object returns S3 GetObject 403 even though the user has GetObject permission—what should be checked?  
**Answer:** The KMS key policy and key usage permissions such as `kms:Decrypt`, along with related policies/conditions.

**Question 9.** Does taking an EBS snapshot once per day prove a 10-minute RPO?  
**Answer:** No. You need an appropriate backup/replication strategy and restore testing to prove the objective.

**Question 10.** Why might an application use EBS, EFS, and S3 at the same time?  
**Answer:** EBS serves per-instance boot/block data, EFS shares a filesystem across workloads, and S3 stores objects for APIs, backups, and long-term retention.

## 17. Key Takeaways

Choose storage based on **how the application interacts with data** first, then optimize capacity and cost:

- **EBS / block:** drives for EC2 and workloads needing block I/O; manage the filesystem in the OS, pay attention to AZ, IOPS/throughput, and snapshots.
- **EFS/FSx / file:** filesystems with paths and file permissions; choose EFS for standard Linux NFS, FSx for specialized protocols/features; pay attention to mount networking, metadata performance, POSIX/Windows permissions, and HA deployment.
- **S3 / object:** bucket/key/API; ideal for images, documents, logs, backups, data lakes, lifecycle; pay attention to storage classes, requests, IAM/bucket policies, versioning, and retrieval.

Before deciding, verify the **access interface**, **number of clients/AZs**, **IOPS/throughput/latency performance**, **RPO/RTO targets**, **permissions/encryption**, and **total lifecycle cost**. This is the foundation for choosing the right AWS service, reducing data risk, and operating a resilient system.

### AWS Reference Documentation

- [Amazon EBS User Guide](https://docs.aws.amazon.com/ebs/latest/userguide/what-is-ebs.html) — EBS volumes and snapshots.
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html) — performance considerations by volume type.
- [Amazon EBS Multi-Attach](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes-multi.html) — conditions and limitations for sharing block volumes.
- [Amazon EFS User Guide](https://docs.aws.amazon.com/efs/latest/ug/whatisefs.html) — NFS, mount targets, storage classes, and access permissions.
- [Amazon FSx documentation](https://docs.aws.amazon.com/fsx/) — Windows, Lustre, ONTAP, and OpenZFS filesystems.
- [Amazon S3 User Guide](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html) — object storage and buckets.
- [Amazon S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html) — choosing classes by access pattern.
- [AWS Backup documentation](https://docs.aws.amazon.com/aws-backup/latest/devguide/whatisbackup.html) — backup options by resource.
