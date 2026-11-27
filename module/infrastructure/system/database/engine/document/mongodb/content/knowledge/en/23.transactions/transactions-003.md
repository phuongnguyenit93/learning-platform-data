# Sessions, Starting Transactions, Commit, and Abort in MongoDB

## Lesson Objectives

In MongoDB, a write operation on **a single document** is already atomic within that document's scope. However, real-world applications have business processes requiring **multiple operations** or **multiple documents** to succeed together or not be applied at all. Examples: transferring 200,000 VND from account A to account B; decrementing inventory and creating an order; updating balances and recording a transaction ledger entry.

MongoDB supports **multi-document transactions** on eligible deployments so that multiple read/write operations can execute within a single transaction. To use transactions properly, you must first understand **sessions** — the context that links operations together. Then you must manage the lifecycle:

~~~text
Create session
    |
    v
startTransaction()
    |
    v
Read / write within session
    |
    +--- all business conditions valid ---> commitTransaction()
    |
    +--- error or explicit cancel --------> abortTransaction()
    |
    v
Close session / release resources
~~~

This lesson belongs to the **Database Engine Document MongoDB** topic, **Transactions** chapter, focusing on **Sessions, starting transactions, commit, and abort**. After this lesson, you will be able to:

1. Distinguish a **logical session** from a **transaction** and understand why they are not synonymous.
2. Create, use, and close a `ClientSession` properly.
3. Call `startTransaction()`, execute operations inside a transaction, and invoke `commitTransaction()` or `abortTransaction()`.
4. Explain atomicity, transaction-scoped consistency, uncommitted data, and read-your-own-writes.
5. Choose `readConcern`, `writeConcern`, and `readPreference` appropriate for transactions.
6. State deployment requirements on replica sets/sharded clusters and the limitations of standalone MongoDB.
7. Build a practical money-transfer transaction with precondition checks and history recording.
8. Distinguish **pre-commit errors**, **transient errors requiring transaction retry**, and **unknown commit results**.
9. Use the official driver's callback transaction API when appropriate and understand the risks of manual retry loops.
10. Avoid long-running transactions, parallel operations on the same session, external side effects, and unsupported operations inside transactions.
11. Design commit/abort tests, idempotency, and production transaction observability.

> **Principle:** A session defines the **execution context**; a transaction defines the **atomic boundary**. `commit` requests accepting the outcome, while `abort` discards the **uncommitted** changes of the transaction. A network error right at commit **does not prove** the transaction failed to commit.

---

## 1. Why Are Multi-Document Transactions Needed?

Suppose there are two accounts:

~~~javascript
{
  _id: "ACC-A",
  owner: "An",
  balance: NumberLong("1000000")
}

{
  _id: "ACC-B",
  owner: "Binh",
  balance: NumberLong("300000")
}
~~~

The application wants to transfer 200,000 VND from A to B.

If handled with two independent update commands:

~~~javascript
db.accounts.updateOne(
  { _id: "ACC-A" },
  {
    $inc: {
      balance: NumberLong("-200000")
    }
  }
);

db.accounts.updateOne(
  { _id: "ACC-B" },
  {
    $inc: {
      balance: NumberLong("200000")
    }
  }
);
~~~

then there is a time window or failure case where:

- Debiting A already succeeded.
- The network or application fails before crediting B.
- The system persists half of the business operation.

An update on A is atomic **on document A**; an update on B is atomic **on document B**. Two separate operations **do not automatically form a shared transaction**.

### 1.1. Goal of a Multi-Document Transaction

The transfer operation requires:

~~~text
If successful:
  A: 1,000,000 ->   800,000
  B:   300,000 ->   500,000
  Transfer history: recorded in the same transaction

If failed:
  A: still 1,000,000
  B: still   300,000
  No completed transfer history record
~~~

A transaction allows writes across multiple documents and collections to become an **all-or-nothing** unit, within MongoDB-supported constraints.

### 1.2. Not Every Problem Needs a Transaction

If only modifying a single document:

~~~javascript
db.accounts.updateOne(
  {
    _id: "ACC-A",
    balance: { $gte: NumberLong("200000") }
  },
  {
    $inc: {
      balance: NumberLong("-200000")
    }
  }
);
~~~

MongoDB already guarantees atomicity of the update operation within a single document. Using a multi-document transaction for a simple single-document condition may yield no commensurate benefit.

**Prioritize proper document design** before adding transactions. Multi-document transactions carry resource, lock/concurrency, and operational costs; they are not a substitute for good schema design.

---

## 2. What Is a Session?

A **session** is a logical context that helps MongoDB and the driver correlate operations issued by the same client. Logical sessions support features such as causal consistency, retryable writes, and multi-document transactions depending on configuration and capabilities.

A session carries a logical identifier (commonly referred to as **`lsid`**) and is managed by the driver and server. A client can run operations **within a session** without starting a transaction.

### 2.1. Three Distinct Objects

| Concept | Nature | Automatically Starts a Transaction? |
|---|---|---|
| `MongoClient` | Client object managing connections, discovery, pooling | No |
| `ClientSession` | Logical context for operations | No |
| Transaction | Group of operations with begin/commit/abort boundary | Yes, when starting a transaction in a session |

In Java:

~~~java
MongoClient client = MongoClients.create(uri);
ClientSession session = client.startSession();
session.startTransaction();
~~~

Each line has a distinct responsibility:

1. Create the client.
2. Create a session bound to the client.
3. Start a transaction within the session.

### 2.2. Having a Session Does Not Mean Every Operation Automatically Participates

If an application has:

~~~javascript
const session = db.getMongo().startSession();
const sessionDb = session.getDatabase("training_bank");

session.startTransaction();

sessionDb.accounts.updateOne(
  { _id: "ACC-A" },
  { $inc: { balance: -100 } }
);
~~~

then the operation on `sessionDb` belongs to the session context. However, an operation written via a regular handle:

~~~javascript
db.getSiblingDB("training_bank")
  .accounts.updateOne(
    { _id: "ACC-B" },
    { $inc: { balance: 100 } }
  );
~~~

**does not automatically join** the transaction merely because it is invoked in the same script file.

The same applies in Java: you must pass `ClientSession` to operations:

~~~java
accounts.updateOne(session, filter, update);
~~~

Never forget to pass the session on any operation that the business requires to be all-or-nothing.

### 2.3. One Session Cannot Run Multiple Transactions Concurrently

At any given time, do not start a second transaction on the same session while the previous transaction is still active. Across drivers, **do not run operations within the same transaction in parallel on the same session** when the API does not support it.

For instance, avoid spawning multiple async write tasks in the same transaction and running them concurrently with `Promise.all`. Operations inside a transaction should follow a clear sequential order.

### 2.4. A Session Is Not a Single Permanent Transaction

One session can execute multiple transactions **sequentially**:

~~~text
Session S
  |
  +-- Transaction T1: start -> operations -> commit
  |
  +-- Transaction T2: start -> operations -> abort
  |
  +-- Transaction T3: start -> operations -> commit
  |
  +-- endSession()
~~~

That does not make T1, T2, and T3 a single transaction. Each transaction has its own boundary and outcome.

### 2.5. Ending a Session

When done, close the session to release client-side logical resources:

~~~javascript
session.endSession();
~~~

In Java, use `try-with-resources` for `ClientSession`. Never hold sessions open indefinitely or share a single session across unrelated requests.

---

