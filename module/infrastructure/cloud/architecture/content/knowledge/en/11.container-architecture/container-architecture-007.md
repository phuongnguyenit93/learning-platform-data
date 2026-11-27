# Designing Stateful Workloads and Persistent Storage

Containers are designed to run applications inside replaceable, packaged environments. When a container or Pod is deleted, restarted, or moved to another node, the writable filesystem inside the container is usually not the place to store long-lived data. This requires special attention for **stateful workloads** such as databases, message brokers, search engines, registries, stream processing platforms, and applications maintaining session data.

Stateful container design must answer a critical question: **how can compute lifecycles remain mutable while data stays durable, consistent, secure, and recoverable?** Attaching a volume to a Pod is only the first step. You must also choose the storage type, define data ownership, plan topology, handle read/write mechanisms, configure replication, backups, restores, access control, and define procedures when a node or zone fails.

In the **CLOUD_ARCHITECTURE** module, this topic connects container architecture with data, networking, compute, and operational choices aligned with Well-Architected goals: reliability, security, performance, cost optimization, and operational excellence.

## 1. Stateless vs. Stateful: Differing in Data Lifecycle

A **stateless workload** does not retain unique business state in the local filesystem or memory of a single replica across requests. Replicas can be replaced, and subsequent requests can be handled by other replicas, provided required data resides in external services or can be regenerated.

A **stateful workload** must preserve part of its data or a stable identity across process/container lifecycles. A database must preserve data pages; a message broker must preserve unacknowledged messages; a search node must preserve index shards or have a rebuild mechanism; a system with local sessions must protect session state when a Pod is replaced.

| Characteristic | Stateless | Stateful |
| --- | --- | --- |
| Primary data | Stored in external DB/cache/object storage or regenerable | Has data to preserve tied to the app or volume |
| Replica replacement | Generally straightforward | Must reattach the right data and prevent conflicting writers |
| Horizontal scaling | Add/remove replicas by load | Must handle sharding, replication, quorum, partitions, or write limits |
| Scheduling | Replicas can run on any eligible node | Placement must consider volume topology and node/zone |
| Recovery | Spin up a new replica and load configuration | May require attaching volumes, log recovery, rebuilds, or failover |
| Testing | Health checks, rollouts, load tests | Plus corruption, detach/attach, node loss, restore, split-brain |

For instance, a containerized web application should externalize sessions to a cache/shared session store and business data to an independently managed database. The API Pods can then stay stateless. However, the database or broker behind them remains a stateful workload requiring its own storage strategy.

### State Does Not Live Only in Files

A workload can hold state in:

- **Filesystem:** data files, indexes, transaction logs, checkpoints.
- **Memory:** sessions, caches, leader state, unpersisted queues.
- **Network identity:** stable hostnames, endpoint addresses, or cluster membership.
- **Logical identity:** node IDs, broker IDs, shard/partition identities.
- **Orchestration metadata:** volume location, replica roles, failover state.

Not everything requires a persistent volume. However, you must clearly identify what **can be regenerated**, what must be **persisted**, and what can be recovered from replicas or other data sources.

## 2. Container Filesystems and Why Persistent Storage Is Needed

Container images typically deploy as immutable filesystem layers (read-only image layers) topped with a container writable layer. This writable layer is tied to the container's lifecycle; when a new container is created, the old writable layer does not automatically carry over to the new container. A replaced Pod also receives a fresh writable filesystem.

~~~mermaid
flowchart TB
    subgraph CONTAINER["Container filesystem"]
      IMG["Image layers (read-only)"]
      WRITE["Writable layer (ephemeral)"]
      IMG --> WRITE
    end
    subgraph POD["Pod"]
      APP["Application process"]
      TMP["Temporary / cache files"]
      APP --> TMP
    end
    PV["Persistent volume"]
    APP -->|Mount path| PV
~~~

The diagram distinguishes image layers, the writable layer, and volumes. Certain temporary paths can be mounted from `emptyDir` or the node's temporary filesystem; these are still not durable storage across all Pod/node failure scenarios. Persistent volumes have an independent lifecycle managed by platform mechanisms and the storage provider.

### When to Use Ephemeral Storage?

Ephemeral storage is suitable for:

- Temporary files created while processing a request/job.
- Regenerable caches that are not the source of truth.
- Scratch space for unpacking, sorting, or transforming data.
- Shared temporary files between containers in the same Pod when the Pod lifecycle is acceptable.

Never use ephemeral storage as the sole home for databases, user uploads, unprocessed messages, or the only checkpoint of a long-running batch job. If the node fails or the Pod is replaced, that data can be lost.

### When Is a Persistent Volume Needed?

Persistent volumes are appropriate when an application needs data to survive independently of the container/Pod, such as:

- Databases storing data files and transaction logs.
- Message brokers storing segments/queue metadata.
- Search engines storing indexes when rebuilding from source is impossible or too slow.
- Registry/artifact services storing blobs and metadata.
- Stateful analytics or streaming engines storing checkpoints/state stores.

However, a persistent volume only covers **one part of the storage layer**. It does not automatically provide backups, replication, transaction consistency, database failover, ransomware protection, or guarantee the application recovers cleanly.

## 3. Storage Models: Block, File, and Object

Choose storage based on the application's access pattern, not just the service name.

| Storage Type | How Applications Access It | Common Use Cases | Trade-Offs |
| --- | --- | --- | --- |
| **Block storage** | Block device attached to a node/VM; filesystem or database manages layout on top | Database data directories, broker disks, workloads needing controlled IOPS/latency | Attachment/topology constraints; requires suitable filesystem and concurrency |
| **File storage** | Multiple clients access a file/directory namespace over protocols like NFS/SMB or equivalents | Shared content, file exchange, home directories, legacy tools needing shared filesystems | Performance depends on metadata/throughput/locking; semantics differ from local disk |
| **Object storage** | Accesses objects via API using keys/buckets/containers; not a standard POSIX filesystem | Media, backups, log archives, static assets, data lakes | Unsuitable as a block disk for typical databases; must understand API/consistency semantics |

### Block Storage

Block volumes provide a storage device to a node or instance. The OS/application formats a filesystem or uses raw devices. Databases typically favor block storage with predictable latency and IOPS, but you must verify:

