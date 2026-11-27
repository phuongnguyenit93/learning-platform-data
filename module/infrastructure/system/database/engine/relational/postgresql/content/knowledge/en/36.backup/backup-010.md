# Backup Encryption, Retention, Offsite Storage, and Access Control

A PostgreSQL backup only has value when it can restore the right data within the required timeframe while authorized personnel can still access the copy. In production environments, backups often hold sensitive data equivalent to—or even more concentrated than—a running database. Therefore, protecting backups must address four concerns together: **encryption**, **retention**, **offsite storage**, and **access control**.

Encryption protects contents against unauthorized file or object reads; retention determines which copies are kept and for how long; offsite storage ensures survival when the host, storage domain, or entire site fails; access control restricts who can create, read, delete, alter retention on, or restore copies. These four layers must be designed alongside WAL archiving, backup catalogs, key management, restore testing, and RPO/RTO targets.

This lesson focuses on building an operational PostgreSQL backup protection policy: selecting backup types, encrypting at the right layers, managing keys, storing copies independently of the source host, configuring retention against accidental deletion/ransomware, and enforcing least-privilege access control.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish logical backups, physical base backups, WAL archives, and storage snapshots.
2. Identify what data must be encrypted: backup files, WAL, manifests, catalogs, credentials, and transport.
3. Distinguish encryption at rest, encryption in transit, and client-side encryption.
4. Explain envelope encryption, KMS/HSM, data encryption keys, and key-encryption keys.
5. Plan key rotation, key recovery, revocation, and separation of duties.
6. Design backup retention aligned with RPO/RTO, business requirements, and legal obligations.
7. Distinguish full, differential, and incremental backups and WAL retention.
8. Design offsite, cross-account, cross-region, and immutable/WORM copies.
9. Separate permissions for backup operators, restore operators, storage administrators, and key administrators.
10. Apply least privilege across PostgreSQL roles, service accounts, object storage, and KMS.
11. Protect backup catalogs, manifests, checksums, and archive chains.
12. Test restores, PITR, and disaster recovery rather than checking only backup job success.
13. Handle ransomware, credential compromise, accidental deletion, key loss, and archive gaps.

> **Scope:** Examples cover self-managed PostgreSQL and managed services. Role names, cloud permissions, KMS APIs, backup tool options, and retention behavior depend on provider/version. Always check documentation for your tools and platform before applying production configurations.

## 2. Why Do Backups Need a Dedicated Protection Policy?

Backups typically contain:

- Customer data, transactions, personally identifiable information, and business records.
- WAL records reflecting database changes.
- Schemas, function definitions, grants, and role metadata in certain logical dumps.
- Database names, hostnames, paths, topology, and operational metadata.
- Manifests, backup labels, checksums, and recovery information.

An exposed backup file can let an attacker read data offline without ever logging into PostgreSQL. An account holding backup delete permissions can destroy recoverability even without touching the production database. A deleted or inaccessible KMS key can leave backup bytes intact yet impossible to decrypt.

### Three Protection Objectives

**Confidentiality:** unauthorized parties cannot read backup contents.

**Integrity:** backups cannot be altered, substituted, or spliced undetected.

**Availability:** backups and required keys remain accessible when restore is needed.

A design that encrypts without managing key recovery protects confidentiality while breaking availability. A design with offsite copies where the same credentials can delete everywhere fails to protect well against ransomware.

## 3. Classifying PostgreSQL Backup Types

| Type | Contents | Typical Recovery Method |
|---|---|---|
| Logical backup | Schema/data at SQL object level, e.g. `pg_dump` | `pg_restore` or `psql` |
| Physical base backup | Consistent cluster/data directory files | Restore physical files, start recovery |
| WAL archive | Continuous WAL segments following base backup | Replay WAL for PITR/roll-forward |
| Storage snapshot | Block volume/filesystem snapshot under consistency protocol | Restore volume/snapshot, recover per procedure |
| Configuration/metadata backup | Configs, service definitions, secret references, backup catalog | Rebuild environment and reconnect backup chain |

### Logical Backup

Example:

```sh
pg_dump -Fc -d appdb -f appdb.dump
pg_restore --list appdb.dump
```

Custom-format dumps support selective and parallel restoration with `pg_restore`. Logical backups fit migrations, object-level recovery, and portability, though they do not replace base backups + WAL archives for cluster-wide PITR.

### Physical Base Backup

Example:

```sh
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /backup/staging/base_2026_11_14 \
  -Fp -X stream -P
```

This command is conceptual; configure replication connections, authentication, TLS, destination, and privileges appropriately. Physical backups are normally tied to PostgreSQL major version/platform compatibility and need WAL for consistent recovery.

### WAL Archive

The WAL archive provides the log chain to replay from a base backup to a recovery target. A base backup without its required WAL chain cannot support PITR. Conversely, a WAL archive without a matching base backup cannot rebuild a database from scratch.

## 4. Backup Chains and Recovery Chains

A basic PITR chain:

```text
Base backup B0
   |
   +-- WAL segment 0001
   +-- WAL segment 0002
   +-- WAL segment 0003
   +-- WAL segment 0004
             |
             +-- Recovery target time/LSN
```

To recover to time T:

1. Select a base backup starting before T.
2. Verify the base backup is complete and its manifest/checksums are valid.
3. Retrieve continuous WAL segments from the backup up to T.
4. Configure appropriate recovery settings.
5. Replay WAL up to the chosen target.
6. Validate data and open the service per the cutover plan.

### Backup Retention Must Preserve the Entire Chain

You cannot keep only "the latest base backup" and delete all older WAL if you must recover to a point prior to the newest backup. Retention policies must track which WAL ranges, timelines, and backup catalogs each base backup requires.

## 5. Multi-Layered Backup Protection Model

A reference architecture:

```text
PostgreSQL primary
   |
   +--> Backup agent / pg_dump / pg_basebackup
   |        |
   |        +--> Local staging (restricted, short-lived)
   |                 |
   |                 +--> Encrypt / checksum / manifest
   |                          |
   |                          +--> Offsite object storage
   |                                   |
   |                                   +--> Immutable retention / Object Lock
   |                                   |
   |                                   +--> Cross-account / cross-region copy
   |
   +--> WAL archive pipeline ----------------------^

KMS/HSM --> key policy / audit / rotation / recovery

Restore environment --> read-only verification --> controlled cutover
```

### Why Multiple Layers?

- Encryption protects backup contents.
- Offsite protects when the source host/site/volume is lost.
- Immutable copies protect against unauthorized deletion/tampering.
- Cross-account isolates administrative privileges from production.
- KMS separates decryption permissions from storage read permissions.
- Restore testing proves the backup chain genuinely works.

No single product or checkbox replaces all of these layers.

## 6. Encryption at Rest

**Encryption at rest** protects stored data by encrypting sectors, volumes, filesystems, objects, or files. For PostgreSQL backups, encryption can span several layers:

| Layer | Example | Scope |
|---|---|---|
| Disk/volume encryption | Encrypted block volume | All bytes on the volume |
| Filesystem encryption | Encrypted filesystem | Files inside the filesystem |
| Object storage encryption | SSE-S3/SSE-KMS/provider-managed encryption | Objects stored on object storage |
| Backup-tool encryption | pgBackRest encryption or tool-supported encryption | Backup repository/contents |
| Client-side/file encryption | Encrypt before upload | Bytes already encrypted before leaving backup host |

### Is Storage Encryption Enough?

Storage-layer encryption at rest helps when physical disks/objects are removed or accessed directly without authorization. However, if an attacker gains API read permissions for objects, the storage service may decrypt and return plaintext. When your threat model requires preventing storage administrators/providers from reading contents, consider client-side encryption with organization-controlled keys.

### Layered Encryption

You can combine volume encryption and backup-level encryption. The two layers serve distinct goals: one protects physical storage; the other protects backup artifacts across copies, storage systems, or accounts.

## 7. Encryption in Transit

Backup data traverses networks between:

- PostgreSQL primary and backup host.
- Backup host and object storage.
- Primary and standby/replica.
- KMS client and key service.
- Restore host and storage.

Use TLS/HTTPS or authenticated encrypted protocols for all connections. For PostgreSQL connections, configure TLS and verify server certificates/hostnames, for example:

```text
sslmode=verify-full
sslrootcert=/secure/path/ca.crt
```

### Enabling Encryption Alone Is Not Enough

TLS must verify server identity. If a client accepts any certificate or skips hostname checks, attackers can spoof endpoints in certain scenarios. Enforce strict certificate validation, protect CA material, and track expiration/rotation.

### Inspecting PostgreSQL Connections

```sql
SHOW ssl;

SELECT
    pid,
    usename,
    application_name,
    client_addr,
    ssl,
    version,
    cipher
FROM pg_catalog.pg_stat_ssl;
```

`pg_stat_ssl` displays TLS status per session. Visibility into other sessions depends on privileges/version.

## 8. Client-Side Encryption vs. Server-Side Encryption

