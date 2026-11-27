# Ephemeral Filesystems and Persistent Storage for Containers

Containers are routinely created, stopped, replaced, and rescheduled throughout an application's lifecycle. Consequently, data written inside a container is not automatically durable. A file created in a container's filesystem can vanish when the container is deleted or replaced with a new container, even if the application keeps the same name and image.

Designing storage for containers requires separating ephemeral data from data that must survive across the workload lifecycle. Caches, intermediate files, and scratch data can live in ephemeral storage; databases, user files, checkpoints, and business data must be stored in volumes or storage services with appropriate durability.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module, chapter **Container Fundamentals**. It covers writable layers, ephemeral filesystems, `tmpfs`, bind mounts, Docker volumes, Kubernetes `emptyDir`, `PersistentVolume`/`PersistentVolumeClaim`, CSI, performance, security, backups, and choosing storage by data lifecycle.

## 1. Why Must Container Filesystems Be Designed Separately?

Containers are designed to be replaceable. A deployment can create new Pods when a node fails, an image is updated, or replicas scale. If critical data resides solely inside the container's local filesystem, replacing the container can result in data loss.

Common scenarios:

- A container restarts after its main process exits or crashes.
- A Pod is deleted and recreated on a different node.
- A Deployment rolling update replaces old Pods with new ones.
- A node is drained, maintained, or loses connectivity.
- An autoscaler scales in a node hosting the Pod.
- A container image is updated and spawns a new instance.

Not every operation causes immediate data loss. A container restart inside the same Pod may still see certain Pod volumes; however, the old container's writable layer is usually discarded when the container is recreated. A new Pod may be scheduled onto another node, so it cannot rely on the previous node's local filesystem.

### 1.1. Classify Data Before Choosing Storage

| Data Type | Examples | Typical Requirements |
|---|---|---|
| Runtime scratch | Temporary files created while handling a request | Can be deleted after processing |
| Cache | Application cache, regenerable downloaded content | Can be lost and rebuilt |
| Logs | Application or audit logs | Should be shipped to a durable logging system |
| Sessions | Login state or shopping cart | Prefer tokens or a shared store |
| User uploads | User images, documents | Requires durability, backups, and access controls |
| Databases | Tables, transactions, indexes | Requires consistency, backup, restore, and HA |
| Checkpoints | Batch or model training progress | Must be stored durably to resume |
| Artifacts | Build outputs, packages, or processing results | Requires retention and versioning |

Ask three questions before selecting a storage location:

1. Can the data be regenerated from another source?
2. Must the data survive a container restart, a Pod replacement, or a node/zone failure?
3. What are the maximum acceptable data loss and recovery time?

## 2. Container Filesystem Layers

Container images are typically built from multiple immutable filesystem layers. When a container runs, the runtime creates a writable layer on top of the image layers. The exact mechanism depends on the container runtime and storage driver; on Linux, OverlayFS is a common implementation.

~~~mermaid
flowchart TB
    W["Container writable layer"] --> I["Image layer 3"]
    I --> J["Image layer 2"]
    J --> K["Image layer 1"]
    K --> B["Base image"]
    W --> V["Mounted volume / bind mount"]
    W --> T["Temporary filesystem / tmpfs"]
~~~

Image layers are shared and typically read-only. The writable layer records container-specific changes such as new, modified, or deleted files. When a container is removed, its writable layer is usually discarded. Image layers remain in the local image cache until pruned.

### 2.1. Copy-on-Write

When an application reads a file from an image layer, the runtime can read directly from the read-only layer. When the application modifies that file, copy-on-write can copy the file up into the writable layer and apply changes there.

This allows multiple containers to share image layers without altering the base image. However:

- Writing heavy volumes of data to the writable layer increases disk consumption and I/O.
- Modifying large files can incur copy-up overhead.
- Data in the writable layer is tied to the container's lifecycle.
- Never use the writable layer to store databases or long-lived business files.

### 2.2. Files in the Image vs. Runtime Files

Files packaged in the image suit source code, libraries, binaries, and immutable default configurations. Data generated at runtime should go into an appropriate volume or storage service.

Do not write runtime files into a source code directory if that directory comes from the image without its own volume. Doing so can:

- Fail if the filesystem is mounted read-only.
- Create data trapped inside the writable layer.
- Get shadowed if a volume is mounted over the same path.
- Make images harder to reuse and state harder to manage.

