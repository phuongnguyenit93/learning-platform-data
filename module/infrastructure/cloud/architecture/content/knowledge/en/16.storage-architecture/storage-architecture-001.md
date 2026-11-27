# Choosing Object, Block, and File Storage by Access Pattern

## 1. Start from How the Application Uses Data

A cloud application may store user images, videos, documents, logs, backups, configuration files, transaction data, and server filesystems. These datasets have very different access patterns. Some data is read as a complete object through an API; some requires a low-latency block device so a database management system can manage data pages itself; and some requires multiple machines to see a single directory tree and perform file operations following POSIX conventions.

The three common storage types are:

- **Object storage:** stores data as objects along with metadata, accessed via an API or compatible protocol. Suitable for images, videos, documents, logs, backups, data lakes, and static content.
- **Block storage:** provides block devices/volumes for the operating system or application to format a filesystem or manage blocks directly. Suitable for VM disks, databases, container volumes, and applications requiring random I/O.
- **File storage:** provides a directory/file namespace with open/read/write/rename/lock operations over a filesystem protocol. Suitable for shared directories, home directories, CMS content, and software that requires filesystem semantics.

No single type is always the fastest, cheapest, or most reliable. The choice depends on **access pattern, data size, number of concurrent clients, latency, IOPS, throughput, durability, consistency, shareability, data lifecycle, security, recovery, and total cost of ownership**.

In the **CLOUD_ARCHITECTURE** module, storage decisions are part of data and cloud infrastructure design. You must start from business requirements and actual workloads, then make trade-offs across performance, reliability, security, scalability, cost, and operational capability following a Well-Architected mindset.

After this lesson, you can:

- Distinguish object, block, and file storage by data model and access interface.
- Translate access patterns into measurable requirements for IOPS, throughput, latency, concurrency, and capacity.
- Choose the right storage type for databases, VMs, containers, media, shared files, and backups.
- Evaluate consistency, durability, availability, replication, snapshots, and backups.
- Design security, encryption, IAM, network access, lifecycle, and data protection.
- Estimate total cost and plan testing before putting storage into production.

## 2. Three Storage Models Viewed from the Application

~~~mermaid
flowchart TB
    App["Application / workload"]
    App --> API["API / SDK"]
    App --> Device["Block device / volume"]
    App --> FS["Filesystem interface"]
    API --> Obj["Object storage"]
    Device --> Block["Block storage"]
    FS --> File["File storage"]
    Obj --> OData["Object + metadata + key"]
    Block --> BData["Blocks + volume"]
    File --> FData["Directories + files + permissions"]
~~~

| Characteristic | Object storage | Block storage | File storage |
| --- | --- | --- | --- |
| Unit of data | Object with key, payload, and metadata | Block address within a volume | File and directory within a namespace |
| Primary interface | HTTP API/SDK, REST, or compatible protocol | Block device via protocol/driver | NFS, SMB, or filesystem protocol |
| Access | Typically by object/key; read/write objects via API | Random or sequential block reads/writes | File, directory, metadata, and lock operations |
| Sharing | Multiple clients access the same object via API and policy | Usually attached to volumes subject to product attach/multi-attach limits | Multiple clients can mount the same file system |
| Scale | Usually scales capacity very large per service | By volume, provisioned size, IOPS, and throughput | By filesystem, capacity, throughput, and client count |
| Best suited for | Media, backups, archives, data lakes | OS disks, database volumes, transactional workloads | Shared directories, home folders, enterprise apps |
| Things to watch out for | No native POSIX filesystem; updating an object is not equivalent to writing blocks | Requires managing filesystem, mounts, snapshots, and attachments | Metadata operations, file locking, permissions, and network latency |

Some products offer multiple interfaces or hybrid features. For example, object storage may provide a mount gateway or file interface; block volumes may support multi-attach in certain modes; file services may offer different performance tiers. When evaluating, understand the **semantics of the specific feature**, rather than inferring from the product name.

## 3. Analyze the Access Pattern Before Choosing

Storage should be chosen based on how the application reads, writes, updates, and shares data. Answer these questions:

| Question | Implication for the choice |
| --- | --- |
| Is data read by key, block offset, or file path? | Determines object, block, or file interface |
| Are whole objects read/written or are small regions updated frequently? | Object fits complete content; block fits random I/O; file fits file operations |
| What is the size of each data unit and total capacity? | Small images, large files, database volumes, and billions of objects behave differently in cost |
| What is the read/write ratio and random/sequential mix? | Affects IOPS, throughput, caching, and media type |
| How many concurrent clients are there? | Affects connections, metadata operations, locking, and sharing |
| Are clients in the same AZ, different AZs, or on-premises? | Affects latency, network path, data transfer costs, and mountability |
| What consistency is needed after a write? | Determines safety when other clients read or update |
| How long must data persist and how should it recover? | Determines lifecycle, replication, backup, snapshot, retention, and archive |
| Who may read, write, share, and delete? | Shapes IAM, POSIX/ACL, encryption, audit, and delete permissions |

