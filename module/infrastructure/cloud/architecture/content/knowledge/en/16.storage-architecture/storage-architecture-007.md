# Storage Encryption and Data Access Control

## 1. Data Protection Must Be Designed Alongside Storage

A cloud application may store data in many places: relational databases, object storage, block volumes, file shares, caches, snapshots, backups, queues, logs, and analytics copies. Enabling a single "encryption at rest" toggle on a database is not enough to prove all data is protected. You must know **what data is stored where, who can read or modify it, how encryption keys are managed, how long copies persist, and how to recover during an incident**.

In the **CLOUD_ARCHITECTURE** module, storage design must start from business requirements and be evaluated alongside reliability, security, scalability, cost, and operations using a Well-Architected mindset. Encryption reduces the risk of unauthorized access when stored data or network traffic is exposed; access control limits which identities and workloads can use data; key management and auditing preserve protection throughout the entire lifecycle.

After this lesson, you can:

- Classify data and map where data is stored, copied, and transmitted.
- Distinguish encryption at rest, encryption in transit, and application/field-level encryption.
- Explain symmetric encryption, envelope encryption, KMS, HSM, and key hierarchies.
- Design IAM/RBAC/ABAC, resource policies, network policies, and workload access under least privilege.
- Separate key administration permissions from permissions to read decrypted data.
- Protect backups, snapshots, replicas, logs, and data exported out of primary storage.
- Plan rotation, revocation, recovery, and auditing.
- Evaluate trade-offs across security, reliability, performance, and cost.

## 2. Start from Data and the Threat Model

The running example is **BookingCloud**, a time-slot equipment rental application. The system stores customer profiles, bookings, equipment schedules, product photos, payment records, operational logs, and reports.

### 2.1. Classify Data Before Choosing Services

| Data group | Examples | Illustrative classification | Protection requirements |
|---|---|---|---|
| Public data | Approved equipment photos, public catalog | Public | Protect integrity, content origin, and write permissions |
| Business data | Booking ID, slot, order status | Internal | Authentication, authorization, encryption, change auditing |
| Personal data | Email, phone number, delivery address | Confidential/personal | Restricted access, encryption, purpose/retention limits, log redaction |
| Financial data | Payment references, invoices, reconciliations | Restricted per policy | Very narrow permissions, full auditing, retention, and integrity |
| Credentials/secrets | DB passwords, API keys, private keys | Secret | Secret manager/HSM, rotation, never logged or baked into images |
| Telemetry | Traces, errors, access logs | Operational, may contain PII | Minimize/redact, RBAC, retention, and auditing |
| Backups/snapshots | Database and volume copies | Equal to or higher than source data | Encryption, separate permissions, retention, restore tests, and delete controls |

Exact classification levels must follow enterprise policy and applicable regulations; no universal label automatically dictates all legal duties. A backup of personal data is still personal data; moving data to another bucket does not reduce its sensitivity.

### 2.2. Map the Data Lifecycle

Trace every data category from collection to deletion:

1. **Create/collect:** data originating from clients, partners, imports, or internal systems.
2. **Ingest:** over TLS, API gateways, identity/authentication, and validation.
3. **Process:** passing through compute, queues, caches, or workflows.
4. **Store:** databases, objects, block/file storage, and indexes.
5. **Share/use:** read by other services, analysts, partners, or ops tools.
6. **Copy/backup:** replicas, snapshots, exports, archives, logs, and disaster recovery regions.
7. **Retain/delete:** end of purpose, retention expiry, or deletion request; must account for copies and legal holds.

~~~mermaid
flowchart LR
    C["Collect / API"] --> P["Process / compute"]
    P --> D[("Primary database")]
    P --> O[("Object storage")]
    D --> R["Read replica / cache"]
    D --> B["Backup / snapshot"]
    O --> A["Archive / replication"]
    P --> L["Logs / traces"]
    R --> U["Authorized users / services"]
    B --> DR["Recovery environment"]
    A --> DR
    L --> OBS["Operations / security teams"]
    D --> X["Retention / deletion"]
    O --> X
    B --> X
    L --> X
~~~

This diagram shows the data lifecycle view. Every arrow should carry an owner, identity, purpose, transport security, retention, and permissions. Replicas, caches, backups, and telemetry are frequently overlooked when teams review only the primary database.

