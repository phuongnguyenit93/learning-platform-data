# Streaming Upload, Streaming Download, and File Metadata with MongoDB GridFS

## 1. What Problem Does GridFS Solve?

MongoDB normally stores a business entity as a **BSON document**. A single document has a **16 MiB** size limit. When an application needs to manage files such as original images, multi-page PDFs, videos, backup archives, data exports, or user-uploaded documents, it cannot simply place all that large binary data into a `BinData` field of one document.

**GridFS** is a specification and set of driver APIs that splits a file into multiple small **chunks**, writes them into MongoDB, and reassembles them on download. Binary data and metadata are stored in two separate collections inside the same **bucket**.

For example, a contract document storage system:

- A user uploads a 70 MiB PDF.
- The server does not read all 70 MiB into RAM.
- The Java driver reads sequentially from an `InputStream`, splits it into chunks, and writes them to GridFS.
- A metadata document describes the file ID, filename, size, upload timestamp, and business attributes.
- On download, the server reads the chunks in order and writes them to the HTTP response's `OutputStream`.
- Application memory stays near the buffer/chunk size instead of growing with the file size.

> **Core takeaway:** GridFS enables storing and recovering a large file across **multiple documents**, while streaming enables the application to **read/write incrementally** instead of loading the entire file into RAM.

### 1.1. When Should You Use GridFS?

GridFS fits well when:

1. Files exceed 16 MiB.
2. You want streaming uploads/downloads to avoid holding the entire file in memory.
3. You want to manage binary content and metadata within the same MongoDB system.
4. You want to leverage MongoDB's backup, replication, access control, and infrastructure.
5. You need to read portions of large files through a driver-supported workflow.
6. The file count is large enough that managing files directly via OS directories becomes cumbersome.

### 1.2. When Should You Not Use It?

Consider alternatives if:

- All files are under 16 MiB and only need simple binary storage in a single `BinData` document.
- You need **atomic updates of the entire file content**. GridFS does not support multi-document transactions.
- The system already has object storage/CDN suited for images, videos, and massive static files; MongoDB can simply store metadata and the object key.
- The application requires specialized features such as object storage multipart uploads, lifecycle transitions to cold storage, edge caching, or video transcoding.
- Files are tiny ephemeral data without persistence requirements as business assets.

GridFS is not an "object storage replacement for every other system." Evaluate latency, backup cost, replication traffic, CDN, durability, internet access, and data operations.

---

## 2. Buckets, `files`, and `chunks`: Architecture Diagram

A GridFS bucket defaults to the name `fs`, consisting of two collections:

```text
Database: files_demo

GridFS bucket "fs"
   |
   +-- fs.files
   |     1 document / 1 complete file version
   |     _id, filename, length, chunkSize, uploadDate, metadata
   |
   +-- fs.chunks
         many documents / 1 file
         _id, files_id, n, data
```

If the bucket is named `attachments`, the collection pair becomes:

```text
attachments.files
attachments.chunks
```

A **bucket** is how the driver organizes the two collections. It is not a special MongoDB server collection type; users can still see both collections in `mongosh`.

### 2.1. Upload Flow

```text
HTTP request / local file / network source
                    |
                    v
               InputStream
                    |
                    v
           GridFSBucket upload
                    |
              split into chunks
                    |
        +-----------+-----------+
        |           |           |
        v           v           v
    chunk n=0   chunk n=1   chunk n=2 ...
        |           |           |
        +-----------+-----------+
                    |
                    v
               fs.chunks
                    |
                    v
          write fs.files document
          after upload completes
                    |
                    v
                 file ID
```

### 2.2. Download Flow

```text
Client requests fileId
           |
           v
    GridFSBucket
           |
           +--> read fs.files metadata
           |
           +--> read fs.chunks in ascending n order
                     |
                     v
                GridFSDownloadStream
                     |
                     v
                 OutputStream
                     |
                     v
              HTTP response / file
```

The Java driver handles splitting and reassembling chunks. **You do not need to manually split bytes into BSON documents** in regular application code.

---

## 3. Document Structure in `fs.files`

An illustrative metadata document:

```javascript
{
  _id: ObjectId("6917a0000000000000000001"),
  length: NumberLong("73400320"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T08:00:00Z"),
  filename: "hop-dong.pdf",
  metadata: {
    tenantId: "TENANT-001",
    documentId: "DOC-100",
    originalFilename: "Lease Agreement.pdf",
    contentType: "application/pdf",
    uploadedBy: "USER-42",
    sha256: "f2ca1bb6c7e907d06dafe4687e579fce...",
    lifecycle: "READY",
    schemaVersion: 1
  }
}
```

This is an illustrative structure, not a real record. The `sha256` field is shortened for readability; an actual SHA-256 checksum is 64 hex characters.

| Field | Meaning | Notes |
| --- | --- | --- |
| `_id` | Unique identifier of the file version | The driver typically generates an `ObjectId`; compatible BSON ID types can be used per API. |
| `filename` | Display/storage name in GridFS | **Not unique** by default; multiple files can share the same name. |
| `length` | File data size in **bytes** | Long/int64, not the number of documents. |
| `chunkSize` | Size of each chunk, except the last chunk | Default **255 KiB = 261,120 bytes**. |
| `uploadDate` | Upload date, BSON Date type | Metadata timestamp, not a durable version ID. |
| `metadata` | Application-defined information | Can be a document holding tenant, MIME, checksum, permissions, description. |
| `md5` | Legacy checksum | **Deprecated**, do not rely on it for security or integrity. |
| Top-level `contentType` | Legacy MIME field | **Deprecated**; use `metadata.contentType`. |
| Top-level `aliases` | Legacy aliases | **Deprecated**; use `metadata`. |

### 3.1. File ID Differs from `filename`

With two uploads:

```text
ID = A, filename = "invoice.pdf", uploadDate = 10:00
ID = B, filename = "invoice.pdf", uploadDate = 11:00
```

These are **two independent versions**—B does not automatically overwrite A's content.

If an API needs "the exact file the user is authorized to view," it is best to use the **ID stored in the business document** and verify corresponding permissions rather than relying solely on the filename.

### 3.2. Metadata Does Not Self-Validate Its Values

You can store:

```javascript
metadata: {
  contentType: "application/pdf"
}
```

but GridFS **does not verify whether the actual file is a PDF** just because you wrote that string. Verifying MIME type, file signatures, malware, and size is the application's responsibility.

---

## 4. Document Structure in `fs.chunks`

An illustrative chunk:

```javascript
{
  _id: ObjectId("6917a0000000000000000101"),
  files_id: ObjectId("6917a0000000000000000001"),
  n: 0,
  data: BinData(0, "JVBERi0xLjcK...")
}
```

| Field | Meaning |
| --- | --- |
| `_id` | Unique ID of the **chunk document** |
| `files_id` | ID of the parent file in `fs.files` |
| `n` | Chunk sequence number, starting at **0** |
| `data` | Chunk bytes stored as BSON Binary |

**Download order** is determined by `n`, not by ObjectId order, upload time, or natural collection document order.

### 4.1. How Many Chunks Does a File Have?

Formula for a file with positive size:

```text
chunkCount = ceil(fileLengthBytes / chunkSizeBytes)
```

Example of a **600 KiB** file using the default **255 KiB** chunk:

```text
File = 600 KiB

Chunk n=0: 255 KiB
Chunk n=1: 255 KiB
Chunk n=2:  90 KiB
------------------
Total    : 600 KiB
```

A file smaller than one chunk still has one chunk holding the exact bytes needed. An **empty file** can have a 0-length metadata document with no chunk data documents at all.

### 4.2. GridFS Chunks Differ from Sharding Chunks

In GridFS, a **chunk** is a binary segment of a file.

In MongoDB sharding, a **chunk/range** is a shard-key partitioning unit. The two terms **do not refer to the same entity** despite sharing a name.

---

## 5. Required GridFS Indexes

GridFS uses two standard indexes:

### 5.1. `chunks` Index

```javascript
db.getSiblingDB("files_demo")
  .fs.chunks
  .createIndex(
    { files_id: 1, n: 1 },
    { unique: true }
  );
```

This index enables reading chunks of a file in order and prevents two chunks from sharing the same `(files_id, n)` pair.

Corresponding query:

```javascript
db.getSiblingDB("files_demo")
  .fs.chunks
  .find({ files_id: fileId })
  .sort({ n: 1 });
```

### 5.2. `files` Index

```javascript
db.getSiblingDB("files_demo")
  .fs.files
  .createIndex({
    filename: 1,
    uploadDate: 1
  });
```

This index supports finding revisions by name and timestamp. It is **not a unique index**, because GridFS allows multiple versions to share the same `filename`.

### 5.3. Does the Driver Create Indexes Automatically?

The Java Sync Driver creates bucket collections on **the first write** when needed. It creates the default GridFS indexes when they do not yet exist and **the bucket is empty**.

Do not interpret this as "the driver always repairs any broken index in a bucket that already has data." When a legacy bucket already exists or has anomalous data, inspect and adjust indexes according to an administrative plan.

Check with:

```javascript
const dbFiles = db.getSiblingDB("files_demo");

dbFiles.fs.files.getIndexes();
dbFiles.fs.chunks.getIndexes();
```

Do not drop these two indexes just to "reduce write overhead": GridFS relies on them to retrieve data and enforce chunk ordering/uniqueness.

