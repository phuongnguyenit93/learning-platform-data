# Persistent Storage, Directory Permissions, and Runtime Resource Limits in MongoDB

A Java application can connect to MongoDB successfully, write data for days, and pass all functional tests, yet still lose data when a container is recreated, fail to start after moving a volume to a new machine, or be repeatedly terminated by the OS due to running out of memory. These failures rarely originate from `insertOne()` or collection design; they stem from the **MongoDB operating environment**.

In the **Operations and Upgrades** chapter of the **Database Engine Document MongoDB** module, this lesson focuses on three areas of responsibility:

1. **Persistent storage:** where database bytes, journal, metadata, indexes, and logs reside; whether data survives container or host replacement; and how recovery works after a crash.
2. **Directory permissions:** the OS account running `mongod` must have appropriate permissions for `dbPath`, log directories, and config files; permissions must never be overly broadened merely to bypass `Permission denied`.
3. **Resource limits:** how disk capacity, IOPS, CPU, RAM, WiredTiger cache, file descriptors, container limits, filesystems, and scheduling affect MongoDB stability.

This lesson also explains key differences between **Linux VM/bare metal**, **Docker/Compose**, **Kubernetes**, and **MongoDB Atlas** deployments, along with configuration examples, diagnostics, runbooks, and exercises.

> **Scope and Safety:** Commands involving `chown`, `chmod`, mount, systemd, Docker volumes, PVCs, or service upgrades are instructional examples for authorized administration environments. Never run permission changes, `docker compose down -v`, database file deletions, or production cluster restarts without verifying backups, topology, volume ownership, and a rollback plan.

## 1. Three Concepts to Distinguish Immediately

| Property | Question to Answer | Symptom When Wrong |
| --- | --- | --- |
| **Persistence** | Does data survive process/container replacement? | New container starts with an empty database |
| **Durability** | Which failures can acknowledged writes survive? | Crash/failover loses some writes |
| **Availability** | When a node dies, does the system still serve requests? | Database is unreachable even though data remains on disk |

These three properties are related but **not synonymous**:

- A **persistent volume** stores bytes beyond the container's lifecycle, but does not automatically guarantee `writeConcern: "majority"` or backups.
- A **replica set** provides node fault tolerance and can increase write durability based on acknowledgment policy, but if the application stores data on ephemeral volumes or accidentally deletes an entire deployment, a replica set does not replace backups.
- A **backup** can restore data, but does not guarantee system availability during the restore.
- A running MongoDB container returning `ping: 1` does not prove it uses persistent storage or has enough free disk space.

### Storage Layer Diagram

```text
Application
   |
   | BSON reads/writes
   v
MongoDB mongod
   |
   +--> WiredTiger cache in RAM
   |
   +--> data files / indexes
   +--> journal and required metadata
   |
   v
dbPath inside runtime environment
   |
   +--> VM/bare metal: mounted filesystem
   |
   +--> Docker: named volume / bind mount
   |
   +--> Kubernetes: PVC -> PV -> storage backend
   |
   v
Storage device / block volume
   |
   +--> Disk controller, filesystem, flush semantics
   +--> Snapshot/backup (must be managed separately)
```

Each layer can fail in different ways. When investigating, identify whether the fault occurred at the **process**, **filesystem**, **container mount**, **storage backend**, or **replication/backup** layer.

## 2. What Is `storage.dbPath`?

Self-managed MongoDB uses `storage.dbPath` to specify the directory holding data for the `mongod` process.

Example Linux configuration:

```yaml
# Partial mongod.conf for illustration.
storage:
  dbPath: /var/lib/mongodb
  journal:
    enabled: true

systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true

net:
  bindIp: 127.0.0.1
  port: 27017
```

Here:

- `/var/lib/mongodb` is the chosen **data** directory for the deployment.
- `/var/log/mongodb/mongod.log` is the **log file**; it is separate from data files.
- `dbPath` is neither a connection string nor a database name.
- Actual paths depend on the package, container image, and configuration. Do not assume every host uses `/var/lib/mongodb`.

Modern MongoDB releases use **WiredTiger** for most standard deployments; exact options and support depend on version. The files inside `dbPath` belong to the storage engine and server.

**Do not treat `dbPath` as a folder of JSON files you can edit manually.** Modifying, moving, deleting, or copying WiredTiger files while `mongod` is running can produce an inconsistent copy or startup failures.

### What Is Typically Inside `dbPath`

Depending on version and storage configuration, the directory may contain files related to:

- WiredTiger metadata and storage files.
- Collection and index data.
- Journal files/journal directory.
- Key management metadata or other internal structures.

File names and layout are **not a stable application API**. Applications must access data through drivers/database commands, never by directly opening files inside `dbPath`.

## 3. Persistence: Process Crash vs. Volume Deletion

Distinguish these scenarios:

```text
Scenario A:
  mongod crashes/restarts
  -> same filesystem and dbPath remain
  -> storage engine performs recovery via supported mechanisms

Scenario B:
  Docker container is deleted
  -> named volume remains and is remounted to the same path
  -> data can persist

Scenario C:
  Docker container is deleted
  -> data was stored only in the container's writable layer
  -> data is not guaranteed to survive recreation

Scenario D:
  Kubernetes Pod is replaced
  -> new Pod reattaches the right PVC/PV
  -> data can continue to persist

Scenario E:
  PVC/PV or disk backend is deleted/lost
  -> storage is gone
  -> must rely on replicas/backups per recovery plan
```

**A persistent volume is not a backup.** If an operator accidentally drops an entire collection, that drop is also written to the persistent volume; a replica set will replicate the drop to the other members.

### Separate Lifecycles

| Resource | Can Be Replaced During Deploy? | Purpose |
| --- | --- | --- |
| Container/Pod | Yes | Packages and runs the process |
| Database process | Can be restarted | Processes queries and writes data |
| Data volume/PV | Must have its own retention policy | Stores database state |
| Backup/snapshot | Managed outside service lifecycle | Recovers from loss/corruption/accidental deletion |
| Secret/certificate | Managed via secret lifecycle | Authentication/TLS; does not replace data volume |

Proper design asks: **When a deployment recreates a Pod/container, what retains the volume identity and access permissions to the existing data?**

## 4. WiredTiger, Cache, Checkpoints, and Journal

WiredTiger uses a cache and writes data to storage according to engine rules. Conceptually:

```text
Client write
     |
     v
MongoDB / WiredTiger
     |
     +--> modifications in cache
     |
     +--> journal/durability path per configuration
     |
     v
Checkpoints and writes to data files
     |
     v
Filesystem / storage device
```

**Checkpoints** and the **journal** work together to support crash recovery. When a process terminates abruptly, the engine uses the persisted durability records to recover to a consistent state per server guarantees and write concern.

Key points:

1. Data appearing in cache **does not mean** it is durably flushed to storage.
2. A write acknowledged with `w:1` does not have the same failover durability as `w:"majority"`.
3. The journal supports recovery but does not replace **replication**, **backups**, or reliable storage hardware.
4. Write paths, checkpoints, and journaling increase **disk I/O** demand; capacity cannot be sized solely by document size.
5. Overall durability depends on the storage engine, write concern, configuration, and the storage backend's ability to honor flush/fsync properly.

### Should You Delete the `journal` Directory to Save Disk Space?

**No.** The journal and internal files belong to the MongoDB storage engine. Manually deleting them while the server is running or during recovery can destroy database recoverability and integrity.

If a disk is filling up, investigate the root cause, expand capacity, manage retention/indexes/backups, or follow the runbook for your MongoDB version. Never "clean up" by deleting files in `dbPath` that you do not understand.

## 5. Write Concern and Durability Are Not Persistence

Suppose a replica set has three members. The application writes:

```javascript
db.orders.insertOne(
  { orderNo: "ORD-1001", status: "NEW" },
  { writeConcern: { w: "majority" } }
);
```

Based on replica set configuration and server capabilities, `w:"majority"` requires acknowledgment from a majority of eligible voting data-bearing members before reporting success. This is part of failover durability policy.

