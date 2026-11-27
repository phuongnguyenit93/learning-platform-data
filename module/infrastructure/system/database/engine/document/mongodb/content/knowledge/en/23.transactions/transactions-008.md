# Long Transactions, Write Conflicts, and Resource Impact in MongoDB

## 1. Opening Scenario: A Transaction Holding State Too Long

Suppose a ticketing application structures an operation in three steps:

1. Read remaining ticket inventory.
2. Deduct one ticket from stock.
3. Create an order and a payment record.

The development team wants all three steps to **succeed or fail together**, so they use a **multi-document transaction**. This is a reasonable choice if the business invariant genuinely spans multiple documents. However, the first version implements:

```text
BEGIN TRANSACTION
    |
    +-- read inventory
    |
    +-- call external payment gateway (waits 35 seconds)
    |
    +-- wait for fraud-check service (waits 20 seconds)
    |
    +-- update inventory
    |
    +-- insert order
    |
COMMIT
```

This transaction can suffer several problems:

- While waiting on the network, it stays alive in MongoDB and consumes transaction-state resources.
- Its read snapshot becomes stale while other writers keep modifying data.
- When updating the inventory document already modified by another transaction, it can hit a **write conflict** and abort.
- The transaction can be terminated due to **excessive lifetime**, cache exhaustion, lock acquisition failures, or topology changes.
- If the transaction callback retries automatically, calling the payment gateway inside the callback risks **executing external side effects multiple times**.

Therefore, the goal is not merely “using a transaction so everything is atomic”, but designing **short transactions with clear boundaries, proper concurrency handling, and zero wasted resource holds**.

This lesson **“Long Transactions, Write Conflicts, and Resource Impact”** belongs to the **Transactions** chapter of MongoDB. After this lesson, you will be able to:

- Explain multi-document transactions and when to use or avoid them.
- Distinguish **write conflicts**, **lock waits**, **transaction timeouts**, and **unknown commit results**.
- Understand why long transactions raise snapshot, cache, version history, and lock management costs.
- Write short transactions in `mongosh` and the Node.js driver.
- Handle retries using **error labels**, separating full-transaction retries from commit retries.
- Design idempotency and move external service calls out of transaction callbacks.
- Monitor open transactions, aborted transactions, and resource bottleneck indicators.
- Establish a remediation runbook when a cluster exhibits excessive long transactions or high write-conflict rates.

## 2. What Can Multi-Document Transactions Do?

### 2.1. Atomicity and Transaction Boundaries

MongoDB already guarantees **atomicity for a write operation on a single document**. When a request only updates fields of one document, you can often use `updateOne()` directly with conditional filters and operators such as `$inc`, `$set`, and `$addToSet`.

Multi-document transactions are used when multiple operations across multiple documents or collections must share an **all-or-nothing** boundary within MongoDB-supported scope:

```text
BEGIN TRANSACTION
    |
    +-- write account A: -100
    +-- write account B: +100
    +-- insert ledger entry
    |
    +-- all valid? --> COMMIT
    |
    +-- error? ------> ABORT / ROLLBACK
```

If the transaction aborts, its uncommitted changes do not become final persisted data. If commit succeeds per the requested acknowledgment level, operations inside the transaction apply atomically per MongoDB semantics.

A transaction **cannot automatically roll back sent emails, external HTTP calls, captured payment gateway charges, or events published to another system**. Those side effects require a different coordination architecture.

### 2.2. Sessions, Transactions, and Commits

With MongoDB drivers, a transaction runs inside a **client session**. Conceptual flow:

```text
startSession()
      |
startTransaction()
      |
  operation A
  operation B
  operation C
      |
commitTransaction()  or  abortTransaction()
      |
endSession()
```

Points to remember:

1. Every command belonging to the transaction must pass **the same session**.
2. A session can outlive a single transaction; do not conflate the two lifecycles.
3. Always commit or abort, then close the session per the driver API.
4. Never run multiple operations concurrently inside one transaction using `Promise.all()` or similar mechanisms when unsupported by the driver; follow a clear sequential order.
5. Never treat an open transaction as a place to wait for user confirmation or a slow external service.

### 2.3. Transactions Can Read from a Snapshot

When using `readConcern: { level: "snapshot" }` in a transaction, reads inside the transaction operate on a consistent snapshot per deployment semantics. Meanwhile, other transactions and requests can continue writing externally.

```text
T0: transaction A starts and reads snapshot, balance=100
T1: transaction B updates balance=80 and commits
T2: transaction A still holds its earlier snapshot context
T3: A tries to write balance based on stale data
    -> may hit a write conflict and abort
```

A snapshot does not mean MongoDB places an **exclusive read lock on every read document** for the duration of the transaction. It provides a consistent view, yet concurrent modifications can trigger conflicts when A attempts to write.

### 2.4. Snapshot Isolation Does Not Replace Every Business Invariant

Even when two transactions read from snapshots and each successfully writes to **different documents**, a rule spanning multiple documents can still be violated without proper enforcement. This is the class of anomalies known as *write skew* under snapshot isolation.

For example, two on-call doctors have two separate documents. Each transaction reads “at least two people on call” and sets **its own document** to `offDuty`. If neither writes to a shared document and no extra constraint exists, both can decide based on the old snapshot, risking **zero doctors left on call**.

To protect this invariant, force contention on a shared state record, validate and update properly inside the transaction, or adopt another suitable data model/constraint. Never assume a transaction serializes every cross-document condition automatically.

## 3. When Is a Transaction Considered “Long”?

There is no universal millisecond threshold for every system. “Long” can mean:

- A few seconds for an interactive API that should only update two documents.
- Tens of seconds when a transaction scans huge amounts of data.
- A transaction pinning a snapshot longer than the churn rate storage/cache can sustain steadily.
- A transaction approaching or exceeding the server's configured **transaction lifetime limit**.

Impact depends on **both duration and workload size**. A read-only transaction left open too long strains snapshot retention; a transaction modifying tens of thousands of documents can hit resource pressure even before reaching the time threshold.

### 3.1. Duration in Time

```text
Short transaction:

BEGIN -> validate with prepared data -> 2 updates -> COMMIT
         [typically completes in a brief window]

Long transaction:

BEGIN -> large query -> loop -> HTTP call -> wait -> updates -> COMMIT
         [multiple waits + large data volume]
```

A practical operational rule:

> Prepare inputs and invoke external services **outside the transaction** whenever possible. Keep inside the transaction only the MongoDB commands that truly must commit together, plus the data checks that must execute against a consistent state.

### 3.2. Size in Resources

A transaction can be short in wall-clock time yet **very heavy**:

- Scanning many documents or missing proper indexes.
- Writing a massive number of documents.
- Performing many updates on contended documents.
- Touching many shards, collections, or namespaces.
- Forcing retention of many data versions due to pinned snapshots.

