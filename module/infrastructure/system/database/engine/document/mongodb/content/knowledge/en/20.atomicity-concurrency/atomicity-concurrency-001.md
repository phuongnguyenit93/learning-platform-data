# Single-Document Atomicity and Multi-Document Limits in MongoDB

## 1. What is atomicity, and why does the document boundary matter?

In a system where multiple users or multiple services write data concurrently, two requirements often arise at the same time:

- An order must not have **status = "paid"** while **paidAt** is still empty because only half of the fields were updated.
- A customer must not withdraw more money than their balance, even when two withdrawal requests arrive almost simultaneously.

MongoDB has a foundational property: **a write operation on a single document is atomic**, even when that operation modifies multiple fields or multiple elements within the document. However, **single-document atomicity does not automatically extend to multi-document atomicity**.

For example:

~~~text
Document A: an Order
   status: "draft"
   paidAt: null
   paymentReference: null

One updateOne modifies all three fields:
   status: "paid"
   paidAt: a BSON Date
   paymentReference: "pay-001"

=> One write operation on a single document:
   there is no intermediate write state where "only one field was modified"
   visible as a half-written result.
~~~

But with two wallet documents:

~~~text
Wallet A: balance = 100
Wallet B: balance =  40

Transfer 30 from A to B:
  1) A -= 30
  2) B += 30

Two independent updateOne calls:
  after step 1: A=70, B=40 (total is only 110)
  after step 2: A=70, B=70 (total returns to 140)
~~~

Each step can be atomic **individually**, but if the program fails after step 1 or another request reads in between, the system can observe an **incomplete transfer** state. To guarantee all-or-nothing across both wallets, you need to design a transaction or another suitable business mechanism.

### Lesson Objectives

After this lesson, you will be able to:

1. Accurately explain MongoDB's **single-document atomicity boundary**.
2. Write **$set**, **$inc**, **$unset**, and multi-field updates in **a single** updateOne.
3. Prevent **lost updates** using update operators, conditional filters, and optimistic concurrency control.
4. Use **findOneAndUpdate** to select and update a single document in one operation.
5. Understand why **updateMany**, **deleteMany**, and **bulkWrite** are not all-or-nothing by default.
6. Identify when to model data within the same document versus when to use a **multi-document transaction**.
7. Distinguish atomicity from **isolation, durability, write concern, read concern, and retries**.
8. Write hands-on scripts on a lab database and explain the outcomes under write contention scenarios.

> The commands below use a dedicated practice database **mongo_atomic_lab** and the tag **atomicity-v1**. Many examples modify data, so each section explicitly notes when you need to re-run the seed. Do not run them against production wallets or inventory.

## 2. What does single-document atomicity mean precisely?

### 2.1. A single write command can change multiple fields together

Suppose an order stores:

~~~javascript
{
  _id: "order-101",
  tenantId: "t001",
  status: "draft",
  paidAt: null,
  paymentReference: null,
  version: 0
}
~~~

We want to transition the order to paid:

~~~javascript
db.orders.updateOne(
  { _id: "order-101", tenantId: "t001", status: "draft" },
  {
    $set: {
      status: "paid",
      paidAt: new Date(),
      paymentReference: "pay-101"
    },
    $inc: { version: 1 }
  }
);
~~~

MongoDB executes **one atomic update on the Order document**. Readers observing documents at appropriate points do not see a state where only status changed to paid while the other fields of **the same update** have not been applied yet.

This does **not** include side effects outside the document, such as sending emails, writing logs to another system, updating another collection, or calling a payment gateway API.

### 2.2. Atomic does not mean a separate read statement and write statement form one operation

Error-prone pattern:

~~~javascript
const order = db.orders.findOne({ _id: "order-101" });

// Between findOne and updateOne, another service can modify the order.

db.orders.updateOne(
  { _id: "order-101" },
  { $set: { status: "paid" } }
);
~~~

These are **two separate operations**. Having findOne read status draft **does not lock that state** until updateOne runs. If updateOne only filters by _id, it can overwrite an order that another task has already transitioned to cancelled.

Fix this by placing **the business condition directly inside the filter of updateOne itself**:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-101",
    tenantId: "t001",
    status: "draft"
  },
  {
    $set: {
      status: "paid",
      paidAt: new Date()
    }
  }
);
~~~

MongoDB evaluates the condition when applying the write operation. If the state has changed beforehand, the operation will no longer match instead of blindly overwriting.

### 2.3. “Atomic” does not mean “never fails”

An update can fail due to validation, insufficient privileges, network errors, write conflicts, unmatched filter conditions, or other limits. Atomicity means **not exposing a half-written state within a single document**, not a promise that every request succeeds.

Also do not conflate:

| Property | Question |
| --- | --- |
| **Atomicity** | Can a change be partially applied? |
| **Isolation** | How can concurrent operations see and affect each other? |
| **Consistency / invariant** | Do business rules remain valid after the operation? |
| **Durability** | At what acknowledgment level is a successful write persisted? |
| **Idempotency** | Does resending the same request cause additional effects? |

MongoDB supports single-document atomicity, but **how you write filters and updates determines whether a business invariant is protected**.

## 3. Setting up a repeatable lab

We use four collections:

- **lab_wallets:** two wallets belonging to the same tenant; balances are stored in **balanceCents** as Int32 so examples avoid floating-point precision errors.
- **lab_stock:** one inventory document with **available**, **reserved**, and version.
- **lab_orders:** three orders with statuses draft/pending/paid.
- **lab_transfer_audit:** records a money transfer when practicing transactions.

Initial IDs and values are fixed so results can be verified after each experiment.

### 3.1. Seed script

