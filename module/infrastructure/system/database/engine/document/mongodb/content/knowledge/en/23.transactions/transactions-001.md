# When Are Multi-Document Transactions Needed

MongoDB guarantees that **a write operation on a single document is atomic**, even when that operation modifies multiple fields or multiple elements of an array. For that reason, having two values that must change together does not automatically mean you need to open a **multi-document transaction**. If those values reside in the same properly modeled document, a conditional `updateOne()` is usually sufficient.

A **multi-document transaction** becomes necessary when a **business invariant** or an **all-or-nothing** operation must span **multiple documents**, multiple collections, or multiple shards, and the application **cannot accept a partially applied state**. In that case, a transaction lets you group writes within a shared commit/abort boundary.

For example: transferring money from account A to B requires both **debiting A** and **crediting B** to take effect; an update command on A does not protect B's document. However, if you are only updating stock quantities within *a single* inventory document, using a multi-document transaction is unnecessary.

This lesson belongs to the **Transactions** chapter of the *Database Engine Document MongoDB* module. The focus is on **identifying the right time to use transactions**, designing small transaction scopes, using sessions and handling concurrency, as well as cases where you **should not use transactions** even when data spans multiple documents.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **single-document atomicity**, **multi-document atomicity**, **read isolation**, **write concern**, and **idempotency**.
2. Identify whether a business invariant resides within a single document or spans multiple documents/collections.
3. Decide when to **embed data**, use a **conditional update**, use a **unique index**, or open a **multi-document transaction**.
4. Explain why `updateMany()`, `insertMany()`, and `bulkWrite()` are **not automatically transactional across the entire group**.
5. Design scenarios for money transfers, reserving multiple SKUs, creating orders with reservations, and updating a ledger using transactions.
6. Understand read/write concern, snapshots, write conflicts, unknown commit results, and retries.
7. Write transactions using `mongosh` and the **MongoDB Java Sync Driver**, properly using `ClientSession`.
8. Recognize transaction limitations when dealing with **external services**, hot documents, large resources, sharding/DDL, or consistency invariants that are not properly guarded.
9. Apply a **decision table** before introducing transactions into a system.

> **Environment and Version:** MongoDB supports multi-document transactions on **replica sets** and **sharded clusters** on supported versions; do not run multi-document transactions against a standalone `mongod` as if it were a replica set. Examples use a dedicated database `txn_need_lab` and illustrate common APIs in modern MongoDB. Limits on transaction lifetime, creating collections/indexes inside transactions, read/write concern, and retries vary by server/driver version; always consult the documentation matching your actual deployment. Do not execute demos on production.

## 1. Atomicity Boundary: Single Document vs. Multiple Documents

A MongoDB write operation on **a single document** guarantees that all modifications within that operation are applied together:

~~~javascript
db.inventory.updateOne(
  {
    _id: "SKU-001",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2
    }
  }
)
~~~

In `SKU-001`, both the `available` and `reserved` fields change together in **a single update**. If the filter is not satisfied, neither field changes. When multiple clients operate concurrently, MongoDB evaluates the filter at write time; the `available >= 2` condition prevents over-reserving beyond the remaining quantity in this document.

In contrast, an operation that must update **two documents**:

~~~javascript
// Decrease A's balance.
db.accounts.updateOne(
  { _id: "ACC-A" },
  { $inc: { balance: -150 } }
)

// Increase B's balance.
db.accounts.updateOne(
  { _id: "ACC-B" },
  { $inc: { balance: 150 } }
)
~~~

Each `updateOne` is atomic with respect to its own document. However, if the first command succeeds and the second fails, MongoDB **does not automatically roll back** ACC-A. Two sequential commands do not share an **all-or-nothing** boundary.

### 1.1. Easily Confused Terms

| Concept | Question It Answers | Example |
|---|---|---|
| **Atomicity** | Can a group of changes happen **partially**? | Debiting A and crediting B commit/abort together. |
| **Isolation** | How can concurrent operations observe/interleave state? | A transaction reads a snapshot while another writer modifies a document. |
| **Consistency** | Which business invariants must be preserved? | Total balance/stock must match the ledger. |
| **Durability / write concern** | To what extent are writes acknowledged by replicas and durable? | `w:"majority"`. |
| **Idempotency** | Does resending the same *business request* duplicate the effect? | A Transfer ID must not transfer money twice. |
| **Retryable write / transaction retry** | Which technical errors can the driver retry? | `TransientTransactionError`, `UnknownTransactionCommitResult`. |

**A transaction does not define business invariants on its own.** If the application sends a debit of 150 and a credit of 120 **in the same transaction**, MongoDB can commit both even though the total amount is wrong. A transaction guarantees **committing/aborting the issued writes together**, while checking amounts, balances, and reconciliation remains the responsibility of business logic.

### 1.2. Atomicity of Command Groups

| Write Method | Default Atomic Scope |
|---|---|
| `insertOne`, `updateOne`, `replaceOne`, `deleteOne` | Single document. |
| `findOneAndUpdate` with predicate | Single document; can return pre-update or post-update version. |
| `updateMany`, `deleteMany` | Individual document by document; **not all-or-nothing across all documents**. |
| `insertMany` | Does not automatically roll back prior inserts on partial failure. |
| `bulkWrite`, even with `ordered:true` | Ordering/stopping on error **does not mean** a transaction across the whole batch. |
| Writes inside the same successfully committed **transaction** | Commit together; if aborted, none of the transaction's writes are applied. |

### 1.3. When Multiple Fields Can Reside in the Same Document

~~~javascript
{
  _id: "ORDER-1",
  state: "DRAFT",
  confirmedAt: null,
  totals: { subtotal: 150, tax: 15, grandTotal: 165 },
  items: [
    { sku: "PEN", qty: 3, price: 20 },
    { sku: "BOOK", qty: 1, price: 90 }
  ]
}
~~~

If confirming an order only changes `state`, `confirmedAt`, and `totals`, a single atomic update on `ORDER-1` is enough to keep them consistent:

~~~javascript
db.orders.updateOne(
  { _id: "ORDER-1", state: "DRAFT" },
  {
    $set: {
      state: "CONFIRMED",
      confirmedAt: new Date(),
      totals: { subtotal: 150, tax: 15, grandTotal: 165 }
    }
  }
)
~~~

Do not split this operation into multiple separate `updateOne` calls if it can be expressed as one update; conversely, **you also do not need a multi-document transaction** for this single-order operation.

## 2. The Decision Question: “Do Multiple Documents Need All-or-Nothing?”

To make the right choice, start with the **invariant**, not the number of collections.

~~~text
Identify the business invariant
         |
         v
Can all state that needs updating fit
in ONE reasonable document?
         |
       +---+
       |
   Yes |                          No
       v                            |
  One conditional update            v
  + CAS/version if needed     Multiple documents need to change
                                    |
                                    v
                      Is partial state acceptable,
                      followed by later reconciliation/compensation?
                             |                |
                            Yes              No
                             |                |
                             v                v
                       Batches, saga,      Transaction
                       outbox, eventual    if supported by system
                       consistency         and scope is appropriate
~~~

### 2.1. Three Criteria That Usually Make a Transaction the Right Choice

**First: There are at least two independent changes across different documents.** For example, a reservation record in `reservations` and an inventory item in `stock`, or two account documents.

**Second: The business cannot allow a partial commit.** If the reservation is saved but stock is not decremented, the system could oversell. If the debit is recorded but the credit is not, the ledger is temporarily incorrect.

**Third: No single-document model or alternative business mechanism is a better fit.** Embedding data might make a document too large, create contention among many writers, or merge entities with independent lifecycles. When you want to keep them as separate documents while still requiring all-or-nothing, a transaction is a candidate.

### 2.2. Multiple Documents Alone Is **Not Enough** to Require a Transaction

Examples:

- Importing 100,000 catalog documents. It is acceptable if the first 10,000 documents are inserted, then subsequent batches continue and retry by ID.
- Updating thousands of documents to add `schemaVersion:2`. Each record can change independently, and the system supports reading both versions concurrently during migration.
- Writing logs/audit/analytics that do not affect the primary business outcome and can be eventual.
- View counts or dashboard aggregations that can lag by a few seconds.
- Deleting soft-deleted records according to a retention policy can proceed incrementally.

These are cases with **multiple writes**, but typically **there is no invariant requiring all records to commit at the exact same point in time**. Using a massive transaction merely to avoid an “in-progress job” state can consume excessive resources and be harder to recover than idempotent batching.

### 2.3. A Unique Index Can Replace a Transaction for Uniqueness Problems

Two clients concurrently create an account with email `"an@example.test"`. If the only requirement is **no two documents share the same email**, a **unique index** on email/canonical email usually protects better than the pattern:

~~~javascript
const existing = db.users.findOne({ email: "an@example.test" })
if (!existing) {
  db.users.insertOne({ email: "an@example.test" })
}
~~~

The check-then-insert pattern has a race condition. A unique index rejects duplicates at write time without needing an open transaction between `findOne` and `insertOne`. The application still needs to handle `E11000`. If **creating a user** must also create a **wallet** and a **billing profile**, and all three must appear together, then that requirement may need a multi-document transaction.

## 3. Practice Dataset

Use the `txn_need_lab` database and separate collections for illustration. The script assumes fixtures do not exist yet; **run only in a demo environment**. Re-running with the same `_id` will hit duplicate key errors — do not drop production collections to recreate fixtures.

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")

lab.accounts.insertMany([
  {
    _id: "A",
    owner: "Lan",
    currency: "VND",
    balance: NumberLong(1000)
  },
  {
    _id: "B",
    owner: "Minh",
    currency: "VND",
    balance: NumberLong(200)
  }
])

lab.inventory.insertMany([
  {
    _id: "SKU-RED",
    available: 5,
    reserved: 0,
    version: 1
  },
  {
    _id: "SKU-BLUE",
    available: 2,
    reserved: 0,
    version: 1
  }
])

lab.orders.insertOne({
  _id: "O-100",
  customerId: "C-1",
  status: "DRAFT",
  items: [
    { sku: "SKU-RED", qty: 3 },
    { sku: "SKU-BLUE", qty: 1 }
  ],
  total: 480,
  version: 1
})

lab.profiles.insertOne({
  _id: "C-1",
  displayName: "Customer A",
  addresses: [
    { label: "home", city: "Hanoi" }
  ]
})

