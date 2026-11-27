# Deleting Files, Detecting Orphan Data, and Handling Incomplete Uploads in MongoDB GridFS

## 1. Opening Scenario: An Upload Interrupted Mid-Way

A contract management application lets users upload 40 MiB PDF files. The application stores files using **GridFS**, a mechanism that persists a file across many small documents in MongoDB. After receiving roughly 25 MiB, the network connection drops and the API process restarts.

The user sees an "upload failed" message. Yet checking MongoDB storage shows the chunk collection is still growing. An operator tries to fix it with:

```javascript
// DANGEROUS: Never delete all chunks like this.
db.fs.chunks.deleteMany({});
```

That command can wipe the contents of **every file** in the bucket, including valid files.

This scenario raises three distinct questions:

1. **Deleting files properly:** when a user requests deletion of a fully stored file, what must be removed?
2. **Detecting orphan data:** how do you find chunks lacking a corresponding file record without mistaking them for chunks of an active upload still in progress?
3. **Incomplete uploads:** when an application cancels an upload, hits a write error, loses connectivity, or crashes, how do you manage state and recover safely?

The lesson **"Deleting Files, Detecting Orphan Data, and Handling Incomplete Uploads"** is part of the **GridFS** chapter of the **Database Engine Document MongoDB** module. After this lesson, you will be able to:

- Identify the `<bucket>.files` and `<bucket>.chunks` structure, linking keys, and indexes.
- Understand exactly when file metadata is created and why an in-progress upload looks like an "orphan."
- Use the `GridFSBucket` API to delete files by `_id`, rather than deleting by `filename` alone.
- Use the upload stream's `abort()` mechanism when intentionally cancelling.
- Distinguish **orphan chunks**, **files missing chunks**, **extra chunks**, and **complete files with no remaining business references**.
- Write **read-only** aggregation reports for orphan candidates and verify file integrity.
- Design an upload ledger/lease, idempotency, and cleanup jobs that avoid racing with uploaders.
- Build a scoped cleanup runbook with pre-checks and post-cleanup verification.
- Evaluate the impact of replication, backups, security, and data retention requirements.

## 2. How Does GridFS Store a File?

### 2.1. A Bucket Consists of Two Collections

By GridFS convention, the default bucket is named `fs` and contains:

```text
database
  |
  +-- fs.files      // metadata for each complete file
  |
  +-- fs.chunks     // binary data pieces
```

If an application creates a bucket named `contracts`, the two collections are `contracts.files` and `contracts.chunks`. Multiple buckets can exist in the same database. Therefore, **never assume every chunk resides in `fs.chunks`**.

A file is split into chunks whose default size is typically **255 KiB**; the final chunk can be smaller. Chunk size can be configured at upload time.

### 2.2. Documents in `files`

Example metadata of a successfully uploaded file:

```javascript
{
  _id: ObjectId("66a000000000000000000323"),
  filename: "hop-dong-2026.pdf",
  length: NumberLong("420000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T03:20:00Z"),
  metadata: {
    tenantId: "TENANT-A",
    documentType: "contract",
    sha256: "..."
  }
}
```

Meaning:

| Field | Role |
| --- | --- |
| `_id` | Unique **File ID** in `files`, referenced by chunks via `files_id` |
| `filename` | Display name, **not required to be unique** |
| `length` | Total byte count of the file content |
| `chunkSize` | Maximum number of bytes per chunk of the file |
| `uploadDate` | Timestamp when upload completed per GridFS spec |
| `metadata` | Application-specific data: ownership, file type, checksum, etc. |

File IDs are usually BSON `ObjectId` values, though applications may use another driver-supported ID type. When comparing `fs.files._id` with `fs.chunks.files_id`, **preserve the exact BSON type**. A string `"abc"` is not identical to a BSON `ObjectId` or UUID with a similar string representation.

### 2.3. Documents in `chunks`

Example of one part of a file:

```javascript
{
  _id: ObjectId("66b000000000000000000001"),
  files_id: ObjectId("66a000000000000000000323"),
  n: 0,
  data: BinData(0, "...")
}
```

Key fields:

- `_id`: unique ID of the chunk.
- `files_id`: reference to the `_id` of the `files` document.
- `n`: chunk sequence number, **starting from 0**.
- `data`: binary data of the chunk.

Diagram:

```text
contracts.files
  _id: F123
  filename: hop-dong.pdf
  length: 420000
  chunkSize: 261120
           |
           | files_id = F123
           v
contracts.chunks
  { files_id: F123, n: 0, data: 261120 bytes }
  { files_id: F123, n: 1, data: 158880 bytes }
```

To download, the driver finds metadata by file ID, reads chunks ordered by `n`, and reassembles the data. If a chunk in the middle is missing, content reconstruction can fail.

### 2.4. Two Important Indexes

GridFS uses:

```javascript
// On the chunks collection of bucket "fs":
db.fs.chunks.createIndex(
  { files_id: 1, n: 1 },
  { unique: true }
);

// On the files collection:
db.fs.files.createIndex(
  { filename: 1, uploadDate: 1 }
);
```

Spec-compliant GridFS drivers generally ensure the required indexes per version rules and when collections are in the appropriate state. In production, do not rebuild indexes blindly; inspect `getIndexes()` and data state first.

The `{files_id:1,n:1}` index enables reading chunks in order and prevents two chunks with the same `files_id` from sharing the same `n`. It **does not create a foreign key**: MongoDB can still hold chunks whose `files_id` has no parent in `files`.

### 2.5. GridFS Does Not Support Multi-Document Transactions

This is a critical limitation: **GridFS does not support multi-document transactions** per MongoDB GridFS documentation, even though MongoDB generally supports transactions across multiple documents and collections.

Do not write:

```javascript
// DO NOT treat this as an atomic solution for an entire GridFS upload.
await session.withTransaction(async () => {
  await bucket.uploadFromStream(...);
  await otherCollection.insertOne(..., { session });
});
```

GridFS writes/modifies multiple chunks and metadata through its own protocol. Never assume a `GridFSBucket` upload/delete can be placed inside a MongoDB transaction to make every chunk and every business document one atomic change.

To coordinate with business collections, design **workflow states, idempotency, post-write checks, and reconciliation**.

## 3. Upload Lifecycle: What Happens Before a File Completes?

### 3.1. Chunks Are Written First, `files` Metadata Is Written Last

By GridFS specification, the driver uploads data in this conceptual order:

```text
T0: open upload stream, allocate fileId
            |
T1: write chunk n=0 into <bucket>.chunks
            |
T2: write chunk n=1
            |
T3: write chunk n=2
            |
        ... more chunks ...
            |
T4: input stream ends and driver flushes successfully
            |
T5: driver creates document in <bucket>.files
            |
T6: upload stream completes successfully
```

**The `files` document is created only after all chunks of the file have finished writing.** `uploadDate` reflects when the upload finished, **not** when it started.

For an empty file with `length:0`, the driver creates the `files` document with **no data chunks**. This is a valid state.

### 3.2. Why Are Parentless Chunks Not Necessarily Garbage?

At time T2:

```text
fs.chunks:
  { files_id: F123, n: 0 }
  { files_id: F123, n: 1 }

fs.files:
  // No _id F123 document yet
```

A job running at that instant sees **two chunks whose `files_id` does not exist in `files`**. Yet the upload is still active; if the job deletes them, it corrupts the file being written.

Therefore:

> "Parent not found in `files`" is a **signal to investigate**, not sufficient proof that chunks can be deleted immediately.

You must combine upload state, data age, the possibility of an active writer, and cleanup coordination policies.

### 3.3. Terminal and Intermediate States

| Case | `files` | `chunks` | Conclusion |
| --- | --- | --- | --- |
| Upload in progress | Usually absent | May be partially present | **Do not delete** |
| Completed upload of non-empty file | Present | Complete | Normal |
| Completed upload of empty file | Present, `length:0` | None | Normal |
| Aborted upload with successful cleanup | Absent | None remaining | Normal |
| Mid-upload failure, cleanup failed | Likely absent | May remain | Orphan candidate |
| Upload completed, app failed to save reference | Present | Complete | Unreferenced at **application layer**, not a GridFS orphan |
| Partially deleted file | Parent may be gone | Chunks may remain | Orphan candidate from failed delete |
| Metadata exists but chunks missing | Present | Missing or out of order | **Corruption/inconsistency**, not orphan chunks |

