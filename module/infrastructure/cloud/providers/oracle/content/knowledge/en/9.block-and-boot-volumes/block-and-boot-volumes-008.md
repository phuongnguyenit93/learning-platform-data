# Recovering Boot Volumes and Troubleshooting Data Mount Errors

## Lesson Objectives

An OCI instance unreachable via SSH does not necessarily have a corrupted Boot Volume. Similarly, an application reporting it cannot write files does not necessarily have an attachment error. Effective recovery starts by identifying the exact layer experiencing the issue, preserving data, and choosing the right recovery path.

This lesson belongs to the **Block Volume and Boot Volume** chapter of the **CLOUD_PROVIDERS_ORACLE** module. The content connects Compute and storage with IAM, VCN networking, monitoring, backups, and service recoverability.

After this lesson, you will be able to:

- Distinguish instance access errors, OS boot errors, and data volume mount errors.
- Choose between restoring from a Boot Volume backup and repairing a Boot Volume via a rescue host.
- Cross-reference volumes, attachments, devices, partitions, filesystems, and mount points.
- Identify UUID, `/etc/fstab`, boot ordering, filesystem, and access permission errors.
- Build a verifiable recovery plan that avoids accidentally writing to the Boot Volume or running two system copies simultaneously with side effects.

Command examples in this lesson illustrate Linux. Boot Volume detach/attach conditions, attachment types, and rescue tools must match the instance type, shape, operating system, and OCI support capabilities. Do not apply a VM boot-detach workflow indiscriminately to bare metal or every other configuration.

## 1. Viewing Incidents Layer by Layer

A typical data path:

```text
Volume resource in OCI
  -> Attachment to instance
  -> Device recognized by the operating system
  -> Partition / LVM / encryption layer, if any
  -> Filesystem
  -> Mount point
  -> Access permissions and application
```

A failure at a lower layer can produce multiple symptoms at upper layers. However, fixing the wrong layer can make data harder to recover.

| Symptom | Hypothesis to Check First | Cannot Conclude Yet |
| --- | --- | --- |
| SSH timeout | Instance status, routes, NSGs/security lists, firewalls, and access path | Boot Volume is corrupted |
| SSH login rejected | User, SSH keys, SSH service, and authentication config | Entire OS needs restoring |
| Console shows emergency mode | Boot error, filesystem, or mandatory mount entry in `fstab` | Root partition is lost |
| OCI reports attached, yet mount is missing | Device connection, partition, filesystem, and mount point | Data is gone |
| Application reports permission denied | User/group, mode, ACLs, and OS security policies | IAM forbids mounting volume |
| Application reports read-only filesystem | Mount state, filesystem errors, or I/O errors | Only file permissions need changing |
| Application reports no space left | Capacity, inodes, quotas, and the filesystem actually backing the path | Filesystem must be recreated |

A running Compute status reflects only part of the infrastructure lifecycle. It does not guarantee the OS booted cleanly, the application is ready, or data mounted properly.

## 2. Preparation Before Performing Recovery

### 2.1. Record Resource Identities and Relationships

Create an incident worksheet with:

- Region, availability domain, compartment, and OCID of the instance.
- OCIDs of the Boot Volume, Block Volumes, and related attachments.
- Instance type, shape, image/OS, and CPU architecture.
- Pre-incident mount points, filesystems, and device identifiers if available.
- Latest operations: OS updates, `fstab` edits, attachment changes, instance replacement, or volume expansion.
- Available backups, desired recovery point, and where required keys/secrets are stored.
- Which applications, batch jobs, or automation could continue touching the instance during remediation.

Do not rely solely on display names when choosing volumes. Two recovery copies can have nearly identical names, identical sizes, and even duplicate filesystem UUIDs.

### 2.2. Define Data and Time Objectives

- **RPO**: up to what point in time is data loss acceptable?
- **RTO**: within what timeframe must the service be restored?

A Boot Volume backup from last week can restore the operating system, but it does not automatically satisfy requirements for data generated today. You must also check compatibility between the application version on the restored boot volume and the current Oracle database schema/data.

