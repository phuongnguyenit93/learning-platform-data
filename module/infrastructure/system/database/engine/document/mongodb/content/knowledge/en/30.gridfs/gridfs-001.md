# Storing Large Files and Criteria for Choosing GridFS in MongoDB

An application can store many types of data in MongoDB: customer information, orders, warranty slips, employee profiles, transaction records, and also **attachments**. For regular business data, each object is typically a BSON document with explicit fields. However, when an application needs to store a 200 MiB video, a 40 MiB PDF, a set of high-resolution images, or a compressed archive of several GiB, placing all the bytes into a single document field hits a limit.

MongoDB enforces a **16 MiB size limit per BSON document** (16 × 1,024 × 1,024 bytes), including the document structure, field names, and the data inside. **GridFS** is MongoDB's mechanism for storing and retrieving large files by **splitting a file into multiple chunks**, storing each chunk as a separate document, while storing the file's metadata in another collection.

GridFS solves the problem of **storing files that exceed the single BSON document limit** and provides a way to **upload/download via streams** through compatible drivers or tools. However, GridFS is not necessarily the best choice for every file. In many systems, **object storage** such as S3-compatible storage, Google Cloud Storage, or Azure Blob Storage can be more suitable for files served directly to many users, via CDN, and for very large storage volumes.

This lesson belongs to the **GridFS** chapter of the **Database Engine Document MongoDB** module. Its main goal is to help you answer:

1. Why does the 16 MiB limit make some direct file-storage approaches unsuitable?
2. How does GridFS store a file across two collections, and why are there chunks?
3. When should you use GridFS, when is BSON binary sufficient, and when should you use object storage?
4. How should metadata, versioning, checksums, security, retention, and backup be designed?
5. What states can mid-flight upload failures, retries, and file deletions leave behind?
6. How do you practice uploading, reading, querying metadata, and deleting files using tools and the MongoDB Java Sync Driver?

## 1. First: Do Not Confuse a File with a Business Document

For example, an insurance contract:

```javascript
{
  _id: "contract-1001",
  customerId: "C01",
  status: "signed",
  documentName: "insurance-contract.pdf",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

The document above contains **metadata**: name, related entity, status, and timestamp. It does not store the PDF content yet.

Another simple approach is to embed binary data directly into the document:

```javascript
{
  _id: "contract-1001",
  documentName: "insurance-contract.pdf",
  mimeType: "application/pdf",
  data: BinData(0, "...base64...")
}
```

This is simply a **BSON binary schema**. For very small files, storing binary data directly can make sense if the business workflow truly wants to read the document and bytes together. However, every document must still stay within the **16 MiB limit**.

If the actual PDF is 30 MiB, you cannot fit the entire content into a single BSON document. Converting it to Base64 or placing it in a string **does not bypass the limit**; Base64 representation usually even increases the payload size before decoding.

### Three Storage Approaches to Consider

| Strategy | Where are the byte data stored? | Where is the metadata stored? | When worth considering |
| --- | --- | --- | --- |
| **Embed BSON binary** | `BinData` field of a document | Same document | Small files, low count, need to operate together with the document |
| **GridFS** | Multiple chunks in MongoDB | GridFS files collection and business metadata if needed | Large files, need streaming, want management inside MongoDB |
| **Object storage + MongoDB** | Object storage | MongoDB stores object key, version, checksum, owner | Large/many files, web/mobile/CDN, independent lifecycle and storage cost |

There is no rule that "every file smaller than 16 MiB must be embedded as BSON." A 2 MiB image served millions of times through a CDN can **very reasonably** live in object storage; whereas a small blob tightly coupled to a document can be embedded directly.

## 2. What Does the 16 MiB Limit Explain and What Does It Not?

16 MiB is the limit **of a single BSON document**, not the size limit of an entire collection, an entire database, or all data in MongoDB.

```text
Regular document:
  { _id, metadata, binary }
            |
            v
  Total BSON document <= 16 MiB

GridFS:
  Large file
    |
    +--> chunk 0  (a document)
    +--> chunk 1  (a document)
    +--> chunk 2  (a document)
    ...
    +--> file metadata (separate document)
```

Each chunk is a separate small document, so no single document has to hold the entire large file. GridFS manages this set of documents as **one logical file**.

### Why Not Manually Split a File into an Array Inside One Document?

An incorrect approach is:

```javascript
{
  _id: "file-01",
  chunks: [
    BinData(0, "..."),
    BinData(0, "..."),
    BinData(0, "...")
  ]
}
```

Splitting bytes into multiple parts **while still placing all parts inside one document** does not change the 16 MiB limit of that document.

If you manually create multiple chunk documents, you are reimplementing part of GridFS yourself: splitting chunks, reassembling the file, managing order, metadata, error checking, and streaming APIs. Unless there is a very specific requirement, you should use the **GridFS specification and drivers** instead of defining an incompatible custom mechanism.

### When Is 16 MiB Not a Strong Enough Reason?

With 1,000 files of 50 KiB each, all of them are smaller than the limit. However, if the application needs to serve them via a CDN, object-level versioning, or very long-term archival policies, storing them in MongoDB may not be the optimal choice.

GridFS is a **MongoDB-based file storage option**, not a rule that "large files must always use MongoDB."

## 3. How Does GridFS Organize Its Two Collections?

GridFS uses two related collections with the same **bucket name**:

- `<bucket>.files`: one document containing metadata for **each managed file**.
- `<bucket>.chunks`: multiple documents containing the **binary data chunks** of those files.

The default bucket is usually named `fs`, meaning:

```text
fs.files
fs.chunks
```

If an application creates a bucket named `attachments`, the two logical collections are:

```text
attachments.files
attachments.chunks
```

The bucket name is **not** an arbitrary field set after upload; tools/drivers must use the exact same bucket to see the same data.

### 3.1. Relationship Diagram Between the Two Collections

```text
                   GridFS bucket: attachments

  attachments.files
  +----------------------------------------------+
  | _id: ObjectId("...A1")                       |
  | filename: "report.pdf"                       |
  | length: 20971520                             |
  | chunkSize: 261120                            |
  | uploadDate: ...                              |
  | metadata: {tenantId, contentType, sha256}    |
  +----------------------------------------------+
                 |
                 | _id = chunks.files_id
                 v
  attachments.chunks
  +----------------------------------------------+
  | files_id: ObjectId("...A1"), n: 0, data: ... |
  | files_id: ObjectId("...A1"), n: 1, data: ... |
  | files_id: ObjectId("...A1"), n: 2, data: ... |
  | ...                                          |
  | files_id: ObjectId("...A1"), n: 80, data:... |
  +----------------------------------------------+
                 |
                 v
      Driver reads chunks in order of n
                 |
                 v
           Intact report.pdf
