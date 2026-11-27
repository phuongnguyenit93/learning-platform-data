# Choosing Between Data Embedding, Atomic Updates, and Transactions

In MongoDB, many concurrency problems do not necessarily require a **multi-document transaction**. Some business invariants can be safely preserved by **embedding related data in the same document** and performing **a single atomic update operation**. Other invariants span multiple documents or collections where a single update is insufficient; those require a **transaction** or another consistency coordination mechanism.

This lesson belongs to the **Atomicity and Concurrency** chapter of the *Database Engine Document MongoDB* module. The focus is not on "how to write transaction APIs" in isolation, but on **choosing the right consistency boundary during data modeling**, avoiding both extremes: cramming an entire system into one giant document or using transactions for every small operation.

After this lesson, you will be able to:

1. Distinguish **single-document atomicity**, **race-prevention conditions**, **multi-document consistency**, and **durability**.
2. Choose **embedding** when fields share a lifecycle and invariant, while recognizing the 16 MiB limit, hot documents, and unbounded arrays.
3. Write `updateOne()` with `$inc`, `$set`, `$push`, `$addToSet`, and `arrayFilters` to modify multiple fields **within the same document**.
4. Use **compare-and-set (CAS)**, `version` fields, and conditional filters to prevent lost updates and overselling.
5. Distinguish `updateMany()`, `bulkWrite()`, and multi-document transactions: **grouping multiple commands does not create batch-wide atomicity**.
6. Write transactions using `ClientSession`/`mongosh` for multi-document operations, handle commit/abort, and understand retryable errors.
7. Select **read concern**, **write concern**, and idempotency approaches matching requirements without confusing them with transactions.
8. Evaluate transaction cost, contention, the relationship between data modeling and performance, as well as saga/outbox choices when external systems are involved.

> **Version scope:** Examples use modern MongoDB syntax common across supported replica set/sharded cluster deployments and Java Sync Driver lines. Exact limits for transactions, sessions, retries, and read/write concerns should be verified against your running MongoDB Server/Driver version. Transaction examples do not run the same way on a **standalone mongod**, because multi-document transactions require a supported deployment. All demo commands use the `atomic_choice_lab` database; do not run them in production.

## 1. Three decision layers: where data lives, how it is updated, and how many documents must commit together

When facing the requirement "update A and B together," first identify **what A and B are**:

~~~text
Business requirement
       |
       v
Can A and B belong to the SAME aggregate/document?
       |
    +-- Yes --> Embed related parts with bounded growth
    |            |
    |            v
    |        Single atomic update + guarding filter
    |            |
    |            +-- If only updating state on 1 document:
    |                 no multi-document transaction needed.
    |
    +-- No ---> Data must live in multiple documents/collections
                 |
                 v
           Must all changes commit/abort together?
                 |
             +---+---+
             |       |
            Yes      No
             |       |
             v       v
         Transaction   Independent updates / eventual consistency
         on supported  / saga-outbox, with idempotency
         deployment
~~~

This diagram is a **guide**, not a rigid mechanical algorithm. Sometimes even though embedding is technically possible, the item count grows unboundedly, many writers contend on a hot document, or parts have independent lifecycles—in those cases, **referencing** makes more sense.

### 1.1. Comparison table of the three strategies

| Strategy | Atomicity boundary | Advantages | Costs / risks |
|---|---|---|---|
| **Embedded data + single update** | One document containing multiple fields/subdocuments/array items. | Simple, often efficient, updates multiple fields together. | Document can bloat; hot spots; data duplication; hard to separate lifecycles. |
| **Conditional atomic update on existing document** | One document, whether the data model uses scalar or embedded fields. | Checks condition and updates on the server in one write; prevents many simple races. | Guarantees nothing for other documents; filter/logic must be exact; business retries must be designed. |
| **Multi-document transaction** | Multiple operations/documents/collections/shards within the supported transaction scope. | All-or-nothing and concern-based isolation; fits cross-document invariants. | Higher cost, increased contention/cache/lock pressure, requires session, retry logic, and resource limits. |

**Embedding** is a **data modeling** decision; **atomic updates** and **transactions** are **write execution** decisions. Do not treat them as three mutually exclusive APIs. You can use an atomic update on an embedded document; you can also use transactions in a predominantly embedded system when a genuinely multi-document operation arises.

### 1.2. Three core questions

1. **Where does the invariant to protect live?** For example, `available >= 0` and a book's active checkouts live in **one book document**; the total balance across two accounts lives across **two account documents**.
2. **How many documents must change in the same business step?** An `updateMany()` touching 10 documents is **not** a group-wide atomic change.
3. **What happens if the request executes twice or fails midway?** `$inc` can increment/decrement twice if the app replays it; transaction rollback does not replace idempotency for **repeated business requests**.

## 2. What does "atomic" mean in MongoDB?

According to the MongoDB Database Manual, a **write operation modifying a single document is atomic**: fields in that document are modified **all together or not at all**, even when the update changes multiple fields and multiple array elements.

~~~javascript
db.books.updateOne(
  { _id: "BOOK-1", available: { $gt: 0 } },
  {
    $inc: { available: -1 },
    $push: {
      checkout: {
        userId: "U-100",
        at: new Date()
      }
    }
  }
)
~~~

If the document matches the filter and the update succeeds, both **`available` decrements by one** and **`checkout` gains one entry** in the same document. A reader never sees the document in a state where "available was decremented while checkout has not been added yet" due to a half-executed update.

### 2.1. What about a command modifying multiple documents?

~~~javascript
db.products.updateMany(
  { category: "stationery" },
  { $set: { promotionEligible: true } }
)
~~~

Each product document is updated **atomically on its own**, yet **the entire `updateMany()` is not atomic like a transaction**. On error or concurrent writes, some products may already be updated while others are not; other operations can interleave.

This is a fundamental distinction:

| Operation | Default atomicity |
|---|---|
| `insertOne()` | One document inserted or not. |
| `updateOne()` | One document. |
| `replaceOne()` | One document. |
| `deleteOne()` | One document. |
| `updateMany()` | **Per document**, not atomic across the whole set. |
| `deleteMany()` | **Per document**, not atomic across the whole set. |
| `bulkWrite()` | Per operation/document per its semantics; **not automatically a batch transaction**. |
| Multi-document transaction | Changes inside the transaction **commit together or abort together**. |

### 2.2. Atomicity differs from durability and "exactly once"

Three distinct properties:

- **Atomicity**: within the guaranteed boundary, a change is never left "half-done."
- **Durability/acknowledgment**: depending on write concern and replica set/commit conditions, how durably a change is persisted and acknowledged.
- **Idempotency**: whether **resending** the same business request causes additional effects.

An `$inc:{stock:-1}` is **atomic** on a document, yet **not idempotent** if a new request is submitted after the first succeeded. A transaction ensures debit/credit commit together, yet if the application runs **a new transaction** a second time for the same transfer code, money can still be transferred twice without deduplication.

### 2.3. "Single-document" guarantee does not mean "race-free"

Two clients concurrently run:

~~~javascript
// Client A
db.counters.updateOne(
  { _id: "C-1" },
  { $set: { value: 100 } }
)

// Client B
db.counters.updateOne(
  { _id: "C-1" },
  { $set: { value: 200 } }
)
~~~

Each update is atomic, yet both match `_id`. The final value can be **100 or 200 depending on execution order**; there is no built-in guarantee notifying the app "you just overwrote a valid change." When conflict detection is required, use **expected-value filters** or **version**.

## 3. Embedding: putting data that must change together into one document

MongoDB is a document database supporting embedded subdocuments/arrays. When parts of an **aggregate** are usually read and updated together with bounded cardinality, embedding lets you perform a single atomic write.

### 3.1. Book checkout example

A referencing model might split:

~~~javascript
// books
{ _id: "BOOK-1", title: "Book A", available: 3 }

// checkouts
{ _id: "CO-1", bookId: "BOOK-1", userId: "U-1" }
~~~

Borrowing a book requires decrementing `available` **and** creating a checkout, modifying **two documents**. Without a transaction, if step one succeeds and step two fails, the two collections diverge.

If the checkout list stays bounded and shares the same lifecycle, you can **embed**:

~~~javascript
{
  _id: "BOOK-1",
  title: "Book A",
  available: 3,
  checkout: [
    { userId: "U-1", at: ISODate("2026-11-12T08:00:00Z") },
    { userId: "U-2", at: ISODate("2026-11-13T08:00:00Z") }
  ]
}
~~~

Now a single `updateOne` can decrement available and append the checkout together. This is **schema design to shrink the consistency boundary**, not merely swapping transaction syntax for update syntax.

### 3.2. When embedding is a good choice

Consider embedding when:

- **One-to-few** or a **strictly bounded subset**, such as a few shipping addresses or a few active processing steps.
- Fields/embedded items **are updated together** and share a business lifecycle.
- The application **reads them together** frequently.
- A key invariant can be protected by a single **filter + update**.
- Write volume on the same document does not create an unacceptable hot spot.