### 2.3. Preserve a Rollback Path

Before making changes that can write to data, preserve the original and create an appropriate copy or backup when conditions allow. Inspection and repair steps should be performed on a separate recovery copy first if time and resources permit.

Never let the original machine and the recovery machine simultaneously run the same data-writing role unintentionally. Control load balancers, workers, batch jobs, schedulers, and automation that might auto-restart the application.

A subnet without a public IP does not necessarily isolate side effects: the machine can still reach DBs, queues, or APIs over private networking. Isolation must be enforced via actual access paths and permissions.

## 3. Choosing a Boot Volume Recovery Path

| Scenario | Priority Evaluation Path | Conditions to Verify |
| --- | --- | --- |
| Good backup exists, need to return to known state | Restore into a new Boot Volume and build recovery environment | Backup timestamp, location, image/shape, keys, and accompanying data |
| Boot is intact, but config like `fstab` is broken | Repair via console or rescue host | Console access, supported boot detach/attach, exact filesystem identifiers |
| Filesystem corruption suspected | Preserve original, diagnose offline on a copy | Matching filesystem tools, device unmounted, fallback plan if unrepairable |
| Instance lost, yet boot was retained | Evaluate reusing the remaining Boot Volume via OCI-supported flow | Compatibility, location, and data condition |
| No suitable recovery copy, data state unclear | Preserve and assess data salvage options | Avoid further writes or creating new filesystems on the old device |

You do not need to restore the entire Boot Volume if the OS is healthy and the error is merely an unmounted data volume. Conversely, fixing `fstab` will not resolve a situation where no usable OS image remains.

## 4. Recovering From a Boot Volume Backup

### 4.1. Selecting the Right Backup

Before restoring, cross-check:

1. Which Boot Volume and environment the backup belongs to.
2. The data timestamp represented by the backup.
3. Whether the backup predates the incident or faulty change.
4. Whether the backup status allows restoration.
5. Availability in the target region/availability domain and required copy steps, if any.
6. IAM permissions and usability of associated encryption keys.
7. Which data resides on separate Block Volumes, DB services, or other storage.

Do not pick a backup solely by job completion timestamp while ignoring when the data point was captured. For transactional workloads, use consistent backup/restore procedures supported by the application or database.

### 4.2. Creating a Separate Recovery Volume

Restoring from a Boot Volume backup creates a recovery Boot Volume via a service-supported workflow. Do not treat this operation as an in-place overwrite of volumes currently attached to the failed instance.

Select a location matching the intended recovery instance. Standard volume attachment is subject to location constraints such as availability domain; having a backup or copy does not mean a volume can be directly attached anywhere.

Wait for the restore operation to reach a usable state and verify the result. Seeing a new resource appear does not prove the data is ready to start the application.

### 4.3. Launching the Recovery Instance and Controlling App Startup

Use the OCI-supported workflow to launch an instance from a Boot Volume with a compatible shape and configuration. Assign networking, permissions, and security policies appropriate for the recovery environment.

Before enabling live traffic, check whether software inside the boot image starts automatically:

- Are application services enabled to start on OS boot?
- Do schedulers run jobs that send emails, process payments, or update DBs?
- Do agents or applications carry configured identities colliding with the original machine?
- What do cloud-init or initialization scripts do when the instance environment changes?
- Are network configurations, hostnames, and dependent addresses still valid?

Restoring the OS does not automatically restore the right IAM policies, routes, NSGs, load balancers, and external resources. Those components must be created or reconciled with appropriate infrastructure configuration.

### 4.4. Reconciling Data Outside Boot

If the boot image contains an older application version while Block Volumes or the DB hold newer data, evaluate compatibility before allowing writes. Never let automatic migrations run blindly during recovery startup.

A boot backup does not include all data on separate Block Volumes. Each component requires an appropriate recovery source and point-in-time relationship, especially when transactions span multiple storage locations.

## 5. Repairing a Boot Volume Using a Rescue Host

