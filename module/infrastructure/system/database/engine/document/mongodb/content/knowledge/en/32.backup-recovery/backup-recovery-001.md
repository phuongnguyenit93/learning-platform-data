# Defining RPO, RTO, and Recovery Scope in MongoDB

## 1. Learning Objectives

A successful backup does not automatically guarantee that the system will recover on time. MongoDB may have an intact snapshot that is too old, is missing data from related collections, or lacks the encryption keys needed for decryption. Even when a restore operation finishes, that still does not mean the application can accept orders, reconcile payments, and return results to users.

This lesson belongs to **Database Engine Document MongoDB → Backup and Recovery → Defining RPO, RTO, and Recovery Scope**. Its focus is determining **how much data loss is acceptable**, **how long recovery is allowed to take**, and **which data and business relationships must be restored**.

After this lesson, learners can:

- Explain RPO and RTO, and distinguish them from backup frequency, backup retention, PITR window, availability, and actual recovery time.
- Calculate RPO/RTO using an actual timeline instead of relying solely on whether a backup job succeeded.
- Set different targets for orders, payments, inventory, customer profiles, catalog, analytics, and cache.
- Choose the scope across documents, collections, databases, tenants, clusters, regions, and consistency groups.
- Distinguish replica set failover from recovering logical corruption.
- Evaluate Atlas scheduled snapshots/Continuous Cloud Backup, `mongodump/mongorestore`, filesystem snapshots, and event-log-based approaches.
- Identify the limitations of backups on replica sets/sharded clusters and selected collection restores.
- Build runbooks for accidental deletion, cluster restore, region outage, application bugs, ransomware, and delayed detection.
- Verify consistency across GridFS, Search indexes, change streams, outbox, payment providers, and systems outside MongoDB.
- Measure actual RPO/RTO during restore drills and prove that the chosen approach meets business requirements.

> **Most important takeaway:** RPO/RTO are **business targets that must be verified**, not features that automatically appear after enabling a replica set, Cloud Backup, or a scheduled `mongodump`.

---

## 2. Business Example: An Accidental Delete of Orders

Suppose the application has these collections:

```text
commerce
  orders
  payments
  inventoryReservations
  shipments
  outboxEvents
  customers
  products
```

An erroneous script runs:

```javascript
db.orders.deleteMany({
  createdAt: {
    $gte: ISODate("2026-11-14T00:00:00Z")
  }
});
```

The script deletes many valid orders. The replica set keeps running because the command is treated as a valid write operation and is replicated. The payment provider may already have captured funds, the broker may already have published `OrderPlaced`, and the inventory service may already have reserved stock.

The real questions that need answers:

1. At what exact time was the first bad command executed?
2. Is there a **clean recovery point** before the bad command?
3. Should we restore the entire cluster or only the affected orders?
4. How will valid transactions after the accidental deletion timestamp be preserved?
5. After restoring orders, will payments/inventory/outbox still be consistent?
6. Within how long must the checkout feature return to service?
7. Who has the authority to approve rolling back data that customers have already interacted with?

Those are the three dimensions of **RPO, RTO, and recovery scope**, not just the question "how do you write the restore command".

---

## 3. RPO: Maximum Permissible Data Loss

**Recovery Point Objective (RPO)** is the maximum acceptable amount of data loss, typically expressed as the time between an incident timestamp and the nearest consistent, recoverable data point.

For example, the business chooses:

```text
RPO(orders) = 5 minutes
```

An incident occurs at 14:00:00; the nearest **usable** recovery point is 13:58:30.

\[
\text{Actual RPO gap}
=T_{\text{incident}}-T_{\text{last usable recovery point}}
\]

\[
14{:}00{:}00-13{:}58{:}30
=90\ \text{seconds}
\]

Under the condition that all changes after the recovery point are treated as potential loss, the actual gap is **1 minute 30 seconds**, which is within the 5-minute RPO.

### 3.1. RPO Is Not Backup Frequency

If snapshots are taken only every 6 hours without PITR and the latest job succeeded at 12:00, an incident at 17:59 can force recovery back to 12:00 — nearly **6 hours of changes** absent from the restored copy.

A 6-hour backup frequency does not guarantee RPO = 6 hours in all cases because:

- A job may fail.
- A snapshot has not completed or been copied to safe storage.
- A snapshot cannot be restored.
- KMS/decryption keys are missing.
- The backup has consistency errors.
- Corruption began before the latest snapshot.
- The infrastructure region holding both source and backup is lost.

Conversely, with Continuous Cloud Backup/PITR and the necessary history, you can pick a point between two snapshots.

### 3.2. What Does RPO = 0 Mean?

RPO = 0 is the target of losing no acknowledged valid writes under defined failure scenarios. This is a very strict goal; do not promise RPO = 0 merely because you have:

- Three replica set nodes.
- `writeConcern:"majority"`.
- A Secondary in another region.
- Continuous backup enabled.

You must account for durability, consistency, failure domains, log capture, retention, external system state, and recovery procedures.

### 3.3. Technical RPO Differs from Final Business Loss

If MongoDB rolls back 2 minutes but the payment provider still stores all transaction IDs, you can **reconstruct** part of the lost state via reconciliation. However, the technical RPO of the restore itself is still 2 minutes; final business loss after recovery may be lower if reconstruction succeeds.

### 3.4. Choose the Appropriate Incident Timestamp

In a cluster outage at 14:00, the incident timestamp is usually clear. However, with **delayed-detection logical corruption**, the safe point must be **before the first bad operation**, which could be many hours before detection. Never automatically pick "5 minutes before the alert" as the recovery point.

---

## 4. RTO: Maximum Time Until Service Resumes

**Recovery Time Objective (RTO)** is the maximum allowed time from the defined incident start timestamp until system functionality **reaches a defined ready state**.

Example:

```text
RTO(checkout) = 30 minutes
```

Timeline:

```text
14:00  Incident starts
14:04  Alert received and acknowledged
14:10  Incident commander selects recovery plan
14:12  Restore begins
14:31  MongoDB restore job completes
14:36  Indexes, network, and secrets are ready
14:40  Business validations complete
14:43  Checkout API opens traffic and processes requests successfully
```

