# Choosing Block Storage, File Storage, and Object Storage on GCP

## Learning Objectives

After this lesson, learners will be able to:

1. Distinguish between **block storage**, **file storage**, and **object storage** by access interface, data unit, shareability, latency, consistency, and billing model.
2. Choose among **Google Cloud Hyperdisk**, **Persistent Disk**, **Local SSD**, **Filestore**, **Google Cloud Managed Lustre**, **Google Cloud NetApp Volumes**, and **Cloud Storage** for specific workloads.
3. Understand why **Cloud Storage FUSE** does not turn object storage into a conventional POSIX/NFS file system, and why a database requiring random writes should not be placed on an object mount.
4. Design around **IOPS, throughput, latency, RPO/RTO, storage location, concurrent access, IAM, VPC**, and data management requirements.
5. Practice creating/inspecting Compute Engine disks, mounting Filestore file shares, creating buckets, and manipulating objects safely using **gcloud**.
6. Identify commonly overlooked costs, select backup tools, and build testing and operations checklists for VMs, GKE, Cloud Run, database services, and Java applications.

## 1. Why Are They All Called "Storage" Yet Cannot Be Used Interchangeably?

An e-commerce system on Google Cloud typically has multiple types of data:

- **Boot volumes and database files** of a VM running PostgreSQL or a Java application.
- **Shared directories** read/written by multiple VMs or pods when processing documents.
- **Product images, videos, PDF documents, backups, and logs** accessed by object name.
- **Temporary data** for sorting, shuffling, caching, or building AI models.

Choosing the same service for every need can cause failures in **APIs**, **locking**, **latency**, **scalability**, **durability**, **shareability**, or **cost**.

In the **CLOUD_PROVIDERS_GCP** module, learners deploy projects/IAM/VPCs, Compute Engine, GKE, Cloud Run, storage, and databases, while also automating releases, protecting resources, and monitoring both reliability and cost. Storage decisions must therefore start from **application behavior**, not just the price table per GiB.

### Three Opening Questions

1. Does the application need a **block device** to format its own file system and read/write by block address?
2. Do multiple machines/pods need a **shared directory tree** with file, directory, rename, file lock, and file permission operations?
3. Is data managed as **complete objects** over an HTTP API, with metadata, versioning, lifecycle management, and large-scale distribution?

If the answers are respectively **yes**, the initial direction is usually **block**, **file**, or **object storage**. In some cases, all three types should be combined.

## 2. Block, File, Object: At Which Abstraction Layer Do They Differ?

### 2.1. Block storage

Block storage provides a VM or node with a **storage device that can be read and written in blocks**. The guest OS decides how to format **ext4, XFS, NTFS**, create the filesystem, set the mount path, and handle locking. The storage provider does not inherently know whether a block belongs to "orders.db" or "index.bin".

~~~text
Java app or PostgreSQL
  ↓ system calls
Guest OS: ext4/XFS/NTFS + buffer cache
  ↓ block read/write
/dev/disk/by-id/google-data-disk
  ↓
Persistent Disk or Hyperdisk
~~~

**Best suited for:** boot disks, VM-local application data, self-managed transactional databases, index engines, and workloads requiring random I/O and block-level semantics.

### 2.2. File storage

File storage provides a **file share** over network protocols such as **NFS** or **SMB**. The storage system manages the directory structure, files, and metadata; multiple clients can mount the same export simultaneously.

~~~text
VM A: /mnt/shared/reports/2026.csv ─┐
                                    ├── NFS / SMB server
VM B: /mnt/shared/reports/2026.csv ─┘       ↓
                                      Filestore / NetApp
~~~

**Best suited for:** shared workspaces, content shared across multiple VMs/pods, legacy software requiring filesystem paths, and workloads using POSIX file locking and metadata.

### 2.3. Object storage

Object storage manages data by **bucket → object name → bytes + metadata**. APIs operate on objects: upload, read, list, delete, copy, update metadata, and create new generations. An **object name** can contain **/** characters to represent prefixes, but the object API does not inherently provide all directory/file descriptor semantics of a file system.

~~~text
Java app
  ↓ Cloud Storage client library / HTTPS API
gs://shop-product-media/images/sku-1001.jpg
  = bucket + object name
  + content type, generation, custom metadata, ...
~~~

**Best suited for:** images/videos, documents, analytics data, artifacts, backups, archives, static assets, and data accessed across multiple services via API.

### 2.4. Core Comparison Table

| Criterion | Block storage | File storage | Object storage |
|---|---|---|---|
| Access unit | Block/device | File, directory | Object and metadata |
| Application interface | Block device + OS file system | NFS/SMB or file protocol | HTTP API, SDK, CLI |
| Resource naming | Disk/volume + device path | Server IP and export path | Bucket and object name |
| GCP examples | Hyperdisk, Persistent Disk | Filestore, Managed Lustre, NetApp Volumes | Cloud Storage |
| Small incremental writes | **Good**, block-level | **Good**, per file system semantics | Usually requires writing a new object/generation |
| Multi-client read/write | Depends on disk access mode and clustered FS | Designed purpose of a file share | Multiple clients via API; concurrent update control required |
| POSIX filesystem | Created and managed by the OS | Yes, depending on product/protocol | **Not by default**; FUSE is not fully POSIX |
| Network scope | Disk attached to VM/node, with zone/region limits | VPC, IP, NFS/SMB ports | Google Cloud APIs, IAM, endpoint/network policy |
| Scalability | Disk size/performance + VM limits | Tier, share capacity, client throughput | Object capacity scales per service model |
| Access latency | Usually suitable for low-latency random I/O | Depends on NFS/network/tier | API and network; does not replace block latency |
| Fault tolerance | Zonal or regional replication depending on product | Zonal/regional/service tier depending on type | Choose regional/dual-region/multi-region location and protection settings |
| Cost model | Provisioned GiB, IOPS, throughput, snapshots | Provisioned share capacity, performance, backups, network | Stored bytes, operations, retrieval, egress, retention |

**No type is "always faster"**: a multi-threaded request reading a 2 GiB object can achieve high throughput; that does not make it suitable for writing individual 4 KiB pages of a database.

## 3. Block Storage on Google Cloud: Persistent Disk, Hyperdisk, and Local SSD

### 3.1. Persistent Disk: Durable Block Storage Attached to VMs

**Persistent Disk** is Compute Engine's network-attached block storage that exists independently of the VM's physical host. A disk can be retained when a VM is deleted if the **auto-delete**/deletion rule is configured accordingly; it can be detached and attached to another VM within supported scopes and modes.

Common types:

| Disk type | API/CLI code | Best suited for | Notes |
|---|---|---|---|
| Standard Persistent Disk | **pd-standard** | Sequential I/O, large-volume cost-sensitive data | HDD, lower random IOPS than SSD |
| Balanced Persistent Disk | **pd-balanced** | General-purpose boot/data disks | SSD, balanced performance and price |
| SSD Persistent Disk | **pd-ssd** | Databases, transactional random I/O | SSD, better throughput/IOPS depending on size and VM |
| Extreme Persistent Disk | **pd-extreme** | Databases requiring high IOPS | Only on supported machine types, separate IOPS configuration |

