# Backing Up Data, Configuration, Keys, and Dependencies Needed for Recovery

A solid database backup alone is not necessarily enough to restore a cloud application. After a region outage, accidental resource deletion, or cloud account compromise, operations teams may still have a database snapshot yet lack deployment configuration, secrets, encryption keys, certificates, DNS records, container images, schema migrations, or access permissions to launch the system. Conversely, having full Terraform and application images while missing data, transaction logs, or decryption keys leaves the service unable to return to operation either.

Disaster recovery (DR) must therefore view the system as an interconnected set of dependencies. What needs protection is not just business data, but **the ability to recreate the environment and open, authenticate, decrypt, connect, route, and operate that data**. This lesson guides scoping backups, managing configuration and key material, protecting external dependencies, determining restore order, and validating outcomes.

This lesson belongs to the **Disaster Recovery** chapter of the **CLOUD_ARCHITECTURE** module. The focus is designing DR from business requirements down to infrastructure resources, data, and operations, balancing reliability, security, scalability, and cost with a Well-Architected mindset.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain why a standalone database backup is insufficient to restore a cloud service.
2. Build a backup inventory covering data, configuration, source code, artifacts, keys, and external dependencies.
3. Distinguish backups, snapshots, replication, archives, and infrastructure as code (IaC).
4. Select frequency, retention, consistency, and copy placement based on RPO/RTO.
5. Design protection for secrets, KMS keys, certificates, identities, and access permissions in DR.
6. Define the dependency graph and recovery sequence from control plane to data plane.
7. Control versioning, integrity, immutability, isolation, and recoverability when the primary account/region is lost.
8. Perform restore tests, data reconciliation, and actual recovery time measurements.

## 2. Service Recovery Requires More Than a Database

### 2.1. Viewing the System as a Set of Dependencies

A booking application may require the following components:

~~~mermaid
flowchart TD
    DNS[DNS and domain] --> EDGE[CDN / WAF / Load balancer]
    EDGE --> APP[Application runtime]
    APP --> ID[Identity and authorization]
    APP --> CFG[Configuration and feature flags]
    APP --> DB[(Database and transaction logs)]
    APP --> CACHE[(Cache)]
    APP --> BUS[Queue / event broker]
    APP --> OBJ[(Object storage)]
    APP --> EXT[Payment / email / third-party APIs]
    DB --> KEY[KMS / encryption keys]
    OBJ --> KEY
    APP --> CERT[Certificates and trust material]
    APP --> OBS[Logs / metrics / traces]
    IAC[Infrastructure definitions and artifacts] --> EDGE
    IAC --> APP
    IAC --> DB
~~~

These components may reside across multiple accounts, projects, subscriptions, or regions. Each has a different backup lifecycle, access control model, and restore procedure. Some data can be regenerated from other sources; other data cannot be recreated if keys or metadata are lost.

### 2.2. Recoverability Verification Questions

For each component, ask:

- If completely lost, from where can the service be recreated?
- Which data is the authoritative source, and which is a derived copy?
- Where are backups stored, and are they still accessible if the primary account/region fails?
- Who has permission to restore and who has permission to decrypt?
- Which versions of the schema, application, and configuration are compatible with this data copy?
- Which components must be ready first for other components to function?
- If an external provider or SaaS goes down, is there a fallback?
- Can the restored copy be verified without affecting production?

### 2.3. Recovery Set

A **recovery set** is the collection of artifacts and metadata needed to rebuild a business capability at a specific point in time. For example, a recovery set for the Booking API might include the database snapshot and logs up to the target timestamp, schema migrations, application image, deployment manifest, config version, secret/key references, DNS/certificates, identity policies, network rules, and external dependency list.

Not everything must be backed up at the same cadence. The goal is ensuring the right version of each component can be located and assembled into a compatible environment.

## 3. Classifying Objects to Back Up

### 3.1. Initial Inventory Matrix

| Group | Examples | Common Protection Methods | Recovery Question |
|---|---|---|---|
| Transactional data | Databases, transaction logs, ledgers | Snapshots, PITR, exports, replicas/backups | Can it be restored to the exact right point? |
| Files and objects | Uploads, invoices, attachments | Versioning, replication, immutable copies | Are metadata and objects at the same point? |
| Configuration | App config, routing, feature flags | Version control, encrypted exports, config history | Do we know the compatible version? |
| Infrastructure | Networking, IAM, database resources, clusters | IaC, provider backups/exports | Can it be rebuilt in a clean account/region? |
| Source code and artifacts | Source, binaries, images, packages | Git mirrors, artifact registry replication | Do artifacts have exact digests and dependencies? |
| Keys and certificates | KMS/HSM keys, signing keys, TLS certs | Key backup/export if supported, escrow, managed rotation records | Can old data still be decrypted and verified? |
| Identity | IdP config, federation, roles, break-glass identity | Config exports, recovery accounts, documented trust | Who can sign in to start the restore? |
| Messaging | Queue/topic config, DLQs, schema registry | Config exports, message archives if needed | Can messages be replayed without bad side effects? |
| DNS and network edge | Zone records, health checks, WAF, CDN | Zone exports, IaC, provider config backups | Can traffic be shifted safely? |
| Observability | Alerts, dashboards, log pipelines | Config as code, exports | Can post-recovery errors be observed? |
| External SaaS/dependencies | Payments, email, CRM, support | Config/contract/API inventory, authorized data exports | Are credentials, webhooks, and endpoints still usable? |
| Runbooks and docs | ADRs, recovery procedures, contact trees | Version control, offline copies | Can responders read them if primary systems are down? |

