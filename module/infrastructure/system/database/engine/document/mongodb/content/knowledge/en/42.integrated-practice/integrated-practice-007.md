# Practicing Transactions, Disconnections, and Handling Unknown Commit Outcomes

An API transferring 50,000 VND between two accounts in MongoDB may commit successfully while the application receives a **socket timeout**: the response packet from the primary was lost right as the transaction committed. If the service immediately re-executes the transfer as a brand-new transaction, the customer can be debited **twice**. Conversely, if the application hits an error mid-transaction and only credits the recipient, the system loses balance integrity. These incidents must be handled through **transactions, error classification, idempotency, and reconciliation**, not a blind `retry()` call.

The lesson **"Practicing Transactions, Disconnections, and Handling Unknown Commit Outcomes"** belongs to the **Integrated Practice** chapter of the *Database Engine Document MongoDB* module. It presents a hands-on sequence runnable on a **test replica set**, covering data modeling, executing transactions, injecting conflicts, simulating failover/disconnects, classifying errors, and verifying business outcomes.

The overarching takeaway: **an error observed by the client does not always tell whether data was committed**. When a commit outcome is unknown, the first priority is **preventing duplicate business side effects**, followed by determining true state via an idempotency key and authoritative data.

> **Lab safety:** Only perform fault injection, primary stepdowns, network blocking, or config edits on an **authorized lab/staging replica set**. Never run these operations on production just to learn. Examples use `mongosh` and modern Java Sync Driver, assuming a MongoDB replica set with transaction support. APIs, error labels, and timeout semantics vary by driver/server/FCV; consult official docs for your exact running versions. Balances, accounts, and transfers here are synthetic data and do not replace accounting, regulatory, or security requirements of real payment systems.

## 1. Learning Outcomes

After this lesson, learners can:

1. Distinguish **single-document atomic updates** from **multi-document transactions**.
2. Configure and inspect replica sets, sessions, transaction options, read concerns, and write concerns.
3. Build a transaction writing to accounts, a transfer log, ledger entries, and an outbox.
4. Explain the difference among **abort before commit**, **confirmed commit success**, **confirmed commit failure**, and **unknown commit outcome**.
5. Recognize error labels `TransientTransactionError` and `UnknownTransactionCommitResult`.
6. Execute **retrying the entire transaction body** where appropriate vs. **retrying only commit** when the commit outcome is unknown.
7. Design **stable idempotency keys**, unique constraints, and outcome verification steps when a client or HTTP gateway retries.
8. Observe failover/connection loss, transaction limits, and post-incident recovery.
9. Write tests with controlled fault injection rather than relying on random races.
10. Build a runbook for handling unknown outcomes without duplicating money, ledger legs, or external notifications.

## 2. Outcome State Map

### 2.1. Four Scenarios That Must Never Be Conflated

| Scenario | What the Application Knows | Correct Action |
|---|---|---|
| **Transaction explicitly aborted before commit** | Writes inside the transaction were not committed. | If transient, retry the **whole transaction** within budget; if business conflict, return business error. |
| **Commit returns success ACK** | Transaction committed per required write concern. | Return success; record transfer ID for auditing. |
| **Commit returns definitive error** | A concrete error occurred, to be interpreted per server/driver semantics. | Classify the error; never assume every error equals rollback. |
| **Commit result unknown** | Client cannot confirm whether commit succeeded or failed. | Retry **commit** per spec/driver helper or verify via the idempotency record; never open a new transaction with a different ID. |

### 2.2. Timeline: Server Committed but Response Was Lost

~~~text
Client                 Primary                 Replicas
  |                       |                        |
  |--- commitTransaction ->|                        |
  |                       |--- replication ------->|
  |                       |<-- majority ACK --------|
  |                       | commit durable          |
  |  X--- network breaks -|                        |
  |                       |                        |
  |  Client gets timeout  |                        |
  |                       |                        |
  |  Outcome locally UNKNOWN                       |
~~~

A network drop at that exact moment leaves the client **without information**, rather than automatically rolling back the server. Variants include primary stepdown, dropped TCP sockets, gateway request cancellation, or application crash right after sending commit.

### 2.3. Retries Have Two Layers

~~~text
One business request (transferId = TR-100)
  |
  +-- HTTP/API retry by user or gateway
  |     -> must reuse same idempotency key
  |
  +-- Driver transaction retry
        |
        +-- TransientTransactionError:
        |     retry whole transaction body when appropriate
        |
        +-- UnknownTransactionCommitResult:
              retry commit of the SAME transaction when possible
~~~

**Driver retry** and **business/API retry** are distinct. The Java driver can retry transient operations or commit within an existing session; a brand-new HTTP request after a process restart must look up the same **business operation ID**—there is no arbitrary way to "resume the old session."

### 2.4. A Principle on "Exactly Once"

The practical goal is an **exactly-once business effect** achieved through idempotency/unique keys and reconciliation—never assuming the network, HTTP, Kafka, or MongoDB driver delivers a packet only once. Data writes must tolerate **at-least-once invocation**.

## 3. Lab Architecture and Prerequisites

### 3.1. Topology

MongoDB multi-document transactions require a supported deployment (a properly configured replica set or sharded cluster). A standalone `mongod` **does not support multi-document transactions** like a replica set.

Two lab setups:

| Lab | Purpose | Notes |
|---|---|---|
| **Single-node replica set** | Learn sessions, atomicity, commit/abort, transaction callbacks. | Has no secondaries to practice true HA elections. |
| **Three-node replica set** | Learn primary stepdown, server selection, majority availability, failover. | Requires reachable hostnames/ports from app and healthy members. |

Do not treat a single-node replica set as proof of HA; `w:"majority"` on one node means majority of **one member**, and cannot test three-node quorum loss.

### 3.2. Read-Only Verification Commands

~~~javascript
// Run on the authorized lab cluster:
db.hello()
rs.status()
db.getMongo().getDBNames()
~~~

`db.hello()` reports primary/secondary view, hosts, and `setName`; `rs.status()` requires appropriate privileges and may not be supported across all proxies or Atlas tiers. Check:

- `setName` matches the replica set name.
- A **PRIMARY** exists with enough healthy secondaries for failover labs.
- Advertised URI hosts resolve and connect from where Java runs.
- FCV/server version supports transactions.
- User has `readWrite` on the lab database, and only lab administrators hold stepdown/failpoint privileges.

### 3.3. Connection String

~~~text
mongodb://lab1.example:27017,lab2.example:27017,lab3.example:27017/txn_lab?replicaSet=rsLab&retryWrites=true
~~~

These are placeholder hostnames, not live addresses. For Atlas, use the cluster's SRV URI and a secret manager. Never hardcode passwords or print connection strings containing credentials in logs.

### 3.4. Controls to Fix in the Lab

1. A dedicated `txn_lab` database for this lesson.
2. Recorded server, driver, Java versions, and URI.
3. Test data isolated from real users.
4. Fixed IDs, timestamps, and amounts per scenario run.
5. A **lab-only** fixture reset procedure, verifying the target cluster before any writes.
6. Visibility into logs, events, and post-failure query results.
7. Modest timeouts sufficient for the lab; do not extrapolate to production benchmarks.

### 3.5. Do Not Start with Fault Injection

First run a **clean, error-free** transaction and verify all business invariants. Only then introduce conflicts, aborts, and simulated disconnects. Without a stable baseline, fault diagnostics lack a reference point.

## 4. Verifiable Transfer Data Model

### 4.1. Collections

We use four collections:

~~~text
accounts
  acct:A / acct:B          balances by currency

transfers
  TR-100                   stable business operation ID

ledgerEntries
  TR-100:DEBIT
  TR-100:CREDIT            postings for reconciliation

outbox
  transfer:TR-100          downstream event pending dispatch
~~~

### 4.2. Fixtures and Assumptions

~~~javascript
const lab = db.getSiblingDB("txn_lab")

// Insert into fresh lab collections; fixed IDs make a second run
// report duplicate _id rather than silently reset balances.
lab.accounts.insertMany([
  {
    _id: "acct:A",
    currency: "VND",
    balanceMinor: NumberLong("100000"),
    version: NumberLong("0")
  },
  {
    _id: "acct:B",
    currency: "VND",
    balanceMinor: NumberLong("20000"),
    version: NumberLong("0")
  }
])

lab.accounts.createIndex({ currency: 1, balanceMinor: 1 })
lab.transfers.createIndex({ from: 1, to: 1 })
lab.ledgerEntries.createIndex({ transferId: 1 })
lab.outbox.createIndex({ eventType: 1, published: 1 })
~~~

Collections already have a default unique index on `_id`. In the lab, `transfers._id` is the stable transfer ID, so no extra unique index on `_id` is needed. In multi-tenant APIs, use a composite key like `tenantId + requestId` with collision-free canonical encoding; this condensed example uses a single tenant.

### 4.3. Invariants

Suppose we transfer `50,000 VND` from A to B with zero fees and no currency conversion. Before:

~~~text
A = 100000
B =  20000
sum = 120000
~~~

After a successful transfer:

~~~text
A = 50000
B = 70000
sum = 120000

ledger:
  TR-100:DEBIT  = -50000
  TR-100:CREDIT = +50000
  net = 0

transfers.TR-100.status = COMPLETED
outbox.transfer:TR-100 has one pending logical event
~~~

Required conditions:

\[
A_{\mathrm{after}} = A_{\mathrm{before}} - q,\qquad
B_{\mathrm{after}} = B_{\mathrm{before}} + q,\qquad
q > 0
\]

\[
(A+B)_{\mathrm{after}} = (A+B)_{\mathrm{before}}
\]

Real systems must also enforce: account ownership, currency pairs, overdraft rules, integer overflow guards, regulatory limits, double-entry ledger accounting, and authorization. Never copy a toy wallet model into a real payment application without proper financial architecture.

### 4.4. Why Not Store Money as Double?

`NumberLong("50000")` is BSON int64 in minor currency units, avoiding binary floating-point errors common with `0.1` and `0.2`. For multiple currencies, values exceeding int64, or decimal scales, use Decimal128/BigDecimal per contract. Consistency requires **the exact same unit and type** across accounts, transfer requests, and ledger entries.

### 4.5. Idempotency Fingerprint

A transfer ID may bind to **only one immutable payload**:

~~~text
TR-100:
  from = acct:A
  to = acct:B
  amountMinor = 50000
  currency = VND
~~~

If a client resubmits `TR-100` with `amountMinor=60000`, never return "success" merely because the ID exists. Compare the payload/fingerprint and return an **idempotency conflict**, never silently executing a different request.

## 5. Exercise A — Recognizing Single-Document Atomicity

### 5.1. A Conditional Update

~~~javascript
lab.accounts.updateOne(
  {
    _id: "acct:A",
    currency: "VND",
    balanceMinor: { $gte: NumberLong("50000") }
  },
  {
    $inc: {
      balanceMinor: NumberLong("-50000"),
      version: NumberLong("1")
    }
  }
)
~~~

An update on a **single document** is atomic: if multiple debits race concurrently, `balanceMinor >= 50000` is evaluated atomically with the write per MongoDB semantics. A successful command returns `matchedCount=1`; if funds are insufficient or the account doesn't match, `matchedCount=0`. Inspect the response rather than assuming no exception means success.

**Do not run this on the fixture and immediately run Transaction Lab B** if you expect initial balance `A=100,000`. Give each scenario its own fixture or controlled reset rather than accumulating arbitrary mutations.

### 5.2. Why Isn't This Enough for Transfers?

If you only run:

~~~javascript
lab.accounts.updateOne(
  { _id: "acct:A", balanceMinor: { $gte: NumberLong("50000") } },
  { $inc: { balanceMinor: NumberLong("-50000") } }
)

// Network error / process crash at this point.

lab.accounts.updateOne(
  { _id: "acct:B" },
  { $inc: { balanceMinor: NumberLong("50000") } }
)
~~~

one command can succeed while the other never runs, breaking the `A+B` sum invariant. Two independent writes to **two documents** do not form a transaction.

### 5.3. Quick Exercise

Predict the final balance and `matchedCount` when two concurrent debits run against `A=100,000`, each trying to debit `70,000` with predicate `>=70000`. Both cannot succeed because after the first, `30,000` remains; expect **at most one matching update**. Even so, this does not guarantee the recipient gets credited—which is why a multi-document transaction or dedicated ledger/workflow is required.

## 6. Exercise B — Successful Transaction in mongosh

Run on a **fresh fixture** `acct:A=100000, acct:B=20000` where `TR-100` does not yet exist. If you ran Section `5.1`, set up a fresh lab or restore the valid fixture snapshot.

### 6.1. Session and Transaction Options

~~~javascript
const session = lab.getMongo().startSession()
const txDb = session.getDatabase("txn_lab")

session.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority", wtimeout: 5000 },
  readPreference: { mode: "primary" }
})
~~~

- **Session** binds operations into one logical transaction.
- `readConcern:"snapshot"` provides snapshot isolation under MongoDB-supported conditions.
- `writeConcern:"majority"` on commit requires majority acknowledgment per semantics, improving durability.
- `readPreference:"primary"` fits transactions containing writes.
- `wtimeout` bounds how long to wait for write concern acknowledgment—**it does not mean rollback on timeout**.

