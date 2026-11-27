# Access Control, Backups, and Consistency Between Metadata and Content in MongoDB GridFS

## 1. The Problem: Storing Large Files Is Not Just Storing Bytes

Suppose a records management application lets users upload PDF contracts, images, videos, or data files. The application wants to store files in MongoDB using **GridFS** and provide these capabilities:

- Users can only download files they are authorized to view.
- A file belonging to tenant A must never appear in results for tenant B.
- Files not yet fully uploaded or not yet security-checked must never be published.
- Any backup/restore must preserve **file content, metadata, and business references**.
- After a network failure, application crash, restore, or delete operation, the system can detect **leftover chunks**, **missing chunks**, and **metadata pointing to wrong content**.
- Replacing a file or revoking permissions must not allow other users to read the wrong version.
- Integrity can be verified via length, chunk count, and checksums.

Example business record:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  filename: "contract-2026.pdf",
  gridFsFileId: ObjectId("65a000000000000000000001"),
  status: "READY",
  visibility: "PRIVATE"
}
~~~

The **`gridFsFileId`** field does not hold binary data: it is a foreign key linking to a GridFS file. If this metadata is restored without the GridFS data, the application will show a "file" in the UI that cannot be downloaded.

Conversely, if the file's chunks were backed up without the file descriptor document, millions of bytes still occupy disk space while the application finds no valid file.

**The focus of this lesson** covers three closely related yet distinct problems:

1. **Access control:** Who can upload, read, edit metadata, and delete files?
2. **Backup and restore:** How do you preserve binary data, metadata, and references at a recoverable state?
3. **Consistency:** How do you guarantee a published file has complete chunks, accurate content, and valid business metadata?

### 1.1. Expected Outcomes

After this lesson, you will be able to:

- Explain the roles of **`fs.files`** and **`fs.chunks`**, and bucket-prefixed collections.
- Distinguish **MongoDB RBAC** at the database/collection level from **per-file authorization** in the application.
- Design safe workflows for upload, verification, publish, download, replacement, and deletion.
- Understand why a GridFS file lacks multi-document atomicity compared to a single MongoDB document.
- Design **point-in-time consistent backups** and verified restore scenarios.
- Detect orphan chunks, missing chunks, mismatched lengths, duplicate sequences, and checksum mismatches.
- Write examples with **`mongosh`, MongoDB Java Sync Driver, and Spring Data MongoDB**.
- Build incident runbooks and periodic checks before serving production files.

## 2. GridFS Structure: One File Is Multiple Documents

MongoDB caps a regular BSON document at **16 MiB**. GridFS splits file content into multiple small blocks to store and stream instead of placing all bytes into a single document.

A **GridFS bucket** consists of two collections:

| Collection | Function |
|---|---|
| **`fs.files`** | One document describing each successfully uploaded file: name, length, chunk size, upload date, and metadata. |
| **`fs.chunks`** | Documents holding the file's binary data, each document representing one chunk. |

The default prefix is **`fs`**. If you create a bucket named **`assets`**, the two collections are **`assets.files`** and **`assets.chunks`**.

~~~text
GridFS bucket "assets"

+----------------------------+
| assets.files               |
| _id: F-100                 |
| filename: contract.pdf     |
| length: 600000             |
| chunkSize: 261120          |
| metadata: {...}            |
+-------------+--------------+
              |
              | chunks.files_id = files._id
              v
+---------------------------------------------------+
| assets.chunks                                     |
| files_id=F-100, n=0, data=Binary(261120 bytes)    |
| files_id=F-100, n=1, data=Binary(261120 bytes)    |
| files_id=F-100, n=2, data=Binary(77760 bytes)     |
+---------------------------------------------------+

File content = chunk 0 + chunk 1 + chunk 2
               in ascending order of n.
~~~

### 2.1. Documents in `assets.files`

Compact example:

~~~javascript
{
  _id: ObjectId("65a000000000000000000001"),
  length: NumberLong(600000),
  chunkSize: 261120,
  uploadDate: ISODate("2026-08-12T09:00:00Z"),
  filename: "contract-2026.pdf",
  metadata: {
    tenantId: "tenant-a",
    ownerId: "user-21",
    status: "SCANNING",
    mediaType: "application/pdf",
    applicationFileId: "DOC-100"
  }
}
~~~

Core GridFS fields:

| Field | Meaning |
|---|---|
| **`_id`** | GridFS file ID, referenced by chunks via `files_id`. |
| **`length`** | Total byte length of the file content. |
| **`chunkSize`** | Maximum size of each chunk except the last chunk. |
| **`uploadDate`** | Timestamp when the upload was recorded by GridFS. |
| **`filename`** | Filename used for lookup/display as needed. |
| **`metadata`** | Custom data, e.g., `tenantId`, `ownerId`, status, checksum, or document type. |

GridFS may include additional fields depending on driver and version. Do not rely on the legacy **`md5`** field as a modern content-protection mechanism; design a dedicated **SHA-256** checksum when integrity verification is needed.

### 2.2. Documents in `assets.chunks`

~~~javascript
{
  _id: ObjectId("65a000000000000000000002"),
  files_id: ObjectId("65a000000000000000000001"),
  n: 0,
  data: BinData(0, "...")
}
~~~

| Field | Meaning |
|---|---|
| **`_id`** | Unique ID of the chunk document itself. |
| **`files_id`** | Points to `_id` of the file in `assets.files`. |
| **`n`** | Chunk order, starting at 0 and increasing contiguously. |
| **`data`** | BSON binary data. |

**Order `n`** is essential. Reassembling chunks by `_id` order or raw query return order is not a valid way to reconstruct a file.

### 2.3. Chunk Size and Verification Formula

The typical default size is **255 KiB = 261,120 bytes**, adjustable at upload time.

With:

~~~text
length = 600000 bytes
chunkSize = 261120 bytes
~~~

expected chunk count:

~~~text
expectedChunks = ceil(length / chunkSize)
               = ceil(600000 / 261120)
               = 3
~~~

Sizes:

~~~text
chunk 0: 261120 bytes
chunk 1: 261120 bytes
chunk 2:  77760 bytes
total:   600000 bytes
~~~

When a file has **`length=0`**, the expected chunk count is 0; the document in `files` still describes a valid empty file. Applications can reject empty files per business policy, but should not treat every empty file as corrupted.

### 2.4. Important Indexes

Per the GridFS specification, standard indexes are:

~~~javascript
db.getCollection("assets.files").createIndex(
  { filename: 1, uploadDate: 1 }
);

db.getCollection("assets.chunks").createIndex(
  { files_id: 1, n: 1 },
  { unique: true }
);
~~~

The **`{files_id:1,n:1}` unique** index prevents any single file from having two chunks with the same sequence number `n`. However, **a unique index does not guarantee all chunks exist**: `n=0, 2` can exist while `n=1` is missing.

Drivers/buckets can create the required GridFS indexes when initializing/checking a bucket. In production, **pre-provision indexes** using an appropriate admin account so runtime accounts do not need index-creation privileges.

### 2.5. Two Collections Are Not One Document

MongoDB guarantees atomicity for a **single document write**. A GridFS file can span tens, thousands, or millions of documents, so you cannot assume uploading or deleting an entire file is an atomic write just because you are using MongoDB.

This directly impacts **read authorization, backup/restore, and failure recovery**.

## 3. Three Layers of Consistency to Distinguish

In a real system, file information typically appears across three layers:

~~~text
             Business application
         +-------------------------+
         | asset_catalog           |
         | assetId, tenant, owner  |
         | status, gridFsFileId    |
         +-----------+-------------+
                     |
                     v
               GridFS metadata
         +-------------------------+
         | assets.files            |
         | _id, length, filename   |
         | uploadDate, metadata    |
         +-----------+-------------+
                     |
                     v
               GridFS content
         +-------------------------+
         | assets.chunks           |
         | files_id, n, data       |
         +-------------------------+
~~~

### 3.1. Consistency Between `files` and `chunks`

A file can only be read intact when:

- The **`assets.files`** document is valid.
- Exactly the expected number of chunks exist.
- Chunks have sequence `n` **`0..N-1`** without gaps or duplicates.
- Total chunk bytes equal **`length`**.
- Actual content matches the stored/trusted checksum if present.

Having **`assets.files`** alone does not prove the file content has all its bytes.

### 3.2. Consistency Between GridFS and the Business Catalog

A business record can reference a file:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  gridFsFileId: ObjectId("65a000000000000000000001"),
  status: "READY"
}
~~~

Desired invariants:

1. A **`READY`** record must point to an existing, readable GridFS file.
2. GridFS metadata for **`tenantId`** must match the business record's tenant.
3. Only one active file version is published for an asset ID at a time per business rules.
4. Read permissions on the business record must be checked before calling GridFS download.
5. Chunks of a file still used by a business record must never be deleted.

### 3.3. Consistency Between Backups and Application State

If **`asset_catalog`** is restored to time T2 while GridFS is restored to T1:

~~~text
T1: GridFS has file F1
T2: asset_catalog already points to file F2

Restore:
  asset_catalog at T2 -> points to F2
  GridFS at T1        -> F2 does not exist
~~~

Result: syntactically valid business metadata whose **content is missing**.

This is why backups must capture **a single consistent state across all related collections**, not merely copy binary files.

## 4. Upload, Download, and Delete Lifecycle: Atomicity Limits

### 4.1. Uploads Typically Involve Multiple Writes

In principle, the GridFS driver writes binary data as documents in **`assets.chunks`**, then writes the descriptor document into **`assets.files`** when the upload finishes.

~~~text
Upload contract.pdf
       |
       v
Write chunk n=0
       |
       v
Write chunk n=1
       |
       v
Write chunk n=2
       |
       v
Create assets.files document
       |
       v
GridFS upload successful
~~~

From an API standpoint:

- When the driver reports upload success, the application can use the returned file ID to access the file.
- Before the document in **`assets.files`** is written, already-written chunks exist without a complete listed file.
- If an upload fails mid-way, chunks without an attached file document can remain.
- If the network drops right after the server receives a write, the client's view of the outcome is uncertain; never assume the server rolled everything back.

### 4.2. Do Not Rely on Multi-Document Transactions for Entire GridFS Uploads

**GridFS does not support multi-document transactions** in a way that turns a file upload into an atomic commit of all **`files`** and **`chunks`**. Do not write:

~~~text
startTransaction()
  write all chunks
  write file document
commitTransaction()

=> guaranteed everything is protected by GridFS as an atomic write
~~~

That is **not** a guarantee GridFS provides.

If the business needs atomicity when *publishing* a file, separate the steps:

1. Upload all bytes into GridFS.
2. Verify content and required metadata.
3. Update **one business document** or publication status using a single atomic update.
4. Allow downloads only for files in the **`READY`** state.

Publication can be done via a **single-document atomic update**, even though writing the bytes beforehand spanned many documents.

### 4.3. Incomplete Upload Scenario

~~~text
T0: Start uploading F100
T1: Write chunk 0
T2: Write chunk 1
T3: Network disconnect before writing chunk 2
T4: No assets.files document for F100

Result:
  Chunks exist with files_id=F100
  No files._id=F100
~~~

Those chunks are **orphan candidates**, yet should not be deleted the instant they are spotted. While another normal upload is running, chunks without a `files` record also exist temporarily. You need **upload leases, grace periods, or reconciliation workflows** to distinguish them.

### 4.4. A `files` Document Is Not Proof of Checksum

If **`assets.files.length = 600000`**, this metadata records the expected length; it does not prove all binary data matches the intended version.

Two files with the same length can still have different contents. To verify integrity, compare the **SHA-256 of re-read bytes** against a digest generated from a trusted source.

### 4.5. Deleting a File Also Involves Multiple Operations

GridFS delete must remove both the **file document** and its associated **chunk documents**. Because multiple documents are involved, do not treat delete as a single-step atomic wipe of all bytes and metadata.

If the process stops partway through, you can end up with:

- File document gone, chunks still remaining.
- Some chunks gone while the delete operation did not finish.
- Business catalog still pointing to a file whose GridFS content was deleted.

Never fix GridFS data by deleting only **`assets.files`** or only **`assets.chunks`** if you want a consistent lifecycle.

### 4.6. Downloads Can Race with Deletes

~~~text
Reader: checks file F100 is READY
                      |
                      v
Cleaner: starts deleting F100
                      |
                      v
Reader: reads chunk n=2 -> already gone
~~~

Checking permissions before download is necessary, yet **does not lock all bytes** against concurrent deletion.

For critical files or long downloads, use **lifecycle states, reference counting/leases, or grace periods before deleting bytes**; also prepare stream error handling if a file changes while being read.

### 4.7. A New Version Should Have a New File ID

When a user replaces a contract:

~~~text
Old file F100 (READY)
       |
       v
Upload new file F101
       |
       v
Validate F101
       |
       v
Atomic update asset_catalog.currentFileId = F101
       |
       v
Schedule delete F100 after grace period
~~~

Never overwrite the bytes of F100's chunks in place. Creating a new file ID enables clean rollback/publishing and reduces the risk of readers receiving mixed content.

## 5. Layers of Access Control

A GridFS application can have multiple layers of defense:

~~~text
HTTP / API caller
      |
      v
Authentication
      |
      v
Application authorization
 (tenant, owner, role, sharing policy)
      |
      v
MongoDB service account
      |
      v
