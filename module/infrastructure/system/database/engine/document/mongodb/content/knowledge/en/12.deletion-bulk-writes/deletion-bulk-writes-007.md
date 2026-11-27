# Batching Large Tasks, Throttling, and Checkpointing in MongoDB

When a MongoDB collection contains millions of documents, deleting old data, updating statuses in bulk, or migrating schemas must be organized as a **controllable, resumable job**. A single command operating on too many documents can run for a long time, spike CPU, I/O, and replication load, be hard to pause, and leave you uncertain which items finished if the process is interrupted.

Three techniques are commonly combined:

1. **Batching:** select and write only a bounded group of documents on each pass.
2. **Throttling:** limit processing rate or concurrency so the job does not unduly impact user-facing queries.
3. **Checkpointing:** durably record the last safely processed position so the next run resumes right where it left off.

A reliable job also requires **safely repeatable operations (idempotency)**. Checkpointing and idempotency go hand in hand: a process can crash after writing data successfully yet before saving its checkpoint, meaning part of the work may be re-executed.

This lesson uses the **deletion and bulk writes** context in MongoDB, with examples in `mongosh`, the Node.js Driver, the Java Driver, and patterns for organizing jobs over millions of documents.

## 1. Why Not Always Use One `updateMany` or `deleteMany`?

Suppose the **audit.events** collection contains 20 million events. You need to delete expired events or mark old documents as archived.

A simple command might be:

~~~javascript
db.events.deleteMany({
  expiredAt: { $lte: new Date() }
});
~~~

Or:

~~~javascript
db.events.updateMany(
  { status: "OLD" },
  { $set: { archived: true } }
);
~~~

These are valid APIs. For small datasets, they may fit well. For large jobs, however, you must also consider:

- **Workload volume:** MongoDB must locate, update, or delete many documents along with their associated index entries.
- **System impact:** writes consume resources on the primary; replica sets must also ship and apply oplog entries.
- **Observability:** there is no application checkpoint showing which batches have finished.
- **Interruptibility and resumption:** on timeouts, network errors, or process termination, you cannot assume either every document was processed or none were.
- **Concurrent data changes:** documents may be inserted or modified while the job runs.
- **Atomicity scope:** standard `updateMany` and `deleteMany` guarantee atomicity only **per individual document**, not all-or-nothing across the entire set outside a transaction.

**One API call does not equal a multi-document transaction.** If an `updateMany` modifies a subset of documents and then encounters an error, the application must inspect and handle the remainder according to the operation's semantics.

Batching does not reduce the total work by itself. Its value comes from **capping the size of each pass, creating pause points, and tracking progress**.

## 2. Three Boundaries of a Large Processing Job

A job can be broken down into processing loops:

~~~text
                          Fixed job configuration
                    (filter, cutoff, batch size)
                                  |
                                  v
                       Read last checkpoint
                                  |
                                  v
                         Select up to N IDs
                                  |
                                  v
                      Batch delete / update
                                  |
                      +-----------+-----------+
                      |                       |
                   SUCCESS                  ERROR
                      |                       |
                      v                       v
               Save checkpoint          Stop, log error
                      |                 Do not advance past
                      v                  unprocessed items
                 Pause/throttle
                      |
                      v
                    Repeat
~~~

Three boundaries to distinguish:

| Boundary | Question | Example |
| --- | --- | --- |
| **Read batch** | How many IDs/documents are fetched per pass? | 500 IDs ordered by `_id` |
| **Write batch** | How many updates/deletes are sent per call? | One `bulkWrite` containing up to 500 `deleteOne` ops |
| **Checkpoint** | When is progress past a sort key confirmed complete? | Only after the entire `bulkWrite` completes successfully |

One read batch can drive multiple write calls, or one `bulkWrite` can hold many operations. **Never advance a batch checkpoint while any write call's outcome remains uncertain.**

## 3. Designing the Job Scope Before Running

Suppose each event looks like:

~~~javascript
{
  _id: ObjectId("672000000000000000000001"),
  status: "EXPIRED",
  expiredAt: ISODate("2026-01-10T00:00:00Z"),
  accountId: "ACC-01",
  payload: {
    action: "LOGIN",
    result: "SUCCESS"
  }
}
~~~

The job must delete events currently in **EXPIRED** status whose expiration is on or before a **fixed cutoff**.

~~~javascript
const cutoff = ISODate("2026-11-01T00:00:00Z");

const filter = {
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
};
~~~

A fixed cutoff prevents the scope of a single job from drifting over time. If every resume re-evaluated **new Date()**, the deletion scope would expand continuously, making the job run longer than planned and hard to reconcile.

### 3.1. What Information Should Stay Stable?

A job descriptor should track:

- **jobId:** unique identifier, e.g., `cleanup-events-2026-11`.
- **Collection and business filter:** which data is eligible for mutation.
- **Cutoff and invariant parameters:** timestamp boundary, rule version.
- **Sort key:** the field used for traversal, e.g., `_id`.
- **Checkpoint:** the last key completely processed.
- **Status:** `RUNNING`, `PAUSED`, `DONE`, or `FAILED`.
- **Operational metrics:** batches completed, last updated time, error count, reported affected documents.

If a job already ran with cutoff A, never silently resume the same `jobId` with cutoff B. Start a new job or follow a controlled scope-change procedure.

### 3.2. Is the Dataset Scope Truly Static?

Even with a fixed cutoff, documents can still be inserted, updated, or deleted concurrently:

- A new event may be inserted with an old `expiredAt` from historical backfills.
- A document may change status from `ACTIVE` to `EXPIRED` after the job's cursor already passed its `_id`.
- An `EXPIRED` document may have its expiration extended, becoming ineligible for deletion.

Consequently, a job using keyset pagination over live mutating data has the semantics of **traversing eligible documents observed along the scan**, not a globally immutable snapshot.

