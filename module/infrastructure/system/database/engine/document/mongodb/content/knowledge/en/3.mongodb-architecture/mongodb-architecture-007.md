# Locks, Concurrency Control, and Write Conflicts in MongoDB's Storage Engine

When multiple users read and update a database simultaneously, operations can touch the same collection, document, or index. Why can two updates on different documents run concurrently? Why does a transaction abort even when all its commands are valid? And why can two successful write commands still lose a business modification? Those questions belong to **locking, concurrency control, and write conflicts**.

This lesson explains MongoDB's architecture with the **WiredTiger storage engine**: MongoDB Server's hierarchical locking, WiredTiger's document-level write control, optimistic concurrency, MVCC, transaction behavior, and how to observe contention. Examples use **mongosh** against the practice database `concurrency_lab`.

After this lesson, you will be able to:

1. Distinguish locks at the **global/database/collection** levels from write concurrency control at the **document** level.
2. Read the four lock modes **IS, IX, S, X** and understand why certain operations wait on one another.
3. Explain **MVCC**, snapshots, and **optimistic concurrency control**.
4. Distinguish **write conflicts**, **lock waits**, **lost updates**, and data constraint errors.
5. Design safe updates using **`$inc`, conditional updates, compare-and-set**, and transactions when needed.
6. Use `serverStatus`, `currentOp`, and metrics to identify causes of slowdowns or retries.

> **Scope note:** WiredTiger is the default storage engine in standard MongoDB Server deployments; specialized deployments like Atlas Infinite have different storage architectures. Metric names and parameters may vary across release branches. Before running administrative operations, consult documentation for your exact server version and environment.

## 1. Two Layers of Concurrency Control

MongoDB Server and WiredTiger both participate in managing data access, but at different layers:

~~~text
Application / mongosh / driver
           |
           v
MongoDB Server
  - processes commands, query plans, transactions
  - multi-granularity lock manager:
      Global -> Database -> Collection
  - intent locks: IS, IX; shared/exclusive: S, X
           |
           v
WiredTiger storage engine
  - document-level write concurrency
  - optimistic concurrency + write conflict detection
  - Multi-Version Concurrency Control (MVCC)
  - cache, journal, checkpoints, and admission
           |
           v
     data and indexes
~~~

MongoDB uses **multi-granularity locking**, allowing locks to be requested at different levels. For most data read/write commands, the server uses **intent locks** at the global, database, and collection levels. WiredTiger handles write contention at the **document level**, so clients writing concurrently to **different documents in the same collection** can usually make progress concurrently.

That does not mean the server "does not lock the collection": an intent lock is still a collection-level lock. Furthermore, some administrative/metadata operations still need stronger locks, such as exclusive locks in certain cases. Do not assume from upper-layer lock modes that all underlying operations are contention-free.

### 1.1. What Is Lock Granularity?

Suppose a command modifies a document:

~~~javascript
db.getSiblingDB("shop").orders.updateOne(
  { _id: 42 },
  { $inc: { retryCount: 1 } }
)
~~~

Resources are accessed along a hierarchy:

~~~text
Global: mongod
  └── Database: shop
      └── Collection: orders
          └── Document: _id = 42
~~~

The **lock manager** operates on the levels down to the collection. When accessing a child resource, an operation declares its "intent" at parent levels; for example, writing at a finer level requires a corresponding **intent exclusive (IX)** lock. **WiredTiger** handles document-level concurrency control inside the storage engine; saying "document-level concurrency" does not mean there is a standalone `DocumentLock(_id)` object exposed in `currentOp.locks`.

### 1.2. The Four Lock Modes: IS, IX, S, and X

| Mode | Full Name | Meaning | Code in MongoDB Lock Stats |
|---|---|---|---|
| **IS** | Intent Shared | Intends to read / acquire shared lock on a lower-level resource. | `r` |
| **IX** | Intent Exclusive | Intends to write / acquire exclusive lock at a lower level. | `w` |
| **S** | Shared | Concurrent shared reading of the locked resource. | `R` |
| **X** | Exclusive | Holds exclusive access to that resource itself. | `W` |

Compatibility matrix for **two requests on the same resource**:

| Held \ Requested | IS | IX | S | X |
|---|:---:|:---:|:---:|:---:|
| **IS** | ✓ | ✓ | ✓ | ✗ |
| **IX** | ✓ | ✓ | ✗ | ✗ |
| **S** | ✓ | ✗ | ✓ | ✗ |
| **X** | ✗ | ✗ | ✗ | ✗ |