Comparison:

| Write concern | Acknowledgment Condition | What Not to Infer |
| --- | --- | --- |
| `w:1` | Primary acknowledges per configuration | Does not guarantee the write survives every failover |
| `w:"majority"` | Majority of relevant members acknowledge per server rules | Does not protect against replicated accidental deletions |
| `j:true` | Requests journal write acknowledgment where supported | Does not replace replication/backups or protect against total host loss |
| `wtimeout` | Limits wait time for write concern | A timeout **does not mean** the operation was definitely not written |

Majority write concern journaling behavior and defaults have changed across MongoDB versions and replica set configurations. Never apply a blanket claim like "every majority write is fsynced on all nodes" to every deployment.

### Java MongoDB Sync Driver Example

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

// collection is obtained from a configured MongoDatabase connection.
MongoCollection<Document> durableOrders =
    collection.withWriteConcern(WriteConcern.MAJORITY);

durableOrders.insertOne(
    new Document("orderNo", "ORD-1001")
        .append("status", "NEW")
);
```

In production, account for majority acknowledgment latency, retryable writes, idempotency, and transaction boundaries. **Do not treat a request timeout as proof that an insert failed**; reconcile using a unique business key before retrying.

### Read Concern and Data Visibility

Read concern governs the consistency of read values; write concern governs write acknowledgment conditions. They are related yet functionally independent. For sensitive workflows, choose read concern, write concern, and session/transaction semantics according to the application's consistency contract.

## 6. Disk Capacity: Account for More Than Document Bytes

A MongoDB capacity estimate must include:

```text
Database logical documents
   + index data
   + WiredTiger storage overhead / compression effects
   + journal/checkpoint overhead
   + oplog (if replica set)
   + temporary files/sorts/migrations/index builds
   + filesystem metadata
   + headroom for upgrades/restores
```

Do not multiply document count by on-screen JSON size and assume that is actual storage usage. BSON, compression, indexes, updates/fragmentation, and workload all affect the result.

### Difference Between Logical Size and Storage Size

MongoDB reports metrics such as `dataSize`, `storageSize`, `indexSize`, and other collection/DB stats. Each answers a different question.

Example in `mongosh`:

```javascript
use appdb

db.stats();
db.orders.stats();
```

If data compresses well, storage size can differ significantly from logical data size. Indexes and the oplog still consume separate space. Check actual metrics for your target version and track **growth trends**.

### Headroom Matters

Disks must not run continuously near 100%. Reserve space for:

- Write spikes and batch ingest bursts.
- Index builds, compact/migrations/rebuilds.
- Checkpoint and journal activity.
- Changes during upgrades or failovers.
- Temporary backups, exports, or restores if performed on the same host.

No single headroom percentage fits every system. Reserve capacity based on data growth rate, collection/index sizes, and the largest expected maintenance operation.

## 7. Storage Throughput, IOPS, and Latency

A database needs not just **enough bytes**, but also **enough read/write speed**.

Metrics to distinguish:

| Metric | Meaning | MongoDB Impact |
| --- | --- | --- |
| Capacity (GiB/TiB) | Total space available | Limits data growth |
| IOPS | I/O operations per second | Impacts workloads heavy in random reads/writes |
| Throughput (MiB/s) | Bytes read/written per second | Critical for scans, backups, and initial sync |
| I/O latency | Time to complete an I/O operation | Directly impacts query latency/checkpoints |
| Queue depth | Backlog of pending I/O | Signals storage cannot keep up with workload |
| Burst credits/limits | Temporary speed boost on cloud disks | Sudden slowdown when credits deplete |

A 1 TiB volume can still be far too slow if provisioned with low IOPS for 10,000 writes/s. Conversely, a fast SSD that is too small will still hit `No space left on device`.

### How Disk Saturation Cascades

```text
Application writes
        |
        v
MongoDB dirty pages / journal
        |
        v
Storage I/O queue backs up
        |
        +--> write latency rises
        +--> checkpoints slow down
        +--> replication lag grows
        +--> reads degrade
        +--> application timeouts
```

Do not watch CPU alone: a MongoDB process with low CPU usage but very slow queries may be **waiting on disk I/O**.

## 8. Choosing Filesystem and Storage Backend

For self-managed MongoDB using WiredTiger, the filesystem and storage backend must meet the durability and performance requirements of the specific version.

Questions to ask:

1. Which filesystems are recommended/supported by MongoDB for the current OS and storage engine?
2. Does the storage backend honor the required flush/fsync guarantees?
3. Does the disk provide adequate random I/O latency and IOPS?
4. Can consistent snapshots/backups be taken and restore-tested?
5. Can capacity be expanded or volumes replaced without losing data?
6. If the host changes, can the volume be reattached/remounted in the proper host/zone?
7. Does storage provide encryption-at-rest and proper key management?

On Linux, **XFS** and **ext4** are commonly cited in MongoDB deployment guidance; verify final choices against **version-specific production notes**, especially regarding WiredTiger filesystem recommendations. Never pick NFS/SMB/shared network filesystems just because mounting is easy; verify support as well as locking, durability, and performance behavior before using one as `dbPath`.

### Mount Options and Driver Configuration

Do not copy a list of mount options from another machine without verifying the filesystem, OS, cloud provider, and MongoDB recommendations. An option that speeds up I/O may alter semantics that durability relies on.

### Separating Data and Logs

Placing `systemLog.path` outside `storage.dbPath` separates responsibilities; under heavy workloads, consider separate disks/filesystems. However, separating directories **does not isolate I/O** if both sit on the same underlying physical volume.

An overgrown log can fill a filesystem without proper log rotation. Conversely, improperly deleting a log while a process holds an open file handle may fail to free space as expected. Use log rotation and supported OS/MongoDB procedures.

## 9. Directory Permissions: Which User Runs MongoDB?

On Linux, the MongoDB service normally runs under a non-root **service account**. The account and group name depend on the package—for instance `mongodb` or `mongod` across different distributions.

First, inspect the actual process:

```bash
# Read-only process inspection; makes no system changes.
ps -eo user,group,pid,cmd | grep '[m]ongod'

# If the service is managed by systemd:
systemctl status mongod
systemctl cat mongod
```

Never assume a distro uses the `mongodb` user. If the package uses `mongod` or a custom user, running `chown` to the wrong user can break service permissions.

### Why Not Run `mongod` as Root?

Root holds broad privileges across the host. If the MongoDB process or an extension has a vulnerability, running as root increases the blast radius. A dedicated least-privilege service account contains the impact.

### Required Permissions

The service identity needs:

- **Traverse/search** permissions on parent directories leading to `dbPath`.
- **Read/write** permissions on data, journal, and metadata inside `dbPath` as required by the engine.
- Permission to create, rename, and delete files managed by MongoDB within the data path.
- Write permission for log files or socket/pid directories if configured.
- Read permission for certificates/keyfiles and configs/secrets per security policy.

Other users should not be able to read private keys, database files, or dump backups unnecessarily.

## 10. Checking `dbPath` Permissions on Linux

Suppose `dbPath` is `/var/lib/mongodb`.

```bash
# Read-only inspection:
ls -ld /var/lib/mongodb
stat /var/lib/mongodb
namei -l /var/lib/mongodb

# Verify the mount hosting the path:
df -hT /var/lib/mongodb
```

Example output:

```text
drwx------  mongodb mongodb ... /var/lib/mongodb
```

This is only an **illustrative sample**: actual user/group and permission bits depend on the deployment. `namei -l` inspects permissions on **parent directories**, which matters because a process might own the leaf directory yet lack traverse permissions on a parent directory.

### Distinguishing Ownership and Mode Bits

- `owner`: user assigned to the file/directory.
- `group`: owner group.
- `r/w/x`: read/write/execute or traverse permissions.
- `ACL`: extended permissions that can grant or restrict access per OS.
- `SELinux/AppArmor`: mandatory access control policies **beyond** Unix mode bits.

Setting `chmod 777` on a directory is not a valid fix for `Permission denied`: it grants write access to every user/process that can reach the path.

## 11. Fixing `Permission denied` Properly

Scenario: MongoDB fails to start after attaching a new volume.

```text
mongod
  -> opening WiredTiger files
  -> Permission denied
  -> process exits