If business rules require processing **the exact list of documents that existed at start time**, design an explicit snapshot scope, an immutable ID list, or a dedicated work-item queue. A timestamp cutoff alone does not turn a collection into a snapshot.

## 4. Choosing a Batch Size

There is no single optimal batch size for every collection. The right size depends on document size, index count, update/delete type, topology, network, and application load.

A practical starting point is a few hundred documents per pass, then measure:

~~~text
Batch size = 100   -> many small passes, easy to interrupt, higher overhead
Batch size = 500   -> moderate baseline for testing
Batch size = 2000  -> fewer loop iterations, though each pass can be heavier
~~~

These numbers are **starting points for testing**, not universal optima or official API limits.

### 4.1. Batches Too Small

- Higher per-command network and setup overhead.
- Frequent checkpoint reads and job-state updates.
- Longer total runtime even though each pass has low impact.

### 4.2. Batches Too Large

- Spikes in I/O and replication traffic.
- Harder to bound per-batch latency.
- Larger set of indeterminate writes if an error occurs.
- Higher risk of hitting message size, operation count, or driver memory limits.

MongoDB and drivers enforce limits on write batches and BSON size. While a driver may split operations into multiple wire batches, that **does not turn `bulkWrite` into an atomic transaction**. The application must still chunk work sensibly.

### 4.3. Do Not Confuse `limit`, `batchSize`, and Write Batches

| Concept | Meaning |
| --- | --- |
| **find().limit(N)** | Caps how many documents the query returns to process in this pass |
| **cursor.batchSize(N)** | Hints how many documents to fetch per cursor network batch; does not limit total results |
| **bulkWrite([...])** | Sends a list of write operations via the driver API |
| **deleteMany(filter)** | Deletes every document matching the filter per command semantics; has no `limit` parameter like `find` |
| **updateMany(filter, update)** | Updates every matching document; has no document-count `limit` parameter |

To **delete at most 500 documents per pass**, the explicit approach is to **select up to 500 IDs** and issue `deleteOne` operations for those IDs, or define a pre-bounded deletion scope.

## 5. Traversing by a Stable Key: Keyset Pagination

On large collections, using **skip()** to paginate while deleting can **skip documents**.

Initial example:

~~~text
IDs: [1, 2, 3, 4, 5, 6]
Batch size: 3
~~~

First pass:

~~~text
skip(0).limit(3) -> [1, 2, 3]
Delete [1, 2, 3]
Remaining [4, 5, 6]
~~~

If the second pass runs:

~~~text
skip(3).limit(3) -> []
~~~

the three remaining documents are missed because deleting `[1, 2, 3]` shifted them to the front. Beyond correctness bugs, deep `skip()` offsets are also expensive.

### 5.1. Using `_id` as the Cursor Key

For collections where `_id` shares a single consistent data type and sort order:

~~~javascript
// First pass: no lastId.
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
})
.sort({ _id: 1 })
.limit(500)
.project({ _id: 1 });
~~~

After completing a batch, persist the last traversed ID:

~~~text
lastId = ID of the 500th document in the batch
~~~

On the next pass, fetch only documents with `_id` greater than `lastId`:

~~~javascript
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff },
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(500)
.project({ _id: 1 });
~~~

This is **keyset pagination**: resumption is anchored by key value, not by skipping row counts.

**`_id` does not automatically represent exact creation chronology.** An `ObjectId` embeds a timestamp component yet does not guarantee strict global time order across all systems; `_id` could also be a string, UUID, or another type. Here `_id` is used because it provides a **deterministic traversal order**, not as a reliable clock.

### 5.2. Needing a Total, Consistent Ordering

In an unsharded collection, MongoDB maintains a unique index on `_id`. In a sharded collection where `_id` is not the shard key, `_id` uniqueness **is not necessarily enforced globally across shards** by the `_id` index alone. Distributed job designs must use keys that uniquely identify documents—typically incorporating the **shard key** and needed tie-breakers.

If a sort key allows duplicates such as `createdAt`, saving only `createdAt` can miss documents sharing the same timestamp. Use a **composite key** for the checkpoint.

### 5.3. Composite Checkpoint `(createdAt, _id)`

Traverse by:

~~~javascript
.sort({ createdAt: 1, _id: 1 })
~~~

Suppose the processed checkpoint is:

~~~javascript
{
  createdAt: ISODate("2026-01-01T10:00:00Z"),
  _id: ObjectId("672000000000000000000123")
}
~~~

The next pass must fetch:

- Documents with `createdAt` **greater than** the checkpoint `createdAt`; or
- Documents with `createdAt` **equal to** the checkpoint and `_id` **greater than** the checkpoint `_id`.

~~~javascript
const lastCreatedAt = ISODate("2026-01-01T10:00:00Z");
const lastId = ObjectId("672000000000000000000123");

db.events.find({
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
})
.sort({ createdAt: 1, _id: 1 })
.limit(500);
~~~

Depending on filter conditions and workload, a supporting index could be:

~~~javascript
db.events.createIndex({ createdAt: 1, _id: 1 });
~~~

The **(createdAt, _id)** pair yields a far more deterministic cursor than a timestamp alone. Still, if `createdAt` is mutated after traversal, documents can jump ahead of or behind the checkpoint. Cursor fields for long-running jobs should be **stable or immutable per the data contract**.

## 6. Batch Writing with `bulkWrite`

MongoDB Drivers provide **bulkWrite** to send multiple operations in a single API call:

~~~javascript
const operations = [
  {
    deleteOne: {
      filter: { _id: ObjectId("672000000000000000000001") }
    }
  },
  {
    deleteOne: {
      filter: { _id: ObjectId("672000000000000000000002") }
    }
  },
  {
    updateOne: {
      filter: { _id: ObjectId("672000000000000000000003") },
      update: { $set: { archived: true } }
    }
  }
];

const result = db.events.bulkWrite(operations, {
  ordered: false
});

printjson(result);
~~~

Available operation models:

- **insertOne:** inserts one document.
- **updateOne:** updates one matching document.
- **updateMany:** updates all matching documents.
- **replaceOne:** replaces an entire document.
- **deleteOne:** deletes one matching document.
- **deleteMany:** deletes all matching documents.

For jobs aimed at **capping documents per batch**, a list of **`deleteOne`/`updateOne` ops targeting selected IDs** is far easier to bound than an uncapped `deleteMany`/`updateMany`.

### 6.1. `ordered: true` vs. `ordered: false`

| Option | Meaning | Behavior on error |
| --- | --- | --- |
| **ordered: true** | Driver/server executes operations in declared order | Typically halts subsequent operations after a write error |
| **ordered: false** | Does not require preserving per-op order; may optimize execution | Remaining operations can still be attempted despite an error |

**`ordered: false` does not guarantee every operation succeeds**, nor does it create an atomic transaction. On failure, some documents may have been written while others have not.

For independent operations—such as deleting distinct IDs—unordered execution works well. For order-dependent chains, review the model; even ordered mode does not provide all-or-nothing rollback.

### 6.2. One `bulkWrite` Is Not a Transaction

Suppose a batch holds 500 operations:

~~~text
Operation 1..200    succeeded
Operation 201       failed due to validation
Operation 202..500  may continue if unordered
~~~

Never assume the entire batch succeeded just because many documents were updated. The driver can throw an exception carrying info on successes and failures. When a batch's outcome is uncertain, **keep the pre-batch checkpoint** and reprocess safely.

If multiple documents truly must commit or roll back together, multi-document transactions fit certain problems. However, **one giant transaction merely to replace batching is rarely right for maintenance jobs over millions of documents**: transactions impose time limits, resource consumption, write contention, and operational cost.

## 7. Idempotency: The Prerequisite for Safe Resumption

Suppose a job fetches a batch of 500 IDs and `bulkWrite` succeeds. Immediately afterward, the process crashes **before saving the checkpoint**.

~~~text
Checkpoint before batch: lastId = 100
BulkWrite: delete IDs 101..600 succeeded
Crash!
Checkpoint is still 100
Restart -> re-select after ID 100
~~~

The system may replay part of the work. **Exactly-once execution** does not come for free just from checkpointing. Practical designs rely on **at-least-once attempts + idempotent operations** to preserve correct business outcomes.

### 7.1. Deleting by ID Is Usually Safe to Replay

~~~javascript
db.events.deleteOne({
  _id: ObjectId("672000000000000000000001")
});
~~~

If the document is already deleted, re-running `deleteOne` deletes no other document and returns **`deletedCount = 0`**. This makes ID-targeted deletion well-suited for retries in cleanup jobs.

Include active business conditions in the delete filter:

~~~javascript
db.events.deleteOne({
  _id: ObjectId("672000000000000000000001"),
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
});
~~~

If the document had its expiration extended or status changed after ID selection, the guard prevents deleting a document **that is no longer eligible**.

### 7.2. `$set` to a Target Value Is Usually Idempotent

~~~javascript
db.events.updateOne(
  { _id: eventId, archived: { $ne: true } },
  {
    $set: {
      archived: true
    }
  }
);
~~~

Even if re-sent, the final state remains **`archived: true`**. Note that if you also set **`updatedAt: new Date()`** on every attempt, the timestamp shifts on retries. Evaluate idempotency across **the entire domain effect**, not just a single field.

### 7.3. `$inc` Is Not Idempotent by Default

~~~javascript
db.accounts.updateOne(
  { _id: "A-01" },
  { $inc: { points: 10 } }
);
~~~

If run twice, points increase by **20**, not 10. Likewise, **`$push`** can append duplicate elements on retry, and inserts with newly generated random IDs can create duplicate business records.

When non-idempotent mutations are required, design an idempotency key or state marker so each job affects each target at most once.

Example of a local marker inside the same document:

~~~javascript
const jobId = "reward-backfill-v1";

db.accounts.updateOne(
  {
    _id: "A-01",
    processedJobs: { $ne: jobId }
  },
  {
    $inc: { points: 10 },
    $addToSet: { processedJobs: jobId }
  }
);
~~~

Because both the guard and the mutation live on one document, they execute atomically together. On retry, the marker prevents double-crediting once `jobId` is present.

**Limitation:** an unbounded `processedJobs` array can grow documents indefinitely. In production systems, consider a separate processing ledger, expiring idempotency keys, or an alternate job design, while respecting atomicity boundaries across related documents.

### 7.4. Checkpoints Do Not Replace Idempotency

A checkpoint only records **how far the cursor reached**. It does not prove external side effects executed once. If a batch writes to MongoDB while also calling HTTP APIs or sending emails, implement idempotency/outbox patterns for those external effects as well.

## 8. Where Should Checkpoints Be Stored?

A common pattern is a dedicated job-state collection, such as **maintenance.jobs**.

Illustrative document:

~~~javascript
{
  _id: "cleanup-expired-events-2026-11",
  collection: "audit.events",
  status: "RUNNING",
  cutoff: ISODate("2026-11-01T00:00:00Z"),
  batchSize: 500,
  lastId: ObjectId("672000000000000000000123"),
  batchesDone: 24,
  deletedReported: 11750,
  updatedAt: ISODate("2026-11-14T04:00:00Z"),
  lastError: null
}
~~~

**lastId** marks the end of the last completed batch, not an in-flight batch. **deletedReported** merely sums deletes reported back to the client when updating checkpoints; it can undercount writes that succeeded right before a crash. If exact deletion totals are needed for compliance audits, use a stronger tracking mechanism.

### 8.1. Job States

~~~text
CREATED
   |
   v
RUNNING -----> PAUSED
   |              |
   |              v
   |           RUNNING
   |
   +----------> FAILED
   |              |
   |              v
   |           RUNNING (after error remediation)
   |
   +----------> DONE
~~~