For example, two clients both holding IX on `orders` is possible because **IX is compatible with IX**. However, if a task requests **X on the same collection**, it is incompatible with IX and must wait or cause other operations to wait. Acquiring X on a collection also uses corresponding intent locks at the database and global levels to manage the full resource tree.

For most CRUD operations, WiredTiger does not need an X lock on the **entire collection** for each single-document update. However, DDL operations have different semantics; `renameCollection`, for instance, may require an exclusive database lock in certain cases. Depending on version and execution phase, index builds also have their own locking requirements.

### 1.3. What Is Lock Contention?

**Lock contention** occurs when an operation needs a lock incompatible with a lock currently held by another operation, forcing it to **wait for lock acquisition**. In a real system, distinguish between:

- **Lock wait:** the lock manager has not yet granted the requested lock.
- **Storage ticket/admission wait:** the operation has not yet received an execution slot into the storage engine even without a collection X lock.
- **I/O wait:** waiting to load pages or flush data, not necessarily caused by locks.
- **Write conflict:** optimistic storage concurrency detected an incompatible concurrent write.

All of these states can increase latency, yet their remedies differ. Seeing one slow request is insufficient to conclude "the database is locked."

## 2. WiredTiger: Optimistic Concurrency at the Document Level

WiredTiger manages data and indexes with **document-level concurrency control** for writes. Two operations modifying different documents in the same collection normally do not block each other just by sharing that collection.

~~~javascript
// Two independent clients can execute concurrently:
db.accounts.updateOne({ _id: "A" }, { $inc: { balance: 10 } })
db.accounts.updateOne({ _id: "B" }, { $inc: { balance: 20 } })
~~~

Both commands can hold IX at the collection level. Each operation works on its own document. This does not guarantee linear throughput scaling because clients still share CPU, cache, disk, indexes, and storage engine concurrency limits.

### 2.1. How Does Optimistic Concurrency Control Work?

Unlike **pessimistic locking**, which acquires exclusive rights upfront, **optimistic concurrency control (OCC)** lets operations proceed assuming most accesses will not conflict. When applying changes, the storage engine checks the relevant versions/states. If two operations cannot both complete under their initial assumptions, the system detects a **write conflict** and one operation must retry or abort depending on context.

~~~text
Client A                           Client B
    |                                  |
    |  accesses document X             |  accesses document X
    |                                  |
    +------- requests update X --------+------- requests update X
                    |
            WiredTiger checks
           write compatibility
                    |
             WRITE CONFLICT
                    |
        one operation proceeds;
        the other retries / aborts
        depending on command and transaction
~~~

For **standard write operations outside a multi-document transaction**, MongoDB has an **internal retry** mechanism when WiredTiger detects a conflict. Clients usually see only the post-resolution command outcome, not individual retry attempts. Still, do not generalize this into "every operation retries infinitely and always succeeds": transactions, resource limits, timeouts, and other errors can still cause requests to fail.

When many clients continually modify **the same hot document**, conflicting and retried work can consume substantial resources. This is a contention bottleneck even though collection-level locking has been minimized.

### 2.2. Why Can't Lock Modes Predict Every Write Conflict?

On a collection, clients A and B can both hold IX because IX–IX are compatible. Yet both clients might simultaneously edit `_id: "A"`. The upper-layer lock manager allows both to proceed; the **storage engine** underneath detects the data-resource conflict. Therefore:

> **IX compatibility does not mean all writes will succeed without contention.** It only says IX lock requests on the **same lock resource** can coexist.

Conversely, if an operation needs X on a collection, it can encounter a **lock wait** from existing intent locks before ever reaching the document-modification step. That is a different wait from a write conflict.

## 3. MVCC and Snapshots: Which Version Does a Reader See?

**Multi-Version Concurrency Control (MVCC)** lets WiredTiger manage data versions so operations can observe a **snapshot**. Readers get a consistent view matching operation semantics rather than seeing a half-written document.

Conceptual example:

~~~text
Time ----------- t0 -------- t1 ------- t2 ----->

Document X:
  t0: balance = 100 (V1)
  t1: new write
  t2: balance = 130 (V2)

Read A uses view at t0     -> may see V1
Read B starts after write  -> may see V2
~~~

With an older snapshot, a read operation can continue observing V1 while V2 already exists in the system. However, **do not assume all MongoDB reads carry identical isolation guarantees**. Exact behavior depends on read concern, transactions, replica set state, and read timing.

