# Attaching Disks, Resizing Capacity, and Managing Filesystems

A Java API running on Compute Engine begins hitting file write errors when its data directory fills up. The operations team increases the Persistent Disk from 100 GiB to 200 GiB in Google Cloud Console, yet `df -h` on the VM still reports the filesystem as roughly 100 GiB. The issue lies in **two separate capacity management layers**: Google Cloud manages the size of the **block device**; the operating system manages the **partitions, volumes, and filesystem** on top of that device.

The lesson **"Attaching Disks, Resizing Capacity, and Managing Filesystems"** belongs to the **Block and File Storage** chapter of the **CLOUD_PROVIDERS_GCP** module. This is practical knowledge for selecting storage types, operating safely on Compute Engine, enforcing permissions via IAM, protecting data, and connecting services such as GKE, Cloud Run, Cloud Storage, or databases. Beyond adding capacity, we must know which storage suits each workload, automate operations, monitor reliability, and avoid unnecessary charges.

After this lesson, you will be able to:

- Distinguish **block storage** (Persistent Disk, Hyperdisk) from **file storage** (Filestore) and object storage (Cloud Storage).
- Explain the chain **disk → partition (if any) → LVM (if any) → filesystem → mount point → application**.
- Create and attach a data disk to a Linux VM using Console/`gcloud`.
- Identify the exact device, format with ext4 or XFS, mount safely, and configure `/etc/fstab`.
- Expand disk, partition, filesystem, or logical volume capacity in the correct order.
- Back up with snapshots, detach disks safely, manage permissions, observe I/O, and estimate costs.
- Know when to use Filestore so multiple VMs can share files instead of attaching a regular filesystem to multiple machines.

> **Lab scope:** example commands use a Linux VM and a **blank data disk** containing no data. `mkfs`, modifying partition tables, and editing `/etc/fstab` can destroy data or prevent a VM from booting if applied to the wrong device. **Never run on a boot disk or a disk holding real data** without verifying and backing up first. Execute only in an authorized lab project and replace all placeholders with real values.

## 1. Three Common Storage Classes on Google Cloud

Not every storage resource works like a "hard drive."

| Type | Typical service | How applications access it | Suitable use cases |
|---|---|---|---|
| **Block storage** | Compute Engine Persistent Disk, Hyperdisk | OS sees a block device; create filesystem and mount | Boot disks, data directories, workloads requiring block I/O |
| **Managed file storage** | Filestore | NFS file share over VPC; clients mount network paths | Multiple VMs/GKE Pods needing a shared POSIX directory tree |
| **Object storage** | Cloud Storage | API/SDK, HTTP, or compatible tools | Images, user files, backups, artifacts, object data |
| **Local SSD** | Host-attached local storage device | Block device on host | Scratch, high-speed caches, regenerable data |

**Block storage** is a collection of data blocks, with no built-in concept of directories or Unix permissions. When attaching a disk to Linux, you need a filesystem such as ext4 or XFS (or an appropriate data management layer) before using it like a directory.

**File storage** already provides the filesystem service and network sharing mechanism. NFS clients simply connect and mount an authorized export; **do not run `mkfs.ext4` against an NFS share**.

**Object storage** is not a default POSIX drive. Cloud Storage suits data accessed by object name/API; it does not share the exact filesystem, locking, rename, and consistency semantics of a block disk or NFS. If a Java application stores user-uploaded images, Cloud Storage is usually worth considering over a VM-attached data disk.

### Boot Disks, Data Disks, and Durability

- **Boot disks** hold the OS and typically the root partition/filesystem; deleting or corrupting them can prevent the VM from booting.
- **Data disks** separate application data from the OS and can be snapshotted, detached, or moved to another VM when the design supports it.
- **Persistent Disk/Hyperdisk** provides durable storage independent of the VM process lifecycle; however, disks can still be deleted via auto-delete settings, administrative actions, or guest-OS data errors.
- **Local SSD** is geared toward temporary data and should not serve as the sole copy of important data. Data retention across VM operations depends on supported machine series and lifecycles.

## 2. Capacity Architecture from Google Cloud to the Application

On Linux, `lsblk` shows **block devices** and dependent layers; `df` shows mounted filesystems. These two commands can report different sizes after expanding a disk.

~~~text
Google Cloud Persistent Disk: app-data (200 GiB)
                  │
                  ▼
Guest OS block device: /dev/disk/by-id/google-app-data
                  │
        ┌─────────┴──────────┐
        │ No partition table │ Or GPT partition table
        │ (filesystem right  │  └── /dev/sdb1 or nvme0n2p1
        │  on the raw disk)  │             │
        └─────────┬──────────┘             ├── (optional) LVM
                  │                        │
                  └──────────┬─────────────┘
                             ▼
                      ext4 / XFS filesystem
                             │
                             ▼
                      /mnt/disks/app-data
                             │
                             ▼
                       Java / application
~~~

The **no-partition** path is used in the lab for simplicity. Real production systems may use GPT, LVM, RAID, or LUKS encryption, making expansion workflows more involved.

### Inspection Commands

~~~bash
# On the Linux VM.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -hT
df -i
sudo blkid
findmnt /
~~~

| Command | Question it answers |
|---|---|
| `lsblk` | Which disks/partitions does the kernel see, their sizes, and hierarchy? |
| `blkid` | Which devices have UUIDs and filesystem types? |
| `df -hT` | Where are filesystems mounted and how much space remains? |
| `df -i` | Are **inodes** exhausted despite free bytes remaining? |
| `findmnt` | Which source backs a mount point, with what filesystem/options? |
| `du -xsh /path` | How much space is data inside that specific filesystem consuming? |