The inventory should record owner, criticality, source of truth, backup method, frequency, retention, encryption, destination, restore procedure, and last test date for each item.

### 3.2. Classification by Reproducibility

Resources can be grouped into three categories:

- **Irreplaceable if lost:** transactional data, customer files, certain private keys, or mandatory audit records.
- **Reproducible from controlled sources:** application images from artifact registries, networking and compute from IaC, schemas from migration repositories.
- **Reproducible or resynchronizable at a cost/time:** search indexes, caches, analytics projections, summary dashboards, or certain event streams.

The "reproducible" group still requires verifying whether the regeneration source is independent of the failure domain. Source code in Git on the same identity provider or artifacts stored only in the failed region may be unreachable when needed.

## 4. Database Data and Backup Consistency

### 4.1. Snapshots, Transaction Logs, and Point-in-Time Recovery

A **snapshot** captures data state at a point in time or per the service's snapshot mechanism. **Transaction log backups** record changes after a checkpoint, allowing recovery closer to the incident. **Point-in-time recovery (PITR)** combines a base backup and logs per database capabilities to restore to a supported timestamp within the retention window.

~~~text
T0        T1        T2        T3        T4
|---------|---------|---------|---------|
Snapshot  Log       Log       Failure   Restore target
          segment   segment   event     before bad write
~~~

PITR is valuable when accidental deletes, bad writes, or corruption are discovered later. However, the time window, restore granularity, log retention, and service limits depend on the database/provider. Verify actual settings and test empirically.

### 4.2. Crash-Consistent vs. Application-Consistent

Storage-level snapshots may guarantee only crash-consistent state: similar to a machine losing power, the system needs log recovery at startup. Application-consistent backups coordinate with the application/database to ensure data is in a cleaner valid state at capture time.

For databases with transaction logs and proper recovery mechanisms, a crash-consistent snapshot can still recover reliably per vendor documentation. For systems writing multiple interdependent files, you must pause/flush or use cross-volume consistent snapshots.

### 4.3. Are Multi-Source Backups Mutually Consistent?

Applications frequently store related data across a database and object storage. If the database snapshot occurs at T1 while object copying completes at T2, metadata may reference files that do not yet exist or newer files may become unreferenced.

Approaches:

- Use immutable version/object IDs and have metadata point to specific versions.
- Record a recovery manifest with snapshot ID, object versions, and timestamps/cursors.
- Pause or quiesce writes during the snapshot window when strict consistency is required.
- Use transactions/outboxes or workflows to track completed object uploads.
- Verify database-to-object references after restoration.

Never assume two independent cloud services take an atomic snapshot at the exact same instant.

### 4.4. Database Scope to Retain

- Primary data and transaction/WAL/binlog/PITR logs.
- Schemas, migration versions, extensions, and required collations.
- Stored procedures, triggers, constraints, views, and database roles where needed.
- Replication/partition configuration and related metadata.
- Encryption configuration, key IDs, and key version references.
- Database parameters/configuration and connection settings.
- Catalogs, metadata, or sequences required for the application to function.

Never store plaintext passwords in dumps. Credentials needed for recovery must reside in a secret manager or a separate recovery process.

## 5. Files, Object Storage, and Unstructured Data

Object storage often holds uploaded files, invoices, photos, exports, and business artifacts. Backups must clearly specify:

- Which buckets/containers and prefixes belong to which applications/tenants.
- Versioning, retention, lifecycle rules, and object locks.
- Cross-region replication and replication lag.
- Metadata, tags, ACLs/policies, and encryption context.
- Incomplete multipart uploads and unreferenced objects.
- How object versions are restored and metadata references repaired.

### 5.1. Versioning Does Not Equal Independent Backup

Versioning helps recover prior object versions after overwrites or deletes according to provider semantics. However, versions may still reside in the same account, under the same admin permissions, and in the same failure domain. If an attacker holds permission to delete both the bucket and its versions, versioning alone may not suffice.

Combine versioning with replication, object locks/retention, a separate backup account, or immutable archives as required. Test version deletion permissions and lifecycle policies empirically.

### 5.2. Object Locks and Immutable Copies