- IOPS, throughput, and latency at realistic I/O sizes.
- Random read/write ratios, sequential workloads, and burst credits if applicable.
- Internal durability and replication of the storage service.
- Whether multi-attach is supported and under what conditions.
- Backups/snapshots, encryption, resizing, and attach/detach durations.

Never mount the same block filesystem across multiple nodes just because a storage driver allows multi-attach. Multi-writer setups require clustered filesystems/distributed locking and applications built for those semantics; ordinary databases are unsafe when two nodes open the same data directory simultaneously without supported clustering mechanisms.

### File Storage

File storage provides a network-accessible directory namespace. It is useful when multiple Pods need to read/write the same set of files or legacy applications expect a file share. Evaluate:

- Multi-client concurrency support, file locking, and rename/permission semantics.
- Throughput, metadata IOPS, file handle limits, and connection limits.
- Performance when many Pods access hot directories or create numerous small files.
- Mount mechanics, network paths, private endpoints, and failover.
- Backups, quotas, retention, and capacity/throughput pricing.

File storage does not resolve application-level concurrency conflicts on its own. Two Pods modifying the same file need locking or safe write protocols; otherwise, files can be overwritten or logically corrupted.

### Object Storage

Object storage is built to store objects with keys and metadata accessed via APIs. It fits images, video, backups, logs, and large-scale unstructured data. Some containerized applications use object storage instead of persistent volumes for media, but never assume an object store offers full filesystem semantics (locks, seeks, atomic renames, POSIX permissions).

For object storage, design:

- Key naming, metadata, versioning, and overwrite policies.
- Multipart uploads, checksums, and integrity verification.
- Lifecycle tiering to cold storage, retention, and deletion rules.
- Access control via workload identity, bucket/container policies, and encryption.
- Event notifications, duplicates, retries, and handling incomplete objects.

### Quick Selection by Data Type

| Data | Commonly Considered Option | Notes |
| --- | --- | --- |
| Database transaction files | Block volume or managed database storage | Must follow database engine guidelines |
| User files/images/video | Object storage | Separate metadata and lifecycle management |
| Shared folder for legacy apps | File storage | Verify file locking and throughput |
| Regenerable cache | In-memory cache or ephemeral disk | Never treat as a durable source |
| Backups and archives | Object storage or backup services | Isolate permissions, retention, and restore tests |
| Engine logs/checkpoints | Block or engine-specific storage | Never delete before engine confirms safety |

## 4. Persistent Storage in Kubernetes: PV, PVC, StorageClass, and CSI

In Kubernetes, applications typically request storage via a **PersistentVolumeClaim (PVC)**. A PVC describes the required capacity, access modes, and storage class. A **PersistentVolume (PV)** represents a cluster-managed storage resource; PVs may be pre-created (static provisioning) or dynamically provisioned from a StorageClass. Volume plugins/CSI drivers connect Kubernetes to the underlying storage system.

~~~mermaid
flowchart TB
    POD["Pod"]
    PVC["PersistentVolumeClaim"]
    SC["StorageClass"]
    PV["PersistentVolume"]
    CSI["CSI driver"]
    BACKEND["Cloud block/file storage"]
    POD -->|Mount PVC| PVC
    PVC -->|Request provisioning| SC
    SC -->|Provision / bind| PV
    PV --> CSI
    CSI --> BACKEND
~~~

The diagram shows the conceptual flow; actual provisioning and binding order can depend on volume binding mode, controllers, CSI drivers, and the scheduler.

### Components

| Component | Responsibility |
| --- | --- |
| **PVC** | Workload's storage request: capacity, access mode, storage class |
| **PV** | Represents the provisioned volume and its attributes |
| **StorageClass** | Provisioning policy: provisioner, storage tier, parameters, reclaim policy, binding mode |
| **CSI (Container Storage Interface)** | Standard interface for storage providers to integrate provisioning, attach, mount, snapshot, and resize capabilities per driver support |
| **Volume snapshot** | Represents a volume snapshot via API/driver support; requires application data-consistency procedures |

### Example PVC Requesting a Block Volume

The following example illustrates a PVC requesting 100 GiB and an access mode. The StorageClass name is a placeholder and must be replaced with one provided by the cluster:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: database-data
  namespace: production
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: standard-block
  resources:
    requests:
      storage: 100Gi
~~~

This example **only requests storage provisioning**; it does not create a database, credentials, backups, or HA. Access modes govern volume attachment per Kubernetes and driver semantics, and do not replace database locking or replication. Actual attach behavior also depends on the CSI provider and platform.

### Mounting a PVC into a Pod

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: storage-check
  namespace: production
spec:
  containers:
    - name: app
      image: example.registry.local/storage-app:v1
      volumeMounts:
        - name: data
          mountPath: /var/lib/app
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: database-data
~~~

The Pod mounts the volume at the declared path. When the Pod is replaced, the controller can create a new Pod and reattach the PVC subject to topology, detach/attach state, and storage provider capabilities. In real environments, verify mount options, filesystem ownership, security contexts, images, and namespaces.

### Access Modes Are Not Application Concurrency Controls

| Access Mode | General Meaning |
| --- | --- |
| **ReadWriteOnce (RWO)** | Volume can be mounted read-write by a single node at a time per volume/plugin semantics; multiple Pods on that same node may share it depending on platform |
| **ReadOnlyMany (ROX)** | Can be mounted read-only by multiple nodes if supported by the driver |
| **ReadWriteMany (RWX)** | Can be mounted read-write by multiple nodes if supported by the driver |
| **ReadWriteOncePod (RWOP)** | Restricts the volume to read-write mount by a single Pod in the cluster, when supported by the CSI driver and Kubernetes |

Do not interpret RWO as "only one Pod" or RWX as "safe for any concurrent writers." RWO typically binds at the node level, whereas RWOP targets Pod-level restriction. Multiple writers still require application/filesystem/database concurrency management. Some storage classes do not support all access modes; verify driver documentation and test in practice.

### StorageClass and Binding Topology

A StorageClass can select disk tiers (performance classes), provisioners, encryption, reclaim policies, and binding modes. Two key binding settings:

- **Immediate:** the volume can be provisioned/bound as soon as the PVC is created, before the scheduler chooses a node; on zonal storage systems, Pods may later get stuck if the volume lands in the wrong topology.
- **WaitForFirstConsumer:** delays provisioning/binding until a consumer Pod is scheduled, allowing the scheduler to consider both Pod placement requirements and storage topology together.

For example, block volumes are zonal resources. If a PVC is created in zone A while a StatefulSet Pod is scheduled in zone B, the Pod can remain Pending because the volume cannot attach there. Use appropriate binding modes and storage topology to minimize this failure. `WaitForFirstConsumer` does not solve multi-zone replication on its own; each replica and its storage placement must be designed explicitly.

### Reclaim Policy and Data Lifecycle

After a PVC is deleted, the PV follows its reclaim policy such as **Retain** or **Delete** depending on resource type and configuration. `Delete` can remove the underlying backend volume as part of cleanup; `Retain` keeps the resource for manual administration or reuse. Never assume deleting a PVC only unmounts it or always deletes data. Before modifying charts/manifests or cleaning up namespaces, check:

- Who owns the volume and data?
- Was the PVC/PV provisioned statically or dynamically?
- What is the current reclaim policy?
- Are there verified snapshots/backups?
- Is there a procedure to recover or rebind if the PVC is recreated?

## 5. StatefulSets and Stable Replica Identity

A Kubernetes **Deployment** suits interchangeable replicas that typically do not need unique identities or volumes. A **StatefulSet** is designed for workloads needing stable network identities, ordered creation/deletion, or dedicated persistent volumes per replica.

StatefulSets typically provide:

- **Stable ordinals:** Pods are named sequentially by index, e.g., `database-0`, `database-1`.
- **Stable network identity:** paired with a headless Service to provide per-Pod DNS identities.
- **Stable storage association:** `volumeClaimTemplates` create a dedicated PVC for each ordinal.
- **Controlled rollouts/scaling:** ordered start/stop/update behavior per StatefulSet policy.

A StatefulSet does not automatically create a database cluster, replication, leader election, quorum, backups, or safe failover. It only provides Pod orchestration and stable identity; the application must still implement an appropriate clustering protocol.

### Three-Replica StatefulSet Example

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: ledger
  namespace: production
spec:
  clusterIP: None
  selector:
    app: ledger
  ports:
    - name: client
      port: 8080
    - name: peer
      port: 7000
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ledger
  namespace: production
spec:
  serviceName: ledger
  replicas: 3
  selector:
    matchLabels:
      app: ledger
  template:
    metadata:
      labels:
        app: ledger
    spec:
      containers:
        - name: node
          image: example.registry.local/ledger-node:v1
          ports:
            - name: client
              containerPort: 8080
            - name: peer
              containerPort: 7000
          volumeMounts:
            - name: data
              mountPath: /var/lib/ledger
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes:
          - ReadWriteOnce
        storageClassName: zonal-ssd
        resources:
          requests:
            storage: 50Gi
~~~

This is an illustrative skeleton; images, peer discovery, authentication, probes, resource requests/limits, backups, security contexts, and storage classes must be engineered for the specific engine. Never deploy a production database StatefulSet using this minimal manifest alone.

For example, ordinal zero receives its own PVC matching the claim template and Pod name. When the Pod is recreated, that PVC is typically retained and reattached to the replacement Pod according to policy and topology. Scaling a StatefulSet down does not automatically delete PVCs under default settings, yet **never rely on lifecycle assumptions**; verify Kubernetes version behavior, retention policies, chart/operator settings, and deletion procedures.

### Scheduling and Spreading Replicas

If three database replicas land on the same node or in the same AZ, losing that node/AZ can break quorum. Consider:

- **Pod anti-affinity or topology spread constraints** to distribute replicas across nodes/AZs.
- **PodDisruptionBudgets (PDBs)** to limit disruptions from supported voluntary maintenance; PDBs do not stop node failures and do not replace HA.
- **Node affinity/taints/tolerations** matched with storage attachment capabilities in the target nodes/zones.
- **Resource requests/limits** so the scheduler places Pods with adequate headroom and avoids contention.
- **Startup/readiness/liveness probes** tuned for the application's recovery sequence.

Forcing three replicas across three AZs only helps if storage, networking, quorum, and the application support that topology. Pods can stay Pending if zonal storage resides in the wrong AZ or if no nodes have sufficient capacity.

## 6. Stateful Workloads Require Cluster-Aware Applications

Attaching multiple Pods to PVCs does not turn an application into a distributed system. A database, broker, or search cluster typically has its own protocols for leader election, sharding, data synchronization, commit acknowledgement, and handling disconnected nodes.

Before deploying, review the engine's documentation on:

- Minimum replica count and quorum rules.
- Node identity, cluster membership, and peer discovery.
- Synchronous vs. asynchronous replication; lag and write acknowledgements.
- Leader election, fencing, and preventing split-brain dual writers.
- Behavior during Pod restarts, volume reattachment, and slow node startups.
- Procedures for adding/removing replicas and resizing capacity.
- Crash recovery, upgrade protocols, and version rollbacks.

An **Operator** can automate the lifecycle of a stateful application: creating clusters, configuring replicas, upgrading, backing up, or failing over using engine-specific logic. Still, an operator is only helpful when supported, properly configured, least-privilege, and backed by runbooks. CRDs/operators do not turn fragile storage into durable storage, nor do they replace testing backups and restores.

### Quorum and Replica Counts

Many consensus systems use majority quorum. With \(N\) voting members, a majority is typically:

\[
Q=\left\lfloor\frac{N}{2}\right\rfloor+1.
\]

With three voting members, quorum is two; the system can tolerate losing one member if the remaining two can still communicate and satisfy protocol rules. With two voting members, quorum is still two, meaning losing one member can prevent the cluster from making progress. This is a common model, though **it does not apply blindly to every database/broker**; some systems use witnesses, voter/non-voter roles, replica roles, or other consensus algorithms.

Do not place three replicas across three AZs just to "have three Pods." Ensure:

- Voters reside in genuinely independent failure domains.
- Inter-member network paths are stable and policies permit required peer traffic.
- Each replica's storage meets latency and durability targets.
- Quorum is preserved during concurrent maintenance or upgrades.
- Applications/clients track writer/leader endpoints and handle failover transitions.

