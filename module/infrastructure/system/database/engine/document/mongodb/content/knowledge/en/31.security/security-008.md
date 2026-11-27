# Data-at-Rest Encryption and Key Management by Deployment Model in MongoDB

## 1. The Security Problem: Data Can Leak Even When No Query Is Running

A MongoDB system can have authentication, authorization, firewalls, and TLS configured, yet still face risk if disks, snapshots, or backups are accessed unexpectedly:

- A technician removes a disk from a failed server for disposal or RMA.
- A volume snapshot is copied to another cloud account due to misconfigured IAM.
- An older backup is stored on an unencrypted disk.
- Data is migrated from one VM to another during operations.
- Infrastructure staff without business-data clearance gain access to WiredTiger files.
- An encryption key is disabled, preventing the cluster from starting or restoring from backup.

**Encryption at rest** protects bytes while they reside on storage media, especially if an unauthorized party without the decryption key obtains a copy of the data.

**Key management** determines who can decrypt, how keys are rotated, post-incident recovery, audit compliance, and the impact of losing or revoking a key.

For MongoDB, implementation differs across:

1. **MongoDB Atlas** — managed service with default encryption and optional **customer-managed keys (CMK)**.
2. **Self-managed MongoDB Enterprise** — supports WiredTiger's **Encrypted Storage Engine**, with **KMIP** or a **local keyfile**.
3. **Self-managed MongoDB Community** — lacks Enterprise's Encrypted Storage Engine; data can be protected via OS, disk, or cloud block-storage encryption.
4. **Client-side encryption architecture** — encrypts fields before sending to MongoDB; this is a different protection layer and does not replace analyzing data-at-rest protection.

> **Overarching principle:** strong data encryption paired with weak key management does not deliver the expected protection. Likewise, disk encryption **does not** replace TLS, authentication, authorization, backup protection, or runtime host access controls.

---

## 2. Define the Right Protection Goal Before Choosing Technology

The same MongoDB cluster has multiple risk surfaces:

| Scenario | Does Encryption at Rest Help? | Additional Controls Needed |
| --- | --- | --- |
| Attacker steals a disk copy **without the key** | Yes, this is its core goal | KMS/key isolation |
| Snapshot or volume outside the running host | Yes, if encrypted and keys are managed properly | IAM, snapshot access policies |
| Attacker logs into MongoDB as a user with read rights | **Insufficient** | RBAC, authentication, auditing |
| Attacker compromises `mongod` process/memory while key is loaded | **Insufficient** | Host security, process isolation, monitoring |
| Traffic between application and MongoDB is sniffed | No | TLS, certificate validation |
| Sensitive data must stay hidden from the server itself | No | CSFLE/Queryable Encryption with proper key management |
| Exported JSON/CSV file sent over email | Not automatically | Encrypt output and delivery channel |
| Decryption key is permanently deleted | Can make data **unreadable** | Key backup/recovery, lifecycle governance |
| Encryption works, yet users hold overly broad roles | Does not solve over-privileged access | Least privilege, role reviews |

A key architectural question:

> **Who must be prevented from reading the data, and in which state of the system?**

If the goal is solely protecting against **stolen disks**, disk encryption can suffice under proper conditions. If the goal is preventing **DBAs or the MongoDB process** from reading a sensitive field, evaluate client-side encryption. If the goal is preventing **network eavesdropping**, use TLS.

---

## 3. Distinguishing Three States of Data

```text
Application memory
       |
       |  Data in transit
       v
TLS connection
       |
       v
mongod memory / query execution
       |
       |  Data at rest encryption boundary
       v
WiredTiger / filesystem / storage volume
       |
       v
Disk, snapshot, backup media
```

### 3.1. Data at Rest

Data written and stored on:

- Database storage files.
- Journals and related files, depending on encryption layer.
- Storage volumes, virtual disks, and snapshots.
- Backup archives, object storage, or external disks.

**Check the actual boundary of each encryption layer.** Encrypted Storage Engine, full-disk encryption, and encrypted backup archives do not share identical boundaries; for example, application logs, core dumps, and an external `mongodump` export may fall outside ESE's scope.

### 3.2. Data in Transit

Data moving across networks:

- Client ↔ `mongod`/`mongos`.
- Replica set members ↔ one another.
- Shards/config servers/routers.
- KMS/KMIP ↔ MongoDB or cloud control planes.

Protect with **TLS**, hostname/certificate verification, and network access controls.

### 3.3. Data in Use

Data actively queried or processed in memory:

- Standard storage encryption must decrypt data for the database to operate.
- Legitimate authorized users still receive plaintext.
- Secrets in memory require host/process security.

If you need to reduce trust placed in the database server, examine **Client-Side Field Level Encryption (CSFLE)** or **Queryable Encryption**, keeping query limits and separate key vaults in mind.

---

## 4. Layered Encryption Model — Architectural Overview

```text
                        Application
                             |
                             | TLS
                             v
                       MongoDB Server
                             |
        +--------------------+--------------------+
        |                                         |
        v                                         v
 Data files / WiredTiger                    DB process memory
        |
        +--> ESE database-level encryption
        |         (MongoDB Enterprise or
        |          Atlas with configured CMK)
        |
        v
 Filesystem / storage volume
        |
        +--> volume-level encryption
        |         (cloud storage, LUKS, BitLocker...)
        |
        v
 Physical disks / cloud snapshots
```

Layers **can coexist**. For example, Atlas Core encrypts cloud volumes by default; enabling CMK database-level encryption adds another encryption layer.

However, **multiple layers do not eliminate all risks**: if the same service account can access both the database and the keys, excessive privileges remain a hazard.

---

## 5. AES-256, Envelope Encryption, and Key Types

In key management, distinguish:

| Term | Target | Purpose |
| --- | --- | --- |
| **Data Encryption Key (DEK)** | Encrypts actual data | Encrypts data bytes directly |
| **Key Encryption Key (KEK)** | Encrypts another key | Protects DEKs/master keys |
| **Master Key** | Root key in a hierarchy | Protects database keys or intermediate key material |
| **Customer-Managed Key (CMK)** | Key managed by customer in KMS | Lets organization own/govern key lifecycle and permissions |
| **Key version** | Material version of a logical key | Preserves decryption of older data across rotations |
| **Key ID / key ARN / key URI** | Key identifier in KMS | Safer to handle than raw key material, still operational metadata to govern |

### 5.1. Envelope Encryption

Instead of encrypting every data page directly with a single customer master key, multiple tiers are used:

```text
Customer-managed key (CMK) / external master key
                        |
                        v
       Encrypt/wrap MongoDB master key
                        |
                        v
          MongoDB master key (wrapped)
                        |
                        v
            Encrypt database keys
                        |
                        v
            Per-database encryption keys
                        |
                        v
              Encrypt database files
```

In Atlas Core with CMK, MongoDB documentation describes: the CMK encrypts **MongoDB Master Keys**, MongoDB Master Keys encrypt **per-database encryption keys**, and those database keys protect WiredTiger data.

### 5.2. Why Multiple Key Tiers?

- Avoids sending all data to KMS to encrypt every block.
- Reduces KMS operations and latency.
- Enables **changing key wrapping** without necessarily rewriting all data.
- Gives each node/database distinct key material per architecture.
- Lets IAM/KMS govern the CMK outside the database.

### 5.3. Key Rotation Does Not Equal Data Re-Encryption

At least three distinct operations exist:

1. **Rotate CMK/key version**: manages key material inside the customer key provider.
2. **Rewrap/rotate master key**: creates or re-encrypts the intermediate key layer.
3. **Rotate data encryption keys and re-encrypt data**: replaces keys protecting data pages, often requiring rebuild/initial sync or dedicated procedures.

These differ in scope, cost, duration, and recoverability.

---

## 6. Deployment Model 1: Default MongoDB Atlas

Per current MongoDB Atlas documentation, **encryption at rest is always enabled**, uses **AES-256**, and cannot be turned off.

### 6.1. Atlas Core

For Atlas Core:

- The cloud provider encrypts storage volumes.
- The cloud provider operates default key management.
- No manual key setup is required for storage volume encryption.
- You can add **database-level encryption with a customer-managed key** depending on tier/deployment support.

```text
Default Atlas Core

MongoDB data
     |
     v
Cloud storage volume encryption
     |
     v
Encrypted cloud disk/snapshot
     |
     +--> cloud provider-managed key
```

**Do not claim** default volume encryption means the company owns a customer-managed key. Those are two different concepts.

### 6.2. Atlas Infinite

2026 documentation also describes **Atlas Infinite** (public preview). With separated compute/storage, data is encrypted at the database level on the compute node **before reaching shared storage**; MongoDB manages default keys per organization and rotates them periodically.

