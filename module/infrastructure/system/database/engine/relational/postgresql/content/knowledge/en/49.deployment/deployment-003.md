# Persistent Volumes, Directory Permissions, and Container Lifecycle in PostgreSQL Deployments

Packaging PostgreSQL in a container standardizes the runtime environment, but a container is not a place for long-term data storage. Containers can be deleted and recreated during deployments, rescheduling, image upgrades, or incident recovery. If the database only writes to the container's writable layer, data can vanish along with the container.

For safe deployment, the lifecycle of the PostgreSQL server must be decoupled from the container lifecycle. The data directory, WAL, tablespaces, and files required for recovery must reside on storage with a clearly managed lifecycle. A new container must be able to reattach the exact volume, run as a user with the appropriate UID/GID and permissions, read configuration, start the existing database, and continue serving the workload.

This lesson explains how to choose persistent volumes, bind mounts, and PVCs; how to lay out `PGDATA`, WAL, and tablespaces; how to handle ownership, mode bits, SELinux, and Kubernetes security contexts; and how to operate stop/restart/recreate, backup/restore, failover, and upgrades for PostgreSQL in containers. Examples use Docker/Compose and Kubernetes, though the principles apply to other container runtimes and orchestration platforms.

This lesson belongs to the **Deployment** chapter of the *Database Engine Relational PostgreSQL* module.

> **Principle:** Containers are replaceable; the database cluster must have its own storage and recovery plan. Never let a container delete/recreate operation accidentally remove the data volume, and never attach the same PostgreSQL data directory to multiple running servers.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between the container writable layer, bind mounts, named volumes, and Kubernetes PersistentVolumes.
2. Choose an appropriate storage type for the PostgreSQL data directory.
3. Lay out `PGDATA`, `pg_wal`, tablespaces, configuration, and backup locations.
4. Understand mount semantics and how mounts obscure existing content in an image.
5. Configure UID/GID, ownership, directory modes, and file permissions.
6. Handle rootless containers, user namespace mapping, and Kubernetes security contexts.
7. Identify SELinux label and filesystem permission issues.
8. Evaluate filesystems, block storage, latency, IOPS, and durability.
9. Manage PVCs, StorageClasses, StatefulSets, and volume retention.
10. Understand container stop signals, graceful shutdown, restarts, and crash recovery.
11. Design readiness, liveness, and startup probes suitable for PostgreSQL.
12. Perform backups/restores and snapshots with appropriate consistency.
13. Ensure WAL, archives, and tablespaces are stored durably.
14. Execute safe rolling updates and major-version upgrades.
15. Avoid mounting the same data directory simultaneously across multiple PostgreSQL instances.
16. Monitor storage capacity, I/O, permissions, and volume health.
17. Build runbooks for permission errors, missing volumes, and failed startups.
18. Create operational and recovery checklists for PostgreSQL containers.

## 2. Container Filesystems and Persistent Storage

A container has a filesystem view composed of image layers and a container writable layer. When a container is removed, its writable layer is typically deleted as well. Externally mounted storage has a lifecycle independent of the container.

### 2.1. The Writable Layer Is Not Database Storage

If PostgreSQL writes to a path without a volume mount, data resides in the writable layer. When the container is recreated from a new image, the old container and its layer can be discarded. The new image does not contain transactions committed in the old container.

Never use the writable layer to store `PGDATA` for a database that must persist across deployments or restarts.

### 2.2. Persistent Volumes Decouple Data from Containers

A persistent volume enables:
- Deleting and recreating containers while preserving database files.
- Upgrading images while keeping storage intact.
- Attaching the volume to a new node/container per platform procedures.
- Decoupling data lifecycle management from image lifecycle.
- Performing backups/snapshots via the storage platform.

Persistent storage is not automatically a backup. If a volume is deleted, corrupted, or data is accidentally dropped, an independent copy is still required.

### 2.3. Common Mount Types

| Type | Managed At | Characteristics | Suitable Use Cases |
|---|---|---|---|
| Container writable layer | Runtime | Tied to the container | Cache/temporary files; never for PGDATA |
| Named volume | Docker/Podman | Runtime manages lifecycle | Single-host databases or Compose environments |
| Bind mount | Host path | Mounts specific directory/file from host | Integrating host-managed storage/backups/config |
| tmpfs | Host memory | Lost when container stops/recreates | Temporary data not requiring durability |
| Kubernetes PVC | Kubernetes/storage provider | Requests storage with independent lifecycle | Stateful workloads |
| Cloud block disk | Cloud provider | Block device attached to node | Databases needing persistent block storage |
| Network filesystem | NAS/storage service | Shared over the network | Use only when PostgreSQL/provider supports required semantics and performance |

### 2.4. Differences Between Named Volumes and Bind Mounts

Named volumes are managed by the container runtime, allowing Compose or the runtime to reference them by a stable name. Bind mounts reference a specific path on the host, so permissions, SELinux labels, backups, and path provisioning are managed more directly by the host/platform.

### 2.5. Mounts Can Obscure Image Contents

When mounting a bind mount over a non-empty directory in an image, the original contents at the mountpoint are hidden inside the container. Named volumes may have different initialization/copy behaviors depending on runtime and options. Do not rely on contents pre-packaged inside an image to store a database; inspect the actual mountpoint and volume.

### 2.6. tmpfs Is Not Persistent Storage

`tmpfs` is suitable for intentionally temporary data. Never mount `PGDATA`, `pg_wal`, or long-lived tablespaces on `tmpfs`. RAM loss or container lifecycle events can wipe data not persisted to durable storage.

## 3. Choosing Persistent Storage for PostgreSQL

PostgreSQL performs many synchronous read/write operations, especially involving WAL and commits. Storage must meet durability and latency requirements, not merely capacity requirements.

### 3.1. Block Storage Is Usually the Common Choice

Cloud block volumes and local block devices generally suit databases because PostgreSQL operates on a filesystem over a block device and requires flush/sync semantics. Select a volume type whose IOPS, throughput, and latency meet the workload.

### 3.2. Evaluating the Filesystem