| Concept | Distinct Meaning to Keep Clear |
|---|---|
| **WiredTiger snapshot** | Data state view provided by the storage engine for an operation. |
| **`readConcern: "local"`** | Reads data on the node under `local` guarantees; does not automatically imply majority-committed data. |
| **`readConcern: "majority"`** | Guarantees tied to majority-committed data per MongoDB conditions. |
| **`readConcern: "snapshot"`** | Snapshot guarantee in supported contexts, commonly used inside transactions. |
| **Transaction snapshot** | View used within a transaction; may not see writes committed by other clients after the snapshot began. |

### 3.1. Stale Reads Inside Transactions

Suppose transaction T read account A under its initial snapshot. Another client modifies A and commits; when T reads again, T **may see stale data**. If T subsequently tries to write A based on an incompatible snapshot, the transaction can suffer a **write conflict** and abort.

This does not mean MongoDB stored corrupt data: snapshots are designed to preserve an isolated read view per the isolation contract. Applications must understand when they need fresh data and when they must retry the entire transaction.

### 3.2. Snapshots, Journal, and Checkpoints Are Not the Same Thing

WiredTiger runs periodic **checkpoints** to write a consistent state to data files for recovery. The **journal** and **write concern** belong to durability and write acknowledgment. They differ from:

- **Concurrency:** who can read/write at the same time and how conflicts are detected?
- **Atomicity:** at what unit is a change all-or-nothing?
- **Isolation:** which versions do operations/transactions observe?
- **Durability:** how do changes survive machine crashes or failovers?

For example, using `w: "majority"` does **not** prevent a lost update from a `$set` computed off stale data. That is a problem of update conditions and business logic, not durability alone.

## 4. Single-Document Atomicity and Commonly Confused Errors

MongoDB guarantees **single-document atomicity** for a write operation, even when modifying multiple fields within the document:

~~~javascript
db.accounts.updateOne(
  { _id: "A" },
  {
    $inc: { balance: -30 },
    $set: { updatedBy: "payment-service" }
  }
)
~~~

For document A, this operation either completes wholly or not at all. However, `updateMany()` modifying multiple documents only guarantees atomicity **per individual document**, without turning the entire update set into a single transaction. Other operations can interleave between documents being updated.

### 4.1. Storage Engine Write Conflicts

A **write conflict** is detected when concurrent modifications violate WiredTiger's concurrency rules. The server may retry a single non-transactional write internally, or a transaction may receive an error and abort. An increasing write-conflict counter **does not automatically** mean an equal number of client requests failed.

### 4.2. Application-Layer Lost Updates

This bug can happen **even when both requests report success from the server**:

~~~text
Initial balance = 100

Client A reads 100                 Client B reads 100
Client A computes 100 - 30 = 70    Client B computes 100 - 20 = 80
Client A $set balance = 70         Client B $set balance = 80

Final result 80: A's update was overwritten by B.
~~~

The two unsafe commands:

~~~javascript
// Assume both clients read balance=100 before either client wrote.
// Client A:
db.accounts.updateOne(
  { _id: "A" },
  { $set: { balance: 70 } }
)

// Client B:
db.accounts.updateOne(
  { _id: "A" },
  { $set: { balance: 80 } }
)
~~~

Each `$set` remains atomic at the document level. Because the filter uses only `_id`, both are valid; the later write overwrites the earlier one. WiredTiger's internal retry mechanism **has no idea** that `100 - 20` was calculated from stale data inside the application.

### 4.3. Lock Wait vs. Write Conflict

| Phenomenon | Origin | Indicators / Handling Direction |
|---|---|---|
| **Lock wait** | Lock manager waiting on an incompatible lock. | `waitingForLock`, `acquireWaitCount`, wait time; look for DDL or long-held locks. |
| **Write conflict** | WiredTiger detects incompatible concurrent write. | Internal retry or transaction abort; reduce hotspots and retry at the right scope. |
| **Lost update** | App reads stale data and unconditionally overwrites. | Wrong business state despite command success; use atomic updates or CAS. |
| **Duplicate key** | Unique index rejects duplicate value. | Duplicate key error, typically code `11000`; handle per data invariant. |
| **Write concern timeout** | Failed to reach write acknowledgment threshold within timeout. | Verify replication/write state before blindly re-sending requests. |
| **Admission wait** | Waiting for a read/write ticket into the storage engine. | Inspect ticket queues and storage load; do not assume a collection lock. |

## 5. Writing Safe Updates Under Concurrent Load