A reasonable example: an order containing `status`, `shippingAddressSnapshot`, `totals`, and a bounded list of line items. When confirming the order, `status` and `confirmedAt` can be updated together in one shot.

### 3.3. When you should **not** embed just for atomicity

Full embedding backfires if:

- An array grows **unboundedly**, like millions of log events, comments, or historical transactions.
- Many independent writers constantly update **one hot document**.
- A **many-to-many** relationship has independent lifecycles, needing per-element indexing, querying, or pagination.
- Child records need independent updates, distinct access permissions, or different retention policies.
- Document size risks hitting the **16 MiB BSON limit**.
- Data is duplicated across too many parents, forcing every source update to touch thousands of documents.

A single document holding both `book.available` and the entire **unbounded** checkout history is usually a bad fit. A better design often embeds only **bounded active checkouts**, while long-term history lives in another collection updated via its own workflow. Define the consistency boundary explicitly: is history auxiliary/eventually consistent data, or must it commit atomically with inventory?

### 3.4. Embedded snapshots differ from authoritative sources

In an order, `shippingAddress` may be a **snapshot at order-placement time** that should not change when the user edits their profile address. Embedding that snapshot in the order is right even if the same address repeats across orders, because each order preserves history.

Conversely, if `customerCreditLimit` must maintain one canonical value across all orders, copying and updating the limit across every order risks inconsistent state. Keep the source of truth in the customer/account document; if multiple documents must change together under an invariant, consider transactions or rethinking the model.

## 4. Test dataset

The examples below use only the `atomic_choice_lab` database. Each demo collection is isolated so one example does not leave unintended side effects on another. **Do not re-run `insertOne/insertMany` with the same `_id` if fixtures already exist**; use a fresh lab collection or reset deliberately.

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

lab.books.insertOne({
  _id: "BOOK-1",
  title: "Book A",
  available: 2,
  checkout: [],
  version: 1
})

lab.counters.insertOne({
  _id: "COUNTER-1",
  value: 10,
  version: 1
})

lab.stock.insertMany([
  {
    _id: "SKU-A",
    available: 5,
    reserved: 0,
    version: 1
  },
  {
    _id: "SKU-B",
    available: 10,
    reserved: 0,
    version: 1
  }
])

lab.accounts.insertMany([
  { _id: "ACC-A", balance: 1000, currency: "VND" },
  { _id: "ACC-B", balance: 200, currency: "VND" }
])

lab.orders.insertOne({
  _id: "ORD-1",
  customerId: "C-1",
  status: "DRAFT",
  total: 300,
  version: 1,
  items: [
    { lineId: "L1", sku: "SKU-A", qty: 1, picked: false },
    { lineId: "L2", sku: "SKU-B", qty: 2, picked: false }
  ],
  events: []
})
~~~

For real finance, **never store money in binary floating-point** when precision to the smallest unit matters. The fixture uses small integers for illustration; real systems use **integer minor units** or BSON Decimal128 with explicit precision and currency rules. Do not treat `balance:1000` in this demo as a full financial ledger design.

### 4.1. Which cases fit a single document?

| Invariant | Where data lives | Possible approach |
|---|---|---|
| `books.available` must decrement when `books.checkout` gains an entry | Inside `BOOK-1` | One atomic `updateOne`. |
| `orders.status` changes with `orders.confirmedAt` | Inside `ORD-1` | One update with state/version filter. |
| `orders.items[L1].picked` and `orders.status` change together | Inside `ORD-1` | One update with `arrayFilters` and suitable conditions. |
| `accounts[ACC-A]` decreases and `accounts[ACC-B]` increases | **Two account documents** | Transaction if commit/abort together. |
| `stock[SKU-A]` and `stock[SKU-B]` both reserved for one order | **Two stock documents** | Transaction or explicit reservation/saga workflow. |
| `orders` transitions to PAID and sends email | MongoDB + **external email system** | Transaction does not cover email; use outbox/idempotency. |

## 5. Single atomic update on an embedded document: borrowing a book

In the fixture, `BOOK-1` has `available:2` and `checkout:[]`. When a user borrows a copy, the requirement is:

~~~text
Condition: available > 0
Simultaneous changes:
  available := available - 1
  checkout := checkout + a new checkout record
~~~

This invariant fits **a single document** very well.

### 5.1. Conditional update with two update operators

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

const result = lab.books.updateOne(
  {
    _id: "BOOK-1",
    available: { $gt: 0 }
  },
  {
    $inc: { available: -1 },
    $push: {
      checkout: {
        checkoutId: "CH-1001",
        userId: "U-100",
        borrowedAt: ISODate("2026-11-14T08:00:00Z")
      }
    }
  }
)

printjson(result)
lab.books.findOne({ _id: "BOOK-1" })
~~~

On the initial fixture, `matchedCount:1` and `modifiedCount:1`; after the update, `available:1` and the `checkout` array contains entry CH-1001. Because both fields sit **inside BOOK-1**, MongoDB ensures both changes in **one update** take effect together.

### 5.2. When two people borrow the last copy simultaneously

Suppose `available:1` remains and Clients A and B both send:

~~~javascript
lab.books.updateOne(
  { _id: "BOOK-1", available: { $gt: 0 } },
  {
    $inc: { available: -1 },
    $push: { checkout: { checkoutId: "CH-A", userId: "U-A" } }
  }
)
~~~

For Client B, the `checkout` entry has a different ID; the filter is identical. MongoDB evaluates the condition under concurrent updates:

~~~text
BOOK-1 available = 1
   |
   +-- A matches available > 0, decrements to 0 and pushes checkout
   |
   +-- B evaluates condition at write time -> available > 0 is false
         => matchedCount = 0; no push, no further decrement
~~~

If B executes first, the outcome reverses; **never oversells beyond remaining stock** within BOOK-1. This is an example of a **server-side conditional update** replacing the dangerous "client reads available then decrements" pattern.

### 5.3. Distinguishing condition failure from exceptions

`updateOne` returns `matchedCount:0` and `modifiedCount:0` when **no document matches the filter**. That is not necessarily an exception; it can mean "out of stock," "record modified by another request," or "ID not found." If the endpoint must return the exact reason, re-read state—without turning the write logic into an unprotected check-then-write.

### 5.4. Another problem: retrying the same request

Suppose CH-1001 was written successfully, yet the client timed out before receiving the response. If the application layer creates **a new request** and resends `$inc:-1` with `$push`, `available` can decrement **a second time** while stock remains. Being **atomic** does not prevent **duplicate business requests**.

One way to reduce risk on **the same document** is putting a stable **checkoutId** in the filter and array:

~~~javascript
const checkoutId = "CH-1002" // Stable ID from the request/event.

const result = lab.books.updateOne(
  {
    _id: "BOOK-1",
    available: { $gt: 0 },
    "checkout.checkoutId": { $ne: checkoutId }
  },
  {
    $inc: { available: -1 },
    $push: {
      checkout: {
        checkoutId,
        userId: "U-101",
        borrowedAt: ISODate("2026-11-14T08:10:00Z")
      }
    }
  }
)
~~~

If the prior update already added CH-1002, resending no longer satisfies `"checkout.checkoutId":{$ne:"CH-1002"}`, preventing a second decrement. Two clients sharing the same checkoutId on the same document cannot both apply this update at write time either.

**Limitation:** `matchedCount:0` could mean "checkoutId already processed," "out of stock," or "BOOK-1 not found"; the application must reconcile by checkoutId. Also, the checkout array cannot grow unboundedly. For long borrow histories, move history to a separate collection and define a workflow/transaction if history must commit with inventory.

### 5.5. Retrieving the document after updating

`findOneAndUpdate()` can **select, update, and return the document** in one operation, avoiding a separate `updateOne` followed by `findOne` read:

~~~javascript
const updated = lab.books.findOneAndUpdate(
  { _id: "BOOK-1", available: { $gt: 0 } },
  { $inc: { available: -1 } },
  { returnDocument: "after" }
)

printjson(updated)
~~~

If unmatched, the result is `null`. This snippet illustrates **decrementing** without pushing checkout. In real business logic, update both fields together as in section 5.1. Depending on shell/driver version, the option to return before/after documents may vary; check the exact API.

## 6. Preventing overselling with `$inc` and quantity filters

Suppose `SKU-A` has `available:5` and `reserved:0`. Reserving **3 units** requires `available >= 3`:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")
const quantity = 3

const result = lab.stock.updateOne(
  {
    _id: "SKU-A",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reserved: quantity
    }
  }
)

printjson(result)
~~~

On success, `SKU-A` changes from `(available:5,reserved:0)` to `(available:2,reserved:3)`. Both fields change **inside one document**, so readers never observe available decremented without reserved incremented from this operation.

### 6.1. Wrong: reading on the client then `$set`

~~~javascript
// Dangerous pattern under concurrency:
const stock = lab.stock.findOne({ _id: "SKU-A" })

if (stock.available >= 3) {
  lab.stock.updateOne(
    { _id: "SKU-A" },
    {
      $set: {
        available: stock.available - 3,
        reserved: stock.reserved + 3
      }
    }
  )
}
~~~

