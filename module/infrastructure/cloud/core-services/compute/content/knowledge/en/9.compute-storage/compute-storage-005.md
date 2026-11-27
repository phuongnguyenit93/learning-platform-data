# Safely Attaching, Detaching, and Resizing Volumes

A volume is a block-level storage unit that can be attached to a compute instance so the operating system can use it like a disk device. On cloud infrastructure, volumes are typically provisioned independently of the VM lifecycle, allowing capacity expansion, machine replacement, or data recovery according to service policy. However, attach, detach, or resize operations in the control plane are only part of the workflow. The operating system and applications must also recognize the right device, manage the filesystem, and close I/O operations safely.

In **CLOUD_CORE_SERVICES_COMPUTE**, proper volume management ensures VMs have adequate capacity for applications, databases, and operational data while minimizing data loss, filesystem corruption, or service disruption. Design must account for storage type, availability zone, IOPS/throughput performance, encryption, snapshots, backups, access permissions, and recovery procedures.

## 1. Volumes in Compute Infrastructure

Volumes are typically provided as block storage. Once attached to a VM, the operating system detects a block device; administrators can create partitions, filesystems, and mount points, and grant permissions to applications.

Key concepts to distinguish:

- **Volume:** a platform-managed block storage resource with its own capacity and performance characteristics.
- **Disk/device:** the device visible to the operating system after the volume is attached.
- **Partition:** a logical region carved on a disk device.
- **Filesystem:** the structure managing files and directories, such as ext4, XFS, or NTFS.
- **Mount point:** the directory where a filesystem is attached in the Linux directory tree; on Windows, volumes are usually assigned a drive letter or mounted to a directory.
- **Snapshot:** a point-in-time capture of volume state provided by the cloud mechanism.
- **Backup:** a recovery copy, usually carrying retention policies and more independent protection than a typical snapshot.

Not every type of storage is a volume. Object storage is accessed via API to store objects; file storage provides file-sharing interfaces such as NFS or SMB; local/ephemeral disks are tied to the host and have a different lifecycle from persistent block volumes. Choosing the right storage type upfront prevents using block volumes for file-sharing needs or local disks as the sole store for persistent data.

### 1.1. Block Volumes vs. Local/Ephemeral Disks

| Characteristic | Persistent block volume | Local/ephemeral disk |
| --- | --- | --- |
| Storage location | Provider's storage system | Local device on the host or physical server |
| Lifecycle | Can exist independently of the VM if retention is configured | Typically tied to the VM/host lifecycle |
| Latency | Depends on backend and storage access path | Typically low due to proximity to CPU and memory |
| Detach/reattach capability | Usually supported within platform limits | May not be supported or have equivalent semantics |
| Data when host/VM is replaced | Usually preserved if the volume is retained | May be lost |
| Use cases | OS/data disks, databases, data requiring persistent storage | Caches, scratch space, regenerable temporary data |

Before acting, clearly identify which volumes hold data to keep and which hold only temporary data. Do not infer data durability solely from a device name or the fact that the operating system displays a disk.

### 1.2. Limits to Verify

Volume attachment capabilities depend on:

- The region or zone where the volume is created and the VM's location.
- The maximum number of volumes supported by the VM or instance type.
- The protocol type and device model exposed by the platform.
- Multi-attach support and concurrent usage conditions.
- Maximum volume size, IOPS, throughput, and aggregate VM-level limits.
- Whether the volume type supports encryption, snapshots, and online resizing.

Some volumes can only attach to VMs in the same availability zone. Some services support sharing a volume across multiple machines, but only with specific volume types, filesystems, and locking mechanisms. Never assume two VMs can mount the same standard filesystem concurrently in read/write mode without corrupting data.

## 2. Attaching a Volume

Attaching is the operation that links a volume to a compute instance. Even after the provider reports completion, the operating system may take a moment to detect the device. The device name requested in the control plane may also differ from the actual name inside the guest OS, especially with NVMe devices.

General workflow:

