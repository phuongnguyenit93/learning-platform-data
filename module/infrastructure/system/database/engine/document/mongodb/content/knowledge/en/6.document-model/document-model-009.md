# History Modeling, Versioning, and Long-Term Data Retention in MongoDB

Not all data in MongoDB only needs to represent **current state**. An order must preserve the price at purchase time; a contract must allow retrieving the signed version; a business configuration must record who changed it and when; device logs may need to be retained for years even when rarely read. Those requirements take document design beyond basic CRUD: you must decide **what information is preserved, where it is stored, for how long, and how it is queried across time**.

MongoDB supports multiple modeling approaches: storing prior versions in a history collection, storing immutable events, capturing snapshots, storing validity intervals, keeping a hot working dataset while moving older records to archival storage. No single model is optimal for every system. Decisions must start from query requirements, recoverability, data integrity, storage limits, and data retention policies.

This lesson sits in the **Document Model** chapter and focuses on data design. Illustrative commands use **mongosh**, a test database `document_history_lab`, and string-based document IDs for readability. Behaviors dependent on MongoDB version, driver, or topology must be verified in your specific deployment environment.

## 1. Why Is a Current-State-Only Model Insufficient?

Suppose an insurance platform has a policy document:

~~~javascript
{
  _id: "policy-1001",
  customerId: "customer-008",
  premium: NumberDecimal("1200000.00"),
  currency: "VND",
  coverage: "BASIC",
  status: "ACTIVE",
  updatedAt: ISODate("2026-04-15T09:00:00Z")
}
~~~

If the application executes:

~~~javascript
db.policies.updateOne(
  { _id: "policy-1001" },
  {
    $set: {
      premium: NumberDecimal("1500000.00"),
      updatedAt: new Date()
    }
  }
)
~~~

then the current document reflects the new premium. However, this document **cannot answer**:

- What was the policy's original premium?
- In which version did the premium change, and on what date did it take effect?
- Who requested the change and for what reason?
- Since when did the system know about that adjustment?
- If the application wrote an erroneous value, can the previous valid version be restored?
- Seven years later, which records must still be retrievable for audits or disputes?

Without designing for this upfront, reconstructing facts from application logs or backups can be incomplete, slow, or fail business evidentiary standards.

### Three Goals Often Confused Together

| Goal | Question to Answer | Data to Retain |
|---|---|---|
| **State history** | At a past edit or point in time, what values did the document hold? | Revisions/snapshots, timestamps, and entity identifier |
| **Audit trail** | Who did what, through which channel, why, and with what outcome? | Actor, operation, request/correlation ID, timestamp, old/new values or events |
| **Long-term retention** | How can data remain readable years later and at what cost? | Versioned/schema-tagged records, metadata, retention policy, archive, and restore capability |

A history collection can support all three goals, yet does not automatically satisfy legal audit or retention requirements. For example, saving old snapshots without actor and reason is insufficient for investigations; saving an event log without preserving old schema readers can make state reconstruction impossible.

## 2. Distinguish Three Types of Versioning

When saying "version," specify the version of **what**.

| Type | Meaning | Example | Typically Used For |
|---|---|---|---|
| **Business revision** | Number of times an entity's business state changed | Policy `revision: 4` | Fetching prior state, optimistic concurrency, auditing |
| **Schema version** | Document structural version that application code knows how to read | `schemaVersion: 2` | Migrations, reading legacy data, app compatibility |
| **Event format version** | Structural version of an event's payload | `eventVersion: 1` | Processing/replaying events emitted by different app releases |

A policy at `revision: 7` may still be stored under `schemaVersion: 2`. A `PolicyPremiumChanged` event with `eventVersion: 1` does not necessarily correspond to revision 1 of the policy. **Never overload a single ambiguous `version` field** for all three purposes.

Example:

~~~javascript
{
  _id: "policy-1001",
  revision: 7,
  schemaVersion: 2,
  customerId: "customer-008",
  terms: {
    premium: NumberDecimal("1500000.00"),
    currency: "VND",
    coverage: "STANDARD"
  },
  updatedAt: ISODate("2026-04-15T09:00:00Z")
}
~~~

At the business level, `revision` increments when domain state changes. At the schema level, `schemaVersion` changes only when the storage format requires different reading/handling logic. Schema changes do not necessarily align with business edits.

## 3. Time in Historical Data: "When" Has Two Meanings

A common mistake is adding a single `updatedAt` field and assuming it captures the entire past.

### 3.1. Recorded Time vs. Effective Time

- **Recorded time / transaction time:** when the system recorded the fact. Applications often use `recordedAt` or `createdAt`.
- **Valid time / effective time:** the interval during which the fact holds true in the business domain; often modeled with `validFrom` and `validTo`.

For example, on May 10, staff enter a premium increase **effective May 1**. The two timestamps do not match:

~~~javascript
{
  entityId: "policy-1001",
  revision: 5,
  premium: NumberDecimal("1500000.00"),
  validFrom: ISODate("2026-05-01T00:00:00Z"),
  recordedAt: ISODate("2026-05-10T08:30:00Z")
}
~~~

Asking "What was the effective premium on May 3?" differs from asking "As of May 3, what premium **did the system know about**?" This is the foundation of **bitemporal** modeling (two time axes).

### 3.2. Half-Open Time Intervals

When representing versions valid over time ranges, a useful convention is:

~~~text
[validFrom, validTo)
 includes validFrom
 excludes validTo

Version A: [2026-01-01, 2026-04-01)
Version B: [2026-04-01, 2026-07-01)
Version C: [2026-07-01, infinity)
~~~

Suppose `validTo: null` means no end date yet. A query finding the active interval at `t` must include records without a `validTo`:

~~~javascript
const t = ISODate("2026-05-15T12:00:00Z")

db.policy_periods.find({
  entityId: "policy-1001",
  validFrom: { $lte: t },
  $or: [
    { validTo: { $gt: t } },
    { validTo: null }
  ]
})
~~~

**Important:** the filter `{validTo: null}` in MongoDB also matches documents **missing the `validTo` field**. If you need to distinguish a missing field from BSON `null`, enforce a consistent schema and use an appropriate filter such as `$exists` or `$type`. Rules forbidding overlapping validity intervals for the same entity must typically be enforced in service/transaction logic; **a simple unique index does not automatically prevent overlapping time ranges**.

## 4. Map of History Storage Models

~~~mermaid
flowchart TD
    R["History storage requirement"] --> A{"Need full state versions?"}
    A -->|"Yes"| B["Current + History / Document Versioning"]
    A -->|"No, need action stream"| C["Append-only Event Log"]
    B --> D{"Small bounded count of old versions?"}
    D -->|"Yes"| E["Bounded embedded history"]
    D -->|"No"| F["Separate history collection"]
    C --> G{"Need fast state rebuild?"}
    G -->|"Yes"| H["Snapshot + events"]
    G -->|"No"| I["Replay events"]
    F --> J["Hot / warm / cold archive"]
    H --> J
    I --> J