- **CREATED:** configuration fixed, not yet started.
- **RUNNING:** making progress or actively processing.
- **PAUSED:** intentionally paused at a safe checkpoint.
- **FAILED:** halted on an error needing intervention; checkpoint preserved.
- **DONE:** finished scanning the scope visible under the chosen traversal strategy.

`DONE` does not automatically prove no document became eligible **behind the cursor** while the job ran. For dynamic data, plan follow-up scans or fresh runs.

### 8.2. Checkpoint Write Order

For every batch:

1. Fetch IDs starting after the saved checkpoint.
2. Execute all write operations in the batch.
3. Verify the batch completed per the job's success criteria.
4. **Only then save `lastId` = last ID of the selected batch.**
5. Advance to the next batch.

Never save `lastId` right after reading before writes are confirmed. If a write fails after the checkpoint already advanced past its ID, resuming will skip that document.

For partial errors, there are two main strategies:

- **Hold the checkpoint and retry the batch** using idempotent operations.
- **Track outcomes per ID**, isolating failing IDs while only advancing past them once reliable retry/remediation tracking is in place.

The first strategy is simpler for ID-based deletes or conditional `$set` updates. The second fits workloads with frequent bad records needing quarantine, provided unattempted IDs cannot be dropped.

## 9. Complete Node.js Example: Batched Deletion and Resumption

The following example uses the MongoDB Node.js Driver. The job:

- Deletes events with **status = EXPIRED** and **expiredAt <= cutoff**.
- Reads at most **500 IDs** per pass, sorted by `_id`.
- Writes via `bulkWrite` using conditional `deleteOne` ops.
- Saves `lastId` **only after `bulkWrite` succeeds**.
- Pauses briefly between batches.
- Stops cleanly after a batch budget so the next scheduled run can resume.

This example assumes an unsharded collection (or globally ordered unique `_id`s), consistent BSON type across `_id`s, and **at most one active executor per `jobId`**. Multi-executor locking is covered in the next section.

~~~javascript
import { MongoClient } from "mongodb";

const uri = process.env.MONGODB_URI;
if (!uri) {
  throw new Error("Missing MONGODB_URI environment variable");
}

const JOB_ID = "cleanup-expired-events-2026-11";
const CUTOFF = new Date("2026-11-01T00:00:00.000Z");
const BATCH_SIZE = 500;
const PAUSE_MS = 200;
const MAX_BATCHES_PER_RUN = 100;

const client = new MongoClient(uri);

