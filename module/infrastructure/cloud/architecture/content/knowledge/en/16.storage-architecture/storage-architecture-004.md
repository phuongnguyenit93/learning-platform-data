# Data Tiering, Lifecycle, and Retention Policies

## 1. Why Does Data Need Multiple Storage Tiers?

Not all data shares the same access frequency, acceptable latency, lifespan, or recovery requirements. A profile avatar may be read continuously; a transaction record needs fast queries in the near term; operational logs may be accessed heavily in the first few days and rarely afterward; closed records may need to be retained for years for reconciliation or legal obligations.

If you store all data on low-latency, high-cost tiers, bills grow with both volume and time. If you move data to the cheapest tier too soon, the application may wait hours to restore an object, pay steep retrieval fees, or miss service latency targets. If you delete solely by data age without checking retention, legal holds, or backups, the system can lose essential records.

**Data tiering** arranges data across storage classes according to access characteristics, performance, durability, availability, and cost. **Data lifecycle** describes how data is created, used, transitioned across tiers, retained, archived long-term, and eventually deleted. **Retention policy** defines how long data or records must be kept, from what starting event, which exceptions apply, and how deletion is proven.

Three related yet distinct decisions:

- Tiering answers: **where should data sit** to satisfy access patterns and cost?
- Lifecycle answers: **how does data change state over time**?
- Retention answers: **how long must data be kept and when is it deleted**?

In the **CLOUD_ARCHITECTURE** module, this is a decision balancing performance, scalability, reliability, security, cost, and operations. It must be grounded in real product data and requirements, not just storage class names.

### Learning Objectives

After this lesson, you can:

1. Classify data by access pattern, latency, size, age, and criticality.
2. Choose hot, warm, cool, cold, or archive tiers based on total cost and retrieval capability.
3. Design lifecycle transitions and expirations so data moves or expires by deterministic rules.
4. Distinguish retention, backups, replicas, archives, and legal holds.
5. Apply retention policies to objects, logs, database exports, and transactional data.
6. Evaluate encryption, IAM, auditing, versioning, deletion, and recovery.
7. Build processes to validate, monitor, and tune storage policies.

## 2. Classify Data Before Choosing a Storage Tier

Do not start by asking "which cloud service is cheapest?" First understand why the data is created and who needs to access it.

### 2.1. Key Classification Dimensions

| Dimension | Question | Example |
|---|---|---|
| **Access frequency** | How often is a read/write performed? | Listing photos are read thousands of times; old logs are rarely queried |
| **Access latency** | How long can users wait? | APIs need milliseconds; archives can take hours to restore |
| **Data size** | Small objects, large files, or many small records? | A few KB of JSON, a few MB of images, several GB of video |
| **Change rate** | Is the data updated frequently? | Sessions change constantly; issued invoices rarely change |
| **Retention** | How long must it be kept? | Caches for minutes; accounting records for years per policy |
| **Durability / availability** | What data loss and downtime are acceptable? | Booking metadata requires stronger protection than regenerable caches |
| **Recoverability** | How fast must recovery be? | Transactional DBs have low RTO; archives allow longer restore times |
| **Sensitivity** | Does it contain PII, payment data, or secrets? | Passports, addresses, logs containing tokens |
| **Residency / sovereignty** | Where is data allowed to reside? | Designated region or jurisdiction |
| **Deletion** | Once no longer needed, how is it removed? | Deleting objects, indexes, replicas, derived copies, and backups by lifecycle |

### 2.2. Grouping by Access Needs

| Data group | Typical characteristics | Storage direction |
|---|---|---|
| **Operational / hot** | Frequent reads/writes, needs low latency | Primary database, high-performance block storage, or hot object tier |
| **Warm** | Periodic access, still needs fast online reads | Database/read replica, standard or infrequent-access object tier |
| **Cool** | Infrequent access, accepts small retrieval fees/latency | Object storage cool/nearline class |
| **Cold / archive** | Rarely accessed, serves on-demand audits/recovery | Archive tier with a restore workflow |
| **Ephemeral** | Temporary data, regenerable or short-lived | Caches, temporary volumes, lifecycle expiration |

Terms like hot/warm/cool/cold are conceptual models. Tier names, minimum storage durations, retrieval latencies, retrieval fees, and transition capabilities vary by provider and storage class. Check pricing tables and service documentation before deciding.

