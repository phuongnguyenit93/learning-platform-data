# Write Concern Timeouts and Commits with Unknown Outcomes in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Troubleshooting  
> **Lesson:** Write Concern Timeouts and Commits with Unknown Outcomes

## 1. One Timeout Can Cause Two Severe Bugs

Imagine a payment service sending an order update to MongoDB. The application waits a few seconds and receives an exception:

```text
Client                  MongoDB primary             Secondaries
   |                           |                         |
   | update order status       |                         |
   |-------------------------->|                         |
   |                           | apply update            |
   |                           |---- replicate ---------->|
   |                           |                         |
   |         network timeout   |                         |
   |<-------------------------X|                         |
   |                           | replication continues   |
```

There are two wrong ways to handle this:

- **Mistake 1 — Treating the timeout as a rollback:** resending an `$inc` command without a deduplication key, causing balances or payment counts to increment twice.
- **Mistake 2 — Treating the timeout as success:** returning success and removing the job from the queue, when the transaction may not have committed or the write may be rolled back after failover.

**A timeout only states that a wait deadline expired; it does not prove whether data was written or not.** Pinpointing where the timeout occurred determines what can actually be concluded.

### 1.1. Running Scenario

`OrderService` receives a command:

```json
{
  "requestId": "pay-confirm-20261114-A100",
  "tenantId": "tenant-demo",
  "orderId": "A100",
  "newStatus": "PAID"
}
```

A single request can trigger:

1. Updating `orders.status`.
2. Incrementing aggregate metrics.
3. Writing an event/outbox entry.
4. Confirming the outcome to the HTTP client.

If the client loses connectivity during `updateOne()` or `commitTransaction()`, the system must know **what it is allowed to do next** without corrupting business state.

### 1.2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish network, driver, server, write concern, and transaction commit timeouts.
2. Understand `w:1`, `w:"majority"`, `j:true`, and `wtimeout`, without equating acknowledged with applied or durable.
3. Explain why a `writeConcernError` can accompany a write already applied on the primary.
4. Distinguish `TransientTransactionError` from `UnknownTransactionCommitResult`.
5. Understand retryable writes and the limits of `retryWrites=true`.
6. Design idempotent commands using `requestId`, unique keys, CAS, and an operation ledger.
7. Reconcile state when the outcome is **unknown**, even when a document is not yet visible on a secondary.
8. Retry the commit **of the same transaction** rather than accidentally re-running side effects.
9. Handle partial success in `bulkWrite` or `insertMany`.
10. Design logs/metrics, runbooks, escalation criteria, and safe labs without disrupting replica sets.
11. Integrate the Java Sync Driver with exception labels, timeouts, and transaction callbacks.
12. Explain the limits of any mechanism when effects already lie outside MongoDB, such as payments or emails.

## 2. Five States That Must Be Distinguished

An operation sent from the application can fall into one of several states:

| State | Meaning | Can it be inferred from a timeout? |
| --- | --- | --- |
| `NOT_SENT` | Client never sent the command | Only if the application has solid proof |
| `NOT_APPLIED` | Server definitely did not apply it | Requires specific errors/evidence, not a generic timeout |
| `APPLIED_ON_PRIMARY` | Primary modified data | May not yet satisfy majority/journal per contract |
| `COMMITTED_DURABLY` | Confirmed per durability contract | Requires acknowledgment or sufficiently strong read/reconciliation |
| `UNKNOWN` | Client lacks proof of final outcome | **Reasonable default state on an ambiguous timeout** |

Never turn `UNKNOWN` into `FAILED` with a single line:

```java
catch (MongoException e) {
    return PaymentStatus.FAILED;
}
```

Many exceptions indicate **cannot confirm**, not **had no effect**.

### 2.1. Two Separate Dimensions: Applied vs. Acknowledged

```text
                                  ACK?
                          No                  Yes
Applied?     No       Not applied         N/A (normal write protocol)
             Yes      Applied, ACK lost   Applied, acknowledged
```

In the "Applied, ACK lost" cell, the application might retry the same request and cause duplicate side effects without idempotency. For transactions, "committed but ACK lost" is the classic case of `UnknownTransactionCommitResult`.

### 2.2. Adding the Durability/Failover Dimension

`APPLIED_ON_PRIMARY` does not automatically equal `MAJORITY_COMMITTED`. A `w:1` write can appear on the primary and later be rolled back if the primary fails over before sufficient replication occurs.

With `wtimeout` on `w:"majority"`, the primary having applied the write **does not equal** majority acknowledgment; the write may keep replicating and eventually reach majority, or during a failover it may be rolled back.

An immediate GET right after a timeout is **insufficient** to confirm the same durability level if it uses read concern `local` or reads from a lagging secondary.

## 3. Types of Timeouts: Do Not Lump Them Under One Label

| Type | Where the deadline expires | What can be inferred | Trap |
| --- | --- | --- | --- |
| Connection establishment timeout | Connection did not complete | Command may not have been sent, yet verify context | Thinking all network errors happen before sending |
| Server selection timeout | Driver found no eligible server | Driver likely did not send the current attempt | Earlier attempts may have run if retried |
| Socket/read timeout | Waiting for response on connection | Server may already have applied/committed | Resending non-idempotently |
| Client-side operation deadline `timeoutMS` | Overall operation timed out | One or more attempts may have been sent | Does not mean the transaction aborted |
| Write concern timeout `wtimeout` | Waiting for `w` after primary applied | Earlier data modifications **are not auto-undone** | Recording the business action twice |
| Server-side operation time limit `maxTimeMS` | Server aborts execution exceeding limit on supported ops | Depends on op/phase; do not assume all side effects roll back | Treating `maxTimeMS` like a write-concern timeout |
| Transaction commit uncertainty | `commitTransaction` response uncertain | Transaction may or may not have committed | Re-running transaction body instead of retrying commit |
| HTTP proxy/gateway timeout | API client timed out waiting | API handler may still be writing | HTTP client retries as a brand-new request |

### 3.1. At Which Stage Does Write Concern Timeout Apply?

For write concern `w > 1`, `wtimeout` bounds how long to wait for enough members to acknowledge **after the operation is applied on the primary**.

Example:

```javascript
db.orders.insertOne(
  {
    _id: "order-timeout-example",
    status: "CREATED"
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 2500
    }
  }
);
```

If majority is not reached within 2.5 seconds, MongoDB returns a **write concern error**, yet **does not automatically undo the changes already applied**.

Per documentation, `wtimeout` does not apply when `w <= 1`. Do not explain `wtimeout:2500` as "the primary has at most 2.5 seconds to run all logic." To bound an entire operation, check supported `timeoutMS`/max-time APIs and driver semantics, without treating them as safe rollbacks.

### 3.2. Write Concern Errors Differ from Write Errors

In some command responses:

```javascript
{
  ok: 1,
  n: 1,
  writeConcernError: {
    code: 64,
    codeName: "WriteConcernFailed",
    errmsg: "waiting for replication timed out",
    errInfo: {
      wtimeout: true
    }
  }
}
```

This is an **illustrative response structure**; codes/fields may vary by version. It indicates the command executed the write on the primary yet failed to meet the write concern. Unlike errors such as duplicate key or validation failure, which reject a write before it completes.

Conversely, the absence of `writeConcernError` **does not** prove a write is majority acknowledged if the client only requested `w:1`.

### 3.3. Why Can Omitting `wtimeout` Be Dangerous?

If the requested `w` cannot be satisfied and no timeout is set, requests can hang indefinitely in the write concern phase. Yet setting an arbitrarily tiny timeout increases **ambiguous outcomes** requiring reconciliation.

Choose based on:

- Application SLOs.
- Normal RTT and replication lag.
- Gateway and queue deadlines.
- Replica set availability.
- Business durability requirements.
- Ability to reconcile safely on timeout.

Never resolve an incident by downgrading `w:"majority"` to `w:0` on a critical payment path.

## 4. Write Concern: What Does "Written" Mean?

### 4.1. `w:0`

The client requests no server acknowledgment for the write result. This is an **unacknowledged write**, unsuitable when the application needs confirmation that data was saved before proceeding; the driver lacks full results to confirm.

Standard retryable writes **do not apply** to write concern `w:0`.

### 4.2. `w:1`

The primary acknowledges per write concern semantics, typically without waiting for a majority of replicas. Latency is lower in many cases, yet an acknowledged write can still be rolled back on failover if not yet replicated.

Never call every `w:1` acknowledgment "durable across failover."

### 4.3. `w:"majority"`

The server waits to satisfy the majority requirement per topology. Depending on version/config, MongoDB ties majority ack to journal durability, including `writeConcernMajorityJournalDefault`.

**Version difference:** starting in MongoDB 8.0, majority acknowledgment is based on a majority of data-bearing voting members having durably written the oplog entry; secondaries may apply the changes to collections asynchronously afterward. Thus, an immediate read from a secondary does not necessarily see the data in the collection right after a majority acknowledgment. When read-your-writes across members is required, use causal consistency or an appropriate read concern.

### 4.4. `j:true`

`j:true` requests journal sync per write concern semantics. It does not replace `w:"majority"` for replication/failover guarantees.

Example:

```javascript
{
  w: "majority",
  j: true,
  wtimeout: 5000
}
```