```

Procedure:

1. Identify the process user/group from the service or container configuration.
2. Verify the actual `dbPath` in use.
3. Verify the volume is mounted at the expected location.
4. Check owner, group, mode bits, and traverse permissions on parent directories.
5. Check whether the filesystem is mounted **read-only**.
6. If the OS runs SELinux/AppArmor, inspect policies and audit logs.
7. Confirm the container's effective UID/GID matches ownership on host files.
8. Change ownership/permissions **only on the verified path** and when safe to do so.

### Lab-Only Ownership Change Example

Suppose you have confirmed the service account is **actually named `mongodb`** and the path **contains only data for that service**:

```bash
# Lab environment example, after properly stopping the service.
# Do not run without verifying path, mount, user, and permissions.
sudo chown mongodb:mongodb /var/lib/mongodb
sudo chmod 700 /var/lib/mongodb
```

This modifies only the **root directory**, not all files beneath it. For ownership mismatches on child files, investigate how they occurred and choose an appropriate fix; **never run `chown -R` on an unverified path**. Specifically, if `/var/lib/mongodb` accidentally contains another mount point, recursive changes can affect unrelated data.

### Why Not Use `chmod -R 777`?

It can allow unauthorized users to read, modify, or delete database files. That creates a security risk and masks underlying identity, mount, or SELinux errors. Broad permissions also cannot fix a read-only filesystem, full disk, or wrong path.

## 12. SELinux, AppArmor, and Additional Policies

On some Linux distributions, beyond owner/mode bits, there are:

- **SELinux labels/policies**.
- **AppArmor profiles**.
- Systemd sandboxing or filesystem access restrictions.
- Container security profiles, user namespaces, and rootless mode.

For example, even with a directory configured as:

```text
Owner = mongod
Mode  = rwx------
SELinux context = wrong policy
```

the process can still be denied. If you move `dbPath` to another mount point, you may need to configure the appropriate security context per system policy. Do not disable SELinux/AppArmor system-wide just to get the database running; inspect denial logs and adjust policies/labels in a controlled manner.

### Systemd Sandboxing

A systemd service may use `ReadWritePaths`, `ProtectSystem`, `DynamicUser`, or other protective directives. Moving `dbPath` outside permitted paths can block `mongod` writes even when Unix permissions look right.

Inspect the **effective unit configuration** using `systemctl cat mongod` and any drop-in overrides. Do not edit vendor unit files directly if you want clean package upgrades.

## 13. Docker: The Writable Layer Is Not a Data Volume

A container has multiple storage layers:

```text
MongoDB container
  /data/db  <-- dbPath in common images
     |
     +--> No volume mounted:
     |       container writable layer
     |       lost when the container is deleted
     |
     +--> Named volume mounted:
             data in Docker-managed volume
             can be reused
```

In common MongoDB images, `/data/db` is usually the data path. However, **verify the exact image/tag configuration** and any `--dbpath`/config flags before mounting; never assume every container uses the same path.

### Named Volume

```bash
# Run in an authorized Docker lab.
docker volume create mongo_lab_data

docker run --name mongo-lab \
  --mount source=mongo_lab_data,target=/data/db \
  mongo:8.0
```

This command demonstrates **attaching a persistent volume**, not a complete production database setup: it lacks users/auth/TLS, verified network isolation, secrets, backups, and a replica set. Do not publish the MongoDB port on a public interface.

If the container is stopped/removed and recreated with the **same named volume**, data can be reused. However, if a new container is created without attaching the volume, the result may be an **empty database**, even though the old volume still exists.

### Docker Compose

```yaml
services:
  mongodb:
    image: mongo:8.0
    volumes:
      - mongodb_data:/data/db
    # Do not publish MongoDB to the host in this example.
    # Auth, TLS, secrets, and network policy must be configured separately.

volumes:
  mongodb_data:
```

This Compose file illustrates **persistence** and must not be treated as a complete security template. In production, pin tested versions or digests, apply proper network policies and credentials, and place backups outside the deploy lifecycle volume.

### Dangerous Command: Deleting Volumes

```bash
# DO NOT run in systems with data you need to keep:
docker compose down -v
```

The `-v` flag deletes project-scoped volumes per Compose semantics. This differs sharply from standard `docker compose down`. Never assume volumes are always removed or always preserved without understanding named/external/anonymous volume declarations and lifecycles.

## 14. Docker Bind Mounts and UID/GID Errors

Named volumes and bind mounts are not the same.

| Type | Strengths | Operational Risks |
| --- | --- | --- |
| **Named volume** | Docker manages the storage path; easy to reuse across containers | Can be deleted if cleanup is misused |
| **Bind mount** | Operator selects the exact host directory | UID/GID, SELinux labels, host permissions, and paths must match |
| **Container writable layer** | Easy for one-off demos | Not persistent across container recreation |
| **Tmpfs** | In-memory/ephemeral | Never use as persistent data store |

Lab bind mount example:

```bash
docker run --name mongo-lab-bind \
  --mount type=bind,source=/srv/mongo-lab-data,target=/data/db \
  mongo:8.0
```

The source path `/srv/mongo-lab-data` must exist, reside on a supported filesystem, and allow access for the **effective UID/GID of the process inside the container**.

### Why Does It Still Fail After "chmod on the Host"?

A container may run with user namespaces or a different numeric UID than the host user name. The name `mongodb` inside a container does not necessarily map to the same owner name on the host, while the kernel evaluates numeric UID/GID under namespace mapping.

Questions to verify:

1. Which UID/GID does the container process run under?
2. What owner/mode/ACLs does the host directory have?
3. Does the Docker daemon use rootless mode or `userns-remap`?
4. Do SELinux/AppArmor policies/labels match?
5. Is the host path actually the mount source used by the container?

Never fix this with `chmod 777` or running the container as root unconditionally. Fix the identity/mount semantics and apply least privilege.

## 15. Docker: Inspecting Volumes and Resource Limits

Read-only status commands:

```bash
docker inspect mongo-lab
docker volume inspect mongo_lab_data
docker stats mongo-lab
docker logs --tail 100 mongo-lab
```

Purpose:

- `docker inspect` shows mounts, image, and runtime config.
- `docker volume inspect` shows volume metadata, not backup contents.
- `docker stats` displays CPU/memory/network/block I/O in the runtime environment.
- `docker logs` reveals permission, storage, or startup errors.

**Never exec into a container to manually edit WiredTiger files under `/data/db`.** If container startup fails, inspect logs and verify mounts/permissions first.

### Container CPU and Memory Limits

Docker provides resource limit options, for example:

```bash
# Conceptual example for a test container.
docker run --rm \
  --memory=2g \
  --cpus=1.5 \
  --mount source=mongo_lab_data,target=/data/db \
  mongo:8.0
```

A 2 GiB RAM limit is a lab assumption, **not a universal recommendation** for production MongoDB. WiredTiger cache, concurrency, workload, and other processes must fit within limits. If the memory cap is smaller than the working set, queries slow down due to I/O; if the process exceeds the cgroup limit, the container can be OOM-killed.

## 16. Kubernetes: A Pod Is Not Where Data Lives

In Kubernetes, Pods are recreated when nodes change, new images roll out, or controllers perform rolling updates. A database must never rely on a **Pod's ephemeral writable filesystem** to retain data.

Storage architecture:

```text
StatefulSet / MongoDB Operator
        |
        v
Pod mongo-0
        |
        v
PersistentVolumeClaim (PVC)
        |
        v
PersistentVolume (PV)
        |
        v
