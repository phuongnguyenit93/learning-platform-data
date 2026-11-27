# Deploying on Kubernetes with Operators and Responsibility Boundaries

Deploying PostgreSQL on Kubernetes using an operator enables declarative database management: the human operator describes the desired state in a Kubernetes resource, and the operator monitors and performs the necessary steps to bring the system to that state. This approach can automate instance creation, replica configuration, failover, backup, or upgrades, depending on the capabilities of the chosen operator.

An operator does not replace the entire role of the DBA, the platform team, or the application development team. Kubernetes is responsible for orchestrating containers and infrastructure resources; the operator understands the PostgreSQL lifecycle within its implemented scope; DBAs and product teams still must decide on data policies, recovery objectives, application workloads, and incident handling procedures. Clearly defining these boundaries is essential for safe system operations.

## 1. What Is an Operator and How Does It Work?

In Kubernetes, an operator typically consists of two main components:

- **Custom Resource Definition (CRD):** extends the Kubernetes API with a new resource type. For example, a PostgreSQL operator may define a resource representing a database cluster.
- **Controller:** a process that watches those resources and runs a reconcile loop to bring the actual state closer to the desired state.

A user creates a custom resource (CR) to describe the configuration. The controller receives an event when the CR changes, reads the current state of the cluster, compares it with the desired configuration, and creates or updates the necessary objects. Those objects may include Pods, StatefulSets, PVCs, Services, Secrets, ConfigMaps, Jobs, or operator-specific resources.

Overview flow:

~~~mermaid
flowchart TD
    A[Human operator declares PostgreSQL CR] --> B[Kubernetes API stores desired state]
    B --> C[Operator watches for changes]
    C --> D[Read actual state]
    D --> E[Reconcile: create or adjust resources]
    E --> F[Pod, PVC, Service, backup job...]
    F --> G[Operator observes result]
    G -->|Not converged| D
    G -->|Converged| H[Update status and conditions]
~~~

The reconcile loop is idempotent/repeatable. The controller may receive the same event multiple times, restart, or reprocess after a resource is modified. Therefore, reconciliation operations must be safe to repeat and based on actual state, rather than assuming each event arrives only once.

Three concepts should be distinguished:

- **CRD** defines the resource type and its schema.
- **CR** is a specific object declared by the user, containing the configuration for a database cluster.
- **Operator** is the control software that reads CRs and manages related resources.

The existence of a CR does not mean the database is ready. A PVC may be waiting for a volume, a Pod may not be scheduled yet, the database may still be initializing, or a replica may not have caught up with WAL. Inspect `status`, `conditions`, events, and operator logs to determine actual progress.

## 2. What Can an Operator Manage?

Each PostgreSQL operator has a different scope and level of automation. Common capabilities include:

| Functional Area | What the Operator May Handle | What Needs Verification |
|---|---|---|
| Cluster initialization | Creating PostgreSQL instances, initial configuration, users, and databases per supported schema | Bootstrap method, secret handling, and resource ownership |
| Replication | Configuring primary/standby, monitoring replica status | Synchronous vs. asynchronous, how lagging replicas are detected |
| HA and failover | Selecting a new primary when the current primary fails, updating endpoints | Fencing mechanism, failover conditions, data loss risk |
| Storage | Creating PVCs, attaching volumes, expanding capacity if supported | CSI driver, StorageClass, volume expansion and recovery limits |
| Backup | Scheduling base backups, archiving WAL, managing retention or restore jobs | Storage destination, encryption, PITR, and restore testing process |
| Configuration | Applying PostgreSQL parameters, CPU/RAM resources | Which parameters require a restart, supported configuration scope |
| Upgrades | Orchestrating image or PostgreSQL version changes | Minor/major upgrade support, extensions, and rollback capability |
| Observability | Exposing metrics, events, logs, or cluster status | Integration with the organization's monitoring and alerting systems |

Do not assume an operator has all of the capabilities above simply from the name "PostgreSQL Operator". Read the documentation for the exact version, CRD schema, compatibility matrix, and product limitations. Some operators only manage basic lifecycle tasks; others provide additional backups, connection poolers, or upgrade mechanisms.

