# Event Data: History Storage, Retention Policies, and Aggregation Queries in MongoDB

## 1. Why Design Event Data Differently from State Data?

An application might have an `orders` document representing the **current state** of an order:

~~~javascript
{
  _id: "order-101",
  tenantId: "tenant-A",
  status: "SHIPPED",
  total: NumberDecimal("125.50"),
  updatedAt: ISODate("2026-11-14T09:05:00Z")
}
~~~

This document answers “What state is the order currently in?”. However, it does not answer on its own:

- When was the order created, and which states did it pass through?
- Who or which system changed the state, and why?
- How many `OrderPaid` events occurred within one hour?
- Which operations must be retained for 30 days, 13 months, or longer?
- When a customer requests reconciliation, how do we reconstruct what happened?
- Can the reporting system view aggregated metrics without scanning billions of records?

To answer these questions, we typically store **event history** in an append-only manner: each significant change creates a new event instead of overwriting older ones.

~~~text
Orders collection: current state
  order-101: SHIPPED
             |
             +------> Event history:
                        08:00 OrderCreated
                        08:10 PaymentAuthorized
                        08:15 PaymentCaptured
                        09:00 OrderPacked
                        09:05 OrderShipped
                                     |
                        +------------+------------+
                        |                         |
                        v                         v
                  Timeline API             Daily rollups
~~~

This lesson belongs to the **MongoDB Document Database Engine** module, **Application Design** chapter, on **Event Data: History Storage, Retention Policies, and Aggregation Queries in MongoDB**.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish event logs, audit logs, domain events, telemetry, and change streams.
2. Design event documents with identity, tenant, actor, timestamps, schema version, and payload.
3. Distinguish `occurredAt` (event time), `receivedAt` (ingest time), and `expiresAt`.
4. Store append-only history and handle corrections, replays, duplicates, and out-of-order events.
5. Choose regular collections, time-series collections, or self-managed bucket documents where appropriate.
6. Design unique indexes, compound indexes, shard keys, and partitions aligned with workloads.
7. Apply retention via TTL indexes or time-series `expireAfterSeconds`, understanding deletion lag and risks.
8. Design hot/warm/cold archival policies, legal holds, and personal data handling.
9. Write hourly/daily/monthly aggregation pipelines using `$match`, `$dateTrunc`, and `$group`.
10. Handle timezones, DST days, missing time buckets, and late arrivals.
11. Build rollups/materialized views using `$merge` or workers.
12. Know when to use Change Streams for projection updates and why checkpoints/idempotency are required.
13. Write MongoDB Java Driver and Spring Data MongoDB examples for ingestion and aggregation.
14. Diagnose performance, memory/disk spilling, query indexes, TTL backlogs, and data correctness.
15. Complete hands-on exercises and a production checklist.

## 2. There Are Many Kinds of “Events”, Not One Universal Format

| Type | Example | Purpose | Storage characteristics |
|---|---|---|---|
| Domain event | `OrderPaid`, `RentalReturned` | Describe a business occurrence | Identity + business version + context |
| Audit event | Who changed whose permissions? | Traceability, governance | Actor, before/after, integrity |
| Application event | Request retry, job completed | Application diagnostics | Correlation/tracing, short retention |
| Security event | Login denied, role grant | Security investigation | Retention and restricted access |
| Telemetry/measurement | CPU 65%, temperature 28°C | Time-based analysis | High-volume measurements, uniform structure |
| CDC/change event | MongoDB insert/update/delete | Downstream synchronization | Resume tokens and scope |
| Business fact | A payment transaction | Reporting and reconciliation | Currency, reference IDs, status |

### 2.1. A Domain Event Is Not a Text Log

A string like `"user did something"` is insufficient to reconstruct business activity. A good event has:

- A clearly defined event type.
- A unique ID within the chosen scope.
- The business entity ID.
- Timestamp and actor.
- Minimal payload with a schema version.
- Correlation/causation metadata.
- A retention policy.

### 2.2. An Audit Event Is Not Necessarily an Event-Sourcing Event

Auditing serves investigations; event sourcing uses the event stream as the **source of truth** to rebuild aggregate state. The two models differ in immutability, ordering, consistency, and retention requirements.

**Do not** enable a 30-day TTL on an event store serving as the source of truth for an event-sourced system without snapshots, replay support, and long-term preservation.

### 2.3. MongoDB Change Streams Do Not Replace Event History

Change Streams read operation history from the oplog, not an infinite business event store. A resume token is only usable while the corresponding oplog history still exists.

If you need to query events from three years ago, you generally need a dedicated collection/archive designed for that purpose rather than relying on `watch()`.

## 3. Three Design Questions Before Creating a Collection

1. **What is the data used for?** User timelines, audits, hourly analytics, state replay, or regulatory evidence?
2. **How long is it retained?** Based on product value, cost, and legal obligations—not arbitrary TTL defaults.
3. **What are the common queries?** By `tenantId + entityId`, by time range, by `eventType`, or GROUP BY day?

A schema tuned solely for insert throughput without time-based indexes/filters can make dashboards crawl. Conversely, adding too many indexes on a high-volume event stream increases write amplification and storage costs.

## 4. Recommended Schema for Regular Event History

Example document-based event:

~~~javascript
{
  _id: "evt-order-101-0004",
  tenantId: "tenant-A",
  eventId: "evt-order-101-0004",
  aggregateType: "Order",
  aggregateId: "order-101",
  aggregateVersion: NumberLong(4),
  eventType: "OrderShipped",
  schemaVersion: 2,
  occurredAt: ISODate("2026-11-14T09:05:00.000Z"),
  receivedAt: ISODate("2026-11-14T09:05:00.180Z"),
  actor: {
    kind: "system",
    id: "warehouse-worker"
  },
  correlationId: "checkout-request-204",
  causationId: "evt-order-101-0003",
  payload: {
    carrier: "carrier-demo",
    trackingReference: "tracking-redacted",
    region: "south"
  },
  retentionClass: "standard",
  expiresAt: ISODate("2027-02-12T09:05:00.000Z")
}
~~~

### 4.1. Identity and Duplicate Protection

- `_id` or `eventId` is the event's unique identifier.
- `tenantId` provides the multi-tenant logical boundary.
- `aggregateId` links the event to the entity.
- `aggregateVersion` expresses per-entity ordering when the workflow controls versions.

If a producer retries after a timeout, the same event must keep **the same event ID** to avoid duplication. Never generate a fresh ObjectId per retry and treat it as a distinct business event.

### 4.2. occurredAt and receivedAt Are Different

- `occurredAt`: when the business event actually happened, per a trusted clock/source.
- `receivedAt`: when the ingest server received/persisted the event.

A device offline for 2 hours can transmit an event at 11:00 whose `occurredAt` is 09:00. This is a **late-arriving event**, not inherently invalid data.

### 4.3. actor, correlationId, and causationId

These fields enable traceability:

~~~text
Request R42
  |
  +--> PaymentAuthorized event
              |
              +--> OrderConfirmed event
                        |
                        +--> ShipmentScheduled event
~~~

There is no need to dump emails, phone numbers, or full HTTP headers into every event just for tracing. Use access-controlled internal identifiers.

### 4.4. schemaVersion

Payloads evolve across releases:

~~~text
OrderPaid v1: { amount, currency }
OrderPaid v2: { amount, currency, paymentMethodCategory }
~~~

Consumers need versioned decoders/upcasters or a migration plan. Never rename fields silently and expect historical reports to stay accurate.

### 4.5. Use Decimal128 for Money

Monetary values should not arbitrarily use binary floating-point when cent-level precision is required. MongoDB supports BSON Decimal128; standardize currency, rounding, and conversion policies.

## 5. Append-Only: Correcting via New Events

In business/legally significant event histories, record a new event to adjust outcomes rather than mutating the old event's payload.

~~~text
2026-11-14 09:00  PaymentCaptured amount 125.50
2026-11-14 09:10  PaymentRefunded amount 20.00
2026-11-14 09:15  PaymentAdjustmentPosted amount -5.00
~~~

State and net totals are derived from the event sequence according to domain rules.

### 5.1. Preventing History Tampering

MongoDB RBAC can separate roles:

- Producer: `insert`, minimal reads.
- Reader: `find`.
- Aggregator: `find` and write to rollup collections.
- Administrator: modify indexes/retention under approval.

Do not grant `update`/`remove` on event archives to everyday services. However, “append-only in the application” **does not automatically make it legally certified WORM/immutable storage**; admin access controls, auditing, backups, and archival policies are still required.

### 5.2. Correction Does Not Mean Deleting Old Events

A correction should reference the original event via `correctsEventId` or `causationId`, and projections must know how to apply corrections per domain logic.

### 5.3. Never Store Secrets in Event Payloads

Never store access tokens, raw payment cards, passwords, or sensitive headers in event logs. Minimize data, encrypt where appropriate, and maintain deletion/anonymization workflows if required by law.

## 6. Choosing Among Three Storage Models

| Model | Good for | Trade-offs |
|---|---|---|
| Regular document collection | Domain events, audits, event sourcing, uniqueness, transactions | More documents/index entries |
| Time-series collection | Dense sensor/device measurements over time | Restrictions on unique indexes, transaction writes, updates |
| Self-managed bucket pattern | Grouping small events per entity/time bucket | Bucket updates, document size, concurrent writes |
| Object storage archive + index manifest | Very long history, low storage cost | Complex direct queries, requires restore/replay |
| Summary/rollup collection | Fast dashboards/aggregated queries | Can be stale, must reconcile |

### 6.1. Default Model for Business Event History

If you need per-event unique IDs, atomic state + outbox updates, entity indexing, and diverse queries, a **regular collection** is usually the easiest choice to govern.