```

The ObjectId/metadata values in the diagram are illustrative examples only, not data created by MongoDB on a lab machine.

### 3.2. Documents in `files`

A GridFS file entry might look like:

```javascript
{
  _id: ObjectId("65f000000000000000000001"),
  length: NumberLong("20971520"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:00:00Z"),
  filename: "report.pdf",
  metadata: {
    tenantId: "tenant-01",
    ownerId: "user-123",
    contentType: "application/pdf",
    sha256: "abcdef...",
    classification: "internal"
  }
}
```

Key fields:

| Field | Meaning |
| --- | --- |
| `_id` | **GridFS file ID**, used to download/delete an exact version |
| `length` | Total file data size, measured in **bytes** |
| `chunkSize` | Maximum chunk size of the file |
| `uploadDate` | Timestamp when the upload was recorded |
| `filename` | Logical filename provided by the application |
| `metadata` | Custom attributes, such as tenant, owner, content type, checksum |

Not all files with the same filename are the same file. **GridFS allows multiple file entries with the same filename**, each with a different `_id`. When business logic needs to identify a specific version, use the **file ID** and explicit version metadata, not just the filename.

Historical fields like `md5` have appeared in older documentation/tools, but **you should not rely on the default MD5 of newer drivers** as integrity verification. If a checksum is needed, the application should use a current algorithm such as SHA-256 and verify end-to-end.

### 3.3. Documents in `chunks`

A chunk can be represented as:

```javascript
{
  _id: ObjectId("65f000000000000000001001"),
  files_id: ObjectId("65f000000000000000000001"),
  n: 0,
  data: BinData(0, "...binary bytes...")
}
```

| Field | Meaning |
| --- | --- |
| `_id` | Unique ID of the chunk document |
| `files_id` | Links to the `_id` of the file entry |
| `n` | Chunk sequence number, typically starting from **0** |
| `data` | Binary data bytes of the chunk |

The driver reassembles chunks in the order `n = 0, 1, 2, ...` to reconstruct the file. You should not manually edit `n`, change `files_id`, or modify `data` directly with manual CRUD operations: even a single missing/out-of-order chunk can cause the downloaded file to fail or become corrupted.

### 3.4. Important Indexes

The GridFS specification uses indexes such as:

- On `chunks`: a compound index **`{files_id: 1, n: 1}`** with an appropriate uniqueness requirement to identify chunk ordering within a file.
- On `files`: an index on **`{filename: 1, uploadDate: 1}`** to support finding file entries by name and timestamp.

Drivers can check/create the required GridFS indexes depending on bucket state and driver version. Do not assume indexes are intact on manually modified collections; you can inspect them with:

```javascript
db.getCollection("fs.files").getIndexes()
db.getCollection("fs.chunks").getIndexes()
```

If the bucket is named `attachments`, replace `fs` with `attachments`. Do not drop/alter system indexes just to optimize another query without understanding GridFS requirements.

## 4. Chunk Size: Why Not Split into a Few Huge Documents?

GridFS uses a default chunk size typically of **255 KiB = 255 × 1,024 = 261,120 bytes**. The last chunk may be smaller.

A 20 MiB file has:

```text
20 MiB = 20 × 1,024 × 1,024
       = 20,971,520 bytes

Default chunk size = 261,120 bytes

Number of chunks = ceil(fileLength / chunkSize)
                 = ceil(20,971,520 / 261,120)
                 = 81 chunks
```

Not every file has exactly 81 chunks; the chunk count depends on the file length and the `chunkSize` of that upload.

### Choosing a Larger or Smaller Chunk Size?

| Smaller chunks | Larger chunks |
| --- | --- |
| More chunk documents | Fewer chunk documents |
| More metadata/index entries | Reduced per-chunk overhead |
| May suit certain streaming/seek patterns | Each operation needs to process a larger chunk |
| May increase the number of retrieval operations | May increase per-chunk memory/bandwidth usage |
| Still subject to overhead limits | Each chunk must stay within the BSON document limit |

**Do not increase the chunk size to exactly 16 MiB**, because a chunk is a BSON document that also includes other fields and overhead. GridFS driver/options and server limits must be respected. The optimal size depends on file sizes, download patterns, network latency, and memory constraints; benchmark instead of always picking the largest value.

### Memory During Streaming

The advantage of a streaming API is that the application can process large files with **memory relatively bounded by buffer/chunk size**, instead of having to keep the entire file in RAM.

```text
Wrong for files of several GiB:
  read entire file -> large byte[] -> upload

Better direction:
  InputStream -> buffer/chunk -> GridFS
       (no need to materialize the entire file)
```

However, streaming does not make the network payload or total bytes written to MongoDB smaller. It mainly helps control **RAM, backpressure, and data transfer pipelines**.

## 5. Lifecycle of Uploading a GridFS File

At a conceptual level, the upload sequence is:

```text
Client opens input stream
        |
        v
GridFS upload API
        |
        +--> read bytes 0..N
        |
        +--> write chunk n=0
        +--> write chunk n=1
        +--> write chunk n=2
        +--> ...
        |
        v
Write file entry in <bucket>.files
        |
        v
Return file ID / upload result
```

By GridFS convention, the file entry metadata should only be published after chunk contents have finished writing. This helps prevent a reader from seeing a complete file entry while the file is still uploading normally.

However, this is **not** an automatic multi-document transaction across all chunks. If the process crashes after writing some chunks but before writing the file entry, the system may be left with **orphan chunks**. If an error occurs at the very end, the client may not know for sure whether the file entry was written.

### What the Driver Handles and What the Application Must Handle

The GridFS driver helps with:

- Splitting/reassembling bytes.
- Writing and reading collections according to the GridFS specification.
- Opening streams for upload/download.
- Managing file IDs and basic metadata.

The application still needs to:

- Authenticate and enforce upload size limits.
- Prevent duplicate uploads caused by retries.
- Check MIME/file signatures and scan for malware when appropriate.
- Assign owner/tenant/business object associations.
- Store access permissions and versions.
- Handle failed upload states, orphan files, or unreferenced files.
- Serve HTTP downloads, caching, or CDN integration if needed.
- Track quotas, storage, backups, and lifecycle deletions.

**GridFS is a byte-storage API**, not a complete document management system.

## 6. Lifecycle of Downloading a GridFS File

Once you have a file ID:

```text
Client sends fileId
       |
       v
Application checks permissions on metadata
       |
       v
GridFS finds file entry
       |
       v
Read chunks with matching files_id
       |
       v
Order by n and stream bytes
       |
       v
HTTP response / file output stream
```

Applications should not download a file by running `find()` on `chunks` and manually converting each `BinData` into a string. Use the **GridFSBucket download API**, because the driver handles chunk structure and data streaming according to specification.

### Downloading by Filename or File ID?

GridFS can look up files by filename, but filenames are **not unique**. For example:

```text
filename: invoice.pdf, _id: A1, uploadDate: 08:00
filename: invoice.pdf, _id: B2, uploadDate: 09:00
```

If an API only requests `invoice.pdf`, you need an explicit **revision policy**: latest version, version selected by the business document, or all versions. For business applications, it is usually better to store the **GridFS file ID** in the attachment record for exact retrieval.

### Partial File Downloads

Some GridFS drivers support operations such as seeking on a download stream. However, GridFS **does not automatically turn into an object store with an HTTP Range API/CDN**. If users play video and continuously seek to different byte ranges, the application must implement streaming/range semantics itself and test chunk-read performance.

Video playback workloads may require transcoding, adaptive bitrate, edge caching, and requirements very different from uploading/downloading a PDF file. GridFS can store the bytes, but **being able to store does not mean serving best**.

## 7. Business Dataset: Which Record Should the File ID Link To?

You should not treat the `fs.files` collection as the sole place defining all ownership and business state. A common architecture separates:

```text
business documents:
  contracts
    { _id:"contract-1001",
      customerId:"C01",
      currentAttachmentId: ObjectId("...") }

GridFS:
  attachments.files
    { _id:ObjectId("..."),
      filename:"contract.pdf",
      metadata:{tenantId:"T01", type:"contract"} }

  attachments.chunks
    { files_id:ObjectId("..."), n:0, data:... }
```

The contract document holds a **reference** to the currently active file version. If a user uploads a new PDF version, the application can:

1. Upload it as a new GridFS file ID.
2. Verify that the new file has completed and been validated.
3. Update `contracts.currentAttachmentId` to the new ID according to business rules.
4. Keep the old file for version history or queue it for deletion once unreferenced.

Do not directly overwrite the chunks of the old file to "update the PDF." GridFS is not designed as an editor capable of arbitrary in-place byte updates on a file currently in use.

### Where Should Metadata Live?

Some metadata should reside in `attachments.files.metadata`:

```javascript
{
  tenantId: "tenant-01",
  ownerId: "user-123",
  businessType: "contract",
  contentType: "application/pdf",
  sha256: "...",
  classification: "internal",
  ingestionVersion: 2
}
```

These fields help search and verify quickly by file entry. However, actual access permissions may depend on another business document—for example, if the contract changed owners or permissions were revoked. **Metadata is not authorization by itself.** The download endpoint must verify the current access context before returning bytes.

### Do Not Use Path or Filename as a Security Identifier

User-submitted filenames can collide, contain invalid characters, include path sequences like `../`, or contain untrusted content. Use a file ID (ObjectId/application ID) for management and use a sanitized display name when returning HTTP headers. Never concatenate a user's filename directly into a local filesystem path to write files.

## 8. Use Cases Where GridFS Fits Well

### 8.1. Files Exceeding 16 MiB When the Application Already Uses MongoDB

For example, a records system that must store 25–60 MiB scanned PDFs. The application already runs MongoDB, does not want to add object storage infrastructure for a moderate number of files, and requires files to be retrieved only through an authenticated backend.

GridFS is a worthy candidate because:

- It is not constrained by the 16 MiB single-BSON-document limit for the entire file.
- Drivers provide streaming APIs rather than forcing the entire file into RAM.
- File metadata can be stored/queried inside MongoDB.
- File data lives within the MongoDB deployment's backup, authentication, and replication system (subject to corresponding operational conditions).

Still, you must evaluate disk usage, replica write traffic, backup size, and download latency before deciding.

### 8.2. Internal Files Downloaded Infrequently

For example, engineering drawings, CAD files, scanned invoices, or warranty documents that are uploaded and read back in a controlled manner. GridFS can be a good fit when **read frequency is not too high**, users access files through the backend, and integration with MongoDB simplifies administration.

### 8.3. Needing to Organize Files by Metadata in MongoDB

If business workflows frequently need to find "all contract PDF documents belonging to tenant X submitted in month Y," file entry metadata helps build queries and indexes.

For example:

```javascript
db.getCollection("attachments.files").find({
  "metadata.tenantId": "tenant-01",
  "metadata.businessType": "contract",
  uploadDate: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}, {
  filename: 1,
  length: 1,
  uploadDate: 1,
  metadata: 1
})
```

The result is metadata, **not the entire byte payload**. This avoids fetching large files when only a listing is needed.

### 8.4. Needing to Manage Files Within an Existing MongoDB System

A small team may prefer fewer systems to operate. GridFS lets you share the same:

- Existing replica set/cluster mechanism.
- MongoDB driver and connection configuration.
- Database access permissions.
- MongoDB infrastructure backup, restore, and monitoring.

However, "same system" also means **large files compete for resources** with business queries; this is an isolation trade-off, not an unconditional advantage.

## 9. When Might GridFS Not Be a Good Choice?

### 9.1. Web/Media Files Serving Very High Traffic

For example, an online learning platform with multi-GiB videos, tens of thousands of concurrent viewers, needing **CDN**, range requests, adaptive bitrate, and edge caching. Storing and serving bytes directly from the database can place unnecessary I/O and network load on MongoDB.

An architecture commonly considered:

```text
Uploader
   |
   v
Object storage (raw/video segments)
   |
   +----> CDN ----> Browser/mobile
   |
   v
MongoDB:
  videoId, objectKey, versions, owner, status, metadata
```

MongoDB still plays an important role for metadata, authorization, and business workflows; **it does not necessarily have to hold the bytes**.

### 9.2. Very Small Files That Need to Travel with a Document

If a file is a few KiB—for example, a small certificate or an internal thumbnail—and the application requires reading it together with the document, storing it in a BSON binary field can be simpler than two GridFS collections. Still, you must consider how often the whole document is returned and its impact on the working set.

Do not embed thousands of images inside one large document just because each image is small. The **total document** still cannot exceed 16 MiB, and document updates/retrievals can become expensive.

### 9.3. Needing POSIX Filesystem Semantics

GridFS is **not a standard POSIX filesystem** that can be mounted and used like a normal directory with full OS locks, rename, append, in-place random writes, and OS permission rules. It is a protocol for storing and reading files through MongoDB drivers.

If a third-party application requires a real file path to open/seek/lock/write-in-place, you need an appropriate filesystem/object storage bridge. Do not treat `GridFSBucket` as an on-disk directory.

### 9.4. Needing Frequent Mid-File Byte Updates

For example, a 5 GiB database file modified in small blocks every second. GridFS is designed for **uploading/downloading file content**; modifying content should normally create a **new file version** or live in a system that supports block-level editing. Updating chunks directly can break integrity and synchronization with file metadata.

### 9.5. Large Storage Costs and Complex Lifecycle Policies

A multi-terabyte backup repository with cold archival policies, versioning, object lock, tiering, and cross-region replication may be supported more naturally by object storage. Putting all bytes into MongoDB can make replica copies, backups, indexes, and operational costs substantial.

GridFS does not natively provide object lifecycle/tiered cold storage like full object storage services; you must calculate the **total system cost**, not just the raw source file size.

## 10. Comparing GridFS and Object Storage Objectively

| Criterion | GridFS in MongoDB | Object storage + MongoDB metadata |
| --- | --- | --- |
| Files larger than 16 MiB | **Yes**, via chunks | **Yes**, via object API |
| Streaming upload/download | Yes via driver/API | Yes via SDK/HTTP API |
| Metadata/queries in MongoDB | File metadata stored directly in MongoDB | MongoDB stores metadata and object key |
| CDN/public distribution | Requires separate application/caching layer | Often has smoother CDN integration |
| HTTP Range/video streaming | Can be built via download stream/seek, requires implementation | Object APIs usually support ranged GET well |
| Infrastructure administration | Tied to existing MongoDB | Adds service/storage credentials and integration |
| Backup/restore | File data contributes to MongoDB backup size | DB backup and object backup policies must be coordinated |
| Replica copy cost | Bytes are replicated per MongoDB configuration | Replication/durability managed by object storage |
| Data locality with metadata | Same DB deployment | Metadata and bytes in two systems |
| Version changes | Upload new file; manage pointer | Object versioning or new key + pointer |
| Deletion/retention | Application handles lifecycle and GridFS delete | Object lifecycle rules can help |
| Very large file read concurrency | May compete for MongoDB resources | Blob/CDN services are typically optimized for this traffic |
| Atomic transaction between metadata and bytes | **Not guaranteed automatically** across multiple GridFS documents | Also no shared transaction with MongoDB by default |

**Deciding factor:** does the application need a file store integrated with the database, or does it need a large-scale object distribution/archival platform? Development and operational costs on both sides must be accounted for, not just lines of upload code.

### Object Storage Does Not Automatically Solve Cross-System Transactions

Storing a file in object storage and then updating a MongoDB reference creates a two-step workflow:

```text
Upload object -> write objectKey to MongoDB
```

If the second step fails, the object can become **orphaned**. If the DB reference is written before upload, the record can point to a nonexistent object. Therefore, both the GridFS model **and** the object storage model require lifecycle management, retries, and cleanup; the difference lies in where the bytes live and which protocols need coordination.

## 11. Selection Criteria: A Decision Model

Answer these questions before choosing:

1. **Single file size:** smaller than 16 MiB or potentially hundreds of MiB/GiB?
2. **File count:** a few thousand, millions, or more?
3. **Total capacity:** a few GiB or many terabytes?
4. **Read/write ratio:** infrequent uploads, frequent downloads; or write-heavy?
5. **Delivery path:** via private backend, HTTP Range, CDN, mobile, media streaming?
6. **File size and access pattern:** full-file download or many byte ranges/seeks?
7. **Metadata needs:** filtering by tenant, owner, document type, version, timestamp?
8. **Security:** internal documents, PII, need signed URLs, malware scanning, encryption?
9. **Retention:** delete after 30 days, retain permanently, cold archive, legal hold?
10. **Durability/recovery:** need point-in-time backup, cross-region, checksum verification?
11. **Current MongoDB load:** is the database running latency-sensitive OLTP workloads?
12. **Operational capability:** is the team already using object storage or trying to avoid adding another system?

### A Pragmatic Decision Tree

```text
Need to store bytes inside MongoDB?
        |
   +----+----+
   |         |
  No       Yes / worth evaluating
   |         |
   v         v
 Object    Can files exceed 16 MiB?
 storage      |
           +--+--+
           |     |
          No    Yes
           |     |
           v     v
     Consider   GridFS is a candidate
     BSON        |
     binary      v
     or blob   Need heavy CDN/range/tiered archive?
                     |
                +----+----+
                |         |
               Yes        No
                |         |
                v         v
           Consider    Benchmark GridFS
           object      with real workload
           storage     and real cost
```

The decision tree only helps frame the questions. You may use object storage even for small files, or use GridFS for moderately sized files if metadata organization and operations genuinely fit.

## 12. Illustrating Three Concrete Business Cases

### Case A — Internal Case-File PDFs

Requirements:

- Each PDF is 5–100 MiB.
- Average of tens to hundreds of uploads per day.
- Only authorized users can download via the backend.
- Search by case ID, owner, and upload date.
- No CDN requirement.

GridFS is **worth trying**: it uses streaming, MongoDB metadata, and backend authorization. You need to inspect backup pressure, download speed, chunk counts, and failure cleanup.

### Case B — Lesson Videos

Requirements:

- Videos from 100 MiB to several GiB.
- Thousands of concurrent viewers.
- Viewers can seek, select bitrates, and stream from multiple regions.
- CDN and edge caching are critical requirements.

Object storage + CDN is usually the **stronger candidate**. MongoDB stores the video record, metadata, owner, permissions, file versions, and processing state. GridFS can technically store the bytes, but it can put unnecessary content-delivery load on MongoDB.

### Case C — 30 KiB Thumbnail in a Record

Requirements:

- Small thumbnail image.
- Always read alongside the profile document.
- No large public traffic.
- Only one image per record, no multiple versions.

A BSON binary field can be simpler than GridFS. However, if profile lists are queried very frequently without needing the image bytes, embedding thumbnails directly can increase payload/cache footprint. In that case, separating the file into GridFS/object storage or a dedicated collection may fit better.

## 13. Practicing with `mongofiles`

**`mongofiles`** is a command-line utility in the **MongoDB Database Tools** suite dedicated to working with GridFS. It is not a built-in helper in every `mongosh` installation; you must install Database Tools properly and configure the appropriate connection.

Illustrative example for a **local MongoDB lab**:

```bash
# Upload demo.pdf into the default fs bucket
mongofiles --uri="mongodb://127.0.0.1:27017" --db=gridfs_lab put demo.pdf

# List files in the fs bucket
mongofiles --uri="mongodb://127.0.0.1:27017" --db=gridfs_lab list

# Download a file with the same name from the bucket (mind where you run the command)
mongofiles --uri="mongodb://127.0.0.1:27017" --db=gridfs_lab get demo.pdf
```

Commands depend on the `mongofiles` version and server permissions; if `demo.pdf` does not exist in the working directory, `put` will fail. For clusters with authentication, use a URI and secure credential storage rather than putting passwords into shell history.

**Be careful with name collisions and local paths when downloading.** Do not accidentally overwrite a file in use in production; use a lab directory and check tool output. In real applications, downloading by **GridFS file ID** via a driver is usually clearer than relying on filename.

### A Note on Bucket Names

The three `mongofiles` examples above use the default `fs` bucket. If the Java code in later sections creates a bucket named `attachments`, those files reside in **`attachments.files` and `attachments.chunks`**, and will not appear in `fs.files` unless the tool is configured with the matching prefix/bucket.

## 14. Inspecting File Metadata with `mongosh`

After `mongofiles put demo.pdf` succeeds, open the database:

```javascript
use gridfs_lab

db.getCollection("fs.files").find(
  {},
  {
    filename: 1,
    length: 1,
    chunkSize: 1,
    uploadDate: 1,
    metadata: 1
  }
).sort({ uploadDate: -1 })
```

Select one file entry:

```javascript
const file = db.getCollection("fs.files").findOne({
  filename: "demo.pdf"
});

if (file) {
  printjson({
    id: file._id,
    filename: file.filename,
    length: file.length,
    chunkSize: file.chunkSize,
    estimatedChunkCount: Math.ceil(
      Number(file.length) / file.chunkSize
    )
  });
}
```

**Only for inspecting metadata**—do not load bytes with this query.

Count chunks:

```javascript
if (file) {
  const count = db.getCollection("fs.chunks").countDocuments({
    files_id: file._id
  });
  print("chunk count =", count);
}
```

In a complete, uncorrupted file, the chunk count normally matches the calculation based on `length` and `chunkSize`, while an empty file may have **0 chunks**. If they do not match, investigate incomplete uploads/corruption and index health, but **do not manually edit chunks** based solely on a count check.

### Do Not Read All Chunk Bytes When You Only Need Metadata

```javascript
// Avoid doing this on very large files if you only want a listing:
db.getCollection("fs.chunks").find({ files_id: file._id })
```

The command above can return many large `BinData` payloads to the client. When you need to inspect structure:

```javascript
db.getCollection("fs.chunks").find(
  { files_id: file._id },
  { _id: 0, files_id: 1, n: 1 }
).sort({ n: 1 }).limit(5)
```

When you need to download bytes, use the GridFS API or `mongofiles get` instead of manually concatenating binary values.

## 15. Uploading with the MongoDB Java Sync Driver

The MongoDB Java Sync Driver provides common APIs:

- `GridFSBuckets.create(database, bucketName)` to obtain a `GridFSBucket`.
- `uploadFromStream()` to upload from an `InputStream`.
- `downloadToStream()` to download into an `OutputStream`.
- `find()` to query file entries.
- `delete()` to delete a file ID along with its associated chunks via the GridFS mechanism.
- `GridFSUploadOptions` to set chunk size and metadata.

Example using a compatible MongoDB Java Sync Driver and Java 17+ to read a file from a lab disk and create a GridFS entry. The environment variable `MONGODB_URI` holds the appropriate URI; do not hard-code credentials.

### 15.1. Streaming PDF Upload

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class UploadGridFsFile {
    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        Path source = Path.of("demo.pdf");
        if (!Files.isRegularFile(source)) {
            throw new IllegalArgumentException(
                "demo.pdf file not found in lab directory"
            );
        }

        // Example: enforce an application-specific upload limit.
        long maxBytes = 200L * 1024 * 1024;
        if (Files.size(source) > maxBytes) {
            throw new IllegalArgumentException(
                "File exceeds the 200 MiB application limit"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client
                .getDatabase("gridfs_lab")
                .withWriteConcern(WriteConcern.MAJORITY);

            GridFSBucket bucket =
                GridFSBuckets.create(db, "attachments");

            Document metadata = new Document(
                "tenantId", "tenant-01")
                .append("ownerId", "user-123")
                .append("businessType", "contract")
                .append("contentType", "application/pdf")
                .append("status", "uploaded");

            GridFSUploadOptions options =
                new GridFSUploadOptions()
                    .chunkSizeBytes(255 * 1024)
                    .metadata(metadata);

            try (InputStream input =
                     Files.newInputStream(source)) {
                ObjectId fileId = bucket.uploadFromStream(
                    "demo.pdf", input, options);

                System.out.println(
                    "GridFS file ID: " + fileId.toHexString()
                );
            }
        }
    }
}
```

This code:

1. Validates the local file and upload size against application policy.
2. Creates a bucket named `attachments`.
3. Configures metadata and chunk size.
4. Streams bytes through the driver.
5. Receives the file ID once the upload completes via the API.

**There is no `Files.readAllBytes(source)` call**, so the application does not need to hold the entire PDF in a `byte[]`. Memory is still used for buffers and driver operations, but it does not scale linearly with the full file size the way reading all bytes into RAM does.

### Why Use `withWriteConcern(WriteConcern.MAJORITY)`?

For instance, to ensure GridFS writes are acknowledged by the server with an appropriate write concern on the database handle, reducing the risk that acknowledged writes are rolled back during normal failover.

However, **majority write concern does not turn all chunk writes into a single transaction**. If an upload fails partway through, you still need failure handling, retry/idempotency, and cleanup. Upload latency may increase when stronger replication acknowledgment is required.

### What If Input Comes from HTTP?

In a web service, the byte source may be an upload request `InputStream` rather than a file on disk. You must still enforce:

- Per-user/tenant quotas.
- Actual bytes read, not just the client-declared HTTP `Content-Length`.
- Timeouts and minimum read rates to prevent hanging connections.
- Concurrent upload limits.
- File type validation and malware scanning.
- Web framework request/multipart limits.
- Handling clients closing the connection mid-transfer.

`GridFSBucket` does not automatically handle these HTTP/security concerns.

## 16. Downloading with the Java Sync Driver

Assuming the application has stored the GridFS file ID in the contract document, you can download accurately by ID:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import org.bson.types.ObjectId;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class DownloadGridFsFile {
    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");
        String rawFileId = System.getenv("GRIDFS_FILE_ID");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }
        if (rawFileId == null || !ObjectId.isValid(rawFileId)) {
            throw new IllegalArgumentException(
                "Missing or invalid GRIDFS_FILE_ID");
        }

        ObjectId fileId = new ObjectId(rawFileId);
        Path destination = Path.of("downloaded-demo.pdf");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("gridfs_lab");
            GridFSBucket bucket =
                GridFSBuckets.create(db, "attachments");

            try (OutputStream output = Files.newOutputStream(
                    destination,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                bucket.downloadToStream(fileId, output);
            }
        }

        System.out.println(
            "Downloaded to " + destination.toAbsolutePath());
    }
}
```

The example uses `CREATE_NEW` to **avoid accidentally overwriting an existing lab file**. If a download throws an error mid-stream, the output file may contain only **partial bytes**. Real applications should download to a **temporary path**, verify length/checksum, and then safely rename/move or delete the temporary file on failure.

### Verifying Permissions Before Downloading

In a multi-tenant backend, you should never simply accept a `fileId` from a URL and return the file. The application must check whether the user has permission to access the file and its corresponding business record.

```text
GET /attachments/{fileId}
       |
       v