### 5.1. Prefer Atomic Update Operators

When incrementing counters or adding/subtracting amounts, use `$inc` instead of reading into the application and calling `$set`:

~~~javascript
db.getSiblingDB("concurrency_lab").counters.updateOne(
  { _id: "downloads" },
  { $inc: { count: 1 } },
  { upsert: true }
)
~~~

With two successful increments, the counter increases by two without losing an update from both reading the old value. When a business condition applies (e.g., sufficient balance), put the condition **inside the same update filter**:

~~~javascript
const result = db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A", balance: { $gte: 30 } },
  { $inc: { balance: -30 } }
)

if (result.matchedCount === 0) {
  print("Matching account not found or insufficient balance")
}
~~~

MongoDB evaluates the update filter condition atomically with the update operation. If another client already deducted funds leaving `balance < 30`, this command will not match. This enforces an **invariant on a single document**.

Note: the balance example illustrates concurrency only and omits transaction IDs, ledgers, deduplication, refunds, and requirements of real financial systems.

### 5.2. Compare-and-Set Using a Version Field

When the application genuinely needs a **read document → modify outside database → write back** sequence, add an application-managed `version` field:

~~~javascript
const lab = db.getSiblingDB("concurrency_lab")
lab.profiles.replaceOne(
  { _id: "user-1" },
  { _id: "user-1", displayName: "An", city: "Hanoi", version: 1 },
  { upsert: true }
)

// Application previously read version = 1.
const result = lab.profiles.updateOne(
  { _id: "user-1", version: 1 },
  {
    $set: { city: "Da Nang" },
    $inc: { version: 1 }
  }
)

if (result.matchedCount === 0) {
  print("Data was modified by another client; reload and reconcile changes")
}
~~~

If two clients both hold version 1, only one update can advance version from 1 to 2. The later client gets `matchedCount = 0`. This outcome is a **non-matching predicate**, not necessarily a storage-engine `WriteConflict` error. Blindly retrying with `version: 1` will never succeed; you must re-read and decide whether to merge, report a conflict, or recompute.

Do not confuse a document's logical `version` field with MongoDB Server's **Feature Compatibility Version (FCV)** or internal MVCC versions.

### 5.3. `findOneAndUpdate` for an Atomic Read–Modify Step

~~~javascript
const updated = lab.accounts.findOneAndUpdate(
  { _id: "A", balance: { $gte: 25 } },
  { $inc: { balance: -25 } },
  { returnDocument: "after" }
)

if (updated === null) {
  print("No account matched the condition")
} else {
  print("New balance: " + updated.balance)
}
~~~

This command checks the predicate, updates a single document, and returns the document per option. The `returnDocument` syntax shown is `mongosh`; other drivers/frameworks may have different option names and return shapes. Side effects outside MongoDB (sending email, calling a payment gateway, publishing a message) do **not** become atomic with this command.

### 5.4. Uniqueness Requires a Unique Index

A `findOne({ email })` followed by `insertOne(...)` still has a race condition if two clients simultaneously see the email does not exist yet. The database needs a unique index:

~~~javascript
lab.users.createIndex({ email: 1 }, { unique: true })
~~~

The losing client may receive a duplicate key error. That is a data-constraint result to handle in application logic, **not** a signal to blindly retry. Depending on the use case, also consider email normalization, collation, partial indexes, or tenant-scoped compound keys.

## 6. Transactions: Processing Multiple Documents Together

When transferring money between accounts A and B, two separate `updateOne` commands cannot by themselves guarantee "debit A and credit B commit together or abort together." When business logic requires atomicity across **multiple documents**, consider a **multi-document transaction** on a supported deployment.

~~~javascript
// mongosh example running on a transaction-capable replica set.
const session = db.getMongo().startSession()
const accounts = session.getDatabase("concurrency_lab").accounts

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const debit = accounts.updateOne(
    { _id: "A", balance: { $gte: 20 } },
    { $inc: { balance: -20 } }
  )
  if (debit.matchedCount !== 1) {
    throw new Error("Missing A or insufficient balance")
  }

  const credit = accounts.updateOne(
    { _id: "B" },
    { $inc: { balance: 20 } }
  )
  if (credit.matchedCount !== 1) {
    throw new Error("Missing account B")
  }

  session.commitTransaction()
  print("Committed")
} catch (error) {
  // Illustrates abort only; not a complete production retry helper.
  try { session.abortTransaction() } catch (_) {}
  print("Transfer failed to commit: " + error.message)
} finally {
  session.endSession()
}
~~~

