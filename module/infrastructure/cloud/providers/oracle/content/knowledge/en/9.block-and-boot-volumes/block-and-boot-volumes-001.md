# Distinguishing Boot Volume, Block Volume, and Local NVMe

## Lesson Objectives

An OCI Compute instance can use multiple types of storage devices. Inside the operating system, they can all appear as disks, but their physical location, role, lifecycle, and data recovery methods are very different.

This lesson belongs to the **Block Volume and Boot Volume** chapter of the **CLOUD_PROVIDERS_ORACLE** module. Learners need to understand how to choose storage for OCI infrastructure while connecting it to Compute, IAM, monitoring, cost, and availability.

After this lesson, you will be able to:

- Explain what Boot Volume, Block Volume, and local NVMe are used for.
- Distinguish between block-level storage, attached devices, filesystems, and application directories.
- Identify which data must persist independently of the instance and which data can be regenerated.
- Interpret capacity, IOPS, throughput, and latency metrics without inferring solely from device names.
- Plan backup, recovery, instance replacement, and control of remaining storage resources.

This lesson does not assume a specific shape, capacity size, performance tier, or price by default. Volume attachment capabilities and local NVMe lifecycles must be verified against the exact instance type, shape, operating system, and planned OCI operations.

## 1. How Are the Three Concepts Different?

**Boot Volume** is the startup volume of an instance in OCI's Boot Volume boot model. It contains the components needed to boot and run the operating system, typically including the root partition and related boot components.

**Block Volume** is a block-level storage volume that you create and attach to an instance for use as needed. It typically holds application data, data filesystems, or data for software with its own block device management mechanism.

**Local NVMe** is NVMe storage attached locally to the Compute host, available on shapes that provide this hardware. It is not an independent Block Volume that you can detach from a host and attach to another instance using the standard Block Volume service workflow.

| Criterion | Boot Volume | Block Volume | Local NVMe |
| --- | --- | --- | --- |
| Primary role | Boot and host the operating system | Additional on-demand block storage | Host-local storage on supported shapes |
| Relationship to Compute | Used as the boot volume | Attached to an instance via an appropriate attachment | Tied to the hardware and lifecycle of the Compute environment |
| Can it hold application data? | Yes, though data separation should be considered | Yes, this is a common use case | Yes, if lifecycle risks are accepted and properly handled |
| Exists independently of the instance | Can be retained, depending on policies and operations | Has its own lifecycle, though still subject to deletion by operations/policies | Not treated as an independent resource movable across hosts like a service volume |
| Data protection | Backup and recovery plan for boot | Appropriate backup, cloning, and recovery plan | Data regeneration or replication/backup to another durable location |
| Performance | Based on volume configuration and I/O path | Based on volume configuration, attachment, and instance limits | Based on local hardware, shape, and workload |

"Boot" describes the startup role; "block" describes how storage is provisioned at the block level; "local NVMe" describes the technology and connection locality. These are not three quality tiers ranked from lowest to highest.

## 2. From Storage Device to Application Data

### 2.1. Block Storage Is Not Yet a Directory

A block storage service provides a range of readable/writable blocks. For a typical application to store files on it, the operating system must recognize the device and have an appropriate storage structure.

A typical flow:

```text
Volume in OCI
  -> Attachment between the volume and instance
  -> Device recognized by the operating system
  -> Partition or volume management layer, if used
  -> Filesystem
  -> Mount point
  -> Application data directory
```

**Attach does not mean mount.** A volume attached to an instance by OCI might still not be used by the operating system or mounted at the exact path the application needs.

A newly created empty Block Volume and a volume restored from a backup also differ: a restored volume may already contain partitions and a filesystem. Do not treat every newly appearing device as an empty disk needing re-initialization.

Some software uses block devices through its own management mechanism instead of mounting a standard filesystem. In such cases, follow the software's storage architecture rather than mechanically applying the filesystem creation workflow.

### 2.2. The Mount Point Determines Where the Application Actually Writes

Suppose data is expected to reside at `/srv/app-data`, mounted from a Block Volume. If the mount fails while the directory still exists on the root filesystem, the application can continue writing to the Boot Volume.

