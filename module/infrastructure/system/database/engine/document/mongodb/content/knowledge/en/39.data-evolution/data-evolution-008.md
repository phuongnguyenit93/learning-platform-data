# Reconciling Counts, Data Types, Constraints, and Business Outcomes

When a MongoDB system evolves from an old schema to a new schema, a migration script finishing with exit code 0 **does not mean the data migrated correctly**. A document might land in the right count yet belong to the wrong tenant, an `amount` field might convert from string `"100.50"` to floating-point `100.5` breaking exact money storage, or an order status might rename cleanly while **balances and revenue totals no longer tie out**.

This lesson—**“Reconciling Counts, Data Types, Constraints, and Business Outcomes”** in the **Data Evolution** chapter of *Database Engine Document MongoDB*—shows how to **prove pre- and post-migration data states are equivalent under a defined contract**, and distinguish exceptions needing repair from intentional business changes.

Reconciliation here is far more than counting documents. A trustworthy migration must prove **four layers**:

1. **Counts and scope:** Nothing lost, duplicated, misassigned across tenants/namespaces, or dropped by skipped partitions.
2. **Data types and structure:** Fields hold exact BSON types, missing/null semantics are handled properly, zero precision loss, and rename/transform rules hold.
3. **Technical constraints:** Unique keys, validators, required fields, relationships, referential assumptions, and lifecycle rules hold.
4. **Business outcomes:** Money, points, statuses, balances, access controls, audit events, and invariants remain accurate even when physical documents change shape.

> **Scope:** Examples use `mongosh` and the MongoDB Aggregation Pipeline targeting modern MongoDB Server releases. Certain operators/stages, sharded behaviors, and index validations vary by version; consult official manuals for your exact server, driver, and FCV before deploying. Collection names, counts, and records below are **synthetic lab data**. Never run mutating/deleting commands on production without backups, formal approval, and a rollback plan.

## 1. Learning Objectives and Terminology

After this lesson, learners will be able to:

- Define **source of truth**, scope, snapshots/watermarks, and reconciliation windows.
- Build a **mapping contract** from old schema to new, covering conversions, drops, derivations, and defaults.
- Prove **count** deltas by collection, tenant, status, and business key.
- Distinguish BSON `int`/`long`/`double`/`decimal`/`string`/`date`/`objectId`/`null`/missing.
- Validate `$jsonSchema` rules, unique indexes, partial indexes, null handling, and duplicates.
- Write aggregations to find **missing, extra, duplicated, wrong-type, out-of-range, and dangling-reference** records.
- Verify invariants such as **balances, balanced transfers, order states, inventory counts, and ledger totals**.
- Design reconciliation for **online migrations with dual-writes/change streams**.
- Structure reconciliation reports, severities, tolerances, exception workflows, fix-and-rerun loops, canaries, and rollbacks.
- Write test and operational plans so a migration is **accepted on evidence**, never gut feeling.

### 1.1. Short Glossary

| Term | Meaning |
|---|---|
| **Baseline** | Counts and key sets from the source at a defined comparison point. |
| **Snapshot/cut** | A consistent point in data at which both sides are compared. |
| **Watermark** | CDC/backfill progress marker, e.g., resume token + checkpoint or internal sequence. |
| **Canonical form** | A unified representation used to test semantic equality across two schemas. |
| **Invariant** | A condition that must always hold per business rules, e.g., total debits equal total credits. |
| **Reconciliation key** | A stable key linking an entity in the old schema to its counterpart in the new schema. |
| **Missing/extra** | A record expected to exist that is absent / present outside expected scope. |
| **Diff** | An evidenced discrepancy; must be classified as intentional, transient, or defect. |
| **Tolerance** | An **explicitly defined** acceptable margin of error, never a blanket excuse to ignore mismatches. |
| **Quarantine** | Isolating unconvertible records for remediation without losing source data. |
| **Go/no-go** | Decision to proceed with or halt cutover based on pre-agreed criteria. |

### 1.2. Reconciliation Differs from Migration Script Unit Tests

A unit test for `convertLegacyOrder` may verify 20 fixtures convert properly. Yet production can hold:

- Legacy fields never seen in tests.
- 1,000 documents missing `tenantId`.
- String amounts using comma decimals.
- Orders edited while backfill was running.
- Duplicate business keys across or within tenants.
- Multi-collection transactions captured at slightly skewed times.

**Reconciliation** measures real data against the contract and separates **data-transformation defects** from **ongoing live system mutations**.

## 2. Running Scenario: Order Schema v1 → v2

Suppose an e-commerce app stores v1 orders:

~~~javascript
// collection: orders_v1
{
  _id: ObjectId("66f000000000000000000001"),
  tenant: "tenant-a",
  orderNo: "ORD-1001",
  customer: "C-001",
  status: "new",
  amount: "125000",
  created: ISODate("2026-10-01T08:00:00Z"),
  items: [
    { sku: "SKU-01", qty: 2, unitPrice: "50000" },
    { sku: "SKU-02", qty: 1, unitPrice: "25000" }
  ]
}
~~~

Target schema v2:

~~~javascript
// collection: orders_v2
{
  _id: "tenant-a:ORD-1001",
  legacyId: ObjectId("66f000000000000000000001"),
  tenantId: "tenant-a",
  orderNo: "ORD-1001",
  customerId: "C-001",
  status: "OPEN",
  amountMinor: NumberLong("125000"),
  createdAt: ISODate("2026-10-01T08:00:00Z"),
  items: [
    { sku: "SKU-01", quantity: 2, unitPriceMinor: NumberLong("50000") },
    { sku: "SKU-02", quantity: 1, unitPriceMinor: NumberLong("25000") }
  ],
  schemaVersion: 2
}
~~~

**Target transformation rules:**

| v1 Field | v2 Field | Rule | Reconciliation |
|---|---|---|---|
| `_id` ObjectId | `legacyId` ObjectId | Preserve exact value. | 1-to-1 mapping; never drop `legacyId`. |
| `tenant` | `tenantId` | Keep tenant unchanged. | Zero records moved to wrong tenant. |
| `orderNo` | `orderNo` | Preserve business order number. | Unique per tenant. |
| `customer` | `customerId` | Preserve customer reference. | Zero dangling references per policy. |
| `status: "new"` | `status: "OPEN"` | Map via status table. | Zero unmapped values. |
| `amount: "125000"` | `amountMinor: NumberLong(125000)` | Parse integer in minor units. | Zero rounding, overflow, or sign errors. |
| `created` | `createdAt` | Preserve UTC instant. | Exact milliseconds/timestamp. |
| `items[].qty` | `items[].quantity` | Preserve integer quantity. | Not negative/zero if forbidden by business. |
| `items[].unitPrice` | `items[].unitPriceMinor` | Parse string → int64. | Sum of line items = order amount per policy. |
| absent | `schemaVersion` | Add constant `2`. | Exact BSON value and type. |
| `_id` | new `_id` | Key `tenant + ":" + orderNo`. | Deterministic, collision-safe key. |

This is a **mapping contract**, not a complete conversion script. Real systems must also specify currency, tax, discount, shipping, and refund semantics. This example assumes `amountMinor` equals the line-item sum with no taxes/discounts; **never apply that invariant blindly to domains with discounts**.

### 2.1. Stable Reconciliation Keys

Do not match `orders_v1._id` directly to `orders_v2._id` because the type and value changed. Use:

~~~text
v1: (_id ObjectId) --legacyId--> v2
business key: (tenant, orderNo) --mapped--> (tenantId, orderNo)
~~~

A schema migration can **change technical identity** while preserving business identity. Keep `legacyId` during transition to investigate missing/duplicate/collision issues; drop it only once retention and audit policies allow.

### 2.2. Classify Intentional Changes

For instance, changing `new → OPEN` alters raw bytes yet **satisfies the contract**. Conversely:

~~~text
v1 amount = "125000"
v2 amountMinor = NumberLong("12500")
~~~

is invalid because a digit was lost. Reconciliation must not demand **raw BSON equality** across intentionally redesigned schemas; compare **canonical business meaning**.

### 2.3. Reconciliation Scope

Before running, document:

- Source and target databases/collections.
- Active/inactive tenants, and whether archived/deleted records migrate.
- Historical time windows and retention bounds.
- Records quarantined or invalid at source.
- Fields that are derived vs. intentionally dropped.
- Join keys, membership rules, and business invariants.
- Cut/watermark points when concurrent writes occur.

**Never** define scope as “whatever documents a query happens to see” if both sides keep mutating.

## 3. Four Layers of Reconciliation

| Layer | Question | Example | Limitation |
|---|---|---|---|
| **L1: Counts** | How many docs/keys on each side? | 10,000 orders before and after. | Matching counts can hide missing A and bogus B. |
| **L2: Structure/type** | Are BSON types and required/optional fields valid? | `amountMinor` must be `long`, `createdAt` must be `date`. | Right type can still hold wrong value. |
| **L3: Constraints/references** | Do uniqueness, ranges, enums, and relations hold? | `tenant+orderNo` unique, allowed statuses. | Referential checks still miss financial math errors. |
| **L4: Business outcomes** | Are business semantics equivalent? | Revenue totals, statuses, inventory, ledgers. | Requires an accurate semantic contract. |

Thorough reconciliation **progresses from broad to deep**:

~~~text
Baseline count
   |
   v
Partition count by tenant/date/status
   |
   v
Join/compare business keys
   |
   v
Type/field/value validation
   |
   v
Constraints + reference integrity
   |
   v
Business invariants / ledger totals
   |
   v
Exception review -> fix -> rerun -> sign-off
~~~

### 3.1. Reconciliation Does Not Always Require 100% Raw Comparison

On terabyte datasets, full row-by-row comparisons burn heavy CPU/IOPS. You can combine **partitioned counts/checksums + incremental exact checks + risk-stratified samples**, while explicitly stating coverage guarantees:

- **100% exact** for primary keys, money, critical statuses, and uniqueness.
- **Sampling** for low-risk payloads or archival data when SLAs allow.
- **Checksums** to localize anomalies, followed by exact field diffs on flagged partitions.

Never claim a 1% sample proves 100% of documents are accurate.

### 3.2. Minimum Stop Bars for Critical Migrations

Recommended business-approved **go/no-go** criteria:

~~~text
MUST:
  - zero missing critical business keys
  - zero extra unauthorized tenant records
  - zero invalid required BSON types
  - zero duplicate unique business keys
  - zero unexplained ledger imbalance
  - source/target CDC watermark converged
  - rollback/fallback remains possible

MAY:
  - allow documented differences in deprecated optional fields
  - allow bounded informational count drift if cut has not converged
    but NEVER declare final reconciliation pass in that state
~~~

These zero thresholds are an **illustrative policy**, not built-in MongoDB rules. For low-risk fields, businesses may approve bounded tolerances; for money and authorization, even one bad record can be critical.

## 4. Choosing Comparison Timing: Baselines, Snapshots, and Watermarks

A common mistake:

~~~text
10:00:00  count orders_v1 -> 100,000
10:00:30  app inserts 500 new orders
10:01:00  count orders_v2 -> 100,500
~~~

Two differing numbers **can both be accurate at two different instants**, proving nothing wrong with the migration. Reliable reconciliation requires an aligned **time boundary**.

### 4.1. Three Strategies

| Strategy | Best For | Pros / Cons |
|---|---|---|
| **Quiesce writes** | Offline migrations / maintenance windows. | Easy consistent cut, yet incurs downtime. |
| **Coordinated snapshot/backup point** | Online workloads with backup/CDC support. | Requires topology-aligned snapshot timestamps. |
| **Backfill + CDC watermark** | Online migrations minimizing write pauses. | Complex due to ordering, deletes, replay, convergence, and duplicates. |

### 4.2. Clean Write Quiesce

If pausing write requests, consumers/background jobs, and DDL, and draining in-flight transactions:

1. Fix cut time \(T\).
2. Capture source baseline.
3. Migrate to target.
4. Reconcile full scope at \(T\).
5. Cut over once criteria pass.

Merely “telling the frontend to stop POSTs” is insufficient: workers, cron jobs, change stream processors, TTL/index actions, and other services can still mutate data.

### 4.3. A Backup/Snapshot Is Not `Date.now()`

Calling `new Date()` before two queries does not create a snapshot. When source and target live in different collections or clusters, normal aggregates read at different instants. For a consistent cut, use a **topology-supported snapshot/transaction/backup strategy** or verified CDC sequence/watermark.

### 4.4. CDC Watermarks

A typical pipeline:

~~~text
Source snapshot @ T0
       |
       v
Backfill historical documents
       |
       v
CDC change stream events since T0
       |
       v
Apply upserts/deletes to target
       |
       v
Durable checkpoint / resume token
       |
       v
Wait until CDC lag small / catch-up at cut T1
       |
       v
Reconciliation of source and target at comparable watermark
~~~

**Never rely solely on wall clocks between two hosts** to decide catch-up; use sequences, `clusterTime`, resume tokens, or ordering mechanisms consistent with your architecture. MongoDB change streams have oplog retention windows and resume constraints; if a token expires, resnapshot/rebuild per runbook.

### 4.5. Records Deleted Mid-Migration

Backfill reads record A, source deletes A, yet a consumer handles only inserts/updates: target retains an **extra record A**. Keyset reconciliation catches this. CDC apply must process **deletes/tombstones** or purge targets per source-of-truth rules.

### 4.6. Dual-Writes Across Both Systems

If an app temporarily dual-writes source + target, write order can skew:

~~~text
Source write succeeds
Target write times out
App retries target
Old event later arrives out of order
~~~

Reconciliation needs sequence/versioning, idempotent upserts, and a **conflict resolution policy**. Never assume “dual-writing in one method” provides distributed transaction coordination across independent clusters.

### 4.7. Read Concern and Write Concern

`readConcern: "majority"` ensures reads see majority-committed data per MongoDB semantics, **not a shared snapshot timestamp across two separate queries**. `writeConcern: "majority"` ensures write durability, **not** that the target has already received the latest CDC event. For snapshot/transactional reads, check server versions and resource/retention pressure from long-lived snapshots.

### 4.8. Record Metadata for Every Reconciliation Run

~~~json
{
  "reconciliationRunId": "orders-v2-20261114-001",
  "mappingVersion": "orders-v1-to-v2.3",
  "source": "shop.orders_v1",
  "target": "shop.orders_v2",
  "scope": "all active tenants up to cut T",
  "snapshotOrWatermark": "<verified value>",
  "startedAtUtc": "2026-11-14T02:00:00Z",
  "status": "RUNNING",
  "toolVersion": "reconcile-1.5",
  "checksumAlgorithm": "sha256-canonical-v2",
  "approvedTolerancePolicy": "policy-2026-11"
}
~~~

This is an **illustrative application manifest**, not a mandatory MongoDB format. `snapshotOrWatermark` must reflect an **actually verified cut**, never a scheduler clock estimate.

## 5. Setting Up the Lab and Baseline

Commands below illustrate workflows in the **`schema_reconcile_lab`** database. Run strictly against an authorized test MongoDB instance/cluster; **never create or drop collections in production**. Run the fixture once since `_id`s are fixed.

### 5.1. Seed Source Data

~~~javascript
const lab = db.getSiblingDB("schema_reconcile_lab")

lab.orders_v1.insertMany([
  {
    _id: ObjectId("66f000000000000000000001"),
    tenant: "tenant-a",
    orderNo: "ORD-1001",
    customer: "C-001",
    status: "new",
    amount: "125000",
    created: ISODate("2026-10-01T08:00:00Z"),
    items: [
      { sku: "SKU-01", qty: 2, unitPrice: "50000" },
      { sku: "SKU-02", qty: 1, unitPrice: "25000" }
    ]
  },
  {
    _id: ObjectId("66f000000000000000000002"),
    tenant: "tenant-a",
    orderNo: "ORD-1002",
    customer: "C-002",
    status: "paid",
    amount: "50000",
    created: ISODate("2026-10-02T09:30:00Z"),
    items: [{ sku: "SKU-01", qty: 1, unitPrice: "50000" }]
  },
  {
    _id: ObjectId("66f000000000000000000003"),
    tenant: "tenant-b",
    orderNo: "ORD-2001",
    customer: "C-003",
    status: "new",
    amount: "30000",
    created: ISODate("2026-10-03T10:00:00Z"),
    items: [{ sku: "SKU-03", qty: 2, unitPrice: "15000" }]
  },
  {
    _id: ObjectId("66f000000000000000000004"),
    tenant: "tenant-b",
    orderNo: "ORD-2002",
    customer: "C-004",
    status: "cancelled",
    amount: "40000",
    created: ISODate("2026-10-04T11:00:00Z"),
    items: [{ sku: "SKU-04", qty: 1, unitPrice: "40000" }]
  }
])
~~~

### 5.2. Seed Target Data with Three Intentional Defects