## 4. Deleting an Uploaded File Properly

### 4.1. Use the `GridFSBucket` API by File ID

With the Node.js MongoDB driver:

```javascript
import { GridFSBucket, ObjectId } from "mongodb";

const bucket = new GridFSBucket(db, {
  bucketName: "contracts"
});

const fileId = new ObjectId("66a000000000000000000323");

await bucket.delete(fileId);
```

`bucket.delete(fileId)` is the API to delete **a file's metadata document along with its associated chunks**. The file ID must belong to the chosen bucket.

Do not use filename as the deletion key:

```javascript
// Wrong intent: filename is not unique, not the expected ID.
await bucket.delete("hop-dong.pdf");
```

Two uploads with the same `filename` can produce **two different file IDs**. Some driver APIs support deleting by name/all revisions, so check exact driver contracts; to delete **one specific version**, target `_id`.

### 4.2. Deletion Order in the Specification

The GridFS spec specifies that on delete, drivers remove:

1. The document in `<bucket>.files` first.
2. The documents with `files_id = fileId` in `<bucket>.chunks` second.

This shrinks the window where readers still see metadata while chunk contents are already gone. However, **there is no single transaction spanning both collections**.

```text
Before:
    files(F123) + chunks(F123,n=0..N)
                 |
          bucket.delete(F123)
                 |
      delete metadata files(F123)
                 |
      delete chunks(files_id=F123)
                 |
After:
    no parent or chunks remain for F123
```

If the process or connection fails **after metadata was deleted but before all chunks were removed**, orphan chunks can remain.

### 4.3. Do Not Equate "Delete Threw an Error" with "Nothing Was Deleted"

A delete can encounter:

- File document not found.
- Timeout deleting metadata or chunks.
- Network drop after the server partially executed it.
- Primary failover error.
- Permission or storage error.
- Another reader currently downloading the file.

When an error occurs, the final state **may be unknown**. Retrying `bucket.delete(fileId)` might throw **FileNotFound** because the `files` document was already deleted on the first attempt. That does not prove all chunks are gone.

Reconcile both:

```javascript
const parent = await db.collection("contracts.files").findOne({
  _id: fileId
});

const remainingChunks = await db.collection("contracts.chunks")
  .countDocuments({
    files_id: { $eq: fileId }
  });

console.log({
  fileMetadataExists: Boolean(parent),
  remainingChunks
});
```

The spec permits some drivers to attempt cleaning up orphan chunks even when metadata is missing, but you must **never depend on that behavior across all drivers/versions**. Recovery decisions must be based on actual state and file ID ownership.

### 4.4. Concurrent Readers and Deletes

There is an inherent race:

```text
Reader A: reads files(F123)
Deleter B: deletes files(F123)
Deleter B: deletes chunks(F123)
Reader A: reads chunks(F123)
          -> chunks may already be missing
```

GridFS does not promise that active downloads will finish intact if another actor deletes the file. If the application must ensure downloads finish before deletion, use business states, read limits, grace periods, or proper coordination.

### 4.5. Deleting by Ownership and Application State

A production handler must never trust a client-supplied `fileId` as sufficient authorization to delete.

Recommended flow:

1. Authenticate user and tenant.
2. Verify the referencing business record belongs to the owner.
3. Check retention and legal holds.
4. Mark business state `DELETING` or record a tombstone.
5. Block new downloads/links based on that state.
6. Delete from GridFS via `bucket.delete(fileId)`.
7. Reconcile metadata and chunks.
8. Mark `DELETED` once verified.
9. Emit minimal audit events without logging sensitive content.

Never promise that GridFS deletion immediately removes physical bytes from backups, snapshots, caches, CDNs, or secondary stores. Those systems have their own retention and purge workflows.

### 4.6. Files Referenced in Multiple Places

Example:

```text
Attachment A -> GridFS file F123
Attachment B -> GridFS file F123
Document C   -> GridFS file F123
```

Deleting F123 when a user deletes only Attachment A breaks B and C. If files are shared, maintain an explicit **reference ownership/reference count or registry** policy.

Never rely on a single `countDocuments({fileId})` check across concurrent writes as proof that no references remain; coordinate reference additions and removals properly.

## 5. Distinguishing Types of "Orphan" Data

### 5.1. Orphan Chunks per the GridFS Spec

An **orphan chunk** is a document in `chunks` whose `files_id` matches no `_id` in `files`.

```text
chunks:
   C1 -> files_id: F123

files:
   no _id F123

=> C1 is an orphan candidate under the GridFS relationship
```

Remember that an active upload exhibits the exact same symptom; to **delete**, you need additional proof that the file ID is no longer being written.

### 5.2. Files with Metadata but Missing Chunks

```text
files:
  F123 length=600000 chunkSize=261120

expected chunks:
  n=0, n=1, n=2

actual chunks:
  n=0, n=2
```

This is a **missing chunk**, not an orphan by definition. The file cannot be read intact. **Never delete `fs.files` to turn it into an orphan and sweep it away** as an automated "fix."

Restore from the original source or backup, or request a re-upload, assess business impact, and log the data corruption incident.

### 5.3. Files with Extra Chunks

```text
files:
  F123 length=420000 chunkSize=261120
  => needs n=0, n=1

actual chunks:
  n=0, n=1, n=2
```

Chunk `n=2` is extra relative to metadata, yet `files_id` **still has a valid parent**, so a query checking only for "no parent" will miss it.

You need a separate integrity-scan workflow. Some drivers may ignore extra chunks during download; never assume "download succeeded" means no extra chunks or metadata mismatches exist.

### 5.4. Complete Files with No Business Reference

For example, `fs.files` contains F123 and all its chunks, yet no record in the `attachments` collection points to F123.

This is an **application-level unreferenced file**, not an orphan chunk. Causes include:

- Upload succeeded, but the API crashed before creating the attachment record.
- File belongs to an unpublished draft.
- File is still retained for auditing or retention policies.
- The reference lives in a different collection or service.
- File is awaiting staff approval.
- Registry sync is lagging.

Cleaning these up requires examining **application lifecycle and references**, not just checking a foreign key in one collection.

### 5.5. Business References Pointing to a Missing File ID

The reverse case:

```text
attachments:
  { _id: A1, fileId: F123, status: AVAILABLE }

GridFS files:
  no F123
```

This is a **dangling application reference**. Return a controlled download error, inspect GridFS chunks, reconcile upload/delete logs, and repair business state. Never insert a fake empty `fs.files` document to "patch" a missing parent.

### 5.6. Diagnostic Matrix

| `files` doc | `chunks` | App reference | Situation |
| --- | --- | --- | --- |
| Present | Complete | Present | Normal |
| Present | 0, `length=0` | Present/absent | Valid empty file |
| Absent | 0 | Absent | Not uploaded or cleanly deleted |
| Absent | Present | Present/absent | **Orphan candidate**; check for active uploads |
| Present | Missing/wrong `n` | Present/absent | Corrupted/inconsistent file |
| Present | Complete | Absent | Unreferenced, not a GridFS orphan |
| Absent | 0 | Present | Dangling business reference |

## 6. Why Can GridFS Leave Orphan Chunks Behind?

### 6.1. Mid-Upload Failure

An upload may write several chunks and then fail:

```text
insert chunk 0 -> success
insert chunk 1 -> success
insert chunk 2 -> network error
               -> no files document created
```

The GridFS spec specifies that when a **server write operation fails**, the driver must return the error; it **is not required and should not attempt to clean up all previously written chunks** before surfacing the original error, because the root cause of the failure may also prevent cleanup.

Consequently, written chunks can remain without a parent. This is one reason to run a **periodic reconciliation job**.

### 6.2. Process Crash

If the process is killed, the pod terminates abruptly, power fails, or the connection drops before the client invokes abort logic, **no abort call is guaranteed to have run**.

Never treat a `finally` block in code as an absolute guarantee: `finally` does not execute under certain hard process crashes.

### 6.3. Abort Can Also Fail

When an application explicitly cancels an upload, the driver may delete already-written chunks. However, if that delete operation itself hits a network/server error, cleanup may be incomplete.

Record a state requiring **reconciliation** instead of immediately reporting "all chunks deleted" just because the client called abort.

### 6.4. Incomplete Delete

A delete operation may remove `files` first and then fail while deleting `chunks`. Remaining chunks lose their parent and become orphans.