Immutable backups restrict modifying/deleting copies during the protected period. Verify the lock mode, retention period, legal holds, and platform override permissions. Immutable copies still require encryption, IAM controls, and a restore procedure; immutability alone does not guarantee backup contents are accurate or usable.

### 5.3. Manifests for File Data

A manifest can record object keys/versions, checksums, sizes, tenant scope, source snapshot, and timestamps. During restore, compare the manifest against object storage to detect missing objects, checksum mismatches, or cross-tenant discrepancies.

## 6. Application, Infrastructure, and Deployment Configuration

### 6.1. Runtime Configuration

Protect configurations that govern application behavior:

- Feature flags and entitlements.
- Tenant registries, routing maps, and shard placements.
- Database endpoints, connection pools, and timeouts.
- Queues/topics, consumer groups, and retry/DLQ policies.
- CORS, allowed origins, callback URLs, and webhook settings.
- Rate limits, quotas, autoscaling thresholds, and circuit breaker policies.
- Locales, timezones, templates, notifications, and integration mappings.

Config must be versioned, schema-validated, owned, and audited. Separate non-sensitive config from secrets. If the primary config service is unavailable, know whether the application can boot with cached config or requires restoring the control plane first.

### 6.2. Infrastructure as Code

IaC tools such as Terraform, CloudFormation, Bicep, or equivalents describe the resources to create. Protect:

- IaC source code and version-pinned modules.
- State files and backend configurations.
- Provider versions, lock files, and dependencies.
- Variable templates, policies, and subnet/CIDR plans.
- Import mappings and resource identifiers needing reference.
- Pipelines, runner identities, and approval rules.

State files can contain resource names, endpoints, and sometimes sensitive secrets depending on the provider/module. Encrypt, restrict access, version, and independently back up state files. Never commit plaintext secrets into repositories or artifacts simply to recreate infrastructure.

### 6.3. State and Drift

Backing up state does not mean real-world infrastructure still matches that state. Manual out-of-band changes (drift) may exist. Before DR execution, compare state, plans, and resource inventories; decide whether to import, recreate, or reconcile each resource.

Never run apply blindly on a new account/region using old state. You could accidentally modify or destroy resources outside the recovery target. Use separate workspaces/backends, review plans, and verify account/region targets before applying.

### 6.4. Source Code and Artifacts

Source repositories should have mirrors or copies in another failure domain. Production artifacts should be immutable by digest/version, scanned, and signed if policy requires. Recovering from verified artifacts avoids depending on build toolchains or package registries that may be broken during an incident.

Store:

- Container image digests and registry locations.
- Packages/binaries, SBOMs, and provenance if available.
- Runtime versions, base images, and migration scripts.
- Deployment manifests, Helm charts, or task definitions.
- Build pipeline definitions and dependency locks.

Do not rely solely on mutable tags like `latest`, as tags can later point to different contents.

## 7. Secrets, Encryption Keys, and Certificates

### 7.1. Why Keys Are a Critical Dependency

A database snapshot may hold ciphertext or data protected with envelope encryption. Losing the encryption key or key-encryption key can render backups undecryptable. Losing signing keys can prevent validating tokens or signatures. Losing TLS private keys/certificate material or trust config can prevent clients from establishing connections.

Therefore, build a key inventory and define recoverability per key type rather than merely writing "KMS is configured."

### 7.2. Classifying Key Material

| Type | Role | What to Store/Recover |
|---|---|---|
| Data encryption key (DEK) | Encrypts actual data | Ciphertext, wrapped DEK, and unwrapping mechanism |
| Key encryption key (KEK) / KMS key | Wraps or decrypts DEKs | Key resource, policies, region/account access, and key versions |
| Signing key | Signs tokens, artifacts, or events | Protected private key, public key history, and key IDs |
| TLS private key | Establishes TLS | Certificate/key lifecycle or re-issuance procedure |
| API credential | Connects to external dependencies | Secret references, rotation procedures, and provider permissions |
| Recovery/break-glass credential | Restores admin access | Offline/controlled vault storage, dual control, and auditing |

### 7.3. Managed KMS and Recovery Boundaries

With managed KMS/HSM services, private keys may be non-exportable by design. What must be protected is:

- The key resource still exists and is not disabled/destroyed.
- Accounts/projects and principals have permission to use the key in the recovery environment.
- Key policies, IAM policies, grants, aliases, and key versions are properly configured.
- The DR region has corresponding keys or provider-supported multi-region keys.
- Interdependent keys (KEKs, signing, database encryption) have a proper recovery order.
- Contacts/escalation paths exist for account recovery and provider support.

Never assume a managed key in Region A automatically works in Region B. Multi-region key semantics, replication, import/export, and deletion vary by provider. Check documentation and test decrypting copied data in the DR environment.

### 7.4. Secure Key Backup

Exportable private keys should only be backed up via an approved procedure: encrypted with an independent protection mechanism, split permissions, restricted access, stored in a separate failure domain, and audited. Never store plaintext keys alongside database dumps or inside the same account those keys protect.

