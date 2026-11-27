# AWS DataSync and File and Object Data Migration

## Learning Objectives

After completing this lesson, you will be able to:

- Explain the role of AWS DataSync in transferring file and object data between on-premises, AWS, and other cloud providers.
- Distinguish DataSync agents, locations, tasks, and task executions.
- Choose Basic mode or Enhanced mode based on storage type, file/object count, and performance requirements.
- Determine when an agent is required vs. when transfers can run agentlessly.
- Design connectivity for NFS, SMB, HDFS, object storage, Amazon S3, Amazon EFS, and Amazon FSx.
- Configure IAM roles, bucket policies, KMS keys, network endpoints, and source/destination access permissions.
- Select transfer mode, overwrite behavior, delete handling, metadata preservation, filters, manifests, and verification options.
- Design initial copy, incremental sync, and cutover for a migration wave.
- Monitor progress via task execution status, CloudWatch metrics/logs, task reports, CloudTrail, and EventBridge.
- Optimize throughput, dataset partitioning, bandwidth throttling, costs, and quotas.
- Troubleshoot common errors and build a runbook for safe migrations.

## 1. What Problem Does AWS DataSync Solve?

When migrating a file server, NAS, or object storage system to AWS, copying data with manual scripts runs into recurring issues: inconsistent transfer speeds, poor progress visibility, missing integrity verification, lost metadata, and difficulty syncing incremental deltas.

AWS DataSync is a managed online data transfer service that copies files and objects between storage systems. It handles reading data, transferring over the network, writing to destination, comparing changes, verifying checksums, and tracking task executions.

Common scenarios include:

- Migrating on-premises file servers or NAS systems to Amazon S3, Amazon EFS, or Amazon FSx.
- Syncing objects between S3 buckets.
- Moving data between AWS and storage services on other clouds.
- Moving data from S3 to EFS or FSx to serve file-based applications.
- Creating periodic data copies for analytics, archiving, or business continuity.
- Transferring data in multiple passes to shrink cutover downtime.

DataSync targets file and object data. It does not replace database migration tools, block-level replication, or application-level replication. For databases requiring schema conversion, transaction logs, and consistency control, evaluate AWS Database Migration Service. For workloads needing server/volume-level replication, evaluate AWS Elastic Disaster Recovery or storage-platform replication.

### DataSync and Related Options

| Need | Service to Evaluate |
|---|---|
| Online, incremental file/object transfer with verification | AWS DataSync |
| Database migration preserving ongoing changes during migration | AWS Database Migration Service |
| Moving massive datasets when network bandwidth is insufficient | AWS Snow Family or suitable offline transfer |
| Providing a file interface for on-premises apps accessing S3 | AWS Storage Gateway |
| Replicating servers for disaster recovery | AWS Elastic Disaster Recovery |
| Replicating objects between S3 buckets via bucket rules | S3 Replication |
| Policy-based AWS resource backups | AWS Backup |

## 2. Architecture and Core Concepts

A DataSync transfer is defined by two locations and a task. Each run of a task produces a task execution.

| Component | Role |
|---|---|
| Agent | VM appliance used to read/write data with customer-managed storage systems |
| Location | Describes a storage endpoint and how DataSync accesses it |
| Task | Pairs a source location, destination location, and transfer options |
| Task execution | A specific run of a task |
| Task report | JSON report detailing transferred, skipped, verified, or deleted items |
| Service endpoint | Endpoint the agent connects to for the DataSync control plane |
| Task network interface | Network interface used on the data plane when tasks connect to AWS storage |

High-level flow:

~~~mermaid
flowchart LR
    S["Source storage"] --> A["DataSync agent or service connector"]
    A --> D["AWS DataSync service"]
    D --> T["Task execution"]
    T --> N["Task network interface / data path"]
    N --> O["Destination storage"]
    T --> M["CloudWatch metrics, logs and task report"]
~~~

DataSync performs three main phases in a task execution:

1. **Prepare:** scans source and destination to determine what data needs processing.
2. **Transfer:** reads data from source, sends it over the data path, and writes to destination.
3. **Verify:** checks checksums and metadata according to the chosen verification mode.

The Prepare phase can take longer than the actual transfer, especially for datasets with tens of millions of small files. Consequently, high network bandwidth alone does not guarantee fast task completion if inventory/scanning is the bottleneck.

## 3. Supported Storage Systems

DataSync supports the following location categories. Supported cloud providers and compatibility vary by Region and task mode; always verify the current AWS matrix before designing.

| Category | Location Types |
|---|---|
| Self-managed file storage | NFS, SMB |
| Hadoop | HDFS |
| Self-managed object storage | S3-compatible object storage |
| AWS object storage | Amazon S3 |
| AWS file storage | Amazon EFS |
| AWS managed file systems | FSx for Windows File Server, FSx for Lustre, FSx for OpenZFS, FSx for NetApp ONTAP |
| Other cloud storage | Google Cloud Storage, Azure Blob Storage, Azure Files, and AWS-supported object storage providers |

Key points to remember:

- NFS and SMB typically require an agent deployed near the file server.
- HDFS requires an agent with network access to NameNodes and DataNodes.
- S3-to-S3 within the same account can use DataSync agentlessly.
- Transfers between AWS storage services in the same account generally do not require an agent.
- Certain cross-account transfers can be agentless when one side is Amazon S3.
- Transfers between EFS and FSx across different accounts may require an agent and NFS/SMB location configurations.
- S3 on Outposts has specific task mode restrictions.

Do not assume every source/destination pair works simply because both location types appear in the list. Support depends on account, Region, partition, and Basic vs. Enhanced mode.

## 4. When Is a DataSync Agent Needed?

An agent is a VM appliance DataSync uses to access storage you manage. Agents can be deployed on-premises, in a VPC, or in supported virtualization environments.

### 4.1 Cases Typically Requiring an Agent

- On-premises NFS/SMB/HDFS to AWS.
- AWS EFS/FSx to storage on another cloud.
- Certain cross-account transfers between AWS storage services when neither side is S3.
- Certain transfers between commercial Regions and AWS GovCloud when both sides are EFS/FSx.

### 4.2 Cases Typically Agentless

- AWS storage services within the same account.
- S3 and another AWS storage service across accounts per the support matrix.
- Amazon S3 and object storage on another cloud.
- Certain S3 transfers between commercial Regions and GovCloud.

Examples:

| Source | Destination | Agent |
|---|---|---|
| On-prem NFS | S3 | Yes |
| On-prem SMB | FSx for Windows | Yes |
| S3 | S3 same account | No |
| S3 account A | S3 account B | No |
| S3 | EFS different account, per support matrix | No |
| EFS | FSx different account | May be needed, depending on location configuration |
| S3 on Outposts | S3 in Region | Yes |

Always verify against the "Do I need an AWS DataSync agent?" and "Where can I transfer your data?" documentation before creating locations.

### 4.3 Agent Placement

Deploy the agent close to source storage to minimize latency and maximize throughput. The agent needs:

- Connectivity to source storage using the appropriate protocol.
- Connectivity to the DataSync service endpoint.
- Data-plane connectivity to task network interfaces and destination services.
- Proper DNS resolution and routing.
- CPU, RAM, and disk sized for the dataset.

Agents can be deployed on VMware ESXi 7.0/8.0, KVM, Nutanix AHV via KVM image, Microsoft Hyper-V, or Amazon EC2 per current AWS options. Enhanced mode agents also support Red Hat OpenShift Virtualization per the October 2026 update.

