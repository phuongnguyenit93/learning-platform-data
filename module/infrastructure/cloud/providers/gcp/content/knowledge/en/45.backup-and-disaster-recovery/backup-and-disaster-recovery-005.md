# Cross-Project Backup Strategy and Separation of Duties

Suppose a Java/Spring Boot application runs on GKE and Cloud SQL in a production project. A deployment account is compromised, and the attacker deletes the database, alters the backup schedule, and attempts to delete the backups too. If the entire workload, backups, and admin permissions live in the same project with broad privileges, a daily snapshot schedule is not enough to guarantee system recovery.

**Cross-project backup** is one way to establish an administrative boundary: the application runs in a source project, backups and protection policies are managed in a different project, and recovery is drilled in an independent target project. **Separation of duties** ensures someone authorized to deploy the app cannot by default alter retention policies, delete backups, manage encryption keys, or self-approve restoring sensitive data.

In the **Backup and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_GCP** module, this lesson connects projects, IAM, VPC, Compute Engine, GKE, Cloud Run, database services, Cloud Storage, encryption, automation, observability, and cost control. The goal is to design a verifiable recovery path, not merely generate backup files that have never been test-restored.

## Learning objectives

After this lesson, you will be able to:

- Distinguish backups, snapshots, replicas, archives, and retention-based deletion protection.
- Separate source projects, backup projects, and restore projects; define IAM and trust boundaries.
- Choose Backup and DR backup vaults, Backup for GKE, Cloud SQL exports, Cloud Storage, or Compute Engine snapshots based on actual product support.
- Design service agents and write/read/restore permissions following least privilege.
- Use enforced retention, Bucket Lock, object versioning, and CMEK without losing the ability to restore.
- Measure RPO/RTO, protect data against ransomware, and execute reconciled restore drills.

## 1. First: backups differ from replicas, snapshots, and archives

| Mechanism | Purpose | Limits to remember |
|---|---|---|
| High availability replica | Rapidly switch service on instance/zone failure | Can replicate accidental deletes or maliciously encrypted data |
| Cross-region read replica | DR, off-region reads, faster data availability | Async replication can lag; not an independent backup |
| Disk snapshot | Captures disk state at a point in time | Does not automatically guarantee DB transaction consistency or project isolation |
| Database-managed backup/PITR | Recovers database to a supported timestamp | Retention and permissions are often tied to the DB control plane; verify restore to an independent environment |
| Backup vault / independent copy | Creates policy-driven recovery points, decoupling data lifecycle | Must check supported workload types, access restrictions, and restore paths |
| Export to Cloud Storage | Creates a portable copy across projects or systems | May omit WAL/binlog, permissions, out-of-scope schemas, or PITR |
| Long-term archive | Meets legal retention and auditing mandates | Reads/restores can be slow; operational fees and retention constraints apply |

A good backup must **survive failures or compromised admin privileges on the source system**, carry metadata to locate the exact point in time, maintain sufficient consistency to restore, and remain accessible with the required permissions and encryption keys when disaster strikes.

### The 3-2-1-1-0 rule in cloud practice

A useful guideline is to keep multiple copies of data, with at least one in a separate failure domain, one **immutable or offline/air-gapped within solution capabilities**, and a target of **zero undetected errors in restore testing**. Never apply copy counts mechanically: two backups in the same project under the same identity may still share the same blast radius. Evaluate independence across projects, IAM, organization, KMS keys, locations, service agents, and networking.

## 2. Start from RPO, RTO, and data classification

Before creating a backup project, identify **what data exists**, **who owns it**, **how far back recovery points can be**, and **how quickly the application must return**.

| Data group | Illustrative examples | Reference RPO | Reference RTO | Backup direction |
|---|---|---|---|---|
| Transactional | Orders, payments, ledgers | 5–15 minutes or stricter | Under a few hours | PITR/periodic backups, DR replicas, and tested restores |
| Cluster config | Kubernetes Deployments, ConfigMaps, policies | Release cadence | Under a few hours | GitOps/IaC alongside Backup for GKE where needed |
| Volume data | PVCs, file shares, media | Change frequency | Depends on size | Backup for GKE / Backup and DR / object copies |
| Logs/audit | Cloud Logging exports, operational history | Compliance mandate | Investigation needs | Sink to storage project with dedicated retention and permissions |
| Secrets, keys, and identities | Secret Manager, KMS keys, IAM policies | Tied to app RTO/RPO | Must be ready before restore | Dedicated policies for identity, key, and config recovery |

Numbers above are **planning examples**, not Google Cloud SLAs. For continuously written apps, a daily backup schedule cannot meet a five-minute RPO. If the business requires a tight RPO, combine PITR, log shipping, CDC, or controlled replication while keeping independent backups against logical errors.

### Recovery point vs. recovery readiness

A backup finishing at 02:00 does not prove recovery can finish in 30 minutes. Time is needed to provision the target project, quotas, instances, networks, firewalls, IAM, KMS, switch DNS, run DB migrations, pull images, and pass business tests. Many systems have a good RPO yet a **poor RTO** because runbooks and recovery permissions were never prepared.

## 3. Three-project topology: source, backup, and restore

A reference diagram:

~~~mermaid
flowchart LR
  subgraph SRC["Project A: app-prod"]
    APP[Spring Boot / GKE / Compute Engine]
    DB[(Cloud SQL / disks)]
    OPS[CI/CD and app operators]
    APP --> DB
  end
  subgraph BAK["Project B: backup-security"]
    VAULT[Backup and DR vault or Backup for GKE]
    GCS[Storage archive with retention]
    AUDIT[Audit logs and alerts]
    KMS[Key project or controlled keys]
  end
  subgraph REC["Project C: isolated-restore"]
    REST[Restore/test cluster or VM]
    VALID[Integrity and smoke tests]
    REST --> VALID
  end
  DB -->|backup via authorized identity| VAULT
  APP -->|service-based backup| VAULT
  DB -. controlled export .-> GCS
  VAULT -->|recovery authorization| REST
  GCS -->|restore drill| REST
  KMS -. policy-compliant decrypt .-> REST
  VAULT --> AUDIT