If `lsblk` reports the disk is already 200 GiB yet `df -hT` still shows 100 GiB, you likely need to expand the **partition** and/or **filesystem**. If `lsblk` itself still shows the old size, verify the disk was actually resized in Google Cloud and whether the guest OS has detected the change.

## 3. Choosing a Block Disk Type by Workload

Compute Engine provides several block storage options. Do not decide based solely on GiB size.

| Option | Characteristics | Usage guidance |
|---|---|---|
| **Persistent Disk Standard** (`pd-standard`) | HDD-backed, cost-optimized for workloads needing sequential throughput over random IOPS | Infrequently accessed data, IOPS-insensitive workloads |
| **Persistent Disk Balanced** (`pd-balanced`) | SSD-backed, balanced cost and performance | General-purpose VM boot/data disks |
| **Persistent Disk SSD** (`pd-ssd`) | SSD-backed, higher performance target than balanced for suitable workloads | Applications with heavier I/O demands |
| **Hyperdisk** (Balanced/Extreme/Throughput/... per support) | Capacity and some IOPS/throughput levels configured separately; subject to machine-type limits | Databases/analytics or workloads needing explicit performance control |
| **Local SSD** | High-speed host-local I/O; data lifecycle tied to VM lifecycle | Caches, scratch, regenerable data |

Actual performance depends on **disk type, size, vCPU count, machine family, disk count, and I/O pattern**. For Persistent Disk, size affects throughput/IOPS limits; for many Hyperdisk types, IOPS or throughput are **provisioned** separately and can be adjusted within service bounds. Adding GiBs does not guarantee immediate drops in application latency.

Some machines support only specific Hyperdisk types. Before creating disks, check **machine type compatibility**, region/zone, disk count limits, quotas, and availability.

### Zonal, Regional, and Multi-Writer

- **Zonal Persistent Disk** is created in one zone and attaches to a compatible VM in that zone.
- **Regional Persistent Disk** maintains synchronous data replicas across two zones in the same region per product design. **It does not automatically make an application highly available**: you still need standby VMs, write-ownership/failover workflows, and application recovery.
- Some disk types support **multi-VM access**, either read-only or multi-writer depending on product and mode. **Never mount standard ext4/XFS in concurrent read-write mode on multiple VMs** if the filesystem is not designed for concurrent writers; data corruption risk is severe. When sharing files, Filestore/NFS is usually a better choice.
- Storing a disk on Google Cloud does not mean data is backed up: disk replication, snapshots, and backups serve distinct purposes.

## 4. Safe Pre-Attach or Pre-Edit Workflow

Always verify four layers: **Cloud resource**, **OS device**, **filesystem**, and **application data**.

1. Confirm **project, zone, VM, and disk name**; note the owner and authorized operators.
2. Check whether the disk already holds data, partitions, or a filesystem. An **existing disk is not necessarily empty**.
3. If it contains data, create a snapshot/backup and check retention policies; use application-consistent backups for databases or continuously writing workloads.
4. Verify service capacity and quota for the change; estimate cost impact.
5. Schedule a maintenance window if unmounting, repartitioning, moving data, or editing `fstab` is required.
6. Prepare a clear rollback plan (snapshot, backup, old disk, image) and designate who handles mount failures.

Example from Cloud Shell or a workstation configured with `gcloud`:

~~~bash
PROJECT_ID="my-storage-lab"
ZONE="us-central1-a"
VM="app-vm"
DISK="app-data"

gcloud config set project "$PROJECT_ID"
gcloud compute instances describe "$VM" \
  --zone="$ZONE" \
  --format="yaml(name,zone,disks)"

# Can only describe once the disk exists.
gcloud compute disks describe "$DISK" \
  --zone="$ZONE"
~~~

In the `instances describe` output, inspect `boot`, `autoDelete`, and `source` for each disk. Avoid confusing a new disk with the boot disk and never assume `/dev/sdb` stays constant across reboots or different VM shapes.

## 5. Hands-on: Creating and Attaching a Persistent Disk to a Linux VM

Assume VM `app-vm` already exists in `us-central1-a`, runs Debian/Ubuntu, and is authorized to receive a data disk. Create a 100 GiB Balanced disk.

### Step 1 — Create the Disk via Console or `gcloud`

In Google Cloud Console, go to **Compute Engine → Storage → Disks → Create disk**, choose the name, same zone as the VM, type `Balanced persistent disk`, and size 100 GiB. Do not select an image/snapshot if you want an empty disk for formatting practice. After creation, verify the name and size.

Equivalent via CLI:

~~~bash
gcloud compute disks create "$DISK" \
  --zone="$ZONE" \
  --size=100GB \
  --type=pd-balanced

gcloud compute disks describe "$DISK" \
  --zone="$ZONE" \
  --format="yaml(name,sizeGb,type,status,users)"
~~~

**A new disk does not automatically appear as a folder inside the VM.** It is a block storage resource created in the Google Cloud project, billed based on provisioned capacity.

### Step 2 — Attach to the VM

In Console, open **Compute Engine → VM instances → app-vm → Edit → Additional disks → Attach existing disk**, select `app-data`, read/write mode, and save. Subject to constraints, attaching a data disk can be done on a running VM.

Equivalent via CLI:

~~~bash
DEVICE_NAME="app-data"

gcloud compute instances attach-disk "$VM" \
  --zone="$ZONE" \
  --disk="$DISK" \
  --device-name="$DEVICE_NAME" \
  --mode=rw

gcloud compute instances describe "$VM" \
  --zone="$ZONE" \
  --format="yaml(disks)"