## 3. Causal Consistency Sessions Differ from Transactions

A session can be used for **causal consistency** **without** running a transaction.

For instance, when an application requires a causally ordered sequence of operations, an appropriate session combined with read/write concerns can help provide guarantees such as read-your-writes and causal ordering under documented conditions.

~~~javascript
const session = db.getMongo().startSession({
  causalConsistency: true
});

try {
  const sdb = session.getDatabase("training_bank");

  // Two operations in the same logical session,
  // but WITHOUT startTransaction.
  sdb.accounts.updateOne(
    { _id: "ACC-A" },
    { $set: { nickname: "An" } }
  );

  const account = sdb.accounts.findOne({
    _id: "ACC-A"
  });

  printjson(account);
} finally {
  session.endSession();
}
~~~

**There is no `startTransaction`** in this example, so the two operations are not combined into a multi-document transaction.

### 3.1. Causal Consistency Has Prerequisites

Causal consistency guarantees such as monotonic reads, read-your-writes, monotonic writes, and writes-follow-reads depend on proper session usage, read/write concerns (often discussed with `majority`), deployment capabilities, and server/driver versions. Never claim “just calling `startSession` gives full ACID”.

### 3.2. Do Not Confuse Logical Sessions with Snapshot Sessions

Some drivers/servers support **snapshot sessions** for consistent point-in-time reads. That is not the same concept as a multi-document transaction in a session. When designing snapshot reads, check the API and rules for your version rather than calling every snapshot read a transaction.

---

## 4. Prerequisites for Using Multi-Document Transactions

### 4.1. Supported Deployments

MongoDB supports multi-document transactions on:

- **Replica sets** — introduced in MongoDB **4.0**.
- **Sharded clusters** — distributed transactions supported since MongoDB **4.2**.

A **standalone `mongod`** does not provide multi-document transactions via the same API. If you only have a single machine for learning, you can run a **single-node replica set** to exercise transactions functionally, even though it lacks high availability.

### 4.2. Storage Engine and Version

Transactions rely on storage engine and deployment capabilities, typically WiredTiger in modern MongoDB deployments. Verify that your server version, driver version, and topology support the transaction API.

Do not write code assuming `startTransaction()` existing on the client guarantees execution; if the server does not support it, the operation fails.

### 4.3. Connecting via a Replica Set URI

In a three-member lab:

~~~text
mongodb://mongo1:27017,mongo2:27017,mongo3:27017/?replicaSet=rsLearn
~~~

With a single-node replica set:

~~~text
mongodb://localhost:27017/?replicaSet=rsDev
~~~

The names `rsLearn` and `rsDev` must match the initialized replica set `_id`. For Atlas or sharded clusters, use the URI provided by your deployment.

### 4.4. Other Practical Prerequisites

- The user has read/write privileges on all collections involved.
- Collections and indexes required for business logic are pre-created in the lab whenever possible.
- The client uses an official driver supporting sessions/transactions.
- Proper read/write acknowledgment settings are configured.
- Transactions remain short and never wait for user interaction midway.
- Error handling and retry strategies are in place.
- Operations outside MongoDB (calling payment APIs, sending emails, Kafka...) **do not automatically belong to this transaction**.

### 4.5. Transactions Do Not Make Two Different Systems Atomic Together

Example:

~~~text
1. MongoDB: deduct inventory.
2. HTTP API: charge via payment gateway.
3. MongoDB: create order.
~~~

A MongoDB transaction **cannot roll back an HTTP API** that already captured payment. For external systems, use outbox, idempotency, sagas, reconciliation, or other transaction/compensation patterns. Never send emails or call payment gateways inside a callback that automatically retries.

---

## 5. Complete Transaction Lifecycle

A transaction passes through these stages:

~~~text
NO SESSION
    |
    v
START SESSION
    |
    v
SESSION ACTIVE, NO TRANSACTION
    |
    +--> startTransaction()
                |
                v
         TRANSACTION ACTIVE
                |
         +------+------+
         |             |
         v             v
   operations OK    Error / user cancel
         |             |
         v             v
  commitTransaction  abortTransaction
         |             |
         v             v
  COMMIT REQUESTED   ABORTED
         |
         +--> commit confirmed: COMMITTED
         |
         +--> commit outcome unknown:
              handle UNKNOWN outcome
                |
                v
     END SESSION AFTER LOGIC COMPLETES
~~~

### 5.1. `startTransaction()`

This requests starting a transaction **within the session**. It initializes client-side transaction state. Subsequent operations are sent with session/transaction metadata; server-side transaction initialization is tied to the actual operations per driver mechanics.

### 5.2. Operations Inside a Transaction

These may include:

- `find` or supported read operations.
- `insertOne`, `insertMany`.
- `updateOne`, `updateMany`.
- `deleteOne`, `deleteMany`.
- Other aggregations/operations **when permitted inside a transaction**.

Not every database command or aggregation stage is valid inside a transaction; see the restrictions section.

### 5.3. `commitTransaction()`

Requests the server to **commit** the changes belonging to the transaction. When the commit succeeds per the configured write concern and related semantics, the transaction is accepted as a unit.

**Never** infer that every commit request definitely failed after a network timeout; the transaction may have already committed on the server without the client receiving the acknowledgment.

### 5.4. `abortTransaction()`

Requests canceling the active transaction, discarding its uncommitted changes. Once aborted, you cannot call commit to “revive” that transaction. To retry the business operation, you must **start a new transaction**.

### 5.5. `endSession()`

Closes the logical session. Never treat closing the session as a substitute for explicitly resolving an unknown commit outcome. Especially in financial systems, resolve/reconcile the outcome before initiating a new transaction with the same business ID.

---

## 6. Mongosh: Creating a Session, Starting, and Committing a Transaction

### 6.1. Preparing Lab Data

Use the `training_bank` database on a replica set. In an isolated lab, seed data outside a transaction:

~~~javascript
use training_bank

db.accounts.insertMany([
  {
    _id: "ACC-A",
    owner: "An",
    balance: NumberLong("1000000"),
    currency: "VND"
  },
  {
    _id: "ACC-B",
    owner: "Binh",
    balance: NumberLong("300000"),
    currency: "VND"
  }
]);

db.transfers.createIndex(
  { requestId: 1 },
  {
    name: "uk_transfers_requestId",
    unique: true
  }
);
~~~

Note: when re-running the lab, `insertMany` with the same `_id` will trigger a duplicate key error. Use a fresh lab database or clean up deliberately; never drop an entire production database.

### 6.2. Successful Commit Transaction Script

~~~javascript
const session = db.getMongo().startSession();

try {
  const bankDb = session.getDatabase("training_bank");
  const accounts = bankDb.getCollection("accounts");
  const transfers = bankDb.getCollection("transfers");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  const amount = NumberLong("200000");

  const debit = accounts.updateOne(
    {
      _id: "ACC-A",
      balance: { $gte: amount }
    },
    {
      $inc: { balance: NumberLong("-200000") }
    }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Source account missing or insufficient funds");
  }

  const credit = accounts.updateOne(
    { _id: "ACC-B" },
    {
      $inc: { balance: amount }
    }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Destination account not found");
  }

  transfers.insertOne({
    _id: "TRANSFER-001",
    requestId: "REQ-TRANSFER-001",
    from: "ACC-A",
    to: "ACC-B",
    amount: amount,
    status: "COMPLETED",
    createdAt: new Date()
  });

  session.commitTransaction();

  print("Transaction commit confirmed");
} catch (error) {
  // Intended for errors occurring while the transaction is active.
  // If an error occurs AT COMMIT, the outcome may be unknown.
  try {
    session.abortTransaction();
  } catch (abortError) {
    print("Abort cannot prove the transaction did not commit");
  }

  throw error;
} finally {
  session.endSession();
}
~~~