During public preview:

- Customer-managed keys are supported via **AWS KMS**.
- Do not assume Azure Key Vault or Google Cloud KMS already has matching CMK support for Atlas Infinite.
- Cross-project/cross-organization restore restrictions apply.

**Do not extrapolate every Atlas Infinite feature to all Atlas Core/Flex tiers or MongoDB Server editions.** Check your exact edition/plan and deployment options.

### 6.3. Shared Responsibility Model

Atlas operates the MongoDB-managed platform components. Customers remain responsible for:

- Who can create clusters?
- Who can read data?
- Who can enable/disable key management?
- IAM permissions of the KMS principal?
- Key lifetimes and retention?
- Metadata/data classification?
- Backup retention and incident response?
- Access auditing and alerting?

“Atlas encrypts data” does not automatically prove an application satisfies every regulatory requirement.

---

## 7. Atlas CMK/BYOK: Greater Control Over Keys

**Customer-managed keys (CMK)** are also called **Bring Your Own Key (BYOK)** in Atlas contexts. You create and own keys in your cloud provider's KMS and grant Atlas permission to use them to encrypt master keys.

Providers for **Atlas Core**:

| KMS Provider | Service |
| --- | --- |
| AWS | AWS Key Management Service (AWS KMS) |
| Microsoft Azure | Azure Key Vault |
| Google Cloud | Google Cloud KMS |

Notably, Atlas documentation states the key-management provider **need not match the cloud provider hosting the cluster**, depending on supported features/config. However, cross-cloud setups increase network, IAM, latency, data-residency, and operational complexity.

### 7.1. Structure When CMK Is Enabled in Atlas Core

```text
Customer's cloud account
  |
  +-- AWS KMS / Azure Key Vault / Google Cloud KMS
         |
         | CMK: Encrypt/Decrypt MongoDB master keys
         |
         v
MongoDB Atlas project configuration
         |
         v
Atlas cluster node
  |
  +-- MongoDB Master Key  [encrypted by CMK]
         |
         +-- Per-database encryption keys
                  |
                  v
            Encrypted data files

+ Cloud provider volume encryption remains enabled.
```

**A CMK does not directly encrypt every application document.** It protects the key tier used to unwrap internal data keys.

### 7.2. Configured at Project Level, Enabled per Cluster

General workflow:

1. Create the CMK in your organization's KMS.
2. Create an IAM role/service principal/service account for Atlas per provider instructions.
3. Grant only encrypt/decrypt and required operations in the KMS integration contract.
4. Configure the provider/key ID in the Atlas project.
5. Enable customer key management on eligible clusters.
6. Verify KMS validation, cluster availability, and backup requirements.
7. Set up alerts for key state, IAM/credential errors, and network failures.

Some Atlas deployments like Flex do not support CMK. Do not assume CMK can be enabled on every tier.

### 7.3. Enabling/Disabling CMK Can Trigger Major Operations

Atlas docs note that enabling or disabling customer key management can trigger an initial sync to re-encrypt data and **rebuild MongoDB Search / Vector Search indexes**. Treat this as an infrastructure change requiring:

- Maintenance and capacity planning.
- Monitoring replication lag.
- Verifying indexes and search availability.
- Rollback/restore plans.
- Availability and cost validation.

Never treat enabling CMK as a zero-impact toggle.

---

## 8. AWS KMS with Atlas: Practical Access Control

Suppose an organization runs Atlas Core with its CMK in AWS KMS:

```text
Organization AWS Account
  |
  +-- KMS key ARN
  |
  +-- IAM role / key policy
         |
         | Atlas permitted to use key per policy
         v
MongoDB Atlas project
         |
         v
Atlas cluster with CMK
```

### 8.1. Required Components

- Accurate Key ARN or key identifier.
- Matching AWS account/region.
- KMS key state is enabled.
- IAM role/trust policy matching the Atlas integration.
- Key policy allowing the required role to use the CMK.
- Strict controls on who can **disable**, **delete**, **schedule deletion**, or edit policies.
- Auditing via AWS CloudTrail/KMS logs.
- If key rotation is enabled, understanding how the provider retains decryption for older ciphertexts.

### 8.2. Avoid Overly Broad Permissions

Never grant:

```json
{
  "Action": "kms:*",
  "Resource": "*"
}
```

unconditionally to a database service principal. This is an **anti-pattern**, not a deployment policy.

Instead, use the minimal policy specified in Atlas integration docs and audit the exact required permissions.

### 8.3. Key ID Differs from Raw Key

In Atlas configurations, applications/operators supply an **identifier** and KMS integration permissions—never copying raw 256-bit keys into source code.

Keep key material inside KMS/HSM and restrict access via **separation of duties**.

---

## 9. Azure Key Vault with Atlas

In Azure environments, CMKs live in **Azure Key Vault**.

Model:

```text
Azure subscription
   |
   +-- Key Vault
          |
          +-- Key / key version
          +-- Access policies / RBAC
          +-- Firewall / private networking
                 |
                 v
             MongoDB Atlas
                 |
                 v
            Encrypted storage
```

Key considerations:

- Identity/service principal holds exact required integration permissions.
- Scope KMS permissions to the needed vault/key, not the entire subscription.
- Check Key Vault firewalls, IP allowlists, and private endpoints per deployment method.
- Enable soft-delete and purge protection per policy and provider requirements.
- Never share credentials across dev/staging/prod.
- Verify recoverability of the **exact key version** used for snapshots.

Atlas may require extra permissions and network paths for data validation and backups. Blocking those via firewall can break features even while the cluster is running.

---

## 10. Google Cloud KMS with Atlas

With Google Cloud KMS, design includes:

- Project and KMS key ring.
- CryptoKey and key versions.
- Service account/identity for Atlas per integration docs.
- IAM permissions for encryption/decryption.
- Key region/location and data residency policies.
- Cloud Audit Logs.
- Key rotation and retention of older key versions.

```text
Google Cloud project
   |
   +-- Cloud KMS
       +-- key ring
           +-- CryptoKey
               +-- key versions
                    |
                    v
                 Atlas CMK
                    |
                    v
            MongoDB master keys
```

Disabling or destroying a **key version** still needed to decrypt data or snapshots can render backups unrestorable. Understand the difference between creating a new version and destroying an old version.

### 10.1. Key Location and Cluster Region

Do not enforce a blanket rule that “keys must be in the same region” across all Atlas deployments unless provider documentation requires it. Instead verify:

1. Current Atlas integration restrictions.
2. Cloud KMS location availability.
3. Data residency/compliance rules.
4. Latency and network availability.
5. Cross-region restore capabilities.

---

## 11. Why Can Revoking a Key Halt the Database?

A CMK controls decryption capability. If Atlas cannot use the customer-managed key:

- A running cluster may continue serving during some brief temporary network/KMS outages.
- However, restarts and validation checks may require key access.
- Atlas periodically validates credentials and key availability.
- If credentials become invalid or the key is disabled/deleted, Atlas can **disable the cluster** on the next validation check.
- A disabled cluster will not read or write data until valid permissions/keys are restored.

Do not state “losing KMS connectivity for one second immediately stops the whole cluster”—docs distinguish **key invalidation** from **temporary network unavailability**.

### 11.1. Blocking Access Differs from Deleting Data

If a CMK is disabled, data files may still exist in storage, yet the system **cannot decrypt them**. That is a severe availability risk.

If a key is permanently deleted and unrecoverable, data/backups protected by it can become **permanently inaccessible**.

### 11.2. KMS Incident Runbook

1. Distinguish network/IAM errors, expired credentials, disabled keys, and destroyed keys.
2. Preserve logs and key IDs; never reset CMK settings impulsively.
3. Identify all dependent clusters, snapshots, and search deployments.
4. Restore IAM/credentials or re-enable/recover key versions per provider.
5. Trigger Atlas/KMS revalidation via supported procedures.
6. Verify cluster health and confirm backups remain restorable.
7. Post-incident, strengthen key deletion protection, alerting, and break-glass access.

Never treat disabling CMK as a “fix” for key-unavailable errors without a vendor-verified plan.

---

## 12. Key Rotation in Atlas: Three Distinct Events

Atlas Core documentation notes that with customer KMS, Atlas automatically **rotates MongoDB Master Keys at least every 90 days** via a rolling process without necessarily rewriting all data pages.

That **does not** mean Atlas automatically rotates **the customer-managed key inside your KMS account**.