~~~

Three projects establish **Google Cloud resource and IAM** boundaries, not automatically three completely independent security zones. Broad grants at the organization/folder level, uncontrolled service account impersonation, or KMS management held by a single group can cut across all projects. The backup zone should have separate administrators, automation identities, policies, logging, and approval flows from production.

| Project | Contents | Owner / IAM direction |
|---|---|---|
| A – source | Workloads, databases, disks, app configs, source-level backup connectors | App/platform team holds operational rights; cannot delete backup vault B |
| B – backup | Backup vaults, backup/restore policies, object archives, backup monitoring | Backup/security team; separates retention configurators from deletion approvers |
| C – restore | DR sandbox, target clusters/VMs/databases, isolated network | Recovery team receives time-bound, approved permissions |
| Key/security project (optional) | Cloud KMS keys, IAM federation, audit sinks | Security/key custodians, preventing backup creators from destroying keys |

**Separating projects does not automatically separate regions.** Backups in project B located in the same region as A still share regional failures. Select locations based on data residency, service support, RPO/RTO targets, and data transfer costs. For backup vaults, location is a vault attribute and must match workload/recovery support.

## 4. Responsibility model and separation of duties

Administrative roles should be designed around **potential blast radius**, not merely team names.

| Organizational role | Allowed | Should not be allowed by default |
|---|---|---|
| Application operator | Deploy/restart apps, view backup status, request restores | Lower retention, delete vaults, grant KMS permissions to self |
| Backup policy admin | Create backup plans, set schedules, monitor coverage | Modify production data or self-approve sensitive restores |
| Vault custodian | Manage vaults/retention and project boundaries | Deploy apps or restore into prod without approval |
| Security/key custodian | Grant/revoke key access per policy, investigate audits | Read all app data via restores by default |
| Restore operator | Restore into approved project C | Overwrite production or disable backup protection arbitrarily |
| Auditor | Read backup job metadata, policies, and logs | Read backup payloads, alter IAM, or restore data |
| Incident commander/approver | Declare DR, approve break-glass | Execute every step alone using standing admin accounts |

Practice the **four-eyes principle**: requests to change retention/delete backups, grant restore IAM, or access backups containing sensitive data should require an independent reviewer. Use IAM groups, resource-scoped roles, temporary elevated access, and Privileged Access Manager (PAM) where appropriate. Break-glass accounts must have auditing, time limits, usage conditions, and regular drills.

### Controlling risks from organization-level permissions

Anyone able to modify organization policies, create folder-level role bindings, impersonate service agents, or administer Cloud KMS can bypass the logical wall between projects A/B/C. Therefore, security teams must audit **effective IAM** (including inherited permissions), service account key creation, domain-restricted sharing, project hierarchy, and policy constraints—never look solely at project B's IAM tab and declare backups independent.

## 5. Backup and DR backup vault: centralized management and deletion protection

**Backup and DR** supports a **centralized** model: place backup vaults and backup plans in a management project to protect Compute Engine, Cloud SQL, Filestore, AlloyDB, and other supported workloads across service projects. A **decentralized** model creates per-project vaults/plans for independent team management. Against source-project compromise, the centralized model is usually preferable if IAM is tightly segregated.

A backup vault is a Google-managed regional resource providing isolation and **enforced retention**. Supported workloads differ between the Google Cloud console path and backup/recovery appliances; choose by service and instance type rather than assuming a vault stores arbitrary files.

### Enforced retention and project deletion protection

- When a vault has **minimum enforced retention**, protected backups cannot be manually deleted early. Backup plan retention must be compatible with the vault minimum.
- Vaults can enforce retention aligned with backup rules and provide an option to **lock the retention configuration** with an effective date. Once the lock takes effect, protection levels cannot be reduced or removed per feature rules.
- Enforced retention carries cost: data is retained until expiration even if the application no longer needs it. Base policies on business, legal, and cost requirements.
- Per updated documentation, **starting November 1, 2026**, Backup and DR automatically applies a project-level lien to projects hosting backup vaults with backups protected by enforced retention. This adds protection against project deletion; still audit lien removal permissions and approval workflows.
- **Backup vault access restriction** constrains valid source/target projects or organizations for backup/restore actions. Access restriction can be immutable after creation, so verify the organizational layout beforehand.

**Never use admin privileges to verify controls by attempting to delete real backups.** Validate via retention configurations, IAM, audit logs, appropriate API dry-runs/permission checks, and sandbox environments. When preparing retention changes or permanent locks, require change approval due to irreversible options.

### Backup vault service agent

Each backup vault has its **own service agent** to perform tasks on behalf of the service. For example, for a vault in project B to protect a Compute Engine VM in project A, grant the vault service agent **Backup and DR Compute Engine Operator** (`roles/backupdr.computeEngineOperator`) on project A. When restoring a VM into project C, grant the corresponding role to the service agent on project C per service guidance. This is a scoped trust relationship, not a reason to grant organization-wide Owner.

~~~bash
# Illustrative minimal IAM per docs for vault service agent accessing source VMs.
# Replace placeholders with the service agent email from the created vault.
gcloud projects add-iam-policy-binding APP_PROD_PROJECT \
  --member="serviceAccount:VAULT_SERVICE_AGENT_EMAIL" \
  --role="roles/backupdr.computeEngineOperator"

# Allow Compute Engine restore into the approved target project.
gcloud projects add-iam-policy-binding ISOLATED_RESTORE_PROJECT \
  --member="serviceAccount:VAULT_SERVICE_AGENT_EMAIL" \
  --role="roles/backupdr.computeEngineOperator"
~~~

These commands are **illustrative for review**—do not run before security approval. Permissions for the vault service agent, backup plan creator, and restore operator are **distinct**. For Cloud SQL, Filestore, AlloyDB, or appliance-managed workloads, check the resource-type permission matrix; never reuse the Compute Engine role for all of them.

## 6. Backup for GKE: true cross-project backup and restore

