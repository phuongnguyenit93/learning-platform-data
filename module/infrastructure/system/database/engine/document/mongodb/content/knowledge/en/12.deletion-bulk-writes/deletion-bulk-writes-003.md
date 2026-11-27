# `findOneAndDelete` and Atomic Read-and-Delete in MongoDB

In MongoDB, an application sometimes needs to **retrieve a document's contents and immediately delete that document**. For example, a worker wants to claim a job from a temporary queue without letting another worker pick up the same job; a service wants to consume a single-use code; or a cleanup task needs to know the exact record it just deleted for logging.

Placing `findOne()` and `deleteOne()` side by side does not satisfy this requirement. Another process can update the document between the two calls, so the document read and the document deleted may no longer reflect the same state. MongoDB provides **`findOneAndDelete(filter, options)`**, which finds, selects, and deletes **one document** as an atomic read-and-write operation while returning the deleted document.

This lesson belongs to the **Deletion and Bulk Writes** chapter and focuses on the correctness semantics of this operation, document selection, concurrency handling, differences from `deleteOne()`/`deleteMany()`/bulk operations, limitations when building queues, and usage in Java or `mongosh`. Examples use the practice database `atomic_delete_lab`. **Do not run delete commands on critical data or production environments without approval and recovery procedures.**

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why `findOne()` followed by `deleteOne()` is not equivalent to an atomic read-and-delete operation.
2. Use `findOneAndDelete()` to delete one document matching a filter and **receive that exact document back**.
3. Use `sort`, `projection`, and conditional filters to select the right document.
4. Understand the scope of **single-document** atomicity, even when multiple clients access the collection concurrently.
5. Distinguish **take-and-immediately-delete** from a **claim/lease/ack** mechanism suited to queues requiring retries.
6. Choose accurately between `findOneAndDelete()`, `deleteOne()`, `deleteMany()`, `findOneAndUpdate()`, and bulk operations.
7. Design handling for timeouts, lost responses, uncertain commit outcomes, replication, and idempotency requirements.
8. Recognize index costs, ordered selection, and limitations with transactions and sharding.

## 2. What Must "Read-and-Delete" Guarantee?

Consider a `jobs` collection:

~~~javascript
{
  _id: "job-101",
  status: "READY",
  payload: { type: "EXPORT_REPORT", reportId: "r-501" },
  createdAt: ISODate("2026-05-01T08:00:00Z")
}
~~~

Requirement: a worker takes one `READY` job, receives its payload, and removes it from the unclaimed pool so no other worker can take the same document via a similar operation.

### Error-Prone Approach: Splitting Read and Delete

~~~javascript
const job = db.jobs.findOne({ status: "READY" })

if (job !== null) {
  db.jobs.deleteOne({ _id: job._id })
  printjson(job)
}
~~~

In a single-worker system with no concurrent updates, this snippet *may appear to work*. However, as soon as there are two workers:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant DB as MongoDB
    participant B as Worker B
    A->>DB: findOne(status=READY)
    DB-->>A: job-101
    B->>DB: findOne(status=READY)
    DB-->>B: job-101
    A->>DB: deleteOne(_id=job-101)
    DB-->>A: deletedCount=1
    B->>DB: deleteOne(_id=job-101)
    DB-->>B: deletedCount=0
    Note over A,B: Both A and B have read the contents of job-101
~~~

If both workers process the `job` they just read without checking the delete result, the same job can execute twice. Even if B checks `deletedCount === 0`, the read and delete still lack a single-step guarantee; the code must bolt on conflict-handling rules.

### Proper Approach for Single-Step Take-and-Delete

~~~javascript
const job = db.jobs.findOneAndDelete({
  status: "READY"
})

if (job !== null) {
  printjson(job)
}
~~~

The query and deletion execute as **one atomic operation on the selected document**. When two workers concurrently call the command to grab work, a document already deleted by Worker A cannot be returned as an existing document to Worker B in another competing delete call.

**Scope note:** this prevents two take-and-delete calls from grabbing **the same document**; it **does not guarantee the job was processed successfully after deletion**. This is an especially critical distinction in queue architectures.

## 3. Syntax and Return Values

### 3.1. mongosh Syntax

~~~javascript
db.collection.findOneAndDelete(
  filter,
  options
)
~~~

Where:

| Component | Role |
|---|---|
| `filter` | Criteria selecting the document to delete |
| `options.sort` | Defines selection order when multiple documents match |
| `options.projection` | Selects which fields appear in the **returned document**; does not decide which fields are deleted |
| `options.collation` | Specifies locale/language-specific string comparison rules when needed |
| `options.maxTimeMS` | Server-side execution time limit per supported API |

Specific options may vary across MongoDB versions, drivers, and call styles. Examples in this lesson use common core options.

### 3.2. Return Value

When a matching document is found, `mongosh` returns the document **as it existed before deletion**:

~~~javascript
{
  _id: "job-101",
  status: "READY",
  payload: { type: "EXPORT_REPORT", reportId: "r-501" },
  createdAt: ISODate("2026-05-01T08:00:00Z")
}
~~~

When no document matches, the result is `null`:

~~~javascript
const removed = db.jobs.findOneAndDelete({
  _id: "no-such-job"
})

print(removed === null) // true
~~~

**It does not return `deletedCount` like `deleteOne()`**. This difference in return type matters when changing APIs or refactoring code from one delete method to another.

### 3.3. When Should You Use It?

`findOneAndDelete()` makes sense when:

- You must know **the contents of the document that was just deleted**.
- The filter may match multiple documents and you want to select and delete one specific document using `sort`.
- You need to eliminate the race window between a separate read and a separate delete.
- Losing the document immediately upon retrieval is acceptable to the business domain.

If you only need to delete by `_id` and check the deleted count, `deleteOne()` is usually simpler. If you need to recover or retry job processing after a crash, see the claim/lease pattern later in this lesson rather than deleting eagerly.

## 4. Creating Lab Data

The following examples assume a fresh lab database without an existing `jobs` collection. Do not re-run the entire `insertMany()` with the same `_id`s if data from a previous run is still present.

~~~javascript
use atomic_delete_lab

