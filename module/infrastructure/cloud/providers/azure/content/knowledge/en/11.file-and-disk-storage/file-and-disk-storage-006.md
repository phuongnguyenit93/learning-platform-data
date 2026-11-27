# Managed Disks and Choosing Disk Types for Virtual Machines

When deploying an Azure Virtual Machine (VM), you do not only choose vCPU count and RAM. Disk performance, durability, and cost determine OS boot time, database read/write speed, log processing capacity, and recovery time when a VM fails. A powerful VM paired with an unsuitable disk type will still perform poorly; conversely, buying an ultra-fast disk when the VM cannot process the I/O only drives up costs.

**Azure Managed Disks** provide block storage volumes for Azure VMs. Azure manages the underlying storage infrastructure while operators choose disk type, size, performance characteristics, redundancy, security, and how disks attach to VMs. This lesson focuses on **understanding managed disks and selecting the right disk type for a VM**, not merely creating a Disk resource.

This lesson belongs to the **File and Disk Storage** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores Microsoft Azure from subscriptions, resource groups, and Entra ID to virtual networks, compute, storage, data, deployment, monitoring, protection, and cost control for an application architecture. Managed disks bridge **compute** and **storage**: choosing properly balances application speed, availability, backup/recovery, and budget.

After this lesson, you will be able to:

- Distinguish managed disks, OS disks, data disks, temporary disks, and ephemeral OS disks.
- Compare Standard HDD, Standard SSD, Premium SSD, Premium SSD v2, and Ultra Disk.
- Calculate IOPS and throughput requirements and evaluate latency by workload.
- Understand performance caps at both the **disk** and **VM** layers, plus the effects of host caching and bursting.
- Select disk types for web servers, file servers, batch jobs, databases, and high-performance workloads.
- Evaluate availability zones, redundancy, snapshots, backups, encryption, and lifecycle management.
- Create/inspect managed disks via Azure Portal or Azure CLI, and attach them to lab VMs when permitted.

## 1. What Is a Managed Disk?

In the Azure Managed Disks model, you create a disk resource with attributes such as:

- **Location** (region), and optionally an **Availability Zone** per design.
- **SKU/disk type**, such as Standard SSD or Premium SSD.
- **Size** in GiB along with corresponding performance limits.
- **Redundancy** and supported security/encryption options.
- **Usage state**: unattached, attached to a VM, or undergoing lifecycle operations.

Azure automatically manages the underlying block storage layout. You **do not** have to create and manage a storage account just to store each virtual hard disk (VHD) as in the legacy unmanaged disks model. In Azure Resource Manager, a managed disk is a standalone resource with its own ID, enabling independent RBAC, tagging, cost tracking, and lifecycle management separate from the VM.

~~~text
Azure subscription
└── Resource group: rg-app-prod
    ├── Virtual machine: vm-app-01
    │   ├── OS disk: disk-app-os
    │   └── Data disk: disk-app-data-01
    │
    ├── Managed disk: disk-app-os       (attached to VM)
    ├── Managed disk: disk-app-data-01  (attached to VM)
    └── Managed disk: disk-backup-test  (unattached)
~~~

The diagram depicts logical relationships only. A disk is a separately managed resource and does not strictly have to reside "inside" the VM or even in the same resource group in all valid scenarios. Verify region/zone constraints and rules when attaching.

**Key distinction:** managed disks **differ from Azure Files and Azure Blob Storage**. A managed disk is a block storage device serving VMs or supported configurations; Azure Files provides file-protocol shares; Blob Storage provides an object API. Never treat a managed disk as an arbitrary multi-machine "shared network drive" without properly designing shared disks and clustering mechanisms.

## 2. OS Disks, Data Disks, Temporary Disks, and Ephemeral OS Disks

A VM can have multiple storage types with very different semantics.

| Component | Purpose | Is data persistent? | Notes |
|---|---|---|---|
| **Managed OS disk** | Holds the OS that boots the VM | Yes, per managed disk characteristics | Requires backups and an appropriate SKU |
| **Managed data disk** | Stores application data, databases, logs, dedicated files | Yes, per managed disk characteristics | Can attach/detach as supported; requires formatting/mounting in guest OS |
| **Temporary/local disk** | Stores temp files, scratch, swap/pagefile, or regenerable caches | **No data persistence guarantee** | Data may be lost during redeployment, maintenance, or host lifecycle events |
| **Ephemeral OS disk** | OS disk placed on local host storage for fast-reimaging VMs | **Not** for long-term OS state | Supported only on compatible VM sizes/configurations |

### Managed OS disk

This is the Windows/Linux boot drive for the virtual machine. For standard VMs, the OS disk is a managed disk; OS data persists outside RAM and does not vanish simply when you restart the VM. **Deleting a VM** may delete or retain the OS disk depending on its **delete option**; always verify lifecycle policies when creating or deleting VMs.

Do not treat the OS disk as the sole home for critical data. For applications requiring independent recovery, typically place databases or business data on **data disks** with proper backups.

### Data disk

A data disk is an additional disk exposed to the VM as a block device. Inside the guest OS, you may need to create partitions, filesystems, mount points, or volumes. Example:

~~~text
Linux VM
  /                    → managed OS disk
  /var/lib/myapp       → managed data disk
  /mnt/scratch         → temporary disk (not for persistent data)
~~~