An operator also does not automatically make a database highly available. HA depends on topology, storage, networking, node distribution, replication, primary election mechanism, fencing, and the application's ability to reconnect. If any of these layers fails to meet requirements, having an operator still does not guarantee continuous service.

## 3. PostgreSQL Deployment Architecture on Kubernetes

A PostgreSQL cluster typically has one primary that accepts writes and one or more standbys that receive WAL from the primary. Depending on configuration, standbys may serve read queries. The operator monitors the instances and coordinates actions across the cluster lifecycle.

Common components:

- **PostgreSQL Pod:** runs the PostgreSQL process. Each instance needs its own identity and lifecycle.
- **PersistentVolumeClaim (PVC):** requests persistent storage capacity for an instance's data. A Pod may be recreated, but the data must be reattached to the correct volume.
- **PersistentVolume (PV):** storage resource provisioned statically or dynamically by Kubernetes via a StorageClass.
- **Service:** provides a stable address for applications to connect to. The operator may create separate endpoints for primary and replicas.
- **Backup target:** usually object storage or an external storage system outside the cluster to hold base backups and WAL.
- **Monitoring:** collects metrics from PostgreSQL, exporters, Pods, nodes, and the operator.

Example logical architecture:

~~~text
Application
   |
   +---- Write Service ----> Primary PostgreSQL
   |                            |
   |                            +---- WAL replication ----> Standby 1
   |                            |
   |                            +---- WAL replication ----> Standby 2
   |
   +---- Read Service -----> Standby (if policy allows)

Operator
   +---- Watches CR and instance status
   +---- Manages Pods, PVCs, Services, and configuration
   +---- Orchestrates failover, backup, and restore as supported

External backup target outside cluster
   +---- Base backup
   +---- WAL archive
~~~

The diagram above only illustrates a common topology. An operator may use StatefulSets, standalone Pods, sidecars, agents, or other orchestration components. Do not rely on internal Pod names or StatefulSet names unless the operator publishes them as a stable API. Applications should connect through a Service or endpoint supported by the operator.

### Primary, standby, and connection paths

Write applications must connect to the endpoint representing the primary. A read endpoint can distribute queries to standbys, but should only be used when the application tolerates replication lag and the corresponding read semantics. Not all read queries are safe to route to a replica: a query immediately after a write might not see the just-committed change if the replica has not yet replayed WAL to the required position.

During failover, the primary role changes. The operator may update endpoints or Pod selector labels, but existing TCP connections generally do not move automatically to the new server. Connection pools must detect broken connections, discard stale connections, and open new ones. Applications need controlled retries for retryable operations, especially noting that a transaction's outcome may be uncertain if the connection drops right at commit time.

### Preventing split-brain

Split-brain occurs when two instances both believe they are primary and both accept writes. This is a severe risk because the two data branches can diverge. An HA solution must have a mechanism to ensure the old primary cannot continue accepting writes when a new primary is promoted. This mechanism is commonly called fencing or leader coordination and may involve coordination state, storage access rights, or instance isolation actions.

Do not build failover yourself simply by changing Pod or Service labels. Switching an endpoint without ensuring the old primary is disabled can cause split-brain. Thoroughly understand the operator's failover/fencing mechanism and test it in a non-production environment before using it in production.

## 4. Planning Before Installing the Operator

Before creating a cluster, operational requirements must be defined:

**Data and recovery objectives.** Define RPO (maximum acceptable data loss) and RTO (maximum time to restore service). RPO affects replication and backup policies; RTO affects topology, failover, restore procedures, and on-call operational readiness.

**Workload and capacity.** Estimate concurrent connections, TPS, read/write ratio, data size, growth rate, WAL volume, and IOPS requirements. Account for space needed for temporary backups, index builds, vacuum, and traffic spikes.

**Versions and compatibility.** Choose PostgreSQL versions, extensions, client drivers, and an operator with a matching compatibility matrix. Define the minor update cycle, major upgrade plan, and how native extensions are handled.

**Topology and failure domains.** Decide on the number of instances, availability zones, node pools, anti-affinity, topology spread, and synchronous replication requirements. Three Pods on the same node are not equivalent to three copies across three independent failure domains.

**Storage.** Choose a StorageClass and CSI driver that meet durability, latency, IOPS, expansion, and snapshot policy requirements. Verify that volumes can be reattached after a Pod moves to another node and understand zone constraints.