Run as a single block in **mongosh**:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_atomic_lab");
  const tag = "atomicity-v1";
  const wallets = lab.getCollection("lab_wallets");
  const stock = lab.getCollection("lab_stock");
  const orders = lab.getCollection("lab_orders");
  const audit = lab.getCollection("lab_transfer_audit");

  // Only delete documents belonging to the practice dataset.
  wallets.deleteMany({ dataset: tag });
  stock.deleteMany({ dataset: tag });
  orders.deleteMany({ dataset: tag });
  audit.deleteMany({ dataset: tag });

  wallets.insertMany([
    {
      _id: "wallet-a",
      dataset: tag,
      tenantId: "t001",
      ownerId: "alice",
      balanceCents: NumberInt(10000),
      version: NumberInt(0)
    },
    {
      _id: "wallet-b",
      dataset: tag,
      tenantId: "t001",
      ownerId: "bob",
      balanceCents: NumberInt(4000),
      version: NumberInt(0)
    }
  ]);

  stock.insertOne({
    _id: "sku-001",
    dataset: tag,
    tenantId: "t001",
    available: NumberInt(2),
    reserved: NumberInt(0),
    version: NumberInt(0),
    reservations: []
  });

  orders.insertMany([
    {
      _id: "order-101",
      dataset: tag,
      tenantId: "t001",
      status: "draft",
      paidAt: null,
      paymentReference: null,
      version: NumberInt(0)
    },
    {
      _id: "order-102",
      dataset: tag,
      tenantId: "t001",
      status: "draft",
      paidAt: null,
      paymentReference: null,
      version: NumberInt(0)
    },
    {
      _id: "order-103",
      dataset: tag,
      tenantId: "t001",
      status: "pending",
      paidAt: null,
      paymentReference: null,
      version: NumberInt(0)
    }
  ]);

  wallets.createIndex(
    { dataset: 1, tenantId: 1, ownerId: 1 },
    { name: "ix_atomic_wallet_owner" }
  );

  stock.createIndex(
    { dataset: 1, tenantId: 1 },
    { name: "ix_atomic_stock_scope" }
  );

  orders.createIndex(
    { dataset: 1, tenantId: 1, status: 1 },
    { name: "ix_atomic_order_status" }
  );

  printjson({
    wallets: wallets.countDocuments({ dataset: tag }),
    stock: stock.countDocuments({ dataset: tag }),
    orders: orders.countDocuments({ dataset: tag }),
    audit: audit.countDocuments({ dataset: tag })
  });
})();
~~~

**Expected output:** wallets = **2**, stock = **1**, orders = **3**, audit = **0**.

### 3.2. Baseline values to remember

| Document | Field | Value |
| --- | --- | ---: |
| wallet-a | balanceCents | 10,000 |
| wallet-b | balanceCents | 4,000 |
| sku-001 | available | 2 |
| sku-001 | reserved | 0 |
| order-101 | status | draft |
| order-102 | status | draft |
| order-103 | status | pending |

The initial total balance across both wallets is **14,000 cents**. The initial sum of available + reserved for sku-001 equals **2**.

To inspect the state:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_atomic_lab");
  const tag = "atomicity-v1";

  print("Wallets:");
  printjson(
    lab.lab_wallets.find(
      { dataset: tag },
      { _id: 1, balanceCents: 1, version: 1 }
    ).sort({ _id: 1 }).toArray()
  );

  print("Stock:");
  printjson(
    lab.lab_stock.findOne(
      { _id: "sku-001", dataset: tag }
    )
  );
})();
~~~

**The examples in the following sections are independent experiments** unless explicitly stated otherwise. Re-run the seed in section 3.1 before each experiment when you want to compare against the expected values.

## 4. A single updateOne modifies multiple fields atomically

### 4.1. Transitioning order status and recording payment info

After running the seed:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_atomic_lab");
  const orders = lab.getCollection("lab_orders");

  const result = orders.updateOne(
    {
      _id: "order-101",
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: {
        status: "paid",
        paidAt: ISODate("2026-06-01T10:00:00.000Z"),
        paymentReference: "pay-lab-101"
      },
      $inc: { version: 1 }
    }
  );

  printjson(result);
  printjson(orders.findOne({ _id: "order-101" }));
})();
~~~

**First-run result:** matchedCount = **1**, modifiedCount = **1**. The document has status paid, paidAt, and paymentReference set together, with version = **1**.

Running the exact same command again yields **matchedCount = 0** because status is no longer draft. This is the desired behavior: the same operation does not "pay" a document that is already in the paid state.

### 4.2. Why check matchedCount and modifiedCount?

The MongoDB driver/mongosh typically returns the following fields:

- **matchedCount:** the number of documents matching the filter for updateOne; usually 0 or 1.
- **modifiedCount:** the number of documents actually modified.
- **upsertedCount/upsertedId:** only present when upsert is enabled and a new insert occurs.

With **matchedCount = 0**, either the _id was not found or conditions such as tenant/status/version are no longer satisfied. Do not treat this as a connection error and blindly retry forever. With **matchedCount = 1, modifiedCount = 0**, the update may have set fields to the exact same values they already had (unless there is a guaranteed changing operator such as incrementing version).

In business logic, **failing to match the state condition** should be returned as an explicit outcome, such as "order was already processed or is no longer in an allowed state," rather than overwriting it.

### 4.3. Updating an Array inside the same document

Atomicity also applies when an operation modifies **an array and multiple fields of the same document**:

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_stock")
  .updateOne(
    {
      _id: "sku-001",
      dataset: "atomicity-v1",
      tenantId: "t001",
      available: { $gte: 1 }
    },
    {
      $inc: {
        available: -1,
        reserved: 1,
        version: 1
      },
      $addToSet: {
        reservations: "reservation-001"
      }
    }
  );
~~~

Starting from the initial seed, the stock document becomes **available = 1**, **reserved = 1**, **version = 1**, and reservations contains reservation-001. All changes belong to one write operation on the stock document.

Important note: **$addToSet only avoids inserting a value that already exists in the Array**; it does not automatically make the entire operation idempotent. If you run the command above again while available is still sufficient, **$inc will still execute again** even though reservation-001 is already in the array. If each reservation must decrement inventory only once, the filter must ensure reservationId does not yet exist, or a dedicated idempotency mechanism is needed.

