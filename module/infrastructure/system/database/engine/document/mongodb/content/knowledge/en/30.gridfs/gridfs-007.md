# Comparing GridFS with Storing Files in Documents or Object Storage

In MongoDB, attachments can be avatars, PDF contracts, reports, audio recordings, videos, or auto-generated documents. Three common choices are: embedding bytes inside a BSON document, storing via GridFS, or storing bytes in object storage while keeping only metadata in MongoDB.

These three options address different needs. Binary inside a document works well when data is small and tightly coupled with the record; GridFS helps when files are large yet you still want to manage bytes inside MongoDB; object storage is convenient for media delivery, CDNs, lifecycles, and storing files independently of the database. There is no optimal answer based solely on file size.

This lesson belongs to the **GridFS** chapter of the **Database Engine Document MongoDB** module, comparing the options across the 16 MiB limit, streaming, indexes/metadata, consistency, versioning, access control, backup/restore, performance, total cost, and error-handling workflows. The final sections include `mongosh` and Java Sync Driver examples, API architecture, exercises, and a checklist.

**Scope:** GridFS is a convention for storing files through MongoDB drivers. Object storage is a byte-storage layer external to MongoDB, such as an S3-compatible service. Examples assume versions and topologies supporting the APIs used; never use sample files from this lesson as production data.

## 1. Three File Storage Models

### 1.1. Binary Directly in a Document