This is a common strong durability request, yet it can still time out if the cluster is unhealthy. That timeout **does not** cause MongoDB to delete the write already applied on the primary.

### 4.5. Never Guess Defaults

The default write concern depends on server version, implicit default write concern, replica sets with arbiters, cluster/Atlas policies, and client/session settings.

Before investigating, record the **effective write concern** rather than inferring it from Java code omitting `.withWriteConcern(...)`. Some deployments default to majority; others follow different rules.

## 5. Three Timelines to Understand Unknown States

### 5.1. Scenario A — Write Applied on Primary, Majority Unacknowledged

```text
T0 Client -> updateOne (w:majority, wtimeout:2000)
T1 Primary applies update
T2 Replication blocked / secondaries slow
T3 2000 ms elapsed -> writeConcernError
T4 Client reports ambiguous result
T5 Replication catches up, write becomes majority committed
```

If the client retries with a new `$inc` command at T4, it increments twice. If the client reports `FAILED` to the business layer, a transaction that actually happened may be treated as never having occurred.

### 5.2. Scenario B — ACK Lost on the Network

```text
T0 Client sends insertOne(_id = order-A100)
T1 Server inserts document
T2 Server sends success response
T3 Connection breaks before response reaches client
T4 Driver/application sees network error
```

On the server, the operation succeeded. If the client sends **a new insert with a new `ObjectId`**, it creates a duplicate business record. Keeping the same deterministic `_id` or unique `requestId` lets the retry detect that the result already exists.

### 5.3. Scenario C — Commit Succeeded, Response Lost

```text
T0 startTransaction
T1 insert ledger / update order / add outbox
T2 commitTransaction sent
T3 Transaction commit succeeds
T4 Commit response lost or timeout
T5 Driver sees UnknownTransactionCommitResult
```

Do not start a **new transaction** re-running from T0 just because of T5. Handle `UnknownTransactionCommitResult` by **retrying the commit on the same transaction/session**, followed by reconciliation if the deadline expires.

## 6. The `UnknownTransactionCommitResult` Error

### 6.1. What Does This Error Label Express?

When the driver throws an error labeled:

```text
UnknownTransactionCommitResult
```

it states that **the outcome of the transaction commit is uncertain to the client**. It does **not** state that the transaction aborted, nor that it definitely committed.

MongoDB supports retrying `commitTransaction` under the existing transaction identity to retrieve or complete the commit decision without re-running the body as a brand-new transaction.

### 6.2. Retrying Commit vs. Retrying Transaction

| Scenario | Correct action in principle |
| --- | --- |
| Error labeled `TransientTransactionError` in body | Can re-run **whole transaction** under proper session/transaction management |
| Commit returns `UnknownTransactionCommitResult` | Retry **commit of the same transaction**, do not run a new body |
| Commit returns definite non-resumable error | Classify by code/label and state; may need reconciliation |
| Prolonged connection loss, commit outcome unretrievable | Mark **`UNKNOWN`**, reconcile via business ID/ledger |
| External side effect already ran inside callback | Duplicate risk on callback retry; must move to an outbox |

### 6.3. Retry Commit Using the Same Identity

A driver transaction is bound to a logical session (`lsid`) and transaction number (`txnNumber`). Retrying commit through **the exact `ClientSession` representing that transaction** is essential.

Never open a different `MongoClient`/`ClientSession`, send a fresh transaction with the same business payload, and call that "retrying commit."

### 6.4. The Driver Can Retry Commits Automatically

MongoDB drivers have rules to retry commits—even when `retryWrites=false` under specification-supported conditions. In the Java Sync Driver, **`ClientSession.withTransaction()`** is a callback API containing retry logic for relevant labels, where:

- `TransientTransactionError`: can retry the whole transaction.
- `UnknownTransactionCommitResult`: retries commit.

The callback API cannot overcome permanent errors, expired deadlines, external side effects, or purged oplog/history; the application still needs reconciliation when final proof is missing.

### 6.5. Commit Timeouts Can Take Longer Due to the Cluster

In a sharded cluster, commits involve the transaction coordinator and participating shards. Certain phases carry internal majority/journal requirements even if the application specifies a different `w`. `commitTransaction` can stall when:

- Participants/shards are slow or unreachable.
- Replication/journal lags.
- Network partitions or failovers occur.
- Transactions are large with write conflicts.
- Disk/CPU/lock pressure spikes.
- The cluster is undergoing maintenance, resharding, or DDL.

Never jump mechanically to "the primary's CPU is low, so commit timeout must be a Java thread bug."

## 7. `TransientTransactionError`: When Retrying the Body Is Appropriate

### 7.1. Meaning

An error labeled `TransientTransactionError` inside a transaction generally indicates a temporary condition such as a primary stepdown or write conflict where the transaction could not finish as planned, and **the entire transaction may be retried** per driver guidance.

Since the callback can run again, the body must be **safe to re-execute**.

### 7.2. Does Not Mean Every MongoDB Exception Is Retryable

Examples:

- `DuplicateKey` because the business key genuinely exists.
- `DocumentValidationFailure` due to wrong BSON type.
- Unsupported collection/index/DDL operation.
- Authorization error.
- Transaction too large for cache (`TransactionTooLargeForCache` in MongoDB 6.2+).
- Business logic throwing an exception.

These errors require fixing data/config/code and will not vanish under infinite retries.

### 7.3. The Mistake of Re-Running Body After Unknown Commit

```java
try {
    session.commitTransaction();
} catch (MongoException e) {
    // WRONG if commit outcome is uncertain:
    runNewTransactionThatIncrementsBalanceAgain();
}
```

If the first commit succeeded, the new transaction applies the effects a second time. For a balance `$inc`, a repeated transaction leaves the balance wrong.

## 8. Retryable Writes: Benefits and Limits

### 8.1. Mechanism

Retryable writes allow official MongoDB drivers to automatically retry eligible single-document write operations upon certain network/election errors.

A request is identified by the driver via logical session + transaction number/statement identity, enabling the server to recognize retries of the same operation per protocol.

In supported versions/topologies:

```text
Java Driver (retryWrites=true)
     |
 first attempt (lsid, txnNumber)
     |
 network/election error
     |
 retry eligible operation
 (same logical statement identity)
     |
 server recognizes/replies without blindly applying twice
```

Prerequisites:

- Replica set or sharded cluster (not standalone).
- Compatible driver/server.
- Acknowledged writes (not `w:0`).
- Write operation belongs to the eligible set.
- Logical session/transaction history retention remains valid.

### 8.2. Commonly Eligible Operations

Common single-document commands:

- `insertOne`.
- `updateOne`.
- `replaceOne`.
- `deleteOne`.
- `findOneAndUpdate`/`findOneAndReplace`/`findOneAndDelete`.
- Certain `insertMany`/`bulkWrite` batches containing eligible statements, per version/specification.

Do not assume `updateMany`/`deleteMany` are protected by retryable writes like single-document statements. Within multi-document transactions, **individual writes inside the transaction do not auto-retry as they do outside a transaction**; transaction labels/commit retries govern instead.

### 8.3. Retry Counts Vary by Version and Timeout Model

Documentation notes drivers typically retry once by default; with client-side operation `timeoutMS`, drivers may retry multiple times until success, a non-retryable error, or deadline expiration.

Never hardcode "retryable writes always retry exactly once" or "retry forever." Check your exact Java Driver version, connection options, and driver specification.

### 8.4. `NoWritesPerformed` Starting in MongoDB 6.1+

If both attempts of a retryable write fail **without any write being performed**, the server can return the error label:

```text
NoWritesPerformed
```

This is useful proof **when the label is actually returned for an eligible server/operation**. Conversely, **the absence of this label does not prove a write was performed**. For batches, partial success remains possible.

Never synthesize this label from exception types or messages; only read labels returned by the driver/server.

### 8.5. Driver Retries Do Not Replace Business Idempotency

If an HTTP client misses a response, sends a **new request** to the API, and the API generates a **new MongoDB operation** with a random `_id`, the driver sees a brand-new request. Driver-level retryable writes have no idea two HTTP requests represent the same business action.

Therefore, you still need:

- Stable idempotency keys from the client/API.
- Unique business keys or request ledgers.
- Never minting a new `ObjectId` for the same command on retry.
- Atomic conditional updates.
- Reconciliation workflows for indeterminate outcomes.

## 9. Write Concern Errors and Retryable Writes Are Not Synonymous

A write may succeed on the primary yet fail `wtimeout`. Not all such cases are automatically retried by the driver like network errors.

Inspect:

- Exception class (e.g., `MongoWriteConcernException`).
- Write concern error code/`errInfo`.
- Retryable/transaction error labels if present.
- Whether the command is retryable.
- Attempt count and timeout model.
- Database state via an appropriate read.

**Never write "catch every `MongoException` and immediately call `updateOne` again."** Application-level retries issue new logical requests outside the driver's retry protocol.

## 10. Error Control Pattern: Separating Transport, Write, Commit, Business

A structured strategy:

```text
                 MongoDB operation outcome
                          |
                  +-------+-------+
                  |               |
              Success         Exception/error
                  |               |
                  v               v
           Confirmed state     Classify phase
                                  |
              +-------------------+----------------+
              |                   |                |
         Deterministic      Retryable/transient    Unknown
          rejection           at supported level  |
              |                   |                v
              v                   v           Reconcile by
        Return business       Bounded retry     requestId/outbox
          failure             with identity     + durable reads
                                  |                |
                                  +--------+-------+
                                           |
                                    final decision /
                                      manual queue
```