1. Identify the target VM, zone, volume ID, and intended use.
2. Check that the volume is in an attachable state and not bound contrary to policy.
3. Verify zone, machine type, attachment limits, and IAM permissions.
4. Attach the volume via console, API, CLI, or IaC tool.
5. Wait for the attach operation to complete in the control plane.
6. Rescan devices in the operating system and identify the exact volume by ID/serial/UUID.
7. If it is a new volume, create partitions and a filesystem per design; if the volume holds existing data, verify the existing filesystem and mounts.
8. Mount it at the appropriate path, set permissions, and configure persistent mounting if needed.
9. Verify the application can read/write and I/O metrics look normal.

### 2.1. Identifying Devices in Linux

Names like `/dev/sdf`, `/dev/xvdf`, or `/dev/nvme1n1` are not always stable across reboots or instance types. Cross-reference provider metadata with the serial number, volume ID, or stable links under `/dev/disk/by-id/`.

Common inspection commands:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,UUID
sudo blkid
sudo dmesg | tail -n 50
~~~

Before running **mkfs**, confirm the device is genuinely a new volume containing no data to preserve. Filesystem creation commands can overwrite metadata from a previous filesystem.

### 2.2. Initializing a New Volume on Linux

The illustrative example below assumes `/dev/disk/by-id/DEVICE_ID` is a verified new, blank device. Replace device names and paths to match your actual environment.

~~~bash
# Verify the device before making changes
lsblk -f /dev/disk/by-id/DEVICE_ID

# Create a filesystem directly on the device (if no partition is needed)
sudo mkfs.ext4 /dev/disk/by-id/DEVICE_ID

# Create mount point and mount
sudo mkdir -p /data
sudo mount /dev/disk/by-id/DEVICE_ID /data

# Verify
findmnt /data
df -hT /data
~~~

For volumes requiring a partition table, create partitions using an appropriate tool such as `parted` or `fdisk`, then create the filesystem on the partition, such as `/dev/nvme1n1p1`. Choosing GPT/MBR, alignment, and partition sizes must follow OS and capacity requirements.

### 2.3. Automatic Mounting After Reboot

To mount a filesystem automatically at boot, Linux typically uses `/etc/fstab`. Reference a UUID or stable identifier instead of `/dev/sdX` names that can shift.

~~~bash
sudo blkid
~~~

Example configuration line:

~~~fstab
UUID=FILESYSTEM_UUID  /data  ext4  defaults,nofail  0  2
~~~

The **nofail** option allows the machine to continue booting when an optional volume is unavailable, though it is not suitable for every mount point. If an application strictly requires `/data`, configure service dependencies so the application does not start when the filesystem is unmounted. Otherwise, the application might mistakenly write data into the `/data` directory on the root filesystem.

After editing, test the configuration before rebooting:

~~~bash
sudo mount -a
findmnt --verify
~~~

Never add an untested fstab entry to a production machine; syntax errors or an incorrect UUID can disrupt the boot process.

### 2.4. Attaching a Volume on Windows

After attaching a volume in the control plane, Windows may require rescanning disks in Disk Management or the corresponding administrative tool. For a new volume:

1. Open Disk Management and confirm the right disk by capacity and status.
2. If the new disk is Offline or Not Initialized, bring it online and initialize it per GPT/MBR policy.
3. Create a New Simple Volume, choose the size, and assign a drive letter or mount path.
4. Format with a supported filesystem, typically NTFS or ReFS depending on requirements.
5. Set a volume label, configure NTFS permissions, and test application access.

If the volume already holds data, do not initialize or reformat it. Verify the filesystem, disk status, and drive letter before putting it into service.

## 3. Safely Detaching a Volume

Detaching disconnects a volume from a VM in the control plane. If the OS or application is still writing data, a forced detach can cause filesystem corruption, data loss, or database damage.

Safe workflow:

1. Identify the applications, processes, and mount points using the volume.
2. Stop accepting new work and drain requests if the volume serves a live application.
3. Complete transactions, flush data, or trigger a checkpoint per application documentation.
4. Stop services using the volume if needed.
5. Verify no processes hold open files or have their current working directory on the mount point.
6. Unmount the filesystem inside the guest OS.
7. Verify the device is no longer mounted and no I/O is occurring.
8. Trigger the detach from the control plane and wait for completion.
9. Verify the volume still exists, is in the expected state, and can be reattached when needed.