### StatefulSet Is Not a Replication Mechanism

StatefulSet creates ordinal identities like `node-0`/`node-1`/`node-2` and per-ordinal volume claims from templates. It does not replicate data across volumes. If a database cluster needs replication, the database engine or operator must perform it; if a PVC is lost, you cannot rely on StatefulSet to recover data on its own.

## 7. Durability, Replication, Snapshots, and Backups Are Separate Layers

A high-durability volume protects data on the device against certain hardware faults, but does not cover every failure mode:

| Mechanism | Purpose | What It Does Not Replace |
| --- | --- | --- |
| Internal storage durability/replication | Protects against hardware loss per storage service design | Accidental deletion, logical bugs, ransomware, app errors |
| Database replication | Maintains data copies for failover/read scaling | Independent historical backups or pre-corruption recovery |
| Volume snapshots | Captures block/file state at a point in time per storage semantics | App-aware consistency, long-term retention, restore testing |
| Database-native backups | Saves logical/physical engine copies, possibly including logs/metadata | Backup accessibility if shared permissions or regions are compromised |
| Point-in-time recovery (PITR) | Restores to a moment prior to a logical error within retention | Zero recovery time or automatic resolution of all corruption types |

### Crash Consistency vs. Application Consistency

Storage snapshots may only guarantee block-level/crash-consistent states per service capabilities. An active database may hold unflushed dirty pages in memory, uncheckpointed transaction logs, or span multiple volumes that must be captured together. A single-volume snapshot is not automatically **application-consistent**.

To capture consistent backups:

1. Use database/engine-integrated backup tools or snapshot APIs when available.
2. When needed, flush/quiesce or briefly pause writes using supported procedures.
3. For engines supporting online backups, capture required checkpoints/LSNs and transaction logs.
4. When data spans multiple volumes, use consistent snapshot groups or coordinated workflows.
5. Verify checksums, metadata, retention, and access permissions post-backup.

Never pause processes or freeze filesystems arbitrarily without understanding the engine's mechanics. Improper backup procedures can produce unusable snapshots or disrupt production traffic.

### RPO, RTO, and Backup Policies

- **RPO (Recovery Point Objective):** maximum age of data an organization can tolerate losing in a defined incident.
- **RTO (Recovery Time Objective):** target duration to restore usable service after an incident.
- **Retention:** how long backups/snapshots are kept, aligned with compliance and recovery needs.
- **Backup isolation:** backups require separate permissions, accounts, or locations so production incidents or compromises cannot easily delete backups too.
- **Restore validation:** periodic testing verifying data can be restored and actually opened/read/written by the application.

Illustrative policy for a transactional database: daily snapshots retained 14 days, daily logical backups retained 30 days, continuous logs for PITR retained 7 days, and periodic copies stored in another region. These intervals are not universal defaults; calculate them from RPO/RTO, data volume, change rate, regulatory mandates, and cost.

### Snapshots Are Not Backups

Snapshots may live under the same account, permissions, or region as the source volume. A user authorized to delete volumes might also delete snapshots if policies are not separated. For critical data, consider independent backups, immutable retention, or separate vaults where supported. Most importantly, rehearse restores and measure elapsed time.

## 8. Storage Topology and Multi-Availability Zone Design

Cloud block volumes usually have a specific **zone/AZ scope**. A volume in AZ A can typically only attach to nodes able to reach that volume per service/driver capabilities; a Pod cannot freely move to AZ B if the volume cannot attach there. File storage may span multiple AZs or have its own topology; object storage is typically an API service with regional/zonal durability published by the provider. Always verify the actual model for each service.

### Two Common Patterns

**One zonal volume per replica:** A StatefulSet provisions a dedicated PVC per Pod in the matching zone. The database engine replicates data across replicas in multiple AZs. When an AZ fails, replicas in surviving AZs continue via engine failover. This is a common pattern for stateful clusters, though quorum and replication lag must be accounted for.

**One shared filesystem across multiple nodes:** Multiple Pods or nodes mount the same file share when the application and file protocol support multi-client access. Account for locking, concurrency, throughput, and failover. Shared filesystems do not replace database replication or transactions when strong data invariants are required.

~~~mermaid
flowchart TB
    subgraph AZA["Availability Zone A"]
      P0["Pod database-0"]
      V0["PVC/PV A"]
      P0 --> V0
    end
    subgraph AZB["Availability Zone B"]
      P1["Pod database-1"]
      V1["PVC/PV B"]
      P1 --> V1
    end
    subgraph AZC["Availability Zone C"]
      P2["Pod database-2"]
      V2["PVC/PV C"]
      P2 --> V2
    end
    P0 <-->|"Database replication"| P1
    P1 <-->|"Database replication"| P2
    P0 <-->|"Database replication"| P2
~~~

The diagram illustrates replicas with independent volumes and database-layer replication. It **does not** show a single volume mounted concurrently across three AZs. Each node must maintain its own identity and data per engine rules; attaching separate volumes does not synchronize data automatically.

### What Happens When an AZ Containing a Volume Fails?

Distinguish four cases:

1. **Pod fails while volume stays healthy:** the controller recreates the Pod, the scheduler places it on a node capable of attaching the volume, and the engine recovers.
2. **Node fails while volume survives:** detach/attach may need confirmation that the old node stopped writing; fencing or safe detach depends on the cloud provider/CSI.
3. **AZ fails:** zonal volumes may become unreachable for the duration of the outage. Replacement Pods in other AZs cannot attach that volume; the database must fail over to a replica with its own volume in a healthy AZ.
4. **Volume or data corruption:** requires a healthy replica or backup restore; spinning up a new Pod mounted to the same corrupted volume will not repair data.

Never force a Pod into a zone unable to reach its data just to make the scheduler show it Running. **Data correctness and single-writer ownership matter more than Pod Running status.**

## 9. Choosing Storage Performance and Sizing

Capacity is not the only metric. Quantify:

- **IOPS:** input/output operations per second.
- **Throughput:** bytes read/written per second.
- **Latency:** I/O completion time, focusing on p95/p99.
- **I/O size and pattern:** 4 KiB random, 256 KiB sequential, or the engine's actual access pattern.
- **Read/write ratio:** proportion of reads vs. writes, sync writes, `fsync`, and checkpoints.
- **Burst behavior:** whether throughput/IOPS bursts rely on finite credits or limits.
- **Capacity growth:** data growth, indexes, WAL/logs, temporary space, and backups.