**Security and operations.** Define namespaces, RBAC, service accounts, network policies, TLS, secret storage locations, backup target access permissions, monitoring, alerting, and on-call ownership.

## 5. Installing and Managing the Operator Lifecycle

Operators are typically installed in a dedicated namespace or a shared namespace for a group of workloads. Installation methods depend on the project: manifests, Helm charts, Operator Lifecycle Manager, or internal packaging pipelines.

Before installing, verify:

- The operator version is compatible with the target Kubernetes and PostgreSQL versions.
- The CRDs to be installed or updated have schemas compatible with existing CRs.
- RBAC permissions are scoped strictly to the resources the operator needs to manage.
- Watch scope: single namespace or cluster-wide.
- Controller replica count and how conflicting processing between controller instances is prevented.
- Upgrade, rollback, and CRD/webhook recovery procedures.
- Image registry, image signatures, supply source, and vulnerability scanning policies.

An operator is a critical workload. If the controller stops, running databases generally do not stop merely because the controller is down, but reconciliation, failover, or backup operations managed by the operator may be disrupted. Therefore, monitor the operator itself, its webhooks, and its supporting components.

Do not delete CRDs just to "reinstall cleanly". Deleting a CRD can delete all custom resources of that kind and destroy the control objects for your clusters. Understand uninstall behavior, finalizers, and PVC retention or deletion policies before removing an operator.

## 6. Declaring a Database Cluster

Human operators typically create a custom resource to describe a PostgreSQL cluster. The resource kind name, API version, and `spec` structure depend on the operator.

The following example is a **conceptual YAML illustration**, not a manifest to be used directly for a specific operator:

~~~yaml
apiVersion: database.example.io/v1
kind: PostgreSQLCluster
metadata:
  name: orders-db
  namespace: data
spec:
  instances: 3
  postgres:
    version: "major-version-supported-by-operator"
    storage:
      size: 200Gi
      storageClass: database-ssd
    resources:
      requests:
        cpu: "2"
        memory: 8Gi
      limits:
        memory: 8Gi
  backup:
    enabled: true
    destination: object-storage-reference
~~~

In real resources, fields may have different names, be nested differently, or require additional configuration for users, databases, replication, TLS, backup credentials, and monitoring. Always use the schema and examples for the exact operator version; the Kubernetes API server will reject invalid fields, or the operator may ignore unsupported configuration.

When applying a CR, monitor the convergence process:

~~~bash
kubectl apply -f postgres-cluster.yaml

kubectl get <postgres-resource> -n data
kubectl describe <postgres-resource> orders-db -n data
kubectl get pods,pvc,svc -n data
kubectl get events -n data --sort-by=.lastTimestamp
~~~

`<postgres-resource>` is the plural resource name defined by the operator's CRD. Replace this placeholder with the actual name from the CRD or operator documentation.

Do not treat a successful `kubectl apply` as proof that the database is ready. Confirm that:

1. The CR is accepted by the API server and recognized by the operator.
2. PVCs are provisioned and attached successfully.
3. Pods are scheduled, started, and passing readiness probes.
4. PostgreSQL is accepting connections.
5. Primary/standby roles are correct and replication is in the desired state.
6. Services point to the right instances.
7. The first backup succeeds and its metadata can be inspected.
8. Metrics and logs are being collected.

## 7. Storage and Data Durability

Databases require durable storage. A container filesystem belongs to the Pod lifecycle and is not a place for long-term PostgreSQL data storage. Operators usually request a PVC for each instance; the PVC is bound to a PV via a StorageClass or static provisioning.

When choosing a StorageClass, evaluate:

- Read/write latency and IOPS under realistic load.
- Sequential throughput, especially during WAL writes or backup/restore runs.
- How the CSI driver handles detach/attach when a Pod is scheduled onto a different node.
- Per-node and availability-zone volume limits.
- Reclaim policy when a PVC is deleted.
- Volume expansion support and filesystem limits.
- Storage provider behavior for snapshots, clones, and restores.

`ReadWriteOnce` generally means a volume can be mounted read-write by one node at a time; it is not a guarantee that only a single process uses the volume. Actual access mode rules and attach capabilities also depend on the CSI driver. Do not manually alter access modes or share one data volume across multiple PostgreSQL instances if the operator architecture does not support it.