**Actual recovery time = 43 minutes**, missing the 30-minute RTO.

### 4.1. Why Not Count the 19-Minute Restore as RTO?

From 14:12 to 14:31 is only the **time to restore database bytes**. Customers still cannot place orders because relationships, indexes, and the application must be verified.

### 4.2. Components of RTO

| Phase | Required Work |
|---|---|
| Detect | Alerting, identifying outage/corruption |
| Decide | Choosing failover, restore, or selective repair |
| Approve | Approving recovery point and data loss |
| Provision | Creating target cluster/storage/network |
| Restore | Loading snapshot/logs or restoring collection |
| Rebuild | Indexes, Search/Vector Search, caches |
| Validate | Checking data and business invariants |
| Cutover | DNS/connection strings/traffic routing |
| Reconcile | Payments, broker, outbox, external effects |
| Ready | Functionality meets business/SLO criteria |

### 4.3. RTO Must Clearly Define "Ready"

"MongoDB responds to `ping` successfully" is not enough. For checkout, it must be able to:

- Create orders and reserve inventory accurately.
- Avoid double-charging.
- Authenticate customers.
- Avoid re-sending unintended side effects.
- Meet error rate/latency thresholds.
- Satisfy minimum business constraints.

You can set **two RTOs**:

```text
RTO critical checkout: 30 minutes
RTO all services:      4 hours
```

A read-only catalog may recover before analytics/reports, but it must not be called **full recovery** while required functions are still down.

---

## 5. Distinguishing Commonly Confused Metrics

| Concept | Question | Unit/Example |
|---|---|---|
| RPO | What is the maximum data loss? | 5 minutes |
| RTO | What is the maximum time until service resumes? | 30 minutes |
| Actual RPO | Actual data gap after recovery? | 90 seconds |
| Actual recovery time/RTA | Actual time until ready? | 43 minutes |
| Snapshot frequency | How often are backups taken? | 6 hours |
| Backup retention | How long are backup copies kept? | 30 days |
| PITR window | Within what range can a recovery point be chosen? | 7 days |
| Availability | Uptime per SLO? | 99.9% |
| Integrity | Is the data accurate after restore? | No missing payments |

### 5.1. Low RPO, High RTO

Snapshot + PITR lets you pick a point close to the incident, but a large cluster can take many hours to restore and rebuild indexes.

### 5.2. High RPO, Low RTO

A snapshot every 24 hours may restore very quickly, but loses many changes written after the snapshot.

### 5.3. There Is No "Free and Best in Every Dimension" Option

Low RPO typically requires continuous backup/log retention, storage, and monitoring. Low RTO typically requires pre-provisioned recovery capacity, automation, fast networking, on-call staff, and regular drills.

---

## 6. Classifying Data by Criticality

An application might have an illustrative matrix:

| Domain | Example RPO | Example RTO | Why |
|---|---:|---:|---|
| Orders | 5 minutes | 30 minutes | Revenue/fulfillment |
| Payments | Near 0 per policy | 30 minutes | Financial reconciliation |
| Inventory reservations | 5 minutes | 30 minutes | Prevent overselling |
| Customer account | 15 minutes | 2 hours | Account permissions/status |
| Product catalog | 1 hour | 4 hours | Can re-import from CMS/ERP |
| Reviews/comments | 15 minutes | 4 hours | User-generated content |
| Analytics projection | 24 hours | 8 hours | Recompute from source |
| Cache/search index | Rebuildable | 4 hours | No need to preserve every index byte |

**These are illustrative numbers**, not MongoDB commitments. Business owners must confirm which data can be lost/reconstructed, acceptable disruption levels, and legal obligations.

### 6.1. BIA (Business Impact Analysis) Questions

- How much revenue is lost by losing 5 minutes of orders?
- Are there financial transactions whose audit records must never be lost?
- Which changes can upstream/providers replay?
- Which features must reopen first?
- Is read-only mode acceptable?
- Does losing user content carry legal consequences?
- Who approves data rollback or compensation?

### 6.2. Tiered Recovery Classification

You can divide into:

- Tier 0: critical transactional state.
- Tier 1: accounts/catalog/operational data.
- Tier 2: reporting/search projections.
- Tier 3: temporary/cache data.

Tiers only have meaning when paired with approved **RPO/RTO and validation criteria**.

---

## 7. Recovery Scope Is a Multi-Dimensional Decision

A request saying "restore MongoDB" is not enough. You need to specify:

| Dimension | Options |
|---|---|
| Granularity | Field/document, collection, database, tenant, cluster |
| Time | Snapshot, PITR point, before bad write |
| Infrastructure | Same/new cluster, different project, different region |
| Consistency | Collections in the same transaction/bounded context |
| Binary data | GridFS files/chunks, external object storage |
| Downstream | Broker, cache, search index, analytics |
| Security | Users/roles, certificates, KMS, secrets |
| Software | MongoDB version/FCV, app schema, driver |
| Readiness | Read-only, critical functions, full service |

### 7.1. Document-Level

A customer had `loyaltyPoints` updated incorrectly, but their address was validly updated after the snapshot. Restoring the **entire old document** would overwrite the address update. Instead, extract the value to fix, reconcile events, and conditionally update only the target field.

### 7.2. Collection-Level

The `products` collection was dropped. Restore the collection into a new namespace, then diff/merge. You must check related collections such as `categories`, `inventory`, `priceRules`, and indexes.

### 7.3. Database-Level

A tenant with its own dedicated database may be convenient to restore separately, yet it may still have references in shared databases or external systems.

### 7.4. Tenant-Level

In shared collections using `tenantId`, restoring one tenant requires finding all entity relations, assets, payments, background jobs, and unique constraints. It is not as simple as picking a single collection name.

### 7.5. Cluster/Region-Level

You must restore cluster data, topology, configuration, and traffic routing. With a new region, this also includes private endpoints, DNS, firewalls, TLS, KMS keys, IAM, and integrations.

---