**Backup for GKE** offers cross-project backup/restore (GA as of August 2025): source cluster in project A, backup plan and backups in project B, restore cluster in project C. This is **distinct** from Backup and DR backup vaults, though both serve recovery and separation of duties.

Backup for GKE protects **Kubernetes resource configuration** and can protect **persistent volume data** per the backup plan. It does not automatically protect external databases outside the cluster (such as Cloud SQL), container registries, external secret stores, DNS, OAuth providers, or all VPC resources. For a Spring Boot app, a successful cluster restore while Cloud SQL remains down does not count as business recovery.

### Relationships between projects and resources

| Resource | Where created | Role |
|---|---|---|
| GKE source cluster | Project A | Workload to back up |
| Backup channel | Project A, same region as cluster | Authorizes sending backups to project B |
| Backup plan and Backup resources | Project B | Backup schedule, backup data, and IAM independent of the cluster |
| Restore channel | Project B, same project/region as backup | Designates project C as authorized to receive restores |
| Restore plan / Restore resources | Project C | Rules for restoring Kubernetes resources/PVCs into cluster C |
| GKE restore cluster | Project C | Recovery test or DR environment |

This administrative path is preferable when decoupling **backup lifecycle from the cluster project**, rather than merely exporting YAML manifests from a CI job. Before configuring, enable the proper APIs in each project, enable the Backup for GKE add-on on target clusters, and verify service agents can operate across projects.

### Example: creating a backup channel

Per Backup for GKE documentation, create the backup channel in the cluster's project and region:

~~~bash
# PROJECT_B_NUMBER is the numeric project number, NOT the project ID.
gcloud beta container backup-restore backup-channels create orders-backup-channel \
  --project=APP_PROD_PROJECT \
  --location=asia-southeast1 \
  --destination-project=projects/PROJECT_B_NUMBER
~~~

Next, create the **backup plan in project B** via Cloud Console, select cross-project backups configuration, specify the source cluster in project A and its matching backup channel. Define namespace/PVC scope, frequency, retention, and storage location before enabling. Do not create the new backup plan directly in A if the objective is independent data isolation in B.

### Cross-project restore

When restoring from a backup in B to a cluster in C, create a **restore channel in project B** and a **restore plan in project C**. Example:

~~~bash
gcloud beta container backup-restore restore-channels create orders-restore-channel \
  --project=BACKUP_SECURITY_PROJECT \
  --location=BACKUP_REGION \
  --destination-project=projects/PROJECT_C_NUMBER
~~~

The restore project admin creates a restore plan referencing the backup plan in B and target cluster in C, configuring conflict policies for namespaced and cluster-scoped resources as well as volume data restore policies. **Restores can replace existing resources**, so always use an isolated test cluster first and inspect namespace transformations and PVC states. If GKE versions differ between source and destination, verify Backup for GKE version skew limits.

### IAM/service agent separation for GKE

- Backup schedule managers need **Backup for GKE Backup Admin** (`roles/gkebackup.backupAdmin`) or an appropriate custom role on the right project/resources.
- Restore managers only need permissions to define restore plans and restore into project C; do not grant unbounded rights on B.
- Backup for GKE service agents use dedicated Google-managed principals. Cross-project backup documentation requires bindings between projects A and B, including **roles/gkebackup.serviceAgent** on the cluster side for the backup project's service agent and **roles/gkebackup.crossProjectServiceAgent** on the backup project for the source project's GKE robot principal.
- Cross-project restore requires IAM bindings for the relevant principals between B/C and the restore channel. Always **retrieve the exact project number** because service agent emails typically use project numbers, not project IDs.
- Never assign `roles/gkebackup.serviceAgent` to human users; service agent roles are intended for service principals.

Follow exact steps and roles from the official docs for your service version rather than guessing service agent emails. Confusing project ID and project number is a frequent error that allows channel creation yet returns 403 during actual backup/restore.

### Limitations to document in the runbook

- **Existing** backup plans or restore plans cannot be converted to cross-project mode with a simple edit; create new configurations per guidelines.
- Backup for GKE is only one piece of the strategy: external Cloud SQL databases and object storage require separate protection flows.
- Plan backups may contain Kubernetes Secrets and resource manifests; review encryption, IAM, payload access, and retention.
- Restoring a Deployment requires container images to still exist in Artifact Registry and runtime identities to hold permissions; GKE backups do not replace registry/secret/config dependency recovery.

## 7. Cloud SQL: source in project A, backup/export in project B

Cloud SQL provides automated backups and PITR depending on engine/edition/configuration; this is the service-attached database recovery mechanism. When independent protection in another project is desired, check whether **Backup and DR** supports your Cloud SQL instance type and cross-project backup plan layout, or perform **controlled exports to a Cloud Storage bucket in project B**.

### Exports are not PITR

For instance, SQL/CSV exports or logical dumps to a bucket in project B help preserve an independent copy for restoring into a new database. However:

- A logical export is typically a **point-in-time data snapshot**, not including transaction logs for arbitrary point-in-time recovery.
- Schema, stored routines, triggers, users/grants, and extension coverage depend on engine and export type.
- If an export lacks the snapshot consistency required by your transactions, use an appropriate mechanism or pause writes where needed; verify rather than assume.
- For large DBs, export and import can be lengthy, pushing RTO past requirements.
- Backups/exports contain sensitive data; permission to download export files for restore can be equivalent to full-database read access.

### Example IAM for exporting to a bucket in another project

A Cloud SQL instance uses a **service-managed service account** to interact with Cloud Storage. For exporting to a bucket in B, troubleshooting docs state this principal needs at least **roles/storage.objectCreator** on the bucket to create export objects; for imports or broader read/write needs, required permissions differ by operation and engine. Users initiating exports also need Cloud SQL export permissions on the instance.

~~~bash
# Grant the Cloud SQL instance service account permission to create objects in bucket B.
# Obtain CLOUD_SQL_INSTANCE_SA from Cloud SQL instance details; do not guess.
gcloud storage buckets add-iam-policy-binding gs://org-orders-db-backup \
  --member="serviceAccount:CLOUD_SQL_INSTANCE_SA" \
  --role="roles/storage.objectCreator"

