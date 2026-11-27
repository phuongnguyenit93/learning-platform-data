# Backup for GKE and Recovering Stateful Applications

> **Chapter:** Advanced GKE and Operations  
> **Lesson:** Backup for GKE and Recovering Stateful Applications  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners progress from project governance, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, databases, release automation, reliability monitoring, and cost management. On GKE, a stateless Deployment can be recreated from Git, whereas **data written to PersistentVolumes, runtime state, and external dependencies** require a dedicated recovery workflow.

**Backup for GKE** is a managed service for backing up and restoring **Kubernetes workloads** and the data on **supported persistent disk volumes**. The hard part of stateful systems is not merely creating a backup: you must define **RPO/RTO**, ensure application-consistent data, pick safe restore policies, rebuild target infrastructure, and **rehearse recovery end to end**.

This lesson focuses on designing, configuring, rehearsing, and operating Backup for GKE. Project, cluster, namespace, and image names are placeholders. Backup/restore commands can incur charges or mutate real resources; run them only in an **approved sandbox**, and never use destructive restore options in production without a change plan and verified backup copies.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **Kubernetes manifest backups** from **volume data backups** and identify resources Backup for GKE does not cover.
2. Explain `BackupPlan`, `Backup`, `RestorePlan`, `Restore`, and the in-cluster agent.
3. Design backup scope by **cluster, namespace, or `ProtectedApplication`**, along with schedules, retention, and locations.
4. Choose appropriate strategies for a **Java StatefulSet using PVCs**, self-managed databases on GKE, and apps using Cloud SQL.
5. Distinguish **crash-consistent** from **application-consistent** snapshots, and know when hooks or database-native backups are required.
6. Configure **volume data restore** policies and resource conflict modes without overwriting live data in the wrong place.
7. Practice `gcloud beta container backup-restore`, `kubectl`, and restore validation in a test cluster.
8. Build runbooks, RPO/RTO drills, IAM controls, monitoring, security, and cost governance.

## 2. What Does Backup for GKE Protect?

Depending on scope and configuration, a backup can contain **two categories**:

| Category | Contents | Key point |
|---|---|---|
| **Configuration backup** | Kubernetes resource manifests captured from the API server, e.g., Deployments, StatefulSets, ConfigMaps, Services, PVCs, and supported resources | Restores workload definitions, **not** the underlying GKE cluster |
| **Volume backup** | Data copy of **PersistentVolumes** of supported types bound to selected PVCs | Must enable **include volume data**; a PVC manifest alone cannot restore disk contents |

Backup for GKE supports GKE **Standard** and **Autopilot** within documented service limits. Several items require separate protection:

| Not fully covered by Backup for GKE | Complementary solution |
|---|---|
| **Cluster infrastructure:** node pools, machine types, VPCs, subnets, routing, cluster flags, and capacity | Terraform/IaC, standardized cluster configs, and cluster-provisioning runbooks |
| **Container image bytes** | Retain images/digests in Artifact Registry with appropriate retention policies |
| **Cloud SQL, Cloud Storage, external load balancers, off-cluster services** | Native backups/PITR/versioning/DR per service with coordinated timestamps |
| **Filestore/NFS, NetApp, and non-Persistent-Disk volumes** under the default volume backup path | Product-specific backups; Filestore has dedicated hook integration guides |
| **State on `emptyDir` or ephemeral container filesystems** | Never place recoverable state on local ephemeral storage |
| **Secrets** when the plan excludes secrets | Secret Manager / GitOps source, key recovery workflows, and explicit `include-secrets` policy |

A backup marked **Succeeded** does not prove a restored Java app can reach Cloud SQL, pull images, read secrets, or meet SLOs.

### 2.1. Service Architecture

~~~mermaid
flowchart LR
  SRC["Source GKE<br/>namespace orders-stateful"]
  AG["Backup for GKE agent"]
  PLAN["BackupPlan<br/>scope + schedule + retention"]
  BACKUP["Backup<br/>manifests + PD volume data"]
  RESTORE["RestorePlan<br/>target + policies"]
  TARGET["Pre-existing target GKE"]
  VERIFY["Test Java app<br/>data + readiness"]
  SRC --> AG
  PLAN --> AG
  AG --> BACKUP
  BACKUP --> RESTORE
  RESTORE --> TARGET
  TARGET --> VERIFY
~~~