function pause(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function run() {
  await client.connect();

  try {
    const events = client.db("audit").collection("events");
    const jobs = client.db("maintenance").collection("jobs");

    // Create initial state only if the job does not yet exist.
    await jobs.updateOne(
      { _id: JOB_ID },
      {
        $setOnInsert: {
          status: "RUNNING",
          cutoff: CUTOFF,
          lastId: null,
          batchesDone: 0,
          deletedReported: 0,
          createdAt: new Date()
        }
      },
      { upsert: true }
    );

    const job = await jobs.findOne({ _id: JOB_ID });

    // Never resume an existing job with a new cutoff.
    if (!(job.cutoff instanceof Date) ||
        job.cutoff.getTime() !== CUTOFF.getTime()) {
      throw new Error("Job cutoff mismatch");
    }

    if (job.status === "DONE") {
      console.log("Job already completed");
      return;
    }

    let lastId = job.lastId ?? null;
    let batchesThisRun = 0;

    while (batchesThisRun < MAX_BATCHES_PER_RUN) {
      const query = {
        status: "EXPIRED",
        expiredAt: { $lte: CUTOFF },
        ...(lastId === null
          ? {}
          : { _id: { $gt: lastId } })
      };

      const batch = await events.find(query, {
        projection: { _id: 1 }
      })
      .sort({ _id: 1 })
      .limit(BATCH_SIZE)
      .toArray();

      if (batch.length === 0) {
        const finish = await jobs.updateOne(
          { _id: JOB_ID, lastId },
          {
            $set: {
              status: "DONE",
              completedAt: new Date()
            }
          }
        );

        if (finish.matchedCount !== 1) {
          throw new Error("Checkpoint changed");
        }

        console.log("No more matching documents after checkpoint");
        break;
      }

      const operations = batch.map(({ _id }) => ({
        deleteOne: {
          filter: {
            _id,
            status: "EXPIRED",
            expiredAt: { $lte: CUTOFF }
          }
        }
      }));

      // If bulkWrite throws, do not save checkpoint.
      // Some deleteOne ops may have succeeded; retrying is safe
      // because deletion targets IDs with business conditions.
      const result = await events.bulkWrite(operations, {
        ordered: false
      });

      const newLastId = batch[batch.length - 1]._id;

      const saved = await jobs.updateOne(
        { _id: JOB_ID, lastId },
        {
          $set: {
            lastId: newLastId,
            status: "RUNNING",
            updatedAt: new Date()
          },
          $inc: {
            batchesDone: 1,
            deletedReported: result.deletedCount
          }
        }
      );

      if (saved.matchedCount !== 1) {
        throw new Error("Failed to persist checkpoint as expected");
      }

      lastId = newLastId;
      batchesThisRun += 1;

      console.log({
        batchesThisRun,
        lastId,
        deleted: result.deletedCount
      });

      await pause(PAUSE_MS);
    }
  } finally {
    await client.close();
  }
}

run().catch((error) => {
  console.error("Job stopped; can resume from checkpoint", error);
  process.exitCode = 1;
});
~~~

### 9.1. Why Does Batch Selection Fetch Only `_id`?

When deleting, there is no need to stream entire event payloads over the network. Projecting **`{ _id: 1 }`** cuts read bandwidth to the client.

On write, the filter repeats **status** and **expiredAt** to avoid deleting a document that another process changed into an ineligible state between selection and deletion.

### 9.2. Why Not Checkpoint Before `bulkWrite`?

If the checkpoint advances before deletion, a connection drop can leave undeleted documents skipped forever. Saving `lastId` as the last ID *selected* rather than *processed* creates holes upon resumption.

Here, the checkpoint advances only after `bulkWrite` returns cleanly. If the driver throws after partial writes, the old checkpoint stays intact so the next run picks up any surviving eligible IDs. That is why **ID-targeted `deleteOne`** is so friendly to retries.

### 9.3. Why Is `deletedReported` Only an Operational Metric?

Consider what can happen:

~~~text
bulkWrite deletes 500 documents successfully
              |
              v
Process crashes before incrementing deletedReported
              |
              v
Resume: those 500 documents are already gone
              |
              v
Job can complete while deletedReported is short by 500
~~~

When exact deletion figures are required for auditing, log per-ID execution trails, snapshot input IDs, or run a dedicated reconciliation process. **Never treat `deletedReported` from this sketch as an authoritative financial or audit figure.**

### 9.4. Why Does the Code Have `MAX_BATCHES_PER_RUN`?

A job spanning millions of documents may need to run across scheduled maintenance windows. Capping batches per invocation lets the process exit cleanly without requiring a single long-lived worker process.

Upon reaching the limit, status remains `RUNNING` and `lastId` is saved. Re-running with **the same `JOB_ID` and `CUTOFF`** picks up from the saved checkpoint.

This is an operational stop point, not a signal that all data has been processed.

### 9.5. Limitations of This Example

The example assumes **a single executor**. If two processes share the same `JOB_ID`, both can read the same checkpoint and issue overlapping deletes. Matching `lastId` on checkpoint update detects some races, yet **it does not replace an exclusive lease prior to writing**.

Furthermore, if a new document is inserted with an `_id` smaller than the current checkpoint, this run will miss it. Use follow-up runs, a work queue, or snapshots when late-arriving data must not be missed.

## 10. Throttling: More Than Just Sleep

In the Node.js example, **pause(200)** introduces a 200 ms rest between passes. While simple and readable, a fixed sleep is not sufficient for every workload.

Average throughput can be approximated as:

~~~text
documents/second ≈ batchSize / (batch processing time + pause time)
~~~

For example, if each batch processes 500 documents in 0.8 s plus a 0.2 s pause, throughput is roughly **500 documents/second**. If each batch takes 3 s, the same settings yield roughly **156 documents/second**.

This formula is approximate because matched counts, modified counts, query time, retries, and system load vary.

### 10.1. Three Common Throttling Approaches

| Approach | Mechanism | Best suited for |
| --- | --- | --- |
| **Fixed pause** | Sleep N milliseconds after each batch | Simple jobs with fairly steady load |
| **Rate limit** | Cap documents or operations per second | Clear target throughput budgets |
| **Adaptive throttling** | Dynamically tune batch size or pause from live metrics | Production systems with fluctuating traffic |

A **rate limiter** such as a token bucket allocates an operation/second budget. With multiple workers, share or partition the rate budget cleanly rather than letting every worker consume the entire global budget on its own.

### 10.2. Which Metrics Should You Monitor?

While running maintenance jobs on MongoDB, track:

- **p95/p99 latency** of user-facing reads and writes.
- Primary CPU, disk I/O, and cache pressure.
- Replication lag and secondary oplog catch-up health.
- ID-fetch time, `bulkWrite` duration, and checkpoint-save duration.
- Selected, matched/modified/deleted counts, and per-batch errors.
- Retry counts, queued batch counts, throughput, and ETA.
- On sharded clusters: per-shard load distribution and impact on balancer/chunk migrations.

If user latency climbs or replication lag crosses operational thresholds, the job should **shrink batch size, lengthen pauses, or pause cleanly at a checkpoint**.

### 10.3. Batch Size and Concurrency Are Different Knobs

One sequential process:

~~~text
Read 500 -> Write 500 -> Save checkpoint -> Pause -> Repeat
~~~

places far smoother load on the cluster than multiple workers executing simultaneously:

~~~text
Worker A: 500
Worker B: 500
Worker C: 500
Worker D: 500
~~~

Even if each worker only batches 500 ops, four concurrent workers generate four times the instantaneous burst. When scaling concurrency, partition work cleanly—e.g., assigning distinct ID ranges or tenants per worker—so two workers never contend on the same slice.

**`maxTimeMS`** bounds execution time for a supported operation; it **is not a throughput throttle**. Similarly, reducing `cursor.batchSize` does not cap the write rate a job generates.

### 10.4. Backoff on Transient Errors

On network blips, primary elections, timeouts, or overload signals, use backoff:

~~~text
Retry 1: wait ~200 ms
Retry 2: wait ~400 ms
Retry 3: wait ~800 ms
Retry 4: wait ~1600 ms
Cap maximum wait time; add jitter
~~~

**Jitter** adds slight randomness to wait times so multiple processes do not retry in lockstep.

Do not retry every error indefinitely. Validation errors, wrong field types, missing permissions, index constraints, or misconfigurations require fixing root causes. For non-idempotent writes, retrying after ambiguous network errors risks duplicating effects.

## 11. Exclusive Processing and Checkpoints Across Multiple Workers

When multiple instances can run a job, sharing **a single checkpoint without ownership coordination** risks duplicate work and lost progress.

Two organizational patterns:

### 11.1. One Job, One Executor

A scheduler allows only one active instance of a given **`jobId`**. This is the simplest model whenever single-executor throughput meets your SLA.

Store a **lease** in the job document:

~~~javascript
{
  _id: "cleanup-expired-events-2026-11",
  ownerId: "worker-A",
  leaseUntil: ISODate("2026-11-14T04:30:00Z"),
  generation: 7,
  lastId: ObjectId("672000000000000000000123")
}
~~~

Workflow:

1. An executor acquires the lease via an **atomic conditional update** on the job document.
2. While running, it renews the lease and carries a **generation/fencing token**.
3. When saving a checkpoint, the filter must match the current `ownerId` and `generation`.
4. If the lease expires or `generation` changes, the stale executor halts instead of continuing.
5. A new executor resumes from the last confirmed checkpoint.

Holding `ownerId` only in process memory or relying solely on scheduler locks fails during network partitions when a zombie instance has not yet exited. Fencing tokens detect stale executors, and if the job triggers external side effects, downstream receivers should also reject stale tokens.

### 11.2. Multiple Sub-Jobs, One Partition Each

When parallelism is genuinely needed, split data into disjoint partitions:

~~~text
Overall job: cleanup-events
├── Partition A: tenantId in group A
├── Partition B: tenantId in group B
├── Partition C: tenantId in group C
└── Partition D: tenantId in group D
~~~

Each partition keeps its **own checkpoint and lease**, subject to a global rate cap. On sharded clusters, partitioning along the shard key can minimize cross-shard fan-out, provided topology and data distribution are well understood.

Never partition by having multiple workers run **`skip(pageNumber * size)`** on a collection undergoing deletion: as documents vanish, offsets shift and cause duplicates or missed items.

## 12. Correctness While the Collection Is Changing

### 12.1. Data Mutates Between Read and Write

Example:

~~~text
T1: Job selects event E because status = EXPIRED
T2: Application restores E to ACTIVE
T3: Job sends deleteOne
~~~

If `deleteOne` filters only by **`{ _id: E }`**, the job deletes a freshly restored event. Always repeat business eligibility conditions on the write operation:

~~~javascript
db.events.deleteOne({
  _id: eventId,
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
});
~~~

Evaluating predicates on the document at write time prevents mutating records that no longer qualify.

### 12.2. Documents Becoming Eligible Behind the Cursor

Suppose the job checkpointed past `_id = 5000`, and then document `_id = 1000` transitions to `EXPIRED`. A query with **`_id > 5000`** will not revisit it.

This is not a MongoDB bug—it is an inherent property of forward-only cursor scans over live data. Mitigations include:

- Running **recurring scheduled jobs** to sweep late-arriving records.
- Materializing a work-item/ID list upfront.
- Enqueueing items when documents transition state.
- Using an immutable time key with a bounded lookback window plus idempotency.

Never claim a job "processed every document that could possibly become eligible during execution" unless the architecture actually guarantees it.

### 12.3. When Is a Job Truly Complete?

With keyset traversal:

~~~text
Find next IDs -> empty
-> Mark DONE
~~~

This means **no matching documents remain past the checkpoint at the moment of the final query**. It does not prove no eligible documents exist behind the checkpoint due to concurrent updates.

If you need "zero remaining old eligible documents," re-scan from the start until an exit condition holds. However, on continuously written collections, absolute emptiness may never stabilize; define time-window rules or use a queue architecture instead.

## 13. Error Handling and Retries with `bulkWrite`

A write batch can encounter:

| Error class | Example | Sound handling |
| --- | --- | --- |
| **Transient network** | Connection drops between write and response | Never assume write didn't happen; use idempotent ops + backoff retries |
| **Primary failover** | Replica set elects a new primary | Keep old checkpoint, wait for cluster recovery, retry safely |
| **Write concern** | Fails to achieve requested acknowledgment | Outcome may be uncertain; handle per durability policy |
| **Validation** | Document violates schema validator | Log bad document; do not skip and blindly advance checkpoint |
| **Duplicate key** | `insertOne` violates unique index | Determine whether retry of same event or conflicting data |
| **State change** | Document no longer matches filter | `deleteOne`/`updateOne` returning 0 matched/deleted can be valid |
| **Checkpoint save failure** | `bulkWrite` succeeded but job state update failed | Resume and replay idempotent writes; never guess `lastId` |

### 13.1. Partial Failures in Unordered `bulkWrite`

With **`ordered: false`**, some operations can succeed while others fail. To keep progressing past isolated errors without dropping failed items, persist **a list of failed IDs requiring reprocessing**. Never swallow errors by logging to console and advancing the batch checkpoint anyway.

A simple pattern:

~~~text
try:
    bulkWrite(batch, ordered=false)
    checkpoint = lastIdInBatch
catch:
    keep existing checkpoint
    log error details
    stop or retry batch with backoff
~~~

This works cleanly when writes are **idempotent** and re-execution creates no unwanted side effects.

### 13.2. Retryable Writes Do Not Replace Checkpoints

MongoDB drivers support retryable writes for eligible operations and failure conditions. However, driver retries handle only single-command/operation transport blips; they do not track "which IDs the job already finished" or replace durable application recovery.

In particular, never assume a series of `bulkWrite` calls, batch iterations, and checkpoint updates is automatically wrapped in one atomic transaction by the driver.

### 13.3. Choosing an Appropriate Write Concern

When a job requires confirmed durability before advancing checkpoints, set **write concern** accordingly. Example on a properly configured replica set:

~~~javascript
db.events.deleteOne(
  { _id: eventId, status: "EXPIRED" },
  { writeConcern: { w: "majority" } }
);
~~~

Choosing the right write concern defines when a write counts as durable. Still, write concern **does not** turn `deleteOne` operations inside a `bulkWrite` into a multi-document transaction.

Updating a checkpoint in another collection is also a separate write. If business data and job state must update atomically together, evaluate transactions or pair idempotent jobs with reconciliation audits.

## 14. Indexes Supporting Batched Traversal Jobs

Jobs typically filter by status and cutoff, then sort by the traversal key:

~~~javascript
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff },
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(500);
~~~