## 3. Tiering Model and Trade-Offs

### 3.1. Illustrative Model

~~~mermaid
flowchart TD
    Create["New data created"] --> Hot["HOT: frequently accessed"]
    Hot -->|Less accessed per threshold| Warm["WARM: periodically accessed"]
    Warm -->|Low latency no longer needed| Cool["COOL: infrequently accessed"]
    Cool -->|Long-term retention only| Archive["COLD / ARCHIVE"]
    Hot -->|Expired and not held| Delete["Delete per policy"]
    Warm -->|Expired and not held| Delete
    Cool -->|Expired and not held| Delete
    Archive -->|Retention period ended| Delete
    Hold["Legal hold / retention lock"] -. "blocks normal policy deletion" .-> Delete
~~~

*Conceptual diagram. Transitions are not strictly one-way; data can be restored or rehydrated back to an online tier. Legal hold/retention lock behavior must be verified against the service's specific semantics.*

### 3.2. Tier Comparison

| Tier | Typical access frequency | Advantages | Trade-offs |
|---|---|---|---|
| **Hot** | Daily or continuous | Low latency, direct access | Higher storage/compute unit cost |
| **Warm** | Periodic, seasonal, or support-driven | Lower cost than hot | Higher retrieval/operation fees, different SLAs |
| **Cool** | Infrequent access while needing online retrieval | Lower storage cost | Retrieval fees, latency, minimum duration, or minimum billable size depending on service |
| **Cold** | Very rare access, mostly for audits/recovery | Low storage cost for multi-year data | Must plan restores, can take hours |
| **Archive / Deep archive** | Almost never accessed in daily operations | Optimized for long-term retention | Slow restores, potential retrieval charges and minimum retention |

Not every object needs to pass through every tier. For example, a log may expire after 30 days without archiving; a 7-year record may transition from hot to cool to archive. Data that must be read immediately during audits may not fit a tier taking hours to restore.

## 4. Choosing Storage Types: Object, Block, File, and Database

Tiering is not limited to shifting objects across storage classes. Data shape and how the application uses it also determine the underlying storage technology.

| Type | Unit of access | Best suited for | Lifecycle considerations |
|---|---|---|---|
| **Object storage** | Object/blob with metadata/key | Images, videos, documents, logs, backups, data lakes | Lifecycles by prefix/tag/age, versioning, storage classes |
| **Block storage** | Block device attached to a VM/workload | Disks for databases, filesystems, boot volumes | Snapshots, volume tiers, resizing, backups, and volume deletion |
| **File storage** | Files/directories via shared protocol | Shared application files, home directories, content workflows | Snapshots, quotas, file retention, directory permissions |
| **Relational database** | Rows/transactions/queries | Bookings, payment ledgers, metadata needing ACID | Partitioning, indexes, archive tables, backup/PITR, and record retention |
| **NoSQL / key-value** | Items/documents/keys or partitions | Sessions, lookups, high-scale workloads | TTLs, partition design, backups, and exports |
| **Cache** | Temporary entries by key | Regenerable sessions/caches, reducing read load | TTLs and eviction; not the default source of truth |
| **Stream / event log** | Records by partition/offset | Events and telemetry with replay within a retention window | Time/size retention, consumer lag, and long-term export |

Object storage generally supports multiple storage classes and lifecycle policies. Hot databases typically need different strategies: time-based partitioning, archive tables, or exports to object storage or a data warehouse. Do not try to move a single database row to a cold tier without accounting for queries, indexes, foreign keys, and application consistency.

## 5. Total Storage Cost: Per-GB Price Is Not Enough

A storage tier with a lower list price can result in higher total cost if data is frequently read, restored, or transitioned.

### 5.1. Cost Components

- **Storage capacity:** GB-months, varying by region, class, redundancy, and usage.
- **Requests/operations:** PUT, GET, LIST, lifecycle transitions, retrieval requests, metadata operations.
- **Retrieval:** fees to read or restore data from cool/archive tiers.
- **Early deletion / minimum duration:** some classes bill a minimum storage duration even if objects are deleted early.
- **Data transfer:** egress, cross-zone/cross-region transfers, replication, and inter-service transfers.
- **Restore/rehydration:** creating temporary online copies, keeping restored copies alive, and operational effort.
- **Monitoring/indexing:** logs, inventories, metadata indexes, catalogs, and observability.
- **Operational cost:** designing policies, handling restores, legal holds, audits, and incidents.