**Server-side encryption (SSE):** the storage service encrypts objects on write and decrypts them when authorized callers read via API.

**Client-side encryption (CSE):** the backup client encrypts bytes before sending them to storage; storage holds only ciphertext.

| Criterion | SSE | CSE |
|---|---|---|
| Who performs encryption? | Storage provider/service | Backup client or encryption gateway |
| What does storage API return? | Plaintext to authorized callers | Ciphertext; caller needs key/client to decrypt |
| Key management | Provider/KMS integration | Organization or organization-controlled KMS |
| Restore complexity | Usually simpler | Requires compatible tool/key/config |
| Protection against storage admin | Depends on trust model/provider | Stronger when storage lacks keys |
| Key loss risk | Provider recovery model | Total loss of restorability if key is lost |

### Choosing Based on Threat Model

If the goal is protecting against stolen physical media or storage infrastructure compromise, SSE may suffice. If you must prevent storage account administrators from reading contents, client-side encryption is usually stronger. Either way, test restoring from an independent environment to confirm key access works.
# Backup Encryption, Retention, Offsite Storage, and Access Control

A PostgreSQL backup only has value when it can restore the right data within the required timeframe while authorized personnel can still access the copy. In production environments, backups often hold sensitive data equivalent to—or even more concentrated than—a running database. Therefore, protecting backups must address four concerns together: **encryption**, **retention**, **offsite storage**, and **access control**.

Encryption protects contents against unauthorized file or object reads; retention determines which copies are kept and for how long; offsite storage ensures survival when the host, storage domain, or entire site fails; access control restricts who can create, read, delete, alter retention on, or restore copies. These four layers must be designed alongside WAL archiving, backup catalogs, key management, restore testing, and RPO/RTO targets.

This lesson focuses on building an operational PostgreSQL backup protection policy: selecting backup types, encrypting at the right layers, managing keys, storing copies independently of the source host, configuring retention against accidental deletion/ransomware, and enforcing least-privilege access control.

## 9. Envelope Encryption

Many systems use **envelope encryption** to encrypt large datasets without encrypting every byte directly with one master key:

1. Generate a Data Encryption Key (DEK) for a backup or backup object.
2. Use the DEK to encrypt backup contents with a suitable symmetric algorithm.
3. Use a Key Encryption Key (KEK) inside KMS/HSM to wrap/encrypt the DEK.
4. Store the ciphertext and wrapped DEK alongside required metadata.
5. On restore, an authorized client asks KMS to unwrap the DEK and decrypts the backup.

```text
Backup plaintext
     |
     +-- DEK (random, scoped)
     |       |
     |       +-- encrypt backup --> ciphertext
     |
     +-- KEK in KMS/HSM
             |
             +-- wrap DEK --> wrapped DEK

Storage: ciphertext + wrapped DEK + manifest
```

### Why Is Envelope Encryption Useful?

- KMS/HSM handles only small key material instead of terabytes of data.
- DEKs can vary per backup/object.
- KEK rotation can re-wrap DEKs in some designs without re-encrypting entire backups.
- KMS audit logs track key usage.

### Metadata Must Be Preserved

Backup manifests must record encryption algorithm/version, key identifier, wrapped DEK, nonce/IV, authentication tag, and tool/version metadata per chosen format. Never invent custom crypto formats without vetted libraries/protocols.

## 10. Choosing Encryption Algorithms and Libraries

Prefer modern authenticated encryption algorithms supported by reputable libraries/tools—such as AES-256-GCM or ChaCha20-Poly1305 where appropriate. Exact algorithms must comply with security policy and backup tool/KMS capabilities.

### Authenticated Encryption

AEAD delivers both confidentiality and integrity/authentication for ciphertext. If a backup is tampered with, decryption/authentication tag verification must fail.

### Avoid Rolling Your Own Crypto

- Never write custom encryption algorithms.
- Never reuse nonces/IVs improperly.
- Never store keys alongside plaintext backups.
- Never hard-code passwords/keys in scripts or repositories.
- Never treat unkeyed checksums as proof against an attacker empowered to alter both files and checksums.

Use built-in backup-tool encryption or standard encryption libraries with versioned formats and tested key recovery procedures.

## 11. Checksums, Integrity, and Authenticity

Checksums detect file corruption during transfer/storage:

```sh
sha256sum base_2026_11_14.tar
```

When checksums are stored in a manifest alongside the backup, the restore process can compare them to catch corruption.

### Checksums Alone Do Not Prevent Unauthorized Modification

An attacker with write access to backups and manifests can alter both. To authenticate provenance/integrity against attackers:

- Sign the manifest with an isolated signing key.
- Store the signature in an independent repository/account.
- Restrict write permissions on signatures.
- Audit all signing/verification events.
- Maintain immutable copies to prevent post-write edits.

### Backup Manifest

A manifest should describe:

- Backup ID, database/cluster identity.
- Backup type and tool/version.
- Start/end timestamps.
- Base backup/checkpoint/WAL ranges.
- File/object names and sizes.
- Checksums.
- Encryption metadata/key ID.
- Retention class and expiration.
- Restore instructions/config references.

Never place secrets, passwords, or plaintext keys inside manifests.

## 12. Key Management: Keys Matter More Than Files

Backup encryption helps only if keys are protected and remain accessible during restore. Key management must answer:

- Who creates keys?
- Who can use keys to encrypt?
- Who can decrypt?
- Who can rotate/disable/delete keys?
- How are keys backed up/recovered?
- How long do keys live relative to backup retention?
- What happens when personnel/service accounts leave?

### KMS and HSM

KMS manages lifecycles, policies, audits, and cryptographic operations. HSMs provide hardware protection for key material. Managed KMS typically integrates HSMs provider-side; exact trust boundaries depend on the service.

### Separating Permissions

A backup operator may need permission to encrypt without needing permission to decrypt every backup. A restore operator needs decrypt rights inside approved restore environments. Key administrators manage key lifecycles/policies without necessarily having permission to read database backups.

## 13. DEK and KEK Lifecycles

| Key | Role | Lifecycle |
|---|---|---|
| DEK | Encrypts backup bytes/objects | Generated per backup or repository policy; wrapped by KEK; wrapped copy stored with metadata |
| KEK | Protects DEKs | Managed inside KMS/HSM; rotation, disabling, policies, and recovery |
| Signing key | Signs manifests/catalogs | Isolated permissions; protect private key; rotate per trust policy |
| TLS private key | Authenticates endpoints | Certificate renewal/rotation; never reuse for backup payloads |

### Never Delete Keys While Backups Still Depend on Them

If a KEK is permanently deleted, wrapped DEKs cannot be unwrapped. Backup files remain on disk yet are permanently unreadable. Retention policies must link **key retention** and key recovery to backup lifespans.

## 14. Key Rotation

Rotation occurs at several levels:

1. **KEK rotation:** replacing the key encrypting DEKs. Systems supporting re-wrapping can rotate KEKs without re-encrypting whole backups.
2. **DEK rotation:** generating fresh DEKs for subsequent backups or re-encrypting existing backups per policy.
3. **Signing key rotation:** switching manifest signatures to a new signing key while retaining old public verification keys long enough to verify historical backups.
4. **TLS certificate rotation:** replacing certificates before expiration and updating trust chains.

### Rotation Does Not Mean Immediate Revocation

After rotation, old backups still need decryption. Keep older key versions decrypt-capable throughout the retention and recovery window; restrict encrypt access on old keys if policy allows.

### Safe Procedure

- Create a new key version.
- Grant encrypt/decrypt permissions per policy.
- Test encrypting a test backup.
- Test restoring an old backup using the old key.
- Test restoring a new backup using the new key.
- Update catalogs/runbooks.
- Retire old keys only after all dependencies expire and with approval.

## 15. Key Recovery and Disaster Recovery

A site-wide outage can take out both backup storage and KMS access. Verify:

- Is KMS available in the DR region?
- Are restore identities/roles provisioned in the DR account?
- Do key policies allow decryption from the restore environment?
- If KMS is unavailable, what valid emergency process exists?
- Is there policy-compliant key escrow/backup if required by the model?
- Who is authorized to trigger emergency decryption?

### Never Arbitrarily Export Plaintext Keys to Files

If key escrow or recovery material is required, use provider/HSM/KMS-approved procedures with dual control and auditing. Never copy a master key into the same offsite bucket holding backups.

### Restore Drills Must Test the Key Path

Test restoring backups inside a separate account/region away from everyday production permissions. This verifies key policies, networking, identity federation, and decrypt permissions work during a real disaster.

## 16. Encryption Passwords and Secret Handling

Some backup tools use passphrases or secret files to encrypt/decrypt. How secrets are passed alters exposure risk:

- Avoid command-line arguments where process lists/logs expose them.
- Avoid echoing secrets into shell history or CI output.
- Avoid committing `.env`, credentials, or private keys to Git.
- Use secret managers/short-lived credentials whenever possible.
- Restrict file permissions and process identities.
- Delete plaintext staging once encrypted artifacts are confirmed complete.

