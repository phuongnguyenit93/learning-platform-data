# Mounting, Filesystems, and In-Machine Data Access Permissions

After a volume or storage service is attached to a virtual machine, the operating system still needs to detect the device, prepare the filesystem, mount it to a path, and grant permissions to the processes using it. If any step goes wrong, applications may fail to see data, accidentally write to the system disk, fail to boot after a reboot, or unintentionally allow unauthorized users to read and modify files.

This lesson covers how to mount block storage and network file shares on Linux/Windows, configure persistent mounts across reboots, manage owner/group/ACL permissions, and protect data. It also distinguishes filesystems from object storage, explains common errors, and outlines safe operational procedures for cloud workloads.

## 1. From Storage to the Path Used by Applications

Cloud storage services expose data through several models. How the operating system sees and accesses data depends on the service type.

| Storage type | How the machine accesses it | Usage examples | Requires mounting a filesystem? |
|---|---|---|---|
| Block storage | Block device attached to the VM | Volumes holding databases, application filesystems, boot disks | Yes, after creating or detecting a filesystem |
| File storage | File sharing via protocols such as NFS or SMB | Directories shared across multiple machines, home directories, shared content | Yes, mount the share into a directory tree or drive |
| Object storage | API or SDK operating on objects by bucket/container and key | Backups, media, logs, artifacts, data lakes | Not required; gateway/FUSE can be used but has semantic limits |

### Block Storage

A block volume provides data blocks for the operating system to use like a disk device. On Linux, the device may appear under names such as **/dev/nvme1n1** or **/dev/sdb**; on Windows, it appears as a new disk.

A new volume typically needs a partition table and filesystem initialized before mounting. A volume that already holds data may already contain a filesystem; reformatting it will destroy the data.

Examples of cloud block storage services include Amazon EBS, Azure Managed Disks, and Google Persistent Disk. Capabilities for attach, detach, multi-attach, availability zones, and performance depend on the specific volume type and configuration.

### File Storage

File storage provides a shared file namespace over the network. Clients mount the share so applications can access it via paths just like a local directory.

Common protocols:

- NFS, common in Linux/Unix environments.
- SMB, common in Windows and also supported on Linux via CIFS.
- Managed file storage services may support one or more of the above protocols.

Examples include Amazon EFS, Azure Files, and Google Cloud Filestore. Check the service's supported protocol, version, authentication mechanism, share permissions, and connection limits.

### Object Storage

Object storage organizes data into objects inside buckets or containers. Applications typically access it via HTTPS APIs, SDKs, or synchronization tools. Object storage does not provide full POSIX filesystem behavior such as file locking, atomic renames, owner/group permissions, and directory operations in the traditional filesystem sense.

Some tools allow mounting object storage via FUSE or a gateway. This can be useful for certain read workflows, but should not be assumed suitable for databases or applications requiring strict POSIX filesystem semantics. Understand caching, consistency, locking, renames, permission mapping, and disconnect behavior.

## 2. Filesystems and Mount Points

A filesystem is the structure that organizes data on a storage device. It manages directories, files, metadata, permissions, and space allocation.

Common filesystems:

- **ext4:** widespread on Linux, supports journaling, and fits many server workloads.
- **XFS:** often used for large volumes and high-throughput workloads; repair tools differ from ext4.
- **NTFS:** standard Windows filesystem, supporting ACLs and extensive administrative features.
- **ReFS:** used in certain Windows environments and matching workloads; verify OS-supported features.
- **NFS/SMB:** network file-sharing protocols, not local filesystems formatted onto a block volume.

### What Is a Mount Point?

On Linux, a mount point is a directory in the filesystem tree where another filesystem is attached. For example, a data volume may be mounted at **/data**, and a file share at **/mnt/shared**.

When you mount a filesystem onto a directory that already contains files, the existing contents of that directory are hidden while the mount is active. The old data remains on the parent filesystem, but applications cannot see it through that path until unmounted. Therefore, choose a dedicated mount point and inspect the directory before mounting.

On Windows, volumes are typically assigned a drive letter such as **D:** or mounted into an empty NTFS folder. Using mount folders instead of drive letters can help organize paths more consistently.

### Distinguishing Attach and Mount

- **Attach:** the cloud platform connects the volume to the VM.
- **Discover:** the operating system detects the new device.
- **Partition:** creating or reading the partition table if needed.
- **Format:** creating a new filesystem on a partition or device.
- **Mount:** attaching the filesystem to a path so processes can access it.