~~~

| Model | Advantages | Limitations to Watch | Suitable Use Cases |
|---|---|---|---|
| **Bounded embedded history** | Read current + a few past versions in one document | Document grows, 16 MiB limit, write contention | Keeping 3–10 recent small, tightly controlled values |
| **Current + History collection** | Compact current, independently queryable history, easy indexing/retention | Must keep current and history updates consistent | Profiles, contracts, configs, price tables |
| **Append-only events** | Expresses business actions; can reconstruct state | Must define event schema, ordering, idempotency, replay | Ledgers, workflows, event-based audits |
| **Snapshots + events** | Reduces cost of replaying from scratch | Must align snapshot checkpoints with event sequences | Long event streams needing fast rebuilds |
| **Temporal intervals** | Query data effective at a given point in time | Hard to manage overlaps, retroactive edits, and bitemporality | Period-based pricing, effective terms, entitlements |
| **Hot/warm/cold archive** | Lower long-term storage cost, lean hot queries | Needs catalog, migration pipeline, search/restore workflows | Multi-year data rarely accessed |

Models can be combined: for instance, an entity has a current document, revision-based history snapshots, an audit event log for operations, and an archival schedule moving older history to cold storage.

## 5. Model A — Bounded Embedded History

For small entities where displaying a profile needs only a few recent values, history can be embedded inside the same document:

~~~javascript
{
  _id: "member-001",
  displayName: "Nguyen Lan",
  phone: "0900000000",
  phoneHistory: [
    {
      value: "0911111111",
      changedAt: ISODate("2026-01-05T09:00:00Z")
    },
    {
      value: "0922222222",
      changedAt: ISODate("2025-12-01T10:00:00Z")
    }
  ]
}
~~~

If policy retains only the last three phone numbers, a single document update can prepend the new entry and trim the array:

~~~javascript
db.members.updateOne(
  { _id: "member-001" },
  {
    $set: { phone: "0933333333" },
    $push: {
      phoneHistory: {
        $each: [{
          value: "0900000000",
          changedAt: new Date()
        }],
        $position: 0,
        $slice: 3
      }
    }
  }
)
~~~

Here the example assumes the current previous number is `0900000000` and passed into the update. **In real applications, never read an old value and write blindly** under concurrent requests. Filter by expected revision/value or use an appropriate update pipeline/transaction so history accurately captures the transition.

### Why Must Arrays Be Bounded?

Every BSON document has a **16 MiB** size limit. An ever-growing history array:

- Continuously inflates the document.
- Increases read/transfer overhead when only current data is needed.
- Creates write contention on the same hot document.
- Complicates pagination and risks hitting the document size cap.
- Forces losing old data if `$slice` is added later.

**Rule:** use embedded history only when element count and byte size are capped by business requirements. For unbounded retention or millions of versions, move history to a separate collection.

## 6. Model B — Current Document and History Collection

This is a common pattern when **current state is read frequently, while history is accessed less often yet must remain complete**.

~~~mermaid
flowchart LR
    API["Current read API"] --> Current["policies: one current document per policy"]
    Current -->|"each controlled change"| History["policy_history: many historical revisions"]
    Auditor["Audit / historical lookup API"] --> History
    Auditor --> Current
~~~

### 6.1. Designing the Current Collection

~~~javascript
use document_history_lab

db.policies.insertOne({
  _id: "policy-1001",
  revision: 1,
  schemaVersion: 1,
  customerId: "customer-008",
  terms: {
    premium: NumberDecimal("1200000.00"),
    currency: "VND",
    coverage: "BASIC"
  },
  status: "ACTIVE",
  createdAt: ISODate("2026-04-01T09:00:00Z"),
  updatedAt: ISODate("2026-04-01T09:00:00Z")
})
~~~

Meaning of fields:

- `_id` preserves a stable identity across the policy lifecycle.
- `revision` is the business revision of the current state.
- `schemaVersion` tells code which layout to parse.
- `terms` contains business data that may change across revisions.
- `createdAt` marks entity creation; `updatedAt` marks state modification and does not replace an audit log.

### 6.2. Designing the History Collection

~~~javascript
db.policy_history.createIndex(
  { entityId: 1, revision: 1 },
  { unique: true, name: "uq_policy_revision" }
)

db.policy_history.createIndex(
  { entityId: 1, capturedAt: -1 }
)
~~~

A history document stores **the snapshot before it was replaced**:

~~~javascript
{
  _id: ObjectId("65f000000000000000000001"),
  entityId: "policy-1001",
  revision: 1,
  schemaVersion: 1,
  snapshot: {
    customerId: "customer-008",
    terms: {
      premium: NumberDecimal("1200000.00"),
      currency: "VND",
      coverage: "BASIC"
    },
    status: "ACTIVE",
    createdAt: ISODate("2026-04-01T09:00:00Z"),
    updatedAt: ISODate("2026-04-01T09:00:00Z")
  },
  capturedAt: ISODate("2026-04-15T09:00:00Z"),
  actorId: "staff-016",
  operation: "CHANGE_PREMIUM",
  reason: "Terms adjustment",
  requestId: "req-change-492"
}
~~~

This document illustrates **data shape**, not automatic server output on updates. MongoDB does not automatically maintain a history collection for every `updateOne`. The application or write pipeline must save it explicitly. In this example, revision 1 is saved when advancing current to revision 2; current holds the latest version.

### 6.3. Why Save Full Prior Snapshots Instead of Only Changed Fields?

A full snapshot lets you read any revision directly without replaying all prior changes. The trade-off is larger history storage, especially for wide documents. If an entity has many unchanged fields and very high mutation rates, you can store deltas/events or take periodic snapshots, though state reconstruction becomes more complex.

A useful snapshot includes every field needed to "review past state," **without necessarily copying every internal technical field or secret**. Rules for personal data, encryption, and retention must be applied specifically.

### 6.4. Reference by ID; Never Embed Unbounded History

The current document can carry lightweight metadata such as `lastChangedBy` and `revision`, without embedding the entire history array. History documents reference `entityId`. This allows:

- Simple current-state lookups by `_id`.
- Paginating history via dedicated indexes.
- Adjusting history retention/archiving without touching the current collection.
- Enforcing separate access control for live user-facing data versus audit records.

## 7. Writing Current and History Consistently Under Concurrent Requests

If you merely run:

~~~text
1. Read current revision 1
2. Insert history revision 1
3. Update current to revision 2
~~~

a failure between steps 2 and 3 can leave an extra history record while state never changed—or if reversed, current changes while history is missing. Two concurrent requests could also read the same revision and overwrite each other.

### 7.1. Optimistic Concurrency with `revision`

A conditional update:

~~~javascript
const result = db.policies.updateOne(
  { _id: "policy-1001", revision: 1 },
  {
    $set: {
      "terms.premium": NumberDecimal("1500000.00"),
      updatedAt: new Date()
    },
    $inc: { revision: 1 }
  }
)

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount
})
~~~