### 6.5. Improper Manual Writes or Deletes

Manual data edits like:

```javascript
// Do not use in production to delete GridFS files.
db.fs.files.deleteOne({ filename: "hop-dong.pdf" });

// Even worse:
db.fs.chunks.deleteMany({});
```

can leave orphans or corrupt files. GridFS drivers manage both collections as one storage format, not two independent tables to edit ad hoc.

## 7. Aborting an In-Progress Upload via Driver API

### 7.1. `abort()` vs. `delete()`

- `abort()`: applies to an **open, incomplete upload stream**, cancelling writes and cleaning up uploaded chunks.
- `bucket.delete(fileId)`: applies to **deleting an already-stored file** by file ID, including metadata and chunks.

Never call `abort()` after an upload stream has already finished and expect it to delete the file. In the Node.js driver, calling `abort()` after completion or calling `abort()` twice can throw errors.

### 7.2. Node.js Example of Explicit Cancellation

The example below uses the modern MongoDB Node.js driver, an isolated test bucket, and a chunk larger than `chunkSizeBytes` for demonstration. It **does not need to simulate a network error**:

```javascript
import {
  MongoClient,
  GridFSBucket,
  ObjectId
} from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI);

await client.connect();

try {
  const lab = client.db("mongo_gridfs_row323_lab");
  const runId = new ObjectId().toHexString();
  const bucketName = "row323_" + runId;

  const bucket = new GridFSBucket(lab, {
    bucketName
  });

  const stream = bucket.openUploadStream(
    "cancelled.bin",
    {
      chunkSizeBytes: 255 * 1024,
      metadata: {
        runId,
        purpose: "abort-demo"
      }
    }
  );

  const fileId = stream.id;

  // Send data without calling end() on the stream.
  // Callback signals that the write was processed by the writable stream.
  await new Promise((resolve, reject) => {
    stream.write(
      Buffer.alloc(300 * 1024, 0x2a),
      (error) => error ? reject(error) : resolve()
    );
  });

  // Call ONLY ONCE, before the stream completes.
  await stream.abort();

  const files = lab.collection(bucketName + ".files");
  const chunks = lab.collection(bucketName + ".chunks");

  console.log({
    fileId,
    metadata: await files.findOne({ _id: fileId }),
    remainingChunks: await chunks.countDocuments({
      files_id: { $eq: fileId }
    })
  });
} finally {
  await client.close();
}
```

If `abort()` succeeds normally, no `files` document was created and chunks for the aborted upload are gone. However, if either write or abort throws, **do not assume cleanup completed**. Record `fileId` for reconciliation.

This example creates a **dedicated bucket name**. Never run it against a production bucket or someone else's file ID.

### 7.3. When the Upload Source Cancels Mid-Way

An HTTP application can detect when a client disconnects or clicks Cancel. Distinguish:

```text
Client closes connection
       |
       v
Application confirms upload has not finished
       |
       v
Stop accepting further input, halt source stream
       |
       v
Call abort on GridFS upload stream while still valid
       |
       v
Record cleanup success / cleanup failure
```

Exact details of calling `destroy()`, `abort()`, and `pipeline()` depend on the Node.js driver and stream state. A stream already destroyed by `pipeline()` on error may require different handling than an open stream; **never call `abort()` twice or attempt `abort()` after `finish`**. Test cancellation handling against your exact driver version.

### 7.4. Never Turn a Cancel Error into "Upload Complete"

An API can return:

```json
{
  "uploadId": "up-123",
  "status": "CANCELLED",
  "fileAvailable": false
}
```

when the user cancels, yet you must separate the business status **"access denied/unavailable"** from the claim **"every chunk has been deleted from the database."**

If abort cleanup fails, more accurate operational states are:

```text
CANCEL_REQUESTED
CLEANUP_PENDING
CLEANUP_FAILED
```

and enqueue `fileId` for reconciliation. Never return a file URL before upload finishes and passes validation.

## 8. Designing an Upload Lifecycle to Know Whether a File Is Still Being Written

### 8.1. Why `fs.files` Is Insufficient to Track In-Progress Uploads

While an upload is running, the `files` document does not exist yet. Therefore you cannot query `fs.files` to tell:

- When the upload started.
- Who owns the upload.
- Which upload attempts still have active heartbeats.
- Whether the client explicitly cancelled.
- How long parentless chunks may legitimately exist.
- Whether a prior cleanup attempt failed.

The application can maintain a dedicated **upload ledger** collection, such as `gridfs_upload_jobs`.

### 8.2. Suggested Lifecycle Document

```javascript
{
  _id: ObjectId("66a000000000000000000324"),
  fileId: ObjectId("66a000000000000000000323"),
  bucketName: "contracts",
  tenantId: "TENANT-A",
  requestId: "req-f37a",
  attemptId: "attempt-01",
  status: "UPLOADING",
  createdAt: ISODate("2026-11-14T03:00:00Z"),
  heartbeatAt: ISODate("2026-11-14T03:00:15Z"),
  leaseUntil: ISODate("2026-11-14T03:01:15Z"),
  workerId: "uploader-3",
  fencingVersion: 7,
  expectedBytes: NumberLong("420000"),
  actualBytesReceived: NumberLong("260000"),
  lastErrorCode: null
}
```

Depending on the system, you can set `_id = fileId` to simplify lookups. What matters is having a **stable identifier** linking the upload job to the GridFS file ID.

Example states:

```text
CREATED
   |
   v
UPLOADING ------> CANCEL_REQUESTED
   |                       |
   |                       v
   |                   ABORTING
   |                       |
   |             +---------+---------+
   |             |                   |
   v             v                   v
VERIFYING      ABORTED         CLEANUP_REQUIRED
   |
   v
AVAILABLE
   |
   v
DELETING
   |
   v
DELETED
```

This is an **application-designed state machine**, not a built-in MongoDB GridFS state list.

### 8.3. Create the Ledger Before Writing Chunks

Workflow:

1. Verify upload permissions and quotas.
2. Generate a stable `fileId`/`attemptId`.
3. Write the upload ledger entry with `UPLOADING`.
4. Open the GridFS upload stream using the chosen ID when supported by the driver.
5. Periodically update heartbeat/progress.
6. Close the source stream and wait for GridFS completion.
7. Verify the `files` document, size, and checksum as required by business rules.
8. Transition the ledger to `AVAILABLE` via compare-and-set.
9. Permit downloads via business APIs.

In Node.js, you can use:

```javascript
const upload = bucket.openUploadStreamWithId(
  fileId,
  "contract.pdf",
  {
    metadata: {
      tenantId,
      requestId,
      attemptId
    }
  }
);
```

Pre-allocating `fileId` lets the ledger, error logs, and cleanup refer to the exact same object. However, never reuse an ID for **two concurrent write attempts** or after an attempt with an unknown outcome.

### 8.4. Heartbeats Are Not Absolute Proof

If `heartbeatAt` looks stale, possibilities include:

- The uploader crashed.
- The node hit a stop-the-world GC pause.
- Network writes to the ledger failed while upload chunks kept flowing.
- The worker experienced a network partition.
- System clocks are skewed.

Never conclude "heartbeat older than 2 minutes = safe to delete all chunks immediately" while a writer might still be running. You need **leases/ownership/fencing** or another quiescence mechanism ensuring old writers cannot keep writing after cleanup claims ownership.

### 8.5. Leases and Fencing Tokens

A stronger architecture:

- Each upload attempt has an `owner` and `leaseUntil`.
- The lease is renewed while the worker stays active.
- The worker checks ownership version before critical steps.
- Cleanup claims ownership only after the old lease expires and the old owner is **fenced**.
- All writers obey the same ownership protocol.

Compare-and-set example:

```javascript
const claimed = await jobs.findOneAndUpdate(
  {
    _id: fileId,
    status: "UPLOADING",
    leaseUntil: { $lt: new Date() }
  },
  {
    $set: {
      status: "CLEANUP_PENDING",
      workerId: "cleanup-worker-1",
      claimedAt: new Date()
    },
    $inc: { fencingVersion: 1 }
  },
  { returnDocument: "after" }
);
```

This is only the **claim step in the state machine**—it is **not sufficient by itself to stop** an old writer from continuing to write to GridFS. The application must enforce actual fencing/quiescence on the write path, such as checking worker ownership and halting chunk writes from revoked attempts. The MongoDB GridFS API itself does not enforce a `fencingVersion` field on each chunk insert.

