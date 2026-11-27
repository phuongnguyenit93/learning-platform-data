# Object Versioning, Immutability, and Accidental Deletion Protection

Object storage is widely used to store images, videos, documents, data exports, logs, and backups at large scale. Service scalability and durability alone do not protect data from every mistake. An authorized user can still accidentally overwrite an object, delete an entire prefix, misconfigure a lifecycle rule, or have credentials compromised and delete data en masse. Replication can also propagate a deletion or malicious payload elsewhere.

To protect data, storage architectures must design **versioning, immutability, retention, legal holds, soft delete, Object Lock, access controls, and recovery workflows** together. These mechanisms relate closely yet do not replace one another. Versioning retains prior versions; immutability blocks edits/deletes for a duration or under a policy; retention and legal holds govern how long data must be preserved; soft delete provides a recovery window after deletion; Object Lock is a suite of object-protection capabilities offered by certain services.

In the **CLOUD_ARCHITECTURE** module, this lesson helps you design storage meeting reliability, security, cost, and operations under a Well-Architected mindset. The goal is to answer: **if an object is overwritten, accidentally deleted, a production account is compromised, or a legal preservation request arrives, can the organization prove the data is intact and restore the right scope?**

## 1. Distinguishing Object Versioning, Immutability, and Retention

| Concept | What it does | What it does NOT automatically guarantee |
| --- | --- | --- |
| **Object versioning** | Stores multiple versions of the same object key when enabled and configured properly | Does not stop someone with permissions from deleting all versions or the bucket |
| **Immutability** | Prevents an object/version from being modified or deleted under policy-protected conditions | Does not automatically protect external metadata, bucket deletion, or reader apps |
| **Retention** | Defines the minimum time data must be kept | Does not mean data must be kept forever |
| **Legal hold** | Preserves objects until validly released, typically for legal/investigative needs | Does not automatically define retention duration or approval authority |
| **Soft delete** | Marks deleted data so it can be recovered within a window | Not an independent backup and can share administrative blast radius |
| **Object Lock / WORM** | Locking mechanism blocking overwrites/deletes by retention or hold | Does not automatically protect credentials, encryption keys, apps, or other copies |
| **Replication** | Copies objects/versions to another bucket, account, or region | Does not create an independent backup; deletions may replicate |
| **Backup** | Creates copies for point-in-time/scoped recovery | Worthless without restore testing and protected delete permissions |

**WORM (Write Once, Read Many)** is the principle of writing once and permitting only reads within the protection scope. A WORM system disallows altering locked content for the specified duration, even if a user with standard write permissions tries to replace it. Specific mechanisms depend on the service: some lock per object version, others use container/bucket-level retention policies or immutable backup vaults.

### Why Layering Matters

An invoice record might have versioning enabled. That allows recovery from overwrites, yet a user permitted to delete all versions can still wipe everything. If the current version is protected by retention, version deletion is blocked during that period. If a legal hold is active, data stays preserved under legal mandate even after normal retention expires. A copy in another account also enables recovery if the production account is compromised.

## 2. Object Keys, Version IDs, and Version Lifecycles

In object storage, objects are typically identified by bucket/container and key. With versioning enabled, a single key can have multiple versions, each with its own identifier. A new PUT typically creates a new version rather than modifying the old version's contents. A DELETE may create a delete marker or soft-delete state depending on the service.

~~~mermaid
flowchart TB
    KEY["Object key: invoices/2026/INV-001.pdf"]
    KEY --> V1["Version v1"]
    KEY --> V2["Version v2"]
    KEY --> V3["Version v3 (current)"]
    KEY --> DM["Delete marker / soft-deleted state"]
    V1 -->|Recoverable| RESTORE["Restore version"]
    V2 -->|Recoverable| RESTORE
    V3 -->|Read current version| CURRENT["Current object"]
~~~

Conceptual illustration. Version naming, delete markers, soft delete, and versioned read operations differ by provider. Verify API and policy behavior before writing runbooks.

### Common Operations

- **PUT/overwrite:** writes a new object at the same key; if versioning is enabled, creates a new version.
- **GET current:** reads the current version per service rules.
- **GET specific version:** reads an exact version by version ID or generation.
- **DELETE:** may create a delete marker/soft-delete marker instead of immediate physical deletion.
- **Delete specific version:** removes one exact version; may be blocked by retention/object lock.
- **List versions:** lists current and noncurrent versions for inventory, recovery, and lifecycles.

### Versioning Has a Cost

Every upload or overwrite can consume additional storage. If an application continually writes to the same key, version counts can grow rapidly; temp files, incomplete multipart uploads, and delete markers also increase management overhead. Define lifecycle rules for noncurrent versions, ensuring policies never purge versions still under retention or legal hold.

### Choosing Object Keys to Reduce Risk

For critical data, immutable or version-identified keys are easier to audit than keys overwritten repeatedly. For instance, store files by UUID/content hash and keep a metadata pointer referencing the current version. Ensure pointer updates use concurrency control; never treat random keys as access control in place of IAM.

## 3. Enabling Versioning and Understanding Delete Markers

Versioning enables recovery from operational mistakes while older versions remain. Keep in mind:

1. Versioning generally must be enabled before the write/delete needing recovery occurs; enabling it later does not recreate lost versions.
2. Suspended/disabled versioning has different semantics from active versioning; check exact state.
3. A delete may create a delete marker hiding the object from default GETs while keeping older versions intact.
4. Deleting a delete marker can make the prior version current again; this operation must be tightly controlled.
5. Anyone permitted to delete specific versions can eliminate recoverability unless protected by retention/immutability.