~~~

For a zonal Persistent Disk, the VM and disk must be in the **same zone**. For regional disks or Hyperdisks, placement and attachment modes depend on each type's features. If another VM currently uses the disk read/write, never attach it read/write to a second VM simultaneously.

### Step 3 — Identify the Exact Disk in Linux

SSH into the VM and run:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
ls -l /dev/disk/by-id/google-*
sudo blkid

# Stable path when attached with --device-name=app-data.
DEV="/dev/disk/by-id/google-app-data"
readlink -f "$DEV"
sudo lsblk -f
~~~

Linux may name the device `/dev/sdb`, `/dev/nvme0n2`, or something else depending on the SCSI/NVMe interface and machine series. The symlink `/dev/disk/by-id/google-app-data` identifies the disk by the **device name specified at attach time**, avoiding guessing kernel names.

**Conditions before formatting:** verify `DEV` points to the **empty data disk**, roughly 100 GiB in size, not the boot disk, with no existing filesystem/partition/critical data. If `lsblk` or `blkid` shows existing data, stop and verify instead of running `mkfs`.

## 6. Formatting ext4, Mounting, and Configuring `fstab`

To focus on core mechanics, the lab puts an **ext4 filesystem directly on the whole disk without a partition table**. This is supported by Linux and Google Cloud for data disks; real projects may use GPT + partitions or LVM.

### Step 1 — Initial Format and Mount

~~~bash
DEV="/dev/disk/by-id/google-app-data"
MOUNT_DIR="/mnt/disks/app-data"

# WARNING: mkfs ERASES existing data structures.
# Run only after confirming this is a NEW and EMPTY data disk.
sudo mkfs.ext4 "$DEV"

sudo mkdir -p "$MOUNT_DIR"
sudo mount -o defaults "$DEV" "$MOUNT_DIR"

# Example ownership only for the lab VM user.
sudo chown "$USER:$USER" "$MOUNT_DIR"

df -hT "$MOUNT_DIR"
findmnt "$MOUNT_DIR"
sudo blkid "$DEV"
~~~

Once mounted, the new filesystem is accessible at `/mnt/disks/app-data`. Applications writing there need appropriate Unix permissions, or ACL/user/group settings per policy. Never use `chmod 777` as a default fix, as it opens read/write access to every user on the VM.

### Step 2 — Re-Mounting Across Reboots

The `mount` command above persists only for the current boot session. To auto-mount on boot, add a proper entry to `/etc/fstab`.

~~~bash
# Retrieve the UUID of the newly created filesystem.
sudo blkid -s UUID -o value "$DEV"

# Back up fstab before editing.
sudo cp /etc/fstab /etc/fstab.bak

# Use an editor to add ONLY ONE line with the exact UUID to /etc/fstab.
sudo nano /etc/fstab
~~~

Example single-line entry, where **UUID must be replaced with the value just retrieved**:

~~~fstab
UUID=XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX /mnt/disks/app-data ext4 defaults,nofail 0 2
~~~

- **UUID** does not depend on whether the kernel calls the disk `sdb` or `nvme0n2`.
- `nofail` lets the system finish booting if the disk is absent; when an application **strictly requires** the disk, still configure unit dependencies/health checks so it does not accidentally write into an empty directory on the boot disk.
- `0 2` are the standard `dump/fsck` fields for ext4 data filesystems.
- Never add overlapping entries for the same mount point.

Test before rebooting:

~~~bash
sudo mount -a
findmnt /mnt/disks/app-data
df -hT /mnt/disks/app-data
~~~

On systemd-based systems, run `sudo systemctl daemon-reload` after editing `fstab` if tools report a reload is needed. If `mount -a` errors out, fix `fstab` immediately while the VM is still running; **never reboot to test by trial and error**.

### Stable Device Names vs. UUIDs: Which to Choose?

| Use | Advantage | Caveat |
|---|---|---|
| `/dev/sdb` or `/dev/nvme0n2` | Easy to spot in one session | Can change across reboots or machine configurations |
| `/dev/disk/by-id/google-app-data` | Tied to `--device-name` at attach | Requires consistent `--device-name` and tracking when reattaching |
| `UUID=...` in `fstab` | Tied to the filesystem; survives device renames | Snapshot/cloned filesystems can share identical UUIDs; handle carefully if mounting together |
| `LABEL=...` in `fstab` | Human-readable and easy to manage | Labels must be unique on the system to avoid mounting the wrong volume |

When creating a disk from a snapshot and attaching it to the **same VM as the source disk**, inspect UUIDs and labels because the copied filesystem can have duplicate identifiers. Never attach to production without confirming which filesystem should mount.

## 7. Resizing Persistent Disk: Two Mandatory Steps

Suppose `app-data` needs to grow from 100 GiB to **200 GiB**. This is an expansion workflow, **not shrinking**. Persistent Disks can grow while attached to a running VM; before modifying partitions/filesystems, have a verified snapshot or backup. For database workloads, ensure application-level consistency.

~~~mermaid
flowchart TD
    A["Snapshot / backup and inspect drive"] --> B["Google Cloud: resize disk 100 → 200 GiB"]
    B --> C{"Does Linux see the larger disk?"}
    C -- "Not yet" --> D["Check operation/guest OS and device"]
    D --> C
    C -- "Yes" --> E{"Partitions/LVM present?"}
    E -- "No" --> F["Grow filesystem on raw device"]
    E -- "Partition" --> G["Grow partition → grow filesystem"]
    E -- "LVM" --> H["Grow partition/PV → LV → filesystem"]
    F --> I["df -hT + app read/write test"]
    G --> I
    H --> I