Authenticate user
       |
       v
Load business record and GridFS metadata
       |
       v
Authorize tenant / owner / ACL
       |
       v
Stream download
```

A client possessing a valid ObjectId **does not imply** the client is authorized to download that ID's content.

## 17. Listing Files, Retrieving Metadata, and Deleting with Java

A backend often needs to list files for a tenant **without downloading their content**.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

public class ListGridFsFiles {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("gridfs_lab");
            GridFSBucket bucket =
                GridFSBuckets.create(db, "attachments");

            for (GridFSFile file : bucket.find(
                    Filters.eq("metadata.tenantId", "tenant-01"))
                    .sort(Sorts.descending("uploadDate"))
                    .limit(20)) {
                System.out.println(
                    file.getId()
                        + " | " + file.getFilename()
                        + " | " + file.getLength()
                        + " bytes"
                );
            }
        }
    }
}
```

Here `find()` returns only **file metadata**, without downloading individual chunks. If queries filtering by `metadata.tenantId` and `uploadDate` run frequently on a large bucket, you can evaluate an appropriate index on `attachments.files`; avoid adding redundant or low-selectivity indexes.

### Deleting a File by ID

When the business workflow permits deletion, Java's `GridFSBucket` supports:

```java
// Execute only after verifying authorization and
// confirming the file is no longer referenced by any business record.
bucket.delete(fileId);
```

