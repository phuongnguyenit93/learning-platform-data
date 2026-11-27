# Boot Disk, Data Disk, and Local Ephemeral Disk

A cloud virtual machine typically uses multiple types of disks. The operating system and boot components reside on the **boot disk**; application data resides on one or more **data disks**; temporary files, caches, and intermediate data can be placed on a **local ephemeral disk** attached to the physical host. These three disk types differ in purpose, lifecycle, performance, and data durability.

Choosing the wrong storage type can cause data to vanish when a VM is deleted, applications to start without required volumes, or the system to pay for performance beyond what it needs. This lesson explains how to distinguish the three disk types, manage their lifecycles, and select them based on workload.

This lesson belongs to the **Compute Storage** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute models from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security configurations; and how to deploy applications, scale workloads, ensure availability, and optimize operational costs. Understanding boot disks, data disks, and local ephemeral disks helps design data lifecycles that align with the compute lifecycle.

## 1. Disks in Cloud Environments

### 1.1. Block Storage and Storage Interfaces

In a virtual machine environment, disks are typically presented to the operating system as a **block device**. The operating system reads and writes data blocks by logical address. Administrators can create partitions, filesystems, volume managers, or use raw devices depending on application requirements.

Three interface types must be distinguished:

- **Block storage:** provides block-level devices for the operating system or application to manage filesystems and data.
- **File storage:** provides shared filesystems over protocols such as NFS or SMB.
- **Object storage:** stores objects by key and metadata via API; it is not attached as a standard block device without a separate gateway layer or driver.

Boot disks and data disks in this lesson are primarily block storage. Local ephemeral disks can also be exposed as block devices, but their data is tied to the lifecycle of the instance or physical host.

### 1.2. Volume Lifecycle

A disk can follow one of three lifecycle models:

- **Bound to the VM:** the volume is created and deleted together with the machine according to policy.
- **Managed independently:** the VM can be deleted while the volume persists so it can be attached to another machine.
- **Bound to the host:** data resides on local hardware and may be lost when the instance stops, migrates, or the host experiences a failure.

Do not infer lifecycle solely from the name "disk". Always inspect the delete-on-termination attribute, retention policy, volume type, and the specific service documentation.

## 2. Boot Disk

### 2.1. What Is a Boot Disk?

A **boot disk** is the disk containing the operating system and the components required for a VM to start. On Linux, it typically holds the bootloader, kernel, initramfs, root filesystem, and system packages. On Windows, it contains the boot partitions and the operating system partition.

A boot disk is typically created from a **machine image** or OS image. An image is the template used to create a disk; a boot disk is the concrete volume provisioned for a VM. An image may contain the operating system, initial configuration, and pre-installed software.

When a VM starts, virtual firmware or the platform's boot mechanism reads the boot components from the boot disk, and the operating system then loads and mounts the root filesystem.

### 2.2. Persistent Boot Disk vs. Ephemeral OS Disk

Many platforms provide boot disks as persistent block volumes. Data can survive VM stop or delete operations, depending on the deletion policy.

Some platforms offer an **ephemeral OS disk** or a mechanism to boot from local storage. The operating system is deployed on host-attached storage or local cache; changes on the boot disk may not be retained across certain lifecycle operations. You must verify behavior during stop, deallocate, reimage, resize, migrate, and host failure.

| Characteristic | Persistent boot disk | Ephemeral boot disk |
|---|---|---|
| Location | Storage volume managed according to cloud policy | Local storage or platform ephemeral mechanism |
| Lifecycle | Can survive VM deletion if the volume is retained | Typically tied to the VM/host and can be recreated from an image |
| Recovery | Can use snapshots, backups, or attach to another VM if supported | Typically recovered by recreating from an image and configuration |
| Best suited for | VMs that must retain OS changes or recover from disk | Immutable workloads, automated recreation, no unique data stored on the OS disk |