A helpful index in this pattern might be:

~~~javascript
db.events.createIndex({
  status: 1,
  _id: 1
});
~~~

This supports filtering by `status` and scanning in `_id` order. Still examine `expiredAt`: if only a tiny fraction of `EXPIRED` documents satisfy `expiredAt <= cutoff`, this index may scan many ineligible entries.

Another approach indexes **`status, expiredAt, _id`** and traverses by the composite key **`(expiredAt, _id)`**. That narrows `expiredAt` tightly, though checkpoints must track the composite key and queries must align with the sort.

No single index is universally optimal. Measure:

- Are many documents filtered out before filling one batch?
- Does the execution plan show `COLLSCAN` or an expensive blocking sort?
- How much write overhead does the new index add to live inserts, updates, and deletes?
- On sharded clusters, does the filter include the shard key to limit scatter-gather fan-out?

Inspect `explain` on the **ID-selection** query:

~~~javascript
db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
})
.sort({ _id: 1 })
.limit(500)
.explain("executionStats");
~~~

A 500-document test on a tiny collection can look instant despite a terrible plan at tens of millions of documents. Benchmark at representative scale before finalizing batch size and indexes.

## 15. Deleting Old Data: When Should You Use TTL?

If the requirement is simply **automatic deletion after an elapsed duration**, MongoDB provides **TTL indexes** for suitable data models.