**Priority order:** preserve business correctness first, reduce latency second—especially for payments, inventory, quotas, points, counters, and emails.

## 11. Idempotency Keys: Bound to the Command, Not the Request Retry

### 11.1. Why Is `requestId` Needed?

Two HTTP requests:

```text
POST /orders/A100/pay
Idempotency-Key: pay-A100-20261114-01
```

must be recognized as **the same command**, even when the second arrives after a timeout or pod restart.

If the client creates a fresh idempotency key on retry, the database cannot distinguish an intentional new request from a retried old request.

### 11.2. Persisting a Request Ledger

An `operations` collection:

```javascript
{
  _id: "pay-A100-20261114-01",
  tenantId: "tenant-demo",
  orderId: "A100",
  requestHash: "sha256-of-canonical-business-payload",
  state: "CONFIRMED",
  result: { orderId: "A100", status: "PAID" },
  createdAt: ISODate("2026-11-14T00:00:00Z"),
  finishedAt: ISODate("2026-11-14T00:00:02Z")
}
```

A unique `_id` guards each idempotency key. `requestHash` detects when the same key is sent with a **different payload**, returning a conflict instead of silently accepting it.

### 11.3. Ledger State Must Not Be Marked Too Early

```text
RECEIVED
   |
   v
PROCESSING
   |
   +----> CONFIRMED (evidence that side effect is durable)
   |
   +----> REJECTED (confirmed business rule cannot apply)
   |
   +----> NEEDS_RECONCILIATION (outcome uncertain)
```

Never set `CONFIRMED` right after sending a command before receiving an ACK/commit or matching evidence.

### 11.4. Ledger and Business Write Must Be Atomic

Wrong:

```text
1. Insert ledger state=CONFIRMED
2. Crash
3. Order update never executed
```

Retries will see `CONFIRMED` and skip the update, leaving business data out of sync.

Better when both ledger and order live in the same MongoDB deployment:

- A short transaction writing **both the order and ledger**.
- Commit with an appropriate write concern.
- Retry per transaction labels.
- Reconcile after unknown commits.

Without transactions, you need a multi-state protocol, CAS/outbox, and reconciliation proven not to lose work. Never assume two separate single writes are atomic merely because they share a collection naming prefix.

## 12. Preventing `$inc` from Applying Twice

### 12.1. Non-Idempotent Update

```javascript
db.accounts.updateOne(
  { _id: "account-demo" },
  { $inc: { balanceCents: NumberLong("5000") } }
);
```

If the application sends two **distinct logical operations** after a timeout, the balance increases twice.

### 12.2. `$set` May Be State-Idempotent Yet Still Insufficient

```javascript
db.orders.updateOne(
  { _id: "A100" },
  { $set: { status: "PAID" } }
);
```

Running twice sets the same `status`, yet traps remain:

- `updatedAt: new Date()` changes.
- Events/outbox fire twice.
- A concurrent transition to `CANCELLED` gets overwritten back to `PAID`.
- Counters/notifications live in separate operations.
- Version/audit fields increment twice.

An update is only idempotent when the **entire business effect** of a retry remains unchanged, not merely one final field's value.

### 12.3. Compare-and-Set

```javascript
db.orders.updateOne(
  {
    _id: "A100",
    tenantId: "tenant-demo",
    status: "CREATED",
    version: NumberInt(7)
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);
```

If the first attempt succeeded, the second does not match because `status`/`version` changed. Still, `matchedCount:0` must distinguish among:

- The prior request already completed.
- Another request moved the order to a different state.
- Wrong ID/tenant.
- Data was deleted or rolled back.
- Version changed due to another operation.

CAS prevents **overwrites/repeated updates**, yet does not answer "who made the prior change." A `requestId`/audit ledger is needed to tell.

### 12.4. Deterministic Upsert by Request

You can record:

```javascript
db.requestLedger.updateOne(
  { _id: "pay-A100-20261114-01" },
  {
    $setOnInsert: {
      tenantId: "tenant-demo",
      orderId: "A100",
      requestHash: "hash-v1",
      state: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

When retrying with the same `_id`, the server finds the existing record without creating a duplicate. However, **upserting the ledger does not automatically make the payment side effect atomic**, and you must handle unique-key races, duplicate keys, and `requestHash` comparisons.

## 13. HTTP APIs with an `UNKNOWN` State

### 13.1. Do Not Return `200 Success` Without Evidence

A strategic response could be:

```json
{
  "requestId": "pay-A100-20261114-01",
  "state": "PENDING_RECONCILIATION",
  "message": "Final outcome not yet confirmed; query status again using requestId."
}
```

Depending on API design, HTTP `202 Accepted` fits when the command was durably accepted for async processing/reconciliation. However, if the request **is not even confirmed durably received**, do not emit a misleading accepted state. Return a transient error carrying the idempotency key and status-lookup endpoint.

### 13.2. Querying by Command ID

```text
GET /operations/pay-A100-20261114-01
```

The application reads the ledger/projection and returns:

- `CONFIRMED`.
- `REJECTED` with a clear reason.
- `PENDING`.
- `NEEDS_RECONCILIATION`.
- `NOT_FOUND`—yet **do not immediately conclude the prior write never happened** if commit or replication remains uncertain.

### 13.3. Mobile/Browser Retries Must Preserve the Key

If mobile connectivity drops, the client retries. Preserve the same key across retries with TTL/retention matching the business lifecycle—never mint a new key per attempt.

Never put keys containing PII, passwords, or card numbers into URLs/logs; keys should be opaque identifiers checked for ownership/authorization before returning status.

## 14. Post-Timeout Reconciliation Workflow

### 14.1. A Single `findOne` Is Not Always Enough

After a `wtimeout`, a query might see the document on the primary before it reaches majority. Conversely, a majority read not seeing the document yet does not prove the write will not reach majority moments later.

Reconciliation must separate:

- **Visibility:** what does a read currently see?
- **Durability:** has state satisfied the required write/read concern?
- **Identity:** was the change caused by the exact `requestId`?
- **Business effect:** do final state, ledger, outbox, and counters align?
- **Time:** are retries or replication still in flight?

### 14.2. Cautious Workflow

```text
Timeout / unknown result
          |
          v
Stop unsafe duplicate submission
          |
          v
Find requestId / deterministic business key
          |
          v
Read primary with appropriate readConcern/session
          |
          +-- found same request, durable evidence?
          |          |
          |          +-- yes -> CONFIRMED
          |
          +-- found conflict/different payload?
          |          |
          |          +-- yes -> CONFLICT / investigation
          |
          +-- not found or durability unclear
                     |
                     v
             bounded retry / monitor
                     |
                     v
             reconcile ledger, history,
               outbox and business source
                     |
                     v
            confirmed/rejected/UNKNOWN
```

Where permitted, set read concern `majority` to inspect majority-committed state. Still, understand read concern and read preference semantics for your MongoDB version. Secondary reads can lag; prefer the primary or use a causally consistent session when read-your-writes is required.

### 14.3. Do Not Use Absence as Absolute Negative Proof

Suppose a write hits `wtimeout` at T0, and at T1 `find({requestId})` returns null. That only says **in the current snapshot/read** the record is absent. It does not prove the original write cannot become majority-committed after T1.

Confirming failure requires stronger evidence, such as a deterministic server rejection, an idempotent reservation/ledger entry within the same transaction, or a business protocol with an immutable decision point.

### 14.4. Record Auditable Reconciliation State

```javascript
{
  _id: "pay-A100-20261114-01",
  state: "NEEDS_RECONCILIATION",
  source: "OrderService",
  lastObservedOrderStatus: "PAID",
  lastObservationReadConcern: "majority",
  attempts: NumberInt(2),
  lastErrorCategory: "WRITE_CONCERN_TIMEOUT",
  lastCheckedAt: new Date(),
  nextAction: "RECHECK_AFTER_REPLICATION_RECOVERY"
}
```

This is a **workflow-tracking document template**, not built-in MongoDB fields. Never paste full snapshots containing PII into public tickets.

## 15. Distinguishing `DuplicateKey` After Retry

### 15.1. Duplicate Key May Signal the Retry Already Happened

If the client retries an insert with the same deterministic `_id`:

```javascript
db.orders.insertOne({
  _id: "tenant-demo:A100",
  tenantId: "tenant-demo",
  externalOrderId: "A100",
  status: "CREATED"
});
```

the second attempt can return E11000 `DuplicateKey`. This **does not automatically prove** the first request succeeded with the same payload/intent, as the key could belong to another request or hold different contents.

### 15.2. Handling Procedure

1. Catch `DuplicateKey`.
2. Read the document by unique key and tenant.
3. Compare `requestId` and canonical payload hash/expected result.
4. If matching: treat as already processed once durability requirements are met.
5. If mismatched: return a conflict; do not overwrite.
6. If absent/uncertain: route to reconciliation.

Never catch `DuplicateKey` and return success unconditionally.

### 15.3. Unique Indexes Must Have the Right Scope

For multi-tenant systems:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

If business rules allow the same `externalOrderId` across different tenants, index the exact composite key. On sharded collections, unique indexes must also satisfy shard-key prefix restrictions and topology rules. Do not assume global uniqueness if the cluster does not enforce it.

## 16. `insertMany` and `bulkWrite` Can Partially Succeed

### 16.1. Why Must Batches Be Handled Per Element?

Suppose a client sends 5 documents:

```text
D1 D2 D3 D4 D5
```

D1/D2 may be written; D3 hits a duplicate key; D4/D5 may or may not have been attempted depending on `ordered`, operation type, and network/concern errors. Never treat a batch as an atomic transaction.

### 16.2. `ordered:true` vs. `ordered:false`

- `ordered:true`: driver/server stops the sequence at the first write error per ordered batch semantics.
- `ordered:false`: attempts remaining operations despite individual errors; execution order may vary.
- Write concern timeouts can occur **after writes were already applied**.
- Network errors can leave batch responses incomplete.

### 16.3. Store Stable IDs for Every Item

```javascript
const docs = [
  { _id: "batch-1:item-1", amount: 100 },
  { _id: "batch-1:item-2", amount: 200 },
  { _id: "batch-1:item-3", amount: 300 }
];
```

When retrying or reconciling, preserve fixed `_id`/unique item keys; never mint fresh `ObjectId` values on every retry.

### 16.4. `NoWritesPerformed` and Partial Batches

MongoDB 6.1+ provides `NoWritesPerformed` for certain retryable write cases where no writes succeeded across attempts. When returned by the server, it is clear evidence; **absence of the label does not imply partial success**, as other states exist.

For batches, inspect:

- Items actually inserted by stable IDs.
- Per-item errors/indices.
- Write concern errors.
- Server/driver retry labels.
- `BulkWriteException` details and available counters.
- Data readbacks and business invariants.

Only retry **items genuinely unconfirmed/unreconciled**, or retry the whole set using idempotency keys proven free of duplicate side effects.

### 16.5. Careful Readback

```javascript
db.batchItems.find({
  _id: {
    $in: [
      "batch-1:item-1",
      "batch-1:item-2",
      "batch-1:item-3"
    ]
  }
});
```

Verify which results have majority durability, which payloads match, and which items remain indeterminate. Never treat "all 3 IDs visible right now" as proof that all downstream external side effects completed.

## 17. Transaction Commit: Handling Multi-Write Atomicity

### 17.1. Order and Ledger Design

A short transaction can write:

```text
orders
  update status CREATED -> PAID