# Example PostgreSQL logical export to a bucket in project B.
# Check exact syntax/flags per engine/version before running in practice.
gcloud sql export sql orders-pg \
  gs://org-orders-db-backup/orders/2026-11-19/orders.sql.gz \
  --database=orders \
  --project=APP_PROD_PROJECT
~~~

These commands are illustrative. Having only **objectCreator** prevents the principal from listing/downloading/deleting existing objects; bucket IAM, retention, monitoring, and cleanup of failed partial files are still needed. Never grant **roles/storage.admin** to a Cloud SQL service account just for exports.

A working export does not mean restore will succeed. The runbook must create a Cloud SQL instance in C, configure private networking/IAM, prepare versions/extensions, grant **read** access on the backup object to the recovery principal, execute the import, verify row counts/checksums or business invariants, and run Spring Boot service smoke tests.

### Cross-database consistency

If the orders API writes to Cloud SQL while publishing Pub/Sub events, a DB export does not automatically create a recovery point synchronized with the Pub/Sub backlog. Track checkpoints, outboxes, consumer offsets, timestamps, or safe event replay mechanisms. A disk-level consistent snapshot is likewise not a distributed transaction spanning databases and queues.

## 8. Compute Engine: snapshot schedules have project boundaries

Compute Engine **scheduled snapshots** are managed by resource policies **within the project hosting the disk**. Google Cloud docs specify that snapshot schedules do not span projects or organizations. You can pick snapshot storage locations per service capabilities, but **a different storage location does not equal a different IAM administrative boundary**.

Therefore, if the requirement is "backups cannot be deleted by project A operators," do not place a snapshot schedule in project A and call it cross-project backup. Evaluate a **Backup and DR backup vault in project B** for supported Compute Engine workloads, granting appropriate scoped permissions to the vault service agent in A.

Before relying on snapshots for application backups:

- Confirm disk scope, snapshot type, encryption key, and location.
- For filesystems/databases, verify **application consistency**: guest flush, VSS, or workload quiescing—not merely crash-consistent snapshots.
- Snapshot schedules have retention, but schedule retention is not inherently **immutable WORM**.
- Alert on snapshot schedule failures and drill creating disks/VMs from snapshots.
- Post-restore, verify boot, networking, firewalls, IAM, and application transaction recovery.

## 9. Cloud Storage in project B: retention, versioning, and overwrite protection

When using Cloud Storage as a backup destination or archive repository, protection requires **multiple layers**:

| Feature | Effect | What it cannot do |
|---|---|---|
| Uniform bucket-level access | Manages access centrally via bucket IAM | Does not make objects immutable |
| Public Access Prevention | Blocks public exposure via public IAM | Does not stop overly privileged internal admins |
| Object Versioning | Retains generations on object overwrite/delete | Does not block permanent deletion of noncurrent generations |
| Soft delete | Enables recovery of deleted objects within retention window | Not equivalent to an irreducible retention lock |
| Bucket retention policy | Retains objects for at least the configured duration | While unlocked, privileged users can alter the policy |
| Bucket Lock | **Permanently** locks retention policy so it cannot be shortened/removed | Does not keep objects forever after retention expires |
| Object Retention Lock | Locks retention on individual objects | Must be enabled and obeys irreversibility rules |
| CMEK | Organization controls encryption keys | Cannot restore if key versions are destroyed or decrypt access is lost |

**Bucket Lock is irreversible.** Once locked, the retention period cannot be removed or reduced; it can only be increased per service rules. Google Cloud also applies a project lien when a bucket retention policy is locked. Verify legal obligations, retention costs, and required durations before locking.

### Append-only IAM for writing backups

For a simple exporter, you can grant the service account in project A **roles/storage.objectCreator** **scoped to bucket B**, without Object Viewer, Object Admin, or Storage Admin. It can write new objects without reading or deleting existing ones. However:

- The account creating objects must not also assign IAM, set retention, alter KMS, or administer project B.
- `objectCreator` works only when backup software **does not need to list/read/overwrite** older objects; some backup tools require extra permissions for catalogs or incremental chains.
- Use unique object names incorporating workload/timestamp/backup ID to avoid collisions; where supported, use upload preconditions such as `generation-match=0`.
- IAM only constrains principal actions; a **retention lock** adds guarantees against early deletion even by broadly privileged operators.
- Monitor object age, checksums, creation timestamps, lifecycle, and restorability; never equate upload success with usable backups.

If data residency mandates storing backups in a specific region, pick a matching bucket location/replication. A bucket in project B is not automatically in another region; if regional DR is also a goal, design location/failure domains accordingly.

### Illustrative bucket policy config

~~~yaml
backup_repository:
  owning_project: backup-security
  bucket: org-orders-db-backup
  storage_location: approved-region
  uniform_bucket_level_access: true
  public_access_prevention: enforced
  object_versioning: enabled
  retention:
    minimum_days: 35
    lock_requires_security_approval: true
  writers:
    - cloud-sql-instance-service-account
  readers:
    - time-bound-restore-service-account
  forbidden_for_app_team:
    - delete_backup
    - update_bucket_iam
    - reduce_retention
    - destroy_kms_key
~~~

This is a **design documentation template**, not a manifest accepted directly by Google Cloud APIs. Actual lock decisions must use tools/processes approved by Security. Never apply permanent-lock test policies to shared buckets before agreeing on cost and lifecycle.

## 10. KMS/CMEK: backups are un-restorable if keys are lost

In a ransomware defense strategy, encryption cuts two ways. It protects backups from unauthorized reading, yet **accidentally destroying or disabling a key version** renders backups undecryptable. For CMEK-encrypted data, manage key lifecycles in lockstep with backup retention.

Designs must specify:

1. **Who owns the key?** Designate security-team key custodians distinct from app deployers and backup operators.
2. **Where does the key live?** Key, bucket, and backup service locations must be compatible per product requirements.
3. **Who encrypts/decrypts?** Grant permissions strictly to the **service agents** executing backups/restores—not Cloud KMS Admin to applications.
4. **What if a key is disabled/destroyed?** Maintain a runbook for restoring key versions/permissions per Cloud KMS behavior, without relying on recovering permanently destroyed keys.
5. **Retention outlives key lifecycle?** Never destroy key versions still needed to read backups retained under policy.
6. **Is there break-glass access?** Must be logged, time-bound, and independently approved.

Do not treat **CMEK as a second backup**. A compromised or revoked key can lock out every encrypted copy sharing that key. Evaluate dedicated keys for the backup domain, independent permissions, alerts on disable/destroy operations, and a backup catalog recording required key references.

### Distinguishing identities

CI/CD service accounts, Backup and DR vault service agents, Backup for GKE agents, Cloud SQL instance service accounts, and Cloud Storage service agents have **distinct roles**. Never share a single principal holding Editor/Owner across A, B, C, and the key project. In your permissions matrix, document the exact principal email/resource ID, exact IAM role, target project/bucket/key, rationale, and revocation conditions.

## 11. Least-privilege matrix and approval workflows

A separation-of-duties model must govern **creating backups**, **deleting backups**, **reading backup payloads**, and **overwriting production via restore**.

| Action | Project/resource | Authorized person or principal | Additional controls |
|---|---|---|---|
| Deploy application | Project A | CI/app operator | No permissions to alter vault B |
| Create automated backups | A → B | Service agent / source backup runner | Minimal permissions on A/B only; no Owner |
| Create or edit backup plan | Project B | Backup policy admin | PR/change approval; alerts on schedule edits |
| Change retention/vault settings | Project B | Vault custodian | Multi-party approval, PAM, auditing |
| Read sensitive backup data | Project B | Approved restore service account | JIT access, data handling rules, no laptop downloads |
| Provision restore cluster/VM/DB | Project C | Recovery operator | Separate budget/quotas/networking and logs |
| Restore into production | Project A | DR lead + restore operator after approval | Change/incident workflow, checkpoints, consistency checks |
| Manage KMS keys | Key/security project | Key custodian | Separate decrypt usage from key administration |
| Review logs and compliance | Audit/backup project | Auditor | Read-only, no payload read rights unless required |
| Delete project/vault or remove lien | Governance/security scope | Specially authorized personnel | Break-glass, multi-party confirmation, independent audit |

Exact roles depend on service type; **there is no single generic backup operator role** valid across every GCP workload. For example, `roles/backupdr.backupvaultAdmin` is a powerful vault management role; `roles/gkebackup.backupAdmin` manages GKE backups; `roles/backupdr.computeEngineOperator` lets a backup vault service agent interact with Compute Engine. Use predefined roles to understand permissions, then narrow scope or use custom roles where appropriate and supported.

### Hidden privilege escalation paths

- **iam.serviceAccountTokenCreator** or `serviceAccountUser` permissions can allow impersonating a principal with backup access; audit effective permissions.
- **resourcemanager.projects.setIamPolicy** on project B can let a user grant themselves broader permissions unless governance controls block it.
- Managing group membership of a `backup-admin` IAM group also confers control over backups.
- Modifying organization policies, security perimeters, or removing project liens can open paths to delete/disable backups.
- Committing CI/IaC changes affecting project B can alter retention policies or backup schedules even without console login.

Therefore, security reviews must inspect the **full permission graph** across organization/folder/project, service accounts, repositories, CI runners, and KMS—not merely direct role bindings.

## 12. Mitigating ransomware and malicious data deletion

Cloud ransomware does not necessarily encrypt files inside a VM; an attacker can call APIs to delete snapshots, lower backup retention, edit backup plans, disable logging, revoke keys, or force backups of corrupted content after compromising the app.

Design defense in depth:

1. **Prevent:** least-privilege IAM, MFA and federation, avoid long-lived user-managed service account keys where safer alternatives exist, restrict IAM edits and delete calls.
2. **Isolate:** backup project independent of application projects, distinct admins, separate CI credentials, compliant with data residency.
3. **Immutability:** Backup and DR vault enforced retention or Bucket Lock/object retention as appropriate; strict governance over irreversible changes.
4. **Protect projects/keys:** project liens, PAM, Cloud KMS IAM, alerts on key disable/destroy, tight limits on removing protections.
5. **Detect:** audit logs and alerts for plan edits, backup IAM changes, logging shutdowns, backup deletions, project deletions, and unusual restores.
6. **Recover:** pre-staged project C, runbooks, temporary permissions, recovery points **prior to compromise**, clean-data validation.
7. **Prove:** restore drills validating integrity, recovery duration, and post-restore secret/identity states.

**The newest backup is not necessarily a clean backup.** Malware or faulty logic may have altered the database days before detection. Maintain retention long enough to reach pre-compromise recovery points and establish clean-point selection methods; you may need to isolate the restored copy from production for forensics before reconnecting.

### Do not absolutize "immutable"

Immutability operates within the chosen service and configuration boundaries. If backup plans stop running, keys cannot decrypt, backups capture corrupted data, or the source project/org is compromised, immutable backups alone may still miss RTO. Only declare "recoverable" after **a full test restore and business validation**.

## 13. Application consistency and recovery order

A Spring Boot application may depend on GKE, Cloud SQL, Secret Manager, Artifact Registry, Pub/Sub, Cloud Storage, and external auth providers. Restoring only Kubernetes Deployments and PersistentVolumes while overlooking databases/secrets can leave services reporting Ready yet unable to process orders.

### Reference dependency order

~~~mermaid
flowchart TB
  ID[IAM, KMS, secrets, and identity] --> NET[VPC, DNS, firewall, and private connectivity]
  NET --> DATA[Restore Cloud SQL / transactional data]
  DATA --> OBJ[Object storage and event checkpoints]
  OBJ --> APP[GKE/VM runtime and images]
  APP --> CHECK[Smoke test + integrity check]
  CHECK --> GO[Controlled traffic cutover]
~~~

Exact order varies by workload, yet must be documented in the runbook. Common pitfalls:

- **Database versions/extensions:** the target DB must match backup compatibility. Logical backups may omit roles/grants or extensions present on source.
- **Identities and secrets:** the app needs the right runtime identity and secret versions; historical keys must remain available to decrypt data.
- **Kubernetes resources:** Backup for GKE restores manifests and PVCs per plan; external DBs, images, and firewalls are not restored automatically.
- **Distributed workflows:** outbox tables, Pub/Sub subscriptions/backlogs, idempotency state, and cron schedulers may not share one checkpoint.
- **Data re-exposure:** sandbox restores must never connect to production payment gateways or send real emails before verification.
- **Object dependencies:** invoice PDFs or images referenced by DB records must exist at a matching recovery point.

When restoring a pre-incident backup, decide how to handle transactions that occurred after the recovery point. A technically acceptable RPO does not define refund rules, customer notices, or event replay; business owners must approve reconciliation.

## 14. Restore drills in project C: testing without breaking production

Schedule **periodic recovery drills** in an independent project C with isolated networking and appropriate test/sanitized data. For sensitive customer data, backup read rights and post-restore access must be controlled as strictly as production; a sandbox is no excuse to bypass data classification.

### Before the drill

1. Select a sample workload, backup ID, timestamp, region/project, and supported checksum/catalog metadata.
2. Obtain change approval, target recovery point, and RTO/RPO criteria.
3. Verify project C has quotas, APIs, IAM, service agents, KMS decrypt access, VPC, DNS, images, and cluster/VM/DB versions.
4. Grant **temporary** restore permissions to the service account; never grant Project Owner to deployers.
5. Block egress to unintended production integrations; tag resources, budgets, and test teardown schedules.

### During the drill

1. Restore into a new namespace/cluster/VM/database—never overwrite the source.
2. Verify manifests/PVCs or disks/DBs are readable and app versions are compatible.
3. Reconcile row counts, hashes/checksums, business transaction IDs, critical records, and access permissions.
4. Run smoke/integration tests: test login, place mock orders, read invoices, check queues (without publishing real events to production).
5. Measure infrastructure provisioning, byte restoration, app startup, consistency checks, and readiness time.
6. Collect evidence logs; evaluate RPO from the last verified checkpoint and RTO from the simulated incident start.

### After the drill

Revoke temporary/JIT restore permissions, close temporary network paths, clean up resources per retention policies, update runbooks, and assign action item owners. Never delete **production backups** just while cleaning up test environments. With locks/retention, avoid creating test backups accidentally locked indefinitely.

### Acceptance criteria

| Check | Sample PASS condition |
|---|---|
| Backup catalog | Matching backup located with timestamp and source identity |
| Permissions | Only approved roles/SAs execute restore; app operators cannot delete backups |
| KMS | Restore reads data without needing key admin privileges |
| Integrity | Data/row counts/transaction IDs match expected checkpoint |
| Application | Critical APIs and jobs pass smoke tests without unintended prod connections |
| RTO/RPO | Both measured metrics fall within approved targets |
| Audit | Logs record role changes, backup access, restore actions, and results |
| Cleanup | Permissions revoked and test resources deleted on schedule; real backup retention untouched |

Adjust PASS criteria per business domain. For a payment system, checking "HTTP 200" is insufficient: verify ledgers, idempotency, and API behavior when the restored DB lacks events emitted after the recovery point.

## 15. Monitoring, auditing, and alerting

Backups are trustworthy only when continuously monitored. A "SUCCESS" job can still skip a volume, miss a namespace, or capture logically corrupted data. Build dashboards across **workload × source project × backup project × recovery point × policy**.

| Signal | Actionable meaning |
|---|---|
 Backup job success/failure | Alert on consecutive failures or missed schedules |
 Last successful backup age | Detect actual RPO breaches even while schedules still exist |
 Protected asset coverage | Identify unprotected VMs/databases/namespaces/PVCs |
 Backup storage growth and retention | Control cost and catch accidental over-retention |
 Changes to vault/backup plan/retention | Detect unauthorized policy changes |
 IAM/service-agent changes | Alert on added Owner roles, delete grants, or unexpected cross-project access |
 KMS key disable/destroy/permission errors | Catch risks of undecryptable backups before restore is needed |
 Cloud Storage deletion/access attempts | Investigate backup deletion/download or ransomware activity |
 Restore operation frequency | Alert on unauthorized or anomalous restores |
 Restore drill success and measured RTO/RPO | Measure real recoverability rather than mere copy creation |

Configure Cloud Audit Logs per activity type and service. Admin Activity logs capture many administrative actions; **Data Access logs may require explicit enablement and incur costs**, especially when auditing backup/object reads. Forward security logs to an independent logging/audit project with its own retention and IAM. For multi-project setups, use folder/organization Log Router sinks where appropriate, ensuring sink writer identities hold write permissions to destinations.

Never log backup contents, credentials, DB export payloads, or secrets into logs/alerts for operational convenience. Dashboards for backup operators should show metadata and status; restore payloads should be accessed only within approved workflows.

## 16. Retention policies and costs

Separate **operational recovery** strategies from **legal archiving**. Short RPOs need frequent backups and PITR; seven-year retention requires archives with immutability policies and protected invoice/contract records.

| Backup tier | Purpose | Example policy for discussion |
|---|---|---|
| Short-term | Recover from deployment errors, accidental deletions | Frequent recovery points sized to RPO |
| Medium-term | Detect corruption/encryption introduced days earlier | Daily/weekly generations long enough for investigation |
| Long-term | Compliance, audits, historical data | Monthly/yearly with dedicated classification and retention |
| Restore test | Verify RTO/RPO | Short-lived test copies in project C, auto-cleaned |

Costs must cover: backup and noncurrent object version storage, vaulted backup retention, backup/restore operations, temporary drill compute, inter-region network transfers, CMEK/KMS, logging, monitoring, and egress. **Enforced retention can require paying for data until expiration** even after the workload is deleted; that is a compliance design feature, not a billing bug.

Cross-project Backup for GKE has billing tied to the backup project; data transfer fees can accrue based on cluster, backup, and restore locations. Before deploying, check current pricing per region, volume type, and GB rather than hardcoding static figures in architecture docs.