### 6.2. Default Model for Measurements

If each device emits a measurement every second with a small payload mostly aggregated over time, a time-series collection is a strong candidate—provided you accept its limitations on uniqueness, indexing, and transactions.

### 6.3. Do Not Choose Based on the Word “Event” Alone

Having a timestamp does not automatically call for a time-series collection. Audit trails needing uniqueness, transactions, and long-term governance often clash with time-series constraints.

## 7. Read/Write Event Design Driven by Queries First

Suppose there are three requirements:

1. Timeline for an order within a tenant.
2. Count all `OrderCreated` events per hour over a date range.
3. Report daily collected revenue per tenant.

To satisfy these, you need at least:

~~~text
tenantId
aggregateId
occurredAt
eventType
amount (for monetary events)
~~~

### 7.1. Ordered Timeline Conventions

Use `aggregateVersion` when a per-aggregate sequence exists. Otherwise, sort by `occurredAt` with a stable tie-breaker like `_id`, remembering not to assume perfectly synchronized wall clocks across producers.

### 7.2. Avoid Arbitrary Duplicate Fields

If `_id` is already the unique event ID, repeating `eventId` should only serve API/standardization conventions. Decide explicitly and document invariants.

## 8. Configuring Collections in the mongosh Lab

Use an isolated database; never run the operations below on real production data:

~~~javascript
use event_design_lab

db.createCollection("domain_events");
db.createCollection("daily_rollups");
db.createCollection("event_archive_manifest");
~~~

### 8.1. Unique Constraint

If the collection is **unsharded**, `_id` is unique across the collection:

~~~javascript
db.domain_events.createIndex(
  { tenantId: 1, eventId: 1 },
  { unique: true, name: "uq_tenant_event_id" }
);
~~~

This index prevents duplicate event IDs within a tenant, assuming each event consistently sets `tenantId` and `eventId`.

### 8.2. Timeline Index

~~~javascript
db.domain_events.createIndex(
  { tenantId: 1, aggregateId: 1, occurredAt: 1, _id: 1 },
  { name: "ix_tenant_aggregate_time" }
);
~~~

Supports filtering by tenant+aggregate, scanning chronologically, and tie-breaking.

### 8.3. Reporting Index

~~~javascript
db.domain_events.createIndex(
  { tenantId: 1, eventType: 1, occurredAt: 1 },
  { name: "ix_tenant_type_time" }
);
~~~

Do not create indexes for every permutation. Verify workload, selectivity, and `explain("executionStats")` before finalizing.

### 8.4. Indexes Increase Write Cost

Every event insert must update all secondary indexes. A collection with hundreds of millions of events and many secondary indexes can significantly increase storage, cache pressure, and write latency.

## 9. Consistent Lab Dataset for Deterministic Results

Run **once on a fresh collection**:

~~~javascript
db.domain_events.insertMany([
  {
    _id: "evt-a-001",
    tenantId: "tenant-A",
    eventId: "evt-a-001",
    aggregateId: "order-101",
    aggregateVersion: 1,
    eventType: "OrderCreated",
    occurredAt: ISODate("2026-11-10T08:00:00Z"),
    receivedAt: ISODate("2026-11-10T08:00:01Z"),
    amount: NumberDecimal("0.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-002",
    tenantId: "tenant-A",
    eventId: "evt-a-002",
    aggregateId: "order-101",
    aggregateVersion: 2,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T08:10:00Z"),
    receivedAt: ISODate("2026-11-10T08:10:01Z"),
    amount: NumberDecimal("125.50"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-003",
    tenantId: "tenant-A",
    eventId: "evt-a-003",
    aggregateId: "order-102",
    aggregateVersion: 1,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T11:30:00Z"),
    receivedAt: ISODate("2026-11-10T11:30:02Z"),
    amount: NumberDecimal("75.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-004",
    tenantId: "tenant-A",
    eventId: "evt-a-004",
    aggregateId: "order-101",
    aggregateVersion: 3,
    eventType: "PaymentRefunded",
    occurredAt: ISODate("2026-11-11T09:00:00Z"),
    receivedAt: ISODate("2026-11-11T09:00:01Z"),
    amount: NumberDecimal("-20.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-b-001",
    tenantId: "tenant-B",
    eventId: "evt-b-001",
    aggregateId: "order-201",
    aggregateVersion: 1,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T16:00:00Z"),
    receivedAt: ISODate("2026-11-10T16:00:01Z"),
    amount: NumberDecimal("400.00"),
    schemaVersion: 1
  },
  {
    _id: "evt-a-005",
    tenantId: "tenant-A",
    eventId: "evt-a-005",
    aggregateId: "order-103",
    aggregateVersion: 1,
    eventType: "PaymentCaptured",
    occurredAt: ISODate("2026-11-10T06:00:00Z"),
    receivedAt: ISODate("2026-11-12T12:00:00Z"),
    amount: NumberDecimal("10.00"),
    schemaVersion: 1
  }
]);
~~~

The last record is a **late-arriving event**: it occurred on the 10th but arrived on the 12th. It must count toward the report for the **day it occurred** when reporting by event time.

### 9.1. Do Not Attach TTL Immediately to This Dataset

Avoid using old eventTimes while learning aggregations only for TTL to delete your data automatically. The TTL section uses a separate lab collection.

### 9.2. Is the Sample Dataset Re-Runnable?

`insertMany` with fixed `_id` values will report a duplicate key error if re-run. That is a good signal confirming uniqueness enforcement, not an error to fix by wiping real data.

## 10. Querying an Aggregate's Timeline

~~~javascript
db.domain_events.find(
  {
    tenantId: "tenant-A",
    aggregateId: "order-101"
  },
  {
    _id: 1,
    eventType: 1,
    aggregateVersion: 1,
    occurredAt: 1,
    amount: 1
  }
).sort({
  aggregateVersion: 1,
  _id: 1
});
~~~

In the dataset, order-101 has `OrderCreated`, `PaymentCaptured`, and `PaymentRefunded`.

### 10.1. Ordering by aggregateVersion

If the producer maintains a controlled incrementing sequence, `aggregateVersion` is more reliable than timestamp sorting alone for reconstructing an aggregate.

### 10.2. Event Replay Requires Business Definitions

Simply sorting events does not reconstruct state by itself. Projection logic is required:

~~~text
OrderCreated  -> status CREATED
PaymentCaptured -> payment status PAID
PaymentRefunded -> adjust paid amount
~~~

### 10.3. Event Sourcing Must Check for Gaps

If aggregate versions are 1, 2, 4, the missing version 3 must be investigated rather than silently skipped.

## 11. Time-Based Queries: Use Half-Open Intervals

For reporting on 2026-11-10 UTC:

~~~javascript
const start = ISODate("2026-11-10T00:00:00.000Z");
const end = ISODate("2026-11-11T00:00:00.000Z");

db.domain_events.find({
  tenantId: "tenant-A",
  occurredAt: {
    $gte: start,
    $lt: end
  }
});
~~~

### 11.1. Why Not Use 23:59:59?

MongoDB BSON Dates have millisecond resolution. Using an end-of-day cutoff like `23:59:59` risks missing the final milliseconds; a half-open interval `[start, end)` prevents boundary bugs and simplifies bucketing.

### 11.2. Never Mix Timestamp Types

BSON Dates differ from ISO strings. If some documents store `occurredAt` as a string, range queries and `$dateTrunc` can fail or sort incorrectly.

### 11.3. Event-Time or Ingest-Time?

| Report | Usually filters by |
|---|---|
| Daily revenue when customers paid | `occurredAt` |
| Pipeline operations, ingestion backlog | `receivedAt` |
| Optimizing retention after receipt | `expiresAt` or `receivedAt` |
| Audit of when the system learned a fact | `receivedAt` alongside source timestamp |

A report may need both dimensions. Document the exact definition on the dashboard.

## 12. TTL on Regular Collections

MongoDB TTL indexes delete documents containing a Date field once they expire. Example in a separate lab collection:

~~~javascript
db.createCollection("transient_events");

db.transient_events.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expire_at"
  }
);
~~~

With `expireAfterSeconds:0`, documents whose `expiresAt` is a BSON Date become eligible for deletion once the current time passes that value.

### 12.1. Example Insert with a 7-Day Policy

~~~javascript
const now = new Date();
const sevenDaysMs = 7 * 24 * 60 * 60 * 1000;

db.transient_events.insertOne({
  _id: "temp-event-001",
  occurredAt: now,
  receivedAt: now,
  eventType: "NotificationSent",
  expiresAt: new Date(now.getTime() + sevenDaysMs)
});
~~~

This policy counts from **ingest**; if 7 days from actual occurrence is required, compute from `occurredAt` per definition while accounting for late arrivals.

### 12.2. The TTL Field Must Be a Date

If `expiresAt` is a string or missing, TTL will not delete the document as expected. Use schema validation/contracts to enforce the Date type.

### 12.3. TTL Does Not Apply to _id

A TTL index must be **single-field**; never create a compound TTL index trying to “also filter tenantId”, and never put TTL on `_id`.

### 12.4. TTL Indexes Also Support Queries

A TTL index is a real index; however, it does not replace tenant/time/eventType indexes needed by your workload.

## 13. TTL Is Background Deletion, Not a Precision Clock

MongoDB's TTL monitor runs in the background; an expired document is not guaranteed to vanish immediately.

~~~text
expiresAt reached
       |
       v
Eligible for deletion
       |
   TTL monitor
       |
       v
Deletion observed later
~~~

### 13.1. Delay Depends on Load

Deletion can lag further on large collections, massive backlogs of expired documents, or busy servers. TTL does not replace access controls to block reading expired data.

### 13.2. On Replica Sets

TTL deletes execute on the primary and replicate to secondaries. If the cluster lacks a primary, lacks majority, or is overloaded, do not expect TTL to stay strictly on schedule.

### 13.3. TTL Is Not a Complete Legal Policy

TTL removes data from the MongoDB collection, yet:

- Backups/snapshots have separate retention.
- Archives/data lakes/object stores hold separate copies.
- Search indexes/caches may retain copies.
- Legal holds may mandate preservation or special deletion workflows.
- Data may linger for a window after expiration.

Full data lifecycle governance and verifiable evidence are required per legal obligations; never treat TTL as proof that every copy was wiped.

## 14. Calculating Expiration from Event Time vs. Ingest Time

Suppose the policy is “retain 30 days”.

| Calculation | Advantage | Risk |
|---|---|---|
| `occurredAt + 30d` | Aligns with business date | Late events may expire immediately upon ingest |
| `receivedAt + 30d` | Guarantees 30 days of processing after ingest | Events retained longer than business age |
| `expiresAt` by retentionClass | Explicit per-event control | Must ensure accurate field and policy sync |
| Per-collection TTL | Simple when one policy fits all | Hard to group mixed retention tiers |
| Archive then delete | Long retention outside hot DB | Requires pipeline and correctness proof |

### 14.1. Late Arrivals

An event occurred 40 days ago and arrives today. If TTL is 30 days from occurredAt, the document may be deleted immediately after ingest. If late data needs analysis, design the retention policy accordingly.

### 14.2. RetentionClass and expiresAt

~~~javascript
{
  eventType: "LoginAttempt",
  retentionClass: "security-90d",
  receivedAt: ISODate("2026-11-14T00:00:00Z"),
  expiresAt: ISODate("2027-02-12T00:00:00Z")
}
~~~

This is an illustrative policy; real retention periods follow security, privacy, and legal mandates.

### 14.3. “No expiresAt” Is Dangerous Without Controls

A document missing the field is never deleted by TTL. If a producer has a schema bug, data can accumulate forever. Use validators, alerts for `expiresAt: {$exists:false}`, and an exception process.

## 15. Partial TTL, Legal Holds, and Data Classification

On a **regular collection**, a partial TTL index can scope deletion to a subset of documents, subject to server version and index rules.

Example policy “delete only debug audit events”:

~~~javascript
db.transient_events.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_debug_only",
    expireAfterSeconds: 0,
    partialFilterExpression: {
      retentionClass: "debug"
    }
  }
);
~~~

