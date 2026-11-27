# Backup Retention Policies, Encryption, and Access Control in MongoDB

## 1. Learning Objectives and Context

MongoDB backups are more than running an export command and saving a file to disk. A copy is useful only when the organization knows **how long to keep it, who is permitted to read/delete/restore it, which key encrypts it, and whether it can actually be recovered within an acceptable timeframe**.

For example, suppose an ordering system hits three incidents:

1. An employee accidentally deletes the `orders` collection at 10:25.
2. Ransomware compromises the backup host and tries to delete every backup file.
3. A backup encryption key is accidentally revoked, leaving backup files intact yet undecryptable.

These three incidents demand distinct controls: an **appropriate recovery point**, **immutable/independent copies**, and **encryption key lifecycle management**. Simply accumulating backup files does not handle all three.

This lesson belongs to the **Backup and Recovery** chapter of the **Database Engine Document MongoDB** module, covering **Backup Retention Policies, Encryption, and Access Control**.

After this lesson, you can:

1. Distinguish backups, snapshots, oplog-based point-in-time recovery, archives, and replica sets.
2. Determine RPO/RTO and design backup schedules, retention tiers, and PIT restore windows.
3. Design daily/weekly/monthly/yearly retention policies balancing legal and cost constraints.
4. Apply the **3-2-1-1-0** rule, offsite copies, immutable storage, and ransomware defenses.
5. Understand MongoDB Atlas Cloud Backup/Continuous Cloud Backup policies and Backup Compliance Policy.
6. Select encryption layers: TLS, encryption at rest, backup file encryption, and KMS/CMK.
7. Preserve decryptability across key rotations, KMS migrations, and historical backup restores.
8. Separate permissions across MongoDB backup users, restore operators, the Atlas control plane, object storage, and KMS.
9. Use `mongodump`/`mongorestore` within proper scope without misassuming replica set/sharded cluster consistency.
10. Design checksum verification, restore drills, audit trails, alerts, and runbooks.
11. Resolve tensions between retention, privacy deletion requests, and legal holds.
12. Draft a complete, testable MongoDB backup policy through practice exercises.

**Core message:** A backup that has never been test-restored, cannot be decrypted when needed, or can be wiped by an over-privileged operator is not a trustworthy recovery strategy.

## 2. From Production Data to a Usable Recovery Point

A data copy can take several forms:

| Form | Nature | Used For |
|---|---|---|
| Logical dump | BSON documents and metadata from `mongodump` | Migrating/restoring by database/collection and small/medium scenarios |
| Physical snapshot | Storage image consistent at a point in time | Faster recovery on matching configurations |
| Cloud Backup snapshot | Managed backup service operated by Atlas | Restoring clusters to retained restore points |
| Oplog/PIT data | Changes captured between snapshots | Restoring to a timestamp within the restore window |
| Immutable/offsite copy | Copy protected against modification/deletion | Shrinking blast radius during ransomware or credential compromise |
| Long-term archive | Historical data kept long term | Legal/audit compliance, typically with a longer RTO |

### 2.1. Replica Sets Do Not Replace Backups

A replica set synchronizes data across nodes, increasing availability. Yet if an accidental delete succeeds and replicates, **the entire replica set loses that data**.

~~~text
            Accidental collection delete
                       |
                       v
               Replica set PRIMARY
                 /          \
                v            v
           SECONDARY 1   SECONDARY 2
                \            /
                 \          /
             Both replicate the delete

        Backup/PIT snapshot preserves pre-incident state
~~~

Sharding does not automatically create recovery history either. Replication and backups solve different problems.

### 2.2. Backup and Restore Must Be Designed Together

A policy saying only "back up nightly" without specifying where to restore, how long it takes, and who can decrypt is incomplete.

You must define the full chain:

~~~text
Source MongoDB -> Consistent backup -> Encrypted storage
                                      |
                                      v
                                  Retention
                                      |
                                      v
                                 Access control
                                      |
                                      v
                                 Restore drill
                                      |
                                      v
                            Recovery acceptance test
~~~

### 2.3. "Backup Successful" Differs From "Recoverable"

A job exiting with code 0 only proves the tool finished without crashing. You must confirm the file actually exists, holds expected contents, passes checksums, has accessible decryption keys, restores cleanly, and satisfies application data checks.

## 3. RPO and RTO: Two Inputs to Retention Policy

**RPO — Recovery Point Objective:** the maximum data loss measured in time that the business tolerates.

**RTO — Recovery Time Objective:** the maximum allowed time to restore service operability.

Example:

~~~text
Incident at 10:25
Latest backup: 10:00
Service restored at 11:10

Max data loss per snapshot: ~25 minutes
Recovery time: 45 minutes
~~~

In this example, without PIT, actual RPO at incident time reaches 25 minutes; observed RTO is 45 minutes.

### 3.1. The Two Targets Are Not Equivalent

Taking snapshots every 5 minutes does not guarantee a 5-minute RTO: restoring a multi-TB database can still take hours.

Conversely, restoring a snapshot in 5 minutes when the latest copy is from last night still incurs a huge RPO.

### 3.2. Setting Targets by Data Classification

| System Group | Example RPO | Example RTO | Suggested Policy |
|---|---:|---:|---|
| Orders / payments | 5 minutes | 1 hour | PIT/continuous backup, regular drills |
| Critical CMS content | 1 hour | 4 hours | Frequent backups, periodic snapshots |
| Recomputable reporting data | 24 hours | 24 hours | Daily snapshots, simple restore |
| Test/sandbox data | Reproducible | Priority-dependent | No backup or very short retention |

**These numbers are design examples**, not default MongoDB SLAs. Confirm with business owners, legal teams, and operations.

### 3.3. RPO Is Measured From a Usable Recovery Point

If a backup starts at 10:00 yet fails encryption/upload at 10:02, no valid backup exists for 10:00. The real recovery point remains 09:00.

Dashboards must show the **last verified recoverable point**, not merely the scheduled job timestamp.

## 4. Retention Is a Policy, Not an Arbitrary Number of Days

Retention defines **which copies are kept and for how long**. It must specify:

- Copy type: snapshot, PIT/oplog, archive.
- Creation frequency.
- Retention duration.
- Storage location.
- Encryption policy.
- Authorized principals.
- Deletion conditions, legal holds, and exceptions.
- Recovery objectives.
- Effective date/revision history and owner.

### 4.1. Common Tiered Scheme

**Grandfather–Father–Son (GFS)**:

- **Son:** short-term hourly/daily copies.
- **Father:** weekly copies.
- **Grandfather:** monthly/yearly copies.

Illustrative policy example:

| Tier | Frequency | Keep For | Purpose |
|---|---|---|---|
| Hourly | Every 6 hours | 7 days | Near-real-time recovery |
| Daily | Every day | 14 days | Fixing bugs detected a few days later |
| Weekly | Every week | 8 weeks | Rolling back prior to major changes |
| Monthly | Every month | 12 months | Reconciliation and auditing |
| Yearly | Every year | 3 years | Policy-mandated archival |
| PIT/oplog | Continuous | 7 days | Recovering to a specific minute/second inside the supported window |

Intervals and durations must be configured on the target platform. **Never** treat this table as a universal legal requirement or Atlas default config.

### 4.2. Snapshot Interval and Retention Duration Are Separate Concepts

A snapshot running every 6 hours and kept for 7 days:

~~~text
frequency = every 6 hours
retention = 7 days
~~~

Without PIT, a failure right before the next snapshot risks losing nearly 6 hours of data. Retaining snapshots for 365 days does not improve near-term RPO if snapshots run too infrequently.

### 4.3. Classify Data Before Setting Retention

- Data reconstructible from trusted upstream sources.
- Critical transactional data.
- Data containing PII or sensitive fields.
- Data subject to statutory record-keeping.
- Data past its lawful purpose.
- Data held under a legal hold.

Excessive retention raises storage costs and breach blast radius; overly short retention loses needed recovery points.

