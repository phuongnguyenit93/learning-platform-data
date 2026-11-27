# AWS Storage Gateway and On-Premises Storage Integration

Many enterprises still operate data center applications, Windows/Linux servers, backup systems, and file workflows that have existed for years. Moving every application to the cloud at once can be costly or impractical due to latency, specialized hardware, regulatory requirements, legacy software, and operational dependencies. Businesses need a way for on-premises applications to keep using familiar storage protocols while storing data on AWS for capacity scale, long-term retention, or disaster recovery.

**AWS Storage Gateway** is a hybrid storage service combining AWS cloud storage with a gateway appliance running on-premises or on Amazon EC2. The gateway presents familiar storage interfaces to applications while connecting data to AWS storage services. Depending on the gateway type, applications access files over NFS/SMB, block volumes over iSCSI, or virtual tape libraries over iSCSI.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, Storage Gateway integrates on-premises systems with Amazon S3, Amazon FSx, Amazon EBS snapshots, and archive services. The module aims to help you select, design, and deploy applications safely with observability, recoverability, and cost control. Therefore, understand exact gateway types, data flows, caching, networking, IAM, encryption, backups, and consistency boundaries before going to production.

## 1. What Problem Does Storage Gateway Solve?

Storage Gateway fits when on-premises applications must keep using existing storage protocols or workflows while the business leverages AWS storage backends.

Common scenarios include:

- Linux applications needing to mount an NFS share while storing files in Amazon S3.
- Windows applications needing SMB shares, Active Directory, and file permissions compatible with existing systems.
- Legacy applications requiring an iSCSI block device while storing primary data or snapshots in AWS.
- Existing backup software needing to write to a virtual tape library instead of physical tapes.
- Maintaining off-site data copies for backup and disaster recovery.
- Teams needing access to Windows file shares on Amazon FSx over hybrid connectivity.

Storage Gateway is not a universal replacement for every storage type. If an application can call S3 APIs directly, or access Amazon EFS or Amazon FSx over the network, you may not need a gateway. If the goal is scheduled bulk data transfer, AWS DataSync may be a better fit. Start from application protocols, data semantics, and latency requirements.

## 2. Types of Storage Gateway

Storage Gateway provides four primary gateway types commonly used in hybrid architectures:

| Type | Application Interface | AWS Backend | Use Case |
|---|---|---|---|
| S3 File Gateway | NFS or SMB | Amazon S3 | On-premises file shares storing files as S3 objects |
| FSx File Gateway | SMB | Amazon FSx for Windows File Server | Low-latency access from on-premises clients to AWS Windows file shares |
| Volume Gateway | iSCSI block volumes | Amazon S3 and EBS snapshots | Applications needing block storage or volume backups |
| Tape Gateway | iSCSI virtual tape library | Amazon S3 and S3 Glacier Flexible Retrieval / Deep Archive | Integrating backup software using tape workflows |

Do not treat the four types as interchangeable configurations. S3 File Gateway maps files to objects; FSx File Gateway maps SMB shares to a Windows file system; Volume Gateway presents block devices; Tape Gateway emulates a tape library and archiving workflow. Each has distinct storage, recovery, and cost behavior.

## 3. High-Level Architecture

The gateway appliance runs on an on-premises host or hypervisor, accepts application requests over the appropriate protocol, and exchanges data with the Storage Gateway service over network links to AWS.

~~~mermaid
flowchart LR
    subgraph OnPrem["On-premises data center"]
      A[Applications and servers]
      B[Storage Gateway appliance]
      C[Cache / Upload buffer / Local disks]
      A --> B
      B <--> C
    end
    subgraph AWS["AWS Region"]
      D[Storage Gateway service]
      E[S3 / FSx / EBS snapshots / Glacier]
      D --> E
    end
    B <-->|Encrypted connection| D
~~~

The gateway appliance is not a standalone storage backend. It exposes interfaces to applications and manages caches, buffers, or data streams per gateway type. Durable data ultimately resides in the corresponding AWS service.

### Role of Cache and Upload Buffer

- **Cache storage** holds frequently accessed data to reduce latency and WAN reads. Cache usage differs between File Gateway and Volume Gateway.
- **Upload buffer** serves as a staging area for data queued for upload to AWS in gateway types that use it. Size it to handle write rates and network outage durations.
- **Local storage** serves as primary data storage for Stored Volume Gateway; never confuse it with the cache of Cached Volume Gateway.

When sizing, separate primary dataset capacity, working set, write rate, bandwidth, and potential WAN outage durations. Undersizing disks based solely on current data volume can exhaust buffers during slow uploads.

## 4. Where Is the Gateway Deployed?

