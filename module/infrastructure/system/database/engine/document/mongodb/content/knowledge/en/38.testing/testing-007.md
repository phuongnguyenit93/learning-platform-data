# Testing Transaction Commit, Rollback, and Retries on MongoDB Replica Sets

## 1. Problem Statement: Transferring Funds Between Two Accounts When the Network Drops Right After Commit

Suppose a digital wallet application transfers **150,000 VND** from account A to account B. The data lives in two MongoDB documents:

~~~javascript
// wallet.accounts
{
  _id: "A",
  ownerId: "customer-101",
  balanceCents: NumberLong("50000000")
}
{
  _id: "B",
  ownerId: "customer-202",
  balanceCents: NumberLong("30000000")
}
~~~

In this example, **balanceCents** is an integer in minor units defined by the system; to illustrate transferring 150,000 VND, the application uses an equivalent integer per the wallet contract rather than assuming decimal places for every currency. In later code examples, this field is named **amountUnits** to avoid ambiguity. This is a technical transaction test; production financial systems require extensive additional accounting, reconciliation, and security controls.

A transfer request requires three operations:

1. Debit account A's balance.
2. Credit account B's balance.
3. Save a transfer record with **transferId** for auditing and deduplication.

If executed independently:

~~~text
Update A: success
Update B: network timeout
Insert transfer record: not executed
~~~

The system loses consistency. A **multi-document transaction** is required so changes belonging to the same business action commit or roll back as a single unit.

Yet a harder scenario arises:

~~~text
Application                     MongoDB replica set
     |                                  |
     | begin transaction                |
     | update A, update B, insert T     |
     |--------------------------------->|
     |                                  |
     | commitTransaction                |
     |--------------------------------->|
     |                                  | commit may succeed
     |            network breaks        |
     X<---------------------------------X
     |
     | "Did commit succeed?"
     | "Should I retry the transaction?"
~~~

If the application resends the **entire transfer** without idempotency, one transfer can be applied **twice**. If it skips retrying, the transaction may actually have committed while the app reports failure.

This lesson addresses three groups of questions:

- **Commit:** When do changes truly become a committed transaction?
- **Rollback/abort:** When a failure occurs before commit, does the system guarantee zero partial updates remain?
- **Retry:** Should the app retry the **whole transaction** or only **commitTransaction**, and how do you prevent duplicate business execution?

### Learning Objectives

After this lesson, you will be able to:

1. Stand up and verify a MongoDB **replica set** in a test environment.
2. Distinguish single-document atomicity from **multi-document transactions**.
3. Describe the **startTransaction → operations → commitTransaction / abortTransaction** lifecycle.
4. Understand the roles of **ClientSession**, **transaction options**, **readConcern**, **writeConcern**, and **readPreference**.
5. Write tests proving **complete commit**, **proper rollback**, and **isolation/concurrency**.
6. Distinguish error labels **TransientTransactionError** and **UnknownTransactionCommitResult**.
7. Retry at the right scope upon network errors, write conflicts, or primary failover.
8. Use **ClientSession.withTransaction()** in the Java Sync Driver and proper Spring transaction management.
9. Design **idempotency keys, unique indexes, and ledger records** to prevent duplicate business requests.
10. Practice fault injection in a lab without harming production data.
11. Test timeouts, commit retries, failover, concurrent transfers, and inspect post-failure outcomes.
12. Understand transaction boundaries with respect to external side effects and operational responsibilities.

**Key takeaway:** *Retrying a commit with an unknown outcome is not the same as re-executing the business action. MongoDB transaction atomicity does not automatically grant exactly-once semantics to HTTP requests, emails, Kafka messages, or external payment gateways.*

## 2. A Replica Set Is a Prerequisite for Transaction Testing

### 2.1. What Is a Replica Set?

A **replica set** is a group of **mongod** processes maintaining identical copies of data and electing a **primary**. Writes go to the primary and replicate to secondaries via replication.

~~~text
                    Java application
                           |
                    MongoDB driver
                           |
          +----------------+----------------+
          |                |                |
     +----v----+      +----v----+      +----v----+
     | node01  |      | node02  |      | node03  |
     | PRIMARY |----->|SECONDARY|----->|SECONDARY|
     +---------+      +---------+      +---------+
         \________ Replica set "rsLab" ________/
~~~

The diagram illustrates topology only. Actual replication paths and oplog sync sources for a secondary may differ from the arrows shown.

MongoDB multi-document transactions are supported on **replica sets and sharded clusters** per compatible MongoDB releases. This lesson focuses on **replica sets**. A `mongod` running in **standalone mode** is not equivalent to a single-node replica set: standalone does not support multi-document transactions like a replica set.

### 2.2. Single-Node Replica Set vs Three-Member Replica Set

Two test environments serve different purposes:

| Environment | What it can test | What it cannot realistically test |
|---|---|---|
| Single-node replica set | Transaction API, commit/abort, rollback logic, idempotency. | Multi-node primary election, real majority availability, replication lag. |
| Three data-bearing members | Transactions plus primary failover, replication/majority behavior. | Does not automatically mirror production hardware/network/traffic. |

You do not need three physical machines to learn transactions: three `mongod` containers or processes on one test host suffice, provided you manage URIs, ports, persistent storage, and replica-set setup properly.

### 2.3. Verifying You Are Connected to a Replica Set

In mongosh:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

On a replica set `mongod` member, output includes **setName**, primary/secondary status, and host lists. In a test environment:

~~~javascript
rs.status();
~~~

Output reports replica set members and states, though this command is intended when connected directly to a member with appropriate privileges; **do not** run `rs.status()` on `mongos` and treat it as a shard replica set's status.

### 2.4. MongoDB URI for a Replica Set

Example:

~~~text
mongodb://node01:27017,node02:27017,node03:27017/wallet
  ?replicaSet=rsLab
  &retryWrites=true
  &w=majority
~~~

This is an illustrative URI; omit line breaks in real configs. **replicaSet=rsLab** tells the driver the topology and how to discover primary/secondaries; hosts must be resolvable and reachable by the client. Production deployments also require authentication, TLS, and secrets management.

**`retryWrites=true` does not replace retry logic for multi-document transactions.** It covers supported retryable single-write operations under MongoDB semantics; transactions require handling errors via transaction labels and commit rules.

### 2.5. Majority and Durability

In a three-data-bearing-voting-member replica set, **majority** typically requires acknowledgments from a majority of voting members per configuration. Using **writeConcern: majority** on transaction commit requests majority durability acknowledgment across the replica set.

Never assume:

~~~text
Primary replied OK to one write
  => any later primary failover always retains it.
~~~

Especially under weaker write concerns, writes not yet majority-committed can be rolled back if an old primary loses leadership. Choose **transaction commit write concern** according to consistency and durability SLOs.

### 2.6. Do Not Confuse the Two Meanings of Rollback

The word **rollback** in MongoDB can refer to:

1. **Transaction abort/rollback:** discarding uncommitted changes of a multi-document transaction.
2. **Replication rollback:** a former primary rejoining a replica set and reverting writes not present in majority-committed history, depending on the failover scenario.

In this lesson, business rollback tests primarily cover **abortTransaction** and transaction atomicity. Failover sections distinguish replication durability separately.

## 3. Atomicity: Single Document vs Multiple Documents

MongoDB guarantees write atomicity at the **single-document** level, even when updating multiple fields within that document.

~~~javascript
db.accounts.updateOne(
  { _id: "A" },
  {
    $inc: { balanceUnits: -150000 },
    $set: { lastUpdatedBy: "transfer-service" }
  }
);
~~~

Both changes inside the same document execute as one atomic document update. Conversely:

~~~javascript
db.accounts.updateOne({ _id: "A" }, { $inc: { balanceUnits: -150000 } });
db.accounts.updateOne({ _id: "B" }, { $inc: { balanceUnits: 150000 } });
db.transfers.insertOne({ _id: "transfer-101", state: "COMMITTED" });
~~~

Are **not an atomic unit** when issued as three independent commands, even sequentially and even with retryable writes enabled.

### 3.1. What Does a Multi-Document Transaction Do?

A transaction groups multiple reads and writes across supported documents and collections:

~~~text
Transaction starts
  |
  +--> debit Account A
  +--> credit Account B
  +--> insert Transfer T
  |
  +--> commit
  |      all changes become committed
  |
  +--> OR abort
         no transaction writes become committed
~~~

MongoDB preserves **atomicity** for writes inside the transaction: after an abort, you never end up with “A debited without B credited.”

### 3.2. Transactions Do Not Replace Business Validation

A transaction does not automatically guarantee:

- Account A has sufficient funds.
- Account B exists.
- Both accounts share the same currency.
- The transfer has not already executed.
- The user is authorized.
- Emails or HTTP payment calls are never sent twice.

Those guarantees require **validation, predicates, indexes, business logic, and idempotency**.

### 3.3. Integer Units for Testing Atomicity

Later examples use **balanceUnits: NumberLong**:

~~~javascript
{
  _id: "A",
  currency: "VND",
  balanceUnits: NumberLong("500000")
}
{
  _id: "B",
  currency: "VND",
  balanceUnits: NumberLong("300000")
}
~~~

After transferring **150000 units**:

~~~text
A = 350000
B = 450000
A + B = 800000 (unchanged)
~~~

These illustrative values test invariants, without prescribing which minor unit a real payment system should adopt. For real currencies, define currency codes, denominations, rounding, overflow bounds, and accounting rules explicitly.

## 4. Transaction Lifecycle on ClientSession

Every transaction is driven through a MongoDB driver **ClientSession**.

~~~text
SESSION OPEN
    |
    v
startTransaction()
    |
    v
READ/WRITE OPERATIONS USING THAT SESSION
    |
    +-------------+
    |             |
    v             v
commitTransaction()    abortTransaction()
    |             |
    v             v
COMMITTED       ABORTED
    |             |
    +------v------+
           |
        close session
~~~

### 4.1. `startSession` Does Not Start a Transaction

In Java:

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction();
    // Operations MUST receive the same session.
}
~~~

**startSession()** creates a logical session. **startTransaction()** begins a transaction on that session; collection operations participate in the transaction only when passed that **session**.

### 4.2. Every Operation Must Share the Same Session

Correct:

~~~java
accounts.updateOne(
        session,
        Filters.eq("_id", "A"),
        Updates.inc("balanceUnits", -150000L)
);
~~~

Broken transactional intent:

~~~java
session.startTransaction();

// Missing session argument: this write is OUTSIDE the transaction.
accounts.updateOne(
        Filters.eq("_id", "A"),
        Updates.inc("balanceUnits", -150000L)
);

session.abortTransaction();
~~~

In the broken snippet, aborting the transaction **does not roll back** the write executed outside the session.

### 4.3. Never Run Parallel Operations on One Session/Transaction

The MongoDB Java Driver does not support concurrent operations inside the same ClientSession. Avoid:

~~~java
// Unsafe design:
CompletableFuture.runAsync(() -> accounts.updateOne(session, ...));
CompletableFuture.runAsync(() -> transfers.insertOne(session, ...));
~~~

A logical transaction should execute operations sequentially within its callback or synchronous service. For parallel workloads, use separate sessions/transactions and manage invariants/concurrency at the business layer.

### 4.4. Read Concern, Write Concern, and Read Preference

Common transaction options:

~~~java
TransactionOptions options = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

- **readPreference.primary()**: routes transaction reads/writes to the replica set primary.
- **ReadConcern.SNAPSHOT**: requests snapshot read semantics inside the transaction; exact guarantees depend on commit write concern and topology.
- **WriteConcern.MAJORITY**: requests majority commit acknowledgment.

Depending on MongoDB version, allowed `readConcern` levels may include **local, majority, snapshot** with distinct semantics. Never assume a snapshot-read transaction automatically achieves full durability unless commit is also majority-acknowledged.