In these cases, merely raising the allowed transaction lifetime rarely solves the root problem.

## 4. Impact of Long Transactions on MongoDB Resources

### 4.1. Pinning Snapshots and Data Version History

MongoDB with the WiredTiger storage engine uses snapshot and multi-version data management. A long-lived transaction pins an **old snapshot point**, requiring the engine to preserve historical versions needed by active readers.

Illustration:

```text
T0              T1              T2              T3
|---------------|---------------|---------------|
   Txn A reads snapshot T0
   |-------------------------------------------|
      other writers keep modifying documents
            |        |           |
            v        v           v
         version 2  version 3   version 4

While snapshot T0 is still needed, the engine must retain
the ability to serve old state rather than discarding all history immediately.
```

The impact can appear as **WiredTiger cache pressure**, version history buildup, eviction load, dirty pages, and degraded read/write throughput. Exact internals depend on MongoDB version, workload, and storage engine; never assume “a transaction keeps a full copy of the entire database in RAM”.

### 4.2. Cache Pressure and Transaction Size Errors

If a transaction generates or buffers too many uncommitted changes, the system can experience cache pressure, eviction stalls, or errors such as **`TransactionTooLargeForCache`** in supporting versions.

Principles:

- Larger transactions modifying more documents/bytes generally incur higher costs.
- Never use a single transaction to update millions of documents by default.
- Split a batch across multiple small transactions **only when the business allows splitting atomicity**.
- For cache-size failures, retrying the exact same payload without shrinking the work rarely helps.
- Inspect real metrics rather than blindly increasing `WiredTiger` cache size.

A transaction does not have an “exact 16 MB limit for **all** data” as described under older oplog mechanisms. Modern MongoDB can emit multiple oplog entries per transaction; BSON document limits and other resource/time limits still apply. Verify your deployment version before assuming operation or byte capacities.

### 4.3. Locks and Resource Contention

MongoDB does not acquire a **global exclusive lock across the entire database** for every transaction. Locking operates across multiple levels alongside storage engine document/record concurrency control and intent locks.

However, a transaction can:

- Hold certain locks/resources until the transaction finishes.
- Contend with other transactions modifying the same documents or accessing metadata.
- Wait for a required lock within configured time budgets.
- Abort due to failing to acquire a lock or hitting a write conflict.
- Extend how long session/transaction-related resources stay occupied.

**Lock waits** and **write conflicts** are related yet distinct situations. A lock wait may finish with success or a timeout. A write conflict aborts the transaction and calls for a retry decision.

### 4.4. Connections, Sessions, and Open Transaction Counts

Transactions use sessions and execution resources appropriate to the topology. Many open or idle transactions strain:

- Application connection pools and session lifecycles.
- Server-side transaction tracking structures.
- Snapshots/cache and version history.
- Capacity to serve new transactions when many compete.

Never assume a transaction **pins a connection identically across every driver and topology**. Pinning and server selection mechanics vary between replica sets and sharded clusters, driver versions, and operation types. Applications must still guarantee zero leaked transactions or sessions.

### 4.5. Replication, Oplog, and Commit

Transaction modifications flow into write/oplog mechanisms and replication per MongoDB semantics. A large transaction can emit many oplog entries and impose apply overhead on secondaries.

When a transaction commits:

- The server must finalize the work for all changes in the transaction.
- Write concerns like `"majority"` make the client wait for acknowledgment per replica set configuration.
- Secondaries may face significant apply load.
- There is no rule that every transaction produces only **one** oplog entry.

**Slow commits** are not necessarily write conflicts. Inspect operation execution time, replication/majority acknowledgment, network latency, and storage resources separately.

### 4.6. A Diagnostic Summary Table

| Symptom | Possible Cause | Further Investigation |
| --- | --- | --- |
| Many `open` or `active` transactions | Long transaction lifecycles, session leaks, or high load | Duration, operation types, application sources |
| Rising abort rate | Write conflicts, timeouts, locks, resource exhaustion, or other errors | Error codes/labels and server logs |
| Rising cache pressure and eviction | Pinned snapshots/history, heavy reads/writes, peer workloads | WiredTiger metrics and transaction duration |
| Rising write P95/P99 latency | Lock contention, I/O, CPU, replication | Command monitoring, disk, `serverStatus` |
| High `WriteConflict` count | Multiple writers contending on documents or indexes | Query patterns, hot keys, retries |
| Transaction lifetime exceeded | Transaction open too long | External waits, heavy queries, timeouts |
| High commit latency | Majority replication, disk, network, topology | Write concern, replication lag, logs |
| `TransactionTooLargeForCache` error | Transaction exceeded cache capacity for buffered changes | Transaction size, batch design |

These are **signals to correlate**. Rising cache usage alone does not prove long transactions are the sole cause; many other workloads share the cache.

## 5. What Is a Write Conflict?

### 5.1. Two Transactions Trying to Modify One Document

Suppose we have a document:

```javascript
{
  _id: "SKU-100",
  available: 10,
  version: 1
}
```

Transactions A and B both read the initial state. B updates the quantity and commits before A attempts to write:

```text
T0: A starts; reads snapshot available = 10
T1: B updates available = 8 and commits
T2: A tries to update available = 7 on that document
    |
    v
MongoDB detects A cannot safely apply the write
against the stale snapshot -> returns WriteConflict / aborts transaction.
```

Without protection, A could overwrite B's change. MongoDB's concurrency control prevents writing on top of an invalidated version while pretending everything succeeded.

### 5.2. Error Codes and Error Labels

A write conflict typically surfaces with an error name like **`WriteConflict`**, commonly MongoDB code **`112`**. Inside a transaction, the driver may receive the **`TransientTransactionError`** label for transient errors eligible for retry.

Illustrative error shape:

```javascript
{
  code: 112,
  codeName: "WriteConflict",
  errorLabels: ["TransientTransactionError"]
}
```

This is an **illustration**; not every write conflict has identical fields, messages, or labels across every version and driver.

Rely on **error labels provided by the driver/server** to drive retry policies, and log codes with context. Never retry blindly using string matching like `error.message.includes("write conflict")`.

### 5.3. Write Conflicts Are Not Duplicate Keys

If two requests attempt to insert the same business key backed by a unique index:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

the second request may receive **`E11000` / code 11000 (`DuplicateKey`)**. This is not the same class as **`WriteConflict` (112)**.

Key difference:

- **Write conflict**: a write plan inside a transaction collides with concurrent changes and may be suitable for retrying the transaction on a fresh snapshot.
- **Duplicate key**: the data/key being written violates a uniqueness constraint; without changing the key or policy, retrying the same payload usually fails again.