// Pre-create collections/indexes for the transaction demo.
lab.createCollection("transfers")
lab.createCollection("reservations")
lab.createCollection("outbox")

lab.transfers.createIndex(
  { requestId: 1 },
  { unique: true, name: "ux_transfer_request" }
)

lab.reservations.createIndex(
  { orderId: 1, sku: 1 },
  { unique: true, name: "ux_order_sku" }
)
~~~

In real financial systems, monetary amounts must use **integer minor units** or **BSON Decimal128** according to standard currency/precision rules, with auditing and reconciliation. The examples use small integers to clarify transactions and are **not** a production-ready banking/ledger architecture.

### 3.1. Invariants Used in This Lesson

| Business Operation | Invariant | Data Boundary |
|---|---|---|
| Update display name/address | Profile fields are updated together. | One document `profiles.C-1`. |
| Decrement stock of one SKU | `available >= 0`; increase reserved by the same amount available decreases. | One document `inventory.SKU-RED`. |
| Transfer money A → B | Debit A and credit B must both complete. | Two documents in `accounts`. |
| Place an order with two SKUs | Reserve all SKUs or reserve none. | Two inventory documents, plus reservation/order. |
| Create user with wallet | A user cannot exist without a wallet if required by the domain. | Two collections. |
| Update status then send email | MongoDB state must be consistent with the intent to emit an event. | MongoDB + external system; needs outbox/consumer. |

## 4. Cases Where Multi-Document Transactions Are **Not Needed**

### 4.1. One Document and One Conditional Update

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")

const result = lab.inventory.updateOne(
  {
    _id: "SKU-RED",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2
    }
  }
)

printjson(result)
~~~

In the fixture, if the update runs once, SKU-RED changes from `available:5,reserved:0` to `available:3,reserved:2`. If two clients request more than what remains, the `available >= 2` filter is evaluated at update time, preventing negative stock. **A multi-document transaction is not needed** when there is only one stock document and no reservation record must be written in the same atomic business operation.

### 4.2. CAS to Prevent Lost Updates on a Single Document

~~~javascript
const expectedVersion = 1

const result = lab.orders.updateOne(
  { _id: "O-100", version: expectedVersion, status: "DRAFT" },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 }
  }
)

if (result.matchedCount === 0) {
  print("May have already been updated by another request.")
}
~~~

CAS/filtering by `version` detects concurrent modifications, avoiding `findOne` followed by `$set` based on a stale snapshot. Multi-document transactions do not replace proper **state transition** design when modifying only a single order.

### 4.3. Embedding Parts That Share a Lifecycle and Invariant

`profiles.C-1` has a small `addresses` array, usually read together with the user profile. If you only need to update the home address and `updatedAt`, both live in the same document, so one update suffices:

~~~javascript
lab.profiles.updateOne(
  { _id: "C-1", "addresses.label": "home" },
  {
    $set: {
      "addresses.$.city": "Da Nang",
      updatedAt: new Date()
    }
  }
)
~~~

Embedding data **is not always better**: unbounded arrays such as millions of audit events, many-to-many relationships, or high-frequency independently updated data easily create oversized/hot documents. When separate documents are needed, decide on transactions based on the invariant across those documents.

### 4.4. Multiple Documents Without an All-or-Nothing Requirement

~~~javascript
lab.orders.updateMany(
  { migrationVersion: { $ne: 3 } },
  { $set: { migrationVersion: 3 } }
)
~~~

This is not atomic across the entire collection, but if the application supports versions 2 and 3 concurrently, you can run in batches, checkpoint, retry, and reconcile. A transaction covering the entire migration is usually unnecessary.

### 4.5. Using a Unique Constraint Instead of a Transaction to Prevent Duplicates

~~~javascript
lab.orders.createIndex(
  { customerId: 1, externalOrderNo: 1 },
  { unique: true, name: "ux_customer_orderNo" }
)
~~~

If you only need each customer to have at most one order per `externalOrderNo`, a unique compound index enforces the constraint directly on write. A transaction does not replace a unique index; even inside a transaction, two documents violating a unique key are still rejected. However, if each order must also update inventory or a ledger in the same commit, a transaction may be needed for **those operations**.

## 5. Classic Case: Transferring Value Between Two Documents

Suppose the two accounts in the fixture have balances:

~~~text
Account A: 1000
Account B:  200
Total:     1200
~~~

An operation transferring **150** from A to B has the valid end state:

~~~text
Account A:  850
Account B:  350
Total:     1200
~~~

The requirement is **never** to leave a persistent state of `A=850,B=200` or `A=1000,B=350`. Because the two accounts are **two separate MongoDB documents**, a single `updateOne()` cannot modify both within one atomic boundary. This is a clear candidate for a multi-document transaction.

### 5.1. Risks of Running Two Independent Updates

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")

const debit = lab.accounts.updateOne(
  { _id: "A", currency: "VND", balance: { $gte: 150 } },
  { $inc: { balance: -150 } }
)

// Suppose the process crashes abruptly before the credit step.
const credit = lab.accounts.updateOne(
  { _id: "B", currency: "VND" },
  { $inc: { balance: 150 } }
)
~~~

The **debit** may have succeeded. If the **credit** does not run or fails to match B, the ledger state is skewed. Two updates with proper filters still do not provide **all-or-nothing** across two documents.

### 5.2. Why Not Embed All Accounts into One Document?

Technically, you could design a single `bank.accounts[]` document containing all accounts so you can modify them atomically. But that model is impractical:

- Accounts have independent lifecycles, access permissions, and cardinality.
- A single document has a **16 MiB BSON** limit.
- Hundreds of writers competing to update one extremely hot document.
- Difficult to index and query individual accounts efficiently.
- Difficult to partition data by tenant, shard, or retention policy.

Transactions let you keep **each account as its own document** while still protecting value-transfer operations that need a shared commit/abort.

### 5.3. Adding a Transfer Record

Even if updating two balances is correct, it is still hard to **know whether a request has already been processed** after a client timeout. Therefore, a realistic model usually includes `transfers` or ledger records with a stable `requestId`/`transferId`:

~~~javascript
{
  _id: "TX-1001",
  requestId: "TX-1001",
  fromAccountId: "A",
  toAccountId: "B",
  amount: NumberLong(150),
  currency: "VND",
  state: "POSTED",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

The transfer record, debit, and credit must be written **in the same transaction** if everything must be consistent together. A unique index on `requestId` helps detect duplicate requests (afterward, you must verify **whether the original payload matches**).

> **Example Scope:** This is an integer value-transfer simulation. Real payment systems require a ledger, system-wide idempotency, auditing, pending/settlement states, risk controls, currency precision, payment provider integration, and reconciliation. Do not use this balance example alone as a production financial system.

## 6. Transaction Example in `mongosh`

The following script uses a **shell-side `ClientSession`** via `startSession()` and the `withTransaction()` helper. It must be run on a replica set or sharded cluster that supports transactions. The `accounts` and `transfers` collections and the unique index were prepared in Section 3.

### 6.1. Calling `withTransaction` and Checking Business Conditions

~~~javascript
const lab = db.getSiblingDB("txn_need_lab")
const session = db.getMongo().startSession()
const txdb = session.getDatabase("txn_need_lab")

const transferId = "TX-1001"
const amount = NumberLong(150)

try {
  await session.withTransaction(async () => {
    // Transfer state and balances are all inside the transaction.
    txdb.transfers.insertOne({
      _id: transferId,
      requestId: transferId,
      fromAccountId: "A",
      toAccountId: "B",
      amount,
      currency: "VND",
      state: "POSTED",
      createdAt: ISODate("2026-11-14T08:00:00Z")
    })

    const debit = txdb.accounts.updateOne(
      {
        _id: "A",
        currency: "VND",
        balance: { $gte: amount }
      },
      { $inc: { balance: NumberLong(-150) } }
    )

    if (debit.matchedCount !== 1) {
      throw new Error("Account A missing or insufficient funds")
    }

    const credit = txdb.accounts.updateOne(
      { _id: "B", currency: "VND" },
      { $inc: { balance: amount } }
    )

    if (credit.matchedCount !== 1) {
      throw new Error("Account B missing")
    }
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  print("Transaction committed")
} finally {
  session.endSession()
}

lab.accounts.find().sort({ _id: 1 })
lab.transfers.findOne({ _id: transferId })
~~~

Starting from the initial fixtures, if the transaction commits successfully, A has **850**, B has **350**, and transfer TX-1001 is recorded. If either the debit or credit condition fails to match, the callback throws an exception and the helper aborts according to driver/session semantics.

**All write operations inside the callback must use `txdb` obtained from `session.getDatabase(...)`**, not accidentally `lab.accounts` outside the session. A write outside the session **is not covered by the transaction**.

### 6.2. Why Use the Helper Instead of Manually Retrying Every Error?

`withTransaction()` and driver transaction APIs handle eligible retry cases, including **`TransientTransactionError`** and **`UnknownTransactionCommitResult`** as specified. A transaction callback **may be re-executed**, so:

- Do not call a payment gateway, send emails, or publish messages **directly inside the callback**.
- Do not use variables outside the callback to accumulate debit counts without resetting them.
- Do not infinitely retry a business exception such as “insufficient funds”.
- Do not assume every error received by the client means “the transaction did not commit”; the commit outcome may be **unknown**.
- Use a stable **business operation ID** when a request is retried at the API level; do not generate a new ID for the same business action.

If the caller resends TX-1001 as a **new HTTP request** after the previous transaction already committed, inserting the transfer ID will trigger a duplicate key error. The application should **look up the existing transfer and compare amount/from/to/currency**, then return an idempotent result if it is the same business request; do not open a new TX-1002 transaction to debit/credit again.

### 6.3. Reading State After Commit

In the demo:

~~~javascript
const a = lab.accounts.findOne({ _id: "A" })
const b = lab.accounts.findOne({ _id: "B" })
const transfer = lab.transfers.findOne({ _id: "TX-1001" })

printjson({ a, b, transfer })
~~~

If you inspect using multiple independent reads in an environment with concurrent writes, values may continue changing after the commit. When you need a consistent snapshot for a **multi-document report**, you must design appropriate read concern/snapshot semantics, such as a read-only transaction with `readConcern:"snapshot"` when supported and required. A successful write transaction **does not turn every subsequent sequence of find queries** into an immutable snapshot.

### 6.4. Version Constraints and Prepared Metadata

`insertOne` on a brand-new collection without indexes or creating collections mid-transaction has restrictions that vary by server version and topology. The demo creates `transfers` and the unique index **before** the transaction. Production deployments should apply schemas/indexes via migrations rather than creating indexes ad hoc inside every transaction.

### 6.5. A Variant Writing Audit Entries in the Same Transaction

If the business requires adding two ledger entries — DEBIT on A and CREDIT on B — alongside the balance updates, you can add `insertMany` into the ledger **inside the transaction**. However, the ledger must have unique event/transfer keys, valid schema, and validation for each debit/credit entry. MongoDB only guarantees that the requested writes commit together; it does not automatically verify that total debits equal total credits.

## 7. When an Order Needs Multiple SKUs: Transaction or Saga?

Suppose order O-100 requires:

~~~text
SKU-RED: needs 3; available is currently 5.
SKU-BLUE: needs 1; available is currently 2.
~~~

The business rule requires **confirming the order only if both SKUs have sufficient stock**. With concurrent orders, the stock of SKU-RED and SKU-BLUE can change between requests.

### 7.1. Two Conditional Updates Do **Not** Yet Protect the Whole Order

~~~javascript
const red = lab.inventory.updateOne(
  { _id: "SKU-RED", available: { $gte: 3 } },
  { $inc: { available: -3, reserved: 3 } }
)

const blue = lab.inventory.updateOne(
  { _id: "SKU-BLUE", available: { $gte: 1 } },
  { $inc: { available: -1, reserved: 1 } }
)
~~~

Each update protects **one SKU** from going negative. However, if red succeeds and blue is out of stock, red remains reserved. If the business **does not allow a partially reserved state**, a transaction is the direct choice.

### 7.2. Wrapping Inventory Updates and the Order Transition

~~~javascript
const session = db.getMongo().startSession()
const txdb = session.getDatabase("txn_need_lab")

try {
  await session.withTransaction(async () => {
    const red = txdb.inventory.updateOne(
      { _id: "SKU-RED", available: { $gte: 3 } },
      { $inc: { available: -3, reserved: 3 } }
    )
    if (red.matchedCount !== 1) {
      throw new Error("SKU-RED unavailable")
    }

    const blue = txdb.inventory.updateOne(
      { _id: "SKU-BLUE", available: { $gte: 1 } },
      { $inc: { available: -1, reserved: 1 } }
    )
    if (blue.matchedCount !== 1) {
      throw new Error("SKU-BLUE unavailable")
    }

    const order = txdb.orders.updateOne(
      { _id: "O-100", status: "DRAFT" },
      {
        $set: {
          status: "RESERVED",
          reservedAt: ISODate("2026-11-14T09:00:00Z")
        },
        $inc: { version: 1 }
      }
    )
    if (order.matchedCount !== 1) {
      throw new Error("Order already processed or missing")
    }

    txdb.reservations.insertMany([
      { _id: "O-100-RED", orderId: "O-100", sku: "SKU-RED", qty: 3 },
      { _id: "O-100-BLUE", orderId: "O-100", sku: "SKU-BLUE", qty: 1 }
    ])
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })
} finally {
  session.endSession()
}
~~~

If every step succeeds and commits, stock, order, and reservation records take effect together. If SKU-BLUE is insufficient or the order has already been processed, the transaction aborts and the SKU-RED reservation **is not retained** from that transaction.

**Execution note:** The example above assumes an O-100 request running against the initial fixture. Do not run it right after the standalone reservation example in Section 4; the state will differ. In real systems, use a stable `orderId`/`eventId` and a unique `(orderId,sku)` index to detect replays; reconcile if already processed rather than simply retrying with new quantities.

### 7.3. Why Both a Status Filter and a Unique Reservation Key Are Needed

If two requests process O-100 concurrently:

- The `status:"DRAFT"` filter prevents transitioning again from `RESERVED`.
- The unique reservation key `(orderId,sku)` prevents duplicate line reservations.
- Conditional stock updates prevent reserving beyond `available`.
- The transaction binds those changes **to commit/abort together**.

Four layers of control address **four different risks**. Having a transaction does not mean you can omit unique keys and business filters. If the order is modified by another request, the transaction may hit a write conflict or match 0; the application must classify the outcome properly.

### 7.4. When a Saga Makes More Sense

Not every system needs an immediate simultaneous commit when reserving each SKU. A marketplace might allow:

~~~text
Order -> PENDING_RESERVATION
    |
    +--> Reserve RED with reservationId
    |
    +--> Reserve BLUE with reservationId
              |
         +----+----+
         |         |
      All ok    Missing/error
         |         |
         v         v
   CONFIRMED     Release RED
                 (compensation)
                 Order FAILED
~~~

This is a **saga / reservation workflow**: it has intermediate states, **timeouts**, **expiry**, **idempotent release**, a **repair worker**, and monitoring. It accepts eventual consistency while scaling better across distributed or independently owned systems, provided the business allows temporary partial holds.

If “never see an order holding a partial subset of SKUs” is a hard requirement inside MongoDB, a short transaction remains more appropriate. If the business allows a `PENDING` state with compensation, a long transaction spanning multiple services is unnecessary.

## 8. Creating Two Documents in Two Collections: User and Wallet

Another case: user registration strictly requires both:

~~~javascript
// users:
{
  _id: "U-100",
  emailCanonical: "an@example.test",
  status: "ACTIVE"
}

// wallets:
{
  _id: "W-U-100",
  userId: "U-100",
  available: NumberLong(0),
  currency: "VND"
}
~~~

If the domain requires that **an `ACTIVE` user must never exist without a wallet**, then the two inserts must commit/abort together or be structured with an appropriate lifecycle.

### 8.1. A Transaction Is a Direct Option

~~~javascript
const session = db.getMongo().startSession()
const txdb = session.getDatabase("txn_need_lab")

try {
  await session.withTransaction(async () => {
    txdb.users.insertOne({
      _id: "U-100",
      emailCanonical: "an@example.test",
      status: "ACTIVE"
    })

    txdb.wallets.insertOne({
      _id: "W-U-100",
      userId: "U-100",
      available: NumberLong(0),
      currency: "VND"
    })
  }, {
    writeConcern: { w: "majority" }
  })
} finally {
  session.endSession()
}
~~~

**Pre-create** the `users`/`wallets` collections and unique indexes on email and `userId` as required in production; certain metadata operations inside transactions are restricted depending on topology/version. After commit, both documents exist together. If the example runs on a database that does not yet have `users`/`wallets`, collection creation inside a transaction depends on version and sharding; create them outside the transaction for this exercise.

### 8.2. Avoiding a Transaction via Lifecycle States

If the domain **allows a user to temporarily exist in a `PENDING` state**:

~~~text
Create user: status = PENDING_WALLET
       |
       v
Create wallet idempotently
       |
       v
Set user status = ACTIVE
~~~

This flow can use independent writes with retry/reconciliation after failure. Essential condition: other components **must not treat `PENDING` as `ACTIVE`**, and a repair worker must resolve stuck users. Thus, the business requirement is not “both documents exist immediately”, but “a user may only become `ACTIVE` once the wallet is ready”. **Redefining valid states** can eliminate the need for a transaction across the entire flow.

### 8.3. Why Unique Indexes Alone Are Not Enough

A unique index on `users.emailCanonical` prevents two users with the same email. A unique index on `wallets.userId` prevents two wallets for the same `userId`. However, **two separate unique indexes** do not guarantee “if a user is inserted, a wallet must also be inserted”. That is a **cross-document/cross-collection existence constraint**, requiring either a transaction or a workflow with a permitted intermediate state.

## 9. Transactions for Consistent Snapshot Reads: When Are They Truly Needed?

So far, the examples have been **write transactions**. However, some use cases read multiple documents and require values corresponding to **the same point-in-time snapshot**: balance auditing, generating period-close reports, or making decisions based on multiple related records.

### 9.1. Two Independent Reads Can Observe Two Different Points in Time

~~~text
T0: A=1000, B=200

Reader: read A -> 1000
Writer: transfers 150 from A to B in a transaction, commits
Reader: read B -> 350

Reader computes A+B = 1350, even though the sum was 1200 before and after the transfer.
~~~

This is not a writer transaction atomicity bug; the reader read from **two different point-in-time snapshots**. If you need the sum from **the same logical point in time**, you must use appropriate **read concern/snapshot semantics**, potentially a read-only transaction with `readConcern:"snapshot"` when supported and needed.

### 9.2. Read-Only Snapshots Are Not Always Necessary

If a dashboard tolerates metrics that are delayed or out of sync by a few seconds, a snapshot read transaction may be unnecessary. Only when a report for compliance, accounting close, or reconciliation requires **multi-document consistency** should you design the read path with snapshot/transaction semantics or versioned closing snapshots.

Do not keep a read-only transaction open for several minutes while a user scrolls through a screen. It can pin a snapshot, increase pressure on storage history, and impose overhead on the cluster.

### 9.3. Snapshots Do Not Automatically Make Every Invariant Serializable

**Snapshot isolation does not equal serializable isolation for all cross-document invariants.** A classic example is **write skew**:

~~~text
Two doctors A/B on call:
  doctors.A.onCall = true
  doctors.B.onCall = true

Rule: at least one doctor must always be on call.

Transaction T1 reads snapshot: A=true, B=true
Transaction T2 reads snapshot: A=true, B=true

T1 updates only A.onCall = false
T2 updates only B.onCall = false

The two transactions write DIFFERENT documents.
After both commit, there is a risk of A=false, B=false.
~~~

Because the two transactions update **different documents**, write conflict mechanisms triggered when modifying the same document do not necessarily protect the “at least one doctor on call” invariant. This is a class of bug you must watch for even when using transactions.

**Design approach:** place the invariant in **a shared guard document** (for example `onCallCount`, where each transaction performs a conditional decrement only while the count remains sufficient), or store the shared state in a small aggregate that can be updated atomically. When both transactions must write the **guard document**, write conflict/CAS serializes contention on the shared condition. Never just “read both and update your own document”.

### 9.4. Stale Reads Inside a Transaction

A transaction using a read snapshot can read state that is stale relative to external writers. If an operation must guarantee that a document has not changed between the start of the transaction and the update, **perform a conditional write / `findOneAndUpdate`** with a state-guarding filter, or restructure the invariant. A strong read concern does not automatically replace filters/versions on contended business variables.

## 10. Concurrency and Write Conflicts in Transactions

MongoDB allows many operations to run concurrently, but when a transaction modifies a document that another writer also modifies, the transaction can **abort with a write conflict**.

### 10.1. Write Conflict Diagram

~~~text
Transaction T1 starts:
  read stock SKU-RED
        |
        +----------- Writer T2 updates SKU-RED, commits
        |
  T1 tries to update SKU-RED based on old snapshot
        |
        v
  May hit write conflict / transaction abort
        |
        v
  Application retries the entire transaction when appropriate
~~~

This is one reason to use the driver's **convenient transaction APIs** and handle error labels properly. However, retrying the whole transaction does not mean you can skip stock/amount checks; conditions must be re-evaluated in the new execution attempt.

### 10.2. Retries Must Classify Errors

| Scenario | Handling Approach |
|---|---|
| `TransientTransactionError` | Driver can usually retry **the entire transaction** (within driver limits/guidelines). |
| `UnknownTransactionCommitResult` | **Retry commit**/reconcile outcome; do not blindly re-run the business operation with a new ID. |
| Insufficient stock/funds (`matchedCount:0`) | This is a **business rejection**; do not retry indefinitely when quantity is insufficient. |
| `E11000 DuplicateKey` | Inspect the conflicting unique key and idempotency; do not treat every duplicate as success. |
| Transaction too large / timeout | Reduce scope, workload, and duration; retrying the same huge transaction may not help. |
| Network/server unavailable | Assess whether commit could have occurred; use session API and operation ID to reconcile. |

An application retrying **a new HTTP request** can still create a new transaction. Even though the driver retries technical writes, that **does not guarantee business-request once-only execution** if a new `requestId` is generated each time.

### 10.3. Use the Same Session, Avoid Parallel Operations

While a transaction is active, every MongoDB write/read belonging to the transaction must use the **same session**. Especially in Java/Node drivers, running multiple operations **in parallel** within one transaction on the same session is not allowed by default. Execute operations sequentially as supported by the API; do not use a thread pool or `Promise.all` on the same session as a way to “speed up the transaction” when the driver warns against it.

### 10.4. Distinguishing Write Conflict Errors from Lost Updates

- **Lost updates** can happen with two standalone `$set` operations on the same document when the app computes new state from a stale snapshot and filters only by `_id`. Each update is atomic, yet overwrites go undetected.
- **Write conflicts in transactions** cause one transaction to abort/retry, protecting storage-level consistency on contended documents.
- **Business invariants** still require `$inc`, CAS/version, unique keys, or a shared guard depending on the requirement; transactions do not automatically know which updates are valid.

## 11. Read Concern and Write Concern Are Not Transactions

A common question: “If I already use `writeConcern:{w:'majority'}`, do I still need a transaction?” Answer: **these are two different concerns**.

### 11.1. Write Concern

Write concern specifies the level of write acknowledgment. For example:

~~~javascript
lab.accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: NumberLong(-10) } },
  { writeConcern: { w: "majority" } }
)
~~~