A **`BackupPlan`** defines source, scope, location, and schedule. A **`Backup`** is a specific point-in-time backup. A **`RestorePlan`** defines target cluster, restore scope, conflict handling, and volume policy. A **`Restore`** is one execution of that restore plan.

One `BackupPlan` produces many `Backups`; one `RestorePlan` can be reused across multiple drills. The target cluster must **already exist** with the Backup for GKE agent installed; creating an eligible plan can install the agent on the cluster.

## 3. Set RPO/RTO Before Configuring Schedules

- **RPO (Recovery Point Objective):** maximum acceptable data loss measured from an incident back to the last usable recovery point.
- **RTO (Recovery Time Objective):** maximum acceptable time after an incident to restore the service to healthy serving state.
- **Retention:** how long backups are kept; **not** the same as RPO.
- **Recovery consistency:** whether restored data remains consistent with transactions and external dependencies.

| Illustrative requirement | Suggested approach | Caveat |
|---|---|---|
| Test namespace where losing a day of data is acceptable | Daily backups, short retention | Saves cost; usually needs no separate HA |
| Java worker writing checkpoints to PVC; minimal progress loss | More frequent backups plus tested checkpoint recovery | Data written between backups may still be lost |
| Self-managed PostgreSQL on GKE requiring very low data loss | Backup for GKE **paired with** WAL archiving/PITR and DB replication | Volume snapshots alone rarely satisfy strict RPOs |
| Survive **single-node or single-zone** failure continuously | Multi-zone architecture, replicas/HA | Backups enable recovery; **they do not replace HA** |
| Recover from a full region outage | Store backups in an eligible DR region with target cluster and dependencies | Check data residency, storage access, egress, and IAM |

**A system's true RPO is measured by successful backups and actually recoverable data**, not a cron string. If backups run hourly yet the latest run failed, the actual data-loss window grows wider.

### 3.1. Crash-Consistent vs. Application-Consistent

Disk snapshots capture block state equivalent to a sudden power loss. Filesystems replay journals, yet applications or databases may still need crash recovery.

| State | Actual guarantee |
|---|---|
| **Crash-consistent** | Restores block state at snapshot time; app must recover as if after a crash |
| **Application-consistent** | Coordinates flush/quiesce/transaction boundaries before snapshot so app state is clean |
| **Point-in-time database recovery (PITR)** | Restores a DB to an exact timestamp via base backups + transaction logs; not automatic with PVC backups |

Backup for GKE provides **`ProtectedApplication`** and **execution hooks** to run pre/post actions around snapshots where supported. For example, a **pre-hook** pauses writes and flushes buffers to disk, and a **post-hook** resumes writes afterward. Never use `kill -9` or arbitrary database locks as "standard hooks"—hooks must be designed and tested by the app/database owners.

## 4. Stateful Java Workload Example

Suppose `orders-worker` processes queued orders and writes **non-skippable checkpoints** to `/var/lib/orders`. The Java image is built and stored in Artifact Registry with pull permissions configured. A single-replica StatefulSet uses a 20 GiB Persistent Disk PVC.

**Prerequisites:** the cluster has a `standard-rwo` StorageClass backed by the PD CSI driver, and the sample image actually runs and writes checkpoints into the mount directory.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-worker
  namespace: orders-stateful
spec:
  clusterIP: None
  selector:
    app: orders-worker
  ports:
  - name: http
    port: 8080
    targetPort: 8080
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: orders-worker
  namespace: orders-stateful
spec:
  serviceName: orders-worker
  replicas: 1
  selector:
    matchLabels:
      app: orders-worker
  template:
    metadata:
      labels:
        app: orders-worker
    spec:
      containers:
      - name: worker
        image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-worker:1.0.0
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: data
          mountPath: /var/lib/orders
        resources:
          requests:
            cpu: "250m"
            memory: "512Mi"
          limits:
            memory: "1Gi"
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: standard-rwo
      resources:
        requests:
          storage: 20Gi
~~~

Create namespace `orders-stateful` first. The StatefulSet creates a PVC typically named `data-orders-worker-0`. Verify:

~~~bash
kubectl get statefulset,pods,pvc -n orders-stateful
kubectl get pv
kubectl describe pvc data-orders-worker-0 -n orders-stateful
kubectl get storageclass
~~~