### Sample workload policy profile

~~~yaml
workload_id: orders-prod
source_project: app-prod
backup_project: backup-security
restore_project: isolated-restore
business_owner: commerce
data_owner: finance
classification: confidential
objectives:
  rpo_minutes: 15
  rto_minutes: 120
recovery_dependencies:
  - cloud-sql
  - gke
  - secret-manager
  - artifact-registry
  - dns-networking
backup_mechanisms:
  database: backup-and-dr-or-managed-backup-plus-independent-export
  k8s: backup-for-gke-cross-project
  objects: cross-project-storage-with-retention
restore_test:
  cadence: quarterly
  destination: isolated-restore
approvals:
  policy_change: backup-admin-plus-security
  production_restore: incident-commander-plus-data-owner
~~~

This is an enterprise-defined **workload backup passport**, not a Google Cloud API manifest. RPO/RTO values, cadence, and retention must be approved by owners rather than inherited from product defaults.

## 17. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Same group holds Owner across A, B, C | Project boundaries become purely cosmetic | Separate IAM by duty, require approvals, audit inherited roles |
| Putting snapshot schedule in project A and calling it cross-project backup | Snapshots remain under source admin control | Use a Backup and DR vault in B or supported project-isolated solution |
| Treating cross-region replicas as anti-ransomware backups | Deletes/logical corruption replicate too | Keep independent, immutable recovery points where needed |
| Enabling versioning without a retention lock | Privileged users can still delete older generations | Use retention policies / Bucket Lock as required and test |
| Granting Storage Admin to an app exporter | Backups can be read, altered, or deleted out of scope | Grant only `objectCreator` or minimal tool-specific rights on bucket B |
| Allowing app teams to lower backup retention | Can disable recovery before an attack | Separate backup policy admin and require approvals |
| Locking overly long retention without review | Irreversible cost and potential violation of data erasure rules | Legal, financial, data review plus sandbox testing |
| Using CMEK without protecting keys | Backups become undecryptable if keys are destroyed/disabled | Separate key custodians and monitor key lifecycle |
| Backing up GKE while omitting Cloud SQL / Artifact Registry | Restored workload fails to run | Build a dependency passport and test end-to-end restore |
| Backing up DB and queues at uncoordinated times without checkpoints | Replayed or missing events | Outbox, idempotency, reconciliation |
| Running restore drills on networks open to production | Sandbox sends real emails, payments, webhooks, or writes | Isolated networks and mock integrations |
| Measuring backup success without testing restores | Corrupted backups or missing permissions go unnoticed | Restore drills, integrity tests, and real RTO/RPO measurement |
| Keeping all copies in one region | Separated projects still share regional outages | Factor geography/location into RTO, RPO, and residency |
| Forgetting to audit IAM/service agents | Privilege escalation or schedule tampering goes undetected | Log sinks, alerts, and periodic access reviews |

## 18. Scenario: protecting a multi-project ordering platform

A Spring Boot ordering platform consists of:

- Project A: GKE cluster running APIs/workers, Cloud SQL PostgreSQL, Pub/Sub connections, and several Cloud Storage objects.
- Project B: `backup-security` hosting Backup for GKE, Backup and DR vault, logical DB export bucket, dashboards, and backup policies.
- Project C: `isolated-restore` with a GKE cluster, fresh database, and VPC blocked from hitting live payment services.
- Security/key project: manages keys and policies with independent approvers.

Suppose the business sets a 15-minute RPO for orders and a 2-hour RTO for accidental deletion, while also needing recovery prior to a late-detected ransomware attack.

### Architectural decisions

1. **GKE:** use cross-project Backup for GKE with backup plan in B, backup channel in A, and restore channel from B to C; select critical namespaces/PVCs and exclude reconstructible caches.
2. **Cloud SQL:** enable supported managed backups/PITR plus independent protection via Backup and DR vault or periodic exports to bucket B. Document how each mechanism covers part of RPO/RTO; never treat nightly exports alone as sufficient for a 15-minute RPO.
3. **Bucket objects:** grant bucket-scoped export permissions from A, unique object naming, appropriate retention, and policies preventing A operators from deleting backups.
4. **IAM:** CI in A holds deploy rights; Backup admin in B manages plans; restore operator in C holds temporary access; key custodian is independent.
5. **Immutability:** choose enforced retention or Bucket Lock per service after assessing irreversible-change risks.
6. **Monitoring:** track backup age, abnormal backup sizes, consecutive failures, IAM/retention edits, KMS activity, and restore drills.
7. **Recovery:** test restoring GKE resources/PVCs and Cloud SQL from matching recovery points, starting the app in C with test credentials.

### Disaster scenario

A CI account in A is stolen; the attacker deletes Deployments, drops a PostgreSQL table, and attempts to delete all backups.

**Expectation:** the attacker cannot manage vaults/retention/backup buckets in B; independent backups survive, and audit logs catch anomalous IAM/data actions. Security contains the compromise and disables leaked credentials. The recovery team picks a clean recovery point prior to the table drop, restores into C, reconciles data, verifies order IDs, and decides how to handle transactions occurring after the recovery point. Only after approval is traffic cut over or recovered data imported into production.

**If decrypt permissions or project C quotas are missing:** RTO can fail even though backups survived. Therefore, IAM/key rotation drills and quota/capacity verification are mandatory parts of testing, never optional extras.

### Sample acceptance report

| Metric | Hypothetical target | How to prove |
|---|---|---|
 Backup isolation | Operator A cannot delete or alter retention in B | Effective IAM review and non-destructive permission tests |
 Recovery point | Within business RPO | Match transaction IDs, PITR timestamps, backup catalog |
 Service recovery | GKE/DB/API restored within RTO | End-to-end timestamps from DR declaration to smoke test |
 Data correctness | Zero missing/duplicate orders beyond approved threshold | Consistency/invariant tests, reconciliation |
 Compromised credential | Cannot access backup payloads or keys | Service account scope, audits, and access reviews |
 Compliance | Retention and residency compliant | Security/legal sign-off, storage/vault config |

