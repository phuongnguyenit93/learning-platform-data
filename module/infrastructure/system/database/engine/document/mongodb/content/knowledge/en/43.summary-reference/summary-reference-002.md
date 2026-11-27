# Decision Matrix for Embedding, Referencing, Atomic Updates, and Transactions in MongoDB

MongoDB lets you organize data as **documents** rather than forcing every entity into separate relational tables. A major advantage is that data commonly read and updated together can reside in a single document and benefit from **single-document write atomicity**. However, just because something can be embedded does not mean it should be, and having two collections does not always require a transaction.

This lesson belongs to the **Summary and Reference** chapter of the **Database Engine Document MongoDB** module and serves as a **decision handbook** for four groups of choices:

1. **Embedding:** placing child data directly inside the parent document.
2. **Referencing:** keeping documents separate and linking them by ID or business key.
3. **Atomic updates:** using update operators, conditional updates, or find-and-modify on a **single document**.
4. **Transactions:** coordinating multiple operations or multiple documents that must commit or abort together, on supported deployments.

These are **not four mutually exclusive options**. A single design can embed a few items in an order, reference product records, use `$inc` to update inventory, and still use a transaction for order creation + inventory deduction if business rules require it.

This guide emphasizes **reference tables, decision trees, behavioral examples, and checklists**. Write-mutating MongoDB commands should only be executed in an authorized test database; never run them in production without an impact assessment, change plan, and proper backups.

## 1. 30-Second Quick Selection Table

| Scenario | Preferred Option to Consider | Why | What Else to Verify |
| --- | --- | --- | --- |
| An order has at most 20 line items; always viewed with the order | **Embed** items | Read and written on the same lifecycle | Size limits, item modifications |
| A customer has millions of orders | **Reference** | History grows without bound | `customerId + date` index, pagination |
| Product price must be preserved as of purchase time | **Embed snapshot** in order | Preserves contract history | Keep separate from current price |
| Product master changes frequently and is used by many orders | **Reference** master | Avoids fan-out updates | Is a snapshot also needed? |
| Increment view count of an article | **$inc on one document** | Atomic counter update | Hot document contention |
| Deduct inventory only if sufficient stock remains | **Conditional update + $inc** | Check and update in one write | Single warehouse or multiple warehouses? |
| Two users edit the same record by version | **Optimistic locking on one document** | Prevents lost updates | `matchedCount` and retries |
| Remove an element from an order's array | **$pull on document** | Single-document atomic | Does the array grow without bound? |
| Transfer funds between two accounts that must commit together | **Transaction** | Multiple documents must stay consistent | Balances, idempotency, ledger |
| Create booking + reserve vehicle with cross-document invariant | **Transaction combined with contention mechanism** | Commits two coordinated writes | Proper double-booking prevention |
| Send email after creating an order | **Outbox + async worker** | Email is outside DB transaction scope | Idempotency, retries, dedup |
| Total revenue dashboard updated from events | **Derived read model** | Avoids recomputing from scratch | Lag and reconciliation |
| Unbounded audit/payment events | **Separate collection** | Independent lifecycle and pagination | Retention, event immutability |
| Need current user profile when viewing a booking | **Reference or $lookup** | Do not use historical snapshot instead of current profile | Authorization/tenant scope |
| Need to update many documents where eventual consistency is acceptable | **Events/saga or verified batch** | Avoid holding long transactions | SLA, retries, compensation |

**Key takeaway:** the right decision depends on **access patterns + cardinality + lifecycle + consistency invariants**, not merely 1:N relationships or the number of collections.

## 2. Two Separate Decision Axes

Many designs fail by mixing up two distinct questions:

- **Data modeling question:** should the data live in the same document or in separate documents?
- **Consistency question:** which changes must be observed as a single atomic unit?

For example, a booking may have addons embedded inside the booking, whereas reserving a vehicle touches an independent resource. Addons can be updated atomically inside the booking, while guaranteeing the vehicle is not double-booked requires a separate concurrency protocol.

| Storage Model | One Document | Multiple Documents |
| --- | --- | --- |
| One business operation | Update operators or `findOneAndUpdate` | May use a transaction or eventual workflow |
| Multiple business operations | State machine/version on document | Transaction, outbox, saga, or reconciliation per invariant |
| Reading data | Single `find`/projection | Multiple queries, `$lookup`, or read model |
| Common risks | Oversized document, hotspot | Referential drift, partial writes |

### 2.1. Embedding Is a Storage Choice, Not an Absolute Optimization

Embedding reduces joins and round trips, but increases document size, contention, and potential data duplication that is hard to maintain.

### 2.2. Transactions Coordinate Commits; They Do Not Replace Schema Design

Transactions protect a set of cross-document writes, but they carry overhead and do not fix poor queries or poorly bounded lifecycles.

### 2.3. Atomic Updates Do Not Equal System-Wide Consistency

`updateOne` is atomic at the single-document level; it does not cover Redis caches, message brokers, emails, payment gateways, or other documents.

## 3. General Decision Tree

~~~text
Are data A and B usually read together?
  |
  +-- No --> Prefer referencing / load when needed
  |
  +-- Yes
       |
       v
     Are element count and size strictly bounded?
       |
       +-- No --> Separate collection / reference / bucket
       |
       +-- Yes
            |
            v
          Do they share lifecycle, owner, and atomicity needs?
            |
            +-- Yes --> Embedding is a strong candidate
            |
            +-- No --> Reference or selective snapshot
                            |
                            v
                          If fast reads are needed,
                          consider a derived view
~~~

Continue with the write question:

~~~text
What must the business invariant modify?
  |
  +-- One document
  |      |
  |      v
  |   Atomic update + conditional predicate
  |   + version if preventing lost updates
  |
  +-- Multiple documents
         |
         v
       Must all commit or abort together?
         |
         +-- No --> Event/outbox/saga + reconciliation
         |
         +-- Yes
              |
              v
           Transaction on supported topology
           + conflict/uniqueness protection
           + idempotency for retries
~~~

**Decision trees are heuristics.** You must verify actual data sizes, throughput, indexability, security, and failure models.

## 4. Criteria Table: Embedding vs Referencing

| Criterion | Favors Embedding | Favors Referencing |
| --- | --- | --- |
| Access | Always read with parent | Often accessed independently |
| Cardinality | One or a few, with a hard bound | Many or unbounded |
| Lifecycle | Created/deleted with parent | Independent lifecycle |
| Writes | Updated alongside parent | Independent, frequent writes |
| Ownership | Single aggregate owner | Multiple owners/services |
| Master changes | Immutable snapshot or rarely changed | Current master data changes frequently |
| Security | Same permission level | Different access permissions |
| Retention | Same retention policy | Different retention/audit policies |
| Size | Well below limit with headroom | Likely to grow large over time |
| Reverse queries | Rare or well-indexed | Frequently querying children across parents |
| Pagination | No child pagination needed | Children have their own feed/pages |
| Concurrency | Few contending writers | Single parent easily becomes a hotspot |

### 4.1. Special Case: Both Reference and Snapshot

An order has `productId` referencing the product master, along with `itemSnapshot.name` and `itemSnapshot.priceMinor`. When the product changes its name or price, past orders still display what was originally agreed.

### 4.2. Single Documents Still Have Limits

A standard BSON document has a **16 MiB** limit. Do not treat 16 MiB as a target size; leave headroom for future updates, index entries, and network traffic.

### 4.3. Bounded Means Truly Bounded

"Average of only three comments" is not a bound if a single post can receive 100,000 comments. Enforce a hard business cap or use a separate collection.

## 5. 1:N Example: Order and orderItems

Relational model:

~~~text
orders
  id, customer_id, status, total

order_items
  order_id, product_id, qty, unit_price
~~~

If each order has a small number of line items and shares the same lifecycle, embedded model:

~~~javascript
{
  _id: "order-101",
  tenantId: "tenant-a",
  customerId: "customer-15",
  status: "DRAFT",
  items: [
    {
      lineId: "line-1",
      productId: "product-8",
      productNameSnapshot: "Notebook",
      qty: 2,
      unitPriceMinor: NumberLong(50000)
    },
    {
      lineId: "line-2",
      productId: "product-12",
      productNameSnapshot: "Pen",
      qty: 1,
      unitPriceMinor: NumberLong(10000)
    }
  ],
  totalMinor: NumberLong(110000),
  version: 1,
  schemaVersion: 1
}
~~~

### 5.1. Benefits

A single order read returns all line items needed for the detail view; historical unit prices do not change when the product master updates.

### 5.2. Limitations