A successful attach does not mean data is ready. Likewise, a volume can be attached but not yet mounted, or mounted successfully while application permissions remain incorrect.

## 3. Safe Procedure for Mounting a Block Volume on Linux

### Step 1: Identify the Exact Device

After attaching the volume from the cloud console or API, inspect devices:

~~~sh
lsblk -o NAME,SIZE,TYPE,FSTYPE,UUID,MOUNTPOINTS
sudo blkid
findmnt
~~~

Cross-check capacity, device type, filesystem, and volume details from the cloud console. Device names like **/dev/sdX** or **/dev/nvmeXnY** can change across reboots or instance types. Never rely solely on device names to identify a data disk.

If the volume already has a filesystem and data, do not run format commands. You can mount the existing filesystem after verifying the exact device and state.

### Step 2: Check Whether the Volume Is New or Holds Data

For a new, blank, and verified volume, you can create a partition table and filesystem per design. The following example is strictly for a new device with no data to preserve:

~~~sh
# Run only after verifying /dev/nvme1n1 is a new, blank volume.
sudo parted /dev/nvme1n1 --script mklabel gpt
sudo parted /dev/nvme1n1 --script mkpart primary ext4 1MiB 100%
sudo mkfs.ext4 /dev/nvme1n1p1
~~~

Partition names in the example may vary by driver and device. Some volumes are used directly without partitions; some designs use LVM or multiple partitions. Follow your system's standard.

**Warning:** **mkfs**, **parted mklabel**, and formatting operations can overwrite metadata and make existing data inaccessible. Always verify the volume, backups, and state beforehand. Never run these commands on volumes containing production data.

### Step 3: Create the Mount Point and Mount

~~~sh
sudo mkdir -p /data
sudo mount UUID=REPLACE_WITH_FILESYSTEM_UUID /data
findmnt /data
df -hT /data
~~~

Replace **REPLACE_WITH_FILESYSTEM_UUID** with the actual UUID obtained from **blkid** or **lsblk -f**. Using a UUID or equivalent stable path avoids depending on device naming order.

If the volume has an XFS filesystem, the mount command is similar; the OS detects the filesystem automatically. Install the corresponding filesystem utilities if a minimal image lacks them.

### Step 4: Verify Permissions and Write Access

After mounting, the filesystem may be owned by **root**. Create an application group or user per policy and grant permissions to the appropriate directory.

Example:

~~~sh
sudo groupadd --force appdata
sudo usermod -aG appdata appuser
sudo chown root:appdata /data
sudo chmod 2770 /data
~~~

Log back in or restart the process so the user picks up the new group. The setgid bit on the directory (**2** in **2770**) ensures newly created files and subdirectories generally inherit the parent directory's group on POSIX filesystems.

Test using the actual application identity:

~~~sh
sudo -u appuser test -r /data && echo "readable"
sudo -u appuser test -w /data && echo "writable"
namei -l /data
~~~

Do not test solely as root, because root can read/write even when the application user lacks permissions.

## 4. Configuring Persistent Mounts Across Reboots with /etc/fstab

The standard **mount** command applies only to the current session. To mount a filesystem automatically at startup, Linux typically uses **/etc/fstab**.

Line structure:

~~~text
<source> <mount-point> <filesystem-type> <options> <dump> <pass>
~~~

Example for an ext4 volume:

~~~fstab
UUID=11111111-2222-3333-4444-555555555555 /data ext4 defaults,nofail,x-systemd.device-timeout=30s 0 2
~~~

The UUID in the example is illustrative only. Replace it with the actual UUID. For XFS, the filesystem check pass field is typically set to **0** at the end rather than using fsck ordering like ext4; follow your filesystem and distribution guidance.

### Field Meanings

- **source:** UUID, LABEL, device, or share source.
- **mount-point:** destination directory.
- **filesystem-type:** ext4, xfs, nfs4, cifs...
- **options:** mount options such as **defaults**, **ro**, **rw**, **_netdev**, **nofail**.
- **dump:** typically **0** on modern systems if `dump` is not used.
- **pass:** filesystem check order at boot; the root filesystem follows its own rules.

### Testing fstab Before Rebooting

After editing the file, run:

~~~sh
sudo findmnt --verify --verbose
sudo mount -a
findmnt /data
~~~