### 5.1. Role of the Rescue Host

A rescue host is a normally functioning instance used to attach the broken volume as a data device under a supported attachment workflow. You inspect logs, check configurations, or repair filesystems without having to boot the OS from the broken volume itself.

When choosing a rescue host:

- Ensure location and attachment type are compatible with the volume.
- Have tools supporting the filesystem, LVM, or encryption layer to be handled.
- Control auto-mounting and avoid automatically executing software from the attached volume.
- If running binaries from the rescued OS via `chroot` is necessary, verify CPU architecture and runtime compatibility. Merely reading files on a filesystem does not require running its binaries.

### 5.2. Controlled Sequence of Operations

1. Prevent applications and automation from continuing to modify the resource needing recovery per operational procedures.
2. Stop the source instance when required by the Boot Volume detach flow and wait for the appropriate state.
3. Confirm the option to keep the volume; never use terminate as a substitute for intentional stop/detach.
4. Detach the Boot Volume per OCI capabilities supported for that instance type.
5. Attach that boot volume, or a copy of it, as a data volume to the rescue host via a supported workflow.
6. Cross-reference the attachment against the actual device and partitions inside the rescue OS.
7. Read configurations, logs, and check filesystems before deciding on repairs.
8. After repairs, flush/unmount and detach cleanly; never detach while still in use.
9. Reattach as boot or create a recovery instance via a supported path.
10. Verify boot, data mounts, and the application before restoring traffic.

Never leave a standard filesystem open for concurrent writes from both the original host and the rescue host. The ability to create multiple attachments does not protect a standard filesystem from unsupported concurrent access.

### 5.3. Distinguishing the Rescue Host's Root From the Broken Host's Root

Suppose the root filesystem under rescue is mounted at `/mnt/recovery`:

| Path | Which Environment Does It Belong To? |
| --- | --- |
| `/etc/fstab` | The running rescue host |
| `/mnt/recovery/etc/fstab` | The operating system being rescued |
| `/var/log` | Logs of the rescue host |
| `/mnt/recovery/var/log` | Logs stored on the rescued filesystem, if logs reside there |

Mistakenly editing the rescue host's `/etc/fstab` both fails to fix the original incident and can prevent the rescue host from booting normally. Similarly, running `journalctl -b` normally reads the current host's boot logs, not automatically the history of a volume mounted elsewhere.

If reading journal logs stored on the rescued volume is needed, use the tool's directory/root-reading mode with the exact path and log format. Do not interpret rescue host logs as evidence from the broken machine.

### 5.4. Understand Limitations of Read-Only Mounts

A journaled filesystem may need to replay its log during mount. The `ro` option alone is not enough to guarantee every mount operation leaves source data untouched.

When preserving the original copy, prefer working on a clone and using non-replaying inspection/mount modes appropriate for the filesystem and tools in use. For example, ext4 has options related to not loading the journal; XFS has a no-recovery mode when mounting read-only. These modes can present an inconsistent view if the filesystem was not previously closed cleanly.

If duplicate UUIDs appear when attaching a copy, identify the exact cause and how to access the copy per filesystem guidelines. Do not change the original volume's UUID just to bypass a warning without knowing which references depend on it.

## 6. Diagnosing Data Mount Errors Bottom-Up

### 6.1. OCI Layer: Is the Volume Actually Attached to the Right Machine?

Verify:

- Volume and attachment OCIDs, not just display names.
- Target instance, availability domain, and attachment status.
- Configured access mode: read/write, read-only, or shared as supported.
- Attachment type and OS connection steps.
- Failed operation events or recent changes.

For iSCSI, inspect sessions and connection steps per guidance for that exact attachment. Do not open an iSCSI port to the Internet or alter all security rules as a knee-jerk reaction to a mount error.

For paravirtualized attachments, still confirm the OS recognizes the device and has suitable drivers. "Attached" in the control plane does not mean every layer inside the guest is ready.

### 6.2. Device Layer: Which Partition Holds the Data?

Run read-only inspection commands on the machine being diagnosed:

```bash
# Relationship between devices, partitions, filesystems, and mounts
lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,UUID

# Read filesystem identifiers; may require admin privileges
sudo blkid

# Root filesystem source of the current machine
findmnt -T /
```

A volume may contain a filesystem directly, multiple partitions, LVM, or an encryption layer. Do not try to mount the parent device if the filesystem actually resides inside a partition or logical volume.

Do not conclude a device is empty simply because one tool does not display `FSTYPE`. Inspect storage layers and tool capabilities before deciding to create a filesystem.

### 6.3. Filesystem and Mount Point Layer

```bash
# Replace with an actually existing data path
findmnt -T /srv/app-data

# Capacity and inodes of mounted filesystems
df -hT
df -i

# Failed units and kernel errors from the current boot
systemctl --failed
sudo journalctl -k -b --no-pager
```

If `findmnt -T /srv/app-data` returns the root filesystem, the data volume may not be mounted there. The application may be writing into a directory on the Boot Volume instead of the intended location.

In particular, when mounting a volume over a directory that already contains files, the old files underneath are hidden from that path; they are not automatically moved onto the new volume. Plan data consolidation if the application spent time mistakenly writing to root before the incident.

### 6.4. Application Cannot Write Yet Mount Looks Correct

Check separately:

- Whether the mount is read-only.
- Whether space or inodes are exhausted.
- Whether user/group, mode, ACLs, and policies such as SELinux permit access.
- Whether the application's UID/GID changed after recovery or host replacement.
- Whether the service uses the right directory, container mount, or namespace.

IAM permissions govern OCI service operations, not OS file permissions. Never grant tenancy admin permissions to fix a filesystem ownership error.

## 7. Fixing `/etc/fstab` and Boot Ordering

### 7.1. A Mount Line Can Halt the OS in Emergency Mode

`/etc/fstab` declares filesystems and how to mount them. An entry pointing to a nonexistent UUID, wrong filesystem type, or invalid options can block booting depending on OS policy.

Fields to understand:

| Field | Role |
| --- | --- |
| Source | Supported UUID, label, or stable device path |
| Mount point | Target directory |
| Filesystem type | e.g., ext4 or XFS, must match actual data |
| Options | Permissions, mount behavior, network requirements, and specific flags |
| Dump/fsck | Parameters for legacy backup tools and per-filesystem check order |

Illustrative line for an ext4 data volume requiring network-dependent treatment during the mount stage:

```fstab
UUID=<ACTUAL_FILESYSTEM_UUID> /srv/app-data ext4 defaults,_netdev 0 2
```

This is not a line to copy verbatim. Use the actual UUID, filesystem, and appropriate options. `_netdev` describes network dependency for the mount process; it does not create iSCSI sessions, fix attachments, or prove the application can access data.

Do not mechanically apply ext4's filesystem check field to XFS. Each filesystem and operating system has its own check/recovery mechanism.

### 7.2. Verify Before Testing All Mounts

On an OS being edited directly, inspect and validate configuration with:

```bash
cat /etc/fstab
findmnt --verify --verbose
```

Validation flags depend on the installed tool version and do not replace verifying data contents. If in rescue mode, the file to edit is inside the mounted root of the broken OS; the default commands above do not automatically switch to that file.

Do not treat `mount -a` as a read-only check. It can actually mount entries and trigger writes or external service interactions. Test only after verifying entries, filesystem types, devices, and expected impact in an appropriate environment.

Before editing `fstab`, preserve the old contents within your recovery plan scope. Change only the faulty entry, then re-verify before rebooting; never wipe all data lines at once just to get a login prompt.

### 7.3. `nofail` Is Not a Way to Ignore All Data Errors

For an optional mount, allowing boot to continue when the mount is missing may be appropriate. However, if it holds mandatory DB or application data, continuing to boot and letting the application write to an empty directory on root is dangerous behavior.

Separate two requirements clearly:

1. Should the OS continue booting if the volume is missing?
2. Should the application service run if the data filesystem is not ready?