Two clients can both read `available:5`, `reserved:0`, and both write `available:2`, `reserved:3`. The database sees **two successful updates**, yet the final state reflects only **one reservation**, causing overselling/misallocation. That is a **lost update**, not a lack of single-command atomicity.

The fix is **putting the quantity condition and increment/decrement into the same update statement**. MongoDB will not let two updates drive available negative simply because both once saw enough at an earlier instant.

### 6.2. Difference between `$set` and `$inc` under concurrency

~~~javascript
// Client A:
lab.stock.updateOne(
  { _id: "SKU-B" },
  { $inc: { reserved: 2 } }
)

// Client B:
lab.stock.updateOne(
  { _id: "SKU-B" },
  { $inc: { reserved: 3 } }
)
~~~

When both succeed once, `reserved` increases by 5 total. `$inc` modifies **the server's current value**, rather than `$set`ting a value computed from a potentially stale client snapshot.

Still, `$inc` alone does not enforce bounds: combine `available:{$gte:quantity}`, `$inc available:-quantity`, and `$inc reserved:+quantity` **in one update**. If the same business operation can be replayed, idempotency is also required.

### 6.3. Multi-field invariants in a single document

A stock aggregate might enforce:

~~~text
available >= 0
reserved >= 0
available + reserved == totalSupply
~~~

An update `$inc:{available:-q,reserved:q}` preserves the sum when starting data is valid. MongoDB does not enforce this aggregate invariant if the application has another broken write path. Govern all write paths, add schema validation where appropriate, and test state transitions.

## 7. Compare-and-set (CAS) and optimistic concurrency control

When business logic reads a document to prepare a complex edit, it cannot always be expressed with `$inc`. If a user edits an article, you may need to **detect that someone else edited first** instead of overwriting.

### 7.1. CAS by expected value

Initially:

~~~javascript
{ _id: "COUNTER-1", value: 10, version: 1 }
~~~

Client A wants to change 10 to 20:

~~~javascript
const resultA = lab.counters.updateOne(
  { _id: "COUNTER-1", value: 10 },
  { $set: { value: 20 } }
)
~~~

Client B read the same snapshot and wants to change it to 30:

~~~javascript
const resultB = lab.counters.updateOne(
  { _id: "COUNTER-1", value: 10 },
  { $set: { value: 30 } }
)
~~~

If A executes first, B no longer matches `value:10` and receives `matchedCount:0`; if B goes first, A fails to match. One update succeeds and one is rejected by condition—**not an exception**.

### 7.2. CAS by `version` field

~~~javascript
const expectedVersion = 1

const result = lab.counters.updateOne(
  {
    _id: "COUNTER-1",
    version: expectedVersion
  },
  {
    $set: { value: 20 },
    $inc: { version: 1 }
  }
)

printjson(result)
~~~

On success, the document becomes `value:20,version:2`. Another client still carrying expectedVersion=1 no longer matches. This is **optimistic concurrency control**: allowing parallel reads while checking conflicts at write time.

### 7.3. Why must version increment in the same update?

Do not do:

~~~javascript
// Wrong: split into two operations.
lab.counters.updateOne(
  { _id: "COUNTER-1", version: 1 },
  { $set: { value: 20 } }
)
lab.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { version: 1 } }
)
~~~

Between the two commands, another writer may intervene or the second command may fail. When updating values and incrementing version **in one write**, the version predicate and new state share the same atomic boundary.

### 7.4. Handling `matchedCount:0`

Never retry infinitely with the stale expectedVersion. A workflow:

1. Re-read the latest document/version.
2. Compare desired changes against current state.
3. Decide whether to **merge**, **surface a conflict to the user**, or recompute the update.
4. Issue a fresh CAS with the new expectedVersion.
5. Cap retry attempts under high contention.

If an endpoint transitions an order from DRAFT to CONFIRMED, CAS can check `status:"DRAFT"`. When needing to detect **any change to the document**, version is stronger than checking status alone, provided all write paths increment version.

### 7.5. The ABA problem when checking only state values

If a field transitions A → B → A between a client's read and write, a filter `state:"A"` matches again even though the document changed in between. When you must detect **any intermediate modification**, incrementing `version` on every write prevents the **ABA** problem, provided all writers increment version and never reset it.

CAS **does not** replace transactions when invariants span multiple documents; a versioned update only protects that single document.

## 8. Updating arrays and status within a single document

Document `ORD-1` holds `items` and `status`. A warehouse worker wants to mark line L1 picked and move the order from DRAFT to `PICKING`. Since both changes reside in **one order document**, use one atomic update:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

const result = lab.orders.updateOne(
  {
    _id: "ORD-1",
    status: "DRAFT",
    items: {
      $elemMatch: {
        lineId: "L1",
        picked: false
      }
    }
  },
  {
    $set: {
      "items.$[line].picked": true,
      status: "PICKING",
      pickedStartedAt: ISODate("2026-11-14T09:00:00Z")
    },
    $inc: { version: 1 }
  },
  {
    arrayFilters: [
      {
        "line.lineId": "L1",
        "line.picked": false
      }
    ]
  }
)

printjson(result)
~~~

**All field changes inside ORD-1** belong to one atomic update. `arrayFilters` selects elements with `lineId:"L1"` and `picked:false`. `$elemMatch` in the filter ensures a qualifying line exists before writing; `status:"DRAFT"` guards the state transition.

### 8.1. Risks even within a single document

- If **two elements share the same lineId**, `$[line]` updates both. A unique multikey index on `items.lineId` **does not forbid duplicate lineIds within the same order**. Domain validation or separate line-item documents are required.
- If the workflow allows picking a second line once the order is already `PICKING`, keeping `status:"DRAFT"` in the filter for subsequent picks will fail to match. Conditions must reflect **all valid transition states**.
- If all lines must be picked before `READY_TO_SHIP`, define a filter predicate guarding that transition in one update, or maintain a consistent summary state.
- If line items live in **separate documents**, updating the order does not commit atomically with individual line documents.

### 8.2. Atomic updates are not free on large documents

Updating large arrays consumes CPU/I/O and multikey index maintenance. Multiple writers updating different elements still write to **the same order document**, creating contention. Choose document boundaries based on **size, write frequency, and data ownership**, not solely for atomicity.

## 9. When is referencing better than embedding?

Suppose an order can have **hundreds of thousands of line items**, each updated independently by multiple workers, needing SKU-level pagination/search and separate audit trails. Embedding everything into `orders.items` bloats the document, hurts indexes, and creates a hot document.

A referencing model:

~~~javascript
// orders:
{
  _id: "ORD-2",
  customerId: "C-2",
  status: "DRAFT",
  total: 0
}

// orderLines:
{
  _id: "LINE-2001",
  orderId: "ORD-2",
  sku: "SKU-A",
  qty: 3,
  state: "OPEN"
}
~~~

Pros: each line is its own document, indexable by `orderId`/`sku`, independently searchable/writable/paginated without bloating the order document. Cons: if the invariant is "`orders.total` equals the sum of **all** lines" and must hold **immediately at every write**, updating a line and updating the order are **not atomic together**. You then need:

- **A transaction** if the cross-document invariant must commit together; or
- **Eventual consistency** with recalculation, version/checkpoints, and repair mechanisms if business rules permit, rather than claiming total is always synchronously up to date.

### 9.1. Distinguish source of truth from derived data

If `orderLines` is the source of truth while `orders.total` is merely for display and can lag a few seconds, asynchronous projection works. However, a **payment-charging** function must never use that lagging total as verified truth unless locked by an appropriate version/snapshot/transition consistency mechanism.

When deciding, ask: **If the summary lags by 3 seconds, could we lose money, oversell stock, or breach a contract?** If yes, enforce tighter synchronous coordination or adjust aggregate boundaries.

### 9.2. One document does not equal one entity

In domain-driven design, an **aggregate boundary** is the cluster of data protecting invariants together. A MongoDB document can hold **multiple small entities/value objects**. Picking the right aggregate often makes single-document atomic updates sufficient.

Conversely, do not cram **every related entity** into one document. Distinguish "displayed together on screen" from "must commit inside one invariant." A dashboard may join multiple collections without **needing** everything inside one document.

## 10. When a multi-document transaction is needed

If business logic mandates that **multiple documents change together or none change**, single-document atomicity is insufficient. For example, transferring 150 currency units from ACC-A to ACC-B:

~~~text
Before: ACC-A = 1000, ACC-B = 200; total = 1200.

Transfer 150:
  ACC-A := 850
  ACC-B := 350

Requirement:
  either both balances change;
  or neither balance changes.
~~~

With two independent `updateOne` calls:

~~~javascript
// Command 1:
lab.accounts.updateOne(
  { _id: "ACC-A", balance: { $gte: 150 } },
  { $inc: { balance: -150 } }
)

// Command 2:
lab.accounts.updateOne(
  { _id: "ACC-B" },
  { $inc: { balance: 150 } }
)
~~~