### 3.1. Common Workload Characteristics

- **Large sequential read/write:** reading or writing large files/videos, backup streams; cares about MB/s or GB/s and network throughput.
- **Small random I/O:** databases reading/writing many small pages at random locations; cares about IOPS, latency, and queue depth.
- **Metadata-heavy:** directory traversal, stat, rename, creating/deleting many files; cares about metadata performance and concurrency.
- **Read-many/write-once:** published content, model artifacts, media; object storage is usually suitable.
- **Shared mutable files:** multiple machines reading/writing the same file or directory tree; requires file locking and consistency semantics.
- **Append-only event/log:** sequential writes, long-term retention, and batch querying; object storage/data lake or a log service may fit.
- **Temporary scratch:** intermediate data that can be regenerated; local ephemeral disk or a low-cost tier may fit.

### 3.2. Do Not Confuse Capacity with Performance

A 10 TB volume is not automatically faster than a 1 TB volume. Many services decouple provisioned capacity from IOPS and throughput; some products let you provision IOPS independently, while others tie performance to size or tier. Similarly, object storage requires virtually no capacity pre-provisioning, yet still has limits on request rate, throughput, request cost, and data retrieval.

Measure against the real workload: request size, read/write ratio, queue depth, thread count, file size distribution, working set, and burst duration. Do not choose based solely on current capacity.

## 4. Object Storage: Object, Key, and Metadata

Object storage stores a payload together with metadata and an identifier (key) inside a bucket/container or corresponding namespace. Applications interact via API/SDK: PUT, GET, HEAD, LIST, DELETE, and features such as multipart upload, versioning, lifecycle, replication, or signed URLs depending on the platform.

~~~mermaid
flowchart TB
    Client["Application / browser"] --> SDK["SDK / HTTPS API"]
    SDK --> Bucket["Bucket / container"]
    Bucket --> O1["Object key: users/42/avatar.jpg"]
    Bucket --> O2["Object key: invoices/2026/INV-001.pdf"]
    Bucket --> O3["Object key: media/video-01.mp4"]
    O1 --> Meta["Payload + system/custom metadata"]
    O2 --> Meta
    O3 --> Meta
~~~

### 4.1. When Is Object Storage Suitable?

- Images, videos, audio, attachments, and documents uploaded/downloaded as whole objects.
- Static website assets and build artifacts.
- Backups, snapshot exports, archives, and long-term logs.
- Data lakes: raw data, Parquet/ORC/CSV, model artifacts, and batch analytics data.
- Content needing global access via CDN or signed URLs.
- Data with a large object count, capacity growing over time, and varied lifecycles.

### 4.2. Keys and Namespace Organization

A key is typically a unique identifier string within a bucket/container. Slashes in keys are usually just a convention creating the appearance of folders; object storage does not necessarily have real directories with full filesystem semantics.

Example:

~~~text
tenant-42/orders/2026/11/order-1001.json
tenant-42/invoices/2026/INV-1001.pdf
tenant-42/media/product-88/main.webp
~~~

Choose keys so they are easy to look up, avoid collisions, limit exposure of personal information, and suit the service's partitioning/request distribution. Do not put emails, phone numbers, or secret tokens in keys if they appear in URLs, logs, or audits. When deletion by tenant or retention is required, the namespace should support clear querying and lifecycle policies.

### 4.3. Object API Is Not Arbitrary File Manipulation

Objects are usually written or replaced as a unit; updating a few bytes in the middle of an object is not like writing random blocks to a disk. Some APIs support multipart uploads or range GETs, but that does not turn object storage into a POSIX filesystem. If an application continually modifies a large file by offset, block storage or a database may be a better fit.

Object storage may support strong read-after-write consistency for certain operations according to the service specification; you must read the provider documentation on PUT/GET/LIST, overwrite, and delete semantics. Do not assume all object services share the same consistency guarantees.

### 4.4. Multipart Upload, Range Read, and Signed URLs

- **Multipart upload:** splits a large file into multiple parts to upload in parallel and retry failed parts; must properly complete or abort to clean up incomplete parts.
- **Range GET:** downloads a byte range, useful for video streaming or resuming partial content; does not mean you can PATCH a region of an object.
- **Pre-signed URL:** grants temporary upload/download access to a client without handing out long-lived cloud credentials; must restrict method, object key, expiration, and size/conditions where the service supports them.
- **CDN:** caches objects close to users, reducing latency and origin requests; requires designing cache keys, invalidation, TTLs, and private content access control.

## 5. Block Storage: Volumes and Block Devices

