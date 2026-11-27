# OS Disks, Data Disks, and Temporary Disks

## 1. Why Distinguish the Three Disk Types on an Azure VM?

When deploying a Virtual Machine (VM) on Microsoft Azure, learners often see multiple drives inside the operating system. Windows may show **C:** and **D:** drives; Linux shows a device holding the root partition **/**, one or more data devices, plus a temporary storage area. They are not identical in purpose, data persistence, management, or cost.

A dangerous mistake is storing a database or user files on the **temporary disk**, then performing an operation that moves the VM to another host and loses all data. Another misconception is thinking shutting down a VM deletes everything on its **data disk**. Understanding storage lifecycles is a prerequisite before deploying stateful applications.

This lesson belongs to the **File and Disk Storage** section of the Azure ecosystem, directly connecting VM operations, networking, data, security, monitoring, and cost control. After this lesson, you will be able to:

1. Distinguish **OS disks**, **data disks**, and **temporary disks** in function and data durability.
2. Understand **managed disks** and how standard OS disks differ from **ephemeral OS disks**.
3. Choose disk SKUs, capacity, and performance based on application characteristics.
4. Attach data disks to a VM, then initialize, partition, format, and mount them safely on Linux/Windows.
5. Determine where caches, swap, and intermediate files belong versus where backups are mandatory.
6. Explain whether data survives or is lost during VM reboot, stop/deallocate, resize, redeploy, or deletion.
7. Apply backup, encryption, authorization, monitoring, and cost-management principles.

## 2. Big-Picture View of a VM's Disk Structure

An Azure VM pairs compute capacity with distinct storage resources. In standard setups, **OS disks** and **data disks** are Azure Managed Disks; the **temporary disk** is typically local storage on the host running the VM, if provided by the chosen VM size.

~~~mermaid
flowchart TB
    VM[Azure Virtual Machine]
    VM --> OS[OS disk: operating system and boot]
    VM --> D1[Data disk 0: application data]
    VM --> D2[Data disk 1: additional data]
    VM --> T[Temporary / local disk: data can be lost]
    OS --> MD[Managed Disk storage]
    D1 --> MD
    D2 --> MD
    T --> HOST[Local storage on host]
~~~

This diagram is a conceptual model. A VM might not include a temporary disk; some VMs also support **ephemeral OS disks**, storing the OS on suitable local host storage instead of a separate persistent OS managed disk. How devices map to drive letters in Windows or device names in Linux also depends on VM size, controller, image, and guest configuration.

### 2.1. Quick comparison table

| Criterion | Standard OS disk | Standard data disk | Temporary disk |
|---|---|---|---|
| Role | Holds OS, boot files, system utilities | Holds data or apps needing long-term persistence | Holds temporary, regenerable data |
| Typical backing storage | Azure Managed Disk | Azure Managed Disk | Local storage on VM host |
| Data on VM stop/deallocate | Generally preserved if disk is not deleted | Generally preserved if disk is not deleted | Not guaranteed; may be lost |
| Data on moving VM to another host | Managed disk is typically reattached | Managed disk is typically reattached | May be replaced or wiped |
| Manageable as standalone Azure disk | Yes, for OS managed disks | Yes | Not as a standard managed disk |
| Best suited for | OS, VM configuration | Databases, stateful apps, persistent files | Caches, scratch, temp files, regenerable data |
| Backup | Use Azure Backup/suitable solution | Back up per RPO/RTO requirements | Never treat as backup-worthy primary storage |
| Cost | Incurs managed disk charges | Priced by SKU/size/performance attributes | Bundled with VM size, not billed as separate managed disk |

**Rule of thumb:** data that **must not be lost** belongs on durable storage with proper backups and recovery. Never rely on drive letters like **D:** or device names like **/dev/sdb** to decide whether storage is persistent.

## 3. OS Disk: The Operating System Boot Drive

The **OS disk (operating system disk)** holds the operating system needed to boot the VM. It is typically created when deploying a VM from a Windows or Linux image.

Components that reside on the OS disk:

- Bootloader, root filesystem, and OS binaries.
- Service configurations, packages, agents, and host settings.
- On Windows, typically mapped to system drive **C:**.
- On Linux, typically holds the **/** filesystem and boot partitions.

When you install software directly on a VM without specifying another path, data may be written to the OS disk. For example, application logs or upload folders placed under the OS partition can fill the disk, destabilizing both the OS and applications.

### 3.1. An OS managed disk is durable storage

In the standard managed disk model, the OS disk resides on Azure Disk Storage infrastructure rather than relying on volatile memory on one compute host. When a VM is stopped and deallocated, the OS managed disk **does not automatically lose data** merely due to deallocation, provided the disk is not deleted by an operation or management policy.

This does **not** mean the OS disk is automatically backed up. Accidental file deletion, overwritten configs, ransomware encryption, or deleting the managed disk still causes data loss. Independent backup/recovery mechanisms are required.

### 3.2. A VM typically has one OS disk

A running VM has one OS disk used for booting. When swapping OS disks, creating a VM from an existing disk, or performing restores, follow VM state restrictions, OS constraints, and image types. Never treat swapping a boot disk like unplugging a live USB drive.

### 3.3. Should the OS disk hold application data?

Technically, applications can write data onto the OS partition. However, for long-lived systems, consider separating **data disks** or using dedicated storage services because:

- OS capacity and application data capacity are tracked independently.
- Reduces risk of the OS running out of space due to logs, uploads, or databases.
- Supports cleaner backup and data lifecycle workflows.
- Simplifies replacing, reimaging, or upgrading VMs without tying all data to the boot disk.

Still, do not split every directory mechanically. Simple systems may use the OS disk with appropriate backups; decide based on RPO/RTO, traffic, cost, and acceptable complexity.

## 4. Caution: An Ephemeral OS Disk Is Not a Standard Managed OS Disk

Azure supports **ephemeral OS disks** on eligible VM sizes and configurations. It places the OS disk on suitable local host storage rather than creating a separate traditional persistent managed OS disk.

Notable properties:

- Can speed up VM creation or reimaging, especially for **stateless** workloads.
- The OS is treated as **recreatable from image**; data written to the OS disk is not preserved across lifecycle events like reimage, deallocate, or host replacement.
- Suits certain VM Scale Sets, temporary processing pools, workers, or environments where reprovisioning fresh machines is normal.
- Unsuitable if the sole copy of critical data resides on the OS disk.
- Support and maximum size depend on VM size, local OS cache/temp space, image, and current Azure limits.

**An ephemeral OS disk differs from a temporary disk.** Both may use local host storage, yet one serves as the **OS boot drive** while the other serves as **temporary scratch storage**. They have distinct roles and lifecycle policies.

When designing a stateful VM, explicitly verify whether its OS disk is a **persistent managed OS disk** or an **ephemeral OS disk**. Never guess based on drive names visible inside the OS.

## 5. Data Disks: Persistent Storage Space for Applications

A **data disk** is an additional disk attached to a VM to store files, databases, logs, application data, or content managed independently of the OS.

An Azure Managed Data Disk can:

- Be created independently and attached to a VM.
- Be attached or detached via supported workflows without necessarily sharing the VM's deletion lifecycle.
- Have its own capacity, SKU, performance profile, and caching mode.
- Be partitioned and formatted by the guest OS.
- Be backed up or snapshotted per application policies.

Maximum data disk count and aggregate VM throughput/IOPS depend on VM size, bus/controller, and supported infrastructure. Do not assume you can attach an unlimited number of disks.

### 5.1. New data disks are usually not ready for files immediately

When you attach a **brand-new** managed disk to a VM, the OS sees the raw block device without partitions, filesystems, or drive letters/mount points.

Therefore, you must:

1. Identify the exact new device.
2. Initialize a partition table if needed.
3. Create partitions and a filesystem per OS conventions.
4. Mount or assign a drive letter.
5. Verify access permissions and persistence across reboots.
6. Configure capacity, performance, and backup monitoring.

**If attaching a disk that already holds data, never reformat it.** Simply verify the filesystem and mount it properly. Formatting overwrites existing storage structures and causes data loss.

### 5.2. Logical Unit Number (LUN)

In SCSI-based models, each data disk attached to a VM is assigned a **LUN**, such as 0, 1, or 2. Azure uses LUNs to distinguish attached disks. A LUN is not Windows drive order **C:**, **D:**, **E:**; nor does it reliably equal Linux device names like **/dev/sdc** or **/dev/sdd**.

Some newer VM generations use NVMe for data paths, so device identification differs from traditional SCSI. In production systems, cross-check **Azure disk resource ID/LUN, capacity, serial, and OS device metadata** rather than trusting a single device letter.

## 6. Temporary Disk: Local Storage Where Data Can Be Lost

The **temporary disk**—also called **resource disk** or **local temporary storage** in some docs—is storage attached to the physical host running the VM. It can deliver strong speed for certain workloads but carries **no long-term data persistence guarantee**.

On many Windows VMs, the temporary disk often takes drive letter **D:** and may hold the pagefile. On some Linux images, it may mount at **/mnt**, **/mnt/resource**, or elsewhere. Some VM families provide local NVMe, while some VM sizes have no temporary disk at all. Drive letters and mount points are only hints.

Data types that **can** reside on a temporary disk if the app tolerates complete loss:

- Caches rebuildable from durable sources.
- Scratch files for short-lived processing.
- Temporary downloads during data transformation.
- Intermediate data for rerunnable batch jobs.
- Certain swap/pagefiles per OS configuration and VM image guidance.

Data types that **should never** reside solely on a temporary disk:

- Primary databases or critical transaction logs.
- User-uploaded files not yet durably persisted elsewhere.
- Irreplaceable secrets, private keys, certificates, or configs.
- The system's sole backup copy.
- Critical session state lacking sync/recovery mechanisms.
- Files that must survive VM host migration or recreation.

**Operational rule:** every time you write to a temporary disk, ask: "If this entire volume vanished right now, could the application still function and recover cleanly?" If the answer is **no**, that storage location is unsuitable.

## 7. What Happens to Data When a VM Changes State?

Not every VM lifecycle action carries the same consequences. The table below outlines **safe design principles**, not a guarantee that bytes remain untouched in every edge case.

| Scenario | Standard managed OS disk | Managed data disk | Temporary disk |
|---|---|---|---|
| Reboot inside guest OS | Typically preserved | Typically preserved | Often persists, **never rely on it** |
| Stop/deallocate VM | Preserved if not deleted | Preserved if not deleted | May be lost/reinitialized |
| Resize VM | Managed disk remains independent if not deleted | Managed disk remains independent if not deleted | May be lost when changing hosts |
| Redeploy to another host | Reattached or recovered via managed platform | Reattached or recovered via managed platform | May be completely wiped |
| Host maintenance/failure | Depends on storage redundancy and platform recovery | Depends on storage redundancy and platform recovery | No guarantee of content retention |
| Delete VM | Depends on **delete option** and disk deletion actions | Depends on **delete option** and disk deletion actions | Does not exist as a standalone persistent disk |