### Accidental Overwrite Scenario

An application uploads the wrong invoice PDF to an existing key. With versioning enabled:

- The new upload becomes current.
- The old version remains readable by version ID.
- Operators identify the valid version via audits/logs/metadata and restore it or write a new current version from the good content.
- Do not delete the bad version if it serves as forensic evidence or sits under retention/legal hold.

### Accidental Delete Scenario

A user deletes a prefix containing many files. With versioning, delete markers may be created per key or follow service-specific semantics. Operators must:

- Pinpoint the exact bucket, prefix, time window, and actor.
- List versions and delete markers.
- Check retention and legal holds.
- Restore across a verified set of keys, avoiding accidental marker removal or bad copies.
- Reconcile object counts and checksums after restore.

Never run a script deleting delete markers in bulk without a dry run and verified scope.

## 4. Immutability, WORM, and Object Lock

Immutability protects content from modification or deletion for a defined duration or condition. In object storage, a common implementation is Object Lock/WORM at the object-version or storage-container level.

Two common retention modes:

- **Governance mode:** privileged operations may bypass or alter protection if the caller holds the required permissions and supplies mandatory conditions. Useful for controlled governance, though not absolute protection against admins holding bypass rights.
- **Compliance mode:** objects are protected strictly; during retention, even high-level administrators cannot shorten or delete them under service semantics. Choose this only once legal requirements and data processes are confirmed.

Services offer different names and control granularity. Never assume governance/compliance behaves identically across clouds; read service documentation and test in a sandbox account.

### Per-Version Object Lock

A locked object version cannot be overwritten or physically deleted during its protection window. Another PUT to the same key may create a new version per service rules, yet the locked version remains preserved. Therefore, distinguish:

- **Current key name** visible to users.
- **Current version** after a new upload.
- **Object-Lock-protected version**.
- **Delete marker** hiding the object from default queries.

Locking one version does not make the whole key, bucket, or external metadata immutable. Verify exact enforcement boundaries.

### Default Retention and Per-Object Retention

A bucket/container can configure default retention applied to new objects. Some services also allow per-version or policy-specific retention. Default retention reduces the risk of developers forgetting to lock objects, but can keep temporary, erroneous, or sensitive files longer than allowed. Align policies with data types and classifications.

### Retention Is Not Backup

Object Lock blocks edits/deletes for a duration, but does not guarantee applications can locate objects, encryption keys remain usable, buckets stay accessible, or logic bugs did not write bad data. You still need backups/replication, catalogs, integrity checks, and restore tests.

## 5. Retention Policies and Legal Holds

A retention policy specifies how long data must be kept. Duration may start from object creation, version lock time, or an organization-defined business event. Business, legal, compliance, and operations teams must align on calculation rules.

Illustrative examples:

| Data type | Reference retention | Considerations |
| --- | --- | --- |
| Invoices/receipts | Per applicable accounting/legal obligations | Do not pick an arbitrary year count without confirming rules and entity type |
| Security logs | Per risk level and investigation policy | Volume, access controls, personal data |
| Database backups | Per RPO/RTO and point-in-time recovery capabilities | Fulls, incrementals, transaction logs |
| Temporary uploads | Short-term per processing workflow | Do not keep indefinitely; delete safely upon expiry |
| Contract records | Contract term plus post-termination obligations | Legal holds may extend past standard retention |

Timeframes are policy decisions, not technical defaults. Require owner sign-off, documented requirement sources, and review triggers when regulations change.

### What Is a Legal Hold?

A legal hold mandates preserving data tied to litigation, investigations, audits, or legal obligations. While a hold is active, data must not be deleted by normal lifecycles even if default retention expires. Holds can target an object, a dataset, or a defined set of records.

Legal hold management must answer:

1. Who can place, view, and lift holds?
2. Which objects/versions are covered and by what search criteria?
3. How are newly arriving related objects brought under the hold?
4. Do lifecycle rules check holds before deleting?
5. Who approves lifting a hold and where is approval evidence stored?
6. Is there a complete audit trail for every hold placement and release?

Never grant broad hold-removal permissions to routine upload applications. Use separated roles, multi-step approvals, and an independent audit log.

### Retention Locks and Policy Drift

Some services allow locking retention configuration at the bucket/container level to prevent shortening retention once protection starts. This aids compliance, yet makes early misconfigurations hard to fix. Practices:

- Test policies in an environment without real data.
- Confirm timezone, start dates, and object-version behavior.
- Check whether the policy affects existing objects or only new ones.
- Restrict who can alter default retention, modes, and durations.
- Use IaC/policy-as-code to detect drift.

## 6. Soft Delete and Recovery Windows

Soft delete typically retains deleted objects or metadata for a grace period before permanent deletion. Depending on the service, it may be called deleted-object retention, recycle bin, recoverable delete, or version/delete-marker behavior.

Soft delete helps when:

- Users accidentally delete files or folders.
- A batch job deletes the wrong prefix.
- An application bug triggers premature deletes before a workflow finishes.
- Admins need to recover data within a short window.

However, soft delete does not cover every failure mode:

