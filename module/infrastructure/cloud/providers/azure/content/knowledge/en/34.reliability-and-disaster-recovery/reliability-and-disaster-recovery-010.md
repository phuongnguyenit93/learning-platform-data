# Designing Service-Appropriate Data Recovery

An e-commerce application on Microsoft Azure might run its API on Azure App Service or Azure Kubernetes Service (AKS), store orders in Azure SQL Database, carts in Azure Cosmos DB, invoice PDFs in Azure Blob Storage, shared files via Azure Files, messages in Azure Service Bus, and secrets in Azure Key Vault. When an operator accidentally deletes orders, when ransomware alters thousands of files, or when an entire region goes down, **there is no single "restore Azure" button** that brings the whole system back into a consistent state.

Each service has its own storage model, backup mechanism, and recovery path. For Azure SQL, you may need a point-in-time restore (PITR) into a new database; for Blob Storage, versioning/soft delete, backups, or cross-location replication; for Service Bus, restoring **message bodies** is not the same as restoring namespace configuration; for a Redis cache, the right recovery path may simply be rebuilding from the primary data source. **Designing service-appropriate data recovery** means choosing a set of mechanisms, execution order, responsibilities, and test evidence that satisfy business value and real failure modes.

This lesson belongs to the **Reliability and Disaster Recovery** chapter of the `CLOUD_PROVIDERS_AZURE` module. It connects Azure knowledge from subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, and databases through deployment, monitoring, security, and cost. Its scope spans Azure design, realistic failure scenarios, safe inspection/lab commands, runbooks, and drill acceptance criteria.

**Boundary:** all subscription names, resource groups, resource names, minute figures, and costs in examples are hypothetical. Never run delete, restore, failover, or backup-policy changes in production without approval. Features, retention limits, regions, tiers, SKUs, and Azure CLI commands evolve over time; before deploying, consult official documentation for the exact service, subscription, and region.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish logical data loss, accidental deletion, corruption, ransomware, app bugs, zone loss, region loss, and account compromise.
2. Explain **RPO, RTO, RLO**, durability, availability, data consistency, backup retention, and recovery points.
3. Distinguish **backups, snapshots, versioning, soft delete, replication, failover, restore, and replay**.
4. Classify data into systems of record, derived data, caches, event logs, and configuration metadata.
5. Build a **service × failure mode × protection mechanism × RPO/RTO × recovery limits matrix**.
6. Design Azure SQL Database PITR, long-term retention, geo-restore, and active geo-replication/failover groups for their proper purposes.
7. Distinguish Azure SQL Managed Instance recovery, Managed Instance links/failover groups, and database-level restores per supported capabilities.
8. Select backups, zone-redundant HA, PITR, and geo-restore for Azure Database for PostgreSQL/MySQL Flexible Server.
9. Distinguish **periodic** vs. **continuous** backups in Azure Cosmos DB, multi-region replication, and change feed.
10. Choose appropriate Blob soft delete, versioning, container recovery, replication, operational/vaulted backups, and immutability.
11. Understand the distinct constraints of **ADLS Gen2**, Azure Files snapshots/backups, and Managed Disks/VM backups.
12. Protect stateful workloads on AKS: manifests/IaC, volumes, external databases, and consistency.
13. Design recovery for Azure Service Bus, Event Hubs, and Azure Queue Storage based on real data replay/reconstruction capabilities.
14. Recover Redis caches, Key Vault secrets/keys, and Azure App Configuration after unintended edits or deletion.
15. Define data recovery in ETL/data lake/Synapse/Databricks/Delta pipelines when tables and sources sit at differing timestamps.
16. Sequence cross-service recovery, protect identities/networking/encryption keys, test integrity, and reconcile side effects.
17. Build investigation runbooks, recovery, rollback/failforward paths, drills, and RPO/RTO evidence.
18. Weigh the cost of extended retention and geo-redundancy against data-loss risk and downtime impact.

## 2. Identify the Exact Failure Class Before Choosing a Tool

### 2.1. Distinct Failure Categories

| Failure | What happens | Priority mechanisms to evaluate |
|---|---|---|
| Accidental single-record delete | Faulty DELETE or API call | Isolated PITR/restore, logical replay |
| Deploying code that writes bad data | Corruption spreads across many records | Pre-fault backup, selective restore, and reconciliation |
| Accidental Blob/file delete | Object vanishes from active view | Soft delete, versions/snapshots, backups |
| Object overwrite | New content replaces old version | Versioning/snapshots, PITR where supported |
| Ransomware or compromised credentials | Data and online copies may be altered/deleted | Immutability, isolated recovery copy, revoke credentials |
| Disk/VM failure | OS or local data loss | Disk snapshots, Azure Backup, image/IaC rebuild |
| Availability Zone outage | One zone stops functioning | Zone-redundant architecture/HA, tested failover |
| Region outage | Primary service/region unreachable | Cross-region architecture, geo-replication, geo-backup/restore |
| Broken key/secret/config | App cannot decrypt or connect | Key Vault recovery, version history, config export/IaC |
| Lost broker namespace | Queues/topics unavailable or message state lost | Service-specific DR, producer retries, durable event archive |
| Replication lag / silent corruption | Replicas receive bad data from primary | Independent restore point, detection, and isolation |
| Network/Entra misconfiguration | Data is intact yet workloads cannot read it | Restore IAM/DNS/VNet/identity; avoid pointless DB restores |

**A synchronous or near-synchronous replica will replicate a bad DELETE too.** Therefore, replicas/HA handle availability and do not replace backups that restore to a point before the fault.

### 2.2. Triage Flowchart

~~~mermaid
flowchart TD
    A["Data / service incident"] --> B{"Is data lost/corrupted or just inaccessible?"}
    B -->|"Inaccessible"| C["Check identity, DNS, network, HA, region"]
    B -->|"Deleted / corrupted"| D{"Independent recovery point available?"}
    D -->|"Yes"| E["Isolated restore + verify integrity"]
    D -->|"No"| F["Replay trusted source / partner recovery"]
    C --> G{"Does primary return within RTO?"}
    G -->|"Yes"| H["Failback / fix infrastructure"]
    G -->|"No"| I["Failover / geo-restore per design"]
    E --> J["Reconcile cross-service state"]
    F --> J
    I --> J
    H --> J
    J --> K["Canary, verify business flows, open traffic"]
~~~

Order matters: **do not restore a database when the real issue is Private DNS or a revoked managed identity**. Conversely, do not fail over to a replica that already replicated corrupted data.

## 3. Concepts You Must Distinguish

### 3.1. Recovery Point Objective (RPO)

**RPO** is the maximum data loss the business tolerates, measured as the gap between the incident timestamp and the restored data timestamp.

~~~text
Incident occurs: 10:00
Latest recoverable data point: 09:55

Observed potential data loss window:
  10:00 - 09:55 = 5 minutes

If target RPO = 15 minutes:
  5 minutes <= 15 minutes → meets RPO target (in this example).
~~~

Do not confuse RPO with a **backup schedule**: backing up every 15 minutes does not guarantee a 15-minute RPO in every outage if jobs fail, lag, or produce unusable points. With async geo-replication, data loss on forced failover depends on actual replication lag.

### 3.2. Recovery Time Objective (RTO)

**RTO** is the target duration for a service or business capability to return to an agreed operational level after disruption.

~~~text
Incident starts: 10:00
Business verification passes: 10:42
Observed recovery time = 42 minutes

If target RTO = 60 minutes:
  42 minutes <= 60 minutes → passed in drill.
~~~

When the restore command finishes **is not when the application is recovered**. RTO must include incident detection, approval, identity/network recovery, deployment, warm-up, integrity checks, and traffic cutover.

### 3.3. Recovery Level Objective (RLO)

**RLO** specifies the minimum service level required when RTO is reached:
- The entire system exactly as before?
- Order intake only, while reports can lag?
- Read-only historical queries, with writes paused?
- Live payment capture required, or temporarily queueing orders for later processing?

A 30-minute RTO for "API returns HTTP 200" does not equal a 30-minute RTO for **customers placing and paying for orders successfully**. Defining RLO prevents declaring DR successful while core business capabilities remain broken.

### 3.4. Retention, Frequency, and Granularity

- **Retention:** how long recovery copies are kept (e.g., 7 days, 35 days, 1 year).
- **Recovery granularity:** what unit can be recovered—full database, container, table, row, file, Blob, snapshot, or version.
- **Recovery point frequency:** selectable discrete timestamps or supported continuous granularity.
- **Backup window:** time taken to create/capture the copy.
- **Restore throughput:** speed of reading backups, transferring bytes, and standing up target resources.
- **Integrity:** whether restored data is valid and complete for business rules.
- **Isolation:** whether recovery can target a clean zone free of spreading corruption or malware.

### 3.5. RPO, RTO, and Consistency Are Three Distinct Targets

A mechanism with a small RPO does not necessarily have a small RTO, and vice versa:
- A geo-replica can cut over fast yet hold replicated bad data.
- A PITR backup can hit the exact pre-fault timestamp yet take hours to hydrate a large database.
- A volume snapshot finishes quickly yet cannot guarantee flushed DB transactions without quiescing.
- Restoring multiple services to the same timestamp does not automatically guarantee cross-service business transactions committed together.

## 4. Backup, Replication, Snapshots, Soft Delete: Clear Comparison

| Mechanism | Recovers accidental delete/edit | Handles regional failure | Isolation level | Typical limitations |
|---|---|---|---|---|
| **Automatic managed backup/PITR** | Yes, within retention/support | Depends on geo-backup support | Pre-fault recovery point | Restore duration, scope, retention |
| **Long-term retention backup** | Yes, at retained recovery points | Depends on backup storage location | Long-term compliance retention | Larger gaps between recovery points |
| **Snapshot** | Yes, point-in-time | Depends on snapshot region/replication | Snapshot-level | May be crash-consistent, not app-consistent |
| **Blob/file versioning** | Yes, for object versions | Depends on redundancy and feature support | Object-level | Does not protect all container/account settings |
| **Soft delete** | Yes, within retention window | Depends on resource type/region | Post-delete recovery | Not a fully isolated backup |
| **Zone redundancy/HA** | Usually no for logical deletes | Zone failure, not full region | HA/replicas | Replicates corruption |
| **Geo-replication** | Should not be treated as backup | Yes, per tier/lag | Active replica | Async data loss and failover complexity |
| **Continuous backup** | Yes, if PITR within window | Depends on service, region/tier | Point-in-time | Restore scope/target/constraints |
| **Export/ETL replay** | Depends on retained events | Yes, if archived elsewhere | Independent event/data copy | RPO tied to archive and replay logic |
| **IaC/GitOps** | For metadata/configuration | Yes, if artifacts/permissions ready | Code-defined state | Does not restore business data |

### 4.1. Treat the 3-2-1 Rule as a Principle, Not a Default Feature

A common governance principle: keep multiple independent copies across distinct failure domains, with at least one protected against deletion/modification by production runtime principals. Azure managed services may maintain internal copies, yet **that does not automatically give an organization a full 3-2-1 strategy**. Evaluate:
- Who has permission to delete all copies?
- Can you recover if the account/subscription is compromised?
- Is there an immutable/offline or equivalently isolated copy as required?
- Can you recover if decryption keys are lost?
- Do copies sit in the same region or under the same access control boundary?
- Have real restores been tested?

### 4.2. Replication Does Not Replace Backups

~~~mermaid
flowchart LR
    APP["Buggy app runs DELETE"] --> PRIMARY["Primary database"]
    PRIMARY -->|"Replication"| SECONDARY["Geo replica"]
    PRIMARY -. "Replicated delete" .-> SECONDARY
    BACK["PITR / isolated backup"] -->|"Restore before DELETE"| REC["Recovery database"]
~~~

For availability outages, you can fail over to the secondary. For corruption/deletions, the secondary likely already holds the bad state. A **pre-fault restore point** or independent archive is what saves you.

## 5. Building a Data Inventory and Decision Matrix

### 5.1. What to Ask Before Picking a Solution

For each dataset, document:
1. **Business owner** and data classification.
2. Is it a system of record or derived/cache data?
3. Azure resource, region, subscription, zone, SKU/tier?
4. Write patterns, writes/sec, size, and growth rate?
5. RPO/RTO/RLO, including regulatory retention mandates?
6. Top threats: accidental delete, overwrite, ransomware, region outage?
7. Required retention and granularity: row, table, object, database?
8. Existing backup/HA/replication mechanisms and who can alter them?
9. Upstream recovery dependencies: Key Vault, Entra, DNS, ACR, networking?
10. Are tools, scripts, integrity checks, and runbooks already proven?

### 5.2. Matrix for a Hypothetical Application

| Data | Role | Target RPO | Target RTO | Candidate mechanisms |
|---|---|---|---|---|
| Orders in Azure SQL | System of record | 5 minutes | 1 hour | PITR + HA/geo options, reconciliation replay |
| Carts in Cosmos DB | Business state | 15 minutes | 2 hours | Continuous backup, multi-region per tier |
| Invoice PDFs in Blob | Financial records | 1 hour | 4 hours | Versioning, soft delete, backups, immutability |
| Shared docs in Azure Files | Internal files | 24 hours | 8 hours | Snapshots/backups and tested restores |
| Service Bus commands | Work to process | Per event contract | 2 hours | Outbox, replay source, DR service support |
| Redis cache | Derived state | No business RPO | 30 minutes | Rebuild/warm, optional persistence |
| Key Vault secrets/keys | Recovery dependency | Zero loss of current and needed history | 1 hour | Soft delete/purge protection, IaC, recovery |
| AKS manifests | Runtime config | Latest Git commit | 1 hour | GitOps/IaC, image digests, cluster rebuild |
| Analytics aggregates | Derived/reporting | 24 hours | 24 hours | Data lake snapshots/Delta logs, ETL replay |

These targets **are hypothetical assumptions for practice**, not Azure SLAs or guarantees for any mechanism. If Orders requires a 5-minute RPO yet actual backups/replication cannot meet it or restores miss RTO, **change the architecture, lower RPO expectations, or renegotiate the SLO**.

### 5.3. Choosing Recovery Sources by Data Class

- **System of record:** usually requires backups/PITR, protected copies, and transaction integrity.
- **Derived data / materialized views:** can be rebuilt from source if source remains intact and ETL is deterministic.
- **Caches:** flushing and warming from source is normal; never treat a cache as the primary database.
- **Event logs / queues:** need replay strategies, checkpoints, idempotency, and event retention.
- **Files / objects:** need versioning, deleted-object recovery, and immutable retention where required.
- **Config / identity:** recover policies/IaC/keys, not just business data.
- **Temporary / scratch data:** total loss can be acceptable, provided it is documented.

## 6. Zone and Region Redundancy on Azure

### 6.1. Failure Domains

An Azure architecture must consider:
- **Process/Pod/VM:** failure of one compute unit.
- **Availability Zone (AZ):** datacenter/zone outage in supported regions.
- **Region:** loss of most services across a geography.
- **Subscription/account boundary:** resource deletion/modification or lost identity permissions.
- **Administrative/security boundary:** compromised operator or automation account.
- **Data corruption boundary:** bad data replicated everywhere.

Not every Azure region has the same Availability Zone count, nor does every SKU support zone redundancy. Verify per service, region, and tier.

### 6.2. LRS, ZRS, GRS, and RA-GRS for Azure Storage

| Storage option | Goal | Points to remember |
|---|---|---|
| **LRS** | Copies within one physical location/region | Does not protect against full region loss |
| **ZRS** | Synchronous replication across zones in supported regions | Not cross-region DR |
| **GRS** | Asynchronous copy in a secondary region | Forced failover risks losing unreplicated data |
| **RA-GRS** | Like GRS, plus bounded read access to secondary | Secondary is typically read-only before failover |
| **GZRS** | Zone-redundant primary + async geo copy | Availability and pricing vary by region/SKU |
| **RA-GZRS** | GZRS plus secondary read access | Not synchronous cross-region writes |

For example, an accidentally deleted Blob is a normal logical change that replicates immediately; Storage GRS **does not replace** soft delete, versioning, or backups. Secondary replicas can lag; never claim RPO=0 merely because GRS is enabled.

### 6.3. Last Sync Time Is Not a Zero-Data-Loss Guarantee

With geo-redundant Storage, replication status and **Last Sync Time** (where provided by the resource/redundancy type) help gauge how much data likely replicated. A **customer-managed failover** when primary is unreachable can lose writes made after the last sync point. The secondary is not writable by default before failover is executed.

Never invoke failover before:
1. Confirming a true region outage rather than DNS/IAM failure.
2. Checking replication status/lag per service capability.
3. Getting business sign-off on potential data loss.
4. Understanding endpoint/account topology changes.
5. Preparing app reconnection and downstream consistency.
6. Having a failback and post-failover operations plan.

### 6.4. Zone Failover vs. Geo-Restore

- **Zone-redundant HA** mitigates intra-region infrastructure faults.
- **Geo-replicas / failover groups** let traffic switch to another region per service capabilities.
- **Geo-restore from backup** builds data elsewhere, typically taking longer than failing over to a warm/hot replica.
- **PITR/retention** targets logical corruption by choosing a pre-fault recovery point.

A design may need **HA, DR, and backups together**: three distinct objectives.

## 7. General Backup Principles for Azure Managed Services

### 7.1. Protection Scope Must Include Metadata and Dependencies