Do not set differing read/write concerns on individual operations inside a transaction expecting per-operation overrides; consult docs on transaction-level settings.

### 6.2. Inserting the Request ID First Inside the Transaction

~~~javascript
txDb.transfers.insertOne({
  _id: "TR-100",
  from: "acct:A",
  to: "acct:B",
  amountMinor: NumberLong("50000"),
  currency: "VND",
  status: "COMPLETED",
  createdAt: new Date()
})
~~~

The unique `_id` blocks creating two records with the same transfer ID. If the transaction aborts, **this insert rolls back as well**—it is not an independent pre-commit "reservation."

### 6.3. Guarded Debit

~~~javascript
const debit = txDb.accounts.updateOne(
  {
    _id: "acct:A",
    currency: "VND",
    balanceMinor: { $gte: NumberLong("50000") }
  },
  {
    $inc: {
      balanceMinor: NumberLong("-50000"),
      version: NumberLong("1")
    }
  }
)

if (debit.matchedCount !== 1) {
  throw new Error("INSUFFICIENT_FUNDS_OR_MISSING_SOURCE")
}
~~~

This is a **business failure**, not automatically a transient error to retry 100 times. Callers must distinguish insufficient funds / missing account from network failures. Throwing here in `mongosh` requires the caller to **abort the transaction** in catch/finally handling; see the combined pattern in `6.6`.

### 6.4. Guarded Credit

~~~javascript
const credit = txDb.accounts.updateOne(
  {
    _id: "acct:B",
    currency: "VND",
    balanceMinor: {
      $lte: NumberLong("9223372036854725807")
    }
  },
  {
    $inc: {
      balanceMinor: NumberLong("50000"),
      version: NumberLong("1")
    }
  }
)

if (credit.matchedCount !== 1) {
  throw new Error("MISSING_DESTINATION_OR_OVERFLOW")
}
~~~

The upper bound is `Long.MAX_VALUE - 50000`, demonstrating int64 overflow protection for a **fixed amount**. Production must calculate the predicate/bound dynamically from `amount` and validate non-negative balances/scale before opening the transaction, while verifying source and destination are **distinct** and share the same currency.

### 6.5. Ledger and Outbox in the Same Transaction

~~~javascript
txDb.ledgerEntries.insertMany([
  {
    _id: "TR-100:DEBIT",
    transferId: "TR-100",
    accountId: "acct:A",
    currency: "VND",
    deltaMinor: NumberLong("-50000")
  },
  {
    _id: "TR-100:CREDIT",
    transferId: "TR-100",
    accountId: "acct:B",
    currency: "VND",
    deltaMinor: NumberLong("50000")
  }
])

txDb.outbox.insertOne({
  _id: "transfer:TR-100",
  transferId: "TR-100",
  eventType: "TransferCompleted",
  published: false,
  createdAt: new Date()
})

session.commitTransaction()
session.endSession()
~~~

In a successful transaction, account updates, the transfer record, ledger entries, and the outbox record commit together; no partial state of **writes inside the same transaction** becomes visible as committed. Sending emails, HTTP payments, or Kafka events **is not inside the MongoDB transaction** merely because the outbox document committed.

### 6.6. Combined Pattern Ensuring Cleanup — Do Not Confuse Unknown with Abort

When managing sessions and commits manually in `mongosh`, separate the **body** phase from **commit**:

~~~javascript
function transferOnceManually(lab, transferId, amountStr) {
  const session = lab.getMongo().startSession()
  const tdb = session.getDatabase("txn_lab")
  let commitAttempted = false

  try {
    session.startTransaction({
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority", wtimeout: 5000 }
    })

    tdb.transfers.insertOne({
      _id: transferId,
      from: "acct:A",
      to: "acct:B",
      amountMinor: NumberLong(amountStr),
      currency: "VND",
      status: "COMPLETED"
    })

    const a = tdb.accounts.updateOne(
      { _id: "acct:A",
        balanceMinor: { $gte: NumberLong(amountStr) } },
      { $inc: { balanceMinor: NumberLong("-" + amountStr) } }
    )
    if (a.matchedCount !== 1) throw Error("DEBIT_NOT_MATCHED")

    // Simplified lab demonstration. For real correctness also:
    // validate account/currency/overflow, insert ledger and outbox.
    const b = tdb.accounts.updateOne(
      { _id: "acct:B" },
      { $inc: { balanceMinor: NumberLong(amountStr) } }
    )
    if (b.matchedCount !== 1) throw Error("CREDIT_NOT_MATCHED")

    commitAttempted = true
    session.commitTransaction()
    return { state: "COMMIT_ACKNOWLEDGED", transferId }
  } catch (e) {
    if (!commitAttempted && session.inTransaction()) {
      try { session.abortTransaction() } catch (_) {}
    }
    // If commit was attempted, do NOT claim "rolled back".
    throw e
  } finally {
    session.endSession()
  }
}
~~~

This is a **brief demo snippet** that does not automatically handle retries, error classification, or verification; `session.endSession()` cleans up client resources and **does not prove** a commit was rolled back. In production code, use the driver transaction helper and the idempotency protocol covered later.

### 6.7. After Commit ACK

~~~javascript
printjson(lab.accounts.find({}, { balanceMinor: 1 }).toArray())
printjson(lab.transfers.findOne({ _id: "TR-100" }))
printjson(lab.ledgerEntries.find({ transferId: "TR-100" }).toArray())
printjson(lab.outbox.findOne({ _id: "transfer:TR-100" }))
~~~

With the initial fixture, `A=50,000`, `B=70,000`, the transfer and 2 ledger entries exist, and the outbox has one unpublished record. That serves as **lab verification**; never run `toArray()` carelessly over millions of records.

## 7. Exercise C — Abort and Atomic Rollback

### 7.1. Creating an Intentionally Aborted Transaction

On a **clean fixture or after recording pre-test balances**, run:

~~~javascript
const sAbort = lab.getMongo().startSession()
const dAbort = sAbort.getDatabase("txn_lab")

try {
  sAbort.startTransaction()

  dAbort.accounts.updateOne(
    { _id: "acct:A" },
    { $inc: { balanceMinor: NumberLong("-10000") } }
  )

  dAbort.accounts.updateOne(
    { _id: "acct:B" },
    { $inc: { balanceMinor: NumberLong("10000") } }
  )

  sAbort.abortTransaction()
} finally {
  sAbort.endSession()
}
~~~

### 7.2. Prediction

Because both writes live in the same transaction and `abortTransaction()` is acknowledged before commit, committed balances **do not change** from that transaction. Outside observers never see those two intermediate writes as committed changes.

### 7.3. Visibility Note

A transaction can read its own snapshot and see its own writes; normal queries from other sessions cannot see them prior to commit under isolation semantics. Never present an uncommitted read from the same session as proof of "persisted successfully to the database."

### 7.4. Abort Is Different from a Network Failure at Commit

- **Abort ACK:** we know the transaction was cancelled.
- **Process crash before sending commit:** while uncommitted and once the session ends, the server aborts per lifecycle/timeout; rely on transaction semantics and recovery.
- **Network drop after sending commit:** client may not know the outcome. Never classify it automatically as aborted.

## 8. Transaction Options: Choosing Right Before Network Fault Labs

| Option | Meaning | What It Does Not Guarantee |
|---|---|---|
| `readConcern: snapshot` | Snapshot isolation for reads in the transaction when prerequisites hold. | Does not eliminate all business write skew outside write conflicts. |
| `writeConcern: majority` | Commit acknowledgment by majority. | Does not mean HTTP responses definitely reach the client. |
| `wtimeout` | Timeout waiting for write concern acknowledgment. | Does not force the server to undo an applied write. |
| `readPreference: primary` | Routes operations to the primary for transaction writes. | Does not prevent elections or failover. |
| Transaction lifetime limit | Server caps how long a transaction stays open. | Not the same as HTTP timeout or Java socket timeout. |
| Driver socket/selection timeouts | Bounds waiting on network/topology. | Does not tell the business outcome after timeout. |

### 8.1. Why Shouldn't Transactions Stay Open Too Long?

A long-running transaction can:

- Pin snapshot history and consume storage/cache resources.
- Increase write conflicts and abort/retry counts.
- Hit the server's transaction lifetime threshold.
- Be impacted by DDL or chunk migrations depending on topology/version.
- Force connections/callers to wait past business deadlines.

Never hold one transaction open to scan millions of records or call external APIs for minutes; split into partitioned jobs, ledger models, or idempotent workflows.

### 8.2. Transactions Do Not Replace Unique Indexes

If two requests concurrently insert `TR-100`, **unique `_id` on `transfers`** protects identity. Snapshot reads/transactions do not replace business idempotency constraints; handle duplicates/retries and compare payloads.

### 8.3. Snapshot and Majority Are Distinct

`readConcern:"snapshot"` governs the transaction's read view; `writeConcern:"majority"` governs commit acknowledgment/durability. These are two separate layers. Across multiple clusters, a transaction in one cluster **does not cover systems outside that cluster**.

## 9. Error Classification: Transient vs. Unknown Commit Outcome

### 9.1. `TransientTransactionError`

An operation inside a transaction can fail due to a write conflict, election, network error, or transient condition. The MongoDB driver may attach error label:

~~~text
TransientTransactionError
~~~

Design meaning: **the current transaction should not continue as if nothing happened**. The driver callback helper can abort and **retry the entire body** in a fresh transaction if budget remains and the error is retryable.

Typical sequence:

~~~text
Start transaction #1
  read / write
  -> write conflict, error label TransientTransactionError
Abort #1
Backoff within budget
Start transaction #2
  run all database operations from beginning
Commit #2
~~~

**Not every `MongoDB` exception carries this label.** Duplicate keys, validation failures, insufficient funds, or auth errors do not become transient. The server/driver version and exact error determine the label.

### 9.2. `UnknownTransactionCommitResult`

If `commitTransaction` was sent but no response arrived, the driver may attach:

~~~text
UnknownTransactionCommitResult
~~~

Meaning: **do not assume the transaction aborted**. While the session/transaction remains usable, the transaction spec's retry path is **re-sending `commitTransaction` for that exact same transaction**, because commit retries are designed not to turn one transaction into a second one.

~~~text
Transaction body succeeded
        |
        v
commitTransaction attempt #1
        |
        +-- response ACK --------> SUCCESS
        |
        +-- response lost / unknown
                |
                v
          retry commitTransaction
          SAME session + transaction
                |
                +-- ACK ----------> SUCCESS
                |
                +-- still unknown -> UNKNOWN / verify
~~~

**Never re-run the entire transfer body immediately after an unknown commit**, especially if the body had side effects outside MongoDB. When using the Java driver helper (`withTransaction`), it performs retries per spec; do not wrap it in an unbounded manual retry loop.

### 9.3. Business Conflicts Are Not Transient Infrastructure Errors

Example:

~~~text
Source account balance = 20,000
Requested transfer = 50,000
Conditional debit matchedCount = 0
~~~

This is a business result **`INSUFFICIENT_FUNDS`**, not a transient glitch to retry hundreds of times. If the source account is missing, return the corresponding error; if the same `transferId` arrives with a different payload, return **`IDEMPOTENCY_CONFLICT`**.

### 9.4. Other Error Labels Cannot Be Ignored

MongoDB drivers expose other labels and error codes for retryable writes, networking, sharding, timeouts, and transactions. An application must:

- Rely on **driver exception classes, error codes, and error labels** instead of parsing message strings.
- Check docs for your exact driver/server version.
- Never retry auth, validation, duplicate-key, or insufficient-funds errors as transient.
- Track actual attempt counts because the driver may already have retried.
- Enforce an overall deadline for the entire business request.

### 9.5. Practical Decision Table

| Error/Outcome | Commit ACK Received? | Action |
|---|---|---|
 Pre-transaction validation failure | Not started | Return input error; do not retry. |
 Insufficient funds on debit | Commit not sent | Abort; return business conflict. |
 Duplicate `transferId` with same payload | Prior commit may exist | Read transfer record, check fingerprint/status; do not transfer again. |
 Duplicate `transferId` with different payload | Cannot treat as equivalent | Return idempotency conflict. |
 Write conflict + `TransientTransactionError` before commit | No | Retry whole transaction via helper/budget. |
 Server selection/network failure before commit; transaction aborted/failed | No | Inspect error semantics; abort/retry transaction per label. |
 `UnknownTransactionCommitResult` on commit | Unknown | Retry **commit of same txn** if possible; then verify business outcome. |
 Majority write concern timeout on commit | Unconfirmed | Never assume rollback; retry commit/verify per spec. |
 HTTP client disconnect after commit request | Client may have missed ACK | Reuse same idempotency key + status/read reconciliation. |
 Error sending email after commit ACK | Transaction committed | Never "roll back" DB by re-running transfer; retry email separately via outbox. |

### 9.6. Tri-State Outcome Model

Avoid a plain boolean `success` when outcomes can be uncertain. An internal API can use:

~~~text
COMMITTED
NOT_COMMITTED_CONFIRMED
UNKNOWN_REQUIRES_VERIFICATION
~~~

`UNKNOWN` does not mean "50% succeeded"; it represents **missing knowledge on the client side**. After verification, the state may resolve to committed or not committed. Preserve the exact same business transfer ID across retries and recovery.