If `orderItems` becomes a massive feed, develops an independent lifecycle, or reverse queries by line items dominate the workload, evaluate splitting into a separate collection.

### 5.3. totalMinor Invariant

When modifying `items` and `total`, updating the same document can be atomic. However, **atomicity does not automatically guarantee arithmetic correctness**: the application must still validate `total = sum(qty × unitPriceMinor)`, overflow, and currency.

### 5.4. Avoid Unbounded $push

A shopping cart or aggregated log can grow forever if uncapped. Use bounded history, a separate collection, or the bucket pattern when appropriate.

## 6. Example of Embedding a Small Subdocument

A shipping address at order placement time:

~~~javascript
{
  _id: "order-102",
  shippingAddressSnapshot: {
    recipient: "Sample Customer",
    city: "Hanoi",
    postalCode: "100000"
  }
}
~~~

### 6.1. Snapshot Differs From Master Address

A customer changing their profile address must not accidentally alter shipping details of an in-flight order if business rules require preserving history.

### 6.2. PII

Snapshot only the necessary fields and apply retention/redaction policies. Do not embed the entire customer profile into thousands of orders.

### 6.3. Security

An admin API that needs `status` without permission to view addresses should not receive raw documents; use DTOs/projections and authorization checks.

## 7. When Referencing Is the Better Choice

For example, a customer placing many orders over several years:

~~~javascript
// customers
{
  _id: "customer-15",
  tenantId: "tenant-a",
  displayName: "Sample Customer",
  updatedAt: ISODate("2026-01-15T00:00:00Z")
}

// orders
{
  _id: "order-101",
  tenantId: "tenant-a",
  customerId: "customer-15",
  createdAt: ISODate("2026-01-16T00:00:00Z"),
  totalMinor: NumberLong(110000)
}
~~~

History query:

~~~javascript
db.orders.find({
  tenantId: "tenant-a",
  customerId: "customer-15"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

### 7.1. Candidate Index

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
~~~

### 7.2. Why Not Embed Orders Inside Customer?

Order history is unbounded and requires pagination. The customer document would grow continuously and become a contention point for every new order.

### 7.3. Referential Integrity

MongoDB does not enforce foreign-key constraints across collections in the way a typical RDBMS does. Applications, workflows, and reconciliation processes must keep references valid per contract.

## 8. Cardinality Table

| Relationship | Suggested Model | Key Considerations |
| --- | --- | --- |
| 1:1 profile settings, shared lifecycle | Embed | Permissions / write independence |
| 1:few phones, bounded | Embed or reference | Sensitive data |
| 1:few order items | Embed | Item cap and price snapshot |
| 1:many bookings/customer | Reference | Pagination/indexes |
| 1:huge logs/device | Separate collection/bucket | Growth/TTL/time-series |
| Many:many user-role | Bounded IDs or mapping collection | Role ownership/expiry |
| Many:many courses-students | Association collection if relationship has fields | Bidirectional queries |
| 1:huge comments/post | Reference + comment collection | Hot post |
| 1:few addresses | Can embed | Search and edit permissions |
| Events/audit history | Append-only collection | Retention, immutable semantics |

### 8.1. One Relationship Can Have Multiple Representations

A product has a canonical catalog record; order items hold snapshots; search indexes hold derived descriptions. Do not treat these as three competing sources of truth.

### 8.2. Document Every Modeling Choice

For each relationship, record max cardinality, access frequency, update frequency, data owner, source of truth, and deletion policy when a reference is removed.

## 9. Over-Embedding and Alternative Patterns

### 9.1. Unbounded Array Anti-Pattern

~~~javascript
{
  _id: "user-1",
  allOrdersEver: [
    // potentially millions
  ]
}
~~~

Risks: 16 MiB limit, write contention, oversized documents, difficult pagination, difficult archiving.

### 9.2. Subset Pattern

Embed only the most recent few items:

~~~javascript
{
  _id: "user-1",
  recentOrderSummaries: [
    { orderId: "o-100", createdAt: ISODate("2026-01-15T00:00:00Z") },
    { orderId: "o-099", createdAt: ISODate("2026-01-14T00:00:00Z") }
  ]
}
~~~

All orders reside in a separate collection. `recentOrderSummaries` is derived data and must have an update mechanism and size cap.

### 9.3. Bucket Pattern

For regular measurements or events, records can be grouped into buckets by time or device. Manage bucket sizes carefully and distinguish when MongoDB time-series collections are preferable.

### 9.4. Outlier Pattern

If most accounts have only a few children while a few accounts have huge counts, do not force every account into an unbounded layout. Keep a common embedded subset and split overflow history out, with readers aware of both sources.

## 10. $lookup and Application Composition

Referencing does not inevitably cause N+1 requests when appropriate aggregations or batched lookups are used.

Example joining orders with the current customer:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      _id: "order-101"
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

### 10.1. When to Use?

When the API needs up-to-date customer info and query frequency/size allow it. If only the display name at order time is needed, a snapshot in the order may be better.

### 10.2. $lookup Does Not Enforce Authorization Automatically

Lookups must be tenant-aware, especially if business IDs can collide across tenants. Never trust a client-supplied `tenantId` without authentication/authorization.

### 10.3. Optimize From Measurements

Use indexes on the joined collection, `explain`, and API p95 metrics. `$lookup` may be fine for infrequent queries but suboptimal for high-volume feeds.

## 11. Single-Document Write Operation Reference Table

| Requirement | Operator/API | Properties |
| --- | --- | --- |
| Set or update a field | `$set` | Atomic within one document |
| Remove a field | `$unset` | Atomic within one document |
| Increment/decrement a number | `$inc` | No read-modify-write needed |
| Keep larger/smaller value conditionally | `$max` / `$min` | Value-conditional update |
| Set server timestamp | `$currentDate` | Uses server clock |
| Append an element to an array | `$push` | Must control growth |
| Add element if not already equal to existing | `$addToSet` | Does not replace unique business keys |
| Remove array element | `$pull` | Single-document atomic |
| Set fields only on insert during upsert | `$setOnInsert` | Does not modify those fields when matching existing doc |
| Multiple changes on the same document | `$set` + `$inc` + `$currentDate` | Single atomic `updateOne` |
| Find, update, and return record | `findOneAndUpdate` | Supports BEFORE/AFTER projection |
| Versioned write | version filter + `$inc` version | Optimistic concurrency |

### 11.1. Atomicity Scope

An `updateOne` on a single document is atomic. An `updateMany` modifying multiple documents **is not atomic as a single whole**: each individual document update is atomic, yet partial progress across documents can be observed concurrently.

### 11.2. Not Every Operator Protects Business Invariants

`$push` appends atomically, yet without a cap it still causes unbounded growth. `$inc` deducts stock atomically, yet without a quantity filter it can drive stock negative.

## 12. Lost Update: Read-Then-Write Is Dangerous

Two requests both read `quantity = 10`:

~~~text
Request A reads quantity=10
Request B reads quantity=10

A computes 10+1 and writes 11
B computes 10+1 and writes 11

Expected after two increments: 12
Observed with naive read-modify-write: 11
~~~

Atomic solution:

~~~javascript
db.counters.updateOne(
  { _id: "views:article-1" },
  { $inc: { value: 1 } }
);
~~~

### 12.1. $inc Prevents Lost Increments

When each request uses atomic `$inc`, two successful increments add 2 in total under server semantics.

### 12.2. Retries Still Require Semantics Review

If a client times out without knowing whether the write executed, retrying a non-idempotent business operation can increment twice. Driver retryable writes and operation IDs help within supported scopes, yet applications must still account for ambiguous results and idempotency.

### 12.3. Hot Counters

A single document updated continuously by many workers creates contention. Sharded counters or event aggregation can help if the business tolerates eventual counts, trading off read complexity.

## 13. Conditional Inventory Deduction in One Document

Suppose a product has `available = 10` and needs to reserve 3 units:

~~~javascript
db.inventory.updateOne(
  {
    _id: "tenant-a:product-1",
    tenantId: "tenant-a",
    available: { $gte: 3 }
  },
  {
    $inc: {
      available: -3,
      reserved: 3
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

### 13.1. Why Is the Predicate Inside the Update?

If you only read `available >= 3` beforehand and then run an unconditional update, two concurrent requests can both observe sufficient stock and deduct, driving inventory negative.

### 13.2. matchedCount Is a Business Signal

- `matchedCount = 1`: one document satisfied the predicate and was updated.
- `matchedCount = 0`: document missing, wrong tenant, or insufficient stock.

Distinguish the exact user-facing error via a follow-up query if needed, without letting that follow-up replace the atomic predicate.

### 13.3. One Document Is Not Yet a Complete Order

The stock deduction can succeed while inserting the order fails if the two steps do not share a transaction or workflow. See later sections for invariants spanning inventory and orders.

## 14. Atomic Multi-Field Updates With $inc and $set

Example transitioning an order from `DRAFT` to `SUBMITTED`:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "tenant-a",
    status: "DRAFT"
  },
  {
    $set: {
      status: "SUBMITTED"
    },
    $inc: {
      version: 1
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

### 14.1. Conditional State Transition

If another request already `CANCEL`ed the order, the update filtering `status: "DRAFT"` will not match. Preconditions protect the state machine.

### 14.2. What Without a Precondition?

An unconditional status update allows illegal state transitions even though the write itself is atomic.

### 14.3. No Multi-Document Transaction Needed for a Single Write

If the entire invariant resides in the `order` document, `updateOne` suffices. Wrapping this single operation in a transaction adds no meaningful new atomicity.

## 15. Optimistic Locking With a Version Field

Document:

~~~javascript
{
  _id: "profile-1",
  tenantId: "tenant-a",
  displayName: "A",
  version: 7
}
~~~

Client/service reads `version=7` and wants to change `displayName`:

~~~javascript
db.profiles.updateOne(
  {
    _id: "profile-1",
    tenantId: "tenant-a",
    version: 7
  },
  {
    $set: {
      displayName: "B"
    },
    $inc: {
      version: 1
    }
  }
);
~~~

### 15.1. Result

If `matchedCount=1`, the update succeeded and `version` becomes 8. If `matchedCount=0`, the record was modified, deleted, or out of scope; return conflict or not found per business rules.

### 15.2. Version Does Not Replace Validation

Even without lost updates, `displayName` must still pass schema and permission validation.

### 15.3. Safe Retries

On conflict, the application can reload and let the user resolve/merge rather than blindly overwriting all fields from a stale snapshot.

## 16. findOneAndUpdate to Fetch the Document at the Exact Moment

Some workflows need to claim a task and retrieve the claimed task simultaneously:

~~~javascript
db.jobs.findOneAndUpdate(
  {
    status: "PENDING",
    availableAt: {
      $lte: ISODate("2026-01-15T12:00:00Z")
    }
  },
  {
    $set: {
      status: "RUNNING",
      workerId: "worker-1"
    },
    $currentDate: {
      claimedAt: true
    }
  },
  {
    sort: {
      availableAt: 1,
      _id: 1
    },
    returnDocument: "after"
  }
);
~~~

### 16.1. Atomic Claim

One worker claims one document; other workers cannot match `status=PENDING` on that document once transitioned to `RUNNING`, provided filters and writes are applied properly.

### 16.2. Leases and Recovery

If a worker crashes, the job can stay stuck in `RUNNING`. Real designs need `leaseExpiresAt`, heartbeats/renewals, or a recovery policy—not just a bare status flag.

### 16.3. Avoid Separate Query-Then-Update for Claiming

Reading a pending job and then running an unconditional update allows two workers to claim the same job.

## 17. Array Updates: $push, $addToSet, $pull

~~~javascript
// Append an item:
db.orders.updateOne(
  { _id: "order-101", status: "DRAFT" },
  {
    $push: {
      notes: {
        by: "staff-1",
        text: "Needs confirmation"
      }
    }
  }
);

// Add a unique primitive tag:
db.orders.updateOne(
  { _id: "order-101" },
  {
    $addToSet: {
      tags: "priority"
    }
  }
);

// Remove a matching embedded item:
db.orders.updateOne(
  { _id: "order-101", status: "DRAFT" },
  {
    $pull: {
      items: { lineId: "line-2" }
    }
  }
);
~~~

### 17.1. $addToSet Does Not Replace a Unique Index

It prevents adding duplicate elements by BSON equality within a single document's array; it does not enforce business uniqueness across documents or handle normalization variants.

### 17.2. Atomic Does Not Mean Totals Match Automatically

Removing a line item with `$pull` without recalculating `totalMinor` per business rules leaves inconsistent data. Recompute totals in the same atomic update whenever possible or use a workflow preserving invariants.

### 17.3. Unbounded Array Growth

Continuously `$push`-ing into `auditTrail`, `comments`, or `history` without bounds bloats the document. Use a separate collection or a bounded subset.

## 18. Updating Array Elements Conditionally

Example updating a line item with a specific `lineId` using `arrayFilters`:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "tenant-a",
    status: "DRAFT"
  },
  {
    $set: {
      "items.$[line].qty": 3
    }
  },
  {
    arrayFilters: [
      { "line.lineId": "line-1" }
    ]
  }
);
~~~

### 18.1. Single-Document Rule

`updateOne` remains atomic within the order document; which elements get updated is controlled by `arrayFilters`.

### 18.2. Define Stable lineIds

Do not rely on array positions if users can delete or reorder items. Stable line IDs prevent updating the wrong item.

### 18.3. Total Invariant

If `qty` changes, `totalMinor` must reflect the change within the same business operation. Avoid separate `qty` and `total` updates that could fail halfway.

## 19. Update Pipelines When New Fields Depend on Old Fields

MongoDB supports updates via aggregation pipelines in compatible versions and operators.

Example refreshing `updatedAt` and computing fields from current values:

~~~javascript
db.inventory.updateOne(
  {
    _id: "tenant-a:product-1",
    tenantId: "tenant-a",
    available: { $gte: 3 }
  },
  [
    {
      $set: {
        available: {
          $subtract: ["$available", 3]
        },
        reserved: {
          $add: [
            { $ifNull: ["$reserved", 0] },
            3
          ]
        },
        updatedAt: "$$NOW"
      }
    }
  ]
);
~~~

### 19.1. Pipeline and Classic Update Syntax Differ

Update pipelines use aggregation expressions; standard update modifiers cannot be mixed arbitrarily inside a pipeline document.

### 19.2. Atomicity Remains Single-Document

A pipeline `updateOne` is atomic for one document. With `updateMany`, each document is updated atomically, not the whole batch as one all-or-nothing transaction.

### 19.3. Numeric Types

If data mixes strings/numbers or `reserved` may be missing, expressions need explicit handling. Sample data uses `Int32` and `NumberLong` per schema; monetary arithmetic may require `Decimal128`.

## 20. Upsert: Atomicity and Uniqueness

An upsert updates an existing record or inserts a new one:

~~~javascript
db.productSettings.updateOne(
  {
    tenantId: "tenant-a",
    productId: "product-1"
  },
  {
    $set: {
      reorderThreshold: 5
    },
    $setOnInsert: {
      createdBy: "system"
    }
  },
  {
    upsert: true
  }
);
~~~

### 20.1. Unique Index for Business Keys

~~~javascript
db.productSettings.createIndex(
  {
    tenantId: 1,
    productId: 1
  },
  { unique: true }
);
~~~

Without an appropriate unique constraint, concurrent upserts can create duplicate business records in certain race conditions.

### 20.2. Do Not Assume upsertedId Is Always Present

When an existing record matches, `upsertedId` can be `null`. Check `matchedCount`, `modifiedCount`, and `upsertedId` according to API semantics.

### 20.3. Upsert Does Not Replace Multi-Document Transactions

It does not guard writes to other collections or prevent orphan references.

## 21. When Are Multi-Document Transactions Needed?

A transaction is useful when **a business invariant requires multiple writes to commit or abort together**.

Example creating a reservation:

~~~text
Read inventory for product-1
Decrement available stock
Create one order
Persist related reservation state

Expected:
  Either all required MongoDB writes commit
  Or none of them commit
~~~

If stock and order live in two documents, separate conditional updates do not guarantee both commit if the second command fails.

### 21.1. Transaction Threshold Table

| Question | If Yes | Direction |
| --- | --- | --- |
| Fields reside in one document? | Yes | `updateOne` / conditional update |
| Writes span multiple documents? | Yes | Check consistency requirements |
| Temporary divergence acceptable? | Yes | Outbox/events/saga may fit |
| Partial commit unacceptable? | Yes | Transaction or redesign boundary |
| External API/email involved? | Yes | DB transaction does not cover it |
| Transaction lasts several minutes? | Yes | Avoid long-running DB transactions; use state machine |
| High hot contention? | Yes | Manage conflicts, retries, and throughput |
| Deployment is standalone? | Yes | Multi-document transactions not supported as in replica set/sharded |

### 21.2. Transactions Are Not a Load-Distribution Mechanism

Long or numerous transactions can cause conflicts, resource consumption, and replication overhead.

### 21.3. Transactions Cannot Fix a Flawed Data Model

A customer document holding millions of bookings remains problematic even if writes are wrapped in transactions.

## 22. Three Consistency Levels to Distinguish

1. **Single-document atomicity:** a write updating one document is all-or-nothing for that document.
2. **Multi-document transaction atomicity:** a group of operations within a transaction commits or aborts together.
3. **End-to-end business consistency:** DB, queues, external payments, emails, caches, and other processes all satisfy the contract invariants.

Never infer level 3 solely from level 1 or level 2.

### 22.1. Read Concern and Write Concern Matter Too

Transactions use appropriate `readConcern` and `writeConcern` to achieve required consistency and durability. Do not confuse transaction atomicity with post-failover commit durability.

### 22.2. Eventual Consistency Can Be Acceptable

For notification emails, dashboards, or search indexes, updating within a few seconds may be valid. Use a durable outbox and reconciliation rather than long transactions.

### 22.3. Business Invariants That Tolerate Zero Divergence

Accounting balances, inventory caps, and non-overlapping rentals require explicit design decisions. Implementations may use a single contention document, unique slot keys, transactions, and idempotency.

## 23. MongoDB Transaction Lifecycle

~~~text
Start client session
         |
         v
Start transaction
         |
         v
Read / write operations using SAME session
         |
         v
Business preconditions hold?
   |                 |
  Yes               No
   |                 |
   v                 v
Commit           Abort
   |
   v
Commit acknowledged under chosen concerns
   |
   v
Return result / publish downstream events
~~~

### 23.1. Sessions Are Mandatory for Transaction Operations

All participating operations must pass the **same `ClientSession`**. Omitting the session on a write executes it outside the transaction, breaking all-or-nothing guarantees.

### 23.2. Unknown Commit Result State

Timeouts or network errors during commit can leave the client unsure whether the transaction committed. Never assume a timeout means no changes persisted.

### 23.3. Recovery

Use version-appropriate driver transaction retry patterns and verify business-layer idempotency; blindly retrying an entire operation with external side effects is unsafe.

## 24. Multi-Document Transaction Example in mongosh

**Run only on a replica-set or sharded MongoDB test deployment that supports transactions, using suitable lab data.** This example demonstrates a two-document transaction with conditional stock deduction.

~~~javascript
const session = db.getMongo().startSession();

const lab = session.getDatabase("mongo_decision_lab");
const inventory = lab.getCollection("inventory");
const orders = lab.getCollection("orders");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const qty = 2;
  const result = inventory.updateOne(
    {
      _id: "tenant-a:product-1",
      tenantId: "tenant-a",
      available: { $gte: qty }
    },
    {
      $inc: {
        available: -qty,
        reserved: qty
      }
    }
  );

  if (result.matchedCount !== 1) {
    throw new Error("Insufficient stock or missing item");
  }

  orders.insertOne({
    _id: "tenant-a:order:reservation-001",
    tenantId: "tenant-a",
    productId: "tenant-a:product-1",
    quantity: qty,
    status: "RESERVED"
  });

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (_) {
    // Commit may already have completed or session ended.
    // Resolve ambiguous outcomes via durable business ID.
  }

  throw error;
} finally {
  session.endSession();
}
~~~

### 24.1. Basic Control-Flow Example

In production, use the driver's recommended transaction callback/retry API for your version. Never assume catching and calling `abortTransaction` after a commit error definitively determines the outcome.

### 24.2. Data Must Exist With the Right Scope

The `inventory` document must have `available`/`reserved` fields with proper numeric types; the `orders` collection and indexes must already meet preconditions.

### 24.3. Idempotency Is Mandatory When Business-Layer Retries Exist

A stable `orderId` and unique key let you look up a committed outcome. Never generate a new `orderId` on retry when the prior transaction's outcome is uncertain.

### 24.4. Not Every Read Needs a Transaction

Read-only dashboards or single lookups can use an appropriate `readConcern` without opening a multi-document transaction.

## 25. Java Sync Driver: Conditional Atomic Update

Java example:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class InventoryOps {
    private InventoryOps() {}

    public static boolean reserve(
        MongoCollection<Document> inventory,
        String tenantId,
        String productId,
        int quantity
    ) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        UpdateResult result = inventory.updateOne(
            Filters.and(
                Filters.eq("_id", productId),
                Filters.eq("tenantId", tenantId),
                Filters.gte("available", quantity)
            ),
            Updates.combine(
                Updates.inc("available", -quantity),
                Updates.inc("reserved", quantity),
                Updates.currentDate("updatedAt")
            )
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

### 25.1. Why Not Find Then Update?

A write with `available >= quantity` checks the precondition atomically at update time rather than relying on a stale application snapshot.

### 25.2. Why Check quantity > 0?

If `quantity` were negative, subtracting stock would actually add stock. Atomicity does not replace business input validation.

### 25.3. What Is Still Missing?

This method updates only one `inventory` document. If it must also create an `order` in another collection, a transaction or partial-state workflow is required.

## 26. Java Sync Driver: Multi-Document Transaction

Minimal example assuming the application's `MongoClient` is reused, the test topology supports transactions, and valid indexes/fixtures exist:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class CheckoutService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;

    public CheckoutService(
        MongoClient client,
        MongoCollection<Document> inventory,
        MongoCollection<Document> orders
    ) {
        this.client = client;
        this.inventory = inventory;
        this.orders = orders;
    }

    public void reserveAndCreateOrder(
        String tenantId,
        String productId,
        String orderId,
        int qty
    ) {
        if (qty <= 0) {
            throw new IllegalArgumentException(
                "qty must be > 0"
            );
        }

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                UpdateResult stockResult =
                    inventory.updateOne(
                        session,
                        Filters.and(
                            Filters.eq("_id", productId),
                            Filters.eq("tenantId", tenantId),
                            Filters.gte("available", qty)
                        ),
                        Updates.combine(
                            Updates.inc("available", -qty),
                            Updates.inc("reserved", qty)
                        )
                    );

                if (stockResult.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Stock not available"
                    );
                }

                orders.insertOne(
                    session,
                    new Document("_id", orderId)
                        .append("tenantId", tenantId)
                        .append("productId", productId)
                        .append("qty", qty)
                        .append("status", "RESERVED")
                );

                return null;
            });
        }
    }
}
~~~