A database backup may preserve tables while omitting:
- Networking / Private Endpoints / DNS.
- Microsoft Entra applications / role assignments.
- Managed identities / principals.
- Key Vault access / network policies.
- CI/CD artifacts and container image digests.
- API Management routes or Front Door origin settings.
- Application configuration / feature flags.
- SQL server-level logins or external secrets, depending on service type.

**Recovery plans need Infrastructure as Code and control-plane rebuild runbooks**, while protecting secrets/keys under least privilege.

### 7.2. Schedules and Retention Must Follow RPO

Account specifically for:
- Freshness of the latest recovery point.
- Succeeded backups vs. merely scheduled jobs.
- Backup/replication lag.
- Backup location and availability if the primary region goes down.
- Time required to copy/hydrate large datasets.
- Retention and legal holds.
- Whether single-object or single-row selective restore is possible.
- Whether restore creates a **new resource** or overwrites in place.
- Whether production principals can delete backups or shorten retention.

A daily backup cannot meet a 15-minute RPO for an order database—yet it may suffice for HR handbook files edited weekly.

### 7.3. Retention Does Not Equal Immutability

- **Backup retention:** lets you choose recovery points within the retention window.
- **Soft delete:** provides a recovery grace period before permanent deletion per policy.
- **Immutability / WORM:** blocks edits/deletes of protected copies during retention per lock mode/policy.
- **Resource locks:** help prevent accidental management-plane mistakes, not a complete barrier against all privileges or data-plane APIs.
- **RBAC/PIM/MFA:** restrict who can delete, purge, disable backups, or shorten retention.

Ransomware-resilient designs separate app runtime rights (writing only required business objects) from backup-admin rights, use immutable/isolated copies where supported, and rehearse restores in clean environments.

### 7.4. Encryption and Keys

Encrypted backups do not guarantee the recoverer can decrypt them. With customer-managed keys (CMK), a lost or purged Key Vault/HSM key can render backups or replicas unreadable depending on the service.

Document:
- Which key identifier/version is used.
- Key Vault availability/geo strategy.
- Unwrap/decrypt permissions for the restore principal.
- Key rotation and retention strategy.
- Soft delete/purge protection/key backups where supported.
- How recovery works if the primary identity/subscription fails.

Never store encryption keys or access tokens in exercises or recovery tickets.

### 7.5. Record Backup Success and Rehearse Restores

A complete check goes beyond "backup completed":

~~~text
Backup succeeded → usable recovery point
  → Restore to isolated target
  → Validate object counts/checksums
  → Validate schema, indexes, constraints
  → Start app against restored data
  → Reconcile linked records/events
  → Measure RPO, RTO and observed data loss
  → Record PASS/FAIL and cleanup
~~~

Azure Monitor / Backup Center / Restore jobs provide operational telemetry per service. Even a "Succeeded" restore job may still miss business criteria such as matching invoices for every paid order.

## 8. Azure SQL Database: PITR and Logical Recovery

### 8.1. Mechanisms

**Azure SQL Database** includes automated backups supporting point-in-time restore (PITR) within supported retention windows. Required backup data (full, differential, transaction logs per service architecture) is managed by Azure. Additional capabilities include:
- **Short-term retention (STR):** choose recent recovery points over a tier/config-dependent window, commonly up to around 35 days for many service tiers.
- **Long-term retention (LTR):** retains selected weekly/monthly/yearly backups—potentially for multiple years where supported—for compliance.
- **Geo-restore:** restores from geo-replicated backups into another region when redundancy/capabilities and recovery points permit.
- **Active geo-replication:** creates asynchronous readable geo-secondaries for regional continuity.
- **Failover groups:** groups databases/secondaries with endpoint routing/failover management per service/tier.

Not every feature or retention option exists on every database tier, deployment model, or region. Verify current capabilities in Azure Portal/CLI for the exact resource.

### 8.2. PITR Is the Primary Tool for Accidental DELETEs

Scenario:
- 09:40: buggy application code deletes 3,000 Orders.
- 10:05: operators detect the loss.
- Need Orders as of **09:39** to read pre-fault data.

Safe procedure:
1. Keep the live database intact so valid transactions after 09:40 are not lost.
2. Select PITR timestamp **09:39 UTC**.
3. Restore to a **new database** such as `orders_recovery_0939`.
4. Restrict network/permissions to recovery operators only.
5. Compare rows and business constraints between restored and live databases.
6. Extract missing records and **merge controllably** back into primary per idempotency/transaction plans.
7. Verify foreign keys, payments, and message state.
8. Never point the entire production app to the restored database if doing so drops valid orders placed from 09:40 to 10:05.
9. Log audit records and run a postmortem.

**PITR returns a database from an earlier timestamp**, not an in-place "UNDO DELETE 3,000 rows" button in production. The new recovery DB serves as the reconciliation source.

### 8.3. Azure CLI Metadata Inspection Example

These commands do not perform a restore:

~~~bash
RG="rg-orders-lab"
SERVER="sql-orders-lab"
DB="orders"

az sql db show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  --query "{name:name,status:status,edition:edition,backupStorageRedundancy:currentBackupStorageRedundancy}" \
  -o json

az sql db str-policy show \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$DB" \
  -o json
~~~

CLI fields and command availability depend on Azure CLI/API versions. Never print SQL admin passwords; viewers need ARM permissions, while querying data requires data-plane access.

### 8.4. PITR in an Approved Lab

Assuming a **lab** SQL Database with a unique unused destination name:

~~~bash
RG="rg-orders-lab"
SERVER="sql-orders-lab"
SOURCE_DB="orders_lab"
RESTORED_DB="orders_lab_restore_20261120"

# Run ONLY in an approved LAB; creates a new database and incurs charges.
az sql db restore \
  --resource-group "$RG" \
  --server "$SERVER" \
  --name "$SOURCE_DB" \
  --dest-name "$RESTORED_DB" \
  --time "2026-11-20T09:30:00Z"
~~~

The recovery point must fall within supported retention and before the incident. This creates a billable resource; clean up afterward under proper ownership. Never set the destination name to the source database, and never use a production server as a lab without approval. Restore duration depends on DB size, tier, workload, log chain, and service load.

### 8.5. Long-Term Retention (LTR) vs. PITR

LTR helps when an organization must restore data from 6–24 months ago or older; LTR backups are typically **discrete restore points** per policy rather than arbitrary second-by-second timestamps across years. To recover from an accidental delete at 09:40 this morning, STR/PITR is normally the right mechanism.

Test:
- LTR policy is configured and actually generating backups.
- Azure subscription/resources can still access those backups.
- Target restore region/server/tier is suitable.
- Encryption/key access and identities work.
- Restoring into dev does not expose PII risks.
- Retention satisfies regulations and budget.

### 8.6. Geo-Replication / Failover Groups Do Not Replace PITR

In a regional outage, a ready secondary yields a lower RTO than geo-restoring from backup. However:
- Cross-region replication is typically asynchronous, so **RPO is not zero by default**.
- Forced failover can lose transactions not yet replicated to the secondary.
- Deletes/corruption replicate to the secondary too.
- Listeners/endpoints, app reconnection, firewalls, and Private DNS must be prepared.
- Server-level users/logins/objects, jobs, alerts, and configs need separate inventory and DR plans per deployment model.
- After failover, verify committed data against logs, outbox rows, and payment gateways.

A database with an active geo-replica but no tested PITR restore **remains vulnerable to logical faults**.

### 8.7. Temporal Tables, CDC, and Audit Logs

Some applications use SQL temporal tables, change data capture (CDC), or audit/event sourcing for faster **row/table-level** recovery. These complement rather than replace backups:
- CDC retention is bounded.
- Temporal history can be altered by overly privileged principals.
- Audit logs rarely contain complete data needed for full reconstruction.
- Replay must be idempotent and enforce consistency constraints.
- Independent SQL restore remains necessary when systems are deeply compromised.

## 9. Azure SQL Managed Instance: Deployment Model Notes

**Azure SQL Managed Instance (MI)** provides automated backups/PITR plus optional long-term retention/cross-region recovery per supported capabilities. It differs from Azure SQL Database single/elastic pools:
- Broader SQL Server instance-level feature surface.
- VNet/private networking and DNS play a larger role during failover.
- Provisioning a new instance and restoring large backups can take significant time.
- Failover groups / Managed Instance links (where supported) and SQL Server migration scenarios need dedicated runbooks.
- SQL Agent jobs, logins, linked servers, and instance-level settings may not automatically follow a single database restore as expected.

### 9.1. Evaluating Database-Level vs. Instance-Level Recovery

| Need | What to verify |
|---|---|
| Accidental table delete | PITR to new DB then merge, or scripted recovery |
| MI instance outage | HA/service recovery per tier/config |
| Region outage | Failover group / geo-restore, networking, and endpoints |
| Lost instance config | IaC/metadata export, jobs/logins scripting |
| Key/credential failure | Entra/SQL logins, Key Vault, TDE/CMK recovery |
| SQL Server workload migration | Support/limits of MI link / backup-restore model |

**Do not reuse Azure SQL Database single-DB CLI commands directly for Managed Instance**; resource namespaces, restore commands, and permissions differ. Follow official MI docs for your version and measure RTO with real drills.

### 9.2. TDE, CMK, and Recovery

SQL TDE uses service-managed keys or CMK per configuration. If the TDE protector/key becomes unavailable, restores or geo-replicas can fail. Backing up keys, enabling soft delete/purge protection, updating key access, and testing restores belong in a complete DR design.

## 10. PostgreSQL Flexible Server and MySQL Flexible Server

### 10.1. Differences Between HA, PITR, and Backups

For **Azure Database for PostgreSQL Flexible Server** and **Azure Database for MySQL Flexible Server**, distinguish:
- Automated backups and retention windows for PITR.
- Restoring typically provisions a **new server** at the recovery point per service API rather than rolling back live production connections in place.
- **Zone-redundant HA** (where supported) mitigates AZ outages, not logical errors requiring PITR.
- **Read replicas** serve read scaling/DR depending on architecture, carry replication lag, and replicate DELETEs.
- **Geo-redundant backup / geo-restore** depends on features, region/SKU, and settings chosen when the server was created or updated.
- Cross-region restores have different RPO/RTO than local restores.

Never apply PostgreSQL rules blindly to MySQL or vice versa; retention, HA support, geo features, and CLI commands can differ.

### 10.2. Example PostgreSQL Config Inspection

~~~bash
RG="rg-orders-lab"
PG="pg-orders-lab"

az postgres flexible-server show \
  --resource-group "$RG" \
  --name "$PG" \
  --query "{name:name,state:state,backup:backup,highAvailability:highAvailability,fullyQualifiedDomainName:fullyQualifiedDomainName}" \
  -o json
~~~

Backup metadata fields can vary across Azure CLI/API versions. This is read-only; never print DB passwords or secret-bearing connection strings.

### 10.3. Sample PostgreSQL PITR Runbook

1. Identify the first bad write and pick a UTC recovery point.
2. Confirm the timestamp falls inside backup retention.
3. Choose target region, zone/HA, VNet/networking, and naming.
4. Restore into a **new** Flexible Server; never overwrite the source.
5. Reapply firewall rules, Private DNS, roles, extensions, and connectivity per actual deployment settings.
6. Inspect schemas, time zones, WAL/transaction consistency, and data.
7. If needed, extract deleted tables/rows and perform a controlled merge.
8. Update application connection strings/secrets if cutting over the entire server.
9. Test connection pooling and sequence/identity values.
10. Monitor write correctness, replay/offsets, and clean up lab resources.

A restored server is a distinct resource; it does not automatically reattach original DNS, monitoring, Private Endpoints, DB users, app secrets, or replication topologies.

### 10.4. Region Changes and Recovery Limits

Never assume geo-redundant backups are enabled just because HA is enabled. A server with zone-redundant HA in the primary region may still have zero backup copies in a secondary region. Conversely, having geo-backups does not guarantee a 15-minute RTO if restoring a large server takes hours.

For MySQL Flexible Server, verify separately:
- Supported backup redundancy and retention.
- Restore point / time granularity.
- Geo-restore capability and compatible target regions.
- HA/replica topology and RPO lag.
- Engine version, DB users/privileges, and connection dependencies.

### 10.5. Business-Level Validation After Database Restore

Post-restore, beyond row counts, verify:
- Read/write test transactions in an isolated environment.
- Foreign keys, indexes, constraints, and sequences.
- Reconciled order/payment statuses.
- Replication/CDC/ETL connectors if used.
- Time zones, collations/charsets, and extensions.
- Credentials/roles and query performance.
- Never open production traffic before reconciliation completes.

## 11. Azure Cosmos DB: Periodic Backup, Continuous Backup, and Multi-Region

### 11.1. Why Cosmos DB Needs a Tailored Design

Azure Cosmos DB uses a partitioned, globally distributed NoSQL model with RU/s throughput, multiple APIs, and tunable consistency. Backup/restore depends on **API, backup mode, tier, and account configuration**. Multi-region replication alone does not automatically give arbitrary point-in-time recovery.

Questions to answer:
- Does the account use API for NoSQL, MongoDB, or another API?
- Is backup mode **Periodic** or **Continuous**?
- What retention and granularity are specifically supported?
- Does the account use multi-region single-write or multi-write?
- Are restore permissions and the target recovery region supported?
- How are container/partition keys, TTLs, unique keys, and indexes configured?
- Does restore create a **new account** or follow API-specific scoping?
- Can the application switch to a new account and refresh connections?

### 11.2. Periodic Backup

**Periodic backup** captures copies at configured intervals and retention supported by the service. It fits scenarios that tolerate restoring to discrete backup points rather than arbitrary timestamps between snapshots.

Characteristics:
- Azure manages backups per account policy.
- Backup frequency/retention has bounds.
- Restore workflows and permissions differ from Azure SQL PITR.
- You generally cannot restore a single document directly in the portal; restore to an isolated target and query/copy selectively.
- Existing backups are not browsable like a live container.
- Potential RPO depends on intervals between successful backups.

### 11.3. Continuous Backup and PITR

**Continuous backup** lets you choose a point-in-time within the retention window per service capabilities; many Cosmos DB API/account combinations offer retention tiers such as **7 or 30 days** (verify current options by API/tier).

Key notes:
- Restores typically provision a **new Cosmos DB account** rather than rewinding the live account in place.
- May support account, database, or container-level recovery depending on API, yet it is not "undo one JSON document" in primary.
- Requires valid timestamp, scope, target location, and potentially a new account/resource identity.
- Mode conversions, geographic availability, unique keys, and restore constraints must be verified for the specific API/version.
- Writes occurring after the chosen timestamp do not automatically merge into the restored account.
- Account/container/index creation time and RU provisioning affect RTO and cost.

### 11.4. Backup Policy Inspection Example

~~~bash
RG="rg-orders-lab"
ACCOUNT="cosmos-orders-lab"

az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,backupPolicy:backupPolicy,locations:locations,consistencyPolicy:consistencyPolicy}" \
  -o json
~~~

This reads resource configuration only; never print keys or connection strings. If `backupPolicy` appears abbreviated in CLI output, inspect authorized Azure Portal/Terraform/ARM metadata. Never convert backup modes without reviewing constraints and irreversibility.

### 11.5. Scenario: Accidental Deletion of the Cart Container

1. An app bug deletes all carts at 13:10.
2. Stop the deleting actor / tighten permissions before restoring.
3. Identify recovery timestamp 13:09, backup mode, and container restore support.
4. Restore to an **isolated** target via Cosmos DB's supported mechanism.
5. Verify partition key paths, unique keys, indexes, TTLs, and document counts.
6. Reconcile carts updated validly by customers after 13:10 from event logs if available.
7. Avoid overwriting newer valid carts with stale restored copies.
8. Selectively merge records or shift connections to the new account under approval.
9. Verify RU budgets/throughput/capacity and consistency.
10. Monitor cart correctness and telemetry, then close the incident.

### 11.6. Multi-Region Consistency Is Not Backup

Cosmos DB supports geo-distribution, read regions, and certain multi-region write models. However:
- Bad deletes/updates propagate across regions.
- Multi-write conflict resolution affects business logic.
- Consistency levels (strong, bounded staleness, session, consistent prefix, eventual) govern read/write semantics, not rolling back deletes.
- Regional failover can alter latency, write availability, and consistency behavior.
- Actual RPO/RTO depends on architecture, failover policies, account mode, and cross-region propagation.
- Never claim "zero data loss" without proof for the exact setup.

### 11.7. Change Feed and Replay

**Change feed** can help:
- Maintain read models/materialized views.
- Replay certain changes to downstream processors within retention/mode limits.
- Build audit/event logs when engineered properly.
- Detect/alert on anomalous data mutations.

However, **change feed does not always retain before-images or all deletes** across every mode, does not replace continuous backup, and cannot restore arbitrary historical state if old data aged out. Understand modes, retention, checkpoints, TTLs, and recorded operation types.

### 11.8. Choosing Periodic vs. Continuous Backup in Cosmos DB

| Scenario | Direction to evaluate |
|---|---|
| Rebuildable cart state, 4-hour RPO | Periodic if it satisfies SLA and cost |
| Orders documents needing PITR near delete time | Continuous backup where supported by API/region |
| Continuity after a regional outage only | Appropriate multi-region/failover, **plus independent backups** |
| 3-year compliance retention | Evaluate dedicated archive/storage options; 7/30-day continuous is insufficient |
| Restore a single document | Restore to isolated target, query/merge document and links |
| Repair bad mass update | PITR before corruption, validate, and selective replay |