Block storage provides logical devices composed of addressable blocks. The operating system can create partitions, format a filesystem, and mount the volume; databases can place data files or logs on the volume according to the engine's guidelines.

~~~mermaid
flowchart TB
    App["Database / OS / container"] --> FS["Filesystem or raw block layer"]
    FS --> Driver["Block device driver"]
    Driver --> Vol["Virtual block volume"]
    Vol --> Backend["Durable storage backend"]
    Snap["Snapshot"] -. "point-in-time copy per service" .-> Vol
~~~

### 5.1. When Is Block Storage Suitable?

- Boot/system disks for VMs.
- Databases requiring random reads/writes and low latency per volume characteristics.
- Transaction logs, message broker data, or applications performing direct file I/O.
- Persistent volumes for containers when the driver/storage class meets topology and access requirements.
- Workloads needing control over the filesystem, cache, mount options, and I/O scheduler.

### 5.2. IOPS, Throughput, and Latency

- **IOPS:** number of input/output operations per second.
- **Throughput:** amount of data transferred per second, usually measured in MB/s or GB/s.
- **Latency:** time to complete a single I/O operation.
- **Queue depth:** number of I/O requests pending or currently in flight.

A workload with many small I/Os can become IOPS-bound; a large-file streaming workload can become throughput-bound. Increasing queue depth sometimes improves utilization but can also increase latency. Look at p50/p95/p99 latency rather than average throughput alone.

### 5.3. Burst and Provisioned Performance

Some volumes have baseline IOPS/throughput and allow bursting for a certain duration or credit budget; other products let you provision IOPS/throughput separately or scale performance with capacity. If you only test for the first few minutes, the team may see good results from burst credits and then hit performance degradation under sustained load.

Load test scenarios must include:

- Sustained load long enough to exhaust burst duration.
- Peak load with the corresponding queue depth.
- Mixed read/write ratios and realistic I/O sizes.
- VM restarts, attach/detach, and failover if the workload requires them.
- Snapshots/backups running under load and their impact on latency.

### 5.4. Attaching Volumes and Sharing

Traditional block volumes are usually attached to one VM or node at a time depending on product limits. Some services offer multi-attach or clustered disks, but only for specific configurations/engines and typically require a cluster-aware filesystem or application-level coordination. **Do not mount the same block volume on multiple machines and let them write to a standard filesystem concurrently** if the product and filesystem do not support it; this can cause corruption.

In Kubernetes, a PVC has access modes such as ReadWriteOnce, ReadOnlyMany, ReadWriteMany, or ReadWriteOncePod, but actual enforcement also depends on the CSI driver and storage backend. An access mode alone does not automatically turn a block backend into a safe shared filesystem.

## 6. File Storage: Shared Filesystems

File storage provides a tree of directories and files with names, metadata, owners, permissions, and familiar filesystem operations. Clients mount it over a network protocol such as NFS or SMB; multiple instances can access the same filesystem when supported by the service.

~~~mermaid
flowchart TB
    A["VM / container node A"] --> M["NFS / SMB mount"]
    B["VM / container node B"] --> M
    C["VM / container node C"] --> M
    M --> FS["Shared file system"]
    FS --> D1["/shared/reports"]
    FS --> D2["/shared/uploads"]
    FS --> D3["/home/users"]
~~~

### 6.1. When Is File Storage Suitable?

- Legacy applications expecting directory paths and filesystem calls.
- Multiple VMs or containers needing concurrent read/write access to shared files.
- Home directories, CMS content, business processing files, and shared workspaces.
- File-processing pipelines shared across machines/workers.
- Applications depending on rename, directory traversal, file locking, or POSIX/SMB ACLs.

### 6.2. Metadata and Concurrency

File workloads do not just read payloads; they also create, rename, list, check permissions on, and delete files. A system with millions of small files and heavy metadata operations can bottleneck even when aggregate MB/s throughput is low. Benchmark directory file counts, directory listings, create/stat/rename rates, lock contention, and client counts.

With multiple clients writing to the same file, you must understand the locking semantics and cache consistency of NFS/SMB/the service. Never assume two concurrent processes writing will coordinate properly on their own. Use file locks, atomic rename, application coordination, or a database when business logic requires it.

### 6.3. NFS and SMB

| Protocol | Common characteristics | Typical use cases |
| --- | --- | --- |
| **NFS** | Commonly used in Unix/Linux environments; versions differ in locking, identity, and transport semantics | Shared Linux filesystems, analytics, and container workloads |
| **SMB** | Commonly used in the Windows ecosystem; supports shares, ACLs, and configured identity integration | Windows file shares, home directories, and SMB-based applications |

This is a guideline, not a strict rule. Some services support both NFS and SMB or specific identity integrations. Always verify protocol versions, authentication, encryption in transit, ports, mount options, and application compatibility.