Deleting a Pod does not necessarily delete its PVC, but that behavior depends on owner references, finalizers, and operator configuration. Verify what happens when deleting a CR, scaling down, replacing an instance, or uninstalling the operator. Know clearly which cases preserve volumes and which cases can delete data.

Volume snapshots can be useful for backups or cloning environments, but a raw filesystem snapshot alone is not automatically equivalent to a consistent PostgreSQL backup. Use a backup mechanism supported by PostgreSQL/the operator, coordinated with checkpoints/WAL or a consistent snapshot procedure. For PITR requirements, ensure valid base backups and a continuous WAL chain are maintained.

## 8. High Availability and Replication Limits

A multi-instance topology reduces downtime when an instance or node fails, but you must distinguish:

- **Replication:** shipping data changes from primary to standby.
- **Failover:** transferring the primary role to a selected standby.
- **Fencing:** ensuring the old primary cannot continue accepting writes.
- **Routing:** directing new connections to the right endpoint after role changes.
- **Recovery:** bringing a failed instance back into the cluster and resynchronizing data.

Asynchronous replication can lose some transactions that were committed on the primary but had not yet reached a standby when the primary was lost. Synchronous replication can reduce data loss risk according to configuration, at the cost that transaction commits may have to wait for standby acknowledgment and be affected when a standby or the network is slow. Understand the exact sync mode, required standby count, and behavior when too few standbys are available.

A replica is not a backup. An accidental delete statement, data encrypted by ransomware, or a logic bug written on the primary will be replicated to standbys. Independent backups and PITR capability remain necessary.

Kubernetes provides Pod scheduling and restarts, but does not fully understand transaction state or whether it is safe to promote a standby. The operator must coordinate database logic to execute failover properly. Do not manually delete the primary Pod just because a readiness probe fails without understanding how the operator uses that signal.

To improve fault tolerance, consider:

- Distributing instances across different nodes and zones using anti-affinity or topology spread.
- Keeping sufficient spare nodes and resources so Pods can be rescheduled after an incident.
- Using an appropriate PodDisruptionBudget (PDB) to limit disruptions from voluntary evictions.
- Testing disruptions caused by node drains, cluster upgrades, and autoscaling.
- Testing node failures, network partitions, replica lag, and primary loss in staging environments.
- Measuring failure detection time, failover time, reconnection time, and potential data loss.

A PDB primarily limits voluntary evictions through the Kubernetes Eviction API. It does not prevent node crashes, automatically create new replicas, or replace the operator's failover mechanism.

## 9. Backups, WAL Archiving, and Point-in-Time Recovery

A production system needs a backup policy independent of replication. A common approach is taking periodic base backups and continuously archiving WAL to object storage or an out-of-cluster repository. With a base backup and the required WAL sequence, PostgreSQL can recover to a point in time within the retained range.

A backup policy must define:

- Base backup frequency and completion time limits.
- Whether WAL archiving is continuous and alerting when archiving stalls.
- Retention period, storage duration, and cross-region or cross-account copies.
- Encryption in transit and at rest, access permissions, and credential management.
- Immutability or protection of backups against accidental deletion.
- RPO/RTO targets and the capacity required during restore.
- Who is authorized to trigger restores and the approval process.

An operator can create backup jobs and manage archive configuration, but the operations team must still verify that backups are actually usable. A job showing a succeeded status does not replace a restore test.

Conduct periodic recovery drills:

1. Select a backup and define a target recovery point in time.
2. Provision an isolated restore environment to avoid overwriting production.
3. Restore the base backup and replay WAL to the requested target time.
4. Verify that the database starts, extensions load, and business data is consistent.
5. Measure completion time, any data loss, and manual steps involved.
6. Record issues, update runbooks, and re-test after fixes.

When deleting a cluster or namespace, ensure the backup target is outside the deletion scope and has independent retention. Do not assume PVCs remain after deleting a CR or that object storage will automatically retain data as desired.

## 10. Resources, Configuration, and Performance

The Kubernetes scheduler uses resource requests to decide which node a Pod can run on. CPU limits can cause throttling when a workload needs more CPU than the limit; memory limits can lead to OOM kills. For databases, unexpected restarts and throttling can impact latency, replication lag, and recovery time.