Avoid forcing one Cosmos DB backup mode across unrelated business domains with conflicting RPO/retention needs if one mode cannot satisfy both; consider splitting accounts with appropriate cost control.

## 12. Azure Blob Storage: Versioning, Soft Delete, Backup, and Replication

### 12.1. Distinguishing Overwrite, Delete, Account Loss, and Region Loss

A PDF invoice in Blob Storage faces distinct failure modes:
- **Overwrite:** blob name remains, yet content is wrong.
- **Delete:** blob moves to deleted state per enabled features.
- **Container deletion:** broader blast radius than individual blobs.
- **Mass corruption:** thousands of blobs modified by ransomware.
- **Storage account configuration loss:** RBAC, networking, or lifecycle policies altered.
- **Region outage:** endpoints cannot reach the primary region.

No single feature handles all of these failure modes alone.

### 12.2. Blob Versioning

On supported accounts/Blob types, **Blob Versioning** retains prior versions whenever a blob is modified/overwritten; recovery copies or promotes an older version.

Notes:
- Increases version count and storage cost.
- Lifecycle policies can purge old versions; align retention with SLAs/compliance.
- Version IDs need protection/auditing if used as evidence.
- Not all Blob types and account setups (especially HNS/ADLS Gen2) offer identical feature sets.
- Versioning **is not immutable** if an overly privileged principal can delete versions.
- With concurrent writes, understand ETags, `If-Match`, and conditional requests.

### 12.3. Blob Soft Delete and Container Soft Delete

**Blob soft delete** recovers deleted blobs/versions within retention if enabled prior to the incident. **Container soft delete** restores deleted containers per service conditions. They may require separate configuration.

| Scenario | Check |
|---|---|
| Single blob deleted | Is Blob soft delete enabled and within retention? |
| Blob overwritten incorrectly | Versioning/snapshots/Blob PITR? |
| Whole container deleted | Is container soft delete enabled and within retention? |
| Thousands of blobs logically corrupted | Operational/vaulted backup or PITR/versions supporting bulk restore? |
| Region outage | Storage redundancy/failover state and protected data |
| Attacker deletes versions | Immutable policy / isolated recovery copy? |

**Soft delete only helps if enabled beforehand and recovery happens within retention.** Never turn it on *after* an outage expecting prior data to reappear.

### 12.4. Operational Backup and Vaulted Backup for Blobs

Depending on account type and service/tier, **Azure Backup for Blobs** offers distinct modes:
- **Operational backup:** uses local Storage-account protections such as point-in-time restore/soft delete/change feed/versioning per support matrix—not equivalent to an independent copy inside a Backup vault.
- **Vaulted backup:** stores protected copies via Backup vault and supported policies, improving isolation and recovery choices over local-only protection.

Specific features carry limits on account types, hierarchical namespaces, regions, recovery granularity, and restore targets. Never call every Azure Blob backup a "vault snapshot" or assume vaulted backup works on every HNS account.

### 12.5. Blob Point-in-Time Restore and Preconditions

Storage Blob point-in-time restore, where supported by account/Blob types, restores block blobs to an earlier timestamp within a window. It typically depends on data-protection features like versioning/change feed/soft delete and imposes account/tier/namespace prerequisites.

If a document claims "30-day PITR," check:
- Were all prerequisite capabilities enabled on the account before the fault?
- Current retention and earliest restorable timestamp?
- Are any unsupported objects present?
- Does restore cover all blobs or specific subsets/ranges?
- Must applications pause writes during restore?
- Should a last-known-good copy be preserved before starting restore?
- Are storage capacity and budget approvals in place?

### 12.6. Immutability/WORM for Invoices and Compliance

Certain business records must be protected against edits or deletion before a retention date. **Azure Blob immutable storage** provides time-based retention or legal holds per supported features.

- A locked policy can be difficult or impossible to shorten.
- An erroneously written yet locked object may require creating a **new correction record** rather than editing the original.
- Immutable storage interacts with versioning, container-level policies, and HNS/account types.
- Never lock an entire test container without approval and understanding resource-deletion/cost implications.
- Encryption keys and IAM still require protection.

**Immutability does not ensure data was accurate when written**; if an app writes a wrong invoice and locks it, you need correction/offsetting records.

### 12.7. Inspecting Storage Account and Blob Protection

~~~bash
RG="rg-orders-lab"
SA="storderslab"

az storage account show \
  --resource-group "$RG" \
  --name "$SA" \
  --query "{name:name,sku:sku.name,kind:kind,isHnsEnabled:isHnsEnabled}" \
  -o json

az storage account blob-service-properties show \
  --resource-group "$RG" \
  --account-name "$SA" \
  --query "{blobDeleteRetention:deleteRetentionPolicy,containerDeleteRetention:containerDeleteRetentionPolicy,versioning:isVersioningEnabled,changeFeed:changeFeed}" \
  -o json
~~~

These commands only read configuration; they never expose secret keys or SAS tokens. Property names and CLI support can vary across CLI/API versions, so verify output in a lab before automating.

### 12.8. Recovering an Overwritten Invoice PDF

1. Stop the process writing bad content.
2. Identify blob URI, fault timestamp, and ETag/version ID.
3. Inspect valid prior versions/snapshots or backup restore points.
4. Copy the older version to a **new name in a recovery container** to inspect first.
5. Verify hash, size, metadata, and that the PDF opens cleanly.
6. Reconcile invoice number, amount, and the SQL order record.
7. Once approved, restore to the primary path or update the DB pointer.
8. Use conditional writes (`If-Match`) to avoid overwriting a newer valid version.
9. Check CDNs/caches/SAS URLs if distributed via edge.
10. Record audit trail, alerts, and retention evidence.

Never generate a **public SAS** to download sensitive data just to test a restore. Use Entra/RBAC with least privilege.

### 12.9. GRS Failover Does Not Undo Bad Data

A GRS Storage account supports regional recovery per service capabilities and failover policies, yet deletes/overwrites replicate too. After failover, account redundancy may change and need reconfiguration per service guidance. Build a dedicated DR procedure covering data plane, backups, endpoints, DNS, and billing.

## 13. ADLS Gen2: Data Lakes and Hierarchical Namespace

### 13.1. ADLS Gen2 Is Blob Storage with Different Semantics

**Azure Data Lake Storage Gen2** builds on Azure Blob Storage with a **hierarchical namespace (HNS)** for paths/directories and filesystem semantics. HNS changes naming, directory renames/deletes, ACLs, and support for several data-protection features.

Never copy a standard GPv2 Blob checklist to an HNS account without checking:
- Are versioning/soft delete/PITR supported for the **exact HNS configuration**?
- How are directory-level deletes/renames backed up and restored?
- Do POSIX-like ACLs/owner/group restore alongside the data?
- Does Azure Backup vaulted/operational backup support that resource type?
- Are events/Delta logs/checkpoint files preserved consistently with data?
- Do backups cover data lake access policies, network rules, and container permissions?

### 13.2. Bronze–Silver–Gold and Reproducibility

~~~mermaid
flowchart LR
    S["Sources / Event logs"] --> B["Bronze raw immutable"]
    B --> E["ETL / Spark"]
    E --> V["Silver curated"]
    V --> T["Aggregations"]
    T --> G["Gold serving tables"]
~~~

If **Bronze raw** stays intact, Silver/Gold can be rebuilt via pipeline code and versioned transformations—but only if:
- Source payloads and schema versions are preserved.
- Pipelines are deterministic or record external reference versions.
- Sensitive data and retention rules match.
- Compute/capacity exists to replay within RTO.
- Checkpoints, watermarks, and exactly-once assumptions are verified.
- All secrets, catalogs, storage credentials, and ACLs are restored.

### 13.3. Delta Lake Time Travel Is Not Backup

**Delta Lake** maintains transaction logs and data files to query older versions within retention. However:
- `VACUUM` / retention cleanup can purge files needed by older versions.
- If transaction logs or underlying ADLS objects are deleted or encrypted by ransomware, time travel fails.
- Time travel does not provide cross-region recovery if the storage region goes down.
- A Delta table can revert its own view while downstream consumers already ingested bad data.
- Check version-restoration limits in your exact platform (Databricks, Synapse, OSS Delta).

Therefore, **protect underlying storage + versioned pipeline code + checkpoints** rather than relying solely on a time-travel query.

### 13.4. Restoring ACLs and Identities

Even after bytes copy cleanly, apps cannot read data if:
- Entra principal object IDs changed.
- Directory ACLs were not restored.
- Private Endpoints/DNS are missing.
- Managed identities/role assignments are absent.
- Filesystem/container paths or external table definitions shifted.
- Customer-managed keys are unreadable.

Recovery sign-off must test **real workload connectivity and permissions**, not just total byte counts.

## 14. Azure Files: Snapshots, Backups, and SMB/NFS

### 14.1. Azure Files Differs from Blob Usage Patterns

Azure Files provides file shares accessed via **SMB** or **NFS** depending on tier/configuration. VMs, AKS pods, and desktops can mount shares and write concurrently.

Common failure modes:
- User deletes a shared team directory.
- Ransomware encrypts files across a share.
- Entire share gets deleted.
- One app overwrites files while other users keep working.
- Mounts drop due to networking/identity faults.
- Region outage.

### 14.2. Share Snapshots

**Azure Files share snapshots** create point-in-time recovery points for a share where supported. You can restore individual files/directories or an entire share via supported tools/services.

Notes:
- Snapshots **reflect state only at the exact capture moment**.
- Snapshots are not automatically transaction-consistent across apps holding open file handles.
- Retention, snapshot limits, costs, and policies constrain protection.
- Not every protocol, tier, or share type shares identical snapshot/restore features.
- File locks, SMB ACLs/NFS permissions, and client mounts require post-restore checks.

### 14.3. Azure Backup for Azure Files

Azure Backup offers **snapshot-based** models and supported vaulted backup capabilities depending on share type, tier, region, and backup policy. Verify:
- Whether a Recovery Services vault or Backup vault is required for that mode.
- Share protocol SMB/NFS, Standard/Premium, and provisioning model.
- File-level vs. share-level restore support.
- Cross-region recovery availability and backup redundancy.
- Retention, soft delete, and immutability support.
- Storage account IAM, firewalls, and private networking.
- RTO when restoring millions of small files.

Never assume "Azure Files has Azure Backup enabled" means copies sit independently of the storage account in another region. **Snapshot backups** and **vaulted backups** have different failure domains and protection semantics.

### 14.4. Restoring a User-Deleted Folder

1. Stop further deletes/edits.
2. Identify the share/path and pre-fault timestamp.
3. Review available snapshot/backup recovery points.
4. Restore to an alternate path before overwriting the live folder.
5. Verify file counts, timestamps, ACLs, and owners.
6. Test read/write from a test client using the proper SMB/NFS identity.
7. Copy/merge into the live path under approval.
8. Check applications holding open file handles or client caches.
9. Resolve lock conflicts and handle changes made after the snapshot timestamp.
10. Save evidence, clean up the staging restore, and tune policies.

### 14.5. Azure Files Does Not Replace Database Backups

Never use an SMB share snapshot in place of point-in-time restore for SQL Server or PostgreSQL storing database files on a share unless your architecture/tooling explicitly supports and proves application-consistent quiescing. **Plain storage snapshots may only be crash-consistent** and do not guarantee database transaction consistency.

## 15. Azure Managed Disks and Virtual Machines

### 15.1. VM Backups, Disk Snapshots, and Azure Site Recovery Differ

| Mechanism | Purpose | Does not guarantee automatically |
|---|---|---|
| **Managed Disk snapshot** | Captures point-in-time disk state, including incremental snapshots where supported | Application-consistent multi-disk DB transactions |
| **Azure Backup for VMs** | Policy-based VM/disk backups and recovery points, with workload-consistency options per config | Recovery of external DBs, networks, or identities |
| **Azure Site Recovery (ASR)** | Replicates and orchestrates VM failover/failback per DR model | Independent clean backups against ransomware/deletion |
| **Golden image + IaC** | Fast rebuild of stateless VMs | Local persistent data and runtime secrets |
| **Native DB backup** | Restores transactions/logs/data per DB engine | OS, networking, or VM identity itself |

In cloud-native designs, prefer **stateless, rebuildable compute**; avoid keeping systems of record on OS disks when managed databases or protected storage fit better.

### 15.2. Crash-Consistent vs. Application-Consistent

- **Crash-consistent:** disk state resembling sudden power loss; databases rely on journal/WAL replay on startup.
- **Application-consistent:** coordinates quiescing/flushing app, filesystem, and DB writers before snapshotting per backup system capabilities.
- **Multi-disk consistency:** when DB data and logs span multiple disks, you need a single consistent restore point across all disks.
- **Transaction consistency:** follows DB engine semantics and app-aware backup settings; never assume every snapshot guarantees it.

For SQL Server on Azure VMs, use SQL workload-aware Azure Backup or native SQL backups to meet RPO/RTO. A VM-level restore may boot the OS while leaving the database inconsistent or missing log backups.

### 15.3. Azure Backup VM Restore

A practical runbook checks:
1. Recovery Services vault or Backup vault per backup type.
2. VM backup policy, job health, and newest recovery point.
3. OS/data disks, encryption, and key availability.
4. Whether an application-consistent recovery point is needed.
5. Full VM restore, disk restore, or file recovery per support.
6. Target VNet/subnet, NSG, IP/DNS, and load balancer registration.
7. VM extensions, managed identity, domain join, and monitoring agents.
8. SQL/database startup and consistency checks.
9. Data integrity and permissions.
10. Re-enrolling backups on the restored VM and cleaning up test resources.

**VM restore does not automatically restore Public IPs, DNS, private endpoints, and App Gateway backends to the exact topology** without runbooks or IaC.

### 15.4. ASR Does Not Replace Historical Data Backups

Azure Site Recovery handles VM/site/region outages, failover testing, and failback. It provides recovery points within limits, yet an ASR-only setup lacks protection against prolonged malware or silent corruption once replication copies the bad state. Combine independent backups, access isolation, PIM, and immutable retention as needed.

### 15.5. Filesystem Mounts and Off-VM Data

A VM application may touch:
- Managed disks for local state.
- Azure Files mounts.
- Blob Storage.
- Azure SQL Database.
- Key Vault.
- External SaaS APIs.

If you restore the VM to yesterday while the external database stays at today, check **app migrations, local queues, and reprocessing**. Never pick a VM recovery point expecting it to rewind external services.

## 16. AKS and Stateful Workload Data

### 16.1. Do Not Confuse Cluster State with Application Data

An AKS cluster comprises:
- Kubernetes API objects: Deployments, Services, ConfigMaps, ServiceAccounts, CRDs.
- Workload manifests in GitOps/IaC.
- PersistentVolumeClaims / PersistentVolumes.
- Azure Managed Disks or Azure Files volumes.
- External Azure SQL, Cosmos DB, Storage, Service Bus, Redis.
- Secrets/identities/certificates, NetworkPolicies, Ingress/Gateway.

**Never treat Kubernetes control-plane/etcd backups as backups for all databases or Blobs.** AKS uses a managed control plane, and workload recovery must account for both persistent volumes and external services.

### 16.2. Two Recovery Layers

~~~mermaid
flowchart LR
    GIT["IaC / GitOps manifests"] --> AKS["Rebuild AKS cluster"]
    BAK["PV snapshots / AKS backup supported"] --> VOL["Restore persistent volumes"]
    DB["SQL/Cosmos backups"] --> D["Restore external data stores"]
    KV["Key Vault/identity recovery"] --> ID["Restore secrets and access"]
    AKS --> READY["App readiness"]
    VOL --> READY
    D --> READY
    ID --> READY
~~~

The **control plane / workload config** layer and the **business data** layer have separate failure domains. A workload backed by managed databases can often just rebuild Pods/Services and reconnect to the separately restored or failed-over database.

### 16.3. Azure Backup for AKS

**Azure Backup for AKS** (depending on region, feature support, and extension/Backup vault) can protect supported Kubernetes resources and persistent volumes via policy. Never assume automatically that:
- Every storage driver/CSI volume is backed up.
- External Azure SQL/Cosmos DB is snapshotted together.
- Every CRD or cluster-scoped resource is included.
- Cross-region/cross-subscription restore works for all features.
- Volume snapshots are application-consistent for an in-Pod database.
- Externalized secrets reside inside Kubernetes backups.

Before adopting it, verify supported AKS versions, backup extension, CSI drivers, regions, Backup vault setup, RBAC, Azure Disk/Files limits, and recovery granularity.

### 16.4. PV/PVC Backups Alone Are Insufficient for Stateful Databases

Consider PostgreSQL running in an AKS StatefulSet:
1. Data and WAL may live on separate volumes.
2. Volume snapshots may occur mid-write.
3. Without quiescing or an app-consistent strategy, restores may need crash recovery or fail.
4. Helm chart/CRD operator versions can drift between backups.
5. PVC storage classes/topologies might not exist in the target region.
6. Database credentials and encryption keys may live outside the cluster.
7. Post-restore checks must still verify DB transactions, replication slots, and users.

For critical workloads, prefer managed database services or proven engine-aware backups like pgBackRest/WAL archiving rather than treating raw Kubernetes snapshots as a tested DB backup strategy.