~~~

### Step 1 — Take a Snapshot Before Changes

From the control workstation using `gcloud`:

~~~bash
SNAPSHOT="app-data-before-grow-20261119"

gcloud compute snapshots create "$SNAPSHOT" \
  --source-disk="$DISK" \
  --source-disk-zone="$ZONE"
~~~

**Snapshots are not automatically application-consistent.** For databases or continuously writing workloads, use appropriate quiescing/backup mechanisms and test restores; taking a snapshot while an app is writing yields at best a crash-consistent copy without guaranteeing application-level transaction integrity. Snapshots holding sensitive data must enforce IAM, encryption, and retention controls.

### Step 2 — Resize the Disk in Compute Engine

~~~bash
# INCREASE capacity from 100 to 200 GiB.
gcloud compute disks resize "$DISK" \
  --size=200GB \
  --zone="$ZONE"

gcloud compute disks describe "$DISK" \
  --zone="$ZONE" \
  --format="yaml(name,sizeGb,status)"
~~~

In Console: **Compute Engine → Storage → Disks → app-data → Edit → Size = 200 GiB → Save**. Verify the operation succeeds before touching the filesystem.

**Note:** you cannot directly shrink a Persistent Disk. To downsize, create a smaller disk, copy data after verifying actual usage, confirm the application works, and only then retire the old disk. In Terraform, reducing `size` can trigger **destroy/recreate** on the disk, wiping data; always inspect `terraform plan` and use `prevent_destroy` where appropriate.

### Step 3 — Grow ext4 on Raw Disk (Unpartitioned Lab)

Inside the VM:

~~~bash
DEV="/dev/disk/by-id/google-app-data"
MOUNT_DIR="/mnt/disks/app-data"

lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -hT "$MOUNT_DIR"

# Valid ONLY if ext4 sits DIRECTLY on the raw disk, with no partition/LVM.
sudo resize2fs "$DEV"

df -hT "$MOUNT_DIR"
findmnt "$MOUNT_DIR"
~~~

With ext4, `resize2fs` can **grow online** on a mounted filesystem when supported conditions are met. Existing data is preserved by a proper grow operation; however, targeting the wrong device, partition, or encountering I/O errors still carries risk. Compare before/after capacity and run a sample read/write check.

**If the VM uses a public Google-provided Linux image and you resize the boot disk:** Compute Engine often auto-expands the boot disk's root filesystem; with custom images or specialized setups, you may need to grow the partition/filesystem manually. Do not apply the unpartitioned data-disk workflow above to a partitioned boot disk.

## 8. What If the Disk Uses Partitions or LVM?

Not every VM places a filesystem directly on a raw disk. A disk can contain one or more partitions, and partitions can act as **physical volumes (PV)** in **Logical Volume Manager (LVM)**. Always inspect the actual layout via `lsblk -f` and `pvs; vgs; lvs` before acting.

### Scenario A — ext4 on a Partition

~~~text
/dev/sdb             200 GiB  ← block disk already expanded
└── /dev/sdb1         100 GiB  ← partition still old size
    └── ext4          100 GiB  ← filesystem still old size
        └── /data
~~~

You must expand the **partition first**, then expand the **filesystem**. Illustrative example where the real device is `/dev/sdb` and partition 1 holds ext4:

~~~bash
# CHECK FIRST: /dev/sdb must be the exact data disk, with matching GPT/partition layout.
lsblk -f /dev/sdb
sudo parted /dev/sdb print

# growpart usually comes from the cloud-guest-utils package.
# Run only when partition 1 is the partition to expand.
sudo growpart /dev/sdb 1

# ext4 lives on the partition, not the raw disk.
sudo resize2fs /dev/sdb1

df -hT /data
~~~

These commands **do not blindly apply** to every configuration: on NVMe machines, the device may be `/dev/nvme0n2` and partition `/dev/nvme0n2p1`; on boot disks, layouts may include EFI, root, and other partitions. The OS may require rescanning the partition table or rebooting in certain cases where an active partition cannot update online. If partition/device numbering differs or critical data is present, never copy examples without a backup and change plan.

### Scenario B — XFS

For XFS, after growing the block disk and partition (if any), expand the filesystem using the **mount point**, not `resize2fs`:

~~~bash
# Assumes the XFS filesystem is mounted at /data and the block layer is already expanded.
findmnt /data
sudo xfs_growfs /data
df -hT /data
~~~

XFS supports **online growth** while mounted and does not support standard shrinking. Requires the `xfsprogs` tools. If `xfs_growfs` reports no size change, confirm the underlying disk/partition grew and the mount point is indeed XFS.

| Filesystem | Primary expansion command | Input |
|---|---|---|
| **ext4** | `resize2fs /dev/DEVICE` | Block device/partition holding ext4 |
| **XFS** | `xfs_growfs /mount-point` | Mount point of the mounted XFS filesystem |
| **btrfs** | `btrfs filesystem resize max /mount-point` | Mount point, after expanding the block layer |
| **NTFS on Windows** | Disk Management or PowerShell `Resize-Partition` | Windows volume; do not run Linux commands |

**Never use `mkfs` to "expand" a filesystem.** `mkfs` creates a brand-new filesystem and can wipe all existing data.

### Scenario C — Disk Using LVM

~~~text
Persistent Disk (200 GiB)
  └── Partition /dev/sdb1 (200 GiB)
       └── Physical Volume (PV)
            └── Volume Group: vg_app
                 └── Logical Volume: lv_data
                      └── ext4 /data
~~~