**Common pitfall:** when creating a disk without specifying a type, the **Google Cloud Console** default may be **pd-balanced**, whereas **gcloud/API** may default to **pd-standard**. Always declare **--type** explicitly and verify the result.

**Persistent Disk performance** generally scales with provisioned capacity and is bounded by **machine series, vCPU count, network egress, number of attached disks, and I/O size**. A small pd-ssd disk on a very weak machine will not automatically achieve the performance of a large disk on a machine with sufficient vCPUs.

### 3.2. Hyperdisk: Block Storage Decoupling Capacity and Performance

**Hyperdisk** provides the ability to configure **capacity** relatively independently of **provisioned performance** within product limits, making it possible to scale IOPS or throughput up/down without necessarily resizing the disk.

| Hyperdisk Type | Reference code | Best suited for |
|---|---|---|
| **Hyperdisk Balanced** | **hyperdisk-balanced** | Most VMs, enterprise applications, boot/data disks, some databases |
| **Hyperdisk Balanced High Availability** | **hyperdisk-balanced-high-availability** | Block storage synchronously replicated across two zones in a region for HA workloads |
| **Hyperdisk Extreme** | **hyperdisk-extreme** | Very high-IOPS databases, high-performance configurations |
| **Hyperdisk Throughput** | **hyperdisk-throughput** | Sequential read/write, Hadoop, Spark, analytics, cold data disks |
| **Hyperdisk ML** | **hyperdisk-ml** | Very high concurrent model/data reads from many accelerator clients |

**Not every VM family supports every Hyperdisk type**, and limits on disk size, volume count, throughput, and IOPS also vary. Therefore, disk selection must align with **machine type, zone, and actual I/O requirements**.

For example, for a workload needing **20,000 IOPS but storing only 100 GiB of data**: you can consider **Hyperdisk Balanced** if supported by the machine series, rather than provisioning a large Persistent Disk solely to obtain more IOPS. Compare the **total cost of capacity + performance** and run benchmarks before deciding.

#### Multi-writer Does Not Mean File Share

Some Hyperdisk types support **READ_WRITE_MANY** or **READ_ONLY_MANY** depending on disk type and conditions. This only allows **attaching one block device to multiple VMs** in a supported mode:

- If two VMs mount a traditional **ext4/XFS** filesystem and write concurrently without a clustered filesystem/coordination, data **can become corrupted**.
- Multi-writer block storage requires a **cluster-aware filesystem/application fencing**, or usage as a certified database cluster.
- If the goal is simply **multiple VMs sharing a directory**, **Filestore/NFS** is usually more suitable and safer than building shared block storage yourself.

### 3.3. Local SSD: Ephemeral Block Storage, Not a Replacement for Durable Disks

**Local SSD** is attached to the physical host, offering low latency and high IOPS/throughput for many workloads. In return, data can be lost when the host/VM is stopped or encounters an unrecoverable event. Never use Local SSD as the sole copy of critical data.

Suitable for:

- **Caches, temporary sort/shuffle, scratch space**, intermediate files.
- Data that can be **reconstructed** from Cloud Storage, a database, or another source of truth.
- HPC/ML jobs requiring fast I/O within the worker lifecycle.

Not suitable for **sole backups**, standalone databases without replication/checkpointing, or data that must persist when the VM is deleted.

### 3.4. Zonal, Regional Disks, and Resilience

**Zonal Persistent Disk/Hyperdisk** stores data within the scope of a zone depending on the product type. **Regional Persistent Disk** and **Hyperdisk Balanced High Availability** are options that synchronously replicate data between two zones within the same region according to the product mechanism.

**Regional replication does not equal backup**:

- Having two replicas reduces the risk of **losing an entire zone**, but accidental file deletion, ransomware encryption, or writing corrupted data can be replicated as well.
- **Disk snapshots/backups** address recovery from logical errors when policies and retention are properly designed.
- **SLO/RTO/RPO** also depend on VM attach/failover capability, database consistency, DNS/IP, runbooks, and testing.

## 4. File Storage: When Multiple Compute Clients Need a Shared Directory Tree

### 4.1. Filestore: Managed NFS

**Filestore** is a managed network-attached storage (NAS) service that allows eligible VMs and GKE workloads to mount **NFS file shares**. Most applications treat the share like a directory and perform standard file read/write operations.

Current options:

| Filestore tier | Availability scope | Typical workload | Features/limits to note |
|---|---|---|---|
| **Zonal** | Per zone | Local HPC, high-performance shared files | Data exposed to zonal risk; backups/snapshots/replication available under conditions |
| **Regional** | Survives zone failure within region by design | Multi-zone services, enterprise apps needing HA | Cost and capacity/performance limits vary by tier |
| **Multishares for GKE (Enterprise)** | Per the product's regional mechanism | Multiple GKE PVCs/namespaces needing file shares | GKE-specific features and provisioner |
| **Legacy Basic HDD/SSD** | Zonal | Older applications requiring compatibility | NFSv3, different capacity/performance from newer tiers |

**Protocols:** Filestore **zonal/regional** supports **NFSv3 and NFSv4.1** depending on tier conditions, while legacy tiers may support only NFSv3. Do not assume every instance supports SMB or every NFS version.

Filestore is **a file share server with an IP address in a VPC**, so it requires proper routes/peering/network connectivity, firewall rules, and NFS client configuration. **It does not have a public HTTPS object URL** like Cloud Storage.

### 4.2. How Does Filestore Differ from Multi-Writer Block Storage?

Filestore's NFS server manages the file namespace and NFS semantics. Clients can mount the same export concurrently with appropriate permission and locking rules. Two VMs do not need to write raw blocks directly as with a multi-writer shared disk.

**However, NFS still has concurrency challenges:** two applications writing concurrently to the **same file** must design locking, write ordering, atomic renames, and flush/fsync according to the semantics of the NFS version in use. A shared filesystem does not automatically synchronize business logic.

### 4.3. Google Cloud Managed Lustre: Purpose-Built Parallel File System

**Managed Lustre** is a managed **parallel filesystem** aimed at **AI training, HPC, media, and very large-scale data analytics** requiring high throughput across many clients. It provides a POSIX interface, integrates with Compute Engine/GKE, and supports data movement to/from Cloud Storage according to product features.

It should only be chosen when the workload genuinely requires **parallel I/O** and there is already a plan for managing data staging, POSIX metadata, pricing, client count, and Lustre ecosystem compatibility. It is not a default replacement for Filestore in small web applications.

### 4.4. Google Cloud NetApp Volumes: NFS/SMB for Enterprise and Hybrid

**Google Cloud NetApp Volumes** supports file-based enterprise workloads with **NFSv3/v4.1/v4.2** and **SMB**, as well as block protocol options such as **iSCSI/NVMe/TCP** within supported features. It fits when an organization migrates existing applications from on-prem NAS, requires SMB for Windows, or needs NetApp data management capabilities.