## 5. Choosing Between Atlas Cloud Backup and Self-Managed

### 5.1. MongoDB Atlas Cloud Backup

Atlas provides policy-based schedules such as **hourly, daily, weekly, monthly, and yearly**, with retention varying by configuration and cluster tier. Snapshots use Atlas-managed mechanisms; per architecture docs, storage works incrementally to optimize cost and support recovery.

Advantages:

- Centralized management of snapshot schedules and retention.
- Cluster or PIT restores when Continuous Cloud Backup is supported/enabled.
- Restore job tracking and auditing in Atlas.
- Optional cross-region snapshot copies.
- Backup Compliance Policy on eligible deployments.

**Verify tier and configuration:** Never claim all Atlas Free, Flex, and Dedicated clusters share identical snapshot/PIT policies. Dedicated M10+ clusters offer specific Cloud Backup and compliance features, whereas Flex has its own backup mechanics.

### 5.2. Continuous Cloud Backup / Point-in-Time Restore

With Continuous Cloud Backup enabled, Atlas retains snapshots alongside the oplog data required to restore to a timestamp inside the **restore window**.

Example:

~~~text
Snapshot 06:00 ---- oplog changes ---- 10:24:59 ---- 10:25 accidental delete
                                             |
                                             v
                               Restore to pre-delete point
~~~

PIT helps recover from accidental deletes or bad updates. Still check:

- Does the restore window cover the target timestamp?
- Is the base snapshot intact and valid?
- Is the oplog chain complete and synchronized?
- Do the cluster, region, and target support restoration?
- What is the resulting RTO from snapshot restore + oplog replay?

### 5.3. Self-Managed Backups

For self-managed MongoDB, options include:

- MongoDB Ops Manager/Cloud Manager or an eligible management platform.
- **Consistent** filesystem/storage snapshots following MongoDB guidelines.
- `mongodump`/`mongorestore` for logical dumps.
- Physical backup strategies coordinating topology, replication, and oplog.

**Never** treat a live file copy of the data directory while the server is writing as a consistent backup. Follow MongoDB's official filesystem snapshot or backup tool procedures.

### 5.4. Avoid Choosing Tools Based Only on Familiarity

| Need | Tool to Evaluate |
|---|---|
| Atlas managed cluster | Cloud Backup and PIT if supported |
| Large, actively written sharded cluster | Coordinated cluster-consistent backup |
| Exporting a small collection intentionally | `mongodump` and `mongorestore` |
| Minute-level RPO | Appropriate continuous/PIT backup |
| Long-term audit archives | Dedicated snapshot/archive retention with compliance controls |
| Fast in-region recovery | Local/optimized snapshot restore where supported |
| Ransomware defense | Immutable/offsite copies and identity separation |

## 6. Retention Characteristics in MongoDB Atlas

An Atlas backup policy specifies a **frequency interval** and **retention duration** per tier.

Illustrative example:

~~~text
Hourly:  every 6 hours, keep 7 days
Daily:   every day, keep 14 days
Weekly:  every week, keep 8 weeks
Monthly: every month, keep 12 months
PIT:     restore window 7 days
~~~

### 6.1. Key Constraints

Per MongoDB Atlas docs:

- Retention must **not be shorter** than its corresponding frequency unit.
- Less frequent tiers require retention equal to or longer than more frequent tiers per policy rules.
- The PIT restore window **cannot exceed** hourly snapshot retention.
- When a snapshot matches multiple policy items, it inherits the longest matching retention.
- Reducing frequency or retention affects existing and future snapshots per specific rules; do not assume changing one setting immediately purges every older copy.

### 6.2. Do Not Confuse Snapshot Age With the PIT Window

Keeping monthly snapshots for 12 months **does not** mean you can PITR to any second over 12 months. PIT depends on the **restore window and oplog data**.

### 6.3. Clocks and Timezones

Atlas backup policies operate in UTC. Teams operating in Vietnam local time must convert timestamps when scheduling and analyzing incidents.

Example:

~~~text
18:00 UTC = 01:00 next day in Vietnam (UTC+7)
~~~

Never add UTC+7 onto a stored timestamp and treat the result as a new UTC time.

### 6.4. Reference Links

- Atlas Backup: `https://www.mongodb.com/docs/atlas/backup-restore-cluster/`.
- Manage Backup Policies: `https://www.mongodb.com/docs/atlas/backup/cloud-backup/configure-backup-policy/`.
- Backup Architecture: `https://www.mongodb.com/docs/atlas/architecture/current/backups/`.

## 7. Backup Compliance Policy and Anti-Tampering Retention

For strict audit requirements, Atlas offers **Backup Compliance Policy** on eligible deployments.

The policy enforces baseline minimums across project clusters and blocks actions that weaken backup retention:

- Cannot arbitrarily delete protected snapshots.
- Cannot shorten retention after a protected snapshot has been taken.
- Cannot arbitrarily disable Cloud Backup.
- Cannot shrink the PIT restore window below compliance minimums.
- Cannot casually disable the compliance policy without formal verification/support workflows.

### 7.1. Important: This Decision Is Hard to Reverse

MongoDB requires a formal process through MongoDB Support with designated legal/security representatives to review disabling or relaxing certain controls. It is not a toggle a Project Owner flips casually.

Before enabling, verify:

1. Statutory retention obligations.
2. Backup storage costs.
3. Workflows for handling privacy deletion requests.
4. Designated security/legal representatives for verification.
5. Recovery procedures and access paths.
6. Management of retained snapshots on terminated clusters.

### 7.2. "Immutable" Differs From "Undeletable by Any User"

A snapshot may be immutable in the sense that its **bytes cannot be modified**, yet an authorized user can still **delete** it. A compliance policy adds protection against deletion and retention reduction. Clarify exactly which protections are active.

### 7.3. Extra Snapshot Retention

Atlas may retain copies beyond the compliance-protected period. During extended retention, certain deletion protections may differ from the compliance-enforced period. Never write blanket claims like "all snapshots are permanently immutable" if configs have phased stages.

### 7.4. Tier/Version Support

Backup Compliance Policy applies to specific cluster classes—typically dedicated M10+ per Atlas docs; never apply one generic runbook across Free/Flex/Infinite without checking deployment specifics.

## 8. The 3-2-1-1-0 Rule and Offsite Backups

A design principle stronger than "save an extra file":

- **3**: at least three copies of data, including production.
- **2**: at least two distinct storage media or independent failure modes where appropriate.
- **1**: at least one offsite copy.
- **1**: at least one immutable or offline/air-gapped copy.
- **0**: zero errors detected after backup verification and restore testing.

~~~text
                   Production MongoDB
                           |
                +----------+----------+
                |                     |
                v                     v
      Same-region snapshot      Offsite encrypted copy
                |                     |
                v                     v
           Fast restore          Immutable retention
                |                     |
                +----------+----------+
                           |
                           v
                       Restore drill
~~~

### 8.1. Permission Independence Matters as Much as Location Independence

If a production operator can delete both the source database and all backup buckets/KMS keys, one compromised account can destroy every copy even across two regions.

Separate:

- Production administration.
- Backup writing.
- Backup deletion.
- Backup recovery.
- KMS administration.
- Compliance/retention overrides.

### 8.2. Cross-Region Alone May Not Be Enough

If the same IAM role holds delete rights in both regions, the second copy can still be wiped simultaneously. For high-impact threat models, consider **cross-account isolation**, **separate credentials**, immutable retention, and multi-party approval.

### 8.3. Verify the Offsite Copy Is Actually Usable

A cross-region copy is meaningful only when:

- Required metadata and data are completely replicated.
- KMS keys are accessible in the target restore region.
- A restore target can be provisioned.
- Network/IAM permissions are configured.
- Drills have been run in the secondary region/account.

## 9. Immutability: Preventing Modification and Deletion During Retention

An immutable/WORM (*Write Once Read Many*) copy is protected from alteration during its retention window, depending on technology and policy.