### Secret Rotation

When rotating passwords or repository credentials, preserve the ability to decrypt older backups. If each repository uses a distinct key/passphrase, the catalog must map the matching version without storing plaintext secrets.

## 17. What Is a Retention Policy?

Retention specifies **which backups are kept, which may expire, and conditions for deletion**. A policy must cover:

- Logical dumps.
- Physical full/incremental/differential backups.
- WAL archives.
- Manifests/catalogs/checksums.
- Encryption keys/key versions.
- Offsite/cross-region/immutable copies.
- Audit records and restore evidence.

### Retention Is More Than "Keep 30 Days"

A business may require:

- Hourly recovery points for a few days.
- Daily backups for several weeks.
- Weekly backups for several months.
- Monthly/year-end backups for compliance.
- Legal holds on specific datasets.

Retention periods must stem from RPO, RTO, compliance, business recovery needs, privacy/deletion obligations, and storage cost.

## 18. Full, Differential, and Incremental Backups

Backup tools may use slightly different terminology; verify tool semantics:

| Type | Contents |
|---|---|
| Full | A complete standalone backup per tool definition |
| Differential | Changes since the most recent full backup |
| Incremental | Changes since a prior backup, usually the latest backup in the chain |

### Chain Example

```text
Sunday: Full F0
Monday: Incremental I1
Tuesday: Incremental I2
Wednesday: Incremental I3

Restore Wednesday:
  F0 + I1 + I2 + I3
```

If I2 is missing/corrupted, the restore chain may fail depending on the tool. Retention must preserve dependencies and the backup catalog needed to reconstruct the chain.

### Differential

Example:

```text
Sunday: Full F0
Monday: Diff D1 (since F0)
Tuesday: Diff D2 (since F0)
Wednesday: Diff D3 (since F0)

Restore Wednesday:
  F0 + D3
```

Differentials grow larger over time; in return, restore chains have fewer steps than incremental chains.

## 19. Retention and WAL Archives

For physical backups + PITR:

- Retain base backups recent enough to meet recovery objectives.
- Retain continuous WAL segments needed for every base backup still inside retention.
- Retain timeline history files.
- Retain backup manifests/catalogs and checksums.
- Retain matching encryption keys.

### Example

If you retain full backups for 30 days and require PITR to any timestamp within those 30 days, you must keep continuous WAL archives covering all supported recovery chains in that window. Never delete older WAL simply because a newer base backup completed if older restore points remain covered by policy.

### Dependency-Based Retention

A single WAL segment can be required by multiple backups/recovery windows. Delete it only once every retained chain no longer depends on it.

## 20. Time-Based vs. Count-Based Retention

Two common approaches:

- Keep by age, e.g., 35 days.
- Keep by count, e.g., latest 7 full backups.

### Combining Both

A policy might keep:

- 14 daily recovery points.
- 8 weekly points.
- 12 monthly points.
- 1 annual point.

These are illustrative examples, not a default schedule. Specify which daily/weekly/monthly backups are full vs. synthetic full, and how WAL ranges depend on them.

### Never Delete Solely by Filename Timestamp

Consult backup catalogs/tool metadata for dependencies and status. Manual file deletion can break chains or confuse backup tools about remaining backups.

## 21. Retention Locks and Legal Holds

Retention locks block objects from being deleted or overwritten before a specified timestamp. Legal holds preserve objects indefinitely or until released under formal legal procedures.

### Two Common Modes

- **Governance mode:** privileged identities can override retention if granted specific permissions and policy approval.
- **Compliance mode:** stricter retention lock; even top administrators cannot delete objects before expiration per provider semantics.

Exact names and behavior depend on the object storage provider.

### Key Distinctions

Retention locks protect objects from deletion/modification during the lock window. They do not prove contents are valid, replace encryption, prevent data leaks, or guarantee keys remain usable.

### Legal Holds

Legal holds apply per case/dataset and require an owner and audit trail. Never let normal retention expiry automatically delete copies under legal hold.

## 22. Immutable Backups and WORM

**WORM (Write Once, Read Many)** allows writing once and then locking objects against edits/deletions for a duration. Immutable backups protect against:

- Ransomware compromising production.
- Leaked admin credentials.
- Misconfigured cleanup scripts.
- Attackers wiping backups alongside the database.

### Design

1. Upload backups to buckets/repositories with versioning or immutable retention.
2. Apply retention locks before attackers can alter policies.
3. Isolate retention management permissions from production accounts.
4. Enable audit logging for put/get/delete/retention changes.
5. Test restoring from immutable copies.

### Versioning Alone Is Not Immutability

Versioning preserves prior versions, yet identities with delete-version rights or lifecycle rules can still purge them. Pair Object Lock/WORM with policies blocking deletions and version deletions.

## 23. What Is Offsite Backup?

An offsite backup is a copy stored outside the source system's failure domain. Examples:

- A separate object storage account.
- A different cloud region.
- An independent provider or storage system.
- Another datacenter/site.
- Controlled offline/tape storage.

### Why Is the Same Host Not Enough?

If backups live on the same volume or host as PostgreSQL, disk failure, ransomware, operator error, or host loss destroys both primary and backups.

### Independent Failure Domains

Offsite is more than another folder. Evaluate:

- Credentials and identity providers.
- Accounts/subscriptions/projects.
- Regions/providers.
- Networks/control planes.
- KMS key administration.
- Delete/retention policies.

If the same admin credential can wipe both the primary and the offsite copy, both still share an administrative failure domain.

## 24. Cross-Account and Cross-Region Copies

Cross-account copies place backups in a separate account/project to limit blast radius if the production account is compromised. Cross-region copies enable recovery when the primary region goes down.

| Design | Primary Protection | What to Verify |
|---|---|---|
| Same account, different bucket | Limited path/object isolation | Shared admin/delete credentials |
| Separate account | Production account compromise | Trust policies, cross-account roles |
| Separate region | Region outage | KMS key availability, replication lag |
| Separate provider | Provider/control-plane outage | Data egress, formats, restore tooling |
| Offline copy | Online ransomware/deletion | Custody, rotation, restore access |

### Cross-Region Alone Is Not Enough

If KMS keys exist only in the primary region or policies bar DR roles from decrypting, secondary-region copies cannot restore. Test both storage paths and key paths.

## 25. Designing an Independent Backup Repository

An offsite repository should have:

- Dedicated storage account/project.
- Separate buckets/containers per environment or security boundary.
- Appropriate versioning/immutability.
- Independent encryption key policies.
- Least-privilege service accounts.
- Audit logs shipped to an independent log system.
- Private network endpoints or restricted egress policies where available.
- Lifecycle rules aligned with retention.
- A dedicated restore role enabled under controlled approval.

### Separating Production and Backup Control Planes

Never use one admin role to manage databases, delete backups, alter retention locks, and delete KMS keys. Separation prevents one compromised credential from destroying the entire recovery chain.

## 26. Backup Staging on the Source Host

Some tools write backups to local staging before uploading. Staging must be protected:

- Use filesystems/volumes with encryption at rest.
- Allow only the backup service account to read/write.
- Restrict shell/admin access on the host.
- Do not retain plaintext staging longer than necessary.
- Enforce disk quotas/headroom and alerts.
- Clean up temporary files with tool-aware cleanup.
- Never delete staging before confirming upload completion.

### Staging Is Not an Offsite Copy

Staging is strictly transient. Mark a backup complete only after upload finishes, checksum/integrity checks pass, and the catalog updates.

## 27. Object Storage Permissions: Separating Actions

Never bundle all permissions into one admin role. Split by action:

| Role | Typical Permissions | Should Not Have by Default |
|---|---|---|
| Backup writer | Put objects into designated prefix | Delete objects, alter retention, manage bucket policies |
| Restore reader | List/get objects needed for restore | Put/delete, alter retention |
| Retention manager | Manage lifecycle/retention per policy | Decrypt keys or read plaintext |
| Storage auditor | Read audit/config metadata | Read object contents |
| Platform administrator | Manage accounts per governance | Unilateral power to break immutable controls |

Exact action names depend on the provider. Also inspect inherited permissions at bucket, account, organization, and KMS levels.

## 28. PostgreSQL Backup Roles and Replication Privileges

For physical backups via `pg_basebackup`, the user needs replication privileges and connection access in `pg_hba.conf`. Example:

```sql
CREATE ROLE backup_user
WITH LOGIN REPLICATION
PASSWORD 'set-through-secret-management';
```

This illustrates role attributes only. Never put production passwords in SQL history or plaintext scripts; use secret managers and rotate per policy.

### Logical Dump Privileges

`pg_dump` normally needs `CONNECT`, `USAGE`/`SELECT` on dumped objects, plus read rights on large objects/sequences or metadata as needed. Use a dedicated read-only role tested on real schemas; never grant superuser just to make backups run.