**mount -a** attempts to mount eligible entries in fstab. If errors appear, fix them before rebooting. A malformed line can slow down boot or drop the machine into emergency mode depending on configuration.

### Choosing nofail Carefully

**nofail** allows the system to continue booting if a filesystem fails to mount under certain systemd configurations. This can be helpful for data volumes not required for OS boot.

However, if an application requires **/data** and the mount fails, the service might mistakenly write into the **/data** directory on the root filesystem. To prevent this, the service should declare a mount dependency, for example in a systemd unit:

~~~ini
[Unit]
Description=Example application
RequiresMountsFor=/data
~~~

That way systemd knows the service requires this mount point before starting. Check the system's fail/boot policy to choose **nofail** appropriately.

### Mounting on Demand

For infrequently used filesystems, consider **x-systemd.automount** so systemd creates an automount unit and mounts only upon access. This can shorten boot times or handle transient network shares, though you must understand timeouts, behavior when the server disconnects, and application impact.

Do not blindly enable automount for every volume. Workloads requiring the filesystem ready immediately at service start should use explicit dependencies.

## 5. Mount Options and Security Impact

Mount options govern how a filesystem is accessed. Common options include:

| Option | Meaning | When to consider |
|---|---|---|
| **ro** | Read-only | Reference datasets or content that must not be modified |
| **rw** | Read/write | Application volumes that need to write data |
| **noatime** | Skips updating access times in the standard way | Can reduce metadata writes for suitable workloads |
| **nosuid** | Ignores set-user-ID/set-group-ID bits on the mount | Data directories that need no privileged executables |
| **nodev** | Prevents interpreting device nodes on the mount | Most application data areas |
| **noexec** | Prevents executing binaries directly from the mount | Directories holding data or untrusted uploads |
| **nofail** | Prevents mount failures from halting boot | Optional volumes, when services have separate dependencies |
| **_netdev** | Marks a network-dependent filesystem | NFS/SMB and network filesystems |

The **nosuid**, **nodev**, and **noexec** options strengthen security for data areas, but they can break applications if software needs to execute binaries or use device nodes on that mount. Test functionality before enforcing them.

**noexec** is also not an absolute security boundary: an interpreter can still read script contents from a filesystem that disallows direct execution. Combine it with access permissions, file source controls, and proper sandboxing.

## 6. Managing Owner, Group, and POSIX Permissions

On Linux filesystems supporting POSIX permissions, each file or directory typically has:

- Owner user.
- Owner group.
- Read (**r**), write (**w**), and execute/traverse (**x**) permissions for owner, group, and others.

Example **ls -l** output:

~~~text
drwxrws---  root appdata  /data
-rw-r-----  appuser appdata report.csv
~~~

For directories, **x** allows traversing into the directory; **r** allows listing entry names; **w** allows creating/deleting/renaming entries when combined with **x**.

### chmod and chown

~~~sh
sudo chown appuser:appdata /data/report.csv
sudo chmod 0640 /data/report.csv
sudo chmod 2770 /data
~~~

Use **chown** to change owner/group and **chmod** to modify mode bits. Avoid running **chmod -R 777** to fix permission errors. That grants broad permissions to every user and can expose data to unauthorized reading, modification, or deletion.

### Umask

Umask determines which permission bits are masked out when creating new files or directories. For example, umask **0027** typically yields files up to **0640** and directories up to **0750**, depending on the mode requested by the application.

Umask can be configured in the service or user environment. Do not rely solely on umask when multiple applications share a directory; design explicit owner/group and default ACLs.

### Default ACLs

POSIX ACLs allow granting fine-grained permissions to more users/groups than the owner/group/others triad.

Example:

~~~sh
sudo setfacl -m g:analytics:r-x /data
sudo setfacl -d -m g:analytics:r-x /data
getfacl /data
~~~

The first line grants permissions to the **analytics** group on the existing directory; the second sets a default ACL so newly created items inside can inherit appropriate permissions. Effective permissions also depend on the ACL mask and the object's mode. Use **getfacl** to verify the result.

Not all filesystems or network protocols support ACLs identically. NFS, SMB, NTFS, and local filesystems each have their own permission models; understand how client-server mapping behaves.

## 7. Access Permissions on NFS

NFS lets multiple Linux machines mount the same export. Access permissions typically combine server-side export policies, UID/GID identities, and permissions on the server's filesystem.