### 26.1. Both Writes Receive the Session

Omitting `session` on either operation executes that write outside the transaction.

### 26.2. Transaction Callbacks Can Be Re-Executed

The driver may retry per policy, so never place non-idempotent side effects like charging a card, sending emails, or incrementing an external counter inside the transaction callback.

### 26.3. Stable orderId

When the client does not know the commit outcome, query by `orderId`/idempotency key to resolve the outcome; do not generate a fresh `orderId` on every retry.

### 26.4. Business Uniqueness Is Not Automatic

If the application permits distinct `orderId`s for the same payment action, transactions do not prevent double-charging. Unique business keys and idempotency remain necessary.

## 27. Transaction Retries, Errors, and Ambiguous Outcomes

Situations to distinguish:

| Situation | What Can Happen | Handling Strategy |
| --- | --- | --- |
| Write conflict | Transaction aborted/retried | Retry per driver guidance and cap |
| Transient transaction error | Temporary error | Retry whole transaction when safe |
| `UnknownTransactionCommitResult` | Client unsure of commit outcome | Retry commit / resolve per guidance |
| Duplicate key | Unique index violated | Check business key and conflict policy |
| Network timeout | Write/commit may have completed | Idempotent reconciliation |
| Business validation failed | Insufficient stock, invalid status | Abort and return business error |
| Process died after commit | DB may have committed | Reconcile by stable ID |

### 27.1. Avoid Infinite Retries

Set timeouts/deadlines and backoff. Prolonged outages or heavy contention must not trigger a retry storm.

### 27.2. Never Infer Rollback From a Timeout

The commit may have succeeded while the response was lost. Investigate using a durable business identifier.

### 27.3. Record Error Labels and Metrics

Retry policies should inspect API error classes/labels rather than matching verbose error message strings containing hostnames or timestamps.

## 28. Transaction Costs and Appropriate Scope

A multi-document transaction can increase:

- Network round trips.
- Lock and conflict pressure.
- Snapshot resource/time overhead.
- Memory/storage pressure for large or long transactions.
- Complexity around retries and commit uncertainty.
- Latency under cross-shard coordination.
- Load on replica sets and high-contention workflows.

### 28.1. Keep Transactions as Short as Possible

Never hold a transaction open while waiting for user input, calling a payment provider, or running multi-minute jobs.