### 5.2. Simple Estimation Formula

\[
Cost_{total} =
Cost_{storage} + Cost_{requests} + Cost_{retrieval}
+ Cost_{transfer} + Cost_{restore} + Cost_{operations}
\]

Hypothetical example comparing two tiers, not a provider quote:

| Monthly component | Tier A (online) | Tier B (cool) |
|---|---:|---:|
| 10 TB capacity | 230 units | 100 units |
| Requests/operations | 10 | 15 |
| Retrieval | 0 | 60 |
| Transfer/other | 10 | 10 |
| **Illustrative total** | **250** | **185** |

In this example, Tier B is cheaper while assumed retrieval stays low. If retrieval rises by 100 units, Tier B totals 285 and Tier A becomes cheaper. Decisions must therefore be based on **measured access patterns**, not storage price alone.

### 5.3. Break-Even Estimate

For steady capacity, you can find the retrieval level where:

\[
StorageSavings \approx RetrievalFees + ExtraOperations + Transfer
\]

This is a simplified break-even point. In practice, add object size distributions, read frequencies, tier minimum durations, restore concurrency, and labor costs. Run monthly/quarterly models across multiple access scenarios.

## 6. Designing Lifecycle Policies

Lifecycle policies automatically apply actions based on data age, prefix, tag, version, or other service-supported conditions. The goal is to minimize manual work and ensure data follows consistent rules.

### 6.1. Common Lifecycle Actions

| Action | Purpose | Questions to answer |
|---|---|---|
| **Transition** | Move objects to another storage class | After how long; are there minimum durations or transition fees? |
| **Expiration** | Delete objects after a period | Is age measured from creation or a business milestone? |
| **Noncurrent version expiration** | Delete older versions | Is history/recovery needed? |
| **Abort incomplete multipart upload** | Clean up abandoned uploads | How long before an upload counts as abandoned? |
| **Delete marker cleanup** | Clean up markers in versioned buckets when appropriate | Does it affect version recoverability? |
| **Archive restore expiry** | Remove temporary online restored copy after a window | Does the original archived object remain intact? |

### 6.2. Illustrative Lifecycle Template

~~~text
Prefix: reports/monthly/

0-30 days: Standard / hot
After 30 days: Cool / infrequent access
After 180 days: Archive
After 7 years: Expire, unless under legal hold

Incomplete multipart uploads: abort after 7 days
Noncurrent versions: retain per separately approved retention
~~~

This is a **hypothetical policy template**, not a universal legal timeframe. The 7-year mark must come from regulations, contracts, and internal policies applicable to the specific record type; it may be shorter or longer.

### 6.3. Example YAML Lifecycle Configuration

~~~yaml
policy:
  name: monthly-report-lifecycle
  scope:
    bucket: reports-prod
    prefix: reports/monthly/
  transitions:
    - after_days: 30
      storage_class: COOL
    - after_days: 180
      storage_class: ARCHIVE
  expiration:
    after_days: 2555
    condition:
      legal_hold: false
  incomplete_uploads:
    abort_after_days: 7
~~~

The schema above is pseudoconfiguration expressing intent. Each cloud provider has its own syntax and semantics; you cannot apply this YAML directly to a bucket without adapting and validating it.

### 6.4. Avoiding Age-Calculation Mistakes

An object may have different dates for creation, modification, transaction completion, case closure, and retention start. **Retention usually must be calculated from an approved business milestone**, not defaulted to `LastModified`.

For instance, a payment record might need 7-year retention from the close of the accounting period. If the object is re-exported daily, a lifecycle based on `LastModified` could stretch retention indefinitely or measure from the wrong date. Store metadata like `retention-start-date`, `record-type`, and `legal-hold` in a way workloads cannot arbitrarily alter.

## 7. Retention Policies: Duration, Purpose, and Exceptions

A retention policy is more than "keep for 5 years." A policy may need to specify:

1. **Data owner:** who is accountable for classification and approving durations.
2. **Data category:** record type, logs, images, events, or personal data.
3. **Purpose:** why data must be kept (operations, contracts, auditing, legal).
4. **Start event:** when the clock starts (creation, contract end, case closure, document issuance).
5. **Retention period:** exact duration and calculation rules.
6. **Disposition:** delete, anonymize, aggregate, or archive upon expiration.
7. **Exceptions:** legal holds, investigations, disputes, or preservation orders.
8. **Evidence:** logs and reports proving the policy was enforced.

### 7.1. Illustrative Retention Matrix

| Data type | Purpose | Clock start | Illustrative policy |
|---|---|---|---|
| Listing cache | Speed up reads | When cached | Minute/hour TTL, regenerable |
| Temporary uploads | Resume uploads or processing | Upon creation | Delete after a few days if incomplete |
| Application debug logs | Short-term troubleshooting | When written | Hot short-term, then expire or retain selectively by event |
| Security audit logs | Investigation and auditing | Per approved audit policy | Keep online/cool or archive for the appropriate term |
| Booking records | Service fulfillment and dispute handling | From defined business milestone | Online during active lifecycle, archive after closure if appropriate |
| Invoices/payment evidence | Accounting, reconciliation, legal obligations | Per record type/applicable rules | Dedicated retention, strict edit/delete controls |
| Marketing analytics | Performance measurement or aggregate analysis | Per purpose and consent/policy | Time-limited, anonymized/aggregated when appropriate |

Timeframes in examples must be confirmed by legal, privacy/data owners, and business stakeholders. Never infer concrete legal obligations from a sample table alone.

## 8. Legal Holds, Retention Locks, and Immutable Storage

### 8.1. Legal Hold

A **legal hold** temporarily suspends deletion or modification of a dataset due to an investigation, dispute, audit, or preservation order. A legal hold can apply by record, object, subject, or time range.

A system needs:

- Authorized roles to place and lift holds.
- Reason, scope, timestamp, requester, and an approval trail.
- A way to locate related copies, exports, replicas, versions, and derived data.
- Mechanisms blocking lifecycle expiration/deletion within the hold scope.
- Periodic review processes to release holds once they expire.

Never allow ordinary service accounts to set or remove legal holds solely via application-supplied metadata.

### 8.2. Retention Lock / Object Lock

Some object stores support mechanisms protecting objects from deletion/modification for a duration, in governance or compliance modes depending on the provider. **Semantics vary**: bypass permissions, extension behavior, version scoping, and bucket configuration differ across providers.

Immutable/WORM storage is valuable for records needing preservation, but misconfiguration can retain data longer than permitted or complicate authorized deletion requests. Before enabling in production, test lifecycles, versioning, legal holds, expiration, and administrator permissions in a controlled environment.

### 8.3. Deleting Data Is Not Just Deleting One Object

A single record may exist across:

- Primary database/object storage.
- Replicas, read models, search indexes, and caches.
- Old versions, soft-delete markers, and multipart uploads.
- Exports, data lakes, warehouses, and integration copies.
- Snapshots, backups, and archives.

Deletion policies must define the scope for each copy and when copies expire. Immutable/retained backups may not delete immediately; document the timeframe until data ages out of backup cycles, while preventing backup restores from resurrecting deleted data without authorization.

## 9. Distinguishing Backups, Replicas, Archives, and Retention

These mechanisms do not replace one another:

| Mechanism | Problem it solves | What does it NOT guarantee? |
|---|---|---|
| **Backup** | Recovering data after accidental delete, corruption, ransomware, or outage | Not necessarily the latest state or directly queryable |
| **Replica** | Increasing availability/reads or maintaining near-real-time copies | Accidental deletes, corruption, or ransomware can propagate to replicas |
| **Archive** | Low-cost storage for rarely accessed data | Does not replace backups/PITR or guarantee fast restores |
| **Retention** | Defining how long data must be kept | Does not create recovery copies on its own |
| **Legal hold / immutability** | Preventing edits/deletes for a scope/period | Does not replace encryption, access control, or backup strategy |

A database with 7-year retention still needs backups/PITR matched to RPO/RTO. An archive retained for 7 years cannot necessarily restore a live database to a consistent point in time.

### 9.1. RPO and RTO

- **Recovery Point Objective (RPO):** maximum acceptable data loss, usually expressed as the time between an incident and the most recent recoverable data.
- **Recovery Time Objective (RTO):** target duration to restore a service/data to a usable state.

