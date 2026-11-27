# Migrating from Relational Data to Document Models by Access Patterns in MongoDB

Moving from a relational database such as PostgreSQL/MySQL to MongoDB is **not** turning every table into a collection, every row into a document, and keeping every JOIN intact. Doing that usually just carries old access patterns onto a new engine, forcing the application to issue many small queries without leveraging document boundaries.

The right starting point is **access patterns**: which data users read together, which operations require atomic writes, which data grows unboundedly, which parts must reflect current state, and which parts must preserve historical snapshots. Only then decide whether to embed, reference, store snapshots, or build read models.

This lesson belongs to the **Data Evolution** chapter of the **Database Engine Document MongoDB** module, presenting a practical approach to model migration with a vehicle-rental booking example, index design, consistency handling, backfill, CDC, verification, and cutover.

**Safety scope:** SQL, `mongosh`, and Java snippets are examples for isolated test environments. Never run migration commands, bulk updates, or write-source switches in production without a change plan, backups, a rollback plan, and formal approval.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Interpret a relational schema through the lens of API and read/write workloads.
2. Build an access-pattern inventory covering filters, sorts, cardinality, frequency, and consistency needs.
3. Choose document boundaries from lifecycles and co-accessed/co-mutated data.
4. Distinguish embedding, referencing, snapshots, and derived read models.
5. Avoid unbounded arrays, write amplification, and BSON document size limits.
6. Translate certain SQL JOINs and GROUP BYs into MongoDB queries or aggregations.
7. Design indexes aligned with access patterns and tenant isolation.
8. Identify invariants not protected by single-document atomicity alone.
9. Map SQL identifiers, dates, numeric types, nulls, and related rows into BSON.
10. Design backfill + CDC pipelines with idempotency, ordering, reconciliation, and rollback.
11. Plan schema evolution with versioning and expand–migrate–contract.
12. Test performance and business behavior before and after cutover.

## 2. Differences Between Relational and Document Models

RDBMSs center on tables, rows, constraints, and foreign-key relationships. Normalization avoids storing duplicate copies of the same data.

~~~text
customers ---- bookings ---- vehicles
                    |
                    +---- booking_addons
                    |
                    +---- payment_events
~~~

To render a booking detail page, SQL typically JOINs multiple tables.

MongoDB lets you represent items **frequently accessed together** inside one document:

~~~text
bookings document
  |
  +-- booking ID, tenant, status
  +-- rental period
  +-- customer snapshot
  +-- vehicle snapshot
  +-- booked addons
  +-- agreed price
  +-- payment summary
~~~

Meanwhile, customer master data, vehicle master data, and payment audit events can still live in separate collections.

### 2.1. There Is No Contest to Eliminate Every JOIN

MongoDB offers references and `$lookup` aggregations. Use them when they are the right choice for correctness and workload. The goal is reducing complexity and round trips on **hot paths**, not achieving “zero JOINs.”

### 2.2. Not Every Table Needs Its Own Collection

Join/line-item tables can become embedded arrays when bounded and lifecycle-coupled. Conversely, one large table may split into multiple collections by lifecycle, archival, and query patterns.

### 2.3. One Domain Can Have Multiple Read Models

Canonical booking data can reside in `bookings`, while a tenant dashboard maintains separately materialized summaries. Clearly define the source of truth and synchronization strategy.

## 3. Initial Relational Schema Example

A simplified vehicle-rental booking schema:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE vehicles (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    plate VARCHAR(40) NOT NULL,
    category VARCHAR(40) NOT NULL,
    current_rate_minor BIGINT NOT NULL
);