### 2.3. Define the Threat Model

Ask who can access what, from where, with which permissions, and what the impact would be:

- An attacker obtains a disk, snapshot, backup, or object export.
- An IAM role or service account is leaked or hijacked.
- A broadly privileged employee downloads customer data improperly.
- A compromised application abuses its service database credentials to read other tenants.
- Secrets or encryption keys leak into source code, images, logs, or CI artifacts.
- Someone with data-delete rights deletes backups or keys needed for recovery.
- A workflow sends data to an unintended endpoint or unexpected third-party provider.
- Logs/traces/DLQs capture tokens, emails, addresses, or sensitive payloads.

Encryption at rest protects scenarios such as media leaving the runtime environment; it does not stop a valid application role from reading and exfiltrating data. Therefore, combine encryption, authorization, network controls, monitoring, and data minimization.

## 3. Three Protection Layers: At Rest, In Transit, and In Use

### 3.1. Encryption at Rest

Encryption at rest protects data stored on media or inside storage services. With cloud-managed storage, providers typically offer server-side encryption; depending on the service, it may be enabled by default or require configuration.

Targets to check:

- Database files, tablespaces, transaction logs, temp files, and automated backups.
- Objects and object versions, incomplete multipart uploads, replication destinations.
- Block volumes, file shares, and local/ephemeral disks if holding sensitive data.
- Snapshots, images, backup copies, and archives.
- Search indexes, cache persistence, queue storage, and data warehouses.

Do not assume every auxiliary component is encrypted just because the database has encryption at rest. Check service documentation for encryption scope, key ownership, defaults, copy handling, and limitations.

### 3.2. Encryption in Transit

Encryption in transit protects data moving between clients, services, databases, queues, storage endpoints, regions, and third parties. TLS/HTTPS is standard for IP connections; certain internal links or custom protocols have corresponding protections.

| Link | Control questions |
|---|---|
| Browser/mobile → API | TLS, hostname/certificate validation, token and session security |
| API → database | TLS connection, server certificate verification, DB identity/role |
| API → object storage | HTTPS, workload identity, bucket/object policies |
| Service → queue | TLS, publisher/consumer identities, and topic/queue permissions |
| Worker → payment/email provider | TLS, endpoint allowlists, secret/token scopes |
| Primary → replica/backup region | Encryption, peer identity, network routes, and key availability |
| App → log/trace backend | TLS, payload minimization, and read/write permissions |

TLS protects data only across that hop. If TLS terminates at a proxy or gateway, data is decrypted there and the next hop must be evaluated separately. Encryption in transit also fails to verify the target service if clients skip certificate/hostname checks.

### 3.3. Encryption in Use and Application-Level Encryption

While an application processes data, plaintext may appear in memory, processes, runtimes, or decrypting services. Sensitive workloads may consider confidential computing / Trusted Execution Environments (TEEs) to reduce host/hypervisor memory inspection in supported models. However, TEEs have constraints around workloads, threat models, attestation, and operations; they do not replace authorization or input validation.

**Field-level/application-level encryption** encrypts specific sensitive fields before writing to a database. This limits database operators or certain queries from reading plaintext, yet complicates search, indexing, sorting, key rotation, and application code. Not every field needs separate encryption; define who may decrypt and which features require plaintext.

| Approach | Strong protection against | Limitations |
|---|---|---|
| Storage encryption at rest | Media/snapshots accessed outside the service or without key decrypt rights | Authorized applications/services still read plaintext |
| TLS in transit | Network eavesdropping/tampering | Does not protect a compromised endpoint |
| Field-level encryption | Restricts plaintext to specific services/key holders | Complicates querying, searching, and key operations |
| Confidential computing | Certain host/platform memory inspection risks | Depends on TEEs, attestation, and workload support |

## 4. Core Algorithms and Encryption Models

### 4.1. Symmetric Encryption

Symmetric encryption uses the same secret key for encryption and decryption. Algorithms such as AES-GCM provide both confidentiality and integrity/authentication when nonces and keys are used properly.

Practical rules:

- Choose standardized algorithms and modes supported by vetted libraries/providers.
- Never invent custom cryptographic algorithms or protocols.
- Follow mode rules for nonces/IVs; in particular, never reuse nonces unsafely under the same key.
- Verify authentication tags on decryption; reject tampered data.
- Store keys separately from ciphertext and protect key backups too.
- Record metadata such as key ID, algorithm/version, and required context for recovery/rotation.

### 4.2. Asymmetric Cryptography

Asymmetric cryptography uses a public/private key pair. The public key can be shared; the private key must be protected. This model is commonly used for key exchange, digital signatures, identity, and trust bootstrapping.

Do not encrypt large files directly with RSA by default. In practice, systems use hybrid/envelope encryption: a public key or KMS protects a symmetric data key, and the data key encrypts the payload with an efficient symmetric algorithm.

### 4.3. Hashing and Encryption Are Different Things

- **Encryption** is reversible back to plaintext with the right key.
- **Cryptographic hashing** produces a one-way digest used for integrity checks or verifiers in certain cases, never to recover plaintext.
- **Password hashing** requires purpose-built algorithms with salts and appropriate cost factors; never store passwords with reversible encryption or fast general-purpose hashes.
- **Digital signatures** verify origin/integrity via public-key verification; they do not encrypt content on their own.

## 5. Envelope Encryption and KMS

For large datasets, applications/storage services usually encrypt data with a **Data Encryption Key (DEK)**. A **Key Encryption Key (KEK)** or KMS key protects the DEK. Ciphertext and the encrypted DEK are stored together with required metadata.

### 5.1. Envelope Encryption Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant KMS as Key Management Service
    participant Store as Encrypted storage

    App->>KMS: Generate data key under KEK
    KMS-->>App: Plaintext DEK + encrypted DEK
    App->>App: Encrypt payload with plaintext DEK
    App->>App: Remove plaintext DEK from use
    App->>Store: Store ciphertext + encrypted DEK + metadata
    Store-->>App: Write confirmed
    App->>Store: Read ciphertext + encrypted DEK
    Store-->>App: Encrypted object and key metadata
    App->>KMS: Decrypt encrypted DEK (authorized identity)
    KMS-->>App: Plaintext DEK
    App->>App: Verify tag and decrypt payload
~~~

This diagram shows the general pattern. With managed databases or object storage, the storage service itself may perform server-side encryption and call KMS instead of the application handling plaintext DEKs. Understand who calls KMS, which key grants/policies apply, and where decrypted data exists.

### 5.2. Role of KMS

A Key Management Service typically supports creating/importing keys by service type; managing key policies, IAM grants, and usage rights; encrypting/decrypting or generating data keys; policy-based rotation; disabling, scheduling deletion, or revoking grants; and integrating with databases, object storage, volumes, backups, and other services.

**KMS does not automatically handle all data permissions.** A role allowed to read an object still needs decrypt rights when the object uses a customer-managed key; conversely, permission to call KMS decrypt does not grant object read access. Effective access is usually the intersection of multiple policies: identity policy, resource policy, key policy/grants, network controls, and service-specific controls.

### 5.3. Provider-Managed Keys, Cloud-Managed Keys, and Customer-Managed Keys

| Key management model | Primary responsibility | Advantages | Trade-offs |
|---|---|---|---|
| Provider-managed / default keys | Provider manages lifecycle; minimal customer configuration | Easy to use, low ops | Less policy control; auditing/rotation varies by service |
| Customer-managed keys in KMS | Customer controls policies, grants, lifecycle; provider operates KMS infra | Stronger access control, disable/revoke, auditing, and separation of duties | Requires owners, rotation, quotas/costs, recovery, and governance |
| External / HSM-backed keys | Organization or external HSM service holds part of key custody | Stricter custody/control requirements | Higher complexity, latency, availability risk, and ops burden |

Naming differs across cloud providers. Read product documentation carefully: "customer-managed" does not necessarily mean key material never resides in provider infrastructure; HSM levels, exportability, regional scope, and recovery differ.

## 6. Key Lifecycle: Creation, Usage, Rotation, and Revocation

An encryption key is an asset that must be managed like a critical service:

1. **Create/provision:** create the key in KMS/HSM or import it via controlled procedures.
2. **Classify/assign owner:** document purpose, data classification, environment, owner, region, and dependent resources.
3. **Authorize:** separate policies for administrators, key users, auditors, and recovery roles.
4. **Use:** workloads call encrypt/decrypt/generate-data-key via short-lived identities; avoid exporting plaintext keys needlessly.
5. **Rotate:** switch key versions per policy/trigger; test reading older data.
6. **Monitor:** alert on unusual calls, grant/policy edits, decrypt spikes, and key expirations if keys expire.
7. **Disable/revoke:** respond to suspected compromise while immediately assessing impact on running workloads.
8. **Retire/delete:** delete only after all dependent data is migrated/retention completes and approval is granted.

### 6.1. Rotation Does Not Always Mean Immediately Re-Encrypting All Data

Some KMS services support automatic key rotation by retaining prior key material/versions to continue decrypting older ciphertext; exact behavior depends on key type and provider. With envelope encryption, you can rewrap encrypted DEKs under a new KEK version without reading and re-encrypting entire payloads, if the design and service support it.

Distinguish clearly:

- **Rotate KEK/KMS key:** change the key version protecting data keys.
- **Rotate DEK:** generate new data keys for new data or objects.
- **Re-encrypt data:** decrypt data and encrypt again with a new key/algorithm.
- **Rewrap DEK:** decrypt the DEK under the old KEK and encrypt it under the new KEK without touching payload ciphertext.

Never claim "enabling automatic rotation re-encrypted all historical data." Verify service semantics and maintain plans for existing data, backups, and key versions.

### 6.2. Risks of Disabling or Deleting Keys

If a key needed to decrypt backups is disabled, deleted, or loses access grants, data may remain stored yet inaccessible. Key deletion can cause unrecoverable data loss.

Before disabling or deleting:

- Inventory dependent resources, snapshots, backups, object versions, and regions.
- Check whether any ciphertext must remain readable under retention/legal holds.
- Test reading data with the new key version or recovery key.
- Require two-person approval / separation of duties for destructive actions.
- Use deletion waiting periods / pending deletion where supported; cancel deletion if dependencies emerge.
- Audit and verify after execution.

An unowned or uninventoried key is a severe availability risk, not merely a security issue.

## 7. Access Control: Who Can Do What with Data?

Encryption and authorization answer two different questions:

- Encryption: can someone without decrypt capability read meaningful content?
- Authorization: which identity may perform which action on which resource, under what conditions?

Even with strong ciphertext protection, an over-privileged service role holding broad read/decrypt rights can still exfiltrate plaintext.

### 7.1. Policy Layers

| Layer | Question | Example |
|---|---|---|
| Identity/IAM policy | Which role/user can invoke an action? | Booking API role may read specific object prefixes |
| Resource policy | Which principals does the resource accept? | Bucket policy allows only approved accounts/roles |
| Key policy/grant | Which identities may use the key and for which actions? | Worker holds decrypt permission for thumbnailing |
| Network control | Where can traffic reach the resource from? | Private endpoints, security groups, firewalls, egress rules |
| Application authorization | Which records may this user read? | Booking owner or authorized staff can view the order |
| Data/tenant policy | Which tenant, row, or object scope applies? | Tenant A cannot read Tenant B's objects |

These layers reinforce one another; one permissive layer should not accidentally expose the system if another layer has gaps.

### 7.2. RBAC and ABAC

**Role-Based Access Control (RBAC)** grants permissions by role:

| Role | Example permissions |
|---|---|
| `booking-api` | Read/write bookings via API or a scoped DB role |
| `thumbnail-worker` | Read source objects, write thumbnail outputs |
| `backup-service` | Create backups within approved scopes |
| `data-analyst` | Read masked/aggregated views, never credentials |
| `security-auditor` | Read audit logs, never alter business data |
| `key-admin` | Manage key policies/lifecycles without default access to plaintext business data |

**Attribute-Based Access Control (ABAC)** evaluates attributes such as environment, data classification, tenant, resource tags, purpose, network identity, or time. For example, a role may read objects only when `environment=production`, `data-domain=booking`, and tenant scope matches.