**Important note on this example:** The snippet focuses on demonstrating `startTransaction()`, `commitTransaction()`, and `abortTransaction()`. In production, **never call abort inside a catch block and assume it proves the transaction did not commit**, especially if the failure occurred in `commitTransaction()`. Use the callback/retry API and inspect error labels as described later.

### 6.3. Verifying After Commit

In a regular `mongosh` session, inspect:

~~~javascript
db.getSiblingDB("training_bank")
  .accounts.find(
    {},
    { _id: 1, balance: 1, currency: 1 }
  )
  .sort({ _id: 1 });

db.getSiblingDB("training_bank")
  .transfers.find({
    requestId: "REQ-TRANSFER-001"
  });
~~~

Starting from the seeded dataset and committing once:

| Account | Before | After |
|---|---:|---:|
| ACC-A | 1,000,000 | 800,000 |
| ACC-B | 300,000 | 500,000 |

There is also one corresponding `transfers` document.

### 6.4. Why Is the Debit Filter Conditional?

The condition:

~~~javascript
{
  _id: "ACC-A",
  balance: {
    $gte: NumberLong("200000")
  }
}
~~~

prevents debiting into a negative balance within an eligible update. If it fails to match, `matchedCount` is 0 and the application throws an error to abort the entire operation.

A transaction **does not replace business validation**. Always validate account existence, currency matching, positive amount, balance, account status, and other constraints.

### 6.5. Why Record History in the Same Transaction?

If you update both balances inside a transaction while inserting the transfer log outside, you risk:

~~~text
Both balances committed
         |
         v
Application crashes before inserting transfer record
         |
         v
No corresponding business audit trail
~~~

Placing the transfer record insert **in the same transaction** guarantees all-or-nothing consistency between balances and internal MongoDB history.

While this does not replace an independent audit trail or full double-entry accounting ledger in an enterprise financial system, it illustrates the atomic boundary principle clearly.

---

## 7. Mongosh: Explicitly Aborting a Transaction

Suppose the application detects invalid data after performing provisional writes.

~~~javascript
const session = db.getMongo().startSession();

try {
  const sdb = session.getDatabase("training_bank");
  const accounts = sdb.getCollection("accounts");

  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: "primary"
  });

  accounts.updateOne(
    { _id: "ACC-A" },
    {
      $inc: {
        balance: NumberLong("-10000")
      }
    }
  );

  // Simulate a business decision: must cancel.
  const approved = false;

  if (!approved) {
    session.abortTransaction();
    print("Transaction aborted per business logic");
  } else {
    session.commitTransaction();
    print("Transaction committed");
  }
} finally {
  session.endSession();
}
~~~

### 7.1. State After Abort

If ACC-A started at 800,000, after the transaction aborts, the balance remains **800,000**. Executing `updateOne` inside the transaction **did not** persist the aborted modification.

### 7.2. Abort Is Not “Undo Anything”

If a write already **committed in an earlier transaction**, a new transaction cannot use `abortTransaction()` to reverse that write.

Example:

~~~text
Transaction T1:
  Debit 100,000
  commit succeeds

Transaction T2:
  abort
~~~

Aborting T2 does not undo T1. To refund or reverse a committed operation, you need a controlled compensating action, such as creating a new refund transaction, never “calling abort again”.

### 7.3. Abort Does Not Cancel Side Effects Outside MongoDB

If while the transaction was running the application sent an email or captured payment via a third-party API, `abortTransaction()` cannot recall that email or API call. Never perform non-idempotent external side effects between start and commit hoping everything will roll back.

---

## 8. Atomicity: What Is Guaranteed and What Is Not?

### 8.1. All-or-Nothing for Transaction Operations

When a transaction commits successfully:

- Changes belonging to the transaction are accepted as one unit.
- If the transaction aborts, its uncommitted writes are not retained as committed data.
- Other applications do not observe a subset of uncommitted writes as committed data under normal isolation rules.

Example:

~~~text
Transaction:
  A.balance -= 200000
  B.balance += 200000
  transfers.insert(...)

Commit succeeds:
  Internal updates are accepted together.

Abort:
  None of the transaction's changes are committed.
~~~

### 8.2. Reads Inside a Transaction See Its Own Writes

Within the same session/transaction:

~~~javascript
const sdb = session.getDatabase("training_bank");

session.startTransaction();

sdb.accounts.updateOne(
  { _id: "ACC-A" },
  { $set: { flag: "PENDING" } }
);

const withinTransaction = sdb.accounts.findOne({
  _id: "ACC-A"
});

printjson(withinTransaction);
~~~

The transaction can read modifications it performed itself. This does not mean clients outside the transaction see the `PENDING` flag before commit.

### 8.3. Transactions Do Not Automatically Guarantee Strict Serializability

Transactions with snapshot read concern provide snapshot isolation under matching semantics, yet **you must not assume all concurrent business operations execute as if in an ideal serial queue**.

Write skew example: two transactions both read a constraint distributed across multiple documents and modify **two different documents**; if the constraint is not enforced via a unique index, conditional write, or synchronization strategy, outcomes can violate the business invariant.

You need:

- Conditional predicates.
- Unique indexes for uniqueness constraints.
- Single-document operations where feasible.
- Write-conflict handling and retries.
- Avoiding the assumption that using a transaction eliminates all race conditions.

### 8.4. Snapshot Reads Can Be Stale Relative to External Changes

A long transaction may read from its established snapshot while another transaction commits newer data. Reading inside a transaction is not a way to immediately see every latest external update.

For problems requiring a strict “lock” or tight update serialization, you may need conditional writes or lock patterns to detect conflicts. Transactions provide atomicity, not a replacement for concurrency control design.

---

## 9. Read Concern, Write Concern, and Read Preference in Transactions

### 9.1. Three Distinct Options

| Property | Question |
|---|---|
| `readConcern` | With what guarantee level is the transaction allowed to read records? |
| `writeConcern` | What acknowledgment/durability level does the commit require? |
| `readPreference` | Which replica set member handles reads for the transaction? |

### 9.2. Sample `TransactionOptions`

~~~javascript
session.startTransaction({
  readConcern: {
    level: "snapshot"
  },
  writeConcern: {
    w: "majority"
  },
  readPreference: "primary"
});
~~~

- `snapshot`: aims for a consistent snapshot inside the transaction per MongoDB semantics.
- `majority`: write concern confirming commit at the supported majority level.
- `primary`: routes transaction reads/writes per transaction requirements.

### 9.3. Transaction Write Concern Is Set at the Transaction/Commit Level

While inside a transaction, do not specify individual write concerns on each insert/update as though they were standalone commands.

**The transaction's write concern is applied at commit.**

Conceptual example:

~~~javascript
session.startTransaction({
  writeConcern: {
    w: "majority"
  }
});

// Operations on collections via the session:
sdb.orders.insertOne({ _id: "O-TX-1" });
sdb.ledger.insertOne({ _id: "L-TX-1" });

// Acknowledgment level is enforced on commit:
session.commitTransaction();
~~~