### 8.6. Avoid Reusing a File ID on Upload Retries

An HTTP request can time out after the server already finished the upload. If the client retries using the same file ID without reconciliation:

- The `files` document may already exist.
- Old chunks may exist without metadata.
- An older uploader may still be writing.
- New inserts may violate unique `{files_id,n}`.
- Two attempts may interleave data if the protocol lacks isolation.

Rules:

1. Keep the **business idempotency key** stable for the same user intent.
2. Bind **`fileId` to one specific upload attempt**.
3. On retry, first reconcile the ledger and `files`/`chunks`.
4. If the prior attempt succeeded, return the existing `fileId` after verification.
5. If indeterminate, do not overwrite the same `fileId`.
6. If a fresh upload is genuinely needed, allocate a new `attemptId`/`fileId` per protocol and clean up the old attempt once confirmed safe.

## 9. Detecting Orphan Chunks with Read-Only Queries

### 9.1. Two-Stage Classification Principle

Never attach a `$lookup` query directly to a `deleteMany`.

**Stage A — Find candidates:**

- Group chunks by `files_id`.
- Join against `files._id`.
- If no parent exists, record as a **candidate**.
- Collect chunk count, `n` range, and estimated size.

**Stage B — Decide on cleanup:**

- Check the upload ledger.
- Check whether any active writer/lease remains.
- Check age and grace period policies.
- Re-verify no parent exists once the system is in a safe state.
- Save audit/dry-run logs and obtain cleanup authorization.
- Delete only approved file IDs.

### 9.2. Aggregation to Find Orphan Candidates

Suppose the bucket is `fs`. Inside the connected database:

```javascript
const chunks = db.getCollection("fs.chunks");
const fileCollectionName = "fs.files";

const candidates = chunks.aggregate(
  [
    {
      $group: {
        _id: "$files_id",
        chunkCount: { $sum: 1 },
        minChunkNumber: { $min: "$n" },
        maxChunkNumber: { $max: "$n" }
      }
    },
    {
      $lookup: {
        from: fileCollectionName,
        localField: "_id",
        foreignField: "_id",
        as: "parentFiles"
      }
    },
    {
      $match: {
        "parentFiles.0": { $exists: false }
      }
    },
    {
      $project: {
        _id: 1,
        chunkCount: 1,
        minChunkNumber: 1,
        maxChunkNumber: 1
      }
    }
  ],
  { allowDiskUse: true }
).toArray();

printjson(candidates);
```

In the output, each group's `_id` is **`files_id`**, not the chunk `_id`. Preserve the BSON type when performing follow-up lookups.

**Important:**

- This is a **candidate report**, not a pre-approved deletion list.
- Aggregation can consume significant CPU, I/O, RAM, and temp disk on large buckets.
- On sharded collections, `$lookup` support and performance depend on version and topology.
- Results read during concurrent writes do not form a "permanent snapshot" for later deletion decisions.
- `allowDiskUse` allows spilling to disk when needed; **it does not make the query free**.
- Do not run it frequently on large clusters without a capacity plan.

### 9.3. Why Not Rely Solely on `ObjectId.getTimestamp()`?

A script can inspect an approximate timestamp from `chunks._id`:

```javascript
const chunk = chunks.findOne({});
print(chunk?._id?.getTimestamp?.());
```

However, ObjectId timestamps:

- Have limited precision and are generated client-side.
- May not reflect when the server actually persisted the write.
- Can be wrong if client clocks drift.
- Do not represent the start or end time of the **entire upload**.
- Do not apply if the application/legacy system uses another ID type.

Thus, chunk timestamps are only a **supporting signal**; rely on the application-managed upload ledger, heartbeats, and attempt IDs. Never compute "orphaned > 24 hours" from an ObjectId alone and auto-delete.

### 9.4. When Buckets Are Very Large

Scanning all of `chunks` and running `$group` across hundreds of millions of chunks is very expensive.

Lighter strategies:

- Start from **timed-out/failed upload jobs** in the ledger to get a bounded list of `fileId` values.
- Use the `{files_id:1,n:1}` index for per-ID `countDocuments`/`find`.
- Record `fileId` whenever the driver reports write/abort/delete errors to prioritize investigation.
- Run scans in batches during approved maintenance windows.
- Separate audit permissions from delete permissions.
- Schedule full integrity audits periodically within a resource budget.
- Maintain audit-job checkpoints to avoid re-scanning excessively.

Never use `distinct("files_id")` across the entire collection as a default strategy on large datasets: the result array can exceed BSON limits and incur heavy scan costs.

### 9.5. Two Scans Still Do Not Replace Coordination

Some systems scan for orphans at T0 and re-check at T0+5 minutes. This reduces accidental deletions, yet **does not eliminate races**:

```text
T0: query sees no files(F123)
T1: upload F123 is still running slowly
T2: second query still sees no files(F123)
T3: job deletes chunks(F123)
T4: uploader writes a new chunk or files(F123)
```

Without a **coordination rule with uploaders**, two reads cannot guarantee absolute safety. In production, use leases/fencing/quiescence or an explicit upload-attempt control mechanism.

## 10. Verifying Integrity of Files That Have Metadata

### 10.1. Expected Chunk Count

If metadata specifies:

- `length = L` bytes.
- `chunkSize = S` bytes.

then for a non-empty file:

\[
N_{\text{expected}}=\left\lceil \frac{L}{S} \right\rceil
\]

Example:

```text
length = 600000 bytes
chunkSize = 261120 bytes

600000 / 261120 ≈ 2.30
=> expectedChunks = 3
=> n values must be 0, 1, 2
```

For `length=0`, the expected chunk count is **0**.

### 10.2. Do Not Check Count Alone

A file with 3 chunks:

```text
n = 0, 1, 3
```

also has count = 3 yet is missing `n=2`. You must check:

- `n` starts at 0.
- `n` is contiguous up to `N-1`.
- No duplicate `n` values exist (the unique index enforces this).
- Each chunk's length equals `chunkSize`, except the last chunk.
- Total byte count equals `files.length`.
- Chunks have the exact `files_id` and BSON type.
- Full content can be read through the driver.
- Stored application checksums match if present.

The spec allows some drivers to **ignore extra chunks** rather than always checking full consistency. Never treat a partial download as proof that all remaining chunks are intact.

### 10.3. Inspecting a Small File with `mongosh`

Use this example only for a chosen file ID whose metadata length fits safely in a JavaScript `Number`:

```javascript
const fileId = ObjectId("66a000000000000000000323");
const files = db.getCollection("fs.files");
const chunks = db.getCollection("fs.chunks");

const file = files.findOne({
  _id: fileId
});

if (!file) {
  throw new Error("File metadata does not exist");
}

const length = Number(file.length);
const chunkSize = Number(file.chunkSize);

if (!Number.isSafeInteger(length) ||
    !Number.isSafeInteger(chunkSize) ||
    length < 0 || chunkSize <= 0) {
  throw new Error("Metadata unsafe for Number arithmetic");
}

const expected = Math.ceil(length / chunkSize);
const parts = chunks.find(
  { files_id: { $eq: fileId } },
  { n: 1, data: 1 }
).sort({ n: 1 }).toArray();

printjson({
  fileId,
  length,
  chunkSize,
  expectedChunks: expected,
  actualChunks: parts.length,
  chunkNumbers: parts.map((part) => part.n)
});
```

On very large files, **do not** call `toArray()` across all chunks: use streaming cursors, bounded aggregations, or checkpointed audit tools. File length can be a BSON `Long`, and converting to JS `Number` is unsafe past the safe integer limit; use BSON `Long`/`BigInt` or driver-appropriate arithmetic.

### 10.4. Verifying Byte Counts and Hashes

An application can compute **SHA-256** of the source content before or during upload, storing it in `files.metadata.sha256` upon completion via a controlled workflow.

During audits, read the file through a GridFS download stream, compute SHA-256, and compare against expected metadata. This detects bad or modified data. It **does not prove tamper resistance** if an attacker can modify both the content and the metadata hash.

Do not rely on the deprecated `files.md5` field as a default integrity mechanism; MD5 does not satisfy modern security needs. Implement application-layer checksums when required.

### 10.5. Corruption Requires Recovery, Not "Hunch-Based" Cleanup