if the first command succeeds and the second hits an error or network timeout, the two accounts drift out of balance. **Each command is atomic individually**, yet there is no shared atomicity across **the two account documents**.

### 10.1. Preparing data for transactions

The `accounts` fixture already has ACC-A and ACC-B. Create the transfer-record collection beforehand:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")
lab.createCollection("transfers")
lab.transfers.createIndex(
  { transferId: 1 },
  { unique: true, name: "ux_transferId" }
)
~~~

Run `createCollection` only once if the collection does not exist yet. In production, create collections/indexes **before** running transactions rather than creating schema structures per request. For each transfer, pass a `transferId` that is **stable and unique per business request** to detect duplicate requests.

### 10.2. Transaction example in `mongosh`

Run on a **replica set/sharded cluster** supporting transactions:

~~~javascript
const session = db.getMongo().startSession()
const txdb = session.getDatabase("atomic_choice_lab")
const amount = 150
const transferId = "TR-1001"

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  // Record the operation ID inside the same transaction.
  txdb.transfers.insertOne({
    _id: transferId,
    transferId,
    fromAccount: "ACC-A",
    toAccount: "ACC-B",
    amount,
    state: "POSTED"
  })

  const debit = txdb.accounts.updateOne(
    { _id: "ACC-A", currency: "VND", balance: { $gte: amount } },
    { $inc: { balance: -amount } }
  )
  if (debit.matchedCount !== 1) {
    throw new Error("Source account missing or insufficient funds")
  }

  const credit = txdb.accounts.updateOne(
    { _id: "ACC-B", currency: "VND" },
    { $inc: { balance: amount } }
  )
  if (credit.matchedCount !== 1) {
    throw new Error("Destination account not found")
  }

  session.commitTransaction()
  print("Transfer committed")
} catch (err) {
  print("Transaction did not finish normally: " + err.message)
  try {
    session.abortTransaction()
  } catch (_) {
    // Transaction may already be aborted, or commit outcome needs classification.
  }
  throw err
} finally {
  session.endSession()
}
~~~

If committed on the initial fixture: ACC-A becomes **850**, ACC-B becomes **350**, and `transfers` holds TR-1001. If an error occurs before commit and the transaction aborts, **no** balance changes or transfer record persist from that transaction.

**Critically important:** This is an example of **transaction boundaries and business-condition checks**, **not production-grade transaction retry/commit code**. If `commitTransaction()` returns **`UnknownTransactionCommitResult`**, you **must not assume the transaction rolled back** or unconditionally submit a new transfer. Use proper driver transaction retry APIs and reconcile by `transferId`. `abortTransaction()` in catch illustrates releasing an uncommitted transaction; uncertain commit outcomes must be handled as a dedicated branch.

### 10.3. Why put transferId inside the same transaction?

If the transfer record were saved outside the transaction, this could happen:

~~~text
Transfer record written successfully
     |
     v
Debit fails -> no money moved
     |
     v
Ledger still shows POSTED (wrong)
~~~

Placing the transfer record **in the same transaction** lets it commit/abort with the debit and credit. A unique index on transferId prevents another transaction from creating **the same ID** on retried business requests. However, a client receiving a duplicate key error must read back the transfer record and verify matching details—never treat every duplicate ID as "transfer succeeded" if amount/from/to differ.

Real financial systems also require a **double-entry ledger**, reconciliation, auditing, account freezes, currency precision, authorization, and consistency with banks/payment providers. This demo only illustrates a MongoDB transaction, not a production-ready payment system.

### 10.4. Transactions perform both reads and writes

A transaction can read related state, compute, and write multiple documents. Still, critical business conditions should be expressed via **filters at write time**, especially under contention. For example, the debit filter `balance:{$gte:amount}` directly guards the account.

Never assume that putting a `findOne` balance read inside a transaction followed by `updateOne({_id},{$set:balance - amount})` automatically solves every concurrency hazard. Transactions have write-conflict/retry semantics, yet applications must still check invariants and handle conflicts.

## 11. Do not use `updateMany` or `bulkWrite` as a transaction substitute

Some developers see multiple operations in one API call and assume they commit together. Wrong:

~~~javascript
lab.accounts.bulkWrite([
  {
    updateOne: {
      filter: { _id: "ACC-A" },
      update: { $inc: { balance: -150 } }
    }
  },
  {
    updateOne: {
      filter: { _id: "ACC-B" },
      update: { $inc: { balance: 150 } }
    }
  }
], { ordered: true })
~~~

`ordered: true` enforces sequential execution yet **does not roll back earlier steps when a later step fails**. `ordered: false` allows unordered execution, making it even less suitable when operations depend on one another.

Similarly:

~~~javascript
lab.accounts.updateMany(
  { _id: { $in: ["ACC-A", "ACC-B"] } },
  { $set: { reviewed: true } }
)
~~~

Each account is updated atomically, but **the two accounts do not share one atomic boundary**. If `reviewed:true` is just metadata tolerating partial results and retries, no transaction is needed. If two accounts share an invariant requiring identical state, use a transaction when appropriate.

### 11.1. When bulk runs *inside* a transaction

`bulkWrite()` can be invoked with **a session currently inside a transaction** on supported deployments/APIs. Then **the transaction** (not bulk itself) provides all-or-nothing semantics for the session's operations. Ensure every call passes **the exact same session**; forgetting the session runs that write **outside the transaction**.

Do not specify per-write `writeConcern` inside a transaction; read/write concerns are set at **the transaction level** and committed via the API. If a write fails, abort/retry the transaction per rules—do not expect unordered bulk to skip errors and commit the rest.

## 12. Read concern, write concern, and transactions solve different problems

Three questions commonly arise:

1. **Atomicity:** must multiple changes commit/abort together?
2. **Read isolation/consistency:** which snapshot does a transaction/reader see, and can a series of changes interleave across timestamps?
3. **Acknowledgment/durability:** to what replica/majority, journaling, and failover degree is a write acknowledged?

**Multi-document transactions** protect cross-document boundaries; **read concern** and **write concern** control configured read/write guarantees. Never mistake setting `writeConcern:{w:"majority"}` on two independent updates for turning those two updates into a transaction.

### 12.1. Write concern does not create group-wide atomicity

~~~javascript
// Two independent writes, even though the app requests majority for each.
lab.accounts.updateOne(
  { _id: "ACC-A" },
  { $inc: { balance: -50 } },
  { writeConcern: { w: "majority" } }
)

lab.accounts.updateOne(
  { _id: "ACC-B" },
  { $inc: { balance: 50 } },
  { writeConcern: { w: "majority" } }
)
~~~

If write A is majority-acknowledged and then B fails, **A does not roll back**. Majority acknowledgment only governs each individual write's confirmation, providing **no all-or-nothing** across two independent commands. (Code options apply where supported by API and deployment.)

### 12.2. Read concern in transactions

Inside transactions, MongoDB supports read concern levels such as `"local"`, `"majority"`, and `"snapshot"` per documentation. When reading a consistent snapshot across multiple transaction steps, `"snapshot"` is commonly used alongside transaction/commit write concern.

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
~~~

Exact guarantees of `snapshot` and `majority` depend on topology, where the transaction runs, and commit conditions. Never set per-operation read concerns inside a transaction; transaction-level options govern them.

### 12.3. Is a committed transaction always visible simultaneously across all reads?

Atomic commit does not mean every **non-transactional asynchronous read** observes all shards at the same snapshot. On sharded clusters, certain read concern levels outside transactions can observe committed writes on different shards at different instants. If a report needs a consistent snapshot across multiple documents/shards, pick an **appropriate read concern** (such as `snapshot` where supported) and design the read path accordingly.

Never assume "because writes used a transaction, an arbitrary sequence of `find()` calls afterward always sees one consistent read snapshot."

### 12.4. Write concern timeout differs from transaction abort

A command or commit can return a **write concern error/timeout** because the requested acknowledgment level was not reached in time. That **does not prove** data was not applied. For uncertain commit outcomes, follow the driver transaction API and error labels; never resend the business request with a new ID merely because the client did not receive success.

## 13. Retryable writes, transaction retries, and idempotency

In distributed systems, a request can do this:

~~~text
Application ----> MongoDB
     |              |
     |             WRITE applied
     |              |
     X <---- network disconnected before response
     |
     v
  Application does not know whether write succeeded.
~~~

If the application resends the request **with a new ID** without checking prior results, it can create duplicate documents or double-apply money/stock changes.

### 13.1. Distinguishing the mechanisms

| Mechanism | Effect | What it does not guarantee |
|---|---|---|
| **Driver/server retryable writes** | Retries eligible single-document writes on transient errors per session/statement. | Does not make `updateMany`/`deleteMany` or arbitrary business requests exactly-once. |
| **Whole-transaction retry** | Re-runs transaction after specific errors like `TransientTransactionError`. | Does not protect against the same business request being **re-initiated** a second time. |
| **Commit retry** | Handles uncertain commit outcomes per `UnknownTransactionCommitResult` label. | Never replace with "start a new transaction and transfer again." |
| **Business idempotency** | Attaches a stable operation ID, preventing the app from applying the same request twice. | Does not make cross-document changes atomic without a matching transaction/workflow. |

