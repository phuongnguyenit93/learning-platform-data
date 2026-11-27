# Deploying Stateful Applications and Managing Stable Machine Identities

A stateful application stores or maintains state required to continue processing—such as transaction data, sessions, indexes, logs, checkpoints, metadata, or cluster membership state. When deploying such applications on the cloud, you must ensure state survives restarts and compute replacements, while also defining which machines or workloads are permitted to access data and communicate with peer members.

A VM can be replaced, an IP can change, a container can be rescheduled, and a Pod can be recreated. Therefore, the architecture must separate **logical identity**, **authentication identity**, **network address**, and **data lifecycle**. A service can preserve a stable name or ordinal for a stateful member while still issuing fresh credentials to the compute instance after machine replacement. This lets the application recover the right data and maintain trust boundaries as underlying infrastructure changes.

In the CLOUD_CORE_SERVICES_COMPUTE module, this lesson connects VM, container, Kubernetes, storage, networking, and security identity choices to how stateful workloads are deployed. The focus is on understanding where state lives, which role a new machine inherits, how credentials are issued, and how to prevent split-brain, data loss, or duplicated identities during scaling and failover.

After this lesson, you will be able to:

- Distinguish stateful applications, stateful compute, and stateless workloads.
- Choose data storage locations aligned with VM, container, or Pod lifecycles.
- Distinguish resource IDs, logical identities, workload identities, and network identities.
- Design stable machine identities using managed identities, service accounts, or certificates with clear lifecycles.
- Deploy stateful applications on VMs, containers, and Kubernetes StatefulSets.
- Use persistent volumes, stable DNS, membership, quorum, leader election, and fencing for their intended purposes.
- Safely execute bootstrapping, machine replacement, credential rotation, and failover.
- Plan backups, restores, scaling, rollouts, and data integrity testing.

## 1. What Is a Stateful Application?

A stateful application maintains information needed across requests or across multiple processing steps. State can live in databases, files, volumes, caches, logs, message offsets, indexes, or process memory.

Examples:

- Databases storing records and transaction logs.
- Search systems storing indexes and shard metadata.
- Message brokers storing messages, offsets, and replication state.
- Collaborative applications storing documents, revisions, and locks.
- Stateful workers storing checkpoints for long-running jobs.
- Web applications storing sessions or shopping carts across requests.

Stateful does not mean all data must sit on the machine running the application. A stateless API can read/write a shared stateful database. Conversely, a stateful application can keep caches in RAM while its authoritative data resides on durable storage.

### Distinguishing Stateful Applications and Stateful Compute

| Concept | Meaning | Examples |
|---|---|---|
| Stateful application | Application that maintains business or processing state | Database, broker, search cluster |
| Stateful compute | Compute instance with local state or identity/membership tied to machine lifecycle | VM holding a data disk, cluster node with member ID |
| Stateless compute | Instance replaceable without migrating local state | API replica, retryable worker |
| Externalized state | State residing in a service with a lifecycle independent of compute | Managed database, object storage, shared cache |
| Stateful workload orchestration | Platform maintains identity/ordering/storage per replica | Kubernetes StatefulSet |

A system can combine multiple models. For example, a stateless API tier runs on a VM scale set, a stateful database tier uses persistent storage and replication, and queue batch workers run on preemptible capacity.

## 2. Inventorying State Before Deployment

Before selecting VMs or controllers, list all data and state the application requires.

| State | Examples | Typically Suitable Storage | Key Requirements |
|---|---|---|---|
| Business records | Orders, accounts, transactions | Database | Transactions, backups, consistency |
| Binary/file data | Images, documents, artifacts | Object storage or shared file storage | Durability, versioning, access control |
| Database files | Data pages, WAL/redo logs | Persistent block storage or managed database | Ordering, fsync, recovery, IOPS |
| Search/index data | Index shards, segments | Persistent volume or managed search service | Replication, rebuild, snapshots |
| Sessions | Logins, workflow state | Shared session store or protected tokens | TTL, security, failover |
| Queue state | Messages, offsets, consumer positions | Durable broker or managed queue | Delivery semantics, replay |
| Local cache | Query cache, compiled artifacts | RAM or ephemeral disk | Regenerable |
| Cluster membership | Node ID, term, shard assignments | Metadata store/cluster consensus | Identity uniqueness, fencing |
| Runtime checkpoints | Job cursors, model state | Database/object storage | Atomic commits, resume |
| Machine credentials | Certificates, key references | Secret manager/TPM-backed store | Confidentiality, rotation, revocation |

For each type of state, answer:

1. Where is the source of truth?
2. Is the data regenerable or must it be preserved?
3. Does the data require consistency across multiple files or volumes?
4. Who is permitted to read/write?
5. When a VM or Pod is deleted, does the data survive?
6. What are the RPO and RTO?
7. Are backups, replication, and restore tests in place?
8. Can it be accessed from a replacement compute instance?

If you do not yet know where state lives, you cannot accurately assess risks during deployment, scale-in, or machine replacement.

## 3. Data Lifecycle Must Be Independent of Compute Lifecycle

Compute instances can regularly be created or deleted. Critical data requires a lifecycle aligned with business requirements.

### Storage Options

