# Write Conflicts, Operation Retries, and Idempotency Requirements in MongoDB

An order-processing application frequently encounters situations where two requests try to deduct stock simultaneously, two workers modify the same document concurrently, or a client resends a request because it never received a server response. Sometimes MongoDB returns a **write conflict** error; sometimes the operation wrote successfully but the response was lost; and sometimes no error appears at all, yet the application accidentally performs **a business effect twice**.

These three issues are related, yet **not the same**:

- **Write contention / write conflict:** concurrent operations cannot both execute under the observed history and expected consistency rules; one operation may need to abort and retry.
- **Retry:** a layer in the system re-executes a command after a transient error, timeout, or uncertain commit outcome.
- **Idempotency:** sending **the same business request** multiple times produces no additional side effects beyond executing it successfully once; the result can be reused or reconciled via a stable request key.

One key statement runs throughout this lesson: **MongoDB guarantees atomicity for a single write operation on a single document, but does not automatically guarantee that duplicate API calls produce a business effect only once.** Likewise, driver-level retryable writes do not mean every HTTP retry or re-execution of an entire business function is safe.

This lesson belongs to the **Atomicity and Concurrency** chapter of *Database Engine Document MongoDB*. Examples primarily use **mongosh**, with a **MongoDB Node.js Driver** sample illustrating transactions and idempotency keys. Commands writing to the `write_conflict_lab` database are for learning environments only. To test transactions, you need a MongoDB **replica set or sharded cluster supporting transactions**, not an ordinary standalone server. Exact error shapes and automatic retry levels depend on MongoDB version, driver, and deployment configuration.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish storage/transaction write conflicts from duplicate key errors, unmet business preconditions, and writes that modify zero documents.
2. Explain **single-document** atomicity, and why `find() → compute → update()` can suffer from race conditions.
3. Use `$inc`, conditional updates, and **optimistic concurrency with version** to update safely where appropriate.
4. Understand how MongoDB reports `WriteConflict`, `TransientTransactionError`, and `UnknownTransactionCommitResult` errors/labels, along with retry boundaries.
5. Distinguish **driver retryable writes**, **transaction retries**, and **application/API retries**.
6. Design a stable `Idempotency-Key` scoped by tenant/operation and bound to a payload fingerprint.
7. Use **unique index + request ledger + transaction** to apply a multi-document business change at most once.
8. Handle timeouts or lost responses without assuming the write never happened.
9. Avoid re-triggering external side effects outside MongoDB when a transaction callback is retried.
10. Apply backoff, retry budgets, metrics observability, concurrency testing, and idempotency key retention policies.

## 2. Four concepts to keep separate

| Concept | Question it answers | Example |
|---|---|---|
| **Atomicity** | Is a change applied as an indivisible whole? | Deducting stock and incrementing reserved in **the same document** |
| **Concurrency control** | Do two concurrent writers lose or overwrite each other's changes? | Two people editing draft version 7 |
| **Retryability** | After a transient error, under what protocol can a command run again? | A transaction aborted due to a write conflict |
| **Idempotency** | Does resending the same request cause a second effect? | Retrying a payment does not charge twice |

These properties complement one another. An `$inc` command is atomic and works well when multiple clients increment a counter, yet **two new `$inc` calls** increment the counter **twice**. A unique index blocks inserting duplicate business keys, yet does not automatically return the prior request's response when a client retries.

### 2.1. Lost response illustration

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant M as MongoDB
    C->>A: POST /reserve (requestId=R1)
    A->>M: Deduct 1 unit from stock
    M-->>A: Write succeeded
    A--xC: Response lost
    Note over C: Unsure whether stock was deducted
    C->>A: Resend POST /reserve, same requestId=R1
    Note over A: If run as a new $inc request, may deduct twice
~~~

MongoDB handled each operation properly. **The bug lies in the application retry design** when the resent request is not recognized as the same business request.

## 3. Race condition: read-then-write is not atomic

Suppose initial inventory is:

~~~javascript
{
  _id: "sku-A",
  tenantId: "t-01",
  available: 1,
  reserved: 0,
  version: 7
}
~~~

Two API calls both check stock availability:

~~~javascript
const item = db.inventory.findOne({ _id: "sku-A" })

if (item.available > 0) {
  db.inventory.updateOne(
    { _id: "sku-A" },
    { $inc: { available: -1, reserved: 1 } }
  )
}
~~~

Between `findOne()` and `updateOne()`, another request can decrement stock. If both A and B read `available = 1`, both decide the order is allowed and subtract one unit, resulting in **available = -1**. Each update is still atomic on the document, but **the stock check sat outside the write operation** and was no longer valid at write time.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as MongoDB
    participant B as Request B
    A->>DB: findOne(_id=sku-A)
    DB-->>A: available=1
    B->>DB: findOne(_id=sku-A)
    DB-->>B: available=1
    A->>DB: $inc available:-1
    DB-->>A: available=0
    B->>DB: $inc available:-1
    DB-->>B: available=-1
    Note over A,B: Both believed stock was available when reading earlier
~~~

### 3.1. Put the condition directly into the update command

~~~javascript
const result = db.inventory.updateOne(
  {
    _id: "sku-A",
    tenantId: "t-01",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1,
      reserved: 1
    }
  }
)

printjson({
  matchedCount: result.matchedCount,
  modifiedCount: result.modifiedCount
})
~~~

This is a **conditional atomic update**. When two operations compete for the last unit under normal conditions and all writers follow the same rule, only the operation that still sees `available >= 1` at execution time deducts stock. The other fails to match the filter and returns `matchedCount = 0`.

**Important:** `matchedCount = 0` **is not a `WriteConflict` error**. It is a normal business outcome: at the moment of update, no document satisfied the condition.

### 3.2. Guarding arbitrary quantities

For a request reserving `qty = 3`:

~~~javascript
const qty = 3

const result = db.inventory.updateOne(
  {
    _id: "sku-A",
    tenantId: "t-01",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      reserved: qty
    }
  }
)
~~~

The application must validate that `qty` is a positive integer within reasonable bounds before sending it to the database. A negative qty flips the sign of `$inc` and causes a business bug even though the query is syntactically valid.

### 3.3. Why isn't a conditional update enough for idempotency?

If inventory has 10 units and the same request `R1` is sent twice:

~~~text
Attempt 1: available 10 → 9, modifiedCount=1
Attempt 2: available  9 → 8, modifiedCount=1
~~~

Both attempts satisfy `available >= 1`. The update is atomic and never oversells stock, yet **the same request was applied twice**. To prevent that, bind the **request identity** to the operation or record it in a request ledger with a unique constraint.

## 4. Optimistic concurrency: updating by version

For a document where overwriting another user's edits must be avoided, use **version compare-and-swap**.

### 4.1. Lost update scenario

Document:

~~~javascript
{
  _id: "draft-001",
  tenantId: "t-01",
  title: "Draft",
  content: "Original content",
  version: 7
}
~~~

Editors A and B both read version 7. A edits title; B edits content but submits the whole old document. If the application uses `replaceOne({_id})` without checking version, B can overwrite the title A just edited.

### 4.2. Version-conditional update

~~~javascript
const expectedVersion = 7

const result = db.drafts.updateOne(
  {
    _id: "draft-001",
    tenantId: "t-01",
    version: expectedVersion
  },
  {
    $set: {
      title: "New title"
    },
    $inc: { version: 1 }
  }
)

if (result.matchedCount === 0) {
  print("CONFLICT: document version changed or not found")
}
~~~

When two clients both send `version: 7`, only the first advances version to 8; the second no longer matches. The API layer can return **HTTP 409 Conflict** or instruct the caller to reload to resolve the conflict.

**Never automatically retry the same old payload against the new version** if doing so could overwrite someone else's edits. Retrying here is a **business decision**: the user or app must merge, reload, or surface a conflict.

### 4.3. HTTP 409 is not MongoDB WriteConflict

When `matchedCount = 0` because version no longer matches, MongoDB typically **does not throw a write conflict error**. The API proactively produces HTTP 409 based on optimistic locking rules. Conversely, a transaction can be aborted by the server with a transient write conflict error/label even when no HTTP 409 was triggered.

## 5. What is a write conflict in MongoDB?

When concurrent operations touch the same data or index entries simultaneously, MongoDB uses concurrency control mechanisms in the storage engine and transaction layer. Some conflicts are handled internally by the server; others are **surfaced to the client**, particularly in multi-document transactions when the snapshot and conflicting writes cannot be reconciled in a valid schedule.

A typical error may carry:

~~~text
code: 112
codeName: "WriteConflict"
message: "... WriteConflict ..."
~~~

However, **do not rely solely on message text**. In practice, inspect the **error code** and especially **error labels** provided by the driver/server, since exact error shapes, locations, and labels vary across versions and operation types.

### 5.1. Where do write conflicts typically appear?

- Two transactions modify the same document while another transaction holds uncommitted changes.
- A transaction reads an older snapshot and tries to write to a document already modified by another transaction in a conflicting way.
- Concurrent write operations in certain index/transaction scenarios resulting in engine-level aborts.
- A transaction operation needs to be retried because of concurrency/failover or transient errors.

Not **every** concurrent update returns `WriteConflict`. For instance, two non-transactional requests calling `$inc` on the same counter are normally coordinated by MongoDB so each increment applies atomically; completion order depends on contention. Some storage-level conflicts are handled internally by the engine without necessarily surfacing to the application.

### 5.2. Write conflicts differ from unique-key conflicts

~~~javascript
db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true }
)
~~~

Two requests simultaneously inserting documents with the same `tenantId + operation + requestId` combination cause one request to receive a **duplicate key** error:

~~~text
code: 11000
codeName: "DuplicateKey"
~~~

This is an enforced **uniqueness constraint**, not the same as a `WriteConflict` error code 112. For a request ledger, a duplicate key may signal two requests using the same idempotency key; the application must inspect the existing record and compare payloads before deciding whether to replay.

### 5.3. Write concern and timeouts are also different

A command can:

1. Be applied on the primary.
2. Fail to return the desired replica set acknowledgment to the client.
3. Or have its response lost on the network.

In this case, never assume "the command failed so nothing was written." **The operation outcome may be uncertain** even though the client observed a timeout, network error, or write concern error.

## 6. Classification table for results and errors

| Scenario | Typical meaning | Appropriate retry/handling |
|---|---|---|
| `modifiedCount = 1` | Conditional update applied changes | Return success; store result if replay is needed |
| `matchedCount = 0` | No document matched filter/version/stock | Handle as a business outcome, not as transient |
| `WriteConflict` (e.g. code 112) | Operation/transaction hit write contention | For transient-labeled transactions, abort and retry **the whole transaction** per protocol |
| `TransientTransactionError` label | Transaction hit a transient condition | Retry the transaction body using a driver helper with backoff/budget |
| `UnknownTransactionCommitResult` label | Transaction commit outcome is unknown | Retry **commit**/reconcile by request ID; do not blindly re-run the side effect |
| `DuplicateKey` / E11000 | Unique index violation | Check which key collided, inspect ledger/business identity; never retry blindly |
| Validation error | Invalid payload/schema | Fix input; resending unchanged will not help |
| Insufficient stock | Available condition unmet | Return business outcome; do not duplicate orders |
| Network timeout after write | Write may already have succeeded | Use the same request ID to inspect/replay; do not create a new operation |
| Write concern timeout | Desired acknowledgment level not reached | State may be uncertain; inspect/reconcile |
| Transaction lifetime exceeded | Transaction ran too long / resource limits | Keep transactions short, handle errors properly, no infinite loops |

**Warning:** this table is a guide. A single error can carry multiple details, and retry decisions must consider **operation context + error labels + business contract**. Do not lump every error mentioning "conflict," "timeout," or "duplicate" into one `retry()` branch.

## 7. Three non-equivalent retry layers

~~~mermaid
flowchart TD
    User["Client sends request with stable ID"] --> HTTP["Application/API retry"]
    HTTP --> Logic["Business operation"]
    Logic --> Driver["Driver retryable write"]
    Driver --> Server["MongoDB"]
    Logic --> Tx["Transaction helper retry"]
    Tx --> Server
    Note["Request identity must survive across all retry layers"] -.-> HTTP
    Note -.-> Logic
~~~

### 7.1. Driver-level retryable writes

In supported topologies and versions, MongoDB drivers provide **retryable writes** for eligible write commands, typically bound to a session and write operation identity. The driver can retry on eligible network or transient errors without turning it into a **new logical write** under the retryable writes protocol.

However:

- Not all commands qualify for retryable writes; for instance, multi-document writes have different rules from single-document writes.
- Not all errors are automatically retried.
- Not all deployments enable or support it identically.
- A retried HTTP request can create a **brand-new driver operation** with a different identity.
- If a business function consists of multiple MongoDB commands and external side effects, retryable writes on individual commands **do not** make the entire function idempotent.

For example:

~~~javascript
// One driver invocation may be retried by the driver under supported mechanisms.
db.counters.updateOne(
  { _id: "views" },
  { $inc: { value: 1 } }
)
~~~

If **the application itself calls `updateOne()` a second time** after a timeout as a new operation, both invocations can increment the counter. Never cite "the driver has retryWrites=true" as proof that API-level behavior is idempotent.

### 7.2. Transaction retries

Multi-document transactions group multiple reads/writes into one commit scope. When a transaction hits a transient error such as a write conflict, the application may need to **abort and re-run the entire transaction body** on a fresh snapshot.

If the transaction already completed its body yet the **commit result is uncertain**, the right strategy may be **retrying the commit of that transaction**, not immediately starting a new business transaction.

Drivers provide helpers like `withTransaction()` or `withSession()` depending on language. Helpers implement transient/unknown commit label handling per the driver specification; you must still plan for when the helper throws a final error or exhausts its time limit.

### 7.3. Application and queue-level retries

An HTTP client, message broker consumer, or scheduler may resend the same work after a timeout, crash, or redelivery. This is a **business retry**; it can run in a different process, session, and transaction. To be safe, you need a stable idempotency key/identity **persisting across runs**.

For example:

~~~text
POST /reservations
Idempotency-Key: reservation-r-123

Body: { sku: "sku-A", qty: 1 }
~~~

If the client resends, the server must recognize this as **the same intent R123**, not a new reservation.

### 7.4. Application retries must be bounded

Even retryable operations require:

- A maximum attempt count or time budget.
- Exponential backoff with jitter.
- Overall timeout and request deadline.
- Distinguishing transient errors from permanent ones.
- Logging/metrics keyed by request ID without logging sensitive data.
- A circuit-breaker or dead-letter mechanism when work cannot complete.

Uncontrolled retries can trigger a **retry storm**, amplifying contention and making a struggling system fail harder.

## 8. Transactions and contention: why the whole body may re-run

Suppose we need to transfer 100 currency units between two accounts stored in two documents:

~~~javascript
// accounts
{ _id: "acc-A", balanceCents: 20000 }
{ _id: "acc-B", balanceCents: 5000 }
~~~

If debiting account A succeeds but the process dies before crediting account B, the data becomes unbalanced. A multi-document transaction helps both updates **commit together or abort together** on supported deployments.

### 8.1. Operations inside a transaction

~~~javascript
// Pseudocode for transaction body:
const debit = accounts.updateOne(
  { _id: "acc-A", balanceCents: { $gte: 10000 } },
  { $inc: { balanceCents: -10000 } },
  { session }
)

if (debit.matchedCount !== 1) {
  throw new Error("INSUFFICIENT_FUNDS")
}

accounts.updateOne(
  { _id: "acc-B" },
  { $inc: { balanceCents: 10000 } },
  { session }
)
~~~

This is **pseudocode**: real code must `await` with an async driver, verify the destination account exists, validate positive amounts, enforce authorization, and handle errors. A transaction needs an explicit commit and suitable write concern. Use integer smallest units such as cents or Decimal128 to avoid floating-point rounding errors.

### 8.2. Two transactions modifying the same account

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as MongoDB
    participant B as Transaction B
    A->>DB: Start snapshot and read acc-A
    B->>DB: Start snapshot and read acc-A
    A->>DB: Write acc-A
    B->>DB: Try writing acc-A concurrently
    DB-->>B: May raise WriteConflict / transient abort
    A->>DB: commit
    DB-->>A: success
    B->>DB: Retry new transaction, read fresh state
~~~

MongoDB does not allow two transactions to both assume they can commit over a conflicting update history. When B aborts, B's writes inside the transaction are not committed. Retrying the whole transaction must re-read current conditions and balances/stock; **never retain check results from an old snapshot**.

### 8.3. Why not retry just the last command?

If a transaction read data from an old snapshot, re-running only the failed update command while keeping decisions made from that stale snapshot can violate business invariants. When a transaction aborts due to a transient error, the right approach is to start (or let the helper start) a new transaction execution, **re-read data, re-verify conditions, and re-execute the whole body**.

### 8.4. Why transaction callbacks must avoid external side effects