Never turn a duplicate key into an infinite retry. Reconcile by business key or return an appropriate conflict error.

### 5.4. Write Conflicts Are Not Lock Timeouts

A transaction may fail to acquire a lock within its configured wait window and throw a different error than `WriteConflict`. MongoDB provides parameters like `maxTransactionLockRequestTimeoutMillis` in supporting environments/versions, specifying how long a transaction waits for needed locks.

Setting a higher timeout may reduce lock-wait errors in some scenarios, yet also **extends wait queues and resource holds**. Never tweak this parameter to “fix” all write contention without identifying the root cause.

### 5.5. Contention from Outside Transactions

Conflicts are not limited to two transactions. An ordinary write outside any transaction can modify a document a transaction already read, preventing the transaction from writing safely against its snapshot.

```text
Transaction A:   reads document X in old snapshot
Writer B:        updateOne(X), commits
Transaction A:   updateOne(X) under A's snapshot
                 -> write conflict can occur
```

This is useful for simulating write conflicts in a controlled way **on a dedicated test document** without running two large concurrent processes.

## 6. Time and Size Limits to Know

### 6.1. `transactionLifetimeLimitSeconds`

MongoDB provides **`transactionLifetimeLimitSeconds`** to cap the lifetime of multi-document transactions. In many self-managed `mongod` configurations, the common default is **60 seconds**, though actual defaults vary by version and service.

When a transaction stays open too long, expired-transaction cleanup can **abort** it. If a transaction is looping or waiting on external tasks, “waiting just a bit longer” can discard all uncommitted work.

In sharded clusters, configuring and synchronizing lifetime parameters may require consistent cluster-wide administration. Managed services may restrict direct edits.

Never treat 60 seconds as a “target budget to spend”. An API with a 200 ms SLA should keep transactions orders of magnitude shorter, even if the server allows 60 seconds.

### 6.2. Inspecting Parameters When Authorized

In an authorized environment, a DBA can check:

```javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
});
```

To inspect the lock wait parameter when supported by the server:

```javascript
db.adminCommand({
  getParameter: 1,
  maxTransactionLockRequestTimeoutMillis: 1
});
```

These are **read-only configuration queries**, not server modifications. If you encounter permission errors or unsupported parameters in your version, do not escalate privileges or alter settings on your own.

### 6.3. Do Not Raise Limits as Your First Remedy

Before modifying `transactionLifetimeLimitSeconds`:

1. Why is the transaction taking so long?
2. Are queries doing `COLLSCAN` or scanning huge document counts?
3. Are HTTP calls, queue waits, or user inputs sitting inside the transaction?
4. Is a massive batch being processed without needing whole-batch atomicity?
5. Are repeated write conflicts hitting a hot document?
6. Do storage and cache still have headroom?

Raising lifetime lets long transactions **stay alive longer and impose heavier resource pressure**, rather than organically increasing throughput.

### 6.4. Document Limits and Other Constraints

MongoDB still enforces **16 MiB per BSON document**. A transaction can span multiple operations and use version-dependent oplog encoding, yet no single document can grow arbitrarily large.

Also account for limits on:

- Permitted operations inside transactions.
- DDL and namespace restrictions.
- WiredTiger cache size and pressure.
- Transaction duration and lock wait limits.
- Multi-shard transactions.
- MongoDB/driver version and write concern settings.

**Never treat a limit from an old MongoDB version as an immutable rule across every newer release.**

## 7. Safe Example: Simulating a Write Conflict in `mongosh`

### 7.1. Lab Prerequisites

This example requires a **transaction-capable MongoDB replica set or sharded cluster**, not an ordinary standalone `mongod`. Run only on a test database and dedicated document you created—never deliberately create contention on production data.

To connect to a local test replica set:

```bash
mongosh "mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/?replicaSet=rs0"
```

Adjust the URI for your actual environment and credentials.

### 7.2. Creating a Test Document

In `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_tx_row252_lab");
const inventory = lab.getCollection("inventory_demo");

const runId = "row252-" + new ObjectId().toHexString();
const skuId = new ObjectId();

inventory.insertOne({
  _id: skuId,
  runId,
  sku: "ROW252-ITEM",
  available: 10,
  revision: 1,
  updatedAt: new Date()
});

print("database=" + lab.getName());
print("runId=" + runId);
printjson(inventory.findOne({ _id: skuId, runId }));
```

We scope everything with `_id` and `runId` so commands touch only the demo document. Never target real inventory collections or guessable IDs.

### 7.3. Intentionally Creating a Conflict on One Test Document

In the **same `mongosh` session**:

```javascript
const session = db.getMongo().startSession();
const txInventory = session
  .getDatabase(lab.getName())
  .getCollection("inventory_demo");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  // Transaction A reads snapshot first.
  const before = txInventory.findOne({
    _id: skuId,
    runId
  });
  printjson({ snapshotRevision: before.revision });

  // Writer B, OUTSIDE transaction A, modifies the exact demo document.
  const outsideResult = inventory.updateOne(
    { _id: skuId, runId },
    {
      $inc: { available: -1, revision: 1 },
      $set: { updatedAt: new Date() }
    }
  );
  printjson({ outsideResult });

  // Transaction A tries to write using the snapshot read before writer B.
  try {
    const insideResult = txInventory.updateOne(
      { _id: skuId, runId },
      {
        $inc: { available: -1, revision: 1 },
        $set: { updatedAt: new Date() }
      }
    );
    printjson({ insideResult });
  } catch (error) {
    print("Transaction write error code: " + error.code);
    print("Message: " + error.message);
    printjson(error.errorLabels ?? []);
  }
} finally {
  // Transaction A does not commit in this demo; always clean up safely.
  try {
    session.abortTransaction();
  } catch (_ignored) {
    // The server may have already aborted the transaction on error.
  }
  session.endSession();
}

printjson(inventory.findOne({ _id: skuId, runId }));
```

Explanation:

- Transaction A pins a snapshot on read.
- Writer B modifies the document **outside A**.
- When A attempts to write against the stale snapshot, MongoDB detects a write conflict and aborts A; the error code typically relates to `WriteConflict`.
- B's update is independent of A, so it **is not rolled back** when A aborts.
- Transaction A **does not commit** in this example, so final state reflects only B's write.

Exact error output depends on server version, timing, topology, and shell. The goal is understanding the conflict mechanism, not matching an exact stderr string across all environments. If an unrelated error appears (topology, authorization, connection), stop and diagnose rather than assuming `WriteConflict`.

### 7.4. Cleaning Up the Demo Document

Before deleting, verify ownership explicitly:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
printjson(
  inventory.findOne(
    { _id: skuId, runId },
    { _id: 1, runId: 1, sku: 1, revision: 1 }
  )
);
```

Once verified as your document:

```javascript
const deleted = inventory.deleteOne({
  _id: skuId,
  runId
});