Confirm the PVC is `Bound` to a PV with the right driver and disk. If the image doesn't exist, the Pod enters `ImagePullBackOff`; if zone capacity or the StorageClass is missing, the PVC stays Pending. **Never place real production data in a lab.**

**A single replica is not HA.** If the Pod or zone fails, restarting onto the volume may stall waiting for disk detachment/reattachment and data replay. For stateless Java services, avoid storing order state on PVCs—keep state in Cloud SQL or Cloud Storage so Pods remain ephemeral.

## 5. Designing a BackupPlan: Scope, Schedule, and Location

### 5.1. Choosing Scope

| Scope | When suitable | Risk |
|---|---|---|
| **All namespaces** | Broad protection across most cluster resources | Heavy; may capture ephemeral workloads needlessly |
| **Selected namespaces** | Workloads cleanly grouped by namespace | Can miss dependent resources in another namespace |
| **`ProtectedApplications`** | Grouping app resources with consistent hooks/quiesce logic | Must define resource groups and hooks accurately |
| **Selected objects at restore** | Narrow targeted recovery where supported | Can miss CRDs, RBAC, or StorageClass dependencies |

Backing up **Kubernetes Secrets** is a separate toggle. When enabled, backups hold sensitive credentials—audit encryption, IAM, retention, and who can read or restore backups. When disabled, the target cluster must have an **independent secret-recreation mechanism** (e.g., Secret Manager + external secrets sync).

### 5.2. Schedule and Retention

- **Smart scheduling:** specify a `target RPO`, and the service triggers backups automatically within constraints; do not combine with a `cron schedule` in the same plan.
- **Cron scheduling:** fixed backup times; monitor actual completion status, not just whether the schedule exists.
- **Retention:** how long backups are retained, aligned with recovery needs and compliance policies.
- **Delete lock:** prevents early deletion during a minimum period; enable/lock retention only after evaluating cost and operational impact.
- **Backup location:** a **regional** resource that can differ from the source cluster's region where supported; factor in network transfer charges and data residency rules.

One cluster can attach to multiple `BackupPlan`s: frequent backups for critical apps, lighter schedules for test workloads, or multi-region backups for DR.

## 6. Hands-On: Creating and Inspecting a Backup

**Note:** the commands below mutate Google Cloud resources—run only in an authorized sandbox with the **Backup for GKE API**, IAM permissions, a valid cluster, and billing enabled. Replace placeholders before running. Examples use `asia-southeast1` and regional GKE cluster `CLUSTER_NAME`; confirm regional service support.

### 6.1. Pre-Creation Checks

~~~bash
gcloud auth list
gcloud config get-value project

gcloud container clusters describe CLUSTER_NAME \
  --project=PROJECT_ID \
  --location=asia-southeast1

kubectl get ns orders-stateful
kubectl get pvc -n orders-stateful
~~~

The operator managing plans typically needs `roles/gkebackup.backupAdmin` plus appropriate GKE access. Never grant `roles/owner` just to bypass permission errors.

### 6.2. Create a BackupPlan for One Namespace

~~~bash
gcloud beta container backup-restore backup-plans create orders-daily \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --cluster=projects/PROJECT_ID/locations/asia-southeast1/clusters/CLUSTER_NAME \
  --selected-namespaces=orders-stateful \
  --include-volume-data \
  --cron-schedule="0 2 * * *" \
  --backup-retain-days=14
~~~

This plan protects namespace `orders-stateful`, **includes volume data**, and retains backups for 14 days. The cron expression is illustrative; check timezone interpretation in official docs and align with system requirements. If the app depends on manually created Secrets that cannot be regenerated on the target, evaluate `--include-secrets` alongside strict sensitive-data governance.

### 6.3. Trigger a Manual Backup and Inspect It

~~~bash
gcloud beta container backup-restore backups create orders-before-upgrade \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily \
  --wait-for-completion

gcloud beta container backup-restore backups describe orders-before-upgrade \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily
~~~

`--wait-for-completion` waits for the API operation to finish, yet you must still **inspect status, errors, and volume backups**; never assume command exit 0 means every workload was backed up.

~~~bash
gcloud beta container backup-restore backups list \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily

gcloud beta container backup-restore volume-backups list \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=orders-daily \
  --backup=orders-before-upgrade
~~~

Inspect **backup status, timestamp, resource index, protected volumes, and any warnings/errors**. If expected resources or volume backups are missing, **do not move on to restore drills or claim RPO compliance** until the gap is resolved.