processed_commands
  insert _id=requestId, result=PAID

outbox
  insert _id=requestId+":OrderPaid", state=NEW
```

Upon successful commit, these changes are atomic **within the MongoDB transaction**. Workers sending emails/payment notifications consume the outbox **post-commit**, rather than invoking external APIs inside a retryable callback.

### 17.2. What Must Never Run Inside the Callback?

Wrong:

```java
session.withTransaction(() -> {
    chargeCreditCard(); // Wrong: external effect can be repeated.
    updateOrder(session);
    return null;
});
```

`withTransaction` can retry the callback on `TransientTransactionError`. MongoDB cannot roll back an external card charge. Use an outbox, saga, or gateway idempotency keys.

### 17.3. Transaction Callbacks Need Idempotency

Even for database-only transactions, callbacks can re-execute. Use `requestId` in a ledger collection with read-existing/compare-payload logic:

```text
begin transaction
    |
 lookup command by requestId
    |
 +-- exists same request hash -> return stored result
 |
 +-- exists different hash -> reject conflict
 |
 +-- absent -> apply conditional business writes,
               insert command result + outbox
    |
 commit with majority
```

If the first commit succeeded and the response was lost, retrying that transaction's commit is the primary path. If recovery eventually requires a new request, the unique ledger prevents double-applying business effects.

## 18. Java Sync Driver: Configuring Write Concern and Retryable Writes

### 18.1. Dependency

Maven example:

```xml
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>VERIFIED_VERSION</version>
</dependency>
```

The APIs below target Java 17 and Java Sync Driver 5.x; align your BOM/driver version with your MongoDB Server/FCV and runtime rather than copying arbitrary version numbers.

### 18.2. Initializing the Client

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

String uri = System.getenv("MONGODB_TEST_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalArgumentException("Missing test URI");
}

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .retryWrites(true)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    MongoDatabase database =
        client.getDatabase("mongo_timeout_row441_lab");

    MongoCollection<Document> orders = database
        .getCollection("orders")
        .withWriteConcern(
            WriteConcern.MAJORITY.withWTimeout(
                5, TimeUnit.SECONDS
            )
        );

    // Operate only on authorized test namespaces.
}
```

Notes:

- `retryWrites=true` does not make every command retryable.
- `wtimeout` bounds only the write concern wait, not the full latency budget.
- Newer drivers/servers support client-side `timeoutMS` with distinct semantics, and connection-string `wtimeoutMS` is marked deprecated in some contexts; check your exact release before configuring.
- Load URIs from a secrets manager; never log connection strings/passwords.
- On Atlas, verify the cluster's default write concern.

### 18.3. Catching `MongoWriteConcernException` Explicitly

```java
import com.mongodb.MongoException;
import com.mongodb.MongoWriteConcernException;
import com.mongodb.MongoWriteException;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

try {
    UpdateResult result = orders.updateOne(
        Filters.and(
            Filters.eq("_id", "A100"),
            Filters.eq("tenantId", "tenant-demo"),
            Filters.eq("status", "CREATED")
        ),
        Updates.set("status", "PAID")
    );

    System.out.println(
        "matched=" + result.getMatchedCount()
    );

} catch (MongoWriteConcernException e) {
    // Write may already have been applied on the primary.
    // DO NOT mark FAILED and DO NOT re-run $inc.
    System.err.println(
        "Write concern not acknowledged: "
        + e.getWriteConcernError().getCode()
    );
    markNeedsReconciliation("A100");

} catch (MongoWriteException e) {
    // Classify DuplicateKey, validation, etc.
    handleDefiniteWriteError(e);

} catch (MongoException e) {
    // Network/selection/deadline and other errors:
    // outcome may be unknown; inspect labels/code/context.
    handleMongoOutcomeUncertain(e);
}
```

`markNeedsReconciliation`, `handleDefiniteWriteError`, and `handleMongoOutcomeUncertain` are **application-defined methods**, not built into the driver. Drive handling from **phase, labels, and business invariants**, not exception names alone.

### 18.4. `matchedCount:0` Is Not Necessarily Failure

A CAS update returning `matchedCount:0` may mean:

- The command already succeeded earlier.
- Another service updated the document.
- The transition was rejected because preconditions changed.

Do not immediately return 404/500 without reading order status and the request ledger.

## 19. Java Transaction Callback: Pattern for MongoDB-Only Body

### 19.1. Example with a Request Ledger

Illustrative workflow on a test MongoDB replica set/sharded cluster:

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;

import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

import org.bson.Document;
import java.util.Date;

static String markPaidOnce(
        MongoClient client,
        MongoDatabase db,
        String tenantId,
        String orderId,
        String requestId,
        String requestHash) {

    MongoCollection<Document> commands =
        db.getCollection("processed_commands");

    MongoCollection<Document> orders =
        db.getCollection("orders");

    MongoCollection<Document> outbox =
        db.getCollection("outbox");

    TransactionOptions options = TransactionOptions.builder()
        .readPreference(ReadPreference.primary())
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();

    try (ClientSession session = client.startSession()) {
        return session.withTransaction(() -> {
            Document previous = commands.find(
                session, Filters.eq("_id", requestId)
            ).first();

            if (previous != null) {
                if (!requestHash.equals(
                        previous.getString("requestHash"))) {
                    throw new IllegalArgumentException(
                        "Idempotency key reused with different payload"
                    );
                }
                return previous.getString("resultStatus");
            }

            var update = orders.updateOne(
                session,
                Filters.and(
                    Filters.eq("_id", orderId),
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("status", "CREATED")
                ),
                Updates.set("status", "PAID")
            );

            if (update.getMatchedCount() != 1) {
                throw new IllegalStateException(
                    "Order not in CREATED state; reconcile"
                );
            }

            commands.insertOne(session,
                new Document("_id", requestId)
                    .append("tenantId", tenantId)
                    .append("orderId", orderId)
                    .append("requestHash", requestHash)
                    .append("resultStatus", "PAID")
                    .append("createdAt", new Date())
            );

            outbox.insertOne(session,
                new Document("_id", requestId + ":OrderPaid")
                    .append("tenantId", tenantId)
                    .append("orderId", orderId)
                    .append("type", "OrderPaid")
                    .append("state", "NEW")
                    .append("createdAt", new Date())
            );

            return "PAID";
        }, options);
    }
}
```

### 19.2. Preconditions for This Example

- Collections must **already exist** before the transaction; do not rely on implicit creation in unsupported environments/scopes.
- Unique `_id` on `processed_commands` and `outbox` protects keys within the namespace.
- Each order has a stable `_id`. If multiple tenants can collide on order IDs, scope `_id`/index keys accordingly.
- The callback writes only to MongoDB; no external emails/payments/APIs.
- If the callback re-runs after a transient error, preconditions and the ledger prevent double-applying one logical command.
- Under concurrent requests with the same `requestId`, the transaction may hit write conflicts or duplicate keys. The app must still verify/reconcile rather than treating every `DuplicateKey` as success.
- `ReadConcern.SNAPSHOT` and `WriteConcern.MAJORITY` have topology-dependent semantics; do not rely on this session to solve consistency outside transactions.
- If the method throws after exhausting its retry budget, **do not conclude from the exception that the commit definitely aborted**. State may require reconciliation per transaction labels.

### 19.3. Why Is There No Manual `commitTransaction` Retry Loop Here?

`ClientSession.withTransaction()` is a callback API with built-in retry logic for `TransientTransactionError` and `UnknownTransactionCommitResult`. Wrapping an extra blind retry loop outside it with **a new `ClientSession` and the same body** can break semantics if no ledger exists.

With lower-level control (`startTransaction`, manual `commitTransaction`), the application manages retries by error labels on the **same session**. Do not arbitrarily overlap both models.

## 20. Java Core API: Handling Unknown Commits at the Right Level

### 20.1. Phase-Safe Pseudocode

```text
with a live ClientSession:
  startTransaction(transactionOptions)

  try:
      execute MongoDB writes in transaction
  catch e:
      if TransientTransactionError:
          abort if appropriate
          retry WHOLE transaction with bounded policy
      else:
          abort if possible
          stop/reconcile or reject depending error

  while commit budget remains:
      try:
          commitTransaction() ON SAME SESSION
          return CONFIRMED
      catch e:
          if UnknownTransactionCommitResult:
              retry COMMIT of the SAME transaction
          else:
              classify; do not blindly re-run body

  if no conclusive commit result:
      return NEEDS_RECONCILIATION