## 10. Exercise D — Java Sync Driver with `withTransaction`

This is the preferred approach for many imperative Java services: use the driver's **transaction helper** instead of hand-rolling retry loops around every command. Examples target MongoDB Java Sync Driver 5.x; choose the exact artifact version from your project's BOM and driver docs.

### 10.1. Illustrative Dependency

~~~groovy
dependencies {
    implementation 'org.mongodb:mongodb-driver-sync:<compatible-5.x-version>'
}
~~~

Replace `<compatible-5.x-version>` with a real version; never mix a newer driver with an incompatible BOM. The sample code focuses on transaction APIs and is not yet a production-hardened security service.

### 10.2. Transfer Function with Guards Inside the Callback

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoException;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class TransferInTransaction {
    public static String transferOnce(
            MongoClient client, String transferId,
            String from, String to,
            long amountMinor, String currency) {

        if (transferId == null || transferId.isBlank()) {
            throw new IllegalArgumentException("transferId required");
        }
        if (from == null || to == null || from.equals(to)) {
            throw new IllegalArgumentException("invalid accounts");
        }
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("currency required");
        }

        MongoDatabase db = client.getDatabase("txn_lab");
        MongoCollection<Document> accounts =
            db.getCollection("accounts");
        MongoCollection<Document> transfers =
            db.getCollection("transfers");
        MongoCollection<Document> ledger =
            db.getCollection("ledgerEntries");
        MongoCollection<Document> outbox =
            db.getCollection("outbox");

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY
                .withWTimeout(5, TimeUnit.SECONDS))
            .readPreference(ReadPreference.primary())
            .build();

        try (ClientSession session = client.startSession()) {
            return session.withTransaction(() -> {
                // Unique _id: business idempotency anchor.
                transfers.insertOne(session, new Document()
                    .append("_id", transferId)
                    .append("from", from)
                    .append("to", to)
                    .append("amountMinor", amountMinor)
                    .append("currency", currency)
                    .append("status", "COMPLETED"));

                UpdateResult debit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", from),
                        Filters.eq("currency", currency),
                        Filters.gte("balanceMinor", amountMinor)),
                    Updates.inc("balanceMinor", -amountMinor));

                if (debit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "SOURCE_MISSING_OR_INSUFFICIENT_FUNDS");
                }

                // Guard against signed int64 overflow on credit.
                long upperBound = Long.MAX_VALUE - amountMinor;
                UpdateResult credit = accounts.updateOne(
                    session,
                    Filters.and(
                        Filters.eq("_id", to),
                        Filters.eq("currency", currency),
                        Filters.lte("balanceMinor", upperBound)),
                    Updates.inc("balanceMinor", amountMinor));

                if (credit.getMatchedCount() != 1) {
                    throw new IllegalStateException(
                        "DESTINATION_MISSING_OR_OVERFLOW");
                }

                ledger.insertMany(session, List.of(
                    new Document("_id", transferId + ":DEBIT")
                        .append("transferId", transferId)
                        .append("accountId", from)
                        .append("currency", currency)
                        .append("deltaMinor", -amountMinor),
                    new Document("_id", transferId + ":CREDIT")
                        .append("transferId", transferId)
                        .append("accountId", to)
                        .append("currency", currency)
                        .append("deltaMinor", amountMinor)));

                outbox.insertOne(session, new Document()
                    .append("_id", "transfer:" + transferId)
                    .append("transferId", transferId)
                    .append("eventType", "TransferCompleted")
                    .append("published", false));

                return transferId;
            }, options);
        }
    }
}
~~~

Explanation:

- `ClientSession` defines transaction scope; collection methods receive **`session`** on every write.
- `withTransaction` executes commit/abort and handles transaction retries and commit retries per Java driver specs; the callback **may run more than once**.
- Unique IDs on `transfers`, `ledgerEntries`, and `outbox` prevent duplicate effects on replayed business requests, though conflicts/verification must still be handled.
- Debit uses an atomic predicate and checks `matchedCount`.
- Credit guards against int64 overflow for `amount > 0`. Initial account balances must use BSON int64 and valid business ranges; never mix numeric types.
- This snippet omits ACL/tenant checks, limits/currency exponents, idempotency fast paths, full API exception mapping, audit/recovery, and request deadlines. It is a **lab example** to teach mechanics.

### 10.3. Why Not Send Emails Inside the Transaction Callback?

**Wrong:**

~~~java
session.withTransaction(() -> {
    // MongoDB operations...
    emailClient.sendTransferConfirmation(transferId);
    return transferId;
}, options);
~~~

If the transaction callback retries, multiple emails are sent; if the DB aborts afterward, the user gets a false confirmation. **Better:** write an `outbox` record inside the transaction; a separate worker publishes emails/events after commit using idempotent delivery.

### 10.4. Never Catch and Swallow MongoException Inside the Body

**Dangerous:**

~~~java
session.withTransaction(() -> {
    try {
        accounts.updateOne(session, filter, update);
    } catch (MongoException e) {
        log.warn("ignore and continue", e);
    }
    return "OK";
});
~~~

The transaction may already be marked aborted by the server, or the body is now missing a critical write. Never swallow errors and return success. Even for truly optional operations, understand transaction state and business invariants; write-critical errors must **propagate** so the helper can abort or retry properly.

### 10.5. Callbacks Can Re-Run and Source Data Can Change

Because retrying the whole body opens a fresh snapshot, a concurrent transfer can change balances between attempts. Never cache `balanceMinor` from a pre-transaction read and carry it into later attempts; rely on **conditional updates** as actual guards. For workflows needing an immutable price quote or FX rate, persist the reference/rate contract and verify consistency rather than fetching a new rate on every callback retry without business approval.

## 11. Exercise E — Java Managing Commit Manually: Seeing Both Retry Loops Clearly

To understand what the driver helper does, review the **algorithmic pseudocode** (not for production copy-paste):

~~~text
function withTransaction(body, deadline):
  while before deadline:
    session.startTransaction()
    try:
      result = body()
    catch e:
      abortTransactionIfPossible()
      if e.hasLabel(TransientTransactionError) and budget:
        backoff()
        continue  // WHOLE transaction
      throw e

    while before deadline:
      try:
        commitTransaction()
        return result
      catch e:
        if e.hasLabel(UnknownTransactionCommitResult) and budget:
          backoff()
          continue  // COMMIT same transaction
        if e.hasLabel(TransientTransactionError) and policy says retry body:
          break     // restart whole transaction
        throw e

  throw DeadlineExceededOrUnknownOutcome
~~~

This diagram shows **conceptual flow** only; the driver specification covers many additional exceptions, timeout behaviors, labels, and server-version nuances. Never write a homegrown retry loop from this snippet alone, as it is easy to mishandle write concern errors, commit retries, session lifecycles, transaction numbers, and driver CSOT.

### 11.1. Recognizing Error Labels in Java

~~~java
try {
    String result = TransferInTransaction.transferOnce(
        client, "TR-200", "acct:A", "acct:B", 5000L, "VND");
    System.out.println("Commit ACK for " + result);
} catch (MongoException e) {
    if (e.hasErrorLabel("UnknownTransactionCommitResult")) {
        // Do not declare rollback.
        // Proceed with controlled verification of TR-200.
        System.err.println("COMMIT_OUTCOME_UNKNOWN: TR-200");
    } else if (e.hasErrorLabel("TransientTransactionError")) {
        // Driver helper may already have retried;
        // preserve deadline and original idempotency key.
        System.err.println("TRANSIENT_TRANSACTION_FAILURE");
    } else {
        System.err.println("MONGO_FAILURE: " + e.getCode());
    }
}
~~~

This classifies errors **after the helper throws**; do not wrap it in an unbounded retry loop in the Java caller. `hasErrorLabel` takes a string, so use spec-exact error-label names updated for your driver version.

### 11.2. Java Retryable Writes Differ from Transaction Retries

The MongoDB Java driver enables `retryWrites=true` under supported deployments/operations. Retryable writes outside transactions use protocol support to avoid applying an eligible write twice within one logical attempt. However:

- Not all write operations are retryable.
- Not all errors/network failures are retried.
- A **new** HTTP request may start new session/transaction IDs.
- Never generate a **new random business ID** on retries.
- Transaction callback retries and commit retries follow separate semantics.

Therefore, keep idempotency records and unique keys **at the business layer** rather than relying on `retryWrites` as your sole protection.

### 11.3. Retry Budgets

Suppose the API deadline is 2 seconds, server selection takes 1 second, the callback runs 2 DB queries, and commit may retry. Track the **remaining total request budget**. A retry succeeding after the client HTTP timeout can leave the DB committed while the client doesn't know. Combine:

- Clear ingress deadlines.
- Attempt caps and backoff with jitter.
- Retry attempt metrics.
- Stable `transferId`.
- Status lookup/verification when unknown.

Never use `while(true)` or "retry for 60 seconds" when the SLO is 500 ms.

## 12. Exercise F — API Idempotency When the Client Retries

### 12.1. An HTTP Retry Is Independent of the Driver Transaction

Suppose a client sends:

~~~http
POST /transfers
Idempotency-Key: TR-100
Content-Type: application/json

{
  "from": "acct:A",
  "to": "acct:B",
  "amountMinor": 50000,
  "currency": "VND"
}
~~~

If the gateway times out after the DB committed, the client will resend the **exact same request with the same `Idempotency-Key`**. The service must never mint `TR-101` just to "try again."

### 12.2. A Unique Operation Record Is Durable Proof

A record:

~~~javascript
{
  _id: "TR-100",
  requestFingerprint: "<canonical-request-hash>",
  from: "acct:A",
  to: "acct:B",
  amountMinor: NumberLong("50000"),
  currency: "VND",
  status: "COMPLETED",
  committedAt: ISODate("2026-11-14T03:00:00Z")
}
~~~

The `transfers` record is **inserted in the same transaction** as both account updates and the ledger. Hence, the presence of a committed record with matching payload proves the workflow ran to commit under the contract. Compute `requestFingerprint` from canonicalized payload fields using a versioned policy; never store placeholders in production.

### 12.3. Logic for Handling Existing Requests

~~~text
receive transferId + payload
          |
          v
validate authentication / tenant / amount / currency
          |
          v
read transfers[transferId] with approved consistency
          |
          +-- exists, same fingerprint, COMPLETED
          |       -> return original result, NO debit
          |
          +-- exists, different fingerprint
          |       -> return IDEMPOTENCY_CONFLICT
          |
          +-- exists, in-progress state (if separate request ledger)
          |       -> return PENDING/verify/retry later
          |
          +-- missing
                  -> attempt transaction with UNIQUE transfer ID
                  -> on duplicate/conflict, re-read and classify
                  -> on unknown commit, verify same ID
~~~

**Read-before-write does not prevent races.** Two requests can both read "missing" and start transactions simultaneously. **Unique indexes** plus write-conflict/duplicate-key handling are the final line of defense; never treat a pre-check as an atomic lock.

### 12.4. How to Compare Fingerprints

Canonical input should include:

~~~text
tenantId
authenticated initiator / scope
fromAccount
toAccount
amountMinor (int64 semantics)
currency
business purpose/version if relevant
~~~

Never hash a raw JSON string if key ordering or whitespace can vary. Use deterministic encoding or versioned canonical JSON. Always **validate the new input first** before comparing or returning a prior result; never let an unauthorized user inspect another tenant's transfer status simply by guessing an ID.

### 12.5. Handling Duplicate Keys Properly

~~~java
try {
    return TransferInTransaction.transferOnce(
        client, transferId, from, to, amount, currency);
} catch (MongoException e) {
    // The exact error class/code depends on operation/server/driver.
    // Duplicate-key 11000 is one possible result for reused ID.
    if (e.getCode() == 11000) {
        // Read committed transfer record with suitable consistency;
        // compare canonical payload and return previous result if same.
    }
    throw e;
}
~~~

This illustrates the **decision point**: on duplicate key, never blindly return success. Read the committed record and verify payload/status/tenant, or return `409 Conflict` when the same ID carries a different payload. A duplicate key on **another ledger/outbox index** may indicate data corruption rather than a completed replay; always identify which constraint fired.

### 12.6. A Separate Request Ledger Before the Transaction?

Sometimes applications insert `idempotencyRequests` as `PENDING` **before** opening the transaction:

~~~text
HTTP request accepted
  |
  v
INSERT PENDING(idempotencyKey, fingerprint, lease/owner)
  |
  v
execute transaction
  |
  +-- commit -> mark result COMPLETED
  |
  +-- timeout/worker crash -> recovery worker verifies outcome
~~~

This supports status polling and deduplicating concurrent callers, yet introduces its own **state machine**: `PENDING` records can be orphaned if a process crashes, requiring lease/expiry/owner fencing, recovery jobs, atomic transitions, and distinguishing "not yet run" from "unknown outcome." Never configure a TTL to auto-delete `PENDING` records before confirming zero side effects remain. If persistent pending state is unnecessary, rely on committed `transfers` records + properly scoped gateway idempotency caching—never pretend to handle unknown outcomes using an in-process memory cache alone.

### 12.7. HTTP Response When Outcome Is Unknown