### 28.2. Specific Limits Depend on Version/Config

MongoDB enforces rules on transaction lifetime, operations, memory, and DDL inside transactions that vary by version and topology. Verify documentation for your exact deployment.

### 28.3. Do Not Mandate "Every Multi-Collection Operation Needs a Transaction"

An append-only audit event can be emitted asynchronously via an outbox with eventual consistency if business rules permit.

## 29. Choosing Transactions vs Eventual Consistency

| Scenario | Consider | Conditions for Safety |
| --- | --- | --- |
| Order + inventory must commit together | Transaction | Conditional stock update, unique order ID |
| Email after order | Outbox worker | At-least-once + idempotency |
| Dashboard updated after order | Derived projection | Lag SLO, replay/reconcile |
| Search index synced with product | Events/read model | Versioning, ordering, retries |
| Debit/credit two account balances | Transaction and ledger invariant | Double-entry, uniqueness, auditing |
| Sync product name snapshot in old orders | Usually avoid if history is immutable | Data ownership policy |
| Combine multiple writes to one document | Atomic update | Conditional predicates |
| Batch migrate many docs without all-or-nothing snapshot | Idempotent bulk + checkpoints | Resume and reconciliation |
| Hard consistency across multiple docs | Transaction or redesign | Scope/timing/constraints |
| Long distributed workflow | Saga/state machine | Compensation and idempotency |

### 29.1. Eventual Consistency Does Not Mean "Ignoring Data Accuracy"

It demands durable events, retries, deduplication, bounded lag, failure handling, and reconciliation.

### 29.2. Transactions Do Not Bring External Services Into the Atomic Boundary

No MongoDB transaction automatically rolls back a third-party payment capture or a sent email.

## 30. Outbox Pattern for External Side Effects

~~~text
MongoDB transaction or atomic document write
       |
       +-- Update business state
       |
       +-- Insert outbox event (same transaction if separate doc)
       |
       v
Commit
       |
       v
Outbox worker reads pending events
       |
       v
Publish to broker / send message
       |
       v
Mark delivery progress with idempotency
~~~

### 30.1. Why Not Publish Before Commit?

If publishing succeeds and the transaction aborts, downstream services act on an order that does not exist.

### 30.2. Why Not Publish After Commit With a Non-Durable Call?

If the process crashes right after commit and before publishing, the event is lost. The outbox persists the intent to publish inside the DB.

### 30.3. Deliveries Can Repeat

A worker can publish and crash before marking the event sent. Consumers need idempotency keys to handle duplicate events.

### 30.4. Two DB Writes Only Need a Transaction If the Outbox Is a Separate Collection

If small outbox metadata can live inside the same aggregate document, the atomic boundary may differ; evaluate growth and access behavior.

## 31. Sagas and Long-Running Workflows

A vehicle rental booking workflow may run:

~~~text
Create booking PENDING
      |
      v
Hold vehicle slot
      |
      v
Authorize payment provider
      |
      +-- Success --> Confirm booking
      |
      +-- Failure --> Release hold, mark failed
~~~

### 31.1. Never Hold a DB Transaction Across the Entire Workflow

Payment providers can take seconds or minutes, risking timeouts. A state machine with compensation is often the right fit.

### 31.2. Compensation Is Not a True DB Rollback

If a payment was charged, you must issue a refund rather than erasing traces as if nothing happened. Keep an explicit audit trail and states.

### 31.3. Idempotency at Every Step

Each action requires a stable operation ID and status checks so retries do not create double reservations or double charges.

## 32. Booking Overlap Is a Special Concurrency Case

If each booking is a separate document, the app might check:

~~~text
Existing startAt < requested endAt
AND
Existing endAt > requested startAt
~~~

Example:

~~~javascript
db.bookings.find({
  tenantId: "tenant-a",
  vehicleId: "vehicle-1",
  status: {
    $in: ["HELD", "CONFIRMED"]
  },
  startAt: {
    $lt: ISODate("2026-02-15T12:00:00Z")
  },
  endAt: {
    $gt: ISODate("2026-02-14T12:00:00Z")
  }
});
~~~

### 32.1. Query-Then-Insert Does Not Protect Concurrency

Two concurrent requests can both observe zero overlapping bookings and insert two conflicting documents.

### 32.2. A Plain Transaction Does Not Automatically Prevent Write Skew

If both transactions only read the absence of conflicts and insert different documents, an explicit conflict/uniqueness mechanism is required; transactions do not automatically enforce uniqueness across arbitrary time intervals.

### 32.3. Approaches

- Materialize discrete slot keys backed by a unique index on `vehicle + slot`.
- Use a shared availability/lock/sequence document updated conditionally to force write contention.
- Use reservation holds with TTL/recovery, backed by proper uniqueness and time contracts.
- Match slot granularity to business rules: daily buckets are insufficient if vehicles have arbitrary pickup/return hours.

### 32.4. Test the Business Invariant

Two active bookings must never overlap for the same vehicle under policy. Verify with concurrent integration tests, not merely sequential tests.

## 33. Money Transfer Transactions Require a Ledger

Example transferring 100 from A to B:

~~~text
account A balance = 1000
account B balance = 500

Operation:
  Debit A by 100 if balance>=100
  Credit B by 100
  Insert ledger entry with transferId

Invariant:
  A+B balance unchanged by this transfer
  One logical transfer per transferId
~~~

### 33.1. Transactions Protect Commit Atomicity

Debit, credit, and ledger insertion must be all-or-nothing if business rules require.

### 33.2. Double-Entry Ledger

In real financial systems, design proper ledger entries and auditing rather than relying on two mutable balances as the sole accounting record.

### 33.3. Stable transferId

Retries after an unknown commit outcome must locate the processed `transferId` rather than generating a new transfer.

### 33.4. Authorization and Currency

Never transfer across mismatched tenants or unauthorized accounts; enforce matching currencies or explicit conversion rules, avoiding overflow and floating-point arithmetic.

## 34. Many-to-One Relationships and Master Data

When one product appears in thousands of orders:

~~~text
Product master
  productId, currentName, currentPrice

Orders
  orderId
  productId
  itemSnapshot(nameAtPurchase, unitPriceAtPurchase)
~~~

### 34.1. Update Master in One Place

Current price changes in the `products` collection without fanning out updates to all historical orders.

### 34.2. History Snapshot

Historical names and prices in orders remain immutable. When users view past orders, they see the terms originally agreed upon.

### 34.3. Do Not Turn Snapshots Into the Primary Catalog Source

Searching current product names should query the product master or a derived search collection, never scan historical orders.

## 35. Many-to-Many and Association Documents

For example, students and courses, or users and roles:

| Context | Design |
| --- | --- |
| User has at most 5 role IDs, read with user | Can embed roles |
| Enrollment has `enrolledAt`, `grade`, `status` | Association collection |
| Course has hundreds of thousands of students | Do not embed all students in course |
| Role metadata changes frequently | Role master + references |
| Need to find all users of a role | Indexed array or association collection based on scale |

### 35.1. Links With Their Own Attributes

If an association has its own history, status, or owner, an association document may be the proper aggregate.

### 35.2. Do Not Ignore Reverse Queries

Embedding role IDs in users makes reading user roles fast, yet finding every user with role X requires a multikey index or a separate association model.

## 36. Indexing According to the Data Model

### 36.1. Embedded Fields

Nested paths can be indexed:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  "shippingAddressSnapshot.city": 1
});
~~~

Create this only if queries filter by city frequently; this index also consumes storage and write budget.

### 36.2. Referenced Child Collections

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
~~~

Serves customer order history scoped by tenant and ordered by time.

### 36.3. Unique Business Keys

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    externalOrderId: 1
  },
  { unique: true }
);
~~~

Enforces `externalOrderId` uniqueness per tenant.

### 36.4. Multikey Arrays

Indexed arrays produce multikey behavior; index entries grow with element count. Even a bounded array must be evaluated if multiple subfields are indexed.

## 37. Indexes Are Neither Foreign Keys Nor Transactions

| Index | What It Helps With | What It Does Not Guarantee |
| --- | --- | --- |
| Unique index | Prevents duplicate business keys within index scope | That referenced documents exist |
| Compound index | More efficient filtering and sorting | Cross-document atomic updates |
| Partial unique | Uniqueness on a filtered subset | Collection-wide uniqueness |
| TTL index | Asynchronous cleanup of expired data | Deletion at the exact expiration second |
| Multikey | Querying array elements | Bounded arrays or same-element rules |
| Shard key index | Routing and distribution per design | Targeted queries when shard key is absent |