- Privileged users can purge permanently or shorten the recovery window.
- Once retention expires, policy deletes the data.
- Malware can encrypt objects and upload new versions; soft delete cannot distinguish good content from bad.
- If access rights, accounts, or encryption keys are compromised, data may become unreadable even if it still exists.
- Mass deletions can make bulk recovery slow and expensive.

### Soft Delete Working Alongside Versioning

When both are enabled, verify the order of operations:

1. Does deleting an object create a delete marker, a soft-delete record, or both?
2. Where are old versions kept and can they be read directly by version ID?
3. Does restoring an object remove a marker or create a new version?
4. Do lifecycle rules apply to noncurrent versions, markers, and soft-deleted objects?
5. Do retention/Object Lock rules block physical purge after the soft-delete window expires?

There are no universal cross-provider semantics. Write service-specific tests and record results so runbooks never rely on guesses.

## 7. Replication Does Not Equal Backup

Replication copies objects or changes to another bucket/container. It supports availability, user proximity, analytics, or DR. Yet if configured to replicate delete markers, overwrites, or ransomware-encrypted payloads, copies are impacted too.

| Mechanism | Purpose | Things to check |
| --- | --- | --- |
| **Same-region replication** | Creates copies within the same region or service domain | Failure domain scope, consistency, and fees |
| **Cross-region replication** | Keeps copies in another region for DR and locality | Replication lag, residency, encryption keys, delete semantics |
| **Cross-account replication** | Separates ownership and blast radius | IAM trust, destination ownership, account admins, and policies |
| **Backup copy** | Keeps recovery points per separate schedule/policy | Retention, immutable vault, catalog, and restores |

### Accidental Deletion Propagating to Replicas

Suppose an application can delete objects and replication copies delete markers. A user accidentally deletes a prefix in the source bucket; markers replicate to the destination, hiding objects from default GETs in both places. If the destination also allows version deletion and shares admin identities, a single mistake can affect both.

Mitigations:

- Separate destination accounts and owning roles; source workloads cannot delete destination copies.
- Apply retention/Object Lock at the destination when protection is required.
- Decide explicitly whether to replicate delete markers; consider replicating only required objects/versions.
- Maintain scheduled backups with independent permissions and retention.
- Drill recovery when the source is deleted, locked, or compromised.

### Replication Lag and Consistency

Cross-region replication is usually asynchronous; newly written objects may not appear at the destination immediately. Applications should not tell users a remote copy exists until confirmed. Monitor pending replication bytes, object age/lag, failure counts, and policy conflicts where supported.

## 8. Independent Backups and Immutable Backups

Backups differ from versioning in goal and scope:

- Versioning recovers earlier versions of an object within the same system.
- Backups create copies for recovery by schedule, dataset, and point in time.
- Immutable backups protect backup copies from alteration or deletion during their retention window.

A backup design may use:

1. A separate backup account/bucket managed by a dedicated role.
2. Write permissions from production while restricting deletion or retention changes.
3. Object Lock/immutable retention at the destination where required.
4. Encryption using keys with independently governed lifecycles and access.
5. A catalog or manifest recording which objects and timestamps each backup holds.
6. Checksum verification, inventories, and backup success/failure reporting.
7. Restores into an isolated zone to verify readability and integrity.

### Backups Must Not Depend Entirely on Production Credentials

If ransomware compromises a workload role able to delete both source objects and backups in the same account, the organization can lose both. Account separation, permission boundaries, vault policies, MFA/approval for destructive actions, and immutable retention shrink the blast radius. Inspect organization administrator and cloud root permissions too, not just application IAM roles.

## 9. Lifecycle Policies: Automating Without Destroying Required Data

Lifecycle policies automatically transition tiers, expire objects, purge old versions, or abort incomplete multipart uploads. They reduce cost and manual toil, yet one wrong rule can wipe data en masse.

Common actions:

- Transition current objects to lower-cost storage tiers after N days.
- Transition noncurrent versions to archive tiers.
- Delete noncurrent versions once retention ends.
- Clean up delete markers when no matching old versions remain.
- Abort incomplete multipart uploads.
- Expire objects matching prefixes/tags.

### Lifecycle Design Principles

1. **Classify first:** buckets/prefixes/tags must distinguish temp files, user content, legal records, backups, and logs.
2. **Retention first:** lifecycles must never delete data still under retention or legal hold; verify whether the service enforces this automatically or requires separate policy design.
3. **Simulate first:** inspect objects slated for transition/deletion using inventories, dry runs, or preview tools where available.
4. **Scoped canary:** apply policies to one prefix/group first, then expand.
5. **Monitor post-rollout:** counts of transitioned/deleted objects and versions, costs, archive read errors, and recoverability.
6. **Change control:** review lifecycle policies like code; never let individual teams add broad rules on shared buckets unchecked.

### Storage Tiers and Retrieval Costs

Cold tiers can cost less per GB stored while charging retrieval fees, imposing restore delays, and enforcing minimum storage durations. If applications read objects frequently, archiving them raises latency and total bills. Forecast from access patterns, not object age alone.

### Example Policies by Data Group

| Group | Suggested policy to evaluate |
| --- | --- |
| Temporary uploads | Delete after a short business-approved period |
| Infrequently accessed public media | Transition tiers as reads drop; retain versions as required |
| Invoices/receipts | Retention/legal hold per approved policy; never auto-delete early |
| Backups | Immutable retention; lifecycle cleanup after recovery window ends |
| Security logs | Age-based tiering, policy-driven retention, audited access |