Key differences:

- **Filestore:** usually the direct managed NFS option on Google Cloud for VMs/GKE.
- **NetApp Volumes:** consider when **SMB**, enterprise NAS features, hybrid migration, or NetApp service levels are required.
- **Managed Lustre:** optimized for **parallel POSIX filesystem** at HPC/AI scale.

Choose based on **protocol, tier, available regions, performance, licensing/pricing, recovery capabilities, and management model**; do not look at the service name alone.

## 5. Object Storage: Cloud Storage, Buckets, and Object Generations

### 5.1. What Is Cloud Storage?

**Cloud Storage** stores objects in **buckets**. Clients can read/write via **Cloud Storage JSON/XML APIs**, SDKs, Google Cloud CLI, or the Console UI. Objects have names, metadata, content types, generation/metageneration numbers, and lifecycle control attributes.

An illustrative path:

~~~text
gs://shop-product-media/images/2026/sku-1001.jpg
  bucket: shop-product-media
  object: images/2026/sku-1001.jpg
~~~

The **/** character is normally part of the object name for prefix-based organization and does not inherently create a POSIX directory. Cloud Storage also supports **hierarchical namespace** for appropriately configured buckets; even so, the **object API still differs from block/NFS filesystems**.

### 5.2. Storage Classes and Access Patterns

| Storage class | Suggested access frequency | Minimum storage duration / retrieval costs |
|---|---|---|
| **Standard** | Hot data, web images, actively served videos, frequently used artifacts | No minimum duration; account for operations/egress |
| **Nearline** | Infrequently accessed data, e.g., roughly monthly | 30-day minimum; retrieval charges apply |
| **Coldline** | Very infrequently accessed data, e.g., roughly quarterly | 90-day minimum; retrieval charges apply |
| **Archive** | Long-term retention, rare restores | 365-day minimum; retrieval charges apply |
| **Rapid** | Low-latency use cases under an eligible **Rapid Bucket** architecture | Applies only under supported Rapid Bucket models and conditions |

**Do not conclude that Archive requires waiting hours to read:** Cloud Storage Archive still provides online access via API; the factors to weigh are **retrieval pricing, storage duration, and product characteristics**.

Depending on requirements, you can use:

- **Object Lifecycle Management:** transitions storage classes or deletes objects by age or rules.
- **Autoclass:** automatically manages storage classes according to bucket policy when appropriate.
- **Object Versioning / soft delete:** supports recovery from deletions/overwrites, with additional retention costs.
- **Retention policy, bucket lock, object holds:** serves data retention or compliance requirements.
- **Signed URLs:** grants time-limited access to external users when the use case warrants it.

### 5.3. Cloud Storage Consistency

Cloud Storage provides **strong global consistency** for object create/read/list/delete and metadata operations per documentation; a new object can be read immediately after a successful upload. This is **not** a reason to treat Cloud Storage as a POSIX filesystem:

- **Strong read-after-write** for objects does not imply **in-place block writes**, **POSIX locks**, or **atomic multi-file transactions**.
- Multiple clients writing to the same object name can overwrite each other depending on execution order. Use **generation preconditions** to prevent lost updates.
- **Public caching via CDN/browser** may cause users to see stale versions until TTL/cache policies allow a refresh, even though the origin object is strongly consistent.

For example, use the **ifGenerationMatch=0** precondition when creating an object for the first time to ensure an existing object is not overwritten.

### 5.4. Object Storage Is Not Only for Backups

Common use cases:

- **Static assets** served via backend bucket/Cloud CDN.
- **Data lakes** with BigQuery, Dataflow, Dataproc, and AI pipelines.
- **Backups and snapshot exports** via supported tools.
- **Event-driven processing** when new objects arrive, using appropriate Pub/Sub/Eventarc mechanisms.
- **Artifact distribution** across projects and CI/CD systems.
- **Document preservation** under retention/compliance rules.

If a workload needs to store many large files, perform sequential reads, access via SDKs, and distribute globally, Cloud Storage is usually a flexible choice. If a workload needs to modify individual 4 KiB blocks or lock files continuously, do not force object storage to do the job of block/NFS storage.

## 6. Cloud Storage FUSE: Is "Mounting a Bucket" File Storage?

**Cloud Storage FUSE** allows mounting a bucket as a directory on Linux (or supported environments) so applications can issue read/write calls by path. Underneath, FUSE still calls the **Cloud Storage object API**.

~~~text
Application reads /mnt/models/model.bin
   ↓ POSIX-like interface via FUSE
Cloud Storage FUSE
   ↓ GET/PUT/list object
gs://ml-models/model.bin
~~~

**Mandatory limitations to understand:**

- **Not fully POSIX compliant**, and not an NFS/CIFS backend.
- Does not fully support filesystem metadata and file locking/patching semantics.
- Modifying the middle of a file typically triggers a **re-upload of the object** rather than a block write; unsuitable for databases, git repositories with heavy metadata operations, or continuously edited filesystem workloads.
- Object API latency is higher than disk/NFS for many small random I/O operations.
- Access permissions are controlled via **Cloud Storage IAM**, not replaced by conventional POSIX chmod/chown.
- **Object Versioning** and certain operations have compatibility limits with FUSE; check documentation before combining them.

**Suitable cases:** reading large models/datasets via file paths, staged ML workloads, or temporary migrations where an application requires a file interface but actual I/O behavior fits object storage.

**Rule of thumb:** An interface that "looks like a directory" does not change the semantics and cost model of object storage.

## 7. Service Selection Decision Diagram

~~~mermaid
flowchart TD
    Q["What does the workload need to store?"] --> D{"Needs a block device or<br/>random in-place I/O?"}
    D -->|Yes| B{"Can data be lost/recreated?"}
    B -->|Yes| L["Local SSD<br/>cache/scratch"]
    B -->|No| H{"Does VM support Hyperdisk?"}
    H -->|Yes| HD["Appropriate Hyperdisk<br/>Balanced/Extreme/Throughput/ML/HA"]
    H -->|No| PD["Persistent Disk<br/>balanced/SSD/standard/..."]
    D -->|No| F{"Needs POSIX/NFS/SMB<br/>and shared file namespace?"}
    F -->|Yes| FF{"Type of file workload?"}
    FF -->|General NFS| FS["Filestore<br/>zonal/regional"]
    FF -->|SMB/enterprise NAS| NET["NetApp Volumes"]
    FF -->|HPC/AI parallel I/O| LU["Managed Lustre"]
    F -->|No| OBJ["Cloud Storage<br/>bucket + object APIs"]
    OBJ --> C["Choose location/class,<br/>IAM, retention, lifecycle"]
~~~

### 7.1. Five Steps Applicable to Any Project

1. **Understand I/O:** whole objects or random block reads/writes? Is file locking/rename mandatory? What are the request sizes and concurrency levels?
2. **Understand sharing:** single VM, multiple VMs, multiple pods, read-only, concurrent writes, or multiple services calling over HTTP?
3. **Understand data:** must it survive VM restarts, zone failovers, application errors, accidental deletion, or ransomware?
4. **Understand security/connectivity:** need private VPC/NFS ports, bucket IAM, CMEK, service accounts, retention policies?
5. **Measure performance and cost:** measure actual IOPS/throughput/latency, check machine/zone limits, and calculate total cost across provisioned capacity, network, snapshots, operations, and retrieval.

### 7.2. Typical Workload Matrix

| Workload | Initial choice | Why | Do not confuse with |
|---|---|---|---|
| Linux VM boot disk | Supported Persistent Disk or Hyperdisk | Guest OS requires a block device | Cannot boot Compute Engine directly from a Cloud Storage object |
| Self-managed PostgreSQL/MySQL on VM | Appropriate Hyperdisk Balanced/Extreme or pd-ssd | Random IOPS, fsync, real file system | Do not use Cloud Storage FUSE as a database data directory |
| Shared folder across multiple VMs | Filestore NFS | Shared namespace, file-level operations | Multi-writer disks do not automatically provide file locking |
| Legacy Windows app requiring SMB | NetApp Volumes or appropriate managed SMB | SMB protocol and workload ACLs | Filestore NFS does not automatically become SMB |
| Large-scale parallel AI/HPC training | Managed Lustre or appropriate specialized system | Parallel POSIX I/O | Small Filestore tiers do not automatically achieve HPC throughput |
| Temporary cache on GPU VM | Local SSD | Fast, data can be recreated | Do not keep the sole checkpoint on Local SSD |
| Product images and media | Cloud Storage Standard + CDN as needed | Object APIs, scale, metadata, caching | Do not use a single VM's Persistent Disk as a shared media server |
| Long-term backups | Cloud Storage by class/retention, appropriate backup product | Data protection and lifecycle | Object storage does not automatically create consistent backups for an actively writing database |
| Multiple GKE pods needing concurrent file read/write | Filestore CSI or NetApp/Lustre per workload | File share with appropriate ReadWriteMany | An RWO block PVC does not mean RWX |
| Analytics data lake | Cloud Storage | Object-oriented data, analytics ecosystem | No need for NFS for most batch object processing |

## 8. Performance: Reading IOPS, Throughput, and Latency Properly

### 8.1. IOPS

**IOPS (I/O operations per second)** measures the number of read/write operations per second. OLTP databases processing many small pages are typically **sensitive to IOPS and latency**.

An illustrative example:

~~~text
10,000 IOPS × 4 KiB / operation
≈ 39 MiB/s of data, yet 10,000 requests/second.
~~~

You cannot choose a disk by looking only at MiB/s; 10,000 requests of 4 KiB behave very differently from a few multi-MiB requests.

### 8.2. Throughput

**Throughput** is the amount of data moving through the system per second (MiB/s, GiB/s). Video processing, ETL, Hadoop, and sequential backups are usually more sensitive to throughput than IOPS.

### 8.3. Latency

**Latency** is the time a single operation takes to complete; measure **p50/p95/p99**, not just the average. For synchronous APIs, a slow storage call can be noticed immediately by users.

| Type | Performance limits to verify |
|---|---|
| **Persistent Disk** | Volume size, disk type, vCPU count, machine limits, aggregate I/O, network egress |
| **Hyperdisk** | Provisioned IOPS/throughput, disk type, machine caps, and volume count |
| **Local SSD** | Machine configuration, parallel I/O, lifecycle |
| **Filestore** | Tier, purchased/provisioned capacity and performance, NFS clients, nconnect, network |
| **Managed Lustre** | Client count, striping, data distribution, metadata performance, network |
| **Cloud Storage** | Request size, client concurrency, object naming, API throughput, retries, location, and network |

### 8.4. Actual Performance Is Often the "Minimum of Multiple Ceilings"

For Persistent Disk and Hyperdisk, actual throughput can be capped by either the **disk cap or the instance cap**. Provisioning **100,000 IOPS** on a disk does not mean a small VM can execute 100,000 IOPS. You must size **both the disk and the machine** appropriately.

For Filestore, NFS client CPU, network, mount options, and number of connections can become bottlenecks. For Cloud Storage, many small objects/single-threaded requests and round-trip latency can dominate. **Benchmark with the real application pattern** instead of treating a marketing number as an SLO guarantee.

## 9. Sharing and Consistency: Differences That Can Corrupt Data

### 9.1. A Disk Is Not Inherently a File Share

A block volume is normally attached read/write to a single VM or node according to its access mode. **Multi-writer Hyperdisks** require a clustered FS/app logic; **ReadWriteMany** in Kubernetes is a requirement on volume access semantics, not a toggle automatically enabled on every PD/Hyperdisk.

### 9.2. NFS Shares a Namespace but Does Not Replace a Transactional Database

Multiple Filestore clients see the same directory. However:

- File locks and cache coherence depend on the NFS version and application protocol.
- Two writers must coordinate when editing the same file.
- A regional NFS server offers better HA than a zonal share per product features, but still requires sufficiently available network/clients.

Do not migrate a self-managed database from block storage to NFS just so multiple VMs can mount the same data directory: the database may not support that multi-host writer model.

### 9.3. Object Strong Consistency Does Not Mean Cross-Object Transactions

Once created successfully, a Cloud Storage object is strongly consistent for reads and lists. However, a workflow that creates **orders/100.json** and then creates **orders/index.json** consists of **two separate operations**, with no atomic transaction spanning both. If transactional integrity is required, use an appropriate database and design idempotent events/manifests.

**Generation preconditions** help resolve concurrent writers at the object level; **object versioning** helps track/restore versions but does not guarantee correct application update logic.

## 10. Durability, HA, Backup, Replication, and Compliance Requirements

### 10.1. Do Not Confuse Durability, Availability, and Recoverability

| Term | Question | Example |
|---|---|---|
| **Durability** | What is the probability data is preserved during infrastructure failures? | Redundancy of disk or object storage |
| **Availability** | Can the workload still access data when a component/zone fails? | Regional Filestore/Regional PD, multi-zone design |
| **Recoverability** | Can data be restored after accidental deletion, corruption, or ransomware? | Snapshots, backups, versioning, retention |
| **RPO** | How much data loss in time is tolerable? | 0 minutes, 15 minutes, 24 hours |
| **RTO** | How long can service downtime last during recovery? | 5 minutes, 1 hour |

### 10.2. Block storage

**Snapshots** can back up disks; for actively writing databases, you must consider **application-consistent** (flush/quiesce or backup-specific) versus crash-consistent snapshots. A VM disk snapshot does not necessarily capture RAM state, multi-disk transaction logic, or data outside that disk.

**Regionally replicated** disks support availability during a zone outage, but still require a **failover procedure** and independent backups.

### 10.3. File storage

Filestore offers **backups/snapshots** depending on tier and features; restoring can take substantial time depending on capacity. For NFS shares with multiple writers, determine point-in-time consistency requirements and whether the application needs quiescing. **Regional Filestore** mitigates zone outage risk but does not replace protection against accidental deletion.

### 10.4. Object storage

Choose **bucket location** based on data and requirements: region, dual-region, multi-region, or supported specialized configurations. These options involve trade-offs in latency, data residency, availability, and cost.

Configure appropriately:

- **Soft delete** and/or **Object Versioning** to support recovery from deletion/overwrites.
- **Lifecycle** rules to automatically transition storage classes or delete data per policy.
- **Retention policy/holds** when legal compliance is required.
- **CMEK** when organization-managed keys are required, along with key recovery capabilities.
- **Replication/data placement** per product features and RPO/RTO requirements; do not assume all classes/regions share the same SLA.

**Caution:** data location replication does not protect against an authorized principal deleting objects, unless retention mechanisms, soft delete/versioning, or restricted permissions protect them.

## 11. Security and Networking for Each Storage Type

| Topic | Block | File | Object |
|---|---|---|---|
| **GCP IAM** | Permissions to create, attach, snapshot, manage disks | Permissions to create/administer instances/shares; IAM does not automatically replace NFS file permissions | Bucket/object IAM and signed URLs where appropriate |
| **Data-plane permissions** | OS user/group, filesystem permissions, encryption | NFS export options, UID/GID, file ACLs/locking, network restrictions | Cloud Storage IAM, conditional access, object preconditions |
| **Network path** | Block volume via Compute Engine infrastructure; guest sees a device | VPC peering/Shared VPC/routes + NFS/SMB ports | Google APIs, Private Google Access/PSC for Google APIs depending on architecture |
| **Encryption** | Default encryption at rest/in transit; CMEK depending on type | Managed service encryption, CMEK/features depending on tier | Encryption at rest/in transit; CMEK if selected |
| **Common exposure** | Attaching the wrong disk or overly broad permissions | Broad NFS share UID/GID, firewall, or routes | Public bucket IAM, long-lived signed URLs, leaked keys |
| **Monitoring** | Compute audit logs, disk metrics, OS logs | Filestore audit/monitoring, NFS errors | Cloud Storage audit logs, request metrics, object access |

### 11.1. Practical Least Privilege

- Separate the **application service account** from storage administrator accounts.
- For private buckets, use **Uniform bucket-level access** when the permission model fits; restrict public access and consider **Public Access Prevention**.
- For Filestore, configure network export options and firewall rules for authorized clients. **NFSv3 with AUTH_SYS/UID/GID is not per-file IAM**; understand the client trust boundary.
- For disks, **compute.disks.use**/attachDisk permissions together with guest-OS permissions determine who can access data; CMEK encryption requires IAM policies on the keys and proper rotation/revocation operations.
- Never embed credentials in images, scripts, or repositories; on VMs/GKE/Cloud Run, use appropriate **service accounts/workload identity**.