If another request already bumped `revision` from 1 to 2, the filter misses and `matchedCount` is 0. The application must return a conflict error or reload current state, **never blindly retrying with the new revision without resolving the business conflict**.

This snippet only protects the current write; **it does not write history yet**.

### 7.2. Multi-Document Transactions

When current and history live in two collections, you can update both inside **a single transaction** on a MongoDB deployment supporting transactions. The example below assumes `policy-1001` is at initial `revision: 1` and is not re-run after succeeding.

~~~javascript
use document_history_lab

const session = db.getMongo().startSession()

try {
  await session.withTransaction(async () => {
    const txDb = session.getDatabase("document_history_lab")
    const current = await txDb.policies.findOne({
      _id: "policy-1001"
    })

    if (!current) {
      throw new Error("POLICY_NOT_FOUND")
    }
    if (current.revision !== 1) {
      throw new Error("REVISION_CONFLICT")
    }

    const changedAt = new Date()
    const update = await txDb.policies.updateOne(
      { _id: current._id, revision: current.revision },
      {
        $set: {
          "terms.premium": NumberDecimal("1500000.00"),
          updatedAt: changedAt
        },
        $inc: { revision: 1 }
      }
    )

    if (update.matchedCount !== 1) {
      throw new Error("REVISION_CONFLICT")
    }

    await txDb.policy_history.insertOne({
      entityId: current._id,
      revision: current.revision,
      schemaVersion: current.schemaVersion,
      snapshot: {
        customerId: current.customerId,
        terms: current.terms,
        status: current.status,
        createdAt: current.createdAt,
        updatedAt: current.updatedAt
      },
      capturedAt: changedAt,
      actorId: "staff-016",
      operation: "CHANGE_PREMIUM",
      reason: "Terms adjustment",
      requestId: "req-change-492"
    })
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })
} finally {
  await session.endSession()
}
~~~

**Execution requirements:** Multi-document transactions require a replica set or sharded cluster supporting transactions; do not run this verbatim on a regular standalone instance. Inside transactions, logic must handle transient errors, write conflicts, and uncertain commit states per driver APIs. The transaction helper may retry the callback on certain errors: keep side effects outside MongoDB—such as sending emails or charging cards—out of the callback.

**Expected post-transaction state:** after committing, current is at revision 2 and history holds the revision 1 snapshot. If any operation fails and the transaction aborts, neither change is committed.

### 7.3. When Two Users Edit the Same Policy Concurrently

~~~text
Initial state: revision = 3

User A reads revision 3
User B reads revision 3

User A: UPDATE {_id, revision: 3} -> revision 4  [succeeds]
User B: UPDATE {_id, revision: 3} -> no match    [conflict]
~~~

Without a revision guard, request B would overwrite A's change in a **lost update**. The revision guard surfaces the conflict; the application still decides whether to merge, ask the user to re-submit, or display a clear error.

### 7.4. Request ID and Idempotency

A revision guard handles concurrency; **idempotency** handles a request resent due to timeout/retry. These are distinct problems. Suppose a client sends `requestId: "req-change-492"`, the server commits, and the client disconnects before receiving the response. On retry, the application must recognize the request was already processed and return the corresponding result instead of applying another edit.

You can use an idempotency-key collection with a business-scoped unique index, or enforce unique operation IDs in the event/history stream. Explicitly model states for in-progress, completed, and retriable failures. Never rely solely on timestamps or assume clients will not send duplicates.

## 8. Querying Current and Historical Versions

### 8.1. Reading Current State

~~~javascript
db.policies.findOne({ _id: "policy-1001" })
~~~

A single current document lets routine business APIs avoid scanning all versions.

### 8.2. Listing History by Revision

~~~javascript
db.policy_history.find(
  { entityId: "policy-1001" },
  {
    entityId: 1,
    revision: 1,
    capturedAt: 1,
    operation: 1,
    actorId: 1
  }
).sort({ revision: -1 }).limit(20)
~~~

The index `{entityId: 1, revision: 1}` supports fetching an entity's revision chain; MongoDB can traverse index order in either direction when appropriate. Verify with `explain("executionStats")` on representative data.

### 8.3. Viewing a Specific Revision

~~~javascript
const revisionNumber = 1

const historical = db.policy_history.findOne({
  entityId: "policy-1001",
  revision: revisionNumber
})

printjson(historical && historical.snapshot)
~~~

Under the "history holds past versions" design, the current revision **does not necessarily exist in `policy_history`**. A "get revision" API must check current first or route to history when a lower revision is requested.

### 8.4. Deep Pagination by Revision

Avoid using `skip(1000000)` as the primary strategy for very long streams. Use keyset pagination:

~~~javascript
const lastSeenRevision = 120

db.policy_history.find({
  entityId: "policy-1001",
  revision: { $lt: lastSeenRevision }
}).sort({ revision: -1 }).limit(20)
~~~

`revision` increases monotonically **within a single entity**; never assume global cross-entity ordering. When paginating history across multiple entities, use a stable sort key with a tie-breaker—such as `recordedAt + _id`—paired with a matching index.

## 9. Model C — Append-Only Event Log and Event Sourcing

The question is not always "what value did the document hold?" Some systems need to know **what happened**:

~~~javascript
{
  _id: "evt-policy-1001-0002",
  aggregateId: "policy-1001",
  sequence: 2,
  type: "PolicyPremiumChanged",
  eventVersion: 1,
  occurredAt: ISODate("2026-04-15T08:58:00Z"),
  recordedAt: ISODate("2026-04-15T09:00:00Z"),
  actorId: "staff-016",
  requestId: "req-change-492",
  payload: {
    previousPremium: NumberDecimal("1200000.00"),
    newPremium: NumberDecimal("1500000.00"),
    currency: "VND"
  }
}
~~~

Events emphasize the business action `PolicyPremiumChanged`, whereas snapshots emphasize state at a revision. An event log can serve auditing; **event sourcing** goes further by reconstructing current state from the event sequence via event application rules.

~~~mermaid
flowchart LR
    Command["Change command"] --> Validation["Business / concurrency check"]
    Validation --> Events["Append ordered event"]
    Events --> Projector["Projector / Reducer"]
    Projector --> Current["Current state projection"]
    Events --> Replay["Replay history"]
    Replay --> Restored["State at sequence N"]
~~~

### 9.1. Required Structure and Indexes

~~~javascript
use document_history_lab

db.policy_events.createIndex(
  { aggregateId: 1, sequence: 1 },
  { unique: true, name: "uq_aggregate_sequence" }
)

db.policy_events.createIndex(
  { requestId: 1 },
  { unique: true, name: "uq_event_request_id" }
)
~~~

A collection-wide unique index on `requestId` is only valid when each request emits **at most one event in that collection**. If one request emits multiple events, use a compound key like `requestId + eventOrdinal`, or a separate idempotency ledger. Index choices must mirror real idempotency boundaries.

