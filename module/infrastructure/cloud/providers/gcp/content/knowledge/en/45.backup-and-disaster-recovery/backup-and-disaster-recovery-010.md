# Recovering from Accidental Deletion, Disabled Keys, and Ransomware

When a dataset disappears, an application fails to decrypt data, or signs of ransomware emerge, hasty reactions can amplify damage. Restoring the wrong version overwrites valid data; re-enabling a compromised encryption key can hand access back to an attacker; restoring backups into a still-compromised environment risks having the restored copy encrypted or deleted all over again.

This lesson covers how to triage incidents, select a **trustworthy recovery point**, perform a **controlled** recovery, and verify that both data and services have returned to a safe state on Google Cloud. The three hands-on scenarios are **accidental deletion**, **unusable Cloud KMS/CMEK keys**, and **ransomware**. These are three distinct problem classes, so a single generic restore command cannot apply to all of them.

This lesson belongs to the **Backup and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_GCP** module. This module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage, and databases; through deployment scenarios, learners select services, protect resources, automate releases, and monitor reliability and cost. Exercises use Cloud Storage, Cloud SQL, Cloud KMS, and Backup and DR as examples, while principles around evidence, permissions, RTO/RPO, and testing apply across workloads.

> **Operational warning:** The commands and configs below are illustrative examples only and must not be run automatically on production data. Only authorized personnel may define incident boundaries, approve overwrite actions, change key states, alter IAM, or execute cutover. If intrusion is suspected, coordinate with Security Incident Response before restoring.

## Learning objectives

After this lesson, you will be able to:

- Distinguish accidental object deletion, deleting an entire bucket/instance, data corruption, lost decryption access, and ransomware.
- Select the right recovery mechanism: Cloud Storage soft delete/versioning, Cloud SQL backup/PITR, snapshots, Backup and DR vaults, or Backup for GKE.
- Recognize `ENABLED`, `DISABLED`, `DESTROY_SCHEDULED`, and `DESTROYED` states of Cloud KMS key versions.
- Distinguish IAM permission failures from unusable keys and know when not to unilaterally re-enable a key.
- Build an incident workflow: containment → evidence → restore point → isolated recovery → verification → cutover.
- Measure actual RPO/RTO and distinguish merely having backups from being able to restore the service.
- Design backup protection using IAM separation of duties, enforced retention, and periodic drills.

## 1. Start by classifying the incident

Similar-looking "cannot read data" errors can stem from vastly different root causes.

| Symptom | Possible cause | First question | What not to do immediately |
|---|---|---|---|
| Objects missing in Cloud Storage | Accidental delete, lifecycle rule, overwrite, malware | Are soft delete, generations, or retention still active? | Unfiltered bulk restore across the entire bucket |
| Cloud SQL instance missing | Accidental deletion of instance or project | Do retained/final backups and a PITR window exist? | Create a new instance with the same name and assume it is restored |
| Database records altered erroneously | Bug, migration, faulty SQL statement | What was the exact change timestamp and PITR window? | Restore directly onto the live database |
| GCS/Cloud SQL reports CMEK error | Key version disabled, IAM/service agent revoked, EKM unavailable | What do key state, permissions, and audit logs show? | Create a new key and delete the old key |
| Many objects encrypted/renamed suddenly | Ransomware or application bug | Any signs of account compromise, mass deletes, or exfiltration? | Run the suspected infected workload against backups |
| Snapshot exists but cannot mount | Missing key, wrong region/quota, data corruption | Are key dependencies and restore target valid? | Delete the snapshot or source disk |

**Accurate identification is the first step of recovery.** During a security incident, run incident response and disaster recovery in parallel while keeping two clear lines of accountability: Security owns evidence and threat containment; the Recovery team owns correctness of the restored environment.

### 1.1. Order of priorities

1. Protect people, accounts, and remaining healthy data.
2. Stop ongoing deletion, encryption, or bad writes once substantiated.
3. Preserve audit logs, timestamps, resource IDs, and forensic data.
4. Locate backups and the key versions needed to read them.
5. Restore into an isolated environment and verify integrity.
6. Switch traffic or update endpoints once approved.
7. Monitor for reinfection, application errors, data drift, and conduct post-incident review.

Never equate **API-level restore success** with **successful business recovery**. Users should only be served again after critical business flows pass testing and accountable leads accept any residual risk.

## 2. One unified runbook structure across all three scenarios

Every incident should track a shared set of fields so on-call teams can coordinate cleanly:

~~~yaml
incident_id: INC-EXAMPLE-2026-001
severity: SEV-1
status: investigating
service: checkout-api
environment: production
detected_at_utc: "2026-11-19T08:00:00Z"
suspected_start_utc: "2026-11-19T07:40:00Z"
incident_commander: "Assigned role"
security_lead: "Assigned role"
recovery_lead: "Assigned role"
source_project: "PROJECT_ID"
affected_assets:
  - "Cloud SQL: orders-db"
  - "Cloud Storage: gs://BUCKET_NAME/orders/"
encryption_dependencies:
  - "projects/KEY_PROJECT/locations/LOCATION/keyRings/RING/cryptoKeys/KEY"
target_rpo_minutes: 15
target_rto_minutes: 120
candidate_recovery_point: "Unconfirmed"
approvals:
  destructive_restore: false
  key_state_change: false
  production_cutover: false