Verify:
- Filesystem supported by the OS and storage provider.
- POSIX semantics.
- `fsync`/flush behavior.
- File locking and shared memory requirements.
- Crash consistency.
- Mount options.
- Filesystem expansion.
- Quotas and capacity reporting.

PostgreSQL relies on the filesystem and OS to guarantee durability. A filesystem or network storage with improper locking or flush semantics can cause severe failures. Only use storage types supported by PostgreSQL/the platform vendor and tested in the target environment.

### 3.3. Network Filesystems

Do not assume NFS/SMB or any shared filesystem is automatically suitable. Verify the support matrix, locking semantics, cache coherency, flush behavior, and failure modes. If the provider recommends block volumes or specifies restrictions, follow that guidance.

### 3.4. Local Ephemeral Disks

Local NVMe can be very fast, but may be lost when an instance/node is replaced. Use only when the architecture has clear replication, backup, and recovery strategies, and the exact data-loss exposure is understood. Do not call a local ephemeral disk "persistent" simply because a path survives a container restart on the same host.

### 3.5. Latency Matters Alongside IOPS and Throughput

WAL flushes and synchronous commits are latency-sensitive. A volume with high throughput but high latency can slow transaction commits. Benchmark with near-production `fsync`/durability settings.

### 3.6. Capacity and Headroom

Estimate:
- Data files.
- Indexes.
- WAL growth.
- Temporary files.
- Sort/hash spills.
- Backup staging if on the same volume.
- Tablespaces.
- Bloat and maintenance headroom.
- Growth over time.

Do not provision a volume tightly fitted to current usage. Reserve room for growth, index builds, and restore bursts.

## 4. Defining the Data Directory and PGDATA

`PGDATA` is the environment variable commonly used by PostgreSQL images to specify the data directory path. It must point to a directory containing a cluster initialized by `initdb` or a directory the entrypoint will initialize on first run.

### 4.1. Separating PGDATA from the Image

A simple Docker Compose example:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped
    stop_grace_period: 1m

volumes:
  pgdata:
```

This is an illustrative configuration. Check the documentation of your actual image tag because entrypoint behavior, default `PGDATA`, secret support, and directory layout can change across image variants or major versions.

### 4.2. Mount Root and PGDATA Subdirectory

In the example above, the volume is mounted at `/var/lib/postgresql/data`, while the cluster lives in the subdirectory `/var/lib/postgresql/data/pgdata`. This layout helps the entrypoint manage the mount root and data subdirectory separately, but it must match the image.

Some images use different layouts by major version or environment variables. Do not copy paths from an old example without checking the image.

### 4.3. Verifying the Cluster Directory

Inside the container, you can check:

```bash
printf 'PGDATA=%s\n' "$PGDATA"
ls -ld "$PGDATA"
ls -l "$PGDATA/PG_VERSION"
```

`PG_VERSION` is a cluster metadata file. Read its contents to confirm the major version of the data directory; never infer the version solely from the image tag.

### 4.4. One Volume per Cluster Data Directory

Under standard architecture, a PostgreSQL cluster has only one primary writer at a time. Never mount the same `PGDATA` read-write into two running PostgreSQL servers. Filesystem locks do not turn a single data directory into a multi-writer database.

### 4.5. Each Replica Has Its Own Data Directory

With physical streaming replication, the primary and each standby maintain their own data directories. WAL/replication transfers changes between nodes; never share a single `PGDATA` as a substitute for replication.

## 5. Mount Semantics in Docker and Compose

A Docker volume is an independent runtime object. The container only sees the volume at the mount destination.

### 5.1. Declaring a Named Volume

```yaml
services:
  db:
    image: postgres:17
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

Compose creates or reuses the named volume using project/name resolution. The actual name may be prefixed by the project name unless configured with explicit `external` or `name`.

### 5.2. Bind Mounts

```yaml
services:
  db:
    image: postgres:17
    volumes:
      - type: bind
        source: ./postgres-data
        target: /var/lib/postgresql/data
```

The host directory must exist or be created according to Compose/runtime semantics. Check owner, permissions, and SELinux labels on the host before starting.

### 5.3. Read-Only Mounts

Read-only mounts suit configs/certificates that the server only needs to read. Never mount `PGDATA` read-only if PostgreSQL needs to write WAL, status files, relation files, and control files.

### 5.4. Do Not Mistakenly Mount a File onto a Directory

If mount destination and source type do not match, the entrypoint may fail to find files or the server may fail to start. Verify file-vs-directory types and path spelling, especially on Windows/WSL.

### 5.5. Container Recreation and Volume Retention

`docker compose down` typically preserves named volumes; `docker compose down -v` requests deletion of project-managed volumes (excluding external volumes per Compose behavior). `docker volume prune` can delete volumes no longer considered in use by the runtime.

Before running deletion commands, confirm volume name, mount source, backups, and intent. Never use `-v` or `prune` as a default cleanup step in production.

### 5.6. External Volumes

You can declare a volume managed by the platform outside Compose. Compose then does not create a new project-scoped lifecycle. Document the volume owner and attach/restore procedures.

### 5.7. Verifying Actual Mounts

Use runtime inspect to verify source, destination, read/write mode, and volume identity. Do not rely solely on YAML because interpolation, project names, or override files can alter the final configuration.

## 6. Directory Permissions: PostgreSQL Needs the Right Owner

PostgreSQL runs under a dedicated OS user, typically `postgres` inside the image. The data directory must belong to the user running the server and have appropriate permissions.

### 6.1. Ownership

On Linux, check:

```bash
id postgres
stat -c '%u:%g %a %n' "$PGDATA"
namei -l "$PGDATA"
```

`id` shows the UID/GID inside the container. `stat` checks owner/mode; `namei -l` inspects permissions of every path component if available.

### 6.2. Directory Permissions

`initdb` creates the data directory with private permissions on Unix by default; typically mode `0700`. The `--allow-group-access` option enables broader group access (typically `0750`). PostgreSQL checks data directory permissions at startup.

Never `chmod` the entire data directory to `0777` to work around an error. Doing so exposes database files to unnecessary users/processes and can cause PostgreSQL to refuse to start.

### 6.3. Parent Directory Traversal