MongoDB RBAC
 (database, collection, actions)
      |
      v
GridFS files/chunks
~~~

**Never skip application authorization** simply because MongoDB has username/password authentication enabled.

### 5.1. MongoDB RBAC Operates at the Collection Level, Not Per File

MongoDB RBAC can grant privileges:

- **`find`** on **`assets.files`** and **`assets.chunks`**.
- **`insert`** to write new documents.
- **`update`** to modify permitted metadata.
- **`remove`** to delete documents.
- **`createIndex`**, **`listIndexes`** for index setup/inspection.

However, two files in the same `assets.files`/`assets.chunks` share the **same collection-level permission scope**. A DB user with read access to both collections can query data across many files, not just the file the app intends for them to view.

Therefore, never issue **direct MongoDB credentials to individual end users** expecting GridFS to enforce file-level ACLs itself.

### 5.2. Typical Application Roles Needed

| Role | What It Can Do | What Must Be Restricted |
|---|---|---|
| **Uploader** | Upload new files belonging to its tenant. | File size/type, quota, `ownerId`, idempotency. |
| **Reader** | Download published and shared files. | Tenant, owner, `READY` state, access expiration. |
| **Editor** | Update business metadata or submit new versions. | Permitted fields only, optimistic concurrency. |
| **Deleter** | Request deletion/revocation of files. | Must check permissions, retention/legal hold. |
| **Security scanner** | Read bytes in unpublished staging, mark scan results. | Cannot alter owner/tenant. |
| **Backup operator** | Back up/restore required collections. | Elevated privileges and controlled procedures. |

Not every application role needs its own MongoDB DB user; you can run a least-privilege application service account and authenticate/authorize every request at the service layer.

### 5.3. Three Distinct Concepts

- **Authentication:** who is calling the API?
- **Authorization:** is that caller permitted to view/modify this file?
- **Integrity:** are the bytes read identical to the uploaded and verified bytes?

Succeeding in one step does not automatically guarantee the other two.

### 5.4. A File ID Is Not an Access Permission

A dangerous endpoint:

~~~text
GET /files/65a000000000000000000001

Server:
  bucket.downloadToStream(fileId, response)
~~~

Without checking tenant, owner, or sharing policies, a user only needs to know or guess a file ID to read someone else's document. An unguessable `ObjectId` is **not** an access control mechanism.

A proper API checks permissions first:

~~~text
GET /assets/DOC-100/download
   |
   v
Authenticate caller
   |
   v
Find business asset by assetId + tenant policy
   |
   v
Assert READY and access granted
   |
   v
Lookup GridFS file ID from verified asset
   |
   v
Stream bytes with controlled response headers
~~~

### 5.5. Authorize via Business Record Rather Than Filename

Filenames can collide:

~~~text
tenant-a/contract.pdf
tenant-b/contract.pdf
tenant-a/contract.pdf (version 2)
~~~

Never use **`filename`** as the sole authorization key. Use a tenant-scoped **business asset ID** and an exact **GridFS file ID** for the content version.

### 5.6. Protecting Permissions When Multiple Users Share

A file can have:

~~~javascript
{
  ownerId: "user-21",
  visibility: "TEAM",
  allowedUserIds: ["user-21", "user-35"],
  tenantId: "tenant-a"
}
~~~

Never allow clients to arbitrarily set **`allowedUserIds`** on a file owned by someone else. Verify the caller is allowed to change sharing policies and record audit events for permission grants and revocations.

## 6. MongoDB RBAC for Both Collections of a GridFS Bucket

### 6.1. Buckets and Real Namespaces

Example setup:

~~~text
Database:  gridfs_security_lab
Bucket:    assets

Collections:
  gridfs_security_lab.assets.files
  gridfs_security_lab.assets.chunks
~~~

In `mongosh`:

~~~javascript
use gridfs_security_lab

db.getCollection("assets.files").getIndexes();
db.getCollection("assets.chunks").getIndexes();
~~~

Do not mistake **`db.assets.files`** syntax for a nested JavaScript property; the explicit syntax when names contain dots is **`db.getCollection("assets.files")`**.

### 6.2. Custom Role for Reading GridFS

An example role for a read-only file service:

~~~javascript
use gridfs_security_lab

db.createRole({
  role: "gridfsAssetReader",
  privileges: [
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.files"
      },
      actions: ["find"]
    },
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.chunks"
      },
      actions: ["find"]
    }
  ],
  roles: []
});
~~~

This role describes **data-read privileges**, which may not satisfy index initialization/verification checks in all drivers. If a driver inspects indexes on a new bucket or missing collection, **pre-create collections and indexes** with a provisioning account instead of granting `createIndex` to readers. Verify behavior for your specific driver and version.

### 6.3. Uploads Require Write Privileges on the Right Collections

An upload service may need:

- **`insert`** into `assets.chunks`.
- **`insert`** into `assets.files` once upload finishes.
- **`find`** as needed for lookups/checks.
- **`update`** on `assets.files` if updating custom metadata/status.
- **`remove`** when cleaning up failed uploads or deleting files; grant only if workflows genuinely require it.

Example role for an upload service capable of authorized file cleanup:

~~~javascript
db.createRole({
  role: "gridfsAssetWriter",
  privileges: [
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.files"
      },
      actions: ["find", "insert", "update", "remove"]
    },
    {
      resource: {
        db: "gridfs_security_lab",
        collection: "assets.chunks"
      },
      actions: ["find", "insert", "remove"]
    }
  ],
  roles: []
});
~~~

**The deletion action name in MongoDB privileges is `remove`**, not an arbitrary action named `delete`. Restrict which users receive this writer role: anyone holding it can delete any file in the bucket if accessing MongoDB directly.

### 6.4. Separate Index Provisioning Privileges from Runtime

A provisioning account may need:

~~~text
createCollection, createIndex, listIndexes
~~~

and matching privileges on the namespace/DB per MongoDB's privilege model. Upload/download applications should not hold privileges to create or drop indexes on startup.

A sound workflow:

1. DBA/deployment migrations create the two collections and required indexes.
2. Verify the unique index on **`assets.chunks(files_id,n)`**.
3. Verify indexes serving metadata/tenant queries.
4. Run services using credentials with minimal data privileges.

### 6.5. Do Not Grant Direct Read Access When Per-File ACLs Are Required

If tenant A and tenant B both store data in **`assets.files`/`chunks`** of one bucket, a MongoDB role granting `find` on both collections **does not isolate each user to a single tenant**.

Two architectures:

| Architecture | Protection Mechanism | Trade-Offs |
|---|---|---|
| **Shared bucket** | MongoDB app service credentials + API tenant/owner authorization. | Simpler schema, but backend must enforce authorization strictly. |
| **Per-tenant bucket/database** | Collection- or database-level RBAC. | Stronger namespace isolation, but more collections/indexes and operational overhead. |

If third parties connect directly to MongoDB, you generally need **namespace isolation** or a genuine DB-level enforcement mechanism. Never expect a `metadata.tenantId` field to be filtered automatically by MongoDB RBAC.

### 6.6. Backup/Restore Privileges Differ from Upload Privileges

An account running **`mongodump`/`mongorestore`** requires backup/restore privileges aligned with MongoDB Database Tools and deployment topology. Never reuse an application service account meant only for GridFS `find`/`insert`, and never grant production restore privileges to API servers.

Distinguish:

- **Application runtime credential:** least privilege.
- **Migration/provisioning credential:** index management.
- **Backup credential:** read all namespaces requiring backup.
- **Restore credential:** used only within controlled operational procedures.

### 6.7. Auditing Permission Changes

Updating owner, visibility, allowed user lists, retention, or legal holds can impact security far more than renaming a file.

Applications should record:

~~~text
who
when
tenantId
assetId
action (GRANT/REVOKE/DELETE/REPLACE)
oldPolicyVersion
newPolicyVersion
requestId
~~~

Do not leave audit records solely in short-lived logs when compliance requires persistence. Define retention, encryption, and access controls for audit data separately.

## 7. Which Metadata Belongs in GridFS vs. Business Collections?

GridFS allows custom fields in **`assets.files.metadata`**:

~~~javascript
{
  metadata: {
    tenantId: "tenant-a",
    ownerId: "user-21",
    mediaType: "application/pdf",
    status: "SCANNING",
    sha256: "...",
    applicationFileId: "DOC-100"
  }
}
~~~

However, an application may also need **`asset_catalog`**:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  currentFileId: ObjectId("65a000000000000000000001"),
  status: "READY",
  displayName: "Lease Agreement",
  visibility: "PRIVATE",
  policyVersion: NumberLong(5),
  version: NumberLong(3),
  createdAt: ISODate("2026-08-12T09:00:00Z"),
  updatedAt: ISODate("2026-08-12T09:05:00Z")
}
~~~

### 7.1. Suggested Separation of Responsibilities

| Storage Location | Appropriate Information |
|---|---|
| **`assets.files`** | `_id`, `filename`, `length`, `chunkSize`, `uploadDate`, metadata for identifying and verifying the file. |
| **`assets.chunks`** | Binary chunks; do not embed business ACLs inside each chunk. |
| **`asset_catalog`** | Publication state, `currentFileId`, owner, ACLs, version, retention, audit linkage. |
| **Upload job/lease** | `requestId`, job status, start/end timestamps, errors, cleanup expiration. |

**Avoid keeping multiple copies of the same access permission without defining a single source of truth.** If both `asset_catalog` and `assets.files` store `ownerId`, define which field is authoritative and how discrepancies are reconciled.

### 7.2. Metadata in GridFS Does Not Guarantee Integrity by Itself

For example:

~~~javascript
{
  metadata: {
    sha256: "abc...",
    mediaType: "application/pdf"
  }
}
~~~

These are just data fields. Anyone permitted to update `assets.files.metadata` can alter them; they are not cryptographic signatures.

If tamper-resistance against malicious modifications is needed:

- Restrict metadata update privileges.
- Store digests in a trusted domain, optionally using digital signatures/HMACs.
- Use immutable versioning or append-only audit logs for critical changes.
- Verify checksums against actually read bytes, never by comparing metadata against itself.

### 7.3. `filename` Is Not a Filesystem Path

A GridFS `filename` could be:

~~~text
../../private/secret.pdf
~~~

In GridFS, this is just a string; it does not mean writing a file to disk at that path is safe.

When downloading or exporting to a local filesystem:

1. Never concatenate user-supplied `filename` directly into a disk output path.
2. Use server-generated names or sanitize/normalize thoroughly.
3. Prevent path traversal, reserved names, and collisions.
4. Keep the original filename in metadata for display when needed.

### 7.4. MIME Type and `mediaType`

A user can upload an executable with the header:

~~~text
Content-Type: application/pdf
~~~

Metadata containing `mediaType="application/pdf"` does not prove the bytes are a valid PDF. If the application enforces file-type policies:

- Check magic bytes and use an appropriate parser.
- Scan for malware when required.
- Limit file sizes and guard against compression bombs.
- Never preview untrusted content under a privileged origin.
- Default to **`Content-Disposition: attachment`** when inline browser rendering is undesirable.

### 7.5. Define the `READY` State Explicitly

Do not treat:

~~~text
assets.files document exists
~~~

as the sole condition for publishing a file. `READY` can require:

~~~text
GridFS upload completed
AND asset linked to verified tenant
AND size limit satisfied
AND checksum verified
AND content scan passed
AND business policy permits publish
~~~

Each condition must have a clear data source and failure/retry state.

## 8. State Machine for Uploading and Publishing Files

A workflow can use:

~~~text
NEW
  |
  v
UPLOADING
  |       \
  |        +--> FAILED / CANCELLED
  v
SCANNING
  |       \
  |        +--> REJECTED
  v
READY
  |
  +--> REPLACING --> READY(newFileId)
  |
  +--> DELETE_REQUESTED
          |
          v
       DELETING
          |
          v
       DELETED
~~~

These state names are application-defined, not mandatory values of the GridFS API.

### 8.1. Starting an Upload

The application creates a catalog record:

~~~javascript
{
  _id: "DOC-100",
  tenantId: "tenant-a",
  ownerId: "user-21",
  uploadRequestId: "REQ-100",
  status: "UPLOADING",
  currentFileId: null,
  createdAt: ISODate("2026-08-12T09:00:00Z")
}
~~~

Place an appropriate unique index on **`tenantId + uploadRequestId`** when the API uses idempotency keys.

### 8.2. Writing Bytes with GridFS

Write the file through the driver, setting metadata:

~~~javascript
{
  tenantId: "tenant-a",
  applicationFileId: "DOC-100",
  status: "SCANNING",
  uploadRequestId: "REQ-100"
}
~~~

Only after the **upload stream closes successfully** should the GridFS file be considered complete per driver API. If an error occurs midway, never mark the catalog `READY`.

### 8.3. Verifying Before Publishing

After upload succeeds:

1. Record `fileId`, `length`, and metadata.
2. Verify file size and checksum.
3. If needed, read bytes to run antivirus/MIME checks.
4. Verify owner/tenant from the authenticated context.
5. Update the catalog to **`SCANNING`** or **`READY`** per business rules.

Never set status `READY` in upload options upfront while the file still awaits scanning or approval.

### 8.4. Atomic Publish via a Conditional Update

