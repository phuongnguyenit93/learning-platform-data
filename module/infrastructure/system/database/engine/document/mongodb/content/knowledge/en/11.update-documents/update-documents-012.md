# Designing Conditional Update Filters and Handling Unmatched Results in MongoDB

## 1. Why Do Document Updates Need Conditions?

In MongoDB, an update command specifies not only **the values to write**, but also **the conditions permitting the change**. For example:

- An order may transition only from `PAID` to `SHIPPED`, never shipped while still `DRAFT`.
- Inventory stock may be decremented only if the current available quantity covers the request.
- Staff members may edit only documents belonging to their tenant or authorized scope.
- A write request from the UI may apply only if the server-side `version` has not changed since the user opened the record.
- A coupon may be redeemed only if remaining uses are positive and it has not expired.
- An unmatched update must be classified accurately: does the document not exist, is the state wrong, was there a concurrent conflict, or was the filter simply too narrow?

Example missing a condition:

~~~javascript
db.orders.updateOne(
  { _id: "ord-100" },
  { $set: { status: "SHIPPED" } }
);
~~~

This command transitions the order's status **regardless of its current state**. If the business rule says "ship only paid orders", put that condition directly in the filter:

~~~javascript
db.orders.updateOne(
  { _id: "ord-100", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

**Core principle:** An update filter is part of your business rules, not merely a way to locate a document. A `matchedCount = 0` result is often an important signal, not an error to ignore.

This lesson belongs to the **Update Documents** chapter of the **Database Engine Document MongoDB** module. You will practice:

1. Designing filters by `_id`, tenant, status, version, and numeric bounds.
2. Using `updateOne()`, operators `$set`, `$inc`, `$unset`, and conditions on nested fields/arrays.
3. Distinguishing **unmatched**, **matched without changes**, **upsert**, and **execution errors**.
4. Applying compare-and-set and optimistic concurrency to avoid overwriting data.
5. Knowing when to avoid `upsert: true` and `updateMany()`.
6. Interpreting results in `mongosh`, Java Driver, and MongoDB Compass.

## 2. Structure of `updateOne` and Atomicity

In `mongosh`:

~~~javascript
db.collection.updateOne(
  filter,
  update,
  options
);
~~~

| Component | Role | Example |
|---|---|---|
| `filter` | Condition to locate the document and precondition before writing | `{ _id: "ord-100", status: "PAID" }` |
| `update` | Operators mutating data or a valid update pipeline | `{ $set: { status: "SHIPPED" } }` |
| `options` | Options such as `upsert`, `arrayFilters`, `collation`, `hint` where supported | `{ upsert: false }` |

With operator updates:

~~~javascript
{
  $set: { status: "SHIPPED" },
  $inc: { version: 1 }
}
~~~

`$set` assigns or replaces a value; `$inc` adds an amount to a numeric field. Within a single `updateOne`, MongoDB applies the update to the selected document atomically at the **single-document** level.

Logic flow:

```text
             Client sends filter + update
                         |
                         v
          MongoDB locates doc matching filter
                         |
                   +-----+------+
                   |            |
                Matched     Not matched
                   |            |
                   v            v
               Validate     upsert: false?
              constraints      |       |
                   |          Yes      No
               Succeeded       |       |
                   |           v       v
                   v       No write   May insert
             Apply update             when upsert:true
                   |
                   v
               Write result
```

**Single-document atomicity is not a multi-document transaction.** If business logic must update order status, deduct stock in another collection, and append an accounting ledger entry together, evaluate multi-document transactions and appropriate consistency patterns. This lesson focuses on per-document conditional update filters.

### 2.1. Why Must the Filter Include the Precondition?

An unsafe pattern:

~~~javascript
const order = db.orders.findOne({ _id: "ord-100" });

if (order.status === "PAID") {
  db.orders.updateOne(
    { _id: "ord-100" },
    { $set: { status: "SHIPPED" } }
  );
}
~~~

Between the two commands, another process might change `status` to `CANCELLED`. The final write still forces `SHIPPED` because the filter checks only `_id`. This is a **time-of-check to time-of-use (TOCTOU)** bug.

The safe pattern for a state transition:

~~~javascript
db.orders.updateOne(
  { _id: "ord-100", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

The `status: "PAID"` condition is checked as part of the update operation itself, eliminating the gap between "read" and "write" for that document.

## 3. Standalone Practice Dataset

Open MongoDB Server with `mongosh` using an account permitted to write to a test database:

~~~javascript
use conditional_update_lab
~~~

Seed the order dataset:

~~~javascript
const demoOrders = [
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    customerId: "cus-01",
    status: "PAID",
    version: NumberInt(1),
    amount: NumberDecimal("125.50"),
    shipping: { city: "Hanoi", method: "STANDARD" },
    lines: [
      { sku: "BK-01", quantity: NumberInt(2) },
      { sku: "BK-02", quantity: NumberInt(1) }
    ]
  },
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    customerId: "cus-02",
    status: "DRAFT",
    version: NumberInt(1),
    amount: NumberDecimal("49.00"),
    shipping: { city: "Da Nang", method: "EXPRESS" },
    lines: [{ sku: "BK-03", quantity: NumberInt(1) }]
  },
  {
    _id: "ord-300",
    tenantId: "tenant-A",
    customerId: "cus-03",
    status: "SHIPPED",
    version: NumberInt(3),
    amount: NumberDecimal("89.90"),
    shipping: { city: "Hue", method: "STANDARD" },
    lines: [{ sku: "BK-01", quantity: NumberInt(1) }]
  },
  {
    _id: "ord-400",
    tenantId: "tenant-B",
    customerId: "cus-04",
    status: "PAID",
    version: NumberInt(1),
    amount: NumberDecimal("210.00"),
    shipping: { city: "Ho Chi Minh City", method: "EXPRESS" },
    lines: [{ sku: "BK-04", quantity: NumberInt(3) }]
  },
  {
    _id: "ord-500",
    tenantId: "tenant-A",
    customerId: "cus-05",
    status: "CANCELLED",
    version: NumberInt(2),
    amount: NumberDecimal("35.00"),
    shipping: { city: "Hanoi", method: "STANDARD" },
    lines: []
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1, version: 1 }
).sort({ _id: 1 });
~~~

Create inventory and coupon data for practicing numeric conditions:

~~~javascript
db.inventory.replaceOne(
  { _id: "stock-BK-01" },
  {
    _id: "stock-BK-01",
    tenantId: "tenant-A",
    sku: "BK-01",
    available: NumberInt(8),
    reserved: NumberInt(0),
    version: NumberInt(1)
  },
  { upsert: true }
);

db.coupons.replaceOne(
  { _id: "coupon-WELCOME" },
  {
    _id: "coupon-WELCOME",
    tenantId: "tenant-A",
    status: "ACTIVE",
    remainingUses: NumberInt(2),
    expiresAt: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  },
  { upsert: true }
);
~~~

This dataset is a sandbox environment. Re-running the seed commands executes `replaceOne(..., {upsert:true})`, **resetting the sample documents** to their definitions above. Subsequent update exercises can alter document state if run repeatedly without resetting.

Inspect the current state:

~~~javascript
db.orders.findOne({ _id: "ord-100" });
db.inventory.findOne({ _id: "stock-BK-01" });
db.coupons.findOne({ _id: "coupon-WELCOME" });
~~~

## 4. Designing Filters from Identifier Keys to Business Rules

### 4.1. Start with a Unique Key

An update targeting a specific record must include an exact identifier condition:

~~~javascript
{ _id: "ord-100" }
~~~

In regular collections, `_id` has a unique index. Match the exact BSON type: the string `"ord-100"` differs from an ObjectId or another type with a similar printed representation.

If you use a broad filter:

~~~javascript
db.orders.updateOne(
  { status: "PAID" },
  { $set: { reviewed: true } }
);
~~~

MongoDB updates only **one** matching document. Never rely on natural order to guess which order that is. When targeting one specific order, use `_id` or a unique key; when genuinely updating multiple orders, use `updateMany` with tight scope controls.

### 4.2. Add Tenant Scope

In multi-tenant applications:

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A"
}
~~~

The tenant condition ensures updates never accidentally apply outside the authorized boundary. However, **a tenant filter does not replace authentication/authorization**. The server-side application must derive the allowed tenant from the authenticated identity, never blindly trusting an arbitrary `tenantId` sent in the request.

Illustrative example:

~~~javascript
db.orders.updateOne(
  { _id: "ord-400", tenantId: "tenant-A" },
  { $set: { reviewed: true } }
);
~~~

No document matches because `ord-400` belongs to `tenant-B`. That is the intended outcome in the sample dataset.

### 4.3. Add Current Status as a Precondition

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A",
  status: "PAID"
}
~~~