RBAC is easier to manage when roles are few and duties stable. ABAC scales more flexibly across multi-tenant/multi-resource environments, though policies can be harder to debug. Practical designs often combine RBAC for job functions with ABAC for resource scoping.

### 7.3. Least Privilege and Separation of Duties

- Grant the minimum permissions needed for only as long as needed.
- Prefer short-lived roles/workload identities over static access keys.
- Separate permissions to create keys, use keys, edit policies, read backups, and delete keys.
- Keep production roles separate from dev/test whenever feasible.
- Restrict wildcards on resources/actions; use explicit resource ARNs/prefixes/conditions.
- Periodically review unused permissions, inherited roles, and policy drift.
- Require approvals, MFA, time bounds, audits, and post-incident review for break-glass access.

## 8. Example Policies for BookingCloud

### 8.1. Identity and Data Access Map

~~~mermaid
flowchart TB
    subgraph APP["Application identities"]
      API["booking-api role"]
      TH["thumbnail-worker role"]
      AN["analyst role"]
      BK["backup role"]
    end
    subgraph DATA["Data resources"]
      DB[("Booking DB")]
      BUCKET[("Object bucket")]
      SNAP[("Backup / snapshots")]
    end
    subgraph KEYS["Key management"]
      KDB["Database KMS key"]
      KOBJ["Object KMS key"]
      KBACK["Backup KMS key"]
    end
    API -->|"Read/write scoped rows"| DB
    API -->|"Put approved object"| BUCKET
    TH -->|"Read source prefix"| BUCKET
    TH -->|"Write thumbnail prefix"| BUCKET
    AN -->|"Read masked view"| DB
    BK -->|"Create/copy backup"| SNAP
    DB --> KDB
    BUCKET --> KOBJ
    SNAP --> KBACK
~~~

This diagram illustrates logical permissions. In a real cloud, the DB/object service calls KMS on behalf of workloads or applications call KMS directly; service-linked roles and grants differ. Verify the actual principals appearing in audit logs.

### 8.2. Policy-by-Principle Example

Example logical policy YAML for a worker:

~~~yaml
identity: thumbnail-worker
environment: production
permissions:
  - action: object.read
    resource: bucket://booking-uploads/source/*
  - action: object.write
    resource: bucket://booking-assets/thumbnails/*
  - action: key.decrypt
    resource: key://booking-uploads-key
conditions:
  requireTls: true
  allowedWorkloadIdentity: booking-thumbnail-service
  denyPublicAccess: true
  denyOtherTenants: true
explicitlyDenied:
  - object.delete
  - database.admin
  - key.scheduleDeletion
~~~

This is pseudoconfiguration, not directly executable AWS/Azure/GCP policy syntax. During implementation, map it to provider-specific IAM/resource policies/KMS grants and inspect indirect paths such as role assumption, wildcards, permission boundaries, and inherited groups.

### 8.3. Database Permissions Do Not Replace Business Authorization

The Booking API's database role may have `SELECT`/`INSERT`/`UPDATE` on certain tables. Yet the API must still verify whether the current user is authorized to read a specific booking.

~~~sql
SELECT booking_id, status, created_at
FROM bookings
WHERE booking_id = :booking_id
  AND tenant_id = :tenant_id;
~~~

Tenant/user scope predicates must come from verified identity claims, never trusting an arbitrary client-supplied `tenant_id`. Row-level security can be added if supported and configured properly; however, verify connection pooling and session context handling so permissions never leak across requests.

## 9. Protecting Each Storage Type

### 9.1. Relational Databases

Verify:

- Encryption at rest for storage, transaction logs, automated backups, and snapshots.
- TLS for connections; verify server identity/certificates.
- Database authentication via IAM/managed identity or credentials managed in a secret manager.
- Least-privilege DB roles; separate schemas/tables/operations by service.
- Row-level access or application authorization for tenants/objects.
- Auditing of connections, role grants, privilege changes, and sensitive reads.
- Backups/PITR, retention, deletion, encryption key dependencies, and restore tests.

Encryption at rest does not replace parameterized queries, SQL injection defense, masking, or table-level read restrictions.

### 9.2. Object Storage