~~~

This is a **documentation template**, not a configuration file for Google Cloud APIs. Replace placeholders with actual incident IDs inside an access-controlled system. Never record confidential info, secrets, or user data in widely shared reports.

### 2.1. Initial decision flowchart

~~~mermaid
flowchart TD
    A["Detect missing / unreadable data"] --> B["Contain risky actions, preserve evidence"]
    B --> C{"Signs of compromise or ransomware?"}
    C -->|"Yes"| D["Trigger Security IR, revoke sessions/credentials per approval"]
    C -->|"No"| E["Inspect timeline and audit logs"]
    D --> E
    E --> F{"Read error caused by CMEK?"}
    F -->|"Yes"| G["Check IAM, key state, and EKM"]
    F -->|"No"| H{"Deleted / corrupted?"}
    G --> I["Identify recoverable key version"]
    H -->|"Yes"| J["Locate soft delete, backup, PITR, vault"]
    H -->|"No"| K["Investigate further, do not overwrite yet"]
    I --> L["Select clean recovery point and valid permissions"]
    J --> L
    L --> M["Restore in isolated environment"]
    M --> N{"Data clean and tests pass?"}
    N -->|"No"| L
    N -->|"Yes"| O["Approve cutover and monitor"]
~~~

### 2.2. Who is authorized to do what?

| Role | Proposed decisions | Must not do unilaterally |
|---|---|---|
| Incident commander | Severity, recovery priority, communications | Bypass security checks |
| Security lead | Compromise scope, evidence preservation, containment, clean bill of health | Delete evidence for quick cleanup |
| Data owner/DBA | Recovery point, integrity, data reconciliation | Overwrite production before confirming loss scope |
| KMS administrator | Analyze key state, restore/enable per approval | Grant broad decryption permissions |
| Recovery operator | Execute restore to designated target | Unilaterally swap production endpoints |
| Service owner/SRE | SLOs, traffic cutover, rollback, and monitoring | Treat HTTP 200 health checks as sufficient |

For destructive data operations, require two-person approval or organizational change control. Never grant `roles/owner` just to run a restore command; grant permissions scoped by task and duration.

## 3. Preparing for recoverability

**A backup is a copy; recoverability is the ability to locate, decrypt, rebuild, and verify that copy within the required timeframe.** A backup can exist yet be unusable if IAM permissions, key versions, regions, networking, or backup accounts were compromised.

Design defense layers:

| Layer | Role | Google Cloud examples |
|---|---|---|
| Near-term recovery | Guard against accidental deletes/overwrites for days | Cloud Storage soft delete; Object Versioning |
| Point-in-time recovery | Pick timestamp before bad data writes | Cloud SQL point-in-time recovery |
| Independent backups and retention | Protect backups if production accounts are compromised | Backup and DR backup vault with enforced retention |
| Immutable data protection | Block deletion/overwrite before expiration | Cloud Storage Bucket Lock / Object Retention Lock |
| Configuration backups | Recreate infrastructure and workloads | Terraform/IaC, Git, Backup for GKE where appropriate |
| Key and identity management | Preserve ability to read backup data | Cloud KMS, service agent IAM, break-glass access |
| Verification and drills | Prove restores actually work | Restore drills, checksums, queries, and transaction reconciliation |

For critical data, apply principles of multiple copies, separate locations/admin boundaries, and at least one copy undeletable by routine production permissions. Do not assume retention features of one service automatically protect resources in another service.

### 3.1. Backup vaults and enforced retention

Backup and DR backup vaults support **enforced retention**. While retention is active, backups are protected against manual deletion—even by admins or Google—within feature scope. Enforced retention must be configured ahead of time; it cannot rescue backups deleted before the policy took effect.

Important notes:

- Vault administration, backup operation, restore operation, and production permissions should be separated.
- Keys, service agents, and the backup project must remain usable; immutable backups do not decrypt themselves.
- Certain vault settings are constrained by permissions, resource type, region, compliance, and cost.
- Long retention increases storage bills and cannot be arbitrarily shortened once locked.
- Project liens can help block deletion of projects holding vaults; still protect projects and identities from compromise.

**Never test deleting backups on live systems to "verify immutability."** In labs, use dedicated test resources and verify policies/configs rather than creating destructive incidents on production data.

## 4. Scenario A: recovering Cloud Storage after accidental deletion

### 4.1. How does soft delete work?

Cloud Storage soft delete retains deleted or overwritten objects or buckets for a configured duration. On supported buckets, soft delete is enabled by default—typically **7 days**, configurable from **3–90 days**, or disabled with retention 0. Individual bucket settings vary, so check before an incident.

Soft-deleted objects **cannot be read directly** or modified. Authorized users restore them into a new live version; the original soft-deleted object stays until its retention expires. Restoring an object with the same name as an active live object risks overwriting/altering live state. **Check names, generations, and overwrite options before running commands.**