### 37.1. TTL and Reservation Holds

TTL deletion is an asynchronous background process, not a lock service expiring holds at the exact timestamp. Business validity must evaluate `expiresAt` in server/application rules rather than waiting on TTL to determine slot availability.

### 37.2. Unique Index on Interval Endpoints

`Unique(vehicleId, startAt, endAt)` does not block overlapping intervals. Enforcing tuple uniqueness is different from enforcing non-overlapping intervals.

## 38. Read Concern, Write Concern, and Durability

When deciding between transactions and atomic updates, identify the required consistency and durability guarantees.

| Mechanism | Question It Answers |
| --- | --- |
| Atomic single-document write | Can a single document be left half-updated? |
| Transaction | Do multiple DB writes in a transaction commit/abort together? |
| Write concern | How many/what kind of members acknowledge the write, and at what durability? |
| Read concern | What snapshot/commit level can reads observe? |
| Read preference | Are reads routed to the primary or a suitable secondary? |
| Causal consistency | What ordering is guaranteed across operations in a session? |

### 38.1. "majority" Is Not a Magic Word

Write concern `"majority"` governs replication acknowledgment, while exact durability guarantees also depend on topology, journaling settings, and MongoDB version. Do not use it to replace transactions when operations require multi-document atomicity.

### 38.2. Secondary Reads

Reads from secondaries can be stale; if read-your-writes is required, configure read preferences, sessions, and read concerns accordingly.

### 38.3. Atomicity Does Not Mean Instant Visibility Across All Caches

Even after a DB commit, downstream search indexes and caches may lag behind. Define latency contracts and reconciliation.

## 39. Multi-Tenant Design Across Choices

Every read and write must constrain the tenant:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "tenant-a",
    status: "DRAFT"
  },
  {
    $set: {
      status: "SUBMITTED"
    }
  }
);
~~~

### 39.1. tenantId Originates From the Backend

Never trust an arbitrary `tenantId` in a request payload without verifying authorization.

### 39.2. References Must Belong to the Same Tenant

`order.customerId` is only valid if the customer belongs to an authorized tenant; a `$lookup` matching solely on `customerId` risks cross-tenant leaks if IDs collide.

### 39.3. Transactions Do Not Enforce Authorization

Wrapping writes in a transaction does not prevent an application from modifying another tenant's document if filters are wrong.

### 39.4. Snapshots and PII

Embed only authorized fields deliberately, applying retention and redaction policies.

## 40. Hot Documents and Throughput

When many requests update the same document:

~~~text
1000 concurrent viewers
   -> all increment same article.views document
~~~

MongoDB preserves atomicity for each update, yet contention, latency, and resource usage increase.

### 40.1. Optimizing Does Not Mean Abandoning Atomicity

Sharded counters or batching can help, provided accuracy and freshness contracts are explicitly defined.

### 40.2. When to Use Event Aggregation?

If view counts do not need immediate unit-level accuracy, partitioned events/counters and asynchronous aggregation reduce hotspots.

### 40.3. When Not To?

Accounting balances or inventory counts requiring strict invariants should not be turned into eventual counters purely for throughput.

## 41. Sharded Clusters and Transactions

MongoDB supports transactions across suitable topologies and versions, including sharded deployments, though coordination cost and operational constraints differ from replica sets.

### 41.1. Align Shard Keys With Queries

Putting `tenantId` in a document does not make every query targeted. Queries must supply appropriate shard-key predicates so `mongos` can route efficiently.

### 41.2. Cross-Shard Writes

A transaction touching multiple shards increases latency and coordination overhead. Design document boundaries and shard keys around the workload.

### 41.3. Unique Indexes

Sharded collections have shard-key rules governing unique indexes depending on MongoDB version. Do not copy non-sharded lab indexes blindly into sharded production.

### 41.4. Do Not Embed Everything Just to Avoid Cross-Shard Transactions

An oversized or hot document can be far worse. Balance locality, cardinality, and concurrency.

## 42. New Data, Legacy Data, and Schema Evolution

Data embedded initially may need to be split out as the product scales.

Version 1 example:

~~~javascript
{
  _id: "customer-15",
  orderSummaries: [
    // bounded during early stage
  ],
  schemaVersion: 1
}
~~~

Version 2:

~~~javascript
// customers
{
  _id: "customer-15",
  schemaVersion: 2
}

// orders
{
  _id: "order-101",
  customerId: "customer-15",
  schemaVersion: 2
}
~~~

### 42.1. Expand–Migrate–Contract

1. Readers understand both v1 and v2.
2. Writers move to v2.
3. Backfill historical documents.
4. Reconcile counts and IDs.
5. Remove legacy fields once no clients depend on them.

### 42.2. Idempotent Migrations

Rerunning transforms must not create duplicate orders. Use stable IDs, unique business keys, and checkpoints.

### 42.3. Do Not Delete Source Data Before Verification

Especially when extracting an embedded array into a separate collection, compare counts and business invariants and prepare a rollback plan.

## 43. Selection Table by Real-World Domain

| Domain | Relationship | Often-Optimal Choice | Notes |
| --- | --- | --- | --- |
| E-commerce | Order → bounded `orderItems` | Embed | Price snapshot |
| E-commerce | Customer → unbounded `orders` | Reference | Paginated history |
| Catalog | Product → unbounded `reviews` | Reference | Reviewer identity |
| CMS | Article → bounded `tags` | Embed | Multikey index if searched |
| CMS | Article → unbounded `comments` | Reference | Moderation lifecycle |
| Messaging | Conversation → unbounded `messages` | Reference | Paging, retention |
| IoT | Device → huge `measurements` | Separate time-series/buckets | TTL/retention |
| Social | User → huge `followers` | Association collection | Bidirectional queries |
| Booking | Booking → small `addons` | Embed | Same aggregate |
| Booking | Booking → current vehicle master | Reference + snapshot | Current vs contracted |
| Payments | Payment → event history | Separate append-only | Auditable |
| Finance | Account → unbounded `ledger` entries | Reference | Ledger source of truth |
| Inventory | Product → `available`/`reserved` counters | Atomic update | Conditional predicate |
| Reporting | Daily revenue | Derived read model | Replay/reconcile |
| Search | Full-text index | Search-specific model | Eventual update |
| Work queues | Job status/lease | Atomic claim | Lease recovery |

**Every row is a suggestion, not a rigid rule.** Real systems must measure cardinality, transaction needs, retention, and traffic.

## 44. Selection Table by Write Type

| Action | Data Scope | Suggestion | Mistake to Avoid |
| --- | --- | --- | --- |
| Change a profile field | 1 document | `$set` | Overwriting stale snapshots |
| Count views | 1 document | `$inc` | Read-modify-write |
| Deduct stock if sufficient | 1 document | Predicate + `$inc` | Check-then-write race |
| Modify an array item | 1 document | `arrayFilters` | Updating wrong item |
| Finalize order and total from items in same doc | 1 document | Atomic update/pipeline | Total mismatching items |
| Claim job | 1 document | `findOneAndUpdate` | Two workers claiming |
| Increment version on edit | 1 document | Version filter + `$inc` | Lost update |
| Update 1,000 independent profile docs | Multiple docs | Bulk/write workflow | Assuming all-or-nothing |
| Create order and reserve inventory | Multiple docs | Transaction/workflow | Partial commit |
| Transfer funds A → B | Multiple docs | Transaction + ledger | Double charge on retry |
| Write outbox after commit | Multiple docs | Same transaction when needed | Lost event |
| Email after commit | External | Outbox/worker | Email inside DB transaction |
| Propagate read model | Async | Events/reconciliation | Unmonitored stale views |

## 45. Selection Table by Consistency Requirement

| Mandatory Condition | Choice | Accompanying Condition |
| --- | --- | --- |
| Prevent negative stock in one record | Conditional atomic update | Filter `available >= qty` |
| Prevent illegal status transitions | Filter current status | State machine |
| Prevent lost updates on one record | Version predicate | Conflict handling |
| Prevent partial update of one document | Single-document write | Built-in MongoDB atomicity |
| Multiple docs must commit together | Transaction | Same session, retry guidance |
| Prevent emitting duplicate business events | Unique event ID/idempotency | Consumer dedup |
| Never lose outbox event after order commit | Durable outbox in same DB atomic scope | Relay/retries |
| Read immediately after write | Appropriate read/session policy | Concern/preference |
| Prevent duplicate bookings per slot | Unique slot/contended record | Time granularity |
| Dashboard updates within 5 seconds | Eventual projection | Lag monitoring, replay |
| Must roll back external payment | Compensation/refund workflow | Not a MongoDB rollback |