### 9.2. Replaying Requires More Than Just an Event List

For reliable reconstruction:

- Events have a **deterministic order** within the aggregate, e.g., `sequence`.
- Recorded events adhere to explicit payload contracts and are not arbitrarily mutated.
- Reducers handle every published `eventVersion` or use compatible upcasters.
- Events apply semantically once at the projection layer; handle duplicates and retries.
- Changes to reducer logic over time must be managed; replaying old events through new logic can yield different outcomes if uncontrolled.
- Events triggering external side effects need reliable delivery, such as an outbox and idempotent consumers.

### 9.3. Event Sourcing Is Not Free

With 100,000 events on an entity, replaying from event #1 on every read is too expensive. You can create a **snapshot every N events**:

~~~javascript
{
  _id: "policy-1001-snapshot-500",
  aggregateId: "policy-1001",
  lastAppliedSequence: 500,
  schemaVersion: 2,
  state: {
    status: "ACTIVE",
    premium: NumberDecimal("1500000.00")
  },
  createdAt: ISODate("2026-06-01T00:00:00Z")
}
~~~

Reconstruct state by loading the latest snapshot **not exceeding the target sequence**, then applying events after `lastAppliedSequence`. Snapshots must be validated against the source event stream; never discard older events merely because a snapshot exists if audit or recovery policies still require them.

### 9.4. Distinguish Event Logs from Change Streams

MongoDB **Change Streams** let applications watch changes on a collection/database/cluster in supported topologies. They are well suited for reactive workflows, syncing projections, or certain pipelines; they are **not automatically a permanent audit store**:

- Change Streams track changes over a resumable window tied to oplog retention and deployment capabilities.
- Consumers must persist resume tokens, handle retries, and tolerate redelivering/reapplying changes.
- If a consumer stops too long, its resume token can become invalid.
- Pre/post-images require explicit configuration and version support; previous values are not always included by default.
- Technical events like "document updated" rarely carry business semantics like "why the premium was adjusted."

If you need long-term audit history, **explicitly design a durable event/history store** and accurate write pipeline rather than relying on the oplog or change streams as the sole historical record.

## 10. Model D — Time-Effective (Temporal) Data

Some domains must query "price valid on date D" or "policy effective when the transaction occurred," even after newer prices have been published.

Example `price_periods` collection:

~~~javascript
db.price_periods.insertMany([
  {
    productId: "product-001",
    price: NumberDecimal("100000.00"),
    currency: "VND",
    validFrom: ISODate("2026-01-01T00:00:00Z"),
    validTo: ISODate("2026-04-01T00:00:00Z"),
    recordedAt: ISODate("2025-12-20T09:00:00Z"),
    revision: 1
  },
  {
    productId: "product-001",
    price: NumberDecimal("120000.00"),
    currency: "VND",
    validFrom: ISODate("2026-04-01T00:00:00Z"),
    validTo: null,
    recordedAt: ISODate("2026-03-15T09:00:00Z"),
    revision: 2
  }
])
~~~

Querying the price effective on May 15:

~~~javascript
const t = ISODate("2026-05-15T00:00:00Z")

db.price_periods.find({
  productId: "product-001",
  validFrom: { $lte: t },
  $or: [
    { validTo: { $gt: t } },
    { validTo: null }
  ]
})
~~~

Reference index:

~~~javascript
db.price_periods.createIndex({
  productId: 1,
  validFrom: -1
})
~~~

This index helps locate intervals starting before the query timestamp; still measure how many candidates the `validTo` check inspects. **No single generic index optimizes every interval-overlap query**.

### 10.1. Retroactive Corrections Complicate the Model

Suppose in June you discover the price effective since April was entered incorrectly. Overwriting the April period directly erases proof of **what the system believed was true before the correction**.

Two distinct queries exist:

1. **As-effective:** What is the business-effective price on April 15 after all adjustments?
2. **As-known:** On April 20, what price did the system actually have recorded?

Answering both may require bitemporal records tracking both valid and recorded intervals, or correction events linked to revisions. This is an advanced pattern requiring precise query definitions before adoption.

### 10.2. Store Transaction Snapshots Independent of Current Prices

In orders, store the locked price:

~~~javascript
{
  _id: "order-2026-001",
  createdAt: ISODate("2026-04-15T09:00:00Z"),
  lines: [
    {
      productId: "product-001",
      qty: 2,
      unitPrice: NumberDecimal("120000.00"),
      currency: "VND"
    }
  ],
  total: NumberDecimal("240000.00")
}
~~~

If the product catalog later changes prices, **`unitPrice` on a confirmed order remains a historical snapshot**. Define which edits are permitted on finalized orders; if adjustments are required, use revisions, credit/adjustment notes, or events rather than untracked overwrites.

## 11. Schema Versioning to Read Data Across Years

Suppose in year one the system stored:

~~~javascript
// schemaVersion 1
{
  _id: "profile-001",
  schemaVersion: 1,
  fullName: "Nguyen Lan",
  phone: "0900000000"
}
~~~

Later, the application moved to:

~~~javascript
// schemaVersion 2
{
  _id: "profile-001",
  schemaVersion: 2,
  person: {
    displayName: "Nguyen Lan"
  },
  contacts: {
    primaryPhone: "0900000000"
  }
}
~~~

If history/archive holds both formats, code expecting only v2 will fail on v1 snapshots. Three basic strategies exist:

| Strategy | How It Works | Trade-offs |
|---|---|---|
| **Eager migration** | Backfill old documents to the new layout | Heavy I/O, risk of mutating history, rollback complexity |
| **Lazy migration** | Upgrade old documents on read/write per rules | Prolonged mixed-schema window, concurrency handling required |
| **Read-time upcasting** | Keep raw stored data; transform to current app model on read | Preserves original bytes; must maintain versioned converters |

Example read-only upcaster that never overwrites stored documents:

~~~javascript
function toProfileView(doc) {
  if (doc.schemaVersion === 1) {
    return {
      id: doc._id,
      displayName: doc.fullName,
      phone: doc.phone
    }
  }

  if (doc.schemaVersion === 2) {
    return {
      id: doc._id,
      displayName: doc.person.displayName,
      phone: doc.contacts.primaryPhone
    }
  }

  throw new Error("UNSUPPORTED_SCHEMA_VERSION")
}
~~~

**Do not blindly overwrite historical documents to upgrade schemas.** When history serves as original evidence, keep raw payloads, `schemaVersion`, and conversion metadata; the application can render normalized views without destroying source records. If regulations require erasing/anonymizing personal data, apply those policies across historical stores as well.

### 11.1. Schema Evolution for Long-Term Archives

Ten years later, an archive needs:

- Encoding and schema/format versions for each data batch.
- Field descriptions, timezones, currency units, and decimal rounding rules.
- Tools or documentation to decode exported BSON/JSON/Parquet/other formats.
- Checksums/integrity metadata and provenance.
- Plans for retiring unsupported software versions.
- Actual read/restore verification drills, not just trusting archive filenames.

