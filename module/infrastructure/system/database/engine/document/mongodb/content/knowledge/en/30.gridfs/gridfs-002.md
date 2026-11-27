# Structure of the files and chunks Collections and Required Indexes in MongoDB GridFS

An application storing original images, videos, PDF documents, or data exports can quickly hit an important MongoDB limit: **each BSON document cannot exceed 16 MiB**. Putting an entire 200 MiB file into a `BinData` field of a single document is not feasible. Even for files below that threshold, reading and writing an entire file as one large document can be unsuitable when the application wants to **stream** data in parts.

**GridFS** solves this problem by splitting a file into multiple parts (*chunks*) and storing them across **two collections**:

- **`fs.files`:** each document represents **one logical file**, containing its ID, total length, chunk size, upload timestamp, and metadata.
- **`fs.chunks`:** each document contains **a segment of bytes** of the file, linked via `files_id` and sequence number `n`.

These two collections come with **essential indexes**. In particular, the **unique `{files_id:1,n:1}`** index on `fs.chunks` ensures each chunk position of a file has at most one document; the **`{filename:1,uploadDate:1}`** index on `fs.files` supports looking up files by name and upload time. They do not serve the same purpose, and **filename is not a file's unique ID**.

This lesson belongs to the **GridFS** chapter of the *Database Engine Document MongoDB* module. Hands-on examples use **mongosh**, the **Node.js MongoDB Driver**, and the **MongoDB Java Sync Driver**. All examples should be run against the learning database `gridfs_lab`, without manually manipulating chunks of production files. Automatic index creation behavior, stream usage, metadata handling, and sharding capabilities must be cross-checked against your **actual server/driver versions** during deployment.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain when to use GridFS and why the 16 MiB BSON limit leads to a chunked storage model.
2. Describe the two collections `<bucket>.files` and `<bucket>.chunks`, and understand that `fs` is simply the default bucket name.
3. Read the fields `_id`, `length`, `chunkSize`, `uploadDate`, `filename`, and `metadata` in a `files` document.
4. Read the fields `_id`, `files_id`, `n`, and `data` in a `chunks` document.
5. Calculate the expected chunk count, final chunk size, and byte offsets for a file.
6. Distinguish the `_id_` index from the two standard GridFS indexes.
7. Explain why `{files_id:1,n:1}` must be unique and why `{filename:1,uploadDate:1}` is not unique.
8. Create, inspect, and properly maintain indexes for both the default bucket and custom-named buckets.
9. Upload/download files as streams without loading the entire file into RAM.
10. Retrieve a file by ID, list multiple versions sharing the same filename, and design custom metadata indexes.
11. Identify incomplete uploads, orphan chunks, missing chunks, duplicate `n` values, and size mismatches.
12. Delete files through the GridFS API instead of deleting from a single collection directly.
13. Understand GridFS limitations regarding whole-file atomicity, transactions, retention, checksums, sharding, and backups.
14. Measure/optimize chunk size performance, index count, query patterns, and file-storage I/O.

## 2. What GridFS Is and Is Not

GridFS is a **convention for storing files on MongoDB**, supported by MongoDB drivers through dedicated upload/download APIs. It is not:

- A new BSON type capable of exceeding 16 MiB in a single document.
- A single collection holding the entire file.
- A filesystem with directories, POSIX permissions, rename, and disk-like random writes.
- A Content Delivery Network (CDN) or an image/video processing service.
- An automatic deduplication mechanism for files with identical content.
- An atomic transaction spanning hundreds of chunks of a file.

### 2.1. When Is GridFS Suitable?

Examples:

- Files of 30 MiB, 200 MiB, or several GiB must be stored within the MongoDB ecosystem.
- The application wants streaming upload/download to avoid loading the entire file into memory.
- Metadata needs to live in MongoDB and be queried by ownership/group/creation date.
- File storage backup/administration needs to stay alongside the database per deployment policy.
- You want to build a custom download API by `fileId` and handle access control in the application.

### 2.2. When Might It Not Be the Best Choice?

- Files are only a few KiB and are only read together with a single business document: `BinData` or a simpler data model may work if appropriate.
- Data requires continuous mid-file updates of a few bytes: GridFS is not designed to **modify chunks in place** arbitrarily.
- Data consists of millions of small objects requiring direct public downloads via CDN: object storage may fit better.
- Files must follow specialized lifecycle rules, multi-region replication, or signed URLs: consider object storage while storing **metadata/references** in MongoDB.

**Rule of thumb:** decide whether to use GridFS based on access patterns, storage needs, operations, and file size; do not default to "use GridFS for every file."

## 3. Two-Collection Architecture

~~~mermaid
flowchart TD
    App["Application / GridFSBucket API"] --> Upload["Upload stream: split bytes into chunks"]
    Upload --> C["fs.chunks"]
    Upload --> F["fs.files"]
    F -->|"One _id per file"| FileMeta["files: length, chunkSize, uploadDate, filename, metadata"]
    C -->|"files_id references _id of fs.files"| Chunk1["chunk n=0"]
    C --> Chunk2["chunk n=1"]
    C --> ChunkN["chunk n=N-1"]
    Read["Download by fileId"] --> F
    Read --> C
    Read --> Combine["Read chunks in ascending n order"]
    Combine --> Client["Stream bytes to client"]
~~~

Suppose a file has `_id=ObjectId("...")`. The document in `fs.files` describes the file; every `fs.chunks` document belonging to that file has `files_id` equal to that exact `_id`. **Byte order does not rely on the chunk's `_id`**—it relies on `n`.

### 3.1. Each Logical File Has Multiple Chunks

~~~text
fs.files:
  _id = F1, length = 700000, chunkSize = 261120

fs.chunks:
  files_id = F1, n = 0, data = 261120 bytes
  files_id = F1, n = 1, data = 261120 bytes
  files_id = F1, n = 2, data = 177760 bytes
~~~

Concatenating `data` from the chunks in order `n=0,1,2` reconstructs a file of exactly `700000` bytes.

### 3.2. There Is No `chunks` Array Field Inside `fs.files`

A common misconception:

~~~javascript
// NOT the standard GridFS schema.
{
  _id: fileId,
  filename: "video.mp4",
  chunks: [binary1, binary2, binary3]
}
~~~

GridFS uses **two separate collections** so that each BSON document stays under 16 MiB and individual chunks can be streamed.

## 4. Bucket Prefix: Why `fs.files` and `fs.chunks`?

The default bucket name is **`fs`**, so the default collections are:

~~~text
fs.files
fs.chunks
~~~

When using a bucket named `avatars`, the corresponding collections become:

~~~text
avatars.files
avatars.chunks
~~~

A single database can use multiple buckets:

~~~text
gridfs_lab
├── fs.files
├── fs.chunks
├── avatars.files
├── avatars.chunks
├── exports.files
└── exports.chunks
~~~

### 4.1. When Should You Create a Separate Bucket?

- Files differ in **purpose and lifecycle**: avatars, export files, document attachments.
- You want different metadata/indexing policies.
- You want to simplify access permission management and cleanup per file category.
- You want to avoid mixing filenames and semantics across application modules.

Different buckets **do not automatically create a security boundary**. Database/collection privileges and user authorization checks must still be designed.

### 4.2. Common GridFSBucket Options

Some drivers allow configuring:

~~~javascript
{
  bucketName: "avatars",
  chunkSizeBytes: 261120
}
~~~

Option names vary slightly across drivers, but their meaning is the **collection prefix** and the **default chunk size for uploads in the bucket**. The `chunkSize` field is stored **per `files` document**, allowing older and newer files to have different chunk sizes.

## 5. Schema of `fs.files`

An example `files` document:

~~~javascript
{
  _id: ObjectId("6748abcd1234567890abcdef"),
  length: NumberLong("700000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:30:00Z"),
  filename: "monthly-report.bin",
  metadata: {
    tenantId: "t-01",
    ownerId: "user-18",
    contentType: "application/octet-stream",
    documentType: "report",
    visibility: "private",
    sha256: "hex-sha256-computed-by-application"
  }
}
~~~

This is a **structural sample**, not a real record. `sha256` is a placeholder value and must not be used as a valid checksum. Fields and their meanings:

| Field | Typical Type | Purpose |
|---|---|---|
| `_id` | Commonly ObjectId by default; can be any driver-supported BSON ID | Unique identifier of **one file version** |
| `length` | BSON 64-bit integer | Full size of the file, **in bytes** |
| `chunkSize` | Integer | Standard chunk size of the file, **in bytes** |
| `uploadDate` | BSON Date | Timestamp when the file was uploaded/completed per driver |
| `filename` | String, may be absent in some cases | Logical name for searching/display; **not unique** |
| `metadata` | Optional document | Application-defined business information |

### 5.1. `_id` Is the File Identity, Not `filename`

Two files can share the same name:

~~~text
monthly-report.bin  -> _id=F1, uploadDate=day 01
monthly-report.bin  -> _id=F2, uploadDate=day 14
~~~

These may be **two versions** of the same filename. When downloading the exact file a user selected, use the **file ID** instead of relying solely on the filename.

### 5.2. `length` Is in Bytes, Not Chunk Count

`length=700000` means **700,000 bytes**. Do not infer "700,000 characters," because the file may be binary or multi-byte UTF-8. Do not use JavaScript's `String.length` to calculate byte length of Unicode content; use byte buffer/stream length.