| Feature | What can it help recover? | Limits to remember |
|---|---|---|
| Soft delete | Recently deleted or overwritten objects/buckets within retention | Unrecoverable via this feature after expiration |
| Object Versioning | Noncurrent prior object versions | Does not protect if the whole bucket is deleted; old versions can still be deleted |
| Bucket retention policy | Prevents deleting/overwriting objects before retention period | Does not recover data deleted prior to enabling |
| Bucket Lock | Locks retention policy at bucket level | Locking is irreversible; incurs costs and constraints |
| Object Retention Lock | Protects individual objects for a retention duration | Does not replace independent backups; requires advance design |

Google Cloud recommends **soft delete** as the primary defense against accidental or malicious Cloud Storage deletion. Object Versioning can complement it for accessing noncurrent versions, but does not replace recovering a deleted bucket.

### 4.2. Investigating deleted objects

First confirm project/bucket and suspected deletion window. Use **read-only** commands:

~~~bash
# Run with an account granted permission to list soft-deleted objects.
gcloud storage ls "gs://RECOVERY_LAB_BUCKET/**" --soft-deleted

# Find deleted generations of a specific object.
gcloud storage ls "gs://RECOVERY_LAB_BUCKET/orders/order-001.json" --soft-deleted
~~~

The output lists generations to pick the target version for recovery. Correlate deletion timestamps, creators, and audit logs with the incident timeline. When many objects were deleted, generate a manifest and expected checksums/metadata before bulk restoring.

### 4.3. Restoring the exact generation

After Data Owner approval and confirming it will not clobber a critical live object, run:

~~~bash
# EXAMPLE IN DEDICATED LAB BUCKET ONLY; DO NOT RUN ON PROD.
gcloud storage restore \
  "gs://RECOVERY_LAB_BUCKET/orders/order-001.json#GENERATION_NUMBER"
~~~

If a live object with the same name exists, CLI options may block overwriting unless the operator explicitly selects overwrite behavior. Never blindly pass `--allow-overwrite`: inspect existing versions first and consider restoring to an isolated prefix/area. Post-restore, verify checksums, content types, new generation numbers, and permissions; restored objects may become **Standard** storage class, affecting cost.

If the entire bucket was deleted, **restore the bucket first**, then restore objects. Via CLI/API, restoring a bucket brings back only an **empty bucket**; objects must be restored separately. The Google Cloud Console provides a flow to restore objects alongside the bucket. Recovery can fail if another user claimed the bucket name or retention expired.

### 4.4. Restoring many objects and bulk restore risks

When thousands of objects were deleted within a timeframe, Cloud Storage supports asynchronous bulk restores filtered by deletion time and patterns. This can take time and money and requires handling objects re-written after deletion. Never use a bucket-wide wildcard if only one prefix was impacted.

Safe sequence:

1. Export the affected object/generation list using read-only commands.
2. Narrow the accidental deletion window; exclude objects intentionally deleted on schedule.
3. Group by prefix; confirm ownership and application impact.
4. Test-restore a small sample into an isolated environment or via non-overwriting workflows.
5. Verify hashes, contents, metadata, and business object-key mappings.
6. Approve filtered bulk restore and monitor the long-running operation.
7. Reconcile succeeded, failed, skipped counts and post-restore live data.

**Soft delete cannot undo a faulty database transaction.** If Cloud Storage objects and Cloud SQL records must stay consistent, recover both under a single recovery plan sharing a common timestamp.

## 5. Extended Scenario A: Cloud SQL deleted or data modified erroneously

Cloud SQL PostgreSQL provides two primary paths:

- **Restore from backup:** recovers data as of the backup timestamp. Choosing an **existing target instance** can **overwrite all existing data** on that instance, including its PITR logs. To reduce risk, prefer a **new instance** during investigation.
- **Point-in-time recovery (PITR):** creates a **new instance** at a timestamp within the PITR window. PITR cannot restore directly onto an existing instance. PITR must be configured beforehand with logs still within retention.

### 5.1. Inspecting before deciding to restore

~~~bash
# Check instance description and verify whether PITR is enabled.
gcloud sql instances describe ORDERS_DB \
  --project=STAGING_PROJECT_ID

# List backups for standard backup models.
gcloud sql backups list \
  --instance=ORDERS_DB \
  --project=STAGING_PROJECT_ID
~~~

The actual backup list depends on **Standard** vs. **Enhanced** backups and instance state. For Enhanced backups, inspect vaults, backup plans, data sources, and corresponding restore permissions. Current docs distinguish restore workflows by backup type; never assume every backup uses the exact same command.

For example, once bad writes are pinpointed at **10:00 UTC** and the PITR window covers **09:55 UTC**, you can propose restoring to **09:55** on a **new instance**. Before executing, double-check timezone formatting and exact error onset from audit/app logs so you do not pick an already-corrupted point.

### 5.2. When an instance is deleted

In Cloud SQL today, post-deletion recovery depends on **retained backups**, **final backups**, **Enhanced backups**, and **PITR logs**. If retained backups exist, restore to a new instance; if PITR for the deleted instance was retained, recover by timestamp via API/CLI per documentation.

If an instance is accidentally deleted without a final backup, Google Cloud allows **contacting Customer Care within four days** to *request* instance recovery under specific conditions. This is **not a guarantee** that data is recoverable and never replaces proactive backup retention. Open a support case immediately; preserve deletion time, project, instance ID, and evidence without recreating resources under the same name.

When restoring to a new instance, IPs, connection names, networking, IAM, authorized networks, and app DNS/secret configs may change. Verify every dependency before shifting traffic.