Parent directories need execute/search permission for the `postgres` user to reach `PGDATA`. Parent directories do not necessarily have to be writable by the PostgreSQL user if the mount/layout does not require creating subdirectories there.

For example, a path with `PGDATA=/srv/postgres/data` needs traverse permissions on `/srv` and `/srv/postgres`, in addition to permissions on `/srv/postgres/data`.

### 6.4. File Permissions

WAL, relation files, control files, and configuration have corresponding access requirements. Never run `chmod -R` arbitrarily while the server is running. If ownership/modes are wrong, stop the server cleanly, identify the root cause, and fix only the affected scope.

### 6.5. Initdb and Non-Empty Directories

`initdb` initializes a new cluster in an appropriately empty directory. If mounting a volume that already contains data, the entrypoint must recognize the existing cluster and skip re-running `initdb`. If the directory contains extraneous files without forming a valid cluster, startup may fail.

Never wipe volume contents to "retry" before confirming it is not a database that needs to be kept.

## 7. UID/GID Mapping and Rootless Containers

Usernames inside an image do not guarantee the same UID/GID as on the host.

### 7.1. Bind Mounts Use Host Ownership

For example, a host directory belongs to UID 1001 while the PostgreSQL process in the container runs as UID 999. From inside the container, the server may fail to write to the directory even though both places show familiar usernames.

Usernames are mapped from UIDs/GIDs; kernel permission checks rely on numeric IDs.

### 7.2. Verify the UID/GID of a Specific Image

Check:

```bash
docker run --rm --entrypoint sh postgres:17 -c 'id postgres'
```

The image tag in the example is illustrative. Pin the exact production tag/digest and re-verify whenever changing images.

### 7.3. Preparing a Bind Mount

The host admin can create the directory and assign owner/group matching the UID/GID the container needs. Linux example:

```bash
sudo install -d -o 999 -g 999 -m 0700 /srv/postgres/data
```

UID/GID `999` is only an example, not a fixed value for every image. Retrieve the actual values from the image and security policy.

### 7.4. Rootless Docker/Podman

Rootless runtimes use user namespace mapping. A UID inside the container may map to a subordinate UID on the host. Running `chown` from the host using the UID seen inside the container may be wrong. Check `uidmap`, `subuid`/`subgid`, or runtime inspect per platform.

### 7.5. User Namespace Remapping

Docker `userns-remap` can alter owner IDs visible on the host. Understand the mapping before creating or `chown`ing bind mounts. Never guess ownership changes, as doing so can break access for other containers.

### 7.6. Do Not Run PostgreSQL as Root to Bypass Permissions

The PostgreSQL server must not run as the OS root superuser. Use an unprivileged user, correct UID/GID, ownership, and mount policies. If an entrypoint starts as root to prepare directories and then drops privileges, that is specific entrypoint behavior; never replace it by running the server directly as root.

## 8. Kubernetes Security Context and PVC Permissions

In Kubernetes, pods can run with `runAsUser`, `runAsGroup`, `fsGroup`, and other controls.

Illustrative example:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 999
    runAsGroup: 999
    fsGroup: 999
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: postgres
      image: postgres:17
      env:
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
      volumeMounts:
        - name: pgdata
          mountPath: /var/lib/postgresql/data
  volumes:
    - name: pgdata
      persistentVolumeClaim:
        claimName: postgres-data