Possible consequences include:

- The Boot Volume fills up even though the data Block Volume is empty.
- Operators back up the wrong location and miss newly written data.
- When the volume is mounted back, the files underneath the mount point become hidden from the visible path.
- Replacement instances do not have the files accidentally written to the old machine's boot volume.

You must verify mounts and make application startup depend on the data filesystem using the operating system's service management mechanism. Do not merely check that the directory exists.

### 2.3. Device Names Alone Are Not Enough to Determine the Storage Source

A path like `/dev/sdb` is not proof that it is always the data Block Volume. Device ordering and naming can change depending on the operating system, attachments, or the boot process.

Similarly, a name containing `nvme` describes the device interface seen by the operating system; it is not enough to conclude that the data has the local NVMe lifecycle of a specific shape. You must cross-check the OCI configuration, attachment information, and appropriate device identifiers.

When configuring persistent mounts, use stable identifiers supported by the operating system and attachment type. If cloning or restoring volumes, also inspect filesystem identifiers to avoid assuming every copy has a different UUID.

## 3. Boot Volume: Where the Operating System Boots

### 3.1. Components Typically Placed on Boot

A Boot Volume typically contains:

- The bootloader and related boot partitions.
- The operating system, kernel, packages, and base libraries.
- Machine configuration, operational agents, and system services.
- Logs, temporary files, or applications if not separated onto another filesystem.

An image is the source used to create the initial machine environment, whereas a Boot Volume is the storage resource used by the instance when running under this model. An image does not replace backups for data generated during operation.

For example, an image containing a JDK and an application does not automatically contain files uploaded by users after the instance has been running for three months.

### 3.2. Should Business Data Be Stored on Boot?

Technically, the operating system can write data to a filesystem located on the Boot Volume. However, mixing the operating system with business data creates operational dependencies:

- Upgrades or machine replacements easily force handling both the OS and data simultaneously.
- Sudden log growth can fill the filesystem used for operating system operations.
- The capacity and backup needs of the operating system differ from those of business data.
- Rebuilding a machine from an image becomes harder if unique data still resides only on the old machine.

For small systems, a shared layout may be acceptable if intentional and backed by a designed backup/restore plan. For systems requiring frequent instance replacement, separating data makes lifecycle management clearer.

Separating data does not mean just renaming a directory. You must confirm the directory actually resides on the data volume or chosen storage service.

### 3.3. Boot Volume Has a Lifecycle That Needs Separate Management

When terminating an instance, how the Boot Volume is handled depends on the keep/delete option and the lifecycle management tools in use. Do not assume that deleting an instance always deletes the boot volume, or always keeps it.

If a Boot Volume is retained, the data still needs to be managed for access permissions, backups, cost, and recoverability. If the boot volume is deleted without an appropriate recovery copy, the original image does not guarantee restoration of all subsequent changes.

There are recovery and maintenance procedures related to Boot Volumes, but they must meet requirements regarding location, instance state, image, and OCI support capabilities. Do not manipulate a boot volume like a regular data volume while the operating system still depends on it.

## 4. Block Volume: Data With an Independent Lifecycle

### 4.1. Separating Data From the Host Lifecycle

A key benefit of Block Volume is the ability to manage data more independently of the instance. When an application machine needs replacement, you can design a workflow to preserve the data volume and connect it to a replacement environment that meets volume attachment conditions.

Common use cases:

- Self-managed application data requiring a dedicated filesystem.
- Data and logs of self-operated database software.
- Working datasets that must persist across multiple instance replacements.
- Storage capacity growing independently of CPU/RAM needs.

Block Volume does not automatically turn an application into a high-availability system. A filesystem served by only a single machine may still require time to reattach, verify, and start the application when that machine fails.

### 4.2. Location and Attachment Types Have Constraints

The volume and instance must satisfy the service's attachment location constraints—typically the same availability domain for standard volume attachments. Do not treat a volume as a drive that can be directly attached to any arbitrary region or availability domain.