This filter enforces the rule "update only if the order is already paid". The condition not only locates the document, it also **expresses the pre-transition state**.

Operation:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: {
      status: "SHIPPED",
      shippedAt: new Date()
    }
  }
);

printjson(result);
~~~

From the initial sample state, `matchedCount: 1` and `modifiedCount: 1` are expected. Re-running immediately finds the document is already `SHIPPED`, failing the `status: "PAID"` precondition: `matchedCount: 0`.

This is a conditional state transition, distinct from setting status unconditionally.

### 4.4. Multiple Conditions Combine with AND by Default

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: "DRAFT",
    "shipping.method": "EXPRESS"
  },
  {
    $set: {
      "shipping.city": "Can Tho"
    }
  }
);
~~~

All conditions must hold **simultaneously**. The dot in `"shipping.method"` accesses the nested field. Similarly, `$set: {"shipping.city": "..."}` edits just the child field without replacing the entire `shipping` object.

### 4.5. Using `$in` When Multiple Starting States Are Valid

An action may allow multiple source states:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: { $in: ["DRAFT", "PENDING"] }
  },
  {
    $set: { lastCheckedAt: new Date() }
  }
);
~~~

This explicitly lists allowed states. When business rules specify an **allowlist of states**, `$in` is usually more accurate than `$nin`, because `$nin` can match missing or null fields.

## 5. Update Results: `matchedCount` vs. `modifiedCount`

An acknowledged update result typically contains:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedId: null,
  upsertedCount: 0
}
~~~

Depending on the `mongosh`/driver version and write concern, printed fields can vary, while core meanings stay consistent:

| Property | Meaning |
|---|---|
| `acknowledged` | Whether the write operation was acknowledged per write concern |
| `matchedCount` | Number of documents matching the filter; for `updateOne`, typically 0 or 1 |
| `modifiedCount` | Number of documents whose content changed; typically 0 or 1 |
| `upsertedCount` | Number of documents inserted via upsert; typically 0 or 1 |
| `upsertedId` | Identifier of the document created when upsert occurred |

Distinguish three cases:

~~~text
matchedCount = 1, modifiedCount = 1
    → Document found and content changed.

matchedCount = 1, modifiedCount = 0
    → Document found without actual changes,
      e.g., $set assigned the exact existing value.

matchedCount = 0, modifiedCount = 0, upsertedCount = 0
    → No document matched and nothing was inserted.
~~~

If `upsertedCount = 1`, an **insert** occurred; do not treat it as updating an existing document.

### 5.1. Example: Matched but Not Modified

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", tenantId: "tenant-A" },
  { $set: { status: "SHIPPED" } }
);
~~~

`ord-300` already has `status: "SHIPPED"`. Since no other field changed, the result is:

~~~javascript
{
  matchedCount: 1,
  modifiedCount: 0
}
~~~

**`modifiedCount = 0` does not mean document not found.** This is a valid *no-op*: writing the same value already stored.

### 5.2. Example: Unmatched

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

In the sample data, `ord-300` is already `SHIPPED`, so the filter does not match:

~~~javascript
{
  matchedCount: 0,
  modifiedCount: 0
}
~~~

You cannot conclude from these two counts alone that the document **does not exist**. In this example, the document exists, yet **fails the status condition**.

### 5.3. Result Handling Decision Table