Example: a database workload drives 8,000 IOPS (70% read, 30% write) with an average I/O size of 16 KiB. Rough raw throughput estimate:

\[
8,000\times16\text{ KiB}=128,000\text{ KiB/s}\approx125\text{ MiB/s}.
\]

This is only a multiplication of IOPS by assumed I/O size; it omits write amplification, metadata, latency, caching, filesystem overhead, and engine batching. Benchmark storage under realistic workloads with production-matching durability settings.

### Capacity Sizing

A simple planning formula:

\[
\text{Required capacity}
= \text{Current data}
+ \text{Growth over period}
+ \text{Index/log/temp}
+ \text{Headroom}.
\]

For example, with 200 GiB of existing data growing at 8 GiB/week planned over 26 weeks, plus 25% for indexes/logs/temp and 20% headroom:

\[
(200+8\times26)\times1.25\times1.20
=612\text{ GiB}.
\]

This calculation assumes steady growth and uses illustrative multipliers; in practice, measure database growth, retention, log rotation, vacuum/compaction, snapshots, and how storage billing charges provisioned capacity. Never provision capacity exactly equal to current usage, or checkpoints, compaction, and recovery operations may run out of temporary space.

### Increasing Size or Changing StorageClass

Expanding volumes often comes with limits and preconditions:

- Does the StorageClass/CSI driver support volume expansion?
- Does the filesystem resize online or require node-level actions?
- Can volumes only grow, never shrink?
- Are there downtime risks, detach/attach cycles, or topology changes?
- Does storage performance scale with provisioned size or configure independently?
- Are pre-resize backups/snapshots required by policy?

Never modify PVCs/StorageClasses in production without understanding controller reconciliation and resize support. For critical databases, plan capacity expansions well before hitting thresholds.

## 10. Securing Persistent Storage

Persistent volumes outlive individual Pods, so data lifecycles and access permissions must be governed as independent assets.

### Encryption at Rest and in Transit

- Encrypt volumes/snapshots with properly managed keys; define permissions for key creation, usage, rotation, and revocation.
- Encrypt traffic between applications and databases/file services, between replicas, and between CSI/nodes and storage backends where required.
- Cross-region backups and replicas must also be encrypted, access-controlled, and tested for decryption during restores.
- Distinguish storage-provider encryption from database/application-layer encryption; both layers serve different purposes and key models.

### Least Privilege and Isolation

1. Only required service accounts/workload identities may manage PVCs, snapshots, or storage APIs.
2. Never allow every namespace/team to create snapshots/clones or delete volumes.
3. Use namespaces, cloud accounts/projects, storage policies, and key policies to separate production from non-production.
4. Avoid storing database secrets, encryption keys, or long-lived credentials in plaintext inside images or manifests.
5. For shared file storage, scope permissions by directory/identity; never open cluster-wide RWX when only one workload writes.
6. Audit create/attach/detach/resize/snapshot/delete and backup/restore operations; alert on unexpected production volume deletions.

### Security Context and Filesystem Permissions

Containers can run with non-root users, read-only root filesystems, and least-privilege volume mounts when applications support them. Check UID/GID, `fsGroup`, ownership, SELinux/AppArmor, or platform equivalents. Never fix permission errors with broad `chmod 777`; that allows any process to write and increases data corruption risk.

For sensitive workloads, check who can `exec` into Pods, access nodes, and reach the host; snapshot permissions can also leak data even if a user cannot query the database directly. Backups require independent access controls.

## 11. Volume Lifecycle: Provision, Attach, Mount, Detach, and Reclaim

Storage has a lifecycle independent of Pods:

~~~mermaid
stateDiagram-v2
    [*] --> Requested: PVC created
    Requested --> Provisioned: PV provisioned
    Provisioned --> Bound: PVC/PV bound
    Bound --> Attached: Attached to node
    Attached --> Mounted: Mounted into Pod
    Mounted --> Detached: Pod/node stopped
    Detached --> Attached: Replacement Pod
    Detached --> Retained: PVC deleted / Retain
    Detached --> Deleted: PVC deleted / Delete
    Retained --> Bound: Reclaimed / rebound per process
    Deleted --> [*]
~~~

This diagram shows a generalized lifecycle. In practice, controllers may execute steps concurrently; detaching can stall when a node becomes unresponsive, and storage policies may hold resources in intermediate states.

### Operational Touchpoints

| Operation | Operational Question |
| --- | --- |
| Provision | Is quota available? Are StorageClass and AZ correct? |
| Bind | Did the PVC bind to the expected PV and attributes? |
| Attach | Was the volume safely detached from the old node? Are per-node attach limits respected? |
| Mount | Are the filesystem, user permissions, and mount options valid? |
| Expand | Do the driver and filesystem support capacity expansion? |
| Snapshot | Did the app quiesce/checkpoint if needed? What are retention and consistency? |
| Detach | Did the Pod flush data and close file handles? Has the node stopped writing? |
| Reclaim/delete | Could deleting a PVC wipe a production volume or backup? |
| Restore | Can data be restored into an isolated environment and verified? |

### Avoiding Split-Brain When Reattaching Volumes

If an old node loses contact with the control plane yet can still write to storage, attaching the same volume to a new node without fencing can create **two simultaneous writers**. Platforms typically have attach/detach and fencing mechanics, but exact behavior varies by driver/cloud. Never force-detach/reattach without confirming the old node has stopped writing and that the provider/engine recovery procedure permits it.

In certain outages, waiting for a clean detach takes longer yet protects data integrity. Runbooks must specify when manual intervention is allowed, who approves it, and how to verify the filesystem/database afterward.

## 12. Observing and Troubleshooting Stateful Workloads

Stateless applications can often swap Pods quickly; stateful workloads require monitoring **processes, Pods, storage, nodes, replication, and data** together.