A transaction maintains an appropriate snapshot view and follows multi-document atomicity rules. **Before committing**, changes are not exposed outside the transaction under transaction semantics; on abort, they are discarded.

### 6.1. Concurrent Writes in Transactions

- Transaction T starts from an older snapshot; an external operation updates X; when T tries to write X, T may **abort due to a write conflict**.
- Transaction T is modifying X; an external write trying to modify X may have to **wait** for T to finish or hit a conflict depending on timing and context.
- Long-running transactions can hold resources that block related DDL; waiting DDL can in turn block new transactions on the same resource.
- Transactions can hit limits on **lock wait time, lifetime, cache**, and permission requirements, even when each command inside is individually valid.

According to MongoDB production documentation, by default a transaction waits **around 5 ms to acquire needed locks**; if unavailable, the transaction may abort. The `maxTransactionLockRequestTimeoutMillis` parameter allows adjusting this in supported environments. **This is a lock-wait limit**, not the maximum runtime of the transaction. Default transaction lifetime has its own separate limit (typically under one minute, configurable).

Do not arbitrarily raise lock timeouts just to "reduce errors": it can lengthen waits or worsen deadlock-handling delays. Identify the source of contention and evaluate version, topology, and environment policies first.

### 6.2. Retrying at the Right Scope

| Error / Label | Meaning | Strategy |
|---|---|---|
| **`TransientTransactionError`** | Transient error requiring the transaction to be retried. | Abort the failed attempt and **retry the entire transaction**, bounded by limits. |
| **`UnknownTransactionCommitResult`** | Client cannot tell whether commit succeeded. | **Retry commit** per driver contract; do not blindly re-run business logic. |
| **`TransactionTooLargeForCache`** | Transaction exceeded WiredTiger cache limits. | Redesign/split the workload; retrying identically rarely helps. |
| **Duplicate key / validation error** | Data constraint not satisfied. | Handle as business error; do not blindly retry. |

MongoDB drivers usually provide a **callback/convenient transaction API** with built-in retry support; the **core transaction API** may require applications to drive retries themselves. Do not confuse driver `retryWrites=true` with automatic whole-transaction retries.

In real applications, retries need **time/attempt bounds**, appropriate backoff, **idempotency keys** for requests that might be re-sent, and careful handling of side effects outside the transaction. If a transaction callback can execute multiple times, never place email sending or third-party payment calls directly inside that callback without deduplication protection.

### 6.3. Long Transactions and Cache Pressure

WiredTiger must retain data versions for active snapshots. Long-running transactions or transactions modifying excessive data can build pressure on cache/history, triggering aborts or errors like `TransactionTooLargeForCache`. Therefore:

- Keep transactions **short**, containing only operations requiring multi-document atomicity.
- Index filters used inside transactions; avoid broad scans.
- Avoid slow network API calls or waiting on user input inside a transaction.
- Abort transactions on error; do not leave abandoned sessions/transactions open.
- If an invariant can be modeled within **a single document**, prefer an atomic operation on that document.

## 7. Yielding, DDL, and Admission Queues

### 7.1. Yielding: Releasing Resources During Long Operations

Long-running reads/updates/deletes can **yield**, temporarily releasing certain locks/resources so other operations can progress and storage transactions do not pin snapshots too long. A multi-document update may yield between documents. The `numYields` field helps observe this behavior when reported.

Yielding is **not committing** and does not turn `updateMany()` into a unified transaction. A high `numYields` is simply a signal to correlate with query plans, execution duration, I/O, and system load.

### 7.2. DDL and Operations Requiring Strong Locks

Metadata operations like renaming a collection, dropping a collection, or phases of index builds have locking requirements distinct from CRUD. For example, if a transaction is using collection C, subsequent DDL needing an X lock on C may wait. While DDL is queued, new transactions trying to access C may also be affected.

~~~text
Transaction T1 holds lock for operation on C
          |
DDL needs incompatible lock on C -> WAITING
          |
New Transaction T2 accesses C    -> may WAIT / TIMEOUT
~~~

Exact locking behavior varies by command and version. Do not assume an index build always holds an exclusive lock for its entire duration, nor assume a "background" task has zero impact on the system.

### 7.3. Read/Write Tickets Are a Different Limit from Locks

WiredTiger also regulates the number of storage transactions allowed to run concurrently via **read/write tickets**. When no tickets remain, an operation may queue **before entering the storage engine**.