After growing the disk 100 → 200 GiB and the **partition** (if the PV sits on a partition), you must:

1. Grow the PV using `pvresize`.
2. Allocate free space in the volume group to the LV using `lvextend`.
3. Grow the filesystem inside the LV using the appropriate tool.

Illustrative example matching the exact layout above:

~~~bash
sudo pvs
sudo vgs
sudo lvs

# Only if /dev/sdb1 is the PV and the partition needs growing.
sudo growpart /dev/sdb 1
sudo pvresize /dev/sdb1

# -r tells lvm to attempt resizing the filesystem alongside the LV.
# The command below consumes all remaining free space in the VG: review first!
sudo lvextend -l +100%FREE -r /dev/vg_app/lv_data

sudo lvs
df -hT /data
~~~

**Never run `lvextend` against an LV name guessed from an example.** On real machines, the PV might sit directly on a raw disk, the VG might contain multiple LVs, or free space might be reserved for another volume. If `-r` does not support the current filesystem/conditions, run the filesystem expansion step separately per OS documentation. LVM adds flexibility, yet **does not eliminate backup requirements**.

## 9. Hyperdisk: Capacity and IOPS/Throughput Can Be Separate Settings

With **Hyperdisk**, beyond GiB size, several volume types let you configure **provisioned IOPS** and/or **provisioned throughput**. This is a major difference from simply growing capacity to tune traditional Persistent Disks.

| Hyperdisk Type | Tunable performance per feature | What to check |
|---|---|---|
| **Balanced** | Provisioned IOPS and throughput | Machine type support and capacity-based bounds |
| **Extreme** | Provisioned IOPS | IOPS limits, machine types, and cost |
| **Throughput** | Provisioned throughput | Sequential workloads, throughput limits |
| **Balanced High Availability** | Provisioned IOPS/throughput per support | Regional scope, replicas, and failover procedures |
| **ML** | Provisioned throughput per support | Access modes and workload profile |

Conceptual example with a compatible **Hyperdisk Balanced**:

~~~bash
# DO NOT use on Persistent Disk types.
# Verify machine type and valid IOPS/throughput values before executing.
HYPERDISK="db-hyperdisk"

gcloud compute disks update "$HYPERDISK" \
  --zone="$ZONE" \
  --size=500GB \
  --provisioned-iops=10000 \
  --provisioned-throughput=500
~~~

These values are **illustrative** and not guaranteed valid for every machine type/zone/capacity. For regional Hyperdisk Balanced HA, commands use `--region` and corresponding settings. Performance updates are subject to change-frequency cooldowns and propagation delays; review documentation for each disk type before acting.

**You still must expand the filesystem inside the guest OS** after increasing Hyperdisk capacity, just like with Persistent Disk. If the volume is in multi-writer mode, follow synchronized procedures across all VMs with a cluster-aware filesystem; do not use the single-writer raw ext4 example across multiple writers.

## 10. Properly Detaching, Reattaching, and Deleting Disks

When moving a data disk from one VM to another in the same zone (per disk eligibility), follow a controlled sequence:

1. Stop applications writing to the mount point and ensure jobs/batches have finished.
2. Confirm snapshots/backups if the data is important.
3. On the old VM, inspect processes holding open files, then `umount`.
4. **Remove or comment out the corresponding entry in `/etc/fstab`** on the old VM before rebooting.
5. Detach the disk from the old VM via the Compute Engine API/CLI.
6. Attach the disk to the new VM with the proper mode; **never run `mkfs`** on a disk that already has a filesystem.
7. Verify UUID, mount point, permissions, and data before starting the application on the new VM.

Example on the old VM:

~~~bash
MOUNT_DIR="/mnt/disks/app-data"

# Check processes still holding files open on the mount point.
sudo fuser -vm "$MOUNT_DIR"

# Unmount only after applications stop writing.
sync
sudo umount "$MOUNT_DIR"

# Edit /etc/fstab: comment out or remove the disk's UUID line before rebooting.
sudo nano /etc/fstab
~~~

On the control workstation:

~~~bash
# Zonal data disk, not a boot disk.
gcloud compute instances detach-disk "$VM" \
  --zone="$ZONE" \
  --disk="$DISK"

# Re-read attached users status before proceeding.
gcloud compute disks describe "$DISK" \
  --zone="$ZONE" \
  --format="yaml(name,status,users)"
~~~

When detaching and reattaching to another VM, use `gcloud compute instances attach-disk` with the new VM name and chosen device name. If the disk and VM are in different zones, attaching cannot automatically migrate data across zones; use snapshot/restore or a supported migration method.

### Detach vs. Delete

- **Unmount:** disconnects the filesystem from the OS directory tree; the disk remains attached to the VM.
- **Detach:** disconnects the block device from the VM; the disk resource still exists in Google Cloud.
- **Delete disk:** permanently deletes the storage resource and data—not a "temporary pause on billing."
- **Delete VM:** may automatically delete boot or data disks if `autoDelete` is enabled; inspect actual settings before deleting.
- **Delete filesystem files:** removes content inside the guest OS without shrinking the **provisioned disk** size being billed.

A disk that is **detached yet still exists** generally continues incurring storage charges. Never delete a disk solely to cut costs without confirming ownership, retention policies, and valid snapshots.

## 11. When Sharing a Filesystem Is Needed: Filestore and NFS

A Persistent Disk formatted with ext4/XFS works well when one VM owns the filesystem in standard single-writer mode. Yet if three VMs must concurrently read/write a POSIX directory tree, consider **Filestore**, Google Cloud's managed NFS file storage service.