For example, for a systemd service, you can define unit dependencies as follows in the appropriate configuration for that exact service:

```ini
[Unit]
RequiresMountsFor=/srv/app-data
```

This dependency ties service startup to the required mount, yet it does not automatically prove the mount is the right volume or that data contents are valid. Verify volume identity and application readiness conditions separately.

Do not set a fixed mount timeout just to make errors disappear faster without understanding actual connection times. Boot ordering, attachment, and device readiness must align.

## 8. When Filesystem Corruption Is Suspected

### 8.1. Stop Guessing From Generic Error Messages

Messages like "wrong filesystem type," "bad superblock," or "read-only filesystem" have multiple causes:

- Selecting the wrong device or partition.
- Filesystem sitting inside LVM or an encryption layer not yet unlocked/activated.
- Missing supporting tools or drivers.
- Duplicate UUID from a clone.
- Journal/log needing recovery.
- Metadata corruption or underlying I/O errors.

Preserve complete error messages and related kernel logs. Never create a new filesystem on the device just to make a mount succeed; that does not fix a mount error for old data.

### 8.2. Offline Diagnostics on the Verified Device

Filesystem check/repair tools require the exact filesystem type and proper device state. For reliable offline checking, the filesystem must no longer be mounted or written to by another machine.

| Filesystem | Common Dedicated Tool | Notes |
| --- | --- | --- |
| ext4 | `e2fsck` | Verify the exact device; check-only and repair modes have different impacts |
| XFS | `xfs_repair` | Do not assume generic fsck calls suffice; check requirements regarding logs and mount state |
| Other types | Tools supported by the filesystem/OS | Do not run tools for another type simply because device names look alike |

Check-only modes, where supported by the tool, help assess state beforehand but may not reflect final state after journal recovery. Read the output and limitations of that mode before deciding to repair.

Do not auto-confirm all repairs or clear filesystem logs as a first step. Repair operations can lose some data; require a copy, a plan, and impact assessment. If recurring I/O errors appear, investigate the attachment/service layer rather than repeatedly running metadata repairs.

### 8.3. A Mountable Filesystem Does Not Guarantee Application Consistency

Returning a filesystem to a mountable state does not guarantee every application transaction completed. For self-managed databases, database recovery, verification, and database-native tools remain necessary per supported procedures.

Similarly, data spanning multiple volumes might be restored to different points in time. One cleanly mounted volume does not resolve inconsistencies across data files, logs, and configurations residing elsewhere.

## 9. Common Troubleshooting Matrix

| Symptom | Check | Evidence-Based Resolution |
| --- | --- | --- |
| Device not visible | Attachment, connection type, session/drivers, and kernel logs | Complete the proper connection steps; do not create a filesystem to test |
| UUID in `fstab` not found | Actual UUID, attached volume, clone/restore, and LVM layers | Fix the reference properly after identifying the data source |
| Boot waits for mount then enters emergency mode | Mandatory entry, device not ready yet, network ordering | Fix configuration and dependencies; allow boot to skip only when required |
| Wrong filesystem error | Partition, metadata, encryption/LVM layer, and supporting tools | Select the right device layer and filesystem type |
| Clone fails to mount due to duplicate UUID | Original volume and copy are both present simultaneously | Use filesystem-supported copy access methods; manage identifier changes carefully |
| Filesystem remounted read-only | Filesystem and I/O error logs | Preserve data, diagnose offline as needed; do not force writes speculatively |
| Mount succeeds yet permission denied | UID/GID, ACLs, SELinux, and path permissions | Fix according to the actual application identity |
| Mount point busy on detach | Processes, working directories, and submounts | Stop usage cleanly before unmounting/detaching |
| Volume is larger, yet filesystem remains small | Device, partition, LVM, and filesystem sizes | Expand each layer properly via supported methods |
| Newly written files missing after mount | Did data reside on root underneath the mount point? | Compare both sources and merge data under controlled steps |
| Boot restored, yet application still errors | Data volume, DB, secrets, permissions, and network config | Restore all dependencies, not just the OS layer |