Technologies can include:

- Atlas Backup Compliance Policy.
- Cloud object storage Object Lock / immutable bucket policies.
- Storage-system snapshot locks.
- Backup vault locks or equivalent mechanisms.
- Offline copies rarely connected to the network.

### 9.1. Governance Mode vs. Compliance Mode

Some cloud object stores offer multiple lock modes. One mode may let a privileged principal bypass retention, while a stricter mode blocks everyone. Inspect exact cloud semantics rather than labeling every retention setting "absolute immutability."

### 9.2. "Immutable" Cannot Fix Destroyed Secrets/KMS Keys

If the backup file cannot be deleted yet the decryption key is lost, you still cannot restore.

~~~text
Immutable backup + destroyed key = data potentially unrecoverable
~~~

Protect **decryptability** independently from byte retention.

### 9.3. Backup Encryption Alone Does Not Stop Ransomware

An attacker with backup-delete permissions can delete encrypted files too. Encryption and immutability protect different security properties.

### 9.4. Test Locks Carefully for Cost Impact

Enabling strict retention locks across an entire backup store can prevent deleting test or leftover data, creating unexpected bills and legal conflicts. Test on an isolated bucket/project first.

## 10. Encryption Layers Across the Backup Lifecycle

There are at least four trust boundaries:

~~~text
1. MongoDB storage (at rest)
          |
2. MongoDB -> backup worker (TLS)
          |
3. Backup worker -> object storage (TLS)
          |
4. Backup object at rest (KMS / client encryption)
          |
5. Object -> restore worker (TLS + decrypt)
~~~

### 10.1. TLS in Transit

When backup tools connect to MongoDB, enforce `tls=true` with server certificate/CA and hostname validation. Never disable TLS validation just to get a backup job running.

Uploads from backup workers to cloud object storage must also use TLS with endpoint and certificate-chain verification.

### 10.2. Database Encryption at Rest Does Not Encrypt Logical Exports

Atlas encrypts data at rest by default, yet an **exported logical BSON dump** is readable by anyone holding the file.

Never assume that because a WiredTiger volume is encrypted, `mongodump` output is automatically encrypted with a key. Protect exported files separately.

### 10.3. Encryption at Rest in Backup Storage

With object storage, server-side encryption via KMS (SSE-KMS or equivalent) encrypts objects at rest at the provider—yet any principal holding both object read and KMS decrypt permissions receives plaintext.

### 10.4. Client-Side Backup Encryption

To prevent even storage-service admins from reading plaintext, encrypt the file/stream **prior to upload** using an organization-approved tool.

Example:

~~~text
mongodump BSON stream
        |
        v
    gzip compression
        |
        v
client-side encryption
        |
        v
private object storage
~~~

Use authenticated encryption or a solution with explicit integrity verification. Never roll custom ciphers or weak ZIP passwords.

### 10.5. Two Encryption Layers Can Coexist

Backup files encrypted client-side can sit inside an SSE-KMS bucket. Two layers enforce separation of duties while adding key/restore complexity. Document where each key lives, who can decrypt, and how recovery works if KMS is disrupted.

## 11. KMS, CMK, and Envelope Encryption

A key-management model:

~~~text
Backup BSON/archive
       |
       v
Data Encryption Key (DEK)
       |
       v
Encrypted archive
       |
       +--> DEK wrapped by Customer-Managed Key (CMK)
                                      |
                                      v
                                   Cloud KMS
~~~

**Envelope encryption** uses a DEK to encrypt data, while a CMK inside KMS wraps the DEK. Keeping the CMK inside KMS avoids distributing raw master keys.

### 11.1. KMS Key Lifecycle Must Span Backup Retention

Suppose:

~~~text
Backup snapshot from 2025
Encrypted using KMS key-version K1
Retention until 2030
~~~

If K1 is destroyed before 2030, the backup becomes unrecoverable even though the object still exists.

### 11.2. Rotation Differs From Destruction

- **Rotate:** add a new key version for newer data/backups.
- **Disable:** temporarily block key usage, which can break restores.
- **Revoke permissions:** restrict which principals can decrypt.
- **Destroy/delete key:** can render backups permanently unreadable.

Never lump all of these under a single "rotate keys" checkbox.

### 11.3. Inventory Keys With Backup Time

Non-secret metadata can record:

~~~json
{
  "backupId": "orders-2026-11-14T00:00:00Z",
  "encryptionMethod": "client-envelope-plus-kms",
  "kmsKeyRef": "alias/backup-key-prod",
  "keyVersionRef": "version-at-backup-time",
  "restoreTested": true
}
~~~

Never write plaintext DEKs/CMKs into manifests. Also protect sensitive topology/namespace metadata if it could aid attackers.

### 11.4. Verify Decryption Before Retiring Old Keys

Every key rotation should test restoring a backup encrypted with the **old key** and one encrypted with the **new key**, especially across account, region, or KMS provider migrations.

## 12. How Does MongoDB Atlas Encrypt Snapshots?

Per MongoDB Atlas documentation:

- Backup snapshots are encrypted at rest via standard cloud-provider mechanisms.
- When **Encryption at Rest using Customer Key Management** is enabled, Atlas adds customer KMS encryption appropriately.
- During restores, snapshot data is transferred over TLS.
- Snapshots and PIT oplogs depend on the keys active at creation time.
- Snapshots encrypted with revoked or inaccessible keys may be unrestorable.

### 12.1. Do Not Confuse Atlas-Managed Encryption With Exports Outside Atlas

Atlas-managed backups use Atlas's encryption architecture. Any file exported to a laptop or external backup server requires its own encryption and storage policy.

### 12.2. KMS Outages Can Block Restores

If your organization revokes a key or modifies IAM grants for Atlas KMS integration, restores can fail. Treat CMK modifications as **disaster recovery changes**, not purely security tweaks.

### 12.3. Recovery Readiness Includes Key Readiness

A report saying "snapshots available = 120" does not prove recoverability if KMS principals lack decrypt grants. Restore drills must exercise the exact KMS/trust path planned for real incidents.

## 13. Encryption Is Not Just Confidentiality—Verify Integrity Too

Distinguish three properties:

- **Confidentiality:** contents are unreadable without the key.
- **Integrity:** detects altered or corrupted contents.
- **Availability:** backups, keys, and infrastructure are accessible for restore.

A SHA-256 checksum detects corruption relative to the original file if stored and verified securely, yet **does not** substitute for authenticated encryption. An attacker controlling both file and checksum storage can modify both.

### 13.1. What Can a Manifest Protect?

A manifest can store:

~~~json
{
  "backupId": "orders-2026-11-14T00:00:00Z",
  "sourceEnvironment": "production",
  "snapshotStartUtc": "2026-11-14T00:00:00Z",
  "backupType": "logical-full",
  "encryptedObject": "orders/2026/11/14/archive.gz.gpg",
  "checksumAlgorithm": "SHA-256",
  "status": "verified"
}
~~~

Sign or protect manifests with independent access/integrity controls. Never mark `status:"verified"` merely because upload finished.

### 13.2. Compression and Encryption Order

Normally **compress first, encrypt second**. Encrypted data compresses poorly. In streaming pipelines, check exit status across every stage so a truncated encrypted file is never accepted.

### 13.3. Checksums Do Not Replace Restore Tests

A backup with a valid checksum yet missing collections or written by an incompatible tool version can still fail restoration. A test restore is far stronger proof.

## 14. Four-Layer Access Control: MongoDB, Atlas, Backup Store, KMS

Having `readWrite` inside a database does not grant snapshot download rights; conversely, someone allowed to restore backups can access vast sensitive data.

### 14.1. Four Layers

~~~text
Application MongoDB RBAC
        |
        v
Backup control plane (Atlas/Ops Manager)
        |
        v
Backup object store IAM/ACL
        |
        v
KMS decrypt permissions
~~~

