# Backing Up and Restoring AKS Applications and Data

An application running on **Azure Kubernetes Service (AKS)** can be redeployed quickly from container images and manifests. However, if a database is accidentally deleted, a PersistentVolume (PV) is corrupted, or an entire cluster goes down, simply spinning up new pods **does not restore business data and state**. That is why an AKS backup strategy must span multiple layers: Kubernetes configurations, volume data, off-cluster data services, Azure infrastructure, and verified restore procedures.

For example, an ordering system has an API in a Deployment, PostgreSQL in a StatefulSet with a PersistentVolumeClaim (PVC), secrets in Azure Key Vault, and invoice images in Blob Storage. Saving the Deployment YAML alone will not restore the orders table; taking a snapshot of the PostgreSQL disk will not recreate Azure Load Balancers, DNS, private endpoints, or workload identity permissions. **A solid recovery plan must spell out what is backed up, what is recreated, and in what order.**

This lesson belongs to the **AKS Operations** chapter on the Microsoft Azure learning path—spanning subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, data, monitoring, security, and cost governance for Azure application architectures.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **backup**, **snapshot**, **replication**, **GitOps/IaC**, and **disaster recovery (DR)**.
2. Classify the layers requiring protection: Kubernetes resources, persistent volumes, off-cluster services, and Azure configuration.
3. Define **RPO**, **RTO**, acceptable data loss bounds, and recovery priorities.
4. Understand the approach of **Azure Backup for AKS**, CSI `VolumeSnapshot`, and Kubernetes backup tools.
5. Distinguish **crash-consistent**, **application-consistent**, and point-in-time database recovery.
6. Design backup policies, retention windows, access controls, encryption, monitoring, and error handling.
7. Author a runbook to restore namespaces, workloads, PVCs, and dependent components.
8. Conduct verified restore drills in a test environment without impacting production.

## 1. What Actually Needs to Be Backed Up in AKS?

A Kubernetes application does not live in a single file or a single disk. Break state down into layers:

| Layer | Examples | Primary Protection Mechanism |
|---|---|---|
| **Azure infrastructure declarations** | AKS cluster, VNet, subnets, routes, ACR, Key Vault, private endpoints | Bicep/Terraform/ARM, versioned configs, recreation pipelines |
| **Kubernetes desired state** | Namespaces, Deployments, StatefulSets, Services, Ingresses, ConfigMaps, RBAC, NetworkPolicies | GitOps, Helm, manifests, plus cluster resource backups where needed |
| **PV/PVC stored data** | Database or application data mounted on volumes | Supported volume snapshots/backups, app-level backup mechanisms |
| **Off-cluster data** | Azure Database for PostgreSQL, Azure SQL, Blob Storage, Cosmos DB | Native backup/PITR/replication of each data service |
| **Secrets and identities** | Key Vault, workload identity, managed identity, RBAC, certificates | Supported config backups/controls, identity and key recovery plan |
| **Artifacts** | Container images, Helm charts, migration packages | Managed ACR/registries and artifact stores with version retention |
| **Operational evidence** | Logs, metrics, audit trails, backup reports | Azure Monitor / Log Analytics with policy-defined retention |

**Kubernetes manifests do not contain PersistentVolume contents.** Conversely, restoring a volume does not recreate the Services, NetworkPolicies, or ConfigMaps that workloads rely on. Both must stay version-consistent with the application release.

### The AKS Control Plane Is Not a Self-Managed `etcd`

AKS is a managed Kubernetes service. Users manage the cluster via the Kubernetes API, but should not plan to directly access and back up AKS's `etcd` as they would on a self-hosted cluster. On AKS, the practical path is protecting Kubernetes resources through supported mechanisms, storing desired state in Git, and backing up durable data properly.

Never take an ad-hoc resource export and call it a **full-cluster backup** without accounting for CRDs, volumes, secrets, cluster-scoped objects, and external data.

## 2. RPO and RTO: Start from Business Requirements

**Recovery Point Objective (RPO)** is the maximum acceptable data loss measured in time when an incident hits. **Recovery Time Objective (RTO)** is the target duration to restore service to an acceptable operating level.

Example:

~~~text
Ordering application
RPO = 15 minutes
RTO = 2 hours

Incident occurs at 14:00
RPO targets recovered data state no older than 13:45
RTO targets restoring usable service before 16:00
~~~

These are **business targets**, not guarantees achieved merely by scheduling a backup every 15 minutes. The system must have usable backups/transaction logs, recovery infrastructure, and drills proving those targets are achievable.

### Set Targets by Component

| Component | Risk If Lost | Suggested Strategy |
|---|---|---|
| Stateless frontend | Can be rebuilt from images/manifests | GitOps and registry; short RTO |
| Stateless API | Can be recreated once dependencies are up | IaC, GitOps, secrets/identities |
| Order database | Lost transactions, customer impact | Database backup/PITR aligned with RPO |
| Uploaded attachments | Lost user documents | Service-appropriate backup, versioning, or replication |
| Rebuildable cache | Performance hit without losing source truth | Warm-up/rebuild strategy |
| Audit logs | Compliance/audit gaps | Retention/backup per compliance rules |

A multi-tier architecture typically requires **dependency-ordered recovery** rather than starting every pod at once.

### Mental Time Breakdown

~~~text
Actual RTO can include:
  T_detect
  + T_approve / T_decide
  + T_provision_cluster_and_network
  + T_restore_resources
  + T_restore_data
  + T_validate
  + T_switch_traffic

Actual RPO depends on:
  timestamp of last valid backup / transaction log
  + backup schedule latency / failures
  + ability to recover data to the target point in time
~~~

Never cite just the execution time of a restore command as your RTO. DNS propagation, data validation, traffic cutover, and approval gates all consume time.

## 3. Backup, Snapshot, Replication, and GitOps Are Not the Same

| Mechanism | Question Answered | Weakness If Used Alone |
|---|---|---|
| **Snapshot** | Can we capture a point-in-time volume state? | May only be crash-consistent; bound to storage/region/driver; lacks full app state |
| **Backup** | Do we have managed recovery points with retention and policy? | Not guaranteed restorable without testing or missing dependencies |
| **Replication** | Is there a near-real-time copy elsewhere? | Bugs, accidental deletes, or bad writes replicate to the replica too |
| **GitOps/IaC** | Can we recreate declared configuration? | Does not restore runtime-generated data |
| **PITR** | Can we restore a database to a specific point in time? | Depends on service, transaction log backups, retention bounds, and base backups |
| **Disaster recovery** | Do we have a plan to rebuild the full service after a major outage? | Requires multiple layers, clear owners, and regular drills |

