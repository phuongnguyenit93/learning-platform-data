# Time Limits, Size Limits, and Restricted Operations in MongoDB Transactions

**Multi-document transactions** let MongoDB execute multiple operations across multiple documents, collections, or databases as an atomic unit in supported topologies. For example, a transfer operation can simultaneously debit wallet A, credit wallet B, and record a transfer history entry; if the transaction aborts, changes within the transaction are not partially committed.

However, a transaction **is not an unbounded workspace**. When a transaction pins a snapshot too long, writes too much data, contends on locks, tries to run unsupported administrative commands, or spans many shards, it can abort, time out, or put heavy pressure on the entire system. A statement easily misunderstood is “MongoDB transactions are capped at 16 MB”: you must distinguish the **16 MiB limit per BSON document/oplog entry** from **total transaction volume**, which is governed by different rules and resource limits across versions.

This lesson belongs to the **Transactions** chapter of the *Database Engine Document MongoDB* module. Its goal is identifying the limits to evaluate **before** putting a business flow inside a transaction—from time, memory, oplog, locks, and restricted commands to error handling and alternative designs. Examples use **`mongosh`** and the **MongoDB Node.js Driver** in the `txn_limits_lab` database. Test on a lab replica set or sharded cluster; **standard standalone MongoDB does not support multi-document transactions**. Rules around DDL, sharding, error codes, timeouts, and cache can change across MongoDB 4.x, 5.x, 6.x, 7.x, 8.x, and later releases; verify your exact server version, driver, and managed MongoDB service when deploying.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain transaction atomic boundaries and differences between transactions, atomic single-document updates, and long-running workflows.
2. Understand `transactionLifetimeLimitSeconds`, when a transaction starts, timeout scenarios, and other parameters such as `maxCommitTimeMS`.
3. Distinguish **16 MiB per BSON document**, **16 MiB per oplog entry**, and the fact that a transaction can span multiple oplog entries; never wrongly enforce a “16 MiB total transaction” rule.
4. Understand why **WiredTiger cache pressure**, long-lived snapshots, and overly large transactions still fail or degrade throughput.
5. Identify which CRUD, aggregation, and DDL operations are permitted in transactions, which have restrictions, and which are disallowed.
6. Distinguish limits on replica sets vs. sharded clusters, especially regarding collection/index creation and chunk migrations.
7. Properly use sessions, read concern, write concern, commit/abort, and avoid unsupported parallel operations on the same session/transaction.
8. Handle `TransientTransactionError`, `UnknownTransactionCommitResult`, and permanent errors without blind retries.
9. Design short transactions with proper indexes, idempotency, and no HTTP calls or long CPU work inside.
10. Split very large batches into multiple checkpointed/reconciled transactions when committing all in one transaction is infeasible.
11. Monitor transaction duration, active/aborted transactions, lock waits, cache pressure, and replication impact.
12. Run lab exercises to observe commits/aborts, timeouts, write conflicts, and the difference between business errors and system-limit errors.

## 2. What Do Transactions Guarantee, and What Do They Not?

A transaction coordinates multiple database operations inside one session:

~~~mermaid
flowchart TD
    Req["Transfer request"] --> Begin["Start transaction"]
    Begin --> Debit["Debit wallet A"]
    Debit --> Credit["Credit wallet B"]
    Credit --> Ledger["Insert transfer ledger"]
    Ledger --> Decision{"Can commit?"}
    Decision -->|Yes| All["All changes committed"]
    Decision -->|No| Abort["Abort: transaction changes not committed"]
~~~

Key guarantees:

- **Atomicity:** writes inside the transaction commit together or roll back as a transaction.
- **Isolation/snapshot semantics:** reads in the transaction follow transaction read concern/snapshot rules, unlike disconnected read/write statements.
- **Commit durability:** depends on write concern and deployment; never infer majority durability merely because a provisional update inside the transaction returned.

Things **transactions do not automatically solve**:

- They do not make external operations like sending emails or calling payment gateways atomic.
- They do not allow transactions to stay open indefinitely.
- They do not make concurrent reads/writes across arbitrary shards free.
- They do not make an API idempotent if a client resends the same request as a new transaction.
- They do not automatically protect every business invariant when two transactions update **different documents** that depend on a shared aggregate condition; strong conditions/constraints must still be designed.
- They do not allow every MongoDB command or aggregation stage inside a transaction.

### 2.1. When One Document Suffices, a Transaction Is Usually Unnecessary

~~~javascript
db.inventory.updateOne(
  { _id: "sku-A", available: { $gte: 1 } },
  { $inc: { available: -1, reserved: 1 } }
)
~~~

MongoDB updates fields of **a single document** atomically. The `available >= 1` predicate sits inside the write itself, avoiding a read-then-write race on stock. When the invariant lives inside one document, a conditional update is simpler than a multi-document transaction.

Multi-document transactions become worthwhile when changes must be consistent **across multiple documents** or collections: e.g., two wallets plus a transfer record, or order + inventory + request ledger.

## 3. Map of Limit Categories

| Limit Category | Examples | Key Takeaway |
|---|---|---|
| **Transaction lifetime** | `transactionLifetimeLimitSeconds` | Typically defaults to **60 seconds**; overly long transactions can abort |
| **Lock wait time** | `maxTransactionLockRequestTimeoutMillis` | Can abort when required locks are not acquired within budget |
| **Commit time** | Driver option `maxCommitTimeMS` | Bounds/controls commit phase per protocol; does not replace lifetime |
| **Server selection / network** | `serverSelectionTimeoutMS`, socket timeout | Client can time out before or after the server processed the operation |
| **BSON size** | Single document max 16 MiB | Applies to every document, including writes inside transactions |
| **Oplog entry** | Each entry has a BSON size limit | Does not mean the entire transaction has only one entry |
| **WiredTiger cache** | Transaction modifies/holds too much data | Can trigger transaction-too-large or cache pressure |
| **Operation / document count** | A batch of hundreds of thousands of updates | Never assume “unlimited”; constrained by resources, time, and contention |
| **Restricted commands** | `$out`, `$merge`, certain DDL/admin commands | Not every command valid outside transactions is valid inside |
| **Topology / sharding** | Cross-shard writes, chunk migrations | Extra constraints and coordination overhead |
| **Driver / session** | Retried transaction callbacks, parallel ops | Preserve session correctly and avoid non-rollbackable side effects |

**No single “transactionLimit” setting** solves all of these constraints. Good design considers all limit dimensions together.

## 4. Lab Environment: Dataset and Transaction Requirements

Suppose we need to transfer reward points between two wallets within **one tenant** and record a transfer entry. Data design:

~~~javascript
// wallets
{
  _id: "wallet-A",
  tenantId: "t-01",
  ownerId: "customer-A",
  balancePoints: 1000,
  version: 1
}

{
  _id: "wallet-B",
  tenantId: "t-01",
  ownerId: "customer-B",
  balancePoints: 200,
  version: 1
}

// transfer_log
{
  tenantId: "t-01",
  requestId: "transfer-R1",
  from: "wallet-A",
  to: "wallet-B",
  amountPoints: 150,
  state: "COMPLETED"
}
~~~

Invariants:

1. Never allow negative balances.
2. Never debit A without crediting B.
3. Never apply the same `requestId` twice.
4. Only transfer between valid wallets in the authenticated tenant.

### 4.1. Preparing Collections **Outside the Transaction**

On a lab MongoDB replica set:

~~~javascript
use txn_limits_lab

db.createCollection("wallets")
db.createCollection("transfer_log")
db.createCollection("request_outbox")

db.wallets.insertMany([
  {
    _id: "wallet-A",
    tenantId: "t-01",
    ownerId: "customer-A",
    balancePoints: 1000,
    version: 1
  },
  {
    _id: "wallet-B",
    tenantId: "t-01",
    ownerId: "customer-B",
    balancePoints: 200,
    version: 1
  }
])

db.transfer_log.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uq_tenant_transfer_request" }
)

db.wallets.createIndex(
  { tenantId: 1, ownerId: 1 },
  { name: "idx_wallet_tenant_owner" }
)
~~~

Run once on an **empty lab database**; re-running inserts with the same `_id` hits duplicate key errors. Pre-creating collections/indexes decouples the exercise from in-transaction DDL exceptions and reduces unexpected metadata locks.

### 4.2. Pre-Flight Verification

~~~javascript
db.wallets.find().sort({ _id: 1 })
db.transfer_log.getIndexes()
~~~

The lab uses small integer `balancePoints` for readability. For real currency, use integer minor units or `Decimal128`, enforce overflow/range checks, and define rounding rules; never use floating-point numbers arbitrarily for money.

## 5. Lifetime Limit: `transactionLifetimeLimitSeconds`

In MongoDB, a multi-document transaction usually has a **default lifetime limit of 60 seconds** controlled by the `transactionLifetimeLimitSeconds` server parameter. If a transaction runs longer than allowed, the server aborts expired transactions automatically.

~~~text
T = 0s    Start transaction
T = 5s    Read wallet A
T = 12s   Update wallet A
T = 35s   Wait on external API (bad practice!)
T = 61s   Transaction may abort due to expired lifetime
T = 62s   Application attempts commit => failure
~~~