`w:"majority"` requests acknowledgment from a calculated majority of eligible voting data-bearing members of the replica set. It **does not turn** independent updates on A and B into a single transaction.

### 11.2. Read Concern

Read concern controls the consistency/recency guarantees of reads; levels such as `local`, `majority`, and `snapshot` have different semantics. **`snapshot`** inside a transaction gives reads within the transaction a consistent snapshot per server rules, subject to deployment/commit conditions.

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})
~~~

These are transaction options, not “by default every `find` across the entire cluster now reads from the same snapshot”.

### 11.3. Transactions and Write Durability

A transaction guarantees atomic commit/abort within its MongoDB boundary, but durability guarantees across failovers depend on write concern/commit conditions. A transaction committed with `w:1` can have different durability characteristics than one committed with `w:"majority"`. Choose concerns based on data criticality and SLOs, without assuming every commit response implies maximum durability.

### 11.4. Unknown Commit Result

On an imperfect network:

~~~text
Client -> commitTransaction
MongoDB -> commit succeeds
Network drops before response reaches client
Client -> does not know whether commit finished
~~~

**Do not** treat every error from commit as proof that the transaction aborted. With `UnknownTransactionCommitResult`, per driver guidelines, continue verifying/retrying **commit** or reconciling using a stable `requestId`. Wrapping a business request in a transaction does not solve the problem of **clients resending an HTTP request after a timeout**.

## 12. Idempotency: Transactions Do Not Automatically Prevent Replayed Business Requests

Suppose a transaction transferring 150 from A to B commits, but the HTTP client times out and resends the same request. If the backend generates a **new `transferId`** and runs another transaction, the database will commit **a second transfer** that is completely valid in atomicity, yet wrong for the business.

### 12.1. A Stable Operation ID

The client provides (or the backend derives from a stored request) `requestId = "TX-1001"`, bound to the payload:

~~~javascript
{
  requestId: "TX-1001",
  from: "A",
  to: "B",
  amount: 150,
  currency: "VND"
}
~~~

A record in `transfers` has a unique index `{requestId:1}`. When the transfer transaction commits, this record commits alongside the debit and credit.

If the request is repeated:

1. Look up the transfer by `requestId`.
2. Compare the **stored payload** with the new request.
3. If it is the same request and already `POSTED`, return an idempotent success.
4. If it is the same ID with a different payload, return **conflict**; do not mutate the record to fit the new request.
5. If the record does not exist or the outcome is unknown, apply the transaction/reconciliation and appropriate retries.

**Do not rely solely on balances** to detect whether a request already ran: multiple other valid transactions can make a balance match an expected value.

### 12.2. Unique Keys and Transactions Must Serve the Same Boundary

~~~javascript
// Inside the same transaction:
txdb.transfers.insertOne({
  _id: "TX-1001",
  requestId: "TX-1001",
  amount: NumberLong(150),
  state: "POSTED"
})

txdb.accounts.updateOne(
  { _id: "A", balance: { $gte: NumberLong(150) } },
  { $inc: { balance: NumberLong(-150) } }
)

txdb.accounts.updateOne(
  { _id: "B" },
  { $inc: { balance: NumberLong(150) } }
)
~~~

This snippet only **illustrates the placement of writes inside the callback**, not a complete transaction: real implementations must check `matchedCount`, scope/currency, use the session, and abort if conditions fail. A unique `transferId` is effective when written **in the same transaction** as the effects being deduplicated.

### 12.3. Retryable Writes vs. Business Idempotency

Certain write operations are automatically retried by MongoDB drivers on technical errors via **retryable writes** using session/statement tracking. However, that does not guarantee an entire **HTTP request** executes once if the caller sends a **new request**. An `$inc` executed twice across two different business requests still modifies the balance twice.

Similarly, `withTransaction()` retries **a single invocation** based on error labels; it does not remember idempotency across **a different invocation** after a client timeout.

### 12.4. Deduplication Requires Appropriate Retention Bounds

A service can store idempotency records for an appropriate retention window. However, purging records too early or changing `requestId` on retries breaks deduplication. Define retention, key scope (global vs. per-tenant/account), uniqueness, and handling for **same `requestId` with a different payload**.

## 13. Transactions Do Not Span Systems Outside MongoDB

A newly placed order might need to:

~~~text
1. Reserve inventory in MongoDB
2. Change order status to CONFIRMED
3. Call payment gateway
4. Send email
5. Publish message to shipping
~~~

A MongoDB transaction only manages changes **within the MongoDB transaction/session**; it cannot commit or abort calls to a payment provider, SMTP server, or message broker.

### 13.1. Wrong: Charging Payment Inside the Transaction Callback

~~~text
START TRANSACTION
  Update order
  Call payment gateway -> CHARGE SUCCESS
  Insert reservation -> FAIL
ABORT TRANSACTION

MongoDB order/reservation roll back
Payment gateway was STILL CHARGED!
~~~

If the driver automatically retries the transaction callback, the gateway call could **be executed a second time**. Never put non-idempotent external side effects inside a transaction callback.

### 13.2. Transactional Outbox to Sync MongoDB State with Event Intent

One option:

~~~text
MongoDB transaction:
  Update order -> CONFIRMED
  Insert reservation records
  Insert outbox event:
      {eventId:"EV-ORDER-100",type:"ORDER_CONFIRMED",orderId:"O-100"}
COMMIT
       |
       v
Outbox dispatcher reads unpublished events
       |
       +--> Publish message / send email
       |
       +--> Mark dispatched status or save checkpoint
~~~

The order, reservations, and outbox can commit together. However, the dispatcher may publish successfully and crash **before marking it dispatched**, publishing again upon restart. Hence **outbox typically provides at-least-once delivery**, requiring **an idempotent consumer keyed by `eventId`**.

### 13.3. Saga/Compensation Across Multiple Systems

If each step is owned by a separate service:

~~~text
Reserve inventory
       |
       v
Charge payment
       |
       v
Book shipment

If payment fails -> Release inventory
If shipment fails -> Refund or compensate according to policy
~~~

This is a **saga**: steps do not share one atomic transaction; instead, each step has durable state, a **compensating action**, retry/idempotency, and reconciliation. Compensation **is not an instant physical rollback**; it can also fail, so you need `PENDING`/`COMPENSATING`/`FAILED` states and operational alerting.

### 13.4. Where to Use Transactions Within a Saga?

Even when the overall workflow uses a saga, **each service** can use **a small transaction** for its own state and outbox. For example, the Inventory service updates stock and reservations in a single transaction, then writes an outbox record to notify the next step. Never hold a MongoDB transaction open while waiting for a payment gateway, because the gateway does not participate in that commit protocol.

## 14. Choosing a Data Model Before Adding Transactions

Multi-document transactions are very useful, but MongoDB favors **designing documents so that data frequently updated together resides in a reasonable aggregate**. Transactions should not replace data modeling decisions.

### 14.1. When Embedding Makes Sense

For example, fields belonging to the same order:

~~~javascript
{
  _id: "O-200",
  status: "DRAFT",
  shippingAddressSnapshot: {
    city: "Hanoi",
    postalCode: "100000"
  },
  totals: {
    subtotal: 300,
    fee: 15,
    grandTotal: 315
  },
  lines: [
    { lineId: "L1", sku: "SKU-RED", qty: 2 },
    { lineId: "L2", sku: "SKU-BLUE", qty: 1 }
  ]
}
~~~