## 7. Comparison by Access Scenario

A quick way to decide is to describe the application's most important operations and check whether the storage supports those semantics naturally.

| Scenario | Starting choice | Reason | Things to verify |
| --- | --- | --- | --- |
| Storing avatars, product images, and uploaded documents | Object | Each file is a separate object, accessed via key/API, easy to integrate with CDN and lifecycle | Object size, signed URLs, versioning, tenant permissions |
| PostgreSQL database on a VM | Block | Database needs filesystem/block I/O and disk control | IOPS, latency, write cache, durability, backup, and crash recovery |
| Multiple Linux VMs reading/writing a shared directory | File | Needs a file namespace and sharing over NFS | Locking, metadata rate, identity mapping, throughput, and mount recovery |
| Static website with high traffic | Object + CDN | Published content is immutable or changes infrequently, cached near users | Cache invalidation, TLS, access control, and origin protection |
| Long-term log data, batch analytics | Object | Data appended/exported as files and read in batches | Time partitioning, columnar format, lifecycle, query engine |
| Regenerable worker scratch data | Local ephemeral or suitable block | Needs temporary I/O, no persistence required after worker finishes | Capacity, local disk speed, eviction, and retries |
| Windows application needing a shared drive | File/SMB | Application expects Windows shares and semantics | Directory service, ACLs, locking, SMB version |
| Multiple containers sharing an upload folder | File if shared filesystem needed; object if exchanging objects | Decide based on file operations vs. object API | Scale, concurrent writes, access mode, network, and cost |

You do not need to force all data of an application into one storage type. An e-commerce application might use a database on block storage or a managed database, images in object storage, exported reports in object storage, and a shared directory for internal tools on file storage.

## 8. Consistency, Locking, and Concurrency

Storage must not only hold bytes; it must provide read/write visibility and update behavior that match the application.

### 8.1. Object Consistency

Object storage typically provides API-level semantics. When updating objects, clients must understand:

- Whether writing a new/replacement object has atomic visibility under the service contract.
- Whether LIST sees new objects immediately under the consistency model.
- Whether versioning retains prior versions on overwrite/delete.
- Whether conditional writes, ETags, generation/version preconditions, or compare-and-swap are supported.
- What the winner/loser or versioning rules are for concurrent PUTs to the same key.

If multiple clients can modify the same object, avoid read-modify-write patterns without coordination. Use conditional requests/version preconditions, an appropriate lease/lock, or move high-concurrency updates to a database. An ETag is not always a content checksum; multipart uploads or encryption can produce service-specific ETag semantics.

### 8.2. Block Consistency

Block devices typically provide device semantics to a single host/kernel or under a supported multi-attach mechanism. Filesystems and databases rely on flushes/barriers, caches, journals, and locks to maintain correctness. When multiple hosts access a block device, only a supported clustered filesystem or application-level coordination can guarantee safety.

Never mount and write to the same raw block volume using two independent standard filesystems at the same time. Each host can cache metadata independently and corrupt the filesystem structure.

### 8.3. File Consistency and Locking

File services require defining behavior when multiple clients read/write the same file, attribute caching, file leases/oplocks, locking, and renames. Semantics vary across NFS/SMB versions and providers.

When multiple workers write outputs, a safer pattern is to write to separate temporary files and publish via rename or a coordinated manifest, rather than having all workers write to the same target file. For transactional data and high-concurrency updates, a database is usually a better abstraction than a filesystem.

## 9. Availability, Durability, and Data Protection

Three commonly confused concepts:

- **Availability:** whether clients can access the service/data when needed.
- **Durability:** the probability that written data will not be lost over a given period.
- **Recoverability:** whether the organization can restore data and applications to the required state within the target time.

A high-durability service can still suffer accidental deletion, ransomware encryption, or logical overwrites. Therefore, durability does not replace versioning, backups, retention locks, replication, and restore testing.

### 9.1. Snapshots Are Not Complete Backups

Snapshots usually capture the state of a volume/filesystem at a point in time according to service capabilities. They are useful for rollbacks, clones, image creation, or backup workflows, but consider:

- Is the snapshot crash-consistent or application-consistent?
- Must the filesystem or database be frozen/quiesced before taking the snapshot?
- Is the snapshot stored in the same failure domain or copied to another account/region?
- Can it be deleted with the same admin permissions or compromised ransomware credentials?
- Can it be restored independently if the original volume is lost?

For databases, a crash-consistent snapshot may require database recovery from WAL/transaction logs. For file shares, snapshots require semantics for open files and actively writing applications. For objects, versioning or object lock can protect against policy-violating deletes/overwrites, but lifecycle and permissions still need management.

### 9.2. RPO and RTO