## 7. Designing a Safe RestorePlan

A `RestorePlan` answers three questions: **where to restore**, **which resources**, and **what to do if resources or volumes already exist**. Picking the wrong options here is the fastest way to overwrite or destroy live data.

### 7.1. Volume Data Restoration Policy

| Volume policy | Meaning | When to use |
|---|---|---|
| `restore-volume-data-from-backup` | Provisions new PVs from supported volume backups | Drills on a **new** target cluster to verify backed-up data |
| `reuse-volume-handle-from-backup` | Rebinds the original underlying volume handle | Only when the original disk definitely exists and reuse is safe |
| `no-volume-data-restoration` | Restores PVC config only; volumes start empty or bind pre-existing PVs | Stateless workloads, unbacked volumes, or externally managed data |

**Do not confuse these:** restoring a PVC manifest does not restore disk data. Choosing "no volume data restoration"—or restoring a backup without volume data—boots the StatefulSet against an empty disk.

### 7.2. Resource Conflict Policy

| Conflict scenario | Option | Risk |
|---|---|---|
| **Namespace/protected app already exists** | `fail-on-conflict` | Safe for drills: aborts instead of overwriting |
| **Merging** | `merge-skip-on-conflict` | Keeps existing resources; may not accomplish a rollback |
| **Replace volume data** | `merge-replace-volume-on-conflict` | Can affect old PVs depending on reclaim policy |
| **Replace resources and volumes** | `merge-replace-on-conflict` | Can overwrite or delete live resources and data |
| **Roll back namespace/app group** | `delete-and-restore` | **Destroys** resources in scope before restoring from backup |
| **Colliding cluster-scoped resources** | Keep existing or replace per policy | Replacing a **CRD** can cascade-delete all Custom Resources of that kind |

Until impact is fully understood, **use a fresh sandbox cluster, a non-existent namespace, and `fail-on-conflict`**. On clusters managed by GitOps or operators, distinguish **restoring data** from **controllers immediately reconciling resources back**.

## 8. Hands-On: Restoring into a Separate Test Cluster

Assume a **target cluster** `CLUSTER_RESTORE` already exists in the same region with a compatible Kubernetes version, node capacity, networking, IAM, storage driver, and image-pull permissions. **Never** run test restores into a live production namespace actively accepting writes.

### 8.1. Create a Non-Overwriting RestorePlan

~~~bash
gcloud beta container backup-restore restore-plans create orders-rehearsal \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --backup-plan=projects/PROJECT_ID/locations/asia-southeast1/backupPlans/orders-daily \
  --cluster=projects/PROJECT_ID/locations/asia-southeast1/clusters/CLUSTER_RESTORE \
  --selected-namespaces=orders-stateful \
  --namespaced-resource-restore-mode=fail-on-conflict \
  --cluster-resource-scope-no-group-kinds \
  --volume-data-restore-policy=restore-volume-data-from-backup
~~~

This plan restores only the selected namespace, skips cluster-scoped resources, and **fails if the namespace already exists**. While safer for drills, the app may still fail to start if **StorageClasses, CRDs, RBAC, or operators** do not yet exist on the target cluster. Those prerequisites must be provisioned via IaC or a separate step.

### 8.2. Execute the Restore

~~~bash
gcloud beta container backup-restore restores create orders-test-restore \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --restore-plan=orders-rehearsal \
  --backup=projects/PROJECT_ID/locations/asia-southeast1/backupPlans/orders-daily/backups/orders-before-upgrade \
  --wait-for-completion

gcloud beta container backup-restore restores describe orders-test-restore \
  --project=PROJECT_ID \
  --location=asia-southeast1 \
  --restore-plan=orders-rehearsal
~~~

Even when the `Restore` resource reports completion, Kubernetes still has to **reconcile and boot the workload**, so never treat the Restore API status as your sole acceptance criterion.

### 8.3. Verify the Restored Cluster

Switch to the **exact test cluster** before running `kubectl`:

~~~bash
gcloud container clusters get-credentials CLUSTER_RESTORE \
  --project=PROJECT_ID \
  --location=asia-southeast1

kubectl config current-context
kubectl get ns orders-stateful
kubectl get statefulset,pods,pvc -n orders-stateful
kubectl get events -n orders-stateful --sort-by=.lastTimestamp
kubectl describe pvc data-orders-worker-0 -n orders-stateful
~~~