Storage Gateway can run as a virtual appliance on-premises or on Amazon EC2 depending on gateway type and support conditions. Supported virtualization platforms per current documentation include VMware ESXi, Microsoft Hyper-V, Linux KVM, and other supported environments by published version.

On EC2, Storage Gateway supports S3 File Gateway, Cached Volume Gateway, and Tape Gateway per service terms. Stored Volume Gateway is not supported on EC2 because that mode requires storing all primary data on local on-premises disks.

Before deploying, check:

- Hypervisor version, host OS, and CPU/RAM requirements.
- UEFI/boot requirements and VM configuration per current images.
- Capacity, type, and performance of local disks.
- NICs, network paths, DNS, NTP, and firewalls.
- Connectivity to Storage Gateway service endpoints and AWS backends.
- Host, hypervisor, and power redundancy on-premises.
- Gateway, volume, tape, or file share quotas per Region.

### Note on the Hardware Appliance

AWS discontinued new orders of the Storage Gateway Hardware Appliance on May 12, 2025. Existing appliance customers can continue using and receiving support through May 2028 per AWS announcements. For new deployments today, prioritize VM appliances or EC2 matching the gateway type and infrastructure needs.

Never create a gateway VM by cloning or restoring a hypervisor snapshot/AMI of another gateway VM. If a gateway VM suffers an unrecoverable failure, deploy and activate a fresh gateway and recover data using the gateway-specific recovery workflow.

## 5. What Is S3 File Gateway?

S3 File Gateway provides an NFS or SMB file interface for on-premises applications while storing data as objects in Amazon S3. Applications mount file shares and read/write files over familiar protocols without integrating the S3 API.

S3 File Gateway fits:

- File shares shared between on-premises apps and cloud workflows.
- Content, media, documents, and file exports.
- Application data requiring file-protocol access.
- Moving file data into S3 for lifecycle management, replication, and analytics.

### Write and Read Flows

When a client writes a file over NFS/SMB, the gateway writes to local cache first and uploads file data and metadata to S3 asynchronously. On reads, the gateway serves from cache if present; otherwise it fetches from S3 via read-through.

~~~mermaid
flowchart TD
    A[NFS / SMB client] --> B[S3 File Gateway]
    B --> C{File in local cache?}
    C -->|Yes| D[Read from cache]
    C -->|No| E[Read object from S3]
    E --> F[Update cache]
    B --> G[Receive file write]
    G --> H[Write to local cache]
    H --> I[Upload data and metadata asynchronously]
    I --> J[Amazon S3 object]
~~~

Key takeaway: when an application receives write acknowledgment from the gateway, data is written to local cache; the S3 upload may still be in progress. If a workflow requires data to be durable in S3 before proceeding, use upload notifications or sync status checks.

## 6. NFS and SMB on S3 File Gateway

S3 File Gateway supports both NFS and SMB. Pick the protocol matching your OS, authentication model, and applications.

| Criterion | NFS | SMB |
|---|---|---|
| Typical clients | Linux/Unix | Windows and SMB-capable applications |
| Common versions | NFSv3, NFSv4.1 | SMBv2, SMBv3 |
| Authentication | IP/network-based client access and Unix metadata permissions | Can integrate with Microsoft Active Directory |
| File permissions | UID/GID and Unix permissions/metadata | Windows ACLs and owner/permission descriptors |
| Use cases | Linux apps, batch, rendering, and file processing | Windows file shares, home directories, Windows apps |

With SMB, you can configure Active Directory, allowed user/group lists, optional guest access, and audit logs. With NFS, restrict allowed client CIDRs/IPs, configure squashing, and set appropriate default metadata.

Never expose SMB/NFS to the entire network when only a specific group of servers needs access. Use network segmentation and file share access policies to restrict sources.

## 7. S3 Objects and File Semantics

S3 is object storage, not a POSIX file system or block device. S3 File Gateway presents a file interface, yet the backend remains objects. Understand these differences:

- Directories map to key prefixes and metadata objects.
- Renames, appends, truncations, or metadata updates can trigger new object operations or re-uploads.
- Objects written directly to the bucket by another client do not automatically appear in the gateway's cache right away.
- Versioning may retain multiple versions when files or metadata are modified.
- Applications relying on strict file locking, atomic renames, or specialized POSIX semantics require compatibility testing.

With S3 Versioning enabled, a single file write can produce one version for object data and another version when the gateway updates metadata. Edits or ownership/metadata changes multiply versions. Track noncurrent versions and configure S3 Lifecycle rules carefully; avoid overly short expirations if recovery or auditing is required.

Avoid having multiple independent systems modify the same objects concurrently via S3 APIs and file shares without clear synchronization rules. AWS recommends avoiding direct object writes into buckets managed by S3 File Gateway via out-of-band workflows.

### Cache Refresh

If another client or service adds, deletes, or overwrites objects directly in the bucket, the file share may still display a cached inventory. Use `RefreshCache` to update the file share's inventory.