CREATE TABLE bookings (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    customer_id BIGINT NOT NULL,
    vehicle_id BIGINT NOT NULL,
    start_at TIMESTAMP NOT NULL,
    end_at TIMESTAMP NOT NULL,
    status VARCHAR(40) NOT NULL,
    total_minor BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE booking_addons (
    id BIGINT PRIMARY KEY,
    booking_id BIGINT NOT NULL,
    addon_code VARCHAR(50) NOT NULL,
    quantity INT NOT NULL,
    unit_minor BIGINT NOT NULL
);

CREATE TABLE payment_events (
    id BIGINT PRIMARY KEY,
    booking_id BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    provider_ref VARCHAR(128),
    event_type VARCHAR(40) NOT NULL,
    amount_minor BIGINT NOT NULL,
    happened_at TIMESTAMP NOT NULL
);
~~~

This is illustrative and omits all real FKs, indexes, and unique constraints.

### 3.1. You Cannot Derive a MongoDB Model from an ERD Alone

You must know the maximum add-ons per booking, how the app reads booking details, vehicle rate volatility, payment/refund frequency, how orphan references are handled, and audit requirements.

### 3.2. Reading the Schema to Spot Invariants

- A booking must belong to a verified tenant.
- Customer and vehicle must belong to permitted tenants.
- `start_at < end_at`.
- Monetary amounts must be computable and properly typed.
- No double-booking a vehicle under business rules.
- Payment records must reconcile with the payment provider.

SQL foreign keys and transactions may currently protect some of these rules. Moving to MongoDB, specify which actor or mechanism enforces each invariant.

## 4. Build an Access-Pattern Inventory Before Designing

Example:

| Pattern | Query or Operation | Frequency | Required Data | Characteristics |
| --- | --- | --- | --- | --- |
| AP1 | GET booking detail | Very high | Booking, vehicle, customer, add-ons | By ID |
| AP2 | Customer booking history | High | Dates, status, amount | Filter/sort/page |
| AP3 | Tenant booking feed | High | Summary, status | Filter/sort/page |
| AP4 | Check vehicle availability | High | Rental period, active holds | Race-sensitive |
| AP5 | Change booking status | High | State/version | Conditional write |
| AP6 | Update customer profile | Medium | Current customer | Independent write |
| AP7 | Payment event audit | Medium | Event history | Unbounded |
| AP8 | Revenue report | Medium | Amount by day/status | Aggregate |
| AP9 | Update vehicle list price | Low | Current rate | Master data |
| AP10 | Investigate refund/dispute | Low | Payment lifecycle | Strong audit |

Frequencies are illustrative. In a real project, measure via logs, tracing, and DB metrics.

### 4.1. Access Pattern Description Template

~~~yaml
id: AP1
name: "Booking detail"
input:
  tenantId: "verified auth context"
  bookingId: "path parameter"
output:
  - dates
  - status
  - vehicle snapshot
  - customer snapshot
  - selected addons
  - agreed total
consistency: "current booking state"
cardinality: 1
readFrequency: high
writeFrequency: medium
latencyObjective: "per API SLO"
~~~

### 4.2. Capture Write Patterns Too

Optimizing reads alone tempts you to embed too much master data, forcing every profile edit to update thousands of bookings. Know which actor owns each field, when it changes, and how often.

### 4.3. Rare Queries Still Matter

Compliance audits or refund investigations may be infrequent yet carry strict data and retention rules. Never omit them from your model.

## 5. Analyzing a Hot SQL JOIN

The booking details page may run:

~~~sql
SELECT b.id, b.tenant_id, b.status,
       b.start_at, b.end_at, b.total_minor,
       c.display_name, v.plate, v.category
FROM bookings b
JOIN customers c ON c.id = b.customer_id
JOIN vehicles v ON v.id = b.vehicle_id
WHERE b.tenant_id = :tenantId
  AND b.id = :bookingId;
~~~

Then the service loads `booking_addons`.

If the API uses these fields on nearly every request, there is a strong case for storing **contractual snapshots and bounded add-ons** inside the booking document.

### 5.1. Do Not Embed the Entire Customer

A profile may hold emails, preferences, addresses, and sensitive fields unnecessary for booking details. Copy only fields needed for the contract and history.

### 5.2. Do Not Embed the Entire Vehicle

A vehicle may carry telemetry, maintenance logs, and thousands of booking references. A booking needs only `vehicleId` plus attributes locked in at booking time.

### 5.3. Historical Data vs. Current Data

The customer name or rate **at booking time** often must stay frozen. If the UI needs live master state, query the reference separately or maintain a derived field with a clear sync contract.

## 6. Proposed Booking Document

~~~javascript
{
  _id: "tenant-a:booking:1001",
  tenantId: "tenant-a",
  sourceBookingId: NumberLong(1001),
  bookingNumber: "BK-2026-1001",

  customerId: "tenant-a:customer:42",
  customerSnapshot: {
    displayName: "Sample Customer"
  },

  vehicleId: "tenant-a:vehicle:7",
  vehicleSnapshot: {
    category: "sedan",
    plate: "TEST-123",
    dailyRateMinor: NumberLong(700000)
  },

  period: {
    startAt: ISODate("2026-11-18T02:00:00Z"),
    endAt: ISODate("2026-11-20T02:00:00Z")
  },

  addons: [
    {
      code: "baby-seat",
      quantity: 1,
      unitMinor: NumberLong(100000)
    }
  ],

  amount: {
    subtotalMinor: NumberLong(1400000),
    addonMinor: NumberLong(100000),
    totalMinor: NumberLong(1500000),
    currency: "VND"
  },

  status: "CONFIRMED",
  paymentSummary: {
    status: "AUTHORIZED"
  },

  version: 1,
  schemaVersion: 2,
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  updatedAt: ISODate("2026-11-14T03:00:00Z")
}
~~~

### 6.1. Canonical Fields

- Booking status, dates, addons, and agreed amount belong to `bookings`.
- Current customer profile belongs to `customers`.
- Current vehicle attributes/rates belong to `vehicles`.
- Verified payment events belong to `paymentEvents` or the payment ledger.
- `paymentSummary` is a read model/derived field if explicitly defined as such.

### 6.2. Intentional Snapshots

A vehicle rate hike next month does not change the price agreed on an older booking. Keeping `vehicleSnapshot.dailyRateMinor` is right when that matches business rules.

### 6.3. MongoDB Does Not Enforce Cross-Collection Foreign Keys Automatically

A booking referencing a `customerId` from another tenant could be saved unless application logic, transactions, or workflows prevent it. Design explicit reference validation.

## 7. Embedding: When Is It Beneficial?

Favor embedding when:

- Data is regularly read alongside the parent.
- Element count is small and genuinely bounded.
- Child items share the parent's lifecycle.
- Parent and child mutations need single-document atomicity.
- Children are rarely queried independently.
- Document size will not grow unboundedly.

Example: bounded addons inside a booking.

~~~javascript
{
  _id: "bk-1001",
  addons: [
    { code: "baby-seat", quantity: 1 },
    { code: "insurance-plus", quantity: 1 }
  ]
}
~~~

### 7.1. Document-Level Atomic Updates

One `updateOne` can update both `status` and `amount` of the same booking in a single-document atomic write.

### 7.2. Embedding Cuts Round Trips

AP1 avoids querying a separate `bookingAddons` collection on the hot read path.

### 7.3. Embedding Has Trade-Offs

Each update grows document size, impacting multikey indexes and write contention. If add-ons have independent lifecycles or access rules, referencing may be better.

## 8. Referencing: When Is It Better?

Favor referencing when:

- Data grows without bound.
- Records are queried or paginated independently.
- Data updates frequently and is referenced by many parents.
- Records have separate retention and security policies.
- A single canonical current state is required.
- Fan-out updates from duplication would be too costly.

Example:

~~~javascript
// customers
{
  _id: "tenant-a:customer:42",
  tenantId: "tenant-a",
  displayName: "Current name"
}

// bookings
{
  _id: "tenant-a:booking:1001",
  tenantId: "tenant-a",
  customerId: "tenant-a:customer:42",
  customerSnapshot: {
    displayName: "Name at booking"
  }
}
~~~

### 8.1. References and Snapshots Coexist

The two fields answer different questions: current customer vs. historical booking record. They are not necessarily redundant waste to delete.

### 8.2. Do Not Overwrite Immutable Snapshots on Master Updates

When a customer changes their name, do not rewrite thousands of historical contracts automatically. Establish separate policies if privacy/anonymization mandates purging personal data.

### 8.3. Referencing May Require `$lookup`

That cost is worthwhile when live profile state is required, data is large, or lifecycles update independently.

## 9. Cardinality Defines Model Limits

| Relationship | Design Direction |
| --- | --- |
| 1:1, shared lifecycle | Embedding is usually convenient |
| 1:few, bounded | Embed if commonly read/written together |
| 1:many, with upper bound | Evaluate size and update frequency |
| 1:many, unbounded | Reference or child collection |
| Many:many | Bounded IDs, association collection, or hybrid |

### 9.1. Small Average Does Not Prove Bounded

An average of two bookings per customer does not rule out one customer having millions of bookings. If an array can grow unboundedly, never store it all inside the customer document.

### 9.2. The 16 MiB Limit

A standard BSON document is capped at 16 MiB. Embedding complete payment histories, logs, or telemetry can breach that limit as the system scales.

### 9.3. Large Binary Payloads

File attachments typically belong in GridFS or object storage, storing only metadata or references inside the business document where appropriate.

## 10. Separating `paymentEvents` from `bookings`

Relational `payment_events` has a 1:N relationship with `bookings`. Model it as a separate collection:

~~~javascript
{
  _id: "payevt-901",
  tenantId: "tenant-a",
  bookingId: "tenant-a:booking:1001",
  providerRef: "sandbox-ref-901",
  eventType: "AUTHORIZED",
  amountMinor: NumberLong(1500000),
  happenedAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

### 10.1. Why Not Embed Every Event?

A booking can accumulate multiple attempts, refunds, webhook retries, disputes, and manual adjustments. Event histories grow over time and carry independent retention/audit requirements.

### 10.2. Summaries Can Still Be Embedded

`booking.paymentSummary.status` accelerates UI reads, yet must not be treated as the authoritative ledger if payment events/providers are the source of truth.

### 10.3. Synchronizing Summaries

When a payment event is verified/persisted, update the summary via outbox/consumer with idempotency and reconciliation. Accept eventual consistency if business rules allow it.

### 10.4. Querying Payment Audits

~~~javascript
db.paymentEvents.find({
  tenantId: "tenant-a",
  bookingId: "tenant-a:booking:1001"
}).sort({
  happenedAt: -1,
  _id: -1
});
~~~

## 11. Many-to-Many Does Not Always Need an Identical JOIN Collection

Example: `vehicles ↔ features`.

Relational designs use a `vehicle_features` join table. In MongoDB:

~~~javascript
{
  _id: "tenant-a:vehicle:7",
  tenantId: "tenant-a",
  featureCodes: [
    "gps",
    "child-seat",
    "insurance-eligible"
  ]
}
~~~

### 11.1. Bounded Codes

If `featureCodes` is small, always read with the vehicle, and carries little per-link metadata, embedding codes works well.

### 11.2. Master Metadata

Feature names, prices, and descriptions that change frequently can stay in a `features` collection rather than being copied onto every vehicle.

### 11.3. Associations with Independent Lifecycles

If the relationship itself carries effective dates, pricing rules, history, or states, a dedicated association collection remains a strong option.

## 12. A Hybrid Model Driven by Access Patterns

~~~text
customers:
  current profile

vehicles:
  current attributes, current rates

bookings:
  main booking state
  customer/vehicle snapshot
  bounded addons
  agreed amount

paymentEvents:
  separate append-only history

bookingStatusEvents:
  optional audit timeline

availabilityAllocations:
  overlap/concurrency-specific model

dailyRevenue:
  optional derived aggregate
~~~

### 12.1. Every Collection Has a Reason

Do not create collections because they used to be SQL tables; create them because their query, update, lifecycle, or retention requirements demand independence.

### 12.2. Keep Sources of Truth Explicit

`paymentSummary`, `dailyRevenue`, and search views can be derived. Allowing arbitrary services to mutate them directly makes reconciliation very difficult.

## 13. Atomicity and Document Boundaries

MongoDB single-document writes are atomic at the document level.

~~~javascript
db.bookings.updateOne(
  {
    _id: "tenant-a:booking:1001",
    tenantId: "tenant-a",
    status: "PENDING"
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 },
    $currentDate: { updatedAt: true }
  }
);
~~~

### 13.1. Conditional Updates Protect State Transitions

If a CANCEL request changed `status` first, a CONFIRM request filtering on `PENDING` fails to match. Never read `status` and overwrite unconditionally.

### 13.2. Do Not Assume Multi-Document Atomicity by Default

If creating a booking, logging a payment event, and updating availability must happen together, a single `updateOne` will not cover all three.

### 13.3. Transactions When Warranted

Multi-document transactions on supported topologies let a group of writes commit together. Still, business workflow design, idempotency, and external side-effect handling remain necessary independently.

### 13.4. Never Embed Everything Just to Avoid Transactions

Stuffing customers, vehicles, and full payment histories into one booking creates unbounded documents, contention, and duplicated master data.

## 14. Availability and Overlapping Time Intervals

One vehicle must not have two active bookings with overlapping periods under business rules.

Two intervals overlap when:

~~~text
existing.startAt < requested.endAt
AND
existing.endAt > requested.startAt
~~~

Overlap filter example:

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  vehicleId: "tenant-a:vehicle:7",
  status: { $in: ["HELD", "CONFIRMED"] },
  "period.startAt": {
    $lt: ISODate("2026-11-22T00:00:00Z")
  },
  "period.endAt": {
    $gt: ISODate("2026-11-19T00:00:00Z")
  }
});
~~~