**Set write concern at the transaction level, never arbitrarily on individual writes inside a transaction.**

### 4.5. Transaction Options Do Not Fix Business Logic Bugs

If code skips balance checks, a transaction will **atomically commit all three business-invalid writes**. Atomicity means “all or nothing,” not “always valid.”

For example, the debit needs a conditional predicate:

~~~javascript
{
  _id: "A",
  currency: "VND",
  balanceUnits: { $gte: NumberLong("150000") }
}
~~~

Then the application must inspect **matchedCount/modifiedCount**. If the account is missing or underfunded, the transaction must abort rather than crediting B.

### 4.6. Avoid Long-Running Transactions

Multi-document transactions carry real overhead:

- Hold snapshots/resources and increase cache pressure.
- Can hit write conflicts with concurrent transactions or writes.
- Face **transaction lifetime limits** and lock/timeout constraints per configuration.
- Consume extra oplog, replication, and recovery resources.
- Can abort on node failures or hit transaction size limits.

Never wrap **scanning 100,000 records, calling HTTP APIs, waiting for user OTP input, and then writing MongoDB** inside a multi-minute transaction. Keep external work outside, minimize operations, and keep transactions short.

## 5. Preparing Test Data on a Replica Set

The following scripts target **wallet_txn_lab** exclusively—never run them against production. Run `mongosh` connected to a test replica set with appropriate privileges.

### 5.1. Create Collections Before Transactions

~~~javascript
const lab = db.getSiblingDB("wallet_txn_lab");

lab.createCollection("accounts");
lab.createCollection("transfers");

lab.accounts.createIndex({ ownerId: 1 });
lab.transfers.createIndex({ sourceId: 1, createdAt: -1 });
~~~

Creating collections and indexes upfront avoids mixing DDL/implicit collection creation issues into transaction tests. If reusing a test environment, check whether collections already exist before calling `createCollection`, or allocate a fresh database per test.

### 5.2. Illustrative Seed Data

~~~javascript
lab.accounts.insertMany([
  {
    _id: "A",
    ownerId: "customer-101",
    currency: "VND",
    balanceUnits: NumberLong("500000")
  },
  {
    _id: "B",
    ownerId: "customer-202",
    currency: "VND",
    balanceUnits: NumberLong("300000")
  }
]);
~~~

This seed runs **outside any transaction** on an empty lab. Across repeated test runs, use isolated fixtures or unique ID prefixes; **never run `deleteMany({})` on a shared database**.

### 5.3. Unique Transfer ID as an Idempotency Key

The `transfers` collection uses a unique **_id**:

~~~javascript
{
  _id: "request-1001",
  sourceId: "A",
  destinationId: "B",
  amountUnits: NumberLong("150000"),
  currency: "VND",
  state: "COMMITTED",
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

MongoDB automatically maintains a unique index on **_id** per collection. The same **transferId** cannot appear twice as normal documents in the collection, yet a unique index alone **does not guarantee** every code path avoids double debits: business logic must inspect transaction state and transfer parameters.

### 5.4. Test Invariants

After success:

~~~text
Before:
  A = 500000
  B = 300000
  Total = 800000

After transfer of 150000:
  A = 350000
  B = 450000
  Total = 800000
  Exactly one transfer record with _id=request-1001
~~~

After abort:

~~~text
A = 500000
B = 300000
No committed transfer record for aborted request
~~~

A test must never claim “rollback succeeded” merely because an exception was thrown: **re-read committed state** and verify actual persisted data.

### 5.5. Measure Under Consistent Read Semantics

Reading from a secondary right after commit can expose replication lag and return old balances. To verify transaction success:

- Read from the **primary** or use an appropriate read concern.
- For durability guarantees, use **majority commit**.
- When read-your-writes or causal ordering is needed, manage sessions and causal consistency properly.
- Never mistake secondary lag for a rolled-back commit.

## 6. Successful Transaction Example in mongosh

### 6.1. Start Session

~~~javascript
const session = db.getMongo().startSession();
const sessionDb = session.getDatabase("wallet_txn_lab");

const accounts = sessionDb.accounts;
const transfers = sessionDb.transfers;
~~~

**Never use `lab.accounts` directly** inside this transaction if that handle was obtained outside the session. Using **sessionDb** ensures commands attach to the proper mongosh session.

### 6.2. Start, Debit, Credit, Insert, and Commit

~~~javascript
session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  readPreference: { mode: "primary" }
});

try {
  const amount = NumberLong("150000");

  const debit = accounts.updateOne(
    {
      _id: "A",
      currency: "VND",
      balanceUnits: { $gte: amount }
    },
    { $inc: { balanceUnits: NumberLong("-150000") } }
  );

  if (debit.matchedCount !== 1) {
    throw new Error("Account A missing or insufficient balance");
  }

  const credit = accounts.updateOne(
    { _id: "B", currency: "VND" },
    { $inc: { balanceUnits: amount } }
  );

  if (credit.matchedCount !== 1) {
    throw new Error("Account B missing or currency mismatch");
  }

  transfers.insertOne({
    _id: "request-1001",
    sourceId: "A",
    destinationId: "B",
    amountUnits: amount,
    currency: "VND",
    state: "COMMITTED",
    createdAt: new Date()
  });

  session.commitTransaction();
  print("Transaction committed");
} catch (error) {
  // A simple lab example. In production, do not treat
  // a commit network error as proof the commit failed.
  try {
    session.abortTransaction();
  } catch (abortError) {
    print("Abort may be unnecessary or unsuccessful: " + abortError);
  }
  throw error;
} finally {
  session.endSession();
}
~~~

**Important limitation:** this shows the **happy path and pre-commit abort** to teach the API. If **commitTransaction() throws an uncertain outcome**, the handler above does not retry by error labels. **Never copy this raw pattern directly into production payments.** The Java **withTransaction** and retry sections explain proper handling.

### 6.3. Observing Results

~~~javascript
lab.accounts.find(
  { _id: { $in: ["A", "B"] } },
  { _id: 1, balanceUnits: 1, currency: 1 }
);

lab.transfers.findOne({ _id: "request-1001" });
~~~

Expected: A=350000, B=450000, and exactly one transfer record.

### 6.4. Why Does the Test Need the Third Record?

If you only check debit and credit, you could miss:

~~~text
Balances committed, transfer receipt missing
~~~

Placing the transfer record **inside the same transaction** forces all three writes to commit or abort together. In real systems, that receipt also powers auditing, idempotency, and reconciliation.

### 6.5. Commit Does Not Equal Sending HTTP 200

Example:

~~~text
MongoDB transaction committed
       |
       v
HTTP connection breaks
       |
       v
Client retries POST /transfer
~~~

A lost HTTP response **does not roll back** the database. Business endpoints must use a stable idempotency key and return the persisted outcome when the client retries.

## 7. Rollback/Abort Example in mongosh

Objective: trigger a failure **mid-transaction** and prove zero “half-written” state remains.

### 7.1. Deliberately Injecting an Error After Debit

Prepare a new transferId **request-abort-01** using the seeded accounts (or an isolated fixture). In mongosh:

~~~javascript
const s2 = db.getMongo().startSession();
const db2 = s2.getDatabase("wallet_txn_lab");

s2.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
});

try {
  db2.accounts.updateOne(
    {
      _id: "A",
      balanceUnits: { $gte: NumberLong("10000") }
    },
    {
      $inc: { balanceUnits: NumberLong("-10000") }
    }
  );

  // Test-only failure before credit and insert receipt.
  throw new Error("Injected application failure");

  // Unreachable:
  // db2.accounts.updateOne(... credit B ...);
  // db2.transfers.insertOne(...);
  // s2.commitTransaction();
} catch (err) {
  s2.abortTransaction();
  print("Transaction aborted: " + err.message);
} finally {
  s2.endSession();
}
~~~

### 7.2. Verifying Rollback

~~~javascript
lab.accounts.find(
  { _id: { $in: ["A", "B"] } },
  { balanceUnits: 1 }
);

lab.transfers.countDocuments({
  _id: "request-abort-01"
});
~~~

Expected: A/B balances are **unchanged compared to before the abort test** and zero records exist for that transfer ID.

### 7.3. Abort Due to Insufficient Funds

If the debit predicate fails to match:

~~~javascript
{
  _id: "A",
  balanceUnits: { $gte: NumberLong("999999999") }
}
~~~

then **matchedCount=0**; business logic must abort. MongoDB does not treat `matchedCount=0` as an exception or transaction error. **A zero-match update is valid MongoDB behavior** unless application code checks it and explicitly rejects.

### 7.4. Abort Due to Missing Recipient

If A was debited inside the transaction yet crediting B matches nothing or B was concurrently deleted, logic must throw and abort. Afterward verify A was not debited.

### 7.5. Abort Due to Unique Constraint

If inserting a transfer record collides on **_id** with an existing record, MongoDB throws a duplicate key error under standard conditions. The transaction fails and must be handled properly:

- Never infinitely retry a duplicate key representing a business conflict.
- Check whether **the existing record has matching request parameters**.
- If same idempotency key yet different parameters, return **conflict**.
- If the exact request already completed, return the prior result per API contract.

Never “work around” a duplicate key by inventing a new transferId and debiting again.

### 7.6. Aborting After Commit Is Semantically Impossible

~~~text
startTransaction
  -> debit/credit
commit succeeded
  -> client later wants to undo
~~~

Once commit succeeds, **abortTransaction() cannot undo a committed transaction**. To issue a refund, business logic must execute a new **compensating transaction** with proper auditing and references. That is a business reversal, not a rollback of the prior transaction.

## 8. Distinguishing Pre-Commit Errors, Transient Errors, and Unknown Commit Outcomes

Not every exception shares the same retry rule. Distinguish **which phase failed**, **what error labels are attached**, and **whether the transaction could already have committed**.

### 8.1. Pre-Commit Business Errors

Examples:

- Insufficient balance.
- Destination account does not exist.
- Currency mismatch.
- Idempotency key reused with different parameters.

~~~text
Start transaction
  -> business predicate fails
  -> abort
  -> return a business failure
~~~

Never retry blindly while the account still lacks funds or inputs are invalid.

### 8.2. TransientTransactionError — Retry the Whole Transaction

The MongoDB driver/server can label temporary transaction failures as **TransientTransactionError**—such as certain write conflicts, primary failovers, or connection drops per release semantics.

~~~text
Error labeled TransientTransactionError
       |
       v
Discard unsuccessful attempt
       |
       v
Start a NEW transaction attempt
       |
       v
Rerun all reads and writes with current conditions
~~~

**Retrying the whole transaction** means re-executing reads and writes in a fresh attempt. Never continue an aborted transaction or replay a single write in isolation.

### 8.3. UnknownTransactionCommitResult — Retry Commit

If the client sends **commitTransaction** and disconnects or receives an indeterminate error, errors may carry the label **UnknownTransactionCommitResult**:

~~~text
Transaction body completed
        |
        v
commitTransaction sent
        |
        X response lost
        |
        v
UnknownTransactionCommitResult
        |
        v
Retry commitTransaction
for SAME transaction/session
~~~

**This is NOT a signal to immediately rerun the body.** The first attempt may already have committed, so rerunning debit/credit in a new transaction risks double transfers without idempotency.

### 8.4. Duplicate Key and Non-Transient Errors

A duplicate transfer ID is not automatically transient. Handle it by:

1. Reading the transfer record for that ID.
2. Comparing all immutable request parameters.
3. If identical and committed, returning the stored result.
4. If same ID yet different parameters, returning conflict.
5. If outcome remains uncertain, reconciling or retrying under bounded policy.

Never swap transferIds arbitrarily to bypass a unique constraint.

### 8.5. Decision Table