---

## 6. Chunk Size: 255 KiB Default and How to Choose

GridFS defaults to **255 KiB**:

```text
255 × 1024 = 261120 bytes
```

You can override the chunk size per file using `GridFSUploadOptions.chunkSizeBytes(...)`.

### 6.1. What Is the Benefit of Choosing Larger Chunks?

Suppose you need to store 1 GiB of data:

- Smaller chunks → more chunk documents, more entries in the `chunks` index.
- Larger chunks → fewer chunk documents, reducing metadata/index/round-trip overhead in some cases.
- Larger chunks also increase per-stream buffers/memory and the amount of data read when accessing a small range.

There is no single best number for every workload. Factors include:

- Average and maximum file sizes.
- Number of concurrent uploads/downloads.
- Whether access patterns primarily stream whole files or read partial ranges.
- Network and MongoDB speed.
- Memory budget per service instance.
- Storage/index cost and data distribution.

### 6.2. Do Not Exceed the BSON Document Limit

Each chunk is **one BSON document**. Keep `chunkSizeBytes` **below the 16 MiB document limit**, leaving headroom for other fields. For example, 1 MiB is a reasonable option to benchmark, though not a mandatory default.

### 6.3. Chunk Size Is Not the HTTP Request Buffer

`chunkSizeBytes` controls how **GridFS stores chunks in MongoDB**. Your HTTP response buffer or Java copy buffer can be 8 KiB, 32 KiB, or another value. You do not need to allocate a 255 KiB byte array for each read call when the driver accepts `InputStream`/`OutputStream`.

---

## 7. Java Sync Driver: Initializing `GridFSBucket`

Use a `mongodb-driver-sync` dependency compatible with your MongoDB Server version. The examples below focus on GridFS APIs and do not include real secrets.

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

public final class GridFSConnection {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_URI is not configured"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client
                .getDatabase("files_demo")
                .withWriteConcern(WriteConcern.MAJORITY);

            GridFSBucket bucket = GridFSBuckets.create(
                database,
                "attachments"
            );

            System.out.println("Bucket name: attachments");
            // Bucket collections are created on the first write.
        }
    }
}
```

If you only call:

```java
GridFSBucket bucket = GridFSBuckets.create(database);
```

the default bucket name is `fs`, so the collections are `fs.files` and `fs.chunks`.

### 7.1. Why Choose `WriteConcern.MAJORITY`?

Java Sync Driver documentation **recommends `WriteConcern.MAJORITY` when storing GridFS files**. If a weak write concern is used and a primary election occurs during an upload, some chunks could be rolled back, leaving an incomplete file.

`MAJORITY` does not eliminate every failure, but it improves durability guarantees depending on topology and replication health. You still need retry/recovery when an upload fails.

### 7.2. Do Not Open a `MongoClient` per File

`MongoClient` manages connection pools. In a backend service, create `MongoClient` for the application's lifecycle, and create/reuse `GridFSBucket` instances for the corresponding databases/buckets.

Do not open and close a connection pool on every upload/download request; handshake overhead, connection churn, and timeouts will increase.

---

## 8. Uploading a File via `InputStream`

This is the simplest way to upload a file from disk, HTTP multipart, or any `InputStream` without holding the entire file in RAM.

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GridFSUploader {

    public static ObjectId uploadPdf(
            GridFSBucket bucket,
            Path source,
            String tenantId,
            String uploaderId
    ) throws IOException {

        Document metadata = new Document()
            .append("tenantId", tenantId)
            .append("uploadedBy", uploaderId)
            .append("contentType", "application/pdf")
            .append("schemaVersion", 1);

        GridFSUploadOptions options =
            new GridFSUploadOptions()
                .chunkSizeBytes(1024 * 1024)
                .metadata(metadata);

        try (InputStream input = Files.newInputStream(source)) {
            return bucket.uploadFromStream(
                source.getFileName().toString(),
                input,
                options
            );
        }
    }
}
```

### 8.1. What Happens in This Code?

1. Java opens the file as an `InputStream`.
2. The driver reads bytes incrementally.
3. The driver saves multiple chunk documents into `attachments.chunks`.
4. Upon upload success, the driver finalizes the file document in `attachments.files`.
5. The method returns an `ObjectId` so the application can link the file to a business record.
6. `try-with-resources` closes the input stream even if the upload fails.

### 8.2. Advantages of Streaming

Do not write:

```java
byte[] allBytes = Files.readAllBytes(source);
bucket.uploadFromStream(
    "huge.pdf",
    new java.io.ByteArrayInputStream(allBytes)
);
```

if files can be very large. That creates an array proportional to the file size. Under concurrent requests, memory consumption spikes rapidly.

Use `Files.newInputStream`, `FileInputStream`, or an appropriate multipart `InputStream` so the file is read as a stream.

### 8.3. Metadata and MIME Types

`contentType` in the example is an **application-declared value**. In production:

- Do not blindly trust the `Content-Type` header sent by the client.
- Verify MIME type using file signatures/parsers or an appropriate scanner.
- Restrict allowed file types per business rules.
- You may keep `metadata.originalFilename`, but avoid using it directly as a filesystem path.

---

## 9. Uploading via `GridFSUploadStream` (`OutputStream`)

In the reverse direction: the application wants to **write bytes incrementally itself** into GridFS—for example, receiving data blocks while applying lightweight transformations.

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSUploadStream;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.InputStream;

public final class GridFSPipeUpload {

    public static ObjectId upload(
            GridFSBucket bucket,
            String filename,
            InputStream source,
            Document metadata
    ) throws IOException {

        GridFSUploadOptions options =
            new GridFSUploadOptions()
                .chunkSizeBytes(1024 * 1024)
                .metadata(metadata);

        // Source ownership is managed by the caller.
        try (GridFSUploadStream target =
                 bucket.openUploadStream(filename, options)) {

            byte[] buffer = new byte[64 * 1024];
            int read;

            while ((read = source.read(buffer)) != -1) {
                if (read == 0) {
                    continue;
                }
                target.write(buffer, 0, read);
            }

            // Closing GridFSUploadStream finalizes the file
            // and performs the steps needed to complete the upload.
            return target.getObjectId();
        }
    }
}
```

**Note on completion timing:** in the code above, `return target.getObjectId()` is evaluated **before** `try-with-resources` calls `close()`, yet the value is only returned from the method after the stream closes successfully. If `close()` throws, the method does not return success.

### 9.1. Why Use an Output Stream?

- The application receives data generated or delivered incrementally.
- You want to compute digests, transform, or encrypt the stream before writing.
- You want control over how many bytes are read per iteration.
- You do not want to materialize the entire content prior to upload.

### 9.2. When Is `uploadFromStream` Simpler?

If you already have an `InputStream` and do not need per-block processing logic, `bucket.uploadFromStream(...)` is usually more concise. Both use GridFS and avoid loading the whole file into RAM.

---

## 10. Streaming Directly from an HTTP Multipart `InputStream`

Suppose the web framework layer provides the `InputStream` of a multipart file. A minimal service method:

```java
public ObjectId saveAttachment(
        InputStream requestBodyStream,
        String safeFilename,
        String tenantId,
        String ownerId,
        GridFSBucket bucket
) {
    Document metadata = new Document()
        .append("tenantId", tenantId)
        .append("ownerId", ownerId)
        .append("contentType", "application/octet-stream")
        .append("state", "UPLOADED");

    GridFSUploadOptions options =
        new GridFSUploadOptions()
            .chunkSizeBytes(255 * 1024)
            .metadata(metadata);

    return bucket.uploadFromStream(
        safeFilename,
        requestBodyStream,
        options
    );
}
```

This snippet assumes the request body has already been authenticated, size-limited, and validated at the HTTP layer. **Never pass raw filenames or MIME types directly from the request** into storage or responses without sanitization and checks.

### 10.1. Request `Content-Length` Is Not Guaranteed to Be Honest

A client can:

- Omit `Content-Length`.
- Send an inaccurate `Content-Length`.
- Use chunked transfer encoding.
- Attempt to stream an enormous file to exhaust disk/indexes.
- Disconnect mid-upload.

You must **enforce a limit on actual bytes read**, even if the request header claims the file is small.

### 10.2. Example of a Size-Limited `InputStream`

A simple Java wrapper (counting bytes as the driver reads):

```java
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;