db.jobs.insertMany([
  {
    _id: "job-101",
    status: "READY",
    priority: 2,
    createdAt: ISODate("2026-05-01T08:00:00Z"),
    payload: { type: "EXPORT", reportId: "r-101" }
  },
  {
    _id: "job-102",
    status: "READY",
    priority: 5,
    createdAt: ISODate("2026-05-01T08:05:00Z"),
    payload: { type: "EMAIL", templateId: "t-102" }
  },
  {
    _id: "job-103",
    status: "DONE",
    priority: 9,
    createdAt: ISODate("2026-05-01T08:02:00Z"),
    payload: { type: "CLEANUP", resourceId: "x-103" }
  },
  {
    _id: "job-104",
    status: "READY",
    priority: 5,
    createdAt: ISODate("2026-05-01T08:05:00Z"),
    payload: { type: "EXPORT", reportId: "r-104" }
  },
  {
    _id: "job-105",
    status: "READY",
    priority: 1,
    createdAt: ISODate("2026-05-01T08:10:00Z"),
    payload: { type: "EMAIL", templateId: "t-105" }
  }
])
~~~

Inspect the data before deleting:

~~~javascript
db.jobs.find(
  {},
  { _id: 1, status: 1, priority: 1, createdAt: 1 }
).sort({ _id: 1 })
~~~

We will select jobs in **descending `priority`**, then **ascending `createdAt`**, and finally `_id` as a deterministic tie-breaker.

## 5. Deleting a Document and Returning That Exact Document

### 5.1. Deleting by Known `_id`

~~~javascript
const removed = db.jobs.findOneAndDelete({
  _id: "job-105"
})

printjson(removed)
~~~

On the unmodified lab dataset, this returns `job-105` and removes it from the collection. Verify:

~~~javascript
db.jobs.findOne({ _id: "job-105" }) // null
~~~

Running the delete for `job-105` a second time returns `null`. That **does not mean the second request is a system error**; it may be a retried operation after the first succeeded. However, the second call also **no longer has the old document contents to return** unless the application stored the result elsewhere.

### 5.2. Deleting by Business Criteria

~~~javascript
const removed = db.jobs.findOneAndDelete({
  status: "READY",
  priority: { $gte: 2 }
})

printjson(removed)
~~~

This deletes only one job matching the filter. If multiple jobs match, **do not assume a stable order** without `sort`. Results can differ across runs, index changes, or workload changes.

### 5.3. Do Not Run an Empty Filter Carelessly

~~~javascript
// DANGEROUS: may delete any arbitrary document in the collection.
db.jobs.findOneAndDelete({})
~~~

This is an example of what to avoid in production. The `{}` filter makes every document a candidate; without `sort` and proper selection criteria, you cannot know which object will be deleted first.

For administrative actions or critical APIs, require mandatory identifying fields, validate inputs, and log the `_id` of the deleted document.

## 6. Selecting Records with `sort`

When multiple documents match the filter, `options.sort` tells MongoDB **which document to prioritize for deletion**.

### 6.1. Taking the Highest-Priority Job

To start fresh, use a new lab database or re-seed the sample data. Then run:

~~~javascript
const job = db.jobs.findOneAndDelete(
  { status: "READY" },
  {
    sort: {
      priority: -1,
      createdAt: 1,
      _id: 1
    }
  }
)

printjson(job)
~~~

With the initial dataset, the first result is `job-102`; `job-104` has the same `priority = 5` and the same `createdAt`, but a higher `_id`, so it comes after `job-102` when sorting ascending by ID.

A second call with the same filter and sort picks `job-104` assuming no concurrent writers or status changes. `job-103` has priority 9 but status `DONE`, so it is **not** selected.

### 6.2. Why Do You Need a Tie-Breaker?

For example:

~~~javascript
sort: { priority: -1 }
~~~

does not define an order between two jobs with equal priority. To make selection deterministic over a stable state, add tie-breaking keys:

~~~javascript
sort: { priority: -1, createdAt: 1, _id: 1 }
~~~

Because `_id` is unique in a normal collection, it serves as a reliable tie-breaker. This makes ordering deterministic for a dataset at a point in time; **it does not guarantee strict global FIFO when multiple clients concurrently insert, update, or delete jobs**.

### 6.3. `sort` Does Not Turn Job Retrieval into a Globally Guaranteed Schedule

New high-priority jobs can arrive between two calls. Workers can also contend while data and indexes are changing. Therefore:

- Do not treat `sort` as "always delivers the absolute global first job" under arbitrary concurrency.
- Do not rely on collection physical/natural order to implement a queue.
- If the domain requires fairness, strict FIFO, scheduling, or SLA-backed delivery, evaluate a dedicated message broker or coordination protocol.

### 6.4. Indexes Serving Filter and Sort

With filter `status: "READY"` and the sort above:

~~~javascript
db.jobs.createIndex(
  {
    status: 1,
    priority: -1,
    createdAt: 1,
    _id: 1
  },
  { name: "idx_ready_priority_time" }
)
~~~

This is an **index candidate**, not a universal formula for every collection. Equality on `status` followed by the sort fields can reduce scans and in-memory sorts for suitable workloads. Indexes increase write/delete overhead and storage size; measure on realistic data, especially when statuses mutate continuously.

## 7. `projection`: Limiting Only What Is Returned

`projection` in `findOneAndDelete()` **does not perform a "partial delete."** The command still deletes the entire document; projection only controls which fields are sent back to the application.

Example:

~~~javascript
const removed = db.jobs.findOneAndDelete(
  {
    status: "READY",
    priority: 2
  },
  {
    projection: {
      _id: 1,
      status: 1,
      priority: 1
    }
  }
)

printjson(removed)
~~~

With the initial data, the output contains only `_id`, `status`, and `priority` of `job-101`. The `payload` field is omitted from the response **yet still deleted along with the document**.

### How Many Fields Should You Return?

- If downstream business processing needs `payload`, do not exclude it from the projection.
- If you only need the `_id` of the deleted record, a narrow projection reduces response payload size.
- If tracing or auditing is required, capture the necessary identifiers and metadata before the result leaves memory.
- Do not strip `_id` from the result if the client needs it for verification or reconciliation.

Some drivers return a wrapper containing metadata rather than the document directly depending on API/version; check your specific driver's return type rather than generalizing everything from `mongosh`.