printjson(deleted);
print("remaining=" + inventory.countDocuments({
  _id: skuId,
  runId
}));
```

Never run `deleteMany({})` or `dropDatabase()` on a shared environment. This transaction demo does not require changing replica set config, deleting oplogs, or forcing elections.

## 8. Short Multi-Document Transaction Example in Node.js

### 8.1. Points Transfer Between Two Wallets

Suppose the application stores:

```javascript
// wallets
{
  _id: ObjectId("66a000000000000000000011"),
  tenantId: "TENANT-A",
  points: 1000
}

{
  _id: ObjectId("66a000000000000000000012"),
  tenantId: "TENANT-A",
  points: 300
}
```

Requirement: transfer 120 points from wallet A to wallet B and insert a ledger entry such that:

1. A never goes negative.
2. A decreases by exactly 120.
3. B increases by exactly 120.
4. The ledger entry is created in the same transaction.

This invariant spans multiple documents. We want a **short** transaction containing only the relevant database commands.

### 8.2. Preparation Before Starting the Transaction

Before starting:

- Verify the caller is authorized to transfer points.
- Parse `amount` into a valid integer greater than 0.
- Resolve tenant and wallet IDs from authenticated context.
- Generate a stable `operationId` for the business request.
- Create a **unique index** on the idempotency/operation ID key in the ledger collection per design.
- Prepare conditions and write values.

Never call payment APIs or wait for user confirmation **inside** the transaction.

### 8.3. Node.js Code with `withTransaction`

Example using the Node.js MongoDB driver, assuming the client is connected, collections/indexes are pre-created, and IDs use matching BSON types:

```javascript
import { MongoClient } from "mongodb";

async function transferPoints({
  client,
  database,
  tenantId,
  fromWalletId,
  toWalletId,
  amount,
  operationId
}) {
  if (!Number.isSafeInteger(amount) || amount <= 0) {
    throw new Error("INVALID_AMOUNT");
  }
  if (fromWalletId.equals(toWalletId)) {
    throw new Error("SAME_WALLET");
  }

  const wallets = database.collection("wallets");
  const ledger = database.collection("transferLedger");
  const session = client.startSession();

  try {
    return await session.withTransaction(
      async () => {
        // Idempotency key must be unique-protected in the database.
        // If operationId already exists, insertOne may throw E11000.
        await ledger.insertOne(
          {
            _id: operationId,
            tenantId,
            fromWalletId,
            toWalletId,
            amount,
            status: "COMPLETED",
            createdAt: new Date()
          },
          { session }
        );

        const debit = await wallets.updateOne(
          {
            _id: fromWalletId,
            tenantId,
            points: { $gte: amount }
          },
          { $inc: { points: -amount } },
          { session }
        );

        if (debit.matchedCount !== 1) {
          throw new Error("INSUFFICIENT_POINTS_OR_WALLET_MISSING");
        }

        const credit = await wallets.updateOne(
          { _id: toWalletId, tenantId },
          { $inc: { points: amount } },
          { session }
        );

        if (credit.matchedCount !== 1) {
          throw new Error("DESTINATION_WALLET_MISSING");
        }

        // Never invoke HTTP, emails, or event publishing here.
        return { operationId, amount };
      },
      {
        readPreference: "primary",
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" }
      }
    );
  } finally {
    await session.endSession();
  }
}
```

**Important assumptions:**

- `points` is stored consistently as a compatible BSON integer type without silent conversion to floating point. For values exceeding JS safe integers, use `Long` or `Decimal128` with proper validation rather than `Number`.
- `operationId` is a stable key for **one transfer**, controlled by the system and protected by a unique index—using `_id` on an unsharded `transferLedger` here, or an equivalent shard-compatible unique design.
- Both wallets belong to the same valid tenant with proper access checks.
- Never treat a duplicate ledger error as “transfer succeeded” before **reconciling the stored record's contents** for that `operationId`.
- If the callback retries, MongoDB writes from the failed prior attempt roll back; external side effects must stay outside the callback.

This pattern intentionally uses **direct conditional updates**. For debiting, `points: {$gte: amount}` checks non-negativity **at write time**, rather than trusting an earlier read from a possibly stale snapshot.

### 8.4. Why Not Read and Then `$set` the Computed Balance?

An approach prone to lost updates:

```javascript
const wallet = await wallets.findOne(
  { _id: fromWalletId },
  { session }
);

await wallets.updateOne(
  { _id: fromWalletId },
  { $set: { points: wallet.points - amount } },
  { session }
);
```

Transactions detect write conflicts, yet computing from a prior snapshot adds unnecessary fragility. Using a **direct atomic conditional update** with `$inc` and checking `matchedCount` is simpler and clearer in this example.

### 8.5. Never Retry by Generating a New `operationId`

If the client misses a response due to a timeout while the transaction committed, calling the function again with a **new `operationId`** can transfer points a second time.

To handle this properly:

- Client/API retains the same operation ID for the same transfer intent.
- Ledger enforces an appropriate unique constraint.
- After an unknown commit error, reconcile the ledger by ID and compare business inputs.
- If the exact operation already committed, return the stored result.
- If no record exists and outcome remains uncertain, follow an explicit recovery/retry policy.

**Transactions guarantee atomicity inside MongoDB; idempotency protects a business intent from executing twice across requests.**

## 9. Retrying Transactions: Transient Errors vs. Unknown Commit Results

### 9.1. Two Important Error Labels

MongoDB drivers expose **error labels** for classification:

| Label | Operational Meaning | Typical Handling |
| --- | --- | --- |
| `TransientTransactionError` | Transaction hit a transient fault before commit finished, e.g., write conflicts or topology errors | Abort old transaction and re-run **the entire transaction** against a fresh snapshot within bounds |
| `UnknownTransactionCommitResult` | Client does not know the outcome of `commitTransaction` (e.g., lost commit response) | Typically **retry commit** per driver mechanics or reconcile; do not immediately re-run business logic |

Not every error carries one of these two labels. **`DuplicateKey`**, validation failures, missing privileges, schema mismatches, or oversized transactions are deterministic errors requiring input/design fixes, not infinite retries.

### 9.2. Why Retry the Whole Transaction on Write Conflicts?

Because Transaction A read an older snapshot, **retrying only the failed update command** inside the failing transaction is insufficient. A transaction snapshot does not refresh to match B's newly committed document.

Correct principle:

```text
Attempt 1:
  start txn -> read old state -> write conflict -> abort

Attempt 2:
  start NEW txn -> read current state -> recompute -> write -> commit