~~~javascript
lab.orders_v2.insertMany([
  {
    _id: "tenant-a:ORD-1001",
    legacyId: ObjectId("66f000000000000000000001"),
    tenantId: "tenant-a",
    orderNo: "ORD-1001",
    customerId: "C-001",
    status: "OPEN",
    amountMinor: NumberLong("125000"),
    createdAt: ISODate("2026-10-01T08:00:00Z"),
    items: [
      { sku: "SKU-01", quantity: 2,
        unitPriceMinor: NumberLong("50000") },
      { sku: "SKU-02", quantity: 1,
        unitPriceMinor: NumberLong("25000") }
    ],
    schemaVersion: NumberInt(2)
  },
  {
    _id: "tenant-a:ORD-1002",
    legacyId: ObjectId("66f000000000000000000002"),
    tenantId: "tenant-a",
    orderNo: "ORD-1002",
    customerId: "C-002",
    status: "PAID",
    amountMinor: "50000", // wrong type: string instead of BSON long
    createdAt: ISODate("2026-10-02T09:30:00Z"),
    schemaVersion: NumberInt(2)
  },
  {
    _id: "tenant-b:ORD-2001",
    legacyId: ObjectId("66f000000000000000000003"),
    tenantId: "tenant-b",
    orderNo: "ORD-2001",
    customerId: "C-003",
    status: "OPEN",
    amountMinor: NumberLong("3000"), // wrong value: missing a trailing 0
    createdAt: ISODate("2026-10-03T10:00:00Z"),
    schemaVersion: NumberInt(2)
  },
  {
    _id: "tenant-a:ORD-ORPHAN",
    legacyId: ObjectId("66f000000000000000000099"),
    tenantId: "tenant-a",
    orderNo: "ORD-ORPHAN",
    customerId: "C-999",
    status: "OPEN",
    amountMinor: NumberLong("500"),
    createdAt: ISODate("2026-10-05T08:00:00Z"),
    schemaVersion: NumberInt(2)
  }
])
~~~

**Engineered defects for learners to catch:**

- Source has **4** docs, target has **4** docs: total counts **match**.
- `ORD-2002` is **missing** at target.
- `ORD-ORPHAN` is an **extra** record at target.
- `ORD-1002.amountMinor` is a **string**, wrong BSON type.
- `ORD-2001.amountMinor` is a `long`, yet **wrong value**.
- `ORD-1001` migrated accurately per example rules.

The fixture intentionally **omits `items` on some v2 records** to illustrate that **required-field/nested invariants** can break too. Never treat synthetic error fixtures as claims about how a production MongoDB pipeline behaves; they are seeded manually for analysis practice.

### 5.3. Indexes Supporting Reconciliation

~~~javascript
lab.orders_v1.createIndex({ tenant: 1, orderNo: 1 })
lab.orders_v2.createIndex({ tenantId: 1, orderNo: 1 })
lab.orders_v2.createIndex({ legacyId: 1 })
lab.orders_v2.createIndex({ tenantId: 1, status: 1, createdAt: 1 })
~~~

These indexes support fixture queries and **are not unique constraints by themselves**. Resolve duplicates before creating real unique indexes; `createIndex` on large datasets consumes I/O/CPU and needs a rollout plan. Add indexes supporting keyset pagination/partition scans based on actual query shapes.

### 5.4. Never Reset Labs with Dangerous Commands

When re-running fixtures, verify you target the sandbox cluster/database before cleaning. This lesson omits any generic `dropDatabase()` snippet so nobody pastes it into production by mistake. Real reconciliation should run under **read-only credentials**, reserving writes strictly for dedicated migration/remediation jobs.

## 6. Reconciling Counts: From Global Totals to Partitions

### 6.1. `countDocuments`, `estimatedDocumentCount`, and `$count`

~~~javascript
const sourceCount = lab.orders_v1.countDocuments({})
const targetCount = lab.orders_v2.countDocuments({})

printjson({
  sourceCount,
  targetCount,
  delta: targetCount - sourceCount
})
~~~

In our lab, both totals equal 4 with delta 0; **you still cannot declare PASS**.

| API | When to Use | Limitations |
|---|---|---|
| `countDocuments(filter)` | Count exact matching documents per filter. | Can trigger costly index/collection scans at scale; not a shared snapshot with other queries. |
| `estimatedDocumentCount()` | Need a **fast metadata estimate**. | Never use to prove exact reconciliation counts; ignores filters/scopes. |
| Aggregation `$count` | Count after filtering/transform stages. | Returns an aggregate cursor; requires explicit cut and filter. |
| `$group` + `$sum:1` | Count per tenant, status, or bucket. | Normalize labels and preserve scope. |

**Note:** `countDocuments({})` can be costly on huge collections; check indexes, hints, and timings per docs. Never use `estimatedDocumentCount` for exact go/no-go decisions.

### 6.2. Count by Tenant

~~~javascript
lab.orders_v1.aggregate([
  { $group: {
      _id: "$tenant",
      count: { $sum: 1 }
  }},
  { $sort: { _id: 1 } }
])

lab.orders_v2.aggregate([
  { $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
  }},
  { $sort: { _id: 1 } }
])
~~~

In the lab:

| Tenant | v1 Count | v2 Count | Delta |
|---|---:|---:|---:|
| `tenant-a` | 2 | 3 | +1 |
| `tenant-b` | 2 | 1 | −1 |
| **Total** | **4** | **4** | **0** |

A total delta of 0 hid **+1 on `tenant-a` and −1 on `tenant-b`**. Always group by meaningful partition keys.

### 6.3. Count by Normalized Status

If v1 uses `new/paid/cancelled` and v2 uses `OPEN/PAID/CANCELLED`, do not compare raw status strings:

~~~javascript
lab.orders_v1.aggregate([
  { $project: {
      tenantId: "$tenant",
      normalizedStatus: {
        $switch: {
          branches: [
            { case: { $eq: ["$status", "new"] }, then: "OPEN" },
            { case: { $eq: ["$status", "paid"] }, then: "PAID" },
            { case: { $eq: ["$status", "cancelled"] },
              then: "CANCELLED" }
          ],
          default: "__UNMAPPED__"
        }
      }
  }},
  { $group: {
      _id: { tenantId: "$tenantId", status: "$normalizedStatus" },
      count: { $sum: 1 }
  }},
  { $sort: { "_id.tenantId": 1, "_id.status": 1 } }
])
~~~

Every `__UNMAPPED__` value is an **exception requiring investigation**, never silently defaulted to `OPEN` just to make totals align.

### 6.4. Count by Day While Verifying Timezones

~~~javascript
lab.orders_v2.aggregate([
  { $group: {
      _id: {
        tenantId: "$tenantId",
        day: {
          $dateToString: {
            format: "%Y-%m-%d",
            date: "$createdAt",
            timezone: "UTC"
          }
        }
      },
      count: { $sum: 1 }
  }},
  { $sort: { "_id.tenantId": 1, "_id.day": 1 } }
])
~~~

If the business defines reporting days in **Asia/Ho_Chi_Minh**, apply that `timezone` on **both sides**. Using UTC on source and local time on target creates false mismatches near midnight.

### 6.5. Count Delta Formula

For each partition \(p\):

\[
\Delta_p = N_{\mathrm{target},p} - N_{\mathrm{source},p}
\]

When cuts/watermarks are truly aligned and no intentional filtering applies:

\[
\forall p,\quad \Delta_p = 0
\]

Yet **\(\Delta_p=0\) is still insufficient**, since A could drop while B is added. Compare **key sets** next.

### 6.6. Business-Meaningful Partitions

Typical partition dimensions include:

- Tenant / region / data residency.
- `schemaVersion` / status.
- Created date or `ObjectId` range per migration plan.
- Currency or payment method.
- Soft-deleted / archived / active.
- Shard key ranges when sharded.

**Never** group solely by `status` if a record could jump between tenants while keeping status totals unchanged.

### 6.7. Handling Soft Deletes and TTL

If the source has `deletedAt` and the target drops deleted records per business rules, compare target counts **against a matching filtered source baseline**, not the unfiltered source. MongoDB's TTL monitor can also purge expired documents asynchronously. Document retention/time boundaries clearly and avoid comparing across mismatched lifecycle windows.

## 7. Reconciling Key Sets: Finding Missing, Extra, Duplicate, and Mismapped Keys

**Counts are only a preliminary signal.** Prove every in-scope source record maps to **exactly one** target record and vice versa. In our fixture, `legacyId` joins `orders_v2` back to `orders_v1._id`.

### 7.1. Find Source Records Missing from Target

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "targetMatches"
    }
  },
  {
    $match: {
      $expr: { $eq: [{ $size: "$targetMatches" }, 0] }
    }
  },
  {
    $project: {
      _id: 1, tenant: 1, orderNo: 1,
      reason: { $literal: "MISSING_TARGET" }
    }
  }
])
~~~

In our fixture, this returns `ORD-2002`. This `$lookup` works within **one database**; if source and target live on **two separate clusters**, a single `$lookup` cannot join across clusters. Instead, run a reconciliation service reading both via the driver, comparing keysets or partition hashes.

### 7.2. Find Target Records Missing from Source

~~~javascript
lab.orders_v2.aggregate([
  {
    $lookup: {
      from: "orders_v1",
      localField: "legacyId",
      foreignField: "_id",
      as: "sourceMatches"
    }
  },
  {
    $match: {
      $expr: { $eq: [{ $size: "$sourceMatches" }, 0] }
    }
  },
  {
    $project: {
      _id: 1, tenantId: 1, orderNo: 1, legacyId: 1,
      reason: { $literal: "EXTRA_TARGET" }
    }
  }
])
~~~

In our fixture, `ORD-ORPHAN` is extra. **Never blindly delete** every extra record: it might be a valid post-cut write, an approved seed, or data from another scope. Investigate timestamps, business rules, and ownership first.

### 7.3. Detect One Source Mapping to Multiple Targets

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "targets"
    }
  },
  {
    $match: {
      $expr: { $gt: [{ $size: "$targets" }, 1] }
    }
  },
  {
    $project: {
      orderNo: 1,
      targetCount: { $size: "$targets" },
      targetIds: "$targets._id"
    }
  }
])
~~~

On large collections, `$lookup` arrays consume heavy RAM or hit BSON limits; grouping keys on the target is usually much cheaper for finding duplicates:

~~~javascript
lab.orders_v2.aggregate([
  {
    $group: {
      _id: "$legacyId",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } }
])
~~~

`$push`ing all `_id`s into one group risks large memory/output; in production, count and cap sampled IDs on high-cardinality groups. Missing `legacyId` values also group together (under BSON expressions), so check missing/null separately to avoid misdiagnosis.

### 7.4. Duplicates on Business Keys

~~~javascript
lab.orders_v2.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        orderNo: "$orderNo"
      },
      n: { $sum: 1 }
    }
  },
  { $match: { n: { $gt: 1 } } }
])
~~~

This checks the **pair `(tenantId, orderNo)`**, not `orderNo` alone, since two tenants can legitimately share an order number. If business requires global uniqueness, update the contract and unique index accordingly.

### 7.5. 1-to-1 Still Does Not Guarantee Matching Tenant

A target doc with a valid `legacyId` yet wrong `tenantId` still joins cleanly. Check further:

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "t"
    }
  },
  { $unwind: "$t" },
  {
    $match: {
      $expr: {
        $or: [
          { $ne: ["$tenant", "$t.tenantId"] },
          { $ne: ["$orderNo", "$t.orderNo"] },
          { $ne: ["$customer", "$t.customerId"] }
        ]
      }
    }
  },
  {
    $project: {
      sourceId: "$_id",
      sourceTenant: "$tenant",
      targetId: "$t._id",
      targetTenant: "$t.tenantId",
      sourceOrderNo: "$orderNo",
      targetOrderNo: "$t.orderNo"
    }
  }
])
~~~

If one source maps to multiple targets, `$unwind` emits multiple rows; resolve **duplicate cardinality** before treating each diff row as a unique entity.

### 7.6. Set Comparison with `$setDifference`

For **small, bounded datasets** that fit safely in memory:

~~~javascript
// Small lab only; DO NOT use toArray() for millions of keys.
const sourceKeys = lab.orders_v1
  .find({}, { tenant: 1, orderNo: 1, _id: 0 })
  .toArray()
  .map(x => x.tenant + "|" + x.orderNo)

const targetKeys = lab.orders_v2
  .find({}, { tenantId: 1, orderNo: 1, _id: 0 })
  .toArray()
  .map(x => x.tenantId + "|" + x.orderNo)

const missing = sourceKeys.filter(x => !targetKeys.includes(x))
const extra = targetKeys.filter(x => !sourceKeys.includes(x))
printjson({ missing, extra })
~~~

This snippet is **solely for a handful of records**. `Array.includes` degrades toward \(O(n^2)\), and joining strings with `|` risks **collisions** if tenant/orderNo contains `|`. In production, use length-prefixed/structured key encoding, `Set`/merge-sort/indexed lookups, streaming chunks, and memory budgets.

### 7.7. Distinguish “Lost Record” from “Not Yet Caught Up”

During online migrations, a source record commits at 10:00:05 while the target's CDC checkpoint sits at 10:00:03. Reconciling right then makes the record look **temporarily** missing. Never ignore it permanently: tag it `NOT_CAUGHT_UP` while `RUNNING`, and make final determinations **only once both sides align on the cut point**.

### 7.8. Reconciliation Keys Can Mutate Under Business Edits

If `orderNo` is editable after creation, keying reconciliation on `orderNo` is unstable. Prefer immutable source IDs or persisted migration IDs; if business keys can change, maintain a mapping table **old key → stable entity ID → current key** and handle rename events.

### 7.9. Composite Keys and Collation

MongoDB collation can treat `"ABC"` and `"abc"` as equal for queries/uniqueness, whereas Java `String.equals` behaves differently. Specify:

- Is comparison case-sensitive?
- Are whitespace trimming or Unicode normalization applied?
- Are Vietnamese diacritics folded in search yet preserved in identity?
- Are leading zeros preserved in `orderNo`?

Key reconciliation must enforce the **exact same normalization/collation contract** rather than blindly calling `toLowerCase` and merging two distinct entities.

## 8. Checking BSON Types, Missing, Null, and Nested Structures

### 8.1. BSON Types Differ from JavaScript Types

MongoDB stores BSON types including `int` (32-bit), `long` (64-bit), `double` (floating point), `decimal` (Decimal128), `string`, `date`, `objectId`, `bool`, `array`, `object`, and `null`. In `mongosh`, JavaScript numbers may hide underlying server BSON types, so **never rely solely on `typeof`**.

Example:

~~~javascript
// Explicit BSON constructors in mongosh:
NumberInt(12)          // BSON int32
NumberLong("12")       // BSON int64
NumberDecimal("12.30") // BSON Decimal128
ISODate("2026-11-14T00:00:00Z") // BSON Date
ObjectId("66f000000000000000000001")
~~~

### 8.2. Type Distribution Summary for a Field