`RefreshCache` does not download every object into local cache; it refreshes the gateway's object listing. A successful API response only initiates the refresh, without guaranteeing completion. Wait for refresh-completion notifications before workflows depend on newly added files.

Example:

~~~bash
aws storagegateway refresh-cache \
  --file-share-arn "arn:aws:storagegateway:ap-southeast-1:111122223333:share/share-EXAMPLE"
~~~

Refreshing an entire bucket or huge prefix consumes API requests, gateway resources, and time. Refresh only the needed scope and avoid triggering refreshes per object during bulk uploads.

## 8. What Is FSx File Gateway?

FSx File Gateway provides low-latency SMB access from on-premises clients to file shares stored on Amazon FSx for Windows File Server. It uses a local cache to cut latency and reduce WAN reads while keeping the managed Windows file system in AWS.

Key distinction:

- S3 File Gateway maps file shares to S3 objects.
- FSx File Gateway maps on-premises file shares to SMB shares on FSx for Windows File Server.

FSx File Gateway suits Windows applications needing SMB, Active Directory, Windows ACLs, and native Windows filesystem semantics. It is not meant for turning an S3 bucket into a Windows file server.

### Dependencies

Using FSx File Gateway requires an FSx for Windows File Server file system and network connectivity from the gateway to FSx—typically AWS Direct Connect or Site-to-Site VPN. The gateway must join the configured Active Directory domain and link to the FSx file system.

On-premises clients connect via SMB to the gateway. The gateway communicates with FSx inside the VPC over the established hybrid link. Factor in DNS, AD domain controllers, Kerberos, SMB, and required RPC ports per port requirements documentation.

### Access Flow

~~~mermaid
flowchart LR
    A[On-premises Windows client] -->|SMB| B[FSx File Gateway]
    B <--> C[Local cache]
    B -->|VPN / Direct Connect| D[Amazon FSx for Windows File Server]
    D --> E[Windows file system]
    B --- F[Active Directory]
~~~

FSx File Gateway delivers low-latency access to frequently used working sets, though overall performance depends on cache hits, WAN bandwidth, latency, and FSx throughput capacity. Test file locking, AD permissions, and failover behavior with real applications.

## 9. What Is Volume Gateway?

Volume Gateway provides block storage over iSCSI targets so on-premises applications see standard disks. Data integrates with Amazon S3 and can be protected via snapshots stored as Amazon EBS snapshots.

Volume Gateway has two configurations:

- **Cached volumes:** Amazon S3 is the primary data store; the gateway keeps frequently accessed data in local cache.
- **Stored volumes:** the entire dataset resides locally on local disks; the gateway asynchronously uploads snapshots to AWS for off-site backups.

Both modes differ in data layout and local storage requirements. Choose based on whether you need the entire dataset stored locally or want S3 as primary storage.

## 10. Cached Volumes vs. Stored Volumes

| Criterion | Cached Volumes | Stored Volumes |
|---|---|---|
| Primary data location | Amazon S3 | On-premises local disks |
| Local cache | Retains hot data | Not used in cached-volume sense |
| Upload buffer | Yes | Yes |
| Client protocol | iSCSI | iSCSI |
| AWS backups | EBS snapshots | EBS snapshots |
| Best suited for | Reducing on-premises storage footprint when working set is smaller than total dataset | Low-latency access to the entire dataset plus off-site backups |
| WAN dependence | Higher for cache misses and uploads | Primarily for snapshot uploads and management |

### Cached Volumes

Applications write to an iSCSI volume. The gateway stages writes in the upload buffer and uploads them to S3, while caching recently accessed blocks locally. Working sets enjoy fast local access, whereas cache misses fetch blocks from AWS over the network.

### Stored Volumes

Applications write to local disks attached to the gateway. The gateway takes scheduled or on-demand snapshots and uploads changed blocks to AWS. This preserves local performance for the entire dataset, but demands full local disk capacity and local disk protection.

### Selection Examples

A video processing workload with a massive archive and a small hot working set fits cached volumes. A legacy database requiring low local latency across the entire block dataset might evaluate stored volumes, subject to verifying database, iSCSI, and consistency requirements.

## 11. iSCSI and Application Integration

Volume Gateway exposes iSCSI targets to application servers. On-premises hosts configure an iSCSI initiator, connect to the target, and receive a block device. The OS then partitions and formats a filesystem as required by the application.

Design considerations:

- Ensure stable LAN connectivity between iSCSI initiators and targets.
- Restrict network ACLs/firewalls strictly to approved initiators.
- Enable multipathing where supported by architecture and gateway for resilience.
- Monitor sessions, latency, throughput, and queue depth.
- Never mount the same volume read-write from multiple hosts unless the application/filesystem provides cluster coordination.
- Follow clean shutdown and volume detach procedures.