### 5.3. `chunkSize` Is a Per-File Property

An older file may have `chunkSize=261120`, while a newer file uses `chunkSize=262144`. The driver reads using the value stored in the **downloaded file's `files` document**, rather than applying the bucket's current chunk size to decode older files.

### 5.4. `uploadDate` Differs from Business Timestamp

A report file might be generated at 08:00 but uploaded at 08:30; `uploadDate` records upload metadata, not necessarily when the business data was created. If you need the report generation time, store `metadata.generatedAt` or another business field with a valid BSON Date.

### 5.5. `metadata` Is Application Data

For example:

~~~javascript
metadata: {
  tenantId: "t-01",
  ownerId: "user-18",
  contentType: "application/pdf",
  reportPeriod: "2026-10",
  dataClassification: "internal"
}
~~~

GridFS does not interpret `ownerId` or `visibility` as enforced ACLs. **The application must authenticate and authorize** when querying, downloading, or deleting. Never store passwords or secrets in metadata.

### 5.6. `md5` and Legacy Fields

Older GridFS implementations included top-level fields like `md5`, `contentType`, or `aliases`. Server-side MD5 computation commands and these legacy fields have been **deprecated / are no longer recommended** in modern drivers and servers. If you need integrity or content type:

- Store `metadata.contentType` validated by the application.
- Use **SHA-256** (or an appropriate checksum/ETag mechanism) computed in the application when needed.
- Never trust a filename extension or client-supplied Content-Type as proof of a safe file.
- Do not design new systems with a hard dependency on GridFS-generated `md5`.

## 6. Schema of `fs.chunks`

A chunk document:

~~~javascript
{
  _id: ObjectId("6748abcd1234567890abc001"),
  files_id: ObjectId("6748abcd1234567890abcdef"),
  n: 0,
  data: BinData(0, "...")
}
~~~

Explanation:

| Field | Typical Type | Role |
|---|---|---|
| `_id` | Unique ID in `fs.chunks` | Identifies the individual chunk document |
| `files_id` | Same BSON type/value as `fs.files._id` | Links the chunk to its file |
| `n` | Non-negative integer | Chunk position within the file, **starting at 0** |
| `data` | BSON binary | The actual raw bytes of the chunk |

### 6.1. Why Is `files_id` Needed?

Within the same `fs.chunks` collection, chunks from many files are interleaved:

~~~text
files_id=F1 n=0
files_id=F2 n=0
files_id=F1 n=1
files_id=F3 n=0
files_id=F1 n=2
files_id=F2 n=1
~~~

A correct download must filter on `files_id=F1` and **sort by `n` ascending**, not by `_id` or physical disk order.

### 6.2. `n` Is Zero-Based Ordering

~~~text
First chunk:   n = 0
Second chunk:  n = 1
Third chunk:   n = 2
...
Nth chunk:     n = N - 1
~~~

If `n` is missing, downloaded data may be incomplete or the driver will raise a missing-chunk error. If two chunks share the same `files_id` and `n`, byte ordering becomes ambiguous; the **unique compound index** must prevent this situation.

### 6.3. `data` Is Binary, Not Stored as Base64 Text

When `mongosh` displays `BinData(...)`, that is how BSON binary data is rendered; it does not mean the driver stored the file as a Base64 string like a normal JSON field. Do not dump `data` into logs, or convert millions of bytes to JSON over internal APIs when streaming can be used.

### 6.4. Each Chunk Document Remains Subject to the BSON Limit

GridFS splits files so that **each chunk document** stays below 16 MiB. Setting `chunkSizeBytes` too large can violate the BSON document limit due to overhead from `_id`, `files_id`, `n`, and the binary wrapper. Do not pick a chunk size close to 16 MiB without verifying driver/server limits.

## 7. Calculating Chunk Count, Offsets, and the Final Chunk

Suppose:

~~~text
File length (L):       700000 bytes
Chunk size (C):        261120 bytes
Expected chunk count:  ceil(700000 / 261120) = 3
~~~

Three chunks:

| `n` | Starting byte offset | Bytes in `data` |
|---:|---:|---:|
| 0 | 0 | 261120 |
| 1 | 261120 | 261120 |
| 2 | 522240 | 177760 |
| **Total** | | **700000** |

### 7.1. General Formulas

For `L > 0` and `C > 0`:

\[
N = \left\lceil\frac{L}{C}\right\rceil
\]

Offset of chunk `n`:

\[
\operatorname{offset}(n)=nC,\qquad 0\le n<N
\]

Size of chunk at `n`:

\[
\operatorname{size}(n)=
\min(C,\; L-nC)
\]

Non-final chunks normally have exactly `C` bytes; the last chunk can be smaller. If `L` is an exact multiple of `C`, the last chunk also has exactly `C` bytes.

### 7.2. Empty Files

For `L=0`, the expected chunk count is **0**, while the file metadata can still exist:

~~~text
fs.files: length=0, chunkSize=C
fs.chunks: no chunks for that fileId
~~~

Do not try to fabricate an `n=0` chunk with empty data simply because application code always expects at least one chunk.

### 7.3. Helper Function

~~~javascript
function expectedChunks(lengthBytes, chunkSizeBytes) {
  if (!Number.isSafeInteger(lengthBytes) || lengthBytes < 0 ||
      !Number.isSafeInteger(chunkSizeBytes) || chunkSizeBytes <= 0) {
    throw new Error("INVALID_SIZE")
  }
  return Math.ceil(lengthBytes / chunkSizeBytes)
}

print(expectedChunks(700000, 261120)) // 3
print(expectedChunks(0, 261120))      // 0
print(expectedChunks(522240, 261120)) // 2
~~~

For very large files whose `length` exceeds JavaScript's safe integer range, do not arbitrarily coerce BSON Int64 into `Number`; use the appropriate large-integer/numeric type provided by the driver. This example only illustrates small files.

### 7.4. Why Is the Default `chunkSizeBytes` 255 KiB?

GridFS commonly uses a default size of **255 KiB = 255 × 1,024 = 261,120 bytes**. This is the GridFS default implemented by many drivers—not 255,000 bytes and not 255 MiB. Users can choose a different chunk size per driver within server limits. Each file records the `chunkSize` actually used.

## 8. The Two Core Indexes of GridFS

In addition to the standard `_id_` index on each collection, GridFS specifies two special compound indexes:

| Collection | Key pattern | Unique? | Purpose |
|---|---|---|---|
| `fs.files` | `{filename:1,uploadDate:1}` | **No** | Look up files by name, support selecting versions by time |
| `fs.chunks` | `{files_id:1,n:1}` | **Yes** | Read chunks of a file in order; prevent duplicate `n` positions |

These are the two **most important GridFS indexes**. Do not replace them with `{uploadDate:1}` on `chunks`, `{n:1}` alone, or a unique `{filename:1}`.

### 8.1. Creating the `files` Index

~~~javascript
db.fs.files.createIndex(
  { filename: 1, uploadDate: 1 },
  { name: "filename_1_uploadDate_1" }
)
~~~

Do not set `unique:true`, because the same filename can have multiple uploaded versions. `uploadDate` supports sorting by time. If versions share the same `uploadDate` down to timestamp resolution, `_id` can be used as a tie-breaker in the application when deterministic ordering is needed.

### 8.2. Creating the `chunks` Index

~~~javascript
db.fs.chunks.createIndex(
  { files_id: 1, n: 1 },
  {
    unique: true,
    name: "files_id_1_n_1"
  }
)
~~~

This index does two things:

1. Filters on `files_id` to retrieve chunks belonging to **one file**.
2. Provides `n` ordering and guarantees no two chunks share the same `(files_id,n)`.

### 8.3. Why Must Uniqueness Be on the Pair `(files_id,n)`?

If only `n` were unique, every file has chunk `n=0`, so uploading a second file would wrongly fail. If only `files_id` were unique, each file could only have one chunk. Uniqueness on the **pair** allows multiple chunks per file while keeping each chunk position unique.

### 8.4. Indexes Do Not Verify Continuity

Unique `{files_id:1,n:1}` **does not guarantee** that all chunks are present:

~~~text
files_id=F1: n=0, n=1, n=3
~~~

There are no duplicates, so the unique index does not detect that `n=2` is missing. Drivers rely on `length`, `chunkSize`, and ordering to catch some forms of errors/incomplete files. Additional integrity/checksum policies are needed if the business requires them.

### 8.5. Indexes Do Not Guarantee Byte Accuracy Either

A unique index cannot verify whether the second chunk's `data` is exactly 261,120 bytes or whether its contents were modified. Integrity cannot rely on indexes alone.

## 9. Why Is the `fs.files` Index Not Unique?

Suppose the application uploads:

~~~text
2026-10-01: filename = invoice.pdf, fileId = A
2026-10-15: filename = invoice.pdf, fileId = B
2026-11-01: filename = invoice.pdf, fileId = C
~~~

Under GridFS, three different logical files are allowed to share the same `filename`. These could be three uploads of the same document, three files from different users, or a common name like `image.jpg`.

### 9.1. Finding Files with the Same Name

~~~javascript
db.fs.files.find(
  { filename: "invoice.pdf" },
  {
    _id: 1,
    filename: 1,
    uploadDate: 1,
    length: 1,
    metadata: 1
  }
).sort({ uploadDate: -1 })
~~~