After activation, AWS manages the appliance and automatically updates agent software and underlying OS. Updates typically run when the agent is idle; the agent may go offline briefly during updates. Check agent status ahead of critical scheduled tasks.

### 4.4 Reference Resource Requirements

| Agent VM Type | vCPU | RAM | Disk |
|---|---:|---:|---:|
| Basic mode agent | 4 | 32 GB for datasets up to 20M items; 64 GB above | 80 GB |
| Enhanced mode agent | 8 | 32 GB | 80 GB |

For EC2-hosted agents, AWS publishes specific instance family/size recommendations based on mode and file count. Datasets with deep directories or large metadata can consume more RAM than expected. Never size an instance solely by total TB; file count and average file size matter just as much.

## 5. Basic Mode and Enhanced Mode

DataSync provides two task modes. Mode must be chosen at task creation and cannot be changed afterward. To switch modes, create a new task.

| Criterion | Enhanced Mode | Basic Mode |
|---|---|---|
| Processing | Parallel listing, preparing, transfer, and verification | Phases are largely sequential |
| Dataset size | Practically unlimited objects per task quota | Enforces file/object/directory quotas |
| Performance | Typically higher, especially for large datasets | Can be slower due to sequential prepare/verify |
| Logging | Structured JSON logs | Unstructured logs |
| Verification | Verifies transferred data | Defaults to checking entire source/destination |
| Task mode | Immutable after creation | Immutable after creation |
| S3 on Outposts | Not supported | Supported |
| Agent | Requires Enhanced mode agent for agent-based transfers | Requires Basic mode agent for agent-based transfers |

### 5.1 Enhanced Mode Updates in 2026

Enhanced mode expanded support across recent AWS updates:

- July 2026: added EFS, FSx for Lustre, HDFS, and agent-based transfers with Azure Blob/object storage; added Hyper-V agent.
- October 2026: added NFS 4.2, FSx for OpenZFS, and object metadata control options.
- October 29, 2026: added remaining FSx types including FSx for Windows File Server and FSx for NetApp ONTAP; added agent image for Red Hat OpenShift Virtualization.

Enhanced mode is now supported across almost all DataSync transfer locations except transfers involving S3 on Outposts. Certain flows to/from NFS, SMB, HDFS, Azure Blob, or object storage require an Enhanced mode agent. For agentless transfers, support depends on the exact source/destination pair.

### 5.2 Differences in Object Tags

When transferring cloud storage to or from a location that does not support object tags:

- Enhanced mode may fail the task immediately if `ObjectTags` is unset or set to `PRESERVE`.
- Basic mode may continue while logging per-object errors where tags cannot be preserved.

Verify destination metadata/tag support before creating tasks, especially for cross-provider object storage migrations.

### 5.3 Required Permissions

To create an Enhanced mode task, the principal calling `CreateTask` requires `iam:CreateServiceLinkedRole`. The account also needs access to DataSync resources and required permissions on location resources. Never grant overly broad permissions just to clear a permission error; identify which role performs each action.

## 6. Agentless Transfers and Cross-Account / Cross-Region

DataSync can move data between AWS storage services without an agent. Within the same account, traffic stays on the AWS network and never traverses the public Internet.

### 6.1 Cross-Account

For cross-account S3, configure an IAM role for DataSync in the account owning the destination or source bucket. The role trust policy must allow DataSync to assume it; bucket policies and KMS key policies must permit required actions.

Do not confuse:
- The role DataSync assumes to access the bucket.
- The role of the operator creating the task.
- The role or credentials the agent uses to access self-managed systems.

### 6.2 Cross-Region

For transfers between AWS storage services in two Regions, one location must reside in the Region where the DataSync task runs. Some NFS/SMB/HDFS/object storage flows cannot be configured as cross-Region transfers in the same way; both locations must be accessible from the Region where the agent is activated.

Cross-Region transfers incur data transfer out charges from the source Region. Factor this alongside DataSync per-GB charges and storage costs.

## 7. Selecting Destination Storage

DataSync moves data; selecting the destination storage remains an architectural decision.

| Destination | When Appropriate |
|---|---|
| Amazon S3 | Objects, backup files, data lakes, archives, static content |
| Amazon EFS | Shared POSIX file systems for Linux workloads |
| FSx for Windows File Server | SMB shares, Windows ACLs, Active Directory integration |
| FSx for Lustre | HPC, ML, high-performance file workloads |
| FSx for OpenZFS | NFS workloads needing filesystem features and low latency |
| FSx for NetApp ONTAP | Enterprise NAS, NFS/SMB, multi-protocol, and NetApp data services |

Evaluate:

- Protocols used by the application.
- POSIX permissions, UID/GID, Windows ACLs.
- File locking and concurrent writers.
- Throughput, IOPS, and latency.
- Capacity and growth.
- Backups, replication, and retention.
- Storage classes and lifecycle policies.
- Availability Zones/Regions and disaster recovery.

Moving from NFS to S3 changes the data model. Applications must read/write objects via compatible APIs or gateways; you cannot assume a POSIX path will work directly against S3.

## 8. Creating an NFS Location

An NFS location requires an agent capable of mounting the NFS export.

Before creating the location:

1. Identify the NFS server hostname/IP and export path.
2. Choose an agent on a network able to reach the server.
3. Open required NFS ports on firewalls.
4. Configure export permissions for the agent.
5. Verify read or write privileges depending on source/destination role.

DataSync defaults to NFS 4.1. Versions 4.2, 4.0, and 3.x are also supported; NFS 4.2 works only in Enhanced mode.

Example read-only source export:

~~~text
/export/data 10.20.1.50(ro,no_root_squash)
~~~

Example read/write destination export:

~~~text
/export/landing 10.20.1.50(rw,no_root_squash)
~~~

These are illustrative examples. Restrict access to the agent's IP per security policy. If root access is not granted, configure UID/GID permissions so DataSync can read or write required data and metadata.

Create the location:

~~~bash
aws datasync create-location-nfs \
  --server-hostname 192.0.2.10 \
  --on-prem-config AgentArns=arn:aws:datasync:ap-southeast-1:111122223333:agent/agent-0123456789abcdef0 \
  --subdirectory /export/data \
  --region ap-southeast-1
~~~

The command returns a `LocationArn`. Save this ARN for the task's source or destination.

## 9. Creating SMB and HDFS Locations

### 9.1 SMB

An SMB location requires an agent and share credentials. DataSync supports NTLM and Kerberos authentication per location configuration.

Verify:

- Server hostname/domain and share path.
- User permissions to enumerate, read, write, and read metadata appropriately.
- Domain/DNS and Kerberos realm when using Kerberos.
- SMB version. AWS recommends SMB 3.0.2 or later because SMB 1.0 carries known security risks.
- Permissions to read/write Windows ACLs if preserving security descriptors.

Example creating an SMB location with NTLM:

~~~bash
aws datasync create-location-smb \
  --agent-arns arn:aws:datasync:ap-southeast-1:111122223333:agent/agent-0123456789abcdef0 \
  --server-hostname fileserver.example.internal \
  --subdirectory /share/migration \
  --authentication-type NTLM \
  --user datasync-user \
  --password fileb://smb-password.txt \
  --domain EXAMPLE \
  --region ap-southeast-1
~~~

In production, never leave passwords in shell history or source control. Prefer AWS-supported secret storage such as Secrets Manager with tightly scoped read permissions.

### 9.2 HDFS

An HDFS location requires an agent able to reach:

- NameNode.
- DataNodes.
- Hadoop KMS if the cluster uses encryption zones.
- Kerberos KDC if Kerberos authentication is configured and supported for that location/task type.

Typical ports are NameNode 8020, DataNode 9866 for Hadoop 3.x, Hadoop KMS 9600, and Kerberos KDC 88. Actual ports depend on your Hadoop distribution and cluster configuration.

## 10. Creating an Object Storage Location

DataSync can access S3-compatible object storage on-premises or on another cloud. Provide:

- Server hostname.
- Bucket/container name.
- Prefix (subdirectory) if transferring only a subset.
- HTTP/HTTPS protocol and port.
- Access key/secret key or supported credentials.
- Agent ARN if the transfer scenario requires an agent.
- Certificate chain if object storage uses a private/self-signed CA.

Prefer HTTPS. Never use plain HTTP across untrusted networks where credentials and data can be exposed. If the server uses a private CA, provide the proper certificate chain so DataSync can validate the server.

DataSync can transfer object storage with or without an agent depending on source/destination and task mode. Check agent requirements before creating the location.

## 11. Creating an Amazon S3 Location

An S3 location uses an IAM role that DataSync assumes to access the bucket. Required permissions differ depending on whether the bucket is source or destination.

### 11.1 Source S3 Permissions

Typically required permissions include:

- `s3:GetBucketLocation`
- `s3:ListBucket`
- `s3:ListBucketMultipartUploads`
- `s3:GetObject`
- `s3:GetObjectTagging` if copying tags
- `s3:GetObjectVersion` and `s3:GetObjectVersionTagging` when handling versioned objects
- `s3:ListMultipartUploadParts` when required

### 11.2 Destination S3 Permissions

In addition to list/location permissions, the destination role typically needs:

- `s3:PutObject`
- `s3:AbortMultipartUpload`
- `s3:ListMultipartUploadParts`
- `s3:GetObject` and `s3:GetObjectTagging` for verification or metadata operations
- `s3:PutObjectTagging` if preserving object tags
- `s3:DeleteObject` if the task is permitted to remove destination objects

These are reference permissions. Depending on task options, versioning, object tags, encryption, and cross-account access, policies may require specific adjustments.

### 11.3 Creating an S3 Location

~~~bash
aws datasync create-location-s3 \
  --s3-bucket-arn arn:aws:s3:::company-migration-bucket \
  --s3-config BucketAccessRoleArn=arn:aws:iam::111122223333:role/DataSyncS3AccessRole \
  --subdirectory /migration/finance \
  --s3-storage-class STANDARD \
  --region ap-southeast-1
~~~

If the bucket uses SSE-KMS with a customer managed key, the key policy must allow the DataSync IAM role to use the key. The IAM policy also needs KMS permissions matching read/write actions; exact permissions depend on source/destination and encryption settings. For cross-account SSE-KMS, specify the full key ARN in the role policy and authorize the role in the key-owning account's key policy. DataSync cannot access buckets using SSE-C.

### 11.4 Cross-Account S3

For a bucket in another account:

- The role DataSync assumes must exist in the bucket-owning account.
- The trust policy must allow DataSync to assume the role.
- The bucket policy must grant the role required actions.
- The KMS key policy must allow the role to use the key if SSE-KMS is enabled.
- Consider `aws:SourceAccount` and `aws:SourceArn` conditions to mitigate confused deputy risk.
- Check Object Ownership and ACL settings to avoid writing objects with unexpected ownership or access.

In Basic mode, S3 prefixes cannot start with a leading slash or contain patterns such as `//`, `/./`, or `/../`. Enhanced mode supports these prefixes. If a source bucket contains unusual object keys, verify mode compatibility and test on a sample prefix before running production tasks.

## 12. IAM, Secrets Manager, and KMS

DataSync separates permissions across multiple layers:

| Principal | Responsibility |
|---|---|
| Migration operator | Creates agents/locations/tasks; starts/stops executions |
| DataSync service-linked role | Executes service operations requiring AWS-managed permissions |
| S3 access role | Allows DataSync to access source/destination buckets |
| Agent / local storage credentials | Accesses NFS, SMB, HDFS, or object storage |
| Logging role / service-linked permissions | Writes logs to CloudWatch |
| Manifest access role | Reads manifests from S3 when a task uses a manifest |

### 12.1 Least Privilege

- Grant DataSync operators permissions only on needed tasks/locations/agents.
- Scope S3 access roles to exact buckets and prefixes.
- Never grant `s3:*` across an entire account.
- Scope KMS keys to the specific role and encryption context where appropriate.
- Never store SMB passwords or object-storage secrets in task definition files.
- Use CloudTrail to audit changes to roles, locations, tasks, and policies.

### 12.2 Data Encryption

DataSync encrypts traffic between locations using mutual TLS 1.3. Connections to source and destination storage use the respective storage protocol's protections, such as SMB security features, object storage TLS, or AWS storage service encryption.

Encryption at rest remains controlled by destination storage:

- S3 SSE-S3 or SSE-KMS.
- EFS encryption at rest.
- FSx encryption at rest using a KMS key.
- Source storage encryption if supported by the existing system.

DataSync does not automatically make every source or destination encrypted at rest. Verify storage settings and key policies independently.

## 13. Network Design for DataSync

A transfer involves at least three logical connections:

1. Agent connects to source storage to read data.
2. DataSync data plane transfers data between source and destination.
3. DataSync service connects to destination storage to write data.

When an on-premises agent uses a public or FIPS endpoint, it requires HTTPS to the DataSync service. With a VPC service endpoint, the agent uses AWS PrivateLink to connect to the service. Task network interfaces in your subnet/VPC need appropriate security groups and routes to reach AWS storage.

### 13.1 Common Ports

| Source | Destination | TCP Port | Purpose |
|---|---|---:|---|
| Agent | NFS server | 2049 | NFS 4.0/4.1/4.2 |
| Agent | NFS server | 111, 2049 | NFS 3.x |
| Agent | SMB server | 139 or 445 | SMB |
| Agent | S3-compatible object storage | 443 or 80 | Object API; prefer HTTPS |
| Agent | Hadoop NameNode | 8020 default | HDFS metadata |
| Agent | Hadoop DataNodes | 9866 default Hadoop 3.x | HDFS data |
| Agent | Kerberos KDC | 88 | Authentication |
| Agent | DataSync VPC endpoint | 1024-1064 | Control plane |
| Agent | DataSync task network interfaces | 443 | Data plane |

Exact ports depend on protocol and storage configuration. Check network requirements documentation for your specific location types.

DataSync supports dual-stack IPv4/IPv6 for supported data sources such as EFS, NFS, SMB, and object storage. Older agent images downloaded before July 16, 2025 do not support IPv6. In dual-stack networks, verify agent version and IP preferences so one side does not attempt IPv6 while routes/firewalls permit only IPv4.

### 13.2 PrivateLink and FIPS

DataSync supports public, VPC, and FIPS service endpoints in supported Regions. VPC endpoint policies can restrict DataSync actions. For compliance workloads, confirm FIPS endpoint availability, agent compatibility, and encryption settings.

### 13.3 Direct Connect and VPN

Direct Connect or Site-to-Site VPN can provide the network path between agents and on-premises/VPC resources. DataSync still requires connectivity to its service endpoint and task data path. Verify route propagation, MTU, firewalls, DNS, and security groups bidirectionally.

## 14. How DataSync Detects Changes and Transfers Data