| Layer | Metrics / Signals to Observe | Risk Indicators |
| --- | --- | --- |
| Pod/process | Restart count, OOMKilled, Pending, readiness, startup duration | Crash loops, resource exhaustion, slow volume mounts |
| Storage | Used capacity, free space, IOPS, throughput, latency, queue depth | Nearing full, throttling, rising p99 I/O latency |
| CSI/node | Attach/detach errors, mount timeouts, node conditions, driver health | Pending Pods, stuck volumes, node plugin failures |
| Database/engine | Replication lag, quorum, leader changes, WAL/log growth, recovery time | Stale replicas, split-brain, inability to commit |
| Backup | Last successful backup, snapshot age, PITR log continuity, restore tests | RPO breached, unreadable/undecryptable backups |
| Queue/broker | Disk usage, unacked messages, segment retention, consumer lag | Blocked messages, disk full, growing backlog |

### Common Scenarios and Responses

**PVC Pending:** inspect StorageClass, quotas, CSI provisioner, binding mode, CIDR/zone topology, and node selectors. Never change storage classes blindly, as doing so may provision volumes in the wrong location.

**Pod fails to mount volume:** check attach state, node plugins, volume/filesystem permissions, zone, and PVC/PV events. Never force-mount while the old node could still be writing.

**Volume nearly full:** identify whether growth comes from logs, WAL, indexes, temporary files, or retention; clean up following engine guidance and expand volumes via approved workflows. Never delete database data files or transaction logs directly while the database is running.

**Rising I/O latency:** check queue depth, IOPS/throughput quotas, I/O sizes, burst credits, noisy neighbors, compaction, and database query patterns. Expanding volume size only helps if performance tiers scale with size and disk is the real bottleneck.

**Replica lag or lost quorum:** protect the writer, identify surviving nodes, inspect WAL/log status, and verify committed data. Follow database/operator runbooks; never start multiple replicas holding stale data as simultaneous writers.

**Repeated backup failures:** check snapshot permissions, storage quotas, networking, encryption keys, PITR log chains, and volume status. A failing backup job must be resolved before RPO policies are breached.

## 13. Rehearsable Backup and Restore Procedures

A strong backup policy must translate into repeatable operational procedures and verified recovery evidence.

### Before Backing Up

1. Classify data and define criticality, owners, and RPO/RTO.
2. Decide between storage-layer backups, database-native backups, or both; review engine recommendations.
3. Determine checkpoint/quiesce timing or log positions if consistency is required.
4. Verify capacity, snapshot permissions, keys/encryption, retention, and storage locations.
5. Design monitoring to detect failed or overdue backups.

### During Restoration

1. Provision an isolated recovery environment; never overwrite production without explicit approval.
2. Select the snapshot/backup and logs matching the target recovery point.
3. Provision target volumes or databases with proper permissions and encryption keys.
4. Execute engine recovery: replay logs, inspect cluster metadata, and restore in order.
5. Validate schemas, checksums/integrity, record counts, business data, and read/write functionality.
6. Measure total recovery duration and data loss against RTO/RPO.
7. Record findings, update runbooks, and fix any failing steps.

### Restore Testing Matters More Than Counting Green Backups

A backup may exist yet fail to restore due to revoked keys, missing metadata, broken log chains, incompatible engine versions, or wrong permissions. Rehearse restores periodically and prove **the application can actually use the restored data**, not just that a volume was created.

## 14. Upgrading Stateful Workloads and Data Schemas

New container images can swap Pods quickly, yet database schemas and on-disk formats may **not be backward-compatible**. Performing a rolling update on a StatefulSet while nodes run mismatched versions risks corrupting the cluster or breaking rollbacks.

Before upgrading:

- Check compatibility matrices across engine versions, operators, CSI drivers, and storage formats.
- Back up and rehearse restores targeting the destination version.
- Verify replication protocols and leader/follower upgrade ordering.
- Allow time for migrations or compaction; never assume a simple Pod restart is enough.
- Configure appropriate update strategies; partitioned rollouts or operator-orchestrated workflows may be required.
- Verify health, quorum, replication lag, and data integrity at every step.

### Expand–Migrate–Contract for Schemas

1. **Expand:** add new fields/indexes/structures that remain compatible with the running version.
2. **Migrate:** update the application to read/write the transitional structures; backfill in batches.
3. **Validate:** reconcile data and measure error rates.
4. **Contract:** drop old structures once no consumers or old versions depend on them.

This pattern reduces risk during simultaneous deployments while Pods run mixed versions. Large data migrations can still spike I/O and lock durations; benchmark against production-like datasets.

## 15. Case Study: Containerized PostgreSQL for a Booking Application

Suppose a booking platform needs to persist bookings and payment references. The operations team wants to run PostgreSQL inside Kubernetes to standardize the platform; illustrative requirements:

- Relatively steady read/write load with campaign-driven bursts.
- Near-zero RPO target for confirmed transactions within a single-AZ outage scenario.
- Cross-region recovery capability within agreed RTO/RPO.
- Database requires block storage with consistent IOPS.
- Application Pods must not access volumes directly; apps connect strictly over the database protocol.

### Structural Choices

One approach deploys three database members, each with its own block-volume PVC, spread across three AZs if supported by the cluster and region; a headless Service handles peer discovery, while separate Services provide role-aware writer/read endpoints. The database engine or operator manages replication, leader election, and failover. Logical backups/PITR archives reside in separate storage with cross-region copies for DR.

Diagram:

~~~mermaid
flowchart TB
    APP["Booking API pods"]
    WRITER["Writer endpoint / Service"]
    subgraph AZ1["AZ A"]
        DB0["PostgreSQL member 0"]
        VOL0["Block volume A"]
        DB0 --- VOL0
    end
    subgraph AZ2["AZ B"]
        DB1["PostgreSQL member 1"]
        VOL1["Block volume B"]
        DB1 --- VOL1
    end
    subgraph AZ3["AZ C"]
        DB2["PostgreSQL member 2"]
        VOL2["Block volume C"]
        DB2 --- VOL2
    end
    APP --> WRITER
    WRITER --> DB0
    DB0 <-->|"Replication protocol"| DB1
    DB1 <-->|"Replication protocol"| DB2
    DB0 <-->|"Replication protocol"| DB2
    BACKUP["Backup / PITR archive"]
    DB0 --> BACKUP
~~~