The `{filename:1,uploadDate:1}` index helps search by name and scan by time. It does not mean `invoice.pdf` belongs to the requester; you must verify owner/tenant.

### 9.2. Use `fileId` for Long-Term References

In a business document:

~~~javascript
{
  _id: "application-2026-001",
  tenantId: "t-01",
  attachmentFileId: ObjectId("6748abcd1234567890abcdef"),
  attachmentFilename: "invoice.pdf"
}
~~~

`attachmentFileId` is the exact reference. `filename` is only for display. If a user re-uploads a file with the same name, the business document can decide when to switch the reference rather than unexpectedly downloading "the newest file."

### 9.3. Where Should Unique Business Keys Live?

If a requirement states "each case file has only one active attachment," enforce that in a **regular collection** managing case/attachment references, using a unique index on `tenantId + applicationId + attachmentType`. Do not turn `fs.files.filename` globally unique to solve a specific business constraint.

## 10. Initializing Buckets and Indexes

`GridFSBucket` in many drivers **checks/creates standard indexes when needed** (usually during the first upload into a new/empty bucket), per the GridFS specification and driver version. However, you should not rely on the first production upload request to create indexes for the first time amid concurrent requests.

### 10.1. Inspecting Existing Indexes

~~~javascript
use gridfs_lab

db.fs.files.getIndexes()
db.fs.chunks.getIndexes()
~~~

Minimum expected indexes after a bucket is properly initialized:

~~~javascript
// fs.files
{ key: { _id: 1 }, name: "_id_" }
{ key: { filename: 1, uploadDate: 1 },
  name: "filename_1_uploadDate_1" }

// fs.chunks
{ key: { _id: 1 }, name: "_id_" }
{ key: { files_id: 1, n: 1 },
  name: "files_id_1_n_1", unique: true }
~~~

This illustrates the **shape of the relevant indexes**, not every literal field in `getIndexes()` output; depending on version, fields like `v`, `ns`, and other options also appear.

### 10.2. Preparing Indexes During Deployment/Migration

For a lab database/bucket or a controlled initialization plan:

~~~javascript
use gridfs_lab

db.createCollection("fs.files")
db.createCollection("fs.chunks")

db.fs.files.createIndex(
  { filename: 1, uploadDate: 1 },
  { name: "filename_1_uploadDate_1" }
)

db.fs.chunks.createIndex(
  { files_id: 1, n: 1 },
  { unique: true, name: "files_id_1_n_1" }
)
~~~

**Run only in environments where collection/index creation is permitted**, avoiding uncontrolled re-runs. If an index with the same key pattern but different options/name exists, check beforehand to avoid conflicts; never drop an index currently used by the application.

### 10.3. Custom Bucket `avatars`

~~~javascript
db.createCollection("avatars.files")
db.createCollection("avatars.chunks")

db.getCollection("avatars.files").createIndex(
  { filename: 1, uploadDate: 1 },
  { name: "filename_1_uploadDate_1" }
)

db.getCollection("avatars.chunks").createIndex(
  { files_id: 1, n: 1 },
  { unique: true, name: "files_id_1_n_1" }
)
~~~

The name `fs` is not part of the key pattern. For a custom bucket, **change both collection names**. If you create `avatars.files` while chunks are stored in `fs.chunks`, a `GridFSBucket` with `bucketName` `avatars` will not find the right chunks.

### 10.4. Do Not Create the Unique Index While Duplicate Data Exists

If an improper import resulted in two chunks sharing `(files_id,n)`, creating the unique index will fail. Before fixing it, back up the data, identify which file is affected, and ensure you have the original source data to recover; never randomly delete one of the chunks in production.

## 11. Which Index Serves Each Query Pattern?

| Query | Appropriate Index |
|---|---|
| Find file metadata by `_id` | `fs.files._id_` |
| Search by name + list versions by `uploadDate` | `fs.files.{filename:1,uploadDate:1}` |
| Download `fileId` F: read chunks ordered by `n` | `fs.chunks.{files_id:1,n:1}` unique |
| Find files by tenant/owner/status | Additional index on `fs.files.metadata.*` if workload requires |
| Find file by SHA-256 checksum | Metadata checksum index if truly needed; do not default to unique |
| Clean up files by expiration policy | Index on metadata/expiration to find candidates; delete via GridFS API |

### 11.1. Indexes Help Find Files, Not Replace Business Authorization

A request:

~~~javascript
db.fs.files.find({
  "metadata.tenantId": "t-01",
  "metadata.ownerId": "user-18",
  filename: "monthly-report.bin"
})
~~~

may benefit from an additional index depending on volume:

~~~javascript
db.fs.files.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.ownerId": 1,
    uploadDate: -1
  },
  { name: "idx_tenant_owner_uploaded" }
)
~~~

This is a **candidate index**, not a mandatory GridFS index. Create it only after measuring real queries and understanding field types and selectivity.

### 11.2. Metadata Indexes Do Not Make Uploads Safer

Indexes speed up metadata filtering; they do not validate content types, remove malware, enforce download authorization, or verify checksums. Those checks belong in the application and file-processing pipeline.

### 11.3. Index Overhead

Every insert into `fs.files` and `fs.chunks` must update the associated indexes. For files with hundreds of thousands of chunks, the chunk index is a necessary cost; adding extra indexes on `chunks` without matching access patterns increases disk, CPU, and write amplification.

## 12. Checking Indexes with `explain()`

After uploading a file, you can inspect the chunk-reading plan:

~~~javascript
const fileDoc = db.fs.files.findOne({
  filename: "sample-700000.bin"
})

if (fileDoc) {
  db.fs.chunks.explain("executionStats").find({
    files_id: fileDoc._id
  }).sort({ n: 1 })
}
~~~

This query is solely to **explain the access path**. Actual file downloads must use `GridFSBucket`/driver APIs to verify length and stream bytes.

When reading `explain`, check:

- Does `winningPlan` use the `files_id_1_n_1` index?
- Is there a blocking sort stage?
- Does `nReturned` match the expected chunk count?
- Do `totalKeysExamined`/`totalDocsExamined` align with the chunk count?
- Does the query filter with the exact BSON value/type of `files_id`?

Stage names can vary across MongoDB/query engine versions. Do not treat an index scan as proof that no byte data is corrupted.

### 12.1. Index Prefix

`{files_id:1,n:1}` works because the query performs equality on `files_id` and then sorts/ranges on `n`. An index `{n:1,files_id:1}` is not equivalent for the workload "read all chunks of a single file."

### 12.2. Do Not Query by Chunk `_id`

`fs.chunks._id` identifies a single chunk document; drivers do not use it for byte ordering. The default `_id_` index does not replace the `(files_id,n)` compound index.

## 13. Uploading Files: Operation Order and Completion Timing

Typical flow:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Bucket as GridFSBucket
    participant Chunks as fs.chunks
    participant Files as fs.files
    App->>Bucket: Open upload stream(filename, metadata)
    loop Each chunk
        Bucket->>Chunks: insert {files_id, n, data}
    end
    App->>Bucket: Finish input stream
    Bucket->>Files: insert file metadata {length, chunkSize, ...}
    Bucket-->>App: Upload complete + fileId
~~~

By GridFS principle, **file metadata is written after the chunks have finished writing** so that a file is not published as a complete object while data is still missing. If an upload fails partway through, chunks without a `files` document may remain (depending on how the driver handles cleanup and the failure mode).

### 13.1. Not a Single Transaction Across All Chunks

Uploading a 5 GiB file involves thousands of chunk inserts. You cannot assume inserts into `fs.chunks` and `fs.files` are automatically **whole-file atomic** in the sense of a multi-document transaction. GridFS uses an **upload/download protocol**, not a substitute for a transaction engine.

### 13.2. What Does a File Appearing in `fs.files` Mean?

In normal driver uploads, the `files` document is typically created **after chunk writes complete**, allowing consumers to discover the uploaded logical file. However:

- Chunk data can still be corrupted by severe failures or manual edits.
- An arbitrary writer could create a malformed `files` document.
- Inconsistent backup/restore can break correspondence between the two collections.
- You cannot assume that a document in `fs.files` guarantees all physical data is intact in every failure scenario.

When integrity matters, verify stream length and checksums.

### 13.3. Upload Streams Should Not Buffer the Whole File

The goal of GridFS is to **stream chunks**. Avoid:

~~~javascript
// UNSUITABLE for multi-GiB files:
const entireFile = await fs.promises.readFile(path)
await uploadAllBytesAtOnce(entireFile)
~~~

This still loads the entire file into RAM, forfeiting the benefit of streaming.

## 14. Node.js: Streaming Uploads via `GridFSBucket`

Modern driver example:

~~~javascript
import { MongoClient, GridFSBucket } from "mongodb";
import { createReadStream } from "node:fs";
import { pipeline } from "node:stream/promises";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

try {
  const database = client.db("gridfs_lab");
  const bucket = new GridFSBucket(database, {
    bucketName: "fs",
    chunkSizeBytes: 261120
  });

  const source = createReadStream("sample-700000.bin");
  const upload = bucket.openUploadStream(
    "sample-700000.bin",
    {
      metadata: {
        tenantId: "t-01",
        ownerId: "user-18",
        contentType: "application/octet-stream",
        documentType: "lab"
      }
    }
  );

  const fileId = upload.id;
  await pipeline(source, upload);
  console.log("Upload completed, fileId =", fileId);
} finally {
  await client.close();
}
~~~