**Never assume "deleting a VM always preserves managed disks."** Azure VMs have **delete option** properties on OS and data disks—such as deleting with the VM or detaching/retaining per config. Verify before deleting to avoid data loss or orphaned billed resources.

For **ephemeral OS disks**, lifecycle differs from standard managed OS disks. They are designed to reimage on corresponding lifecycle events; never rely on changes stored on an ephemeral OS disk for persistence.

### 7.1. Stop and deallocate differ in VM compute billing

Shutting down from inside the guest OS may not mean Azure compute resources are **deallocated**. When stopping compute billing, verify the actual VM state in Azure. Even when compute is deallocated, **standalone managed disks and related resources can continue accruing charges**.

Never intentionally wipe temporary disk data on live systems to "verify behavior"; run such tests strictly in isolated labs with disposable dummy data.

## 8. Selecting Azure Managed Disk Types

Managed disks come in multiple SKUs tailored for different latency, IOPS, throughput, and cost profiles.

| Disk tier | General characteristics | Typical use cases |
|---|---|---|
| **Standard HDD** | Lower cost, lower performance, HDD-backed storage | Light loads, infrequent access, latency-insensitive environments |
| **Standard SSD** | SSD balancing cost and performance | General-purpose apps, dev/test environments |
| **Premium SSD** | SSD for higher-performance workloads; throughput scales with size/tier | Application servers, databases, production |
| **Premium SSD v2** | Independent sizing of capacity and performance within supported bounds | Data disks with flexible IOPS/throughput requirements |
| **Ultra Disk** | High-performance provisioning within supported feature/SKU bounds | Workloads highly sensitive to I/O performance |

Depending on SKU, not every disk can serve as an **OS disk**. For instance, **Premium SSD v2** and **Ultra Disk** are designed for data disks, subject to regional and VM-size support; do not pick them for boot drives where unsupported.

Specifications to verify from product documentation and deployment options:

- Minimum, maximum, and increment sizes.
- Provisioned IOPS and throughput by size/SKU or configuration.
- Bursting capabilities.
- Support for Availability Zones, redundancy, and shared disks.
- Support for host caching, snapshots, backups, encryption, and online resizing.
- Aggregate I/O limits of the chosen VM size.

### 8.1. Performance is not determined by the disk alone

Application throughput is constrained by **both the disk and the VM**. For example, a data disk may offer high potential IOPS, yet the VM size or bus/controller cannot push that volume of I/O to the disk.

Measure:

1. IOPS from real workloads.
2. Average read/write request size.
3. Throughput in MB/s.
4. Application- and OS-level latency.
5. Disk limits and VM uncached/cached throughput limits.
6. Workload CPU utilization and I/O queue depth.

Never pick Premium/Ultra solely from stored file size. A small database might demand intense IOPS, whereas a large, rarely accessed archive might fit a more economical SKU.

### 8.2. Disk caching

Certain Azure managed disks and VM sizes support **host caching** modes such as **None**, **ReadOnly**, or **ReadWrite**, depending on disk/SKU combination and workload type.

- **ReadOnly** can accelerate workloads with repeated reads.
- **ReadWrite** requires careful review of data consistency requirements and application guidance.
- **None** suits write-heavy workloads or cases mandated by service specifications.

Never enable caching on databases by guesswork. Supported modes, cache behavior, and recommendations differ across OS disks, data disks, and SKUs. Check documentation for your OS, database engine, and Azure disk service.

## 9. Choosing Storage Locations by Workload Nature

| Data | Recommended location | Rationale |
|---|---|---|
| Windows/Linux OS | OS disk | Boot drive and system configuration |
| Database running inside VM | Appropriately sized managed data disk | Durable, independent capacity/IOPS tuning and backups |
| Long-term user files | Managed data disk or Azure Blob/Files per app design | Supports backups, access control, and recovery |
| Regenerable image thumbnail caches | Temporary disk when supported by VM | Uses local storage without retention overhead |
| Intermediate processing files | Temporary disk if loss allows rerun | Reduces durable storage dependence for scratch |
| Logs for investigation and compliance | Managed disk and/or shipped to central logging | Avoid losing evidence on VM host changes |
| Backups | Azure Backup, Recovery Services vault, or suitable solution | Isolated from production disk lifecycle |
| Data needed across multiple VMs | Azure Files, Blob, managed DBs, or shared disks where supported | A standard data disk is not automatically a multi-VM file share |

**Shared disk** is a specialized feature on supported managed disks/SKUs allowing block-level sharing for compatible clustered systems. Exposing one disk to multiple machines **does not** automatically create safe file sharing. You need a cluster-aware filesystem/cluster manager or a storage service built for multi-client access.

## 10. Design Example: Java Application Running on a Linux VM

Suppose a development team deploys a Java API onto an Azure Linux VM. The API processes uploaded files, generates thumbnail images, and writes logs.

**Poor initial design:**

- Both application binaries and business data write into the OS partition.
- Pre-processed uploads are staged on the temporary disk without durable persistence.
- Logs live solely on the temporary disk, vanishing whenever the VM redeploys.
- No data disk backups or restore tests exist.

**Improved design:**