## 8. `collation` and String Conditions

In multi-language systems or case-insensitive lookups, collation affects string comparisons and sort order:

~~~javascript
db.session_tokens.findOneAndDelete(
  { ownerEmail: "USER@EXAMPLE.COM" },
  {
    collation: { locale: "en", strength: 2 }
  }
)
~~~

This example is meaningful only when the collection contains matching data and uses a compatible collation configuration. Setting `strength` can enable locale-aware case-insensitive matching.

Guidelines:

1. If entity identity must be unambiguous, use normalized keys/IDs rather than guessing by display email.
2. An index created with a specific collation may not be used the same way by a query specifying a different collation.
3. Do not confuse collation with access control: a request to delete a token must be authenticated and authorized for the target token.

## 9. Atomicity: What Does MongoDB Guarantee?

### 9.1. A Single Document Is the Atomic Unit

MongoDB guarantees atomicity for write operations on **a single document**, including finding and deleting one document with `findOneAndDelete()`. Another client cannot observe a "read-but-not-yet-deleted" intermediate state as happens with two separate application calls.

Example with two concurrent workers:

~~~mermaid
sequenceDiagram
    participant W1 as Worker 1
    participant DB as MongoDB
    participant W2 as Worker 2
    W1->>DB: findOneAndDelete({_id:"job-101"})
    W2->>DB: findOneAndDelete({_id:"job-101"})
    DB-->>W1: job-101 (if W1 wins)
    DB-->>W2: null (if W2 arrives after deletion)
    Note over W1,W2: Only one call can delete document job-101
~~~

If the filter is broad and **multiple `READY` documents** exist, both workers can simultaneously receive **two different documents**—which is desirable for work distribution. If only one matching document exists, one worker gets the document and the other gets `null` (or whatever reflects other concurrent changes).

### 9.2. Atomicity Does Not Mean the Entire Workflow Is Atomic

Suppose:

~~~text
1. findOneAndDelete(job) succeeds
2. call email sending service
3. write completion log
~~~

MongoDB guarantees only step 1 at the document boundary. If the application crashes at step 2, the job is already gone from the collection even though the email may never have been sent. If step 2 sends the email but step 3 fails, the system has no clear completion record.

This is why `findOneAndDelete()` fits **single-use consumption where losing the item after pickup is acceptable**, but does not by default suit **job queues requiring at-least-once processing**.

### 9.3. Atomicity Does Not Automatically Span Multiple Documents

The command:

~~~javascript
db.jobs.findOneAndDelete({ status: "READY" })
~~~

deletes **only one document**. It does not atomically decrement a counter in another collection, write an audit record, or emit an outbox event. When multiple MongoDB changes must be consistent, consider a transaction or adjust your data model so related values reside in the same document.

## 10. No Result When the Filter Matches Nothing

~~~javascript
const missing = db.jobs.findOneAndDelete({
  _id: "job-does-not-exist"
})

print(missing === null) // true
~~~

`null` generally means **no document matched at the time of execution**; it does not prove:

- The document never existed.
- Another worker just deleted it (it could be a bad filter, a changed status, or a mistyped ID).
- The job was previously processed successfully.
- The collection is completely empty.

Interpret `null` according to **the filter and domain contract**. For example, an API deleting a token by `_id` might treat "already absent" as an acceptable outcome, whereas a worker polling for jobs that receives `null` should treat it as "no eligible job currently available"—two distinct semantics.

## 11. Using Filters to Prevent Deleting Modified Data

A major benefit of atomic find-and-delete is **evaluating conditions at the exact instant of deletion**, rather than relying on stale reads.

### 11.1. Deleting by Status and Expiration

Consider a document:

~~~javascript
{
  _id: "token-001",
  userId: "user-01",
  status: "ACTIVE",
  expiresAt: ISODate("2026-05-15T10:00:00Z")
}
~~~

A command that deletes the token only if expired:

~~~javascript
const now = new Date()

const expiredToken = db.session_tokens.findOneAndDelete({
  _id: "token-001",
  status: "ACTIVE",
  expiresAt: { $lte: now }
})

printjson(expiredToken)
~~~

If the token has not expired as of the application-supplied `now`, the command does not delete it. If `status` changed away from `ACTIVE` prior to execution, the filter does not match either. This avoids "read old state, then delete without checking current state."

`new Date()` uses the clock of the `mongosh` or application process. For time-sensitive security workflows, define a trusted time source, account for clock skew, and validate token issuance/revocation logic; never assume every client clock is perfectly synchronized.

### 11.2. Optimistic Concurrency with a Version Field

An object can carry a `revision`:

~~~javascript
{
  _id: "draft-101",
  ownerId: "user-01",
  revision: 7,
  status: "DRAFT"
}
~~~

If the user viewed revision 7 and confirmed deleting that version:

~~~javascript
const deletedDraft = db.drafts.findOneAndDelete({
  _id: "draft-101",
  ownerId: "user-01",
  revision: 7,
  status: "DRAFT"
})
~~~

If another request updated the content to revision 8 or transitioned it to `PUBLISHED` before this operation ran, the filter will not match, protecting the newer version from accidental deletion. The application can return a conflict error asking the user to review, rather than falling back to `deleteOne({ _id })` and bypassing the guard.

### 11.3. Filters Must Include Access Boundaries

A multi-tenant API must never rely solely on:

~~~javascript
db.orders.findOneAndDelete({ _id: request.params.orderId })
~~~

if IDs could be probed across tenants. Include `tenantId`, owner, and status from the authenticated principal:

~~~javascript
const deleted = db.orders.findOneAndDelete({
  _id: orderId,
  tenantId: authenticatedTenantId,
  status: "DRAFT"
})
~~~

`authenticatedTenantId` must come from the verified authentication/authorization context, never trusting a client query string alone. Atomicity protects consistency; **it does not replace authorization**.

## 12. Using It as a "Take-and-Delete" Queue: Pros and Cons

A simple queue:

~~~javascript
const job = db.jobs.findOneAndDelete(
  { status: "READY" },
  {
    sort: { createdAt: 1, _id: 1 }
  }
)

if (job !== null) {
  // The application continues processing job.payload outside MongoDB.
}
~~~