A driver helper can invoke the callback multiple times:

~~~javascript
// AVOID inside a callback that may be re-executed:
await sendEmail("Transfer completed")
await chargeCardWithNewPaymentId()
await publishMessageWithoutDedupe()
~~~

If the transaction aborts after the email is sent, re-running the callback sends another email. A MongoDB transaction **does not roll back emails, HTTP APIs, payment gateways, or message brokers**.

To combine MongoDB changes with external side effects, see the **transactional outbox** pattern below.

## 9. Distinguishing `TransientTransactionError` and `UnknownTransactionCommitResult`

These two labels lead to two different strategies:

### 9.1. Transient error while the transaction body is running

An error labeled `TransientTransactionError` typically indicates the current transaction should be discarded and **the entire transaction retried** (per appropriate driver protocol).

~~~text
Transaction A:
  read stock
  update stock
  write ledger
  -> TransientTransactionError

Retry:
  start new transaction
  re-read stock
  update or reject based on current state
  write/replay ledger
  commit
~~~

During a retry, business conditions may have changed: stock was available before, now it is out of stock. That is expected behavior because retries must never rely on stale snapshots.

### 9.2. Uncertain commit result

In the situation:

~~~text
Client sends commitTransaction
MongoDB may have committed
Commit response is lost
~~~

the driver may attach the `UnknownTransactionCommitResult` label. **Never assume the transaction aborted** and start a brand-new business transaction with a new key.

Appropriate actions:

1. Use the **commit** retry mechanism for the same transaction while still in a valid driver/session context.
2. When indeterminate, query the **request ledger** using the stable identity.
3. Return an unknown/processing status per API contract until reconciled.
4. All API-level retries must preserve **the same idempotency key**.

### 9.3. Do not equate ACK with business truth

Observing a "timeout" does not prove MongoDB failed to commit; observing "retry request succeeded" does not prove external side effects ran only once. Maintain clear commitment boundaries:

- **MongoDB transaction**: scopes the MongoDB writes included in the transaction.
- **Idempotency ledger**: identifies one business request across multiple calls.
- **Outbox / consumer dedupe**: coordinates external effects outside MongoDB that can be delivered or received more than once.

## 10. Idempotency: exact definition

An operation `f` is called idempotent if applying the same intent again **produces no additional changes beyond the first successful application** within the defined contract.

~~~text
Set state: set status = "DONE"
  Resending multiple times keeps status DONE

Increment number: $inc counter by 1
  Sending new operations multiple times increments multiple times

Transfer 100,000 VND:
  Same requestId must transfer only once
  Two distinct requestIds can be two valid transfers
~~~

Idempotency **does not mean** all requests with the same body should be merged into one. If a user genuinely purchases **two identical items in two separate orders**, two valid intents must carry **two distinct request IDs**.

### 10.1. Distinguishing three types of keys

| Key type | Example | Role |
|---|---|---|
| Business identity | `orderId = ord-101` | Identifies a business entity |
| Idempotency/request identity | `requestId = R-abc` | Identifies one **operation intent** across retries |
| Driver retry identity | Session/transaction statement identity | Supports retrying one operation at the driver layer per MongoDB protocol |

These identities may relate to one another, but do not automatically substitute for each other. For an order-creation API, you might use a client-generated stable `orderId` as both business key and idempotency boundary, or store a separate request ID to replay responses.

### 10.2. Scope of an idempotency key

A client key could collide across two tenants or two endpoints:

~~~text
tenant=t-01, operation=RESERVE_STOCK, key=R1
tenant=t-02, operation=RESERVE_STOCK, key=R1
tenant=t-01, operation=CANCEL_ORDER,  key=R1
~~~

These three cases are three **valid distinct identities** if the API scopes by tenant + operation + key.

Apply the unique key over the exact scope, for example:

~~~javascript
db.request_log.createIndex(
  {
    tenantId: 1,
    operation: 1,
    requestId: 1
  },
  {
    unique: true,
    name: "uq_request_scope"
  }
)
~~~

`tenantId` must come from the authenticated context, not solely from a self-declared client body.

### 10.3. A key must not silently change payload

First call:

~~~text
key: R1
payload: { sku: "sku-A", qty: 1 }
~~~

Subsequent call:

~~~text
key: R1
payload: { sku: "sku-A", qty: 5 }
~~~

This is not a retry of the same intent. The API should report **IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD** or an explicit conflict response. To do this, store a **fingerprint** of the canonicalized payload, not just the key.

Canonicalization must define:

- Object field ordering does not affect meaning.
- Numeric types and Decimal128/int representations do not silently shift.
- Default values are normalized prior to hashing.
- Non-intent fields such as trace IDs or ancillary headers do not alter the fingerprint if the contract excludes them from business data.
- Operation and tenant belong to the identity scope.

An arbitrary `JSON.stringify` on any object **is not always canonical serialization**. For complex payloads, use a consistent canonicalization rule set shared across client/server and API versions.

## 11. Unique indexes: mandatory backstop against duplicate requests

The following code is **unsafe** under concurrency:

~~~javascript
const old = db.request_log.findOne({
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1"
})

if (!old) {
  // Two workers can both observe that key R1 does not exist yet.
  db.request_log.insertOne({
    tenantId: "t-01",
    operation: "RESERVE_STOCK",
    requestId: "R1"
  })
}
~~~

Two workers can both receive `null` from `findOne()` before either inserts. This is a **check-then-insert race**.

### 11.1. Use a unique index

~~~javascript
db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)
~~~

If two writers concurrently insert in the same scope, at most one record can exist; the other receives a duplicate key or transaction conflict error depending on the situation. **A unique index is the final line of defense**, independent of whether every application pre-checks.

### 11.2. Duplicate key errors must be interpreted accurately

Do not write:

~~~javascript
try {
  // insert request marker
} catch (err) {
  if (err.code === 11000) {
    return { success: true } // WRONG: unknown which key collided and what the prior request did.
  }
}
~~~

Instead:

1. Distinguish whether the duplicate key came from **the request-scope index** or another business index.
2. Read the request record by exact scope.
3. Compare fingerprints.
4. If already completed, return the stored result.
5. If the request is still processing, return pending/wait or perform bounded retry.
6. If payloads differ, return conflict **without applying a new effect**.

### 11.3. Creating a marker alone and updating business state outside is insufficient

~~~text
1. insert request marker R1 succeeds
2. process crashes before deducting stock
3. Retry sees marker R1 and returns "already processed"
~~~

This is a **lost effect**, even without duplication. Conversely:

~~~text
1. deduct stock
2. process crashes before writing request marker
3. Retry sees no marker and deducts stock a second time
~~~

This is a **duplicated effect**. If the marker and business update reside in **two documents** and must be consistent together, use a **multi-document transaction** or design a single-document atomic operation when feasible.

## 12. Request ledger and state machine

A ledger can store:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1",
  payloadHash: "sha256-canonical-payload",
  state: "COMPLETED",
  result: {
    ok: true,
    reservationId: "res-101",
    sku: "sku-A",
    qty: 1
  },
  createdAt: ISODate("2026-11-01T10:00:00Z"),
  completedAt: ISODate("2026-11-01T10:00:01Z")
}
~~~

For short operations inside one transaction, you can **insert the ledger record, update business data, and save the result in the same transaction**. The ledger record becomes visible only after commit if everything commits together; a transient `PROCESSING` state inside an uncommitted transaction is not visible as an "already issued lock" to other requests prior to commit.

### 12.1. Common states

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING: Claim request
    PROCESSING --> COMPLETED: Commit succeeded
    PROCESSING --> REJECTED: Rejected by business rule
    PROCESSING --> RETRYABLE: Transient error
    RETRYABLE --> PROCESSING: Retry same requestId
    PROCESSING --> UNKNOWN: Lost response / commit uncertain
    UNKNOWN --> COMPLETED: Reconcile finds outcome
    UNKNOWN --> RETRYABLE: Proven uncommitted
~~~

This is an **application state model**, not automatic states provided by MongoDB. How these states are persisted depends on design:

- With a **short transaction** saving marker and effect in one commit, external readers may only ever see terminal states `COMPLETED/REJECTED`.
- With a **long-running process** (calling a payment gateway, processing files), a persisted `PROCESSING` state with lease/heartbeat, recovery worker, and terminal states is typically needed.
- `UNKNOWN` means **outcome not yet known**, not failure, and does not permit re-executing under a new key.

### 12.2. Should business rejections be persisted?