### UID/GID Must Be Consistent

In the traditional POSIX model, files store numeric UIDs and GIDs. If user **appuser** has UID 1001 on one VM but a different UID on another VM, permissions may behave unexpectedly when both mount the NFS share.

Organizations should use an identity directory or standardize numeric UIDs/GIDs for shared users/groups. Do not rely solely on displayed usernames; verify numeric IDs.

### Root Squash

NFS servers often enable **root_squash**, mapping client `root` privileges to an unprivileged user on the server. This prevents `root` on one VM from automatically acting as `root` across the shared filesystem.

Never disable root squash simply to resolve file-write errors. Grant proper server-side owner/group permissions or use a managed service identity.

### Mounting NFS on Linux

NFSv4.1 mount example:

~~~sh
sudo mkdir -p /mnt/shared
sudo mount -t nfs4 -o vers=4.1,hard,_netdev \
  nfs.example.internal:/exports/team /mnt/shared
findmnt /mnt/shared
~~~

Server names and exports in the example are illustrative. Before mounting, check DNS, routes, firewall/security groups, and export permissions. NFS typically uses TCP 2049, though you must verify the exact protocol and service configuration.

With NFS, the **hard** option is commonly used so the client keeps retrying I/O operations when the server stops responding, avoiding premature write errors in some scenarios. However, processes can block for a long time if the server disconnects. Design application-level timeouts, monitoring, and recovery plans. Do not switch arbitrarily to **soft**, because I/O errors returned to applications can cause data corruption if software handles them improperly.

### Persistent NFS Mounts

Example fstab:

~~~fstab
nfs.example.internal:/exports/team /mnt/shared nfs4 rw,hard,_netdev,nofail,x-systemd.automount 0 0
~~~

Tailor options to network policies, availability requirements, and how applications use the share. If a service strictly requires the share, declare **RequiresMountsFor=/mnt/shared** or an equivalent dependency instead of letting the application create the folder and mistakenly write to the root filesystem.

## 8. Access Permissions on SMB/CIFS

SMB is commonly used for Windows file shares and can be mounted from Linux via CIFS. Effective access can be governed simultaneously by share permissions and NTFS ACLs on the server. In many models, effective permission is the more restrictive of the two layers.

### Mounting SMB on Linux

Install the CIFS utilities package appropriate for your distribution, then mount the share. Never place passwords directly in commands or fstab, as they can leak via shell history, process lists, or configuration files.

Example using a credentials file:

~~~sh
sudo install -d -m 0755 /mnt/team
sudo install -d -m 0700 /etc/samba
sudo install -m 0600 /dev/null /etc/samba/team.cred
~~~

The credentials file should be populated via a proper secret management mechanism and readable only by root. Illustrative content structure, containing no real secrets:

~~~text
username=SERVICE_ACCOUNT
password=RETRIEVED_SECRET
domain=EXAMPLE
~~~

Mount command:

~~~sh
sudo mount -t cifs //files.example.internal/team /mnt/team \
  -o credentials=/etc/samba/team.cred,vers=3.1.1,uid=1001,gid=1001,file_mode=0640,dir_mode=0750
~~~

The **uid**, **gid**, **file_mode**, and **dir_mode** options control how permissions are presented on the client in certain mount modes. When the server enforces ACLs and domain authentication, server-side permissions remain decisive. Check the SMB version and the service's signing/encryption policies.

### Persistent SMB Mounts

You can specify the share source and credentials file in fstab:

~~~fstab
//files.example.internal/team /mnt/team cifs credentials=/etc/samba/team.cred,vers=3.1.1,_netdev,nofail,x-systemd.automount 0 0
~~~

Never put a password directly in an fstab line. Protect the credentials file with strict permissions, scope the service account narrowly, and rotate credentials regularly.

## 9. Mounting and Permissions on Windows

### Identifying a New Disk

After attaching a managed disk, inspect it with PowerShell:

~~~powershell
Get-Disk
Get-Partition
Get-Volume
~~~

Cross-check disk number, capacity, status, and volume info against the attached resource. Do not rely solely on the disk number, as ordering can shift after infrastructure changes.

### Initializing and Formatting a New Volume

The example below is strictly for a new, blank disk with a verified disk number:

~~~powershell
# Run only after confirming Disk 2 is a new disk containing no data.
Initialize-Disk -Number 2 -PartitionStyle GPT

$partition = New-Partition -DiskNumber 2 -UseMaximumSize -AssignDriveLetter
Format-Volume -Partition $partition -FileSystem NTFS -NewFileSystemLabel "AppData"
~~~

**Initialize-Disk** and **Format-Volume** can destroy existing structures or data. For disks already containing data, never run these commands; identify the filesystem and volume before assigning a mount point.

### Assigning a Drive Letter or Mount Folder

Windows can assign a volume to a drive letter such as **E:** or mount it into an empty NTFS folder. Manage this via Disk Management, Storage cmdlets, or appropriate tooling.

Drive letters usually persist across reboots, though you should verify them after disk or machine configuration changes. For applications needing stable paths, you can use mount folders and track them in inventory.

### NTFS ACLs with icacls

Example granting Modify permission to a service account on a data directory:

~~~powershell
icacls D:\AppData /grant "EXAMPLE\AppSvc:(OI)(CI)M"
icacls D:\AppData
~~~

**OI** and **CI** allow permissions to inherit down to files and subdirectories; **M** stands for Modify. Preserve Administrators and SYSTEM permissions according to your organization's baseline. Never run **/reset** or strip inheritance on production directories without understanding the full inherited ACL chain.

### Share Permissions vs. NTFS Permissions

For Windows SMB shares, remote access is governed by both share permissions and NTFS ACLs. A user granted Full Control on the share but only Read in NTFS remains restricted to Read by NTFS. Test using the actual client and server accounts to verify effective permissions.

## 10. Securing Filesystems and Data

Mounting merely exposes data in the directory tree; it does not automatically protect the data. Coordinate multiple security layers.

### Encryption at Rest

Use volume or filesystem encryption per platform capabilities:

- Cloud-managed encryption or customer-managed keys for block volumes.
- Data encryption on file services according to service features.
- LUKS or guest-level filesystem encryption when the organization needs to manage the encryption layer inside the guest.
- Key policy, rotation, and decryption permissions tailored to each environment.

If using guest-level encryption, ensure keys remain accessible at boot and a recovery procedure exists when the VM is replaced. Never store passphrases or key material inside images or fstab.

### Encryption in Transit

For network file shares, use appropriate protocol versions and security settings. SMB supports encryption depending on version/configuration; NFS can use identity protection and privacy mechanisms such as Kerberos or platform-supported network encryption. Never assume every NFS/SMB connection is encrypted automatically.

### Least Privilege

- Mount read-write only when the application needs to write.
- Use **ro** for read-only datasets.
- Grant owner/group/ACL permissions to the exact service account.
- Avoid **777** and avoid running applications as root.
- Use **nosuid**, **nodev**, and **noexec** where compatible.
- Restrict network access to NFS/SMB via security groups, firewalls, and private endpoints.
- Separate untrusted upload directories from executable directories.

### SELinux and AppArmor

Even when Unix mode bits permit access, SELinux or AppArmor can still block a process. On Linux systems using SELinux, inspect contexts with:

~~~sh
ls -Zd /data
sudo ausearch -m AVC -ts recent
~~~

If contexts are wrong, use policy tools such as **semanage fcontext** and **restorecon** following system standards. Never disable SELinux simply to make an application run.

AppArmor can likewise restrict which paths a process may access. Check profiles and audit logs whenever permission errors occur despite seemingly correct ownership and groups.

## 11. Filesystems in Containers

Containers typically use the host filesystem along with mounts declared when launching the container or pod.

Common mount types:

- Bind mount: maps a specific host path into the container.
- Named volume: lifecycle managed by the container runtime or orchestrator.
- Persistent volume: storage resource orchestrated independently of the pod lifecycle.
- Ephemeral volume: temporary data tied to the container or pod lifecycle.

Watch out for UID/GID inside the container mismatching ownership on the host. A container running as user 10001 may fail to write to a host directory owned by UID 1000. Design consistent user/group mappings or use appropriate permission mechanisms.

In Kubernetes, `PersistentVolume` and `PersistentVolumeClaim` describe storage resources; `StorageClass` can provision volumes dynamically. Access modes indicate the access patterns a volume supports, though not every mode guarantees safe concurrent writes from multiple nodes. Always inspect the actual capabilities of the driver and filesystem.