By default, DataSync scans source and destination to identify files/objects needing copying. It compares content/metadata per task options, transferring only differences when `TransferMode` is `CHANGED`.

On the first run, most of the dataset transfers. Subsequent runs can copy only modified files/objects.

### 14.1 Basic Mode

Basic mode prepares the dataset, then transfers and verifies sequentially. With many small files, scanning/preparing can consume the majority of total execution time.

### 14.2 Enhanced Mode

Enhanced mode parallelizes listing, preparing, transferring, and verification. Data can start transferring as soon as items are prepared, scaling far better on massive datasets.

### 14.3 Open or Locked Files

- DataSync can usually transfer open files.
- If a file changes while being transferred, verification may detect an inconsistency; rerun the task to capture the latest version.
- If a file is locked and the storage server denies DataSync access, the file may be skipped with an error.
- DataSync does not lock or unlock files on behalf of applications.

For database files or continuously written datasets, coordinate snapshots/quiescing or application-level exports. Never treat a successful file copy alone as proof of transactional consistency.

## 15. Transfer Mode, Overwrite, and Delete Behavior

These options govern how DataSync synchronizes data.

| Option | API Value | Meaning |
|---|---|---|
| Transfer only changed data | `CHANGED` | After initial copy, copy only differing data/metadata |
| Transfer all data | `ALL` | Copy all source data on every run |
| Overwrite destination | `ALWAYS` | Overwrite when source differs from destination |
| Do not overwrite | `NEVER` | Preserve destination even if source differs |
| Keep destination-only files | `PRESERVE` | Do not delete destination files/objects absent from source |
| Remove destination-only files | `REMOVE` | Delete destination items no longer present at source |

Notes:

- `CHANGED` fits recurring synchronization.
- `ALL` can be useful to force a full re-copy, but increases data transfer and request costs.
- `REMOVE` can delete data on destination.
- `PreserveDeletedFiles=REMOVE` cannot be combined with `TransferMode=ALL` because DataSync does not scan destination to identify deletions in `ALL` mode.
- Overwriting may incur retrieval or early-deletion charges in certain S3 storage classes. Overwriting metadata can effectively delete/recreate objects and incur charges.
- When destination receives independent writes, `NEVER` protects destination data but can leave source and destination out of sync.

Before enabling `REMOVE`, pilot against a dedicated prefix and verify filters, backups/versioning, and destination data ownership.

## 16. Metadata Preservation

Moving files/objects is more than copying bytes. Applications may rely on permissions, ownership, timestamps, tags, and metadata.

### 16.1 POSIX Metadata

DataSync can preserve:

- UID/GID.
- POSIX permissions.
- Access time (Atime).
- Modification time (Mtime).
- Metadata for special devices within supported limits.

Atime is best-effort since timestamp semantics vary across systems. `Mtime=PRESERVE` is recommended for recurring transfers so DataSync detects changes consistently.

DataSync does not copy NFS version 4 ACLs. If applications rely on NFSv4 ACLs, plan separate permission migration and test on destination before cutover.

### 16.2 SMB Security Descriptors

When transferring between SMB and FSx for Windows File Server, or between FSx for Windows File Server locations, you can configure copying owner, DACLs, and SACLs via `SecurityDescriptorCopyFlags`.

SACLs require elevated privileges on Windows sources. The destination may assign ownership based on the user configured for the destination location. Verify ACL semantics and domain identities before cutover.

### 16.3 Object Metadata and Tags

When transferring between object storage systems, DataSync can preserve user-defined object metadata and object tags. Enhanced mode added `ObjectMetadata` control options in the October 2026 update.

Metadata mappings across cloud providers are not always 1:1. Attributes such as `ContentType`, `ContentEncoding`, `ContentLanguage`, and `CacheControl` may copy on a best-effort basis if supported by destination.

Never assume proprietary metadata from a source vendor transfers intact to destination. Build a test dataset exercising all metadata/tag types and verify results prior to large migrations.

## 17. Filters and Manifests

Two mechanisms select which data gets transferred:

- **Filters:** select files/folders/objects by pattern.
- **Manifest:** list exact files/objects to transfer.

### 17.1 Include Filters

Include filters restrict scanned/transferred data. For example, transfer only two directories:

~~~text
/finance|/legal
~~~

Include patterns support a trailing `*` wildcard. For example, `/reports*` is supported, whereas `*.csv` is not a valid include pattern under current wildcard rules.

### 17.2 Exclude Filters

Exclude filters skip unwanted data:

~~~text
*/.temp|*/cache|*.tmp
~~~

Filters are case-sensitive and relative to the source location path. In AWS CLI, wrap filters in single quotes and separate multiple patterns with `|`.

Example:

~~~bash
aws datasync create-task \
  --source-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-source12345678901 \
  --destination-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-dest1234567890123 \
  --excludes FilterType=SIMPLE_PATTERN,Value='*/temp|*/tmp'
~~~

### 17.3 Manifest

A manifest is a CSV file listing exact file/object paths to transfer. Manifests fit when the list comes from an inventory system or when controlling a specific subset of items.

A manifest cannot specify a directory name to imply copying its contents recursively. List individual file/object paths or use an include filter for directory trees.

Enhanced mode supports manifests up to 20 GB. Store the manifest in S3 and grant an IAM role for DataSync to read it. You can pin the manifest's S3 version ID so runs use the exact approved list.

### 17.4 Paths Excluded Automatically by DataSync

DataSync automatically ignores certain special paths such as `.snapshot`, `/.aws-datasync`, `/.awssync`, and `/.zfs` in applicable scenarios. Check current AWS documentation if your storage platform creates custom snapshot directories or metadata paths.

## 18. Data Integrity and Verification

DataSync always performs integrity checks in transit during transfer. Additionally, you can configure post-transfer verification.

| Verify Mode | API Value | Behavior |
|---|---|---|
| Verify only transferred data | `ONLY_FILES_TRANSFERRED` | Compares checksums of transferred items between source and destination |
| Verify all data | `POINT_IN_TIME_CONSISTENT` | Scans and verifies the entire source and destination dataset |
| No additional verification | `NONE` | Retains only in-transit integrity checks during transfer |

`ONLY_FILES_TRANSFERRED` is recommended for most cases and is the default in Enhanced mode. `POINT_IN_TIME_CONSISTENT` is the default in Basic mode, but is not supported in Enhanced mode.

When using a manifest, verification applies only to items listed in the manifest. `POINT_IN_TIME_CONSISTENT` is unsuitable for S3 Glacier Flexible Retrieval or S3 Glacier Deep Archive; consult storage class guidance before selecting it.

Verification failures can include:

- Checksum failure.
- Metadata failure.
- Files were added.
- Files were removed.
- Source modified while task was running.

A task execution status of `SUCCESS` means DataSync completed according to its configured options. It does not prove the application is ready for cutover, all business transactions are consistent, or unsupported metadata was preserved.

## 19. Scheduling and Incremental Synchronization

DataSync tasks can run manually or on a schedule. Schedules support cron/rate expressions with a minimum interval of one hour. Schedules use UTC.

Example running daily at 22:00 UTC:

~~~text
cron(0 22 * * ? *)
~~~

Example running every 12 hours:

~~~text
rate(12 hours)
~~~

A task schedule can be automatically disabled if the task repeatedly fails with the same error or the Region is disabled. Monitor `Schedule` status and `DisabledReason`.

### 19.1 Multi-Pass Migration

A common strategy:

1. Initial copy: transfer the full dataset.
2. Incremental copy: run periodically to copy deltas.
3. Rehearsal: measure delta sync time and test the application on destination.
4. Freeze: stop writes or switch source to read-only.
5. Final sync: execute the final pass and verify.
6. Cutover: switch clients/applications to destination.
7. Validation: verify reads/writes, permissions, paths, metadata, and business workflows.
8. Rollback window: keep source read-only or rollback-ready per policy.
9. Decommission: retire source only after owner sign-off and retention compliance.

DataSync does not automatically create transactionally consistent snapshots for applications. For continuously written files, pair with application quiescing, storage snapshots, or storage-native consistency mechanisms.

## 20. Monitoring Task Executions

When starting a task, DataSync transitions through statuses such as:

| Status | Meaning |
|---|---|
| `QUEUED` | Waiting for agent/task slot |
| `LAUNCHING` | Initializing task execution |
| `LAUNCHED` | Execution started |
| `PREPARING` | Scanning and determining items to transfer |
| `TRANSFERRING` | Transferring data |
| `VERIFYING` | Verifying data |
| `SUCCESS` | Completed |
| `ERROR` | Execution failed |
| `CANCELLING` | Stopping execution |

Task status and task execution status are distinct concepts. A task may be `AVAILABLE` or `UNAVAILABLE` while an execution carries its own status.

One agent runs one task execution at a time. If another task shares the same agent, its execution enters `QUEUED`. Task queueing is enabled by default.

## 21. CloudWatch Metrics, Logs, and Task Reports

### 21.1 CloudWatch Metrics

DataSync publishes metrics to the **`aws/datasync`** namespace at 5-minute intervals and retains metrics for 15 months.

Useful metrics:

| Metric | Meaning |
|---|---|
| `BytesTransferred` | Logical bytes sent by DataSync before compression |
| `BytesCompressed` | Physical bytes sent over network after compression, if any |
| `BytesWritten` | Bytes written at destination |
| `FilesTransferred` | Files/objects/directories transferred |
| `FilesSkipped` | Items skipped |
| `FilesDeleted` | Items deleted at destination |
| `FilesListedSource` | Objects discovered at source in Enhanced mode |
| `FilesPrepared` | Objects prepared for transfer in Enhanced mode |
| `BytesVerifiedDestination` | Bytes verified at destination in Basic mode |
| `BytesPreparedSource` | Bytes prepared at source in Basic mode |

Metric availability differs between Basic and Enhanced mode. Filter metrics by `TaskId` and `AgentId` to pinpoint bottlenecks.

### 21.2 CloudWatch Logs

Enable at least basic and transfer-error logging. Enhanced mode automatically sends structured logs to `/aws/datasync` via the service-linked role. Basic mode requires configuring a log group and write permissions.

Select log level by need:

- `OFF`: sends no task logs.
- `BASIC`: logs basic info and transfer errors.
- `TRANSFER`: logs every transferred file/object and integrity check.

`TRANSFER` can generate substantial log volume; factor in retention and ingestion costs.

### 21.3 Task Reports

Task reports are generated in JSON at two detail levels:

- Summary only: counts of transferred/skipped/verified/deleted items, bytes, start/end timestamps, status, and task options.
- Standard: summary plus per-file/object/folder details for transferred, skipped, verified, or deleted items; configurable for errors only or successes and errors.

Task reports are invaluable when migrating millions of files, auditing chain-of-custody, or pinpointing individual failed items.

### 21.4 CloudTrail and EventBridge

CloudTrail records API calls such as creating locations, creating tasks, starting executions, updating tasks, and deleting resources. EventBridge can capture task execution state-change events to trigger notifications or automation.

Use SNS/Chatbot or incident management tools to alert owners when executions hit `ERROR` or schedules become disabled.

## 22. Optimizing Throughput and Migration Duration

Performance depends on many factors:

- Bandwidth and latency between agent and source/destination.
- Storage throughput and IOPS.
- File count and average file size.
- Metadata lookup performance.
- Agent CPU and RAM.
- Task mode.
- Concurrent task count.
- Compression and data compressibility.
- Prepare and Verify durations.

### 22.1 Many Small Files

With millions of small files, metadata operations and directory traversal become the bottleneck. Consider:

- Splitting datasets by directory or prefix.
- Running multiple tasks in parallel with dedicated agents per task.
- Assigning multiple agents to one location when appropriate.
- Narrowing scope via include/exclude filters or manifests.
- Verifying the storage array is not overloaded by parallel reads.

DataSync allows up to four Basic mode agents and four Enhanced mode agents attached to a single location. Multiple agents do not provide HA: every agent attached to a location must be online when the task starts.

### 22.2 Many Large Files

For large files, network throughput and storage I/O matter more than metadata scanning. Check:

- NIC bandwidth and EC2 instance network performance.
- Direct Connect / VPN throughput.
- Destination storage throughput.
- Data compression ratio.
- Task bandwidth limit.

### 22.3 Bandwidth Throttling

Use `BytesPerSecond` to avoid saturating production links. Setting `-1` represents unlimited bandwidth in DataSync configuration. Raise limits overnight during off-peak windows and throttle during peak business hours.

Never tune bandwidth limits based solely on network utilization. Watch source storage latency, application latency, and queue backlogs as well.

## 23. Quotas and Limits to Know

Quotas vary by Region. Check AWS Service Quotas ahead of large migrations.

| Item | Published Default Value |
|---|---:|
| Tasks per account/Region | 100, adjustable on request |
| Basic mode: items for on-prem/self-managed/other cloud to AWS | 50 million files/objects/directories per task execution |
| Basic mode: items between AWS storage services | 25 million per task execution |
| Enhanced mode: items | Practically unlimited by task dataset quota |
| Max throughput per agent-based task | 10 Gbps |
| Max throughput per agentless task | 5 Gbps |
| Filter length | 102,400 combined characters |
| Queued executions per task | 50 |
| Concurrent Enhanced task executions | 120 |
| Task execution history | 30 days |
| Enhanced mode manifest | 20 GB |

In Basic mode with over 20 million items, AWS requires at least 64 GB RAM on the agent. S3 prefixes count as directories toward Basic mode quotas; deeply nested prefixes increase inventory item counts.

For huge datasets, partition tasks by prefix/directory and avoid overlaps so items are neither copied twice nor accidentally deleted. Never evaluate quotas using total TB alone; inventory file/object/directory counts as well.

## 24. AWS DataSync Costs

DataSync costs include:

1. **DataSync data transfer charge:** per-GB fee for transferred data.
2. **Enhanced mode task execution charge:** additional task execution fee for Enhanced mode.
3. **Storage request charges:** S3 `LIST`, `HEAD`, `GET`, `PUT`, tagging, and multipart requests.
4. **Destination storage charges:** S3/EFS/FSx storage, throughput, IOPS, or provisioned capacity.
5. **Data transfer charges:** cross-Region, Internet egress, or related network charges.
6. **KMS charges:** API requests against customer managed keys.
7. **PrivateLink:** VPC interface endpoint charges if used.
8. **Logging/reporting:** CloudWatch Logs, S3 task reports, and Athena queries.

### 24.1 Why Can S3 Request Costs Be High?

Each task execution may scan source and destination. DataSync can invoke:

- `ListObjectsV2` to list prefixes.
- `HeadObject` to inspect metadata during prepare/verify.
- `GetObject` to read object content.
- `GetObjectTagging` to read tags.
- `PutObject` and multipart uploads to write objects.
- `PutObjectTagging` to write tags.
- `CopyObject` when updating metadata.