Example on a BSON Date field **`expiredAt`**:

~~~javascript
db.events.createIndex(
  { expiredAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

With this configuration, eligible documents are removed by MongoDB's background TTL monitor. Deletion **is not guaranteed to occur at the exact instant of expiration**.

Comparison:

| Requirement | TTL index | Custom batched job |
| --- | --- | --- |
| Simple age/Date-based expiration | Good fit | Possible |
| Per-batch control and application checkpoints | Not its primary function | Yes |
| Multi-step domain deletion rules | Limited | More flexible |
| Throttling driven by application metrics | Cannot be controlled via app loop | Customizable |
| Per-ID audit logging | Requires extra mechanism | Easily integrated |
| Schema migrations / bulk updates | No | Yes |

TTL is great for straightforward retention policies. Yet whenever ordering, reporting, load throttling, and exact job pausing matter, a custom batching pipeline remains valuable.

## 16. Bulk Updates Instead of Bulk Deletes

The same batching and checkpointing principles apply to updates.

Suppose you need to flag old events:

~~~javascript
const batch = db.events.find({
  archived: { $ne: true },
  createdAt: { $lt: cutoff }
})
.sort({ _id: 1 })
.limit(500)
.project({ _id: 1 })
.toArray();

const operations = batch.map((document) => ({
  updateOne: {
    filter: {
      _id: document._id,
      archived: { $ne: true },
      createdAt: { $lt: cutoff }
    },
    update: {
      $set: {
        archived: true
      }
    }
  }
}));

if (operations.length > 0) {
  db.events.bulkWrite(operations, { ordered: false });
}
~~~

This illustrates **a single batch** without checkpointing code. In a complete job, persist the checkpoint after the batch succeeds as shown earlier.

### 16.1. `$set` and `$inc` Have Different Retry Semantics

| Operation | Re-running after network error | Notes |
| --- | --- | --- |
| **`deleteOne` by ID and conditions** | Usually safe for final data state | Second delete typically does nothing |
| **`$set: { archived: true }`** | Usually idempotent | Final state remains `true` |
| **`$unset` a field** | Usually idempotent | Once removed, re-running changes nothing |
| **`$addToSet` a fixed value** | Avoids adding equal duplicate elements | Verify data types and element equality semantics |
| **`$inc: { balance: 10 }`** | Not idempotent | Retry can increment twice |
| **`$push`** | Not idempotent by default | Retry can append duplicate elements |
| **`insertOne` with fixed `_id`** | Retry may hit duplicate key | Distinguish benign retry collision from business conflict |

When a job needs non-idempotent transformations, add state-transition guards, processed markers, or stronger consistency patterns within the required scope.

## 17. Java Driver Example: Conditional Batch Update

In the MongoDB Java Sync Driver, a batch is represented as a list of **`WriteModel<Document>`**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.WriteModel;
import com.mongodb.bulk.BulkWriteResult;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public class ArchiveEventBatch {

    public static void main(String[] args) {
        List<String> ids = List.of("EV-01", "EV-02", "EV-03");

        try (MongoClient client =
                     MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> collection =
                    client.getDatabase("audit")
                          .getCollection("events");

            List<WriteModel<Document>> operations = new ArrayList<>();

            for (String id : ids) {
                operations.add(new UpdateOneModel<>(
                        Filters.and(
                                Filters.eq("_id", id),
                                Filters.ne("archived", true)
                        ),
                        Updates.set("archived", true)
                ));
            }

            if (!operations.isEmpty()) {
                BulkWriteResult result = collection.bulkWrite(
                        operations,
                        new BulkWriteOptions().ordered(false)
                );

                System.out.println(
                        "Matched: " + result.getMatchedCount()
                );
                System.out.println(
                        "Modified: " + result.getModifiedCount()
                );
            }
        }
    }
}
~~~

This demonstrates **writing a single batch** with pre-supplied IDs and no keyset/checkpoint loop. In a real job, fetch IDs via keyset pagination, inspect `bulkWrite` results, persist checkpoints in a job collection, and throttle between passes.

Distinguish **`matchedCount`** from **`modifiedCount`**: a document may match without changing value, or stop matching because another service updated it first. Interpret these counters in domain context.

## 18. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `skip(offset)` while deleting | Remaining documents shift and get skipped | Use keyset pagination |
| Saving only a non-unique timestamp as cursor | Skips documents sharing the same timestamp | Store composite `(timestamp, _id)` |
| Using a mutable field as the sort cursor | Documents jump across the cursor, causing duplicates/skips | Use an immutable key or snapshot |
| Saving the checkpoint before writing | On write failure, next run skips the incomplete batch | Checkpoint only after confirmed success |
| Retrying `$inc` or `$push` without idempotency | Doubles side effects | Use guards, markers, or operation logs |
| Treating `ordered: false` as "everything succeeds" | Silently ignores per-op errors | Classify and handle partial failures |
| Using `deleteMany` expecting `limit(500)` | Deletes every matching document in the collection | Select 500 IDs, then `deleteOne` |
| Shrinking `cursor.batchSize` to throttle writes | Fails to limit actual write throughput | Throttle the loop and concurrency |
| Replacing cutoff with `new Date()` on resume | Job scope drifts continuously | Keep cutoff immutable |
| Scaling concurrency with a shared unguarded checkpoint | Duplicate writes and state races | Use leases or disjoint partitions |
| Filtering status only during ID selection | Deletes documents that are no longer eligible | Repeat business predicates on the write |
| Treating summed `deletedCount` as exact audit proof | Crashes before checkpoint undercount deletions | Build dedicated audit/reconciliation |
| Ignoring replication lag | Overloads secondaries | Monitor metrics and throttle |
| Assuming `DONE` means no late-arriving records | Late eligible documents are missed | Schedule follow-up runs or use queues/snapshots |

## 19. Practice Lab: Test Event Cleanup Job

Run the following exercises in a dedicated test database. Never run test deletes against production data.

### Exercise 1: Seed Sample Data

~~~javascript
use mongo_batch_lab

db.events.insertMany([
  {
    _id: 1,
    status: "EXPIRED",
    expiredAt: ISODate("2025-01-01T00:00:00Z")
  },
  {
    _id: 2,
    status: "EXPIRED",
    expiredAt: ISODate("2025-02-01T00:00:00Z")
  },
  {
    _id: 3,
    status: "ACTIVE",
    expiredAt: ISODate("2025-03-01T00:00:00Z")
  },
  {
    _id: 4,
    status: "EXPIRED",
    expiredAt: ISODate("2025-04-01T00:00:00Z")
  },
  {
    _id: 5,
    status: "EXPIRED",
    expiredAt: ISODate("2025-05-01T00:00:00Z")
  },
  {
    _id: 6,
    status: "EXPIRED",
    expiredAt: ISODate("2027-01-01T00:00:00Z")
  }
]);
~~~

Assume a cutoff of Jan 1, 2026. Eligible IDs are **1, 2, 4, 5**. ID 3 has status `ACTIVE`, so it is ineligible; ID 6 has not reached the cutoff yet.

### Exercise 2: Fetch the First Two IDs

~~~javascript
const cutoff = ISODate("2026-01-01T00:00:00Z");

const batch1 = db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff }
})
.sort({ _id: 1 })
.limit(2)
.project({ _id: 1 })
.toArray();