Example read-only mount in a Pod:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: report-reader
spec:
  containers:
    - name: reader
      image: example/report-reader:1.0
      volumeMounts:
        - name: reports
          mountPath: /reports
          readOnly: true
  volumes:
    - name: reports
      persistentVolumeClaim:
        claimName: reports-pvc
~~~

This example illustrates mount structure only; PVCs and access permissions must match your cluster's storage driver, namespace, and policies. With SELinux, certain runtimes require corresponding labels or mount options. Never grant broad permissions on host paths just to bypass permission errors.

## 12. Safely Unmounting and Detaching Volumes

Before detaching a block volume or disconnecting a file share, stop applications using the data. If processes still hold open files, unmounting may fail with `busy` or introduce consistency risks.

### On Linux

~~~sh
sudo fuser -vm /data
sudo lsof +f -- /data
sudo sync
sudo umount /data
findmnt /data
~~~

Only after confirming the filesystem is unmounted should you detach the volume in the cloud console/API. If nested mounts or bind mounts exist underneath, handle them in the proper order.

Do not use **umount -f** or lazy unmount as a default way to override busy errors. First identify the processes using the mount and stop them cleanly. For disconnected NFS shares, operations may hang; follow the service's recovery procedure.

### On Windows

Stop services and applications using the volume, close open file handles, verify no workload is writing data, and then remove the drive letter/mount point or take the disk offline before detaching per platform guidelines. Never detach a disk while an application is using it or writes remain unfinished.

### Backups and Snapshots

Block volume snapshots can provide disk-level recovery points. For databases or actively writing applications, snapshots do not automatically guarantee application consistency. Use native backups, flush/quiesce hooks, or platform-supported application-consistent snapshot mechanisms.

Mounting, unmounting, and detaching do not replace backups. Periodically verify restore capability, encryption key access, and recovery times.

## 13. Mount Performance and Availability

A filesystem can mount cleanly yet fail to meet workload performance requirements. Factors to review:

- Volume type, provisioned IOPS, and throughput.
- Queue depth and latency at the block device level.
- Filesystem type and block size.
- Sequential/random and read/write access patterns.
- Multiple processes contending on the same file or directory.
- Network latency and bandwidth for NFS/SMB.
- Client and server caching behavior.
- Open file limits, inodes, and metadata operations.
- File sizes and small-file counts.

With network filesystems, losing connectivity can stall or block I/O operations. Applications need timeouts, bounded retries, and graceful error handling when the share is unavailable. Never let a service write critical data into a fallback directory on the root disk when mounting the share fails.

### Monitoring Capacity and Inodes

On Linux:

~~~sh
df -hT
df -i
du -xhd1 /data
findmnt --target /data
~~~

A filesystem can run out of inodes even while byte capacity remains free. Track capacity, inodes, file counts, and growth rates.

### Monitoring I/O

~~~sh
iostat -xz 1
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
~~~

**iostat** typically comes from the `sysstat` package. Cross-reference guest metrics with cloud provider volume metrics. A VM-level or volume-level cap can bottleneck a workload even when the filesystem and permissions are configured properly.

## 14. Mount Errors and Troubleshooting

| Symptom | Common cause | What to check |
|---|---|---|
| **wrong fs type** or unrecognized filesystem | Missing filesystem, missing driver/tools, or wrong device selected | **lsblk -f**, **blkid**, verify filesystem packages; never format before verifying data |
| **already mounted** | Filesystem is already mounted elsewhere | **findmnt**, inspect mount points and fstab |
| **mount point does not exist** | Target directory has not been created | Create the mount point and check ownership |
| **permission denied** | Wrong owner/group/ACL, export policy, SMB share ACL, or identity | **id**, **namei -l**, **getfacl**, inspect server-side permissions |
| **device is busy** when unmounting | Process holds open files or working directory inside mount | **fuser -vm**, **lsof**, stop the service cleanly |
| Slow boot or drops into emergency mode | Bad fstab entry, missing device, or network share not ready | **findmnt --verify**, systemd journal, UUID, and **_netdev** |
| NFS timeout | DNS, routing, firewall, export, or server unavailable | Check endpoint, TCP 2049, export policy, and logs |
| SMB mount failure | Credentials, dialect, DNS, port, or share ACL | Check credentials file, SMB version, TCP 445, and share permissions |
| App cannot write even though mounted | Service user lacks permission, UID/GID mapping, or SELinux/AppArmor | Check process identity, ACLs, and audit logs |
| App writes to root disk instead of volume | Mount failed while the mount-point directory still exists | Readiness/dependency **RequiresMountsFor**, verify **findmnt** before start |