Suppose request R1 is rejected due to out-of-stock. Later, stock is replenished and the client retries R1. If the contract defines "the same request always replays the same outcome," you must **store the OUT_OF_STOCK result** so subsequent retries return the same answer. If the contract allows retrying the decision after business conditions change, define a new key and clear rules; **never arbitrarily alter the meaning of the same requestId**.

A common approach: record state `REJECTED` and a stable response for terminal business rejections; never persist fake success for transient infrastructure errors.

### 12.3. Data stored in the ledger

Store sufficient fields:

- Scope: tenant, operation, requestId.
- Fingerprint/canonical payload or information needed to verify equivalence.
- State and result sufficient to replay the API contract.
- Created/affected business entity IDs.
- Timestamps, schema/API version, and attempt metadata as needed.

Avoid storing secrets or unnecessary sensitive payment payloads. The ledger itself must also have access controls, encryption/storage per policy, size monitoring, and a retention policy.

## 13. End-to-end design: reserving stock exactly once

Business requirement:

> The API accepts a request to reserve `qty` units of `sku`. Resending the same `tenantId + operation + requestId` must not reserve stock a second time and must return the previously processed result. Two distinct `requestId` values represent two independent reservation transactions.

Data:

~~~javascript
// inventory
{
  _id: "sku-A",
  tenantId: "t-01",
  available: 10,
  reserved: 0
}

// request_log
// Unique index on tenantId + operation + requestId
~~~

### 13.1. Transaction algorithm

~~~text
Input: authenticatedTenantId, requestId, sku, qty

Validate:
  qty is a positive integer within bounds
  sku is valid, tenant is authenticated
  requestId meets allowed format and length

Identity = (tenantId, "RESERVE_STOCK", requestId)
Fingerprint = SHA256(canonical({sku, qty}))

BEGIN TRANSACTION
  existing = request_log.findOne(Identity)
  if existing:
    if existing.fingerprint != Fingerprint: CONFLICT
    return existing.savedResult

  request_log.insertOne(Identity, Fingerprint, provisional state)

  updated = inventory.findOneAndUpdate(
    sku + tenant + available >= qty,
    $inc available -= qty, reserved += qty
  )

  if not found / insufficient stock:
    result = OUT_OF_STOCK
  else:
    result = RESERVED with stable reservationId

  request_log.updateOne(Identity, state=COMPLETED, result)
COMMIT TRANSACTION

Return savedResult
~~~

**Because inserting the ledger, updating inventory, and saving the result occur in one transaction**, a successful commit yields a consistent outcome for the business operation. If the transaction aborts, neither the ledger entry nor the stock deduction from that transaction commits.

### 13.2. Concurrent calls with the same requestId

~~~mermaid
sequenceDiagram
    participant A as Request A / R1
    participant B as Request B / R1
    participant DB as MongoDB
    A->>DB: Transaction insert ledger R1
    B->>DB: Transaction insert ledger R1
    Note over DB: Unique index allows only one R1 record
    A->>DB: Deduct stock and save result
    A->>DB: Commit
    DB-->>A: RESERVED
    DB-->>B: Duplicate key / conflict / transient abort
    B->>DB: Re-read ledger R1 once outcome is clear
    DB-->>B: Return saved result, no further deduction
~~~

Actual ordering depends on scheduling: the winner can flip, or one transaction can retry and see the committed record. **Do not assume the error will always be E11000**. The unique constraint and transaction form the guardrails; the application layer must handle error and uncertain-commit branches.

### 13.3. Concurrent calls with two different requestIds

~~~text
R1 reserves 1 unit of sku-A
R2 reserves 1 unit of sku-A
~~~

These are **two different intents** and must not be deduplicated merely for sharing SKU/qty. If stock is sufficient, both can succeed. If stock is insufficient, the conditional update prevents overselling; inside transactions, contention can raise a transient write conflict requiring a retry that re-checks current stock.

### 13.4. Storing OUT_OF_STOCK state

When out of stock, the transaction can still commit **the rejection ledger entry** without altering inventory:

~~~javascript
{
  ok: false,
  code: "OUT_OF_STOCK",
  sku: "sku-A",
  qty: 1
}
~~~

When the client resends the same R1 after inventory is restocked, the API replays the rejection result (if the contract adopts this semantics). To place a new order against the updated inventory, the client issues **a new request with a new requestId**.

## 14. Node.js Driver sample: ledger + transaction + conditional update

This example uses the modern MongoDB Node.js Driver in an environment supporting transactions. It illustrates the core processing pattern; production requires adding authentication, request tracing, error mapping, rate limiting, schema validation, and retention policies.

### 14.1. Index and initial data

Run in mongosh against `write_conflict_lab`:

~~~javascript
db.inventory.insertOne({
  _id: "sku-A",
  tenantId: "t-01",
  available: 10,
  reserved: 0,
  version: 1
})

db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)
~~~

### 14.2. Business handler function

~~~javascript
import { MongoClient } from "mongodb";
import { createHash } from "node:crypto";

// Use a replica set / sharded cluster connection string supporting transactions.
const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

const database = client.db("write_conflict_lab");
const inventory = database.collection("inventory");
const requests = database.collection("request_log");

class IdempotencyConflict extends Error {
  constructor() {
    super("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD");
    this.name = "IdempotencyConflict";
  }
}

async function reserveStock({
  tenantId,       // Taken from auth context.
  requestId,      // Kept stable by client across retries.
  sku,
  qty
}) {
  if (!tenantId || !requestId || !sku ||
      !Number.isSafeInteger(qty) || qty <= 0 || qty > 1000) {
    throw new Error("INVALID_INPUT");
  }

  const identity = {
    tenantId,
    operation: "RESERVE_STOCK",
    requestId
  };

  // With fixed payload {sku, qty}, key ordering is explicitly stable.
  // For general JSON payloads, use a consistent canonicalization library.
  const fingerprint = createHash("sha256")
    .update(JSON.stringify({ sku, qty }))
    .digest("hex");

  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      const previous = await requests.findOne(identity, { session });

      if (previous) {
        if (previous.fingerprint !== fingerprint) {
          throw new IdempotencyConflict();
        }
        return previous.result;
      }

      await requests.insertOne({
        ...identity,
        fingerprint,
        state: "PROCESSING",
        createdAt: new Date()
      }, { session });

      const updated = await inventory.findOneAndUpdate(
        {
          _id: sku,
          tenantId,
          available: { $gte: qty }
        },
        {
          $inc: {
            available: -qty,
            reserved: qty,
            version: 1
          }
        },
        {
          session,
          returnDocument: "after",
          projection: {
            _id: 1,
            available: 1,
            reserved: 1
          }
        }
      );

      const result = updated === null
        ? {
            ok: false,
            code: "OUT_OF_STOCK",
            sku,
            qty
          }
        : {
            ok: true,
            code: "RESERVED",
            sku,
            qty,
            remaining: updated.available
          };

      await requests.updateOne(
        identity,
        {
          $set: {
            state: "COMPLETED",
            result,
            completedAt: new Date()
          }
        },
        { session }
      );

      return result;
    }, {
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });
  } catch (error) {
    // Post-transaction handling: never assume error = uncommitted.
    // A colliding key, unknown commit result, or network error
    // must be reconciled by identity before deciding the API outcome.
    if (error.code === 11000 ||
        error.hasErrorLabel?.("UnknownTransactionCommitResult")) {
      const existing = await requests.findOne(identity);
      if (existing) {
        if (existing.fingerprint !== fingerprint) {
          throw new IdempotencyConflict();
        }
        if (existing.state === "COMPLETED") {
          return existing.result;
        }
      }
    }

    // Unknown outcome or unrecovered error: let API layer report
    // appropriate status / retry with the same key within budget.
    throw error;
  } finally {
    await session.endSession();
  }
}

// At application shutdown, close the client with await client.close().
~~~

### 14.3. Explaining key points

1. **Stable identity:** `tenantId + operation + requestId` is used to read/write the ledger. The unique index prevents two records with the same identity.
2. **Fingerprint:** detects a client reusing a key with a different payload. The example uses fixed key ordering; production needs general canonicalization for complex payloads.
3. **Transaction:** the marker, stock update, and result commit together.
4. **Conditional update:** `available >= qty` is checked right inside the write command, preventing overselling.
5. **Replay:** if the ledger already committed, duplicate requests return `previous.result` without further deducting stock.
6. **Transaction retry:** `withTransaction` can re-run the callback on transient errors per driver protocol; the callback **calls no external services**.
7. **Unknown outcome:** catch does not assume every exception means abort; if no record is visible yet, never mint a new key and blindly retry the operation.
8. **Out of stock:** the `OUT_OF_STOCK` result is also persisted, giving stable replay semantics.