Never apply a single broad lifecycle rule across a bucket mixing datasets with different retention obligations.

## 10. Access Permissions: Protecting Objects and Delete Capabilities

Object storage spans multiple permission layers: bucket/container policies, identity policies, access points, legacy ACLs if supported, key policies, retention permissions, and account admin roles. Design both read/write access and destructive permissions.

### Separation of Duties by Role

| Role | Required permissions | Permissions to restrict |
| --- | --- | --- |
| Upload application | Put objects into its assigned prefix | List whole bucket, delete versions, alter retention |
| Read application | Get objects within needed prefixes | Put/delete, alter policies, view backups |
| Lifecycle service | Execute approved lifecycle actions | Modify bucket-wide Object Lock/legal holds |
| Backup writer | Write backup copies and required metadata | Delete old backups, shorten retention |
| Restore operator | Read backups, provision targets, restore with approval | Modify source backups or delete originals |
| Compliance/legal | Place/lift legal holds per workflow | Everyday application admin rights |
| Security auditor | Read audits, inventories, policies, and reports | Modify objects or retention |

### Evaluate Delete Permissions Separately

In some services, standard object deletion differs from deleting specific versions; bypassing retention or lifting legal holds may be independent permissions. Permission names differ by provider. Do not just check policies for `PutObject`/`GetObject`; enumerate every destructive capability:

- Deleting current objects or creating delete markers.
- Deleting specific versions.
- Bypassing governance retention.
- Modifying or lifting legal holds.
- Disabling versioning or changing default retention.
- Deleting buckets/containers or altering replication/lifecycle policies.
- Deleting encryption keys or revoking key usage.

### MFA/Approval for Sensitive Actions

Actions like deleting production buckets, mass-deleting versions, shortening retention, or lifting legal holds should require approvals, step-up authentication, and auditing. Some clouds offer MFA delete, vault locks, multi-party approval, or policy guardrails; verify product support and configuration. Do not treat console login MFA as sufficient if an API role can still execute bulk deletes.

## 11. Defending Against Ransomware and Accidental Deletion

Ransomware on object storage can appear as encrypting and overwriting files, tampering with metadata, deleting versions, or deleting access keys. Layer defenses together:

- Versioning to preserve prior versions.
- Object Lock/immutable backups to protect critical copies.
- Cross-account backups to shrink blast radius.
- Least-privilege IAM separating backup writers from backup deleters.
- Anomaly detection on sudden PUT/DELETE spikes, version deletions, or policy changes.
- Conditional throttling/denials when a source displays abnormal destructive behavior if supported.
- Inventories, checksums, and baseline object/version counts.
- Procedures to isolate credentials, pause sync/replication if needed, preserve evidence, and restore cleanly.

### Early Detection

| Signal | Why it matters |
| --- | --- |
| Spike in DELETE / version deletes | Potential accidental mass delete or compromised credentials |
| Abnormal PUT frequency on existing keys | Potential bulk overwrite or encryption attack |
| Retention/Object Lock policy changes | Possible attempt to weaken protections |
| Surge in replicated delete markers | Deletions may be propagating to destinations |
| Unusual jump in version/object counts | Potential cost spike or overwrite loop attack |
| Lifecycle rule modifications | Possible setup for automated mass deletion |
| KMS/key permission changes | Risk of rendering data undecryptable |

Store audit logs where permissions and retention are independent of data buckets. If logs sit in the same account where a compromised role can delete them, evidence can be destroyed alongside data.

### Incident Response Playbook

1. **Isolate compromised identities:** revoke/rotate credentials, disable roles, or restrict networks per procedure.
2. **Preserve evidence:** retain audit logs, policy versions, request IDs, actors, and timestamps.
3. **Stop propagation:** pause affected workloads, automation, or replication if needed and safe for intact data.
4. **Determine scope:** affected buckets, prefixes, keys, versions, delete markers, retention, legal holds, and regions.
5. **Select a trusted recovery source:** immutable backups or verified versions prior to the incident.
6. **Restore to an isolated zone:** scan for malware, verify checksums, metadata, and consistency.
7. **Reconcile and reopen:** prioritize critical datasets; verify application read/write correctness.
8. **Remediate root cause:** tighten permissions, fix automation, add alerts, and re-drill.

Never restore directly into a compromised production bucket before regaining control of credentials and policies, as freshly restored data could be deleted or encrypted again.

## 12. Encryption and Key Management Design

Encryption protects object contents, yet key lifecycles require careful management. An existing object whose key was deleted or whose decrypt permission was revoked becomes unusable data.

### Common Options

- **Provider-managed keys:** the provider manages key material and rotation per service features; reduces key operations at the cost of less direct control.
- **Customer-managed keys (CMK):** the organization controls key policies, rotation, and auditing via KMS/key vault; requires managing availability and key permissions.
- **Client-side encryption:** the application encrypts before uploading; maximizes control while requiring key distribution, metadata, rotation, recovery, and compatibility management.

### Design Requirements

1. Key policies allow only appropriate workloads/roles to encrypt/decrypt.
2. Key rotation preserves readability of objects encrypted under older keys.
3. Backups and replicas have access to their respective keys at destinations/regions.
4. Key deletion enforces waiting periods, approvals, and dependency checks.
5. Key access audits stay independent of object audits.
6. Restore drills verify data can actually be decrypted.

### Encryption and Immutability Are Separate Layers