| Storage | Characteristics | Best Fit | What to Verify |
|---|---|---|---|
| Instance local/ephemeral disk | Attached to instance or node; may be lost on host replacement | Cache, scratch, temporary data | Never use as sole copy of critical data |
| Persistent block volume | Volume can survive restarts and reattach per service conditions | Databases, indexes, stateful services | Attachment, zone, filesystem, snapshots, IOPS |
| Shared file storage | Multiple compute units access the same filesystem per supported semantics | Shared content, application files | Locking, consistency, throughput, mount behavior |
| Object storage | Accessed via API, suited for immutable or versioned objects | Files, backups, artifacts, checkpoints | Versioning, consistency, retention, request rate |
| Managed database | Provider manages much of data operations | Transactional data | Backups, failover, endpoints, replica lag, connection limits |
| Distributed data service | Data distributed across nodes/shards/replicas | Search, brokers, distributed databases | Quorum, membership, replication, repair |

### Persistent Volumes Do Not Replace Backups

A persistent volume can outlive a VM or Pod, yet it can still be deleted, logically corrupted, encrypted by ransomware, or overwritten with bad data. Snapshots and backups must be designed separately, with retention policies and restore testing.

### Data Durability and Availability Are Different

- Durability refers to the likelihood that data is not lost.
- Availability refers to the ability to access the service when needed.
- Consistency refers to the observable state of reads/writes.
- Recoverability refers to the ability to restore after an incident.

A highly durable volume attachable only in a single zone can still interrupt workloads if that zone fails. Replication improves availability, but if deletions or corruption are replicated, you still need backups with point-in-time recovery.

## 4. What Is a Stable Machine Identity?

"Machine identity" is often confused with a hostname, IP address, or instance ID. Those values are useful for locating resources, but they are not necessarily durable credentials or logical identifiers.

Separate four layers:

| Identity Layer | Question Answered | Examples | Can It Change on Replacement? |
|---|---|---|---|
| Resource identity | Which resource is the cloud managing? | VM instance ID, container ID, node resource ID | Usually yes |
| Logical identity | Which member/role is this in the system? | db-replica-2, shard-03, StatefulSet ordinal | Can be kept stable |
| Authentication identity | Which principal is proving identity for permissions? | Managed identity, service account, X.509 certificate, SPIFFE ID | Can be reissued/rotated |
| Network identity | Which endpoint do clients discover and connect to? | DNS name, service name, private IP, load balancer | IPs can change; names can stay stable |

A sound architecture does not rely on a fixed IP address to authenticate machines. DNS or service discovery provides endpoints; an identity provider verifies principals; authorization decides what a principal can do; persistent storage holds state.

### Example

A database replica has logical name **orders-db-2**. The current VM has instance ID **i-abc123**, private IP **10.10.2.15**, and certificate serial **cert-91**. When the VM is replaced:

- The logical role remains **orders-db-2**.
- The new instance ID is **i-def456**.
- The IP may become **10.10.2.27**.
- A new certificate is issued with a different serial.
- The data volume is reattached following a safe procedure.
- Cluster membership verifies the new node is legitimately assuming that member identity.

Do not copy the old VM's certificate private key into images or onto the new VM just to keep the same serial. Preserving the logical identity while issuing fresh authentication credentials is generally much safer.

## 5. Stable Identity Does Not Mean Using Static IPs

Static IPs are occasionally needed for allow-lists or communicating with legacy systems, but they should never be the sole authentication mechanism.

### Hostnames

Hostnames can be preserved across rebuilds if configuration processes name machines by logical role. However, hostnames can be spoofed or duplicated if bootstrapping goes wrong; they do not prove a machine is trustworthy.

### Private IPs

Private IPs can change when instances are replaced, subnets change, or network interfaces are recreated. Some services support attaching static or secondary IPs, but an IP is a network property with its own lifecycle.

### DNS / Service Discovery

DNS names or service registries help clients locate endpoints without hardcoding specific IPs. DNS can update during failover or replacement. Manage TTLs, health checks, split-horizon DNS, and caching.

### Identity-Based Access

Use workload identities, managed identities, instance roles, service accounts, or certificates to authenticate principals. Policies bind permissions to identities rather than relying on network addresses.

You can combine DNS, private IPs, and identity-based authorization, provided each component stays in its proper role.

## 6. Models for Issuing Machine Identity

Clouds and platforms offer several ways to issue identities to compute.

### Instance Profiles or Managed Identities

VMs are assigned a role/managed identity. Applications fetch short-lived tokens from a metadata/identity endpoint per provider mechanics, eliminating the need to bake long-lived access keys into images.

Advantages:

- Credentials are issued automatically along the instance lifecycle.
- Permissions can be revoked or adjusted in the control plane.
- Short-lived tokens reduce the risk of long-lived credential leaks.
- Permissions can be separated by workload role.

Things to protect:

- Block metadata access from unauthorized workloads.
- Enforce secure metadata service modes per provider (e.g., IMDSv2).
- Scope IAM permissions to least privilege.
- Never log tokens or credentials.
- Check token audience, expiry, and rotation.
- Separate roles across APIs, workers, backup agents, and admin tasks.

### Kubernetes ServiceAccounts and Workload Identity