```

If business logic computes prices, stock, or limits from read data, each retry must **recompute** from the fresh attempt's state.

### 9.3. `withTransaction` and Automatic Retries

The MongoDB Node.js driver's `session.withTransaction(callback, options)` manages the transaction lifecycle and driver-defined retries, avoiding manual commit/abort boilerplate.

However:

- The callback may execute **multiple times** across transaction retries.
- Never place non-idempotent external side effects inside the callback.
- Non-retryable errors still surface and must be handled.
- Never wrap an unbounded outer retry loop that piles extra load onto an already contended cluster.
- On timeouts or unknown commits, APIs still need idempotency and business reconciliation.

Every service must enforce **timeouts/deadlines and retry budgets** matching SLAs, rather than holding resources indefinitely under persistent transient errors.

### 9.4. Commit Retries Differ from Body Retries

Suppose:

```text
begin transaction
  debit A
  credit B
commitTransaction() -> MongoDB committed
                    -> response lost
client receives UnknownTransactionCommitResult
```

If the client **re-runs debit/credit as a new business operation**, it can transfer money/points twice. When the driver retries **the commit of that exact transaction**, that is a separate path—it does not initiate a new business operation.

Never write:

```javascript
// Anti-pattern:
try {
  await transferMoney();
} catch (error) {
  // Wrong if response was lost at COMMIT without reconciling:
  await transferMoney(); // Especially dangerous with a new business ID.
}
```

Instead, use a **stable `operationId`**, let the driver handle commit retries where supported, and reconcile afterward when needed.

### 9.5. Excessive Retries Can Make Things Worse

When 200 requests collide on a “hot” document, all hit write conflicts, and all retry immediately:

```text
200 writers
   |
   +-- many write conflicts
   |
   +-- immediate retries
   |
   +-- higher contention
   |
   +-- even more conflicts
```

Consider:

- Bounding attempt counts.
- Jittered backoff.
- Limiting concurrent requests on the same aggregate.
- Queueing or serializing at the application layer if suitable for the domain.
- Redesigning the data model or using atomic operators instead of transactions where sufficient.
- Reducing work inside the transaction.

No single retry count is optimal for every workload.

## 10. Do Optimistic Locking and Transactions Replace Each Other?

### 10.1. Atomic Updates on One Document

In many inventory scenarios, one operation suffices:

```javascript
db.inventory.updateOne(
  {
    _id: skuId,
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2 }
  }
);
```

The predicate **is evaluated atomically at write time**, preventing two writers from silently over-decrementing the same stock count.

If the requirement stays within **one document**, a multi-document transaction adds no extra atomicity benefit.

### 10.2. Optimistic Locking with `version`

Detecting stale form submissions:

```javascript
db.products.updateOne(
  {
    _id: productId,
    version: expectedVersion
  },
  {
    $set: { priceCents: newPriceCents },
    $inc: { version: 1 }
  }
);
```

If `matchedCount:0`, no document matched both ID and version. Distinguish not-found from stale-version if the API returns detailed errors.

This is **compare-and-set (CAS)**, ideal for single-document updates. It does not commit multiple documents atomically together, nor does it require opening a long transaction just to check a version.

### 10.3. Multi-Document Transactions

Transactions fit when business invariants span multiple operations:

```text
Debit A + Credit B + Insert ledger
              |
              v
       one transaction
```

Even with transactions, you may still need:

- Unique indexes on business keys.
- CAS/versioning or state conditions when users edit from stale views.
- Idempotency keys for duplicate requests.
- Transaction retry/abort policies.
- Proper isolation/invariant definitions.

None of these three tools completely replaces the other two.

### 10.4. Decision Table

| Scenario | Usually Appropriate Starting Tool |
| --- | --- |
| Deduct stock in one document if sufficient | `updateOne` with predicate and `$inc` |
| Edit one document from a versioned form | `updateOne` with `version` (CAS) |
| Create order and ledger across two collections atomically | Multi-document transaction |
| Prevent two commands creating the same business ID | Unique index; add idempotency as needed |
| Send email after transaction commits | Transactional outbox / idempotent worker |
| Update one million documents that can be split | Checkpointed batches, not one giant transaction by default |
| Many writers hitting one counter | Atomic update, sharded counter, or contention-aware model |

## 11. Anti-Patterns That Create Long Transactions

### 11.1. Making HTTP Calls Inside Transactions

```javascript
await session.withTransaction(async () => {
  await orders.updateOne(
    { _id: orderId },
    { $set: { status: "PROCESSING" } },
    { session }
  );

  // AVOID: external latency stretches the transaction,
  // and the callback may be retried by the driver.
  await paymentGateway.capture(paymentId);
});
```

The issue is not only slowness:

- If the transaction aborts, the external payment is not automatically refunded.
- If the callback retries, the capture can execute twice.
- The transaction holds resources while waiting on the network.

The typical alternative is **state machine + outbox + idempotent consumer**:

```text
Short transaction:
  update order state
  insert outbox event
  COMMIT
       |
       v
Worker reads outbox (post-commit)
       |
       v
Call paymentGateway with idempotency key
       |
       v
Record outcome via appropriate transaction/update
```

This is an **eventual workflow**; MongoDB and the payment gateway do not become a single distributed atomic transaction. Handle retries, intermediate states, reconciliation, and business compensation.

### 11.2. Waiting on Users Inside Transactions

```text
BEGIN -> create draft -> wait for user to click confirm -> COMMIT
```

This is an anti-pattern. User response times span seconds or hours, far exceeding transaction lifetime and wasting resources.

Alternative:

1. Save draft/quote state independently per business contract.
2. Wait for confirmation **outside the transaction**.
3. Upon confirmation, open a **new** short transaction.
4. Re-verify price, stock, version, and changed preconditions.
5. Commit or return a conflict if conditions no longer hold.

### 11.3. Iterating Large Cursors Inside Transactions

```javascript
await session.withTransaction(async () => {
  // Risk: reading large datasets and looping for a long time.
  const cursor = orders.find(
    { status: "PENDING" },
    { session }
  );
  for await (const order of cursor) {
    await processOrderWithMoreQueries(order, session);
  }
});
```

If whole-batch atomicity is not required, paginate by key with checkpoints and small per-order/group transactions. If whole-batch atomicity is truly mandatory, evaluate alternative patterns (materialized state, staging collections, versioned releases) instead of defaulting to one huge transaction.

### 11.4. Unindexed Queries Inside Transactions

Example inside a transaction:

```javascript
await orders.findOne(
  {
    tenantId,
    externalOrderId
  },
  { session }
);
```

If this API runs thousands of times per second without a suitable index on `{tenantId,externalOrderId}`, queries scan large collections, stretching transaction duration and contention.

A compound index aligned with query patterns and uniqueness constraints (if needed) bounds query time, though each index adds write overhead. Design indexes for real workloads and verify query plans **outside transactions**; never add indexes blindly.

### 11.5. Running Parallel Operations Inside One Transaction

```javascript
// Avoid:
await session.withTransaction(async () => {
  await Promise.all([
    accounts.updateOne(filterA, updateA, { session }),
    accounts.updateOne(filterB, updateB, { session })
  ]);
});
```

The MongoDB Node.js driver does not support running parallel operations inside one transaction like this. Run **sequentially**:

```javascript
await session.withTransaction(async () => {
  await accounts.updateOne(filterA, updateA, { session });
  await accounts.updateOne(filterB, updateB, { session });
});
```

To increase throughput, design concurrency **across independent transactions** with resource bounds and conflict handling—not `Promise.all` on a single session/transaction.

## 12. Monitoring: Where Do Long Transactions Show Up?

### 12.1. `serverStatus().transactions`

When authorized to read metrics:

```javascript
const status = db.serverStatus();