| Task | Primary Owner | Impact |
| --- | --- | --- |
| Rotate MongoDB Master Keys (Atlas Core with CMK) | Atlas | Platform-managed; rolling/maintenance behavior |
| Rotate customer CMK/key material | Organization and KMS provider | Policies, key versions, old ciphertext compatibility |
| Re-encrypt all data under a new key hierarchy | Depends on operation/migration | May require initial sync/rebuild |
| Test restoring snapshots using old keys | Organization + Atlas | Proves key history remains usable |
| Revoke a compromised key | Organization | Requires incident assessment and re-encryption scope |

### 12.1. Rotation Is Not Deleting Old Keys

A safe policy:

- Create a new key version or rotate per provider.
- Verify decryption of previously created data and snapshots.
- Retain required versions per retention policy.
- Monitor KMS access errors.
- Disable/delete old versions only after confirming **no dependent data remains** or under an approved crypto-erasure plan.

### 12.2. Rotation Needs a Recovery Runbook

“Rotate every 90 days” is a governance requirement. Real value lies in **data and backups remaining decryptable** after rotation.

A green rotation status on a KMS dashboard does not prove a six-month-old snapshot still restores.

---

## 13. Deployment Model 2: Self-Managed MongoDB Enterprise

MongoDB Enterprise on WiredTiger supports the **Encrypted Storage Engine (ESE)**.

Unlike generic block-device encryption, ESE encrypts **data files at the storage engine layer** using database keys, protected by a key hierarchy.

### 13.1. Processing Model

```text
MongoDB Enterprise mongod
       |
       +-- Data query in memory
       |
       v
WiredTiger Encrypted Storage Engine
       |
       +-- Per-database keys
       |        |
       |        v
       |  Internal key store (encrypted)
       |        |
       v        v
Encrypted files on dbPath
                ^
                |
            Master key
                ^
                |
        KMIP server or local keyfile
```

In self-managed ESE:

- Database keys are managed inside the server and written to disk only in encrypted form.
- The master key must be managed separately from the data in supported designs.
- Supported options are **KMIP key manager** (recommended) or **local keyfile**.
- Never apply Enterprise ESE options to MongoDB Community Edition.

### 13.2. Cipher Modes

Per the MongoDB Manual, Encrypted Storage Engine defaults to **AES256-CBC**. On Linux, MongoDB Enterprise also supports **AES256-GCM**. Current docs note GCM is no longer supported as an ESE block cipher on Windows.

Never switch cipher modes in production just because someone says GCM is “better” without evaluating version, FIPS, backup/restore, and operational runbooks.

### 13.3. You Cannot Enable ESE on Existing Data with One Flag

MongoDB cannot directly encrypt a `dbPath` **already containing unencrypted data** simply by adding `enableEncryption: true` and restarting.

For a replica set holding existing data, documentation prescribes a **rolling initial sync** so each member initializes a fresh encrypted `dbPath`, syncs, and steps over primary cleanly.

This requires backups, capacity, replication windows, write quorum, and a rollback plan.

---

## 14. Self-Managed Enterprise: KMIP Instead of Keeping Keys on the DB Host

**KMIP — Key Management Interoperability Protocol** — allows MongoDB Enterprise to talk to a compatible key manager appliance or service.

```text
                Key Management System
                    (KMIP server)
                         |
                  TLS + identity
                         |
                         v
               MongoDB Enterprise
                  mongod process
                         |
                         v
              WiredTiger encrypted data
```

### 14.1. Why Is KMIP Recommended?

- Separates the master key from database hosts.
- Enables auditing of key access operations.
- Supports activation, rotation, and revocation policies.
- Supports HSM/key appliances where required.
- Separates MongoDB admin rights from KMS admin rights.
- Satisfies stricter key-governance mandates than local files.

### 14.2. Required KMIP Operations

Current documentation lists operations required on the KMIP server in the default configuration:

- `Create`.
- `Get`.
- `Activate`.
- `GetAttributes`.
- `Encrypt`.
- `Decrypt`.

Legacy KMIP protocol modes behave slightly differently. Never simply open port 5696 assuming the integration works: you also need matching protocol versions, server certificates, client certificates, and key operation permissions.

### 14.3. Illustrative `mongod.conf` Configuration

```yaml
storage:
  dbPath: /var/lib/mongodb

security:
  enableEncryption: true
  kmip:
    serverName: "kmip.internal.example"
    port: 5696
    serverCAFile: "/etc/mongodb/kmip-ca.pem"
    clientCertificateFile: "/etc/mongodb/kmip-client.pem"

replication:
  replSetName: rs0
```

**This is a conceptual configuration for a fresh node or properly prepared `dbPath`**, not a safe config to apply straight to running production.

Prerequisites omitted from the snippet:

- Real hostnames and DNS.
- Issued and trusted certificates.
- TLS/hostname verification and network access.
- MongoDB Enterprise license/version.
- Remaining replica set member settings.
- Secret/certificate file permissions.
- Monitoring, backups, and recovery.

### 14.4. Verifying Server Hostnames in Certificates

MongoDB checks the KMIP server name against SAN/CN per TLS rules. If the hostname or IP does not match the certificate, `mongod` can fail to start.

Never solve this by disabling TLS verification arbitrarily. Issue certificates with the right names and CA.

---

## 15. Self-Managed Enterprise: Local Key Management

A local keyfile lets MongoDB ESE load its master key from an **administrator-protected file**.

Example configuration:

```yaml
storage:
  dbPath: /var/lib/mongodb

security:
  enableEncryption: true
  encryptionKeyFile: /etc/mongodb/ese-master-key
```

Example **creating a keyfile in a test environment** using a cryptographic tool:

```bash
# Run on a self-managed host with appropriate permissions and paths.
openssl rand -base64 32 > /etc/mongodb/ese-master-key

# Only the account running mongod may read the keyfile.
chmod 600 /etc/mongodb/ese-master-key
```

Documentation requires base64-encoded key material in the expected format, with owner/permissions meeting `mongod` requirements. In production, generate keys through controlled secret provisioning/KMS workflows and avoid exposing keys in shell history or collected logs.

### 15.1. Do Not Use the Wrong Keyfile Option

MongoDB has **two easily confused settings**:

| Name | Purpose |
| --- | --- |
| `security.keyFile` | Internal authentication between cluster members (shared secret) |
| `security.encryptionKeyFile` | Master key file for Encrypted Storage Engine |

These two files **are not the same**—never share one file just because both are called “keyfile”.

### 15.2. Local Key Management Has Severe Limitations

The MongoDB Manual emphasizes:

- Local keyfile management may fail compliance key-governance mandates.
- The keyfile must be tightly protected.
- **Key rotation is not available with local key management** under the documented master-key rotation mechanism.
- If the keyfile is lost without a compatible recovery copy, ESE data may become undecryptable.

Therefore, for systems requiring rotation, auditing, HSM, or compliance, **prefer a KMIP key manager** over a local keyfile.

### 15.3. Back Up Keyfiles Independently from Data

Never store the keyfile and encrypted backups in the same open directory. Conversely, **never forget to back up the keyfile**; data backups without the required key cannot be restored.

The sound approach is escrowing in a secure secrets manager with restricted access, offline recovery procedures, and restore drills.

---

## 16. Self-Managed MongoDB Community: Infrastructure-Level Encryption

MongoDB Community Edition lacks Enterprise's native WiredTiger Encrypted Storage Engine. That does not mean Community data “cannot be encrypted at rest”.

Infrastructure options:

- **Linux LUKS/dm-crypt**.
- **Windows BitLocker**.
- **Cloud block volume encryption**, e.g., provider-managed encrypted volumes.
- Encrypted filesystems or storage arrays.
- Managed disks with customer- or platform-managed keys per product capabilities.

```text
MongoDB Community mongod
          |
          v
      WiredTiger
          |
          v
     Filesystem
          |
          v
  Encrypted block device
  (LUKS / BitLocker / cloud)
          |
          v
     Physical disk
```

### 16.1. What It Protects

If someone obtains only an **encrypted disk image** without the key:

- Data files and filesystem blocks are unreadable.
- Other files residing inside that encrypted filesystem are also protected.
- Volume snapshots can inherit encryption per cloud/storage rules.

### 16.2. What It Does Not Protect

Once the volume is unlocked and `mongod` is running:

- The process reads files and serves data normally.
- OS root/administrators may still inspect the machine or keys.
- Authorized database users still query plaintext.
- Exports/files copied onto unencrypted external storage become plaintext.

Block-storage encryption and ESE have **different threat boundaries**. Never document that “LUKS is completely equivalent to ESE/KMIP” for every compliance standard.

### 16.3. Paths to Audit

- `storage.dbPath` and data files.
- Journals and related temporary files if separate.
- Backup destinations.
- Dumps and exported files.
- Core dumps and swap files.
- Application logs, diagnostics, and crash reports.
- CI/CD artifacts or local developer copies.