A successful restore may require privileges across **all four layers**, depending on architecture.

### 14.2. Separation-of-Duties Matrix

| Role | Read DB for Backup | Write Backup | Delete Backup | Decrypt | Restore Prod |
|---|---|---|---|---|---|
| Backup agent | Yes, scoped | Yes | No | Typically encrypt only | No |
| Backup auditor | No | No | No | Not by default | No |
| Staging restore operator | Scenario-dependent | No | No | Yes with approval | No |
| Disaster recovery lead | With approval | Possible | Not by default | Via KMS authorization | Yes with change approval |
| Retention administrator | No | Policy management | Scoped/with approval | Not by default | No |
| KMS administrator | No | No | No | Key/policy admin; no default backup read | No |
| Application developer | Per app roles | No | No | No | No |

This is an **illustrative matrix**, not literal built-in role names in MongoDB/Atlas.

### 14.3. Preventing "Privilege Accumulation"

If a single principal holds object read, KMS decrypt, and external network egress, it can exfiltrate backups. Enforce just-in-time access, auditing, MFA, approvals, and network restrictions.

### 14.4. Restore Operators Can Read More Data Than Normal Users

Restoring into a cluster they control lets an operator read every collection, even if they lacked `read` privileges on the source DB. Hence restore permissions are highly sensitive.

## 15. MongoDB Built-In `backup` and `restore` Roles on Self-Managed

MongoDB provides built-in roles:

- `backup` in `admin`: privileges needed to perform common `mongodump` operations on covered data.
- `restore` in `admin`: privileges to restore data within supported scope.

Creating an illustrative backup principal in a self-managed lab:

~~~javascript
use admin