```

### 20.2. Java Commit Retry Skeleton

```java
import com.mongodb.MongoException;
import com.mongodb.client.ClientSession;
import java.time.Duration;

static void commitWithBoundedRetry(
        ClientSession session,
        Duration budget) {

    long deadline =
        System.nanoTime() + budget.toNanos();

    while (true) {
        try {
            session.commitTransaction();
            return;
        } catch (MongoException e) {
            boolean unknown =
                e.hasErrorLabel("UnknownTransactionCommitResult");

            if (!unknown) {
                throw e;
            }

            if (System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                    "COMMIT_UNKNOWN: requires reconciliation",
                    e
                );
            }

            // Retry COMMIT on same live session; do not call
            // startTransaction() or re-run the business body.
            // Add bounded backoff/jitter and metrics as needed.
        }
    }
}
```

**This skeleton illustrates the principle**, not a complete production transaction coordinator: you also need backoff, interrupt/deadline handling, error taxonomy, session lifecycle management, state transitions, and observability. If the method throws upon exhausting budget, retain `requestId` for reconciliation—never re-run the whole body simply because `IllegalStateException` was caught.

### 20.3. Driver Retries `commitTransaction` with Majority

MongoDB docs note that when the driver retries a commit, the write concern on the retried commit is raised/set to `w:"majority"` per commit retry behavior. Do not assume every commit retry carries the same effective write concern as the original command.

### 20.4. Unknown Commit Result After Session Closes

If the process crashes or the session has closed, do not assume you can reconstruct the original transaction merely by re-sending business statements. Recovery uses the ledger/unique request ID, majority reconciliation, and designed audit trails.

## 21. Timeout Configuration: No Single Universal Knob

### 21.1. Distinction Table

| Setting | Scope | Purpose | Does not guarantee |
| --- | --- | --- | --- |
| `serverSelectionTimeoutMS` | Driver | Find eligible MongoDB server | That an earlier write was not applied |
| `connectTimeoutMS` | Driver/socket | Establish connection | Status of an already-sent attempt |
| `socketTimeoutMS` | Driver/socket | Wait for socket read/write (when supported) | That the server rolled back when client stopped waiting |
| `timeoutMS` | Client-side operation timeout in supported versions | Total operation deadline | Whether transaction body rolled back (check separately) |
| `wtimeout` | Write concern | Wait for required member ACKs | Does not undo primary writes |
| `wtimeoutMS` in URI | Driver/config (deprecation nuances) | Write concern timeout | Full replacement for `timeoutMS` |
| `maxTimeMS` | Server-side limit on supported ops | Abort execution past limit | "No mutation" guarantee for all write types |
| `maxCommitTimeMS` | Transaction options on supported versions | Server time limit for commit | Proof commit definitely did not happen after timeout |
| HTTP gateway timeout | App/API | Request response deadline | That backend processing stopped running |

### 21.2. Avoid Unbudgeted "Timeout Stacking"

Example:

```text
Gateway timeout:            5 s
Java client total timeout:  10 s
MongoDB wtimeout:            8 s
Transaction body:            4 s
External sink timeout:      15 s
```

The gateway returns 504 after 5 seconds while the backend keeps writing for up to 10 seconds. An immediate client retry with a new request ID creates a duplicate.

Design around an end-to-end deadline:

- Headroom for server selection/connection.
- Query/write/commit duration.
- Time for reconciliation or persisting `PENDING` state.
- Graceful shutdown.
- Backpressure when `UNKNOWN` counts rise.
- Preserving the idempotency key across the entire lifecycle.

### 21.3. Overly Short Timeouts Trigger Retry Storms

```text
replication lag rises
       |
write concern timeouts
       |
clients retry unsafe writes
       |
additional write load
       |
replication lag rises further
```

This is a **retry storm**. Mitigate with bounded retries + exponential backoff/jitter, rate limits, circuit breakers, idempotency, and load shedding rather than raising timeouts indefinitely.

## 22. Diagnosing Replication When `wtimeout` Spikes

### 22.1. First Questions

- Which effective `w` is the command using?
- Is the error a genuine write concern error or a network timeout?
- Is there a healthy primary, or did an election just happen?
- Are secondaries lagging in applying the oplog or slow on journal/fsync?
- Is oplog replication, flow control, disk IOPS, or the network saturated?
- Is a member in `RECOVERING`, `STARTUP2`, or unreachable?
- Are too many concurrent transactions, checkpoints, or index builds overlapping?
- On a sharded cluster, which participant is the commit waiting on?

### 22.2. `rs.status()` and Replication Info

On an authorized replica set:

```javascript
const st = rs.status();

printjson({
  set: st.set,
  myState: st.myState,
  members: st.members.map((m) => ({
    name: m.name,
    stateStr: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate
  }))
});
```

You can also inspect:

```javascript
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
```

Fields vary by release and permissions. Never diagnose root cause from a single lag number in one snapshot; collect time series alongside disk/network/CPU metrics.

### 22.3. Cluster Symptoms to Correlate

```text
Client wtimeout errors ↑
    |
    +-- Secondary replication lag ↑
    +-- Disk write await/IOPS ↑
    +-- Journal sync latency ↑
    +-- Primary flow control ↑
    +-- Election/stepdown events ↑
    +-- Long transactions/index builds ↑