**A snapshot is not automatically a region-resilient backup.** Snapshots may live within the same storage scope or region; check backup tiers, cross-region copy capabilities, and recovery points independent of the primary system.

### Risks Replication Cannot Fix

If an application accidentally deletes all rows and that deletion replicates, the replica mirrors the damaged primary. Returning to before the deletion requires **historical recovery points** such as backups, PITR, or object versioning.

## 4. AKS Incident Scenarios to Prepare For

| Scenario | Symptom | Approach |
|---|---|---|
| Accidental Deployment deletion | Pods vanish, data intact | Restore manifests via GitOps/Helm |
| Accidental PVC/PV deletion | Workload cannot mount data | Restore volume from eligible backup or snapshot |
| Bad database writes | Pods run fine yet data is corrupted | PITR or logical/physical database restore |
| Node pool failure | Pods cannot schedule | Restore node capacity, reschedule, verify storage |
| Namespace deletion | Missing Kubernetes resources and possibly PVCs | Restore namespace-scoped resources, volumes, and dependencies |
| Cluster deleted or unusable | Kubernetes API/workloads down | Recreate target cluster via IaC, restore apps and data |
| Regional outage | Multiple Azure services impacted together | Fail over to prepared DR region; backups/data must be restorable there |
| Ransomware / compromised account | Data or backups deleted/tampered | Separate permissions, immutable/offsite backups where supported, verify clean before restore |
| Faulty app update | New image/config causes failures | Roll back app version; restore data if schema migrations had side effects |

Common thread: recover at the **exact layer that failed**. Recreating a Deployment will not fix a corrupted database; restoring an entire volume is overkill if only a ConfigMap was deleted.

## 5. AKS Backup Architecture Map

Reference model:

~~~text
                        Azure Resource Manager
                       Bicep / Terraform / GitOps
                                  |
                                  v
                  AKS cluster (running applications)
                    |               |             |
                    v               v             v
             K8s resources     PVC/PV data     External services
             Namespace/CRD     Azure Disk      SQL/Blob/Key Vault
                    |               |             |
                    |               |             |
                    +---- Backup/restore ----+    +-- Separate backup/PITR
                              |
                              v
                    Recovery points
                  + policy + retention
                              |
                              v
                Backup vault / backup storage
                (per chosen backup solution)
                              |
                              v
                      Recovery cluster
                              |
                              v
              Validate data, auth, and networking
                              |
                              v
                    Controlled traffic cutover
~~~

**No single tool automatically backs up every box in this diagram.** Azure Backup for AKS, CSI driver snapshots, Kubernetes tools like Velero, managed database backups, and GitOps each cover distinct scopes.

In production designs, maintain a **backup coverage matrix** documenting how each resource is protected, who owns it, and how restores are proven.

## 6. What Is Azure Backup for AKS?

**Azure Backup for AKS** is an Azure Backup solution designed to protect AKS cluster components within supported features and configurations. It uses Azure Backup constructs—**Backup vault**, **backup policy**, **backup instance / recovery points**, and an in-cluster extension—alongside supported volume data protection.

Depending on version and support scope, it can back up Kubernetes resources and PersistentVolume data for supported storage types, commonly involving **Azure Disk CSI-backed persistent volumes** and snapshots. Components such as Azure Files, other CSI drivers, Windows workloads, specialized cluster modes, CRDs, and off-cluster data must be evaluated separately.

### Key Components to Recognize

| Component | Role |
|---|---|
| **Backup vault** | Manages backup instances, policies, recovery points, and service-level protections |
| **Backup policy** | Defines backup schedules, retention, and supported settings |
| **AKS backup extension** | Component deployed inside the cluster to coordinate backups/restores per service design |
| **Trusted Access / role assignments** | Trust, identity, and RBAC required between the backup service, cluster, and Azure resources |
| **Storage account / backup storage** | Stores backup artifacts/state where required by the solution |
| **Snapshot resource group** | Holds volume snapshots per configured settings |
| **Backup instance** | Protected target resource and its backup history state |
| **Recovery point** | Point-in-time data/resource artifact usable in supported restore operations |

Exact resource names, fields, retention tiers, and recovery point formats evolve with Azure Backup. Always consult **current AKS backup documentation and region/cluster/storage support matrices** before deploying.

### What Azure Backup for AKS Does Not Do Automatically

- Does not back up or restore contents of external **Azure SQL, PostgreSQL, Cosmos DB**, or Blob Storage data outside the cluster.
- Does not automatically capture full **ARM configurations** of VNets, private endpoints, firewalls, Azure Load Balancers, DNS, or identities in all scenarios.
- Does not guarantee application transaction consistency simply because a volume snapshot succeeded.
- Does not promise identical restore portability across every PVC/CSI driver type.
- Does not automatically recreate external secrets or guarantee encryption keys/Workload Identity work out of the box.
- Does not replace periodic restore testing and operational runbooks.

## 7. Distinguishing Backup Vault vs Recovery Services Vault

In Azure, not every backup type uses the same vault or CLI/API. For instance, traditional VM backups typically use a **Recovery Services vault**, whereas newer Azure Data Protection solutions like **Azure Backup for AKS** use a **Backup vault** within supported scopes.

| Service | Typical Backup Management Store | Notes |
|---|---|---|
| Azure Backup for AKS | Backup vault and integrated AKS backup components | Schedules, retention, K8s resources/PV scope per support matrix |
| Azure VM backup | Recovery Services vault per service capabilities | Protects VMs/disks under the Azure VM Backup model |
| Azure Database for PostgreSQL / Azure SQL | Native service backup/PITR or supported solution | Restores under database-specific rules |
| Blob Storage | Versioning/soft delete/backup or matching mechanism | Not included by default in an AKS backup |

Never assume having a Recovery Services vault in a subscription means AKS application data is backed up. **Verify the exact backup instance for the target resource.**

## 8. PersistentVolume, PVC, and CSI VolumeSnapshot

In Kubernetes:

- **PersistentVolume (PV)** represents provisioned storage capacity in the cluster.
- **PersistentVolumeClaim (PVC)** is a workload's request for storage.
- **StorageClass** defines how volumes are provisioned.
- **CSI driver** bridges Kubernetes with backend storage.
- **VolumeSnapshotClass**, **VolumeSnapshot**, and **VolumeSnapshotContent** manage CSI snapshots when supported by the cluster and storage driver.

~~~text
StatefulSet / Pod
      |
      v
     PVC
      |
      v
     PV
      |
      v
CSI storage driver
      |
      v
Azure Disk / supported storage backend

VolumeSnapshot -> SnapshotContent -> Backend snapshot
~~~