~~~javascript
db.asset_catalog.updateOne(
  {
    _id: "DOC-100",
    tenantId: "tenant-a",
    status: "SCANNING",
    uploadRequestId: "REQ-100"
  },
  {
    $set: {
      currentFileId: ObjectId("65a000000000000000000001"),
      status: "READY",
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
~~~

The filter conditions prevent an older upload worker from accidentally publishing a file if the catalog already moved to another request/version. Check **`matchedCount`/`modifiedCount`** to verify the update succeeded as expected.

**An `updateOne` on a single catalog document is atomic at the document level**, though it does not turn the preceding GridFS upload and validation into a multi-document atomic transaction.

### 8.5. Do Not Maintain Two Conflicting Sources of `READY`

If:

~~~text
asset_catalog.status = READY
assets.files.metadata.status = SCANNING
~~~

the service must know which state is authoritative. One approach:

- **`asset_catalog.status`** is the authoritative publication state.
- **`assets.files.metadata.status`** is auxiliary information for scanners/repair tools.
- Downloads always check the catalog and resolve the corresponding GridFS file ID.

If you choose to use `assets.files.metadata.status` alone as `READY`, apply the same rigor to security, validation, and conditional updates. Never mix two conflicting conventions across endpoints.

### 8.6. Failure After Upload Yet Before Publish

~~~text
GridFS upload F100 success
  |
  X app crash before catalog READY
~~~

Upon restart, file F100 may exist while the catalog remains **`UPLOADING`/`SCANNING`**. A recovery worker should look up by **`uploadRequestId`/`applicationFileId`**, verify integrity, and decide whether to publish or clean up based on state—never blindly re-uploading and creating duplicates.

## 9. Safe Upload Workflow and Error Handling

### 9.1. Steps of an Upload Endpoint

~~~text
POST /assets
     |
     v
Authenticate and authorize uploader
     |
     v
Validate tenant, quota, length, type, requestId
     |
     v
Create catalog status=UPLOADING
     |
     v
Stream request bytes into GridFS
     |
     v
Close upload successfully -> get GridFS file ID
     |
     v
Verify content: size / SHA-256 / malware scan
     |
     v
Conditionally publish catalog status=READY
     |
     v
Return business assetId and version
~~~

If upload fails at any step, record the failure state and let a worker **decide cleanup/retry** based on preconditions. Never return a success response merely upon creating the initial catalog record.

### 9.2. Enforcing Size Limits While Reading the Stream

Suppose a user sends:

~~~http
Content-Length: 100000
~~~

This header may be absent or fail to reflect the actual bytes received. The API should **count bytes directly on the input stream** and abort if the limit is exceeded, rather than trusting `Content-Length` alone.

For example:

~~~text
maximumAllowedBytes = 50 MiB
count bytes while reading
if readBytes > maximumAllowedBytes:
    cancel/abort upload
    mark failed
    schedule safe cleanup
~~~

GridFS handles files larger than the BSON document limit; **it does not mean you should allow unbounded uploads**.

### 9.3. SHA-256 at Source and Storage

An integrity check:

~~~text
SHA256(input bytes) = H1
    |
    v
GridFS stores bytes
    |
    v
SHA256(downloaded stored bytes) = H2

H1 == H2 -> stored data matches source by SHA-256
~~~

Distinguish:

- **H1** computed by the backend from the input stream it trusts.
- **H2** computed from bytes read back out of GridFS.
- Merely copying a client-supplied SHA-256 into metadata is a **client claim**, not a backend-verified result.

The digest can live in `asset_catalog` or `metadata`, but clarify the **source of truth** and who is authorized to update it.

### 9.4. Validating Media Types

A file named **`report.pdf`** does not guarantee the bytes are a PDF. Validation steps can include:

1. Check the extension against an allowlist.
2. Perform content sniffing / magic-byte inspection.
3. Parse or scan with controlled tools.
4. Run virus/antimalware scanning per product requirements.
5. Mark the file **`REJECTED`** if validation fails.

Never execute macros, scripts, or embedded code from an untrusted file while scanning its contents.

### 9.5. Idempotency on Client HTTP Retries

Suppose on the first attempt:

~~~text
REQ-100 -> upload F100 succeeded
         -> HTTP response lost
~~~

The client resends the same request:

~~~text
REQ-100 -> retry
~~~

If the backend always generates a fresh F101, two files will exist for one business intent. A **unique request key** on `asset_catalog` helps:

- Detect that the request already started.
- If `READY`, return the confirmed result.
- If still `UPLOADING`/`SCANNING`, return a pending status or resume the workflow safely.
- If `FAILED`, apply a versioned/leased retry policy.

Never treat a repeated HTTP request as a brand-new file when the caller supplied an idempotency key.

### 9.6. Retrying a GridFS Upload Does Not Default to Resuming from the Last Chunk

If an upload drops at chunk 7, do not assume calling `uploadFromStream` again will automatically resume from chunk 8. Unless the application implements an explicit resumable protocol supported by the driver/API, **starting a GridFS upload from scratch creates a new file version**.

Distinguish:

- **HTTP client retry**.
- **Driver retryable writes** for eligible single operations.
- **Application-level resumable upload protocol**.

These three mechanisms have different scopes and semantics.

### 9.7. Timeout When the File Finished Writing Yet the Client Never Received the ID

Scenario:

~~~text
Driver sends upload completion step
Server already wrote assets.files
Network drops the response
Caller receives exception/timeout
~~~

Never assert the file does not exist just because the client saw an error. If the workflow uses a **pre-allocated `fileId`, `uploadRequestId`, or `applicationFileId`**, recovery can query for the current state.

During reconciliation, never let a client alter `tenantId` or `ownerId` to claim an unpublished file.

### 9.8. Never Hold the Whole File in RAM

GridFS provides chunked streaming. Avoid:

~~~text
read entire 2 GB file into byte[]
bucket.uploadFromStream(new ByteArrayInputStream(...))
~~~

That approach can exhaust the Java heap. With real input streams, manage buffering, rate limits, cancellation, and streaming checksums.

## 10. Downloading with the Right Permissions, File, and Version

### 10.1. Check Business ACLs Before Fetching Bytes

An illustrative `mongosh` pattern:

~~~javascript
use gridfs_security_lab

const asset = db.asset_catalog.findOne({
  _id: "DOC-100",
  tenantId: "tenant-a",
  status: "READY"
});

if (!asset) {
  throw new Error("Asset not found or not available");
}

const file = db.getCollection("assets.files").findOne({
  _id: asset.currentFileId,
  "metadata.tenantId": asset.tenantId,
  "metadata.applicationFileId": asset._id
});

if (!file) {
  throw new Error("GridFS file metadata mismatch");
}
~~~

This is **only the metadata lookup step in `mongosh`**, without downloading binary data. In real applications, `tenantId` must come from the **authenticated context**, and owner/sharing policies must be checked thoroughly.

### 10.2. Use Business Asset IDs Rather Than GridFS IDs in Public APIs

Prefer designing:

~~~http
GET /assets/DOC-100/content
~~~

instead of exposing an endpoint that downloads any GridFS file ID without permission lookups. Using a business ID is not a security measure by itself; it simply provides a clean chokepoint where the backend enforces authorization.

### 10.3. Preventing IDOR

**Insecure Direct Object Reference (IDOR)** occurs when a client alters an object ID in a request and accesses someone else's resource.

Scenario:

~~~text
User A has access to DOC-100.
User B has access to DOC-101.

User A tries GET /assets/DOC-101/content.
~~~

If the service queries solely by `_id` without checking tenant/owner/sharing rules, User A can download User B's file.

Checks must rely on the **authenticated user and resource policy**, never on obscure paths or simple ID encoding.

### 10.4. Do Not Return Unnecessary Sensitive Metadata

A file document might contain:

~~~javascript
{
  metadata: {
    tenantId: "tenant-a",
    ownerId: "user-21",
    securityLabel: "CONFIDENTIAL",
    internalWorkflowId: "WF-742",
    sha256: "..."
  }
}
~~~

A download API typically only needs to return:

~~~text
Content-Type
Content-Length
Content-Disposition
ETag/version if applicable
binary stream
~~~

Never expose the entire `assets.files.metadata` as public JSON when it contains internal IDs or security labels.

### 10.5. Headers and Browser Safety

Headers to consider:

~~~http
Content-Type: application/pdf
Content-Disposition: attachment; filename="contract.pdf"
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
~~~

These are illustrative examples. Set `Cache-Control` according to sensitivity and re-download requirements; generate `Content-Disposition` using safe escaping/encoding libraries to prevent header injection.

If previewing untrusted documents, consider an isolated origin/CSP and safe content-processing tools.

### 10.6. Supporting Range Requests

Large videos or PDFs may require:

~~~http
Range: bytes=100000-199999
~~~

GridFS supports chunked reads and seek/read APIs depending on the driver. However, **HTTP Range is not enabled automatically just because data is stored in GridFS**.

The backend must:

- Parse and validate byte ranges.
- Use appropriate read/seek APIs.
- Return accurate `Content-Range` and `206`/`416` status codes.
- Authorize every request before serving bytes.
- Control database I/O spikes caused by many concurrent range requests.

### 10.7. Permissions Revoked Mid-Download

If a multi-GB file is actively streaming when an admin revokes access:

~~~text
T1: API verifies READY and read permission
T2: Stream begins
T3: Admin revokes permission
T4: Stream may still be sending
~~~

A single permission check at request start does not automatically terminate an already-open stream. Security policy must define whether revocations apply:

- **To new requests only**; or
- **Immediately to active streams**, requiring advanced cancellation/lease/revocation mechanisms.

Never promise "instant revocation" unless the system actively aborts in-flight streams.

## 11. Replacing Versions, Deletion, and Retention

### 11.1. Never Modify Chunks in Place to Replace a File

A safer replacement flow:

~~~text
Asset DOC-100
  currentFileId = F100
         |
         v
Upload F101, verify, scan
         |
         v
Atomic compare-and-swap:
  currentFileId F100 -> F101
  version 3 -> 4
         |
         v
New requests read F101
Old F100 retained during grace/reader lease
         |
         v
Asynchronous cleanup of F100
~~~

Never update `metadata.length` and overwrite F100's chunks to "turn" it into F101.

### 11.2. Optimistic Concurrency on the Catalog

~~~javascript
const expectedVersion = NumberLong(3);

const result = db.asset_catalog.updateOne(
  {
    _id: "DOC-100",
    tenantId: "tenant-a",
    status: "READY",
    version: expectedVersion
  },
  {
    $set: {
      currentFileId: ObjectId("65a000000000000000000009"),
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Asset was modified concurrently");
}
~~~

This prevents two users from updating the same catalog version where the second user silently overwrites the first user's changes.

### 11.3. Deletion Begins with a State Transition

For sensitive files, start with:

~~~javascript
db.asset_catalog.updateOne(
  {
    _id: "DOC-100",
    tenantId: "tenant-a",
    status: "READY"
  },
  {
    $set: {
      status: "DELETE_REQUESTED",
      updatedAt: new Date()
    }
  }
);
~~~

Once status is no longer `READY`, APIs must reject **new downloads**. Only then does a worker safely delete the bytes, update status upon success, and log an audit record.

### 11.4. Do Not Delete Still-Referenced Files

A `fileId` may still be referenced by:

- Current active asset.
- Required historical version.
- A legal hold.
- An unfinished processing job.
- An active download stream.
- A backup/restore workflow.

Before deleting, check business reference and retention policies. Never bulk-delete file IDs solely because they are not the `currentFileId` of a single document.

### 11.5. Idempotent Cleanup

A deletion worker might crash after removing the GridFS file yet before marking the catalog `DELETED`. Retries should:

1. Find catalog entries in `DELETING` state.
2. Check if the GridFS file still exists.
3. If present, delete it by `fileId`.
4. If already gone, verify no leftover chunks exist via a dedicated check.
5. Mark `DELETED` once all criteria are met.

Do not treat a "file not found" exception as an unrecoverable failure, nor treat it as proof that all chunks are gone.

### 11.6. Privacy Deletion and Backups

When a user requests data deletion:

~~~text
Delete live copy
  !=
Immediately delete all backups/snapshots
~~~

Backup retention, archives, and statutory/contractual deletion policies must be defined upfront. **Encryption key lifecycle / crypto-shredding** can be applied in suitable architectures, though that requires designing key management from day one.

Never claim data has been erased everywhere if older backups can still contain the file.

## 12. Backing Up GridFS: Do Not Back Up `assets.chunks` Alone

A GridFS backup intended for recovery must capture:

1. **`assets.files`**: file descriptor documents, `_id`, `length`, `chunkSize`, `filename`, and `metadata`.
2. **`assets.chunks`**: binary chunks with `files_id`, `n`, and `data`.
3. **`asset_catalog`** or business collections referencing the files.
4. Indexes and configuration needed to restore permissions, validation, or application schemas.
5. A **consistent point in time** across all related parts.

### 12.1. Common Backup Approaches

| Backup Method | Strengths | Risks to Address |
|---|---|---|
| **Managed snapshot / point-in-time backup** | Supports topology-consistent backups when provided by the platform. | Requires retention planning, restore testing, and understanding snapshot scope. |
| **`mongodump` / `mongorestore`** | Backs up/restores BSON and metadata at the database level. | Must handle snapshot consistency under concurrent writes. |
| **Replica set `mongodump --oplog`** | Captures/replays oplog to produce a consistent dump under supported conditions. | Cannot be applied arbitrarily to sharded clusters or single-collection dumps. |
| **Direct filesystem file copy** | Can be part of storage-level snapshot workflows. | Hot copies without consistency mechanisms can be corrupted; requires proper snapshot/lock/coordination. |
| **`mongofiles get` per file** | Handy for exporting a few files to inspect or transfer. | Not a substitute for full backups; does not preserve all metadata/indexes/ACLs. |
| **`mongoexport` JSON/CSV** | Suitable for exporting structured data reports. | Not a safe BSON/GridFS backup tool for raw binary chunks. |

**Recommendation:** for production, prefer snapshot/point-in-time backup solutions supported by your deployment and run regular restore tests. If using Database Tools, understand their topology limitations and behavior under concurrent writes.

### 12.2. Backing Up Only `assets.files` Is Insufficient

If you have:

~~~text
assets.files:
  F100 -> length=600000, chunkSize=261120

assets.chunks:
  (not backed up)
~~~

After restore:

~~~text
find GridFS F100 -> metadata visible
download F100 -> missing content, data error
~~~

Conversely, backing up only **`assets.chunks`** preserves bytes while losing file descriptors, filenames, lengths, and ACL linkage.

### 12.3. Do Not Forget the Catalog and Permissions

If GridFS metadata holds `tenantId` while the business catalog holds owner/ACL/`currentFileId`, both must be backed up under one consistency model.

~~~text
Complete backup set needs:

gridfs_security_lab.assets.files
gridfs_security_lab.assets.chunks
gridfs_security_lab.asset_catalog
gridfs_security_lab.asset_permissions (if separate)
gridfs_security_lab.asset_audit (if within recovery scope)
~~~

If application records live in another database or deployment, point-in-time consistency is harder. Define coordination or recovery via reconciliation/sagas; never assume two separate MongoDB clusters share a single snapshot point automatically.

## 13. Point-in-Time Consistency: More Important Than Dump Order

### 13.1. An Inconsistent Backup Example

Suppose a backup tool runs sequentially:

~~~text
09:00:00  Dump assets.files
09:00:01  Upload F100 starts, writes chunks
09:00:05  Upload F100 ends, writes files document
09:00:10  Dump assets.chunks
~~~

The backup may contain:

~~~text
assets.files:  missing F100
assets.chunks: contains F100's chunks
~~~

If backed up in the reverse order:

~~~text
09:00:00  Dump assets.chunks
09:00:05  Upload F100 finishes
09:00:10  Dump assets.files
~~~

The backup may contain:

~~~text
assets.files:  contains F100
assets.chunks: missing F100's chunks
~~~

The second case is especially dangerous because the catalog may mark the file `READY` while its bytes are incomplete.

### 13.2. Sharing the Same Database Is Not Enough

Even when **`assets.files`** and **`assets.chunks`** live in the same database, dumping them with two separate commands at different times **does not produce a consistent snapshot**.

You need a **consistent recovery point** or a quiesced maintenance window (no uploads, deletes, or metadata updates) with confirmation that all writes have settled.

### 13.3. Replica Sets: Using the Oplog Mechanism Supported by Database Tools

For a replica set and a full dump, Database Tools supports **`mongodump --oplog`** to capture operations occurring during the dump; on restore, the oplog can be replayed via the matching procedure.

**Illustrative** command from an operations host with MongoDB Database Tools installed:

~~~bash
mongodump \
  --uri="mongodb://backup-user@db1.example:27017,db2.example:27017/?replicaSet=rs0" \
  --archive="./replica-set-backup.archive.gz" \
  --gzip \
  --oplog
~~~

When running for real:

- Never put passwords in shell history or public examples.
- Configure proper credentials, network/TLS, and backup privileges.
- **`--oplog`** requires dumping the **entire mongod/replica set** and cannot be arbitrarily combined with **`--db`, `--collection`, or `--query`** per Database Tools rules.
- Consider running against an appropriate secondary to offload the primary per backup strategy.
- Never apply a replica-set example as a guaranteed consistent backup for a **sharded cluster**.

**Note:** the shell command above only outlines options; it is not a complete runbook for every MongoDB version, TLS/Atlas topology, or security policy.

### 13.4. Sharded Clusters Require Consistent Cross-Shard Backups

In a sharded cluster, a file or related collections can span shards. Dumping through `mongos` while writes occur does not automatically guarantee **a synchronized snapshot across all shards**.

Prioritize:

1. Supported managed sharded-cluster snapshots / point-in-time backups.
2. Dedicated backup tools with cross-shard coordination.
3. Otherwise, a true maintenance window halting writes and verifying consistency before dumping.

Never treat **`mongodump --oplog`** on a single shard as a backup of an entire sharded GridFS deployment. Never stitch together per-shard snapshots taken at different times and call them point-in-time consistent.

### 13.5. A Backup Snapshot Can Contain Chunks from In-Progress Uploads

Suppose at snapshot time:

~~~text
F100 chunk 0 already written
F100 chunk 1 already written
F100 upload not finished yet
assets.files does not have F100 yet
asset_catalog.status = UPLOADING
~~~

This snapshot still reflects **the true state of the system at capture time**. It is not necessarily a broken backup.

After restore, a recovery worker must handle **in-progress uploads** per that state—for instance marking them `FAILED`/`RETRYABLE` and cleaning up chunks after a grace period. Do not assume every orphan chunk in a backup indicates an inconsistent point-in-time backup.

### 13.6. Defining the Recovery Point for Metadata and Bytes

When the business catalog and GridFS share a replica set, the target is:

~~~text
Snapshot at T:

asset_catalog(T)
assets.files(T)
assets.chunks(T)
~~~

If a file was **`READY` at T**, the backup is expected to include all published bytes as of T.

If a file was still **`UPLOADING` at T**, the backup may contain partial catalog/chunks without a complete `files` record. Recovery should keep the file hidden and reprocess or clean up the workflow.

## 14. Restoring GridFS: Right Data Is Not Enough—Permissions Must Be Right Too

### 14.1. Controlled Restore Workflow

~~~text
Restore request
      |
      v
Choose verified backup/recovery point
      |
      v
Restore into isolated staging environment
      |
      v
Verify collections and indexes
      |
      v
Reconcile files/chunks/business links
      |
      v
Verify sample SHA-256 + content reads
      |
      v
Validate app permissions/tenant isolation
      |
      v
Promote or re-point application traffic
      |
      v
Monitor and complete recovery
~~~

**Never restore an unverified archive directly onto live production** where it could overwrite current data or resurrect revoked access permissions.

### 14.2. Example `mongorestore` with Oplog Replay

For an archive created in a supported manner:

~~~bash
mongorestore \
  --uri="mongodb://restore-user@restore-host.example:27017/?replicaSet=rsRestore" \
  --archive="./replica-set-backup.archive.gz" \
  --gzip \
  --oplogReplay
~~~

Run only on an **authorized recovery deployment**, with compatible Database Tools versions and restore privileges. **`--oplogReplay`** has constraints around how the archive was created and other restore options; check current Database Tools documentation.

Never add **`--drop`** to a production restore command just to "clean things up" without knowing exactly which collections it will drop. For many systems, restoring into a fresh environment and promoting is safer than restoring in place.

### 14.3. Preserve `_id`, `files_id`, and `n`

During restore:

~~~text
assets.files._id = F100
assets.chunks.files_id = F100
assets.chunks.n = 0,1,2
~~~

**Never generate fresh `_id` values for `assets.files`** while forgetting to update `files_id` in chunks and `currentFileId` in the catalog. Changing file IDs is a system-wide reference migration, not a casual restore step.

### 14.4. Verify Indexes

After restore:

~~~javascript
use gridfs_security_lab

db.getCollection("assets.files").getIndexes();
db.getCollection("assets.chunks").getIndexes();
db.asset_catalog.getIndexes();
~~~

Minimum checks:

- Unique index **`{files_id:1,n:1}`** on `chunks`.
- Required GridFS indexes for drivers and queries.
- Unique index on `catalog` for business keys/`requestId` where applicable.
- Indexes by tenant/owner/status if APIs list/filter by them.

If a restore copies documents without preserving index definitions, data may be readable while queries slow down or unique constraints go unprotected.

### 14.5. Restored Permissions May Differ from Current Permissions

If a backup at T1 had:

~~~text
DOC-100 shared with user-35
~~~

but at T2:

~~~text
user-35's access was revoked
~~~

then restoring to T1 can **reinstate old permissions** if policies reside inside the snapshot.

Your DR procedure must decide:

- Are critical revocations stored outside the backup snapshot?
- During restore, are permission changes after the recovery point reapplied from an audit/event log?
- Should sensitive file downloads be temporarily paused until policy reconciliation finishes?
- Who has authority to approve reopening the service?

Restoring the right bytes with stale ACLs can become a serious security incident.

### 14.6. Synchronizing Backups with External Systems

A file may be referenced by:

- A search index.
- An RDBMS managing contracts.
- A message broker / outbox.
- A CDN / cache.
- An external object store or archive.

Restoring MongoDB to T1 **does not automatically restore those systems to T1**. After recovery, you may need to rebuild projections, invalidate CDNs, and reconcile by business IDs.

### 14.7. Choosing Meaningful RPO and RTO

| Metric | Question |
|---|---|
| **RPO (Recovery Point Objective)** | How much recent data/activity can be lost at most during recovery? |
| **RTO (Recovery Time Objective)** | How long does it take to bring the file service back online? |

For GridFS, RTO includes not only restoring bytes, but also verifying checksums, indexes, permissions, and the business catalog.

RPO must cover both **file content and permission/metadata changes**. Never measure RPO solely by newly created file counts.

## 15. Verifying Integrity Between `assets.files` and `assets.chunks`

After backup/restore or an upload failure, distinguish **metadata exists** from **the file is readable with exact bytes**.

### 15.1. Technical Invariants

For each file document `F`:

~~~text
id        = F._id
length    = F.length
chunkSize = F.chunkSize

expectedChunks =
  length == 0 ? 0 : ceil(length / chunkSize)
~~~

When `expectedChunks > 0`:

1. Exactly `expectedChunks` chunks exist.
2. Sequence **`n`** runs contiguously from `0` to `expectedChunks - 1`.
3. Every non-final chunk has `data` byte length equal to `chunkSize`.
4. The final chunk has the exact remaining byte length.
5. Sum of byte lengths equals `F.length`.
6. SHA-256 of all bytes matches the verified digest if present.

Items 2–6 cannot be inferred from **`countDocuments`** alone.

### 15.2. Final Chunk Verification Formula

For a non-empty file:

~~~text
lastChunkBytes =
  length - (expectedChunks - 1) * chunkSize
~~~

Example:

~~~text
length         = 600000
chunkSize      = 261120
expectedChunks = 3
lastChunkBytes = 77760
~~~

If the final chunk has 12,000 bytes instead of 77,760, metadata might still report `length=600000` while content is truncated. If a chunk has the right byte count yet was partially altered, only checksum/content verification catches it reliably.

### 15.3. Inspecting a File in `mongosh`

Assuming a real GridFS file ID is known:

~~~javascript
use gridfs_security_lab

const fileId = ObjectId("65a000000000000000000001");

const file = db.getCollection("assets.files").findOne({
  _id: fileId
});

printjson(file);

if (file) {
  print("length=" + file.length);
  print("chunkSize=" + file.chunkSize);
}

db.getCollection("assets.chunks").aggregate([
  {
    $match: {
      files_id: fileId
    }
  },
  {
    $sort: {
      n: 1
    }
  },
  {
    $project: {
      _id: 0,
      n: 1,
      byteLength: {
        $binarySize: "$data"
      }
    }
  }
]);
~~~

Expected result for the example file:

| `n` | `byteLength` |
|---:|---:|
| 0 | 261120 |
| 1 | 261120 |
| 2 | 77760 |

If no real file has been uploaded in the lab yet, the code returns `null` or an empty cursor. The IDs in this lesson are illustrative; **never fabricate binary data just to match example metadata**.

### 15.4. Total Chunks and Total Bytes

~~~javascript
db.getCollection("assets.chunks").aggregate([
  {
    $match: {
      files_id: fileId
    }
  },
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 },
      totalBytes: {
        $sum: {
          $binarySize: "$data"
        }
      },
      minN: { $min: "$n" },
      maxN: { $max: "$n" }
    }
  }
]);
~~~

If:

~~~text
chunkCount=3
minN=0
maxN=2
totalBytes=600000
~~~

that is a good sign, yet **still does not prove sequence uniqueness** if the unique index is missing and duplicate `n` records exist. Nor does it prove byte content matches if a chunk was replaced by binary data of equal size.

### 15.5. Unique Index and Remaining Gaps

~~~javascript
db.getCollection("assets.chunks").createIndex(
  { files_id: 1, n: 1 },
  { unique: true }
);
~~~

The index prevents duplicate sequences within a file. However:

~~~text
n = 0, 2, 3
~~~

still satisfies uniqueness while missing chunk `n=1`. In practice, GridFS drivers throw errors when encountering invalid sequences or chunk sizes. Treat read errors as an integrity incident rather than trying to patch chunks together.

### 15.6. Detecting File Documents Missing Chunks

A reconciliation check can:

~~~text
For each published file:
  load GridFS file document
  calculate expectedChunks
  read related chunks in n order
  verify contiguous sequence and sizes
  stream data to SHA-256
  compare digest and expected length
  record verification result
~~~

With millions of files, never verify all bytes inside an HTTP request. Instead:

- Check counts and sequences first.
- Partition by tenant, upload time, or newly added files.
- Verify full checksums on a schedule or risk-based cadence.
- Prioritize recently restored files or files from failed uploads.

### 15.7. Never Adjust `length` to Match Missing Data

If:

~~~text
assets.files.length = 600000
actual chunks = 500000 bytes
~~~

updating `length=500000` only hides the incident. The file may be truncated in the middle or at the end and is no longer valid for business use.

Right approach: **quarantine the file, mark it `CORRUPT`/`UNAVAILABLE`, restore bytes from backup or request a re-upload**, and verify the checksum before republishing.

## 16. Orphan Chunks and Missing Files

### 16.1. Two Different Forms of "Orphan"

**Orphan chunks**:

~~~text
assets.chunks has files_id=F100
assets.files has no _id=F100
~~~

**Orphan GridFS file / unreferenced file**:

~~~text
assets.files has _id=F101
assets.chunks for F101 are complete
asset_catalog no longer references F101
~~~

The second form is not necessarily an error: F101 could be a historical version, a file awaiting scanning, or a legitimate uploaded file not yet published.

### 16.2. Querying Orphan Chunk Candidates

Use only for **inspection** in small/lab environments, as grouping and looking up across all chunks can be very resource-intensive:

~~~javascript
db.getCollection("assets.chunks").aggregate([
  {
    $group: {
      _id: "$files_id",
      chunkCount: { $sum: 1 }
    }
  },
  {
    $lookup: {
      from: "assets.files",
      localField: "_id",
      foreignField: "_id",
      as: "fileMatches"
    }
  },
  {
    $match: {
      "fileMatches.0": {
        $exists: false
      }
    }
  },
  {
    $project: {
      _id: 1,
      chunkCount: 1
    }
  }
]);
~~~

This query finds only **candidates**. An active GridFS upload legitimately writes chunks before its `files` record appears.

### 16.3. Never Delete Orphan Candidates Immediately

A cleanup policy should require:

1. No upload lease/job is still active for `fileId`/`uploadRequestId`.
2. The candidate is past a **grace period** suited to the maximum upload duration.
3. No catalog record is in `SCANNING`/`RECOVERING`.
4. No backup/restore/cutover is processing that file.
5. Confirmation that the file is truly no longer needed.
6. Auditing and idempotent cleanup execution.

Without these checks, a cleaner running concurrently with an uploader can delete chunks of a file being created, causing failed uploads and corrupted data.

### 16.4. Cleaning Up Orphan Chunks

**Do not run the following in production merely upon spotting a candidate.** Once fully verified in a lab or authorized environment, a deletion step might be:

~~~javascript
const confirmedOrphanId = ObjectId(
  "65a000000000000000000099"
);

db.getCollection("assets.chunks").deleteMany({
  files_id: confirmedOrphanId
});
~~~

This illustrates deleting chunks for a verified `files_id`. In production, use a cleanup worker with leases, states, dry-run mode, auditing, and retries; never run manual `deleteMany` without knowing who is uploading.

### 16.5. File Exists Yet Chunks Are Missing

~~~text
assets.files F100 exists
expected n = 0,1,2
actual n   = 0,2
~~~

Do not "fix" this by creating chunk `n=1` filled with zeros or copying `n=2` to `n=1`. Exact file content was lost and must be **restored faithfully**.

When a consistent backup exists:

1. Lock download/publish access for F100.
2. Locate a backup holding the complete file.
3. Restore F100 into staging or extract per procedure.
4. Compare SHA-256 against the trusted digest.
5. Restore/swap the pointer via a controlled workflow.
6. Log the incident and perform root-cause analysis.

### 16.6. Catalog References a Nonexistent File

An exploratory reconciliation query:

~~~javascript
db.asset_catalog.aggregate([
  {
    $match: {
      status: "READY"
    }
  },
  {
    $lookup: {
      from: "assets.files",
      localField: "currentFileId",
      foreignField: "_id",
      as: "gridFsMatches"
    }
  },
  {
    $match: {
      "gridFsMatches.0": {
        $exists: false
      }
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      currentFileId: 1,
      status: 1
    }
  }
]);
~~~

**Never automatically delete the catalog record** when the GridFS file is missing: that record may be evidence of an incident requiring recovery. Transition the asset to `UNAVAILABLE` and identify a recovery source.

### 16.7. Tenant or Business ID Mismatch

Even when the file exists, you could observe:

~~~text
asset_catalog:
  assetId=DOC-100, tenantId=tenant-a, currentFileId=F100

assets.files:
  _id=F100, metadata.tenantId=tenant-b
~~~

This is a critical linkage bug. Never serve the file merely because `_id` matches. Quarantine or investigate, verify authoritative metadata, and inspect logs before making edits.

## 17. Checksums: Verifying Bytes, Not Just Chunk Counts

### 17.1. Why SHA-256?

A cryptographic hash like SHA-256 detects content modification with an astronomically low practical collision probability. It is well suited for verifying normal file integrity.

Never substitute **byte count** or **filename** for a checksum:

~~~text
File A length=600000, filename=contract.pdf
File B length=600000, filename=contract.pdf

Contents of A and B can still differ.
~~~

### 17.2. Where Should Hashing Happen?

A pipeline:

~~~text
Client upload bytes
       |
       v
Backend computes SHA-256 while streaming
       |
       v
GridFS stores bytes
       |
       v
Backend verifies read-back SHA-256 when required
       |
       v
Publish verified digest
~~~

The input hash computed by the backend can serve as the expected digest. For higher assurance around backups/restores, also hash the **read-back file**.

### 17.3. When Must Full Bytes Be Re-Read?

- After a significant restore.
- After missing/mismatched chunk incidents.
- When using GridFS as a document archive with long-term verification requirements.
- When proof is needed that a file remained verbatim.
- During periodic checks under an integrity policy.

Note that hashing a 20 GB file still requires reading 20 GB, so plan I/O and throughput. Do not hash an entire repository during peak hours without capacity.

### 17.4. Checksums Differ from Digital Signatures

A **SHA-256 digest** proves bytes match an expected digest if the digest itself is trusted.

A **digital signature** verifies that a digest or document was signed by a specific key. If an attacker can alter both bytes and `metadata.sha256`, digest verification alone will still "match."

To defend against tampering by actors with database write access, store digests/signatures in a separate trust domain with proper key management and auditing.

## 18. Java Sync Driver: `GridFSBucket`, Metadata, and Streams

The MongoDB Java Sync Driver provides the **`GridFSBucket`** API for streaming uploads, downloads, and deletions.

A custom bucket:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

public final class GridFsConnectionExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "gridfs_security_lab"
            );

            GridFSBucket bucket = GridFSBuckets.create(
                    database,
                    "assets"
            );

            // Bucket "assets" uses assets.files and assets.chunks.
            System.out.println(bucket.getBucketName());
        }
    }
}
~~~