### 11.2. Data Residency

Storage types differ in how you choose **zone, region, dual-region, or multi-region**. If business rules require data to remain in a specific country/region, decisions must follow **service terms, actual storage location, and replication/backup flows**. Do not use a multi-region bucket as a substitute for a single-region residency requirement.

## 12. Hands-on A: Creating and Mounting a Persistent Disk on Compute Engine

**Goal:** a Linux VM in **asia-southeast1-b** needs a 100 GiB **pd-balanced** disk to store data files. IDs in the example are hypothetical; creating resources incurs charges.

| Variable | Example value |
|---|---|
| Project | shop-dev-001 |
| Zone | asia-southeast1-b |
| VM | app-vm-01 |
| Disk name | app-data |
| Disk size/type | 100 GiB / pd-balanced |

### 12.1. Check Before Creating

~~~bash
gcloud compute instances describe app-vm-01 \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b

gcloud compute disks list --project=shop-dev-001 \
  --filter="zone:(asia-southeast1-b)"
~~~

Verify whether the disk name already exists and where disks are attached. Do not run format commands on a disk that already contains data.

### 12.2. Create the Disk

~~~bash
gcloud compute disks create app-data \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --type=pd-balanced \
  --size=100GB
~~~

### 12.3. Attach to a VM in the Same Zone