### 5.3. Checking consistency after restore

- Reconcile order counts and total values across business logs, backups, and external payment sources.
- Verify schema migrations/versions and compatible application code.
- Check duplicate keys, foreign keys, and order state machines.
- Inspect outbox/event logs; replay idempotently to avoid duplicate transactions.
- Run read-only smoke queries before opening writes.
- Confirm services point secrets/connection strings to the restored instance.

For payment systems, never blindly replay all messages or requests. Reconciling with external payment processors may require business owner sign-off and anti-double-charge safeguards.

## 6. Scenario B: Cloud KMS/CMEK key disabled

Data in Cloud Storage, Cloud SQL, or snapshots may remain intact yet unreadable because its **customer-managed encryption key (CMEK)** is inactive. Restoring from backups can also fail if those backups rely on the same unavailable key version.

### 6.1. States of a Cloud KMS key version

| State | Usable for crypto operations? | Remediation |
|---|---|---|
| `ENABLED` | Yes, if IAM/service agent permits | Investigate permissions, region, service integration, or EKM |
| `DISABLED` | No; key material is retained | Can be **enabled** again after approval |
| `DESTROY_SCHEDULED` | No; pending destruction | Can be **restored** during waiting period, then **enabled** |
| `DESTROYED` | No; key material destroyed | Normally **unrecoverable**; narrow technical exception for identically re-imported key material |
| `PENDING_GENERATION` / `PENDING_IMPORT` | Not yet usable | Wait for completion or troubleshoot key creation/import |

The default scheduled destruction delay for a key version is typically **30 days**, though configurable or constrained by organization policy. Once the waiting period expires, key destruction is in principle irreversible. Exceptions for re-importing identical key material **do not** apply broadly and are not a standard recovery plan.

**Rotating the primary key version does not automatically decrypt old data.** Data encrypted with an earlier version still needs that exact version to decrypt; rotation governs encrypting new data rather than re-encrypting existing data to the new version.

### 6.2. Inspecting before changing key state

~~~bash
# Read-only: inspect key version states.
gcloud kms keys versions list \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID

# Read-only: inspect a specific version.
gcloud kms keys versions describe KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID
~~~

Concurrently check:

1. Cloud Audit Logs: who called `DisableCryptoKeyVersion`, `DestroyCryptoKeyVersion`, or edited IAM, and when?
2. Key usage tracking and which resources reference the key version; note this data can lag or be incomplete.
3. Does the storage service's **service agent** hold `roles/cloudkms.cryptoKeyEncrypterDecrypter` on the key?
4. Is the KMS location compatible with the resource and recovery region?
5. For Cloud EKM: is the external key manager online, authorizing key usage, and retaining key material?
6. Are there signs of unauthorized use, key compromise, or security policy tampering, or was it an accident?

A `PERMISSION_DENIED` error does not mean the key version is DISABLED. Having permission to read a Cloud Storage object also does not mean a user needs direct CMEK decrypt rights; normally the service's **service agent** performs encryption/decryption.

### 6.3. Accidental disablement with no signs of attack

Once Security and the KMS owner confirm an accident, `DISABLED` can transition back to `ENABLED`:

~~~bash
# Run ONLY after approval and verifying KEY_VERSION.
gcloud kms keys versions enable KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID
~~~

Afterward, verify version state, audit logs, service agent permissions, and test a **read** operation on a test resource encrypted with that version. Never re-enable all old versions wholesale if only one version is relevant.

If a key version is `DESTROY_SCHEDULED` and **has not passed its deadline**, the workflow is:

~~~bash
# Run ONLY after Security/KMS owner approval.
gcloud kms keys versions restore KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID

# Restore returns the version to DISABLED; enable separately.
gcloud kms keys versions enable KEY_VERSION \
  --key=DATA_KEY \
  --keyring=DATA_RING \
  --location=KMS_LOCATION \
  --project=KMS_PROJECT_ID
~~~

Do not confuse `restore key version` with `restore object/backup`. This step only restores usability of the key material; it **does not undo data deleted or encrypted by malware**.

### 6.4. If a key was disabled due to suspected compromise

Do not blindly re-enable it under an operational outage runbook. Security must determine:

- Could the key be used by an attacker-controlled identity?
- Does the attacker still retain permissions on service agents, identities, KMS IAM, or backup projects?
- Must workloads be isolated, identities rotated, access blocked, new keys created, and data re-encrypted?
- Are audit trails preserved and resources on the old version safely migrated before disabling/destroying?
- Is temporary restoration safe and compliant with legal mandates?

For a **DESTROYED** key, never claim "backups will save us." If backups remain encrypted with the lost key material, they may be unreadable. Recovery plans must prove both backups **and** an independent decryption path.

## 7. Scenario C: ransomware and compromised accounts

Cloud ransomware does not necessarily run as malware inside a VM. Attackers can steal credentials, call APIs to delete objects, overwrite objects with attacker-encrypted payloads, create/hold keys, or destroy backups. It may also involve **data exfiltration** prior to encryption; restoring data alone does not address exfiltration risk.

### 7.1. Mandatory response steps

**Detection and confirmation**