Pods can use a ServiceAccount to receive an identity. Managed Kubernetes typically supports binding ServiceAccounts to cloud IAM principals or workload identity federation. When a Pod is recreated, logical identity persists via the ServiceAccount while fresh short-lived tokens are issued.

Never share one overly broad node role across all Pods. Scoping permissions at the workload level shrinks the blast radius.

### X.509 Certificates and Mutual TLS

Machines or workloads can use certificates to authenticate via TLS/mTLS. Certificates embed subject/SAN or URI identities tied to the machine/workload. Private keys should be protected by a secret manager, secure enclave, or TPM when required.

Processes needed:

- Initial enrollment and identity verification.
- Policy-driven certificate issuance.
- Rotation before expiration.
- Revocation when a machine is compromised or decommissioned.
- Trust bundle distribution.
- Auditing of certificate issuance and usage.

### SPIFFE/SPIRE and Workload Identity Frameworks

Some systems use SPIFFE IDs or similar mechanisms to represent workload identity independently of IP addresses. Workloads receive an SVID (typically X.509 or JWT) from an identity control plane after attestation. This fits environments with many services, platforms, and clusters needing consistent mTLS.

Distinguish workload identity from host identity. Host identity proves a node/VM is trustworthy; workload identity identifies the specific process or service running on that host.

### TPM and Attestation

TPMs or hardware-backed security modules can hold non-exportable keys and provide evidence of boot/hardware state. Attestation lets an identity service verify a machine meets a baseline before issuing credentials.

Not all cloud VMs or serverless runtimes expose TPM/attestation directly to customers. Check the actual instance types, confidential computing features, and identity services in use.

## 7. Role-Based Identity vs. Per-Instance Identity

Two common design patterns:

**Role-based identity:** every replica of a workload receives a principal/role with the same permission set, while each instance receives its own short-lived token. Well suited for stateless APIs or homogeneous worker pools.

**Per-instance identity:** each VM/node holds a distinct principal or certificate. Well suited when per-machine auditing, individual revocation, mTLS peer identity, or per-member policies are needed.

For stateful clusters, both layers are often needed:

- Logical member ID identifies the replica's position/role.
- Per-instance authentication identity verifies the current compute instance.
- Cluster membership or consensus confirms the replica is authorized to participate.
- Fencing/versioning prevents an old instance from writing after replacement.

Never distribute a single static credential copied across all nodes if the system needs to distinguish individual members.

### Selection Matrix

| Requirement | Typically Suitable Identity |
|---|---|
| Many API replicas sharing database access permissions | Workload role/managed identity |
| Per-VM auditing and revocation | Per-instance certificate or instance principal |
| Kubernetes Pod accessing cloud services | ServiceAccount bound to workload identity |
| mTLS between services | X.509/SPIFFE identity |
| Verifying host integrity before issuing secrets | Hardware-backed attestation if platform supports it |
| Stateful member needing stable ordinal | Logical member ID + reissued per-instance credentials |

## 8. Deploying Stateful Applications on VMs

VMs fit when applications require specific OS, kernel, disk layouts, or specialized software. For stateful workloads, separate boot disks from data disks.

### Boot Disks and Data Disks

- Boot disks hold the OS and software reproducible from images.
- Data disks hold database files, indexes, or persistent state.
- Backups/snapshots protect data disks according to consistency requirements.
- VM replacement can boot from a new image and reattach the data disk procedurally.
- Filesystem mounts and application recovery must be verified before opening traffic.

Never place the sole copy of data on the boot disk if your replacement strategy rebuilds the OS. When attaching a data disk to a new VM, verify the old VM has been fenced or safely detached before mounting read-write on the new host.

### Bootstrapping

Stateful VM provisioning sequence:

1. Create the VM from a versioned image.
2. Attach the managed identity/instance role.
3. Receive logical role or member assignment from the control plane.
4. Fetch certificates/secrets using the identity.
5. Attach or discover the persistent data volume.
6. Verify volume ID, filesystem, encryption keys, and mount state.
7. Run application recovery (journal/WAL/redo replay if needed).
8. Verify cluster membership and replication status.
9. Admit traffic only after readiness and consistency checks pass.

### Do Not Clone Identities in Golden Images

Golden images should contain only software and baseline configuration. Never bake machine private keys, unique node IDs, host certificates, or secrets from a running instance into an image. Cloning an image containing a shared machine identity across multiple VMs causes duplicate identities, mTLS conflicts, or overwritten audit trails.

### VM Identity Flow

~~~mermaid
flowchart TD
    A[Provision VM from image] --> B[Cloud assigns new resource ID]
    B --> C[Attach managed identity/instance role]
    C --> D[Bootstrap receives logical role]
    D --> E[Enrollment issues new certificate]
    E --> F[Attach persistent data volume]
    F --> G[Verify data and membership]
    G --> H[Readiness succeeds]
    H --> I[Admit to service traffic]
~~~

## 9. Deploying Stateful Applications with Containers

Containers package runtimes and dependencies cleanly, but a container's writable filesystem is rarely the place for durable data.

Principles:

- Images are immutable and versioned.
- Data resides on persistent volumes or external services.
- Container identity comes from service accounts/workload identity.
- Never bake certificate private keys or credentials into images.
- Configure readiness/liveness/startup probes.
- Gracefully shut down and drain before termination.
- Control UID/GID, filesystem permissions, and `securityContext`.

### Container Replacement

When a container restarts, a new container ID may be assigned. The Pod may stay intact or be replaced depending on the cause. Data in the writable layer must never be treated as durable. Volume mounts can preserve data across container restarts, though volume lifecycles and reattachment capabilities depend on the storage driver.

### Single Container or Multiple Containers?

Stateful applications can use sidecars for backup agents, log collectors, or proxies. Sidecars in the same Pod share certain resources and lifecycles; if a backup agent slows down or holds file locks, evaluate its impact on the primary application.

Do not bundle a database, backup agent, and multiple independent applications into a single container just to reduce Pod counts. Each component deserves a clear lifecycle and failure handling.

## 10. StatefulSets and Stable Identity in Kubernetes

Kubernetes StatefulSets are designed for workloads requiring stable ordinal identities, ordered deployment/scaling, and dedicated storage per Pod.

For example, a 3-replica StatefulSet creates Pods named:

- `orders-db-0`
- `orders-db-1`
- `orders-db-2`

Pod ordinals remain stable when Pods are replaced in a StatefulSet. Paired with a headless Service, each Pod gets stable DNS derived from its Pod and service name. `volumeClaimTemplates` create dedicated PVCs per ordinal.

### StatefulSets Do Not Automatically Turn an App into a Distributed Database

StatefulSets provide primitives for identity, ordering, and volume association. The application still must handle:

- Replication and consistency.
- Leader election or primary/replica roles.
- Quorum and membership.
- Backups/restores.
- Failover and fencing.
- Schema/data migrations.
- Recovery when volumes corrupt or zones fail.

Do not use a StatefulSet merely because an application "has a database" if a managed database or a Deployment + external state fits better.

### Example Headless Service and StatefulSet

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-db
spec:
  clusterIP: None
  selector:
    app: orders-db
  ports:
    - name: database
      port: 5432
      targetPort: 5432
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: orders-db
spec:
  serviceName: orders-db
  replicas: 3
  selector:
    matchLabels:
      app: orders-db
  template:
    metadata:
      labels:
        app: orders-db
    spec:
      serviceAccountName: orders-db
      containers:
        - name: database
          image: registry.example/orders-db:16.2
          ports:
            - name: database
              containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/database
          resources:
            requests:
              cpu: "1"
              memory: "2Gi"
            limits:
              cpu: "2"
              memory: "4Gi"
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: fast-block
        resources:
          requests:
            storage: 100Gi
~~~

This manifest illustrates Kubernetes structure, not a production-ready configuration for a specific database. Production deployments need official images, suitable StorageClasses, `securityContext`, probes, backup agents/operators, anti-affinity/topology spread, `PodDisruptionBudget`, secret injection, and database-specific bootstrap/replication procedures.

### Stable DNS

With a headless Service and StatefulSet, Pods resolve in the form:

~~~text
<statefulset-pod>.<headless-service>.<namespace>.svc.cluster.local
~~~

For example, `orders-db-0.orders-db.production.svc.cluster.local`. DNS stably locates a member; it does not prove that member holds the primary role or has permission to accept writes. The application must still verify roles and membership.

### PVC Lifecycle

PVCs created by a StatefulSet typically persist across Pod replacements. Deleting a StatefulSet does not necessarily delete PVCs under all policies; inspect cluster retention policies and storage reclaim policies. Never assume PVCs are always preserved or always deleted. Backups and restores must be managed independently.

## 11. Cluster Membership, Quorum, and Leader Election

Distributed applications often need to know which nodes are members, which node can accept writes, and when a leader can be elected.

### Membership

Membership records may track:

- Member ID or ordinal.
- Endpoint/DNS name.
- Role (voter, learner, replica, observer).
- Generation/term.
- Health/heartbeat.
- Replication position.
- Version and compatibility metadata.

Membership must be updated via the application's protocol—never infer it solely from whether a Pod exists or DNS resolves.

### Quorum

Many consensus systems require a quorum to commit changes. With `N` voting members, a majority quorum is typically:

\[
Q = \left\lfloor \frac{N}{2} \right\rfloor + 1
\]

For example, a 3-voter cluster needs 2 voters for a majority; a 5-voter cluster needs 3. Losing quorum can halt writes to preserve consistency.

Never arbitrarily increase replica counts without understanding the membership protocol. A new replica may need to bootstrap from a snapshot, catch up logs, and only then be promoted to voter.

### Leader Election

Leader election picks one member to coordinate writes or background work. It requires:

- Time-bounded leases/terms.
- Heartbeats.
- Protections preventing two active leaders simultaneously.
- Fencing tokens or monotonically increasing epochs.
- Procedures for network partitions.
- Observability for election churn.

An old worker can keep running after its lease expires due to GC pauses or network partitions. Storage or downstream systems must reject writes carrying stale epochs.

### Fencing

Fencing prevents a deposed member from continuing to write. For example:

- Node A holds term 12.
- A becomes network-partitioned.
- Node B is elected with term 13.
- B begins writing.
- A recovers and sends a write with term 12.
- The storage/consensus layer rejects A's write.