db.createUser({
  user: "backup_agent",
  pwd: passwordPrompt(),
  roles: [
    { role: "backup", db: "admin" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

### 15.1. Do Not Use `root` for Routine Backups

`root` can modify/delete data and users far beyond backup needs. Use a dedicated account and never reuse production application credentials.

### 15.2. Restores May Require Additional Privileges

Certain restore operations require privileges beyond the `restore` role, for instance:

- Restoring metadata tied to `system.profile` has special requirements.
- `mongorestore --oplogReplay` has strict requirements: MongoDB docs note a user-defined role with `anyAction` on `anyResource` is required for that scenario.

**This is an extremely broad privilege.** Never grant it casually just to "make it work"; run only on an isolated target under formal approval and a complete restore runbook.

### 15.3. Separate Backup and Restore Principals

A backup agent should only **read source** and **write to the object store**, with zero rights to run `mongorestore --drop` on production. Restore operators should receive time-bound privileges only for approved incidents.

### 15.4. Atlas Uses a Different Database User Mechanism

On MongoDB Atlas, manage database users/roles through Atlas's supported interfaces. Do not run `db.createUser()` directly and expect Atlas user management to mirror self-managed behavior.

## 16. Atlas Backup Roles and Operational Privileges

Depending on operation/API path, Atlas distinguishes project-level roles such as:

- **Project Read Only**: views eligible backup info and policies.
- **Project Backup Creator**: creates and performs certain snapshot management actions per docs.
- **Project Backup Manager**: broader management of backup/restore tasks.
- **Project Backup Recovery Operator**: initiates restore jobs in supported scenarios.
- **Project Owner**: broad administrative control.

Per Atlas docs, **initiating a restore job** requires an appropriate role such as Project Backup Recovery Operator, Project Backup Manager, or Project Owner. Cross-project/cross-organization restores require privileges on both source and target—typically Project Backup Manager/Project Owner depending on scenario.

### 16.1. No Single "Backup Admin" Covers Every API

Certain endpoints (such as triggering on-demand snapshots via API) have specific role requirements. Always read the **Required Access** page for the exact action before writing automation.

### 16.2. Separate Approvers From Restore Executors

A cluster-level restore into a target cluster can **wipe all existing data** on that target. Require formal approval, target verification, and safeguards against targeting production by mistake.

### 16.3. Atlas Authorization Best Practices

- Use project-specific roles instead of defaulting to Organization Owner.
- Dedicated API/service accounts for automation.
- Restrict snapshot deletion permissions unless required.
- Enforce MFA/SSO and auditing for operators.
- Use just-in-time recovery privileges.
- Review role assignments periodically.

## 17. Storage Repository Permissions: Read, Write, Delete, and Immutability

For self-managed backups in object storage, separate actions:

- **Write:** upload new objects.
- **Read/List:** list and download copies.
- **Delete:** delete objects/versions.
- **Change retention:** shorten retention or bypass locks.
- **Manage encryption keys:** grant/revoke/disable CMKs.

### 17.1. Backup Writers Do Not Need Delete

An automated backup account normally only needs to write objects to new unique paths and verify completion. Limiting delete rights protects historical backups if that account is compromised.

### 17.2. Partition by Application and Environment

Example object path hierarchy:

~~~text
backups/
  production/
    orders/
      2026/11/14/...
    catalog/
      2026/11/14/...
  staging/
    orders/
      ...
~~~

Prefix partitioning organizes access, yet paths alone are **only names**; enforce boundaries via bucket policies/IAM, not just naming conventions.

### 17.3. Avoid Public ACLs

MongoDB backups can hold complete PII, financial records, and accidentally stored secrets. Never make buckets/objects public or issue overly long-lived pre-signed URLs.

### 17.4. Deletions Need Approvals and Retention Protection

If business rules expire old backups automatically, lifecycle rules must respect object locks and legal holds. A lifecycle rule must never silently purge copies protected by mandatory retention.

## 18. Illustrative IAM Policy Example for Object Storage

A backup writer using object storage should hold only minimal permissions. Pseudocode:

~~~json
{
  "role": "mongo-backup-writer-prod",
  "resource": "backup-bucket/production/orders/*",
  "allow": [
    "ListAuthorizedPrefix",
    "WriteNewBackupObject",
    "ReadOwnWriteMetadata"
  ],
  "deny": [
    "DeleteBackupObject",
    "BypassObjectRetention",
    "ChangeBucketPolicy",
    "DisableKmsKey"
  ]
}
~~~

**This is a permission model, not valid AWS/GCP/Azure IAM JSON.** Translate into exact provider actions, resources, and condition keys, and verify effective permissions.

### 18.1. Why Include Explicit Denies?

If a principal accidentally inherits a broader role elsewhere, explicit denies act as guardrails in IAM systems that support them. Always verify policy evaluation precedence in your provider.

### 18.2. Separate KMS Grants

A backup writer using client-side public-key encryption can encrypt without holding the private decryption key. With KMS envelope encryption, it needs data-key generation/wrapping calls—**not** default decryption rights across all historical backups.

Restore operators receive `Decrypt` on relevant key versions only with approval and auditing.

## 19. `mongodump` Scenario: Logical Backup on Self-Managed MongoDB

### 19.1. Prerequisites Before Running

- Compatible MongoDB Database Tools version.
- Network/TLS/backup user with proper privileges.
- Verified deployment type: standalone, replica set, or sharded.
- Sufficient disk capacity and protected backup store.
- Plan to avoid leaving plaintext backups on the host.
- Exit code checks and alerting.
- Never use an illustrative single command as the backup strategy for a large sharded cluster.

### 19.2. Basic Dump for a Small Lab

Example backing up `backup_lab` on self-managed MongoDB; not guaranteed consistent under concurrent writes:

~~~bash
mongodump \
  --host db1.example.test \
  --port 27017 \
  --tls \
  --username backup_agent \
  --authenticationDatabase admin \
  --db backup_lab \
  --archive=backup_lab.archive.gz \
  --gzip
~~~

Omitting the password from the command line allows Database Tools to prompt interactively per configuration/version. In automation, use tool-supported secret injection and keep passwords out of process arguments and logs.

**Warning:** `backup_lab.archive.gz` is a compressed BSON dump, **not encrypted** merely because `--gzip` was passed.

### 19.3. Compression Is Not Encryption

~~~text
--gzip    = compression
--archive = output format
--tls     = encryption in transit
~~~

Never carelessly label a `.gz` file an "encrypted backup."

### 19.4. Backing Up One Database May Be Insufficient

Applications can depend on users/roles, indexes, cluster configuration, external secrets, object store files, and application code/config. Logical dumps do not capture dependencies outside MongoDB.

## 20. Consistent Replica Sets: `--oplog` and `--oplogReplay`

For a **self-managed replica set member**, `mongodump --oplog` captures oplog entries occurring during the dump to produce a point-in-time consistent backup when prerequisites are met.

Example for an **entire replica set**, not a single database:

~~~bash
mongodump \
  --host rs-member.example.test \
  --port 27017 \
  --tls \
  --username backup_agent \
  --authenticationDatabase admin \
  --oplog \
  --archive=full-rs.archive.gz \
  --gzip
~~~

### 20.1. Requirements for `--oplog`

MongoDB docs require when using `--oplog`:

- **Full dump** of a replica set member.
- Do not combine with `--db`, `--collection`, `--query`, or other scope-limiting flags.
- Do not use through `mongos` to back up an entire sharded cluster.
- Concurrent DDL/user/role/cluster-policy changes during dump can cause failure.
- Compatible tool and server versions.

Specifically, upgrading Feature Compatibility Version across a time-series format conversion mid-backup can prevent `mongorestore --oplogReplay` from replaying that oplog segment per current version warnings.

### 20.2. Restoring in an Isolated Lab

~~~bash
mongorestore \
  --host restore-lab.example.test \
  --port 27017 \
  --tls \
  --username restore_agent \
  --authenticationDatabase admin \
  --archive=full-rs.archive.gz \
  --gzip \
  --oplogReplay
~~~

**Run only on a properly prepared isolated restore lab target.** `--oplogReplay` requires broad privileges, and restoring data/users/roles can alter target authentication.

### 20.3. Do Not Use `--drop` Recklessly

`mongorestore --drop` drops matching collections on the target before restoring. When the dump includes the `admin` database, dropping/restoring can overwrite users/roles and lock out authentication mid-run.

Never test directly against production. Use a dedicated target cluster for restore drills.

## 21. Sharded Clusters: Consistency Must Span Shards

A sharded MongoDB cluster has:

~~~text
mongos
  |
  +--> Shard A replica set
  +--> Shard B replica set
  +--> Config server replica set
~~~

Dumping each shard at arbitrary times **does not automatically create** a globally consistent snapshot when transactions and migrations run concurrently.

### 21.1. Why Isn't `--oplog` Enough?

MongoDB docs state `mongodump --oplog` **cannot back up an entire sharded cluster via `mongos`**. Nor does `mongorestore --oplogReplay` support sharded clusters the way it does full replica-set dumps.

### 21.2. Recommended Approach

- Prefer Atlas/Cloud Manager/Ops Manager or a compatible coordinated backup solution.
- If self-managing a sharded cluster, follow MongoDB's exact guides on coordinated dumps, consistency, balancer/chunk migrations, and transaction timing.
- Never glue separate dump files together and call them a "cluster-wide point-in-time backup" without coordination.
- Test restores must verify cross-shard data, indexes, and application behavior.

## 22. Encrypting `mongodump` Output With Approved Tools

A self-managed file backup workflow can stream → compress → encrypt, avoiding plaintext archives on intermediate disks.

**Conceptual example** using GPG public-key encryption on Linux/macOS, assuming the backup recipient's public key is already imported:

~~~bash
set -o pipefail

mongodump \
  --host rs-member.example.test \
  --port 27017 \
  --tls \
  --username backup_agent \
  --authenticationDatabase admin \
  --oplog \
  --archive \
  --gzip \
  | gpg --batch --encrypt \
      --recipient backup-archive-recipient \
      --output full-rs-2026-11-14.archive.gz.gpg
~~~

Notes:

- `backup-archive-recipient` identifies a provisioned, verified public key—not a hardcoded password.
- `mongodump` still receives its auth secret via a secure channel.
- `set -o pipefail` surfaces errors from **any stage in the pipeline** in Bash rather than checking only GPG's exit code.
- GPG outputs must live in private storage with integrity checks.
- Production pipelines also require stdout/stderr redaction, disk quota checks, and upload retries.

### 22.1. Should You Use GPG in Production?

Possibly, if your organization maintains full key lifecycles, recovery procedures, and tool hardening. This is not saying "GPG is always best"; cloud KMS envelope encryption or backup tools with native key management may fit better.

### 22.2. Never Keep the Private Key on the Same Host as Sole Protection

If the private decryption key resides on the same backup host and an attacker compromises that host, encryption at rest provides no boundary.

### 22.3. Upload Over TLS With Dedicated IAM

After creating the encrypted file, upload over TLS to a private bucket using a workload identity permitted only to write new objects—unable to delete or bypass retention.

## 23. Verifying Encrypted Backups Without Restoring Into Production

After backup and upload:

1. Verify file/object size.
2. Check job/pipeline exit codes.
3. Compute ciphertext checksums.
4. Write a protected manifest.
5. Verify decryption keys/certificates work in the recovery environment.
6. Inspect archive headers/schemas if applicable.
7. Restore into an isolated test cluster.
8. Run data and application checks.

### 23.1. Hashing the Encrypted File

Example:

~~~bash
sha256sum full-rs-2026-11-14.archive.gz.gpg
~~~

Store the checksum with the backup ID in an integrity-protected manifest. Matching hashes prove identical bytes, not valid business data.

### 23.2. Testing Decryption With GPG

In a recovery environment holding the valid private key:

~~~bash
gpg --decrypt \
  --output restored.archive.gz \
  full-rs-2026-11-14.archive.gz.gpg
~~~

The intermediate output is a **plaintext compressed BSON archive**; store it in a restricted folder and securely wipe it after restore. To avoid intermediate files, use streaming decryption with strict permissions and pipeline status checks.

### 23.3. Restore Drill Into an Isolated Target

~~~bash
mongorestore \
  --host isolated-restore.example.test \
  --port 27017 \
  --tls \
  --username restore_agent \
  --authenticationDatabase admin \
  --archive=restored.archive.gz \
  --gzip
~~~

For archives containing an oplog, perform full `--oplogReplay` only when test topology and privileges meet requirements. Never carry this command over to production without a formal restore plan.

### 23.4. Using `--dryRun` as a Secondary Check

`mongorestore --dryRun` on supported versions summarizes the restore plan without writing data. However, dry runs **do not replace** verifying decryption, data integrity, and application consistency in a real restore.

## 24. Access Control Policy for Restore Workflows

Restoring into an empty cluster is a very different workflow from **overwriting** a populated cluster.

### 24.1. Restore Targets Must Be Chosen Explicitly

Before restoring, confirm:

- Exact target project/cluster/database.
- Is it serving live users?
- What data will be deleted or overwritten?
- Does the restore include users/roles?
- Could application endpoints accidentally point at the target?
- Is there namespace mapping from backup to staging?
- Are KMS/trust/decrypt permissions present?
- Are restore verification and rollback plans ready?

### 24.2. Atlas Cluster-Level Restores Can Replace the Entire Target

MongoDB Atlas docs state that for cluster-level restores, existing data on the target cluster may be deleted prior to restore and the target becomes unavailable during the job. Treat this operation as a **high-impact change**.

### 24.3. Approval With Separation of Duties

Example:

~~~text
Incident Commander -> requests recovery
Security/DBA Lead  -> approves access grants
Recovery Operator  -> executes restore job
Application Owner  -> validates business state
Auditor            -> archives evidence
~~~

Never allow one unsupervised account to alter retention, delete backups, fetch keys, restore onto production, and purge audit logs.

### 24.4. Just-in-Time Restore Access

Decrypt/restore privileges should be granted per incident/time window where practical, auto-expire, and be audited. Break-glass access requires on-call oversight and post-incident revocation.

## 25. Test Restores: What Must Be Verified?

Tool-level restore completion is not enough. Build an **acceptance suite**.

### 25.1. Technical Checks

- Cluster is online and all members are healthy.
- Expected collections exist.
- Indexes are created and finished building.
- Counts show no abnormal gaps.
- Sample documents exist.
- Cross-collection references are valid.
- Roles/users follow policy.
- No missing keys leave field-level ciphertext unreadable.

### 25.2. Business Checks

For an ordering system, verify:

- Orders and paired payments hold valid states.
- No orders restored without line items.
- Product/SKU references exist.
- Timestamps and timezones match expectations.
- Test read/write requests succeed.
- External integrations do not emit uncontrolled duplicate events.

### 25.3. Checking Whether RPO/RTO Were Met

Sample report:

~~~text
Recovery point available: 2026-11-14 10:24:30 UTC
Failure detected:         2026-11-14 10:25:00 UTC
Service available:        2026-11-14 11:02:00 UTC

Observed data gap: 30 seconds
Observed restore duration: 37 minutes
~~~

Measure against evidence-backed timestamps. Against a 5-minute RPO and 60-minute RTO, timing passes—yet data acceptance checks are still required.

### 25.4. Drill Schedule

- Test a recent scheduled backup.
- Test a 30/90-day-old backup to verify key retention.
- Test PIT near a simulated DDL/incident event.
- Test cross-region/cross-account restores.
- Test recovery when a privileged backup credential is revoked.
- Test when an older KMS key version is required.

Never test only by restoring a freshly created file onto the exact host that wrote it.

## 26. Retention vs. Data Deletion Obligations

Backup retention can conflict with personal-data erasure requests. Immutable copies retain data from before deletion.

### 26.1. Never Claim Deleting From Production Deletes From Backups

~~~text
Day 1: Document containing PII is backed up
Day 3: User requests deletion; production deletes it
Day 4: Day 1 backup still contains the PII
~~~

A sound policy must define:

- Legal basis for retaining backups.
- Minimum and maximum retention periods.
- Who may access backups and for what purpose.
- Handling erasure requests against immutable backups.
- Procedures to **reapply deletions** if an older backup is restored.
- Purging copies once retention expires.

### 26.2. Restores Can Resurrect Deleted Data

If Day 1's backup is restored on Day 7, documents deleted on Day 3 reappear. Maintain a deletion ledger/tombstones or a policy-compliant suppression pass before exposing restored data to users.

### 26.3. Legal Holds

A legal hold may require retaining data past standard schedules. It must be formally approved with defined scope, owner, expiry reviews, and strict access control—never retain all backups forever "just in case."

### 26.4. Avoid Hardcoding Universal Legal Timelines

Laws, industries, jurisdictions, and contracts set varying timelines. This is a technical guide; real compliance retention requires alignment with organizational policy and qualified legal counsel.

## 27. Cross-Region Recovery and Failure Domains

Region A suffers a prolonged outage:

~~~text
Primary Atlas cluster (Region A)
          |
     Backup snapshots
          |
          v
     Copy Region B
          |
          v
   Target Cluster Region B
          |
          v
  Application traffic cutover
~~~

### 27.1. A Cross-Region Copy Does Not Automatically Restore Traffic

You still need:

- Target restore cluster.
- Network endpoints, VPC peering, or private links.
- Secrets and database users.
- KMS grants in the target region/account.
- DNS/service discovery cutover.
- Application compatibility.
- Forward-recovery or rollback runbooks.

### 27.2. Do Not Put Every Key in One Failure Domain

If Region A goes down and the KMS key is only accessible in Region A, Region B backups may fail to decrypt. Test cross-region/cross-provider KMS resilience explicitly.

### 27.3. Copy Retention Can Differ From Source

Atlas supports snapshot distribution/copies per policy, with specific retention limits on copied snapshots. Never assume a cross-region copy stays retained longer than source without configuring and verifying it.

## 28. Storage Costs and Optimizing Retention

Backup cost is more than snapshot count:

- Baseline size and daily change rate.
- Incremental snapshot dependencies.
- Snapshot frequency.
- PIT/oplog retention.
- Cross-region/cross-account copies.
- Data egress/transfer and restore compute.
- KMS API operations.
- Immutable long-term storage.
- Restore drill environments.
- Object versioning and storage classes.

### 28.1. Rough Estimate for Logical Full Backups

Suppose each encrypted full archive is 100 GB, taken daily, retained 30 days:

~~~text
100 GB x 30 = 3,000 GB ~ 3 TB
~~~

This excludes index metadata, replication, cross-region copies, object versions, and data growth. Atlas snapshots are typically incremental, so **never** calculate Atlas costs simply by multiplying full cluster size by snapshot count.

### 28.2. Longer Retention Is Not Automatically Safer

Keeping backups for a year without proven restore capability, missing keys, or shared deletion permissions with production remains fragile. Optimize around RPO/RTO, legal duties, and verified recoverability.

### 28.3. Cold Archives

Long-term cold archives cost less per GB, yet retrieval/rehydration is often slow and incurs retrieval fees. With a 1-hour RTO, never place your **only copy** in a tier taking hours just to thaw.

## 29. Automated Backup Pipeline: End-to-End Controls

A solid pipeline:

~~~text
Scheduler
   |
   v
Acquire workload identity
   |
   v
Read source / Snapshot
   |
   v
Compress -> Encrypt
   |
   v
Upload immutable destination
   |
   v
Verify checksum / manifest
   |
   v
Register backup catalog
   |
   v
Scheduled isolated restore test
   |
   v
Alert / Retention lifecycle
~~~

### 29.1. Job States

At minimum:

~~~text
STARTED
CAPTURED
ENCRYPTED
UPLOADED
VERIFIED
RESTORE_TESTED
EXPIRED
FAILED
~~~

Never mark `VERIFIED` right after `UPLOADED`.

### 29.2. Never Leak Secrets Into Commands or Logs

- Never print full MongoDB URIs with credentials.
- Never print cloud storage access keys.
- Never log plaintext backups.
- Never print KMS key material.
- Never bundle private-key PEMs into CI artifacts.
- Disable core dumps or lock down access when secrets sit in memory.

### 29.3. Pipeline Exit Status

In shell pipelines, catch failures from `mongodump` as well as encryption/upload tools. Checking only the last command can produce an encrypted empty/truncated file while reporting success.

### 29.4. Idempotency

Backup IDs/filenames should be unique and manifest-tracked; retries must never overwrite a good copy with a broken file. If the same backup ID runs twice, define strict checksum, upload-condition, and object-versioning rules.

## 30. Observability and Alerting

### 30.1. Metrics

- `last_successful_backup_timestamp`.
- `last_verified_recovery_point`.
- `backup_job_duration_seconds`.
- `backup_artifact_bytes`.
- `backup_upload_errors_total`.
- `restore_drill_last_success_timestamp`.
- `restore_drill_duration_seconds`.
- `backup_objects_without_manifest`.
- `unreadable_encryption_key_count`.
- `retention_policy_violations`.
- `snapshot_delete_attempts`.
- `failed_kms_decrypt_requests`.

These names are **illustrative application/observability metrics**, not built-in metrics exported by MongoDB.

### 30.2. Practical Alerts

- No new verified backup within 2× the backup interval.
- PIT window shorter than the business RPO requirement.
- Restore test failure.
- Certificate or KMS errors.
- Unexpected snapshot deletions.
- Access policy wider than baseline.
- Immutable object lock missing on new artifacts.
- Offsite copy lag exceeding acceptable thresholds.
- Backup catalog out of sync with actual stored objects.

### 30.3. Audit Trail

Who changed retention? Who downloaded a backup? Who called KMS Decrypt? Who initiated a restore? Who deleted a snapshot? Logs must capture identity, timestamp, resource, outcome, and change/incident ID without leaking secrets.

## 31. Runbook for Recovery After Accidental Deletion

Suppose at 10:25 an operator discovers data was deleted from the database.

1. **Contain:** stop further destructive writes and preserve audit logs.
2. **Identify:** pinpoint the faulty operation's timestamp and affected collections/tenants.
3. **Select point:** pick a PIT right before the operation if within the window.
4. **Verify:** confirm valid snapshot/oplog and accessible KMS keys.
5. **Choose target:** prefer an isolated recovery cluster; avoid overwriting production unnecessarily.
6. **Authorize:** obtain restore and decrypt approvals.
7. **Restore:** execute per Atlas/backup tool runbook.
8. **Validate:** verify counts, indexes, and application invariants.
9. **Reconcile:** reapply valid updates occurring after the recovery point if needed.
10. **Cutover:** switch traffic under controlled checks.
11. **Audit:** record actual RPO/RTO and root cause.
12. **Improve:** update policies, permissions, and drills.

### 31.1. Pre-Error PIT Is Not Always the Whole Answer

Restoring to 10:24 can roll back valid transactions committed after 10:24. Plan reconciliation for valid writes—especially payments and external integrations.

### 31.2. Restoring to a Separate Target

For most drills and investigations, isolated restores let you inspect discrepancies before touching production, and minimize the risk of overwriting live data.

## 32. Ransomware and Compromised Backup Operators

What can a compromised backup writer account do?

If it holds:

~~~text
read database + write backup + delete backup + disable KMS
~~~

an attacker can exfiltrate data and destroy recoverability.

### 32.1. Defensive Architecture

- Writers only create new backups; never delete.
- Retention/immutability cannot be bypassed by writers.
- KMS admins are separate from backup writers.
- Backup copies reside in independent accounts/regions.
- Audit/KMS logs ship to a separately privileged sink.
- Restore operators hold temporary privileges requiring approval.
- Backup catalogs and manifests carry integrity protection.

### 32.2. When Compromise Is Detected

1. Revoke credentials/access tokens.
2. Audit read, delete, and KMS key activities.
3. Verify how many immutable/offsite copies remain intact.
4. Rotate all related credentials.
5. Run restore drills from trusted copies.
6. Investigate potential PII exfiltration.
7. Preserve evidence and investigate per incident policy.

Never just run a fresh backup and consider the incident closed.

## 33. Sample Policy in YAML Format

This is an **illustrative organizational policy document**, not YAML directly applicable to Atlas or MongoDB.

~~~yaml
policyId: mongo-orders-prod-v1
owner: platform-backup-team
dataClassification: confidential
source:
  platform: mongodb-atlas
  project: orders-prod
  deployment: dedicated
objectives:
  rpoMinutes: 5
  rtoMinutes: 60
backup:
  continuousPIT: true
  pitRestoreWindowDays: 7
  schedules:
    - frequency: hourly
      intervalHours: 6
      retentionDays: 7
    - frequency: daily
      retentionDays: 14
    - frequency: weekly
      retentionWeeks: 8
    - frequency: monthly
      retentionMonths: 12
  immutableCopy: true
  offsiteRegion: secondary-region
encryption:
  inTransitTLS: required
  atRest: managed
  customerManagedKey: enabled
access:
  backupWriterCanDelete: false
  restoreRequiresApproval: true
  kmsDecryptJustInTime: true
validation:
  verifyEveryBackup: true
  restoreDrillEveryDays: 30
  testOldKeyRecovery: true
retentionExceptions:
  legalHoldRequiresApproval: true
  handleDeletionRequests: true
~~~

### 33.1. Adapting the Policy Before Applying to Tooling

- Validate frequency vs. retention constraints in Atlas.
- Confirm Continuous Cloud Backup availability on the cluster tier.
- Measure actual RPO/RTO and cost.
- Map roles to IAM, Atlas, and DB RBAC.
- Define exact enforcement for `immutableCopy`.
- Confirm compatible storage regions and KMS grants.
- Translate abstract policy into concrete API/Terraform configs.

### 33.2. Periodic Policy Reviews

As a database grows from 100 GB to 5 TB, RTO changes even if the backup schedule stays identical. Test periodically and update targets and budgets.

## 34. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "Replica sets are backups" | Accidental deletes replicate; independent recovery points are needed |
| "Keeping 365 days means low RPO" | RPO depends on frequency/PIT and valid backups |
| "PIT window equals monthly retention" | PIT depends on oplog/restore window |
| "Having a backup file means it restores" | Integrity, keys, permissions, compatibility, and tests are required |
| "`mongodump --gzip` is encrypted" | gzip is compression |
| "DB TLS encrypts the dump file too" | TLS only protects data in transit |
| "Atlas backups aren't encrypted" | Atlas snapshots have encryption at rest |
| "CMKs can be deleted right after rotation" | Older snapshots may still need old keys |
| "Revoking a key doesn't affect backups" | Can render restores undecryptable |
| "An immutable snapshot can never be deleted" | Distinguish immutability from delete/retention protection |
| "An offsite region is always safe" | Shared IAM/KMS still creates a shared failure domain |
| "Backup writers need delete rights to clean up" | Separate lifecycle/deletion duties |
| "DB `readWrite` suffices to take Atlas snapshots" | Atlas control plane roles are a separate layer |
| "Atlas Project Owner implies KMS decrypt" | KMS grants/keys are a separate layer |
| "Restore users can hold all permissions" | Grant least privilege with approvals |
| "`mongodump --oplog` backs up whole sharded clusters" | Unsupported; requires coordinated backups |
| "`mongorestore --drop` is harmless" | Deletes target data and user metadata |
| "Job exit 0 proves recoverability" | Verify files, keys, and restore drills |
| "File hashes prove business correctness" | Checksums do not replace data validation |
| "Deleting from production deletes from backups" | Older backups can still hold PII |
| "More copies are always better" | Balance retention, cost, and privacy |
| "Restores automatically bring apps online" | Network, DNS, secrets, and app checks still apply |
| "5-minute RPO means 5-minute RTO" | Two independent targets |
| "You can test restores straight onto production" | Use an isolated target |
| "Keeping backups doesn't require keeping keys" | Losing keys loses decryption ability |
| "One account managing everything is simpler" | Huge blast radius and insider risk |

## 35. Practice Exercises

Exercises involving DDL or restores must run in an **isolated lab environment**. Never alter real Atlas Backup Compliance Policies or delete real backups for practice.

### Exercise 1 — Replicas vs. Backups

Why does a 3-node replica set fail to protect against a successfully replicated `db.orders.drop()`?

### Exercise 2 — RPO/RTO

Snapshot at 10:00, incident at 10:25, service restored at 11:10. What are observed RPO and RTO without PIT?

### Exercise 3 — GFS Retention

Design an hourly/daily/weekly/monthly schedule for a system requiring 14-day bug recovery and 12-month audit retention.

### Exercise 4 — PIT Window

If monthly snapshots are kept for 12 months while the PIT window is 7 days, can you restore to 11:59:59 on a day 8 months ago?

### Exercise 5 — Choosing Frequency

With a 15-minute RPO and no PIT, is a 6-hour backup sufficient? Why?

### Exercise 6 — Atlas Backup Policy

List the frequency tiers supported by Atlas. When a snapshot matches both daily and weekly policies, which retention applies?

### Exercise 7 — Compliance Protection

What actions does Backup Compliance Policy block? Why evaluate carefully before enabling?

### Exercise 8 — 3-2-1-1-0

Apply this principle to production MongoDB, offsite object storage, and restore drills.

### Exercise 9 — Permission Independence

Two backup copies sit in different regions yet share the same IAM role with delete permissions. Are these truly independent failure domains?

### Exercise 10 — TLS and File Encryption

Distinguish TLS connections, MongoDB encryption at rest, and encryption of exported BSON archives.

### Exercise 11 — gzip

Does `mongodump --archive --gzip` encrypt output? What protection layer is needed if stored outside Atlas?

### Exercise 12 — KMS

An older backup depends on CMK version K1. If K1 is destroyed, what happens?

### Exercise 13 — Integrity

What does hashing ciphertext detect? Why is storing the checksum alongside the attacker-modifiable file insufficient?

### Exercise 14 — Least Privilege

Distinguish permissions of a backup writer, backup restore operator, retention admin, and KMS admin.

### Exercise 15 — MongoDB Roles

Are the `backup` and `restore` roles in `admin` equivalent to Atlas Project Backup Manager?

### Exercise 16 — Oplog Replay

Why does `mongorestore --oplogReplay` require elevated privileges and why should it run only inside an approved runbook?

### Exercise 17 — Sharded Clusters

Why does dumping each shard at random times fail to yield a cluster-consistent backup?

### Exercise 18 — `mongodump --oplog`

Can `mongodump --oplog` be combined with `--db` or run via `mongos` to back up an entire sharded cluster? Explain.

### Exercise 19 — Restore Targets

List at least 5 checks before running `mongorestore --drop` or an Atlas cluster-level restore.

### Exercise 20 — Cross-Region and KMS

Offsite snapshots live in Region B while the CMK only serves Region A. What risk must be tested?

### Exercise 21 — Permission Matrix

Design a "create/list/read/delete/restore/decrypt" matrix for backup writer, auditor, restore operator, and retention admin.

### Exercise 22 — Restore Drill

Design a restore test for a 90-day-old backup including KMS verification and application invariant checks.

### Exercise 23 — Alerting

Define an alert when `last_verified_recovery_point` ages past RPO. Why isn't alerting on "job ran" enough?

### Exercise 24 — Personal Data

A user was deleted from production yet remains in a month-old backup. When restoring that backup, what must happen before reopening service?

### Exercise 25 — Legal Holds

When does a legal hold permit keeping data past normal retention? Who approves and reviews it?

### Exercise 26 — Object Lock

Ransomware tries to delete an encrypted object. Which permissions and controls must block it?

### Exercise 27 — Cost

30 compressed/encrypted full logical backups of 100 GB each: what is the raw data footprint excluding replication/copies?

### Exercise 28 — Incident Response

Backup writer credentials are leaked. List steps for revocation, verifying immutable copies, KMS, restores, and auditing.

### Exercise 29 — Atlas Restore Access

Which project roles can initiate a restore job? Why do cross-project restores check permissions on both source and target?

### Exercise 30 — End-to-End Policy

Design a policy with 5-minute RPO, 1-hour RTO, 7-day PIT, snapshot tiers, one immutable offsite copy, KMS key lifecycle, separated RBAC, and monthly restore drills. List components that must be benchmarked before production.

## 36. Production Readiness Checklist

### Recovery Objectives and Retention

- [ ] RPO/RTO approved by business owners.
- [ ] Backup mechanism matched to Atlas/self-managed topology.
- [ ] Hourly/daily/weekly/monthly/yearly retention tiers configured appropriately.
- [ ] PIT restore window satisfies requirements.
- [ ] PIT window clearly distinguished from archival retention.
- [ ] Owner, review cadence, and exception process defined.
- [ ] Legal hold and erasure-request workflows established.
- [ ] Retention and cross-region copy costs evaluated.

### Copies and Survivability

- [ ] Replication never treated as a backup substitute.
- [ ] Offsite copy and failure-domain separation active.
- [ ] Immutable/offline copy maintained as appropriate.
- [ ] Backup writer cannot delete historical backups.
- [ ] Retention lifecycle cannot illegally bypass locks.
- [ ] Manifests and integrity checks enforced.
- [ ] `last_verified_recovery_point` tracked continuously.

### Encryption and Keys

- [ ] TLS enforced on backup/restore traffic.
- [ ] gzip never confused with encryption.
- [ ] Backup archives outside Atlas encrypted.
- [ ] Key manager/KMS governed by strict RBAC.
- [ ] Older keys retained long enough to read historical backups.
- [ ] Recovery plan exists for KMS unavailability.
- [ ] Decryption tested on both newest and oldest copies.
- [ ] Plaintext, passwords, and private keys never logged.

### Access Control

- [ ] Database backup role and restore role separated.
- [ ] Atlas roles verified per exact API/action.
- [ ] Object writer/list/read/delete permissions separated.
- [ ] KMS decrypt not granted by default to all backup operators.
- [ ] Production restores require explicit approval.
- [ ] MFA/JIT/break-glass policies active.
- [ ] Audit logging covers read/decrypt/delete/restore events.
- [ ] No single shared account controls the entire backup chain.

### Recovery and Drills

- [ ] Restore tests automated or regularly scheduled.
- [ ] Isolated target and verification suite ready.
- [ ] RTO/RPO tested on production-scale datasets.
- [ ] Indexes, users/roles, and application invariants verified.
- [ ] Historical backup and cross-region restores tested.
- [ ] `--drop` never run in production tests.
- [ ] Replica set/sharded cluster consistency addressed.
- [ ] Runbooks ready for ransomware, accidental deletion, and KMS failure.
- [ ] Post-incident evidence and policy improvements tracked.

## 37. Summary

A trustworthy MongoDB backup policy combines **retention, encryption, access control, and verifiability**:

- **Retention:** choose frequencies and lifetimes based on RPO/RTO, audit needs, legal rules, and cost; distinguish snapshot tiers from the PIT restore window.
- **Atlas:** Cloud Backup, Continuous Cloud Backup, and Backup Compliance Policy provide managed controls for snapshots, recovery windows, and deletion protection on eligible tiers.
- **Self-managed:** `mongodump`/`mongorestore` are useful yet carry consistency limits, especially on sharded clusters; production needs coordinated workflows.
- **Immutability:** offsite/immutable copies curb ransomware risk, yet do not fix destroyed keys or overly broad IAM.
- **Encryption:** TLS, database at rest, encrypted backup objects, and client-side encryption are distinct layers; KMS keys must outlive historical backups.
- **Access control:** separate backup writers, restore operators, delete/retention admins, and KMS decrypt roles; require audits and approvals for high-risk actions.
- **Restore drills:** a backup is reliable only when it can be decrypted, recover data and applications, and hit target timelines.

A strong design answers not only **"how many copies do we keep?"** but also **"which copy is usable, who is allowed to fetch it, which key decrypts it, and how fast can we restore the right data?"**

## Official References

- [MongoDB Atlas — Guidance for Atlas Backups](https://www.mongodb.com/docs/atlas/architecture/current/backups/)
- [MongoDB Atlas — Back Up, Restore, and Archive Data](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Atlas — Manage Backup Policies](https://www.mongodb.com/docs/atlas/backup/cloud-backup/configure-backup-policy/)
- [MongoDB Atlas — Backup Scheduling, Retention, and On-Demand Snapshots](https://www.mongodb.com/docs/atlas/backup/cloud-backup/scheduling/)
- [MongoDB Atlas — Configure a Backup Compliance Policy](https://www.mongodb.com/docs/atlas/backup/cloud-backup/backup-compliance-policy/)
- [MongoDB Atlas — Snapshot Management](https://www.mongodb.com/docs/atlas/backup/cloud-backup/snapshot-management/)
- [MongoDB Atlas — Continuous Cloud Backup/PIT Restore](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Atlas — Storage Engine and Cloud Backup Encryption](https://www.mongodb.com/docs/atlas/backup/cloud-backup/cloud-backup-encryption/)
- [MongoDB Atlas — Encryption at Rest using Customer Key Management](https://www.mongodb.com/docs/atlas/security-kms-encryption/)
- [MongoDB Atlas — Restore from a Snapshot](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-snapshot/)
- [MongoDB Atlas — Snapshot Distribution](https://www.mongodb.com/docs/atlas/backup/cloud-backup/snapshot-distribution/)
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Database Tools — mongorestore Access and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [MongoDB Manual — Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
- [MongoDB Manual — Back Up and Restore Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/)