A persistent boot disk can still be deleted if delete-on-termination is enabled or an operator deletes the volume. An ephemeral OS disk is suitable when the system can rebuild the OS from an image and configuration. Always verify the provider's policy.

### 2.3. Designing a Boot Disk

When choosing a boot disk, consider:

- **Capacity:** sufficient for the OS, packages, system logs, agents, and update headroom.
- **Performance:** boot time, package updates, and system operations depend on IOPS and latency.
- **Filesystem:** OS images usually already configure an appropriate filesystem.
- **Encryption:** enable encryption at rest; verify key access permissions if using a customer-managed key.
- **Backup:** use golden images, snapshots, or backups based on recovery requirements.
- **Configuration management:** use cloud-init, configuration management, or an image pipeline to minimize manual changes.
- **Deletion policy:** determine whether the boot disk should be retained when the VM is deleted.

For immutable servers, software changes should be packaged into a new image or deployment. When rollback is needed, redeploying the previous image is usually easier to control than manually repairing a boot disk that has been modified many times.

### 2.4. Boot Disk Recovery

If a boot disk is corrupted or the operating system fails to boot:

1. Check VM status, console logs, and platform events.
2. Determine whether the issue lies in boot configuration, filesystem, kernel, drivers, or the volume itself.
3. If the volume is persistent and the platform supports it, take a snapshot before making repairs.
4. Create a rescue VM and attach the faulty boot disk as a data disk if you need to inspect the filesystem or retrieve logs.
5. Create a new boot disk from a verified snapshot or image if recovery is required.
6. Verify networking, IAM, startup scripts, agents, and application configuration before returning the VM to service.

Do not repair a filesystem while the disk is still being written to by another operating system. Bring the volume to a consistent state following the platform's procedure before performing offline inspection.

## 3. Data Disk

### 3.1. What Is a Data Disk?

A **data disk** is an additional disk used to store application data, databases, uploaded files, logs, queues, or content that must exist independently of the operating system.

Separating data from the boot disk clarifies lifecycle and capacity management. You can replace a VM or update the OS image while keeping the data volume to attach to the new machine, provided the volume policy allows it.

A VM can attach multiple data disks. Depending on the OS and application, they can be used individually, combined into logical volumes, configured in RAID, or mounted to different directories.

### 3.2. Benefits of Separating Boot Disk and Data Disk

- **Independent lifecycle:** replace or recreate the VM while retaining the data volume if policy permits.
- **Capacity management:** expand data capacity without resizing the boot disk.
- **Dedicated performance:** select volume types and IOPS/throughput tiers tailored to demand.
- **Targeted backups:** schedule snapshots or backups based on criticality.
- **Security:** apply separate encryption, key access permissions, and retention policies.
- **Portability:** detach the volume and attach it to another VM if zone, instance type, and filesystem constraints are met.

Separating disks does not automatically provide high availability. If there is only a single volume in a single zone, the volume can still be a single point of failure for the application. Check the storage service's redundancy and replication capabilities.

### 3.3. Data Disks by Workload

| Workload | Common layout | What to evaluate |
|---|---|---|
| Stateless Web/API | Boot disk for OS; data disk if local cache or files are needed | VM can be recreated; critical files should live in durable services |
| Database | Data disk for data files, logs, or WAL depending on design | IOPS, latency, throughput, durability, and backups |
| File upload | Data disk or file/object storage | Capacity, sharing across VMs, retention, and backups |
| Logging | Dedicated disk or centralized logging service | Capacity growth, write rate, rotation, and retention period |
| Batch processing | Data disk for input/output; local ephemeral for scratch | Retries, checkpoints, and reproducibility |
| Container host | Boot disk for OS/runtime; separate volume for persistent data | The writable layer should not be the sole storage location |

For databases, follow the DBMS guidelines on data layout, transaction logs, WAL, cache, and filesystem. Do not arbitrarily split across multiple disks or use RAID without understanding the impact on durability, write ordering, and recovery.