### Row-Level Security

If tables enable RLS, understand `pg_dump` behavior, `BYPASSRLS`/owner privileges, and relevant options. A backup missing rows due to RLS can exit cleanly yet be incomplete. Define explicitly whether the backup role may bypass RLS under policy and auditing.

## 29. `pg_hba.conf` and Network Access

Allow the backup service account to connect only from designated backup hosts/networks. Enforce TLS and strong authentication, narrow CIDRs, and never open replication connections to the public internet.

Conceptual example:

```text
# TYPE  DATABASE  USER         ADDRESS          METHOD
hostssl replication backup_user 10.20.30.40/32   scram-sha-256
```

This is syntax illustration; place rules in the right order in `pg_hba.conf` and configure TLS/certificates. A broader rule higher up matches before narrower rules below.

### Do Not Forget Network Policies

Security groups/firewalls/private endpoints must also restrict source/destination traffic. `pg_hba.conf` does not replace network firewalls.

## 30. Service Accounts and Short-Lived Credentials

Backup automation should never depend on personal user accounts. Use dedicated service identities:

- One identity to create backups.
- One identity to write to the offsite repository.
- One identity to read/restore.
- One identity to manage keys if needed.

### Prefer Short-Lived Credentials

Where supported by providers, use workload identity, instance roles, managed identities, or short-lived tokens instead of static access keys. This shrinks exposure from leaked long-lived secrets.

### When Static Credentials Are Unavoidable

- Store inside a secret manager.
- Scope down resources and actions tightly.
- Rotate periodically and after incidents.
- Never share between production and DR.
- Audit usage and alert on anomalous credential activity.

## 31. Separation of Duties

Divide critical duties:

| Duty | Recommended Role |
|---|---|
| Create backups | Backup operator/service |
| Read backups | Approved restore operator |
| Delete/expire backups | Retention manager per policy |
| Modify Object Lock | Security/storage admin under dual control |
| Create/rotate KEK | Key administrator |
| Decrypt in DR | Restore role + KMS policy/approval |
| Review audits | Security auditor |

### Why Separate?

Someone who creates backups should not also have power to wipe all copies or delete decryption keys. Someone managing keys does not need permission to read plaintext data. Separation of duties reduces insider and credential-compromise risk.

## 32. Audit Trails and Detecting Anomalous Access

Log:

- Who created backups, and from which host/database.
- Who uploaded/downloaded objects.
- Who called key decrypt/unwrap.
- Who altered retention/lifecycle/Object Lock.
- Who deleted objects/versions or changed bucket policies.
- Who restored data and where it landed.
- Who changed credentials/roles/KMS policies.

### Audit Logs Must Be Independent

If audit logs sit solely inside the production account, an attacker compromising the account can wipe both backups and evidence. Ship audit events to an independent log account/SIEM with retention/immutability and restricted edit access.

## 33. Protecting Backup Catalogs and Metadata

Backup catalogs normally store information on:

- Backup IDs and backup sets.
- Parent/child links for incremental backups.
- WAL ranges/timelines.
- Start/stop LSNs or backup labels.
- Checksums and file mappings.
- Encryption key IDs/versions.
- Retention/expiration states.

Losing the catalog makes locating and assembling backup chains difficult even if files survive. Protect catalogs with dedicated backups, versioning, encryption, immutable/offsite copies, and restore tests.

### Catalogs Must Not Contain Plaintext Secrets

Catalogs should store key identifiers and required metadata—never plaintext DEKs, passphrases, or cloud credentials.

## 34. Backup Integrity and Restore Verification

A backup job exiting 0 proves only that the tool reported success in its own execution. Layer multiple checks:

1. Backup files/objects have expected sizes and manifests.
2. Checksums/hashes verify cleanly.
3. Backup catalog recognizes the backup.
4. WAL chain is continuous if PITR is required.
5. Encryption metadata/key IDs resolve cleanly.
6. Restore tools can read and decrypt.
7. PostgreSQL starts/recovers.
8. Business data is validated post-restore.

### Integrity vs. Recoverability

Valid checksums do not prove the database boots. Decryptable backups do not prove the WAL chain is complete. Database startup does not prove business data is complete or RPO is met. Test end-to-end.

## 35. Scheduled Restore Tests

Design restore drills:

- Restore logical dumps into isolated databases.
- Restore physical base backups onto isolated hosts.
- Replay WAL to target timestamps.
- Restore offsite copies in the DR region/account.
- Restore using older key versions.
- Restore while production credentials are unavailable.
- Verify backup chains after retention cleanup.

### Measure

- Restore duration.
- WAL replay duration.
- Data validation duration.
- Key access latency/failures.
- Network throughput.
- Storage provisioning time.
- Actual RTO vs. target.

Do not check only backup creation; **test restores prove copies are usable**.

## 36. RPO, RTO, and Retention

**RPO (Recovery Point Objective):** maximum data loss accepted by the organization, usually expressed in time.

**RTO (Recovery Time Objective):** target duration to restore service.

Example:

- 15-minute RPO: recovery points/WAL archive must stay fresh enough to lose at most 15 minutes of changes.
- 2-hour RTO: base backups, WAL chains, keys, compute/storage, and restore runbooks must bring the service back within 2 hours.

### RPO Depends on More Than Full Backup Schedules

PITR with continuous WAL archiving yields recovery points much closer to incident time. If archive lag reaches 40 minutes, nightly base backups will not achieve a 15-minute RPO.

### RTO Depends on More Than Backup Size

Restore duration also depends on provisioning, network, decryption, decompression, WAL replay, index/constraint validation, application checks, and cutover.

## 37. Retention, Privacy, and Data Deletion

Backup retention can conflict with personal data erasure requests or legal holds. Establish policies approved by legal/security/data governance:

- Define retention basis per data class.
- Define when backups expire and get purged.
- Evaluate whether scoped cryptographic erasure is appropriate.
- Manage legal holds/exceptions.
- Record when records were deleted from live systems and when older backups expire.
- Ensure restores do not reintroduce deleted data into production without reapplying deletion controls.

### Cryptographic Erasure

In some designs, destroying a key renders ciphertext unreadable. This is high-impact and cannot substitute for data deletion if keys are shared across multiple backups or plaintext copies exist. Apply only when encryption/key scopes and legal policies are explicitly designed for it.

## 38. Ransomware and Immutable Backups

Ransomware actively hunts and deletes backups before encrypting production. Countermeasures:

- Separate backup accounts from production identities.
- Enforce immutable/WORM retention.
- Restrict delete/version-delete permissions.
- Protect KMS key deletion with dual control and deletion waiting periods where supported.
- Use short-lived credentials.
- Maintain offline/air-gapped copies per threat model.
- Audit and alert on deletions/retention changes.
- Test restoring from immutable copies.

### Do Not Treat Immutability as the Complete Solution

Attackers can still steal plaintext if they hold decrypt rights, corrupt new backups before locking, or hijack restore environments. Separate write/read/decrypt/delete permissions and verify backup integrity.

## 39. Protecting Against Accidental Deletion

Layers of protection:

- Object versioning.
- Soft delete/recycle bin where supported by provider.
- Retention locks.
- MFA/approval for destructive operations.
- Cross-account copies.
- Audit alerts on delete events.
- IaC reviews for lifecycle/bucket policy changes.

### Lifecycle Rules

Lifecycle policies delete objects automatically on expiration. Misconfigured prefixes/tags can wipe active backups. Test rules on sandbox prefixes, review plans, apply clear tags, and monitor objects nearing expiration.

## 40. Workflow for Publishing a Secure Backup

Reference pipeline:

1. Create backup from PostgreSQL per snapshot/backup tool protocol.
2. Collect WAL/metadata needed for consistency and PITR.
3. Compute checksums and generate manifest.
4. Encrypt backup using a DEK.
5. Wrap DEK using KEK/KMS.
6. Upload ciphertext/manifest to offsite repository.
7. Apply immutable retention and cross-account/region replication.
8. Verify object sizes/checksums/signatures.
9. Update backup catalog and key references.
10. Run scheduled restore validation and archive audit evidence.

### Backup Status

Never mark a backup `COMPLETE` immediately when local dumping ends. Publish completion only after all artifacts, WAL dependencies, encryption metadata, object uploads, and integrity checks succeed.

## 41. Example: pgBackRest and Repository Encryption

pgBackRest is a widely used tool managing physical backups, incremental/differential backups, WAL archiving, and repositories. It supports passphrase-based repository encryption in appropriate configurations.

Conceptual config example:

```ini
[global]
repo1-type=s3
repo1-path=/pgbackrest
repo1-s3-bucket=company-pg-backups
repo1-s3-region=ap-southeast-1
repo1-cipher-type=aes-256-cbc
repo1-cipher-pass=<provided-through-secure-secret-management>

[app]
pg1-path=/var/lib/postgresql/data
```