## 3. Distinguishing Storage Types

| Storage Type | Typical Lifecycle | Used For |
|---|---|---|
| Writable layer | Tied to the container | Ephemeral runtime changes not meant to persist |
| `tmpfs` / memory-backed volume | Tied to container or Pod depending on runtime | Speed-sensitive scratch and temporary data |
| Docker named volume | Independent of container; persists until deleted | Local databases or files retained on the host |
| Bind mount | Tied to a host path | Development, config, or host data integration |
| Kubernetes `emptyDir` | Tied to the Pod lifecycle | Scratch shared across containers in a Pod |
| Kubernetes ephemeral volume | Tied to Pod or corresponding volume mechanism | Ephemeral storage provisioned by CSI |
| `PersistentVolume` | Governed by PV/storage lifecycle policy | Data that must outlive the Pod |
| Object storage | Governed by bucket/object retention | Files, artifacts, backups, and unstructured data |

The term "persistent" must be understood within its specific scope. A Docker volume outlives a container yet still depends on the host; a Kubernetes PV outlives a Pod yet may live in a single AZ or be deleted under its reclaim policy. Explicitly define the failure domain your data must survive.

## 4. Writable Layer: Temporary Storage Tied to the Container Lifecycle

The writable layer fits temporary files needed only while the container exists. Examples:

- PID files or runtime sockets.
- Small regenerable caches.
- Intermediate files for a short-lived request.
- Process-local temporary data not shared with other containers.

Do not store:

- Production databases.
- Unique user-uploaded files.
- Single copies of audit logs.
- Single copies of long-running job checkpoints.
- Long-lived secrets or keys.

### 4.1. What Happens When a Container Restarts?

Distinguish restarting a process from creating a new container:

- If a process inside the same container restarts, the writable layer still belongs to that container and generally remains intact.
- If the runtime deletes the old container and creates a new one from the image, the old writable layer does not carry over automatically to the new container.
- If a Pod is replaced, the new container does not use the old Pod's writable layer.

Docker or Kubernetes restart policies do not turn the writable layer into durable storage. Always check which operation is occurring: process restart, container restart, container recreation, or Pod replacement.

## 5. `tmpfs` and In-Memory Storage

`tmpfs` is a filesystem storing contents in memory, potentially backed by RAM and swap depending on OS configuration. It fits temporary data requiring fast access or data that should not be written to disk.

Examples:

- Temporary files holding intermediate data.
- Regenerable caches.
- Sensitive files that should avoid landing on standard disk.
- Application sockets or scratch data.

`tmpfs` is not durable storage. Contents are typically lost when the mount is unmounted, the container/Pod terminates, or the machine reboots.

### 5.1. Memory Limits

`tmpfs` consumes host memory or memory within the cgroup scope. Without a cap, temporary data can compete with the application for RAM. Inside containers, inspect memory limits and matching `tmpfs` settings.

In Kubernetes, a memory-backed `emptyDir` can count toward the Pod's memory usage. If temporary data grows excessively, the container may be OOMKilled or the Pod impacted by memory pressure.

### 5.2. Docker `tmpfs`

~~~bash
docker run --rm \
  --mount type=tmpfs,destination=/run/cache,tmpfs-size=64m \
  my-worker:1.0
~~~

This example mounts a `tmpfs` capped at 64 MiB at `/run/cache`. Exact syntax and options depend on the Docker version and host platform. Never write data requiring recovery to this path.

## 6. Docker Volumes

Docker volumes are managed by Docker and have a lifecycle independent of the containers using them. Volumes typically reside under Docker's data directory on the host or are managed by a volume plugin.

Creating and using a named volume:

~~~bash
# Create volume
docker volume create app-data

# Run container and mount volume
docker run -d \
  --name app \
  --mount source=app-data,target=/var/lib/app \
  my-app:1.0

# Inspect volume
docker volume inspect app-data

# Remove container while keeping volume
docker rm -f app
~~~

After the container is removed, the named volume remains until explicitly deleted by command or volume management policy. This makes volumes preferable to the writable layer when data must survive container replacement on the same host.

### 6.1. Named Volumes vs. Anonymous Volumes

- **Named volume:** assigned an explicit user-defined name, making it easy to reference in configuration and operations.
- **Anonymous volume:** automatically created with a generated ID when a container requests a volume without specifying a name.

Anonymous volumes can become orphaned when containers are removed without cleaning up volumes. Maintain a clear inventory and cleanup workflow.