### 16.5. Velero and Community Tools

Tools like Velero can back up Kubernetes resources and coordinate volume snapshots or file-level backups depending on plugins and storage backends. However:
- It is not a default Azure-managed backup service.
- You own operations, upgrades, plugins, credentials, and backup storage.
- Restore ordering of CRDs and controllers matters greatly.
- Source and target Kubernetes versions may differ.
- The backup bucket/storage account needs strict separation and deletion protection.
- It does not automatically back up external managed databases.

Strong AKS disaster recovery pairs **GitOps IaC + application-level backups + proper PV backups + identity/network recovery**.

### 16.6. Runbook for Rebuilding AKS After a Region Outage

1. Pick the target region and confirm node SKU capacity/quotas.
2. Provision VNet/subnets/private DNS/firewalls via IaC.
3. Provision the AKS cluster with matching identity/OIDC/Workload ID.
4. Restore ingress/gateways, NetworkPolicies, monitoring, and container registry auth.
5. Deploy CRDs/controllers/storage classes in dependency order.
6. Restore Kubernetes objects/PVs or sync via GitOps as appropriate.
7. Restore external databases/Blobs/file shares per their dedicated runbooks.
8. Map secrets, user-assigned managed identities, and RBAC.
9. Run readiness/smoke/business checks before traffic cutover.
10. Update Front Door/DNS/routes; monitor queues and data integrity.
11. Re-enable backup policies on the new cluster and services.
12. Record observed RPO/RTO against targets.

Never spin up all Pods before external databases and messaging recover; doing so triggers retry storms, duplicate messages, or cache stampedes.

## 17. Azure Service Bus, Event Hubs, and Azure Queue Storage

### 17.1. Message Brokers Are Not Database Backups

An **Azure Service Bus** queue/topic/subscription holds:
- Broker entity metadata and settings.
- Active message bodies.
- Scheduled messages.
- Dead-letter messages.
- Duplicate detection windows, sessions, locks, and transactions per tier.
- Producers/consumers and checkpoint/processing state.

A "backup namespace configuration" solution may preserve only **metadata**, not individual message bodies. Verify the exact **data-plane recovery** your business requires.

### 17.2. Service Bus Geo-Disaster Recovery vs. Data Geo-Replication

Under the classic **alias/metadata-pairing Geo-Disaster Recovery (Geo-DR)** model, the primary capability is recovering **namespace/entity metadata**—it **does not automatically replicate message data**. After failover, apps connect to the secondary namespace, yet queued messages sitting in the primary do not automatically appear there.

Service Bus also provides **Geo-Replication** capabilities varying by tier, region, and release that can include message data with specific behaviors and limits. Never equate the two features; before choosing, verify:
- What do Basic/Standard/Premium tiers support?
- Is the feature available for your region and namespace config?
- How are message bodies, sessions, and scheduled/DLQ messages replicated?
- What are sync/async lag and forced-failover RPO?
- Which clients, connection strings, or aliases must update?
- Is producer/consumer failback supported?
- What are the cost and capacity implications of running paired namespaces?

**A DR plan stating only "enable Service Bus Geo-DR" does not prove message RPO targets are met.**

### 17.3. Recovering Messages via Transactional Outbox

If Orders API writes an order to Azure SQL and sends a Service Bus message, use a **transactional outbox** inside the database:

~~~mermaid
flowchart LR
    API["Orders API"] --> TX["SQL transaction: Order + Outbox row"]
    TX --> PUBLISH["Outbox publisher"]
    PUBLISH --> SB["Service Bus"]
    SB --> WORKER["Idempotent worker"]
    WORKER --> DB["Invoice state"]
~~~

When Service Bus goes down:
- Order + Outbox rows still commit atomically inside SQL.
- The publisher can retry sending once Service Bus recovers.
- Duplicate deliveries can happen if an ACK is lost, so consumers must be idempotent.
- Outbox cleanup must never purge unsent events prematurely.
- If Orders DB is restored to an earlier timestamp, reconcile events already sent before the outage.

An outbox lets you replay business events, yet **does not turn Service Bus into an exactly-once delivery system**.

### 17.4. Event Hubs Differs from Service Bus

**Azure Event Hubs** is an event-streaming ingestion service with per-partition retention, consumer offsets/checkpoints, and replay within retention. Protect:
- Event retention window and throughput/capacity.
- Consumer checkpoints (typically stored in Azure Blob Storage per SDK).
- Event schemas, partition keys, and producer IDs.
- **Event Hubs Capture** when enabled: archives events to Azure Blob Storage/ADLS per policy and constraints.
- Azure Storage backups/immutability on archives for long retention.
- Cross-region DR/geo-replication per tier/capability.
- Replay tooling and idempotent consumers.

If retention is 7 days and a fault is discovered 30 days later, you cannot replay directly from Event Hubs once events expire without Capture/archives. **A checkpoint records processing position, not a backup of event payloads.**

### 17.5. Event Hubs Capture and Archive Replay

A recovery plan:
1. Enable Capture if business needs archiving longer than stream retention where supported.
2. Store archives in Storage with suitable redundancy/backups/immutability.
3. Track schema versions and retention windows.
4. When a downstream DB corrupts, find the last-good checkpoint.
5. Rebuild stores/counters from captured events idempotently.
6. Account for per-partition ordering, duplicates, and event-time vs. processing-time.
7. Persist durable replay progress markers.
8. Cross-check totals/checksums and billing records.
9. Switch serving pointers only after validation.
10. Retain source archives per compliance.

### 17.6. Azure Queue Storage

Azure Queue Storage is not an infinite transaction log:
- Messages carry TTL/visibility semantics.
- Consumers normally delete messages after processing.
- Deleted or expired messages usually cannot be replayed directly.
- Storage geo-redundancy does not restore an erroneously processed message.
- Persist business intent in a database/outbox or durable event archive.
- If DLQs, topics, or richer transactions are needed, evaluate Service Bus.

### 17.7. What Does RPO Mean for Messaging?

Business messaging RPO can be defined as:

~~~text
An accepted order must never lose
the intent to generate an invoice when the broker is unavailable.

Business source of truth = Orders + Outbox
Recovery requirement:
  No accepted order without recoverable invoice command
  (retries/duplicates allowed; lost intent forbidden).
~~~

This effectively achieves **zero lost business intent** even if ephemeral broker state is lost, provided DB/outbox recovery meets RPO, publishers/workers behave properly, and reconciliation is verified. Never assign RPO=0 to Service Bus merely because a topic exists.

## 18. Caching: Azure Managed Redis and Redis Deployments

### 18.1. Caches Should Hold Derived Data

Example: caching recent shopping carts:
- If cached values can be rebuilt from Azure SQL/Cosmos DB and hold no exclusive writes, losing the cache does not lose business data.
- On cache failover, apps can read from source and warm the cache.
- Guard against **cache stampede**: thousands of requests hitting the DB simultaneously when the cache is cold.
- TTLs, warming strategies, circuit breakers, and read-only fallbacks affect RTO.

Even though Azure Managed Redis or Azure Cache for Redis offers various HA/persistence/replication features by SKU/lifecycle, **never assume a cache is a durable system of record**.

### 18.2. When a Cache Is Actually the System of Record

If an app stores shopping carts **only** in Redis, losing the cache means losing data. You must then:
1. Set RPO/RTO quite differently from standard ephemeral caches.
2. Evaluate persistence (RDB/AOF), backup/export, and geo features for your exact service/tier.
3. Check snapshot frequency and failure domains.
4. Test restores and failover, especially session/auth consistency.
5. Or move carts to Cosmos DB/SQL as the system of record and keep Redis strictly for derived data.

Never conclude "Redis never needs backups": it depends on how the business uses it.

### 18.3. Cache Recovery Runbook

1. Determine whether the fault is network/auth or lost cache data.
2. Verify the system-of-record database is healthy.
3. Apply rate/concurrency limits so DB traffic does not overwhelm primary storage.
4. Enable fallbacks, TTL adjustments, and cache-warming policies.
5. Monitor cache hit ratios, DB CPU/RUs, and p95 latency.
6. Rebuild cache keys/patterns via approved paths.
7. Verify cache invalidation still works on updates.
8. If caching sensitive user data, protect keys/values and logs.
9. Disable emergency bypass modes after recovery.
10. Record observed RTO and any DB cost spikes.

## 19. Key Vault, Identities, and App Configuration in DR

### 19.1. Without Keys, Backups Can Be Useless

A database or file archive encrypted with a Key Vault CMK may remain intact yet fail to restore if:
- The key was purged.
- Key Vault is unreachable in the DR region.
- The restore identity lacks unwrap/decrypt permissions.
- Private Endpoints/DNS are misconfigured.
- A rotated key version was discarded.
- Tenant/subscription IAM changed.
- HSM migration/backups do not meet requirements.

**Key Vault must sit inside your recovery dependency graph**, not as an afterthought.

### 19.2. Key Vault Soft Delete and Purge Protection

With Key Vault, **soft delete** and **purge protection** prevent premature loss of keys, secrets, certificates, or vaults within retention/capability rules. Key notes:
- Soft delete protects against accidental deletes during retention.
- Purge protection blocks purging before retention expires per service rules.
- Never "back up" secret values by exporting plaintext into Git.
- Key Vault backup/restore operations have object, region/tenant, and resource constraints; verify supported backup models.
- Rotating secrets creates versions; restoring an old version does not reactivate passwords/tokens already revoked downstream.
- Vault-level restores do not automatically rebuild all RBAC, networking, Private DNS, or managed identities without IaC.

### 19.3. Separating Recovery Roles

| Principal | Responsibility | Minimum permissions |
|---|---|---|
| Runtime identity | Read secrets or run required crypto operations | Scoped data-plane role |
| Backup operator | View jobs and pick recovery points | Scoped backup permissions |
| Restore operator | Provision isolated restored resources | Restore permissions |
| Key admin | Manage key lifecycles/purge policies | Key management via PIM |
| Identity admin | Restore roles/federation/principal configs | Entra/Azure RBAC governance |
| Audit viewer | Review evidence | Read-only logs per policy |

Never grant long-lived subscription `Owner` to an app just so it can manage its own DR. Use MFA/PIM, dual control, and auditing for emergency incident access.

### 19.4. Azure App Configuration Is Operational Data Too

App Configuration stores key-values, feature flags, and labels, offering snapshots, revisions, and soft delete depending on tier/feature support. Critical configs can also be versioned/exported via IaC and source control.

If feature flags are lost or altered accidentally:
- Business code paths can change immediately.
- App refresh caches mean instances do not see updates simultaneously.
- Restoring an App Configuration value does not roll back binaries or databases.
- Multi-region App Configuration replicas/geo-replication have distinct semantics from backups.
- Connection/security settings must be verified in the target region.

Manage important key-values via **configuration-as-code and release audits**, keeping secrets in Key Vault. Every emergency flag change needs an owner and timestamp.

### 19.5. IaC Backs Up the Control Plane, Not the Data Plane

Bicep/Terraform/GitOps can rebuild:
- VNets/subnets/Private DNS/NSGs.
- Azure resources, SKUs, and network rules.
- RBAC role assignments when principal IDs remain valid.
- App Service/AKS/Container Apps configs.
- Alert rules and diagnostic settings.
- Storage/DB configs and backup policies.
- Front Door/Traffic Manager routes.

They **do not restore Orders rows, Blob contents, or Service Bus message bodies**. Conversely, database backups cannot restore IaC if your Git repo is lost. Protect Git repositories, artifacts, state backends, key material, and backups together.

## 20. Data Factory, Synapse, Databricks, and Analytics Platforms

### 20.1. Analytics Data Has Multiple Layers

An analytics platform typically includes:
- Azure Data Factory or Synapse pipelines.
- Azure Data Lake Storage Gen2 raw/bronze/silver/gold layers.
- Azure Databricks notebooks/jobs/Delta tables/Unity Catalog.
- Azure Synapse Analytics SQL pools / lake databases.
- Event Hubs / Event Hubs Capture and stream checkpoints.
- Azure SQL / Cosmos DB as operational sources.
- BI semantic models/dashboards.
- Git repos, workspace definitions, secret scopes, identities, and networking.

If a Gold aggregate is lost, you can rebuild from Bronze/Silver. If raw event archives are lost after upstream retention expires, **the source data is gone for good**.

### 20.2. Distinguishing Data Recovery from Pipeline Recovery

| Object | Primary mechanism | Post-restore risks |
|---|---|---|
| Raw data in ADLS | Versioning/soft delete/backup/immutable archive per feature | Source event gaps, ACLs/paths |
| Delta table | Transaction log/time travel + underlying object protection | `VACUUM`/log retention, corruption |
| Databricks notebooks/jobs | Git/CI/CD, workspace export/IaC | Mismatched runtime/libraries/compute config |
| Unity Catalog metastore/permissions | Service-supported backup/DR policies, IaC, catalog exports | External location/credential/owner mismatches |
| Data Factory pipelines/triggers | Git integration, ARM/Bicep, deployed artifacts | Wrongly enabled/disabled triggers, linked-service secrets |
| Synapse dedicated SQL pool | Built-in restore points/backups per capability | Restore duration and DB objects/security |
| Synapse serverless SQL | Code-defined views/external tables; data lives in Storage | Query logic alone is useless if Storage is lost |
| Streaming checkpoints | Checkpoint blobs/files and source retention | Stale offsets can replay duplicates or expire |
| Gold reports | Recompute from source + versioned logic | Can take hours and incur compute cost |

Never treat a single ADLS snapshot as sufficient to restore an entire Synapse/Databricks workspace and its permission model.

### 20.3. Reprocessing Must Preserve Logic and Time Semantics

When rebuilding a report:
1. Pin the exact source dataset/version.
2. Pin pipeline/SQL/notebook code versions.
3. Preserve time zones, watermarks, and event-time vs. processing-time semantics.
4. Rebuild into a **new table/path** so live serving reports stay intact.
5. Check schema evolution, deduplication, and late-arriving events.
6. Reconcile record counts and business aggregates against control totals.
7. Account for consistency with still-arriving operational writes.
8. Switch catalog/serving pointers only after validation.
9. Record lineage, commit hashes, data versions, and UTC timestamps.
10. Clean up temp artifacts per retention without deleting source archives.

### 20.4. Delta Time Travel Example

Illustrative syntax in a supported Delta Lake environment:

~~~sql
-- Read an earlier version to investigate; do not mutate the production table.
SELECT *
FROM orders_gold VERSION AS OF 145;
~~~

Reading version 145 depends on retaining the Delta transaction log and underlying data files. Before running `RESTORE TABLE` or overwrites, review carefully because those write operations mutate current state and impact downstream consumers. Never run them on production data without approval.

### 20.5. Derived Data Can Accept Longer RTOs

If Gold reports refresh daily, a 12-hour rebuild may be acceptable, while Orders API needs under 1 hour. Use **business impact** to prioritize capacity. Never pay for cross-region hot replicas on every aggregate table if overnight batch reporting suffices.

## 21. Consistency Across Multi-Service Recovery

### 21.1. One Business Transaction Spans Multiple Stores

Checkout example:
1. Orders API writes an order to Azure SQL.
2. Updates Cart state in Cosmos DB.
3. Sends `InvoiceRequested` via Service Bus.
4. Worker writes a PDF to Blob.
5. Calls external payment partner.
6. Sends confirmation email.

If SQL restores via PITR to 09:55, Cosmos to 10:00, Blob to 09:50, and Service Bus starts with an empty namespace, **there is no single "whole-system 09:55" snapshot**. Separate services do not share one distributed transaction across all steps.

### 21.2. Skewed Recovery Points Diagram

~~~mermaid
flowchart TD
    T["Incident 10:00"] --> SQL["SQL Orders restore 09:55"]
    T --> COS["Cosmos Cart restore 09:58"]
    T --> BL["Blob invoice version 09:50"]
    T --> SB["Service Bus metadata restored, messages unknown"]
    SQL --> REC["Reconciliation engine"]
    COS --> REC
    BL --> REC
    SB --> REC
    REC --> VALID["Business invariants + audit"]
~~~

Never pick the same portal timestamp across services and assume consistency: snapshot cadence, replication lag, and event pipelines differ.

### 21.3. Define the System of Record per Entity

For example:
- **Orders SQL** is the source of truth for accepted order status.
- **Payment provider** is the source of truth for captured payments.
- **Outbox row** is the source of truth for event-emission intent.
- **Invoice Blob** is a derived record artifact, regenerable if source data exists.
- **Cart Cosmos** reflects pre-checkout state, disposable after order completion.

During restore:
- Never "re-charge" customers just because SQL PITR lacks payment records.
- Query the payment gateway by stable payment transaction ID under approval.
- If a valid order lacks an invoice, run an idempotent **compensating invoice generation job**.
- If an invoice exists without an order, reconcile before deleting anything.

### 21.4. Business Invariants

Recovery must satisfy invariants such as:
- Each `orderId` maps to at most one logical accepted order.
- The same payment intent is never captured twice.
- Every captured order either has or is queued for an invoice.
- Invoices match order amounts, currencies, and tax rules.
- Message replay produces zero duplicate side effects.
- Inventory reservations never go negative or leak indefinitely.
- Each tenant sees only its own data.
- Financial totals reconcile against external ledgers.

**Row counts and HTTP 200 are never enough** to declare recovery successful.

### 21.5. Using Event Sourcing / Outbox Within Proper Scope