### 14.1. Query-Then-Insert Has a Race

Two requests can both observe “zero overlaps” and insert bookings concurrently. A unique index on `vehicleId/startAt/endAt` **will not stop overlapping intervals** whose start/end timestamps differ.

### 14.2. Approaches

- Slot allocations with unique keys per time bucket.
- A shared allocation/availability document serving as a contention point.
- Transactions combining writes on that contention record.
- Explicit reservation holds, expirations, and conflict handling.

### 14.3. Do Not Treat Transactions Alone as a Cure-All

If two transactions merely query for the **absence** of conflicting documents and then insert different documents, you still need explicit contention or uniqueness keys to prevent write skew.

## 15. Replacing SQL JOINs with MongoDB `find` via Snapshots

AP1 reading a booking:

~~~javascript
db.bookings.findOne({
  _id: "tenant-a:booking:1001",
  tenantId: "tenant-a"
});
~~~

When the document holds status, period, snapshots, addons, and amount, detail APIs need no read-time JOIN.

### 15.1. Benefits

Fewer network round trips and fewer collections on the hot path.

### 15.2. Costs

Snapshots increase storage and require clear retention/PII policies. This is a deliberate trade-off, not free.

### 15.3. APIs Needing Current Profiles

When business genuinely needs live customer state, query `customers` separately or use `$lookup`. Never substitute booking-time `customerSnapshot` for live data.

## 16. Using `$lookup` When Current Data Is Required

Example fetching current customer scoped by tenant:

~~~javascript
db.bookings.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      _id: "tenant-a:booking:1001"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        customerKey: "$customerId",
        tenantKey: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$customerKey"] },
                { $eq: ["$tenantId", "$$tenantKey"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 0,
            displayName: 1
          }
        }
      ],
      as: "currentCustomer"
    }
  }
]);
~~~

### 16.1. Tenant-Aware Lookups

Never join solely on a business ID if IDs can collide across tenants. Enforce access checks in the service/repository as well.

### 16.2. `$lookup` Returns an Array

Even for zero or one matching record, the output is an array. Use `$first`/`$unwind` or mapper logic if an object is desired, handling missing matches safely.

### 16.3. Query Plans

Unindexed `$lookup` over large datasets is expensive. Run `explain`, measure latency, and evaluate snapshots or derived read models on hot paths.

## 17. Customer Booking History and Pagination

Query by tenant + customer and sort:

~~~javascript
db.bookings.find(
  {
    tenantId: "tenant-a",
    customerId: "tenant-a:customer:42"
  },
  {
    _id: 1,
    status: 1,
    period: 1,
    amount: 1,
    createdAt: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 17.1. Why Include an `_id` Tie-Breaker?

Multiple bookings can share identical `createdAt` values. Sorting solely by timestamp is not deterministic enough for pagination.

### 17.2. Large `skip` Offsets

Deep pagination using `skip` scans and discards many entries. Use keyset pagination with `lastCreatedAt` and `lastId` where appropriate.

### 17.3. Keyset Condition

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  customerId: "tenant-a:customer:42",
  $or: [
    {
      createdAt: {
        $lt: ISODate("2026-11-12T10:00:00Z")
      }
    },
    {
      createdAt: ISODate("2026-11-12T10:00:00Z"),
      _id: {
        $lt: "tenant-a:booking:1001"
      }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Keyset pagination does not freeze an immutable snapshot during concurrent writes; define read semantics per use case.

## 18. Translating SQL `GROUP BY` to Aggregation

Relational:

~~~sql
SELECT tenant_id, status,
       COUNT(*) AS cnt,
       SUM(total_minor) AS amount
FROM bookings
GROUP BY tenant_id, status;
~~~

MongoDB:

~~~javascript
db.bookings.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      count: { $sum: 1 },
      amountMinor: {
        $sum: "$amount.totalMinor"
      }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.status": 1
    }
  }
]);
~~~