This snippet requires an **existing local file `sample-700000.bin`** at a controlled path. It does not generate the file and does not guarantee the actual file is 700,000 bytes; the name is just for identification. Metadata fields `tenantId` and `ownerId` must come from the **application's trusted context**, never unconditionally from the request body.

### 14.1. Why Capture `fileId` Before the Pipeline Completes?

`openUploadStream()` creates a stream whose ID is known upfront, but **knowing the ID does not mean the upload has succeeded**. Only after `await pipeline(...)` completes without error should you publish `fileId` as a downloadable file.

### 14.2. When the Pipeline Fails

If the source read fails, the network drops, or the upload stream aborts, cleanup depends on state and driver behavior. Do not expose `fileId` to users as a completed file. Record the upload attempt, log the error code, and have a process to clean up orphan chunks once you are certain no upload is still active.

### 14.3. Chunk Size Is a Bucket/Upload Option

MongoDB records the actual `chunkSize` in `fs.files`. Do not read a runtime configuration variable to compute the chunk count of **a file uploaded last week**, because bucket settings may have changed.

## 15. Node.js: Downloading by ID

Using the `fileId` obtained after upload:

~~~javascript
import { MongoClient, GridFSBucket, ObjectId } from "mongodb";
import { createWriteStream } from "node:fs";
import { pipeline } from "node:stream/promises";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

try {
  const database = client.db("gridfs_lab");
  const bucket = new GridFSBucket(database, {
    bucketName: "fs"
  });

  // Example ID: replace with a valid uploaded file ID.
  const fileId = new ObjectId("6748abcd1234567890abcdef");

  // Production: check permissions on fs.files before downloading.
  const download = bucket.openDownloadStream(fileId);
  const output = createWriteStream("downloaded.bin");

  await pipeline(download, output);
  console.log("Downloaded");
} finally {
  await client.close();
}
~~~

**Note:** The ObjectId above is a 24-character hex placeholder. For the demo to succeed, replace it with the real ID of a file you just uploaded, and choose an output path that will not overwrite important files. If the file's `_id` is not an ObjectId, use the matching BSON type rather than forcing it to `ObjectId`.

### 15.1. Do Not Let Clients Choose Arbitrary Local Paths

In an API server, never use a user-submitted filename directly as an unvalidated filesystem path. If a client requests a download named `../../secret.txt` and the server writes directly to disk, it can cause path traversal. The local path is determined by the **service**; the GridFS filename is display metadata.

### 15.2. Downloading by Filename

Some GridFS drivers provide `openDownloadStreamByName`. This API must determine a **revision** when multiple versions share a filename; defaults/options must be checked for your driver version. When a business entity already holds the `fileId`, prefer `openDownloadStream(fileId)` to avoid downloading the wrong version.

### 15.3. Serving Files over HTTP

Streaming to the HTTP response reduces RAM compared to reading the whole file into a buffer. Before streaming:

1. Authenticate the principal.
2. Query `fs.files` and verify tenant/owner/permissions.
3. Set a safe `Content-Type` per policy, without trusting unvalidated metadata.
4. Set `Content-Disposition` to prevent dangerous content from rendering inline unexpectedly.
5. Enforce rate/concurrency limits, and handle client disconnects and stream errors.

GridFS does not enforce access control from metadata fields automatically.

## 16. Java Sync Driver: `GridFSBucket` and Upload/Download

Example using the MongoDB Java Sync Driver and `GridFSBuckets`:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import org.bson.Document;
import org.bson.types.ObjectId;

public class GridFSUploadDownloadDemo {
    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("gridfs_lab");
            GridFSBucket bucket = GridFSBuckets.create(database, "fs");

            GridFSUploadOptions options = new GridFSUploadOptions()
                .chunkSizeBytes(261120)
                .metadata(new Document("tenantId", "t-01")
                    .append("ownerId", "user-18")
                    .append("contentType", "application/octet-stream"));

            ObjectId fileId;
            try (InputStream source =
                    new FileInputStream("sample-700000.bin")) {
                fileId = bucket.uploadFromStream(
                    "sample-700000.bin", source, options
                );
            }

            try (OutputStream output =
                    new FileOutputStream("downloaded-copy.bin")) {
                bucket.downloadToStream(fileId, output);
            }

            System.out.println("GridFS fileId: " + fileId);
        }
    }
}
~~~

In this code:

- `GridFSBuckets.create(database,"fs")` uses the default bucket with prefix `fs`.
- `uploadFromStream` reads from `InputStream`, splits chunks by `chunkSizeBytes`, and creates file metadata.
- `downloadToStream` looks up `fs.files` and `fs.chunks` by ID, writing to `OutputStream`.
- Hard-coded local paths are suitable only for labs; production services must control permissions and paths.
- The code uses `ObjectId` as it is the most common ID type; depending on the API/version, custom BSON IDs may be supported.

### 16.1. Do Not Mix Bucket Names When Downloading

If you upload using bucket `exports`:

~~~java
GridFSBucket exports = GridFSBuckets.create(database, "exports");
~~~

you must download using **the same bucket**. Using the default `fs` bucket to download an ID stored in `exports.files` will report file not found, even though the ObjectId exists in another collection.

## 17. Inspecting Uploaded Files with `mongosh`

After an actual successful upload:

~~~javascript
use gridfs_lab

const fileDoc = db.fs.files.findOne({
  filename: "sample-700000.bin"
})

printjson(fileDoc)
~~~

The file may not be exactly 700,000 bytes if the name does not reflect its size; calculations must always use the **actual `fileDoc.length`**.

### 17.1. Listing Chunks Without Printing Binary Data

~~~javascript
if (fileDoc) {
  db.fs.chunks.find(
    { files_id: fileDoc._id },
    { data: 0 }
  ).sort({ n: 1 })
}
~~~

The `{data:0}` projection avoids printing long binary payloads. Never output raw `BinData` to consoles/logs, especially when files contain sensitive data.

### 17.2. Counting Chunks

~~~javascript
if (fileDoc) {
  print("Chunks =", db.fs.chunks.countDocuments({
    files_id: fileDoc._id
  }))
}
~~~

### 17.3. Checking Expected Chunk Count

~~~javascript
if (fileDoc) {
  const expected = Math.ceil(
    Number(fileDoc.length) / fileDoc.chunkSize
  )
  const actual = db.fs.chunks.countDocuments({
    files_id: fileDoc._id
  })

  printjson({
    fileId: fileDoc._id,
    expectedChunks: expected,
    actualChunks: actual
  })
}
~~~

Coercing `Number(fileDoc.length)` is only safe for labs and sufficiently small files. For very large files, use appropriate 64-bit integer/`BigInt` types. **Matching counts alone do not prove the file is intact**; chunks could be missing `n=2` and have `n=3` instead, or `data` could be altered.

### 17.4. Checking Chunk Byte Length in `mongosh`

To inspect actual byte length in a lab setting using the `BinData` API of your `mongosh` version:

~~~javascript
const firstChunk = db.fs.chunks.findOne(
  { files_id: fileDoc._id, n: 0 }
)

if (firstChunk) {
  print("First chunk exists")
  // No need to decode/print the entire binary payload in the CLI.
}
~~~

To verify integrity, use **streaming download + application-side checksum** instead of loading all `data` into `mongosh` and creating memory pressure.

## 18. Distinguishing Metadata Queries from Reading File Contents

A search API:

~~~javascript
db.fs.files.find(
  {
    "metadata.tenantId": "t-01",
    filename: "sample-700000.bin"
  },
  {
    _id: 1,
    filename: 1,
    uploadDate: 1,
    length: 1,
    metadata: 1
  }
).sort({ uploadDate: -1 })
~~~

reads **metadata**, without downloading bytes. The application retrieves `_id` and then calls `GridFSBucket` to stream content. This is a good pattern:

~~~text
Find metadata + authorize
  -> choose exact fileId
  -> GridFSBucket.openDownloadStream(fileId)
  -> stream bytes
~~~

Do not query:

~~~javascript
db.fs.chunks.find({ files_id: fileId })
~~~

and serialize those documents into a JSON HTTP response to download a file; that increases memory/network overhead and leaks internal storage structure.

## 19. Chunk Size: Non-Trivial Trade-Offs

The default of around **255 KiB** is usually a reasonable starting point, though not an absolute optimum.

### 19.1. Smaller Chunks

Pros:

- Each read/write operation carries a smaller payload.
- Can be more flexible when incremental streaming processing is needed.
- Keeps each BSON document smaller.

Cons:

- Large files produce **many more documents**.
- More entries in the `fs.chunks` index.
- More insert/read operations and per-chunk overhead.
- Higher metadata/document overhead relative to byte payload.

### 19.2. Larger Chunks

Potential pros:

- Fewer documents/chunk inserts for the same file.
- Fewer index entries.
- Can reduce per-operation overhead in some workloads.

Cons:

- Each operation transfers a larger payload.
- Heavier when reading a small slice or when backpressure/memory is constrained.
- Must remain under the 16 MiB BSON document limit and driver/protocol limits.
- Does not automatically boost throughput if the bottleneck is network, disk, or replication.

### 19.3. Comparison Example for a 100 MiB File

Let `L=104857600 bytes`:

| Chunk size | Expected chunk count |
|---|---:|
| 255 KiB = 261120 bytes | 402 |
| 256 KiB = 262144 bytes | 400 |
| 1 MiB = 1048576 bytes | 100 |
| 4 MiB = 4194304 bytes | 25 |