public final class SizeLimitedInputStream
        extends FilterInputStream {

    private final long maxBytes;
    private long consumed;

    public SizeLimitedInputStream(
            InputStream input,
            long maxBytes
    ) {
        super(input);
        if (maxBytes < 0) {
            throw new IllegalArgumentException(
                "maxBytes must be non-negative"
            );
        }
        this.maxBytes = maxBytes;
    }

    @Override
    public int read() throws IOException {
        int value = super.read();
        if (value != -1) {
            consumed++;
            if (consumed > maxBytes) {
                throw new IOException("Upload too large");
            }
        }
        return value;
    }

    @Override
    public int read(
            byte[] bytes,
            int offset,
            int length
    ) throws IOException {
        int maxToRead = (int) Math.min(
            (long) length,
            maxBytes - consumed + 1L
        );
        if (maxToRead <= 0 && length > 0) {
            throw new IOException("Upload too large");
        }
        int read = in.read(bytes, offset,
            Math.max(maxToRead, 0));
        if (read > 0) {
            consumed += read;
            if (consumed > maxBytes) {
                throw new IOException("Upload too large");
            }
        }
        return read;
    }
}
```

The pattern above illustrates the byte-counting idea. In production, carefully account for `skip()`, `mark/reset()`, and any other read paths, or use a battle-tested wrapper; a wrapper that only overrides a couple of methods can be bypassed if callers invoke other methods. Framework upload limits and reverse-proxy limits should still be enabled as defense in depth.

---

## 11. Upload Failures: GridFS Does Not Have a Single-Document Commit

This is a critical point.

An upload must write **multiple chunk documents** and then write the file metadata. GridFS **does not support multi-document transactions** to wrap that entire sequence in one ACID transaction.

Scenario:

```text
Upload 5 MiB file
    |
    +-- chunk 0: success
    +-- chunk 1: success
    +-- chunk 2: success
    +-- chunk 3: network error
    |
    X file metadata may not be finalized yet
```

**Orphaned chunks** can remain: chunk documents whose `files_id` has no parent document in `fs.files`.

### 11.1. Common Failure Causes

- Client/user cancels the upload.
- `InputStream` throws `IOException`.
- Primary election, connection reset, or timeout.
- Disk quota/collection/storage failure.
- Write concern timeout.
- Process killed before completion.
- Error during the final metadata document write.

Do not assume an exception **always** cleans up every chunk; per driver documentation, failed uploads can leave orphaned chunks that require cleanup.

### 11.2. Impact on File IDs

When an upload succeeds, the driver returns a file ID. If the upload throws, **do not create a `READY` pointer in the business document** as if the file were complete.

If you supply a custom ID before upload, that ID may already have been used for partial chunks; blindly retrying with the same ID can hit duplicate key errors or leave inconsistent state. You need an explicit strategy distinguishing completed, incomplete, and indeterminate uploads.

### 11.3. Cleaning Up Orphaned Chunks

A chunk is orphaned if:

```text
fs.chunks.files_id does not exist in fs.files._id
```

However, **do not immediately delete** every apparent orphan: a valid **in-progress** upload will also have written chunks before finalizing `fs.files`.

A safer procedure:

1. Run under approved administrative privileges.
2. Select **candidate orphan chunks old enough** relative to the maximum allowed upload duration.
3. Cross-check `files_id` against `fs.files` and application-level upload/lease state.
4. Ensure no uploader is still active for that ID.
5. Log/emit metrics and delete in bounded batches once confirmed orphaned.
6. Validate behavior in staging before applying to production.

Never run a `deleteMany` for "every chunk missing a file" while concurrent uploads are running.

---

## 12. What Should an Upload API Return?

After success:

```json
{
  "fileId": "6917a0000000000000000001",
  "filename": "report.pdf",
  "status": "READY"
}
```

This is an application-designed API response, **not a built-in GridFS response**.

### 12.1. Defining Business States

One model:

```text
REQUEST_RECEIVED
     |
     v
VALIDATING
     |
     v
UPLOADING
     |
     +-- failure --> FAILED / cleanup
     |
     v
GRIDFS_COMPLETED
     |
     v
SCANNING / VERIFYING
     |
     +-- rejected --> QUARANTINED / cleanup
     |
     v
READY
```

Do not transition a file to a public `READY` state before the driver upload succeeds and business verification finishes.

### 12.2. Metadata Status Does Not Replace Transactions

If an application writes:

1. Content into GridFS.
2. A business document linking `fileId`.

**the two steps are not automatically atomic**. If step 2 fails, the file may exist without a business pointer; reconciliation/cleanup is needed. If the business requires a consistent view of the current version, upload the new version first and then use a **single-document atomic update on the pointer document** to switch to the new file ID once ready.

---

## 13. Downloading a File by ID into an `OutputStream`

If the API already knows the file ID, this is the most direct approach:

```java
import com.mongodb.client.gridfs.GridFSBucket;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GridFSDownloader {

    public static void download(
            GridFSBucket bucket,
            ObjectId fileId,
            Path outputPath
    ) throws IOException {

        try (OutputStream output =
                 Files.newOutputStream(outputPath)) {
            bucket.downloadToStream(fileId, output);
            output.flush();
        }
    }
}
```

`bucket.downloadToStream(...)` reads the file from GridFS and writes directly to the target stream. The application does not need to allocate a `byte[]` sized to the full file length.

### 13.1. Avoiding the Bug of Writing Failed Files Directly to the Target Name

If a download fails partway through, `outputPath` can contain a **partial file**. In applications with integrity requirements:

1. Write to a temporary path on the same filesystem.
2. Finish downloading and close the stream.
3. Verify size/checksum if available.
4. Atomically move/rename the temporary file to the final path if the platform/filesystem supports it.
5. Clean up the temporary file on error.

Do not treat starting a download as sufficient to mark a file as successfully recovered.

---

## 14. Downloading as an `InputStream` with `GridFSDownloadStream`

If you want to **control each block yourself** for HTTP streaming, SHA-256 computation, or stream processing, use `openDownloadStream`:

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.OutputStream;

public final class GridFSStreamCopy {

    public static void copyFile(
            GridFSBucket bucket,
            ObjectId fileId,
            OutputStream destination
    ) throws IOException {

        try (GridFSDownloadStream input =
                 bucket.openDownloadStream(fileId)) {

            byte[] buffer = new byte[64 * 1024];
            int read;

            while ((read = input.read(buffer)) != -1) {
                if (read == 0) {
                    continue;
                }
                destination.write(buffer, 0, read);
            }

            destination.flush();
        }
    }
}
```

### 14.1. Memory Footprint

If the file is 1 GiB long, this code allocates only a 64 KiB copy buffer (in addition to buffers and resources managed by the driver and HTTP framework). It **does not** allocate a 1 GiB array.

### 14.2. Why Not Use a Single `read()` Call?

Wrong:

```java
byte[] bytes = new byte[(int) file.getLength()];
input.read(bytes);
```

Problems:

- `length` is a `long`; casting to `int` can overflow.
- A single `InputStream.read(byte[])` call **is not guaranteed to fill** the buffer.
- Large files can cause `OutOfMemoryError`.
- An HTTP client disconnecting mid-stream still wastes memory.

If you need to read an exact byte count into a small buffer, use a proper stream-reading loop or supported read-fully APIs.

### 14.3. `getGridFSFile()`

`GridFSDownloadStream` provides:

```java
GridFSFile fileInfo = input.getGridFSFile();

long length = fileInfo.getLength();
String filename = fileInfo.getFilename();
Document metadata = fileInfo.getMetadata();
```

This is the metadata of the file selected for download, useful when setting HTTP headers before streaming content.

---

## 15. Downloading by `filename` and Revision

GridFS **allows multiple files with the same `filename`**, so downloading by name must specify a revision.

Example:

```text
filename = "contract.pdf"

Upload 1: 2026-01-10, ID=A
Upload 2: 2026-02-10, ID=B
Upload 3: 2026-03-10, ID=C
```

Revision semantics:

| Revision | Result |
| --- | --- |
| `0` | Oldest version, ID=A |
| `1` | Next version, ID=B |
| `2` | Following version, ID=C |
| `-1` | Newest version, ID=C |
| `-2` | Second newest version, ID=B |

Java API:

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSDownloadOptions;

import java.io.IOException;
import java.io.OutputStream;

public final class GridFSRevisions {

    public static void downloadOriginal(
            GridFSBucket bucket,
            String filename,
            OutputStream output
    ) throws IOException {

        GridFSDownloadOptions options =
            new GridFSDownloadOptions()
                .revision(0);

        bucket.downloadToStream(
            filename,
            output,
            options
        );
    }

    public static void downloadLatest(
            GridFSBucket bucket,
            String filename,
            OutputStream output
    ) throws IOException {

        GridFSDownloadOptions options =
            new GridFSDownloadOptions()
                .revision(-1);

        bucket.downloadToStream(
            filename,
            output,
            options
        );
    }
}
```

By default, when multiple files share the same name, GridFS downloads **the most recent version** based on `uploadDate`.

### 15.1. Why Is Downloading by ID Usually Safer?

- `filename` is not unique.
- Users may upload multiple times under the same name.
- Names can change via `rename()`.
- Concurrent uploads/renames/deletes can shift which file is "latest."
- Metadata `uploadDate` should not replace a business version number in workflows requiring strict ordering.

For business document APIs, store the ID in `documents.currentFileId` and download the exact specified ID. If "latest" is desired, the application should define a clear pointer-update policy.

---

## 16. `GridFSBucket.find()`: Querying Files via Metadata

You can query metadata through the `GridFSBucket` API rather than reading raw `fs.files` directly in every situation.

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.conversions.Bson;

public final class GridFSMetadataQuery {

    public static void listTenantPdfs(
            GridFSBucket bucket,
            String tenantId
    ) {
        Bson filter = Filters.and(
            Filters.eq("metadata.tenantId", tenantId),
            Filters.eq(
                "metadata.contentType",
                "application/pdf"
            )
        );

        bucket.find(filter)
            .sort(Sorts.descending("uploadDate"))
            .limit(50)
            .forEach((GridFSFile file) -> {
                System.out.println(
                    file.getObjectId().toHexString()
                    + " " + file.getFilename()
                    + " " + file.getLength()
                );
            });
    }
}
```