```

This is a skeleton to explain security context, not a complete production manifest. UID, mount path, image, probes, resources, secrets, and StorageClass must match the platform.

### 8.1. runAsUser and runAsGroup

`runAsUser` and `runAsGroup` define the numeric identity of the process inside the container. Choose a UID/GID supported by the image and consistent with mounted storage ownership.

### 8.2. fsGroup

`fsGroup` can cause the volume to be mounted with a supplementary group for the pod or alter ownership/mode depending on the volume driver and Kubernetes implementation. Not all CSI drivers support this identically.

`fsGroup` does not automatically guarantee the data directory passes PostgreSQL permission checks. Verify `stat`, effective groups, and mode bits from inside the pod.

### 8.3. fsGroupChangePolicy

On supported Kubernetes versions, `fsGroupChangePolicy: OnRootMismatch` can avoid recursive ownership changes on every mount when the root directory already matches. For large volumes, recursive ownership changes can significantly prolong pod startup. Confirm whether the CSI driver handles ownership.

### 8.4. Init Containers for Preparing Ownership

Some deployments use an init container with appropriate permissions to prepare directories. This approach requires review:
- Is running as root permitted?
- Does it `chown` the entire volume on every start?
- Does the volume contain millions of files?
- Do security policies/Pod Security Admission permit it?
- Do UID/GID match the main container?

Do not grant broad root privileges just to avoid designing proper ownership.

### 8.5. readOnlyRootFilesystem

You can enable a read-only root filesystem for the container and mount required writable paths via separate volumes. PostgreSQL still requires writable `PGDATA`, socket/temp paths, and directories needed by the image/runtime. Test startup, logs, and recovery when enabling this policy.

### 8.6. Capabilities and Privileges

Run non-root and drop unnecessary capabilities per image/platform guidance. Do not use privileged pods or broad `hostPath` mounts without explicit justification and approval.

## 9. SELinux, AppArmor, and Filesystem Labels

On SELinux-enabled systems, correct Unix mode bits alone are not enough. Security labels can prevent a container from accessing a bind mount.

### 9.1. SELinux Labels

Docker/Podman may support relabeling bind mounts using options like `:Z` (private label for the container) or `:z` (shared label across containers), depending on the runtime. For example:

```bash
docker run -v /srv/postgres/data:/var/lib/postgresql/data:Z ...
```

Do not blindly apply relabel options to storage shared by multiple services. Relabeling can alter labels on the host path and break other processes.

### 9.2. Diagnosing SELinux

Inspect audit logs/AVC denials, file labels, and container process contexts. Never disable SELinux host-wide to work around a mount error.

### 9.3. AppArmor and seccomp

AppArmor/seccomp can restrict filesystem syscalls or process actions. Use compatible profiles and check audit/logs if the server gets denied. Avoid `unconfined` as a default solution.

### 9.4. Kubernetes SELinux Options

Kubernetes can assign SELinux contexts to containers/volumes per policy and CSI driver. Verify node OS, runtime, admission policies, and volume plugins. A configuration on one node does not guarantee identical labels across all nodes.

## 10. Separating Data, WAL, Tablespaces, and Configuration

A PostgreSQL cluster has multiple file types with distinct purposes and lifecycles.

### 10.1. PGDATA

`PGDATA` contains control files, catalogs, relation files, subdirectories, and by default `pg_wal` unless WAL is placed separately via a supported mechanism.

### 10.2. WAL

WAL is required for crash recovery and durability. If `pg_wal` sits on a separate mount or symlink, that volume must be managed durably alongside the data directory. Losing WAL can render the cluster unrecoverable.

Never place WAL on `tmpfs` or a container's writable layer in any system requiring durability.

### 10.3. Tablespaces

Tablespaces allow relation files to reside outside `PGDATA`. These locations must be mounted/persisted on every host that needs to use them. Logical/physical backups and restores must handle tablespaces properly.

### 10.4. Archive Destination

`archive_command` or an archive library can write WAL to object storage, a filesystem, or an external service. The archive location requires dedicated credentials, network policy, retention, and monitoring.

### 10.5. Configuration

Configuration can be mounted read-only or managed via ConfigMaps/secrets/configuration management. Ensure configuration is not lost on container recreation and is versioned/audited. Avoid mounting an entire config directory that shadows default files required by the image.

### 10.6. Secrets and Certificates

Mount passwords/certificates from a secrets manager or Kubernetes Secret per policy. Restrict read permissions and never bake secrets into image layers. Check file modes, rotation, and certificate reload/restart requirements.

## 11. Volume Capacity and I/O

PostgreSQL can grow faster than expected due to WAL, index builds, temp files, bloat, and long-running transactions.

### 11.1. Monitoring Filesystem Capacity

Inside the container or node, check total/used/available bytes, inodes if the filesystem has limits, per-directory growth, WAL directory size, temporary files, tablespace paths, and volume quotas.

### 11.2. Near-Full Volumes Are Incidents

Disk full can cause writes, WAL creation, checkpoints, or maintenance to fail. Set alerts before running out of space and define actions: expand the volume, clean up authorized data, inspect replication slots/archives, or handle runaway temp files.

Never delete files in `PGDATA` or `pg_wal` via the shell to reclaim space. Use PostgreSQL-supported procedures to manage WAL, logs, and database objects.

### 11.3. PVC Expansion

Some StorageClasses/CSI drivers support volume expansion. Increasing PVC capacity may require:
- A StorageClass allowing expansion.
- Updating the PVC spec.
- CSI volume expansion.
- Filesystem resize.
- Pod remount/restart depending on the driver.

Verify actual capacity inside the pod after expansion. Do not assume editing `resources.requests.storage` immediately increases filesystem capacity.

### 11.4. IOPS and Throughput

Set limits/provisioned performance according to the workload. Monitor volume latency, queue depth, and throttling. A volume shared with backup/logging workloads can cause contention.

### 11.5. Separate WAL and Data Volumes

Separating WAL onto its own volume can help in certain designs, but introduces additional failure domains and consistency requirements. If separated:
- Both volumes must be persistent.
- Mount paths must exist on every replacement node.
- Backups/snapshots must capture a consistent state of both.
- Capacity and IOPS are sized separately.
- Restore procedures must restore both to the right locations.

Do not separate WAL just because a tutorial showed it without benchmarking first.

## 12. Stateful Workloads in Kubernetes

PostgreSQL is a stateful workload. Kubernetes provides StatefulSets, PVCs, and storage orchestration to manage identity/storage.

### 12.1. StatefulSet

StatefulSet provides stable pod identity and can create dedicated PVCs from `volumeClaimTemplates`. This is a common pattern for one PostgreSQL instance per pod, paired with an operator or replication manager when HA is needed.

### 12.2. PVC Template

Condensed example:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
        - name: postgres
          image: postgres:17
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 100Gi
```

This skeleton illustrates stable PVC association. Production requires a StorageClass, security context, resources, probes, secrets, config, services, backups, and HA design.

### 12.3. ReadWriteOnce Is Not a Database Lock

`ReadWriteOnce` describes an access mode at the volume-attachment/node level per storage implementation; it is not a PostgreSQL multi-writer lock mechanism. Some CSI drivers allow multiple pods on the same node to mount the volume in specific ways. Never rely on access mode to let two PostgreSQL servers share `PGDATA`.

### 12.4. ReadWriteOncePod

If supported by the CSI/platform, `ReadWriteOncePod` can restrict a volume to being mounted by a single pod at a time. This is an additional safeguard; you still need an architecture enforcing a single writer and fencing/HA procedures.

### 12.5. PVC Lifecycle

PVCs typically exist independently of Pods. Deleting a Pod does not necessarily delete the PVC. Deleting a StatefulSet also has retention behavior depending on policy/version. Explicitly define whether PVCs are retained or deleted when scaling down or deleting a StatefulSet.

### 12.6. PV Reclaim Policy

`Retain` preserves underlying storage after a PVC/PV is released, allowing administrators to handle data deliberately. `Delete` may instruct the storage provider to delete the volume when the claim is released. Check the StorageClass/PV policy before deleting claims.

### 12.7. Do Not Use replicas: 2 with the Same PGDATA

Two PostgreSQL containers do not become HA just by running two replicas with the same mount. HA requires each instance to have its own storage, replication/fencing, leader election, and failover policy. A shared volume with two postmasters can corrupt the cluster.

## 13. Docker Compose and Volume Lifecycle

Compose suits development, testing, and certain single-host deployments. Production HA requires evaluating host failure, storage failure, and failover as well.

### 13.1. Stable Volume Declarations

```yaml
services:
  db:
    image: postgres:17
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
    name: production-postgres-data
```

Explicit naming helps identify the volume. Pin image versions/digests according to release processes; never use uncontrolled floating tags for production databases.

### 13.2. docker compose up and Recreation

When a container is recreated, Compose reattaches the named volume by project/config. Verify the volume name does not change due to project name or directory changes.

### 13.3. down, down -v, and prune