**Note:** This is an example for a **different collection or alternative index design**; do not create it with the same key specification as the `ttl_expire_at` index in section 12 on the same collection without checking index conflicts. Use a single unified policy or intentionally separate collections/TTL fields.

### 15.1. Legal Holds

Do not try to handle every legal hold by setting `expiresAt` far in the future without governance. Options include:

- Moving held records into a non-TTL collection/archive.
- Excluding via partial TTL under a sound policy.
- Building an approval-gated hold/release workflow.
- Keeping an audit record of the hold decision.
- Synchronizing backup/archive handling.

### 15.2. Partial TTL Does Not Delete Instantly

A document matching the filter and past expiration still waits for the TTL monitor. Never use TTL as a security boundary to block real-time access.

### 15.3. Separating Storage by Event Type

If audits require 7 years and telemetry requires 7 days, sharing one collection with complex TTL rules can be hard to operate. Splitting collections by access pattern and retention is often worth considering.

## 16. Changing a TTL Policy Requires Change Management

Before shrinking `expireAfterSeconds` from 90 days down to 7 days:

1. Estimate how many documents immediately become eligible for deletion.
2. Review backups/archives and legal retention mandates.
3. Check disk/CPU/I/O and replication impact of bulk deletes.
4. Check SLOs and maintenance windows.
5. Secure approval and a realistic rollback plan.
6. Apply via `collMod` per the appropriate docs/version.
7. Monitor TTL deletion lag and remaining dataset size.
8. Never assume deleted data can be “rolled back” by increasing TTL again.

### 16.1. Do Not Use createIndex to Change an Existing TTL Index

MongoDB docs require modifying `expireAfterSeconds` on an existing TTL index via `collMod` (per supported version/features), not by re-running `createIndex` with a different option.

### 16.2. Back Up Before Destructive Changes

TTL expiration deletes data; it cannot be undone by raising the expiration threshold after documents vanish. Recovery requires backups and a reconciliation plan.

## 17. Time-Series Collections Group Measurements

For sensor readings, MongoDB provides time-series collections stored internally as buckets at the storage engine level.

~~~javascript
db.createCollection("device_measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "meta",
    granularity: "minutes"
  },
  expireAfterSeconds: 2592000
});
~~~

`2592000` seconds equals 30 days for illustration. `measuredAt` is the **measurement time**; `meta` holds relatively stable source metadata.

### 17.1. Measurement Example

~~~javascript
db.device_measurements.insertMany([
  {
    measuredAt: ISODate("2026-11-14T08:00:00Z"),
    meta: {
      tenantId: "tenant-A",
      deviceId: "device-7",
      region: "south"
    },
    temperatureC: 27.3,
    humidityPct: 65
  },
  {
    measuredAt: ISODate("2026-11-14T08:05:00Z"),
    meta: {
      tenantId: "tenant-A",
      deviceId: "device-7",
      region: "south"
    },
    temperatureC: 27.8,
    humidityPct: 64
  }
]);
~~~

### 17.2. MetaField Should Be Stable

`meta` should represent identifying/grouping attributes of the series, such as deviceId, tenantId, and location/region. Changing metadata arbitrarily on every record fragments buckets and degrades storage efficiency.

### 17.3. Do Not Put Every Payload Field into meta

Never place timestamps, request IDs, or per-event volatile fields into meta unless used for grouping. High cardinality and constant churn hurt bucket compression.

## 18. Important Limitations of Time-Series Collections

Compared to regular collections, time-series collections have specific semantics depending on MongoDB version:

- MongoDB does not support **unique indexes** on time-series collections.
- No default `_id` index as on regular collections.
- Cannot perform **writes** to time-series collections inside transactions.
- Updates/deletes are restricted; do not use them as a mutable order-state table.
- Time-series measurements have a distinct document size limit (4 MB in current Manuals).
- Indexing and shard key patterns have release-dependent constraints.
- TTL operates by **bucket**, not “millisecond-exact per-document deletion”.

### 18.1. The Idempotency Problem

If a producer sends the same measurement twice with the same eventId, a time-series collection cannot enforce a unique index on eventId. You must tolerate/deduplicate in queries or use a separate staging/dedup architecture.

### 18.2. You Cannot Solve Everything Using a Transaction with a Side Collection

Because time-series writes are unsupported inside transactions, you cannot create a MongoDB transaction combining “insert unique event key into a regular collection” and “insert time-series measurement” and claim the two steps are atomic.

Alternatives:

- Regular collection as the source of truth with unique constraints, and time-series as a derived read model.
- At-least-once ingestion followed by downstream deduplication.
- Message broker/event IDs with an idempotent/reconciled pipeline.
- If strict uniqueness is mandatory, prefer a regular collection over time-series.

### 18.3. Read Side Still Excels at Aggregation

Time-series collections are great for meta/time queries and statistics. Write/uniqueness restrictions do not mean poor query/aggregation capability.

## 19. Time-Series TTL Operates by Bucket

When creating a time-series collection with `expireAfterSeconds`, MongoDB uses `timeField` to evaluate expiration, yet **only deletes a bucket once all measurements in that bucket have expired**.

~~~text
Bucket B contains:
  08:00 measurement
  08:20 measurement
  08:55 measurement

TTL 30 days:
  08:00 expired
  08:20 not yet expired
  08:55 not yet expired

=> Bucket B is not deleted yet.
~~~

Even after a bucket becomes eligible, MongoDB still uses a background TTL process, so deletion is not instantaneous.

### 19.1. Granularity Affects Bucket Coverage

Per time-series TTL documentation, `seconds`/`minutes`/`hours` granularity governs the maximum time span a bucket can cover. Larger bucket spans typically introduce greater deletion lag relative to measurement time.

### 19.2. Partial TTL on Time-Series

Starting in MongoDB 7.0, you can create partial TTL indexes based on `metaField` to expire a subset of measurements **earlier** than the collection-level TTL. When a collection has a global `expireAfterSeconds`, a partial TTL **cannot** extend a group's lifetime beyond the collection-wide TTL.

### 19.3. Do Not Blindly Apply Regular Collection TTL Syntax to Time-Series

Always check documentation for your exact server version. Time-series TTL/index policies differ from regular collections; do not assume every `partialFilterExpression` is supported.

### 19.4. Time-Series for Audit Trails?

If auditing requires unique eventIds, compensating correction records, tiered retention, and transactions alongside domain state, a regular collection is usually a better fit.

## 20. Sharding for Event Data

Continuously growing event data may require sharding. However, the shard key must align with queries and write distribution.

Commonly evaluated options:

- `tenantId`: queries typically stay within one tenant; risk of a giant tenant.
- `tenantId + aggregateId`: entity locality; wide time-range queries may scatter.
- `tenantId + occurredAt`: per-tenant time-range routing; risk of shard hotspots if monotonic.
- Hashed keys distribute writes evenly, trading off range queries and unique indexes.

### 20.1. Unique Index Rules When Sharding

MongoDB sharded collections enforce the **unique index shard-key-prefix** rule. Not every unique index valid on an unsharded collection remains permitted after sharding.