`GridFSFile` typically provides:

- `getId()` (`BsonValue`) and the convenience `getObjectId()` when the ID is an `ObjectId`.
- `getFilename()`.
- `getLength()`.
- `getChunkSize()`.
- `getUploadDate()`.
- `getMetadata()`.

### 16.1. Metadata Filters and Tenant Isolation

Display only files belonging to the authenticated tenant. `tenantId` must come from the **server-side authenticated context**, not from an arbitrary client-supplied query parameter.

When downloading directly by ID, you must still **verify that the file ID belongs to the tenant and the user is authorized to read it**; filtering the list page by tenant alone is not enough.

### 16.2. `GridFSFile.getObjectId()` Has ID-Type Constraints

If you create a GridFS file with `_id` as a BSON type other than `ObjectId`, the convenience `getObjectId()` method may not work. In code supporting multiple ID types, use `getId()` as a `BsonValue` with the matching bucket overloads.

---

## 17. Querying Metadata Directly with `mongosh`

MongoDB does not hide GridFS collections. For example:

```javascript
const d = db.getSiblingDB("files_demo");

d.attachments.files.find(
  {
    "metadata.tenantId": "TENANT-001",
    "metadata.contentType": "application/pdf"
  },
  {
    filename: 1,
    length: 1,
    uploadDate: 1,
    metadata: 1
  }
).sort({
  uploadDate: -1
}).limit(20);
```

Inspecting chunks of a file:

```javascript
const fileId = ObjectId("6917a0000000000000000001");

d.attachments.chunks.find(
  { files_id: fileId },
  { n: 1, _id: 1, data: 0 }
).sort({ n: 1 });
```

**Do not use** `find()` directly on `chunks` to download a file and manually concatenate `BinData` when a GridFS driver is available; the driver handles ordering, EOF, and proper validation.

### 17.1. Querying Metadata Does Not Download Binary Data

When listing files through `attachments.files`, MongoDB returns only **metadata documents**; it does not load chunks for every file. This is a major advantage when displaying document lists, sizes, MIME types, and upload dates.

### 17.2. Do Not Rely on `uploadDate` for Authorization

`uploadDate` indicates when an upload occurred, not whether a user is allowed to view the file or whether the file is `READY`. Use metadata and proper business ACLs.

---

## 18. Designing Useful Metadata for Production Systems

Metadata can be organized into groups:

| Group | Suggested Fields |
| --- | --- |
| Tenant/ownership | `tenantId`, `ownerId`, `uploadedBy` |
| File type | `contentType`, `extension`, `originalFilename` |
| Business references | `documentId`, `caseId`, `contractId` |
| Integrity | `sha256`, `hashAlgorithm` |
| Lifecycle | `state`, `verifiedAt`, `deletedAt` |
| Search/filtering | `tags`, `category`, `classification` |
| Versioning | `businessVersion`, `replacesFileId` |
| Security | `scanStatus`, `sensitivity`, `retentionUntil` |
| Governance | `schemaVersion`, `sourceSystem` |

Example:

```javascript
{
  metadata: {
    schemaVersion: 2,
    tenantId: "T100",
    ownerId: "USER-42",
    originalFilename: "report Q4.pdf",
    contentType: "application/pdf",
    sha256: "full-64-character-sha256-hex",
    businessVersion: 3,
    state: "READY",
    scanStatus: "CLEAN",
    labels: ["finance", "q4"]
  }
}
```

The `sha256` value in the example illustrates the schema, not a valid digest.

### 18.1. Metadata Is Application Schema, Not a Fixed Specification

GridFS does not enforce `metadata.tenantId` or `metadata.state`; that is an application choice. You can apply MongoDB schema validation to `attachments.files`, but be careful to avoid conflicting with the structure required by the GridFS driver.

### 18.2. Do Not Store Unnecessary Sensitive Data

Avoid putting passwords, access tokens, full personal addresses, or file contents into metadata unless required. Metadata may be queried, indexed, backed up, and logged differently from binary payloads.

---

## 19. MIME Type: Put `contentType` in `metadata`, Do Not Trust the Client

MongoDB GridFS has a historical `files.contentType` field, which is **deprecated**. Place the MIME type inside:

```javascript
metadata: {
  contentType: "application/pdf"
}
```

### 19.1. Distinguishing Three MIME Sources

1. **Client-declared MIME**: HTTP header, which can be wrong or spoofed.
2. **Filename extension**: `.pdf`, `.png`, `.exe`; also untrustworthy.
3. **Detected MIME**: based on file signature/approved parser, usually more reliable, though it does not by itself eliminate malware.

For example, a request claims `image/png` while the actual bytes are an executable. GridFS will store the bytes; protection is the application's responsibility.

### 19.2. When Serving Files over HTTP

Recommendations:

- `Content-Type` based on verified metadata.
- `Content-Length` from `GridFSFile.getLength()` if available and no compression/transformation altered the bytes.
- `Content-Disposition: attachment` with filename sanitized/encoded per RFC.
- `X-Content-Type-Options: nosniff`.
- Appropriate cache, authorization, and range-request policies.

Never send `Content-Type: text/html` simply because a client uploaded a file claiming to be HTML when the business only allows attachments.

---

## 20. SHA-256, Integrity Checks, and Why `md5` Is Deprecated

GridFS historically included an `md5` field produced via `filemd5`. MongoDB has **deprecated** MD5 support and recommends that applications compute their own checksums and store them in `metadata`.

MD5 is unsuitable against intentional collisions and is not a modern choice for file integrity/security. Use **SHA-256** or a digest algorithm aligned with organizational policy.

### 20.1. Computing SHA-256 During Streaming Upload

You can wrap the `InputStream` with `DigestInputStream`:

```java
import java.io.DigestInputStream;
import java.io.InputStream;
import java.security.MessageDigest;

MessageDigest sha256 =
    MessageDigest.getInstance("SHA-256");

try (InputStream raw = Files.newInputStream(path);
     DigestInputStream input =
         new DigestInputStream(raw, sha256)) {

    ObjectId id = bucket.uploadFromStream(
        "report.pdf",
        input,
        options
    );

    byte[] digest = sha256.digest();
    String hex = java.util.HexFormat
        .of()
        .formatHex(digest);

    // At this point we have both fileId and digest.
    // We can update the checksum metadata after upload.
}
```

`java.util.HexFormat` was introduced in Java 17. If your project uses an older Java version, convert bytes to hex with compatible code.

### 20.2. Timing of Checksum Availability

In streaming, the complete digest is only known **after reading the entire file**. However, `GridFSUploadOptions.metadata` must be provided before the upload starts.

Approaches:

- **Two-pass read**: compute the hash first, then upload on the second pass; costs extra I/O, but metadata contains the checksum at creation time.
- **Single-pass streaming**: compute the hash during upload, and upon success update `metadata.sha256` in `*.files`; requires handling the window between upload completion and metadata update.
- **Staging/READY**: allow files to become visible/downloadable only after checksum and scan completion are recorded.
- **Server-trusted digest**: accept a client-supplied checksum for comparison, but never treat a client checksum as proof of safe content.

If an HTTP request body cannot be re-read, two passes are not feasible without spooling to temporary disk. When spooling, enforce storage limits and clean up temporary files.

### 20.3. Verifying on Download

Compute SHA-256 over the bytes **actually downloaded** and compare against the trusted metadata digest. If they differ, treat the file as compromised and do not publish the downloaded content as a complete file.

Checksums detect corruption, but do not replace authorization, malware scanning, or encryption.

---

## 21. Updating Metadata After Upload

GridFS metadata lives in `attachments.files`. Application fields can be updated through a standard `MongoCollection`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import org.bson.Document;
import org.bson.types.ObjectId;

public final class GridFSMetadataUpdate {

    public static void markVerified(
            MongoDatabase database,
            ObjectId fileId,
            String sha256Hex
    ) {
        MongoCollection<Document> files =
            database.getCollection("attachments.files");

        files.updateOne(
            Filters.eq("_id", fileId),
            Updates.combine(
                Updates.set(
                    "metadata.sha256",
                    sha256Hex
                ),
                Updates.set(
                    "metadata.scanStatus",
                    "CLEAN"
                ),
                Updates.set(
                    "metadata.state",
                    "READY"
                )
            )
        );
    }
}
```

### 21.1. Only Modify Application Metadata Fields

**Do not directly modify** system fields such as:

- `length`.
- `chunkSize`.
- `_id`.
- `files_id` and `n` in `chunks`.

Editing `length` or `chunkSize` improperly can cause GridFS readers to fail with missing/corrupt chunk errors or read wrong data. Never "fix the length" via metadata edits without matching chunk data.

### 21.2. Avoiding Race-Condition State Overwrites

If a slow scanner updates `scanStatus: CLEAN` after a file was already revoked, the scanner must not blindly set the state to `READY`.

Use a conditional update:

```javascript
db.getSiblingDB("files_demo")
  .attachments.files
  .updateOne(
    {
      _id: fileId,
      "metadata.state": "SCANNING"
    },
    {
      $set: {
        "metadata.state": "READY",
        "metadata.scanStatus": "CLEAN"
      }
    }
  );
