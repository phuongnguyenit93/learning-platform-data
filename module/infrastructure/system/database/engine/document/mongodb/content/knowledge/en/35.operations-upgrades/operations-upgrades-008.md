# Managing Index, Validator, and Configuration Changes on Live Data in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Operations and Upgrades  
> **Lesson:** Managing Index, Validator, and Configuration Changes on Live Data

## 1. Opening Scenario: Small Change, Big Impact

An ordering system runs a MongoDB replica set holding tens of millions of documents. The development team wants to apply three changes:

1. Create a compound index `{tenantId: 1, status: 1, createdAt: -1}` to speed up the order listing page.
2. Add a validator requiring `status` in `CREATED`, `PAID`, `CANCELLED` and non-negative `amountCents`.
3. Update a monitoring setting and a few server parameters to reduce performance alerts.

On a test collection with a few hundred documents, every change finishes in seconds. On live data, reality differs:

- An index build consumes CPU, RAM, and I/O, needs extra disk space, and must synchronize across the replica set.
- Legacy data may have wrong types, missing fields, duplicate values, or violate the new validator.
- A new validator can break write requests from older application instances not yet upgraded.
- A newly created index might be ignored by the query planner; conversely, dropping an index that looked unused can cause p99 latency to spike sharply.
- Changing a TTL can trigger bulk deletions of documents sooner than expected.
- Configuration parameters vary across **runtime**, **startup**, **collection**, or **cluster** scopes, and not all apply or roll back identically.
- If a change overlaps a failover, batch import, or server upgrade, isolating the root cause becomes far harder.

So the right question is not merely **"Which MongoDB command runs?"**, but:

> **How do we ship changes to production while protecting data, preserving SLAs, controlling compatibility, measuring before-and-after impact, and knowing how to recover?**

This lesson presents a complete **change management** workflow for **indexes, schema validators, and MongoDB configuration** on live user-facing data.

### 1.1. Learning Objectives

After this lesson, you will be able to:

- Classify changes by risk, reversibility, and cross-node impact.
- Capture baselines for query plans, indexes, schema violations, version/FCV, and active configuration.
- Plan index builds on populated collections while tracking commit quorum and resources.
- Use **hidden indexes** to test index removal impact before physically dropping them.
- Convert an index to **unique** using controlled duplicate checks.
- Modify TTL and partial/compound indexes without accidental data deletion or regressions.
- Roll out validators with `$jsonSchema`, `collMod`, `validationLevel`, and `validationAction` in stages.
- Distinguish runtime-changeable config from changes requiring rolling restarts, FCV/upgrades, or managed-service controls.
- Design **expand–migrate–contract**, idempotent migrations, canary rollouts, rollbacks, and incident runbooks.
- Practice inside an isolated MongoDB namespace, modifying and deleting only records created by the lab itself.

## 2. Changing Schemas in MongoDB Differs from Editing a YAML File

MongoDB is a document database. Documents inside the same collection can vary in structure:

```javascript
// Legacy document
{
  _id: ObjectId("66a000000000000000000381"),
  tenantId: "T-1",
  status: "paid",
  amount: "350000"
}

// New document
{
  _id: ObjectId("66a000000000000000000382"),
  tenantId: "T-1",
  status: "PAID",
  amountCents: NumberLong("35000000"),
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

If a validator requires `amountCents` of type `long` and uppercase `status: "PAID"`, the legacy document does not comply.

**Schema flexibility** speeds up early development, yet demands discipline when evolving contracts between the database and applications.

### 2.1. Three Fundamentally Different Types of Changes

| Type | Examples | Typical Impact |
| --- | --- | --- |
| Index | Creating compound/unique/TTL/partial indexes; hide/drop | Query planner, CPU, disk, write amplification, constraints |
| Validator | `collMod` changing `$jsonSchema`, validation level/action | Insert/update acceptance, type/data correctness |
| Configuration | `setParameter`, startup YAML, driver options, FCV | Monitoring, networking/auth, memory/threads, feature behavior, operability |

A single change often spans multiple categories. For example, converting `status` from free-form strings to an enum:

1. Requires the application to write the new status values.
2. Requires migrating legacy status values.
3. Requires a validator to block invalid statuses.
4. May require a new index to optimize status filters.
5. Requires keeping the old index while legacy app versions still run.

### 2.2. Risk Classification

| Change | Easy to Roll Back? | Biggest Risk |
| --- | --- | --- |
| Add non-unique index | Can be dropped, though rebuilding is costly | Disk/CPU/IOPS during build plus write overhead |
| Add hidden index | Can be dropped or unhidden | Still incurs build/write cost and unique/TTL semantics if enabled |
| Hide index | Usually quick to unhide | Queries may switch plans and slow down |
| Drop index | Reverting requires **rebuilding** | Lost performance or constraints during rebuild |
| Enable unique | Dropping unique may require rebuild, not a trivial toggle | Existing/new write duplicates, broken invariants |
| Shorten TTL | Can revert setting, yet deleted documents never auto-recover | Premature legitimate TTL data loss |
| Validator `warn` | Easy to revert | Log growth; does not actually block bad data |
| Validator `error` | Easy to revert | Insert/update requests start failing |
| Startup auth/TLS/port | Rolling rollback possible, yet high risk | Connection loss, health check / election failures |
| FCV/major upgrade | Constrained by upgrade/downgrade paths | Feature, data, or driver incompatibility |

Never rate risk solely on "the command runs in milliseconds". Assess **data and system impact after the command completes**.

## 3. Change Contract: Objective, Scope, and Accountability

Every production change should have a concise, specific change record:

```yaml
changeId: mongo-orders-2026-11-14-01
owner: team-orders
environment: production
cluster: orders-rs
database: commerce
collection: orders
changeType: index
objective: reduce p95 latency of listOrders query
proposal: add hidden compound index then unhide
preconditions:
  - clusterHealthy
  - enoughDiskHeadroom
  - noConcurrentMigration
  - currentIndexesSaved
successMetrics:
  - readP95BelowSLO
  - noNewWriteErrors
  - replicationLagWithinBaseline
rollbackTrigger:
  - readP99Regresses
  - writeLatencyOrDiskSaturation
rollbackMethod: hideNewIndexAndRestorePreviousRouting
approvals:
  - applicationOwner
  - databaseOperator
```

This is an **application change record template**, not YAML parsed by MongoDB.

### 3.1. Mandatory Pre-Start Questions

- Which **database/collection/shards** does the change touch?
- How many documents, indexes, tenants, and users are affected?
- What are the current MongoDB version, FCV, drivers, and topology?
- Is any primary or secondary lagging, unhealthy, or short on disk?
- What was measured in staging on a representative dataset?
- Which write paths change? Are older app/worker versions still running?
- Has a backup/restore strategy been verified?
- Are a maintenance window or traffic guardrails needed?
- What defines success, and when must we abort?
- If instant rollback is impossible, what is the **forward-fix** plan?

### 3.2. Do Not Change Three Major Things at Once

If you create an index, enable a strict validator, and tweak cluster settings simultaneously, pinpointing the cause of a latency spike becomes very difficult. Normally follow this sequence:

```text
Baseline + backups
        |
        v
Deploy backward-compatible application code
        |
        v
Create/validate new index (as needed)
        |
        v
Observe / clean old data
        |
        v
Tighten validator with monitoring
        |
        v
Remove obsolete indexes/settings later
```

Steps can be grouped within a release, yet each step needs its own **checkpoint and proceed/rollback decision**.

## 4. Collecting Inventory and Baseline Before Changes

### 4.1. Exact Cluster, Version, and Namespace

In `mongosh`, with authorized privileges only:

```javascript
printjson({
  dbName: db.getName(),
  serverVersion: db.version(),
  hello: db.adminCommand({ hello: 1 })
});
```

Inspect feature compatibility version if authorized:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

`hello` output varies by topology and version. Connecting via `mongos` differs from connecting directly to `mongod`; for sharded collections, account for shard keys and data distribution.

**Never run production DDL using a URI copied from a test environment.** Record the endpoint, database, collection, and cluster ID in the change record, and enforce two-person verification for destructive changes.

### 4.2. Save Current Index Definitions

```javascript
const c = db.getCollection("orders");

printjson(c.getIndexes());
```

Details to archive:

- Index names, key order, `unique`, `sparse`, and partial filters.
- Collations, TTLs, and hidden flags.
- Specialized indexes (text, geospatial, hashed, wildcard, etc.).
- Indexes supporting shard keys.
- Index sizes and usage frequency.

On populated collections, `getIndexes()` alone **does not reveal whether an index is actually beneficial**. Inspect query patterns and usage stats.

### 4.3. Save Current Collection Options and Validators

```javascript
const infos = db.getCollectionInfos({
  name: "orders"
});