| Error / situation | Action |
|---|---|
| Pre-commit validation fails | Abort and return business error. |
| **TransientTransactionError** in body | Retry **whole transaction** in a fresh attempt. |
| **UnknownTransactionCommitResult** on commit | Retry **commit of the same transaction**. |
| Duplicate transfer ID | Reconcile existing record, verify parameters. |
| HTTP response lost after commit | Client resends with same idempotency key; server returns prior result. |
| Prolonged primary outage | Bounded retry/backoff, return indeterminate status when needed, reconcile. |
| Code/schema/permission error | Fix the bug; never retry blindly. |

### 8.6. Inspecting Error Labels in Java

~~~java
if (exception.hasErrorLabel("TransientTransactionError")) {
    // Retry transaction body in a new attempt.
}

if (exception.hasErrorLabel("UnknownTransactionCommitResult")) {
    // Retry commit, not the entire body immediately.
}
~~~

This snippet illustrates **classification only**. Never write a naive manual loop around two `if` statements while ignoring session/commit state or time budgets.

### 8.7. Retryable Writes Differ from Transaction Retries

| Mechanism | Scope |
|---|---|
| **Retryable write** | Supported single-write operations, typically outside multi-document transactions. |
| **Transaction body retry** | Rerunning reads/writes after transient errors. |
| **Commit retry** | Resending commit for the same transaction when outcome is uncertain. |
| **HTTP retry** | A fresh business request arriving at the service; requires an idempotency key. |
| **Message redelivery** | Consumer receiving an old event again; requires deduplication. |

**`retryWrites=true`** does not automatically provide exactly-once semantics for multi-step HTTP requests.

## 9. Java Sync Driver: Transaction Callback with `withTransaction`

The MongoDB Java Sync Driver provides **ClientSession.withTransaction(...)**. The driver manages the transaction lifecycle and retries supported error labels according to driver specifications, reducing the risks of hand-rolled retry loops.

### 9.1. Transaction Options

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

TransactionOptions txOptions = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

Prerequisites: compatible driver/server, replica set URI, collections/indexes already created, proper permissions, and an application timeout policy.

### 9.2. Domain Request Carrying an Idempotency Key

~~~java
package com.example.wallet;

public record TransferRequest(
        String transferId,
        String sourceId,
        String destinationId,
        String currency,
        long amountUnits) {

    public TransferRequest {
        if (transferId == null || transferId.isBlank()
                || sourceId == null || sourceId.isBlank()
                || destinationId == null || destinationId.isBlank()) {
            throw new IllegalArgumentException(
                    "Transfer and account IDs are required");
        }
        if (sourceId.equals(destinationId)) {
            throw new IllegalArgumentException(
                    "Source and destination must differ");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException(
                    "Currency is required");
        }
        if (amountUnits <= 0) {
            throw new IllegalArgumentException(
                    "Transfer amount must be positive");
        }
    }
}
~~~

Owner validations, access permissions, currency normalization, and business transaction limits must be added in real systems.

### 9.3. Passing the Same ClientSession to Every Command

~~~java
package com.example.wallet;

import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;
import java.util.Objects;

public final class TransferService {

    private static final TransactionOptions TX_OPTIONS =
            TransactionOptions.builder()
                    .readPreference(ReadPreference.primary())
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(WriteConcern.MAJORITY)
                    .build();

    private final MongoClient client;
    private final MongoCollection<Document> accounts;
    private final MongoCollection<Document> transfers;

    public TransferService(MongoClient client) {
        this.client = Objects.requireNonNull(client);
        var database = client.getDatabase("wallet_txn_lab");
        accounts = database.getCollection("accounts");
        transfers = database.getCollection("transfers");
    }

    public Document transfer(TransferRequest request) {
        Objects.requireNonNull(request);

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                Document existing = transfers.find(
                        session,
                        Filters.eq("_id", request.transferId())
                ).first();

                if (existing != null) {
                    verifySameRequest(existing, request);
                    return existing;
                }

                UpdateResult debit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", request.sourceId()),
                                Filters.eq("currency", request.currency()),
                                Filters.gte(
                                        "balanceUnits",
                                        request.amountUnits())
                        ),
                        Updates.inc(
                                "balanceUnits",
                                -request.amountUnits())
                );

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Source missing, wrong currency, "
                                    + "or insufficient funds");
                }

                UpdateResult credit = accounts.updateOne(
                        session,
                        Filters.and(
                                Filters.eq("_id", request.destinationId()),
                                Filters.eq("currency", request.currency())
                        ),
                        Updates.inc(
                                "balanceUnits",
                                request.amountUnits())
                );

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                            "Destination missing or wrong currency");
                }

                Document receipt = new Document(
                        "_id",
                        request.transferId()
                ).append("sourceId", request.sourceId())
                 .append("destinationId", request.destinationId())
                 .append("amountUnits", request.amountUnits())
                 .append("currency", request.currency())
                 .append("state", "COMMITTED")
                 .append("createdAt", new Date());

                transfers.insertOne(session, receipt);
                return receipt;
            }, TX_OPTIONS);
        }
    }

    private static void verifySameRequest(
            Document existing,
            TransferRequest request) {

        Object amount = existing.get("amountUnits");
        boolean same = request.sourceId().equals(
                existing.getString("sourceId"))
                && request.destinationId().equals(
                        existing.getString("destinationId"))
                && request.currency().equals(
                        existing.getString("currency"))
                && amount instanceof Number
                && request.amountUnits()
                        == ((Number) amount).longValue();

        if (!same) {
            throw new IllegalStateException(
                    "Idempotency key reused with different parameters");
        }
    }
}
~~~

### 9.4. `withTransaction` Can Invoke the Body Multiple Times

The driver can retry the callback in a fresh transaction attempt after transient failures. Hence, **the body must be safe to re-execute**:

- Never send emails inside the callback.
- Never call external payment REST APIs inside the callback.
- Never publish Kafka events directly inside the callback.
- Never generate a new `transferId` per attempt.
- Never emit side-effect logs without deduplication.

**`transferId` must remain stable across attempts and HTTP retries.** In the snippet, `createdAt` calls `new Date()` and may differ across aborted attempts; if business rules require a fixed request timestamp, generate it before the callback and pass it inside `TransferRequest`.

### 9.5. `withTransaction` Does Not Replace Business Idempotency

The transaction callback retries internally, yet a fresh HTTP POST creates a **brand-new ClientSession and transaction**:

~~~text
POST /transfers, transferId=abc
    -> MongoDB transaction commits
    -> HTTP response lost

POST /transfers, transferId=abc again
    -> must return previous result
    -> must NOT debit again
~~~

Checking `transferId` before debiting combined with the unique **_id** on `transfers` enforces database idempotency alongside business parameter checks.

### 9.6. Two Concurrent Requests with the Same ID

Two requests can both read “transfer does not exist yet” before either commits. **Unique `_id`** prevents two receipt records with the same ID, while the transaction guarantees the failed attempt leaves no partial debit/credit behind.

However, the losing request may hit a **duplicate key or write conflict**. The API layer must:

1. Classify errors after driver retries complete.
2. Re-read `transferId` with appropriate read consistency.
3. Verify `sourceId`/`destinationId`/`currency`/`amount` match.
4. Return the existing result when it represents the same business request.
5. Return conflict if the key matches yet parameters differ.
6. If outcome remains unclear, use **bounded reconciliation** rather than blindly debiting again.

### 9.7. Bounded Retries

Every retry requires **a deadline, bounded attempts or time window, backoff/jitter where appropriate, and error observability**. Driver `withTransaction` retries supported labeled errors, yet cannot make a transaction succeed indefinitely if the cluster stays down.

## 10. Manual Retry Model: Which Scope Gets Repeated?

Without **withTransaction**, the application manages the transaction lifecycle and error branches itself. Studying this model clarifies semantics, though **you should never turn a naive short loop into a production transaction manager**.

### 10.1. Two Distinct Loops

~~~text
OUTER LOOP: transaction attempt
  |
  v
startTransaction
  |
  v
execute body
  |
  +-- TransientTransactionError? --> abort attempt, retry OUTER
  |
  v
INNER LOOP: commit of THIS attempt
  |
  v
commitTransaction
  |
  +-- UnknownTransactionCommitResult? --> retry INNER
  |
  +-- known success --> return success
  |
  +-- known non-retryable failure --> stop/reconcile
~~~

**Never** turn `UnknownTransactionCommitResult` into an automatic signal to debit/credit all over again.

### 10.2. Deadline-Bounded Pseudocode

~~~text
deadline = now + configuredRetryBudget

while timeRemaining(deadline):
    start a new transaction attempt

    try:
        execute transaction reads/writes
    catch error:
        bestEffortAbort()

        if error has TransientTransactionError:
            backoffAndRetryWholeAttempt()
            continue

        throw error

    while timeRemaining(deadline):
        try:
            commit SAME transaction
            return COMMITTED
        catch error:
            if error has UnknownTransactionCommitResult:
                backoffAndRetryCommitOnly()
                continue
            throw error

    return UNKNOWN_NEEDS_RECONCILIATION

return RETRY_BUDGET_EXHAUSTED
~~~

This pseudocode highlights the two retry scopes; real implementations must follow driver transaction specifications, including **session state, commit errors, server selection, cancellation, retry budgets, and exception labels**. When the deadline expires with an uncertain commit outcome, never assume the transaction aborted.

### 10.3. Retrying Commit Uses the Same Transaction Identity

For a commit retry to be valid, the client must retain the exact **logical session and transaction identity** (session ID and transaction number managed by the driver). Never start a new transaction and call it a “commit retry.”

Never tamper with or spoof **lsid/txnNumber** via raw BSON in application code. Use the driver's **ClientSession API**.

### 10.4. Errors That Must Never Be Auto-Retried

If the server reports an update matched nothing:

~~~text
matchedCount=0
reason=insufficient funds
~~~

that is a business outcome to handle, not a labeled transient failure. Retrying 100 times when nobody deposited funds only spikes DB load and slows the API.

### 10.5. Bounded Retries, Backoff, and Overload

On an overloaded or electing cluster:

~~~text
100 application instances
  x 500 requests
  x immediate retry loop
  = retry storm
~~~

Apply:

- Request-level retry budgets/deadlines.
- Exponential backoff with jitter where appropriate.
- Circuit breakers/admission control during outages.
- Metrics for attempts, transient errors, and unknown outcomes.
- Idempotency and reconciliation for timed-out requests.

The driver already has its own retry policy. Avoid wrapping **withTransaction** in multiple stacked infinite retry loops across controller, service, and message consumer layers.

## 11. Designing a Transaction Test Matrix

A thorough test suite asks more than “did commit succeed without throwing?” It verifies **post-failure state**, **retry scopes**, **durability**, and **business idempotency**.

### 11.1. Core Matrix

| Scenario | Error / condition | Post-test expectation |
|---|---|---|
| Happy commit | No errors, sufficient funds | A decreases, B increases, exactly one receipt, total conserved. |
| Explicit abort | Throws after debit | Committed balances unchanged, no receipt. |
| Missing recipient | B does not exist | Debit on A rolled back, no receipt. |
| Insufficient funds | Debit predicate mismatches | Zero data changes, returns business error. |
| Currency mismatch | B uses different currency | Neither debit, credit, nor receipt commits. |
| Duplicate ID, same parameters | Request resent after commit | Returns prior result, no second debit. |
| Duplicate ID, different parameters | Key reused with different amount | Conflict, no second debit. |
| Transient error before commit | Write conflict or failover | Driver retries whole body; commits once or fails cleanly. |
| Unknown commit outcome | Commit reply lost | Retries commit/reconciles; never blindly reruns body. |
| Primary stepdown | Failover mid-attempt | Recovers/retries per labels, invariants hold. |
| Parallel distinct transfer IDs | Two requests share source balance | Never goes negative beyond policy; totals/receipts consistent. |
| Read from secondary | Replication lag | Never confuse stale read with abort; assert per read concern. |
| Retry budget exhausted | Prolonged DB outage | API reports failure/unknown appropriately; reconciliation resolves outcome. |
| External side effect | Callback replayed | No uncontrolled duplicate emails/publishes. |