Never automatically return `200 OK`, nor always `500 retry with new ID`. An API can:

- Return an explicit `UNKNOWN/PENDING_VERIFICATION` state with `operationId` via a job/status protocol **when the backend stores durable lookup state**.
- Or return `503`/`504` advising "outcome unconfirmed; retry with the same `Idempotency-Key` or check the status endpoint," without exposing internal DB topology.
- Return `409` when a reused key has a mismatched payload; never let callers overwrite it.

`202 Accepted` should only be used when the system has **durably accepted** the request with a background continuation/status lookup mechanism. Never use `202` to mask an unknown outcome when no lookup exists.

### 12.8. Client Retries Must Also Be Bounded

HTTP clients should retry with exponential backoff + jitter and bounded attempts/total deadline. If every client retries at the exact same 1-second mark, a newly elected primary can get hit by a **retry storm**. Status endpoints and read-repair reduce redundant write-path retries when clients merely need to check outcomes.

## 13. Exercise G — Reconciling Outcomes After Unknown Commit

### 13.1. Three Sources of Evidence

After `UnknownTransactionCommitResult`, inspect:

1. Does `transfers[transferId]` contain a committed record with matching fingerprint and status?
2. Does `ledgerEntries` contain the right debit/credit legs summing to zero?
3. Do `accounts` satisfy invariants alongside the ledger?

**Never** rely solely on current account balances to conclude whether a transfer ran, because **other concurrent transfers** may have touched both accounts. The transfer record and ledger with stable IDs provide direct proof.

### 13.2. Verification Queries in mongosh

~~~javascript
const t = lab.transfers.findOne({ _id: "TR-100" })
const legs = lab.ledgerEntries
  .find({ transferId: "TR-100" })
  .toArray()

printjson({ transfer: t, ledger: legs })
~~~

In a small lab, `toArray()` fetches at most two ledger legs per contract. On real large ledgers, bound queries, rely on unique keys, and avoid printing PII. These two queries **do not share a single snapshot** if collections are changing; consistent proof requires appropriate read concern/snapshot policies.

### 13.3. Checking Ledger Sum by transferId

~~~javascript
lab.ledgerEntries.aggregate([
  { $match: { transferId: "TR-100" } },
  {
    $group: {
      _id: "$transferId",
      n: { $sum: 1 },
      netMinor: { $sum: "$deltaMinor" },
      types: { $addToSet: { $type: "$deltaMinor" } },
      accounts: { $addToSet: "$accountId" }
    }
  }
])
~~~

In the toy model, require **`n=2`**, `netMinor=0`, types containing only `long`, accurate account IDs, and one debit/one credit. If the transfer record and ledger are absent right after a commit timeout, **do not immediately conclude `NOT_COMMITTED`**: primary elections, replication lag, stale reads, or an in-flight commit can leave evidence incomplete.

### 13.4. Consistency Level of Verification Reads

On a healthy replica set, read with `readPreference: primary` and `readConcern: majority` to reduce the risk of reading rollback-able data. Still, a majority read **does not create a shared snapshot** across two independent queries without a transaction/snapshot, and absence alone does not definitively prove commit never happened or cannot still finish.

In a recovery protocol:

- Wait until the cluster has an eligible primary/quorum.
- Query using the exact `transferId` and verify payload.
- If no record is found, keep `UNKNOWN` until the retry/verification protocol reaches a valid conclusion under deadlines/fencing.
- If safe idempotent re-execution is permitted, reuse the **exact same key**—never create a new business ID.
- Provide escalation/manual review when an outcome remains unverifiable.

### 13.5. Never Use "Checking Total A+B" as the Sole Answer

If A and B also receive other transfers, their sum could still equal 120,000 even if `TR-100` never ran—or change legitimately due to deposits/withdrawals. Rely on **event/ledger identity** and per-`transferId` reconciliation, not only an aggregate snapshot of two accounts.

### 13.6. Process Crash Right After Commit

~~~text
1. HTTP request TR-100 arrives.
2. MongoDB transaction commits.
3. Process crashes before returning HTTP 201.
4. Client retries TR-100 through another pod.
5. Pod reads committed transfers.TR-100.
6. Fingerprint matches -> return original completed result.
7. NO second debit or credit.
~~~

This clearly shows why **idempotency records belong in durable storage**, never solely in an in-memory JVM flag.

### 13.7. Recovery Worker and Uncertain States

An independent worker can scan `idempotencyRequests` stuck in `PENDING_VERIFICATION`, inspect MongoDB state, and reconcile. Workflow:

~~~text
PENDING_VERIFICATION
        |
        +--> transfer record matches + invariants
        |       -> COMPLETED_VERIFIED
        |
        +--> same ID but payload differs
        |       -> CONFLICT / MANUAL_INVESTIGATION
        |
        +--> no conclusive evidence yet
        |       -> RETRY_LATER with backoff
        |
        +--> controlled idempotent re-execution authorized
                -> use SAME transferId, verify again
~~~

Never mark a request `FAILED` just because 3 status queries hit server selection timeouts; that is a **monitoring/recovery failure**, not proof the transfer never happened.

## 14. Exercise H — Simulating Primary Stepdown on a Lab Replica Set

### 14.1. Objective

Observe:

- An active transaction conflicting/failing when the primary changes.
- Driver SDAM updating the cluster description.
- New commands waiting on server selection.
- Errors bearing `TransientTransactionError` or `UnknownTransactionCommitResult` depending on **exact timing** of the network/election event.

**There is no guarantee** every stepdown produces `UnknownTransactionCommitResult`. If the client hasn't sent commit yet, the outcome is usually not unknown-commit; if commit already ACKed, no error appears at all. This exercise teaches **timing classification**, not forcing a specific label by chance.

### 14.2. Prerequisites

- A **3-node lab replica set** with a healthy electable secondary.
- Zero real user traffic, and cluster admin privileges for the lab.
- App uses a proper seed list / `replicaSet` URI, not `directConnection=true` pinned to an old primary.
- Metrics/traces attach correlation IDs to every request.
- Fresh fixture IDs per run—never reuse an already-committed `TR-100` when testing new transactions.

### 14.3. Running Bounded Repeated Transactions in the Lab

For example, a worker sends a **bounded series** of distinct transfer IDs with small amounts:

~~~text
TR-LAB-001: transfer 100
TR-LAB-002: transfer 100
TR-LAB-003: transfer 100
...
TR-LAB-010: transfer 100
~~~

In another terminal, connect directly to the **lab primary**, verify `rs.status()`, and intentionally step it down:

~~~javascript
// ONLY on an authorized, disposable replica set primary in LAB:
rs.stepDown(15)
~~~

This command may interrupt the `mongosh` connection, temporarily prevent the old primary from accepting writes, and trigger an election if an eligible secondary exists. It **impacts availability**—never run in production. Without an electable secondary/quorum, it can fail or cause unwanted downtime. Never pass `force:true` to bypass safety checks just for a lab demo.

### 14.4. Recording the Timeline

~~~text
time       event
--------   ---------------------------------------------------
12:00:00   TR-LAB-003 body started on primary A
12:00:01   PRIMARY A stepdown initiated
12:00:02   Server selection fails / SDAM sees topology change
12:00:04   SECONDARY B elected PRIMARY
12:00:05   Driver selects B, retries eligible transaction
12:00:06   TR-LAB-003 eventually acknowledged or reported unknown
~~~

Timestamps and outcomes above are an **illustrative scenario**, not logs from an executed lab. Always record **actual** Java timestamps, error codes/labels, command events, and DB outcomes during practice.

### 14.5. Key Takeaways

If the driver reports an error during the **pre-commit body**, retrying the transaction may be appropriate. If the error hits **commit result**, never launch a brand-new transfer with a different ID. After the election, verify using the stable `transferId`; remember that `withTransaction` may already have retried internally.

### 14.6. While the Cluster Has No Primary

`serverSelectionTimeoutMS` may expire, indicating **the client could not locate an eligible server** within the selection window. Never raise connection pool size endlessly to "fix" primary elections. Choose appropriate request deadlines and fallbacks; for writes with ambiguous outcomes, preserve verification state rather than declaring definitive failure.

## 15. Exercise I — Disconnecting Right at the Commit Boundary

### 15.1. Breakpoints to Distinguish

~~~text
P0 before transaction start
P1 after first debit, before credit
P2 after all writes, before commit send
P3 commit sent, before server applies
P4 commit applied, before client receives ACK
P5 after commit ACK, before HTTP response
~~~

| Point | What We Can Infer |
|---|---|
| P0 | Request has not started a DB transaction, though we must still guard against earlier attempts with the same key. |
| P1 | If uncommitted and aborted, debit never becomes a committed write. |
| P2 | If commit was never sent, the transaction has not succeeded; session/timeout handles abort. |
| P3 | Client does not know if the server received or applied commit. |
| P4 | Server may have committed while client never received confirmation. |
| P5 | Database commit succeeded; HTTP client may still time out and retry. |

Points **P3/P4** are specifically why `UnknownTransactionCommitResult` and verification exist. Never guess the exact breakpoint `P` from a generic network error string without instrumentation.

### 15.2. Simulating with a Fault Proxy / Test Harness

To reproduce **lost commit response**, use a lab test harness/proxy capable of:

1. Letting the commit request **actually reach the server**.
2. Allowing the server to apply the commit.
3. Intentionally dropping or delaying the **response** on the return path.
4. Recording `transferId`, attempt number, timestamps, and observed driver errors.
5. Disabling the fault afterward and querying the DB to verify.

Do not merely "cut the network before sending commit" and claim you tested unknown commit. With Toxiproxy, Chaos Mesh, or fault-injection frameworks, exact setup depends on network topology/TLS and requires authorization; a misplaced interceptor can drop packets **before the server commits**, creating a different test case.

### 15.3. MongoDB `failCommand` Test Failpoint

Some test deployments expose the `failCommand` failpoint to inject errors into commands, including transaction commands depending on server/test enablement. **Do not assume failpoints are available on Atlas/production**, and a `closeConnection` failpoint triggered on receiving `commitTransaction` may close the socket **before the commit executes**, failing to demonstrate "server committed, response lost." Verify fault placement via server traces and consult your test framework's docs.

### 15.4. Predicting Three Trials

- **Trial A:** Drop request before commit reaches the server → cannot prove commit happened; transaction aborts after timeout.
- **Trial B:** Drop response after server majority-commits → client sees timeout/unknown while transfer record and ledger exist.
- **Trial C:** Drop nothing → clean commit ACK; HTTP can still time out if a downstream gateway drops it.

Expected output is **classifying each scenario from evidence**, not forcing fixed ratios of error labels.

### 15.5. What If You Cannot Set Up a Proxy?

Write an integration test with a **mock transaction gateway** returning `UNKNOWN` right after the repository completes, exercising **application idempotency and status recovery**. That proves **application logic** handles injected ambiguity, not which runtime exception class/label the MongoDB driver throws during a real network fault.

### 15.6. Observing Outcomes Using the Same ID

Once the fault clears:

~~~javascript
lab.transfers.findOne({ _id: "TR-LAB-007" })
lab.ledgerEntries.find({ transferId: "TR-LAB-007" })
~~~

If the transfer and both valid legs exist, never re-execute as `TR-LAB-007-RETRY`. If no record appears, **do not equate absence with rollback right after quorum loss**; follow verification deadlines, consistency checks, and retry policies.

## 16. Exercise J — Two Competing Requests and Write Conflicts

### 16.1. Same Account, Two Distinct Transfer IDs

Account A initially holds `100,000`. Two requests arrive concurrently:

~~~text
TR-C1: A -> B amount 80000
TR-C2: A -> C amount 80000
~~~

Under a **no-overdraft** policy, both cannot succeed. MongoDB transactions keep **each transfer's** writes atomic; `balanceMinor >= amount` enforces balance sufficiency at write time. Concurrent transactions can trigger a **write conflict**, get retried by the driver helper per transient labels, and the second attempt observes the updated balance, lacks funds, and returns a business conflict.

### 16.2. Never Replace the Write Guard with a Plain Read

**Wrong:**

~~~text
T1 reads A = 100000
T2 reads A = 100000
T1 decides 80000 is affordable
T2 decides 80000 is affordable
~~~

Read-before-write fails without conditional updates or version checks. A transaction snapshot does not guarantee a business decision made from a document read **stays valid across concurrent writes**; write-time guards remain mandatory.

### 16.3. Bounded Concurrency Lab

On a fixture with `A=100,000` and valid B/C, launch two tasks on a two-worker executor, each calling `TransferInTransaction.transferOnce(...)` with distinct IDs `TR-C1`/`TR-C2`. Never spawn unbounded threads. Once both finish or throw:

1. Verify at most one transfer has status `COMPLETED` per contract.
2. Sum affected account balances and ledger legs.
3. Verify A never goes negative if overdrafts are forbidden.
4. Check logs for write conflicts/transient retries (may or may not occur depending on scheduling).
5. Never rely on task submission order to assume which transfer wins.

### 16.4. Same transferId Arriving at Two Pods

Two requests sharing **`TR-C1`** can both observe "missing" before either transaction starts. Unique records and conditional writes ensure at most one business effect commits. If one caller hits a duplicate key or write conflict, **verify the transfer record** and return the original result when payloads match; never create `TR-C1-2`.