Volume Gateway serves apps needing block devices without turning legacy workloads into cloud-native systems. Test database consistency, filesystem recovery, and behavior during gateway disconnects.

## 12. Snapshots and AWS Backup for Volume Gateway

Volume Gateway supports on-demand and scheduled snapshots. Snapshots are stored as Amazon EBS snapshots in AWS and capture incremental changes since the prior snapshot.

You can use:

- Built-in snapshot schedules in Storage Gateway.
- AWS Backup for centralized backup plans, retention, auditing, and restores.

AWS Backup supports backing up and restoring both cached volumes and stored volumes. Recovery points can restore into a Storage Gateway volume or an Amazon EBS volume depending on recovery needs.

### Reference Backup Workflow

1. Define RPO and backup windows.
2. Check upload buffer health, volume status, and AWS connectivity.
3. Configure backup plans or snapshot schedules.
4. Set retention and cross-account/cross-Region copies if required.
5. Monitor backup jobs and recovery points.
6. Periodically test restores to a gateway or EBS volume.
7. Verify data integrity, application consistency, and KMS permissions.

Volume snapshots alone do not guarantee application consistency for every database. For workloads requiring I/O quiescing or transactional consistency, coordinate snapshots with application backup hooks.

## 13. What Is Tape Gateway?

Tape Gateway provides a virtual tape library (VTL) for on-premises backup software. Backup software discovers tape drives and a media changer over iSCSI, writing backups to virtual tapes. The gateway stores virtual tapes in Amazon S3 and can archive them to S3 Glacier Flexible Retrieval or S3 Glacier Deep Archive.

Tape Gateway helps enterprises invested in tape-based backup software move tape vaults to the cloud without overhauling existing backup workflows.

### Components

- **Virtual tape library (VTL):** presents ready-to-read/write virtual tapes to backup software.
- **Tape drives:** iSCSI devices used by backup software for reads and writes.
- **Media changer:** emulates robotic loading and unloading of tapes in the library.
- **Virtual tape shelf (VTS):** long-term archive repository for ejected tapes.

When backup software ejects a tape, Tape Gateway uploads data and archives the tape into the chosen pool. Archived tapes cannot be read directly; they must be retrieved back to a Tape Gateway before restoring.

## 14. Tape Gateway Archiving and Retrieval

When creating virtual tapes, choose an archive pool:

| Archive Pool | Backend | Purpose |
|---|---|---|
| Glacier Pool | S3 Glacier Flexible Retrieval | Long-term storage with periodic retrieval needs |
| Deep Archive Pool | S3 Glacier Deep Archive | Very long-term storage rarely accessed |

Reference retrieval times per AWS documentation:

- Tapes in S3 Glacier Flexible Retrieval typically take about 3–5 hours to retrieve.
- Tapes in S3 Glacier Deep Archive typically take about 12 hours.

Actual durations and costs depend on archive tier, retrieval type, tape size, and system state. Never use archive pools for data requiring restoration in minutes.

Restore workflow:

1. Locate the tape barcode and status in the VTL.
2. Request retrieval of the tape from archive to a Tape Gateway in the same Region.
3. Wait for the tape status to transition to `AVAILABLE`.
4. Use backup software to mount/read the tape and restore data.
5. Verify restored data and log retrieval duration/costs.

Retrieved tapes are read-only (write-protected) so stored backups remain immutable. Test restores end-to-end before committing RTOs to the business.

## 15. Backup Software Integration

Tape Gateway is designed to work with backup applications supporting VTL/iSCSI. AWS maintains a list of supported third-party backup software along with configuration guides for specific products.

Before selecting, verify:

- Your backup software version is on the compatibility list.
- How the software manages media changers, barcodes, and tape pools.
- Tape eject/export procedures to trigger archiving.
- Handling of full tapes, expired tapes, and media rotation.
- Where backup catalogs are protected and whether they can recover independently.
- How backup software recovers if a gateway is replaced or a Region link drops.

For example, AWS publishes setup guides for Veeam Backup & Replication with Tape Gateway. Exact steps depend on software version and organizational backup policies; follow vendor instructions and current compatibility matrices.

For Volume Gateway, backup apps can use Storage Gateway snapshots or AWS Backup. For S3 File Gateway, stored data consists of S3 objects, enabling S3 Versioning, lifecycle rules, replication, and S3-native backup strategies.

## 16. Hybrid Networking

The gateway connects both to on-premises applications and to AWS endpoints. Network design must cover data paths, management, and synchronization.

### Client-to-Gateway Flows