### 11.2. Commit Tests Must Inspect More Than Return Values

~~~text
Given:
  A = 500000, B = 300000

When:
  commit transfer 150000 with ID=req-1

Then:
  A = 350000
  B = 450000
  sum(A,B) = 800000
  exactly 1 transfer record _id=req-1
  receipt parameters match request
~~~

Testing **business invariants** is far stronger than checking a single status field.

### 11.3. Rollback Tests Must Read Back After Abort

~~~text
Given:
  A = 500000, B = 300000

When:
  debit A inside transaction
  inject failure before credit
  abort

Then:
  A = 500000
  B = 300000
  no receipt from aborted transaction
~~~

Never treat an exception being thrown as proof of rollback. If the debit accidentally ran outside the session, abort still runs while the balance changed!

### 11.4. Testing Visibility of Partial Writes

Inside an uncommitted transaction, the same session observes its own writes (read-your-own-writes). External readers using appropriate read semantics **must not observe uncommitted partial transaction writes as committed state**.

Test design:

1. T1 starts and debits A without committing yet.
2. T2 performs an independent read under the chosen consistency level.
3. T1 aborts.
4. T2 / a fresh reader confirms zero partial committed state exists.

Never use a lagging secondary reader to draw conclusions about fresh write visibility.

### 11.5. Testing Concurrent Updates

Two transfers sharing the same source:

~~~text
A balance = 200 units

T1: A -> B, 150 units, ID=req-1
T2: A -> C, 150 units, ID=req-2
~~~

If overdrafts are forbidden, **both debits cannot succeed** for a total of 300 units. The **balanceUnits >= amount** predicate plus transaction write-conflict handling enforce this constraint. One attempt may retry on a fresh snapshot and then detect insufficient funds.

Verification conditions:

~~~text
A >= 0
sum(A,B,C) unchanged
at most one 150-unit transfer committed
each committed receipt corresponds to one debit/credit
~~~

### 11.6. Tests Must Never Rely Solely on Sleep

Never write:

~~~text
sleep(100)
assert failover completed
~~~

Elections, reconnects, and replication take variable durations. Use **deadline-bounded polling** for observable conditions (new primary elected, committed record visible, replica healthy) and fail with diagnostics if the deadline expires.

### 11.7. Never Disguise UNKNOWN as FAIL

An indeterminate commit outcome differs from a confirmed abort:

~~~text
ABORTED:
  transaction was not committed

COMMITTED:
  transaction committed and known

UNKNOWN:
  client cannot determine final commit outcome yet
~~~

APIs and reconciliation jobs must handle `UNKNOWN` explicitly. Never fire an automatic refund merely because the commit reply timed out: if the first transaction actually committed, an unverified reversal creates new errors.

## 12. Testing with a Single-Node Replica Set

A single-node replica set works well for **commit/abort smoke tests and converter/session wiring**. It cannot realistically test multi-node majority failover.

### 12.1. Starting a Lab `mongod`

Example **solely on a lab machine** with `mongod` installed and a dedicated data directory:

~~~bash
mkdir -p /tmp/mongodb-txn-lab
mongod \
  --replSet rsLab \
  --bind_ip localhost \
  --port 27017 \
  --dbpath /tmp/mongodb-txn-lab
~~~

On Windows, Docker, or Kubernetes, directory and process startup differ; this shell snippet targets a Unix-like test environment. Never reuse a port or `dbpath` holding important MongoDB data.

In a separate `mongosh`:

~~~javascript
rs.initiate({
  _id: "rsLab",
  members: [
    { _id: 0, host: "localhost:27017" }
  ]
});
~~~

Then verify:

~~~javascript
rs.status();
db.adminCommand({ hello: 1 });
~~~

Wait until the node becomes **PRIMARY** before running transaction tests.

### 12.2. Why Is Single-Node Sufficient for Getting Started?

A one-node replica set still runs session transactions on supported versions. It verifies:

- Does the application create a `ClientSession` properly?
- Do all writes pass through the same session?
- Do commit and abort behave properly?
- Is the unique transfer ID enforced?
- Do domain/business predicates hold?

Never use a single-node setup to draw conclusions about primary-loss resilience, multi-node majority writes, or secondary reads.

### 12.3. When Are Three Members Required?

Scenarios requiring **at least a multi-node replica set test**:

- Elections and primary stepdowns.
- Majority write concern when one node is unavailable.
- Replication lag.
- Secondary reads after commit.
- Node partitions and reconnects.
- Durable commits across failover.

In production, members, votes, priorities, disks, and network topology must follow HA design; three containers on one host **do not prove** resilience to whole-host failure.

## 13. Fault Injection: Testing Failures Safely Without Breaking Production

Retry tests only mean something when they reproduce tricky failure windows:

- Connection drops mid-transaction body.
- Write conflicts during updates.
- Primary elections before commit completes.
- Connection closed before commit acknowledgment reaches the client.
- Secondary lag or replication unavailability.

**Every fault-injection experiment must run on an isolated lab replica set** with test data and authorized accounts. Never run failpoints, stepdowns, process kills, or connection-breaking proxies against production or shared environments without dedicated change/incident procedures.

### 13.1. Three Levels of Fault Injection

| Level | Mechanism | Determinism |
|---|---|---|
| Application-level | Throw exception after debit, before credit. | High; tests abort logic, not server/network. |
| Server command-level | Supported test failpoints like **failCommand**. | Reproduces command errors; version/config dependent. |
| Infrastructure/network | Proxy drops connections, node stepdown, partitions. | Tests real network/election behavior; timing harder to synchronize. |

Start with **application-level** faults before introducing deeper fault injection.

### 13.2. `failCommand` Failpoint Is Strictly for Test Environments

MongoDB provides **failpoints** to inject command-level faults in supported builds/configurations. A test-only example:

~~~javascript
db.adminCommand({
  configureFailPoint: "failCommand",
  mode: { times: 1 },
  data: {
    failCommands: ["commitTransaction"],
    closeConnection: true
  }
});
~~~

This deliberately drops the connection on the `commitTransaction` command where supported. **It does not guarantee the commit already executed before the drop**: the failpoint may fire before the command executes on the server.

Consequently, tests must allow both realistic outcomes and verify:

1. Did the client/driver classify exceptions and error labels accurately?
2. Did the driver retry commit or report unknown per contract?
3. Once settled, does the database hold **0 or 1 commit** for that `transferId`, never a double debit?
4. Did the business request reconcile via idempotency key?

**Never** run `failCommand` and claim you proved “server committed yet client lost the reply” without explicit timing synchronization.

### 13.3. Disabling the Failpoint After Testing

In the test environment on the configured node:

~~~javascript
db.adminCommand({
  configureFailPoint: "failCommand",
  mode: "off"
});
~~~

Failpoints require special privileges/config and may be unavailable on managed deployments. If denied, use a supported network proxy or test harness; **never relax production permissions** just to run an exercise.

### 13.4. Reproducing Unknown Outcomes with a Network Proxy

An advanced technique places a test proxy between the client and replica set so scripts control client→server and server→client traffic in the lab.

~~~text
Java test client
      |
      v
Network fault proxy
      |
      v
Replica set primary
~~~

Scenario goals:

1. Transaction body finishes.
2. Commit is sent.
3. Server→client reply channel breaks.
4. Driver handles the unknown outcome.
5. Test reads receipt and balances once the network recovers.

Controlling the exact **post-commit, pre-reply** window may require a specialized protocol-aware test proxy. Without tight timing control, report “injected network fault near commit” and verify invariants without fabricating certainty.

### 13.5. Primary Stepdown in a Multi-Node Replica Set

On a **test primary** with healthy secondaries:

~~~javascript
rs.stepDown(15);
~~~

This steps down the primary for the configured duration per supported semantics. An election and driver topology discovery ensue; an in-flight transaction may fail and need a retry.

What to measure:

- Which error and labels did the driver receive?
- How long did electing a new primary take?
- Did any transaction abort?
- Did any request report unknown commit?
- Do balances and receipts satisfy invariants after recovery?
- Were majority-acknowledged commits preserved?

Never run `stepDown` carelessly on a single-node replica set with no secondaries to elect.

### 13.6. Where to Inject Faults?

Define distinct fault points:

~~~text
F1: before startTransaction
F2: after first debit
F3: after second credit
F4: after receipt insert, before commit
F5: during commit request/response
F6: after confirmed commit, before HTTP response
~~~

Each answers a different question:

- F2–F4: rollback atomicity on transaction abort.
- F5: commit result ambiguity and commit retries.
- F6: **application-level idempotency** after DB commit.

A suite injecting only at F2 proves nothing about F5 or F6.

### 13.7. Do Not Stack Multiple Faults in Initial Tests

If you simultaneously step down the primary, throttle disks, drop packets, and trigger write conflicts, failures become opaque. Start with one isolated fault and clear expected outcomes before running combined chaos tests.

## 14. Testing Transactions Across Primary Failover

### 14.1. Key Milestones

~~~text
T0: start transaction on primary P1
T1: debit and credit
T2: commit attempt
T3: P1 steps down / network interrupted
T4: P2 becomes primary
T5: client reconnects and resolves/retries
T6: verify balances + transfer receipt
~~~

To troubleshoot cleanly, log **sanitized attempt IDs, transfer IDs, error labels, cluster time/session context**, and event timestamps.

### 14.2. Pre-Commit Failures

If failover occurs before commit, the in-flight attempt usually cannot continue and the driver signals a transient error. Retrying requires:

1. A new transaction attempt.
2. Re-reading account balances.
3. Re-evaluating funds, currency, and idempotency.
4. Committing on the new primary under transaction options.

Never reuse stale document snapshots to perform an unguarded debit.

### 14.3. Failures Around Commit

If the network breaks around commit, the outcome is uncertain. **Never infer from the old primary disappearing that the transaction definitely aborted.**

Only a driver-compliant commit retry or reconciliation via **transferId** establishes the business outcome safely.

### 14.4. Majority Write Concern

Durability tests must distinguish:

~~~text
Commit acknowledged with majority
    vs
Commit acknowledged under weaker concern
~~~

Getting a reply from one primary is insufficient to prove majority durability if options used a weaker write concern. In a three-member replica set, when majority is lost, majority writes block or fail per timeouts/config, and the application must tolerate indeterminate states.

### 14.5. Secondary Reads After Failover

After a transaction commits, a secondary may lag behind:

~~~text
Read from primary: new balance
Read from lagging secondary: old balance
~~~

Never misinterpret temporary lag as a partial transaction commit. Specify **read preference, read concern, and causal session guarantees** in tests so replication lag is never mistaken for rollback.

### 14.6. Never Infer “Exactly Once” from Majority

Majority commit strengthens database durability. It **does not** stop an HTTP client from resending the full business request after a dropped response. **Exactly-once business effects** require idempotency keys, unique constraints, and reconciliation.

## 15. Spring Data MongoDB: MongoTransactionManager

In Spring applications, **MongoTransactionManager** integrates MongoDB transactions with **@Transactional**.

### 15.1. Configuring the Transaction Manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

Configuration APIs and default transaction options can vary by Spring Data MongoDB version. When specific **snapshot/majority** guarantees are required, configure explicit transaction options on `MongoTransactionManager` rather than assuming defaults match the Java Driver example.