~~~bash
gcloud compute instances attach-disk app-vm-01 \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b \
  --disk=app-data \
  --device-name=app-data

gcloud compute disks describe app-data \
  --project=shop-dev-001 \
  --zone=asia-southeast1-b
~~~

**A successful attach does not mean the guest OS can use it yet.** A new disk may not be formatted or mounted.

### 12.4. Format and Mount Inside the VM

**Data loss warning:** the **mkfs.ext4** command overwrites any existing filesystem. **Use it only when you are certain the disk is brand new, contains no data**, and the device is correctly identified.

~~~bash
# Run inside the VM, not on your laptop
lsblk -f
ls -l /dev/disk/by-id/google-app-data

# Only on an EMPTY disk, confirm the right device
sudo mkfs.ext4 -m 0 -F /dev/disk/by-id/google-app-data

sudo mkdir -p /mnt/app-data
sudo mount -o discard,defaults /dev/disk/by-id/google-app-data /mnt/app-data

df -h /mnt/app-data
~~~

To mount automatically after reboot, prefer using the **filesystem UUID** in **/etc/fstab** after verifying the exact UUID, mount options, and behavior when the disk is unavailable; use **nofail** if the business allows the VM to boot even when the disk is absent. Do not edit fstab automatically without a recovery procedure, as misconfiguration can prevent the VM from booting.

### 12.5. Key Takeaway

A block disk provides a **device**; you must manage the **filesystem, permissions, mounting, backups, filesystem resizing, and consistency across multiple writers**. This is a different set of responsibilities from uploading files to Cloud Storage.

## 13. Hands-on B: Filestore File Share for Two VMs

**Goal:** two Linux VMs in the same VPC need to share the **/mnt/shared** directory to exchange documents. Choose **Filestore Regional** for a scenario requiring HA within a region; verify tier/quota/pricing and supported regions before creating.

Example:

| Variable | Example value |
|---|---|
| Project | shop-dev-001 |
| Region | asia-southeast1 |
| VPC | vpc-app |
| Filestore instance | fs-shared |
| NFS share | shared |
| Capacity | 1 TB |

### 13.1. Create the Filestore Instance

~~~bash
gcloud filestore instances create fs-shared \
  --project=shop-dev-001 \
  --region=asia-southeast1 \
  --tier=REGIONAL \
  --file-share=name="shared",capacity=1TB \
  --network=name="vpc-app"
~~~

This command incurs **provisioned capacity charges** as soon as the instance is created. Regions/tiers may have separate quotas and organizational policies. You must check the Cloud Filestore API, instance management permissions, and reserved IP ranges in the VPC to avoid conflicts.

### 13.2. View IP and Share Name

~~~bash
gcloud filestore instances describe fs-shared \
  --project=shop-dev-001 \
  --region=asia-southeast1
~~~