An update inside a transaction may return to the client before commit, yet it has not been published as an independent committed write.

### 9.4. `readConcern:"snapshot"` and `writeConcern:"majority"`

This pairing is commonly used to request a consistent snapshot alongside stronger commit durability.

Understand the exact contract: snapshot-of-majority-committed-data guarantees depend on transaction-level read concern together with committing the transaction using `w:"majority"` per server documentation. Never treat a single option in isolation as guaranteeing all cluster reads/writes are always latest/linearizable.

### 9.5. `readPreference:"primary"`

Multi-document transactions **that perform writes** must execute per primary rules. Standard safe practice is selecting `primary` for transactions.

Never try routing a write transaction to a secondary via `secondaryPreferred` to speed things up: secondaries do not accept normal application writes like a primary.

### 9.6. Other Read Concerns

MongoDB also offers `local`, `majority`, and other levels. Each carries different guarantees and costs; suitability for transactions depends on server version, topology, and documented rules.

In this chapter, `snapshot` clearly illustrates multi-document consistency. However, that does not mean every transaction must always manually override it; official drivers and deployments provide defaults and option inheritance where appropriate.

---

## 10. Committing Is Not the Same as “Sending the Commit Command”

This is one of the most crucial distinctions.

### 10.1. Three Points in Time

~~~text
T1: Client sends commitTransaction to server.
T2: Server commits the transaction.
T3: Client receives commit acknowledgment.
~~~

If the connection drops between T2 and T3, the client may see a **network error**, even though the transaction committed on the server.

If failure occurred before T2, the server may not have committed. From a network error alone, the client **cannot know for certain** which case happened.

### 10.2. Errors at Commit Represent Unknown Outcomes

MongoDB drivers attach **error labels** in certain cases, such as:

- `UnknownTransactionCommitResult`: the commit outcome is undetermined.
- `TransientTransactionError`: a transient error meaning the transaction can be restarted from scratch per applicable rules.

**Never** assume every error means “the transaction failed and nothing was written”.

### 10.3. Retrying Commit Differs from Retrying the Entire Business Operation

If the commit result is unknown, the resolution may be **retrying `commitTransaction()` on the same transaction/session** per the API and error label, rather than immediately re-running the debit/credit operations as a brand-new transaction.

If the transaction hit a transient error before commit, the standard handling is **aborting the old transaction and re-executing the entire transaction** in a new transaction.

These are two **different** retry loops; never conflate them.

### 10.4. Decision Table

| Error Location and State | Risk | Handling Approach |
|---|---|---|
| Business validation fails before commit | Invalid business request | Abort, return business error, do not auto-retry |
| Write conflict/transient error during execution | Transaction needs a fresh attempt | Retry **the entire transaction** when labeled/eligible |
| Connection lost right at commit, unknown outcome | Server may have already committed | Retry **commit** per label/driver contract; do not re-run business logic |
| Commit returns success | Transaction confirmed per semantics | Close session, finish |
| Abort confirmed | Uncommitted changes discarded | Safe to execute another attempt in a new transaction |
| Write concern timeout at commit | Outcome requires verification | Classify result/error, track commit, reconcile via business ID |

### 10.5. Never Use Unbounded Catch-All Retries

A loop like:

~~~javascript
while (true) {
  // re-run the entire business logic
}
~~~

is dangerous because:

- It can cause duplicate writes.
- It can push an overloaded server into a retry storm.
- It fails to separate business errors from transient server errors.
- It mishandles unknown commit outcomes.
- The transaction may keep failing on a permanent constraint.

Use the driver's transaction helper when appropriate; if implementing manually, enforce retry budgets, error classification, and observability.

---

## 11. Handling Errors and Retries with the Callback API

Official drivers typically provide a **callback transaction API** (such as `withTransaction`) to implement retry logic for transient errors and commit outcome uncertainty within driver capabilities.

Concept:

~~~text
withTransaction(callback):
    startTransaction()
    try:
        run callback containing database operations
        commitTransaction()
    if eligible transient error:
        abort and re-execute callback
    if commit result unknown:
        attempt to resolve via commit retry per driver rules
    if business error or non-retryable error:
        abort and propagate error
~~~

This is a **conceptual diagram**, not executable code of any specific driver. Drivers enforce deadlines and specific retry policies; never assume every error is retryable.

### 11.1. Callbacks Can Execute Multiple Times

If the callback re-runs, everything inside it repeats:

~~~text
Desired:
  MongoDB transfer operations -> retry inside transaction.

Undesired:
  Send email 3 times when callback retries 3 times.
  Call payment gateway 3 times.
  Publish Kafka event 3 times.
~~~

**Never place non-idempotent external side effects inside the callback**. A better architecture writes an **outbox document** inside the MongoDB transaction, and a separate worker publishes events post-commit with explicit idempotency and retries.

### 11.2. Idempotency Keys

When a client sends a transfer request:

~~~javascript
{
  requestId: "REQ-TRANSFER-001",
  from: "ACC-A",
  to: "ACC-B",
  amount: 200000
}
~~~

create a unique index:

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  {
    unique: true,
    name: "uk_transfer_requestId"
  }
);
~~~

Purpose: if a client times out post-commit and resends the same request ID, the system can detect that the request was already processed instead of debiting a second time.

However, **a unique index alone does not solve all of idempotency**: the application must still verify that the stored request ID has the same amount/from/to, distinguish pending vs. completed states, and return the right response. On duplicate key errors, never assume every error means the prior transaction succeeded.

### 11.3. Use Bounded Retries and Structured Logs

Fields worth logging (without leaking sensitive data):

- Operation name / sanitized business request ID.
- Transaction attempt number.
- Error label.
- Commit attempt count.
- Duration.
- Whether outcome is known/unknown.
- MongoDB deployment/version.
- Error category, without dumping raw account details or secrets.

Enforce a retry budget to prevent requests from hanging indefinitely.

---

## 12. Java Sync Driver: Manual Sessions and Transactions

### 12.1. Conceptual Dependencies

A Java application connecting to a replica set uses the MongoDB Java Sync Driver to obtain `MongoClient`, `MongoDatabase`, and `MongoCollection`.

Example:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class TransactionManualExample {

    public static void main(String[] args) {

        String uri =
            "mongodb://mongo1:27017,mongo2:27017,mongo3:27017/"
            + "?replicaSet=rsLearn";

        MongoClientSettings clientSettings =
            MongoClientSettings.builder()
                .applyConnectionString(new ConnectionString(uri))
                .build();

        try (MongoClient client = MongoClients.create(clientSettings);
             ClientSession session = client.startSession()) {

            MongoDatabase database =
                client.getDatabase("training_bank");

            MongoCollection<Document> accounts =
                database.getCollection("accounts");

            MongoCollection<Document> transfers =
                database.getCollection("transfers");

            TransactionOptions options =
                TransactionOptions.builder()
                    .readPreference(ReadPreference.primary())
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(
                        WriteConcern.MAJORITY.withWTimeout(
                            5,
                            TimeUnit.SECONDS
                        )
                    )
                    .build();

            session.startTransaction(options);

            boolean commitAttempted = false;

            try {
                var debit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", "ACC-A"),
                        Filters.gte("balance", 200000L)
                    ),
                    Updates.inc("balance", -200000L)
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Insufficient balance or missing source account"
                    );
                }

                var credit = accounts.updateOne(
                    session,
                    Filters.eq("_id", "ACC-B"),
                    Updates.inc("balance", 200000L)
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "Missing destination account"
                    );
                }

                transfers.insertOne(
                    session,
                    new Document("_id", "TRANSFER-JAVA-001")
                        .append("requestId", "REQ-JAVA-001")
                        .append("from", "ACC-A")
                        .append("to", "ACC-B")
                        .append("amount", 200000L)
                        .append("status", "COMPLETED")
                );

                commitAttempted = true;
                session.commitTransaction();

            } catch (RuntimeException ex) {
                if (!commitAttempted) {
                    try {
                        session.abortTransaction();
                    } catch (RuntimeException ignored) {
                        // Log properly in a real application.
                    }
                }

                // If the error occurred at commit, do not assume
                // the transaction failed. This example does not yet
                // implement a commit retry loop.
                throw ex;
            }
        }
    }
}
~~~

