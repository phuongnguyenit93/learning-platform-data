# MongoDB Review Checklist for Data Modeling, Queries, Security, Backups, and Operations

A MongoDB application can pass all basic CRUD tests and still harbor severe risks in production: documents growing without bound over time, indexes misaligned with actual query shapes, `null` values breaking unique constraints, cross-tenant data leaks, untested backups, or a failover triggering a flood of duplicate orders due to non-idempotent retries. These issues span **distinct architectural layers**, so inspecting Java code alone or running a single `db.stats()` check cannot yield reliable confidence.

The **"MongoDB Review Checklist for Data Modeling, Queries, Security, Backups, and Operations"** belongs to the **Summary and Reference** chapter of the **Database Engine Document MongoDB** module. Use it to review designs before rollout, audit live systems periodically, prepare major migrations, and hand off operations. Every item should produce **concrete evidence** and **actionable decisions** rather than a vague "looks good."

## 1. Desired Outcomes and Five Review Pillars

After completing this checklist, the responsible team should be able to answer:

1. **Data modeling:** Do document shapes, relationships, BSON types, unique constraints, and data lifecycles match business rules and growth projections?
2. **Queries and performance:** Are critical queries, aggregations, and indexes verified against realistic workloads and proper `explain` analysis?
3. **Security:** Do authentication, database RBAC, tenant authorization, network/TLS, secrets management, and PII protection provide defense in depth?
4. **Backups and recovery:** Are backups usable, are RPO/RTO targets realistic, and do restore procedures and drill evidence exist?
5. **Operations:** Does the system have monitoring, alerts, capacity plans, runbooks, maintenance procedures, and failure/failover response plans?

End-to-end review diagram:

```text
Business requirements & SLO/RPO/RTO
                 |
                 v
           DATA MODELING
    schema, keys, relations, retention
                 |
                 v
         QUERIES AND INDEXES
      access patterns, explain, load
                 |
                 v
              SECURITY
    auth, roles, tenant, TLS, secrets
                 |
                 v
          BACKUPS / RESTORES
      backups, PITR, drills, evidence
                 |
                 v
             OPERATIONS
       metrics, failover, runbooks
                 |
                 v
         RISKS + OWNER + DUE DATE
                 |
                 v
        Release / improvement decision
```

**Scope:** self-managed MongoDB, replica sets, sharded clusters, Atlas, and Java/Spring Data MongoDB applications; exact capabilities depend on server version, cluster tier, topology, driver, and configuration. Examples use placeholder databases and synthetic data. Never alter schemas, delete records, or inject faults in production solely because an item appears on this checklist.

## 2. Using the Checklist Without Turning It Into Paperwork

Assign one of four statuses to each item:

| Status | Meaning | Example |
| --- | --- | --- |
| **PASS** | Verified with current, valid evidence | Unique index exists and duplicate test fails as expected |
| **FAIL** | Evidence shows the requirement is not met | Read-only account still holds delete privileges |
| **UNKNOWN** | No reliable evidence exists yet | Backups run on schedule but restore has never been tested |
| **N/A** | Not applicable, with justification | Sharding is not used, so shard key checks are N/A |

Never mark `PASS` simply because a setting appears in source code or a wiki. **Code written, resources provisioned, live runtime configuration, and observed runtime behavior** are four separate forms of evidence.

Record each finding with:

```text
Check ID:
Requirement / Criterion:
Environment:
Status: PASS | FAIL | UNKNOWN | N/A
Evidence: link to dashboard / query plan / test report / change ticket
Impact if wrong:
Risk severity:
Owner:
Due date:
Temporary mitigation:
Review date and reviewer:
```

### Risk Classification

- **Critical:** potential data loss, credential exposure, cross-tenant read/write leaks, or inability to recover a mission-critical service.
- **High:** likely production outage, rapid resource exhaustion, loss of consistency guarantees, or missed RPO/RTO.
- **Medium:** insufficient capacity headroom, unstable query latency under load, or missing key alerts.
- **Low:** documentation gaps or minor improvements with verified workarounds.

These are review guidelines; final severity depends on service criticality, blast radius, exploitability, and organizational policy.

## 3. When Should You Re-Run the Review?

| Timing | Primary Focus |
| --- | --- |
| **Before design** | Access patterns, aggregate boundaries, growth, security model, RPO/RTO |
| **Before release** | Live indexes, migrations, query plans, permissions, backups, rollback |
| **After workload shifts** | Index performance, hot keys, CPU/RAM/disk, SLOs |
| **After adding sensitive collections/fields** | Schema validation, DTO/redaction, encryption, access control |
| **Before sharding / cluster resize** | Shard key, unique indexes, capacity, data migration, failover |
| **Before version upgrades** | Driver/server compatibility, deprecated behaviors, restore/failback |
| **Monthly / quarterly** | Role reviews, backups/drills, alert rules, unused indexes, retention |
| **Post-incident** | Root cause, affected data, alert gaps, runbooks, remediation |

For small systems, multiple checks fit into one session. For large systems, divide ownership across engineering, DBA/SRE, security, and business stakeholders.

## 4. Lock In Non-Functional Requirements Before Auditing

You cannot declare a cluster "good enough" without knowing its targets:

- **Read/write SLOs:** p95/p99 latency, throughput, error budget, concurrent clients.
- **RPO:** maximum acceptable data loss window.
- **RTO:** maximum acceptable recovery duration.
- **Data retention:** what data must be kept, for how long, and where.
- **Consistency:** do users need read-your-writes, latest reads, or eventual consistency?
- **Security and compliance:** PII categories, residency, auditing, least privilege.
- **Growth:** data, index, oplog, backup, working set, and write volume trajectories.
- **Failure domains:** node, AZ, region, cloud provider, or external dependencies.

Checklist:

- [ ] Critical use cases and their respective owners are listed.
- [ ] Success and failure semantics are defined for critical writes.
- [ ] Latency/availability SLOs and retry budgets are defined.
- [ ] Approved RPO/RTO targets exist—not just "daily backups."
- [ ] Encryption, logging, and retention requirements are documented.
- [ ] Cost and scaling bounds are understood.

## 5. Build a MongoDB Asset Map

Before reviewing individual collections, compile an **inventory of what is actually running**:

```text
Environment -> cluster / project
            -> region / topology / MongoDB version
            -> databases / collections
            -> indexes / validators / TTL
            -> service accounts / roles
            -> applications / jobs / CDC consumers
            -> storage / backup / network controls
            -> owning team / escalation contact
```

Checklist:

- [ ] Every critical cluster, database, and collection has an owner.
- [ ] Server version, Java driver, Spring Data version, and upgrade paths are known.
- [ ] Replica set / sharded topology, shard keys, and regions are documented.
- [ ] All write paths outside the primary app are known: ETL, migrations, schedulers, `mongosh`, import tools.
- [ ] All read clients are known: APIs, analytics, change streams, exports, backups.
- [ ] A sufficiently representative staging environment exists for major changes.
- [ ] Secrets and topology details are stored in access-controlled systems, never public repos.

**Risk signal:** claiming "only this app writes to the collection" while unowned migration scripts or background workers exist.

## 6. Data Modeling: Aggregate Boundaries

MongoDB stores data as documents; **query units and single-document atomicity** should guide boundary design.

Order example:

```javascript
{
  _id: "ORD-001",
  tenantId: "tenant-a",
  status: "RESERVED",
  items: [
    { sku: "SKU-A", quantity: 2, price: NumberDecimal("125000") },
    { sku: "SKU-B", quantity: 1, price: NumberDecimal("85000") }
  ],
  total: NumberDecimal("335000")
}
```

Line items typically read and modified inside a single order context often fit well embedded in the order document. Conversely, product master data, long-term price history, or customer profiles with independent lifecycles usually belong elsewhere.

Checklist:

- [ ] Each document represents a clearly defined aggregate or business entity.
- [ ] Co-read fields are deliberately evaluated for embedding.
- [ ] Referenced collections have clear ownership and lifecycles.
- [ ] Rules exist when embedded snapshot data differs from mutable referenced sources.
- [ ] Guidelines prevent write hotspots on single documents.
- [ ] Cross-collection invariants are enforced via transactions or suitable workflows.

**Evidence:** 3–5 concrete business request traces mapped to collections—not merely an ERD copied verbatim from SQL.

## 7. Embed or Reference?