### 18.1. Tenant Reports Must Filter by Tenant

The example above is a cross-tenant aggregation for authorized backend jobs. Tenant-facing APIs must prepend a `$match` on `tenantId` from the authenticated context.

### 18.2. Booking Revenue Differs from Payment Received

`Booking.amount` is the agreed total, not necessarily collected cash. Accounting reports require authoritative payment ledgers/finance sources.

### 18.3. Derived Analytics Collections

If aggregations run repeatedly over huge datasets, consider precomputing daily summaries with idempotent event replay and reconciliation.

## 19. Index by Queries, Not by Field Lists

Candidate indexes:

~~~javascript
// Customer history
db.bookings.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});

// Tenant status feed
db.bookings.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});

// Payment audit
db.paymentEvents.createIndex({
  tenantId: 1,
  bookingId: 1,
  happenedAt: -1,
  _id: -1
});

// Business booking number
db.bookings.createIndex(
  {
    tenantId: 1,
    bookingNumber: 1
  },
  { unique: true }
);
~~~

### 19.1. Built-In `_id` Index

MongoDB automatically creates a unique index on `_id` for standard collections. Detail lookups by `_id` already have an access path, yet tenant filtering remains mandatory for authorization.

### 19.2. Do Not Copy Every SQL Index

SQL indexes served normalized joins and table scans; MongoDB indexes must serve your new document query shapes.

### 19.3. Every Index Has a Cost

Indexes consume disk/RAM and add write amplification. Use `explain`, `nReturned`, `docsExamined`, latency, and selectivity to justify each one.

### 19.4. Lead Compound Indexes with `tenantId` When Appropriate

Tenant-scoped filters often benefit from leading with `tenantId`, depending on query shape and cardinality.

## 20. Identities and Primary Keys from SQL to MongoDB

A SQL `BIGINT` id may be globally unique or unique only within a tenant/partition.

MongoDB `_id` is unique within a collection, so map deterministically.

Example:

~~~text
tenant-a / SQL booking id 1001
    -> MongoDB _id "tenant-a:booking:1001"

tenant-b / SQL booking id 1001
    -> MongoDB _id "tenant-b:booking:1001"
~~~

### 20.1. Never Generate Random `ObjectId`s on Migration Retries

If the same source row gets a fresh `_id` on each run, retries create duplicates. Deterministic IDs or a durable mapping table are mandatory for idempotency.

### 20.2. Keep Source IDs as Metadata

Store `sourceBookingId` and `sourceSystem` for tracing and reconciliation. Never let trace metadata determine tenant authorization.

### 20.3. Business Keys and Uniqueness

`bookingNumber` may need per-tenant uniqueness. Use a compound unique index and audit legacy data before building it.

### 20.4. Sharded Collections Restrict Unique Indexes

When sharded, unique indexes and shard keys obey version-specific rules. Never assume an index applies unchanged across sharded topologies.

## 21. Mapping SQL Types to BSON

| SQL | Typical BSON / Java Choice | Notes |
| --- | --- | --- |
| `BIGINT` | `Int64` / Java `long` | Preserve range and sign |
| `INT` | `Int32` / `int` | Never mix with Strings |
| `DECIMAL` | `Decimal128` or integer minor units | Precision and rounding |
| `TIMESTAMP` | BSON `Date` / `Instant` mapping | Timezones |
| `VARCHAR` | `String` | Collation and normalization |
| `BOOLEAN` | BSON `Boolean` | Never store `"true"` String |
| `NULL` | `null` or missing per contract | Query semantics differ |
| `BLOB` | `Binary`/GridFS/object ref | 16 MiB limit and lifecycle |
| JOIN table | Embedded array or collection | Access patterns and cardinality |

### 21.1. SQL `TIMESTAMP` Is Not Always UTC

Columns without timezone info may reflect an application's local timezone. Confirm source semantics before converting to BSON Date.

### 21.2. Never Arbitrarily Convert Money to `double`

Protect monetary precision with `Decimal128` or integer minor units with explicit scale and currency rules.

### 21.3. `NULL` and Missing

In MongoDB, explicit `null` and missing fields behave differently across several operators. Decide whether migrations keep explicit `null` or omit the field.

### 21.4. Document Size

Before embedding child records, calculate worst-case sizes, not just averages.

## 22. Schema Validation for New Documents

An illustrative validator:

~~~javascript
db.createCollection("bookings", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "customerId",
        "vehicleId",
        "period",
        "status",
        "amount"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        vehicleId: { bsonType: "string" },
        status: {
          enum: [
            "PENDING",
            "HELD",
            "CONFIRMED",
            "CANCELLED",
            "COMPLETED"
          ]
        },
        period: {
          bsonType: "object",
          required: [
            "startAt",
            "endAt"
          ],
          properties: {
            startAt: { bsonType: "date" },
            endAt: { bsonType: "date" }
          }
        },
        schemaVersion: { bsonType: "int" }
      }
    }
  }
});
~~~

### 22.1. Validators Do Not Replace Foreign Keys

Cross-collection references, amount totals, and interval overlaps require application logic, transactions, or dedicated validation workflows.

### 22.2. Do Not Enforce Strict Schemas in One Step Over Legacy Data

Use expand/migrate/contract so older documents and writers do not fail abruptly.

### 22.3. Explicit Contracts Still Matter

Even though MongoDB does not force uniform fields on every document, your team must govern required fields, types, versions, and nullability.

## 23. Schema Evolution: Expand–Migrate–Contract

Suppose v1:

~~~javascript
{
  _id: "bk-1",
  totalMinor: NumberLong(1200000),
  schemaVersion: 1
}
~~~

V2:

~~~javascript
{
  _id: "bk-1",
  amount: {
    totalMinor: NumberLong(1200000),
    currency: "VND"
  },
  schemaVersion: 2
}
~~~

Workflow:

1. Readers support both v1 and v2.
2. Writers begin emitting v2.
3. Background migration converts legacy documents.
4. Verify counts and field values.
5. Once legacy clients retire, remove legacy read/write code.
6. Tighten validation and schema contracts once data is uniform.

### 23.1. Idempotent Migration

Compute values from sources via `$set` or deterministic transforms; avoid `$inc` if replays could double-count money.

### 23.2. Dual Fields May Be Needed During Transition

If old apps read root `totalMinor`, maintain compatibility for a bounded window rather than dropping the field immediately.

### 23.3. Do Not Overload `schemaVersion` as Business Version

`schemaVersion` describes shape, whereas `version` for optimistic concurrency or state transitions carries a distinct meaning.

## 24. Turning a Relational Schema Into a Mapping Specification