Updating a lock or DNS record alone is insufficient if an old client can still write directly to storage. Fencing must be enforced at the layer controlling side effects.

## 12. Persistent Volumes, Attach/Detach, and Single-Writer Safety

For block volumes, understand attachment semantics and access modes. Some volumes permit read-write attach/mount from only one node at a time; some storage supports multi-attach without automatically providing distributed locking or filesystem consistency.

### Procedure to Move a Volume to New Compute

1. Mark the old member to stop accepting new writes.
2. Fence or confirm the old member has stopped.
3. Flush data and detach the volume if the old host is still reachable.
4. If the old host died abruptly, follow storage/provider force-detach procedures and verify no writer remains active.
5. Attach the volume to the new machine/Pod.
6. Verify encryption keys, filesystem, and volume identity.
7. Run application/database recovery tools.
8. Verify consistency and replication position.
9. Reintroduce the new member into the cluster per the membership protocol.

Never attach the same writable filesystem to two machines simultaneously unless the storage and filesystem explicitly support concurrent multi-writer access. Doing so causes corruption even when both VMs appear healthy.

### Volume Topology

Persistent disks may be constrained to a single zone. A Pod bound to a PVC in zone A cannot schedule onto a node in zone B. Configure `StorageClass` topology, volume binding modes, and scheduler rules appropriately.

If zone failover is required, choose a storage/replication architecture that supports it. A zonal volume does not magically migrate to another zone just because a StatefulSet launches a new Pod.

## 13. Network Identity and Stable Endpoints

Stateful clusters typically require both stable client endpoints and stable member endpoints.

### Client Endpoints

Clients typically connect to:

- A load balancer or Service.
- A DNS alias pointing to the primary/leader.
- A managed database endpoint.
- A gateway or proxy capable of backend selection.

Client endpoints can point to the current primary after failover. Configure appropriate TTLs, health checks, and client retries.

### Member Endpoints

Each member may need a stable hostname for replication or heartbeats. StatefulSet headless DNS or private DNS records help here. However, DNS only maps names to addresses; cluster protocols still must authenticate members.

### Never Use IPs as Member IDs

If member IDs are derived from IP addresses, changing subnets or recreating nodes unexpectedly mutates membership. Use logical IDs managed in metadata, StatefulSet ordinals, or database cluster configurations, and use separate network endpoints for connectivity.

### DNS Caching and Failover

Clients may cache DNS records or hold connection pools open longer than DNS TTLs. After failover, ensure:

- Connections to the old endpoint are closed/refreshed.
- Retries use backoff.
- The new primary role is verified before writing.
- Transactions/idempotency handle indeterminate outcomes.
- Concurrent writes to both old and new primaries are prevented.

## 14. Secure Bootstrapping and Enrollment

A new machine must prove its identity before receiving secrets or joining a stateful cluster.

### Bootstrap Sequence

~~~mermaid
sequenceDiagram
    participant P as Provisioner
    participant VM as New compute
    participant ID as Identity service
    participant SM as Secret manager
    participant CL as Cluster control
    P->>VM: Create from trusted image
    VM->>ID: Present instance identity/attestation
    ID-->>VM: Short-lived workload credential
    VM->>SM: Request scoped secret/certificate
    SM-->>VM: Certificate/config
    VM->>CL: Register logical member and generation
    CL-->>VM: Membership/role decision
    VM->>VM: Attach data and recover state
    VM->>CL: Report readiness and replication status
~~~

### Principles

- Images must be built from trusted pipelines and versioned.
- Never bake unique machine credentials into images.
- The identity provider must verify the resource or workload before granting permissions.
- Credentials must be short-lived and rotated.
- The secret manager returns only scoped secrets.
- Logical member assignments must be issued or verified via the control plane.
- New nodes must not write before completing fencing/recovery.
- Audit enrollment, certificate issuance, secret access, and membership changes.

### Cloud-Init and Bootstrap Scripts

Bootstrapping should be idempotent and safe to re-run. Never overwrite data volumes, reset databases, or generate new member IDs if an earlier step was interrupted. Use versioned state/markers and check preconditions before executing destructive operations.

## 15. Credential Rotation and Identity Revocation

Credentials must be rotated periodically and during security incidents. Rotation should not disrupt the entire cluster.

A certificate rotation workflow can include:

1. Issue a new certificate for the instance/workload.
2. Update the trust bundle to accept both old and new certificates during the transition window.
3. Reload the service or establish new connections.
4. Verify mTLS with peers.
5. Revoke the old certificate once no longer in use.
6. Audit and confirm no clients are still using the old credential.

With managed identities, token rotation is usually handled by the platform; applications still must handle token expiration and refreshes.

When a VM is suspected of compromise:

- Revoke or disable the principal/certificate.
- Isolate the network.
- Fence the member from write permissions.
- Replace compute from a trusted image.
- Issue new credentials.
- Restore or verify the data volume.
- Inspect audit logs and secret access history.
- Rejoin the cluster only after verifying integrity.

Do not delete an old identity before checking dependencies and completing needed audits, though dangerous access permissions must be blocked immediately per incident procedures.

## 16. Scaling Stateful Workloads