For example, with a range shard key `{ tenantId: 1 }`, a unique index `{ tenantId:1, eventId:1 }` satisfies the prefix rule, subject to other requirements.

### 20.2. Do Not Assume Global `_id` Uniqueness When `_id` Is Not the Shard Key

On a sharded collection, if `_id` is not part of the shard key, MongoDB only guarantees `_id` uniqueness within each shard; producers must guarantee globally unique IDs or design keys accordingly.

### 20.3. Hashed Unique Constraints Have Limits

MongoDB does not support unique hashed indexes. If strict uniqueness on `tenantId,eventId` is required, never pick a hashed shard key assuming the existing unique index still works unchanged.

### 20.4. Time-Series Sharding Has Its Own Rules

Time-series collections have specific shard key constraints around `metaField` and `timeField`. Current MongoDB Manuals warn that `timeField`-only shard keys can cause hotspots, and `timeField` in time-series shard keys has been deprecated since MongoDB 8.0. Check release documentation before deciding.

## 21. Large-Scale Event Storage: Hot/Warm/Cold Tiering

A sample policy:

~~~text
Event created
      |
      v
Hot MongoDB (0-30 days)
      |
      +--> near-real-time API
      +--> troubleshooting
      +--> dashboard short windows
      |
      v
Warm history (30-180 days)
      |
      +--> archive MongoDB / optimized storage
      +--> weekly/monthly reporting
      |
      v
Cold archive (>180 days)
      |
      +--> object storage / data lake
      +--> compliance/replay on demand
      |
      v
Final deletion per policy (subject to legal hold)
~~~

Day ranges are illustrative, not MongoDB defaults or legal recommendations.

### 21.1. Archival Must Complete Before Deletion

~~~text
Select finalized range
     |
Export/upload with checksums
     |
Verify count, IDs, schemas, decrypt/restore
     |
Write immutable archive manifest
     |
Approve deletion of hot copy
     |
TTL/manual cleanup
~~~

Never enable TTL and only start archiving afterward if events could be deleted before export finishes.

### 21.2. Archive Manifest

~~~javascript
{
  _id: "archive-tenantA-2026-10",
  tenantId: "tenant-A",
  from: ISODate("2026-10-01T00:00:00Z"),
  toExclusive: ISODate("2026-11-01T00:00:00Z"),
  objectUri: "archive://approved-bucket/tenantA/2026-10",
  documentCount: NumberLong(1200345),
  checksum: "sha256-reference-value",
  schemaVersion: 3,
  verifiedAt: ISODate("2026-11-14T00:00:00Z"),
  status: "VERIFIED"
}
~~~

URIs/checksums are placeholders; manifests need strict permissions and tamper protection.

### 21.3. Backups Differ from Archives

Backups restore system state to a point in time; archives preserve and query long-term history. TTL deletes replay chronologically across replication/backups, though older snapshots can still hold TTL-deleted events.

### 21.4. Restore Drills

An archive is only meaningful if you can decrypt, download, verify schemas/counts/checksums, and replay it. Never mark `ARCHIVED` solely because an upload job returned success.

## 22. Compliance, Privacy, and Legal Holds

An event log can still contain personal data even when storing only IDs and timestamps, due to linkability.

Define:

- Data controller/owner.
- Purpose limitation and data minimization.
- Retention categories and legal basis.
- Deletion/anonymization/hold workflows.
- Access controls and auditing.
- Encryption at rest and in transit.
- Backup/archive retention.
- Region/data residency requirements.
- Data subject request workflows.

### 22.1. Event Sourcing and Right-to-Erasure Can Conflict

If long-term event history is the source of truth yet contains PII, design deletion strategies upfront: tokenized references, a separated PII side store, redaction policies, or crypto-shredding where legally permitted.

### 22.2. TTL Does Not Delete Search Indexes or Caches

An event may expire via TTL in MongoDB while copies persist in Elasticsearch, data lakes, or caches. Propagate deletions according to policy.

### 22.3. Legal Holds Should Be Explicit in the Retention Model

Never abuse an unmonitored `expiresAt:null` to represent an indefinite hold. Define explicit hold states, approvals, and controls that can prove when a hold is released.

## 23. MongoDB Aggregation: Counting Events by Type

Counting by `tenantId` and `eventType`:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-12T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$eventType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
]);
~~~

In the dataset: tenant-A has 3 `PaymentCaptured`, 1 `PaymentRefunded`, and 1 `OrderCreated` (including the ingested late arrival).

### 23.1. Put $match at the Start of the Pipeline

Place tenant/time filters early to leverage indexes and reduce data entering blocking stages.

### 23.2. Multi-Tenant Privacy Rules

Never omit the `tenantId` filter on dashboards/requests. Application authorization must verify allowed tenants before querying; collection-level database roles do not enforce row-level tenant isolation automatically.

## 24. $dateTrunc: Grouping by Hour or Day

MongoDB 5.0+ provides `$dateTrunc`:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: "PaymentCaptured",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        bucketStart: {
          $dateTrunc: {
            date: "$occurredAt",
            unit: "hour",
            timezone: "UTC"
          }
        }
      },
      events: { $sum: 1 },
      gross: { $sum: "$amount" }
    }
  },
  { $sort: { "_id.bucketStart": 1 } }
]);
~~~

Results for tenant-A on the 10th UTC have buckets 06:00 (10.00), 08:00 (125.50), and 11:00 (75.00). The final event's `receivedAt` is on the 12th, yet grouping by `occurredAt` attributes it to the 10th.

### 24.1. Store Buckets as BSON Dates

Do not convert buckets into strings for grouping if you still need Date sorting, ranges, or indexing. Format strings at the API/presentation layer when appropriate.

### 24.2. binSize

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "minute",
    binSize: 15,
    timezone: "UTC"
  }
}
~~~

Groups into 15-minute intervals.

### 24.3. startOfWeek

For weekly reporting, define whether weeks start on Monday or Sunday per business rules using `startOfWeek` with `unit:"week"`. Never let dashboards and batch jobs use conflicting conventions.

## 25. Timezones and Daylight Saving Time

MongoDB stores BSON Dates as UTC milliseconds since the epoch. Yet a “business day” may be defined in the tenant's local timezone.

Example:

~~~javascript
{
  $dateTrunc: {
    date: "$occurredAt",
    unit: "day",
    timezone: "Asia/Ho_Chi_Minh"
  }
}
~~~

### 25.1. UTC Buckets Differ from Local Calendar Dates

An event at 2026-11-10 23:30Z falls on the 11th in Vietnam (UTC+7). If a dashboard reports “the 10th in Vietnam”, the query must compute UTC boundaries from the corresponding local midnights rather than slicing by the timestamp's UTC date.

### 25.2. DST

In timezones with Daylight Saving Time, a local calendar day can be 23 or 25 hours long. `$dateTrunc` understands timezone rules; never add a fixed 24 hours to represent every local calendar day.

### 25.3. Timezone Should Be a Policy Field

If tenants span different timezones, store a governed timezone identifier like `Asia/Ho_Chi_Minh`, rather than storing fixed offsets like `+07:00` as a substitute for DST-aware timezones.

### 25.4. Do Not Mix Timezone Grouping with Timezone Filtering

Grouping by local day while matching by UTC day cuts off events at the start or end of the local day. Compute `startUtc` and `endUtc` from the requested local date.

## 26. Aggregating Amounts and Adjustment Events

Given `PaymentCaptured` (+) and `PaymentRefunded` (-), define net cash amount:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: {
        $in: ["PaymentCaptured", "PaymentRefunded"]
      },
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-12T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        day: {
          $dateTrunc: {
            date: "$occurredAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      net: { $sum: "$amount" },
      eventCount: { $sum: 1 }
    }
  },
  { $sort: { "_id.day": 1 } }
]);
~~~

Expected results for tenant-A:

- Nov 10 UTC: 125.50 + 75.00 + 10.00 = **210.50**.
- Nov 11 UTC: -20.00 = **-20.00**.

### 26.1. Do Not Sum Every eventType

If `OrderCreated` also has an `amount` field, summing across all eventTypes double-counts revenue. Define the exact list of events contributing to each metric.

### 26.2. Refunds Are Not Always Negative Numbers

A system might store refund `amount` as positive, requiring `$cond` to negate by eventType. Choose a consistent convention, test on real data, and version it.

### 26.3. Multi-Currency

Never add USD and VND into one `net` number. Group by `currency` or convert using an FX rate fixed at the business point in time, recording rate source and rounding rules.

## 27. Handling Missing Time Buckets and $densify

If a chart API needs 24 hourly buckets while events only occurred at 06:00, 08:00, and 11:00, standard aggregation results **do not** automatically generate empty buckets.

MongoDB 5.1+ supports `$densify`:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: "PaymentCaptured",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$occurredAt",
          unit: "hour",
          timezone: "UTC"
        }
      },
      total: { $sum: "$amount" }
    }
  },
  { $set: { hour: "$_id" } },
  { $project: { _id: 0, hour: 1, total: 1 } },
  {
    $densify: {
      field: "hour",
      range: {
        step: 1,
        unit: "hour",
        bounds: [
          ISODate("2026-11-10T00:00:00Z"),
          ISODate("2026-11-11T00:00:00Z")
        ]
      }
    }
  },
  {
    $set: {
      total: { $ifNull: ["$total", NumberDecimal("0")] }
    }
  },
  { $sort: { hour: 1 } }
]);
~~~

### 27.1. Watch Out for Bounds Semantics

`$densify` generates missing documents within the specified bounds; test start/end-of-day edge cases, MongoDB versions, and inclusive/exclusive bound semantics before shipping to a production API.

### 27.2. Never Generate Millions of Buckets Accidentally