### 3.1. Pre-Unmount Checks on Linux

~~~bash
findmnt /data
sudo fuser -vm /data
sudo lsof +f -- /data
~~~

If a process is using the filesystem, identify the service and stop it following the application's shutdown procedure. Do not use **umount -l** or **umount -f** as a default workaround to bypass active processes; these flags can mask ongoing I/O state and introduce data corruption risks.

Once the application has stopped and the filesystem is idle:

~~~bash
sync
sudo umount /data
findmnt /data
~~~

If `umount` reports `target is busy`, find every process still referencing the mount point—including shells sitting inside that directory, container bind mounts, or background services. Resolve the cause and try again.

### 3.2. Detaching a Volume on Windows

On Windows, close applications and open handles using the volume, stop dependent services, and take the disk offline or eject it per provider instructions before detaching. Never remove a disk while a database or application is still writing.

If the volume has multiple partitions or drive letters, verify all mount paths have been released. For clusters or shared disks, follow cluster ownership transfer and locking procedures before detaching from a node.

### 3.3. Operating System Volumes

OS/root volumes may follow special rules. Many platforms prohibit detaching a root disk while the VM is running; some allow swapping the root disk when stopped or under a dedicated recovery workflow. Do not apply data-disk detach procedures to a root volume without verifying platform support.

## 4. Resizing a Volume

Resizing typically involves two layers:

1. **Increasing volume size in the control plane:** requesting the provider to expand the block device.
2. **Expanding structures inside the guest OS:** updating partitions, physical volumes, logical volumes, and the filesystem so the OS can use the added capacity.

Increasing size in the console/API alone does not automatically enlarge the filesystem. Conversely, trying to expand a partition before the provider finishes resizing will not expose the new capacity.

### 4.1. Before Resizing

Before changing capacity:

- Verify the volume ID, VM, filesystem, and current size.
- Check whether the volume type supports online resizing or requires stopping the VM.
- Check maximum capacity, minimum increment, and rate limits on modifications within a time window.
- Evaluate whether IOPS/throughput scales with capacity or needs separate configuration.
- Verify the latest snapshot/backup and confirm restore capability.
- Check whether the filesystem and partition layout support online expansion.
- Estimate completion time for both the provider operation and filesystem expansion.
- Schedule a maintenance notice if the workload must stop or performance may be impacted.

Snapshots do not replace independent backups. For critical data, maintain verified backups and a recovery plan before altering disk structures.

### 4.2. Expanding a Volume and Filesystem on Linux

Suppose a volume is expanded from 100 GiB to 200 GiB in the control plane. Rescan the device in the OS if the new size is not detected automatically:

~~~bash
lsblk
sudo blockdev --getsize64 /dev/nvme1n1
~~~

If the filesystem sits directly on the entire block device, expand the filesystem according to its type:

~~~bash
# ext4: can be expanded while the filesystem is mounted
sudo resize2fs /dev/nvme1n1

# XFS: expand using the active mount point
sudo xfs_growfs /data
~~~

Use the command matching the actual device and filesystem. **resize2fs** does not work on XFS; **xfs_growfs** takes the mount point of the XFS filesystem.

### 4.3. Expanding a Partition Before the Filesystem

If the volume is partitioned, expand the partition holding the filesystem after the block device grows. On some Linux distributions, **growpart** handles this:

~~~bash
# Example: expand partition 1 on /dev/nvme1n1
sudo growpart /dev/nvme1n1 1

# Then expand the corresponding filesystem
sudo resize2fs /dev/nvme1n1p1
~~~

For XFS on a partition, run **xfs_growfs** on the mount point after extending the partition. Verify the exact partition name; NVMe devices typically use a `p1` suffix, while other devices use forms like `s1` or `1`.

Never run grow commands on an unverified device. If the partition table or filesystem reports errors, halt and verify backups before proceeding.

### 4.4. Expanding an LVM-Backed Volume

With Linux Logical Volume Manager (LVM), the stack typically follows:

**Volume block device → Partition (if any) → Physical Volume (PV) → Volume Group (VG) → Logical Volume (LV) → Filesystem**

After the provider expands the disk, extend the partition if present, then update the PV and LV:

~~~bash
# Verify the layout first
sudo pvs
sudo vgs
sudo lvs

# If the PV sits on a partition, expand the partition first
# Then instruct LVM to recognize the new capacity
sudo pvresize /dev/nvme1n1p1

# Extend both the LV and filesystem together if the filesystem supports it
sudo lvextend -r -L +50G /dev/vg_data/lv_app
~~~

This example assumes the volume group has sufficient extents and the PV/LV paths match. **lvextend -r** invokes the appropriate filesystem resize tool; inspect the output and confirm capacity afterward. If you omit `-r`, you must manually expand the filesystem after extending the LV.

### 4.5. Expanding a Volume on Windows

After the provider expands the disk:

1. Run Rescan Disks in Disk Management or the administrative console.
2. Verify the new capacity appears as Unallocated space immediately adjacent to the partition to expand.
3. Use Extend Volume if the disk layout and filesystem support it.
4. Verify the new capacity, filesystem, and volume status.

If another partition, recovery partition, or special layout sits between the free space and the data partition, Extend Volume may be unavailable. Never delete a partition just to make space contiguous without confirming its role and recoverability.

## 5. Shrinking Volumes and Changing Volume Types

Expansion is far more widely supported than shrinking. Many block storage services forbid shrinking a volume directly because truncating the block device can slice off data at the end of the disk.

If you must reduce capacity:

1. Create a new volume at the target smaller size.
2. Create a filesystem and mount it on the target machine.
3. Copy data with an appropriate tool, preserving permissions, ownership, ACLs, and metadata.
4. Pause writes or run a final sync pass to avoid missing updates.
5. Verify checksums, file counts, permissions, and application behavior.
6. Switch mounts or application configuration to the new volume.
7. Retain the old volume for a rollback window before deleting per policy.

Never attempt to shrink a volume to downsize a filesystem if the provider does not support shrinking or you have not checked filesystem constraints. Changing volume type, IOPS, or throughput may also carry specific preconditions and apply durations; check the modification/optimization state before triggering subsequent changes.

## 6. Snapshots, Backups, and Data Consistency

A snapshot typically captures a volume at a point in time via the provider's mechanism. Snapshot consistency depends on whether the application and OS are actively writing during capture.

Distinguish between:

- **Crash-consistent snapshot:** equivalent to the state after an abrupt power loss; the filesystem or application may require recovery on restore.
- **Filesystem-consistent snapshot:** the filesystem is flushed or frozen via a supported mechanism prior to taking the snapshot.
- **Application-consistent backup:** the application coordinates to bring data into a recoverable state, such as via a database checkpoint or backup API.

For databases or multi-volume systems, snapshotting individual volumes at slightly different times can produce an inconsistent dataset. Use multi-volume consistent snapshot mechanisms or application-level backups when the workload requires it.

Controlled snapshot workflow:

1. Verify the application and volume type support snapshotting.
2. Flush data or invoke quiesce/checkpoint hooks per application guidelines.
3. Take the snapshot or backup.
4. Wait for completion and verify metadata.
5. Record retention, encryption key, and access permissions.
6. Periodically test restoring to an isolated volume or environment.

Never treat a successful snapshot creation as proof that a backup can restore cleanly. Only a restore test validates the end-to-end recovery process.

## 7. Encryption, Access Control, and Volume Protection

Volumes can hold application data, user records, or sensitive information. Apply protection from creation through deletion:

- Enable encryption at rest per policy; verify whether keys are provider-managed or customer-managed.
- Restrict attach, detach, snapshot, copy, and delete permissions via IAM/RBAC.
- Do not share volumes or snapshots across accounts without explicit permission controls.
- Use encryption keys with appropriate rotation, backup, and usage policies.
- Protect data in transit over the network using platform-supported encryption mechanisms.
- Log all volume actions and permission changes.
- Delete or revoke keys following data retention schedules to avoid rendering recoverable backups unreadable.

Detaching a volume does not erase its data, nor does it revoke snapshot access permissions. When handing a volume off to another team, consider wiping data, provisioning a fresh volume from a clean image, or following an organization-approved sanitization process.

## 8. Attaching the Same Volume to Multiple Machines