Scaling stateful workloads is more complex than adding stateless replicas because each replica may carry distinct data, identities, and roles.

### Vertical Scaling

Increase CPU/RAM/storage throughput for existing members. Suitable when:

- The database does not yet require sharding.
- A single shard requires large memory.
- Workloads have limited parallelism.
- Horizontal scaling introduces excessive coordination overhead.

Evaluate downtime, online resize support, volume IOPS, and licensing.

### Horizontal Scaling

Can include:

- Read replicas to increase read throughput.
- Sharding/partitioning to distribute data.
- Broker partitions to spread consumers.
- Search shards/replicas to scale indexes.
- StatefulSet replicas to maintain member identities.

Adding replicas does not automatically increase write capacity. If all members funnel writes through a single leader, that leader remains the bottleneck.

### Scale-In

Before reducing replicas:

- Identify which shards, partitions, or leader roles the member holds.
- Rebalance or migrate data.
- Drain clients/connections.
- Remove the member cleanly through the official protocol.
- Verify remaining replication and quorum stay healthy.
- Only then detach/delete storage or compute.

Deleting Pods/VMs directly can cost the cluster quorum or force expensive shard rebuilds.

### Autoscaling

Generic autoscalers do not understand all stateful application semantics. Use dedicated controllers/operators or explicit workflows to scale members, rebalance data, handle joins/leaves, and preserve quorum. Never attach an HPA to scale a database cluster if the database does not support dynamic membership.

## 17. Deployment, Upgrades, and Rolling Replacement

Stateful apps require compatibility across application versions, schemas, data formats, and cluster protocols.

### Rolling Updates

Replace members one by one in an order supported by the application:

1. Verify cluster health and low replication lag.
2. Select an eligible member to restart per protocol.
3. Drain traffic or transfer roles.
4. Take backups/checkpoints as required.
5. Replace compute or image.
6. Provision identity/certificates and attach data.
7. Start up, recover, and catch up replication.
8. Verify health, version, and membership.
9. Proceed to the next member.

Never restart multiple voters simultaneously if doing so risks losing quorum.

### Expand-and-Contract Migrations

When schemas or data formats change:

- Add new structures compatible with the old version.
- Deploy a version that reads/writes both or maintains compatibility.
- Backfill data.
- Switch consumers to the new structure.
- Verify no old members remain.
- Remove old structures in a later release.

### Rolling Back Images Does Not Roll Back Data

Rolling back a VM/container image does not undo schemas or data written by the newer version. Maintain a compatibility window, backups, and migration/compensation strategies.

## 18. Availability, Backups, and Recovery

Stateful workloads need explicit plans for data protection and member recovery.

### Backups

- Database backups with application consistency and point-in-time recovery where needed.
- Volume snapshots scheduled around consistency requirements.
- Object versioning/retention.
- Backup encryption keys and controlled restore permissions.
- Backing up metadata/configuration/identity policies needed to rebuild.
- Separating backup deletion privileges from routine workload operations.
- Periodic restore tests.

### Replication

Replication lowers RPO and enables failover, yet it can also replicate corruption or accidental deletions. Combine replication with immutable backups and point-in-time recovery.

### RPO/RTO

Define per workload:

- RPO: acceptable data loss window.
- RTO: target service recovery time.
- Failover time: time to detect, decide, promote, and shift traffic.
- Rebuild time: time to provision compute, attach storage, recover, and catch up.

### Recovery Sequence

1. Identify the incident and recovery point.
2. Fence old members or stale writers.
3. Restore storage/replicas.
4. Provision new compute from a tested image.
5. Issue identities/certificates.
6. Attach volumes and run recovery.
7. Rejoin membership/quorum.
8. Verify consistency and transactions.
9. Update DNS/endpoints and shift traffic.
10. Monitor SLOs, replication, and audit logs.

## 19. Architecture Example: Order Storage Service with Stateful Members

An order system consists of an API, a three-member database cluster, and event-processing workers.

~~~mermaid
flowchart TD
    U[Client] --> LB[Load balancer / stable DNS]
    LB --> API1[Stateless API A]
    LB --> API2[Stateless API B]
    API1 --> DBP[(Database primary)]
    API2 --> DBP
    DBP --> DBR1[(Replica 1)]
    DBP --> DBR2[(Replica 2)]
    API1 --> Q[(Durable queue)]
    API2 --> Q
    Q --> W[Idempotent workers]
    W --> OS[(Object storage)]
    subgraph Identity
      WI[Workload identity]
      CA[Certificate authority]
      SM[Secret manager]
    end
    API1 -.-> WI
    API2 -.-> WI
    DBP -.-> CA
    DBR1 -.-> CA
    DBR2 -.-> CA
    WI --> SM
~~~

Design:

- Stateless API runs multiple replicas; each Pod/VM uses the `orders-api` role with least privilege.
- Database members hold dedicated logical identities and distinct certificates.
- Database data sits on persistent volumes or a managed database service.
- Client DNS/service endpoint points to the active writer.
- Replication and consensus/database protocols manage member state.
- Queue workers enforce idempotency and checkpoints.
- Backups are stored in independent storage with retention rules.
- Monitoring tracks replication lag, quorum, connections, storage latency, and certificate expiry.