~~~mermaid
flowchart LR
    A["App VM A"] --> D["Filestore NFS share"]
    B["App VM B"] --> D
    C["GKE Pods via CSI driver"] --> D
    D --> E["Managed filesystem shared over VPC"]
~~~

**Comparing block disks and NFS:**

| Question | Persistent Disk/Hyperdisk | Filestore |
|---|---|---|
| Guest OS actions | Receives block device; format/mount filesystem | Mounts NFS export; do not format block device |
| Multiple clients reading/writing files | Requires specialized modes/filesystems if multi-writer | Designed for multi-client NFS per configuration |
| File permissions | Linux permissions/ACLs per filesystem | POSIX permissions and NFS mechanics, plus network controls |
| Scaling | Grow block disk then grow partition/FS if needed | Resize Filestore instance capacity per tier/rules |
| Network path | Disk attached at VM infrastructure layer | Private IP in VPC, firewall rules, and NFS mount |
| Use cases | App data disks, block I/O | Shared files, home directories, apps needing a common filesystem |

### Example: Mounting a Share on a Linux VM

Suppose the Filestore instance has private IP `10.0.1.2` and share name `share1`, and the VM has VPC routes and firewall rules allowing NFS:

~~~bash
# Debian/Ubuntu; requires connectivity to apt repositories or an internal mirror.
sudo apt-get update
sudo apt-get install -y nfs-common

sudo mkdir -p /mnt/shared

# IP and share are illustrative; replace with your real Filestore details.
sudo mount -t nfs -o rw,tcp \
  10.0.1.2:/share1 /mnt/shared

findmnt /mnt/shared
df -hT /mnt/shared
~~~

To mount at VM boot, configure `/etc/fstab` after verifying network connectivity and NFS mounting work:

~~~fstab
10.0.1.2:/share1 /mnt/shared nfs defaults,_netdev,nofail 0 0
~~~

`_netdev` tells the OS this is a network filesystem. Options such as `nconnect`, NFS version, timeouts, and locking features depend on the Filestore tier, Linux kernel, and workload. For GKE, use the **Filestore CSI driver** or supported integration rather than SSHing into nodes to mount manually.

**Warning:** Filestore uses NFS, so you must design private networking, firewalls, POSIX permissions, file locking, and backups accordingly. An NFS share is not a "hidden hard drive" on which to run `fdisk` or `resize2fs`. Even when multiple VMs share files, applications must still handle concurrency and transactional state safely.

## 12. Data Protection: Snapshots, Backups, and Recovery

Resizing disks or modifying partitions can often be done online, yet **no operation replaces backups**.

| Measure | Purpose | Do not misunderstand |
|---|---|---|
| **Persistent Disk snapshot** | Point-in-time copy of a block disk, supporting new disk creation/recovery | Does not automatically guarantee application consistency for actively writing databases |
| **Snapshot schedule** | Creates scheduled snapshots and enforces retention | Must verify schedules, permissions, expiration, and restore capability |
| **Application/database backup** | Captures logical copies restorable to transactional states | Does not mean a single disk snapshot alone is sufficient |
| **Regional disk replication** | Protects against certain infrastructure/zone failures | Does not protect against accidental app deletion or ransomware |
| **Filestore backup/snapshot** | Protects shares per tier capabilities | Do not run PD snapshot commands against Filestore |
| **Offsite/cross-region/isolated permissions** | Reduces blast radius of single-scope destruction | Requires evaluating residency, data policies, and cost |

Creating a snapshot without testing restores leaves residual risk. Periodically practice:

1. Pick a verified valid snapshot.
2. Create a **new** disk from the snapshot in a test environment.
3. Attach **read-only** if appropriate or attach to an isolated VM.
4. Verify the filesystem, critical files, and application recovery logic.
5. Record actual recovery time (RTO) and acceptable data loss (RPO) against system requirements.

For critical data systems, use dedicated backup solutions capable of application-level quiescing/flushing and adhere to approved backup/retention schedules.

## 13. IAM, Encryption, and OS-Level Permissions

In Google Cloud, disk security has at least three layers:

1. **Control plane IAM:** who can create, attach, detach, resize, snapshot, or delete disks.
2. **Encryption/keys:** data at rest is encrypted by Google Cloud; customer-managed encryption keys (CMEK) can be used where regulations require.
3. **Guest OS permissions:** who can read/write mounted directories via Unix users/groups, ACLs, or application policies.

| Job role | Permissions to consider | How to scope |
|---|---|---|
| Storage/platform operator | `compute.disks.create`, `compute.disks.update`, `compute.disks.delete`, and snapshot permissions when needed | Compute Disk/Storage management role in authorized projects |
| VM operator | `compute.instances.attachDisk` / `detachDisk` and corresponding disk permissions | Scoped only to assigned VMs/disks |
| Security/KMS administrator | Key management and granting key usage under CMEK | Keep separate from general VM operations |
| Guest OS administrator | Partitioning, mounting, `fsck`, editing `fstab` | Audited `sudo`, restricted SSH |
| Application service account | Cloud Storage/Secret Manager API permissions if needed by workload | No disk delete/modify permissions unless required |

Broad administrative roles like `roles/compute.storageAdmin` or `roles/compute.instanceAdmin.v1` bundle many permissions beyond single actions. Prefer narrower predefined roles or custom roles matching actual permissions; review **IAM inherited from Folders/Organizations** before granting more. Permissions to edit filesystems inside the guest OS do not come directly from `roles/compute.storageAdmin`; they depend on VM login and `sudo` access.

### Encryption and Deletion