This diagram is an illustrative structure, **not a production-ready configuration**. PostgreSQL does not become HA simply by deploying three Pods in a StatefulSet; it requires a specific clustering/operator architecture, replication mode, witness/quorum, fencing, connection routing, backups, and tested failover. For strict requirements, a managed database service can supply these capabilities with lower operational burden; compare both options before self-hosting.

### Booking Write Flow

Applications call the writer endpoint over TLS using least-privilege credentials/identities. The database commits transactions per configured durability settings. With synchronous replication, define which replicas must acknowledge commits and how quorum loss is handled; with asynchronous replication, quantify replication lag and potential data loss on failover. APIs use idempotency keys to handle retries after timeouts.

### When the Writer Pod Fails

The operator or cluster manager detects the failure, evaluates surviving members, and elects/promotes a new leader per protocol. The writer Service/endpoint updates to the new member, and API connection pools reconnect. Tests must measure time until the API resumes successful booking writes and verify confirmed transactions are neither lost nor duplicated.

### When the AZ Holding the Writer's Volume Fails

Zonal volumes in the failed AZ cannot attach to another AZ. The cluster must pick a sufficiently caught-up replica in a healthy AZ, promote it per rules, and fence the old Pod so the former writer cannot resume writes. Actual RPO depends on replication mode and commit acknowledgements. Provisioning a blank volume cannot substitute for database replication.

### Logical Data Corruption or Accidental Deletion

Replicas can immediately replay a mistaken `DELETE`. Operations selects backups/PITR prior to the mistake, restores into an isolated cluster, validates legitimate transactions, and reconciles transactions recorded after the recovery point. This is why replication and backups must be designed independently.

### Should You Self-Host Databases in Kubernetes?

Compare against managed databases:

| Criterion | Self-Operated DB in Kubernetes | Managed Database |
| --- | --- | --- |
| Control | Greater control over engine, extensions, scheduling, and storage layout | Constrained by product features and limits |
| Operations | Team owns operators, versions, backups, failover, and on-call | Provider manages underlying infra tasks; customer still manages schemas, permissions, and data |
| Storage | Chooses CSI, topology, volumes, and policies directly | Integrated storage/HA managed by the service |
| Flexibility | Deep customization possible | May restrict versions, extensions, and host-level access |
| Risk | Misconfigured operators, PVCs, quorum, restores, or upgrades can break recovery | Dependent on provider SLAs, quotas, APIs, and processes |
| Total cost | Compute + storage + engineering/on-call + monitoring + backups | Service fees + storage + transfer + backups + auxiliary limits |

If the team lacks experience operating database clusters, the convenience of standardizing on Kubernetes may not justify the data risk. Managed databases are often worth considering for critical transactional data; self-hosting fits when specialized control requirements exist and the team proves end-to-end operational capability.

## 16. Migrating Stateful Workloads into Containers

Containerizing stateful applications is more complex than packaging stateless APIs because data, identity, networking, and storage topology may be coupled to legacy hosts.

### Step 1 — Inventory Data and Dependencies

Document data directories, logs, caches, temp files, config files, secrets, network ports, existing volumes, replication, backups, and data-touching cron/jobs. Classify:

- Business data that must be preserved.
- Data that can be rebuilt from other sources.
- Caches and temp files that can be discarded.
- Logs requiring retention or forwarding to a logging platform.
- Cluster/identity metadata requiring dedicated migration steps.

Never mount an old server's raw directory straight into a container without verifying ownership, permissions, mount options, and filesystem semantics.

### Step 2 — Choose an Operational Model

Evaluate managed databases, supported operators, or self-managed StatefulSets. Review SLAs, extensions, versions, networking, compliance, backup capability, on-call staffing, upgrade windows, and cluster expertise. StatefulSets should not be treated as mandatory simply because other workloads run on Kubernetes.

### Step 3 — Standardize Storage and Security

Choose block/file/object per engine; configure StorageClasses, encryption, reclaim policies, topology, quotas, and volume sizes. Configure service accounts, secrets, security contexts, ingress/egress, and isolated backup targets.

### Step 4 — Build a Production-Like Test Environment

Load representative data and test IOPS, throughput, latency, access permissions, Pod restarts, node drains, rescheduling, volume detach/attach, backups, and restores. Confirm the application runs against matching engine versions and real schemas.

### Step 5 — Synchronize Data and Migrate

Approaches include backup/restore, replication between old and new sources, or batched migration. Define cutover windows, freeze writes if needed, check replication lag, reconcile row counts/checksums, and set rollback criteria. For transactional data, identify the single source of truth at each phase and how transactions during the cutover window are handled.

### Step 6 — Reversible Cutover

Shift traffic in waves or controlled windows, verifying reads/writes and metrics. Never let both old and new systems accept writes concurrently unless designed for multi-writer conflict resolution. Keep the legacy source in a reconcilable state per plan while preventing unintended traffic from hitting it.

### Step 7 — Post-Cutover Operations

Closely monitor storage, replica lag, quorum, backups, restores, latency, capacity, and costs during heightened observation. Update runbooks, on-call rotations, patch/upgrade procedures, and ownership.

## 17. Well-Architected Multi-Pillar Evaluation

| Pillar | Questions for Stateful Containers | Required Evidence |
| --- | --- | --- |
| **Reliability** | When a Pod/node/AZ fails, how are data and the writer recovered? | Replication, fencing, RTO/RPO, restore/failover tests |
| **Security** | Who can read volumes, snapshots, backups, and keys? | IAM, encryption, audits, network policies, secret rotation |
| **Performance** | Does storage meet IOPS/throughput/p99 targets during compaction and peak load? | Benchmarks, storage telemetry, load tests |
| **Cost optimization** | Are provisioned volumes, snapshots, replicas, backups, and egress appropriate? | Cost per GB/IOPS/job, retention, capacity forecasts |
| **Operational excellence** | Who owns patching, upgrades, backups, restores, and stuck-volume recovery? | Runbooks, alerts, automation, owners, drills |
| **Sustainability** | Are capacity and replicas sized efficiently, avoiding chronic overprovisioning? | Utilization, lifecycle policies, right-sizing, safe deletion |

An architecture with three replicas across three AZs is insufficient if backups cannot be restored. High-IOPS volumes mean nothing if the database misconfigures `fsync`. An operator promising automatic failover does not prevent split-brain unless fencing is verified. Evaluate **end-to-end** from application down to data and operational procedures.