**`MongoClient`** is normally reused across many requests in an application; the `main` example closes it on exit. Never create a new `MongoClient` per chunk or per file download.

### 18.1. Uploading with Custom Metadata

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.InputStream;

public final class GridFsUploadService {
    private final GridFSBucket bucket;

    public GridFsUploadService(GridFSBucket bucket) {
        this.bucket = bucket;
    }

    public ObjectId uploadPending(
            InputStream input,
            String filename,
            String assetId,
            String tenantId,
            String ownerId,
            String uploadRequestId) {

        Document metadata = new Document(
                "tenantId",
                tenantId
        ).append(
                "ownerId",
                ownerId
        ).append(
                "applicationFileId",
                assetId
        ).append(
                "uploadRequestId",
                uploadRequestId
        ).append(
                "status",
                "SCANNING"
        );

        GridFSUploadOptions options = new GridFSUploadOptions()
                .chunkSizeBytes(255 * 1024)
                .metadata(metadata);

        // Input stream must already be size-limited and authorized.
        return bucket.uploadFromStream(
                filename,
                input,
                options
        );
    }
}
~~~

Notes:

1. The API receives **`tenantId`/`ownerId` from an authenticated backend context**, never trusting caller-supplied parameters blindly.
2. **`uploadFromStream`** writes the file across multiple documents; mid-flight errors can occur.
3. Metadata status **`SCANNING`** means the file is not yet published.
4. Upon upload success, it returns the **GridFS file ID**, yet the business service must still verify and publish in a separate step.
5. This snippet does not enforce byte limits inside the method itself; production code must wrap the input stream and enforce quotas and cancellation.