| Gateway Type | Primary Protocol | Common Ports |
|---|---|---:|
| S3 File Gateway NFS | NFS | TCP 2049; some versions/operations require associated RPC services |
| S3 File Gateway SMB | SMB | TCP 445 |
| FSx File Gateway | SMB | TCP 445; plus Active Directory ports per configuration |
| Volume Gateway | iSCSI | TCP 3260 |
| Tape Gateway | iSCSI | TCP 3260 |

These are primary data protocol ports, not a complete firewall list. Always consult port requirements for your exact gateway type and version to open DNS, NTP, activation, service endpoints, AD/Kerberos/LDAP/RPC, and other needed connections.

### Gateway-to-AWS Flows

The gateway needs working DNS/NTP and HTTPS connectivity to the Storage Gateway service endpoint. For private connectivity, configure VPC endpoints and network paths per service documentation. Never assume a gateway can keep uploading during a total AWS outage; caches and upload buffers absorb only finite write bursts.

Gateways typically require outbound HTTPS over TCP 443 to AWS service endpoints and supporting endpoints listed in port requirements. Restrict outbound traffic to exact endpoints/Regions for your gateway type while permitting DNS and NTP to approved infrastructure. Avoid opening unrestricted outbound internet access when explicit endpoint lists suffice.

### Direct Connect or Site-to-Site VPN?

| Criterion | AWS Site-to-Site VPN | AWS Direct Connect |
|---|---|---|
| Connectivity | Encrypted tunnels over the Internet | Dedicated private network connection to AWS |
| Deployment time | Typically faster | Requires circuit provisioning and carrier setup |
| Latency stability | Depends on Internet routing | Generally predictable with dedicated bandwidth |
| Encryption | IPsec | Not encrypted at physical layer by default; consider MACsec or VPN overlay when required |
| Best suited for | Moderate workloads, backups, backup paths | Heavy traffic, stable latency, long-term hybrid workloads |

VPN can serve as a backup path for Direct Connect. Either way, measure real throughput, packet loss, latency, and data transfer costs.

## 17. Data Security and Access Control

Storage Gateway bridges corporate networks and AWS, requiring controls across clients, the gateway, and cloud backends.

### IAM and S3

For S3 File Gateway, file shares use an IAM role to access buckets/prefixes. Grant least-privilege permissions for needed operations; bucket policies should restrict access to the specific gateway, account, and encryption conditions. Avoid broad S3 access when only one prefix is needed.

### Active Directory and File Permissions

For SMB, integrate with Active Directory and restrict users/groups. For NFS, restrict client IPs/CIDRs and enforce UID/GID/Unix permissions. Disable guest access unless explicitly required by an application.

### Encryption

- Traffic between the gateway and AWS is protected by TLS per service design.
- S3 objects can use SSE-S3 or SSE-KMS per file share and bucket policy requirements.
- Volumes/tapes and backups require verifying KMS keys, key policies, and restore permissions.
- Local disks, hosts, hypervisors, and internal networks must also be hardened per company policy.

KMS keys are critical dependencies. If a key is disabled, loses policy grants, or enters pending deletion, encrypted backups and objects become unreadable. Document key ARNs, Regions, owners, and recovery steps in DR runbooks.

### Auditing

Enable CloudTrail to log Storage Gateway, S3, and AWS Backup API calls. For SMB, enable SMB audit logging where file-access tracking is needed. Store logs in access-isolated destinations with appropriate retention.

## 18. Performance, Sizing, and Caching

Gateway performance depends on host CPU/RAM, local disks, NICs, cache hit rates, upload buffers, network bandwidth, and workload patterns.

### Sizing Factors

- Working set: the subset of data read repeatedly.
- Write rate: new data written during peak periods.
- Upload backlog: volume accumulated during slow WAN or link outages.
- Cache hit ratio: percentage of read requests served from local cache.
- Concurrent clients: number of simultaneous clients and operations.
- File size distribution: millions of tiny files add metadata overhead; huge files stress upload throughput.
- Gateway VM CPU/RAM and local storage latency.

Never deploy a minimum-spec VM for every workload. Follow gateway-specific sizing guidance, then load-test using production-like file sizes, concurrency, and access patterns.

### Cache Metrics

For S3 File Gateway, metrics such as `CacheHitPercent`, `CachePercentUsed`, `CacheFree`, and `CloudBytesUploaded`/`Downloaded` track cache and network behavior. For Volume Gateway, monitor cache, upload buffer, read/write latency, and throughput per volume type.

If `CacheHitPercent` is low, expand cache capacity, improve working-set locality, or review access patterns. If `CachePercentDirty` stays elevated, data is waiting to upload; inspect bandwidth, upload throughput, network errors, and buffer capacity.

## 19. Monitoring and Operating the Gateway

Amazon CloudWatch provides metrics and alarms for Storage Gateway. Monitor both gateway health and supporting resources.