## 5. Write contention: lost update with read–modify–write

### 5.1. Two reads seeing the same stale balance

Suppose two nearly simultaneous requests both read **wallet-a = 10,000 cents**:

~~~text
Request A reads balance=10,000
Request B reads balance=10,000

A wants to withdraw 1,000 => computed in app: 9,000
B wants to withdraw 2,000 => computed in app: 8,000

A $set balance=9,000
B $set balance=8,000

Final result = 8,000
Two withdrawals should actually leave = 7,000
~~~

Each **$set on a single document** is atomic; the bug occurs because both computed based on a **stale snapshot** and then overwrote each other. This is a **lost update**, not MongoDB "writing half a document."

### 5.2. Simulating a lost update in a single mongosh session

Re-run the seed before this snippet. We deliberately simulate **two identical stale read results**, without needing two concurrent processes:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_wallets");
  const filter = {
    _id: "wallet-a",
    dataset: "atomicity-v1",
    tenantId: "t001"
  };

  const snapshotA = c.findOne(filter);
  const snapshotB = c.findOne(filter);

  const resultA = c.updateOne(
    filter,
    { $set: { balanceCents: snapshotA.balanceCents - 1000 } }
  );
  const resultB = c.updateOne(
    filter,
    { $set: { balanceCents: snapshotB.balanceCents - 2000 } }
  );

  printjson({ first: resultA.modifiedCount,
              second: resultB.modifiedCount });
  print("Final balance: " +
    c.findOne(filter).balanceCents);
})();
~~~

**Expected output:** final balance = **8,000 cents**, not 7,000. The second command used the stale read value of 10,000 and overwrote the first command's result of 9,000.

**Takeaway:** an atomic update does not automatically fix an **application-side read–modify–write** bug when the new value is computed from a stale read without concurrency conditions.

## 6. Using update operators to avoid overwrites

### 6.1. $inc performs increment/decrement on the server

Re-run the seed. Instead of reading the balance and using $set, send the delta:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_wallets");
  const filter = {
    _id: "wallet-a",
    dataset: "atomicity-v1",
    tenantId: "t001"
  };

  const first = c.updateOne(
    filter,
    { $inc: { balanceCents: -1000 } }
  );
  const second = c.updateOne(
    filter,
    { $inc: { balanceCents: -2000 } }
  );

  printjson({ first: first.modifiedCount,
              second: second.modifiedCount });
  print("Final balance: " +
    c.findOne(filter).balanceCents);
})();
~~~

**Expected output:** **7,000 cents**. Both $inc operations act on the current value of the same document; each update is atomic and does not need to overwrite using a stale snapshot.

However, remember another detail: **a negative $inc does not automatically guarantee a non-negative balance**. If multiple withdrawals exceed the balance, MongoDB will still apply the decrement if the filter does not forbid it.

### 6.2. Conditional filters protect the balance invariant

Re-run the seed. To withdraw 3,000 cents only when the account has sufficient funds:

~~~javascript
(() => {
  const c = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_wallets");
  const amount = 3000;

  const result = c.updateOne(
    {
      _id: "wallet-a",
      dataset: "atomicity-v1",
      tenantId: "t001",
      balanceCents: { $gte: amount }
    },
    {
      $inc: {
        balanceCents: -amount,
        version: 1
      }
    }
  );

  printjson(result);
  printjson(
    c.findOne(
      { _id: "wallet-a", dataset: "atomicity-v1" },
      { _id: 1, balanceCents: 1, version: 1 }
    )
  );
})();
~~~

**Expected output on first run:** matchedCount = 1, remaining balance **7,000**, version = 1. If you subsequently request a withdrawal of **8,000** with the filter balanceCents >= 8,000, you get **matchedCount = 0** and the balance stays 7,000.

When two withdrawal requests arrive concurrently, the **balanceCents >= amount** check sits inside **updateOne itself**. With this design, each withdrawal can only succeed if the document still satisfies the condition at update time; it does not rely on a previously read balance.

**Business rules must be designed completely.** This lab snippet does not replace a ledger system, fraud checks, idempotency, or authorization controls. If a withdrawal request for 3,000 is submitted twice as two independent $inc commands, it can still deduct **6,000** if the balance is sufficient both times.

### 6.3. Conditional updates act as conditional compare-and-set

Pattern:

~~~text
UPDATE document
  IF version == version read earlier
  THEN modify fields and version += 1
  ELSE do not modify
~~~

In MongoDB, you do not need a separate API named CAS: a **version** filter combined with update operators expresses compare-and-set on a single document.

## 7. Optimistic concurrency control with version

### 7.1. Why is version needed?

For some fields, the change is not an addition that can use $inc. For example, two people editing a shipping address simultaneously:

~~~text
User A reads version=3, old address
User B reads version=3, old address

A edits address to X
B edits address to Y

If filtering only by _id, the later request can overwrite the earlier request.
~~~

**Optimistic concurrency control** stores a version number in the document, requiring writers to assert that the version has not changed.

### 7.2. Example on the order lab

Re-run the seed:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_orders");

  const identity = {
    _id: "order-101",
    dataset: "atomicity-v1",
    tenantId: "t001"
  };

  const readByA = orders.findOne(identity);
  const readByB = orders.findOne(identity);

  const resultA = orders.updateOne(
    { ...identity, version: readByA.version },
    {
      $set: { shippingNote: "Deliver in the morning" },
      $inc: { version: 1 }
    }
  );

  const resultB = orders.updateOne(
    { ...identity, version: readByB.version },
    {
      $set: { shippingNote: "Deliver in the afternoon" },
      $inc: { version: 1 }
    }
  );

  printjson({
    firstMatched: resultA.matchedCount,
    secondMatched: resultB.matchedCount
  });
  printjson(
    orders.findOne(identity, {
      _id: 1, version: 1, shippingNote: 1
    })
  );
})();
~~~

**Expected output:**