Before ETL, document every source and target clearly:

| SQL Source | MongoDB Target Field | Transformation |
| --- | --- | --- |
| `bookings.id` + `tenant_id` | `bookings._id` | Stable composite string |
| `bookings.tenant_id` | `tenantId` | String |
| `bookings.customer_id` | `customerId` | Stable mapped reference |
| `customers.display_name` | `customerSnapshot.displayName` | Snapshot policy |
| `bookings.vehicle_id` | `vehicleId` | Stable mapped reference |
| `vehicles.category` | `vehicleSnapshot.category` | Snapshot policy |
| `booking_addons` rows | `addons` array | Grouped + bounded |
| `bookings.total_minor` | `amount.totalMinor` | Int64 |
| `bookings.status` | `status` | Valid enum |
| `bookings.created_at` | `createdAt` | UTC BSON Date |
| `payment_events` rows | `paymentEvents` collection | Separate documents |
| n/a | `schemaVersion` | Target version |

### 24.1. Historical Snapshots May Be Missing in SQL Sources

If the RDBMS kept only current vehicle rates, you cannot reliably reconstruct contracted historical rates without archived rate tables or order line amounts. Define a fallback policy and document data-quality caveats.

### 24.2. Never Drop Fields Silently

Every source column must be classified: retained, transformed, intentionally dropped, deferred, or externally stored, with owner sign-off.

### 24.3. Reference Mappings Must Be Consistent

If `booking.customerId` maps to a string key while `customers._id` remains a `long`, lookups will fail. Keep ID types uniform domain-wide.

## 25. Data Profiling Before Migration

Measure:

- Row counts per table, tenant, status, and time range.
- Foreign-key orphans.
- Duplicate business keys.
- Missing/null/invalid enum values.
- Max and percentile add-ons per booking.
- Max events per booking.
- Monetary precision and outliers.
- Timestamp ranges and timezone anomalies.
- Largest text/blob fields.
- Soft-deleted rows and retention policies.
- Existing schema/data corruption.

### 25.1. Real Relational Data May Violate the ERD

Legacy scripts or disabled constraints can leave orphan rows. Never assume every foreign key holds cleanly.

### 25.2. Quarantine Bad Rows

If a transformation fails, record source IDs, reason codes, and remediation actions in a dead-letter/quarantine store. Never silently skip rows and report SUCCESS.

### 25.3. Baseline for Reconciliation

Capture counts, sums, and invariants at a specific watermark to compare against the MongoDB target.

## 26. Offline Migration

Simple workflow:

~~~text
Block or stop source writes
        |
        v
Export consistent source snapshot
        |
        v
Transform + load MongoDB
        |
        v
Reconcile and smoke test
        |
        v
Switch application
~~~

### 26.1. Pros

Minimal ordering hazards between backfill and live updates; clear recovery point.

### 26.2. Cons

Long downtime if data volume is large or transforms/index builds take hours. Unviable for tight uptime SLOs.

### 26.3. Never Promise “Just Dump and Import”

A real migration encompasses data models, indexes, validation, application behavior, and external integrations.

## 27. Online Migration: Backfill Combined with CDC

~~~text
SQL source of truth
   |
   +---- Consistent snapshot at watermark T0
   |           |
   |           v
   |        Backfill target
   |
   +---- Change Data Capture (after T0)
               |
               v
       Ordered/idempotent apply
               |
               v
            MongoDB
               |
               v
       Reconcile / shadow reads
               |
               v
             Cutover
~~~

### 27.1. Source of Truth Before Cutover

SQL remains canonical. The MongoDB target is being built and reconciled.

### 27.2. CDC Must Capture Deletes

A SQL DELETE post-snapshot must map to a tombstone, hard delete, or soft delete per business policy—ignoring deletes leaves ghost records in MongoDB.

### 27.3. Events Can Replay

CDC pipelines require idempotency due to duplicates, retries, and consumer rebalances. Never assume exactly-once delivery at every layer.

## 28. Batched Backfill and Checkpointing

Pseudo SQL:

~~~sql
SELECT id, tenant_id, customer_id,
       vehicle_id, status, total_minor,
       created_at
FROM bookings
WHERE id > :lastId
ORDER BY id
LIMIT :batchSize;
~~~

### 28.1. Keysets Instead of Large `OFFSET`s

Large offsets scan heavily and shift under concurrent inserts. Keyset cursors on a stable unique key enable clean resumption.

### 28.2. Composite Source Keys

If `id` is unique only per tenant, use a composite checkpoint rather than `lastId` alone.

### 28.3. Avoid N+1 SQL Queries

Never query customer, vehicle, and addons row-by-row for millions of bookings. Batch joins/prefetches, stream rows, and bound memory.

### 28.4. Checkpoint Only After Confirmed Writes

Marking a batch complete before target writes persist causes crashes to lose slices of data.

### 28.5. Throttling

Backfills must not saturate production SQL or MongoDB CPU/IOPS. Monitor throughput, queue lag, and resource utilization, with pause/resume controls.

## 29. Deterministic and Idempotent Target Writes

One SQL row must always map to the same MongoDB `_id`:

~~~javascript
db.bookings.replaceOne(
  { _id: "tenant-a:booking:1001" },
  {
    _id: "tenant-a:booking:1001",
    tenantId: "tenant-a",
    sourceBookingId: NumberLong(1001),
    status: "PENDING",
    schemaVersion: 2
  },
  { upsert: true }
);
~~~

### 29.1. Safe Scope of `replaceOne`

Only appropriate when the target has not yet received newer CDC/application writes, or an ordering policy guarantees freshness.

### 29.2. Backfill Overwriting CDC Is a Critical Bug

If CDC already applied `CONFIRMED` and a delayed backfill writes `PENDING`, target state **regresses**. Prevent this via snapshot barriers, sequencing, or monotonic source versions.

### 29.3. Conditional Upserts Are Trickier Than They Look

An upsert filtering on `_id` and `sourceVersion < incoming` can attempt a duplicate `_id` insert when the target already holds a newer version. Design explicit insert/update conflict handling rather than assuming a version predicate suffices.

### 29.4. Idempotency Does Not Eliminate Auditing

Log source IDs, modified/unchanged counts, and conflicts for troubleshooting.

## 30. CDC Ordering and Duplicate Events

~~~text
Source transaction committed
      |
      v
SQL log / connector
      |
      v
Event keyed by booking ID
      |
      v
Transform
      |
      v
Apply only when appropriate source sequence
      |
      v
MongoDB target
~~~

### 30.1. Per-Entity Ordering

If `PENDING → CONFIRMED → CANCELLED` events arrive out of order, the target ends up in the wrong state. Enforce ordering/watermarks derived from source log semantics.

### 30.2. App Timestamps Are Not Always Authoritative Order

`createdAt`/`updatedAt` can collide or suffer clock skew. Source log sequences, row versions, or transaction commit ordering are far more reliable where available.

### 30.3. Cross-Table Changes