### 45.1. Define Consistency via Business Questions

"Data must be consistent" is too vague. Write: "During reservation, two `ACTIVE` reservations cannot exist on the same resource-slot," or "Once a write is acknowledged, a user reading their own status must observe the new version."

### 45.2. Stronger Guarantees Usually Carry Cost

Cross-shard transactions, `majority` write concern, `snapshot` read concern, and contention points increase latency and capacity needs. Measure the trade-offs.

## 46. 10-Question Checklist Before Finalizing a Schema

1. **What are the primary read patterns?** Which fields load together vs separately?
2. **What are the primary write patterns?** Single or multiple documents?
3. **What is the maximum cardinality?** Are there any unbounded arrays?
4. **Who owns the data?** Who updates it, and what is its lifecycle?
5. **Historical snapshot or current master?** Avoid accidental syncing.
6. **What are the consistency invariants?** Express them as testable statements.
7. **What are the unique/index requirements?** Which keys must be unique?
8. **What is the tenant/security scope?** Are there cross-tenant references?
9. **What are the growth/retention projections?** 16 MiB limit, write hotspots, history retention?
10. **What is the failure/retry policy?** Partial commits, ambiguous outcomes, external side effects?

If questions 3, 6, or 10 remain unanswered, hold off on finalizing the model for critical flows.

## 47. Common Anti-Patterns

| Anti-Pattern | Why It Is Wrong | How to Improve |
| --- | --- | --- |
| Turning every SQL table 1:1 into a MongoDB collection | Excessive joins and round trips | Access-pattern-driven boundaries |
| Embedding all comments in an article | Unbounded array | Separate `comments` collection |
| Embedding full booking history in customer | Bloated/hot document | Reference + pagination |
| Copying current price to old orders and syncing | Corrupts history | Immutable price snapshot |
| Forgetting to update denormalized fields | Data drift | Canonical owner + events/reconcile |
| Reading stock then writing new count | Lost update | Predicate + `$inc` |
| Updating stock without checking available | Can go negative | Atomic conditional filter |
| Assuming `updateMany` is all-or-nothing | Partial states become visible | Use a transaction if needed |
| `findOne` then update to claim a job | Two workers can claim | `findOneAndUpdate` |
| Using `$addToSet` instead of a collection-wide unique index | Does not protect across docs | Unique business index |
| `$push`-ing logs endlessly into parent | 16 MiB limit / bloat | Separate history collection |
| Using transactions for every `updateOne` | Unnecessary overhead | Atomic update |
| Holding a transaction open waiting on payment | Timeouts/contention | Saga/state machine |
| Sending emails inside a transaction callback | Retries send duplicate emails | Outbox |
| Treating unknown commit outcome as abort | Duplicate writes on retry | Idempotent reconciliation |
| Using transactions to stop interval overlaps without contention | Write skew | Unique slots / shared write |
| Lowering write concern to hide timeouts | Durability risk | Diagnose lag and workload |
| Reading secondaries while demanding latest state | Stale reads | Appropriate read strategy |
| One index for every relationship | Poor query plans | Workload-specific indexes |
| Forgetting tenant filter | Data leak | Trusted scope |
| Storing money as `Double` | Precision loss | Minor units / `Decimal128` |
| Expecting DB transactions to roll back emails | Incorrect | Compensation |
| Schema migration generating random IDs | Duplicate records | Stable IDs |
| Measuring only read latency | Ignores write/index costs | Full workload metrics |

## 48. Risk Assessment Matrix Before Changing a Choice

| Change | Affected Area | Primary Risk | What to Measure/Verify |
| --- | --- | --- | --- |
| Embed child collection into parent | Schema shape | Oversized docs, data loss | Count/cardinality/size |
| Reference out from embedded array | Query path | N+1 reads, orphan refs | Indexes, integrity |
| Add snapshot field | Duplicate data | Staleness/PII | Ownership, retention |
| Switch read-modify-write to `$inc` | Concurrency | Retry duplicates | Counter invariant |
| Add optimistic locking | API conflict behavior | More retries | Conflict rate |
| Add transactions | Write path | Latency/conflicts | p95/abort/lag |
| Switch transaction to saga | Consistency model | Partial states | Compensation coverage |
| Add outbox | Event delivery | Duplicate processing | Dedup/replay/lag |
| Add unique index | Writes & data quality | Existing duplicates | Data cleanup/index build |
| Add TTL | Retention | Async deletion | Business expiry logic |
| Move to sharding | Routing, unique constraints | Scatter-gather, hotspots | Shard-key analysis |

### 48.1. Do Not Change Too Many Variables at Once

Splitting collections, changing IDs, altering consistency, and changing shard keys simultaneously makes rollback and root-cause analysis hard. Phase migrations with verification evidence.

### 48.2. Account for Newly Written Data

Once the application writes using the new schema, rolling back to old binaries may break readers. Prepare reader compatibility, dual-schema support, and forward-fix plans.

## 49. Practice Problems: Choosing the Right Model

### Exercise 1 — Address List

A customer has at most 3 addresses, usually viewed with the profile, yet PII requires separate access control. Choose embed or reference? State when splitting is required despite being bounded.

### Exercise 2 — Millions of Messages

A conversation has millions of messages and needs infinite scroll. Why should all messages not be embedded in the conversation? Design the pagination index.

### Exercise 3 — Order Items

An order has at most 10 items with prices fixed at purchase time. Design the document snapshot and total invariant.

### Exercise 4 — Customer Master

A customer changes their name. Distinguish current profile data from the name snapshot inside past orders.

### Exercise 5 — Follower Graph

An account has millions of followers, queried in both directions. Choose an association collection or embedded IDs?

### Exercise 6 — Device Telemetry

100 measurements/second/device, 30-day retention. Compare an array in the device document against a time-series/bucket collection.

### Exercise 7 — Small Tags

An article has at most 8 tags and needs tag-based search. How can tags be embedded and indexed?

## 50. Exercises on Atomicity and Concurrency

### Exercise 8 — Lost Update

Two requests both read `counter=10` and write `11`. Show how to use `$inc` to obtain `12`.

### Exercise 9 — Stock Condition

Product `available=4`; two requests want to reserve `qty=3`. Design the filter/update and state the expected number of successful reservations.

### Exercise 10 — State Transition

A `DRAFT` order can be `SUBMIT`ted or `CANCEL`ed, but cannot be `SUBMIT`ted after `CANCEL`. Write the conditional update.

### Exercise 11 — Optimistic Lock

A profile has `version=5` and two clients edit concurrently. Design conflict detection.

### Exercise 12 — Array Update

Update only `lineId=line-7` in `items`, without using array indices. Write `arrayFilters`.

### Exercise 13 — Job Claiming

Two workers simultaneously look for a `PENDING` job. How do you use `findOneAndUpdate`, leases, and a recovery policy?

### Exercise 14 — Upsert

Concurrent requests try to create a `tenantId+productId` config. Why is a unique index needed?

### Exercise 15 — updateMany

A bulk status update across 1,000 documents fails partway through. Can you assume the entire batch rolls back? When is a transaction required?

## 51. Exercises on Transactions and Eventual Consistency

### Exercise 16 — Order + Stock

Create an order and deduct stock across two collections. Write the transaction concept and describe retry idempotency.

### Exercise 17 — Payment Capture

The DB transaction commits, yet calling the payment provider fails. Does MongoDB roll back the payment provider? Design a saga/outbox flow.

### Exercise 18 — Unknown Commit Result

A client times out during commit. Why must you not generate a new `orderId` to retry? How do you reconcile using a stable `orderId`?

### Exercise 19 — Booking Overlap

Two requests query for zero overlap and then insert. Why is a standard transaction insufficient? Propose slot keys or a contention document.

### Exercise 20 — Ledger Transfer

Transferring money between two accounts updates balances and a ledger. Write the invariants and idempotency key.

### Exercise 21 — Dashboard

`dailyRevenue` updates with a 2-second lag. When is eventual consistency acceptable? Which metrics and replay safeguards are needed?

### Exercise 22 — Outbox Duplicate

An outbox worker publishes a message and crashes before marking it sent. Why does the consumer need idempotency?

### Exercise 23 — Retry Storm

A transaction repeatedly hits write conflicts. How do you configure deadlines/backoff and fallback/alerts?

## 52. Scenario Synthesis Exercises

### Exercise 24 — Booking Aggregate

Design a booking document with addons, customer/vehicle snapshots, references, and a separate payment ledger. Draw the consistency boundaries.

### Exercise 25 — Hotspots