Not every key should be backed up. For certificates that can be reissued by a CA, re-issuance and validation procedures may be safer than storing private keys long-term. For non-reproducible keys, proper escrow/backup procedures are required.

### 7.5. Rotation and Decrypting Historical Data

When rotating keys, older data may remain encrypted under older key versions. Retain decryption capability until all retained data/backups have been re-encrypted or expired past retention.

Record metadata such as key ID, key version, algorithm, encryption context, and effective dates. Test restores against data encrypted across multiple key generations. Never destroy old keys simply because a new key has been issued.

### 7.6. Secret Rotation During DR

After a compromise incident, credentials may need rotation rather than restoring old secrets verbatim. Runbooks should distinguish:

- Secrets that must be restored to read data/boot the system.
- Secrets that must be rotated immediately because they were exposed.
- Secrets that can be regenerated once the recovery account is operational.
- Tokens/sessions that must be revoked, not restored.

Never restore a revoked or suspected-compromised credential just to get the application running faster.

## 8. Identity, Access Permissions, and Break-Glass

DR can fail before starting if admins cannot sign in to the cloud account, identity provider, or secret vault.

Prepare:

- Recovery identities independent of the IdP/region being protected whenever feasible.
- Break-glass accounts protected by MFA/hardware factors and dual control.
- Procedures to restore federation, SSO, DNS, and certificates.
- Minimal IAM policies or roles to read backups, decrypt, and provision DR.
- Lists of approvers, escalation contacts, and verification methods outside primary systems.
- Periodic login tests from recovery workstations/networks.

Break-glass credentials must be managed as highly sensitive assets: stored securely, unused in daily operations, alerting on every use, and rotated after drills or incidents per policy.

## 9. External Dependencies to Include in the Recovery Plan

### 9.1. Identity Providers

Applications may rely on SSO, OIDC/SAML, MFA, directory sync, and identity federation. Retain configuration exports, issuer/metadata, client IDs, redirect URIs, group mappings, signing/encryption certificate references, and emergency admin procedures. Client secrets/private keys belong in a vault.

If the primary IdP suffers an outage, is a local recovery admin needed? If so, that access must be restricted, audited, and activated only via formal procedure.

### 9.2. DNS, Domains, and Certificates

Retain zone files or DNS exports, records, TTLs, health checks, registrar ownership, domain renewal contacts, DNSSEC config, and certificate issuance procedures. A DNS record can be recreated, yet unavailable registrar access or DNSSEC keys can stall DR.

Define TTLs and traffic-cutover plans before an incident; never alter NS or DNSSEC hastily without knowing registrar and authoritative DNS status.

### 9.3. Payments, Email, and SaaS

Build a dependency inventory including:

- Provider/tenant/account and region.
- API base URLs, webhook endpoints, and subscriptions.
- Credential references, rotation owners, and expiration dates.
- Data export/retention and support SLAs.
- Rate limits, quotas, IP allowlists, and certificate requirements.
- Transaction reconciliation mechanisms after reconnecting.

Not every external dependency can be backed up. A payment provider may hold the authoritative ledger; the application must retain transaction references, idempotency keys, and reconciliation workflows rather than trying to copy the provider's private state.

### 9.4. Networking and Security Perimeter

Restore VPCs/VNets, subnets, routes, NAT, firewalls/security groups, private endpoints, peering, transit gateways, VPN/Direct Connect/ExpressRoute, WAF, and egress policies. Ensure external partner IP allowlists permit traffic from the DR region if the design requires it.

### 9.5. Messaging and Schema Registries

Queue/topic configs, retention, DLQs, partitions, consumer groups, ACLs, schema registries, and event compatibility can be mandatory dependencies. If messages reside on a primary broker that is lost, know whether an archive/replay source exists. Never assume queue messages are backed up automatically; verify service semantics and retention.

## 10. Recovery Sequence Based on the Dependency Graph

### 10.1. Recovering from Foundation Up to Application

The exact order depends on architecture, though a common sequence is:

1. **Recovery access:** accounts, identities, MFA, break-glass, auditing.
2. **Keys and trust:** KMS/HSM access, key policies, certificates, signing trust.
3. **Control plane:** networking, IAM roles, IaC backend/state, config services, registries.
4. **Data foundation:** storage, databases, transaction logs/PITR, schemas, and replication.
5. **Messaging and dependencies:** queues, schema registries, object stores, caches, or projections.
6. **Runtime:** compute, clusters, container images, application config, and secrets.
7. **Edge:** DNS, CDN, WAF, load balancers, certificates, and routing.
8. **Validation:** health checks, synthetic transactions, reconciliation, and phased traffic ramp.

This sequence is a reference framework. For example, database encryption keys must be ready before database restore; some identity services require networking and DNS; workloads may need queues before accepting traffic. Derive the exact order from the actual dependency graph.