One SQL transaction can update both `bookings` and `booking_addons`. If CDC streams the tables separately, assemble the target document from a consistent state or reconcile once both changes apply.

### 30.4. Appending Payment Events

Deterministic event IDs plus unique indexes discard retry duplicates. External non-database side effects still require separate idempotency.

## 31. Dual-Write Is Not Automatically Atomic

A service writing two datastores:

~~~text
Write SQL succeeds
Write MongoDB fails
~~~

or:

~~~text
Write MongoDB succeeds
Write SQL fails
~~~

### 31.1. `try/catch` Does Not Solve Distributed Commits

A local SQL transaction cannot roll back an already-committed MongoDB write, and vice versa.

### 31.2. The Outbox Pattern

A standard approach: write business changes and an outbox row inside the same SQL transaction, then have a background consumer ship changes to MongoDB with retries and deduplication.

### 31.3. Never Allow Two Authoritative Writers

Before cutover, SQL is authoritative. After cutover, MongoDB is authoritative per plan. Avoid letting both accept independent writes without reconciliation.

## 32. Shadow Reads Before Cutover

~~~text
Client
  |
  v
Application
  |
  +--> SQL authoritative query ---> response to client
  |
  +--> MongoDB shadow query ------> compare / log diff
~~~

### 32.1. Do Not Serve Shadow Results Until Proven Reliable

Initially use shadow reads solely for comparison without affecting user-facing responses.

### 32.2. Canonicalize Before Comparing

Dates, numeric types, field ordering, null/missing, and derived fields can format differently. Compare contracted business fields.

### 32.3. Intentional Sampling

Cover multiple tenants, statuses, dates, large bookings, cancellations/refunds, and missing references—not just happy paths.

### 32.4. Shadow Load

Extra MongoDB reads add load. Throttle/sample shadow traffic and watch p95 latency and resource impact.

## 33. Reconciliation: Row Counts Alone Are Not Enough

| Check | Defects Caught |
| --- | --- |
| Total count | Missing/duplicate records |
| Count by tenant/status | Localized skew |
| Sum of amounts by day/tenant | Financial discrepancies |
| Deep sample comparison | Wrong snapshots/addons |
| Duplicate business keys | Broken ID mapping |
| Orphan references | Missing master records |
| Schema validator failures | Wrong BSON types |
| CDC watermark/lag | Target lagging behind |
| API shadow diffs | Behavioral mismatches |
| Index/query plans | Performance readiness |

### 33.1. Compare at Identical Recovery Points

Never compare SQL at T2 directly against MongoDB backfilled only to T1 and raise false alarms. Align watermarks or account for in-flight CDC events.

### 33.2. Canonical Hashes

If using checksums, standardize field ordering, BSON types/dates, `Decimal128`, Unicode normalization, and derived fields.

### 33.3. Never Log Raw PII

Reports should retain counts, masked IDs, and sanitized diffs. Even test environments must respect privacy policies.

## 34. MongoDB Reconciliation Aggregation

~~~javascript
db.bookings.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      count: {
        $sum: 1
      },
      amountMinor: {
        $sum: "$amount.totalMinor"
      }
    }
  },
  {
    $sort: {
      "_id.tenantId": 1,
      "_id.status": 1
    }
  }
]);
~~~

### 34.1. Compare Counts and Sums

Two groups can have identical booking counts yet different totals. Always verify critical business invariants.

### 34.2. This Aggregation Is Cross-Tenant

Use it solely in authorized backend migration validation. Single-tenant APIs must prepend `$match` on `tenantId`.

### 34.3. Payment Data Is Separate

Payment reports must reconcile payment ledgers/events against the provider rather than assuming booking amounts equal cash collected.

## 35. Cutover Gates

Before switching traffic:

1. Backfill complete within scope.
2. CDC lag/watermark within agreed bounds.
3. Counts, totals, and invariants reconciled.
4. Critical shadow reads passing.
5. Read/write/transaction workflows passing.
6. Unique indexes and schema validations ready.
7. Network, TLS, auth, and RBAC roles verified.
8. Query plans and p95 latency meeting SLOs.
9. Source-of-truth switch executed per approved plan.
10. Rollback/forward-fix strategy ready.

### 35.1. Optional Brief Write Freeze

A short write pause lets CDC catch up to the final watermark for a clean cutover check. Use only if SLAs allow.

### 35.2. Canary Rollout

Shift a small percentage of read traffic first, then ramp gradually. Write cutovers must be coordinated across services so SQL and MongoDB do not diverge.

### 35.3. Never Mark PASS Just Because the Copy Job Succeeded

Data might still be incomplete, indexes missing, or applications misbehaving against the new model.

## 36. Rollback After MongoDB Has Accepted Writes

~~~text
SQL frozen at T0
        |
        v
MongoDB receives new bookings at T1
        |
        v
Problem detected at T2
~~~

Pointing the app back to SQL immediately loses writes made after T0 unless SQL was synced back.

### 36.1. Rollback or Forward-Fix?

- Roll back when data can be preserved and contracts permit.
- Forward-fix when MongoDB is already the source of truth holding substantial fresh writes.
- Reverse replication/reconciliation if returning to SQL without data loss is required.

### 36.2. Avoid Split-Brain

Never let SQL and MongoDB accept independent authoritative writes concurrently without an explicit conflict/consistency design.

### 36.3. Define Rollback Gates Before Cutover

Decide approvers, time limits, how new writes are handled, and where outbox/payment queues route beforehand.

## 37. Java Sync Driver: Single-Booking Read

Java CLI demo:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import org.bson.Document;
import org.bson.conversions.Bson;

public class BookingReadDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("rental_demo");
            MongoCollection<Document> bookings =
                db.getCollection("bookings");

            String trustedTenant = "tenant-a";

            Bson filter = Filters.and(
                Filters.eq(
                    "_id", "tenant-a:booking:1001"
                ),
                Filters.eq(
                    "tenantId", trustedTenant
                )
            );

            Bson projection = Projections.include(
                "customerSnapshot",
                "vehicleSnapshot",
                "period",
                "addons",
                "amount",
                "status"
            );

            Document doc = bookings.find(filter)
                .projection(projection)
                .first();

            if (doc == null) {
                System.out.println("Not found");
            } else {
                System.out.println(doc.toJson());
            }
        }
    }
}
~~~

### 37.1. `MongoClient` Lifecycle

Web services normally reuse one `MongoClient` over the service lifetime. This example uses try-with-resources because it is a one-shot CLI.

### 37.2. Never Expose Raw Documents Directly

In production, map `Document` to a tightly scoped DTO rather than returning raw internal JSON.

### 37.3. Tenant ID Comes from Auth

`trustedTenant` comes from verified backend auth context, never from an untrusted user parameter.

## 38. Java Sync Driver: Conditional State Update

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.conversions.Bson;

Bson filter = Filters.and(
    Filters.eq(
        "_id", "tenant-a:booking:1001"
    ),
    Filters.eq(
        "tenantId", "tenant-a"
    ),
    Filters.eq(
        "status", "PENDING"
    )
);