An article receives 20,000 updates/second on its views counter. When should you consider sharded counters or event aggregation instead of a single document?

### Exercise 26 — Retention

Notification history must be retained for 90 days, while user profiles are kept long-term. Should notifications be embedded in the user document?

### Exercise 27 — Access Control

An order belongs to `tenant-a`, while its `customerId` collides with a business ID in `tenant-b`. Design the lookup and validation to prevent leaks.

### Exercise 28 — Migration

Extract `customer.orderSummaries` into an `orders` collection, preserving stable IDs, backfill idempotency, and reader compatibility.

### Exercise 29 — Sharding

`tenantId` is used as a shard-key component, yet one tenant accounts for 70% of writes. What must be evaluated before choosing the key?

### Exercise 30 — Trade-Off Report

A new design cuts read p95 by 40% while increasing write p95 by 25% and storage by 30%. Based on workload and SLOs, propose a conditional decision.

## 53. Answer Guidelines for Self-Review

These are **solution directions**, not the only valid answers:

| Exercise | Core Guidance |
| --- | --- |
| 1 | Embed if permissions/lifecycle match; reference if PII/access differs |
| 2 | `messages` collection, index `conversationId + createdAt + _id` |
| 3 | Bounded items + `unitPrice` snapshot, `total` invariant |
| 4 | Current master reference vs historical snapshot |
| 5 | Association collection for unbounded many-to-many |
| 6 | Time-series/partitions/buckets; never embed unboundedly |
| 7 | Bounded `tags` array + multikey index |
| 8 | `$inc: {value: 1}` for each successful write |
| 9 | Filter `available >= 3`; only one of the two writes succeeds when `available=4` |
| 10 | Filter `status=DRAFT` alongside `$set` status |
| 11 | Filter `version=5` + `$inc` version, conflict if `matchedCount=0` |
| 12 | `$set items.$[line].field` + `arrayFilters` |
| 13 | `findOneAndUpdate` + lease expiry/recovery |
| 14 | `Unique(tenantId, productId)`, handle duplicate key |
| 15 | `updateMany` is per-document atomic, not all-or-nothing |
| 16 | Same-session transaction and stable order ID |
| 17 | Outbox/saga/compensation; do not rely on DB rollback for external APIs |
| 18 | Reconcile by durable `orderId` when commit is ambiguous |
| 19 | Slot uniqueness or shared contention write |
| 20 | Atomic debit, credit, ledger; unique `transferId` |
| 21 | Lag SLA, replay, dedup, and reconciliation |
| 22 | At-least-once delivery produces duplicates |
| 23 | Bounded retries/backoff, metrics/conflict response |
| 24 | Embed bounded addons, refs/snapshots, separate ledger |
| 25 | Hot document; sharded counters with freshness trade-off |
| 26 | Separate notifications with TTL/retention |
| 27 | Tenant-aware references/lookup and trusted tenant auth |
| 28 | Expand–migrate–contract, stable IDs, reconciliation |
| 29 | Tenant skew/hotspot, shard targeting, uniqueness |
| 30 | SLOs and read/write weighting determine the trade-off |

## 54. Pre-Decision Review Checklist

### Data Model

1. Critical access patterns are documented.
2. Maximum cardinality and growth are projected.
3. No unintentional unbounded arrays exist.
4. Embedded children share lifecycle and owner.
5. Master references and historical snapshots are clearly separated.
6. Derived fields have a canonical source and sync policy.
7. Maximum document size leaves ample headroom.
8. Retention and privacy rules are addressed.
9. Reverse queries have suitable indexes/plans.
10. Tenant access and referential rules are explicit.

### Atomic Operations

11. No read-modify-write for increments/decrements.
12. Conditional predicates reside inside the update filter.
13. Status transitions are guarded.
14. Optimistic versioning is used where needed.
15. `matchedCount`/`modifiedCount`/`upsertedId` are handled accurately.
16. Embedded arrays have bounds.
17. Nested field updates do not accidentally overwrite entire subdocuments.
18. `updateMany` is not mistaken for all-or-nothing.
19. Retry ambiguity has a durable business ID.
20. Invariants are tested under concurrency.

### Transactions and Workflows

21. Writes that must commit together are explicitly identified.
22. All transaction operations share the same session.
23. Deployment supports transactions.
24. Read/write concerns match requirements.
25. Transactions are short with timeout/retry strategies.
26. External side effects stay outside the DB transaction.
27. Outbox/sagas implement idempotency/compensation.
28. No competing authoritative writers exist.
29. Interval uniqueness has real conflict protection.
30. Reconciliation and audit plans are in place.

### Operations

31. Indexes serve measured query workloads.
32. Index write and storage costs are measured.
33. SLOs, peak traffic, and hotspots are evaluated.
34. Sharding and unique index constraints are reviewed.
35. Schema version, rollout, and rollback are clear.
36. Changes deploy only with proper environment and permissions.
37. Logs record error codes, metrics, and tracing without leaking PII.
38. Integration tests cover positive, negative, and concurrent cases.

## 55. Architecture Decision Record Template

~~~yaml
decisionId: "ADR-MONGO-001"
title: "Embed order items and reference products"
businessRequirement:
  - "Read order detail in one request"
  - "Preserve price at purchase time"
  - "Support current product catalog changes"
readPatterns:
  - "GET order by tenant and orderId"
  - "LIST orders by customer and createdAt"
writePatterns:
  - "Create order with bounded items"
  - "Update status conditionally"
cardinality:
  orderItemsMax: 20
model:
  embed:
    - "order.items"
    - "item price/name snapshot"
  reference:
    - "order.customerId"
    - "item.productId"
consistency:
  singleDocument:
    - "status and version"
    - "items and agreed amount"
  multiDocument:
    - "reserve stock and persist order"
  external:
    - "payment authorization via saga/outbox"
indexes:
  - "tenantId,customerId,createdAt,_id"
  - "tenantId,externalOrderId unique"
risks:
  - "item cap enforcement"
  - "transaction retry contention"
  - "outbox duplicate events"
verification:
  - "exact order details"
  - "no negative stock"
  - "no duplicate external order"
  - "read/write p95 within SLO"
owner: "application architecture team"
status: "proposed"
~~~

### 55.1. Decision Records Enable Future Review

When data grows or business contracts evolve, the team can understand why embedding or transactions were originally chosen instead of guessing from the schema alone.

### 55.2. Risks Need Owners

A design with an outbox where nobody monitors queue lag or reconciliation is not truly complete.

## 56. Runbook for Selecting Model and Atomicity Level

~~~text
INPUT:
  API read/write patterns
  Data cardinality and lifecycle
  Business invariants
  Tenant/security rules
  Storage and latency SLO

MODEL:
  Embed small bounded co-owned data
  Reference large or independent data
  Snapshot historical contracts
  Materialize derived views only with sync policy

WRITE:
  One document?
    -> Atomic update with predicate/version
  Multiple documents?
    -> Is all-or-nothing required?
       YES -> transaction + same session + retry/idempotency
       NO  -> outbox/saga + eventual reconciliation
  External effect?
    -> Never assume DB transaction rolls it back

VERIFY:
  Correct result and reference integrity
  No negative stock or illegal transitions
  No duplicate business operation
  No cross-tenant data leak
  Read/write p95 and storage within SLO
  Retry/timeout/failover behavior

RECORD:
  Architecture decision
  Schema and index version
  Failure modes and owner
  Rollout/rollback plan
~~~

## 57. Reference Summary

**Embed** when data is small, bounded, shares a lifecycle, and is typically read/written with its parent. **Reference** when data is large, updated independently, shared, or carries distinct retention/permission rules. A **snapshot** is an intentional copy preserving history; never confuse it with current master data.

**Atomic updates** using `$inc`, `$set`, conditional filters, `arrayFilters`, or `findOneAndUpdate` are the default choice for invariants contained **within a single document**. **Transactions** are warranted when multiple MongoDB documents must commit or abort together on a supported deployment; they must be paired with retries/idempotency, proper concerns, and failure-case testing. For operations outside the database or long-running workflows, **outbox, sagas, and reconciliation** are generally required.

MongoDB's strength does not lie in eliminating every JOIN or wrapping every operation in a transaction. Its value comes from **setting clear data and consistency boundaries aligned with business invariants**, keeping queries fast, preventing concurrency corruption, and letting the system evolve as scale increases.

## References

- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Embedding Versus References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Manual — Schema Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/)
- [MongoDB Manual — Documents](https://www.mongodb.com/docs/manual/core/document/)
- [MongoDB Manual — Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/)
- [MongoDB Manual — Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