A Kubernetes **`VolumeSnapshot`** is a declarative object requesting a snapshot and tracking its status. It does not by itself replace a full backup strategy with schedules, retention, off-cluster storage, and recovery after losing the entire cluster.

### Check Whether the Environment Supports Snapshots

~~~bash
kubectl get storageclass
kubectl get pv
kubectl get pvc --all-namespaces
kubectl get volumesnapshotclass
kubectl get volumesnapshot --all-namespaces
~~~

`get volumesnapshotclass`/`volumesnapshot` will fail if snapshot CRDs/CSI snapshot components are not installed; treat that as a sign to verify supportability rather than installing extra components in production just for a lab.

### PV Reclaim Policy

A StorageClass/PV carries a **`Retain`** or **`Delete`** reclaim policy. If a workload deletes a PVC while its PV uses **`Delete`**, the underlying storage backend may be wiped by the provisioner. Setting `Retain` everywhere is not a silver bullet either: it leaves orphaned disks and ongoing charges.

Before restoring, inspect **reclaim policies, finalizers, binding modes, volume affinity, access modes, and StorageClasses**. Restoring into a new PVC must avoid accidentally overwriting or deleting an active source disk.

## 9. CSI `VolumeSnapshot` Manifest Example

The YAML below illustrates snapshotting the **`orders-data`** PVC in the **`shop-data`** namespace. Use only in a lab cluster where the CSI driver and snapshot class are supported and verified.

~~~yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: orders-data-snap-lab
  namespace: shop-data
spec:
  volumeSnapshotClassName: "<SUPPORTED_SNAPSHOT_CLASS>"
  source:
    persistentVolumeClaimName: orders-data
~~~

The placeholder string in this example **is not a valid snapshot class**. Substitute the verified name from your cluster. Creating snapshots can incur storage charges and requires appropriate RBAC.

### Check Snapshot Status

~~~bash
kubectl get volumesnapshot -n shop-data
kubectl describe volumesnapshot -n shop-data orders-data-snap-lab
~~~

Status fields such as **`readyToUse`** and the bound **`VolumeSnapshotContent`** indicate whether the snapshot is ready. However, **`readyToUse=true` does not prove database contents are transactionally consistent**.

### Restore to a New PVC Rather Than Overwriting Blindly

Example creating a new PVC from a `VolumeSnapshot`:

~~~yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: orders-data-restore-lab
  namespace: shop-data
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: "<SUPPORTED_STORAGE_CLASS>"
  resources:
    requests:
      storage: 64Gi
  dataSource:
    name: orders-data-snap-lab
    kind: VolumeSnapshot
    apiGroup: snapshot.storage.k8s.io
~~~

This is an **illustrative template**. Volume type, size, region/zone, snapshot class, and StorageClass must align. Restoring into a new PVC depends on CSI driver and backend support; not every cluster/region/zone combination works.

**Never mount the same `ReadWriteOnce` PVC across multiple independent nodes assuming it is safe.** Verify disk attachment rules and access modes. For databases, restore to an isolated instance and validate integrity before switching traffic.

## 10. Crash-Consistent vs Application-Consistent

A **crash-consistent snapshot** captures disk block state at an instant, similar to pulling the power plug on an OS or application. Filesystems and databases may need to replay journals/WAL upon startup.

An **application-consistent backup** coordinates with the application so data reaches a clean state—flushing buffers, checkpointing, quiescing writes, or invoking database backup APIs.

| Consistency Level | What It Protects | Limitations |
|---|---|---|
| Crash-consistent snapshot | Block storage state at snapshot time | Transactions spanning multiple disks/services may not align |
| Application-consistent | Data after application-coordinated quiesce/flush | Requires properly designed hooks/backup protocols |
| Database-native backup/PITR | Logical/physical DB state plus transaction logs | Requires its own config, retention, and restore procedures |
| Multi-service consistency | Consistency across DB, queues, Blob, cache, and app | Requires business checkpoints, transactions, or reconciliation |

### Why Snapshotting Three Disks Does Not Automatically Yield a Transaction Point

A database may spread files across separate volumes: data volume, WAL volume, and auxiliary files. If snapshots fire sequentially, they capture slightly different timestamps, potentially leaving the database unrecoverable without manual repair.

Therefore:

1. Determine whether your app can safely tolerate crash-consistent restores.
2. If not, use **database-native backups**, quiesce hooks, or storage mechanisms supporting application-consistent snapshots.
3. For multi-volume databases, verify coordinated multi-volume snapshot support and ordering.
4. Always **test restores** and verify data constraints.

**Never claim every Azure Disk CSI snapshot is automatically application-consistent.** That depends on application coordination and specific feature support.

## 11. Databases in AKS: Back Up at the Database or Disk Layer?

Consider PostgreSQL running in a StatefulSet. There are at least three options:

| Strategy | Scope | Best Fit |
|---|---|---|
| CSI `VolumeSnapshot` | On-disk state at snapshot instant | Fast volume restore when crash-consistency is acceptable and tested |
| Database logical backup | Schema/data exported via tools like `pg_dump` | Logical migrations/restores, small-to-medium DBs as requirements allow |
| Physical backup + WAL/PITR | Base physical backup plus transaction log archive | Low RPO and point-in-time recovery when configured properly |

A volume snapshot of PostgreSQL **does not replace** WAL archiving when business SLAs demand a 5-minute RPO and PITR. Conversely, a nightly `pg_dump` cannot meet a 15-minute RPO.

### Example Verifying a PostgreSQL Logical Backup

These commands illustrate **database tooling only**, not commands to run directly on production AKS:

~~~bash
# From an authorized admin environment with secure DB connectivity.
pg_dump --format=custom \
  --dbname="<POSTGRES_CONNECTION_DSN>" \
  --file="orders-2026-11-20.dump"

# Inspect backup table of contents without restoring.
pg_restore --list "orders-2026-11-20.dump"
~~~

Protect dump files like production data: encrypt them, enforce RBAC, manage retention, verify checksums, and store them in an independent location. **`pg_restore --list` does not prove a restore will succeed**; restore into a test database and validate rows and constraints.

Never put passwords in shell history, public command lines, or pipeline logs. Use secure auth/secret delivery mechanisms.

### Database Services Outside AKS

If the app uses **Azure Database for PostgreSQL Flexible Server**, **Azure SQL**, Cosmos DB, or another managed service, use **that service's** native backup/PITR features per support terms. Backing up an AKS namespace does not capture PaaS database contents.

## 12. GitOps and IaC Are Indispensable

Backing up Kubernetes resources helps, yet **desired state in Git** enables repeatable reconstruction and change control:

- Bicep/Terraform defines AKS, VNets, subnets, ACR, Key Vault, private DNS, and role assignments.
- Helm/Kustomize/YAML defines Deployments, StatefulSets, Services, ConfigMaps, NetworkPolicies, and RBAC.
- Flux/Argo CD or deployment pipelines reconcile desired state into the cluster.
- Registries store images using **immutable tags/digests**.

### Why Not Just Save `kubectl get -o yaml`?

A live cluster export includes **`status`, `resourceVersion`, `UID`, `managedFields`, runtime IPs, secret values**, and fields unsuitable for re-applying cleanly. It may also omit CRDs, cluster-scoped objects, or Azure infrastructure definitions.

When restoring via GitOps, apply reviewed source manifests and environment parameters. For backup tools, understand which resource types are included and whether non-restorable fields are stripped.

### Be Careful When GitOps Runs During a Restore

If a GitOps controller reconciles automatically mid-restore, it can:

- Delete newly restored resources absent from Git.
- Overwrite restored images/configs with current versions.
- Scale up workloads before PVCs/data finish restoring.
- Trigger database connections and app migrations prematurely.

Your runbook must define **when to suspend or control reconciliation**, resuming only once data and manifests are ready.

## 13. Protecting Kubernetes Secrets and Identities

A backup containing Kubernetes **`Secret`** objects can hold tokens, passwords, or certificates even though `data` values appear Base64-encoded. **Base64 is not secret encryption.**

Recommendations:

1. Prefer **Azure Key Vault**, workload identity, and External Secrets / Secrets Store CSI Driver per supported architecture.
2. Store secret *references* in Git, **never commit secret values**.
3. Evaluate whether backups truly need copies of Secrets or whether they should be re-fetched securely from Key Vault.
4. If backups contain Secrets, encrypt backup stores, restrict access, audit reads, and maintain post-incident rotation plans.
5. When rebuilding a new cluster, re-establish **OIDC issuer / workload identity trust, managed identities, federated credentials, and RBAC**; new clusters can have different issuers/identities.
6. Protect encryption keys / Key Vault access needed to decrypt backups or volumes.

**Never blindly restore old ServiceAccount tokens or stale identity configs** into a new cluster expecting permissions to keep working. Verify trust and identity bindings on the target cluster.

## 14. Preparing Azure Backup for AKS

The steps below form a **deployment framework**, not copy-paste commands for every subscription. Supported versions, regions, tiers, and CLI flags evolve.

### Step 1: Check Compatibility

Verify:

- AKS cluster version, node pools, Kubernetes APIs, and add-on/network settings.
- Azure Disk CSI driver, StorageClasses, PVC/PV types, and snapshot support for PV backups.
- Namespaces and resource types requiring backup.
- Regions for the cluster, vault, storage, and snapshots—plus target restore region support.
- Quotas, snapshot permissions, and cost.
- Backup/retention policies aligned with supported limits and RPO targets.

If a PVC uses a storage type outside the solution's support matrix, **never mark that data as protected** simply because Kubernetes manifests backed up cleanly.

### Step 2: Design Azure Backup Resources

Prepare components per current documentation:

1. **Backup vault** in an approved subscription/resource group.
2. **Backup policy** with appropriate schedule and retention.
3. **AKS backup extension** on the cluster with required connectivity.
4. **Trusted Access** and required role assignments.
5. Storage account/container for backup artifacts where required by the feature.
6. Snapshot resource group or supported snapshot store.
7. Backup instance bound to the protected cluster/scope.

Separate backup administration from application administration. A namespace admin should not necessarily hold permission to delete Backup vaults or recovery points.

### Step 3: Define Protection Scope

Inventory:

- Namespaces to protect.
- Kubernetes objects: Deployments, StatefulSets, Services, ConfigMaps, CRDs/custom resources, and cluster-scoped resources as supported.
- Compatible PVCs/PVs and data sizes.
- External data requiring separate PaaS backups.
- Sensitive objects such as Secrets or admission configs.

Avoid overly narrow filters that accidentally skip critical PVCs or namespaces. Conversely, backing up every system namespace needlessly increases restore complexity and privilege scope.

### Step 4: Enable Policy and Create a Test Recovery Point

In the **Azure Portal**, open the Backup vault / AKS backup blade per available features and configure the protected scope, frequency, and retention. Wait for the backup job to succeed, then verify the **recovery point exists and belongs to the right cluster/namespace**.

**A successful backup job is only step one.** Test restoring into an isolated test namespace/cluster to prove manifests, volumes, and actual data recover cleanly.

### Step 5: Schedule Drills

Establish a restore drill schedule, assign owners, record acceptance evidence, and flag unprotected gaps. Run DR drills periodically and after major changes to the cluster, storage driver, database, or backup policy.

## 15. Azure CLI and Kubernetes Commands to Inspect State

Commands below are **read-only** against Azure/Kubernetes resources and suited for pre/post-backup checks. Ensure matching CLI/extension versions and read permissions.

### Inspect Cluster and Configuration

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az aks show \
  --resource-group "<AKS_RESOURCE_GROUP>" \
  --name "<AKS_CLUSTER_NAME>" \
  --query "{name:name,location:location,kubernetesVersion:kubernetesVersion,provisioningState:provisioningState}" \
  --output json
~~~

### Inspect Backup Vaults and Backup Instances

~~~bash
az dataprotection backup-vault list \
  --resource-group "<BACKUP_RESOURCE_GROUP>" \
  --output table

az dataprotection backup-instance list \
  --resource-group "<BACKUP_RESOURCE_GROUP>" \
  --vault-name "<BACKUP_VAULT_NAME>" \
  --output json
~~~

The **`az dataprotection`** command group may require specific Azure CLI/extension versions. If a command or flag is missing, check CLI docs and `--help` rather than assuming backups are unconfigured.

### Inspect Kubernetes Storage and Workloads

~~~bash
kubectl get namespaces
kubectl get deployments,statefulsets -A
kubectl get pvc -A
kubectl get pv
kubectl get storageclass
kubectl get volumesnapshot -A
~~~

Never treat **`kubectl get all`** as an exhaustive resource inventory: it **excludes** NetworkPolicies, PVCs, Secrets, CRDs, and many other object types.

### Inspect a Specific PVC and Workload

~~~bash
kubectl describe pvc -n shop-data orders-data
kubectl get statefulset -n shop-data
kubectl get pods -n shop-data -o wide
kubectl get events -n shop-data --sort-by=.lastTimestamp
~~~