Storing multi-year archives does not equal achieving a multi-minute RPO. Design backup frequency, transaction logs/PITR, replication, restore procedures, and real-world testing.

## 10. Lifecycle for Object Storage

Object storage generally fits images, videos, export files, documents, and logs because objects can be managed by keys, metadata, tags, versions, and storage classes.

### 10.1. Prefixes and Tags

Objects can be grouped by:

- Prefix: `uploads/`, `booking-documents/`, `reports/`, `logs/`.
- Tag: `data-classification`, `retention-class`, `owner`, `environment`, `legal-hold`.
- Timestamps/business metadata: `created-at`, `retention-start-date`, `record-closed-at`.

Prefixes are easy to organize and often convenient for policies; tags are more flexible but require controlling who can create/modify tags. Never allow user uploads to arbitrarily set `legal-hold=false` or alter retention metadata if those are governance attributes.

### 10.2. Versioning

Versioning lets you recover objects after accidental overwrites or deletions, but increases storage usage by retaining multiple versions. Lifecycles must address:

- Current versions.
- Noncurrent versions.
- Delete markers.
- Incomplete multipart uploads.
- Object locks/legal holds on the relevant versions.

A delete in a versioned bucket may only insert a delete marker; old versions remain and can continue incurring charges. Understand the provider's exact deletion and retrieval behavior.

### 10.3. Restoring Objects from Archive

Reference workflow:

1. Confirm owner, justification, and authorization to retrieve.
2. Check object/version, retention, hold status, and archive state.
3. Submit a restore request with an appropriate priority/time window.
4. Track restore progress and cost.
5. Once ready, read the data, verify checksum/integrity, and enforce access control.
6. After the access window ends, let the restored copy expire or return per policy.
7. Log an audit trail of requester, object reference, approval, and outcome.

Never promise that an archived object can be read immediately like the Standard tier. Restore duration, priority, and pricing depend on the specific class.

## 11. Lifecycle for Databases and Structured Data

Databases do not always support automatically moving individual rows between hot/cold classes. Strategies include:

### 11.1. Time Partitioning

Partitioning tables by month/quarter/year helps manage historical data, indexes, and archive/drop partition operations.