```

Never reason "wtimeout is rising = turn off majority." If the replica set has replication trouble, lowering durability merely hides symptoms and raises data-loss risk.

### 22.4. Sharded Transactions Differ from Single-Shard Writes

Multi-shard transactions require coordination. If one participant is slow or network links flap, commit outcomes can stay unknown longer. Ensure you:

- Know which shards the transaction touches.
- Monitor `mongos`/config/shard health.
- Check locks, distributed commits, and cross-shard latency.
- Use a business ledger for reconciliation.
- Never restart all `mongos`/shards just because one transaction timed out.

## 23. What Should Be Logged for Investigation?

A safe log record:

```json
{
  "event": "mongo_write_outcome",
  "requestId": "pay-A100-20261114-01",
  "operation": "confirmPayment",
  "namespace": "commerce.orders",
  "phase": "COMMIT",
  "outcome": "UNKNOWN",
  "writeConcern": "majority",
  "errorLabel": "UnknownTransactionCommitResult",
  "attempt": 2,
  "durationMs": 5100,
  "correlationId": "req-51db",
  "reconciliationScheduled": true
}
```

**Never log:**

- Passwords or connection strings containing secrets.
- Full customer documents containing PII.
- Raw payment/card details.
- Transaction session identifiers when policy forbids.
- Sensitive stack traces inside HTTP responses.
- Messages claiming "rollback done" if `abortTransaction()` was merely called after an unknown commit.

### 23.1. Suggested Application-Defined Metrics

```text
mongo_write_attempts_total
mongo_write_success_total
mongo_write_concern_timeout_total
mongo_network_timeout_total
mongo_commit_unknown_total
mongo_transaction_transient_error_total
mongo_retryable_write_attempts_total
mongo_reconciliation_pending
mongo_reconciliation_confirmed_total
mongo_reconciliation_conflicts_total
mongo_idempotency_duplicate_requests_total
mongo_business_write_latency_seconds
mongo_transaction_commit_latency_seconds
mongo_replication_lag_seconds
mongo_app_retry_budget_exhausted_total
```

These are **sample names**, not built-in MongoDB Server metrics. When building dashboards, segment error rates by operation type, client version, cluster, and tenant cohort rather than lumping all timeouts together.

### 23.2. A Good Alert Has Three Layers

1. **Symptom:** rising unknown outcomes.
2. **Resource/DB:** replication lag, disk, elections.
3. **Business invariant:** pending reconciliation count, duplicate prevention, diverging payments/orders.

Timeout rates dropping while the reconciliation queue keeps growing means **recovery is incomplete**.

## 24. Incident Runbook: Write Concern Timeout

### 24.1. Phase A — Contain and Prevent Duplicate Side Effects

1. Identify collection, command type, effective write concern, and onset timestamp.
2. Preserve `requestId`/business IDs for affected requests.
3. Pause all **non-idempotent** retries (especially `$inc`, random `_id` inserts, external payments).
4. Record `UNKNOWN` explicitly instead of marking failed or success.
5. Verify API gateway/client retry logic is not minting new request IDs.

### 24.2. Phase B — Assess Cluster Health

- Replica set/shard member states.
- Recent elections/stepdowns.
- Replication lag and oplog apply rate.
- Disk latency/queue, journal sync, CPU/memory.
- Background tasks: index builds, backups, bulk imports.
- Network, connection pools, and thread contention.
- Whether the write concern policy is achievable under current topology.

### 24.3. Phase C — Reconcile

- Read by stable `requestId` and expected business key.
- Use read concern/preference matching the durability contract.
- Cross-check the operation ledger, order state, outbox, balances, and external gateways.
- Mark `CONFIRMED` when durable evidence exists.
- Mark `REJECTED` when proof confirms the operation could not/did not apply.
- Keep `NEEDS_RECONCILIATION` while ambiguous.
- Execute bounded retries using the same logical identity or an approved recovery protocol.

### 24.4. Phase D — Restore Performance

Only after protecting correctness:

- Throttle non-urgent batch writes.
- Remediate unhealthy members, disks, or networks.
- Tune application backoff and circuit breakers.
- Inspect connection pool and server selection settings.
- Evaluate capacity and placement.
- Revisit SLO/timeout configurations based on measurements.

Never alter cluster-wide default write concern just to silence alerts without evaluating durability requirements.

## 25. Incident Runbook: Unknown Transaction Commit

### 25.1. Do Not Re-Run the Body Immediately

When commit reports `UnknownTransactionCommitResult`:

1. If the **`ClientSession` for the same transaction is still alive**: retry commit via driver/callback API within a bounded policy.
2. If the driver callback is managing retries: let it finish or throw per budget; avoid stacking manual outer retries.
3. If the process/session is lost or budget is exhausted: preserve `requestId` and route to reconciliation.
4. Read the ledger + all writes in the transaction with appropriate consistency.
5. Distinguish confirmed commits, confirmed aborts, and states lacking proof.
6. Never call `abortTransaction()` after an unknown commit and log "definitely rolled back."

### 25.2. If the Transaction Involved External Side Effects

If the callback sent an email or charged a payment, inspect external idempotency records immediately. A MongoDB transaction cannot roll back a charge already settled externally. Recovery may require **compensation** or an outbox/saga, not just retrying commit.

### 25.3. When Commit Cannot Retry Due to Permanent Errors

Never loop infinitely when:

- The session/transaction is no longer valid.
- Tokens/identities expired.
- Authentication/authorization failed.
- The driver/application is shutting down.
- The cluster remains unhealthy.
- Retry budgets or HTTP deadlines expired.

Transition state to `UNKNOWN`/reconciliation and fire clear alerts rather than silent background retries.

## 26. Safe `mongosh` Lab: Observing Outcomes and Idempotency

### 26.1. Lab Scope

- Use a **test MongoDB replica set**, not standalone, for transactions/retryable writes.
- Use synthetic data with no real payments.
- Never run `rs.stepDown()`, shut down secondaries, or inject network partitions just to "force a timeout."
- Never modify FCV, replica set config, or oplog settings.
- Create only random namespaces and documents tagged with `runId`.
- Never drop whole databases or touch others' data.
- This lab simulates an ambiguous outcome by **ignoring the response at the application layer** after a normal write—without breaking the cluster.

### 26.2. Creating an Isolated Namespace

```javascript
const lab = db.getSiblingDB("mongo_timeout_row441_lab");
const runId = "row441_" + new ObjectId().toHexString();
const ordersName = "orders_" + runId;
const commandsName = "commands_" + runId;
const tenantId = "tenant_" + runId;

for (const n of [ordersName, commandsName]) {
  if (lab.getCollectionNames().includes(n)) {
    throw new Error("Namespace conflict, refuse overwrite");
  }
}

lab.createCollection(ordersName);
lab.createCollection(commandsName);

const orders = lab.getCollection(ordersName);
const commands = lab.getCollection(commandsName);

printjson({
  db: lab.getName(),
  orders: ordersName,
  commands: commandsName,
  runId,
  tenantId
});
```

### 26.3. Seeding an Order

```javascript
const orderId = "order_" + runId;
const requestId = "confirm_" + runId;

orders.insertOne({
  _id: orderId,
  runId,
  tenantId,
  status: "CREATED",
  version: NumberInt(1),
  amountCents: NumberLong("1500")
});

printjson(orders.findOne({ _id: orderId, runId }));
```

### 26.4. Recording a Stable Command ID

```javascript
const commandDoc = {
  _id: requestId,
  runId,
  tenantId,
  orderId,
  requestHash: "demo-confirm-v1",
  state: "RECEIVED",
  createdAt: new Date()
};

commands.updateOne(
  { _id: requestId, runId },
  { $setOnInsert: commandDoc },
  { upsert: true }
);
```

This is a simple lab reservation. **Do not treat this step alone as atomic with the business update.** In production, use a short transaction or a strict multi-state ledger protocol with recovery.

### 26.5. Running the CAS Update

```javascript
const first = orders.updateOne(
  {
    _id: orderId,
    runId,
    tenantId,
    status: "CREATED",
    version: NumberInt(1)
  },
  {
    $set: {
      status: "PAID",
      lastRequestId: requestId
    },
    $inc: {
      version: 1
    }
  }
);

printjson({
  matched: first.matchedCount,
  modified: first.modifiedCount
});
```

### 26.6. Simulating "Client Missed the Result"

Instead of forcing a network timeout, pretend the application missed the `first` response object. From another terminal/consumer flow, resend the exact same **CAS command**:

```javascript
const again = orders.updateOne(
  {
    _id: orderId,
    runId,
    tenantId,
    status: "CREATED",
    version: NumberInt(1)
  },
  {
    $set: {
      status: "PAID",
      lastRequestId: requestId
    },
    $inc: {
      version: 1
    }
  }
);

printjson({
  retryMatched: again.matchedCount,
  retryModified: again.modifiedCount,
  current: orders.findOne({ _id: orderId, runId })
});
```

Expected after the first success: the second call returns `matchedCount:0`; `version` incremented only from 1 to 2, not 3. **Yet `matchedCount:0` alone does not prove the cause**; `lastRequestId` on the document confirms this request updated the order in the lab.

### 26.7. Reconciling Before Marking Confirmed

```javascript
const observed = orders.findOne({
  _id: orderId,
  runId,
  tenantId
});

if (!observed ||
    observed.status !== "PAID" ||
    observed.lastRequestId !== requestId) {
  throw new Error("Cannot confirm logical request");
}

commands.updateOne(
  {
    _id: requestId,
    runId,
    tenantId,
    state: "RECEIVED"
  },
  {
    $set: {
      state: "CONFIRMED",
      confirmedAt: new Date()
    }
  }
);

printjson({
  observed,
  command: commands.findOne({ _id: requestId, runId })
});
```

This **illustrates an idempotency protocol with a reconciliation step**, not proof of end-to-end atomicity. Because the ledger and order are two separate writes, a production implementation must handle crashes between them, e.g., via a transaction.

### 26.8. Testing Write Concern Safely

```javascript
const ack = lab.runCommand({
  update: ordersName,
  updates: [
    {
      q: { _id: orderId, runId, tenantId },
      u: { $set: { labMarker: "majority-ack" } },
      multi: false
    }
  ],
  writeConcern: {
    w: "majority",
    j: true,
    wtimeout: 5000
  }
});

printjson({
  ok: ack.ok,
  n: ack.n,
  writeConcernError: ack.writeConcernError
});
```

On a healthy test replica set, this command succeeds. If a write concern error occurs, **do not** blindly retry an `$inc`; read back and reconcile.

Never set `w:100` or make majority unavailable to trigger timeouts. The lab teaches handling, not stressing or disabling replica members.

### 26.9. A Short Transaction in the Lab

If your test deployment supports transactions and the collections are created:

```javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase(lab.getName());
const sorders = sdb.getCollection(ordersName);
const scommands = sdb.getCollection(commandsName);

const txnOrderId = "txn_order_" + runId;
const txnRequestId = "txn_confirm_" + runId;