If metadata exists while chunks are missing:

1. Stop serving the file as valid.
2. Check replicas, write errors, logs, and deletion history.
3. Determine whether an original source, backup, or upload source exists.
4. Recover through a safe, verified process.
5. Notify business owners if a re-upload is required.
6. Never edit `length`/`chunkSize` to make a corrupted file appear valid.

Adjusting metadata to match remaining chunks **does not restore the lost data**.

## 11. Controlled Orphan Cleanup

### 11.1. Multi-Gate Safe Workflow

A production cleanup job should pass through:

```text
Detect orphan CANDIDATES
          |
          v
Correlate upload ledger / delete logs
          |
          v
Exclude active uploads and protected files
          |
          v
Wait quarantine / grace period
          |
          v
Acquire cleanup ownership / fence writers
          |
          v
Recheck files and chunks by exact fileId
          |
          v
Dry-run + audit / approval
          |
          v
Delete narrowly scoped chunks
          |
          v
Verify zero remains + record outcome
```

If there is no way to prove the uploader has stopped or been fenced, a **"needs investigation"** state is safer than automatic deletion.

### 11.2. Never Delete by `filename` or Missing-Parent Date Heuristics

A command like:

```javascript
// Contraindicated in production:
db.fs.chunks.deleteMany({
  files_id: { $nin: oldFileIds }
});
```

carries huge risks:

- File IDs may have differing BSON types.
- `oldFileIds` may be incomplete.
- New uploads may have just started.
- Broad `$nin` logic can wipe valid data.
- No per-ID audit evidence is recorded.

Clean up using an **explicit list of file IDs**, one ID or small batch at a time, with rechecks and logging.

### 11.3. Re-Reading Before Deleting a Candidate

Suppose `candidateFileId` came from the ledger and the system **has guaranteed no uploader can still write to that ID**:

```javascript
const candidateFileId = new ObjectId(
  "66a000000000000000000325"
);

const files = db.getCollection("fs.files");
const chunks = db.getCollection("fs.chunks");

// Read-only preflight:
const parent = files.findOne({
  _id: { $eq: candidateFileId }
});

const count = chunks.countDocuments({
  files_id: { $eq: candidateFileId }
});

printjson({
  candidateFileId,
  hasParent: Boolean(parent),
  chunksCount: count
});
```

If `parent` exists, **abort orphan cleanup**, because it is no longer a "parentless chunk." If `count=0`, nothing needs to be deleted. If `count>0`, verify ledger, permissions, and quarantine before issuing a delete.

### 11.4. Executing Cleanup After Authorization

Only after all preconditions pass, the technical cleanup operation can be:

```javascript
// Execute only after approval, quiescence/fencing,
// and confirming candidateFileId belongs to the right bucket.
const result = chunks.deleteMany({
  files_id: { $eq: candidateFileId }
});

printjson(result);

print("remaining=" + chunks.countDocuments({
  files_id: { $eq: candidateFileId }
}));
```

This operates directly on GridFS internal structures, not via the standard file deletion API. It is appropriate only for **verified orphan chunks**, never for files with valid metadata.

Do not run this in production simply because a `$lookup` report returned candidates. In systems without fencing/quiescence, use a maintenance window with confirmed writer shutdown, or deploy a safe upload protocol before enabling automatic cleanup.

### 11.5. Limiting Batches, Rate, and Resources

Cleaning up many GB of chunks can cause:

- Heavy deletes impacting replication and oplog.
- I/O spikes and cache pressure.
- Increased primary write latency.
- Secondary replication lag.
- Storage/compaction overhead without immediate disk space reclamation.
- Impact on backups or change streams.

Recommended practices:

- Clean up in bounded batches of file IDs.
- Throttle by expected QPS and bytes.
- Support deadlines and stop flags.
- Monitor replication lag, disk, CPU, and p95 write latency.
- Stop before hitting resource/SLO thresholds.
- Record processed file IDs to avoid infinite loops.

**Deleting logical documents does not immediately shrink disk usage** due to storage engine allocation and space reuse mechanics.

## 12. Safe Hands-On Example: Isolated Bucket, Untouched Shared Data

### 12.1. Prerequisites

The snippets below are for a **test MongoDB instance** and a compatible Node.js MongoDB driver. There is no need to kill primaries, break replica sets, or corrupt real files.

Goals:

1. Create a bucket with a **unique per-run name**.
2. Upload a complete file.
3. Manually insert a "simulated orphan chunk" **only inside the test bucket**.
4. Find the orphan candidate using a read-only query.
5. Delete that exact simulated chunk after confirming no uploader exists.
6. Delete the complete file via `bucket.delete()`.

### 12.2. Creating the Bucket and Uploading a Complete File

```javascript
import {
  MongoClient,
  GridFSBucket,
  ObjectId,
  Binary
} from "mongodb";

import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

const client = new MongoClient(process.env.MONGODB_URI);

await client.connect();

try {
  const lab = client.db("mongo_gridfs_row323_lab");
  const runId = new ObjectId().toHexString();
  const bucketName = "row323_" + runId;
  const bucket = new GridFSBucket(lab, { bucketName });

  const files = lab.collection(bucketName + ".files");
  const chunks = lab.collection(bucketName + ".chunks");

  const upload = bucket.openUploadStream(
    "readme-row323.txt",
    {
      metadata: {
        runId,
        case: "complete"
      }
    }
  );

  await pipeline(
    Readable.from([
      Buffer.from("GridFS row323 completed file\n", "utf8")
    ]),
    upload
  );

  const completedFileId = upload.id;

  console.log({
    runId,
    bucketName,
    completedFileId,
    fileMetadata: await files.findOne({
      _id: completedFileId
    }),
    chunkCount: await chunks.countDocuments({
      files_id: { $eq: completedFileId }
    })
  });

  // Subsequent practice steps can be placed inside this try block.
} finally {
  await client.close();
}
```

`pipeline()` succeeds when the upload stream finishes per the Node.js driver contract. If `pipeline()` throws, record `fileId` for cleanup/reconciliation; never assume all chunks were cleaned up.

### 12.3. Creating a Simulated Orphan

**Only inside the newly created test bucket**, after the complete upload above:

```javascript
const orphanFileId = new ObjectId();
const orphanChunkId = new ObjectId();

await chunks.insertOne({
  _id: orphanChunkId,
  files_id: orphanFileId,
  n: 0,
  data: new Binary(
    Buffer.from("test orphan chunk", "utf8")
  )
});

console.log({
  parent: await files.findOne({
    _id: orphanFileId
  }),
  chunksCount: await chunks.countDocuments({
    files_id: { $eq: orphanFileId }
  })
});
```

Expected output:

```text
parent: null
chunksCount: 1
```

This intentionally creates **malformed/incomplete data** to practice orphan detection. Never run this on production `fs.chunks` or any bucket shared with other applications.

### 12.4. Finding the Orphan in the Test Bucket

```javascript
const candidates = await chunks.aggregate([
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 }
    }
  },
  {
    $lookup: {
      from: bucketName + ".files",
      localField: "_id",
      foreignField: "_id",
      as: "parents"
    }
  },
  {
    $match: {
      "parents.0": { $exists: false }
    }
  },
  {
    $project: {
      _id: 1,
      chunkCount: 1
    }
  }
]).toArray();

console.log(candidates);
```

In this isolated test bucket with no active uploaders, `orphanFileId` is a valid candidate. `completedFileId` is **not** a candidate because it has parent metadata.

### 12.5. Cleaning Up Only the Simulated Orphan

Because the script itself created `orphanFileId`/`orphanChunkId` and no uploader exists:

```javascript
const parent = await files.findOne({
  _id: orphanFileId
});

if (parent) {
  throw new Error("Orphan demo ID already has a parent: aborting!");
}

const deleted = await chunks.deleteOne({
  _id: orphanChunkId,
  files_id: { $eq: orphanFileId },
  n: 0
});

console.log({
  deletedCount: deleted.deletedCount,
  remaining: await chunks.countDocuments({
    files_id: { $eq: orphanFileId }
  })
});
```

Here `deleteOne()` matches **both chunk ID and file ID**, which is safer for test data. In production, once confirmed no active writer remains, you may need to clean up all chunks of a specific `fileId`, following the multi-gate workflow above.

### 12.6. Deleting the Complete File via the Driver