StorageClass / block storage backend
```

Key concepts:

- **PVC:** the workload's storage claim.
- **PV:** the volume resource satisfying the claim.
- **StorageClass:** defines how storage is provisioned, topology rules, and provisioner parameters.
- **StatefulSet:** manages stable identities and volume claim templates for stateful workloads.
- **MongoDB Operator/Helm deployment:** can manage replica sets and storage, but you must verify actual defaults and configuration.

**A StatefulSet alone does not replace a MongoDB replica set or backups.** StatefulSets manage identity/storage naming at the Kubernetes layer; MongoDB replication handles consistency across database members.

## 17. StatefulSet and `volumeClaimTemplates`

A Kubernetes snippet solely to illustrate **one PVC per Pod**:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mongo-lab
spec:
  serviceName: mongo-lab
  replicas: 1
  selector:
    matchLabels:
      app: mongo-lab
  template:
    metadata:
      labels:
        app: mongo-lab
    spec:
      containers:
        - name: mongod
          image: mongo:8.0
          volumeMounts:
            - name: mongo-data
              mountPath: /data/db
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
  volumeClaimTemplates:
    - metadata:
        name: mongo-data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: "20Gi"
```

This is a **storage illustration snippet**, not a production MongoDB deployment manifest: it omits Services, MongoDB replica set configuration, auth/TLS, readiness/liveness probes, resource tuning, `storageClass`, backups, topology spread, and other operator requirements.

### What Does `ReadWriteOnce` Mean?

In Kubernetes, `ReadWriteOnce` specifies that a volume can be mounted read-write by **a single node at a time** per volume/plugin semantics; it is **not** a mechanism that locks a single `mongod` process in all circumstances. Never attach the same `dbPath` for two independent MongoDB processes to write simultaneously without a supported architecture.

### One PVC per Replica Set Member

A replica set needs independent members, each with its own data path/volume per deployment. Never point all members to a shared data directory hoping to create a "shared database".

```text
mongo-0 -> PVC mongo-data-mongo-0
mongo-1 -> PVC mongo-data-mongo-1
mongo-2 -> PVC mongo-data-mongo-2
```

MongoDB replication communicates over the network via the oplog; it is **not replaced** by a shared filesystem among `mongod` processes.

## 18. Kubernetes securityContext, `runAsUser`, and `fsGroup`

Pods/containers may run under a non-root UID/GID and need write access to the PVC. You may see configuration like:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1001
    runAsGroup: 1001
    fsGroup: 1001
```

The UID/GID `1001` here are **illustrative only**, not the identity of every MongoDB image. Confirm that your chosen image/Operator supports the exact user and permissions.

### `fsGroup` Is Not Magic

Kubernetes/runtime/storage drivers may use `fsGroup` to grant group permissions on volumes per their capabilities. However:

- Not every CSI driver/backend handles it identically.
- Some setups perform recursive ownership changes, which can take a long time on volumes with millions of files.
- Existing permissions/ACLs/SELinux can still block access.
- Rootless/user namespaces and image users can complicate mapping.

If a PVC fails to mount or write, check events, effective UID/GID, and storage-driver behavior. Never add a root init container that recursively `chown`s an entire production volume without evaluating risks and downtime.

### Commands to Inspect PVCs and Pods

```bash
kubectl get pvc -n mongo-lab
kubectl describe pvc mongo-data-mongo-lab-0 -n mongo-lab
kubectl describe pod mongo-lab-0 -n mongo-lab
kubectl logs mongo-lab-0 -n mongo-lab --tail=100
```

The PVC name in the example follows a common template/StatefulSet naming pattern; on a real cluster, use the exact name returned by `kubectl get pvc`.

## 19. StorageClass, Topology, and Volume Access

A PVC can stay `Pending` because:

- No matching StorageClass exists.
- The backend lacks quota or capacity.
- The StorageClass enforces zone/topology constraints.
- The provisioner/CSI controller has an error.
- The access mode or volume mode is unsupported.
- Storage backend secrets/permissions are invalid.

### Zone Awareness

If a volume is provisioned in availability zone A while the Pod is scheduled in zone B, block storage may fail to attach. Configure topology, scheduler, and storage alignment properly, especially during failovers or rescheduling.

### Reclaim Policy and PVC Deletion

Kubernetes PVs have reclaim policies such as `Retain` or `Delete`; exact behavior depends on the StorageClass/PV and controller. In addition, StatefulSets have PVC retention policies for scaling down or deletion in supporting Kubernetes versions.

**Never assume deleting a StatefulSet always preserves all PVCs**, and never assume deleting a PVC leaves the underlying disk backend untouched. Before making changes, inspect actual retention/reclaim policies and verify backups.

### `emptyDir`

`emptyDir` is created for a Pod and is not meant to persist after the Pod is deleted. It is suitable for **temporary data**, not a long-term `dbPath`. A container restart inside the Pod may still see `emptyDir`, but that does not mean it survives the Pod's lifecycle.

## 20. RAM: WiredTiger Cache Is Not Total Memory Usage

MongoDB consumes RAM across multiple components:

```text
Process RSS / memory usage
   |
   +--> WiredTiger internal cache
   +--> Query execution buffers
   +--> Connections, threads, stacks
   +--> Internal metadata/structures
   +--> Allocator / memory overhead
   +--> TLS, compression, and driver interaction

OS memory
   |
   +--> Filesystem page cache
   +--> Kernel memory
   +--> Other processes on the host
```

**Do not treat the WiredTiger cache limit as the process's total RAM limit.** If cache is configured to 1 GiB, the process can consume significantly more than 1 GiB due to all other components.

### Why Looking Only at `free -m` Misleads

Linux uses spare RAM for page cache to speed up I/O. A host with low "free" memory but plenty of "available" memory is not necessarily critically short on RAM. Examine actual memory pressure: swap/major faults, cache eviction, OOM events, memory usage, and latency.

### WiredTiger Cache Config

MongoDB offers settings such as `storage.wiredTiger.engineConfig.cacheSizeGB`. Defaults and calculation in container/cgroup environments **depend on version, platform, and resource limits**. Never copy a hardcoded setting from a 64 GiB RAM server onto a Pod capped at 2 GiB.

If the cache is too large relative to the memory cap, the process may be OOM-killed. If the cache is too small for the working set, disk reads and query latency increase. Size the cache using metrics and workload behavior.

## 21. Container OOM and CPU Throttling

When Kubernetes/Docker caps RAM:

```text
MongoDB memory pressure
       |
       v
Container exceeds memory limit
       |
       v
OOM kill / container restart
       |
       v
MongoDB recovery on the same persistent volume
       |
       v
Workload disrupted
```

If the volume is ephemeral, a restart/recreation can cause data loss. Even with a persistent volume where the storage engine recovers via supported mechanisms, downtime and crash loops remain severe incidents.

### CPU Requests and Limits

- **CPU request** helps the scheduler place the Pod based on reserved resources.
- **CPU limit** can trigger throttling when the workload tries to use more CPU than its quota.
- **Memory request/limit** affects scheduling and OOM behavior.

For example, setting a CPU limit too low on an aggregation-heavy workload can spike p95/p99 latency even while the disk is idle. Conversely, leaving resources uncoordinated can cause MongoDB to contend with neighboring services.

### Reading Signals from Kubernetes

```bash
kubectl top pod -n mongo-lab
kubectl describe pod mongo-lab-0 -n mongo-lab
```

Inspect `Last State: OOMKilled`, restart counts, events, and cgroup/Prometheus metrics if available. `kubectl top` requires a working metrics server and does not replace historical monitoring.

## 22. File Descriptors and `ulimit`

Each network connection, socket, and open file can consume a process **file descriptor** on Unix-like systems. When MongoDB serves many connections and accesses many data files, too low a limit can trigger file/socket open errors.

Inspection commands on Linux:

```bash
# Limit of the current shell (not necessarily mongod):
ulimit -n