// Seed outside the transaction, before starting:
orders.insertOne({
  _id: txnOrderId,
  runId,
  tenantId,
  status: "CREATED",
  version: NumberInt(1)
});

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  const result = sorders.updateOne(
    {
      _id: txnOrderId,
      runId,
      tenantId,
      status: "CREATED"
    },
    {
      $set: {
        status: "PAID",
        lastRequestId: txnRequestId
      }
    }
  );

  if (result.matchedCount !== 1) {
    throw new Error("Unexpected transaction precondition");
  }

  scommands.insertOne({
    _id: txnRequestId,
    runId,
    tenantId,
    orderId: txnOrderId,
    state: "CONFIRMED",
    requestHash: "demo-txn-v1"
  });

  session.commitTransaction();
} catch (e) {
  print("Transaction error: " + e.message);

  // This lab does not try to trigger UnknownTransactionCommitResult.
  // In a real app, that label requires retrying the commit
  // of the same session/transaction before concluding.
  // Never assume abortTransaction cancels a commit
  // once the commit outcome is already UNKNOWN.
  throw e;
} finally {
  session.endSession();
}
```

This brief snippet **lacks a full retry loop**; it shows how a transaction updates the order and ledger in one commit. If the server errors or commit outcome is unknown, treat it as indeterminate and follow the Java/Runbook procedures—do not replay the transaction manually with this script.

### 26.10. Reading Back After Commit

```javascript
printjson({
  order: orders.findOne({
    _id: txnOrderId,
    runId
  }),
  command: commands.findOne({
    _id: txnRequestId,
    runId
  })
});
```

Where possible, read with matching consistency guarantees; in a healthy lab, you will see `PAID` and ledger `CONFIRMED`. **Never** treat a local log saying `commitTransaction` was sent as proof the transaction committed.

### 26.11. Cleanup by `_id + runId`

Before deleting:

```javascript
printjson({
  db: lab.getName(),
  orders: orders.getName(),
  commands: commands.getName(),
  runId
});

const ownOrders = orders.find(
  { runId, tenantId },
  { _id: 1, runId: 1 }
).toArray();

const ownCommands = commands.find(
  { runId, tenantId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  orderCount: ownOrders.length,
  commandCount: ownCommands.length
});
```

Only after confirming the run and ensuring no other app uses them:

```javascript
for (const item of ownOrders) {
  orders.deleteOne({
    _id: item._id,
    runId,
    tenantId
  });
}

for (const item of ownCommands) {
  commands.deleteOne({
    _id: item._id,
    runId,
    tenantId
  });
}

printjson({
  remainingOrders: orders.countDocuments({ runId, tenantId }),
  remainingCommands: commands.countDocuments({ runId, tenantId })
});
```

Never run `dropDatabase()` or `deleteMany({})` on a shared database. Lab collections may be cleaned up per owner/retention rules after verification, not arbitrarily dropped inside scripts.

## 27. Targeted Experiment: Simulating Timeouts Without Breaking the Cluster

You can rehearse application behavior via **fault injection on the response path inside a test harness** instead of killing primaries/secondaries:

- Let the server write succeed, while a test stub/adapter returns `UNKNOWN` to the caller.
- Verify the caller **does not** issue another `$inc` or insert a random ID.
- Verify the caller preserves the same `requestId`.
- Verify the status endpoint reads state from the ledger.
- Verify that on an unknown transaction commit result, code retries **commit** rather than invoking an external callback outside driver mechanics.
- Verify workflows exhausting retry budgets enter the reconciliation queue.
- Verify reconciliation does not mark `REJECTED` merely because one majority read did not yet see the record.
- Verify business sinks emit no duplicate emails/payments.
- Test failovers on a test replica set per infrastructure-approved runbooks—never in production.

A mocked exception test does not prove the real server emits the exact same error labels. Combine MongoDB integration tests with failure-path tests; this section outlines methodology, not full QA execution.

## 28. Reconciling External Payments and Outboxes

### 28.1. MongoDB Transactions Do Not Encompass Payment Gateways

```text
MongoDB transaction commits
            |
         response lost
            |
Application unsure
            |