If you need to transition `status` and record `confirmedAt`, everything is in one order document. If you must simultaneously update quantities in the **inventory collection**, that involves multiple documents and requires evaluating the invariant. Never claim “embedding lines into the order makes everything in checkout atomic”, because inventory and payment records remain separate.

### 14.2. When Referencing Is Better

Referencing is appropriate when:

- **Unbounded one-to-many** relationships: audit logs, comments, ledger entries.
- Documents have **independent lifecycles**, different access controls, or different retention policies.
- Independent indexing/pagination is required on child records.
- Many independent writers would turn an embedded document into a **hot document**.
- Individual records could hit the **16 MiB** limit if everything were embedded.

When splitting data, do not assume every write requires a transaction. Classify each invariant: **immediate consistency required** or **eventual consistency acceptable**.

### 14.3. Materialized Summaries Can Be Eventual

For example, `orders` is the source of truth, while `dailyRevenue` is a read table aggregated periodically. If the report tolerates a 5-second delay and is not used to deduct funds, there is no need for every order insert to update `dailyRevenue` inside a transaction. A change stream, outbox, or aggregation job can update the summary with checkpoints.

If a summary is used for **credit limit decisions** or immediate settlement, choose an appropriate consistent design (transaction, shared counter, ledger, versioned snapshot) rather than assuming an eventual summary is always up to date.

### 14.4. Do Not Embed an Unbounded Ledger Just to Avoid Transactions

~~~javascript
{
  _id: "ACC-A",
  balance: 1000,
  ledgerEntries: [
    // Millions of records over many years.
  ]
}
~~~

This design carries size, performance, and contention risks. If ledger entries need long-term retention, modeling **each entry as a separate document** is usually better. When balance and ledger entry must commit together, a **short transaction** is one solution; if the ledger is the source of truth, the balance can be a versioned derived projection with policy-driven reconciliation.

### 14.5. Sharing a Lifecycle Does Not Mean Data Must Be Co-Updated

A customer profile and multiple orders are often displayed on the same page, but that does not mean they must share a transaction when the user changes their name. Orders can hold a **historical snapshot of the name/address at the time the order was placed**. Keeping a snapshot is often more accurate for the business than trying to rewrite every historical order in a transaction just to sync a new name.

## 15. Limits and Costs of Multi-Document Transactions

A transaction simplifies all-or-nothing reasoning, but it is not free. MongoDB must manage sessions, snapshots, transaction state, uncommitted writes, concurrency conflicts, the commit protocol, and associated resource limits.

### 15.1. Transactions Should Be Short with a Clear Scope

A reasonable transaction:

~~~text
Start transaction
  Insert transferId
  Conditional debit
  Conditional credit
Commit
~~~

A risky transaction:

~~~text
Start transaction
  Scan 10 million documents
  Call remote payment gateway
  Wait for user confirmation
  Update thousands of documents
  Sleep for a long retry delay
Commit
~~~

Never keep a transaction open waiting on user input, external network calls, or long-running batch migrations. Break work into **small business units** with idempotency/checkpoints if the overall job lacks an all-or-nothing invariant.

### 15.2. Limits to Check in Production

| Topic | Notes |
|---|---|
| **Transaction lifetime** | MongoDB has `transactionLifetimeLimitSeconds`, commonly defaulting to **60 seconds**; configurable. Overly long transactions can be aborted. |
| **WiredTiger cache** | Snapshots/history and transaction writes can create memory pressure; overly large transactions can hit `TransactionTooLargeForCache`. |
| **Write conflicts** | Transactions can abort under write contention, requiring bounded retries. |
| **Lock acquisition** | Transactions can hit lock timeouts if locks cannot be acquired in time, depending on configuration/server. |
| **Sharded transactions** | Incur multi-shard coordination/commit overhead and specific constraints. |
| **DDL/metadata** | Creating collections/indexes, renaming/dropping, and concurrent DDL have version/topology-dependent restrictions. |
| **Read/write concern** | Configured at the transaction level via the API; cannot be arbitrarily overridden per write. |
| **Parallel session use** | Do not execute operations in parallel on the same session if the driver does not support it. |
| **External services** | SMTP, payments, and message brokers are not part of MongoDB transactions. |
| **Large number of writes** | Do not treat a transaction as a commit mechanism for every record in an unbounded job. |

Specific limits can change across MongoDB release lines. Check the **MongoDB Database Manual for your exact server version** and benchmark representative workloads instead of treating a fixed number as a guarantee for all deployments.

### 15.3. Scope Transactions to Business Boundaries

Suppose a job needs to generate 20,000 invoices. If each invoice is independent and an invoice plus its `invoiceLines` must commit together, design **one transaction per invoice** or per small controlled business group; do not default to a single transaction for all 20,000 invoices. That way, an error on invoice 500 does not force rolling back 499 completed invoices when the domain allows incremental progress.

### 15.4. Index Before Adding Transactions

A transfer needs to locate accounts by `_id` and reservations by `(orderId,sku)`. Creating proper indexes helps:

- Reduce read/update time and how long the transaction holds resources.
- Reduce the number of records inspected and unnecessary contention.
- Enforce uniqueness of request/line records.

Transactions do not make poor query filters or missing indexes fast. Never wrap a full-collection-scanning `updateMany` in a transaction without understanding its execution plan and document count.

### 15.5. Metrics to Monitor

| Metric | Signal to Investigate |
|---|---|
| P95/P99 transaction duration | Are transactions holding snapshots too long or slowing down commits? |
| Abort/write conflict rate | Hot documents, overly broad transaction scope, or high contention. |
| Transaction retries | Rapidly climbing retries can trigger a retry storm. |
| WiredTiger cache usage/history pressure | Too many long-running snapshots or cache exhaustion. |
| Lock waits/timeouts | Contention from DDL, metadata, or hot documents. |
| Replication lag/majority commit latency | Write acknowledgment requirements/cluster health impacting latency. |
| Number of participating shards | Are there unnecessary scatter-gather or cross-shard transactions? |
| Idempotency conflicts | High duplicate requests, unstable keys, or payload mismatches. |
| Outbox lag | External workflows lagging even when local transactions commit cleanly. |

### 15.6. Transactions in Sharded Clusters

MongoDB supports distributed transactions across sharded clusters in supported versions. However, multi-shard transactions incur additional coordination/commit overhead and failure modes; sometimes a **data model that keeps related records on a single shard** reduces cost. Even so, placement does not turn two documents into **one**: if two documents on the same shard require all-or-nothing semantics, you still need a transaction unless you redesign the aggregate boundary.

**Do not confuse "same shard" with "same document".**

### 15.7. When One Transaction Is Not Enough Because an Invariant Spans Independent Systems

A MongoDB transaction only manages data coordinated within its supported cluster. If a business invariant spans an **external SQL database**, a payment gateway, or Kafka, you need a dedicated **distributed workflow**/outbox/saga/2PC architecture where appropriate — you cannot simply wrap everything in a MongoDB transaction.

## 16. Java Sync Driver: Safe Transactions per Business Unit

The Java Sync Driver supports multi-document transactions via `ClientSession`. With the `withTransaction()` convenience API, the driver handles many retry/commit cases based on error labels. Below is a standalone **transfer** example; it assumes the collections and unique indexes from Section 3 already exist and `MongoClient` is connected to a transaction-capable replica set/sharded cluster.

### 16.1. One-Document Conditional Update in Java (Baseline Comparison)

Before opening a transaction, check whether a single update suffices:

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

// database is the MongoDatabase for "txn_need_lab".
MongoCollection<Document> inventory = database.getCollection("inventory");
int quantity = 2;

UpdateResult result = inventory.updateOne(
    and(
        eq("_id", "SKU-RED"),
        gte("available", quantity)
    ),
    combine(
        inc("available", -quantity),
        inc("reserved", quantity)
    )
);

if (result.getMatchedCount() == 1) {
    System.out.println("Reserved");
} else {
    System.out.println("Stock insufficient or SKU missing");
}
~~~

One SKU in a single document with no requirement to write a reservation document at the same time ⇒ **no multi-document transaction needed**. However, if the request is replayed at the API layer, `$inc` could run again; you still need a stable request ID/ledger or appropriate conditional business state transition.

### 16.2. Transaction Using `ClientSession.withTransaction()`

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.inc;

// client: MongoClient connected to a deployment supporting transactions.
MongoDatabase database = client.getDatabase("txn_need_lab");
MongoCollection<Document> accounts = database.getCollection("accounts");
MongoCollection<Document> transfers = database.getCollection("transfers");

TransactionOptions options = TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

String requestId = "TX-JAVA-2001";
long amount = 150L;

try (ClientSession session = client.startSession()) {
    String committedId = session.withTransaction(() -> {
        transfers.insertOne(
            session,
            new Document("_id", requestId)
                .append("requestId", requestId)
                .append("fromAccountId", "A")
                .append("toAccountId", "B")
                .append("amount", amount)
                .append("currency", "VND")
                .append("state", "POSTED")
        );

        UpdateResult debit = accounts.updateOne(
            session,
            and(
                eq("_id", "A"),
                eq("currency", "VND"),
                gte("balance", amount)
            ),
            inc("balance", -amount)
        );
        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Source account missing or insufficient funds"
            );
        }

        UpdateResult credit = accounts.updateOne(
            session,
            and(eq("_id", "B"), eq("currency", "VND")),
            inc("balance", amount)
        );
        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                "Destination account missing"
            );
        }

        return requestId;
    }, options);

    System.out.println("Transfer committed: " + committedId);
}
~~~

In this pattern:

- **Every write** receives the `session` parameter. Omitting `session` on one call executes that write outside the transaction.
- Writing `requestId` alongside debit/credit allows those changes to **commit or abort together**.
- The `balance >= amount` filter still enforces the business condition at update time; transactions do not automatically prevent negative balances.
- The callback can be invoked again under driver retry semantics. It contains no emails, payment gateways, or side effects outside MongoDB.
- The unique index on `requestId` must be created beforehand. On duplicate requests, the service must reconcile against the existing record and payload rather than infinitely retrying as a transient error.
- If the source or destination is concurrently modified by another transaction, a write conflict can occur; the driver retries under supported conditions.