### 13.2. Important transaction error labels

Per MongoDB documentation:

- **`TransientTransactionError`:** a transient error prevented transaction completion; typically requires **retrying the entire transaction**.
- **`UnknownTransactionCommitResult`:** unknown whether commit succeeded; typically requires **retrying commit** via the transaction/session API rather than replaying the whole business flow.
- **`DuplicateKey`:** request may have violated a unique business identity; classify and verify instead of retrying blindly.
- **`TransactionTooLargeForCache`** or resource errors: transaction is too large/hot; usually requires **splitting smaller** rather than retrying endlessly.

Drivers provide **convenient transaction APIs** that automatically handle certain retry/commit labels. However, because transaction callbacks can re-execute, never place non-idempotent **emails, payment gateway charges, or external event publications** inside the callback.

### 13.3. Non-idempotent operations

| Write | Can replaying the same request after success cause additional effects? |
|---|---|
| `$set:{status:"PAID"}` on same ID | Usually keeps state unchanged, though valid transitions must be checked. |
| `$inc:{balance:-100}` | **Yes**: can debit a second time. |
| `$push:{events:event}` | **Yes**: appends duplicate events if unconditional. |
| `insertOne` with same `_id` | Next attempt hits duplicate key; reconcile to verify the original request. |
| `updateOne` with expected `version` | Replay after version increment fails to match; distinguish conflict from prior success. |
| `deleteMany` with broad filter | Later replay can delete newly added documents matching the filter. |
| Transfer transaction with unique transferId inside same transaction | Detects existing transfer; verify contents to classify. |

### 13.4. Idempotency keys must be business-stable

Example API:

~~~text
POST /transfers
Idempotency-Key: t-abc-123
Body: {from:"ACC-A",to:"ACC-B",amount:150}
~~~

The server must ensure:

1. **Same idempotency key + same payload** executes at most one logical operation.
2. **Same idempotency key + different payload** is rejected as a conflict.
3. If the prior request's outcome is uncertain, the server inspects durable state by key and reconciles.
4. If multiple documents must update all-or-nothing, record the key and apply changes **inside the same transaction** or consistent workflow.
5. Keys have policy-defined retention/TTL; deleting idempotency records too early lets old requests run again.

`retryWrites=true` in a connection string helps supported technical retries, yet **does not replace** these API-level rules.

### 13.5. Why should you not retry every transaction indiscriminately?

If a transaction failed due to **insufficient funds**, retrying identically will not help. If due to duplicate transferId, resending repeatedly only reports duplicate. If due to a short-lived write conflict, a few retries with **bounded exponential backoff/jitter** can succeed. Error classification and retry caps are mandatory to avoid overloading the cluster.

## 14. Transactions do not cover emails, payments, or message brokers

A business workflow might require:

~~~text
1. Order transitions from CONFIRMED to PAID.
2. Save payment event.
3. Send confirmation email.
4. Publish message to warehouse/shipping.
~~~

A MongoDB transaction covers writes **inside MongoDB**, yet **does not commit or roll back** SMTP calls, payment providers, or Kafka/RabbitMQ in the same transaction. An already-sent email **is not unsent** simply because the MongoDB transaction subsequently aborts.

### 14.1. Wrong: calling external services mid-transaction hoping for rollback

~~~text
Start MongoDB transaction
    |
    +-- Update order (uncommitted)
    +-- Call payment gateway -> charged successfully
    +-- Insert payment record -> validation error
    |
Abort MongoDB transaction
    |
    +-- Order rolled back, gateway still charged!
~~~

This is a **distributed workflow**, not solely a MongoDB atomicity problem. Even worse, with transaction callback retries, calling the payment gateway inside the callback can charge **a second time**.

### 14.2. Transactional outbox

A common pattern:

~~~text
MongoDB transaction:
  - Update order -> PAID
  - Insert outbox event: {eventId, orderId, type:"ORDER_PAID"}
Commit
       |
       v
Outbox dispatcher reads unpublished events
       |
       v
Publish message to broker / send email
       |
       v
Mark dispatched (retryable)
~~~

The **outbox record** commits in MongoDB alongside the order, so an order never reaches PAID without **the intent to emit the event** once the transaction commits. External communication executes **at-least-once**: the dispatcher might publish twice if it publishes successfully and dies before marking dispatched. Therefore, consumers must be **idempotent by eventId**—never assume outbox automatically yields cross-system exactly-once delivery.

### 14.3. Saga / compensation

When steps span multiple independent services, consider a **saga**:

~~~text
Reserve stock
    |
    +--> Charge payment
             |
             +--> Arrange shipment

If payment fails:
  release reservation (compensating action)

If shipment fails:
  compensate according to business rules
~~~

Compensation **is not simultaneous physical rollback**: intermediate states are visible, requiring auditing, retries, idempotency, and error handling for compensating actions themselves. Use sagas when business rules accept eventual consistency and valid compensating actions exist. For two simple MongoDB updates that must commit together, a transaction is usually clearer than a manual saga.

### 14.4. No single choice fits every step

A real system can combine:

- **Embedded order** so status transition + timestamp + address snapshot remain atomic.
- **Per-SKU conditional update** to keep stock non-negative.
- **Transaction across order and inventory reservations** when invariants span multiple documents synchronously.
- **Outbox** to emit events after commit without losing emission intent.
- **Saga** to coordinate payment gateways, fulfillment, and refunds.

Good design places **strong synchronous boundaries** only where genuinely needed, rather than forcing distant steps into one oversized transaction.

## 15. Transaction costs and operational decisions

Multi-document transactions are valuable when ACID across documents is required, yet usually cost more than single-document writes. A transaction holds session/snapshot state, can occupy WiredTiger cache/lock resources, and raises write-conflict rates when multiple clients modify overlapping data.

### 15.1. Limits to know

According to MongoDB's **Production Considerations** documentation:

- MongoDB has **`transactionLifetimeLimitSeconds`**, typically defaulting to **60 seconds**, bounding transaction lifetime. Deployments/versions may configure different limits; never design a job assuming unbounded transaction duration.
- Long or write-heavy transactions increase **WiredTiger cache** pressure and can abort due to write conflicts or errors like `TransactionTooLargeForCache`.
- Transactions acquire locks under deployment rules and timeouts, aborting if locks cannot be acquired in time.
- Operations creating collections/indexes, modifying metadata, resharding, DDL, and topology changes face specific restrictions alongside transactions.
- Transactions on sharded clusters carry coordination overhead and more complex failure modes than single writes.

Never interpret "MongoDB has transactions" as permission to open a transaction at the start of a one-million-record import job and commit at the end. Large jobs should be split into **small business units**, each with checkpoints/idempotency and its own transaction **when needed**.

### 15.2. Hot documents vs multi-document contention

Embedding lots of state into one document keeps updates atomic, yet concentrates writes:

~~~text
Document ORDER-1
  Worker A -> edits item L1
  Worker B -> edits item L2
  Worker C -> updates status
  Worker D -> appends event
~~~

Four writers contend on one document; even if each update is atomic, the workload can suffer **contention** and even lost updates if using `$set` with stale copies.

Splitting line items into separate documents relieves the hot spot, though updating an order summary synchronously with every line then needs transactions or eventual consistency. No single strategy always wins; measure **write frequency, contention, read patterns, and invariant boundaries**.

### 15.3. Especially with unbounded arrays

If an account stores its entire transaction history in an embedded array:

~~~javascript
{
  _id: "ACC-A",
  balance: 1000,
  entries: [ /* grows forever over time */ ]
}
~~~

then even though each `$push` + `$inc` is atomic, the document bloats, becomes hot, is hard to query/paginate, and approaches 16 MiB. For real ledgers, **entries are stored as separate documents**; if balance and entry must commit together, a transaction may be needed. In other designs, the ledger is the source of truth and balance is a derived summary reconciled by version/checkpoint.

### 15.4. Measure instead of guessing

Metrics to monitor:

| Metric | Symptom to watch |
|---|---|
| P50/P95/P99 write latency | Are large-document updates or transactions unusually slow? |
| Write conflicts/retries | Are many clients contending on the same documents? |
| Transaction abort rate | Are many transactions failing due to contention/timeouts? |
| Transaction duration | Are snapshots/locks held too long? |
| WiredTiger cache pressure | Is cache or history pressure spiking? |
| Replication lag/write concern latency | Is write acknowledgment adding high latency? |
| BSON document size | Are embedded arrays approaching 16 MiB? |
| Index size/write overhead | Are array/field indexes making updates expensive? |
| Outbox lag/reconciliation count | Are eventual workflows falling behind or missing items? |

A 10-document test is not enough to validate a production schema. Test with **representative data**, concurrent writers, and verify invariants after errors, timeouts, and stepdowns.

### 15.5. Optimizing transaction boundaries