Starting in MongoDB **7.0**, the default algorithm can dynamically tune maximum ticket counts. Metric names vary by version:

- Newer branches expose **`queues.execution`** in `serverStatus`.
- Some branches/versions expose **`wiredTiger.concurrentTransactions`**.

Do not conclude overload solely because `available` tickets are low. Inspect **queued operations, wait times, throughput, and latency**. Likewise, do not arbitrarily raise max tickets as a universal fix: if the root cause is I/O or a hot document, allowing more concurrency can worsen contention.

## 8. How to Observe Locks and Write Conflicts

The examples below **only read statistics** and typically require appropriate monitoring privileges. In a replica set, verify **which node** you are inspecting and whether it is primary, secondary, or undergoing a rolling upgrade; output varies by version.

### 8.1. Counters in `serverStatus`

~~~javascript
// Run on the mongod to observe.
const s = db.serverStatus()

print("Server version: " + db.version())

print("Write conflict counter:")
printjson(s.metrics?.operation?.writeConflicts)

print("Lock metrics:")
printjson(s.locks)

print("Global lock information:")
printjson(s.globalLock)

print("Storage admission (version-dependent):")
printjson(s.queues?.execution ?? s.wiredTiger?.concurrentTransactions)
~~~

Meaning:

- **`metrics.operation.writeConflicts`** counts conflicts recorded by the server per the metric definition; it is **not** the number of failed client requests.
- **`locks`** may provide counters such as `acquireCount`, `acquireWaitCount`, and `timeAcquiringMicros` by resource and lock mode.
- **`globalLock`** is a high-level summary of activity/queues; it does not mean every write takes a global X lock.
- **`queues.execution`** or **`wiredTiger.concurrentTransactions`** helps inspect admission; verify exact semantics for your server version.

Many metrics are **cumulative counters since `mongod` started**. To observe trends, take deltas between two timestamps on the same node:

~~~text
T0: writeConflicts = 1000
T1 (after 60 seconds): writeConflicts = 1240
Delta = 240 / 60 seconds = 4 write conflicts/sec
~~~

This is only a calculation example. Four conflicts/second is not enough to declare an incident: examine request rate, latency, throughput, and transaction aborts. Counters reset to 0 on process restart.

### 8.2. Inspecting Operations Waiting on Locks

~~~javascript
db.currentOp({ waitingForLock: true })
~~~

To inspect details of active operations:

~~~javascript
const active = db.currentOp({ active: true })
printjson(active.inprog?.map(op => ({
  opid: op.opid,
  ns: op.ns,
  op: op.op,
  secs_running: op.secs_running,
  waitingForLock: op.waitingForLock,
  locks: op.locks,
  lockStats: op.lockStats,
  numYields: op.numYields,
  writeConflicts: op.writeConflicts
})))
~~~

`currentOp` is a point-in-time snapshot of activity, not a complete history of every conflict that occurred. `waitingForLock: false` **does not rule out** an operation waiting on I/O, admission, or having finished waiting right before you looked. In a sharded cluster, an operation may appear on multiple nodes in different states.

### 8.3. Slow Log and Database Profiler

When commands are slow, combine the slow operation log, database profiler (if permitted), and monitoring:

| Indicator | Investigation Clue |
|---|---|
| `millis` / duration | Severity of operation slowness; compare against baseline. |
| `locks` / `lockStats` | Lock acquisitions, lock wait counts, and total wait time. |
| `numYields` | How many times the operation yielded resources. |
| `writeConflicts` | Write conflict count recorded for the operation. |
| `docsExamined` / `keysExamined` | Whether too much data is being scanned. |
| storage queue / ticket metrics | Whether operations are queuing to enter the storage engine. |
| transaction aborts | Which transactions / when aborts are occurring. |

The database profiler has **overhead** and can log command details containing sensitive data; enable it only as permitted. Start with metrics, slow logs, and query plans before turning to the profiler if needed.

## 9. Three Hands-On Concurrency Experiments

Use the separate `concurrency_lab` database for practice. Contention experiments require **two `mongosh` windows** connected to the same deployment. If commands finish too quickly to observe an explicit write conflict, that is normal: the server may have retried internally or the two operations did not actually collide at the exact same instant.

### 9.1. Setup

~~~javascript
const lab = db.getSiblingDB("concurrency_lab")

lab.accounts.replaceOne(
  { _id: "A" },
  { _id: "A", balance: 100, version: 1 },
  { upsert: true }
)