### Investigation Workflow

1. Confirm the resource is attached at the cloud provider.
2. Check the device or network endpoint seen by the operating system.
3. Identify the actual filesystem and mount point using **lsblk**, **findmnt**, or Windows tools.
4. Read kernel, systemd, NFS/SMB client, or VM agent logs.
5. Verify networking, DNS, firewalls, and server-side permissions.
6. Verify owner/group/ACLs and OS security policies.
7. Test access as the exact application user.
8. Fix configuration and verify with test mounts or validation commands.
9. Test reboot or reconnect before promoting to production.

Never run **fsck** or filesystem repair tools on a filesystem mounted read-write. For XFS, use specialized tools such as **xfs_repair** following official instructions and the proper mount state. Before repairing, ensure you have a backup/snapshot and understand the risks.

## 15. Example: Mounting a Data Volume for a Linux Service

A web service stores uploaded files at **/srv/app-data**. The operations team attaches a new block volume and needs it mounted persistently with write access restricted to the application user.

Workflow:

1. Cross-check volume ID and size in the cloud console.
2. Run **lsblk -f** to identify the new device.
3. Verify the device holds no data that needs to be preserved.
4. Create the filesystem according to your chosen standard.
5. Obtain the UUID and create the **/srv/app-data** mount point.
6. Add the UUID to fstab with appropriate options.
7. Run **findmnt --verify** and **mount -a**.
8. Create the **appdata** group and grant permissions to the service account.
9. Add **RequiresMountsFor=/srv/app-data** to the systemd unit.
10. Test read/write as the application user and test rebooting in staging.

Illustrative fstab configuration:

~~~fstab
UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee /srv/app-data ext4 defaults,nofail,x-systemd.device-timeout=30s 0 2
~~~

Illustrative directory permissions:

~~~sh
sudo groupadd --force appdata
sudo usermod -aG appdata appuser
sudo chown root:appdata /srv/app-data
sudo chmod 2770 /srv/app-data
sudo -u appuser touch /srv/app-data/write-test
sudo -u appuser rm /srv/app-data/write-test
~~~

Before deleting the test file, verify it is the exact file just created. In production, verify the application refuses to start if the mount is missing, and ensure the volume is backed up per data policy.

## 16. Pre-Production Checklist for Mounts

- [ ] Identified the right storage type: block, file, or object.
- [ ] Matched volume/share IDs with the device or endpoint inside the machine.
- [ ] Checked for an existing filesystem before formatting.
- [ ] Selected a filesystem suited to the OS and workload.
- [ ] Selected a mount point that does not obscure data to keep.
- [ ] Used UUIDs or stable identifiers for block volumes.
- [ ] Validated fstab using **findmnt --verify** and **mount -a**.
- [ ] Defined clear behavior when the volume or network share is unavailable.
- [ ] Configured service dependencies/readiness so it never writes mistakenly to the root filesystem.
- [ ] Enforced least privilege for owner, group, mode, and ACLs.
- [ ] Standardized UID/GID mappings if using NFS or shared filesystems.
- [ ] Protected SMB credentials and kept them out of command history and fstab.
- [ ] Enabled encryption at rest and in transit per requirements.
- [ ] Restricted network access to NFS/SMB to required machines only.
- [ ] Checked SELinux/AppArmor policies if active.
- [ ] Tested access using the exact service account.
- [ ] Verified capacity, inodes, latency, and throughput.
- [ ] Tested reboot, reconnect, unmount, and detach workflows.
- [ ] Configured backups and verified restore capability.
- [ ] Set up logs, alerts, and runbooks for mount failures.

## Conclusion

For applications to use data reliably, you must complete the full chain: attach, device discovery, filesystem setup, mounting, and permissions. Block storage typically requires a local filesystem; file storage is mounted via NFS/SMB; object storage is typically accessed via API and should use gateways only when semantics fit. Persistent mounts require stable identifiers, fstab validation, explicit dependencies, and safe handling when storage is unavailable. Proper owner/group/ACL permissions, encryption, network policies, and testing with the actual service account ensure data remains accessible only to authorized processes throughout the machine's lifecycle.