| Area | Metrics or Statuses | Meaning |
|---|---|---|
| Gateway health | Gateway status, health notifications | Is the gateway operating normally? |
| Cache | `CacheHitPercent`, `CachePercentUsed`, `CacheFree` | Does cache fit the working set or is it filling up? |
| Upload | `UploadBufferPercentUsed`, `CloudBytesUploaded` | Is data queued or uploading slowly? |
| Download | `CloudBytesDownloaded`, read latency | Cache misses and reads fetched from AWS |
| Volume | `ReadBytes`/`WriteBytes`, IOPS, latency, snapshot status | Block volume performance and backup progress |
| File share | File share status, upload notifications, refresh status | Is the file share available and synced? |
| Tape | Tape status, archive/retrieval progress | Are tapes ready for read/write or archived? |

Storage Gateway metrics follow CloudWatch retention policies; do not treat them as long-term audit archives. If multi-month trend analysis is required, export metrics or build dedicated dashboards/retention.

### Essential Alarms

- Gateway transitions to an unavailable state.
- Cache nears full capacity or cache hit ratio drops sharply.
- Upload buffer grows continuously or nears capacity.
- Upload/download throughput drops below baseline.
- Snapshot or backup jobs fail.
- File share leaves `AVAILABLE` state.
- `RefreshCache` does not finish within expected time.
- Tape archive/retrieval hangs or times out.

## 20. Updates, HA, and Gateway Recovery

Gateway appliances require software updates and maintenance. Schedule maintenance windows, read release notes, and check status afterward. Never modify hypervisor configurations or local disks attached to a running gateway arbitrarily.

### VMware HA

Storage Gateway integrates with VMware vSphere High Availability using application-level health checks on supported VMware deployments. If a host fails, vSphere HA restarts the VM on another cluster host. This provides appliance-level HA, not data backups or regional DR.

### Recovering a Failed Gateway

Recovery steps depend on gateway type:

- S3 File Gateway: deploy/activate a new gateway, attach file shares, and rebuild cache/inventory per recovery procedures.
- Volume Gateway: restore from EBS snapshots or recovery points; for cached volumes, take recovery snapshots per guidance.
- Tape Gateway: retrieve/associate virtual tapes on a new gateway per documented procedures.
- FSx File Gateway: deploy a new gateway, reconnect to the FSx file system, and verify AD/shares.

Never recover a gateway by cloning an old VM. Always follow official AWS recovery procedures to prevent inconsistent state.

## 21. Storage Gateway, DataSync, and Other Options

| Need | Best-Fit Service | Rationale |
|---|---|---|
| On-premises apps needing NFS/SMB interface to S3 | S3 File Gateway | Exposes file protocols backed by local cache |
| Windows apps needing SMB and AD to cloud file server | FSx File Gateway + FSx for Windows | Preserves native Windows file share semantics |
| Apps needing iSCSI block devices | Volume Gateway | Provides block volumes over iSCSI |
| Backup software needing VTL/tape workflows | Tape Gateway | Preserves tape backup workflows with cloud archiving |
| Bulk or scheduled file/object transfers | AWS DataSync | Managed data movement without maintaining a persistent file gateway |
| Cloud-native apps using object APIs | Direct Amazon S3 | Eliminates gateway layer |
| Cloud-native apps needing file systems | Amazon EFS or Amazon FSx | Managed file systems accessed directly over the network |

Storage Gateway is chosen when applications must keep using on-premises storage protocols. DataSync fits migrations or scheduled syncs; both can complement each other—for instance, using DataSync for initial bulk seeding into S3 and File Gateway afterward for ongoing file access.

## 22. Deployment Example: Integrating an On-Premises File Share with S3

A company runs a Linux application generating daily reports into an NFS share. Storage is growing rapidly, and operations wants to move storage to S3 without rewriting the application for S3 APIs.

### Design

1. Deploy an S3 File Gateway VM in the data center.
2. Provision local SSD cache sized for the working set and access rate.
3. Create a dedicated S3 bucket for reports with encryption enabled and a bucket policy scoped to the gateway role.
4. Create an NFS file share with allowed client CIDRs restricted to the application subnet.
5. Mount the share on the application server and test file permissions.
6. Configure CloudWatch alarms for cache, uploads, and gateway health.
7. If any external system writes directly to the bucket, plan `RefreshCache` and notifications; prefer a single standardized write path through the gateway.
8. Apply S3 Lifecycle rules to uploaded objects for appropriate storage classes and retention.
9. Test restoring files from S3, replacing a failed gateway, and handling WAN outages.

### Operational Flow

~~~mermaid
flowchart TD
    A[Linux report application] -->|NFS| B[S3 File Gateway]
    B --> C[Local cache]
    B -->|Upload async| D[S3 bucket]
    D --> E[S3 Lifecycle / Replication]
    F[CloudWatch metrics and alarms] --> G[Operations team]
    B --> F
    D --> H[Analytics / Data processing]