```

Check `matchedCount`/`modifiedCount` per your application contract.

---

## 22. Creating Secondary Indexes for Metadata and List APIs

The default indexes keep GridFS working, but if the application frequently lists files by tenant/owner/status, custom indexes may be needed.

```javascript
const d = db.getSiblingDB("files_demo");

d.attachments.files.createIndex({
  "metadata.tenantId": 1,
  "metadata.state": 1,
  uploadDate: -1
});

d.attachments.files.createIndex({
  "metadata.documentId": 1,
  uploadDate: -1
});
```

A query:

```javascript
d.attachments.files.find({
  "metadata.tenantId": "T100",
  "metadata.state": "READY"
}).sort({
  uploadDate: -1
}).limit(20);
```

### 22.1. Why Index Frequently Queried Metadata?

Without suitable indexes, the system may scan many file metadata documents whenever users open a list view. Even though binary payloads reside in another collection, an `attachments.files` collection with millions of entries still requires query planning.

### 22.2. Do Not Index Every Field

Each index adds storage, write maintenance, and backup costs. Create indexes based on real query shapes: tenant/status/date, `documentId`, filename/version, or checksum if deduplication requires it.

### 22.3. TTL Does Not Replace GridFS Delete

**Do not place a TTL index directly on `attachments.files.uploadDate` expecting it to delete the file's data.** TTL only removes documents from `*.files`—it does not invoke `GridFSBucket.delete` to remove the associated chunks, easily leaving orphaned chunks behind.

For retention, use a **lifecycle job** that finds files due for deletion and calls GridFS `delete(fileId)` in a controlled manner, with cleanup and auditing.

---

## 23. `rename` and `delete` by File ID

The GridFS driver exposes:

```java
bucket.rename(fileId, "report-2026.pdf");
bucket.delete(fileId);
```

### 23.1. `rename`

`rename(fileId, newFilename)` renames **one specific file ID**. It does not touch the bytes and does not rename all revisions sharing the old filename.

Because multiple files can share a name, **do not rename by ambiguous name**.

### 23.2. `delete`

`delete(fileId)` removes the file metadata and chunks for one file ID using the GridFS mechanism.

Because GridFS lacks multi-document transactions, an interrupted delete can leave orphaned chunks or an inconsistent state. You should:

- Record the deletion intent (audit).
- Avoid unbounded retries without classifying the outcome.
- Reconcile chunks if the operation fails.
- Verify authorization before deleting.
- Avoid deleting by filename when multiple versions share a name.

### 23.3. Do Not Drop the Bucket to Delete One File

`bucket.drop()` deletes the **entire bucket** (both collections). This is a major destructive operation reserved for confirmed administrative/test procedures, never for a `DELETE /files/{id}` endpoint.

---

## 24. Streaming HTTP Downloads: API Design

A conceptual endpoint:

```text
GET /api/files/{fileId}
Authorization: Bearer ...
```

Recommended workflow:

```text
1. Authenticate request.
2. Parse/validate fileId.
3. Verify file belongs to tenant/owner and is READY.
4. Read metadata and validate MIME/length/filename.
5. Set HTTP response headers.
6. Stream GridFSDownloadStream -> response output stream.
7. Close stream and handle client disconnect errors.
```

### 24.1. Example with Jakarta Servlet

```java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;
import com.mongodb.client.gridfs.model.GridFSFile;
import jakarta.servlet.http.HttpServletResponse;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.IOException;
import java.io.OutputStream;

public final class DownloadController {

    public static void send(
            GridFSBucket bucket,
            ObjectId fileId,
            HttpServletResponse response
    ) throws IOException {

        // CALL BEFORE SERVING RESPONSE:
        // authenticate + authorize fileId + tenant + READY.
        // Example only demonstrates streaming.

        try (GridFSDownloadStream input =
                 bucket.openDownloadStream(fileId)) {

            GridFSFile info = input.getGridFSFile();
            Document metadata = info.getMetadata();

            String mime = "application/octet-stream";
            if (metadata != null) {
                String validated = metadata
                    .getString("contentType");
                if (validated != null &&
                    !validated.isBlank()) {
                    // Production must validate against MIME allowlist.
                    mime = validated;
                }
            }

            response.setContentType(mime);
            response.setHeader(
                "X-Content-Type-Options",
                "nosniff"
            );
            response.setContentLengthLong(
                info.getLength()
            );

            // Download filename must be sanitized/encoded
            // per RFC 6266/5987 before setting the header.

            byte[] buffer = new byte[64 * 1024];

            try (OutputStream output =
                     response.getOutputStream()) {

                int read;
                while ((read = input.read(buffer)) != -1) {
                    if (read > 0) {
                        output.write(
                            buffer, 0, read
                        );
                    }
                }
                output.flush();
            }
        }
    }
}
```

**This snippet omits real authentication and authorization**, as those belong to your framework and business context. Never deploy a public download endpoint using only the streaming example.

### 24.2. Avoid Returning JSON Errors After Streaming Has Started

If reading chunk 100 fails after the HTTP response has already sent 99 chunks, the server **cannot go back** and send a clean JSON error response at the start of the body. Typically you must abort the connection and record metrics; the client sees an interrupted download.

To detect corrupted files earlier, validate metadata/chunks beforehand or verify checksums upon completion, while still designing clients to handle partial downloads.

### 24.3. HTTP Headers Must Be Safe

Never write directly:

```text
Content-Disposition: attachment; filename=<client-supplied-name>
```

if the name can contain CRLF, quotes, path separators, or unencoded Unicode. Use proper header-escaping/encoding libraries and an application filename policy.

### 24.4. Which HTTP Streaming Framework Should You Use?

- Servlet/Spring MVC: `OutputStream` or `StreamingResponseBody`.
- Reactive stack: use the appropriate **Reactive Streams driver/GridFS APIs**; never wrap the blocking Sync Driver inside an event-loop thread and call it non-blocking.
- With external object storage, you can return a signed URL if architecture permits, though that is a different workflow.

---

## 25. HTTP Range Requests and Partial File Downloads

A browser/video player may send:

```http
Range: bytes=1000000-1999999
```

This requests **a byte slice** of the file rather than the complete file.

GridFS allows reading parts of a file without loading the entire file into memory. However:

- Do not assume a basic GridFS streaming endpoint automatically supports **HTTP 206 Partial Content**.
- You must parse/validate `Range`, support single or multi-range per policy, and handle `416 Range Not Satisfiable`.
- You must return proper `Content-Range`, `Content-Length`, and `Accept-Ranges` headers.
- Ensure only the exact requested byte count is written.
- Compute chunk positions and offsets or use stream/seek APIs supported by your driver version.
- Evaluate the cost of frequent skip/seek operations, especially with large chunk sizes.
- If using `ETag`/`If-Range`, ensure clear file-identity and checksum semantics.

### 25.1. Chunk Index Formula

Given chunk size `C` and 0-based byte offset `B`:

```text
chunkIndex        = floor(B / C)
offsetWithinChunk = B % C
```

Example with `C = 261120` bytes and `B = 600000`:

```text
chunkIndex = floor(600000 / 261120) = 2
offset     = 600000 - (2 * 261120) = 77760
```

This formula explains file layout. **Do not query raw chunks directly in normal endpoints** when the driver provides file-reading APIs; apply custom range logic only when truly needed and tested.

### 25.2. When to Use a CDN or Object Storage?

If an application serves large videos to many concurrent clients requiring streaming, partial ranges, CDN, cache invalidation, and high bandwidth, dedicated object storage/CDN is often a better fit. GridFS can still serve as the data source when MongoDB storage is required, but benchmark carefully.

---

## 26. Durability, Replication, and Failover

A GridFS file consists of **multiple MongoDB documents**. This has implications:

- Each chunk insert is a MongoDB write operation.
- File metadata is written after the upload completes per driver behavior.
- A primary election can occur mid-upload.
- Read/write concerns govern durability and visibility.
- There is no single transaction spanning all chunks + file metadata.

### 26.1. Majority Write Concern

The MongoDB Java Sync Driver recommends uploading with:

```java
MongoDatabase majorityDatabase =
    database.withWriteConcern(
        com.mongodb.WriteConcern.MAJORITY
    );

GridFSBucket durableBucket =
    GridFSBuckets.create(
        majorityDatabase,
        "attachments"
    );