printjson(status.transactions);
```

In supporting versions, this section exposes metrics such as:

- `currentOpen`: currently open transactions.
- `currentActive`: transactions actively executing an operation.
- `currentInactive`: open transactions currently idle between operations.
- `totalStarted`: cumulative transactions started.
- `totalCommitted`: cumulative transactions committed.
- `totalAborted`: cumulative transactions aborted.

Field names and definitions can vary across versions. If a field is absent in one version, do not assume it equals zero. Track **time series** rather than single snapshots.

High `currentInactive` warrants investigation; it often indicates transactions waiting on the application, though workload shapes and measurement nuances can also contribute. Correlate with application traces and transaction durations.

### 12.2. Inspecting Active Operations

Depending on privileges and version:

```javascript
const active = db.currentOp({ active: true });

printjson(active);
```

Under heavy load, output can be large and expose namespaces/queries. In real environments, filter strictly for what you are investigating and avoid logging sensitive data. Some versions support `$currentOp` with transaction/session fields; check syntax for your exact server version.

What to look for:

- Which operations are running long?
- Which session/transaction is involved?
- Which command and namespace is it targeting?
- Is it waiting on locks or showing long inactive intervals?
- Do query durations diverge from total transaction duration?

No single `currentOp` snapshot proves “this request is the sole cause of cache pressure”. Correlate with server metrics.

### 12.3. WiredTiger Cache and Eviction

A high-level diagnostic check:

```javascript
const server = db.serverStatus();

printjson({
  transactions: server.transactions ?? null,
  wiredTigerCache: server.wiredTiger?.cache ?? null
});
```

This is a **read-only diagnostic**. `wiredTiger.cache` contains many fields whose names vary across versions. In production, extract targeted metrics into your monitoring system instead of dumping full cache objects into logs.

If long transactions coincide with rising dirty/eviction pressure, pinned snapshots and write load are suspect—yet indexes, checkpoints, read queries, and other tasks also share the cache.

### 12.4. Application-Layer Tracing

Every critical transaction should emit a correlation ID:

```text
request_id
business_operation_id
transaction_attempt
transaction_duration_ms
db_operations_inside_txn
write_conflict_count
commit_duration_ms
commit_outcome: CONFIRMED / UNKNOWN / FAILED
```

What to record:

- Transaction start and end timestamps.
- Operation group names without logging raw queries containing personal data.
- Retry rates, abort rates, and error labels.
- Batch sizes and touched document counts.
- External service wait times—ideally **outside transactions**.

If using driver command monitoring, scrub sensitive fields before exporting metrics; never log credentials, payment details, or customer payloads.

## 13. Troubleshooting High `WriteConflict` and Transaction Timeouts

### 13.1. Symptom Classification

| Symptom | Causes to Check | Initial Remediation |
| --- | --- | --- |
| `WriteConflict` on same document | Contention / hot key, stale snapshot | Shorten transactions, use atomic updates, reduce concurrency |
| `TransientTransactionError` | Write conflict or other transient error | Retry full transaction within budget; inspect error labels |
| `UnknownTransactionCommitResult` | Unknown commit result | Follow driver commit retry and reconcile `operationId` |
| `TransactionTooLargeForCache` | Excessive buffered changes / snapshot cache | Shrink batches, redesign transactions |
| Transaction lifetime expired | Open too long | Remove waits/HTTP, tune queries, cut operation count |
| Lock acquisition timeout | Waiting too long for locks | Inspect competing operations, metadata/DDL |
| `E11000` | Duplicate unique key | Handle business conflict or idempotency |
| Slow commits | Disk, network, majority write concern | Inspect replication lag and I/O |
| Snapshot too old / history pressure | Long transactions/snapshots, high churn | Shorten duration, investigate cache/history |
| Many inactive transactions | Opened without commit/abort, session leaks | Tracing, `finally` cleanup, audit driver usage |

Before raising retries, check whether retrying actually has **a chance to succeed**. A transaction failing a unique key or invalid input will not fix itself on retry.

### 13.2. Low-Impact Triage Procedure

1. **Confirm errors**: error codes, error labels, operations, durations, and rates.
2. **Identify hot keys**: are many requests updating the exact same account, inventory, or counter document?
3. **Break down duration**: total transaction time vs. individual queries vs. commit.
4. **Check locks/cache**: `serverStatus`, `currentOp`, Atlas/monitoring, disk latency.
5. **Check query plans**: are filters selective and backed by indexes?
6. **Evaluate topology/replication**: is majority commit waiting on lagging secondaries or network links?
7. **Mitigate risk**: throttle batches, cap concurrency, move side effects out, narrow transaction scope.
8. **Verify**: confirm abort/commit rates, P95/P99 latency, and resource metrics improve after changes.

Never impulsively run `killOp`, raise transaction lifetime, disable majority write concern, or reshard collections without an approved runbook—especially in production.

### 13.3. When a Hot Document Causes Contention

Suppose one `dailyCounter` document is updated by thousands of transactions:

```javascript
{
  _id: "daily-2026-11-14",
  count: 123456
}
```

If every transaction updates this document, it becomes a **serialization bottleneck**, even when transactions otherwise touch distinct documents. Consider:

- Moving counter updates outside the transaction using atomic `$inc` if invariants permit.
- Using **bucketed/sharded counters** when aggregating multiple documents fits consistency semantics.
- Queueing or grouping writes by business key.
- Redesigning the model to avoid touching a global document in every transaction.
- If a global invariant must hold, design explicit serialization/locking at one clear point rather than letting every transaction collide randomly.

Sharding a collection does not eliminate write conflicts on **the same document**. Changing a shard key alters data distribution, not concurrency control on a single record.

## 14. Additional Costs of Transactions on Sharded Clusters

### 14.1. Single-Shard vs. Multi-Shard Transactions

In a sharded cluster, a transaction may touch one or multiple shards depending on data placement and routing. Touching multiple shards requires commit coordination so participants commit or abort atomically.

```text
Application
    |
  mongos
    |
    +-------------+
    |             |
    v             v
  Shard A       Shard B
   debit         credit
    |             |
    +---- commit coordination ----+