## 8. Consistency Group Between Orders and Payments

Example:

```javascript
// orders
{
  _id: "ORD-1001",
  status: "PAID",
  paymentId: "PAY-1001",
  total: 500000
}

// payments
{
  _id: "PAY-1001",
  orderId: "ORD-1001",
  status: "CAPTURED",
  amount: 500000
}
```

If you restore `orders` to before payment capture without restoring/reconciling `payments`, the data becomes inconsistent.

A consistency group might include:

```text
orders
payments
inventoryReservations
shipments
outboxEvents
invoiceMetadata
```

You do not necessarily have to restore every collection to the exact same timestamp if reliable reconciliation exists, but you must **make an explicit decision**.

### 8.1. External Systems

MongoDB backups do not automatically roll back:

- Payment gateways that already captured funds.
- Message brokers that already emitted events.
- Email/notification providers that already sent notifications.
- Object storage that already saved or deleted files.
- Shipping services that already created waybills.

This is why **reconciliation and idempotency** must be part of the recovery scope.

### 8.2. Smaller Scope Can Sometimes Be Harder Than Larger Scope

Restoring an entire cluster can more easily guarantee database-level consistency at a single timestamp, though it rolls back many good writes. Selective repair of a single field touches fewer bytes, yet demands auditing, merging, and concurrency control.

---

## 9. A Replica Set Does Not Replace Backups

### 9.1. High Availability Differs from Data Recovery

A replica set keeps operating when a node goes down, through replication and election when eligible.

```text
Primary -> replication -> Secondary A
        -> replication -> Secondary B
```

If the primary fails while the data is still valid, failover may suffice; **there is no need to roll back to a snapshot**.

### 9.2. Accidental Deletions Still Replicate

```javascript
db.orders.deleteMany({});
```

A majority-acknowledged delete can still be an erroneous business operation. Secondaries also receive the change and do not retain historical versions to undo it via election alone.

### 9.3. `writeConcern:"majority"` Does Not Create a Backup

Majority write concern governs write acknowledgment within the replica set; it does not create an independent copy to protect against logical corruption or ransomware.

### 9.4. The Oplog Has a Finite Window

The oplog is used for replication/change streams and does not store history indefinitely. Without a backup mechanism and properly managed oplog history, you cannot automatically "time travel" to any arbitrary point in time.

---

## 10. Backup Methods and Recovery Capabilities

| Method | Strengths | Limitations |
|---|---|---|
| Atlas scheduled snapshots | Managed backup and retention | RPO depends on snapshot points |
| Atlas Continuous Cloud Backup/PITR | Choose a point within restore window | Requires tier/feature and restore workflow |
| `mongodump/mongorestore` | Logical dump, selectable namespaces | No built-in PITR; slow for large restores |
| `mongodump --oplog` | Consistent full replica set dump when supported | Only oplog within dump window; no arbitrary PITR |
| Filesystem snapshots | Block-level recovery can be fast | Journal/volume/shard consistency |
| Atlas/Ops Manager | Backup automation/policy | Depends on deployment/edition |
| Event log + snapshots | Replay good business events | Requires ordering/dedup/idempotency |
| Replication | High availability | Does not protect against bad writes |

Effectiveness must be measured against your dataset/topology and tool versions. No single row in the table automatically guarantees RPO = 1 minute / RTO = 15 minutes.

---

## 11. Atlas Cloud Backup and Continuous Cloud Backup

### 11.1. Scheduled Snapshots

Atlas Cloud Backup creates snapshots according to a backup policy and retention schedule. For eligible clusters, operators can select a snapshot point to restore from.

According to current documentation, managed Cloud Backup in the described scope is primarily for **Dedicated M10+**; Free clusters do not have managed Cloud Backup like Dedicated clusters. Verify specific tiers and features before designing an SLA.

### 11.2. Continuous Cloud Backup/PITR

Continuous Cloud Backup combines snapshots and history so you can select a **date/time or oplog timestamp** within the restore window. The MongoDB Atlas Architecture Center describes the ability to achieve an RPO as low as about **1 minute** under suitable conditions; do not interpret that as a guarantee that every cluster/incident has an actual RPO of 1 minute.

### 11.3. Selective Database/Collection Restore

Atlas supports restoring **selected databases or collections** from a snapshot or Continuous Cloud Backup in supported environments.

**Important:** Atlas documentation notes that selective restore is **not designed to reduce RTO**, and can take **longer than a full cluster restore**. Do not assume "fewer collections means it must be faster."

### 11.4. Create as New vs Overwrite Existing

- **Create as new:** restores data into a new namespace on name collision, supporting diff/merge workflows.
- **Overwrite existing:** overwrites selected namespaces, which can lose writes on the target.

For accidental deletion incidents, prefer restoring into an **isolated cluster/namespace** for verification first.

### 11.5. Limitations of Selective Restore

Per current MongoDB docs, there are limitations regarding:

- MongoDB Search indexes: selected restore does not restore Search indexes; they must be rebuilt.
- Individual time-series collection restores.
- Certain Queryable Encryption collections.
- Views, NVMe clusters, or specific encryption/network conditions.
- Disk space and concurrent restore jobs.

Before operating, check the docs for your exact deployment and version.

### 11.6. Full Snapshots and Search Indexes

A full snapshot can restore **Search index definitions**, but Search index data generally must undergo **initial sync/rebuild** by the search process. Search endpoints may take longer to become operational even after CRUD is ready.

### 11.7. Restore Target

Atlas documentation recommends preventing client operations on the target being restored. Restoring to a **new cluster** and then cutting over typically reduces production impact and preserves the source for forensics.

---

## 12. Logical Backup with `mongodump` and `mongorestore`

### 12.1. Backing Up a Collection in a Lab

```bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --db=shop \
  --collection=products \
  --out=./shop-products-backup
```

Run this in a terminal using MongoDB Database Tools, not `mongosh`. If writes continue during the dump, the output does not automatically guarantee database-wide consistency.

### 12.2. Restoring to a Temporary Namespace

```bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --nsInclude="shop.products" \
  --nsFrom="shop.products" \
  --nsTo="recovery.products" \
  ./shop-products-backup
```

These URIs and paths are examples. You must verify the actual source/target/dump before running. Do not use `--drop` on a production target without an approved plan, as it deletes target collection data before restoring.

### 12.3. When Is It Suitable?

- Exporting a collection before migration.
- Restoring a namespace to staging to extract data.
- Supplemental backup for small/medium datasets.
- Reconciliation and comparing documents.

### 12.4. When Is It Insufficient?

You cannot assume a multi-TB logical dump will meet very low RPO/RTO targets. Restoring requires loading BSON, building indexes, network/disk resources, and validation.

### 12.5. Compatibility

Database Tools and source/target MongoDB Server versions have constraints based on major version/FCV. Do not assume a dump from a newer version can be restored to an arbitrary older server.

---

## 13. `mongodump --oplog` Is Not Arbitrary PITR

### 13.1. What Is It For?

If a full replica set dump runs while the system is still receiving writes, `--oplog` captures oplog operations that occurred **during the dump**. When restoring with `--oplogReplay`, the tool can bring the data to a consistent state per its supported mechanism.

### 13.2. Full Replica Set Dump Example

```bash
mongodump \
  --uri="$SOURCE_REPLICA_SET_URI" \
  --oplog \
  --archive=./replica-set.archive.gz \
  --gzip
```

Restore to an **isolated** target:

```bash
mongorestore \
  --uri="$TARGET_REPLICA_SET_URI" \
  --archive=./replica-set.archive.gz \
  --gzip \
  --oplogReplay
```

### 13.3. Key Limitations to Remember

- `--oplog` is for a **full replica set dump**; it cannot be combined arbitrarily with `--db`, `--collection`, or `--query`.
- The same full `--oplogReplay` approach cannot be used on a sharded cluster.
- Running `mongodump --oplog` against `mongos` does not turn it into cluster-wide PITR for a sharded cluster.
- DDL/role changes or FCV/time-series format conversions can cause issues depending on the Database Tools version.
- Atlas Free/Flex tiers have unsupported `mongorestore` options, including `--oplogReplay` per documentation.

### 13.4. `--oplogReplay` Is Not Arbitrary PITR

The tool replays oplog entries **recorded during the dump itself**; it does not provide continuous history to restore to an arbitrary timestamp hours or days later. True PITR requires a base snapshot and log capture/retention designed for that goal.

---

## 14. Filesystem Snapshots and Sharded Consistency

### 14.1. Block-Level Snapshots

Storage snapshots can be created faster than logical dumps, but consistency depends on the MongoDB journal, storage volumes, file layout, and proper procedure.

Do not copy a subset of data files from `dbPath` while MongoDB is writing and treat it as a consistent backup.

### 14.2. Sharded Clusters Have Multiple Components

```text
mongos
  |---- Shard A replica set
  |---- Shard B replica set
  |---- Shard C replica set
  |---- Config server replica set
```

Backups must account for all shards and config metadata. Snapshotting Shard A at 13:00 and Shard B at 13:15 may fail to reflect a globally consistent state.

### 14.3. Balancer, Migrations, and Distributed Transactions

Chunk migrations, resharding, and cross-shard transactions complicate manual backups. MongoDB documentation for self-managed sharded filesystem backups outlines steps to stop writes/the balancer, lock, and take snapshots in the proper sequence.

### 14.4. Choosing the Right Solution

If you lack the capacity to engineer snapshot consistency on a sharded deployment, prefer a MongoDB-supported managed backup solution over manually stitching together dumps that lack a global recovery point.

### 14.5. Topology Compatibility

Sharded cluster restores also depend on shard/config configuration, target version, and shard topology. Check Atlas snapshot restore limitations when target topology changes before committing to an RTO.

---

## 15. Delayed-Detection Corruption: Choosing a Clean Point

Timeline:

```text
13:55:07 bad script begins deleting/corrupting data
13:55:20 many more bad writes occur
14:10:00 system finally detects the issue
```

If you only restore to "5 minutes before detection" (14:05), the data still contains bad writes from 13:55. The clean point may need to be **13:55:06** or earlier.

### 15.1. Why Picking an Older Point Has a Cost

During the 15 minutes from 13:55 to 14:10, other orders/payments may have been written legitimately. A full-cluster rollback to 13:55 risks losing good writes.

### 15.2. Strategies

| Strategy | Pros | Risks |
|---|---|---|
| Full PITR before bad write | Easy to reason about clean database state | Rolls back good writes |
| Selective collection restore | Narrower scope | Easy to misalign relationships |
| Temporary restore then extract docs | Preserves current data | Complex merge logic |
| Compensating repair | Preserves many good writes | Repair script could also have bugs |
| Replay good business events | Can reconstruct state | Needs reliable log and dedup |

### 15.3. Do Not Replay All Operations After the Clean Point

If you apply the entire oplog after the clean point, the bad delete will simply execute again. You must selectively replay good events and perform business reconciliation.

### 15.4. RPO Reporting Must Be Honest

If a full rollback loses 15 minutes of good writes, do not report "1-minute RPO" just because the PITR service theoretically supports closely spaced points. Record actual loss/reconstructed events and residual gaps.

---

## 16. Document-Level Repair Without Losing Valid Updates

Before the incident:

```javascript
{
  _id: "CUS-101",
  loyaltyPoints: 250,
  addressVersion: 3
}
```

A bad script sets `loyaltyPoints:0`, and afterward the user updates their address to version 4. Restoring the entire old document would lose the address update.

Instead:

1. Restore the backup into a temporary namespace.
2. Retrieve the pre-error `loyaltyPoints` value.
3. Reconcile point addition/deduction transactions after that timestamp.
4. Update only `loyaltyPoints` conditionally/with version checks.
5. Record a recovery ticket and audit trail.

An **illustrative example — do not run without calculating the exact point balance**:

```javascript
const result = db.customers.updateOne(
  {
    _id: "CUS-101",
    loyaltyPoints: 0
  },
  {
    $set: {
      loyaltyPoints: 250,
      recoveryTicket: "INC-2026-101"
    }
  }
);

print(result.modifiedCount);
```