**Do not run this Java example right after the TX-1001 example and expect the initial 1000/200 balances.** The fixture may have changed. This example only demonstrates structure; run it independently on an appropriately reset lab collection.

### 16.3. What Should the Transaction Return to the API?

An API should not return an unclassified “success/fail”. Possible cases:

| Outcome | Recommended API Handling |
|---|---|
| Committed successfully, new `requestId` | Succeed and return the transfer ID. |
| `requestId` already exists with **matching** payload and state `POSTED` | Return idempotent success without debiting again. |
| `requestId` already exists with a different payload | Report conflict; likely a client bug or ID reuse. |
| Insufficient funds | Return business rejection; do not blindly retry. |
| Transient database error | Bounded retry per API/driver rules. |
| Commit result unknown | Handle via transaction API and reconcile before creating a new business operation. |
| Validation/authorization error | Do not execute transfer; log/respond per policy. |

### 16.4. Why Should Callbacks Avoid External Operations?

~~~java
session.withTransaction(() -> {
    // BAD IDEA:
    // paymentGateway.charge(...); // May re-execute when the callback retries.
    ...
}, options);
~~~

Do not send emails, charge cards, or publish non-idempotent events directly inside the callback. Instead, insert an **outbox record inside the MongoDB transaction**, and let a dispatcher process it after commit. If a gateway must be called in the workflow, use the gateway's idempotency key and an orchestration/saga with explicit state.

### 16.5. Java Driver and Transaction Retries

The driver's helper API handles certain retry cases, but **business logic must still be bounded and deterministic**. Additionally, some errors (validation, duplicate key, transaction too large) are not transient. If the application wraps an outer retry loop around the helper, avoid retry storms, duplicate side effects, and especially never change `requestId` across attempts of the same business operation.

## 17. Spring Data MongoDB: When to Use `@Transactional`?

In Spring Data MongoDB applications, an appropriate transaction manager can manage MongoDB transactions and propagation as configured. Example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {

    private final AccountRepository accounts;
    private final TransferRepository transfers;

    public TransferService(
        AccountRepository accounts,
        TransferRepository transfers
    ) {
        this.accounts = accounts;
        this.transfers = transfers;
    }

    @Transactional
    public void transfer(String requestId, String fromId,
                         String toId, long amount) {
        // Illustrates service boundary; repository methods
        // must use the properly configured MongoDB session/transaction.
        // Production code needs atomic conditional debit, credit,
        // unique requestId, modified count checks, and error handling.
        transfers.record(requestId, fromId, toId, amount);
        accounts.debitIfEnough(fromId, amount);
        accounts.credit(toId, amount);
    }
}
~~~

This is **service-layer pseudocode**, not compile-ready code, since the repository methods `record`/`debitIfEnough`/`credit` are hypothetical APIs. It expresses the transaction boundary; when implementing, you must:

- Configure **MongoTransactionManager** and transaction support matching your MongoDB deployment.
- Ensure repository/database calls participate in the **same session**.
- Verify debit/credit success; an update method matching zero documents **does not throw an exception** unless your code explicitly checks it.
- Understand **Spring AOP proxies and self-invocation**: a direct call from another method in the same class can bypass the transaction interceptor.
- Understand rollback semantics by exception type. Do not assume checked exceptions roll back unless configured.
- Do not treat the annotation as an idempotency/retry mechanism.

If a service only updates a single embedded order document, wrapping a single update in `@Transactional` adds unnecessary complexity. Choose transactions based on invariants, not out of habit on every service method.

## 18. Decision Table: When Is It Needed, When Is It Not?

Instead of following a rule like “multiple documents always need a transaction”, evaluate **immediacy**, **tolerance for partial commits**, **number of systems involved**, and **data model** together.

| Scenario | Multiple Documents Change? | Partial State Acceptable? | Usually Appropriate Choice |
|---|---|---|---|
| Decrement stock and increment reserved **in the same SKU document** | No | No partial state between the two fields | **One conditional `updateOne`** with `$inc`. |
| Update status and timestamp in one order | No | No | **One atomic update** filtering by status/version. |
| Edit an embedded address in a user profile | No | No | **One update**; no multi-doc transaction needed. |
| Transfer money between account A and B | Yes | **No** | **Multi-document transaction** + stable transfer ID. |
| Transfer money while writing a transfer/ledger record | Yes | **No** | Transaction covering balances and ledger/transfer records. |
| Reserve two SKUs; order is valid only if both have enough stock immediately | Yes | **No** | Short transaction with conditional updates per SKU. |
| Reserve SKUs step-by-step, allowing `PENDING` and release on failure | Yes | **Yes**, inside a controlled workflow | **Reservation saga/compensation**, idempotency. |
| Create user and wallet: cannot have an `ACTIVE` user without a wallet | Yes | No if immediately `ACTIVE` | Transaction or **`PENDING` lifecycle** if allowed by the domain. |
| Import tens of thousands of independent products | Yes | Yes | `insertMany`/`bulkWrite` in batches, with checkpoints. |
| Upgrade `schemaVersion` across many documents | Yes | Usually yes | Idempotent migration; no massive transaction needed. |
| Write a non-critical analytics event per order | Yes | Yes | Eventual consistency/outbox depending on guarantees required. |
| Mark order `PAID` and send email | MongoDB + external system | MongoDB cannot commit email simultaneously | Local transaction + **outbox**; idempotent consumer. |
| Update account profile and all historical order snapshots | Yes | Usually should not alter old orders | Design **snapshot semantics**, not bulk transactions. |
| Dashboard reading multi-collection stats with acceptable lag | Multiple read documents | Yes | Eventual aggregation/read model, not necessarily a snapshot transaction. |
| Period-close report needing a multi-document point-in-time snapshot | Multiple read documents | **Read skew unacceptable** | Snapshot read semantics/transaction or versioned snapshot. |
| Enforce unique username | Two inserts may race | No duplicates | **Unique index**; no transaction needed just for uniqueness. |
| Count audit events per day | Yes | Yes | Asynchronous materialization/aggregation. |
| Enforce “at least one doctor on call” across two documents | Yes | No | **Shared guard/CAS** or single-doc model; snapshot transaction alone is insufficient. |

### 18.1. Condensed Decision Tree

~~~text
1. Which invariant must be protected?
  |
  +-- Fits inside a single document?
  |      |
  |      +-- Yes -> Conditional update + CAS/version/unique constraint.
  |
  +-- Spans multiple documents?
         |
         +-- Does the business accept partial progress or a PENDING state?
         |      |
         |      +-- Yes -> Saga/outbox/batches/reconciliation.
         |
         +-- Cannot accept partial commit?
                |
                +-- All writes belong to a supported MongoDB deployment?
                |      |
                |      +-- Yes -> Short multi-document transaction,
                |                 predicate checks, and idempotency.
                |
                +-- Involves external systems?
                       |
                       +-- MongoDB transactions do not cover them.
                           Design outbox/saga/compensation.
~~~

### 18.2. Four Questions to Answer Before Enabling a Transaction

1. **If the process stops after the first write, can the data be repaired later through a valid workflow?** If yes, eventual consistency may suffice.
2. **With concurrent clients, which invariant can still break even if each update is atomic?** This is where CAS, unique constraints, transactions, or shared guards are needed.
3. **Should a resent request execute again?** Design an idempotency ID and reconciliation.
4. **Are there factors outside MongoDB?** If so, a MongoDB transaction does not solve the entire problem.

## 19. Common Pitfalls When Deciding to Use Transactions

| Misconception | Correct Explanation |
|---|---|
| “MongoDB doesn't have ACID transactions.” | It supports multi-document transactions on supported deployments. |
| “Since transactions exist, everything should go inside one.” | Transactions need a **small scope per invariant** to avoid holding resources for long. |
| “Each `updateOne` is atomic, so two `updateOne` calls are atomic together.” | Two independent updates can succeed partially. |
| “`bulkWrite({ordered:true})` is equivalent to a transaction.” | Ordered controls execution order and stopping on error; it does not roll back already-executed operations. |
| “`updateMany` is atomic across all documents.” | Each document is updated atomically on its own; the overall operation is not all-or-nothing. |
| “To guarantee email uniqueness, open a transaction with find+insert.” | A unique index prevents races directly; finding beforehand is insufficient. |
| “Embedding all documents into one document is always best.” | Risks hitting 16 MiB, hot documents, and mixing entities with different lifecycles. |
| “Every referenced relationship needs a transaction.” | Only when an invariant requires **co-commit**; many relationships allow eventual consistency. |
| “Multi-document transactions solve all lost updates.” | You still need CAS/`$inc`/write conditions and write-conflict handling. |
| “Snapshot transactions automatically guarantee serializability for every invariant.” | Snapshot isolation can still suffer from **write skew** across different written documents. |
| “`writeConcern:majority` makes two independent commands commit together.” | Write concern only controls acknowledgment/durability. |
| “Commit timeout means the transaction aborted.” | The outcome may be unknown; handle `UnknownTransactionCommitResult`. |
| “Because the driver retries transactions, idempotency isn't needed.” | A **new HTTP/business request** can still re-run the operation. |
| “`$inc` is always safe to retry.” | Technical retryable writes differ from business replay; `$inc` is not idempotent if executed twice. |
| “With a unique `transferId`, every duplicate request is definitely a success.” | You must verify the existing record has the **same payload** and expected status. |
| “A MongoDB write outside the transaction will also roll back.” | Only writes attached to the correct session/transaction are covered. |
| “Wrapping an external payment gateway call in a transaction rolls back the charge.” | MongoDB does not control the gateway; use saga/compensation/idempotency. |
| “Outbox guarantees messages are delivered exactly once.” | Typically **at-least-once**; consumers must deduplicate. |
| “Long transactions are fine because default lifetime is unlimited.” | Lifetime limits, cache, and lock constraints apply; check server configuration. |
| “Transactions on the same shard are unnecessary.” | Two documents are still two atomic boundaries without a transaction. |
| “If you use write transactions, you don't need transactions on the read path.” | Multiple independent reads can observe different points in time. |
| “If a transaction callback throws an exception, every exception is retryable.” | Business errors and resource errors must be classified, not blindly retried. |
| “Just adding `@Transactional` puts every MongoDB repository on the same session.” | Transaction manager/proxy and session wiring must be configured properly; self-invocation can bypass proxies. |