A newly created managed data disk usually has no filesystem. **Attaching a disk in Azure does not automatically create a formatted and mounted directory** inside Linux or Windows.

### Temporary disk

Many VM sizes include **temporary storage** attached to the host, appearing at different paths depending on OS and configuration. This is **not a managed disk**. Data stored there can be lost during maintenance, live migration, or host replacement, so use it strictly for regenerable data.

Never place primary databases, sole backups, security keys, or irreplaceable business files on a temporary disk. Additionally, some VM sizes have no temporary disk; do not design applications to assume one exists by default.

### Ephemeral OS disk

An **ephemeral OS disk** places OS data onto local VM host storage in supported configurations to serve **stateless** workloads that can be recreated rapidly, such as scale-out pools. It differs from a temporary data disk even though both rely on local host storage in certain models.

Ephemeral OS disks are **unsuitable** if you expect OS modifications to survive all host events or want traditional managed OS disk backup/snapshot operations. Before using them, verify current support for VM size, image, caching/placement, capacity, and feature limits.

## 3. Five Common Managed Disk Options

Azure offers multiple disk types. SKU names, supportability, and pricing vary by region, VM size, and time; the table below describes **design roles**, not static benchmark numbers.

| Disk type | General characteristics | Typical suitable workloads | What to verify |
|---|---|---|---|
| **Standard HDD** | Low storage cost; latency and throughput less consistent than SSD | Infrequently accessed data, light batch jobs, I/O-insensitive dev/test | Unsuitable for low-latency apps; availability/SKU |
| **Standard SSD** | Baseline SSD, generally more consistent than HDD for light/moderate loads | Small web apps, dev/test, low-to-moderate enterprise workloads | Performance scales with size/tier; VM limits |
| **Premium SSD** | High-performance SSD for production with multiple size/performance tiers | Production web/API, app servers, moderate databases | Performance tiers, host caching, conditional bursting |
| **Premium SSD v2** | More flexible independent sizing of capacity, IOPS, and throughput | Databases or workloads needing performance decoupled from capacity | **Data disk only**, not for OS disk; VM/region/zone and caching limits |
| **Ultra Disk** | High IOPS/throughput targeting ultra-low latency and specialized workloads | Very large transactional databases, I/O-intensive systems | **Data disk only**, not for OS disk; VM/region/zone support and other limits |

### Standard HDD: cost-first, slower acceptable

Standard HDD fits when data does not need continuous read/write activity, random access is low, and throughput is non-critical. Examples include small lab VMs or rarely accessed data. However, low cost per GiB **does not equal** low total system cost: if batch jobs take much longer or require extra VMs to compensate for slow I/O, overall costs can rise.

### Standard SSD: balanced starting point

Standard SSD is often a sensible baseline for realistic test environments, low-I/O application servers, or workloads not yet profiled enough to justify Premium investment. Monitor metrics before upgrading.

### Premium SSD: common production choice

Premium SSD typically fits when applications need better IOPS and latency while retaining familiar manageability. Performance depends on **disk size/performance tier** and support conditions. You can pay for a larger size/tier to unlock higher IOPS/throughput, provided the VM itself supports that I/O rate.

### Premium SSD v2: decoupling performance from capacity

Premium SSD v2 allows configuring **size**, **provisioned IOPS**, and **provisioned throughput** independently within supported ranges; it fits well when moderate capacity still demands high IOPS. Baselines and resource caps apply; values cannot be set arbitrarily beyond limits.

**Do not use Premium SSD v2 for OS disks.** It is strictly a **data disk** type. Support for host caching, snapshots, backups, redundancy, VM families, and Availability Zones must be checked separately; never blindly copy standard Premium SSD configurations.

### Ultra Disk: specialized workloads

Ultra Disk targets peak performance and ultra-low latency demands, requiring supported VMs, compatible regions/zones, and dedicated configuration. You can tune IOPS/throughput within each disk size's boundaries. **Ultra Disk is a data disk only**, never an OS disk, and do not assume backup/caching/redundancy features match Premium SSD.

If a workload is merely a static-file website or light task server, Ultra Disk is almost certainly not the first option to evaluate.

## 4. Don't Pick Disks by GiB Alone: IOPS, Throughput, and Latency

Three metrics to measure:

1. **IOPS (I/O operations per second):** number of read/write operations per second.
2. **Throughput:** volume of data transferred per second, typically expressed in MB/s or MiB/s.
3. **Latency:** time to complete a single I/O operation, typically in ms. For interactive transactions, p95/p99 tail latency matters more than simple averages.

**High IOPS** benefits workloads with many small requests, such as OLTP databases. **High throughput** benefits large data streams, such as sequential file reads or batch processing. Latency reveals how slow each individual I/O is and directly impacts application responsiveness.

### Simple calculation example

Suppose an application drives **6,000 IOPS** with an average I/O size of **16 KiB**. Theoretical throughput:

~~~text
6,000 I/O/s × 16 KiB/I/O = 96,000 KiB/s
96,000 / 1,024 = 93.75 MiB/s
~~~

If the workload grows to **12,000 IOPS** at the same I/O size, throughput rises to roughly **187.5 MiB/s**. Therefore, when selecting a disk, you must satisfy **both** operation rate and byte rate simultaneously.

Reverse example: a workload needs **150 MiB/s** with an average I/O size of **16 KiB**:

~~~text
150 MiB/s × 1,024 KiB/MiB ÷ 16 KiB/I/O
= 9,600 IOPS
~~~

These formulas provide **preliminary estimates**, not benchmark guarantees. Real I/O mixes reads/writes, random/sequential patterns, queue depth, caching, and application/filesystem limits. When comparing against Azure docs using **MB/s**, watch the difference between MB (decimal) and MiB (binary).

### Profile the workload before purchasing

| Question | Significance |
|---|---|
| What are peak and p95/p99 IOPS? | Evaluates real demand rather than daily averages |
| Typical I/O size? | Converts IOPS to throughput |
| Read/write ratio? | Determines caching benefits and write behavior |
| Random or sequential? | Affects latency and throughput |
| How long must data be retained? | Drives capacity, backup, and lifecycle choices |
| Can the app tolerate throttling/latency spikes? | Guides headroom reserves and bursting reliance |
| Recovery window after disk/VM failure? | Dictates backup, redundancy, and DR design |

Never infer an application needs a fast disk solely from total stored GiB (e.g., 200 GiB used). **Capacity** and **I/O demand** are two separate dimensions.

## 5. How Fast a Disk Runs Also Depends on the VM

Every VM size enforces limits on attachable data disk count, **maximum uncached disk IOPS/throughput**, and sometimes cached I/O, networking, or Premium/Ultra support. A disk capable of 20,000 IOPS will never deliver 20,000 IOPS if the VM caps out lower.

~~~text
Application
    |
Guest OS / filesystem / driver
    |
Azure VM size (IOPS/throughput limits)
    |
Host cache (if enabled and supported)
    |
Managed disk (size/SKU/performance limits)
    |
Azure storage backend
~~~

Observed performance reflects the **end-to-end path**, governed by the tightest bottleneck. Conceptual approximation:

~~~text
Actual IOPS ≲ min(
    IOPS generated by app/OS,
    relevant VM IOPS limit,
    effective disk IOPS limit
)

Actual throughput ≲ min(
    throughput from app/OS,
    relevant VM throughput limit,
    effective disk throughput limit
)
~~~

This mental model helps locate bottlenecks rather than modeling every detail of caching and scheduling. With multiple disks, VM-wide aggregate caps still apply; you cannot sum disk IOPS indefinitely past the VM ceiling.

### Configuration selection example

Suppose a database needs **10,000 IOPS**, around **160 MiB/s**, and 500 GiB usable capacity. You should:

1. Select a database-capable VM family/size whose **uncached** disk throughput/IOPS exceeds requirements with headroom.
2. Choose a data disk SKU/size capable of sustaining that IOPS and throughput.
3. Verify region/zone and caching support for the VM–disk pairing.
4. Benchmark with a representative workload rather than purely sequential I/O tests.
5. Monitor as user counts grow or queries/indexes evolve.

No single SKU answer follows from those three numbers alone without knowing workload mix, latency SLOs, I/O distribution, VM compatibility, and regional pricing.

## 6. Host Caching, Bursting, and Striping

### Host caching

Some VM/disk pairs support **host caching** (e.g., None, ReadOnly, or ReadWrite depending on disk type and OS/data role). Caching can accelerate certain read workloads but requires careful review of write patterns and data consistency.

- **ReadOnly** can help repeated read workloads when supported.
- **ReadWrite** is unsuitable for all write patterns and strict consistency systems; always check database/application and Azure recommendations.
- **None** disables host caching for that disk and may be required for specific workloads or disk types.

Premium SSD v2 and Ultra Disk carry host caching restrictions; **do not assume** standard Premium SSD caching modes apply to them.

A database may recommend different cache modes for OS disks, data files, and transaction logs. Follow guidance from both the database engine and the disk type in use.

### Bursting

Certain disk SKUs/sizes support **disk bursting** to absorb short I/O spikes. Credit-based or on-demand bursting mechanisms exist depending on product line. Bursting does not guarantee sustained high IOPS continuously.

For instance, a VM booting or applying package updates for a few minutes benefits from short bursts, whereas a high-load transactional database running **all day** should be sized for sustained performance rather than relying on burst credits.

### Striping / combining multiple data disks

For workloads needing higher throughput/IOPS, you can use **Storage Spaces** on Windows or **LVM/RAID in supported designs** on Linux to combine multiple data disks into one volume. However:

- VM-wide aggregate IOPS/throughput and disk count limits still apply.
- Performance depends on stripe size, queue depth, and I/O patterns.
- Application backups/snapshots must maintain consistency across the entire volume set.
- Volume expansion and recovery procedures must prevent data loss.

Do not treat striping as the default before evaluating Premium SSD v2, Ultra Disk, or a better-suited VM size.

## 7. Choosing Disk Types by Workload

### Web/API servers

Web servers typically read executables and libraries and write modest logs. If the service is genuinely **stateless**, store critical data in managed databases/storage rather than solely on the OS disk.

- Dev/test or light I/O: **Standard SSD** is a practical starting point for measurement.
- Production needing fast boots, steady response, and higher I/O: consider **Premium SSD** if metrics justify it.
- Do not start with Ultra Disk simply because an app serves many HTTP requests; bottlenecks often lie in CPU, networking, or databases.

### Transactional databases (OLTP)

Databases typically generate heavy small I/O and are latency-sensitive. Separate data and logs as needed for administration, recovery, and tuning:

- **Premium SSD**: common starting point for moderate databases.
- **Premium SSD v2**: worth evaluating if flexible IOPS/throughput tuning is needed.
- **Ultra Disk**: reserved for exceptionally demanding I/O and latency needs after verifying VM/region support.

Consider read/write ratios, transaction logs, and checkpoint behavior rather than choosing a disk purely from theoretical total IOPS.

### File servers or file processing services

If only one VM needs an application data drive, Standard SSD or Premium SSD may suffice. If the requirement is **multiple VMs accessing a shared folder over SMB**, evaluate **Azure Files** or a supported file-sharing service before attempting shared managed disks.

### Batch, data processing, and scratch

Large batch jobs often favor sequential throughput over IOPS. Regenerable scratch data can sometimes leverage temporary/ephemeral storage strategies, while critical inputs and outputs must reside on durable storage. For batch jobs with vital checkpoints, use managed disks or appropriate object storage/backups.

### Systems needing thousands of IOPS

Do not jump straight to Ultra Disk. Measure actual demand first, pick a compatible VM size, check whether Premium SSD v2 or Premium SSD meets requirements, and compare total cost alongside HA/backup support.

## 8. Short Decision Matrix by Priority

| Priority | First candidates to evaluate | Rationale |
|---|---|---|
| Low cost, light I/O, latency-insensitive | Standard HDD | Lower storage cost in exchange for I/O responsiveness |
| Balanced price/performance for dev/test or light apps | Standard SSD | Low complexity, suited to many baseline workloads |
| Production needing steadier latency/IOPS | Premium SSD | Familiar choice with broad manageability support |
| Scaling IOPS without scaling capacity in legacy tiers | Premium SSD v2 | More independent performance tuning |
| Very large databases, ultra-low latency, extreme I/O | Ultra Disk | Specialized performance architecture with specific compatibility prerequisites |
| OS disk for traditional VMs | Standard SSD or Premium SSD per VM/workload | Premium SSD v2 and Ultra Disk are not intended for OS disks |
| Disposably regenerable scratch data | Temporary/local storage when provided by VM | Must not be treated as persistent managed disks |

**Note:** this table is a **shortlist** guide and does not replace checking SKU docs and benchmarking. Certain disk types restrict backup, snapshot, caching, ZRS, bursting, zone, and VM size support. Always verify at deployment time.

## 9. Availability Zones, Redundancy, and Resilience

A managed disk is a storage resource within an Azure **region**. Certain disk types and regions support **LRS (locally redundant storage)** and **ZRS (zone-redundant storage)** in compatible configurations.

### LRS vs. ZRS

- **LRS:** maintains redundant data copies within a single storage fault domain scope per service design.
- **ZRS:** replicates synchronously across Availability Zones within a supported region to improve zone-level fault tolerance for supported managed disk types.

**ZRS does not equal cross-region replication.** If your goal is surviving an entire regional outage, design application- or service-level backup/replication/DR, such as Azure Site Recovery or database-native replication.

### Selecting zones for VMs and disks

A VM placed in **zone 1** must use disks compliant with regional/zonal placement rules and disk type constraints. Some disks are zonally pinned; ZRS configurations have distinct behaviors. Never assume an arbitrary disk from any zone/region can attach to any VM.

Before creating VMs:

1. Confirm the disk type and VM size are supported in the target region/zone.
2. Select redundancy based on zonal failure risk and budget.
3. Use Availability Sets/Zones or scale-out architectures for compute resilience.
4. Design backups/restores for valuable data.
5. Verify permissions, encryption, and current attach/move capabilities.

### Disk durability does not replace backups

Even a highly redundant managed disk can hold data **accidentally deleted, encrypted by ransomware, or corrupted by application bugs**. Logical errors replicate synchronously across storage copies. Retention-backed backups, tested restores, and deletion protections remain essential.

## 10. Snapshots, Azure Backup, and Disaster Recovery

### Snapshots

A snapshot captures point-in-time disk state as supported by the service. It helps with cloning, testing, or restoring disks. However:

- Snapshots are not automatically **application-consistent** for a running database.
- Multi-disk workloads require cross-disk consistency handling.
- Snapshots require retention policies, access control, and cost tracking.
- Disk types differ in snapshot support and APIs.

### Azure Backup

**Azure Backup** for Azure VMs defines protection and recovery policies tailored to VM/disk capabilities rather than manual file copies. When designing, specify:

- RPO/RTO and backup retention duration.
- Full-VM backups vs. workload/database-specific policies.
- Disk inclusion/exclusion scope, consistency modes, and SKU limitations.
- Encryption keys, RBAC, and recovery steps during regional or account outages.

**Never assume** every disk SKU shares identical backup features or pricing. Cross-check the Azure Backup support matrix against your VM, disk, and region.

### Region failover

To mitigate full-region outages, evaluate multi-region architectures, Azure Site Recovery for supported workloads, or data-tier replication mechanisms. Each solution carries distinct RPO/RTO and constraints; **never treat an LRS disk snapshot as a complete multi-region DR plan**.

A true DR drill must verify the VM boots, data is consistent, services connect, and applications process transactions cleanly.

## 11. Managed Disk Security and Encryption

### Server-side encryption at rest