~~~sql
-- Illustrative PostgreSQL monthly partitioning.
CREATE TABLE booking_events (
    event_id BIGINT NOT NULL,
    booking_id VARCHAR(40) NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    event_type VARCHAR(80) NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE booking_events_2026_11
PARTITION OF booking_events
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
~~~

Adapt this example to your actual database engine and partitioning strategy. Check unique constraints, primary keys, indexes, query pruning, timezones, and maintenance. Never drop a partition solely because the month ended if retention/legal holds have not been verified.

### 11.2. Archive Tables or Exports

Historical data can move to archive tables, object storage, data warehouses, or analytical stores. The workflow must ensure:

1. Identifying the eligible dataset by business milestone.
2. Consistent export (snapshot/CDC/appropriate transaction boundary).
3. Verifying row counts, checksums, keys, and references.
4. Marking/deleting online rows only after the archive copy is verified and readable.
5. Updating historical queries or lookup APIs to know where data lives.
6. Monitoring cost and restore speed.

Avoid uncoordinated "copy then delete" scripts lacking transactions, manifests, or reconciliation. If a job crashes mid-run, you must know which batches completed, which remain, and how to re-run idempotently.

### 11.3. TTL for Naturally Expiring Data

TTLs fit sessions, caches, ephemeral tokens, temporary state, or data with clear business expiration. Avoid simple TTLs for records subject to legal retention or linked to primary records unless related retention rules exist.

TTLs may not delete at the exact second of expiration; many systems run background sweeps with lag. Applications must block use of expired data in business logic even before physical cleanup occurs.

## 12. Tiering Logs, Telemetry, and Audits

Logs usually have time-decaying access patterns: fresh logs need fast queries during incidents; older logs are rarely read yet may be required for audits or investigations.

Reference layout:

| Data age | Location/tier | Purpose |
|---|---|---|
| 0–14 days | Hot log search tier | Incident response, debugging, and alerting |
| 15–90 days | Appropriate log storage/cool tier | Recent event investigation, trends |
| After 90 days | Object/archive per policy | Audits or long-term retention requirements |
| Past approved retention | Expire/delete | Reduce data footprint and cost |

These cutoffs are examples only. Security audit logs, application debug logs, access logs, and analytics data have different purposes and retentions. Do not lump them under one policy, as you risk keeping sensitive data too long or deleting needed evidence too early.

### Logs Can Contain Sensitive Data

Before archiving logs, mask/redact tokens, passwords, payment data, and PII; restrict search/restore permissions; encrypt and audit access. Moving sensitive logs to an archive does not make them less sensitive.

## 13. Security and Data Governance Across All Tiers

Tiering does not reduce data protection obligations. Controls must follow data throughout its lifecycle:

- **Classification:** public, internal, confidential, restricted, or the organization's taxonomy.
- **Encryption at rest:** use storage encryption; manage keys, rotation, and decrypt permissions.
- **Encryption in transit:** TLS or equivalent during moves, restores, and replication.
- **IAM:** separate read, write, delete, restore, and retention-admin permissions by role.
- **Network access:** private endpoints, controlled egress paths, and access policies.
- **Auditing:** track reads, downloads, restores, tier changes, deletes, retention edits, and hold placement/removal.
- **Integrity:** checksums, versioning, object locks, or verification as required.
- **Data minimization:** retain no more data than needed for the purpose and duration.
- **Residency:** regions and replication targets compliant with organizational and legal rules.

Specifically separate **data read**, **data delete**, and **retention/hold administration** permissions. A routine operations account should not simultaneously be able to delete immutable backups or lift legal holds without break-glass procedures and auditing.

## 14. Observability and Cost Management

A lifecycle policy that runs cleanly from a technical standpoint may still miss cost or business goals. Monitor:

| Metric | Meaning | Signal to watch |
|---|---|---|
| Capacity by class | Which tiers hold data | Continuous hot growth may mean lifecycles are not running |
| Object/row count by age | Scale of historical data | Data is not expiring as expected |
| Transition counts / failures | Tier moves and errors | Misconfigured selectors or ineligible objects |
| Retrieval volume/cost | How much cool/archive data is being read | Tier is too cold for actual access patterns |
| Restore times and failures | Ability to retrieve data | Whether RTO is being met |
| Versioned bytes / delete markers | Capacity held by old versions | Deleting objects does not reduce bills |
| Incomplete upload volume | Abandoned multipart upload waste | Missing or misconfigured cleanup rules |
| Retention/hold exceptions | Records blocked from deletion | Legal holds lacking owners or overdue for review |
| Cost per retained TB/year | Holding cost | Comparing classes, redundancy, requests, and transfers |

Alert when objects past retention remain unexpectedly without a hold; when hot capacity spikes; when restore durations exceed RTO; when retrieval fees or egress surge; when lifecycle transitions/expirations fail; or when policies, locks, or retention metadata change outside approved workflows.

## 15. Case Study: Data Lifecycle for a Booking Platform

**Context:** an accommodation booking app stores bookings, payment receipts, listing photos, operational logs, and exported reports. Photo volume grows quickly; logs need fast querying during incidents but are rarely read after a few weeks; transactional records must be kept per approved policy. The system needs to cut costs while keeping records searchable and recoverable.

### 15.1. Classification and Storage Direction

| Dataset | Access pattern | Reference storage design |
|---|---|---|
| Active bookings | Frequent reads/writes | Primary relational DB, backups/PITR, and replicas per RTO/RPO |
| Completed bookings | Rare updates, occasional lookups | Keep in DB during operational window; consistent archive export for long-term history if needed |
| Payment evidence/invoices | Reconciliation access, dedicated retention needs | Protected store, auditing, retention, and holds by record type |
| Popular listing photos | Frequent GETs | Hot/standard object tier, CDN, and versioning if needed |
| Inactive listing photos | Rarely read, but must recover within a defined window | Cool tier once listing has been closed long enough |
| Application debug logs | Heavy reads during incidents | Short-term hot logs, then expire or selectively archive |
| Security audit logs | Rarely read, high investigative value | Integrity/access-controlled storage with dedicated retention |
| Exported reports | Read shortly after creation, then rarely | Hot → cool → archive; delete at policy expiration |

### 15.2. Lifecycle Flow for Listing Photos

~~~mermaid
flowchart TD
    Upload["Upload listing photo"] --> Validate["Validate, scan, classify"]
    Validate --> Hot["Hot object + CDN"]
    Hot --> Active{"Is listing active?"}
    Active -->|Yes| Hot
    Active -->|Ineligible for display| Cool["Cool tier after inactivity period"]
    Cool --> Restore{"Reuse requested?"}
    Restore -->|Yes| Rehydrate["Restore / move online"]
    Rehydrate --> Hot
    Restore -->|No, retention expired| Hold{"Legal hold?"}
    Hold -->|Yes| Archive["Retain under hold"]
    Hold -->|No| Delete["Delete object, versions, and derived copies"]
~~~

Before deleting photos, check active listings, cache/CDN, thumbnails, resized variants, old versions, and backup copies. If photos contain personal data, deletion requests may apply to derived copies per policy.

### 15.3. Retention Flow for Transaction Records

1. The payment service records the transaction and immutable reference per ledger design.
2. Records are classified and stamped with an approved `retention-start-date`.
3. Frequently accessed records remain in a restricted online layer.
4. Once the operational period ends, records can be batch-exported/archived with a manifest and checksums.
5. If a dispute arises, a legal hold blocks expiration for that exact scope.
6. Once holds are lifted and retention ends, a disposition job deletes in-scope copies and logs an audit record.

Do not treat copying to an archive as permission to delete the source before the export is verified. Nor should an archive be treated as a full backup for the ledger system.

### 15.4. Acceptance Criteria

- Every dataset has an owner, classification, access pattern, and retention start event.
- Tier transitions do not push application latency past SLOs; restores meet committed times.
- Held data cannot be deleted by lifecycle expiration.
- Exports/archives have manifests, checksums, and tested read-back procedures.
- Backups/PITR are designed to separate RPO/RTO targets, distinct from archives.
- Secrets/PII are protected in logs and archives.
- Dashboards track capacity, retrievals, restores, transition failures, and cost per data class.

## 16. Designing Safe Tiering and Deletion Workflows

A sound policy needs a pilot and verification stage before broad rollout:

1. **Inventory:** collect data lists, ages, prefixes/tags, sizes, versions, and access metrics.
2. **Classify:** assign data category, owner, sensitivity, retention start date, and hold status.
3. **Model:** estimate storage, requests, retrievals, transfers, restores, and operational costs across scenarios.
4. **Pilot:** apply the policy to a small prefix/bucket/partition using test or low-risk data.
5. **Verify transition:** confirm actual storage classes, permissions, latency, and billing.
6. **Verify restore:** restore a sample, verify checksums/content/metadata, and measure elapsed time.
7. **Enable expiration:** turn on deletion only after policies, holds, and recovery have been verified.
8. **Monitor:** track lifecycle failures, exceptions, retrievals, and costs; review periodically.

### 16.1. Idempotent Batch Deletion

For database archiving, each batch should have a manifest recording partition/key range, count, checksum, export timestamp, copy status, verification status, and disposition. Jobs must be idempotent so re-runs neither create duplicate uncontrolled copies nor delete unarchived data.

Example state machine:

~~~text
DISCOVERED
  -> EXPORTED
  -> VERIFIED
  -> ELIGIBLE_FOR_DELETE
  -> DELETED

Branches:
VERIFY_FAILED -> RETRY / MANUAL_REVIEW
LEGAL_HOLD     -> ON_HOLD
~~~

Never jump directly from `DISCOVERED` to `DELETED`. `VERIFIED` evidence must prove the archive copy is genuinely usable, not merely that a file exists.

## 17. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Choosing tiers by price/GB alone | Retrieval and operation fees raise total cost | Use real access patterns and a total-cost model |
| Archiving data that still needs low latency | Slow APIs or unexpected restores | Define access SLAs and hot read paths |
| Deleting by `LastModified` without business context | Retention starts at the wrong date or extends forever | Store `retention-start-date` from an approved event |
| Treating archives as backups | Cannot recover DB to a point in time | Design separate backups/PITR and RPO/RTO |
| Enabling expiration as soon as lifecycle is created | Accidental deletion of active data, versions, or unarchived items | Pilot, inventory, restore test, and require approval |
| Forgetting noncurrent versions / delete markers | Old data stays around and keeps incurring charges | Define explicit lifecycles for versions and markers |
| Ignoring retrieval/egress fees | Bills spike during audits or restores | Estimate frequency, size, and access regions |
| Using self-declared tags for legal holds | Users can alter or bypass holds | Use protected hold/lock mechanisms with auditing |
| Keeping sensitive logs in archives without encryption/ACLs | Data exposure despite rare access | Enforce classification, encryption, IAM, and redaction |
| Deleting sources before verifying archives | Data loss when copies fail or are incomplete | Require export manifests, checksums, and read-back before disposition |
| Assuming TTL deletes at the exact instant | Expired data can remain physically present | Enforce expiry in application logic and account for sweep lag |

## 18. Storage Architecture Review Checklist

### Classification and Tiering

- [ ] Data is classified by owner, purpose, sensitivity, access frequency, and latency.
- [ ] Hot/warm/cool/archive tiers match access patterns and retrieval SLAs.
- [ ] Storage, requests, retrievals, transfers, restores, and operations are costed.
- [ ] Provider minimum durations, minimum billable sizes, and transition fees are evaluated.
- [ ] Databases, objects, blocks, files, caches, and streams have data-appropriate lifecycle designs.

### Lifecycle and Retention

- [ ] Transitions/expirations tie to defined business milestones.
- [ ] Noncurrent versions, delete markers, and multipart uploads have policies.
- [ ] Retention periods specify owner, purpose, start event, disposition, and evidence.
- [ ] Legal holds/retention locks cannot be altered or lifted by ordinary workloads.
- [ ] Deletion covers replicas, indexes, caches, exports, and related copies per policy.
- [ ] Policies were piloted; expiration is enabled only after verifying scope.

### Backups and Recovery

- [ ] Backups/PITR are independent of archives and have RPO/RTO targets.
- [ ] Restores have been tested, checksums/contents verified, and durations measured.
- [ ] Manifests and batch states exist for exports/archives.
- [ ] Reconciliation and manual review procedures exist if copy/verify/delete fails.

### Security and Operations

- [ ] Encryption at rest/in transit, key management, IAM, and network access are designed.
- [ ] Read, delete, restore, retention administration, and legal hold permissions are separated.
- [ ] Audit logs cover access and policy changes.
- [ ] Dashboards track capacity by class, transitions, retrievals, restores, retention exceptions, and cost.
- [ ] Owners and runbooks exist for legal holds, emergency restores, lifecycle failures, and deletion requests.

## 19. Practice Exercise

**Context:** a booking platform stores five datasets: active bookings, completed bookings, listing photos, debug logs, and payment evidence. Photos grow 30% per quarter; logs are heavily queried for the first 10 days; reconciliation teams may look up certain receipts at any time; a subset of records may enter legal disputes. Hot object storage costs are climbing.

Design the policies:

1. Classify each group by access frequency, latency, sensitivity, and retention purpose.
2. Choose hot/warm/cool/archive or database/backup tiers; explain trade-offs.
3. Define lifecycle transitions and expirations for photos, logs, and exports.
4. Identify retention start events for bookings and payment evidence; state who approves durations.
5. Design legal holds and prevent expiration jobs from deleting held records.
6. Describe how to export historical bookings to an archive with manifests, checksums, and read-back.
7. Distinguish backups/PITR, replicas, and archives; set RPO/RTO for operational data.
8. Estimate total cost including storage, requests, retrievals, egress, restores, and logs.
9. Define required dashboards/alerts and how to handle emergency restores.
10. Write acceptance criteria before enabling automatic expiration.

**Self-check hints:** Do not archive photos solely by age if listings are still active and need fast access. Do not delete bookings based on export date. Under a legal hold, identify all related versions and copies. Having an object in an archive does not prove you have a backup; test restores and verify integrity.

## 20. Key Takeaways

**Tiering** optimizes where data lives by access pattern and cost; **lifecycle** automates moving/deleting data by rules; **retention** defines how long data must stay and which exceptions block deletion. All three decisions must stem from data classification, business milestones, and real retrieval needs.

Archives do not replace backups, replicas do not replace versioning/retention, and deleting a single object does not delete every copy. Sound design pairs appropriate tiers, controlled lifecycles, legal holds, encryption, IAM, auditing, RPO/RTO, and restore testing. Enable expiration only after verifying scope, confirming saved copies, and proving data is handled strictly per policy.