### 19.1. Signs That Transactions Are Being Overused

- A transaction runs for several minutes to migrate hundreds of thousands of independent documents.
- Inside a transaction there are HTTP calls, user waits, or sleep/backoff delays.
- No clear business invariant is articulated, only “wanting to wrap everything together”.
- Every API reading/writing **a single document** opens an unnecessary multi-document transaction.
- The application relies on transactions to compensate for poor data modeling, such as unbounded embedded audit arrays.
- No stable business request ID exists for flows with `$inc` or external charges.
- Abort, retry, or cache overhead is never measured during rollout.

### 19.2. Signs That Transactions or Consistency Boundaries Are Missing

- Debit A succeeds while credit B sometimes fails with no reconciliation.
- An order is `CONFIRMED` without a reservation record, even though the domain states this is never allowed.
- Two SKUs must be reserved together, yet the code issues two `updateOne` calls and returns success if the last one succeeds.
- A user is `ACTIVE` without a required wallet, and there is no `PENDING` state or repair worker.
- A ledger record is written before the balance update and can exist alone on failure.
- A service tries to enforce a cross-document invariant via find+write without a shared guard or transaction.

### 19.3. When Transactions Are Unnecessary Yet Consistent Auditing Is Desired

An audit record **is sometimes part of the business invariant**: for example, an order must have a “transition to PAID” audit entry at the exact time its status changes. In that case:

- If the audit is bounded to a few entries sharing the order lifecycle, you can embed the event in the **order document** and update atomically.
- If the audit must be stored unboundedly in a separate collection **and** cannot be missed, use a transaction for status + audit/outbox record.
- If the audit is telemetry where delayed or occasionally dropped entries are acceptable per policy, the invariant is weaker and an asynchronous pipeline works.

The word “audit” alone does not dictate a transaction; **the business guarantee required for the audit** is the deciding factor.

## 20. Comprehensive Scenario Analysis

### 20.1. An E-Commerce Order

Order O-100 consists of:

~~~text
Order document:
  status = DRAFT
  lines = [SKU-RED qty3, SKU-BLUE qty1]

Inventory documents:
  SKU-RED, SKU-BLUE

Reservation documents:
  R-RED, R-BLUE

Payment provider:
  External service

Outbox:
  Events to publish
~~~

Classify each requirement:

| Requirement | Scope | Decision |
|---|---|---|
| Only change status/updatedAt on the order | One doc | Conditional update. |
| Reserve SKU-RED without going negative | One inventory doc | Conditional `$inc`. |
| Reserve both RED and BLUE, insert reservation records, and update order | Multiple MongoDB docs | Transaction if partial commit is disallowed. |
| Send email right after order confirmation | MongoDB + SMTP | Outbox dispatcher, no SMTP inside transaction. |
| Wait several minutes for payment | MongoDB + gateway | Payment saga/state machine, do not hold a transaction open. |
| Update revenue dashboard | Derived data | Can be eventual via version/checkpoint. |
| Read a point-in-time consistent report | Multiple read docs | Snapshot consistency if required by business. |

### 20.2. Separating Transaction Boundaries from Long Business Workflows

A clean workflow can look like:

~~~text
Step A (short MongoDB transaction):
  Reserve all local SKUs
  Create reservation records
  Set order = RESERVED
  Insert outbox event
Commit
         |
         v
Step B (outside transaction):
  Request payment with idempotency key
         |
      +-- success --> Step C (short transaction):
      |                  Mark order PAID
      |                  Insert outbox ORDER_PAID
      |                Commit
      |
      +-- failure --> Step D (transaction/compensation):
                         Release reservation
                         Mark order PAYMENT_FAILED
                         Insert outbox ORDER_RELEASED
                       Commit
~~~

This example **combines local transactions with an end-to-end saga**. No transaction stays open across the payment gateway call. If Step D fails, idempotent retries or a repair worker are required. If Step C commits but the event has not been published yet, the outbox dispatcher can pick up and continue.

### 20.3. Replay Protection at Every Step

Each step should have an ID:

~~~text
orderId = O-100
reservationId = RES-O-100
paymentRequestId = PAY-O-100
outboxEventId = ORDER_PAID-O-100
~~~

On retry:

- If the reservation is already held, do not deduct stock again.
- If the payment already succeeded, do not charge again with a new request ID.
- If the order is already `PAID`, do not transition it again as a new event.
- If the event was already delivered, the consumer must not apply the side effect twice.

**Atomicity handles partial failures within one boundary; idempotency handles the same business intent repeating across boundaries.**

### 20.4. When Business Invariants Evolve

A startup may initially sell single-SKU orders: a single conditional inventory update suffices. Later, carts support multiple SKUs per order and require reserving all together: the consistency boundary changed, making transactions a candidate. Later still, inventory moves to a separate service: MongoDB transactions no longer span the remote service, requiring sagas/reservations. **The decision to use transactions evolves with architecture and policy**, rather than being a fixed property of MongoDB.

## 21. Hands-On Exercises and Suggested Answers

Each exercise is an **independent scenario**. If running commands against `txn_need_lab` after previous examples modified it, create a separate demo collection or reset fixtures in the lab environment. Never run balance/inventory-modifying commands on production for testing.

### Exercise 1 — One Document, Two Fields

**Prompt:** Inventory document `{_id:"SKU-1",available:10,reserved:0}`. A request needs to decrease `available` by 3 and increase `reserved` by 3. Is a multi-document transaction needed?

**Answer:** No, because both fields are in **the same document**:

~~~javascript
db.inventory.updateOne(
  { _id: "SKU-1", available: { $gte: 3 } },
  { $inc: { available: -3, reserved: 3 } }
)
~~~

This is **a single conditional atomic update**. Filtering `available` inside the operation itself prevents races.

### Exercise 2 — Multiple Documents Without a Shared Invariant

**Prompt:** A job needs to mark 50,000 products with `lastIndexedVersion:7`. If interrupted halfway, the job resumes later filtering by old versions; consuming queries tolerate stale data for a few minutes. Is a transaction needed for all 50,000 products?

**Answer:** No. Batched `updateMany`/`bulkWrite` with checkpoints and idempotency is usually better. Partial progress is an **allowed** state.

### Exercise 3 — Transferring Money Between Two Accounts

**Prompt:** Debit 150 from account A, credit 150 to B. Immediate consistency is required across both documents. What should you choose?

**Answer:** A multi-document transaction, checking `matchedCount` on debit/credit and recording a stable transfer record in the same transaction; choose appropriate read/write concern. Do not rely on two independent `updateOne` calls as an atomic unit.

### Exercise 4 — `bulkWrite(ordered:true)`

~~~javascript
db.accounts.bulkWrite([
  {
    updateOne: {
      filter: { _id: "A" },
      update: { $inc: { balance: -50 } }
    }
  },
  {
    updateOne: {
      filter: { _id: "B" },
      update: { $inc: { balance: 50 } }
    }
  }
], { ordered: true })
~~~

**Prompt:** If B does not exist, does ordered bulk automatically roll back the debit on A?

**Answer:** No. An `updateOne` matching no document **is not an error by default**; it returns `matchedCount: 0` in the result, and ordered bulk does not know the invariant “B must exist”. If both must succeed together, use a transaction and **verify business conditions**, rather than checking only whether the command threw an exception.

### Exercise 5 — Unique Username

**Prompt:** Two concurrent requests register the same username. The only goal is preventing two users with the same username. Is a transaction wrapping `findOne + insertOne` needed?

**Answer:** Normally **no**. A unique index on `username` (with proper canonicalization/collation and null policy) is the database-level safeguard; the application handles `E11000`. Checking beforehand only improves UX and does not prevent races.

### Exercise 6 — User and Wallet

**Prompt:** When creating an `ACTIVE` user, a wallet document must be created at the same time; no `PENDING` state is allowed. Two inserts across two collections. What should be used?

**Answer:** A transaction wrapping both inserts on the same session; if the wallet insert fails, the user insert aborts as well. Pre-create indexes/collections before deployment and use a stable request ID.

### Exercise 7 — With a `PENDING` State

**Prompt:** Policy changes: new users start as `PENDING_WALLET` and become `ACTIVE` only after the wallet is successfully created. A worker can retry. Is a transaction still mandatory?

**Answer:** No. You can use an eventual workflow with idempotent wallet creation, state-based transitions, and a repair worker. The new invariant is “an `ACTIVE` user must have a wallet”, not “every `PENDING` user already has a wallet”.

### Exercise 8 — Two SKUs, All-or-Nothing Requirement

**Prompt:** An order requires SKU-A qty 2 and SKU-B qty 4. If SKU-B is short, SKU-A must not remain reserved. The two SKUs are two inventory documents. Which approach should you choose?

**Answer:** A transaction with two conditional updates and reservation/order state in the same scope, aborting if any `matchedCount` is 0. Alternatively, change the business rule to allow `PENDING` + compensation, in which case a saga is an option; do not treat two independent conditional updates as all-or-nothing.

### Exercise 9 — CAS in One Document

**Prompt:** Two admins edit order version 3 concurrently. You want only one update to succeed and the other to see a conflict.

**Answer:**

~~~javascript
db.orders.updateOne(
  { _id: "O-1", version: 3 },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 }
  }
)
~~~

If the first update increments `version` to 4, the other gets `matchedCount:0`. No multi-document transaction is needed for a single order document.

### Exercise 10 — Balance Query and Snapshot

**Prompt:** A report reads account A, then a transaction transferring A → B commits, then the report reads B. Can the report's sum A+B disagree with both the pre-transaction and post-transaction states?

**Answer:** Yes, because the two independent reads observed **two different points in time**. If a consistent report is required, use read concern/snapshot transactions or a versioned closing snapshot. Atomicity of a write transaction does not make non-snapshot reads consistent across multiple documents.

### Exercise 11 — Write Skew

**Prompt:** Two doctors A/B are on call; the rule is at least one must remain on call. T1 reads both and takes A off call; T2 reads both and takes B off call. T1 and T2 update **two different documents**. Is putting them in snapshot transactions enough to guarantee the invariant will not be violated?

**Answer:** No. **Write skew** can occur under snapshot isolation when they do not contend on the same document/guard. You need a shared guard document updated conditionally or to model the invariant in a single aggregate, handling conflicts and retries.

### Exercise 12 — `w:"majority"`