Running `$densify` over a 10-year range with a 1-second step generates a massive document count. Bound query windows, step sizes, partitions, and output sizes.

### 27.3. Zero Differs from Missing

Transaction reports may treat no events as 0. However, in sensor telemetry, a missing measurement differs from 0°C. Do not default-fill 0 for every metric.

## 28. $fill and Discontinuous Telemetry Data

MongoDB 5.3+ provides `$fill`, including methods like `locf` (last observation carried forward) and `linear` where appropriate.

Example on an already densified series:

~~~javascript
{
  $fill: {
    sortBy: { measuredAt: 1 },
    output: {
      temperatureC: {
        method: "locf"
      }
    }
  }
}
~~~

### 28.1. Never Use LOCF for Monetary Events

A prior temperature may serve as an approximation per policy; “no transaction” never means carrying last hour's revenue forward into the next hour.

### 28.2. Linear Interpolation Has Limits

Do not interpolate faulty or expired data into “real” figures when the product must distinguish measured vs. estimated values. If interpolating, attach `isEstimated` metadata and the calculation method.

### 28.3. Users Must Know Metric Origin

Result tables should distinguish raw observations, rollups, imputed values, and corrections.

## 29. $setWindowFields: Running Totals and Moving Averages

MongoDB 5.0+ supports window functions.

Example computing a running total on **daily rollups**:

~~~javascript
db.daily_rollups.aggregate([
  { $match: { tenantId: "tenant-A", metric: "net-payments" } },
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: { bucketStart: 1 },
      output: {
        cumulativeNet: {
          $sum: "$net",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $project: {
      tenantId: 1,
      bucketStart: 1,
      net: 1,
      cumulativeNet: 1
    }
  }
]);
~~~

### 29.1. Partition by Tenant and Metric

Without partitioning, data from multiple tenants can get summed together. If the collection holds multiple metrics or currencies, partition and filter completely.

### 29.2. SortBy Does Not Guarantee Final Output Ordering

Per the docs, `$setWindowFields` does not guarantee final output order. If the API requires sorted results, append a `$sort` stage at the end of the pipeline.

### 29.3. Moving Averages on Measurements

You can use `$avg` with `documents:[-2,0]` to average the last three measurements. That is **3 observations**, not necessarily 3 minutes when data has gaps.

## 30. Distinguishing Raw Aggregations from Materialized Rollups

| Approach | Freshness | Query cost | Write/maintenance cost |
|---|---|---|---|
| Query raw events | Near real-time | Scales with events in the window | Less infrastructure |
| Query precomputed daily rollup | Has lag | Usually small | Needs rollup jobs |
| Incremental rollup via Change Streams | Near real-time | Small | Checkpoints/idempotency and replay |
| Offline warehouse analytics | Slower | Tuned for long-term reporting | ETL and synchronization |
| Mixed hot + archive query | Varies | Complex | Must merge data sources |

### 30.1. When Are Rollups Valuable?

If every dashboard opens 20 times per minute and scans 100 million events, precomputed hourly/daily rollups are usually far more efficient.

### 30.2. Raw Data Remains the Reconciliation Source

When business rules change or late events arrive, you must be able to recompute rollups from an authoritative source within the retention/archive window.

### 30.3. Metric Definitions Must Be Versioned

`net-payments-v1` and `net-payments-v2` may differ in refund rules. Never silently overwrite historical metrics without a migration and downstream notification.

## 31. Daily Batch Rollups with $merge

MongoDB aggregation provides `$merge` to upsert results into a materialized collection.

Example **recomputing** the UTC Nov 10 bucket for tenant-A:

~~~javascript
db.domain_events.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: {
        $in: ["PaymentCaptured", "PaymentRefunded"]
      },
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        bucketStart: {
          $dateTrunc: {
            date: "$occurredAt",
            unit: "day",
            timezone: "UTC"
          }
        }
      },
      net: { $sum: "$amount" },
      eventCount: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: {
        $concat: [
          "$_id.tenantId",
          ":net-payments:",
          {
            $dateToString: {
              date: "$_id.bucketStart",
              format: "%Y-%m-%d",
              timezone: "UTC"
            }
          }
        ]
      },
      tenantId: "$_id.tenantId",
      metric: { $literal: "net-payments" },
      bucketStart: "$_id.bucketStart",
      net: 1,
      eventCount: 1
    }
  },
  {
    $merge: {
      into: "daily_rollups",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

### 31.1. Why whenMatched: replace?

When recomputing the entire bucket from raw events, we want to replace the old result with the new total, **not add onto the previous run**. This makes reruns idempotent for unchanged source data and metric definitions.

### 31.2. What If There Are No Events?

A `$group` pipeline produces no output for an empty bucket. Consequently, `$merge` **does not automatically delete an old rollup** when all source events for a bucket are removed or corrected. Maintain an explicit reconciliation/deletion policy for empty buckets.

### 31.3. Never Blindly Add Incrementally

`$merge` with `whenMatched:"merge"` or `$inc` updates can double-count on job retries/replays. If using incremental updates, enforce per-event deduplication or atomic checkpoints.

### 31.4. Sharded Targets

When `daily_rollups` is sharded, `$merge` has version-specific requirements on unique indexes, `on` fields, and shard keys. Read the `$merge` reference and check target indexes before deploying.

## 32. Late-Arriving Events Alter Past Rollups

For example, event `evt-a-005` occurred on the 10th but arrived on the 12th. If the rollup for the 10th ran on the 11th, the old result was:

~~~text
PaymentCaptured: 125.50 + 75.00 = 200.50
~~~

After receiving the late event of 10.00, the correct result is:

~~~text
PaymentCaptured: 210.50
~~~

### 32.1. How to Handle It

- Use a rolling recomputation window, such as recomputing the last 7 days.
- Use a watermark on `receivedAt` and flag affected event-time buckets.
- Use a correction queue holding bucket keys needing recomputation.
- For extremely old late data, query from the archive and issue an audited restatement.

### 32.2. A Watermark Is Not the “Current Clock”

If the system waits up to 48 hours for events to arrive, a bucket is only “final” once the data-driven watermark passes that threshold. Define lateness SLAs and when corrections remain permitted.

### 32.3. Published Reports Need Restatement Semantics

A closed financial report should never silently alter historical numbers without a trace. Record report versions, correction events, approvals, and restatement timestamps per business rules.

## 33. Change Streams for Near-Real-Time Rollups

When fast updates are required, Change Streams can watch inserts into a regular event collection:

~~~text
Domain event inserted
       |
       v
MongoDB Change Stream
       |
       v
Consumer processor
       |
       +--> update rollup/projection
       |
       +--> persist resume token/checkpoint
~~~

### 33.1. Never Assume Exactly-Once

A consumer can process an event and crash before saving its token; upon restart, the event is replayed. If the consumer applies `$inc` again, the rollup double-counts.

### 33.2. Idempotency

Options:

- Unique processed-event keys in a separate collection.
- Atomic transactions writing both projection and checkpoint when both live in regular MongoDB collections.
- Recomputing the bucket from raw events when notified of a change.
- Version-based upserts.

### 33.3. Change Stream Tokens Do Not Live Forever

Resume tokens depend on oplog history. If downtime exceeds the oplog window, workers need rebootstrapping and reconciliation rather than calling `resumeAfter` endlessly.

### 33.4. Time-Series Specifics

Time-series changes/events and write transaction constraints differ from regular collections. Never assume you can apply the exact same atomic write+checkpoint pattern to time-series; check your server version and build appropriate derived materializations.

## 34. Outbox When Events Result from Business Transactions

Suppose a use case updates `orders` and emits `OrderPaid`. Writing the event to a regular MongoDB collection in the same transaction guarantees atomic intent:

~~~text
@Transactional:
  update orders.order-101
  insert domain_events (OrderPaid)
  insert outbox (publish intent)

Commit MongoDB

Async publisher:
  read outbox
  send broker
  mark delivered idempotently
~~~

### 34.1. Domain Events Do Not Automatically Publish to Kafka

A MongoDB transaction cannot roll back an HTTP call or external broker publish. Use an outbox and at-least-once delivery with consumer idempotency.

### 34.2. Never Hold a MongoDB Transaction Across Network I/O

Calling a payment gateway inside a transaction that later fails to commit leaves external side effects outside the DB. Design sagas/compensation when workflows span multiple services.

### 34.3. Time-Series Does Not Accept Writes in Transactions

When state+event must commit atomically, store domain events in a regular collection first; you can build downstream time-series projections/metrics afterward.

## 35. Compression, Storage, and Self-Managed Bucket Patterns

If individual events are tiny, document/index overhead can be significant. You can evaluate the bucket pattern:

~~~javascript
{
  _id: "device-7:2026-11-14T08",
  tenantId: "tenant-A",
  deviceId: "device-7",
  hourStart: ISODate("2026-11-14T08:00:00Z"),
  entries: [
    { second: 0, value: 27.3 },
    { second: 300, value: 27.8 }
  ]
}
~~~

### 35.1. Advantages

Reduces document count for vast numbers of tiny measurements and makes fetching a time window for a single device efficient.

### 35.2. Disadvantages

- Hot buckets suffer concurrent updates.
- Arrays can grow toward the document size limit.
- Hard to deduplicate individual entries.
- TTL deletes the entire bucket rather than individual events.
- Indexing nested events is harder.
- Requires extra validation and compaction code.

### 35.3. Built-In Time-Series Bucketing Is Usually Better When Applicable

MongoDB time-series already optimizes bucket storage. Only build a custom bucket pattern for specialized requirements that time-series cannot meet, and benchmark the trade-offs.

## 36. Aggregation Performance: Explaining Query Plans

Example:

~~~javascript
db.domain_events.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      eventType: "PaymentCaptured",
      occurredAt: {
        $gte: ISODate("2026-11-10T00:00:00Z"),
        $lt: ISODate("2026-11-11T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
    }
  }
]);
~~~