### When the Primary Fails

1. The cluster detects the primary is unhealthy.
2. Consensus/election selects the member eligible to take over.
3. Fencing prevents the old primary from writing if it recovers late.
4. A replica is promoted per database protocol.
5. DNS/proxy/load balancer updates the writer endpoint.
6. The API reconnects and retries safely using transactions/idempotency.
7. Old compute is isolated and its credentials revoked or rotated.
8. A replacement node is provisioned and rejoins procedurally.

Never automatically point DNS to a replica solely because a TCP health check succeeds. The writer endpoint must be determined by database role or an authoritative control plane.

## 20. Example Workload Identity Policy

Illustrative policy:

| Principal | Permitted | Should Not Be Granted |
|---|---|---|
| orders-api | Read DB secrets, connect to DB under app role, publish order events | Cluster administration, deleting backups, rotating CA |
| orders-db-member | Read own certificate, replicate with peers, access member volume | Reading API secrets or administering the whole cloud account |
| orders-worker | Consume queue, read input objects, write outputs, update job status | Direct writes to unrelated database admin tables |
| backup-agent | Read data per backup policy and write to backup vault | Deleting backup retention locks or workload admin rights |
| platform-operator | Perform audited operational tasks via approved workflows | Sharing runtime application credentials |

Separating roles ensures that if a worker is compromised, an attacker cannot administer the database or wipe backups. With per-instance identities, you can revoke the exact certificate or principal of a compromised member.

## 21. Securing State and Machine Identities

### Data at Rest

- Encrypt boot/data volumes and object storage.
- Use customer-managed keys when tighter control is required.
- Scope key permissions separately for workloads and backups.
- Never leave credentials in unprotected snapshots/images.
- Enforce retention and secure deletion policies.

### Data in Transit

- Enforce TLS/mTLS between members and services.
- Verify hostnames/SANs and trust chains.
- Rotate certificates with overlap windows.
- Never disable certificate verification to bypass errors.
- Use private networks and workload-level segmentation.

### Runtime Hardening

- Patch OS, kernel, container runtime, and applications.
- Run non-root with least privilege.
- Protect metadata endpoints.
- Disable unnecessary administrative ports.
- Audit SSH/remote access and control plane APIs.
- Ship logs off-compute so they survive instance deletion.

### Clones and Snapshots

Snapshots may contain machine-specific state such as host keys, certificates, node IDs, local accounts, or secret caches. Before provisioning a new machine from a snapshot, determine which components must be regenerated and which stateful data must be preserved.

Never clone a cluster member's raw data volume to create two independent writers. To add replicas, use the cloning/bootstrapping mechanism supported by the database or distributed system.

## 22. Observability and Operations

Monitor compute, storage, identity, and cluster protocols together.

### Compute

- CPU, memory, disk pressure, and network throughput.
- Restarts, evictions, node health, and boot times.
- Container/VM versions and image drift.
- Startup/readiness durations.

### State and Storage

- Volume attach/detach errors.
- IOPS, throughput, latency, and queue depth.
- Database transaction log/WAL growth.
- Replication lag and recovery times.
- Backup success, restore tests, and retention.
- Checkpoint age and job resume status.

### Identity

- Token issuance/refresh failures.
- Certificate expiry, rotation, and revocation.
- Authentication/authorization failures.
- Duplicate logical identities or instance identities.
- Anomalous metadata endpoint access.
- Secret manager access audits.

### Cluster

- Member count, quorum status, and leader changes.
- Election churn and fencing rejections.
- Split-brain suspicions.
- Node join/leave durations.
- Client reconnects, DNS updates, and endpoint shifts.
- Version skew and schema compatibility.

Never write tokens, private keys, passwords, or raw private certificate material to logs. Log identity references, certificate serials/fingerprints, and correlation IDs safely.

## 23. Common Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| New machine cannot fetch secrets | Managed identity/role not attached, wrong trust policy, or token endpoint error | Instance profile, service account binding, IAM audit |
| Certificate rejected | SAN/identity mismatch, stale trust bundle, or expired certificate | Issuance, expiry, SANs, CA bundle, system clock |
| Pod has stable name but fails to join cluster | DNS/Service works, but membership or credentials are wrong | Cluster member registry, mTLS identity, join protocol |
| Volume attach fails | Volume still attached to old host, zone mismatch, or unusable encryption key | Attachment state, fencing, topology, KMS |
| Two members writing simultaneously | Split-brain or broken fencing | Leader term, quorum, writer leases, storage enforcement |
| StatefulSet Pod Pending | PVC topology, storage capacity, taints/affinity, or quotas | Events, PVC/PV, StorageClass, node capacity |
| New Pod boots with wrong data | Wrong volume attached, old restore point, or incompatible schema | Volume ID, backup timestamp, schema/version |
| Failover succeeds but clients still fail | DNS caching, stale connection pools, or un-updated endpoints | DNS TTL, client reconnects, proxy/Service endpoints |
| Scale-in breaks quorum | Removed voter before reconfiguring membership | Membership state, PDBs, quorum policy |
| Cloned VM causes duplicate identity | Image contains host keys/certificates/member IDs | Image build, bootstrap regeneration, identity audits |