- Persistent Disk and Hyperdisk are encrypted at rest by default. **CMEK** adds key control along with operational risk if keys are disabled or revoked; plan key rotation and recovery.
- Sensitive data in snapshots/backups must be protected on par with originals.
- Before deleting a VM or running `terraform destroy`, review `autoDelete`, disk attachments, retained snapshots, and retention policies.
- When using Terraform, inspect `plan` before disk type/size changes; `lifecycle.prevent_destroy = true` helps shield critical data resources from accidental replacement.
- For Filestore, **NFS/POSIX permissions and firewalls** matter: network reachability alone does not imply safe write access for every file.

## 14. Monitoring Filesystems, I/O, and Capacity Alerts

Disk management does not end once mounting succeeds. Monitor the **Cloud disk**, **filesystem**, and **application** together.

### Inside the Linux Guest

~~~bash
# Disk/partition/filesystem overview.
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS
df -hT
df -i
findmnt /mnt/disks/app-data

# Directory usage within the same filesystem.
sudo du -xsh /mnt/disks/app-data/*

# Check kernel logs when I/O errors appear.
sudo dmesg --level=err,warn | tail -n 40

# If sysstat is installed, observe per-block-device IOPS/latency:
iostat -xz 1 5
~~~

Do not conclude a disk is failing just because `df` reports full. Other common causes include:

- **Inode exhaustion:** millions of small files exhaust ext4 inodes even when `df -h` shows free GBs.
- **Deleted files held open by processes:** space stays allocated until the process closes the descriptor; `lsof +L1` helps investigate when authorized.
- **Missing mount:** the application writes to a directory on the boot disk because the data disk is unmounted; check `findmnt` and `fstab`.
- **Permission denied:** Unix ownership/ACLs, read-only mounts, or application policies.
- **High I/O latency:** random workloads, disk type, vCPU caps, throughput/IOPS limits, queue depth, or database behavior.
- **Quota/capacity:** inability to create new disks or hitting per-VM disk count/attach limits.

### Cloud Monitoring and Alerts

Cloud Monitoring exposes disk bytes, I/O operations, and latency metrics by machine/disk type; Ops Agent/guest monitoring tracks filesystem utilization inside the VM. Set alerts for:

| Metric | Signal |
|---|---|
| Filesystem used % / free bytes | Risk of running out of space within days |
| Free inodes | System may fail to create new files |
| Read/write bytes and operations | Actual load, spotting traffic spikes |
| I/O latency / queue depth | Application experiencing I/O bottlenecks |
| Disk resize/snapshot operations | Unexpected or failed administrative actions |
| Backup age / snapshot schedule | Missing recent recovery points |
| Provisioned GiB and performance cost | Over-provisioned capacity or high Hyperdisk IOPS/throughput |

A static `filesystem used > 85%` alert is only an example: optimal thresholds depend on growth rate, criticality, and time needed to expand. For `/var/lib` or database data disks, alert on **projected time until full**, not merely a fixed threshold.

## 15. Costs and Storage Architecture Choices

Disks are normally billed by **provisioned capacity**, not just the GBs of data reported by `du`. Expanding from 100 to 200 GiB increases provisioned capacity and therefore cost even if the filesystem still holds only 60 GiB. Some Hyperdisk types also bill for **provisioned IOPS/throughput**; snapshots and network/storage services carry separate fees as well.

| Component | Billing drivers | How to optimize |
|---|---|---|
| Persistent Disk | Disk type, provisioned GiB, zone/region | Match tier and size to workload; delete unused disks after backing up |
| Hyperdisk | Provisioned GiB and corresponding performance metrics | Measure actual demand; avoid keeping unnecessary high IOPS/throughput |
| Snapshot | Stored snapshot size and retention | Sensible retention schedules; verify restores |
| Regional disk | Disk type/replication per region | Use only when availability requirements demand it |
| Filestore | Tier, capacity, performance, and lifetime | Use for multi-client POSIX genuinely needing NFS |
| Network/backups/logging | Data transfer, backups, logs/metrics | Track auxiliary SKUs |

**Analyze demand before resizing:** a full filesystem may stem from unrotated logs, uncleaned temp files, or misplaced backups. Continuously growing disks without fixing root causes locks in ongoing costs. Conversely, deleting files shrinks `du`/`df` usage without automatically reducing billed provisioned disk size.

If you need to shrink from 200 to 100 GiB, **you cannot shrink a Persistent Disk in place**. You must create a new disk sized for the data, copy/restore, test the application, switch mounts, and retire the old disk safely. With XFS especially, never promise in-place filesystem shrinking.

Cloud Billing budget alerts help track spending, yet **never automatically delete disks or stop resources**. Maintain an inventory process for unowned disks/snapshots, retention, and cleanup decisions.

## 16. Scenario: Java API Running Out of Data Disk Space

An enterprise runs a Java API on a Compute Engine VM:

~~~text
Client → External Application Load Balancer
              ↓
        Compute Engine VM
        ├── Boot disk 40 GiB (OS + JVM)
        └── Data disk 100 GiB (ext4 → /srv/app/data)
              ├── Temporary uploads
              ├── Generated reports
              └── Application cache
              ↓
         Cloud Storage / Cloud SQL
~~~

When monitoring alerts that the data filesystem hit 88% and is growing fast, the operations team:

1. Checks `df -hT`, `df -i`, and `du -xsh`, confirming the app is not writing into the boot disk by mistake.
2. Checks data growth and retention; moves durable uploaded files to Cloud Storage where appropriate instead of treating a single VM's data disk as multi-instance storage.
3. Confirms the disk is a zonal `pd-balanced` with an ext4 filesystem placed **directly on the raw block device**.
4. Takes a snapshot/backup and verifies restore capability.
5. Uses `gcloud compute disks resize` to expand 100 → 200 GiB.
6. Inside the VM, checks `lsblk` and runs `resize2fs` on the **exact device**; verifies `df -hT`.
7. Triggers a real report-generation request and reads the file back; monitors disk latency and error rates.
8. Updates retention policies, alerts, budgets, and change records.

If the API scales out via a multi-VM Managed Instance Group, **each VM gets its own disk**, not a single shared ext4 data disk. Durable uploads should move to Cloud Storage/Filestore or an appropriate shared data architecture; databases should have dedicated backups/HA. For containers on GKE, use PersistentVolume/PersistentVolumeClaim with supported CSI drivers; on Cloud Run, never assume you can attach a Compute Engine Persistent Disk directly to a container like a traditional VM.

### When to Grow a Disk vs. Switch Services

| Scenario | Suitable direction |
|---|---|
| Single VM needs more space for a local filesystem | Resize Persistent Disk and grow FS |
| Multiple VMs need concurrent read/write to a POSIX directory tree | Filestore/NFS per locking/performance needs |
| Uploaded images/docs need durability and multi-instance access | Cloud Storage and SDK/API |
| Database needs replication, HA, transactional backups | Managed database service or specialized data system |
| Regenerable, latency-sensitive cache | Local SSD or in-memory cache per data-loss tolerance |
| Block I/O needing independently tuned IOPS/throughput | Hyperdisk compatible with machine type and budget |

## 17. Pre-Create or Pre-Resize Production Disk Checklist

- [ ] Confirmed project, zone/region, VM, disk name, owner, and cost center.
- [ ] Checked disk type and machine-type/zone compatibility.
- [ ] Identified the exact **block device** via `/dev/disk/by-id`, without guessing `sdb`.
- [ ] Verified whether the disk is empty or holds data before any `mkfs` command.
- [ ] Identified raw filesystem, GPT partitions, LVM, or other layers using `lsblk`, `blkid`, and corresponding tools.
- [ ] Created a snapshot/backup with a verified restore/rollback plan.
- [ ] Confirmed target size and verified it **only increases**, avoiding accidental shrink requests.
- [ ] After resizing the Cloud disk, expanded the right partition/PV/LV/filesystem.
- [ ] Checked `df -hT`, `findmnt`, and ran an application read/write test.
- [ ] Verified `fstab` uses the right UUID/by-id and tested `mount -a` before rebooting.
- [ ] Reviewed data disk auto-delete, encryption, IAM, and backup storage.
- [ ] Confirmed ext4/XFS is never mounted for unsupported concurrent writes across VMs.
- [ ] Enabled monitoring for filesystem used %, inodes, I/O latency, and snapshot age.
- [ ] Planned graceful app shutdown/unmount/disk swap when needed; never detach actively written disks.
- [ ] Estimated costs for provisioned disk capacity, Hyperdisk performance, Filestore, and snapshots.

**Practice exercise:** A VM running a Java application has a 100 GiB data disk; the team wants to grow it to 250 GiB. Consider three variants:

1. **ext4 on raw disk:** list the ordered Cloud resize steps, Linux resize steps, and verification commands.
2. **ext4 on GPT partition 1:** distinguish `growpart` from `resize2fs`; explain why skipping the partition step fails to expose the new space.
3. **XFS on LVM:** diagram the chain disk → partition → PV → VG → LV → XFS; list the tools used at each layer and the prerequisite for `xfs_growfs`.

Then explain: (4) why snapshots do not automatically guarantee transactional database backups; (5) why you cannot attach the same ext4 volume read/write to two VMs merely because a block disk supports multi-writer; (6) how to transition to Filestore if three VMs need to share files; (7) why billing rises even when `du` stays low; and (8) what checks prevent boot failures caused by `/etc/fstab`.

## Official References

- [Create a Persistent Disk volume](https://cloud.google.com/compute/docs/disks/add-persistent-disk) — creating and attaching disks to VMs.
- [Format and mount a non-boot disk on Linux](https://cloud.google.com/compute/docs/disks/format-mount-disk-linux) — filesystems, `/dev/disk/by-id`, and `/etc/fstab`.
- [Resize Persistent Disk](https://cloud.google.com/compute/docs/disks/resize-persistent-disk) — expanding disks, partitions, ext4/XFS, and limits.
- [Modify Hyperdisk size and performance](https://cloud.google.com/compute/docs/disks/modify-hyperdisks) — Hyperdisk capacity, provisioned IOPS/throughput.
- [Persistent Disk and Hyperdisk overview](https://cloud.google.com/compute/docs/disks) — disk types, performance, and features.
- [Detach and reattach disks](https://cloud.google.com/compute/docs/disks/detach-reattach-boot-disk) — detaching/attaching and auto-delete/guest OS caveats.
- [Create and manage disk snapshots](https://cloud.google.com/compute/docs/disks/create-snapshots) — data protection and snapshots.
- [Schedule disk snapshots](https://cloud.google.com/compute/docs/disks/scheduled-snapshots) — snapshot schedules and retention.
- [Mount Filestore shares on Compute Engine](https://cloud.google.com/filestore/docs/mounting-fileshares) — NFS client, `fstab`, networking.
- [Filestore overview](https://cloud.google.com/filestore/docs/overview) — file storage and service tiers.
- [Compute Engine disk pricing](https://cloud.google.com/compute/disks-image-pricing) — storage, performance, and snapshots.
- [Filestore pricing](https://cloud.google.com/filestore/pricing) — file shares by tier/capacity.