- `docker compose down` typically removes containers/networks while keeping named volumes.
- `docker compose down -v` requests deletion of project volumes per Compose semantics.
- `docker volume prune` can delete unused volumes.

Before running these, inspect volumes and verify backups/retention. Cleanup commands can cause irreversible data loss if a volume lacks backups.

### 13.4. Compose Project Name

Default volumes can be prefixed by the project name. Renaming a folder/project can create a new empty volume instead of attaching the old one. Use `name`/`external` when stable identity is required and document migration steps.

### 13.5. Do Not Treat Restart Policy as HA

`restart: unless-stopped` only governs container restarts under runtime policy. It provides no replication, backup, fencing, multi-node failover, or guarantee that the data volume remains accessible after host loss.

## 14. Container Lifecycle and PostgreSQL Shutdown

Containers have their own lifecycle: create, start, stop, restart, kill, remove. PostgreSQL has its own lifecycle: startup, recovery, accepting connections, shutdown, and crash recovery.

### 14.1. Graceful Shutdown

When stopping a container, the runtime sends a signal to the process per image/runtime settings, and may send a kill signal after a timeout. PostgreSQL has different shutdown modes:
- Smart: waits for clients to disconnect.
- Fast: disconnects clients and rolls back active transactions.
- Immediate: stops immediately, requiring crash recovery on next start.

In a container environment, verify the signal reaches the PostgreSQL process and the timeout is long enough for the chosen shutdown policy.

### 14.2. Termination Grace Period

Set stop timeout/termination grace period long enough for PostgreSQL to shut down under normal workloads. If the timeout is too short, the runtime may kill the process before shutdown completes. PostgreSQL will then typically require crash recovery on the next startup, increasing downtime and requiring log checks.

### 14.3. PID 1 and Signal Forwarding

Shell entrypoints need `exec` or an appropriate init/signal-forwarding mechanism so signals reach the server process. Avoid shell wrappers that drop or swallow signals.

### 14.4. Restart Does Not Mean Restore

Restarting a container with the same volume usually just restarts the cluster and runs recovery if needed. It does not restore deleted data, fix volume corruption, or resolve major-version incompatibilities.

### 14.5. Stop Before Detaching or Moving Volumes

Never detach a block volume or move a data directory while the postmaster is still running. Stop the server cleanly, verify shutdown is complete, and only then detach/snapshot/copy per storage platform guidance.

### 14.6. Crash Recovery

After a process/host crash, PostgreSQL uses WAL to recover the cluster. Ensure `PGDATA` and WAL storage both exist and that storage honors flush semantics properly. Check startup logs and recovery completion before opening traffic.

## 15. Startup, Readiness, and Liveness Probes

The orchestrator needs to know whether the container has started, PostgreSQL is accepting connections, and applications can use the right role/endpoint.

### 15.1. Startup Probe

A startup probe gives the database time for lengthy startup/recovery without being repeatedly restarted by the liveness probe. Set its budget based on realistic recovery duration.

### 15.2. Readiness Probe

Readiness determines whether a pod receives traffic. `pg_isready` checks PostgreSQL connection status, but does not automatically verify:
- Whether the node is primary or standby.
- Whether the application database exists.
- Whether the application role has permissions.
- Whether schema migrations have completed.
- Whether remote dependencies are healthy.

If the application needs a writable primary, the readiness check must reflect that role/condition per the HA design.

### 15.3. Liveness Probe

Liveness determines whether the process needs restarting. Do not use a heavy query or external dependency for liveness if transient errors would trigger a restart loop.

### 15.4. Probe Timing

Configure initial delay/period/timeout/failure threshold based on measured startup/recovery times. If probe timeouts are too tight during a load spike, the orchestrator may restart a database actively serving traffic.

### 15.5. Kubernetes Probe Example

```yaml
startupProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432
  periodSeconds: 5
  failureThreshold: 60

readinessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432
  periodSeconds: 5
  timeoutSeconds: 3
  failureThreshold: 3

livenessProbe:
  exec:
    command:
      - sh
      - -c
      - pg_isready -h 127.0.0.1 -p 5432
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 6
```

This is a starting example, not a probe policy for all deployments. For HA, readiness needs to check primary/standby roles and app-specific conditions. Configure the startup probe to prevent liveness checks from intervening before recovery has a chance to finish.

## 16. Storage Consistency and Durability

PostgreSQL durability relies on WAL, `fsync`/flush, the filesystem, and storage hardware/platform guarantees.

### 16.1. Do Not Disable fsync to Speed Up Production

`fsync=off` can cause data loss or corruption after an OS/power crash. Use it only in disposable/test environments with clear understanding of the risks; never use it as a default optimization.

### 16.2. Storage Cache and Flush Guarantees

Verify whether the provider guarantees write ordering/flush semantics. A storage layer that acknowledges writes before data is truly durable can break durability assumptions.

### 16.3. Synchronous Commit

`synchronous_commit` affects when a commit is acknowledged relative to WAL flush/replication mode. Do not alter it merely to mask storage latency; define the durability contract and test failover/data-loss windows.

### 16.4. Clock and Host Events

Containers do not have storage isolated from the host kernel/devices. Node reboots, disk detaches, host replacements, and storage failovers are all part of the recovery model. Document provider event behavior.

### 16.5. Do Not Copy Live PGDATA with Regular File Copy

Copying the database directory while PostgreSQL is running without a supported backup method can yield an inconsistent copy. Use `pg_basebackup`, a supported backup mode/API, or a snapshot workflow with proper consistency and WAL recovery.

## 17. Volume Backups, Snapshots, and Restores

Persistent volumes protect data from container deletion, but do not replace independent backups.

### 17.1. Logical Backup

`pg_dump`/`pg_dumpall` create logical backups suited for database/object-level recovery and migrations. Backup files must be stored outside the database volume with retention and restore testing.

### 17.2. Physical Backup

Use `pg_basebackup` or backup tooling supporting PostgreSQL physical backups and WAL archiving. Ensure tool versions and procedures are compatible with the server.

### 17.3. Volume Snapshots