### 10.2. Dependency Graph and Critical Path

~~~mermaid
flowchart TD
    ACCESS[Recovery identity and account access] --> KEYS[KMS / certificates / trust]
    ACCESS --> NET[Network and IAM baseline]
    KEYS --> DATA[Restore database and object data]
    NET --> CONTROL[Config, registry, deployment control plane]
    CONTROL --> DATA
    DATA --> BUS[Messaging and schema registry]
    DATA --> APP[Application runtime]
    BUS --> APP
    APP --> EDGE[DNS / WAF / load balancer]
    EDGE --> VERIFY[Smoke test and traffic ramp]
~~~

A component with many dependents sits on the critical path. Independent branches can run in parallel without violating prerequisite relationships. Specify owners and completion criteria for each node.

### 10.3. Recovery Manifest

A manifest helps select matching versions of data, config, images, and keys:

~~~json
{
  "recoveryId": "dr-2026-11-18-01",
  "target": "ap-southeast-2",
  "database": {
    "snapshotId": "snapshot-042",
    "logPosition": "checkpoint-991",
    "schemaVersion": "2026.11.18.3"
  },
  "application": {
    "imageDigest": "sha256:example-digest",
    "release": "booking-api-4.8.2"
  },
  "configuration": {
    "version": 184,
    "tenantRegistryVersion": 72
  },
  "encryption": {
    "keyReferences": ["db-kek-v7", "object-key-v3"]
  }
}
~~~

This is an illustrative structure; never put secret values inside a manifest. Manifests should be signed or stored with integrity controls, reviewed by approvers, and point to immutable artifacts.

## 11. Backup Placement, Isolation, and Tamper Resistance

### 11.1. Keep Backups Out of the Same Failure Domain

Backups in the same account, under the same admin roles, and in the same region as production can be lost in the same outage or deleted simultaneously. Consider:

- Cross-region copies for region-outage risk.
- Cross-account/project/subscription copies for credential-compromise risk.
- Dedicated backup vaults with independent policies.
- Immutable retention or object locks.
- Offline/air-gapped copies for extremely critical data where appropriate.

Each layer adds cost, egress, key management complexity, and restore steps. Choose based on threat model, RPO/RTO, and retention obligations.

### 11.2. The 3-2-1 Rule and Variants

The 3-2-1 rule is commonly interpreted as having multiple copies across more than one storage type/location with at least one copy off-site/outside the primary failure domain. In cloud environments, extend this thinking to:

- Having more than one verified copy.
- Having a copy in an independent failure domain.
- Having at least one copy resistant to modification/deletion by production credentials.
- Having a copy restorable without total dependence on the primary control plane.

Copy count alone never replaces verifying consistency, retention, and restorability.

### 11.3. Immutability and Least Privilege

Backup writers should only create copies; deletion/retention overrides should use separate identities requiring approval or MFA. Recovery operators should only read backups and restore into authorized targets. Every change to retention, vault policies, key policies, and replication must be audited.

### 11.4. Independent Backup Catalog

Maintain a catalog showing which backups exist, which system they belong to, timestamps, regions, encryption key references, checksums, retention, owners, test status, and associated recovery sets. The catalog needs an independent copy so the team never loses the ability to locate backups during an incident.

Never store secrets inside the catalog; use resource IDs and secret references resolvable in the recovery environment.

## 12. RPO, RTO, and Retention Drive Backup Strategy

### 12.1. RPO

RPO is the maximum data loss an organization accepts, usually expressed as time prior to the incident. A 15-minute RPO means the recovery point must be no older than roughly 15 minutes before the incident under the agreed measurement method and scope.

### 12.2. RTO

RTO is the target time to restore a service to a defined operating level. RTO is not just database restore time; it includes access, keys, networking, data, applications, DNS, testing, and opening traffic.

### 12.3. Example Policy Selection

| Workload | Example RPO/RTO | Backup/DR Approaches to Consider |
|---|---|---|
| Booking/payment core | Very low RPO, short RTO | Continuous PITR/log backups, cross-region recovery, runbooks, and frequent drills |
| Listing/catalog | Multi-hour RPO may fit depending on business | Periodic snapshots, object versioning, exports/replicas, and index rebuilds |
| Search projection | Regenerable from source/events | Retain schemas and event replay sources; snapshots to speed up rebuilds |
| Cache/session | Regeneration or partial loss acceptable per policy | No need to back up every entry; retain config and source data |
| Audit/compliance | Long retention, high integrity | Immutable archives, access logs, legal holds, and retrieval tests |

These values only illustrate tiering. RPO/RTO must be approved by business owners and proven through testing on real datasets.

### 12.4. Retention Policy

Retention must consider:

- RPO and the corruption/ransomware detection window.
- Audit durations, contracts, and legal holds.
- Storage, retrieval, and cross-region transfer costs.
- Transaction log retention for PITR.
- Retaining keys capable of decrypting backups.
- Ability to restore matching application/schema versions.