Plan capacity for:

- CPU and RAM for normal load, peak load, and maintenance.
- Operating system page cache, shared buffers, and backend memory.
- Concurrent connection counts and per-connection memory overhead.
- WAL generation, checkpoints, autovacuum, and long-running queries.
- Temporary space for sorts/hashes, index builds, and backups.
- Headroom to run replicas or recover after node failures.

Do not set `work_mem` too high just to speed up sorts. This parameter can be allocated multiple times within a single query and concurrently across many sessions; total memory consumption can be many times the configured value. A high `max_connections` also increases overhead. A connection pooler can reduce direct connections to PostgreSQL, but must be configured appropriately for session state, prepared statements, and transaction pooling.

PostgreSQL parameters should be managed through the configuration mechanism supported by the operator. Some parameters can be reloaded; others require a restart. Do not edit configuration files directly inside a running container if the operator will overwrite them or does not track those changes. Store the desired configuration in a managed declarative source.

Monitor at least CPU, memory, disk latency, disk usage, WAL rate, checkpoints, autovacuum, active connections, lock waits, replication lag, transaction age, dead tuples, and connection errors. Only with these metrics can you distinguish Kubernetes resource shortages from query, index, or PostgreSQL configuration issues.

## 11. Security and Access Control

Databases hold critical data, so security must be designed at both the Kubernetes and PostgreSQL layers.

**RBAC and service accounts.** The operator needs permissions to create and update resources within its scope. Avoid granting cluster-admin unless explicitly justified. Separate cluster administration, database management, and application data access permissions.

**Secrets.** Passwords, TLS certificates, and object storage credentials should be stored in Secrets or an organization-approved secret management system. Base64-encoded Kubernetes Secrets do not mean the data is encrypted. Enable encryption at rest for the Kubernetes datastore, restrict Secret read permissions, rotate credentials, and avoid putting secrets into Git or logs.

**Networking.** Use NetworkPolicies or equivalent mechanisms to restrict which sources can reach PostgreSQL ports, replication ports, metrics, and webhooks. Only open necessary connections between the operator, databases, backup targets, and applications.

**TLS.** Encrypt client and replication connections when required by security policy. Manage CAs, certificate lifecycles, hostname verification, and certificate rotation procedures. Do not disable TLS verification as a quick fix for certificate errors.

**Pods and images.** Use images from trusted sources, pin versions or digests per policy, scan for vulnerabilities, and restrict Linux privileges, filesystems, and capabilities. Apply Pod Security Standards or equivalent policies. Do not run containers as root or privileged without an approved technical reason.

**Database accounts.** Create separate roles for applications, migrations, backups, and administration. Grant least privilege; do not use superuser for regular application connections. Document and review permissions periodically.

## 12. Upgrading the Operator and PostgreSQL

There are at least two separate version lifecycles:

1. **Operator version:** changes to controllers, CRDs, webhooks, and reconciliation logic.
2. **PostgreSQL version:** changes to the database server, catalogs, extensions, and on-disk data format in major versions.

Upgrading the operator does not mean upgrading PostgreSQL. Conversely, upgrading PostgreSQL may require a newer operator that supports the corresponding images, bootstrap behavior, or migration procedures.

Before upgrading:

- Read release notes and compatibility matrices for the operator, Kubernetes, PostgreSQL, and extensions.
- Check whether CRDs have schema changes or conversion webhooks.
- Back up CRs and necessary configurations; verify data backups.
- Test on a staging copy with data size and extensions similar to production.
- Measure downtime, catch-up time, temporary space, and rollback feasibility.
- Identify application endpoints, connection pools, and schema migration schedules.

Minor upgrades typically have a simpler procedure, but still require checking extensions, images, and restart impact. Major upgrades may require `pg_upgrade`, logical replication, or other migration methods depending on the operator. Never assume changing the version field in a CR is enough to convert the data directory.

Rolling back a major upgrade is usually complex because the upgraded data directory may not be backward-compatible. Prepare a restore plan or a plan to shift traffic back to the old cluster, and determine how to reconcile writes that occurred during cutover.

Upgrading Kubernetes nodes or CSI drivers can also disrupt databases. Check PDBs, rescheduling capacity, volume attachment, anti-affinity, and node drain ordering. Do not perform simultaneous maintenance across all failure domains of a cluster.