### 3.4. Zone and Region Scope

Persistent data disks are typically provisioned with either zonal or regional scope. A zonal volume may only be attachable to VMs in the same zone. If a VM fails, a replacement VM can be launched in that zone and reattached to the volume; however, if the entire zone goes down, the volume may become inaccessible.

Some services offer regional disks or replicated volumes that can support multiple zones through specific mechanisms. Never assume every persistent disk is automatically replicated across multiple zones.

During design, verify:

- Whether the volume is created in a zone or a region.
- Whether it can attach to a VM in another zone.
- Whether multi-attach is supported and across how many VMs.
- Replication and failover mechanisms.
- Which zones or regions snapshots/backups can be restored to.

## 4. Local Ephemeral Disk

### 4.1. What Is a Local Ephemeral Disk?

A **local ephemeral disk** is storage backed by local hardware on the physical host running the VM, typically SSD or NVMe. The platform may expose it as one or more block devices inside the VM.

Because it sits close to the CPU and does not necessarily traverse the network to a block storage system, a local disk typically offers low latency and high throughput/IOPS. It is well suited for temporary data, caches, scratch space, intermediate files, and regenerable data.

Data on a local ephemeral disk does not have the independent persistence guarantees of a persistent volume. Data may be lost during VM stop/deallocate, migration, resize, reimage, host failure, or instance recreation. The exact set of events depends on the provider and instance type.

### 4.2. Suitable Use Cases

Local ephemeral disks are suitable for:

- **Temporary files:** transient files created during processing.
- **Cache:** data that can be reloaded from a durable source.
- **Scratch space:** working area for batch jobs, ETL, image processing, or simulations.
- **Temporary database workspace:** intermediate data or regenerable indexes if supported by the application.
- **Temporary checkpoints:** checkpoints periodically flushed to persistent storage before job completion.
- **Build workspace:** build directories and intermediate artifacts that can be regenerated.

Do not use a local ephemeral disk as the sole copy of databases, user files, encryption keys, critical configurations, or unique checkpoints. Data that must be preserved must be copied to a persistent volume or durable storage service.

### 4.3. Lifecycle and Risks

A local ephemeral disk may survive certain reboot operations while losing data during others. Some platforms preserve data across soft reboots but wipe it on stop/deallocate; others have specific behaviors during live migration or host maintenance.

Distinguish between:

- **Reboot guest OS:** restarting the operating system inside the VM.
- **Stop/start:** stopping and starting the VM according to the cloud provider's semantics.
- **Deallocate:** releasing the compute host or capacity.
- **Resize:** changing the machine type or resources.
- **Reimage/recreate:** rebuilding the operating system or instance from an image.
- **Host failure/maintenance:** physical infrastructure faults or maintenance events.

Do not deduce whether data will persist or be lost solely from the operation's name. Check the instance type documentation and test in a non-critical environment.

### 4.4. Comparing Local Ephemeral and Persistent Data Disks

| Criterion | Persistent data disk | Local ephemeral disk |
|---|---|---|
| Location | Managed block storage service | Local storage device on the host |
| Durability | Can exist independently of the VM per policy | Tied to instance/host lifecycle; may be lost when instance state changes |
| Performance | Depends on volume type, storage network, and provisioned tier | Typically low latency, high throughput; depends on host and model |
| Attach/detach | Typically supported within service limits | Typically bound to the instance, not portable as an independent volume |
| Snapshot/backup | Typically supports service-level snapshots or backups | Data must be copied to durable storage |
| Purpose | Data to retain, databases, application files | Cache, scratch, temporary files, regenerable data |

A local disk is not inherently faster than every persistent disk. Benchmark on the actual instance and volume type; a properly provisioned persistent volume can outperform a host-constrained local disk.

## 5. Architecture Combining All Three Disk Types

A VM can use a boot disk, a data disk, and a local ephemeral disk simultaneously:

~~~mermaid
flowchart TB
    VM["Virtual Machine"]
    VM --> OS["Boot disk<br/>OS, kernel, agents"]
    VM --> DATA["Persistent data disk<br/>Database, uploads, application data"]
    VM --> TMP["Local ephemeral disk<br/>Cache, scratch, temporary files"]
    DATA --> SNAP["Snapshot / Backup"]
    TMP --> COPY["Copy data to keep<br/>to persistent storage"]
    SNAP --> RESTORE["Restore / Attach<br/>when replacing VM"]
~~~

Example of an image-processing server:

- The boot disk holds Linux, the runtime, and monitoring agents.
- The data disk holds the input file queue or application data that must be retained.
- The local ephemeral disk holds intermediate image files after decompression and processing buffers.
- Once processing finishes, results are written to a persistent data disk or object storage.
- If the VM is replaced, a new machine is created from the image and reattached to the data disk; scratch data is regenerated.

The application must be able to handle the loss of scratch data and rerun jobs when needed.

## 6. Attaching and Managing Data Disks in the OS

### 6.1. General Procedure

After creating a volume and attaching it to a VM, the operating system must recognize the device. Common workflow:

1. Create a volume with the appropriate capacity, performance tier, zone, and encryption.
2. Attach the volume to the VM.
3. Verify the new device appears in the operating system.
4. If it is a new blank disk, create a partition or filesystem.
5. Mount it to the application directory.
6. Configure persistent mounting across reboots.
7. Verify permissions, ownership, filesystem, and read/write capability.
8. Configure monitoring, backups, and capacity alerts.

Never run a format command on a disk that already contains data. Identify the new device by size, serial, volume ID, or stable path before taking action.

### 6.2. Linux Example

List block devices and filesystems:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
~~~

Inspect identifiers and filesystems:

~~~bash
sudo blkid
~~~

Suppose `/dev/nvme1n1` is a brand-new disk, just attached and verified to contain no data that needs to be kept. You can create an ext4 filesystem:

~~~bash
sudo mkfs.ext4 /dev/nvme1n1
sudo mkdir -p /data
sudo mount /dev/nvme1n1 /data
~~~

**Note:** `mkfs.ext4` creates a new filesystem and can destroy existing data. Only run it on a verified blank disk. For disks that already have partitions, you typically need to use the partition device such as `/dev/nvme1n1p1` rather than formatting the entire disk.

To mount automatically after reboot, obtain the UUID:

~~~bash
sudo blkid -s UUID -o value /dev/nvme1n1
~~~

After confirming the UUID, add a corresponding line to `/etc/fstab`:

~~~fstab
UUID=REPLACE_WITH_UUID /data ext4 defaults,nofail 0 2
~~~

Replace `REPLACE_WITH_UUID` with the actual UUID. `nofail` allows the system to continue booting if the volume is unavailable; for applications that strictly require `/data`, add a systemd dependency or health check so the service does not accidentally write data into an empty directory on the root disk.

Verify the configuration before rebooting:

~~~bash
sudo findmnt --verify
sudo mount -a
findmnt /data
df -h /data
~~~

Then set directory ownership and permissions for the service account. Do not grant overly permissive write permissions such as `777` without a clear requirement.

### 6.3. Device Names Can Change

Device names such as `/dev/sdb` or `/dev/nvme1n1` can change when a VM reboots, additional disks are attached, or the instance type changes. Avoid using transient device names in mount configurations if the platform provides a UUID, filesystem label, or stable path under `/dev/disk/by-id`.

With NVMe, device names may reflect how the cloud provider maps volumes. Use metadata or the serial number to match the exact volume ID before taking action.

### 6.4. On Windows

On Windows Server, a new disk typically appears in Disk Management or via PowerShell. The standard process includes:

1. Identify the new disk by capacity and status.
2. Bring the disk online if needed.
3. Initialize the GPT partition style where appropriate.
4. Create a volume and format the filesystem such as NTFS or ReFS per application requirements.
5. Assign a drive letter or mount point.
6. Configure NTFS permissions and verify application access.
7. Verify the volume appears after a reboot.

Only initialize and format a disk verified to be new. If the disk holds data from an old machine, inspect its status and filesystem before writing.

## 7. Performance and Choosing Volume Types

### 7.1. Key Metrics

Storage performance is typically evaluated by:

- **IOPS (Input/Output Operations Per Second):** number of read/write operations per second.
- **Throughput:** amount of data transferred per second, usually measured in MB/s or GB/s.
- **Latency:** time taken to complete a single I/O operation.
- **Queue depth:** number of I/O requests waiting or currently being processed.
- **Block size:** size of each read/write operation.
- **Read/write mix:** ratio of reads to writes in the workload.

High IOPS does not automatically mean high throughput. With small block sizes, a workload may be IOPS-bound; with large block sizes, it may be throughput-bound. High latency can slow down a database even when total throughput has not reached its limit.

### 7.2. Common Storage Categories

| Storage category | Characteristics | Typical matching workloads |
|---|---|---|
| General-purpose SSD | Balances cost, IOPS, and throughput; may have burst credits | Boot disks, web/API, general-purpose applications |
| Provisioned IOPS SSD | Allows selecting high or consistent IOPS per service tier | Transactional databases, random I/O workloads |
| Throughput-optimized HDD/SSD | Optimized for sequential throughput or cost per capacity | Batch jobs, data processing, logging |
| Cold/archive storage | Low cost for infrequently accessed data; higher retrieval latency or restore required | Long-term backups, rarely accessed data |
| Local NVMe/instance store | Local device, low latency, high performance; ephemeral lifecycle | Scratch, cache, temporary data |

Volume type names, performance tiers, burst mechanisms, and pricing vary across providers. Check both per-volume limits and aggregate instance limits, as a VM may have an IOPS or throughput cap lower than the sum of its attached disks.

### 7.3. Choosing by Access Pattern

- OLTP databases typically have many small, random I/Os, making latency and IOPS critical.
- Data warehouses or batch scans typically read large blocks, so sequential throughput may matter more.
- Continuous log writing requires evaluating write throughput, durability, and rotation policies.
- Boot disks need consistent boot and update times, but usually do not require the highest IOPS profile.
- Caches and scratch space can leverage local NVMe if the data can be regenerated.

Benchmarks should use realistic load patterns: block size, read/write ratio, queue depth, thread count, and duration. Short test runs may be skewed by caches or burst credits and fail to represent sustained load.

### 7.4. Combining Multiple Disks

Multiple disks can be combined using LVM, RAID, or storage pools to increase capacity or performance. However:

- RAID 0 can increase aggregate throughput/IOPS but offers no redundancy; a single disk failure can lose the entire array.
- RAID 1/10 can increase fault tolerance or read performance depending on configuration, at the cost of extra capacity.
- LVM provides flexible capacity management but does not inherently provide replication or backup.
- A snapshot of a single disk does not automatically guarantee consistency across multiple disks if the application writes concurrently.

For databases or critical workloads, only use RAID and multi-disk layouts in accordance with OS, database, and cloud provider guidance. Never treat RAID as a substitute for backups.

## 8. Snapshots, Backups, and Data Recovery

### 8.1. What Is a Snapshot?

A **snapshot** is a point-in-time record of a volume's state, typically managed by the cloud storage service. Depending on the platform, snapshots can be used to create new volumes, restore data, or create images.

Snapshots are useful for point-in-time backups, but they do not automatically guarantee the application is in a consistent state. If the OS or database is actively writing, a snapshot may only reflect a crash-consistent state.

### 8.2. Crash-Consistent vs. Application-Consistent