If `dbPath` sits on an encrypted volume while a backup job writes `mongodump` outside that volume, the backup may be **unprotected**.

---

## 17. Choosing a Model by Operational Responsibility

| Criterion | Atlas Default | Atlas + CMK | Enterprise ESE + KMIP | Enterprise ESE + Local Keyfile | Community + Disk Encryption |
| --- | --- | --- | --- | --- | --- |
| Primary encryption layer | Cloud volume / Atlas edition | Adds DB-level CMK layer | WiredTiger ESE | WiredTiger ESE | Filesystem/block device |
| Who operates MongoDB storage? | Atlas | Atlas | Organization | Organization | Organization |
| Who controls master/CMK? | Platform | Customer in KMS | Customer/KMIP appliance | Keyfile administrator | Customer or cloud provider |
| KMS outage impacts startup? | Per platform | Possible | Possible | Local keyfile availability | Per disk unlock/KMS |
| Who drives rotation? | Platform | Platform + customer | Customer per KMIP runbook | Limited; no local rotation workflow | OS/cloud storage |
| Setup complexity? | Low | Medium–high | High | Medium | Depends on infra |
| Key usage auditability? | Per platform controls | KMS audit | KMIP appliance audit | Limited | KMS/OS |
| Encrypts data while server processes queries? | Not client-side | Not client-side | No | No | No |

If an enterprise requires **customer control over encryption keys**, do not merely see “disk encrypted” and check the box. Verify **who can disable, delete, and rotate the keys**.

---

## 18. Encryption-at-Rest Boundaries Often Overlooked

### 18.1. Data in RAM

Even when the storage engine encrypts files, `mongod` must decrypt data to run queries. Data and some key material reside in process memory while running.

Required:

- OS hardening.
- Restricted shell/admin access.
- Memory dump/core dump policies.
- EDR/monitoring.
- Patch management.
- Incident response for host compromise.

### 18.2. Data on the Network

Always enforce TLS:

```text
App -- TLS --> mongos/mongod
MongoDB nodes -- TLS --> each other
Database or Atlas -- secure KMS channel --> key provider
```

Never disable hostname verification or skip certificate validation to rush past config errors.

### 18.3. Logs and Observability

Application logs can contain query parameters, user IDs, tokens, or document fragments if logged carelessly. ESE does not automatically encrypt logs shipped to an external logging service.

Apply data minimization, redaction, log retention, and access control.

### 18.4. Temporary Files and Backup Exports

If a job runs:

```bash
mongodump --archive=backup.archive
```

do not assume `backup.archive` is encrypted by ESE. It is an export read through the client protocol and must be protected separately via destination or pipeline encryption.

### 18.5. Snapshots

Cloud snapshot encryption can differ from MongoDB ESE. Restoring snapshots requires both ciphertext storage and valid key access; older snapshots may retain key dependencies from when they were taken.

---

## 19. Encryption at Rest vs. Client-Side Encryption: Complementary, Not Competitors

MongoDB offers two **in-use encryption** approaches:

- **Client-Side Field Level Encryption (CSFLE)**.
- **Queryable Encryption (QE)**.

With these, drivers encrypt sensitive fields **before transmitting them to MongoDB**. The server sees encrypted field values rather than plaintext for protected fields, subject to configuration and supported query types.

```text
Application
    |
    +-- encrypt selected fields
    |       using DEK
    v
TLS ciphertext payload
    |
    v
MongoDB stores encrypted field values
    |
    +-- plus encryption at rest of storage files
```

### 19.1. Two Different Key Hierarchies

**Server-side encryption at rest**:

```text
CMK / ESE master key
    -> database keys
    -> storage files
```

**Client-side encryption**:

```text
Customer Master Key in KMS
    -> wraps Data Encryption Keys (DEKs)
    -> DEKs stored encrypted in key vault collection
    -> encrypted application fields
```

Even when both name AWS KMS or Azure Key Vault, **key vaults, access permissions, and purposes** can remain separate.

### 19.2. Business Example

Document:

```javascript
{
  _id: "CUSTOMER-100",
  name: "Alice Nguyen",
  identityNumber: "<sensitive encrypted field>",
  city: "Hanoi"
}
```

With storage encryption alone, any user or DBA permitted to read `identityNumber` still sees plaintext.

With CSFLE/QE, the application controls field encryption so the server sees only ciphertext for that field; depending on mode and version, limited querying over encrypted fields is supported.

### 19.3. Limitations

- Not every operator and aggregation stage works on encrypted fields.
- Queryable Encryption and CSFLE have different compatibility/version rules.
- Key material and the key vault must be backed up and governed independently.
- Encryption/indexing/metadata add overhead and application architectural changes.
- Do not assume client-side encryption hides all metadata, document structure, or access patterns.

**Never pitch client-side encryption as an excuse to disable TLS or skip encrypted backups.** Protection layers reinforce each other.

---

## 20. Designing Least-Privilege Key Administration

An enterprise model should separate roles:

| Role | Typical Permissions | Should Not Have Unless Needed |
| --- | --- | --- |
| MongoDB DBA | Operate clusters, collections/indexes | Delete CMKs or disable all keys |
| KMS administrator | Manage policies, lifecycles, recovery | Read all application business data |
| Security auditor | View logs, key events, alerts | Decrypt data or raw key material |
| Deployment automation | Configure per environment | Wildcard admin across every project/account |
| Application runtime | Connect/query per role | Modify KMS key policies |
| Break-glass operator | Audited emergency privileges | Routine unlogged daily use |

### 20.1. Separation of Duties

Ensure no single individual can simultaneously:

1. Read all data.
2. Alter KMS key policies.
3. Delete all backups.
4. Delete audit logs.

At minimum, enforce MFA, approvals, audit trails, bounded access, and incident escalation.

### 20.2. KMS Identifiers Are Not the Only Secret

A Key ARN/URI is normally an **identifier**, not a raw secret key. Still, avoid publishing account IDs, regions, vault paths, or internal topology unnecessarily. Credentials and trust policies must always be protected.

### 20.3. Never Use One Key Across All Environments

Separate:

```text
kms/prod/customer-data
kms/staging/customer-data
kms/dev/test-data
```

to bound blast radius. Dev can use synthetic data and dedicated keys; never copy production keys onto laptops.

---

## 21. Key Lifecycle: From Creation to Safe Destruction

An unmanaged key easily becomes either a vulnerability or an outage risk.

```text
Key design and classification
             |
             v
         Key creation
             |
             v
        Activate / grant
             |
             v
           In use
             |
      +------+------+
      |             |
      v             v
   Rotate       Revoke/disable
      |             |
      v             v
 Keep old       Incident/
 versions       restore decision
      |
      v
 Confirm no live data/backups depend on old key
      |
      v
 Archive or destroy under approved policy
```

### 21.1. Key Creation

- Use KMS/HSM or a cryptographically secure random generator.
- Never derive keys from passwords, timestamps, project names, or hardcoded strings.
- Pick key algorithms and key usages matching provider/feature specs.
- Record owner, purpose, environment, rotation cadence, and retention.
- Restrict who can execute Create/Delete operations.

### 21.2. Activation and Granting Access

- Allow key usage only for principals that genuinely need decryption.
- Define separate policies for backup validation and restore.
- Restrict network egress to KMS/KMIP.
- Alert on policy changes.
- Track which key ID is active on every cluster.

### 21.3. Key Rotation

- Clarify whether it is CMK rotation, master-key rotation, or database-key rollover.
- Check snapshot compatibility and older key versions.
- Never rotate all nodes at once if the runbook requires rolling steps.
- Monitor cluster health and replication quorums.

### 21.4. Key Destruction

Key destruction impacts data availability and can be **irreversible**. Proceed only when:

- Data classification and retention rules permit it.
- Exact dependent clusters and backups are identified.
- Formal approvals are recorded.
- Recovery has been drilled or confirmed unnecessary.
- An audit trail exists.

**Crypto-shredding** can render data undecryptable, but is only valid when all plaintext copies and key backups are accounted for.

---

## 22. Self-Managed: Migrating an Unencrypted Replica Set to ESE

MongoDB docs warn **never start ESE with a new key on a `dbPath` containing unencrypted data**. Migrating an existing replica set requires a rolling initial sync.

### 22.1. Conceptual Workflow

```text
Initial replica set:
  primary     plaintext dbPath
  secondary A plaintext dbPath
  secondary B plaintext dbPath
```

Stages:

1. Back up and verify restore; confirm replica set health/quorum.
2. Prepare KMIP/keyfile, certificates, permissions, and networking for node A.
3. Point secondary A to a valid clean `dbPath` with encryption enabled.
4. Perform initial sync from a healthy source to populate encrypted data.
5. Wait for node A to become healthy and catch up.
6. Repeat for secondary B.
7. Step down the primary cleanly while preserving quorum.
8. Convert the former primary to secondary and initial-sync with ESE.
9. Verify all members, read/write continuity, and backups.

**Never** wipe a `dbPath` based on an internet snippet without verified backups and approval. Deleting data directories can cause data loss if replication is incomplete.

### 22.2. Rolling Migration Is Not Zero-Risk

Potential issues:

- Long initial sync duration.
- Insufficient oplog window.
- Disk capacity exhaustion.
- Unreachable KMS/KMIP.
- Certificate mismatches.
- Write concern failures.
- Primary elections or lag.
- Older backups retaining different encryption states.

Plan maintenance windows, monitoring, and rollback procedures.

---

## 23. Self-Managed KMIP Master-Key Rotation

MongoDB provides a master-key rotation procedure for replica set members using KMIP.

Principles:

- **Never rotate multiple replica set members simultaneously** if it risks losing write quorum.
- Rotate secondaries sequentially, wait for health, then handle the primary after a controlled stepdown.
- Use `--kmipRotateMasterKey` or the equivalent config option per MongoDB's runbook.
- The process may exit `mongod` upon completing rotation; restart normally per instructions.
- Master-key rotation **rewraps the encrypted keystore** rather than necessarily re-encrypting all data.

### 23.1. Directional Command/Config Example

```bash
# Syntax skeleton example. Do not run directly in production
# without verifying version documentation and runbook.
mongod \
  --enableEncryption \
  --kmipRotateMasterKey \
  --kmipServerName kmip.internal.example \
  --kmipServerCAFile /etc/mongodb/kmip-ca.pem \
  --kmipClientCertificateFile /etc/mongodb/kmip-client.pem
```

Production also requires `dbPath`, replication settings, ports, and normal node parameters. The snippet above is **not a complete runnable configuration**.

### 23.2. Local Keyfiles Cannot Use This Workflow

Documentation notes **key rotation is not supported with local key management** in the KMIP manner. If periodic rotation is required, adopt KMIP or plan a separate rebuild/re-encryption strategy.

---

## 24. Special Note on AES256-GCM and Filesystem Restores

MongoDB Enterprise on Linux supports the **AES256-GCM** ESE cipher. GCM is authenticated encryption requiring strict IV/counter uniqueness.

Per the MongoDB Manual:

- After certain **hot backup restores**, MongoDB can detect a “dirty” key state and roll over keys automatically where supported.
- With **cold filesystem snapshot restores**, the system may not automatically detect IV reuse, creating confidentiality and integrity risks.
- MongoDB provides `--eseDatabaseKeyRollover` specifically for this scenario.

This is **not** a routine master-key rotation option:

| Option | Target |
| --- | --- |
| `--kmipRotateMasterKey` | Rotate KMIP master key / rewrap keystore |
| `--eseDatabaseKeyRollover` | Roll over database keys in documented ESE AES256-GCM filesystem restore scenarios |

Never use the two options interchangeably. Before an ESE-GCM restore, consult your MongoDB version's runbook to prevent **IV reuse**.

---

## 25. Backups: Is Encrypted Data Alone Enough to Restore?

A backup can be completely intact byte-for-byte yet **unusable** if required keys, IAM policies, or key versions are missing.

### 25.1. Three Common Backup Types

| Backup Type | Considerations |
| --- | --- |
| Encrypted cloud volume snapshot | Needs matching KMS/storage key to restore |
| ESE filesystem snapshot | Needs ESE master key/keystore and cipher-specific restore steps |
| Logical backup (`mongodump`/export) | Output may be plaintext; protect separately |

### 25.2. Atlas Backups

Atlas encrypts snapshot volumes. When using customer-managed keys, restores can depend on the key active when the snapshot was created. If the key is invalid, the snapshot may be unrestorable.

Never just check “backup succeeded”. Test **actual restores** in an isolated environment using proper key permissions.

### 25.3. Enterprise ESE Backups

Preserve:

- Data snapshot.
- Configuration/metadata required for decryption.
- Access to the KMIP master key or keyfile recovery.
- Exact key/version mappings.
- MongoDB version and cipher options.

**Never** store raw master keys alongside encrypted data inside an unprotected shared backup.

### 25.4. Community + Disk Encryption Backups

If the backup is a snapshot of an encrypted volume, policies may inherit volume encryption. If the backup is extracted with `mongodump` and written to object storage, the output **may be unencrypted** unless the destination or archive enforces its own encryption.

---

## 26. Disaster Recovery: Two Dimensions to Test

A sound system answers both questions:

1. **Do the data files still exist?**
2. **Do the keys needed to decrypt those data files still exist and work?**

### 26.1. Scenario A — Host Lost, Key Intact

- Provision a new host.
- Restore the encrypted backup.
- Restore TLS/KMIP/KMS permission settings.
- Unlock/bind the right key.
- Run integrity checks and application smoke tests.

### 26.2. Scenario B — Data Intact, Key Lost

- Check key backups/escrow.
- Check if the provider offers soft-delete/key-version recovery.
- Do not attempt “swapping in a new key” to decrypt old ciphertext; a new key cannot unwrap old ciphertexts.
- If unrecoverable, the data may be permanently inaccessible.

### 26.3. Scenario C — Key Intact, Permission Denied

- Identify which IAM/service principal/network policy changed.
- Re-grant least-privilege access.
- Review KMS audit logs.
- Retry restart/restore per runbook.
- Never hardcode admin credentials instead of fixing identity integration.

### 26.4. Scenario D — Restoring an Old Snapshot After Rotation

- The snapshot may require an older key version.
- Never purge old key material before retention cutoffs expire.
- Drill restores in staging after every key lifecycle change.
- Validate data at the application layer, not merely that the port opens.

---

## 27. Sharded Clusters: Don't Encrypt Only the Primary Shard

A sharded cluster has multiple components:

```text
Application
     |
     v
   mongos
     |
     +--> Shard replica set A
     |       primary + secondaries
     |
     +--> Shard replica set B
     |       primary + secondaries
     |
     +--> Config server replica set
             primary + secondaries
```

### 27.1. Every Location Holding Data Files Must Be Covered

- Shard `mongod` members store collection data.
- Config server replica set stores sharding metadata and configuration data.
- Backups/snapshots of all members/shards need matching protection policies.
- `mongos` is a router rather than a data-file store like shard `mongod`s, yet its configs, logs, credentials, and endpoints still require security.

Never enable encryption only on a primary shard while skipping secondaries or config servers.

### 27.2. KMS Networking Is a Cluster-Wide Dependency

A DNS, firewall, or certificate change on KMIP can impact multiple members on restart. Provide HA/redundancy for KMIP services and verify connectivity from all hosts, AZs, and regions.

### 27.3. Key Separation by Environment and Cluster

Explicitly define whether policy uses one shared CMK across a project's clusters or separate CMKs per data classification/environment. One overly broad CMK expands blast radius; too many keys increase operational complexity.

---

## 28. Atlas and Search/Vector Search When Enabling CMK

Changing encryption-at-rest configuration affects more than database files alone.

Current Atlas documentation notes that enabling/disabling customer key management can:

- Trigger initial sync.
- Re-encrypt cluster data.
- Rebuild MongoDB Search and MongoDB Vector Search indexes.

Therefore, when planning:

1. Inventory Search/Vector Search indexes.
2. Estimate rebuild time and capacity.
3. Determine whether separate **Search Node Data Encryption/CMK** settings are required per supported Atlas configs.
4. Monitor query latency, index availability, and resource pressure.
5. Check KMS dependencies for search nodes per current documentation.

Never assume that enabling CMK on the DB cluster automatically applies the exact same key policy to **every search node, derived index, and external export**. Verify each component.

---

## 29. Multi-Cloud and Key Residency

Organizations may run MongoDB on one provider while holding CMKs in another. This introduces:

- Cross-cloud authentication.
- Network egress/IP allowlists.
- KMS endpoint latency.
- Recovery planning if one provider suffers an outage.
- Data residency and legal constraints.
- Key usage, API call, and cross-cloud network costs.
- Monitoring/auditing split across two systems.

### 29.1. Decision Example

```text
MongoDB Atlas cluster: Cloud A / Region X
CMK:                   Cloud B / Region Y

Questions:
  - Does the Atlas feature support this provider pairing?
  - Who holds the KMS role/service principal?
  - Is the cross-cloud network path reliable?
  - Does it comply with data residency?
  - If Cloud B has an outage, how do cluster restarts behave?
  - Which keys/regions are needed to restore backups?
```