Requires **`kubeconfig`** access to the target cluster. Credential commands like **`az aks get-credentials`** mutate your local kubeconfig, so do not treat them as completely zero-impact read commands; run only when authorized and verify your active context.

### Always Check Context

Before any restore or apply:

~~~bash
kubectl config current-context
kubectl cluster-info
~~~

This basic safety check prevents accidentally applying manifests to production while intending to restore into a lab cluster.

## 16. Building an Actionable Backup Policy

A policy should document:

| Attribute | Example Details to Record |
|---|---|
| Workload | `orders-api` / `orders-db` |
| Owner | Platform team and data owner |
| Backup scope | Namespaces, K8s resources, volumes, and off-cluster data |
| Schedule | Aligned with approved RPO, factoring in backup duration |
| Retention | Short/long-term tiers per business and regulatory needs |
| Recovery target | Original cluster, new cluster, alternate namespace, or alternate region if supported |
| Encryption | Backup data encryption, keys, and decryption RBAC |
| Isolation | Separation between workload operators and recovery-point deletion rights |
| Validation | Restore drills, checksums, business queries, health checks |
| Alerts | Backup failures, missing recovery points, unexpected retention changes |
| Budget | Storage, snapshots, vaults, transfers, and restore test costs |

### Two-Layer Backup Design Example

A system with an in-cluster database and Blob documents:

- **Kubernetes backup:** daily or per approved cadence for manifests and eligible PVs.
- **Database PITR:** transaction logs and base backups meeting an RPO tighter than snapshot intervals.
- **Blob Storage:** versioning, soft delete, or backup/retention tailored to document SLAs.
- **IaC/GitOps:** stored and tested cluster recreation capability.
- **DR drills:** scheduled full-service recovery tests.

Never copy fixed schedules from examples straight into production. Meeting a 15-minute RPO requires real 15-minute recovery capability; a 24-hour PV snapshot is plainly insufficient without transaction log / PITR protection.

## 17. Layered Application Recovery Workflow

A **restore runbook** starts by classifying the outage and picking the right recovery point.

### Phase A: Incident Assessment

1. Determine whether the outage involves lost Kubernetes resources, lost volumes, corrupted databases, or cluster/region loss.
2. Identify the **last known-good timestamp** and risk of corruption propagation.
3. Halt or throttle writes to affected systems when needed to avoid overwriting evidence or compounding corruption.
4. Select a verified backup/recovery point with valid provenance, active retention, and proven restorability.
5. Choose the restore target: isolated namespace, new cluster, or new database instance.

Never restore straight over production before confirming the backup predates ransomware or identifying exactly when database corruption began.

### Phase B: Prepare Target Infrastructure

1. Provision or confirm target subscription/resource group and AKS cluster via IaC.
2. Verify Kubernetes version/API compatibility, node pools, CSI drivers, ingress/egress, and StorageClasses.
3. Prepare VNets, subnets, routes, DNS, private endpoints, network policies, and load balancing.
4. Configure ACR image pull rights, Workload Identity, Key Vault, RBAC, and certificates.
5. Install required CRDs/operators **at matching supported versions** before restoring custom resources.

A common failure is restoring PVCs before the cluster has a matching StorageClass/CSI driver, or restoring CustomResources before their CRD/operator exists.

### Phase C: Restore Data

1. Verify the source recovery point, snapshot, or DB backup.
2. Restore PV/PVCs or databases into an isolated target, preserving original sources for forensics.
3. Verify volume mounts, filesystems, permissions, encryption keys, and consistency checks.
4. For databases, execute WAL replay/PITR or vendor restore steps.
5. Validate integrity, row counts, schemas, referential integrity, and exact recovered timestamp.

### Phase D: Restore Application Layer

1. Apply manifests in dependency order.
2. Verify Secret references and Workload Identity bindings.
3. Attach pods to restored volumes and PaaS dependencies.
4. Start workloads with proper readiness/liveness/startup probes.
5. Verify NetworkPolicies, DNS, and external endpoints.
6. Review GitOps reconciliation state before re-enabling auto-sync.

### Phase E: Acceptance and Traffic Cutover

1. Run read/write API and transaction tests against the recovered environment.
2. Compare state against the recovery point and measure any transaction loss relative to RPO.
3. Inspect logs, monitoring, and backlog capacity.
4. Shift traffic via DNS/gateway/load balancer per cutover plan.
5. Monitor post-cutover errors and keep a fallback plan ready where feasible.
6. Record actual recovery duration and lessons learned.

## 18. Recovery Order for an App with a StatefulSet

Consider an ordering system consisting of:

~~~text
AKS cluster
  |
  +-- orders-api Deployment
  +-- orders-db StatefulSet
  |     +-- PVC orders-data
  +-- orders-worker Deployment
  +-- ConfigMap / Secret references
  +-- Services / Ingress / NetworkPolicy
  |
  +-- Azure Key Vault
  +-- Azure Service Bus queue
  +-- Blob Storage
~~~

A sensible order:

1. Restore foundational infrastructure: cluster, node pools, CSI, namespaces, CRDs/operators.
2. Restore the database and volume in an environment isolated from public traffic.
3. Verify the database boots cleanly and schemas/records match expectations.
4. Restore Secrets/identities from trusted sources, never restoring compromised credentials.
5. Create Services/NetworkPolicies and verify API connectivity to the database.
6. Start queue workers only after guarding against duplicate job side effects and confirming DB stability.
7. Run end-to-end tests, then open ingress and cut over traffic.

### Why Not Start Workers First?

If workers immediately consume Service Bus messages against a database restored to an earlier timestamp, they may double-write records, reprocess messages, or trigger duplicate external side effects. You need a **reconciliation strategy** across the message broker, job ledger, and database.

Some messages may already be completed in the broker while the restored DB lacks their rows; conversely, messages may remain in the queue while external side effects already executed. AKS backup alone does not solve this distributed transaction gap.

## 19. Restoring to an Alternate Namespace or New Cluster

**In-place restore** and **restore to alternate location** serve different goals.

| Mode | When to Use | Risks |
|---|---|---|
| Restore original namespace | Recovering from localized accidental deletion | May overwrite live objects or clash with running controllers |
| Restore new namespace | Validating backups without touching production | Hostnames, Secrets, Service names, and PVC references need remapping |
| Restore new cluster (same region) | DR drill or cluster loss | Must rebuild infra, CSI, identities, DNS, and ACR integration |
| Restore alternate region | Full-region outage scenario | Requires region-accessible backups, networking, and data replicas |

Support for namespace remapping, resource filtering, volume restore, and cross-location recovery **depends on the backup tool and feature version**. Do not assume Azure Backup for AKS supports arbitrary cross-region or cross-subscription restores without checking the matrix.