### Investigation Procedure

1. Identify the logical member ID and current resource ID.
2. Verify authentication identity and certificates.
3. Check endpoints/DNS and routing.
4. Inspect volume ID, attachment, encryption keys, and filesystem.
5. Read cluster membership, term, quorum, and replication lag.
6. Confirm no stale writer remains active.
7. Run application consistency/health checks.
8. Open traffic or allow writes only once state is unambiguous.

## 24. Testing Replacement, Failover, and Identity Lifecycle

A stateful design must be tested under realistic compute replacement scenarios.

| Scenario | How to Test | Expected Result |
|---|---|---|
| VM reboot | Reboot a member procedurally | Data volume and identity recover cleanly |
| VM replacement | Launch a new VM from image and attach volume per runbook | New instance ID, intact logical role, fresh credentials |
| Container restart | Restart container inside a Pod | Persistent data intact, process recovers cleanly |
| StatefulSet Pod replacement | Delete a Pod in a controlled manner | Pod ordinal/DNS/PVC intact, safe cluster rejoin |
| Certificate rotation | Issue new certificates and revoke old ones | Peer trust transitions without downtime |
| Identity revocation | Revoke principal/certificate of a test member | Member is blocked and cannot continue accessing resources |
| Node/zone failure | Make a node or zone unavailable in staging | Quorum and availability hold as designed |
| Split-brain simulation | Network-isolate an old member | Fencing prevents the old member from writing |
| Volume recovery | Restore snapshot into an isolated environment | Integrity checks and application recovery succeed |
| Scale-in | Remove a member via protocol | Quorum, replication, and data placement remain intact |
| Rolling upgrade | Upgrade members one by one | Version/schema compatibility preserved |
| Restore from backup | Restore cluster into a fresh environment | Data, identities, and endpoints recreate cleanly |

Conduct fault injection only within authorized environments and scopes. For production, use change windows, observers, abort criteria, and rollback plans.

## 25. Checklist for Deploying Stateful Applications and Machine Identities

### State and Storage

- [ ] State inventory, sources of truth, and retention are documented.
- [ ] Critical data resides on storage with an appropriate lifecycle.
- [ ] Ephemeral disks hold only regenerable data.
- [ ] Persistent volumes have clear attachment/topology semantics.
- [ ] Backups, snapshots, replication, and restore tests meet RPO/RTO.
- [ ] Post-recovery consistency checks are defined.

### Machine/Workload Identity

- [ ] Resource ID, logical identity, authentication identity, and network identity are clearly separated.
- [ ] IPs or hostnames are never used as sole credentials.
- [ ] Images contain no private keys, unique machine IDs, or secrets.
- [ ] Workloads use appropriate managed identities/service accounts/certificates.
- [ ] Permissions follow least privilege and are separated by workload role.
- [ ] Credentials have expiry, rotation, and revocation.
- [ ] Enrollment and identity issuance are audited.
- [ ] Clones/restores include procedures to regenerate identities.

### Cluster and Lifecycle

- [ ] Member IDs, ordinals, membership, and endpoints are defined.
- [ ] Quorum, leader election, and fencing are thoroughly understood.
- [ ] Volumes enforce single-writer or supported storage/application semantics.
- [ ] Scale-in removes/rebalances members before deleting compute.
- [ ] StatefulSet/PVC/headless Service retention policies are explicit.
- [ ] Rolling upgrades maintain schema/version compatibility.
- [ ] Failover/failback has been rehearsed.

### Network, Security, and Operations

- [ ] DNS/service discovery provides stable endpoints.
- [ ] mTLS/TLS and certificate validation are active.
- [ ] Network segmentation and firewalls follow least privilege.
- [ ] Metadata endpoints and node access are locked down.
- [ ] Metrics cover storage, replication, quorum, identity, and certificate expiry.
- [ ] Logs/audits are shipped off-instance.
- [ ] Runbooks exist for machine replacement, identity revocation, volume restore, and cluster rejoin.

## 26. Self-Check

1. How does a stateful application differ from stateful compute?
2. Why do persistent volumes not replace backups?
3. Distinguish resource identity, logical identity, authentication identity, and network identity.
4. Why should private IPs not be used as machine identities?
5. When replacing a VM, what must remain stable and which credentials should be reissued?
6. What different needs do managed identities and per-instance certificates solve?
7. How does a StatefulSet provide stable identity and storage association, and what does it leave unsolved?
8. Why does a stable DNS name not prove a member is authorized to act as primary?
9. Which failures do quorum and fencing prevent during a network partition?
10. Why must you not attach the same block filesystem read-write to two nodes unless storage supports it?
11. When scaling in a database cluster, what steps must happen before removing a member?
12. How do you test machine replacement to verify data, identity, and membership recover properly?

Safely deploying stateful applications requires synchronizing three lifecycles: compute must be replaceable, data must be protected per business requirements, and identities must clearly prove who is accessing resources or participating in a cluster. Logical identities and endpoints can remain stable so the system continues recognizing members; authentication credentials should be issued and rotated along the compute trust lifecycle. Combining persistent storage, membership, quorum, fencing, workload identity, backups, and replacement testing lets applications recover cleanly without depending on any single VM or container.