A durable event log with schema versions, correlation IDs, and idempotent processors enables:
- Rebuilding read models.
- Replaying operations missed after restore.
- Recomputing counters.
- Detecting cross-system drift.

However, reliable replay requires:
- Retaining event logs long enough.
- Prohibiting out-of-policy history edits/deletes.
- Deterministic handlers or persisted external reference versions.
- Avoiding replaying side effects (payment captures/emails) without idempotency/compensation.
- Replay checkpoints and pause/resume controls.
- Throughput capacity to finish within RTO.

### 21.6. Reconciliation Checklist

~~~text
Reconciliation ID:
Incident start / detection UTC:
Source of truth per business entity:
Recovery point and restore target per service:
Known potentially lost writes:
Known duplicated messages/side effects:
Order-to-payment matches:
Order-to-invoice matches:
Inventory reservation checks:
Message/event checkpoint:
Failed/missing/duplicate record count:
Operator/DBA/business approval:
Final RPO/RTO/RLO measured:
~~~

Never include payment card numbers, tokens, secrets, or raw PII in public reports. Use record IDs and classification-based access controls.

## 22. Ordering Recovery via the Dependency Graph

### 22.1. Never Recover in Arbitrary Order

Multi-service recovery needs a sequence:

~~~mermaid
flowchart TD
    A["Incident declaration / freeze writes"] --> B["Identity, keys, subscription access"]
    B --> C["Network, DNS, private endpoints"]
    C --> D["Data restoration / region failover"]
    D --> E["Messaging / outbox / replay checkpoint"]
    E --> F["Compute/IaC apps in recovery environment"]
    F --> G["App integration and consistency tests"]
    G --> H["Traffic cutover / canary"]
    H --> I["Monitor, reconcile, close incident"]
~~~

This order is a **reference template**; in some regional outages you must stand up compute first to run recovery tools, or restore backup storage and networking in parallel. What matters is defining dependencies explicitly so parallel steps never break consistency.

### 22.2. Phase 0: Declare and Contain the Incident

1. Assess incident severity, affected services, regions, and tenants.
2. Stop faulty writers/jobs or enforce a change freeze.
3. Block unnecessary deletes, purges, and key rotations.
4. Preserve logs, access records, and backup metadata.
5. Mobilize comms, on-call, business owners, and emergency approvals.
6. Separate network/identity/availability outages from actual data loss.
7. Capture current snapshots/recovery points if beneficial and safe.
8. Confirm target RPO/RTO and acceptable data-loss thresholds.
9. Choose the recovery region, subscription, and isolation boundary.
10. Never execute destructive actions before understanding the plan.

### 22.3. Phase 1: Restore Minimum Permissions and Foundation

- Entra tenant/principals, managed identities, and RBAC.
- Key Vault CMKs/secrets, access policies, and purge protection.
- VNets, routing, NSGs, Azure Firewall, Private DNS, and endpoints.
- Backup operator identities and restore permissions.
- Artifact / container registry access.
- Target capacity/quotas per service.
- Log Analytics/Monitoring and the evidence trail.

If primary tenant/identities are suspected compromised, never reuse potentially exposed service principals or tokens to build the recovery environment.

### 22.4. Phase 2: Restore Systems of Record

Suggested priority:
1. SQL / primary databases.
2. Irreplaceable Blob/Files records.
3. Cosmos / operational datasets.
4. Message/outbox archives and checkpoint state.
5. Required configs/artifacts.
6. Derived stores, caches, and reports last.

Depending on the business, Blob might be the system of record while SQL only indexes metadata; let your actual data matrix dictate order.

### 22.5. Phase 3: Reopen the Application Under Control

- Start APIs in read-only/quiesced mode if reconciliation is needed.
- Keep background consumers paused until checkpoints are validated.
- Enable a limited canary cohort and verify transaction correctness.
- Run smoke/integration tests without unintended external side effects.
- Measure latency, 5xx rates, auth, and quotas.
- Gradually enable writes and idempotent workers.
- Watch backlogs, DLQs, invoices, and payment reconciliation.
- Update DNS/Front Door/global routing only per approved plan.
- Re-enable backup policies and monitoring on the new target.
- Inform business stakeholders which RLO level has been restored.

### 22.6. Phase 4: Failback and Cleanup

Once the primary region or main service is repaired:
- Treat the DR region as the active source of truth.
- Never allow the old primary to accept writes automatically.
- Plan reverse replication / cutback per service capabilities.
- Reconcile records, offsets, and writes created during DR.
- Switch traffic per runbook and fence old writers.
- Re-enable monitoring, backups, and IAM on the steady-state region.
- Clean up test resources with approval while keeping backups/evidence per retention.
- Update IaC/configs and the drill report.

**Failback is never simply flipping a CNAME back** when two regions have diverged.

## 23. DR Architectural Patterns by RPO/RTO

### 23.1. Backup-and-Restore

~~~text
Primary service
   → scheduled backup/restore points
   → independent protected retention
   → restore into new resource on incident
   → validate + route app
~~~

Best fit:
- Workloads not needing single-digit-minute RTO.
- Tight budgets.
- Acceptable recovery measured in tens of minutes or hours.
- Data loss aligned with backup policy cadence.

Risks: long restore times and dependencies on networking, identities, and keys.

### 23.2. Pilot Light / Warm Standby

~~~text
Primary region: full production
DR region: IaC, network, keys, some DB copies,
           minimal compute and standby configs
On incident: scale and route
~~~

Fits workloads needing shorter RTO than cold restores without paying for 100% dual capacity. Verify:
- Live DR database replicas or geo-backups.
- ACR image availability and quotas.
- DNS/Front Door failover.
- Managed identity / Key Vault access.
- Server warm-up and caches.
- Async replication RPO.

### 23.3. Active-Passive Regional Design

- Primary handles writes.
- Secondary runs hot or warm with networking and compute ready.
- Database uses geo-replicas or supported DR features.
- Automatic or manual failover aligned with app/DB semantics.
- Guard against stale writes and split-brain.
- Pair with independent PITR/backups against corruption.

### 23.4. Active-Active

Two or more regions serve requests simultaneously, potentially both writing. Safe operation requires:
- A data service supporting multi-region writes and matching consistency.
- Conflict resolution and business-level idempotency.
- Session/tenant routing.
- Managed replication lag and read consistency.
- Cross-region compatible schema rollouts.
- Distributed tracing and observability.
- Independent backups against logical faults/compromise.
- Handling divergent updates during network partitions.

**Active-active raises data complexity sharply**; never choose it chasing zero RTO without mastering consistency and conflict semantics.

### 23.5. RPO/RTO Trade-Off Matrix

| Architecture | Achievable RPO | Achievable RTO | Cost / complexity |
|---|---|---|---|
| Scheduled local backups | Tied to backup interval | Long recovery from scratch | Low–medium |
| Geo-backup restore | Tied to backup/geo availability | Usually longer than hot standby | Medium |
| Warm standby + geo-replica | Tied to replication lag | Shorter than cold restore | Medium–high |
| Active-passive hot | Tied to DB failover semantics | Can be short; must be tested | High |
| Active-active multi-write | Tied to consistency/conflicts | Can be very short for some faults | Very high |
| Event replay/rebuild | Tied to durable event retention | Tied to volume and compute throughput | Depends on data volume |

This is a **relative comparison**, not an Azure SLA or feature promise. Measure against your exact service SKU, volume, and regions.

## 24. Ransomware, Malicious Deletion, and Protecting Recovery Copies

### 24.1. Assume-Breach Mindset

If an attacker compromises an app account or subscription:
- They can delete/overwrite primary data.
- They may attempt to shorten backup retention.
- They can purge Blob versions if permissions are broad.
- They can tamper with build pipelines, IaC, and container images.
- They can rotate/purge encryption keys to block decryption.
- They can wipe unprotected logs/audit trails.

Accidental-delete features alone are inadequate if the same principal can wipe recovery copies too.

### 24.2. Defensive Layers

1. Least-privilege data-plane roles for apps; avoid blanket delete/purge/admin rights.
2. Separate backup/restore operators from runtime identities.
3. Enforce MFA, PIM, conditional access, and break-glass governance.
4. Use immutable/isolated copies where supported by the service.
5. Enable soft delete and purge protection on Key Vault, Backup vaults, and Storage where supported.
6. Maintain cross-region/cross-account copies when business risk demands it.
7. Protect encryption key lifecycles/availability for recovery.
8. Audit backup policies and alert on retention drops or disabled backups.
9. Enforce secret scanning, SBOMs, and CI security to block supply-chain compromise.
10. Rehearse clean-room recovery without reusing potentially compromised credentials.

### 24.3. "Available Backup" Does Not Guarantee "Clean"

If corruption started three weeks ago, yesterday's backup still holds poisoned records. You must:
- Find the **first known bad change**.
- Pick a recovery point prior to that timestamp within retention.
- Cross-check logs and event sources to separate bad writes from good writes.
- Scan/sandbox restored data if malware or malicious files are a risk.
- Never expose a recovery DB to production networks before validation.
- Preserve evidence per incident/forensics policies.

### 24.4. Security During Recovery Workflows

A restored production database containing PII must never open automatically to every developer in a test region. Recovery targets require:
- Network isolation.
- Least-privilege access.
- Encryption at rest and in transit.
- Proper logging and redaction.
- Approved retention and cleanup.
- Audited key access.
- Zero raw customer records pasted into tickets.
- Synthetic data only in public demos.

### 24.5. Business Recovery vs. Cyber Recovery

Business DR prioritizes restoring availability during a regional outage. Cyber recovery may require:
- Isolating compromised accounts and tokens.
- Re-verifying image and automation provenance.
- Selecting clean backups predating infection.
- Rotating credentials and keys per security incident policy.
- Forensic investigation.
- Accepting longer RTO to preserve integrity and containment.

**Failing over immediately to a corrupted replica can prolong the incident** rather than fixing it.

## 25. Backup Policies, IaC, and Recovery Evidence

### 25.1. A Policy Is More Than Retention Days

A policy specification might look like:

~~~yaml
# Internal policy document example, NOT an Azure Backup CLI manifest.
dataClass: orders-critical
owner: orders-platform-team
systemOfRecord: azure-sql-database

objectives:
  rpo: "PT5M"
  rto: "PT1H"
  rlo: "accept-and-read-orders"

protection:
  type: "managed-pitr-plus-geo-strategy"
  shortTermRetention: "review per supported tier"
  longTermRetention: "business/compliance approved"
  geoRecovery: "verify enabled and test actual restore"
  immutableCopy: "evaluate where supported"

operations:
  backupSuccessAlert: true
  restoreDrillCadence: quarterly
  restoreTarget: isolated-recovery-environment
  dataIntegrityOwner: orders-business-owner
  securityApprovalRequired: true
~~~

This is an **illustrative organization-defined schema**, not an Azure ARM/Bicep/Terraform resource you can apply directly. Values capture policy intent; translate them into exact service configurations and IaC modules.

### 25.2. Separating Backup Policies from Application Permissions

- App identities may need to read/write Orders, never alter backup retention.
- Backup policy owners govern retention and schedules.
- Restore operators have permissions to restore into isolated targets.
- Security owners audit immutability, purge protection, and anomalous access.
- Auditors review reports/traces without reading secret values.
- Cost owners review long retention, storage redundancy, and duplicate backups.

Inspect exact Azure built-in roles and actions per resource/vault. Never grant subscription `Owner` to automation just to manage recovery points.

### 25.3. Infrastructure as Code for DR

A solid IaC module defines:
- Primary/secondary regions and resource naming.
- Storage redundancy and backup policies where supported.
- Target recovery VNet/Private DNS/endpoint topology.
- Managed identities and RBAC.
- Key Vault/CMK protections and retention.
- Monitoring alerts and diagnostic settings.
- App deployments, ACR images, and Front Door routing.
- Data resource SKUs, quotas, and capacity.
- Recovery environment tags, budgets, and lifecycle rules.

**Never store plaintext backup decryption keys, SQL passwords, or Storage account keys in IaC source.** Terraform state can hold secrets even when source files do not; secure state backends and access permissions.

### 25.4. Sources of Truth for Protection Posture

| Source | What it verifies | Limitation |
|---|---|---|
| ARM/CLI configuration | Retention, redundancy, IAM, resource state | Good config does not prove jobs succeed |
| Azure Backup jobs / Backup Center | Job pass/fail and recovery points | Restore usability remains untested |
| Azure Monitor Logs/Metrics | Alerts for backup gaps and error trends | Ingestion/retention can fail |
| Application audit/outbox | Committed business operations | Usually not a full data archive |
| Test restore report | Actual RPO/RTO and validation | One drill does not cover every failure mode |
| IaC/Git version | Rebuilding the control plane | Contains no data-plane records |

### 25.5. Backup Policy Drift

Suppose a new DB deployed by a pipeline uses weaker backup redundancy than standard. The resource runs smoothly for months until a regional outage exposes the gap.

Prevent drift with:
1. Policy-as-code for SKUs, redundancy, and retention.
2. Azure Policy where aliases/effects cover target properties.
3. Post-deployment readback verification.
4. Periodic resource inventories.
5. Alerts when backups are disabled or retention shortened.
6. Auditing config-change permissions.
7. Blocking production deployment of critical datasets lacking DR setup.
8. Running restore drills after major changes.
9. Documenting exceptions with owners and expiration dates.
10. Updating runbooks and cost forecasts.

Never treat an Azure Policy "compliant" badge as 100% proof of recoverability: Azure Policy mainly checks configuration properties, not end-to-end business recovery.

## 26. Monitoring Backups and Recovery on Azure

### 26.1. Signals to Track

| Signal | Operational question |
|---|---|
| Last successful backup | When did the latest backup succeed? |
| Earliest/latest restorable timestamp | What time range is actually recoverable? |
| Retention remaining | Do pre-incident recovery points still exist? |
| Geo-replication lag | How much data might the secondary lack? |
| Backup/restore job failures | Are policies or copies failing? |
| Restore duration | What RTO is measured at current data size? |
| Recovery point integrity | Are restored databases/files actually usable? |
| Secret/key availability | Can backups still be decrypted/unwrapped? |
| DR resource readiness | Are quotas, DNS, VNets, and identities ready? |
| Outbox/queue backlog | Is business intent waiting to replay? |
| Data reconciliation failures | Are records missing or duplicated post-restore? |
| IAM/policy changes | Did anyone lower retention or disable backups? |
| Monthly backup/storage spend | Is protection aligned with budget? |
| Restore drill cadence | When was the last drill and when is the next due? |

### 26.2. Backup Center and Azure Monitor

Azure Backup Center / Azure Business Continuity Center or corresponding Azure Backup/Monitor experiences can surface jobs, policies, protected instances, and compliance per current support.

Not every managed service (Cosmos DB/SQL/Postgres/Blob) emits backup jobs into a **Recovery Services vault**. For example:
- Azure SQL Database automated PITR differs from Azure Backup VM jobs.
- Azure Backup for Blobs uses Backup vault / Storage protection mechanisms.
- Cosmos DB continuous backup is an account-level service policy.
- Service Bus Geo-DR is not a scheduled backup job.
- Event Hubs Capture is a data archiving pipeline.

Therefore, unified dashboards must query **each service's proper telemetry source**, never using Azure Backup job counts as the total count of protected datasets.

### 26.3. KQL Query for Sensitive ARM Changes

If the subscription exports Azure Activity Logs to Log Analytics and `AzureActivity` is populated:

~~~kusto
AzureActivity
| where TimeGenerated > ago(24h)
| where OperationNameValue has_any (
    "delete", "write", "purge", "backup", "failover"
)
| project TimeGenerated, ResourceGroup,
    ResourceProviderValue, ResourceId,
    Caller, OperationNameValue, ActivityStatusValue
| order by TimeGenerated desc
~~~

This query is a **broad investigative filter**. `OperationNameValue` includes legitimate writes; Activity Logs primarily capture management-plane operations and do not replace Key Vault/Storage data-plane diagnostics. Tune per resource provider and action to avoid alert fatigue. If logs are not exported to the workspace, empty results do not prove nothing happened.

### 26.4. Alerting on Backup Gaps

Example for Orders RPO target = 15 minutes:
- Monitor **latest restorable point**, not just job counts.
- Alert when age relative to current UTC exceeds the threshold minus a safety buffer.
- Distinguish transient backup lag from prolonged failures.
- Assign on-call owners and escalation paths.
- Surface recovery objectives on dashboards.
- Keep system clocks/time zones and UTC timestamps accurate.
- When alerted, verify recovery points in tools/portals rather than trusting stale metadata caches.

Never promise alerts catch every corrupted backup; pair alerts with restore drills and integrity checks.

### 26.5. Tracking Real RTO from Drills

A lab timeline:

~~~text
09:00  Incident declared
09:10  Scope + root cause isolated
09:20  Recovery point approved
09:45  Restored resource created
10:05  Data validation finished
10:15  App canary passing
10:25  Traffic fully served

Observed RTO: 85 minutes, from 09:00 to 10:25
~~~

Against a 60-minute target RTO, this drill **FAILS on RTO**, even though the restore job finished at 09:45. Document concrete fixes: warm standby, index optimization, shrinking backup size, pre-provisioning networks, automating tests, or revisiting the objective.

### 26.6. Auditing Restoration Operations