### 6.2. Deleting Volumes

Deleting a container does not necessarily delete its volumes. Conversely, deleting a volume destroys the data inside it. Flags such as `docker rm -v` or `docker compose down -v` can remove volumes attached within that command's scope.

Before deleting a volume:

- Identify which containers or services use the volume.
- Verify backups and restore capability.
- Double-check the volume name and associated project/stack.
- Never run bulk prune commands on production hosts without assessing impact.

### 6.3. Docker Compose

~~~yaml
services:
  database:
    image: postgres:16
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - database-data:/var/lib/postgresql/data
    secrets:
      - db_password

volumes:
  database-data:

secrets:
  db_password:
    file: ./secrets/db_password.txt
~~~

This example illustrates a named volume for the database data directory and a secret file for the password. In production, manage secrets with an environment-appropriate mechanism rather than storing passwords in source control. A Docker volume on a single host does not automatically provide multi-host replication or backups.

## 7. Bind Mounts

A bind mount attaches a specific host path into a container. It is useful in software development, mounting configuration files, or integrating with directories managed by a host agent.

~~~bash
docker run --rm \
  --mount type=bind,source=/srv/app/config,target=/etc/app,readonly \
  my-app:1.0
~~~

This example mounts a configuration directory from the host into `/etc/app` in read-only mode.

### 7.1. Advantages and Risks

Advantages:

- Easy file sharing between host and container.
- Files can be edited on the host without rebuilding the image.
- Integrates smoothly with development and debugging tools.

Risks:

- Container depends on the host's filesystem layout.
- UID/GID ownership and permissions may mismatch.
- Containers can alter host files if mounted read-write.
- Host paths may not exist or may differ across nodes.
- Moving the container to another host does not automatically move the data.

### 7.2. When to Use Bind Mounts

Use bind mounts when you need intentional access to a specific host path. For business data needing independent lifecycle management, consider volumes or managed storage services.

Never mount the entire host root directory into a container. Grant only the minimal required path, prefer read-only mounts, and strictly control access permissions.

## 8. Docker Volumes, Bind Mounts, and `tmpfs`: Which One to Choose?

| Criterion | Named Volume | Bind Mount | `tmpfs` |
|---|---|---|---|
| Management location | Docker/volume driver | Host path | Memory filesystem |
| Portability across container restarts on same host | Can be reattached | Requires matching host path | Data discarded after lifecycle |
| Sharing with host | Accessible via management mechanisms, though avoid ad-hoc edits | Direct | Not stored as regular disk files |
| Data after container removal | Typically retained unless volume is deleted | Remains on host | Lost when mount/lifecycle ends |
| Best fit | App data that must stay on the host | Configs, source code, host integration | Speed-sensitive scratch/caches |
| HA scope | No built-in multi-host HA | Host-dependent | Ephemeral |

For production databases, a named volume only ensures data survives container replacement on the same host. It does not solve host failures, disk failures, replication, backups, or failover.

## 9. Kubernetes Volumes and Pod Lifecycle

Kubernetes provides volumes to share data among containers within the same Pod or to attach storage with a lifecycle independent of the Pod.

### 9.1. `emptyDir`

`emptyDir` is created when a Pod is assigned to a node and exists throughout the Pod's lifecycle. Multiple containers in the same Pod can mount the same `emptyDir` to share files.

When a container in the Pod restarts, `emptyDir` persists. When the Pod is removed from the node, `emptyDir` data is deleted.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: scratch-worker
spec:
  containers:
    - name: producer
      image: busybox:1.36
      command: ["sh", "-c", "echo ready > /scratch/state.txt; sleep 3600"]
      volumeMounts:
        - name: scratch
          mountPath: /scratch
    - name: consumer
      image: busybox:1.36
      command: ["sh", "-c", "sleep 5; cat /scratch/state.txt; sleep 3600"]
      volumeMounts:
        - name: scratch
          mountPath: /scratch
  volumes:
    - name: scratch
      emptyDir: {}
~~~

This example shows two containers in the same Pod sharing a `scratch` directory. Do not use `emptyDir` for data that must survive Pod replacement.

### 9.2. Memory-Backed `emptyDir`

~~~yaml
volumes:
  - name: memory-scratch
    emptyDir:
      medium: Memory
      sizeLimit: 128Mi
~~~