### 14.4. Limitations of the snippet

- The snippet **does not replace** a complete service; it requires a valid connection URI and a deployment supporting transactions.
- `findOneAndUpdate` return shape depends on the Node driver API version; the code above assumes a modern driver returning the document or `null` directly by default, rather than an older wrapper object with `value`.
- If a duplicate key happens due to another racing transaction that has **not yet committed**, an immediate ledger read may not see the record yet; bounded retry/reconciliation is needed. Never conclude "key not seen so re-insert under a new key."
- For uncertain commit results, the driver helper may already have retried commit; if it still throws, handle it at the API layer per the `UNKNOWN/PENDING` contract and use the same requestId for follow-up queries.
- A transaction can abort due to infrastructure faults, exceeded lifetime, or contention; never pull HTTP calls, emails, or payment gateways into the callback.
- Using `_id = sku` in the example assumes SKUs are globally unique across the collection. If in reality `sku` is unique only **within a tenant**, document keys must be designed to avoid cross-tenant collisions (e.g., tenant-namespaced `_id` or a compound unique key).
- If a stable **reservationId** is required, derive/define it deterministically from requestId and store it in result within the same transaction; never generate a fresh ID on each replay.

## 15. When modifying only one document: avoid transactions when unnecessary

Transactions are useful for synchronizing **multiple documents**. When an operation can be expressed as a single atomic update on **one document**, that approach is simpler and cheaper.

For example, a job counter allowing the same request ID to increment only once:

~~~javascript
db.job_counters.insertOne({
  _id: "job-1",
  completed: 0,
  appliedRequestIds: []
})
~~~

Operation:

~~~javascript
const requestId = "R1"

const result = db.job_counters.updateOne(
  {
    _id: "job-1",
    appliedRequestIds: { $ne: requestId }
  },
  {
    $inc: { completed: 1 },
    $addToSet: { appliedRequestIds: requestId }
  }
)
~~~

The filter verifies requestId **has not yet appeared**, while `$inc` and `$addToSet` occur inside **the same single-document update**. Sending R1 twice normally matches only the first time; the second yields `matchedCount = 0`.

### 15.1. Important limitations

- The `appliedRequestIds` array grows with request volume, potentially making the document very large and creating contention/a hot document.
- The 16 MiB BSON limit and array maintenance cost make this pattern **unsuitable for unbounded request history**.
- Replaying complex response bodies still requires somewhere to store results.
- If callers must distinguish an already-used request from another unmatched condition, appropriate readback is required.

This pattern is helpful for **small scopes, bounded key counts**, or short processing windows. For systems handling millions of requests, a separate ledger usually manages retention and scale better.

### 15.2. Are `$set` and `$addToSet` always idempotent?

~~~javascript
db.orders.updateOne(
  { _id: "ord-1" },
  { $set: { status: "PAID" } }
)
~~~

Usually produces an idempotent effect regarding **the status field state** when repeating the same value. However, if the operation also triggers an email, audit event, or updates an external counter, the overall workflow is not necessarily idempotent.

~~~javascript
db.orders.updateOne(
  { _id: "ord-1" },
  { $addToSet: { tags: "vip" } }
)
~~~

`$addToSet` avoids adding **the same element to an array** multiple times per element equality rules, yet does not solve every business intent, oversized arrays, or objects with differing structures. Idempotency must be defined at the whole-operation level, not just for one operator.

## 16. Why do `$inc` retries require special care?

`$inc` is commonly used to:

- Increment view/event counts.
- Deduct stock.
- Credit/debit balances.
- Increment attempt counters.
- Maintain state counters.

It is atomic when mutating a single document, yet **not idempotent if executed as two new invocations**.

### 16.1. "Approximate" counters

An analytics counter not requiring strict exactness may accept at-least-once semantics or eventual reconciliation. Still, document expected accuracy; never use this model for money or strict inventory limits.

### 16.2. Counters requiring exactness

For example, confirming delivery:

~~~text
Request R1: confirm a package was delivered
Business effect: increment deliveredCount exactly once
~~~

If request R1 can be redelivered, tie a stable identity to package state or a request ledger:

~~~javascript
db.packages.updateOne(
  {
    _id: "pkg-101",
    status: { $ne: "DELIVERED" }
  },
  {
    $set: { status: "DELIVERED" }
  }
)
~~~

If a warehouse-wide counter must also increment **at the same time** as changing the package state in another document, consider a transaction or event/outbox + dedupe/reconciliation. Retrying `$inc` directly on the warehouse counter after a timeout easily leads to double counting.

### 16.3. Distinguish "repeated command" from "repeated intent"

~~~text
Same payload: increase counter by 1
  Different R1 and R2 => two valid increments
  R1 sent twice        => only one increment if contract is idempotent
~~~

You cannot infer whether two requests with identical payloads are duplicates without a request identity.

## 17. Write conflicts and bounded backoff

When many workers write to the same hot document, immediate synchronized retries can create a **thundering herd**:

~~~text
100 workers hit transient conflict
100 workers retry immediately
Collide on the hot document again
Many workers keep retrying
~~~

### 17.1. Backoff strategy

A reference formula:

\[
\mathrm{delay} = \min(\mathrm{cap}, \mathrm{base}\cdot 2^{\mathrm{attempt}})\times\mathrm{jitter}
\]

Where `jitter` is a bounded random factor so workers do not retry in lockstep. For example, base 20 ms, cap 1,000 ms; applications must also enforce a **total maximum duration**, not just an attempt count.

### 17.2. Retry pattern outside helpers

~~~javascript
// Pseudocode: use when the operation/driver layer does not already retry
// the relevant transient errors. Never wrap in an infinite retry loop.
async function retryTransient(operation, maxAttempts = 4) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (error) {
      const transient = error.hasErrorLabel?.("TransientTransactionError");
      if (!transient || attempt === maxAttempts - 1) {
        throw error;
      }

      const exponential = Math.min(1000, 20 * (2 ** attempt));
      const jitter = 0.5 + Math.random();
      const delay = Math.floor(exponential * jitter);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
~~~

This is an **illustrative pattern**, not advice to wrap every `withTransaction()` indiscriminately without checking what the helper already retries. Some drivers already retry the transaction body/commit by error label. Stacking multiple retry layers can inflate attempt counts unexpectedly. For `UnknownTransactionCommitResult`, **do not** mechanically apply the same whole-operation retry logic.

### 17.3. Classify errors before retrying

Never retry blindly:

- `DuplicateKey` on a unique business key — reconcile key and intent.
- Payload validation — resending unchanged will fail again.
- Out of stock — do not assume inventory will magically appear immediately.
- Version mismatch — requires business conflict resolution.
- Authorization failure — retrying does not grant permissions.
- Unknown commit outcome — retry commit or reconcile first.

### 17.4. Reduce contention before increasing retries

Backoff relieves pressure, yet the root fix may be:

- Shortening transaction duration and reducing the number of documents touched.
- Moving hot counters to a lower-contention model when requirements allow.
- Partitioning workloads by tenant/key or queuing writes.
- Batching sensibly, avoiding having many requests update one global document.
- Moving long-running tasks out of transactions.
- Tuning indexes/filters so transactions touch fewer documents.

Retries provide **resilience**, not a substitute for concurrency design.

## 18. Write concern, read concern, and durability

### 18.1. Atomicity does not mean majority durability

An atomic single-document update is still acknowledged according to a specific write concern. In a replica set:

- `w: 1` typically acknowledges from the primary per configuration.
- `w: "majority"` requests majority acknowledgment per deployment semantics, impacting latency and survival across failovers.
- Journal/durability and commit visibility also depend on storage/replica set configuration.

For high-value operations, define **acceptable failover data-loss tolerance**, rather than relying merely on receiving a client ACK.

### 18.2. Read concern when reconciling the ledger

After an uncertain commit outcome, an application might read the ledger to verify. If reading from a lagging secondary or using an unsuitable read preference/read concern, **not seeing the record immediately** does not prove the transaction failed to commit.

When reconciliation is needed, choose read semantics aligned with system consistency, prefer a source capable of observing committed state reliably, and perform bounded **verification** retries rather than immediately issuing a new side effect.

### 18.3. Write concern errors are not business rejections

If MongoDB returns a write concern timeout, the application must never treat it as equivalent to `available < qty`. One is **unachieved/uncertain write acknowledgment**, while the other is **an unmet business condition**.

Mixing the two states causes severe bugs: customers see "out of stock" even though stock was deducted, or the system retries a new transaction and deducts stock twice.

## 19. Transactional outbox: idempotency for external side effects

Suppose after reserving stock, the system must emit a `StockReserved` event to another service. Calling the message broker directly inside the transaction callback risks re-running and emitting duplicates; furthermore, the broker does not participate in the MongoDB commit.

### 19.1. Outbox pattern

In **the same transaction** as inventory and ledger:

~~~javascript
// Pseudocode inside MongoDB transaction:
inventory.updateOne(/* conditional stock deduction */, { session })
request_log.insertOne(/* identity + result */, { session })
outbox.insertOne({
  _id: "event-R1",
  type: "StockReserved",
  requestId: "R1",
  tenantId: "t-01",
  sku: "sku-A",
  qty: 1,
  status: "PENDING",
  createdAt: new Date()
}, { session })
~~~

**No network publishing inside the transaction callback.** A worker outside the transaction reads committed outbox entries, publishes events, and marks them sent.

~~~mermaid
flowchart LR
    API["API reserve R1"] --> TX["MongoDB transaction"]
    TX --> DB1["inventory"]
    TX --> DB2["request ledger"]
    TX --> DB3["outbox event-R1"]
    DB3 --> Worker["Outbox relay"]
    Worker --> Broker["Message broker"]
    Broker --> Consumer["Consumer dedupe event-R1"]
~~~

### 19.2. Outbox can still deliver duplicates

The worker can:

1. Publish the event successfully.
2. Crash before marking the outbox entry SENT.
3. Restart and publish the same event again.

Hence outbox typically delivers **at-least-once**; consumers must deduplicate by `eventId` or a stable business key, usually backed by a unique index/ledger on the receiving side. Never claim outbox alone gives "end-to-end exactly-once."

### 19.3. External payment APIs

When calling a payment gateway, if the provider supports an **idempotency key**, pass a stable key tied to the intent and store the mapping between internal request ID and external charge ID. For providers without idempotency support, design dedicated reconciliation/deduplication. A MongoDB transaction cannot roll back funds already captured by an external provider.

### 19.4. Never generate a random event ID on each retry

If request R1 is resent and the application generates `event-Random2` instead of `event-R1`, consumers will treat them as two independent events. Event identity must be deterministically bound to the business operation when deduplication is required.

## 20. TTL and idempotency key retention policies

A request ledger grows with request volume. TTL can clean up records that do not need permanent retention, yet **deleting a ledger entry removes duplicate-protection proof for that prior window**.

### 20.1. Reference TTL index

~~~javascript
db.request_log.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_request_expiration" }
)
~~~