Every restore job should retain:
- Incident/ticket ID and approvals.
- Source/target resource IDs, owner, and region.
- Backup policy and UTC recovery-point timestamp.
- Restore job ID and start/end timestamps.
- Executing principal, role, and emergency access used.
- Data validation results and row/file checksums.
- Measured RPO/RTO.
- Business reconciliation outcomes and exceptions.
- Decision to clean up or retain the target.
- RBAC-protected evidence links.

Never record secret values, database passwords, or user payment details in work items.

## 27. Cost and Optimizing Data Recovery Budgets

### 27.1. Cost Components

~~~text
Total data recovery architecture cost =
    Backup storage and transactions
  + Long-term retention capacity
  + Geo-redundant storage/replication
  + Warm standby or cross-region compute
  + Recovery Services/Backup vault service fees where applicable
  + Encryption key management
  + Logging/diagnostic ingestion and retention
  + Network/egress/cross-region data transfer
  + Restore drill compute/storage/requests
  + Automation, monitoring, and incident operations
~~~

Real pricing varies by region, SKU, redundancy, retention, data size, churn rate, and Azure billing terms. Use the Azure Pricing Calculator, Azure Cost Management, and current service pricing—never copy illustrative figures from a lesson into a real budget.

### 27.2. High Data Churn Drives Up Backup Storage

Suppose a 5 TiB Blob source has heavy versioning; 30-day retention does not simply equal **5 TiB × 30** because Storage uses snapshot/copy-on-write mechanics, churn rates, block granularity, and varying tiers/billing. Conversely, versioned storage can grow sharply when apps overwrite large objects hourly.

Measure:
- Total protected capacity.
- Daily churn rate and full vs. incremental backup mechanics.
- Number of versions/snapshots.
- Geo-redundancy factor and egress.
- Backup frequency.
- Temporary restore target storage cost.
- Compression/deduplication where supported.
- Lifecycle rules without violating compliance retention.

### 27.3. Hot Standby vs. Cold Restore

| Criterion | Cold restore | Warm/hot standby |
|---|---|---|
| Always-on compute | Little or none | Ongoing standby cost |
| Typical RTO | Longer | Can be shorter |
| RPO | Backup cadence / geo-backup | Replication lag / consistency |
| Complexity | Restore workflow | Replication/failover/failback |
| Best fit | Reports, low churn, long RTO | Orders/payments, short RTO |
| Logical fault protection | Yes, if backed up pre-fault | Still needs separate PITR backups |
| Testing | Restore drill | Failover + restore drill |

Do not buy active-active just to protect a low-priority guide document; conversely, do not rely on nightly backups for a 5-minute-RPO financial ledger without a recoverable event log.

### 27.4. Optimizing by Data Tiers

- **Tier 0:** financial / system-of-record; PITR/geo, guarded backups, frequent drills.
- **Tier 1:** critical operational state; fast backup/restore, tailored retention.
- **Tier 2:** business documents; versioning, soft delete, immutable retention per policy.
- **Tier 3:** derived analytics; prioritize source archives and rebuilds.
- **Tier 4:** ephemeral caches/temp data; rebuild, potentially no backup.

These tiers are **illustrative governance classes** tied to real business RPO/RTO/RLO—not Azure SKU tier names.

### 27.5. Budget for Testing—Never Skip It

A cheap DR plan on paper that has never been restore-tested carries extreme risk. Budget for:
- Restoring lab target resources.
- Running integrity queries.
- Standby region quotas and compute.
- VNet / Private DNS connectivity.
- Replaying event archives.
- Verifying Key Vault / CMK access.
- Post-failover load testing.
- Controlled cleanup.

A quarterly drill catches backup gaps or missing keys early—before a real outage exposes them.

## 28. Lab A: Restoring SQL and Blob in an Isolated Environment

### 28.1. Purpose

An order needs recovery from SQL PITR and an overwritten invoice PDF needs recovery from a Blob version/snapshot. The lab proves:
- Pre-incident backups/recovery points existed.
- Restores do not overwrite source data.
- Data is read and validated.
- Business state reconciles across both services.
- RPO/RTO are measured.
- Cleanup runs only after owner approval.

### 28.2. Safety Preconditions

- **Dedicated lab** subscription/resource group with budget and retention bounds.
- A lab Azure SQL Database containing synthetic sample Orders.
- A lab Blob Storage account with supported protection features enabled before creating test data.
- Least-privilege Azure CLI / JDK / SQL client.
- Zero connections to production payments, email, or APIs.
- Working lab Key Vault/CMK/Private DNS.
- A recovery timestamp within retention.
- Restore target names distinct from source DB/Blob names.

### 28.3. Step 1: Read Config and Capture UTC Timestamps

~~~bash
RG="rg-recovery-lab"
SQL_SERVER="sql-recovery-lab"
SOURCE_DB="orders_lab"
STORAGE="strecoverylab"

az account show --query "{subscription:id,tenant:tenantId}" -o json

az sql db show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SOURCE_DB" \
  --query "{name:name,status:status}" \
  -o json

az sql db str-policy show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SOURCE_DB" \
  -o json

az storage account blob-service-properties show \
  --resource-group "$RG" \
  --account-name "$STORAGE" \
  --query "{versioning:isVersioningEnabled,blobDelete:deleteRetentionPolicy,containerDelete:containerDeleteRetentionPolicy}" \
  -o json
~~~

Never run create/delete/restore commands against resources outside the approved lab.

### 28.4. Step 2: Simulate a Fault

In the lab:
1. Insert a few synthetic Order records.
2. Upload a synthetic invoice PDF.
3. Record the UTC timestamp before injecting the fault.
4. Delete one synthetic Order in the lab DB or overwrite a synthetic Blob.
5. Record the fault UTC timestamp.
6. Confirm zero real users, privacy exposure, or hidden dependencies.

Never inject fake corruption in production just to test backups.

### 28.5. Step 3: SQL PITR to a New Database

~~~bash
RESTORED_DB="orders_lab_restore_exercise"
RESTORE_TIME="2026-11-20T09:30:00Z"  # Replace with valid lab UTC time

# Creates a new billable database. Run only in approved lab.
az sql db restore \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$SOURCE_DB" \
  --dest-name "$RESTORED_DB" \
  --time "$RESTORE_TIME"

az sql db show \
  --resource-group "$RG" \
  --server "$SQL_SERVER" \
  --name "$RESTORED_DB" \
  --query "{name:name,status:status}" \
  -o json
~~~

This command does not touch the source DB. Wait for provisioning/restore to finish, sign in with the lab Entra/SQL identity, and run SQL verification. Never assume a recovery timestamp holds data if it falls outside retention.

### 28.6. Step 4: Compare SQL Data

Example **read-only** T-SQL against restored and source DBs:

~~~sql
SELECT COUNT(*) AS OrderCount
FROM dbo.Orders;

SELECT OrderId, Status, TotalMinorUnits
FROM dbo.Orders
WHERE OrderId IN ('demo-001', 'demo-002');
~~~

Then check:
- Does the deleted demo order appear in the restored DB?
- Are valid orders created after the fault still present in the source DB?
- Are primary keys, foreign keys, and unique constraints intact?
- Do payment/invoice IDs match?
- Do restore status and response time meet criteria?

Never copy the whole restored DB back over source; plan a **selective recovery** for missing records using unique keys and guarded transactions.

### 28.7. Step 5: Blob Version / Snapshot

On a blob account with versioning/snapshots enabled and synthetic data:
1. List versions of the synthetic blob via portal, SDK, or Azure CLI.
2. Identify the version ID predating the overwrite.
3. Copy the older version to a **recovery container/path**.
4. Inspect size, hash, and PDF contents.
5. Reconcile invoice number/amount against restored SQL Orders.
6. Do not overwrite the live Blob without approval.
7. Restore/promote verified content using a conditional ETag update.

Exact CLI syntax to copy a historical version depends on auth mode, version ID, Blob type, API, and tool version—verify actual syntax against your **lab account** rather than assuming one copy command fits every HNS/account mode.

### 28.8. Step 6: Conclude Lab with Measurements

~~~text
Incident simulated:         10:00 UTC
Restorable SQL point:       09:58 UTC
SQL data loss window:       2 minutes
Blob recovered version:     09:59 UTC
Business verification:      10:48 UTC

Observed RPO SQL:           2 minutes
Observed RTO to verified:   48 minutes

Goal SQL RPO:               5 minutes → PASS
Goal business RTO:          60 minutes → PASS
~~~

Figures above are illustrative. Learners must record real timestamps from their lab rather than marking PASS from the template.

### 28.9. Cleanup

- Restored target databases and Blob recovery containers accrue charges; clean up after capturing evidence and approvals.
- Never delete source data used by a shared lab.
- Never purge vaults, backup history, or keys.
- Never disable backups to save cost without informing the owner.
- Record teardown IDs, observed costs, and lessons learned.

## 29. Lab B: Tabletop Recovery for Cosmos DB, Queues, and Analytics

### 29.1. Scenario

A team discovers:
- 13:00: application writes an incorrect `cartTotal` field to Cosmos DB for several carts.
- 13:05: Azure Service Bus holds many unprocessed `InvoiceRequested` commands.
- 13:10: Databricks Gold reporting tables were computed with bad values.
- 13:20: Incident confirmed.
- Orders SQL remains accurate and the payment provider lost zero data.

The goal is not wiping all cloud resources, but building a **recovery map** and proving how to avoid double charges, duplicate invoices, lost carts, and bad reports.

### 29.2. Pre-Restore Decisions

Answer:

1. Does the Cosmos DB account use periodic or continuous backup?
2. What are the earliest restorable time and recovery granularity?
3. Can we restore 12:59 to an isolated account?
4. How will valid carts updated after 13:00 be handled?
5. Does current Service Bus Geo-DR protect **message bodies** or only metadata?
6. Does Orders SQL hold outbox rows sufficient to re-emit missing `InvoiceRequested` events?
7. Which invoices did workers already create, and are idempotency keys enforced?
8. Can Gold tables be rebuilt from Bronze raw?
9. Is Event Hubs/Capture retention sufficient for replay?
10. How long does restoring core capabilities take under RLO?

### 29.3. Data Mapping

| Source | Keep or recover? | Recommended action |
|---|---|---|
| Accurate Orders SQL | Keep | No PITR or overwrite |
| Accurate payment provider | Keep | Read-only reconciliation |
| Corrupted Cosmos Carts from 13:00 | Isolated restore pre-fault | Selective merge by `cartId`/version |
| Service Bus active messages | Keep / inspect | Do not purge queue; pause unsafe consumers briefly |
| SQL Outbox | Replay source | Idempotent replay of missing events |
| Invoice Blobs | Inspect | Do not regenerate if valid invoice already exists |
| Corrupted Gold analytics | Rebuild | Recompute from verified Bronze/Silver |
| Healthy Key Vault / identities | Keep | Do not rotate unnecessarily |

Never roll every service back to 12:59 just because one table is corrupted. **Preserving intact data** is essential to recovery correctness.

### 29.4. Execution Plan

~~~mermaid
flowchart TD
    A["Freeze faulty Cart writer"] --> B["Restore Cosmos to isolated target"]
    B --> C["Identify corrupted cart records"]
    C --> D["Merge validated records, preserve good updates"]
    A --> Q["Pause unsafe invoice consumers"]
    Q --> O["Compare SQL Outbox and invoice state"]
    O --> R["Replay only missing intents"]
    D --> V["Business checks"]
    R --> V
    V --> G["Rebuild analytics Gold"]
    G --> Z["Resume traffic and monitor"]
~~~

Specify who executes each step, required approvals, comparison datasets, and rollback for the recovery steps themselves.

### 29.5. Preserve History Instead of Erasing Tracks

Do not delete corrupted Carts in primary before exporting forensic evidence and building a recovery plan; immediate deletion can:
- Erase the timestamp of the first bad write.
- Emit extra change-feed/delete events.
- Replicate further bad mutations.
- Complicate payment/order reconciliation.
- Destroy root-cause evidence.

Freeze write paths, copy authorized data/logs, and perform selective repair. When PII is involved, follow retention/forensics policies.

### 29.6. PASS Criteria

- Cosmos data fixes only affected records.
- Valid carts updated after 13:00 are not inadvertently rolled back.
- Orders SQL and payment provider remain uncorrupted.
- Outbox/message reconciliation neither drops nor duplicates side effects.
- Invoice PDFs and ledger totals match.
- Gold reports are rebuilt from trusted source records.
- The app handles new carts normally.
- RPO/RTO are measured against targets.
- Zero sensitive data appears in public logs.
- Evidence and owner sign-off are archived.

## 30. Failure-Specific Runbooks

### 30.1. Runbook A: Batch of Orders Accidentally DELETEd in Azure SQL

1. Detect via alert/audit/business check; record incident UTC time.
2. Stop the faulty job/app issuing DELETEs and preserve logs.
3. Find the first bad transaction in DB/audit logs.
4. Check PITR retention and latest restorable time.
5. Approve a pre-fault timestamp and isolated target DB.
6. Restore to a **new database**; never overwrite source.
7. Verify row counts, keys, foreign keys, and constraints.
8. Analyze good writes after the restore timestamp to preserve valid data.
9. Write a selective merge script wrapped in a transaction/rollback plan.
10. Dry-run on staging/recovery copy with DBA review.
11. Apply to primary upon approval.
12. Reconcile Orders–Payments–Invoices and outbox events.
13. Monitor p95/5xx/SQL health and reopen writers.
14. Log RPO/RTO and root cause to prevent recurrence.

### 30.2. Runbook B: Deletion or Ransomware on Blob/Files

1. Isolate the principal/process deleting or mutating data.
2. Preserve diagnostic logs, audits, and affected object inventory.
3. Check versioning/soft delete/snapshots/backup policies **enabled prior to the incident**.
4. Locate the earliest bad overwrite/delete.
5. Select pre-fault versions/snapshots.
6. If compromise is suspected, restore into an **isolated** account/container/share.
7. Check file counts, hashes, ACLs, metadata, and malware scans.
8. Cross-check SQL records rather than treating an old wrong invoice as authoritative.
9. Selectively restore or issue correction records respecting immutability.
10. Verify app pointers, caching/CDN, and SAS expiration.
11. Reopen access only once compromised principals are eradicated.
12. Rotate source tokens/keys if needed, log audits, and harden controls.

### 30.3. Runbook C: Region Outage

1. Distinguish an Azure region outage from DNS/IAM/app-deployment failures.
2. Activate DR plan per owner and business impact.
3. Check secondary region health, quotas, capacity, and networking.
4. Measure replication lag / last sync to estimate potential RPO.
5. Choose **hot-replica failover** or **geo-restore backup** per data integrity.
6. Approve potential data loss if forced failover carries risk.
7. Stand up/restore Key Vault/identities/Private DNS and app runtimes per dependency graph.
8. Block split-brain writers; stop producers/consumers as needed.
9. Verify DB/Blob/message source state.
10. Open a canary cohort or read-only mode.
11. Reconcile Orders/outbox/payments and worker offsets.
12. Shift Front Door/DNS/app endpoints controllably.
13. Monitor RLO/RPO/RTO and DR spend.
14. Do not rush failback when primary returns; plan two-way sync.

### 30.4. Runbook D: Cosmos DB Corrupted by Mass Update

1. Halt faulty jobs and bad writes.
2. Confirm account API, backup mode, and retention.
3. Locate timestamp predating the bad update.
4. Restore to an isolated target via supported API.
5. Verify container settings, partition keys, indexing, and TTLs.
6. Separate corrupted records from valid updates inside the incident window.
7. Design merges using ETags/conditional writes or idempotency.
8. Test on sample/staging data while watching RU throttling.
9. Run repairs in batches and track progress.
10. Verify cart/customer invariants, multi-region consistency, and change feed.
11. Re-enable writes; retain target backup briefly for audit.
12. Review backup mode and permissions to shrink future blast radius.

### 30.5. Runbook E: Service Bus Namespace Lost or Message Backlog Vanished

1. Confirm namespace outage vs. application consumer bugs.
2. Verify tier and actual DR mode: metadata-only alias vs. data geo-replication.
3. Inspect primary/secondary messaging state, active messages, and DLQ.
4. Pause senders/consumers that might duplicate during cutover.
5. Fail over namespace/alias per supported playbook.
6. If messages did not replicate, use **SQL Outbox / immutable event archive** to recover intent.
7. Replay by stable message ID with idempotent handlers.
8. Check scheduled messages, sessions, and locks per service semantics.
9. Reconcile accepted Orders against produced invoices and queue backlog.
10. Test DLQ/retry/poison-message policies.
11. Restore traffic within rate limits and watch errors.
12. Document missing/duplicated messages, RPO, and root cause.

### 30.6. Runbook F: Lost Key Vault CMK or Secret

1. Assess accidental delete, policy denial, network outage, or compromise.
2. Halt further purges, deletes, or rotations.
3. Inspect soft-deleted objects/vault, retention, and purge protection.
4. Recover keys/secrets/certificates where supported.
5. Restore roles/access policies, Private DNS, and identity permissions.
6. Verify key version / protector association.
7. Test decrypt/unwrap on an isolated recovered resource.
8. If downstream credentials were revoked, reissue/rotate validly.
9. Check all database/storage encryption dependencies.
10. Audit actors, logs, and IAM changes.
11. If the key is unrecoverable, pursue alternate backups/recovery—never promise decryption.
12. Update key lifecycles and DR drills.