**Never let transactions approach this threshold** even if errors haven't occurred yet: lock contention, failovers, network slowness, and application GC pauses can slow requests unexpectedly.

### 5.1. Viewing the Parameter on Your Deployment

If you have admin privileges and the server permits it:

~~~javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
})
~~~

This inspects **server configuration**; do not run it inside a transaction. Managed MongoDB services may restrict altering this parameter or expose it via their control plane.

### 5.2. A 60-Second Default Does Not Guarantee “Every Transaction Runs a Full 60 Seconds”

Transactions can fail **sooner** due to:

- Write conflicts with another transaction.
- Failure to acquire required locks.
- Session/connection failure or primary change.
- Large data/payload exceeding cache capacity.
- Disallowed command inside the transaction.
- Application timeout triggering explicit abort.
- Memory/execution limits of specific stages.

Conversely, background cleanup/abort of expired transactions follows server operational mechanics; never write code assuming “at exactly 60,000 ms every transaction cancels simultaneously”. Set application deadlines **shorter than the server threshold** with explicit handling.

### 5.3. Do Not Raise Lifetime as Your First Fix

Raising `transactionLifetimeLimitSeconds` can help specialized workloads, yet longer transactions are much more prone to:

- Pinning old read/write snapshots, blocking version reclamation.
- Increasing cache and storage pressure.
- Holding locks or transaction resources longer.
- Increasing write conflict probability with other transactions/writes.
- Increasing risks during failovers, chunk migrations, or stalled jobs.

**Prioritize trimming work, narrowing operation scope, and removing network calls from transactions** before raising server-wide limits.

## 6. Timeouts and Deadlines Are Not All One Thing

A real request passes through multiple stages:

~~~mermaid
flowchart LR
    API["API request deadline"] --> Select["Server selection"]
    Select --> Tx["Transaction body"]
    Tx --> Lock["Lock wait / execution"]
    Lock --> Commit["commitTransaction"]
    Commit --> Response["Client response"]
~~~

| Parameter / Limit | Scope | Risk When Misunderstood |
|---|---|---|
| `transactionLifetimeLimitSeconds` | Server-side transaction lifetime | Thinking it only bounds individual queries |
| `maxTransactionLockRequestTimeoutMillis` | Server-side lock acquisition wait budget | Mistaking it for total transaction lifetime |
| `maxCommitTimeMS` | Commit-phase time bound where supported by driver/server | Thinking raising it lets the transaction body run longer |
| `maxTimeMS` on supported operations | Individual command execution time | Treating it as a replacement for total transaction deadline |
| `serverSelectionTimeoutMS` | Driver wait to find an eligible server | Assuming the query already ran on the server |
| Socket/connect timeout | Network/driver layer | Client timeout does not prove commit did not occur |
| Application deadline | Entire business request | If longer than server lifetime, cannot guarantee completion |

### 6.1. `maxCommitTimeMS`

In supporting drivers, the `maxCommitTimeMS` transaction option caps commit execution time per command semantics. Example:

~~~javascript
// Node.js Driver: part of transaction options
{
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" },
  maxCommitTimeMS: 10000
}
~~~

Never interpret this as a strict guarantee of “60s body + 10s commit”. Transaction lifetime, commit timeout, commit retries, and server scheduling interact. If commit outcome is unknown, **reconcile or retry commit properly** rather than assuming nothing was written.

### 6.2. Lock Request Wait Time

`maxTransactionLockRequestTimeoutMillis` controls the transaction's lock wait budget in applicable situations. In some versions/configurations, the default wait is **quite short**; concurrent DDL or contended operations can abort a transaction long before hitting the 60-second lifetime.

Inspect when authorized:

~~~javascript
db.adminCommand({
  getParameter: 1,
  maxTransactionLockRequestTimeoutMillis: 1
})
~~~

Do not increase this arbitrarily in production, as waiting longer for locks extends queues, degrades peer operations, and hides indexing or transaction design flaws.

### 6.3. Client Timeouts Do Not Determine Commit Outcomes

~~~text
Client -> commitTransaction
Server -> commit succeeds
Network -> drops response
Client -> receives timeout
~~~

Here, the client **must never treat a timeout as proof of rollback**. Design idempotency keys and store business outcomes in the database to verify/replay when requests arrive again.

## 7. Why Do Long Transactions Pressure the Storage Engine?

MongoDB with WiredTiger uses MVCC/snapshots to support concurrent readers and writers. A long transaction pins an older observation state while other transactions continue writing.

### 7.1. Long-Pinned Snapshots

~~~text
T0: Transaction T reads snapshot
T1: Other writers modify thousands of documents
T2: Transaction T has not committed/aborted yet
T3: Storage engine must retain version history needed for T's consistent reads
~~~

The cost surfaces as cache usage, version history retention, eviction pressure, and delayed resource reclamation. Not every transaction locks the entire collection from start; yet **long snapshots still carry cost** even while the transaction sits idle waiting on the application.

### 7.2. Modifying Many Documents Increases Footprint

A transaction updating 100,000 documents:

~~~javascript
// Conceptual pseudocode, DO NOT run in one giant transaction.
for (const id of 100000Ids) {
  db.records.updateOne(
    { _id: id },
    { $set: { processed: true } }
  )
}
~~~

generates large in-memory change sets, extensive index modifications, oplog volume, and high contention with other writers. Even without a universal “max X documents per transaction” cap across versions, **overly broad transactions still fail and hurt throughput**.

### 7.3. Abort Cost Scales with Size Too

If a huge transaction aborts after buffering extensive uncommitted writes, the server must discard that work and the application may have to redo it. Retrying a 2-second transaction is often acceptable; aborting a 50-second transaction after heavy writes multiplies load and threatens SLOs.

### 7.4. Avoid Slow Operations Inside Transactions

Never place:

~~~javascript
// Examples you SHOULD NOT put inside a transaction callback:
await callExternalPaymentGateway();
await uploadBigFile();
await waitForUserApproval();
await slowRemoteHttpRequest();
await sleep(30000);
~~~

These operations sit outside MongoDB's commit boundary and keep transaction resources pinned while doing zero database work.

## 8. The 16 MiB Size Limit: Three Things Easily Confused

### 8.1. Single BSON Document Limit

MongoDB enforces a **16 MiB limit per BSON document**. An order document embedding an oversized `items` array or payload remains invalid even if inserted inside a transaction:

~~~javascript
{
  _id: "order-too-big",
  items: [ /* data pushing document past 16 MiB */ ]
}
~~~

**Transactions do not raise the maximum size of a single document.** If data naturally exceeds the limit, split documents, adopt a referenced model, or use GridFS for large binaries as appropriate.

### 8.2. Per-Oplog-Entry Limit

The oplog records changes for replication. **Each BSON oplog entry has a size limit tied to the 16 MiB BSON limit.** In modern MongoDB versions (4.2+), a multi-operation transaction can produce **multiple oplog entries**, rather than squeezing the entire transaction into **one single oplog entry** as older versions did.

Therefore:

> It is false to claim “every multi-document transaction in modern MongoDB has a hard 16 MiB total cap”.

Actual transaction capacity depends on memory/cache, lifetime, operation count, oplog, write throughput, and server version. In very old legacy MongoDB versions, oplog encoding and total limits differed; check version docs when maintaining legacy clusters.

### 8.3. Total Transaction Bytes Are Still Not Infinite

Suppose a transaction updates 30,000 small documents. Total modified bytes may **exceed 16 MiB** without violating “16 MiB per BSON document”. Yet the transaction can still fail because:

- Cache cannot hold the modified set/snapshots.
- Lifetime expires.
- Write conflicts or lock timeouts occur.
- Oplog, storage, or network saturates.
- One specific document exceeds 16 MiB.
- An individual command/request exceeds BSON/message limits.

**The right practice is measuring and bounding the unit of work**, rather than treating 16 MiB total as a single magic design number.

### 8.4. Comparison Table

| Question | Answer |
|---|---|
| Can a document written in a transaction exceed 16 MiB? | **No**, per BSON document limit |
| Does a modern transaction always produce only one oplog entry? | **Not necessarily**; it can span multiple entries |
| Does total transaction writes > 16 MiB always fail? | **No**; depends on other limits |
| Is writing 1 GiB in one transaction always safe? | **No**; extreme cache, lifetime, and resource pressure |
| Does enabling `allowDiskUse` solve document size limits? | **No**; stage spilling does not raise BSON limits |
| Does changing write concern increase BSON limits? | **No**; write concern governs acknowledgment/durability |

## 9. WiredTiger Cache and `TransactionTooLargeForCache`

A transaction whose uncommitted change set is too large relative to cache capacity puts heavy pressure on WiredTiger and can abort. MongoDB surfaces errors such as `TransactionTooLargeForCache` in applicable versions. Starting in MongoDB 6.2, driver/server handling changed for cache-exceeding transactions: **never expect infinite automatic retries to make a transaction exceeding cache capacity succeed**.

### 9.1. Separating Transient Conflicts from Size Errors

Two transactions might both abort, yet:

~~~text
A: WriteConflict because two writers touched one document
   -> Retrying with backoff on a fresh snapshot can succeed.