When `medium: Memory` is specified, Kubernetes mounts a `tmpfs` for `emptyDir`. Contents consume memory and can add to memory pressure. `sizeLimit` caps volume size per configuration; you still must account for the Pod's memory limits and total memory consumption.

### 9.3. `ephemeral-storage`

Kubernetes tracks local ephemeral storage as a resource. Requests and limits for `ephemeral-storage` can apply to container writable layers, container logs, and disk-backed `emptyDir` volumes.

Example:

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
    ephemeral-storage: "1Gi"
  limits:
    cpu: "1"
    memory: "1Gi"
    ephemeral-storage: "2Gi"
~~~

Requests help the scheduler account for required local storage; limits enable kubelet to monitor usage and evict Pods that exceed thresholds or when nodes run short on disk per policy. Exact accounting depends on filesystem layout and node configuration.

Do not confuse `ephemeral-storage` with a PVC. It represents temporary local node storage, not a durable disk that can reattach on another node.

## 10. `PersistentVolume` and `PersistentVolumeClaim`

A `PersistentVolume` (PV) is a cluster storage resource representing a volume with a lifecycle independent of Pods. A `PersistentVolumeClaim` (PVC) is a workload's request for storage. Kubernetes binds a PVC to a matching PV based on capacity, access modes, `StorageClass`, and other criteria.

Basic flow:

1. An administrator or `StorageClass` provisions a PV.
2. The workload creates a PVC requesting capacity and an access mode.
3. Kubernetes binds the PVC to a matching PV or dynamically provisions a volume.
4. The Pod mounts the PVC into a container.
5. Pods may be replaced; the PVC persists according to policy.
6. Volumes detach/attach according to storage backend capabilities and topology.

~~~mermaid
flowchart TD
    A["Application Pod"] --> B["PersistentVolumeClaim"]
    B --> C["PersistentVolume"]
    C --> D["CSI Driver"]
    D --> E["Cloud Block / File Storage"]
    F["StorageClass"] --> D
    G["Snapshot / Backup"] --> E
~~~

PVCs decouple storage requests from backend implementation details. Applications can request capacity and access modes without knowing exact cloud provider block device names.

### 10.1. PVC and Pod Example

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: app-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
  storageClassName: fast-block
---
apiVersion: v1
kind: Pod
metadata:
  name: app
spec:
  containers:
    - name: app
      image: my-app:1.0
      volumeMounts:
        - name: data
          mountPath: /var/lib/app
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: app-data
~~~

This example requests 20 GiB via a `StorageClass` named `fast-block`. That `StorageClass` must exist and be configured with an appropriate CSI driver in the cluster. `ReadWriteOnce` does not mean only one Pod can mount it in every scenario; access mode semantics depend on node and driver behavior.

### 10.2. Dynamic Provisioning

With dynamic provisioning, a PVC can trigger CSI to provision a new volume according to its `StorageClass`. Operators do not need to create each PV manually.

A `StorageClass` can specify:

- The CSI provisioner.
- Disk type or performance tier.
- Topology/zone constraints.
- Filesystem or volume parameters.
- Reclaim policy.
- Binding mode.
- Volume expansion policy if supported by the backend.

Inspect the `StorageClass` before creating production PVCs. A storage class named "fast" does not by itself prove latency, IOPS, or durability; verify actual backend specifications.

### 10.3. Access Modes

Common access modes:

- **ReadWriteOnce (RWO):** the volume can be mounted read-write by a single node at a time under Kubernetes/driver semantics; multiple Pods on that same node can share it.
- **ReadOnlyMany (ROX):** the volume can be mounted read-only by multiple nodes if supported by the backend.
- **ReadWriteMany (RWX):** the volume can be mounted read-write by multiple nodes if supported by the backend.
- **ReadWriteOncePod (RWOP):** restricts read-write mounting to a single Pod where supported.

Access modes are mount/claim constraints; they do not replace filesystem permissions or application-level locking. RWX does not guarantee safe concurrent writes by applications; applications still need file locking, transactions, or proper synchronization protocols.

## 11. `StorageClass`, CSI, and Topology

The Container Storage Interface (CSI) is the standard interface enabling Kubernetes to communicate with storage providers. A CSI driver can provision, attach, mount, resize, snapshot, or perform other operations depending on implemented capabilities.

### 11.1. `StorageClass`

A `StorageClass` describes a class of dynamically provisionable storage. For example, a cluster might define:

- A class for high-performance block storage.
- A class for cost-optimized block storage.
- A class for shared file storage supporting RWX.
- A class for local ephemeral storage or specialized volume types.

Never pick a `StorageClass` by name alone. Check its provisioner, parameters, binding mode, reclaim policy, topology, and backup/snapshot support.

### 11.2. Volume Topology

Some block volumes can only attach to instances within the same AZ where the volume was created. If a Pod moves to a node in another AZ, the scheduler needs topology awareness to place the Pod where the volume can attach.

`volumeBindingMode: WaitForFirstConsumer` delays volume binding/provisioning until the scheduler knows where the Pod will run. This enables better topology selection across many block storage architectures.

~~~yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-block
provisioner: csi.example.com
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
reclaimPolicy: Retain
parameters:
  tier: performance
~~~

This is a structural example; `csi.example.com` and `tier` are illustrative values that must be replaced with your actual driver's provisioner and parameters. Do not apply this YAML directly to a cluster lacking the corresponding CSI driver.

### 11.3. Reclaim Policy

The reclaim policy governs what happens to a PV when its PVC is deleted:

- **Retain:** keeps the PV and its data for manual administrator handling or controlled reuse.
- **Delete:** instructs the backend to delete the volume when the claim/PV is released according to provisioner semantics.

Actual behavior also depends on the CSI driver and storage service. For critical data, know exactly what gets deleted when a PVC is deleted and ensure backups exist beforehand.

## 12. `StatefulSet` and Volume Claim Templates

`StatefulSet` fits workloads needing stable identities and dedicated storage per replica, such as database or broker clusters.

`volumeClaimTemplates` creates a dedicated PVC for each Pod. A Pod can be recreated with the same identity and reattach its corresponding claim, subject to storage capabilities and topology.

~~~yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ledger
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
        - name: database
          image: example/ledger-db:2.0
          volumeMounts:
            - name: data
              mountPath: /var/lib/ledger
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: fast-block
        resources:
          requests:
            storage: 50Gi
~~~

Each replica receives its own claim. `StatefulSet` does not automatically replicate database data or guarantee quorum; the database engine or an operator must manage replication, leader election, and consistency.

### 12.1. Deleting `StatefulSet` and PVCs

PVCs created by `volumeClaimTemplates` typically have an independent lifecycle and are not automatically deleted simply because a Pod restarts. Retention behavior when deleting or scaling a `StatefulSet` depends on the `StatefulSet` retention policy configuration and Kubernetes version.

Before scaling in or deleting a `StatefulSet`, check:

- Which PVCs still exist.
- Which PVs are bound to which PVCs.
- Whether the reclaim policy is `Retain` or `Delete`.
- Whether recent snapshots/backups exist and restores have been tested.
- Whether data must be preserved to rebuild the cluster.

## 13. Object Storage vs. Block/File Storage

Not all container data needs a mounted filesystem. Choose storage based on how the application accesses data:

| Type | Access Pattern | Best Fit |
|---|---|---|
| Block storage | Block device used by a filesystem/database | Databases, filesystems needing steady IOPS and low latency |
| File storage | File protocols such as NFS or SMB | Files shared across multiple nodes/Pods, home directories |
| Object storage | Object API, bucket/key | Uploads, artifacts, backups, media, and unstructured data |
| Local ephemeral disk | Node/instance local disk | Scratch, regenerable caches, high-throughput temporary data |
| Memory storage | RAM/`tmpfs` | Small temporary data requiring ultra-low latency |

### 13.1. Block Storage

Block volumes are typically attached to a single VM/node and formatted with a filesystem or consumed directly by applications supporting raw block devices. Evaluate IOPS, throughput, latency, queue depth, burst balance, and limits tied to volume/instance size.

Block volumes cannot necessarily be attached read-write concurrently to multiple nodes. Some services offer multi-attach with strict requirements and limits; the filesystem or database must safely support concurrent access.

### 13.2. File Storage

File storage allows multiple nodes to access a shared namespace. It helps when applications must share files across Pods. Verify:

- NFS/SMB version and mount options.
- Throughput and IOPS per workload.
- File locking and consistency semantics.
- Permissions, UID/GID, ACLs, and root squash.
- Network path and mount targets per AZ.
- Behavior during network storage disruptions.

### 13.3. Object Storage

Object storage is accessed via API rather than a full POSIX filesystem. It excels for uploads, media, backups, and artifacts. Applications should use SDKs/APIs and handle multipart uploads, retries, checksums, versioning, and lifecycle policies.