**Recovery Point Objective (RPO)** is the maximum acceptable data loss measured in time; **Recovery Time Objective (RTO)** is the target maximum time to restore service. Both must be defined by business processes:

| Workload | RPO/RTO questions to ask | Design measures likely needed |
| --- | --- | --- |
| Order database | Can confirmed transactions be lost? How soon must service resume? | Consistent backups, log shipping/PITR, replicas/failover, and drills |
| Product images | Can they be regenerated or must every accepted upload be kept? | Object versioning, replication, deletion protection |
| Shared files | How fast must directories and permissions be restored? | Snapshots, cross-failure-domain backups, ACL/identity backups |
| Log analytics | How many minutes of log loss are acceptable? | Buffering/replication, object retention, partitioned exports |

A low RPO typically requires more frequent replication or log capture, increasing cost and network dependency. A low RTO requires runbooks, automation, standby capacity, and drills; it cannot be achieved simply by buying a faster storage tier.

### 9.3. Replication Is Not Backup

Replication puts data in another failure domain for HA/DR or closer access. However, accidental deletes, bad overwrites, or encrypted data can replicate to the copy. Backups with retention and historical recovery are a distinct protection layer.

Data protection design should be layered:

1. **Replication/HA** to tolerate component or zone failures according to supported semantics.
2. **Snapshots/point-in-time recovery** to roll back to a state before a given point.
3. **Independent backups** with retention, separate delete permissions, and copies outside the primary failure domain.
4. **Restore tests** to measure recovery time, consistency, and completeness of restored data.

## 10. Storage Security and Data Governance

Storage holds critical data and must be protected across transit, storage at rest, access identity, and deletion lifecycle.

### 10.1. Identity and Access Control

- For object storage, grant permissions by bucket/container, prefix, object, or required role; use short-lived signed URLs when clients need direct upload/download.
- For block storage, restrict who can create, attach, detach, snapshot, copy, and delete volumes; workload network access must also be controlled.
- For file storage, combine network security with POSIX owner/mode, ACLs, identity mapping, or directory services.
- Separate permissions for reading, writing, deleting, key management, and policy changes. An application role does not necessarily need permission to delete backups.
- Use workload identities/managed identities where appropriate; avoid embedding long-lived access keys on machines or containers.

### 10.2. Encryption

| Layer | Questions |
| --- | --- |
| In transit | Do clients connect over TLS, encrypted NFS/SMB, or a protected network? How are certificates verified? |
| At rest | Is encryption enabled by default or opt-in? Do objects, volumes, snapshots, and backups differ? |
| Key management | Use provider-managed keys or customer-managed keys? Who can rotate/disable them? |
| Key availability | If KMS/keys are locked or a region has an outage, can the application still read data? |
| Audit | Are reads, writes, deletes, policy changes, and key changes logged? |

Customer-managed keys increase control and policy compliance, but add responsibility for rotation, availability, recovery, and permission boundaries. If a key is disabled or deleted, encrypted data can become inaccessible even when the storage service itself is healthy.

### 10.3. Data Lifecycle and Deletion

Object storage often supports lifecycle transitions to cold tiers, archives, or expiration. File and block storage have their own retention, snapshot schedules, volume deletion policies, and backup cleanup. Define:

- Which tier holds hot data accessed frequently?
- When does data move to a cheaper tier, and how long does a restore take?
- Are there minimum storage durations or retrieval charges?
- How is expired data deleted across objects, versions, snapshots, replicas, and backups?
- Do legal/privacy obligations require deletion across all copies or retention locks?

Do not apply lifecycle transitions based purely on data age if a workload still accesses the data frequently. Archive retrieval fees and restore delays can outweigh cheaper storage rates.

### 10.4. Multi-Tenant Storage

For multi-tenant data, separate namespaces/prefixes alone do not guarantee isolation. Enforce tenant validation policies in the backend, check key ownership, separate roles or buckets by risk level, prevent IDOR, and test cross-tenant access. For file shares, verify identity mapping and ACLs; for block storage, volume attachments and snapshots must enforce tenant/account boundaries.

## 11. Performance and Sizing by Workload

Before choosing a tier, build a verifiable workload profile:

| Metric | How to collect |
| --- | --- |
| Current capacity and growth rate | Total bytes, object/file count, weekly/monthly growth |
| Data unit size | Distribution of small/medium/large, p50/p95/p99 |
| Read/write ratio | Counts of reads/writes, overwrites, deletes, and metadata requests |
| IOPS | Small I/Os per second at the block/file backend |
| Throughput | Sustained read/write MB/s or GB/s |
| Latency | p50/p95/p99 per operation, not just averages |
| Concurrency | Number of concurrent clients, threads, processes, mounts, and requests |
| Working set/cache | Hot data size, cache hit ratio, page cache |
| Network path | Same AZ, cross-AZ, on-prem, Internet, or CDN |