Bson update = Updates.combine(
    Updates.set(
        "status", "CONFIRMED"
    ),
    Updates.inc(
        "version", 1
    ),
    Updates.currentDate(
        "updatedAt"
    )
);

UpdateResult result = bookings.updateOne(
    filter, update
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Booking not found or state changed"
    );
}
~~~

### 38.1. Single-Document Atomicity

`status` and `version` update together in one atomic booking write.

### 38.2. Payments Do Not Sync Automatically

Updating booking status does not automatically update a separate payment ledger collection or external payment provider.

### 38.3. Tenant Isolation

Every repository read, update, and delete must filter by the trusted tenant.

## 39. Multi-Tenant Security in Document Models

Every API needs:

- Verified tenant context.
- `tenantId` filter at the document root or matching access-control predicate.
- Cross-reference validation.
- Tenant-aware `$lookup` where used.
- Rejection of arbitrary client-supplied BSON filters.
- Indexes supporting tenant-scoped queries.
- Audit logs with masked identifiers.

### 39.1. Snapshots Containing PII

Never copy an entire profile if the screen only needs `displayName`. Sensitive fields carry separate retention and anonymization policies.

### 39.2. Field-Level Access

Projections shrink network payloads, yet do not enforce authorization on their own. Enforce DTO and role policies.

### 39.3. Never Assume `_id` Alone Grants Access

Even when `_id` is an unguessable UUID, the application must still verify tenant/owner permissions.

## 40. Sharding and Long-Term Growth

If the system needs a sharded cluster, select shard keys based on query patterns, cardinality, and write distribution.

### 40.1. `tenantId` Can Be Both Helpful and Risky

Most queries filter by tenant, aiding locality, yet one giant tenant driving most writes can create a hotspot depending on shard-key design.

### 40.2. Do Not Pick a Key Simply Because Every Document Has It

Evaluate distribution, growth, query targeting, unique-index restrictions, and resharding capabilities for your MongoDB version.

### 40.3. Denormalization Does Not Replace Sharding Design

A `bookings` collection with embedded snapshots still needs proper shard targeting and indexes as it scales.

## 41. Evaluating the Model with Metrics

Measure before and after:

- API p50/p95/p99 latency.
- DB round trips per request.
- Documents examined vs. returned.
- Winning plans and index utilization.
- Document size distribution.
- Write latency and write amplification.
- Storage and index footprint.
- Multi-document transaction frequency.
- CDC lag and read-model staleness.
- Data reconciliation diffs.
- Business error rates and availability.

### 41.1. Do Not Count Reduced JOINs Alone

A “single document” design with bad write p95 or bloated document sizes is not necessarily better.

### 41.2. Small Fixtures Differ from Performance Datasets

Correctness tests use small targeted fixtures; load tests need representative volumes and realistic tenant/request distributions.

### 41.3. Test Negative Cases

Bookings with zero addons, missing customers, tenant mismatches, duplicate business IDs, payment retries, and overlapping booking intervals.

## 42. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| 1:1 table-to-collection port | Still lots of JOINs and round trips | Design around access patterns |
| Embedding all bookings inside customer | Unbounded array, 16 MiB limit | Separate `bookings` collection |
| Embedding all payment events | Bloated audit history | Separate append-only collection |
| Syncing current vehicle rate into old bookings | Corrupts price history | Immutable price snapshot |
| Copying master data onto every record | Massive fan-out updates | Deliberate references/snapshots |
| Two authoritative writers on one field | Drift and conflicts | Clear ownership contract |
| Omitting tenant filter in `$lookup` | Cross-tenant data leak | Tenant-aware access checks |
| Missing unique business index | Duplicate bookings | Stable IDs + uniqueness |
| Storing Dates as Strings | Broken range/sort behavior | BSON Date |
| Storing Decimals as `double` | Precision loss | `Decimal128` / minor units |
| Turning SQL NULL into missing carelessly | Altered query semantics | Explicit mapping policy |
| Omitting `schemaVersion` | Hard mixed-schema reads | Expand–migrate–contract |
| Uncheckpointed backfill | Expensive retries, lost slices | Batched resumable job |
| Random IDs on retry | Duplicate records | Deterministic mapping |
| Backfill overwriting fresher CDC | Stale regression | Watermarks / source versions |
| Ignoring SQL deletes | Ghost records in MongoDB | Tombstone / delete mapping |
| Dual-writing without outbox | Partial commits | One canonical store + CDC |
| Reconciling total counts only | Misses tenant/amount errors | Grouped counts + invariants |
| Comparing snapshots from different times | False diffs | Aligned watermarks |
| Cutting over while CDC lags | Stale/missing writes | Enforced cutover gates |
| Rolling back by swapping URI post-writes | Loses fresh writes | Reverse sync / forward-fix |
| Querying absence then inserting booking | Double-booking race | Slot / contended allocation |
| Assuming unique start/end stops overlap | Interval collisions | Proper concurrency model |
| Missing indexes for feeds | Slow scans/sorts | Explain + index design |
| Extrapolating scale from tiny fixtures | Misleading results | Dedicated performance suite |
| Using raw PII in migration tests | Privacy exposure | Synthetic/anonymized data |

## 43. Decision Flow: Embed vs. Reference

~~~text
Is the child always read with the parent?
    |
    +-- No --> Reference likely
    |
    v
Is cardinality strictly bounded?
    |
    +-- No --> Separate collection likely
    |
    v
Does it share lifecycle and consistency?
    |
    +-- Yes --> Embedding candidate
    |
    +-- No --> Reference / historical snapshot
    |
    v
Is it updated independently or widely shared?
    |
    +-- Yes --> Reference or derived model
    |
    v
Will max document size stay reasonable?
    |
    +-- No --> Reconsider
    |
    v
Prototype, index and measure workload
~~~

This is a **heuristic**, not an absolute rule. Historical snapshots may live inside a booking even when master data updates independently.

## 44. Relational Schema Analysis Exercises

### Exercise 1 — Inventory

From `customers`/`vehicles`/`bookings`/`booking_addons`/`payment_events`, list 8 access patterns with filters, sorts, and expected round trips.

### Exercise 2 — Booking Detail

Design a `booking` document optimized for AP1. Which fields should be snapshots, and which should stay references?

### Exercise 3 — Historical Rent Rate

A vehicle's current rate changes from 700,000 to 900,000. Which rate should a confirmed booking display, and why?

### Exercise 4 — One-to-Many

Up to 10 add-ons vs. unbounded payment events. Choose embed vs. reference and justify.

### Exercise 5 — Many-to-Many

Vehicle features carry mutable metadata. Design `featureCodes` alongside a `features` master collection.

### Exercise 6 — Current vs. Snapshot

A customer updates their `displayName`. When should `bookingSnapshot` keep the old name, and when does an API need the current name?

## 45. Query and Index Exercises

### Exercise 7 — Tenant History

Write the filter, sort, and index to read the 20 latest bookings for a customer in `tenant-a`.

### Exercise 8 — Keyset