### 30.7. Runbook G: Restore Job Succeeded Yet App Still Fails

1. Verify the app points to the right recovery endpoint/database.
2. Check schema/engine version, DB users, and firewalls.
3. Check Entra identities, Key Vault secrets, and CMKs.
4. Check VNet/Private Endpoints/DNS in the target region.
5. Check App Configuration, feature flags, and binary compatibility.
6. Check missing dependent Blobs, queues, or caches.
7. Check data corruption or row-level invariants.
8. Inspect SDK timeouts, 401/403/429 responses, and DB connections.
9. Run controlled read-only business smoke tests.
10. If data is wrong, roll back cutover or continue repair—never declare DR PASS.

### 30.8. Runbook H: Ransomware and Compromised Production Identity

1. Trigger security incident response; appoint Incident Commander.
2. Block further writes/deletes; isolate exposed credentials and workloads per security policy.
3. Preserve evidence, logs, and backup inventories.
4. Pinpoint the earliest compromise / bad-data timestamp.
5. Select **clean** recovery points predating infection.
6. Stand up a recovery environment with separate permissions/identities.
7. Verify image provenance and patch/vulnerability baselines.
8. Restore data and scan for malware/corruption.
9. Rotate exposed secrets/keys per service guidance without destroying keys needed to decrypt recovery paths first.
10. Verify business integrity and user access controls.
11. Ramp canary traffic and watch for suspicious activity.
12. File legal/compliance notices, run postmortem, and harden guardrails.

### 30.9. Failback Runbook After Cross-Region DR

1. Establish that the DR region is the current source of truth.
2. Prevent the old primary from accepting writes automatically.
3. Assess lag and divergent data on the old primary.
4. Choose re-seed, reverse replication, or backup restore per service.
5. Restore networking/keys/identities across both regions.
6. Reconcile data written during DR operations.
7. Load-test and validate business transactions in the rebuilt primary.
8. Freeze or throttle writes briefly at cutback if required.
9. Shift traffic after approvals and health checks.
10. Monitor replication across SQL/Cosmos/Storage/queues.
11. Re-enable backup policies and geo-redundancy.
12. Record actual RPO/RTO and lessons learned.

### 30.10. When No Suitable Recovery Copy Exists

Sometimes backups are missing, retention expired, or CMKs are gone. Then:
- **Never fabricate claims that Azure can definitely recover it.**
- Document the missing recovery point, timeframe, and affected data classes.
- Search legitimate secondary sources: immutable archives, payment ledgers, outboxes, exported reports, or partner records.
- Evaluate rebuilding via business event replay.
- Avoid tampering with production transaction logs in engine-unsupported ways.
- Escalate business and legal risk per governance process.
- Apply only approved data repairs and reconciliations.
- Fix backup architecture and monitoring to prevent recurrence.

## 31. DR Drills: From Tabletop to Full Restore

### 31.1. Drill Maturity Levels

| Level | Activity | Purpose |
|---|---|---|
| **L0: review** | Review matrices, policies, owners | Catch missing documentation |
| **L1: tabletop** | Simulate DB/region loss without touching resources | Clarify decisions/dependencies |
| **L2: isolated restore** | Restore DB/Blob/VM into test target | Verify recovery points |
| **L3: workload validation** | Run test app against restored data | Measure consistency and RTO |
| **L4: failover exercise** | Shift an approved slice of traffic | Test routing and capacity |
| **L5: full business DR drill** | End-to-end under governance | Measure whole-business RPO/RTO/RLO |

Never run L4/L5 in production unilaterally just because someone wants to "test failover"; require planned change windows, approvals, and rollback plans.

### 31.2. Drill Plan Template

~~~text
DR drill ID: DR-ORDERS-LAB-001
Scope: Orders SQL + Invoice Blob + outbox replay
Recovery environment: isolated lab subscription
Start UTC: <approved timestamp>
Data sensitivity: synthetic
Target RPO: <= 15 minutes
Target RTO: <= 120 minutes
Target RLO: read/create test order and verify invoice
Incident commander: assigned owner
Database owner: assigned owner
Security approver: assigned owner
Rollback/cleanup plan: documented
Evidence: monitoring, job IDs, counts, checksums
~~~

This is a template, not an Azure API schema. Effective drills include independent observers recording surprises rather than massaging reports to look compliant.

### 31.3. Execution Checklist

1. Verify permissions and quotas prior to the drill.
2. Snapshot current backup retention and recovery-point states.
3. Record UTC start time and freeze test writes.
4. Inject a representative simulated failure.
5. Provision restored resources in the isolated boundary.
6. Restore Key Vault/identity/network dependencies if required by scenario.
7. Boot the app using proper test credentials/data.
8. Reconcile DB/outbox/Blob/messages.
9. Run smoke, integration, and security tests.
10. Measure observed data-loss window and business recovery time.
11. Compare against target RPO/RTO/RLO.
12. Log failed steps, human errors, and improvements.
13. Clean up post-approval while preserving backup policies.
14. Schedule re-testing after major architectural changes.

### 31.4. Issues Drills Commonly Uncover

- Backup retention shorter than contractual RPO.
- Source account lacked a prerequisite feature, preventing recovery of older deletes.
- DR region lacked VM/DB quotas.
- Storage backups relied on a purged key.
- Restored DB came up yet App Service couldn't reach its Private Endpoint.
- Service Bus Geo-DR moved metadata only, losing business messages.
- Consumers ran before data reconciliation, duplicating invoices.
- New SQL schema was incompatible with stale standby app images.
- Restore target was accidentally created in a production resource group.
- Runbook relied on an expired service principal.
- GitOps pipeline silently overwrote restore/cutover state.
- Log Analytics lacked enough telemetry to prove RPO/RTO.

### 31.5. Grading by Observable Outcomes

To conclude:
- **Recovery point verified:** PASS/FAIL.
- **Data integrity verified:** PASS/FAIL.
- **App/service readiness:** PASS/FAIL.
- **Business invariants:** PASS/FAIL.
- **RPO objective:** PASS/FAIL by actual timestamps.
- **RTO objective:** PASS/FAIL by business recovery time.
- **Security/isolation:** PASS/FAIL.
- **Observability/audit:** PASS/FAIL.
- **Cleanup/owner sign-off:** PASS/FAIL.

A DR drill that fails a criterion still delivers huge value—it reveals an architectural gap to fix, not a reason to tweak measurements for a "PASS."

## 32. Case Study: Recovering an E-Commerce System on Azure

### 32.1. Architecture and Data Classification

A company runs:
- **Azure Front Door:** traffic routing.
- **Spring Boot on AKS:** Orders API, Payment Integration, Invoice Worker.
- **Azure SQL Database:** orders and SQL Outbox, system of record for accepted orders.
- **Azure Cosmos DB:** carts and product recommendations.
- **Azure Service Bus:** `InvoiceRequested` command delivery.
- **Azure Blob Storage:** invoice PDFs plus a separate policy archive.
- **Azure Key Vault:** partner payment tokens / CMKs.
- **Azure Data Lake Storage Gen2 + Databricks:** reporting.
- **Azure Managed Redis:** product/pricing cache.
- **Azure Monitor / Application Insights:** monitoring and incident evidence.

~~~mermaid
flowchart LR
    U["Customers"] --> FD["Azure Front Door"]
    FD --> API["Orders API / AKS"]
    API --> SQL["Azure SQL + Outbox"]
    API --> COS["Cosmos DB Carts"]
    API --> KV["Key Vault"]
    SQL --> P["Outbox Publisher"]
    P --> SB["Service Bus"]
    SB --> W["Invoice Worker"]
    W --> B["Blob invoices"]
    SQL --> ETL["Data pipelines"]
    B --> ETL
    ETL --> LAKE["ADLS / Delta / Reports"]
    API --> RED["Redis cache"]
    API -. "Telemetry" .-> MON["Azure Monitor"]
    W -. "Telemetry" .-> MON
~~~

### 32.2. Business Objectives

| Business flow | Target RPO | Target RTO | Initial-stage RLO |
|---|---|---|---|
| Order confirmation | 5 minutes | 60 minutes | Read and create valid orders |
| Payments | Zero double-charge, 100% intent reconciliation | 90 minutes | Status checks / no duplicate capture |
| Invoice PDFs | 60 minutes or regenerate from valid data | 4 hours | View historical invoices |
| Carts | 15 minutes | 2 hours | Customers can view/edit carts |
| Product cache | Tolerates loss | 30 minutes | API serves via DB fallback |
| Reporting | 24 hours | 24 hours | Reports display staleness warning |

**A 5-minute RPO for Orders is not automatically guaranteed by an arbitrary region backup setting.** The team must prove matching SQL backup/replication/replay mechanisms. Payment targets emphasize a **business invariant** over timestamps, because you must never re-capture a payment simply because a local restore lacked a row.

### 32.3. Primary Incident

Simulated timeline:
- 09:40: buggy release runs mass DELETE on Orders SQL.
- 09:43: app emits some `InvoiceRequested` commands via outbox for new orders.
- 09:45: alert fires on abnormal SQL row-count drop.
- 09:50: incident commander stops faulty writer and pauses invoice worker.
- 09:55: determines PITR before 09:40 is needed without dropping valid orders from 09:40–09:50.
- 10:00: Azure SQL restore to isolated DB initiated.
- 10:30: DB restored; reconciliation begins.
- 10:55: selective merge completes; worker resumes safely.
- 11:05: business smoke tests pass; traffic reopens.

### 32.4. Why Not Restore Everything to 09:39?

| Component | Post-fault state | Decision |
|---|---|---|
| Orders SQL | Batch of rows deleted | Restore **09:39 copy**, selective merge |
| Cosmos DB Carts | Unaffected | Keep intact |
| Payment provider | Validly captured | Keep intact; use reconciliation API |
| Service Bus | Holds recently sent messages | Keep; do not purge namespace |
| SQL Outbox | Holds valid new rows | Reconcile/replay gaps; do not drop |
| Blob invoices | Holds valid new PDFs | Keep; verify references |
| Redis cache | May hold stale state | Invalidate/rebuild |
| Analytics Gold | Skewed by SQL DELETE | Rebuild after SQL repair |
| Key Vault | Healthy | Do not rotate unnecessarily |

Rolling everything back to 09:39 would discard payments and orders succeeded during the subsequent 10 minutes. **Selective recovery and reconciliation** are architectural requirements, not a variation of full rollback.

### 32.5. Recovery Timeline and Measurements

In the scenario above:
- Incident starts 09:40.
- First known-good SQL recovery point chosen: 09:39.
- Looking solely at the PITR image, potential data gap is **1 minute** at fault time, while writes from 09:39–09:50 require selective recovery/replay.
- Detection: 09:45, 5 minutes post-fault.
- Containment: 09:50, 10 minutes post-fault.
- Restored SQL usable at 10:30.
- Business RLO reached at 11:05.
- **Observed business recovery time = 85 minutes** from 09:40 to 11:05.

Against a 60-minute Orders RTO target, **this drill FAILS on RTO**, even though the DB restore job finished in 50 minutes and data reconciled cleanly. Improvements include:
- Automating identification of affected rows.
- Querying governed audit/CDC/temporal history.
- Safely parallelizing restores and business verification prep.
- Optimizing target compute/DB restore sizing.
- Tightening alerts on suspicious deletes.
- Streamlining emergency restore approvals per policy.

### 32.6. Additional Risks to Address

- Restored SQL DB lacks permissions for the app identity.
- New Blob invoices generated by workers lack matching order rows after SQL recovery.
- Outbox replay emits duplicate Service Bus commands.
- Payment provider charged while local order status vanished.
- Old AKS app versions fail against post-migration schemas.
- Key Vault tokens rotated mid-incident.
- Redis cache serves stale state after DB repair.
- Unrebuilt Gold reports show wrong revenue figures.

Each risk needs an owner, validation test, and recovery metric.

### 32.7. Post-Incident Design Upgrades

The team decides to:
1. Add business-metric alerts on abnormal SQL row drops.
2. Strip unnecessary DELETE privileges from runtime roles.
3. Add governed temporal/audit history on critical entities.
4. Drill SQL PITR into a recovery DB quarterly.
5. Enforce stable SQL Outbox IDs and idempotent consumers.
6. Retain invoice Blob versions and backups properly.
7. Build automated Orders–Payments–Invoices reconciliation.
8. Add dry-run recovery scripts and manual merge approvals.
9. Enable Key Vault soft delete / purge protection per policy.
10. Enforce RPO/RTO targets and measurement rules in release governance.

### 32.8. Another Scenario: Region Outage

If both primary Azure SQL and AKS regions go down:
- You cannot simply PITR SQL into the failed region.
- Use geo-capable DB recovery/failover per actual configuration.
- Stand up AKS/networking/identities in the DR region.
- Check Storage redundancy/Blob recovery and Service Bus DR mode.
- Inspect geo-replication lag before forced failover.
- Fence split-brain writers and establish the new source of truth.
- Ramp traffic via Front Door once business data is coherent.

This is a **distinct recovery path** from accidental row deletion. Never force one runbook onto every root cause.

## 33. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Better practice |
|---|---|---|
| Equating LRS/ZRS/GRS with backups | Bad deletes replicate with no recovery point | Independent backups/PITR/versioning |
| Treating soft delete as immutable backup | Privileged attackers can still bypass or erase | Least privilege + immutable/isolated copies |
| Measuring RTO only by restore job completion | App still isn't serving users | Measure until business smoke tests PASS |
| Picking backup cadence purely from RPO | Backup failures/lag exceed data-loss limits | Track latest restorable point + alerts |
| Treating a read replica as an old snapshot | Corruption replicates | PITR prior to bad write |
| Overwriting primary immediately on SQL restore | Loses valid post-fault writes | Restore to new DB and merge selectively |
| Swapping entire Cosmos DB account without reconciling | Loses valid cart updates | Isolated restore, merge, check TTL/ETags |
| Expecting Cosmos multi-region to undo DELETEs | Deletes replicate | Continuous/periodic backups matching needs |
| Skipping Cosmos backup-mode checks | Missing PITR when needed | Inventory API/tier/retention |
| Blob GRS without versioning | Overwrites leave zero prior versions | Enable versioning/soft delete/backups |
| Enabling soft delete after deletion | Cannot recover pre-feature objects | Preconfigure and test restores |
| Setting Blob lifecycle expiry too short | Recovery points disappear early | Match retention to data classification |
| Locking WORM on unvalidated data | Bad records cannot be edited | Validate before applying immutability |
| Copying Blob checklist to ADLS HNS | Unsupported features, lost ACLs | Check HNS support matrix |
| Treating Azure Files snapshots as DB backups | Inconsistent DB restores | Engine-aware backups/quiescing |
| Treating AKS etcd backup as full state | External DBs/PVs lost | Back up each data path separately |
| Treating ASR as ransomware backup | Malware/corruption replicates | Independent clean recovery copies |
| Treating Service Bus metadata Geo-DR as message sync | Queued messages lost on failover | Verify DR mode + Outbox/archives |
| Treating Event Hubs checkpoints as backups | Cannot replay after retention expires | Use Capture/archives and retention |
| Using Redis as sole store without persistence | Lost carts/sessions | Use a managed DB or proper persistence/backups |
| Rotating/purging CMKs before restoring | Backups become undecryptable | Plan key lifecycles and recovery |
| Backups exist yet DR region lacks quotas | RTO breached | Pre-check capacity and drill |
| Copying production DB openly to dev | Exposes PII/secrets | Isolated recovery environments |
| Picking identical UTC timestamps across services expecting consistency | Business state skews | Reconciliation and invariants |
| Starting queue workers before DB recovery | Duplicate/lost side effects | Enforce restore order / drain workers |
| Traffic rollback instead of data restore | Bad state remains live | Plan business data repair |
| Keeping only `:latest` image tag | Cannot redeploy stable code | Immutable digests / artifact retention |
| Disabling monitoring in DR to save money | Zero incident evidence | Budget DR telemetry |
| Never rehearsing failback | Split-brain when primary returns | Explicit reverse sync/cutback |
| Declaring DR PASS on HTTP 200 | Payments/invoices still broken | RLO/business acceptance |

### 33.1. One Guiding Rule

**Each failure class demands its own answer:**
- **Availability** faults → HA/replicas/failover.
- **Logical/corruption** faults → backups/PITR/versioning/reconciliation.
- **Security compromises** → isolation/immutable clean copies/key rotation.
- **Metadata/config** loss → IaC/Git/identity recovery.
- **Event loss** → durable outbox/event archive/replay.
- **Derived state** loss → rebuild from source.

If a proposal answers every failure class with a single "replicated = yes" checkbox, the design is incomplete.

## 34. Pre-Production Data Recovery Design Checklist

### 34.1. Business Objectives

- [ ] Every dataset is classified as system of record, derived, cache, archive, or messaging.
- [ ] Business owners and data classifications are assigned.
- [ ] RPOs in minutes/hours are approved rather than inferred from backup schedules.
- [ ] RTOs measure business capability recovery, not just restore job completion.
- [ ] RLO is explicit: read-only, accept writes, payments, or full service.
- [ ] RTO/RPO are evaluated separately for accidental deletes, ransomware, and region outages.
- [ ] Legal retention, data residency, and PII constraints are documented.
- [ ] Dependencies, critical paths, and restore ordering are defined.

### 34.2. Azure SQL / Postgres / MySQL / Cosmos