External payment API may also have succeeded
```

If the payment gateway supports idempotency keys, preserve **the same key** across all retries and query transaction status at the gateway. Never submit a new charge with a fresh key hoping MongoDB will roll back the earlier one.

### 28.2. Transactional Outbox

Inside the MongoDB transaction, update the order and insert an outbox event:

```javascript
{
  _id: "pay-A100-20261114-01:OrderPaid",
  eventType: "OrderPaid",
  orderId: "A100",
  requestId: "pay-A100-20261114-01",
  publishState: "NEW"
}
```

A worker publishes **post-commit**, using sink idempotency and checkpoint state. If the publish response drops, the worker retries with the same event key. This yields at-least-once delivery with idempotent processing, not automatic exactly-once across every downstream system.

### 28.3. When Multiple Sources of Truth Diverge

If the payment gateway reports the charge succeeded while the MongoDB ledger is unconfirmed, follow a reconciliation policy:

1. Verify the gateway transaction ID.
2. Verify the MongoDB order/request ledger and payment references.
3. Prevent charging again.
4. Decide whether to repair MongoDB state, issue compensation, or route to manual review.
5. Record an audit entry.

Never issue a refund or re-charge solely because of a MongoDB socket timeout.

## 29. Error Taxonomy and Automated Decisions

| Event | What is known for certain? | Action |
| --- | --- | --- |
| `insertOne` majority-acknowledged | Write satisfied write concern contract | Mark confirmed, proceed |
| `MongoWriteConcernException` | Write concern unmet; primary modification may exist | Reconcile; do not blind retry |
| Network timeout after send | Outcome unknown | Retry per eligible driver protocol/idempotency key or reconcile |
| `NoWritesPerformed` returned by server for eligible retryable write | No writes occurred per label semantics | Can classify no-write, still check business flow |
| `DuplicateKey` on retry | Key already exists | Read/compare request identity/hash |
| Validation failure | Document rejected by validator in that operation | Fix payload/type; do not retry forever |
| `TransientTransactionError` in body | Whole transaction eligible for retry | Bounded callback/core transaction retry |
| `UnknownTransactionCommitResult` | Unknown whether commit occurred | Retry commit on same session; then reconcile |
| `TransactionTooLargeForCache` | Transaction too big for cache per version | Redesign batch/transaction; do not blind retry |
| Client-side timeout of `withTransaction` | Callback may stop at deadline; check commit labels | Reconcile; do not equate with abort |
| `matchedCount:0` after CAS | Preconditions did not match at update time | Read order+ledger; distinguish already applied vs. conflict |
| Batch error | Partial success possible | Per-item reconciliation |
| HTTP 504 | Gateway timed out waiting | Keep `requestId`, status endpoint/async resolution |

This is a classification guide; drivers, servers, and versions may introduce additional codes and labels. **Rely on real evidence rather than inventing certainty from a generic exception.**

## 30. Diagnosing Common Misconceptions

| Misconception | Consequence | Correct understanding |
| --- | --- | --- |
| "Timeout means nothing was written" | Duplicate updates/inserts | `UNKNOWN` unless proven otherwise |
| "`wtimeout` rolls back data" | Wrong client retries | Primary modifications are not auto-undone |
| "`wtimeout` bounds the entire update" | Broken SLOs | Covers only the write concern phase for `w` |
| "`w:1` is majority durable" | Data can roll back on failover | Choose appropriate write concern |
| "`j:true` equals `w:majority`" | Confuses journal vs. replication | Two separate durability dimensions |
| "MongoDB always uses the same default `w`" | Wrong contract after topology changes | Verify effective default |
| "Missing on one secondary read = write failed" | Dropped or doubled work | Account for replication lag/read concern |
| "8.0 majority ack means secondaries applied immediately" | Read misses state | Use causal consistency when required |
| "Catch every `MongoException` and retry `$inc`" | Double-increments balance | Classify errors and enforce idempotency |
| "`retryWrites=true` solves HTTP retries too" | New requests still duplicate | Use a stable `requestId` |
| "`retryWrites` works with `w:0`" | No ACK/statement retry | Use acknowledged writes |
| "`updateMany` auto-retries like `updateOne`" | Can repeat multi-writes | Check operation eligibility |
| "All retryable writes try once across all drivers" | Wrong under `timeoutMS`/newer versions | Read version-specific docs |
| "Absence of `NoWritesPerformed` means written" | False conclusion | Absence proves nothing |
| "On body transient error, commit right away" | Transaction may have aborted | Separate transient body from unknown commit |
| "`UnknownTransactionCommitResult` = aborted" | Starts duplicate transaction | Retry commit on the same session |
| "Retrying commit = re-running callback" | Duplicate external effects | No |
| "`withTransaction` callback runs only once" | Duplicate emails/charges | Callbacks can replay |
| "MongoDB transaction rolls back payment gateways" | Broken distributed atomicity | Use outbox/saga/idempotency |
| "Aborting after unknown commit ensures no commit" | Wrong conclusion | Must reconcile |
| "`DuplicateKey` on retry means definite success" | Returns wrong request's result | Compare `requestHash` |
| "CAS `matchedCount=0` means already paid" | Misses other conflicts | Read the ledger |
| "Mint a new `ObjectId` on every retry" | Duplicate business records | Use deterministic keys |
| "Batch error means whole batch rolled back" | Overlooks partial writes | Reconcile per item |
| "Driver auto-retry suffices for exactly-once" | Side effects still duplicate | End-to-end idempotency |
| "Raising timeouts fixes root cause" | Masks replication pressure | Measure cluster/IOPS/lag |
| "Disable majority to stop alerts" | Loses durability | Fix root cause and review policy |
| "No need to persist `UNKNOWN` state" | Forgotten work | Durable reconciliation queue |
| "Test timeouts by shutting down prod secondary" | Causes real outage | Use controlled labs/fault injection |
| "Log full payloads to debug" | Leaks PII/secrets | Redacted structured logging |

## 31. Applied Exercises

### Exercise A — Write Concern Timeout

Scenario:

```text
Primary applied update at T1.
Secondaries were unreachable.
At T3, wtimeout=2000 ms returned a writeConcernError.
At T4, secondaries came back.
```

1. Can you say the update rolled back at T3?
2. Why must you not retry `$inc` as a new operation?
3. What does a majority read at T3/T4 reveal, and what does it not reveal?
4. If the primary fails over between T3 and T4, what must be checked?

### Exercise B — Network ACK Loss

```text
T0 insertOne(_id="A100")
T1 server applies insert
T2 success response lost
T3 client sees socket timeout
```

Design handling using a deterministic ID, `requestHash`, and readback. If a retry returns `DuplicateKey`, which conditions must be verified before treating it as success?

### Exercise C — Unknown Commit

A transaction updates `orders`, `ledger`, and `outbox`. `commitTransaction` returns label `UnknownTransactionCommitResult`.

1. Which operation do you retry?
2. Should you immediately re-run `session.withTransaction` body as a new transaction?
3. If the session is gone, how do you reconcile the collections?
4. If the outbox worker already sent a message, where is deduplication needed?

### Exercise D — Transient Transaction Error

An update inside a transaction hits `TransientTransactionError` before commit.

1. How does this differ from an unknown commit?
2. How might the callback be re-executed?
3. Why must you not call a charge API inside the callback?
4. What retry budget and idempotency are required?

### Exercise E — `$inc` and CAS

A `balance=1000` counter needs +500 for command `C-17`. The client times out after sending the update.

1. Why is retrying `$inc:500` unsafe?
2. Write a CAS filter using version and command ID.
3. If the CAS retry sees `matched=0`, what are the possible causes?
4. When is a transaction with a command ledger needed?

### Exercise F — API Status Endpoint

Design:

```text
POST /orders/A100/pay
Idempotency-Key: C-17
GET /operations/C-17
```

Specify responses for `CONFIRMED`, `REJECTED`, `NEEDS_RECONCILIATION`, duplicate same payload, and duplicate different payload.

### Exercise G — Batch Partial Success

A batch has 6 inserts and hits a network error partway through.

1. Can you retry the whole batch with random `ObjectId`s?
2. Which keys must be saved before sending?
3. If a retry reports duplicate key on one item, what do you check?
4. When is `NoWritesPerformed` helpful?

### Exercise H — Replica Set Health

```text
Primary CPU: 45%
Secondary disk w_await: 50 ms
Replication lag: 90 s
wtimeout errors: rising sharply
```

Diagnose likely causes, metrics to inspect, why raising primary CPU alone will not fix it, and safe load-shedding measures.

### Exercise I — Majority Read Misses Data

After `wtimeout`, a majority read does not yet find `requestId`.

1. Does this prove the request was definitely not written?
2. What if the write reaches majority commit moments later?
3. Which protocol prevents duplicate submission?
4. When is manual reconciliation required?

### Exercise J — Layered Timeouts

A request has:

```text
HTTP gateway: 3 s
Java operation timeout: 8 s
MongoDB wtimeout: 5 s
```

1. Why can the gateway return 504 while the backend keeps writing?
2. Which identity must HTTP retries preserve?
3. Which changes protect correctness?
4. Why does raising the gateway timeout not fix replication lag?

### Exercise K — Java Driver Labels

One exception carries:

```text
UnknownTransactionCommitResult
```

Another carries:

```text
TransientTransactionError
```

Write pseudocode handling each case separately, distinguishing Core API vs. Callback API.

### Exercise L — Ledger Atomicity

A service executes:

```text
insert ledger CONFIRMED
update order PAID
```

If it crashes between the two writes, what happens? Design a safer transaction or state-machine/reconciliation flow.

### Exercise M — Sharded Transaction

A transaction touches multiple shards and times out on commit. List the components to inspect, why `mongos`/coordinator affect latency, and how to read business state after an unknown commit.

### Exercise N — Rollback/Failover

A `w:1` write is acknowledged to the client by the primary, then the primary fails over and the write is absent on the new primary.

1. Does this contradict `w:1`?
2. How should write concern be chosen for payment flows?
3. Why is idempotency still required even with `majority`?
4. Do backups solve duplicate retries?

### Exercise O — Lab Without Breaking the Cluster

Design an integration test where a write succeeds yet **a fake timeout occurs at the application boundary**. Prove:

- The API does not return false success.
- Retries reuse `requestId`.
- CAS/updates do not increment version twice.
- Reconciliation reads the exact result.
- No duplicate external notifications fire.

### Exercise P — Postmortem

A system saw 200 timeouts in 10 minutes and 17 orders were double-charged. Write a postmortem covering timeline, write concern, retry path, idempotency gap, data repair, monitoring, ownership, and preventive steps.

## 32. Production Rollout Plan When Fixing Incidents

### 32.1. Before Changes

Record baselines:

- Unknown outcomes per operation.
- Rates of `wtimeout`, network timeouts, and unknown transaction commits.
- Effective write concern/driver settings.
- Replication lag, elections, disk latency, and journal sync.
- Idempotency key coverage.
- Duplicate business key counts.
- Operations awaiting reconciliation.
- Error budgets and business impact.

### 32.2. During Rollout

Generally safe sequence:

1. Instrument errors by phase and labels.
2. Disable unsafe retry paths via feature flags.
3. Deploy stable request IDs/ledgers.
4. Enable idempotent conditional writes/transaction outboxes.
5. Add bounded retries at the appropriate layer.
6. Enable reconciliation workers with clear ownership and rate limits.
7. Improve cluster health and capacity.
8. Observe a full business cycle before retiring legacy logic.

Never simultaneously change majority write concern, connection pools, retry policies, and transaction bodies without a way to isolate cause and effect.

### 32.3. When Rolling Back Code

An older app version may **not understand** the new request ledger/idempotency contract. Code rollbacks must not strip business key protections. If the old version is incompatible, roll forward or preserve a compatibility layer.

If `UNKNOWN` commands accumulated during deployment, keep processing them through the same reconciliation protocol—never wipe the pending queue just because "the release rolled back."

## 33. Official References and Version-Specific Verification Points

Key authoritative sources:

- [Write Concern — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j`, `wtimeout`, write concern errors, and rollback semantics.
- [Retryable Writes — MongoDB Manual](https://www.mongodb.com/docs/manual/core/retryable-writes/) — eligibility, retryable write identity, `NoWritesPerformed`, and timeout model.
- [Transactions — MongoDB Manual](https://www.mongodb.com/docs/manual/core/transactions/) — transaction-level concerns, commit behavior, and sharded coordination.
- [Handling Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — `TransientTransactionError` and `UnknownTransactionCommitResult`.
- [Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession`, `withTransaction()`, callback/core API.
- [Java Sync Driver Connection and Network Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/) — driver connection/timeout/retry settings.
- [Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/) — timeout/retry/write concern options, `wtimeoutMS` deprecation nuances.
- [Java Driver MongoException](https://mongodb.github.io/mongo-java-driver/) — error labels, exception subclasses, and version-specific Javadocs.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history, replication, rollback risks.
- [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/) — how non-majority writes can roll back.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — `local`/`majority`/`snapshot` read semantics.
- [Causal Consistency](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/) — read-your-writes across sessions.
- [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/) — ordered/unordered and partial success.
- [Server Status](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — replication and transaction metrics.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — monitoring managed cluster deployments.

**Version notes:** retryable write behaviors evolve across drivers and `timeoutMS`; `NoWritesPerformed` was introduced in MongoDB 6.1; `TransactionTooLargeForCache` in 6.2; majority acknowledgment and secondary apply behavior changed in MongoDB 8.0. Verify server version, FCV, driver, connection-string settings, and topology before modifying production.

## 34. Conclusion

A MongoDB timeout is not a boolean "succeeded" or "failed." It is a signal requiring **phase and evidence classification**:

1. **`wtimeout` does not auto-roll back** writes already applied on the primary. A write may reach majority after the client sees a write concern error, or roll back during failover if not yet majority-committed.
2. **Network/socket/client timeouts** can lose responses even when the server completed the work, so never blindly resend non-idempotent operations.
3. **`retryWrites=true`** protects eligible logical writes at the driver layer, yet cannot tell that two new HTTP requests represent the same business action.
4. **`UnknownTransactionCommitResult`** must be handled by retrying **the commit of the same transaction** while possible; **`TransientTransactionError`** can require retrying **the whole transaction** per driver/specification.
5. **Idempotency keys, unique constraints, CAS, ledgers, and transactional outboxes** bridge crash windows and systems outside MongoDB.
6. **Readbacks must account for durability.** Seeing a document does not prove majority ACK; not seeing one does not prove it cannot commit moments later.
7. **Bulk operations can partially succeed**; reconcile item by item via stable identities instead of assuming whole-batch rollback.
8. **Operational runbooks** must protect data correctness first, then resolve replication lag, disk, network, capacity, and timeout tuning.
9. When proof is lacking, the right state is **`UNKNOWN`/`NEEDS_RECONCILIATION`**—complete with owner, retry budget, check schedule, and audit trail—never a fabricated success or failure.

**Core principle:** when MongoDB reports a write concern timeout or an unknown commit outcome, **preserve business identity, prevent duplicate side effects, gather durable evidence, and confirm only after state is reconciled**. This foundation keeps systems accurate across network partitions, failovers, retries, deploys, and incident recoveries.