If recovery in another location is needed, appropriate backup/restore, copying, or replication workflows may be required instead of direct attachment. The support and scope of each mechanism must be verified separately.

Attachment types such as paravirtualized or iSCSI have different OS requirements and connection steps. Success on the OCI side is not enough to prove the filesystem is ready inside the guest machine.

### 4.3. Attaching the Same Volume to Multiple Machines Does Not Create a Safe Shared Filesystem

Some configurations support multiple attachments with appropriate access modes. That does not mean you can mount a standard filesystem read/write on multiple instances and write concurrently.

For multiple machines to safely use the same block device, you need an application architecture, filesystem, or cluster management software that supports concurrent access and consistent coordination. Without this mechanism, data can become corrupted even if all attachments were created successfully.

If the application needs to share files over the network, evaluate a file storage service or an appropriate sharing solution. Block storage and file storage address different interface layers.

### 4.4. Capacity in OCI and Filesystem Capacity Are Two Layers

When increasing volume size, the operating system may also need to rescan the device size, extend the partition or volume management layer, and then extend the filesystem using a supported method.

Do not conclude the task is complete simply because the Console displays the new size. Conversely, shrinking or migrating data must not be assumed to be a simple reverse of expanding capacity; choose a workflow appropriate for the service and filesystem.

## 5. Local NVMe: Local Performance Coupled With Host Lifecycle

### 5.1. Local Means Data Is Tied to Compute Hardware

On shapes with local NVMe, the application uses the host's local storage devices. This can offer useful latency and throughput characteristics, but the device does not have an independent resource model like a remote Block Volume.

Potentially suitable workloads:

- Caches that can be repopulated from a primary data source.
- Intermediate files in batch jobs or data processing pipelines.
- Scratch space for compute tasks.
- Components of a system that already has a verified data replication and recovery mechanism.

You must also account for the time needed to rebuild caches or intermediate data when a machine is lost. A design that runs fast in steady state may still recover too slowly if it has to reload a massive amount of data.

### 5.2. Do Not Infer Lifecycle From One Successful Reboot

Local NVMe does not follow a simple rule like "every reboot loses data." Behavior depends on the shape and actual operation. However, data surviving one reboot also does not prove it survives stop/start, shape changes, host migration, maintenance, or termination.

Before using it, build a matrix for your exact environment:

| Event | Questions to Confirm |
| --- | --- |
| OS reboot | How are the devices and data preserved for this instance type? |
| Stop/start | Will the same hardware continue to be used, and is local data preserved? |
| Shape change or instance replacement | Will previously used local devices still be accessible? |
| Host maintenance or hardware failure | What is the data recovery plan when the old machine becomes unreachable? |
| Terminate or scale-in | Which data must be saved elsewhere before the machine is removed? |

When the business requirement is "never lose the sole copy of data if the host disappears," do not use local NVMe as the sole point of protection.

### 5.3. Using Local NVMe for Regenerable Data

Example of an image processing task:

```text
Original image in durable storage
  -> download to local NVMe for decoding and processing
  -> write final result to durable storage
  -> confirm task completion
  -> intermediate files may be deleted
```

If the instance is lost mid-task, the system can pick up the task again and process from the original image. Duplicate result writes or side effects during retries must be controlled.

Conversely, if the application confirms an upload as successful while the file resides only on local NVMe without a durable copy, the system may lose data that was already reported to the user as successful.

## 6. Performance: Reading Capacity, IOPS, Throughput, and Latency Properly

### 6.1. Four Distinct Metrics

| Metric | Description | Example Question |
| --- | --- | --- |
| Capacity | Total amount of data that can be stored | Is there enough space for data, logs, and growth? |
| IOPS | Number of I/O operations completed per second | Can it handle many small accesses? |
| Throughput | Amount of data transferred per second | Is reading/writing large files fast enough? |
| Latency | Time to complete a single operation | Does each read/write slow down transactions? |

Assuming the same I/O size and ignoring overhead:

```text
Approximate throughput = IOPS x size per I/O

20,000 IOPS x 8 KiB = 160,000 KiB/s
                    = 156.25 MiB/s
```