Storage snapshots can be useful, but verify:
- Is the snapshot crash-consistent or application-consistent?
- Is one or multiple volumes snapshotted atomically?
- Does it capture WAL and tablespaces?
- Is checkpoint/quiesce/backup mode required?
- Can the snapshot attach to a different host?
- How are snapshot retention and encryption handled?

A consistent snapshot of a block volume can recover as after a crash if PostgreSQL and storage guarantees align; unsynchronized snapshots across multiple volumes may yield an unrecoverable state.

### 17.4. WAL Archive and PITR

For point-in-time recovery, you need a base backup plus a continuous WAL chain up to the target time. The archive must reside on independent storage with monitoring for failed archives, retention, and restore tests.

### 17.5. Restore Drills

Periodically restore onto a new volume/cluster:
1. Create a target volume.
2. Install PostgreSQL and extension packages at exact versions.
3. Restore the base backup or logical dump.
4. Configure tablespaces/WAL paths.
5. Replay WAL if doing PITR.
6. Verify recovery completion.
7. Run database/application validation.
8. Measure recovery time and update RTO/RPO.

### 17.6. Do Not Store Backups on the Same Volume

If backup files are written to the same volume as `PGDATA`, losing the volume destroys both the database and backups. Use independent storage, a separate account/region, or a backup service aligned with your threat model.

## 18. Tablespaces and Multiple Volumes

Tablespaces allow relation files to be stored outside the data directory.

### 18.1. Stable Mount Paths

If a tablespace path is a `/pg_tblspc` symlink to another mount, the target path must exist with proper ownership before the server starts. Any node that may be promoted or restored onto must have the matching structure.

### 18.2. Backup Coverage

Physical backup/restore must include tablespace contents per procedure. Logical dumps can recreate objects in specified tablespaces, though they do not preserve all physical layouts.

### 18.3. Snapshot Consistency

If data, WAL, and tablespaces span multiple volumes, use snapshot consistency groups if supported by the provider or use a supported backup method. Unsynchronized per-volume snapshots can create states that cannot be safely replayed.

### 18.4. Disk Failure Domains

Separating volumes can improve performance or capacity management, but also introduces additional failure domains. Evaluate volume loss, attach failures, and recovery for each path.

## 19. Major-Version Upgrades in Containers

Changing an image tag is not a database major-version upgrade.

### 19.1. Data Directory Format

PostgreSQL major versions can change internal data formats. Never start a new major binary directly against an old major data directory unless following a supported upgrade procedure.

### 19.2. Migration Methods

Depending on the environment, you can use:
- `pg_upgrade`.
- Logical dump/restore.
- Logical replication/cutover.
- Managed provider upgrade workflows.

Choose a method based on extension compatibility, downtime, data size, and recovery plan.

### 19.3. Do Not Attach Production Volumes to Test Containers

Create a snapshot/clone or restore onto a separate volume for rehearsals. Never let two containers potentially write to the production data directory.

### 19.4. Pin Image Versions

Use exact major/minor tags or immutable digests per release policy. A floating `latest` tag can accidentally change the major version or OS base during deployment.

### 19.5. Extension Binaries

Install native extension binaries matching the target PostgreSQL major version on target images/hosts. Data/catalog migrations and `ALTER EXTENSION UPDATE` are separate steps to verify per extension documentation.

### 19.6. Major Upgrade Rollback

You cannot roll back by switching the image back to the old major version and mounting the target data directory. Keep the source cluster/backup separate and design cutover/reconciliation before the target accepts writes.

## 20. Rolling Updates and HA

PostgreSQL is not a stateless web service. Rolling updates must follow the database topology.

### 20.1. Primary and Standbys

Each node has its own volume. Before failover/promotion, verify the node has the right image, configuration, extension packages, certificates, and data state.

### 20.2. Fencing

The HA manager must ensure the old node stops accepting writes after a new node is promoted. Storage attachment policies alone do not replace fencing/leader election.

### 20.3. Node Rescheduling

When a pod is scheduled onto another node, the CSI driver must attach the volume, mount the proper filesystem, and restore ownership/labels. Measure attach/mount/startup/recovery duration.

### 20.4. PodDisruptionBudget

PDBs can limit voluntary disruptions, though they do not protect against node/storage failures. Configure according to replica count/HA policy and understand interactions with node drains.

### 20.5. StatefulSet Rollouts

StatefulSet update strategies can replace pods sequentially, but do not inherently understand PostgreSQL replication safety or promotion order. Use an operator/HA controller designed for PostgreSQL when managed failover is required.

### 20.6. Replication Readiness

Before updates/failover, check replay lag, replication state, timeline, and slots. Promoting a lagging standby can lose transactions already committed on the primary.

## 21. Kubernetes Storage Lifecycle

### 21.1. StorageClass

A StorageClass specifies the provisioner and parameters such as disk type, performance tier, encryption, or topology. Pin/record the StorageClass and understand behavior when volumes are provisioned in specific zones.

### 21.2. VolumeBindingMode

`WaitForFirstConsumer` can delay provisioning/binding until the scheduler knows pod topology. This helps with zonal volumes, though it can affect scheduling behavior.

### 21.3. Topology and Zones

Persistent block volumes may only attach within a single zone. A pod rescheduled to another zone may fail to mount. HA/DR designs must account for zone failures, cross-zone replication, and restores.

### 21.4. PVC Deletion Protection

Define StatefulSet PVC retention policies, PV reclaim policies, and provider snapshots/backups. Never assume deleting a StatefulSet always keeps or always deletes claims.

### 21.5. Restoring to a New PVC

When recovering, you typically create a new PVC from a snapshot/backup and deploy the pod with that claim. Verify identity/path/ownership before starting the server.

## 22. Security and Data-at-Rest

Volumes hold database files, WAL, temporary data, and potentially sensitive records.

Verify:
- Cloud volume encryption at rest.
- Encryption key ownership/rotation.
- Filesystem permissions.
- Host access.
- Snapshot access policies.
- Backup encryption.
- Secret mounts.
- Audit logs.
- Data deletion/retention policies.

### 22.1. Encryption at Rest

Prefer encryption supported by the storage provider/host platform per policy. Verify key permissions and restore capability during key rotation or revocation.