| Result | Minimum Conclusion | Next Step |
|---|---|---|
| Matched 1, modified 1 | Matching record found and updated | Confirm success |
| Matched 1, modified 0 | Matching record found without changes | Check whether contract allows no-op |
| Matched 0, upserted 0 | No record satisfied the entire filter | Classify as not found / conflict / precondition |
| Upserted 1 | New record inserted | Return appropriate created/upserted response |
| Exception thrown | Command, privilege, validation, unique key, or network error | Analyze error category; never equate with no-match |
| Unacknowledged write | Insufficient confirmation metrics | Check write concern and verify state per protocol |

## 6. Unmatched Is a Business State, Not Automatically a Server Error

A filter may combine multiple conditions:

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A",
  status: "PAID",
  version: NumberInt(1)
}
~~~

If `matchedCount: 0`, common possibilities include:

1. **Not found:** the `_id` was deleted or never created.
2. **Out of scope:** the document belongs to another tenant; the app must not leak that tenant's data.
3. **Wrong status:** the document is `DRAFT`, `SHIPPED`, `CANCELLED`, or another state.
4. **Version conflict:** the document still exists, updated concurrently by another actor.
5. **Type mismatch:** ID, version, date, or number passed with an unexpected BSON type.
6. **Guard condition failed:** insufficient stock, coupon exhausted, or expired.
7. **Schema inconsistency:** field missing or `null`, causing the filter to exclude the document.

From `matchedCount: 0` alone, **you cannot know the exact single cause**. Use an inspection strategy aligned with business rules, read permissions, and allowed information disclosure.

### 6.1. Diagnosing with a Follow-Up Read After No-Match

Example on the practice database:

~~~javascript
const orderId = "ord-300";
const tenantId = "tenant-A";

const result = db.orders.updateOne(
  {
    _id: orderId,
    tenantId: tenantId,
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" }
  }
);

if (result.matchedCount === 0) {
  const current = db.orders.findOne(
    { _id: orderId, tenantId: tenantId },
    { _id: 1, status: 1, version: 1 }
  );

  if (current === null) {
    print("Record not found within allowed scope.");
  } else {
    print("Record still exists but does not satisfy update condition.");
    printjson(current);
  }
}
~~~

The tenant condition **stays in the diagnostic query**. This is vital in multi-tenant systems: never query by `_id` bypassing tenant scope and leak the true status of a resource the caller is unauthorized to see.

A post-update read is **only an observation at a later instant**. Under concurrent writes, the document may have changed again before or after diagnosis. Never treat this read as proof of the exact state at the instant the update failed.

### 6.2. Classifying Outcomes at the API Layer

A common HTTP API mapping:

| Confirmed Scenario per Application Policy | Appropriate Response |
|---|---|
| Resource does not exist in authorized scope | `404 Not Found` |
| Version mismatch or status already transitioned | `409 Conflict` |
| HTTP `If-Match` precondition failed | `412 Precondition Failed` |
| Invalid input payload | `400 Bad Request` or `422 Unprocessable Content` per convention |
| Processed successfully, including allowed no-op | `200 OK` or `204 No Content` |
| Infrastructure failure with uncertain write outcome | Appropriate error response paired with reconciliation/retry |

There is no mandatory rule that "every `matchedCount: 0` returns 404". Status codes must match your API contract and security policy.

## 7. Compare-and-Set: Atomic State Transitions

**Compare-and-set (CAS)** means writing a new value only if the current value equals an expected value.

~~~text
Expected state: PAID
New state:      SHIPPED

If server still has PAID    → write SHIPPED
If server differs from PAID → do not write
~~~

Example:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: {
      status: "SHIPPED",
      shippedAt: new Date()
    }
  }
);
~~~

When two workers concurrently try to transition a document from `PAID` to `SHIPPED`, only the worker that observes `status: "PAID"` when applying its update succeeds. The other receives `matchedCount: 0` once the state has changed.

This is especially useful for state machines, task claiming, one-time processing flags, or operations where only one actor may win a transition.

### 7.1. Never Use `$ne` When Only One Source State Is Valid

~~~javascript
// Broader than the business rule "only from PAID":
db.orders.updateOne(
  {
    _id: "ord-100",
    status: { $ne: "SHIPPED" }
  },
  { $set: { status: "SHIPPED" } }
);
~~~

`$ne: "SHIPPED"` matches documents in `DRAFT`, `CANCELLED`, or **missing the `status` field**. When only `PAID` is allowed to transition, write `status: "PAID"` explicitly.

Likewise, `$nin` excludes specific states without enforcing an allowlist; enumerate valid source states explicitly.

### 7.2. Avoid Re-Triggering Side Effects on Retries

If a state transition also sends an email, publishes an event, or deducts inventory elsewhere, the first worker succeeding does not prevent a second worker from repeating those side effects if poorly coordinated. Separate:

- **State change:** performed conditionally in the database.
- **External side effects:** handled via single-delivery/processing guarantees per contract (e.g., outbox/idempotency).

Never claim a system is "exactly once" merely because the filter includes `status: "PAID"`.

## 8. Optimistic Concurrency Using a `version` Field

Status filters help, yet sometimes status stays the same while another field changes. When a client reads a document and submits edits, use **`version`** to prevent overwriting stale snapshots.

Initial document example:

~~~javascript
{
  _id: "ord-200",
  tenantId: "tenant-A",
  status: "DRAFT",
  version: NumberInt(1),
  shipping: { city: "Da Nang", method: "EXPRESS" }
}
~~~

### 8.1. Reading the Current Version

~~~javascript
const current = db.orders.findOne(
  { _id: "ord-200", tenantId: "tenant-A" }
);

printjson({
  id: current._id,
  status: current.status,
  version: current.version
});
~~~

In real applications, the record may have been read seconds or minutes earlier; `version` is the revision the client assumes is still current.

### 8.2. Updating with `expectedVersion`

~~~javascript
const expectedVersion = NumberInt(1);

const result = db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    version: expectedVersion
  },
  {
    $set: {
      "shipping.city": "Can Tho"
    },
    $inc: {
      version: NumberInt(1)
    }
  }
);

printjson(result);
~~~

While the document is at version 1, the update succeeds and bumps version to 2. Afterward, another client submitting version 1 matches nothing. No pessimistic lock is needed to detect stale versions here.

### 8.3. Combining `version` and `status`

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: "DRAFT",
    version: NumberInt(2)
  },
  {
    $set: { status: "PENDING" },
    $inc: { version: NumberInt(1) }
  }
);
~~~