| Question | If "Yes" | Recommendation |
| --- | --- | --- |
| Are children always read with the parent? | Yes | Consider embedding |
| Does child count grow without bound? | Yes | Consider a separate collection |
| Do children have an independent owner/lifecycle? | Yes | Usually reference |
| Must parent and child update atomically? | Yes | Embed if size and cardinality permit |
| Do many documents share the same entity? | Yes | Reference or snapshot per business rules |
| Are complex cross-collection joins/reports needed? | Yes | Evaluate `$lookup`, denormalization, and cost |

For instance, appending event history into `events:[]` inside an account document grows endlessly unless capped. Storing events in a dedicated collection keyed by `accountId` and timestamp is usually better.

Checklist:

- [ ] No "unbounded" arrays exist inside hot documents.
- [ ] Sensitive PII is not duplicated unnecessarily across many documents.
- [ ] Any denormalized fields have explicit sync mechanisms and staleness tolerances.
- [ ] Document sizes are tested against projected future volume, not tiny demo data.

## 8. Check Document Size, Cardinality, and Growth Rate

MongoDB imposes a **16 MiB** BSON document limit for standard documents. Design must factor in real growth rates, array element counts, and nested objects.

Forecasting example:

```text
One user generates 2 events per minute
~2 x 60 x 24 x 365 = 1,051,200 events/year
```

Never embed full event histories inside a user document. Beyond hitting size limits, every update on a huge document increases contention and I/O overhead.

Checklist:

- [ ] Maximum and percentile document sizes are tracked per collection.
- [ ] Arrays capable of unbounded growth are identified.
- [ ] High-cardinality fields and value distributions are understood.
- [ ] Bucketing, archiving, or referencing strategies exist for histories.
- [ ] Growth is forecasted per tenant, user, and transaction volume.
- [ ] No single hot document acts as a global counter/event sink for the whole system.

**Do not look at averages alone:** a handful of huge tenants or devices will hit limits long before the average moves.

## 9. BSON Data Types and IDs

Checklist:

- [ ] `_id` uses a consistent type: `ObjectId`, `String`, or an appropriate UUID Binary subtype.
- [ ] Java POJOs/codecs do not mix `ObjectId` and hex `String` for the same concept.
- [ ] UUIDs use a uniform representation across all writers (e.g., `STANDARD` when policy mandates).
- [ ] Monetary values use `Decimal128`/`BigDecimal` with defined precision/scale, never arbitrary `Double`.
- [ ] Timestamps are stored consistently as BSON Date/UTC.
- [ ] Application code clearly handles `Instant`, `LocalDate`, `LocalDateTime`, and timezone conversions.
- [ ] External IDs are normalized in type and format on ingestion.
- [ ] Enumerations have contracts for unknown values and schema evolution.
- [ ] Everything is not stored as `String` merely to simplify JSON serialization.

For example, these two queries **are not always equivalent**:

```javascript
db.orders.findOne({ _id: ObjectId("65f000000000000000000001") });
db.orders.findOne({ _id: "65f000000000000000000001" });
```

BSON `ObjectId` and BSON `String` are distinct types. During migrations, test both legacy and new code paths.

## 10. Null, Missing Fields, and Defaults

MongoDB distinguishes these states:

```javascript
{ _id: 1, email: null }
{ _id: 2 }
{ _id: 3, email: "" }
```

Query:

```javascript
db.customers.find({ email: null });
```

matches both **explicit `null`** and **missing fields**. Non-partial single-field unique indexes have specific `null`/missing semantics that must be understood before storing optional fields.

Checklist:

- [ ] Clear semantics exist for missing fields, explicit `null`, empty strings, and empty arrays.
- [ ] Patch DTOs define whether an omitted field means "unchanged" or "remove."
- [ ] Unique optional fields use proper index strategies (partial/sparse as needed).
- [ ] BSON type comparison rules are covered by tests.
- [ ] Java field defaults are not assumed to auto-backfill existing DB records.

Diagnostic queries:

```javascript
// Field does not exist:
db.customers.find({ email: { $exists: false } }).limit(20);

// Field has BSON Null:
db.customers.find({ email: { $type: 10 } }).limit(20);
```

## 11. Schema Validation and Change Management

MongoDB offers schema flexibility, **yet that does not mean every document in a collection should have an arbitrary shape**.

Checklist:

- [ ] Required/optional fields, BSON types, and validation rules are documented.
- [ ] Collection validators (`$jsonSchema`) or equivalent app-level validations are in place where appropriate.
- [ ] API input validation runs before writes to return clear client errors.
- [ ] Validators are tested against positive and negative fixtures.
- [ ] When adding new fields, older readers handle missing fields safely.
- [ ] Schema versioning or migration strategies exist for legacy documents when needed.
- [ ] New indexes are built over clean data rather than assuming annotations auto-deploy.
- [ ] Long-running migrations have rollback or forward-fix plans.
- [ ] Shared field types across services never change without a compatibility window.

Conceptual validator example:

```javascript
db.createCollection("reviews", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "rating"],
      properties: {
        tenantId: { bsonType: "string" },
        rating: {
          bsonType: "int",
          minimum: 1,
          maximum: 5
        }
      }
    }
  }
});
```

Run collection creation only in a **lab** or approved migration. Validators never replace tenant authorization.

## 12. Safe Schema Evolution Patterns

Field migrations should typically follow **expand → migrate → contract**:

```text
Release A: Readers understand both oldField and newField
          Writers gradually switch to newField
              |
              v
Migration: Backfill / dual-read / verify
              |
              v
Release B: Stop depending on oldField
              |
              v
Cleanup: Drop oldField once backups and preconditions hold
```

Checklist:

- [ ] Old and new client versions can coexist safely during rolling deploys.
- [ ] Migrations are idempotent or maintain checkpoints/resume markers.
- [ ] Batch sizes are bounded, rate-limited, and throttled against oplog/secondary lag.
- [ ] Before/after metrics track matched, modified, missing, and mistyped counts.
- [ ] Scripts updating millions of documents always have dry-run modes and observability.
- [ ] Fallback plans exist if a unique index build fails on duplicate keys.

**Risk:** converting `amount` from `String` to `Decimal128` while an older Java batch job still writes `String` leaves mixed types, breaking sorting, indexing, and filters unpredictably.

## 13. Time-Based Data, TTL, and Retention

Checklist:

- [ ] Data is classified: transactions, audits, logs, sensor metrics, sessions, tokens, backups.
- [ ] Retention policies and legal holds exist for each class.
- [ ] TTL indexes are applied only where appropriate; expiration is never treated as instantaneous.
- [ ] Time-series collections configure `timeField`, `metaField`, and `granularity` appropriately for measurements.
- [ ] TTL never substitutes for business cancellation workflows or authorization.
- [ ] Archiving, rollups, or downsampling strategies exist for large historical datasets.
- [ ] Secondary/oplog impact is assessed before bulk deletions.
- [ ] Deleted records remain understood to persist inside backups/snapshots during retention windows.

TTL index example:

```javascript
db.temporary_sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_expires_at" }
);
```

Create TTL indexes only when policy accepts BSON Date expiration and asynchronous TTL monitoring. Check collection options and index restrictions per server version.

## 14. Shard Keys and Scalability

Applicable only if the cluster uses or plans to use sharding.

Checklist:

- [ ] Shard key aligns with query routing and write distribution.
- [ ] Key distribution avoids hotspots (such as one dominant tenant).
- [ ] Shard key cardinality, monotonicity, and value frequency are analyzed.
- [ ] Critical queries include the shard key for targeted routing where needed.
- [ ] Unique indexes obey sharded-collection rules in the target server version.
- [ ] Chunk distribution, balancer/migration costs, and shard capacity are forecasted.
- [ ] Plans exist for unavoidable scatter-gather queries.
- [ ] Cross-shard transactions and aggregations are evaluated for latency.

**Never pick a shard key solely because a field appears often in filters**; evaluate load spread, immutability, index constraints, and routing needs.

## 15. Workload Inventory and Query Patterns

Every critical collection should maintain a table:

| Query ID | Query | Frequency | SLO | Target Index |
| --- | --- | --- | --- | --- |
| Q1 | Get order by tenant + ID | High | Low p95 | `_id_` + tenant check |
| Q2 | List tenant orders by `createdAt` desc | High | Low p95 | `{tenantId:1,createdAt:-1}` |
| Q3 | Orders by status/time window | Medium | Per report | Filter/sort compound index |
| Q4 | Conditional inventory update by SKU + available | High | Conditional write | Unique `_id` |
| Q5 | Monthly revenue aggregation | Batch | Bounded | Pipeline/rollup evaluated separately |

Checklist:

- [ ] Top queries are ranked by **cumulative execution time** and **p95/p99**, not call count alone.
- [ ] Query shapes, filters, sorts, projections, limits, and batch sizes are captured.
- [ ] Cardinality and selectivity stats are measured on representative data.
- [ ] Spikes on large tenants are accounted for in queries and aggregations.
- [ ] Peak traffic and background jobs are modeled together.
- [ ] Connection pool behavior and retry amplification are understood.

**Evidence:** sanitized logs, database profiler, Atlas Query Profiler, or approved APM traces—never turn on verbose production profiling blindly by reflex.

## 16. Index Review: Fewer, Better Indexes

Indexes accelerate qualifying reads at real cost:

- RAM / index cache footprint.
- Disk storage and backup volume.
- Write maintenance across inserts, updates, and deletes.
- Build/rebuild and migration overhead.

Checklist:

- [ ] Every index maps to a specific query shape or unique/TTL constraint.
- [ ] Compound index key order aligns with equality, sort, and range predicates.
- [ ] Collation is checked for string comparisons and case-insensitive searches.
- [ ] Partial, sparse, unique, and multikey semantics are verified.
- [ ] Redundant or duplicate indexes are avoided.
- [ ] Production indexes are never dropped solely because they looked unused over a short window.
- [ ] Index sizes and growth rates are tracked.
- [ ] Index changes follow build, rollout, permission, load, and rollback plans.

Example:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created_desc" }
);
```

This is a candidate index only. Validate effectiveness against live workloads and `explain` rather than applying a rigid formula to every query.

## 17. Equality, Sort, Range, and Compound Index Order

A practical rule of thumb known as **ESR** (Equality → Sort → Range) guides field order in compound indexes, though it is not an unbreakable law for every query.

Query example:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(50);
```

Candidate index:

```javascript
{ tenantId: 1, status: 1, createdAt: -1 }
```

Checklist:

- [ ] Equality predicates narrow scans effectively.
- [ ] Sorts are index-supported without triggering blocking `SORT` stages.
- [ ] Range predicates and field order are verified with `explain`.
- [ ] One giant compound index is not abused to "cover every API."
- [ ] Index prefix reuse across other query shapes is evaluated.
- [ ] Queries using `$in`, regex, collation, and multikey paths are tested separately.

**Look beyond index counts:** what matters is which index wins, how many keys/docs are examined, and the write cost of maintaining them.

## 18. Unique Indexes: Commonly Overlooked Pitfalls

Checklist:

- [ ] Every business unique key is backed by an actual unique index, not just an app-level check.
- [ ] In multi-tenant setups, index keys include `tenantId` when uniqueness is per-tenant.
- [ ] Optional fields define explicit policies for `null` and missing values.
- [ ] `E11000` handlers inspect **which index failed** rather than catching everything as success.
- [ ] `upsert` filters match the business unique key, avoiding extra `status`/`version` predicates that cause no-match duplicate inserts.
- [ ] Same idempotency key with a different payload is rejected as a conflict.
- [ ] Collation or case normalization does not create unexpected duplicate collisions.
- [ ] Concurrent inserts and upserts are tested.

Specifically:

```javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uk_tenant_request" }
);
```

A unique index blocks creating two orders with the same key, yet **does not stop double payments or duplicate emails** if retries occur outside a transaction or outbox.

## 19. Multikey Arrays, Array Queries, and Indexing

Checklist:

- [ ] Array-of-documents queries use `$elemMatch` whenever multiple predicates must match the same element.
- [ ] Developers understand when plain dot notation matches **different elements** in the array.
- [ ] Compound multikey restrictions are verified.
- [ ] Unique multikey indexes are not assumed to forbid duplicates **within a single document's array**.
- [ ] Large arrays do not bloat documents or updates.
- [ ] Projections or limits prevent returning oversized arrays unnecessarily.