printjson(infos.map((x) => ({
  name: x.name,
  options: x.options
})));
```

Specifically archive verbatim:

- `validator`.
- `validationLevel`.
- `validationAction`.
- Default collation.
- Time-series, capped, encryption, or other special properties.

To roll back a validator accurately, you need the **exact previous expression and options**, not just a vague note like "it used to be looser".

### 4.4. Baseline Query Plans and Performance

```javascript
db.orders.find({
  tenantId: "T-1",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(20)
  .explain("executionStats");
```

Track:

- `totalDocsExamined` and `totalKeysExamined`.
- `nReturned`.
- Plan stages such as `IXSCAN`/`COLLSCAN` and any blocking sort.
- p50/p95/p99 latency **from live traffic**, not solely a single `explain`.
- Write latency/error rates plus CPU and disk load.

`explain("executionStats")` can perform substantial read work; avoid running unbounded cluster-wide scans during peak hours just for a report.

### 4.5. Resource Baseline

Key areas to capture:

| Group | Before Change |
| --- | --- |
| CPU/RAM | Process CPU, resident memory, WiredTiger cache/dirty/eviction |
| Disk | IOPS, throughput, read/write await, queue depth, free space |
| Replication | Secondary lag, health, majority commit / read concern |
| DB concurrency | Active/waiting operations, locks/tickets, pool wait |
| Application | QPS, timeouts, read/write p95/p99, error rates |
| DDL | Active index builds / index count, recent migrations |
| Business | Count of schema violators, duplicate keys, TTL eligibility |

## 5. Index Changes: Choose the Right Design Before Building

### 5.1. Compound Indexes Must Match Query Patterns

Suppose an API runs:

```javascript
db.orders.find({
  tenantId: "T-1",
  status: "PAID"
}).sort({ createdAt: -1 })
  .limit(20);
```

A candidate index:

```javascript
{
  tenantId: 1,
  status: 1,
  createdAt: -1
}
```

This combines two equality filters and one sort field. Still, the optimal index depends on:

- Actual cardinality and selectivity.
- Whether queries filter across many statuses or primarily one.
- Range predicates, pagination, and collations.
- Other queries able to reuse a prefix of the compound index.
- Write overhead, index size, and RAM/cache capacity.
- Plan cache and application hints.

Do not create a dedicated index for every query variation if cumulative write overhead and index footprint grow too large.

### 5.2. Field Ordering Guidelines

For queries combining equality, sort, and range predicates, the **Equality – Sort – Range (ESR)** heuristic is a solid starting point—yet it is a heuristic, not an absolute law. A highly selective range predicate can alter ideal ordering. Validate with `explain` and benchmarks.

For example:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

efficiently serves tenant/status filters with descending sort, whereas:

```javascript
{ createdAt: -1, tenantId: 1, status: 1 }
```

is not equivalent for that query pattern.

### 5.3. Partial Indexes Save Space Under Strict Conditions

If queries care only about active orders:

```javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  {
    name: "active_orders_by_tenant",
    partialFilterExpression: {
      status: "ACTIVE"
    }
  }
);
```

This index covers only a subset of documents. The query planner selects a partial index only when the query predicate proves results fall strictly within the index filter. A query omitting `status: "ACTIVE"` cannot use this index to return all documents.

Never replace a full index with a partial index while queries still need inactive or cancelled records.

### 5.4. Unique Indexes Carry Historical Data Risks

Before adding:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

with `unique: true`, check:

- Whether duplicates already exist.
- Documents missing `externalOrderId` or holding `null`.
- Collation, case, and Unicode semantics.
- Whether older write paths can still generate duplicates.
- Unique index and shard key rules for sharded collections.
- Whether business uniqueness changed from global to per-tenant.

Never run `createIndex(..., {unique: true})` blindly in production and wait for errors to "discover dirty data".

## 6. Index Builds on Large Populated Collections

### 6.1. Online Index Builds Are Not Cost-Free

Modern MongoDB builds indexes on populated collections while allowing concurrent reads and writes for most of the build. However:

- Exclusive collection locks occur at the **start and end** of the build.
- Scanning and sorting consume CPU, RAM, and temporary disk.
- Concurrent writes during the build add overhead.
- Replicated and sharded deployments require participation from data-bearing members.
- Index builds can abort or stall waiting for quorum if a node fails.

Thus "online build" **does not mean zero latency impact**. Size capacity headroom and monitor closely.

### 6.2. Commit Quorum on Replica Sets

In replicated index builds, the primary waits for a configured set of data-bearing voting members to finish building per **commit quorum** before marking the index ready.

Key concepts:

- `commitQuorum`: members required to finish building per policy.
- Default is typically `votingMembers` per documentation.
- An unavailable voting member can cause the index build to **wait**.
- Progress must be tracked across **every member**.
- Lowering commit quorum is a risky operational trade-off, not a routine button to "force completion".

Reference syntax **for illustration only**:

```javascript
db.runCommand({
  createIndexes: "orders",
  indexes: [
    {
      key: { tenantId: 1, status: 1, createdAt: -1 },
      name: "orders_tenant_status_created_v2"
    }
  ],
  commitQuorum: "votingMembers"
});
```

Never run this sample in production without checking existing indexes, storage headroom, replica set health, and schema permissions.

### 6.3. Default to Replicated Index Builds

Never attempt a manual "rolling index build" by detaching replica set members one by one as standalones without an officially supported MongoDB runbook. Rolling index builds are a **specialized** procedure that lowers fault tolerance, prolongs the change, and forces elections.

Never mix replicated index builds with rolling index builds when docs warn against conflicts. In Atlas or managed services, use the platform's index management workflows.

### 6.4. Monitoring Progress

With appropriate privileges:

```javascript
db.adminCommand({
  currentOp: 1,
  $all: true
});
```

Or use `$currentOp` on `admin` where supported by version and role. Look for active index build operations, elapsed time, progress, namespace, and lock/wait state.

**Never** kill an index build solely because it is taking a long time; evaluate abort/recovery impact, disk usage, commit quorum, and workload before acting.

### 6.5. Index Build Resource Constraints

Verify:

- Free disk and temporary space on every member.
- `maxIndexBuildMemoryUsageMegabytes` or version-equivalent tuning.
- `indexBuildMinAvailableDiskSpaceMB` (available starting in MongoDB 7.1) where applicable.
- CPU, IOPS, throughput, and cloud burst credits.
- Other concurrent DDL operations.
- Oplog/replication lag under heavy writes.

Never tweak internal knobs from an old blog post without checking your exact release/version.

## 7. Hidden Indexes: Essential Tool for Rollout and Rollback

### 7.1. What Is a Hidden Index?

A **hidden index** still exists, updates on writes, consumes disk/RAM, and enforces semantics such as **unique** or **TTL**. The single critical difference is that **the query planner cannot select it** for normal queries.

It is ideal for:

- Pre-building a new index without exposing it to the query planner yet.
- Testing the impact of removing an existing index before dropping it.
- Rolling back quickly via **unhide** if latency degrades after hiding an index.
- Timing index activation cleanly with a feature flag or change window.

### 7.2. Creating an Index as Hidden

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  {
    name: "orders_tenant_status_created_v2",
    hidden: true
  }
);
```

Once built, the index consumes resources even though the planner ignores it.

### 7.3. Unhiding to Expose to the Optimizer

```javascript
db.orders.unhideIndex(
  "orders_tenant_status_created_v2"
);
```

Verify:

```javascript
printjson(db.orders.getIndexes());

printjson(
  db.orders.find({
    tenantId: "T-1",
    status: "PAID"
  }).sort({ createdAt: -1 }).limit(20)
    .explain("executionStats")
);
```

Unhiding makes the index **eligible**, without guaranteeing the planner picks it for every query. Observe actual plans and latency.

### 7.4. Hiding to Test Removing an Index

```javascript
db.orders.hideIndex(
  "orders_status_legacy"
);
```

Monitor all query shapes and traffic cycles. If p99 spikes:

```javascript
db.orders.unhideIndex(
  "orders_status_legacy"
);
```

This instant rollback works only while the index stays intact. **Dropping** the index forces a full **rebuild** to bring it back.

### 7.5. Limitations of Hidden Indexes

- Cannot hide the `_id` index.
- Cannot force a query to use a hidden index with `hint()`.
- Unique constraints **still apply**.
- TTL expiration **still runs**.
- Hidden indexes still add write overhead.
- Toggling hide/unhide can **reset** `$indexStats` counters.

Therefore, to canary a new index, never rely on `hint(hiddenIndex)`. Perform a **controlled unhide** while monitoring the optimizer and traffic, or test on an equivalent staging cluster.

### 7.6. Hiding Is Not a Per-Tenant Canary

Hide/unhide is a collection-level index attribute, **not a per-tenant feature flag**. Once unhidden, the planner considers the index across the entire collection's workload.

For cohort-based canaries, design application-level routing, distinct query shapes, or shadow/staging environments, while monitoring collection-wide impact once eligible.

## 8. When Should You Drop an Index?

### 8.1. Never Drop Solely Because `$indexStats.ops` Is Low

Check index usage with:

```javascript
db.orders.aggregate([
  { $indexStats: {} }
]);
```

An index showing few ops over 1 hour might serve:

- Month-end billing.
- Nightly jobs or quarterly reports.
- Post-failover recovery.
- Rare yet business-critical queries.
- Legacy APIs still in production.

`$indexStats` also has caveats: counts reflect the queried node and reset on restarts or hide/unhide events. Never compare raw `ops` across members with different uptimes and declare an index unused.

### 8.2. Safe Index Removal Workflow

1. Document queries currently using the index and their owners.
2. Confirm it is not enforcing uniqueness, TTL, or business rules.
3. Hide the index first.
4. Observe across representative business cycles.
5. If clean, schedule the drop under a change ticket.
6. Archive the exact index definition in case a rebuild is needed.
7. Monitor write latency and storage after dropping.
8. If regressions appear, restore via the standard index build workflow.

`dropIndex()` is DDL—never put it into an unreviewed automated "index cleanup" cron job.

### 8.3. Never Drop a Constraint Index Just to Reduce Write Overhead

If a unique index protects business uniqueness, hiding preserves the constraint whereas dropping removes it. **Data integrity outweighs disk savings.** For TTL indexes, dropping halts automatic expiration and alters data-retention behavior.

## 9. Unique Indexes on Existing Data: Detecting and Preventing Duplicates

### 9.1. Find Duplicates Before Enabling Unique

Example for planned uniqueness on `tenantId + externalOrderId`:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 50 }
]);
```

**Never run this unbounded pipeline on a collection of hundreds of millions of documents**: `$group`/`$push` can exhaust RAM/disk, build huge ID arrays, and overload the server. In production, use sampling, partitioning, bounded batches, or budgeted audit workflows—and check BSON null/missing fields and collations.

### 9.2. Path to Convert Non-Unique to Unique (MongoDB 6.0+)

MongoDB supports a `collMod` workflow using `prepareUnique`:

```text
Existing non-unique index
           |
           v