### 22.2. Container Access

Only the PostgreSQL container and authorized maintenance/backup processes should have required access to `PGDATA`. Avoid mounting the data volume into multiple application containers.

### 22.3. Snapshot Permissions

Snapshots can contain the entire database, including deleted-but-not-yet-reclaimed data and WAL. Restrict who can copy, share, export, or restore snapshots.

### 22.4. Temporary Files

Sort/hash spills may contain sensitive data. Choose temporary storage, permissions, and retention per policy. If temp paths reside on ephemeral disks, explicitly accept losing temp files on container stop.

## 23. Monitoring for Volumes and Container Lifecycle

Monitor the database and storage simultaneously.

### 23.1. Storage Metrics

- Volume capacity/available bytes.
- IOPS/throughput.
- Read/write latency.
- Queue depth/throttling.
- Filesystem errors.
- Attach/mount failures.
- PVC pending/binding states.
- Volume expansion status.

### 23.2. PostgreSQL Metrics

- WAL generation and archive status.
- Checkpoint activity.
- Replication lag.
- Long-running transactions.
- Temporary file usage.
- Database size/index growth.
- Autovacuum progress.
- Startup/recovery duration.
- Connection saturation.

### 23.3. Container Metrics

- Restart count.
- OOM kills.
- Exit codes.
- Termination reasons.
- Startup/readiness duration.
- Node evictions.
- Probe failures.
- CPU/memory throttling.

### 23.4. Alerting

Alert before volumes fill up or replica lag exceeds budgets. Alert on restart loops, mount failures, permission denied errors, archive backlogs, and repeated recoveries. Every alert must have a corresponding runbook.

### 23.5. Correlating Events

When PostgreSQL slows down, correlate query latency with volume latency, node pressure, CPU throttling, and WAL/checkpoint metrics. Do not blame every latency spike on the SQL planner.

## 24. Docker Compose Example with Dedicated Data Volume and Config

The following example illustrates a data volume and a read-only config mount:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./postgresql.conf:/etc/postgresql/postgresql.conf:ro
    command:
      - postgres
      - -c
      - config_file=/etc/postgresql/postgresql.conf
    secrets:
      - db_password
    restart: unless-stopped
    stop_grace_period: 1m

volumes:
  pgdata:

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

This is an illustrative example; `POSTGRES_PASSWORD_FILE` support, secret mounts, config paths, and entrypoint behavior depend on the image/runtime. Ensure config files have proper read permissions and do not unintentionally override critical defaults. Secret files must never be committed to source control.

## 25. Kubernetes PVC and Pod Security Example

A minimal PVC:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-data
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: fast-block
```

The name `fast-block` is illustrative and must be replaced with an actual StorageClass.

A Pod referencing the claim:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 999
    runAsGroup: 999
    fsGroup: 999
    fsGroupChangePolicy: OnRootMismatch
  containers:
    - name: postgres
      image: postgres:17
      env:
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
      volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
      resources:
        requests:
          cpu: "1"
          memory: 2Gi
        limits:
          memory: 4Gi
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: postgres-data
```

This example omits Services, Secrets, probes, config, backups, HA, and full resource sizing. For production, consider a PostgreSQL operator or platform-specific controller rather than writing all lifecycle management yourself.

## 26. Runbook: PostgreSQL Reports Permission Denied

When the server cannot read/write the data directory:

1. Check logs to identify the denied path and operation.
2. Confirm the container is mounting the correct volume.
3. Check the actual UID/GID of the PostgreSQL process.
4. Check owner/mode of `PGDATA` and parent directories.
5. Check rootless/user namespace mapping.
6. Check SELinux/AppArmor denials.
7. Check whether the filesystem is mounted read-only or the volume attach mode.
8. Stop the server if ownership/mode changes are needed.
9. Fix the exact path/UID/GID per image and policy.
10. Start staging or the approved instance and verify recovery.

Never run `chmod -R 777`, never run the server as root, and never delete the data directory to resolve permission errors.

## 27. Runbook: Container Starts with an Empty Volume

If a new container initializes an empty database instead of seeing the old cluster:

1. Stop application traffic to the new container.
2. Confirm which volume the container is mounting.
3. Inspect the volume name/ID and host path.
4. Check the Compose project name or PVC claim binding.
5. Check whether `PGDATA` changed compared to the previous image.
6. Check whether the mount destination changed.
7. Locate the old volume from inventory/backups; do not prune/delete.
8. Reattach the correct volume after confirming ownership.
9. Check `PG_VERSION` and cluster identity.
10. Open traffic only after confirming the right cluster and recovery state.

Do not run `initdb` again on a production volume simply because the entrypoint did not find the expected cluster.

## 28. Runbook: Volume Fails to Attach or Pod Stuck Pending

1. Check PVC/PV state and events.
2. Check StorageClass/provisioner.
3. Check zone/topology constraints.
4. Check if the volume is still attached to another node.
5. Check provider API/quotas/permissions.
6. Check access mode and CSI driver support.
7. Do not force-detach while PostgreSQL might still be writing.
8. Use the HA/fencing runbook to confirm the old node has stopped.
9. Attach the volume per provider procedure.
10. Verify filesystem and PostgreSQL recovery before accepting traffic.

## 29. Runbook: Container Killed or in Restart Loop

1. Inspect exit code, termination reason, OOMKilled status, and probe events.
2. Check startup logs and PostgreSQL crash recovery.
3. Verify whether the termination grace period is sufficient.
4. Check volume mount/permissions after restart.
5. Check memory limits and OOM pressure.
6. Check whether startup/liveness probes are too aggressive.
7. Identify whether an extension/preload/library is failing startup.
8. Never delete `postmaster.pid` without confirming no postmaster is using the data directory.
9. Wait for recovery to complete and run validation.
10. Adjust resource/probe/shutdown policies after identifying the root cause.

## 30. Runbook: Volume Nearly Full

1. Identify the growing filesystem/volume and path.
2. Distinguish database files, WAL, archives, temp files, and logs.
3. Check replication slots and archive backlogs.
4. Check long-running transactions/autovacuum.
5. Expand the volume if supported by the platform and approved.
6. Handle logs/backups/temp files per retention policy.
7. Do not delete WAL files manually.
8. Monitor filesystem capacity and recovery.
9. Confirm archiving/replication resumes normally.
10. Adjust capacity alerts and growth forecasts.