This filter protects **both** the state-transition rule and the version expectation. If either condition fails, nothing changes.

### 8.4. Requirement for `version` to Remain Meaningful

Every write path modifying protected fields must consistently increment `version`:

~~~javascript
db.orders.updateOne(
  { _id: "ord-200", tenantId: "tenant-A" },
  {
    $set: { "shipping.method": "STANDARD" },
    $inc: { version: NumberInt(1) }
  }
);
~~~

If another process modifies the document without incrementing `version`, a client holding the old version can still overwrite data. Therefore, **`version` is a protocol across all writers**, not a decorative field.

### 8.5. How to Handle a Version Conflict

When `matchedCount: 0` due to a stale version:

1. Never automatically overwrite using the same stale payload.
2. Re-read the current state within authorized scope.
3. Inform the client that data changed and provide a reload or merge path.
4. If retrying automatically, rebuild the change from the fresh document and verify the action remains valid.
5. For quantities/balances, prefer atomic update operators over overwriting precomputed totals.

A version mismatch should generally be handled as an **expected conflict**, not a server error to retry blindly.

## 9. Numeric Conditions: Deducting Stock Only When Sufficient

A common requirement is decrementing inventory without letting quantities go negative.

**Unsafe pattern:**

~~~javascript
const inv = db.inventory.findOne({ _id: "stock-BK-01" });

if (inv.available >= 3) {
  db.inventory.updateOne(
    { _id: "stock-BK-01" },
    { $inc: { available: -3, reserved: 3 } }
  );
}
~~~

Two processes can both read `available = 8`, both see enough stock, and both deduct, causing overselling when combined requests exceed inventory.

**Safer single-document pattern:**

~~~javascript
const requested = NumberInt(3);

const result = db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    tenantId: "tenant-A",
    available: { $gte: requested }
  },
  {
    $inc: {
      available: NumberInt(-3),
      reserved: NumberInt(3),
      version: NumberInt(1)
    }
  }
);

printjson(result);
db.inventory.findOne({ _id: "stock-BK-01" });
~~~

Starting from the initial data, `available` drops from 8 to 5 and `reserved` rises from 0 to 3. Attempting to deduct 6 when only 5 remain:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    tenantId: "tenant-A",
    available: { $gte: 6 }
  },
  {
    $inc: {
      available: -6,
      reserved: 6
    }
  }
);
~~~

Expected result: `matchedCount: 0`, preventing negative inventory.

### 9.1. Why `$inc` Instead of `$set`ting a Precomputed Number?

Suppose two workers both read `available = 8`. If both compute `8 - 3 = 5` and send `$set: {available:5}`, two reservations only reduce stock by 3 in total. `$inc` applies the delta against the current server value within the write itself.

Combining `available: {$gte: requested}` with `$inc` lets MongoDB evaluate the stock guard and update the document atomically.

### 9.2. Do Not Guess the Reason from `matchedCount = 0`

No match can occur because:

- The SKU / inventory ID does not exist.
- `tenantId` differs.
- `available` is insufficient.
- The `available` field is missing or has the wrong type.

The application can read authorized inventory details to craft an accurate message, without exposing other tenants' data solely to distinguish failure reasons.

### 9.3. Units and Numeric Types

Choose an integer type fitting your domain range for stock. For very large quantities, evaluate Int64 and overflow bounds. For currency, avoid imprecise Double arithmetic; use Decimal128 or integer minor units per your domain contract.

## 10. Time Windows and Usage Limits

A coupon is valid only while ACTIVE, unexpired, and having remaining uses. Combine all guards in one filter:

~~~javascript
const result = db.coupons.updateOne(
  {
    _id: "coupon-WELCOME",
    tenantId: "tenant-A",
    status: "ACTIVE",
    remainingUses: { $gt: 0 },
    expiresAt: { $gt: new Date() }
  },
  {
    $inc: { remainingUses: NumberInt(-1) },
    $set: { lastUsedAt: new Date() }
  }
);

printjson(result);
~~~

The dataset in section 3 sets the coupon to expire 7 days from seed time so the example runs cleanly in practice. With 2 uses left, two successful redemptions bring `remainingUses` to 0; a third attempt matches nothing.

### 10.1. Timestamps Must Match BSON Types

`expiresAt` is stored as a Date. If an API receives an ISO string while the database stores a BSON Date, parse it into a Date before building the comparison filter. Never assume MongoDB converts date strings to Dates automatically.

### 10.2. Evaluation Time vs. Display Time

The snippet above uses `new Date()`, taking the clock from the client issuing the request. If strict server-side time checks are required without risking client clock skew, establish a consistent time-source policy rather than assuming all client clocks stay synchronized.

For strict expiration enforcement, evaluate where the condition is checked, how timestamps are generated, and the impact of clock drift rather than focusing solely on filter syntax.

### 10.3. Avoid `$nin` for "Not Expired" Conditions

A filter like `status: {$nin:["EXPIRED"]}` can match coupons missing `status` or holding disallowed statuses. When requiring `ACTIVE`, specify `status:"ACTIVE"` alongside the `expiresAt` guard.

## 11. Nested Fields and Arrays in Update Filters

### 11.1. Conditions on Nested Objects

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    tenantId: "tenant-A",
    status: "DRAFT",
    "shipping.method": "EXPRESS"
  },
  {
    $set: {
      "shipping.city": "Hai Phong"
    }
  }
);
~~~

`"shipping.method"` is verified before updating `"shipping.city"`. Dot notation updates the child field without overwriting the whole `shipping` object.

If `shipping` is missing or has the wrong type, the condition fails to match. Never "fix" this by removing the guard when that field represents a critical business precondition.

### 11.2. Array Elements: Conditions Must Apply to the Same Object

Suppose `ord-100` has:

~~~javascript
lines: [
  { sku: "BK-01", quantity: NumberInt(2) },
  { sku: "BK-02", quantity: NumberInt(1) }
]
~~~

Requirement: decrement `quantity` by 1 on the line with `sku = "BK-01"` only if **that same line** has at least 1 left.

Do not rely on two independent dot-paths:

~~~javascript
{
  "lines.sku": "BK-01",
  "lines.quantity": { $gte: 1 }
}
~~~

Those two conditions **can be satisfied by different elements** in the same array. Use `$elemMatch` to require a single element to satisfy both:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    lines: {
      $elemMatch: {
        sku: "BK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: {
      "lines.$.quantity": NumberInt(-1)
    }
  }
);
~~~

The positional `$` in the update path refers to the array element matched by the filter. On the initial dataset, `BK-01` drops from 2 to 1.

### 11.3. What If Multiple Array Elements Share the Same SKU?

Positional `$` updates only the first matched element; if the same SKU can repeat and business rules require updating all matching lines, use `arrayFilters` with `$[identifier]` and explicit predicates.

Illustrative example:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    lines: {
      $elemMatch: {
        sku: "BK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: {
      "lines.$[line].quantity": NumberInt(-1)
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "BK-01",
        "line.quantity": { $gte: 1 }
      }
    ]
  }
);
~~~

This updates **every element** in `lines` matching `arrayFilters`, not just one. If business rules forbid duplicate SKUs in an order, enforce that constraint in the data model and write logic; otherwise updating all matching elements can over-decrement multiple lines.

### 11.4. Avoid Ambiguous Array Conditions in Sensitive Logic

Consider a document containing:

~~~javascript
lines: [
  { sku: "BK-01", quantity: NumberInt(0) },
  { sku: "BK-02", quantity: NumberInt(10) }
]
~~~

Two separate dot-paths would match `sku: "BK-01"` on the first line and `quantity >= 1` on the second line, falsely passing the document. `$elemMatch` prevents this cross-element match bug.

## 12. `matchedCount = 0` and Response Strategies

Before handling a no-match, distinguish two kinds of APIs:

- **Precondition-enforced commands:** e.g., ship an order only when PAID. No-match is a precondition failure; never strip the filter and retry unconditionally.
- **Target-state commands:** e.g., "mark reviewed = true"; if already true, a no-op may succeed per API contract.

### 12.1. "Not Found" and "State Already Changed" Are Different Issues

~~~javascript
const filter = {
  _id: "ord-300",
  tenantId: "tenant-A",
  status: "PAID"
};

const result = db.orders.updateOne(
  filter,
  { $set: { status: "SHIPPED" } }
);
~~~

On no-match, do not claim `ord-300` does not exist—it is currently `SHIPPED`. Note that if a caller lacks permission to view status, an API may intentionally return a uniform message to avoid leaking existence/state details.

### 12.2. Never Drop Conditions to "Fix" Zero Matched

Wrong:

~~~javascript
const conditional = db.orders.updateOne(
  { _id: "ord-300", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);

if (conditional.matchedCount === 0) {
  // Wrong: dropping status changes the business rule.
  db.orders.updateOne(
    { _id: "ord-300" },
    { $set: { status: "SHIPPED" } }
  );
}
~~~

This fallback destroys the precondition. If the state differs from expected, return a conflict or route to a different business workflow.

### 12.3. When Should You Retry?

Distinguish clearly:

| Scenario | Handling |
|---|---|
| `matchedCount: 0` due to status/version mismatch | Do not blindly retry with the same filter; re-read and classify conflict |
| `matchedCount: 1`, `modifiedCount: 0` | Check if valid no-op; do not treat as network failure |
| Network error before/during write, outcome unknown | Use retryable writes / reconciliation; never assume "not written" |
| Duplicate key from upsert | Inspect race/unique key, decide conditional retry |
| Validation error | Fix input or schema; never retry identical command |
| Authorization error | Adjust permissions properly; never strip tenant/scope filters |

MongoDB drivers support **retryable writes** under supported topologies. Driver retries do not guarantee arbitrary business logic or external side effects can be retried infinitely without creating duplicate records or payments.

## 13. Designing for Idempotency

**Idempotent** means repeating a request produces no unintended extra changes beyond the contract's defined outcome.

### 13.1. `$set` with the Same Value Can Be Idempotent

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", tenantId: "tenant-A" },
  { $set: { reviewed: true } }
);
~~~

The first run yields `modifiedCount: 1`; repeating it yields `matchedCount: 1, modifiedCount: 0`. Final state stays `reviewed: true`.

### 13.2. `$inc` Is Not Automatically Idempotent

~~~javascript
db.inventory.updateOne(
  { _id: "stock-BK-01" },
  { $inc: { available: -1 } }
);
~~~

Running twice for the same business request deducts two units. For operations that must run **at most once per `requestId`**, introduce an idempotency key and persistent processing state, often backed by unique constraints or transactions/outbox across documents.

A status filter prevents duplicate effects only when the status **actually changes in a way that excludes subsequent runs**.

### 13.3. CAS Helps Idempotency in One Case

~~~javascript
db.orders.updateOne(
  { _id: "ord-100", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

Once the first run succeeds, subsequent runs requiring `PAID` fail to match. Even then, the application must define what to return on replay: return conflict, accept "already SHIPPED" as logical success, or verify by `requestId`. Status `SHIPPED` alone cannot tell whether a replay came from the same caller.

## 14. Upsert: Useful, Yet Dangerous with Preconditions

`upsert: true` instructs MongoDB to insert a new document if the filter matches none. It fits "update if present, create if absent", yet can be **semantically wrong** when no-match signals a violated business precondition.

### 14.1. Example That Easily Misbehaves

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" }
  },
  {
    upsert: true
  }
);
~~~

Once `ord-100` has moved to `SHIPPED`, `status: "PAID"` no longer matches. With upsert enabled, the server attempts **to insert a new document** per upsert rules instead of reporting a normal no-match. Since `_id: "ord-100"` already exists, the insert violates the unique index and throws a duplicate key error.

If the filter lacks a unique `_id`, the system risks inserting unintended duplicate documents. Therefore:

> **Never enable upsert merely to "handle" `matchedCount = 0` on a conditional state transition.**

### 14.2. Using Upsert for Configuration by Unique Key

A better example is saving settings keyed by `_id`:

~~~javascript
db.settings.updateOne(
  { _id: "tenant-A:notification" },
  {
    $set: {
      enabled: true,
      updatedAt: new Date()
    },
    $setOnInsert: {
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

If absent, the document is inserted. If present, `$set` updates its fields while `$setOnInsert` applies only to the insert branch.

Distinguish the outcomes:

~~~text
matchedCount: 1, upsertedCount: 0 → updated existing document
matchedCount: 0, upsertedCount: 1 → created new document
~~~

Under concurrent upserts, a unique index and duplicate-key handling remain essential.

## 15. `updateMany`: Cannot Be Treated Like `updateOne`

`updateMany` modifies **all documents matching the filter**, magnifying the blast radius of an overly broad filter.

~~~javascript
db.orders.updateMany(
  {
    tenantId: "tenant-A",
    status: "DRAFT"
  },
  {
    $set: {
      needsReview: true
    }
  }
);
~~~

In the initial sample dataset, this targets `ord-200`. In production databases, thousands of documents could match the same status.

### 15.1. Previewing Scope

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "DRAFT"
};

db.orders.find(
  filter,
  { _id: 1, tenantId: 1, status: 1 }
);

db.orders.countDocuments(filter);
~~~

Only after confirming the scope, run the update:

~~~javascript
db.orders.updateMany(
  filter,
  {
    $set: {
      needsReview: true
    }
  }
);
~~~

**Note:** running `countDocuments` beforehand does not freeze the data. New documents can enter or leave the filter between counting and updating. If you need a fixed snapshot set, design batch/snapshot/transaction workflows rather than treating a preview read as a lock.

### 15.2. Why `matchedCount` and `modifiedCount` Can Differ

`updateMany` may return:

~~~javascript
{
  matchedCount: 50,
  modifiedCount: 35
}
~~~

This happens when 15 documents already had `needsReview: true`. It does not indicate 15 failures. Cross-check the update expression and prior state.

### 15.3. No Whole-Batch Transaction from `updateMany` Alone

Update atomicity applies per individual document. Across multiple documents, updates occur document by document; never assume all documents transition atomically as one transaction merely because you called `updateMany`. When all-or-nothing across multiple documents is required, evaluate multi-document transactions and their operational limits.

## 16. Filter Edge Cases

### 16.1. `$ne` and `$nin` Can Match Missing Fields

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-200",
    status: { $ne: "SHIPPED" }
  },
  {
    $set: { readyForShipping: true }
  }
);
~~~

If `status` is missing, `$ne` still matches. Likewise, `$nin` matches missing fields. When business rules require status to belong to an explicit set, use `status: {$in:["PAID","READY"]}`.

### 16.2. `null` Is Not the Same as Missing

~~~javascript
{ status: null }
~~~

In MongoDB, null-equality matches both `null` fields and missing fields. To match only BSON Null, use:

~~~javascript
{ status: { $type: "null" } }
~~~

To require the field to exist:

~~~javascript
{ status: { $exists: true } }
~~~

Note that `$exists: true` still matches fields set to `null`. Use `$type: "string"` or schema constraints when status must be a string.

### 16.3. BSON Types Must Match

~~~javascript
{ version: NumberInt(1) }
~~~

If a client passes `"1"` as a string, comparing against a numeric `version` will not match. Across BSON numeric types, MongoDB has numeric equivalence rules, yet **strings differ from numbers** and **ObjectIds differ from hex strings**.

At the API boundary, parse and validate IDs, numbers, and dates before constructing filters. A type-mismatch no-match can easily masquerade as a state conflict.

### 16.4. `$or` Requires Proper Grouping

For example, allowing transitions from `PAID` or `READY` while always enforcing `_id` and tenant:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    $or: [
      { status: "PAID" },
      { status: "READY" }
    ]
  },
  {
    $set: { status: "SHIPPED" }
  }
);
~~~

Here `_id` and `tenantId` are ANDed with the `$or` group. A shorter equivalent is:

~~~javascript
{
  _id: "ord-100",
  tenantId: "tenant-A",
  status: { $in: ["PAID", "READY"] }
}
~~~

Never put an `$or` branch outside the tenant constraint, as doing so can accidentally authorize unrelated records.

### 16.5. Empty Filter

~~~javascript
db.orders.updateOne(
  {},
  { $set: { accidentallyTouched: true } }
);
~~~

An empty filter `{}` selects an arbitrary document in the collection. When targeting a single order, `{}` is far too broad.

With `updateMany({}, ...)`, it affects the entire collection. Backends should enforce guards rejecting writes missing identifier/scope filters unless a full-collection operation is explicitly intended.

### 16.6. Unindexed Conditions

A filter can be logically accurate yet slow on large collections. `_id` filters leverage the default unique index. When updating frequently by business keys such as `{tenantId, externalOrderId}`, consider a compound unique index matching business requirements.

Avoid over-indexing every auxiliary `status`/`version` column indiscriminately; review query plans against write and index maintenance costs.

## 17. Monitoring Update Results in MongoDB Compass

MongoDB Compass lets you inspect documents, enter filters in the Documents tab, and edit data depending on version. To observe exact `updateOne` semantics and `matchedCount`/`modifiedCount`, run commands in `mongosh` and inspect results in Compass.

Workflow:

1. Connect Compass to the same cluster/server used by `mongosh`.
2. Open `conditional_update_lab` and the `orders` collection.
3. Enter the filter:

   ~~~json
   {"_id":"ord-100","tenantId":"tenant-A","status":"PAID"}
   ~~~

4. Inspect the document before updating. Run the state-transition `updateOne` in `mongosh`.
5. Click Refresh Documents; filter by `_id` and `tenantId` alone to view the post-update state.
6. Re-apply the filter including `status: "PAID"` and refresh; if the update succeeded, the list is empty because the document no longer holds the old status.
7. Trigger a version conflict on `ord-200`, and verify the updated version in Compass.
8. Open `inventory` and inspect `available` and `reserved` before/after the conditional `$inc` example.

**Common pitfall:** An empty filter result in Compass after an update **does not mean the document was deleted**. It simply no longer satisfies the status/version filter currently entered.

Compass UI behavior varies across versions. Clicking Edit Document and Save does not necessarily emit the exact `updateOne` command studied here. Always verify server state and `mongosh` outputs directly.