These numbers are only divisions for chunk counts, **not a performance benchmark**. Increasing chunk size does not automatically make uploads 4× faster.

### 19.4. Choosing Based on Workload

Measure:

- P50/p95/p99 upload/download latency.
- Throughput in bytes/s and concurrent streams.
- Operations per second on `fs.chunks`.
- CPU/disk cache/network on primary/secondaries.
- Index size and data size.
- Backpressure behavior when clients have slow connections.
- Ratio of small files to large files.

Do not switch an entire system to 8 MiB chunks just to reduce insert counts, especially when most files are only 200 KiB.

## 20. What About Files Smaller Than the Chunk Size?

For example, a 32 KiB file with `chunkSize=261120`:

~~~text
fs.files.length = 32768
fs.files.chunkSize = 261120
fs.chunks: n=0, data=32768 bytes
~~~

GridFS still creates a `files` metadata document and one chunk for a non-empty small file. The GridFS model has a minimum overhead of **two documents** plus index entries. If an application stores countless 1 KiB icons, the overhead may outweigh a simpler data model or object storage. GridFS is not the default choice for every small binary payload.

## 21. Very Large Files: Chunk Counts and Practical Limits

GridFS allows storing files larger than 16 MiB by splitting them into chunks, but that does not make the system limitless:

- Disk capacity, quotas, and oplog have limits.
- Replica sets must replicate all chunks.
- Upload speed is bounded by network/driver/backpressure.
- Very large files produce huge numbers of chunks and index entries.
- Backup/restore must remain consistent across **both collections**.
- Failed uploads can leave partial data behind.
- Each BSON chunk document remains subject to BSON limits.

If an application routinely stores multi-GiB to multi-TB media, compare GridFS against object storage in terms of throughput, CDN, cost, range retrieval, lifecycle, and administration.

### 21.1. Do Not Wrap an Entire File in One Multi-Document Transaction

Avoid designs like:

~~~text
BEGIN TRANSACTION
  Upload 5 GiB consisting of tens of thousands of chunk inserts
  Write business record
COMMIT
~~~

A long/large transaction can exceed lifetime, cache, or other limits. Nor should the GridFS API be assumed to behave like an atomic single-document operation inside arbitrary transactions. If you need consistent publication of a file and business record at the application level, use a **staging/publish state**, not a giant transaction.

## 22. File Lifecycle: PENDING, READY, and DELETED

A practical application pattern uses a **regular collection** to manage file references and business lifecycle:

~~~javascript
{
  _id: "attachment-001",
  tenantId: "t-01",
  ownerId: "user-18",
  gridFsFileId: ObjectId("6748abcd1234567890abcdef"),
  bucketName: "fs",
  state: "READY",
  expectedSha256: "application-computed-sha256",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

A workflow:

~~~mermaid
flowchart TD
    Start["Create upload intent"] --> Pending["Business state=PENDING"]
    Pending --> Stream["Stream file into GridFS"]
    Stream --> Success{"Upload completed?"}
    Success -->|"No"| Failed["FAILED; clean up per policy"]
    Success -->|"Yes"| Verify["Verify length/checksum/content scan"]
    Verify --> Ready["Publish business reference=READY"]
    Ready --> Download["Allow download only when authorized"]
    Ready --> Delete["Receive delete request"]
    Delete --> Cleanup["GridFSBucket.delete(fileId)"]
    Cleanup --> Deleted["Mark DELETED/write audit"]
~~~

### 22.1. Publish the File After Upload

Do not write the business record in state `READY` when you only **know the `fileId`** before the stream finishes. If the application crashes between upload and publish, a reconciliation job must distinguish complete unpublished files from orphan chunks.

### 22.2. Do Not Promise Two-Phase Atomicity Just Because There Are Two Steps

A staging/publish workflow has **intermediate states** and requires recovery. If the post-upload job crashes before updating the business reference, a complete GridFS file may exist without being linked yet. Use a stable upload intent ID, timeouts, and reconciliation.

## 23. Incomplete Uploads: Orphan Chunks

An upload might write:

~~~text
fs.chunks:
  files_id=F1 n=0
  files_id=F1 n=1
  files_id=F1 n=2

fs.files:
  no _id=F1 yet
~~~

These are **orphan chunks**: chunk documents without a corresponding `files` document. Some drivers attempt cleanup on normal abort, but crashes or network failures can still leave data behind. Never assume every upload failure cleans up cleanly.

### 23.1. Caution Regarding Orphan Scanners

A join/aggregation to detect `files_id` values lacking metadata can be useful for auditing, but **do not automatically delete everything**:

- A valid **in-progress** upload also has chunks before its `files` document is created.
- Secondary reads may lag.
- Long batch uploads may still be running.
- An older backend instance might be retrying/recovering.

Only clean up after a **safe grace period** has elapsed, after confirming no active upload session remains, and with backup/auditing per policy.

### 23.2. Audit Example Using Aggregation

For lab investigation, you can group by `files_id` and compare against `files` metadata:

~~~javascript
db.fs.chunks.aggregate([
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 },
      minN: { $min: "$n" },
      maxN: { $max: "$n" }
    }
  },
  {
    $lookup: {
      from: "fs.files",
      localField: "_id",
      foreignField: "_id",
      as: "file"
    }
  },
  {
    $match: {
      file: { $size: 0 }
    }
  },
  {
    $project: {
      _id: 1,
      chunkCount: 1,
      minN: 1,
      maxN: 1
    }
  }
])
~~~

This aggregation can be expensive on very large `chunks` collections; it **only identifies candidates** and does not verify age or active uploads. Do not run it across a production cluster during peak hours without a plan.

### 23.3. Safe Orphan Cleanup

Prefer a workflow that tracks upload intents/active sessions, checks age, verifies backups, and deletes in small batches. Avoid patterns like:

~~~javascript
// DO NOT use in production:
db.fs.chunks.deleteMany({
  files_id: { $nin: allKnownFileIds }
})
~~~

This command can delete chunks from active uploads, corrupt data, and scan the entire collection.

## 24. Files with Metadata but Missing Chunks

For example:

~~~text
fs.files:
  _id=F2, length=700000, chunkSize=261120

fs.chunks:
  files_id=F2 n=0
  files_id=F2 n=2
~~~

Chunk `n=1` is missing, even though the `files` document exists. Unique `{files_id:1,n:1}` does not prevent this scenario. Depending on driver/version, downloading may fail with a missing-chunk or chunk-size-mismatch error.

### 24.1. How to Handle It

1. Do not attempt to export the file "at all costs" when bytes are known to be missing.
2. Log `fileId`, chunk count, and the error—do not log binary data.
3. Check recent deployments, manual deletions, backup/restore events, and disk faults.
4. If the original source file exists, re-upload it as a **new `fileId`**, verify checksums, and update the reference.
5. Never fabricate chunk `n=1` with empty bytes or duplicate another chunk.

### 24.2. Do Not Trust Count Alone

A file with `N=3` chunks where `n` values are `0, 1, 4` still has **count=3**. You must check for a **contiguous sequence** and individual chunk sizes, and ultimately verify a full-file checksum when required.

## 25. Checksums, Integrity, and Legacy `md5`

GridFS stores bytes; end-to-end integrity is an application-level requirement. A strong policy might record:

~~~javascript
metadata: {
  sha256: "sha256-digest-hex",
  expectedLengthBytes: NumberLong("700000"),
  contentType: "application/octet-stream"
}
~~~

The SHA-256 value must be **computed from the actual content** by the application, not a placeholder.

### 25.1. Streaming SHA-256

In Node.js:

~~~javascript
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";

async function sha256OfFile(path) {
  const hash = createHash("sha256");

  for await (const chunk of createReadStream(path)) {
    hash.update(chunk);
  }

  return hash.digest("hex");
}
~~~

This function computes the checksum without reading the whole file into RAM. In production, if hashing before upload and the source file could change between two reads, ensure an immutable source or hash inline with the pipeline via a safe streaming mechanism. You can recompute the checksum on the download stream to verify it matches the stored value.

### 25.2. Checksums Differ from Authentication

A checksum confirms content matches the expected digest, but if an attacker has permission to modify both the file **and** the metadata checksum, it can still be forged. You need access controls, auditing, encryption/signatures, or integrity protections aligned with your threat model.

### 25.3. Do Not Assume GridFS Generates SHA-256

The GridFS specification does not make SHA-256 a mandatory field in `fs.files`. `metadata.sha256` is an **application convention** and must be computed and verified explicitly.

## 26. Deleting Files: Both Metadata and Chunks Must Be Cleaned Up

`GridFSBucket` provides deletion by **file ID**, for example in Node.js:

~~~javascript
import { MongoClient, GridFSBucket, ObjectId } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

try {
  const bucket = new GridFSBucket(client.db("gridfs_lab"));
  const fileId = new ObjectId("6748abcd1234567890abcdef");

  // Call only after authentication and verifying deletion permission.
  await bucket.delete(fileId);
} finally {
  await client.close();
}
~~~

Replace the example ObjectId with a real ID. `GridFSBucket` handles deleting both file metadata and corresponding chunks according to the API/driver. Do not test `delete` on production files.

### 26.1. Wrong: Deleting Only `fs.files`