- Validate signals: mass object replacements, delete spikes, ransom notes, anomalous service accounts, IAM policy edits, KMS access errors, or out-of-schedule audit activity.
- Correlate Cloud Audit Logs, Security Command Center findings, Cloud Logging, applications, and independent monitors.
- Record detection and suspected attack start times in UTC; distinguish "detected at 10:00" from "data altered since 09:20."

**Controlled containment**

- Coordinate with Security to disable or restrict compromised identities and active sessions; enforce separation of duties.
- Stop suspected compromised workloads from continuing writes/deletes via approved controls without destroying evidence.
- Isolate affected VMs/Pods or networks; block attacker lateral movement paths.
- Shield intact backups, key material, and backup projects from compromised production privileges.
- Preserve logs and forensic images/snapshots per organizational policy; never reintroduce malware into production.

**Eradication and recovery**

- Investigate entry point, abused privileges, persistence mechanisms, and potentially accessed data.
- Patch root causes, rotate credentials, tighten IAM; rebuild clean environments from trusted IaC/images.
- Select a recovery point **prior to infection/bad writes**, not blindly the newest backup.
- Restore into an isolated recovery zone/branch; run integrity checks and security reviews.
- Reopen traffic via canary or cohorts once Security + Data owner sign off.
- Watch for reinfection, retries, unusual writes, and anomalous backup changes.

Google Cloud recommends recovering from **healthy backups**, rebuilding infrastructure from trusted CI/CD/IaC, verifying vulnerabilities are removed, and updating monitoring post-incident.

### 7.2. Never restore into an area still controlled by the attacker

If a production project is compromised, restoring backups into the same project using the same service account risks immediate re-deletion. Whenever possible, use a dedicated **recovery project**, separate service identities, VPC, and key permissions with least-privilege recovery paths. Grant temporary elevated rights with approval and revoke afterward.

~~~mermaid
flowchart LR
    subgraph Bad["Suspected compromised zone"]
      W["Suspected compromised workload / identity"]
      D["Data at risk of tampering"]
    end
    subgraph Vault["Privilege-separated backup zone"]
      B[("Backup vault / immutable objects")]
      K["Key / KMS authorization"]
    end
    subgraph Clean["Isolated recovery zone"]
      I["Verified IaC + images"]
      R["Restore to new target"]
      T["Malware scan + integrity + business checks"]
    end
    W --> D
    B --> R
    K --> R
    I --> R
    R --> T
    T --> A{"Security and owner approval?"}
    A -->|"Yes"| P["Controlled cutover"]
    A -->|"No"| R
~~~

In practice, network diagrams must show project boundaries, service agents, egress, private access, KMS, logging, DNS, and operator rights. "Different project" does not automatically mean clean if it trusts the same compromised identity.

### 7.3. Finding a clean recovery point

| Timestamp | Illustrative meaning |
|---|---|
| 08:40 | Backup completed; no signs of compromise yet |
| 09:10 | First anomalous IAM change observed |
| 09:25 | Mass object overwrites begin |
| 09:40 | Monitoring reports data read errors |
| 09:55 | Security confirms incident |

A backup taken at **09:30** may already contain tampered data despite being the newest. Here, **08:40** is a better *candidate*, yet hashes, timelines, and malware indicators must still be checked. If a clean point cannot be verified, never claim "the latest backup is clean."

### 7.4. Immutable does not equal sufficient

Backup vaults with enforced retention, Cloud Storage soft delete, and Bucket Lock defend against deletion. However:

- Attackers can still corrupt data **before the backup runs**.
- Recovery credentials can be compromised if shared with production.
- Missing key versions or KMS service agent IAM can block decryption.
- Restores can incur major costs, egress, and quota contention.
- Some systems require transaction reconciliation, event replay, or separate metadata/secret restoration.

Test restore workflows regularly—including building new targets and validating DB/query/app health—rather than merely checking backup creation dates.

## 8. Protecting backups and keys before an incident

### 8.1. Separation of administrative duties

| Asset | Recommended protection |
|---|---|
| Production project | Runtime workloads cannot delete backups or lower retention |
| Backup project/vault | Separate admin team; appropriate enforced retention |
| KMS project | Key administration separated from usage; auditing and approvals |
| Restore identity | Dedicated account or temporary elevation; audited |
| Cloud Storage retention | Configured pre-incident, restricting who may modify it |
| IaC/artifacts | Protected repository branches, signed artifacts, retained tested releases |
| Logs/evidence | Restricted log deletion rights, proper retention and storage location |

With Cloud Storage **Bucket Lock**, locking retention is irreversible; never apply it casually to scratch buckets or short-lived logs. With Object Versioning, noncurrent versions can still be deleted under policies; configure lifecycle and soft delete to match recovery goals rather than treating versioning as immutable backup.

### 8.2. Lifecycle and key-destruction controls

- Alert on changes to IAM, backup plans, key version states, bucket soft-delete policies, and retention.
- Before destroying a key, audit key usage, backup retention, encryption dependencies, and re-encryption feasibility.
- Maintain a key/resource mapping: a backup may depend on a key in another project/region.
- With Cloud EKM, recovery depends on both the Google Cloud key association and external key manager availability/permissions.
- Never equate retention with RPO: retention keeps recovery points for a duration, whereas **RPO** is acceptable data loss; they relate yet differ. Set backup frequency, WAL retention, and retention policies independently.
- Track costs of versioning, soft delete, backup vaults, and inactive keys; long retention increases storage spend.