Keeping files without their schemas or decoders can render archived data unusable.

## 12. Very Long-Running Growth: Do Not Store Everything in One Document

A sensor system may record thousands of measurements per hour. This model leads to trouble:

~~~javascript
// For anti-pattern illustration only.
{
  _id: "sensor-001",
  readings: [
    { at: ISODate("2026-01-01T00:00:00Z"), value: 23.1 },
    { at: ISODate("2026-01-01T00:01:00Z"), value: 23.2 }
    // ... array growing without bound over months and years
  ]
}
~~~

The document grows toward the 16 MiB BSON limit and every read/write handles an ever-larger structure. Alternative models:

### 12.1. One Event/Measurement per Document

~~~javascript
{
  sensorId: "sensor-001",
  measuredAt: ISODate("2026-01-01T00:00:00Z"),
  temperatureC: 23.1
}
~~~

Benefits include simpler range queries, time-based retention, and flexible sharding/archiving. The trade-off is larger document and index entry counts.

### 12.2. Bounded Bucket Pattern

Group readings by day/hour/device, with explicit caps:

~~~javascript
{
  _id: "sensor-001:2026-01-01:00",
  sensorId: "sensor-001",
  bucketStart: ISODate("2026-01-01T00:00:00Z"),
  bucketEnd: ISODate("2026-01-01T01:00:00Z"),
  count: 2,
  readings: [
    { at: ISODate("2026-01-01T00:00:00Z"), value: 23.1 },
    { at: ISODate("2026-01-01T00:01:00Z"), value: 23.2 }
  ]
}
~~~

Buckets reduce metadata/index entries compared to individual documents in some workloads, yet require enforcing count/size limits, handling concurrent bucket writes, and range filtering. Oversized buckets still hit 16 MiB.

### 12.3. Time-Series Collections

For timestamped measurements with source metadata, MongoDB offers **time-series collections**. Example:

~~~javascript
use document_history_lab

db.createCollection("sensor_measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "sensor",
    granularity: "minutes"
  }
})

db.sensor_measurements.insertOne({
  measuredAt: ISODate("2026-01-01T00:00:00Z"),
  sensor: {
    sensorId: "sensor-001",
    location: "warehouse-A"
  },
  temperatureC: 23.1
})
~~~

Time-series collections are built for time-series workloads with dedicated internal storage layouts. Update/delete capabilities, indexing, sharding, and retention differ from regular collections and vary by server version. **Never pick time-series merely because a document has a date field**; verify workload and feature requirements.

## 13. Long-Term Storage: Hot, Warm, and Cold Tiers

Multi-year data does not all have to sit in the same collection serving daily requests. You can tier storage:

~~~mermaid
flowchart LR
    Ingest["Data source / API"] --> Hot["HOT: current / recent history"]
    Hot -->|"Retention / archive job"| Warm["WARM: infrequently queried history"]
    Warm -->|"Verified archive job"| Cold["COLD: object storage / archival system"]
    Catalog["Archive catalog / manifest"] --> Cold
    Query["Historical query"] --> Hot
    Query --> Warm
    Query --> Restore["Archive lookup & restore service"]
    Restore --> Cold
~~~

| Tier | Contents | Access Characteristics | Design Decisions |
|---|---|---|---|
| **Hot** | Current state, recent history | Direct queries, low-latency SLA | API indexes, working set sizing, HA |
| **Warm** | Older revisions/events still queried occasionally | Lower query rate, higher latency tolerated | Separate collection/cluster, minimal indexes, batching |
| **Cold** | Rarely accessed data kept for years | Lookup via manifest then read/restore | Format, checksums, encryption, permissions, retrieval cost |

Do not hardcode 30/90/365-day thresholds for every system. Policies must reflect real requirements and retention obligations:

- Payment/tax/contract records may require multi-year retention.
- Telemetry may need per-minute detail for weeks, then aggregated summaries.
- Certain personal data must be erased under policy or valid user requests.
- Data under dispute investigation may be placed on **legal hold**, suspending normal retention deletions.

### 13.1. Metadata for an Archive Batch

Example manifest:

~~~javascript
{
  _id: "archive-policy-history-2025-q1",
  dataset: "policy_history",
  fromRecordedAt: ISODate("2025-01-01T00:00:00Z"),
  toRecordedAtExclusive: ISODate("2025-04-01T00:00:00Z"),
  objectUri: "archive://policies/2025/q1/history-v1",
  format: "BSON",
  formatVersion: 1,
  schemaVersions: [1, 2],
  documentCount: 258900,
  checksumAlgorithm: "SHA-256",
  checksum: "<checksum-of-archive>",
  exportedAt: ISODate("2026-04-01T00:00:00Z"),
  retentionUntil: ISODate("2033-04-01T00:00:00Z"),
  state: "VERIFIED"
}
~~~

`objectUri` is a conceptual address, not a built-in MongoDB API URI. The application needs an archive service or custom export/restore workflow. The `checksum` field must also specify **over which exact bytes and ordering it is computed**; a placeholder string does not prove integrity.

### 13.2. Archives Must Preserve Discoverability

If archived data only exists as daily files, how do you locate the history of `policy-1001`?

A viable design includes:

- Manifests indexed by time range, tenant, collection, or partition.
- A catalog/index mapping `entityId` or business keys to archive batches.
- A lookup router determining whether requested data sits in hot, warm, or cold storage.
- A retrieval pipeline handling decryption, checksum verification, and format-version parsing.
- Access controls matching or stricter than the live database.

**Data stored in an archive that cannot be located or decoded is incomplete archival.**

## 14. Safe, Idempotent Archival Workflows

Never do this:

~~~text
1. Delete all old documents from MongoDB.
2. Then try exporting them to files.
~~~

If export fails, data is permanently lost. A safer pipeline:

1. **Select cutoff:** e.g., history with `capturedAt < T` and not under legal hold; fix timezone, filter predicates, and batch snapshot scope.
2. **Mark / checkpoint job:** assign a batch ID and identify target documents by stable keys rather than fragile offsets.
3. **Export data:** use a versioned format with controlled ordering/metadata; write to authorized storage.
4. **Verify:** validate record count, checksum, key ranges, and schema versions; sample-read records back from the archive.
5. **Publish manifest:** mark `VERIFIED` only once files and metadata are ready, recording storage locations.
6. **Allow online deletion:** after verifying retention rules, legal holds, replicas, and restore checks; delete in rate-limited batches.
7. **Re-verify and monitor:** detect unmoved documents, duplicate exports, or retry needs.

~~~mermaid
flowchart TD
    Select["Select batch and cutoff"] --> Export["Export to archive"]
    Export --> Verify{"Checksum + count + readback valid?"}
    Verify -->|"No"| Retry["Alert / idempotent retry"]
    Retry --> Export
    Verify -->|"Yes"| Manifest["Publish VERIFIED manifest"]
    Manifest --> Policy{"Retention / legal hold allows deletion?"}
    Policy -->|"No"| Keep["Keep online or hold"]
    Policy -->|"Yes"| Delete["Batch-delete online records"]
    Delete --> Audit["Readback, audit, metrics"]