Each ledger record can carry `expiresAt`. The TTL monitor deletes expired documents **non-instantaneously**; cleanup runs with background delay per MongoDB mechanics. TTL is a retention tool, not a millisecond-accurate business deadline lock.

### 20.2. Retry horizon

If clients can retry for 48 hours while the ledger expires after 1 hour, the same key can be treated as a new request and take effect a second time.

Retention should be at least as long as **the committed retry window** plus recovery/replay/queue lag, or backed by a more durable business identity preventing duplicates.

### 20.3. When should you not rely solely on TTL?

For invoices, payments, order confirmations, or money transfers requiring long-term auditability, business keys/transaction records may have to be retained under accounting/legal requirements. A short-lived request ledger can support API replay, but **does not replace** durable uniqueness constraints on business entities.

### 20.4. TTL and in-flight transactions

Never set expiration so short that records awaiting reconciliation get deleted before outcomes are resolved. Separate retention policies for terminal records versus in-flight/unknown requests, or set `expiresAt` only once safe to purge.

## 21. Sharding, unique indexes, and hot keys

On a sharded cluster, unique indexes have specific constraints regarding shard keys and uniqueness scope. Do not assume any arbitrary compound unique index is enforced cluster-wide like on an unsharded collection. When designing a ledger on a sharded collection:

- Define shard keys, tenant scope, and request ID distribution.
- Check **unique index rules** for sharded collections for your MongoDB version.
- Avoid partitioning schemes where two records with the same business identity can land outside unique-constraint protection.
- Evaluate distributed transactions if inventory, ledger, or outbox reside on different shards.
- Avoid a single cluster-wide hot counter document if every request writes to it and causes heavy contention.

For financial/stock domains, correctness of **unique identity + atomic transaction + routing** outweighs raw throughput micro-optimizations.

### 21.1. Cross-shard transactions

A multi-document transaction on a sharded cluster adds coordination cost compared to a single-document update. At scale, you can:

- Co-locate related documents using a suitable shard key when the data model allows.
- Use atomic single-document updates for invariants confined to one document.
- Bound transaction duration and number of documents touched.
- Choose outbox/saga flows when workflows span multiple services that cannot share one MongoDB transaction.

**Never treat transactions as free**, and never wrap long network calls inside them.

## 22. From write conflicts to HTTP contracts

The API should distinguish:

| Scenario | Candidate HTTP status | Response should include |
|---|---|---|
| First request succeeds | `200`/`201` | Result and business ID |
| Retry with same key and payload, completed | Same stored response semantics | Replayed result, no second side effect |
| Reused key with different payload | `409 Conflict` | `IDEMPOTENCY_KEY_REUSED` code |
| Insufficient stock, terminal outcome | `409` or `422` per API | `OUT_OF_STOCK` code stored for replay if contract requires |
| Transient transaction exceeds retry budget | `503` or appropriate transient error | Retry with same key, do not mint a new key |
| Commit/outcome unknown | `202 Accepted`/pending or clear transient error | Request ID and how to check status |
| Invalid payload | `400`/`422` | Validation errors |
| Unauthorized user | `403`/`404` per policy | Do not disclose unauthorized resources |

These are **API design choices**, not mandatory MongoDB HTTP codes. An API may return `409` for version conflicts or business rejections, yet should include a **machine-readable code** so clients do not confuse them with transient database conflicts.

### 22.1. APIs can expose a request lookup endpoint

~~~http
POST /reservations
Idempotency-Key: R1

GET /operations/R1
~~~

The status lookup endpoint must be scoped by principal/tenant so knowing a request ID does not reveal another user's results. When a client loses a response, it should **poll status or resend the same key**, never send a new key to "make sure it goes through."

### 22.2. Never report success when uncertain

If the process does not know whether the transaction committed, never return:

~~~javascript
{ ok: true, reservationId: "res-new" }
~~~

without evidence. Nor return "failed, safe to retry with a new key" if the prior request might still commit. An **UNKNOWN/PENDING state with reconciliation** is far better than a false assertion.

## 23. Observability and operations

Useful metrics:

| Metric | Purpose |
|---|---|
| `write_conflict_count` | Detect contention in transactions/write paths |
| `transaction_retry_count` | Measure transaction re-execution frequency |
| `unknown_commit_count` | Track uncertain commit states and reconciliation |
| `idempotency_replay_count` | Rate of valid duplicate request replays |
| `idempotency_payload_conflict_count` | Detect keys reused for different intents |
| `duplicate_key_count` by index | Distinguish expected dedupe from business data errors |
| `request_pending_age` | Spot stuck requests |
| `hot_document_update_latency` | Observe contention on hot stock/counters |
| `outbox_delivery_attempts` | Track event redelivery and consumer dedupe |
| `p95/p99 operation latency` | Measure retry impact on SLOs |

Not all metrics exist verbatim inside MongoDB; many require **application instrumentation**, while others come from server metrics, profiler, or diagnostic logs depending on version.

### 23.1. Minimum log fields per request

~~~text
traceId=...
tenantId=t-01
operation=RESERVE_STOCK
requestId=R1
attempt=2
transactionOutcome=COMMITTED|ABORTED|UNKNOWN
replayed=true|false
errorCode=...
errorLabels=[...]
durationMs=...
~~~

Avoid logging sensitive data (tokens, card numbers, full payloads). If client-supplied request IDs could contain sensitive data, enforce format/length rules or use server-issued safe IDs.

### 23.2. Alerts worth considering

- Sudden spike in conflict/retry rate after deployment.
- Rate of unknown/pending requests failing to reach terminal states.
- Negative stock or anomalous counters despite business invariants.
- Duplicate scope records in ledger (impossible if unique constraint is intact).
- Growing outbox backlog and rising consumer duplicate rate.
- Rising transaction latency and high transaction abort counts.
- TTL expiring too early or ledger storage exceeding budget.

## 24. Lab: atomicity, optimistic concurrency, and retries

This lab modifies **lab data only**. To observe real transaction write conflicts, use a MongoDB replica set/sharded cluster supporting transactions. Concurrent operations are not guaranteed to emit the exact same error code every run: outcomes depend on scheduling, locking, and driver behavior.