| Component | Storage location | Policy |
|---|---|---|
| OS, packages, Java runtime | OS managed disk | Patch images and back up as required |
| Persistent app config | Secure config store, optionally paired with suitable disk | Versioned config and access control |
| Persistent internal data | Managed data disk mounted at `/data` | Backups, monitoring, capacity thresholds |
| User-uploaded files | Azure Blob Storage or Managed Disk per design | Ensure durable write before returning success |
| Thumbnail cache files | Temporary/local storage | Evictable and regenerable from source |
| Critical logs | Azure Monitor/Log Analytics or central log system | Shipped off-VM for diagnostics and audit |
| Secrets | Azure Key Vault/managed identity where applicable | Never hardcoded or stored solely on temporary disk |

The system may later evolve to App Service, containers, or managed data services, yet the principle of **separating persistent from ephemeral storage** remains unchanged.

## 11. Inspecting Disk Configuration in Azure Portal

Inspection workflow for an Azure VM:

1. Sign in to the Azure Portal with read access to the VM, disks, and resource group.
2. Open **Virtual machines** and select the target VM.
3. Open the **Disks** blade.
4. Identify the **OS disk** and **Data disks** list, disk resources, sizes, SKUs, and attachment status.
5. Check **LUN**, host caching, and editable properties.
6. Check lifecycle **Delete with VM / Detach** options if visible.
7. For individual disk resources, inspect region, zone, SKU, size, and properties.
8. Cross-check results against volumes/drives appearing **inside the VM**.

The temporary disk may appear inside the guest OS while **not appearing as an independent managed data disk** in Azure's managed disks list. Recognizing this prevents formatting or backing up the wrong volume.

Verify whether your actual VM image/size provides local temporary storage and how the OS mounts it; never assume every Windows VM has `D:` or every Linux VM has `/mnt/resource`.

## 12. Inspecting OS Disks and Data Disks with Azure CLI

Example using Azure CLI to query disk properties on an existing VM. Commands below **do not run automatically in this lesson**; substitute resource group and VM details for your authorized environment.

~~~bash
az login
az account set --subscription "<subscription-id>"

az vm show \
  --resource-group rg-vm-storage-lab \
  --name vm-app-01 \
  --query "storageProfile.{osDisk:osDisk,dataDisks:dataDisks}" \
  --output json
~~~

`storageProfile.osDisk` and `storageProfile.dataDisks` show the disks configured on the VM. Managed disks typically expose `managedDisk.id`, `diskSizeGB`, `caching`, and other properties depending on setup.

List managed disks in the resource group:

~~~bash
az disk list \
  --resource-group rg-vm-storage-lab \
  --query "[].{name:name,sizeGB:diskSizeGB,sku:sku.name,state:diskState,managedBy:managedBy}" \
  --output table
~~~

Show a specific data disk:

~~~bash
az disk show \
  --resource-group rg-vm-storage-lab \
  --name disk-appdata-01 \
  --query "{name:name,sizeGB:diskSizeGB,sku:sku.name,state:diskState,managedBy:managedBy}" \
  --output json
~~~

**Note:** an attached data disk shows attached status and references its managing VM. However, Azure disk metadata cannot tell you whether the internal filesystem is mounted, what files exist inside, or whether applications are actively using it. Check inside the guest OS for that.

## 13. Creating and Attaching a Managed Data Disk via Azure CLI

Assume VM **vm-app-01** already exists in resource group **rg-vm-storage-lab**. Create a new 64 GiB Standard SSD data disk:

~~~bash
az disk create \
  --resource-group rg-vm-storage-lab \
  --name disk-appdata-01 \
  --size-gb 64 \
  --sku StandardSSD_LRS
~~~

Attach the disk to the VM:

~~~bash
az vm disk attach \
  --resource-group rg-vm-storage-lab \
  --vm-name vm-app-01 \
  --name disk-appdata-01 \
  --lun 0
~~~

Verify:

~~~bash
az vm show \
  --resource-group rg-vm-storage-lab \
  --name vm-app-01 \
  --query "storageProfile.dataDisks[].{name:name,lun:lun,sizeGB:diskSizeGB,managedDisk:managedDisk.id}" \
  --output table
~~~

**Prerequisites before running:**

- Resource group, VM, region, and disk SKU must match Azure-supported combinations.
- VM size has available LUNs and I/O headroom for the new data disk.
- LUN 0 is unused.
- Operator holds permissions to create disks and modify the VM.
- Disk and zone settings are compatible with the VM.
- Managed disk cost implications are understood.

After attaching, the OS may still see an unusable **raw disk**. Complete the Linux or Windows preparation steps below.

**Do not** use this example to attach and format disks on production VMs without approval and explicit verification of the target new disk.

## 14. Safely Preparing a Data Disk on Linux

Linux may present disks as **/dev/sdc**, **/dev/sdd**, or **/dev/nvme...**, depending on image and bus. Device names are **not immutable identifiers**.

### 14.1. Identifying the right disk

Inside the Linux VM, inspect block devices:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL
sudo blkid
findmnt /
findmnt /data
~~~

Compare sizes, device names, filesystems, and Azure Portal/CLI metadata. Also check stable device aliases provided by Azure images if available. On some SCSI systems, **/dev/disk/azure/** contains LUN-mapped symlinks; NVMe systems may expose devices differently.

**Stop if you are unsure which device is the new disk.** Never format a device merely because a guide happened to call it **/dev/sdc**.

### 14.2. Creating a filesystem on a verified empty new disk

Assuming an administrator verified a brand-new empty device, substitute the confirmed device path:

~~~bash
# RUN ONLY ON A NEW DATA DISK VERIFIED TO CONTAIN NO DATA
sudo mkfs.ext4 /dev/<confirmed-new-data-device>