## 18. Java Driver: Reading Results and Classifying No-Match

Example using the MongoDB Java Driver with `Filters` and `Updates`:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Date;

MongoCollection<Document> orders = database.getCollection("orders");

Bson filter = and(
    eq("_id", "ord-100"),
    eq("tenantId", "tenant-A"),
    eq("status", "PAID"),
    eq("version", 1)
);

Bson update = combine(
    set("status", "SHIPPED"),
    set("shippedAt", new Date()),
    inc("version", 1)
);

UpdateResult result = orders.updateOne(filter, update);

if (result.getMatchedCount() == 0) {
    System.out.println("No match: not found or precondition conflict");
} else if (result.getModifiedCount() == 0) {
    System.out.println("Matched, but no effective change");
} else {
    System.out.println("Updated successfully");
}
~~~

This snippet assumes `database` is a connected `MongoDatabase`; it illustrates the core operation logic rather than a complete standalone Java program with connection/try-with-resources boilerplate.

Explanation:

- The filter specifies `_id`, `tenantId`, `status`, and `version`.
- The update both changes status and increments version.
- `getMatchedCount() == 0` alone is insufficient to pinpoint the exact cause.
- To classify further, perform an authorized scoped read and handle concurrent races appropriately.

### 18.1. Scoped No-Match Handling Pattern

~~~java
if (result.getMatchedCount() == 0) {
    Document current = orders.find(
        and(
            eq("_id", "ord-100"),
            eq("tenantId", "tenant-A")
        )
    ).first();

    if (current == null) {
        // Not found within the allowed tenant scope.
        // Return Not Found per API policy.
    } else {
        // Document exists but precondition no longer holds.
        // Return Conflict/Precondition Failed per API contract.
    }
}
~~~

The follow-up read reflects state at a newer instant; under concurrent writes, it is not guaranteed to mirror the exact instant of the failed update. Applications must return consistent responses without leaking sensitive details, while logging safely.

### 18.2. Conditional Inventory Example in Java

~~~java
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

MongoCollection<Document> inventory = database.getCollection("inventory");

int requested = 3;

Bson stockFilter = and(
    eq("_id", "stock-BK-01"),
    eq("tenantId", "tenant-A"),
    gte("available", requested)
);

Bson stockUpdate = combine(
    inc("available", -requested),
    inc("reserved", requested),
    inc("version", 1)
);

UpdateResult stockResult = inventory.updateOne(stockFilter, stockUpdate);

if (stockResult.getMatchedCount() == 0) {
    // Insufficient stock or inventory record not visible within allowed scope.
}
~~~

Do not unconditionally map `stockResult.getMatchedCount() == 0` to "out of stock", as the SKU might not exist or belong to a different tenant.

## 19. Index Planning and Query Inspection

A straightforward way to inspect how a filter locates documents is running `find` with the same filter and `explain`:

~~~javascript
const filter = {
  _id: "ord-100",
  tenantId: "tenant-A",
  status: "PAID",
  version: NumberInt(1)
};

db.orders.find(filter).explain("executionStats");
~~~

Note that the sample dataset has very few documents, so explain metrics here do not represent production performance.

Fields to inspect:

| Property | Meaning |
|---|---|
| `winningPlan` | Selected query execution plan |
| `IXSCAN` | Index scan stage |
| `COLLSCAN` | Collection scan stage |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of matching documents returned by `find` |

Filters by `_id` use the default index directly. For updates by `tenantId`, `externalId`, or state-machine queries over many records, design indexes around real query patterns and uniqueness needs. Indexes optimize finding documents; they **do not replace** preconditions in the filter.

When using collations or mixed BSON types, ensure queries and indexes share compatible comparison configurations.

## 20. Common Pitfalls and Fixes

| Symptom | Possible Cause | Fix |
|---|---|---|
| `matchedCount: 0` even though ID exists | Status/version/tenant filter failed | Check each precondition; never drop conditions and blindly retry |
| `modifiedCount: 0` with `matchedCount: 1` | `$set` matched existing value (no-op) | Handle per API contract; do not return not found |
| Re-running state transition fails to match | State already moved away from old value | Often CAS working as designed |
| Version filter fails to match | Client held a stale snapshot | Reload, report conflict, or merge safely |
| Inventory goes negative | Deducted without precondition or unguarded writer bypassed protocol | Pair `available: {$gte: requested}` with `$inc`, enforce schema/invariants |
| Update hit wrong order | Filter checked only status or non-unique field | Include `_id`/unique key and tenant |
| `$ne` filter picked documents missing the field | `$ne`/`$nin` match missing fields | Use allowlist `$in`, plus `$exists`/`$type` when needed |
| Array update edited unintended line item | Array predicates matched across different elements | Use `$elemMatch` and proper positional updates |
| `upsert:true` caused duplicate key | Precondition no-match triggered insert attempt | Disable upsert for state transitions; separate create flows |
| Pre/post read disagrees with `matchedCount` | Concurrent modifications occurred | Treat reads as point-in-time observations; use CAS/transactions |
| Retry deducted quantity twice | `$inc` is not business-idempotent | Use idempotency keys, deduplication, and result checks |
| String ObjectId filter fails to match | BSON type mismatch | Parse IDs into exact BSON types |
| Update rejected despite matching filter | Schema validation, unique index, privileges, or server error | Inspect exception separately; never classify as no-match |
| Bulk update changed only one record | Used `updateOne` when `updateMany` was intended | Define exact scope, preview, and safety bounds |
| Called `updateMany` with `{}` | Empty filter matched entire collection | Add app-layer guards, strict privileges, and pre-checks |

## 21. Guided Practice Exercises

Before each exercise, if you need the exact starting state described, reload the sample dataset from section 3. Never use a production database.

### Exercise 1. Conditional State Transition

Starting from `ord-100` in `PAID` status, run:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: {
      status: "SHIPPED",
      shippedAt: new Date()
    }
  }
);
~~~

**Question:** What are `matchedCount` and `modifiedCount` on the first run? How do they change if you run the exact same command again immediately?

*Hint:* First run is `1/1`, second run is `0/0` because the precondition no longer holds.

### Exercise 2. Distinguishing No-Match from No-Op