## 13. Observability and Troubleshooting

When a database is unavailable, determine which layer has the issue: CR/operator, Kubernetes scheduling, storage, networking, PostgreSQL, or the application.

Observation points:

| Layer | Observation Sources | Questions to Answer |
|---|---|---|
| Custom resource | `kubectl get`, `describe`, status/conditions | Has the operator picked up the config? Which condition is failing? |
| Operator | Controller logs, events, webhook logs | At which step did reconcile fail? Are there permission or schema errors? |
| Kubernetes | Pod status, events, node conditions | Is the Pod pending, crash-looping, OOM-killed, or evicted? |
| Storage | PVC/PV, CSI events, volume metrics | Is the volume bound/attached/mounted? Is it out of space or having I/O errors? |
| PostgreSQL | Server logs, `pg_stat_activity`, replication views | Is the database accepting connections? Are there locks, checkpoints, or abnormal replica lag? |
| Application | Connection pool, timeouts, SQLSTATE, request traces | Are connections hitting the right endpoint? Are retries safe? |

Useful investigation commands:

~~~bash
kubectl get pods -n data -o wide
kubectl describe pod <postgres-pod> -n data
kubectl logs <operator-pod> -n operator-namespace
kubectl logs <postgres-pod> -n data
kubectl get pvc -n data
kubectl get events -n data --sort-by=.lastTimestamp
~~~

Namespace, Pod, and container names should be replaced with your environment's values. If a Pod has multiple containers, specify the target container with the `-c` option.

From a PostgreSQL connection with appropriate privileges, you can inspect roles and activity:

~~~sql
SELECT pg_is_in_recovery();

SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database();

SELECT *
FROM pg_stat_replication;
~~~

`pg_is_in_recovery()` returns `false` on an active primary and `true` when the instance is in recovery/standby mode. `pg_stat_replication` provides information about standbys connected to the primary; on a standby, this view does not replace checking WAL replay status.

During an incident, do not rush to delete Pods, PVCs, or CRs. First collect events, logs, conditions, volume status, and database roles. Deleting a Pod can destroy evidence or trigger unwanted operator actions. Deleting a PVC can cause data loss. If manual intervention is required, follow the operator's runbook and have an explicit decision owner.

## 14. Responsibility Boundaries Across Teams

A well-operated system clearly documents who is responsible for each layer. The table below is a reference model; organizations may assign duties differently, but critical responsibilities must never lack an owner.

| Party | Primary Responsibilities | Should Not Default to Scope |
|---|---|---|
| Kubernetes control plane and node platform | API, scheduler, nodes, runtime, underlying networking, policies, and cluster capacity | Correctness of PostgreSQL transactions, schemas, or queries |
| Storage/Cloud platform | CSI, volume durability, storage performance and limits, object storage | Database backup policies, PITR, and business data validation after restore |
| PostgreSQL operator | Reconciling resources per CR; managing lifecycle, replication, failover, backup, or upgrades within supported scope | Deciding RPO/RTO, query analysis, data modeling, or all business processes |
| DBA/Data platform | Database design, HA/backup policies, parameters, database permissions, upgrades, restore tests, and data runbooks | Operating all Kubernetes nodes or replacing application team responsibilities |
| Application team | Connection pooling, timeouts, retries, idempotency, queries, schema migrations, and connection error handling | Unilaterally changing cluster configuration or deleting database resources |
| Security/Compliance | Access policies, encryption, auditing, retention, and compliance requirements | Replacing recovery testing and day-to-day technical operations |

### Where does the operator's responsibility end?

An operator can automate actions it was designed and configured for: creating Pods, maintaining replicas, executing failover, running backups, or applying configurations. However, an operator cannot automatically make every business decision.

For example, an operator can detect that the primary lost connectivity and promote a standby according to policy. It cannot decide on its own whether losing a few seconds of data is acceptable for a payment system. Decisions on synchronous replication, RPO, and handling transactions with uncertain outcomes must be agreed upon by DBAs and application teams.

An operator can run scheduled backups, but the data-owning team must decide retention, cross-region storage requirements, access permissions, and restore validation. An operator can apply resource limits, but sizing must be based on workloads and actual observations.