sudo mkdir -p /data
sudo mount /dev/<confirmed-new-data-device> /data

findmnt /data
df -h /data
~~~

Where partition tables are needed, create a partition first with the appropriate tool and format the **partition**, avoiding formatting the wrong raw device. The example above puts a filesystem directly on the block device for clarity; real operational environments may choose GPT, LVM, RAID, or other volume managers.

**Data loss warning:** `mkfs.ext4` writes a new filesystem and destroys existing structures. Never paste it blindly without verifying the new disk, data state, LUN, and device path.

### 14.3. Automatic mounting across reboots

Manual mounting alone does not survive reboots. On Linux, **/etc/fstab** with filesystem UUIDs is commonly used:

~~~bash
sudo blkid /dev/<confirmed-new-data-device>
~~~

Sample entry in **/etc/fstab**:

~~~text
UUID=<uuid-from-blkid> /data ext4 defaults,nofail 0 2
~~~

Substitute the actual filesystem UUID and test configuration before rebooting. Using UUIDs is more resilient than hardcoding **/dev/sdc**, because device names can shift across infrastructure changes.

After saving the file, test mounting:

~~~bash
sudo mount -a
findmnt /data
df -h /data
~~~

Errors in filesystem entries or mount options can prevent smooth booting; edit **/etc/fstab** only when you understand paths, UUIDs, and recovery mode. **nofail** lets the system boot if the volume is unavailable, yet dependent applications should still verify the mount so they do not accidentally write into an empty directory on the OS disk.

### 14.4. Permissions and directory layout

After mounting, create application folders and set appropriate ownership/permissions:

~~~bash
sudo mkdir -p /data/app
sudo ls -ld /data /data/app
~~~

Never use **chmod 777** as a default shortcut. Configure the proper user/group for the application process, plus ACLs and VM security policies.

## 15. Preparing a Data Disk on Windows

On a Windows VM, use **Disk Management** or PowerShell to locate the new disk.

### 15.1. Checking existing disks

Open PowerShell with appropriate privileges:

~~~powershell
Get-Disk | Format-Table Number, FriendlyName, OperationalStatus, PartitionStyle, Size
Get-Volume | Format-Table DriveLetter, FileSystemLabel, FileSystem, Size
~~~

Compare disk number, size, and operational status against the newly attached data disk. A new disk may appear as **RAW** or **Offline** depending on the environment. Never assume **Disk 1** or **D:** is automatically your new data disk.

### 15.2. Initializing a new disk

Only after confirming the exact **disk number** belongs to the new empty data disk—not the OS or temporary disk—run:

~~~powershell
# Replace N with the verified new disk number; do not run if disk holds data.
Initialize-Disk -Number N -PartitionStyle GPT

$partition = New-Partition -DiskNumber N -UseMaximumSize -AssignDriveLetter
$partition | Format-Volume -FileSystem NTFS -NewFileSystemLabel AppData
~~~

These commands alter disk metadata. Never run them in production without approval, backups, and exact verification of the target disk. If the disk already holds NTFS/ReFS or application data, bring it online and assign a drive letter **without initializing or reformatting**.

Once the new volume is ready, applications can use paths like **E:\AppData** or a chosen mount point. Do not assume `E:` is always free; Windows may assign another drive letter.

### 15.3. Avoiding misuse of the D: drive

On many Azure Windows VMs, `D:` is the **temporary disk**, often holding the pagefile or temp folders. If an administrator formats `D:` or places a database there mistaking it for a managed data disk, data loss risk is severe.

Verify the backing disk via Portal, Disk Management, and Azure VM metadata before choosing a drive for critical data.

## 16. Temporary Disks on Linux and Windows: Proper Usage

### 16.1. Linux

Some Linux VM images automatically mount the resource disk at **/mnt** or **/mnt/resource**. Before using it, inspect:

~~~bash
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
findmnt /mnt
findmnt /mnt/resource
df -h
~~~

If no temporary disk exists on the VM size, those paths may not exist or may simply be directories on the OS disk. Never write caches to a path assuming it automatically lands on local temporary storage.

Example application cache paths on verified local temporary storage:

~~~text
/tmp/job-cache
/mnt/resource/app-cache
~~~

These are examples only; actual paths depend on image and configuration. Applications must recreate cache directories, verify permissions, and handle cases where local temp space is absent.

### 16.2. Windows

On some Azure Windows VMs, temporary storage appears as **D:**. However, that is **not a universal rule across all VMs**; drive letters and volumes may be configured differently.

Verify via Disk Management/PowerShell, VM size documentation, and device details. Never delete the pagefile or repartition the temporary drive without understanding OS impact.

### 16.3. Designing applications to tolerate cache loss

A safe pattern:

1. Store authoritative source data on managed disks or durable services like Blob Storage.
2. Write cached copies/thumbnails to temporary storage.
3. On cache read, check if the file exists.
4. On cache miss, regenerate from the durable source.
5. Enforce TTLs and size caps so caches do not fill the local volume.
6. Never acknowledge success for a critical upload while it resides solely on the temporary disk.

Local storage can be fast, yet its intended role is **regenerable data**, never long-term retention.

## 17. Expanding Capacity and Adjusting Data Disks

When a managed disk runs short on capacity, you may need to expand the disk or add another disk.

General workflow:

1. Check **provisioned capacity** in Azure and **filesystem usage** inside the guest.
2. Measure data growth rate and decide on the target size.
3. Verify SKU/VM size limits and online resize eligibility.
4. Back up/verify recoverability prior to risky operations.
5. Update the managed disk size using supported procedures.
6. Extend the partition/filesystem inside Linux or Windows as needed.
7. Verify application data access and I/O metrics afterward.

Azure CLI example resizing a managed data disk under supported conditions:

~~~bash
az disk update \
  --resource-group rg-vm-storage-lab \
  --name disk-appdata-01 \
  --size-gb 128
~~~

**This command does not automatically grow the guest filesystem.** The OS typically requires extending partitions and filesystems with OS tools. Never assume you can shrink a managed disk directly like expanding one; shrinking generally requires data migration/restoration workarounds and faces strict limits.

If changing disk type, IOPS, throughput, or caching, check update rules, VM stop/deallocate requirements, and app impact for that specific SKU.

## 18. Detaching Data Disks, Replacing VMs, and Deletion Policies

One advantage of managed data disks is managing their lifecycle independently of the VM when configuration and procedures allow.

**Safe detach procedure:**

1. Notify users or stop workloads writing to the disk.
2. Flush buffers, stop services, and unmount filesystems on Linux or take volumes offline cleanly on Windows.
3. Confirm no processes still hold the disk open.
4. Run detach in Azure.
5. Confirm disk state and verify data remains intact.
6. If needed, attach to another compatible VM and mount **without reformatting**.

Azure CLI detach example:

~~~bash
az vm disk detach \
  --resource-group rg-vm-storage-lab \
  --vm-name vm-app-01 \
  --name disk-appdata-01
~~~

**Never use detach as a substitute for a clean OS unmount.** Detaching a block device during active database writes risks corruption. Some configurations require stopping the VM or additional steps.

When deleting a VM, verify the **delete option** on OS and data disks. If set to **Delete**, disks are deleted along with the VM per policy. If set to **Detach**, disks remain and continue accruing charges. Before deleting resources, document which disks must be kept, which can be deleted, and verify backups first.

## 19. Backups, Snapshots, and Data Recovery

**Durability does not equal recoverable backups.** Managed Disks provide durable block storage per service design, yet cannot automatically protect against logical errors, accidental deletion, ransomware, or application corruption.

### 19.1. Snapshots

A **snapshot** captures a point-in-time state of a disk via supported snapshot mechanics. It helps create checkpoints before changes or spawn recovery disks.

Azure CLI example creating a snapshot from a managed disk:

~~~bash
az snapshot create \
  --resource-group rg-vm-storage-lab \
  --name snap-appdata-before-update \
  --source disk-appdata-01
~~~

A snapshot is an Azure resource with its own cost and lifecycle. A snapshot taken while an application is actively writing may only provide **crash-consistent** state depending on circumstances, not automatically transaction-consistent state for databases.

### 19.2. Azure Backup

For critical VMs/disks, evaluate **Azure Backup** and appropriate backup policies. Key elements to define:

- Recovery targets: **RPO** and **RTO**.
- Backup scope: entire VM, OS disk, specific data disks.
- Backup frequency, retention duration, and storage location.
- Application data consistency level.
- Encryption and access controls over backups.
- Periodic restore testing capabilities.

Database engines may require specialized application-aware backups or quiescing/transaction log coordination for consistency. Never assume block-device snapshots replace logical or transaction-aware backups.

### 19.3. Host-loss scenario

Suppose a VM must redeploy to another host:

- Azure managed data disks typically persist and reattach per configuration.
- The temporary disk may start empty or be recreated.
- Applications must rebuild caches and temp data from durable sources.
- If using an ephemeral OS disk, the OS may be reimaged from the base image.
- Backups and DR procedures remain vital for logical errors or broader outages.

## 20. Securing OS Disks and Data Disks

### 20.1. Encryption at rest

Azure Managed Disks are **encrypted at rest** via Azure server-side encryption using platform-managed keys by default. Depending on compliance needs and feature support, organizations can evaluate customer-managed keys (CMK) via configurations such as a Disk Encryption Set.

Encryption at rest does not replace:

- TLS for data in transit across networks.
- Protecting application and administrator credentials.
- Guest OS permissions and RBAC.
- Backup management and recovery readiness.
- Protecting data in memory, caches, or local temporary storage.

Some environments also evaluate **encryption at host** per VM supportability and security policy; never assume all VMs share identical encryption defaults.

### 20.2. Azure RBAC vs. OS-level permissions

Managing Azure disks via Portal/API is a **control-plane permission**. Reading files inside guest volumes is governed by OS accounts, filesystem permissions, and application access controls.

Best practices:

- Assign least-privilege Azure RBAC roles to create, attach, and delete disks.
- Use Microsoft Entra ID, MFA, and Privileged Identity Management (PIM) for sensitive admin privileges.
- Enforce proper user/group permissions and ACLs inside Linux/Windows.
- Keep secrets in approved secret management services; never store them solely on temporary disks.
- Track VM/disk changes via Azure Activity Log and guest OS auditing.

### 20.3. Safe disk deletion

For sensitive data, deletion must follow organizational lifecycle and data-sanitization policies. Avoid running destructive actions like formatting or deleting purely by drive letter. Verify exact disk resource ID, scope, and owner before approving.

## 21. Availability, Deployment Zones, and Disk Limits

A managed disk is an Azure resource tied to a specific SKU, region, and availability constraints. When designing HA/DR:

- Choose disk SKUs with suitable redundancy where supported, such as LRS/ZRS per SKU and region.
- Verify disk and VM compatibility with the selected availability zone.
- Do not assume a disk in one zone attaches directly to a VM in an arbitrary zone.
- Use application- or service-tier replication/DR for multi-zone or multi-region targets if required.
- Test rebuilding VMs and restoring data disks/apps from backups or images.
- With ephemeral OS and temporary disks, plan state recreation rather than trying to preserve local data.

**Availability Zone redundancy** on a disk and **multi-region backups** address different risks. Single-region availability enhancements do not replace recovery plans for full-region outages or accidental data deletion.

## 22. Monitoring Disk Performance and Capacity

Reliable operations combine Azure telemetry with guest OS monitoring.

| Metric group | What to track | Goal |
|---|---|---|
| Disk read/write operations | I/O operations over time | Identify IOPS demand |
| Disk read/write bytes | Read/write volume over time | Evaluate throughput |
| Latency/queue depth | I/O latency and queue length where measurable | Spot disk or VM bottlenecks |
| Disk IOPS/throughput limits | Utilization relative to disk/VM SKU caps | Pinpoint which resource is throttling |
| Filesystem usage | Percentage used and inode usage where applicable | Prevent disk-full app outages |
| Application errors | Timeouts, `fsync`/I/O errors, file write failures | Correlate I/O issues with business errors |
| Backup status | Last backup timestamp, failures, restore health | Ensure recoverability |

Azure Monitor supplies supported VM and disk metrics. Guest **filesystem capacity** typically requires Azure Monitor Agent, guest metrics, or OS tools; not every metric comes solely from the managed disk resource.

On Linux:

~~~bash
df -h
lsblk -f
iostat -xz 1
~~~

`iostat` requires installing its package, typically `sysstat`. On Windows, use Performance Monitor, Resource Monitor, or equivalent I/O monitoring utilities.

When applications slow down, examine CPU, RAM, VM I/O caps, disk IOPS, host caching, and backend latency together before concluding you must buy a pricier disk SKU.

## 23. Controlling Disk Storage Costs

Cost drivers include:

1. **Managed disk SKU**: Standard HDD, Standard SSD, Premium SSD, Premium SSD v2, or others.
2. **Provisioned capacity**: never assume billing always matches bytes written inside the filesystem.
3. **Provisioned performance**: certain SKUs bill separately for reserved IOPS/throughput.
4. **Snapshots and backups**: copy storage, retention, and data transfer may incur separate charges.
5. **Redundancy**: LRS/ZRS choices and regional/SKU pricing.
6. **Orphaned disks**: detached yet undeleted disks keep incurring charges.
7. **VM size**: local temporary disks come bundled with compute tiers; VMs with large local storage carry corresponding compute pricing.
8. **Monitoring and logs**: metric/diagnostic ingestion into storage or analytics services carries fees.

When a VM is deallocated, compute charges may stop per billing rules, yet standalone managed disks persist and continue billing. When budgeting, check the Azure Pricing Calculator and Cost Management for your actual SKU/region.

A cost-saving approach is workload separation:

- Right-sized OS disk for the operating system.
- Data disk matched to real IOPS, avoiding over-spec'd SKUs.
- Regenerable caches placed on temporary/local storage if supported and suitable.
- Large shared files or non-block data moved to Blob/Files when appropriate.
- Test disks/snapshots deleted once dependencies are cleared and deletion is authorized.

**Never delete a disk solely because its state says Unattached.** Verify whether it is a recovery disk, manual backup, or intentionally retained resource.

## 24. Common Operational Mistakes

### 24.1. Seeing drive D: and assuming it is a managed data disk

On some Windows VMs, `D:` is the temporary disk. Verify disk metadata in Azure and the OS. Critical data must never live solely where host changes wipe it.

### 24.2. Attaching a disk succeeds yet no drive appears in Explorer

The disk may still need initialization, partitioning, formatting, or a drive letter. Inspect Disk Management/`Get-Disk` before acting. If the disk holds existing data, **never initialize or reformat**.

### 24.3. Linux mounts /data, then loses the path after reboot

Inspect **/etc/fstab**, UUIDs, filesystem type, disk discovery timing, and mount status. Avoid relying on mutable names like **/dev/sdc**.

### 24.4. VM runs out of OS disk space despite free space on data disk

Apps or logs may still be writing to **/** or **C:**. Check actual write paths, mount points, and write permissions. Relocate data or configure log rotation.

### 24.5. Increasing disk size in Azure yet the OS shows no extra space

The Azure disk resource expanded, yet guest partitions/filesystems have not been extended. Check resize conditions, guest rescanning, and filesystem tools. Never modify partitions without backups and a rollback plan.

### 24.6. Database vanishes after VM deallocate/redeploy

The data likely resided on a temporary disk, ephemeral OS disk, or wrong mount path. Verify actual storage paths, inspect backups, and trace logs/timelines; never format or overwrite disks before assessing recovery options.

### 24.7. Deleting a VM also deletes the data disk

Check each disk's **delete option**. "Managed" does not mean "automatically kept when deleting a VM." Configure delete policies per operational needs and verify backups first.

### 24.8. Disk boasts high IOPS yet application stays slow

The VM size may be hitting its throughput cap, the filesystem/I/O queue may be unoptimized, the app may block synchronously, or caching may be misconfigured. Measure across VM, disk, guest, and app to locate the real limit.

### 24.9. Snapshots exist yet restores yield inconsistent databases

Block-level snapshots are not automatically application-consistent. Use database-aware backup tools, verify transaction logs, and drill restores.

### 24.10. Detached disks continue accruing bills

Detaching removes the VM link; it does not delete the disk. Audit whether the disk must be retained or deleted per resource governance.

## 25. Controlled Lab Exercise: Three Disk Types

**Context:** you have a test Azure Linux VM and appropriate disk management permissions. The goal is to inspect the OS disk, create a new data disk, locate the temporary disk if provided by the VM size, and verify data resides in the right places.

**Safety conditions:**

- Operate strictly inside a budget-capped lab resource group.
- Never format or delete production VMs or disks.
- Confirm disk identity in both Portal/CLI and the guest OS before any potentially destructive command.
- If your VM size lacks a temporary disk, mark that step **not applicable** rather than inventing assumptions.

### Part A — Inventory

1. Open the VM in the Azure Portal and identify the OS disk, existing data disks, SKUs, and delete options.
2. Run the **az vm show** query from Section 12 or inspect equivalent details in the Portal.
3. On Linux, run **lsblk** to identify the filesystem hosting **/**.
4. Record OS disk capacity, filesystem details, and current usage before starting.