## 19. Sandbox lab exercises

Execute inside approved **sandbox projects**; never create permanent retention locks or backups containing real customer data.

1. Diagram projects A/B/C and an optional key project; list all principals holding broad permissions via organization/folder inheritance.
2. Write a consistency and backup passport for a Spring Boot application with a database and persistent volume.
3. Pick a supported Compute Engine or GKE workload and design a backup vault or cross-project Backup for GKE path.
4. For GKE, identify exact locations for backup channel, backup plan, restore channel, and restore plan; build an IAM/service agent matrix without guessing emails.
5. For Cloud SQL, design an export to bucket B using `objectCreator` and an independent restore plan. Explain why logical exports are not equivalent to PITR.
6. Configure a test bucket with uniform bucket-level access, public access prevention, object versioning, and **unlocked** retention; evaluate lock impact before seeking approval.
7. Create a service account with backup-write-only permissions; verify via legitimate permission checks that it cannot read or delete existing objects.
8. Simulate missing decrypt permissions in a test **without destroying real keys** to observe error messages and refine the runbook.
9. Restore the workload into project C and run smoke/integrity tests; measure actual RTO and potential data loss based on recovery point.
10. Build alerts for backups exceeding RPO age, IAM changes, or unscheduled restores. Assign alert recipients clearly.
11. Write a summary report: which targets the design meets, unprotected dependencies, retention costs, and remediation actions.

Never use privileged access or delete commands on production backups to prove isolation; verify via IAM policy reviews and sandboxes. After drills, revoke temporary access and delete only temporary resources per policy.

## 20. Pre-approval strategy checklist

- [ ] All workloads and datasets have business/data owners, classifications, and clear RPO/RTO targets.
- [ ] HA replicas, snapshots, PITR, independent backups, and archives are distinguished.
- [ ] Project A/B/C boundaries and IAM trust paths are mapped with a service agent inventory.
- [ ] Application teams cannot lower retention, delete vaults/buckets, or grant themselves backup access.
- [ ] Effective IAM across folders/organization, service account impersonation, and CI/CD is reviewed.
- [ ] Backup and DR vaults have supported resource types and compliant locations/access restrictions/retention.
- [ ] Cross-project Backup for GKE has proper backup/restore channels, plans, and service agent permissions.
- [ ] Cloud SQL has tested managed backups/PITR or an independent database backup strategy.
- [ ] Compute snapshot schedules are not mistaken for cross-project isolation.
- [ ] Cloud Storage buckets have scoped IAM, public access prevention, and required retention.
- [ ] Bucket Lock / enforced retention is reviewed by security/legal/finance before locking.
- [ ] Backups and keys have aligned lifecycles; key versions are never destroyed while backups still need them.
- [ ] Project liens and authorized lien-protection/removal procedures are in place where applicable.
- [ ] Backup metadata, payloads, and audit logs have separate access permissions.
- [ ] Alerts exist for job failures, stale backups, IAM/KMS/retention changes, and anomalous restores.
- [ ] An isolated restore project exists with quotas, VPC, identities, images, and mock integrations.
- [ ] Periodic restore drills prove RTO/RPO and business consistency.
- [ ] A ransomware runbook exists for selecting clean recovery points and preventing reinfection.
- [ ] Costs for copies, retention, network transfers, logging, and tests are budgeted.
- [ ] Project/region recoverability is verified against realistic failure domains.

## 21. Conclusion

**Cross-project backup and separation of duties protect recoverability itself, not merely where backup files sit.** A source project may fail or be compromised, yet recovery points, retention policies, audit evidence, and decryption keys must not fall alongside it. On Google Cloud, Backup and DR backup vaults support centralized governance with enforced retention; Backup for GKE supports cross-project protection and recovery; Cloud SQL exports, Compute Engine snapshots, and Cloud Storage offer complementary mechanisms with distinct limits. Effective design requires understanding each product, separating identities and service agents, governing IAM/KMS changes, maintaining an independent restore project, and **regularly proving backups restore into a business-valid system** within approved RTO/RPO.

## References

- [Google Cloud Backup and DR — Backup vaults for immutable and indelible backups](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault)
- [Backup and DR — Create and manage a backup vault](https://docs.cloud.google.com/backup-disaster-recovery/docs/cloud-console/backup-vault-create)
- [Backup and DR — Backup plans](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-plan)
- [Backup for GKE — Overview](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Backup for GKE — Perform cross-project backups](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/cross-project-backups)
- [Backup for GKE — Perform cross-project restores](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/cross-project-restores)
- [Backup for GKE — Plan a set of restores](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore-plan)
- [Backup for GKE — Cross-project pricing](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/about-pricing)
- [Compute Engine — About snapshot schedules](https://docs.cloud.google.com/compute/docs/disks/about-snapshot-schedules)
- [Compute Engine — Create snapshot schedules](https://docs.cloud.google.com/compute/docs/disks/scheduled-snapshots)
- [Cloud SQL — Roles and permissions for import/export](https://docs.cloud.google.com/sql/docs/mysql/roles-and-permissions)
- [Cloud Storage — Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Cloud Storage — Use and lock bucket retention policies](https://docs.cloud.google.com/storage/docs/using-bucket-lock)
- [Cloud Storage — Object Retention Lock](https://docs.cloud.google.com/storage/docs/using-object-lock)
- [Cloud Storage — Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage — Public Access Prevention](https://docs.cloud.google.com/storage/docs/public-access-prevention)
- [Cloud KMS — Key management](https://docs.cloud.google.com/kms/docs/key-management-service)
- [Google Cloud — IAM best practices](https://docs.cloud.google.com/iam/docs/using-iam-securely)
- [Google Cloud — Privileged Access Manager](https://docs.cloud.google.com/privileged-access-manager/docs/overview)
- [Google Cloud — Audit Logs overview](https://docs.cloud.google.com/logging/docs/audit)
- [Google Cloud Architecture Center — Disaster recovery](https://docs.cloud.google.com/architecture/disaster-recovery)