### 36.1. Signals to Inspect

- Does an index match the filter?
- `totalDocsExamined`, `totalKeysExamined`.
- How many input documents enter `$group`?
- Is there a blocking sort?
- Is there disk spilling?
- Actual p95/p99 under production-like workloads.
- Is there scatter-gather due to missing the shard key?

### 36.2. Do Not Tune Based on Tiny Datasets

With six lab events, the planner choosing a collection scan can be completely reasonable. Benchmark with representative data volumes and cardinalities.

### 36.3. Query Shapes Must Be Stable

Never log raw dynamic event payloads as metric labels; log query shapes, collections, anonymized tenant groups, and durations.

## 37. Memory Limits, Disk Spills, and Output BSON Size

A pipeline with `$group`/`$sort` over tens of millions of events can consume significant RAM. MongoDB enforces memory limits on blocking stages and supports spilling depending on stage, version, and configuration.

Example:

~~~javascript
db.domain_events.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    {
      $group: {
        _id: "$eventType",
        count: { $sum: 1 }
      }
    }
  ],
  { allowDiskUse: true }
);
~~~

### 37.1. allowDiskUse Does Not Make Unbounded Queries Cheap

Spilling to disk consumes I/O and can impact other workloads. First narrow time windows, reduce cardinality, add proper indexes, or use rollups.

### 37.2. Output Document Size

BSON document size is typically capped at 16 MiB for regular collections/results. Never group all events via `$push:"$$ROOT"` into a giant array expecting to return it in one document.

### 37.3. Cursors and Pagination

Aggregation results can be large; use cursor batch sizes, time/key pagination, or rollups. Avoid pulling months of raw data into JVM memory to group when MongoDB handles it better.

## 38. Indexing Rules for a Dashboard

Suppose a dashboard runs:

~~~javascript
{
  tenantId: "tenant-A",
  eventType: "PaymentCaptured",
  occurredAt: {
    $gte: start,
    $lt: end
  }
}
~~~

A suitable index is typically:

~~~javascript
{
  tenantId: 1,
  eventType: 1,
  occurredAt: 1
}
~~~

### 38.1. Equality First, Range After

When filtering equality on tenantId/eventType followed by a range on occurredAt, this compound index is usually favorable. However, actual workloads, selectivity, collations, and sort requirements may favor another layout.

### 38.2. Timelines Have Different Queries

Timelines filtering `tenantId + aggregateId` and sorting by time should use their own index rather than forcing all query types onto one index.

### 38.3. Hot Write Paths

Do not add a new index just to speed up a rarely run admin dashboard if it slows down all writes. Consider rollups or archive queries instead.

### 38.4. Indexing by Date String?

Do not store only `dateKey:"2026-11-10"` and drop the original Date. A date key can help rollups, yet timezone or policy changes render old keys ambiguous.

## 39. Java Sync Driver: Idempotent Event Insert

Java 17+ example using the MongoDB Java Sync Driver:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Date;

public final class EventWriter {

    private final MongoCollection<Document> events;

    public EventWriter(MongoCollection<Document> events) {
        this.events = events;
    }

    public void recordPayment(String tenantId, String eventId,
                              String orderId, BigDecimal amount) {

        Document event = new Document("_id", eventId)
            .append("tenantId", tenantId)
            .append("eventId", eventId)
            .append("aggregateId", orderId)
            .append("aggregateVersion", 1L)
            .append("eventType", "PaymentCaptured")
            .append("schemaVersion", 1)
            .append("occurredAt", Date.from(Instant.now()))
            .append("receivedAt", new Date())
            .append("amount", new Decimal128(amount));

        try {
            events.insertOne(event);
        } catch (MongoWriteException ex) {
            if (ex.getError().getCode() == 11000) {
                // Duplicate ID: reconcile payload/business invariants.
                // Never assume every duplicate is a success.
                return;
            }
            throw ex;
        }
    }
}
~~~

### 39.1. Duplicate Keys Must Verify Payload

If the same eventId arrives with a different payload, this may be a data-integrity incident rather than a valid idempotent retry. Compare event hashes/versions/tenants and raise an error on conflicting content.

### 39.2. Global IDs in Sharded Deployments

The `_id=eventId` example assumes producer-controlled unique eventIds. When sharding by a tenant key other than `_id`, account for MongoDB's `_id` uniqueness locality. Design schemas/unique indexes compatible with the shard-key prefix, or enforce global uniqueness outside the sharded collection.

### 39.3. Timestamps from the JVM Clock

`Instant.now()` depends on the application server's clock. When event time matters, monitor clock sync and distinguish time sources (business source vs. ingest server). Never substitute ObjectId timestamps for all business timelines.

## 40. Java Driver: Querying History by Time Range

~~~java
import static com.mongodb.client.model.Filters.*;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;

public final class EventHistoryReader {

    private final MongoCollection<Document> events;

    public EventHistoryReader(MongoCollection<Document> events) {
        this.events = events;
    }

    public void printTimeline(String tenantId,
                              String aggregateId,
                              Instant start,
                              Instant end) {

        events.find(and(
                eq("tenantId", tenantId),
                eq("aggregateId", aggregateId),
                gte("occurredAt", Date.from(start)),
                lt("occurredAt", Date.from(end))
            ))
            .sort(Sorts.ascending("occurredAt", "_id"))
            .limit(100)
            .forEach(doc -> {
                System.out.println(
                    doc.getString("eventType") + " " +
                    doc.getDate("occurredAt"));
            });
    }
}
~~~

### 40.1. Pagination

`limit(100)` alone does not provide stable pagination. For long timelines, use a keyset cursor based on `occurredAt` + `_id`, compute next-page predicates, and keep sorts and indexes aligned.

### 40.2. Never Log Full Event Payloads

Printing eventType/time is a lab example. Production requires redaction and tenancy guards; never dump customer data to stdout just for debugging.

## 41. Java Driver: Daily Aggregation

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Filters;
import org.bson.Document;

import java.time.Instant;
import java.util.Arrays;
import java.util.Date;

public class DailyEventCounter {

    public void report(MongoCollection<Document> events,
                       String tenantId,
                       Instant from,
                       Instant toExclusive) {

        events.aggregate(Arrays.asList(
            Aggregates.match(Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.gte("occurredAt", Date.from(from)),
                Filters.lt("occurredAt", Date.from(toExclusive))
            )),
            new Document("$set", new Document("day",
                new Document("$dateTrunc", new Document("date", "$occurredAt")
                    .append("unit", "day")
                    .append("timezone", "UTC")))),
            Aggregates.group("$day", Accumulators.sum("count", 1)),
            Aggregates.sort(new Document("_id", 1))
        )).forEach(System.out::println);
    }
}
~~~

### 41.1. Schema Versions and Null Guards

If an event lacks occurredAt or has the wrong type, dateTrunc can return null or error out. Use schema validation and data quality checks at ingestion instead of merely filtering out bad records and claiming totals are complete.

### 41.2. Align Dependency Versions

Driver builder APIs/aggregation support depend on the application's dependency versions. Use the MongoDB Java Driver version managed by the Spring Boot BOM when integrating Spring, and verify compatibility with MongoDB server/operator versions.

## 42. Spring Data MongoDB: Event Entity

Example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.index.CompoundIndexes;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("domain_events")
@CompoundIndexes({
    @CompoundIndex(
        name = "ix_tenant_aggregate_time",
        def = "{'tenantId':1, 'aggregateId':1, 'occurredAt':1, '_id':1}"
    ),
    @CompoundIndex(
        name = "ix_tenant_type_time",
        def = "{'tenantId':1, 'eventType':1, 'occurredAt':1}"
    )
})
public class DomainEvent {

    @Id
    private String id;

    private String tenantId;
    private String aggregateId;
    private long aggregateVersion;
    private String eventType;
    private int schemaVersion;
    private Instant occurredAt;
    private Instant receivedAt;

    protected DomainEvent() {
    }

    // Constructors/getters and payload mapping per domain logic.
}
~~~

### 42.1. Index Annotations Are Not a Migration Plan

In production, never leave auto-index creation enabled by default without assessing index build times, unique violations, and write impacts. Manage indexes via a dedicated migration pipeline.

### 42.2. Timestamp Mapping

Spring Data Java Time types provide converters to BSON Date. Ensure consistent UTC/timezone handling; an `Instant` carries no local timezone like `ZonedDateTime` does.

### 42.3. Repositories Do Not Solve Every Aggregation

`MongoRepository` fits simple CRUD/queries. For complex pipelines or rollups, use `MongoTemplate.aggregate`, Aggregation builders, or tested driver APIs.

## 43. Spring Data MongoDB: Aggregating with MongoTemplate

Example Spring Data code:

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;
import org.bson.Document;

import java.time.Instant;
import java.util.Date;

public class EventReportService {

    private final MongoTemplate template;

    public EventReportService(MongoTemplate template) {
        this.template = template;
    }

    public AggregationResults<Document> countByType(
            String tenantId, Instant from, Instant to) {

        Aggregation pipeline = newAggregation(
            match(Criteria.where("tenantId").is(tenantId)
                .and("occurredAt").gte(Date.from(from))
                .lt(Date.from(to))),
            group("eventType").count().as("eventCount"),
            sort(org.springframework.data.domain.Sort.Direction.DESC,
                "eventCount")
        );

        return template.aggregate(
            pipeline, "domain_events", Document.class
        );
    }
}
~~~