~~~

### 14.1. Idempotency of Archive Jobs

Archive jobs may rerun after timeouts, restarts, or failovers. Ensure:

- Deterministic batch IDs so retries do not emit conflicting manifests for the same data.
- Deterministic document keys, fixed cutoffs, and stable selection rules.
- Exports/retries do not alter content unpredictably.
- Online deletion runs only after the archive is verified readable.
- Per-document errors are logged with resume support.

For **still-mutable** data, requirements are stricter. Archive only closed/immutable documents, or use freeze states, version/cutoff transactions, and reconciliation so mid-export updates are never missed.

### 14.2. Counts Alone Do Not Prove Correctness

If an export writes 10,000 documents by duplicating one document and dropping another, `documentCount` still equals 10,000. Combine key-set/unique-ID checks, deterministic checksums, schema metadata checks, and restore tests. The higher the compliance bar, the more independent verification should be from the export job itself.

## 15. TTL, Retention, and Data Deletion Rules

MongoDB offers **TTL indexes** to automatically remove documents after an age threshold. Example for logs using creation time:

~~~javascript
db.transient_events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 60 * 60 * 24 * 30 }
)
~~~

For documents with a BSON Date `createdAt`, TTL deletes them once older than 30 days. However:

- The TTL monitor runs in the background, so it **does not promise second-exact deletion at expiration**.
- TTL **deletes data**; it does not export or archive it.
- Enabling TTL without a verified archive can violate long-term retention rules.
- TTL is unsuitable for per-document legal holds or complex variable retention rules.
- TTL indexes and partial filter support have version-, collection-type-, and schema-specific constraints.
- For time-series collections, TTL/expiry options follow separate rules; check your server version and collection type.

### 15.1. Distinguish Storage Retention, Online Lookup Window, and Deletion Deadline

Example:

~~~text
Transaction date:                 2026-01-01
Fast online lookup until:         2027-01-01
Archive retention until:          2033-01-01
Policy-driven deletion/anonymize: after retention obligation expires
~~~

In this case, never put a one-year TTL on the **only copy** of a transaction that must be kept until 2033. Move data to warm/cold tiers after one year, retain manifests, and delete only once obligations expire with no legal holds.

### 15.2. Soft Delete Does Not Equal Physical Deletion

~~~javascript
db.policies.updateOne(
  { _id: "policy-1001" },
  {
    $set: {
      deletedAt: new Date(),
      status: "DELETED"
    }
  }
)
~~~

This is a **soft delete**: the document still exists and may remain in backups, history, logs, and archives. When fulfilling valid personal-data erasure requests, scope every copy and retention policy rather than treating `deletedAt` as proof of system-wide removal.

## 16. Indexes for Long-Term History Queries

History can grow hundreds of times larger than current data. You cannot blindly copy current collection indexes onto history and assume optimal performance.

| Common Query | Index to Consider | Notes |
|---|---|---|
| View revisions of an entity | `{entityId: 1, revision: -1}` | Paginate by revision; can be unique |
| View entity history over time | `{entityId: 1, capturedAt: -1}` | Needs a tie-breaker key for stable sort if timestamps collide |
| Find events of an aggregate | `{aggregateId: 1, sequence: 1}` | Enforces unique sequence per aggregate |
| Query logs by tenant and time | `{tenantId: 1, recordedAt: -1}` | At large scale, evaluate sharding/retention |
| Scan archive batches by cutoff | Index supporting `capturedAt` and partition range | Create only if needed by jobs to avoid write amplification |
| Find price by effective interval | Index leading with business key and valid time | Overlap queries must be benchmarked |

### 16.1. Illustrating Query Plan Inspection

~~~javascript
db.policy_history.find({
  entityId: "policy-1001",
  revision: { $lt: 100 }
}).sort({ revision: -1 }).limit(20)
  .explain("executionStats")
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. On tiny collections, MongoDB may pick a collection scan; never judge index effectiveness on a few sample documents.

### 16.2. History Growth and Index Size

Every revision creates a new document, growing history indexes too. Plan around:

- Revision/event creation rate per second and per year.
- Average snapshot size and data duplication factor.
- Compressor choice, disk footprint, and decompression CPU.
- Number of indexes maintained under continuous writes.
- RAM/cache sizing and hot working set.
- Retention/archival, backups, replica sets, and restore times.

If history only serves rare audits, avoid adding many indexes for arbitrary ad-hoc filters to reduce write and storage costs. In exchange, expose deterministic lookup paths such as by `entityId` or partitioned time ranges.

## 17. Integrity, Auditing, and Security

History models used for auditing must prioritize **accuracy and traceability**.

### 17.1. Typical Audit Fields

| Field | Meaning | Notes |
|---|---|---|
| `entityId` | Modified entity | Stable ID across all revisions |
| `revision` / `sequence` | Change order | Must have generation rules and uniqueness |
| `actorId` | Who triggered the action | May be a service account or system job |
| `operation` | Business change type | Use meaningful names, not merely "update" |
| `reason` | Reason for change | May be mandatory for sensitive operations |
| `recordedAt` | System recording timestamp | Synchronized clocks, stored as BSON Date |
| `requestId` / `correlationId` | Links logs and requests | Supports idempotency and investigation |
| `schemaVersion` / `eventVersion` | How to parse payload | Essential for reading old history |
| `oldValue` / `newValue` or `snapshot` | Changed content | Store only needed data; minimize sensitive fields |

### 17.2. Append-Only Must Be Protected by Access Controls

"Append-only" is an **application/workflow convention**; regular MongoDB collections can still be modified or dropped by accounts with sufficient privileges. For tamper-resistant auditing:

- Separate application write privileges from administrative privileges.
- Restrict updates/deletes on history at both database permission and service layers.
- Ship audit copies to an independently protected store when high assurance is needed.
- Use checksums/signatures or immutable/WORM archival storage per organizational standards if required.
- Log access, permission changes, exports, and deletions.

Never treat a unique index or an application-level `immutable: true` field as a security guarantee against privileged administrators.

### 17.3. History May Retain Sensitive Data That Was Edited or Removed

If a user once mistyped a phone number and later updated it, both numbers may remain in history. Policies must define:

- Who may view historical values?
- When must a field be masked or purged from history?
- Which fields require encryption and key management?
- Are there legal retention exceptions or legal holds?
- Do backups and archives comply with the same retention and access controls?

Audit goals do not grant blanket permission to retain all personal data indefinitely.

## 18. History Is Not Backup, and Backup Does Not Replace History

Two distinct purposes:

| Component | Question Answered | Limitations |
|---|---|---|
| History collection | "How did this entity change over time?" | Can be accidentally dropped/corrupted alongside the DB |
| Audit event stream | "Who created which event, in what order?" | Must protect integrity and handle event schemas |
| Replica set | "Can the system keep serving if a node fails?" | Replicates accidental deletions and bad writes too |
| Backup | "Can data be restored after an outage or data loss?" | Bound by RPO/RTO, scope, and restore testing |
| Archive | "Can cold data be retained and retrieved years later?" | Needs manifest, format, permissions, checksums, readability |

A history collection on the same cluster as current can be lost simultaneously due to misconfiguration or a dropped database. Conversely, daily backups restore an entire database yet cannot easily answer "Who changed the product price at 09:12?" Both tools complement each other.

### 18.1. RPO and RTO for History Systems

- **RPO:** acceptable data loss in an outage; critical audits may require very low RPO.
- **RTO:** maximum time to restore the system and lookup capability.

Test restores across **current, history, indexes, and version metadata**, not just the current collection. When archives live externally, test downloading, decrypting, and verifying checksums.

## 19. Migrations and Compatibility Across Application Releases

A sound design must survive many software releases.

### 19.1. Expand–Migrate–Contract Releases

Example renaming `premium` to `terms.premium`:

1. **Expand:** new app version reads both old and new schemas, writing the target format under clear rules.
2. **Migrate:** backfill current documents in batches, checkpoint progress, and validate edge cases.
3. **Contract:** once nothing depends on the old field, retire compatibility code on current data as planned.

History/archives may still preserve original formats, so **old schema readers** cannot necessarily be deleted at the same time as old write code.

### 19.2. Schema Migration Is Not a Business Change

When merely relocating `premium` to `terms.premium` without changing business value or meaning, do not automatically bump business `revision` or emit a "fee adjusted" event. Record separate migration metadata if needed. Conversely, if a migration alters business meaning, explicitly define its audit and revision impact.

### 19.3. Testing Reads Against Real Historical Data

A regression test suite should include:

- Current documents in the latest schema.
- Snapshots across multiple older `schemaVersion` values.
- Events across multiple `eventVersion` values.
- Records with valid legacy nulls, missing fields, or legacy types.
- Data restored from archives.

The goal is catching early when a new release can no longer decode historical records.

## 20. Cost and Complexity of Design Options

To choose a model, estimate **historical volume**, not just current documents.

Assumptions:

~~~text
Entities:                     2,000,000
Average changes/year:         6 per entity
Logical snapshot size:        3 KiB
Retention period:             7 years
~~~

Estimated revision count:

~~~text
2,000,000 × 6 × 7 = 84,000,000 history documents
~~~

Estimated logical snapshot volume (excluding metadata, indexes, compression, replicas, backups):

~~~text
84,000,000 × 3 KiB
≈ 240 GiB logical snapshot data
~~~

This is illustrative only. With 0.3 KiB event deltas, logical size can be much smaller, yet replay, `eventVersion` management, and projections take more effort. Snapshots give direct revision queries in exchange for larger data duplication.

### Calculating Total Cost by Requirements

~~~text
Multi-year storage cost =
  current data
  + history/events/snapshots
  + indexes and metadata
  + replication
  + backups/retention
  + cold archive
  + CPU/I/O for writes, queries, exports, and restores
~~~

Compression shrinks physical disk footprint in many cases, yet does not eliminate CPU overhead, query planning, lookup latency, or tiering strategy.

## 21. Common Design Scenarios

### Scenario A — Product Prices Change, Yet Past Orders Must Stay Accurate

**Requirement:** Update catalog prices frequently while preserving locked prices on every order.

**Model:** `products` holds current prices, `product_price_history` tracks price changes or effective intervals, and `orders.lines[].unitPrice` stores a snapshot independent of the catalog. Never retroactively join old orders to `products.price`.

**Troubleshooting:** If old order totals shift after a catalog edit, check whether the app is recalculating from live prices instead of reading stored snapshots.

### Scenario B — Contracts Must Show the "Version Effective on Date D"

**Requirement:** View the terms in effect when an incident or dispute occurred.

**Model:** Current + revision history, or effective-date intervals; use bitemporal records if retroactive edits occur. History tracks actor, reason, and `schemaVersion`. Queries over `validFrom/validTo` must handle overlaps and timezones.

**Risk:** Simply sorting by most recent `updatedAt` will not reliably select the terms effective on a past date.

### Scenario C — Application Config Requires Rollback

**Requirement:** After deploying a broken config, revert to a prior version.

**Model:** Current + history snapshots; every change records `revision` and deployment metadata. Record a rollback as **a new revision** copying content from the target older revision so the full change sequence remains visible; never silently delete intermediate revisions.

**Risk:** Overwriting current with an old snapshot without logging the rollback breaks the audit trail.

### Scenario D — Billions of Telemetry Events, Mostly Querying Last 30 Days

**Requirement:** Fast dashboards for recent data, multi-year statistical retention.

**Model:** Time-series or event collections optimized for ingestion, indexed by sensor/tenant/time, short online retention, and long-term aggregates/archives. Control payloads, `schemaVersion`, and catalog metadata. Use TTL only on data with an explicit deletion policy.

**Risk:** Appending all readings into an array on one device document causes unbounded growth and hits the 16 MiB limit.

### Scenario E — Audit Records Must Survive Account Deletion

**Requirement:** Investigate system actions while complying with personal data laws.

**Model:** Audit events with appropriate actor IDs/pseudonymous tokens, isolated permissions, retention rules, and policy-driven anonymization/deletion. Avoid stuffing unnecessary PII in payloads; balance erasure requests against legal retention duties.

**Risk:** History becomes an unbounded stash of sensitive personal data already erased from current tables.

## 22. Practice Lab: Building Contract Change History

Follow these steps in order on a **lab database**. The transaction portion requires a replica set or sharded cluster; on a standalone instance, run the schema/query steps and trace the transaction logic conceptually.

### Part 1 — Setup

~~~javascript
use document_history_lab

db.createCollection("policies")
db.createCollection("policy_history")

db.policies.insertOne({
  _id: "lab-policy-001",
  revision: 1,
  schemaVersion: 1,
  status: "ACTIVE",
  terms: {
    premium: NumberDecimal("500000.00"),
    currency: "VND"
  },
  createdAt: ISODate("2026-01-01T00:00:00Z"),
  updatedAt: ISODate("2026-01-01T00:00:00Z")
})

db.policy_history.createIndex(
  { entityId: 1, revision: 1 },
  { unique: true }
)
~~~

If you already ran earlier snippets, collections/indexes may exist; use a fresh lab database or adjust names. Do not delete data you do not own just to rerun the exercise.

### Part 2 — Design the Update Workflow

Each policy edit must:

1. Accept `entityId`, `expectedRevision`, `requestId`, actor, and proposed changes.
2. Authenticate and validate business rules.
3. Inside a transaction: read current, verify `expectedRevision`, conditionally update current, and insert the old snapshot into `policy_history`.
4. Enforce uniqueness on `entityId + revision` and business-scoped idempotency on `requestId`.
5. After commit, return the new revision and final state to the client.