Given sort `createdAt` desc, `_id` desc, write the predicate for the next page.

### Exercise 9 — `$lookup`

Use `$lookup` to fetch the current customer while enforcing a `tenantId` match.

### Exercise 10 — Group By

Write an aggregation counting bookings and summing amounts by tenant and status.

### Exercise 11 — Unique ID

SQL booking IDs are unique only per tenant. Propose a MongoDB `_id` scheme and unique business key.

### Exercise 12 — BSON Conversion

Convert SQL `BIGINT`, `DECIMAL`, `TIMESTAMP`, and `NULL` with explicit semantics.

### Exercise 13 — Validator

Write a JSON Schema validator covering `tenantId`, `period` Dates, and the `status` enum.

## 46. Consistency Exercises

### Exercise 14 — Status Transition

Two requests—CONFIRM and CANCEL—both start from PENDING. Write conditional updates and expected outcomes.

### Exercise 15 — Interval Overlap

Two requests check vehicle availability simultaneously and both insert. Why does double booking happen? Propose a slot or contention-record design.

### Exercise 16 — Payment Summary

A payment event is delivered twice. How do you update the summary without double-counting the amount?

### Exercise 17 — External Effects

Confirming a booking sends an email and charges a card. Does a MongoDB transaction roll back those two external actions?

## 47. Migration Exercises

### Exercise 18 — Mapping

Build a complete SQL-to-BSON mapping covering stable IDs, snapshots, addons, dates, money, and `schemaVersion`.

### Exercise 19 — Data Profiling

Which baseline counts, orphan checks, duplicate checks, and max cardinalities are needed pre-migration?

### Exercise 20 — Batch Checkpoint

Design a keyset backfill by source ID with crash recovery and proper checkpoint timing.

### Exercise 21 — CDC Ordering

A backfill PENDING record arrives after CDC already applied CONFIRMED. Design how to prevent regression.

### Exercise 22 — SQL `DELETE`

A booking is hard-deleted or soft-deleted in SQL while CDC runs. How should the target handle it?

### Exercise 23 — Dual-Write

SQL commit succeeds while the MongoDB write fails. Design an outbox/canonical-source strategy.

### Exercise 24 — Reconciliation

Total counts match, yet 100 bookings belong to the wrong tenant. How do you detect it?

### Exercise 25 — Shadow Reads

Design shadow queries for booking details and feeds, persisting sanitized diffs.

### Exercise 26 — Cutover

Define go/no-go gates for CDC lag, reconciliation, indexes, auth, and application smoke tests.

### Exercise 27 — Rollback

MongoDB has already accepted 500 bookings post-cutover. Why can you not simply switch the URI back to SQL? Propose forward-fix vs. reverse sync.

### Exercise 28 — Mixed Schema

Move root `totalMinor` to `amount.totalMinor`. Design expand–migrate–contract and an idempotent backfill.

## 48. Pre-Migration Checklist

### Analysis

1. Read/write access-pattern inventory confirmed.
2. Cardinalities, growth, and lifecycles measured.
3. Invariants/constraints and transaction boundaries clear.
4. Master data, snapshots, events, and derived models separated.
5. Data privacy and retention rules documented.
6. Document size and headroom estimated.

### Design

7. Embed/reference decisions justified by access patterns.
8. Zero uncontrolled unbounded arrays.
9. Stable IDs and valid tenant scoping defined.
10. Consistent BSON mappings for money, dates, and nulls.
11. Status/availability concurrency modeled.
12. Indexes aligned with filters, sorts, and uniqueness.
13. Schema validation and versioning prepared.
14. Ownership and sync rules for derived fields documented.

### Migration

15. Source profiling and baseline captured.
16. Deterministic transforms, checkpoints, and retries built.
17. Consistent snapshot/watermark established.
18. CDC ordering, deletes, and deduplication defined.
19. Never two concurrent authoritative writers.
20. Reconciliation by tenant, status, amount, and invariants.
21. Shadow reads and concurrency tests passing.
22. Cutover/rollback owners and gates assigned.

### Operations

23. Monitoring p95, errors, CDC lag, and throughput.
24. Backup/restore/DR plan ready for MongoDB target.
25. Security, roles, and TLS verified.
26. Legacy SQL writes retired per plan.
27. Legacy data/credentials handled per retention policy.
28. Evidence and corrective actions assigned to owners.

## 49. Illustrative Migration Runbook

~~~text
DISCOVER:
  Inventory SQL tables and constraints
  Record hot reads, writes, cardinalities
  Identify historical snapshot requirements

DESIGN:
  Choose aggregate/document boundaries
  Embed bounded, reference unbounded data
  Define canonical/derived ownership
  Specify BSON mapping, indexes and schemaVersion
  Test interval concurrency and tenant isolation

PREPARE:
  Verify source/target and backups
  Capture baseline and CDC watermark
  Define deterministic IDs
  Approve cutover/rollback plan

BACKFILL:
  Extract consistent batches
  Transform and write idempotently
  Save checkpoints after confirmations
  Monitor throughput, quarantine failures

SYNC:
  Consume ordered CDC events
  Deduplicate and handle deletes
  Prevent stale backfill overwrites
  Monitor lag and reconcile

VALIDATE:
  Counts by tenant/status
  Money totals and business invariants
  Deep sample comparison
  Shadow API reads
  Index plans, performance and security

CUTOVER:
  Quiesce source writes if needed
  Catch up CDC to agreed watermark
  Verify readiness and switch traffic
  Monitor application and data quality

RECOVER:
  Stop rollout if gates fail
  Choose rollback or forward-fix
  Reconcile all writes after cutover

CLOSE:
  Preserve sanitized evidence
  Retire old write path and secrets safely
  Update monitoring, backups and runbooks
~~~

## 50. Conclusion

Moving from relational to document models is a **data-model redesign centered on how the application uses data**:

- **Never translate tables mechanically:** start with access patterns, lifecycles, and consistency requirements.
- **Embed where fitting:** small, bounded child items read and written with their parent.
- **Reference where needed:** master data, audit histories, and unbounded relationships.
- **Use intentional snapshots:** preserve prices, names, and terms locked in at transaction time.
- **Keep sources of truth clear:** derived summaries and read models need clear ownership, event ordering, and reconciliation.
- **Design for concurrency:** single-document atomicity does not automatically solve multi-collection workflows or interval overlaps.
- **Map data accurately:** stable IDs, monetary types, dates, NULLs, and schema versions.
- **Make migrations repeatable:** backfill checkpoints, CDC, idempotency, shadow reads, validation, and cutover gates.
- **Account for new writes in rollback:** post-cutover, flipping a connection string alone will lose data.

A well-designed document model simplifies hot paths, preserves historical accuracy, and scales cleanly. Migration success is measured not by how many tables were deleted, but by **business correctness, measured performance, and safe evolvability**.

## References

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedded Data and References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Schema Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/)
- [MongoDB Manual — BSON Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — Aggregation](https://www.mongodb.com/docs/manual/aggregation/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