Do not run commands like:

```javascript
// DO NOT MANUALLY DELETE PARTIAL PIECES:
db.getCollection("attachments.chunks").deleteMany({
  files_id: someFileId
});
```

if the goal is to delete a valid file, because direct manipulation can wipe the content while leaving the file entry behind, creating corrupted data. Use the GridFS API and lifecycle policies.

A single `delete()` call can also fail partway through its steps. Applications must understand that **deleting a GridFS file can involve multiple documents** and must have a process to detect leftover files/chunks.

## 18. Verifying Integrity with Checksums

Suppose you upload a 40 MiB file and store `length` in the file entry. Having the right size is **not enough** to prove every byte matches the source: two files can have the same length yet different contents.

A practical approach is to compute **SHA-256** at the application layer:

1. Compute the hash of the source file via streaming.
2. Upload the content and store the hash in metadata or the business record.
3. On download, recompute SHA-256 over the received bytes.
4. Compare the hash and length before marking the file as verified.

### Computing SHA-256 in Java Without Reading the Entire File into RAM

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public class FileHash {
    public static String sha256(Path path) throws Exception {
        MessageDigest digest =
            MessageDigest.getInstance("SHA-256");

        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[64 * 1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
```

This method uses Java 17+ for `HexFormat`. It does not hold large files in memory.

**A note on consistency:** if the application computes the hash first and then the source file **is modified** before/during upload, the metadata hash may not match the uploaded bytes. Use an immutable source/staging file or compute the hash on the exact byte stream being uploaded and update metadata after completion via a controlled workflow.

### Checksums Do Not Replace Authentication

A hash detects content that differs from the stored hash, but if an attacker has permission to alter **both the file and the metadata hash**, simple hash comparison does not protect authenticity. For strong tamper-resistance requirements, you need digital signatures, access controls, auditing, and proper key management.

## 19. Duplicate Filenames, File Versions, and Idempotent Uploads

Suppose a user uploads `contract.pdf`, and the request times out right after the server finishes writing. The user clicks Upload again.

```text
Upload request #1
    |
    +--> chunks written
    +--> files entry written
    |
    X  Response lost
    |
Upload request #2
    |
    +--> a new file ID
    +--> more new chunks
```

The result can be **two GridFS files with the same filename** and identical content. A client-side error from the driver does not always prove that the previous upload definitely failed to complete.

### Do Not Use Filename as an Idempotency Key

Two different people can upload two different files both named `contract.pdf`. Conversely, the same user may intentionally upload v2 using the same name. Therefore, filename does not represent a single logical upload.

The design can use:

- **`uploadRequestId`** issued by the backend, unique within the tenant/business operation scope.
- **Content hash** to assist with duplicate-content detection, with an explicit policy on whether deduplication is allowed.
- **Version** of the business attachment.
- An **attachment record** with a unique index on the business key.
- States such as `PENDING`, `UPLOADED`, `SCANNED`, `ACTIVE`, `FAILED`.

Example of a business record:

```javascript
{
  _id: "attach-1001",
  tenantId: "tenant-01",
  contractId: "contract-1001",
  uploadRequestId: "req-8f2d",
  fileId: ObjectId("65f000000000000000000001"),
  filename: "contract.pdf",
  sha256: "...",
  version: 2,
  state: "ACTIVE",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

If the client retries with the same `uploadRequestId`, the application can return the already-recorded result instead of creating a new file. This mechanism must be protected with appropriate unique constraints/conditional updates and concurrency handling; **merely checking beforehand with `findOne()` and then inserting does not protect against race conditions**.

### Replacing a File While Keeping Old Versions

```text
contract-1001.currentAttachmentId ---> file A (v1)

Upload file B (v2)
        |
        v
Validate & scan succeeded
        |
        v
Update contract pointer -> file B
        |
        v
file A: kept in history or queued for cleanup
```

Do not delete file A **before** the pointer to B is safely updated if the business requires a downloadable file to always be available. When changing pointers and deleting files across multiple collections, you need a consistency/reconciliation policy rather than assuming GridFS provides a single transaction across all steps.

## 20. Mid-Upload Failures and Orphan Chunks

One of the most important operational issues is an incomplete upload:

```text
100 MiB File
    |
    +-- chunk 0   [written]
    +-- chunk 1   [written]
    +-- chunk 2   [written]
    +-- ...
    +-- chunk 100 [written]
    |
    X  Network drop / process crash
    |
    ?  No file entry in attachments.files yet
```

Chunks that were written but **have no corresponding entry in `files`** are called **orphan chunks**. Depending on failure timing and driver behavior, leftover data may accumulate and require garbage collection.

### Why Not Delete Orphan Chunks Immediately Upon Seeing Them?

A file **currently undergoing a valid upload** will also have written chunks whose file entry has not yet been published. If a cleanup job runs while an upload is active, it could delete chunks that are still needed, corrupting the upload.

Therefore, a cleanup workflow needs to:

1. Determine whether an upload is active or its lease has expired.
2. Enforce a **grace period** sufficiently longer than the maximum upload duration.
3. Distinguish existing file entries from unreferenced chunks.
4. Confirm no writer is still using the corresponding file ID.
5. Run in batches and log what gets deleted.
6. Provide dry-run mode, alerts, and a recovery plan for production.

Do not run an ad-hoc `deleteMany()` scanning `fs.chunks` in production without understanding the state of active uploads.

### Deleting Unreferenced Files

Another type of orphan is a **complete file entry with all its chunks**, where no business document still references its file ID. This is an **orphan file**, distinct from an orphan chunk.

For example:

```text
attachments.files:
  A1, A2, A3

contracts.currentAttachmentId:
  A1, A3

A2 is no longer referenced by any current contract
```

However, A2 might still need to be retained as a historical version, under legal hold, or for another business workflow. Cleanup must therefore be driven by **lifecycle policy**, not just a simple join against a single collection.

## 21. GridFS and Multi-Document Transactions

Each GridFS file typically spans **multiple documents** across two collections. **GridFS does not support multi-document transactions for GridFS upload/download operations themselves according to MongoDB's documented rules**, so you should not promise that an entire upload can be wrapped atomically in a shared transaction like updating two business documents.

Even when the application uses MongoDB transactions for other records, you must still design intermediate states for GridFS:

```text
ATTACHMENT_CREATED
        |
        v
UPLOADING
        |
        v
GRIDFS_UPLOAD_COMPLETE
        |
        v
CHECKSUM/SCAN_COMPLETE
        |
        v
BUSINESS_RECORD_ACTIVE
```

If a failure occurs at any step, you need to determine:

- Does the file completely exist in GridFS yet?
- Does the business pointer already point to the file?
- Are valid scan results and checksums present yet?
- Which step should a retry resume from, or should it create a new upload request?
- How will leftover bytes be cleaned up after a waiting period?

### Distinguishing Business-Pointer Atomicity from File-Upload Atomicity

A command like:

```javascript
db.contracts.updateOne(
  { _id: "contract-1001", version: 1 },
  {
    $set: { currentAttachmentId: someNewFileId },
    $inc: { version: 1 }
  }
)
```

is an atomic **single-document update** on the contract document. However, it **does not turn the preceding chunk writes into part of a transaction with that update**. This is a boundary you must understand when building reliable file management systems.

## 22. Durability and Write Concern for Large Files

GridFS stores chunks and metadata in MongoDB, so it remains subject to **write concern** and replication rules:

- `w:1`: primary acknowledgment per configuration.
- `w:"majority"`: requires appropriate majority acknowledgment from the replica set.
- `j:true`: requires journal durability when appropriate.
- `wtimeout`: limits how long to wait for acknowledgment; a timeout does not automatically mean the operation rolled back.

For files with many chunks, the write concern level impacts total latency and throughput. If an upload has not received sufficient ACKs or the connection drops mid-way, the client must not assume all chunks exist.

**Key takeaway:** writing files through MongoDB does not automatically make them safer than object storage in all situations. Actual durability also depends on:

- Replica set topology and placement across failure domains.
- Backup/restore and snapshot consistency.
- Disk I/O, corruption, and checksums.
- File update/deletion policies.
- Recovery capability after upload/delete failures.

For critical attachments, verify the full pipeline from **upload bytes → metadata → business reference → restore test**, not just seeing `insert completed`.

## 23. Backup and Restore: Always Remember There Are Two Collections

A complete GridFS file requires **both the file entry and the chunks**. If backup/restore includes `attachments.files` while omitting `attachments.chunks`, the application may see metadata yet fail to download any content.

```text
GridFS Backup:
  attachments.files   +
  attachments.chunks  +
  business references +
  metadata/indexes
            |
            v
      Usable restore
```

### Point-in-Time Backup Consistency

If the file entry is backed up at time T1 while chunks are backed up at an inconsistent time T2, data may be missing, orphaned, or mismatched with business references. For continuously active systems, use MongoDB-supported snapshot/backup methods and a consistency plan across related collections.

### Test Restores, Not Just Backups

A good restore test includes:

1. Restoring GridFS collections and business records into an isolated environment.
2. Selecting several file IDs of varying sizes and versions.
3. Downloading bytes using the driver.
4. Comparing length and SHA-256 against trusted source metadata.
5. Verifying file permissions and tenant associations.
6. Comparing results when restoring to a different cluster/topology.

Successful backup reports alone do not prove every file can be read after an incident. A **restore test** is stronger operational evidence.

## 24. Metadata Indexes and Collection Scale

GridFS creates many chunks per file. If a system has **one million files**, the number of chunk documents can be many millions more depending on average file size.

Suppose each file averages 100 chunks:

```text
1,000,000 file entries
        × 100 chunks/file
        = 100,000,000 chunk documents
```

Chunks also incur index entries, BSON overhead, replication, and backup bytes. Therefore, GridFS sizing decisions must forecast **chunk count**, not just file count.

### Indexing Metadata Queries

If an API lists a tenant's files by timestamp:

```javascript
db.getCollection("attachments.files").createIndex(
  {
    "metadata.tenantId": 1,
    uploadDate: -1
  },
  { name: "idx_tenant_upload_date" }
)
```

This index supports a common metadata query, though it still carries write/index storage overhead. Do not create separate indexes for every metadata field unless an actual query needs them.

### Do Not Index the Chunk `data` Payload

`data` holds binary bytes. An index on `data` does not help search by filename, owner, or content type in the usual way, and can incur massive overhead. Index **queryable metadata**, not the entire binary payload.

### Is Searching by Filename Safe?

`filename` is useful when users want to browse a list, but it should not serve as a business primary key. The same name can have multiple versions, Unicode characters, and differing normalization rules. File ID remains the more stable technical identifier for downloads and deletions.

## 25. Security and Upload Safety

An attachment may contain sensitive data or malware. Even when stored inside MongoDB, the application must protect both metadata and bytes.

### 25.1. Authorization by Tenant and Business Record

Suppose a user in tenant A guesses an ObjectId belonging to tenant B. If the download endpoint serves a file by ID without checking permissions, that is a critical vulnerability.

The flow should include:

1. Authenticate the request.
2. Load the business record/attachment record belonging to the tenant the user is permitted to access.
3. Check role, owner, state, and policy.
4. Resolve the GridFS file ID tied to that exact record.
5. Stream bytes only after authorization succeeds.
6. Audit sensitive downloads.

Never trust `metadata.tenantId` supplied directly by the client in an upload request; the backend must obtain the tenant from the **trusted authentication context**.

### 25.2. MIME Type Is Not Proof of a Safe File

A client can send:

```text
filename = invoice.pdf
Content-Type = application/pdf
```

while the actual bytes are not a PDF. You should inspect file signatures/magic bytes and apply malware scanning/quarantine where appropriate. Do not rely on the `.pdf` extension or the `Content-Type` header as proof.

### 25.3. Encryption and Database Access Controls

Use TLS for connections, least-privilege database permissions, secret management, and storage encryption as required. If **application-level encryption** is needed, define where stream encryption/decryption happens, key management, and the impact on checksums and range requests.

### 25.4. Safe HTTP Responses

When serving files, configure appropriate headers:

- Verified or policy-approved `Content-Type`.
- Safe `Content-Disposition`, properly handling Unicode names and special characters.
- `X-Content-Type-Options: nosniff` where appropriate.
- `Cache-Control` aligned with data sensitivity.
- Download concurrency limits and rate/byte quotas.

Do not render user-uploaded HTML/SVG directly on the same origin without addressing script/content injection risks.

## 26. Performance: Factors Affecting Upload/Download

GridFS is not automatically faster than every file system. A 500 MiB file can produce thousands of chunks, requiring many read/write operations, index accesses, network round-trips, and replication work.

### Upload Throughput Depends On:

- Chunk size and chunk count.
- Network latency between the app and MongoDB.
- Write concern, journaling, and replica lag.
- Disk throughput and write amplification.
- Concurrent uploads.
- Driver connection pool and read buffers.
- Sharding configuration, shard load, and indexes.

### Download Throughput Depends On:

- Server and client locality.
- Cache hit rate and read I/O.
- Chunk count/round-trips depending on driver implementation.
- HTTP streaming handling in the application.
- Network bandwidth and user-side limits.
- Checksum verification, decryption, compression, and malware scanning if performed at download time.

### Impact on OLTP Workloads

Suppose the same replica set is serving low-latency order queries, and a backup job begins uploading 200 files × 1 GiB:

```text
GridFS uploads
  -> disk writes
  -> oplog / replication traffic
  -> cache / I/O pressure
  -> can degrade p95 business query latency
```

Isolating workloads onto a separate storage tier/cluster or choosing object storage can be a sound architectural decision. Do not look only at upload throughput during benchmarks; measure the **p95/p99 of concurrent business APIs**.

## 27. Benchmarking GridFS Against Object Storage

Set up a representative workload:

| File type | Size | Frequency | Access path |
| --- | ---: | --- | --- |
| Thumbnail image | 30 KiB | Very high | Web/mobile, cache/CDN |
| Contract PDF | 20–80 MiB | Moderate | Authenticated backend |
| Report export ZIP | 100–500 MiB | Low | On-demand download |
| Lesson video | 200 MiB–2 GiB | High reads | Range/CDN |
| Log archive | 1–10 GiB | Rare reads | Long-term storage |

Measure:

1. Upload p50/p95/p99 and throughput in MiB/s.
2. Download p50/p95/p99, time-to-first-byte, and throughput.
3. Actual bytes transferred, retry traffic, and client timeout count.
4. RAM/CPU of the upload/download service.
5. MongoDB I/O, cache, replication lag, and query latency.
6. Total **files + chunks + indexes** storage size, including replica copies/backups.
7. Storage, network egress, and maintenance costs.
8. HTTP Range capability, CDN hit ratio, and multi-region latency.
9. Metadata search, versioning, and deletion policy capabilities.
10. Backup/restore and post-failure cleanup complexity.

**Do not compare a single file download from localhost GridFS against object storage in a distant network region and declare one absolutely faster.** Benchmarks require representative environments, topologies, and concurrency.

### Formula for Forecasting Chunk Counts

With `N` files of size `L_i` bytes and chunk size `C_i`:

```text
chunks_for_file_i = ceil(L_i / C_i)
total_chunks ≈ sum(chunks_for_file_i)
```

This estimates chunk document counts for complete files; it excludes orphan chunks, indexes, compression, replicas, oplog, and backups. For empty files, there are typically no data chunks, only the file metadata entry.

## 28. Sharding GridFS: Scalable, Yet Not Automatic

A GridFS bucket is stored in MongoDB collections, so at large scale you may need to evaluate **sharding** or workload partitioning. However, you should not assume that "a file is split into chunks" means "chunks are evenly distributed across multiple shards."

Two distinct concepts:

- **GridFS chunk**: a binary piece of a file.
- **Sharded cluster shard-key range/chunk**: MongoDB's unit of data distribution across shards.

If GridFS collections need sharding:

1. Check **sharding eligibility, shard key, and index restrictions** for the MongoDB version in use.
2. Preserve compatibility with GridFS's `files_id + n` index and query path.
3. Consider whether a single large file creates a hotspot on one shard.
4. Measure scatter-gather/routing impact when querying metadata or fetching individual chunks.
5. Evaluate balancer, shard migration, backup, and restore costs.
6. Do not manually alter collection layout/chunk data bypassing the GridFS driver.

A deployment with many shards where all file downloads concentrate on one resource group can still hit bottlenecks. If the workload mainly serves bytes to public users, object storage/CDN may fit better than scaling a sharded cluster solely to serve media.

## 29. GridFS and Retention / Data Deletion Policies

Suppose regulations require deleting contract files after seven years, except copies held under legal hold. You can store:

```javascript
{
  _id: "attach-1001",
  fileId: ObjectId("65f000000000000000000001"),
  uploadedAt: ISODate("2026-11-14T08:00:00Z"),
  retentionUntil: ISODate("2033-11-14T00:00:00Z"),
  legalHold: false,
  status: "ACTIVE"
}
```

A lifecycle job:

1. Finds attachment records that have expired and have no legal hold.
2. Verifies there are no business references requiring retention.
3. Marks `DELETING` or an equivalent status to prevent races.
4. Calls controlled GridFS deletion by ID.
5. Records the deletion and reconciles files/chunks.
6. Updates business status and retains audit metadata if policy permits.

**Do not create a TTL index on `attachments.files.uploadDate` and assume MongoDB auto-deleting the file entry will delete all associated chunks.** TTL directly on file metadata can delete the entry without going through the GridFS delete workflow, leaving orphaned data in `chunks`. GridFS retention must be enforced through a **proper file-deletion workflow**, not just metadata deletion.

If legal compliance requires hard deletion, you must also consider backup retention, replica copies, caches, object versions, and proof of deletion. GridFS does not automatically handle every compliance requirement.

## 30. When Should Files Be Kept Immutable?

A useful practice is to treat **each GridFS file ID as an immutable content version**:

```text
File A -> sha256 A -> attachment version 1
File B -> sha256 B -> attachment version 2

Business record -> current version = B
```

Benefits:

- Clear checksums/versions.
- In-flight downloads cannot have their bytes altered mid-transfer.
- Easy to audit which file was signed/approved.
- Business pointers can roll back to an older version if policy allows.
- Cleanup based on reference counts/retention is clearer.

The trade-off is that storing multiple versions consumes storage space. Therefore, you need a version retention policy and controlled deduplication; do not share a single file across tenants if deletion rights and data isolation do not permit it.

## 31. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Inserting a 30 MiB `BinData` file fails | BSON document exceeds 16 MiB | Use GridFS or object storage |
| Created `attachments` bucket but `fs.files` is empty | Checking the wrong bucket | Inspect `attachments.files`/`attachments.chunks` |
| Two `contract.pdf` entries appear | Filenames are not unique; re-upload/versions | Store file ID, operation ID, and revision |
| Upload hangs then times out | Network/I/O/write concern/overloaded backend | Determine state, idempotent retry, cleanup |
| Chunks exist without a `files` entry | Upload aborted mid-way | Detect orphans, grace period, controlled cleanup |
| `files` entry exists but download misses bytes | Missing/corrupted chunk or inconsistent restore | Check data/indexes/backups, verify checksum |
| Downloading whole file into a byte array causes OOM | Not using streaming | Use `InputStream`/`OutputStream` and buffers |
| User downloads another tenant's file | Relying solely on file ID | AuthN/AuthZ on business record and tenant |
| `.pdf` file is not actually a PDF | Trusting client MIME/extension | Check file signature, malware scanning |
| Manually deleted file entry, chunks remain | Bypassed GridFS delete | Use `bucket.delete` and lifecycle jobs |
| TTL on `fs.files` leaves leftover data | TTL deletes only the file entry | Design retention around GridFS delete |
| Video playback is slow despite GridFS storing it | Missing CDN/range/streaming architecture | Compare with object storage/CDN |
| Metadata queries are slow | Missing index for metadata filters | Create appropriate indexes on `files` |
| Order API DB slows down during heavy uploads | GridFS competes for I/O/replication | Isolate workload/scale/choose different storage |
| File ID returned but business pointer not written | Two steps are not jointly atomic | Retry/state machine, reconciliation |
| Replacing file by editing chunks directly | Violates GridFS structure | Upload a new version |
| Backup restores metadata but files won't open | Missing chunks or inconsistent snapshot timing | Back up both collections, run restore tests |
| Stored SHA-256 mismatches download | Source changed between passes or corruption | Immutable staging, end-to-end verification |
| Using filename from URL as local path | Path traversal/name collisions | Use ID, sanitize, tempfiles |
| Team counts only files without estimating chunks | Overhead underestimated | Estimate chunks, indexes, replicas |

## 32. Exercises with Answers

### Exercise 1. Document Limit

An application wants to store a 25 MiB ZIP file in a `BinData` field of an `exports` document. Can the entire file be stored inside one BSON document?

**Answer:** No. The limit of a single BSON document is **16 MiB**, including overhead. Use GridFS or object storage; Base64 does not bypass the limit.

### Exercise 2. Splitting Chunks Inside the Same Document

A developer splits a 40 MiB file into 80 pieces and puts a `chunks` array containing all pieces into **one document**. Does this bypass the 16 MiB limit?

**Answer:** No. The total document size still exceeds the limit. GridFS stores **each chunk in a separate document** alongside a separate file entry.

### Exercise 3. Two Collections of a Bucket

What collections does a bucket named `archives` have?

**Answer:** `archives.files` containing file metadata and `archives.chunks` containing chunk documents. The default `fs` bucket uses `fs.files` and `fs.chunks`.

### Exercise 4. Which Field Links a Chunk to a File?

```javascript
{
  _id: ObjectId("..."),
  files_id: ObjectId("..."),
  n: 12,
  data: BinData(0, "...")
}
```

**Answer:** `files_id` points to the `_id` of the file entry in `files`. `n` is the chunk sequence number, not the file ID.

### Exercise 5. Calculating Chunk Count

A file is 20 MiB in size, with a chunk size of 255 KiB. How many data chunks are needed?

**Answer:** `ceil(20 × 1024 / 255) = ceil(80.3137...) = 81` chunks. The final chunk does not need to be a full 255 KiB.

### Exercise 6. Duplicate Filenames

In `fs.files`, there are two documents with `filename: "receipt.pdf"` but different `_id` values. Is this necessarily a data error?

**Answer:** No. GridFS allows multiple file entries with the same filename. The application must define versions/revisions and use the file ID to retrieve the intended version.

### Exercise 7. Choosing Storage for Video

A platform streams 2 GiB videos to tens of thousands of viewers, needing CDN and seeking across byte ranges. Should GridFS or object storage be prioritized for evaluation?

**Answer:** **Object storage + CDN** is usually better suited for large-scale media delivery and ranged requests. MongoDB can still store metadata, permissions, and object keys. GridFS can store bytes, but it does not natively provide full media-delivery features.

### Exercise 8. Choosing Storage for Internal Records

A service stores 25 MiB PDFs with low download volume, needs MongoDB metadata, and is accessed only through an authenticated backend. Is GridFS worth trying?

**Answer:** Yes. The files exceed the single BSON document limit; GridFS provides streaming and metadata within MongoDB. Still, you must benchmark disk/backup/latency costs and compare against object storage if already available.

### Exercise 9. Mid-Upload Failure

A consumer crashes after uploading 50 chunks but before the file entry is written. What can be left behind in the system?

**Answer:** **Orphan chunks** without a corresponding file entry may remain. You must have a cleanup workflow with a grace period and awareness of active uploads, rather than immediately deleting every chunk lacking an entry.

### Exercise 10. Order of Updating Business Pointers

You want to replace contract file A with file B. Should you update the pointer to B **before** B finishes uploading successfully, or after B has uploaded and passed validation?

**Answer:** Usually **after B is complete and valid**. Then update the pointer according to business rules and handle file A per version/retention policy. Never let an official record point to a file that is not ready.

### Exercise 11. Checksums

A downloaded file has a length equal to `files.length`. Is that sufficient to conclude the bytes are intact?

**Answer:** Not sufficient. You need a strong checksum like SHA-256 or equivalent content verification. Two files of the same length can have different bytes.

### Exercise 12. Metadata and Authorization

An endpoint receives `fileId` from a URL. The file ID exists, so the server immediately returns the bytes. What is the problem?

**Answer:** There is a risk of exposing files belonging to other users/tenants. You must authenticate and check business ownership/ACLs before streaming.

### Exercise 13. Deleting with TTL

An operations team creates a TTL index on `fs.files.uploadDate` so file metadata automatically disappears after 30 days. Is this a standard GridFS way to delete the entire file?

**Answer:** No. TTL on the file entry does not invoke GridFS delete to remove chunks. It can leave orphan chunks behind. You need a lifecycle job using the GridFS API while enforcing retention and permissions.

### Exercise 14. Optimizing Upload RAM

Java code uses `Files.readAllBytes()` for a 1 GiB file and passes the byte array to an API. How should this be improved?

**Answer:** Use `InputStream` and `GridFSBucket.uploadFromStream()`, and apply size limits, backpressure, and timeouts. Do not hold the entire file in RAM.

### Exercise 15. Capacity Forecasting

An application has 200,000 files, averaging 150 chunks per file. Approximately how many complete chunk documents are there?

**Answer:** `200,000 × 150 = 30,000,000` chunk documents. This excludes file entries, indexes, replica copies, orphan data, backups, and oplog.

### Exercise 16. Distinguishing GridFS Chunks from Sharding Chunks

GridFS splits a file into 500 chunks. Can we conclude the file's bytes are evenly distributed across 500 shards?

**Answer:** No. A GridFS chunk is a **file piece**; a sharding chunk/range is a **cluster data distribution unit**. Involving multiple shards requires a dedicated sharding design.

### Exercise 17. A 10 KiB File

An application has a 10 KiB binary JSON configuration read alongside a single configuration document. Does it need to use GridFS?

**Answer:** Not required. If the total BSON document stays below 16 MiB and read/update patterns fit, embedding binary or storing text/document data directly can be simpler. Consider security and schema design.

### Exercise 18. PDF Files with the Same Name

A user uploads `invoice.pdf` v1 and then v2. The download API queries by filename and always picks "the newest file," yet the business needs to reproduce the exact signed invoice from last year. Where is the design flaw?

**Answer:** Filename does not designate an immutable version. The business record must store the **file ID/version** of the signed copy; v2 is a separate file entry.

## 33. Checklist for Adopting GridFS in a Project

Before deciding, verify:

1. **Does the problem truly require storing bytes in MongoDB?** Compare with BSON binary or object storage.
2. **File sizes and counts:** forecast files exceeding 16 MiB, total chunks, storage volume, and throughput.
3. **Upload/download path:** streaming, timeouts, quotas, and concurrency.
4. **Access pattern:** whole-file, HTTP Range, video, CDN, or internal backend.
5. **Bucket naming:** `fs` or a domain bucket, consistent across drivers/tools.
6. **Metadata schema:** tenant, owner, content type, checksum, file version, retention.
7. **Business references:** store file ID in business records; do not use filename as a unique key.
8. **Indexes:** keep required GridFS indexes, add metadata indexes based on actual queries.
9. **Write concern and replication:** choose appropriate durability and factor it into latency.
10. **Atomicity:** do not assume multi-chunk uploads are a single transaction.
11. **Retry/idempotency:** `uploadRequestId`, unique constraints, and duplicate detection.
12. **Cleanup:** orphan chunks, orphan files, failed uploads, and grace periods.
13. **Versioning:** immutable files, upload new versions, update pointers safely.
14. **Checksums:** store SHA-256 and verify when needed, preventing source changes mid-upload.
15. **Security:** AuthN/AuthZ, tenant isolation, TLS, encryption, malware scanning.
16. **Retention:** use a GridFS delete workflow, do not delete `files` metadata directly with TTL.
17. **Backup/restore:** both `files` and `chunks` together with business references, backed by restore tests.
18. **Monitoring:** storage/indexes, upload failures, replication lag, OLTP p95/p99.
19. **Scaling:** evaluate GridFS sharding by version and workload, or offload to object storage.
20. **Benchmarking:** measure with a realistic file corpus, concurrency, and target SLAs; do not decide on intuition.

## 34. Summary

**GridFS** enables MongoDB to store large files by splitting bytes into multiple **chunk documents** in `<bucket>.chunks` and storing a **file metadata document** in `<bucket>.files`. It overcomes the **16 MiB per-BSON-document limit** for the overall file and provides **streaming upload/download** through MongoDB drivers.

However, just because a file **can be stored in GridFS** does not mean GridFS **is the best place to store it**. For small files that need to travel with one document, BSON binary can be simpler. For videos, high-scale public image/file downloads, CDN delivery, byte ranges, and long-term archival, object storage + MongoDB metadata is usually worth prioritizing in evaluation. For large documents accessed through a backend, needing integrated metadata/queries and moderate traffic, GridFS is a reasonable candidate.

When choosing GridFS, treat **file ID, chunks, metadata, business references, checksums, versions, and retention** as a single lifecycle system. Uploads/deletes can fail across multiple documents; write concern does not replace idempotency or cleanup. By forecasting chunk counts, benchmarking I/O, using streams, enforcing strict access controls, and testing full restores, applications can leverage GridFS within its proper scope without turning MongoDB into an overloaded file server.

### Official References

- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Java Sync Driver — Store and Retrieve Files with GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [MongoDB Database Tools — mongofiles](https://www.mongodb.com/docs/database-tools/mongofiles/)
- [MongoDB Manual — BSON Document Size](https://www.mongodb.com/docs/manual/reference/limits/#bson-documents)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