**Mandatory functional tests:** confirm the Java application sees checkpoint data from the backup, reads known test records, handles job replay idempotently, reaches required dependencies, maintains steady readiness, and logs no errors. For databases, verify WAL/crash recovery and data integrity using database-native tools.

## 9. Stateful Application Recovery Runbook

~~~mermaid
flowchart TD
    Incident["Incident detected / restore requested"]
    Assess["Classify failure + blast radius + RPO/RTO"]
    Pick["Select successful backup<br/>verify resource index & volumes"]
    Fence["Prevent split-brain writes<br/>decide maintenance"]
    Target["Provision/verify target cluster<br/>IAM, network, images, StorageClass"]
    Restore["Run safe RestorePlan"]
    Validate["Validate PVs, Pods, DB recovery<br/>Java data + health + SLOs"]
    Cut["Shift traffic once verified"]
    Monitor["Monitor + log evidence + review"]
    Incident --> Assess --> Pick --> Fence --> Target --> Restore --> Validate --> Cut --> Monitor
~~~

**Execution sequence:**

1. Confirm the failure: bad rollout, deleted files, cluster loss, or regional outage? Define **scope and recovery point**.
2. Freeze writes or enforce **fencing**: prevent both the old primary and the restored workload from writing concurrently to external systems (Cloud SQL, queues, APIs).
3. Select a backup verified for **success, resource index, and volume data**—do not blindly pick the latest name.
4. Provision or verify the target cluster: compatible Kubernetes version, StorageClass/CSI, CRDs/Operators, service accounts, Workload Identity Federation for GKE, networking, and secrets.
5. Pick a `RestorePlan` matching the goal: **empty cluster** vs. **data-only/rollback**. Use destructive modes only after reviewing PV reclaim policy impact.
6. Monitor the Restore and volume restores; verify Pods, Bound PVCs, image pulls, container logs, and health checks.
7. Validate **data end-to-end**: record counts, checkpoints, job state, transactions, and permissions.
8. Only after SLOs and data integrity pass, shift traffic/DNS/load balancers per runbook.
9. Record **actual RPO**, **actual RTO**, evidence, and lessons learned; prepare failback if needed.

**Never promote a restored cluster to production just because a Pod turns `Running`.** An app can run cleanly while reading **stale data** or still pointing at the live production database while its PVC volume was rolled back.

## 10. ProtectedApplication, Hooks, and Consistency

For stateful setups, classify workloads into three buckets:

| Workload | Sensible protection approach |
|---|---|
| **Stateless** Java API with state in Cloud SQL/Storage | Back up manifests if needed; **separate DB/object backups** |
| Java worker writing checkpoints or embedded DB to PD PVC | Backup for GKE with **volume data**, quiesce/flush via hooks if needed, restore tests |
| Self-managed PostgreSQL/MySQL on GKE | Backup for GKE + DB-native backups/WAL/PITR or operator backups; test crash/app consistency |

**`ProtectedApplication`** groups resources belonging to an app and attaches execution hooks where supported. Reference pattern:

~~~text
Before snapshot:
  1. Pause incoming write requests / checkpoint updates
  2. Flush data to disk and hold consistent state
During snapshot:
  3. Backup for GKE captures supported volume data
After snapshot step:
  4. Release quiesce state; app resumes normal writes
On restore:
  5. Mount new volume, replay journal/WAL, verify integrity
~~~

Never reuse identical pre/post hooks blindly across databases: MySQL, PostgreSQL, Cassandra, Redis, and Java embedded stores have very different semantics. Hooks can also **time out** or fail, breaking backup guarantees—monitor hook outcomes explicitly.

**If your app uses Cloud SQL**, Backup for GKE **does not snapshot Cloud SQL**. To achieve consistent recovery across manifests, PVCs, and Cloud SQL, design a **coordinated backup/recovery workflow** and test it in staging—never assume they capture the exact same instant automatically.

## 11. Restoring Across Clusters, Projects, and Regions

Restoring from one GKE cluster to another is supported within service constraints. Verify:

- **Target cluster already exists** with the Backup for GKE agent enabled/installed.
- **Version compatibility:** current documentation allows target Kubernetes minor versions from the source backup's version up to **three minor versions newer**, inclusive. Re-verify current rules when upgrading.
- **Projects:** cross-project backup/restore relies on explicit IAM and restore channels; never assume any project can restore another project's backups automatically.
- **Regions:** `BackupPlan` location determines where backups reside. Using a different region from source or target clusters incurs cross-region transfer fees and residency checks.
- **Storage:** Disk/StorageClass, zone topology, reclaim policies, PV CSI capabilities, and quotas on the target cluster.
- **Dependencies:** load balancers, DNS, Artifact Registry images, secrets, Cloud SQL, IAM, and networking must exist or be recreated accurately.

### 11.1. Namespace Renaming and Transformation Rules

Backup for GKE supports **transformation rules** to rewrite selected Kubernetes fields during restore, such as namespaces/references or StorageClasses where supported. Use these carefully for migrations or drills, checking all references:

- `ServiceAccount`, `RoleBinding`, and ConfigMap/Secret namespaces.
- PVC and StorageClass compatibility.
- Database endpoints, project IDs, regions, and workload identities.
- DNS/ingress hosts, TLS certificates, and callback URLs.

**Never apply blind search-and-replace on namespaces or StorageClasses** across manifests—that can break security boundaries or attach the wrong dataset.

## 12. IAM, Security, and Backup Deletion Protection

### 12.1. Separate Backup Permissions from Restore Permissions

| Task | Reference role | Rationale |
|---|---|---|
| Create/manage `BackupPlan` and backups | `roles/gkebackup.backupAdmin` | Does not automatically grant destructive restore rights |
| Create/manage `RestorePlan` and restores | `roles/gkebackup.restoreAdmin` | Separates approved DR execution |
| Full Backup for GKE admin | `roles/gkebackup.admin` | Restrict strictly to overall platform owners |

For cross-project/cluster setups, additional permissions cover GKE, service agents, networking, encryption, and read/write APIs; the roles above are only one slice. Never grant `roles/owner` to clear `PERMISSION_DENIED`.

### 12.2. Backups Are Sensitive Data Too

- Carefully evaluate **`include-secrets`**; backups holding Secrets require tight IAM and retention.
- Use **CMEK** on `BackupPlan` where required and supported by service/location; protect keys and decryption access for DR.
- Enable audit logs, restrict who can delete or restore backups, and review org policies.
- Consider **backup deletion locks and retention locks** to guard against accidental or malicious deletion; confirm cost and operational lock-in before enabling.
- Retain IaC, container images, and external DB backups long enough for **full recovery**, not just PVC snapshots.

**Backups stored in the same project and region as production share blast radius from destructive ops or compromised IAM.** When your threat model demands isolation, evaluate **cross-project/multi-region backups** with separate IAM boundaries where supported.

## 13. Monitoring and Troubleshooting

### 13.1. Operational Metrics

| What to watch | Action if abnormal |
|---|---|
| Last successful backup | Alert if elapsed time exceeds target RPO |
| Backup / volume backup status | Identify missing PVCs/resources or agent/CSI failures |
| Agent / cluster reachability | Inspect APIs, in-cluster agent, IAM, and networking |
| Restore status and volume restores | Check PVs/PVCs, StorageClasses, quotas, and API errors |
| App recovery | Readiness, logs, checkpoint/DB integrity, job replay |
| Retention / deletion locks | Ensure backups don't expire before rollback windows |
| Cost | Track backup storage, volume snapshots, cross-region transfer, and restores |

Monitor via **GKE → Backup for GKE** in Cloud Console, Cloud Monitoring/Logging, and `gcloud`; trigger alerts on real completion telemetry rather than assuming an active schedule succeeded.

### 13.2. Common Errors

| Symptom | Possible cause | How to diagnose |
|---|---|---|
| Backup lacks PVC data | Forgot `--include-volume-data` or unsupported volume type | Inspect `BackupPlan`, `volume-backups list`, CSI driver |
| Backup fails on hook | Bad/timed-out quiesce command or missing permissions | Inspect `ProtectedApplication`/hooks and logs |
| Cannot restore to target | Missing target cluster/agent or incompatible K8s version | Check cluster, add-on, and version skew rules |
| `fail-on-conflict` halts restore | Namespace/resources already exist | Use an empty test cluster instead of flipping to destructive modes blindly |
| Restored PVC stays `Pending` | Missing StorageClass/driver, zone topology, capacity, or quota | `kubectl describe pvc` and events |
| Pod hits `ImagePullBackOff` | Backups do not store container image bytes | Check Artifact Registry, node identity, and digest |
| App runs with empty data | Missing volume backup or `no-volume-data-restoration` selected | Verify volume restore policy, PVs, and mount paths |
| Restored Java app hits wrong Cloud SQL | Restored old config pointing at production DB | Check Secrets/configs, VPC, IAM, and DB endpoints |
| Restore overwrote/deleted PV/data | Used merge-replace / `delete-and-restore` + PV reclaim policy | Freeze changes; inspect intact backups and recovery runbooks |
| Cannot delete backup | Deletion lock or retention lock active | Check policy and expiration; never try to bypass locks |
| Unexpected cost spike | Too-frequent schedules, long retention, multi-region, large volumes | Billing breakdown and plan inventory |