Even when few bytes change, scanning millions of objects generates request charges.

### 24.2 Storage Classes

When S3 is destination, DataSync writes new objects to the selected storage class. For existing objects, DataSync preserves the existing storage class by default unless `TransferMode=ALL` is used.

Certain storage classes incur retrieval, overwrite, deletion, or minimum storage duration fees. Overwriting metadata can effectively delete/recreate an object and trigger charges.

Consider:

- S3 Standard / Intelligent-Tiering for frequently accessed or unpredictable patterns.
- S3 Standard-IA / One Zone-IA when appropriate and retrieval patterns are planned.
- Glacier classes for archiving after migration completes, rather than writing directly to archive classes during repeated sync loops.
- Lifecycle rules to clean up incomplete multipart uploads.

### 24.3 Cost Optimization

- Do not schedule syncs more frequently than data actually changes.
- Narrow prefixes and scope using filters or manifests.
- Choose Basic vs. Enhanced based on object count, compatibility, and execution cost.
- Set bandwidth limits suited to the network.
- Avoid verifying the entire dataset every run when verifying only transferred files suffices.
- Plan storage classes and lifecycle rules ahead.
- Estimate cross-Region data transfer charges.
- Monitor S3 request metrics alongside DataSync metrics.

## 25. Ensuring Cutover and Rollback

A migration is not over when DataSync reports `SUCCESS`. Validate applications, owners, and data consistency.

### 25.1 Cutover Checklist

1. Inventory source dataset and record file/object counts and total size.
2. Choose destination storage and confirm permissions/metadata mapping.
3. Run initial copy.
4. Inspect task reports, errors, and skipped items.
5. Run scheduled incremental syncs.
6. Test applications against destination.
7. Schedule maintenance window and notify owners.
8. Stop writes or switch source to read-only.
9. Run final sync.
10. Run verification and data reconciliation.
11. Switch DNS, mount paths, or application configuration.
12. Monitor application metrics and error logs.
13. Retain source for the rollback window.
14. Decommission only after business owner sign-off.

### 25.2 Rollback

If the application fails on destination:

- Stop writes to destination to prevent split-brain.
- Revert application/mount paths to source if source remains authoritative.
- Identify data written after cutover and how to reconcile it.
- Never run reverse sync automatically without verifying overwrite/delete semantics.
- Record errors and fix tasks/options before the next cutover attempt.

DataSync does not resolve bidirectional data conflicts. If both source and destination accept writes, you need application- or storage-level conflict resolution.

## 26. AWS DataSync Discovery and Service Changes

AWS DataSync Discovery previously collected capacity, utilization, and performance metrics from supported storage systems to recommend AWS storage targets. However, the DataSync Discovery feature was discontinued on May 20, 2025.

Therefore, for new projects, do not design workflows around creating DataSync Discovery jobs. Use storage vendor inventories, AWS Migration Hub (for existing projects), or other appropriate discovery/assessment tools for planning, then use DataSync for data movement.

Keep this in mind when encountering older tutorials that still describe DataSync Discovery.

## 27. Lab: Migrating NFS Data to Amazon S3

This lab simulates migrating from an NFS file server to S3 using Enhanced mode. Use a sandbox account and test data. Never use production data or enable destination deletion on a first run.

### Step 1: Prepare

Prerequisites:

- AWS account and Region supporting DataSync.
- NFS server with a test export.
- DataSync Enhanced mode agent deployed near the NFS server.
- Target S3 bucket.
- IAM role allowing DataSync to access S3.
- Network paths between agent, NFS server, and DataSync endpoints.

Create the bucket and configure encryption/lifecycle per lab requirements. Verify the NFS export allows only the agent's IP.

### Step 2: Create the NFS Location

~~~bash
aws datasync create-location-nfs \
  --server-hostname 192.0.2.10 \
  --on-prem-config AgentArns=arn:aws:datasync:ap-southeast-1:111122223333:agent/agent-0123456789abcdef0 \
  --subdirectory /export/lab \
  --region ap-southeast-1
~~~

Save the returned `LocationArn` as `SOURCE_LOCATION_ARN`.

### Step 3: Create the S3 Access Role and Location

The DataSync role needs source/destination permissions accordingly. For a destination bucket, allow listing the bucket, multipart operations, putting/getting objects, and tag operations if preserving tags.

Create the S3 location:

~~~bash
aws datasync create-location-s3 \
  --s3-bucket-arn arn:aws:s3:::company-datasync-lab \
  --s3-config BucketAccessRoleArn=arn:aws:iam::111122223333:role/DataSyncS3AccessRole \
  --subdirectory /lab-migration \
  --s3-storage-class STANDARD \
  --region ap-southeast-1
~~~

Save the returned `LocationArn` as `DESTINATION_LOCATION_ARN`.

### Step 4: Create an Enhanced Mode Task

~~~bash
aws datasync create-task \
  --source-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-source12345678901 \
  --destination-location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-dest1234567890123 \
  --name nfs-to-s3-lab \
  --task-mode ENHANCED \
  --options TransferMode=CHANGED,VerifyMode=ONLY_FILES_TRANSFERRED,OverwriteMode=ALWAYS,PreserveDeletedFiles=PRESERVE,LogLevel=TRANSFER \
  --region ap-southeast-1
~~~

Replace location ARNs with your actual ARNs. The principal creating an Enhanced task needs `iam:CreateServiceLinkedRole`. For Enhanced tasks, DataSync automatically sends structured logs to `/aws/datasync` when the service-linked role and Region are configured properly.

### Step 5: Run the Task

~~~bash
aws datasync start-task-execution \
  --task-arn arn:aws:datasync:ap-southeast-1:111122223333:task/task-0123456789abcdef0 \
  --region ap-southeast-1
~~~

Save the returned `TaskExecutionArn`. Check status:

~~~bash
aws datasync describe-task-execution \
  --task-execution-arn arn:aws:datasync:ap-southeast-1:111122223333:task/task-0123456789abcdef0/execution/exec-0123456789abcdef0 \
  --query Status \
  --region ap-southeast-1
~~~

### Step 6: Verify Data

- Confirm task execution reaches `SUCCESS`.
- Inspect CloudWatch logs and task reports if configured.
- Compare file/object counts and bytes transferred.
- Spot-check sample files by checksum.
- Check POSIX permissions/UID/GID if needed.
- Check object metadata/tags if required.
- Confirm source files were not deleted.
- Rerun the task to test incremental behavior.

### Step 7: Test Failure Handling

Create a test file the agent cannot read or a locked file. Observe skipped/error reporting. Then fix permissions and rerun.

### Step 8: Cleanup

After finishing the lab and saving results:

~~~bash
aws datasync delete-task \
  --task-arn arn:aws:datasync:ap-southeast-1:111122223333:task/task-0123456789abcdef0 \
  --region ap-southeast-1
~~~

~~~bash
aws datasync delete-location \
  --location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-source12345678901 \
  --region ap-southeast-1
~~~

~~~bash
aws datasync delete-location \
  --location-arn arn:aws:datasync:ap-southeast-1:111122223333:location/loc-dest1234567890123 \
  --region ap-southeast-1
~~~

Delete the S3 bucket, IAM role, and agent only when certain no other resources depend on them. The commands above are samples; substitute ARNs created during your lab.