**Do not choose cross-cloud key placement just to feel “more secure”.** Back it with a clear threat model and reliable KMS operations.

---

## 30. Monitoring Encryption and Key Management

Useful signals:

| Metric/Signal | Why It Matters |
| --- | --- |
| Cluster encryption enabled | Confirms control is active |
| CMK configured vs. default only | Distinguishes key ownership level |
| Key state enabled/disabled | Prevents outages from invalid keys |
| KMS credential expiration | Prevents authentication failures |
| KMS access denied count | Detects policy drift or attacks |
| KMIP connection latency/failures | Tracks KMS availability dependency |
| Key rotation due date | Governance |
| Last completed master-key rotation | Auditing |
| Unexpected key policy changes | Security incident indicator |
| Cluster/node restart failures | May indicate inability to unwrap master key |
| Replica lag and initial sync status | Critical when enabling encryption |
| Search index rebuild state | After CMK changes |
| Backup encrypted status | Prevents plaintext backup copies |
| Backup restore test success | Proves data actually recovers |
| Dependent snapshots per key version | Prevents premature old-key deletion |
| OS volume encryption state | For Community/infra models |
| Audit records for KMS usage | Detects anomalies |

### 30.1. Critical Alerts to Define

Alert on:

- KMS key scheduled for deletion.
- CMK disabled or pending destruction.
- IAM role/key policy modified.
- KMS validation failure.
- KMIP certificate nearing expiration.
- Backup restore drill failure.
- Overdue key rotation.
- DB node failing restart due to unavailable key.

### 30.2. Minimal Safe Logging

Logs may record:

```text
clusterId
environment
keyIdentifier (masked/redacted per policy)
operation
timestamp
principal
result
requestId
```

**Never log raw key material, passphrases, decrypted data, or full credentials.** If key IDs are sensitive under organizational policy, redact them in logs as well.

---

## 31. Checking Encryption Status in Self-Managed Deployments

Checks available from the host/configuration:

### 31.1. Inspect `mongod` Configuration

```yaml
security:
  enableEncryption: true
  kmip:
    serverName: "kmip.internal.example"
```

Or:

```yaml
security:
  enableEncryption: true
  encryptionKeyFile: /etc/mongodb/ese-master-key
```

This shows Enterprise ESE configuration. Always cross-check against the **effective running process** and successful startup logs—reading a config file alone does not prove the running node loaded it.

### 31.2. Inspect Command-Line Options

With appropriate privileges:

```javascript
db.adminCommand({
  getCmdLineOpts: 1
});
```

Returns active startup options. Never paste full output into public tickets, as it can leak paths, endpoints, filenames, or sensitive settings.

### 31.3. On Linux Using Encrypted Volumes

**Read-only** diagnostic commands can help:

```bash
lsblk -f

# If the valid LUKS mapping name is known:
cryptsetup status mongodb-data
```

Never run `cryptsetup luksFormat`, `mkfs`, or partition modifications on machines holding data just to “check encryption”—those commands destroy data.

### 31.4. On Windows

BitLocker includes volume-status tools, but always check the **exact volume containing `dbPath`**. Having the system drive encrypted does not prove data drives, backup drives, and pagefiles are protected.

---

## 32. Checking Status in Atlas

In Atlas, verify at least:

1. Edition/cluster tier.
2. Default encryption level per Atlas Core or Infinite.
3. Whether CMK is enabled on the **exact target cluster**.
4. Project key-management provider and key ID.
5. KMS validation status.
6. Backup/snapshot encryption and restore requirements.
7. Search node/derived index encryption settings if applicable.
8. Operator IAM roles and permissions.
9. KMS audit events and alert rules.
10. Project data residency/security policies.

### 32.1. Default Encryption Is Not Proof of CMK

Compliance reports should distinguish:

```text
Encryption at rest: ENABLED
Mechanism: Atlas default cloud volume encryption
Customer-managed key: NO
```

from:

```text
Encryption at rest: ENABLED
Mechanism: Atlas database-level + underlying volume
Customer-managed key: YES
KMS provider: AWS/Azure/GCP (per edition)
Key state: VALID
```

Writing only “AES-256 enabled” omits details needed to demonstrate customer key ownership.

---

## 33. Encryption and Performance

Encryption can affect CPU, I/O, cache, startup duration, and backup/restore operations.

| Overhead | Description |
| --- | --- |
| Encryption/decryption CPU | Depends on cipher, hardware acceleration, and workload |
| KMS/KMIP round trips | Typically during key unwrap/initialization/rotation, not every query |
| Startup latency | Depends on KMS availability and key access |
| Initial sync/re-encryption | Can take significant time on populated clusters |
| Key rotation | Requires rolling operations/maintenance |
| Backup storage | Snapshot ciphertexts, metadata, and key dependencies |
| Monitoring/alerting | Requires logs from both MongoDB and providers |
| Compliance operations | Audits, policies, drills, break-glass readiness |

### 33.1. Do Not Assume Encryption Severely Slows Every Query

AES often uses hardware CPU acceleration. Actual overhead depends on hardware, storage engine, cache hit ratio, read/write mix, and provider.

Benchmark:

- Read throughput.
- Write latency p50/p95/p99.
- CPU utilization.
- Initial sync duration.
- Node restarts with KMS.
- Backup/restore duration.
- Behavior under simulated KMS latency/failures.

### 33.2. Never Use Encryption as an Excuse to Skip Index Tuning

If a query lacks indexes and scans millions of documents, toggling ESE will not fix the query plan. Index, schema, and workload tuning remain essential.

---

## 34. Example: Security Design for a Contract-Storing SaaS App

Requirements:

- MongoDB Atlas Core.
- Tenant data isolation.
- Some contracts contain personal ID numbers.
- Backups must remain restorable for 5 years.
- Customers require CMK.
- Search by contract name is needed.

Proposed layers:

```text
SaaS Application
  |
  +-- Authenticated tenant context
  +-- Field-level policy for sensitive data
  +-- TLS to Atlas
  |
  v
MongoDB Atlas Core
  |
  +-- Default volume encryption
  +-- CMK-backed database-level encryption
  +-- RBAC / auditing / network restrictions
  |
  +-- Backups / snapshots
        |
        +-- Key dependency inventory
        +-- Restore drills
  |
  +-- Search indexes
        |
        +-- Data classification
        +-- Search-node encryption policy
```

### 34.1. Decisions to Document

- Which KMS provider manages the CMK?
- Scoped per project, cluster, or environment?
- Who can disable/delete keys?
- Is key deletion protection enabled?
- Which key versions do 5-year snapshots depend on?
- Does the personal ID field need client-side encryption?
- Are search indexes allowed to index sensitive fields?
- When a customer offboards, how are logical deletion and backup retention handled?

### 34.2. Things to Avoid

- Giving one IAM role permission to both read all contracts and delete the CMK.
- Copying snapshots into dev environments in plaintext.
- Logging `identityNumber` when the app decrypts it.
- Skipping restore drills from older key versions.
- Assuming Atlas CMK automatically encrypts exported PDFs/CSVs.

---

## 35. Example: MongoDB Enterprise in a Data Center

Requirements:

- Three-node replica set.
- Raw encryption master keys must not reside on database hosts.
- Organization has an HSM/KMIP appliance.
- Periodic key rotation required.
- Minimal downtime.

Architecture:

```text
              KMIP/HSM HA
                /    \
               v      v
            Node A  Node B  Node C
            mongod  mongod  mongod
               |      |      |
               v      v      v
            ESE dbPaths encrypted
```

### 35.1. Roadmap

1. Prepare KMIP HA, DNS, certificates, and networking.
2. Grant exact required operations/permissions.
3. Verify a test node starts with an encrypted `dbPath`.
4. Practice backup/restore + key access.
5. Plan rolling initial sync for the existing replica set.
6. Monitor health and quorum.
7. Document a per-member master-key rotation runbook.
8. Test KMIP outage and certificate expiration behavior.
9. Separate key admin, DBA, and audit privileges.

### 35.2. Why Not Use a Local Keyfile Here?

Requirements that “the master key must not reside on DB hosts” and “audited rotation” rule out manually managed local keyfiles. KMIP provides cleaner boundaries and governance.

---

## 36. Example: MongoDB Community on a Linux Host

Requirements:

- Mid-sized internal app.
- Self-managed Community.
- Prevent disk-image leakage if hardware is stolen.
- No Enterprise ESE or KMIP available.

Viable model:

```text
Application --TLS--> MongoDB Community
                         |
                         v
                       dbPath
                         |
                         v
                 LUKS-encrypted volume
                         |
                         v
                       disk
```

Mandatory responsibilities:

1. Ensure the volume holding **the actual `dbPath`** is encrypted.
2. Define unlock key/passphrase policy (TPM, recovery key, secret manager, etc.).
3. Back up the recovery key independently.
4. Encrypt backup exports too.
5. Keep sensitive data out of logs and plaintext dumps.
6. Maintain host hardening, RBAC, TLS, and firewalls.
7. Run restore drills onto a fresh host.

**Never claim Community has Enterprise's `security.enableEncryption` ESE option.** Here, protection operates at the OS/storage layer.

---

## 37. Risks of Key Reuse

One key covering too many clusters creates a huge **blast radius**:

```text
KMS key K1
  |
  +-- production cluster A
  +-- production cluster B
  +-- staging cluster C
  +-- snapshot archive D
```

If K1 is disabled or deleted, multiple systems fail together.

Conversely, creating a separate CMK per file for cluster-at-rest encryption adds needless complexity.

### 37.1. Choosing the Right Granularity

Base on:

- Environment (prod/staging/dev).
- Data classification.
- Business ownership.
- Regulatory boundaries.
- Geography.
- Restore/retention requirements.
- Cluster count.
- Operational overhead.

Example:

```text
prod-finance-cmk
prod-general-cmk
staging-cmk
dev-cmk
```

Names only illustrate policy separation; they do not prescribe fixed API key paths.

### 37.2. Be Careful Sharing a CMK Across Tenants

If multiple tenants demand independent key control, a single project-level CMK may not satisfy full tenant-specific key ownership. Evaluate separate clusters/projects or client-side per-tenant keys rather than assuming Atlas storage encryption can assign a distinct CMK per document.

---

## 38. Differences Between Rotate, Revoke, and Crypto-Delete

| Action | Meaning | Risk |
| --- | --- | --- |
| **Rotate** | Replace key material/version per policy | Old backups still need old keys |
| **Rewrap** | Re-encrypt data/master key under a new KEK | Must preserve hierarchy compatibility |
| **Re-encrypt** | Re-encrypt the data itself under a new DEK | I/O intensive, may require migration |
| **Disable** | Temporarily block key usage | Cluster/startup/restore may fail |
| **Revoke IAM grant** | Remove principal permissions | Cuts key access without changing key material |
| **Schedule deletion** | Queue key for permanent removal | Data loss risk if not canceled |
| **Destroy** | Permanently erase key material | Irreversible loss of decryption |
| **Crypto-shred** | Destroy keys to eliminate data access | Effective only if no plaintext or key copies remain |

Never use “rotate” when you mean “delete the old key”—the two actions have completely different consequences.

---

## 39. Common Implementation Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| MongoDB Enterprise won't start with ESE | KMIP unreachable, wrong cert/key | Check startup logs, KMIP/TLS/permissions |
| Enabling encryption on existing `dbPath` fails | Data is unencrypted | Rolling initial sync/migration per docs |
| MongoDB Community reports unknown/unsupported encryption option | ESE is an Enterprise feature | Use Enterprise or OS disk encryption |
| Atlas CMK cannot be enabled | Tier/deployment unsupported or missing Project Owner rights | Check requirements |
| Atlas shuts down after key policy change | Key disabled or invalid credentials | Restore KMS access per runbook |
| Running cluster won't restart after KMS outage | Cannot fetch master key on startup | HA KMS, networking, credential recovery |
| Snapshot restore fails after rotation | Old key/version lacks access | Restore permissions/key version |
| Backup exists yet yields plaintext | Logical export lacks its own encryption | Encrypt backup output/destination |
| KMIP TLS hostname mismatch | SAN/CN mismatch | Issue matching certificate |
| KMIP client certificate expired | Late PKI rotation | Renew early, alert |
| Local keyfile lost | No escrow/recovery | Potentially permanent data loss |
| DB user still reads plaintext | At-rest encryption doesn't stop valid users | RBAC/CSFLE/QE |
| Queries sniffed on the network | TLS missing | Enable TLS/cert verification |
| Atlas Search rebuilds when enabling CMK | Initial sync/re-encryption affects Search | Capacity/maintenance/monitoring |
| KMS audit log lacks expected events | Wrong principal, audit config, or operation path | Check integration and key usage |
| Dev cluster reads prod data | Weak key/data segregation | Separate keys, data, IAM, backups |
| ESE GCM cold snapshot restore hazard | IV/key reuse | Follow `--eseDatabaseKeyRollover` guide |
| Key rotation loses quorum | Multiple nodes changed at once | Rolling per-member procedures |
| Disk encryption enabled yet logs leak data | Logs fall outside disk boundary | Log redaction/encryption |
| CMK enabled yet app exports are unencrypted | CMK only protects at-rest layer | Output encryption/access policies |

---

## 40. Deployment Model Checklists

### 40.1. Atlas

- [ ] Identified Atlas edition/tier and default encryption?
- [ ] Confirmed whether customer-managed keys are actually required?
- [ ] Valid KMS provider and key location?
- [ ] Least-privilege key policy and IAM?
- [ ] Configured at Atlas project and enabled on target clusters?
- [ ] Search nodes/backups covered by matching policies?
- [ ] Key state and validation alerts active?
- [ ] Accounted for initial sync/Search index rebuild impact?
- [ ] CMK rotation schedule exists alongside understanding of Atlas's master-key rotation?
- [ ] Tested snapshot restores using older key versions?

### 40.2. Self-Managed Enterprise

- [ ] WiredTiger and Enterprise ESE available?
- [ ] Chosen KMIP vs. local keyfile per compliance?
- [ ] Verified KMIP HA, certificates, and permissions?
- [ ] Keyfile/local secrets absent from Git and logs?
- [ ] `dbPath` initialized with valid encryption state?
- [ ] Replication members/config servers share consistent security policy?
- [ ] Tested backup/restore with exact cipher mode?
- [ ] Per-member KMIP master-key rotation runbook exists?
- [ ] If using AES256-GCM, understand cold filesystem restore risks?
- [ ] Monitoring KMS-related errors, quorum, and restarts?

### 40.3. Community + Storage Encryption

- [ ] Volume/disk holding `dbPath` is encrypted?
- [ ] Recovery key/TPM/secret manager policy exists?
- [ ] Backup exports and logs are protected?
- [ ] User/root host access is hardened?
- [ ] Verified startup recovery after host loss?
- [ ] TLS and RBAC configured?
- [ ] Auditing covers key unlock and access?
- [ ] Documented that disk encryption does not protect client-side/query-in-use data?

---

## 41. Architectural Decision Questionnaire

1. Is your deployment Atlas Core, Atlas Infinite, Enterprise, or Community?
2. Are you protecting against stolen **disk images**, **snapshots**, or **DBAs**?
3. Is **customer key ownership** required, or is platform-managed sufficient?
4. Does KMS/KMIP have enough availability for startups and recovery?
5. Who can disable or delete keys?
6. Are soft-delete and purge protection enabled?
7. How long must data and backups be retained?
8. Over that span, how many key versions must stay available?
9. Are there region or data-residency requirements?
10. Must specific fields be encrypted before reaching the database?
11. How do encryption changes affect replica sync and Search indexes?
12. If the key provider is down for a day, what is the app and DR plan?
13. Have restores been tested onto a new host or region?
14. Does rotation replace CMK material or rewrap database master keys?
15. Are logs, exports, and backups verified to be protected?
16. Have CPU/I/O/KMS costs been evaluated?
17. Do you need tenant-specific key control or only project-level CMK?
18. Is audit/compliance evidence sufficient to document shared responsibilities?

---

## 42. Applied Exercises with Answers

### Exercise 1 — Default Atlas

An Atlas Core cluster has not enabled CMK.

**Question:** Is data encrypted at rest?

**Answer:** Yes. Atlas enables encryption at rest by default using cloud-provider-managed volume encryption. However, it is **not a customer-managed DB-level key**.

### Exercise 2 — Customer-Managed Key

An organization wants to revoke keys independently, retain KMS audit logs, and control decrypt permissions.

**Question:** Which Atlas model fits?

**Answer:** Atlas with CMK/BYOK on a supported deployment, paired with KMS policies, recovery, and key deletion protection.

### Exercise 3 — MongoDB Community

A team runs Community in a data center and wants disk encryption against hardware theft.

**Question:** Can they use `security.enableEncryption` like Enterprise?

**Answer:** No. Native Encrypted Storage Engine is an Enterprise feature. Use LUKS/BitLocker or storage-level encryption.

### Exercise 4 — Disk Encryption and DBAs

MongoDB has ESE enabled, yet a user with `readWriteAnyDatabase` can read data.

**Question:** Why?