```

Do not treat a file uploaded with `w:1` as guaranteed durable across failover. Specifically with GridFS, some chunks can roll back independently if failover occurs mid-stream.

### 26.2. Read Concern

Metadata may already be visible at a given read level, yet if chunks are missing due to errors or rollback, streaming downloads can fail. Never assume that because `fs.files` exists, the binary payload is intact in every failure scenario.

### 26.3. Do Not Put GridFS Operations Inside a Multi-Document Transaction

The MongoDB Manual explicitly states that GridFS **does not support multi-document transactions**. A large upload spans many documents and considerable duration, so do not try to open a transaction and write chunks through the driver to force unsupported atomicity.

Instead, use **immutable file versions + an atomic pointer switch** on a business document once the new version finishes uploading and verification.

---

## 27. Versioning Design and Atomic Pointers

Suppose contract `CONTRACT-100` has an active PDF file.

Instead of uploading a new file to overwrite the old one:

```javascript
{
  _id: "CONTRACT-100",
  tenantId: "T100",
  currentFileId: ObjectId("6917a0000000000000000001"),
  businessVersion: 3
}
```

When updating the file:

1. Upload the new PDF to GridFS, obtaining `newFileId`.
2. Virus-scan/verify/checksum the new version.
3. If successful, update the **single contract document** to switch `currentFileId` to `newFileId`.
4. Let new readers use the new version.
5. Handle the old file according to retention policy in a separate job.

Example conditional atomic update:

```javascript
db.contracts.updateOne(
  {
    _id: "CONTRACT-100",
    currentFileId: oldFileId,
    businessVersion: 3
  },
  {
    $set: {
      currentFileId: newFileId,
      updatedAt: new Date()
    },
    $inc: {
      businessVersion: 1
    }
  }
);
```

If `matchedCount === 0`, another writer may have changed the version; do not immediately delete the new file or overwrite the pointer unconditionally.

**Strength:** the pointer switch is atomic at the document level, even though the preceding GridFS upload was not whole-file atomic.

### 27.1. Do Not Delete the Old File Too Early

Existing readers may have already resolved `oldFileId` and be mid-download. Deleting immediately can break in-flight downloads. Use a retention grace period or proper lease/reference counting.

---

## 28. Metadata vs. Business Version Differences

GridFS filename revisions:

```text
fileA name=contract.pdf time=10:00
fileB name=contract.pdf time=11:00
```

provide a mechanism to pick "the newest file by name."

However, **business versions** might be:

```text
contract version 3: Signed
contract version 4: Addendum amended
contract version 5: Cancelled
```

Do not assume upload order matches business state order. An older file might be re-uploaded for recovery; its `uploadDate` would be newer even though its business version is lower.

Therefore, store the business version in the business document or `metadata.businessVersion`, and use the exact `fileId` for each version.

---

## 29. Sharding and GridFS

MongoDB GridFS has two independent collections: `*.files` and `*.chunks`. In a sharded cluster, evaluate sharding for each collection separately.

### 29.1. `chunks` Collection

The MongoDB Manual describes common suitable shard key patterns for `chunks`:

```javascript
{ files_id: 1, n: 1 }
```

or:

```javascript
{ files_id: 1 }
```

Because `files_id` is often a coarsely time-increasing `ObjectId`, ranged sharding can create a write hotspot. Hashed sharding on `files_id` is viable under specific conditions compatible with driver behavior (especially when drivers do not use `filemd5` during upload).

**Do not blindly pick a hashed shard key assuming every driver/version supports it**; check constraints in the MongoDB Manual.

### 29.2. `files` Collection

`*.files` contains only metadata and is usually much smaller than `*.chunks`. The MongoDB Manual suggests considering **leaving `files` unsharded** if scale permits; if sharding `files` is required, use `_id` or combine with application fields per guidance.

### 29.3. Do Not Confuse Sharding with Splitting Files into Chunks

- GridFS chunks: splitting **one file** into multiple BSON documents.
- Shard key: deciding **which shard** holds which documents.
- A single file's chunks may be distributed across shards depending on shard key and placement.
- Downloads must fetch all chunks in order; latency may increase when reading across multiple shards.

---

## 30. Performance: Concurrent Files and Memory Budget

Suppose a service has:

```text
Concurrent uploads:   30
Chunk size:            1 MiB
Java copy buffer:     64 KiB
MongoDB connections:  per pool/driver
```

Total memory is not simply `30 × 64 KiB`, because the driver, buffering, BSON encoding/decoding, HTTP framework, and GC all consume memory. However, streaming **bounds memory by connection/buffer count** rather than scaling with the combined size of all files in flight.

### 30.1. Common Bottlenecks

- Disk I/O on the primary/shards.
- Replication bandwidth and majority acknowledgments.
- Network bandwidth between the app and MongoDB.
- Chunk document and index write amplification.
- Undersized connection pools.
- GC pressure caused by allocating too many byte arrays in application code.
- Chunk size too large or too small.
- Concurrent uploads exceeding quotas.
- Poorly compressible binary data inflating storage.
- Slow downloads caused by the HTTP client rather than MongoDB.
- Backup/restore processing huge chunk volumes.

### 30.2. Limiting Concurrency

Enforce semaphores/rate limits per tenant and globally. Never let a single user open hundreds of upload streams and starve the entire service's connection pool.

### 30.3. CSOT and `InputStream`

The Java Sync Driver supports **Client-Side Operation Timeout (CSOT)** for GridFS—for example, configuring `withTimeout(...)` on the bucket in supported versions.

The documentation notes: when `uploadFromStream()` reads from an `InputStream`, Java's `InputStream` has no built-in read timeout by default; a blocking stream can cause an operation to exceed the intended time limit before a timeout is thrown.

This means you need **timeouts at the HTTP/input source**, not just at the MongoDB operation layer.

---

## 31. Download Integrity: Detecting Files with Missing Chunks

A structurally valid GridFS file requires:

1. Consistent `length` and `chunkSize` metadata.
2. Contiguous chunk indices `n = 0, 1, ..., N-1` as expected.
3. All chunks except the last having size `chunkSize`.
4. Total reassembled bytes matching `length`.

### 31.1. Failure Scenario

Suppose metadata states:

```text
length = 600 KiB
chunkSize = 255 KiB
Expected n = 0, 1, 2
```

Yet `chunks` contains only `n=0` and `n=2`. The file is missing chunk `n=1`. The download driver may throw a missing-chunk or corruption error.

Do not "fix" it by reducing `length` to 345 KiB; that alters the file's meaning and leaves chunk ordering broken.

### 31.2. Detection and Handling

- Emit metrics for GridFS download failures.
- Verify chunk completeness and check the SHA-256 checksum.
- If a source of truth or backup exists, restore or re-upload the file per procedure.
- If the file was already served to a client, flag an integrity incident.
- Never synthesize missing bytes with zeros or concatenate out-of-order chunks.

---

## 32. Multi-Tenant Systems: Shared Bucket or Per-Tenant Buckets?

### 32.1. Shared Bucket

```text
attachments.files
attachments.chunks
  metadata.tenantId = T1/T2/T3
```

Pros:

- Fewer buckets/collections to administer.
- Centralized metadata queries and indexes.
- Easy to run a single shared GridFS service.

Cons:

- Must **enforce authorization on every endpoint**.
- A query by file ID alone does not filter by tenant.
- Per-tenant retention/backup is harder if strict physical isolation is required.

### 32.2. Per-Tenant Buckets

```text
tenantA.files, tenantA.chunks
tenantB.files, tenantB.chunks
```

This provides physical separation at the collection-naming level, but many tenants create many collections and indexes, increasing administrative overhead. Allowing user-supplied bucket names directly also risks injection or uncontrolled collection creation.

**There is no universal right choice.** Evaluate tenant count, quotas, isolation, compliance, backup, and index overhead.

### 32.3. A File ID Is Not an Authorization Token

Do not assume an unguessable ObjectId is sufficient security. With:

```text
GET /files/6917a0000000000000000001
```

the server must still verify the user has permission to read the file for that tenant and that the file is in a servable state.

---

## 33. Upload/Download Security

Minimum security checklist:

1. Enforce file size limits at the reverse proxy, web framework, and streaming layer.
2. Limit concurrent uploads per user/tenant.
3. Validate file type and magic-byte signatures.
4. Scan for malware if the domain requires it.
5. Never trust client-supplied filenames.
6. Never use `filename` as a local filesystem path.
7. Restrict read/write permissions on GridFS buckets and metadata.
8. Never use file IDs as a substitute for access control.
9. Use TLS, authentication, and proper secret management.
10. Enforce quotas/disk alerts and retention policies.
11. Never log raw file content or sensitive data.
12. Set safe `Content-Disposition`/MIME types and `nosniff`.
13. Protect against path traversal, CRLF injection, and malicious filenames.
14. Consider encryption at rest and encryption in transit per requirements.
15. Publish `READY` state only after verification.
16. Enforce idempotency and retry budgets for uploads.
17. Audit downloads, deletions, and metadata changes.
18. Maintain backup/restore plans covering both `files` and `chunks`.

### 33.1. File Encryption

MongoDB provides storage-layer and transport-layer data protection. If business rules require **end-to-end encryption**, encrypt bytes in the application prior to upload and store algorithm/key-reference metadata. Plan for key rotation and streaming decryption on download.

Never store raw encryption keys inside the same file's `metadata`.

### 33.2. Malware Scanning and ZIP Bombs

A tiny ZIP archive can decompress into massive output. Do not check only the uploaded file's byte length while ignoring downstream unpacking limits. If the system generates PDF/image previews or extracts archives, run scanners/converters inside sandboxed environments with strict memory, CPU, and time limits.

---

## 34. Idempotency When Clients Retry Uploads

An HTTP client may retry due to a timeout at the end of an upload:

```text
Client sends POST /upload
Server finishes GridFS upload, receives fileId
Network drops before response arrives
Client retries the same request
Server uploads a brand new file
```

Result: two file IDs with identical bytes. GridFS **does not automatically detect that this is the same HTTP request**.

### 34.1. Idempotency Keys

One design:

```text
POST /uploads
Idempotency-Key: 8b7f...

Server:
  - writes upload request record with unique (tenantId, key)
  - checks PENDING/READY/FAILED state
  - uploads file
  - saves fileId and result
  - returns previous result when receiving a request with the same key