Run on `ord-300`:

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", tenantId: "tenant-A" },
  { $set: { status: "SHIPPED" } }
);
~~~

Then run:

~~~javascript
db.orders.updateOne(
  { _id: "ord-300", status: "PAID" },
  { $set: { status: "SHIPPED" } }
);
~~~

**Question:** Why does the first yield `matched=1, modified=0` while the second yields `matched=0, modified=0`? Which command actually located the document?

### Exercise 3. Filters Must Preserve Tenant Scope

Try:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-400",
    tenantId: "tenant-A",
    status: "PAID"
  },
  {
    $set: { needsReview: true }
  }
);
~~~

**Expected:** `matchedCount: 0`. `ord-400` belongs to another tenant. Why must diagnostic read queries in APIs also retain the tenant condition?

### Exercise 4. Version Conflict

Reset `ord-200` and run:

~~~javascript
const first = db.orders.updateOne(
  {
    _id: "ord-200",
    version: NumberInt(1)
  },
  {
    $set: { "shipping.city": "Hai Phong" },
    $inc: { version: NumberInt(1) }
  }
);

const second = db.orders.updateOne(
  {
    _id: "ord-200",
    version: NumberInt(1)
  },
  {
    $set: { "shipping.city": "Can Tho" },
    $inc: { version: NumberInt(1) }
  }
);

printjson({ first, second });
~~~

**Expected:** The first matches, while the second fails to match because `version` incremented. Explain how the client should report and handle the conflict.

### Exercise 5. Conditional Stock Deduction

After resetting `stock-BK-01` to `available = 8`:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    available: { $gte: 3 }
  },
  {
    $inc: {
      available: -3,
      reserved: 3
    }
  }
);
~~~

**Expected:** `available = 5`, `reserved = 3`.

Try deducting 6 more:

~~~javascript
db.inventory.updateOne(
  {
    _id: "stock-BK-01",
    available: { $gte: 6 }
  },
  {
    $inc: {
      available: -6,
      reserved: 6
    }
  }
);
~~~

**Expected:** No match, `available` stays 5. Why is pre-checking stock with `findOne` insufficient?

### Exercise 6. Expired or Exhausted Coupon

Run the command from section 10 three times on a coupon with `remainingUses = 2`. Analyze `matchedCount` on each run. If it expires during practice, reset the coupon and re-run.

### Exercise 7. Same Array Element

On the initial `ord-100`, decrement `quantity` of SKU `BK-01` if at least 1 remains:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-100",
    lines: {
      $elemMatch: {
        sku: "BK-01",
        quantity: { $gte: 1 }
      }
    }
  },
  {
    $inc: { "lines.$.quantity": -1 }
  }
);
~~~

**Question:** Which invariant does `$elemMatch` protect? When should `arrayFilters` be used instead?

### Exercise 8. Avoiding Upsert on State Transitions

Explain the risk of this command:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-300",
    status: "PAID"
  },
  {
    $set: { status: "SHIPPED" }
  },
  {
    upsert: true
  }
);
~~~

**Hint:** `ord-300` is currently `SHIPPED`, so the filter does not match. Upsert tries to create a document with the same `_id`, violating the unique index. Disable upsert when transitioning existing documents.

### Exercise 9. Choosing API Responses

Suppose an update API receives:

| Result | Interpretation |
|---|---|
| `matched=1, modified=1` | Change applied |
| `matched=1, modified=0` | Matched without changes |
| `matched=0, upserted=0` | Filter unsatisfied; needs classification |
| `upserted=1` | New document inserted |
| Driver throws duplicate key | Unique index violation or upsert race |
| Driver throws validation error | Post-update document violates validator |

Decide which cases mean success, conflict, or error per API contract. Never return a single generic status code for every `modifiedCount = 0` outcome.

### Exercise 10. Designing Filters for Requirements

Write filters for these requirements:

1. Transition order `ord-100` only if it belongs to `tenant-A` and is `PAID`.
2. Edit address on `ord-200` only if `version = 1` and status is `DRAFT`.
3. Reserve 4 units of `stock-BK-01` only if enough `available` stock remains.
4. Redeem coupon `coupon-WELCOME` only if ACTIVE, unexpired, and uses remain.
5. Update line `BK-01` of `ord-100` only when that same element has `quantity >= 2`.
6. Flag `DRAFT` orders of `tenant-A` for review without touching other tenants.

**Mental checklist:**

~~~text
Which entity am I updating?
    ↓
Which identifier is unique and tenant-scoped?
    ↓
Which status/version/numeric conditions must hold AT WRITE TIME?
    ↓
Which update operators avoid overwrites and reduce race risks?
    ↓
How should matchedCount / modifiedCount / upsertedCount be handled?
    ↓
If unmatched, is retry allowed or must conflict be returned?
~~~

## 22. Key Takeaways for Production Systems

- **Filters are preconditions:** put `_id`, tenant, status, version, and numeric bounds directly in the update command rather than checking with `findOne` and writing unconditionally.
- **Single-document updates are atomic:** combine `$inc`, `$set`, and consistent filters to enforce invariants within a document; never mistake that for multi-document transactions.
- **Read results accurately:** `matchedCount = 0` does not imply non-existence; `modifiedCount = 0` does not imply failure.
- **Never relax filters on no-match:** failed preconditions must drive business handling rather than stripping `status` or `version` just to force a write through.
- **Use explicit allowlists:** `$ne`/`$nin` can match missing fields; when only specific states are valid, `$in` is safer.
- **Be careful with upsert:** no-match from a failed precondition is completely different from no-match because a record has not been created yet.
- **Protect against concurrency:** `version`/CAS works only when every write path follows the same protocol.
- **Handle retries distinctly:** `$set` of a constant value and `$inc` of a counter have different repeatability semantics; use idempotency keys for financial, inventory, and external side effects.
- **Measure and verify:** use `mongosh`, Compass, logs, and `explain` to validate data, filter conditions, and query plans while preserving access boundaries.

Well-designed conditional update filters enable MongoDB to execute **the right action, on the right document, in the right state**. Explicit handling of unmatched results helps systems distinguish valid conflicts from real errors, avoid accidental overwrites, and preserve consistency under concurrent actors.