Encryption does not prevent an authorized writer from overwriting an object with garbage. Immutability does not automatically protect a key from deletion or revocation. Pair both with identity controls, backups, and auditing. With client-side encryption, backups are only useful if decryption keys and metadata are independently protected.

## 13. Object Lock and APIs: Details to Verify

Object storage services expose Object Lock/WORM with differing API models. Common concepts include:

- Enabling Object Lock on a bucket/container or at resource creation time.
- Setting default retention at the bucket/container level.
- Setting retention on a specific object version.
- Placing or removing legal holds.
- Reading retention/hold state before attempting deletes.
- Configuring replication to preserve Object Lock attributes at the destination if supported.

Some services require versioning to be enabled to use Object Lock. Some offer governance/compliance locks; others expose date-based retention APIs. Never copy commands from one provider to another without verifying semantics.

### Example Policy Logic

A document upload flow might:

1. Authenticate the uploader and authorize writes to the assigned prefix.
2. Create the object with an immutable key identifier, checksum, and classification metadata.
3. Apply default retention or explicit retention per document type.
4. Record the object version ID and metadata pointer in the database.
5. Emit an audit event with an operation ID.
6. Verify the version holds the expected retention/hold.

A deletion flow might:

1. Verify role and approval.
2. Check retention and legal holds.
3. Verify business rules and reconcile backups.
4. Delete the exact approved version/key.
5. Log the audit outcome and verify remaining versions.

### Governance Bypass and Compliance Controls

If using governance mode, treat bypass permissions as break-glass access. Require a dedicated role, multi-party approval, short TTLs, MFA, and logs shipped to an independent system. If using compliance mode, verify immutable durations/conditions and processes before enabling, as a misconfiguration can incur ongoing storage costs or conflict with data deletion obligations.

## 14. Inventories, Checksums, and Integrity Evidence

Versioning and backups show that copies exist, not necessarily that contents are uncorrupted. Inventories and checksums detect missing objects, duplicates, metadata drift, or corrupted payloads.

### Inventories

Periodic inventories can record:

- Bucket/container, key, version ID/generation.
- Size, storage tier, checksum, creation timestamp.
- Relevant encryption key/algorithm metadata.
- Retention expiration and legal hold status.
- Replication status/destination if applicable.
- Classification tags and owner.

Export inventories to storage with independent permissions and retention. If inventories sit only in the bucket being accidentally deleted, the recovery list can be lost too.

### Checksums and ETags

Checksums such as SHA-256 verify object content after upload, replication, and restore. Never assume an ETag is always the MD5 of the entire object; multipart uploads, encryption, or service implementations can change ETag semantics. Use explicit checksum APIs or checksum metadata and record both algorithm and value.

### Post-Recovery Reconciliation

A restore workflow should check:

- Object counts and total bytes per prefix/classification.
- Presence of required keys/versions.
- Content checksums compared against trusted manifests.
- Business metadata and pointers in the database.
- Application ability to decrypt and read objects.
- Permissions and retention applied post-restore.

Do not rely on object counts alone; two versions can share the same count while holding different contents.

## 15. Designing Restores: Picking the Right Version and Avoiding a Second Overwrite

During an incident, recovery must begin by **identifying a trusted timestamp** and authoritative data source. Neither the newest version is always right, nor is the oldest version guaranteed clean.

### Single-Object Restore Workflow

1. Identify the affected key, bucket, object version, and operation ID.
2. Locate the pre-incident version via audit logs, checksums, manifests, or metadata records.
3. Check that version's legal hold, retention, and read permissions.
4. Read into a staging area, scan content, and verify checksums.
5. Restore by creating a new current version from the good copy or updating the pointer per workflow; do not mutate locked versions directly.
6. Verify users read the right version, metadata stays synchronized, and audits are recorded.

### Bulk Restore

For a large prefix/bucket, prepare a manifest of objects to restore, batch sizes, API rate limits, retries, and checkpoints. Run a dry run to preview impact; restore in waves; record per-object success/failure; ensure idempotency so re-runs do not create uncontrolled copies.

### Restoring After Bucket Deletion or Account Compromise

If the source bucket is deleted, versioning inside that bucket may not suffice; recovery depends on resource undelete support and how the service stores versions. Cross-account backups, immutable vaults, and IaC to rebuild bucket policies/DNS/access points become vital. When an account is compromised, regain identity control first before opening restore permissions.

## 16. Building Data Policies by Classification

Do not apply identical retention to every object type. Classify data by value, sensitivity, legal obligations, rebuildability, and recovery cost.

| Data group | Versioning | Immutability / retention | Soft delete | Backup / replication |
| --- | --- | --- | --- | --- |
| User content | Usually helpful against overwrites | Per contract/retention rules | Useful for short recovery windows | Replication/backups per criticality |
| Invoices/receipts | Strongly consider version retention and audits | May require WORM/legal holds by regulation | Does not replace retention duties | Independent copies and restore tests |
| Security logs | Versioning not always needed for append-only logs | Immutable retention often worthwhile | Can help prevent accidental deletes | Independent account/vault |
| Backup data | Retain copies per recovery points | Immutable retention per backup policy | Not the sole protection layer | Separate account/region matched to RTO/RPO |
| Temporary files | Can disable or keep very short | Usually no WORM needed | Short window only if needed | Usually no backup |
| Analytics datasets | Versions or snapshots per pipeline | Based on rebuildability and legal rules | Can be useful | Snapshots/replication per rebuild cost and time |