A workload reading 1 MiB blocks at 300 MiB/s only needs about 300 operations per second under this simple model. Therefore, a high IOPS number alone is not enough to conclude that every workload will be fast.

### 6.2. Bottlenecks Can Lie Outside the Volume

Observed performance is affected by the entire I/O path:

- Volume performance level and capacity as configured in the service.
- Limits of the shape and allocated instance resources.
- Attachment type, drivers, and operating system configuration.
- Network path to remote storage.
- I/O size, queue depth, sequential vs. random read/write patterns.
- Filesystem, caching, data synchronization mechanisms, and application access patterns.

Increasing volume resources does not guarantee improvement if the bottleneck is on the Compute or application side. Similarly, fast local NVMe will not fix a request that mostly waits on a remote database.

Benchmark results must describe measurement conditions, especially caching and durable write requirements. Reading data already cached in RAM is not a direct measurement of disk speed.

### 6.3. Boot Can Also Become a Bottleneck

If application logs and temporary files reside on the root filesystem, a heavy write burst can affect other operating system activities. Monitoring the Boot Volume is not just checking whether there is enough space to install packages; you need to observe free space, latency, and I/O behavior while the application runs.

Separating data or log filesystems when justified helps isolate requirements and reduce contention on the same volume. However, volumes may still share instance-level limits, so splitting does not automatically double the machine's I/O capacity.

## 7. Data Durability, Backup, and Consistency

### 7.1. Three Goals That Cannot Be Used Interchangeably

- **Storage durability**: protecting data against failures within the scope the storage service is designed to handle.
- **Backup and recovery**: returning to an appropriate data copy after accidental deletion, logical corruption, or other incidents.
- **Availability**: continuing to serve or restoring service within the required timeframe.

A highly durable volume can still contain bad data written by an application. Retaining a volume after a machine failure may still require time to restore the service. An intact backup that has never been restored has not yet proven it meets recovery goals.

### 7.2. Boot Backup Does Not Replace Backups of Data on Other Volumes

If the operating system is on the Boot Volume and database data is on two Block Volumes, backing up only the boot volume does not protect the two data volumes. Likewise, backing up data volumes does not automatically include runtime configuration on boot or secrets managed in another service.

List all components required to restore the entire service:

| Component | Recovery Source to Identify |
| --- | --- |
| Operating system and application | Image, deployment configuration, or appropriate boot backup |
| Business data | Backup/replication and data recovery mechanism |
| Data spanning multiple volumes | Recovery copies with appropriate point-in-time relationship and consistency |
| Configuration, permissions, networking | Infrastructure configuration, policies, and operational runbooks |
| Encryption keys and secrets | Management service along with required access permissions |
| Data on local NVMe | Regeneration source or a copy stored elsewhere |

### 7.3. A Volume Copy Is Not Necessarily Application-Consistent

Operating systems, databases, and applications may hold data in memory or write across multiple steps. A block-level backup does not inherently understand whether a business transaction has completed.

For self-managed database software, use software-supported backup/restore procedures combined with quiescing or coordination mechanisms when needed. If data spans multiple volumes, evaluate cross-volume consistency and transaction state.

Volume group backup mechanisms, where appropriate, help coordinate at the storage layer but do not automatically replace application-consistent backup requirements. Do not treat a backup as a complete snapshot of running process memory.

### 7.4. Set Targets and Test Recovery

Two questions to answer:

- **RPO**: what is the maximum acceptable data loss measured in time?
- **RTO**: how quickly must the service be restored?

For example, if business data is generated continuously but backups only run daily, a requirement to lose no more than a few minutes of data needs additional appropriate mechanisms; you cannot conclude it is met just because a backup policy exists.

A recovery test should verify data, application startup capability, permissions, connectivity, and total completion time. For caches using local NVMe, cache warm-up time is also part of the recovery plan.

## 8. Security, IAM, and Cost

### 8.1. Encryption and Access Control Are Different Layers