**Limitations of the code above:** It clearly demonstrates manual steps and abort/commit boundaries, **not a complete production error-handling template**. If an error happens during commit, the code **does not** re-run the entire transfer; it propagates the exception so the application layer can resolve the unknown outcome as required. In production, use the callback transaction API when suitable or implement commit/transaction retries based on error labels per driver guidelines.

### 12.2. Why Must Operations Receive `session`?

In the Java driver:

~~~java
accounts.updateOne(session, filter, update);
~~~

differs from:

~~~java
accounts.updateOne(filter, update);
~~~

The second command omits the session; it runs outside the active transaction. A transaction only protects operations executed with the right session.

### 12.3. Why Use `try-with-resources`?

~~~java
try (ClientSession session = client.startSession()) {
    // ...
}
~~~

ensures the session is closed when the block completes. `MongoClient` should likewise be managed as a long-lived application singleton rather than creating a new client per request.

The `main` example above creates a client for illustration; in a production service, inject a single application-managed `MongoClient`.

### 12.4. Typed Models vs. `Document`?

`Document` is convenient for labs. For domain models, you can use POJOs/codecs, repositories, schema validation, and custom mapping. Regardless of representation, transaction semantics still depend on **`ClientSession`** and the proper deployment.

---

## 13. Java Sync Driver: Callback Transactions with `withTransaction`

When you do not want to build the entire retry/commit loop manually, use the driver's callback API (check exact method names and signatures for your driver version).

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class TransactionCallbackExample {

    public static void doTransfer(
            ClientSession session,
            MongoCollection<Document> accounts,
            MongoCollection<Document> transfers) {

        TransactionOptions options =
            TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        session.withTransaction(() -> {

            var debit = accounts.updateOne(
                session,
                new Document("_id", "ACC-A")
                    .append("balance",
                        new Document("$gte", 100000L)),
                new Document("$inc",
                    new Document("balance", -100000L))
            );

            if (debit.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Insufficient funds"
                );
            }

            var credit = accounts.updateOne(
                session,
                new Document("_id", "ACC-B"),
                new Document("$inc",
                    new Document("balance", 100000L))
            );

            if (credit.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Missing destination account"
                );
            }

            transfers.insertOne(
                session,
                new Document("_id", "TRANSFER-CALLBACK-001")
                    .append("requestId", "REQ-CALLBACK-001")
                    .append("amount", 100000L)
            );

            return null;

        }, options);
    }
}
~~~

In this example:

- `session.withTransaction` manages start/commit/abort and eligible retries per the driver contract.
- The callback only executes **MongoDB operations bound to the session** and required validation logic.
- Do not send emails, call payment gateways, or perform non-idempotent file writes inside the callback.
- A stable request ID must be designed to handle client-level retries outside the callback.
- A business exception like insufficient funds must not be treated as transient or retried endlessly.

### 13.1. Does the Callback API Replace Idempotency?

**No.** The driver can retry at the transaction/commit level in supported scenarios, while an application request can still be resent by a user or API gateway after a timeout. That is a different retry layer. Unique business IDs and state tracking remain essential.

### 13.2. Error Labels and Retry Decisions

Official drivers inspect error labels to determine retry behavior. Never catch **every** `MongoException` blindly and re-run the callback:

- Duplicate key errors from duplicate data are usually business/idempotency cases.
- Validation errors do not disappear on retry.
- Authorization/authentication failures are not transient conflicts.
- Unknown commit results require a dedicated strategy.
- Eligible transient errors can retry the entire transaction.

### 13.3. Controlling Transaction Duration

Even with the callback API, keep transactions short and never wait on users, external network services, or heavy computations. Callbacks have bounded retry budgets; long waits risk hitting the transaction lifetime limit and increasing contention.

---

## 14. Spring Data MongoDB and Session Boundaries

In Spring applications, you can use `MongoTransactionManager` and `@Transactional` once transaction support is configured for your replica set/sharded cluster and Spring Data version.

Conceptual example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransferRepository transferRepository;

    public TransferService(
            AccountRepository accountRepository,
            TransferRepository transferRepository) {
        this.accountRepository = accountRepository;
        this.transferRepository = transferRepository;
    }

    @Transactional
    public void transfer(String fromId,
                         String toId,
                         long amount,
                         String requestId) {

        // Business pseudocode:
        // 1. Conditional debit and check matchedCount.
        // 2. Credit destination.
        // 3. Save transfer log in the same transaction.
        // 4. Throw exception if any check fails.
    }
}
~~~

This snippet illustrates the service boundary; specific repository methods and manager configuration must be provided by your project.

### 14.1. `@Transactional` Does Not Work Automatically in Every Configuration

For real MongoDB transactions:

- The MongoDB deployment must support transactions.
- Spring Data / `MongoTransactionManager` must be configured properly.
- Database operations must execute through components participating in the session/transaction.
- Transaction semantics and exception rollback rules must be understood.
- Self-invocation or calls bypassing the Spring proxy can cause `@Transactional` not to take effect under standard proxy setups.
- MongoDB transactions do not automatically span external SQL databases or REST APIs.

### 14.2. Do Not Mix Transaction Managers Across Different Resources

An application using both PostgreSQL and MongoDB does not automatically gain a distributed ACID transaction simply because both use `@Transactional`. Choose the transaction manager explicitly and coordinate across resources via sagas, outbox, or compensation.

### 14.3. Use This Abstraction Only After Mastering the Manual API

Understanding `ClientSession`, `startTransaction`, `commitTransaction`, and `abortTransaction` helps diagnose real failures when Spring abstractions report timeouts, transient errors, or uncertain commits. Frameworks simplify the API, not the underlying limits.

---

## 15. Common Transaction Mistakes

### 15.1. Accidentally Writing Outside the Session

~~~javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase("shop");

session.startTransaction();

sdb.orders.insertOne({ _id: "O-001" });

// DESIGN BUG: does not belong to the session above.
db.getSiblingDB("shop")
  .inventory.updateOne(
    { _id: "SKU-001" },
    { $inc: { stock: -1 } }
  );
~~~

If the transaction aborts, the order is rolled back while the inventory update remains persisted outside. Use the same session for **all operations** that must be atomic together.

### 15.2. Starting Nested Transactions

~~~javascript
session.startTransaction();
// ...
session.startTransaction(); // Not a valid nested transaction.
~~~

Commit or abort the active transaction before starting a new one.

### 15.3. Forgetting `commitTransaction()`

Merely starting and updating:

~~~javascript
session.startTransaction();
sdb.orders.insertOne({ _id: "O-101" });
session.endSession();
~~~

is not a valid way to commit a transaction. You must explicitly call commit, handle the outcome, and then close the session.

### 15.4. Running Transactions on Standalone

Running transactions against a standalone instance without transaction support causes errors. For single-machine learning, use a single-node replica set rather than assuming standalone behaves like a production replica set.

### 15.5. Using `secondary` Read Preference for Write Transactions

Write transactions must follow primary routing rules. Never set secondary reads on a write transaction expecting a secondary to accept inserts or updates.

### 15.6. Unsupported DDL Operations

Not every operation is permitted inside transactions. Certain DDL/index operations and aggregation stages like `$out` and `$merge` have restrictions; never treat schema migrations as part of a normal transfer transaction.

Create collections, indexes, and schema validation before handling transactions. Exact DDL support varies by MongoDB version, topology, and rules; verify documentation before special cases.

### 15.7. Overly Long Transactions

Holding a transaction open while:

- Calling external APIs.
- Waiting for user payment.
- Processing a batch of millions of documents.
- Building heavy reports.
- Sleeping for a long interval.

increases lock contention, snapshot/cache pressure, replication overhead, and the risk of exceeding the transaction lifetime limit.

### 15.8. Blindly Retrying a Monetary Transfer

A network error at commit does not prove the transaction failed to commit. If a client retries “transfer money” with a new request ID, it can double-transfer. Design idempotency before handling timeouts.

---

## 16. Write Conflicts and Concurrent Operations

### 16.1. Two Transactions Modifying the Same Account

T1 and T2 start concurrently from the same state:

~~~text
T1: Reads A.balance = 500000
T2: Reads A.balance = 500000

T1: A.balance -= 400000
T2: A.balance -= 300000
~~~

MongoDB uses concurrency control and write-conflict detection so conflicting modifications to the same document cannot both commit improperly. One transaction may receive a **write conflict / transient transaction error** and need to retry per policy.

### 16.2. Do Not Read and Then Unconditionally Update

Business bug:

~~~javascript
const a = accounts.findOne({ _id: "ACC-A" });

if (a.balance >= amount) {
  accounts.updateOne(
    { _id: "ACC-A" },
    { $inc: { balance: -amount } }
  );
}
~~~

Without concurrency protection, decisions made on a stale read can become invalid.

Safer with a write predicate:

~~~javascript
const result = accounts.updateOne(
  {
    _id: "ACC-A",
    balance: { $gte: amount }
  },
  {
    $inc: {
      balance: -amount
    }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Insufficient balance");
}
~~~

Placing the condition on the write enforces the invariant at write time, even across transaction retries.

### 16.3. Write Skew and Multi-Document Constraints

Suppose two doctors are on call under the rule “at least one doctor must always be on call”. Two transactions can read the same snapshot, and each turns off on-call status for a **different** doctor. If they only read, count, and update two separate documents, snapshot isolation can permit write skew, breaking the invariant.

The solution is not merely adding a transaction, but designing a shared write target, conditional update, constraint, or synchronization mechanism. Transaction atomicity and business serializability are two separate questions.

---

## 17. Transactions on Replica Sets and Sharded Clusters

### 17.1. Replica Sets

In a replica set, the primary handles transaction operations. Transactions can span multiple collections on supported deployments.

Commit durability depends on write concern and replication health. If the primary fails over while a transaction is active, the driver/client may receive a transient error and need to retry.

### 17.2. Sharded Clusters

MongoDB has supported distributed transactions on sharded clusters since 4.2. When operations touch multiple shards, commit coordination is more complex than on a single replica set, involving multi-participant commit coordination.

Trade-offs:

- Commit latency can be higher.
- Higher likelihood of timeouts/transient errors under some workloads.
- DDL, chunk migration, namespace, and operation restrictions must be checked.
- Bounded retries and idempotency remain necessary.
- Keep transactions as small and short as possible.

### 17.3. Do Not Stuff Entire Batches into One Transaction Unnecessarily

For instance, importing 1 million documents into 20 collections should not default to one giant transaction. Partition by business atomic units and use bulk writes, idempotency, and checkpoints.

### 17.4. Sharding Does Not Fix Broken Transaction Design

Distributing data across shards helps scale certain workloads, yet transactions still require proper sessions, start/commit/abort handling, and consistency settings. Never view sharding as a free pass to run unbounded transactions.

---

## 18. Time, Resource, and Operation Limits

### 18.1. Transaction Lifetime

MongoDB provides **`transactionLifetimeLimitSeconds`**, typically defaulting to **60 seconds** on applicable deployments. Transactions running past the limit can be aborted by the server.

Do not assume “every transaction always gets exactly 60 seconds on every MongoDB version”. Check actual configuration and environment settings.

### 18.2. Transactions Consume Snapshots and Resources

Transactions pin snapshot state and increase pressure on WiredTiger cache, memory, locks, and replication. Long-running transactions can cause:

- `TransactionTooLargeForCache` or related resource errors.
- Write conflicts.
- Disk/cache pressure.
- Increased latency for other operations.
- High commit latency.

Do not equate the **16 MB BSON document size limit** with “every transaction has a 16 MB limit”. Transactions are governed by oplog entry, resource, and operational constraints; exact limits depend on server version.

### 18.3. Unsupported Operations

Certain aggregation stages like `$out`/`$merge` and administrative/DDL commands are disallowed inside transactions in many setups. Never assume “every `mongosh` command that runs outside a transaction runs inside one”.

### 18.4. One Session Must Not Be Used Concurrently at Will

In Node.js or async systems, never run parallel operations on the same session/transaction using `Promise.all` when unsupported by the driver. In Java, never share a single `ClientSession` across multiple threads for parallel transaction operations.

### 18.5. Avoid External I/O Mid-Transaction

Instead of:

~~~text
start transaction
  update account
  call payment gateway taking 20 seconds
  send email
  update ledger
commit
~~~

consider:

~~~text
MongoDB transaction:
  internal updates
  insert outbox event
commit

Post-commit worker:
  read outbox event
  call external API with idempotency key
  mark result / retry / compensate
~~~

This architecture decouples atomic database changes from external side effects.

---

## 19. Distinguishing Business Errors, Operation Errors, and Commit Errors

### 19.1. Business Errors

For example, insufficient funds:

~~~javascript
const result = accounts.updateOne(
  {
    _id: "ACC-A",
    balance: { $gte: amount }
  },
  { $inc: { balance: -amount } }
);

if (result.matchedCount === 0) {
  throw new Error("INSUFFICIENT_FUNDS");
}
~~~

This is not a transient server error. Immediate automatic retries will not increase the balance. The transaction should abort and return a valid error to the caller.

### 19.2. Transient Database Errors

Situations such as write conflicts or elections may require re-executing the transaction. When the driver provides the `TransientTransactionError` label, follow the API's transaction retry guidance.

Never classify errors by matching exact error message strings, as messages can change across versions or locales; use error labels and codes.

### 19.3. Unknown Commit Outcomes

When an error carries `UnknownTransactionCommitResult`, do not immediately re-run the transaction body as a new transaction. It may have already committed. Use commit retries within the same transaction/session per the driver, or reconcile business state if direct verification fails.

### 19.4. Server-Aborted Transactions

Some errors cause the server to abort the transaction. Continuing to issue writes afterward as if the transaction were still active causes secondary errors. Inspect state, abort if appropriate, and start a fresh transaction for a retry.

### 19.5. Retryable Writes Differ from Transaction Retries

**Retryable writes** operate at the level of certain individual write operations; **transaction retries** re-execute an entire group of operations or a commit. The two mechanisms do not replace each other and have distinct conditions.

---

## 20. Transactions and API Request Idempotency

### 20.1. The Replayed Request Problem

Client sends:

~~~json
{
  "requestId": "REQ-2026-001",
  "fromAccount": "ACC-A",
  "toAccount": "ACC-B",
  "amount": 200000
}
~~~

The server commits, but the response is lost in transit. The client resends the same request.

If the API simply starts a new transaction and debits/credits again, money transfers twice. MongoDB transactions ensure **atomicity of each execution**, not deduplication across separate HTTP requests.

### 20.2. Using a Stable Business ID

Create a unique index:

~~~javascript
db.transfers.createIndex(
  { requestId: 1 },
  {
    name: "uk_requestId",
    unique: true
  }
);
~~~

Inside the transaction, write the transfer record alongside account changes. A committed request ID remains persisted for future lookups.

### 20.3. API Flow to Consider

~~~text
Receive requestId
     |
     v
Completed transfer exists for requestId?
     |
     +-- Yes, payload matches ---> return existing result
     |
     +-- Yes, payload differs ---> report conflict
     |
     +-- Not found --------------> attempt transaction
                                       |
                                       +--> commit success
                                       |
                                       +--> business failure + abort
                                       |
                                       +--> transient retry
                                       |
                                       +--> unknown commit -> verify/reconcile
~~~

A production idempotency design must also handle **two concurrent requests arriving with the same `requestId`** and intermediate pending states. A unique index is an essential foundation, paired with atomic record checks and response policies.

### 20.4. Do Not Emit External Events Inside the Transaction Body

If the body contains:

~~~text
accounts.update...
emailService.send("Transfer successful")
transfers.insert...
~~~

the callback may retry, sending multiple emails even though MongoDB commits only once. Use an outbox, idempotent message processing, or an appropriate distributed pattern.

---

## 21. Transactions vs. Single-Document Operations

MongoDB guarantees atomicity for a write operation on a single document. For example, storing a shopping cart in one document:

~~~javascript
{
  _id: "CART-101",
  items: [
    { sku: "A", quantity: 1 },
    { sku: "B", quantity: 2 }
  ],
  totalItems: 3
}
~~~

If the entire update logic resides within the same document and can be expressed as one atomic update, a multi-document transaction is usually unnecessary.

Example:

~~~javascript
db.carts.updateOne(
  { _id: "CART-101" },
  {
    $inc: { totalItems: 1 },
    $push: {
      items: {
        sku: "C",
        quantity: 1
      }
    }
  }
);
~~~

A single update modifies multiple fields of one document under document atomicity. Before introducing sessions/transactions, ask:

- Must multiple documents be updated synchronously together?
- Can data sharing an invariant be modeled in one document?
- Is a single conditional update sufficient?
- Can the task be designed idempotently instead of using a large transaction?

Transactions are useful, not a replacement for document modeling.

---

## 22. Post-Commit Guarantees and Observations

### 22.1. After Successful Commit

Suppose a transaction updates A and B and commits with `w:"majority"`. The client receives confirmation per that level. Another secondary lagging behind does not contradict majority semantics.

### 22.2. Before Commit

Operations inside a transaction produce provisional results visible to the session itself. Other clients do not see them as committed changes under isolation semantics.

### 22.3. After Abort

Uncommitted writes of the transaction do not persist as final state. However:

- Previously committed transactions are unaffected.
- Operations executed outside the session are not rolled back.
- Side effects outside MongoDB are not rolled back.

### 22.4. During Failover

If the primary changes while a transaction is active, the transaction may abort or return a transient error, and the caller must handle it per the driver API. Never promise that an in-flight transaction will seamlessly survive every election without retrying.

### 22.5. Majority Commit Does Not Mean Every Secondary Has Caught Up

A three-member replica set achieves majority once the primary and one secondary acknowledge, while the third secondary may still lag. This affects secondary read preference visibility right after commit.

---

## 23. Observing Transactions in MongoDB

### 23.1. `db.currentOp()`

With appropriate privileges:

~~~javascript
db.currentOp();
~~~

You can inspect active operations and transaction details exposed by the server. Avoid relying on a single internal field name across all versions.

### 23.2. `serverStatus()`

~~~javascript
db.serverStatus();
~~~

MongoDB exposes metrics on transactions, operations, connections, and the storage engine where applicable. Exact fields and formats vary across versions.

### 23.3. Logging and Monitoring

Track:

- Active/open/aborted/committed transaction counts where exposed.
- Transaction duration (p50, p95, p99).
- Write conflicts.
- Commit latency.
- Unknown commit results.
- Retry attempts.
- Replica set elections.
- Write concern timeouts.
- Cache/memory pressure.
- Slow operations.
- Business ID reconciliation failures.

Do not measure only a single insert inside the transaction; end-to-end cost covers the whole body plus commit and retries.

### 23.4. Adding Comments/Tracing Where Supported

Many MongoDB operations support `comment` for tracing. In applications, attach request correlation IDs free of sensitive data and log error labels and retry counts with sensible limits.

---

## 24. Testing Transactions: What Must Be Proven?

### 24.1. Successful Commit

Seed A=1,000,000 and B=300,000; transfer 200,000. After commit:

- A = 800,000.
- B = 500,000.
- One transfer record exists.
- Total A+B is unchanged (assuming zero fees).

### 24.2. Abort on Business Validation

Attempt to transfer 2,000,000 from A when A has only 1,000,000. After abort:

- A remains 1,000,000.
- B remains 300,000.
- No `COMPLETED` transfer record exists.
- API returns `INSUFFICIENT_FUNDS`.

### 24.3. Missing Destination

Provisionally debit A inside the transaction, then fail to match B on update. Abort. Verify A was not debited.

### 24.4. Mid-Flight Failure

Inject an intentional fault after debiting and before crediting. Abort. Verify no partial effects persist.

### 24.5. Duplicate Request ID

Commit request `REQ-001`, then resend the same request ID. Verify no second debit occurs and the expected response is returned.

### 24.6. Concurrent Transactions

Run two concurrent transfers both debiting A. Verify balance never goes negative and retries/aborts behave properly. Use controlled concurrency tests with realistic datasets rather than a single sequential run.

### 24.7. Failover Mid-Transaction

In a staging or replica set lab environment, simulate a primary election while a transaction is running. Verify driver retry labels, API output, idempotency, and absence of double writes.

### 24.8. Unknown Commit Outcome

Simulate connection loss during commit in a test harness. Verify the application does not automatically transfer twice and reconciles by request ID.

### 24.9. Transaction Timeout

Simulate a transaction exceeding its lifetime limit in a lab environment and verify error handling. Never hold a production transaction open just to test timeouts.

### 24.10. Reading Outside the Transaction

Run an uncommitted transaction and read from a separate client. Verify only committed data is visible per chosen concerns, avoiding confusion between in-session provisional state and external visibility.

---

## 25. Practice Exercises

### Exercise 1 — A Session Is Not a Transaction

Create a session and execute two operations without calling `startTransaction`. Explain why multi-document atomicity is not provided.

### Exercise 2 — Commit

Create two accounts with initial balances. Write a transaction transferring 100,000 and inserting a transfer record. Commit and inspect all three documents.

### Exercise 3 — Abort

Write a transaction debiting an account, then explicitly abort. Prove the data remains unchanged. Explain why aborting does not undo writes from an earlier committed transaction.

### Exercise 4 — Forgetting the Session

Inside a transaction, update `accounts` using the session but insert into the transfer log using a regular non-session handle. Simulate an error before commit. Analyze why the log is not rolled back and fix the code.

### Exercise 5 — Balance Condition

Use an `updateOne` filter with `balance: {$gte: amount}` and inspect `matchedCount`. If funds are insufficient, abort and return a business error.

### Exercise 6 — Recording History

Extend Exercise 2 so the transfer log contains `requestId`, from/to, amount, status, `createdAt`, and a unique index on `requestId`. Test duplicate requests.

### Exercise 7 — Error Labels

Diagram two handling flows:

- `TransientTransactionError` → retry the entire transaction under appropriate bounds.
- `UnknownTransactionCommitResult` → retry commit / reconcile rather than blindly re-running the body.

### Exercise 8 — Java Sync Driver

Write Java code with `MongoClient`, `ClientSession`, `TransactionOptions`, two `updateOne(session, ..)`, `insertOne(session, ..)`, and commit/abort. Ensure the session is closed.

### Exercise 9 — Callback API

Convert Exercise 8 to `session.withTransaction(...)` keeping only MongoDB operations inside the callback. Explain why `emailService.send` must not be called inside the callback.

### Exercise 10 — Read/Write Concern

Select `readConcern: snapshot`, `writeConcern: majority`, and `readPreference: primary`. Explain which aspect each controls and why a majority commit does not guarantee every secondary is caught up.

### Exercise 11 — Standalone vs. Replica Set

Run a transaction on a standalone lab instance and observe the error; then test on a single-node replica set. Why does a single-node replica set support the transaction API without providing HA?

### Exercise 12 — Write Conflicts

Run two concurrent transactions updating the same account. Observe transient/write conflict errors and describe a bounded retry strategy.

### Exercise 13 — Insufficient Funds and Duplicate Transfers

In a transfer transaction, if the debit matches nothing or the request ID was already processed, abort or return the appropriate idempotent response. Build a status matrix and API response table.

### Exercise 14 — External Side Effects

Design an order creation flow that emits an `ORDER_CREATED` event only after commit. Outline an outbox solution and idempotent consumer.

### Exercise 15 — Overly Long Transactions

Suppose a transaction processes 50,000 products and calls two external APIs. Analyze lifetime, cache pressure, and retry storm risks; propose splitting into smaller atomic units.

### Exercise 16 — Sharded Transactions

Contrast a single-replica-set transaction with a distributed transaction spanning multiple shards in terms of commit coordination, latency, and failure modes. No manual implementation of internal coordination is required.

### Exercise 17 — Failover Testing

In staging, stop the primary while a transaction is active. Observe errors, retries, and final account balances. Why can't you assume failure solely from a request timeout?

### Exercise 18 — Monitoring

Propose a dashboard for transaction count, commit rate, abort rate, write conflict rate, latency, timeouts, and unknown commit results. Define thresholds/alerts grounded in real workload characteristics.

---

## 26. Review Questions

1. What is a logical session?
2. How does a session differ from a transaction?
3. Does creating a session automatically start a transaction?
4. What does `startTransaction()` do?
5. Why must every operation needing atomicity use the same session?
6. Can one session run two transactions concurrently?
7. What does `commitTransaction()` do?
8. What does `abortTransaction()` do?
9. Can an abort undo a previously committed transaction?
10. Does calling `endSession()` substitute for committing?
11. Which deployments support transactions?
12. How does a single-node replica set differ from standalone regarding the transaction API?
13. Why is write concern evaluated at commit rather than per write inside a transaction?
14. What does `ReadConcern.SNAPSHOT` provide?
15. What does `WriteConcern.MAJORITY` guarantee, and what does it not guarantee?
16. What role does `ReadPreference.primary()` play in transactions?
17. Why does a write succeeding inside a transaction not mean it is already committed?
18. Why does losing connection during commit yield an unknown outcome?
19. How do `TransientTransactionError` and `UnknownTransactionCommitResult` differ?
20. Why is retrying commit different from retrying the whole transaction?
21. Why shouldn't every business exception be retried?
22. Why can a `withTransaction` callback execute more than once?
23. Why shouldn't emails be sent inside a transaction callback?
24. How does a unique request ID aid idempotency?
25. Why is a unique index not the complete solution for idempotency?
26. Do transactions automatically prevent all race conditions or write skew?
27. When is an atomic single-document update sufficient instead of a transaction?
28. What are the costs of long-running transactions?
29. What does `transactionLifetimeLimitSeconds` usually limit?
30. Why are DDL and certain aggregation stages restricted inside transactions?
31. What extra overhead can transactions incur on sharded clusters?
32. Why should you never implement an unbounded retry loop?
33. Which metrics should be monitored when transactions abort frequently?
34. Why can a failover cause an active transaction to fail?
35. What test design proves debit/credit/ledger all-or-nothing behavior?

---

## 27. Summary

Multi-document transactions in MongoDB rely on two clear conceptual levels:

- **Session:** the logical context binding database operations together.
- **Transaction:** an atomic boundary of operations starting with `startTransaction()` and ending with `commitTransaction()` or `abortTransaction()`.

Key principles:

1. **Pass the exact same session** to every operation requiring atomicity.
2. **Keep transactions short**, with explicit business preconditions and data constraints.
3. **Commit** is the step requesting acceptance; provisional writes inside the transaction are not yet committed.
4. **Abort** discards only that transaction's uncommitted changes; it never rolls back out-of-session writes or external APIs.
5. **Unknown commit errors** differ from pre-commit transient errors and require distinct retry handling.
6. **Callback transaction APIs** reduce manual retry bugs, yet application-level request idempotency is still required.
7. **Read/write concerns** govern consistency and durability; transactions do not automatically make all operations serializable.
8. **Replica sets and sharded clusters** are the supported deployments; standalone lacks equivalent multi-document transaction support.
9. **Transactions do not replace document modeling, schema validation, or outbox/sagas** for work outside MongoDB.
10. **Test commits, aborts, concurrent updates, failovers, and timeouts** before shipping monetary or inventory workflows to production.

A good transaction does more than “run without throwing”. It accurately answers: **which changes truly belong to the same transaction, when is the outcome confirmed, what must happen if commit is uncertain, and how do we prevent a request from executing twice?**

## Official MongoDB References

- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions and Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/)
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — Transactions and Read Concern](https://www.mongodb.com/docs/manual/core/transactions/#read-concern-write-concern-read-preference)
- [MongoDB Manual — Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/)
- [MongoDB Manual — Read Concern Snapshot](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Session Commands](https://www.mongodb.com/docs/manual/reference/command/startSession/)
- [MongoDB Manual — Commit Transaction Command](https://www.mongodb.com/docs/manual/reference/command/commitTransaction/)
- [MongoDB Manual — Abort Transaction Command](https://www.mongodb.com/docs/manual/reference/command/abortTransaction/)
- [MongoDB Manual — MongoDB Shell Transactions](https://www.mongodb.com/docs/mongodb-shell/reference/methods/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver — Sessions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/#client-sessions)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