```

Overhead rises due to inter-component networking, transaction metadata, locking, and commit coordination phases. For co-accessed data, shard key choice and document design influence how many shards participate.

### 14.2. Include the Shard Key in Filters When Appropriate

In a multi-tenant application:

```javascript
{
  _id: orderId,
  tenantId: authenticatedTenantId
}
```

If the collection is sharded by `tenantId`, full filter predicates enable targeted routing and narrow scope. Omitting the shard key can force queries across multiple shards depending on operation and version.

Never assume every multi-shard transaction is slower than every single-shard transaction without measuring—**benchmark** your actual workload. Still, when business invariants fit on one document or one shard, targeted data modeling reduces coordination cost.

### 14.3. DDL, Chunk Migrations, and Version Restrictions

Transactions interact with administrative/DDL operations like creating collections, building indexes, altering structure, and migrating chunks. Supported in-transaction DDL and lock interaction **depend on MongoDB version and deployment type**.

Never keep a long transaction open across a data migration while running arbitrary DDL expecting everything to work smoothly. Schedule schema/index changes relative to transaction workloads, test in production-like environments, and consult version-specific documentation.

## 15. Timeouts: Transaction, Lock, Command, Server Selection, and HTTP

### 15.1. Multiple Timeouts Operate at Different Layers

```text
HTTP request deadline
    |
    +-- driver server selection timeout
    |
    +-- MongoDB command maxTimeMS / socket timeout
    |
    +-- transaction lifetime limit
    |
    +-- transaction lock request timeout
    |
    +-- commit writeConcern wtimeout
```

Never cite a single “30-second timeout” without specifying which layer owns it.

| Timeout / Limit | Scope | Possible Outcome |
| --- | --- | --- |
| HTTP/API deadline | Application request | Client stops waiting, yet DB work may still be running |
| `serverSelectionTimeoutMS` | Driver picking an eligible node | Cannot find primary/secondary within limit |
| `maxTimeMS` or driver deadline | Single command execution where supported | Command may be interrupted per server rules |
| `transactionLifetimeLimitSeconds` | Transaction lifespan | Expired transaction may be aborted |
| `maxTransactionLockRequestTimeoutMillis` | Lock wait inside transaction | Lock timeout / abort depending on scenario |
| `wtimeout` | Waiting for write concern acknowledgment | Write acknowledgment outcome may remain uncertain |

Some timeouts use **milliseconds**, whereas lifetime uses **seconds**. Double-check units when configuring.

### 15.2. A Request Timeout Does Not Mean the Transaction Aborted

If a reverse proxy closes the HTTP request before the MongoDB callback finishes, the backend may still execute the transaction unless cancellation/deadlines are propagated. Design for:

- End-to-end deadline propagation and checks.
- `finally` blocks closing sessions and aborting when safe.
- Preventing background callbacks from blindly writing after clients received errors without idempotency.
- Tracking actual database transaction duration, not just HTTP response times.

Never equate a client disconnect with a guaranteed executed `abortTransaction`.

### 15.3. Commit Timeouts Require Reconciliation

If `commitTransaction` hits a timeout or unknown result:

```text
Database: commit may have completed.
Client:   never received definitive confirmation.
```

This state is **undetermined**, not definitely failed. Use driver commit retries per documentation and reconcile using a business operation ID instead of starting a fresh business transaction with a new key.

## 16. Designing Short Transactions: Practical Patterns

### 16.1. Separate Preparation from the Atomic Boundary

Order creation example:

```text
OUTSIDE TRANSACTION
  - authenticate user
  - validate inputs
  - estimate taxes/fees
  - fetch reference info not needing a pinned snapshot
  - prepare operationId

INSIDE SHORT TRANSACTION
  - check current inventory conditions
  - deduct quantity
  - insert order
  - insert outbox event
  - commit

POST-COMMIT
  - worker dispatches events/notifications
  - call external services with idempotency keys
  - reconcile on errors
```

Data prepared outside the transaction can **become stale** before commit. Any condition critical to correctness (valid pricing, sufficient stock, catalog version, active permissions) must be **re-checked or enforced inside the transaction/atomic write**.

### 16.2. Keep Only Truly Necessary Queries Inside

Replace:

```text
BEGIN
  query 1,000 orders
  fetch customer details repeatedly
  compute report
  call HTTP
  update two documents
COMMIT
```

with:

```text
Outside:
  read reference data, compute proposed values

BEGIN:
  read/verify fields requiring consistency
  update exact target documents by key
  insert ledger/outbox
COMMIT

Outside:
  emit events and return response
```

For queries that must run inside the transaction, index the filter predicates. Seeing a `COLLSCAN` on a large collection means your long transaction is likely **a symptom of a slow query**, not a transaction API flaw.

### 16.3. Processing Bulk Data with Checkpoints

A 500,000-document migration script rarely needs **one single transaction**:

1. Partition into batches along a stable key.
2. Each batch processes a bounded set of documents.
3. Persist checkpoint/idempotency state.
4. Support resuming or re-running safely after failures.
5. Include final consistency verification.

If business rules strictly demand an all-at-once transition with zero visible intermediate state, evaluate staging collections, versioned pointer swaps, or dedicated migration patterns rather than assuming batching preserves global atomicity.

### 16.4. Address Contention Before Adding Hardware

Adding CPU/RAM helps raw capacity, yet if 1,000 writers update one hot document concurrently, logical contention remains. Mitigations:

- Shorten transactions.
- Reduce operations touching hot records.
- Limit concurrency per business key.
- Use atomic single-document updates where transactions are unnecessary.
- Change aggregate/bucket models.
- Use budgeted retries with backoff.

Re-measure abort rates and latency after changes, not just CPU utilization.

## 17. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “MongoDB transactions lock the entire database” | MongoDB uses multi-granularity locks/concurrency control; no global exclusive lock across all transactions |
| “Opening the transaction as early as possible is safer” | Opening early pins snapshots and resources longer |
| “As long as commit is last, waiting on HTTP inside is fine” | External waits stretch transactions and external side effects do not roll back |
| “Snapshot means other writers must wait for me” | Other writers proceed; your transaction can hit write conflicts |
| “`WriteConflict` means database corruption” | Normal concurrency contention; handle via retries or redesign |
| “`WriteConflict` and `DuplicateKey` are the same” | Different error codes and handling policies |
| “Just raising `maxTransactionLockRequestTimeoutMillis` fixes conflicts” | Lock wait timeouts do not eliminate write conflicts |
| “Default lifetime is 60s so using ~59s is fine” | 60s is just a common lifetime cap, not an SLA target |
| “Immediate retries always succeed eventually” | Can worsen contention; use backoff and limits |
| “Retrying the single failed update inside the old transaction works” | Old snapshots do not refresh after conflicts; start a new transaction |
| “Unknown commit result means nothing wrote” | Commit may have succeeded; retry commit / reconcile |
| “Driver auto-retries so callbacks can send emails” | Callbacks can run multiple times; side effects can duplicate |
| “Unique indexes are unnecessary if using transactions” | Transactions do not enforce uniqueness without constraints |
| “Updating one document needs a transaction” | MongoDB guarantees single-document atomicity natively |
| “A one-million-document batch in one transaction is always better” | Cache, lifetime, contention, and replication costs can be severe |
| “Adding RAM eliminates hot-document contention” | Logical write contention still occurs |
| “Every transaction writes exactly one oplog entry” | Transactions can span multiple oplog entries per version/mechanics |
| “Retryable errors and business conflicts can share one handler” | Transient faults, duplicates, validation, and unknown commits need distinct policies |

## 18. Practice Exercises

### Exercise A. Identifying Long Transactions

Given the workflow:

```text
BEGIN
  find customer
  HTTP call: check fraud (8 seconds)
  find inventory
  update inventory
  HTTP call: charge card (12 seconds)
  insert order