### Part 3 — Execute and Observe

Perform at least three valid edits on `lab-policy-001` with incrementing revisions, recording different actors and reasons. Also test:

- A request using an old `expectedRevision` and confirm it triggers a conflict.
- Resending a duplicate `requestId` and verifying how the same result is returned without creating a new edit.
- Reading current and revisions 1 and 2 from history.
- Querying the 20 latest revisions and simulating keyset pagination.
- Updating display format v1 → v2 via an upcaster while keeping old snapshots intact.

### Part 4 — Design the Archive

Assume after two years, old history moves to cold storage yet must be kept for seven years.

Write a batch archive design covering:

- Cutoff by timestamp and finalized status.
- Rules excluding records under active edits or legal holds.
- Export with `schemaVersion`, checksums, and key lists.
- Manifest with status, counts, ranges, URI, and `retentionUntil`.
- Sample read verification and restore testing before online deletion.
- Idempotency/checkpointing if the job is interrupted mid-run.
- Lookup path to retrieve archived records by `entityId`.

### Part 5 — Evaluate Outcomes

| Criterion | Required Evidence |
|---|---|
| Accurate current state | One current document holding the highest revision |
| Complete history | Every revision transition saves a snapshot of the replaced version |
| No lost updates | Concurrent updates protected by revision guards |
| No duplicates | Retries handled idempotently with appropriate unique keys |
| Legacy data readable | Revision queries and multi-`schemaVersion` upcaster work |
| Efficient queries | Indexes on entity/revision verified with `explain()` on representative data |
| Recoverable archive | Manifest, checksum, and verified restore drill |
| Compliant retention | No premature TTL/deletion of sole copies; legal holds respected |

## 23. Design Mistakes to Avoid

| Mistake | Consequence | Fix |
|---|---|---|
| Embedding full history in one document | Unbounded document, heavier reads/writes | Cap array or move to a history collection |
| Writing history after current without a transaction | Gap can lose version records | Transaction or outbox/event model with reconciliation |
| Overwriting old revisions during rollback | Audit trail broken | Append a new revision representing the rollback action |
| Using `schemaVersion` as business revision | Broken concurrency and migration logic | Separate `schemaVersion` and business `revision` |
| Using `updatedAt` instead of validity intervals | Wrong historical effective-date answers | Model `validFrom`/`validTo` and `recordedAt` |
| Treating Change Streams as permanent audit storage | Cannot resume/replay distant history | Persist events/history durably in dedicated collections |
| Putting TTL on the sole copy needed for years | Unrecoverable deletion at TTL expiry | Archive and verify before deleting online copies |
| Allowing arbitrary updates/deletes on history | Integrity compromised | Access controls, audit logs, immutable storage when needed |
| Keeping archive files without format/schema docs | Unreadable data after upgrades | Format versions, schema catalog, restore drills |
| Retaining PII indefinitely across all snapshots | Privacy and compliance risk | Data minimization, retention schedules, legal hold handling |
| Indexing every field in history | Bloated index storage and write overhead | Index by real queries and check `executionStats` |
| Treating a replica set as backup | Accidental deletions replicate immediately | Independent backups and tested restores |

## 24. Review Questions

**1. When should history be split into a separate collection?**

When history grows over time, needs independent querying/pagination, has a different retention policy than current, or cannot fit within a small bounded array inside the document. MongoDB caps BSON documents at 16 MiB; unbounded arrays are unsuitable.

**2. How do business revision and `schemaVersion` differ?**

Business revision tracks the sequence of business state changes for an entity, often supporting optimistic concurrency. `schemaVersion` identifies the data layout that code must parse or migrate. They do not necessarily increment together.

**3. Why should saving the old snapshot and updating current be inside a transaction?**

Because they mutate two documents/collections and must succeed or fail together. Without multi-document atomicity, a failure between steps leaves current and history out of sync.

**4. How does a history collection differ from an event log?**

History snapshots record state at a given revision; events record actions/transitions that occurred. Event sourcing additionally defines rules to reconstruct current state by replaying events while handling ordering, versioning, and idempotency.

**5. Which two questions do valid time and recorded time answer?**

Valid time answers when data was effective in the business domain. Recorded time answers when the system learned/recorded the data. Retroactive corrections cause those two questions to produce different answers.

**6. Can Change Streams serve as a 10-year audit source?**

No. Change Streams observe changes on supported topologies and resume capability depends on oplog retention and deployment limits. Long-term auditing requires pushing events to durable storage with explicit schemas, versions, and verification.

**7. Why store a price snapshot inside an order?**

So order history does not change when catalog prices update. It preserves the exact transaction state at purchase time.

**8. Does TTL replace archiving?**

No. TTL only deletes documents automatically by age; archiving requires exporting, manifests, integrity checks, permissions, discoverability, and restore capability. Enable TTL only when data is permitted to be deleted and is not the sole required copy.

**9. Why is comparing record counts before/after export insufficient?**

A job can export one record twice and skip another while leaving the total count unchanged. Use key-set/checksum checks alongside sample readbacks and restore drills.

**10. When reverting to an old config, why create a new revision instead of overwriting history?**

Because a rollback is a new state-changing event that must be traceable. Overwriting past revisions erases the audit trail and breaks decision history reconstruction.

**11. When is one event per document better than embedding?**

When event volume is large and continuous, queries filter independently by time/tenant/sensor, and retention is managed independently; embedded arrays must not grow without bound.

**12. What is needed to read an archive years later?**

File locations, format and schema versions, checksums, decryption keys if encrypted, a catalog to look up by entity/time, compatible reader software, and periodic restore drills.

## 25. Pre-Deployment Design Checklist

- [ ] Clarify target questions: revision lookup, action audit, as-of time queries, or long-term retention.
- [ ] Separate business `revision`, `schemaVersion`, and `eventVersion` (if using events).
- [ ] Choose current/history, event log, temporal intervals, or a justified combination.
- [ ] Define exactly when a revision is created and which unique keys enforce uniqueness.
- [ ] Design optimistic concurrency with transactions/idempotency across collections.
- [ ] Never use an unbounded history array inside a single BSON document.
- [ ] Define timestamp fields, timezones, and valid vs. recorded time semantics.
- [ ] Store only required snapshot/event fields and protect sensitive data.
- [ ] Choose indexes based on historical query APIs and archive workloads.
- [ ] Define retention, legal holds, and deletion rules across current/history/archive/backups.
- [ ] Give archives manifests, checksums, versions, lookup paths, and tested restores.
- [ ] Verify the application can read history across multiple `schemaVersion` values.
- [ ] Distinguish replication, history, backups, and archives in operational plans.
- [ ] Measure history/index growth rate, storage costs, restore times, and query latency.

Good history design enables a system to answer **what state existed, which change produced it, when it took effect, and how it can be read back years later**. The key is drawing clean document boundaries, protecting consistency when creating revisions, managing data lifecycles, and verifying lookup/restore paths against realistic scenarios.