lab.accounts.replaceOne(
  { _id: "B" },
  { _id: "B", balance: 100, version: 1 },
  { upsert: true }
)
~~~

### 9.2. Two Increments on the Same Document

In both terminals, execute:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A" },
  { $inc: { balance: 1 } }
)
~~~

If both succeed and initial balance was 100, final balance is 102. Each increment executes atomically on the document. Next, test repeatedly under light load and inspect `writeConflicts` before/after if permitted; do not generate heavy load on shared environments.

### 9.3. Lost Update Without Any Client Error

Reset A to `balance: 100`, then **in both terminals read before either side writes**:

~~~javascript
const old = db.getSiblingDB("concurrency_lab").accounts.findOne({ _id: "A" })
printjson(old)
~~~

Terminal 1:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A" },
  { $set: { balance: old.balance - 30 } }
)
~~~

Terminal 2 still holds `old.balance = 100` read earlier:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A" },
  { $set: { balance: old.balance - 20 } }
)
~~~

The final value may be 80 (if terminal 2 wrote last) instead of 50. Both commands can report success. That is a **lost update** caused by application logic.

Retry using filter `{ _id: "A", version: old.version }` and `$inc: { version: 1 }`: the second write with the stale version no longer matches, returning `matchedCount` = 0.

### 9.4. Two Conditional Withdrawals

Reset `balance = 100`. In both terminals, each attempts to withdraw 80:

~~~javascript
db.getSiblingDB("concurrency_lab").accounts.updateOne(
  { _id: "A", balance: { $gte: 80 } },
  { $inc: { balance: -80 } }
)
~~~

Only one update can match and bring the balance to 20; the other fails to match because `20 < 80`. This shows the benefit of **enforcing invariants directly inside an atomic update**.

### 9.5. Transaction Conflict Experiment

On a replica set, you can start two transactions reading/writing the same document and control write order to observe a transaction abort. Exact behavior depends on scheduling, version, and system conditions; **do not hardcode assertions on specific wait times or error codes**. The goal is to observe the difference between:

~~~text
Atomic $inc          -> never loses a successful increment
Stale read + $set    -> can lose an update silently with no error
CAS version          -> detects modified data via matchedCount=0
Transaction conflict -> can abort, requiring retry of the whole transaction
~~~

## 10. Practical Diagnostic Workflow

When suspecting slowdowns from locks or write conflicts:

1. **Narrow the scope:** affected requests, collections, nodes, time window, server version, and recent workload changes.
2. **Classify the symptom:** lock wait, write conflict, admission queue, I/O, CPU, network, query plan, or application logic.
3. **Measure over time:** p50/p95/p99 latency, throughput, `metrics.operation.writeConflicts`, lock wait metrics, queues, and transaction aborts.
4. **Locate hot operations and accesses:** are many clients updating the same `_id`? Is DDL running during peak hours? Are transactions long? Are missing indexes causing broad scans?
5. **Adjust update patterns if needed:** atomic updates, CAS, unique indexes, appropriately scoped transactions; reduce batch sizes or bound concurrency with justification.
6. **Re-measure under comparable load:** compare latency, throughput, and error rate—never conclude from a single counter.

| Symptom | Hypothesis | What to Check |
|---|---|---|
| Write-conflict counter rises with update latency | Hot document or heavy writes to same data region | `_id` distribution, write operations, transaction retries. |
| `waitingForLock` rises during migration | DDL and long operations contending for locks | Lock modes, namespaces, active transactions. |
| Transaction aborts rise, high cache pressure | Transactions too large/long or heavy contention | Lifetime, document count, indexes, cache size, error labels. |
| Read/write ticket queue grows | Storage admission saturation | CPU, disk, throughput, queue depth; do not raise tickets blindly. |
| Slow yet low lock wait, high `docsExamined` | Collection scan / missing index | `explain()` and access patterns. |
| Write succeeds yet final value is wrong | Lost update or business race condition | Read–calculate–write flow, update predicates, CAS. |
| Duplicate key errors spike | Multiple clients inserting the same unique key | Unique indexes, idempotency, and duplicate handling logic. |

Optimizing application patterns usually pays off more than tuning lock parameters: keep transactions short, index filters properly, reduce writes to overly hot documents, enforce business conditions in updates, and use bounded retries with idempotency. Change server parameters only with evidence and an understanding of your running version's behavior.

## 11. Frequently Asked Questions