~~~javascript
// DO NOT do this:
db.fs.files.deleteOne({ _id: fileId })
~~~

Without cleaning up `fs.chunks`, file metadata disappears while chunks continue occupying storage, creating orphans.

### 26.2. Wrong: Deleting Only `fs.chunks`

~~~javascript
// DO NOT do this:
db.fs.chunks.deleteMany({ files_id: fileId })
~~~

File metadata remains while downloads lack bytes, creating a corrupted file. Perform direct edits only under a verified repair/recovery runbook with clear ownership.

### 26.3. Deletion Is Not Always Atomic Across Both Collections

Deleting a GridFS file involves multiple document operations. Depending on where a failure occurs, retry/reconciliation may be required. An application needs lifecycle states like `DELETING`/`DELETED` and background cleanup rather than promising users every byte was physically erased the instant the API starts processing.

## 27. Retention and TTL: Beware of Orphan Chunks

A seemingly reasonable idea:

~~~javascript
// DANGEROUS if used as a complete file-deletion mechanism.
db.fs.files.createIndex(
  { uploadDate: 1 },
  { expireAfterSeconds: 2592000 }
)
~~~

A TTL index on `fs.files` only affects **documents in the `files` collection**—it does not know to delete corresponding documents in `fs.chunks`. The result can create **a huge number of orphan chunks**.

### 27.1. What Should Proper Retention Do?

A workflow:

1. Identify expired files using business policy and metadata (e.g., `metadata.expiresAt`).
2. Check whether the file is still referenced by business records, legal holds, or active workflows.
3. Mark it for deletion and write an audit log.
4. Call `GridFSBucket.delete(fileId)` with appropriate retry/backoff.
5. Reconcile in case of partial deletion failure.
6. Monitor orphan chunks and storage reclamation.

### 27.2. Index for Finding Candidates

~~~javascript
db.fs.files.createIndex(
  {
    "metadata.expiresAt": 1,
    "metadata.tenantId": 1
  },
  { name: "idx_expiry_tenant" }
)
~~~

This is a **regular index**, not a TTL index. It helps a cleanup worker find files whose `expiresAt` has passed and then call the GridFS API. Order keys according to actual queries and multi-tenant characteristics; do not index every metadata field.

### 27.3. Backups and Deletion Compliance

Deleting from active GridFS does not automatically remove copies in backups, object caches, or downstream systems. If personal-data deletion policies apply, evaluate the entire retention/backup lifecycle rather than just a single `delete` API call.

## 28. File Versioning and Filename Collisions

Two files with different IDs but the same filename can represent versions:

~~~javascript
// Illustrative metadata query output:
[
  { _id: "F-new", filename: "invoice.pdf", uploadDate: ISODate("2026-11-14T09:00:00Z") },
  { _id: "F-old", filename: "invoice.pdf", uploadDate: ISODate("2026-10-14T09:00:00Z") }
]
~~~

MongoDB does not automatically generate version numbers `1, 2, 3` for identical names; `uploadDate` and ID provide lookup order, while **version semantics** must be defined by the application.

### 28.1. Lookup by Name Can Be Ambiguous

~~~javascript
db.fs.files.find({ filename: "invoice.pdf" })
  .sort({ uploadDate: -1 })
~~~

If two files share the exact same `uploadDate` down to the millisecond, a deterministic tie-breaker is needed. For workflows requiring revisions 1, 2, 3, store `metadata.revision` or a regular reference record with appropriate unique constraints.

### 28.2. Tenant + Filename

If two tenants both upload `avatar.png`, searching by filename alone mixes results. Before downloading, query metadata with `tenantId` from the authenticated principal and verify owner/access policy, then download using the exact `fileId`.

### 28.3. Deduplicating by Checksum?

Two files with the same SHA-256 have identical bytes, yet may differ in owner, permissions, retention period, or encryption. Physical deduplication is not a free built-in GridFS feature. If you build content-addressable storage yourself, you must handle reference counting, access permissions, isolation, race conditions, and ensure bytes are never deleted while another user still references them.

## 29. Backup and Restore: Both Collections Must Be Consistent

A snapshot of `fs.files` at 10:00 and a snapshot of `fs.chunks` at 10:15 may not represent the same logical file state, especially while uploads/deletes are running:

~~~text
10:00: fs.files does not yet have F1
10:05: upload of F1 completes
10:15: fs.chunks already contains F1
~~~

Restoring the two parts from different points in time can leave orphan chunks. The reverse scenario can restore metadata with missing chunks.

### 29.1. Consistent Backups

Use a backup/restore strategy suited to your MongoDB topology (replica set/sharded cluster), with a tool-guaranteed consistency point. Do not manually copy `fs.files` at one time and `fs.chunks` at an arbitrary time and treat them as a complete backup.

### 29.2. After Restore

Verify:

- Both collections and their indexes are present.
- File/chunk counts and storage sizes look reasonable.
- No orphan chunks or files with missing chunks exist.
- A sample set of files can be downloaded and verified with SHA-256.
- Business references point to existing `fileId` values.
- Encryption keys, credentials, and ACLs were restored properly.

## 30. Replica Sets, Sharding, and GridFS

GridFS stores **many documents**, so replication handles inserts and deletes across two collections. For large files, uploads generate a continuous stream of writes through the primary and oplog; secondaries must replicate and apply them.

### 30.1. Read Preference and Freshness

If an upload just finished on the primary, reading `fs.files` and `fs.chunks` from a lagging secondary may not yet see the file or a complete view depending on consistency settings. For requirements like "immediately downloadable right after upload," consider reading from primary or using appropriate read/write concerns and causal consistency.

### 30.2. Write Concern

Write concern governs write durability during upload. `w:"majority"` may fit critical documents but adds commit latency when the cluster experiences replication lag. Do not infer upload success from a single chunk insert; wait for the **stream to complete** and follow your durability policy.

### 30.3. GridFS on a Sharded Cluster

If you need to distribute file data across multiple shards:

- Review **collection sharding and unique index rules** for your MongoDB version.
- `fs.chunks` has a mandatory unique compound index on `{files_id:1,n:1}`; the shard key and unique-index constraints must be compatible.
- `fs.files` and `fs.chunks` are **two separate collections** and may have different routing/placement requirements.
- Do not arbitrarily choose a hashed shard key or drop the unique chunk index just to make sharding succeed.
- Uploads/downloads may touch multiple shards and introduce network/coordination overhead.

Sharding GridFS is an advanced architectural decision; inspect version documentation, datasets, and specific workloads. Do not replace a proper runbook with a few unplanned `sh.shardCollection` commands.

### 30.4. When Workloads Are Very Large

Compare against object storage on:

- Cost per GB and egress charges.
- CDN, byte-range requests, signed URLs.
- File count and throughput.
- Multi-region replication and lifecycle/archival.
- Access policies and compliance.

GridFS is valuable when you want file storage inside MongoDB alongside metadata/queries/workflows; it is not always cheaper at global media scale.

## 31. Access Control and File Content Safety

Binary files are not automatically safe just because they live in a database.

### 31.1. Authentication and Authorization

A download API should:

~~~text
User principal
  -> check tenant/owner/business policy
  -> look up fs.files by exact fileId
  -> verify metadata matches authorized access
  -> GridFSBucket streams content
  -> audit download
~~~

Never take `ownerId` from a request body to decide permissions; obtain it from the authenticated session/token and business rules.

### 31.2. Content Type and File Extension

Do not blindly trust `filename:"photo.jpg"` or `metadata.contentType:"image/jpeg"` provided by the client. Inspect magic bytes/MIME using appropriate tools, scan for malware per your threat model, and control how browsers render the file. HTML/script files are dangerous if served inline with an unsafe `Content-Type`.

### 31.3. Do Not Log Binary Payloads

Never print `fs.chunks.data` to logs, analytics, or error reports. Doing so risks leaking user data, inflating log costs, and hindering investigations.

### 31.4. Encryption

MongoDB provides transport and at-rest protection depending on deployment; if application-level encryption is required, encrypt the file before upload and store appropriate encryption metadata/key version. Never store the encryption key inside `fs.files.metadata` alongside the ciphertext.

## 32. Common Performance Issues

### 32.1. Chunk Queries Not Using the Index

~~~javascript
db.fs.chunks.find({ files_id: fileId }).sort({ n: 1 })
~~~

Without `{files_id:1,n:1}`, the query may scan chunks from many other files or perform a blocking sort; download speed drops sharply. Check the standard index and query plan.

### 32.2. Huge Files with Too-Small Chunk Sizes

A 50 GiB file with 8 KiB chunks creates millions of chunks, inflating I/O and index entries. Choose a chunk size suited to memory/network capacity and file-transfer goals.

### 32.3. Using GridFS Unconditionally for Tiny Files

If most files are 1–2 KiB and counts are huge, the overhead of two collections and indexes may not be worthwhile. A regular collection or object storage is often better.

### 32.4. Unbounded Filename Lookups on Every Download

Searching by filename and picking the newest file can behave unexpectedly due to name collisions or version updates. Use the exact `fileId` bound to the business reference and authorization.

### 32.5. Ignoring Backpressure

Streaming does not mean the network path is always fast enough. Handle client disconnects, limit concurrent streams, and enforce request timeouts and rate limits to avoid exhausting connection pools or database resources.

### 32.6. Excessive Indexing

Not every metadata field needs its own index. Monitor `totalIndexSize`, write latency, query frequency, and cache pressure.