```

If a client retries with the same key but different content, never silently return "success" for the old file; compare content fingerprints/parameters per API contract.

### 34.2. Do Not Confuse Idempotency with Hash-Based Deduplication

Two requests with the same SHA-256 could be:

- The exact same document re-sent on retry.
- Two independent attachments with identical content belonging to two different contracts.
- Files governed by different retention/ownership policies.

Matching hashes do not mean you can omit a business file record. If deduplication is used, it requires reference counting, tenant isolation, and proper lifecycle handling.

---

## 35. Retention Management and Data Deletion

A document may require:

- Retention for 7 years per policy.
- Deletion upon data-subject request.
- Preservation under legal hold.
- Keeping previous versions for 30 days after a new upload.
- Temporary cleanup after failed uploads.

### 35.1. Metadata-Driven Lifecycle Jobs

```javascript
db.getSiblingDB("files_demo")
  .attachments.files
  .find({
    "metadata.state": "EXPIRED",
    "metadata.legalHold": { $ne: true }
  });
```

The job retrieves the file ID and calls:

```java
bucket.delete(fileId);
```

Do not rely on a TTL index on `*.files` as an automatic way to delete chunks. If `delete` fails, the job must retry/reconcile.

### 35.2. Soft Delete vs. Physical Delete

A file can be marked:

```javascript
metadata: {
  state: "DELETED",
  deletedAt: ISODate("2026-11-14T08:00:00Z")
}
```

Soft delete only blocks access at the application layer; the binary bytes **still exist** until `delete(fileId)` is called. For true deletion requirements, enforce physical cleanup, account for backup retention, and maintain audit logs.

---

## 36. GridFS Backup and Restore

A valid backup must capture **both collections** of the bucket:

```text
attachments.files
attachments.chunks
```

If you back up only `attachments.files`:

- You have filenames, lengths, and metadata.
- You have **no bytes** to download.

If you back up only `attachments.chunks`:

- You have binary chunks.
- You lack file metadata to identify complete files, filenames, and lengths per the GridFS contract.

### 36.1. Backup Consistency

Because uploads write chunks and then metadata across multiple operations, snapshots/backups must use a MongoDB-supported consistent backup mechanism to avoid torn states. During restore tests, verify random samples of file lengths/checksums, file metadata counts, and orphan status.

### 36.2. Restoring to Another Environment

When restoring backups across environments, restore the exact bucket name, IDs, metadata, indexes, and permissions; never assume `fs.files` is the `attachments` bucket. After restore, run integrity checks and do not expose unverified files.

---

## 37. Operational Observability: Metrics to Track

| Metric | Meaning |
| --- | --- |
| Uploads started/succeeded/failed | Upload success rate |
| Downloads started/succeeded/failed | Download success rate |
| Upload/download bytes per second | Bandwidth |
| File size distribution | Capacity and chunk sizing |
| Average chunks per file | `chunkSize` impact |
| Upload/download p50/p95/p99 | Actual latency |
| Active upload/download streams | Concurrency pressure |
| Connection pool utilization | Pool exhaustion risk |
| GridFS `chunks` collection size | Storage growth |
| Orphaned chunk candidates | Cleanup backlog |
| Metadata state age | Files stuck in `PENDING`/`SCANNING` |
| SHA-256 verification failures | Potential data corruption |
| Retry/idempotency conflicts | Duplicate or inconsistent requests |
| Files missing business pointers | Dangling files |
| Business pointers to missing files | Broken references |
| Replica lag/write concern timeouts | Durability/availability |
| Quota utilization | Resource exhaustion risk |

### 37.1. Do Not Use File Count Alone to Measure Storage

A bucket with 10 million 1 KiB files is completely different from a bucket with 10,000 10 GiB files. Track **bytes, chunk count, and retention**, not just `countDocuments()` on `*.files`.

---

## 38. Frequently Asked Operational Questions

### 38.1. Upload Succeeded, Why Is the File Missing from the List?

Check:

- Is the bucket name right (`fs` vs. `attachments`)?
- Is the database right?
- Was the file metadata finalized?
- Do `metadata.tenantId`/`status` filters match?
- Is the application filtering for `READY` while metadata is still `SCANNING`?
- Is read preference/replication lag affecting visibility?
- Is `fileId` the right BSON type?

### 38.2. Why Can't the File Be Downloaded Even Though Metadata Exists?

Possible causes:

- Wrong file ID.
- Missing/corrupted chunks.
- Wrong bucket name/database.
- Metadata record edited directly.
- Authorization blocked it.
- Data rolled back/missing due to write concern issues.
- Restore omitted `*.chunks`.

### 38.3. Why Are There Multiple Files with the Same Name?

That is normal GridFS behavior; every upload creates a new file ID/version. Use `find` and `GridFSDownloadOptions.revision(...)`, or store a business pointer.

### 38.4. Can Metadata Be Added After Upload?

Yes. Update `metadata.<field>` in `*.files`, without altering system fields like `length` or `chunkSize`. If a checksum is computed during a single-pass stream, it can be added afterward and the state transitioned to `READY` once verification completes.

### 38.5. Does Renaming Move or Re-Encode Bytes?

No. GridFS `rename(fileId, name)` changes only the filename metadata of a single file; it does not re-upload content.

### 38.6. Is Deleting `fs.files` with `deleteOne` Enough?

No. It does not invoke GridFS logic to remove all chunks. Use `GridFSBucket.delete(fileId)`; if raw metadata was already deleted, run a safe orphan-cleanup workflow.

---

## 39. Hands-On Exercises

### Exercise 1 — Determining Chunk Count

A 600 KiB file is uploaded with `chunkSize` 255 KiB.

**Question:** How many chunks are created, and what is the size of each chunk?

**Answer:** 3 chunks: 255 KiB, 255 KiB, and 90 KiB.

### Exercise 2 — Two Collections

The default bucket `fs` is stored in database `training`.

**Question:** What are the names of the two collections?

**Answer:** `training.fs.files` and `training.fs.chunks`.

### Exercise 3 — Custom Bucket Name

Java:

```java
GridFSBuckets.create(database, "documents");
```

**Question:** What are the collections?

**Answer:** `documents.files` and `documents.chunks` in that database.

### Exercise 4 — Chunk Sequence Number

A chunk has `n: 0`.

**Question:** Which chunk is it?

**Answer:** The first chunk; numbering starts at 0.

### Exercise 5 — Downloading a Large File

A developer writes:

```java
byte[] data = new byte[(int) gridFSFile.getLength()];
```

**Question:** What are the risks?

**Answer:** Overflow when `length` > `Integer.MAX_VALUE`, OOM, and non-streaming behavior. Use `openDownloadStream` and a small buffer.

### Exercise 6 — MIME Metadata

A team writes `contentType` at the top level of `fs.files`.

**Question:** What is the modern recommendation?

**Answer:** Top-level `contentType` is deprecated; use `metadata.contentType` and validate MIME types.

### Exercise 7 — MD5

A file needs a checksum to detect data corruption.

**Question:** Should you rely solely on `fs.files.md5`?

**Answer:** No. MD5 is deprecated; the application should compute SHA-256 or a suitable digest and store it in `metadata`.

### Exercise 8 — Revisions

`"report.pdf"` is uploaded three times chronologically. Which files do revision `0` and `-1` return?

**Answer:** Revision `0` is the oldest version; `-1` is the newest version.

### Exercise 9 — Updating a File

You want new users to see version 4 while existing readers can still finish downloading version 3.

**Hint:** Upload version 4 under a new file ID, verify it, atomically update the pointer in the business document, and retain version 3 per retention policy.

### Exercise 10 — Mid-Upload Failure

An upload fails after three chunks and before `fs.files` metadata is written.

**Question:** What may be left behind?

**Answer:** Orphaned chunks; clean them up safely without deleting chunks of active uploads.

### Exercise 11 — TTL

A team creates a TTL index on `fs.files.uploadDate` to delete files after 7 days.

**Question:** What is the problem?

**Answer:** Only metadata documents are TTL-deleted; chunks are not automatically deleted via the GridFS API. Use a lifecycle job calling `bucket.delete`.

### Exercise 12 — Renaming

Two file IDs A and B share the same name. A developer calls `rename(A, "new.pdf")`.

**Question:** Is B renamed?

**Answer:** No; only file A.

### Exercise 13 — `chunks` Index

You need to maintain ordering and uniqueness of chunks per file.

**Answer:** Unique index `{files_id:1,n:1}`.

### Exercise 14 — Metadata Index

A UI lists files by tenant/status/newest.

**Hint:** Test a compound index `{"metadata.tenantId":1, "metadata.state":1, uploadDate:-1}` and run `explain` against the workload.

### Exercise 15 — Tenant Isolation

A user knows the ObjectId of a file belonging to another tenant.

**Question:** Should they be allowed to download it just because the ID is valid?

**Answer:** No. Verify permissions from the authenticated context and metadata/business ACLs.

### Exercise 16 — Single-Pass Checksum

An input stream can only be read once; the checksum is only complete after upload finishes.

**Hint:** Compute the digest while streaming, update metadata after upload succeeds, transition to `READY` only after verification, and handle the update window.

### Exercise 17 — Mid-Stream HTTP Error

The server has already written 3 MiB to the client when it discovers the next chunk is missing.

**Question:** Can it return a clean JSON 500 response?

**Answer:** You cannot replace a body already sent. Abort/close the connection, log the error, and let the client handle partial downloads.

### Exercise 18 — Empty File

A file is 0 bytes.

**Question:** Must a 255 KiB chunk data document be created?

**Answer:** No. An empty file has metadata with `length: 0` and needs no chunk documents.

### Exercise 19 — Sharding

A team wants to use `location: "2dsphere"` as the shard key for `fs.chunks`.

**Answer:** Unsuitable. GridFS `chunks` requires specific key patterns; inspect `files_id` and `n` per the GridFS sharding guidelines.

### Exercise 20 — File Storage vs. Object Storage

An application serves 10 GiB videos globally with CDN, range requests, and transcoding.

**Hint:** Evaluate dedicated object storage/CDN versus GridFS; do not choose GridFS merely because MongoDB is already running.

---

## 40. Misconceptions to Avoid

| Misconception | Correct Understanding |
| --- | --- |
| "GridFS is a single collection." | It is a bucket made of `files` and `chunks` collections. |
| "GridFS files must still be under 16 MiB." | Each chunk document is subject to the BSON limit; the overall file can be much larger. |
| "Every file is always split into full 255 KiB chunks." | The last chunk can be smaller; an empty file may have zero chunks. |
| "Receiving an ID at upload start means it succeeded." | Wait for upload/finalization to finish and handle exceptions. |
| "GridFS supports multi-document transactions." | No; application-level consistency patterns are required. |
| "Failed uploads always roll back completely." | Orphaned chunks may remain. |
| "Deleting `fs.files` cascades to `fs.chunks`." | No; use GridFS delete/cleanup workflows. |
| "TTL on `fs.files` deletes the binary data." | No; TTL deletes only metadata documents. |
| "Filename is a unique key." | Multiple versions can share the same filename. |
| "Revision 0 is the newest." | Revision 0 is the oldest; `-1` is the newest. |
| "GridFS always generates MD5 and it is secure enough." | MD5 is deprecated; use application hashes like SHA-256. |
| "`contentType` must be top-level." | That legacy field is deprecated; store it in `metadata`. |
| "Client `Content-Type` proves a file is a PDF." | Validate bytes/file signatures per policy. |
| "`InputStream` streaming always holds the whole file in RAM." | It can process data in small chunks/buffers. |
| "A single `InputStream.read(bytes)` always fills the buffer." | No; you must loop. |
| "`downloadToStream` returns data in chunk ObjectId order." | GridFS orders by `n`. |
| "Updating `length` fixes a corrupted file." | No; it can worsen GridFS corruption. |
| "`WriteConcern` `w:1` is always safe across elections." | Chunks can roll back; drivers recommend `majority`. |
| "Having file metadata means all chunks are guaranteed intact." | Account for partial failures, rollbacks, and corruption. |
| "Every download-by-ID request is authorized." | An ID does not replace authorization. |
| "A GridFSBucket is an all-purpose object storage/CDN." | Benchmark against streaming/range/global delivery requirements. |
| "Renaming a file alters its bytes." | `rename` only changes the filename metadata. |
| "Creating a `MongoClient` per request is fine." | Causes connection churn and pool overhead. |
| "Larger chunk sizes are always faster." | Trade-offs exist across memory, index docs, range access, and concurrency. |
| "File count is a capacity metric." | Track bytes, chunk counts, and retention. |
| "Equal checksums mean two business files are one record." | Apply lifecycle, ownership, and tenant deduplication policies. |
| "Soft delete deletes the binary data." | Not yet; physical deletion per retention is required. |
| "Backing up `fs.files` is enough to restore." | You need consistent backups of both `files` and `chunks`. |
| "Upload success means the asset is `READY`." | Scanning, checksums, and approval may still be pending. |
| "Sync Driver upload from `InputStream` is non-blocking." | The Sync Driver is blocking; reactive workloads require reactive APIs. |

---

## 41. Production Checklist

1. Does GridFS fit the file sizes and access patterns?
2. Is object storage/CDN needed instead of or alongside GridFS?
3. Are the database and bucket name clearly defined?
4. Are the default `*.files` and `*.chunks` indexes guaranteed?
5. Is the chunk size suited to the workload and memory budget?
6. Are uploads truly streaming, without `readAllBytes` on large files?
7. Are downloads truly streaming, handling partial output?
8. Are input size limits enforced by actual bytes received?
9. Are file type/signature validation and malware scanning in place?
10. Are filenames sanitized and never used directly as local paths?
11. Is MIME placed in `metadata.contentType` and validated?
12. Are SHA-256/checksums and verification workflows implemented?
13. Are file IDs clearly distinguished from filenames/revisions?
14. Are versioning policies and atomic business pointers implemented?
15. Are `UPLOADING`/`SCANNING`/`READY`/`FAILED` states modeled?
16. Are retry/idempotency mechanisms ready for HTTP upload timeouts?
17. Is orphan-chunk cleanup implemented with a safe grace period?
18. Are deletions executed via `GridFSBucket.delete`, not TTL directly on `files`?
19. Are retention, legal hold, and backup/restore plans in place?
20. Is `majority` write concern configured on GridFS uploads?
21. Are primary elections, replica lag, and timeouts handled?
22. Is authorization enforced both when listing and when downloading by ID?
23. Are tenant isolation and data/throughput quotas enforced?
24. Are metadata indexes created for query/list workloads?
25. Are file/chunk counts, bytes, and upload/download p99 monitored?
26. Are concurrency limits and connection pool sizing configured?
27. If HTTP Range is required, are 206/416 contracts implemented properly?
28. Are response headers, `nosniff`, and filename encoding protected?
29. Are restored file checksums verified after backup?
30. Are mid-upload/mid-download failures and crash/failover scenarios tested?

Overall flow diagram:

```text
User sends file
      |
      v