B: The same 200,000 updates make the transaction too large for cache
   -> Retrying the identical update count will likely fail again.
   -> Must shrink batch, scope, document size, or change architecture.
~~~

Do not classify every transaction error as `TransientTransactionError` and retry forever. Inspect error codes, labels, and version docs; for structural/resource errors, **reshape the workload**.

### 9.2. Why Adding Cache Is Not the Sole Fix

Adding RAM/cache helps certain workloads, yet:

- Transactions still face lifetime limits.
- Huge datasets require substantial I/O and commit time.
- Concurrent transactions multiply memory footprints.
- Large batches disrupt peer workloads and recovery.
- It never bypasses 16 MiB document caps or disallowed commands.

Favor small transactions touching only necessary documents, backed by indexes and resumable workflows.

## 10. Lock Contention and Early Transaction Aborts

MongoDB uses multi-granularity locks and storage engine concurrency control. A transaction updating documents modified concurrently by another transaction can hit a write conflict; metadata/DDL operations can force transactions to wait for locks.

Example:

~~~mermaid
sequenceDiagram
    participant T1 as Transaction A
    participant DB as MongoDB
    participant T2 as Transaction B
    T1->>DB: Read then update wallet-A
    T2->>DB: Attempt update wallet-A
    DB-->>T2: WriteConflict / transaction abort may occur
    T1->>DB: commit
    DB-->>T1: Succeeds
    Note over T2: Retry new transaction, re-read state
~~~

### 10.1. Write Conflicts Differ from Business Failures

~~~javascript
const result = db.wallets.updateOne(
  {
    _id: "wallet-A",
    balancePoints: { $gte: 150 }
  },
  {
    $inc: { balancePoints: -150 }
  }
)
~~~

If `matchedCount = 0`, the wallet may be missing or short on points. That is a **conditional filter outcome**, not necessarily a MongoDB `WriteConflict`.

Conversely, a transaction aborted with a transient write conflict error must be retried at the proper layer, because its previous snapshot/conditions may now be stale.

### 10.2. Lock Wait Time Differs from Application Timeout

A 60-second transaction lifetime does not mean every lock waits 60 seconds. Lock timeouts have their own budget and can be much shorter. Never crank lock timeouts up just to force a heavy DDL/batch transaction through at all costs; that extends downtime and worsens contention.

### 10.3. Indexes Keep Transactions Short

~~~javascript
db.wallets.updateOne(
  { _id: "wallet-A", tenantId: "t-01" },
  { $inc: { balancePoints: -100 } }
)
~~~

Querying by `_id` uses the default index to locate the target document immediately. If a transaction must scan millions of documents before writing due to a missing index, lifetime and resource consumption spike.

**Optimizing queries before raising transaction timeouts** is a high-leverage principle.

## 11. CRUD Operations Supported in Transactions

Under supported topologies and versions, transactions support standard data operations:

| Group | Examples | Notes |
|---|---|---|
| Read | `find`, `findOne`, supported read-only aggregations | Reads honor session/read concern |
| Insert | `insertOne`, `insertMany` | Each doc obeys BSON limit; can hit duplicate key |
| Update | `updateOne`, `updateMany` | Needs proper predicates and indexes |
| Delete | `deleteOne`, `deleteMany` | Large delete sets can make transactions too large |
| Find-and-modify | `findOneAndUpdate`, `findOneAndDelete` | Useful for atomic conditional updates |
| Bulk | Supported forms of `bulkWrite` | Must pass session; avoid huge batches |
| Aggregation | `$match`, `$group`, `$project`, `$lookup`, compatible stages | Certain stages/namespaces restricted; pipelines can be costly |

### 11.1. Multiple Collections Can Participate

~~~javascript
// Inside the same transaction:
wallets.updateOne(/* debit wallet A */)
wallets.updateOne(/* credit wallet B */)
transfer_log.insertOne(/* insert result */)
~~~

This is the primary reason for multi-document transactions. Still, each extra document expands the work scope and contention surface.

### 11.2. Multiple Databases Can Participate, With Caveats

MongoDB transactions can span multiple collections/databases in supported setups. However, **`admin`/`config`/`local` namespaces, DDL, sharded topologies, and special commands carry specific restrictions**. Never assume any namespace accessible outside a transaction can be read/written freely inside one.

### 11.3. Do Not Overuse `updateMany` and `deleteMany`

~~~javascript
// Risky if the matching set is huge:
db.events.updateMany(
  { expireAt: { $lt: new Date() } },
  { $set: { archived: true } }
)
~~~

Inside a transaction, touching massive result sets can exceed lifetime/cache budgets. For archival and cleanup, running **small checkpointed batches** is usually far better than wrapping all history in one transaction.

## 12. Commands and Stages Disallowed in Transactions

Certain operations are incompatible with transactions or strictly constrained. The list below highlights major categories; **it does not replace the official compatibility table for your server version**.

### 12.1. `$out` and `$merge`

These two aggregation stages write pipeline results to a collection:

~~~javascript
// DO NOT use as an output stage inside a transaction:
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  { $out: "order_status_report" }
])
~~~

~~~javascript
// Also DO NOT use $merge inside a transaction:
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  {
    $merge: {
      into: "order_status_report",
      whenMatched: "merge",
      whenNotMatched: "insert"
    }
  }
])
~~~

`$out` and `$merge` **are disallowed inside aggregation pipelines within multi-document transactions**. To materialize reports, run the pipeline outside transactions with appropriate consistency/idempotency, or compute inside the transaction via supported read-only stages and perform explicit writes on a small set.

### 12.2. `mapReduce`

The map-reduce command is unsupported inside multi-document transactions. For aggregations, prefer supported aggregation pipelines; for heavy ETL jobs, run outside transactions or use checkpointed batches.

### 12.3. `count` Command

The legacy `count` command is unsupported inside transactions. To count conditionally, use a compatible aggregation:

~~~javascript
// Inside a transaction, using a session-bound collection:
txDb.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "n" }
])
~~~

The driver's `countDocuments()` is implemented via aggregation and is the modern choice under supported conditions. Never confuse legacy `db.collection.count()` with `countDocuments()` inside transactions.

### 12.4. `explain` and Diagnostic Commands

Do not expect `explain` or administrative commands to run as if outside a transaction. Example:

~~~javascript
// Never run explain as part of a business transaction.
db.orders.explain("executionStats").find({ status: "PAID" })
~~~

To analyze query performance, run queries/explains **outside transactions in a test environment** under representative conditions. Never execute DDL, `serverStatus`, `replSet` admin commands, or monitoring/debug tools inside transaction bodies.

### 12.5. System Collections and Special Namespaces

Special collections—particularly in `local`, `config`, `admin`, or `system.*` namespaces—have transaction restrictions. Never try using application transactions to alter system metadata or replica set configuration.

### 12.6. Capped Collections

Write operations to capped collections are restricted in transactions; **never use multi-document transactions to write to capped collections assuming they behave like standard collections**. Depending on version, reading capped collections under snapshot read concern can also be restricted. When business logic needs a durable event log inside transactions, use a normal collection with indexes/TTL retention and an outbox, not a capped collection.

### 12.7. Change Streams

Change streams **observe committed changes** and operate independently of business transactions. Never open a change stream cursor inside a transaction expecting it to emit events for that transaction's own uncommitted writes. Design change stream consumers with resume tokens, checkpoints, and deduplication outside transactions.

## 13. DDL in Transactions: Avoid Two Extreme Claims

Both statements below can be wrong:

1. “MongoDB never allows creating collections/indexes inside a transaction.”
2. “Since transactions are supported, you can create/drop/rename any collection/index inside a transaction.”

Since MongoDB **4.4**, **creating collections and indexes inside transactions** is supported in specific cases subject to important conditions. This feature does not make all DDL valid and still carries sharded cluster restrictions.

### 13.1. Recommended Design Pattern

For an online business workflow:

~~~text
Deployment / migration:
  create collections
  create unique and supporting indexes
  verify schema validation

Runtime transaction:
  read/write on existing collections
  commit business outcome
~~~

Benefits:

- Avoids metadata locks and index builds during request transactions.
- Reduces surprises across server versions and topologies.
- Simplifies reviewable/rollbackable migrations.
- Prevents the first live request from acting as “collection creator”.

### 13.2. When Creating Collections/Indexes Inside a Transaction Is Genuinely Needed

Verify:

- MongoDB server version and driver support.
- Transaction read concern and DDL-specific requirements (certain cases require `"local"`).
- Whether the collection/index already exists.
- Whether the transaction performs cross-shard writes.
- Whether the exact command (`create`/`createIndexes`) is permitted.
- Concurrent locks and metadata operations.

Avoid:

~~~javascript
// Do not treat this as a universal production pattern:
session.startTransaction()
db.createCollection("some_dynamic_collection")
db.some_dynamic_collection.createIndex({ arbitrary: 1 })
// ...
~~~

unless all conditions are verified. In practice, it is usually **better to pre-create schemas** and avoid holding transactions open during DDL.

### 13.3. Drop, Rename, `collMod`, and Admin DDL

Do not infer from limited create/index support that `dropCollection`, `renameCollection`, `collMod`, shard key changes, or `replSet` reconfiguration work inside transactions. Those commands carry separate restrictions and belong in standalone migration/operational workflows.