**Investigation order:** verify backup record → resource/volume index → restore policy → target cluster → PVC/Pod events → application data. Never "fix" a restore by deleting a running production namespace or original volumes.

## 14. Costs and Boundaries with HA

**Backup ≠ High Availability.** Backups recover from bugs, accidental deletion, or bad deployments; HA keeps services online during expected infrastructure faults. Critical systems typically need both.

| Cost / resource | Cost drivers |
|---|---|
| Backup for GKE | Backup management/storage SKUs and protected resource volume |
| Volume snapshots | Data size and associated snapshot storage |
| Cross-region backups | Cross-region data transfer and destination storage |
| Rehearsal / DR cluster | Nodes, control plane, disks, load balancers, IPs |
| Security / logging | Cloud KMS/CMEK, logs, retention |
| Operational effort | Rehearsal time, reviews, consistency validation, and runbooks |

Never assume **14-day retention = always 14 backups**; actual count depends on schedule frequency and completed runs. Never estimate backup storage while forgetting **target cluster and data transfer fees**. Check Cloud Billing and the Google Cloud Pricing Calculator before rolling out policies at scale.

## 15. Case Study: Recovering Orders Worker After a Bad Release

**Hypothetical scenario:** a retail team runs `orders-worker` (Java StatefulSet) writing checkpoints to a PD PVC. CI ships a new image; a logic bug advances the checkpoint too far, skipping incomplete jobs. A sibling service persists transactions in Cloud SQL.

**Goal:** restore the backed-up checkpoint without duplicate order processing and without touching live production Cloud SQL during rehearsal.

**Recommended workflow:**

1. **Stop new consumers** and record current offsets/checkpoints; identify jobs whose side effects already succeeded.
2. Inspect the most recent successful `Backup` and verify its **`VolumeBackup`** actually holds the PVC data.
3. Provision a separate GKE restore cluster, isolated via networking/IAM so it cannot write to production Cloud SQL or queues.
4. Run restore with `fail-on-conflict` and `restore-volume-data-from-backup`, targeting only namespace `orders-stateful`.
5. Validate the checkpoint on the restored PVC against audit/job tables to separate **unprocessed** from **already processed** jobs.
6. Recover using **idempotent replay/deduplication** and roll back the app image to a compatible version.
7. Once verified, cut over endpoints/traffic or reload state inside an approved change window—never allow two workers to write concurrently.
8. Measure actual data loss against RPO and recovery duration against RTO; update the runbook.

**Lesson:** volume backups restore checkpoint files, yet they never "undo" transactions already committed in Cloud SQL, Pub/Sub, or payment gateways. Final correctness depends on **application transaction design and idempotency**.

## 16. Exercises and Self-Assessment Questions

### Exercise 1 — Backup Scope

An application includes a Java Deployment, ConfigMap, Secret, PD PVC, and Cloud SQL PostgreSQL. Its `BackupPlan` selects only the namespace and **omits** `include-volume-data` and `include-secrets`.

**Question:** what is inside the backup? What requires separate protection?

**Hint:** manifests (minus Secrets) are backed up, but PVC data and Secrets are excluded; Cloud SQL is out of scope.

### Exercise 2 — RPO/RTO

Backups run daily with 30-day retention. Product requires a 15-minute RPO and 30-minute RTO.

**Question:** is the current plan sufficient? What else is needed?

**Hint:** long retention does not shorten RPO; you need higher-frequency backups/CDC/PITR/app replication and rehearsed recovery times.

### Exercise 3 — StorageClass and PV

Restore reports completion, yet `data-orders-worker-0` sits `Pending`. The target cluster lacks StorageClass `standard-rwo`.