**Answer:** ESE protects at-rest bytes. While running, the server decrypts data for authorized RBAC queries. Enforce least privilege and evaluate CSFLE/QE if the server itself must not see certain plaintext fields.

### Exercise 5 — Local Keyfile vs. KMIP

Security policy mandates auditing key usage and periodic master-key rotation.

**Question:** What should Enterprise choose?

**Answer:** A KMIP-compatible key manager, not a local keyfile.

### Exercise 6 — Lost Keyfile

You have an encrypted `dbPath` backup, but the local keyfile was permanently deleted.

**Question:** Can you simply generate another keyfile to decrypt it?

**Answer:** No. A new key cannot decrypt ciphertexts encrypted under the old key. You need a compatible key backup/recovery.

### Exercise 7 — Atlas Rotation

Atlas automatically rotates MongoDB Master Keys periodically when using CMK.

**Question:** Does that mean Atlas also rotates the customer's KMS CMK automatically?

**Answer:** No. Managing the CMK and its key versions belongs to customer KMS policy.

### Exercise 8 — Snapshot After Rotation

A two-year-old snapshot is protected by an older key version; the organization deletes that key version.

**Question:** What is the consequence?

**Answer:** The snapshot may become unrestorable. Retain older key versions per retention policy and run restore tests.

### Exercise 9 — Logical Backup

MongoDB Enterprise ESE is enabled. The team runs `mongodump` onto an unencrypted USB drive.

**Question:** Is the output guaranteed to be encrypted?

**Answer:** No. Logical exports over the API can contain plaintext; encrypt the destination or archive separately.

### Exercise 10 — KMS Network Outage

KMS becomes unreachable briefly.

**Question:** Will a running Atlas cluster definitely halt immediately?

**Answer:** Never claim that outright. Atlas distinguishes temporary connectivity issues from invalid credentials/keys; restarts and validations may be affected. Maintain runbooks and HA KMS.

### Exercise 11 — Primary and Secondaries

An Enterprise replica set enables ESE only on the primary.

**Question:** Is the deployment fully protected?

**Answer:** No. Secondaries also hold data files; all members need consistent encryption policies and migration.

### Exercise 12 — KMIP Certificate

A MongoDB Enterprise node connects to a KMIP server whose certificate mismatches its hostname.

**Question:** What can happen?

**Answer:** `mongod` may fail to start due to TLS hostname verification. Fix DNS/certificates rather than disabling verification.

### Exercise 13 — CBC vs. GCM

An ESE deployment on Linux uses AES256-GCM and restores from a cold filesystem snapshot.

**Question:** What must you watch out for?

**Answer:** MongoDB warns about IV reuse risk; follow the runbook using `--eseDatabaseKeyRollover` where applicable.

### Exercise 14 — Key Scopes

Multiple production clusters depend on a single CMK.

**Question:** What is the risk?

**Answer:** Huge blast radius if the key is disabled or deleted. Consider key separation by environment and data classification.

### Exercise 15 — Field-Level

An organization wants database admins unable to read personal ID numbers while MongoDB still stores the records.

**Question:** Is enabling ESE alone enough?

**Answer:** No. Evaluate CSFLE/Queryable Encryption and client-side key vault controls.

### Exercise 16 — Search Indexes

A team toggles CMK on Atlas Core and notices Search indexes rebuilding.

**Question:** Is this a random bug?

**Answer:** Not necessarily. Atlas docs note re-encryption/initial sync can rebuild Search/Vector Search indexes; plan maintenance and capacity accordingly.

### Exercise 17 — Rotation vs. Deletion

A security officer proposes immediately deleting all old KMS key versions after rotation.

**Question:** Is that safe?

**Answer:** Not if any data or snapshots remain encrypted under those versions. Map dependencies before destroying keys.

### Exercise 18 — Encryption Compliance

A team reports “AES-256 is on, so we automatically pass PCI-DSS/HIPAA.”

**Question:** Is that conclusion valid?

**Answer:** No. Encryption is one security control; compliance also requires IAM, auditing, governance, incident response, retention, and other controls in scope.

### Exercise 19 — Preventive Measures

A CMK depends on a service principal whose credential is nearing expiration.

**Question:** What should you do?

**Answer:** Alert and rotate the credential ahead of expiry, verify Atlas/KMS validation, and prepare break-glass access—do not wait for a cluster outage.

### Exercise 20 — Encryption Keyfile Confusion

An admin uses the same file for `security.keyFile` and `security.encryptionKeyFile`.

**Question:** Why is that wrong?

**Answer:** They serve two distinct purposes—internal authentication and ESE master-key storage—requiring separate policies, contents, permissions, and rotation.

---

## 43. Official MongoDB Documentation

- [MongoDB — Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/): Encrypted Storage Engine, cipher modes, key hierarchy, and KMIP/keyfiles.
- [MongoDB — Configure Encryption](https://www.mongodb.com/docs/manual/tutorial/configure-encryption/): Enterprise ESE, KMIP, local keyfile, and encrypting existing data via rolling initial sync.
- [MongoDB — Rotate Encryption Keys](https://www.mongodb.com/docs/manual/tutorial/rotate-encryption-key/): rolling rotation, KMIP master-key rotation, and local key management limits.
- [MongoDB — Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/): `security.enableEncryption`, `security.encryptionCipherMode`, and KMIP options.
- [MongoDB — Atlas Encryption at Rest Overview](https://www.mongodb.com/docs/atlas/security-encryption-at-rest-overview/): Atlas Core/Infinite, AES-256, CMK hierarchy, backups, and rotation.
- [MongoDB — Encryption at Rest using Customer Key Management](https://www.mongodb.com/docs/atlas/security-kms-encryption/): KMS providers, permission requirements, setup, and key validation.
- [MongoDB — Manage Customer Keys with AWS KMS](https://www.mongodb.com/docs/atlas/security-aws-kms/): AWS IAM/key policies and key lifecycles.
- [MongoDB — Manage Customer Keys with Azure Key Vault](https://www.mongodb.com/docs/atlas/security-azure-kms/): Azure Key Vault and access policies.
- [MongoDB — Manage Customer Keys with Google Cloud KMS](https://www.mongodb.com/docs/atlas/security-gcp-kms/): GCP key hierarchy and service accounts.
- [MongoDB — Storage Engine and Cloud Backup Encryption](https://www.mongodb.com/docs/atlas/backup/cloud-backup/cloud-backup-encryption/): snapshot security and key dependencies.
- [MongoDB — Access an Encrypted Snapshot](https://www.mongodb.com/docs/atlas/tutorial/access-encrypted-snapshot/): restoring snapshots with customer keys.
- [MongoDB — In-Use Encryption](https://www.mongodb.com/docs/manual/core/security-in-use-encryption/): CSFLE and Queryable Encryption.
- [MongoDB — Choosing In-Use Encryption](https://www.mongodb.com/docs/manual/core/queryable-encryption/about-qe-csfle/): differences between the two client-side approaches.
- [MongoDB — TLS/SSL](https://www.mongodb.com/docs/manual/core/security-transport-encryption/): transport encryption.
- [MongoDB — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/): defense layers beyond encryption.
- [MongoDB — Backups](https://www.mongodb.com/docs/manual/core/backups/): backup and recovery.

**Version note:** Capabilities for Atlas Core/Infinite, tier availability, key providers, self-managed ESE ciphers, CSFLE/QE, and backup/restore vary by MongoDB Server/FCV/driver/edition. Consult documentation for your exact deployment and test in staging before changing any key policy.

## 44. Summary

**Data-at-rest encryption** in MongoDB is not a single identical setting across all environments:

- **Atlas:** data is encrypted by default; Atlas Core can add database-level encryption using **CMK/BYOK** on supported deployments. Atlas Infinite has its own storage architecture and phased CMK support.
- **Self-managed Enterprise:** uses **WiredTiger Encrypted Storage Engine**, preferring **KMIP** when key separation, rotation, and auditing are required; local keyfiles carry governance and rotation limits.
- **Self-managed Community:** encrypts at the **OS/block storage/cloud volume** layer instead of Enterprise ESE.
- **Client-side encryption:** when sensitive fields must stay protected even from the database server, add CSFLE/Queryable Encryption with a separate key vault.

The **CMK → master key → database keys** hierarchy enables envelope encryption, but operating it safely requires governing **key lifecycles, IAM, certificates, rotation, backups, key versions, and KMS availability**. Losing a key can be as catastrophic as losing data; a snapshot without its decryption key is an unusable backup.

Finally, encryption at rest is only **one layer in defense-in-depth**. TLS, RBAC, auditing, log/export protection, host hardening, and disaster recovery drills remain mandatory under your threat model.

**Encryption protects bytes on disk; proper key management protects control and recoverability across the entire system.**