- [ ] Azure SQL STR/LTR and backup redundancy/geo support are verified.
- [ ] SQL PITR into a new DB and selective merges are drilled.
- [ ] SQL geo-replicas/failover groups are not treated as corruption backups.
- [ ] Managed Instance instance-level configs and SQL Agent jobs have DR plans.
- [ ] PostgreSQL/MySQL Flexible Server backup retention/geo options match SKU.
- [ ] Restored Flexible Servers have identities, networking, and roles tested.
- [ ] Cosmos DB periodic/continuous backup mode matches API/tier.
- [ ] Cosmos PITR, TTL, unique keys, partitioning, and restore targets are understood.
- [ ] Multi-region replication and conflict policies are verified.
- [ ] Post-restore queries, checksums, and business integrity checks exist.

### 34.3. Blob / ADLS / Files / VM / AKS

- [ ] Blob soft delete, container soft delete, and versioning match supported objects/accounts.
- [ ] Blob operational/vaulted backups and immutability are selected per requirements.
- [ ] Storage GRS/RA-GRS and replication lag are evaluated.
- [ ] HNS/ADLS Gen2 feature support, ACLs, and Delta logs are protected.
- [ ] Azure Files snapshots/backups support the exact SMB/NFS/tier setup.
- [ ] Azure Files recovery checks SMB/NFS permissions and file handles.
- [ ] VM backups use app-consistent strategies where needed.
- [ ] ASR never replaces clean recovery-point backups.
- [ ] AKS GitOps/IaC, CSI volumes, and external DB backups are separated cleanly.
- [ ] Kubernetes restores test CRD/identity/network ordering.
- [ ] Runtime principals cannot arbitrarily delete storage accounts or backups.

### 34.4. Messaging, Caching, and Analytics

- [ ] Service Bus Geo-DR protection scope (metadata vs. message bodies) is confirmed.
- [ ] Outbox/idempotency and replay plans protect accepted business intents.
- [ ] Azure Event Hubs retention, Capture, checkpoints, and archive policies are valid.
- [ ] Message schema versioning and DLQ recovery are tested.
- [ ] Azure Queue Storage is not relied on as an infinite event history.
- [ ] Redis caches are rebuildable or backed by business-appropriate persistence/backups.
- [ ] ADLS Bronze raw data and Databricks/Synapse/ADF pipeline code are retained.
- [ ] Delta time travel retention/`VACUUM` is not mistaken for complete backups.
- [ ] Analytics rebuild workloads have enough compute to meet RTO.

### 34.5. Security, Access, and Operations

- [ ] Key Vault CMKs/versions and purge protection meet requirements.
- [ ] Managed identities, Entra RBAC, and break-glass plans are prepared.
- [ ] Private DNS/VNets/NSGs/Firewalls in the recovery region are tested.
- [ ] DR region has real quotas, capacity, and network endpoints.
- [ ] Recovery targets are isolated with PII/credential controls.
- [ ] Azure Monitor alerts cover backup gaps, failures, policy drift, and anomalous deletes.
- [ ] Backup/restore jobs have owners, retention, and audit trails.
- [ ] Immutable/independent clean copies exist where cyber risks require them.
- [ ] Approvals are required before failover, delete, purge, or data merges.
- [ ] Zero plaintext secrets exist in IaC, tickets, or scripts.
- [ ] RPO/RTO/RLO are measured during restore drills.
- [ ] Runbooks, on-call rotations, release gates, and cleanup plans are in place.

### 34.6. Cost, Review, and Governance

- [ ] Storage backup retention, copy sizes, and geo costs are budgeted.
- [ ] Budgets cover restore drills and target recovery resources.
- [ ] Data is tiered by criticality to avoid over-protecting caches.
- [ ] Cost Management tags/alerts and monitoring costs are configured.
- [ ] Backup policies/SLAs are reviewed as data volume grows.
- [ ] Regional outages and accidental deletions are drilled separately.
- [ ] Failback plans and split-brain prevention exist.
- [ ] Evidence proves restored apps actually process transactions.
- [ ] Retention periods for stable artifacts, keys, and backups align cleanly.
- [ ] Exceptions carry owner sign-off and expiration dates.

## 35. Self-Check Questions

1. **What is RPO?** Maximum tolerable data loss, measured as time between the incident and the recovery point.
2. **What is RTO?** Target duration to restore business/service capability.
3. **What does RLO mean?** Service level required when RTO is reached—such as read-only vs. full payment processing.
4. **How does backup retention differ from backup frequency?** Retention is how long copies are kept; frequency is how often points are created.
5. **Why does a 15-minute backup schedule not guarantee a 15-minute RPO?** Jobs can fail/lag, or recovery points can be unusable.
6. **Does a completed restore job mean RTO is met?** No; application startup and verification remain.
7. **What does zone redundancy protect against?** Single availability zone failures within supported regions.
8. **Does ZRS solve a full-region outage?** No.
9. **Does GRS replicate synchronously to the secondary region?** No; cross-region replication is typically asynchronous.
10. **Does RA-GRS allow reading the secondary where supported?** Yes, prior to failover per Storage read-access semantics.
11. **Does GRS save an accidentally DELETEd Blob?** Not by default; deletions replicate, requiring soft delete/versioning/backups.
12. **Do replicas replace PITR backups?** No; corruption can replicate.
13. **How does immutability differ from soft delete?** Immutability blocks edits/deletes during retention per policy; soft delete recovers deleted objects within a grace window.
14. **Does a resource lock replace immutable backups?** No.
15. **What is a system of record?** The authoritative data store governing business state.
16. **How can derived analytics data recover?** Rebuild from original sources and versioned ETL if intact.
17. **Does a Redis cache need the same RPO as Orders SQL?** No if strictly derived; yes if it holds unique state.
18. **What scenario does Azure SQL PITR solve best?** Restoring a DB to a timestamp prior to delete/corruption within retention.
19. **Does Azure SQL PITR undo a single row in place inside the live DB?** No; it normally restores a new DB for selective merging.
20. **Why not overwrite the entire Orders DB when only 100 rows were lost?** It would wipe valid writes committed after the chosen timestamp.
21. **What is Azure SQL LTR for?** Long-term/compliance retention of recovery copies per policy and support.
22. **Is LTR the same as second-by-second PITR across years?** No; LTR typically keeps discrete restore points.
23. **Does SQL active geo-replication protect against bad UPDATEs?** No; UPDATEs replicate too.
24. **Does forced geo-failover risk losing data?** Yes, depending on replication lag and service behavior.
25. **Does SQL Managed Instance match SQL Database single DB in all restore APIs?** No.
26. **Does zone-redundant HA on PostgreSQL imply geo-backups?** No.
27. **Does PostgreSQL/MySQL Flexible Server PITR usually create a new server?** Typically yes, per service restore flow.
28. **Does a read replica replace backups?** No.
29. **How does Cosmos DB Periodic backup differ from Continuous?** Periodic keeps discrete points; Continuous supports PITR within retention per capability.
30. **Does Cosmos DB multi-region automatically save a deleted container?** No.
31. **Does Cosmos DB continuous backup restore a single document directly into primary?** No; scope and target constraints apply.
32. **Does Cosmos DB change feed always preserve before-images and all deletes?** No; depends on mode and configuration.
33. **What failures does Blob versioning solve?** Recovering prior content before overwrites/changes where supported.
34. **Do Blob soft delete and container soft delete serve the same scope?** No; one protects objects and the other protects containers.
35. **If you enable soft delete after a deletion, can it recover the already-deleted object?** No.
36. **Is Operational backup for Blobs always an independent copy in a Backup vault?** No.
37. **Does Vaulted backup for Blobs automatically support every HNS account?** Never assume; check the support matrix.
38. **Does Blob immutability turn a wrong invoice into a right one?** No; it only prevents edits/deletes per policy.
39. **How does ADLS Gen2 differ from standard GPv2 Blob?** HNS, ACL/path semantics, and different data-protection support limits.
40. **Does Delta time travel replace backups?** No if underlying files/logs were deleted or retention expired.
41. **Are Azure Files snapshots database-aware backups?** Not by default.
42. **Besides file contents, what must SMB/NFS file restores check?** ACLs/permissions, file handles, and mount behavior.
43. **Are VM disk snapshots always transaction-consistent?** No; they can be crash-consistent only.
44. **Does Azure Site Recovery replace ransomware backups?** No.
45. **Do AKS resource manifests back up external SQL/Cosmos?** No.
46. **What matters when backing up AKS PVCs?** CSI/volume support, application consistency, storage classes, and restore topology.
47. **Does a metadata-only Service Bus Geo-DR alias retain message bodies?** No.
48. **Why distinguish Service Bus Geo-DR from Geo-Replication?** Feature support and message-data protection differ.
49. **What problem does Transactional Outbox solve?** Commits business intent alongside DB transactions to replay messages if the broker fails.
50. **Does an outbox guarantee consumers run exactly once?** No; idempotency is still required.
51. **Are Event Hubs checkpoints backups of event payloads?** No; they record processing offsets only.
52. **What does Event Hubs Capture do?** Archives events to Storage/ADLS for retention/replay beyond stream limits when properly configured.
53. **Does GRS automatically restore deleted messages in Azure Queue Storage?** Not by default.
54. **What performance risk arises when a Redis cache is cold?** Cache stampede slamming the DB.
55. **Is purging a Key Vault CMK dangerous for backups?** Yes; backups may become undecryptable.
56. **What do Key Vault soft delete / purge protection guard against?** Premature deletion/purging of keys, secrets, or vaults within retention/rules.
57. **Do App Configuration snapshots restore data-plane Orders rows?** No; configuration only.
58. **Does IaC replace SQL/Blob backups?** No; IaC rebuilds the control plane, not business data.
59. **Does restoring 3 services to the same timestamp guarantee consistency?** No; business-level reconciliation is required.
60. **Why must payments reconcile against external gateways outside the DB?** Payments may have captured even when local DB restores drop records.
61. **What does idempotency achieve during replay?** Prevents duplicate side effects.
62. **Why might reports still look wrong post-restore?** Derived Gold/ETL tables have not been rebuilt from clean sources.
63. **Why restore identity/networking before apps?** Apps cannot read data, decrypt, or connect without them.
64. **When can failback cause split-brain?** When the old primary accepts writes before syncing with the DR source of truth.
65. **How does cyber recovery differ from regional failover?** Needs containment, clean backups, and identity/image attestation.
66. **Does a small RPO guarantee a small RTO?** No.
67. **Does having zero backup-gap alerts prove backups restore cleanly?** No; test restores and integrity checks are required.
68. **What makes a DR drill PASS?** Verified recovery point, data integrity, app/business RLO, and RPO/RTO within targets.
69. **What drives DR cost?** Protected data size/churn, retention, redundancy, warm replicas, monitoring, and drills.
70. **What defines the strongest data-recovery design?** Classifying every service/data store, matching mechanisms to fault classes and SLOs, protecting keys/rights, planning reconciliation, independent backups, regular drills, and active monitoring.

## 36. References

The following resources are **official** starting references. Before configuring or running recovery commands, verify SKUs, regions, tiers, feature availability, retention limits, and docs for current service versions. This lesson does not provide fixed Azure SLAs in place of official service terms.

### Azure Reliability, Redundancy, Backups, and Cost

- [Azure Well-Architected Framework – Reliability](https://learn.microsoft.com/en-us/azure/well-architected/reliability/) — reliability, disaster recovery, failure modes.
- [Azure Storage redundancy](https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy) — LRS/ZRS/GRS/RA-GRS/GZRS/RA-GZRS.
- [Azure Backup documentation](https://learn.microsoft.com/en-us/azure/backup/) — backup policies, vaults, restore scenarios.
- [Azure Site Recovery overview](https://learn.microsoft.com/en-us/azure/site-recovery/site-recovery-overview) — VM/site disaster recovery.
- [Azure Monitor documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/) — metrics, logs, alerts.
- [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/) — budgets, cost attribution, usage.
- [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/) — cost estimation by region/SKU.

### Databases

- [Azure SQL Database recovery from backups](https://learn.microsoft.com/en-us/azure/azure-sql/database/recovery-using-backups) — PITR, deleted database restore, geo-restore concepts.
- [Azure SQL Database long-term backup retention](https://learn.microsoft.com/en-us/azure/azure-sql/database/long-term-retention-overview) — multi-year backup retention.
- [Azure SQL Database active geo-replication](https://learn.microsoft.com/en-us/azure/azure-sql/database/active-geo-replication-overview) — geo-secondaries and failover.
- [Azure SQL failover groups](https://learn.microsoft.com/en-us/azure/azure-sql/database/failover-group-sql-db) — group failover/endpoint behavior.
- [Azure SQL Managed Instance](https://learn.microsoft.com/en-us/azure/azure-sql/managed-instance/) — deployment model and restore/HA guidance.
- [PostgreSQL Flexible Server backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-backup-restore) — automatic backups, PITR, geo options.
- [MySQL Flexible Server backup and restore](https://learn.microsoft.com/en-us/azure/mysql/flexible-server/concepts-backup-restore) — retention, restore points, and regional capabilities.
- [Azure Cosmos DB backup and restore](https://learn.microsoft.com/en-us/azure/cosmos-db/online-backup-and-restore) — periodic backup mode.
- [Azure Cosmos DB continuous backup introduction](https://learn.microsoft.com/en-us/azure/cosmos-db/continuous-backup-restore-introduction) — PITR, support matrix, and limits.
- [Azure Cosmos DB multi-region writes](https://learn.microsoft.com/en-us/azure/cosmos-db/multi-region-writes) — distributed write consistency/conflicts.

### Storage, Files, AKS, Messaging, and Caching

- [Azure Blob Storage data protection](https://learn.microsoft.com/en-us/azure/storage/blobs/data-protection-overview) — soft delete/versioning/point-in-time restore.
- [Azure Backup for Blobs overview](https://learn.microsoft.com/en-us/azure/backup/blob-backup-overview) — operational and vaulted protection per capability.
- [Immutable storage for Azure Blob](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview) — WORM and legal hold.
- [ADLS Gen2 overview](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction) — HNS, filesystem behavior.
- [Azure Files snapshots](https://learn.microsoft.com/en-us/azure/storage/files/storage-snapshots-files) — share snapshots and file recovery.
- [Azure Files backup](https://learn.microsoft.com/en-us/azure/backup/azure-file-share-backup-overview) — snapshot/vaulted backup by share/tier.
- [Azure VM backup overview](https://learn.microsoft.com/en-us/azure/backup/backup-azure-vms-introduction) — VM recovery points.
- [Azure Backup for AKS](https://learn.microsoft.com/en-us/azure/backup/azure-kubernetes-service-backup-overview) — supported Kubernetes resources/volumes.
- [Azure Service Bus Geo-DR](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-geo-dr) — namespace metadata DR.
- [Azure Service Bus documentation](https://learn.microsoft.com/en-us/azure/service-bus-messaging/) — messaging, geo-replication options, DLQ/transactions.
- [Azure Event Hubs Capture](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-capture-overview) — event archive to Storage/ADLS.
- [Azure Queue Storage documentation](https://learn.microsoft.com/en-us/azure/storage/queues/) — message lifecycle/visibility/TTL.
- [Azure Managed Redis documentation](https://learn.microsoft.com/en-us/azure/redis/) — caching, HA, persistence by tier.

### Identity, Configuration, Analytics, and Operations

- [Azure Key Vault soft-delete overview](https://learn.microsoft.com/en-us/azure/key-vault/general/soft-delete-overview) — soft delete and purge protection.
- [Azure Key Vault RBAC](https://learn.microsoft.com/en-us/azure/key-vault/general/rbac-guide) — data-plane roles.
- [Azure App Configuration snapshots](https://learn.microsoft.com/en-us/azure/azure-app-configuration/concept-snapshots) — versioned immutable configuration snapshots.
- [Azure Databricks Delta history](https://learn.microsoft.com/en-us/azure/databricks/delta/history) — table versions/time travel and retention.
- [Azure Data Factory documentation](https://learn.microsoft.com/en-us/azure/data-factory/) — source/pipeline/trigger orchestration.
- [Azure Synapse Analytics documentation](https://learn.microsoft.com/en-us/azure/synapse-analytics/) — SQL pools / lake analytics recovery context.
- [Azure Well-Architected operational excellence](https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/) — runbooks, drills, incidents, and evidence.

**Conclusion:** data recovery design on Azure must start from **business RPO, RTO, RLO, and each dataset's role**, not from asking "does this service have backups yet?" Azure SQL, PostgreSQL/MySQL, Cosmos DB, Blob/ADLS, Azure Files, VMs/AKS, Service Bus/Event Hubs, Redis, Key Vault, and analytics all carry **distinct failure modes, backup/restore granularities, and regional capabilities**. **Replication helps availability yet does not always rescue logical corruption; snapshots/soft delete cover certain deletes/overwrites yet do not replace isolated backups; restoring data does not automatically recover identities, DNS, encryption keys, or cross-system transactional consistency**. A truly reliable design classifies data, protects systems of record, pairs appropriate backups/PITR/versioning/archives with least privilege and immutable/clean copies where needed, **rehearses isolated restores, integrity checks, and reconciliation**, and backs them with sequenced recovery runbooks, capacity/budgeting, monitoring, and timed RPO/RTO drills. Declare recovery successful only when the application delivers committed business capabilities and data has been verified accurate.