- **Crash-consistent snapshot:** similar to the disk state when a machine abruptly loses power. The filesystem or database may need to replay journals/logs upon startup.
- **Application-consistent snapshot:** the application is prepared before the snapshot—for example, flushing buffers, freezing the filesystem, or using the database's backup mechanism to ensure data consistency.

For databases, use backup tools or integrated snapshot mechanisms supported by the DBMS. If data spans multiple volumes, coordinate snapshots to preserve relationships among data files, transaction logs, and metadata.

### 8.3. Backups Are Not Snapshots

Snapshots are typically tied to the volume service and may share dependencies within the same region or account. Backups may include retention policies, catalogs, cross-region copies, encryption keys, and dedicated restore workflows.

Define:

- Backup frequency and retention period.
- Workload RPO and RTO.
- Whether copies exist in another region or account.
- Who has permission to delete backups and snapshots.
- Whether encryption keys remain accessible during recovery scenarios.
- Whether restoration to a new volume or VM is possible.
- Post-restore data verification procedures.

A backup is only useful once you have tested restoring it and verified that the application works with the recovered data.

### 8.4. Data Disk Recovery Procedure

1. Identify the snapshot/backup to restore and the target point in time.
2. Create a new volume from the selected copy.
3. Choose the zone and volume type matching the destination VM.
4. Attach the new volume to a rescue VM or application VM.
5. Inspect the filesystem, UUID, partitions, and permissions.
6. If it is a database, perform recovery according to the DBMS documentation.
7. Verify data integrity and application functionality.
8. Cut over traffic or the application to the restored volume.
9. Record the actual recovery time and update the runbook.

Do not overwrite the original volume before verifying the restored copy. Retain the original volume according to investigation or rollback policies if needed.

## 9. Security and Lifecycle Management

### 9.1. Encryption

Block volumes can support encryption at rest using provider-managed or customer-managed keys. Verify that:

- Boot disks, data disks, and snapshots are all encrypted per policy.
- Key usage permissions are properly granted to the VM, service, or recovery account.
- Keys are not disabled or deleted before the data retention period expires.
- Snapshots or cross-region copies preserve encryption policies or are reconfigured as required.
- Data in transit between the VM and the storage service is protected per requirements.

Volume encryption does not replace filesystem access controls. Applications still require proper file permissions, service accounts, and secret management.

### 9.2. Safe Attach and Detach

Before detaching a data disk from a Linux VM:

1. Stop applications writing to the disk.
2. Flush buffered data.
3. Unmount the filesystem.
4. Verify the device is no longer in use.
5. Perform the detach from the cloud control plane.
6. Check the volume status before attaching it to another VM.

You can use `sync`, `fuser`, or `lsof` to assist with verification. Never detach a volume while a database or filesystem is still writing, as this can cause data corruption.

On Windows, stop services using the volume and take the disk offline following the proper procedure before detaching.

### 9.3. Multi-Attach and Shared Filesystems

Some volume types support simultaneous attachment to multiple VMs, though this capability has limits regarding volume type, VM count, zone, and operating system. Multiple VMs seeing the same block device does not mean a standard filesystem can be safely written to concurrently by multiple machines.

Filesystems like ext4 or NTFS are generally not designed to be mounted read-write by multiple hosts on the same block device without proper clustering mechanisms. Use a clustered filesystem, distributed locking, or a file storage service designed for concurrent access.

If the application simply needs multiple VMs to read and write files concurrently, NFS, SMB, or object storage may be more suitable than multi-attach block storage.

### 9.4. Volume Deletion and Data Protection

When deleting a VM, know whether attached volumes will be retained or deleted alongside it. Policies may differ between boot disks and data disks, or across instance types.

Before deleting resources:

- Check delete-on-termination and retention policies.
- Verify the volume is no longer in use by any application.
- Create a backup if the data needs to be kept.
- Verify that the snapshot can be restored.
- Confirm data retention requirements and internal compliance rules.
- Record the volume ID and owner to avoid accidental deletion.