### 11.1. Example Distinguishing IOPS and Throughput

A database performs 20,000 I/Os per second, each 8 KiB. Raw data throughput is approximately:

**20,000 × 8 KiB ≈ 156.25 MiB/s.**

A video pipeline writing 1 MiB chunks at 500 MiB/s needs roughly 500 I/Os per second if each chunk produces one corresponding I/O. The two workloads have vastly different throughput and IOPS demands; you cannot choose storage using a single MB/s figure.

This example excludes filesystem metadata, write amplification, caching, replication, request overhead, and actual I/O sizes. Use application-level benchmarks to confirm.

### 11.2. Queue Depth and Tail Latency

When a workload issues many parallel I/Os, higher queue depth can help utilize the backend, but once it exceeds processing capacity, wait times increase and p95/p99 latency degrades. A database might achieve higher average throughput while critical transactions slow down. Set queue limits, timeouts, and concurrency according to application SLAs.

### 11.3. Caching and CDN

Caching at the application, OS page cache, CDN, or service cache layer can reduce storage requests. However, caching introduces invalidation, stale data, and consistency concerns. For immutable versioned objects, long caching can be effective; for frequently changing files, you need TTL/ETag/conditional GET and a publishing strategy. Do not use caching to mask backend latency before understanding the bottleneck.

## 12. Total Cost of Ownership and Tier Optimization

Per-GB storage pricing is only part of the bill. TCO can include:

- Monthly capacity stored per tier.
- Provisioned IOPS/throughput, capacity, or performance add-ons.
- API requests (GET/PUT/LIST/metadata), retrievals, and restores.
- Snapshots, versioning, replication, and backups.
- Cross-AZ/region replication, network egress, and data transfer.
- Gateways, caches, CDNs, mount compute, and licenses.
- Operational labor, on-call, auditing, migrations, and recovery.
- Downtime or data loss costs from choosing an unsuitable tier.

| Type | Common cost components | Pitfalls |
| --- | --- | --- |
| Object | GB-month, request class, retrieval, replication, egress, versioning | Excessive LIST/GET calls, unpruned versions, and frequent archive restores |
| Block | Provisioned capacity, IOPS/throughput, snapshots, cross-zone transfer | Over-provisioning size/speed, keeping stale snapshots, paying for idle provisioned resources |
| File | Capacity, throughput mode, metadata/operations, backups, cross-zone | Heavy client/metadata operations, provisioned filesystem sitting mostly idle |

### 12.1. Hot, Warm, and Cold Data

- **Hot:** accessed frequently, requires low latency; choose an appropriate performance tier and cache.
- **Warm:** accessed unevenly; standard or auto-tiering classes may fit.
- **Cold/archive:** rarely accessed, can wait for restore; account for minimum retention, retrieval fees, and restore times.

Older data is not automatically cold. Legal records may be accessed unexpectedly with a tight SLA; factor in both retrieval probability and restore cost.

### 12.2. Estimating Capacity and Cost

Rough object storage estimate:

**Monthly capacity cost = average GB stored × GB-month unit price.**

Total cost must add requests, retrievals, replication, versioned copies, and egress. For block storage, provisioned volume capacity may be billed even before the filesystem is filled; for file storage, billing may follow the service's capacity/throughput mode. Use the provider's actual pricing model and measure growth instead of comparing per-GB unit prices alone.

## 13. Choosing Storage for Containers and Cloud-Native Applications

Containers are short-lived and continually rescheduled and scaled; storage must be decoupled from container lifecycles whenever data must persist.

### 13.1. Ephemeral Volumes and Local Disks

Suitable for caches, scratch space, temp files, and regenerable data. The upside is low latency and typically direct node attachment; the downside is that data can be lost when a Pod/node is deleted or relocated. Never use ephemeral storage for unique transactional data.

### 13.2. Persistent Block Volumes via CSI

A container orchestrator can use a CSI driver to provision and attach block volumes to Pods. Understand access modes, topology, attachment limits, volume binding modes, snapshot classes, and behavior when a Pod moves nodes. A volume may be tied to a single zone, preventing a Pod from rescheduling freely across all zones.

### 13.3. Shared File Volumes

When multiple replicas need the same directory tree, file storage can be mounted into multiple Pods/nodes if the driver supports the required sharing mode. Verify ReadWriteMany, NFS/SMB semantics, throughput, locking, identity, and network policies. If replicas only need identical input files, object storage with local download/caching can be simpler and cheaper.

### 13.4. Object Storage for Application Data

Containerized applications should generally store uploads, documents, and media directly in object storage via SDK/API or signed URLs. Do not mount a bucket as a filesystem just for coding convenience if the application already operates on objects; filesystem gateways can behave differently on renames, locking, and consistency.