This illustrates configuration style only, not a complete production file. Verify exact options, encryption modes, and provider-specific settings against your pgBackRest version. Never store plaintext passphrases in broadly readable config files; use secret injection and strict file permissions.

### What to Verify

- Is repository encryption enabled on the right repo?
- Are all required backup/WAL objects encrypted?
- Are keys/passphrases stored and recoverable independently?
- Can the restore host read the repository and decrypt?
- Are repository metadata/catalogs protected?
- Does the offsite bucket enforce immutable retention and isolated policies?

## 42. Example: Barman and Object Storage

Barman manages physical backups and WAL archiving for PostgreSQL. The backup architecture can pair with encryption at the filesystem, storage, object storage, or an appropriate client-side layer.

### Design

1. Barman receives base backups/WAL from PostgreSQL.
2. Backup repositories sit on encrypted storage.
3. A pipeline copies/replicates artifacts to offsite object storage.
4. Object storage enables SSE-KMS or receives client-side encrypted ciphertext.
5. Bucket policies/retention locks prevent unauthorized deletion.
6. Restore drills verify Barman and key access can read offsite copies.

Never assume Barman succeeding means the repository uses client-side encryption. Pinpoint exact encryption layers and test plaintext exposure against your threat model.

## 43. Example: Encrypting `pg_dump` Before Upload

For logical dumps, create a custom-format file and pass it through an approved encryption tool before upload:

```sh
pg_dump -Fc -d appdb -f /secure-staging/appdb.dump

# Encrypt using an approved, authenticated-encryption tool.
# Store ciphertext and signed manifest in offsite storage.

sha256sum /secure-staging/appdb.dump
```

This outlines steps without prescribing specific encryption commands because formats/key management depend on organization-approved tooling. Never piece together ad-hoc OpenSSL flags or cipher options in production without defining nonces, authentication, key wrapping, and restore formats.

### Restore

1. Download ciphertext.
2. Verify signed manifest/checksum.
3. Obtain decrypt permission/key version.
4. Decrypt into protected staging.
5. Run `pg_restore --list` to confirm dump readability.
6. Restore into an isolated database.
7. Run data validation.

Never decrypt sensitive backups into world-readable directories or unencrypted temporary disks.

## 44. Storage Snapshots and Consistency

Storage snapshots can be very fast, yet snapshotting a live database must follow consistency protocols. A block snapshot taken without a PostgreSQL-aware workflow requires crash recovery and appropriate WAL.

### Snapshot Types

- Crash-consistent: equivalent to storage losing power at a point in time; PostgreSQL needs crash recovery.
- Application-consistent: backup orchestration coordinates with the database to guarantee consistent state.
- Snapshots with WAL/archive integration: combining volume snapshots and WAL for recovery/PITR.

### What to Verify

- Does the snapshot cover all needed volumes/data files?
- Is WAL/`pg_wal` snapshotted or archived consistently?
- Must multiple volumes be snapshotted atomically?
- Are required backup labels/metadata preserved?
- Can restored snapshots boot/recover on the exact PostgreSQL version?

Fast snapshots do not equal complete or PITR-ready backups.

## 45. Backup Encryption and WAL Encryption

WAL records data changes and can expose sensitive data. If base backups are encrypted while WAL archives sit in plaintext, attackers can read or partially reconstruct contents.

### Must Cover

- Base backups.
- WAL archive segments.
- Logical dumps.
- Temporary/staging files.
- Backup manifests/catalogs.
- Exported configuration files.
- Replicated and cross-region copies.

### Encryption Scope

Verify whether encryption occurs pre-upload or via storage services. Trace every path WAL takes, including `archive_command`, object replication, restore downloads, and temporary spools.

## 46. TLS for WAL Streaming and Backup Connections

Streaming replication and `pg_basebackup` use PostgreSQL connections. Enforce TLS via server settings/`pg_hba` rules and client SSL parameters.

### Inspection

```sql
SHOW ssl;
SHOW ssl_min_protocol_version;

SELECT
    pid,
    usename,
    application_name,
    client_addr,
    ssl,
    version,
    cipher
FROM pg_catalog.pg_stat_ssl;
```

### Certificate Lifecycle

- Protect private keys with strict filesystem permissions.
- Use CA/certificate chains with clear renewal workflows.
- Update trust stores on backup/restore hosts.
- Monitor expiration ahead of deadlines.
- Enforce hostname verification.
- Revoke certificates immediately if identities are compromised.

Never let backup pipelines fail unexpectedly due to expired certificates or CA rotations missed on DR hosts.

## 47. Encryption Metadata and Tool Compatibility

A backup may be encrypted by a specific tool/version. To restore years later, record:

- Tool name/version.
- Encryption format/version.
- Cipher/AEAD algorithm.
- KMS key ID/version or passphrase reference.
- Wrapped DEK metadata.
- Compression format/version.
- Manifest schema version.
- Verified restore commands/runbooks.

### Backward Compatibility

Never upgrade tools or change encryption formats without testing reads of older backups. Preserve compatible binaries/container images or define repository migration paths.

### Never Store Secrets in Runbooks

Runbooks should reference secret managers/key IDs and authorization steps. Never embed passphrases/private keys directly into docs or tickets.

## 48. Compression and Encryption Order

Normally, data is **compressed first and then encrypted**:

```text
Database backup
   |
   +--> Compression
           |
           +--> Encryption
                   |
                   +--> Offsite storage
```

Encryption produces high-entropy bytes, so compressing after encryption saves almost no space. Compressing before encrypting saves more storage and network bandwidth.

### Impact

- Compression consumes CPU and can extend backup duration.
- Encryption consumes CPU or hardware acceleration.
- Parallelism affects throughput and memory.
- Restores decrypt first, then decompress.

Measure end-to-end backup/restore times on representative data; never optimize storage ratios at the expense of blowing past RTO.

## 49. Backup Repositories and Deduplication

Some tools/repositories support block-level deduplication or incremental chains. Dedup saves space, though retention/immutability and encryption order affect efficiency:

- Encrypting each file with a random DEK alters bytes completely and lowers dedup ratios.
- Repository-level encryption preserves dedup in certain tool designs.
- Dedup services may need visibility into plaintext or chunk metadata depending on architecture.

### Threat Model

Deduplication can leak information via side channels in certain cross-tenant designs. Rely on vetted tool/provider mechanisms; never invent convergent encryption solely to save storage.

## 50. Retention for Logical vs. Physical Backups

Logical dumps and physical backups have differing characteristics:

| Criterion | Logical | Physical |
|---|---|---|
| Portability | Higher across certain environments/versions | Tied to cluster/version/platform |
| Object-level restore | More convenient | Usually restore cluster/DB then extract |
| Cluster-wide PITR | Not provided by a standalone dump | Combines base backup + WAL |
| Size/time | Can be slow for large databases | Usually suited to large physical recovery |
| Retention dependencies | Usually independent per dump | Incremental chain/WAL dependencies |

A strategy can keep daily logical dumps for selected databases alongside physical base backups + WAL for disaster recovery. Both require encryption, offsite copies, retention, and restore tests.

## 51. Tiering Retention by Sensitivity

Not all databases share the same data sensitivity or retention duration. Classify them:

- Tier A: customer/financial data, strong encryption, immutable offsite, approved access.
- Tier B: operational metadata, shorter retention as needed.
- Tier C: test/synthetic data, simpler policies yet still under access controls.

### Beware Derived Data

A database labeled "metadata only" can still contain usernames, emails, IP addresses, internal topology, or SQL text. Inspect actual contents before relaxing controls.

## 52. Access Control for Backup Repositories

Access control must govern separately:

- Listing objects.
- Reading/downloading.
- Uploading/creating.
- Overwriting existing versions.
- Deleting versions.
- Modifying retention/legal holds.
- Modifying bucket policies/encryption settings.
- Decrypting/unwrapping keys.
- Replicating/copying objects across accounts.

### Least Privilege

A backup writer normally needs only `Put` into a specific prefix. It never needs delete-bucket, lifecycle-edit, or KMS-key-admin rights. Restore readers get temporary `Get`/`List` permissions during approved windows. Retention managers get policy actions without needing plaintext read rights.

## 53. Object Prefixes and Environment Isolation

Organize repositories by security boundary:

```text
backup-root/
  prod/
    cluster-a/
    cluster-b/
  staging/
    cluster-test/
  legal-hold/
    case-2026-001/
```

This layout is illustrative. Use separate buckets/containers instead of prefixes if stronger policy isolation is needed.

### Benefits

- Roles access only required prefixes/environments.
- Retention policies can differ.
- Audits separate cleanly.
- Prevents test backups from overwriting production.

Prefixes do not create true security boundaries if bucket policies allow broad access.

## 54. Access Control for Restores

A restore creates a plaintext copy in a new environment. Procedures must specify:

- Who can request a restore?
- Who approves sensitive data restores?
- Which account/VPC/network receives the restore?
- Who gets decrypt permission and for how long?
- Is masking/anonymization required before developers access it?
- How long is staging data kept and how is it purged?