### Where does Kubernetes's responsibility end?

Kubernetes manages Pod lifecycles, scheduling, service discovery, resource quotas, volume attachment via CSI, and cluster policies. Kubernetes does not inherently understand whether a PostgreSQL Pod is primary or standby, does not verify sufficient data replay, and does not guarantee zero transaction loss when a Pod is replaced.

Readiness probes indicate whether a Pod should receive traffic according to declared conditions. Liveness probes can cause a container to be restarted. Misconfigured probes can cause restart loops or remove a Pod from a Service when the database is simply under heavy load. Probes must reflect status appropriate to their purpose and coordinate with the operator's mechanisms.

### Where does the application team's responsibility end?

After a failover, existing connections may be dropped. Applications must have reasonable timeouts, pools capable of evicting broken connections, and safe retries. A network error at commit time does not indicate for certain whether the transaction committed. Non-idempotent operations need request identification mechanisms or status checks before retrying to avoid duplicate writes.

The application team also owns queries, workload-specific indexes, schema migrations, and driver compatibility. An operator will not automatically tune a slow query or fix transaction logic causing lock contention.

## 15. Common Misconceptions

**A Pod restart means the database has recovered.** A Pod may be in the Running state while PostgreSQL is not yet ready for traffic, is still replaying WAL, or has not synchronized replicas. Check readiness, database role, and replication status.

**Having three replicas means backups are unnecessary.** Replication replicates accidental changes and logical data corruption as well. Independent backups, WAL archiving, and restore tests remain mandatory per data objectives.

**A PDB guarantees HA.** A PDB only throttles certain voluntary evictions. It does not handle primary crashes, split-brain, storage failures, or full-zone outages.

**An existing PVC means the data is safe.** A PVC only represents a storage claim. You must understand PV/CSI durability, reclaim policies, snapshots, and recovery procedures.

**The operator automatically upgrades PostgreSQL safely.** Upgrade capability depends on versions, extensions, data directories, and migration strategies. Read the documentation and rehearse beforehand.

**The Service always points to the new primary immediately.** Endpoints may take time to update; DNS caches and connection pools may retain stale state. Applications must handle connection failures and verify server roles appropriately.

**Directly editing Pods or StatefulSets to fix issues.** Resources managed by an operator can be overwritten by reconciliation. Modify the CR or official configuration mechanism instead, unless a runbook specifies a particular temporary action.

**Handing all responsibility to the DBA or platform team.** DBAs cannot control nodes and CSI without platform permissions; platform teams cannot be responsible for transaction correctness and business backups without data owners. Each team must own the part it controls.

## 16. Pre-Production Checklist

- [ ] Selected an operator and version compatible with Kubernetes, PostgreSQL, and extensions.
- [ ] Reviewed CRD schema, support scope, installation, upgrade, and uninstallation procedures.
- [ ] RPO, RTO, topology, and replication policies approved by DBA/data owner.
- [ ] Instances distributed across appropriate nodes or failure domains.
- [ ] StorageClass, CSI, capacity, IOPS, volume expansion, and reclaim policy verified.
- [ ] PVCs will not be accidentally deleted when deleting or modifying the CR.
- [ ] Backups and WAL archives stored at an independent destination; PITR/restore drilled.
- [ ] Failover, fencing, routing, and application reconnection tested.
- [ ] PDB, anti-affinity, topology spread, and node drain configured appropriately.
- [ ] CPU/RAM requests, limits, connection pool, and PostgreSQL settings sized to workload.
- [ ] RBAC, Secrets, TLS, NetworkPolicies, and image policies meet security requirements.
- [ ] Metrics, logs, events, alerts, and runbooks have on-call ownership.
- [ ] Separate plans exist for operator, CRD, PostgreSQL minor, and major version upgrades.
- [ ] Application team has tested timeouts, retries, idempotency, and schema migrations.
- [ ] Responsibility boundaries and incident decision makers are documented.

Deploying PostgreSQL with an operator is effective when the desired state is clearly declared, the operator fits the requirements, storage and networking meet database demands, and each team understands its share of responsibility. Operators automate the technical lifecycle within their supported scope; service reliability still depends on data design, restorable backups, resilient applications, and rehearsed operational procedures.