## 14. End-to-End Example: E-Commerce Platform

Suppose a system has a transactional database, product images, invoice documents, a shared directory for a legacy processing tool, and scheduled backups.

~~~mermaid
flowchart TB
    Web["Web / Mobile"] --> API["API / Application"]
    API --> DB[("Managed relational DB")]
    Web -->|Upload/download via signed URL| Obj["Object storage: images, invoices"]
    API -->|Metadata and access permissions| Obj
    Legacy["Legacy processing VMs"] --> NFS["Shared file storage"]
    Worker["Container workers"] -->|Read shared data| NFS
    DB --> Backup["Backup / PITR"]
    Obj --> Lifecycle["Versioning / Lifecycle / Replication"]
    NFS --> Snap["Snapshot / Backup"]
~~~

### 14.1. Why Split It This Way?

- The database uses a storage backend suited to its engine; if self-hosting the database on a VM, block volumes must be sized for random I/O, write latency, durability, and backups.
- Product images and invoices are objects; the application stores metadata, owner, status, and permissions in the database, with payloads in object storage.
- The file share serves the legacy tool needing a shared NFS/SMB namespace across machines; if workers only exchange immutable files, you can gradually migrate toward objects to reduce filesystem dependency.
- Database and file share backups need retention, off-domain copies, and restore tests. Object versioning alone does not replace system-wide backups.

### 14.2. Secure Upload Flow

1. The client asks the API to create an upload intent for a document.
2. The backend validates the tenant, file type, and allowed size, and issues a short-lived signed URL with a server-generated key.
3. The client uploads directly to object storage; there is no need to proxy all bytes through API compute unless processing requires it.
4. The backend verifies the upload (object key, size, checksum/metadata, scan status) and records metadata in the database.
5. Unscanned files are held in a quarantine area; only after passing scanning are downloads allowed via an authorized flow.
6. Lifecycle, retention, and per-tenant deletion are enforced by policy.

Direct uploads offload bandwidth and compute from the API, but the backend must still enforce authorization and verify that the uploaded object matches the expected key/size. A signed URL is a bearer capability; anyone holding the URL before expiration can use its signed permissions, so do not log or share URLs carelessly.

## 15. Migrating Between Storage Types

Replacing object with file, block with a managed database, or a file share with an object store is more than copying bytes. You must also migrate semantics, permissions, metadata, lifecycle, and application access patterns.

### 15.1. Migration Steps

1. **Inventory:** list datasets, capacity, object/file counts, access patterns, owners, ACLs, metadata, dependencies, and retention.
2. **Target contract:** define API/semantics on the new storage, consistency, performance, encryption, keys, versions, and restore behavior.
3. **Baseline:** measure latency, IOPS, throughput, error rates, costs, and job durations on the current system.
4. **Bulk copy:** copy data while verifying checksums/sizes/metadata; preserve permissions and encryption per policy.
5. **Incremental sync:** synchronize changes occurring during the copy; define capture mechanisms and delete handling.
6. **Validation:** compare counts, checksums, object/file mappings, ACLs, application data, and performance.
7. **Cutover:** switch clients to the new endpoint, throttle writes or use well-coordinated dual-writes; record the cutover timestamp.
8. **Rollback window:** keep the old source read-only/recoverable as planned; define how to handle new data created on the target.
9. **Decommission:** delete the old source, snapshots, secrets, and permissions after the rollback window closes and owners sign off.

### 15.2. Risks When Changing Semantics

| Transition | Issues that cannot be ignored |
| --- | --- |
| File → Object | Directory renames, POSIX permissions, file locks, and partial updates lack native equivalent semantics |
| Object → File | Key mapping, object metadata, versioning, huge counts of small objects, and path/filename limits |
| Block → Object | Random writes, filesystem journals, and database data files cannot simply be copied as objects and keep running |
| Object → Block | Loses the key/API abstraction; must self-manage filesystems, partitions, scaling, and backups |
| Self-managed storage → Managed service | IAM, endpoints, access models, quotas, encryption keys, and maintenance windows differ |