This is why **single-field scope** sometimes requires more complex business auditing than restoring an entire collection.

---

## 17. GridFS Is a Consistency Group

GridFS stores files across:

```text
fs.files  -> metadata
fs.chunks -> binary chunks
```

If you restore only `fs.files` without chunks, file downloads break. If you restore only chunks without metadata, the driver cannot locate file contents normally.

There may also be:

```text
invoiceMetadata
assetVersions
assets.currentFileId
fs.files
fs.chunks
```

After a restore, the `currentFileId` pointer could reference a non-existent file if metadata and the bucket were restored to different timestamps.

### 17.1. Integrity Checks

- Every referenced `fileId` must exist.
- Chunk sequence/size must be valid.
- Stream full sample files and compute SHA-256 where available.
- Verify access permissions, legal hold, and retention.
- Do not delete orphan chunks too early while uploads might still be in flight.

### 17.2. Attachments Outside MongoDB

S3/GCS/Azure Blob have their own backup/versioning mechanisms. MongoDB Cloud Backup does not automatically restore external object storage to the same timestamp.

---

## 18. Change Streams, Outbox, and External Systems

### 18.1. Source Rolled Back, Consumer Ahead

```text
MongoDB source restored to T1
Consumer checkpoint / broker state still at T2
```

The resume token may no longer be valid, or projections may still contain changes after T1. Do not simply restart the consumer from checkpoint T2 and assume everything is consistent.

### 18.2. Recovery Plan

- Stop consumers/workers that could cause side effects.
- Identify the source of truth.
- Bootstrap or rebuild projections from the restored source.
- Reconcile broker/outbox event IDs.
- Use inbox/dedup patterns to avoid double charges/emails.
- Check event ordering and gaps.
- Re-enable processing only when state is valid.

### 18.3. Payment Providers

If MongoDB rolls an order back to PENDING while the provider already shows CAPTURED, query and reconcile the transaction ID. Never blindly re-send a capture request.

### 18.4. Search Indexes

Search/Vector Search indexes may require rebuild/initial sync after a restore. Working CRUD does not mean retrieval/full-text queries are ready.

---

## 19. Measuring RPO from Recovery Point Metadata

Example of an **application backup catalog**, not a standard Atlas response:

```json
{
  "backupId": "BK-20261114-1358",
  "sourceCluster": "commerce-prod",
  "type": "pitr-snapshot",
  "lastConsistentPoint": "2026-11-14T13:58:30Z",
  "completedAt": "2026-11-14T14:01:00Z",
  "status": "VERIFIED",
  "restoreTest": "DRILL-20261107"
}
```

`completedAt` is when the job finished, **not** the timestamp of the data state. RPO must be based on `lastConsistentPoint` that is actually recoverable and valid for the incident.

### 19.1. Recommended Metrics

- Last usable consistent recovery point.
- Age of the recovery point.
- PITR window start/end.
- Backup job failures.
- Restore test age.
- Cross-region copy lag.
- Encryption key availability.
- Immutable retention policy.

### 19.2. Do Not Count Only "Backup SUCCESS"

If the RPO target is 5 minutes but the latest usable point is 90 minutes old, you must alert even if last week's job reported success.

---

## 20. Breaking RTO Down into a Time Budget

Example **60-minute** target:

| Stage | Budget |
|---|---:|
| Detect and triage | 5 minutes |
| Decision and approval | 5 minutes |
| Provision target | 8 minutes |
| Restore data | 25 minutes |
| Index/search warm-up | 7 minutes |
| Validation | 5 minutes |
| Cutover + smoke tests | 5 minutes |
| **Total** | **60 minutes** |

If data restore takes 40 minutes instead of 25, you must change the strategy/capacity or accept a different RTO target; you cannot "hide" the time by declaring completion early.

### 20.1. Bandwidth Example

For 2 TiB transferred at 1 Gbit/s effective throughput:

\[
T \approx \frac{2\times2^{40}\times8}{10^9}
\approx 17\,592\text{ seconds}
\]

That is nearly **4.9 hours** at ideal raw-byte transfer speed, before accounting for overhead/indexes/validation. You cannot promise a 30-minute RTO if the actual recovery path requires copying that volume of data in that manner.

### 20.2. Storage Snapshots Optimize Differently

Block-level snapshots/Atlas restores can use mechanisms other than raw copying, so do not use the calculation above to assume every 2 TiB restore takes 4.9 hours. **Benchmark the exact recovery path you have chosen**.

### 20.3. Critical Path

Some steps can run in parallel (provisioning the target while confirming the restore point), but RTO is determined by elapsed time to actual readiness, not the "theoretical" sum of individual steps.

---

## 21. New Recovery Cluster or Overwrite Existing Target?

### 21.1. Restoring to a New Cluster/Namespace

```text
Faulty production
   |
   v
Backup/PITR
   |
   v
Isolated recovery target
   |
   v
Validation + reconciliation
   |
   v
Traffic cutover
```

Pros:

- Preserves the source for forensics.
- Allows data diffing and verification.
- Reduces the risk of losing good writes.
- Enables canary/smoke tests before cutover.

Trade-off: requires storage/compute/network/keys and a traffic cutover plan.

### 21.2. Overwrite Restore

Simpler in terms of infrastructure, but risks deleting good writes on the target, leaving a partial state if the job fails, and hindering forensics.

### 21.3. Write Fencing

During cutover, never allow both the source and the recovery target to accept writes independently. Use maintenance/freeze/routing controls and a clear source of truth. Valid writes between the recovery point and cutover must be **reconciled/replayed** per policy.

### 21.4. Failback

If traffic is later moved back to the old cluster, you must handle writes created on the recovery target. Never simply flip DNS back and ignore the new data.

---

## 22. Ransomware and Backup Immutability

An attacker with permissions to delete both production and backups in the same account can destroy both. Recovery design should consider:

- Appropriate immutable/indelible backup policies.
- Separation of duties and least privilege.
- MFA/SSO, auditing, and break-glass processes.
- Cross-region/cross-account copies.
- Encryption/KMS key recovery.
- Clean-room restore.
- Containing compromised accounts before reopening traffic.

If data was silently modified over several weeks, a short PITR window may no longer contain a **clean point**. Retention must account for **time-to-detection** and legal obligations.

Do not restore the application with compromised secrets and allow bad writes to repeat.

---

## 23. Runbook for Accidental Collection Deletion

1. **Declare incident**, recording affected namespace, first error timestamp, and impact.
2. **Stop/block related writes** per policy.
3. **Identify a clean recovery point** before the bad operation.
4. **Select an isolated target/namespace**, avoiding overwriting production.
5. **Restore selected data** according to backup product capabilities.
6. **Verify schema/indexes/validators and data samples**.
7. **Identify good writes after the clean point**; do not replay bad writes.
8. **Perform conditional merge**, using dry-run/version checks and auditing.
9. **Reconcile** related collections, payments, and broker state.
10. **Smoke tests, business sign-off, cutover**.
11. **Document actual RPO/RTO, missing events, and postmortem**.

### 23.1. Why Consider Selective Restore Latency?

Atlas docs state that selected database/collection restore is not intended to reduce RTO and can take longer than a full restore. Choose it for **scope and the ability to preserve good data**, not under the assumption that it is always faster.

---

## 24. Runbook for Full Cluster/Region Outage

1. Determine whether it is a node failover or actual data loss.
2. Activate the incident commander and relevant RPO/RTO tier.
3. Find the latest usable backup/restore window and confirm encryption keys.
4. Check target topology, server version/FCV, and networking.
5. Provision the target in the appropriate region/project.
6. Restore data and monitor job/disk/capacity.
7. Restore users/roles, secrets, configuration, and indexes/search.
8. Validate business invariants and authorization/tenant isolation.
9. Bring application critical services to a ready state.
10. Cut over traffic with write fencing.
11. Reconcile payments/outbox/broker/object storage.
12. Record actual RPO/RTO, gaps, and failback plan.

Do not treat a restore job reporting SUCCESS as meaning every service is ready. A new cluster may still lack private endpoints, TLS certs, or Search index data.

---

## 25. Post-Restore Accuracy Verification

### 25.1. Document Counts Are Only a First Step

```javascript
db.orders.countDocuments();
db.payments.countDocuments();
db.customers.countDocuments();
```

Matching document counts do not prove that contents and relationships are correct.

### 25.2. Reconciling Near the Incident Timestamp

```javascript
db.orders.find({
  createdAt: {
    $gte: ISODate("2026-11-14T00:00:00Z")
  }
}).sort({
  createdAt: -1
}).limit(20);
```

Substitute the timestamp according to the actual incident. Do not use count output as a complete conclusion.

### 25.3. Business Invariants

- A PAID order must have a corresponding CAPTURED payment.
- No double-charging with the same provider transaction ID.
- Inventory reservations must not exceed available stock.
- Invoice metadata must point to an existing file.
- No violations of tenant isolation.
- Outbox/inbox event IDs must not be processed multiple times.
- Data legally requested for deletion must not reappear contrary to policy.

### 25.4. Example: Finding Orders Missing a Payment Document

```javascript
db.orders.aggregate([
  {
    $match: {
      paymentId: { $exists: true }
    }
  },
  {
    $lookup: {
      from: "payments",
      localField: "paymentId",
      foreignField: "_id",
      as: "matchingPayments"
    }
  },
  {
    $match: {
      matchingPayments: { $size: 0 }
    }
  },
  {
    $project: {
      _id: 1,
      paymentId: 1
    }
  },
  {
    $limit: 50
  }
]);
```

This is only **one type of check**; it does not prove all business logic is sound. For large datasets, use indexes/sampling/batching so validation does not overload the newly restored cluster.

### 25.5. Index and Query Readiness

Check:

- Unique indexes, partial/TTL indexes, collations.
- MongoDB Search/Vector Search rebuild/initial sync.
- Critical query plans.
- Cache/buffer warm-up.
- Change stream consumer projections.
- External dependency health.

---

## 26. RPO/RTO Dashboard and Alerting

| Metric | Purpose |
|---|---|
| `backup_last_success_timestamp` | Latest backup job |
| `backup_last_usable_recovery_point` | Usable restore point |
| `backup_lag_seconds` | Age of recovery point |
| `backup_job_failures_total` | Backup errors |
| `backup_restore_validation_failures_total` | Integrity errors |
| `pitr_window_seconds` | Restore window |
| `cross_region_copy_lag_seconds` | DR backup copy lag |
| `restore_job_duration_seconds` | Data recovery duration |
| `restore_validation_duration_seconds` | Validation duration |
| `cutover_duration_seconds` | Traffic cutover |
| `drill_actual_rpo_seconds` | RPO in drills |
| `drill_actual_rto_seconds` | RTO in drills |
| `unreconciled_business_events` | Good events not yet recovered |
| `search_rebuild_seconds` | Search readiness |

Alert when the last usable recovery point is older than the business RPO **even if the previous backup job reported SUCCESS**.

---

## 27. Restore Drills

Example drill timeline:

```text
Tincident       = 14:00
Talert          = 14:03
Tdecision       = 14:08
TrestoreStart   = 14:12
TrestoreEnd     = 14:28
TvalidationDone = 14:37
TserviceReady   = 14:43
```

Actual RTO is 43 minutes. Actual RPO is calculated from the **restored clean recovery point** to the incident timestamp, combined with evaluating valid data replayed/reconciled.

### 27.1. Drill Scenarios

- Restoring a collection to a temporary namespace.
- PITR prior to a simulated bad write.
- Full cluster restore to a new target.
- Cross-region recovery.
- GridFS files/chunks and app references.
- Payment/order reconciliation.
- Search index rebuilding.
- KMS key access.
- Change stream projection rebuild.

### 27.2. Drills Must Be Safe

Never run destructive restores into production just to measure metrics. Use an isolated target, protect sensitive data, and perform only authorized operations.