Object storage typically supports bucket/container policies alongside object metadata/versions. Check public access blocks / default-private policies, access points, and cross-account access; default encryption and customer-managed keys where required; TLS-only policies, signed URL expiries, and method/scope restrictions; versioning, object locks/retention, and lifecycle transitions; replication destinations, inventory reports, multipart uploads, and delete markers; access logs/data events and version delete permissions.

A signed URL is a bearer capability: anyone holding it while valid can perform the signed action. Never log full URLs, avoid overly long expiries, and scope strictly to the required method and object.

### 9.3. Block and File Storage

For block volumes and file shares:

- Enable encryption on new volumes and verify snapshots/clones are encrypted as required.
- Control attach/mount via identities, security groups/networks, and storage export policies.
- Isolate volumes by workload/tenant when blast radius or permissions demand it.
- Protect filesystem permissions, ownership, mount options, and node-level secrets.
- Verify data residency, replicas, snapshots, keys, and attach behavior during failover.

Volume encryption does not protect against processes authorized to mount the volume and read files. OS/filesystem and application permissions must still be restricted.

### 9.4. Caches, Queues, Search, and Analytics

Even "temporary" services can hold sensitive data:

- Caches may store tokens, profiles, or sessions; enforce TTLs, TLS, authentication, and private networking.
- Queues may hold payloads across retention, replays, or DLQs; minimize payloads, encrypt, and restrict read access.
- Search indexes may mirror PII fields; apply index mappings, field-level controls, or masking.
- Data lakes/warehouses may separate raw and curated zones; enforce catalogs/classification, column/row policies, lineage, and retention.
- Logs/traces may capture request bodies/headers; redact at the source and restrict access.

## 10. Backups, Snapshots, Replicas, and Disaster Recovery

A backup is not just another copy. It often holds as much or more data than the live store and is a prime target for attackers seeking to disable recovery.

### 10.1. Requirements to Verify

| Area | Question |
|---|---|
| Encryption | Are backups/snapshots encrypted and with which key? |
| Access | Who can create, read, copy, restore, and delete? |
| Isolation | Are backups in a separate account/project/vault? |
| Immutability | Is appropriate retention lock/WORM/object lock enabled? |
| Cross-region | Does the key exist and have usage rights in the target region? |
| Retention | Do retention and deletion schedules match policies/legal holds? |
| Integrity | Are checksums, catalogs, and backup completion verified? |
| Recovery | Are restores tested against RTO/RPO and runbooks? |

~~~mermaid
flowchart LR
    DB[("Primary DB")] --> BK["Backup service"]
    BK --> ENC["Encrypt with backup key"]
    ENC --> VAULT["Isolated backup vault"]
    VAULT --> COPY["Cross-region/account copy"]
    COPY --> REC["Restore in recovery environment"]
    REC --> VERIFY["Verify data + application"]
    VERIFY --> READY["Recovery ready"]
~~~

A successful snapshot does not prove the application can recover. Test restoring the database, key permissions, networking, secrets, schema, application, and business transactions. If the key exists only in the source region or the recovery role lacks key usage rights, the backup copy can be useless.

### 10.2. Immutable Backups and Separation of Duties

Ransomware or a compromised account may attempt to delete backups alongside primary data. Reduce risk via dedicated backup accounts/vaults and restricted cross-account access; policy-based immutable retention/object locks; backup-writer roles lacking delete permissions; separate approval for delete roles; MFA/approval on destructive actions; alerts when retention locks or backup policies change; independently managed keys and tested recovery workflows.

Immutable does not mean kept forever. Balance retention, legal holds, privacy deletion duties, costs, and applicable regulations.

## 11. Key Rotation, Migration, and Re-Encryption

Key changes may be routine operations or responses to key compromise. Both cases demand different urgency levels and plans.

### 11.1. Routine Rotation

1. Check the key type and automatic rotation support.
2. Identify which ciphertext depends on the key/version.
3. Enable or create the new key version per procedure.
4. Verify services can still read older data.
5. If needed, batch-rewrap DEKs or re-encrypt payloads.
6. Monitor decrypt errors, latency, and continued usage of the old key version.
7. Retire the old key only after dependencies, retention, and restore paths end.

### 11.2. Suspected Key Compromise