### 24.1. Initialization

~~~javascript
use write_conflict_lab

db.inventory.insertOne({
  _id: "sku-lab",
  tenantId: "t-01",
  available: 2,
  reserved: 0,
  version: 1
})

db.request_log.createIndex(
  { tenantId: 1, operation: 1, requestId: 1 },
  { unique: true, name: "uq_request_scope" }
)

db.drafts.insertOne({
  _id: "draft-lab",
  tenantId: "t-01",
  title: "Initial draft",
  version: 1
})
~~~

Run setup only once on an empty lab database; repeating the same `_id` causes duplicate key errors.

### 24.2. Exercise A — Conditional stock update

~~~javascript
const qty = 1

const result = db.inventory.updateOne(
  {
    _id: "sku-lab",
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      reserved: qty
    }
  }
)

printjson(result)
printjson(db.inventory.findOne({ _id: "sku-lab" }))
~~~

Execute three times consecutively. Predictions:

~~~text
Initial:   available=2, reserved=0
Run 1:     available=1, reserved=1, modifiedCount=1
Run 2:     available=0, reserved=2, modifiedCount=1
Run 3:     available=0, reserved=2, matchedCount=0
~~~

Explain why stock never goes negative, yet **the first two runs could still be a duplicated effect** if they share the same requestId.

### 24.3. Exercise B — Optimistic concurrency

~~~javascript
const before = db.drafts.findOne({ _id: "draft-lab" })

const updateA = db.drafts.updateOne(
  {
    _id: "draft-lab",
    version: before.version
  },
  {
    $set: { title: "Editor A" },
    $inc: { version: 1 }
  }
)

const updateB = db.drafts.updateOne(
  {
    _id: "draft-lab",
    version: before.version
  },
  {
    $set: { title: "Editor B" },
    $inc: { version: 1 }
  }
)

printjson({
  a: updateA.matchedCount,
  b: updateB.matchedCount
})
~~~

Because both use `before.version = 1`, expected sequential outcome:

~~~text
A matchedCount=1
B matchedCount=0
Final doc: title="Editor A", version=2
~~~

This is a **business version conflict**, not necessarily a MongoDB `WriteConflict` error.

### 24.4. Exercise C — Unique request key

~~~javascript
const identity = {
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1"
}

db.request_log.insertOne({
  ...identity,
  payloadHash: "hash-for-sku-lab-1",
  state: "COMPLETED",
  result: { ok: true, sku: "sku-lab", qty: 1 }
})

// Intentionally repeat insert with the same identity:
db.request_log.insertOne({
  ...identity,
  payloadHash: "hash-for-sku-lab-1",
  state: "COMPLETED"
})
~~~

The second command is expected to fail with a duplicate key error. Explain why this error **is not enough** to prove business stock was updated if the marker and stock update are not inside the same transaction.

### 24.5. Exercise D — Request key with differing payload

~~~javascript
const old = db.request_log.findOne({
  tenantId: "t-01",
  operation: "RESERVE_STOCK",
  requestId: "R1"
})

const incomingHash = "hash-for-sku-lab-5"

if (old && old.payloadHash !== incomingHash) {
  print("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD")
}
~~~

Goal: distinguish **retrying the same intent** from **reusing a key for a new intent**. In production, fingerprint must be a real hash of the canonical payload, not an illustrative string.

### 24.6. Exercise E — Observing transaction write conflicts

Run on a lab replica set using two mongosh sessions. Each starts a transaction and tries modifying **the same document** before either commits.

**Session A:**

~~~javascript
use write_conflict_lab
const sessionA = db.getMongo().startSession()
const txDbA = sessionA.getDatabase("write_conflict_lab")
sessionA.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

printjson(txDbA.drafts.findOne({ _id: "draft-lab" }))

txDbA.drafts.updateOne(
  { _id: "draft-lab" },
  { $set: { title: "Transaction A" } }
)

// Hold before committing so Session B contends.
~~~

**Session B (while A is still open):**

~~~javascript
use write_conflict_lab
const sessionB = db.getMongo().startSession()
const txDbB = sessionB.getDatabase("write_conflict_lab")
sessionB.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

printjson(txDbB.drafts.findOne({ _id: "draft-lab" }))

try {
  printjson(txDbB.drafts.updateOne(
    { _id: "draft-lab" },
    { $set: { title: "Transaction B" } }
  ))
} catch (e) {
  printjson({
    code: e.code,
    codeName: e.codeName,
    errorLabels: e.errorLabels,
    message: e.message
  })
  try { sessionB.abortTransaction() } catch (_) {}
}
~~~

**Back to Session A:**

~~~javascript
try {
  sessionA.commitTransaction()
} finally {
  sessionA.endSession()
}
~~~

**Clean up Session B** if its transaction is still active:

~~~javascript
try { sessionB.abortTransaction() } catch (_) {}
sessionB.endSession()
~~~

In practice, Session B can encounter a write conflict/transient error when modifying a document already written by A in an uncommitted transaction. This depends on timing; if sessions do not overlap, outcomes differ. Do not assert that every run must produce exact code 112. If a transaction aborts, **retry a new transaction**, never continue committing the broken session state.

### 24.7. Exercise F — Lost response

Logical simulation:

~~~text
Request R2 sent to API
Transaction ledger + stock commit
Server drops connection before returning JSON
Client retries R2 after 5 seconds
~~~

Design the response: the server looks up the ledger by scope, checks fingerprint, and returns the stored result; **never invoke `$inc` again** as a new intent.

### 24.8. Exercise G — External side effect

Inside a transaction callback sits the mock call:

~~~javascript
await sendEmail("Reserved")
~~~

Explain what happens if the callback is re-executed after a transient error; fix the design using a transactional outbox and consumer deduplication.

### 24.9. Exercise H — Retry budget

A transaction experiences four consecutive transient errors. Design a retry schedule with backoff/jitter, overall deadline cap, attempt logging, and fallback when budget is exhausted. Why not immediately retry 1,000 times on a hot document?

### 24.10. Exercise I — TTL

The API allows clients to retry the same requestId for 72 hours, but ledger TTL is only 24 hours. What can happen at hour 50? Propose a more durable retention policy and business uniqueness safeguard.

## 25. Guided answers

**Exercise A:** The first two runs are two valid atomic updates looking only at stock. If they were retries of the same R1, the system deducted twice: conditional updates solve overselling, **not idempotency**. The third run lacks stock so matchedCount=0.

**Exercise B:** A sets version to 2, B uses the stale version so matchedCount=0. The API can return a version conflict asking to reload or merge, without necessarily hitting a WriteConflict error.

**Exercise C:** The unique index blocks two ledger records in the same scope. If the marker is written separately from stock, crashing between steps still causes lost or duplicate effects. Use a transaction or single-document design.

**Exercise D:** A key with a differing hash is an **intent conflict**, not a valid retry. Return an explicit error code without touching inventory.

**Exercise E:** Transactions can hit write conflicts when two sessions modify the same document. On transient abort, re-run **the entire transaction** on a fresh snapshot; on uncertain commit outcome, retry commit/reconcile.

**Exercise F:** If the ledger committed, replay R2's response. If the outcome is uncertain, keep the requestId and reconcile; never submit a new key to avoid double reservation.

**Exercise G:** Callback retries can send multiple emails. Write the outbox entry in the same transaction; relay publishes externally, consumer deduplicates by stable event ID.

**Exercise H:** Backoff+jitter reduces retry storms. Deadlines/budgets prevent holding requests and resources indefinitely; afterward return a status instructing retry with the same key or hand off to recovery.

**Exercise I:** If the ledger is purged after 24 hours, a retry at hour 50 can be treated as a new request. Choose retention longer than the retry horizon, plus durable business-entity uniqueness where needed.

## 26. Common mistakes