Some services offer multi-attach or shared block storage, yet exposing a block device to multiple machines does not automatically make a filesystem safe.

If two machines mount a standard filesystem such as ext4 or XFS in read/write mode simultaneously, each kernel updates metadata independently and corrupts the filesystem. Multi-attach requires a cluster-aware filesystem, distributed locking, or an application specifically designed for concurrent block-device access.

Before using a shared volume:

- Verify the provider and volume type support multi-attach.
- Check limits on VM count, zones, instance types, and read/write modes.
- Use a clustered filesystem or appropriate locking mechanism.
- Define which node holds write ownership and implement fencing when a node fails.
- Test split-brain, network partition, and node recovery scenarios.

If the goal is sharing files across multiple machines, file storage such as NFS/SMB is usually a better fit than multi-attach block volumes, depending on latency and throughput requirements.

## 9. Monitoring Performance and Diagnosing Volume Issues

After attaching, resizing, or changing volume type, monitor both provider metrics and the OS.

| Metric group | Meaning | Signals to investigate |
| --- | --- | --- |
| IOPS | Read/write operations per second | Hitting provisioned or instance limits |
| Throughput | Data read/written per second | Hitting volume or aggregate VM caps |
| Read/write latency | Time to complete I/O | Rising p95/p99, applications waiting on disk |
| Queue depth | Number of queued or active I/Os | Sustained queue growth |
| Burst balance/credit | Available burst headroom if supported | Depleted credits and performance drop |
| Filesystem capacity | Used and available space | Disk full, inode exhaustion |
| I/O wait | CPU time spent waiting on I/O | Workload bottlenecked by storage |
| Disk errors | Device or filesystem errors | Resets, timeouts, read/write errors |

On Linux, you can run:

~~~bash
lsblk -f
df -hT
df -i
iostat -xz 1
findmnt
dmesg | tail -n 100
~~~

**df -hT** shows capacity and filesystem type; **df -i** checks inodes; **iostat** displays IOPS, throughput, queues, and wait times when the `sysstat` package is installed. Provider metrics remain essential because some limits exist at the storage backend or instance layer invisible to the guest OS.

Common symptoms:

- **Volume attached successfully but missing in OS:** check device rescan, drivers, permissions, operation status, and device mapping.
- **Disk visible but refuses to mount:** verify filesystem, partition, UUID, read-only flags, and kernel errors.
- **Wrong volume mounted after reboot:** inspect `/etc/fstab`, UUIDs, and service dependencies.
- **Resized in console but OS capacity unchanged:** rescan the block device, then expand partition/PV/LV and filesystem.
- **Disk full despite remaining block capacity:** check inodes, filesystem reserved space, and the actual mount point.
- **Detach fails with target busy:** locate processes, containers, or shells still holding the mount point.
- **Slow I/O:** cross-check IOPS, throughput, latency, queue depth, burst credits, and VM-level limits.

## 10. Example: Expanding a Data Volume for a Linux Application

A VM running an order-processing service has a 100 GiB data volume mounted at `/data`. As utilization reaches the alert threshold, the operations team needs to expand it to 200 GiB without data loss.

Workflow:

1. Verify volume ID, filesystem, partitions, and mount point using `lsblk`, `findmnt`, and `df`.
2. Check the latest backup and confirm restore capability; notify stakeholders if transient I/O latency is possible during modification.
3. Increase volume capacity in the control plane and wait for the modification state to complete.
4. Rescan the device inside the guest if the OS has not recognized the new size.
5. If partitioned, extend the corresponding partition; if using LVM, extend the PV and LV in order.
6. Expand the filesystem: use `resize2fs` for ext4 or `xfs_growfs` for XFS.
7. Verify `df -hT /data`, permissions, and application read/write functionality.
8. Monitor I/O latency, queue depth, and kernel logs after the change.
9. Update asset inventory, alert thresholds, and future growth plans.

If the filesystem expansion step fails, halt further changes and leave the volume in its current state. Collect command outputs, kernel logs, and metadata; never reformat the volume or create a new filesystem to attempt a fix. Restore from backup or engage platform support if filesystem structures show signs of corruption.