### Handling Resource Name Collisions

A target test cluster may already have a Service `orders-db`, PVC `orders-data`, or matching CRDs. During restore, choose the tool's **skip/replace/map** policy carefully to avoid overwriting active data.

For PVCs, the safest pattern is restoring under a new name or isolated namespace and validating before ever touching volumes actively written by a StatefulSet.

## 20. Disaster Recovery for a Regional Outage

Losing an entire region differs from losing a single node pool. Clusters, VNets, private DNS resolvers, storage, databases, and backup storage can all be affected together.

~~~text
Primary region
  AKS + DB + Storage + Backup policy
            |
            | Tested compatible backup / replication
            v
Secondary region
  Network + AKS template + image access
  DB recovery target + data restore
  Secrets/identity + DNS + traffic failover
~~~

### Specific Requirements for Cross-Region Recovery

- Verify **backup tier, recovery point type, and cross-region restore support** for Azure Backup for AKS and volume storage.
- Check where snapshots and artifacts physically reside; primary-region snapshots may be unreachable during a regional outage.
- Maintain **dedicated data DR strategies** for PaaS databases, Blob Storage, and external systems.
- Ensure ACR images remain pullable in the target region even if the primary registry region is impaired; evaluate geo-replication where appropriate.
- Pre-verify quotas and AKS/node pool SKU capacity in the target region.
- Reconfigure Workload Identity federation, DNS, Key Vaults, private endpoints, certificates, and backend addresses.
- Plan DNS/traffic failover; never treat Azure Traffic Manager or Front Door as a data-restore tool.
- Measure RTO/RPO against a true region-loss scenario, not just same-region restores.

**Never claim same-region backups equal cross-region DR** without proving data can be accessed and restored in the secondary region.

## 21. How to Conduct a Restore Drill

A backup is only trustworthy once restored under conditions close to a real outage. Run scheduled **restore drills** and repeat after major architectural changes.

### Step 1: Select Test Data and Scenarios

Examples:

- Namespace **`orders-dr-test`**, containing zero real customer data.
- A PVC with sample files and recorded checksums.
- A test database containing an **`orders`** table and synthetic records.
- An isolated ingress unreachable by production users.

Pick two scenarios: **restoring a namespace/PVC** and **restoring onto a fresh cluster**. If cross-region DR is required, drill in the secondary region as well.

### Step 2: Record Baseline State

Capture evidence:

~~~text
Application release: v1.7.3 (illustrative)
Kubernetes version: per lab cluster
Namespace: orders-dr-test
PVC: orders-data-test
Database:
  order_count = 1250
  last_order_id = TEST-1250
Sample file checksum: SHA-256 recorded prior to backup
Backup recovery point: <RECOVERY_POINT_ID>
~~~

Never place connection strings, account keys, tokens, or personal data inside drill reports.

### Step 3: Create / Verify the Recovery Point

Verify backup jobs, recovery points, retention, and covered volumes/resources. Proceed to restore only after confirming the recovery point comes from the intended test dataset.

### Step 4: Restore Safely

Restore into an **isolated** namespace or cluster. Never take down production to run a lab drill. For test databases, restore to an authorized test instance—never overwrite user-facing data.

### Step 5: Verify Correctness

| Check | Pass Criterion |
|---|---|
| Resource restore | Deployments/StatefulSets/Services/PVCs exist in expected scope |
| PVC binding | PVC is `Bound` and mounts cleanly |
| File data | Sample files exist with matching SHA-256 checksums |
| Database | Valid schema, row counts, and constraints |
| Application health | Readiness passes and business queries succeed |
| Secrets/identity | Workers/APIs hold right permissions without using compromised old secrets |
| Network | DNS, NetworkPolicies, ingress/egress, and private endpoints work |
| RPO | Recovered data timestamp meets the target RPO |
| RTO | Total time from incident detection to usable service meets RTO |
| Monitoring | Logs, metrics, and alerts continue operating |

### Step 6: Capture Lessons Learned

Record elapsed time per step, errors, manual workarounds, undocumented dependencies, and remediation items. A failed restore drill is a **valuable finding**; never mark a drill successful merely because pods started.

## 22. Auditing Permissions and Protecting Backups from Deletion

### Principle of Least Privilege

Separate teams:

| Group | Permissions to Review |
|---|---|
| Platform team | Administer AKS and infrastructure within assigned scope |
| Application team | View workloads/deployments; cannot arbitrarily delete recovery points |
| Backup team | Manage backup policies/instances and execute approved restores |
| Security team | Govern protection requirements and alert on disabled/modified backups |
| Audit team | Read reports and evidence with zero write/delete permissions |

Design Azure RBAC, Kubernetes RBAC, managed identities, and Trusted Access consistently. **Never grant subscription-wide Owner just so an extension can take snapshots** when narrower permissions are supported.

### Ransomware and Compromised Credential Risks

An attacker with elevated privileges may attempt to:

- Delete or disable backup policies.
- Delete recovery points or underlying snapshot resources.
- Rotate/destroy encryption keys, delete Key Vaults, or render backups undecryptable.
- Corrupt primary data so subsequent backups capture poisoned state.
- Disable audit logs, break DNS/routes, or alter identities.

Controls to evaluate:

1. Separate backup deletion/modification rights from day-to-day application operations.
2. Protect vaults and recovery points with **soft delete, immutability, and multi-user authorization** where supported by vault type, data source, and region.
3. Keep recovery points/copies in an isolated failure domain per DR requirements.
4. Monitor Activity Logs and alert on any changes to protection settings.
5. Protect keys/identities needed for restore, and plan recovery if a tenant or credential is compromised.
6. Test restores using fallback operator identities/workstations under approved procedures.

**Never assume every Azure Backup anti-deletion feature is identically supported for AKS.** Verify exact policies and supported backup types.

## 23. Backing Up Private Clusters and Networking

Private AKS clusters, private endpoints for Azure Storage or vaults, Azure Firewalls, and custom DNS improve security yet make backups/restores dependent on network paths.

Verify:

- Is the backup extension deployed and running inside the cluster?
- Do agents/extensions have permissions and network routes to required backup services?
- Can the CSI driver create snapshots via the Azure control plane?
- Do storage accounts holding backup artifacts have matching firewalls, private endpoints, and DNS?
- Can the restore target reach container registries, Key Vaults, databases, and storage?
- Are NSGs, UDRs, or outbound firewalls blocking required endpoints?
- Do Workload Identity pods have valid trust configured after moving to a new cluster?