An efficient transaction typically:

1. Includes **only the writes that must commit together**.
2. Makes no network calls to external services.
3. Never waits on user input or UI actions.
4. Avoids large unnecessary reads/scans.
5. Has indexes supporting critical filters (account, transferId, orderId).
6. Uses **bounded retries** guided by error labels and driver APIs.
7. Carries an **operation ID** to detect duplicate business requests.
8. Logs/monitors without exposing sensitive data.

### 15.6. When multiple documents do not need a transaction

Not every multi-document write requires ACID. For example, a job marking 50,000 articles as re-indexed:

~~~javascript
lab.articles.updateMany(
  { reindexVersion: { $lt: 42 } },
  { $set: { reindexVersion: 42 } }
)
~~~

Each document updates individually and can be retried/reconciled. If "some articles re-indexed, others not yet" is acceptable, a transaction is unnecessary and very expensive. If readers **must never** observe mixed versions, use a **versioned dataset/pointer switch** or staged rollout rather than forcing all documents into one huge transaction.

## 16. MongoDB Java Sync Driver: single-document updates and transactions

In Java, choosing the **data model** still matters more than builder syntax. The Java Driver provides `MongoCollection.updateOne()`, `findOneAndUpdate()`, `ClientSession`, and `withTransaction()`.

### 16.1. Conditional stock update

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;

// Assumes database is connected to atomic_choice_lab.
MongoCollection<Document> stock = database.getCollection("stock");

int quantity = 3;
UpdateResult result = stock.updateOne(
    and(
        eq("_id", "SKU-A"),
        gte("available", quantity)
    ),
    combine(
        inc("available", -quantity),
        inc("reserved", quantity)
    )
);

if (result.getMatchedCount() == 1) {
    System.out.println("Reservation accepted");
} else {
    System.out.println("Not enough stock or SKU not found");
}
~~~

`UpdateResult.getMatchedCount()` verifies whether the document matched the filter at write time. The code avoids a separate `findOne` followed by `$set` using a client-computed value from stale state.

### 16.2. Version CAS in Java

~~~java
import static com.mongodb.client.model.Updates.set;

long expectedVersion = 1L;

UpdateResult casResult = database.getCollection("counters").updateOne(
    and(
        eq("_id", "COUNTER-1"),
        eq("version", expectedVersion)
    ),
    combine(
        set("value", 20),
        inc("version", 1)
    )
);

if (casResult.getMatchedCount() == 0) {
    // Caller decides to read-retry, merge, or return 409 Conflict.
    System.out.println("Concurrent modification detected");
}
~~~

In the fixture, `version` starts as a BSON integer compatible with `eq("version",1L)` under MongoDB's numeric comparison semantics; in real projects, standardize the BSON/Java type and test codecs to avoid type or precision bugs. Every write path must increment version, or optimistic locking loses its guarantee.

### 16.3. Multi-document transaction with `withTransaction()`

The Java Sync Driver provides a **convenient transaction API** handling retry/commit cases by error label without writing the full transaction loop manually:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

// client: MongoClient connected to a replica set/sharded deployment.
MongoDatabase database = client.getDatabase("atomic_choice_lab");
MongoCollection<Document> accounts = database.getCollection("accounts");
MongoCollection<Document> transfers = database.getCollection("transfers");

TransactionOptions txOptions = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

String transferId = "TR-JAVA-1001";
long amount = 150L;

try (ClientSession session = client.startSession()) {
    String committedId = session.withTransaction(() -> {
        transfers.insertOne(
            session,
            new Document("_id", transferId)
                .append("transferId", transferId)
                .append("fromAccount", "ACC-A")
                .append("toAccount", "ACC-B")
                .append("amount", amount)
                .append("state", "POSTED")
        );

        UpdateResult debit = accounts.updateOne(
            session,
            and(
                eq("_id", "ACC-A"),
                eq("currency", "VND"),
                gte("balance", amount)
            ),
            inc("balance", -amount)
        );
        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Account missing or insufficient balance"
            );
        }

        UpdateResult credit = accounts.updateOne(
            session,
            and(eq("_id", "ACC-B"), eq("currency", "VND")),
            inc("balance", amount)
        );
        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException("Destination account missing");
        }

        return transferId;
    }, txOptions);

    System.out.println("Committed transfer: " + committedId);
}
~~~

Points to remember:

- Every operation belonging to the transaction must pass **the same `ClientSession`**, e.g., `transfers.insertOne(session, ...)` and `accounts.updateOne(session, ...)`.
- Create collections/indexes before entering the transaction in demo environments.
- `withTransaction` can re-run the callback on certain transient errors. Never call payment gateways or send non-idempotent emails **inside the callback**.
- If the business request is resent as a **new API call**, a new transaction can still run; the unique transferId detects duplicates, yet you must **reconcile payload/state**.
- For business-rule `IllegalStateException`, the callback aborts and the transaction does not commit; it is not a transient database error, so infinite retries will not fix it.
- Exact transaction retry and exception details depend on **Java Driver version**. This code is a structural template to integrate with logging, authorization, checkpoints, business rules, and real deployment settings.

### 16.4. Do not run parallel operations on the same session

Inside a transaction, execute operations **sequentially per driver API** rather than spawning multiple threads/async operations sharing one `ClientSession` expecting safe parallel execution. Transaction sessions have strict usage rules; many drivers do not support parallel operations inside one transaction.

### 16.5. Combining transactions with outbox in Java

Instead of sending an email directly inside the callback, add a write:

~~~java
MongoCollection<Document> outbox = database.getCollection("outbox");

// Inside the withTransaction callback, same session:
outbox.insertOne(
    session,
    new Document("_id", "EV-TR-JAVA-1001")
        .append("eventType", "TRANSFER_POSTED")
        .append("transferId", transferId)
        .append("createdAt", new java.util.Date())
);
~~~

After commit, a separate dispatcher sends the event and records dispatch status. If the event is published twice on retry, the consumer uses `eventId` to avoid double processing. Outbox protects **the intent to emit an event** inside MongoDB; it does not create atomicity between MongoDB and the broker.

## 17. Design choice scenarios

### 17.1. Scenario A — Updating order status and timestamp

**Requirement:** Allow an order in DRAFT status to transition to CONFIRMED while recording confirmation time in the same step.

**Solution:** Both fields live in the same document; use **one conditional update**:

~~~javascript
const lab = db.getSiblingDB("atomic_choice_lab")

lab.orders.updateOne(
  {
    _id: "ORD-1",
    status: "DRAFT"
  },
  {
    $set: {
      status: "CONFIRMED",
      confirmedAt: ISODate("2026-11-14T10:00:00Z")
    },
    $inc: { version: 1 }
  }
)
~~~

**No multi-document transaction needed.** If two clients confirm concurrently, one transitions the status and the other matches 0. If the workflow must also deduplicate retries at the request level, add an operation ID/version or logic returning the existing outcome.

### 17.2. Scenario B — Reserving inventory for one SKU

**Requirement:** Never let `available` go negative when multiple orders request the same SKU; track held units in `reserved`.

**Solution:** One stock document per SKU, `updateOne` filtering `available >= quantity`, `$inc available:-quantity` and `$inc reserved:+quantity`. If a separate reservation record must also be written **at the same time**, decide whether that record can be eventual or must commit together:

- **Not required synchronously:** conditional update + outbox/repair/ledger with idempotent workflow.
- **Must commit together:** transaction across stock and reservation document.

### 17.3. Scenario C — Reserving two SKUs as "all or nothing"

**Requirement:** An order needs SKU-A and SKU-B. If either SKU lacks stock, the other must not remain reserved.

Two stock documents:

~~~text
SKU-A: available=5
SKU-B: available=10
Request: reserve SKU-A 3, SKU-B 4
~~~

Two independent conditional updates are **each atomic on their own**, yet this can occur:

~~~text
Reserve SKU-A succeeds
Reserve SKU-B fails to match (out of stock or document missing)
=> SKU-A remains reserved even though the order lacks both items.
~~~

If the invariant is **immediate all-or-nothing**, put both updates in a **transaction**, check `matchedCount` on each, and abort if either misses. If business rules allow temporarily reserving each SKU and releasing when another lacks stock, use a **reservation saga** with compensation, expiration, and idempotency.

### 17.4. Scenario D — Transferring money between two accounts

**Requirement:** Debit one account, credit another, and commit a transfer record together.

**Typical solution:** Two account documents and the transfer record in a **transaction**, using a unique business transferId, checking balance/currency conditions at write time, and handling unknown commit outcomes. Do not embed all user accounts into a single system-wide document just to avoid transactions: that document would be massive, hot, and mix independent lifecycles.

### 17.5. Scenario E — Writing 100,000 log events

**Requirement:** Each log entry is independent, eventual ingestion is acceptable, and checkpoints are supported.

**Solution:** Separate documents, batched `insertMany`/`bulkWrite`, unique event IDs if deduplication is needed, and bounded retries. **Do not** embed all logs into one unbounded document. **Do not** open a giant transaction for 100,000 events unless a genuine invariant requires all-or-nothing.