COMMIT
```

Answer:

1. Which steps should move outside the transaction?
2. Which steps must be re-verified inside the transaction?
3. Why is charging a card inside a retryable callback dangerous?
4. If the charge succeeded yet the transaction aborts, what workflow/compensation is needed?

### Exercise B. Write Conflict After a Stale Snapshot

Document `{_id:"P1",version:3,price:100}`:

```text
A: start transaction, read version 3
B: update price=110, version=4, commit
A: update price=105 inside old transaction
```

Explain:

- Why can A hit `WriteConflict`?
- Should A retry only the update inside the old transaction?
- If A wants version-checked updates, how can CAS be applied?
- If A and B both edit price, is blindly letting A win valid business behavior?

### Exercise C. Two Errors with Different Retry Semantics

Compare:

```text
Case 1:
  Transaction update -> WriteConflict (TransientTransactionError)

Case 2:
  commitTransaction -> network drops, UnknownTransactionCommitResult
```

In each case, what should retry: **the whole transaction**, **commit of the current transaction**, or **business operation reconciliation**? Why is generating a new `operationId` when retrying Case 2 dangerous?

### Exercise D. Contention on a Hot Document

A system has a `globalCounter` document. Every order creation request runs:

```text
BEGIN
  update globalCounter
  insert order
COMMIT
```

At 500 concurrent requests, `WriteConflict` spikes. Propose at least three changes to reduce contention **while preserving required invariants**, and identify which invariants need re-analysis if splitting the counter across multiple documents.

### Exercise E. Unsolvable by Raising Lifetime

`transactionLifetimeLimitSeconds` was raised from 60 to 300. Abort rates remain high, and `wiredTiger.cache` is under heavy pressure.

List:

- Metrics to inspect.
- Why raising lifetime can worsen the situation.
- Optimizations requiring no server config change.
- When to consider a batch/checkpoint model.

### Exercise F. Multi-Shard Transactions

A transaction transfers points between two wallets in two tenants residing on different shards:

1. Why does commit require extra coordination?
2. How does including the shard key in filters affect routing?
3. How can transaction duration be reduced?
4. Why shouldn't you optimize solely for “single shard” at the expense of access control or uniqueness requirements?

## 19. Test Data Cleanup Guide

The `mongosh` experiment created only one document in `mongo_tx_row252_lab.inventory_demo`. Before cleaning up, confirm the exact connection, database, document ID, and `runId` in your current session:

```javascript
print("database=" + lab.getName());
print("collection=" + inventory.getName());
print("runId=" + runId);

const owned = inventory.findOne(
  { _id: skuId, runId },
  { _id: 1, runId: 1, sku: 1, available: 1 }
);

printjson(owned);
```

Once verified as your own test document:

```javascript
const result = inventory.deleteOne({
  _id: skuId,
  runId
});

printjson(result);
print("remaining=" + inventory.countDocuments({
  _id: skuId,
  runId
}));
```

Never run `deleteMany({})`, `drop()`, or `dropDatabase()` on shared databases. If a test transaction left a session open or active, **abort/`endSession`** per permissions and policies before cleaning up. Never modify `local.oplog.rs`, replica set config, or documents outside your test run.

## 20. Official References

When implementing, consult documentation matching your **exact MongoDB and driver versions**:

- [Transactions — MongoDB Manual](https://www.mongodb.com/docs/manual/core/transactions/) — mechanics and scope of multi-document transactions.
- [Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — lifetime, locks, cache, and operations.
- [Transactions and Read Concern](https://www.mongodb.com/docs/manual/core/transactions/#transactions-and-read-concern) — read semantics in transactions.
- [Transactions and Write Concern](https://www.mongodb.com/docs/manual/core/transactions/#transactions-and-write-concern) — commit acknowledgment.
- [TransactionTooLargeForCache](https://www.mongodb.com/docs/manual/reference/error-codes/) — error code/name lookup by server version.
- [Node.js Driver — Transactions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/) — `withTransaction`, sessions, retries, and driver limits.
- [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server metrics.
- [currentOp](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/) — observing active operations.
- [Transaction Lifetime Limit](https://www.mongodb.com/docs/manual/reference/parameters/#mongodb-parameter-param.transactionLifetimeLimitSeconds) — lifetime configuration by version.

## 21. Conclusion

MongoDB multi-document transactions ensure **multiple MongoDB operations commit or abort together**, yet should never wrap every step of a business process. **Long transactions** pin snapshots and resources longer, driving WiredTiger cache pressure, lock waits, write conflicts, timeouts, and aborts—especially under high write volume or concurrency.

**`WriteConflict`** is a key signal of concurrency control: the transaction acted on a snapshot or condition invalidated by concurrent changes. Transient errors may call for **retrying the whole transaction against a fresh snapshot**, whereas **`UnknownTransactionCommitResult`** calls for distinct commit retry and reconciliation handling. Never blindly retry business operations with new IDs, skip unique constraints, or call external services inside retryable callbacks.

Safe design starts with three principles: **keep transactions short**, **enforce invariants at write time via proper predicates and indexes**, and **bound retries alongside idempotency and resource monitoring**. When single-document atomicity suffices, prefer simple atomic writes; when multi-document atomicity is truly needed, keep transaction scope tight, track duration and abort rates, and prepare a clear conflict-handling process.