## 18. Common Mistakes

1. **Storing primary data in the container's writable layer:** replacing the container loses the data.
2. **Equating PVCs with backups:** volumes survive Pod restarts, yet remain vulnerable to accidental deletion, corruption, or ransomware.
3. **Assuming StatefulSet handles replication:** StatefulSet only manages identity/storage association; the engine/operator must implement data protocols.
4. **Confusing RWO with "single Pod":** semantics are typically node-scoped; distinguish from RWOP and check CSI behavior.
5. **Treating RWX as safe multi-writer by default:** file locking and concurrency logic must still be handled by the application/filesystem.
6. **Misplacing zonal volumes:** Pods get scheduled into an AZ unable to attach the volume.
7. **Sharing one block volume across multiple database replicas:** risks split-brain and corruption without supported cluster/filesystem architectures.
8. **Scaling Pods without accounting for storage/networking:** adding replicas multiplies IOPS, connections, replication traffic, and cost.
9. **Ignoring storage latency:** insufficient IOPS or rising queue depth can spike database p99 latency even while CPU stays low.
10. **Taking snapshots while the database is inconsistent:** snapshots exist yet fail database recovery.
11. **Deleting PVCs to tidy up resources:** may trigger a `Delete` reclaim policy and wipe backend volumes.
12. **Force-detaching before fencing the old node:** two writers can corrupt the same data.
13. **Never rehearsing restores:** green backup jobs do not prove data is recoverable.
14. **Upgrading engines and changing storage simultaneously:** changing multiple variables in one release complicates rollbacks and root-cause analysis.

## 19. Practice Exercise and Guided Answers

A team deploys Redis and PostgreSQL on Kubernetes:

- PostgreSQL holds 500 GiB of data, requiring durable writes and a maximum RPO of 5 minutes in a single-AZ failure scenario.
- Redis serves as a regenerable cache; cached data is not a source of truth.
- PostgreSQL requires at least 8,000 IOPS and low write latency.
- Three AZs are available; the app team plans to deploy three database replicas using a StatefulSet.
- Backups must be retained for 30 days and restorable within 60 minutes.

### Question 1 — Which Workload Needs Persistent Volumes?

**Guided answer:** PostgreSQL requires durable storage, typically block volumes or managed database storage per engine guidelines. A Redis cache can run on ephemeral memory if cache loss is acceptable and it can be rebuilt; if Redis holds queues, sessions, or non-regenerable state, it requires its own persistence/HA design aligned with its actual role.

### Question 2 — Can One RWO PVC Be Attached to All Three PostgreSQL Pods?

**Answer:** No. The standard design gives each database member its own storage, while the engine replicates data between members. RWO is not a record-distribution mechanism and does not synchronize databases automatically.

### Question 3 — Do Three StatefulSet Pods Guarantee a 5-Minute RPO?

**Answer:** Not yet. You must select appropriate replication modes and commit acknowledgements, verify replication lag, quorum, failover, fencing, and committed data. Test an AZ outage and measure actual data loss. StatefulSet only manages Pod/volume identity orchestration.

### Question 4 — What Minimum Storage Metrics Must Be Benchmarked?

**Answer:** 8,000 IOPS at representative I/O sizes, throughput, p95/p99 latency, read/write ratio, `fsync` behavior, queue depth, burst behavior, and performance during concurrent backups/compaction. Also verify capacity and headroom for WAL, indexes, and temporary space.

### Question 5 — Do Daily Volume Snapshots Meet 30-Day Retention and 60-Minute Restore?

**Answer:** Not enough information to conclude yes. Verify snapshot consistency, retention count, required PITR logs, storage regions, encryption keys, restore bandwidth, and database startup/validation duration. You may need database-native backups or combined snapshots plus logs; run an actual restore drill to measure real times.

### Question 6 — Pod `PostgreSQL-0` Hits a Node Failure, and the Scheduler Tries Another AZ. What Must Be Checked?

**Answer:** Whether the volume is zonally constrained, whether the old node has been safely fenced/detached, whether the volume can attach in the new AZ, PVC binding mode, and scheduler constraints. If the volume cannot move across AZs, the cluster must fail over to a replica holding its own volume in another AZ per engine protocol.

### Question 7 — Is Deleting PVCs Safe for Cleaning Up Staging?

**Answer:** Check the reclaim policy, PV/backend volume, `ownerReference`, snapshots, and data purpose first. If the policy is `Delete`, deleting the PVC can wipe the backend volume. Data that must be kept should be backed up or handed off before deletion.

### Question 8 — When Should You Choose a Managed Database Over PostgreSQL on StatefulSet?

**Guided answer:** When the organization lacks on-call expertise to operate database clusters, requires high HA/backup/restore reliability, and a managed service satisfies engine/version/network/compliance needs, a managed database reduces risk and effort. Self-managed fits when deep customization is required and the team has proven end-to-end operational capability.

## 20. Pre-Production Review Checklist for Stateful Containers

- Is it clearly defined which data is ephemeral, which is persistent, and where the source of truth lives?
- Does the storage type (block/file/object) match access patterns and engine requirements?
- Do PV/PVC/StorageClass/CSI drivers satisfy access modes, topology, resize, and quotas?
- Do the StatefulSet/operator provide proper identity and protocols, and have quorum/fencing been tested?
- Are Pods and volumes distributed across failure domains with sufficient capacity when an AZ fails?
- Have IOPS, throughput, latency, capacity growth, and headroom been benchmarked?
- Are encryption, key policies, workload identity, security contexts, and auditing configured?
- Do backups, snapshots, retention, PITR, and restore tests meet RPO/RTO?
- Do runbooks cover PVC Pending, stuck attach/detach, full volumes, replica lag, and restores?
- Have upgrades, schema migrations, rollbacks, and cutovers been tested?
- Are provisioned volumes, replicas, snapshots, backups, data transfer, and operational costs accounted for?
- Are owners, dashboards, alerts, and periodic drill schedules established?

A well-designed stateful container architecture proves more than just Pods running and volumes mounting. It proves that data is **accurate, durable, protected, recoverable within targets, and operable through real failure scenarios**.