```javascript
const ownedFile = await files.findOne({
  _id: completedFileId,
  "metadata.runId": runId
});

if (!ownedFile) {
  throw new Error("Could not verify ownership of demo file");
}

await bucket.delete(completedFileId);

console.log({
  fileStillExists: Boolean(
    await files.findOne({ _id: completedFileId })
  ),
  chunksRemaining: await chunks.countDocuments({
    files_id: { $eq: completedFileId }
  })
});
```

Normally, the output confirms metadata is gone and chunk count is `0`.

**Note:** the snippets in sections 12.3–12.6 reference variables `lab`, `runId`, `bucketName`, `bucket`, `files`, `chunks`, and `completedFileId` created in section 12.2; to run continuously, place all steps inside the same `try` block before `client.close()`, or organize them into a single complete script. Do not copy individual snippets into separate processes and guess old file IDs.

### 12.7. After the Lab, Do Not Drop a Shared Database

The test bucket uses a random name for isolation. After confirming no demo files/chunks remain, an administrator can reclaim the two empty collections **per lab procedure**. Never run:

```javascript
// Dangerous in a shared database:
db.dropDatabase();
db.fs.files.drop();
db.fs.chunks.drop();
```

If the test environment has a namespace-cleanup policy, follow it. Do not spin up/tear down MongoDB clusters or disable replication just to practice orphan cleanup.

## 13. A Stateful Reconciliation Worker

### 13.1. Why Should the Job Read from the Ledger First?

Suppose there are 30 million chunks, yet only 12 uploads failed today. Scanning all `chunks` to group 30 million records is vastly more expensive than:

```text
gridfs_upload_jobs:
  status in ["CLEANUP_REQUIRED", "ABORT_FAILED"]
  lease expired
  age > gracePeriod
       |
       v
12 candidate fileIds
       |
       v
findOne files by _id
count chunks by files_id
       |
       v
cleanup only approved IDs
```

This is **candidate-driven reconciliation**, which is usually much friendlier to system resources.

### 13.2. Conditional Cleanup Pseudocode

```javascript
async function inspectCandidate({
  jobs,
  files,
  chunks,
  fileId
}) {
  const job = await jobs.findOne({ fileId });

  if (!job) {
    return {
      action: "MANUAL_REVIEW",
      reason: "NO_UPLOAD_LEDGER"
    };
  }

  if (!["CLEANUP_REQUIRED", "ABORT_FAILED"].includes(job.status)) {
    return {
      action: "SKIP",
      reason: "STATUS_NOT_ELIGIBLE"
    };
  }

  const parent = await files.findOne({
    _id: { $eq: fileId }
  });

  if (parent) {
    return {
      action: "MANUAL_REVIEW",
      reason: "PARENT_EXISTS"
    };
  }

  const chunksCount = await chunks.countDocuments({
    files_id: { $eq: fileId }
  });

  return {
    action: "CANDIDATE_FOR_APPROVAL",
    fileId,
    chunksCount
  };
}
```

**This function is read-only and deletes nothing.** It does not verify fencing, lease ownership, retention, or backups, so its output must not be treated as permission to delete. In production, the worker needs separate claim, recheck, and authorization steps and must never process the same `fileId` in parallel.

### 13.3. Do Not Let "Repair" Run While Sources Keep Writing

If uploader servers are running, checking `parent=null` is not enough. A sound cleanup service requires clear agreements:

- Uploaders share the same upload ledger and ownership protocol.
- The uploader has acknowledged cancellation/fencing and will definitely write no new chunks.
- Cleanup holds ownership for the duration of execution.
- If preconditions fail, mark `MANUAL_REVIEW` and do not delete.
- Transition `UPLOADING -> CLEANUP_PENDING` only via atomic compare-and-set when eligible.
- If cleanup fails, preserve state/attempt metadata for safe retries without wiping source records.

If you do not control all uploaders, use a **maintenance window** that halts writes to the bucket before cleaning up garbage.

### 13.4. Retrying Cleanup Without Causing Further Damage

A job should be idempotent in intent:

- If all chunks are gone and no parent exists → mark cleanup complete.
- If a parent unexpectedly appears → **stop** and escalate for investigation.
- If another cleanup worker already claimed the lease → do not compete.
- If partial chunks remain and the writer is fenced → continue cleaning that exact `fileId`.
- If a timeout yields an unknown outcome → re-query instead of assuming "cleanly deleted."

Never record `DONE` simply because `deleteMany` was sent without verifying and recording the outcome.

## 14. Recovering When Upload Finished Yet the API Lost the Response

### 14.1. A Tricky Failure Mode

```text
Client -> API -> GridFS
                |
                | all chunks written
                | files metadata created
                | upload stream completed
                |
API disconnects before returning fileId to client
```

The client may hit a timeout and click "Retry." If the API immediately generates a new `fileId`, the database can end up storing **two complete copies** for a single business intent.

### 14.2. Reconciling by `requestId`

An upload ledger entry containing:

```javascript
{
  requestId: "req-8821",
  tenantId: "TENANT-A",
  fileId: ObjectId("66a000000000000000000323"),
  status: "UPLOADING",
  expectedBytes: NumberLong("420000")
}
```

When the client retries:

1. Look up the ledger by `tenantId + requestId`, protected by an appropriate unique constraint.
2. If the ledger is `AVAILABLE`, verify the attachment/`fileId` and return it.
3. If the ledger is `UPLOADING`, check owner/lease and avoid blindly creating duplicate attempts.
4. If `fs.files` has a parent for `fileId` and size/hash can be verified, reconcile the ledger to `AVAILABLE` if policy permits.
5. If only parentless chunks exist, do not treat it as a complete file.
6. If the previous attempt truly terminated and was cleaned up/fenced, create a new attempt per protocol.

The **idempotency key** protects the intent "upload this document once"; the `fileId` protects the chunk structure of each attempt. The two ID layers serve distinct roles.

### 14.3. Never Fabricate Metadata When Only Chunks Remain

The GridFS spec defines many fields in `files`, such as `length`, `chunkSize`, `uploadDate`, and `metadata`. Without the parent document, surviving chunks alone cannot prove:

- Whether the source sent the entire file.
- Whether the final chunk is intact.
- Whether the actual size matches expectations.
- Whether filename/metadata match business rules.
- Whether the checksum matches the original file.

Therefore, never insert a guessed `fs.files` document to turn orphans into a valid file. When recovery is needed, prefer **re-uploading from a trusted source** or following a verified recovery procedure.

### 14.4. Retries Must Never Mix Two Attempts

```text
Attempt A: fileId F123, chunks n=0..4, failed
Attempt B: fileId F124, re-upload from start
```

This is easy to distinguish and clean up. Conversely, if both A and B use `F123` while A is not fenced:

```text
A: writes chunk 4
B: writes chunks 0..5
A: writes chunk 5
```

the unique index might catch duplicate `n`, yet that is not proper concurrency control. Never allow two independent uploaders to share a `fileId`.

## 15. Factors Affecting Cleanup in Real Clusters

### 15.1. Replica Sets and Read Preference

If an audit reads `fs.files` from a lagging secondary while reading `fs.chunks` from another node or at a different point in time, it can observe an inconsistent snapshot:

```text
Primary:
  files(F123) already written

Lagging secondary:
  does not see files(F123) yet

Audit:
  sees chunks(F123), does not see files(F123)
  -> false-positive orphan
```

For deletion decisions, use a **consistent, authoritative read strategy** suited to your deployment, checking primary/current state, write concern, and replication apply timing. Still, **read concern alone** does not eliminate races with active uploaders.

### 15.2. Do Not Treat GridFS Like a Cross-Collection Transaction

Even with `majority` read or write concern, deleting across two collections does not become a GridFS transaction. Concern settings govern acknowledgment and visibility, not whole business-state concurrency.

### 15.3. Sharded GridFS

In a sharded cluster, examine:

- Which bucket is used.
- Whether `files` and `chunks` are sharded.
- Whether the shard key on `chunks` includes `files_id` in a valid configuration.
- Whether the unique `{files_id:1,n:1}` index remains valid under sharding/uniqueness rules.
- Whether cleanup queries by `files_id` are targeted or scatter-gather.
- Whether chunks of a file can span multiple shards.
- Whether chunk migrations, resharding, or DDLs are currently running.

Never alter shard keys or create/drop GridFS indexes during incident cleanup without a DBA-approved plan.