~~~javascript
lab.orders_v2.aggregate([
  {
    $project: {
      amountType: { $type: "$amountMinor" }
    }
  },
  {
    $group: {
      _id: "$amountType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
~~~

In our fixture, expect 3 `long` records and 1 `string`. This **type** discrepancy is invisible to total document counts.

### 8.3. Listing Records with Wrong Types

~~~javascript
lab.orders_v2.aggregate([
  {
    $match: {
      $expr: {
        $ne: [{ $type: "$amountMinor" }, "long"]
      }
    }
  },
  {
    $project: {
      orderNo: 1,
      tenantId: 1,
      amountMinor: 1,
      actualType: { $type: "$amountMinor" }
    }
  }
])
~~~

**Crucial distinction:** The aggregation `$type` expression returns `"missing"` for absent fields and `"null"` for BSON Null. The query operator `{field: {$type: "long"}}` has distinct semantics—especially on arrays—so use `$expr` and the `$type` expression to classify a **field at an exact path**.

### 8.4. Missing and Null Are Not Identical

~~~javascript
// Document A:
{ _id: "A" } // amountMinor missing

// Document B:
{ _id: "B", amountMinor: null } // amountMinor explicitly null
~~~

In MongoDB queries:

~~~javascript
// Matches both null and missing:
db.orders_v2.find({ amountMinor: null })

// Only when field exists with BSON null:
db.orders_v2.find({ amountMinor: { $type: "null" } })

// Only when field does not exist:
db.orders_v2.find({ amountMinor: { $exists: false } })
~~~

`$exists:true` also matches fields set to `null`. Required fields typically disallow both missing and null; for optional “unknown” fields, missing and null may carry distinct contract meanings.

### 8.5. Mutually Exclusive Breakdown of Missing/Null/Wrong Type

~~~javascript
lab.orders_v2.aggregate([
  {
    $project: {
      kind: {
        $switch: {
          branches: [
            {
              case: {
                $eq: [{ $type: "$amountMinor" }, "missing"]
              },
              then: "MISSING"
            },
            {
              case: {
                $eq: [{ $type: "$amountMinor" }, "null"]
              },
              then: "NULL"
            },
            {
              case: {
                $eq: [{ $type: "$amountMinor" }, "long"]
              },
              then: "OK_LONG"
            }
          ],
          default: "WRONG_TYPE"
        }
      }
    }
  },
  { $group: { _id: "$kind", count: { $sum: 1 } } }
])
~~~

This yields **mutually exclusive categories**, far more actionable than a single “bad” counter because remediation differs for missing, null, and string values.

### 8.6. Expected Types of Required Fields

A v2 schema profile might specify:

| Field | Required BSON Type | Mandatory? | Meaning |
|---|---|---|---|
| `_id` | `string` | Yes | Deterministic target ID. |
| `legacyId` | `objectId` | Yes during transition | Link back to source. |
| `tenantId` | `string` | Yes | Tenant boundary. |
| `orderNo` | `string` | Yes | Business ID. |
| `customerId` | `string` | Yes | Relation ID. |
| `status` | `string` | Yes | Enum contract. |
| `amountMinor` | `long` | Yes | Integer in minor currency units. |
| `createdAt` | `date` | Yes | UTC instant. |
| `items` | `array` | Yes per example | Line items. |
| `schemaVersion` | `int` | Yes | Schema version. |

Never assume `int` and `long` are interchangeable just because both are mathematical integers. When Java reads a `Long`, BSON int32 records may behave differently across converters; when the contract demands **long**, reconcile both exact type and mapping.

### 8.7. Nested Fields and Array Elements

~~~javascript
lab.orders_v2.aggregate([
  { $unwind: { path: "$items", preserveNullAndEmptyArrays: true } },
  {
    $project: {
      orderNo: 1,
      itemType: { $type: "$items" },
      skuType: { $type: "$items.sku" },
      qtyType: { $type: "$items.quantity" },
      priceType: { $type: "$items.unitPriceMinor" }
    }
  }
])
~~~

This inspects each item; on missing/empty arrays, `preserveNullAndEmptyArrays:true` keeps the order row yet does not prove “valid items exist.” Separate checking **that `items` exists and is non-empty** (if required) from checking element types. Guard with `$isArray` and `$size`/`$filter` so non-array values do not crash pipelines.

### 8.8. `$isNumber` Does Not Replace Exact Type Requirements

`$isNumber` matches any numeric BSON type (`int`, `long`, `double`, `decimal`) and **does not enforce exact int64**. When `amountMinor` must strictly be `long`, check `$type` (plus range rules) instead of `$isNumber` alone.

### 8.9. `Date` Is an Instant, Not an ISO-Looking String

~~~javascript
{ createdAt: "2026-10-01T08:00:00Z" }   // BSON string
{ createdAt: ISODate("2026-10-01T08:00:00Z") } // BSON Date
~~~

These look similar in JSON yet have **different types**, breaking sorts, range queries, TTL indexes, timezone math, and serialization. During reconciliation, compare UTC instants/milliseconds per contract rather than assuming input strings parsed in the right zone.

### 8.10. `ObjectId` vs. String

`ObjectId("66...")` differs from string `"66..."` in BSON type and index ordering. If intentionally converting `ObjectId` → String ID, enforce canonical mapping (e.g., lowercase hex) and preserve legacy links; **never** treat raw `ObjectId` and hex strings as equal in `$lookup`.

## 9. Reconciling Conversion Rules: Valid Type Alone Is Not Enough

A field with the right BSON type can still hold the **wrong value**. Converting `"30000"` into `NumberLong("3000")` produces a valid `long` that is off by 10x. Compare **contract-normalized source values** against targets rather than checking target types alone.

### 9.1. Catching Parse Errors Before Conversion

~~~javascript
lab.orders_v1.aggregate([
  {
    $project: {
      orderNo: 1,
      tenant: 1,
      originalAmount: "$amount",
      originalType: { $type: "$amount" },
      parsed: {
        $convert: {
          input: "$amount",
          to: "long",
          onError: "__INVALID__",
          onNull: "__NULL_OR_MISSING__"
        }
      }
    }
  }
])
~~~

`$convert` catches errors without aborting the entire aggregation. Note that `__NULL_OR_MISSING__` alone does not separate missing from null; inspect `originalType` too. In production, record **error codes and redacted raw values** in a quarantine manifest rather than silently dropping rows with `onError:null`.

### 9.2. When Not to Use `$toLong` Blindly

~~~javascript
{ $toLong: "$amount" }
~~~

If `amount` is `"N/A"` or overflows int64, the aggregation fails; if `amount` is `double`, `$toLong` truncates fractional digits and loses precision. For money migrations:

1. Validate input format, scale, and currency.
2. Parse per signed-off rules.
3. Check range/overflow.
4. Validate target type and value.
5. Quarantine unconvertible records.

`$convert` with `onError` builds error reports instead of crashing the batch, yet **must never turn invalid sources into zero**.

### 9.3. Specify Currency Units Explicitly

In our example, source `"125000"` is **minor units (dong)** matching `NumberLong(125000)`. If sources store `"1250.00"` major units, mappings need **currency exponents**:

~~~text
USD: 12.34 dollars -> 1234 cents (scale=2)
JPY: 100 yen       -> 100 yen   (scale=0)
VND: 125000 dong   -> 125000 dong (scale=0 in this example)
~~~

Never apply `×100` blindly across currencies. Reconcile currency codes and rounding rules rather than comparing mismatched units.

### 9.4. `Double` and `Decimal128` Are Different

`Double` is binary floating point, unable to represent many decimal fractions exactly (like `0.1`). `Decimal128` stores exact decimal digits and scales suited to finance. If the contract specifies `Decimal128("12.30")`, storing `double 12.3` has the **wrong type and different precision semantics**, even if printed digits look alike.

For money, prefer:

- Int64 minor units when scale/currency/range fit; or
- `Decimal128` with explicit rounding and scale rules.

Check Java `BigDecimal` ↔ MongoDB `Decimal128` converters and overflow limits; never call `doubleValue()` before persisting.

### 9.5. Int64 Overflow and Negative Values

Signed int64 spans \(-2^{63}\) to \(2^{63}-1\). Numeric strings beyond that range cannot fit in BSON `long`. Reconcile:

- Unparseable record counts.
- Out-of-bounds values per business rules.
- Whether negative amounts are valid for refunds/adjustments.
- Totals per currency/tenant and aggregate accumulator types.

Never use `0` as a parse-error sentinel when `0` is a valid business value.

### 9.6. Comparing Source vs. Target After Canonical Conversion

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "targets"
    }
  },
  { $unwind: "$targets" },
  {
    $addFields: {
      expectedAmount: {
        $convert: {
          input: "$amount",
          to: "long",
          onError: null,
          onNull: null
        }
      },
      targetType: { $type: "$targets.amountMinor" }
    }
  },
  {
    $match: {
      $expr: {
        $or: [
          { $ne: ["$targetType", "long"] },
          { $eq: ["$expectedAmount", null] },
          { $ne: ["$expectedAmount", "$targets.amountMinor"] }
        ]
      }
    }
  },
  {
    $project: {
      orderNo: 1, tenant: 1,
      sourceAmount: "$amount",
      expectedAmount: 1,
      targetAmount: "$targets.amountMinor",
      targetType: 1
    }
  }
])
~~~

In the lab, `ORD-1002` fails type and `ORD-2001` fails value. **This predicate is a basic check**, not a complete substitute for format/rounding/currency validation. Notably, BSON numeric comparisons can treat differing numeric types as mathematically equal, which is why **`targetType` is checked explicitly**.

### 9.7. Reconciling Status Mappings