## 11. Automating Volume Lifecycle

IaC and automation standardize how volumes are created, attached, expanded, and protected. A resource definition can declare capacity, volume type, encryption, tags, snapshot policies, and VM associations. However, guest-OS changes such as partitioning, filesystems, and mounting typically require `cloud-init`, configuration management, or dedicated scripts.

An automated workflow should be structured into stages:

1. **Provision:** create the volume with compliant encryption, zone, performance tier, and tags.
2. **Attach:** attach to the VM and wait for provider completion.
3. **Discover:** locate the device via stable ID/serial.
4. **Initialize:** for new volumes only, create partitions/filesystems matching declared config.
5. **Mount:** create the mount point, set permissions, and configure persistent mounting.
6. **Verify:** check filesystem, capacity, permissions, and I/O.
7. **Monitor:** alert on capacity, inodes, latency, and performance limits.
8. **Detach/cleanup:** drain workload, unmount, and detach according to procedure.

Automation must be idempotent: re-running must never accidentally format a volume holding data or recreate filesystems unnecessarily. Record metadata confirming initialization, inspect filesystem signatures before formatting, and enforce explicit guards around any destructive operations.

Conceptual declarative example:

~~~yaml
volume:
  name: orders-data
  size_gib: 200
  type: general-purpose-ssd
  availability_zone: zone-a
  encrypted: true
  delete_on_instance_termination: false
  tags:
    application: orders
    environment: production
    owner: platform-team
mount:
  device_identity: provider-volume-id
  path: /data
  filesystem: xfs
  initialize_only_if_empty: true
~~~

Field names and volume types vary by provider. Verify the `delete_on_instance_termination` policy or equivalent option to ensure the disk lifecycle matches expectations.

## 12. Pre- and Post-Operation Checklists

**Before attaching**

- [ ] Verified volume ID, VM, zone, and device type.
- [ ] Confirmed volume is not attached contrary to policy or exceeding attach limits.
- [ ] Confirmed whether the volume is new or already contains data.
- [ ] Verified encryption, permissions, and retention policy.

**Before detaching**

- [ ] Drained the application and completed transactions/checkpoints.
- [ ] Verified no processes are using the mount point.
- [ ] Flushed buffers and cleanly unmounted the filesystem.
- [ ] Confirmed whether local/ephemeral data will be lost.

**Before resizing**

- [ ] Verified exact volume and target capacity.
- [ ] Checked limits, volume type, and online/offline resize support.
- [ ] Confirmed valid backup/snapshot and verified restore steps.
- [ ] Identified the exact partition, LVM, and filesystem chain to extend.

**After the operation**

- [ ] Control plane reports completion.
- [ ] OS detects the right device and capacity.
- [ ] Filesystem is mounted at the correct path with right permissions and size.
- [ ] Application reads/writes normally.
- [ ] I/O metrics, logs, and alerts show no anomalies.
- [ ] Metadata and asset inventory are updated.

## 13. Operational Principles

1. **Verify volume identity:** use volume ID, serial, or UUID rather than relying solely on mutable device names.
2. **Distinguish storage types:** know which data sits on persistent block volumes and which sits on local/ephemeral disks.
3. **Attach with control:** check zone, limits, permissions, and volume state before attaching.
4. **Detach after quiescing:** drain applications, flush data, and cleanly unmount before detaching in the control plane.
5. **Resize across both layers:** expand the block device, then partitions/LVM and the filesystem inside the guest OS.
6. **Never format volumes with data:** initialize a filesystem only after confirming the volume is new and blank.
7. **Snapshots do not replace backups:** verify consistency and run periodic restore tests.
8. **Protect access:** enforce encryption, IAM/RBAC, key management, and volume operation audit logs.
9. **Multi-attach requires coordination:** use a clustered filesystem or block-sharing-aware application; never mount read-write concurrently without coordination.
10. **Measure after changes:** verify capacity, IOPS, throughput, latency, and application health.

Attaching, detaching, and resizing volumes span both cloud and operating system layers. By coordinating both layers cleanly, identifying devices accurately, safeguarding data, and validating after every change, operations teams can scale storage capacity while maintaining data integrity, availability, and predictable costs.