### 16.5. Write Conflicts Are Not Automatically Final Application Errors

If the driver helper retries and commits within the deadline, HTTP returns success even though logs record a transient conflict on attempt 1. If retries exhaust the budget, return an appropriate status while preserving the stable ID. Never expose internal details like `"WiredTiger write conflict at X"` to end users.

## 17. Majority Write Concern, Timeouts, and Durability

### 17.1. `wtimeout` Is Not a Full-Transaction Timeout

If commit specifies:

~~~javascript
writeConcern: { w: "majority", wtimeout: 5000 }
~~~

`wtimeout=5000` bounds how long to wait for **majority acknowledgment**. A timeout here does not guarantee the write rolled back. The primary may have applied it, with durability governed by replication, quorum, and failover.

### 17.2. What Happens When Quorum Is Lost?

In a 3-node replica set, if too few members can acknowledge majority, commits cannot complete majority acknowledgment within the deadline. **Taking down or disrupting two nodes** is an outage-inducing test—run only in a controlled disposable lab; never induce this in production just to learn.

### 17.3. Write Concern vs. Read Concern

| Question | Mechanism Involved |
|---|---|
| "How many members acknowledge commit?" | `writeConcern`. |
| "Which consistent view does the transaction read?" | `readConcern`. |
| "Did the client receive the commit response?" | Network/socket/driver retries. |
| "Will a duplicate request transfer money twice?" | Idempotency key + unique constraint/business protocol. |
| "Is the ledger balanced?" | Independent business reconciliation. |

Never cite `w:"majority"` as proof of **HTTP exactly-once**, nor `readConcern:"snapshot"` as proof an external email was sent once.

### 17.4. `retryWrites` and Rollback

The server can roll back non-majority-committed writes during primary failover per replication semantics; majority commits offer stronger durability within deployment guarantees. Yet a response timeout never tells the client which branch occurred. For critical operations, set appropriate write concerns and verify via consistency policies and idempotency rather than guessing from network errors.

### 17.5. Client Operation Timeouts

The Java driver has multiple timeout layers: server selection, socket/network, connection checkout, server-side `maxTimeMS`, and **client-side operation timeout (CSOT)** in supporting versions—plus HTTP gateway deadlines. These **are not identical**, and cancelling at one layer does not always abort an already-dispatched server command.

~~~text
HTTP request deadline
  |
  +-- app request queue
  +-- server selection
  +-- connection checkout
  +-- transaction body commands
  +-- commit/retry and verification
  +-- HTTP response serialization
~~~

Derive deadlines from **business SLOs**, leave headroom for recovery/status responses, and avoid raising every timeout to minutes just to "eliminate errors."

### 17.6. Avoid the "Just Raise the Timeout" Anti-Pattern

When no primary exists, a longer `serverSelectionTimeoutMS` simply stalls clients longer without conjuring a primary. When DB CPU is saturated, raising socket timeouts masks queue pileups. When commit is unknown, longer timeouts **do not provide idempotency**. Identify the slow phase and act appropriately.

## 18. Outbox: Moving Side Effects Outside the Transaction Safely

### 18.1. Problem with Sending Email Before Commit

~~~text
MongoDB transaction opened
  debit/credit prepared
  send email "Transfer completed"
  transaction aborts
~~~

An already-sent email cannot be rolled back by MongoDB. Similarly, payment SDK calls, HTTP webhooks, and Kafka publishes are **external side effects** that do not participate in MongoDB transactions.

### 18.2. Transactional Outbox

~~~text
One MongoDB transaction:
    update accounts
    insert transfer record
    insert ledger entries
    insert outbox event PENDING
       |
       v
COMMIT
       |
       v
Outbox publisher (separate job)
    read pending events
    publish to broker/email service
    mark published or checkpoint
~~~

If the transaction aborts, no outbox event commits. If it commits and the publisher crashes, the event stays pending for later dispatch. **This does not guarantee exactly-once publishing**: a publisher can publish successfully and crash before marking `published`.

### 18.3. Idempotent Publish/Consume

Every event carries a stable ID:

~~~json
{
  "_id": "transfer:TR-100",
  "transferId": "TR-100",
  "eventType": "TransferCompleted",
  "published": false
}
~~~

Consumers should track processed event IDs or use provider idempotency keys, processing an event only once per policy. If the broker delivers an event twice, downstream must never issue two invoices or charge twice.

### 18.4. Publish History Needs Auditing

Outbox workers should track:

- Event ID and transfer ID.
- Attempt count, `nextRetryAt`, redacted `lastErrorCode`.
- `publishedAt` / acknowledgment evidence.
- Lease/owner fencing across multiple workers.
- Dead-lettering / manual review once retries exceed thresholds.

Never delete an outbox event before confirmed per protocol. A unique `_id` deduplicates the logical event, not consumer side effects.

### 18.5. When to Use a Saga?

If a business operation spans MongoDB, an external payment gateway, and a separate inventory service, one MongoDB transaction cannot span all three. A **Saga** breaks it into local transactions with retries, compensation, and an idempotent state machine. Compensation is not physical rollback: issuing a refund is a **new audited business operation**, not erasing a captured payment's history.

## 19. Verifying Independent Business Invariants

### 19.1. Do Accounts Have Expected Balances and Currencies?

~~~javascript
lab.accounts.find(
  { _id: { $in: ["acct:A", "acct:B"] } },
  { balanceMinor: 1, currency: 1, version: 1 }
)
~~~

In an isolated lab, `A+B` before and after must stay `120,000` for zero-fee internal transfers. If other movements touch those accounts, comparing current totals **is insufficient** to verify `TR-100` alone.

### 19.2. Per-Transfer Ledger Check

~~~javascript
lab.ledgerEntries.aggregate([
  { $match: { transferId: "TR-100" } },
  {
    $group: {
      _id: "$transferId",
      entries: { $sum: 1 },
      netDelta: { $sum: "$deltaMinor" },
      dataTypes: { $addToSet: { $type: "$deltaMinor" } },
      accounts: { $addToSet: "$accountId" }
    }
  }
])
~~~

In the fee-free toy transfer, expect 2 entries, `netDelta=0`, type `long`, and exact accounts A/B. Yet `netDelta=0` **is not sufficient**: two entries with flipped signs or wrong IDs can still sum to 0; check per-leg IDs, amounts, currencies, and statuses.

### 19.3. Finding Transfers with Wrong Ledger Counts

~~~javascript
lab.ledgerEntries.aggregate([
  {
    $group: {
      _id: "$transferId",
      n: { $sum: 1 },
      net: { $sum: "$deltaMinor" }
    }
  },
  {
    $match: {
      $or: [
        { n: { $ne: 2 } },
        { net: { $ne: 0 } }
      ]
    }
  }
])
~~~

This rule applies **only to the two-leg, zero-fee toy model**. Real multi-leg/fee/multi-currency ledgers must define exact debit-credit balance rules per business domain. Importantly, `$sum` skips non-numeric values, so validate `$type` and required fields before accepting a PASS.

### 19.4. Finding Transfers Missing Required Legs

~~~javascript
lab.transfers.aggregate([
  {
    $lookup: {
      from: "ledgerEntries",
      localField: "_id",
      foreignField: "transferId",
      as: "legs"
    }
  },
  {
    $match: {
      $expr: { $ne: [{ $size: "$legs" }, 2] }
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      nLegs: { $size: "$legs" }
    }
  }
])
~~~

Use only within the same database on moderately sized datasets, backed by an index on `ledgerEntries.transferId`. A `$lookup` building large arrays hits resource limits, so production reconciliation should stream partitions rather than joining a multi-terabyte ledger unguarded.

### 19.5. Checking No Outbox Event Was Lost

~~~javascript
lab.transfers.aggregate([
  {
    $lookup: {
      from: "outbox",
      let: { tid: "$_id" },
      pipeline: [
        { $match: {
            $expr: { $eq: ["$transferId", "$$tid"] }
        }}
      ],
      as: "events"
    }
  },
  {
    $match: {
      $expr: { $ne: [{ $size: "$events" }, 1] }
    }
  }
])
~~~

Expect every completed transfer to have exactly one **logical outbox event**; `published` may still be `false` before the worker dispatches it. Never treat `published: false` as an uncommitted transfer.

### 19.6. Interpreting Inconsistent State

If `transfers.TR-100.status=COMPLETED` exists without matching ledger or outbox rows, possible causes include:

- Legacy/migrated data predating the new workflow.
- Direct out-of-transaction writes.
- Session/transaction handling bugs.
- Partial database restore or migration.
- Inconsistent query read concerns or snapshots.

Never "fix" this by re-running the money transfer. First isolate record/version history, write paths, and commit evidence; repair ledger/outbox through approved, idempotent, audited remediation.

## 20. Observing the Driver and MongoDB During Disconnects

### 20.1. Separating Three Phases

A slow HTTP request can stall at:

~~~text
HTTP request accepted
   |
   v
MongoDB server selection
   |
   v
Connection checkout / TCP reconnect
   |
   v
Transaction body commands
   |
   v
commitTransaction
   |
   v
HTTP response
~~~

A `MongoTimeoutException` during **server selection** is completely different from a socket read timeout after **commit was sent**. Seeing only HTTP 504 without command-phase timelines makes it impossible to know whether the transaction committed.

### 20.2. Driver Event Listeners

The MongoDB Java Driver provides observability APIs:

| Listener/Event Family | Helps Answer |
|---|---|
| **Command monitoring** — `CommandStarted`/`Succeeded`/`Failed` | Were body/commit/abort commands sent by the driver, and what were durations/errors? |
| **SDAM** — cluster/server description/heartbeats | Which primary was eligible; did an election or topology change occur? |
| **CMAP** — pool created/cleared, checkout started/succeeded/failed | Was the driver waiting on connections, clearing pools, or reconnecting after failover? |
| **Application tracing** — request/transfer ID, attempts, deadline | How many DB attempts or HTTP retries did one business operation trigger? |
| **MongoDB server logs/metrics** | What were commit, replication, recovery, and resource symptoms on the server? |

Never rely on command listener logs as the sole audit trail for transfer outcomes: logs can be dropped during crashes, lack guaranteed retention, and a single client sees nothing of other pods.

### 20.3. Java CommandListener Counting Attempts by Command Name

~~~java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

final class TransactionCommandMetrics implements CommandListener {
    private final ConcurrentHashMap<String, LongAdder> started =
        new ConcurrentHashMap<>();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        started.computeIfAbsent(
            event.getCommandName(), ignored -> new LongAdder())
            .increment();
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        // Observe command name, elapsed time, outcome.
        // Do not log full command BSON.
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        // Observe failure type/command name with redaction.
    }
}
~~~

Register via `MongoClientSettings.builder().addCommandListener(...)` and pass settings to `MongoClients.create(settings)`. Metrics should distinguish `commitTransaction`, `abortTransaction`, `update`, `insert`, attempt counts, and failures. **Listeners are strictly for observability**—never use them to alter retry behavior or spoof responses.

### 20.4. Correlation and Fields to Log

~~~text
operationId:            TR-LAB-007
requestFingerprint:     sha256:<computed>
serviceInstance:        transfer-api-pod-2
attemptNo:              2
phase:                  COMMIT
driverErrorClass:       MongoSocketReadTimeoutException
errorLabels:            [UnknownTransactionCommitResult]
primaryBefore:          lab1
primaryAfter:           lab2
elapsedMs:              320
result:                 UNKNOWN_REQUIRES_VERIFICATION
~~~

Values above are **sample logs**, not real observed output. Never log full connection URIs/passwords, BSON containing PII, session credentials, or auth headers. Keep `requestId`/`transferId` in **retained traces/logs**, never as high-cardinality Prometheus metric labels.

### 20.5. Key Backend Metrics

- `transactions.started/committed/aborted` per server metrics available in your version.
- Replication state, election counts, majority availability.
- Driver connection checkout waits and `connectionPoolCleared`.
- Server selection failures, socket errors, and command p95/p99.
- Separate counters for transaction body retries vs. commit retries.
- Business `unknown_commit_results_total` and recovery age.
- Idempotency conflicts and duplicate-key errors.
- Ledger imbalance / transfer-without-outbox alerts.
- HTTP p95/p99, 429/503/504 rates, pod restarts, and GC pressure.

When logs show "transaction failed" while a transfer record exists, dashboards must distinguish **client-observed failures** from **committed business effects**.

### 20.6. `serverStatus` and `currentOp`

In a lab with monitoring privileges:

~~~javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 })

printjson(status.connections)
printjson(status.transactions)
printjson(status.metrics?.commands)
~~~

Nested metric names and availability vary by server version and topology. Verify missing fields against docs rather than hardcoding dashboards to examples. `$currentOp`/`db.currentOp()` reveals active operations but requires privileges; avoid printing raw commands containing sensitive data.

### 20.7. Never Restart All Pods During a Primary Election

If a liveness probe kills pods simply because the DB briefly lacks a primary for a few seconds, all pods restart simultaneously, recreating `MongoClient`s, connection pools, and TLS handshakes—triggering a **connection storm**. Keep liveness separate from readiness/dependency checks; use retries, backoff with jitter, and bounded queues so systems recover gracefully without crushing the newly elected primary.