prepareUnique: true
  -> blocks NEW duplicates
           |
           v
Audit/fix old duplicates
           |
           v
unique: true, dryRun: true
           |
           v
unique: true
  -> verifies and converts
```

Example commands—**never run directly in production without approval**:

```javascript
// 1. Existing index (verify exact name first):
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_externalOrderId_lookup",
    prepareUnique: true
  }
});

// 2. Audit conversion readiness:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_externalOrderId_lookup",
    unique: true
  },
  dryRun: true
});

// 3. Only after cleaning duplicates and passing dryRun:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_externalOrderId_lookup",
    unique: true
  }
});
```

`prepareUnique: true` **does not scan or clean existing duplicates**; it blocks new duplicates going forward. Switching to `unique: true` scans for duplicates and errors (e.g., `CannotConvertIndexToUnique`) if any remain, requiring cleanup before retrying.

`dryRun: true` is not a transaction and does not lock business workflows; concurrent writes must still be controlled. Unique rules on **sharded collections** also require checking shard key prefixes and related constraints.

### 9.3. Duplicate Resolution Must Follow Business Rules

Never blindly "keep the first document and delete the rest" when duplicates link to payments, audit logs, or external references.

Valid strategies include:

- Merging according to business decisions and lineage.
- Scoping uniqueness per tenant.
- Tagging legacy duplicates for policy-driven resolution.
- Separating historical records from active records.
- Using a partial unique index **only when business semantics genuinely permit it**.

Once unique is enabled, applications must handle **`DuplicateKey`** errors as part of their contract rather than retrying inserts infinitely with newly generated IDs.

## 10. TTL Indexes: Changes Can Trigger Mass Deletions

### 10.1. TTL Example

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "session_expiration",
    expireAfterSeconds: 0
  }
);
```

With a `Date` in `expiresAt`, the TTL monitor deletes expired documents per index rules. TTL deletion is **not guaranteed to the exact millisecond**; it depends on monitor scheduling and server load.

### 10.2. Shortening TTL on Historical Data

Suppose an index uses `expireAfterSeconds: 2592000` (30 days) and you lower it to `86400` (1 day). Many historical documents **suddenly become eligible for immediate deletion**.

This is not merely "tuning an index"; it is **altering a retention policy and risks irreversible data loss**.

Procedure:

1. Count how many records become eligible under the new TTL.
2. Check legal holds, compliance, and audit retention.
3. Assess downstream system impact.
4. Consider batched pre-deletion before changing the TTL to avoid delete bursts.
5. Take a backup/recovery checkpoint where required.
6. Modify TTL only after formal approval.
7. Monitor TTL deletion rates, replication lag, disk, and write latency.

### 10.3. Modifying a TTL Index via `collMod`

On supporting versions:

```javascript
db.runCommand({
  collMod: "sessions",
  index: {
    name: "session_expiration",
    expireAfterSeconds: 86400
  }
});
```

**Syntax example only.** Never run before quantifying how much data will expire. Raising TTL back up after records are deleted **cannot bring back deleted documents**.

### 10.4. Hidden TTL Indexes Still Delete

A TTL index with `hidden: true` continues expiring documents. **Never hide a TTL index hoping to pause deletions.**

## 11. Validators: Write Guards, Not "Automatic Migrations"

### 11.1. When Does a Validator Run?

A MongoDB collection validator checks inserts and updates according to `validationLevel` and `validationAction`. Setting a new validator via `collMod` **does not scan, fix, or remove** existing documents immediately.

Example legacy document:

```javascript
{
  _id: 1,
  amountCents: "50000",
  status: "paid"
}
```

If the new validator requires `amountCents` as `long` and `status: "PAID"`, this document stays in the collection **right after `collMod` succeeds**. The validator protects **subsequent write paths** according to the configured level and action.

### 11.2. Using `$jsonSchema`

Example validator for `orders`:

```javascript
const orderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "status",
      "amountCents"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      },
      createdAt: {
        bsonType: "date"
      }
    }
  }
};
```

Not every JSON Schema draft feature is supported verbatim in MongoDB. MongoDB uses `bsonType`, with version-specific keyword constraints. When using `NumberInt`, `NumberLong`, or `Decimal128`, match exact **BSON types**, not just printed values.

### 11.3. `validationAction`

| Value | Behavior |
| --- | --- |
| `warn` | Permits invalid writes while logging warnings to the MongoDB log |
| `error` | Rejects violating inserts/updates when validation applies |
| `errorAndLog` | Rejects and logs violation details; documented from MongoDB 8.1+ |

`warn` is useful for **measuring violations before blocking writes**, though it does not enforce clean data. `errorAndLog` can swell log volumes and log sensitive data without careful log governance; never enable it casually just to "get more debug output".

### 11.4. `validationLevel`

| Value | Meaning |
| --- | --- |
| `off` | Disables validation for inserts and updates |
| `moderate` | Validates inserts and updates to **currently valid documents**; updates to existing invalid documents are not blocked by the validator in the same way |
| `strict` | Validates all inserts and all updates against the rules |
| `constraint` | MongoDB 9.0+; prepared enforcement level ensuring all documents in the collection comply, restricting bypass rules |

`strict` is the standard default for schema validation. Yet `strict` **does not retroactively validate existing documents when first enabled**; old documents are checked only when updated. The newer `constraint` level has dedicated preparation/upgrade rules—consult version-specific docs.

### 11.5. Behavior Matrix Across States

Suppose a new validator considers document A **valid** and document B **invalid**:

| Operation | `moderate + error` | `strict + error` |
| --- | --- | --- |
| Insert valid new document | Allowed | Allowed |
| Insert invalid new document | Rejected | Rejected |
| Update A to become invalid | Rejected | Rejected |
| Update B while keeping it invalid | Allowed since B was already invalid | Rejected |
| Update B to become valid | Allowed | Allowed |
| Leave existing B untouched | Remains in collection | Remains in collection |

With `validationAction: "warn"`, violations within scope are typically logged instead of rejected—ideal for observation phases.

### 11.6. Validation Does Not Replace Business Transactions

A validator enforces `amountCents` types and `status` enums. It cannot automatically:

- Enforce business-key uniqueness where a compound unique index is needed.
- Enforce tenant ownership permissions.
- Guarantee non-negative inventory across multi-document transactions.
- Validate third-party payment outcomes.
- Verify foreign references in another collection exist.

Use validators for **document-level contracts**. Use atomic operations, indexes, transactions (where needed), and authorization for cross-document and security invariants.

## 12. Auditing Data Before Enabling Strict Validators

### 12.1. Measuring Non-Compliant Documents

Using `orderValidator` from above:

```javascript
db.orders.find({
  $nor: [orderValidator]
}).limit(30);
```

Or:

```javascript
db.orders.countDocuments({
  $nor: [orderValidator]
});
```

This **queries using the validator predicate** without altering the collection. Across tens of millions of documents it can trigger a full scan; cap cost or run across partitions/batches/supporting indexes.

**Never run a heavy unthrottled count scan mid-peak and blame "the validator for slowing down the database".** Run audits on staging or snapshots, bound execution time, and watch CPU/disk.

### 12.2. Classify Violations Rather Than Fixing Everything Uniformly

| Violation | Example | Considerations |
| --- | --- | --- |
| Missing field | `amountCents` absent | Derive from authoritative source; never fabricate `0` |
| Wrong BSON type | String `"50000"` instead of `Long` | Parse/validate and handle out-of-range values |
| Wrong enum | `"paid"` vs. `"PAID"` | Intentional mapping preserving semantics |
| Negative value | `amountCents: -15` | Investigate business bug; never reset silently to `0` |
| Renamed legacy field | `amount` vs. `amountCents` | Versioned migration with reconciliation |
| Out-of-scope legacy record | Legacy event type | Separate collection or conditional validator rules |

"Live data" means records driving real business state with audit trails. **Never auto-delete or alter monetary fields of unknown origin** just to make a validator pass.