- Scope the incident: affected keys, principals, workloads, ciphertexts, timestamps, and whether attackers hold ciphertext.
- Disable/restrict keys or revoke grants per incident playbook; weigh availability impact before broad actions.
- Rotate related credentials and workload identities.
- Create new keys and re-encrypt/rewrap affected data.
- Inspect backups, replicas, exports, logs, and out-of-region copies.
- Search audits for abnormal decrypts, policy edits, and data exfiltration.
- Assess notification duties and preserve forensic evidence per incident response processes.

Never delete a key immediately upon suspected compromise if doing so destroys investigation or recovery capability. Isolate and restrict permissions per playbook, then decide key lifecycle based on actual scope.

## 12. Auditing and Detecting Abnormal Access

Encryption and permissions are preventive controls; auditing and detection surface abuse or misconfiguration.

Record principals/roles/service identities accessing resources; actions such as read/write/delete/decrypt/grant/rotate/disable/schedule deletion; resource/key IDs, environment/region, and policy context; timestamps, source networks, request/correlation IDs, and outcomes; IAM/resource/key policy changes and approvers; and access to backup vaults, snapshots, DLQs, and exports.

Never log plaintext sensitive data, tokens, or private keys in audit logs. Protect audit logs from modification/deletion by the audited workloads themselves; use an account/project or sink with separate permissions, retention, and integrity controls.

### 12.1. Alert Signals

- A role suddenly decrypts far more objects or customers/tenants than usual.
- Access from an unseen region, network, or source identity.
- Bursts of `AccessDenied` errors after a policy change.
- Key disables, new grants, policy wildcards, or scheduled deletions outside change windows.
- Backup vault deletions or retention lock changes.
- Public access/bucket policy or database network exposure changes.
- Unusual spikes in DLQ/export/log access.

A single alert does not confirm an attack on its own. Enrich alerts with deployment changes, owners, workload baselines, and incident response context.

## 13. Reference Design for BookingCloud

| Component | Data | Encryption | Identity/access | Audit/recovery |
|---|---|---|---|---|
| Booking DB | Bookings, customer references | At rest + TLS | API DB role; app-level tenant checks | DB audits, backups/PITR, restore tests |
| Customer contact table/fields | Emails, phone numbers | At rest; field-level if threat model requires | Only services needing contact info; masked for analysts | Access logs, retention/deletion workflows |
| Object bucket | Original photos, thumbnails | At rest with proper key + HTTPS | Prefix-scoped upload/read roles; public only for approved assets | Versioning, lifecycles, access events, backups |
| Queue/events | Booking events, processing tasks | At rest/in transit per service | Separate producer/consumer permissions | Retention, DLQ, replay audits |
| Backup vault | DB/volume/object copies | Dedicated key or approved policy | Backup role writes; recovery role restores; delete separated | Immutable retention, cross-region restore tests |
| Logs/traces | Request metadata, errors | At rest + TLS ingest | Apps write; ops/security read by duty | Redaction, retention, tamper protection |
| KMS | KEK/DEK protection | HSM/KMS per service | Key admin and key user separated | Key policy audits, rotation, recovery |

You do not need one single key for every resource. Separate keys by data domain, environment, region, or blast radius when it clarifies permissions and incident containment; avoid proliferating so many keys that owners and rotation become unmanageable.

## 14. Well-Architected Evaluation

| Perspective | Review questions | Required evidence |
|---|---|---|
| **Operational Excellence** | Who owns keys, policies, backups, and rotation? Who responds to decrypt errors? | Key inventories, IaC, runbooks, alerts, audits, and restore drills |
| **Security** | Is data encrypted at every required hop? Are read/decrypt rights minimal? | Threat models, IAM/resource/key policies, TLS checks, access reviews |
| **Reliability** | Could key disablement/rotation or region loss make data unreadable? | Key recovery, cross-region key design, backup/restore tests, RTO/RPO |
| **Performance Efficiency** | How do KMS calls, field-level encryption, and audits impact latency/throughput? | p95/p99 latency, controlled key caching/reuse, load tests, quotas |
| **Cost Optimization** | What do KMS calls, HSMs, log retention, backups, and re-encryption cost? | Cost breakdown by key/requests/data volume and retention |
| **Sustainability** | Are redundant copies kept or data retained beyond its purpose? | Retention, lifecycles, duplicate-copy inventories, deletion evidence |