## 21. Operations Runbook: `UNKNOWN_REQUIRES_VERIFICATION`

A practical runbook defines **owners, deadlines, evidence, escalation**, and preserves the exact idempotency key across retries.

### Step 1 — Pin Operation Identity

Preserve:

~~~text
transferId = TR-100
fingerprint = hash(from,to,amountMinor,currency,tenant,...)
receivedAt = T0
driver session/attempt correlation (if available)
~~~

Never mint a new transaction ID or random HTTP idempotency key for the same logical request just because a gateway timed out.

### Step 2 — Record the Failure Phase

Distinguish:

- Before transaction start.
- Inside body before commit.
- Inside `commitTransaction`.
- After commit ACK, before HTTP response.

Without sufficient trace data, record **`PHASE_UNKNOWN`** rather than guessing. Inspect error labels/codes, SDAM/CMAP, and topology timelines; never log passwords or PII.

### Step 3 — Do Not Issue a Compensating Transfer Immediately

While unsure if the debit occurred, a "reverse transfer" can **create spurious money** if the original transaction never committed. Issue compensation only after verifying state and obtaining business approval; it is a new operation with its own `transferId` and audit trail.

### Step 4 — Wait for Server Stability and Verify

Wait for a healthy cluster with an eligible primary, using appropriate read/write concerns. Look up `transfers[TR-100]` by stable ID and compare full payload/fingerprint. If committed, verify ledger/outbox invariants under the same consistency cut or sufficient evidence.

### Step 5 — If No Record Appears, Proceed Cautiously

Never mark `NOT_COMMITTED` from a single missing read right after an election. Where the application protocol permits **idempotent re-execution**, rerun with the exact same stable key and unique constraint (or retry commit if the original session/transaction is still alive). If evidence remains inconclusive and policy forbids retry, keep it unknown and escalate.

### Step 6 — Recovery State Transitions

~~~text
UNKNOWN_REQUIRES_VERIFICATION
         |
         +-- committed record matches + checks pass
         |       -> COMMITTED_VERIFIED
         |
         +-- definitive abort evidence / safe retry
         |       -> NOT_COMMITTED_CONFIRMED / RETRY_SAME_KEY
         |
         +-- different payload / inconsistent ledger
         |       -> SECURITY_OR_DATA_CONFLICT / MANUAL_REVIEW
         |
         +-- no reliable evidence yet
                 -> RETRY_STATUS_CHECK_WITH_BACKOFF
~~~

`NOT_COMMITTED_CONFIRMED` requires solid proof (e.g., confirmed abort ACK and commit never started in that workflow), never an assumption from "a read returned null."

### Step 7 — Return Accurate Info to the Client

- `COMMITTED_VERIFIED`: return the original transfer result without writing anything new.
- `RETRY_SAME_KEY`: only when idempotency is guaranteed, instruct client to reuse the same key.
- `UNKNOWN`: report that outcome is unconfirmed; return `operationId` for status lookup.
- `CONFLICT`: same key with different payload; refuse to process a new transfer.

Never leak balances or account IDs of another tenant through a status endpoint; auth and tenant isolation are mandatory.

### Step 8 — Post-Recovery

- Reconcile ledger/transfer/outbox so unknown cases never linger indefinitely.
- Record root cause: stepdown, network, timeout, pool starvation, or app crash.
- Update alert thresholds and runbooks.
- Re-test idempotency under concurrent requests and client retries.
- File financial/business incident reports if real impact occurred.

### 21.1. Operational Service Levels

Define separately:

~~~text
API response SLO
  -> time to respond ACK or UNKNOWN accurately

Resolution SLO
  -> time to classify UNKNOWN to committed/not committed

Reconciliation SLO
  -> time to prove ledger and dependent effects are consistent
~~~

You cannot promise every transfer gets a commit confirmation in 200 ms during an election, yet you can design APIs that return **honest, recoverable states** without ever duplicating effects.

## 22. Integration Testing and Fault-Injection Plan

### 22.1. Three Testing Layers

| Layer | What It Tests | What It Cannot Test |
|---|---|---|
| **Unit tests** | Payload mapping, idempotency fingerprint, state machine, error classification. | Real MongoDB server commit/rollback behavior. |
| **Integration tests on lab replica set** | Sessions, transaction atomicity, unique indexes, concurrent write conflicts, verification queries. | True network partitions without a harness. |
| **Controlled fault-injection tests** | Elections, timeouts, dropped/delayed commit responses, process crash/recovery. | Every possible production topology/network combination. |

Never use standalone MongoDB mocks to claim multi-document transactions are tested. Integration tests need a **replica set test topology** matching production server versions closely.

### 22.2. Required Test Matrix

| Test ID | Injection / Condition | Mandatory Business Outcome |
|---|---|---|
| T01 | Normal commit, amount 50,000 | One committed transfer, A−50,000 / B+50,000, 2 ledger legs, 1 outbox. |
| T02 | Debit insufficient funds | Abort, zero committed transfer/ledger/outbox, balances unchanged. |
| T03 | Missing destination | Abort whole transaction, A untouched. |
| T04 | Currency mismatch | Reject/abort, never silently cross-convert currencies. |
| T05 | `from == to` | Reject input prior to transaction. |
| T06 | `amount <= 0` | Reject input, zero DB writes. |
| T07 | Credit int64 overflow | Abort, zero partial transfer created. |
| T08 | Two competing transfers on same account | No overspend, bounded retries, invariants hold. |
| T09 | Same `transferId` same payload twice | Single business effect; second returns identical result. |
| T10 | Same `transferId` different payload | Idempotency conflict; zero new writes. |
| T11 | Crash after body, before commit | Zero committed partial transfer. |
| T12 | Explicit abort | Balances/ledger unchanged from that transaction. |
| T13 | `TransientTransactionError` in body | Helper retries eligible body; zero repeated external side effects. |
| T14 | Commit response lost after commit | Client sees unknown; DB has exactly one committed effect. |
| T15 | Commit request never reaches server | Never report success; retry/recover with same key. |
| T16 | Primary stepdown during body/commit | No double transfer; labels/timeline classified accurately. |
| T17 | Majority write concern timeout | Never conclude rollback from `wtimeout` alone. |
| T18 | HTTP client timeout after DB ACK | Retry with same key returns original result. |
| T19 | Outbox publisher crash after broker ACK | Consumer deduplicates event ID; zero duplicate external effect. |
| T20 | Recovery worker restarts repeatedly | Persistent status/idempotency preserved; eventually resolves. |

### 22.3. Exact Assertion Targets

In an isolated test, for example:

~~~text
before:
  accounts A=100000, B=20000
  no transfer TR-500

after one successful transfer of 50000:
  A=50000, B=70000
  transfers.TR-500 present, status COMPLETED
  ledger.TR-500:DEBIT  = -50000
  ledger.TR-500:CREDIT = +50000
  outbox.transfer:TR-500 exists
  no other records sharing business transfer ID
~~~

For a **failed/aborted** transaction, assert **all** of these remain untouched. For an **unknown** outcome, tests must verify the app **never assumes rollback** and classifies using the durable transfer record. Never assert only an exception class while ignoring DB state.

### 22.4. Baseline Capture and Cleanup

Every test should:

1. Use an isolated database/collection prefix or dedicated fixture.
2. Verify the replica set test URI is non-production.
3. Record expected balances and fixed/unique transfer IDs per test.
4. Inject faults deterministically and reproducibly.
5. Inspect committed state post-fault and assert invariants.
6. Close sessions/clients and clear fault rules.
7. Save sanitized test evidence, even on failure.

Never leave a failpoint or network rule enabled after a test finishes, causing flaky failures in subsequent tests. A good test harness runs cleanup **even when assertions fail**.

### 22.5. Bounding Concurrency When Inducing Write Conflicts

To test races, use **two or a few workers** touching the same account with predictable conflicts; never fire 100,000 transaction requests to brute-force DB errors. Tests must prove post-contention correctness, not depend on fixed millisecond timings.

### 22.6. Testing Retried Callbacks with External Side Effects

In a helper/service unit test, inject a transient error on attempt 1 so the callback re-runs, and count invocations on email/payment mocks. Expected:

~~~text
transaction body attempts = 2
MongoDB committed transfer count = 1
external payment charge in transaction body = 0
outbox logical event count = 1
~~~

This is the **expected outcome of the test scenario**, not a promise that the driver always retries exactly twice in every environment. External publishers/consumers may still receive events multiple times and must be idempotent.

### 22.7. Mocking Unknown Commit Does Not Replace Cluster Tests

In unit tests, mock the gateway as "server committed, client lost response" to verify HTTP responses and recovery. Pair that with replica set integration tests for transactions/invariants, and controlled proxy fault tests where infrastructure allows. Never conflate those three layers or claim "we tested network partitions" simply because a mock threw `MongoSocketException`.

### 22.8. Testing Long-Stuck Unverified States

Seed a synthetic `PENDING_VERIFICATION` past SLA and verify the recovery worker:

- Never marks `FAILED` without proof.
- Never retries with a new key.
- Applies bounded attempts and dead-letter/escalation.
- Records `lastSeen`/`lastError`/`nextRetryAt`.
- Reads the transfer record and resolves once the DB recovers.

### 22.9. Testing Access Control

A `tenant-a` user must never inspect status/ledger of `TR-tenant-b` simply by knowing `transferId`. Scope auth/idempotency keys by trusted principal/tenant. Test cross-tenant status GETs, replay POSTs, and conflict responses to ensure zero leaked amounts or account numbers.

### 22.10. Load-Testing Recovery

Run a bounded workload ramping traffic in stages in the lab, measuring HTTP p99, server election delay, pool checkout waits, aborted/committed transactions, retry amplification, and unresolved unknown age. Optimize headroom; never crank up retries or pools when DB CPU/IOPS are already saturated.

## 23. Common Reasoning Mistakes

| Mistake | Why It Is Dangerous | Better Practice |
|---|---|---|
| "Socket timeout means the transaction rolled back." | Commit may have succeeded while ACK was lost. | `UNKNOWN` + verify same ID. |
| "Every `MongoException` should retry the full body." | Non-transient business/validation errors exist. | Use error codes/labels + bounded policy. |
| "`UnknownTransactionCommitResult` => start a new transaction with a new ID." | Causes double debit/credit. | Retry same commit if possible; idempotent status verification. |
| "`TransientTransactionError` => retry only the credit." | Partial workflow breaks semantics. | Retry whole transaction via helper/spec. |
| "`withTransaction` callback runs only once." | Driver may retry the callback. | Keep external side effects out of callback. |
| "Send email before commit; abort recalls it." | MongoDB cannot roll back emails. | Transactional outbox. |
| "`writeConcern:majority` guarantees HTTP ACK reaches client." | Network can still drop the response. | Idempotency + status endpoint. |
| "`wtimeout` forces a rollback." | Write may already be applied/committed. | Classify/verify outcome. |
| "`retryWrites=true` makes the entire business flow exactly-once." | New HTTP requests use new sessions/IDs. | Stable business `transferId` + unique index. |
| "One missing read confirms no commit." | Stale reads, elections, or in-flight commits. | Verified consistency and recovery protocol. |
| "Idempotency key is optional." | HTTP retries create duplicate effects. | Require stable client-supplied/once-generated keys. |
| "Same key, different payload returns prior success." | Masks wrong requests or malicious retries. | Compare fingerprint; return `409 Conflict`. |
| "Read-before-insert prevents concurrent duplicates." | Two pods both observe missing. | Unique index + conflict handling. |
| "Unique transfer ID protects all ledger rows." | Child/outbox IDs can still collide/duplicate. | Deterministic child IDs + transaction. |
| "Money as Double keeps exact financial decimals." | Binary floating-point rounding drift. | Int64 minor units / Decimal128 contract. |
| "Two separate writes form a transaction because they share one HTTP request." | Without a transaction, atomicity is per-operation/document. | `ClientSession` + transaction. |
| "A `bulkWrite` is automatically atomic across all docs." | Bulk ops are not multi-doc transactions. | Multi-document transaction when needed. |
| "Transactions prevent overspending in every case." | Predicates can be buggy under concurrency. | Conditional debit, validation, unique IDs. |
| "Snapshot reads replace unique indexes." | Concurrent identity creation races. | Unique index on transfer ID. |
| "No need to check `matchedCount`." | Insufficient-funds no-op debit still lets credit commit. | Validate `matchedCount`; abort on failure. |
| "Transactions allow direct Kafka/payment calls." | External systems do not roll back with DB. | Outbox/saga/idempotency. |
| "Consecutive REST calls returning OK mean one commit." | Logs/caches can drop or replay. | Durable transfer record + ledger proof. |
| "Ledger `net=0` proves every transfer is valid." | Wrong legs can cancel to zero. | Per-leg identity/type/value checks. |
| "Primary stepdown always emits unknown commit label." | Exact timing determines observed errors. | Capture actual phase/errors/DB state. |
| "Fault-inject production to prove resilience." | Causes real outage and data risk. | Authorized replica-set lab/test proxy. |
| "Increasing pool size fixes missing primary." | Pools cannot elect a primary. | SDAM/network/election monitoring. |
| "Restart all pods during DB election." | Triggers a reconnect storm. | Separate liveness and readiness. |
| "Shorter timeout means write never reached server." | Client deadlines do not roll back server work. | Unknown-outcome protocol. |
| "Infinite retries guarantee success." | Retry amplification causes overload/double effects. | Attempt caps/backoff/jitter/deadlines. |
| "Keep transactions open for minutes for external APIs." | Lifetime/resource conflicts, repeated side effects. | Short DB transaction + workflow/saga. |
| "Rollback just means transferring money back." | Unknown outcome may never have committed. | Verify first; compensate via new audited op. |
| "In-memory PENDING status endpoint is enough." | Process crashes wipe state. | Durable request status/recovery protocol. |
| "A mock exception test proves failover works." | Mocks don't model server/network behavior. | Real replica-set integration/fault tests. |
| "A `transfers` record means no ledger check needed." | Legacy/corrupt records may exist. | Independent business invariants/reconciliation. |
| "Monitoring logs are sole proof of commit." | Logs can drop on crashes. | Durable DB state and write concern proof. |