This is a guiding matrix, not a default policy. A single category may contain varying sensitive fields; classification and retention must be approved by data owners alongside security/legal.

### Data Minimization and the Right to Delete

Immutability can conflict with personal data deletion requests or data minimization principles. Design upfront:

- Do we truly need to store the raw content or only a hash/metadata?
- Can personally identifying fields be separated from immutable objects?
- Can each object be encrypted with a distinct data encryption key that is destroyed when retention ends, if permitted by law/policy?
- When a legal hold arises, what workflow halts deletion?
- When retention ends, how are deletion proofs and audits generated?

Never use crypto-shredding to evade legal obligations; key destruction must be reviewed by security/legal and depends on retention rules, backup/key replication, and encryption semantics.

## 17. Case Study: Cloud Invoice and Document Vault

A rental platform stores invoices, contracts, and handover records as PDFs. Hypothetical requirements:

- Every document has an identifier and needs version traceability.
- Users can upload updated revisions, yet signed documents must be preserved.
- Some records carry legal holds.
- The app needs fast reads of the current revision; compliance needs to look up older revisions.
- Production might be compromised; backups must have an isolated blast radius.
- The system must prove restored objects match manifests/checksums.

### Data Design

One design approach:

1. The source bucket stores objects under identifier keys rather than relying solely on user-supplied filenames.
2. Versioning is enabled for document classes needing history; a metadata database tracks document ID, object key, version ID, checksum, owner, classification, and state.
3. Signed documents receive retention/immutability per approved policy; legal holds are controlled through a separate compliance role.
4. The upload app only has write permissions to its assigned prefix, with no rights to delete versions or alter retention.
5. A backup pipeline copies objects to a separate account/vault with immutable policies and independent key management.
6. Audit logs, inventories, and checksum manifests are stored where production apps cannot delete them.

~~~mermaid
flowchart TB
    APP["Document API"]
    META["Metadata database"]
    SRC["Source object bucket\nVersioning enabled"]
    LOCK["Retention / Object Lock\nLegal hold"]
    AUDIT["Audit + inventory + checksum"]
    COPY["Backup / replication pipeline"]
    subgraph BACKUP["Backup account / vault"]
        DST["Immutable object copy"]
        KEY["Independent key policy"]
    end
    APP --> SRC
    APP --> META
    SRC --> LOCK
    SRC --> COPY
    COPY --> DST
    DST --> KEY
    SRC --> AUDIT
    DST --> AUDIT
~~~

This diagram shows logical responsibilities; whether Object Lock, version metadata, legal holds, and encryption keys replicate natively depends on the service. If replication does not preserve required attributes, the pipeline must apply policies at the destination and verify after copying.

### New Version Upload Flow

1. Client authenticates and sends document ID, document type, checksum, and file.
2. API checks write permission by document owner and legal hold state.
3. Object is uploaded under the appropriate key; version ID/generation is captured from the storage response.
4. Metadata database updates via transaction/version control to point to the new object version.
5. Audit records actor, operation ID, checksum, version, and policy.
6. Backup pipeline ingests the change and confirms the destination copy holds matching protection attributes.

Never update the metadata pointer before the object upload and verification succeed. If the database commits while upload fails, the pointer targets a nonexistent object. If the upload succeeds while metadata commit fails, a reconciliation job must find orphaned objects by operation ID.

### Replacing an Erroneous Invoice Upload

If the wrong revision is uploaded:

- Do not delete the old object/version to "clean up."
- Identify the valid version via signed document records, checksums, and audits.
- Create a new current version from the valid content or update the pointer via a controlled workflow.
- Retain the erroneous version if legal/compliance requires evidence preservation.
- Record an audit entry for the correction and version linkage.

### Legal Hold Flow

When a dispute arises, compliance identifies affected documents/versions, places a legal hold using an approved role, and logs case ID, actor, timestamp, and reason. Lifecycles are verified not to delete held versions. When approved to lift the hold, the system audits the change and confirms standard retention remains enforced.

### Recovery Flow After Compromise

1. Revoke compromised production application credentials.
2. Preserve audits and inventories in the independent account.
3. Pause pipelines if they are replicating malicious content or deletions.
4. Select a pre-incident backup point.
5. Restore objects into a clean bucket, scan for malware, and reconcile checksums/manifests.
6. Restore metadata pointers and verify versions, retention, legal holds, and keys.
7. Reopen read/write access only after security sign-off.

## 18. Cost and Operability Trade-Offs

Versioning, immutability, replication, and backups improve recoverability while increasing storage usage, request counts, retrieval fees, key management overhead, and restore times. Calculate **total data lifecycle cost**, not just single-GB storage rates.

| Cost component | Driver | Control measure |
| --- | --- | --- |
| Current object storage | Active object capacity | Appropriate compression, lifecycle tiering, purging temp files |
| Noncurrent versions | Overwrites and version retention | Noncurrent lifecycles after retention/hold ends |
| Delete markers/metadata | Frequent deletes and object history | Inventories, validated marker cleanup workflows |
| Immutable retention | Mandatory retention even when unaccessed | Proper classification, approved durations, capacity forecasting |
| Replication | Copies across regions/accounts | Select datasets needing replication, measure bytes and lag |
| Backups | Full/incremental copies, logs/PITR, catalogs | Retention matched to RPO/RTO, dedupe if supported |
| Retrieval/archive | Reading cold-tier data | Restore testing, factoring retrieval fees and time |
| KMS/key operations | Encrypt/decrypt calls, audits, rotation | Appropriate key scopes and request patterns |
| Inventory/audit | Object listings, events, and logs | Tune frequency, retention, partitioning, and permissions |
| Restore operations | Copying data back, compute, and egress | Drills, batch tuning, and dataset prioritization |

