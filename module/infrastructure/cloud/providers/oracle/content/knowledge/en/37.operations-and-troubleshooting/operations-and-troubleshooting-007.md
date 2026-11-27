# Handling Disk Full, Volume Latency, and Filesystem Errors

## 1. Objectives and Scope

In the **Operations and Troubleshooting** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson guides you through handling three common storage incidents on Oracle Cloud Infrastructure (OCI):

- Applications cannot write because capacity is full, inodes are exhausted, or quotas are reached.
- Slow I/O increases response times for requests, batch jobs, or database transactions.
- Filesystems report errors, switch to read-only, or fail to mount.

The operational goal is to restore service with trustworthy data, find the root cause, and put controls in place to prevent recurrence. Increasing volume size or performance is only one of several available measures.

The commands in this lesson are for **Bash on Linux**, primarily Oracle Linux with XFS or ext4 and volumes attached to OCI Compute. Learners should know SSH, `sudo` privileges, mount points, partitions, and how to identify resources in the right tenancy, region, and compartment.

The path `/srv/app-data`, device `/dev/sdb`, partition `/dev/sdb1`, service `myapp.service`, and OCIDs in the examples are all illustrative values. Replace them with verified values on the target host. Never assume a device keeps the same name after detaching, attaching, or moving to a rescue host.

This lesson analyzes filesystems administered by operators on Compute. For OCI File Storage, switch to the NFS branch; for Object Storage, check requests, permissions, and service limits. For Autonomous Database or managed database services, use the service's operational mechanisms. Do not apply Compute host filesystem repair commands to storage layers outside your OS administration scope.

## 2. Separate the Layers Before Choosing a Fix

A data write path can traverse:

```text
Application / database
          |
Filesystem: XFS, ext4
          |
Logical volume (LV), volume group (VG), physical volume (PV) if using LVM
          |
Partition if present
          |
Block device in Linux
          |
Attachment: paravirtualized or iSCSI, possibly with multipath
          |
OCI Block Volume or Boot Volume
```

Not every system has all layers. A filesystem may sit directly on the whole volume; an LVM PV may also sit directly on the disk rather than a partition.

Three measurements answer three different questions:

| Observation | Question Answered | What Cannot Yet Be Concluded |
| --- | --- | --- |
| Volume size in OCI | How much block capacity has the service allocated? | Whether the filesystem can use the added space yet? |
| `lsblk`, `pvs`, `lvs` | How do Linux and LVM see each layer's size? | Whether the app can write under its user, quota, and path? |
| `df`, inode/quota checks | Does the filesystem have allocatable resources for the workload? | Whether the I/O path meets latency and throughput needs? |

For example, OCI increasing a volume from 100 to 200 capacity units while `df` still shows the old size indicates you need to inspect the guest OS expansion chain. It is not proof that the OCI resize failed.

### Identify Error Messages

| Symptom | First Investigation Direction | Common Pitfalls |
| --- | --- | --- |
| `No space left on device` / `ENOSPC` | Capacity, inodes, actual mount, allocation limits | Randomly deleting the largest file |
| `Disk quota exceeded` / `EDQUOT` | User, group, or project quota | Expanding the volume while leaving the quota unchanged |
| `Read-only file system` / `EROFS` | Mount options, kernel logs, filesystem state | Immediately remounting read-write without knowing the cause |
| `Input/output error` / `EIO` | Kernel logs, attachment, I/O path, filesystem metadata | Assuming running a repair tool fixes everything |
| Slow requests, timeouts, no space errors | I/O queue, workload, volume and instance limits | Raising VPUs before measuring |
| `Permission denied` / `EACCES` | Permissions, ACLs, SELinux, and executing user | Blaming every write failure on disk full |

A system can hit multiple error groups simultaneously. For example, a missing data mount causes the app to write onto the root filesystem; a full root stops agents from sending telemetry; continuous retries generate even more logs and I/O.

## 3. Stabilize Service and Collect Initial Evidence

Before changing data, record the UTC start time, impact level, recent changes, and involved resources. Minimum identifiers include instance OCID, volume OCID, attachment, compartment, region, mount point, filesystem, and the workload owning the data.

Separate two permission surfaces:

- IAM in OCI allows viewing or modifying volumes, attachments, metrics, and backups by compartment.
- Permissions in the guest OS allow reading logs, inspecting devices, stopping services, or administering filesystems.