### 23.1. Reviewing a Transaction Pull Request

Questions to answer before merging:

1. Does every business request have a **stable `transferId`/idempotency key**?
2. Are unique indexes and payload fingerprints enforced/verified?
3. Are debit/credit `matchedCount`, currency, overflow, and ACLs checked?
4. Do all writes requiring atomicity share the **same `ClientSession`**?
5. Is the callback free of external side effects, `subscribe()`, or non-idempotent logic?
6. Does error handling distinguish transient body retries from unknown commits?
7. Are deadlines, backoff, and attempt caps set for retries and recovery?
8. Are transfer/ledger/outbox verified after timeouts, crashes, and failovers?
9. Do tests run against a replica set with safe fault injection and DB state assertions?
10. Do monitoring and alerts distinguish "client failed" from "business committed"?

## 24. Practice Exercises with Answers

Exercises use **synthetic lab data**. For fault injection and failover, run only on an authorized test replica set. The goal is interpreting **DB outcomes and client knowledge state**, never treating an exception string as absolute truth about commit status.

### Exercise 1 — One Document vs. Two Documents

**Prompt:** Is an `updateOne` decrementing A's balance with predicate `>= q` atomic? Do two separate `updateOne` calls on A and B share the same atomicity?

**Answer:** A single update on **one document** is atomic. Two separate updates on two documents are not atomic together; a mid-way failure breaks the sum invariant. Use a multi-document transaction or another workflow with invariants and reconciliation.

### Exercise 2 — Standalone MongoDB

**Prompt:** A developer runs standalone MongoDB and calls `startTransaction`. Does it support multi-document transactions?

**Answer:** No. A replica set or sharded deployment supporting transactions is required. A single-node **replica set** works for commit/abort labs, though it cannot practice multi-node HA elections.

### Exercise 3 — Must the Session Be Passed?

**Prompt:** A `ClientSession` and transaction are started, yet `accounts.updateOne(...)` omits `session` while `ledger.insertOne(session, ...)` passes it. Are both writes definitely in the same transaction?

**Answer:** No. Java Sync Driver operations must call the **`session` overload** to join the transaction. Inspect every write call individually rather than assuming session presence in the method suffices.

### Exercise 4 — Commit ACK

**Prompt:** `commitTransaction` is ACKed under majority write concern. May the app return success for the transfer ID?

**Answer:** Yes, per contract and verified business state (barring other app errors), logging the transfer ID for audit. Majority ACK proves DB commit under semantics; still handle lost HTTP responses gracefully.

### Exercise 5 — Timeout at Commit

**Prompt:** The client sent `commitTransaction`, and the socket closed before a response arrived. Did the transaction definitely roll back?

**Answer:** No. The outcome is **unknown**; the server may have committed. Retry **commit of the same transaction** if session/helper permits, or verify via the stable transfer ID.

### Exercise 6 — TransientTransactionError

**Prompt:** Inside the body, the second update hits a write conflict labeled `TransientTransactionError`. Retry only the second update or the whole transaction body?

**Answer:** Under the transaction retry pattern, abort and **retry the entire transaction body** in a new transaction when eligible and within budget, using the driver helper. Never continue an aborted/errored transaction as if nothing happened.

### Exercise 7 — UnknownTransactionCommitResult

**Prompt:** Commit throws with label `UnknownTransactionCommitResult`. Should the app re-invoke the callback with a new transfer ID?

**Answer:** No. Retry `commitTransaction` on the same session/transaction if supported, then verify durable state. Running a fresh callback with a new ID risks double-debiting if the first commit succeeded.

### Exercise 8 — wtimeout

**Prompt:** `wtimeout=5000` on a majority commit expires. Does that prove the write was never applied on the primary?

**Answer:** No. Timing out waiting for majority acknowledgment does not mean the server rolled back. Classify the outcome and never retry the business effect under a new key.

### Exercise 9 — Insufficient Funds

**Prompt:** A has `30,000`, request `q=50,000`, and debit predicate `balance >= q` returns `matchedCount=0`. Should we proceed to credit B?

**Answer:** No. Abort the transaction and return a business conflict / insufficient funds error—do not credit B or record a `COMPLETED` transfer. Never retry indefinitely on a business precondition failure.

### Exercise 10 — Missing Destination

**Prompt:** Debit on A ran inside the transaction, then credit on B matched nothing because B doesn't exist. Does A lose money?

**Answer:** If the transaction **aborts properly** without committing, the debit never becomes committed. Throw/abort rather than catching and committing. Lab verification must confirm balances and ledger remain unchanged.

### Exercise 11 — Two Competing Transfers

**Prompt:** A has `100,000`; TR1 transfers `80,000` and TR2 transfers `80,000` concurrently with no overdrafts. Can both succeed?

**Answer:** Both must not succeed if guards and transactions are properly configured. One may hit a write conflict and retry, then observe insufficient funds and fail cleanly. What matters is **zero negative balances and a balanced ledger**.

### Exercise 12 — Same ID, Same Payload

**Prompt:** A client resends `TR-100` with identical from/to/amount/currency after an HTTP 504. How should it be handled?

**Answer:** Read the durable transfer record and compare fingerprint and status. If committed, return the original result **without debiting again**. If unknown/pending, follow recovery using the same ID.

### Exercise 13 — Same ID, Different Payload

**Prompt:** `TR-100` previously transferred `50,000`; the client retries `TR-100` with `70,000`. Can it be treated as the same request?

**Answer:** No. Return an **idempotency conflict** per API policy—never execute a new transfer or overwrite the old record. Keys must be scoped to tenant and authenticated caller.

### Exercise 14 — Read-Before-Write Race

**Prompt:** Two pods both read that `transfers.TR-100` does not exist yet. Can both inserts commit?

**Answer:** Unique `_id` prevents both from committing two transfer records with the same ID; one hits duplicate key or write conflict. Read-before-write is an optimization only, not a synchronization lock. The failing caller must verify the committed record and payload.

### Exercise 15 — Callback Side Effects

**Prompt:** A `withTransaction` body calls an email API, then a write conflict triggers a callback retry. How many emails might be sent?

**Answer:** Potentially more than one, even though only one transaction commits. Never send emails inside the callback; write an outbox event in the transaction and dispatch externally with an idempotent consumer.

### Exercise 16 — Abort ACK

**Prompt:** After uncommitted updates to A/B, `abortTransaction()` succeeds. Do we need a reverse transfer to refund?

**Answer:** No. Those uncommitted writes were aborted and never committed. A reverse transfer would be a bogus new movement. Compensate only after confirming a committed movement needs reversal.

### Exercise 17 — Process Crash After Commit ACK

**Prompt:** The DB committed, and the app crashed before sending the HTTP response. The client retries on another pod. Why is durable idempotency storage required?

**Answer:** The new pod lacks the crashed pod's in-memory state. Durable transfer IDs, unique indexes, and status lookups return the original committed result without double-transferring.

### Exercise 18 — Server Selection Timeout

**Prompt:** The replica set temporarily has no primary, and the driver cannot find an eligible server. Does increasing `maxPoolSize` fix this?

**Answer:** No. A larger pool cannot elect a primary. Check SDAM/election/network/read preferences, deadlines, and backoff. If an earlier attempt already sent commit, follow unknown-outcome protocols rather than assuming every selection timeout means "nothing was written."

### Exercise 19 — Stepdown and Error Labels

**Prompt:** Running `rs.stepDown(15)` in the lab while a workload runs—will every transaction throw `UnknownTransactionCommitResult`?

**Answer:** No. Exact timing dictates the outcome: body transient error, selection timeout, unknown commit, or clean success prior to stepdown. Use command-phase traces and durable DB state to classify.

### Exercise 20 — retryWrites=true

**Prompt:** With `retryWrites=true` enabled, do we still need a stable transfer ID on HTTP POST?

**Answer:** Yes. Driver retryable writes cover only eligible single-attempt protocol writes; clients/gateways create brand-new HTTP requests after timeouts. Business keys and unique constraints are required to block duplicate business effects.

### Exercise 21 — Int64 Overflow on Recipient

**Prompt:** B's balance is near `Long.MAX_VALUE`, so adding `q=50,000` could overflow. Does a transaction enforce this rule automatically?

**Answer:** No. Validate input and guard the update with `balanceMinor <= Long.MAX_VALUE - q`, checking `matchedCount`. On no-match, abort so the debit does not commit. For multi-currency/high-precision needs, choose an appropriate numeric model.

### Exercise 22 — Currency Mismatch

**Prompt:** A uses VND and B uses USD; a request transfers `50,000` and code simply increments/decrements both balances. What is wrong?

**Answer:** The transaction may be atomic yet **financially broken**; never add two distinct currencies as equal units. Enforce matching currencies or build an explicit FX workflow with rates, rounding, and per-currency ledgers.

### Exercise 23 — Session Omitted on One Write

**Prompt:** `transfers.insertOne(session,...)` and `ledger.insertMany(session,...)` pass `session`, while `accounts.updateOne(...)` omits it. Can partial state commit even if the method is named `transferAtomic`?

**Answer:** Yes. The account update runs outside the transaction; if the transaction aborts, accounts still mutate independently. Every write requiring atomicity must use the same `ClientSession` in the Java Sync Driver.

### Exercise 24 — Majority Read Sees Missing

**Prompt:** Right after commit response loss, a majority read finds `transfers.TR-100` missing. Does that prove rollback?

**Answer:** Not conclusively. Confirm cluster stability, cut/commit state, and recovery protocol; the commit may still be in flight or read timing may differ. Keep `UNKNOWN`, retry commit on the same session if possible, or execute idempotent verification/re-execution with the same key and unique constraint.

### Exercise 25 — Ledger Sums to Zero

**Prompt:** The ledger has two entries `+50,000` and `−50,000`, `net=0`. Is that enough to confirm `TR-100` is right?

**Answer:** Not yet. Verify leg IDs, account IDs, from/to, currency, BSON types, status, and record identity; two legs on the wrong accounts still sum to zero.

### Exercise 26 — Outbox Publisher Crash

**Prompt:** A worker publishes an event to the broker and crashes before setting `published=true`. Can it send a duplicate on restart?

**Answer:** Yes. Outboxes typically provide **at-least-once delivery**. Consumers must be idempotent using stable event IDs/provider keys so duplicate events never trigger duplicate transfers.

### Exercise 27 — Email Inside Callback

**Prompt:** An email is sent at the end of a transaction callback before commit is called. If commit fails, is the email recalled?

**Answer:** No. Emails are external side effects. Write an outbox record inside the transaction and let a worker send after commit with deduplication and separate retries.

### Exercise 28 — Missing Outbox While Account/Ledger Committed

**Prompt:** Verification finds a completed transfer and two valid ledger legs, but the outbox event is missing. Should we re-run the transfer to create the event?

**Answer:** No. The money likely moved already; re-running causes a double transfer. Investigate code/legacy/migrations, emit an approved idempotent repair event, audit, and re-verify.

### Exercise 29 — Mocking Network Errors

**Prompt:** A unit test mocks throwing `MongoSocketException` and the service returns `UNKNOWN`. Does that prove real MongoDB committed and lost the response?

**Answer:** No. It proves **application behavior** under injected errors. Testing server/driver behavior requires replica-set integration/fault-proxy tests and durable state verification.

### Exercise 30 — `failCommand` closeConnection

**Prompt:** A failpoint closes the connection as soon as `commitTransaction` arrives. Does this definitely simulate "server committed, then ACK was lost"?

**Answer:** No. The connection may close **before the command executes**. Simulating lost responses post-commit requires a fault harness proving the commit ran, verified against server/driver timelines.

### Exercise 31 — Fault Injection in Production

**Prompt:** A teammate suggests running `rs.stepDown` in production to test retries. Does that fit this lesson's scope?

**Answer:** No. This lesson authorizes lab/staging only. Production chaos testing requires a dedicated approved program with blast-radius controls, rollback plans, and incident readiness—never for a learning exercise.

### Exercise 32 — CommandListener as Business Proof?

**Prompt:** Java logs say `commitTransaction started`. Does that mean the transaction committed?

**Answer:** No. `started` only means the driver began sending the command; network drops or server errors can follow. Require a commit ACK or durable state verification.

### Exercise 33 — Bug When Callback Re-Runs