## 10. End-to-End Example: `fstab` Error Prevents VM From Booting Normally

### 10.1. Context

A Java API runs on an OCI VM. The OS sits on a Boot Volume, working data sits on a Block Volume mounted at `/srv/app-data`, and business results are stored in a separate Oracle database.

After replacing the data volume with a restored copy, the operator kept the old UUID in `fstab`. On the next reboot, the console showed the OS waiting for a nonexistent device and then dropping into emergency mode.

### 10.2. How to Analyze

Initial evidence:

- The instance still has its Compute resources and Boot Volume.
- The console displays an error waiting for the data mount's UUID.
- A new data attachment exists, yet the filesystem identifier does not match the old entry.

Therefore, the first investigation path is checking mounts and `fstab`, not concluding the boot volume is lost and restoring the entire OS back to last week.

### 10.3. Evaluable Recovery Workflow

1. Isolate the pipeline so the application does not run and write data during repair.
2. Record volumes/attachments and preserve a rollback path.
3. If the console allows safe editing, use that path; otherwise evaluate a rescue host per boot detach/attach conditions.
4. Cross-check the actual UUID of the data filesystem against `fstab` in the broken OS.
5. Update the entry for the verified volume—do not just pick a device of the same size.
6. Check Java service dependencies so it does not start when data is missing.
7. Return the Boot Volume to the boot path via a supported method.
8. Confirm root and `/srv/app-data` point to the right sources; verify data matches the desired recovery timestamp.
9. Test DB connectivity and application tasks before accepting traffic.
10. Monitor for errors and verify a planned reboot when conditions allow.

If it is later discovered that the application had written into the directory on root while the data volume was unmounted, handle that data separately. Fixing the UUID does not automatically move those files onto the data volume.

## 11. Pre-Cutover Checks Before Restoring Service

| Group | Conditions to Confirm |
| --- | --- |
| Boot | OS boots cleanly with no errors needing intervention on the boot path |
| Identity | Correct instance, volumes, attachments, and intended recovery copy |
| Mount | Root, data, and mandatory filesystems have the right sources, permissions, and options |
| Data | Contents and recovery timestamp meet requirements; no data left stranded under mount points |
| Application | Correct version, configuration, secrets, and migration state |
| Dependencies | DB, network, DNS, IAM, and related services function properly |
| Concurrency | Only authorized application/worker instances perform side effects |
| Recovery | Original copy or rollback option remains usable per plan |
| Monitoring | Monitor boot, capacity, I/O, mounts, and business errors post-recovery |
| Cost | Know which rescue hosts, retained volumes/copies/backups exist and who owns them |

A single successful mount check does not prove mounts will work after reboot. Verify startup configuration and dependencies with a test matching your environment's availability requirements.

Once stabilized, document the root cause, recovery timestamp, potential data loss per RPO, and actual duration against RTO. Decommission rescue resources or copies only when recovery needs end per data retention policies; a detached resource may still hold data worth keeping and costs that must be managed.

## 12. Self-Check

1. Why is an SSH timeout not proof that the Boot Volume is corrupted?
2. When should you restore from backup instead of fixing configuration via a rescue host?
3. Does a boot backup protect data on separate Block Volumes? What else must be reconciled with an Oracle database?
4. When the filesystem under rescue is mounted at `/mnt/recovery`, which `fstab` file is the target to inspect?
5. Why is the `ro` mount option alone insufficient to prove the source copy won't be altered by journal recovery?
6. If `findmnt -T /srv/app-data` returns the root filesystem, what risk might the application face?
7. Why is adding `nofail` not a universal fix for mandatory data mounts?
8. What must be confirmed before running filesystem repair tools?
9. Why shouldn't a recovered boot volume freely run the same schedulers or workers concurrently with the original machine?
10. What evidence is required before placing a recovered instance back behind the load balancer?

The output of this lab is a workflow that clearly specifies the fault layer, recovery source, preserved data copy, applied changes, and evidence that the application uses the right data after startup.