### 43.1. Never Bypass Tenant Authorization

MongoTemplate does not verify which tenant a user belongs to. The service must authorize `tenantId` or derive tenant context from the authenticated principal rather than trusting raw request parameters.

### 43.2. Spring Boot Config Prefixes

Spring Boot 3.5 uses `spring.data.mongodb.uri`. Spring Boot 4.x uses `spring.mongodb.uri` per its documentation. An app connecting to the wrong cluster should never be patched by modifying report data.

## 44. Event Schema Validation

MongoDB provides `$jsonSchema` validators to reject malformed documents in regular collections.

Example requiring minimal fields:

~~~javascript
db.runCommand({
  collMod: "domain_events",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "eventId",
        "eventType",
        "occurredAt",
        "receivedAt",
        "schemaVersion"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        eventId: { bsonType: "string" },
        eventType: { bsonType: "string" },
        occurredAt: { bsonType: "date" },
        receivedAt: { bsonType: "date" },
        schemaVersion: {
          bsonType: "int",
          minimum: 1
        }
      }
    }
  },
  validationAction: "error"
});
~~~

This validator update is **only for a prepared lab**. In production, migration review is required and legacy data must be compatible before running `collMod`.

### 44.1. Numeric Version Type

`schemaVersion` can use int or long, provided the contract is consistent. The validator above requires int.

### 44.2. Conditional Fields

If `PaymentCaptured` requires amount/currency while `OrderCreated` does not, use conditional validation, a schema registry, application checks, or separate event types/collections as appropriate.

### 44.3. Schema Validation Does Not Replace Security

A validator does not stop an authorized admin from deleting documents or prevent sensitive data from landing in an arbitrary payload field if the schema permits it. Enforce RBAC and data minimization.

## 45. Measuring and Governing Event Ingestion

Useful signals:

~~~text
events_ingested_total{eventType}
events_rejected_total{reason}
events_duplicate_total
events_schema_invalid_total
events_late_arrivals_total
events_ingestion_lag_seconds
events_write_latency_seconds
events_rollup_lag_seconds
events_archive_backlog
events_retention_backlog
events_size_bytes
events_ttl_deleted_total
~~~

These names are illustrative **custom application metrics**; they are not built into MongoDB by default.

### 45.1. Calculating Ingest Lag

~~~text
ingestion lag = receivedAt - occurredAt
~~~

If source clocks are unsynchronized, the result can be negative; validate clocks and attach quality flags.

### 45.2. TTL Monitor Metrics

MongoDB `serverStatus` exposes counters under `metrics.ttl` depending on version, such as deletedDocuments/passes/subPasses. Track deletion rates, backlogs, storage, and expiration distributions; counters reset on process restarts.

### 45.3. Signs of Aggregation Regressions

Monitor query durations, documents examined, scan/return ratios, disk spills, cache/disk I/O, index usage, and dashboard p95/p99.

### 45.4. High-Cardinality Metrics

Never use `eventId`, arbitrary `tenantId`, or `aggregateId` as Prometheus labels on every event. Unique time-series metric cardinality can explode.

## 46. Verifying Retention Without Waiting for Instant TTL Deletion

In the lab:

~~~javascript
const now = new Date();

db.transient_events.countDocuments({
  expiresAt: {
    $lte: now
  }
});
~~~

This number measures **documents currently past expiration that still exist**, not proof that the TTL monitor is broken. Compare it against monitor activity, workload, and wait intervals.

### 46.1. Test TTL with Reasonable Time Bounds

Never assert “an expired document must disappear within 50 milliseconds”. Use a configurable wait-until deadline and report actual observed lag.

### 46.2. Testing Time-Series TTL Differs

With time-series buckets, an old measurement can persist until the **entire bucket** becomes eligible. Tests must account for bucket span and granularity rather than individual measurement timestamps alone.

### 46.3. Testing Policy Changes

If shortening retention makes millions of documents immediately eligible, test resource impact in staging first; never run destructive production experiments.

## 47. Data Correctness: Backfills, Replays, and Deduplication

Reliable event analytics must handle:

| Phenomenon | Impact | Solution |
|---|---|---|
| Producer retry | Duplicate event | Stable eventId + unique key/dedup |
| Network partition | Late arrival | Event time + ingest time |
| Out-of-order delivery | Wrong projection | Aggregate version/ordering |
| Business correction | Stale past reports | Correction event + recompute |
| Consumer crash | Event replay | Idempotent processor |
| Oplog history loss | Stream gap | Rebootstrap/reconciliation |
| Schema v1/v2 | Parse/metric drift | Schema version/upcaster |
| Clock skew | Wrong time bucket | Time sync and quality flags |
| TTL earlier than archive | Lost history | Archive-first workflow |
| Legal hold | Deletion conflict | Governed hold store/policy |
| Multi-currency | Meaningless sums | Group currency/FX policy |

### 47.1. Immutable Events vs. Updatable Projections

Raw events are append-only, whereas `daily_rollups` is derived state and can be `replace`d on recomputation. Never confuse updating a rollup with rewriting raw history.

### 47.2. Replays Can Trigger Side Effects

Re-running an aggregator from raw events is safe when outputs are written deterministically. Re-running an event consumer that sends emails/SMS/charges cards requires idempotency or disabling external side effects in replay mode.

## 48. Test Plan for Event Design

| Test | Input | Assertion |
|---|---|---|
| Insert new event | Valid event ID | One document |
| Duplicate event | Same eventId/payload | No duplication |
| Conflicting duplicate | Same ID, different payload | Incident/conflict |
| Timeline | Event versions 1,2,3 | Sorted, no gaps |
| Half-open range | Exact boundary time | No double-counted buckets |
| Late event | Old occurredAt, new receivedAt | Counted in old bucket |
| Mixed currency | USD/VND | Never summed blindly |
| Refund | Negative adjustment | Accurate net |
| Timezone | Local midnight | Correct UTC interval |
| DST | 23h/25h day | Accurate calendar buckets |
| TTL Date | expiresAt BSON Date | Eventual deletion |
| TTL string | expiresAt string | Validation rejects |
| Time-series TTL | Partially valid bucket | Deleted only when bucket eligible |
| Rollup rerun | Job run twice | No double counting |
| Rollup late correction | Late-arriving event | Results restated |
| Archive verify | Export + checksum | Counts/invariants pass |
| Legal hold | Held record | Never deleted by workflow |
| Sharded uniqueness | Shard-key prefix | Constraint enforced |
| Query performance | Production-scale samples | p95 and scan ratio within thresholds |
| History loss | Stale Change Stream token | Reconcile, never falsely report caught-up |

### 48.1. Testcontainers and Environments

Use a replica set when testing transactions or change streams. Time-series features, TTL, and aggregations require compatible MongoDB Server versions with pinned container images.

### 48.2. Never Use Real Production Data

Use test tenants, generated event IDs, and PII-free datasets. Fault injection and TTL retention experiments belong strictly in authorized labs.

## 49. Common Anti-Patterns

| Mistake | Why it is wrong | Replace with |
|---|---|---|
| Overwriting old events | History lost | Append corrections |
| Using Change Streams as an archive | Finite oplog | Regular event store/archive |
| Storing only string timestamps | Hard queries/timezones | BSON Date |
| Storing only receivedAt | Cannot distinguish late data | occurredAt + receivedAt |
| TTL from occurredAt ignoring late arrivals | Backfilled events deleted immediately | Explicit retention policy |
| Assuming TTL deletes immediately | Background monitor | Accept eventual cleanup |
| Compound TTL index | Unsupported | Single Date-field TTL |
| Time-series for unique event ledger | Unique indexes unsupported | Regular collection |
| Writing time-series in a transaction | Unsupported | Regular source-of-truth |
| Putting varying eventId in metaField | Bucket fragmentation | Stable metadata |
| Grouping by UTC while labeling local | Wrong daily reports | Align timezones |
| Summing all eventTypes | Double counting | Explicit metric semantics |
| Adding USD+VND | Wrong totals | Group by currency |
| `$inc` on every Change Stream replay | Double counting | Dedup/atomic checkpoint |
| `$merge` merge on batch recompute | Keeps stale numbers | Deterministic replace |
| Never cleaning empty rollups | Stale metrics | Reconciliation |
| Indexing only occurredAt | Slow tenant queries | Suitable compound index |
| Too many indexes | Write amplification | Workload-driven indexes |
| Unbounded `$densify` | Output explosion | Bounded window/step |
| Long aggregations behind live APIs | High latency | Materialize/async |
| Ignoring backup retention | Incomplete deletion | Full-lifecycle governance |
| Ad-hoc null for legal holds | Hard to audit | Explicit hold policy |
| Archiving without verification | Data loss | Checksums/counts/restore drills |
| Finalizing numbers in a single batch | Late corrections missed | Watermark/restatement policy |

## 50. Production Checklist for Event Data

### Model and Schema

- [ ] Classified domain/audit/telemetry/CDC events.
- [ ] Stable event IDs and tenant/aggregate identities defined.
- [ ] `schemaVersion` and contract evolution policy in place.
- [ ] `occurredAt` and `receivedAt` clearly defined.
- [ ] Timestamps use BSON Date with UTC storage.
- [ ] Decimal128 or proper numeric model for money.
- [ ] No unnecessary secrets/PII in payloads.
- [ ] Correction/compensation semantics defined.
- [ ] Idempotency under retries and replays.
- [ ] Unique/shard-key design verified.

### Storage and Retention