Managed encryption lowers operational toil without removing responsibility for access control, key lifecycles, and restore verification. A security posture only matters when operated consistently through changes and incidents.

## 15. Practice Exercise: Reviewing Storage and Access Policies

A team proposes:

> "Use one bucket and one KMS key across all environments. All backends share one admin role to read objects. Backups live in the same account as primary data. Logs store full request bodies for easy debugging. The database already has encryption at rest enabled, so internal TLS is unnecessary."

Review the design:

**Task 1 — Data inventory:** list BookingCloud datasets, classifications, and locations across primary DB, objects, caches, queues, logs, snapshots, and backups.

**Task 2 — Encryption:** diagram traffic from clients to API, API to DB/object/queue, replicas, and backups. Identify hops needing TLS, datasets needing at-rest encryption, and cases warranting field-level encryption.

**Task 3 — Key management:** propose key separation by environment/data domain, key-admin/key-user roles, rotation, recovery, and key compromise procedures.

**Task 4 — Authorization:** design roles for the booking API, thumbnail worker, analysts, backups, and auditors. Draft bucket/resource/key policy principles; distinguish object read rights from KMS decrypt rights.

**Task 5 — Backups:** design an isolated vault, immutability/retention, cross-region copies, and restore tests. Explain why same-account backups have a large blast radius.

**Task 6 — Auditing:** select at least five events to alert on, such as decrypt spikes, key policy changes, public bucket access, backup deletion, and cross-tenant access.

**Task 7 — Trade-offs:** compare provider-managed keys, customer-managed KMS keys, and HSM-backed keys across control, availability, cost, latency, and responsibility.

### Self-Check Framework

| Initial proposal | Problem | Improvement direction |
|---|---|---|
| One shared admin role | Large blast radius, poor accountability | Workload-scoped roles, least privilege, short-lived identities |
| One key for all environments | Dev compromise impacts production; hard to separate policies | Separate keys/domains by environment and sensitivity |
| Same-account backups | Attackers delete both data and recovery copies | Dedicated backup vault/account, immutable retention |
| Logging full request bodies | Can expose tokens and PII | Source-level redaction, minimal log schemas |
| Database encryption at rest only | Leaves transit hops and other resources unprotected | TLS, bucket/queue/backup encryption, permission reviews |
| Assuming object read implies decrypt | Two separate policy layers | Check resource policies and key policies/grants independently |

This provides an analytical direction. Final configurations must match the actual cloud provider and enterprise data policies.

## 16. Pre-Production Storage Checklist

- [ ] Data inventory, classification, owner, purpose, and retention exist for every store/copy.
- [ ] Encryption at rest is enabled/verified for DBs, objects, volumes, snapshots, backups, and caches/queues holding sensitive data.
- [ ] TLS and hostname verification are enforced across required transit hops.
- [ ] Places where plaintext appears during processing are mapped, with field-level encryption or TEEs where the threat model requires them.
- [ ] Keys have owners, purposes, environments, policies, rotation, and recovery paths.
- [ ] Key admin, key user, backup, delete, and auditor roles are properly separated.
- [ ] IAM/resource/key/network/application policies follow least privilege and tenant scoping.
- [ ] No secrets appear in source code, images, logs, public IaC state, or examples.
- [ ] Backups/snapshots have encryption, isolation, immutability/retention, and cross-region recovery as needed.
- [ ] Restore tests prove data, keys, networking, identities, and the application all work end-to-end.
- [ ] Logs/audits enforce redaction, retention, restricted read access, and integrity protection.
- [ ] Alerts exist for abnormal decrypts, policy/key edits, public exposure, and backup deletion.
- [ ] Rotation/revocation/re-encryption procedures are tested with clear owners.
- [ ] Latency, quotas, KMS/storage/audit costs, and SLO impacts have been measured.

Storage encryption and data access control are complementary protection layers. Encryption reduces readability when storage media or transit paths are exposed; authorization restricts which identities can use data; key lifecycles, backups, and auditing sustain protection and recoverability over time. Sound designs trace the entire data lifecycle—from creation to the final copy—and verify controls with policies, logs, and restore tests.