Cleaning up unused volumes reduces costs, but requires an inventory, owner tags, and an approval process for critical data.

## 10. Choosing Disk Types by Need

| Need | Boot disk | Data disk | Local ephemeral disk |
|---|---|---|---|
| Holding the OS | Suitable | Not primary purpose | Can be used for ephemeral OS disk if supported by platform |
| Application data to retain | Should not be used as sole location if separable | Suitable | Not suitable as sole copy |
| Database | Only if architecture explicitly requires | Suitable with proper performance and durability | Only for cache/scratch or recoverable data |
| Regenerable cache | Possible but usually wastes boot storage | Can be used if longer retention is needed | Very suitable if performance and lifecycle fit |
| Scratch/batch temporary | Should not be used as large temporary space | Can be used | Suitable |
| VM recovery | Boot disk image/snapshot | Attach or restore volume | Regenerate data from durable source |
| Moving between VMs | Subject to volume and zone capabilities | Usually supports attach/detach within service limits | Usually tied to instance/host |

Production servers can use a boot disk sized appropriately for the OS, one or more data disks for persistent data, and local ephemeral disks for caches or scratch space. Stateless workloads can favor immutable boot disks and store data in services outside the VM.

## 11. Design Examples

### Example A: Stateless Web Server

A fleet runs multiple identical web VMs. Boot disks are created from a golden image containing the OS, runtime, and agents. Uploaded files are stored in object storage or a shared file service; temporary caches can reside on local ephemeral disks.

When a VM fails, autoscaling provisions a new VM from the image. Cache recovery is unnecessary because the application can repopulate it. Important logs are shipped to a centralized logging system rather than kept solely on local disk.

### Example B: Database on a VM

A database VM has a persistent boot disk for the OS and a high-performance data disk for database files. Transaction logs or WAL may reside on a separate volume if required by the database and design guidelines. Backups are created using database tools and stored independently of the VM.

Operations teams monitor latency, IOPS, throughput, queue depth, and free space. When VM replacement is needed, the data volume can be reattached according to zone constraints and recovery procedures. Local ephemeral disks are used only for caches or regenerable intermediate data.

### Example C: Large-Scale Batch Data Processing

A worker downloads input from object storage, processes it on local NVMe, and writes results back to persistent storage. The job takes periodic checkpoints so it can resume after instance replacement.

If the local ephemeral disk loses data, the scheduler reruns the job or re-downloads the input. This design leverages local storage speed without relying on temporary data persisting forever.

### Example D: Replacing a VM While Keeping the Data Volume

An older VM needs an OS upgrade. The team snapshots the data disk, launches a new VM from a golden image, attaches the volume in the matching zone, and mounts it by UUID. The application is validated against the data before cutting over traffic.

Once the new VM runs stably, the team handles the old VM per policy. If rollback is needed, the data volume and snapshot still provide a controlled recovery path.

## 12. Common Mistakes

**Assuming every boot disk is persistent.** Some platforms support ephemeral OS disks or policies that delete the boot volume with the VM. Check disk type and deletion behavior.

**Storing the sole copy of data on a local ephemeral disk.** Data can be lost when the instance or host changes. Use local disks only for regenerable data or data already replicated to durable storage.

**Formatting a disk that contains data.** Filesystem creation commands can destroy data. Always verify volume ID, size, partitions, and filesystems before formatting.

**Using fixed device names like `/dev/sdb`.** Device ordering can change. Prefer UUIDs or stable paths for mounting.

**Creating snapshots without testing restores.** A snapshot does not prove the application can recover properly. Rehearse and validate data after restoring.

**Assuming snapshots are always application-consistent.** Snapshots taken while a database is writing may only be crash-consistent. Use backup or quiesce mechanisms supported by the application.

**Detaching a disk while applications are still writing.** This can corrupt filesystems or database data. Stop the application, flush, and unmount before detaching.