### Pros

- Concise code: a single operation claims, deletes, and returns the payload.
- Two workers cannot receive the same deleted document in competing calls.
- No extra `PROCESSING` state or lock-release mechanism needed.
- Fits **single-consumption data** where losing the item after retrieval is acceptable, such as certain ephemeral caches/tickets under an explicit contract.

### Critical Cons

- **If the worker crashes after deletion ⇒ the job may be lost.**
- When external processing fails, the original document no longer exists to retry unless saved elsewhere.
- A timeout after commit leaves the worker unaware of which job was deleted and potentially without its payload to process.
- No built-in ack, retry, or dead-letter mechanism.
- Prioritization and dispatch are subject to contention, indexes, and topology; it lacks the built-in SLAs of a dedicated message broker.

**Architectural takeaway:** if work must not be lost, design **claim/lease/ack** or use a queue system with appropriate delivery guarantees. Do not pick `findOneAndDelete()` simply because it prevents duplicate pickup while ignoring failure recovery.

## 13. Safer Queue Pattern: Claiming with `findOneAndUpdate()`

Instead of deleting immediately, a worker **marks the job as claimed** and sets a *lease* expiration. Only after processing finishes does it acknowledge completion or perform a conditional delete.

~~~mermaid
flowchart LR
    READY["READY"] -->|"findOneAndUpdate + claim token"| LEASED["LEASED"]
    LEASED -->|"Successful processing + ACK"| DONE["DONE or delete"]
    LEASED -->|"Lease expired / retry"| READY
    LEASED -->|"Exceeded max attempts"| DEAD["DEAD LETTER"]
~~~

### 13.1. Initializing a Recoverable Job

~~~javascript
db.reliable_jobs.insertOne({
  _id: "reliable-job-001",
  status: "READY",
  createdAt: new Date(),
  availableAt: new Date(),
  attempts: 0,
  payload: { type: "EXPORT", reportId: "r-777" }
})
~~~

### 13.2. Claiming a Job

~~~javascript
const now = new Date()
const workerId = "worker-01"
const claimToken = new ObjectId().toString()
const leaseUntil = new Date(now.getTime() + 60000)

const claimed = db.reliable_jobs.findOneAndUpdate(
  {
    $or: [
      {
        status: "READY",
        availableAt: { $lte: now }
      },
      {
        status: "LEASED",
        leaseUntil: { $lte: now }
      }
    ]
  },
  {
    $set: {
      status: "LEASED",
      leaseOwner: workerId,
      claimToken: claimToken,
      leaseUntil: leaseUntil,
      claimedAt: now
    },
    $inc: { attempts: 1 }
  },
  {
    sort: { createdAt: 1, _id: 1 },
    returnDocument: "after"
  }
)

printjson(claimed)
~~~

The state transition on **one job** is atomic. Once a job transitions from `READY` to `LEASED` with an unexpired lease, no other worker using the same filter/lease protocol will claim it.

### 13.3. Conditional ACK Using the Claim Token

After processing succeeds, the worker can delete the job **only if it still holds the lease**:

~~~javascript
if (claimed !== null) {
  const ack = db.reliable_jobs.findOneAndDelete({
    _id: claimed._id,
    status: "LEASED",
    leaseOwner: workerId,
    claimToken: claimToken
  })

  printjson(ack)
}
~~~

The `claimToken` guard prevents a stale worker from deleting a job after its lease expired and another worker reclaimed it. Stricter systems can add expiration checks and a **fencing token** on the downstream system executing side effects. A lease in MongoDB alone cannot stop a stalled worker from sending commands to an external service after its lease expires.

### 13.4. When Processing Fails

The application can use a conditional update keyed by `claimToken` to:

- Return the job to `READY` with a future `availableAt` for backoff.
- Increment `attempts` and stop retrying after a limit.
- Move it to `DEAD_LETTER` for operator inspection.
- Periodically renew the lease for long-running work, only if owner/token still match.

Never reset `status` to `READY` without verifying owner/token: a stale worker could inadvertently release a new worker's active lease.

### 13.5. At-Least-Once Does Not Mean Exactly-Once Effect

In a retry-enabled workflow, a job can run again if a worker executes the side effect and crashes before ACKing. Therefore, **handlers must be idempotent** or use stable business keys, transactions/outbox patterns, and deduplication on the receiving system. Claim/lease designs target **no lost jobs**, accepting possible redelivery; achieving exactly-once business effects requires additional guarantees.

## 14. Timeouts and Uncertain Commit Outcomes

Consider this scenario:

~~~mermaid
sequenceDiagram
    participant Client
    participant DB as MongoDB
    Client->>DB: findOneAndDelete({status:"READY"})
    DB->>DB: Select and delete job-101
    DB--xClient: Response lost due to network error
    Note over Client: Does not know which job was deleted
    Client->>DB: Sends new command with same broad filter
    DB-->>Client: May delete job-102
~~~

This is a major trap: **operation atomicity itself does not make a retried API request idempotent**.

### 14.1. Driver Retries and Application Retries Are Not the Same

On supported versions, topologies, and command types, MongoDB drivers can use **retryable writes** to retry the exact same write operation using driver-level transaction/operation identity. `findOneAndDelete` belongs to the read-modify-write group capable of supporting retryable writes under qualifying conditions.

However:

- A **new HTTP request** can initiate a **new MongoDB operation** without sharing the driver's retry identity.
- If the filter is broad (`status: "READY"`), a new call can pick a different document.
- Not every error or topology guarantees retries in the same way.
- Never assume re-running a whole business function will return the previously deleted document.

In some retryable-write implementations, MongoDB stores extra state to support retries of find-and-modify operations; for large documents or multi-node replica sets, this can carry noticeable overhead. Check behavior and metrics for your specific version.

### 14.2. Deleting by `_id` vs. Deleting by a Broad Filter

If the requirement is "delete token `token-001`," retrying the same filter:

~~~javascript
db.tokens.findOneAndDelete({ _id: "token-001" })
~~~

may return `null` on the second call, yet **it will not delete a second token**. This supports the idempotent effect "the token no longer exists," though it does not automatically reproduce **the returned payload of the first deletion**.