- [ ] Regular vs. time-series chosen based on constraints.
- [ ] Time-series limits on uniqueness/transactions/updates understood.
- [ ] Single-field Date TTL or collection TTL configured appropriately.
- [ ] TTL deletion lag accepted and monitored.
- [ ] Schema validation enforced on expiry fields.
- [ ] Late arrivals protected from unintended immediate deletion.
- [ ] Backup/archive/legal hold policies aligned.
- [ ] Archives verified prior to hot deletion.
- [ ] Restore drills and checksums validated.
- [ ] Owner and approval required for retention changes.

### Queries and Analytics

- [ ] Queries always apply proper tenant/time filters.
- [ ] Half-open time ranges used consistently.
- [ ] Grouping via dateTrunc with the proper timezone.
- [ ] Business metrics specify event types, units, and currencies.
- [ ] Handling defined for empty buckets and data quality issues.
- [ ] Indexes aligned with timeline/reporting workloads.
- [ ] Explain/profiler/performance measured on representative datasets.
- [ ] No excessive memory/disk spills.
- [ ] Rollups in place for long-range/frequent dashboards.
- [ ] Rollup reruns and late corrections tested.

### Systems and Operations

- [ ] Change Streams use resume tokens/checkpoints when used.
- [ ] Consumers enforce idempotency/fencing.
- [ ] Oplog window and lag monitored.
- [ ] Data correctness tested after failover/restart.
- [ ] Metrics for ingestion, rollups, archival, and TTL.
- [ ] Alerts for latency, backlogs, and retention anomalies.
- [ ] RBAC restricts writes/updates/deletes.
- [ ] Auditing and data privacy policies enforced.
- [ ] Runbooks ready for backfill/replay/recompute.
- [ ] Owner/incident procedures defined for data loss.

## 51. Hands-On Exercises

Run TTL creation/deletion, data inserts, and schema changes only on a lab MongoDB instance.

### Exercise 1 — Classifying Event Types

Compare domain events, audit events, telemetry measurements, and MongoDB change streams.

### Exercise 2 — State vs. History

An order is currently SHIPPED. Which questions require event history rather than reading order status alone?

### Exercise 3 — Event Identity

Design a stable eventId across producer retries that prevents duplicate inserts.

### Exercise 4 — Tenant Isolation

An event collection serves 100 tenants. Design fields/queries so no other tenant's data leaks.

### Exercise 5 — Event Time vs. Ingest Time

A device records an event at 09:00 and uploads it at 12:00. Which field should a daily dashboard use?

### Exercise 6 — SchemaVersion

Create two versions of PaymentCaptured and a backward-compatible consumer strategy.

### Exercise 7 — Correction

A payment recorded the wrong amount. Why can appending an AdjustmentPosted event be better than editing the original event?

### Exercise 8 — Money

Explain why binary floating point introduces errors when summing money; how is Decimal128 used?

### Exercise 9 — Regular vs. Time-Series

An audit event requires a unique ID and a transaction alongside an order. Which collection type do you choose?

### Exercise 10 — Time-Series Constraints

Why can't you put a unique index on eventId in a time-series collection?

### Exercise 11 — Basic TTL

Create a TTL index on expiresAt Date with expireAfterSeconds:0.

### Exercise 12 — TTL Delay

Why does an event that just expired not necessarily vanish instantly?

### Exercise 13 — Invalid TTL Values

If expiresAt is a string or missing, what goes wrong with deletion?

### Exercise 14 — Late Arrivals and Retention

An event from 45 days ago is ingested today with a 30-day TTL from occurredAt. What can happen?

### Exercise 15 — Partial TTL

Separate debug events and audit events with different lifetimes; design a safe collection/policy.

### Exercise 16 — Legal Hold

An event is reaching TTL expiry while under a legal hold. Design a workflow preventing deletion and recording approval.

### Exercise 17 — Archive-First

List the verification gates required before deleting hot data after export.

### Exercise 18 — Backup vs. Archive

Why does a backup snapshot not equate to a long-term queryable/replayable archive?

### Exercise 19 — Time-Series Bucket Expiry

A bucket holds measurements at 08:00, 08:20, and 08:55. Why is the bucket not deleted when the 08:00 record expires?

### Exercise 20 — Time-Series Meta

Select stable metadata for device measurements and identify fields that must not go into meta.

### Exercise 21 — Sharding

If unique {tenantId,eventId} is required, how must the shard key relate to the unique index?

### Exercise 22 — Timeline Index

Design an index for tenantId + aggregateId + occurredAt and explain sorting.

### Exercise 23 — Reporting Index

Design an index for tenantId + eventType + time range.

### Exercise 24 — Half-Open Intervals

Why use `$gte start` and `$lt end` instead of 23:59:59?

### Exercise 25 — Aggregate Count

Count PaymentCaptured per hour using `$match`, `$group`, and `$dateTrunc`.

### Exercise 26 — Net Amount

From the lab dataset, compute tenant-A's net amount for UTC Nov 10 and Nov 11.

### Exercise 27 — Multi-Currency

Explain why summing USD+VND is meaningless without an FX conversion policy.

### Exercise 28 — Local Timezone

Which calendar day in Vietnam does a 23:30 UTC event belong to? Write the matching dateTrunc timezone.

### Exercise 29 — DST

Why can a local calendar day be other than 24 hours long?

### Exercise 30 — Missing Buckets

A chart has no measurement at 07:00. When should you fill 0 vs. return missing?

### Exercise 31 — $densify

Densify hourly over one day; what bounds prevent output explosion?

### Exercise 32 — $fill

Compare last-observation-carried-forward and linear interpolation.

### Exercise 33 — Running Total

Use `$setWindowFields` on daily rollups to compute cumulative net payments.

### Exercise 34 — Batch Rollup

Use `$merge` with whenMatched=replace to recompute daily buckets without double counting on retries.

### Exercise 35 — Empty Buckets

If all source events for a day are corrected/removed, why doesn't `$merge` delete the stale rollup automatically?

### Exercise 36 — Late Events

An event from the 10th arrives on the 12th. Design a recompute/restatement strategy.

### Exercise 37 — Change Stream Replay

A consumer increments a rollup and crashes before saving its checkpoint. What mechanism prevents double counting?

### Exercise 38 — Oplog History Loss

Consumer downtime exceeds the oplog window. Can you recover the old token simply by retrying forever?

### Exercise 39 — Outbox

Design a transaction updating an order and writing event/outbox records in regular collections.

### Exercise 40 — Performance

Explain the differences between docsExamined, keysExamined, query duration, and disk spills.

### Exercise 41 — Projection Access Control

Producers only need insert; report readers only need find. Why not share a root account?

### Exercise 42 — Java Driver

Write an event insert with a stable ID and distinguish valid duplicate retries from duplicate payload conflicts.

### Exercise 43 — Spring Data

Create a DomainEvent entity with occurredAt and an aggregation query by tenant/time.

### Exercise 44 — Observing TTL

Write a script counting events past expiresAt that still exist. Why shouldn't you immediately conclude TTL is broken?

### Exercise 45 — Test Plan

Propose positive/negative tests for unique IDs, time boundaries, timezones, late data, retention, and rollups.

### Exercise 46 — Comprehensive Architecture Design

Design a system processing one billion order/payment events per month with:

- Raw MongoDB regular event collection.
- Tenant/aggregate identities and uniqueness.
- 90-day hot retention, long-term archival.
- TTL and legal hold workflows.
- Atlas/self-managed backup strategy.
- Timeline and reporting indexes.
- Daily materialized rollups.
- Late arrivals and restatements.
- Java/Spring Data ingestion.
- Monitoring, SLOs, deduplication, and replay.
- Data privacy and restoration drills.

## 52. Summary

A reliable MongoDB event data design must simultaneously solve **history storage**, **retention**, and **aggregation**:

1. **History:** Events have stable IDs, tenant/aggregate identities, event/ingest timestamps, schema versions, and minimal payloads. Correct history with compensation/adjustment events rather than silent overwrites.
2. **Collection choice:** Regular collections fit domain/audit/transactional events; time-series collections fit dense measurements while imposing limits on unique indexes, updates, and transaction writes.
3. **Retention:** TTL indexes or time-series `expireAfterSeconds` are non-instantaneous background deletions. True lifecycle management requires archive-first workflows, backup/retention alignment, legal holds, and data privacy controls.
4. **Queries:** Use tenant + time filters, `[start,end)` intervals, BSON Dates/UTC, `$dateTrunc` with timezones, and explicit business metric semantics; never mix event types or currencies blindly.
5. **Aggregations:** Frequent dashboards should rely on recomputable rollups. Deterministic `$merge` avoids double counting; late events demand watermark and restatement policies.
6. **Operations:** Change Streams are near-real-time event feeds, not archives; build idempotent consumers, checkpoints, oplog headroom, tests, and reconciliation.
7. **Security:** Application-level append-only behavior, least-privilege RBAC, auditing, encryption, and retention policies must be designed together.

**Quick rule of thumb:** *Store events to preserve what actually happened; enforce retention to govern the lifecycle; build rollups to answer fast—but all three are only trustworthy when they share the exact same definitions of time, identity, and correctness.*

## Official References

- [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/)
- [MongoDB Manual — Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB Manual — Time Series Indexes](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-index/)
- [MongoDB Manual — Automatic Removal for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Indexing Strategies](https://www.mongodb.com/docs/manual/applications/indexes/)
- [MongoDB Manual — Unique Indexes and Sharding](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Manual — $dateTrunc](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateTrunc/)
- [MongoDB Manual — $densify](https://www.mongodb.com/docs/manual/reference/operator/aggregation/densify/)
- [MongoDB Manual — $fill](https://www.mongodb.com/docs/manual/reference/operator/aggregation/fill/)
- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — $merge](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
- [Spring Data MongoDB — Aggregation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html)