## 33. Troubleshooting Common Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Download reports file not found | Wrong `fileId` or bucket prefix | Check `<bucket>.files` and ID BSON type |
| Download missing chunk | Missing `n` in `<bucket>.chunks` | Count/sort chunks, compare with `length` |
| Duplicate key on chunk insert | Duplicate `(files_id,n)` | Unique index and upload logic |
| File exists but opens corrupted | Altered/missing chunk or wrong checksum | Stream download and hash, audit |
| Disk space does not shrink after metadata delete | Orphan chunks | Verify deletion via `GridFSBucket` |
| Many orphan chunks | Upload crashes/failed cleanup or TTL on `files` | Audit with a grace period |
| Search by filename returns multiple files | Filename is not unique | Select exact `fileId`/revision |
| First upload unusually slow | First-time collection/index creation | Check migrations/indexes |
| Slow downloads with many files | Missing chunk index or I/O contention | `explain`, metrics, indexes |
| Byte count mismatch | Confused characters/bytes or wrong chunk size | Check `length` and streaming checksum |
| New file missing on secondary | Replication lag/read consistency | Read preference and lag |
| Sharding reports index error | Incompatible shard key/unique constraints | Review version rules and design |
| File deleted before retention expires | TTL on `files` or wrong cleanup policy | Audit retention |

### 33.1. Fixes to Avoid

Do not bulk-delete `fs.chunks` simply because a query saw no `fs.files` entry at that instant; new uploads may be in flight. Do not drop the unique index to let a failing upload proceed. Do not manually edit `n` or `data` without the original source bytes and a verified repair plan.

## 34. Practice A — Identifying the Schema

Given two documents:

~~~javascript
// Document A
{
  _id: ObjectId("6748abcd1234567890abcdef"),
  filename: "sample.bin",
  length: NumberLong("700000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:30:00Z")
}

// Document B
{
  _id: ObjectId("6748abcd1234567890abc001"),
  files_id: ObjectId("6748abcd1234567890abcdef"),
  n: 0,
  data: BinData(0, "...")
}
~~~

Answer:

1. Which document belongs to `fs.files`? Which belongs to `fs.chunks`?
2. Which field links the two documents?
3. Can `filename` be used instead of `files_id` in a chunk? Why or why not?
4. What does `n=0` mean?

## 35. Practice B — Calculating Chunk Counts

Given `L=700000`, `C=261120`. Calculate:

- Number of chunks.
- Sizes of `n=0`, `n=1`, and `n=2`.
- Starting byte offset of `n=2`.

Then calculate the chunk counts when `L=0` and `L=522240`.

## 36. Practice C — Identifying Mandatory Indexes

Among the following indexes, select the two core GridFS indexes:

~~~javascript
{ filename: 1 }
{ filename: 1, uploadDate: 1 }
{ files_id: 1, n: 1 }
{ n: 1, files_id: 1 }
{ "metadata.tenantId": 1 }
~~~

Which index is **unique**? Why cannot the other indexes substitute for them?

## 37. Practice D — Duplicate Filenames

A bucket contains three files:

~~~text
F1: filename=invoice.pdf, uploadDate=2026-10-01
F2: filename=invoice.pdf, uploadDate=2026-11-01
F3: filename=invoice.pdf, uploadDate=2026-11-14
~~~

Requirements:

- Write a query listing all three files, sorted newest first.
- Explain why `filename` is not unique.
- Design a reference from a business invoice to `F2` so it does not automatically switch to `F3`.

## 38. Practice E — Inspecting `GridFSBucket` After Upload

Run Node or Java to upload a lab file, then in `mongosh`:

~~~javascript
db.fs.files.getIndexes()
db.fs.chunks.getIndexes()
db.fs.files.find({}, { filename: 1, length: 1, chunkSize: 1, uploadDate: 1 })
~~~

Pick an actual `fileId` and inspect its chunks:

~~~javascript
const file = db.fs.files.findOne({
  filename: "sample-700000.bin"
})

if (file) {
  db.fs.chunks.find(
    { files_id: file._id },
    { data: 0 }
  ).sort({ n: 1 })
}
~~~

Identify what value `n` starts from, the actual chunk count, and which field holds the raw binary data.

## 39. Practice F — Missing Chunk

Suppose:

~~~text
fs.files:  F1 length=700000 chunkSize=261120
fs.chunks: F1 n=0, n=2
~~~

Answer:

1. Expected chunk count?
2. Does the unique index detect the missing `n=1`?
3. What error might downloading encounter?
4. Should you manually create chunk `n=1` with empty bytes?
5. What data source should the recovery workflow use?

## 40. Practice G — Incomplete Upload

An upload loses network connectivity after writing 20 chunks; no `files` document is found. Explain:

- Why do chunks remain without file metadata?
- Why should you not immediately delete every orphan candidate?
- What information must a cleanup job check?

## 41. Practice H — Misconfigured TTL

A team creates:

~~~javascript
db.fs.files.createIndex(
  { uploadDate: 1 },
  { expireAfterSeconds: 86400 }
)
~~~

Questions:

1. Which collection does this index delete documents from?
2. Are the corresponding chunks automatically deleted?
3. Why can storage usage grow?
4. Design a cleanup worker using `GridFSBucket.delete` and auditing.

## 42. Practice I — Chunk Size

A 100 MiB file has `chunkSize=255 KiB`. Calculate the expected chunk count. Then suppose chunk size is changed to 1 MiB:

- How does the chunk count change?
- How might index/operation costs change?
- Can we conclude throughput increases 4×?
- Does the driver downloading the old file use the new chunk size or the value stored in `fs.files`?

## 43. Practice J — Security and Metadata Indexes

Design:

~~~javascript
metadata: {
  tenantId: "t-01",
  ownerId: "user-18",
  contentType: "application/pdf",
  expiresAt: ISODate("2027-01-01T00:00:00Z")
}
~~~

Write a query to find an owner's files within a tenant, sorted newest first. Choose a suitable additional index. Explain why `metadata.ownerId` **does not automatically grant permissions** to a user.

## 44. Practice K — Custom Bucket

A service uploads into bucket `exports`. Fill in the names of the two collections and the two standard GridFS indexes. If a download uses bucket `fs`, what happens? Can the same `fileId` exist in two different buckets?

## 45. Practice L — Integrity

Upload a file, compute SHA-256 on the client, and store `metadata.sha256`. On download, recompute SHA-256 from the stream:

- When must the two checksums match?
- If downloaded bytes are missing/altered, what are the symptoms?
- Why should legacy MD5 not be the sole integrity check?
- Why is SHA-256 stored inside metadata insufficient against an attacker permitted to modify both the file and the checksum?

## 46. Practice Answer Hints

**A:** Document A belongs to `fs.files`; Document B belongs to `fs.chunks`. `files_id` equals `files._id`; `n=0` is the first chunk. Filenames can collide and therefore cannot replace the identifier.

**B:** Three chunks. `n=0` is 261,120 bytes, `n=1` is 261,120, `n=2` is 177,760; offset of `n=2` is 522,240. Empty file: 0 chunks. 522,240-byte file: 2 chunks.

**C:** `{filename:1,uploadDate:1}` on `files` is **non-unique**; `{files_id:1,n:1}` on `chunks` is **unique**. The other indexes do not preserve the required query/index invariants.

**D:** `find({filename:"invoice.pdf"}).sort({uploadDate:-1})`; store `fileId=F2` in the business reference to always download the exact version.

**E:** Indexes must match `files` filename/uploadDate and `chunks` unique `files_id`/`n`. `n` starts at 0; `data` is BSON binary. Check chunk count using the real file's `length/chunkSize`.

**F:** Expected 3 chunks, missing `n=1`. The unique index does not detect the gap. Download may fail with missing chunk/corruption. Do not fabricate bytes; recover from the original source file or a consistent backup.

**G:** Chunks were written before metadata; the upload never finished. An orphan candidate could be an upload still in progress. Check active intents, data age, grace period, backups, and run batch cleanup.

**H:** TTL on `fs.files` deletes only metadata and can leave orphan chunks. A cleanup worker must find expired files and delete them via the GridFS API, with retries and audit/reconciliation.

**I:** 100 MiB at 255 KiB requires 402 chunks; at 1 MiB it requires 100 chunks. Fewer chunks can reduce operations/index entries, but you cannot conclude throughput scales proportionally. Drivers read the `chunkSize` stored per file.

**J:** Query by `metadata.tenantId`, `metadata.ownerId`, sorting `uploadDate:-1`; candidate index `{ "metadata.tenantId":1, "metadata.ownerId":1, uploadDate:-1 }`. Authorization is enforced by the application based on the principal, not automatically by MongoDB from metadata.

**K:** `exports.files`, `exports.chunks`, with filename/uploadDate and unique `files_id`/`n` indexes. Bucket `fs` will not automatically see files in `exports`. `_id` is unique only per collection; pair `bucketName` with `fileId` if an ID could exist across multiple buckets.

**L:** Upload and download SHA-256 values must match if bytes are unchanged. A mismatch indicates bad data or differently computed metadata/hash. Legacy MD5 does not meet modern integrity requirements; access controls/signatures are needed if the threat model includes an attacker modifying both data and hash.

## 47. Mistakes to Avoid