| Mistake | Why is it dangerous? | Fix |
|---|---|---|
| Treating atomic `$inc` as idempotent | Two new invocations increment twice | Stable request ID + ledger or same-document guard |
| Reading stock then updating by `_id` | Stock condition can become stale | Put `available:{$gte:qty}` in the atomic filter |
| Treating `matchedCount=0` as WriteConflict | Confuses business outcome with storage error | Separate version/stock conflicts from transient errors |
| Retrying every error containing "conflict" | Duplicate/validation/version errors do not self-heal | Classify code, label, and business meaning |
| Retrying unknown commit with a new transaction and new key | Can apply the effect twice | Retry commit/reconcile, keep the same key |
| Omitting unique index on ledger | Two workers can both insert | Unique index on the exact scope |
| Only checking ledger then inserting | Check-then-insert race | Unique constraint and transaction |
| Inserting marker then updating stock outside transaction | Crash leaves half-finished state | Same transaction or same document |
| Deducting stock then writing ledger separately | Crash before marker causes retry to deduct twice | Transaction |
| Retrying transaction body containing email/payment calls | External side effects do not roll back | Outbox/external idempotency |
| Reusing one key with a different payload | Wrong intent replay | Fingerprint + conflict |
| Deduplicating every request with the same body | Wrongly drops two valid orders | Distinguish by request IDs |
| Ledger TTL shorter than retry window | Old key treated as brand new | Adequate retention or durable business identity |
| Reading stale ledger then concluding uncommitted | Commit may not yet be visible | Appropriate consistency/reconciliation |
| Enabling infinite retries | Retry storms, contention, and timeouts | Budget + exponential backoff + jitter |
| Assuming transaction covers broker/payment | No atomic commit across external systems | Outbox/saga/consumer dedupe |
| Using a unique index incompatible with shard key | Constraint may not enforce as expected | Proper sharding and unique scope design |
| Logging full sensitive payloads/IDs | Data exposure risk | Minimal logging, masking |

## 27. Review questions

**1. What is a write conflict?**

A write contention situation where an operation/transaction cannot proceed or commit under a consistent history accepted by the engine, causing an abort/error and requiring a retry at the proper layer.

**2. Do all concurrent updates return WriteConflict?**

No. Many single-document updates are coordinated/serialized atomically by the engine; some conflicts appear only inside transactions. Never assume an error occurs solely because two requests arrive simultaneously.

**3. Is `modifiedCount=0` equivalent to MongoDB WriteConflict?**

No. It can be a normal outcome when the filter does not match or the update changes no values. Inspect `matchedCount` and business rules.

**4. Why isn't `findOne()` followed by `updateOne({_id})` enough to protect stock?**

Between read and write, another request can modify stock. The `available >= qty` check must occur inside the atomic update itself.

**5. Does a stock-guarding conditional update prevent a retried request from deducting twice?**

No. While stock remains sufficient, a duplicate request sent as a new operation can deduct again; an idempotency identity is required.

**6. What do retryable writes guarantee?**

Under supported conditions, the driver can retry the same write operation per MongoDB's retryable writes protocol. It does not make arbitrary HTTP retries or business-function re-executions idempotent.

**7. How should `TransientTransactionError` be handled?**

Abort the current transaction and retry the entire transaction body per driver/helper protocol, re-reading state on a fresh snapshot within attempt/time bounds.

**8. How does `UnknownTransactionCommitResult` differ?**

It is unknown whether the commit succeeded. Never blindly re-run the business operation; retry commit in a valid context or reconcile the ledger by request ID.

**9. Why is a unique ledger index essential?**

It stops two concurrent writers from creating two records with the same tenant/operation/requestId, eliminating the check-then-insert race.

**10. Does duplicate key E11000 always mean the same request already succeeded?**

No. Determine which index/key collided, read the ledger, and compare fingerprint/state; the duplicate key may stem from another business constraint.

**11. What is a fingerprint used for?**

Detecting when a request ID is reused with a different payload/intent; allowing replay only when both key and intent match.

**12. Should an OUT_OF_STOCK outcome be stored in the ledger?**

If the API adopts "same request replays same outcome" semantics, yes. If you want to re-evaluate stock after replenishment, use a new request or a clearly specified rule.

**13. Why should a transaction callback not call a payment API?**

The callback may be retried; MongoDB cannot roll back external charges, risking double billing. Use payment-side idempotency keys and/or outbox/reconciliation.

**14. Does an outbox guarantee an event is never published twice?**

No. The relay can publish and crash before marking sent, causing redelivery. Consumers must deduplicate by stable event ID.

**15. How does a business unique index differ from an idempotency key?**

A business index enforces uniqueness of domain entities like orderNo. An idempotency key identifies an operation request for replay and duplicate-effect prevention; sometimes they coincide, though not always.

**16. What kind of error is a version mismatch typically?**

An application-level optimistic concurrency conflict, usually detected via `matchedCount=0` and mapped to HTTP 409, not a MongoDB WriteConflict by default.

**17. Why do retries need backoff+jitter?**

To prevent many workers from retrying simultaneously against the same hot document, reducing contention and retry storms.

**18. Should you retry after a network timeout with a new request ID?**

No. The previous attempt may have committed; using a new ID can duplicate effects. Keep the same ID and reconcile.

**19. What problem does a ledger TTL shorter than the retry horizon cause?**

Old records disappear before the client retries, causing the server to treat the retry as a new intent. Pick appropriate retention and durable business uniqueness.

**20. Does a MongoDB transaction provide end-to-end exactly-once semantics automatically?**

No. It is atomic across the MongoDB writes inside the transaction; API retries, external side effects, outbox delivery, and consumers require separate idempotency mechanisms.

## 28. Quick reference sheet

| Requirement | Pattern / solution |
|---|---|
| Atomically increment counter in one document | `updateOne({_id},{$inc:{value:1}})` |
| Never deduct stock below 0 | `updateOne({_id,available:{$gte:qty}},{$inc:{available:-qty}})` |
| Never overwrite a modified document | `updateOne({_id,version:expected},{$set:{...},$inc:{version:1}})` |
| Prevent duplicate request ledger entries | Unique `{tenantId:1,operation:1,requestId:1}` |
| Same request key, different payload | Canonical payload hash + `409` conflict |
| Persist ledger and business changes together | Multi-document transaction |
| Transaction transient abort | Retry **whole transaction** per label and budget |
| Transaction commit uncertain | Retry **commit**/reconcile, do not emit new intent |
| HTTP retry after lost response | Send **same Idempotency-Key** |
| Only set an idempotent state | `$set` with suitable filter, verify full workflow |
| Single-document dedupe with few keys | Conditional update + `$addToSet` in same document |
| Emit events after commit | Transactional outbox + consumer dedupe |
| Handle external payments | Provider idempotency key + reconciliation |
| Reduce hot contention | Short transactions, smart partitioning, backoff+jitter |
| Clean up ledger | TTL exceeding retry horizon / appropriate retention |

## 29. Pre-production retry checklist

- [ ] Clearly defined **a single business intent** and its request identity?
- [ ] Clients preserve the same ID across timeouts, retries, and redelivery?
- [ ] Idempotency key properly scoped to tenant + operation?
- [ ] Canonical payload fingerprint blocks key reuse with differing intents?
- [ ] Unique index created and verified, including for sharded topologies?
- [ ] Update operations place stock/version preconditions directly in filters?
- [ ] When spanning multiple documents, do business changes and ledger share a transaction?
- [ ] Are transaction callbacks free of external side effects, or moved to outbox/safe protocols?
- [ ] Are transient transaction errors distinguished from unknown commit results?
- [ ] Do driver/helper retries and application retries avoid unbounded stacking?
- [ ] Duplicate key handling reads back the ledger rather than blindly returning success?
- [ ] For pending/unknown requests, is there a status/reconciliation endpoint?
- [ ] Are retry attempts, deadlines, backoff, jitter, and rate limits capped?
- [ ] Are terminal business rejections persisted and replayed properly?
- [ ] Is ledger retention longer than the retry horizon, backed by durable business uniqueness where needed?
- [ ] Does observability capture requestId, attempt, error labels, outcome, p95/p99, and write-conflict rate?
- [ ] Tested concurrent same-key, distinct-key, lost response, failover, and callback retry scenarios?
- [ ] Enforced auth/tenant checks and avoided logging secrets or sensitive payloads?

## 30. Conclusion

**Write conflicts** reflect write contention in MongoDB, especially prominent in multi-document transactions. When an operation aborts due to a transient error, the proper retry is typically **re-executing the entire transaction** on fresh state; when commit outcome is uncertain, **retry commit or reconcile** rather than assuming nothing was written.

Yet **infrastructure-level retry success does not equal business-level idempotency**. The same HTTP request can arrive again after the database has already committed. An atomic `$inc` command can still debit funds or deduct inventory twice if invoked as two new operations. Identify requests with a **stable idempotency key**, enforce via **unique index**, verify **payload fingerprint**, persist **results for replay**, and use **transactions** when the ledger and business changes span multiple documents. For emails, payments, or brokers, add dedicated **outbox, deduplication, and reconciliation**.

The goal is a system that **withstands concurrency, recovers cleanly from timeouts/crashes, and never turns a retried request into a second business effect**.