Read **networks[].ipAddresses**, **fileShares[].name**, tier, and state. For example, suppose the resulting IP is **10.50.10.20**; substitute the actual IP. VMs must have routes/firewall rules reaching the Filestore IP address.

### 13.3. Mount from a Linux VM

~~~bash
# On the VM, e.g., Debian/Ubuntu
sudo apt-get update
sudo apt-get install -y nfs-common

sudo mkdir -p /mnt/shared
sudo mount -t nfs -o vers=3 10.50.10.20:/shared /mnt/shared

df -h /mnt/shared
mount | grep /mnt/shared
~~~

If both VMs need the share, run the mount command from the second VM (after setting up routes/firewall). Choose **NFSv3/v4.1** based on the Filestore tier and kernel/client compatibility; do not assume both VMs have equal write permissions if export/UID/GID/file permissions disallow it.

**After a reboot**, a manual mount is not automatically restored. Consider **/etc/fstab, _netdev, automount/autofs**, and verify behavior when the NFS server is unavailable. With GKE, prefer using the **Filestore CSI driver/PVC** rather than SSHing into nodes to edit fstab.

### 13.4. What Not to Do

- Do not try running **mkfs.ext4** against an NFS address.
- Do not treat a Filestore IP as a public DNS endpoint.
- Do not leave an NFS share open to an entire CIDR if only a few clients need access.
- Do not expect a snapshot of an NFS share with multiple active writers to be application-consistent without a quiescing plan.

## 14. Hands-on C: Cloud Storage Bucket for Product Images

**Goal:** store the image **sku-1001.jpg** and access it by object path; the bucket uses **Standard** class and uniform bucket-level access. Bucket names must be globally unique; the example below is a placeholder only.

### 14.1. Create the Bucket

~~~bash
gcloud storage buckets create gs://shop-media-REPLACE-UNIQUE \
  --project=shop-dev-001 \
  --location=asia-southeast1 \
  --default-storage-class=STANDARD \
  --uniform-bucket-level-access
~~~

Replace **REPLACE-UNIQUE** only with an approved name. Creating a bucket can incur costs when storing data, performing operations, or using network egress. Verify **public access prevention**, IAM, lifecycle, and required organizational policies.

### 14.2. Upload and Read Objects

~~~bash
gcloud storage cp ./sku-1001.jpg \
  gs://shop-media-REPLACE-UNIQUE/images/sku-1001.jpg

gcloud storage ls \
  gs://shop-media-REPLACE-UNIQUE/images/

gcloud storage cp \
  gs://shop-media-REPLACE-UNIQUE/images/sku-1001.jpg \
  ./sku-1001-downloaded.jpg
~~~

**No NFS mount or block formatting is needed**. Applications or pipelines interact via bucket/object APIs.

### 14.3. Java Cloud Storage Client Example with ADC

Assume the Java API has a service account granted appropriate object creation permissions on the bucket:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ProductPhotoStore {
    public static void uploadNew(String bucket, String objectName,
                                 Path localFile) throws Exception {
        Storage storage = StorageOptions.getDefaultInstance().getService();
        BlobId id = BlobId.of(bucket, objectName);
        BlobInfo blob = BlobInfo.newBuilder(id)
            .setContentType("image/jpeg")
            .build();
        byte[] bytes = Files.readAllBytes(localFile);
        storage.create(blob, bytes, Storage.BlobTargetOption.doesNotExist());
    }
}
~~~

This example uses **Application Default Credentials**; do not hardcode service account private keys. **doesNotExist()** uses a generation precondition to reduce the risk of overwriting when an object with the same name already exists. For large files in production, prefer **streaming/resumable uploads** instead of reading the entire object into RAM.

### 14.4. Protecting Content

Do not make a bucket public just to get an application working quickly. For public images, you can choose a **backend bucket + Cloud CDN** architecture with an appropriate bucket policy; for private documents, have the authenticated application serve content or issue time-limited **signed URLs**. Design lifecycle/versioning according to recovery needs and cost.

## 15. GKE, Cloud Run, and Cloud SQL: Choosing Storage by Compute Platform

### 15.1. GKE PersistentVolume/PersistentVolumeClaim

In GKE, applications declare a **PersistentVolumeClaim (PVC)** and the **Container Storage Interface (CSI)** driver can provision the corresponding storage.

| Need on GKE | Selection direction |
|---|---|
| A single pod/database instance needing a block filesystem | **Compute Engine PD/Hyperdisk CSI**, appropriate access mode |
| Multiple pods needing a shared NFS share with **ReadWriteMany** | **Filestore CSI** or a supported NFS solution |
| Datasets/training using object APIs | **Cloud Storage SDK** or GCS FUSE CSI under supported conditions |
| High-throughput parallel POSIX for HPC/AI | **Managed Lustre** if integration fits |

Example of a basic PVC using the **standard-rwo** StorageClass available in supported GKE environments:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-rwo
  resources:
    requests:
      storage: 50Gi
~~~

**ReadWriteOnce** does not mean any pod can read/write across different nodes. RWO typically restricts read/write attachment to a single node/volume; **ReadWriteMany** requires a storage driver that genuinely supports sharing. Check the storage class, provisioner, zone topology, reclaim policy, and backups before deploying a StatefulSet.

### 15.2. Cloud Run

Cloud Run is a managed container platform where instances can scale to 0 or be replaced. Do not treat a container's ephemeral filesystem as durable state storage. With Cloud Run:

- **Cloud Storage** is generally suitable for images/documents, artifacts, and durable data via SDK or supported mounts.
- **Filestore/NFS** can work with volume mounts and VPC connectivity supported by Cloud Run, but you must check product/region limits, performance, and cost.
- Transactional databases should use **Cloud SQL, AlloyDB, Spanner**, or an appropriate managed product rather than self-managing a container's filesystem.

### 15.3. Cloud SQL Does Not Require Users to Attach Persistent Disks

**Cloud SQL** is a managed database; users select size, HA, backups, maintenance, and storage settings through the service interface. You do not manually create a PD and attach it to a Cloud SQL instance as you would with Compute Engine.

Only when **self-managing a database on a VM** do you directly select PD/Hyperdisk, filesystem, mounting, replication, and backups at the machine layer.

## 16. Cost Optimization: Do Not Look Only at USD/GiB

### 16.1. Components to Include in Estimates

| Type | Primary cost | Commonly overlooked items |
|---|---|---|
| **Persistent Disk** | Provisioned GiB by disk type/zone | Regional replicas, snapshots, disks left behind after VM deletion |
| **Hyperdisk** | Capacity + provisioned IOPS/throughput depending on type | Over-provisioning beyond actual need, multi-writer architecture, snapshots |
| **Local SSD** | Attached capacity per machine pricing configuration | Cost of reconstructing data if the host fails |
| **Filestore** | Provisioned capacity/tier/performance | Unused capacity, backups, cross-region traffic, client VMs |
| **Managed Lustre** | File system capacity/performance, operations per service | Data import/export, staging, idle filesystems |
| **NetApp Volumes** | Service level, capacity, features | Snapshots/replication, networking, SMB/enterprise operations |
| **Cloud Storage** | Stored bytes × class/location | API operations, retrieval fees, early deletion, egress, versioning, soft delete, logging |