### 8.3. Testing backups via real restores

A "backup success" report only shows the service finished a backup job. It does not prove:

- The right backup can be located.
- Service agents and operators hold restore permissions.
- Required key versions can still decrypt data.
- Target restore region/location is compatible.
- Application data aligns consistently with logs/message queues.
- SLOs, RTO, and RPO satisfy business requirements.

Quarterly or based on risk, run restore drills in an isolated environment; also test failure paths like broken keys, missing IAM, and insufficient quotas.

## 9. Safe hands-on exercises in a lab environment

**Never test by deleting or altering production data.** Use an isolated test project/bucket, synthetic data, and a small budget; before acting, inspect soft-delete settings on the lab bucket.

### Exercise 1 — Recover a deleted mock object

1. Create a test bucket with soft delete enabled per Cloud Storage guidance in an approved lab project.
2. Upload a synthetic JSON file; record object name, generation, checksum, and timestamp.
3. An authorized instructor deletes **that test object only** to simulate accidental deletion.
4. List soft-deleted versions and pick the right generation.
5. Run `gcloud storage restore` for that generation after verifying it does not overwrite a live object.
6. Read the restored object, compare checksums, and check metadata.
7. Record time from detection to verification, incurred fees, and required IAM.

This exercise requires no real malware and must not disrupt shared resources.

### Exercise 2 — Inspecting a test key's states without breaking real data

1. Use a dedicated Cloud KMS key version for the lab to encrypt synthetic data.
2. Inspect key state with `gcloud kms keys versions describe`.
3. Discuss what happens when a key becomes `DISABLED` or `DESTROY_SCHEDULED`.
4. Only in an approved lab, test disable/enable or schedule/restore on test data; do not execute full destruction.
5. Verify the `DESTROY_SCHEDULED → DISABLED → ENABLED` state flow, IAM, and logs.
6. Write a dedicated runbook for suspected key compromise; only Security authorizes re-enabling.

### Exercise 3 — Ransomware tabletop without running malware

Assign four roles: Incident Commander, Security, Data Owner, and Recovery Operator. Each group receives a hypothetical timeline and backups timestamped before and after the compromise time.

Tasks:

- Select containment and evidence preservation steps.
- List identities, projects, storage locations, and key dependencies to audit.
- Pick a recovery point and explain why it is **likely clean**.
- Propose an isolated restore environment and pre-cutover verification checks.
- Compute RPO/RTO from timestamps; note costs and data-loss risks.
- Present a "restore vs. wait longer" decision with rationale and approvers.

## 10. Measuring RPO, RTO, and recovery quality

**RPO (Recovery Point Objective):** maximum acceptable data loss in time. **RTO (Recovery Time Objective):** maximum desired time to restore service after an incident, using clearly defined start/end boundaries.

Hypothetical timeline example:

| UTC time | Event |
|---|---|
| 09:50 | Latest verified clean recovery point |
| 10:00 | Erroneous data-write incident starts |
| 10:12 | System detects and opens incident |
| 11:20 | App restored, business checks pass, and traffic reopened |

Defining impact start as **10:00**, the organization loses up to roughly **10 minutes of data** if restoring to 09:50; **actual achieved RPO ≈ 10 minutes** in this example. Measuring RTO from incident start **10:00** to service restoration **11:20**, **actual achieved RTO ≈ 80 minutes**. Never use detection time (10:12) to shrink RTO unless operational standards explicitly define that start point.

~~~text
Actual data loss window = Incident time - Last verified clean recovery point
Actual service recovery  = Verified service restore time - Incident start time
~~~

With ransomware, the "last clean point" may precede the newest backup by far. If when the attacker began altering data cannot be determined, record **unknown** or an uncertainty range rather than reporting a falsely exact RPO.

### 10.1. Layered post-restore verification

| Verification layer | How to verify | Pass condition |
|---|---|---|
| Backup artifact | Exact source, timestamp, and generation | Evidence present; hashes/metadata consistent |
| Decryption | Valid key version / service agent | Test read succeeds without excessive privilege grants |
| Database | Schema, rows, consistency, constraints | No corruption or data loss beyond approved RPO |
| Application | Health, smoke tests, critical user journeys | SLIs pass within predefined thresholds |
| Asynchronous events | Queues, outbox, retry/idempotency | Zero duplicate events or unapproved dropped messages |
| Security | No remaining IOCs/persistence; IAM restored | Security lead approves opening traffic |
| Operations | Logs, metrics, alerts, new backup jobs | On-call, monitoring, and rollback ready |
| Business | Transaction reconciliation, customer data | Data/business owner signs off |

On GKE, Backup for GKE can restore Kubernetes resources into a target cluster, yet recreating resources does not guarantee workloads run right away; scheduling, networking, volumes, IAM, and application readiness must converge. On Compute Engine, create new disks/VMs from usable snapshots and verify data before shifting workloads; never assume snapshots hold consistent DB states without application-aware quiescing.

## 11. Logs and evidence to retain

Depending on service and policy, investigative sources include:

- **Cloud Audit Logs:** object/instance deletions, IAM edits, retention changes, KMS key version states.
- **Cloud Logging and Error Reporting:** app errors, 403/permission failures, decrypt errors, retry spikes.
- **Security Command Center:** configuration and anomalous behavior findings if enabled.
- **Cloud Monitoring:** error spikes, throughput, CPU, connection counts, latency, and backup health.
- **Backup and DR / Cloud SQL backup reports:** backup plans, retention, selected recovery points, restore outcomes.
- **Organizational access/activity logs:** identity providers, CI/CD, PAM/break-glass approvals.
- **Forensic evidence:** snapshots/disk images/logs preserved under chain of custody for security investigations.

Start with Cloud Logging queries filtered by resource type, project, and incident time window. Different log categories may require Data Access audit logging enabled upfront with separate costs/retention; **never assume every API call is logged in full by default**.

### 11.1. Sample recovery log

~~~yaml
incident_id: INC-EXAMPLE-2026-001
resource: "Cloud Storage orders object"
root_cause: "accidental delete, no evidence of compromise yet"
evidence:
  - "audit log event reference"
  - "generation list before restore"
recovery_point: "object generation approved by Data owner"
restore_target: "isolated lab prefix / approved destination"
approvals:
  - "Security: approved"
  - "Data owner: approved"
actual_rpo_minutes: 10
actual_rto_minutes: 80
validation:
  checksum: passed
  application_smoke: passed
  reconciliation: pending
next_review: "Date/time per process"
~~~

Never mark `passed` before actually executing the check. If reconciliation remains pending, reopen traffic only under approved conditions and risk acceptance.

## 12. Coordinating DR with key recovery

An encrypted backup design has at least three dependencies:

1. **Intact backup/ciphertext still within retention.**
2. **Usable right key version**, or a verified origin key-management/import mechanism.
3. **Exact service agents and identities** holding permissions on both key and restore target.

Do not alter Cloud KMS IAM mid-restore without confirming which permissions apply to source and target. For Cloud SQL cross-region restore with CMEK, a key **in the target region** may be required for the newly created instance, while the source backup may still depend on decryption via the source key. Check service documentation per backup type and region; never treat "create a new key" as a cure for losing an old key.

### Key dependency exercise

Suppose a Cloud SQL backup created at 09:50 uses a `DISABLED` key version while the service agent still holds KMS permissions. With no signs of attack, the flow may be: verify version → approve enable → verify backup read → create new instance → restore → verify.

If that same key version is `DESTROYED`, that flow is no longer an option. If the backup was encrypted under another key and an independent copy exists, evaluate an alternate path; otherwise, operators must transparently report limits rather than promising data recovery.

## 13. Avoiding common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Restoring immediately on spotting an error | Overwrites good data, destroys evidence | Classify incident, pick isolated restore target |
| Picking newest backup during suspected ransomware | May restore malware or tampered data | Verify clean point via timeline and IOCs |
| Equating soft delete with versioning | No protection against deleting the bucket | Check soft delete/retention; versioning is supplementary |
| Not checking generation numbers | Restores wrong version or overwrites live object | Use exact generation; verify hash and metadata |
| Assuming PITR "rolls DB back in place" | Misunderstands semantics, breaks cutover | Cloud SQL PITR creates a new instance; plan routing/validation |
| Thinking backups alone guarantee recovery | Key material/IAM/quotas/regions may block | Drill restores along actual decryption paths |
| Enabling KMS key immediately when compromise is suspected | Can re-grant attacker read access | Get Security approval; revoke bad access first |
| Creating a new key then deleting old versions | Old data becomes undecryptable | Retain needed versions; re-encrypt with verification |
| Granting Owner to "restore faster" | Expands blast radius and attack leverage | Least privilege, temporary elevation, and auditing |
| Restoring into the same compromised identity | Restored copy gets destroyed again | Separate projects/permissions; clean recovery zone |
| Skipping message/outbox reconciliation | Duplicate orders or lost events | Audit transactions; idempotent replay |
| Testing availability only, not data | API returns 200 with wrong data | Test critical user journeys, hashes, and reconciliation |
| Long retention without cost modeling | Runaway backup storage bills | Align data policies with RPO/retention/compliance |
| Omitting evidence and approvers | Hard to investigate and audit | Incident records, approvals, timestamps, links |

## 14. Prevention and recovery readiness checklist

**Before an incident**

- [ ] Inventory exists for data assets, backup locations, owners, and criticality.
- [ ] Business owner approved RPO/RTO with measurement methods and periodic DR tests.
- [ ] Cloud Storage soft delete/retention and object versioning are configured intentionally.
- [ ] Cloud SQL backups/PITR are explicitly enabled, with post-deletion backup retention where needed.
- [ ] Backup and DR vaults have separated permissions and enforced retention if appropriate.
- [ ] Key/resource/backup dependency mappings are updated after key rotations.
- [ ] Every critical backup has been test-restored onto a new target.
- [ ] Audit logs, monitoring, and alerts exist for mass deletes and IAM/KMS/retention edits.
- [ ] Recovery project, break-glass accounts, and controlled runbooks exist.
- [ ] Procedures exist for evidence preservation and malware/exfiltration response.

**During an incident**