Avoid mounting object storage as a filesystem and assuming renames, locks, or atomic writes behave like local disks. Design around the service's object API.

## 14. Durability, Availability, and Backups

Durability describes the likelihood that data is not lost over time; availability describes the ability to access data when needed. High-durability storage can still become temporarily unavailable; a mounted volume can still suffer accidental deletion.

To protect data:

- Choose appropriate replication and failure domains.
- Enable backups or snapshots aligned with your RPO.
- Use retention policies and versioning where needed.
- Protect backups against accidental deletion.
- Test restores periodically.
- Monitor write errors, checksums, and replication lag.
- Decouple backups from the primary workload's lifecycle.

### 14.1. Snapshots Do Not Replace Full Backups

Snapshots can provide volume recovery points, though application consistency must be verified. For databases, crash-consistent snapshots may require recovery logs; application-consistent snapshots require coordinated flushes or quiescing.

When an application spans multiple volumes, snapshotting volumes at different moments can yield an inconsistent state. Use volume snapshot groups or database-native backup workflows when cross-volume consistency is required.

### 14.2. Backups and Replication Solve Different Problems

Replication keeps the service running when one replica or node fails. Backups enable recovery when data is accidentally deleted, hit by ransomware, or corrupted by bugs replicated across all replicas.

Never treat replicas as backups. Maintain retention policies, independent copies, and separated access permissions.

## 15. Container Storage Performance

Storage can become a bottleneck even when CPU and memory have headroom. Measure per workload:

- Read/write IOPS.
- Throughput (MiB/s or GiB/s).
- Average and tail latency.
- Queue depth.
- `fsync`/flush latency.
- Cache hits/misses.
- File counts and metadata operations.
- Network throughput to file/object storage.

### 15.1. IOPS and Throughput

IOPS measures I/O operations per second; throughput measures bytes transferred per second. Small-block random read workloads can be IOPS-bound; large-file processing can be throughput-bound.

Do not look solely at a volume's advertised maximums. Real-world performance depends on instance/network limits, filesystems, queue depth, block size, and concurrency.

### 15.2. Latency

Databases are especially sensitive to tail latency. A few slow writes can stall transactions, connection pools, and request queues. Inspect p95/p99 storage latency alongside application latency.

### 15.3. Local SSDs and Ephemeral Disks

Local NVMe or instance store volumes offer high performance, though data is typically tied to the instance or hardware lifecycle. Use them for caches, scratch, shuffle data, or regenerable datasets; never use them as the sole copy of critical data.

If data must be kept, replicate or checkpoint it to durable storage before the instance stops.

## 16. Capacity, Quotas, and Eviction

Temporary filesystems have finite limits. If writable layers, logs, or `emptyDir` volumes consume too much space, the node can run out of disk and impact multiple workloads.

In Kubernetes, kubelet monitors local ephemeral storage and can evict Pods when the node hits disk pressure or a Pod exceeds configured limits per policy. A single container writing unbounded logs can exhaust node disk even if the business app writes few files.

Controls:

- Set appropriate `ephemeral-storage` requests and limits.
- Configure log rotation and log shipping.
- Set `sizeLimit` on `emptyDir` volumes where appropriate.
- Monitor node filesystems and inode usage.
- Clean up temporary files after jobs complete.
- Never keep unbounded caches on local disk.
- Alert before nodes hit disk-pressure thresholds.

### 16.1. Disk Space and Inodes

A filesystem can run out of inodes even with abundant free bytes if an application creates millions of small files. Monitor both disk space and inodes:

~~~bash
df -h
df -i
du -sh /var/lib/app/*
~~~

These commands are Linux examples; adjust paths and permissions for your image/container. When inspecting a container, determine whether the filesystem belongs to the writable layer, a volume, or the host node.

## 17. Filesystem and Volume Security

Storage mounts extend a container's reach to external data. Enforce least privilege:

- Run as a non-root user whenever possible.
- Set explicit ownership and permissions.
- Mount volumes read-only if the application only needs reads.
- Avoid mounting sensitive host paths.
- Never store secrets in images or writable layers.
- Encrypt data at rest and in transit as required.
- Manage keys and KMS/secret service permissions carefully.
- Separate volumes across tenants or workloads with distinct security boundaries.
- Audit reads, writes, snapshots, and deletions of critical data.

### 17.1. UID/GID and Permissions

A container may run with a UID/GID different from the host. A volume may mount successfully yet fail application writes if ownership mismatches.

In Kubernetes, `securityContext.fsGroup` can help set group ownership on supported volumes and CSI drivers. Behavior and performance vary by volume type; do not assume it always updates permissions recursively across every backend.

### 17.2. Read-Only Root Filesystem

Setting the root filesystem read-only limits tampering with system files if a container is compromised. Applications may still need dedicated writable paths such as `/tmp`, `/var/cache`, or runtime directories.

~~~yaml
securityContext:
  runAsNonRoot: true
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
~~~

When `readOnlyRootFilesystem` is enabled, mount separate writable volumes for paths requiring writes. Otherwise, the application may fail at startup or when creating temporary files.

### 17.3. Secrets and Sensitive Data

Never bake secrets into images or write long-lived secrets into shared volumes. Use a secret manager or Kubernetes Secrets protected by encryption at rest, RBAC, and proper rotation policies.

If secrets are mounted as files, control file permissions, refresh timing, and how the application handles updated contents.

## 18. Logging in Containers

Containers typically log to stdout/stderr for runtime collection. This aligns well with orchestration platforms because agents can ship logs to centralized backends.

Avoid writing the sole copy of logs to files inside the writable layer. When a container is replaced, those files can vanish. If an application must write log files:

- Mount an appropriate volume.
- Configure log rotation.
- Run an agent or sidecar to forward logs centrally.
- Cap storage size and retention.
- Monitor for collector or network failures.

Do not rely on a single local log file as a durable audit trail when business requirements demand tamper resistance or long-term retention.

## 19. Migrating and Upgrading Stateful Workloads

Rolling updates swap container images while preserving volumes if mount configurations stay unchanged. However, existing volume data may still be incompatible with the new application version.

Before upgrading:

1. Check whether schemas or data formats changed.
2. Create a backup/snapshot following application procedures.
3. Test the migration against a copy of the data.
4. Verify whether the previous version can read data after migration.
5. Prepare a rollback plan.
6. Execute migrations sequentially and monitor for errors.

For databases, schema migrations may not be reversible. Use an expand-and-contract strategy when old and new application versions must run concurrently.

### 19.1. Moving Pods to Another Node

If a PVC uses a block volume with AZ-scoped topology, the replacement Pod may have to schedule on a node in the same AZ to attach the volume. If that AZ goes down, the volume becomes unreachable even if the Pod controller creates a new Pod.

Resilience requires storage replication or database replicas in another AZ. Simply rescheduling a Pod does not automatically move block data across zones.

### 19.2. Migrating Across Environments

Bind mounts depend on host paths; local Docker volumes depend on the host; PVs depend on CSI backends and topology. When moving across clusters or cloud providers, plan for export/import, snapshot restores, replication, or data migration.

Never assume a volume driver or filesystem mount option carries identical semantics across platforms.

## 20. Storage Selection Examples by Workload

| Workload | Data | Suitable Option | Notes |
|---|---|---|---|
| Stateless Web API | Sessions, cache, uploads | Shared session store; regenerable cache; object storage for uploads | Never keep sole sessions/files in writable layer |
| Batch worker | Temporary input/output, checkpoints | `emptyDir` or local scratch for intermediates; object/block storage for checkpoints | Jobs must resume after interruption |
| PostgreSQL | Data directory, WAL | Persistent block volume or managed database storage | Backups, replication, `fsync`, and failover |
| Media processing | Temporary files, outputs | Local NVMe scratch and object storage for outputs | Upload durable outputs before deleting scratch |
| Shared content service | Shared files | Managed file storage supporting multi-node access | Verify locking and throughput |
| CI runner | Source checkout, cache, artifacts | `emptyDir`/local scratch for workspace; artifact store for outputs | Caches can be purged; artifacts need retention |

## 21. Practical Example: Database Containers and File Uploads

An e-commerce application runs an API on Kubernetes. Initially, developers stored uploaded images and database files in directories inside the container. During a rolling update, new Pods spun up and the old files disappeared.

Redesigned architecture:

1. The stateless API runs multiple replicas across multiple nodes.
2. Uploaded files are written to object storage via API; the database stores only object keys and metadata.
3. The database runs as a managed service or a `StatefulSet` with PVCs, backups, and proper replication.
4. Caches and temporary files use `emptyDir` with size limits.
5. Logs write to stdout/stderr and ship to a centralized logging system.
6. PVCs specify defined `StorageClass`, topology, and reclaim policies.
7. Backups undergo restore testing independently of the Pod lifecycle.

Afterward, when API Pods are replaced, uploaded files remain intact in object storage and database data stays on durable storage. When a node fails, Kubernetes schedules a replacement Pod, while the database/storage tier handles topology and failover through dedicated mechanisms.

## 22. Common Mistakes

- **Storing critical data in the writable layer:** container replacement can destroy the data.
- **Confusing container restart with container recreation:** the two operations have different filesystem lifecycles.
- **Using `emptyDir` for data that must outlive Pod replacement:** `emptyDir` is deleted when the Pod terminates.
- **Treating Docker volumes as multi-host storage:** local volumes remain bound to a host or driver.
- **Overly broad read-write bind mounts:** containers can modify host data beyond their intended scope.
- **Using uncapped `tmpfs`:** can trigger memory pressure or OOM kills.
- **Assuming PVCs can always attach in any AZ:** block volumes can be topology-constrained.
- **Assuming `StatefulSet` replicates data automatically:** `StatefulSet` provides identity and claims; the database must handle replication.
- **Ignoring reclaim policies:** deleting a PVC can cascade into deleting the backend volume.
- **Confusing access modes with permissions:** RWO/RWX do not replace UID/GID, ACLs, or file locking.
- **Monitoring capacity while ignoring inodes:** filesystems can still run out of file creation capacity.
- **Skipping restore tests:** snapshots may exist yet fail to restore a working application.
- **Logging exclusively inside the container:** logs can vanish when the container is replaced.
- **Deploying without schema checks:** a newer application version can render data unreadable by older versions.

## 23. Container Storage Design Checklist

Before deploying, confirm:

- [ ] Data is classified into scratch, cache, logs, sessions, uploads, databases, and checkpoints.
- [ ] Critical data does not reside solely in the writable layer.
- [ ] Lifecycles of containers, Pods, nodes, and volumes are clearly distinguished.
- [ ] `tmpfs`/`emptyDir` have appropriate memory or disk limits.
- [ ] Docker volumes or bind mounts have clear ownership and cleanup policies.
- [ ] PVCs specify appropriate capacity, access modes, and `StorageClass`.
- [ ] CSI drivers and volume topology are verified.
- [ ] Reclaim policies will not unexpectedly delete data.
- [ ] `StatefulSet` deployments have dedicated replication/consistency strategies.
- [ ] Backups, snapshots, and restores have been tested.
- [ ] Metrics cover IOPS, throughput, latency, capacity, and inodes.
- [ ] Permissions, UID/GID, read-only mounts, and encryption are configured.
- [ ] Logs and secrets do not rely on the writable layer.
- [ ] Upgrade/migration workflows include backups and rollback plans.

## 24. Operations and Maintenance Workflow

1. **Inventory:** catalog volumes, PVCs, PVs, `StorageClass`es, and owners.
2. **Classification:** separate regenerable data from data requiring retention.
3. **Capacity planning:** forecast storage size, IOPS, throughput, inodes, and growth.
4. **Lifecycle policy:** define retention, snapshots, reclaim behavior, and cleanup.
5. **Security review:** audit permissions, encryption, secrets, and mount scopes.
6. **Observability:** monitor latency, mount errors, attach/detach events, disk pressure, and backups.
7. **Recovery testing:** restore data and boot the application from restored copies.
8. **Change management:** test schemas, migrations, and compatibility before deployment.
9. **Retirement:** verify ownership and backups before deleting PVCs, PVs, or volumes.

## 25. Key Takeaways

Container filesystems consist of multiple layers with distinct lifecycles. The writable layer and `tmpfs` fit ephemeral data; Docker volumes, bind mounts, and Kubernetes PV/PVCs store data outside containers with varying durability guarantees and infrastructure dependencies. `emptyDir` lives alongside the Pod, whereas PVCs can outlive Pods depending on reclaim policies and storage backends.

Select storage based on data lifecycle, failure domains, access patterns, performance, and security requirements. Critical data needs backups, restore testing, and appropriate replication; a local disk or single-host volume does not automatically provide multi-node HA. Monitor capacity, inodes, IOPS, throughput, and latency together. Explicitly design ownership, topology, permissions, and deletion policies so containers can be replaced freely without losing business data.