**Prompt:** The driver helper retries a transaction body after a transient error, and the body generates a new UUID transfer ID on every run. What is the risk?

**Answer:** Business identity shifts between attempts, breaking deduplication and unknown-outcome verification. Generate or accept **`transferId` once at the request boundary** and keep it immutable across retries.

### Exercise 34 — Retrying Past HTTP Deadline

**Prompt:** API deadline is 800 ms; after 750 ms, the driver hits a transient error. Should the app retry the body for 5 more seconds and return success?

**Answer:** Not if it breaches end-to-end SLOs or contracts. Respect deadlines/attempt caps and return `UNKNOWN` or an appropriate temporary error with recovery status. If commit may already have been sent, never assume zero side effects.

### Exercise 35 — Compensation While Outcome Is Unknown

**Prompt:** The client doesn't know if `TR-100` committed, so it immediately submits a reverse transfer B→A. Is this safe?

**Answer:** No. If `TR-100` never committed, reversing sends money the wrong way. Verify the outcome first; compensation is a new audited/approved operation used only after confirming the original transfer committed and must be reversed.

### Exercise 36 — Transaction with Only One Transfer Record

**Prompt:** `transfers` has one `TR-100`, while `ledger` has four legs with different IDs. Did unique `transfers._id` guarantee exactly once?

**Answer:** No. Deterministic unique IDs on child legs/outbox, full transaction scope, and per-transfer cardinality/invariant checks are all needed; a single record alone does not prove all side effects are accurate.

### Exercise 37 — HTTP Status for Unknown

**Prompt:** Commit is unknown and the backend has no durable pending state. Should it return `200 Transfer Completed`?

**Answer:** No. Return an honest `UNKNOWN`/temporary error with operation ID/status query guidance per protocol. Use `202 Accepted` only when durably accepted with a continuation and status lookup mechanism.

### Exercise 38 — Cross-Tenant Idempotency

**Prompt:** `tenant-b` queries status using `tenant-a`'s `transferId` and receives amounts and account IDs. What is violated?

**Answer:** Authorization and data isolation. Scope idempotency keys and status reads by trusted principal/tenant; never return records from guessed IDs, even when transaction correctness is flawless.

### Exercise 39 — Counting Errors Across Two Layers

**Prompt:** The driver retried a transaction twice and the gateway retried the HTTP request once. API logs show "one request," so a DBA assumes only one DB attempt ran. Why is that wrong?

**Answer:** **Business request, HTTP attempt, transaction body attempt, and commit attempt are four distinct units.** Monitor correlation IDs and per-layer retries; excessive attempts cause retry amplification during failovers.

### Exercise 40 — Designing a Fault-Tolerant Transfer Workflow

**Prompt:** Design a transfer API on a 3-node MongoDB replica set resilient to primary elections, socket response drops, gateway retries, and outbox worker crashes. Business requires zero double debits, full ledger auditing, and queryable status. Outline the architecture, code patterns, and acceptance criteria.

**Suggested Answer:**

1. Use a replica set with proper URI/quorum, compatible MongoDB Java Sync Driver version, and one application-scoped `MongoClient`.
2. Accept/assign a stable `transferId`/idempotency key at the request boundary; validate auth/tenant, currency, positive amount, limits, and `from != to`.
3. Enforce a unique transfer ID (tenant-scoped) and an immutable request fingerprint.
4. Use `ClientSession.withTransaction` with `readConcern: snapshot`, majority commit write concern, and primary read preference.
5. Inside the callback, insert the transfer record, run conditional debit and credit overflow guards, insert 2 ledger entries, and insert one outbox event.
6. Check `matchedCount` and throw business exceptions on precondition failure; never swallow MongoDB errors or trigger external side effects inside the callback.
7. Let the helper retry transient body/commit errors per labels; enforce deadlines, attempt caps, and backoff with jitter for application-level retries.
8. On `UnknownTransactionCommitResult`, never declare rollback; retry the same commit if the session remains valid and supported by the helper, or verify the durable transfer record/ledger/outbox with the exact same ID.
9. On HTTP retries with matching payload, return the original committed result; on same ID with mismatched payload, return conflict; concurrent callers are serialized/blocked by the unique index.
10. Dispatch outbox events after commit with leasing, retries, idempotent consumers, and processed-event tracking so duplicate deliveries never trigger a second business effect.
11. Maintain a `PENDING_VERIFICATION` state machine (if using a durable request ledger), recovery worker, escalation/manual review, and ACL-protected status API.
12. Test on a replica set: success, abort, insufficient funds, missing destination, two concurrent transfers, same-ID retries, stepdown, lost commit responses, process crashes, and outbox replays.
13. Monitor CommandListener/SDAM/CMAP events, HTTP p99, unknown commit counts/ages, transaction retries, ledger imbalances, and alerts.
14. Never assert only HTTP 200: prove **exactly one committed business effect**, accurate balances, 2 exact ledger legs, 1 logical outbox event, and zero cross-tenant leakage.
15. Run fault injection solely on authorized lab/staging environments with cleanup and recovery after tests finish.

A sound design is one that **prevents executing the business action twice regardless of whether the client received the commit ACK**. When evidence is lacking, it holds a verifiable pending state rather than turning a network error into an unfounded data conclusion.

## 25. Official Documentation and Version Reference Guide

The following resources help verify syntax/session semantics, retry behavior, error labels, and deployment requirements. Some `current` paths redirect to newer releases, so match the exact **MongoDB Server version, FCV, Java Driver version, and replica set/sharding topology** in use. Code snippets in this lesson are written for lab learning and are not claimed to have been executed against the reader's cluster.

### 25.1. Transactions and Snapshot/Majority

1. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document transaction properties, sessions, atomicity, and deployment support.
2. [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — transaction lifetimes, operation restrictions, locking, cache/resources, and deployment behavior.
3. [MongoDB Manual — Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot read semantics and prerequisites.
4. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `majority`, `wtimeout`, acknowledgments, and durability.
5. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — eligible retryable writes and limitations; distinct from business idempotency.
6. [MongoDB Manual — Replication](https://www.mongodb.com/docs/manual/replication/) — elections, majority, rollbacks, oplog, and replica-set semantics.

### 25.2. Java Driver Transactions and Error Handling

7. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `TransactionOptions`, `withTransaction`, callbacks, and session lifecycles.
8. [MongoDB Java Sync Driver — Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/) — pool lifecycle, checkout limits, and connection churn.
9. [MongoDB Java Sync Driver — Cluster Settings](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/cluster-settings/) — server selection, replica set discovery, latency/topology.
10. [MongoDB Java Sync Driver — Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/) — command/CMAP/SDAM listeners and driver observability.
11. [MongoDB Driver Specification — Transactions](https://github.com/mongodb/specifications/blob/master/source/transactions/transactions.md) — normative transaction helper retry patterns, errors, commit retries, and server/driver interoperability.
12. [MongoDB Driver Specification — Retryable Writes](https://github.com/mongodb/specifications/blob/master/source/retryable-writes/retryable-writes.md) — wire protocol and retry semantics.

### 25.3. Failover Scenarios and Testing

13. [MongoDB Manual — `rs.stepDown()`](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/) — primary stepdown, election conditions, and availability impact. **Use only in the lab within this lesson's scope.**
14. [MongoDB Manual — `replSetStepDown`](https://www.mongodb.com/docs/manual/reference/command/replSetStepDown/) — command-level stepdown behavior and prerequisites.
15. [MongoDB Manual — `serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — version-dependent connection/transaction/server metrics.
16. [MongoDB Manual — Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — `replicaSet`, `retryWrites`, read/write concern, and timeout URI options.
17. [MongoDB Manual — `configureFailPoint`](https://www.mongodb.com/docs/manual/reference/command/configureFailPoint/) — failpoint configuration on supported test binaries/deployments; never assume permissions or availability in production.

### 25.4. Spring Data and Beyond MongoDB

18. [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `MongoTransactionManager`, reactive transaction manager, session binding, and caveats.
19. [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — enforcing BSON shapes; aids correctness without replacing multi-collection invariants.
20. [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — unique IDs, missing/null semantics, sharding restrictions, and duplicate protection.
21. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — building outbox/consumer workflows and resume requirements; does not automatically guarantee exactly-once external effects.

### 25.5. What to Check When Upgrading Driver or Server Versions

1. Are `withTransaction` API signatures and driver automatic retries still valid for your release line?
2. Which specific exception classes/codes carry `TransientTransactionError` and `UnknownTransactionCommitResult` labels?
3. Did client-side operation timeout or commit retry deadline behavior change?
4. Do majority write concern/journaling and transaction lifetime defaults match cluster settings?
5. Are transactions supported on your standalone/single-node replica set/sharded deployment?
6. Do monitoring events expose command names/durations and redact BSON by default?
7. Did privileges, options, or server-version rules change for `rs.stepDown`/failpoints?
8. Does the app stack another retry layer outside the driver (Spring Retry, HTTP gateway, message consumer)?

## 26. Lab Summary Checklist

### 26.1. Safe Operations Checklist

| Question | Pass Criterion |
|---|---|
| Sure you're connected to the **lab** replica set? | URI/cluster verified, zero real users. |
| Know pre-exercise balances? | Fixture/baseline documented; no uncontrolled ID reuse. |
| Transaction updates multiple documents? | Proper session/transaction with all writes participating. |
| Business guards checked? | `matchedCount`, currency, `amount > 0`, overflow, `from != to`. |
| Idempotency key present? | Stable per logical request, unique, and fingerprint-checked. |
| Errors classified properly? | Transient body vs. unknown commit vs. business conflict. |
| Retries bounded? | Deadlines/caps/jitter and aware of automatic driver retries. |
| Fault injection authorized? | Lab replica set only, with post-test cleanup/recovery. |
| Durable state verified? | Transfer record, exact ledger legs, balances, and outbox. |
| Unknown outcomes handled? | Unknown state / status lookup / recovery, zero double transfers. |
| External side effects decoupled? | Outbox / consumer idempotency. |
| Concurrency and crashes tested? | Same-ID and distinct-ID races; post-commit response loss. |

### 26.2. Four Concepts Never to Conflate in Incident Reviews

~~~text
1. Transaction ATTEMPT
     = one execution attempt inside driver/client.

2. Transaction COMMIT
     = durable database outcome under the chosen write concern.

3. Client OBSERVATION
     = what the application received (ACK/error/timeout).

4. Business EFFECT
     = whether exactly one intended transfer and ledger event exists.
~~~

One HTTP request can spawn multiple driver attempts, a commit may go unobserved by the client, and a business effect may already exist even though HTTP returned an error. **Never** treat these four concepts as synonymous.

### 26.3. Practice Report Template

~~~text
Lab run ID:               TXN-LAB-20261114-01
Cluster:                  rsLab / 3-node disposable replica set
Server version / FCV:     <verified>
Java driver version:      <verified>
Fault scenario:           primary stepdown / commit response loss
Business transfer ID:     TR-LAB-007
Request fingerprint:      <computed>
Observed error class:     <actual>
Observed error labels:    <actual>
Transaction body attempts:<measured>
Commit attempts:          <measured>
Majority commit ACK:      yes/no/unknown
Transfer record:          present/missing/unverified
Ledger:                   balanced/invalid/unverified
Outbox:                   one/none/multiple/unverified
Business outcome:         COMMITTED / NOT_COMMITTED / UNKNOWN
Recovery action:          <what was done, same ID>
Data loss/double effect:  <evidence>
Fault cleanup:            confirmed
Reviewer:                 <lab owner>
~~~

Replace placeholders with results from an **actual lab run** when practicing. Never fill in "PASS" merely because a command threw no exception, and never write `NOT_COMMITTED` when the only evidence is a timeout or lost response.

## 27. Conclusion

MongoDB transactions guarantee that multiple writes sharing a session/transaction **commit or abort atomically as a unit**, yet they **do not guarantee the client always receives the commit result**. Network drops, elections, gateway timeouts, and process crashes can occur right at the response boundary, leaving the client knowing only that the **outcome is unknown**.

When handling such cases, uphold three rules:

1. **Retry the right piece:** `TransientTransactionError` may call for retrying the entire transaction body via the driver helper and deadline; `UnknownTransactionCommitResult` calls for retrying **commit of the same transaction** or verifying durable state—never starting a new transfer with a different ID.
2. **Idempotency at the business layer:** Use a stable transfer ID, unique constraint, payload fingerprint, conditional debit/credit guards, and ledger/outbox writes committed in the same transaction. HTTP/gateway retries must never produce a second effect.
3. **Reconcile instead of guessing:** When an ACK is lost, inspect the transfer record and ledger by the same ID under appropriate consistency policies; when evidence is inconclusive, hold `UNKNOWN_REQUIRES_VERIFICATION` and follow recovery protocols rather than equating a timeout with rollback.

Practice must cleanly separate **transaction correctness**, **network visibility**, **external side effects**, and **recoverability**. A resilient system does not merely succeed when everything is healthy: when the primary switches, sockets close, or callers time out, it preserves accurate data and reports honestly what is known and what remains unknown.

**The single most important lesson: a disconnection error is not proof a transaction failed; correctness comes from properly designed transactions, stable idempotency keys, and verifying committed outcomes before acting again.**