### 17.6. Scenario F — Order PAID and sending email

**Requirement:** When an order becomes PAID, a confirmation email intent must be recorded, yet the email service can fail.

**Solution:** To guarantee no lost events, commit the order transition and outbox record **in MongoDB** (one document if sharing an aggregate and properly designed, or a multi-document transaction). The dispatcher sends the email post-commit with idempotent retries. Never call SMTP inside a transaction expecting rollback to unsend email.

### 17.7. Scenario G — Updating many documents when intermediate states are acceptable

**Requirement:** Mark millions of reports as migrated to schema version 3; the job can pause and resume.

**Solution:** Checkpointed batches, `updateMany`/`bulkWrite` filtering by version, idempotent updates, and reconciliation; no global transaction needed. While version 3 is still rolling out downstream, the app can **read by version or feature flag** until migration completes.

### 17.8. Scenario H — One customer with multiple shipping addresses

If each user has at most a small number of addresses, usually viewed with the profile and edited together, embedding `addresses` in the user document makes sense. If addresses have separate permissions/lifecycles, are shared across entities, or are unbounded, referencing fits better. **Do not pick embedding solely because "MongoDB supports arrays"**; evaluate access patterns.

### 17.9. Summary by scenario

| Business requirement | Data boundary | Preferred choice | Reason |
|---|---|---|---|
| Decrement available and add active checkout on same book | One book document | Embedding + conditional update | Both changes atomic together. |
| Change order status and timestamp | One order document | CAS by status/version | Prevents conflicting transitions. |
| Mark one line item in a small order | One order document | `$[line]` + single update | No multi-document transaction needed. |
| Reserve one SKU | One stock document | `$inc` with available filter | Prevents overselling on that SKU. |
| Reserve two SKUs that must both succeed | Two stock documents | Transaction or compensating saga | Depends on immediate vs eventual invariant. |
| Transfer money from A to B | Two accounts + transfer record | Transaction + unique transferId | All-or-nothing and prevents duplicate requests. |
| Store long-term audit logs | Multiple log documents | Reference + batching/idempotency | Avoids unbounded arrays. |
| Send email after order PAID | MongoDB + SMTP | Outbox, dispatcher, dedupe | Transactions do not cover SMTP. |
| Independent per-document migration | Multiple documents | Batches + checkpoints | Accepts partial progress; avoids giant transactions. |
| Multiple child entities updated independently | Multiple documents | Reference; transaction only if needed | Reduces hot documents and enables independent queries. |

## 18. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| "MongoDB is a document DB so it has no transactions." | MongoDB supports multi-document ACID transactions on appropriate deployments. |
| "With transactions available, schema design doesn't matter." | Embedded data and single-document atomicity remain simpler and more efficient when suitable. |
| "Embedding everything in one document is safest." | Risks 16 MiB limit, hot documents, unbounded arrays, and mixed lifecycles. |
| "Single-update atomicity prevents lost updates." | Two `$set` calls by `_id` can overwrite each other; use CAS/`$inc`/conditional updates. |
| "`$inc` automatically prevents overselling." | Requires `available >= quantity` in the same update filter. |
| "Since `$inc` is atomic, retrying the request endlessly is safe." | `$inc` is not idempotent at the business-request level. |
| "Checking stock with `findOne` before updating is enough." | Race between read and write; conditions belong in the write filter. |
| "`matchedCount:0` means MongoDB errored." | Usually just no matching document; can mean business rejection/conflict. |
| "Status-based CAS catches every edit." | Can suffer ABA or another field changing while status stays the same; use version when needed. |
| "Calling two updateOne commands sequentially forms a transaction." | No; partial success can occur. |
| "`ordered:true` in bulkWrite rolls back on error." | No; ordered only controls execution order and stops on failure. |
| "`updateMany` is atomic across the whole collection." | Each document is atomic; the overall operation is not. |
| "Transactions automatically stop all request replays." | A **new** business transaction can run the same action twice; an idempotency ID is needed. |
| "`writeConcern:majority` replaces transactions." | Majority governs acknowledgment/durability, not multi-document all-or-nothing. |
| "Commit timeout means the transaction aborted." | Outcome may be unknown; handle `UnknownTransactionCommitResult` per driver API. |
| "Just retry the whole business flow on timeout." | Can double debit/charge, especially if the prior commit succeeded. |
| "Inside a transaction you can call a payment service and roll it back." | External side effects sit outside MongoDB transactions. |
| "Outbox guarantees exactly-once delivery to every consumer." | Dispatch can be at-least-once; consumers must deduplicate by eventId. |
| "Sagas equal atomic rollback." | Compensation is a separate business step with visible intermediate states and potential failures. |
| "Larger transactions are always better because everything commits once." | Large/long transactions increase cache, lock, conflict, and abort risks. |
| "A document should contain only one tiny entity." | A document can hold an aggregate of multiple embedded value objects sharing invariants. |
| "A dashboard reading multiple collections must use a transaction." | Strong snapshots/transactions are needed only when **consistency requirements truly demand them**; many reports tolerate eventual/stale views. |

### 18.1. Code review checklist

When reviewing a MongoDB write path, ask:

1. **Which document or set of documents forms the invariant boundary?**
2. **Why embed?** Is element count bounded and lifecycle shared?
3. **Are write-time conditions checked?** E.g., status, available, version, eventId.
4. **Can two writers run concurrently?** If so, which wins/loses and how does the app handle matchedCount=0?
5. **If the request times out after writing, how do retries behave?** Is the business ID stable?
6. **Are there external side effects?** Is outbox/saga needed?
7. **If using a transaction, do all DB operations share the same session?**
8. **On transaction conflicts or unknown commit outcomes, are retry/catch paths correct?**
9. **Is the transaction small and bounded?** Do indexes support its filters?
10. **If data is split across multiple documents, does the system accept eventual consistency?**

## 19. Practice exercises with answers

Each exercise is independent and assumes inputs as stated. If running against `atomic_choice_lab` after earlier update examples, use a fresh lab collection or restore fixtures deliberately; previously modified values may differ.

### Exercise 1 — Choosing a model for book checkouts

A library stores at most **5 active checkouts** inside each book document. On borrow, it must simultaneously decrement `available` and add an active checkout. Is a two-document transaction required?

**Answer:** Both fields can be embedded in one book document using **a single atomic `updateOne`** with filter `available:{$gt:0}`, `$inc available:-1`, and `$push checkout`. No multi-document transaction is needed just for those two fields. Long-term borrow history can be stored separately via an explicit workflow.

### Exercise 2 — Two clients updating a counter from the same snapshot

Counter starts at 10. Client A reads 10 and wants to add 5; Client B reads 10 and wants to add 3. Both `$set` the counter to 15 and 13. Is the final counter guaranteed to equal 18?

**Answer:** No. One update overwrites the other, leaving 13 or 15 depending on order. Use:

~~~javascript
// Client A
db.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { value: 5 } }
)

// Client B
db.counters.updateOne(
  { _id: "COUNTER-1" },
  { $inc: { value: 3 } }
)
~~~

When both succeed once, the final value is **18**. If business requests can replay, idempotency is still required.

### Exercise 3 — Preventing negative stock

`SKU-A` has `available:4`, and two clients both reserve 3 items. Write an update so available never goes negative.

**Answer:**

~~~javascript
db.stock.updateOne(
  { _id: "SKU-A", available: { $gte: 3 } },
  {
    $inc: {
      available: -3,
      reserved: 3
    }
  }
)
~~~

With only 4 units, **at most one request** can deduct 3; the other fails to match when available drops to 1.

### Exercise 4 — What does `matchedCount:0` mean?

An `updateOne({_id:"SKU-A",available:{$gte:5}},...)` returns `matchedCount:0`. Does that mean the server broke?

**Answer:** Not necessarily. Either SKU-A does not exist or available is less than 5. It means **unmatched filter**, typically a business rejection/conflict. To distinguish exact causes, re-read state appropriately—never remove the safety condition from the update.

### Exercise 5 — Preventing duplicate checkouts on request timeout

A client borrows a book with `checkoutId:"CH-1"` and times out. What is the risk of retrying identically with `$inc:-1` and `$push checkout`?

**Answer:** If the first attempt succeeded, a new business retry can decrement available and push checkout a second time. Add filter `"checkout.checkoutId":{$ne:"CH-1"}` in the same update, keep the ID stable, and reconcile on matchedCount=0. For long histories, prefer a unique ledger/transaction over unbounded embedded arrays.

### Exercise 6 — Version-based CAS

Document:

~~~javascript
{ _id: "P-1", title: "Old draft", version: 7 }
~~~

Two users both read version 7 and edit title. Write a conflict-safe update.

**Answer:**

~~~javascript
db.posts.updateOne(
  { _id: "P-1", version: 7 },
  {
    $set: { title: "New version by User A" },
    $inc: { version: 1 }
  }
)
~~~

If A succeeds, version becomes 8. Request B filtering version 7 fails to match; the app can report a conflict and offer a merge.