For databases running on block storage, migration typically requires database-native backup/restore, replication, or logical migration; never copy a raw volume while a database is actively writing without a consistent procedure.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Choosing storage by per-GB price alone | Performance, request, and retrieval costs exceed expectations | Calculate TCO based on the access pattern |
| Using a block volume to share files across VMs | Filesystem corruption if multi-writer is unsupported | Use a file service or a supported clustered filesystem |
| Treating object storage like a POSIX filesystem | Incorrect semantics for rename/lock/partial update | Use the object API or an appropriate file service |
| Treating snapshots as backups | Deletes/corruption can affect snapshots or miss application-level recovery | Maintain independent backups, retention, and restore tests |
| Treating replication as protection against accidental deletion | Bad or deleted data replicates to the replica | Use versioning, backups, retention locks, and recovery |
| Sizing volumes by capacity without benchmarking | Insufficient IOPS/throughput or wasted spend | Benchmark with the right I/O profile and tier |
| Attaching shared file storage to every container | Increases network latency, metadata contention, and cost | Use only when filesystem sharing is truly needed |
| Leaving buckets/file shares public | Data leaks and privacy violations | Least privilege, signed URLs, private endpoints, and auditing |
| Ignoring egress/replication costs | Bills spike during cross-region copies or reads | Estimate traffic and client locations |
| Archiving via lifecycle too early | Slow restores and high retrieval fees | Classify data by access probability and SLA |
| Migrating by copying bytes only | Loss of ACLs, metadata, versions, consistency, or rollback | Perform full inventory, incremental sync, and validation |

## 17. Practice Exercise: Choosing Storage for a Multi-Workload System

A content processing platform has the following capabilities:

- An API managing accounts, orders, and metadata.
- A transactional database requiring random reads/writes and recovery per an approved RPO.
- Users uploading videos from mobile devices; file sizes range from a few MB to many GB.
- Container workers batch-processing videos that can run across multiple nodes.
- A legacy tool on multiple VMs needing shared visibility into an export reports directory.
- Completed data retained long-term for auditing, with read frequency decreasing over time.

**Assignment requirements:**

1. Choose object, block, and file storage for each dataset; justify based on access patterns.
2. Define the video upload path using signed URLs/multipart uploads and how to verify checksums, tenant permissions, and virus scanning.
3. Size the database volume by IOPS, throughput, latency, and queue depth; state load assumptions clearly.
4. Choose NFS/SMB or an alternative for the legacy directory; analyze locking, metadata, and concurrent access.
5. Build a hot/warm/archive lifecycle, retention, and retrieval SLA for videos, reports, and backups.
6. Design backups/replication to meet RPO/RTO, distinguishing snapshots from independent backups.
7. Propose encryption, IAM, network isolation, auditing, key rotation, and per-tenant deletion policies.
8. Create a TCO table covering capacity, IOPS, requests, egress, snapshots, archive retrieval, and operational labor.
9. Write a migration plan if moving the legacy tool from a file share to object storage; note semantics to change and rollback conditions.

### Evaluation Guidance

A sound design can use a managed database with service-managed storage or engine-appropriate block volumes, object storage for videos and documents, and file storage for the legacy tool requiring a shared directory. Workers should only use file storage if shared filesystem operations are required; if processing stages exchange immutable objects, object keys and a manifest can be simpler.

The backup section must state clearly which data is protected, where copies reside, who has delete permissions, and how restores are proven. The cost section must include request/retrieval/egress/replication charges rather than GB alone.

## 18. Pre-Production Storage Checklist

- [ ] Every dataset has a clear owner, classification, retention, and business requirement.
- [ ] Access patterns are documented: object/key, random/sequential block, file/metadata, or mixed.
- [ ] Metrics exist for capacity, growth, IOPS, throughput, latency, concurrency, and data unit sizes.
- [ ] Storage semantics for consistency, locking, atomicity, rename, overwrite, and multi-client access are verified.
- [ ] Block attach/multi-attach and filesystem sharing strictly follow product/driver limits.
- [ ] Object keys, buckets/prefixes, signed URLs, versioning, and lifecycle are planned.
- [ ] File protocol, identity mapping, ACLs, locking, and network access are tested.
- [ ] Encryption in transit/at rest, key ownership, rotation, and recovery are designed.
- [ ] IAM/ACLs follow least privilege; tenant isolation and delete permissions are verified.
- [ ] Snapshots, backups, replication, and PITR are distinguished; RPO/RTO have owner sign-off.
- [ ] Real restore tests have been run on data and applications, not just checking that backup jobs succeeded.
- [ ] Tiers/lifecycles match retrieval SLAs; minimum duration, retrieval, and early deletion fees are factored in.
- [ ] Costs include storage, performance, requests, network, backups, replication, logging, and labor.
- [ ] Benchmarks ran under realistic load, including peak, concurrency, mixed I/O, and tail latency.
- [ ] Migration/cutover includes checksums, incremental sync, validation, rollback, and old-data cleanup.
- [ ] Logs, metrics, quotas, capacity alerts, and runbooks are ready for operations, investigation, and recovery.

**Remember:** Object storage fits data accessed by object/key; block storage fits block-level I/O devices for VMs, databases, and random I/O workloads; file storage fits applications needing a shared filesystem and namespace. Choose based on the **access pattern and semantics to preserve**, then validate through benchmarks, security reviews, backup/restore tests, and total cost of ownership. A good architecture can combine all three types so every dataset lives where it best matches how it is created, read, shared, and recovered.