A 90-day backup whose key is destroyed after 30 days is not a 90-day recovery plan.

## 13. Backup Automation and Procedures

### 13.1. Backup as Code

Define backup policies in versioned code/config: protected sources, schedules, retention, destination vaults/accounts/regions, encryption, immutability settings, notifications, and owners. Review backup policy changes as critical infrastructure changes.

### 13.2. Post-Backup Tasks

A workflow can:

1. Create snapshot/export.
2. Confirm job success and backup ID.
3. Verify size, checksums, or metadata per service capabilities.
4. Copy to the target account/region.
5. Apply retention/immutability.
6. Update the backup catalog.
7. Alert on missing copies, schedule delays, or quota/storage failures.

Never mark a backup healthy solely because the job API returned success. Verify the copy finished and is retrievable at the recovery destination.

### 13.3. Backup Monitoring

Key metrics:

- Backup success/failure rate.
- Age of latest successful backup.
- PITR log gaps and replication lag.
- Cross-region copy completion time.
- Backup bytes, growth, and storage capacity.
- Encryption/key availability.
- Immutable retention status.
- Restore test pass rate and measured restore duration.
- Backup catalog drift against resource inventory.

Alerts should align with RPO: if the latest recoverable point exceeds the RPO threshold, trigger a backup incident even if the most recent job just ran.

## 14. Restore Testing: The Most Important Evidence

### 14.1. Why You Must Test Restores

A backup can exist yet be unusable because:

- Files/dumps are corrupted or missing log segments.
- Keys are disabled, deleted, or policies deny decryption.
- Matching schema migrations or compatible application versions are missing.
- Backups reside in an inaccessible account/region.
- DNS, certificates, identities, or secrets cannot be recreated.
- Object metadata is out of sync with the database.
- Restore exceeds RTO or consumes unexpected capacity.

### 14.2. Testing Levels

| Level | Execution | What It Proves |
|---|---|---|
| Metadata check | Verify job, backup ID, size, checksum, retention | Copies exist and metadata is valid |
| Isolated restore | Restore into a sandbox account/network | Data can be read/decrypted and started |
| Application validation | Run app and business queries | Schemas, config, and runtime are compatible |
| DR exercise | Restore full dependencies, shift simulated traffic | End-to-end procedure is executable |
| Business validation | Reconcile transactions, reports, owner sign-off | Data has business integrity and is accepted |

### 14.3. Restore Must Test Keys

A critical test uses an identity in the recovery environment to:

1. Access the backup.
2. Retrieve the right key reference/version.
3. Decrypt a snapshot or sample object.
4. Start the database and read test data.
5. Verify certificates/signatures or tokens if in scope.

Do not merely check that a key exists; prove the recovery principal has permission to use the key and the key can still decrypt historical data.

### 14.4. Measuring Actual RTO

Record start and end timestamps for each step: obtaining access, creating networking, restoring databases, restoring files, deploying apps, checking dependencies, DNS cutover, and smoke testing. Total duration including approval wait times must be compared against RTO. If it exceeds targets, improve the runbook or architecture.

## 15. Scenario-Based Recovery Runbooks

### 15.1. Primary Region Loss

1. Activate incident command and confirm region outage scope.
2. Verify recovery account/identity and backup vault access.
3. Select recovery set and point-in-time meeting RPO.
4. Check keys/KMS, networking, and configuration in the target region.
5. Restore databases/objects and recover schemas and dependencies.
6. Deploy immutable artifacts with compatible configuration.
7. Smoke test data, identity, queues, and external integrations.
8. Shift traffic under control; monitor errors and replication.
9. Record achieved RPO/RTO and preserve the old source per policy.

### 15.2. Cloud Account Loss or Compromise

- Use an independent recovery identity/account and verify administrative privileges.
- Access cross-account immutable backups if still protected.
- Do not reuse credentials or signing keys suspected of exposure.
- Rotate/reissue secrets, certificates, and integration credentials.
- Inspect audit logs, resource drift, and potential attacker persistence.
- Recreate infrastructure from verified IaC inside a clean account.
- Restore data from trusted copies after identifying a pre-compromise point.

### 15.3. Accidental Deletion or Logical Corruption

1. Stop jobs or deployments causing data corruption.
2. Identify the first timestamp of bad data and affected scope.
3. Choose a PITR target prior to the faulty transaction.
4. Restore into a separate environment; do not overwrite production immediately.
5. Extract/compare data needing repair and verify invariants.
6. Apply approved repairs or cut over to the recovered instance.
7. Reconcile transactions occurring after the recovery point.

### 15.4. Lost Key or Certificate

Distinguish temporarily disabled keys, misconfigured policies, deleted keys recoverable within a deletion window, permanently destroyed keys, and expired certificates. Check provider recovery windows, replicas/backups, and key versions. If a key is unrecoverable, assess re-encryption, reissuance, or irreversible impact before claiming backups remain usable.