**Prompt:** If debit A and credit B are two independent writes both using `w:"majority"`, does MongoDB guarantee they commit or roll back together?

**Answer:** No. Majority write concern controls the write acknowledgment level **of each individual command**. It does not turn two independent writes into a transaction.

### Exercise 13 — Transaction Callbacks Can Retry

**Prompt:** Inside `session.withTransaction()`, code calls a payment gateway to charge, then commits MongoDB. The driver encounters a transient error and retries the callback. What is the risk?

**Answer:** The payment may be charged **a second time** because calls to external systems are outside the transaction. Do not place external side effects inside the callback. Use gateway idempotency keys, outbox/sagas, and workflow states decoupled from the MongoDB transaction.

### Exercise 14 — Unknown Commit Result

**Prompt:** The client receives `UnknownTransactionCommitResult` after committing a transfer. Should it immediately open a new transaction with a new transfer ID?

**Answer:** No. The previous transaction **may have already committed**. Use the transaction API to retry the commit per guidelines, and look up the stable `transferId`/reconcile as needed; do not unconditionally replay the business operation with a new ID.

### Exercise 15 — Duplicate Transfer ID

**Prompt:** An HTTP request repeats the same `requestId:"TX-1"`, but the second payload has a different amount. The unique index reports a duplicate. Should the backend return “transfer succeeded” or something else?

**Answer:** It must **compare the payload** against the existing record. If `amount`/`from`/`to`/`currency` differ, return **conflict** and do not transfer again. Do not treat every duplicate key as an idempotent success.

### Exercise 16 — Migration Cannot Expose Half-Old, Half-New Data

**Prompt:** A system wants to migrate 1 million documents without readers seeing a mix of old and new schemas. Should it use one giant transaction?

**Answer:** Not by default. Consider **versioned datasets**, compatible dual-read/write, backfilling into a new collection followed by an **atomic pointer/metadata switch** when ready, or an appropriate workflow. A million-record transaction can exceed lifetime/cache limits and cause heavy contention. Only use transactions at small boundaries that truly need to commit together.

### Exercise 17 — Outbox and Duplicate Events

**Prompt:** A transaction commits an order and an outbox event. The dispatcher publishes the event successfully but crashes before marking it dispatched. On restart, the event publishes again. Did the outbox fail?

**Answer:** Not necessarily. This is **at-least-once delivery**. Consumers must deduplicate by `eventId`; the outbox guarantees the intent to emit the event is saved atomically with DB state, not end-to-end exactly-once delivery to external systems.

### Exercise 18 — Same Shard

**Prompt:** Two account documents reside on the same shard in a sharded cluster. Since they are on the same shard, can two independent `updateOne` calls replace a transaction to guarantee debit/credit commit together?

**Answer:** No. **Same shard is not the same document**. If all-or-nothing is required across two documents, a transaction or a redesigned data/business model is still required.

### Exercise 19 — Two Fields in an Embedded Order

**Prompt:** An order document contains `status`, `confirmedAt`, `shippingAddressSnapshot`, and `items`. Only `status` and `confirmedAt` need to change together. What is the benefit of using a multi-document transaction?

**Answer:** Usually none. A single conditional `updateOne` on the order document already guarantees atomicity; adding a multi-document transaction complicates the API without solving any cross-document invariant.

### Exercise 20 — Overly Long Transaction

**Prompt:** A transaction stays open for 8 minutes, scans many documents, calls an HTTP service, and then commits. What are the risks?

**Answer:** Transactions face lifetime limits, cache, and lock constraints, easily abort or conflict, and external services are outside the commit and may be called repeatedly. Split into short transactions for local invariants, and handle HTTP workflows via sagas/outbox/idempotency.

### Exercise 21 — When a Transaction Still Does Not Protect a Business Rule

**Prompt:** Inside a transaction, code decrements A by 150 and increments B by **120**; all commands succeed. Does MongoDB block the commit because the total balance changed?

**Answer:** Not automatically. A transaction guarantees that the **issued commands commit/abort together**, without understanding conservation of money. The application must validate amounts and ledger invariants; consider double-entry design, validation, and reconciliation.

### Exercise 22 — “Update Matched Nothing” Inside a Transaction

**Prompt:** A transaction calls `updateOne({balance:{$gte:500}},{$inc:{balance:-500}})` which returns `matchedCount:0` without throwing an exception. If the code does not check and still credits account B, can the transaction commit?

**Answer:** Yes. A non-matching update does not throw an error by default; if the application proceeds to commit, B can be credited without A being debited. **You must check `matchedCount`** and throw/abort when business preconditions fail.

### Exercise 23 — Transactions Creating Data Across Multiple Collections

**Prompt:** An order must have both an `orders` document and an `invoice` document to be considered `POSTED`. If the invoice insert fails, the order must not exist in `POSTED` status. What design makes sense?

**Answer:** A transaction creating/updating the order and invoice together, or a workflow with a `PENDING_INVOICE` state that never exposes `POSTED` until the invoice exists. The choice depends on whether intermediate states are acceptable.

### Exercise 24 — Using Transactions to Guarantee Unique Emails?

**Prompt:** Inside transactions, two concurrent requests query for an email and then insert the same email, **without** a unique index. Can this guarantee no duplicate emails?

**Answer:** You should not rely on it. Both transactions can read snapshots where the email is absent and then insert **two different documents**; there is no unique constraint blocking duplicate keys. Use a **unique index** as the enforcement point rather than check-then-insert inside transactions.

### Exercise 25 — Splitting a Business Workflow

**Prompt:** A flow needs to (a) create a reservation in MongoDB, (b) call a payment gateway, and (c) send an email. Can one MongoDB transaction span all three for all-or-nothing execution?

**Answer:** No. Payment and email are outside MongoDB transactions; design a short transaction for reservation/outbox, gateway idempotency, a saga with compensation, and an idempotent dispatcher/consumer. The overall outcome can be eventual with explicit states.

## 22. Official MongoDB Documentation and Further Learning

The following links help verify syntax and limits **by MongoDB Server/Driver version**. For real deployments, always consult the exact MongoDB version you run (along with FCV, topology, and driver version) rather than applying a limit from a different version verbatim.

1. [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity guarantees; concurrent updates and filter evaluation at write time.
2. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transaction types, all-or-nothing semantics, replica sets/sharded clusters, read/write concerns.
3. [Transactions — Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — locks, WiredTiger cache, lifetime, DDL, sharded concerns, and operational constraints.
4. [Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — error labels and retry logic, drivers/convenient APIs.
5. [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — difference between technical retries and business request replays.
6. [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — `local`, `majority`, `snapshot`, and read consistency.
7. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j`, and write acknowledgment levels.
8. [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — read observation models, single-document atomicity, and transaction snapshots.
9. [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — filter + update operators + `matchedCount`, `arrayFilters`, and `upsert`.
10. [`db.collection.updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — per-document atomicity when modifying multiple documents.
11. [`db.collection.bulkWrite()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — ordered/unordered execution, per-operation error handling, and partial success.
12. [`db.collection.findOneAndUpdate()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/) — atomically read, modify, and return one document.
13. [Model Data for Atomic Operations](https://www.mongodb.com/docs/manual/tutorial/model-data-for-atomic-operations/) — designing documents so fields that change together stay together.
14. [Embedded Data](https://www.mongodb.com/docs/manual/data-modeling/embedding/) — benefits of embedding and limits around cardinality/lifecycle.
15. [References](https://www.mongodb.com/docs/manual/data-modeling/references/) — when data should live in separate documents.
16. [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — 16 MiB BSON limit and system limits.
17. [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — protecting business keys from duplicates across concurrent requests.
18. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction()`, `TransactionOptions`, and error handling.
19. [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — `updateOne()`, builders, and result handling.
20. [MongoDB 8.0 — Transactions](https://www.mongodb.com/docs/v8.0/core/transactions/) — pinned documentation for the 8.0 branch to verify behavior/limits.
21. [MongoDB 7.0 — Transactions](https://www.mongodb.com/docs/v7.0/core/transactions/) — reference for the 7.0 branch on systems not yet upgraded.
22. [MongoDB Drivers API — Transactions Specification](https://github.com/mongodb/specifications/blob/master/source/transactions/transactions.md) — session, retry, and behavior concepts at the driver specification level, for advanced learners.

### 22.1. Pull Request Review Checklist

Before merging a change that uses a transaction, reviewers can ask:

1. **Which invariant must hold?** State it in a verifiable way, e.g., “no transfer exists that debited without crediting”.
2. **How many documents does the invariant span?** Could it reasonably live in one document?
3. **Is a `PENDING` state or partial progress allowed?** If yes, would saga/batching with reconciliation suffice?
4. **Do all writes in the transaction use the same session?** Did any write accidentally run outside the transaction?
5. **Do conditional updates check `matchedCount`?** Transactions do not throw automatically when a filter matches nothing.
6. **Are there a unique business ID and idempotency?** Post-commit timeouts can trigger API replays.
7. **Are there external calls inside the transaction callback?** Move side effects to an outbox/saga.
8. **Are retries and commit outcomes properly classified?** Never replay unconditionally when commit outcome is unknown.
9. **Is there potential write skew or an uncontended cross-document invariant?** Is a shared guard/CAS needed?
10. **Is the transaction scope small, properly indexed, and within resource limits?** Measure under concurrency.

## 23. Conclusion

**Multi-document transactions are only needed when a business invariant requires changes across multiple MongoDB documents to commit or abort together, or when a sequence of reads requires a consistent snapshot that independent reads cannot guarantee.** The number of documents or collections alone **does not** determine whether a transaction is needed: the deciding factor is **the required level of consistency**.

Before introducing a transaction, choose the right **aggregate/document boundary**, and leverage **atomic conditional updates**, `$inc`, CAS/versioning, and **unique indexes** for constraints enforceable on a single document or key. When data has independent lifecycles and the invariant genuinely spans multiple documents, a **short transaction with proper session usage, read/write concerns, and `matchedCount` checks** is usually the clear choice.

Finally, a transaction is not “magic against every race”: the application must still define business invariants, prevent write skew using shared guards or appropriate modeling, handle write conflicts and commit outcomes, use **stable idempotency keys**, and offload **external side effects** to an outbox or saga when needed. The best design uses **the fewest transactions necessary while strictly preserving all mandatory business guarantees**.