If the requirement is "take *any* valid token/job," a broad filter can select a different document on retry. To replay the exact same result, you need a request identity plus storage for the selected document, or a stable claim mechanism.

### 14.3. Request Ledger Pattern When You Must Return the Deleted Document

For an endpoint like `POST /consume-token`, you can:

1. Have the client send a stable `requestId`.
2. Have the server check a request ledger with a unique index.
3. Inside a transaction, delete the specific token and store the result in the ledger.
4. When receiving the same `requestId` again, return the stored result without executing a new delete.

Data model:

~~~javascript
{
  _id: "consume-req-001",
  operation: "CONSUME_TOKEN",
  targetId: "token-001",
  status: "COMPLETED",
  deletedSnapshot: {
    _id: "token-001",
    ownerId: "user-01",
    type: "ONE_TIME"
  },
  createdAt: ISODate("2026-05-15T10:00:00Z")
}
~~~

Do not store sensitive token secrets in the ledger unnecessarily; the example above illustrates metadata. Access control, encryption, retention, and what goes into `deletedSnapshot` must be explicitly defined.

### 14.4. Transaction Example for Deleting and Persisting the Result

This example assumes a **replica set or sharded cluster supporting transactions**, and that the target document already exists:

~~~javascript
const session = db.getMongo().startSession()