# Inspect limits of the running mongod process:
pidof mongod
cat /proc/<mongod-pid>/limits
```

In the final command, replace `<mongod-pid>` with the actual PID before running; it is a placeholder, **not literal shell syntax**.

### Why Changing `ulimit -n` in a Terminal Often Fails to Fix the Service

A `mongod` started by systemd inherits resource limits from the **service manager/unit configuration**, not necessarily from an operator's SSH shell.

Inspection example:

```bash
systemctl show mongod -p LimitNOFILE -p TasksMax -p MemoryMax
systemctl cat mongod
```

When an actual change is needed, use a systemd drop-in following configuration management procedures and perform a controlled restart, rather than editing the vendor unit file or setting `ulimit` in an unrelated shell.

### Other Limits

| Limit | Impact |
| --- | --- |
| Number of open files (NOFILE) | Connections/file handles |
| Max processes/threads (NPROC/TasksMax) | Threads and process resources |
| Virtual memory/address space | Memory allocation capability |
| cgroup memory limit | OOM kill if exceeded |
| cgroup CPU quota | CPU throttling |
| PID limit | Unable to spawn new threads/processes |
| Disk quota/inodes | Unable to create/write additional files |
| Connection limit | Clients rejected or queued on the server |

Specific recommended values must be checked against **MongoDB production notes for your exact version, OS, and topology**. No single `ulimit -n` figure fits every scale.

## 23. Full Filesystem, Full Inodes, and Read-Only Remounts

Three distinct faults can all manifest as MongoDB failing to write:

1. **Out of bytes:** `df -h` shows the filesystem is full.
2. **Out of inodes:** `df -i` shows inode allocation is exhausted despite remaining byte capacity.
3. **Filesystem switched to read-only:** due to I/O errors, policy, or disk problems, new writes/creations fail.

Status commands:

```bash
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt /var/lib/mongodb
```

`findmnt` identifies the actual mount and its options; paths may vary by deployment. If the expected mount is missing yet the service starts anyway, `dbPath` may inadvertently sit on the host's **root filesystem** instead of the intended data disk.

### Never Fix Disk-Full by Deleting WiredTiger Files

Deleting a data, index, or journal file inside `dbPath` can cause corruption. Appropriate measures include:

- Identifying the real volume and growth trend.
- Expanding capacity/IOPS through supported methods.
- Checking oplog, indexes, retention, logs, and backups to pinpoint space consumers.
- Cleaning up business data through MongoDB APIs and policies, never via the filesystem.
- Preparing a recovery plan if the disk has already entered an error state.

Even deleting many MongoDB documents does not necessarily reduce filesystem usage immediately: the storage engine may retain pages for reuse. Do not treat an immediate drop in `df` as the sole metric of cleanup success.

## 24. Swap, Memory Pressure, and Kernel Tuning

Recommendations on Transparent Huge Pages (THP), swap, kernel limits, and memory management **change across MongoDB versions and operating systems**. Do not apply a rigid rule like "always disable THP" or "always enable THP" across all MongoDB releases.

Before changing kernel/VM tuning:

1. Record the MongoDB version, OS/kernel, and storage engine.
2. Check the matching MongoDB **production notes**.
3. Capture baseline state and metrics.
4. Test in a production-like environment.
5. Prepare a rollback and ensure changes persist across reboots if needed.

### What Can Swap Cause?

When hot working sets are pushed into swap, query latency can spike sharply. However, blindly disabling all swap on a memory-constrained host can cause earlier OOM kills. Size RAM and cgroups properly instead of blaming swap alone.

## 25. Permissions on Logs, Sockets, Certificates, and Backups

Many engineers check only `dbPath` while overlooking other paths:

| Component | Example | Permissions to Check |
| --- | --- | --- |
| Data | `/var/lib/mongodb` | `mongod` needs read/write/traverse |
| Log | `/var/log/mongodb/mongod.log` | `mongod` needs file write and directory traverse |
| TLS private key | `/etc/mongodb/tls/server.pem` | `mongod` needs read; do not expose to all users |
| Internal keyfile | `/etc/mongodb/keyfile` | Strictly restricted permissions per security requirements |
| PID/socket directory | `/run/mongodb` | May be managed by systemd/tmpfiles |
| Backup archive | `/backup/mongodb/...` | Backup service needs write; access controlled separately |

### Never Place TLS Keys in a Publicly Accessible Data Volume

Private keys and credentials must be managed through a secret/certificate lifecycle. Do not move them into a broadly readable shared folder just so a container can read them.

### Backups Need Sufficient Access, Not Full Host Privileges

Backup tools/agents need to read data via supported APIs or snapshot mechanisms and write to the backup target. They do not need `chmod -R 777` on the data directory. Apply least privilege and use dedicated credentials for backup/restore.

## 26. Replica Sets: Persistence and Durability Across Multiple Nodes

A replica set consists of multiple `mongod` instances:

```text
Application
      |
      v
Primary mongod    -> data volume A
      |
      +--> Secondary 1 -> data volume B
      |
      +--> Secondary 2 -> data volume C
```

Each member needs **its own data path and persistent storage**. Replica sets replicate operations via MongoDB replication; members never write to a shared data directory.

### What Can Still Go Wrong Even with Three Members

- All three volumes share the same storage failure domain.
- Backups capture an inconsistent snapshot of a single volume.
- Clients use a write concern mismatched to RPO.
- An operator accidentally drops a collection and the drop replicates.
- Disk saturation hits multiple members simultaneously.
- Permissions change during an image/package upgrade, preventing multiple members from starting.

A replica set provides **availability and fault tolerance** within its design boundaries; it does not replace backups, data validation, or capacity planning.

### Oplog and Disk

The oplog stores operation history for replication and change streams per supported mechanisms. Oplog size and retention affect:

- A secondary's ability to catch up with the primary.
- The ability to resume change streams within the retained window.
- Required disk space allocation.

The oplog is not an arbitrary backup and cannot be treated as an infinite immutable history log. Size it based on write rate, maximum tolerated downtime, replication lag, and CDC needs.

## 27. Consistent Backups Matter More Than Copying Directories

An anti-pattern:

```bash
# DO NOT use as a safe backup method for a running MongoDB instance:
cp -r /var/lib/mongodb /tmp/mongo-backup
```

While `mongod` is writing, sequential file copies can capture data and journal files at **different points in time**, producing an inconsistent backup.

Options to evaluate per version/topology:

- **Logical backups** via `mongodump` where appropriate.
- **Filesystem/storage snapshots** using a MongoDB-supported consistent snapshot method.
- Backup agents/managed backup services capable of PIT/cluster-aware backups.
- **MongoDB Atlas managed backups** on supported tiers/configurations.

### Backups Also Need Their Own Operational Environment

- Never store all backups on the same disk as the database.
- Verify permissions and encryption for backups.
- Enforce retention and backup immutability where required.
- Measure restore speed and verify data integrity.
- Confirm backups include the right databases, roles/configurations, and dependencies needed for recovery.

**An untested backup is an unproven backup.**

## 28. Examples of Monitoring Disk, Process, and Storage with Read-Only Commands

On Linux:

```bash
# Capacity and mounts:
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt /var/lib/mongodb

# RAM and CPU:
free -h
vmstat 1 5

# Process and resource limits:
ps -eo user,group,pid,rss,cmd | grep '[m]ongod'
systemctl show mongod -p LimitNOFILE -p TasksMax -p MemoryMax

# Storage devices:
lsblk -f
```

If `sysstat` tools are installed:

```bash
iostat -xz 1 5
```

In some container/cloud environments, host commands/metrics may not expose full block-device I/O directly. Cross-check cloud volume metrics, cgroup metrics, and your monitoring server.

### Reading Metrics from MongoDB

In `mongosh`, with appropriate privileges:

```javascript
db.adminCommand({ serverStatus: 1 });

db.getSiblingDB("appdb").stats();