Having `sudo` does not grant OCI volume-resize permissions. Conversely, having volume management permissions does not grant Linux login rights. When the CLI or Console reports unauthorized, check principal, region, compartment, and OCID before treating it as a storage outage.

If the workload has replicas or a tested traffic-shift mechanism, drain traffic from the failing node per runbook. For non-essential jobs, pause producers, exports, or batch jobs growing the data to buy investigation time. When metadata errors or repeated I/O errors occur, prioritize isolating writes and preserving evidence.

### Initial Observation Command Set

Run on the instance under investigation:

```bash
date -u
hostname

findmnt -T /srv/app-data -o TARGET,SOURCE,FSTYPE,OPTIONS
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT

df -hT -- /srv/app-data
df -i -- /srv/app-data

sudo journalctl -k --since "-30 minutes" --no-pager
```

How to read the output:

- `findmnt -T` shows the filesystem actually backing the path, even if that path is merely a directory on the root filesystem.
- `lsblk` links mount points to partitions, LVs, and disks. Cross-check UUIDs, stable device paths, and attachment details when confirming identity.
- `df -hT` shows space usage and filesystem type; `df -i` shows inode usage. Check both before concluding "space is available". [GNU: df](https://www.gnu.org/software/coreutils/manual/html_node/df-invocation.html)
- Kernel logs show whether errors began before or after a mount, resize, attachment change, or reboot.

If the path is inside a container, inspect the filesystem and mount namespace seen by the application process. A path with the same name on the host may not point to the same storage location.

Tools like `iostat`, `pidstat`, `lsof`, `growpart`, or XFS utilities may not be pre-installed. Prepare them in operational images. Do not install stacks of packages onto an already-full root filesystem just to investigate.

## 4. Handle Disk Full by Root Cause

### 4.1. Out of Block Space

Illustrative example:

```text
Filesystem     Type  Size  Used  Avail  Use%  Mounted on
/dev/sdb1      xfs    98G   97G   1.0G   99%  /srv/app-data
```

First, identify fast-growing directories within that exact filesystem:

```bash
sudo du -xhd1 /srv/app-data
```

Then drill down only into large branches, for instance:

```bash
sudo du -xhd1 /srv/app-data/logs
```

The `-x` option prevents traversing into other filesystems; `-d1` limits display depth. Limiting output does not eliminate the cost of traversing files underneath, so a tree with millions of files can still generate significant load. [GNU: du](https://www.gnu.org/software/coreutils/manual/html_node/du-invocation.html)

Sources of growth to check include application logs, export files, heap dumps, core dumps, upload directories, temporary files, and backups mistakenly placed on the application host.

Choose actions based on ownership and data lifecycle:

| Space-Consuming Data | Appropriate Action |
| --- | --- |
| Closed old logs past retention | Clean up per retention policy after keeping needed investigative data |
| Active log surging suddenly | Address log-generation cause, rotate, and instruct the app to reopen the file via supported mechanism |
| Regenerable cache | Use the application's cache cleanup utility |
| Exports or backups verified elsewhere | Clean local copies per policy; verify recoverability if it is a backup |
| Needed business data | Expand or migrate in a planned manner |
| Oracle Database datafiles, redo, control files, archived logs | Route to DBA workflows and database tools |

Moving files to another directory on the same filesystem does not free space. Compressing files directly on a nearly full filesystem can require temporary space and spike CPU/I/O. Only do so after calculating headroom and impact.

### 4.2. Inode Exhaustion from Too Many Small Files

Example:

```text
Block space used:  58%
Inodes used:       100%
New file creation: No space left on device
```

On filesystems with suitable inode reporting, isolate with:

```bash
sudo du --inodes -x --max-depth=1 /srv/app-data
```

Common culprits include one-file-per-request patterns, caches without TTL, session files, spools, and uncollected temporary directories. Stop the abnormal file-creation source, identify expired file sets, and clean up in load-limited batches.

Do not assume expanding the volume automatically solves every inode case. Inode allocation depends on filesystem design; ext4 and XFS behave differently. After cleanup, re-measure inodes, test creating a file as the application user, and monitor file-count growth rate.

Deleting millions of files can spike metadata load. If the service is degraded, throttle cleanup rate and coordinate timing with workload instead of running multiple concurrent sweeps.

### 4.3. `df` Reports Full While `du` Cannot Account for It

A major cause is **unlinked files still held open via file descriptors by a process**. The filename is gone from the directory tree `du` walks, while space remains allocated until the open reference is released. [GNU Coreutils FAQ](https://www.gnu.org/software/coreutils/faq/coreutils-faq.html)

Check:

```bash
sudo lsof +L1
```

Match device, inode, PID, file type, and size against the full filesystem. Do not mechanically sum every line because one inode can appear across multiple descriptors or processes.

Recovery typically involves asking the application to reopen logs via a supported mechanism, or restarting the specific service after assessing impact. For instance, restarting `myapp.service` only makes sense once you confirm that service holds the relevant file and you have a plan to maintain service availability.

Do not blindly truncate via `/proc/<pid>/fd/<fd>`: that can corrupt actively used data and does not fix why logs keep growing.

If no deleted-but-open files appear, check next:

- Did `du` run with sufficient permissions and on the same filesystem as `df`?
- Is data sitting under a mount point hidden beneath another mount?
- Are differences due to filesystem metadata, reserved blocks, sparse files, or block reporting math?
- Does a container or process have a different mount namespace?
- Do kernel logs show filesystem errors making metrics unreliable?

Investigate data hidden beneath a mount only through an appropriate maintenance workflow. Never unmount a volume actively serving writes just to "peek" at the directory underneath.

### 4.4. Quotas Block Writes Even When Filesystem Has Free Space

Quotas can restrict space or inodes per user, group, or project. On XFS with the corresponding quota type enabled, these commands only output reports:

```bash
sudo xfs_quota -x -c 'report -ubh' /srv/app-data
sudo xfs_quota -x -c 'report -uih' /srv/app-data
sudo xfs_quota -x -c 'report -pbh' /srv/app-data
```

These reports respectively inspect blocks by user, inodes by user, and blocks by project. Identify the exact quota type in use and the executing user; raising a quota for the wrong user will not resolve the application's error. [Oracle Linux: XFS quota reporting](https://docs.oracle.com/en/operating-systems/oracle-linux/8/xfs/xfs-ManagingQuotasonanXFSFileSystem_displaying_block_usage_information.html)

Linux filesystem quotas differ from OCI compartment resource quotas. One blocks writes inside the filesystem; the other can block requests to provision more cloud resources.

For ext4, also check reserved blocks if only non-root users run out of usable space. Do not reflexively shrink the root filesystem's reserved space: evaluate its role in preserving administrative access when nearly full.

### 4.5. Missing Data Mount Fills Up Root

If `/srv/app-data` is supposed to be a dedicated volume yet `findmnt -T` returns the `/` filesystem, the application may have written into the directory on root while the volume was unmounted.

Handling sequence:

1. Stop writers targeting that path.
2. Record data created on root and existing data on the data volume.
3. Restore the attachment or mount according to the actual root cause.
4. Reconcile, move, or merge data according to application rules.
5. Restart the application only after the mount point is verified.

Mounting the volume back hides existing data in the underlying directory without merging it automatically. If you only notice root usage stopped growing and ignore the orphaned writes, the system can lose track of records.

To prevent recurrence, services should depend on required mounts and verify the expected filesystem before writing. With systemd, you can design dependencies using `RequiresMountsFor=` combined with mount identity checks in runbooks or startup scripts.

## 5. When You Need to Expand an OCI Volume

Expand only after identifying the exact volume and confirming which layer lacks space. Before changing anything, ensure you have a valid backup or recovery point; for actively written data, coordinate application quiesce/backup mechanisms to meet consistency requirements.

OCI supports increasing block volume and boot volume sizes; it does not support shrinking volumes in place. Therefore, resize decisions must account for long-term cost. If shrinking is needed later, plan to create a smaller volume and migrate data appropriately. [OCI: Resizing a Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/resizingavolume.htm)

### 5.1. Expand at the Service Layer

OCI CLI example for a **data block volume**, run in an environment with permissions and region configured:

```bash
VOLUME_OCID='ocid1.volume.REPLACE_ME'

oci bv volume get --volume-id "$VOLUME_OCID"

oci bv volume update --volume-id "$VOLUME_OCID" --size-in-gbs 200
```

The value `200` is the new target size, not the increment. It must be larger than the current size. Re-read the volume after the request completes and confirm the new size. For boot volumes, use the dedicated boot volume operation; do not apply data volume commands verbatim. [OCI: Online Resizing a Block or Boot Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/update-online-resize-block-boot-volume.htm)

A successful resize request in OCI does not finish the work inside Linux.

### 5.2. Rescan the Right Device

After the volume grows, follow the rescan instructions OCI provides for the corresponding attachment and OS. For compatible SCSI device paths, OCI documentation illustrates reading one block directly then triggering a rescan. Once you have verified the disk is `/dev/sdb` and the corresponding sysfs path exists:

```bash
sudo dd iflag=direct if=/dev/sdb of=/dev/null count=1
echo 1 | sudo tee /sys/class/block/sdb/device/rescan
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT
```

This is a rescan example, not a performance benchmark. If the attachment, driver, or device does not match, do not guess sysfs paths. For multipath, follow the full procedure to update all paths and maps rather than rescanning only one member path. [OCI: Rescanning the Disk](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/rescanningdisk.htm)

### 5.3. Example: Data Volume with Partition and XFS, Without LVM

Assuming verified facts:

- `/dev/sdb` is the exact data volume just expanded.
- `/dev/sdb1` contains XFS mounted at `/srv/app-data`.
- The partition has contiguous free space immediately after it to expand into.
- The filesystem is healthy; a recovery plan and appropriate change window are in place.

Preview the partition change:

```bash
sudo growpart -N /dev/sdb 1
```

Only when the preview looks right, expand for real:

```bash
sudo growpart /dev/sdb 1
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT
```

`growpart` takes **disk** and **partition number** as two separate arguments. `-N` is dry-run mode. If it reports it cannot grow, lacks contiguous space, or the kernel has not seen the new size, stop and fix the right layer rather than deleting and recreating partitions by guesswork. [Canonical: growpart](https://github.com/canonical/cloud-utils/blob/main/man/growpart.1)

Once the partition in the kernel shows the new size:

```bash
sudo xfs_growfs -d /srv/app-data
df -hT -- /srv/app-data
```

XFS grows while mounted; the argument above is the mount point. This command does not expand the underlying disk or partition by itself. [Oracle Linux: Growing an XFS File System](https://docs.oracle.com/en/operating-systems/oracle-linux/9/xfs/xfs-GrowinganXFSFileSystem.html)

If the filesystem sits directly on the whole disk, skip the partition step. For ext4 verified healthy in an environment supporting online growth, run `resize2fs` on the device holding the filesystem after lower layers have expanded:

```bash
sudo resize2fs /dev/sdb1
df -hT -- /srv/app-data
```

Use only the branch matching the actual filesystem. `resize2fs` is not for XFS; `xfs_growfs` is not for ext4. When checking and repairing ext4 before changes is needed, perform it offline per maintenance procedure. [Oracle Linux: Resizing an Ext File System](https://docs.oracle.com/en/operating-systems/oracle-linux/9/ext/ext-ResizinganExtFileSystem.html)

### 5.4. Cases with LVM or Expanding the Root Filesystem

With LVM, inspect device relationships first:

```bash
sudo pvs
sudo vgs
sudo lvs -o lv_path,lv_size,vg_name,devices
```

If the PV sits on a partition, the partition must grow first. Then update the PV, check free space in the VG, extend the exact LV, and grow the filesystem. If the PV sits directly on the whole disk, do not create an extra partition.

Specific example where verified PV is `/dev/sdb1`, LV is `/dev/vg_app/lv_data`, and filesystem is XFS at `/srv/app-data`:

```bash
sudo pvresize /dev/sdb1
sudo pvs
sudo vgs

sudo lvextend -L +20G /dev/vg_app/lv_data
sudo lvs -o lv_path,lv_size,vg_name,devices

sudo xfs_growfs -d /srv/app-data
df -hT -- /srv/app-data
```

`+20G` is the increment for the LV and works only if the VG has enough free extents. Do not blindly allocate all free space if the VG serves other LVs. Some tool versions may resize the PV when growing the partition, so verify actual state between steps. [Oracle: Configure Logical Volumes](https://docs.oracle.com/en/learn/ol-lvm/)

For supported root filesystems on Oracle Linux, `oci-growfs` in OCI Utilities can handle expansion for supported layouts. Verify layout, version, and image-specific guidance before using it; do not run assumed data-volume sequences on the boot disk. [OCI Utilities Reference](https://docs.oracle.com/en-us/iaas/oracle-linux/oci/oci-utilities-reference.htm)

## 6. Investigate Volume Latency Using Evidence

### 6.1. Pinpoint Where the Slowdown Occurs

"Slow disk" can mean:

- The application waits on locks or CPU before issuing I/O.
- Filesystem or memory pressure causes writes, flushes, or writebacks to queue up.
- Multiple workloads contend for the same volume.
- The workload hits IOPS or throughput limits.
- Instance shape, attachment, or connection path caps performance.
- The I/O path experiences timeouts, retries, or disconnects.
- A database waits on synchronous I/O due to transaction characteristics.

Measure application request latency, guest OS stats, and OCI metrics over the exact same time range. Compare against a baseline with a comparable workload; do not use a single universal latency number as the benchmark for all I/O types.

### 6.2. Observe Inside Linux

```bash
iostat -xz -y 1 10
vmstat 1 10
sudo pidstat -d 1 10
```

`iostat -y` omits the first report since boot so you focus on the current window. Key columns to watch:

| Column | Investigative Meaning |
| --- | --- |
| `r/s`, `w/s` | Completed read/write requests per second |
| `rkB/s`, `wkB/s` or version variants | Read/write throughput |
| `r_await`, `w_await` | Average I/O time, including queuing and service |
| `aqu-sz` | Average queue length |
| `%util` | Device busy time as measured by the OS |

On devices serving parallel I/O, `%util` near 100% does not by itself prove performance limits are reached. Nor is `await` the pure latency of the OCI service. [iostat manual](https://man7.org/linux/man-pages/man1/iostat.1.html)

Use `pidstat` to identify which workloads generate I/O, then cross-check backup schedules, log rotation, data scans, and batch jobs. With `vmstat`, watch swap and memory pressure; read consecutive samples because the first report may reflect cumulative boot statistics.

Do not add I/O across LVs, partitions, and disks as if they were independent streams: the same I/O can be observed at multiple layers.

If request p99 rises while block I/O does not change, inspect traces, locks, CPU, connection pools, or other dependencies before modifying volume configuration. Stable averages can also hide brief flush bursts that drive tail latency spikes.

### 6.3. Correlate with OCI Metrics

In the `oci_blockstore` namespace, select the right volume by `resourceId` and distinguish attachments when needed:

| Metric | What to Inspect |
| --- | --- |
| `VolumeReadOps`, `VolumeWriteOps` | Read/write operations during the interval |
| `VolumeReadThroughput`, `VolumeWriteThroughput` | Bytes read/written during the interval |
| `VolumeThrottledIOs` | Number of throttled I/Os |
| `VolumeGuaranteedIOPS` | Provisioned IOPS under current config |
| `VolumeGuaranteedVPUsPerGB` | Active VPU/GB level |

Do not treat total operations in one minute as IOPS; convert by time interval and aggregation statistic. Volume metrics do not replace in-guest filesystem capacity measurements. [OCI: Block Volume Metrics Reference](https://docs.oracle.com/en-us/iaas/Content/Block/References/volumemetrics-reference.htm)

When data is missing, check region, compartment, filters, time window, and metric-read permissions. "No data" needs its own handling branch because it does not mean zero I/O.

### 6.4. Understand Limits Before Scaling Performance

Usable performance is constrained by multiple layers: volume size and performance tier, per-volume caps, aggregate instance limits, and attachment configuration. Raising VPUs does not remove instance-level limits. For Ultra High Performance, check support requirements and multipath configuration for your actual attachment, shape, and image. [OCI: Block Volume Performance](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumeperformance.htm)

A rule-of-thumb calculation:

```text
Approximate throughput = IOPS × average I/O size

12,000 IOPS × 8 KiB   = 93.75 MiB/s
1,000 IOPS × 256 KiB  = 250 MiB/s
```

This is an illustrative calculation, not an OCI performance guarantee. A workload with modest IOPS can still hit throughput limits because of large I/O sizes.

Similarly, a strictly sequential I/O workload averaging 2 ms latency can complete at most ~500 I/Os per second when only one request is in flight at a time. Raising provisioned performance will not automatically make an application add concurrency. Conversely, pushing queue depth too high can increase throughput while raising per-request latency.

### 6.5. Choose Actions from Metric Patterns

| Combined Evidence | Hypothesis to Test | First Action |
| --- | --- | --- |
| Throttling rising, queue rising, workload near provisioned cap | Volume limit is the bottleneck | Shed non-essential load; evaluate performance adjustment |
| Multiple volumes slow simultaneously on one instance | Instance aggregate cap or guest OS pressure | Compare shape, CPU, memory, and total I/O |
| No throttling, but kernel logs timeouts/resets | Attachment or I/O path issue | Preserve logs, check connectivity and path config |
| Latency spikes strictly during backups/exports | Workload contention | Reschedule or cap job concurrency |
| Slow writes with rising swap and memory pressure | Memory shortage or writeback backlog | Address memory pressure and app config |
| Low IOPS, low queue, app writes synchronously one-by-one | Workload lacks concurrency or is app-bound | Review write design and durability requirements |

Each row is an investigative direction, not an automatic conclusion. Change one factor at a time and measure before/after under comparable conditions.

Do not disable `fsync`, flushes, or database durability guarantees merely to lower latency numbers. With iSCSI, you can inspect sessions using the appropriate read-only status command:

```bash
sudo iscsiadm -m session -P 3
```

If the system uses multipath, inspect maps and paths with:

```bash
sudo multipath -ll
```

These two commands are only meaningful if the system actually uses those technologies. Never log out sessions or detach a volume with a mounted filesystem just to test reconnecting.

### 6.6. Controlled Benchmarking

During a production incident, start with metrics from the live workload. Running heavy benchmarks against an actively serving volume can worsen the situation.

When limits must be verified, use a dedicated test volume or file, controlling data pattern, capacity, I/O size, read/write mix, queue depth, and duration. Record tool version, shape/volume config, and metrics over the exact test window. Distinguish baseline latency tests from IOPS or throughput saturation tests. [OCI: Block Volume Performance Tests](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/bv-perf-win-tests.htm)

Do not use `dd` to write over raw devices containing data. Do not use a single file copy affected by page cache to claim a volume meets or fails performance targets.

## 7. Handle Filesystem Errors and Read-Only State

### 7.1. Determine Whether Fault Is Filesystem or Device Path

Start with mount options and kernel logs:

```bash
findmnt -T /srv/app-data -o TARGET,SOURCE,FSTYPE,OPTIONS
sudo journalctl -k --since "-1 hour" --no-pager
```

Message groups to preserve include block device I/O errors or timeouts, ext4 journal errors, XFS metadata errors, filesystem shutdown notices, and read-only remount notices.

A filesystem mounted `ro` may result from intentional configuration or error-protection behavior. XFS can also shut down the filesystem and return I/O errors; not every XFS fault surfaces as a read-only remount.

If the block path continues timing out or dropping devices, prioritize restoring the I/O path and controlling writes first. Metadata repair tools cannot fix a dropped iSCSI connection or broken attachment.

### 7.2. Prepare Before Repairing

A recoverable procedure must answer:

1. Which data is affected and who owns it?
2. Is there a replica, backup, or recovery copy meeting RPO/RTO?
3. Can producers be stopped, traffic drained, and processes using the filesystem closed?
4. Is the exact device holding the filesystem a partition, an LV, or the whole disk?
5. Is there a backup or clone preserving the pre-repair state?
6. Do the kernel and repair tools support all features enabled on the filesystem?

A backup of a damaged state can still be useful for investigation or trying alternative recovery paths, though it is not a healthy backup. For critical data, prefer testing recovery on an appropriate clone whenever possible.

Never run `mkfs` to fix a filesystem containing data you want to keep. Never run repair on a parent disk when the actual filesystem resides inside a partition or LV.

### 7.3. XFS: Check Offline Before Repairing

This example applies only to a verified **XFS data filesystem** on `/dev/sdb1`. Applications are drained/stopped and no processes hold the mount open:

```bash
sudo umount /srv/app-data
findmnt --source /dev/sdb1

sudo xfs_repair -n /dev/sdb1
```

`findmnt` must no longer list a mount for that filesystem. If `umount` reports busy, find the holding processes and resolve dependencies; do not use lazy unmount to bypass the offline requirement.

`xfs_repair -n` only inspects proposed modifications. After reviewing results, keep necessary copies and run repair:

```bash
sudo xfs_repair /dev/sdb1
```

If there is a dirty log, journal replay via a controlled mount/unmount cycle in an appropriate environment may be needed; stop if state is unclear. `xfs_repair -L` clears the log and can lose data—it is strictly a last resort after recovery assessment, not a default command. [Oracle Linux: Checking and Repairing XFS](https://docs.oracle.com/en/operating-systems/oracle-linux/9/xfs/xfs-CheckingandRepairinganXFSFileSystem.html)

After repair, remount with verified options, check kernel logs, and verify application data. Successful metadata repair does not prove every individual file's contents are intact.

### 7.4. ext4: Check and Repair While Unmounted

Dedicated example for **ext4**, not to be run sequentially after the XFS branch:

```bash
sudo umount /srv/app-data
findmnt --source /dev/sdb1

sudo e2fsck -f -n /dev/sdb1
```

Once results are reviewed, a backup copy exists, and changes are accepted:

```bash
sudo e2fsck -f /dev/sdb1
```

Do not default to adding `-y` to accept every modification. Save output, act according to findings, and check exit status. Checking/repairing a mounted filesystem can corrupt data; a root filesystem requires an offline environment or rescue host. [Oracle Linux: Checking and Repairing an Ext File System](https://docs.oracle.com/en/operating-systems/oracle-linux/9/ext/ext-CheckingandRepairinganExtFileSystem.html)

If files are recovered into `lost+found`, reconcile them with the application. Do not treat a successful mount as proof that all business data is restored.

### 7.5. Faulty Boot Volume, No SSH Access

When an instance fails to boot or the root filesystem is read-only, use the serial console to capture boot messages. If offline repair is needed, OCI's procedure is to stop the instance, detach the boot volume, and attach it as a data volume to a compatible Linux rescue instance in the same region and availability domain.

On the rescue host, compare `lsblk` before/after attaching, identify the exact partition or LV, avoid confusing it with the rescue host's root disk, and avoid auto-mounting the volume needing repair. After repairing and verifying, unmount, detach from the rescue host, and re-attach to the original instance. [OCI: Recovering a Corrupted Boot Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/recoveringlinuxbootvolume.htm)

If the boot volume and rescue host share duplicate VG names or UUIDs, handle them using proper LVM/filesystem procedures before activating or mounting. Never blindly activate all LVs.

A controlled reboot can assist journal recovery in certain situations; repeated forced reboots do not replace diagnosis and can destroy evidence.

## 8. Notes When the Workload Is Oracle Database

First distinguish three types of "full":

| Layer | Indicators to Check | Responsible Owner |
| --- | --- | --- |
| Linux filesystem | Blocks, inodes, quotas, mount errors | OS and storage operator |
| ASM disk group | Capacity and redundancy requirements inside ASM | DBA/ASM administrator |
| Tablespace or Fast Recovery Area (FRA) | Limits and usage inside the database | DBA and database tools |

Free disk space does not guarantee the FRA or tablespaces are within configured limits. Conversely, enabling database autoextend does not guarantee the underlying filesystem has room.

For FRA or archived logs, cleanup decisions must consider backups, recovery windows, and other consumers needing logs, such as standby databases. Use Oracle Database management tools and coordinate with DBAs; deleting files at the OS level can desynchronize the repository from actual data and break recoverability. [Oracle Database: Maintaining RMAN Backups](https://docs.oracle.com/en/database/oracle/oracle-database/18/bradv/maintaining-rman-backups.html)

When the database reports I/O waits, correlate database stats with guest OS and OCI metrics at identical timestamps. Use diagnostic tools matching active permissions and licensing. Do not label every I/O-related wait event an infrastructure fault before checking access patterns, execution plans, concurrency, and backup schedules.

## 9. Example Combining Steps on a Data Volume

Suppose a Java app on OCI Compute sees rising write errors after debug logging was enabled. These figures are illustrative to explain decision-making, not real benchmark results.

| Observation | Result |
| --- | --- |
| `findmnt -T /srv/app-data` | Expected data filesystem |
| `df -hT` | 99% used |
| `df -i` | 9% inodes used |
| `du` on filesystem | Significantly less than usage reported by `df` |
| `lsof +L1` | JVM holding a deleted log file open |
| Kernel log | No device or metadata errors in inspection window |

Handling sequence:

1. Dial back debug logging and stop the abnormal log producer.
2. Keep investigative logs in a location with free space; avoid copying onto the full filesystem.
3. Use the log-reopen mechanism supported by the app; if a JVM restart is required, drain the node and ensure service continuity.
4. Confirm the descriptor closes, space is reclaimed, and the app can write again.
5. Check retention and log rotation with the application team.
6. Use post-stabilization data growth trends to decide whether a resize is needed.

If high latency persists afterward, open a separate I/O investigation branch using `iostat`, workload metrics, and OCI metrics. Do not assume latency vanished simply because `df` dropped.

If instead kernel logs show I/O errors or an XFS shutdown, stop and take the data-protection and filesystem/storage-path recovery branch. Deleting logs will not resolve that condition.

## 10. Monitoring, Automation, and Cost Control

### 10.1. Alert on Remaining Serving Capacity

Combine multiple signals:

| Signal | Operational Meaning |
| --- | --- |
| Block usage percentage and remaining bytes | Actual usable space |
| Inode usage and quotas | Ability to create files/allocate for workload |
| Growth rate and projected time to exhaustion | Remaining time window to intervene |
| Throttled I/Os, queue depth, and app latency | Level of performance degradation |
| Kernel errors or abnormal filesystem state transitions | Need for data protection |
| Missing required mount | Risk of misdirected writes onto root |
| Telemetry stopped reporting | Monitoring blind spot |

Filesystem metrics must be collected from the guest via supported agents or appropriate custom metrics. Looking only at Block Volume size cannot tell you used space inside XFS/ext4.

For instance, 80% and 90% can be a team's starting alert thresholds, but must be tuned per workload. A huge filesystem at 92% may have more runway than a small filesystem at 75% receiving high-rate dumps.

Simple estimation:

```text
Time remaining ≈ Available space / Net growth rate

24 GiB remaining, growing net 3 GiB/hour
=> About 8 hours if the rate stays constant
```

Factor in bursts, response lag, and resize/recovery time. When growth rates fluctuate, use multiple measurement windows and absolute space thresholds to guide decisions.

### 10.2. Automate Under Verifiable Conditions

An automated log-cleanup task needs allowed paths, file types, file ages, cleanup caps, evidence saved elsewhere, and concurrency locks. Store action logs on a destination independent of the full filesystem.

For automated expansion, verify exact OCID, size/cost caps, volume state, quotas, and guest growth readiness. Require verification after each layer; a successful resize request in OCI must not be treated as the completion criterion.

Do not automate filesystem repair or deletion of business data purely from a disk-percentage alert.

### 10.3. Balance Performance, Availability, and Budget

- Separate logs, data, and temporary files when it helps isolate impact and enforce clean retention.
- Reduce contention by rescheduling batch jobs before buying more performance.
- When raising VPUs or changing shapes for emergency relief, log the timestamp and schedule a post-stabilization review.
- Base new volume sizes on growth data; volumes cannot shrink in place, so over-sizing carries long-term cost.
- Run periodic restore tests and measure recovery time. Untested backups do not reveal real RTO.
- Design failover using replication or appropriate HA mechanisms. Never mount standard XFS/ext4 read-write concurrently from multiple instances simply because a volume supports multi-attach.

HA does not automatically replace backups: deleted or corrupted data can replicate to standbys. Operations must guarantee both service continuity and the ability to return to a known-good data state.

## 11. Verify Before Closing the Incident

Verify using the application's user and execution path, not solely as `root`.

| Verification Group | Required Evidence |
| --- | --- |
| Right storage target | Mount point, source, UUID, or identifier matches design |
| Sufficient allocatable resources | Blocks, inodes, and quotas all have headroom |
| Writes succeed under real conditions | Health check or synthetic transaction via app mechanism writes and reads back data |
| No new storage errors | Kernel and app logs show no continuing related errors during observation window |
| Performance meets targets | Latency, error rate, and I/O return to acceptable levels under representative load |
| Trustworthy data | Appropriate reconciliation after repair, failover, or restore |
| Recovery readiness intact | Backup/replication/HA re-verified after changes |
| Root cause halted | Runaway producer, retention, mount dependency, or faulty config addressed |

If a volume was expanded, verify all layers in use:

```text
Size in OCI
    -> disk in Linux
    -> partition if present
    -> PV / VG / LV if present
    -> filesystem
    -> permissions, quotas, and application writes
```

The incident record should preserve a UTC timeline, resource identifiers, before/after outputs, changes applied, data impact scope, and owner of follow-up actions.

When escalating to Oracle Support, provide volume/instance/attachment OCIDs, region, availability domain, attachment type, performance configuration, time window, metrics, kernel logs, and recent changes. Remove credentials and unnecessary sensitive data. Time-aligned evidence helps distinguish guest OS, workload, and platform service faults faster.