## 28. Common Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Agent offline | VM stopped, DNS/network/firewall, or endpoint unreachable | Check agent status, VM, routes, DNS, and endpoint ports |
| NFS mount failed | Wrong export path, blocked NFS ports, or missing export permissions | Test mount from a host on the same network and check export rules |
| SMB access denied | Invalid user/domain/password or insufficient share/NTFS ACLs | Check credentials, domain, DNS, share, and file ACLs |
| Kerberos authentication failed | Mismatched principal/keytab/krb5.conf | Check case-sensitive principal, realm, and clock synchronization |
| S3 location creation failed | Missing IAM role, bucket policy, KMS key policy, or trust policy | Verify assume-role trust and S3/KMS permissions |
| S3 `HeadObject`/`GetObjectTagging` AccessDenied | Missing permissions to read metadata/tags/versions | Add `GetObject`/`GetObjectTagging`/`GetObjectVersion` permissions |
| Task stuck in `PREPARING` | Too many small files or slow storage scan | Check item count, agent RAM, storage metadata speed, and filters |
| Task `QUEUED` | Agent running another task | Wait for prior task to finish or assign a dedicated agent |
| Task `UNAVAILABLE` | Agent offline or location unreachable | Check agent and location connectivity |
| Checksum failure | File modified during transfer or storage read inconsistency | Stop writes, rerun incremental sync, and inspect source storage |
| Metadata failure | Destination does not support source metadata | Adjust metadata options or choose compatible target storage |
| Files skipped | Filters, permissions, locked files, or special paths | Read task report for per-item skip reasons |
| Enhanced task fails on object tags | Destination lacks tag support while `ObjectTags=PRESERVE` | Set `ObjectTags=NONE` if business does not need tags |
| High S3 request costs | Task scans millions of objects per run | Reduce schedule frequency; scope with prefixes or manifests |
| Low throughput | Agent/storage/network bottleneck or small-file overhead | Measure each layer; scale agents/tasks and partition dataset |
| Task schedule disabled | Repeated task failures or disabled Region | Check `DisabledReason`, fix error, and re-enable schedule |
| Unwanted stale files at destination | `PreserveDeletedFiles=PRESERVE` | Evaluate `REMOVE` after backups and scoped testing |
| Destination overwritten | `OverwriteMode=ALWAYS` | Use `NEVER` or separate prefixes; verify task execution options |
| Unsupported task mode | Incompatible source/destination/task mode | Check support matrix and create a new task in the right mode |

## 29. Best Practices

### Before Migration

- Inventory file/object counts, total capacity, and average item size.
- Classify data by owner, sensitivity, and retention.
- Verify storage compatibility and task mode.
- Choose agent vs. agentless based on the AWS matrix.
- Benchmark throughput and prepare duration with a pilot.
- Design least-privilege IAM, KMS, and networking.
- Define RPO, RTO, cutover windows, and rollback plans.

### During Migration

- Use Enhanced mode for large datasets where locations support it.
- Use filters/manifests to control scope.
- Enable task reports for large datasets or audit requirements.
- Keep source authoritative until final sync and validation finish.
- Monitor task status, errors, skipped files, and checksums.
- Use bandwidth limits to protect production networks and storage.
- Run parallel tasks only when source/destination have sufficient I/O and network headroom.

### After Migration

- Verify file counts, bytes, metadata, and permissions.
- Test applications against destination.
- Retain source per rollback and retention policies.
- Reconcile costs and S3 request charges.
- Archive task reports and approval evidence.
- Decommission source only after business owner sign-off.

### Ongoing Operations

- Set sync intervals no more frequent than real business need.
- Monitor schedule status and task execution errors.
- Alert on task `ERROR`, offline agents, or rising queue age.
- Review task reports and CloudWatch metrics.
- Audit IAM roles, Secrets Manager secrets, and KMS permissions.
- Verify quotas ahead of major migration waves.
- Update runbooks as AWS expands task modes or supported locations.

## 30. Practice Questions

1. What problem does AWS DataSync solve?
2. Distinguish agent, location, task, and task execution.
3. When does DataSync require an agent?
4. Give an example of an agentless transfer between two S3 buckets.
5. How does Enhanced mode differ from Basic mode across prepare/transfer/verify?
6. Why cannot task mode be changed after creation?
7. Is DataSync Discovery still available?
8. Why should the agent be deployed close to source storage?
9. What information does an NFS location require?
10. Why should the S3 access role be separate from the operator role?
11. What is the difference between `TransferMode` `CHANGED` and `ALL`?
12. What does `OverwriteMode` `NEVER` protect?
13. Why must `PreserveDeletedFiles` `REMOVE` be tested carefully?
14. Can `REMOVE` be combined with `TransferMode` `ALL`?
15. Which types of metadata can DataSync preserve?
16. Are include filters case-sensitive?
17. When should you use a manifest instead of a filter?
18. How does `ONLY_FILES_TRANSFERRED` differ from `POINT_IN_TIME_CONSISTENT`?
19. Why can files written during migration fail verification?
20. Can a DataSync schedule run more frequently than once per hour?
21. What information do task reports provide?
22. Why can S3 request costs be high even when few bytes changed?
23. Can one agent run multiple tasks concurrently?
24. Does DataSync resolve conflicts when both source and destination accept writes?
25. Which steps must complete before cutover?

### Answer Hints

1. Managed, incremental file/object transfer with verification and monitoring across on-premises, AWS, and other clouds.
2. Agent accesses storage; location describes an endpoint; task defines source/destination/options; execution is a single run.
3. Primarily when accessing on-prem/self-managed storage or cross-account/cross-cloud pairs per the support matrix.
4. S3 bucket in account A to S3 bucket in account B in supported flows can run agentlessly.
5. Enhanced parallelizes stages and supports massive datasets; Basic runs sequentially and enforces quotas.
6. Mode dictates agent type, processing architecture, and task behavior; changing modes requires a new task.
7. No. Discovery was discontinued on May 20, 2025.
8. Minimizes network latency and maximizes read performance from storage.
9. Agent ARN, server hostname, export path, and NFS mount options.
10. Operators manage tasks; DataSync assumes the S3 role to read/write S3. Separating roles enforces least privilege.
11. `CHANGED` copies only differences after initial copy; `ALL` copies all source items every run.
12. Prevents overwriting modified data on destination.
13. It can delete destination data, risking data loss or storage charges.
14. No. `REMOVE` requires scanning destination; `ALL` does not scan destination to detect deletions.
15. Depending on systems: POSIX UID/GID/permissions/timestamps, SMB ACLs, object tags, and user-defined metadata.
16. Yes. Filters are case-sensitive.
17. When transferring an exact list of files/objects rather than matching patterns.
18. `ONLY_FILES_TRANSFERRED` verifies transferred items; `POINT_IN_TIME_CONSISTENT` scans the entire dataset and is unsupported in Enhanced mode.
19. Source changes mid-transfer cause checksums or metadata to mismatch.
20. No. Minimum schedule interval is one hour.
21. Summaries and item-level details for transferred/skipped/verified/deleted items with status, bytes, and timestamps.
22. DataSync still scans and issues `LIST`/`HEAD`/`GET`/tagging requests across millions of objects.
23. No. An agent executes one task execution at a time.
24. No. Authoritative source and conflict resolution must be designed separately.
25. Initial/incremental syncs, write freeze, final sync, verification, application validation, owner approval, and rollback plan.

## 31. Interview Questions

### When should you choose DataSync over writing a custom `rsync` script?