## 31. Common Deployment Mistakes

| Mistake | Consequence |
|---|---|
| Storing PGDATA in the writable layer | Database lost when container is deleted |
| Mounting a new empty volume by mistake | Container creates a new cluster; app sees an empty database |
| Changing PGDATA path | Entrypoint cannot find the old cluster |
| UID/GID mismatch | Permission denied or initdb/startup failure |
| chmod 777 | Over-exposes access and can violate permission checks |
| Running PostgreSQL as root | Violates PostgreSQL security model |
| Unverified fsGroup | Volume remains unwritable or startup becomes very slow |
| Missing SELinux labels | Permission denied despite valid mode bits |
| Placing WAL on ephemeral storage | Cannot perform crash recovery after container/host loss |
| Deleting PVC/volume during cleanup | Data loss |
| Two postmasters sharing PGDATA | Corruption or unsafe concurrent access |
| Relying only on same-volume snapshots | No independent backup if volume is lost |
| Changing major image tag directly | Binary incompatible with data directory |
| Stop timeout too short | Process gets killed and requires crash recovery |
| Overly aggressive probes | Restart loop during startup/recovery |
| Not testing attach on another node | Failover/rescheduling cannot mount storage |

## 32. Pre-Deployment Checklist

- [ ] Choose a storage type supported by PostgreSQL/the platform.
- [ ] Evaluate latency, IOPS, throughput, and durability.
- [ ] Decouple `PGDATA` from the container writable layer.
- [ ] Pin image tag/digest and verify default `PGDATA`.
- [ ] Confirm stable volume names/claim identities.
- [ ] Verify mount source/destination and read/write modes.
- [ ] Verify the image's UID/GID.
- [ ] Verify ownership/modes of `PGDATA` and parent paths.
- [ ] Check rootless/user namespace mapping.
- [ ] Check SELinux/AppArmor.
- [ ] Confirm WAL and tablespaces are persistent.
- [ ] Define independent backup/archive locations.
- [ ] Verify secret/config mounts.
- [ ] Define stop timeout and startup/recovery budgets.
- [ ] Design probes aligned with primary/standby roles.
- [ ] Define PVC/PV retention and reclaim policies.
- [ ] Confirm each PostgreSQL instance has dedicated storage.
- [ ] Rehearse restart, recreate, reschedule, and restore.

## 33. Operations Checklist

- [ ] Container restarts preserve the right volume and cluster identity.
- [ ] Image updates do not unexpectedly change the data directory path.
- [ ] Graceful shutdown completes within the termination budget.
- [ ] Startup probe does not restart clusters undergoing recovery.
- [ ] Readiness opens traffic only when role/DB state is appropriate.
- [ ] Disk capacity and I/O latency have alerts.
- [ ] WAL/archive/replication lag are monitored.
- [ ] PVC attach/mount events are monitored.
- [ ] Permission/SELinux errors have runbooks.
- [ ] Snapshots/backups have retention and restore drills.
- [ ] Failover nodes have matching extension packages/configs.
- [ ] PVC deletion/prune commands require approval/process.
- [ ] Major upgrade rehearsals use separate clones/volumes.
- [ ] Multiple postmasters never share `PGDATA`.

## 34. Official References

- [PostgreSQL — File System Level Backup](https://www.postgresql.org/docs/current/backup-file.html): filesystem-level backups and consistency requirements.
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archiving, and PITR.
- [PostgreSQL — pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): physical base backups.
- [PostgreSQL — initdb](https://www.postgresql.org/docs/current/app-initdb.html): cluster initialization and data directory permissions.
- [PostgreSQL — Server Shutdown](https://www.postgresql.org/docs/current/server-shutdown.html): shutdown modes.
- [PostgreSQL — WAL Reliability](https://www.postgresql.org/docs/current/wal-reliability.html): durability and storage assumptions.
- [Docker — Volumes](https://docs.docker.com/engine/storage/volumes/): named volumes and lifecycle.
- [Docker — Bind Mounts](https://docs.docker.com/engine/storage/bind-mounts/): host paths and mount behavior.
- [Docker Compose — Volumes](https://docs.docker.com/reference/compose-file/volumes/): volume configuration.
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/): PV, PVC, StorageClass, and reclaim policy.
- [Kubernetes — StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/): stable identity and storage claims.
- [Kubernetes — Security Context](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/): `runAsUser`, `fsGroup`, and security settings.
- [Kubernetes — Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): startup, readiness, and liveness probes.

PostgreSQL `/current/` paths and Docker/Kubernetes documentation may change across versions. When deploying, consult the manual matching your actual PostgreSQL major version, image digest, container runtime, Kubernetes version, and CSI driver.

## 35. Summary

PostgreSQL in containers is only durable when database files sit on storage with an independent lifecycle, proper access permissions, and tested recovery procedures. Containers can be recreated, but volumes, WAL, tablespaces, backups, and cluster identity must be managed consistently.

1. **Storage:** use appropriate persistent volumes, measure latency/IOPS/throughput, and never store `PGDATA` on writable layers or `tmpfs`.
2. **Paths:** keep `PGDATA`, mount destinations, WAL, and tablespaces fixed; verify volume identity before starting.
3. **Permissions:** run PostgreSQL as a non-root user, verifying UID/GID, ownership, mode bits, and SELinux labels.
4. **Lifecycle:** forward shutdown signals properly, allow sufficient termination time, configure probes around startup/recovery, and never replace HA with restart policies.
5. **Recovery:** maintain independent backups, archive WAL, take consistent snapshots, and practice restore drills onto new volumes.
6. **Kubernetes/Compose:** intentionally manage PVC/named volume retention, storage topology, and deletion policies.
7. **Upgrades:** never change the major image and directly mount an old data directory; use supported PostgreSQL migration procedures.

A reliable deployment must pass tests for container recreation, node restarts, volume attachment on suitable nodes, backup restores, and crash recovery while preserving the right cluster, data, and access permissions.