### 12.3. Start with Type Distribution Statistics

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$amountCents" },
      total: { $sum: 1 }
    }
  },
  { $sort: { total: -1 } }
]);
```

`$type` returns each field's BSON type or missing representation per version, showing how many documents have `long`, `int`, `string`, or missing values.

On large collections, `$group` carries cost; run it only in appropriate environments and windows.

## 13. Phased Validator Rollout

### 13.1. Phase 0 — Compatible Application Code

Before touching database rules:

- Update all write paths to emit proper BSON types.
- Update batch jobs, importers, and ETL pipelines.
- Check whether older app versions remain running.
- Standardize enums and field semantics.
- Set up logging/alerting for `DocumentValidationFailure`.
- Test code against both legacy and new documents.

Even a well-written validator triggers an outage if active services still write legacy shapes.

### 13.2. Phase 1 — Warn Only

```javascript
db.runCommand({
  collMod: "orders",
  validator: orderValidator,
  validationLevel: "moderate",
  validationAction: "warn"
});
```

This allows violating writes (within the validation level) while logging warnings. Because diagnostic log volume can spike, set log retention/PII controls and monitor violations.

Exit criteria: new violation count drops to acceptable levels, with every violation source identified.

### 13.3. Phase 2 — Block New Invalid Writes While Allowing Legacy Remediation

```javascript
db.runCommand({
  collMod: "orders",
  validator: orderValidator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Effect:

- New invalid inserts are rejected.
- Updating a valid document into an invalid one is rejected.
- Existing invalid documents can still be fixed per `moderate` semantics.

Use this stage to stop new invalid writes before backfilling historical data.

### 13.4. Phase 3 — Batched Legacy Remediation

Never run `updateMany({}, { $set: { amountCents: 0 } })` in production.

Standard approach:

1. Select a small cohort by `_id`, tenant, or time range.
2. Read source records and compute target values deterministically.
3. Validate each conversion individually.
4. Apply updates with **compare-and-set** predicates on version/old values.
5. Record progress and failures—never silently skip failing records.
6. Reconcile before/after counts and totals.
7. Advance to the next batch with throttling.

Records invalid due to genuine business inconsistencies belong in a manual remediation queue rather than being forced "valid to turn dashboards green".

### 13.5. Phase 4 — Switch to Strict

Once a reliable audit confirms zero invalid documents remain and every writer matches the schema:

```javascript
db.runCommand({
  collMod: "orders",
  validator: orderValidator,
  validationLevel: "strict",
  validationAction: "error"
});
```

All updates now undergo validation. Still, `strict` alone does not guarantee zero legacy violations remain if an audit missed records or bypasses occurred; continue monitoring.

### 13.6. MongoDB 9.0: `constraint` as a Special Level

In MongoDB 9.0+, documentation introduces `validationLevel: "constraint"` with a preparation step:

```javascript
// Illustrates ordering only; never run in prod
// without a plan and verified MongoDB >= 9.0.
db.runCommand({
  collMod: "orders",
  prepareConstraintValidationLevel: true
});

db.runCommand({
  collMod: "orders",
  validationLevel: "constraint",
  validationAction: "error"
});
```

Conditions:

- Requires an existing validator defined beforehand.
- Requires the preparation step on existing collections per docs.
- Cannot alter rules simultaneously while upgrading to `constraint`.
- `validationAction` must be `error` or `errorAndLog`.
- Restricts `bypassDocumentValidation` and rule edits while in `constraint`.
- Editing rules later may require **downgrading the level** first and re-running the upgrade sequence.

**Never apply 9.0 snippets to MongoDB 7.0/8.0.** Check FCV, drivers, and compatibility matrices before adopting new validation levels.

## 14. Which Operations Does a New Validator Affect?

### 14.1. "Unrelated" Updates Can Still Fail

Suppose a legacy document has `amountCents: "50000"`. The app tries only to update a note:

```javascript
db.orders.updateOne(
  { _id: id },
  { $set: { note: "Confirmation call made" } }
);
```

Under `strict + error`, MongoDB validates the resulting document post-update; since it remains invalid, the update fails. Thus **raising `validationLevel`** on unmigrated data can break seemingly unrelated updates.

### 14.2. `bypassDocumentValidation` Is Not a Default Policy

Certain commands/drivers support `bypassDocumentValidation` when the user holds privileges. Treat it strictly as a **controlled exception**, never a default emergency workaround.

- Grant bypass privileges only for explicit operational reasons.
- Log audit trails and duration.
- Never use bypass to keep legacy writers emitting bad data.
- Under MongoDB 9.0 `constraint`, bypass capabilities are restricted per docs.

### 14.3. Validators Do Not Run on Deletes

Schema validation applies to inserts and updates; deleting a document does not require it to be "valid". Deletes remain governed by authorization, retention policies, and application/transaction rules.

### 14.4. Security When Logging Validation Failures

Validator error messages and logs can contain snippets of violating documents. Never dump full raw production documents into centralized logs without controls for PII, tokens, addresses, personal notes, and financial data.

Enforce RBAC, masking, retention limits, and log-level discipline when using `warn` or `errorAndLog`.

## 15. MongoDB Configuration: Identify Scope Before Editing

### 15.1. Configuration Layers

```text
Application / MongoDB Driver
  URI, pool, retryWrites, readPreference, timeouts
                     |
                     v
MongoDB Process startup
  mongod.conf / command flags, networking, TLS, storage
                     |
                     v
Server runtime parameters
  selected getParameter / setParameter capabilities
                     |
                     v
Database/collection options
  collMod validator, index definition, TTL, collation
                     |
                     v
Cluster-wide semantics
  replica set config, FCV, sharding, auth/upgrade features
```

These layers differ in **scope, required privileges, effective timing, and rollback**.

### 15.2. Runtime `getParameter` / `setParameter`

Reading a parameter:

```javascript
db.adminCommand({
  getParameter: 1,
  slowOpThresholdMs: 1
});
```

On supporting versions, `slowOpThresholdMs` can adjust at runtime, altering slow-operation logging/profiling thresholds. However, **not every parameter is runtime-mutable**, nor do all parameters behave identically across `mongod`/`mongos` or every release.

**Illustrative** example only:

```javascript
// Never run in production merely from a lesson example:
db.adminCommand({
  setParameter: 1,
  slowOpThresholdMs: 200
});
```

Requirements:

- Record the previous value.
- Verify mutability for your exact server version.
- Understand performance and logging impact.
- Check whether it persists across restarts.
- Define rollback/expiration and measure log volume.
- Apply consistently across all relevant members if needed.

### 15.3. Runtime Changes Do Not Always Persist Across Restarts

A successful `setParameter` call does **not automatically write to the startup config file**. On restart, the server reverts to `mongod.conf` or compiled defaults.

Your process must track:

- Desired state in config management/IaC.
- Observed runtime value.
- Effective parsed startup value.
- Configuration owner.
- Drift detection checks.

### 15.4. Startup Config Requires Proper Rollout

Changes to network/TLS, storage engine settings, or startup-only parameters generally require restarting processes to take effect.

For replica sets:

1. Check health and backups.
2. Confirm version/FCV compatibility throughout the transition.
3. Update members one by one per the **official rolling procedure**—never drop quorum all at once.
4. Monitor elections and replication catch-up.
5. Confirm app drivers remain compatible with CA/TLS/URIs.
6. Step down the primary only when needed and ready.
7. Retain rollback configs and keys.

Never invent a DIY "rolling restart" for sharded clusters, `mongos`, or config servers outside the documented upgrade order.

### 15.5. Reading Startup Options

```javascript
const config = db.adminCommand({
  getCmdLineOpts: 1
});

printjson({
  parsedStorage: config.parsed?.storage,
  parsedNet: config.parsed?.net,
  parsedSetParameter: config.parsed?.setParameter
});
```

Requires privileges and may be restricted on managed services. Output can expose **sensitive configuration details**; never paste raw output into public tickets.

### 15.6. Driver Configuration Is Also a Performance Change

Some real-world latency spikes stem not from `mongod`, but from:

- Saturated connection pools.
- `maxPoolSize` set too low or too high.
- `waitQueueTimeoutMS` or server selection timeouts.
- `retryWrites` and transient errors.
- `secondary` read preference hitting lagging secondaries.
- Mismatched `maxTimeMS` across endpoints.
- BSON serialization or network compression overhead.

Never tune server memory or indexes when MongoDB queries execute fast and requests are actually queueing in the driver pool.

## 16. Feature Compatibility Version and Server Upgrades

### 16.1. FCV Is Not a Cosmetic Version Number

MongoDB uses **featureCompatibilityVersion (FCV)** to control features and on-disk formats after binary upgrades. Two clusters running the same binary version with different FCVs differ in feature availability and downgrade paths.

Standard upgrade flow:

```text
Read upgrade release notes
          |
          v
Driver/application compatibility check
          |
          v
Backup + test restore
          |
          v
Rolling binary upgrade per topology
          |
          v
Observe cluster stability
          |
          v
Set FCV using documented procedure
          |
          v
Enable version-dependent features
```

Never run `setFeatureCompatibilityVersion` merely to unlock a hidden index or validator feature without completing the supported upgrade path.

### 16.2. Version-Aware Validator and Index Features

Examples of version-gated capabilities:

- Hidden indexes require supporting server version/FCV.
- Converting non-unique indexes to unique via `prepareUnique`/`dryRun` starts in MongoDB 6.0.
- Index build memory and disk safeguards evolve across releases.
- `validationAction: "errorAndLog"` starts in MongoDB 8.1.
- `validationLevel: "constraint"` starts in MongoDB 9.0.

Operations teams must verify **server version + FCV + topology + driver + Atlas plan** before releasing scripts.

### 16.3. Managed Services Differ from Self-Managed

Atlas and managed services may:

- Restrict `setParameter` commands.
- Orchestrate index builds and restarts automatically.
- Provide dedicated dashboards and query profilers.
- Block direct edits to `mongod.conf`.
- Manage backups, PITR, and upgrade windows internally.

Never try to run self-managed cluster commands to bypass provider controls.

## 17. Expand–Migrate–Contract: Safe Schema Evolution Pattern

### 17.1. Why Does It Take Multiple Releases?

Suppose you want to migrate:

```javascript
// Old
{ amount: "350000" }

// New
{ amountCents: NumberLong("35000000") }
```

You cannot deploy a validator requiring `amountCents: long` before every writer and legacy document has converted.

### 17.2. Expand

- Updated app reads both `amount` and `amountCents`.
- Updated app starts writing the new field.
- Establish a clear single source of truth during transition.
- If dual-writing, keep both fields consistent with mismatch detection.
- Pre-build any needed new indexes as hidden.
- Enable the validator in `warn` mode first.

### 17.3. Migrate

- Backfill legacy documents in small batches.
- Use compare-and-set or version checks to avoid overwriting concurrent writes.
- Track progress by `_id` or job state with idempotent retries.
- Validate data against business semantics (currency units, timezones, enums).
- Monitor replication lag, write p95, disk, and validation logs.
- Use canary cohorts plus a manual queue for unconvertible edge cases.

### 17.4. Contract

- Stop writing/reading the legacy field once all clients have migrated.
- Switch validator to `moderate + error`, then `strict + error` when ready.
- Hide the legacy index, measure, and drop later.
- Remove legacy code/fields in a dedicated change.
- Retain backups/rollback paths per retention policy.

**Contract must be the final step**, only after proving zero legacy writers or unmigrated records remain.

## 18. Idempotent Migrations and Concurrent Writes

### 18.1. Why Is Collection-Wide `updateMany` Dangerous?

A command like:

```javascript
// Never run on live data:
db.orders.updateMany(
  {},
  { $set: { amountCents: NumberLong(0) } }
);
```

can corrupt every order's value, flood the oplog, spike dirty pages, cause secondary lag, and leave no simple rollback.

### 18.2. Updates Must Filter on Old Value / Version

A record:

```javascript
{
  _id: orderId,
  version: 7,
  amount: "350000",
  amountCents: null
}
```

After the application computes the valid target value:

```javascript
db.orders.updateOne(
  {
    _id: orderId,
    version: 7,
    amount: "350000",
    amountCents: null
  },
  {
    $set: {
      amountCents: NumberLong("35000000"),
      migrationVersion: "amount-v2"
    },
    $inc: { version: 1 }
  }
);
```

The filter detects if the document changed before the migration wrote. If `matchedCount: 0`, re-read and decide; **never fall back to filtering solely by `_id` and overwriting**.

For legacy records missing fields or versions, tailor filters to exact existing state using `$exists` and value checks—never stamp one template blindly across all documents.

### 18.3. Batches and Checkpoints

```text
Read candidate IDs (bounded)
         |
         v
Transform and validate in app
         |
         v
BulkWrite bounded updates
         |
         v
Record matched/modified/conflicts
         |
         v
Checkpoint last processed ID
         |
         v
Throttle, observe, repeat
```

Never hold an unbounded cursor or a multi-million-document transaction open. Use small chunks, stop flags, rate limits, and restart-safe checkpoints.

### 18.4. Handling New Writes During Backfill

Two coordination models exist:

**Option A — Quiesce writes:** pause writes to the target dataset during a maintenance window.

**Option B — Online migration:** applications write the new contract, backfill uses versioned compare-and-set, and outbox/change streams/reconciliation handle eventual consistency.

Never assume a scan at T0 followed by an update at T1 sees a frozen snapshot while live services keep writing.

## 19. Canaries, Traffic, and Query Plan Rollbacks

### 19.1. Break Rollouts into Checkpoints

```text
Baseline captured
     |
New index built hidden
     |
Index unhidden / query plans observed
     |
App canary / guardrails
     |
Validator warn
     |
Migration small cohort
     |
Validator moderate+error
     |
Validator strict+error
     |
Old index hidden, then drop later
```

Exact ordering depends on the goal. If the new app relies on the new index, build and unhide it before ramping app traffic.

### 19.2. Some Changes Are Collection-Wide

- `collMod` validators affect all write paths on that collection per rules.
- Hiding/unhiding an index alters the planner for the entire collection, not one user.
- TTL edits affect all eligible documents.
- Cluster startup config affects the node.

Thus **application traffic canaries** do not isolate blast radius for global DDL. For high-risk changes, use shadow collections, versioned namespaces, or realistic staging.

### 19.3. Guardrails

Monitor during rollout:

- API p95/p99 and error rates.
- `DocumentValidationFailure` / `DuplicateKey` rates.
- MongoDB read/write latency.
- `totalDocsExamined` / `totalKeysExamined` on hot queries.
- Index build progress.
- CPU, memory, disk IOPS, queue depth, and free space.
- Replication lag and member health.
- TTL deletions when altering retention.
- Business conversions and record counts.

Set thresholds against internal baselines and SLOs—never assume a blanket "5% latency increase is always fine".

### 19.4. Never Delete Data to Roll Back

The safest rollbacks **preserve data**:

- Hide the new index or unhide the old index.
- Restore the prior validator from the archived snapshot definition.
- Revert to the compatible prior application query version.
- Restore prior runtime parameter values.
- For startup configs, perform a valid rolling rollback.

Once data has been migrated or expired by TTL, rollback requires a **forward fix or controlled restore**, not a single undo command.

## 20. Rollback Capability Matrix

| Change | How to Revert | Caveat |
| --- | --- | --- |
| Add index | Hide or drop index | Dropping requires rebuilding if needed again |
| Unhide new index | Hide index | Plan cache and plans may shift |
| Hide old index | Unhide old index | Fast since index stays maintained |
| Drop index | Recreate/rebuild from definition | Consumes I/O and time; constraints lost meanwhile |
| Validator `warn` | Restore old validator/options | Violations already accepted remain in DB |
| Validator `strict`/`error` | Restore prior level/action/rules | Rejected writes do not replay automatically |
| Unique conversion | Follow documented constraint/index procedure | Not a trivial toggle; duplicates/queries need care |
| Shorten TTL | Raise TTL back | Deleted documents **do not auto-recover** |
| Runtime `setParameter` | Re-apply previous value | Verify persistence across restarts |
| Startup config | Rolling restart with old config | Preserve quorum and compatibility |
| FCV/major upgrade | Official downgrade path if supported | May be impossible once new features are used |
| Data migration | Reverse migration if lossless | Information may be lost if transform was lossy |

Never promise "every schema change rolls back in 1 minute" when some changes are semantically destructive.

## 21. Monitoring Risk During and After Changes

### 21.1. Minimal Dashboard

```text
+-----------------------------+------------------------------+
| API p95 / p99 + error rate  | MongoDB read/write latency   |
+-----------------------------+------------------------------+
| Validation failures         | DuplicateKey rate            |
+-----------------------------+------------------------------+
| Index build progress        | Index size / disk free       |
+-----------------------------+------------------------------+
| Query plan/docs examined    | Index usage ($indexStats)    |
+-----------------------------+------------------------------+
| CPU / WiredTiger cache      | Disk IOPS / await / queue    |
+-----------------------------+------------------------------+
| Replication lag + elections | Migration progress/conflicts |
+-----------------------------+------------------------------+
| TTL deletions               | Config/version drift         |
+-----------------------------+------------------------------+
```

### 21.2. Monitor Over Time, Not Just One Snapshot

An index might cut p95 immediately yet raise **write overhead** days later under peak ingestion. A validator might trigger errors only when a nightly batch job runs. A TTL change might purge documents days later when records cross the age threshold.

Therefore:

- Watch closely right after deploy.
- Observe across at least one full critical business cycle.
- Slice metrics by namespace, query shape, and client version.
- Log exact timestamps of hide/unhide/metric resets.
- Handle counter resets properly across process restarts.

### 21.3. Alerts Distinguishing Incidents from Normal Variance

| Alert | Investigation Focus |
| --- | --- |
| Index build failed | Duplicates, disk space, quorum, conflicts, version |
| Query latency spiked after unhide/hide | Which plan the planner chose and for which query shapes |
| Validation errors spiked | Legacy writer, wrong BSON type, unmigrated documents |
| `DuplicateKey` spiked | Race condition, new unique index, missing key semantics |
| TTL deletes spiked after retention change | Eligible record count and business policy |
| Replication lag rose during migration | Batch size, secondary disk/CPU, write concern |
| Free disk dropped during index build | Index/temp files, snapshots, data growth |
| Config drift after restart | Non-persistent runtime parameter, stale IaC |

Never reflexively drop an index or disable a validator the second an alert fires; follow the **decision tree and change owner**.

## 22. Runbook: Index Build Slow or Stalled

### 22.1. Observations

```text
Index build running 40 minutes
Disk queue rising
Replication lag growing
Primary is healthy
One voting secondary is unreachable
```

This combines I/O pressure with **commit quorum waiting**. Never assume "server deadlock" based solely on build duration.

### 22.2. Procedure

1. Confirm namespace, index name, and change ticket.
2. Inspect `currentOp`/logs for build state and participating members.
3. Check free disk and temp space across every member.
4. Check CPU, WiredTiger cache, IOPS, and replication lag.
5. Check voting members and commit quorum.
6. Pause non-urgent batch jobs if needed.
7. Decide whether to wait, recover the unreachable node, or abort per runbook.
8. Document status/errors if aborted.
9. Never blindly launch a second build with the same index name.

Lowering commit quorum below default trades away consistency/availability guarantees—never do it casually.

## 23. Runbook: Application Write Errors After Enabling Validator

### 23.1. Signals

- `DocumentValidationFailure` spikes.
- Insert/update API error rates rise.
- Only one legacy app version or ETL job is failing.
- Data audits reveal remaining legacy invalid records.

### 23.2. Investigation

1. Inspect active validator/level/action via `getCollectionInfos`.
2. Identify violating document cohorts and BSON types.
3. Locate un-updated app versions and code paths.
4. Separate **new invalid inserts** from **updates to invalid legacy docs**.
5. Check privacy of error/log payloads.
6. Compare against rollout plan and rollback thresholds.

### 23.3. Mitigation

Depending on severity:

- Fix or roll back the offending writer code.
- Step back from `strict` to `moderate` if approved and aligned with goals.
- Revert `error` to `warn` **strictly as a tracked emergency exception**.
- Remediate legacy records in batches and retry failed requests safely.
- Never turn on `bypassDocumentValidation` across all writers to bypass the validator.

Relaxing a validator does not automatically replay rejected requests; applications need idempotent retries or reconciliation.

## 24. Runbook: Hiding/Dropping an Index Slowed Queries

Suppose after hiding an old index:

```text
Query p95: 50 ms -> 650 ms
DocsExamined: 200 -> 2,000,000
COLLSCAN on hot path
```

Action:

1. Confirm before/after query shapes and index names.
2. Run a bounded `explain` on a representative query.
3. If the index is still hidden, **unhiding** is the fast rollback.
4. If already dropped, rebuild with a sized build plan; throttle/shed traffic temporarily if needed.
5. Inspect plan cache, filters, collations, and query changes.
6. Never inflate connection pools to "mask" a `COLLSCAN`.
7. Document root cause and update the index inventory.

## 25. Hands-On Lab on Test MongoDB: Hidden Index + Phased Validator

### 25.1. Conditions and Boundaries

This lab uses only a **test MongoDB deployment** supporting hidden indexes and `collMod` validators, with collection-creation privileges. Never run these commands against production.

Safe design:

- Dedicated lab database with a **unique randomized collection name** per run.
- Documents tagged with a unique `runId` and deterministic `_id`.
- A legacy invalid document inserted **before enabling the validator**.
- Clean up only documents created by the current run.
- Never modify cluster config/FCV or run system-wide migrations.
- Never drop databases or indexes used by others.

### 25.2. Create an Isolated Namespace

```javascript
const lab = db.getSiblingDB("mongo_change_row380_lab");
const runId = "row380-" + new ObjectId().toHexString();
const collName = "orders_" + runId.replace(/-/g, "_");

if (lab.getCollectionNames().includes(collName)) {
  throw new Error("Collection name already exists; refusing to overwrite.");
}

lab.createCollection(collName);
const orders = lab.getCollection(collName);

printjson({
  database: lab.getName(),
  collection: orders.getName(),
  runId
});
```

### 25.3. Insert Documents Before Enabling the Validator

```javascript
const validId1 = new ObjectId();
const validId2 = new ObjectId();
const legacyId = new ObjectId();

orders.insertMany([
  {
    _id: validId1,
    runId,
    tenantId: "TENANT-LAB",
    status: "CREATED",
    amountCents: NumberInt(1000),
    createdAt: new Date()
  },
  {
    _id: validId2,
    runId,
    tenantId: "TENANT-LAB",
    status: "PAID",
    amountCents: NumberInt(2500),
    createdAt: new Date()
  },
  {
    _id: legacyId,
    runId,
    tenantId: "TENANT-LAB",
    status: "paid",            // wrong legacy enum
    amountCents: "2500",       // wrong legacy BSON type
    createdAt: new Date()
  }
]);

print("owned=" + orders.countDocuments({ runId }));
```

### 25.4. Create a Hidden Compound Index

```javascript
const indexName = "row380_tenant_status_created_v1";

orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: indexName, hidden: true }
);

printjson(orders.getIndexes());
```

The query planner ignores the hidden index. Test:

```javascript
const q = {
  tenantId: "TENANT-LAB",
  status: "PAID"
};

printjson(
  orders.find(q)
    .sort({ createdAt: -1 })
    .limit(10)
    .explain("executionStats")
);
```

Then unhide:

```javascript
orders.unhideIndex(indexName);

printjson(
  orders.find(q)
    .sort({ createdAt: -1 })
    .limit(10)
    .explain("executionStats")
);
```

On a 3-document collection, the planner may **skip the index** even after unhiding because a `COLLSCAN` is cheaper. That is normal. The goal is understanding index eligibility, not benchmarking performance in a tiny lab.

### 25.5. Define the Validator

```javascript
const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["tenantId", "status", "amountCents"],
    properties: {
      tenantId: { bsonType: "string", minLength: 1 },
      status: { enum: ["CREATED", "PAID", "CANCELLED"] },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      }
    }
  }
};
```

### 25.6. Enable `warn + moderate`

```javascript
lab.runCommand({
  collMod: collName,
  validator,
  validationLevel: "moderate",
  validationAction: "warn"
});
```

The legacy document stays in place because `collMod` does not auto-migrate data. Measure:

```javascript
printjson(
  orders.find({
    runId,
    $nor: [validator]
  }).toArray()
);
```

Test an invalid insert:

```javascript
const warnBadId = new ObjectId();

orders.insertOne({
  _id: warnBadId,
  runId,
  tenantId: "TENANT-LAB",
  status: "paid",
  amountCents: NumberInt(-5)
});
```

Under `warn`, MongoDB permits the insert and logs a validation warning. Use synthetic data only in the lab collection and inspect diagnostic logs if permitted (no need for admin privileges merely to confirm the demo).

### 25.7. Switch to `moderate + error`

```javascript
lab.runCommand({
  collMod: collName,
  validator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Test an invalid insert with a new ID:

```javascript
const rejectedId = new ObjectId();

try {
  orders.insertOne({
    _id: rejectedId,
    runId,
    tenantId: "TENANT-LAB",
    status: "UNKNOWN",
    amountCents: NumberInt(-10)
  });
  print("UNEXPECTED: invalid document inserted");
} catch (e) {
  print("Expected validation error: " + e.codeName);
}
```

When rejected, no document with `rejectedId` exists. In tooling targeting unknown server versions, check error codes/names rather than assuming identical error message strings across drivers.

### 25.8. Fix Only the Lab's Legacy Documents

On live data, never alter statuses or amounts without authoritative rules. In this lab we **know** the synthetic values upfront:

```javascript
const fixedLegacy = orders.updateOne(
  {
    _id: legacyId,
    runId,
    status: "paid",
    amountCents: "2500"
  },
  {
    $set: {
      status: "PAID",
      amountCents: NumberInt(2500)
    }
  }
);

const fixedWarn = orders.updateOne(
  {
    _id: warnBadId,
    runId,
    status: "paid",
    amountCents: NumberInt(-5)
  },
  {
    $set: {
      status: "CANCELLED",
      amountCents: NumberInt(0)
    }
  }
);

printjson({ fixedLegacy, fixedWarn });
```

Setting `0` here is purely a lab convention; it does **not** represent how to resolve negative amounts in production. Next:

```javascript
print("invalidOwned=" + orders.countDocuments({
  runId,
  $nor: [validator]
}));
```

### 25.9. Switch to `strict + error`

After verifying zero invalid test records remain:

```javascript
lab.runCommand({
  collMod: collName,
  validator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Confirm the stored validator:

```javascript
printjson(
  lab.getCollectionInfos({ name: collName })
);
```

Try an invalid update on a valid document:

```javascript
try {
  orders.updateOne(
    { _id: validId1, runId },
    { $set: { amountCents: "wrong type" } }
  );
  print("UNEXPECTED: invalid update accepted");
} catch (e) {
  print("Expected validation error: " + e.codeName);
}
```

With the validator active, the update fails and `amountCents` retains its valid type.

### 25.10. Hide the Index Again to Simulate Rollback

```javascript
orders.hideIndex(indexName);
printjson(orders.getIndexes());
```

This avoids physically dropping the index, demonstrating that hide/unhide controls query planner eligibility.

### 25.11. Clean Up Only Documents Owned by This Run

Verify first:

```javascript
print("db=" + lab.getName());
print("collection=" + collName);
print("runId=" + runId);

const ownedDocs = orders.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  ownedCount: ownedDocs.length,
  ownedIds: ownedDocs.map((x) => x._id)
});
```

Once you confirm the exact collection, `runId`, and owned documents:

```javascript
for (const item of ownedDocs) {
  orders.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + orders.countDocuments({ runId }));
```

The lab collection and index remain after cleaning the documents. A lab administrator may reclaim the **exact randomized collection** per environment policy, without ever running `dropDatabase()` or `deleteMany({})` on a shared database.

## 26. Sample Change Plan for a New Production Index

### 26.1. Before

```text
[ ] Owner + approvals + scheduled window
[ ] Cluster/version/FCV/topology verified
[ ] Existing indexes and validator/export config saved
[ ] Query plans and latency baseline
[ ] Disk/memory/IOPS headroom on every member
[ ] Replication healthy; no other active index builds
[ ] Data duplicates/constraints checked if unique
[ ] Backup and recovery plan ready
[ ] App rollback / feature flags prepared
```

### 26.2. During

```text
1. Create index hidden (where appropriate).
2. Observe index build progress, disk, CPU, and replication.
3. Confirm build completed across relevant nodes.
4. Unhide at change checkpoint.
5. Compare query plans + p95/p99, error rate, and writes.
6. Hold/continue/rollback based on defined guardrails.
7. Record timestamp, operator, and results.
```

### 26.3. After

```text
[ ] No unexplained query regressions
[ ] No new write failures / DuplicateKey surprises
[ ] Replication and disk within budget
[ ] Index owner/use cases documented
[ ] Previous index kept until representative observation
[ ] Rollback/forward-fix state clear
[ ] Review after business cycle / nightly jobs
```

This is a **runbook template**, not a Content QA evaluation of the lesson.

## 27. Sample Change Plan for a Validator

Before enabling `error`:

- Audit violators by BSON types and business meaning.
- Confirm all services, ETL jobs, migrations, and admin scripts emit valid shapes.
- Start with `moderate + warn` when legacy data exists.
- Watch warning trends and log volumes.
- Transition to `moderate + error` once new violation sources are fixed.
- Backfill legacy records using idempotency and compare-and-set.
- Switch to `strict + error` once audits confirm readiness.
- Use MongoDB 9.0+ `constraint` only after preparation and understanding its restrictions.

Rolling back restores prior validator/options, without automatically fixing invalid writes accepted under `warn` or replaying requests rejected under `error`.

## 28. Sample Change Plan for Server Configuration

Before running `setParameter` or editing `mongod.conf` or FCV:

1. Identify whether the setting is **runtime, startup, or cluster-scoped**.
2. Read the official docs for your exact MongoDB version, FCV, and edition.
3. Snapshot current config and runtime parameters.
4. Determine whether the change requires restarts, elections, and rolling order.
5. Check TLS/auth/network and driver reconnect resilience.
6. Test in staging with a rollback rehearsal.
7. Schedule backups, maintenance windows, and notifications.
8. Roll out node by node per supported procedure.
9. Verify observed/runtime values post-restart.
10. Compare latency, error rates, replication, and logs against baseline.

Never modify security, durability, or eviction/cache settings "just to test" in production without approval.

## 29. Common Pitfalls

| Pitfall | Why It Is Wrong | Right Practice |
| --- | --- | --- |
| Building an index on 100M docs without checking free disk | Index builds and temp files can fill disks | Forecast space; monitor every member |
| "Online builds never affect writes" | Start/end locks, CPU/IOPS load, and commit quorum apply | Measure, pick windows, enforce guardrails |
| "Planner will definitely use the new index" | Selection depends on query shape and cost | Verify with `explain` and latency |
| "Hidden indexes cost zero resources" | Still maintained on writes and consume disk | Account for write overhead |
| "Hiding a unique index disables uniqueness" | Uniqueness remains enforced | Never hide to relax constraints |
| "Hiding a TTL index pauses expiration" | Hidden TTL indexes still expire docs | Manage retention intentionally |
| "You can hint a hidden index" | Hidden indexes are ineligible | Perform a controlled unhide |
| "Zero ops in 1 hour means drop the index" | Nightly/monthly jobs may need it | Observe across full business cycles |
| "A dropped index rolls back via unhide" | Physical index is gone | Must rebuild |
| "A unique index auto-merges duplicates" | Build/conversion fails on duplicates | Audit and resolve per business rules |
| "`prepareUnique` cleans old duplicates" | Only blocks new duplicates | Run `dryRun` and remediate legacy data |
| "Shortening TTL leaves old data alone" | Can trigger mass deletions | Count eligible docs; legal review |
| "`collMod` fixes all invalid documents" | Does not retro-migrate data | Audit + backfill |
| "Strict validator means all existing docs are valid" | Legacy invalid docs can remain | Audit and reconcile |
| "`moderate` blocks invalid updates to legacy docs" | Existing invalid docs are exempt from certain checks | Understand levels; move to `strict` post-migration |
| "`warn` keeps bad data out" | Permits invalid writes through | Use for observation, then move to `error` |
| "Rolling back `error` replays rejected requests" | Failed requests do not auto-replay | Idempotent retries / reconciliation |
| "Use bypass for every migration" | Weakens invariants and auditing | Restrict privileges and scope |
| "Client schema maps retro-migrate DB data" | Does not rewrite existing collection docs | Expand–migrate–contract |
| "`setParameter` persists forever" | Many runtime settings reset on restart | Update IaC + check config drift |
| "Every setting is runtime-changeable" | Many are startup-only or managed-restricted | Check version and scope |
| "Change FCV arbitrarily to unlock a feature" | FCV ties to upgrade/downgrade paths | Follow documented upgrade procedures |
| "App canaries scope DDL to one user group" | Validators and indexes apply collection-wide | Use shadow collections / staging / rollback |
| "Replica sets need only primary checks" | Index builds and replication hit all members | Monitor all data-bearing members |
| "Fast `explain` means the whole system is fast" | Misses live traffic, cache pressure, and p99 | Monitor production SLOs |
| "Filtering migrations by `_id` alone is enough" | Concurrent updates can be clobbered | Use compare-and-set / version checks |
| "Delete backups right after migration" | Rollbacks or retention may need them | Retain per policy |
| "TTL mistakes reverse by flipping the option back" | Purged data does not auto-restore | Prepare recovery backups beforehand |
| "Validators replace authorization" | Validators do not enforce tenant access | Enforce RBAC + app authorization |

## 30. Applied Exercises

### Exercise A — Planning an Index

An 80M-document `orders` collection runs:

```javascript
find({ tenantId, status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(30)
```

Design the compound index, explain key order, list metrics to capture, explain why a hidden index helps, and explain its limitation for per-tenant canaries.

### Exercise B — Finding Duplicates Before Unique

Data:

```javascript
{ tenantId: "T1", externalOrderId: "A1" }
{ tenantId: "T1", externalOrderId: "A1" }
{ tenantId: "T2", externalOrderId: "A1" }
```

1. If the unique key is `{tenantId, externalOrderId}`, which records conflict?
2. Why shouldn't duplicates be auto-deleted blindly?
3. Outline the `prepareUnique → dryRun → unique` workflow.
4. What shard key constraints apply if the collection is sharded?

### Exercise C — Shortening TTL

Session documents have existed for 40 days. TTL is lowered from 60 days to 7 days.

1. Which sessions become eligible for deletion?
2. Does hiding the index pause deletion?
3. Why are backups and legal review needed?
4. How should replication lag and IOPS be monitored?

### Exercise D — Changing Validators on Legacy Data

Existing docs:

```javascript
{ status: "paid", amountCents: "1000" }
{ status: "PAID", amountCents: NumberInt(1000) }
```

The validator requires `status: "PAID"` and `amountCents` as int/long.

1. Does `collMod` fix the first document automatically?
2. Compare `warn`, `moderate + error`, and `strict + error`.
3. What happens if an older service updates `note` on the first document?
4. Design a verifiable migration.

### Exercise E — Adding a Required Field

Developers want `currency` to be a required string on all invoices.

1. Why shouldn't `strict` validation turn on before every client writes `currency`?
2. How does expand–migrate–contract apply?
3. Where must legacy missing `currency` values be derived from?
4. When is it safe to remove legacy read-fallback code?

### Exercise F — Runtime Config Change

An operator runs `setParameter` during peak traffic, and the change disappears after a restart.

1. Why?
2. What must be recorded in config management?
3. How do you audit observed vs. desired config?
4. What are startup-only settings?

### Exercise G — FCV and Upgrades

A service wants a MongoDB 9.0 feature; the new binary is installed, yet FCV has not been raised.

1. Why might the feature still be unavailable?
2. Why shouldn't FCV be changed before completing the rolling binary upgrade?
3. Which driver, backup, and downgrade checks are needed?
4. Who approves irreversible release steps?

### Exercise H — Index Build Waiting on Commit Quorum

One voting secondary is unreachable; the primary finished scanning, yet the index is not marked ready.

1. How does commit quorum cause this?
2. Why shouldn't you lower quorum hastily?
3. Which node, disk, and log checks are needed?
4. How do you verify build completion once the member returns?

### Exercise I — Designing Rollback

After hiding an old index, p99 jumps from 90 ms to 2.5 s. The old index is still hidden.

1. Which command restores eligibility immediately?
2. Why would dropping it have made recovery much harder?
3. Should you inspect plan caches and query shapes?
4. What SLO and observation rules trigger rollback?

### Exercise J — Currency Migration

Some `amount` fields store VND strings, while others already store "amount multiplied by 100". Migrate to `amountCents: Long`.

1. Why can't you multiply every record by 100 blindly?
2. Which metadata or sources must guide normalization?
3. Design an update with version/value filters.
4. How do you detect conflicts, retry idempotently, and audit totals?

### Exercise K — Managed MongoDB

A guide shows startup YAML for self-managed MongoDB, yet the real service runs on Atlas.

1. Why can't you edit `mongod.conf` directly?
2. Which Atlas controls apply instead?
3. How might metrics and privileges differ?
4. Who owns rolling upgrades, backups, and change windows?

### Exercise L — Linked Change Sequence

A project is changing indexes, standardizing BSON types, and planning to drop legacy fields.

Plan at least 5 phases, specifying for each phase:

- Preconditions.
- Commands or config changes.
- Success metrics.
- Risks and race conditions.
- Rollback or forward-fix path.
- When to notify application owners.

## 31. Official Reference Documentation

Exact behavior varies by MongoDB server version, FCV, driver, and topology. Before running production DDL, verify the release-specific documentation and effective privileges:

- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — index types and usage.
- [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — build lifecycle, locks, replicated index builds, commit quorum, and resource needs.
- [Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/) — hide/unhide, unique/TTL semantics, `$indexStats` reset.
- [`createIndexes` command](https://www.mongodb.com/docs/manual/reference/command/createIndexes/) — syntax and options.
- [`collMod` command](https://www.mongodb.com/docs/manual/reference/command/collMod/) — validators, validationLevel/action, TTL, hidden, and convert-to-unique.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — `$jsonSchema` and impact on existing documents.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — `moderate`, `strict`, and `constraint` (where available).
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — `warn`/`error`/`errorAndLog`.
- [Convert an Existing Index to a Unique Index](https://www.mongodb.com/docs/manual/core/index-unique/convert-to-unique/) — `prepareUnique`, `dryRun`, and resolving duplicates.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — TTL expiration and monitor behavior.
- [`$indexStats`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/) — reading index usage.
- [`getCmdLineOpts`](https://www.mongodb.com/docs/manual/reference/command/getCmdLineOpts/) — parsed startup configuration.
- [`getParameter` / `setParameter`](https://www.mongodb.com/docs/manual/reference/command/setParameter/) — runtime parameters and support rules.
- [Upgrade a Replica Set](https://www.mongodb.com/docs/manual/release-notes/) — release notes and FCV/upgrade paths.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — managed service metrics.
- [Rolling Index Builds](https://www.mongodb.com/docs/manual/core/rolling-index-builds/) — exceptions, trade-offs, and warnings.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — write acknowledgments and uncertain outcomes.

**Note:** Current documentation covers capabilities introduced in MongoDB 8.1 and 9.0; do not assume they exist in 6.0/7.0/8.0. Verify hidden indexes, unique conversions, and `collMod` options for your exact server and FCV before applying.

## 32. Conclusion

**Managing index, validator, and configuration changes on live data** is a multi-stage operational discipline—not running a single DDL command.

- **Indexes:** design from query patterns, build with capacity headroom, hide before dropping, respect unique/TTL semantics, and track commit quorum and query plans.
- **Validators:** never treat `collMod` as magic legacy data repair. Progress from `warn` to `moderate + error`, migrate data, then enforce `strict + error`, pairing data audits with writer compatibility.
- **Configuration:** separate driver, runtime, startup, cluster, and FCV layers, understanding restart requirements, persistence, deployment ownership, and downgrade rules.
- **Live data:** migrations require idempotency, compare-and-set, audits, retention checks, backups, and proper privileges. Rollbacks cannot automatically restore TTL-deleted documents or lossy transforms.
- **Observability:** track p95/p99, error rates, disk/CPU, replication, index builds/usage, validation errors, and business outcomes continuously from baseline through post-rollout.

**Core principle:** before every change, identify **what is impacted, success criteria, safety evidence, fault detection, and the recovery path**. A good change does not merely make queries faster or data cleaner—it deploys and runs safely while users continue using MongoDB.