## 16. Common Mistakes

| Mistake | Consequence | How to Improve |
|---|---|---|
| Backing up only the database | Missing config, keys, images, and dependencies prevent app startup | Recovery set covers the entire dependency graph |
| Treating replicas as backups | Accidental deletes/corruption spread to replicas | Versioned/immutable backups and PITR |
| Keeping backups in the same account with production admin rights | Attackers can delete backups too | Cross-account vaults, least privilege, immutability |
| Losing KMS keys or policies | Snapshots exist yet cannot be decrypted | Key inventory, policy backup/recovery, and decrypt tests |
| Unversioned configuration | Cannot recreate system behavior at recovery point | Config as code, versioning, and manifests |
| Saving only image tags | Tags can mutate, hiding the exact binary | Pin digests and keep immutable artifacts |
| Unprotected IaC state | Cannot update/reconcile infrastructure | Encrypted state backups, access control, and restore tests |
| Not backing up DNS/registrar access | Cannot shift traffic even when the app runs | Zone exports, registrar recovery, and documented processes |
| Expired certificates/secrets in DR | Connections or authentication fail | Expiry monitoring, renewal runbooks, and key inventory |
| Treating backup job success as restore success | Failures discovered too late in a disaster | Isolated restores and DR exercises |
| Restoring data incompatible with app/schema | Runtime errors or corrupt writes | Recovery manifests and compatibility validation |
| Ignoring queue/event replay | Duplicate side effects or lost ordering | Idempotency, offsets, DLQs, and replay policies |
| Failing to protect runbooks/contacts | Responders cannot execute steps | Offline copies, owners, and contact reviews |

## 17. Example Recovery Set for the Booking Service

Suppose the Booking Service runs in one region using a relational database, object storage, event broker, KMS, identity provider, and payment provider.

### 17.1. Inventory

| Component | Authoritative Source | Protection Copy | Recovery Condition |
|---|---|---|---|
| Booking DB | Primary relational DB | PITR + cross-region snapshots | Compatible KMS key and schema |
| Attachments/invoices | Object bucket | Versioning + immutable cross-account copies | Object versions, checksums, and metadata |
| Application | Artifact registry | Image digest mirror and source repo mirror | Runtime config and deployment manifests |
| Tenant/config registry | Config/control-plane DB | Versioned snapshots/exports | Correct placement and policies |
| KMS | Managed key service | Key replicas/backups usable per provider | Recovery principal holds decrypt rights |
| Identity | IdP | Federation/config exports, break-glass | Valid issuer, certificates, and admin access |
| Messaging | Broker | Topic/schema config and archives if required | Safe offsets/replay and idempotent consumers |
| DNS/certificates | Registrar/DNS provider/CA | Zone exports, IaC, issuance procedures | Admin access and valid certificates |
| Payments | Provider system of record | Transaction references and reconciliation logs | New credentials, webhooks, and idempotency |

### 17.2. Recovery Sequence

~~~mermaid
flowchart TD
    A[Recovery identity and account] --> B[KMS and certificates]
    A --> C[Network and IAM]
    B --> D[Restore Booking DB and objects]
    C --> E[Restore config and deployment control]
    D --> F[Start event broker and schema registry]
    E --> G[Deploy Booking API]
    F --> G
    G --> H[Validate payment and identity integrations]
    H --> I[DNS cutover and traffic ramp]
    I --> J[Reconcile bookings and attachments]
~~~

### 17.3. Completion Criteria

- Database restore reaches the approved recovery point.
- Application starts on the right release and schema version.
- Booking records can be read/written per verified invariants.
- Referenced files exist, pass checksums, and can be decrypted.
- Identity, payment webhooks, and certificates operate properly.
- Queue consumers start from safe offsets/replay points with side effects deduplicated.
- DNS/edge shifts traffic; error rates and latency stay within thresholds.
- Business owners reconcile bookings, payment references, and transaction counts.
- Actual RPO/RTO are recorded.

## 18. Well-Architected Evaluation

| Pillar | Question | Mitigations and Trade-Offs |
|---|---|---|
| **Operational Excellence** | Are catalogs, owners, versions, and runbooks maintained for every recovery dependency? | Backup as code, inventories, restore exercises; adds metadata maintenance effort |
| **Security** | Are backups, keys, and break-glass independent of production credentials? | Cross-account isolation, immutability, least privilege, MFA, and auditing |
| **Reliability** | Can data and dependencies recover in proper order within RTO/RPO? | PITR, recovery sets, dependency graphs, restore testing, and reconciliation |
| **Performance Efficiency** | Does restore have enough IOPS, networking, compute, and throughput to catch up? | Capacity planning, parallel restores, and traffic ramps; standby resources add cost |
| **Cost Optimization** | Are there duplicate backups, excessive retention, or needlessly expensive archives? | Data tiering, lifecycle policies, compression, and retention reviews |
| **Sustainability** | Are valueless artifacts or redundant copies consuming storage/network avoided? | Justified retention, audited cleanup, and snapshot/rebuild by criticality |