db.getSiblingDB("appdb").orders.stats();
```

Focusing on the WiredTiger cache:

```javascript
const status = db.adminCommand({ serverStatus: 1 });
printjson(status.wiredTiger?.cache);
```

Specific metric fields vary across MongoDB versions/storage engines and may require privileges. Never copy metric names assuming every server returns the exact same structure.

### Never Expose `serverStatus` to the Internet

Server metrics and config can reveal sensitive operational details. Restrict monitoring, dashboards, and log access per organizational policy.

## 29. Signals to Alert On Before Incidents Occur

| Category | Example Signal | Investigation Action |
| --- | --- | --- |
| Disk | Free space shrinking fast | Forecast exhaustion date; inspect growth/indexes/oplog |
| Disk I/O | Rising latency and queue depth | Check volume limits, burst credits, concurrent jobs |
| Memory | OOM kills, cache pressure, swap | Check cgroups, WiredTiger cache, working set |
| CPU | Sustained saturation/throttling | Inspect queries, aggregations, and CPU quotas |
| Filesystem | Read-only remount, I/O errors | Investigate storage/backend; halt further writes if unsafe |
| Process | Unexpected `mongod` restarts | Read logs, systemd/Kubernetes events |
| Limits | Too many open files | Inspect NOFILE and connection growth |
| Replication | Growing lag or unhealthy member | Check network/disk/CPU/oplog |
| Backups | Failed jobs or failed restore tests | Remediate before a real outage |
| K8s | PVC Pending, VolumeAttachment errors | Inspect CSI/topology/quotas |
| Security | Ownership/ACL/cert changes | Review deployments/automation |

Thresholds must match workload and desired response time. A small database growing 1 GiB/day differs completely from a workload growing 100 GiB/hour.

## 30. Common Incidents and Layering Root Causes

### Incident A: New Container Starts, Collections Vanish

Possibilities:

- The old container used its writable layer instead of a named volume.
- The new container mounted a **different volume**.
- The Compose project name changed, creating a new named volume.
- `dbPath` changed while the mount stayed on the old path.
- The app pointed to a different database or connection URI.

Inspect:

```bash
docker inspect mongo-lab
docker volume ls
docker volume inspect mongo_lab_data
```

Never rush to run `mongorestore` onto the new container before verifying **whether the old volume still exists**. It may just be a wrong mount rather than actual data loss.

### Incident B: MongoDB Fails to Start After Moving a Volume

Possibilities:

- Different UID/GID/permissions.
- Read-only mount or wrong mount path.
- Mismatched SELinux/AppArmor labels.
- Image/server version incompatible with data files.
- Filesystem/storage I/O errors.

Read logs and inspect mounts/ownership first. Never run `--repair` as a knee-jerk reaction; storage repair operations carry risk and must follow your MongoDB version's recovery procedure and backups.

### Incident C: Pod `CrashLoopBackOff`

Possibilities:

- `OOMKilled` due to low memory limit.
- PVC `Pending` or attachment failure.
- `Permission denied`.
- Config/TLS/internal auth errors.
- Health probes misconfigured for recovery duration.

Diagnose:

```bash
kubectl describe pod mongo-lab-0 -n mongo-lab
kubectl logs mongo-lab-0 -n mongo-lab --previous
kubectl describe pvc mongo-data-mongo-lab-0 -n mongo-lab
```

Do not raise memory limits when the root cause is a storage mount failure, and do not `chown` a PVC when the cause is an OOM kill.

### Incident D: Database Is Slow While CPU Is Low

Possibilities:

- High disk latency, throughput/IOPS cap.
- Working set exceeds cache/RAM.
- Page faults or swapping.
- A backup or index build competing for I/O.

Inspect `iostat`, cloud disk metrics, and WiredTiger cache/eviction metrics instead of just adding vCPUs.

## 31. Upgrading MongoDB: Check Storage Before Swapping Binaries

Upgrading MongoDB can affect:

- Metadata/storage format and backward compatibility.
- Filesystem/OS support.
- Index builds or background operations.
- Default resource consumption.
- Kernel tuning recommendations.
- Driver/protocol compatibility.
- Feature Compatibility Version (FCV) and rolling upgrade procedures.

**Never take data files from a newer version and arbitrarily start an older binary on the same `dbPath`.** Compatibility and upgrade/downgrade paths are constrained by MongoDB version.

### Preflight Storage and Resource Checklist

1. Identify source/target MongoDB versions, FCV, topology, and OS.
2. Read the corresponding **release notes** and **upgrade path**.
3. Confirm sufficient disk headroom for indexes, migrations, and temporary operations.
4. Measure IOPS, CPU, RAM/cache, and replication lag under normal load.
5. Verify data volumes, mount paths, and ownership persist across deployment.
6. Check whether the new image/package changes the service user UID/GID or paths.
7. Verify `ulimit`/systemd/cgroup and kernel recommendations for the new release.
8. Ensure verified backups exist and restore has been rehearsed.
9. Test the upgrade in a staging environment with representative volumes/data.
10. Have a **supported rollback plan**, not just swapping back the image tag.

### Rolling Upgrade Does Not Mean "Restart Everything at Once"

For replica sets, you must normally follow MongoDB's upgrade order and quorum/primary availability rules. For sharded clusters, follow dedicated procedures for config servers, shards, and routers. Never restart all nodes simultaneously or delete StatefulSets/PVCs just to roll out a new image.

## 32. Why Directory Permissions Can Break After an Upgrade

A new OS package or container image may introduce:

- A different service user/group name.
- A different numeric UID/GID.
- Different data/log/config paths.
- Tighter systemd sandboxing.
- Different security profiles or file labels.
- Different volume mount mechanics due to chart/operator changes.

Example:

```text
Before upgrade:
  /srv/mongo-data owned by UID 999

After upgrade:
  mongod runs as UID 1001

Without matching group/ACL:
  Permission denied when opening data files