### Example Storage Growth from Versioning

Assume 2 million objects averaging 4 MiB each, overwritten on average 3 times per month with noncurrent versions kept for 6 months. If every write creates a full new copy without dedupe/compression:

- One current set is roughly \(2,000,000 \times 4\text{ MiB} = 8,000,000\text{ MiB}\), about 7.63 TiB.
- Six months can produce roughly 36 million noncurrent versions assuming 3 overwrites/object/month.
- If each version is also 4 MiB, noncurrent data could reach roughly 137 TiB before compression, lifecycles, or avoiding duplicate versions.

This hypothetical scenario illustrates how versioning can multiply storage; actual numbers vary with overwrite rates, version sizes, storage implementations, multipart uploads, and policies. Measure using inventories and billing data before setting broad retentions.

### Cost Control Must Never Break Retention

Never shorten retention or disable Object Lock purely to trim bills while preservation obligations still apply. Instead, optimize key design, eliminate needless overwrites, transition tiers appropriately, clean up unprotected temp data, and apply lifecycles once retention/legal holds expire.

## 19. Testing Versioning, Immutability, and Recovery

A policy is trustworthy only once tested in a safe environment with evidence.

| Test case | Simulation | Expected result |
| --- | --- | --- |
| Overwrite object | PUT new content to same key | Prior version remains readable per policy |
| Delete object | User deletes key | Delete marker / soft delete follows exact semantics |
| Delete version | Attempt deleting a version inside retention | Blocked per policy if version is protected |
| Governance bypass | Standard role attempts bypass | Denied; break-glass role succeeds with audit |
| Compliance retention | Regular admin tries shortening/deleting | Cannot violate retention under service semantics |
| Legal hold | Place hold then run lifecycle | Object is not deleted while hold is active |
| Lifecycle | Dry-run on test prefix | Only eligible versions transition or expire |
| Replication delete | Delete source object | Destination handles delete marker as configured |
| Credential compromise | Use production role to try deleting backups | Destination/immutable vault rejects it |
| Key rotation | Rotate encryption key | Both old and new objects still decrypt |
| Restore | Recover object set from backup | Checksums, metadata, and app verification pass |
| Bulk restore | Recover large prefix | Idempotent retries, checkpoints, exact counts |

### Test Permissions Across Multiple Identities

Do not test only as an admin. Create representative identities:

- Application upload/read.
- Lifecycle automation.
- Backup writer.
- Backup restore operator.
- Security auditor.
- Compliance/legal hold operator.
- Break-glass administrator.

Run positive and negative permission tests: which identities can read/write, and which are blocked from deleting versions, altering retention, lifting holds, or deleting buckets. This catches overly broad permissions before an incident.

### Test Restores Against RTO

Pick a representative object set (including large objects, multi-version keys, encrypted files, legal holds, and dependent metadata). Measure:

- Time to locate manifests and identify valid versions.
- Time to provision/prepare the destination.
- Copy/restore throughput and throttling.
- Time for decryption, scanning, and checksums.
- Time to update metadata/application pointers.
- Time until users verify data readability.

A restore that finishes copying bytes while the app cannot parse metadata/versions or decrypt keys is still a failed restore.

## 20. Common Mistakes

1. **Enabling versioning and assuming data cannot be lost:** version delete rights, bucket deletion, and lifecycles can still destroy recoverability.
2. **Treating replication as backup:** deletes, overwrites, and ransomware payloads can replicate to destinations.
3. **Enabling Object Lock without classifying data:** temp or erroneous files get locked long-term, driving up costs and complicating deletion requests.
4. **Choosing governance mode while granting wide bypass permissions:** admins or workload roles can bypass protection.
5. **Turning on compliance retention before testing:** wrong durations may be impossible to shorten under service semantics.
6. **Confusing object keys with version IDs:** restoring or deleting the wrong version.
7. **Assuming a delete marker means physical deletion:** old versions remain or markers merely hide objects.
8. **Applying bucket-wide lifecycle rules indiscriminately:** accidentally purging legal records or unexpired backups.
9. **Not testing soft delete alongside versioning:** assuming the wrong recovery precedence for the service.
10. **Keeping backups in the same account with the same admin rights:** a production compromise can wipe backups too.
11. **Failing to protect encryption keys:** objects survive physically yet become undecryptable.
12. **Relying on ETag as a universal checksum:** multipart uploads or encryption can stop ETags from matching whole-object MD5s.
13. **Not keeping independent inventories/manifests:** after bucket loss, you do not know exactly what to restore.
14. **Checking only object counts after restore:** contents or metadata may still be wrong despite matching counts.
15. **Skipping negative permission tests:** regular identities may unexpectedly delete versions or alter retention.
16. **Ignoring noncurrent versions and retrieval fees in TCO:** actual bills exceed forecasts.
17. **Restoring straight into a compromised production bucket:** freshly recovered data can be destroyed again.
18. **Lacking legal hold ownership:** data remains locked or gets released wrongly with no accountability.

## 21. Practice Exercise and Reference Answers