Never open unrestricted outbound Internet or flip Storage to **Allow all networks** just because a backup job failed. Isolate **DNS, TCP/443, RBAC, Trusted Access, quotas, CSI**, and compatibility errors properly.

### DNS After Restoring to a New Cluster

A workload calling Blob Storage or a database by standard hostname may still depend on private DNS zones, VNet links, or forwarders in the target region/VNet. A running container does not prove it can reach data endpoints.

## 24. Backup Monitoring and Alerting

Reliable operations monitor both **backups** and **restores**.

| Signal | Why It Matters |
|---|---|
| Backup job success/failure | Catch failing scheduled backups early |
| Last successful recovery point | Verify RPO remains satisfied |
| Recovery point age | Measure gap from latest valid backup to now |
| PV coverage | Detect newly created volumes lacking backup protection |
| Snapshot failures | Catch CSI/storage/quota/permission errors |
| Backup storage growth | Track capacity and spend |
| Restore drill success | Measure real-world recoverability |
| Restore duration | Compare against target RTO |
| Policy/vault changes | Detect unauthorized schedule or retention edits |
| Failed data validation | Catch backups that exist yet hold corrupted data |

### Alert Scenarios

- No successful backup within a window exceeding RPO.
- Backup jobs failing across consecutive runs.
- A new PVC created without matching backup coverage.
- Backup extension unhealthy after an AKS upgrade.
- Volume snapshots stuck before reaching **`readyToUse`**.
- Unauthorized retention edits or backup instance deletions.
- Latest restore drill missed RTO/RPO.

Azure Monitor, Azure Backup Center, diagnostic settings, and Activity Logs provide relevant signals per service. Never assume every business metric in the table above exists out of the box—some require custom dashboards or inventory checks.

## 25. Troubleshooting Common Failures

| Symptom | Possible Cause | Investigation Path |
|---|---|---|
| Backup succeeds yet database data is missing | Only manifests backed up, or snapshot lacked app consistency | Check backup scope, PVs, DB logs, and restore drill |
| Cannot back up PVC | Unsupported CSI driver/volume type or missing snapshot rights | Check StorageClass, PV, backup compatibility, job errors |
| Snapshot stuck Pending | Wrong `VolumeSnapshotClass`, CSI snapshot controller/driver error | Describe `VolumeSnapshot` and inspect CSI events |
| Backup extension not running | Image pull, DNS, RBAC, or version incompatibility | Check pods, events, identities, and feature docs |
| Backup job permission failure | Missing role assignments or Trusted Access | Check identities, resource scopes, and request IDs |
| Cannot restore to another cluster | Incompatible Kubernetes/CSI/region/backup tier | Check support matrix, target config, and recovery point |
| Restored PVC stays unbound | Wrong StorageClass, zone/volume affinity, quota, or invalid snapshot | Check PVC/PV events and storage provisioning |
| Pod runs yet app stays unready | ConfigMaps/Secrets, database, ingress, or mismatched image | Check logs, probes, network, and image digest |
| Database boots yet recent transactions missing | Actual RPO missed or PITR unconfigured | Check last recovery point and transaction logs |
| Secrets restored yet app gets 401/403 | Broken Workload Identity / Key Vault trust, or expired secrets | Check OIDC issuer, RBAC, and secret rotation |
| GitOps deletes newly restored resources | Missing from Git or reconciliation ran mid-restore | Check desired-state source and restore sequence |
| Cannot delete recovery points | Retention, soft delete, immutability, or lock policy | Verify permissions and protection locks; do not bypass |
| Sudden backup cost spike | Frequent snapshots, long retention, DR drills, or verbose logs | Check usage/cost by vault, storage, and workload |
| Restore succeeds yet user traffic fails | DNS, gateway, certificates, ingress, or NetworkPolicies | Test end-to-end and verify cutover routing |

### Layer-by-Layer Diagnosis

1. **Backup configuration:** does the job actually cover the target namespaces, resources, and PVs?
2. **Storage:** are volume type, snapshot status, size, zone, and quotas valid?
3. **Security:** are identities, roles, Trusted Access, and Key Vault permissions valid?
4. **Kubernetes:** are CRDs, StorageClasses, namespaces, and Deployments ready?
5. **Application:** are database schemas, logs, HTTP health, and business transactions valid?
6. **External services:** are Blob/SQL/Service Bus/DNS/registries reachable and healthy?
7. **DR objectives:** do recovery duration and recovered data timestamp meet RTO/RPO?

Never "fix" a Pending PVC by blindly changing `reclaimPolicy` or deleting the old PV: you could destroy still-recoverable data.

## 26. Backing Up and Restoring Queues, Events, and Background Jobs

For event-driven systems on AKS, state does not live solely in one database:

- Service Bus queues hold pending work.
- Blob Storage holds pipeline inputs and outputs.
- Job ledgers track processing state.
- Azure Functions/workers may re-run jobs post-restore.

### Problems a Single Snapshot Cannot Solve

Suppose Job J sent an invoice to a partner API and then marked itself `SUCCEEDED` in the DB. If the DB is restored to just before that commit, workers may re-send the invoice, causing duplicates. Conversely, if a queue message was completed while the DB lost its record, some work may never be replayed.

Solutions require:

1. Durable **idempotency keys** per business action.
2. Transaction/outbox/inbox patterns where appropriate.
3. Reconciliation across event sources, queues, ledgers, and outputs.
4. Starting workers only after DB recovery and reconciliation.
5. Controlled replay mechanisms rather than blind bulk replays.
6. Opening user traffic only after data reconciliation completes.

**A single database's RPO does not automatically equal the entire pipeline's RPO** when Blob Storage and queues follow separate protection mechanisms.

## 27. AKS Backup Costs

Cost components to budget:

- Storage capacity of Azure Disk snapshots or backend storage.
- Kubernetes/backup artifact storage and retention duration.
- Azure Backup vaults, backup instances, and recovery points per pricing terms.
- Backup storage tiers, replicas, or cross-region copies where supported.
- Compute (CPU/RAM) consumed by backup extensions/agents.
- Separate backup/PITR capacity for PaaS databases and Blob Storage.
- Network/egress/cross-region transfers, ACR, and supporting services.
- Azure Monitor / Log Analytics and log retention.
- Temporary AKS clusters/node pools spun up for restore drills.

### RPO vs Cost Trade-Offs

More frequent backup schedules increase snapshot counts, operations, and storage fees. Too infrequent a schedule fails your RPO. Never cut costs purely by deleting recovery points below business requirements.

Hypothetical example:

~~~text
Total protected capacity: 500 GiB
Snapshot schedule: every 4 hours
Retention: per approved policy
Data churn: application-dependent