### Exercise 7 — An order containing multiple line items

Order ORD-1 has two lines L1/L2 embedded in `items`. An operation must set `items[L1].picked = true` and `order.status = PICKING`. Is a transaction required?

**Answer:** No multi-document transaction is needed if all fields reside **inside ORD-1** using a single `updateOne` with `arrayFilters` and appropriate state predicates. If line items are separate documents that must commit with the order, evaluate transactions/invariants.

### Exercise 8 — Unbounded embedding

A system stores every comment from post creation through years later inside `posts.comments`. A popular post can receive millions of comments. Even though `$push` is atomic, should you use one document?

**Answer:** Usually **no**. Unbounded arrays bloat documents, risk hitting 16 MiB, and cause contention; comments should be separate documents or bounded subset/bucket patterns depending on access patterns. Single-document atomicity does not solve size and lifecycle issues.

### Exercise 9 — Transfer A → B without a transaction

ACC-A balance=1000, ACC-B balance=200. Debit 150 succeeds, credit 150 fails. Since each `updateOne` is atomic, does the system preserve total 1200?

**Answer:** No. State can end up as A=850, B=200, total=1050. You need a **transaction** if debit/credit must commit together, or an accepted compensating workflow if the domain permits intermediate states.

### Exercise 10 — Two SKUs that must both be reserved

An order needs SKU-A and SKU-B; ship only if **both are reserved**. If updating SKU-A succeeds and SKU-B lacks stock, what must happen?

**Answer:** If **immediate** all-or-nothing is required, run both conditional updates inside **one transaction**; check `matchedCount` on each and abort if either is short. If eventual consistency is acceptable, use a reservation saga with idempotent release, expiration, and compensation repair.

### Exercise 11 — Does `bulkWrite(ordered:true)` replace a transaction?

~~~javascript
db.accounts.bulkWrite([
  {
    updateOne: {
      filter: { _id: "ACC-A" },
      update: { $inc: { balance: -150 } }
    }
  },
  {
    updateOne: {
      filter: { _id: "ACC-B" },
      update: { $inc: { balance: 150 } }
    }
  }
], { ordered: true })
~~~

**Answer:** No. Ordered preserves execution order and halts on write errors, **without rolling back** the first update. Only a transaction spanning the session operations gives multi-document all-or-nothing.

### Exercise 12 — Majority write concern

Two independent updates each specify `writeConcern:{w:"majority"}`. If the second update fails, does the first automatically roll back?

**Answer:** No. Write concern governs write acknowledgment level, not forming a transaction across two commands. Even if both are independently majority-acknowledged, they do not form a single atomic unit.

### Exercise 13 — Retrying after an uncertain commit outcome

A client calls `commitTransaction()` and receives an error labeled `UnknownTransactionCommitResult`. Should it immediately open a new transaction and transfer the same amount again?

**Answer:** No. The prior commit **may have succeeded**. Use the transaction/driver API to retry **commit** as documented, then reconcile using a stable `transferId` if needed. Never mint a new transfer ID to replay unconditionally.

### Exercise 14 — Idempotency after transaction success

A transfer TR-1001 committed. Due to a timeout, the HTTP caller resends the same transfer request with **the same transferId**, and the handler starts a new transaction. How do you prevent double debiting?

**Answer:** Insert a unique transferId inside **the same transaction** as debit/credit. The retry hits the duplicate ID or reads existing state, verifies matching `from/to/amount`, and returns the proper idempotent result. Observing an account balance alone after timeout is insufficient to prove whether the prior business request ran.

### Exercise 15 — Payment gateway inside a transaction

A transaction updates an order, calls an external gateway to charge, and then inserts a payment record. The payment succeeds but the insert fails. Does rolling back the transaction refund the gateway charge?

**Answer:** No. MongoDB only rolls back writes belonging to the transaction **inside MongoDB**. The gateway is a separate system. Use an idempotent workflow/saga with compensation and persisted states; combine outbox/ledger per architecture.

### Exercise 16 — Does outbox publish exactly once?

The dispatcher publishes an event successfully but crashes before marking the outbox event dispatched. After restart, the event is published again. Did the outbox pattern fail completely?

**Answer:** No. This is standard **at-least-once delivery**. Outbox ensures event intent is committed with DB state; consumers deduplicate using `eventId` to avoid duplicating business side effects. Proper checkpointing and retries are still needed.

### Exercise 17 — Giant transactions

A migration wants to update 500,000 documents in a single transaction lasting several minutes. Should it do so just to "commit everything together"?

**Answer:** Re-examine the invariant boundary. Large transactions increase cache/lock pressure, hit lifetime limits, and risk aborts. When incremental progress is allowed, use idempotent batches, checkpoints, and versioned rollouts. If readers must see an atomic cutover, consider a copy/pointer-switch/version pattern to keep transaction boundaries tiny.

### Exercise 18 — Version and ABA

A state goes A → B → A while a client holds its initial snapshot. Does a CAS checking only `state:"A"` detect the intermediate change?

**Answer:** No. The filter matches again once state returns to A. Use a `version` incremented on every write to detect any modification, provided all writers increment version.

### Exercise 19 — Transaction or not for analytics reports?

A dashboard refreshes every minute showing PAID order counts and total revenue. Numbers can lag by 10 seconds without affecting billing. Is a transaction required to keep all order/revenue summaries synchronously aligned?

**Answer:** Use an **eventually consistent** projection/read model, change streams/outbox, or periodic batch aggregation with data timestamps/versions. You do not need multi-document transactions merely because a dashboard reads across collections if latency is tolerable and the numbers do not drive payment decisions.

### Exercise 20 — Single-document update boundary

A `wallet` document holds `available`, `held`, and `lastOperationId`. An update filters by ID, sufficient available, and `lastOperationId != requestId`, then runs `$inc available:-q`, `$inc held:+q`, and `$set lastOperationId:requestId`. Can it block **non-consecutive** duplicate requests after another request intervenes?

**Answer:** **Not reliably.** `lastOperationId` remembers only **the very last request**. If request A runs, then B changes lastOperationId to B, and old request A replays, the filter `lastOperationId != A` matches and processes A a second time. To deduplicate reliably across a retention window, maintain a bounded **set/ledger of operation IDs** with an appropriate retention policy, or a unique per-request record inside a transaction.

## 20. Official MongoDB documentation

When consulting docs, check the exact MongoDB Server/Driver version of your deployment, as transaction details, limits, error labels, and new features can differ across releases.

- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity, concurrent updates, `$inc`, CAS, and `updateMany` boundaries.
- [Model Data for Atomic Operations](https://www.mongodb.com/docs/manual/tutorial/model-data-for-atomic-operations/) — pattern embedding `available` and `checkout` in one document for atomic updates.
- [Embedded Data in Your MongoDB Schema](https://www.mongodb.com/docs/manual/data-modeling/embedding/) — embedding benefits for atomic reads/updates.
- [References](https://www.mongodb.com/docs/manual/data-modeling/references/) — multi-document models and when to use references.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — distributed ACID transactions, sessions, commit/abort, and behavior.
- [Transactions — Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — WiredTiger cache, lifetime, lock timeouts, and operational notes.
- [Read Concern, Write Concern, and Read Preference](https://www.mongodb.com/docs/manual/core/transactions/#read-concern-write-concern-and-read-preference) — transaction-level concerns.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — read levels, inside/outside transactions, and snapshot semantics.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j`, and write acknowledgment levels.
- [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — distinguishing atomicity from read visibility.
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retryable writes, supported conditions, and exceptions.
- [Transactions and Retry](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — guide to application transactions and driver retries.
- [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — filters, update operators, `arrayFilters`, and `upsert`.
- [`db.collection.findOneAndUpdate()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/) — updating and returning a document with atomic single-document semantics.
- [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — atomicity boundaries when modifying multiple documents.
- [`db.collection.bulkWrite()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — ordered/unordered execution and partial success without default transactions.
- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — BSON document limits and system limits.
- [FAQ: Concurrency](https://www.mongodb.com/docs/manual/faq/concurrency/) — locking, concurrency control, and concurrent writes.
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `TransactionOptions`, `withTransaction()`, and best practices.
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — `updateOne`, `UpdateResult`, and Java builders.
- [MongoDB 8.0 — Transactions](https://www.mongodb.com/docs/v8.0/core/transactions/) — version-pinned documentation for comparing behavior.

**Conclusion:** When choosing between **data embedding, atomic updates, and transactions**, start from **business invariants**, not from APIs. If fields that must change together fit cleanly inside **one document**, prefer **a single conditional atomic update** using `$inc`, `$set`, `arrayFilters`, or versioned CAS as appropriate. If data has independent lifecycles, high cardinality, or heavy contention, use **references**; reach for **multi-document transactions** only when multiple documents genuinely must commit or abort together. Finally, whether using single-document writes or transactions, still design **idempotency, retries, read/write concerns, and external side-effect handling**—because atomicity alone does not solve every concurrency and failure mode of distributed systems.