Authenticate + authorize
      |
      v
Validate size/type/name
      |
      v
InputStream -> GridFSBucket
      |
      +--> *.chunks n=0,1,2,...
      |
      +--> *.files metadata
      |
      v
Upload success -> fileId
      |
      v
Scan/checksum/verify
      |
      v
Update state READY
      |
      v
Atomic business pointer
      |
      v
Download by authorized fileId
      |
      v
GridFSDownloadStream -> HTTP OutputStream
      |
      v
Client receives bytes
```

---

## 42. Official Documentation and References

- [GridFS — MongoDB Manual](https://www.mongodb.com/docs/manual/core/gridfs/): mechanism, two collections, default chunk size, indexes, transactions, and usage criteria.
- [Large File Storage with GridFS — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/): creating `GridFSBucket`, streaming upload/download, metadata, revisions, rename/delete.
- [GridFS Specification](https://github.com/mongodb/specifications/tree/master/source/gridfs): cross-driver contract and `files`/`chunks` format.
- [Java GridFSBucket API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/mongodb-driver-sync/com/mongodb/client/gridfs/GridFSBucket.html): upload/download overloads and bucket configuration; pick the API version matching your dependency.
- [Java GridFSUploadOptions API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/mongodb-driver-sync/com/mongodb/client/gridfs/model/GridFSUploadOptions.html): chunk size and metadata.
- [Java GridFSDownloadOptions API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/mongodb-driver-sync/com/mongodb/client/gridfs/model/GridFSDownloadOptions.html): revision selection when downloading by filename.
- [Client-Side Operation Timeout — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/): GridFS timeouts and `InputStream` timeout limitations.
- [Write Concern — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/write-concern/): `w: "majority"` and durability.
- [BSON Document Size](https://www.mongodb.com/docs/manual/reference/limits/#bson-document-size): 16 MiB per-BSON-document limit.
- [ObjectId](https://www.mongodb.com/docs/manual/reference/bson-types/#objectid): ID, BSON type, and uniqueness notes.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/): compound index principles and index maintenance cost.
- [MongoDB Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/): preserving collection data in a recoverable state.

MongoDB Server and Java Sync Driver documentation can change across releases. Before going to production, verify the exact **server version, driver version, topology, GridFS bucket name, and write/read concern** of your operating environment.

## 43. Conclusion

**GridFS** stores large files as multiple `chunks` and a metadata document in `files`. The default `fs` bucket creates `fs.files` and `fs.chunks`; the default chunk size is **255 KiB**, read order follows `n`, and files are identified by `_id` rather than `filename`.

With the **Java Sync Driver**, you can upload via `uploadFromStream(InputStream)` or write directly to `GridFSUploadStream`, and download via `downloadToStream(OutputStream)` or read from `GridFSDownloadStream`. Streaming design lets you process very large files without loading all bytes onto the heap.

**Metadata** should store tenant/owner, MIME type, business ID, SHA-256 checksum, version, and `READY` state inside `metadata`, avoiding deprecated legacy fields such as top-level `contentType` or `md5`. Downloading by filename requires understanding revisions: `0` is the oldest version and `-1` is the newest.

Finally, because GridFS **does not support multi-document transactions**, mid-flight upload or delete failures can leave partial chunks behind. Production systems need **majority write concern**, idempotency, checksums, scanning, orphan cleanup, immutable file versions, and atomic business pointers. Downloads also require authorization, MIME/header safety, and proper HTTP partial-response handling.

**GridFS solves chunked file storage and streaming; the application must still design lifecycle, consistency, access control, and recovery so that files are truly reliable.**