**Question:** why isn't Restore API success enough? Which resources must be verified or provisioned?

**Hint:** CSI driver/StorageClass, quotas, zone topology, PV/PVC events, and Pod lifecycle.

### Exercise 4 — Conflict Mode

An operator wants to rehearse on a cluster where namespace `orders-stateful` already holds recent test data, and picks `delete-and-restore` to "move fast."

**Question:** what is the risk? Which policy is safer for a first rehearsal?

**Hint:** it can delete existing resources/PVs depending on reclaim policy; use an empty target and `fail-on-conflict`.

### Exercise 5 — Crash Consistency

PostgreSQL on a PVC is backed up while serving live transactions, with no quiesce hooks or WAL archiving.

**Question:** does that snapshot guarantee clean recovery of every transaction?

**Hint:** it provides at best volume-level crash consistency; you need PostgreSQL-native recovery, WAL/PITR, hooks, and restore tests.

### Exercise 6 — Cross-Region DR

Both application replicas and backups sit in Region A. The goal is surviving a full Region A outage.

**Question:** what additional requirements apply to backup location, target cluster, container images, Cloud SQL, and IAM?

**Hint:** store backups in an independent region, prepare DR infra and off-GKE backups, plus target-region networking, KMS keys, and capacity.

### Exercise 7 — Operators and GitOps

A namespace is managed by Flux/Argo CD plus a database operator. A `RestorePlan` uses `merge-replace` on that same namespace.

**Question:** what can happen right after restore?

**Hint:** controllers immediately reconcile manifests back; handle CRD/CR conflicts and data volumes separately, coordinating GitOps/operator pause and resume.

### Exercise 8 — Proving Backups Work

A backup shows `Succeeded`, so the team declares DR complete.

**Question:** propose a verification checklist of at least five steps proving RPO/RTO compliance.

**Hint:** test target cluster provisioning, PVC mounts, app/data integrity, external dependencies, idempotent replay, and elapsed recovery time.

## 17. Production Checklist

- [ ] Defined **owners, RPO/RTO, data classification**, and explicit failure scenarios.
- [ ] Inventoried Kubernetes manifests, PVCs/PDs, secrets, images, Cloud SQL/Storage, and cluster infrastructure.
- [ ] `BackupPlan` selects exact namespaces/apps, enables **`include-volume-data`** where needed, and sets an intentional Secrets policy.
- [ ] Schedule and retention align with RPO and alert on **last successful backup**.
- [ ] Databases have application-consistency / DB-native backup solutions and tested replay procedures.
- [ ] DR cluster can be rebuilt via IaC with sufficient capacity, IAM, networking, StorageClasses, and artifacts.
- [ ] `RestorePlan` scope, **conflict policy**, and **volume policy** have been peer-reviewed.
- [ ] Rehearsed restore onto an isolated target, validating Bound PVCs, Pod health, data integrity, and external side effects.
- [ ] Cross-project/cross-region access, KMS keys, Secrets, and image pulls verified for DR.
- [ ] Separated backup, restore, and delete permissions; configured retention/deletion locks per threat model.
- [ ] Dashboards and alerts cover backup failures, missing volume backups, RPO breaches, and costs.
- [ ] Recorded **measured** RPO/RTO after drills and updated runbooks.

## 18. Official Documentation

Check the latest GKE versions, feature stages, `gcloud beta` syntax, and limits when deploying for real:

- [Backup for GKE overview](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Plan a set of backups](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/backup-plan)
- [Back up your workloads](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/backup)
- [Plan a set of restores](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore-plan)
- [Restore a backup](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore)
- [Define volume data restore behavior](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/volume-data-restore-policy)
- [Handle resource conflicts during restore](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/resource-conflict)
- [ProtectedApplications and execution hooks](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/protected-application)
- [Backup for GKE locations](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/about-locations)
- [Kubernetes StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [GKE Backup pricing](https://cloud.google.com/kubernetes-engine/pricing)

**Key takeaway:** **Backup for GKE protects Kubernetes configurations and supported Persistent Disk data—not entire off-cluster infrastructure or managed services.** To recover stateful Java applications reliably, you need **volume backups, appropriate consistency, non-destructive `RestorePlan` settings, a prepared target cluster, and end-to-end testing**. Only after measuring real RPO/RTO and verifying restored data and side effects can an organization trust its DR plan.