**Stopping a VM does not delete its disks**, nor does it stop all storage charges. For Filestore, billing may be based on **provisioned capacity** even when actual used data is small. For Cloud Storage, a cheaper class per stored byte may not save money if accessed frequently and incurring retrieval/early deletion charges.

### 16.2. TCO Thinking Example

A **2 TiB directory of images** does not need block-level edits, contains many objects, and is served via CDN. Using a VM + PD as a file server requires factoring in CPU/VM uptime, patching, backups, load balancing, egress, and HA. Cloud Storage can reduce operational overhead, though API calls and CDN egress must be accounted for.

Conversely, a **200 GiB database** executing thousands of small transactions per second will encounter unsuitable latency/semantics if using an object API. "Cheaper storage price for 200 GiB" is not a valid basis for choosing storage if the application fails to meet its SLO.

### 16.3. Optimization Process Without Breaking Performance

1. Measure **capacity, IOPS, throughput, latency, requests, and egress** over at least one typical load cycle.
2. Check zone/region availability and disk/file tier support.
3. Choose the **minimum tier that meets the SLO**, avoiding over-provisioning out of vague caution.
4. Design backups/lifecycle/retention before shrinking capacity or deleting data.
5. Cross-check Cloud Billing reports, budgets/alerts, workload metrics, and test results.
6. Review periodically as data/load grows, since today's right design may not be optimal a year from now.

## 17. Integrated Scenario: E-Commerce System with AI Processing

The enterprise **Phu An** operates:

- A Java API on a **Compute Engine regional managed instance group**.
- Self-managed PostgreSQL on a VM or considering Cloud SQL.
- Two workers needing a shared directory to generate PDF reports.
- Millions of product images, CSV exports, and backups.
- A GPU worker preprocessing images with many temporary files.
- Several services running on GKE and Cloud Run.

### 17.1. Reference Architecture

~~~mermaid
flowchart TB
    WEB["Web / mobile clients"] --> LB["Application Load Balancer"]
    LB --> API["Java API<br/>Compute Engine / GKE"]
    API --> DB["PostgreSQL VM<br/>Hyperdisk / PD<br/>or Cloud SQL"]
    API --> OBJ["Cloud Storage<br/>product images, exports"]
    WORK["PDF generation workers<br/>multiple VMs/pods"] --> NFS["Filestore Regional<br/>NFS shared directory"]
    GPU["GPU processing worker"] --> SSD["Local SSD<br/>scratch/cache"]
    GPU --> OBJ
    NFS --> OBJ
    OBJ --> CDN["Cloud CDN if appropriate"]
~~~

| Component | Choice | Rationale and safeguards |
|---|---|---|
| API boot disks | PD Balanced/Hyperdisk Balanced | Block device, sized to VM and actual I/O |
| Self-managed PostgreSQL | Hyperdisk Balanced/Extreme or PD SSD | Random I/O, filesystem, consistent backups, replication |
| Managed PostgreSQL | Cloud SQL | DB service manages storage/HA separately |
| PDF shared workspace | Filestore Regional | Multiple workers see the same file tree; account for locking/HA |
| Product images | Cloud Storage Standard | Object APIs, metadata, CDN, IAM |
| Datasets/archives | Cloud Storage by class/lifecycle | Scalability, retention, retrieval costs |
| GPU temporary files | Local SSD | Ephemeral recreatable data; checkpoint to Cloud Storage |
| Large-scale parallel ML training | Managed Lustre if workload is large enough | Throughput/POSIX, benchmark first |

### 17.2. Why Not Choose One Service for Everything?

**Assumption A: use Cloud Storage FUSE for PostgreSQL.** High risk around POSIX semantics, random writes/patching, and latency; not a suitable database backend.

**Assumption B: use one PD mounted rw across multiple web VMs.** Standard filesystems do not safely handle concurrent writes from multiple hosts; requires a shared file solution or cluster-aware system.

**Assumption C: use Filestore for all public images.** Can work if the application serves HTTP itself, but increases operational overhead for the file serving layer and misses native Cloud Storage/CDN, metadata, and lifecycle capabilities.

**Assumption D: keep all important files on Local SSD.** Risk of data loss during a host event; requires durable storage/replication and checkpointing.

### 17.3. SLOs and Testing for Each Layer

| Test | Expectation |
|---|---|
| PostgreSQL running fsync/random write tests | IOPS/p99 latency within thresholds; backup restore succeeds |
| VM/zone failure | Failover plan exists for disks, Filestore, or DB; RTO/RPO met |
| Two workers generating PDFs on the same share | No mutual file overwrites; locking/atomic rename works properly |
| Cloud Storage new object upload | GET/list succeeds after write; IAM is accurate; no unintended public access |
| Concurrent clients modifying an object | Generation precondition prevents lost updates |
| GPU worker stopped | Durable checkpoints exist; Local SSD data can be rebuilt |
| Cloud CDN cached images | Cache invalidation/versioned URL strategy in place |
| Peak traffic month | Billing across storage, operations, egress, and metrics provides sufficient visibility |

## 18. Common Mistakes

**"GCS FUSE turns Cloud Storage into a POSIX NFS drive."** False. FUSE is an adapter over the object API with limitations in POSIX compliance, patching, locking, latency, and metadata.

**"Persistent Disk is a hard drive on the physical host, so deleting the VM loses the data."** Fundamentally false: PD is network-attached block storage independent of the host; however, the **auto-delete deletion rule** can cause the disk to be deleted alongside the VM.

**"If block storage supports multi-writer, anyone can mount ext4 and write to it."** False. It requires a clustered filesystem or specialized application coordination; otherwise data corruption can occur.

**"Regional disks replace backups."** False. Replication protects against zone failures, not against accidental deletion or logical data corruption.

**"File storage is always accessible to every VM without network configuration."** False. Filestore requires proper VPC routes/ports/firewalls/export permissions and matching UID/GIDs.

**"Object storage has eventual consistency, so newly uploaded objects cannot be read immediately."** Incorrect for Cloud Storage operations guaranteed to have **strong consistency**; distinguish this from public caching and cross-object transactions.

**"Archive storage means you cannot read data immediately."** Not quite; Cloud Storage Archive is an online storage class with different retrieval fees and minimum storage duration from Standard.

**"The Cloud Run filesystem is like a VM's Persistent Disk."** False. A container's filesystem is not inherently durable; use an appropriate external storage service.

**"Increasing Hyperdisk IOPS will make the application twice as fast."** Not necessarily. VM caps, CPU, queue depth, database locks, networking, and I/O size can bottleneck performance.

**"Stopping a VM stops charges for all disks/Filestore/buckets."** False. Retained disks, shares, and objects typically continue to incur their respective charges.