### Restoring Does Not Automatically Authorize Data Access

An engineer may need to verify a restore without reading customer records. Restore inside an isolated environment, restrict networking, mask data, and grant temporary ticket-scoped access.

## 55. Restore Testing and Sensitive Data

When restoring production backups into non-production:

- Restrict user access.
- Mask/anonymize data where appropriate.
- Never send dumps via email/chat.
- Use encrypted volumes.
- Block outbound network access.
- Delete staging on schedule.
- Audit queries/downloads where supported.

Backup encryption stops protecting data once restored into plaintext. Restore environments require production-grade controls or formally approved exceptions.

## 56. Immutable Retention and Delete Permissions

A backup writer role may create new objects without deleting versions. A retention service can let objects expire naturally on schedule. Security admins authorized to modify Object Lock must operate under MFA/dual approval.

### Handling Exceptions

If a backup must be deleted early due to privacy/legal mandates:

1. Identify exact objects/versions and dependencies.
2. Check legal holds and regulatory rules.
3. Confirm remaining restore chains still meet policy post-deletion.
4. Obtain owner/security/legal approval per workflow.
5. Execute using a dedicated privileged role.
6. Archive audit evidence and verify post-action state.

Never bypass retention locks by deleting buckets/accounts or keys without assessing recovery fallout.

## 57. Cross-Account Copies and Trust Policies

A backup writer from the production account should assume a role in the backup account scoped strictly to uploading into its prefix. The backup account must never trust all principals in the production account.

### Controls

- Restrict specific principal ARNs/service identities.
- Enforce external IDs/conditions where supported by provider.
- Restrict actions and resource ARNs.
- Use short session durations.
- Audit `AssumeRole` and object writes.
- Never grant permissions to alter bucket policies/retention.

### Restore Role

A restore role can reside in a separate DR account, enabled only during restores with appropriate read/decrypt rights. Use approval workflows or just-in-time access.

## 58. KMS Policies and Decrypt Permissions

Object storage policies and KMS key policies are two separate layers. A principal with `GetObject` but lacking key decrypt rights can download ciphertext without reading plaintext. Conversely, key decrypt rights without object read rights cannot restore either.

### Verify Both

- Does the storage identity have `Get`/`List` on the right objects?
- Does the KMS identity have `decrypt`/`unwrap` on the right key versions?
- Does the key policy permit the DR role?
- Are KMS network endpoints reachable from the DR region?
- Is the key active (not disabled/pending deletion)?
- Do audit logs capture decrypt events?

Never grant `kms:*` just to silence an `AccessDenied` error. Identify exact actions and resource/key contexts.

## 59. KMS Deletion Protection

Deleting a KEK breaks decryption for every dependent backup. Protect keys:

- Restrict `schedule deletion` permissions.
- Require MFA/dual approval.
- Enable deletion waiting periods where supported.
- Alert on key policy/disable/deletion changes.
- Keep a key inventory linked to backup retention.
- Verify key state during backup verification.

### Disable vs. Delete

Disabling a key temporarily blocks decryption and is reversible; scheduled deletion causes permanent key loss once the waiting period expires. Runbooks must distinguish them and restrict who can execute either.

## 60. Retention and Lifecycle Automation

Lifecycle automation expires backups per policy, but must respect dependencies:

1. Identify backup sets past retention.
2. Confirm the backup is not a parent of any retained incremental chain.
3. Confirm WAL ranges are no longer needed by any active recovery point.
4. Check legal holds.
5. Check immutable retention expiration.
6. Delete through the backup tool/catalog or supported lifecycle mechanism.
7. Update catalogs/audits.
8. Verify remaining restore points still work.

Never apply a blanket 30-day delete rule when backup chains require longer dependencies or monthly/legal copies exist.

## 61. Restoring from Offsite Backups

A restore runbook should specify steps in order:

1. Open an incident/change record and identify the business owner.
2. Choose a recovery point meeting RPO.
3. Identify the required base backup and WAL chain.
4. Verify backup manifest, signature/checksum, and catalog.
5. Provision restore host/storage/networking.
6. Grant short-lived storage read and KMS decrypt permissions.
7. Download ciphertext to encrypted staging.
8. Verify integrity, then decrypt/decompress.
9. Restore physical files or run `pg_restore` on logical dumps.
10. Replay WAL to target if performing PITR.
11. Run database/business validation.
12. Grant application access, cut over, and monitor.
13. Revoke temporary permissions; retain or purge staging per policy.

### Every Step Needs an Owner

Runbooks must name executors, approvers, estimated durations, dependencies, and escalation contacts. A single restore command is not a disaster recovery runbook.

## 62. PITR and Recovery Targets

PostgreSQL supports recovery targets by timestamp, transaction ID, restore point, or LSN depending on version/configuration. Modern configurations use `recovery.signal` with `recovery_target_*` parameters; exact implementation depends on major version.

Conceptual example:

```text
restore_command = 'retrieve archived WAL segment'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
```

Never paste this literal `restore_command` into production: it must be a real command/script fetching the right WAL segment, validating filenames, and returning proper exit statuses. Choose target actions based on cutover plans and version.

### Selecting a Recovery Target

- Locate the timestamp immediately prior to data-corrupting operations.
- Verify timezone/clock sources.
- If using a named restore point, confirm the WAL holds that restore point.
- Use `pause` to inspect state before promoting if required by procedure.
- Avoid picking a target too early and unnecessarily losing valid transactions.

## 63. PITR Chain Completeness

Before restoring, confirm:

- Base backup is valid with start/stop metadata.
- WAL archive starts at the segment required by the base backup.
- Zero gaps exist in the middle.
- Timeline history files are complete if timeline switches occurred.
- Encryption key versions remain active.
- `restore_command` reaches the right repository/region.
- Backup tooling understands the chain/dependencies.

One tiny WAL gap can fail PITR to a later target even when all other backup files are intact.

## 64. Restoring into an Isolated Environment

Never restore production backups directly over live production without an approved cutover plan.

### Isolated Restore

- Use a separate VPC/subnet.
- Block outbound network access by default.
- Do not register in production service discovery.
- Never send real emails/payments/webhooks.
- Use dedicated credentials.
- Restrict user access.
- Mask data if used for non-production.

### Why?

A restored database can contain jobs, triggers, scheduled tasks, or credentials that cause applications to trigger external side effects upon startup. Isolation lets you validate data without unintended transactions.

## 65. Restore Validation for PostgreSQL

After starting the database:

```sql
SELECT version();
SELECT pg_is_in_recovery();
SELECT current_database();
SELECT now();
```

Verify further:

- Expected databases/schemas/tables exist.
- Row counts/aggregates/key ranges match validation plans.
- Constraints and indexes are usable.
- Extensions/functions/roles/configurations match.
- Sequences/identity values are in the right state.
- WAL recovery finished at the intended target.
- Application smoke tests pass.

### Do Not Stop at Counting Rows

A table with matching row counts can still hold missing or altered data. Use business invariants, checksums, sums, representative queries, and application-level checks.

## 66. Restoring Logical Dumps

Inspect the archive:

```sh
pg_restore --list appdb.dump
```

Restore into a test database:

```sh
createdb restore_test
pg_restore \
  --dbname=restore_test \
  --no-owner \
  --no-privileges \
  appdb.dump
```

Options like `--no-owner`/`--no-privileges` fit only certain environments; if ownership/grants must be preserved, matching roles and an appropriate restore policy are needed.

### Globals

`pg_dump` does not automatically back up cluster-wide roles/tablespaces like `pg_dumpall --globals-only`. Save globals via a separate workflow and protect that file as sensitive data:

```sh
pg_dumpall --globals-only > globals.sql
```

Check file contents and permissions; globals dumps can hold role definitions/password hashes and security metadata.

## 67. Restoring Physical Base Backups

For physical backups:

1. Use a compatible PostgreSQL major version.
2. Prepare an empty data directory with matching owner/permissions.
3. Restore the base backup per tool instructions.
4. Provide the WAL archive and `restore_command`.
5. Configure recovery targets if PITR is needed.
6. Start the server inside an isolated network.
7. Monitor recovery logs until the target is reached.
8. Check `pg_is_in_recovery()` and data.

Never copy a running data directory using ordinary filesystem copies without using a supported backup protocol/snapshot consistency workflow.

## 68. Restore Tests for Old Encryption Keys

Every key rotation should include restore testing:

| Test | Expected Outcome |
|---|---|
| Backup encrypted with old key version | Decrypts cleanly within retention window |
| New backup with new key version | Decrypts cleanly |
| Restore role in DR account | Permitted to unwrap required keys |
| Key disabled in lab | Restore fails with clear error; re-enable per approval |
| Manifest has wrong key ID | Validation fails before restore |

Never disable/delete a production key to test. Use test keys and isolated repositories.

## 69. Restore Duration and Bottlenecks

RTO can be dominated by:

- Storage provisioning.
- Object download/network throughput.
- Decryption/decompression CPU.
- Backup chain length.
- WAL replay volume.
- Database crash recovery.
- Index/constraint rebuilding for logical restores.
- DNS, secrets, certificates, and application deployment.
- Business validation/cutover.

### Measure in Practice

Record timestamps for each phase. If RTO target is 2 hours while downloading backups alone takes 90 minutes, optimizing WAL replay will not solve the primary bottleneck.

## 70. Backup Retention and Restore Frequency

A backup kept for 7 years without being restore-tested for 7 years can become unreliable due to:

- Changing tool formats.
- Retired key versions.
- Expired certificates/CAs.
- Deleted cloud accounts/roles.
- Excessively slow archive-tier retrieval.
- Outdated documentation.
- Unsupported older PostgreSQL major versions/platforms.

Long retention requires an **operational compatibility plan**: archive tool/runtimes, key lifecycles, catalogs, documentation, and periodic test restores.

## 71. Runbook: Backup Job Succeeded Yet Object Not Offsite

1. Check backup process exit code and local staging status.
2. Verify whether the upload job ran.
3. Check object count/size and multipart completion.
4. Check credentials, networking, endpoints, and bucket policies.
5. Check checksums/manifests post-upload.
6. Check encryption metadata and key IDs.
7. Publish backup complete only after verification.
8. Keep local staging for a defined short window.
9. Retry upload using idempotent object keys/tool protocols.
10. Alert if offsite RPO is breached.

Never delete local staging merely because the backup process ended; confirm the offsite artifact is complete first.

## 72. Runbook: Backup Exists Yet Fails Decryption

1. Read manifest to identify encryption format and key ID/version.
2. Check tool/version and decryption compatibility.
3. Check KMS key state: enabled, scheduled deletion, policy.
4. Confirm the restore role holds unwrap/decrypt permissions.
5. Check networking/regional endpoints to KMS.
6. Check audit logs for `AccessDenied`/key errors.
7. Verify wrapped DEK/nonce/tag metadata is intact.
8. Invoke key recovery/approval processes if needed.
9. Test decryption on an isolated copy.
10. Never log plaintext keys in logs/tickets during remediation.

## 73. Runbook: KMS Key Disabled or Scheduled for Deletion

1. Identify key ID/version and dependent backup sets.
2. Trace who/what automation changed state via audit logs.
3. If inside the deletion waiting period, trigger deletion cancellation per approval.
4. Restore necessary policies/permissions.
5. Test decrypting a test backup.
6. Confirm restore roles and the DR region hold access.
7. Assess key compromise vs. accidental action.
8. Rotate/replace keys per incident response if needed.
9. Update inventories/dependency maps.
10. Add alerts and dual control to prevent recurrence.

If a key was permanently deleted, recovery depends on key backups/escrow or copies encrypted with another key. Never assume ciphertext can be recovered by creating a new key with the same name.

## 74. Runbook: Backup Tampering or Deletion Detected

1. Halt related lifecycle/destructive automation.
2. Preserve audit logs and forensic evidence.
3. Identify affected objects, versions, manifests, and signatures.
4. Check immutable/offline/cross-account copies.
5. Revoke compromised credentials/roles.
6. Inspect KMS policies and decrypt activity.
7. Select the latest verified backup.
8. Restore into an isolated environment.
9. Assess data exposure and report per incident policy.
10. Rebuild pipelines with fresh identities/keys after containment.

Never overwrite forensic evidence by writing a new backup to the same object names.

## 75. Runbook: Offsite Region Unreachable

1. Confirm whether the outage affects storage, networking, identity, or KMS.
2. Check cross-region replicas/secondary repositories.
3. Check key availability and policies in the DR region.
4. Verify backup catalogs/manifests have copies.
5. Provision the restore environment in a healthy region.
6. Grant short-lived restore identities.
7. Restore a verified backup.
8. Check WAL chain/PITR coverage.
9. Run application validation and cut over per DR plan.
10. Once the region recovers, reconcile backup replication gaps.

## 76. Runbook: Retention Accidentally Deleted Needed Backups

1. Stop lifecycle jobs or fix the faulty policy.
2. Check versioning, soft-delete, immutable copies, and cross-account repositories.
3. Identify affected backup chains/WAL ranges.
4. Assess remaining recovery points and RPO impact.
5. Restore objects if the provider supports undelete/version restoration.
6. Verify manifests/checksums/key access.
7. Test restoring the chain.
8. Update the catalog.
9. Review lifecycle selectors/tags/prefixes.
10. Add dry-runs, approvals, and alerts before subsequent deletions.

## 77. Runbook: Suspected Ransomware Compromise of Backup Credentials

1. Revoke/disable compromised service identities.
2. Halt upload/delete jobs potentially controlled by the attacker.
3. Protect immutable/offline copies and audit logs.
4. Audit object deletions/version deletions/retention changes.
5. Audit KMS decrypt/disable/deletion activity.
6. Identify backups created prior to compromise.
7. Verify signatures/checksums from an independent trust domain.
8. Restore into a clean-room environment.
9. Rotate credentials/keys per incident response plan.
10. Rebuild pipelines with new identities and test.

Never use backups created after compromise without verifying integrity and provenance.

## 78. Backup Security Design Checklist

### Encryption

- Are backups, WAL, catalogs, manifests, and staging encrypted?
- Are encryption at rest and in transit verified?
- Is client-side encryption needed per threat model?
- Are key IDs/versions cataloged?
- Have key rotation/recovery been tested?

### Retention and Integrity

- Does retention meet RPO/RTO/compliance?
- Are WAL dependencies and incremental chains preserved completely?
- Are immutable/WORM copies present?
- Are manifests/checksums/signatures protected?
- Are legal holds and deletion obligations handled?

### Offsite

- Do copies live outside the host/site/account failure domain?
- Are cross-region/cross-account workflows functional?
- Are KMS keys ready in DR?
- Are archive/replication lags alerted?

### Access Control

- Do backup writers lack delete/admin rights?
- Are restore readers granted temporary access?
- Are retention and KMS admins separated?
- Is MFA/dual approval required for destructive operations?
- Are audit logs independent and immutable?

### Restore

- Periodic restore drills?
- PITR chain verified?
- Restores with old keys and DR roles tested?
- Actual RTO measured?
- Runbooks and owners up to date?

## 79. Sample Permissions Matrix

| Action | Backup writer | Restore operator | Retention admin | Key admin | Auditor |
|---|---:|---:|---:|---:|---:|
| Create backup | Yes | No | No | No | No |
| Upload object | Yes | No | No | No | No |
| Read/download | Staging prefix if needed | Yes, temporary | Not by default | No | Metadata |
| Decrypt/unwrap key | Encrypt-only if supported | Yes, with approval | No | Manage policy | Audit |
| Delete object/version | No | No | Per policy/approval | No | No |
| Modify retention/Object Lock | No | No | Yes, dual control | No | Read audit |
| Rotate KEK | No | No | No | Yes, dual control | Read audit |
| Read audit logs | No | Not by default | No | No | Yes |

This matrix is a reference. Map to exact provider actions and audit inherited permissions; an account-level high-privilege role can override prefix-level restrictions.

## 80. Common Misconceptions

**"Encrypted backups at rest mean no administrator can read them."** No. SSE can return plaintext to authorized callers.

**"TLS is enough to protect backups."** No. TLS secures transit; objects still require encryption at rest/client-side per threat model.

**"Checksums prove attackers didn't modify backups."** Not if attackers can alter both backups and checksums. Signatures/immutable copies are needed.

**"Existing backup files mean restore will work."** Not if keys, catalogs, WAL chains, or tool formats are lost.

**"KMS keys can be deleted after rotation."** Not while older backups still depend on that key version.

**"Cross-region copies decrypt automatically."** No. Key policies, identities, and KMS availability in the DR region are required.

**"Versioning equals immutability."** No. Old versions can still be deleted if an identity holds delete-version permissions.

**"An offsite bucket in the same account stops ransomware."** Not if shared credentials/admins can delete both.

**"Backup writers need admin privileges to run."** No. Grant only permissions required by the backup method and objects.

**"`pg_dump` includes all cluster globals."** No. Roles/tablespaces and cluster-wide metadata need separate workflows.

**"Base backups do not need WAL."** Physical backups normally require matching WAL for consistency/recovery and PITR.

**"WAL archives do not need base backups."** No. A WAL chain needs a matching base backup to rebuild a database.

**"Retention is just a number of days."** No. Dependency chains, keys, legal holds, and restore metadata must be preserved.

**"Backup job exit code 0 is enough."** No. Uploads, integrity checks, and test restores are still required.

**"Restoring to staging carries no data risk."** No. Production backups still hold sensitive data and trigger application side effects.

**"Destroying keys is a simple way to erase data."** No. Keys may span multiple backups; cryptographic erasure requires careful design and approval.

**"Object Lock protects against every incident."** No. It does not guarantee confidentiality, key availability, or correctness of new backups.