try {
  const result = await session.withTransaction(async () => {
    const txDb = session.getDatabase("atomic_delete_lab")
    const requestId = "req-remove-001"
    const targetId = "token-001"

    const existing = await txDb.delete_requests.findOne({
      _id: requestId
    })

    if (existing !== null) {
      if (existing.targetId !== targetId) {
        throw new Error("REQUEST_ID_REUSED_FOR_OTHER_TARGET")
      }
      return existing.deletedSnapshot
    }

    const deleted = await txDb.session_tokens.findOneAndDelete({
      _id: targetId
    })

    await txDb.delete_requests.insertOne({
      _id: requestId,
      targetId,
      status: "COMPLETED",
      deletedSnapshot: deleted,
      completedAt: new Date()
    })

    return deleted
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  printjson(result)
} finally {
  await session.endSession()
}
~~~

Under normal conditions, the transaction ensures **deleting the token and saving the ledger entry commit or abort together**. If two concurrent transactions race on the same `requestId`, one may hit a duplicate key error or write conflict; the application layer must retry or read the ledger by key and handle indeterminate commit outcomes. Transaction callbacks should not perform external side effects outside MongoDB because retries may re-invoke the callback.

This is only a lab sketch: production readiness still requires authenticating the actor/tenant, binding the request ID to payload/operation, bounding result size, setting TTL policies, and handling driver errors.

## 15. When Multiple Documents Must Change Together

`findOneAndDelete()` selects and deletes **only one document**. Sometimes a business action also needs to:

- Increment a statistics counter.
- Write an audit document.
- Create an outbox event.
- Update another account or state table.

If these steps must stay consistent with the deletion, use a **multi-document transaction**, on a supporting deployment, to commit multiple operations together.

~~~text
Transaction:
  findOneAndDelete(target)
  insertOne(audit record)
  updateOne(counter)
  insertOne(outbox event)
Commit
~~~

However, transactions add cost, duration limits, and contention risk. Do not turn a simple read-and-delete into a multi-minute transaction when redesigning the data model can avoid it. Furthermore, a MongoDB transaction **does not atomically commit with email providers, payment gateways, or message brokers**. For external side effects, use an outbox with idempotent consumers or an appropriate coordination protocol.

### When You Need to Delete Multiple Documents

If you want to delete **every document** matching a filter, use:

~~~javascript
db.expired_records.deleteMany({
  expiresAt: { $lte: new Date() }
})
~~~

`deleteMany()` returns the count of deleted documents, **not the contents of each document**. Outside a transaction, `deleteMany()` does not guarantee "all documents deleted in one all-or-nothing atomic step"; write atomicity remains per document.

If you must capture each document's contents for auditing before deletion, build a controlled workflow using transactions, archive-before-delete, or copy-out/verify/delete. **Do not loop `findOneAndDelete()` and assume the whole batch is atomic.**

## 16. Comparing Related Delete Operations

| Command | Target documents | Primary return value | When to choose |
|---|---|---|---|
| `findOneAndDelete(filter, options)` | At most 1 | Deleted document or `null` | Need atomic read-and-delete of a single document |
| `deleteOne(filter)` | At most 1 | Result with `deletedCount` | Only need to delete and verify whether one was deleted |
| `deleteMany(filter)` | Many | Result with total deleted count | Delete a set of documents matching criteria |
| `findOneAndUpdate(filter, update, options)` | At most 1 | Pre- or post-update document per option | Claim jobs, change state, and receive contents |
| `bulkWrite([...])` | Multiple operations | Aggregated batch result | Reduce round-trips across many writes; does not return old docs like `findOneAndDelete` |
| `collection.drop()` | Entire collection | Drop status | Remove the collection, its indexes, and metadata |

### 16.1. `findOneAndDelete` vs. `deleteOne`

~~~javascript
// Delete only, read deleted count.
const a = db.tokens.deleteOne({ _id: "token-002" })
printjson(a.deletedCount)

// Delete and receive the old document.
const b = db.tokens.findOneAndDelete({ _id: "token-003" })
printjson(b)
~~~

If you do not need the document contents, do not use `findOneAndDelete()` just because its name sounds more "complete." Consider document-return overhead, retry behavior, and load.

### 16.2. `findOneAndDelete` vs. `findOneAndUpdate`

~~~javascript
// One-time consume: document disappears immediately.
db.jobs.findOneAndDelete({ status: "READY" })

// Recoverable claim: document remains, status changes.
db.jobs.findOneAndUpdate(
  { status: "READY" },
  {
    $set: {
      status: "PROCESSING",
      claimedAt: new Date()
    }
  },
  { returnDocument: "after" }
)
~~~

The second pattern still requires leases, ownership, retries, and acks if jobs can run long. However, it retains data for investigation and crash recovery instead of deleting upon pickup.

### 16.3. Bulk Does Not Mean Batch-Wide Atomicity

~~~javascript
db.tokens.bulkWrite([
  {
    deleteOne: {
      filter: { _id: "token-004" }
    }
  },
  {
    deleteOne: {
      filter: { _id: "token-005" }
    }
  }
])
~~~

Operations in `bulkWrite` reduce call overhead and offer ordering choices, but **they do not create an atomic transaction across the entire batch**. If you cannot lose any operation when part of a batch fails, design retries/idempotency and verify per-target outcomes; if whole-batch atomicity is required, evaluate transactions within appropriate bounds.

In newer MongoDB versions, some single-delete APIs may support `sort`; check your server and driver version before substituting. The primary deciding factor remains **whether you need the deleted document returned**.

## 17. Performance: Indexes, Sort, and Write Cost

A `findOneAndDelete()` call typically has two cost components:

1. **Finding** the document matching the filter and sort.
2. **Deleting** the document, updating indexes, and recording the change through storage and replication.

On large collections, broad filters or unindexed sorts can force MongoDB to read many documents, scan numerous index keys, or perform expensive sorts before picking a document to delete.

### 17.1. Measuring the Lookup Portion with an Equivalent Query

To see how well an index is used, run a `find()` with the same filter and sort:

~~~javascript
db.jobs.find({
  status: "READY"
}).sort({
  priority: -1,
  createdAt: 1,
  _id: 1
}).limit(1).explain("executionStats")
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and whether a `SORT` stage appears. This is a **reference measurement** of lookup cost; it does not measure the full deletion work or internal retry overhead of `findOneAndDelete()`.

### 17.2. Indexes Must Match Real Queries

~~~javascript
db.jobs.createIndex({
  status: 1,
  priority: -1,
  createdAt: 1,
  _id: 1
})
~~~

This index can help a `status = READY` query sorted by priority/time/id. But if you also filter on `availableAt <= now`, tenant partition, job type, or constantly changing priorities, re-evaluate index key order based on selectivity, scan cost, sort elimination, and update overhead.

### 17.3. Do Not Use `findOneAndDelete` in a Tight Loop for High-Volume Cleanup

~~~javascript
// Do not run this infinite loop on a production collection.
while (db.events.findOneAndDelete({ archived: true }) !== null) {
  // ...
}
~~~

When the goal is deleting millions of records, removing one document per call creates excessive round-trips, contention, and server load. Evaluate `deleteMany()`, bounded batching, retention/TTL, partitioning/archival, or a snapshot-export-verify-delete pipeline depending on your objective. If you must capture every deleted document, design that as an archive/audit pipeline, not a read-and-delete loop.

### 17.4. Many Workers Contending on the Queue Head

When thousands of workers all query the first job via the same index and sort, contention can arise. An efficient filter index does not automatically make a queue scale linearly. You may need to:

- Partition jobs by tenant, queue name, or shard key.
- Cap polling workers and add backoff when no jobs are available.
- Use appropriate batching or claiming to reduce lookup frequency.
- Monitor CPU, lock/contention metrics, p95/p99 latency, IOPS, and replication lag.

If your system has complex work-distribution SLAs, consider a dedicated message broker instead of trying to turn a collection into a general-purpose queue.

## 18. Replica Sets, Write Concern, and Sharded Clusters

### 18.1. Replica Sets

On a replica set, deletes execute on the primary per replica set semantics and are replicated. Write outcomes depend on **write concern**, failover behavior, and retry logic.

- `w: 1` acknowledges from the primary per configured settings; it does not mean the delete is majority-committed.
- `w: "majority"` requires majority acknowledgment per MongoDB/deployment semantics, affecting latency and durability across failovers.
- If a client loses the response, a timeout alone does not prove the deletion did not happen.
- Clients must understand read preference, read concern, and read-your-own-writes expectations in their topology.

Single-document atomicity and durability/visibility after failover are **two separate concerns**. Choose a write concern matching the criticality of the deleted data.

### 18.2. Sharded Clusters

In a sharded cluster, filtering precisely on the shard key enables targeted routing to the relevant shard, especially when deleting by a known business ID. With broad filters or cluster-wide sorts, finding candidates and coordinating execution can be complex, resource-intensive, and subject to version-specific limitations.

Never assume every `findOneAndDelete({status:"READY"}, {sort:...})` gives cluster-wide FIFO or ideal horizontal scaling. When designing a sharded queue, consider:

- Shard key choice and queue boundaries.
- Routing predicates in the filter.
- Hotspots on shards holding high-priority jobs.
- Index overhead, cross-shard operations, and topology.
- Transaction, consistency, and failover requirements.

Check the documentation for your **exact MongoDB version** before selecting syntax, especially for complex options and transactions on sharded collections.

### 18.3. Deleting Is Not a Backup Strategy

Deleting a document and replicating that delete does not mean secondaries retain a copy for recovery. If important data is deleted by mistake, recovery depends on dedicated backups/snapshots or audit/history logs. For data that must be preserved, never design a workflow that deletes first and attempts to save a copy afterward.

## 19. Using `findOneAndDelete` in the Java Driver

In the MongoDB Java Sync Driver, the corresponding method is:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.FindOneAndDeleteOptions;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

MongoCollection<Document> jobs = database.getCollection("jobs");

FindOneAndDeleteOptions options = new FindOneAndDeleteOptions()
    .sort(Sorts.orderBy(
        Sorts.descending("priority"),
        Sorts.ascending("createdAt"),
        Sorts.ascending("_id")
    ))
    .projection(Projections.include(
        "_id", "status", "priority", "payload", "createdAt"
    ));

Document deleted = jobs.findOneAndDelete(
    Filters.eq("status", "READY"),
    options
);

if (deleted == null) {
    System.out.println("No matching job found");
} else {
    System.out.println("Claimed and deleted: " + deleted.getString("_id"));
}
~~~

The `database` variable is assumed to be a `MongoDatabase` obtained from a `MongoClient` connected to the lab database. There is no `use` command inside Java as in `mongosh`; the Java driver specifies the database when obtaining the handle.

### 19.1. Comparing Java APIs

~~~java
// Delete only, read deleted count.
long deletedCount = jobs.deleteOne(
    Filters.eq("_id", "job-101")
).getDeletedCount();

// Delete and receive the old document.
Document deletedJob = jobs.findOneAndDelete(
    Filters.eq("_id", "job-102")
);
~~~

If using asynchronous or reactive drivers, the call style differs while preserving MongoDB semantics. When using frameworks like Spring Data MongoDB, verify that your chosen method actually issues a single atomic find-and-delete operation rather than two separate `find` and `remove` calls.

### 19.2. Application Code Must Handle `null` Results

Avoid writing:

~~~java
Document deleted = jobs.findOneAndDelete(
    Filters.eq("_id", "missing")
);
System.out.println(deleted.getString("_id")); // Potential NullPointerException.
~~~

Always check `deleted != null` before reading fields or triggering side effects.

## 20. Business Safety When Reading and Deleting

### 20.1. Single-Use Codes

Suppose a collection stores single-use tokens:

~~~javascript
{
  _id: "token-001",
  ownerId: "user-01",
  purpose: "CONFIRM_ACTION",
  status: "ACTIVE",
  expiresAt: ISODate("2026-12-31T00:00:00Z")
}
~~~

An API can consume the token:

~~~javascript
const consumed = db.one_time_tokens.findOneAndDelete({
  _id: submittedTokenId,
  ownerId: authenticatedUserId,
  purpose: "CONFIRM_ACTION",
  status: "ACTIVE",
  expiresAt: { $gt: new Date() }
})

if (consumed === null) {
  // Token does not exist, already used, expired, wrong purpose, or does not belong to user.
}
~~~

"Token vanishes when used" behavior may fit here. However, if consuming the token must accompany updating another resource, consider transactions and handling uncertain commit states. **Never use the mere existence of a token in the database as sole proof of authorization**; authenticate the request and bind the token to the user and purpose.

### 20.2. Cleaning Up Expired Records Requiring Audit

If you only need to bulk-delete expired records, `deleteMany()` may fit. If each record must be archived first, build an **archive → verify → conditional delete** pipeline. `findOneAndDelete()` captures the document before deleting it, yet if the process dies after deletion and before persisting the archive, the record can still be lost.

### 20.3. Conditional Draft Deletion

When a user requests deleting a draft currently being edited:

~~~javascript
db.drafts.findOneAndDelete({
  _id: draftId,
  tenantId: tenantIdFromAuth,
  ownerId: currentUserId,
  revision: expectedRevision,
  status: "DRAFT"
})
~~~

This is a strong example of a filter combining **identity + authorization scope + status + revision**. If it returns `null`, the application must not fall back to deleting by `_id` alone; distinguish not-found, unauthorized, and version conflict per your API contract without leaking information across tenants.

## 21. Common Pitfalls

| Pitfall | Why is it wrong? | Correct approach |
|---|---|---|
| `findOne()` then `deleteOne()`, assuming it is atomic | Leaves a window for concurrent updates/workers | Use `findOneAndDelete()` or guarded conditions + transactions where appropriate |
| Not checking `deletedCount` in the two-call approach | Another worker may already have deleted it | At minimum check the result; better yet, use a single atomic command |
| Calling `findOneAndDelete({})` | Can delete an arbitrary document | Use explicit filters and `sort` when ordered selection is needed |
| Assuming single-field `sort` is deterministic | Duplicate values have no tie-breaker | Add `_id`/a unique key to `sort` |
| Thinking `projection` deletes only certain fields | Projection only limits returned fields | Use `$unset` to remove fields, not `findOneAndDelete` |
| Expecting `deletedCount` from `findOneAndDelete()` | API returns a document or `null` | Choose `deleteOne()` if you only need a count |
| Using a take-and-delete queue for unlosable jobs | Worker crash loses the job | Claim/lease/ack + retries/idempotency |
| Retrying a broad filter after a timeout | Can delete an additional, different document | Request ledger, stable claims, or targeting by `_id` |
| Treating retryable writes as HTTP idempotency | A new HTTP retry may start a new operation | Track request IDs and replay responses per contract |
| Treating a single-doc op as workflow-wide transaction | Does not cover external services or other collections | Use transactions/outbox matching consistency boundaries |
| Using `deleteMany()` expecting batch-wide atomicity | No all-or-nothing atomicity by default | Use transactions when needed within appropriate limits |
| Omitting tenant/owner from the filter | Can delete resources outside authorized scope | Enforce authorization scope in filter predicates |
| Deleting before exporting archives | Failure between steps can lose data | Export, verify, then perform conditional delete |
| Unindexed filters/sorts on large collections | Expensive CPU/I/O scans and sorts | Index for filter+sort and measure with representative queries |

## 22. Complete Hands-On Lab

Run these exercises on the `atomic_delete_lab` database. For predictable results, start from the `jobs` dataset in Section 4 on a fresh lab database.

### Part A — Select and Delete

**Exercise A1.** Find the job with `status = "READY"` and highest priority, breaking ties by older `createdAt`, then smaller `_id`. Use `findOneAndDelete()` and print `_id`. Prediction:

~~~text
Run 1: job-102
Run 2: job-104
Run 3: job-101
Run 4: job-105
Run 5: null
~~~

On the original dataset, `job-103` has status `DONE`, so the `READY` filter skips it despite priority 9.

~~~javascript
function takeNextReadyJob() {
  return db.jobs.findOneAndDelete(
    { status: "READY" },
    {
      sort: {
        priority: -1,
        createdAt: 1,
        _id: 1
      }
    }
  )
}

printjson(takeNextReadyJob())
~~~

**Exercise A2.** Use `projection` to return only `_id`, `status`, and `priority`. Confirm the document is completely deleted even though `payload` was not returned.

**Exercise A3.** Delete a nonexistent `_id`, observe `null`, and explain what it means.

### Part B — Comparing with Other Commands

**Exercise B1.** Write a `deleteOne()` by `_id`; describe the difference between `DeleteResult.deletedCount` and the document returned by `findOneAndDelete()`.

**Exercise B2.** Write a `deleteMany()` to delete all `DONE` jobs in the lab. Explain why it does not return the deleted documents and why the entire batch must not be treated as a single atomic write.

**Exercise B3.** Write a `bulkWrite()` deleting two specific IDs. If one ID does not exist, explain what the command returns and why it still does not imply an atomic transaction across all operations.

### Part C — Concurrent Workers

Open two `mongosh` sessions connected to **the same lab database**, and run in each shell:

~~~javascript
const removed = db.jobs.findOneAndDelete(
  { status: "READY" },
  { sort: { createdAt: 1, _id: 1 } }
)

printjson(removed)
~~~

Observe that when multiple jobs exist, the two calls can receive two different documents. When only one `READY` job remains, one call receives the job and the other receives `null`. You do not need to force both threads to arrive at the exact same instant; the goal is to understand atomicity boundaries.

**Question:** If a worker deletes a job and crashes, does MongoDB automatically recreate the document? Describe what mechanism must be added to prevent job loss.

### Part D — Designing a Retry-Capable Queue

Replace eager deletion with:

1. `findOneAndUpdate` to claim a `READY` job with a unique `claimToken` and `leaseUntil`.
2. An idempotent handler processing the payload.
3. Conditional `findOneAndDelete` to ACK by `_id + claimToken`.
4. Retry with backoff upon lease expiration.
5. Dead-lettering after max attempts.

Explain the race when Worker A stalls, its lease expires, Worker B reclaims the job, and Worker A unexpectedly finishes. Why must the ACK check the claim token, and why might external systems need fencing?

### Part E — Designing a Draft Deletion API

A multi-tenant system has a document:

~~~javascript
{
  _id: "draft-101",
  tenantId: "tenant-A",
  ownerId: "user-7",
  status: "DRAFT",
  revision: 3,
  content: { title: "Proposal Draft" }
}
~~~

Write a filter that deletes the document **only if**:

- `_id` matches the request.
- `tenantId` and `ownerId` come from the authenticated principal.
- `status` is still `DRAFT`.
- `revision` is still `3`.

If the command returns `null`, explain how the API can handle **state conflicts** without inadvertently leaking documents belonging to another tenant.

## 23. Review Questions and Answers

**1. What does `findOneAndDelete()` perform atomically?**

It finds, selects, and deletes **a single document** in one MongoDB operation while returning the document as it was before deletion. It does not turn application-side job processing into a transaction.

**2. Why are `findOne()` followed by `deleteOne()` not equivalent?**

Because there is a window between reading and deleting during which another process can modify or delete the document. Two workers can read the same job before either deletes it.

**3. When multiple documents match, how do you select which document to delete?**

Use `sort` in options. If sort fields can contain ties, add a unique tie-breaker like `_id` for deterministic ordering over a stable dataset.

**4. How does the return value of `findOneAndDelete()` differ from `deleteOne()`?**

`findOneAndDelete()` returns the old document or `null`; `deleteOne()` returns a write result containing `deletedCount`. Do not mix up these return types.

**5. Does `projection` cause only part of a document to be deleted?**

No. Projection only restricts the fields of the **returned** document; the entire document is deleted from the collection.

**6. Why can a worker using `findOneAndDelete()` still lose jobs?**

The document is deleted the moment the worker retrieves it. If the worker crashes before completing the task, no record remains in the collection to retry.

**7. When should you use `findOneAndUpdate()` instead of `findOneAndDelete()`?**

When you need to keep the job in the database, mark it `PROCESSING`/`LEASED`, enforce lease timeouts, support retries and acks, and recover from failures.

**8. Is an HTTP retry with filter `{status:"READY"}` safe after a timeout?**

Not automatically. If the first request deleted job A but the response was lost, a new retry can delete job B. You need a request identity/ledger or stable claim mechanism.

**9. What is the benefit of adding `revision` to the filter?**

It ensures you only delete the exact state the client saw and was authorized to delete; if the document moved to a new revision, the filter stops matching instead of deleting the newer version.

**10. Can `findOneAndDelete()` delete 100 documents atomically?**

No. Each call deletes at most one document. Multiple calls do not form a transaction, and `deleteMany()` is not atomic across the whole set outside a transaction either.

**11. Do retryable writes solve lost responses at every layer of the system?**

No. The driver retries a single operation under MongoDB's supported rules; a new application-level request can be a distinct operation. Broad-filter deletes require domain-level guarantees.

**12. Why is an appropriate index needed when using `sort`?**

To reduce the number of documents/keys scanned and avoid costly in-memory sorting before selecting a document. However, indexes also add write/delete cost, so measure against real workloads.

**13. When using `findOneAndDelete()` for single-use codes, what must you check besides token existence?**

Validate user identity, purpose, expiration, status, and authorization boundaries; if another resource must update simultaneously, consider transactions and indeterminate commit handling.

**14. Is a replica set a backup for a just-deleted document?**

No. Valid delete operations are replicated; recovering deleted data depends on dedicated backup/history systems.

## 24. Quick Decision Table

| Practical need | Approach |
|---|---|
| Delete one document by ID without needing its contents | `deleteOne({_id})` |
| Delete one document and retrieve a pre-delete snapshot | `findOneAndDelete({_id})` |
| Pick one document by filter + order and delete it | `findOneAndDelete(filter, {sort})` |
| Pick one document and keep it for worker processing/retries | `findOneAndUpdate` + claim/lease/ack |
| Delete multiple documents by condition | `deleteMany(filter)` with a load plan |
| Batch multiple delete/write commands to cut round-trips | `bulkWrite` (does not mean batch-wide atomicity) |
| Delete and consistently write audit/outbox/counters | Transaction if deployment supports it and fits bounds |
| Must archive data before deleting | Export → verify → conditional delete |
| Delete records by age | Appropriate TTL/retention; do not treat TTL as an archive |
| Retry the same request and return the same delete result | Stable request ID + ledger/transaction/idempotency |

## 25. Conclusion

`findOneAndDelete()` fits cases where the domain needs to **select one document, delete it atomically, and receive the deleted contents**. It cleanly resolves the "read first, delete later" race condition at the single-document level: `filter` guards deletion conditions, `sort` defines candidate priority, and `projection` shapes the response payload.

However, **atomicity does not guarantee safety for the entire workflow**. If a document represents work that must complete reliably, deleting it on pickup risks job loss on crash. If a client loses a response after commit, re-sending the same broad filter can delete a different document. Use claim/lease/ack, request identities, transactions, outboxes, or dedicated queue services aligned with your retry, durability, and idempotency needs. Good design always starts by asking: **"Do I want to delete this data as soon as it is read, or must I guarantee the work can resume after any failure?"**