### 15.2. Using `@Transactional`

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletApplicationService {

    private final MongoTemplate template;

    public WalletApplicationService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void transferOnce(
            String transferId,
            String sourceId,
            String destinationId,
            long amountUnits) {

        Query debitQuery = Query.query(
                Criteria.where("_id").is(sourceId)
                        .and("balanceUnits").gte(amountUnits)
        );

        var debit = template.updateFirst(
                debitQuery,
                new Update().inc("balanceUnits", -amountUnits),
                "accounts"
        );

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Source missing or insufficient funds");
        }

        Query creditQuery = Query.query(
                Criteria.where("_id").is(destinationId)
        );

        var credit = template.updateFirst(
                creditQuery,
                new Update().inc("balanceUnits", amountUnits),
                "accounts"
        );

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Destination missing");
        }

        template.insert(
                new org.bson.Document("_id", transferId)
                        .append("sourceId", sourceId)
                        .append("destinationId", destinationId)
                        .append("amountUnits", amountUnits)
                        .append("state", "COMMITTED"),
                "transfers"
        );
    }
}
~~~

This demonstrates **transaction demarcation**, not a complete transfer service: add currency checks, permissions, idempotency lookup, and duplicate concurrency handling as in the Java Driver example. Transactional methods work only when Spring's **transaction interceptor** actually wraps the call.

### 15.3. Spring Session Binding

When calling `MongoTemplate` or `MongoRepository` inside a properly managed transactional method, Spring Data binds the session to the active transaction context.

Never instantiate a separate `MongoClient` inside the method or invoke raw driver calls without the bound session, as those run outside the Spring-managed transaction.

### 15.4. `@Transactional` Rollback Rules

By default, Spring **rolls back on unchecked exceptions** (`RuntimeException` and `Error`), while checked exceptions may require explicit **rollbackFor** rules. If a method catches exceptions and returns normally:

~~~java
@Transactional
public void badExample() {
    try {
        // debit...
        // credit fails...
    } catch (Exception ex) {
        // Swallows exception; transaction manager may commit.
    }
}
~~~

never assume the transaction aborts automatically. Rethrow the exception or mark rollback via supported Spring APIs and policies.

### 15.5. Self-Invocation and Proxies

If another method in the same bean calls a **@Transactional** method directly via **this.transferOnce(...)**, Spring's proxy-based transaction interception is **bypassed**.

Integration tests must prove transactions actually engage when invoked normally through the Spring bean proxy. Seeing `@Transactional` in source code is not proof transactions are active.

### 15.6. `@Transactional` Does Not Automatically Handle Retries

**`MongoTransactionManager`/`@Transactional` mainly manages start, commit, and rollback.** It does not automatically replicate Java Driver `withTransaction` callback retries across all versions and failure modes.

To handle transient retries, implement policy at an **outer orchestration layer** so each retry enters a **fresh transactional proxy invocation**, rather than looping inside a failed transaction.

For **UnknownTransactionCommitResult**, never simply rerun the entire `@Transactional` method without business idempotency and reconciliation; understand Spring transaction completion and driver commit semantics for your version.

### 15.7. Never Mix Transaction Managers Carelessly

Applications combining **DataSourceTransactionManager/JpaTransactionManager** with **MongoTransactionManager** must specify the right manager explicitly. A plain `@Transactional` may open only a SQL transaction, leaving Mongo operations outside that atomic unit.

MongoDB transactions **do not form distributed ACID transactions with SQL, Kafka, or HTTP services**. Coordinating external systems requires outbox, saga, or other explicit patterns.

## 16. Unit and Integration Tests for Commit/Abort in Java

For MongoDB transactions, **unit tests with mocked repositories cannot verify server atomicity**. You need at least an **integration suite connected to a real replica set** asserting persisted state.

### 16.1. What Does Each Testing Layer Prove?

| Layer | What it verifies | What it cannot prove |
|---|---|---|
| Domain unit test | Input validation, amounts, parameter mismatches. | Server commit/rollback. |
| Mocked transaction service | Call ordering, exception propagation. | Data actually rolled back on server. |
| Single-node replica set integration | Session wiring, commit/abort, unique index/idempotency. | Multi-node failover, majority availability. |
| Three-node replica set integration | Elections, majority commit, retry behavior, secondary lag. | All production failure modes. |
| End-to-end / API test | HTTP timeouts/retries, responses, business idempotency. | External boundaries unless broker/gateway simulated. |

### 16.2. Happy Path Test

Example with JUnit 5 using **MONGODB_TEST_URI** targeting a test replica set with unique fixture IDs:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.UUID;

public class TransferIntegrationTest {

    @Test
    void commitUpdatesBothAccountsAndReceipt() {
        String uri = System.getenv("MONGODB_TEST_URI");
        assertNotNull(uri, "Use a dedicated test replica set");

        try (MongoClient client = MongoClients.create(uri)) {
            var database = client.getDatabase("wallet_txn_lab");
            MongoCollection<Document> accounts =
                    database.getCollection("accounts");
            MongoCollection<Document> transfers =
                    database.getCollection("transfers");

            String prefix = "it-" + UUID.randomUUID();
            String sourceId = prefix + "-source";
            String destinationId = prefix + "-destination";
            String transferId = prefix + "-transfer";

            accounts.insertMany(List.of(
                    new Document("_id", sourceId)
                            .append("currency", "VND")
                            .append("balanceUnits", 500000L),
                    new Document("_id", destinationId)
                            .append("currency", "VND")
                            .append("balanceUnits", 300000L)
            ));

            var service = new TransferService(client);
            var receipt = service.transfer(
                    new TransferRequest(
                            transferId,
                            sourceId,
                            destinationId,
                            "VND",
                            150000L
                    )
            );

            Document source = accounts.find(
                    new Document("_id", sourceId)
            ).first();
            Document destination = accounts.find(
                    new Document("_id", destinationId)
            ).first();

            assertNotNull(source);
            assertNotNull(destination);
            assertEquals(350000L,
                    source.getLong("balanceUnits"));
            assertEquals(450000L,
                    destination.getLong("balanceUnits"));
            assertEquals(800000L,
                    source.getLong("balanceUnits")
                            + destination.getLong("balanceUnits"));

            assertEquals(transferId, receipt.getString("_id"));
            assertEquals(1L, transfers.countDocuments(
                    new Document("_id", transferId)
            ));
        }
    }
}
~~~

This is a lab test pattern without automatic cleanup yet. In real test suites, **isolate databases/collections or delete only test-owned ID prefixes**, never wiping shared collections. Assertions on majority durability must use appropriate read preference and read concern.

### 16.3. Testing Abort After Debit

~~~java
try (ClientSession session = client.startSession()) {
    session.startTransaction(txOptions);

    try {
        accounts.updateOne(
                session,
                Filters.eq("_id", sourceId),
                Updates.inc("balanceUnits", -10000L)
        );

        throw new IllegalStateException(
                "Simulated failure after debit");
    } catch (IllegalStateException ex) {
        session.abortTransaction();
    }
}

Document source = accounts.find(
        Filters.eq("_id", sourceId)
).first();
assertEquals(originalBalance,
        source.getLong("balanceUnits"));
~~~

Assumes fixture variables are initialized in the test. This tests **transaction abort**, not network faults or ambiguous commits.

### 16.4. Missing Session Test — Anti-Pattern

~~~java
session.startTransaction();
accounts.updateOne(Filters.eq("_id", sourceId), update);
session.abortTransaction();
~~~

Because `updateOne` omits the `session` argument, the write commits independently and **abort does not undo it**. Keep this as a negative diagnostic in an isolated fixture; never write it in application code.

### 16.5. Testing Idempotent Resends

1. Call `service.transfer` the first time with a stable ID.
2. Inspect balances and receipt.
3. Call `service.transfer` again with the same ID and parameters.
4. Confirm balances did not change again and receipt count stays 1.
5. Confirm the second response represents the same business outcome.

### 16.6. Testing Same ID with Different Parameters

~~~text
First:  ID=req-100, amount=150000
Second: ID=req-100, amount=200000
~~~

Expect conflict and zero second debit. Merely checking whether the ID exists and returning success without comparing payloads breaks idempotency semantics.

### 16.7. Testing Write Conflicts

Two sessions on two threads:

~~~text
A balance = 200 units
T1 reads A=200, wants debit 150
T2 reads A=200, wants debit 150
~~~

One attempt hits a conflict and retries on the new snapshot, potentially observing insufficient funds.

Expected invariants:

~~~text
A >= 0
sum(A,B,C) unchanged
at most one 150-unit transfer committed
each receipt corresponds to matching debit/credit
~~~

Use **CountDownLatch/CyclicBarrier** in the test harness to align the race window rather than fixed sleeps.

### 16.8. Testing Concurrent Duplicate Requests

Two threads send the exact same `transferId`. One succeeds while the other hits duplicate key or conflict requiring reconciliation. Afterward:

~~~text
receipt count = 1
debit happened once
credit happened once
sum balance invariant holds
~~~

Both API calls need not return HTTP 200 if no reconciliation layer sits above them, yet **two business effects must never occur**.

### 16.9. Failover Tests Differ from Application Exception Tests

Throwing `IllegalStateException` after debit proves abort, not primary election. Failover tests require multiple nodes and controlled fault injection. Always log the exact injected fault and observed error labels.

### 16.10. Testcontainers and Replica Set Testing

Supported versions of the **Testcontainers MongoDB module** run a MongoDB container as a replica set and expose its connection URI. Workflow:

~~~text
JUnit lifecycle:
  start isolated replica set container(s)
  wait for PRIMARY
  create collections and indexes
  seed fixture documents
  execute transaction test
  inspect committed state
  stop/dispose test deployment
~~~

Check APIs for your Testcontainers version. A single-container replica set suffices for commit/abort, yet **cannot prove multi-node primary failover**.

## 17. HTTP Idempotency and Business-Level Resends

Clients retry requests after timeouts even when MongoDB committed.

### 17.1. Placing Idempotency Keys at the API Boundary

Example:

~~~http
POST /transfers HTTP/1.1
Idempotency-Key: transfer-req-1001
Content-Type: application/json

{
  "sourceId": "A",
  "destinationId": "B",
  "amountUnits": 150000,
  "currency": "VND"
}
~~~

Each **logical business request** uses a stable key. Retries after timeout keep **the same key**; a brand-new transfer gets a new key.

### 17.2. Duplicate Keys Must Compare Payloads

~~~text
Idempotency-Key = k-1

Request A: A -> B, 150000 VND
Request B: A -> C, 150000 VND
~~~

Never silently return A→B's success to A→C. Bind keys to one explicit business action by comparing immutable fields or a canonical request fingerprint (paying attention to normalization).

### 17.3. When Outcomes Remain UNKNOWN

~~~text
Client receives timeout / pending / status unknown
                |
                v
GET /transfers/{transferId}
                |
                v
Server checks persisted receipt and reconciles
                |
                v
COMMITTED / definitively FAILED / still UNKNOWN
~~~

API contracts can expose status endpoints, same-key retries, or pending workflows. Never treat `UNKNOWN` as an automatic abort and issue a new business request with a fresh ID.

### 17.4. Unique Indexes and Retention

A unique **_id** establishes a durable deduplication boundary, yet still requires:

- Using the same stable ID across every code path.
- Keeping debit/credit/receipt inside one transaction.
- Handling races and parameter mismatches.
- Retaining receipts/idempotency keys long enough.

If receipts are purged after 24 hours while clients can retry the same key after 30 days, double-debit protection vanishes upon deletion. Align retention with the replay horizon, business audit, and compliance rules.

### 17.5. Message Broker Replays

A consumer receives:

~~~text
TransferRequested(eventId=e-101, transferId=t-101)
~~~

Brokers redeliver events if a consumer crashes before ACK. Consumers must use **unique `transferId`/`eventId` and durable deduplication** within their processing boundary instead of minting a new `transferId` on each delivery.

### 17.6. Exactly-Once Must State Its Scope