- A matchedCount = **1**, shippingNote is “Deliver in the morning”, version increments from 0 to 1.
- B matchedCount = **0** because it still used version 0.
- A's change is not overwritten by B.

The application should return a **business-meaningful conflict**, such as asking the client to reload and decide whether to overwrite or merge. Do not automatically retry B with the new version and overwrite A unless conflict resolution rules are defined.

### 7.3. Limitations of version

Version is only effective when **every relevant write path updates and checks version under a consistent contract**. Another task that updates the document without incrementing version can prevent clients from detecting conflicts. Nor does version hold a continuous lock on the document between two requests.

If you need to use **updatedAt** as a marker, be careful with clock resolution and operations sharing the same timestamp. A clear monotonically increasing integer is usually easier to manage for optimistic concurrency.

## 8. findOneAndUpdate: select and update in one operation

### 8.1. Replacing separate candidate lookup and update

Suppose a worker needs to pick a pending job and transition it to processing. The pattern:

~~~text
findOne({status:"pending"})
  ->
updateOne({_id:job._id}, {$set:{status:"processing"}})
~~~

has a race window: two workers can pick the same pending job before either worker marks it. **findOneAndUpdate** allows selecting and updating a single document as one operation, together with filter conditions.

Example with lab order-103:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_orders");

  const claimed = orders.findOneAndUpdate(
    {
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "pending"
    },
    {
      $set: {
        status: "processing",
        claimedBy: "worker-A",
        claimedAt: ISODate("2026-06-01T11:00:00.000Z")
      },
      $inc: { version: 1 }
    },
    {
      sort: { _id: 1 },
      returnDocument: "after"
    }
  );

  printjson(claimed);
})();
~~~

**Result after seed:** returns **order-103** with status processing and claimedBy worker-A. Running it again returns **null** if no pending documents remain.

**returnDocument: "after"** requests returning the document state **after the update**. Do not confuse this with different driver APIs where the result may be wrapped in a metadata object depending on version; the example above uses mongosh.

### 8.2. Why isn't returnDocument a separate read?

When using findOneAndUpdate, MongoDB identifies one matching document and updates it in a single atomic operation. That is the right mechanism for claiming a job or conditionally changing state.

However:

- It does not by itself guarantee the job is **actually processed only once** if the worker crashes after claiming.
- It does not automatically protect side effects outside the database.
- A real queue system needs timeout/lease design, retries, and idempotency.
- If multiple documents match, use an explicit sort and appropriate index to control ordering; do not assume an arbitrary document will always be chosen consistently.

An atomic single-document claim is a necessary step, but not the entirety of a reliable job-processing protocol.

## 9. updateMany and deleteMany: atomic per document, not across the whole set

### 9.1. updateMany

For example, transitioning all draft orders of t001 to pending:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_atomic_lab")
    .getCollection("lab_orders");

  const result = orders.updateMany(
    {
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: { status: "pending" },
      $inc: { version: 1 }
    }
  );

  printjson(result);
})();
~~~

From the seed, the first run yields **matchedCount = 2** and **modifiedCount = 2** (order-101 and order-102).

**Each document update is atomic**, but **the entire updateMany is not wrapped in an automatic transaction**. While updateMany is running, other tasks may observe some documents changed and others not yet changed (depending on the read/concurrency model). If the operation fails or is interrupted, some documents may already have been modified.

### 9.2. deleteMany

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_orders")
  .deleteMany({
    dataset: "atomicity-v1",
    tenantId: "t001",
    status: "draft"
  });
~~~

deleteMany also deletes multiple documents; **each single-document deletion is atomic**, but the entire set of matching documents does not automatically form an all-or-nothing unit. Do not treat deleteMany as "either delete all or delete none" without an appropriate transaction.

### 9.3. bulkWrite is not automatically a transaction

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_orders")
  .bulkWrite(
    [
      {
        updateOne: {
          filter: { _id: "order-101", dataset: "atomicity-v1" },
          update: { $set: { status: "pending" } }
        }
      },
      {
        updateOne: {
          filter: { _id: "order-102", dataset: "atomicity-v1" },
          update: { $set: { status: "pending" } }
        }
      }
    ],
    { ordered: true }
  );
~~~

**ordered: true** controls executing operations in order and stopping on error. **ordered: false** allows flexible ordering and continuing remaining operations per bulk write semantics. Neither **automatically guarantees rolling back all earlier succeeded operations if a later operation fails**.

### 9.4. Quick comparison

| Operation | Default atomicity scope | Can modify/delete multiple documents? |
| --- | --- | --- |
| **updateOne** | One selected document | No, at most one |
| **replaceOne** | One selected document | No, at most one |
| **deleteOne** | One selected document | No, at most one |
| **findOneAndUpdate** | Select and update one document | No, at most one |
| **updateMany** | Each document individually | Yes |
| **deleteMany** | Each document individually | Yes |
| **bulkWrite** | Per operation/document under its own semantics | Yes |
| **Multi-document transaction** | Operations inside the transaction commit/abort together | Yes, within deployment limits |

If a document simultaneously contains multiple elements in an Array, updateOne can modify multiple Array elements **while remaining inside a single document**. The number of modified elements is not how the atomicity boundary is defined; **the number of modified documents** is the primary boundary.

## 10. Transferring money between two wallets: why is a transaction needed?

### 10.1. Two independent updateOne calls leave a gap

After seeding, suppose we want to transfer **3,000 cents** from wallet-a to wallet-b:

~~~javascript
// This is an INTENTIONALLY NON-TRANSACTIONAL PATTERN, used only for explanation.
const wallets = db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_wallets");

const debit = wallets.updateOne(
  {
    _id: "wallet-a",
    dataset: "atomicity-v1",
    tenantId: "t001",
    balanceCents: { $gte: 3000 }
  },
  { $inc: { balanceCents: -3000 } }
);

// If the application crashes here, only wallet A has been debited.