printjson(batch1);
~~~

This selects IDs **1** and **2**. The checkpoint after a successful batch will be **2**.

### Exercise 3: Delete Two IDs Using `bulkWrite`

~~~javascript
const operations1 = batch1.map((item) => ({
  deleteOne: {
    filter: {
      _id: item._id,
      status: "EXPIRED",
      expiredAt: { $lte: cutoff }
    }
  }
}));

db.events.bulkWrite(operations1, { ordered: false });
~~~

Once completed, IDs 1 and 2 are gone. Re-running the same **`operations1`** yields 0 additional deletions since those IDs no longer exist.

### Exercise 4: Resume Using the Checkpoint Instead of `skip`

~~~javascript
const lastId = 2;

const batch2 = db.events.find({
  status: "EXPIRED",
  expiredAt: { $lte: cutoff },
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(2)
.project({ _id: 1 })
.toArray();

printjson(batch2);
~~~

This selects IDs **4** and **5**. Using `skip(2)` on a collection where 1 and 2 were just deleted would skip documents. Explain how `lastId` prevents this bug.

### Exercise 5: Simulating a Crash Before Checkpointing

1. Delete `batch1` successfully.
2. Assume the checkpoint still holds **`lastId = null`** because the process died before saving.
3. Re-run the first batch query.
4. Observe that MongoDB returns only the remaining eligible IDs.
5. Delete them and save the checkpoint after success.

Explain why **ID-targeted deletion** supports safe resumption, yet summed `deletedCount` values may fail to reflect deletions that happened right before the crash.

### Exercise 6: Inserting Late-Arriving Data

After the checkpoint advances past ID 5, insert a test document with an `_id` smaller than 5 that qualifies for deletion. A query for **`_id > 5`** will not find it.

Answer: to avoid missing late-arriving data in a real system, should you run another scheduled job pass, enqueue work items, or snapshot the target scope at start time?

### Exercise 7: Designing a Status-Update Job

An **invoices** collection has fields:

~~~javascript
{
  _id: "INV-1001",
  status: "PENDING",
  dueAt: ISODate("2025-12-01T00:00:00Z"),
  overdue: false
}
~~~

Requirement: mark every `PENDING` invoice whose `dueAt` has passed as `overdue: true`. Design:

- The selection filter with a fixed cutoff.
- The **`$set: { overdue: true }`** operation per ID.
- Batch size and pause mechanism.
- Stable-key checkpointing.
- Write guards preventing updates to invoices that just transitioned to `PAID`.
- Retry rules if the process crashes after `bulkWrite` but before saving the checkpoint.

A multi-document transaction is unnecessary when flagging independent invoices. What matters is that each write is **idempotent**, business conditions are checked at write time, and checkpoints advance only after completed batches.

## 20. Operational Principles to Remember

In MongoDB, large-dataset jobs should be designed as **a sequence of small, verifiable units of work**. Each pass selects a bounded batch of IDs using a stable sort key, runs `bulkWrite`/`deleteOne`/`updateOne` with domain predicates, persists a checkpoint after writes complete, and throttles before the next pass.

For jobs running hours or days, your design must withstand three realities:

1. Processes can crash at any point, including **right after writes succeed and before saving the checkpoint**.
2. Documents in the collection can mutate concurrently while the job runs.
3. Batch writes can succeed partially, and **error-handling code must account for that**.

Therefore, **checkpointing + idempotency + stable job scope + metric-driven throttling** form the foundation for processing millions of documents while retaining the ability to pause, resume, and protect cluster health.

## References

- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/)
- [MongoDB Manual — db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/)
- [MongoDB Manual — db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Node.js Driver — Bulk Operations](https://www.mongodb.com/docs/drivers/node/current/crud/bulk-write/)