**Using multi-attach with unsupported filesystems.** Multiple VMs mounting a standard filesystem read-write simultaneously can corrupt data. Use a clustered filesystem or appropriate shared file service.

**Looking only at capacity and ignoring performance.** A volume with enough GB but insufficient IOPS or throughput can still slow down the application. Benchmark using realistic I/O patterns.

**Treating RAID as a backup.** RAID can improve performance or disk fault tolerance, but it does not protect against accidental deletion, application bugs, or zone-wide outages.

## 13. Pre-Deployment Checklist

- [ ] Identify which data belongs on the boot disk, data disk, and local ephemeral disk.
- [ ] Verify the lifecycle of each disk type during stop, deallocate, resize, delete, and host failure.
- [ ] Define delete-on-termination and retention policies.
- [ ] Choose capacity, IOPS, throughput, and volume type based on the workload.
- [ ] Verify zone/region scope and attach/detach capabilities.
- [ ] Enable encryption at rest and verify key access permissions.
- [ ] Configure filesystems and mount using UUIDs or stable identifiers.
- [ ] Format new disks only after verifying no data needs to be retained.
- [ ] Configure backups/snapshots, retention, and independent copies where needed.
- [ ] Determine whether crash-consistent or application-consistent backups are required.
- [ ] Test restoring both boot disks and data disks following the runbook.
- [ ] Stop applications, flush, and unmount before detaching.
- [ ] Verify multi-attach and filesystem support before allowing concurrent multi-VM access.
- [ ] Monitor capacity, latency, IOPS, throughput, and I/O errors.
- [ ] Define how local ephemeral data is regenerated after VM replacement.

## 14. Key Takeaways

- A **boot disk** contains the operating system and boot components; its lifecycle may be persistent or ephemeral depending on the platform.
- A **data disk** stores application data and can be managed independently of the VM to support machine replacement or recovery.
- A **local ephemeral disk** is typically fast and suited for caches, scratch space, and temporary files; data is tied to the instance or host and may be lost.
- Distinguish block, file, and object storage to choose the right storage interface.
- Select volumes based on IOPS, throughput, latency, block size, and access pattern—not capacity alone.
- Snapshots and backups must be verified via restore procedures; databases may require application-consistent backups.
- Attach/detach operations must be performed after applications stop writing and filesystems are unmounted.
- Multi-attach is safe only when the volume, filesystem, and application support concurrent access.
- Good design places data that must be kept on persistent storage and uses local ephemeral disks only for regenerable data.

## Glossary

| Term | Meaning |
|---|---|
| Boot disk | A disk containing the operating system and components required for a VM to boot. |
| Data disk | An additional disk used to store application data. |
| Local ephemeral disk | Local storage tied to the VM or host with a temporary lifecycle. |
| Persistent volume | A volume that can exist independently of the VM lifecycle per service policy. |
| Block storage | Storage presenting block-level devices to the operating system or application. |
| Machine image | A template used to create a boot disk or virtual machine. |
| Attach / detach | Connecting or disconnecting a volume from a VM. |
| Filesystem | The structure that manages files and directories on a block device. |
| UUID | A unique identifier of a filesystem or device provided by the operating system. |
| IOPS | Input/Output Operations Per Second. |
| Throughput | The amount of data transferred per unit of time. |
| Latency | The time taken to complete a single I/O operation. |
| Snapshot | A point-in-time record of a volume's state. |
| Crash-consistent | A snapshot state equivalent to an abrupt power loss or crash. |
| Application-consistent | A snapshot taken after the application prepares its data to ensure consistency. |
| Delete-on-termination | A policy that deletes a volume when its VM is deleted or terminated. |
| Multi-attach | The ability to attach a single volume to multiple VMs simultaneously if supported by the service. |
| RAID | A method of combining multiple disks to improve performance, capacity, or fault tolerance. |
| Headroom | Reserve capacity or capability to accommodate growth and fluctuations. |