## 19. Practice Exercises and Suggested Answers

### Exercise A — Service Selection

For each requirement, choose the appropriate service group and explain why:

1. A VM needs its own disk to install Ubuntu and PostgreSQL.
2. Three Linux VMs processing images need a shared folder to read/write together.
3. 10 million product images need web serving, metadata, and lifecycle management.
4. A GPU job needs 2 TiB of recreatable scratch data.
5. A legacy Windows file server requires SMB.
6. Large-scale AI training requires parallel POSIX I/O.

**Suggested answers:** (1) Hyperdisk/Persistent Disk; (2) Filestore; (3) Cloud Storage and CDN if appropriate; (4) Local SSD per supported configuration, with durable checkpoints; (5) NetApp Volumes/SMB solution; (6) Managed Lustre if scale, cost, and integration fit.

### Exercise B — Distinguishing Access Modes

A StatefulSet on GKE uses a **ReadWriteOnce** PVC attached to node A. The development team wants multiple pods across multiple nodes to edit a file on this volume concurrently.

**Question:** Can they simply point all pods to mount the same volume? What solution should be used?

**Answer:** You cannot assume RWX is supported from RWO. If a shared file namespace across multiple nodes is needed, choose Filestore CSI/NFS or an appropriate product supporting ReadWriteMany. Multi-writer block is a separate problem requiring a clustered filesystem.

### Exercise C — Evaluating Technical Value

A workload has:

- 200 GiB of data.
- 20,000 random read/write IOPS, 4 KiB block size.
- Low p99 latency requirement.
- The VM supports Hyperdisk, but the current PD type delivers low performance at 200 GiB.

Compare:

- Increasing Persistent Disk size to gain more performance.
- Switching to Hyperdisk Balanced and provisioning appropriate IOPS/throughput.

**Guidance:** Evaluate **disk and VM IOPS limits**, actual p99 latency, capacity + IOPS/throughput pricing, migration feasibility, and downtime/rollback. Do not optimize solely on GiB cost.

### Exercise D — Cloud Storage Concurrency

Two workers attempt to upload **reports/final.json** at the same time. Both use the same object name but contain different content.

**Question:** Does strong consistency prevent lost updates? How do you avoid unintended overwrites?

**Answer:** No; strong consistency refers to visibility after a successful operation. Use **generation preconditions** such as **doesNotExist/ifGenerationMatch**, versioned object names, manifests, or transactional coordination in a database.

### Exercise E — Designing Backup and DR

An application has a 500 GiB database, a 2 TiB NFS directory, and a 20 TiB Cloud Storage bucket. Policy requires RPO=15 minutes and RTO=2 hours for critical data.

Describe:

1. Which components need replication/HA.
2. Backups/snapshots/versioning/retention for each group.
3. How to perform a restore drill and measure RTO/RPO.
4. How to protect against accidental deletion by broadly privileged accounts.
5. Additional costs from snapshots, versioning, replication, egress, and aged data.

**Hint:** A 15-minute RPO cannot be achieved solely via once-daily snapshots. The database may require replication/WAL, while Filestore and buckets need appropriate backup/versioning schedules. Recoverability is only proven when a restore test succeeds.

### Exercise F — Troubleshooting Operational Errors

The team encounters:

- **A VM has a new disk attached, but `/mnt/app-data` is missing**.
- **Filestore mount timeout**.
- **Cloud Storage upload returns 403**.
- **GCS FUSE edits to large files are very slow**.

**Troubleshooting approach:**

| Symptom | First checks |
|---|---|
| Disk attached but not mounted | Does the guest OS see the device? Was the **right disk** formatted and mounted? Filesystem UUID/fstab? |
| Filestore timeout | IP/export path, NFS version, VPC routes, firewall, reserved range, instance state |
| Cloud Storage 403 | IAM principal, bucket access level, uniform access, org policy/PAP, service account |
| Slow GCS FUSE patches | Is it actually rewriting the whole object? Does the app require POSIX? Should it switch to block/NFS or SDK? |

## 20. Summary and References

**Seven Key Principles:**

1. **Block** provides a storage device for the OS and applications, suited for boot/databases/in-place writes; choose **Persistent Disk/Hyperdisk** based on VM, IOPS, and durability.
2. **Local SSD** is for high-performance ephemeral data, not the sole copy of critical data.
3. **File storage** provides a shared namespace and semantics over NFS/SMB/parallel POSIX; choose **Filestore**, **NetApp Volumes**, or **Managed Lustre** based on protocol and workload.
4. **Cloud Storage** stores objects via APIs, provides strong consistency for supported object operations, and manages class/location/lifecycle/IAM as needed.
5. **Cloud Storage FUSE** does not turn a bucket into a POSIX filesystem; do not use it as the data directory of a random-write database.
6. **High availability, durability, and backups are three distinct requirements**. Regional replication does not replace snapshots, retention, or restore testing.
7. Sound decisions evaluate **I/O patterns, concurrency, permissions, connectivity, RPO/RTO, total cost, and SLOs**, rather than simply choosing the tier with the lowest storage price.

**Official Google Cloud Documentation:**

1. [Choose a disk type — Compute Engine](https://docs.cloud.google.com/compute/docs/disks) — choosing Persistent Disk/Hyperdisk/Local SSD.
2. [Persistent Disk overview](https://docs.cloud.google.com/compute/docs/disks/persistent-disks) — disk types, durability, and semantics.
3. [Google Cloud Hyperdisk overview](https://docs.cloud.google.com/compute/docs/disks/hyperdisks) — Balanced/HA/Extreme/Throughput/ML, limits, and performance.
4. [Add a Persistent Disk volume](https://docs.cloud.google.com/compute/docs/disks/add-persistent-disk) — gcloud create, attach, guest filesystem.
5. [Filestore service tiers](https://docs.cloud.google.com/filestore/docs/service-tiers) — zonal, regional, multishares, legacy.
6. [Create a Filestore instance](https://docs.cloud.google.com/filestore/docs/creating-instances) — network, share, and CLI.
7. [Mount Filestore file shares on Compute Engine](https://docs.cloud.google.com/filestore/docs/mounting-fileshares) — NFS mount, network, and fstab.
8. [Google Cloud Managed Lustre overview](https://docs.cloud.google.com/managed-lustre/docs/overview) — parallel POSIX filesystem for AI/HPC.
9. [Google Cloud NetApp Volumes overview](https://docs.cloud.google.com/netapp/volumes/docs/discover/overview) — NFS/SMB and enterprise workloads.
10. [Cloud Storage storage classes](https://docs.cloud.google.com/storage/docs/storage-classes) — Standard/Nearline/Coldline/Archive/Rapid.
11. [Cloud Storage consistency](https://docs.cloud.google.com/storage/docs/consistency) — object read/list consistency.
12. [Cloud Storage FUSE overview](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/overview) — semantics and limitations compared to POSIX.
13. [GKE persistent volumes](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/persistent-volumes) — CSI provisioners, PV/PVC, and access modes.