A backup has value only when it holds the right data, retains its keys, is accessible in the required failure domain, and can be restored within business-acceptable timelines.

## 19. Practice Exercises

### Exercise A — Snapshot Without a Key

The team has a database snapshot in the standby region, but the KMS key resides in the locked production account.

**Question:** Why is the backup insufficient? What evidence must be added?

**Hint:** Identify key recovery/replication and policies, identities authorized to use the key, and compatible key versions, then execute a decrypt/restore test from the standby account. Seeing a key ID in metadata alone does not prove decryption works.

### Exercise B — Config Drift

The IaC repository contains old configuration, while production routes, security groups, and database parameters were modified manually.

**Question:** Is standing up DR directly from the repo safe?

**Hint:** Not yet. Perform inventory and drift reconciliation, choose the approved desired state, update IaC, and test the plan in the target account/region. Never apply old state blindly.

### Exercise C — Database and Object Timestamp Skew

A 10:00 DB snapshot references an object upload that only replicated at 10:07. Recovery only has object backups up to 10:05.

**Question:** Can the restore be declared complete?

**Hint:** No, if 10:00 records reference nonexistent objects. Use object versioning/manifests or synchronized consistency groups, reconcile references, and accept/repair missing data per policy.

### Exercise D — Compromised Credentials

After ransomware, the team wants to restore original API secrets and signing keys verbatim from backup to save time.

**Question:** What are the risks and how should this be handled?

**Hint:** Attackers may already possess those secrets. Restore decryption access needed for data, yet rotate/revoke affected credentials, reissue signing keys with planned public-key/token overlap, and verify integrations.

### Exercise E — Breached RTO

Database backup restore takes 45 minutes, yet standing up networking, identity, DNS, and the application takes another 90 minutes.

**Question:** What is the service's RTO and where should improvements focus?

**Hint:** End-to-end RTO covers total time until the service meets recovery criteria, not just the database. Optimize the control plane, IaC, recovery identity, automation, pre-provisioned capacity, and critical-path dependencies.

### Exercise F — Queue Replay

After restore, the team replays all messages from the broker archive, causing consumers to send duplicate booking confirmation emails.

**Question:** What must be designed before replaying?

**Hint:** Event IDs, inbox/idempotency, offsets/sequences, replay windows, side-effect type filtering, and dry-run modes. Distinguish updating projections from non-repeatable actions like emails or payments.

## 20. Checklist Before Approving a Backup and Recovery Plan

- [ ] Recovery set and dependency graph established for every critical service.
- [ ] Each component has an owner, source of truth, backup method, retention, and restore procedure.
- [ ] Databases have snapshots/PITR/log retention matching RPO.
- [ ] Required schemas, migrations, extensions, metadata, and sequences are protected.
- [ ] Object storage has versioning, replication/immutable copies, and manifests/checksums where needed.
- [ ] Runtime config, feature flags, tenant routing, and entitlements are versioned.
- [ ] IaC source, state, provider locks, modules, and pipelines are separately protected.
- [ ] Source code, image digests, packages, and deployment manifests have immutable mirrors/artifacts.
- [ ] KMS, HSM, DEK/KEK references, signing keys, certificates, and rotation history have recovery plans.
- [ ] Recovery identities, break-glass, MFA, dual control, and IAM policies have been tested.
- [ ] DNS, registrar, WAF, CDN, networking, IP allowlists, and trust dependencies are inventoried.
- [ ] SaaS/payment/email/IdP have endpoints, credential references, quotas, contacts, and reconciliation procedures.
- [ ] Queues/topics, schema registries, DLQs, offsets, and replay policies are defined.
- [ ] Backups reside in independent failure domains with appropriate immutability/access controls.
- [ ] Independent backup catalog records snapshot IDs, timestamps, key references, checksums, retention, and owners.
- [ ] Restore sequencing reflects the dependency graph and critical path.
- [ ] Recovery manifest aligns compatible data, schema, application, config, and key versions.
- [ ] Scheduled isolated restores, application validations, and DR exercises exist.
- [ ] Actual RPO/RTO measured including approvals and dependency restoration.
- [ ] Runbooks exist for region loss, account compromise, corruption, key failure, and queue replay.
- [ ] Post-compromise secret rotation/revocation procedures and audit evidence protection exist.

**Core takeaway:** DR does not merely restore data—it restores the entire ability to operate a service. Databases, objects, configuration, IaC, artifacts, identity, DNS, secrets, keys, and external dependencies must each have clear owners, versions, copies, and restore procedures. The dependency graph governs recovery order; the recovery manifest pairs compatible versions; and restore tests prove keys, permissions, data, and applications actually work. Only when end-to-end RPO/RTO are measured does an organization have evidence that its plan can meet business needs.