### Part B — Attach a new data disk

1. Create a small budget-friendly managed disk using Section 13 commands.
2. Attach it to the VM on an unused LUN.
3. Inside the guest, run **lsblk** and **blkid**; correlate with the newly attached disk.
4. Only after confirming it is the new empty disk: create a filesystem, mount at **/data**, and verify.
5. Create a test file under **/data**, e.g., **/data/lab-check.txt**.
6. Retrieve the UUID and configure persistent mounting across reboots per Section 14.

### Part C — Temporary disk

1. Verify whether your VM size includes local temporary storage.
2. Inspect the mount/volume with OS tools.
3. If present, write a **non-critical** cache file to the temp area.
4. Document why that file must **not** be treated as persistent data.
5. **Do not intentionally redeploy/deallocate** just to wipe the file; simulate cache loss safely by deleting only that test cache file and regenerating it.

### Part D — Verify and clean up

1. Reboot the lab VM per plan and confirm **/data** remounts with your test file intact.
2. Confirm app logs/data did not accidentally write onto the OS disk while `/data` was unmounted.
3. Confirm temporary paths are designed to tolerate data loss.
4. If testing backups, use lab-appropriate snapshots/backups and note consistency characteristics.
5. Stop disk-using services, unmount, and **safely** detach the data disk before deleting authorized test resources.
6. Delete unneeded lab snapshots/disks once dependency checks pass, and verify costs in Cost Management.

**Expected outcome:** you can distinguish the OS managed disk, managed data disk, and local temporary disk (if present), explain data persistence across lifecycle events, and mount data drives without risking data loss.

## 26. Production Readiness Checklist for VMs with Data Disks

- [ ] Confirmed whether OS disk is managed or ephemeral and understood lifecycle implications.
- [ ] Critical data does not reside solely on temporary disks.
- [ ] Data disk SKU, capacity, IOPS, and throughput satisfy workload needs.
- [ ] VM size supports required disk count, bus/controller, and aggregate I/O.
- [ ] Data disks attached with appropriate LUNs and identified via stable metadata.
- [ ] Guest filesystems, partitions, mounts, and file permissions verified.
- [ ] Existing data disks were never reformatted.
- [ ] Linux mounts use UUIDs or equivalent stable identifiers; Windows volumes verified.
- [ ] Filesystem usage, I/O, app errors, and backup health monitored.
- [ ] Backups match RPO/RTO and restores have been practiced.
- [ ] Encryption at rest, Azure RBAC, OS rights, and secret storage reviewed.
- [ ] VM delete options and disk lifecycles explicitly defined.
- [ ] Zone/DR plans aligned without confusing redundancy for backups.
- [ ] Budgeted for managed disks, snapshots, backups, and orphaned disks.

## 27. Self-Check Questions

1. How does an OS disk differ in role from a data disk? Why does OS disk type matter?
2. How do standard managed OS disks differ from ephemeral OS disks?
3. Which drive letter does a temporary disk often receive on Windows VMs? Why should you not rely on that letter when placing a database?
4. When stopping/deallocating a VM, what typically happens to managed data disk contents? Does a temporary disk share that guarantee?
5. Why might a newly attached data disk not appear immediately as a writable drive?
6. Why must you positively identify the target device before running `mkfs` or `Initialize-Disk`?
7. Does LUN 0 always equal `/dev/sdc` on every Linux VM?
8. After expanding a managed disk in Azure, does the guest filesystem automatically expand too?
9. When deleting a VM, is managed disk data always guaranteed to survive?
10. Does a managed disk snapshot automatically guarantee a database-consistent backup?
11. If thumbnail caches disappear after host maintenance, how should the application behave?
12. Which metrics and settings would you inspect if a disk advertises high IOPS yet your Java API stays slow?

## 28. Summary

In Azure Virtual Machines, the **OS disk** primarily boots and runs the operating system; **data disks** store application data requiring governance, protection, and backups; and **temporary disks** offer local scratch space whose **contents can be lost** when underlying infrastructure shifts. Standard OS disks and data disks are typically persistent Azure Managed Disks per storage policies, whereas **ephemeral OS disks** are a special option suited to recreatable workloads.

In operations, **positively identify disks before formatting**, attach and mount data disks using stable identifiers, never store critical data on temporary disks, select SKUs from real workload needs, and establish clear backup/restore and deletion policies. Combine Azure RBAC, guest OS monitoring, Azure Monitor, and Cost Management to operate VM storage safely, resiliently, and cost-effectively.