~~~

If the application must confirm a report is durably stored in S3 before firing a completion alert, workflows must wait for upload notifications or explicit confirmation. Never treat a local cache write as proof that S3 upload has finished.

## 23. Deployment Example: Backing Up On-Premises Servers with Volume Gateway

A legacy application requires iSCSI block storage and needs off-site backups.

### Selection

- If the entire dataset demands low local latency, evaluate Stored Volume Gateway.
- If the dataset is large with a small working set and can tolerate WAN latency on cache misses, evaluate Cached Volume Gateway.

### Steps

1. Deploy the gateway on a host with sufficient CPU/RAM and local disks.
2. Configure upload buffer and cache/primary storage per chosen mode.
3. Connect the application server via an iSCSI initiator.
4. Create, format, and mount volumes as required by the application.
5. Set up snapshot schedules or AWS Backup plans.
6. Monitor upload buffers, snapshot status, and latency.
7. Test restoring a snapshot into a new volume and attaching it to a test host.
8. Measure actual RTO/RPO and update runbooks.

If the data center loses WAN connectivity, Stored Volume Gateway retains primary data on local disks but cannot upload new snapshots. Cached Volume Gateway depends more heavily on cache hits and S3 reachability for cache misses. Simulate link failures before committing availability SLAs.

## 24. Costs and Optimization

Storage Gateway costs go beyond gateway fees alone. Factor in backend storage, requests, data transfer, retrievals, snapshots, local hardware, and operations.

| Gateway Type | Cost Components to Evaluate |
|---|---|
| S3 File Gateway | S3 storage classes, requests, versioning, replication, data transfer, and local cache hardware |
| FSx File Gateway | FSx capacity/throughput/backups, networking, gateway VM, and local cache |
| Volume Gateway | EBS snapshot storage, data transfer, gateway host/local disks, and AWS Backup |
| Tape Gateway | Virtual tape storage, archive tiers, retrievals, backup software licenses, and networking |

### Optimization Approaches

- Size caches for the working set rather than the entire dataset.
- Use cache hit and dirty cache metrics to spot bottlenecks.
- Pick storage classes matching read frequency and recovery SLAs.
- Manage S3 object version lifecycles to prevent unbounded noncurrent versions.
- Apply upload bandwidth throttling during business hours to protect WAN links.
- For Tape Gateway, pick Glacier Flexible Retrieval vs. Deep Archive according to restore RTO.
- For Volume Gateway, align snapshot schedules and retention with RPO.
- Monitor bucket data transfer and request charges.
- Delete unused gateways, volumes, snapshots, or virtual tapes once owners confirm.

Never pick an archive tier solely for storage price. If RTO demands a 30-minute restore while a tape requires 12 hours to retrieve, the architecture fails business requirements.

## 25. Common Deployment Pitfalls

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Gateway fails to activate | DNS, NTP, firewall, or unreachable service endpoint | Check network requirements and activation endpoint |
| File share not `AVAILABLE` | Misconfigured IAM role, bucket policy, or KMS policy | Verify role, bucket, key, and permissions |
| New S3 files do not appear | Gateway serving cached inventory | Run `RefreshCache` and wait for completion notification |
| Unexpected S3 storage growth | Versioning retaining many versions or file edits creating new versions | Review version lifecycle rules and write patterns |
| Low cache hit ratio | Large working set or random read patterns | Increase cache size, improve locality, and re-measure |
| Upload buffer nearing full | Slow WAN, low upload throughput, or link outage | Check network, buffer sizing, and bandwidth limits |
| iSCSI volume not visible | Wrong port, initiator, target, or session config | Verify TCP 3260, initiator configuration, and volume status |
| Snapshot fails to finish | Upload buffer, disk, or connectivity issues | Inspect gateway health and snapshot status |
| Tape restore misses SLA | Tape resides in archive tier requiring multi-hour retrieval | Align archive tiers with RTO and test retrievals |
| Gateway VM fails after cloning | Cloning/snapshotting gateway VMs is unsupported | Deploy a fresh gateway and follow recovery procedures |
| FSx share unreachable | AD, DNS, VPN/Direct Connect, or SMB policy issues | Check domain join, routing, and port requirements |

## 26. Production Checklist