**"Immutable backups need no auditing."** No. You must still detect policy, key, and restore permission changes.

**"Frequent backups guarantee good RPO."** Not if WAL archive lag or broken restore chains exist.

**"Having backups means meeting RTO."** Not if provisioning/decryption/downloading/replay/validation take too long.

## 81. Practice Exercises

### Exercise 1 — Backup Classification

Distinguish `pg_dump`, `pg_basebackup`, WAL archives, and storage snapshots. Which recovery scenarios fit each type?

### Exercise 2 — Threat Model

An object storage administrator can read objects via API. Does SSE-KMS protect contents against this identity? When is client-side encryption required?

### Exercise 3 — Encryption at Rest

Compare volume encryption, filesystem encryption, object SSE-KMS, and backup-tool encryption. Choose layers for a production backup repository.

### Exercise 4 — Encryption in Transit

Explain TLS and hostname verification. Why is `sslmode=verify-full` stronger than encrypting connections without verifying server identity?

### Exercise 5 — Client-Side Encryption

Design a `pg_dump` -> authenticated encryption -> object storage pipeline. Which metadata must be saved to restore?

### Exercise 6 — Envelope Encryption

Diagram the DEK/KEK flow: generate DEK, encrypt backup, wrap DEK, store wrapped DEK, unwrap on restore. Why doesn't KMS need to receive all backup bytes?

### Exercise 7 — AEAD

Explain confidentiality and integrity/authentication in AES-GCM or ChaCha20-Poly1305. Why is nonce reuse dangerous?

### Exercise 8 — Checksums and Signatures

An attacker holds write access to objects and manifests. Why is a plain SHA-256 checksum insufficient? Design a signed manifest using a separate signing key.

### Exercise 9 — Key Rotation

A repository holds 2-year-old backups encrypted with KEK v1. Design rotation to KEK v2 while keeping older backups restorable.

### Exercise 10 — Key Deletion

If KEK v1 is deleted while old backups still have a 5-year retention, what is the consequence? Design a key inventory/deletion guard.

### Exercise 11 — Key Recovery

A DR region cannot access the primary region's KMS key. List preparation steps so restores can still decrypt in DR.

### Exercise 12 — Secret Handling

Evaluate the risks of passing passphrases via command-line arguments, shell history, or CI logs. Propose secret managers/short-lived credentials.

### Exercise 13 — Retention

Design a retention schedule with hourly for 48 hours, daily for 30 days, weekly for 12 weeks, and monthly for 12 months. Which additional dependencies must be kept?

### Exercise 14 — Full/Differential/Incremental

Compare restore chains for full + incremental vs. full + differential. What are the impacts on storage and RTO?

### Exercise 15 — WAL Retention

A base backup is kept for 30 days and PITR is required across all 30 days. Why must WAL archives be kept continuously along the recovery chain?

### Exercise 16 — Legal Hold

A backup passed normal retention yet sits under legal hold. Design an exception so lifecycle automation never deletes that object.

### Exercise 17 — Immutable/WORM

Distinguish versioning, governance retention lock, and compliance retention lock. Which mechanism stops administrators from deleting objects early?

### Exercise 18 — Offsite

A backup is stored on a separate volume on the same host. Why isn't it offsite yet? Design at least two independent failure domains.

### Exercise 19 — Cross-Account

Design a production backup role permitted only to `Put` into a prefix in the backup account. Which permissions must be denied?

### Exercise 20 — Cross-Region

A primary region suffers an outage. List all storage, KMS, identity, network, catalog, and WAL dependencies needed in the DR region.

### Exercise 21 — Staging

A backup tool writes plaintext files to local staging before uploading. Design permissions, encryption, cleanup, and failure recovery.

### Exercise 22 — PostgreSQL Backup Role

Create a replication-only role for `pg_basebackup`. Why avoid granting superuser? List `pg_hba`/TLS settings to verify.

### Exercise 23 — Logical Dump Permissions

A `pg_dump` completes yet misses rows due to RLS. Explain the risk and design roles/validation for policy-compliant complete backups.

### Exercise 24 — Separation of Duties

Separate backup writer, restore reader, retention manager, key admin, and auditor. Why should all permissions not belong to one service account?

### Exercise 25 — Auditing

Design audit events to log for object upload/download/delete, KMS decrypt, retention changes, and restore actions. Where should logs be stored?

### Exercise 26 — Backup Catalog

An incremental backup's files survive while its catalog is lost. Which metadata/dependencies are needed to reconstruct the chain?

### Exercise 27 — Restore Verification

Design a workflow verifying checksums, signatures, encryption metadata, WAL continuity, and PostgreSQL startup. Why does each step prove a different property?

### Exercise 28 — RPO/RTO

A system requires a 15-minute RPO and 2-hour RTO. Propose schedules for base backups, WAL archiving, offsite replication, and restore tests.

### Exercise 29 — Restoring from Logical Dumps

Create a custom-format `pg_dump`, verify with `pg_restore --list`, and restore into an isolated database. Which roles/globals must be prepared separately?

### Exercise 30 — Physical/PITR Restore

Design a procedure to restore a base backup and replay WAL to a `recovery_target_time`. How should timeline history and WAL gaps be checked?

### Exercise 31 — Snapshot Consistency

Distinguish crash-consistent and application-consistent snapshots. Why do simultaneous multi-volume snapshots require orchestration?

### Exercise 32 — Compression/Encryption

Why do pipelines usually compress before encrypting? Measure CPU, storage ratio, and restore duration for both orderings.

### Exercise 33 — Deduplication

Explain why encrypting every file with a random DEK lowers dedup efficiency. State the risks of convergent encryption.

### Exercise 34 — Lifecycle Rules

A rule deleting objects after 30 days accidentally deletes a parent full backup still used by an incremental chain. Design dependency-aware cleanup.

### Exercise 35 — Restore Staging Security

Restore a production database into staging for developers. Design network isolation, masking, access approval, outbound restrictions, and cleanup.

### Exercise 36 — Ransomware

An attacker compromises production admin credentials and deletes backups in the same account. Design cross-account immutable copies, identity isolation, and key controls.

### Exercise 37 — KMS Key Disabled

Backups remain intact yet decryption fails because a key is disabled. Write a runbook checking key state, audits, policies, approvals, and test restores.

### Exercise 38 — Archive Outage

The archive destination is unreachable for 20 minutes during heavy WAL generation. Design alerts, disk headroom, retries, and PITR continuity checks.

### Exercise 39 — Retention/Privacy

A customer requests personal data deletion while immutable backups remain locked for 90 days. Propose coordination across data governance, legal holds, restore deletion replay, and key-scope analysis.

### Exercise 40 — End-to-End Backup Security Design

A company operates production PostgreSQL:

- 8 TB of transactional data.
- 5-minute RPO, 90-minute RTO.
- Daily physical base backups, incrementals every 6 hours.
- Continuous WAL archive.
- Two cloud regions and a separate backup account.
- Data contains customer PII.
- One team operates databases; one security team manages KMS.
- Must retain daily 35 days, weekly 6 months, annual 7 years.
- Ransomware/credential compromise is in the threat model.

Design:

1. Encryption at rest/in transit/client-side suited to the threat model.
2. DEK/KEK strategy, key rotation, and DR-region recovery.
3. Backup/WAL/catalog/manifest retention dependencies.
4. Offsite cross-account/cross-region immutable copies.
5. IAM/PostgreSQL roles following least privilege and separation of duties.
6. Object Lock/legal hold and lifecycle rules.
7. Independent audit logging and alerts on destructive actions.
8. Restore runbook, PITR, and data validation.
9. Restore drills proving RPO/RTO with older key versions.
10. Incident response when backups are deleted, keys are disabled, or archiving breaks.

## Conclusion

**PostgreSQL backups are sensitive data assets and must be protected like production data.** Encryption at rest/in transit/client-side, integrity checks, and key management safeguard confidentiality/integrity—yet matter only if keys remain recoverable in time. Envelope encryption and KMS manage DEKs/KEKs, while key rotation must keep every backup inside retention decryptable.

**Retention must understand the full recovery chain.** Full/incremental/differential backups carry distinct dependencies; physical base backups require continuous WAL for PITR; manifests, catalogs, timeline histories, and key versions must also be retained. Lifecycle automation needs dependency-aware cleanup, legal holds, and immutable/WORM controls to prevent accidental deletion or ransomware.

**Offsite backups require independent failure domains and administrative control.** Cross-account, cross-region, immutable storage, short-lived service identities, least privilege, and separation of duties reduce the chance one credential compromise destroys both primary and backups. Storage permissions and KMS decrypt permissions are two separate layers; test both in DR.

Finally, **test restores prove backups work**. Verify checksums/signatures, key access, WAL continuity, PostgreSQL recovery, business data, and restore duration in isolated environments. A backup is complete only when it can be found, read, decrypted, restored, and verified within committed RPO/RTO.