### 18.2. Checking File Metadata Before Downloading

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.OutputStream;

public final class SecureGridFsDownloadService {

    private final GridFSBucket bucket;
    private final MongoCollection<Document> catalog;
    private final MongoCollection<Document> files;

    public SecureGridFsDownloadService(
            GridFSBucket bucket,
            MongoDatabase database) {

        this.bucket = bucket;
        this.catalog = database.getCollection("asset_catalog");
        this.files = database.getCollection("assets.files");
    }

    public void download(
            String assetId,
            String authenticatedTenantId,
            OutputStream output) {

        // Minimal example: checks only tenant + state.
        // Production must enforce full owner/share-role ACLs.
        Document asset = catalog.find(
                Filters.and(
                        Filters.eq("_id", assetId),
                        Filters.eq("tenantId", authenticatedTenantId),
                        Filters.eq("status", "READY")
                )
        ).first();

        if (asset == null) {
            throw new IllegalArgumentException(
                    "Asset is not available"
            );
        }

        ObjectId fileId = asset.getObjectId("currentFileId");
        if (fileId == null) {
            throw new IllegalStateException(
                    "READY asset has no GridFS file ID"
            );
        }

        Document file = files.find(
                Filters.and(
                        Filters.eq("_id", fileId),
                        Filters.eq(
                                "metadata.tenantId",
                                authenticatedTenantId
                        ),
                        Filters.eq(
                                "metadata.applicationFileId",
                                assetId
                        )
                )
        ).first();

        if (file == null) {
            throw new IllegalStateException(
                    "GridFS file metadata mismatch"
            );
        }

        bucket.downloadToStream(fileId, output);
    }
}
~~~

**Important:** this is a minimal illustration of **pre-download authorization + metadata cross-checking**. A production service also needs:

- Real owner/group/sharing ACLs, not just tenant matching.
- Stability checks on status/version/tenant throughout the workflow.
- Size/rate limits, timeouts, and cancellation.
- Policies for deletes occurring concurrently with downloads.
- Safe `Content-Type`, `Content-Disposition`, and cache headers.
- Error mapping (`not found`/`forbidden`) that avoids leaking whether a file exists in another tenant.

### 18.3. Do Not Use Find-by-Filename as an Authorization Source

~~~java
// Error-prone with multiple tenants or multiple versions.
bucket.downloadToStreamByName("contract.pdf", output);
~~~

Downloading by name can involve multiple versions or owners. For ACL-protected documents, resolve the **business asset** and exact authorized **GridFS file ID**.

### 18.4. Publishing via Conditional Update

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.ObjectId;

public final class GridFsPublisher {

    private final MongoCollection<Document> catalog;

    public GridFsPublisher(MongoCollection<Document> catalog) {
        this.catalog = catalog;
    }

    public void publishVerified(
            String assetId,
            String tenantId,
            String uploadRequestId,
            ObjectId verifiedFileId) {

        UpdateResult result = catalog.updateOne(
                Filters.and(
                        Filters.eq("_id", assetId),
                        Filters.eq("tenantId", tenantId),
                        Filters.eq("status", "SCANNING"),
                        Filters.eq(
                                "uploadRequestId",
                                uploadRequestId
                        )
                ),
                Updates.combine(
                        Updates.set(
                                "currentFileId",
                                verifiedFileId
                        ),
                        Updates.set("status", "READY"),
                        Updates.inc("version", 1)
                )
        );

        if (result.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Concurrent modification or invalid state"
            );
        }
    }
}
~~~

This method assumes **`verifiedFileId` was already verified by a trusted step**. Never call `publishVerified` immediately after upload if malware scanning or checksum validation is still pending.