- [ ] Engage Incident Commander and Security on any sign of compromise.
- [ ] Identify start time, detection time, affected resources, and projects.
- [ ] Preserve logs, snapshots, and evidence per policy.
- [ ] Verify backup/soft-delete/PITR windows **before expiration**.
- [ ] Verify exact key version, key state, IAM/service agents, and region.
- [ ] Obtain approval before overwrite restores, enabling keys, or switching production endpoints.
- [ ] Restore to an isolated target and verify cleanliness/safety.
- [ ] Run integrity checks, business reconciliation, and smoke tests.
- [ ] Record actual RPO/RTO, costs, and residual risk.
- [ ] Cut over only with approval; monitor for recurrence.
- [ ] Update runbooks, backup protections, and threat detections post-mortem.

## 15. Self-check

1. Why can objects in a Cloud Storage bucket with Object Versioning still be lost if the entire bucket is deleted?
2. When restoring a soft-deleted object, what role does the generation number play?
3. Does restoring a soft-deleted bucket via gcloud automatically restore all objects inside it?
4. What is the difference between restoring a Cloud SQL backup onto an existing instance vs. PITR?
5. How does a `DISABLED` Cloud KMS key version differ from `DESTROYED`?
6. What steps are needed to make a `DESTROY_SCHEDULED` key usable again?
7. Why might an existing backup still be undecryptable?
8. Why does ransomware require choosing a clean backup rather than the newest one?
9. Does a backup vault with enforced retention eliminate the need for IAM separation and recovery drills?
10. In the example where an incident starts at 10:00, the clean recovery point is 09:50, and service resumes at 11:20, what are actual RPO and RTO?
11. When recovering orders and outbox records, what can happen if Pub/Sub messages are replayed without idempotency?
12. When must Security approval take priority before re-enabling a CMEK?

**Answer key**

1. Versioning keeps noncurrent versions inside the bucket, not protecting against deleting the entire bucket; bucket soft delete or independent backups fit this scenario better.
2. Generation uniquely identifies the deleted object version, preventing restoring the wrong version or clobbering newer live versions.
3. No. CLI/API bucket restore returns the bucket itself; objects must be restored separately. Console offers an option to restore objects together.
4. Restoring a backup onto an existing instance can overwrite target data; PITR creates a new instance at a timestamp within the recovery window.
5. `DISABLED` retains key material and can be re-enabled; `DESTROYED` destroys key material and is normally unrecoverable.
6. Restore the version while still within the scheduled destruction window → version returns to `DISABLED` → enable after approval.
7. Missing CMEK key version, missing KMS permission for the service agent, EKM unavailability, or region constraints.
8. The newest backup may hold already tampered/encrypted data; a clean point prior to compromise must be verified.
9. No. Vaults prevent deletion during retention, but do not prove backups are clean, IAM is accurate, or keys remain readable.
10. Measured from incident start 10:00, actual RPO is ~10 minutes and actual RTO is ~80 minutes.
11. Duplicate processing, duplicate orders, or repeated notifications/charges; idempotency and reconciliation are required.
12. Whenever signs indicate credential compromise, exfiltration, unauthorized IAM edits, or the key was disabled for containment.

## Conclusion

Effective recovery does not begin with a restore command—it begins by **pinpointing the exact root cause, protecting remaining healthy data, choosing a decryptable recovery point, and verifying a clean state before reopening service**. Accidental deletion can be addressed with soft delete/versioning or backups; `DISABLED` Cloud KMS keys can be re-enabled under control whereas `DESTROYED` keys can render data unreadable; ransomware requires investigation and rebuilding a clean environment before applying backups. Regardless of managed services used, organizations still require separation of duties, DR drills, measurable RPO/RTO, and accountable ownership of cutover decisions.

## References

- [Google Cloud Storage — Soft delete overview](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Google Cloud Storage — Use soft-deleted objects](https://docs.cloud.google.com/storage/docs/use-soft-deleted-objects)
- [Google Cloud Storage — Use soft-deleted buckets](https://docs.cloud.google.com/storage/docs/use-soft-deleted-buckets)
- [Google Cloud Storage — Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Google Cloud Storage — Bucket Lock](https://docs.cloud.google.com/storage/docs/bucket-lock)
- [Google Cloud SQL PostgreSQL — Backup and recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Google Cloud SQL PostgreSQL — Restore an instance](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/restoring)
- [Google Cloud SQL PostgreSQL — Point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Google Cloud SQL PostgreSQL — Delete instances and recovery](https://docs.cloud.google.com/sql/docs/postgres/delete-instance)
- [Google Cloud KMS — Enable and disable key versions](https://docs.cloud.google.com/kms/docs/enable-disable)
- [Google Cloud KMS — Destroy and restore key versions](https://docs.cloud.google.com/kms/docs/destroy-restore)
- [Google Cloud KMS — Key version states](https://docs.cloud.google.com/kms/docs/key-states)
- [Google Cloud KMS — Customer-managed encryption keys](https://docs.cloud.google.com/kms/docs/cmek)
- [Backup and DR — Backup vault overview](https://docs.cloud.google.com/backup-disaster-recovery/docs/concepts/backup-vault)
- [Backup for GKE — Restore from backup](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/how-to/restore)
- [Google Cloud Security — Mitigate ransomware attacks](https://docs.cloud.google.com/docs/security/mitigating-ransomware-attacks)