### 15.4. Storage Does Not Shrink Immediately After Delete

After deleting many chunks, `countDocuments` drops right away, yet OS database files may not shrink proportionally. WiredTiger can **reuse** freed internal space.

Never spontaneously run `compact`, `repairDatabase`, rebuild replica sets, or drop collections simply because OS disk usage did not drop immediately; those are separate operational decisions with availability and risk implications.

### 15.5. Backups, Retention, and Legal Hold

Deleting a file in GridFS does not delete copies in:

- Retained snapshots/backups;
- External archives outside MongoDB;
- CDNs and HTTP caches;
- Logs or messaging systems carrying payload copies;
- Clients that already downloaded the file.

For legal documents or retained data, verify legal holds before deleting. For personal-data deletion requests, coordinate deletion across all managed copies and document backup retention windows per policy.

## 16. Monitoring and Alerting

### 16.1. Suggested Metrics

The names below are **application-defined metrics**, not built-in MongoDB fields:

| Metric | Purpose |
| --- | --- |
| `gridfs_uploads_started_total` | Count of started uploads |
| `gridfs_uploads_completed_total` | Count of completed uploads |
| `gridfs_uploads_aborted_total` | Count of explicitly aborted uploads |
| `gridfs_upload_errors_total` | Upload error breakdown |
| `gridfs_abort_cleanup_failures_total` | Count of failed abort cleanups |
| `gridfs_upload_inflight` | Number of currently open uploads |
| `gridfs_upload_age_seconds` | Age of open uploads |
| `gridfs_orphan_candidates` | File IDs with chunks but missing parent |
| `gridfs_orphan_candidate_bytes` | Estimated candidate byte volume |
| `gridfs_verified_orphan_bytes` | Verified byte volume approved for cleanup |
| `gridfs_missing_chunk_files` | Files with metadata but missing chunks |
| `gridfs_unreferenced_completed_files` | Complete files lacking business references |
| `gridfs_delete_errors_total` | Delete errors by `fileId` |
| `gridfs_reconciliation_duration_seconds` | Audit/cleanup job duration |
| `gridfs_cleanup_deleted_chunks_total` | Chunks deleted after verification |
| `gridfs_cleanup_jobs_manual_review` | Cases ineligible for automatic deletion |

In particular, **orphan candidates** and **verified orphans** are not the same metric. Candidate counts naturally rise during peak upload traffic without any corruption.

### 16.2. Operations Dashboard

A dashboard might group:

```text
+---------------------------+-------------------------+
| Upload success / error    | Abort / cleanup errors  |
+---------------------------+-------------------------+
| Upload inflight & age     | Orphan candidates age   |
+---------------------------+-------------------------+
| Verified cleanup backlog  | Missing chunks alerts   |
+---------------------------+-------------------------+
| Bucket files/chunks count | Chunk storage growth    |
+---------------------------+-------------------------+
| Primary write latency     | Replication lag         |
+---------------------------+-------------------------+
```

Watch trends: a handful of temporary orphan chunks during active uploads is normal; a **steadily growing verified orphan backlog** warrants priority action.

### 16.3. Alerts Should Have Context

Illustrative **hypothetical thresholds**, not MongoDB-guaranteed numbers:

- An upload stuck `UPLOADING` for over 2 hours despite a 10-minute SLA.
- An upload in `ABORT_FAILED` with uncleaned chunks after 24 hours.
- Verified orphan bytes exceeding 10 GiB.
- An `AVAILABLE` file throwing `ChunkIsMissing` on read.
- Sudden spike in delete errors.
- Reconciliation job failing to complete across multiple cycles.

Tune thresholds to file sizes, network speeds, upload SLAs, and legal retention. For files hundreds of GiB in size, multi-hour uploads can be completely normal; never apply a 10-minute threshold blindly to every bucket.

### 16.4. Safe Logging and Tracing

A useful log event might include:

```json
{
  "requestId": "req-8821",
  "attemptId": "attempt-02",
  "tenantId": "TENANT-TEST",
  "bucket": "contracts",
  "fileId": "66a000000000000000000323",
  "status": "CLEANUP_REQUIRED",
  "operation": "UPLOAD_ABORT",
  "errorCode": "NETWORK_TIMEOUT",
  "bytesUploaded": 260000,
  "occurredAt": "2026-11-14T04:00:00Z"
}
```

Never log file contents, chunk data, access tokens, filenames containing PII, or signed download URLs. In multi-tenant systems, enforce RBAC and retention on logs.

## 17. Incident Investigation Runbooks

### 17.1. Case A — Upload Failed, Chunks Keep Growing

1. Collect `fileId`, bucket name, attempt ID, and failure timestamp.
2. Check if any uploader is **still active**.
3. Inspect the upload ledger/lease and client retries.
4. Check whether `fs.files` has a parent yet.
5. Count chunks by exact `fileId`.
6. If the uploader is still alive, **do not clean up**.
7. If stopped/fenced, move the candidate through quarantine and controlled cleanup.
8. Confirm chunk count drops to 0 and update the ledger.

Never use `filename` to locate all chunks of an upload, because chunks do not store `filename` and multiple revisions can share a name.

### 17.2. Case B — Delete Returned an Error Yet the API Already Hid the File

1. Check the attachment tombstone/`DELETING` state.
2. Query metadata by `fileId` from an authoritative source.
3. Count chunks by `fileId`.
4. If the parent still exists, check whether delete failed at the first step due to permissions or network.
5. If the parent is gone while chunks remain, treat it as a cleanup candidate from an incomplete delete.
6. Block new downloads and confirm no uploader exists for that ID.
7. Execute approved cleanup.
8. Mark `DELETED` only after verifying final state and writing an audit record.

Do not blindly "retry `bucket.delete` until errors stop" without distinguishing `FileNotFound` from network or authorization errors.

### 17.3. Case C — Download Reports Missing Chunk

1. Verify file metadata exists and `length`/`chunkSize` are valid.
2. Compare expected count, min/max `n`, chunk sizes, and checksum.
3. Identify which users/applications reference the file.
4. Suspend serving the corrupted file if needed.
5. Check deletion, cleanup, and manual write history.
6. Restore from a trusted source or request re-upload.
7. Never delete metadata to hide the error.

### 17.4. Case D — Bucket Too Large, Need to Reclaim Space

1. Separate **valid file bytes** from **verified orphan bytes**.
2. Separate complete unreferenced files from orphan chunks.
3. Check retention policies and legal holds.
4. Plan throttled batch cleanup.
5. Monitor replication lag and write latency.
6. Verify cleaned document/byte counts.
7. Do not equate freeing logical records with immediate OS disk shrinkage.

## 18. Reference Architecture: Upload, Download, Delete, and Cleanup

A coordinated design:

```text
                API Gateway
                     |
                     v
           Attachment Service
               |          |
          auth/quota       | file references
               |          v
               |      attachments
               |
          upload ledger <---------+
               |                  |
               v                  |
          GridFSBucket            |
        +------+-------+          |
        |              |          |
        v              v          |
    bucket.files   bucket.chunks  |
        |              |          |
        +--------------+          |
               |                  |
       successful upload          |
               |                  |
               v                  |
       mark AVAILABLE ------------+
               |
        downloads permitted
               |
        deletion requested
               |
         mark DELETING
               |
        bucket.delete(fileId)
               |
         verify / reconcile
               |
         mark DELETED

Cleanup worker:
    reads failed uploads + delete errors
                  |
            checks leases
                  |
         excludes active writers
                  |
          rechecks exact IDs
                  |
         deletes verified chunks
                  |
           records audit
```

In this design, **GridFS holds bytes**, while the **application ledger and `attachments` hold business meaning**. Never assume inspecting `fs.files` alone tells you whether a file is awaiting approval, cancelled, under retention, or currently being downloaded.

## 19. Mistakes That Easily Cause Data Loss