When you need managed transfers, monitoring, scheduling, incremental copying, verification, filters/manifests, and native AWS storage integration. Custom scripts can work for small environments or niche logic, but engineering must build and maintain retries, auditing, monitoring, and consistency controls themselves.

### Is DataSync a backup tool?

DataSync can copy data periodically and assist with certain business continuity scenarios, but it does not replace backup lifecycles, point-in-time recovery, immutable retention, or application-consistent backups. Pair with AWS Backup, S3 Versioning/Object Lock, or snapshots per workload needs.

### Why is Enhanced mode suited for tens of millions of objects?

Enhanced mode parallelizes listing, preparing, transferring, and verification while avoiding Basic mode dataset quotas. However, agents, storage I/O, networking, and supported locations remain practical bounds.

### When are multiple agents needed?

When datasets are huge, contain many small files, or require parallel tasks and storage/network can sustain the load. Attaching multiple agents to one location does not create HA; all attached agents must be online when a task runs.

### Does DataSync guarantee consistency while applications continue writing?

It does not guarantee application-level transactional consistency. DataSync can flag files modified mid-transfer, but clean migration still requires quiescing or snapshots plus a final incremental sync.

### Why is application testing still required after a task reports `SUCCESS`?

`SUCCESS` confirms transfer completed per task options. Applications may depend on ACLs, paths, case sensitivity, ownership, file locking, or semantics not fully mirrored by destination storage.

### When should you use a manifest instead of an include filter?

Use a manifest when you have an exact list of files/objects to transfer, such as an approved inventory. Use filters when selecting by folder or filename patterns.

### Can DataSync perform bidirectional synchronization?

A task has explicit source and destination roles, not conflict-resolving bidirectional sync. Two opposing tasks can overwrite each other. Design a clear source of truth and handle conflicts at the application or storage layer.

## 32. Pre-Production Migration Checklist

### Scope and Compatibility

- [ ] Source/destination pair is in the supported transfer matrix.
- [ ] Correct task mode selected.
- [ ] Agent requirements verified.
- [ ] Dataset inventory includes file/object/directory counts and total capacity.
- [ ] Storage metadata and permissions mapped.
- [ ] Discovery removed from plans if legacy documentation referenced it.

### Security and Networking

- [ ] Agent placed on a network close to source storage.
- [ ] Security groups/firewalls allow required ports.
- [ ] DataSync service endpoint and task ENIs have valid network paths.
- [ ] IAM roles follow least privilege.
- [ ] S3 bucket policies and KMS key policies verified.
- [ ] No secrets stored in shell history or source control.
- [ ] Encryption at rest and in transit verified.

### Task Options

- [ ] Appropriate `TransferMode` selected.
- [ ] `OverwriteMode` reviewed.
- [ ] `PreserveDeletedFiles` verified not to delete unintended data.
- [ ] Metadata/tag/ACL options match destination capabilities.
- [ ] Filters/manifests tested.
- [ ] `VerifyMode` aligns with task mode and storage class.
- [ ] Bandwidth limits and schedules approved.

### Monitoring and Operations

- [ ] CloudWatch metrics monitored.
- [ ] Task logs and task reports enabled.
- [ ] CloudTrail/EventBridge notifications have assigned owners.
- [ ] Runbooks ready for `ERROR`, offline agents, and skipped items.
- [ ] Quotas and throughput verified.
- [ ] S3 request costs and data transfer charges estimated.

### Cutover

- [ ] Initial copy completed.
- [ ] Incremental sync rehearsed.
- [ ] Maintenance window announced.
- [ ] Source writes stopped or controlled.
- [ ] Final sync and verification PASSED.
- [ ] Application validation PASSED.
- [ ] Rollback plan and retention window approved.
- [ ] Business owner sign-off obtained before source decommission.

## 33. Official References

- [What is AWS DataSync?](https://docs.aws.amazon.com/datasync/latest/userguide/what-is-datasync.html)
- [How AWS DataSync works](https://docs.aws.amazon.com/datasync/latest/userguide/how-datasync-transfer-works.html)
- [Where can I transfer my data with AWS DataSync?](https://docs.aws.amazon.com/datasync/latest/userguide/working-with-locations.html)
- [Do I need an AWS DataSync agent?](https://docs.aws.amazon.com/datasync/latest/userguide/do-i-need-datasync-agent.html)
- [Choosing a task mode for your data transfer](https://docs.aws.amazon.com/datasync/latest/userguide/choosing-task-mode.html)
- [Requirements for AWS DataSync agents](https://docs.aws.amazon.com/datasync/latest/userguide/agent-requirements.html)
- [Deploying your AWS DataSync agent](https://docs.aws.amazon.com/datasync/latest/userguide/deploy-agents.html)
- [Activating your AWS DataSync agent](https://docs.aws.amazon.com/datasync/latest/userguide/activate-agent.html)
- [AWS DataSync network requirements](https://docs.aws.amazon.com/datasync/latest/userguide/datasync-network.html)
- [AWS DataSync encryption in transit](https://docs.aws.amazon.com/datasync/latest/userguide/encryption-in-transit.html)
- [Configuring AWS DataSync transfers with an NFS file server](https://docs.aws.amazon.com/datasync/latest/userguide/create-nfs-location.html)
- [Configuring AWS DataSync transfers with an SMB file server](https://docs.aws.amazon.com/datasync/latest/userguide/create-smb-location.html)
- [Configuring AWS DataSync transfers with Amazon S3](https://docs.aws.amazon.com/datasync/latest/userguide/create-s3-location.html)
- [Configuring DataSync transfers with an object storage system](https://docs.aws.amazon.com/datasync/latest/userguide/create-object-location.html)
- [Creating a task for transferring your data](https://docs.aws.amazon.com/datasync/latest/userguide/create-task-how-to.html)
- [Choosing what AWS DataSync transfers](https://docs.aws.amazon.com/datasync/latest/userguide/task-options.html)
- [Configuring how to handle files, objects, and metadata](https://docs.aws.amazon.com/datasync/latest/userguide/configure-metadata.html)
- [Transferring specific files, objects, and folders by using filters](https://docs.aws.amazon.com/datasync/latest/userguide/filtering.html)
- [Transferring specific files or objects by using a manifest](https://docs.aws.amazon.com/datasync/latest/userguide/transferring-with-manifest.html)
- [Configuring how AWS DataSync verifies data integrity](https://docs.aws.amazon.com/datasync/latest/userguide/configure-data-verification-options.html)
- [Scheduling when your AWS DataSync task runs](https://docs.aws.amazon.com/datasync/latest/userguide/task-scheduling.html)
- [Starting a task to transfer your data](https://docs.aws.amazon.com/datasync/latest/userguide/run-task.html)
- [Monitoring your AWS DataSync transfers](https://docs.aws.amazon.com/datasync/latest/userguide/monitoring-overview.html)
- [Monitoring data transfers with Amazon CloudWatch metrics](https://docs.aws.amazon.com/datasync/latest/userguide/monitor-datasync.html)
- [Monitoring data transfers with task reports](https://docs.aws.amazon.com/datasync/latest/userguide/task-reports.html)
- [Monitoring data transfers with Amazon CloudWatch Logs](https://docs.aws.amazon.com/datasync/latest/userguide/configure-logging.html)
- [AWS DataSync quotas](https://docs.aws.amazon.com/datasync/latest/userguide/datasync-limits.html)
- [AWS DataSync pricing](https://aws.amazon.com/datasync/pricing/)
- [AWS DataSync document history](https://docs.aws.amazon.com/datasync/latest/userguide/doc-history.html)