Azure Managed Disks are encrypted at rest via platform **server-side encryption (SSE)**. You can use Microsoft-managed keys by default or evaluate **customer-managed keys (CMK)** via a **Disk Encryption Set** when required by security/compliance policy.

With CMK, design:

- Key access rights and required identities/permissions.
- Availability of Azure Key Vault or Managed HSM per supported models.
- Key rotation, recovery, and impact if a key is disabled or deleted.
- Resource regions, subscriptions, and disk SKU compatibility rules.

**SSE/CMK does not replace Azure RBAC or backups.** An identity holding disk-deletion permissions can still cause an outage even when data is encrypted.

### Encryption at host and in-guest encryption

Azure also provides capabilities such as **encryption at host** or guest-OS encryption depending on workload and supported configuration. **Azure Disk Encryption (ADE)** with BitLocker/dm-crypt is distinct from SSE; do not stack them blindly or assume every VM/disk supports every combination.

Choose based on policy, service support, and key lifecycle. Review **OS disks, data disks, snapshots, backups, and recovery regions** end to end.

### Authorization and governance

Disks can be governed via Azure RBAC at subscription, resource group, or individual resource scopes. Only authorized operators should create, attach/detach, export, snapshot, or delete disks. In particular, disk/snapshot export permissions expose raw data access risk and must be treated as sensitive operations.

For critical data, evaluate Azure Policy, resource locks, tagging, Activity Logs, and configuration-change alerts. A **CanNotDelete lock** prevents accidental control-plane deletion but does not block corrupt writes inside the guest OS.

## 12. Lifecycle Management: Create, Attach, Resize, Detach, and Delete

A managed disk can exist **independently** of a VM. A disk resource may keep accruing charges even after being detached from a VM unless deleted.

### Create and attach

To use a data disk inside a VM, the typical sequence is:

1. Create a managed disk with the right size/SKU.
2. Attach the disk to the VM using a supported LUN and caching mode.
3. Open the guest OS to discover the new block device.
4. For a brand-new empty disk: partition, format, and mount per OS conventions.
5. Configure persistent mounts, filesystem permissions, and monitoring.

**Strictly distinguish new disks from disks holding existing data:** formatting destroys existing data. When attaching a disk that already contains data, **inspect and mount the filesystem**—never reformat it.

### Resize

Managed disks support capacity expansion subject to disk type, VM state, and size rules. After increasing size in Azure, you typically also need to **extend the partition/filesystem** inside the guest OS. Do not assume resizing in Azure instantly gives applications usable free space.

Do not assume shrinking disks is supported. Depending on product/operation, resizing or switching SKUs may require deallocating the VM, reconfiguring, and scheduling maintenance; check documentation for your exact disk type.

### Detach and delete

Before detaching a data disk from a VM, stop writing applications, unmount cleanly, verify filesystem state, then detach. Never detach a volume holding active database transactions without a consistent shutdown procedure. Once detached, the disk remains a live resource and **may continue incurring charges**.

When deleting a VM, inspect **delete options** for OS disks, data disks, and network interfaces. Never assume deleting a VM always deletes all disks—or retains all disks. Verify before confirming any production deletion.

## 13. Managing Disks via Azure Portal

Example creating a data disk in a lab subscription:

1. Open the [Azure Portal](https://portal.azure.com/) and select the right subscription and resource group.
2. Search for **Disks** and select **Create**.
3. Enter a name like **disk-lab-data-01**, region, and Availability Zone as appropriate.
4. Choose disk type: e.g., **Standard SSD** for a light lab.
5. Select the required size; note **provisioned size** can drive billing regardless of actual written bytes.
6. Set source type to empty disk or an appropriate source if needed.
7. Review supported redundancy and encryption settings.
8. Review estimated pricing, policies, and create the disk.

To attach to a lab VM, go to VM → **Disks** → attach existing data disk → select supported caching → save. Sign into the guest OS to inspect and initialize the volume if brand new. Never format disks on VMs holding valuable data.

### Inspecting disk properties

In the Disks blade, inspect:

- **SKU**, capacity, and zone/region.
- **Managed by** (attached VM) or unattached state.
- Performance parameters such as IOPS/throughput where displayed/configurable for the disk type.
- Encryption, tags, resource ID, access permissions, and cost.
- Snapshots/backups if configured.

Azure Portal labels, limits, and options may vary by SKU/region. If an option does not appear, do not assume every disk type supports it and the Portal is broken; verify support docs.

## 14. Azure CLI: Creating and Inspecting Managed Disks

This section creates **a standalone empty data disk** without provisioning a VM. It is ideal for learning disk resources without risking production filesystems. However, **disks can incur charges even while unattached**, so clean up after finishing the lab.

Examples use **Bash in Azure Cloud Shell**. Windows PowerShell uses different variable syntax and line continuations; adapt commands accordingly if using PowerShell.

### Step 1: Sign in and select subscription

~~~bash
az login
az account list --output table
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table

RG="rg-managed-disk-lab"
REGION="southeastasia"
DISK="disk-lab-data-01"
~~~

Replace **SUBSCRIPTION_ID** with an authorized lab subscription—never run labs on production subscriptions. Even if Cloud Shell is already signed in, confirm the active subscription first.

### Step 2: Create a dedicated resource group

~~~bash
az group create \
  --name "$RG" \
  --location "$REGION" \
  --tags environment=learning purpose=managed-disk-lab
~~~

### Step 3: Create a Standard SSD data disk

~~~bash
az disk create \
  --resource-group "$RG" \
  --name "$DISK" \
  --location "$REGION" \
  --size-gb 32 \
  --sku StandardSSD_LRS \
  --tags environment=learning purpose=managed-disk-lab
~~~

This example picks **32 GiB** and Standard SSD LRS to keep the exercise simple. It is not a default production recommendation. If your subscription/region disallows the SKU or Azure Policy blocks it, follow policy rather than switching arbitrarily to an expensive SKU.

### Step 4: Inspect the created disk

~~~bash
az disk show \
  --resource-group "$RG" \
  --name "$DISK" \
  --query "{name:name,sku:sku.name,sizeGiB:diskSizeGB,state:diskState,location:location,id:id}" \
  --output json

az disk list \
  --resource-group "$RG" \
  --output table
~~~

Inspect **sku.name**, **diskSizeGB**, **diskState**, and **id**. A newly created unattached disk shows the corresponding unattached state. Exact column names/states depend on resource and API version.

### Step 5: Verify SKU compatibility before upgrading

Before choosing Premium SSD v2 or Ultra, confirm VM size, region, Availability Zone, quota, and feature compatibility. Azure CLI can list SKUs/VM sizes and related resources, yet **merely seeing a SKU name in a list is not proof it can attach to a specific VM**.

Also collect **workload metrics**, because a pricier disk does not guarantee a faster application.

### Step 6: Clean up lab resources

After confirming the disk is unattached and the resource group holds only test resources:

~~~bash
az disk delete \
  --resource-group "$RG" \
  --name "$DISK" \
  --yes

az group delete \
  --name "$RG" \
  --yes

az group exists --name "$RG"
~~~

A result of **false** confirms the resource group no longer exists in ARM. Monitor Cost Management since billing data updates with a delay.

**Do not run deletion commands** if using a shared resource group containing others' resources or a disk attached to a real VM. If a disk is attached, stop I/O, detach cleanly, and preserve required data first.

## 15. Attaching a Data Disk to a VM and Preparing Guest OS

If you have a **dedicated lab VM**, you can practice attaching the disk. This is an optional advanced step since running VMs incurs compute charges and formatting mistakes can erase data.

### Attaching via Azure CLI

Assuming a lab VM and disk already exist with compatible region/zone settings:

~~~bash
az vm disk attach \
  --resource-group <LAB_RESOURCE_GROUP> \
  --vm-name <LAB_VM_NAME> \
  --name <EXISTING_LAB_DATA_DISK_NAME>
~~~

Substitute placeholders only after verifying it is an **empty lab data disk**, not an OS disk or user data disk. Some disk types or VM sizes require extra flags; do not force attachment if incompatible.

### Linux: inspect devices before formatting

On Linux, inspect block devices and filesystems:

~~~bash
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,UUID
lsblk -f
~~~

Device paths can vary across VM types, kernels, and reboots. **Never assume a data disk is always `/dev/sdc`** or the next letter after the OS disk. Cross-check size, serial/LUN, and VM documentation before acting.

If the disk is brand new, operators can create a filesystem and mount using standard OS tools. Formatting commands like **mkfs** or **Format-Volume** are destructive; this guide omits hardcoded format commands to prevent formatting the wrong drive. For disks containing existing data, mount only after verifying the filesystem.

For persistent mounts, Linux typically uses **UUIDs in `/etc/fstab`** rather than mutable device names. Test mount options carefully so the VM still boots if the disk is temporarily absent or faulty.

### Windows: check Disk Management

On Windows VMs, check **Disk Management** or PowerShell `Get-Disk`/`Get-Volume` to identify disks by size, status, and disk number. If completely new, initialize the disk, create a volume, format, and assign a drive letter. **Never initialize or format a disk already containing data.**

### Detaching the disk

Before detaching: stop writes, close applications, unmount/offline the volume cleanly, then detach via Portal or Azure CLI per procedure. Ensure application backups and restores are verified for important disks.

## 16. Observing and Diagnosing Disk Performance

When applications run slowly, inspect **both Azure metrics and the guest OS**:

| Signal | Explanation |
|---|---|
| Disk Read/Write Operations | Read/write I/O rate over time |
| Disk Read/Write Bytes | Data read/written, helping estimate throughput |
| Disk latency | I/O response time where exposed by metrics/OS |
| Disk queue length / I/O wait | Operations queuing or waiting on disk |
| Disk bandwidth/IOPS consumed percentage | Shows proximity to VM/disk caps where metric is supported |
| Throttled I/O / VM caps | Indicators of hitting performance ceilings |
| CPU/RAM/cache | Avoid mistaking compute/memory bottlenecks for disk issues |

Azure Monitor exposes supported VM and disk metrics; exact names vary by resource/SKU. The guest OS provides deeper telemetry via tools like **iostat**, **sar**, **perfmon**, **Get-Counter**, and database monitoring.

### Workflow when a database has high latency

1. Identify which requests and timestamps experience slowness; gather p95/p99 latency.
2. Measure IOPS, throughput, queue depth, and read/write ratio.
3. Check whether the VM is hitting its uncached/cached disk IOPS or throughput ceiling.
4. Check whether the disk SKU/size/performance setting is hitting its ceiling.
5. Inspect host caching, filesystem, drivers, and database queries/indexes.
6. If upgrading is needed, pick the lowest-risk change with a rollback plan.
7. Re-benchmark against a representative workload to verify improvement and cost.

**High disk queues do not always prove a weak disk SKU.** They can stem from missing query indexes, inefficient application I/O patterns, or insufficient VM CPU/RAM.

## 17. Disk Selection Scenarios: Three Case Studies

### Scenario A: small internal portal

A VM runs an API storing very little local data, with its database separated into another service. OS capacity is 64 GiB, I/O is low, and cost is prioritized.

**Candidate:** Standard SSD OS disk. Evaluate boot times, actual latency, backups, and upgrade to Premium only if metrics/SLAs show Standard SSD falls short.

### Scenario B: database VM with 700 GiB of data

The app requires 8,000 IOPS, roughly 120 MiB/s at peak, and cares about latency. Data should not share the OS disk.

**Candidate:** Premium SSD data disk, or Premium SSD v2 if supported by VM/region. Pick a VM size with headroom on IOPS/throughput. Separate data/logs and align caching with database engine guidance. Add backup/restore and availability design.

**Do not conclude** Premium SSD v2 is definitely cheaper or faster without checking pricing tables, limits, and workload benchmarks.

### Scenario C: massive data analytics system

Batch workloads perform large sequential reads/writes across multiple TBs; single-transaction latency is not decisive.

**Candidate:** optimize for throughput and total price, potentially using multiple data disks or storing inputs/outputs in Blob Storage. Ultra Disk fits only if measurements prove extraordinary demands. Also consider managed-storage analytics services if they reduce VM operational overhead.

### Comparison template before deciding

| Attribute | Option 1 | Option 2 |
|---|---|---|
| Disk SKU and size | Standard/Premium per quote | Premium SSD v2/Ultra if supported |
| VM size and I/O limits | Verify specifically | Verify specifically |
| Sustained IOPS | >= demand + headroom | >= demand + headroom |
| Sustained throughput | >= demand + headroom | >= demand + headroom |
| Latency p95/p99 | Per benchmark | Per benchmark |
| Availability/redundancy | LRS/ZRS as supported | LRS/ZRS as supported |
| Backup/restore | Supported and tested | Supported and tested |
| Monthly cost | Disk + snapshots + backup + VM | Disk + provisioned perf + backup + VM |

Run **benchmarks in a test environment** with production-like I/O before purchasing large configurations. A large-block sequential benchmark does not accurately model an 8 KiB random-write database.

## 18. Costs: More Than Just Capacity Charges

Managed disks typically bill based on disk type, provisioned capacity, and SKU-specific performance parameters. For some disk types, provisioned IOPS and throughput are billed separately. Additional charges can come from snapshots, backups, redundancy, or transactions per service pricing.

### Commonly overlooked charges

- **Unattached** data disks remain billed resources.
- Old snapshots, cloned disks, and uncleaned test restores.
- Over-provisioned disk sizes bought solely for IOPS/throughput despite low actual data usage.
- Premium SSD v2/Ultra disks configured with provisioned IOPS/throughput far above long-term needs.
- Oversized VMs chosen purely for disk throughput while leaving CPU/RAM idle.
- Cross-region replication, backup, and recovery costs.
- Maintaining standby VMs, software licenses, and monitoring tools.

### Optimization workflow

1. Apply **tags** for owner, environment, and purpose.
2. Use Azure Cost Management to inspect disk/VM spend by resource group.
3. Compare actual demand against disk and VM caps to define reasonable headroom.
4. Adjust SKUs/performance in controlled steps after benchmarking.
5. Audit unattached disks and expired snapshots regularly.
6. Set budget alerts—remembering budget alerts **do not stop spending automatically**.
7. Review costs after each test cycle and clean up lab resources.

## 19. Common Issues

| Symptom | Possible causes | Resolution |
|---|---|---|
| Cannot select Premium SSD v2 or Ultra | Unsupported VM size, region, zone, SKU, or config | Check support matrix; select compatible VM/SKU/zone |
| Newly attached disk missing in File Explorer | Not initialized/partitioned/formatted/mounted in guest OS | Check Disk Management/`lsblk`; format only confirmed new disks |
| Disk visible yet app cannot write | Filesystem permissions, read-only mount, or disk full | Inspect OS logs, filesystem, permissions, and free space |
| High-IOPS disk bought yet VM stays slow | Hit VM IOPS/throughput cap or app bottleneck | Check both VM/disk metrics and app benchmarks |
| High DB latency despite IOPS below cap | Queries/indexes, queue depth, caching, networking, or I/O latency | Measure p95/p99, queues, and inspect DB engine |
| Cannot attach disk to VM in another zone | Different region/zone or disk type disallows such attachment | Verify compatibility and snapshot/copy/DR procedures |
| Disk resized yet filesystem unchanged | Guest partition/filesystem not yet extended | Run guest OS resize procedure with backups |
| VM deleted yet disk still incurs charges | Delete option retained disk or disk was not auto-deleted | Audit unattached disks and retention policies before cleanup |
| Detached disk fails deletion | Residual state/resource dependency or RBAC permissions | Inspect `managedBy`/`diskState` and RBAC roles |
| Scratch data vanishes on VM restart | Stored on temporary disk or ephemeral OS storage | Move persistent data to managed disks or managed services |
| Backup fails with newer disk SKU | Feature unsupported or config misses prerequisites | Check Azure Backup and disk support matrices |
| Encrypted data becomes inaccessible | CMK/Key Vault permissions or disabled key | Check key availability, DES, identity, and key recovery |
| Logical data loss despite LRS/ZRS | Accidental delete/overwrite replicated synchronously | Configure backups/retention and test restores |

When reporting issues, gather **VM size, disk SKU, disk resource ID, zone/region, IOPS/throughput, metrics, OS logs, and recent changes**. Never include credentials or secrets in tickets or logs.

## 20. Hands-On Exercises and Self-Check Questions

### Exercise 1: Choosing disk types

For the three workloads below, build a table proposing disk SKUs and rationales:

1. Internal web server, 64 GiB OS, 500 IOPS, data stored in Azure SQL Database.
2. VM running an 800 GiB transactional database, 12,000 peak IOPS, 16 KiB average I/O, low latency required.
3. Batch video processor reading and writing hundreds of GiB per run, most intermediate data regenerable.

For workload 2, compute preliminary throughput:

~~~text
12,000 I/O/s × 16 KiB/I/O = 192,000 KiB/s
192,000 / 1,024 = 187.5 MiB/s
~~~

Then check **VM max uncached IOPS/throughput**, latency requirements, region/zone, and cost before finalizing the SKU.

### Exercise 2: Designing for safety

A database VM requires daily backups, recovery from accidental deletions, and restoration within a business-defined SLA. Determine:

- How should OS disks and data disks be separated?
- Which snapshot/backup strategy creates compliant recovery points?
- How will you verify transactional consistency and test restores?
- Is a standby region needed? If so, what RPO/RTO applies?
- Who is allowed to export/delete disks and alter encryption keys?

### Self-Check Questions

1. How does a managed disk differ from a temporary disk?
2. Why should Premium SSD v2 and Ultra Disk not be chosen as OS disks?
3. How are IOPS, throughput, and latency related?
4. If a disk supports high IOPS yet the VM lacks uncached throughput, what happens?
5. When does host caching help, and why must databases use caution?
6. Can disk bursting replace proper sizing for sustained workloads?
7. Why does ZRS not replace a multi-region DR plan?
8. Is a snapshot of a running database disk always application-consistent?
9. Is Azure Disk Encryption identical to default SSE/CMK?
10. Why does detaching a disk from a VM not stop billing?
11. When a new data disk does not appear as a Linux directory, which steps are missing?
12. Would you pick Standard SSD, Premium SSD, or Ultra without workload metrics? Why or why not?

## 21. Pre-Production Checklist

- [ ] Workload profile documented: capacity, IOPS, throughput, read/write ratio, block size, and latency SLO.
- [ ] Verified VM size supports disk SKU, disk count, region/zone, and I/O limits.
- [ ] OS disks, data disks, and temporary storage used strictly for intended purposes.
- [ ] Disk size/tier and IOPS/throughput include adequate headroom without relying solely on bursting.
- [ ] Host caching matches workload guidance and disk type.
- [ ] Backup, retention, restore tests, and DR plans align with RPO/RTO.
- [ ] LRS/ZRS and Availability Zones selected per supportability, not confused with cross-region replication.
- [ ] SSE/CMK, key governance, RBAC, and auditing meet policy.
- [ ] Disk deletion options, tags, owners, and cleanup procedures defined.
- [ ] Both VM-level and disk-level limits monitored; latency and disk space alerts configured.
- [ ] Disk expansion, mounting, and restoration tested in a non-critical environment.
- [ ] Costs budgeted across disks, VMs, snapshots, backups, and unattached resources.

## 22. References

- [Introduction to Azure managed disks](https://learn.microsoft.com/azure/virtual-machines/managed-disks-overview) — managed disk model, SKUs, and features.
- [Select a disk type for Azure IaaS VMs](https://learn.microsoft.com/azure/virtual-machines/disks-types) — Standard HDD/SSD, Premium SSD, Premium SSD v2, and Ultra Disk.
- [Azure VM disk performance](https://learn.microsoft.com/azure/virtual-machines/disks-performance) — evaluating IOPS, throughput, and VM/disk limits.
- [Disk caching for Azure virtual machines](https://learn.microsoft.com/azure/virtual-machines/premium-storage-performance#disk-caching) — caching and performance considerations.
- [Azure managed disk encryption](https://learn.microsoft.com/azure/virtual-machines/disk-encryption) — encryption and key management.
- [Azure Backup for Azure virtual machines](https://learn.microsoft.com/azure/backup/backup-azure-vms-introduction) — VM backup and recovery.
- [Azure CLI: az disk](https://learn.microsoft.com/cli/azure/disk) — creating, reading, updating, and deleting disks.
- [Azure CLI: az vm disk](https://learn.microsoft.com/cli/azure/vm/disk) — attaching/detaching and managing VM data disks.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating disk/VM costs in a chosen region.

**Conclusion:** Selecting managed disks for Azure VMs must start from **I/O patterns, VM limits, latency requirements, recovery targets, and total cost**, never capacity or SKU names alone. For most applications, measure first on Standard SSD or Premium SSD; move to Premium SSD v2 or Ultra only when workload telemetry and supportability truly warrant it. Regardless of disk type, store critical data on durable storage, configure backups/restores, restrict operational permissions, and regularly test recovery.