| Mistake | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Deleting by `filename` without checking revisions | Names are not unique | Resolve exact `fileId` |
| Manually deleting only `fs.files` | Leaves parentless chunks | Use `bucket.delete(fileId)` |
| Deleting all of `fs.chunks` | Destroys every file's content | Clean up only verified file IDs |
| Deleting immediately when parent is missing | Could be an active upload | Check ledger, lease, and quiescence |
| Using ObjectId timestamp as proof uploader died | Clock skew, precision, races | Use workflow state and fencing |
| Calling `abort()` after upload finished | Abort is no longer semantically valid | Use `delete()` for completed files |
| Calling `abort()` twice | Driver may throw errors | Manage single-abort state |
| Assuming `finally` always runs on crash | Process can be hard-killed | Run a reconciliation job |
| Assuming failed upload writes clean up all chunks | Spec allows orphans after write errors | Record `fileId` and clean up later |
| Retrying upload with same `fileId` when prior attempt is unknown | Duplicate/interleaved chunks | Reconcile, fence, use attempt IDs |
| Letting two workers share the same `fileId` | Races and duplicate chunk `n` | Single owner/lease/fencing |
| Using GridFS inside multi-document transactions | Unsupported by GridFS | State machine and reconciliation |
| Treating metadata with zero chunks as always an error | Empty files are valid | Check `length` |
| Assuming parent existence guarantees all chunks | Chunks may be missing or extra | Run integrity checks |
| Comparing chunk count alone | Misses sequence gaps | Check `n`, bytes, checksum |
| Deleting immediately when absent from `attachments` | May still have references/retention | Reference registry and legal hold |
| Assuming `delete()` returning `FileNotFound` means chunks are gone | Differs across drivers/prior failures | Count/reconcile remaining chunks |
| Reading lagging secondaries to decide cleanup | False-positive orphans | Use authoritative source and quiescence |
| Continually full-scanning `chunks` on large clusters | Heavy CPU/disk/memory cost | Candidate-driven audits |
| Unthrottled cleanup of hundreds of GB | Hurts replication and APIs | Batch, rate-limit, monitor |
| Assuming MongoDB delete wipes backups/CDNs | Copies persist elsewhere | End-to-end retention/deletion workflow |
| Not logging `fileId` on upload failure | Cannot trace orphans | Stable `fileId`/`attemptId` and audit logs |

## 20. Hands-On Exercises and Review Questions

### Exercise A. Identifying Orphans

Bucket `fs` has:

```javascript
// files
{ _id: "F1", length: 500000, chunkSize: 261120 }
{ _id: "F2", length: 0, chunkSize: 261120 }

// chunks
{ files_id: "F1", n: 0 }
{ files_id: "F1", n: 1 }
{ files_id: "F3", n: 0 }
```

Answer:

1. Which file is normal?
2. Is `F2` having no chunks a form of corruption?
3. Is `F3` an orphan candidate?
4. What additional information is needed before deleting `F3`?
5. Why cannot `F3` be treated as a complete file?

### Exercise B. Deleting a File with Multiple Revisions

There are three `fs.files` documents all named `report.pdf` with different `_id` values.

1. Why is `filename` insufficient to delete one version?
2. What does `bucket.delete(fileId)` delete?
3. If a client wants to delete all revisions, what must be collected and verified?
4. If `delete` times out, why cannot you conclude all chunks still exist?

### Exercise C. Crashed Upload

An upload wrote chunks `n=0..8` yet has no metadata in `files`.

1. Is this necessarily an orphan safe to delete?
2. What is the difference between a client cancelling with `abort()` versus a process crash?
3. Which fields should an upload ledger store?
4. What fencing/quiescence is required before cleanup?

### Exercise D. File Missing a Chunk

Metadata:

```text
length=600000
chunkSize=261120
```

Existing chunks have `n=0` and `n=2`.

1. What is the expected count?
2. What is the actual count?
3. Why cannot you rely on `countDocuments` alone?
4. Should you adjust `length` to avoid download errors?
5. From which source should you recover?

### Exercise E. Retry with Unknown Outcome

A request receives an HTTP timeout after the upload may have finished.

1. Why can immediately re-uploading with a new `fileId` create duplicates?
2. How do you look up by business idempotency key?
3. If `fs.files` exists while the ledger still reads `UPLOADING`, what must be verified?
4. If only parentless chunks exist, should you resume uploading with the same ID?

### Exercise F. Cleanup Under Replication Lag

An audit reads `fs.files` from a secondary while an uploader just committed metadata on the primary.

1. Why can false-positive orphans be reported?
2. If you switch the audit to the primary, are upload races eliminated?
3. When is a maintenance window needed?
4. Why shouldn't you simply raise `readConcern` and treat it as fencing?

### Exercise G. Growing Bucket Size

A bucket contains:

```text
Valid file bytes:              800 GiB
Verified orphan bytes:          12 GiB
Completed but unreferenced:     30 GiB
Unknown / active uploads:        5 GiB
```

1. Which group can be prioritized for cleanup after review?
2. Why shouldn't you blindly delete the 30 GiB group?
3. Why shouldn't you blindly delete the 5 GiB group?
4. After deleting 12 GiB of chunks, why might OS disk usage not shrink right away?

### Exercise H. Designing Two State Layers

Draw state machines for:

- Business attachment: `PENDING → AVAILABLE → DELETING → DELETED`.
- Upload job: `CREATED → UPLOADING → VERIFYING → COMPLETED/FAILED/CLEANUP_REQUIRED`.

Explain why the two state machines differ and why a complete file whose attachment is not yet `AVAILABLE` is not automatically an orphan.

### Exercise I. Batched Audits

A bucket has 100 million chunks and 200 recent failed uploads.

1. Why is running `$group` over all chunks not the best first step?
2. Which index accelerates looking up chunks by `fileId`?
3. What information is needed in the ledger?
4. If a cleanup job restarts after a timeout, what must it verify before deleting further?
5. How do you limit impact on primary write latency?

### Exercise J. Permissions and Security

A user submits a random `fileId` and calls the DELETE API.

1. Why does knowing the ID not grant deletion permission?
2. Where must tenant, reference, and retention checks be performed?
3. Once deleted from GridFS, where else might copies still exist?
4. Which details must never be written to logs?

## 21. Official References

When deploying, cross-check your **MongoDB server version, driver version, topology, sharding setup, and deployment policies**:

- [GridFS — MongoDB Manual](https://www.mongodb.com/docs/manual/core/gridfs/) — two-collection format, indexes, limits, and the lack of multi-document transaction support.
- [MongoDB GridFS Specification](https://github.com/mongodb/specifications/blob/master/source/gridfs/gridfs-spec.md) — chunk/file write order, upload abort, orphan scenarios, and delete semantics.
- [Store Large Files with GridFS — Node.js Driver](https://www.mongodb.com/docs/drivers/node/current/crud/gridfs/) — using `GridFSBucket`, upload/download/delete/drop.
- [GridFSBucketWriteStream API — Node.js Driver](https://mongodb.github.io/node-mongodb-native/6.17/classes/GridFSBucketWriteStream.html) — `abort()`, stream state, and upload stream methods per driver.
- [GridFS — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/) — examples and orphan-chunk notes on upload failures.
- [MongoDB Node.js Driver API](https://mongodb.github.io/node-mongodb-native/) — verify file ID types, stream uploads, and error handling for your version.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — index design and inspecting indexes on `files`/`chunks`.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — write acknowledgment levels and behavior under network/replication failures.

The GridFS specification is especially valuable for understanding why drivers **cannot guarantee that operations across `files` and `chunks` are atomic like a transaction** and why certain upload errors can leave chunks without metadata. Specific APIs such as `abort()`, stream events, and errors must still be verified against your driver.

## 22. Conclusion

**GridFS** splits a file into chunks and creates metadata in `files` only when the upload finishes. Consequently, **parentless chunks** can represent failed files, leftover deletes, or simply **an upload currently in progress**. There is no safe rule like "if `files_id` is absent from `fs.files`, delete immediately."

When deleting a complete file, use **`GridFSBucket.delete(fileId)`** with a verified ID; when explicitly cancelling an open upload, use **`abort`** and verify cleanup. If an upload or delete fails, record `fileId`/`attemptId` and reconcile both collections. Because GridFS **does not support multi-document transactions**, applications need their own state machines, idempotency, and recovery procedures.

Detecting orphans is only the first step. A reliable system requires an **upload ledger, ownership, heartbeats/leases, fencing or writer quiescence, grace periods, dry-runs, exact-fileId cleanup, post-delete verification, and metrics**. Beyond orphan chunks, you must also distinguish missing/extra chunks, complete unreferenced files, and dangling references pointing to missing files; each requires a different policy.

**Core principle:** delete only data verified to no longer belong to an active upload or valid file, and always prioritize data recoverability over reclaiming disk space quickly.