~~~javascript
lab.orders_v1.aggregate([
  {
    $lookup: {
      from: "orders_v2",
      localField: "_id",
      foreignField: "legacyId",
      as: "t"
    }
  },
  { $unwind: "$t" },
  {
    $addFields: {
      expectedStatus: {
        $switch: {
          branches: [
            { case: { $eq: ["$status", "new"] }, then: "OPEN" },
            { case: { $eq: ["$status", "paid"] }, then: "PAID" },
            { case: { $eq: ["$status", "cancelled"] },
              then: "CANCELLED" }
          ],
          default: "__UNMAPPED__"
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$expectedStatus", "$t.status"] }
    }
  },
  {
    $project: {
      orderNo: 1,
      sourceStatus: "$status",
      expectedStatus: 1,
      targetStatus: "$t.status"
    }
  }
])
~~~

**Always flag unmapped source statuses too**, even if the target happened to write the same sentinel. Never treat `"__UNMAPPED__"` as valid just to make diff counts 0.

### 9.8. Rounding and Tolerance Comparisons

For money in minor units, enforce **exact integer equality**. For sensor measurements or approved algorithmic outputs, you may allow:

\[
|v_{\mathrm{target}} - v_{\mathrm{expected}}| \le \epsilon
\]

Yet \(\epsilon\) must be business-approved **per field, unit, currency, and source**—never slap a global `0.01` tolerance across the board and ignore drift. For ratios, combine absolute and relative tolerances guarded against zero denominators, testing near-zero, negative, huge, and overflow values.

### 9.9. Comparing Times and Timezones

MongoDB BSON `Date` stores milliseconds since the Unix epoch. When both sides hold `Date`, compare **UTC instants**. When sources hold timezone-less local date strings, document timezone assignment and DST ambiguity rules. `createdAt` must never shift by +7 hours simply because the app runs in Vietnam.

### 9.10. Arrays: Set or Sequence?

~~~json
// Two arrays with identical elements in different order:
{"tags": ["a", "b"]}
{"tags": ["b", "a"]}
~~~

If `tags` has **set semantics**, canonicalize by sorting and deduplicating. If `items` carries `lineNumber` and display order matters, never blindly sort and call two orders equal. The mapping contract must state **order-sensitive** vs. **order-insensitive**, duplicate rules, and nested element defaults.

### 9.11. Dropping Fields Requires Conditions

If schema v2 drops `legacyNotes` as “unused,” first check for non-empty values and audit/legal retention mandates. Omitting a field from the target is valid only when policy permits:

~~~text
Drop allowed if:
  field is deprecated AND
  no current business consumer AND
  retention policy allows omission AND
  migration manifest records decision.
~~~

Never silently lose unknown fields via `ignoreUnknownProperties` and assume conversion succeeded.

## 10. Technical Constraints: `$jsonSchema`, Unique Indexes, and Schema Versions

MongoDB provides **document validation** and indexes to enforce part of your invariants at the storage layer. Still, validators and indexes **do not replace historical data reconciliation**, and cross-collection business rules still require application or aggregation checks.

### 10.1. Example v2 Schema Validator

On a **new lab collection** after cleaning fixtures (or a separate test collection), define:

~~~javascript
db.createCollection("orders_v2_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "orderNo", "customerId",
        "status", "amountMinor", "createdAt", "schemaVersion"
      ],
      properties: {
        _id: { bsonType: "string" },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string", minLength: 1 },
        customerId: { bsonType: "string" },
        status: {
          enum: ["OPEN", "PAID", "CANCELLED"]
        },
        amountMinor: { bsonType: "long", minimum: 0 },
        createdAt: { bsonType: "date" },
        schemaVersion: { bsonType: "int", enum: [2] },
        items: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["sku", "quantity", "unitPriceMinor"],
            properties: {
              sku: { bsonType: "string" },
              quantity: { bsonType: "int", minimum: 1 },
              unitPriceMinor: { bsonType: "long", minimum: 0 }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

**This validator matches the lab model**, not every production system. If `items` must always exist and be non-empty, add `items` to `required` and set `minItems:1` per supported JSON Schema version. If refunds allow negative amounts, omit `minimum:0` across all transactions.

### 10.2. `required` and `bsonType` Are Separate Conditions

~~~javascript
required: ["amountMinor"],
properties: {
  amountMinor: { bsonType: "long" }
}
~~~

`required` enforces field presence; `bsonType:"long"` enforces type. Having `bsonType` without `required` allows missing fields; having `required` without `bsonType` lets string `"1000"` slip through.

### 10.3. Updating Validators with `collMod`

~~~javascript
db.runCommand({
  collMod: "orders_v2_validated",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderNo", "amountMinor"],
      properties: {
        tenantId: { bsonType: "string" },
        orderNo: { bsonType: "string" },
        amountMinor: { bsonType: "long" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Illustrates `collMod` syntax on a **lab collection**. It replaces the entire existing validator rather than merging field-by-field—running carelessly in production can accidentally drop older checks. Require versioned schema changes, reviews, and rollback plans.

### 10.4. `validationLevel` and `validationAction`

| Option | Practical Meaning |
|---|---|
| `validationLevel:"strict"` | Checks eligible inserts and updates against the rule. |
| `validationLevel:"moderate"` | Updates on already-invalid docs bypass strict revalidation unlike valid docs; consult exact docs. |
| `validationAction:"warn"` | Permits violating writes while logging warnings; useful for observational rollouts. |
| `validationAction:"error"` | Rejects non-compliant writes unless bypassed with proper privileges. |

Updating a validator **does not automatically repair or delete invalid historical documents**. Actively scan and remediate the collection using **`$jsonSchema` queries** before tightening to `strict/error`.

### 10.5. Finding Documents Failing the Validator

~~~javascript
const v2Schema = {
  bsonType: "object",
  required: ["tenantId", "orderNo", "amountMinor"],
  properties: {
    tenantId: { bsonType: "string" },
    orderNo: { bsonType: "string" },
    amountMinor: { bsonType: "long" }
  }
}

lab.orders_v2.find({
  $nor: [{ $jsonSchema: v2Schema }]
}, { tenantId: 1, orderNo: 1, amountMinor: 1 })
~~~

Under this minimal rule, `ORD-1002` fails type checks. Production should share the **exact same versioned definition** between validator rollout and reconciliation; still, never assume a short schema rule covers all business invariants.

### 10.6. Unique Business Keys

~~~javascript
// Run only on a clean/authorized collection.
lab.orders_v2.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uniq_tenant_orderNo" }
)
~~~

Unique indexes enforce uniqueness per **key + collation/index rules**, not whether `orderNo` matches format rules or belongs to the right tenant. If duplicates exist, building a unique index fails; **count and resolve duplicates first**.

### 10.7. Missing/Null with Unique Indexes

Single-field unique indexes map missing fields and `null` to a null-like index key, causing duplicate-key collisions if multiple documents omit the field. Compound unique indexes require auditing missing/null combinations too. **Never rely on unique indexes to enforce required-field validation.** Pair `required`/BSON types with indexes.

### 10.8. Partial Unique Indexes

If uniqueness applies only to active records:

~~~javascript
lab.orders_v2.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "uniq_active_tenant_orderNo",
    partialFilterExpression: { isActive: true }
  }
)
~~~

This is an **alternative design**, not something to slap on alongside a full unique index expecting it to replace it. Confirm `isActive` exists and is boolean across all active records. Partial indexes enforce uniqueness only on documents **matching the filter**, leaving documents missing `isActive` unconstrained. Reconcile missing/invalid flags and scope.

### 10.9. Unique Indexes and Sharding

In sharded collections, unique index guarantees depend on **shard key prefixes**, sharding style, and server versions. Never build an arbitrary unique index and assume cluster-wide uniqueness holds. Verify sharded-cluster docs, shard key design, and business keys pre-migration.

### 10.10. Enforce Sequentially, Never Abruptly

A viable sequence:

~~~text
Observe existing shape/types
        |
        v
Report invalid source records
        |
        v
Backfill and fix target data
        |
        v
Reconcile exact required/unique fields
        |
        v
Create indexes and introduce validator warn
        |
        v
Monitor new writes / exceptions
        |
        v
Switch to validator strict/error after approval
~~~

Never leave `warn` active forever claiming schemas are enforced; never enable `error` before legacy apps/consumers are compatible and cause mass production failures.

## 11. Reconciling Cross-Collection Relations and Implicit Constraints

MongoDB does not provide RDBMS-style foreign keys by default. If `orders.customerId` references `customers._id`, the application must define whether dangling references are permitted under retention, soft deletes, and tenant isolation.

### 11.1. Controlled Customer Fixture

In the same lab database:

~~~javascript
lab.customers_v2.insertMany([
  { _id: "C-001", tenantId: "tenant-a", active: true },
  { _id: "C-002", tenantId: "tenant-a", active: true },
  { _id: "C-003", tenantId: "tenant-b", active: true },
  { _id: "C-004", tenantId: "tenant-b", active: false }
])

lab.customers_v2.createIndex({ tenantId: 1, _id: 1 })
~~~

Here `ORD-ORPHAN.customerId="C-999"` has no matching customer. **Never** blindly assume every archived order must link to a live customer: if privacy policies permit customer deletion, define retention/anonymization semantics first.

### 11.2. Finding Dangling Customer References

~~~javascript
lab.orders_v2.aggregate([
  {
    $lookup: {
      from: "customers_v2",
      localField: "customerId",
      foreignField: "_id",
      as: "customerMatches"
    }
  },
  {
    $match: {
      $expr: {
        $eq: [{ $size: "$customerMatches" }, 0]
      }
    }
  },
  {
    $project: {
      tenantId: 1, orderNo: 1, customerId: 1,
      reason: { $literal: "MISSING_CUSTOMER" }
    }
  }
])
~~~

This `$lookup` joins `orders_v2` to `customers_v2` within **the same database**. When references use composite keys (`tenantId+customerId`), joining solely on `customerId` can match a **customer in another tenant**, masking an isolation breach.

### 11.3. Enforcing Matching Tenants

~~~javascript
lab.orders_v2.aggregate([
  {
    $lookup: {
      from: "customers_v2",
      let: {
        cid: "$customerId",
        tid: "$tenantId"
      },
      pipeline: [
        { $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            }
        }}
      ],
      as: "validCustomer"
    }
  },
  {
    $match: {
      $expr: { $eq: [{ $size: "$validCustomer" }, 0] }
    }
  },
  { $project: { orderNo: 1, tenantId: 1, customerId: 1 } }
])
~~~

This verifies existence and **tenant consistency**, not `active/inactive` status. If historical orders may point to inactive customers, adding `active:true` produces false positives. If customer IDs are only unique per tenant (not global), design composite keys properly rather than relying solely on `_id`.

### 11.4. Checking One-to-Many Relations

Common checks:

- Order → `orderItems`: every item belongs to a valid order.
- Customer → addresses: addresses never point across tenants.
- Payment → order: every captured payment matches a valid order with aligned amount/currency.
- Invoice → order: invoice numbers do not map improperly to multiple orders.
- User → roles: new permissions are no broader than old permissions.

For many-to-many or embedded structures, you may need **`$unwind` + `$group`** before reconciling; never assume every `$lookup` returns a single document.

### 11.5. Referential Integrity and Deletes

If the source soft-deletes customers, the target may keep orders while anonymizing personal details. A blanket “every order needs a customer record” check can clash with privacy compliance. Separate:

1. Must **active orders** have active customers?
2. Can **historical orders** retain hashed/tombstone customer IDs?
3. After erasure requests, which fields must be purged/masked?
4. Are intentional orphans tracked with timestamps and reason codes?

Reconcile against each data tier's **policy**, not a single rigid foreign-key rule.

### 11.6. Embedded vs. Referenced Transitions

If v1 embeds `order.items[]` and v2 extracts `order_items`:

~~~text
source orders_v1:
  1 order, 3 embedded items

target:
  orders_v2: 1 order
  order_items_v2: 3 documents
~~~

Never compare source document count against the sum of both target collections. Compare **entity counts**:

- Order count = unique orders.
- Source item count = sum of `$size(items)` across source orders.
- Target item count = item documents linked to those orders.
- Per-order quantity/amount sums match.

This is why **cardinality contracts** belong in mapping specs.

### 11.7. Unique Constraints Do Not Prove Valid References

An `order_items` row with unique `(orderId, lineNo)` can still point to a non-existent `orderId` and pass its unique index. Run join/invariant checks for orphans alongside application validation or transactions where atomicity is required.

### 11.8. Cross-Tenant Data Is a Security Defect

A migration can get counts and totals 100% right while assigning records to the wrong `tenantId`. Treat this as a **security defect**, higher priority than a 0.1% reporting skew:

~~~text
Cross-tenant reference mismatch = CRITICAL
Source record assigned wrong tenant = CRITICAL
~~~

For sensitive data, never dump raw documents into exception reports; store masked/hashed keys and investigation metadata under strict access controls.

## 12. Reconciling Business Outcomes: Balances, Totals, and Statuses

### 12.1. Never Sum `amount` Without Agreeing on Semantics

Summing `amountMinor` across **all orders** does not equal **revenue**. `CANCELLED` orders retain gross amounts yet contribute zero recognized revenue. Refunds may be negative cash flows or separate transactions. Before aggregating, define:

| Metric | Exact Scope |
|---|---|
| Gross order amount | Sum of line-item prices before discounts/tax/shipping per policy. |
| Net payable | Gross − discounts + tax + shipping. |
| Paid amount | Captured/settled payments per time/currency policy. |
| Net revenue | Recognized revenue per accounting rules, distinct from paid orders. |
| Refund amount | Executed refunds, timing, and sign conventions. |
| Inventory balance | Opening + receipts − shipments + returns + adjustments. |
| Account balance | Opening balance + signed ledger movements. |

**Reconciling the wrong metric definition is worse than not reconciling**, because both sides can agree on wrong numbers.

### 12.2. Total Amount by Tenant After Normalizing Source

~~~javascript
lab.orders_v1.aggregate([
  {
    $project: {
      tenantId: "$tenant",
      amountLong: {
        $convert: {
          input: "$amount",
          to: "long",
          onError: null,
          onNull: null
        }
      },
      rawType: { $type: "$amount" }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      totalAmountMinor: { $sum: "$amountLong" },
      count: { $sum: 1 },
      invalidConversionCount: {
        $sum: {
          $cond: [
            { $eq: ["$amountLong", null] }, 1, 0
          ]
        }
      }
    }
  }
])
~~~

If `invalidConversionCount` is non-zero, **never treat `totalAmountMinor` as a PASS** because `$sum` skips nulls. Generate an exception report first, and compare scope totals only once sources convert cleanly.

### 12.3. Target Totals Must Check Types Separately

~~~javascript
lab.orders_v2.aggregate([
  {
    $group: {
      _id: "$tenantId",
      totalAmountMinor: { $sum: "$amountMinor" },
      count: { $sum: 1 },
      invalidTypeCount: {
        $sum: {
          $cond: [
            { $ne: [{ $type: "$amountMinor" }, "long"] },
            1, 0
          ]
        }
      }
    }
  }
])
~~~

MongoDB's `$sum` accumulator ignores non-numeric values in `$group`. Thus **a string amount silently lowers the sum instead of throwing an error**. Pair `invalidTypeCount` and exact value checks with aggregate sums.

### 12.4. Example of Wrong Totals Despite Equal Document Counts

In our fixture:

| Tenant | Parsed Source Amount | Target `$sum` over Typed Values | Status |
|---|---:|---:|---|
| `tenant-a` | 175,000 | 125,500 | Fails: string amount skipped + extra 500 order. |
| `tenant-b` | 70,000 | 3,000 | Fails: missing order + 3,000 instead of 30,000. |
| **Total** | **245,000** | **128,500** | Failed. |

Numbers in this table derive from the lab fixtures, **not a live MongoDB run**. If business counts only paid orders, apply the same normalized `PAID` filter on both sides to get a matching table.

### 12.5. Verifying Invariant: Line Items = Order Total

In an **example model without tax/discount/shipping**, assume:

\[
\text{order.amountMinor}
=\sum_{i=1}^{n}\text{items}[i].\text{quantity}
\times\text{items}[i].\text{unitPriceMinor}
\]

First ensure `items` is a valid array with integer `quantity` and `long` `unitPriceMinor`. Over properly typed documents:

~~~javascript
lab.orders_v2.aggregate([
  {
    $match: {
      $expr: {
        $and: [
          { $isArray: "$items" },
          { $eq: [{ $type: "$amountMinor" }, "long"] }
        ]
      }
    }
  },
  {
    $addFields: {
      itemTotal: {
        $reduce: {
          input: "$items",
          initialValue: NumberLong("0"),
          in: {
            $add: [
              "$$value",
              { $multiply: [
                  "$$this.quantity",
                  "$$this.unitPriceMinor"
              ]}
            ]
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$itemTotal", "$amountMinor"] }
    }
  },
  {
    $project: {
      orderNo: 1,
      amountMinor: 1,
      itemTotal: 1
    }
  }
])
~~~

This pipeline **runs only on records with an `items` array and `long` amount**. It **does not** replace checks for missing items, wrong element types, or overflow; malformed arrays can cause `$multiply` to fail. Profile data first or use guarded conversions/error reporting in production. Reconcile line items in int64/`Decimal128` and test overflow on large quantities.

### 12.6. Compare Totals Within Identical Scope, Status, and Currency

Never sum VND and USD together into one number. Partition by `currency`, tenant, ledger date, and status:

~~~text
key = (tenantId, currency, recognizedDate, statusCategory)
sourceTotalMinor(key) == targetTotalMinor(key)
sourceCount(key) == targetCount(key)
~~~

If currency conversion applies, use identical exchange rates, timestamps, and rounding rules. Never compare USD-converted targets against raw VND sources without a conversion contract.

### 12.7. Ledgers Demand Exact Checks

Suppose each ledger entry stores signed `deltaMinor` and accounts track `openingBalance`. Invariant:

\[
\text{ClosingBalance}_{a}
=\text{OpeningBalance}_{a}
+\sum_{e\in a}\text{deltaMinor}_e
\]

For transfers between two accounts:

\[
\sum_{e\in \text{transferId}}\text{deltaMinor}_e=0
\]

This is a simplified **double-entry** model assuming zero fees or FX; production must match your exact accounting rules.

### 12.8. Lab Ledger for Reconciliation

~~~javascript
lab.ledger_v2.insertMany([
  {
    _id: "T1:A", transferId: "T1",
    accountId: "A", tenantId: "tenant-a",
    deltaMinor: NumberLong("-30000")
  },
  {
    _id: "T1:B", transferId: "T1",
    accountId: "B", tenantId: "tenant-a",
    deltaMinor: NumberLong("30000")
  },
  {
    _id: "T2:A", transferId: "T2",
    accountId: "A", tenantId: "tenant-a",
    deltaMinor: NumberLong("-10000")
  },
  {
    _id: "T2:B", transferId: "T2",
    accountId: "B", tenantId: "tenant-a",
    deltaMinor: NumberLong("9000") // off by 1000
  }
])
~~~

Check that every transfer balances:

~~~javascript
lab.ledger_v2.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        transferId: "$transferId"
      },
      netDeltaMinor: { $sum: "$deltaMinor" },
      nEntries: { $sum: 1 }
    }
  },
  {
    $match: {
      $or: [
        { netDeltaMinor: { $ne: 0 } },
        { nEntries: { $ne: 2 } }
      ]
    }
  }
])
~~~

In our fixture, `T2` is off by −1,000. Checking `nEntries=2` is a **lab-only rule**; real ledgers can have multi-leg postings (fees/taxes). What matters is asserting **zero net balance per currency + transferId + tenant** and validating types/identities before `$sum`.

### 12.9. Prevent Offsetting Two-Sided Errors

A ledger with a +1,000 error and a −1,000 error in the same group still nets to 0. Also verify:

- Matching entry keysets between source and target.
- Debit/credit leg counts per contract.
- Exact account IDs, tenant, and currency.
- Per-leg amounts, not just totals.
- Duplicate `transferId`/leg IDs and sequence rules.

**Aggregate totals are necessary, not sufficient.**

### 12.10. Inventory

Stock balances must typically satisfy:

\[
\mathrm{stockEnd}
=\mathrm{stockStart}
+\mathrm{receipts}
-\mathrm{shipments}
+\mathrm{returns}
+\mathrm{adjustments}
\]

though backorders/negative inventory may be permitted by business rules. If migrating inventory snapshots to event sourcing, check **snapshot + event replay totals** at aligned watermarks per SKU, warehouse, and tenant—not merely event counts.

### 12.11. Workflow/Status Invariants

For example, a `PAID` order must have a captured payment record, and a `CANCELLED` order cannot receive fulfillment events afterward (barring reversals). When changing enums, reconcile:

- State counts per tenant/time.
- Valid historical state transitions.
- Linked payment/fulfillment records.
- Customer-facing business dashboards.

If the migration retains only **final state**, you cannot prove transition history wasn't lost from the current snapshot alone. Checking history requires retaining event/audit logs with stable event IDs.

### 12.12. Privacy/Business Outcomes

A migration can preserve every raw value yet **violate personal data erasure rules** if the target retains fields meant to be anonymized. Business reconciliation must cover **data access, retention, masking, and residency**, not just money and counts.

## 13. Normalizing Two Schemas for Comparison: Canonical Representation

When two schemas differ in field names, ID types, or status labels, convert both into **the same logical representation** before comparing values.

### 13.1. Canonical Contract for v2 Orders

For `ORD-1001`, a canonical form could be:

~~~json
{
  "entityKey": ["tenant-a", "ORD-1001"],
  "tenantId": "tenant-a",
  "customerId": "C-001",
  "status": "OPEN",
  "amountMinor": "125000",
  "createdAt": "2026-10-01T08:00:00.000Z",
  "items": [
    ["SKU-01", "2", "50000"],
    ["SKU-02", "1", "25000"]
  ]
}
~~~

Here `amountMinor` is encoded as a **normalized decimal string** so different languages compare exact int64 values without JavaScript Number precision loss; `createdAt` normalizes to **UTC ISO instant with fixed milliseconds**. The canonical form is **not** the required MongoDB target schema; it is an internal reconciliation format capturing contracted business fields.

### 13.2. What a Canonical Contract Must Specify

1. **Which fields are kept/renamed/derived/dropped** and why.
2. **Key encoding**: avoid naive delimiters that can collide.
3. **Type normalization**: whether int32 → int64 is permitted; long vs. decimal; epochMs dates.
4. **Null/missing rules**: whether distinct, whether defaults apply.
5. **Unicode/case/collation**: exact match vs. NFKC/trim/case folding policy.
6. **Arrays**: ordered list vs. unordered set/multiset; whether duplicates carry meaning.
7. **Nested objects**: field order irrelevant vs. raw-byte consumers.
8. **Unknown fields**: dropped per allowlist vs. flagged as exceptions.
9. **Numeric precision/rounding**: exact vs. per-field tolerance.
10. **Version** of the contract and canonicalizer; stamp every reconciliation run.

### 13.3. Distinguish Null, Missing, and Default

~~~text
source: field missing
target: field = null
~~~

If the contract states **missing ≠ explicit null**, preserve separate `MISSING` and `NULL` tags in the canonical form. If the contract turns missing into default `null`, document it explicitly since it affects queries, indexes, and app serialization.

### 13.4. Sorting Arrays Properly

If `items` carries `lineNumber`, order can be keyed by `lineNumber`. If the target reordered items while keeping `lineNumber`, canonicalize by sorting on `lineNumber` **only when the contract specifies so**. For sets like tags, sort and deduplicate; for ledger postings, duplicates carry meaning and must never be deduplicated.

### 13.5. Design-Level Java Canonicalization Pattern

~~~java
record CanonicalItem(
    String sku,
    long quantity,
    long unitPriceMinor) {}

record CanonicalOrder(
    String tenantId,
    String orderNo,
    String customerId,
    String normalizedStatus,
    long amountMinor,
    java.time.Instant createdAt,
    java.util.List<CanonicalItem> items) {}

// Two adapters sharing the same contract for different input schemas:
CanonicalOrder fromLegacy(org.bson.Document legacy);
CanonicalOrder fromTarget(org.bson.Document target);
~~~

Both functions must emit **identical objects** for equivalent records, parsing per contract and rejecting invalid values. Never generate source and target using the exact same buggy migration helper and treat equality as proof: a **shared bug** passes false matches on both sides.

### 13.6. Never Use BSON Field Order for Semantic Equality

Two BSON documents can differ in raw bytes due to key ordering, numeric BSON types, or serializer versions. When semantics care only about fields and values, sort into a canonical order. Raw `JSON.stringify` of two JavaScript objects is likewise an unreliable equality oracle if property order or `undefined` handling differs.

### 13.7. Independent Checks Beyond Canonical Comparison

If both source and target converters share a bug “divide amount by 10,” canonical objects still match. Always verify **independent invariants**: gross order amount = line items, balances = ledger, valid state maps, intact UTC instants, and preserved keys/cardinalities. Canonical equality beats raw comparison, yet never replaces business checks.

## 14. Hashes and Checksums to Localize Drift

### 14.1. Why Not Hash Raw BSON Directly?

Two semantically equivalent documents can differ in `_id`, field names, status labels, raw string/long types, and intentional metadata. Hashing raw BSON/JSON produces false mismatches. **Canonicalize per contract** first, using identical encoding/versions on both sides.

### 14.2. Building Per-Record Hashes

~~~text
Source doc                          Target doc
    |                                   |
    v                                   v
Canonicalize v1                     Canonicalize v2
    |                                   |
    v                                   v
Deterministic encoding             Same encoding/version
    |                                   |
    v                                   v
SHA-256 fingerprint                SHA-256 fingerprint
    |                                   |
    +---------- compare by stable key --+
~~~

Compare hashes by **immutable entity key** at a verified snapshot/watermark. On mismatch, authorized readers pull records for a **field-level diff**. Hashes are a triage tool, not a replacement for validating keys, counts, relations, and business rules.

### 14.3. Deterministic Encoding Must Be Strictly Defined

~~~text
reconcile-contract-version: 3
record:
  for each field in sorted canonical name order:
    nameLength + UTF-8 name
    explicit type tag
    valueLength + value bytes
  arrays:
    element count + elements in business-defined order
  null: explicit NULL tag
  missing: explicit MISSING tag if semantically distinct
~~~

Never concatenate `tenantId + orderNo + amount` without lengths/tags: `("ab","c")` and `("a","bc")` both yield `"abc"`. In Java, run `MessageDigest.getInstance("SHA-256")` over canonical bytes; **hashing does not normalize data by itself**.

### 14.4. Do Matching Hashes Prove Absolute Equivalence?

Finite hashes carry theoretical collision risk, though SHA-256 makes collisions practically negligible. In reality, the biggest bugs come from **wrong normalization, omitted fields, or mismatched timestamps**. For money and permissions, retain exact business checks and field-level verification on critical partitions.

### 14.5. Partition-Level Hashes

~~~text
Partition by (tenantId, month, key-range)
  |
  +-- source count and sorted canonical fingerprints
  +-- target count and sorted canonical fingerprints
  |
  v
Deterministic partition checksum
  |
  +-- equal => likely identical under contract
  |
  +-- mismatch => drill down to key and field diffs
~~~

Never hash records in **collection natural order**, since MongoDB does not guarantee stable natural order. Sort by a deterministic key or use commutative aggregations with collision analysis; sorted merges are safest.

### 14.6. Merkle Trees for Massive Datasets

~~~text
               ROOT HASH
               /       \
           Range A     Range B
           /   \       /    \
         A1     A2   B1      B2
~~~

Compare roots and drill into differing branches. Ensure range boundaries, record ordering, snapshots, and hash schema versions stay identical. If a record landed in the **wrong partition due to a bad key**, verify key mappings first.

### 14.7. Checksums Do Not Replace Exception Reports

A hash mismatch only says “something differs,” not **what broke**. Exception reports need keys/partitions, expected vs. actual canonical field hashes, diff codes, severities, source snapshot/watermark, and remediation ticket links. Never dump PII or credentials into widely shared reports.

### 14.8. Avoid Memory Spikes

Never call `collection.find().toArray()` over terabytes. Use indexed cursors/key ranges, streaming hashes, memory budgets, batch caps, and throttling. A checksum job saturating DB CPU/IOPS can break SLOs; inspect `explain("executionStats")` and run in approved windows.

## 15. Reconciling Large Data: Streaming Merge Joins and Partitioning

`$lookup` works well when collections share one database and have indexes. Yet source → target migrations often span **two clusters**, massive sizes, or separate credentials—requiring a **reconciliation service** that never loads entire collections into RAM.

### 15.1. Streaming Merge Join of Two Sorted Streams

Suppose both readers emit rows:

~~~text
CanonicalKey(tenantId, orderNo) | canonicalFingerprint | version
~~~

Sorted ascending by key:

~~~text
Source                           Target
("a","001"), h1                  ("a","001"), h1
("a","002"), h2                  ("a","003"), hX
("a","004"), h4                  ("a","004"), hY
~~~

Algorithm:

~~~text
while source.hasRow and target.hasRow:
    if source.key < target.key:
        emit MISSING_TARGET(source)
        advance source
    else if source.key > target.key:
        emit EXTRA_TARGET(target)
        advance target
    else:
        if hash/source-values differ:
            emit VALUE_DIFF(source,target)
        advance both

emit remaining source rows as MISSING_TARGET
emit remaining target rows as EXTRA_TARGET
~~~

When each reader streams sorted by the same **canonical key/collation**, memory stays near \(O(1)\) for cursor buffers and merge CPU is \(O(N+M)\) **excluding sort cost**. Ensure MongoDB uses supporting indexes; large in-server sorts still cost heavy I/O and RAM.

### 15.2. Detect Duplicates Before Merging

If source or target has two rows sharing a key, a naive 1-to-1 merge yields false diffs. Instead:

- Group adjacent identical keys into runs.
- If cardinality exceeds expected, emit `DUPLICATE_SOURCE`/`DUPLICATE_TARGET`.
- Compare multiple records per domain contract (fail if strictly 1-to-1).
- Never pick one record arbitrarily to “drop the duplicate” and report PASS.

### 15.3. Partition by Key Range

~~~text
Reconcile Run 2026-11-14
  Partition 00: tenant-a, IDs A000-A999
  Partition 01: tenant-a, IDs B000-B999
  Partition 02: tenant-b, IDs A000-A999
  ...
~~~

Partition boundaries must be **stable, non-overlapping, and gap-free**. Never partition with `skip/limit` offsets over live collections because inserts/deletes shift pages. Use **keyset/range filters** over immutable indexed keys or snapshot cuts.

### 15.4. Retry Only Failed Partitions

When partition #17 fails due to network errors:

1. Preserve manifest, run ID, `mappingVersion`, and snapshot cut.
2. Mark `FAILED_RETRYABLE` with error reason.
3. Retry only that partition under identical cuts/canonical rules with bounded backoff.
4. Never merge results from two different snapshots into one PASS.
5. If the snapshot/watermark can no longer be held, restart per recovery plan rather than mixing timestamps.

### 15.5. Do Not Automatically Rely on `readPreference=secondary` for Consistency

Reading secondaries offloads the primary, yet **replication lag and inter-node skew** break baseline alignment without snapshot/optime coordination. For critical reconciliation, prioritize a read mode matching your consistency contract before optimizing read routing.

### 15.6. Protect Databases from Reconciliation Jobs

Enforce limits on:

- Active partitions and concurrent queries.
- Cursor batch sizes, max durations, and retry caps.
- `maxTimeMS` and client deadlines per op.
- CPU/IOPS/network budgets inside maintenance windows.
- Indexed queries only; prevent unexpected cluster-wide `COLLSCAN`s.
- Pause/resume when production latency or replication lag spikes.

**Reconciliation is also a workload**: an overly aggressive checker can destabilize production and cause source/target drift from retries.

### 15.7. Stratified Sampling

When business permits sampling for non-critical data:

~~~text
Stratify by:
  tenant size
  migration transform type
  schema version
  date range
  rare enum values
  known malformed source groups
~~~

A flat 1% random sample misses rare, high-risk edge cases. **Oversample new, rare, heavily transformed, or historically buggy cohorts**, reporting explicit confidence and coverage. Never use a passing sample to waive exact checks on payments or permissions.

### 15.8. Compare Real Application Query Results

Beyond document diffs, run **dual-read/shadow queries** with authorized parameters:

~~~text
query: listPaidOrders(tenant, dateRange)
source adapter -> canonical result
target adapter -> canonical result
compare IDs/order/totals and latency
~~~

Shadow reads must trigger zero side effects, enforce authorization/PII masking, and align cuts when needed. Results can differ due to in-flight writes, unstable sorts, or search index lag, so verify **watermarks and query semantics** before declaring a bug.

## 16. Reconciling Online Migrations: Backfill + CDC

### 16.1. Migration Lifecycle

A practical online workflow:

~~~text
PREPARE
   |
   v
BASELINE / SNAPSHOT T0
   |
   v
BACKFILL historical partitions
   |
   v
CAPTURE/APPLY CDC since T0
   |
   v
SHADOW READ + CONTINUOUS RECONCILIATION
   |
   v
CATCH-UP / VERIFIED WATERMARK T1
   |
   v
FREEZE OR COORDINATE FINAL WRITES
   |
   v
FINAL EXACT RECONCILIATION
   |
   +-- FAIL -> repair/rollback/hold
   |
   +-- PASS -> CUTOVER
                   |
                   v
              MONITOR/ROLLBACK WINDOW
~~~

Never start CDC **after** backfill without replaying writes that occurred during the historical scan; mutations between snapshot and stream start will be lost.

### 16.2. Handling Insert, Update, Replace, and Delete

| Event Type | Target Action per Contract | Required Checks |
|---|---|---|
| Insert | Canonical convert + deterministic upsert. | Single target key, right tenant/type. |
| Update | Convert latest state or version-aware patch. | Never overwrite newer events with older ones. |
| Replace | Recompute target fields from full replacement. | Remove fields stripped by replacement. |
| Delete | Delete/tombstone/archive per policy. | Zero lingering extra target records. |
| DDL/rename/drop | Handle per runbook or halt. | Never silently skip namespaces. |

MongoDB change streams emit `resume tokens` and events per options; **do not assume every update event includes the entire post-update document**. If using `fullDocument` lookup, verify docs on `fullDocument`, concurrent write races, and retention. CDC consumers must reconstruct **the exact versioned final state**.

### 16.3. Idempotent Apply

An event can replay if crashing before checkpointing:

~~~text
Apply event E100 to target
Target write succeeds
Process crashes before recording E100 checkpoint
Restart resumes at E100
Event E100 delivered again
~~~

Stay safe via:

- Deterministic target `_id`/business keys.
- Version/sequence-gated idempotent upserts.
- Persisting checkpoints only after durable apply per policy.
- Avoiding duplicate child docs or external side effects on replay.
- Classifying duplicate-key errors rather than treating every E11000 as success.

### 16.4. Ordering and Stale Events

When records carry `sourceVersion`:

~~~text
target version 21
incoming event version 20  -> do not overwrite version 21
incoming event version 22  -> apply, then checkpoint
~~~

MongoDB change stream and transaction event ordering follow topology-specific rules; **never invent a global incrementing counter** if the source lacks one. In multi-shard/multi-collection flows, use version gates against out-of-order writes, or connectors guaranteeing per-key order and resync on gaps.

### 16.5. Dual-Write Can Yield Partial Success

~~~text
App writes source: SUCCESS
App writes target: TIMEOUT
App returns HTTP 500
Retry comes in with same business request
~~~

A target timeout **does not prove the write failed to commit**. Use stable idempotency keys, unique business indexes, and read-repair; two `save` calls across separate MongoDB clusters do not magically form a distributed transaction.

### 16.6. Watermark Convergence

Never declare PASS when:

~~~text
Source high watermark = E13000
Target applied = E12700
Lag = 300 events
~~~

Even if counts “coincidentally match,” the target lacks 300 events. Cutover criteria typically require:

~~~text
1. All historical partitions completed.
2. No unresolved transform errors/quarantine blockers.
3. Target applied every event through agreed cut T.
4. No replay gap; resume token/lag verified.
5. Key, type, constraint and business checks PASS at T.
~~~

Never treat “lag under 1 second” as **exactly caught up** when 100 writes/s are flowing and zero-loss is required.

### 16.7. Change Streams Do Not Retain History Forever

Oplog/change stream retention shrinks when write rates surge. If backfill takes 3 days while oplog retains 1 day, consumers can **lose resumability from T0**. Watch window/lag and keep snapshot-rebuild plans ready rather than trusting coincidental count matches.

### 16.8. Final Cut and Rollback

Online migrations typically need a **coordinated final cut** (short quiesce or write-routing fence) to:

1. Lock source-of-truth/writer ownership.
2. Wait for CDC to catch up past the fence.
3. Run final critical reconciliation (or verify immutable proofs).
4. Shift reads and writes to target.
5. Block old writers from mutating the source erroneously.
6. Maintain a rollback/run-forward strategy covering post-cutover writes.

Once the target receives fresh writes, rolling back to source **is no longer trivial** without reverse replication or backward reconciliation. Never write “rollback = swap connection string” without accounting for new writes.

## 17. Exception Reports, Quarantine, and Controlled Repair

Reconciliation must produce auditable **artifacts**, not a single “count mismatch” log line. Every exception needs an error type, evidence, severity, owner, and post-remediation status.

### 17.1. Actionable Error Taxonomy

| Code | Description | Typical Action |
|---|---|---|
| `MISSING_TARGET` | Source record absent at target at same cut. | Check CDC lag; resync key/partition. |
| `EXTRA_TARGET` | Target record lacks matching source. | Check deletes/tombstones/seeds/excluded scope. |
| `DUPLICATE_KEY` | Multiple records share one business key. | Halt unique rollout; analyze collision. |
| `WRONG_BSON_TYPE` | Field present with wrong BSON type. | Reconvert from source with precision checks. |
| `MISSING_REQUIRED` | Required field absent. | Trace source/mapping; never guess defaults. |
| `INVALID_ENUM` | State outside mapping table. | Quarantine; update contract if valid new state. |
| `VALUE_DIFF` | Canonical fields disagree. | Field-level diff; compare source/versions. |
| `REFERENCE_ORPHAN` | Relation points to missing entity. | Check tenant, soft deletes, retention. |
| `CROSS_TENANT` | Relation or record mapped to wrong tenant. | Security incident; block cutover, escalate. |
| `BUSINESS_INVARIANT` | Ledger/order/inventory balance mismatch. | Investigate independently; never plug totals. |
| `CDC_GAP` | Missing history/replay gap; skewed watermark. | Never pass; resnapshot/resync. |
| `INVALID_SOURCE` | Source record already violates contract. | Quarantine for business remediation; never skip silently. |

### 17.2. Sample Exception Record

~~~json
{
  "runId": "orders-v2-20261114-001",
  "partitionId": "tenant-b:2026-10",
  "category": "VALUE_DIFF",
  "severity": "HIGH",
  "entityKeyHash": "sha256:<computed>",
  "fieldPath": "amountMinor",
  "expectedCanonical": "30000",
  "actualCanonical": "3000",
  "mappingVersion": "orders-v1-to-v2.3",
  "snapshotOrWatermark": "<verified cut>",
  "status": "OPEN",
  "ownerTeam": "migration",
  "createdAtUtc": "2026-11-14T02:10:00Z",
  "resolution": null
}
~~~

This illustrates a JSON report structure. `entityKeyHash` must be **actually computed**, never a dummy placeholder string. For PII, omit raw inputs unless authorized and encrypted; store redacted/hashed identifiers and secure evidence links.

### 17.3. Severity Must Reflect Impact

Example rubric:

- **CRITICAL:** cross-tenant leak, payment/ledger imbalance, missing critical keys, unrecovered CDC gap, retention violation.
- **HIGH:** wrong financial types/values, duplicate unique keys, broken required relations.
- **MEDIUM:** optional UI/analytics field mismatch or rebuildable derived summary skew.
- **LOW/INFO:** documented intentional shifts, non-business metadata per contract.

**Never** rely on error percentages alone: one critical failure outweighs 1,000 optional metadata diffs.

### 17.4. Exception State Machine

~~~text
OPEN
  |
  +--> INVESTIGATING
  |        |
  |        +--> FIX_PENDING
  |        |       |
  |        |       v
  |        |     RECHECK
  |        |       |
  |        |       +--> RESOLVED (verified)
  |        |       +--> OPEN (still mismatched)
  |        |
  |        +--> ACCEPTED_INTENTIONAL (approved)
  |
  +--> FALSE_POSITIVE (with evidence)
~~~

Never sweep everything to `IGNORED` with a blanket filter. An intentional exception needs a **policy ID, approver, version, and expiry**, especially if ingestion continues.

### 17.5. Quarantining Unconvertible Records

A source row `amount:"12,50"` fails integer parsing; never insert `amountMinor:0` just to “hit counts.” Instead:

1. Preserve raw source reference and failure reason.
2. Quarantine the key in an RBAC-protected remediation store.
3. Determine whether source data was dirty or mapping rules lacked a case.
4. Obtain business approval for repair/conversion.
5. Replay deterministically with the same idempotency key.
6. Re-reconcile the key/partition and archive proof.

Never let quarantine become a permanent dumping ground for skipping data without owners or SLAs.

### 17.6. Remediation Must Not Lose Authoritative Updates

If target holds a wrong amount, repair safely:

~~~text
Identify stable key + source version
      |
      v
Re-read authoritative source at approved cut/version
      |
      v
Apply deterministic mapping
      |
      v
Conditional update with expected version
      |
      v
Verify target type/value/invariants
      |
      v
Record fix ticket/audit/reconciliation evidence
~~~

Never fix targets by “adding 27,000 to totals” or setting invalid entries to zero/mean. If target already accepted post-cut writes, guard repairs by version so valid updates are never overwritten.

### 17.7. Reconciliation Should Have Independent Ownership

A migration job claiming “I copied everything” is not enough. Prefer an **independent reconciliation implementation** reading authoritative source/target and the reviewed contract. Shared logic between converter and checker can mask shared bugs into false PASSes.

## 18. Reconciling with the Java MongoDB Driver: Streaming and Type-Safe

The Java snippet below uses the MongoDB Java Sync Driver for **bounded source cursors + indexed target lookups**. It demonstrates the technique, not a production distributed reconciler—production needs metrics, snapshots, retries, sharding, pagination, and reverse scans.

### 18.1. Verifying Exact 1-to-1 Target Matches

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;
import java.util.ArrayList;
import java.util.List;

public final class OrderReconcileExample {
    public static void run(
            MongoCollection<Document> source,
            MongoCollection<Document> target) {

        long missing = 0;
        long duplicate = 0;
        long wrongAmount = 0;
        long examined = 0;

        try (MongoCursor<Document> cursor = source
                .find()
                .batchSize(200)
                .iterator()) {
            while (cursor.hasNext()) {
                Document s = cursor.next();
                ObjectId legacyId = s.getObjectId("_id");

                // Requires index on target.legacyId for large datasets.
                List<Document> hits = target.find(
                        Filters.eq("legacyId", legacyId))
                    .limit(2)
                    .into(new ArrayList<>());

                examined++;

                if (hits.isEmpty()) {
                    missing++;
                    continue;
                }
                if (hits.size() > 1) {
                    duplicate++;
                    continue;
                }

                Document t = hits.get(0);
                Long expected;
                try {
                    expected = Long.valueOf(s.getString("amount"));
                } catch (RuntimeException invalid) {
                    // Production: report INVALID_SOURCE and quarantine key.
                    wrongAmount++;
                    continue;
                }

                Object actual = t.get("amountMinor");
                if (!(actual instanceof Long)
                        || !expected.equals(actual)) {
                    wrongAmount++;
                }
            }
        }

        System.out.printf(
            "examined=%d missing=%d duplicate=%d wrongAmount=%d%n",
            examined, missing, duplicate, wrongAmount);
    }
}
~~~

**Notes:**

- Java Sync Driver maps BSON int64 to `java.lang.Long` in `Document`; `instanceof Long` verifies **exact type** rather than loose numeric equality.
- `Long.valueOf(s.getString("amount"))` holds only when source contracts use valid integer strings. Check missing, null, Unicode digits, whitespace, overflow, and currency in production.
- `limit(2)` detects **more than one target match**, not exact duplicate totals above 2; count large duplicate groups separately.
- This snippet does not yet check **extra targets**, cross-tenant mismatches, statuses, child items, checksums, ledgers, or CDC cuts.
- Apply proper `readConcern`/snapshots/watermarks; reading two clusters at separate times is not automatically consistent.
- Never print raw PII or credentials in reports.

### 18.2. Never Instantiate a `MongoClient` per Record

**Wrong:**

~~~java
for (Document sourceRow : sourceRows) {
    try (MongoClient c = MongoClients.create(uri)) {
        // check one record ...
    }
}
~~~

Opening topology discovery, connection pools, and TLS handshakes per row destroys performance. Create **shared `MongoClient` instances** per cluster/reconcile job with bounded pools and close them when the job finishes. For two clusters, maintain two long-lived clients outside the loop.

### 18.3. Bounded Parallelism

To scale throughput, run partitions in bounded parallel workers:

~~~text
partitionQueue (bounded)
       |
       +-- worker 1 -> source cursor + target batch lookups
       +-- worker 2 -> source cursor + target batch lookups
       +-- worker 3 -> source cursor + target batch lookups
       +-- worker 4 -> source cursor + target batch lookups
       |
       v
append-only reconciliation report + checkpoints
~~~

Never spawn one task per document across 100 million records; it blows up memory and saturates MongoDB. If 4 workers are insufficient, ramp up incrementally while watching CPU, IOPS, pool wait times, and replication lag.

### 18.4. Optimizing Target Lookups in Batches

Per 200-doc source batch, fetch matching targets in one call with `Filters.in("legacyId", ids)`:

~~~java
var sourceBatch = /* max 200 source Documents */;
var legacyIds = sourceBatch.stream()
    .map(s -> s.getObjectId("_id"))
    .toList();

List<Document> targetBatch = target
    .find(Filters.in("legacyId", legacyIds))
    .into(new ArrayList<>());
~~~

This illustrates **batched lookups**; group hits by `legacyId`, flag duplicates/missing, and bound BSON query/response sizes and RAM. Never pass millions of IDs in a single `$in`.

### 18.5. Canonical Comparison in Java

In production, separate:

~~~java
record Diff(String code, String entityKey, String fieldPath) {}

CanonicalOrder parseLegacy(Document source);
CanonicalOrder parseTarget(Document target);

List<Diff> compare(CanonicalOrder expected, CanonicalOrder actual);
~~~

These method signatures are **design blueprints**, not a complete compilable class. Test with fixtures covering missing/null, invalid enums, int32-vs-int64, date timezones, `Decimal128`, array reordering, overflow, tenant mismatches, and unknown fields.

### 18.6. Cursors, Timeouts, and Resume

Large Java cursors require `try-with-resources`/`close()`, `batchSize`, and checkpoints keyed by **last processed stable key**, never row offsets. If interrupted mid-run, resume unfinished ranges **under the exact same snapshot/cut**; if that snapshot expired, restart cleanly on a fresh cut without mixing runs in one report.

## 19. Spring Data MongoDB and Application-Level Reconciliation

Spring Data MongoDB streamlines mapping, repositories, and transactions. However, production reconciliation must distinguish **entity-level Java validation, actual stored BSON in the collection, and cross-document business rules**.

### 19.1. Schema v2 DTO

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders_v2")
public class OrderV2 {
    @Id
    private String id;
    private String tenantId;
    private String orderNo;
    private String customerId;
    private String status;
    private Long amountMinor;
    private Instant createdAt;
    private List<OrderItemV2> items;
    private Integer schemaVersion;
    @Version
    private Long version;

    // Constructors/accessors per Spring Data mapping.
}
~~~

In Java, `Long amountMinor` **does not prove server storage is BSON `long`** when multiple clients or scripts write to the collection. Spring Data converts types on read, so exact-type reconciliation must query **BSON types in MongoDB** or read raw `Document`/`BsonDocument` rather than trusting deserialized DTOs alone.

### 19.2. Bean Validation Does Not Replace MongoDB Validators

Annotations:

~~~java
@NotNull
@PositiveOrZero
private Long amountMinor;
~~~

only apply at Spring boundaries enforcing Bean Validation. They **do not block** admin scripts, legacy services, or external jobs writing directly to MongoDB. Use `$jsonSchema`/unique indexes for storage guarantees and queries/transactions/services for cross-collection invariants.

### 19.3. Finding Schema Mismatches with `MongoTemplate`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import java.util.List;

public List<Document> findWrongAmountTypes(MongoTemplate template) {
    BasicQuery q = new BasicQuery(
        "{ $expr: { $ne: [" +
        "    { $type: '$amountMinor' }, 'long' " +
        "] } }");
    q.limit(100);

    return template.find(q, Document.class, "orders_v2");
}
~~~

This `BasicQuery` pulls **at most 100 exception samples**, insufficient to certify the entire collection clean. Full-scale reconciliation requires aggregation `$group` or streaming cursors—never declare PASS from a `limit(100)` query.

### 19.4. `ReactiveMongoTemplate`

In WebFlux:

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.bson.Document;
import reactor.core.publisher.Flux;

Flux<Document> findWrongTypes(ReactiveMongoTemplate template) {
    BasicQuery q = new BasicQuery(
        "{ $expr: { $ne: [" +
        "    { $type: '$amountMinor' }, 'long' " +
        "] } }");
    q.limit(100);
    return template.find(q, Document.class, "orders_v2");
}
~~~

Reactive I/O reduces blocked threads yet does not make an unindexed `$expr` scan cheap. Bound concurrent partitions and stream buffers, and never call `collectList()` over millions of documents.

### 19.5. Repository Finders Are Not Enough for Reconciliation

~~~java
interface OrderV2Repository extends MongoRepository<OrderV2, String> {
    long countByTenantIdAndStatus(String tenantId, String status);
}
~~~

Derived finders help for **count metrics**, yet verifying BSON types, cross-collection `$lookup`, duplicates, CDC watermarks, ledger balances, and canonical equivalence requires `MongoTemplate`/aggregations or a dedicated reconciliation service. Never cram complex checks into unreadable derived repository methods.

### 19.6. Two Datasources and Transaction Boundaries

When source and target are separate MongoDB clusters, two `MongoTemplate`/client instances have **separate transaction contexts**. `@Transactional` on the target does not span source cluster, target cluster, and Kafka atomically. Online migrations require snapshots + CDC/idempotent apply + reconciliation watermarks rather than assuming cross-system atomic commits.

### 19.7. Optimistic Locking and Races During Repair

`@Version` detects stale writes on compatible repository `save` paths. Still, remediating `amountMinor` while the target accepts fresh order edits must check **expected source/target version** in the update filter:

~~~java
// Pseudocode: update only if sourceVersion is still 42.
Query q = Query.query(Criteria.where("_id").is(targetId)
    .and("sourceVersion").is(42L));
Update u = new Update()
    .set("amountMinor", correctAmount)
    .set("sourceVersion", 43L);

template.updateFirst(q, u, "orders_v2");
~~~

`sourceVersion` and `43L` are illustrative; versions must derive from authoritative source events/contracts rather than inventing arbitrary increments.

### 19.8. Reading Raw BSON When Exactness Matters

For `Decimal128`, `ObjectId`, BSON `Date`, and `int32`/`int64`, mappers can flatten raw type distinctions into generic Java types. Exact reconciliation should read:

~~~java
MongoCollection<org.bson.BsonDocument> raw = database
    .getCollection("orders_v2", org.bson.BsonDocument.class);
~~~

and inspect `BsonValue.getBsonType()` / `isInt64()` / `isDecimal128()` directly. Never guess BSON storage types from REST API JSON responses.

## 20. Testing Your Reconciliation Strategy

### 20.1. Unit Tests for Mapping Contracts

Every rule needs positive, negative, and boundary test cases:

| Rule | Positive | Negative / Boundary |
|---|---|---|
| `amount` string → int64 | `"125000" → 125000L` | `"12,50"`, empty, null, overflow, whitespace. |
| Status mapping | `"new" → "OPEN"` | `"unknown"`, unexpected uppercase variants. |
| Date | Preserves exact UTC instant. | Timezone-less local dates, DST ambiguities. |
| Tenant | Keeps `tenant-a`. | Shifted to `tenant-b`, missing tenant. |
| `ObjectId` legacy link | Matches source `ObjectId`. | Hex string instead of `ObjectId`, duplicate `legacyId`. |
| `items` | Correct sum and quantities. | Missing/empty array, wrong element type, reordered semantics. |
| Currency | Accurate integer minor units. | Mixed VND/USD, wrong scale, rounding drift. |
| Optional fields | Missing/null per contract. | Defaults silently altering meaning. |

### 20.2. Adversarial Fixtures

Build a test suite containing:

- Equal total counts with different keysets.
- Duplicate business keys inside one tenant.
- Identical `orderNo` across two distinct tenants (**valid**).
- Right value with wrong BSON type.
- Right BSON type with wrong value.
- Malformed source formats and conversion overflows.
- Missing/null/type mismatches.
- Reordered arrays (allowed or disallowed per rule).
- Cross-tenant references.
- Payment/ledger off by 1 minor unit.
- Updates arriving post-backfill, deletes/tombstones, CDC replays.

If your checker passes when these injected defects are present, fix **the checker**, not only the migration code.

### 20.3. Property-Based and Metamorphic Testing

Useful properties:

~~~text
for every valid legacy order x:
  canonicalizeLegacy(x) == canonicalizeTarget(migrate(x))

for every target accepted by validator:
  required types / enum / indexes obey contract

for every business transfer:
  sum(postings.deltaMinor) == 0

applying the same CDC event twice:
  final target state is unchanged
~~~

Property-based tests generate wide edge-case coverage. Still, comparing `canonicalizeLegacy` against `migrate` when both share a bug produces false PASSes—always pair with **independent expected fixtures and invariants**.

### 20.4. Integration Tests Against Real MongoDB

Mock repositories cannot verify `$convert`/`$type`, indexes, unique constraints, `$lookup`, BSON codecs, or transactions. Use a test MongoDB lab or Testcontainers replica set matching your production server version:

1. Seed fixtures.
2. Run migration on the test collection.
3. Run reconciliation.
4. Assert expected exceptions are caught, and pass once repaired.
5. Test duplicate-key/validator errors and rollbacks.
6. Clean up the test namespace safely.

**Never** let migration/reconciliation tests mutate production due to misconfigured URIs; enforce strict environment/credential guards.

### 20.5. Compare Against an Independent Source of Truth

If the business maintains audited accounting ledgers or financial exports, reconcile post-migration totals against them. When both source and target share a pre-existing app bug, source-to-target equality passes while actual balances are wrong. Reconciling against **independent invariants** prevents false confidence.

### 20.6. Load Testing the Reconciliation Job

Measure not just runtime, but also:

- DB p95/p99 latency while the checker runs.
- CPU, IOPS, cache, and lock impact.
- Checker memory footprint while streaming keys.
- Network transfer and driver pool wait times.
- CDC lag and oplog history windows.
- Retry behavior across primary stepdowns.
- Restart/resume from partition checkpoints.

Never let the reconciliation checker trigger a production outage right before cutover.

### 20.7. Dry-Run and Canary

Progression:

~~~text
Small lab fixture -> dev contract tests
       |
       v
Staging copy/snapshot -> full reconciliation
       |
       v
Production read-only shadow comparison
       |
       v
Small tenant/range canary
       |
       v
Full rollout + final exact reconciliation
~~~

Ensure canaries include small yet high-risk cohorts—never test only the “easiest tenant” and extrapolate safety globally.

### 20.8. Regression Testing After Mapping Rule Changes

If the mapping contract bumps from v2.3 to v2.4:

1. Document why it changed and which data ranges are affected.
2. Lock v2.3 expected behaviors into regression fixtures.
3. Add fixtures for the new v2.4 rules.
4. Re-run previously passed partitions impacted by the change.
5. Never mix v2.3 and v2.4 hashes inside one partition summary.
6. Update versioned manifests and exception resolutions.

## 21. SLOs, Monitoring, and Reconciliation Dashboards

A reconciliation run can succeed technically yet lack **sufficient coverage**. Break dashboards down by batch, tenant, schema version, business criticality, and cut/watermark.

### 21.1. Core Metrics

| Metric | Unit | Meaning |
|---|---|---|
| `source_count` / `target_count` | Documents | Counts per scope/partition. |
| `source_unique_keys` / `target_unique_keys` | Keys | Separates duplicates from raw doc counts. |
| `missing_target_count` | Keys | Source records absent at target at same cut. |
| `extra_target_count` | Keys | Target records lacking valid source. |
| `duplicate_key_count` | Keys/groups | Keys with wrong cardinality. |
| `wrong_bson_type_count` | Documents/fields | Schema type violations. |
| `missing_required_count` | Documents/fields | Absent mandatory fields. |
| `invalid_enum_count` | Documents/fields | Unmapped state values. |
| `reference_orphan_count` | References | Broken links per business policy. |
| `business_invariant_failures` | Groups | Broken ledger/payment/inventory outcomes. |
| `value_diff_count` | Keys/fields | Canonical value mismatches. |
| `unresolved_critical_count` | Exceptions | Cutover blockers. |
| `cdc_lag_events` / `cdc_lag_seconds` | Events/seconds | Target distance behind source watermark. |
| `verified_partitions` | Partitions | Actual coverage passing checks. |
| `reconcile_duration_seconds` | Seconds | Speed and cutover window fit. |
| `reconcile_failure_rate` | % | Tool/network/conversion failure rate. |

### 21.2. Define the Coverage Denominator Explicitly

~~~text
coverage = verified_in_scope_keys / all_in_scope_source_keys
~~~

If target holds extra keys or source holds duplicates, source-only coverage is incomplete; track **reverse coverage** and partition completion too. Never wave away 0.1% unchecked critical payments under “99.9% coverage.”

### 21.3. Differential Dashboard

Illustrative dashboard:

~~~text
Reconciliation run: orders-v2-20261114-001
Mapping version:   v2.3
Cut/Watermark:     VERIFIED T1
Partitions:        180/200 verified
Missing keys:      12
Extra keys:        3
Wrong BSON types:  21
Value diffs:       8
Critical blockers: 2
Ledger imbalance:  1
Go/No-Go:          NO-GO
~~~

**Never paint everything green merely because `migrated rows == source count`.** Here 180/200 partitions is incomplete coverage with critical blockers; status must stay NO-GO.

### 21.4. Quality and Progress Alerts

Tier alerts by severity:

- **Critical:** any cross-tenant record, unexplained ledger imbalance, unrecoverable CDC gap, or missing critical business key.
- **High:** rising invalid types/duplicates or missing keys post-catch-up.
- **Operational:** stalled partitions, failed checksum jobs, CDC lag nearing oplog retention window.
- **Warning:** low-risk field diffs exceeding approved tolerances.

Scope metrics by **source/target cut and mapping version**—never blend runs across differing versions.

### 21.5. Monitoring Database Impact

Watch separately:

- CPU, IOPS, network, and WiredTiger cache.
- Application query latency p95/p99.
- Driver pool checkout wait times and active connections.
- `$lookup`/`$group` execution times and explain plans.
- Replication lag and CDC lag.
- Reconciliation queue depth and backpressure.

If the checker pushes production p99 up, **throttle or pause** per runbook while saving checkpoints; never chase a deadline into a bigger outage.

### 21.6. Metric Labels and Security

Never put `orderNo`, `customerId`, or PII into Prometheus labels, which explodes cardinality. Use bounded `runId`, `partitionGroup`, `errorCode`, `severity`, and `schemaVersion`. Keep record details inside a **secure exception store** governed by RBAC and retention.

## 22. Runbook: Closing Reconciliation Before and After Cutover

### Stage A — Preparation

1. Define authoritative source, v1/v2 schemas, tenants/partitions, and approved exclusions.
2. Lock `mappingVersion`, canonicalization rules, and expected key cardinalities.
3. Document business invariants by currency/status/time, owners, and tolerance policies.
4. Prepare backups/recovery points and run compatible restore tests.
5. Provision read-only reconciliation credentials, supporting indexes, and resource budgets.
6. Define snapshot/quiesce/CDC watermark cuts and evidence capture.
7. Set up dashboards, exception stores, on-call escalation, and go/no-go gates.
8. Rehearse in staging/canary including deliberate fault/bad-data injection.

### Stage B — Pre-Migration Baseline

1. Lock source dataset and verified cut \(T_0\).
2. Compute counts/unique keys by tenant, date, `schemaVersion`, and status.
3. Profile BSON types, missing/nulls, invalid enums, and source anomalies.
4. Save source financial/ledger/inventory summary totals per business rules.
5. Record partition manifests/hashes and canonicalizer version.
6. Quarantine source anomalies under policy rather than dropping them.

### Stage C — Migration/Backfill

~~~text
Read source partition at agreed cut
    |
    +-- validate input format and identity
    |
    +-- convert via versioned mapping
    |
    +-- write target with idempotent key/version
    |
    +-- record applied checkpoint and errors
    |
    v
Reconcile count, keyset, BSON type, value, constraints, business
~~~

For online migrations, process CDC concurrently with ordering/version guards, delete handlers, and resume tokens; never mark a partition ready while a CDC gap remains.

### Stage D — Exception Review and Remediation

1. Export PII-scrubbed summaries and file severity-tiered tickets.
2. Classify each exception: **true defect, transient lag, intentional transform, invalid source, or checker defect**.
3. Fix mapping, source data, or target per runbook.
4. Apply conditional version-aware updates so fresh writes are never overwritten.
5. Re-run under the **same cut/`mappingVersion`** or start a clean new run.
6. Re-verify linked business invariants post-fix, not just the repaired field.
7. Archive resolution evidence and approvers.

### Stage E — Final Gate

Example decision table:

| Criterion | Required at Go/No-Go |
|---|---|
| Historical partitions | 100% of in-scope partitions completed and verified. |
| Source/target comparison cut | Same approved logical cut/watermark. |
| Missing critical keys | 0 unresolved. |
| Extra/duplicate keys | 0 unexplained. |
| BSON required type mismatches | 0 unresolved. |
| Unique/validator violations | 0 unresolved relevant violations. |
| Referential/tenant violations | 0 cross-tenant; orphans within approved policy. |
| Ledger/payment/inventory | Invariants within exact/tolerance policy. |
| CDC | Caught up to final cut, zero lost resume history. |
| Rollback | Feasible, tested, owners ready. |
| Business sign-off | Data owner, ops, security/finance as required. |

If any critical check FAILS or coverage is unknown, the decision is **NO-GO**. Never loosen tolerances after seeing failures just to “clear the bar” without formal approval and audit.

### Stage F — Cutover

1. Freeze/fence writers per approved architecture.
2. Verify final source → target watermark.
3. Run final critical reconciliation (or confirm immutable proofs hold).
4. Route reads and writes to target.
5. Monitor correctness, write errors, latency, authorization, and duplicate events.
6. Maintain rollback/run-forward plans accounting for **post-cutover writes**.
7. Never delete source data or backups before rollback/retention windows expire.

### Stage G — Post-Cutover

- Run periodic reconciliation on high-risk business invariants throughout the observation window.
- Watch exception trends, false positives, and new enum/type anomalies.
- Tighten validators/indexes once all active app versions are compatible.
- Close remaining low-risk exceptions and retention reviews.
- Archive final manifests, checksums, sign-offs, tickets, cuts, and tool/mapping versions.
- Conduct postmortems and add regressions to mapping tests.

### 22.1. When to Roll Back vs. Run Forward?

**Rollback** fits when the target has minimal new writes or reliable reverse sync exists. **Run-forward** fixes the target on the new schema when rolling back would lose fresh data, reverse migration is incomplete, or shapes cannot safely downgrade. Weigh:

- Time elapsed since cutover and volume of new writes.
- Compatibility of legacy apps with the new schema.
- Actual backup/recovery points.
- Feasibility of target → source replay/reconciliation.
- Business criticality and tolerable data-loss window.

Never call “swapping DNS/connection strings” a complete rollback once both sides have diverged.

## 23. Diagnosing Mismatched Metrics

| Symptom | First Suspect | Verification Action |
|---|---|---|
| Total counts match yet tenant counts skew | Missing & extra offset; wrong tenant mapping. | Keyset diff per tenant; join `legacyId`. |
| Target count > source count | CDC duplicates, extra seeds, soft-delete rules. | Unique keys, watermarks, deletes/tombstones. |
| Target count < source count | Backfill skips, invalid quarantine, CDC gap. | Partition progress, error logs, missing keysets. |
| `wrong_type_count` rises | Different drivers/serializers; missed conversion. | `$type` distribution, mapping version, writer inventory. |
| Target `$sum` unexpectedly low | String/null skipped or missing rows. | Type counts, exact value diffs, unique keys. |
| Keysets match yet business totals diverge | Wrong amount/precision/currency/status. | Canonical values, ledgers, invariant checks. |
| Hashes fail across all partitions | Schema version, encoding, timezone, key order bug. | Canonical contract version; sample field diffs. |
| Hashes match yet reports fail | Checker omitted field or missing invariant. | Independent ledger/source; mutation-test checker. |
| Cross-tenant references | Key mapping/join omitted tenant dimension. | Composite-key joins, tenant auth policies. |
| Counts fluctuate every run | Both sides writing or unfixed cut. | Snapshots/watermarks, TTL/CDC lag/clock semantics. |
| Quarantine grows steadily | Source drift, validator/app mismatch. | New source writers, `schemaVersion`, invalid samples. |
| Unique index build fails | Existing duplicates or null-key collisions. | Duplicate groups, required fields, index rules. |
| Checker runs too slowly | Collection scans, huge joins, unbounded concurrency. | Explain plans, indexes, partitioning, throttling. |
| Post-cutover drift returns | Lingering old writers, out-of-order dual-writes. | Fencing, CDC versions, app deployment inventory. |
| Report says PASS yet users report bad orders | Incomplete scope/invariants or auth mapping bug. | Trace business request; compare entity + related docs. |

### 23.1. Never Fix Drift Simply by “Re-Running the Migration”

If a migration is non-idempotent, re-running can:

- Duplicate child documents.
- Overwrite fresh target values.
- Re-credit money or points.
- Stamp current timestamps over historical dates.
- Corrupt audit trails.

Before replaying, ensure **stable keys, versioned mappings, deterministic transforms, conditional upserts, and checkpoints**. Any financial remediation requires audit and approval.

### 23.2. “Errors Exist Yet Counts Still Match”

An error can skip one malformed record while an extra bug inserts a phantom record, leaving totals equal. Reports must always show:

~~~text
source_count
target_count
unique_key_count
missing_keys
extra_keys
type_errors
value_errors
business_errors
quarantine_count
watermark_gap
~~~

No single metric proves migration success.

## 24. Common Misconceptions

| Misconception | Why It Is Wrong | Right Practice |
|---|---|---|
| “Migration script exit 0 means data is right.” | Scripts can swallow errors or apply buggy maps. | Independent reconciliation against the contract. |
| “Matching total counts is enough.” | Missing A + extra B + tenant drift still nets 0. | Keyset/partition diffs and constraint checks. |
| “`estimatedDocumentCount` is exact.” | It is a metadata estimate. | `countDocuments`/aggregation at aligned cuts. |
| “Counts taken 1 minute apart still compare cleanly.” | Concurrent writes shift snapshots. | Verified logical cuts/watermarks. |
| “`readConcern:majority` freezes one snapshot across queries.” | Each read can evaluate at different timestamps. | Snapshots, transactions, or CDC coordination. |
| “New doc count equals old count when extracting items.” | Entity cardinalities change. | Reconcile cardinality per entity type. |
| “`ObjectId` hex string equals raw `ObjectId`.” | Different BSON types. | Canonical ID mapping and type checks. |
| “String `'1000'` and `NumberLong(1000)` behave identically.” | Storage types and sort/query semantics differ. | Exact BSON `long` and value contracts. |
| “`$sum` errors on string amounts.” | Non-numeric values are silently ignored in `$group`. | Invalid type counters + exact checks. |
| “`$isNumber` proves a field is `long`.” | It accepts `int`, `double`, and `decimal`. | Check `$type:"long"`. |
| “Missing and `null` are identical.” | Query, validator, and index semantics differ. | Separate missing and null flags. |
| “`$convert onError:0` fixes counts.” | Turns bad data into valid-looking zero money. | Quarantine parse errors; never silent-default. |
| “`Double` is accurate enough for all currencies.” | Binary floating-point rounding/scale risk. | Int64 minor units or `Decimal128` per policy. |
| “Adding a validator fixes old data.” | Validators do not mutate historical documents. | Scan and remediate old records explicitly. |
| “Unique indexes enforce required fields.” | Null/missing and partial filter nuances. | Combine `required` + type validation + unique index. |
| “Compound unique indexes are always globally unique when sharded.” | Shard-key prefix rules and version limits apply. | Design indexes per sharding docs. |
| “`$lookup` joins across separate clusters.” | Aggregation `$lookup` cannot join independent clusters. | External reconciliation app/compare. |
| “Foreign key check passes so tenant is fine.” | Joining solely on ID misses cross-tenant collisions. | Composite tenant-aware joins. |
| “Hashing raw BSON compares v1/v2 cleanly.” | Intentional field/type shifts trigger false diffs. | Canonicalize before hashing. |
| “Matching SHA-256 proves all business logic.” | Omitted fields or shared bugs yield false PASSes. | Independent invariants and exact critical checks. |
| “Reordered arrays are always bugs.” | Some arrays carry set semantics. | Contract defines order-sensitive vs. insensitive. |
| “Reordered arrays are always fine.” | Line-item order may matter. | Check stable `lineNumber`/sequence. |
| “1-second CDC lag means fully caught up.” | Unapplied events remain in flight. | Exact watermark cut verification. |
| “Change streams keep history forever.” | Bounded by oplog retention/resume windows. | Watch lag/window; resnapshot on gaps. |
| “Dual-writing two clusters is atomic.” | Partial successes and timeouts are ambiguous. | Idempotent apply, CDC, and reconciliation. |
| “Rollback just swaps the connection string.” | Target may hold exclusive post-cutover writes. | Reverse sync, restore, or run-forward plan. |
| “All extra target records should be deleted.” | Could be valid seeds, new writes, or retention data. | Verify scope and ownership before mutating. |
| “A 1% sample proves 100% accuracy.” | Rare defects evade small random samples. | Risk-based exact checks + documented sampling. |
| “Matching counts and totals prove every ledger entry.” | +/− errors cancel out. | Per-key and per-leg balance checks. |
| “0.01 tolerance everywhere is fine.” | Money and security demand exactness. | Field/business-specific tolerance policies. |
| “Reconciliation should run as fast as possible.” | Unbounded scans can breach production SLOs. | Throttle, index, partition, and respect headroom. |
| “Fixing a field needs no linked recheck.” | Repairs can break totals or relations. | Reconcile keys plus linked invariants. |
| “Dump full documents into detailed diff logs.” | Leaks PII/credentials/secrets. | Redacted evidence, RBAC, and retention. |

## 25. Hands-On Exercises and Answers

Exercises rely on hypothetical scenarios and the lab fixtures above—never single production runs. For writes, DDL, or validators, act strictly inside an **authorized MongoDB lab/staging environment**. Evaluation focuses on **diagnosing root causes, writing accurate checks, and defining PASS/NO-GO gates**, not mutating real data.

### Exercise 1 — Matching Total Counts

**Prompt:** Source has 4 documents, target has 4. Can you conclude the migration succeeded?

**Answer:** No. The fixture has missing `ORD-2002` at source and extra `ORD-ORPHAN` at target, canceling out to 4. Reconcile keysets, tenant partitions, BSON types, values, references, and business invariants.

### Exercise 2 — Counts by Tenant

**Prompt:** Source `tenant-a=2`, `tenant-b=2`; target `tenant-a=3`, `tenant-b=1`. Total is 4 on both. What do you report?

**Answer:** `tenant-a` has +1 extra and `tenant-b` is missing 1. Reconcile by `(tenant, orderNo)` / `legacyId` for missing/extra records or cross-tenant misrouting. Never pass solely on total delta 0.

### Exercise 3 — `estimatedDocumentCount`

**Prompt:** Huge collection; `estimatedDocumentCount()` returns 10,000,000 on both source and target. Is that sufficient for an exact go/no-go gate?

**Answer:** No. It is a metadata estimate ignoring scopes/filters. Run exact counts/keysets at aligned cuts with proper scan/index capacity planning.

### Exercise 4 — Keyset Difference

**Prompt:** Source keys `{A,B,C}`, target `{A,C,D}`. Do counts match? Missing/extra?

**Answer:** Both have count 3, yet `B` is missing and `D` is extra. Reconcile bidirectionally, not source→target alone.

### Exercise 5 — Mapping Keys

**Prompt:** v1 `_id` is `ObjectId`, v2 `_id` is string `tenantId:orderNo`. Can you join directly on `_id`?

**Answer:** No. Join via the defined `legacyId`/business key or mapping table, checking 1-to-1 cardinality and types.

### Exercise 6 — Duplicate `legacyId`

**Prompt:** Two target docs share `legacyId` with different `_id`s. Target has unique `_id`, so is data valid?

**Answer:** No. Unique `_id` prevents duplicate target PKs, not one source mapping to two targets. Group on `$legacyId` or add a unique index if contracted.

### Exercise 7 — Wrong Tenant

**Prompt:** Source order in `tenant-a` maps to `tenant-b` at target with accurate amount/status. Severity?

**Answer:** **Critical** in multi-tenant systems due to data-leak risk. Enforce tenant equality and composite references, block cutover, and audit authorization/residency.

### Exercise 8 — BSON `long` vs. `string`

**Prompt:** Are `amountMinor:"50000"` and `amountMinor:NumberLong("50000")` equivalent?

**Answer:** No. Different BSON types; schema v2 mandates `long`. Check `$type` in aggregation or `$jsonSchema` `bsonType:"long"`, not stringified equality.

### Exercise 9 — Wrong Value with Valid Type

**Prompt:** Source `amount:"30000"`, target `NumberLong("3000")`. Will type checking catch this?

**Answer:** No, target is still `long`. Run contract `$convert` on source and exact comparison, plus line-item/ledger sums.

### Exercise 10 — Missing vs. Null

**Prompt:** Document A lacks `amountMinor`; B has `amountMinor:null`. Can `{amountMinor:null}` return both?

**Answer:** Yes. Equality to `null` matches both missing and explicit `null`. Use `$exists:false` vs. `$type:"null"`, and enforce `required` + `bsonType` for mandatory fields.

### Exercise 11 — `$isNumber`

**Prompt:** `$isNumber:"$amountMinor"` returns true. Does that prove BSON `long`?

**Answer:** No; `int32`, `double`, and `Decimal128` are also numeric. Enforce `$type:"long"` plus value/range checks.

### Exercise 12 — Invalid Parse

**Prompt:** Source `amount:"12,50"`; migration used `$convert onError:0`, producing target `amount=0`. Count as converted?

**Answer:** No. `0` is a valid business amount that masks errors. Quarantine/log `INVALID_SOURCE`, review locale/scale rules, and replay cleanly before rechecking.

### Exercise 13 — Overflow

**Prompt:** Source string exceeds `Long.MAX_VALUE` while target expects int64. What should happen?

**Answer:** Flag conversion overflow; never truncate or wrap. Business decides between `Decimal128` or a new schema type, then replays under the new `mappingVersion`.

### Exercise 14 — Currency

**Prompt:** Source 10.00 USD maps to integer 10, and source 10 JPY maps to integer 10. Raw numbers match. Valid?

**Answer:** No if target stores minor units: 10.00 USD must be 1,000 cents while 10 JPY is 10 yen per currency exponent. Reconcile per currency with proper scales.

### Exercise 15 — `Double` vs. `Decimal128`

**Prompt:** Migration converts `NumberDecimal("0.10")` to Java `double` and stores MongoDB `Double`. Does it preserve precision and type?

**Answer:** No. Binary floating point introduces representation error and uses the wrong BSON type. Use `BigDecimal`/`Decimal128` or int64 minor units per contract; avoid `doubleValue()`.

### Exercise 16 — UTC Dates

**Prompt:** Source `2026-10-01T08:00:00Z`, target `2026-10-01T15:00:00Z` because the app runs in GMT+7. Same instant?

**Answer:** No; target shifted by 7 hours. `15:00+07:00` equals `08:00Z` when formatted locally, yet the stored BSON `Date` must remain `08:00Z`. Compare epoch milliseconds/UTC.

### Exercise 17 — Status Mapping

**Prompt:** Source has status `"returned"` absent from the mapping table, and the script defaults it to `"OPEN"`. Safe?

**Answer:** No. Flag unknown values as `INVALID_ENUM`/`UNMAPPED`, update the contract with approval or quarantine—never silent-default into another business state.

### Exercise 18 — Validator `required`

**Prompt:** `properties.amountMinor.bsonType:"long"` without `required:["amountMinor"]`. Can a document missing `amountMinor` pass?

**Answer:** Yes. `properties` validates a field only when present; `required` enforces presence. Combine both for mandatory fields.

### Exercise 19 — Validator Rollout

**Prompt:** Switching `validationAction:"error"` on a collection with invalid history. Does MongoDB auto-repair old docs?

**Answer:** No. Validators check writes per `validationLevel`/`validationAction`; scan and remediate historical invalids and stage `warn→error` with telemetry.

### Exercise 20 — Unique Index

**Prompt:** `orders_v2` has unique `{tenantId:1,orderNo:1}`. Can two different tenants share the same `orderNo`?

**Answer:** Yes, because `tenantId` differs in the compound key. Duplicates within the same `(tenantId, orderNo)` are blocked; also audit missing/null and collation rules.

### Exercise 21 — Partial Unique

**Prompt:** Unique index on `{tenantId:1,orderNo:1}` uses `partialFilterExpression:{isActive:true}`. Is a document lacking `isActive` protected?

**Answer:** No, because it falls outside the partial filter. Pair with `isActive` required/type validation and verify scope/uniqueness.

### Exercise 22 — Sharded Unique Constraints

**Prompt:** On a sharded collection, a developer creates a unique index ignoring the shard key and assumes global uniqueness. Safe?

**Answer:** No. Sharded unique indexes require shard-key prefixes and version compatibility. Verify docs, topology, and tests before cutover.

### Exercise 23 — Dangling Reference

**Prompt:** `orders_v2.customerId="C-999"` has no matching customer, while count/status/amount are valid. Is it an error?

**Answer:** Potentially `REFERENCE_ORPHAN`; check domain rules on deleted/anonymized customers. If active orders require valid customers, treat as a defect and catch with tenant-aware `$lookup`.

### Exercise 24 — Cross-Tenant Join

**Prompt:** `customerId "C-010"` exists in `tenant-b`, and an order in `tenant-a` uses the same ID. Can joining solely on `customerId` pass falsely?

**Answer:** Yes—a **false PASS** when IDs are not globally unique. Join on both `customerId` and `tenantId`; authorization and data residency are critical invariants.

### Exercise 25 — Embedded → Referenced

**Prompt:** Source has 1 order embedding 3 items; target has 1 order and 3 item documents. Should source doc count=1 match target doc count=4?

**Answer:** No. Compare **entity cardinality**: 1→1 orders, 3→3 items, plus line IDs/quantities/prices/totals per mapping spec.

### Exercise 26 — Revenue Totals Only on `PAID`?

**Prompt:** Source has 3 `PAID` and 5 `CANCELLED` orders; target retains `amount` on cancelled docs. Should a revenue check sum all orders?

**Answer:** No if revenue means recognized `PAID`/settled orders. Define status, captured/refunded payments, currency, date, and cut explicitly. Equal gross sums do not prove equal revenue.

### Exercise 27 — Ledger Totals

**Prompt:** Ledger transfer `T2` has entries −10,000 and +9,000. Transfer net invariant is 0. Outcome?

**Answer:** Net = −1,000; `BUSINESS_INVARIANT` critical/high per domain. Never patch with an arbitrary balancing entry; trace the authoritative source, check currency/fees, and audit remediation.

### Exercise 28 — Offsetting Errors

**Prompt:** Two ledger bugs of +1,000 and −1,000 net to 0. Does that prove zero lost money?

**Answer:** No. Verify per-entry/per-transfer keysets/values, account assignments, and double-entry rules. Sums are only necessary, not sufficient.

### Exercise 29 — Canonical Comparison

**Prompt:** Source status `"new"`, target `"OPEN"`. Raw JSON differs, yet the contract maps `new→OPEN`. Report an error?

**Answer:** No, when conforming to contract. Canonicalize source status to `OPEN`, then check identity, amount, dates, and invariants. Never demand raw BSON equality across intentional schema changes.

### Exercise 30 — Hashing Raw BSON

**Prompt:** SHA-256 of raw v1/v2 BSON differs because field names changed. Does that prove the migration broke?

**Answer:** No. Canonicalize semantic data into deterministic versioned bytes before hashing by stable key. On mismatch, drill down to field diffs rather than trusting hashes alone.

### Exercise 31 — Matching Hashes Yet Broken Checker

**Prompt:** Both canonicalizers forgot the `currency` field; hashes match even though VND turned into USD. Can this pass?

**Answer:** No. The mapping contract missed a critical field. Rely on independent business invariants, sample oracles, and mutation/field-coverage tests; version and re-run canonicalization.

### Exercise 32 — Arrays

**Prompt:** Tags shifted from `["x","y"]` to `["y","x"]`. Is it wrong?

**Answer:** Depends on contract: if `tags` is a set, sorting makes them equivalent; if order-sensitive sequence, it is a mismatch. Never default to sorting arrays across all collections.

### Exercise 33 — Counts Taken at Different Instants

**Prompt:** Source count at 10:00 is 100,000; target count at 10:01 is 100,500 after 500 inserts. Is this definitely a bug?

**Answer:** No—different snapshots. Use quiesce/snapshot cuts or CDC watermarks and compare equal scope at a verified cut.

### Exercise 34 — CDC Gap

**Prompt:** Target applied `E12700` while source watermark is `E13000`, yet counts happen to match. Final PASS?

**Answer:** No. 300 events remain unapplied; catch up and verify zero gaps, then check counts/keys/types/business at the same cut. If oplog history expired, resnapshot per runbook.

### Exercise 35 — Dual-Write Partial Success

**Prompt:** Source write succeeds, target times out, app retries the same request. Can it generate a new random target ID each time?

**Answer:** Unsafe—target might have committed on timeout. Use deterministic target IDs/idempotency, versioned upserts, and outcome checks; never assume cross-cluster atomicity.

### Exercise 36 — Deletes During Backfill

**Prompt:** A copies to target, source deletes A, CDC ignores delete events. What does reconciliation find?

**Answer:** Target holds **extra record A**. Handle tombstones/deletes per retention policy, checkpoint in order, and re-verify.

### Exercise 37 — Lost Resumability

**Prompt:** Backfill takes 72 hours while change stream history retains 24 hours. Can you keep going and just compare counts?

**Answer:** No if CDC gapped and cannot resume; updates/deletes may be lost. Recover via supported snapshot/CDC protocols or resnapshot/rebuild under a fresh run—never PASS on coincidental counts.

### Exercise 38 — Sampling

**Prompt:** Checked 1% random records and found zero errors. Can you accept all remaining unchecked payment data?

**Answer:** No when policy demands exactness. Sampling proves only the sample; run full key/type/ledger exact checks on critical data and stratified samples on business-approved low-risk data.

### Exercise 39 — Rollback After Target Received Writes

**Prompt:** 5 hours post-cutover, target holds 20,000 new orders not reverse-synced to source. Can you roll back simply by pointing URIs back to source?

**Answer:** No. Source lacks 20,000 orders, causing data loss and identity conflicts. Execute reverse sync/reconciliation, restore/run-forward, and get business sign-off per rollback plan.

### Exercise 40 — Designing a Full Reconciliation Run

**Prompt:** 200M-document MongoDB `orders` collection on a replica set; v1 has string amounts, v2 has int64 minor units and a new status enum; continuous writes; sensitive multi-tenant access controls. Design an auditable reconciliation plan to reach go/no-go.

**Suggested Answer:**

1. Define authoritative source, `mappingVersion`, immutable business keys, and tenant/retention/soft-delete scopes.
2. Specify expected cardinalities, required BSON types, status maps, tenant isolation, and precision/currency/date rules.
3. Establish online snapshot + CDC protocol at T0 with durable resume tokens/checkpoints and idempotent upsert/delete apply; prevent gaps.
4. Capture source baselines: counts, unique keys, type distributions, and ledger totals by tenant, date, currency, and status.
5. Partition source/target by immutable indexed keys; run streaming merge joins or batched lookups with bounded workers (never `toArray()`).
6. Detect missing/extra/duplicate keys, cross-tenant mappings, missing required fields, wrong BSON types, and value diffs.
7. Canonicalize source/target under the same contract; partition-hash for triage and exact-diff critical fields.
8. Verify independent invariants: line-item totals, paid/refund totals, balanced ledgers, customer references, and PII/retention rules.
9. Persist exception reports with severity, mapping version, verified cut, redacted key/hash, remediation owner, and proof.
10. Quarantine invalid sources; repair via version-aware updates and idempotent replay—never silent defaults.
11. Monitor MongoDB CPU/IOPS/cache/replication lag and checker progress; throttle or pause if production SLOs degrade.
12. Perform final catch-up at T1, briefly freeze/fence writes if architecture demands, and re-run critical checks at the exact cut.
13. Go/no-go: zero critical missing keys, type/tenant/ledger defects, zero CDC gaps, full required coverage, feasible rollback.
14. Canary cutover, watch query results/dashboards/errors, and keep source/backups throughout the retention window.
15. Archive final manifests, checksums, and owner approvals; never mix mapping versions or snapshots in one report.

A plan is valid only when **counts, data types, constraints, and business outcomes** are all verified at the same logical cut. “200M rows processed” or “0 script failures” never substitutes for that evidence.

## 26. Quick Decision Table: Choosing the Right Check for Each Goal

| Goal | First Check | Follow-Up Check | What to Avoid |
|---|---|---|---|
| Zero lost orders | Counts by tenant/date. | Source→target missing and target→source extra keys. | Trusting total counts alone. |
| Zero duplicate entities | Group business/legacy key cardinality. | Unique indexes per scope/collation/shard key. | Relying solely on target `_id`. |
| Valid data types | `$type` distribution + required/missing/null. | `$jsonSchema` validator/collection scan. | Checking Java DTO types alone. |
| Accurate amount conversion | Contract `$convert` on source. | Exact compare on target `long`/`Decimal128` + sum invariants. | Defaulting errors to 0; using `Double` for money. |
| Accurate states | Enum/version mapping. | Status counts + transition/payment/fulfillment invariants. | Raw string comparison across intentional renames. |
| Valid relations | `$lookup`/app join on stable keys. | Tenant-aware reference checks, 1-to-N cardinality. | Joining on ID without tenant. |
| Accurate money/ledgers | Counts + sums by currency/tenant/time. | Per-entry/per-transfer exact balance. | Offsetting errors hiding in sums. |
| Zero online drift | CDC watermarks/resume checkpoints. | Final exact compare at verified cut. | Comparing arbitrary timestamps. |
| Massive datasets | Partition counts/hashes. | Streaming sorted per-key merge/diff. | `toArray()` on entire collections. |
| Post-cutover safety | Shadow reads + critical invariants. | Monitor new writes, reverse sync/rollback feasibility. | Deleting source too early. |

### 26.1. Acceptance Report Template

~~~text
Reconciliation run:      orders-v2-20261114-001
Migration contract:      orders-v1-to-v2.3
Source/target cut:       VERIFIED logical watermark T1
Scope:                   ALL approved in-scope tenant partitions
Source count:            <measured>
Target count:            <measured>
Distinct business keys:  <measured>
Missing target:          0
Extra target:            0 (or approved exceptions)
Duplicate business key:  0
Required BSON type:      PASS
Validator/index checks:  PASS
Cross-tenant mapping:    0
Business invariants:     PASS
CDC gap:                 NONE
Critical unresolved:     0
Rollback strategy:       VERIFIED
Decision:                GO (requires owner sign-off)
~~~

**Replace placeholders with real evidence**; never submit a template as automatic proof. Unmeasured items must read `UNKNOWN/INCOMPLETE`, never default to `PASS`.

### 26.2. A Four-Layer Check per Entity

~~~text
Entity identity:
  exactly one source key maps to exactly one target key

Shape:
  BSON field type/required/optional/nested arrays as contract

Constraint:
  unique + tenant-aware relationships + allowed state/range

Outcome:
  amount/ledger/inventory/status behavior as business oracle
~~~

Only when all four layers pass at the **exact same cut** is migration acceptance justified.

## 27. Official MongoDB and Spring Data Documentation

Links below verify syntax, semantics, and version rules. `/manual/` paths may point to the latest MongoDB Server branch; for older deployments, match your exact **Server version, FCV, Database Tools, and Java Driver**. Never copy `collMod`/index commands from examples into production without evaluating existing data, cluster sharding, and rollout policies.

### 27.1. Counting, Grouping, and Type Checking

1. [`countDocuments()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/) — exact matching document counts, costs, and limits.
2. [`estimatedDocumentCount()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.estimatedDocumentCount/) — metadata estimate, not a substitute for exact counts.
3. [`$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — grouping by tenant/status/currency and accumulators.
4. [`$sum`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/) — numeric vs. non-numeric handling in accumulators.
5. [`$type` aggregation expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/) — BSON types, missing, and null in aggregation.
6. [`$type` query operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/) — query semantics and array caveats.
7. [`$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/) — BSON type conversions, `onError`, `onNull`, and limits.
8. [`$toLong`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toLong/) — conversions and error cases.
9. [`$dateToString`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateToString/) — timezone and date bucketing.
10. [`$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — intra-database joins, index requirements, and performance.

### 27.2. Validation, Uniqueness, and Schema Evolution

11. [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — document validation, `$jsonSchema`, and rollouts.
12. [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `bsonType`, `required`, and validator examples.
13. [`collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/) — updating collection validators and validation actions.
14. [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness, missing/null, and sharded considerations.
15. [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — `partialFilterExpression` and subset uniqueness.
16. [Index Strategies](https://www.mongodb.com/docs/manual/applications/indexes/) — query/index planning for scans and reconciliation.
17. [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — int32, int64, double, Decimal128, ObjectId, Date, and comparisons.
18. [Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — type-safe representation for exports/reports.

### 27.3. Snapshots, Change Streams, and Transactions

19. [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — local/majority/snapshot semantics.
20. [Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot read behavior and prerequisites.
21. [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — events, resume tokens, and oplog retention.
22. [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history windows/retention and online migration implications.
23. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity, snapshots, concurrency, and limits.
24. [Sharded Clusters](https://www.mongodb.com/docs/manual/sharding/) — shard keys, routing, and cluster-wide constraints.

### 27.4. Java / Spring Data and Performance

25. [Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/) — typed BSON, cursors, aggregation, connection pooling, and error handling.
26. [Java Driver BSON/Document API](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/) — `Document`, BSON types, and serialization.
27. [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — mapping, `MongoTemplate`, repositories, `@Version`, and transactions.
28. [Spring Data MongoDB — Template Query Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Query`/`Criteria`/`BasicQuery`.
29. [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — query plans, indexed scans, and reconciliation costs.
30. [MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/) — export/backup/`mongodump` docs; never assume a dump is a consistent online snapshot without proper procedures.

### 27.5. Mandatory Questions Before Running Any Command

1. Do source and target share one database or span **two clusters**? Will `$lookup` even work?
2. Is a snapshot/cut verified, or are you comparing live mutating data at two instants?
3. Does your MongoDB version/FCV support these operators, validators, and index semantics?
4. Are numeric values `long`/`Decimal128` or `string`/`double`, and is any precision lost?
5. Do tenant, currency, date/timezone, and soft-delete scopes match on both sides?
6. Can the aggregation use indexes? Will it overload the primary or risk losing the CDC window?
7. Where do diffs get written, who can read them, and could PII leak?
8. If errors surface, do you have version-aware remediation, rechecks, and rollbacks?

## 28. Conclusion

Reconciliation in **MongoDB data evolution** is the process of proving **the exact same set of business entities** preserves **accurate values and constraints** across physical representation changes, without breaking access controls or transactional logic.

A convincing verification suite answers all four questions:

1. **Counts:** Are all business keys present per tenant/partition with zero unexpected duplicates or extras?
2. **Data types:** Do required fields, BSON types, missing/null states, numeric precision, dates, and arrays conform to contract?
3. **Constraints:** Are unique keys, JSON Schema rules, reference integrity, statuses, and tenant isolation protected?
4. **Business outcomes:** Are order totals, ledger balances, inventory, payments, lifecycles, and privacy/retention intact?

While systems continue accepting writes, base every check on **coordinated logical snapshots or watermarks**—never compare numbers sampled at arbitrary times. At scale, combine **partition counts, canonical fingerprints, streaming exact diffs, and bounded workloads**; for critical errors, **quarantine, investigate, repair under audit, and re-verify**, rather than defaulting to zero or waiving them globally.

**A migration should be accepted only upon unified reconciliation evidence across counts, BSON types, constraints, and business invariants at a single cut, paired with full explanations for every exception and a verified recovery path if cutover fails.**