Actual cost is NOT simply:
  500 GiB x 6 snapshots/day x days

Because incremental snapshots and backend storage meter changed blocks differently.
~~~

Check Azure pricing by region/tier/storage and track real spend via **Cost Management**. Tag workloads/owners, set budgets, and monitor backup storage growth.

## 28. Case Study: E-Commerce Application DR

An enterprise runs an ordering application on AKS:

- **`orders-api`** is a stateless Deployment.
- **`orders-worker`** processes Service Bus messages.
- **`orders-db`** is a PostgreSQL StatefulSet backed by an Azure Disk CSI PVC.
- PDF invoices live in Azure Blob Storage.
- Secrets live in Key Vault; workloads use Microsoft Entra Workload ID.
- Networking uses private AKS, Private DNS, and Azure Firewall.
- Business targets are **15-minute RPO** and **2-hour RTO**.
- Recovery is required for cluster loss, plus evaluation of full-region loss DR.

### Tasks

1. List every resource type that must be backed up or recreated.
2. Classify each item under GitOps/IaC, Azure Backup for AKS, database backup, and Blob backup.
3. Explain why a 24-hour Azure Disk snapshot fails a 15-minute RPO for PostgreSQL.
4. Propose a WAL/PITR mechanism or database architecture meeting the 15-minute RPO.
5. Outline steps to provision the target cluster, configure CSI/StorageClasses, and restore PVCs.
6. Specify recovery order for Key Vault/workload identity, DB, API, workers, and traffic.
7. Describe how to reconcile Service Bus messages after restoring the DB to an earlier point.
8. Explain why source-region-only snapshots are insufficient for regional DR.
9. Define data, health, RPO, and RTO checks for a drill.
10. Propose RBAC, anti-deletion protections, monitoring, and cost controls.

### Solution Guide

Separate at least three recovery streams:

- **Infrastructure + app:** IaC/GitOps, digest-pinned images, and reviewed configs.
- **PVC/PostgreSQL:** supported backup plus a DB-native/PITR strategy meeting the 15-minute RPO rather than relying solely on daily snapshots.
- **External data:** Blob/Service Bus/Key Vault restored or recreated via service-appropriate mechanisms and policies.

During DR, restore the cluster and foundational dependencies first; then restore the database, verify data, start the API, reconcile job ledgers/queues, and only then start workers and cut over traffic. **`Backup completed` never substitutes for `restore drill passed`.**

## 29. Production Checklist

| Category | Required Evidence |
|---|---|
| Objectives | Approved RPO/RTO per application and data tier |
| Scope | Inventory of namespaces, CRDs, PVCs/PVs, and off-cluster services |
| Compatibility | Verified AKS version, CSI driver, volume types, and Backup feature/tier support |
| Backup vault | Inspected instances, policies, retention, and recovery points |
| Permissions | Proper Trusted Access, Azure RBAC, Kubernetes RBAC, and identities |
| Data consistency | Application-consistent or PITR configured where business requires |
| GitOps/IaC | Cluster and manifests reproducible; images retained |
| Security | Encryption, keys, secrets, and separated backup deletion rights |
| Networking | Private DNS, routing, firewalls, ingress, and egress verified |
| DR region | Backups/data accessible and restorable in target DR region where supported |
| Restore | Tested into isolated namespace/cluster without overwriting production |
| Validation | Database/schema/checksum verification, app health, business transactions |
| Queues | Post-restore reconciliation, controlled replay, and idempotency |
| Monitoring | Alerts for backup jobs, recovery point age, snapshots, and policy edits |
| Cost | Budget covering vaults, snapshots, DBs, transfers, drills, with assigned owner |
| Documentation | Runbooks, owners, approvers, timings, and rollback procedures |

## 30. Self-Check Questions

1. Why does backing up Deployment YAML fail to restore data inside a PVC?
2. How do RPO and RTO differ? If RPO is 15 minutes, is a daily backup enough?
3. Why doesn't replication replace historical backups after accidental deletions?
4. Which AKS-related components are not necessarily included in a Kubernetes backup?
5. How does Azure Backup for AKS differ from backing up a VM via a Recovery Services vault?
6. Why must you check storage types and CSI drivers before claiming a PVC is protected?
7. How does a `VolumeSnapshot` differ from a managed backup with retention and DR capabilities?
8. Does `readyToUse=true` on a snapshot prove a database is application-consistent?
9. When are database-native backups and PITR more critical than volume snapshots?
10. Why shouldn't `kubectl get all` be used as a complete inventory of cluster objects?
11. Why might GitOps overwrite or delete newly restored resources?
12. When failing over to a new AKS cluster, what must you check for Workload Identity?
13. Why restore data into an isolated environment before cutting over traffic?
14. Why are losing a cluster/namespace and losing an entire region two distinct scenarios?
15. What determines whether a backup can be restored in a secondary region?
16. Why do you need a queue and job-ledger runbook after restoring a database?
17. Is a successful backup job enough proof that your RTO and RPO targets are met?
18. How do you verify checksums and business data integrity on a restore?
19. Which Backup vault/policy changes require security alerts?
20. How would you design a safe restore drill for a namespace containing a PVC?
21. Why shouldn't you delete a troubled PVC/PV before checking its reclaim policy?
22. Which costs are commonly overlooked when budgeting AKS DR?

## References

- Microsoft Learn — *Azure Kubernetes Service backup overview*: https://learn.microsoft.com/azure/backup/azure-kubernetes-service-backup-overview
- Microsoft Learn — *Back up AKS using Azure Backup*: https://learn.microsoft.com/azure/backup/azure-kubernetes-service-backup-configure
- Microsoft Learn — *Restore AKS using Azure Backup*: https://learn.microsoft.com/azure/backup/azure-kubernetes-service-restore
- Microsoft Learn — *Azure Backup documentation*: https://learn.microsoft.com/azure/backup/
- Microsoft Learn — *Persistent volumes in AKS*: https://learn.microsoft.com/azure/aks/concepts-storage
- Microsoft Learn — *Azure Disk CSI driver for AKS*: https://learn.microsoft.com/azure/aks/azure-disk-csi
- Kubernetes — *Volume Snapshots*: https://kubernetes.io/docs/concepts/storage/volume-snapshots/
- Kubernetes — *Persistent Volumes*: https://kubernetes.io/docs/concepts/storage/persistent-volumes/
- Microsoft Learn — *Workload identity for AKS*: https://learn.microsoft.com/azure/aks/workload-identity-overview
- Microsoft Learn — *AKS best practices for business continuity and disaster recovery*: https://learn.microsoft.com/azure/aks/operator-best-practices-multi-region