### 13.4. DDL Concurrent with Transactions

If an admin starts building an index or altering metadata while transactions read/write a collection, operations may block on locks or transactions may time out/abort depending on ordering and version. Avoid running heavy index builds concurrently with critical batch transactions without an operational plan and monitoring.

## 14. Sharded Transactions: Additional Constraints

MongoDB supports distributed transactions on sharded clusters in eligible versions, yet at higher cost than single-shard or single-replica-set transactions.

### 14.1. Coordinating Commits Across Multiple Shards

~~~mermaid
flowchart TD
    App["Application"] --> Router["mongos"]
    Router --> S1["Shard A: wallet-A"]
    Router --> S2["Shard B: wallet-B"]
    Router --> S3["Shard C: transfer_log"]
    S1 --> Coord["Distributed commit coordinator"]
    S2 --> Coord
    S3 --> Coord
    Coord --> Outcome["Commit or abort entire transaction"]
~~~

When a transaction spans multiple shards, it incurs extra routing, commit coordination, network, replication, and failure-handling work. This increases **latency and timeout risk** compared to single-document atomic updates.

### 14.2. Do Not Arbitrarily Create Collections in Cross-Shard Write Transactions

Collection/index creation inside transactions has specific limits when writing across shards. Specifically, review rules around **implicit collection creation** and **cross-shard writes**. Never design a runtime transaction that simultaneously creates a new collection on shard A while writing another collection on shard B expecting it to work across deployments.

### 14.3. Chunk Migrations and Metadata Changes

A sharded cluster may actively balance chunks or update metadata. Transactions can interact with migrations and vice versa; certain chunk/placement changes can cause transactions to abort and retry. You should:

- Keep transactions short.
- Include the shard key in filters where appropriate to avoid scatter-gather routing.
- Minimize the number of participating shards.
- Implement error-label-based retry handling.
- Measure commit latency and failures on a real topology.

### 14.4. Reads in Distributed Transactions

Read concern `snapshot` provides a consistent transaction-wide snapshot under supported conditions. Never assume secondary read preferences or arbitrary aggregations work freely inside transactions; multi-document transactions normally require **`primary` read preference** at the driver.

## 15. Read Concern, Write Concern, and Transaction Options

Three primary settings:

~~~javascript
{
  readPreference: "primary",
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
}
~~~

### 15.1. `readPreference: primary`

Transactions must follow primary routing requirements. Never set `secondary` to “offload transaction reads” expecting the transactional session to behave like ordinary read-only queries outside transactions.

### 15.2. `readConcern: snapshot`

Snapshot lets reads inside a transaction observe data at a consistent point in time under supported rules. However, snapshot does not turn transactions into full serializable isolation for every complex invariant; write skew and aggregate-condition checks still require proper data constraints.

### 15.3. `writeConcern: majority` at Transaction Commit

Transaction write concern is configured at the **transaction/commit level**, not scattered arbitrarily across inner operations. Use `majority` when durability across failovers is required per MongoDB semantics. Majority acknowledgment can take longer than `w:1` depending on replication health.

### 15.4. Change Read/Write Concern Only When You Understand the Requirements

Never lower `w` or downgrade `snapshot` to `local` just to stop a timing-out transaction from failing if the business requires high durability/consistency. Optimization must balance correctness, throughput, and SLOs.

## 16. Sessions and Execution Order: Never Parallelize Unconditionally

Operations within a transaction must share **the same session**. In the Node.js Driver, **never assume running `Promise.all()` across multiple commands in one transaction is safe or supported**.

Avoid:

~~~javascript
await session.withTransaction(async () => {
  await Promise.all([
    wallets.updateOne(filterA, updateA, { session }),
    wallets.updateOne(filterB, updateB, { session })
  ]);
});
~~~

The Node.js Driver does not support parallel operations inside a single transaction like this. Never reuse the same session concurrently for two independent transactions.

Execute sequentially in controlled order:

~~~javascript
await session.withTransaction(async () => {
  const a = await wallets.updateOne(filterA, updateA, { session });
  if (a.matchedCount !== 1) throw new Error("SOURCE_NOT_FOUND");

  const b = await wallets.updateOne(filterB, updateB, { session });
  if (b.matchedCount !== 1) throw new Error("DEST_NOT_FOUND");
});
~~~

### 16.1. Cursors Must Be Consumed Within the Transaction

If reading multiple documents via a cursor, finish consuming the cursor while the session and transaction are still valid. Never return an unconsumed cursor, commit/close the session, and expect to keep reading from the old transaction snapshot indefinitely.

### 16.2. Never Reuse a Session Past Its Ended Lifecycle

Driver sessions have a clear lifecycle. Once a transaction commits or aborts, it cannot keep running commands on that snapshot. Inside helpers like `withTransaction()`, the callback can re-execute in a fresh attempt; any snapshot-dependent state must be re-read/recomputed inside the callback.

### 16.3. Keep Each Transaction's Scope Clear

One transaction scoped to **one business intent** is far easier to reason about and retry than a single transaction bundling thousands of unrelated intents just to “reduce commit count”.

## 17. `mongosh` Example: Committing/Aborting a Points Transfer

Assume setup from Section 4 ran. Create a session:

~~~javascript
const session = db.getMongo().startSession()
const txDb = session.getDatabase("txn_limits_lab")

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const amount = 150
  const debit = txDb.wallets.updateOne(
    {
      _id: "wallet-A",
      tenantId: "t-01",
      balancePoints: { $gte: amount }
    },
    {
      $inc: { balancePoints: -amount, version: 1 }
    }
  )

  if (debit.matchedCount !== 1) {
    throw new Error("INSUFFICIENT_POINTS_OR_WALLET_MISSING")
  }

  const credit = txDb.wallets.updateOne(
    {
      _id: "wallet-B",
      tenantId: "t-01"
    },
    {
      $inc: { balancePoints: amount, version: 1 }
    }
  )

  if (credit.matchedCount !== 1) {
    throw new Error("DESTINATION_WALLET_MISSING")
  }

  txDb.transfer_log.insertOne({
    tenantId: "t-01",
    requestId: "transfer-R1",
    from: "wallet-A",
    to: "wallet-B",
    amountPoints: amount,
    state: "COMPLETED",
    createdAt: new Date()
  })

  session.commitTransaction()
  print("COMMITTED")
} catch (e) {
  print("TRANSACTION ERROR: " + e.message)
  try { session.abortTransaction() } catch (_) {}
} finally {
  session.endSession()
}
~~~

If commit succeeds:

~~~text
wallet-A: 1000 -> 850
wallet-B:  200 -> 350
transfer_log: record transfer-R1 added
~~~

### 17.1. Re-Running the Raw Transaction Is Not a Safe Retry

In this example, the unique index on `{tenantId,requestId}` blocks a duplicate `transfer-R1` insert. Re-running without checking the ledger first causes a duplicate key error. Even though it prevents a double commit, the API still needs to **replay the previous result** or return an appropriate conflict. Production designs should query the request ledger, match fingerprints, and return committed results.

### 17.2. Why Abort Inside Catch?

If a transaction fails mid-body, close/abort it cleanly. However, when **commit outcome is unknown** due to network loss, never treat every exception as proof of non-commit; you may need to retry commit or reconcile via `requestId`. This `mongosh` snippet illustrates basic commit/abort, **not a complete unknown-commit implementation**.

### 17.3. Verifying State **After** the Transaction

~~~javascript
db.wallets.find().sort({ _id: 1 })
db.transfer_log.find({ requestId: "transfer-R1" })
~~~

With appropriate read/write concerns and topology, observe results from an authoritative source per business needs. If the client just lost a commit response, apply reconciliation rules rather than immediately issuing a new transfer with a fresh `requestId`.

## 18. Node.js Driver: Short Transactions with the Helper

Example using a modern driver on a transaction-capable replica set/sharded cluster:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI, {
  serverSelectionTimeoutMS: 5000
});

await client.connect();

const database = client.db("txn_limits_lab");
const wallets = database.collection("wallets");
const transfers = database.collection("transfer_log");

async function transferPoints({
  tenantId, requestId, sourceId, destinationId, amountPoints
}) {
  if (!tenantId || !requestId ||
      !sourceId || !destinationId || sourceId === destinationId ||
      !Number.isSafeInteger(amountPoints) || amountPoints <= 0) {
    throw new Error("INVALID_TRANSFER");
  }

  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      // Callback may be re-executed by driver on transient errors.
      // Never call HTTP/payment/email here.
      const previous = await transfers.findOne(
        { tenantId, requestId },
        { session }
      );

      if (previous) {
        if (previous.from !== sourceId ||
            previous.to !== destinationId ||
            previous.amountPoints !== amountPoints) {
          throw new Error("IDEMPOTENCY_KEY_REUSED");
        }
        return {
          ok: true,
          requestId,
          replayed: true
        };
      }

      // Conditional filter prevents negative balance.
      const debit = await wallets.updateOne(
        {
          _id: sourceId,
          tenantId,
          balancePoints: { $gte: amountPoints }
        },
        { $inc: { balancePoints: -amountPoints, version: 1 } },
        { session }
      );

      if (debit.matchedCount !== 1) {
        throw new Error("INSUFFICIENT_POINTS_OR_SOURCE_MISSING");
      }

      const credit = await wallets.updateOne(
        { _id: destinationId, tenantId },
        { $inc: { balancePoints: amountPoints, version: 1 } },
        { session }
      );

      if (credit.matchedCount !== 1) {
        throw new Error("DESTINATION_MISSING");
      }

      await transfers.insertOne({
        tenantId,
        requestId,
        from: sourceId,
        to: destinationId,
        amountPoints,
        state: "COMPLETED",
        createdAt: new Date()
      }, { session });

      return {
        ok: true,
        requestId,
        replayed: false
      };
    }, {
      readPreference: "primary",
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" },
      maxCommitTimeMS: 10000
    });
  } finally {
    await session.endSession();
  }
}