### 27.3. Measure on Production-Like Data

Restoring a 10 GiB dataset in a lab last year does not prove RTO for 5 TiB of production data this year. Whenever volume, topology, sharding, or search indexes change, re-measure.

---

## 28. Incident Roles

| Role | Responsibility |
|---|---|
| Incident commander | Command, prioritization, communication |
| DBA/SRE | Backup, restore, topology, monitoring |
| Application owner | API readiness, writes/cutover |
| Business owner | Approving recovery point and data-loss trade-offs |
| Security | Compromise containment, secrets/KMS, forensics |
| Finance/Operations | Payment/logistics reconciliation |
| Compliance/Legal | Retention, legal hold, privacy |

Decisions that may discard good writes (e.g., overwriting production, rolling back several hours) must be approved per the runbook. Break-glass/backup recovery permissions must be prepared in advance, while maintaining auditing and least privilege.

---

## 29. Combined Scenario: Application Bug Followed by Region Outage

```text
09:00 bad deployment corrupts the status of 20,000 orders
09:15 bug is detected
11:00 region hosting MongoDB experiences an outage
```

### 29.1. Restore Latest 10:59

Recovers from the region loss, but order statuses remain corrupted from 09:00.

### 29.2. Roll Back Entire Cluster to 08:59

Removes bad writes, but loses good writes from 09:00–11:00 across other domains.

### 29.3. Combined Approach

1. Restore the cluster in a new region to the latest reliable point for infrastructure recovery.
2. Identify the corrupted orders.
3. Use a snapshot/PITR before 09:00 to extract clean values.
4. Reconstruct legitimate changes after 09:00 from audits/events/providers.
5. Perform selective repair with CAS.
6. Reconcile payments/inventory/outbox/shipments.
7. Document actual RPO/RTO per domain and residual gaps.

No single recovery plan always optimizes all three goals: **minimal data loss, fast recovery, and small repair scope**.

---

## 30. Common Mistakes

1. **"Replica sets already provide backups."** They replicate logical errors.
2. **"Majority writes guarantee RPO=0 in all cases."** False.
3. **"Hourly snapshots mean an exact 1-hour RPO."** You need a usable recovery point.
4. **"Backup SUCCESS means it can be restored."** It must be tested.
5. **"RTO is the duration of `mongorestore`."** RTO lasts until the service is ready.
6. **"Collection restore is always faster than cluster restore."** Atlas docs do not claim this.
7. **"Restoring one collection doesn't affect others."** Relationships can drift out of sync.
8. **"Replay all operations after corruption."** That can recreate the bad writes.
9. **"`mongodump --oplog` is arbitrary PITR."** False.
10. **"`mongodump --oplog` works for an entire sharded cluster."** Not the way a replica set dump does.
11. **"All Atlas tiers have the same Cloud Backup."** You must verify.
12. **"Restored Search definitions mean index data is ready."** Rebuilding may be required.
13. **"GridFS only needs `fs.files`."** Chunks would be missing.
14. **"Only restore data; IAM/KMS/network aren't needed."** False.
15. **"Overwriting a target never loses new data."** It can lose data.
16. **"The oplog is retained forever."** False.
17. **"Snapshotting one shard is enough."** False.
18. **"Encrypted backups don't need decryption keys."** False.
19. **"A MongoDB rollback also rolls back the payment provider."** False.
20. **"Document counts are enough verification."** Invariants are required.
21. **"Choosing a restore point doesn't need business approval."** False.
22. **"One RPO fits every domain."** Unsuitable for most systems.
23. **"Any dump can be restored into an older version."** Check FCV/version.
24. **"Index warm-up doesn't count toward RTO."** It can affect readiness.
25. **"Running one drill is enough."** Data and infrastructure change continuously.

---

## 31. DR Policy Checklist

### 31.1. Business

- [ ] List critical domains/services.
- [ ] Define maximum data loss per domain.
- [ ] Critical and full-service RTO.
- [ ] Sources of reconstructible data.
- [ ] Retention/legal/privacy requirements.
- [ ] Business owner approval of RPO/RTO.

### 31.2. Recovery Scope

- [ ] Document/collection/database/tenant/cluster/region.
- [ ] Orders/payments/inventory/outbox consistency groups.
- [ ] GridFS files/chunks + app metadata.
- [ ] Search indexes/cache/projections.
- [ ] Broker/checkpoints/external services.
- [ ] Version/FCV/sharded topology.
- [ ] IAM/TLS/KMS/DNS/private endpoints.

### 31.3. Backup

- [ ] Snapshot schedule and retention.
- [ ] PITR window if needed.
- [ ] Last usable consistent point.
- [ ] Restore verification cadence.
- [ ] Immutability and offsite policy.
- [ ] Key availability.
- [ ] Restore tools compatibility.
- [ ] Backup failure alerts.

### 31.4. Execution

- [ ] Detect/decision budget.
- [ ] Provisioning automation.
- [ ] Measured restore throughput.
- [ ] Search/index warm-up.
- [ ] Business validation.
- [ ] Traffic cutover/write fencing.
- [ ] Failback/rollback plan.
- [ ] Actual RPO/RTO from drills.

---

## 32. Practice Exercises

### Exercise 1 — Calculating RPO

An incident happens at 14:00, and the latest usable consistent point is at 13:56:40. Calculate the actual RPO gap and compare it against a 5-minute target.

### Exercise 2 — Calculating RTO

Outage at 09:00, database restore finishes at 09:22, indexes ready at 09:30, checkout opens traffic at 09:41. Is a 30-minute RTO target met?

### Exercise 3 — Worst-Case Snapshot Gap

Snapshots run every 4 hours, with no PITR. Determine the worst-case loss window and the impact of one failed backup job.

### Exercise 4 — Business Matrix

Propose RPO/RTO for orders, payments, catalog, and analytics, justified by business impact.

### Exercise 5 — Replica Set

Why can an election not undo a replicated `deleteMany({})`?

### Exercise 6 — Clean PITR Point