A company stores contract documents and user avatars in object storage:

- 800,000 PDF contracts, some digitally signed and required to be preserved by legal policy.
- 5 million replaceable user avatars; the app routinely updates avatars at the same key.
- The production upload role currently has PUT, GET, and DELETE on the entire bucket.
- Cross-region replication is enabled, including delete markers.
- Nightly backup jobs run in the same account as production.
- Operations has never tested bulk restores and maintains no independent inventory.

### Question 1 — Which priority risks must be addressed?

**Reference answer:** The upload role can delete across the entire bucket; backups share the production account; delete markers replicate; no inventory or restore tests exist. Signed contracts need dedicated classification, retention, and legal holds. User avatars have different retention needs and require deletion controls for personal data requests.

### Question 2 — Should Object Lock compliance mode be enabled for the whole bucket?

**Reference answer:** No, do not apply it blanket-style across datasets with different retention duties. Separate buckets or prefixes/policies by classification, confirm retention with legal, and test semantics first. Signed contracts may need WORM; frequently updated avatars may need short-term versioning/soft delete or on-demand deletion policies.

### Question 3 — How should upload permissions change?

**Reference answer:** Restrict PUT to tenant prefixes or issued paths; scope GET strictly as needed; remove permissions to delete versions, alter retention, lift holds, edit lifecycle/replication rules, and delete buckets. Use separate roles for lifecycles, backup writers, restores, and compliance. Write independent audit logs.

### Question 4 — Is current replication sufficient against accidental deletion?

**Reference answer:** No. Because delete markers replicate, source deletions hide objects at the destination. Re-evaluate replication settings, separate destination accounts and permissions, and add immutable retention/independent backups; always test actual service behavior.

### Question 5 — How should backups for contracts be designed?

**Reference answer:** Use a dedicated destination account/vault, write-only permissions from production as needed, policy-driven immutable retention, isolated encryption keys, and independent inventories/manifests. Allow only restore operators to read and recover with approval; never grant backup delete rights to applications.

### Question 6 — What if a contract is under legal hold while a lifecycle rule tries to delete noncurrent versions?

**Reference answer:** Holds must preserve data per service semantics. Verify policy enforcement and logs; lifecycles must never drop held versions. Run negative permission tests and configure alerts if holds are lifted or retention changes.

### Question 7 — What is needed to restore 100,000 accidentally overwritten avatars?

**Reference answer:** Inventories/version listings, the incident timestamp, a manifest of valid keys/versions, checksums, batching with checkpoints, API rate-limit handling, idempotent retries, and a staging destination. Run a dry-run/canary restore; verify object counts, content checksums, metadata, and application pointers before reopening.

### Question 8 — Why can't you compare ETags alone to verify all objects?

**Reference answer:** ETags are not necessarily whole-object MD5 hashes under multipart uploads, encryption, or certain service implementations. Use explicit checksum APIs or checksum metadata with documented algorithms, verifying after upload, replication, and restore.

## 22. Object Storage Architecture Review Checklist

- Is data classified by owner, sensitivity, rebuildability, and retention obligations?
- Is versioning enabled on the right buckets/prefixes with verified delete-marker semantics?
- Are version IDs/generations stored alongside business metadata?
- Which objects require immutability/WORM; are retention modes and durations approved?
- Do legal holds have owners, audits, placement/release workflows, and lifecycle checks?
- Do soft-delete windows, versioning, and lifecycles interact properly?
- Are version deletion, retention bypass, disabling versioning, and bucket deletion restricted?
- Does replication copy delete markers, metadata, and retention as required?
- Is the destination in a separate account/role with independent immutable backups?
- Do backups have checksums, manifests, catalogs, key access, and restore tests?
- Do encryption keys have policies, rotation, recovery, and separated permissions?
- Are inventories and audits stored independently from the production account?
- Were lifecycles previewed, canaried, reviewed, and monitored post-rollout?
- Does TCO include current/noncurrent versions, retrievals, replication, backups, audits, and restores?
- Are runbooks ready for ransomware, accidental deletion, single-object restore, and bulk restore?
- Have RTO/RPO been measured for single-object and dataset recovery?

## 23. Well-Architected Evaluation

| Pillar | Question | Evidence |
| --- | --- | --- |
| **Reliability** | Can overwrites, deletes, bucket loss, and compromise recover within RTO/RPO? | Versioning, immutable backups, inventories, restore drills |
| **Security** | Who can read, write, delete versions, bypass retention, lift holds, or delete keys? | IAM, key policies, audits, separation of duties |
| **Performance** | Do version listings, retrievals, restores, and replication meet load? | Latency, throughput, API quotas, restore benchmarks |
| **Cost optimization** | Are versions kept too long, replicas duplicated, or wrong datasets archived? | Inventories, lifecycle forecasts, cost per object/GB |
| **Operational excellence** | Are dry runs, approvals, runbooks, alerts, and retention/hold owners in place? | IaC, policy-as-code, alerts, audits, and drills |
| **Sustainability** | Is data kept only as long as required and safely purged when no longer needed? | Classification, retention, lifecycles, deletion evidence |

Sound design balances three goals: **recovering cleanly from mistakes, preserving data that must be kept, and avoiding indefinite storage of unneeded data**. Versioning enables reverting to earlier copies; immutability and retention block destruction for required windows; independent backups and restore tests prove recoverability. These layers only work when backed by access controls, encryption, auditing, and clear operational accountability.