| Mistake | Consequence | Right Approach |
|---|---|---|
| Storing a 100 MiB file in one BSON document | Exceeds 16 MiB | Use GridFS or object storage |
| Thinking GridFS only has `fs.files` | Ignoring chunks/data | Always account for both collections |
| Using `filename` as a unique ID | Version/name collisions | Store and download by exact `fileId` |
| Using `n` as a collection-wide ID | Every file starts at `n=0` | Use `(files_id,n)` |
| Omitting the unique chunk index | Duplicate chunk positions, non-deterministic downloads | `{files_id:1,n:1} unique` |
| Making `filename` unique | Cannot upload versions with the same name | Regular non-unique `files` filename/uploadDate index |
| Sorting chunks by `_id` | Wrong byte order | Sort by `n` ascending |
| Not checking `files_id` BSON type | Query misses despite visually similar IDs | Use the exact same BSON ID type |
| Assuming every file uses 255 KiB chunks | Configuration may differ | Read `files.chunkSize` |
| Interpreting 255 KiB as 255,000 bytes | Wrong chunk counts/offsets | 261,120 bytes |
| Trusting unique index to prevent all corruption | Missing chunks/bad data still fail | Verify count/sequence/size/hash |
| Publishing `fileId` before stream completes | Business record points to incomplete upload | Publish after success |
| Deleting `fs.files` directly | Leaves orphan chunks | `GridFSBucket.delete` |
| Deleting `fs.chunks` directly | Metadata remains, file corrupted | `GridFSBucket.delete` |
| TTL on `files` only | Metadata lost, chunks remain | Cleanup worker via GridFS API |
| Deleting all orphans immediately | May delete active uploads | Grace period, active intents, audit |
| Loading entire file into RAM | OOM/GC pressure | Streaming |
| Trusting file extension for MIME | Unsafe content | Validate/scan/content policy |
| Treating metadata tenant as automatic ACL | Cross-tenant file exposure | Authorize before download |
| Relying on legacy MD5 | Does not guarantee modern integrity | App SHA-256 and security controls |
| Backing up `files`/`chunks` at different times | Orphans/missing data after restore | Consistent backup |
| Assuming GridFS auto-deduplicates | Wasted storage, duplicate uploads | Stable ID/dedupe architecture if needed |
| Pushing chunk size near 16 MiB | Exceeds BSON limit, memory pressure | Choose size with headroom |
| Dropping chunk unique index to shard | Breaks GridFS invariants | Design around shard-key constraints |

## 48. Review Questions

**1. What is GridFS used for?** — Splitting files into multiple BSON chunks to store/stream files larger than the single-document limit or serve streaming files.

**2. What are the two default collections called?** — `fs.files` and `fs.chunks`.

**3. What if the bucket is named `images`?** — `images.files` and `images.chunks`.

**4. Which field of `fs.files` stores the raw file bytes?** — No field stores the full bytes; bytes live in `fs.chunks.data`.

**5. Which field links chunks to a file?** — `fs.chunks.files_id` equals `fs.files._id`, with matching BSON type/value.

**6. Does `n` start at 1?** — No, it starts at **0**.

**7. What key pattern does the `chunks` index require?** — `{files_id:1,n:1}`.

**8. Is the chunk index unique?** — **Yes**, on the pair `(files_id,n)`.

**9. What is the standard `files` index?** — `{filename:1,uploadDate:1}`, **non-unique**.

**10. Why is `filename` not unique?** — To allow uploading multiple files/versions with the same name.

**11. Can `fs.chunks._id_` replace the chunk compound index?** — No, because it does not support filtering/sorting by `fileId` and `n`.

**12. What is the typical default chunk size?** — **255 KiB = 261,120 bytes**.

**13. How many chunks does a 700,000-byte file need with 261,120-byte chunks?** — **3**.

**14. How long is the final chunk of that file?** — **177,760 bytes**.

**15. How many chunks does an empty file have?** — **0**.

**16. Why not use a unique `{n:1}` index?** — Because every file has `n=0`, `n=1`; uniqueness must include `files_id`.

**17. Does the unique index automatically detect missing chunks?** — No; it only prevents duplicate key positions.

**18. Should you delete a file with `db.fs.files.deleteOne`?** — No; it can leave orphan chunks. Use the GridFS API.

**19. Does a TTL index on `files` delete chunks?** — Not automatically; a cleanup worker using `GridFSBucket.delete` is needed.

**20. Why is knowing `fileId` before upload finishes not enough to publish?** — Because the stream can still fail and no complete `files` document exists yet.

**21. Does MongoDB validate the actual file against `metadata.contentType`?** — No; that is application metadata.

**22. Should you upload a large file inside one giant transaction?** — No; GridFS is not a whole-file transaction mechanism, and transactions have resource/lifetime limits.

**23. When should you choose object storage over GridFS?** — When you need CDN/signed URLs/lifecycle/media scale or better cost per GB, depending on workload.

**24. What must be considered when sharding GridFS?** — The unique chunk index, shard-key constraints, routing, version rules, and consistency across both collections.

**25. How do you verify file integrity?** — Stream-download, verify byte length/chunk sequence, and check SHA-256 hash per policy.

## 49. Quick-Reference Command Table

| Goal | Command/Concept |
|---|---|
| Inspect files metadata | `db.fs.files.find()` |
| Inspect chunks of one file | `db.fs.chunks.find({files_id:fileId}).sort({n:1})` |
| Count chunks | `db.fs.chunks.countDocuments({files_id:fileId})` |
| `files` index | `db.fs.files.createIndex({filename:1,uploadDate:1})` |
| `chunks` index | `db.fs.chunks.createIndex({files_id:1,n:1},{unique:true})` |
| List indexes | `getIndexes()` |
| Measure query plan | `explain("executionStats")` |
| Node upload | `bucket.openUploadStream(filename,options)` |
| Node download | `bucket.openDownloadStream(fileId)` |
| Node delete | `bucket.delete(fileId)` |
| Java upload | `bucket.uploadFromStream(filename,input,options)` |
| Java download | `bucket.downloadToStream(fileId,output)` |
| Default chunk size | 255 KiB = 261,120 bytes |
| Chunk count | `ceil(length/chunkSize)` |
| Byte offset of chunk `n` | `n*chunkSize` |
| Integrity verification | Application-level streaming SHA-256 |
| Retention deletion | Worker finds candidates then calls `GridFSBucket.delete` |

## 50. Pre-Production Checklist for GridFS

- [ ] Does the file truly need GridFS, or does object storage / regular `BinData` fit better?
- [ ] Is the bucket prefix defined and used consistently across upload/download/delete?
- [ ] Do both `<bucket>.files` and `<bucket>.chunks` have the standard indexes?
- [ ] Is `{files_id:1,n:1}` on `chunks` **unique**?
- [ ] Is `{filename:1,uploadDate:1}` on `files` **non-unique**?
- [ ] Do all business references store the exact `fileId` (and `bucketName` if multiple buckets exist)?
- [ ] Is `length` interpreted as bytes, rather than characters or chunk count?
- [ ] Is chunk size chosen with headroom below the BSON limit and benchmarked for the workload?
- [ ] Are uploads/downloads streamed with backpressure and disconnect handling?
- [ ] Are files published only after upload succeeds and required verification passes?
- [ ] Are quotas/file size limits and rate limits enforced at the API?
- [ ] Is owner/tenant metadata populated from auth context, with authorization before download?
- [ ] Are MIME/file extensions, scanning, and safe response headers enforced?
- [ ] Is SHA-256 or an appropriate integrity policy implemented without relying on legacy MD5?
- [ ] Are duplicate filenames and revisions handled explicitly?
- [ ] Are upload retry policies and `PENDING`/`READY`/`FAILED` states implemented?
- [ ] Is there reconciliation for orphan chunks and unpublished file references?
- [ ] Have you avoided placing TTL only on `files` and leaving chunks behind?
- [ ] Are deletions performed via the `GridFSBucket` API with auditing and retries for partial failures?
- [ ] Are consistent backups taken of both collections and verified with restore tests?
- [ ] If sharded, has unique-index/shard-key compatibility been verified?
- [ ] Are ingest/download throughput, p95/p99 latency, bytes, chunks, and storage metrics tracked?
- [ ] Is there an operational plan for index creation or driver upgrade behavior changes?
- [ ] Are binary data, secrets, and unnecessary PII kept out of logs?

## 51. Conclusion

GridFS stores files in MongoDB by **separating file metadata from byte data**. `fs.files` holds the identifier, total size, chunk size, upload timestamp, filename, and metadata; `fs.chunks` holds the binary segments linked via `files_id` and ordered by `n`. Combining the two collections enables storing and streaming files beyond the **16 MiB limit of a single BSON document** without loading the entire file into RAM.

Two core indexes keep this design functioning properly: **unique `{files_id:1,n:1}`** on `chunks` to read data in order without duplicate positions, and **non-unique `{filename:1,uploadDate:1}`** on `files` to search by name and uploaded versions. They do not substitute for each other, and neither index by itself proves a file has all its chunks or intact bytes.

In real applications, use the **GridFSBucket API** for uploads, downloads, and deletions; store **`fileId`** as your reference, stream instead of buffering whole files, verify integrity when needed, handle incomplete uploads/orphan chunks, avoid misconfigured TTLs that leak storage, and protect metadata by tenant permissions. For large workloads, evaluate chunk size, index footprint, replication/sharding, backups, and object storage alternatives before finalizing your architecture.