if (debit.matchedCount === 1) {
  wallets.updateOne(
    {
      _id: "wallet-b",
      dataset: "atomicity-v1",
      tenantId: "t001"
    },
    { $inc: { balanceCents: 3000 } }
  );
}
~~~

If both succeed, A = **7,000**, B = **7,000**, total = **14,000**. But if only the debit succeeds, A = 7,000 and B = 4,000, leaving a total of 11,000. One atomic updateOne cannot roll back another updateOne that ran before it.

**Do not use this pattern for production financial transactions.** It is shown to clarify the boundary of single-document atomicity.

### 10.2. Multi-document transactions guarantee all-or-nothing in the database

MongoDB supports **multi-document transactions** on **replica sets** and **sharded clusters** subject to version/deployment requirements. A transaction can group:

1. Check and debit the source wallet.
2. Credit the destination wallet.
3. Write an audit document for the transfer.
4. **Commit** all or **abort** all.

Diagram:

~~~text
START TRANSACTION
       |
       +-- UPDATE wallet-a: -3,000 if sufficient
       |
       +-- UPDATE wallet-b: +3,000
       |
       +-- INSERT transfer-audit
       |
       +-- COMMIT
             |
             +-- success: all three changes take effect
             |
             +-- abort: changes in the transaction are not committed
~~~

Transactions are the solution when **an invariant must hold across multiple documents**. However, they carry costs in resources, latency, contention, and error-handling complexity. If the data model can place related fields into **one document with a suitable size bound and lifecycle**, a single-document update is usually simpler.

## 11. Transaction example with the MongoDB Node.js driver

This example is Node.js code for a lab environment with a MongoDB **replica set or sharded cluster that supports transactions**; it will not succeed on a standalone mongod that does not support transactions. You must install the **mongodb** package and provide a URI with read/write access to the lab database.

Re-run the section 3 seed before trying this. The example uses a **fixed transferId** to identify the business request; it only modifies documents with the lab dataset and fixed IDs.

~~~javascript
// Save as a JavaScript example if running with Node.js (ES module).
// npm install mongodb
import { MongoClient } from "mongodb";

async function transferOnce(uri, transferId, amountCents) {
  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw new Error("amountCents must be a positive integer");
  }

  const client = new MongoClient(uri);
  await client.connect();

  const session = client.startSession();
  const lab = client.db("mongo_atomic_lab");
  const wallets = lab.collection("lab_wallets");
  const audit = lab.collection("lab_transfer_audit");
  const dataset = "atomicity-v1";
  const tenantId = "t001";

  try {
    await session.withTransaction(async () => {
      // If the request already committed earlier with the same ID, do not transfer a second time.
      const existing = await audit.findOne(
        { _id: transferId, dataset },
        { session }
      );

      if (existing) {
        if (
          existing.amountCents !== amountCents ||
          existing.fromWalletId !== "wallet-a" ||
          existing.toWalletId !== "wallet-b"
        ) {
          throw new Error("transferId was already used for different parameters");
        }
        return;
      }

      const debit = await wallets.updateOne(
        {
          _id: "wallet-a",
          dataset,
          tenantId,
          balanceCents: { $gte: amountCents }
        },
        {
          $inc: {
            balanceCents: -amountCents,
            version: 1
          }
        },
        { session }
      );

      if (debit.matchedCount !== 1) {
        throw new Error("Source wallet has insufficient funds or is invalid");
      }

      const credit = await wallets.updateOne(
        {
          _id: "wallet-b",
          dataset,
          tenantId
        },
        {
          $inc: {
            balanceCents: amountCents,
            version: 1
          }
        },
        { session }
      );

      if (credit.matchedCount !== 1) {
        throw new Error("Valid destination wallet not found");
      }

      await audit.insertOne(
        {
          _id: transferId,
          dataset,
          tenantId,
          fromWalletId: "wallet-a",
          toWalletId: "wallet-b",
          amountCents,
          createdAt: new Date()
        },
        { session }
      );
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      readPreference: "primary"
    });
  } finally {
    await session.endSession();
    await client.close();
  }
}

// Example call with a test replica set/sharded cluster URI:
// await transferOnce(process.env.MONGODB_URI, "transfer-lab-001", 3000);
~~~

After a successful one-time transfer, the expected state is:

~~~text
wallet-a: 7,000 cents
wallet-b: 7,000 cents
Total:   14,000 cents
lab_transfer_audit: contains document transfer-lab-001
~~~

### 11.1. Why pass session to each operation?

Every **findOne, updateOne, and insertOne** call inside the callback must receive the same **session**. If an updateOne is not passed the session, it can execute **outside the transaction** and will not be rolled back when the callback fails.

A transaction is not simply calling **startTransaction** at the top and having every command in the whole program automatically belong to the transaction. Session scope must be managed explicitly.

### 11.2. Why check matchedCount?

If the source wallet has insufficient funds, the **balanceCents >= amountCents** filter does not match; the callback throws an error so the transaction aborts. If the destination wallet does not exist, the credit operation has matchedCount = 0; it must also abort rather than committing only the debit.

A transaction **does not automatically understand business constraints**. If you omit the sufficient-funds condition, the transaction can commit a negative-balance withdrawal **atomically yet wrongly from a business standpoint**.

### 11.3. Audit ID and idempotency

The **_id = transferId** field on audit serves as the identifying key for a transfer. Inside the transaction, the code checks whether transferId already exists and validates its details. If a request with the same transferId is repeated after a successful commit, the code does not debit/credit again.

However, with **two concurrent requests sharing the same transferId**, one request may encounter a write conflict or duplicate key when both try to insert the audit record; handling must rely on the transaction outcome and re-checking state. This is **one part of idempotency design**, not a guarantee that all network errors have been solved.

In a real payment system, you also need to define global/tenant uniqueness, request signatures, handling of side effects outside MongoDB, and already-processed events.

### 11.4. Transaction callbacks can run again

Helpers such as **withTransaction** support handling retryable transaction errors. The callback can be invoked again after a **transient transaction error**. Therefore:

- **Do not send emails, call payment gateways, or produce external side effects directly inside the callback** if they are not idempotent.
- Do not rely on a local counter incremented inside the callback as proof that "the callback runs only once."
- MongoDB operations inside the callback must use the session and remain consistent with the retry mechanism.
- **UnknownTransactionCommitResult** must be handled properly so you do not start a new transaction that transfers money a second time.

The **fixed transferId** pattern is only a starting point. For production, consult the driver/version documentation, unknown commit states, and reconciliation strategies.

### 11.5. Why not put an entire large workflow into a transaction?

Multi-document transactions have operational limits on duration, resources, contention, and abort behavior; default thresholds may vary by deployment configuration. Do not bundle millions of documents into one giant transaction just to avoid designing checkpoints.

If a process must update millions of records and can run for minutes or hours, it typically needs to be split into business units that can be **retried**, **resumed**, and **reconciled**. Transactions fit small groups of documents that must commit together, not as a replacement for every batch job.

## 12. Isolation, snapshots, and conflict types

### 12.1. Atomicity and isolation are not the same

Distinguish between:

- **Single-document atomicity:** an update on a document does not expose a state where only half the fields of that command were updated.
- **Transaction isolation:** reads and writes inside a transaction are observed according to transaction read/write rules and read concern.
- **Serializability:** a stronger guarantee where transactions produce outcomes equivalent to some serial execution order in all considered scenarios.

Do not assume **snapshot isolation** guarantees **serializability** for every invariant across multiple documents. Some constraints may require **writing to a shared guardian document**, unique indexes, write conditions, or appropriate transaction/application-level locking design.

### 12.2. Write conflicts

If two transactions simultaneously attempt to modify the same document, MongoDB can detect a **write conflict**, aborting one transaction or requiring a retry under supported mechanisms. This avoids certain invalid overlapping writes but can increase latency and retry rates on hot documents.

For example, multiple workers updating the same stock document:

~~~text
Transaction A: reads stock, intends to update sku-001
Transaction B: reads stock, intends to update sku-001

When both attempt to write the same document, a write conflict can occur.
The application must handle aborts/bounded retries and idempotency.
~~~

Do not retry indefinitely when many clients contend on a single document. You may need backoff, queuing, or data model changes to reduce hot spots.

### 12.3. Write skew across multiple documents

Suppose a policy requires **at least one on-call employee**. There are two employee documents A and B, both with onCall = true. Two transactions can concurrently observe that the other employee is still on call, and then each transaction modifies **a different document** to onCall = false. Relying only on snapshots without creating a forced conflict point on the same document can violate the **at least one on-call** invariant in isolation models that allow write skew.

Remediation depends on the system:

- Place the team's on-call state in **a single document** and update conditionally.
- Write to a shared **guardian/version document** to create a controlled contention point.
- Design data constraints or an update protocol aligned with the desired isolation level.

This example is raised as a reminder that **transactions are a tool, not magic that automatically proves every business rule**.

## 13. Document boundaries when designing schemas

### 13.1. Embedding can group an invariant into one document

Suppose inventory counts consist of:

~~~javascript
{
  _id: "sku-001",
  available: 2,
  reserved: 0,
  reservations: []
}
~~~

A single updateOne can preserve the invariant **available + reserved = 2** when moving one unit from available to reserved:

~~~javascript
db.inventory.updateOne(
  { _id: "sku-001", available: { $gte: 1 } },
  {
    $inc: {
      available: -1,
      reserved: 1
    }
  }
);
~~~

Both fields reside in **the same document**, so the application will not see available decremented without reserved incremented within the scope of that update.

If available and reserved were split into two independent documents, preserving a constant sum becomes harder and may require transactions.

### 13.2. But do not embed unboundedly just to "get atomicity"

A MongoDB document has a **16 MiB BSON** limit. If you embed millions of transactions or reservations into one document:

- The document can grow very large.
- All updates contend on the same hot document.
- Pagination or querying individual items becomes difficult.
- Differences in item lifecycles and retention are obscured.

Therefore, **single-document atomicity is one design factor**, not a reason to cram the entire system into a single document.

### 13.3. Common scenarios

| Invariant/requirement | Can it live in one document? | When another approach is needed |
| --- | --- | --- |
| Status, paidAt, reference of an Order | Yes, usually appropriate | When Payment/Audit in another collection must be written atomically together |
| available/reserved of a SKU | Yes, if sharing lifecycle and reasonable update rate | If inventory is partitioned across multiple warehouses/documents |
| Adding a tag to a Product array | Yes | When tags grow unboundedly or update independently |
| Money transfer A → B | No, if the two wallets are two documents | Transaction or ledger/other business protocol |
| Deleting a User and all related data | Usually spans multiple collections | Small-scope transaction, saga, or checkpointed job |
| Writing an Order together with a Payment record | May span multiple documents | Transaction when they must commit together in MongoDB |
| Sending an email after Order commit | Not a MongoDB operation | Outbox pattern, queue, and idempotent consumer |

## 14. Unique indexes and atomicity: do not check-then-insert

### 14.1. Race condition in checking existence before inserting

Error-prone pattern:

~~~javascript
if (!db.users.findOne({ email: "a@example.com" })) {
  db.users.insertOne({ email: "a@example.com" });
}
~~~

Two requests can both fail to find the email and both insert. Each **insertOne** is single-document atomic, but **"only one unique email may exist"** is an invariant **across multiple documents**.

**A unique index** is the proper way for MongoDB to enforce uniqueness at the storage level for the indexed key:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true, name: "ux_tenant_email_normalized" }
);
~~~

The application normalizes the email and handles **duplicate key errors**, rather than relying solely on a prior findOne check. For multi-tenant applications, the unique key definition must reflect the actual intended scope; consider null/missing values and sharding if applicable.

### 14.2. Unique indexes do not replace transactions

A unique index protects a specific kind of invariant on **keys**, but it does not simultaneously transfer money between two wallets, write an audit log, and send a notification. When choosing a solution:

- **Conditional filters** for single-document invariants.
- **Unique indexes** for cross-document uniqueness.
- **Transactions** for groups of MongoDB operations that must commit together.
- **Outbox/saga/idempotency** for workflows spanning multiple systems.

Each tool solves a different class of problems.

## 15. Write concern, read concern, and data durability

### 15.1. An atomic update can be acknowledged at different levels

Atomicity does not answer the question "has the change been durably persisted across failover?". That is the role of **write concern**.

For example:

~~~javascript
db.getSiblingDB("mongo_atomic_lab")
  .getCollection("lab_orders")
  .updateOne(
    {
      _id: "order-101",
      dataset: "atomicity-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: { status: "pending" }
    },
    {
      writeConcern: {
        w: "majority",
        wtimeout: 5000
      }
    }
  );
~~~

With a suitable **replica set**, majority requires write acknowledgment from a majority of data-bearing members according to MongoDB's mechanism. When receiving a **write concern timeout/error**, the operation may already have changed state on the server without being acknowledged to the requested level; **do not conclude with certainty that "it was not written"** without reconciliation.

Depending on topology, standalone mode, and deployment configuration, write concern behavior may differ; verify it before applying the pattern in production.

### 15.2. Read concern is a different concern

Read concern levels such as **local**, **majority**, and **snapshot** are used in different contexts. They control the properties of data read; they do not turn multiple independent updateOne calls into a transaction.

For example, using majority read concern does not make a two-step money transfer all-or-nothing. If logic needs to observe **a consistent state across two wallets**, you must design appropriate transactions/reads.

### 15.3. Do not confuse atomicity with exactly-once

An **$inc** operation on a single document is atomic. But if a client sends the same request twice because a user clicks twice or a request is manually retried, $inc can take effect **twice**.

In environments supporting driver/session **retryable writes**, eligible single-document operations can be retried automatically with a mechanism that avoids repeating the effect of **the same statement**. That does not mean every resubmitted HTTP request creating a new workflow is recognized as the same event.

To achieve "each payment/transfer applies only once," you need a **business idempotency key**, data constraints, and state reconciliation after uncertain errors.

## 16. Writing data and side effects outside MongoDB

### 16.1. Transactions do not cover email systems or payment gateways

Suppose a transaction commits setting Order status to paid and inserting a Payment record. Then the application calls an email service to send a receipt. If the email service fails, **the already-committed MongoDB transaction does not automatically roll back**.

Do not call a non-idempotent service inside a transaction callback: the callback can retry, and external side effects are outside MongoDB's commit/abort.

### 16.2. Transactional outbox

A common approach:

~~~text
Inside a MongoDB transaction:
  1) Update Order -> paid
  2) Insert Payment
  3) Insert OutboxEvent: "SendReceipt"
  COMMIT

Separate worker:
  4) Read unprocessed OutboxEvent
  5) Send email
  6) Mark result; retry with idempotency
~~~

Order/Payment/OutboxEvent can commit together in MongoDB, though **the email may arrive later**. The consumer must tolerate redelivery (at-least-once delivery) and use idempotency when the goal is avoiding duplicate emails.

Outbox does not create a distributed transaction between MongoDB and the email service; it enables durable, retryable business synchronization.

### 16.3. Sagas and compensation

If a workflow spans multiple services (ordering, payment, inventory, shipping) and cannot place all steps in a single database transaction, a **saga** may be needed:

~~~text
ReserveStock
  -> ChargePayment
     -> CreateShipment
        -> on failure, run appropriate compensating steps
~~~

Compensation is not storage-level atomic rollback: earlier steps may already have been observed externally, and compensation itself can fail. States and retries must be modeled explicitly.

## 17. Sharded clusters and atomicity scope

### 17.1. A single document remains the fundamental boundary

In a sharded collection, a document lives at a location routed by the shard key and cluster rules. A conditional write on a single document still has single-document atomicity, though performance and routing depend on the filter/shard key and server version.

Do not infer from single-document atomicity that **an updateMany across multiple shards** is atomic across the cluster.

### 17.2. Cross-shard transactions

MongoDB supports distributed transactions on sharded clusters subject to deployment requirements. They incur additional coordination, networking, and error-handling overhead. When designing:

- Choose shard keys and access patterns that minimize unnecessary distributed queries.
- Do not assume cross-shard transactions have the same cost as single-document updates.
- Use appropriate timeouts/budgets and monitor transaction aborts/write conflicts.
- Consider placing fields tied to the same invariant in the same document if scale and read paths permit.

Rules regarding transactions, sharding, and server versions must be checked against the MongoDB Manual for the running version before deploying to production.

## 18. Failure patterns and prevention

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Two withdrawals of 1,000 and 2,000 only deduct 2,000 | Both requests read the same stale value then $set | Use $inc or version + conditional update |
| Negative balance after two withdrawal requests | Negative $inc without checking sufficient balance in filter | Add balance >= amount to the update filter |
| Payment status is paid but paymentReference is missing | Two fields modified by two separate updates | Combine in one updateOne if in the same document |
| updateMany stops midway, only some orders change status | Not atomic across the whole document set | Transaction when all-or-nothing is needed, or idempotent batch |
| bulkWrite ordered=true still leaves earlier updates on error | Ordered is not a transaction | Handle partial success or use a transaction |
| Transfer only debited the source wallet | Two independent updateOne calls, crash in between | Multi-document transaction or compensating protocol |
| Transaction still commits a negative balance | Missing business condition in filter | Check the invariant directly in the write operation |
| Two users create duplicate email | Unsynchronized check-then-insert | Unique index and duplicate key handling |
| Version fails to catch another update | Some writers forget to increment/check version | Enforce a uniform contract across all write paths |
| findOneAndUpdate claims job yet job is processed twice | Worker crashes/retries after claim, external side effects | Lease/queue protocol and idempotency |
| Transaction callback sends email twice | Callback can retry after transient errors | Do not place non-idempotent side effects inside callback |
| Write times out, client manually retries $inc | Unknown whether the write occurred | Use appropriate retryable writes and business idempotency key |
| Snapshot transaction still violates two-document invariant | Write skew, no shared contending write point | Guardian doc, constraints, or proper transaction model |
| Many write conflicts on one stock document | Hot document under high contention | Limit concurrency, backoff, or partition data |
| Read between two transfer writes sees total wallet sum change | No transaction across the two documents | Transaction or suitable ledger model |
| Transaction on standalone fails | Topology does not support multi-document transactions | Use a suitable replica set/sharded cluster |
| Oversized transaction frequently aborts | Holds resources long, contention, or exceeds limits | Shrink transaction boundary; batch/resume |
| Atomic update done yet data lost after failover | Atomicity differs from durability/acknowledgment | Configure suitable write concern and recovery |