// Call from API only after authorization checks:
// await transferPoints({
//   tenantId: "t-01",
//   requestId: "transfer-R2",
//   sourceId: "wallet-A",
//   destinationId: "wallet-B",
//   amountPoints: 100
// });

// Close client on application shutdown:
// await client.close();
~~~

### 18.1. What the Helper Can Do

`withTransaction()` coordinates start/commit/abort and eligible retries based on error labels per the MongoDB Driver specification. The transaction callback **can be invoked again** on transient errors. Keep non-rollbackable side effects out of the callback.

### 18.2. What the Helper Does Not Automatically Solve

- It does not extend transaction lifetime indefinitely.
- It does not make an oversized transaction fit in cache.
- It does not allow forbidden commands to execute.
- It does not unify two HTTP calls carrying different `requestId` values into one intent.
- It does not guarantee two concurrent business requests sharing a key return cleanly on attempt 1; duplicate key/write conflicts may still need handling around the helper.
- It does not auto-recover from permanent errors.

**This snippet is a learning skeleton.** Production code must handle duplicate-key collisions on the specific unique index, canonicalized fingerprints, unknown commit outcomes, retry budgets, response replays, request authorization, monitoring, and session lifecycle. Never use in real monetary systems without designing and testing those paths.

### 18.3. Transactions Are Not for Long Computations

If fee calculation or routing calls external APIs, perform those before the transaction whenever possible; just recognize that data may change between computation and commit. Inside the transaction, re-verify **final preconditions** via conditional updates or version checks.

## 19. `TransientTransactionError` and Retrying the **Entire Transaction**

Under contention, a transaction may abort with the `TransientTransactionError` label. For these errors, standard handling is:

1. Abort (or let the helper abort) the current attempt.
2. Start a new transaction attempt.
3. **Re-read data and preconditions**.
4. Re-run the MongoDB writes belonging to the transaction.
5. Commit within reasonable timeout/budget limits.

Never just retry the last update statement while keeping an old snapshot once the entire transaction has aborted.

### 19.1. Transient Errors Do Not Freeze Business Decisions

~~~text
Attempt 1:
  Read balance = 100
  Plan to transfer 80
  -> Write conflict, transaction aborts

Attempt 2:
  Read new balance = 50
  -> Insufficient points, return business rejection
~~~

This is correct under concurrency. Never cache “attempt 1 had enough points” and skip the precondition on attempt 2.

### 19.2. Over-Retrying Large Transactions Amplifies Load

If a transaction takes 20 seconds and routinely retries three times, one request consumes massive resources and breaches API deadlines. Reducing transaction scope and contention usually helps far more than raising retry counts.

### 19.3. Errors That Should Not Retry Identically

- Validation errors.
- Unresolved duplicate key errors from business unique constraints.
- Commands/namespaces unsupported inside transactions.
- Transactions too large for cache.
- BSON documents exceeding 16 MiB.
- Re-evaluated data where the business precondition no longer holds.

When errors carry version-specific labels/codes, follow the **exact driver and server contract**. Never decide solely from strings containing “transaction aborted”.

## 20. `UnknownTransactionCommitResult`: Unknown Commit Outcome

`UnknownTransactionCommitResult` is critical because the transaction **may have already committed**:

~~~mermaid
sequenceDiagram
    participant API as Application
    participant DB as MongoDB
    API->>DB: commitTransaction
    DB->>DB: Commit succeeds
    DB--xAPI: Response lost
    Note over API: Unknown whether committed
    API->>DB: Retry commit / query request ledger
    DB-->>API: Outcome determined or needs reconciliation
~~~

### 20.1. Never Start Another Business Transaction Immediately

Wrong:

~~~text
Commit R1 times out
=> API generates requestId R2
=> Transfers money again
~~~

Better:

~~~text
Commit R1 times out
=> Driver retries commit of the attempt while context remains valid
=> If still unknown, read/reconcile R1 ledger
=> Client retries with the same requestId R1
=> Never auto-submit a new transfer with R2
~~~

### 20.2. Why Does a Unique Request ID Help?

Because the transaction writes `transfer_log` together with both wallet updates, reading a committed `requestId = R1` record with matching payload proves the business effect applied in that commit. If you do not see the record immediately due to read preference/consistency, **do not conclude the transaction definitely did not commit**; read/retry/reconcile per policy.

### 20.3. Retry Budgets

Both commit retries and transaction retries must be **bounded** to avoid infinite loops when the database degrades. Once the deadline expires, the API can return `PENDING`/`UNKNOWN` with the `requestId` and a status endpoint instead of falsely asserting success or failure.

## 21. Transactions and External Side Effects

Anti-pattern:

~~~javascript
await session.withTransaction(async () => {
  await inventory.updateOne(..., { session });
  await sendEmail("Order placed successfully");
  await chargeExternalCard(...);
});
~~~

Because:

1. Emails/payments are not rolled back by MongoDB transactions.
2. Callbacks can retry, sending emails or charging twice.
3. Network calls can stretch transactions toward lifetime limits.
4. External timeouts create ambiguity both inside and outside the DB.

### 21.1. Transactional Outbox

Inside the same MongoDB transaction, write:

~~~javascript
// Pseudocode: all operations must share the same session.
await inventory.updateOne(/* business update */, { session });
await orders.insertOne(/* order */, { session });
await outbox.insertOne({
  _id: "event-order-101",
  type: "OrderCreated",
  orderId: "order-101",
  state: "PENDING",
  createdAt: new Date()
}, { session });
~~~

Post-commit, a worker reads the outbox and publishes events to a broker. Since relays can republish after crashes, consumers must deduplicate by a stable event ID.

### 21.2. Never Hold Transactions Open Waiting on Users

If a workflow involves loan approval, document review, external payments, or user confirmation, use a **state machine / saga**:

~~~text
PENDING_APPROVAL
  -> APPROVED
  -> PAYMENT_REQUESTED
  -> PAYMENT_CONFIRMED
  -> COMPLETED
~~~

Each step uses a short transaction to update state/ledger/outbox, never keeping one MongoDB transaction open across minutes or hours.

## 22. Large Batches: Splitting into Multiple Checkpointed Transactions

Suppose 2 million records must be updated:

~~~javascript
// Do not put all 2 million records into one transaction.
db.records.updateMany(
  { jobId: "recalc-2026" },
  { $set: { processed: true } }
)
~~~

If all changes tried committing together, a giant transaction would fail due to lifetime/cache limits. First, re-examine **the real atomicity requirement**:

- Must “all 2 million records flip visibility at one exact instant”?
- Or must the **job complete accurately, be resumable, and avoid skipping/double-processing**?
- Can you use a **version/cutover flag** once data is prepared?

### 22.1. Batching with Checkpoints

Pattern:

~~~mermaid
flowchart TD
    Job["2M records job"] --> Read["Read batch of 500 IDs"]
    Read --> Tx["Short transaction: update batch + checkpoint"]
    Tx --> Done{"More records?"}
    Done -->|Yes| Read
    Done -->|No| Final["Mark job COMPLETED / cutover"]
~~~

Pseudocode:

~~~javascript
// Pseudocode illustrating architecture, not a standalone runnable script.
while (true) {
  const ids = await loadNextBatchAfterCheckpoint(jobId, 500);
  if (ids.length === 0) break;

  await withShortTransaction(async (session) => {
    await updateRecordsByIds(ids, { session });
    await saveCheckpoint(jobId, ids[ids.length - 1], { session });
  });
}
await markJobCompleted(jobId);
~~~

With this pattern:

- Each transaction has a **bounded write set**.
- The checkpoint and batch updates commit together.
- After a crash, the job resumes from the checkpoint.
- Updates must be idempotent or guarded against double-counting.
- There is no atomicity across **all 2 million records at once**; document those semantics explicitly.

### 22.2. Sizing Batches to Real Data

“Batch of 500” is not universally optimal. Appropriate size depends on:

- Document size and number of updated indexes.
- Participating shards.
- Write conflict rates.
- Transaction duration p95/p99.
- Cache/disk/CPU and replication health.
- Priority of concurrent transactions on the same collection.

Start small, measure in practice, and scale carefully—never pushing batch sizes near lifetime or cache limits.

### 22.3. Need an Atomic Cutover?

Suppose you are replacing a 100,000-product price table. Rather than updating live prices inside one giant transaction:

1. Write the new price table under `priceVersion: "v2"`.
2. Validate all v2 data and indexes.
3. Commit one small update on a config document: `activePriceVersion = "v2"`.
4. Readers query using the active version.

This is a **versioned read model + atomic pointer switch**, giving readers a complete cutover without a single massive transaction. Design consistency, cache invalidation, and rollback plans accordingly.

## 23. Why Transactions Do Not Replace Unique Constraints and Data Modeling

A transaction with a consistent snapshot does not automatically enforce arbitrary **global** invariants.

Suppose a system allows at most one active coupon per `tenantId + campaignId`. If two transactions concurrently read “no active coupon yet” and insert two different documents, without an appropriate unique constraint, **write skew** can occur depending on model and scheduling.

Stronger solution:

~~~javascript
db.coupons.createIndex(
  { tenantId: 1, campaignId: 1 },
  {
    unique: true,
    partialFilterExpression: { status: "ACTIVE" },
    name: "uq_active_coupon_per_campaign"
  }
)
~~~

Create this index **outside runtime transactions** and validate existing data and partial filter rules. The unique constraint blocks two active records sharing the key even under competing writers.

### 23.1. Snapshot Isolation Does Not Mean Every Operation Is Serializable

Suppose two doctors check “at least one doctor on call” and each cancels their own shift in **two different documents**. If they merely read the total and update their own document, the system can break the “always one doctor on call” invariant even though each transaction saw a valid snapshot. Model the invariant using a shared guard record with an atomic conditional update, unique constraint, or explicit coordination pattern.

### 23.2. Bounded Data Keeps Transactions Small

If an order embeds a small list of items, everything changes in one document. If you separate unbounded line items and immutable history, never build a transaction that touches the entire history just to update an order status.

## 24. Practical Error Handling: Do Not Retry Every Exception

Response matrix:

| Scenario | Typical Consequence | Response |
|---|---|---|
| `TransientTransactionError` | Attempt may abort due to transient fault | Retry **entire transaction** via driver/helper within budget |
| `UnknownTransactionCommitResult` | Unknown whether commit succeeded | Retry **commit** or reconcile via request identity |
| `TransactionTooLargeForCache` | Transaction exceeds cache capacity | Reduce scope/batch or redesign; do not retry identically forever |
| Transaction lifetime exceeded | Transaction expired | Shorten work, review timeouts; never blindly raise server limits |
| Lock timeout | Failed to acquire lock | Reduce contention/DDL overlap; retry with backoff if transient |
| `DuplicateKey` | Unique index violated | Reconcile business/idempotency key; never treat as generic transient |
| BSON document too large | Document exceeds 16 MiB | Redesign schema/payload; retries cannot fix |
| Unsupported command/stage | Operation disallowed in transaction | Move stage/DDL outside transaction or change approach |
| Validation error | Invalid data | Fix input data; do not retry unchanged |
| Application deadline | Client budget exhausted | Abort if still safe; reconcile if commit is uncertain |

### 24.1. Never Treat Every Timeout as a Rollback

A network error **before commit** differs from a lost response **after commit may have succeeded**. Driver error labels guide technical retries, while the application persists `requestId`/ledger entries to resolve business outcomes.

### 24.2. Retry Limits and Backoff

Pseudocode:

~~~javascript
// Illustrative orchestration pseudocode when no helper handles
// the corresponding retries. Never wrap an infinite retry around a retrying helper.
async function runWithBudget(operation, maxAttempts = 4) {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (error) {
      const transient =
        error.hasErrorLabel?.("TransientTransactionError");

      if (!transient || attempt === maxAttempts - 1) {
        throw error;
      }

      const base = Math.min(1000, 25 * (2 ** attempt));
      const jitter = 0.5 + Math.random();
      await new Promise(resolve =>
        setTimeout(resolve, Math.floor(base * jitter))
      );
    }
  }
}
~~~

Never apply this wrapper to `UnknownTransactionCommitResult` and re-run **the business operation** as a fresh transaction. When commit outcome is unknown, retry commit per protocol or reconcile rather than treating it as a transient body failure.

## 25. Monitoring Transactions on Server and Application

A transaction can fail on time or resource limits before the API gathers full context. Instrument both server and application layers.

### 25.1. `serverStatus().transactions`

When authorized:

~~~javascript
const stats = db.serverStatus()
printjson(stats.transactions)
~~~

Exact fields vary by version, typically reporting active, open, committed, and aborted counts along with related metrics. Never hardcode dashboards to every field of one version across multi-version fleets.

### 25.2. `currentOp` and Profiler/Logs

When authorized, inspect running operations, sessions, durations, lock waits, and related attributes using `currentOp` or profiler/diagnostic logs. Run administrative diagnostics **outside business transactions**.

### 25.3. Application Metrics to Track

| Metric | Meaning |
|---|---|
| `txn_duration_ms_p50/p95/p99` | How long transactions stay open |
| `txn_attempts_per_business_request` | Attempts needed per business intent |
| `txn_commit_latency_ms` | Duration of commit step |
| `txn_abort_count_by_error_code` | Breakdown of abort causes |
| `transient_retry_count` | Level of contention / transient faults |
| `unknown_commit_count` | Rate of uncertain commit outcomes |
| `txn_docs_modified` | Write footprint |
| `txn_bytes_changed_estimate` | Approximate operation scale |
| `lock_wait_ms` | Lock contention |
| `cache_pressure`, `eviction` | WiredTiger load |
| `replication_lag`, `majority_commit_latency` | Durability / failover impact |
| `idempotency_replay_count` | Detected API retries |

These are **suggested application metric names**, not built-in MongoDB metric names verbatim. Several must be aggregated from driver instrumentation and application logs.

### 25.4. Safe Session Logging

A log entry may include:

~~~text
traceId=...
tenantId=t-01
businessRequestId=transfer-R2
attempt=2
transactionDurationMs=...
commitOutcome=COMMITTED|ABORTED|UNKNOWN
errorCode=...
errorLabels=[...]
documentsModified=...
~~~

Never log passwords, full connection strings, or sensitive financial payloads. Use stable IDs to correlate attempts and reconciliation records.

## 26. Testing Time Limits in the Lab

**Run only on a lab replica set**; never force transaction timeouts by holding a real transaction open on production.

### 26.1. Inspecting Server Parameters

~~~javascript
db.adminCommand({
  getParameter: 1,
  transactionLifetimeLimitSeconds: 1
})
~~~

Record the actual value. If 60, that is the common default lifetime limit. Never alter parameters just to “demo errors” on shared environments.

### 26.2. Short Transaction

~~~javascript
const s = db.getMongo().startSession()
const d = s.getDatabase("txn_limits_lab")

try {
  s.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  d.wallets.findOne({ _id: "wallet-A" })
  d.wallets.updateOne(
    { _id: "wallet-A" },
    { $inc: { version: 1 } }
  )

  s.commitTransaction()
  print("COMMITTED")
} catch (err) {
  print(err.message)
  try { s.abortTransaction() } catch (_) {}
} finally {
  s.endSession()
}
~~~

### 26.3. Observing Long-Lived Transactions

To understand the lifetime threshold in an **isolated lab**, you can start a transaction, perform a read/write, wait past the server threshold in a controlled way, and then try committing. You will observe an aborted/expired transaction error, though **exact error codes are not guaranteed identical across versions**.

Never insert long `sleep` calls inside callbacks containing external side effects. In `mongosh`, ensure the session is always aborted/ended in every branch after testing. The core takeaway is not “force commit to fail at millisecond 60,000”, but **long-lived transactions are not a mechanism for long batches**.

## 27. Testing Restricted Operations

### 27.1. `$out` Inside a Transaction

On the lab database, test with a session:

~~~javascript
const s = db.getMongo().startSession()
const d = s.getDatabase("txn_limits_lab")

try {
  s.startTransaction()

  // $out stage is unsupported inside a transaction.
  d.wallets.aggregate([
    { $group: { _id: "$tenantId", n: { $sum: 1 } } },
    { $out: "wallet_summary" }
  ]).toArray()

  s.commitTransaction()
} catch (e) {
  printjson({
    code: e.code,
    codeName: e.codeName,
    message: e.message
  })
  try { s.abortTransaction() } catch (_) {}
} finally {
  s.endSession()
}
~~~

Expect an unsupported/incompatible operation error depending on server version. Never use this as a production pattern; run reporting outside transactions with versioning/cutover if needed.

### 27.2. Replacing with a Read-Only Aggregation

~~~javascript
const s = db.getMongo().startSession()
const d = s.getDatabase("txn_limits_lab")

try {
  s.startTransaction()

  const summary = d.wallets.aggregate([
    { $group: { _id: "$tenantId", wallets: { $sum: 1 } } }
  ]).toArray()

  printjson(summary)
  s.commitTransaction()
} catch (e) {
  print(e.message)
  try { s.abortTransaction() } catch (_) {}
} finally {
  s.endSession()
}
~~~

Read-only `$group` can be supported inside transactions, yet avoid opening a transaction solely to run a heavy reporting aggregation without an atomic multi-document need.

### 27.3. Using `countDocuments()`

In the Node.js Driver, use:

~~~javascript
const total = await wallets.countDocuments(
  { tenantId: "t-01" },
  { session }
);
~~~

inside a valid transaction callback instead of the legacy `count` command. If counting millions of documents to make write decisions, ensure proper indexes and evaluate snapshot/invariant design; huge counts can push transactions past lifetime limits.

## 28. Testing Write Conflict Contention in the Lab

Two `mongosh` sessions connected to the lab replica set, both modifying `wallet-A`:

### Session A

~~~javascript
use txn_limits_lab

const sessionA = db.getMongo().startSession()
const txA = sessionA.getDatabase("txn_limits_lab")
sessionA.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

printjson(txA.wallets.findOne({ _id: "wallet-A" }))

txA.wallets.updateOne(
  { _id: "wallet-A" },
  { $inc: { version: 1 } }
)

// Do not commit yet; switch to session B.
~~~

### Session B While A Is Still Open

~~~javascript
use txn_limits_lab

const sessionB = db.getMongo().startSession()
const txB = sessionB.getDatabase("txn_limits_lab")
sessionB.startTransaction({
  readConcern: { level: "snapshot" },
  writeConcern: { w: "majority" }
})

try {
  printjson(txB.wallets.findOne({ _id: "wallet-A" }))
  printjson(txB.wallets.updateOne(
    { _id: "wallet-A" },
    { $inc: { version: 1 } }
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

### Ending Sessions A and B

~~~javascript
// Session A:
try {
  sessionA.commitTransaction()
} finally {
  sessionA.endSession()
}

// Session B, inside session B only:
try { sessionB.abortTransaction() } catch (_) {}
sessionB.endSession()
~~~

When the two transactions overlap, B can hit a write conflict/transient error and abort. **Exact codes/labels are not guaranteed identical on every run**, as timing and locking vary. Once transaction B aborts, you cannot “continue committing” its old snapshot; start a new transaction and re-read the document.

## 29. When to Use Transactions vs. Alternative Models

| Case | Preferred Approach | Reason |
|---|---|---|
| Decrement stock of one SKU in one document | Conditional atomic `updateOne` | Invariant lives in one document; low overhead |
| Transfer points between two wallets + record ledger | Short multi-document transaction | Multiple documents must commit/abort together |
| Change order status + write outbox | Short transaction | Atomic between business state and event metadata |
| Import millions of records | Checkpointed batches | Giant transaction hits lifetime/cache limits |
| Export report via `$out`/`$merge` | Out-of-transaction job | Stages disallowed in transactions |
| Update system-wide price list | Versioned data + atomic pointer cutover | Avoids giant transaction updating all records |
| Multi-hour approval workflow | Saga / state machine | Never hold transactions open while waiting |
| External provider payment | Provider idempotency + outbox/reconciliation | MongoDB transactions cannot roll back network calls |
| Thousands of writers hitting one counter | Sharded counters / buckets or reduce contention | Transactions/retries do not fix hot keys at the root |
| Schema/index changes | Out-of-transaction runtime migrations | Avoids DDL locks and version restrictions |

## 30. Comprehensive Exercises

### Exercise A — Choosing Transaction vs. Atomic Update

For three tasks:

1. Deduct one unit of stock inside the same `inventory` document.
2. Debit wallet A, credit wallet B, and record a log.
3. Update 800,000 products to add a `searchVersion` field.

Choose the right approach and explain trade-offs.

### Exercise B — What Does 60 Seconds Mean?

A transaction starts at 10:00:00, calls a partner API taking 50 seconds, and then updates 3 documents taking 20 seconds. Why can the transaction abort? Where should the API call sit?

### Exercise C — Distinguishing Timeouts

Explain the differences among:

- `transactionLifetimeLimitSeconds`
- `maxCommitTimeMS`
- `serverSelectionTimeoutMS`
- `maxTransactionLockRequestTimeoutMillis`

Which controls whether the driver finds a primary? Which relates to a transaction staying alive too long?

### Exercise D — “Transactions Are Max 16 MB”

Evaluate this claim. Is a transaction modifying 10,000 small documents totaling over 16 MiB always rejected? What real limits must be accounted for?

### Exercise E — Single Oversized Document

An order document embeds 20,000 items, producing BSON over 16 MiB. Does wrapping the insert in a transaction solve it? Propose two data modeling alternatives.

### Exercise F — Cache

A transaction contains 200,000 updates, and every attempt fails with `TransactionTooLargeForCache`. Is raising retries to 100 sensible? Propose batching/checkpoints.

### Exercise G — Restricted Commands

Given:

~~~javascript
db.orders.aggregate([
  { $group: { _id: "$status", n: { $sum: 1 } } },
  { $merge: { into: "daily_status" } }
])
~~~

Should this run inside a transaction? If a consistently materialized report is required, how else can you build it?

### Exercise H — Index Creation

An app wants each tenant to create a new collection inside a request transaction. Why check version, sharding, and DDL restrictions? Why is pre-creating schemas easier to operate?

### Exercise I — Transaction Retry

Two transactions concurrently modify `wallet-A`; one attempt receives `TransientTransactionError`. Should you retry the entire transaction or only the final update? Why?

### Exercise J — Unknown Commit

The driver sends `commitTransaction`; the DB commits, yet the client drops connection. Can the app create a new transfer with a different `requestId` “to be sure it ran”? Design the reconciliation step.

### Exercise K — Parallel Commands

In Node.js:

~~~javascript
await session.withTransaction(async () => {
  await Promise.all([
    updateWalletA({ session }),
    updateWalletB({ session })
  ]);
});
~~~

Why should operations in the same transaction not run in parallel like this?

### Exercise L — Multi-Shard Workload

A transaction must write across 5 shards and stays open nearly 50 seconds. List sources of risk compared to a single-shard transaction and propose design improvements.

### Exercise M — Write Skew

Two transactions both observe two staff on duty, then each takes one off duty in two separate documents. Why does snapshot alone fail to enforce “always one person on duty”? Design an alternative invariant.

### Exercise N — Outbox

A transaction updates an order and sends an email directly inside the callback. If the callback retries, what happens? Convert to an outbox and explain why consumers still need deduplication.

### Exercise O — Monitoring

Design a metric table covering p95/p99 transaction duration, aborts by reason, write conflicts, lock waits, cache pressure, and majority commit latency. Base alert thresholds on real baselines rather than invented universal numbers.

## 31. Suggested Answers

**Exercise A:** Single document uses conditional atomic update. Wallet transfer + ledger needs a short multi-document transaction. Large import uses checkpointed batches or versioned migration.

**Exercise B:** The transaction exceeds the typical 60-second lifetime and can abort. Place the API call outside the transaction; the transaction should only check and commit required DB preconditions.

**Exercise C:** Server selection bounds finding a node; transaction lifetime bounds transaction age; `maxCommitTimeMS` bounds commit; lock request timeout bounds lock waits. None substitute for each other.

**Exercise D:** Claiming “16 MiB total transaction limit” is inaccurate for modern versions supporting multiple oplog entries. Individual documents remain capped at 16 MiB, individual oplog entries have limits, and total volume remains constrained by cache, lifetime, and resources.

**Exercise E:** Transactions do not raise document limits. Split items into referenced documents pointing to the order, or move large binaries/blobs to dedicated storage (such as GridFS for files).

**Exercise F:** Retrying an oversized transaction identically repeats the failure. Split into small batches, checkpoint inside each transaction, tune indexes, and shrink duration.

**Exercise G:** `$merge` is disallowed inside transactions. Run the job outside transactions using versioned materialized reports and an atomic pointer cutover or appropriate consistency pattern.

**Exercise H:** In-transaction DDL faces version, read concern, and cross-shard limits. Pre-creating collections/indexes via migrations reduces metadata lock risks and runtime errors.

**Exercise I:** Retry the whole transaction and re-read data against a fresh snapshot. Never carry forward conditions from an aborted attempt.

**Exercise J:** Never generate a new `requestId`. Retry commit via the helper or reconcile the ledger for the original `requestId`; if unresolved, return `PENDING`/`UNKNOWN` per API contract.

**Exercise K:** The Node Driver does not support parallel operations inside one transaction via `Promise.all`. Run sequentially and manage the same session explicitly.

**Exercise L:** Adds routing, network, coordinator, commit latency, failover/chunk migration, and contention risks. Reduce touched shards and transaction lifetime; consider versioned workflows/sagas if cross-shard atomicity is unnecessary.

**Exercise M:** Two transactions can modify two different documents based on a shared aggregate invariant, causing write skew. Use a shared guard document, conditional counter, or data model constraint to force real write conflicts.

**Exercise N:** Callback retries can send the email twice even if the DB only commits once. Write an outbox entry inside the transaction, have a relay publish post-commit, and deduplicate by event ID in the consumer.

**Exercise O:** Focus on p95/p99 trends, abort rates, locks/cache, commit latency, and throughput impact; tune thresholds to SLOs and measured baselines.

## 32. Review Questions

**1. Why does MongoDB enforce a transaction lifetime limit?**

Because long transactions pin snapshots/resources and increase contention, cache pressure, and recovery costs. The server bounds lifetime so transactions cannot hold resources indefinitely.

**2. What is the typical default transaction lifetime?**

Usually **60 seconds**, controlled by `transactionLifetimeLimitSeconds`. Verify the actual value in your deployment.

**3. Does a transaction exceeding 60 seconds always abort at millisecond 60,000?**

Never assume exact millisecond timing. Background cleanup handles expiry and other errors can occur sooner; set application deadlines comfortably below the threshold.

**4. Does `maxCommitTimeMS` replace `transactionLifetimeLimitSeconds`?**

No. One bounds commit; the other bounds transaction age. Design overall deadlines and error handling for both.

**5. Can a single BSON document inside a transaction exceed 16 MiB?**

No. The BSON document limit still applies.

**6. Is a modern transaction always capped at 16 MiB total?**

No. Modern versions can emit multiple oplog entries per transaction; total transaction scale remains bounded by other resource limits.

**7. Does `allowDiskUse: true` solve the 16 MiB document limit?**

No. It applies to spill-capable aggregation stages; it neither raises the BSON document limit nor rescues a transaction too large for cache.

**8. Can a transaction containing hundreds of thousands of updates fail even if every document is tiny?**

Yes. Lifetime, WiredTiger cache, contention, oplog/storage load, and topology still impose real limits.

**9. Should `TransactionTooLargeForCache` be retried indefinitely?**

No. Shrink the transaction/batch, adjust the data model, or scale resources; identical retries tend to fail repeatedly.

**10. Are `$out` and `$merge` allowed inside transactions?**

No. Run materialization outside transactions or use an alternative versioned output workflow.

**11. Can `countDocuments()` be used inside a transaction?**

Yes in supported scenarios; it runs via aggregation. The legacy `count` command is not supported the same way.

**12. Can collections or indexes ever be created inside a transaction?**

Supported in certain cases since MongoDB 4.4, subject to version, read concern, and topology constraints—especially in sharded transactions. Pre-creating schemas is usually safer at runtime.

**13. Can `Promise.all()` run two updates concurrently in one Node.js transaction?**

No; the Node.js Driver does not support parallel operations within one transaction. Run sequentially.

**14. What action does `TransientTransactionError` call for?**

Abort the attempt and retry the **entire transaction** per driver protocol within a budget, re-reading state.

**15. What action does `UnknownTransactionCommitResult` call for?**

Retry commit properly or reconcile via an idempotency ledger; never assume non-commit and issue a new business intent.

**16. Why avoid calling payment APIs inside a transaction callback?**

Callbacks can retry, external payments do not roll back with MongoDB, and network calls stretch transactions toward lifetime limits.

**17. Why is a single-document update usually better than a multi-document transaction for a simple invariant?**

Atomic single-document updates are simpler, carry less overhead, and avoid pinning snapshots or coordinating multi-document commits.

**18. Do transactions automatically guarantee every business invariant?**

No. Snapshot isolation and write conflicts do not prevent all write skew across distinct documents; constraints must still be modeled properly.

**19. Can you split a huge job into multiple transactions while keeping whole-job atomicity?**

Not automatically. Each batch is atomic on its own; for readers to observe a complete cutover, design versioning/cutover or another model.

**20. Why are cross-shard transactions usually more expensive than single-shard transactions?**

They require routing, inter-shard communication, and distributed commit coordination, adding failure modes and commit latency.

## 33. Common Mistakes

| Mistake | Problem | Fix |
|---|---|---|
| Assuming transactions can run arbitrarily long | Lifetime expires, pins resources | Keep transactions short with clear deadlines |
| Raising lifetime to rescue huge batches | Cache/contention issues persist | Split into checkpointed batches |
| Confusing 16 MiB document limit with total transaction limit | Incorrect capacity design | Distinguish BSON docs, oplog entries, and resource limits |
| Assuming multiple oplog entries mean unlimited transactions | Cache, lifetime, and I/O still cap scale | Benchmark load and narrow scope |
| Retrying every transaction error identically | Permanent errors loop; unknown commits double-apply | Classify by codes, labels, and outcomes |
| Calling HTTP/email/payments inside transactions | No rollback; callback retries duplicate side effects | Outbox / external idempotency |
| `Promise.all` on one transaction session | Unsupported in Node Driver | `await` sequentially |
| Putting `$out`/`$merge` inside transactions | Unsupported stage | Run outside transactions |
| Putting arbitrary DDL inside transactions | Version/topology/lock restrictions | Run migrations outside; verify support |
| Unindexed queries inside transactions | Slow scans cause timeouts | Optimize indexes and filters |
| Using transactions for long reporting reads | Pins snapshots and adds load | Read-only queries outside transactions or appropriate snapshot models |
| Confusing `matchedCount=0` with `WriteConflict` | Broken business handling | Separate conditional failures from transient aborts |
| Concluding timeout equals non-commit | Risk double-applying on retry | Request ledger and reconciliation |
| Transactions unnecessarily hitting multiple shards | Higher commit latency and failure modes | Shard-key-aware design |
| Forgetting unique index on `requestId` | Concurrent retries duplicate side effects | Idempotency ledger + unique constraint |
| Believing snapshot prevents all write skew | Aggregate invariants can still break | Guard documents, unique constraints, data modeling |
| Testing on standalone `mongod` | Multi-document transactions cannot run | Use a replica set lab |
| Not monitoring p95/p99 duration | Problems surface only after production overload | Instrumentation, alerts, and SLOs |

## 34. Quick Reference Table

| Need | Tool / Principle |
|---|---|
| Check transaction lifetime | `db.adminCommand({getParameter:1,transactionLifetimeLimitSeconds:1})` |
| Check lock wait parameter | `db.adminCommand({getParameter:1,maxTransactionLockRequestTimeoutMillis:1})` |
| Start `mongosh` session | `db.getMongo().startSession()` |
| Start transaction | `session.startTransaction({readConcern:{level:"snapshot"},writeConcern:{w:"majority"}})` |
| Commit | `session.commitTransaction()` |
| Abort | `session.abortTransaction()` |
| Node Driver helper | `session.withTransaction(async()=>{...})` |
| Commit time budget | `maxCommitTimeMS` in transaction options per driver |
| Transient errors | Retry whole transaction per label and budget |
| Unknown commit | Retry commit / reconcile, keep same `requestId` |
| BSON document limit | 16 MiB **per document** |
| Large batch writes | Multiple short transactions + checkpoints |
| Materialization commands | `$out`/`$merge` outside transactions |
| Data migration | Pre-create collections/indexes, versioned cutover |
| Monitor transactions | `db.serverStatus().transactions`, `currentOp`, metrics |
| Reduce lock/cache pressure | Short transactions, solid indexes, small write scope |
| External events | Transactional outbox + consumer deduplication |

## 35. Pre-Production Transaction Checklist

- [ ] Is **multi-document atomicity** genuinely required, or is one atomic update enough?
- [ ] How many documents, collections, and shards does the data touch?
- [ ] Are all operations permitted inside transactions on your server version?
- [ ] Are collections and indexes pre-created before runtime to avoid unexpected DDL?
- [ ] Are HTTP requests, emails, payments, and user waits kept outside transactions?
- [ ] Are batch sizes, touched document counts, and estimated bytes bounded for real load?
- [ ] Does every document stay under 16 MiB without confusing it with total transaction size?
- [ ] Have WiredTiger cache, disk, oplog, and replication health been evaluated?
- [ ] Are reads, filters, and updates inside transactions backed by good indexes?
- [ ] Is the application deadline shorter than server lifetime, with lock/commit timeout handling?
- [ ] Are read concern, write concern, and read preference chosen for business consistency?
- [ ] Do all commands use the same session and execute sequentially in Node.js?
- [ ] Since retry helpers can re-invoke callbacks, are non-DB side effects excluded?
- [ ] Are transient aborts, unknown commits, duplicate keys, BSON size, and cache errors distinguished?
- [ ] Are unique business constraints/idempotency keys in place for HTTP retries?
- [ ] Can outcomes be reconciled after lost commit responses?
- [ ] For sharded clusters, have cross-shard writes, DDL, and chunk migrations been checked?
- [ ] For long workflows, have checkpointed batches, sagas, or versioned cutovers been considered?
- [ ] Were transaction duration, abort reasons, lock waits, and cache measured in a representative environment?
- [ ] Is there a rollback/mitigation plan if transaction changes degrade throughput?

## 36. Conclusion

MongoDB transactions solve **multi-write atomicity** within a supported scope, yet come with **time, cache, size, and operation limits**. Default lifetime is typically around 60 seconds; individual BSON documents remain capped at 16 MiB; modern versions can emit multiple oplog entries for a transaction, which **does not make transactions unbounded**. Commands like `$out`, `$merge`, certain DDL/admin operations, and special namespaces carry specific restrictions. Distributed transactions add coordination overhead and topology constraints.

The solid strategy is **keeping transactions small, short, and focused on business invariants**, pre-creating schemas and indexes, querying via strong indexes, configuring sessions and concerns accurately, handling `TransientTransactionError` and `UnknownTransactionCommitResult` differently, and keeping external side effects out of transaction callbacks. For multi-million-document tasks or long workflows, use **checkpointed batches, outboxes, sagas, or versioned cutovers** instead of stretching a single transaction to cover everything.