- [ ] Selected the right gateway type for application protocols and data backends.
- [ ] Verified hypervisor/EC2 support and Hardware Appliance lifecycle status.
- [ ] Host meets CPU/RAM, local disk, and NIC sizing guidance.
- [ ] Cache and upload buffer sized for working set, write rate, and outage windows.
- [ ] DNS, NTP, firewalls, service endpoints, and hybrid routing verified.
- [ ] NFS/SMB/iSCSI restricted to authorized clients and subnets.
- [ ] IAM roles, bucket policies, Active Directory, and KMS policies follow least privilege.
- [ ] Defined source of truth and rules preventing uncoordinated writes outside the gateway.
- [ ] Scheduled or workflow-driven `RefreshCache` configured if S3 buckets change outside the gateway.
- [ ] Snapshots/AWS Backup/retention configured and restore tests passed.
- [ ] Tape archive tiers meet business retrieval RTOs.
- [ ] CloudWatch alarms monitor gateway health, cache, upload buffer, and snapshots.
- [ ] Procedures documented for gateway updates and deploying replacement gateways.
- [ ] Runbooks ready for WAN outages, gateway VM failures, or data center loss.
- [ ] Latency, throughput, cache hit ratio, and RTO/RPO measured under load tests.
- [ ] Storage, request, transfer, snapshot, and retrieval costs tracked.

## 27. Key Takeaways

AWS Storage Gateway connects on-premises applications to AWS storage services over familiar protocols. S3 File Gateway exposes NFS/SMB over S3 objects; FSx File Gateway provides SMB access to FSx for Windows File Server; Volume Gateway delivers iSCSI block volumes in cached or stored modes; and Tape Gateway emulates a VTL so backup software writes virtual tapes and archives them to S3 Glacier.

Each gateway type has distinct data flows and semantics. Size caches and upload buffers properly, verify WAN, DNS, NTP, IAM, KMS, Active Directory, and firewalls, and understand asynchronous uploads, cache refreshes, snapshots, and archive retrievals. Test gateway backups and HA with real restores rather than relying solely on device health indicators.

Choose Storage Gateway when applications require on-premises storage protocols paired with AWS storage backends. Combine CloudWatch, AWS Backup, S3 lifecycle rules, replication, and recovery runbooks to run a cost-controlled, operable hybrid storage solution aligned with business needs.

## References

- [What is AWS Storage Gateway?](https://docs.aws.amazon.com/storagegateway/latest/userguide/WhatIsStorageGateway.html)
- [Creating and Activating a Gateway](https://docs.aws.amazon.com/storagegateway/latest/userguide/creating-your-gateway.html)
- [Storage Gateway Requirements and Supported Hosts](https://docs.aws.amazon.com/storagegateway/latest/userguide/Requirements.html)
- [Storage Gateway Port Requirements](https://docs.aws.amazon.com/storagegateway/latest/userguide/Resource_Ports.html)
- [What is Amazon S3 File Gateway?](https://docs.aws.amazon.com/filegateway/latest/files3/what-is-file-s3.html)
- [How Amazon S3 File Gateway Works](https://docs.aws.amazon.com/filegateway/latest/files3/file-gateway-concepts.html)
- [Refreshing the S3 File Gateway Cache](https://docs.aws.amazon.com/filegateway/latest/files3/refresh-cache.html)
- [Monitoring S3 File Gateway](https://docs.aws.amazon.com/filegateway/latest/files3/monitoring-file-gateway.html)
- [What is Amazon FSx File Gateway?](https://docs.aws.amazon.com/filegateway/latest/filefsxw/what-is-file-fsxw.html)
- [FSx File Gateway Requirements](https://docs.aws.amazon.com/filegateway/latest/filefsxw/Requirements.html)
- [What is Volume Gateway?](https://docs.aws.amazon.com/storagegateway/latest/vgw/WhatIsStorageGateway.html)
- [How Volume Gateway Works](https://docs.aws.amazon.com/storagegateway/latest/vgw/StorageGatewayConcepts.html)
- [Backing Up Storage Gateway Volumes](https://docs.aws.amazon.com/storagegateway/latest/vgw/backing-up-volumes.html)
- [Best Practices for Volume Gateway](https://docs.aws.amazon.com/storagegateway/latest/vgw/best-practices.html)
- [How Tape Gateway Works](https://docs.aws.amazon.com/storagegateway/latest/tgw/StorageGatewayConcepts.html)
- [Archiving Virtual Tapes](https://docs.aws.amazon.com/storagegateway/latest/tgw/archiving-tapes-vtl.html)
- [Retrieving Archived Tapes](https://docs.aws.amazon.com/storagegateway/latest/tgw/retrieving-archived-tapes-vtl.html)
- [Monitoring Storage Gateway](https://docs.aws.amazon.com/storagegateway/latest/vgw/Main_monitoring-gateways-common.html)
- [VMware vSphere High Availability with Storage Gateway](https://docs.aws.amazon.com/storagegateway/latest/vgw/vmware-ha.html)
- [AWS Storage Gateway Hardware Appliance Availability Notice](https://docs.aws.amazon.com/storagegateway/latest/tgw/appliance-quick-start.html)