OCI provides storage encryption for Boot Volumes and Block Volumes, with key management options according to service capabilities. Distinguish between encryption at rest and encryption in transit; do not infer one layer solely from the other being enabled.

Encryption at rest does not prevent an authorized application from reading data once the volume is attached and exposed to the operating system. You need to coordinate:

- IAM for creating, attaching, deleting, and managing backups/volumes.
- Key permissions when using customer-managed keys.
- Operating system permissions, service accounts, and file access rights.
- Secrets management and control over which software can read data.

Do not treat application NSGs or security lists as the sole mechanism deciding who can manage volumes via OCI APIs. Resource control-plane permissions and guest-OS data read permissions are different layers.

### 8.2. Remaining Volumes Still Need Management

Stopping an instance does not mean the associated Boot Volumes, Block Volumes, and backups stop incurring costs. Similarly, a detached volume is still a resource that requires management.

Track at least:

- Configured capacity and performance tiers.
- Volumes retained after instance termination or environment replacement.
- Backups, retention policies, and copies created.
- Owner, purpose, and data retention requirements.

Tags and compartments help organize ownership, but they do not replace deletion and retention policies. Before removing a resource, you must know whether it is still a required copy for recovery.

For local NVMe, cost and availability are tied to the Compute shape choice. Do not assume it is a free extra resource just because it is not managed as a separate Block Volume.

## 9. Example: Storage Layout for a Java Application on OCI

### 9.1. Context

A Java application receives document files, processes their contents, and stores business results in a separately deployed Oracle database service. The application can be replaced or scaled in when load decreases.

Data groups:

1. Operating system, JDK, agents, and application binaries.
2. User document files already confirmed as successfully uploaded.
3. Extracted files and intermediate data during processing.
4. Logs used for diagnostics and auditing as required.
5. Configuration and secrets to access services.

### 9.2. An Evaluable Layout Option

| Data Group | Illustrative Placement | Rationale and Conditions |
| --- | --- | --- |
| Operating system and base software | Boot Volume | Has a rebuild workflow from image/configuration and change management |
| Files confirmed to users | Appropriate durable storage, not only the processing host's local drive | Survives instance replacement or scale-in |
| Data requiring an instance's dedicated filesystem | Block Volume if truly required by architecture | Manage mounts, backups, and reattachment workflow during replacement |
| Regenerable intermediate files | Local NVMe if the shape has it and performance requires it | Has a primary data source and retry mechanism |
| Logs | Bounded local buffer, shipped to centralized storage as required | Does not depend entirely on a machine that will be terminated |
| Configuration and secrets | Appropriate configuration/secrets management mechanism | Does not rely on a single manually copied file on boot |

Block Volume is an option for block-level data, not the answer for every data type. If multiple instances need to access the same files, choose an appropriate storage interface and concurrency model instead of mounting the same read/write filesystem across all machines.

The fact that the application accesses an Oracle database does not mean you must buy local NVMe for the application server. Measure where actual I/O and latency occur before selecting hardware.

### 9.3. Failure Scenarios and Expected Outcomes

- **Processing host disappears mid-task**: original files remain intact; tasks can be picked up again and processed without producing incorrect duplicates.
- **Boot fills up due to logs**: detected via monitoring; logs are bounded and do not cause loss of the sole copy of business data.
- **Data volume is not mounted**: the application does not keep mistakenly writing to root as if everything were ready.
- **Instance is replaced**: software can be rebuilt, reconnected to data sources, and service restored according to plan.
- **Accidental deletion of business files**: a recovery option exists beyond keeping a filesystem that already reflects the deletion.

## 10. Practice: Reading Storage Information in Linux

If you have an authorized test Linux machine, the following read-only commands help correlate devices with filesystems. They do not create, format, or mount volumes; some tools may need to be preinstalled.

```bash
# View devices, filesystems, UUIDs, and mount points
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,UUID

# Identify the filesystem containing the root path
findmnt -T /

# View capacity and types of mounted filesystems
df -hT

# Replace this path with a data directory that actually exists on the machine
findmnt -T /srv/app-data
```

How to read the output:

1. Use `findmnt -T /` to identify the source of the root filesystem.
2. Use `lsblk` to see the relationship between devices, partitions, and storage layers, if any.
3. Use `findmnt -T` with the data path to identify the filesystem containing it.
4. Compare with the root filesystem: does the data truly reside on a separate volume?
5. Cross-reference with Boot Volume, Block Volume, and attachment details in OCI using supported identifiers.
6. Check filesystem capacity with `df`, not just device size in `lsblk`.

If the data directory does not have its own mount, `findmnt -T` may return the parent filesystem containing that directory. That is critical information for detecting unexpected writes to boot.

OS-level output does not fully confirm retention/deletion policies, backups, performance tiers, or local NVMe preservation rules. Those attributes must be cross-checked at the OCI service layer and in operational configurations.

Complete the following inventory sheet:

| Item | Details to Record |
| --- | --- |
| Path or device | Root, application data, logs, cache, temporary files |
| Actual resource type | Boot Volume, Block Volume, local NVMe, or other type |
| Identifiers | Volume/attachment in OCI and device identifier inside the guest machine |
| Lifecycle | On reboot, machine replacement, stop/start, terminate, or scale-in |
| Performance needs | Capacity, IOPS, throughput, latency, and measurement method |
| Durability | Where the primary data copy resides, whether it can be regenerated |
| Protection and recovery | Backup, regeneration source, RPO/RTO, and restore evidence |
| Permissions and cost | Owner, IAM, keys, retention, and retained resources |

## 11. Common Misconceptions

| Statement | Issue | Correct Understanding |
| --- | --- | --- |
| "Boot Volume only holds the OS, so there's no need to worry about data" | Applications, logs, or uploads might be writing to root | Verify actual paths and filesystems |
| "Successful attach means the application can use it immediately" | Device, filesystem, mount, and permissions are still needed | Verify end-to-end from attachment to application path |
| "Block Volume is a shared file drive for all machines" | Block devices do not automatically coordinate concurrent writes | Use concurrency mechanisms or an appropriate file service |
| "Local NVMe always loses data on reboot" | Behavior also depends on environment and operation | Check the specific lifecycle; do not guess |
| "Local NVMe kept data after reboot, so it can hold the sole copy" | Does not prove survival across host failure or termination | Protect data elsewhere or keep it regenerable |
| "A durable volume needs no backup" | Does not address accidental deletion or logical data corruption | Design backups and test recovery |
| "Boot backup protects the entire machine and data" | Data may live on other volumes/services | Inventory every component required for recovery |
| "Expanding a volume automatically gives the filesystem more space in all cases" | Device/partition/filesystem layers may require separate steps | Verify capacity at every layer |
| "A device named NVMe is definitely local storage" | Interface name is not enough to describe service lifecycle | Cross-reference resource source and OCI configuration |
| "Deleting an instance ends all storage costs" | Volumes and backups may still remain | Manage the lifecycle of each individual resource |

## 12. Self-Check

1. What is the main difference in role between Boot Volume and Block Volume? Why do both still need a recovery plan?
2. An application writes to `/srv/app-data`, yet `findmnt -T` shows the path resides on the root filesystem. What might have happened?
3. Why can't you infer the OCI storage type solely from `/dev/sdb` or a device name containing `nvme`?
4. Does attaching a Block Volume to two instances suffice to mount a standard filesystem read/write on both?
5. When is local NVMe a reasonable choice for intermediate files? What step must be completed before confirming results to the user?
6. Why is a volume data backup not guaranteed to be consistent at the application transaction level?
7. Why does 20,000 IOPS with 8 KiB I/O only equal about 156.25 MiB/s under a simple calculation?
8. After expanding volume capacity, which layers must be checked so the application actually gets more storage space?
9. If an instance is terminated, what information determines whether the Boot Volume and Block Volumes are kept or deleted?
10. What must the inventory sheet record so someone else can recover the application when the old host is no longer reachable?

An operable storage design must clearly state where data resides, which events it survives, how it is protected, and how long it takes to recover. Device names or high performance tiers do not substitute for these decisions.