Bad writes start at 10:10:15 and are detected at 10:30. Why is 10:25 not a clean point?

### Exercise 7 — Selected Restore

Design a runbook to restore `products` to a temporary namespace, diff, merge, and validate.

### Exercise 8 — Logical Dump

Create a `mongodump` of a lab collection and `mongorestore` on a lab target. Explain consistency limitations.

### Exercise 9 — `--oplog`

Write a full replica set dump with `--oplog` and restore with `--oplogReplay`; state limitations for sharded clusters and arbitrary PITR.

### Exercise 10 — Sharding

Diagram 3 shards + config server; explain why snapshotting each shard at different timestamps can produce invalid state.

### Exercise 11 — GridFS

Define the recovery scope for invoice metadata + `fs.files` + `fs.chunks` + asset references.

### Exercise 12 — Search Index

Explain why CRUD is restored while Vector Search is not yet ready.

### Exercise 13 — Network Time

Calculate the lower bound to transfer 2 TiB over 1 Gbit/s and list factors that make snapshot-based restore differ from raw copy.

### Exercise 14 — Payment Reconciliation

A MongoDB order rolls back to PENDING while the provider remains CAPTURED. Design a workflow that prevents double-charging.

### Exercise 15 — Drill

Design a 60-minute restore drill, recording the timeline, actual RPO/RTO, and checks.

### Exercise 16 — Ransomware

Propose immutable backups, IAM isolation, KMS key recovery, and clean-room restore.

### Exercise 17 — Single Corrupted Field

Restore old `loyaltyPoints` while keeping the new address update, with a conditional version check.

### Exercise 18 — Change Stream Recovery

MongoDB source returns to T1, while consumer checkpoint remains at T2. How do you bootstrap/reconcile without dropping or double-processing events?

### Exercise 19 — Tenant Recovery

`tenant-a` uses shared collections; identify the relationships that must be restored selectively and the risks of namespace-level restore.

### Exercise 20 — RTO at Scale

Compare restoring a 10 GiB lab vs. 5 TiB production, categorizing bottlenecks and benchmarking methodology.

---

## 33. Review Questions

1. What is RPO?
2. What is RTO?
3. How does RPO differ from backup frequency?
4. How does RTO differ from restore command duration?
5. What is actual recovery time/RTA?
6. How do retention and the PITR window differ?
7. Why is RPO=0 hard to guarantee?
8. Why can payments have a different RPO from analytics?
9. Does backup SUCCESS prove it can be restored?
10. Does a replica set replace backups?
11. Does majority write protect against logical corruption?
12. Is the oplog retained forever?
13. What capability does Atlas Continuous Cloud Backup add?
14. Do all Atlas tiers have the same Cloud Backup?
15. Is Atlas selective restore faster than full restore by default?
16. How does create-as-new differ from overwrite?
17. Is `mongodump` a logical or physical backup?
18. Can `--oplogReplay` restore to any timestamp long after the dump?
19. Which components does a sharded backup require?
20. Why does delayed-detection corruption make choosing a recovery point harder?
21. Why shouldn't you replay the entire oplog after bad writes?
22. How can restoring an entire old document overwrite good updates?
23. Which collections must be restored for GridFS?
24. Might Search indexes need rebuilding after a restore?
25. What is the risk of a change stream token newer than the restored source?
26. If the provider is CAPTURED while MongoDB rolled back, what must be done?
27. When should you restore to a new target?
28. What is write fencing during cutover?
29. How do KMS keys relate to recovery?
30. What else must ransomware response do besides restoring?
31. Does RTO include index/cache warm-up?
32. Why does backup `completedAt` not equal the last consistent point?
33. Do document counts prove consistency?
34. What kinds of business invariants should be checked?
35. Why must DR drills use production-like data?
36. Who must approve a recovery point that incurs data loss?
37. When is read-only degraded mode used?
38. How must retention account for attacker dwell time?
39. Why are periodic restore drills necessary?
40. If RPO is met but RTO is missed, are commitments satisfied?

---

## 34. Summary

To protect MongoDB data meaningfully, start from business requirements:

- **RPO:** Maximum acceptable data loss. Must be based on an **actually restorable consistent recovery point**, not just backup frequency.
- **RTO:** Maximum time until **service functionality is ready**, including detection, decision, provisioning, restore, rebuild, validation, and cutover.
- **Recovery scope:** The data to be repaired/restored and consistency relationships, from a single document to an entire cluster/region, including external dependencies.

Principles worth remembering:

1. Replica sets/failover do not replace backups.
2. Atlas snapshots/PITR, `mongodump`, and filesystem snapshots have different limitations.
3. `mongodump --oplog` is neither arbitrary PITR nor a complete sharded cluster backup.
4. Selected restore does not inherently reduce RTO.
5. Restoring to an isolated target better protects data when diff/merge is needed.
6. Data recovery must include indexes, GridFS, brokers, providers, and business reconciliation.
7. KMS/keys, IAM, topology, and networking are part of the recovery scope.
8. RPO/RTO must be proven in **restore drills**, with timelines, validation, and business sign-off.

A good plan must answer: **To what point can we recover? Which data must remain consistent? How long until customers can use critical features again? And what real evidence shows the plan actually works?**

## References

- [MongoDB Atlas — Back Up, Restore and Archive Data](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Atlas Architecture Center — Guidance for Backups](https://www.mongodb.com/docs/atlas/architecture/current/backups/)
- [MongoDB Atlas — Continuous Cloud Backup Restore](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-continuous/)
- [MongoDB Atlas — Recover a Point In Time](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Atlas — Selected Databases and Collections Restore](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-db-coll/)
- [MongoDB Atlas — Restore Your Cluster](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-overview/)
- [MongoDB Atlas — Cloud Backup Overview](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Manual — Backups for Self-Managed](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Backup and Restore Tools](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/)
- [MongoDB Manual — Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/)
- [MongoDB Manual — Sharded Cluster Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/)
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Database Tools — mongorestore Behavior and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [MongoDB Manual — Replica Set High Availability](https://www.mongodb.com/docs/manual/core/replica-set-high-availability/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