~~~javascript
{
  _id: "attachment-001",
  ownerId: "user-001",
  filename: "hello.txt",
  contentType: "text/plain",
  length: 5,
  data: BinData(0, "SGVsbG8="),
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

`BinData` represents BSON Binary. The Base64 representation of `"Hello"` here only illustrates binary bytes in the shell; applications normally send real byte arrays through the driver.

**Metadata and file bytes live in the same document.** This is simple for small data, yet the entire BSON document is size-limited.

### 1.2. GridFS

~~~text
MongoDB database
  |
  +-- fs.files
  |    _id
  |    filename
  |    length
  |    chunkSize
  |    uploadDate
  |    metadata
  |
  +-- fs.chunks
       files_id, n=0, data=<bytes>
       files_id, n=1, data=<bytes>
       files_id, n=2, data=<bytes>
       ...
~~~

The file is split into multiple chunks. Each chunk is a small BSON document, allowing the overall file to exceed the single-document threshold. GridFS drivers provide streaming upload and download.

### 1.3. Object Storage and MongoDB Metadata

~~~text
MongoDB attachments:
  _id = ATT-001
  ownerId = USER-001
  status = ready
  storage = {bucket, key, versionId}

Object storage:
  bucket = private-files
  key = tenant-a/ATT-001/v1
  content = file bytes
~~~

MongoDB handles business records, metadata, permissions, and state. Object storage holds bytes and service-level delivery/lifecycle features.

## 2. Overview Comparison Table

| Criterion | Embedded BSON Binary | GridFS | Object storage |
| --- | --- | --- | --- |
| Byte location | Inside one MongoDB document | Multiple MongoDB chunk documents | External service outside MongoDB |
| Files exceeding 16 MiB | Not possible in one document | Supported via chunks | Supported per service limits |
| Streaming large files | Not convenient | Supported by driver APIs | Usually supported by API/HTTP |
| Atomic bytes + metadata | Within the same document | Multiple writes/docs | Two separate systems |
| Querying business metadata | Directly in MongoDB | `fs.files` or app collection | MongoDB metadata collection |
| CDN capability | Needs custom gateway | Needs custom gateway | Often has convenient ecosystem |
| HTTP Range / multipart | App implements itself | Needs additional handling | Often built-in dedicated support |
| Bytes in MongoDB backup | Yes | Yes | No, must back up separately |
| Database footprint | Both bytes and metadata | Bytes, chunks, and indexes | Primarily metadata |
| Authorization | MongoDB + backend | MongoDB + backend | Backend + object IAM/policies |
| Versioning | Application version | New `fileId` | Object key / `versionId` |
| Lifecycle / archival | Application | Application | Can leverage storage policies |
| Typical examples | Small files / thumbnails | Large internal files | Videos, large PDFs, CDN |

**Preliminary conclusion:** File size is a necessary factor to check, yet read frequency, permissions, retention, deployment requirements, and total cost ultimately drive the choice.

## 3. The 16 MiB BSON Document Limit

MongoDB typically caps a single BSON document at **16 MiB**:

\[
16\ \mathrm{MiB}=16 \times 1024 \times 1024=16{,}777{,}216\ \text{bytes}
\]

The limit applies to the **entire** document:

~~~text
_id
tenantId
filename
contentType
length
metadata
data bytes
BSON field names, type markers and overhead
~~~

### 3.1. An Exact 16 MiB File Still Cannot Be Embedded with Metadata

If the bytes alone already total 16 MiB, no room remains for other fields and BSON overhead. Applications should enforce a much lower upload limit rather than targeting the exact 16 MiB boundary.

### 3.2. Base64 Strings Differ from BSON Binary

An HTTP API receiving:

~~~json
{"dataBase64":"SGVsbG8="}
~~~

can decode it into bytes. Storing the raw string incurs Base64 inflation and stores a `String` field; using BSON Binary stores raw binary bytes.

### 3.3. When to Use GridFS to Exceed the Limit?

When a file cannot be embedded yet the organization wants to keep bytes in MongoDB, **GridFS is the standard mechanism**. If reliable object storage is already available, still compare both before deciding.

### 3.4. Total Dataset Limits Differ from Single-Record Limits

MongoDB can store vast numbers of small files across many documents, yet any single document cannot exceed 16 MiB. GridFS splits a file across multiple documents to work within that rule—it does not abolish the BSON limit.

## 4. When Should You Embed Binary in a Document?

Embedding usually makes sense when:

- Files are small and size-bounded.
- The file is read alongside the business record.
- You want to update bytes and metadata **atomically in the same document**.
- You do not need to stream huge files.
- There is no need for a CDN or independent lifecycle.
- Total database footprint remains manageable.

Example of a small signature or thumbnail:

~~~javascript
{
  _id: "avatar:user-001",
  userId: "user-001",
  version: 2,
  mimeType: "image/webp",
  data: BinData(0, "..."),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
~~~

### 4.1. Atomic Update in One Document

~~~javascript
db.avatars.updateOne(
  {
    _id: "avatar:user-001",
    version: 2
  },
  {
    $set: {
      data: BinData(0, "SGVsbG8="),
      mimeType: "text/plain",
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
~~~

In this example, the bytes are just the text `"Hello"`, not a real WebP image. The point illustrated is that version, bytes, and MIME field update together in **one MongoDB document operation**.

### 4.2. When Not to Embed Even If the File Is Small?

- Files downloaded very frequently from the internet.
- Files needing independent CDN/caching.
- Metadata is queried frequently while bytes are rarely needed.
- File counts are massive, making database storage and backups expensive.
- Files need independent versioning or lifecycle policies.

**A 40 KiB file downloaded a million times a day may fit object storage + CDN better than BSON embedding.**

### 4.3. Use Projection When Only Metadata Is Needed

~~~javascript
db.avatars.find(
  {
    userId: "user-001"
  },
  {
    data: 0
  }
);
~~~

Avoid transferring bytes whenever you only want to display `filename` or status.

### 4.4. Defining an Application-Level Threshold

An application might cap embedded binaries at 1 MiB. That is a workload-specific policy, **not** a MongoDB limit replacing 16 MiB.

## 5. What Is GridFS?

**GridFS** is a convention for storing files using two MongoDB collections: one collection for file metadata and one collection holding binary chunks.

The default bucket is usually **`fs`**, corresponding to:

~~~text
fs.files
fs.chunks
~~~

You can name other buckets:

~~~text
attachments.files
attachments.chunks
reports.files
reports.chunks
~~~

### 5.1. GridFS Is Not a POSIX Filesystem

It does not provide directory trees, path permissions, file locking, HTTP media streaming, or CDNs out of the box. It is a file-storage layer built on MongoDB collections and driver APIs.

### 5.2. Why Can It Store Large Files?

A long file is split into multiple chunks; each chunk is a separate BSON document. Thus the overall file can exceed 16 MiB without requiring one document to hold all bytes.

### 5.3. Use the GridFS Driver Instead of Editing Collections Manually

The driver handles splitting/reassembling chunks, numbering, uploads, and downloads. Directly inserting or deleting in `fs.chunks` can leave missing chunks, mismatched lengths, or corrupted files.

## 6. Metadata in `fs.files`

A GridFS record typically looks like:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  filename: "contract.pdf",
  length: NumberLong(10485760),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:00:00Z"),
  metadata: {
    ownerId: "user-001",
    tenantId: "tenant-a",
    contentType: "application/pdf",
    businessAttachmentId: "ATT-001"
  }
}
~~~

| Field | Role |
| --- | --- |
| `_id` | GridFS file identity |
| `filename` | Descriptive name; can collide |
| `length` | Total bytes |
| `chunkSize` | Chunk size |
| `uploadDate` | Upload timestamp |
| `metadata` | Optional application data |

### 6.1. `filename` Is Not Unique

Two users can upload `invoice.pdf`, or one document can have multiple versions with the same name. **Never download or delete based on `filename` alone.** Store the exact `fileId` in the business record.

### 6.2. A Separate Application Attachment Record

~~~javascript
{
  _id: "ATT-001",
  ownerId: "user-001",
  tenantId: "tenant-a",
  status: "ready",
  storageType: "gridfs",
  gridFsBucket: "attachments",
  gridFsFileId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

This record governs permissions, versions, status, and links to orders/customers without relying solely on `fs.files.metadata`.

### 6.3. Avoid Duplicating Sources of Truth

If `ownerId` and `status` are copied between the app collection and `fs.files.metadata`, decide which one is authoritative and how permission changes propagate.

## 7. Chunk Documents in `fs.chunks`

A chunk:

~~~javascript
{
  _id: ObjectId("507f191e810c19729de860ea"),
  files_id: ObjectId("507f1f77bcf86cd799439011"),
  n: 0,
  data: BinData(0, "...")
}
~~~

- **`files_id`** links to the file.
- **`n`** is the chunk sequence starting at `0`.
- **`data`** holds the chunk's bytes.

### 7.1. Important Unique Index

GridFS uses the index:

~~~javascript
{
  files_id: 1,
  n: 1
}
~~~

with uniqueness so a file cannot have two chunks with the same `n`.

### 7.2. File Metadata Index

An index on `filename` and `uploadDate` is used by GridFS to look up files by name/time. Business metadata may need additional indexes if the application queries it heavily.

### 7.3. Do Not Search PDF Text by Querying `chunks`

Storing PDF bytes does not mean MongoDB can search sentences inside them directly. You must extract text and build a dedicated text/vector index.

## 8. Chunk Size and Splitting Overhead

GridFS commonly defaults to a chunk size of **255 KiB**:

\[
255 \times 1024 = 261{,}120\ \text{bytes}
\]

For a file of `L` bytes and chunk size `C`:

\[
N=\left\lceil \frac{L}{C}\right\rceil
\]

For example, a 10 MiB file typically requires **41 chunks** at that size.

### 8.1. The Last Chunk Is Usually Smaller

If `L` is not evenly divisible by `C`, the last chunk holds the remaining bytes. Never discard the final chunk just because it is smaller than `chunkSize`.

### 8.2. Multi-Gigabyte Files Produce Many Chunk Documents

A 1 GiB file at 255 KiB/chunk needs over four thousand chunks. This increases document/index counts and backend operations.

### 8.3. Larger Chunks Are Not Always Better

- Increasing chunk size reduces the number of chunks.
- Larger chunks also affect memory usage, retries, and per-operation payload size.
- Very large chunks must still stay within the BSON document limit.

Benchmark with realistic file sizes, concurrency, and storage topologies.

### 8.4. Empty Files

A file with `length=0` has zero chunks; do not treat it as an error if the application permits empty files.

## 9. GridFS Upload Workflow

~~~text
InputStream
   |
   v
GridFS driver
   |
   +--> write chunk n=0
   +--> write chunk n=1
   +--> write chunk n=2
   |
   v
Write fs.files metadata
   |
   v
Return fileId
~~~

Normally, the driver writes `fs.files` once the upload finishes.

### 9.1. Mid-Upload Failures

Chunks without a matching `fs.files` entry can remain. This is a type of orphan/incomplete upload requiring careful cleanup.

### 9.2. Crash After Upload Before Saving Application Metadata

A complete GridFS file may already exist while the application has not yet saved `fileId` into `ATT-001`. Retrying without idempotency can create a duplicate file.

### 9.3. The `ready` State

Mark the application attachment `ready` only after both the GridFS upload and validation succeed. If antivirus scanning is required, keep the file in `quarantine`/`pending` until scanning finishes.

### 9.4. Do Not Assume Atomicity Across All Chunks

GridFS spans multiple writes and documents. One upload is not a single-document atomic operation. Even when the backend uses transactions elsewhere, understand driver and topology boundaries rather than assuming all file operations share a transaction.

## 10. GridFS Download Workflow

~~~text
HTTP request ATT-001
      |
      v
Authenticate + authorize
      |
      v
Lookup attachment metadata
      |
      v
GridFS fileId
      |
      v
Driver reads chunks by n
      |
      v
OutputStream -> HTTP response
~~~

### 10.1. Streaming Reduces Memory Usage

Chunks can be read sequentially without loading the entire file into a large `byte[]`.

### 10.2. Backpressure and Slow Clients

If a downloader reads slowly, the application must avoid unbounded buffering; enforce stream cancellation, timeouts, and backpressure.

### 10.3. HTTP Range Is Not Built In

A GridFS stream does not automatically implement full HTTP range headers and semantics. Applications can implement partial reads using driver APIs, but must handle `Range`/`206`/`If-Range` correctly themselves.

### 10.4. CDNs Require an Additional Layer

GridFS does not generate public URLs or cache at the edge. For heavy media delivery, object storage/CDN is usually more convenient.

## 11. Replacing GridFS File Contents

A safe approach is to **create a new `fileId` and swap the reference**.

~~~text
File version 1 -> GridFS ID A
File version 2 -> GridFS ID B
~~~

Workflow:

1. Upload version 2 to GridFS.
2. Verify length, checksum, and policies.
3. Update the business record from A to B with a version check.
4. Keep A for rollback/retention if needed.
5. Delete A once unreferenced or past retention.

### 11.1. Never Edit Chunks Directly

Manually updating a chunk can break length/ordering and expose inconsistent bytes to concurrent readers.

### 11.2. Atomic Pointer Switch

~~~javascript
db.attachments.updateOne(
  {
    _id: "ATT-001",
    activeVersion: 1
  },
  {
    $set: {
      activeVersion: 2,
      gridFsFileId: newFileId
    }
  }
);
~~~

Updating a business pointer inside a single document is atomic, even though uploading the new file and cleaning up the old one are separate steps.

## 12. Deleting GridFS Files

Use **`GridFSBucket.delete(fileId)`** instead of deleting directly from just one collection.

### 12.1. Deleting `fs.files` While Keeping `fs.chunks`

Chunks continue consuming storage without valid file metadata.

### 12.2. Deleting `fs.chunks` While Keeping `fs.files`

File metadata remains, yet downloads fail with missing data.

### 12.3. Failed Deletes

Because multiple documents are involved, implement retries and reconciliation. Never assume `delete` is atomic under every failure mode.

### 12.4. Shared References

If multiple business records reference the same `fileId`, never delete the bytes when only one reference is removed. Maintain an ownership/reference policy.

## 13. How Does Object Storage Work?

Object storage stores data by **bucket/container + object key**.

~~~text
Bucket: private-attachments
Key: tenant-a/contracts/ATT-001/v1
Bytes: <contents of contract.pdf>
~~~

MongoDB stores metadata:

~~~javascript
{
  _id: "ATT-001",
  tenantId: "tenant-a",
  ownerId: "user-001",
  filename: "contract.pdf",
  contentType: "application/pdf",
  length: NumberLong(10485760),
  status: "ready",
  storage: {
    kind: "object",
    bucket: "private-attachments",
    key: "tenant-a/contracts/ATT-001/v1",
    versionId: "if-supported"
  }
}
~~~

### 13.1. Keys Are Not POSIX File Paths

Slashes in an object key are typically just a naming convention/prefix. Object storage does not necessarily have real directories.

### 13.2. Never Store Presigned URLs as Permanent References

Presigned URLs expire. Store the bucket, key, and version ID, and issue fresh URLs when authorized users request access.

### 13.3. Object Metadata Does Not Replace a Business Database

Providers support object tags and metadata, yet those do not replace MongoDB queries by `orderId`, `ownerId`, status, tenant, or authorization rules.

## 14. Uploading Objects Through the Backend

~~~text
Client -> Application API -> Object storage
                        |
                        v
                  MongoDB metadata
~~~

Pros:

- The backend sees the bytes, making validation and scanning easy.
- Synchronous policies can run inline.

Cons:

- The application bears all upload bandwidth.
- Large files and concurrent uploads create load.

Use streaming rather than reading whole files onto the heap.

## 15. Direct Uploads via Presigned URLs

A workflow:

~~~text
Client -> Backend: request upload
Backend: authenticate + validate size/type
Backend -> MongoDB: create pending attachment
Backend -> Client: short-lived upload URL
Client -> Object storage: put/multipart
Client -> Backend: finalize request
Backend -> Object storage: verify
Backend -> MongoDB: mark ready
~~~

### 15.1. Do Not Trust Client Claims of Upload Success

The backend must verify object existence, byte size, checksum/file signature, and scan policies as needed.

### 15.2. Scope and TTL

Presigned URLs must be tightly scoped by key, HTTP method, and expiration. Never issue a token granting write access to an entire bucket.

### 15.3. Multipart Uploads

Object storage usually provides multipart APIs for large files. If an upload fails, abort and clean up incomplete parts per provider guidelines.

### 15.4. Idempotent Retries

Use a stable attachment ID and upload attempt/version to avoid creating unnecessary duplicate objects.

## 16. Object Downloads and CDNs

Two patterns:

~~~text
Backend proxy:
Client -> App -> Object storage -> App -> Client

Direct signed download:
Client -> App (auth)
App -> Client (short-lived URL)
Client -> Object storage
~~~

### 16.1. CDNs

Object storage typically integrates smoothly with CDNs for read-heavy media. Cache hits reduce origin requests and latency.

### 16.2. Private Objects

Never make a bucket holding personal contracts public. Use private origins, signed URLs/cookies, cache keys, and appropriate expirations.

### 16.3. Byte Ranges

Object storage generally supports `Range` requests via HTTP/SDKs, making media seeking and download resumes convenient.

### 16.4. Egress Costs

When using object storage/CDNs, monitor data egress, cache hit ratios, and request fees—not just GB-month storage rates.

## 17. Comparing Atomicity and Consistency

### 17.1. Binary in a Document

When bytes and metadata live in one document, a single update modifies both atomically per MongoDB semantics.

### 17.2. GridFS

Bytes span many chunk documents plus file metadata, and the business record may be a third document. Applications need workflow states and partial-failure handling.

### 17.3. Object Storage

Object puts and deletes happen outside MongoDB transactions. The two writes succeed or fail independently.

~~~text
MongoDB attachment update
            +
Object storage put
            !=
One automatic distributed transaction
~~~

### 17.4. Recommended State Machine

~~~text
PENDING
   |
   v
UPLOADING
   |
   v
VERIFYING / SCANNING
   |
   +----> READY
   |
   +----> FAILED / RETRY

READY -> DELETING -> DELETED
~~~

Serve only `READY` files to authorized users.

## 18. Two-Phase Finalize Design

Reserve metadata:

~~~javascript
db.attachments.insertOne({
  _id: "ATT-001",
  tenantId: "tenant-a",
  ownerId: "user-001",
  storage: {
    kind: "object",
    bucket: "private-attachments",
    key: "tenant-a/ATT-001/v1"
  },
  status: "pending",
  createdAt: new Date()
});
~~~

After upload completes, the backend verifies and finalizes:

~~~javascript
db.attachments.updateOne(
  {
    _id: "ATT-001",
    status: "pending"
  },
  {
    $set: {
      status: "ready",
      verifiedAt: new Date()
    }
  }
);
~~~

### 18.1. Failure After Upload Before Finalize

The object exists while metadata stays `pending`. A reconciliation job can inspect the object at its stable key and either finalize or clean up per policy.

### 18.2. Failure Before Upload

Metadata is `pending` while no object exists yet. After a timeout, retry or mark `failed`; never return a download link.

### 18.3. Never Promote `pending` to `ready` Based on Time Alone

Elapsed time does not prove bytes were uploaded properly. Require verification evidence from the storage service or backend validation.

## 19. Idempotency and Duplicate Uploads

A request may upload successfully while the response is lost on the network.

~~~text
Server put success
  |
  v
Response lost
  |
  v
Client retries
~~~

If each retry creates a new `fileId` or `objectKey`, duplicates accumulate.

### 19.1. Stable Logical Attachment ID

Create `ATT-001` before uploading. Retries of the same operation must resolve back to `ATT-001`.

### 19.2. Upload Attempt / Version

Store attempt IDs, versions, or hashes to distinguish retries from genuinely new content versions.

### 19.3. Conditional Updates

When finalizing or switching references, check expected version/status so stale operations never overwrite newer state.

### 19.4. Cleaning Up Duplicates

Never delete files solely because checksums match when multiple owners or different retention rules may apply. Enforce ownership/reference policies.

## 20. Versioning Across the Three Models

| Model | Typical Way to Replace a File |
| --- | --- |
| Embedded | Update `Binary` field + version in document |
| GridFS | Upload new `fileId`, swap pointer |
| Object storage | Use new key version or provider `versionId` |

### 20.1. Immutable Versions Enable Rollbacks

~~~text
ATT-001/v1
ATT-001/v2
ATT-001/v3
~~~

When v3 breaks, the system can point back to v2 if retained and allowed by policy.

### 20.2. Never Delete Old Versions Before Verifying New Ones

If uploading v2 fails after deleting v1, the user loses their file. Follow verify → switch → grace period → cleanup.

### 20.3. Concurrent Edits

If a user uploads v3 while a migration copies v2, the migration worker must never revert the active pointer from v3 back to v2. Use document versions / CAS.

## 21. Checksums and Integrity

You can store:

~~~javascript
{
  length: NumberLong(1234567),
  sha256: "sha256-digest-of-exact-bytes"
}
~~~

### 21.1. Legacy MD5 in GridFS

Older GridFS versions/APIs included `md5` or `filemd5`. Do not treat this as a modern security check or assume it is always present.

### 21.2. Object Storage `ETag`

`ETag` may differ from MD5—especially with multipart uploads or server-side encryption, depending on the provider. Never replace SHA-256 verification merely because a provider returns an `ETag`.

### 21.3. Checksums Do Not Replace Authorization

SHA-256 verifies bytes, not whether a user is authorized to read the file or whether it came from a trusted creator. Authenticity may require digital signatures or additional verification.

### 21.4. When Should You Verify?

After uploads, after migrations, when restoring from backups, or per integrity policy. For very large files, measure CPU and I/O costs.

## 22. Security and Sensitive Data

### 22.1. Binary/GridFS in MongoDB

Use database RBAC, TLS, encryption, restricted direct DB access, and backend ownership checks.

### 22.2. Object Storage

Use private buckets, least-privilege IAM, encryption at rest/TLS, tightly scoped presigned URLs, and audit logs.

### 22.3. Unguessable IDs Are Not Permissions

A client knowing another tenant's GridFS `fileId` or object key does not gain permission to view it simply by knowing that string.

### 22.4. Spoofed File Types

Do not trust a `.pdf` filename, client-sent MIME type, or extension to determine safety. Inspect bytes/signatures and enforce allowlists.

### 22.5. Malware Scanning

~~~text
UPLOADED -> QUARANTINED -> SCAN
                              |
                              +-> CLEAN -> READY
                              |
                              +-> INFECTED -> REJECT
~~~

If the scanner times out and policy mandates scanning, the file must not become `READY`.

### 22.6. Caching Private Attachments

Never place private PDFs into a public CDN cache without signed access controls. Configure `Cache-Control`, TTLs, and invalidations carefully.

## 23. HTTP File Responses

When serving bytes through the backend, configure headers:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="contract.pdf"
Content-Length: 1234567
Cache-Control: private, no-store
~~~

This is an example, not a fixed policy for every file.

### 23.1. Sanitize Filenames

User-entered filenames must be encoded/sanitized before placing them into HTTP headers to prevent header injection and path tricks.

### 23.2. `Content-Disposition`

`inline` allows browsers to render some formats directly; `attachment` prompts a download. For untrusted files, assess XSS and active-content risks before allowing `inline`.

### 23.3. `Range`

Return status `206` only when the server properly implements byte ranges, `If-Range`, `Content-Range`, and invalid-range handling.

### 23.4. Cancellation

Stop reading the stream when the client disconnects; never keep downloading a 2 GiB file into an unused buffer.

## 24. Cost and Capacity

### 24.1. Embedded and GridFS

Bytes go into MongoDB data storage, replication, and backups.

Costs include:

- Primary/secondary disk.
- Network replication traffic.
- Index overhead.
- Backups and snapshots.
- Restore time.
- Database CPU and I/O.
- Client download bandwidth through DB/app.

### 24.2. GridFS Chunk Overhead

Each large file produces many chunk docs and index entries. Storage cost depends not just on total bytes, but also document and operation counts.

### 24.3. Object Storage

Costs can include GB-month storage, PUT/GET requests, multipart operations, egress, CDN, archive retrieval, cross-region replication, and versioning.

### 24.4. Estimation Example

~~~text
Stored bytes ~ sum(file sizes)
Monthly served bytes ~ requests * mean bytes transferred
Mongo replicated footprint ~ bytes * replica copies + overhead
~~~

Factor in peak traffic, backups, cross-region transfers, CDN cache hit rates, and migration phases.

### 24.5. No Single Model Is Universally Cheapest

Object storage can be inexpensive for large, rarely downloaded files, yet heavy egress adds up. GridFS can suit internal systems leveraging existing MongoDB capacity, though you must watch capacity and query latency impact.

## 25. Backup and Disaster Recovery

### 25.1. Embedded

Bytes and metadata live in the same MongoDB document. Database backup/restore covers both.

### 25.2. GridFS

You must back up and restore **both `files` and `chunks` collections**, along with application attachment mappings. Backing up only `fs.files` cannot restore bytes.

### 25.3. Object Storage

Metadata lives in MongoDB and bytes live in the object store. They may have two separate backup and retention schedules.

### 25.4. Skewed Restores

~~~text
MongoDB restored at T1
Object storage current at T2
~~~

This can create orphan objects or dangling references. Run reconciliation after DR.

### 25.5. RTO/RPO Must Cover the Entire System

Do not measure only whether MongoDB restored cleanly; also verify object references are downloadable and file permissions/versions remain accurate.

## 26. Metadata Indexing

For embedded binaries or app attachments:

~~~javascript
db.attachments.createIndex({
  tenantId: 1,
  ownerId: 1,
  status: 1,
  createdAt: -1
});
~~~

For GridFS metadata:

~~~javascript
db.fs.files.find(
  {
    "metadata.tenantId": "tenant-a",
    "metadata.businessAttachmentId": "ATT-001"
  },
  {
    filename: 1,
    length: 1,
    uploadDate: 1
  }
);
~~~

If workloads frequently filter by metadata, add matching indexes on `fs.files` or the app collection.

### 26.1. Searching Inside Files Is Not Metadata Search

PDFs stored in GridFS or object storage cannot be queried by sentence automatically. You need text extraction/OCR (if required) plus a text index or vector search.

### 26.2. Do Not Create Indexes on Intuition

Index important query patterns and measure real behavior; every index carries storage and write costs.

## 27. Java Sync Driver: Storing Small Binaries

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;

import org.bson.Document;
import org.bson.types.Binary;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Date;

public class SaveSmallFile {

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        Path path = Path.of("hello.txt");
        byte[] bytes = Files.readAllBytes(path);

        int applicationLimit = 1024 * 1024;

        if (bytes.length > applicationLimit) {
            throw new IllegalArgumentException(
                    "File too large for embedded storage"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> files =
                    client.getDatabase("file_lab")
                          .getCollection("smallFiles");

            files.insertOne(
                    new Document("_id", "hello-file")
                            .append("filename", "hello.txt")
                            .append("contentType", "text/plain")
                            .append("length", bytes.length)
                            .append("data", new Binary(bytes))
                            .append("createdAt", new Date())
            );
        }
    }
}
~~~

### 27.1. Memory

`Files.readAllBytes()` fits small, bounded files. Never use it for large files in production.

### 27.2. The Application Limit Is Illustrative

1 MiB is simply the policy in this example, not a MongoDB hard limit.

## 28. Java Sync Driver: GridFS Upload

~~~java
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

public class UploadGridFS {

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        Path path = Path.of("manual.pdf");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("file_lab");

            GridFSBucket bucket = GridFSBuckets.create(
                    db,
                    "attachments"
            );

            GridFSUploadOptions options =
                    new GridFSUploadOptions()
                            .chunkSizeBytes(255 * 1024)
                            .metadata(
                                    new Document(
                                            "tenantId",
                                            "tenant-a"
                                    ).append(
                                            "ownerId",
                                            "user-001"
                                    ).append(
                                            "contentType",
                                            "application/pdf"
                                    )
                            );

            try (InputStream source =
                         Files.newInputStream(path)) {

                ObjectId fileId = bucket.uploadFromStream(
                        path.getFileName().toString(),
                        source,
                        options
                );

                System.out.println(fileId);
            }
        }
    }
}
~~~

### 28.1. Bucket Name

The `attachments` bucket uses `attachments.files` and `attachments.chunks`, not `fs.files`/`fs.chunks`.

### 28.2. Returned `fileId`

Save `fileId` in the application record upon upload completion, with retry handling and tenant authorization.

### 28.3. Chunk Size

255 KiB is a common default; adjust only after benchmarking.

## 29. Java Sync Driver: GridFS Download

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

import org.bson.types.ObjectId;

import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class DownloadGridFS {

    public static void main(String[] args) throws Exception {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        ObjectId fileId = new ObjectId(
                "507f1f77bcf86cd799439011"
        );

        try (MongoClient client = MongoClients.create(uri);
             OutputStream target = Files.newOutputStream(
                     Path.of("downloaded.pdf")
             )) {

            GridFSBucket bucket = GridFSBuckets.create(
                    client.getDatabase("file_lab"),
                    "attachments"
            );

            bucket.downloadToStream(fileId, target);
        }
    }
}
~~~

### 29.1. Illustrative File ID

Replace the `ObjectId` in code with the actual value returned by an upload.

### 29.2. HTTP Endpoints Must Check Permissions

This snippet performs only the download itself. In real APIs, load metadata first, verify user authorization, and only then download.

### 29.3. Partial Downloads

If a destination file was only partially written due to a network error, delete it or write to a temporary file and verify before marking success.

## 30. Java: GridFS Metadata and Deletion

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;

import org.bson.types.ObjectId;

public class GridFSOperations {

    public static GridFSFile find(
            GridFSBucket bucket,
            ObjectId fileId
    ) {
        return bucket.find(
                Filters.eq("_id", fileId)
        ).first();
    }

    public static void delete(
            GridFSBucket bucket,
            ObjectId fileId
    ) {
        bucket.delete(fileId);
    }
}
~~~

Before deleting, the application must verify retention, shared references, owner, and status.

## 31. Abstraction Across All Three Storage Backends

An interface:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Map;

public interface FileStorage {

    StoredFile upload(
            String name,
            InputStream input,
            Map<String, String> metadata
    ) throws Exception;

    void download(
            StoredFile reference,
            OutputStream output
    ) throws Exception;

    void delete(
            StoredFile reference
    ) throws Exception;
}
~~~

~~~java
public record StoredFile(
        String kind,
        String storageId,
        String filename,
        String contentType,
        long length
) {}
~~~

Possible implementations:

~~~text
EmbeddedMongoStorage
GridFSStorage
ObjectStorageAdapter
~~~

### 31.1. Do Not Hide Differences

An abstraction should not assume every backend shares identical presigned URLs, Range behavior, atomic updates, multipart uploads, or versioning.

### 31.2. Storage References

Store both `kind` and a durable identifier (GridFS bucket/`fileId` or object bucket/key/`versionId`), not just a filename or temporary URL.

## 32. Stable Download API

An endpoint:

~~~text
GET /attachments/ATT-001/content
~~~

Workflow:

1. Authenticate user.
2. Load attachment metadata from MongoDB.
3. Check tenant/owner/status/ACL.
4. Resolve storage backend.
5. Stream download or issue a signed URL per policy.
6. Log access and metrics.

### 32.1. Do Not Let the Frontend Send `fileId` to Bypass Permissions

`fileId`/`ObjectId` is not an access token. The backend must verify permissions on `ATT-001`.

### 32.2. Swapping Backends Without Changing the API

When storage metadata records `kind` and an explicit reference, you can migrate gradually from GridFS to object storage while frontends keep calling the same attachment API.

## 33. Migration: Embedded to GridFS

A workflow:

1. Inventory file sizes and access patterns.
2. Provision GridFS bucket, indexes, and capacity.
3. Read binary source.
4. Upload via the GridFS driver.
5. Verify length and checksum.
6. Update attachment reference with a version check.
7. Support reading both embedded and GridFS during the transition.
8. Monitor errors and sample downloads.
9. Keep the source for rollback.
10. Clean up old bytes after confirmation.

Never delete original bytes before the new upload is verified and the reference has switched.

## 34. Migration: GridFS to Object Storage

~~~text
GridFS download stream
       |
       v
Object upload stream
       |
       v
Verify size + checksum
       |
       v
Switch MongoDB reference
       |
       v
Serve from object storage
       |
       v
Retire GridFS after grace period
~~~

### 34.1. Never Load the Entire File into RAM

Use streaming and multipart object uploads when needed.

### 34.2. Concurrency

If the source file changes during migration, the worker must check `activeVersion` before switching pointers.

### 34.3. Rollback

Retain the original GridFS file for a rollback grace period.

### 34.4. Orphan Objects

A successful object upload followed by a failed pointer switch can leave an unreferenced object; run reconciliation.

## 35. Migrating Back to GridFS

When policy requires files to reside inside MongoDB:

1. Fetch the exact object version.
2. Stream into GridFS.
3. Verify size and checksum.
4. Update the reference with a version check.
5. Serve via GridFS.
6. Clean up old objects after retention.

Never rely on an expiring presigned URL as a durable data source.

## 36. Concrete Selection Cases

| Workload | Worth-Considering Option | Reason |
| --- | --- | --- |
| 12 KiB avatar, low traffic | Embedded BSON | Simple, atomic with profile |
| 50 KiB logo, millions of views | Object storage + CDN | Distribution and caching |
| 25 MiB PDF contract | GridFS or object storage | Exceeds BSON limit, needs ACLs/retention |
| 100 MiB internal report | GridFS | Stream within MongoDB if capacity suffices |
| 2 GiB public video | Object storage + CDN | Range requests, egress, media ecosystem |
| Large multi-year ZIP backups | Object storage / archive tier | Lifecycle and cost |
| 100 KiB JSON artifact with record | Embedded BSON | Supports atomic updates |
| Tiny public file read constantly | Object/CDN or cache layer | Access pattern outweighs raw size |

Do not treat this table as a rigid rule. Evaluate deployment, network costs, SLAs, operations, and compliance requirements.

## 37. Operations and Monitoring

Key metrics:

- Upload success/failure rate.
- File size distribution (P50/P95/max).
- Download P50/P95 latency and time to first byte.
- Concurrent streams.
- MongoDB disk, I/O, and replica lag when using GridFS.
- Chunks per file and orphan chunk count.
- Object storage egress and request charges.
- CDN hit/miss ratio.
- Overdue pending uploads.
- Failed scans and checksum mismatches.
- Dangling references and orphan objects.
- Backup/restore duration.
- Delete/lifecycle processing errors.

### 37.1. Measuring Database Latency Alone Is Not Enough

For HTTP file APIs, measure end-to-end until the client receives the final byte, including slow networks, Range requests, and cancellations.

### 37.2. Orphan Cleanup Must Be Cautious

Before deleting an orphan candidate, enforce a grace period and avoid active uploads. Accidental deletion can cause unrecoverable data loss.

## 38. Common Pitfalls

| Mistake | Consequence |
| --- | --- |
| Embedding files too close to 16 MiB | BSON document exceeds limit |
| Storing Base64 strings instead of BSON Binary | Overhead and wrong schema |
| Querying metadata without projecting out bytes | Heavy network/memory load |
| Using GridFS for every tiny thumbnail | Unnecessary overhead |
| Treating GridFS as a CDN | Missing HTTP distribution ecosystem |
| Backing up only `fs.files` | No chunks for recovery |
| Manually deleting `fs.files` | Orphan chunks |
| Manually deleting `fs.chunks` | Corrupted files |
| Treating `filename` as a unique ID | Wrong version downloaded/deleted |
| Marking `ready` before verifying | Empty/incomplete files served |
| Upload crashes without cleanup | Orphan storage leaks |
| Downloading large files into `byte[]` | Memory pressure |
| Retries always generating new `fileId` | Duplicates |
| Editing chunks directly | Inconsistent files |
| Deleting shared files | Data loss for other references |
| Storing only presigned URLs | Expiring, broken references |
| Trusting client-sent MIME types | Dangerous content |
| Assuming `ETag` is always MD5 | Faulty integrity verification |
| Skipping user tenant checks | Data exposure |
| Putting private files in public CDN caches | Data leaks |
| Backing up only MongoDB when bytes live in object store | Incomplete disaster recovery |
| Missing cleanup for incomplete multipart uploads | Storage leaks |
| Deleting source before verifying target | File loss |
| Searching PDF text by querying `chunks` | No text index |
| Ignoring egress measurements | Unexpected bills |

## 39. Practice: Choosing a Model

### Exercise 1
A 15 KiB avatar stored with a user profile, rarely downloaded. Choose embedded, GridFS, or object storage and explain why.

### Exercise 2
A 20 MiB PDF, infrequently accessed and internal-only. Compare GridFS against object storage.

### Exercise 3
A 3 GiB video with many viewers, needing CDN and HTTP Range. Choose an architecture and state the trade-offs.

### Exercise 4
A 40 KiB image downloaded 1 million times per day. Why is small size alone not enough to pick BSON embedding?

### Exercise 5
A 100 KiB JSON artifact that must update atomically alongside a report's status. Is GridFS needed?

## 40. Practice: GridFS

### Exercise 6
Calculate the chunk count for a 10 MiB file with a 255 KiB chunk size. Can the last chunk be shorter than `chunkSize`?

### Exercise 7
Explain the roles of `fs.files`, `fs.chunks`, `files_id`, `n`, and the unique index on `(files_id, n)`.

### Exercise 8
An upload worker crashes after writing 5 chunks before creating `fs.files`. Where are the remaining bytes, and how should they be cleaned up?

### Exercise 9
Two users both upload `invoice.pdf`. Why is `filename` insufficient to pick the exact file?

### Exercise 10
Replace v1 with v2 in GridFS while allowing rollback. Design the verify, switch, and cleanup steps.

### Exercise 11
If you delete only `fs.files`, what happens? What if you delete only `fs.chunks`?

### Exercise 12
Write Java Sync Driver code using `GridFSBucket.uploadFromStream` and `downloadToStream` for large files.

## 41. Practice: Object Storage and Consistency

### Exercise 13
Design direct uploads via presigned URLs, a MongoDB `pending` record, backend verification, and marking `ready`.

### Exercise 14
An object upload succeeded while metadata stays `pending`. Design safe retry/reconciliation.

### Exercise 15
Why not store a presigned URL as a durable storage ID? Explain bucket/key/`versionId`.

### Exercise 16
MongoDB is restored to T1 while object storage is at T2. What orphan or dangling cases can arise?

### Exercise 17
Is `ETag` always an MD5 checksum? Why define a separate SHA-256 contract?

### Exercise 18
A user knows another tenant's `fileId`. What must the download endpoint verify?

### Exercise 19
Two business records share one `fileId`. When one record is deleted, can the bytes be deleted immediately?

### Exercise 20
Design `quarantine → scan → ready` for PDF uploads and handle scanner timeouts.

## 42. Practice: Migration and Cost

### Exercise 21
Migrate one million documents containing binaries to GridFS. Write a plan covering dual-read, verification, rollback, and cleanup.

### Exercise 22
Migrate from GridFS to object storage. Specify stream copying, checksum verification, and version checking.

### Exercise 23
A file stored in MongoDB GridFS receives one million downloads per month. Which TCO components must be measured to compare with object storage?

### Exercise 24
PDF reports in GridFS need semantic search and page citations. What text extraction/indexing steps are needed beyond storing bytes?

### Exercise 25
Object storage has incomplete multipart uploads and MongoDB has expired `pending` records. Design cleanup with grace periods and auditing.

### Exercise 26
Propose a `FileStorage` abstraction across embedded, GridFS, and object storage. Which capabilities must not be assumed identical?

## 43. Pre-Production Checklist

1. Profile P50/P95/max file sizes.
2. If embedding in BSON, calculate total document size and leave headroom below 16 MiB.
3. Separate metadata-only endpoints from byte-serving endpoints.
4. Use streaming for large files; avoid loading whole files onto the heap.
5. Identify CDN, Range, multipart, and direct-upload requirements.
6. Assess concurrent uploads and downloads.
7. Use stable business attachment IDs.
8. Store GridFS `fileId` or object bucket/key/version accurately.
9. Never treat `filename` as unique.
10. Model `pending`/`uploading`/`verifying`/`ready`/`deleting`/`failed` states.
11. Mark `ready` only after verification and scanning per policy.
12. Implement idempotent retries for network failures.
13. Enforce checksum and size validation per contract.
14. Replace content with new versions and atomic pointer switches.
15. Never delete shared files while live references remain.
16. Check tenant/owner/ACL permissions in the backend.
17. Use private object buckets and scoped signed URLs.
18. Configure HTTP headers, `Content-Disposition`, and `Range` properly.
19. Handle client cancellations and streaming backpressure.
20. Back up both metadata and bytes.
21. For GridFS, back up both `files` and `chunks` collections.
22. For object storage, maintain independent backup/retention and DR reconciliation.
23. Implement orphan cleanup with a grace period.
24. Enforce legal hold, retention, and deletion policies.
25. Account for disk, replication, index, backup, and egress costs.
26. Monitor p95 download latency and database impact.
27. Copy and verify during migrations before switching and cleaning up.
28. Keep storage backend details hidden from API clients.
29. If file-content search is needed, build separate extraction and indexing.
30. Maintain runbooks for upload timeouts, partial chunks, and dangling references.

## 44. Conclusion

**Embedding files in BSON documents** makes sense when files are small, read alongside business data, and benefit from single-document atomic updates. The 16 MiB limit applies to the **total BSON document**, not just the file's bytes.

**GridFS** is suitable when storing large files inside MongoDB and using streaming upload/download. It provides `fs.files` and `fs.chunks`, yet also creates many documents, increases database costs, and requires state management, retries, orphan-chunk handling, and proper deletion workflows.

**Object storage + MongoDB metadata** usually fits media and large files with high download volumes, CDNs, multipart uploads, Range requests, and independent lifecycles. The trade-off is coordinating consistency across two systems and managing object permissions.

Therefore, the choice depends not just on **file size**, but on **access patterns, atomicity, streaming/CDN needs, access control, versioning, backups, total cost, and failure recovery**. Regardless of backend, stable attachment IDs, byte verification, state management, and reconciliation prevent duplicates, lost files, and data leaks.

## References

- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Manual — Limits](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB GridFS Specifications](https://github.com/mongodb/specifications/tree/master/source/gridfs)
- [MongoDB Java Sync Driver — GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