```

This is an illustrative scenario, **not a claim that a specific MongoDB image uses UID 999 or 1001**. Check release notes and inspect the actual image/process.

To prevent this:

1. Pin tested image/package versions.
2. Record the current effective service UID/GID.
3. Test upgrades with a **volume copy** in a lab.
4. Check filesystem ownership and SELinux/AppArmor policies.
5. Plan permission transitions if changes are needed.
6. Never recursively re-own millions of files mid-downtime without estimating I/O and duration.

## 33. Procedure for Moving Data to a New Disk

Suppose you need to move `dbPath` from a small disk to a larger volume.

**Do not** simply put a new `storage.dbPath` line in the config and restart while old data stays at the previous path; MongoDB may see an empty directory and initialize a fresh database, or fail configuration checks.

Conceptual plan:

1. Identify topology (standalone/replica set/sharded).
2. Choose a MongoDB-supported migration method: e.g., adding a new member for initial sync, backup/restore, or stopping the service cleanly and copying data via a supported consistent procedure.
3. Ensure backups and RPO/RTO are approved.
4. Prepare the filesystem/disk, mount point, and owner/permissions.
5. Move or synchronize data through a **consistent** process; never copy live files arbitrarily.
6. Update `dbPath`/volume mappings and service configuration.
7. Start up and inspect logs/recovery, replica status, collections, and indexes.
8. Validate checksums/business data per policy.
9. Retain the old volume for the defined rollback window rather than deleting it immediately.

### Replica Sets Can Minimize Downtime

Instead of copying live files from a primary, you can plan rolling member replacements with new volumes and let MongoDB handle initial sync/replication via supported procedures. This requires adequate disk, CPU, and network capacity plus careful monitoring of replication lag and quorum. Never treat it as an automated single-command "volume swap" for all topologies.

## 34. MongoDB Atlas: What Is Managed by the Service

With MongoDB Atlas, users typically do not directly:

- Run `chown` on `dbPath` directories on Atlas-managed nodes.
- Edit systemd limits on MongoDB hosts.
- Mount PVCs onto Atlas-managed `mongod` processes.
- Delete journal or data files on nodes.

Atlas provides capacity, storage, and managed service options based on cluster tier and deployment. Operators remain responsible for:

- Selecting cluster sizes and storage adequate for the workload.
- Monitoring CPU, memory, disk, IOPS/latency, and replication lag using provided metrics.
- Managing database users, network access, and application permissions.
- Configuring backup/restore, retention, and testing restores.
- Monitoring capacity/autoscaling alerts where enabled.
- Verifying upgrade impact, driver compatibility, and application behavior.

**Never apply Linux VM `chmod`/`chown` instructions to Atlas-managed nodes.** When an Atlas cluster hits resource or storage limits, use supported scaling, configuration, and managed support mechanisms rather than trying to alter internal files.

## 35. Comparison Table Across Runtime Environments

| Criterion | Linux VM/Bare Metal | Docker/Compose | Kubernetes | Atlas |
| --- | --- | --- | --- | --- |
| Data path | `storage.dbPath` on filesystem | `dbPath` in container, mounted volume | PVC/PV via StatefulSet/Operator | Managed |
| Persistence | Operator-managed volume/partition | Named volume/bind mount | PVC/PV and reclaim policy | Managed infrastructure |
| File permissions | OS user/group/ACL/SELinux | UID/GID/container namespace/host mount | `runAsUser`/`fsGroup`/CSI/security context | Not directly edited |
| RAM/CPU | Host/process limits | Docker/cgroup limits | Requests/limits/cgroup | Cluster tier/config |
| Open files | `ulimit`/systemd | Host/container limits | Container/runtime/node limits | Managed |
| Disk metrics | `df`/`iostat`/cloud disk | Docker/host disk metrics | PVC/CSI/cloud volume metrics | Atlas metrics |
| Backup | Self-managed or backup service | Backup outside container volume | Operator/cluster-aware backup | Managed backup per feature |
| Upgrade | Package/binary + FCV procedure | Image + data volume compatibility | Operator/StatefulSet upgrade | Atlas release/upgrade policy |
| Common risks | Wrong permissions, disk full | Lost volume/wrong mount | PVC/attach/zone/OOM | Sizing/backup/network/migration |

No environment eliminates the need for **monitoring storage, resources, and data recovery**; environments only differ in who holds access and responsibility at each layer.

## 36. Diagnostic Runbook When MongoDB Fails to Start After Deploy

### Step 1 — Determine Scope

```text
Service process crashing?
Container OOMKilled?
Pod PVC Pending?
MongoDB starts but database is empty?
One secondary unhealthy or entire cluster offline?
```

### Step 2 — Preserve Evidence

- Do not delete files inside `dbPath`.
- Do not create a new volume and overwrite the old one without knowing its state.
- Do not run `mongod --repair` arbitrarily.
- Do not set directory permissions to `777`.
- Collect logs, events, and mount/UID/GID details before taking action.

### Step 3 — Inspect the Environment

| Platform | Information to Collect |
| --- | --- |
| VM | `systemctl status`, logs, `df`, `findmnt`, `ls -ld`, limits |
| Docker | `docker inspect`, logs, volume name, image, memory limits |
| Kubernetes | Pod events, PVC/PV, storage class, security context, OOM state |
| Atlas | Cluster alerts, metrics, backup status, recent configuration changes |

### Step 4 — Classify Root Cause

```text
Permission denied -> owner/mode/ACL/SELinux/UID
No space left      -> capacity/inodes/quota
Read-only FS       -> storage/backend/filesystem
OOMKilled          -> memory limit/cache/query load
Too many files     -> NOFILE/connections
Volume not found   -> mount/PVC/StorageClass/topology
Invalid config     -> image/package/version change
Data corruption    -> backup/recovery protocol; do not edit manually
```

### Step 5 — Controlled Recovery

Once root cause is identified and a backup/rollback plan is ready:

1. Apply the minimal change at the exact right layer.
2. Restart following the proper order and quorum rules.
3. Confirm `mongod`/members are healthy.
4. Read actual data and run business queries; do not rely solely on `ping`.
5. Check replication lag and write concern behavior.
6. Monitor CPU, RAM, disk latency, and errors.
7. Write an incident report and preventive actions.

## 37. Common Failure Patterns

| Symptom | Likely Root Cause | Approach |
| --- | --- | --- |
| New container has empty DB | Forgot to mount volume or different `dbPath` | Inspect mounts, locate old volume |
| `Permission denied` opening WiredTiger | Wrong UID/GID/ACL/SELinux | Verify user/mount/policy; apply minimal fix |
| `No space left on device` | Data/index/journal/oplog/logs full | Forecast capacity, expand storage, enforce cleanup policy |
| `Read-only file system` | FS remounted RO or volume policy | Investigate storage backend |
| `Too many open files` | Low NOFILE or connection leak | Inspect process limits and workload |
| `OOMKilled` | Memory cap/WiredTiger cache/query pressure | Right-size memory, inspect metrics/cache |
| CPU throttling, p99 spikes | Low cgroup CPU quota | Measure quota, query load, tune resources |
| PVC `Pending` | CSI/quota/StorageClass/zone | Describe PVC/events |
| Pod cannot attach PV | Topology/attachment conflict | Check node zone and AccessMode |
| MongoDB slow with low CPU | Disk I/O latency, page faults/swap | Inspect `iostat` and WiredTiger cache |
| Data files on root FS instead of data disk | Wrong mount or unmounted volume | Check `findmnt`/`df` before writing |
| Backup cannot restore | Live file copy or inconsistent backup | Switch to supported backup and restore testing |
| Data lost after `down -v` | Docker volumes deleted | Restore backup, fix deploy runbook |
| Primary failover loses writes | Mismatched write concern/RPO | Review write concern and replica health |
| Startup failure after image swap | UID/version/storage incompatibility | Upgrade preflight, backup, rollback |
| Same PVC shared across multiple members | Shared `dbPath` without isolation | Dedicated volume per member |
| Large disk yet queries stay slow | Low IOPS/high latency | Measure storage performance, not just capacity |
| Database healthy but logs fill volume | Missing log rotation/retention | Configure log lifecycle |

## 38. Exercises with Answers

### Exercise 1. MongoDB runs, but data disappears when the container is deleted

A developer runs a MongoDB container without mounting a volume. After `docker rm` and recreating it, the database is empty. Why?

**Answer:** Data was stored in the old container's writable layer with no persistent volume reused. You need a proper named volume/bind mount at `dbPath` plus separate backups.

### Exercise 2. With a volume, do we still need backups?

MongoDB uses a named Docker volume; a developer accidentally drops an entire collection. Can the volume recover the old data?

**Answer:** No. The volume persists the effects of the drop command as well. You need an appropriate backup/snapshot/PIT strategy.

### Exercise 3. `bindIp` and filesystem permissions

The `mongod` log reports `Permission denied` when opening a WiredTiger file. Will changing `bindIp` to `0.0.0.0` help?

**Answer:** No. That is a filesystem permission error, not a network listener issue. Inspect `dbPath`, service UID/GID, ownership, mounts, and SELinux/AppArmor.

### Exercise 4. Ownership

`/srv/mongo-data` is owned by root, while the MongoDB service runs under a non-root UID. Should you run `chmod -R 777`?

**Answer:** No. Verify the true UID/GID and path/mount, then grant least-privilege permissions through proper ownership, group, ACL, or policy.

### Exercise 5. When disk is nearly full

An operator notices journal/data files consuming substantial space and wants to delete files manually from `dbPath`.

**Answer:** Never do that. These are internal storage engine files. Investigate disk usage, expand capacity, apply API-level retention/cleanup, and follow the official runbook.

### Exercise 6. Write concern

An application uses `w:1` on a replica set and the primary fails abruptly. Can you guarantee every acknowledged write survived failover?

**Answer:** No. `w:1` does not provide majority acknowledgment guarantees. Choose write concern based on RPO and understand your replica set configuration.

### Exercise 7. Does `majority` replace backups?

A user accidentally deletes data and the deletion replicates to a majority.

**Answer:** Majority confirms that the operation replicated per policy—including accidental deletions. It cannot restore deleted history; you need backups/PIT recovery.

### Exercise 8. Cache

A Pod has a 2 GiB memory limit, and the WiredTiger cache is set close to the full 2 GiB. What is the risk?

**Answer:** MongoDB uses RAM outside the WiredTiger cache as well; the Pod can be OOM-killed. Size the cache and cgroups properly while monitoring actual RSS and working set.

### Exercise 9. CPU

MongoDB p95 latency rises after setting a very low CPU limit while disk metrics look normal. What could cause this?

**Answer:** CPU throttling can slow down query execution. Inspect cgroup CPU metrics and query workload, then adjust requests/limits with evidence.

### Exercise 10. Storage

A volume has 500 GiB free, yet I/O latency stays high and the database is slow. Will increasing storage capacity definitely solve it?

**Answer:** No. Evaluate IOPS, throughput, disk latency, and volume limits. Capacity and performance are independent dimensions.

### Exercise 11. Systemd `ulimit`

An operator runs `ulimit -n 100000` in an SSH terminal, yet the `mongod` service still reports `Too many open files`.

**Answer:** A systemd-managed service has its own resource limits. Inspect effective `LimitNOFILE` and apply a drop-in configuration per procedure rather than setting limits in an interactive shell.

### Exercise 12. Kubernetes `emptyDir`

MongoDB uses `emptyDir` for `dbPath`, and the Pod is deleted and recreated. Is data guaranteed to remain?

**Answer:** No. `emptyDir` is bound to the Pod lifecycle; use PVC/PV for persistent data.

### Exercise 13. One PVC for three MongoDB members

Three replica-set members mount the exact same directory to "save disk space".

**Answer:** Invalid. Every member must have its own data path; MongoDB replication does not synchronize via a shared `dbPath`.

### Exercise 14. StorageClass and zones

A PVC is provisioned in zone A, while the Pod is scheduled in zone B and cannot attach the volume.

**Answer:** Inspect storage topology, scheduling, binding mode, and CSI/zone constraints; this is not a MongoDB query bug.

### Exercise 15. `fsGroup`

`fsGroup` is configured, yet the Pod still cannot write to the PVC.

**Answer:** Not all storage drivers and ownership setups support identical semantics. Check effective UID/GID, volume ACL/SELinux, CSI driver, and events; do not arbitrarily `chown` the whole volume.

### Exercise 16. Disk space and inodes

`df -h` shows many GiB free, yet `mkdir`/file writes fail claiming no space left.

**Answer:** Inodes may be exhausted, a quota hit, or the filesystem mounted read-only; use `df -i`, `findmnt`, and storage metrics to distinguish.

### Exercise 17. Image upgrade

A new MongoDB image runs under a different UID than the owner of a bind-mounted data directory.

**Answer:** This can cause `Permission denied`. Preflight checks must verify UID/GID and plan controlled permission transitions; never launch a new image blindly against a production volume.

### Exercise 18. Changing `dbPath`

An operator changes the path to a new empty volume and sees an empty database even though the old volume still holds data.

**Answer:** MongoDB is reading a different `dbPath`; verify mounts/config and perform a consistent data migration. Do not rush to delete or overwrite the old volume.

### Exercise 19. Backing up a live directory

A shell script runs `cp -r /var/lib/mongodb` while MongoDB receives writes. Is this a reliable backup?

**Answer:** It cannot be assumed reliable. Files may be copied at inconsistent timestamps. Use logical backups, consistent snapshots, or backup services per MongoDB-supported procedures.

### Exercise 20. Atlas

An application uses MongoDB Atlas and receives disk/capacity alerts. Should you SSH into the Atlas node to run `chmod` or delete the journal?

**Answer:** No. Atlas manages nodes and storage. Check cluster sizing, metrics, autoscaling, and backups, and use supported managed operations.

### Exercise 21. Cleaning up volumes during deploy

A team routinely runs `docker compose down -v` before every deployment. What is the risk?

**Answer:** It can delete named/anonymous volumes per Compose semantics, wiping MongoDB data. Never use `-v` on persistent databases without explicit intent and backups.

### Exercise 22. Replica set and storage failure domain

A three-member replica set places all three data volumes on the same failure-prone disk backend.

**Answer:** If that backend fails, all three members can lose data or availability. Design independent failure domains, replica placement, and backups.

### Exercise 23. Monitoring

Is monitoring only CPU and connection count sufficient to ensure MongoDB stability?

**Answer:** No. You must also monitor disk capacity/latency, WiredTiger cache, memory/OOM, file descriptors, replication lag, backups, and PVC/mount health.

### Exercise 24. FCV

After upgrading MongoDB binaries, a team wants to enable all new features immediately and revert only the binary if something fails.

**Answer:** Unsafe. Follow supported upgrade/FCV and downgrade paths, backed by verified backups and restore plans. Storage format changes and feature flags can complicate rollbacks.

## 39. Persistent Operations Checklist

### Storage

- [ ] Actual `dbPath` verified on the right filesystem/volume.
- [ ] Data volume survives container/Pod recreation by design.
- [ ] Backups reside outside the same failure domain and are restore-tested.
- [ ] Disk capacity accounts for data, indexes, journal, oplog, and upgrade headroom.
- [ ] Storage IOPS/latency meets SLA under representative load.
- [ ] Filesystem and mount options are compatible with the MongoDB/OS version.
- [ ] No scripts directly modify or delete WiredTiger files.

### Permissions and Security

- [ ] Effective service user/UID/GID confirmed before setting ownership.
- [ ] Data/log/keyfile paths have only necessary permissions.
- [ ] Parent directories, ACLs, SELinux/AppArmor, and systemd sandboxing checked.
- [ ] Docker bind mounts and Kubernetes PVCs align with security context.
- [ ] Never use root or `chmod 777` as a default workaround.
- [ ] Secrets, TLS private keys, and backups are protected separately.

### Resources

- [ ] RAM/cgroup limit includes headroom beyond the WiredTiger cache.
- [ ] CPU quotas and throttling are monitored.
- [ ] Disk latency, IOPS, free capacity, and inodes have alerts.
- [ ] `NOFILE`/process limits verified on the **actual process**, not just a shell.
- [ ] Alerts exist for `OOMKilled`, `CrashLoopBackOff`, and PVC Pending/attachment errors.
- [ ] Replication lag, oplog, and all members are monitored.

### Upgrades and Recovery

- [ ] MongoDB version, FCV, and supported upgrade path verified.
- [ ] Image/package updates do not unexpectedly alter data paths or UIDs.
- [ ] Sufficient disk/resource headroom reserved for migration/index work.
- [ ] Backups verified and restore-tested.
- [ ] Rolling upgrade follows proper order while preserving quorum/availability.
- [ ] Realistic rollback plan in place—not merely reverting an image tag.
- [ ] Application reads/writes and durability verified after upgrade.

## 40. Summary

MongoDB **persistent storage** is more than "having a disk". You must ensure `storage.dbPath` sits on a volume whose lifecycle is independent of the process/container/Pod, that the filesystem and storage backend satisfy durable write requirements, that capacity and IOPS are sufficient, and that backups and restores are verified. **Write concern, journaling, replication, and backups** protect against different failure modes; no single layer replaces the others.

**Directory permissions** must match the actual user/UID/GID running `mongod`, alongside Unix permissions, ACLs, SELinux/AppArmor, systemd sandboxing, and container/PVC contexts. `Permission denied` is a signal to verify the **right mount, right process, and right policy**, not an invitation to run as root or apply `chmod 777`.

**Resource limits** must be treated as part of database design: WiredTiger cache is not total RAM, CPU quotas can trigger throttling, disk I/O can bottleneck while space remains free, and file-descriptor limits can break connections. For Docker and Kubernetes, volume lifecycles, cgroups, PVCs/StorageClasses, and topology introduce extra layers requiring monitoring.

Before any upgrade, record version/FCV, data paths, permissions, volume mappings, resource limits, and backups. Sound operations follow **observe first, change the right layer, verify recovery, and re-measure post-deploy**—rather than hot-patching inside data directories during an incident.

### Version-Specific Official References

- [MongoDB Manual — Storage Engines](https://www.mongodb.com/docs/manual/core/storage-engines/)
- [MongoDB Manual — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Configuration Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — Production Notes](https://www.mongodb.com/docs/manual/administration/production-notes/)
- [MongoDB Manual — UNIX ulimit Settings](https://www.mongodb.com/docs/manual/reference/ulimit/)
- [MongoDB Manual — Upgrade Procedures](https://www.mongodb.com/docs/manual/release-notes/)
- [Kubernetes Documentation — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes Documentation — StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