MongoDB transactions guarantee atomicity across MongoDB writes within their scope. They do not automatically ensure an external **payment gateway** or **email server** is invoked exactly once.

Never claim end-to-end exactly-once without idempotency and recovery across every boundary.

## 18. Transactional Outbox for Post-Commit Side Effects

An app may need to publish an event once a transfer commits. Publishing directly inside the callback:

~~~text
Transaction attempt 1:
  debit/credit
  send Kafka event
  transaction aborts after write conflict

Transaction attempt 2:
  debit/credit
  send Kafka event again
  commit
~~~

The broker already received the event from the aborted attempt. MongoDB transactions **cannot roll back an external broker**.

### 18.1. Storing the Outbox Record in the Same Transaction

One solution inserts a record into **wallet.outbox** inside the same transaction as debit/credit/transfer:

~~~javascript
{
  _id: "outbox-transfer-req-1001",
  eventType: "TransferCommitted",
  aggregateId: "request-1001",
  payload: {
    sourceId: "A",
    destinationId: "B",
    amountUnits: NumberLong("150000")
  },
  state: "PENDING",
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

Create collections and indexes before the transaction. Inside the callback:

~~~text
debit A
credit B
insert transfer receipt
insert outbox event
commit
~~~

If the transaction aborts, the outbox event never commits either; the dispatcher never sees events from aborted transactions.

### 18.2. Dispatcher Runs After Commit

~~~text
MongoDB transaction COMMITTED
           |
           v
Outbox record PENDING
           |
           v
Background dispatcher
           |
           v
Publish to broker
           |
           v
Mark outbox record SENT
~~~

If the dispatcher publishes and crashes before marking `SENT`, the event may be published **again**. Thus outbox provides **at-least-once delivery**; consumers still need deduplication/idempotency by `eventId`.

### 18.3. Outbox Is Not a Distributed ACID Transaction

MongoDB commit and broker ACK do not form a cross-system ACID transaction. Outbox ensures publish intent is durably persisted with business data and retried after crashes.

### 18.4. Compensating Transactions

If an external payment service already processed funds yet a downstream step failed, a **saga/compensating action** may be required:

~~~text
Original transaction COMMITTED
   |
   v
New business action reverses effect
   |
   v
New transaction/ledger entry with reference
~~~

Compensation needs its own ID, authorization, and audit record. Never call **abortTransaction()** expecting to undo a completed commit.

### 18.5. Testing the Outbox

Essential tests:

1. Transfer commit → exactly one outbox event exists.
2. Transfer abort → zero outbox events committed.
3. Dispatcher crash before publish → retries cleanly.
4. Dispatcher crash after publish before ACK/markSent → consumer deduplicates.
5. Replay same `transferId` → zero duplicate business outbox events.

## 19. Transaction Isolation Does Not Automatically Make Every Invariant Safe

A transaction provides consistent snapshot reads and atomic writes, yet should not be assumed to automatically enforce every **cross-document constraint** under serializable semantics.

### 19.1. Concurrent Transactions on the Same Account

When two transactions update the same source account A, write conflicts or conditional predicates force one to retry. With a balance predicate, the fresh attempt detects insufficient funds.

### 19.2. Write Skew When Updating Disjoint Documents

Suppose a hospital requires **at least one doctor on call** at all times:

~~~text
Doctor A: onCall=true
Doctor B: onCall=true
~~~

Two concurrent transactions read the same snapshot showing two doctors on call:

~~~text
T1 reads A,B; sets A.onCall=false
T2 reads A,B; sets B.onCall=false
~~~

Because the two transactions write different documents without a shared write conflict or guard, **write skew** can leave zero doctors on call.

This is why **snapshot isolation must not be equated with automatic serializable business invariants**.

### 19.3. Ways to Enforce the Invariant

Depending on the domain:

- Mutate a shared **guard/coordination document**.
- Use conditional updates on an invariant-owning document.
- Use unique indexes or schema constraints where expressible.
- Remodel data so critical invariants live inside one atomic document.
- Apply application/queue serialization per architecture review.

Never merely enable **readConcern: snapshot** and drop validation.

### 19.4. Intentional Concurrency Tests

Concurrency tests should intentionally trigger possible races using synchronization barriers rather than spawning threads and hoping contention happens.

State expectations clearly:

~~~text
Correctness invariant
Conflicting read/write sets
Expected committed or aborted attempts
Retry conditions
Final persisted state
~~~

When a constraint relies on a **unique index**, test duplicate races and error handling too.

## 20. Observability for Transactions and Retries in Test Environments

When a transaction test fails, logs and metrics must distinguish business errors, mapping/session bugs, transient write conflicts, primary elections, unknown commit outcomes, and retry exhaustion.

### 20.1. Metrics to Collect

| Conceptual metric | Meaning | Bounded labels |
|---|---|---|
| **txn.started** | Number of transaction attempts. | service, operation, environment. |
| **txn.committed** | Number of confirmed commits. | service, operation. |
| **txn.aborted** | Number of aborted attempts. | service, reason category. |
| **txn.body.retry** | Whole-body retry count. | operation, error category. |
| **txn.commit.retry** | Commit retry count. | service, operation. |
| **txn.commit.unknown** | Indeterminate commit outcomes. | operation, error category. |
| **txn.duration** | Duration of body + commit. | operation. |
| **txn.write.conflict** | Write-conflict errors. | operation. |
| **txn.idempotent.hit** | Returned stored receipt result. | operation. |
| **txn.idempotent.conflict** | Key collided with differing payload. | operation. |
| **txn.reconciliation.pending** | Unresolved outcomes awaiting reconciliation. | service. |

Metric names above are **application-defined examples**, not automatically exported by MongoDB itself.

### 20.2. ServerStatus

On a `mongod` member with appropriate privileges:

~~~javascript
const s = db.adminCommand({ serverStatus: 1 });
printjson(s.transactions);
~~~

Server versions expose gauges/counters for open, active, committed, and aborted transactions. Fields like **currentOpen**, **currentActive**, **totalCommitted**, and **totalAborted** vary by version and topology.

With cumulative counters:

~~~text
totalCommitted(t0) = 12300
totalCommitted(t1) = 12420
elapsed = 60 seconds

committedRate = (12420 - 12300) / 60 = 2/s
~~~

Never graph raw cumulative counters as QPS; account for process restarts and counter resets.

### 20.3. Logs, Profiler, and Current Operations

Logs and profiler entries capture transaction errors, write conflicts, elections, slow operations, and potentially sensitive metadata. Never turn on high-level profiling uncontrolled in production just to run tests.

**currentOp/$currentOp** tools (per server version) help inspect active transactions, yet snapshots are fleeting, verbose, and contain sensitive query/infra info; prefer formal monitoring and bounded sampling.

### 20.4. Client-Side Tracing

One logical request can spawn multiple attempts:

~~~text
traceId=abc
transferId=request-1001
  attempt=1 -> TransientTransactionError
  attempt=2 -> commit returned UnknownTransactionCommitResult
  attempt=2 -> commit retry succeeded
~~~

Log **attempt number**, phase (**body/commit**), and error label/category—never raw balances, tokens, account secrets, or full documents.

### 20.5. Do Not Count Attempts as Transfers

~~~text
Logical business transfers: 1
Transaction body attempts:  3
Commit calls:               possibly >3
Committed receipts:         1
~~~

Summing every attempt on a dashboard as “money transferred” corrupts business metrics. Derive business counts from durable receipts/ledgers and invariants.

### 20.6. Context-Aware Alerts

~~~text
High TransientTransactionError + primary elections
  -> investigate replica set health

UnknownTransactionCommitResult + network errors
  -> investigate transport and unresolved commit outcomes

Transaction p95 rising + write conflicts
  -> investigate contention and transaction duration

Reconciliation queue growing
  -> protect business SLA and replay semantics
~~~

Never page solely because **`txn.aborted > 0`**: normal business aborts like insufficient funds do not indicate a cluster outage.

## 21. Limits and Costs of Multi-Document Transactions

### 21.1. Transactions Are Not Free

Multi-document transactions increase cache/snapshot pressure, lock waits/write conflicts, replication work, latency, and retry overhead. If an invariant fits inside a single document, a single-document atomic update is simpler and cheaper.

### 21.2. Transaction Lifetime

MongoDB enforces a **transaction lifetime limit** plus timeout and resource limits per server version/configuration. Excessively long transactions get aborted.

Never write:

~~~text
startTransaction
  -> scan huge collection
  -> call external payment API
  -> wait for customer OTP
  -> update three accounts
  -> commit
~~~

Keep transactions short and push external I/O and user waits outside.

### 21.3. Very Large Transactions

Processing millions of documents in one transaction holds vast resources, invites conflicts, slows replication, and is painful to retry. Where business rules permit, split into smaller checkpointed/idempotent batches rather than stuffing everything into one giant ACID transaction.

### 21.4. Collection and Index Creation

MongoDB permits limited DDL inside transactions depending on version and conditions. For business commit/abort tests, **create collections and indexes beforehand** so DDL behavior does not obscure test goals.

### 21.5. Sharded Transactions

Transactions run on supported sharded clusters as well, yet multi-shard coordination amplifies latency and failure modes. Results on a single-node replica set never prove performance for distributed multi-shard transactions.

### 21.6. Snapshot Is Not Serializable

`ReadConcern.SNAPSHOT` does not automatically enforce all cross-document constraints; write skew remains possible when transactions update disjoint documents based on overlapping reads. Use guard documents, conditional writes, unique indexes, or data-model adjustments when needed.

### 21.7. Long Transactions and Primary Failover

Open transactions abort during elections. Keep callbacks brief, index queries properly, avoid external I/O, and monitor **p95/p99 duration** alongside transient errors.

### 21.8. Retry Storms

If hundreds of instances retry immediately after a new primary election without backoff, the cluster can overload again. Enforce deadlines, backoff with jitter, and circuit breakers per architecture.

### 21.9. Retry Budgets Depend on Business SLOs

A real-time API with a 2-second deadline cannot wait out a 10-second election; it must return **pending/unknown** and reconcile. A batch worker can wait longer. One infinite retry loop serves neither well.

## 22. Diagnostic Runbook When Transactions Fail

### 22.1. Case A — Aborted Yet Account Still Debited

~~~text
Application says transaction aborted.
Account A balance decreased anyway.
~~~

Investigate:

1. Did the debit call pass the **ClientSession**?
2. Did all operations share the same client/session context?
3. Did Spring `@Transactional` actually use `MongoTransactionManager` and run through a proxy?
4. Did a raw driver write execute outside the session?
5. Are you misreading another test fixture or stale secondary data?

If a write ran outside the transaction, abort **cannot undo** it. Fix session propagation and add an integration assertion.

### 22.2. Case B — Commit Response Timeout

~~~text
commitTransaction sent
network timeout
result unknown
~~~

Do not mint a new transfer ID. While the same transaction/session remains active, retry commit per driver rules. Once the HTTP request ends, use the durable `transferId` to reconcile and return the true state.

### 22.3. Case C — Two Receipts for One Business Action

Check:

- Did a retry generate a new `transferId`?
- Did two services use different key spaces?
- Did one code path skip idempotency?
- Were old receipts purged too early by TTL/retention?
- Were writes split across different collections?

Unique `_id` blocks **the same ID** in one collection, yet cannot detect two distinct IDs representing the same business intent.

### 22.4. Case D — Transient Errors Spike After Deploy

Inspect transaction duration, query plans, collection scans, hot documents, concurrent updates, primary elections, and network/disk/cache metrics. Never simply raise retry counts when contention or heavy queries are the root cause.

### 22.5. Case E — Callback Sent Email Twice

The callback retried after a transient error, and the external email fired during the aborted attempt. Move event emission into an outbox inside the transaction and dispatch post-commit with deduplication.

### 22.6. Case F — Spring `@Transactional` Has No Effect

Checklist:

- Is `MongoTransactionManager` registered properly?
- Does `@Transactional` reference the right manager?
- Was the method invoked through the Spring proxy rather than `this` self-invocation?
- Were exceptions swallowed?
- Do repositories/templates share the transaction context?
- Is MongoDB running as a replica set?

Seeing the annotation in source code never proves transactions are active.

### 22.7. Case G — Duplicate Key on Receipt

Compare the existing record against business inputs. If parameters match and state is `COMMITTED`, return the stored result. If parameters differ, return conflict. Never blindly convert duplicate key into unconditional success.

### 22.8. Case H — Two Transfers Both Try to Withdraw 150 from 200

Verify:

1. Debit uses conditional predicate `balanceUnits >= amount`.
2. Both attempts target the same source document.
3. Write conflicts trigger fresh retry attempts.
4. Each attempt re-reads the account and re-evaluates funds.
5. Zero overdrafts or double receipts occur.

Reading balance outside the transaction and updating unconditionally causes overdrafts.

### 22.9. Case I — Majority Commit Cannot Complete

Inspect replica set members, majority availability, replication lag, write concern timeouts, and disk/network pressure. Never downgrade write concern solely to silence errors without evaluating durability and business risk.

### 22.10. Case J — Stale Balance Read After Commit

If reading a secondary, replication lag is likely. Use primary reads, appropriate read concerns, or causal consistency during verification. If the primary lacks the data after a confirmed commit, inspect namespaces, receipts, session wiring, and error handling.

### 22.11. Case K — API Timed Out Yet Receipt Is COMMITTED

The HTTP response dropped after commit. Retrying with the same idempotency key must return the existing outcome without debiting twice.

### 22.12. Case L — Refund Needed After Commit

Issue a **compensating/reversal transaction** with its own `transferId`, audit trail, and link to the original transaction. `abortTransaction()` cannot reverse a completed commit.

### 22.13. Procedure for Handling UNKNOWN

~~~text
1. Identify original transferId and immutable parameters
2. Check driver error phase and labels
3. If same session still active and label allows:
     retry same commit, bounded by deadline
4. Otherwise query durable receipt by original ID
5. If receipt COMMITTED with matching parameters:
     return existing business result
6. If receipt absent but outcome still uncertain:
     move to pending reconciliation, do not blindly replay
7. When outcome is conclusively resolved:
     update client status/audit record
~~~

A **single missing receipt read** does not prove the transaction aborted, especially while commit outcome is uncertain or if reading a lagging secondary. Use bounded waiting/retries per consistent observation policy.

## 23. Pre-Release Testing Checklist

### 23.1. Environment and Configuration

- [ ] MongoDB runs as a replica set, not standalone.
- [ ] MongoDB, driver, and Spring Data versions support transactions compatibly.
- [ ] Client URI specifies the replica set with reachable hosts.
- [ ] Collections, indexes, and fixtures exist before transactions start.
- [ ] Test accounts use scoped privileges, never production credentials.
- [ ] Dedicated test data; cleanup deletes only test-owned records.
- [ ] Chosen transaction options justify read concern, write concern, and read preference.
- [ ] Both single-node and multi-node failover tests exist where needed.

### 23.2. Commit

- [ ] Debit A, credit B, and insert receipt execute in one transaction.
- [ ] All operations use the same session or Spring transaction manager.
- [ ] On commit success, A/B balances match expectations.
- [ ] Total balance sum is conserved per fixture invariants.
- [ ] Transfer receipt count equals 1 under the stable key.
- [ ] Currency and parameters obey business contracts.
- [ ] Verification uses consistent reads without mistaking secondary lag.

### 23.3. Abort / Rollback

- [ ] Error thrown after debit → A/B unchanged after abort.
- [ ] Missing recipient → debit rolled back.
- [ ] Insufficient balance → transaction aborts without committing.
- [ ] Currency mismatch → zero partial debits.
- [ ] Duplicate key leaves zero partial state.
- [ ] Zero external side effects emitted from aborted callbacks.
- [ ] Spring methods never swallow exceptions and commit accidentally.

### 23.4. Retries and Unknown Commits

- [ ] `TransientTransactionError` retries the **whole transaction**.
- [ ] `UnknownTransactionCommitResult` retries **commit of the same transaction**.
- [ ] Retries enforce bounded attempts/deadlines and backoff policies.
- [ ] Transaction callbacks trigger no external side-effecting calls.
- [ ] Every logical request carries a stable idempotency key.
- [ ] HTTP retries after commit never debit twice.
- [ ] Same key with different parameters returns conflict.
- [ ] Concurrent same-key requests create at most one business effect.
- [ ] Unknown outcomes past deadline enter pending/reconciliation handling.
- [ ] Logs and metrics separate body retries from commit retries.

### 23.5. Replica Set Failover

- [ ] Multi-node test triggers real primary election.
- [ ] Majority write concern verified.
- [ ] Node unavailability does not cause infinite API retries.
- [ ] Election recovery uses deadlines/polling instead of short fixed sleeps.
- [ ] Post-failover balances, invariants, and receipts verified.
- [ ] Replication lag distinguished from rollback.
- [ ] Failpoints/stepdowns run only in the lab and are cleaned up afterward.

### 23.6. Spring Data

- [ ] `MongoTransactionManager` bean registered properly.
- [ ] `@Transactional` specifies the right transaction manager.
- [ ] Calls invoke through the Spring proxy.
- [ ] Checked/unchecked rollback rules explicitly verified.
- [ ] No new `MongoClient` or raw writes bypassing the transaction.
- [ ] Outer retry layer invokes fresh transactional attempts properly.
- [ ] Never nest MongoDB transactions inside SQL `@Transactional` expecting distributed ACID.

### 23.7. Operations and Security

- [ ] Metrics track duration, aborts, retries, and unknown outcomes.
- [ ] Bounded reconciliation queue with clear ownership.
- [ ] Logs exclude raw balances, PII, and secrets.
- [ ] Transaction bodies stay short with proper indexes.
- [ ] Alerts distinguish business aborts from cluster failures.
- [ ] Backup/recovery and audit trails cover receipts and outbox records.
- [ ] Compensation workflows exist for post-commit business reversals.

## 24. Hands-On Exercises

All exercises must run against an **authorized test database**—never run connection-breaking commands or primary stepdowns on production. For fault-injection exercises without a multi-node lab, write a detailed test plan and pseudocode.

### Exercise 1 — Replica Set Diagram

Draw one primary and two secondaries, showing Java Driver connections and write/replication flows. Explain why three members do not mean three shards.

### Exercise 2 — Standalone vs Single-Node Replica Set

Distinguish standalone `mongod` from a single-node replica set running a single `mongod` process. Which supports practicing multi-document transactions on supported releases?

### Exercise 3 — Provision a Lab Replica Set

Set up a lab replica set and run `hello` and `rs.status`. Explain when the node is ready for transactions and why you must wait for `PRIMARY`.

### Exercise 4 — Create Fixtures

Create two VND accounts `A=500000` and `B=300000`, plus a `transfers` collection. Use lab-scoped IDs and never delete other users' records.

### Exercise 5 — Single-Document Atomicity

Write an `updateOne` modifying two fields on Account A. Why is this already document-atomic without needing a multi-document transaction?

### Exercise 6 — Three Operations Without a Transaction

Describe the partial failure states when debiting A, crediting B, and inserting a receipt run as three independent commands. Why does `retryWrites` not turn them into an ACID transaction?

### Exercise 7 — Commit via mongosh

Create a `ClientSession`, call `startTransaction`, debit A, credit B, insert the receipt, and commit. Verify both balances and the receipt afterward.

### Exercise 8 — Abort After Debit

Inject an application exception after debiting A yet before crediting B. Call `abortTransaction`. Re-read balances and prove no half-written state exists.

### Exercise 9 — Missing Session Operation

Write a negative test: call `startTransaction` and accidentally call `updateOne` without passing `session`. Explain why abort fails to undo the standalone write. Run only on a lab fixture.

### Exercise 10 — Insufficient Balance

Given `A=100`, request transferring `150`. Write the debit predicate `balanceUnits >= amount` and inspect `matchedCount`. When `matchedCount=0`, what must the application do?

### Exercise 11 — Destination Missing

Debit A inside a transaction, then attempt crediting non-existent account B. Verify throwing/aborting leaves A's balance untouched.

### Exercise 12 — Currency Mismatch

Given `A=VND` and `B=USD`. Write predicates guarding currency on both debit and credit. When B fails to match, what state must the transaction reach?

### Exercise 13 — Commit Receipt

Insert a transfer record with a unique ID inside the same transaction as the balance updates. Why must the receipt not be written in a separate command outside the transaction after commit?

### Exercise 14 — Total Balance Invariant

In a zero-fee fixture, transfer 150000 units from A to B. Write assertions:

~~~text
A_after = A_before - 150000
B_after = B_before + 150000
A_after + B_after = A_before + B_before
~~~

### Exercise 15 — `ReadConcern.SNAPSHOT`

Explain why transaction reads using `snapshot` and commits using `majority` write concern serve different roles. Does `snapshot` alone make every cross-document business invariant serializable?

### Exercise 16 — Retrying the Whole Transaction

Diagram the flow when a write in the body throws an error labeled **TransientTransactionError**. Which attempt is discarded and which operations must rerun?

### Exercise 17 — Retrying Commit

Diagram the flow when `commitTransaction` throws an error labeled **UnknownTransactionCommitResult**. Why retry commit on the same transaction rather than rerunning the debit?

### Exercise 18 — Non-Transient Errors

How should missing currency, non-existent destination, or duplicate-key conflicts be classified? When is retrying the whole body futile?

### Exercise 19 — Java `withTransaction`

Write Java Sync Driver code opening a `ClientSession` and calling `withTransaction` with `TransactionOptions` for primary, snapshot, and majority. All MongoDB operations must pass the same session.

### Exercise 20 — Side-Effect-Free Callbacks

List four actions never to put inside a retryable callback: email, HTTP payment calls, Kafka publishes, and external system updates. Explain what happens if the callback runs twice.

### Exercise 21 — HTTP Resend After Commit

MongoDB committed request `ID=T1` yet the API reply dropped. Client resends POST with the same ID. Design receipt lookup logic returning the old result without debiting twice.

### Exercise 22 — Same Key, Changed Amount

Two POSTs share an ID, yet the second changes amount from 100 to 200. How must the server respond? Why is returning success without comparing payloads wrong?

### Exercise 23 — Duplicate Race

Two threads concurrently submit the same `transferId`. Design a test using a barrier, unique receipt ID, and assertions proving zero double debits.

### Exercise 24 — Concurrent Insufficient Funds

`A=200`; T1 and T2 both attempt transferring `150` to different recipients. Build a conflict/retry test verifying A never goes negative and at most one transfer commits.

### Exercise 25 — Write Skew

Doctors A and B are both on call. Two transactions read the snapshot and each takes a different doctor off call. Explain why snapshot isolation does not automatically enforce “at least one doctor on call” and propose a guard document.

### Exercise 26 — Single-Node Limitation

Which tests can a single-node replica set run? Why can't it evaluate majority election durability or secondary lag?

### Exercise 27 — Primary Stepdown

Draft a test plan using **rs.stepDown** solely on a three-member lab replica set. Specify injection points, metrics to observe, and final invariants.

### Exercise 28 — Commit Network Fault

Design a test where the client loses the reply around commit. Why does `failCommand` with `closeConnection` not guarantee you simulated “commit succeeded then ACK lost”?

### Exercise 29 — Retry Budgets

An API has a 2-second deadline while a replica set election takes 10 seconds. What response should it return, and what reconciliation replaces infinite retries?

### Exercise 30 — Secondary Stale Read

After a majority commit, a test reads an old secondary and sees the prior balance. Why can't you conclude rollback occurred? Fix the observation strategy.

### Exercise 31 — Spring `MongoTransactionManager`

Write a `@Configuration` bean for `MongoTransactionManager` and a Spring service method annotated with `@Transactional` targeting it. Create an integration test proving rollback on runtime exceptions.

### Exercise 32 — Self-Invocation

A service calls `this.transferOnce()` from another method in the same bean. Why can proxy-based transactions fail to engage? Propose a proper invocation design.

### Exercise 33 — Swallowed Exceptions

A `@Transactional` method catches `Exception` and returns success. Why can changes commit even when a business step failed? Design proper propagation and rollback rules.

### Exercise 34 — Checked Exceptions

Compare Spring's default rollback behavior for `RuntimeException` vs checked exceptions. When is `rollbackFor` required?

### Exercise 35 — Outbox in Transaction

Add an outbox event inside the transfer transaction. Test commit creates the event and abort creates none. Why must the dispatcher still support redelivery and consumer deduplication?

### Exercise 36 — Callback Generating Timestamps

A callback calls `new Date()` on every retry. How does that affect receipt consistency? When a business contract requires a fixed timestamp, where should it be created?

### Exercise 37 — Reconciling Unknown Outcomes

Write an algorithm with a deadline that looks up `transferId`, compares immutable parameters, and returns `COMMITTED`/`CONFLICT`/`PENDING` accurately. Why is a single absent receipt read not conclusive proof of abort?

### Exercise 38 — Logs and Metrics

Propose metrics separating transaction attempts, body retries, commit retries, unknown outcomes, idempotency hits, and committed business transfers. Why never count attempts as successful transfers?

### Exercise 39 — Testing Majority Durability

In a three-member lab replica set, propose a failover test following a confirmed majority commit. What must you observe so secondary lag or read concerns are not mistaken for lost writes?

### Exercise 40 — Transactions and SQL

A Spring service writes to MongoDB and PostgreSQL inside a `@Transactional` method configured only with `MongoTransactionManager`. Are both databases guaranteed to commit or roll back together? Design a saga/outbox when needed.

### Exercise 41 — Transaction Lifetime

A transaction stays open 90 seconds scanning millions of records and calling HTTP APIs. List resource/timeout risks and how to shrink transaction duration.

### Exercise 42 — Retry Storms

50 service instances each hold 100 pending transfers and all retry immediately after a primary election. Describe the amplified load and how backoff, budgets, and circuit breakers mitigate it.

### Exercise 43 — Post-Commit Reversals

A transfer committed; the user requests a refund. Why does `abortTransaction` not help? Sketch a compensating transaction and audit link.

### Exercise 44 — Classifying Errors

Classify: insufficient funds, write conflict, lost commit reply, invalid schema, duplicate `transferId`, and replica set unavailable. Which retry the body, retry commit, or never retry?

### Exercise 45 — End-to-End Test Plan

Design a test suite for a transfer API covering:

~~~text
Setup:
  isolated replica set + accounts + unique transfer IDs

Cases:
  commit / abort / duplicate / conflict / failover / timeout

Assertions:
  balance invariants
  exactly one receipt per business request
  no partial committed state
  no uncontrolled external side effects

Observability:
  attempt counts, error labels, duration, reconciliation

Cleanup:
  only dedicated test data
~~~

Never assert solely on HTTP status; verify durable state inside MongoDB.

## 25. Review Questions

1. What are the primary roles in a replica set?
2. Which topology conditions do multi-document transactions require?
3. How does a single-node replica set differ from standalone `mongod`?
4. How does MongoDB provide built-in single-document atomicity?
5. Why don't three updates across three documents form a transaction without a session?
6. Is a `ClientSession` itself a transaction? Which method starts one?
7. Why must every MongoDB operation in a transaction pass the same session?
8. Does `abortTransaction` roll back a write executed without passing the session?
9. What is the purpose of `ReadConcern.SNAPSHOT`?
10. What is the purpose of `WriteConcern.MAJORITY` on commit?
11. Why do replica set transaction reads/writes normally target the primary?
12. Do transactions automatically check sufficient balances?
13. Why must the application classify `matchedCount=0`?
14. Can a successful commit appear to the client as a timeout?
15. When commit outcome is unknown, can you conclude the transaction definitely aborted?
16. What kind of retry does `TransientTransactionError` call for?
17. What kind of retry does `UnknownTransactionCommitResult` call for?
18. Why is retrying commit different from retrying the whole business body?
19. Do retryable writes outside transactions provide multi-document atomicity?
20. Why avoid infinite retry loops?
21. Can the driver's `withTransaction` execute its callback multiple times?
22. Why avoid sending emails inside the callback?
23. When must `transferId` be generated so it stays stable across attempts?
24. Which HTTP retry risk does an idempotency key solve?
25. Is unique `_id` on receipts alone enough to prevent double transfers across all paths?
26. When the same key arrives with a different amount, how must the API respond?
27. Can two concurrent requests both read “receipt does not exist yet”?
28. Does a duplicate key error always mean the prior request committed with identical parameters?
29. Why inspect balances and receipts after abort?
30. How does primary failover differ from an application exception before commit?
31. Why is a single-node replica set insufficient for testing elections?
32. How does majority commit differ in durability from weaker write concerns?
33. Why can reading a lagging secondary cause false rollback conclusions?
34. What does `MongoTransactionManager` manage?
35. Does `@Transactional` automatically implement full `withTransaction` retry semantics?
36. Why can self-invocation disable `@Transactional`?
37. How do Spring's default rollback rules differ for checked exceptions vs `RuntimeException`?
38. Why does `MongoTransactionManager` not form an ACID transaction with a SQL database?
39. What is a transactional outbox?
40. Under what conditions can an outbox dispatcher publish duplicates?
41. Why do broker consumers still need deduplication even when the outbox row is inserted once?
42. Does transaction atomicity equal end-to-end exactly-once delivery?
43. Is snapshot isolation always serializable for cross-document constraints?
44. How does write skew happen in the on-call doctors example?
45. What ways exist to enforce invariants with guard documents or unique indexes?
46. What cache, timeout, and conflict risks do long transactions create?
47. Why does `failCommand` with `closeConnection` not automatically prove commit succeeded before the drop?
48. Which metrics distinguish body retries from commit retries?
49. Which durable records help reconcile `UNKNOWN` outcomes?
50. How does post-commit compensation differ from pre-commit abort?

## 26. Summary: Transaction Tests Must Verify Data, Not Just Exceptions

A trustworthy transaction flow follows this mental model:

~~~text
                BUSINESS REQUEST
             stable transferId + payload
                        |
                        v
                 Input validation
                        |
                        v
              Start MongoDB transaction
                        |
                        v
              Check existing receipt ID
                        |
                +-------+--------+
                |                |
          Existing record    No existing record
                |                |
                v                v
           Verify payload    Conditional debit
                |                |
                |                v
                |            Credit receiver
                |                |
                |                v
                |           Insert receipt
                |                |
                +-------+--------+
                        |
                        v
               Commit transaction
                        |
               +--------+---------+
               |                  |
               v                  v
         Known success       Error/uncertainty
               |                  |
               |          +-------+------------------+
               |          |                          |
               |          v                          v
               |   Transient error?           Unknown commit?
               |          |                          |
               |          v                          v
               |    Retry whole body             Retry same commit
               |          |                          |
               +----------+--------------------------+
                        |
                        v
              Business result/reconciliation
                        |
                        v
             Validate durable invariants
~~~

### 26.1. Five Critical Invariants

**Invariant 1 — Atomicity**

~~~text
Either:
  debit A + credit B + receipt all committed
Or:
  none of these transaction writes committed
~~~

**Invariant 2 — Valid Balances**

~~~text
If overdraft is disallowed:
  balanceUnits(source) >= 0

For a transfer without fees:
  sum(balanceUnits of involved accounts)
  remains unchanged
~~~

**Invariant 3 — Idempotency**

~~~text
Same logical transferId + same immutable request parameters:
  at most one business transfer effect
  repeat requests return the existing result
~~~

**Invariant 4 — Never Fabricate Outcomes**

~~~text
Confirmed COMMITTED != confirmed ABORTED != UNKNOWN
~~~

When unknown, applications must retry or reconcile per protocol rather than assuming abort or issuing a new transfer.

**Invariant 5 — External Side Effects Managed Separately**

~~~text
MongoDB transaction cannot atomically undo:
  email sent
  Kafka event published
  payment gateway request accepted
~~~

For external side effects, apply outbox, idempotency, or saga patterns matching the business contract.

### 26.2. Practical Principles

1. **Use a replica set** to test multi-document transactions; standalone `mongod` is not equivalent.
2. **Every operation must pass the exact ClientSession**, or engage a genuine Spring transaction context.
3. **Commit and abort require persisted-data assertions** after operations finish.
4. **Handle `matchedCount=0` in business logic**; MongoDB does not automatically raise an insufficient-funds error.
5. **`ReadConcern.SNAPSHOT`** and **`WriteConcern.MAJORITY`** address distinct concerns; pick them per SLO and topology.
6. **`TransientTransactionError` → retry the whole transaction** in a fresh attempt.
7. **`UnknownTransactionCommitResult` → retry commit of the same transaction** when protocol permits.
8. **Never retry infinitely**, and never invoke external side effects inside replayable callbacks.
9. **Stable idempotency keys** prevent duplicate business requests after lost HTTP replies.
10. **Unique indexes do not replace validation/reconciliation** under concurrent requests or key-payload mismatches.
11. **Primary failovers and network faults** need dedicated tests rather than substituting application exceptions.
12. **Secondary lag never proves rollback**; use appropriate read observation policies.
13. **Spring `@Transactional` requires `MongoTransactionManager` and proxy invocation**, with clear rollback rules.
14. **Outbox/compensation** manage side effects outside MongoDB.
15. **Test concurrency**, because atomic transactions do not automatically prevent write skew.
16. **Metrics must separate attempts, commit retries, business effects, and unknown outcomes**.
17. **Short, well-indexed transactions** reduce conflicts and resource pressure.
18. **Test results must be reproducible**, with fault injections scoped to labs and properly cleaned up.

### 26.3. Official References

- [MongoDB Transactions — Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — limits, resources, and transaction deployment.
- [MongoDB Transactions — Core Concepts](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity and transaction semantics.
- [MongoDB Transactions — Retries](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — transaction APIs, error handling, and retries.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgment and durability levels.
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — local/majority/snapshot semantics.
- [MongoDB Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — routing reads across replica sets.
- [MongoDB Replica Sets](https://www.mongodb.com/docs/manual/replication/) — primary/secondaries, elections, and replication.
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — distinguishing retryable writes from transaction retries.
- [MongoDB Transactions in Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction`, and commit/abort.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — driver overview and API integration.
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `MongoTransactionManager`, `@Transactional`, and session binding.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — proxies, `@Transactional`, and rollback rules.
- [MongoDB Configure Fail Point](https://www.mongodb.com/docs/manual/reference/command/configureFailPoint/) — test failpoints where supported by environment/version.
- [MongoDB serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — transaction metrics and node diagnostics.

Transaction behaviors, error labels, driver callback retries, server commands, and failpoints can vary by **MongoDB server version, MongoDB Java Driver version, Spring Data MongoDB version**, and deployment (Atlas vs self-managed). Consult the documentation for your exact versions before deploying to production or building a fault-injection harness.

**Conclusion:** Testing transaction commit, rollback, and retries on a replica set is genuinely valuable only when it proves **zero partial committed states, zero double business effects on retries, and zero false assumptions about indeterminate commit outcomes**. Combine MongoDB transactions, idempotency records, error-label-driven retries, controlled fault injection, and durable post-test data verification to build a system that recovers cleanly from failures.