### 18.5. Computing SHA-256 in Java While Reading a GridFS File

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class GridFsIntegrityVerifier {

    public static String sha256(
            GridFSBucket bucket,
            ObjectId fileId)
            throws IOException, NoSuchAlgorithmException {

        MessageDigest digest = MessageDigest.getInstance("SHA-256");

        try (
                GridFSDownloadStream stream =
                        bucket.openDownloadStream(fileId)
        ) {
            byte[] buffer = new byte[64 * 1024];
            int read;

            while ((read = stream.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

This code uses **`java.util.HexFormat`** (Java 17+). It hashes bytes **read back from GridFS**, not `metadata.sha256`. Compare the result against the expected digest stored in a trusted source.

The GridFS driver may throw exceptions on missing/corrupted chunks; an integrity verifier must **record the failure state and refuse to publish** rather than swallowing exceptions and reporting "verified."

### 18.6. Handling Large Streams in Java

With `GridFSDownloadStream`:

- Read using a small buffer without loading the entire file onto the heap.
- Close the stream with **`try-with-resources`**.
- Enforce timeouts and cancellation per service architecture.
- If the HTTP client disconnects, close the stream so database cursors are never leaked.

### 18.7. `GridFSBucket.delete` Does Not Delete the Whole Application Asset

~~~java
bucket.delete(fileId);
~~~

This deletes only the GridFS file; it does not update **`asset_catalog`**, clear legal holds, notify clients, or clean up external references.

Call it only after the business service verifies delete permissions and executes the corresponding lifecycle/retention workflow.

## 19. Spring Data MongoDB: `GridFsTemplate` and Access Control

Spring Data MongoDB provides **`GridFsTemplate`** for GridFS save/read/delete operations in imperative applications.

### 19.1. Choosing the Bucket Name

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.MongoConverter;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

@Configuration
public class GridFsConfig {

    @Bean
    GridFsTemplate assetsGridFsTemplate(
            MongoDatabaseFactory databaseFactory,
            MongoConverter converter) {

        return new GridFsTemplate(
                databaseFactory,
                converter,
                "assets"
        );
    }
}
~~~

Ensure the bean targets the right database and bucket so the application does not accidentally write into the default **`fs`** bucket while APIs read from **`assets`**.

### 19.2. Storing a File with Metadata

~~~java
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

import java.io.InputStream;

public final class SpringGridFsUploadService {

    private final GridFsTemplate gridFsTemplate;

    public SpringGridFsUploadService(
            GridFsTemplate gridFsTemplate) {
        this.gridFsTemplate = gridFsTemplate;
    }

    public ObjectId uploadPending(
            InputStream input,
            String filename,
            String contentType,
            String tenantId,
            String assetId) {

        Document metadata = new Document(
                "tenantId",
                tenantId
        ).append(
                "applicationFileId",
                assetId
        ).append(
                "status",
                "SCANNING"
        );

        return gridFsTemplate.store(
                input,
                filename,
                contentType,
                metadata
        );
    }
}
~~~

**Note:** `contentType` here is application-assigned metadata and does not validate content automatically. When input comes from a multipart request, enforce size limits and validation.

### 19.3. Reading a File via `GridFsTemplate`

~~~java
import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.GridFsResource;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;

import java.io.InputStream;
import java.io.IOException;

public final class SpringGridFsReader {

    private final GridFsTemplate gridFsTemplate;

    public SpringGridFsReader(GridFsTemplate gridFsTemplate) {
        this.gridFsTemplate = gridFsTemplate;
    }

    public InputStream openStreamAfterAuthorization(
            ObjectId verifiedFileId) throws IOException {

        GridFSFile file = gridFsTemplate.findOne(
                Query.query(
                        Criteria.where("_id").is(verifiedFileId)
                )
        );

        if (file == null) {
            throw new IllegalArgumentException(
                    "File not found"
            );
        }

        GridFsResource resource = gridFsTemplate.getResource(file);
        return resource.getInputStream();
    }
}
~~~

The method name **`openStreamAfterAuthorization`** is deliberate: the caller must already have verified tenant, owner, sharing policy, and `READY` state from the business catalog. It **does not perform authorization itself** just by receiving an `ObjectId`.

The caller must **close the `InputStream`** once the response stream finishes or aborts.

### 19.4. Deleting with Spring Data

~~~java
gridFsTemplate.delete(
    Query.query(
        Criteria.where("_id").is(verifiedFileId)
    )
);
~~~

This executes query-based GridFS deletion provided by the framework. It does not handle **`asset_catalog` lifecycle**, auditing, retention, or concurrent downloads.

### 19.5. Why Does `@Transactional` Not Solve Everything?

Do not write:

~~~java
@Transactional
public void uploadBusinessAsset(...) {
    gridFsTemplate.store(...);
    assetRepository.markReady(...);
}
~~~

assuming **all GridFS chunks, the file document, and the catalog commit atomically**. GridFS does not support multi-document transactions in that pattern.

Use a **state machine + atomic catalog publish update + recovery/reconciliation**.

### 19.6. Accessing GridFS from a Spring Controller

A web controller should:

1. Extract principal/tenant from the security context.
2. Call a service to check permissions in the catalog.
3. Verify GridFS file metadata/status per policy.
4. Prepare response headers.
5. Stream content with proper resource cleanup.
6. Log asset ID/correlation ID and errors; avoid logging raw bytes or sensitive metadata.

Never let a controller read raw `GridFsTemplate` by an arbitrary `fileId` without a permission check.

## 20. Encryption, Backup Retention, and Operational Security

### 20.1. Encryption in Transit

Application connections to MongoDB and backup services should use **TLS**. When GridFS holds sensitive data, ensure:

- Connection URIs/drivers are properly configured for TLS.
- Certificate validation is enabled—never disable certificate checks "just to make it work."
- MongoDB credentials are never passed over HTTP or logged.
- Secrets are stored in a secret manager or protected environment with rotation procedures.

HTTPS downloads must also be protected at proxies/gateways, not just between the application and database.

### 20.2. Encryption at Rest

MongoDB deployments can support encryption at rest via the platform/Atlas or storage engine/KMS configuration. Verify:

- Do GridFS chunks and metadata share the same encryption policy?
- How are keys managed and rotated?
- Are backups/snapshots/archives independently encrypted?
- Who is authorized to retrieve keys for restores?

Encryption at rest mitigates unauthorized disk/backup access, yet **does not replace application authorization**: a service holding valid DB credentials can still read decrypted data per its privileges.

### 20.3. Application-Level Encryption

Under strict threat models, you can **encrypt file bytes before uploading to GridFS**:

~~~text
Plaintext stream
      |
      v
Authenticated encryption
      |
      v
Encrypted bytes stored in GridFS
      |
      v
Download -> decrypt for authorized caller
~~~

When doing so, ensure:

- Per-tenant/file/version key management.
- Standard nonces/IVs and authenticated encryption.
- Key identifiers and decryption metadata stored in an appropriate trust domain.
- Antivirus/content scanning performed where plaintext is legitimately available.
- Key rotation and backup restores that include the keys.
- Never invent custom crypto from string concatenation or XOR.

If keys are lost, a backup may restore cleanly while **its contents remain undecryptable**. Backup/DR drills must verify key recovery too.

### 20.4. Securing Backups Containing Personal Data

An archive of GridFS chunks may contain:

~~~text
contracts
identity document scans
profile photos
financial records
internal files
~~~

Although stored inside BSON and compressed archives, this remains sensitive data. Require:

- Encrypting backups before writing to storage.
- Least-privilege read/list/delete access on backups.
- Separate protection for encryption keys.
- Checking storage locations and data residency requirements.
- Never placing unanonymized production backups on personal laptops or open staging servers.
- Retention, immutability, and offsite copies aligned with your threat model.

### 20.5. Restore Drills Are More Than Commands Succeeding

A restore test must prove:

1. The archive/snapshot is accessible.
2. Databases and indexes restored properly.
3. Sample files of varying sizes and types download cleanly.
4. Checksums match trusted digests.
5. Tenant/owner permissions behave as expected.
6. No tested `READY` catalog records reference missing files.
7. Recovery completes within RTO and meets RPO.

### 20.6. Never Restore Production Credentials onto Uncontrolled Test Environments

If a backup includes old users/roles or access policies, inspect them before connecting applications. Recovery environments should:

- Isolate networking and credentials from production.
- Suppress real emails, webhooks, and outbound side effects.
- Prevent accidental CDN or public DNS routing.
- Open access only after verifying ACLs and data.

## 21. Monitoring, Alerting, and Periodic Reconciliation

### 21.1. Metrics to Track

| Suggested Metric | Meaning |
|---|---|
| **`gridfs_upload_started_total`** | Upload requests started. |
| **`gridfs_upload_completed_total`** | GridFS uploads closed successfully. |
| **`gridfs_upload_failed_total`** | Failed uploads, categorized by network/size/quota/scan. |
| **`gridfs_pending_age_seconds`** | Time files remain in `UPLOADING`/`SCANNING`. |
| **`gridfs_ready_without_chunks_total`** | `READY` files found lacking complete chunks. |
| **`gridfs_orphan_chunk_candidates_total`** | File IDs with chunks but missing a `files` record. |
| **`gridfs_orphan_bytes_estimate`** | Estimated bytes held by orphan candidates. |
| **`gridfs_metadata_mismatch_total`** | Mismatches in tenant/`assetId`/length/hash. |
| **`gridfs_download_failed_total`** | Failed downloads by forbidden/not found/corrupt. |
| **`gridfs_reconciliation_lag_seconds`** | Age of data not yet reconciled. |
| **`gridfs_backup_age_seconds`** | Time since the last successful backup. |
| **`gridfs_restore_verification_failures`** | Failures during restore drills or integrity checks. |

These are **suggested application metrics**, not built-in metric names emitted automatically by MongoDB.

### 21.2. Separating Permission Errors from Corruption Errors

A rejected download may stem from:

~~~text
UNAUTHORIZED       -> not authenticated.
FORBIDDEN          -> lacks permission.
NOT_FOUND          -> asset missing or hidden by policy.
NOT_READY          -> upload still processing or revoked.
CORRUPT            -> missing chunks / checksum mismatch.
DEPENDENCY_FAILED  -> MongoDB / network failure.
~~~

Public APIs may return a uniform `404` for unauthorized resources to avoid existence leaks. Internally, keep distinct **reason codes** to separate security incidents from storage incidents.

### 21.3. Scheduled Reconciliation Jobs

~~~text
Scheduled reconciliation
  |
  +-- Scan recent READY assets
  |     |
  |     +-- Verify currentFileId exists
  |     +-- Compare tenant/applicationFileId
  |     +-- Check chunks count/sequence/length
  |     +-- Periodic checksum verification
  |
  +-- Scan stale UPLOADING/SCANNING jobs
  |     |
  |     +-- Check lease and current state
  |     +-- Retry verification or quarantine
  |
  +-- Find old orphan candidates
  |     |
  |     +-- Dry-run report
  |     +-- Confirm no active references/leases
  |     +-- Cleanup with audit
  |
  +-- Reconcile metadata/cross-system references
        |
        +-- Report mismatches
        +-- Queue manual/automatic safe repairs
~~~

Never run a bucket-wide **`deleteMany`** job from a single lookup result, because active uploads look like orphans before their `files` record is written.

### 21.4. Quarantine Before Repairing

When a `READY` file shows a mismatch:

1. Mark the catalog entry **`CORRUPT`** or **`UNAVAILABLE`**.
2. Stop serving new downloads.
3. Preserve logs and metadata for investigation.
4. Locate a trusted source or backup.
5. Verify restored bytes and metadata.
6. Publish the repaired version through a conditional workflow.

Never silently patch and destroy evidence, especially for legally significant documents.

### 21.5. Rate-Limit Reconciliation

1 million files of 1,000 chunks each create massive I/O if all bytes are read daily.

Design with:

- Bounded batches and cursors.
- Prioritizing recent assets, newly restored assets, or incident-affected assets.
- Sampling and risk-based checksum schedules where policy allows.
- Metrics for documents/bytes examined.
- Throttling based on MongoDB load and operating hours.

### 21.6. Alerting on Business Invariants

~~~text
Any READY asset with missing GridFS file:
  severity = critical

Checksum mismatch for published legal document:
  severity = critical; quarantine and investigate

Stale UPLOADING requests beyond max duration:
  severity = warning; review cleanup

Backup is older than RPO:
  severity = critical

Restore drill cannot complete within RTO:
  severity = reliability risk
~~~

Actual thresholds depend on SLOs and content sensitivity. Never equate orphan candidates with a corruption incident while active upload leases exist.

## 22. Scenario-Based Incident Runbooks

### 22.1. Case A — Interrupted Upload

~~~text
Client timeout during upload.
asset_catalog.status = UPLOADING.
Some chunks exist.
No GridFS file document.
~~~

Steps:

1. Keep the asset unpublished.
2. Check `uploadRequestId`, expected `fileId`, and upload lease.
3. If the upload is still running, do not clean up.
4. If the lease expired with no active writer, mark `FAILED`/`RETRYABLE`.
5. On retry, reuse the same business request key to avoid duplicate catalog entries.
6. Clean up chunks after the grace period with auditing.

### 22.2. Case B — File Document Exists, Missing Chunk

~~~text
assets.files.length = 600000
expected chunks = 3
actual chunks = 2
~~~

Steps:

1. Mark the asset `UNAVAILABLE`; never return a truncated file.
2. Verify chunk indexes and queries.
3. Inspect logs, backups, restores, and delete races.
4. Locate a backup containing complete bytes.
5. Verify checksums and recover via a new version or restore workflow.
6. Publish `READY` only once complete.

### 22.3. Case C — Catalog Points to a Missing File

~~~text
asset_catalog.status = READY
asset_catalog.currentFileId = F101
assets.files._id=F101 not found
~~~

Steps:

1. Hide downloads for this asset.
2. Inspect version history, audit logs, and restore points.
3. Check whether `fileId` suffered a bad migration or out-of-band delete.
4. Locate a prior copy or backup and verify its hash.
5. Restore the pointer via conditional update—never guess a file solely by matching `filename`.

### 22.4. Case D — After Restore, a Revoked User Can View a File Again

~~~text
At T1: user-35 allowed.
At T2: permission revoked.
Restore snapshot T1.
~~~

Steps:

1. Pause sensitive downloads or apply a temporary deny policy.
2. Reconcile revocations/ACL changes from audit/recovery logs.
3. Verify tokens, caches, and CDNs are invalidated.
4. Test `user-35`'s access before reopening the service.
5. Document controls and cutover timestamp.

### 22.5. Case E — SHA-256 Mismatch Despite Correct Chunk Count

~~~text
expectedChunks = actualChunks
sumChunkBytes = assets.files.length
SHA-256 differs
~~~

Steps:

1. Do not treat this as success just because counts match.
2. Check how the expected digest was generated.
3. Recompute from bytes read out of GridFS.
4. Compare against a trusted original or backup.
5. Quarantine and preserve evidence of corruption or tampering.

### 22.6. Case F — Cleaner Corrupts an In-Progress Upload

~~~text
Uploader writes chunk n=0.
Cleaner sees chunks without files record.
Cleaner removes chunks.
Uploader writes n=1,2 and file document.
Download now fails.
~~~

Remediation:

1. Stop the cleaner and affected uploads if needed.
2. Mark affected file versions `CORRUPT`/`UNAVAILABLE`.
3. Locate sources for re-upload.
4. Add **upload leases, grace periods, and explicit upload job states** before re-enabling the cleaner.
5. Test concurrency prior to production.

### 22.7. Case G — Backup Contains Only One Collection

~~~text
Backup assets.files only.
No assets.chunks.
~~~

You cannot reconstruct content from `metadata.length` and `filename`. Locate another backup containing chunks at a matching recovery point, or request source re-uploads / handle data loss. Update runbooks to back up the whole bucket and business references.

### 22.8. Case H — Unique Chunk Index Missing After Restore

If the **`{files_id:1,n:1}` unique** index is missing:

1. Pause writes that risk creating duplicate `n` values if needed.
2. Check existing data for duplicates.
3. Resolve duplicates via a trusted process—never drop an arbitrary chunk blindly.
4. Rebuild the unique index.
5. Run integrity verification/reconciliation on affected data.

Simply rebuilding the index will fail if duplicate keys already exist. Never delete duplicate chunks randomly without verifying the right bytes.

### 22.9. Case I — Backup Succeeded Yet Decryption Keys Are Lost

~~~text
Backup archive restored
GridFS files/chunks available
Encryption key missing
File bytes cannot be decrypted
~~~

For applications encrypting files before GridFS, include **key management** in the DR plan. A backup of ciphertext fails business recovery if the corresponding keys cannot be recovered.

Never store an uncontrolled plaintext key backup alongside sensitive data; build an access-controlled escrow/KMS recovery mechanism.

## 23. Solution Selection Matrix by Requirement

| Requirement | Recommended Solution | Do Not Confuse With |
|---|---|---|
| Per-file read permissions | Application ACL/tenant policy, check catalog before download. | MongoDB `find` on collection. |
| Infrastructure-level tenant isolation | Separate buckets/databases if DB-level isolation is needed. | Merely adding `metadata.tenantId` in a shared bucket. |
| Files exceeding BSON limit | GridFS splits bytes into chunks. | One 16 MiB BSON document. |
| Uploads hidden until complete | State machine publishing `READY` only after verification. | `assets.files` exists = public. |
| Zero-downtime file replacement | Upload new `fileId`, atomic pointer swap, delayed cleanup. | Overwriting chunks in place. |
| Link-preserving backups | Point-in-time snapshot of catalog + `files` + `chunks`. | Dumping two collections at different times. |
| Restoring a sharded cluster | Coordinated sharded backup / managed PIT. | Combining unsynchronized per-shard snapshots. |
| Complete data verification | Sequence/chunk length/total bytes + SHA-256. | Counting `files` documents alone. |
| Orphan chunk cleanup | Leases + grace period + reconciliation + audited cleanup. | Deleting all parentless chunks immediately. |
| Data deletion compliance | Live deletion + backup retention/key policy. | Calling `bucket.delete(fileId)` alone. |
| Incident monitoring | Metrics/checkpoints/audits/restore drills. | Watching CPU or file count alone. |

## 24. Lab Testing Procedure for a GridFS Bucket

This is a hands-on plan that **never touches production**.

### 24.1. Preparation

1. Connect to the lab MongoDB database **`gridfs_security_lab`**.
2. Use the GridFS bucket **`assets`**.
3. Create a small file with known content.
4. Upload using Java `GridFSBucket` or Spring Data `GridFsTemplate`.
5. Save the real file ID returned by the driver.

### 24.2. Inspect Metadata

~~~javascript
use gridfs_security_lab

db.getCollection("assets.files").find(
  {},
  {
    filename: 1,
    length: 1,
    chunkSize: 1,
    uploadDate: 1,
    metadata: 1
  }
).limit(20);
~~~

Verify every completed upload has a `files` document; `metadata.tenantId`/`applicationFileId` originate from the service; and files are not published before the catalog reaches `READY`.

### 24.3. Inspect Chunks

~~~javascript
const id = ObjectId("65a000000000000000000001");

db.getCollection("assets.chunks").find(
  { files_id: id },
  { _id: 0, files_id: 1, n: 1 }
).sort({ n: 1 });
~~~

Replace **`id`** with the real file ID from your upload. If the file is empty, the chunk count is `0`.

### 24.4. Test Application Authorization

Create two tenants/users:

~~~text
Tenant A:
  User A owns DOC-100.

Tenant B:
  User B owns DOC-200.
~~~

Tests:

1. A downloads DOC-100 -> allowed if `READY`.
2. A downloads DOC-200 -> denied.
3. B downloads DOC-100 -> denied.
4. A submits `fileId` directly -> API still enforces authorization.
5. Unauthenticated user -> denied per policy.

### 24.5. Test Incomplete Uploads

In a test environment using mocks/fault injection:

1. Start uploading multiple chunks.
2. Interrupt the stream mid-way.
3. Observe the catalog does not transition to `READY`.
4. Cleaner does not delete chunks while the upload lease is active.
5. Once the lease expires, cleanup runs per protocol.

Never intentionally corrupt a production GridFS bucket to test business flows.

### 24.6. Test Backup/Restore

1. Upload one small file, one large multi-chunk file, and one zero-byte file if policy permits.
2. Save expected sizes/SHA-256 digests from the original bytes.
3. Take a topology-consistent backup.
4. Restore into an isolated lab database.
5. Verify `files`, `chunks`, indexes, and catalog.
6. Download and compare SHA-256.
7. Verify per-tenant ACLs.
8. Verify files in `SCANNING`/`FAILED` remain inaccessible.

### 24.7. Test Connection Failures During Version Replacement

1. DOC-100 points to F100.
2. Upload F101.
3. Simulate a crash before pointer swap: DOC-100 still serves F100.
4. Simulate a crash after pointer swap yet before cleanup: DOC-100 serves F101, while F100 remains until later cleanup.
5. Verify no mixed output of half F100 + half F101 occurs.

### 24.8. Test Concurrent Download and Delete

1. Reader starts downloading F100.
2. User requests deleting DOC-100.
3. Service blocks new download requests after state transition.
4. Per policy, the active stream finishes or is explicitly terminated.
5. Chunk cleanup runs only once lease/grace/retention rules allow.

Expectations must be defined in business requirements prior to testing.

## 25. Common Mistakes

### 25.1. "GridFS is one big document, so uploads are atomic"

**False.** GridFS splits a file across multiple documents in `files` and `chunks`, without an atomic commit across all bytes and metadata like a single-document write.

### 25.2. "`assets.files` exists, so chunks are complete and intact"

**Insufficient.** Check chunk count, `n` sequence, total bytes, and checksums when integrity is required. Bad backup/restore or concurrent deletes can leave metadata and binary out of sync.

### 25.3. "MongoDB RBAC alone ensures users see only their own files"

**False in a shared bucket.** DB roles restrict collections and actions; they do not filter individual GridFS files by `metadata.ownerId`. Application authorization is mandatory.

### 25.4. "ObjectIds are unguessable, so permission checks aren't needed"

**False.** An ID is not an authorization token. Once leaked through logs, browser history, emails, or API responses, files must still be protected.

### 25.5. "Only `assets.chunks` needs to be backed up"

**False.** Without `files` records, you lose `length`, `chunkSize`, `filename`, and linkage. You also need the business catalog and ACLs.

### 25.6. "Dumping `assets.files` then `assets.chunks` makes a consistent backup"

**False under concurrent writes.** Dumping two collections at different instants can yield file documents with missing chunks or orphan chunks.

### 25.7. "`mongodump --oplog` works identically for standalone, replica sets, and sharded clusters"

**False.** `--oplog` has prerequisites and limits depending on topology and dump options. Sharded clusters require cross-shard coordinated backups or managed PIT.

### 25.8. "A readable backup archive means data is fully recoverable"

**False.** You need restore drills verifying indexes, ACLs, catalog links, sample bytes, and checksums. With application encryption, key recovery is also required.

### 25.9. "Counting the right number of chunks is enough"

**False.** `n=1` could be missing while `n=3` exists; counts do not prove contiguous sequences. Equal-sized chunks can still hold wrong bytes.

### 25.10. "If the checksum mismatches, update `metadata.sha256`"

**Dangerous.** That covers up data corruption. Resolve the expected digest from a trusted source and restore original bytes or a valid new version.

### 25.11. "Immediately delete all chunks lacking a `files` record"

**Dangerous.** Active uploads may have written chunks before creating their `files` record. Use leases, grace periods, and reconciliation.

### 25.12. "Deleting a GridFS file deletes all business metadata"

**False.** `GridFSBucket.delete` does not update `asset_catalog`, audits, external caches, or backups. Implement full lifecycle deletion.

### 25.13. "Chunks can be overwritten in place to update a version"

**Bad practice.** Readers can observe mixed content or mismatches. Create a new file ID, verify it, and atomically swap the pointer.

### 25.14. "`metadata.mediaType` proves the file format"

**False.** Client-declared MIME can be spoofed. Use content sniffing, scanning, and parsers when security policies apply.

### 25.15. "Restoring an old backup does not affect access permissions"

**False.** ACLs inside a snapshot may predate permission revocations. Run policy reconciliation before reopening downloads.

### 25.16. "SHA-256 is the same as a digital signature"

**Not quite.** A digest verifies bytes only if the expected hash is trusted. Digital signatures/HMACs require key management to authenticate origin and prevent digest tampering.

### 25.17. "Encryption at rest makes application ACLs unnecessary"

**False.** Valid DB credentials can still read data permitted to that account. API AuthN/AuthZ and key management serve different purposes.

### 25.18. "Setting `READY` in two documents is a single atomic step"

**False.** Two updates across two separate documents are not jointly atomic in a GridFS workflow. Pick **one authoritative publish pointer/state** and reconcile secondary metadata copies eventually.

### 25.19. "Deleting a live file deletes it from backups"

**False.** Backups have independent retention. Sensitive-data deletion workflows must account for backup lifecycles, archives, and cryptographic key policies.

### 25.20. "A single permission check at stream start guarantees instant revocation"

**Not by default.** Running downloads can continue unless the application implements active cancellation/revocation.

### 25.21. "Once a file uploads successfully, it can be served immediately"

**Not necessarily.** Malware scanning, PDF validation, size/hash checks, tenant ownership, and business approval may still be required before publishing.

### 25.22. "Filename is a unique key for downloads"

**False.** Multiple tenants and versions can share a filename. Use an authorized business ID and the exact GridFS file ID for that version.

## 26. Exercises

### Exercise 1 — Distinguishing Metadata and Content

Draw the linkage diagram:

~~~text
asset_catalog -> assets.files -> assets.chunks
~~~

Explain which fields connect each layer and what happens if any layer is missing.

### Exercise 2 — Chunk Count

A file has:

~~~text
length = 600000 bytes
chunkSize = 261120 bytes
~~~

Calculate `expectedChunks` and the byte length of each chunk. Explain the role of `n=0,1,2`.

### Exercise 3 — Empty File

How many chunks does a file with `length=0` have? Why might business rules reject empty files even though GridFS can represent them?

### Exercise 4 — Unique Index

Create the unique index **`{files_id:1,n:1}`** on `assets.chunks`. Which duplicates does this index prevent, and which missing-chunk scenarios does it fail to prevent?

### Exercise 5 — MongoDB RBAC

Write a custom role granting only **`find`** on `assets.files` and `assets.chunks`. Explain why this role does not isolate individual `ownerId` values in a shared bucket.

### Exercise 6 — Upload Permissions

A service only uploads and reads metadata without file deletion rights. List the actions it may need on `files`/`chunks` and explain how to provision indexes separately.

### Exercise 7 — IDOR

An API exposes **`GET /files/{fileId}`** and downloads directly by `ObjectId`. Describe how an attacker knowing someone else's ID could download their file and how to fix it with business ACLs.

### Exercise 8 — Tenant Mismatch

A catalog record for `tenant-a` points to a GridFS file with `metadata.tenantId=tenant-b`. Write a download workflow that rejects the request and raises an alert rather than returning the file.

### Exercise 9 — State Machine

Design states **`UPLOADING, SCANNING, READY, REJECTED, DELETING, DELETED`**. For each state, decide whether the API permits downloads.

### Exercise 10 — Idempotency

A client uploads with `requestId` `REQ-100`; the server finishes writing to GridFS, yet the response is lost. How should a retry with the same `requestId` be handled so two business assets are not created?

### Exercise 11 — Failure Before Publish

GridFS upload F100 succeeds, yet the process crashes before `asset_catalog` reaches `READY`. Propose a recovery worker that inspects metadata/`fileId` and safely publishes or cleans up.

### Exercise 12 — Version Replacement

DOC-100 currently points to F100. Upload F101 and run `updateOne` conditioned on `version=3` to swap the pointer. If `matchedCount=0`, how should the service respond?

### Exercise 13 — Concurrent Download and Delete

A reader has started downloading a 1 GB file when an admin requests deletion. Design policies for new requests, in-flight streams, grace periods, and when to delete chunks.

### Exercise 14 — Inconsistent Backup

Consider the timeline:

~~~text
T1: dump assets.chunks
T2: upload new file completes
T3: dump assets.files
~~~

Explain how a file can appear in metadata yet lack chunks after restore.

### Exercise 15 — `mongodump` and Oplog

In a replica set, explain why **`mongodump --oplog`** is used when a consistent backup is needed under supported conditions. Why can this pattern not be applied verbatim to every sharded cluster?

### Exercise 16 — Backup Scope

An application has **`assets.files`**, **`assets.chunks`**, **`asset_catalog`**, and **`asset_permissions`**. List which collections require consistent backup and the consequences of omitting `asset_permissions`.

### Exercise 17 — Restore and Stale ACLs

A user's access was revoked at T2, while the backup from T1 still grants access. Design a policy reconciliation step before reopening downloads.

### Exercise 18 — Checking Chunks with Aggregation

Write a query using **`$binarySize`**, **`$group`**, and `files_id` to compute `chunkCount`, `totalBytes`, `minN`, and `maxN`. Why does that query still not replace a checksum?

### Exercise 19 — Orphan Chunks

Write a `$lookup` finding `files_id` values that have chunks but no `files` document. Which conditions must hold before cleanup so active uploads are not deleted?

### Exercise 20 — `READY` Asset Missing GridFS File

Write an aggregation from `READY` `asset_catalog` entries looking up `assets.files` by `currentFileId` and returning entries missing files. What recovery workflow fits?

### Exercise 21 — Checksum

Design a Java service that streams a GridFS file and computes SHA-256, comparing against a trusted expected digest. What happens if the chunk count matches yet a single byte was altered?

### Exercise 22 — Malware Scanning System

A file named **`report.pdf`** is uploaded, yet its bytes are not a PDF. Design validation steps before transitioning to `READY`. Why not trust the client-sent `Content-Type`?

### Exercise 23 — Application-Level File Encryption

An enterprise encrypts each file with a per-file key before storing in GridFS. If a backup is restored without its keys, what happens? What must be added to the DR plan?

### Exercise 24 — Spring Data `GridFsTemplate`

Write Spring Data code using **`GridFsTemplate.store()`** with custom metadata containing `tenantId`, `assetId`, and `status=SCANNING`. Describe how to query the GridFS file and return an `InputStream` after authorization.

### Exercise 25 — Backup Operator Privileges

Why should the account running `mongorestore` not be the MongoDB credential used by a public API server? Propose separating runtime, provisioning, backup, and restore roles.

### Exercise 26 — Periodic Restore Drills

Design a restore drill containing:

~~~text
One small file
One large multi-chunk file
One empty file if policy permits
One tenant-a private file
One tenant-b private file
~~~

Test both checksums and access control after restore.

### Exercise 27 — TTL and Backup Retention

A user requests file deletion. The file is deleted from live GridFS, yet backups retain data for 90 days. Write an explanation of retention and compliant policy options.

### Exercise 28 — Monitoring

Choose at least five metrics to detect upload failures, orphan candidates, checksum mismatches, stale `READY` links, and backups past RPO.

### Exercise 29 — Concurrent Cleanup

A cleaner sees chunks without a `files` document and tries to delete them immediately. Write pseudocode using upload leases + grace period + reconciliation to avoid destroying active uploads.

### Exercise 30 — Multi-Tenant Architecture

Compare:

- One shared `assets` bucket protected through the API.
- Separate buckets/databases per tenant.

Evaluate security isolation, collection/index counts, backups, operational complexity, and suitable use cases.

## 27. Review Questions

1. Into which two collections does GridFS split a file?
2. What is the default GridFS bucket prefix? If a bucket is named `assets`, what are the two collections called?
3. How are `fs.files._id` and `fs.chunks.files_id` related?
4. What is the role of field `n` in `chunks`?
5. Why is a unique index on `files_id+n` insufficient to guarantee no chunks are missing?
6. What is the typical default size of a GridFS chunk?
7. With `length=0`, how many chunks does a GridFS file need?
8. Why cannot a GridFS file be treated as a single atomic document write?
9. Are temporary chunks lacking a `files` document always corrupted data?
10. Does GridFS support multi-document transactions as an atomic whole-upload commit mechanism?
11. How does collection-level MongoDB RBAC differ from per-file ACLs?
12. Why is an `ObjectId` not an authorization token?
13. Why must APIs verify tenant, owner, and state before downloading?
14. When filenames match, how do GridFS file ID and business asset ID differ?
15. What information should `asset_catalog` hold instead of relying solely on GridFS metadata?
16. When should the `READY` state be published?
17. Why separate `UPLOADING`, `SCANNING`, and `READY`?
18. What risk does an idempotency key solve when clients retry uploads?
19. What state is left if an upload succeeds yet crashes before publishing?
20. What are the benefits of pointer-swap file replacement over updating chunks in place?
21. When deleting a GridFS file, does the driver automatically update `asset_catalog`?
22. When revoking permissions mid-stream, what policies must be defined?
23. Why is backing up only `fs.files` or `fs.chunks` insufficient?
24. What can happen if the two collections are backed up at different times?
25. What topology/option constraints apply to `mongodump --oplog`?
26. Why does a sharded cluster need coordinated backups or managed snapshots?
27. Can a point-in-time snapshot contain in-progress upload chunks and still be valid?
28. Must restores preserve `files._id`, `chunks.files_id`, and `n`?
29. After restore, why must both ACLs and revocations be verified?
30. How are RPO and RTO interpreted in a file storage system?
31. What formula computes `expectedChunks` from `length` and `chunkSize`?
32. Why does an accurate total chunk byte count not prove content accuracy?
33. How does SHA-256 differ from metadata length and digital signatures?
34. Why shouldn't you edit `length` to mask missing chunks?
35. How do orphan chunks differ from unreferenced GridFS files?
36. Why must orphan candidates never be deleted while an upload lease is active?
37. What conditions must a cleanup worker verify before deleting bytes?
38. Why must filenames never be concatenated directly into filesystem paths?
39. How do you protect against serving untrusted HTML/PDF files through browsers?
40. How can Java `GridFSBucket` and Spring `GridFsTemplate` perform streaming uploads and downloads?
41. Why can a backup containing bytes without encryption keys be useless?
42. Which metrics help detect `READY` files missing content?
43. When a catalog record points to another tenant's file, what must the service do?
44. Can a restore test be considered successful without re-downloading at least sample files?
45. Which conditions must be met before reopening downloads after recovery?

## 28. Operational Checklist Before Deploying GridFS to Production

### 28.1. Before Building the Service

- [ ] Define bucket/database names, avoiding confusion between **`fs`** and **`assets`**.
- [ ] Define file size limits, allowed file types, quotas, and timeouts.
- [ ] Provision required indexes, especially **`unique(files_id,n)`**.
- [ ] Separate runtime privileges from provisioning/backup/restore privileges.
- [ ] Design business asset IDs, tenant IDs, and owner/sharing policies.
- [ ] Choose where authoritative metadata and state live.
- [ ] Define `uploadRequestId` and idempotency rules.
- [ ] Define SHA-256/content validation and scanning.
- [ ] Define data/backup encryption and key lifecycle.

### 28.2. Before Publishing a File

- [ ] Upload stream completed per GridFS driver.
- [ ] File ID linked to the right business asset/tenant.
- [ ] File size within limits.
- [ ] Content readable and verified when policy requires.
- [ ] Checksum/malware/media-type checks passed.
- [ ] Catalog updated to `READY` via conditional single-document update.
- [ ] Non-`READY` files blocked from download.
- [ ] Audit/correlation ID recorded for the upload operation.

### 28.3. Before Serving Downloads

- [ ] Caller authenticated.
- [ ] Tenant/owner/share ACLs verified.
- [ ] Asset is in `READY` state.
- [ ] `currentFileId` matches version with no GridFS metadata mismatch.
- [ ] Response headers safely escaped/sanitized.
- [ ] Stream timeouts, cancellation, and cleanup implemented.
- [ ] Behavior during concurrent deletion/revocation defined.
- [ ] Binary contents and sensitive metadata excluded from logs.

### 28.4. Before Deleting

- [ ] Caller authorized to delete.
- [ ] File not under legal hold or retention prohibition.
- [ ] Catalog no longer exposes the file to new requests.
- [ ] Active references and in-flight readers checked per policy.
- [ ] Cleanup worker enforces leases, grace periods, and auditing.
- [ ] `files`/`chunks` and catalog reconciled after deletion.
- [ ] Backup retention and data-deletion policies reviewed.

### 28.5. Before Declaring a Backup Recoverable

- [ ] `assets.files`, `assets.chunks`, and catalog included in backup scope.
- [ ] Recovery point is consistent across topology.
- [ ] Backup encrypted and stored with controlled access.
- [ ] Required configurations and encryption keys backed up.
- [ ] Restore drill executed in an isolated environment.
- [ ] Indexes verified after restore.
- [ ] Small/large sample files downloaded and checksums compared.
- [ ] `READY` links, orphan candidates, and missing chunks checked.
- [ ] ACLs/revocations and external integrations reconciled.
- [ ] RPO and RTO targets met.

## 29. Summary: Three Invariants to Protect

When using GridFS, do not merely ask "Did MongoDB store the file?" A secure design must uphold three invariants:

### Invariant 1 — Right Permissions

~~~text
CanRead(user, asset)
  = authenticated
    AND authorized by tenant/owner/share policy
    AND asset is READY
    AND file is the verified current version
~~~

MongoDB RBAC protects database/collection scope and actions; **application ACLs protect individual files**. Never substitute an `ObjectId` or `filename` for access control.

### Invariant 2 — Right Content

~~~text
ValidGridFSFile(file)
  = files record exists
    AND expected chunks exist
    AND chunk numbers are contiguous
    AND total bytes == files.length
    AND checksum matches trusted digest (when required)
~~~

Integrity cannot be verified merely by seeing a `files` document or counting chunks.

### Invariant 3 — Restoring a Single Consistent State

~~~text
ConsistentRecoveryPoint(T)
  = business catalog at T
    + GridFS file records at T
    + GridFS chunks at T
    + relevant access policies at T
    + recovery procedure for in-progress workflows
~~~

Backups must be consistent in time and topology, especially when concurrent uploads/deletes occur. Restoring valid bytes with broken links or stale permissions is still an unsafe restore.

### Principles to Remember

1. **GridFS stores files across multiple documents**; never assume uploads or deletes are atomic inside a multi-document transaction.
2. **A bucket consists of `files` and `chunks`**; back up and restore both alongside business metadata.
3. **MongoDB RBAC does not filter individual files** in a shared bucket; the service must enforce ACLs.
4. **Publish only after verification** via an authoritative state or pointer updated conditionally.
5. **Use a new version when replacing content**, retain old files long enough for reads/rollback, and clean up safely afterward.
6. **Incomplete uploads can leave chunks without a `files` record**; never delete until confirming the upload is no longer active.
7. **Orphan/missing chunks require reconciliation**, never ad-hoc edits to `length` or binary data.
8. **Checksums computed from real bytes** are vital integrity checks; digests must come from trusted sources.
9. **Backup/restore requires point-in-time consistency**, not two arbitrary sequential dumps.
10. **Permissions and encryption keys must be restored accurately**, including post-recovery-point revocations per policy.
11. **Java `GridFSBucket` and Spring Data `GridFsTemplate`** provide streaming APIs, while business lifecycle and recovery remain the application's responsibility.
12. **DR drills, auditing, metrics, and runbooks** are part of correctness, not tasks deferred until an outage.

### Official References

- [MongoDB GridFS — Overview and Schema](https://www.mongodb.com/docs/manual/core/gridfs/) — `files`/`chunks`, indexes, upload/download, transaction limits.
- [MongoDB Database Tools: mongodump](https://www.mongodb.com/docs/database-tools/mongodump/) — BSON backups, `--oplog`, and constraints.
- [MongoDB Database Tools: mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/) — restore and oplog replay.
- [MongoDB Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/) — backup strategies by topology.
- [MongoDB Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/) — privileges and least-privilege principles.
- [MongoDB Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/) — `find`, `insert`, `update`, `remove`, `createIndex`, and related actions.
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — protecting chunk sequence uniqueness.
- [MongoDB Java Sync Driver — GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/) — `GridFSBucket`, `uploadFromStream`, `downloadToStream`, and `delete`.
- [Spring Data MongoDB — GridFS](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-gridfs.html) — `GridFsTemplate`, `GridFsResource`, and template APIs.
- [MongoDB TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/) — securing connections to MongoDB.
- [MongoDB Encryption at Rest](https://www.mongodb.com/docs/manual/core/security-encryption-at-rest/) — protecting stored data.

Design GridFS as a **content lifecycle management system**, not just a binary dumping ground. A file is truly ready to serve only when **the right user is authorized, the exact bytes are verified, and metadata plus content can be recovered to a single consistent state**.