Example:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 2 }
    }
  }
});
```

Using `"items.sku": "SKU-A"` and `"items.quantity": { $gte: 2 }` separately allows matching across **two distinct elements**. That is a correctness bug, not merely a performance issue.

## 20. Execution Plans: Reading `explain` Properly

Inspection command in lab/staging:

```javascript
db.orders.find({
  tenantId: "tenant-a",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20)
  .explain("executionStats");
```

Key fields to inspect:

- `winningPlan` and stage tree for your server engine/version.
- `IXSCAN` vs `COLLSCAN` and actual index key pattern.
- `totalKeysExamined` and `totalDocsExamined`.
- `nReturned`.
- Whether any blocking sort stage appears.
- Execution time estimates and pipeline stage details.
- Whether the query runs scatter-gather on a sharded cluster.

Checklist:

- [ ] `explain` runs against **representative data distributions and sizes**.
- [ ] Indexes, filters, and sorts match production shapes.
- [ ] Fast `explain` results on 20-document test collections are never treated as SLO proof.
- [ ] `docsExamined/nReturned` and `keysExamined/nReturned` ratios are reviewed.
- [ ] Observed latency accounts for warm vs cold cache and concurrency.
- [ ] Not every `COLLSCAN` is treated as a bug: tiny collections or intentional full scans may be valid.

**Note:** `explain` has specific execution semantics, and `executionStats` executes the query and can scan substantial data. Avoid running heavy `explain("executionStats")` on a primary during an incident.

## 21. Projections, Covered Queries, and Data Minimization

Example API needing only summary fields:

```javascript
db.orders.find(
  { tenantId: "tenant-a", status: "PAID" },
  { _id: 1, status: 1, total: 1, createdAt: 1 }
).limit(50);
```

Checklist:

- [ ] APIs do not fetch full documents when only a few fields are needed.
- [ ] Projections never expose PII, passwords, tokens, or internal fields.
- [ ] Network payload sizes and serialization costs are checked.
- [ ] Covered queries are evaluated with their constraints rather than treated as mandatory goals.
- [ ] Exclusion blacklists are not relied on as the sole security control when schemas add new sensitive fields.
- [ ] API DTO allowlists follow explicit schemas and contracts.

**Projection does not replace authorization.** Returning just one field of another tenant's document is still a data leak.

## 22. Aggregation: Memory Limits and Data Scoping

Checklist:

- [ ] `$match` appears as early as semantics allow to leverage indexes.
- [ ] `$project`/`$unset` trims unnecessary fields early.
- [ ] `$group` cardinality is bounded; millions of keys are not grouped without resource budgets.
- [ ] `$lookup` uses indexed foreign keys and enforces tenant boundaries.
- [ ] `$sort`, `$facet`, and `$unwind` are measured for output expansion.
- [ ] `allowDiskUse` is not enabled blindly where disk/IOPS are constrained.
- [ ] Reporting endpoints enforce limits, timeouts, and quotas.
- [ ] Pre-aggregation or rollups are considered instead of scanning raw history on every request.
- [ ] Pipelines never leak cross-tenant data across `$lookup` or `$unionWith`.

Example:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      status: "PAID",
      createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
    }
  },
  {
    $group: {
      _id: "$currency",
      total: { $sum: "$total" },
      orderCount: { $sum: 1 }
    }
  }
]);
```

Never sum amounts across different currencies into one total without explicit exchange-rate conversion rules.

## 23. Pagination, Sorting, and Cursor Lifecycle

Checklist:

- [ ] Sorting includes a **unique tiebreaker** (typically `_id`) for deterministic pagination.
- [ ] Deep `skip` pagination cost is evaluated; keyset/range pagination is used for large feeds where appropriate.
- [ ] Cursor batch sizes and timeouts suit the workload.
- [ ] Java queries never accidentally materialize entire collections into a `List`.
- [ ] Client-supplied page sizes are capped.
- [ ] Multi-tenant scope and authorization hold across every page.

Keyset example sorting newest first:

```javascript
// Candidate index:
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 }
);

db.orders.find({
  tenantId: "tenant-a",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
}).sort({ createdAt: -1, _id: -1 }).limit(50);
```

`lastCreatedAt` and `lastId` are **application variables** that must be encoded/decoded safely and paired with the authenticated tenant; this snippet is not standalone without defining them.

## 24. Write Patterns, Contention, and Idempotency

Checklist:

- [ ] No unguarded read–modify–write without version/CAS on contended data.
- [ ] Counters and stock use atomic `$inc` plus business predicates where appropriate.
- [ ] Retries with the same key and payload do not duplicate business effects.
- [ ] Unique idempotency keys and replay response contracts exist.
- [ ] MongoDB transactions are reserved for multi-document commit invariants.
- [ ] Transactions remain brief and never call payment/email APIs inside retryable callbacks.
- [ ] `WriteConflict`, `TransientTransactionError`, and unknown commit outcomes are handled per driver guidance.
- [ ] Timeouts are never assumed to mean guaranteed write failure.
- [ ] Bounded retries, backoff/jitter, and rate limits are configured.
- [ ] Concurrency tests run 2–100 parallel writes on hot keys, not just unit tests.

Conditional decrement example:

```javascript
db.inventory.updateOne(
  { _id: "SKU-A", available: { $gte: 2 } },
  { $inc: { available: -2 } }
);
```

This is atomic **within a single document**, not atomic with inserting an order in another collection. If order creation and inventory deduction must commit together, use a transaction or a well-defined compensating workflow.

## 25. Correctness Verification by Business Invariant

Critical workflows should define **concrete invariants**:

| Workflow | Invariant |
| --- | --- |
| Inventory | `available >= 0` |
| Order creation | At most one order per `(tenantId, requestId)` |
| Stock reservation | `available + active reserved` reconciles with stock movements |
| Wallet / ledger | Double-entry ledger entries balance |
| User profile | Updates never overwrite a newer version |
| Booking | No two incompatible reservations overlap on the same unit/time slot |
| Event consumer | Duplicate event IDs never trigger duplicate side effects |

Checklist:

- [ ] Invariants are codified as assertions, automated tests, or reconciliation jobs.
- [ ] Verification goes beyond checking HTTP 200 or "MongoDB command succeeded."
- [ ] Mid-flight transaction abort and fault-injection tests exist.
- [ ] Procedures exist to repair data drift after outages.
- [ ] Business owners approve remediation steps—records are never deleted ad hoc.

## 26. Replica Sets, Write Concern, and Read Preference

Checklist:

- [ ] Replica set members, votes, failure domains, and majority conditions are documented.
- [ ] Primary and secondary replication health are monitored.
- [ ] Critical write concerns match RPO—never defaulting to `w:0`.
- [ ] Read preference policies are explicit per endpoint.
- [ ] Endpoints reading from secondaries tolerate replication lag per business rules.
- [ ] Read concerns match consistency requirements (`local`/`majority`/`snapshot`/`linearizable` as appropriate).
- [ ] Plans exist for elections, stepdowns, and primary unavailability.
- [ ] Secondary read preferences never break idempotency checks by missing a newly created order.

**Separate two questions:** "Did the write obtain majority acknowledgment?" and "Which version does a read observe?" A secondary read can still return stale data immediately after a successful write on the primary.

## 27. Verifying Transaction Boundaries

In the Java Sync Driver:

```java
try (ClientSession session = mongoClient.startSession()) {
    session.withTransaction(() -> {
        orders.insertOne(session, newOrder);
        inventory.updateOne(
            session,
            stockFilter,
            stockUpdate
        );
        return null;
    }, transactionOptions);
}
```

Illustrative snippet: `mongoClient`, `orders`, `inventory`, `newOrder`, `stockFilter`, `stockUpdate`, and `transactionOptions` are provided by the service. Keep non-idempotent external side effects out of the callback.

Checklist:

- [ ] All MongoDB operations requiring atomicity participate in the same session/transaction.
- [ ] Each concurrent transaction owns its own `ClientSession`.
- [ ] Developers know explicitly which operations sit **outside** the transaction.
- [ ] Spring `@Transactional` pairs correctly with `MongoTransactionManager` and proxy boundaries.
- [ ] Timeouts and retry budgets are enforced; transactions never wait on user forms.
- [ ] Business errors trigger proper aborts rather than being swallowed into partial commits.
- [ ] Tests run against transaction-capable replica sets or sharded clusters, not standalone mocks alone.

## 28. Change Streams, Oplog, and Consumers

If using Change Streams / CDC:

- [ ] Resume tokens persist durably across restarts.
- [ ] Consumers handle at-least-once delivery with idempotency.
- [ ] Alerts monitor consumer lag relative to the oplog window.
- [ ] Playbooks exist when resume tokens age out of oplog history (re-bootstrap/snapshot/reconcile).
- [ ] `fullDocument` lookups, pre-/post-images, and retention are configured intentionally.
- [ ] Sensitive documents are not dumped into unprotected stream logs.
- [ ] Replica set failovers and consumer restarts are tested.
- [ ] Oplog size is never shrunk to save disk without checking CDC and replication needs.

**Never check only whether the consumer is "Connected."** It may be connected while falling behind the event rate or missing expired history.

## 29. Authentication and Database RBAC

Checklist:

- [ ] Production never exposes unauthenticated database access.
- [ ] Each service/application uses its own distinct identity where feasible.
- [ ] Services receive least privilege: read/write on specific databases/collections, never root.
- [ ] Bootstrap/migration accounts are separated from runtime service accounts.
- [ ] Read-only accounts cannot insert, update, or drop; writers cannot administer users/roles.
- [ ] Processes exist to provision, revoke, and rotate credentials.
- [ ] Positive/negative auth and `authSource` tests run against an auth-enabled test instance.
- [ ] Database RBAC is never confused with HTTP user/tenant authorization.
- [ ] Role changes undergo review and auditing.

When scoping roles to individual collections, inspect **exact custom privilege definitions**, because built-in database-level `readWrite` grants access across all collections in that database.

### Evidence

A negative security test passes only when the operation fails specifically with **Unauthorized**—not because TLS or network connectivity broke. Establish a positive connection baseline first and assert zero unauthorized mutations.

## 30. Network Isolation and TLS

Checklist:

- [ ] MongoDB is reachable only from approved networks and services.
- [ ] Firewalls, Atlas IP Access Lists, Private Endpoints, and VPC peering are reviewed.
- [ ] `0.0.0.0/0` is never opened casually to troubleshoot connectivity.
- [ ] TLS is mandatory with certificate chain and hostname verification enabled.
- [ ] `tlsInsecure=true` and disabled hostname verification are forbidden in production.
- [ ] Certificate rotation has an owner and expiration alerts.
- [ ] Backup, monitoring, and admin clients also connect over encrypted channels.
- [ ] With Private Endpoints, live DNS resolution and routing are verified—not just endpoint creation.
- [ ] Runbooks clearly distinguish DNS, TLS, AuthN, and RBAC errors.

A MongoDB URI with `tls=true` that disables certificate validation does not provide the protection of properly verified TLS.

## 31. Multi-Tenant and Object-Level Authorization

A MongoDB service account may hold privileges to read every document in `orders`, yet the API must restrict queries by principal:

```javascript
db.orders.findOne({
  _id: "ORD-001",
  tenantId: "tenant-a"
});
```

Checklist:

- [ ] Tenant/owner scope derives from the authenticated principal or verified delegation.
- [ ] Client-supplied `tenantId` parameters are never trusted blindly.
- [ ] GET by ID, list, search, aggregation, export, and attachment endpoints all enforce scope.
- [ ] PATCH/DELETE include the tenant/owner predicate **directly inside the write filter** where applicable.
- [ ] Negative tests verify cross-tenant isolation.
- [ ] Cache keys and cached query results never leak across tenants.
- [ ] Cross-tenant admin access follows explicit policy and auditing.
- [ ] Detailed error messages or statuses do not leak whether an unauthorized resource exists.

**Projection never replaces authorization**; exposing even a single field from another tenant's document is a breach.

## 32. Injection and Input Validation

Checklist:

- [ ] APIs validate types and schemas, never accepting raw MongoDB query objects from clients except tightly controlled admin endpoints.
- [ ] Java code builds typed filters/criteria rather than concatenating arbitrary JSON into operators.
- [ ] Request JSON containing `$ne`/`$where` cannot be interpreted as query operators when a plain `String` was expected.
- [ ] Client-supplied sort and filter fields pass an allowlist.
- [ ] Page sizes, regex complexity, batch sizes, and query timeouts are capped.
- [ ] BSON types and value ranges are validated.
- [ ] Import and ETL pipelines do not bypass tenant or business validations inadvertently.

Java Sync Driver example:

```java
collection.find(
    Filters.and(
        Filters.eq("tenantId", principalTenantId),
        Filters.eq("email", requestEmailString)
    )
);
```

`requestEmailString` must be validated as a `String`; variables represent validated application inputs set elsewhere. Never build filters straight from an untrusted `Map<String, Object>` capable of smuggling MongoDB operators.

## 33. Secrets, Encryption, and PII

Checklist:

- [ ] MongoDB URIs and passwords never appear in Git, test reports, or error responses.
- [ ] Secrets live in a secret manager with rotation and revocation workflows.
- [ ] Private keys and TLS certificates enforce strict file/KMS permissions.
- [ ] TLS in transit is verified.
- [ ] Encryption at rest is verified via storage/platform configuration, including backups.
- [ ] Fields needing extra protection are evaluated for CSFLE, Queryable Encryption, or equivalents per feature support.
- [ ] Remembering that authorized reads see plaintext—this does not mean at-rest encryption is broken.
- [ ] PII in logs, query profilers, traces, exports, and audit events is masked or minimized.
- [ ] Public APIs return DTO allowlists instead of serializing raw persistence entities.
- [ ] Data classification and retention policies exist.

Distinguish clearly: **base64 is encoding, hashing is not reversible encryption, TLS does not protect data at rest on disk, and encryption at rest does not restrict users holding DB read roles**.

## 34. Auditing and Data Access Controls

Checklist:

- [ ] Sensitive reads, exports, role changes, and deletes leave audit trails per policy.
- [ ] Application audit logs capture HTTP actor, tenant, and correlation IDs where needed.
- [ ] MongoDB/Atlas audit logging is marked PASS only if genuinely enabled and supported by the tier.
- [ ] Audit logs enforce separate access controls and retention.
- [ ] Plaintext secrets and full PII are excluded unless strictly justified.
- [ ] Alerts fire on privilege escalation and anomalous access patterns.
- [ ] Incident diagnostics work without flipping on full raw request logging.

Because multiple HTTP users share one MongoDB service account, database audit logs often see only the service identity. Application audit logs supply the end-user actor and business context; both layers complement each other.

## 35. Backup Inventory: What Exists, Where, and Who Owns It?

Checklist:

- [ ] Backup mechanism is known: managed snapshot, filesystem snapshot, `mongodump`, or equivalent.
- [ ] Schedules, retention, encryption, and storage isolation are defined.
- [ ] Operational owners and authorized restore operators are designated.
- [ ] Backups reside in failure domains/regions aligned with RPO/RTO.
- [ ] Alerts monitor failed, missed, or slow backup jobs.
- [ ] Databases/collections covered by backups (and any exclusions) are listed.
- [ ] Capacity plans handle faster-than-expected backup growth.
- [ ] Dump archives are never written onto an already tight `dbPath` volume.
- [ ] KMS keys required to decrypt backups during restores are inventoried.

**"Nightly backups" are not enough**: you must verify the latest backup **actually succeeded, is consistent, remains readable, and passed a restore test**.

## 36. Backup Consistency

Different backup mechanisms carry different consistency semantics. Copying raw files of a live, actively written database can produce an **inconsistent** state relative to journals and checkpoints. On replica sets and sharded clusters, multi-node and point-in-time backups must be evaluated for consistent recovery points.

Checklist:

- [ ] Backup method is officially supported by MongoDB/platform for the topology.
- [ ] Plain `cp -r dbPath` on a live `mongod` is never treated as a consistent backup method.
- [ ] Snapshots use vendor-supported coordination/consistency guarantees.
- [ ] Oplog/PITR is enabled if RPO requires restoring finer than full backup intervals.
- [ ] Backup encryption keys and metadata share aligned lifecycles.
- [ ] Archive integrity, downloadability, and restorability are verified.
- [ ] Evidence confirms backups actually include all critical collections.

`mongodump` suits certain workloads, yet by default it does not provide PITR or a globally consistent snapshot across **all shards** under arbitrary writes. Verify documentation for your exact deployment and version.

## 37. RPO and RTO: Measure Against Real Recovery Operations

Example:

```text
Critical ordering API:
  RPO = a few seconds per business approval
  RTO = 30 minutes

Daily-only backup:
  Last backup = last night
  Potential restore point = hours behind current time
```

If RPO requires seconds yet only nightly backups exist, **never mark PASS** without adding suitable replication, PITR, or DR strategies.

Checklist:

- [ ] RPO and RTO targets are signed off by business owners.
- [ ] Backup interval plus PITR window satisfies RPO.
- [ ] Infrastructure provisioning, data download, and oplog replay fit within RTO.
- [ ] Restore tests run at realistic production-scale data volumes.
- [ ] Application cutover and post-restore consistency checks are planned.
- [ ] Criteria exist for selecting a clean restore point after corruption, ransomware, or buggy migrations.
- [ ] Procedures stop upstream writers from corrupting data during restores.

**Replication does not replace backups:** accidental deletes or bad updates replicate to secondaries immediately. Backups/PITR restore pre-incident states within retention bounds.

## 38. Restore Drills Are the Ultimate Evidence

A proper drill should cover:

1. Selecting an actual backup produced by the production-like pipeline.
2. Provisioning an **isolated** restore environment with sufficient capacity, networking, and RBAC.
3. Decrypting and downloading the backup using an authorized identity.
4. Restoring via the documented procedure matching the backup type.
5. Verifying restored databases, collections, indexes, users/roles, and expected config boundaries.
6. Running read/write functional checks on the restored environment where appropriate.
7. Reconciling record counts, checksums/sample invariants, and logs.
8. Measuring **actual elapsed duration** against RTO.
9. Recording the achievable RPO recovery point.
10. Cleaning up sensitive data and temporary permissions per policy.

Checklist:

- [ ] Latest drill date and detailed results are recorded.
- [ ] Evidence demonstrates real restore success—not just "backup job succeeded."
- [ ] Missing or rotated KMS keys and restore permissions are tested as planned.
- [ ] Restore runbooks do not rely on tribal knowledge held by one person.
- [ ] Approvals are required before restoring over production.
- [ ] Reconciliation covers uncertain transaction outcomes post-cutover.

If a restored environment contains production data, protect it **at the exact same sensitivity tier**—never grant broad developer access just because the environment is named staging.

## 39. Cross-Region Backups and Disaster Recovery

Checklist:

- [ ] Failure domains are mapped: host, AZ, region, cloud account, KMS, operator.
- [ ] Backups do not depend exclusively on the same region/account that could lose access.
- [ ] Multi-region DR accounts for data residency and cost.
- [ ] DNS, connection string, and network cutover plans exist.
- [ ] Failback plans exist once the primary site recovers.
- [ ] Cross-region restore/failover is tested in an authorized environment.
- [ ] Policies prevent split-brain or two uncoordinated writer sets.
- [ ] Regional RTO/RPO claims are never advertised until failover/restore times are measured.

A backup stored in another region remains **unrecoverable within RTO** if application secrets or KMS keys only exist in the failed region.

## 40. Monitoring: Four Metric Groups

A solid dashboard separates:

| Group | Metrics | Issues Surfaced |
| --- | --- | --- |
| **User / SLO** | p95/p99 API latency, error rates, successful writes | Real user experience |
| **MongoDB** | Query latency, ops/s, active connections, locks/cache, replication lag | Database bottlenecks |
| **Infrastructure** | CPU, RAM/cgroup OOMs, disk bytes/inodes, IOPS/latency | Resource limits |
| **Recovery** | Backup freshness, restore drills, oplog window, alerts | Recovery readiness |

Checklist:

- [ ] Baselines exist for normal and peak hours.
- [ ] Dashboards track critical endpoints, not just average CPU/disk.
- [ ] Metrics and alerts map to owners and on-call escalation paths.
- [ ] Correlation IDs link application failures to DB and network events.
- [ ] Metric retention spans long enough to spot growth trends.
- [ ] Credentials and PII never leak into metric labels.
- [ ] Alerts fire when backups fail or no valid recent backup exists.

## 41. Storage Capacity and I/O Performance

Checklist:

- [ ] Actual `dbPath`, mount, PVC, or Atlas tier bytes free are tracked.
- [ ] **Inodes, quotas, and read-only remounts** are monitored where applicable.
- [ ] **Time-to-full** forecasts track growth rate rather than waiting on a static 90% threshold.
- [ ] IOPS, throughput, and latency headroom cover peaks, backups, and initial syncs.
- [ ] Storage auto-scaling caps, triggers, and lag are understood.
- [ ] Backups, archives, and logs do not silently share and starve data volumes.
- [ ] Index growth and oplog/CDC retention are budgeted.
- [ ] Safe volume/PVC resize runbooks exist.

Simple forecast:

```text
Time-to-full ≈ available GiB / net growth GiB per hour
```

Use only when net growth is positive and relatively steady. Index builds, bulk imports, TTL backlogs, and storage auto-scaling can alter trajectories abruptly.

**Never delete WiredTiger data files, journals, or oplogs to free disk space.** Logical document deletes do not always shrink OS disk usage immediately due to storage reuse.

## 42. Memory, WiredTiger, and Query Pressure

Checklist:

- [ ] Host RAM is distinguished from container cgroup memory limits.
- [ ] Process RSS, OS `MemAvailable`, swap, and OOM events are monitored.
- [ ] WiredTiger cache size fits the server version and actual memory limit.
- [ ] Cache eviction, dirty pages, and read-ticket pressure metrics are tracked.
- [ ] Sorts, groups, and aggregations avoid unbounded memory usage.
- [ ] Java clients never load millions of documents into unbounded `List`s.
- [ ] Connection pools and cursor lifecycles are managed cleanly.
- [ ] WiredTiger cache is never raised when the root cause is a cgroup OOM.
- [ ] Disk spill is not enabled blindly when volumes already lack IOPS or space.

**Remember:** WiredTiger cache is not the total RSS of `mongod`. Low Linux "free" RAM does not necessarily indicate memory exhaustion when OS page cache is reclaimable.

## 43. Replica Health and Failover Readiness

Checklist:

- [ ] Enough healthy voting members exist to preserve majority.
- [ ] Replication lag is tracked per member.
- [ ] Oplog window covers lag, maintenance, and CDC requirements.
- [ ] Failover and driver reconnection are tested in staging.
- [ ] Rolling restarts preserve quorum under the topology.
- [ ] Potential rollback behavior is understood for every write concern contract.
- [ ] Playbooks handle full-disk members, OOMs, or initial sync needs.
- [ ] When all members are nearly full, failover is never treated as a capacity fix.
- [ ] Applications avoid tight retry loops without backoff during elections.

A single healthy `rs.status()` snapshot **never substitutes** for continuous monitoring of lag, heartbeats, and elections over time.

## 44. Logs, Slow Operations, and Incident Signals

Checklist:

- [ ] Log rotation and retention cannot fill data volumes.
- [ ] Slow-query diagnostics use appropriate thresholds and overhead budgets.
- [ ] Raw connection URIs containing passwords are never logged.
- [ ] Alerts track `E11000` spikes, `WriteConflict`, and timeouts per business criticality.
- [ ] Logs distinguish authentication failures, authorization failures, and network/TLS failures.
- [ ] Backup jobs, index builds, migrations, and TTL backlogs are visible.
- [ ] Incident evidence follows retention policies with sensitive payloads redacted.

Safe log sample:

```json
{
  "event": "MONGO_OPERATION_FAILURE",
  "operation": "update_inventory",
  "errorCategory": "TRANSIENT_TRANSACTION",
  "correlationId": "req-demo-001",
  "collection": "inventory",
  "durationMs": 250,
  "sensitivePayload": "REDACTED"
}
```

Illustrative schema only; you do not need to dump full documents to diagnose an active incident.

## 45. Maintenance, Index Builds, and Upgrades

Checklist:

- [ ] Supported MongoDB, driver, and Spring Data version policies exist.
- [ ] Matching staging environments exist for upgrade testing.
- [ ] Backups and rollback/failback plans precede schema or config changes.
- [ ] Wire protocol, feature compatibility, and driver API impacts are reviewed.
- [ ] Feature Compatibility Version (FCV) is never bumped without understanding downgrade restrictions.
- [ ] Rolling upgrades follow the exact replica set / sharded cluster guide for the version.
- [ ] Schema and index migrations include load budgets and peer review.
- [ ] Post-upgrade validation benchmarks performance—not just a health ping.
- [ ] Transactions, change streams, and encryption are re-tested if used.
- [ ] Maintenance windows, owners, communications, and abort criteria are defined.

Before building a new unique index, verify legacy data **contains zero duplicates**; index builds do not automatically pick records to delete.

## 46. Java / Spring Data Integration Checklist

- [ ] MongoDB driver and Spring Data dependency versions are aligned consistently.
- [ ] Java entity mappings (`@Id`, `@Version`, `@Field`) and codecs for UUID/`Decimal128`/Date are accurate.
- [ ] `MongoClient` lifecycles share connection pools cleanly.
- [ ] Connection, server selection, and socket timeouts align with SLOs.
- [ ] Queries enforce tenant filters derived from the authenticated principal.
- [ ] DTOs stay separate from persistence entities.
- [ ] Handlers manage `DuplicateKeyException`, optimistic locking, transient errors, and unknown outcomes.
- [ ] Multi-document writes use sessions and transaction managers properly.
- [ ] Critical operations enforce bounded retries and idempotency keys.
- [ ] Cursors, streams, and aggregation outputs are bounded.
- [ ] Secrets are never hardcoded in `application.yml` or printed to logs.
- [ ] Integration tests run against real MongoDB with matching topologies and roles.

Common pitfall: `@Version` protects entity saves, yet if an HTTP API reloads the latest document right before saving without **checking the client-supplied `expectedVersion`**, it can still overwrite stale form edits.

## 47. *Read-Only* Lookup Commands in `mongosh`

Examples use placeholder database `appdb` and collection `orders`. Pick commands suited to your role; never run queries scanning hundreds of millions of documents on an overloaded production cluster.

```javascript
// Server/topology:
db.adminCommand({ hello: 1 });

// Metrics summary (with appropriate monitoring role):
const server = db.adminCommand({ serverStatus: 1 });
printjson(server.connections);
printjson(server.mem);
printjson(server.wiredTiger?.cache);

// Database stats:
const app = db.getSiblingDB("appdb");
printjson(app.stats());

// Indexes:
printjson(app.orders.getIndexes());

// Query plan on a representative, bounded query:
printjson(
  app.orders.find({
    tenantId: "tenant-demo",
    status: "PAID"
  }).sort({ createdAt: -1 })
    .limit(20)
    .explain("queryPlanner")
);
```

`queryPlanner` does not execute the full runtime scan like `executionStats`; use `executionStats` only when actual scan metrics are required and cost is vetted. Never judge production health from a single snapshot.

### Checking Replica Set State

```javascript
// Run on a replica set with appropriate privileges:
rs.status();
```

Do not apply `rs.status()` blindly to standalone nodes or `mongos`. On Atlas, prefer tier-appropriate dashboards and metrics provided by your role.

## 48. Java Verification Snippet for Indexes and Queries

Example intended for integration tests **on a lab database**:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class QueryReviewExample {

    public static void run(MongoClient client) {
        MongoDatabase database = client.getDatabase("appdb");
        MongoCollection<Document> orders =
            database.getCollection("orders");

        Document found = orders.find(
            Filters.and(
                Filters.eq("tenantId", "tenant-demo"),
                Filters.eq("status", "PAID")
            )
        ).projection(
            new Document("_id", 1)
                .append("status", 1)
                .append("createdAt", 1)
        ).limit(1).first();

        System.out.println(
            found == null ? "No matching fixture" : "Fixture found");
    }
}
```

Key points to observe:

- Filters always enforce tenant scope on multi-tenant data.
- Projections fetch only required fields.
- Limits prevent materializing large result sets.
- Whole documents and PII are never printed to logs.
- Integration tests use synthetic fixtures and verify both positive and negative cases.

This is not a benchmark. Evaluating index performance additionally requires `explain`, realistic load, latency metrics, and live index stats.

## 49. Incident Response Runbook: Least-Destructive Sequence

```text
Alert / SLO breach detected
          |
          v
Confirm scope + topology + business impact
          |
          v
Preserve evidence, protect data and quorum
          |
          v
Shed non-essential load / retry storms
          |
          v
Triage network / AuthN / RBAC / query / resource / storage
          |
          v
Choose least-destructive recovery: capacity / runbook
failover / roll back faulty change
          |
          v
Reconcile data + transaction outcomes + API SLOs
          |
          v
Incident closure + postmortem + preventive actions
```

Checklist:

- [ ] Incident commander, on-call rotation, and escalation contacts exist.
- [ ] Dedicated runbooks cover primary unavailability, replica lag, disk-full, OOM, and backup failures.
- [ ] Risky operational commands require preconditions and approvals.
- [ ] Never delete `journal/`, `WiredTiger*`, oplogs, or PVCs as a "quick fix" for full disks.
- [ ] Never restart all replica set members simultaneously.
- [ ] Never invoke `rs.reconfig(..., {force:true})` by reflex.
- [ ] Diagnostics distinguish permission, network, and data corruption errors.
- [ ] Post-recovery checks verify ACKed writes, unknown outcomes, and external side effects.

## 50. Symptom → First Investigation Lookup Table

| Symptom | Check First | Misconception to Avoid |
| --- | --- | --- |
| `E11000` duplicate key | Index name, `keyValue`, filter, upsert | Not every duplicate is safely idempotent |
| Rising query p99 | Query plan, indexes, cardinality, disk I/O | Do not just enlarge the connection pool |
| Memory / OOM | RSS, cgroup, WiredTiger, query spill, JVM heap | Do not just raise cache size |
| `ENOSPC` | `dbPath` mount, bytes, inodes, quotas, I/O | Never delete WiredTiger files |
| Secondary lag | Write rate, oplog window, disk/network | Never shrink oplog blindly |
| No primary | Majority, health, elections, network | Never run `force` reconfig arbitrarily |
| Authentication failed | TLS/network, credentials, `authSource` | Never grant root just to test |
| Unauthorized | Roles, privileges, collection scope | Do not confuse with bad password |
| Cross-tenant leak | Principal, filters, cache/exports/lookups | Projection alone is insufficient |
| Timeout after write | Driver labels, commit state, idempotency key | Never assume write did not happen |
| Backup succeeded yet restore fails | Archive integrity, KMS, procedure | Having a backup ≠ recoverable |
| Change stream cannot resume | Token persistence, oplog window | Never fabricate lost events |
| TTL data has not vanished yet | TTL monitor/index, date types | TTL is not instantaneous |
| Collection stays large after delete | WiredTiger space reuse / indexes | `deleteMany` does not shrink `df` immediately |
| Index build fails | Existing duplicates, RAM/disk/index limits | Never delete data arbitrarily |

## 51. Minimum Pre-Release Gate

### Modeling

- [ ] Business entities and aggregate boundaries are clear.
- [ ] Types, IDs, and unique keys are consistent with schema validation.
- [ ] No unbounded arrays or document growth exist.
- [ ] Retention, TTL, and archiving plans are clear.
- [ ] Migration and backward-compatibility plans exist.

### Queries

- [ ] Top queries have candidate indexes plus `explain` and metrics.
- [ ] Sorts, pagination, and aggregations are bounded.
- [ ] Hot queries do not trigger unintended `COLLSCAN`s.
- [ ] Performance tests run at representative data volumes.
- [ ] Transaction, idempotency, and concurrency invariants are tested.

### Security

- [ ] Authentication, RBAC, TLS, and network controls match scope.
- [ ] Cross-tenant and ownership negative tests pass.
- [ ] Secrets and PII never leak via APIs, logs, or exports.
- [ ] Auditing and key rotation have clear owners.

### Backups

- [ ] Latest backup is valid with failure alerts enabled.
- [ ] RPO/RTO targets are satisfied.
- [ ] Restore drill has current evidence within review interval.
- [ ] Backup encryption, ACLs, and retention are sound.

### Operations

- [ ] Capacity headroom, time-to-full, and load budgets are clear.
- [ ] Replica health, quorum, lag, and CDC are monitored.
- [ ] On-call, runbooks, rollback, and escalation paths exist.
- [ ] Server/driver compatibility and upgrade plans are verified.
- [ ] Critical SLOs and alerts are validated.

No release should ever proceed automatically while a Critical FAIL remains unresolved or unaccepted by proper authority. A critical `UNKNOWN` item such as "restore never tested" must be treated as an **evidence gap**, never a PASS.

## 52. Reusable Review Report Template

```markdown
# MongoDB Architecture & Operations Review

## Context
- Application:
- Environment:
- Cluster / MongoDB version:
- Driver / Spring Data version:
- Database(s):
- Business owner:
- Engineering owner:
- On-call / DBA:
- Review date:

## Requirements
- Critical operations / SLO:
- RPO / RTO:
- Data classification:
- Retention / residency:
- Peak workload / forecast:

## Findings
| ID | Pillar | Status | Risk | Evidence | Owner | Due |
|----|--------|--------|------|----------|-------|-----|
| M-01 | Model | UNKNOWN | High |  |  |  |
| Q-01 | Query | UNKNOWN | Medium |  |  |  |
| S-01 | Security | UNKNOWN | Critical |  |  |  |
| B-01 | Backup | UNKNOWN | Critical |  |  |  |
| O-01 | Operations | UNKNOWN | High |  |  |  |

## Decisions
- Must-fix before release:
- Accepted risks (with approver):
- Mitigations / feature flags:
- Rollback plan:
- Restore readiness:
- Follow-up date:
```

This is a review template; do not assume `UNKNOWN` rows represent any real system's state. Store evidence in appropriately restricted locations—especially query samples, diagrams, backups, and security configs.

## 53. Sample Review of an E-Commerce Application

**Hypothetical context:** a Java/Spring Boot API backed by a MongoDB replica set with collections `customers`, `orders`, `inventory`, and `payment_requests`.

### Modeling

Findings:

```text
orders.items embedded: reasonable
customers.purchaseHistory[] grows without bound: FAIL
payment_requests requestId has unique index: PASS
amount stored as Double: REVIEW/HIGH if monetary
```

Action: move purchase history to a dedicated collection indexed by user/time; migrate monetary fields to `Decimal128` via a controlled backfill.

### Queries

Findings:

```text
GET orders/{id} checks tenant: PASS
GET /orders?status=... sort createdAt: missing index: FAIL
Daily revenue aggregation scans entire history: evaluate rollup
```

Action: measure `explain` and latency on realistic workloads, add the compound index, and bound reporting resource budgets.

### Security

Findings:

```text
Service account holds admin privileges: CRITICAL
API returns internalNotes in customer JSON: HIGH
TLS enabled with hostname verification: PASS
```

Action: separate migration and runtime credentials, enforce least-privilege roles, apply DTO allowlists, and add negative integration tests.

### Backups

Findings:

```text
Daily backup job succeeds: PASS on schedule
Restore drill missing: UNKNOWN/HIGH or CRITICAL per RPO/RTO
Backups reside in same cloud account/region: REVIEW
```

Action: execute a restore drill, measure RTO, and audit failure domains, secret storage, and KMS key dependencies.

### Operations

Findings:

```text
Disk at 82%, growing 8 GiB/day: needs time-to-full forecast
Replica lag alert missing: FAIL
Unbounded app retry timeouts: HIGH
```

Action: configure capacity and lag alerts, add backoff/jitter/idempotency, and rehearse failovers. This example shows how **every finding requires a concrete action**, rather than evaluating a real cluster.

## 54. Technical Interview / Review Questions

### Question 1. A collection has 3 million documents without an index for its main query. Is adding RAM alone enough?

**Answer:** Probably not. You must examine the query plan, selectivity, sorting, working set, and storage I/O; an appropriate index often cuts scanned documents far more effectively than adding RAM alone.

### Question 2. Two requests both read stock = 2 and write `available=1`. Why is MongoDB single-document atomicity insufficient?

**Answer:** Each write is atomic individually, yet read–modify–write based on stale reads causes lost updates. Use conditional `$inc` or CAS/version predicates.

### Question 3. Why does a unique index not replace idempotency?

**Answer:** An index blocks duplicate keys; the application must still distinguish same-key/same-payload retries from conflicting payloads and prevent duplicate external side effects.

### Question 4. Collection `orders` has a unique `{tenantId, requestId}` index. Do two tenants using the same `requestId` collide?

**Answer:** No, if `tenantId` differs and no other unique index is violated; uniqueness applies to the pair.

### Question 5. Tenant A's GET returns only the `status` field of Tenant B's order. Is that still a violation?

**Answer:** Yes. Projections never substitute for document/tenant authorization.

### Question 6. An API querying `{email: null}` returns documents missing the `email` field. Why?

**Answer:** MongoDB equality against `null` matches both explicit `null` and missing fields per query semantics; use `$type` or `$exists` to distinguish them.

### Question 7. Why does `@Version` not automatically protect against a stale HTTP form submission?

**Answer:** If the backend reloads the latest version before saving without comparing against the client's `expectedVersion`, it still overwrites newer changes using old form data. Enforce `expectedVersion`/ETag with CAS on write.

### Question 8. You already have a three-node replica set. Do you still need backups?

**Answer:** Yes. Accidental deletes and faulty updates replicate immediately. Backups and PITR recover from logical errors and broader disasters.

### Question 9. Backups report Success every night. Why run restore drills?

**Answer:** Backups may miss collections, lack encryption keys, hold corrupt archives, hit missing permissions, or take longer than RTO to restore. Drills provide real proof.

### Question 10. Disk hits 95%. What should you do before deleting documents?

**Answer:** Check growth rates, `dbPath`/mounts, bytes/inodes/IOPS, active workloads, topology/quorum, and expand capacity or throttle ingestion. Never delete WiredTiger, journal, or oplog files.

### Question 11. Why is `allowDiskUse` not always the fix for an out-of-memory aggregation?

**Answer:** It shifts pressure onto temporary disk I/O; if disks are already saturated or nearly full, performance or stability can worsen.

### Question 12. Does seeing `COLLSCAN` in `explain` automatically prove a bug?

**Answer:** No. It depends on collection size, query intent, selectivity, and execution cost. Check examined/returned ratios and actual workload impact.

### Question 13. A read-only orders service uses `readWriteAnyDatabase`. Which pillar FAILS?

**Answer:** Security (least privilege / RBAC). The service holds far broader privileges than needed.

### Question 14. Does a timeout during transaction commit prove the transaction aborted?

**Answer:** No. It may be an unknown commit result; retry commit or reconcile using driver semantics and a stable idempotency key.

### Question 15. Why can `skip(100000)` be much slower than keyset pagination?

**Answer:** Deep skips force the engine to walk past huge numbers of index/document entries before emitting a page. Keyset pagination jumps straight via sort key + tiebreaker when properly indexed.

### Question 16. On a sharded collection, does creating a unique index on an arbitrary field guarantee global uniqueness?

**Answer:** No. Unique indexes on sharded collections enforce rules tied to the shard key and MongoDB version; verify compatibility beforehand.

### Question 17. Time-series data has a TTL index. Do backups immediately purge expired data too?

**Answer:** No. TTL runs asynchronously on the live collection per policy; backups and snapshots follow their own retention schedules.

### Question 18. Only one Java service is supposed to write to a collection, yet an ETL job writes via the raw driver. Why include ETL in the review?

**Answer:** The ETL job is a live writer that can bypass app-level validation, versioning, and idempotency, breaking invariants.

### Question 19. A query projection excludes `passwordHash`, yet responses still leak `internalRiskScore`. What went wrong?

**Answer:** Exclusion blacklists miss newly added sensitive fields; switch to DTO allowlists and add regression tests.

### Question 20. A change stream worker stores its resume token only in RAM. What is needed after a crash?

**Answer:** Durable token storage and recovery handling if oplog history expires, plus idempotent processing or re-bootstrapping.

### Question 21. A secondary lags further behind than the oplog window. Can it resume replication normally?

**Answer:** No guarantee; it may require an initial sync or re-bootstrapping depending on topology and consumer needs.

### Question 22. Is a 20 MiB MongoDB document valid?

**Answer:** Standard BSON documents cap at 16 MiB; redesign via referencing, bucketing, or GridFS for large files.

### Question 23. `MongoClients.create(uri)` succeeds without throwing. Does that prove credentials are valid?

**Answer:** Not yet. Drivers often connect and authenticate lazily on the first command; tests must execute a real database operation.

### Question 24. Why is a security test checking "insert failed with any error" insufficient to verify RBAC?

**Answer:** It could fail from duplicate keys, network drops, or TLS errors. Assert `Unauthorized` explicitly and verify zero data mutation.

### Question 25. Target RTO is 30 minutes, yet the restore drill took 4 hours. What is the status?

**Answer:** FAIL against RTO; improve backup/DR tooling/capacity or obtain formal approval to adjust RTO—never mark PASS.

### Question 26. Disk fills up due to journal or WiredTiger files. Should you `rm` large files in `dbPath`?

**Answer:** Never. Those are internal engine files required for consistency and recovery; expand capacity and follow supported remediation.

### Question 27. Two users edit two different fields simultaneously and `@Version` throws a conflict. Is MongoDB broken?

**Answer:** No. Document-level optimistic locking conservatively prevents lost updates; field-level merging requires explicit application design.

### Question 28. TLS is enabled. Is it safe to log full URIs with passwords?

**Answer:** No. TLS protects traffic in transit, not secrets written to application log files.

### Question 29. A production dataset containing PII is restored to staging. Can RBAC be relaxed because it is staging?

**Answer:** No. Restored sensitive data demands equivalent protection, masking, access control, and retention.

### Question 30. Pre-release review finds Backup Restore Drill is UNKNOWN. Can it be marked PASS because scheduled backups succeed?

**Answer:** No. Successful backup schedules do not prove restorability; complete a drill or record formal risk acceptance.

## 55. Post-Review Prioritization Matrix

Not every finding gets fixed simultaneously. One way to triage:

| Priority | Example | Typical Decision |
| --- | --- | --- |
| **P0 / Block** | Cross-tenant leak, plaintext credential exposure, no recoverable backup for critical data | Block release / trigger incident response per policy |
| **P1 / Before release or mitigated** | Missing unique idempotency key for payments, non-atomic transaction, zero quorum headroom | Fix beforehand or obtain formal risk acceptance |
| **P2 / Upcoming sprint** | Query p99 misses SLO, missing index on major endpoint | Assign action with deadline and benchmark |
| **P3 / Periodic improvement** | Low-impact redundant index, non-blocking doc gap | Assign owner for next review cycle |

Assignment template:

```text
Finding ID: Q-07
Description: /orders list query scans too many docs for large tenants
Evidence: explain + p99 dashboard
Risk: High
Owner: Orders backend team
Mitigation: cap page size + rate limit
Fix: compound index & keyset pagination
Acceptance: p99 meets SLO on peak fixture
Deadline:
Rollback: feature flag / restore prior index policy
```

Acceptance targets must reflect real SLOs. Never treat a sample p99 figure as a universal standard across systems.

## 56. Final Five-Pillar Summary Checklist

### A. Data Modeling

- [ ] Aggregates and document boundaries match use cases.
- [ ] Embedding vs referencing aligns with cardinality and lifecycle.
- [ ] No unbounded documents or arrays exist.
- [ ] BSON types, IDs, money, and timestamps are standardized.
- [ ] Contracts cover missing, `null`, and optional fields.
- [ ] Unique constraints and schema validation are active.
- [ ] Schema migration, retention, and archiving plans exist.
- [ ] Shard keys and time-series setups match workloads where used.

### B. Queries

- [ ] Top query shapes are measured on representative data.
- [ ] Compound, unique, partial, multikey, and collation indexes are right.
- [ ] `explain` and examined/returned ratios are verified.
- [ ] Sorts, pagination, and aggregations are bounded and index-aligned.
- [ ] Applications never materialize unbounded results.
- [ ] Write concurrency and invariants use atomic updates, CAS, transactions, and idempotency appropriately.

### C. Security

- [ ] Authentication is enabled and verified by negative tests.
- [ ] Database RBAC enforces least privilege.
- [ ] Network isolation, TLS, and private connectivity are sound.
- [ ] Tenant/owner authorization is enforced across all paths.
- [ ] Secrets, encryption, PII, logs/exports, and audits are governed.
- [ ] Credential and key rotation have owners.

### D. Backups

- [ ] Backups are valid, encrypted, and properly retained/ACL-protected.
- [ ] RPO and RTO are clearly defined.
- [ ] PITR is enabled where business rules require it.
- [ ] Restore drills are executed and timed.
- [ ] DR/failure-domain plans and controls for restored sensitive data exist.
- [ ] Alerts monitor backup failures and recovery readiness.

### E. Operations

- [ ] SLOs, error budgets, metrics, and alerts have owners.
- [ ] Capacity (bytes, inodes, IOPS, RAM) tracks headroom and time-to-full.
- [ ] Replica health, quorum, lag, and oplog are monitored.
- [ ] On-call rotations, runbooks, incident decisions, and rollbacks exist.
- [ ] Maintenance, upgrades, and index builds follow change control.
- [ ] Java pools, retries, transactions, and CDC expose observability.
- [ ] Postmortem and reconciliation procedures cover corrupted data or uncertain write outcomes.

## 57. Conclusion

A reliable MongoDB deployment requires **accurate data models, efficient queries, strict permissions, proven recoverability, and disciplined operations**. All five pillars interlock: flawed models prevent clean indexing; poor queries drive cache and disk pressure; broad permissions risk leaks; untested backups fail during crises; and missing monitoring or runbooks prolong outages.

The core value of this checklist lies not in ticking boxes, but in **evidence and concrete follow-through**. For every risk, record an owner, impact, verifying test or metric, due date, and closure criteria. Keep unverified items marked `UNKNOWN`; resolve or formally accept critical risks before shipping.

Applied repeatedly during design, pre-release gates, routine operations, and post-incident reviews, this checklist serves as a **shared engineering contract among developers, DBAs/SREs, security teams, and business owners**—catching bugs early, preventing duplicate or lost updates, protecting SLOs, and ensuring recoverability long before an emergency strikes.

### Official References

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Aggregation](https://www.mongodb.com/docs/manual/aggregation/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Authentication and Authorization](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Client-Side Field Level Encryption](https://www.mongodb.com/docs/manual/core/csfle/)
- [MongoDB Manual — Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Replica Sets](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Atlas — Monitor Cluster Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/)
- [MongoDB Atlas — Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