**Does MongoDB lock documents?**  
With WiredTiger, MongoDB supports **document-level write concurrency**. The server still uses intent locks at the global/database/collection levels. Do not picture every document as having a publicly visible lock object in `currentOp.locks`.

**Do two readers block each other?**  
For most normal reads, read operations can proceed concurrently. Which data version is seen depends on read concern and snapshot context.

**Does `$inc` guarantee no lost additions?**  
Successful `$inc` operations on the same document are applied atomically; unlike two clients reading the same value and issuing `$set` with stale calculations. However, applications must still handle retries/idempotency if requests can be re-sent.

**Does seeing write conflicts mean data is corrupted?**  
No. It is a contention-detection signal that triggers internal retries or transaction aborts to preserve correctness. Conversely, business data can still become wrong via lost updates without raising any conflict error.

**Does `w: "majority"` prevent lost updates?**  
No. Write concern governs write acknowledgment durability; lost updates stem from update predicates and stale data in application logic.

**Is `updateMany()` atomic across the whole matched set?**  
No. Each modified document is atomic individually; documents modified by a single multi-document command can be observed partially by other operations.

**Why does the write-conflict counter rise while clients see no errors?**  
Because MongoDB can retry certain conflicts internally. The counter does not equal failed client requests.

**When should transactions be used?**  
When multiple documents must commit/abort together and the invariant cannot be safely expressed in a single atomic update. Transactions carry their own overhead, limits, and retry rules.

**Is there an equivalent to SQL's `SELECT ... FOR UPDATE`?**  
MongoDB does not have a direct query-syntax equivalent. Use conditional updates, `findOneAndUpdate`, or transactions with appropriate semantics instead.

## 12. Self-Check Exercises

1. **IX with IX:** Two writes to different documents both hold IX on the collection. Are those two locks compatible? **Yes**; document-level conflicts can still happen if they hit the same document.
2. **Lost update:** Two clients both read `count=10` and both `$set` it to 11. What is the result after both succeed? **11**; one increment was lost. Use `$inc` for atomic increments.
3. **CAS:** An update requires `version=3`, but the document is already at `version=4`, returning `matchedCount=0`. Is this definitely a WiredTiger WriteConflict? **No**; that is a non-matching filter predicate.
4. **Transaction retries:** Do `TransientTransactionError` and `UnknownTransactionCommitResult` follow the same strategy? **No**: typically retry the **entire transaction** for transient errors, and retry **commit** for unknown commit results.
5. **Counters:** `writeConflicts` rises from 1000 to 1120 over 30 seconds. What do we know? **An increase of 120** in the metric; we do not yet know whether any client requests failed or whether latency is high.
6. **Atomicity:** An `updateMany` modifies 200 documents; can clients observe some modified documents before all 200 finish? **Yes**; there is no cross-document atomicity outside a transaction.
7. **Lock scope:** Can an operation needing collection X skip parent lock levels? **No**; multi-granularity locking acquires corresponding intent locks at database/global levels.

## 13. Official Documentation

The following pages belong to the **MongoDB Database Manual**. Select the matching server documentation branch when applying to a specific version; `/docs/manual/` may point to the current release branch and differ from your environment.

- [FAQ: Concurrency](https://www.mongodb.com/docs/manual/faq/concurrency/) — multi-granularity locking, IS/IX/S/X, lock yielding, and observing locks.
- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — document-level concurrency, optimistic control, MVCC, checkpoints, and read/write tickets.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — atomicity, concurrent updates, lost updates, and conditional filters.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document commit and abort.
- [Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — write conflicts, lock acquisition, DDL, snapshots, cache, and lifetime.
- [Handle Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/) — error labels and transaction retry rules.
- [`serverStatus` command](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — lock metrics, write conflicts, and queues.
- [Database Profiler Output](https://www.mongodb.com/docs/manual/reference/database-profiler/) — lock wait counts, wait durations, and write conflicts.
- [`db.currentOp()`](https://www.mongodb.com/docs/manual/reference/method/db.currentOp/) — active operations and lock status.
- [WiredTiger — Manual 7.0](https://www.mongodb.com/docs/v7.0/core/wiredtiger/) and [WiredTiger — Manual 8.0](https://www.mongodb.com/docs/v8.0/core/wiredtiger/) — examples of version-pinned documentation.

When diagnosing real systems, always record **server version, topology, storage engine, metric capture time, driver version, and operation type**. The same "slow writes" symptom could be a lock wait, write conflict, admission queue, I/O bottleneck, or application race; only by pinpointing the exact layer causing the issue can you choose the right fix.