## 19. Practice exercises

### Exercise 1 — Transitioning an Order status

After seeding, use **updateOne** to transition order-101 from draft to paid while updating paidAt, paymentReference, and version. Run it a second time. Explain matchedCount in both runs and why there is no state where "paid is set while only one of the three fields was written" from that update itself.

### Exercise 2 — Simulating a lost update

Have two clients A and B both read wallet-a's balanceCents as 10,000. A wants to withdraw 1,000, B wants to withdraw 2,000. Simulate two **$set** commands based on stale snapshots. Why can the result be 8,000 instead of 7,000 even though both updates are atomic?

### Exercise 3 — Fixing lost updates with $inc

Re-run the seed and execute two **$inc** operations of -1,000 and -2,000 on the same wallet. Predict the final balance. When is $inc more suitable than read–compute–$set? If one withdrawal is submitted twice, what else is needed?

### Exercise 4 — Guarding non-negativity

Write an updateOne to withdraw 8,000 cents from wallet-a when only 7,000 remain. The filter must include the condition balanceCents >= amount. Record matchedCount, modifiedCount, and the final balance. Explain why running a find first to check funds and then updating still has a race condition.

### Exercise 5 — Optimistic concurrency

Two people both read order-101 at version 0 and each edits shippingNote. Use a version filter in updateOne and $inc version. Predict matchedCount of the second command and how to respond to the conflict at the HTTP/API layer.

### Exercise 6 — Atomic Array update

On sku-001 with available=2 and reserved=0, write one updateOne to move 1 unit to reserved while adding reservationId to the Array. When run again with the same reservationId, does $addToSet prevent $inc from running again? Propose a filter or idempotency mechanism to avoid duplicate reservations.

### Exercise 7 — Claiming a job with findOneAndUpdate

Use pending order-103 to simulate a worker claiming a job. After claiming, run the same command again to see if a result is returned. If the worker crashes after claiming but before processing, what must the workflow add?

### Exercise 8 — updateMany is not a transaction

Run updateMany to change both draft orders of t001 to pending. Explain how atomicity applies to each order, and what can happen if the command is interrupted after only one document is processed. Under what circumstances can this be solved with a transaction?

### Exercise 9 — Transferring money between two wallets

Draw a diagram of two updateOne calls: debit wallet-a 3,000 and credit wallet-b 3,000. Point out the intermediate state after the debit step. Then write transaction pseudocode ensuring debit, credit, and audit commit together or abort together.

### Exercise 10 — Analyzing a Node.js transaction

In the transferOnce example, remove **{session}** from the credit operation. What dangerous outcome can happen if the transaction aborts afterward? Why must the code check matchedCount on debit/credit and throw when invalid?

### Exercise 11 — Transaction callback retry

If the withTransaction callback is re-executed after a transient error, what consequences can sending an email inside the callback cause? Propose a transactional outbox to emit notifications after commit.

### Exercise 12 — Unique index

Two requests both check that an email does not exist and then insert two documents. Why does each atomic insertOne still fail to guarantee a unique email? Write a unique index on tenantId/emailNormalized and describe how to handle duplicate key errors.

### Exercise 13 — Snapshots and write skew

Two employees A/B both have onCall=true, and the system requires at least one person on call. What issue can two transactions encounter if each modifies a different document based on the initial snapshot? Propose a guardian document and conditional write to protect the invariant.

### Exercise 14 — Designing document boundaries

Classify these scenarios: updating status/paidAt of an Order, transferring available/reserved inventory, transferring money between two Wallets, deleting a User along with Orders, sending an email when Order is paid. Choose an appropriate single-document update, transaction, unique index, outbox, or saga and explain the trade-offs.

### Exercise 15 — Unknown result and retries

A client sends a withdrawal command using $inc, but the connection drops before receiving a response. What states could have occurred? Why must you not blindly resend a new $inc without an idempotency mechanism? Distinguish driver retryable writes from resubmitting a new HTTP request.

### Exercise 16 — Observing write conflicts

Suppose a very popular SKU is updated thousands of times per second. Design an experiment measuring **matchedCount**, write latency, conflict/retry frequency, and contention level. Propose two data model or processing flow changes to reduce the hot spot without losing the inventory invariant.

## 20. Official references

- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/).
- MongoDB Manual — [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/).
- MongoDB Manual — [db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/).
- MongoDB Manual — [db.collection.findOneAndUpdate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/).
- MongoDB Manual — [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/).
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Node.js Driver — [Transactions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/).

**Conclusion:** MongoDB guarantees that **a write operation on a single document is atomic**, even when modifying multiple fields or Array elements. That does not automatically prevent **lost updates**, **overdrafts**, or **duplicate requests** if the application uses read–modify–write and filters without conditions. Use **$inc, conditional updates, version, and findOneAndUpdate** to protect invariants residing within a single document. Across multiple documents, **updateMany, deleteMany, and bulkWrite are not all-or-nothing by default**; when shared commit/abort is required, use **multi-document transactions** with sessions, business checks, and proper error/retry handling. Designing document boundaries around invariants, lifecycles, and concurrency load is the key to achieving correctness without paying unnecessary transaction overhead.
