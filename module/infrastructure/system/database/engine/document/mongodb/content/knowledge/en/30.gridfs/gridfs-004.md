# Range Reads, Filename Management, and Multiple Versions with MongoDB GridFS

## Lesson Objectives

**MongoDB GridFS** is a convention for storing and retrieving file contents by splitting bytes into multiple **chunks** and keeping metadata in separate documents. Users commonly learn about GridFS when they need to store files larger than the **16 MiB** BSON document limit, yet three capabilities make GridFS especially useful for real-world applications:

1. **Byte-range reads** (partial/range reads): streaming video, playing audio, resuming interrupted downloads, or reading only a header or a document slice.
2. **Filename management**: searching by name, renaming, distinguishing display names from file identifiers, and handling multiple files with the same name.
3. **Multi-version management**: storing multiple uploads under the same name, selecting old/new revisions or pinning to an exact `fileId`, restoring, and deleting according to policy.

This lesson belongs to **Database Engine Document MongoDB → GridFS → Range Reads, Filename Management, and Multiple Versions**.

After this lesson, you will be able to:

- Describe the `fs.files`/`fs.chunks` structure and the `files_id + n` relationship.
- Calculate the chunks containing a byte range and handle file start/end boundaries.
- Use GridFS streams to skip leading bytes and read the exact requested byte count instead of loading the entire file into RAM.
- Map HTTP `Range` requests to GridFS and distinguish `200`, `206`, and `416` responses.
- Use `GridFSBucket`, `GridFSDownloadStream`, and `GridFSDownloadOptions` from the Java Sync Driver.
- Download by `fileId` or by `filename`, choosing revisions `0`, `1`, `-1`, and `-2`.
- Rename and delete a single specific version by ID without accidentally deleting all versions sharing the same name.
- Design logical assets + immutable file versions + active pointers to avoid overwrites during concurrent uploads.
- Build metadata search indexes, retention policies, integrity checks, and authorization.
- Identify risks from incomplete uploads, deleting while readers are active, corrupted chunks, and GridFS transaction limits.
- Compare GridFS against BSON `BinData`, object storage, CDN, and cases where GridFS should not be used.
- Test range requests, concurrency, zero-length files, revision ordering, and caching/ETags.

> **Most important principle:** `filename` is a **display label, not a unique key**. Each upload must have its own `fileId`. Whenever you need to read an exact version or perform controlled deletions/renames, prefer operating by `fileId`.

---

## 1. Why Does GridFS Split Files into Chunks?

### 1.1. BSON Document Limit

MongoDB caps the size of a single BSON document at **16 MiB**. A PDF, video, or archive file can easily exceed that limit. You cannot arbitrarily place an entire 200 MiB file into a `BinData` field inside one document.

GridFS stores:

~~~text
user file: video.mp4 (many MiB)
              |
              v
       GridFS upload API
              |
       +------+------+
       |             |
       v             v
   fs.files       fs.chunks
   1 document     N documents
   metadata       binary pieces
~~~

### 1.2. What Is a Bucket?

A bucket is a pair of collections sharing the same prefix:

| Bucket name | Metadata collection | Data collection |
|---|---|---|
| `fs` (default) | `fs.files` | `fs.chunks` |
| `attachments` | `attachments.files` | `attachments.chunks` |
| `videos` | `videos.files` | `videos.chunks` |

A single database can contain multiple buckets. A bucket name is an organizational grouping, **not an automatic tenant authorization boundary**.

### 1.3. Default Chunk Size

GridFS uses a default chunk size of **255 KiB**:

\[
C = 255 \times 1024 = 261\,120\text{ bytes}
\]

Every chunk is full except the last one; the last chunk holds only the remaining bytes. An empty file has an `fs.files` document with `length:0` and **needs no empty chunk**.

### 1.4. Metadata in `fs.files`

Example (illustrative ObjectId):

~~~javascript
{
  _id: ObjectId("6914a9aa0000000000000001"),
  length: NumberLong("600000"),
  chunkSize: 261120,
  uploadDate: ISODate("2026-11-14T02:30:00Z"),
  filename: "training.mp4",
  metadata: {
    tenantId: "tenant-a",
    assetId: "ASSET-101",
    logicalVersion: 1,
    contentType: "video/mp4",
    sha256: "application-computed-hash",
    uploadedBy: "user-101"
  }
}
~~~

Core fields:

| Field | Role |
|---|---|
| `_id` | Unique identifier of **one uploaded GridFS content item** |
| `length` | Logical size of the file, in bytes |
| `chunkSize` | Target number of bytes per chunk |
| `uploadDate` | Timestamp when upload metadata was created |
| `filename` | Filename; can **repeat** across multiple documents |
| `metadata` | Application-defined extended attributes |

**Note:** Legacy fields such as `md5`, top-level `contentType`, and `aliases` are marked deprecated by the GridFS spec. Prefer `metadata.contentType`/`metadata.aliases` and an application-managed strong checksum when needed.

### 1.5. Chunks in `fs.chunks`

~~~javascript
{
  _id: ObjectId("6914b0bb0000000000000001"),
  files_id: ObjectId("6914a9aa0000000000000001"),
  n: 0,
  data: BinData(0, "...")
}

{
  _id: ObjectId("6914b0bb0000000000000002"),
  files_id: ObjectId("6914a9aa0000000000000001"),
  n: 1,
  data: BinData(0, "...")
}

{
  _id: ObjectId("6914b0bb0000000000000003"),
  files_id: ObjectId("6914a9aa0000000000000001"),
  n: 2,
  data: BinData(0, "...")
}
~~~

`files_id` links to `fs.files._id`; `n` is the sequence number **starting from 0**. The GridFS driver reassembles chunks by `n` to reconstruct the byte stream.

### 1.6. GridFS Chunks Differ from Sharding Chunks

The term "chunk" here refers to a **data piece of a file**. It is **not** the chunk/range concept used for data partitioning in a MongoDB sharded cluster.

---

## 2. How Is a 600,000-Byte File Split?

With the default chunk size:

~~~text
File length L = 600000 bytes
Chunk size C = 261120 bytes

Chunk n=0: bytes 0      .. 261119   => 261120 bytes
Chunk n=1: bytes 261120 .. 522239   => 261120 bytes
Chunk n=2: bytes 522240 .. 599999   =>  77760 bytes
~~~

Total:

\[
261120 + 261120 + 77760 = 600000
\]

### 2.1. Number of Chunks Stored

For `L > 0`:

\[
N = \left\lceil \frac{L}{C} \right\rceil
\]

For `L=0`, the chunk count is 0.

Examples:

| File size | Chunk count, if C=261120 |
|---:|---:|
| 0 B | 0 |
| 1 B | 1 |
| 261119 B | 1 |
| 261120 B | 1 |
| 261121 B | 2 |
| 522240 B | 2 |
| 600000 B | 3 |

### 2.2. Large Files Do Not Need to Be Loaded Entirely into RAM

When reading via stream, the application can fetch one chunk at a time and flush it progressively to the HTTP response/output stream. This avoids:

~~~java
byte[] entireFile = new byte[(int) fileLength];
~~~

That snippet both consumes RAM proportional to the file size and risks integer overflow/invalid allocation if the file exceeds `int` limits.

### 2.3. Each File Has Its Own `chunkSize`

`fs.files.chunkSize` is stored **per file**. If the application changes the default chunk size, previously uploaded files are not automatically re-chunked. When computing ranges, always read `chunkSize` from the actual file document rather than hard-coding a global 255 KiB.

---

## 3. What Is a Byte-Range Read?

Suppose a user wants to jump to the 20th second of a video, so the player only needs the corresponding byte segment. Or a file viewer needs the first 4 KiB to inspect a header.

No need to download the entire file:

~~~text
File: [..................................................]
      0                                               L-1

Range to read:
                [==========]
                start       end
~~~

### 3.1. Two Common Interval Conventions

In internal byte processing, use **half-open** intervals:

\[
[start,\ endExclusive)
\]

Byte count:

\[
length = endExclusive - start
\]

In HTTP `Range: bytes=a-b`, both start and end are **inclusive**:

\[
[a,\ b]
\]

Byte count:

\[
length = b - a + 1
\]

### 3.2. Example of a Range

~~~http
GET /files/6914a9aa0000000000000001 HTTP/1.1
Range: bytes=1000-1999
~~~

If valid, response:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 1000-1999/600000
Content-Length: 1000
Content-Type: video/mp4
~~~

The backend must send **exactly 1,000 bytes** at offsets 1000 through 1999. Do not send 1,001 bytes due to an off-by-one boundary error.

### 3.3. Three Common Range Forms

| Header | Meaning |
|---|---|
| `bytes=0-1023` | First 1,024 bytes |
| `bytes=500-` | From byte 500 to the end |
| `bytes=-500` | Last 500 bytes |
| `bytes=0-0` | Only the first byte |

`bytes=-500` is **not** a negative offset; it is a suffix-range form.

### 3.4. HTTP Range vs. API-Level `skip`

HTTP expresses the client's request. The GridFS driver provides a **streaming reader**; the HTTP application must translate the header into an offset and byte count, and construct the matching HTTP status and headers.

---

## 4. Formulas to Determine the Chunks Containing a Range

Suppose:

- `L` = file size.
- `C` = `chunkSize` in `fs.files`.
- `a` = **inclusive** start offset.
- `b` = **inclusive** end offset.

Condition for a non-empty file:

\[
0 \leq a \leq b < L
\]

First chunk:

\[
firstChunk = \left\lfloor \frac{a}{C} \right\rfloor
\]

Last chunk:

\[
lastChunk = \left\lfloor \frac{b}{C} \right\rfloor
\]

Offset inside the first chunk:

\[
offsetInFirst = a \bmod C
\]

### 4.1. Example Crossing a Chunk Boundary

With a 600,000 B file and C=261120:

~~~text
Request: bytes=260000-263000

Chunk 0: [0 ........ 261119]
                  ^ from 260000
Chunk 1: [261120 ......... 522239]
          ^ to 263000

firstChunk = floor(260000 / 261120) = 0
lastChunk  = floor(263000 / 261120) = 1

From Chunk 0: 261120 - 260000 = 1120 bytes
From Chunk 1: 263000 - 261120 + 1 = 1881 bytes

Total = 3001 bytes
~~~

### 4.2. Example Contained Within One Chunk

~~~text
Range: bytes=270000-275000

firstChunk = 1
lastChunk  = 1
offsetInFirst = 270000 - 261120 = 8880
length = 5001 bytes
~~~

Without understanding chunk boundaries, it is easy to fetch the wrong chunk or introduce off-by-one bugs.

### 4.3. Direct Retrieval at the Data-Model Level

At the data level:

~~~javascript
db.fs.chunks.find({
  files_id: fileId,
  n: {
    $gte: firstChunk,
    $lte: lastChunk
  }
}).sort({ n: 1 });
~~~

This example explains chunk math, **not as advice to reimplement the entire GridFS driver yourself**. The driver also checks chunk order, chunk sizes, read errors, and compatibility details. For regular application code, prefer the driver's streaming API.

### 4.4. Reading Only a Slice Does Not Verify the Whole File

If a client reads only up to byte 1023 and closes the stream, the driver will not detect corruption in later chunks. The GridFS spec requires validating the order/size of chunks **that were read**, so a partial range read alone does not prove the entire file is intact.

---

## 5. Java `GridFSDownloadStream` and `skip(long)`

### 5.1. Creating a GridFS Bucket

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSBuckets;

MongoDatabase db = mongoClient.getDatabase("media_lab");

GridFSBucket bucket = GridFSBuckets.create(
    db,
    "media"
);
~~~

A bucket named `media` uses the two collections `media.files` and `media.chunks`.

### 5.2. Opening a Stream by ID

~~~java
import com.mongodb.client.gridfs.GridFSDownloadStream;
import org.bson.types.ObjectId;

ObjectId fileId =
    new ObjectId("6914a9aa0000000000000001");

try (GridFSDownloadStream input =
         bucket.openDownloadStream(fileId)) {

    long fileLength =
        input.getGridFSFile().getLength();

    System.out.println("File length: " + fileLength);
}
~~~

`GridFSDownloadStream` is a readable stream; it must be closed when finished, even if the client disconnects.

### 5.3. `skip` May Not Skip All Requested Bytes in One Call

The `InputStream.skip(n)` contract allows returning fewer than `n` bytes skipped. Correct code must never just write:

~~~java
input.skip(start); // Not guaranteed to skip all start bytes.
~~~

and immediately read.

Always check how many bytes were actually skipped.

### 5.4. `skipFully` Helper

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

static void skipFully(
        InputStream input,
        long bytesToSkip) throws IOException {

    if (bytesToSkip < 0) {
        throw new IllegalArgumentException(
            "Offset cannot be negative"
        );
    }

    long remaining = bytesToSkip;

    while (remaining > 0) {
        long moved = input.skip(remaining);

        if (moved <= 0) {
            // Fallback to advance by one byte.
            if (input.read() == -1) {
                throw new EOFException(
                    "EOF before target offset"
                );
            }

            moved = 1;
        }

        remaining -= moved;
    }
}
~~~

This code ensures the stream advances to the target offset when sufficient data exists. Whether the driver optimizes chunk seeking depends on the implementation; never claim `skip` is always $O(1)$ or never touches earlier chunks. Measure real I/O if workloads frequently read at very large offsets.

### 5.5. Helper to Read an Exact Byte Count

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

static void copyExactly(
        InputStream input,
        OutputStream output,
        long count) throws IOException {

    if (count < 0) {
        throw new IllegalArgumentException(
            "Invalid byte count to read"
        );
    }

    byte[] buffer = new byte[64 * 1024];
    long remaining = count;

    while (remaining > 0) {
        int wanted = (int) Math.min(
            buffer.length,
            remaining
        );

        int read = input.read(
            buffer, 0, wanted
        );

        if (read == -1) {
            throw new EOFException(
                "GridFS missing bytes in requested range"
            );
        }

        if (read == 0) {
            continue;
        }

        output.write(buffer, 0, read);
        remaining -= read;
    }
}
~~~

### 5.6. Combining Them to Read a Range

~~~java
import com.mongodb.client.gridfs.GridFSDownloadStream;
import java.io.IOException;
import java.io.OutputStream;
import org.bson.types.ObjectId;

static void streamRange(
        GridFSBucket bucket,
        ObjectId fileId,
        long start,
        long endInclusive,
        OutputStream output) throws IOException {

    if (start < 0 || endInclusive < start) {
        throw new IllegalArgumentException(
            "Invalid read range"
        );
    }

    try (GridFSDownloadStream input =
             bucket.openDownloadStream(fileId)) {

        long total =
            input.getGridFSFile().getLength();

        if (start >= total
                || endInclusive >= total) {
            throw new IllegalArgumentException(
                "Range out of file bounds"
            );
        }

        skipFully(input, start);

        long count =
            endInclusive - start + 1;

        copyExactly(input, output, count);
    }
}
~~~

Key points:

- Use `long` for offsets and lengths.
- Do not allocate a byte array the size of the entire file.
- Verify `endInclusive < total`.
- Count the exact number of bytes.
- Open a separate stream per request.
- `try-with-resources` closes the stream on completion or error.
- Errors mid-HTTP-stream can occur after headers were already sent, making it impossible to switch to `500`; record metrics and terminate the connection cleanly.

### 5.7. `downloadToStream` vs. `openDownloadStream`

`bucket.downloadToStream(id, output)` is convenient for downloading the **entire** file to an output stream. When partial ranges are needed, `openDownloadStream` with stream positioning/reading is usually more flexible.

Do not call `downloadToStream` into a `ByteArrayOutputStream` just to slice out a few bytes: that defeats streaming.

---

## 6. HTTP Range: Mapping `200`, `206`, and `416` Properly

### 6.1. Full File: HTTP 200

Request without `Range`:

~~~http
GET /api/files/6914a9aa0000000000000001 HTTP/1.1
~~~

Response:

~~~http
HTTP/1.1 200 OK
Accept-Ranges: bytes
Content-Length: 600000
Content-Type: application/octet-stream
ETag: "6914a9aa0000000000000001"
~~~

The body contains all 600,000 bytes.

### 6.2. Partial File: HTTP 206

~~~http
GET /api/files/6914a9aa0000000000000001 HTTP/1.1
Range: bytes=260000-263000
~~~

Response:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 260000-263000/600000
Content-Length: 3001
Content-Type: application/octet-stream
~~~

### 6.3. Unsatisfiable Range: HTTP 416

If the file length is 600,000 B:

~~~http
Range: bytes=700000-800000
~~~

avoid trying to skip past EOF. A standard response for an unsatisfiable byte range:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */600000
~~~

### 6.4. Empty File

`length=0`:

- There is no valid byte to satisfy `bytes=0-0`.
- A request without a range → `200` with `Content-Length:0`.
- A request with an unsatisfiable range → `416` with `Content-Range: bytes */0`.

### 6.5. Open-Ended Range

For `Range: bytes=500-`:

~~~text
start = 500
endInclusive = L - 1
count = L - 500
~~~

If `start >= L`, the range is unsatisfiable.

### 6.6. Suffix Range

`Range: bytes=-500`:

~~~text
count = min(500, L)
start = L - count
endInclusive = L - 1
~~~

For a 600,000 B file, this returns bytes 599500–599999.

### 6.7. When End Exceeds File Length

`Range: bytes=500-999999` with `L=600000` can still return bytes 500 through 599999 by clamping the end to the file length. Do not return `416` just because `end` exceeds `length` if `start` is valid.

### 6.8. Multiple Ranges

~~~http
Range: bytes=0-99,200-299
~~~

This is a **multi-range request**. To satisfy it fully, the server needs `multipart/byteranges` with a boundary, multiple `Content-Range` headers, and a properly formatted body.

If a gateway supports only single ranges, it may **ignore `Range` and return the full `200`** per HTTP semantics, rather than pretending to support multiple ranges while sending only one slice. Never return a malformed `206`.

---

## 7. Java: Planning a Safe HTTP Range

This function illustrates a parser for a single valid range. Separate **parsing + validation** from **GridFS reading** for easier testing.

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

record ByteRange(
    long start,
    long endInclusive,
    long total
) {
    long contentLength() {
        return endInclusive - start + 1;
    }

    String contentRange() {
        return "bytes " + start
            + "-" + endInclusive
            + "/" + total;
    }
}

static final Pattern SINGLE_RANGE =
    Pattern.compile("^bytes=(\\d*)-(\\d*)$");

static ByteRange parseSingleRange(
        String header,
        long total) {

    if (total < 0) {
        throw new IllegalArgumentException(
            "Invalid metadata length"
        );
    }

    Matcher matcher =
        SINGLE_RANGE.matcher(header.trim());

    if (!matcher.matches()) {
        throw new IllegalArgumentException(
            "Unsupported range syntax"
        );
    }

    String left = matcher.group(1);
    String right = matcher.group(2);

    if (left.isEmpty() && right.isEmpty()) {
        throw new IllegalArgumentException(
            "Range has no offset"
        );
    }

    if (total == 0) {
        throw new IllegalArgumentException(
            "Empty file has no valid byte range"
        );
    }

    if (left.isEmpty()) {
        long suffix = Long.parseLong(right);

        if (suffix <= 0) {
            throw new IllegalArgumentException(
                "Suffix length must be positive"
            );
        }

        long count = Math.min(suffix, total);

        return new ByteRange(
            total - count,
            total - 1,
            total
        );
    }

    long start = Long.parseLong(left);

    if (start >= total) {
        throw new IllegalArgumentException(
            "Start exceeds end of file"
        );
    }

    long end;

    if (right.isEmpty()) {
        end = total - 1;
    } else {
        long requestedEnd =
            Long.parseLong(right);

        if (requestedEnd < start) {
            throw new IllegalArgumentException(
                "End is smaller than start"
            );
        }

        end = Math.min(
            requestedEnd,
            total - 1
        );
    }

    return new ByteRange(start, end, total);
}
~~~

### 7.1. Classifying Parser Errors

- `IllegalArgumentException` can stem from an invalid or unsupported range.
- `NumberFormatException` occurs when a number is too large to fit in `long`.
- Do not blindly collapse all errors into HTTP `416`: malformed headers may be ignored or return `400` per policy, whereas **valid syntax that is unsatisfiable** is the canonical `416` case.
- This parser handles only **single ranges**, not multi-ranges.
- `Range` headers can be excessively long or crafted for DoS; enforce a length limit before parsing.
- When a client sends `If-Range`, the server must verify the validator; never return `206` from a different version if the `ETag`/`Last-Modified` does not match.

### 7.2. Decoupling the Parser from the HTTP Framework

A unit test can call `parseSingleRange("bytes=-500", 600000)` without MongoDB or a web server. This makes testing off-by-one and overflow bugs much easier than testing through the full controller.

---

## 8. Spring MVC: Skeleton for Returning HTTP Partial Content

The following example shows how to combine **GridFS streaming + HTTP Range** in Spring MVC. This is a skeleton for **single ranges**; production requires completing `If-Range`, multi-range policy, authorization, and MIME type handling. To keep the logic focused, `parseSingleRange` and `streamRange` refer to the helpers above.

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation
    .StreamingResponseBody;

import static com.mongodb.client.model.Filters.eq;

@RestController
@RequestMapping("/api/files")
public class FileDownloadController {

    private final GridFSBucket bucket;

    public FileDownloadController(
            GridFSBucket bucket) {
        this.bucket = bucket;
    }

    @GetMapping("/{fileId}")
    public ResponseEntity<StreamingResponseBody> download(
            @PathVariable String fileId,
            @RequestHeader(
                value = "Range",
                required = false
            ) String rangeHeader) {

        // 1. Validate ObjectId format.
        if (!ObjectId.isValid(fileId)) {
            return ResponseEntity
                .badRequest()
                .build();
        }

        ObjectId id = new ObjectId(fileId);

        // 2. In production: check auth + tenant,
        // visibility/permissions of the logical asset before reading.
        // Do not rely solely on an unguessable ObjectId.
        GridFSFile file = bucket
            .find(eq("_id", id))
            .first();

        if (file == null) {
            return ResponseEntity
                .notFound()
                .build();
        }

        long total = file.getLength();

        HttpHeaders headers = new HttpHeaders();

        headers.set(
            HttpHeaders.ACCEPT_RANGES,
            "bytes"
        );

        headers.setContentType(
            MediaType.APPLICATION_OCTET_STREAM
        );

        // ETag by ID is only appropriate when content is
        // treated as immutable for that exact ID.
        headers.setETag(
            "\"" + id.toHexString() + "\""
        );

        if (rangeHeader == null
                || rangeHeader.isBlank()
                || rangeHeader.contains(",")) {

            // Multi-range not supported: return full 200.
            headers.setContentLength(total);

            StreamingResponseBody body = output ->
                bucket.downloadToStream(id, output);

            return new ResponseEntity<>(
                body, headers, HttpStatus.OK
            );
        }

        final ByteRange range;

        try {
            range = parseSingleRange(
                rangeHeader,
                total
            );
        } catch (IllegalArgumentException error) {
            headers.set(
                HttpHeaders.CONTENT_RANGE,
                "bytes */" + total
            );

            // Production should distinguish syntax errors vs.
            // unsatisfiable ranges to pick the exact status.
            return new ResponseEntity<>(
                null,
                headers,
                HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE
            );
        }

        headers.set(
            HttpHeaders.CONTENT_RANGE,
            range.contentRange()
        );

        headers.setContentLength(
            range.contentLength()
        );

        StreamingResponseBody body = output ->
            streamRange(
                bucket,
                id,
                range.start(),
                range.endInclusive(),
                output
            );

        return new ResponseEntity<>(
            body,
            headers,
            HttpStatus.PARTIAL_CONTENT
        );
    }
}
~~~

### 8.1. Items to Complete Before Production

1. Check permissions/tenant against the logical asset; `fileId` is not an authorization token.
2. Validate `If-Range` and `If-None-Match`/conditional requests.
3. Define policies for malformed ranges, multiple ranges, and `HEAD`.
4. Cap body streaming resources and concurrent requests.
5. Use trusted/validated MIME metadata; never blindly trust client-uploaded values.
6. Set safe `Content-Disposition`, normalize filenames, and prevent CRLF/path injection.
7. Handle timeouts, cancellation, and metrics when clients close connections.
8. Base `ETag` on an immutable version or content hash.
9. Ensure source files are not deleted mid-stream, or use retention/leases.
10. Keep audit logs free of sensitive filenames or PII.

### 8.2. Why Verify Authorization **Before** Streaming?

An HTTP server can begin sending bytes immediately. Discovering that the user lacks permission after starting the response is too late: partial data may already have leaked.

### 8.3. When the Client Aborts Mid-Download

The streaming API will encounter an output write error or stop when the client closes the socket. Do not keep reading the file from MongoDB after the client disconnects; close the input stream, record metrics, and release resources.

---

## 9. `Content-Range`, `ETag`, and Caching Across Multiple Versions

### 9.1. Why Does `ETag` Matter?

A video might have versions v1 and v2. If a client downloads the first 5 MiB from v1 and later resumes the next 5 MiB from v2 **over the same filename URL**, the stitched content will be corrupted.

Use a validator:

~~~http
ETag: "v1-file-id-or-sha256"
~~~

When resuming, the client can send:

~~~http
Range: bytes=5242880-
If-Range: "v1-file-id-or-sha256"
~~~

If the current version is still v1, the server can return partial v1. If the validator does not match, the server should ignore `Range` and return the full current version with `200` per HTTP semantics.

### 9.2. Pinning Versions in URLs

A safe approach:

~~~text
GET /assets/ASSET-101           -> redirect/lookup currentFileId
GET /files/<fileId-of-v1>       -> bytes of v1
GET /files/<fileId-of-v2>       -> bytes of v2
~~~

`/files/{fileId}` becomes a route to **immutable content**. CDNs and browsers can cache with a stable validator, while `/assets/{assetId}` always resolves to the current version per policy.

### 9.3. `filename` Is Not an `ETag`

`"training.mp4"` can point to multiple versions, so using the filename as an `ETag` is wrong. `ETag` must be derived from an immutable `fileId`/SHA-256/version ID, never from a mutable display name.

### 9.4. Response Headers Should Reflect the Exact File

A well-formed response includes:

- Verified/allowed `Content-Type`.
- Exact `Content-Length` for the range or file.
- `Content-Range` when status is `206`.
- `Accept-Ranges: bytes` when supported.
- `ETag` of the specific content.
- `Last-Modified` if reliable timestamp metadata exists and semantics match.
- Sanitized download filename in `Content-Disposition`.

### 9.5. Never Publicly Cache Private Files

If content belongs to a specific tenant or user, `Cache-Control` and CDN cache keys must ensure bytes are never shared with unauthorized users. A stable `ETag` does not mean public caching is permitted.

---

## 10. Filename Management: `filename` Is Not Unique

### 10.1. Two Files with the Same Name Are Valid

Example:

~~~javascript
{
  _id: ObjectId("6914a9aa0000000000000001"),
  filename: "contract.pdf",
  uploadDate: ISODate("2026-11-10T09:00:00Z")
}

{
  _id: ObjectId("6914a9aa0000000000000002"),
  filename: "contract.pdf",
  uploadDate: ISODate("2026-11-11T09:00:00Z")
}
~~~

GridFS allows two documents with the same `filename`. They are **two distinct file IDs**, which drivers can treat as **revisions** of the same name.

### 10.2. Proper Identifiers

| Concept | Used For | Unique by Default? |
|---|---|---|
| `fileId` / `fs.files._id` | Identifying one content version | Yes |
| `filename` | Display, searching, download by name | **No** |
| `uploadDate` | Upload timestamp, supports revision ordering | No |
| `assetId` | Logical ID of a document in the application | Application-defined |
| `logicalVersion` | Business version 1, 2, 3... | Application-assigned |
| `sha256` | Content verification/reconciliation digest | Not computed by GridFS by default |

### 10.3. Finding Files by Name with `mongosh`

~~~javascript
use media_lab

db.media.files.find(
  { filename: "contract.pdf" },
  {
    _id: 1,
    filename: 1,
    length: 1,
    uploadDate: 1,
    metadata: 1
  }
).sort({
  uploadDate: -1,
  _id: -1
});
~~~

This **lists metadata**. To download bytes, use GridFS driver/API calls.

### 10.4. Do Not Rely on Filename for Authorization

If `tenant-a` and `tenant-b` both upload `report.pdf`, a query by filename alone returns both. The application must enforce a trusted `tenantId`/asset ownership check rather than treating `filename` as a security boundary.

### 10.5. Never Turn `filename` into a Filesystem Path

Names like `../../private.txt` or names containing slashes/backslashes can cause path traversal if concatenated directly into local disk paths.

If saving to disk is required:

- Generate a safe internal/temporary filename.
- Use the sanitized filename only for `Content-Disposition`.
- Avoid using uploaded names as actual disk paths.
- Never use filenames from HTTP headers without validating encoding, control characters, and length.

---

## 11. GridFS Revisions: Positive and Negative Numbers

### 11.1. Revision Selection Rules

The GridFS spec defines revisions across files sharing the **same `filename`**, ordered by `uploadDate`:

| Revision | Meaning |
|---:|---|
| `0` | First/oldest uploaded version |
| `1` | Next version by upload time |
| `2` | Third version |
| `-1` | Newest version |
| `-2` | Second newest version |
| `-3` | Third newest version |

By default, downloading by filename selects **revision `-1`**.

### 11.2. Example with Three Versions

~~~text
filename = report.pdf

2026-11-01  fileId=A   revision 0  / -3
2026-11-05  fileId=B   revision 1  / -2
2026-11-12  fileId=C   revision 2  / -1

Default download by filename -> C
Download revision(0)         -> A
Download revision(1)         -> B
Download revision(-2)        -> B
~~~

### 11.3. Revision Is Not a Stored Field in `fs.files`

`revision` is a **relative position** in the list of files sharing a filename. It is not a fixed version number stored by GridFS like `metadata.logicalVersion`.

If version A is deleted, positive revision indices of B and C shift because the list changed. When D is uploaded, `-1` moves to D. Thus a URL like:

~~~text
/download?filename=report.pdf&revision=-1
~~~

is not an immutable reference over time.

### 11.4. What If Two Uploads Have the Same `uploadDate`?

`uploadDate` has finite timestamp precision. If two records share the exact same `uploadDate`, do not rely on revision ordering as a **strict business sequence** when deterministic tie-breaking is required.

Assign an application-level `logicalVersion` via transaction/CAS in custom metadata. Whenever exactness matters, use the selected version's `fileId`.

### 11.5. Renaming Affects Revision Groups

If a file's filename is changed from `report.pdf` to `summary.pdf`, that version moves into the new name group. Revision numbering under both the old and new names changes.

Never use `revision(-1)` as an immutable business identity for a signed contract.

---

## 12. Java Sync Driver: Downloading by Filename and Revision

### 12.1. Default Newest

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.GridFSDownloadStream;

try (GridFSDownloadStream input =
         bucket.openDownloadStream("report.pdf")) {

    // This is the newest version per GridFS
    // download-by-name revision semantics.
    input.transferTo(outputStream);
}
~~~

This uses `InputStream.transferTo` (Java 9+). Do not close `outputStream` if it belongs to the HTTP framework; the framework manages output lifecycle.

### 12.2. Selecting the Oldest Version

~~~java
import com.mongodb.client.gridfs.model.GridFSDownloadOptions;

GridFSDownloadOptions options =
    new GridFSDownloadOptions().revision(0);

try (GridFSDownloadStream input =
         bucket.openDownloadStream("report.pdf", options)) {

    input.transferTo(outputStream);
}
~~~

### 12.3. Selecting the Second Newest Version

~~~java
GridFSDownloadOptions options =
    new GridFSDownloadOptions().revision(-2);

try (GridFSDownloadStream input =
         bucket.openDownloadStream("report.pdf", options)) {

    input.transferTo(outputStream);
}
~~~

### 12.4. Downloading the Full File to an `OutputStream`

~~~java
import com.mongodb.client.gridfs.model.GridFSDownloadOptions;

GridFSDownloadOptions options =
    new GridFSDownloadOptions().revision(-1);

bucket.downloadToStream(
    "report.pdf",
    outputStream,
    options
);
~~~

`downloadToStream` is convenient for full downloads; the stream is resolved by **filename + revision**. When ranges are needed, use `openDownloadStream` with `skipFully`/`copyExactly`.

### 12.5. Do Not Overuse Download-by-Name in Public APIs

When a user selects a document by asset ID, the safer pattern is typically:

1. Resolve the asset ID with authorization checks.
2. Retrieve `currentFileId` or `versionFileId`.
3. Download that exact file ID.

Downloading by filename is handy for labs and CLIs, but in production multi-tenant/versioned asset systems, filenames collide and shift.

---

## 13. Java: Listing Revisions Then Downloading by ID

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSFile;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

import java.util.ArrayList;
import java.util.List;

List<GridFSFile> revisions = new ArrayList<>();

bucket.find(
        Filters.eq("filename", "report.pdf")
    )
    .sort(
        Sorts.orderBy(
            Sorts.ascending("uploadDate"),
            Sorts.ascending("_id")
        )
    )
    .into(revisions);

for (GridFSFile file : revisions) {
    System.out.println(
        file.getId() + " "
        + file.getFilename() + " "
        + file.getUploadDate()
    );
}
~~~

### 13.1. Why List Metadata First?

The application can display to the user:

- Upload timestamp.
- Uploader.
- File length.
- Business version.
- Checksum.
- Virus scan status.
- Access permissions.
- Version notes.

### 13.2. Sorting by `_id` as a Tie-Breaker

Sorting by `uploadDate` is GridFS's revision mechanism, but if the application wants deterministic UI ordering on equal timestamps, adding `_id` works **when file IDs share a valid comparable type**. This is an application UI convention; it does not mean the GridFS driver uses the exact same tie-breaker when resolving `revision(-1)`.

### 13.3. Selecting an Explicit ID

~~~java
GridFSFile chosen = revisions.get(0);

try (GridFSDownloadStream input =
         bucket.openDownloadStream(
             chosen.getId()
         )) {

    input.transferTo(outputStream);
}
~~~

This pins the download to a specific version. If the file is deleted between listing and downloading, the download will fail; the application must handle that race.

### 13.4. Select by Business Version, Not List Position

In applications using `metadata.logicalVersion` or an `assetVersions` collection, when a user picks "version 7," map version 7 → `fileId` and read by ID. Never assume list index 6 is always version 7.

---

## 14. Renaming Files: `rename(fileId, newFilename)`

### 14.1. Renaming Does Not Change Bytes

~~~java
import org.bson.types.ObjectId;

ObjectId fileId =
    new ObjectId("6914a9aa0000000000000001");

bucket.rename(
    fileId,
    "training-final.mp4"
);
~~~

GridFS `rename` updates `filename` on the file metadata identified by ID; chunks and content remain untouched.

### 14.2. Do Not Use `rename` to "Overwrite" Content

`rename` does not modify `fs.chunks.data`. If a user uploads a new file with an old name, that creates **a new `fileId`**. Renaming an old version to a new name does not turn the old version into the new bytes.

### 14.3. Renaming One File Among Multiple Versions with the Same Name

Suppose three files are all named `report.pdf`. Calling `bucket.rename(fileIdB, "report-old.pdf")` renames only version B, leaving A and C untouched.

### 14.4. Renaming All by Name

The GridFS spec mentions optional advanced operations for managing multiple files with the same name. Never assume your Java Sync Driver version exposes `renameByName`; when you need to rename all:

1. List the matching file IDs by `filename`.
2. Verify permissions and the set of revisions.
3. Call `rename(fileId, newName)` for each ID.
4. Handle partial success, as operations are not atomic across multiple files.

### 14.5. Naming Policies

You can establish rules such as:

- `filename` is for display only.
- Display names contain no control characters.
- Enforce a maximum length.
- Do not require bucket-wide uniqueness.
- Maintain `displayName` independently from `filename` if needed.
- Store logical paths/folders in separate app metadata (e.g., `folderId`) rather than encoding an entire hierarchy into `filename`.

---

## 15. Deleting Files: By `fileId` and Concurrent Read Risks

### 15.1. Deleting a Single Version

~~~java
ObjectId oldFileId =
    new ObjectId("6914a9aa0000000000000001");

bucket.delete(oldFileId);
~~~

GridFS `delete` removes the file metadata and its associated chunks. It targets a **file ID**, and does not delete other versions sharing the same `filename`.

### 15.2. Do Not Delete Arbitrarily by Name

If a user chooses "delete v2 of `contract.pdf`," resolve `versionId → fileId` and delete that exact ID. A manual command like:

~~~javascript
db.fs.chunks.deleteMany({
  files_id: someFileId
});
~~~

while metadata remains will corrupt the file. Never delete `chunks` or `files` independently unless executing a controlled administrative/recovery runbook while understanding GridFS invariants.

### 15.3. Race Between Delete and Download

~~~text
Reader A: reads metadata for fileId=X
           |
Writer B: delete(X)
           |
Reader A: reads chunks of X
           |
           v
Reader A may encounter missing chunks
~~~

The GridFS spec explicitly notes an inherent race between metadata and chunks when a file is deleted concurrently with reads. Drivers cannot turn deleting across two collections into a simple atomic operation for all cases.

### 15.4. Policy to Prevent Premature Deletion

If a file is actively being served to clients:

- Soft-delete the logical asset first.
- Block new downloads from starting.
- Wait long enough for active downloads or active-reader leases to finish.
- Only after the retention/grace period, call `bucket.delete(fileId)`.
- Monitor download errors and orphan cleanup.

This is an **application-level rule**, not a built-in locking feature of GridFS.

### 15.5. Deleting All Revisions

If you need to delete the entire history sharing a filename:

1. Resolve `_id` values scoped by tenant/asset, not just by filename.
2. Check legal hold/retention and delete permissions.
3. Delete each file ID via the GridFS API.
4. Audit each outcome.
5. Support retries if interrupted partway through.

Some drivers provide advanced delete-by-name helpers, but you cannot assume every version provides them or satisfies tenant/version policies.

### 15.6. Do Not Confuse Dropping a Bucket with Deleting One File

`bucket.drop()` or dropping `fs.files`/`fs.chunks` **destroys the entire bucket**, not a single file version. Never use it in normal production workflows.

---

## 16. GridFS Does Not Support Multi-Document Transactions for File Operations

The MongoDB Manual explicitly states that **GridFS does not support multi-document transactions**. GridFS uploads/deletes touch many documents across chunks and files; they are not designed as an atomic write of all chunks inside a MongoDB transaction.

### 16.1. An Upload Has Multiple Steps

~~~text
Start upload
     |
     v
Insert chunk n=0
     |
     v
Insert chunk n=1
     |
     v
Insert chunk n=2
     |
     v
Insert metadata into fs.files
     |
     v
Upload complete
~~~

If the process or network dies mid-upload, **orphan chunks** or incomplete states can remain.

### 16.2. Do Not Wrap Upload + App Metadata in a Transaction Expecting Atomicity

Flawed design:

~~~text
startTransaction()
  GridFS upload entire 2 GB file
  insert appAsset
commit()
~~~

GridFS does not support this transaction pattern, and long-running transactions are unsuitable for large streaming files.

### 16.3. Proper Coordination: Upload First, Publish Pointer Afterward

~~~text
1. Upload new GridFS file (fileId=Y).
2. Wait for upload to complete.
3. Compute/verify checksum and scan content if required.
4. Transaction/atomic update on app metadata:
     asset.currentFileId = Y
     asset.currentVersion += 1
     assetVersions insert (assetId,version,Y)
5. If step 4 fails:
     Y is not active yet and can be cleaned up per policy.
~~~

The app metadata transaction **does not include the GridFS upload**. It only governs **when an uploaded version is published as current**.

### 16.4. Incomplete Uploads Must Never Be Readable

Never expose a new `fileId` in a public asset pointer before upload succeeds and validation passes. Maintain states like `UPLOADING`/`SCANNING`/`READY` in application metadata.

---

## 17. Designing Logical Assets and Immutable Versions

### 17.1. The Problem with Filename/Revision Alone

If a document is named `contract.pdf` and users re-upload it 4 times, GridFS can select the latest by `uploadDate`. However, applications need:

- A stable URL for the logical document.
- An immutable ID for each version.
- History including author, comment, timestamp, and hash.
- Tenant permissions.
- "Restore v2" without losing v3/v4.
- Auditing on renames and deletions.
- Protection against lost updates during concurrent uploads.

Do not delegate all of that to `filename + revision(-1)`.

### 17.2. `assets` Collection

~~~javascript
{
  _id: "ASSET-101",
  tenantId: "tenant-a",
  displayName: "contract.pdf",
  currentVersion: 3,
  currentFileId: ObjectId(
    "6914a9aa0000000000000003"
  ),
  generation: NumberLong("3"),
  status: "ACTIVE",
  updatedAt: ISODate("2026-11-14T05:00:00Z")
}
~~~

### 17.3. `assetVersions` Collection

~~~javascript
{
  _id: "ASSET-101:v3",
  assetId: "ASSET-101",
  tenantId: "tenant-a",
  version: 3,
  fileId: ObjectId(
    "6914a9aa0000000000000003"
  ),
  originalFilename: "contract.pdf",
  contentType: "application/pdf",
  length: NumberLong("600000"),
  sha256: "application-computed-hash",
  uploadedBy: "user-101",
  createdAt: ISODate("2026-11-14T05:00:00Z"),
  status: "READY"
}
~~~

### 17.4. Indexes for Business Versions

~~~javascript
db.assetVersions.createIndex(
  {
    tenantId: 1,
    assetId: 1,
    version: 1
  },
  {
    unique: true,
    name: "uk_asset_version"
  }
);

db.assetVersions.createIndex(
  {
    fileId: 1
  },
  {
    unique: true,
    name: "uk_asset_file_id"
  }
);
~~~

If multiple assets intentionally reference the same `fileId` to deduplicate physical storage, a unique index on `fileId` no longer fits. Design indexes according to actual ownership and deduplication policies.

### 17.5. Separating Two Kinds of Identifiers

| URL/API | Resolves To | Content Immutable? |
|---|---|---|
| `/assets/ASSET-101` | `currentFileId` | **No**; current content can change |
| `/assets/ASSET-101/versions/3` | `fileId` of v3 | Yes, unless deleted/bytes altered |
| `/files/6914...` | Exact GridFS `fileId` | Yes, if files are immutable |
| `/download?filename=contract.pdf` | Driver picks by name/revision | Not guaranteed stable |

### 17.6. How Can "Restore v2" Work?

Two options:

- Move the current pointer back to v2's `fileId` (recording a new revision/generation in the audit log).
- Create a new business version v5 pointing to the same content as v2, and set current to v5.

The second option is usually easier to audit if every publish/restore must create a new state transition. Never decrement `currentVersion` from 4 back to 2 if the system uses monotonic versions to prevent concurrency bugs.

---

## 18. Concurrent Uploads and Optimistic Concurrency

### 18.1. The Race

~~~text
Asset generation = 3

User A reads gen=3
User B reads gen=3

User A uploads fileId=A4
User B uploads fileId=B4

A wants to set currentFileId=A4
B wants to set currentFileId=B4
~~~

With an unconditional update, the final state depends on write order; a version can be lost from history or version 4 written twice.

### 18.2. Conditional Update / Compare-and-Swap

After the GridFS upload finishes, application metadata can attempt:

~~~javascript
const expectedGeneration = NumberLong("3");

const result = db.assets.updateOne(
  {
    _id: "ASSET-101",
    tenantId: "tenant-a",
    generation: expectedGeneration
  },
  {
    $set: {
      currentFileId: newFileId,
      updatedAt: new Date()
    },
    $inc: {
      generation: NumberLong("1"),
      currentVersion: 1
    }
  }
);

if (result.modifiedCount !== 1) {
  throw new Error("VERSION_CONFLICT");
}
~~~

This is the core CAS demo. **If the app also needs to insert into `assetVersions` as part of the logical change**, perform the writes across **application metadata collections** inside a MongoDB-supported transaction or use an equivalent atomic invariant design.

Do not wrap the GridFS upload in the transaction.

### 18.3. When CAS Fails

`newFileId` has finished uploading but is not published yet; you may need to:

- Retain it as an unreferenced draft for a short window.
- Allow retrying publication after the user refreshes/merges, without blind overwriting.
- Clean up per policy.
- Audit the upload and the conflict.

### 18.4. Never Reuse a `fileId` to Overwrite Bytes

GridFS treats a file as stored content; **it does not support arbitrarily editing/appending chunks of a completed file like a mutable file**. For a new version, upload a new file with a new ID and swap the pointer. Never edit `fs.chunks.data` directly.

### 18.5. Application Checkpoint

When updating the current pointer, check both current `generation` and permissions. If a later upload fails to become active due to conflict, never delete a version currently in use by other users.

---

## 19. Searching and Managing Filenames at Scale

### 19.1. Standard GridFS Indexes

Per GridFS:

~~~javascript
db.fs.files.createIndex(
  {
    filename: 1,
    uploadDate: 1
  }
);

db.fs.chunks.createIndex(
  {
    files_id: 1,
    n: 1
  },
  {
    unique: true
  }
);
~~~

Compliant drivers ensure these indexes according to their version-specific behavior. If a bucket uses the prefix `media`, the collections are `media.files` and `media.chunks`.

### 19.2. Why Does the `files` Index Need `filename, uploadDate`?

A lookup by filename/revision typically runs:

~~~javascript
db.fs.files.find({
  filename: "report.pdf"
}).sort({
  uploadDate: 1
});
~~~

The index supports finding files with the same name and sorting by `uploadDate`.

### 19.3. Why Must the `chunks` Index Be Unique?

A single file cannot have two chunks with the same `n`. The index:

~~~javascript
{
  files_id: 1,
  n: 1
}
~~~

with `unique:true` protects this invariant and enables drivers to fetch consecutive chunks efficiently.

### 19.4. Additional Indexes for Tenant/Asset Metadata

If you frequently query:

~~~javascript
db.media.files.find({
  "metadata.tenantId": "tenant-a",
  "metadata.assetId": "ASSET-101"
}).sort({
  uploadDate: -1
});
~~~

consider:

~~~javascript
db.media.files.createIndex(
  {
    "metadata.tenantId": 1,
    "metadata.assetId": 1,
    uploadDate: -1
  },
  {
    name: "idx_media_tenant_asset_date"
  }
);
~~~

This is a candidate index; use `explain` and real workloads to decide. Avoid creating too many indexes when upload volumes are high.

### 19.5. Searching Names with Regex

If the UI searches for `report` across all filenames:

~~~javascript
db.media.files.find({
  filename: /report/i
});
~~~

unanchored, case-insensitive regexes are hard to optimize with standard B-tree indexes. At large scale, consider a dedicated search metadata collection, normalized filenames, prefix searches, or MongoDB Search depending on requirements.

### 19.6. Do Not Treat Filename as a Unique Path

If multiple folders or tenants both contain `invoice.pdf`, the logical identity should be `assetId` plus folder/tenant metadata. Making `filename` globally unique fails for most multi-user document management systems.

---

## 20. Managing Metadata: MIME Type, Checksum, Uploader

### 20.1. Using `metadata` for Extensions

~~~java
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;

GridFSUploadOptions options =
    new GridFSUploadOptions()
        .chunkSizeBytes(256 * 1024)
        .metadata(
            new Document(
                "tenantId", "tenant-a"
            )
                .append(
                    "assetId", "ASSET-101"
                )
                .append(
                    "contentType",
                    "application/pdf"
                )
                .append(
                    "uploadedBy",
                    "user-101"
                )
        );
~~~

This example picks `256 KiB` for the upload configuration, differing from the **255 KiB** default. `chunkSizeBytes` applies only to the new file and does not re-chunk existing files.

### 20.2. Never Trust Client MIME Types

A client can declare `application/pdf` while the payload is an executable. If inline browser viewing is permitted, validate content type, scan for malware, and set appropriate `Content-Disposition`/`Content-Security-Policy` headers.

### 20.3. Checksums

The legacy `md5` field in GridFS should not be relied upon as a modern integrity/security mechanism. When needed:

1. Hash bytes during upload, e.g., SHA-256.
2. Store the checksum in application metadata.
3. Re-verify during audits, downloads, or backup restores as needed.
4. Never alter the checksum after content is published.

### 20.4. Full-File SHA-256 Cannot Be Proven from a Single Range

If a client reads only bytes 1000–1999, you cannot verify the full-file SHA-256 from that slice alone unless a Merkle/chunk-proof structure exists. You can verify per-chunk checksums or verify the full file during ingestion and reconciliation.

### 20.5. User-Supplied Metadata Needs Validation

- Allowlist content types.
- Enforce filename length limits and Unicode normalization.
- Derive tenant/owner from the authenticated context.
- Assign business versions server-side.
- Reject arbitrary updates to core fields `length`, `chunkSize`, `uploadDate`, and `_id`.

---

## 21. Streaming Uploads and Saving New Versions in Java

### 21.1. Uploading a File into GridFS

~~~java
import com.mongodb.client.gridfs.GridFSBucket;
import com.mongodb.client.gridfs.model.GridFSUploadOptions;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.InputStream;

static ObjectId uploadDocument(
        GridFSBucket bucket,
        String safeFilename,
        InputStream input,
        String assetId,
        String tenantId) {

    GridFSUploadOptions options =
        new GridFSUploadOptions()
            .metadata(
                new Document(
                    "tenantId", tenantId
                )
                    .append(
                        "assetId", assetId
                    )
                    .append(
                        "contentType",
                        "application/pdf"
                    )
            );

    return bucket.uploadFromStream(
        safeFilename,
        input,
        options
    );
}
~~~

`uploadFromStream` reads the source via streaming and returns the `ObjectId` of the new file. Ownership of the source `InputStream` stays with the caller: the calling code should close it using `try-with-resources`.

### 21.2. Each Upload Has Its Own ID

~~~java
ObjectId v1 = uploadDocument(
    bucket, "contract.pdf",
    inputV1, "ASSET-101", "tenant-a"
);

ObjectId v2 = uploadDocument(
    bucket, "contract.pdf",
    inputV2, "ASSET-101", "tenant-a"
);
~~~

`v1` and `v2` can share the same filename while remaining two files with separate bytes.

### 21.3. Replacing Content

Do not modify chunks of `v1`; upload `v2` and update the logical asset pointer only after:

- Upload succeeds.
- Malware/content validation passes if needed.
- SHA-256/length are verified.
- Business permissions are valid.
- Expected `generation` has no conflict.

### 21.4. Do Not Equate Upload Success with Publish Success

If the GridFS upload succeeds but the application metadata update fails, the content exists without being active. Run cleanup or retry publication according to your runbook.

---

## 22. Download by ID vs. by Filename: Which Should You Choose?

### 22.1. Comparison Table

| Requirement | Download by ID | Download by filename |
|---|---|---|
| Return exact signed version | **Good** | Risk of picking another version |
| Resumable HTTP Range | **Good** due to stable URL | Needs `If-Range`/`ETag` to prevent mixing versions |
| Restoring older revision | Resolve ID from version metadata | Can use revision, though not pinned |
| Simple lab | Suitable | Convenient |
| Multi-tenant | Combine with asset authorization | Filenames collide easily |
| Download auditing | Unambiguous ID | Easily ambiguous |
| Cache/CDN | Enables immutable URLs | Filename URL changes content |
| Rename | ID never changes | Old-name lookup breaks |

### 22.2. Recommended Rules

- **Business APIs:** use `assetId` and `versionId`.
- **Physical byte APIs:** use `fileId`.
- **GridFS `filename`:** use for display, admin tools, and download-by-name where appropriate.

---

## 23. Concurrent Range Reads and Resource Limits

### 23.1. Video Players May Open Multiple Requests

A player might issue:

~~~http
Range: bytes=0-1023
Range: bytes=1048576-2097151
Range: bytes=5242880-
~~~

Requests can arrive concurrently. Never share one `GridFSDownloadStream` across multiple HTTP requests; each request should open its own stream for the authorized `fileId`.

### 23.2. Limiting Concurrent Streams

If 1,000 clients download large files, each stream holds cursors, buffers, and network resources. Enforce:

- Driver connection pool tuning.
- Server concurrency limits.
- Timeouts and read deadlines.
- Per-user/tenant rate limits.
- Reasonable read buffer sizes.
- CDN or reverse proxy caching where appropriate.
- Monitoring of bytes streamed and client aborts.

### 23.3. Tiny Ranges at Very High Request Rates

A malicious client can request tens of thousands of tiny ranges to amplify overhead. Rate-limit, normalize requests, reject excessive connections, and cache popular files per policy.

### 23.4. Chunk Size Trade-Offs

| Smaller chunks | Larger chunks |
|---|---|
| Less wasted reads on small slices when drivers fetch chunk-level | Fewer documents for large files |
| More chunk documents and index entries | Lower metadata overhead |
| More round-trips when reading the full file | Can increase peak memory/buffer per chunk |
| Fits some random-read workloads | Fits some sequential-read workloads |

No single `chunkSize` is optimal for every file. Benchmark with realistic file sizes and range patterns. Because `chunkSize` is stored per file, you do not need to migrate old files when changing settings for new uploads.

---

## 24. GridFS and Streaming HTTP Are Not an Object Storage CDN

### 24.1. When GridFS Makes Sense

- The application already uses MongoDB and wants to manage files on the same infrastructure.
- You need to query metadata in MongoDB.
- You need multiple revisions and partial/range streaming.
- Files exceed the BSON document limit.
- Download traffic fits within cluster capacity.

### 24.2. When to Consider Object Storage

- Very large public video/file downloads at global scale.
- Need for direct CDN integration, object lifecycles, and storage classes.
- High data egress putting pressure on MongoDB.
- Need for multipart/resumable uploads with specialized semantics.
- No need to join/search metadata inside the database.

An alternative architecture:

~~~text
Application metadata: MongoDB
Binary objects: S3/GCS/Azure Blob
Signed URLs/CDN: directly from object store
~~~

Do not claim GridFS is always faster or cheaper than object storage. Decide based on workload, availability, backups, and cost.

### 24.3. GridFS Does Not Generate Thumbnails or Transcode Video

For video streaming, GridFS only stores bytes and supports reading slices. It does not:

- Generate HLS/DASH renditions.
- Transcode video.
- Generate thumbnails.
- Compute codecs/bitrates.
- Guarantee browser playback across formats.
- Provide CDN caching/prefetching.

Those tasks belong in a media pipeline outside GridFS.

---

## 25. Recovering from Failed Uploads and Orphan Chunks

### 25.1. Interrupted Uploads

Suppose chunks `n=0,1` were saved, but the process crashed before writing `files` metadata. Chunks can remain with a `files_id` that has no matching document in `fs.files`.

### 25.2. Never Immediately Delete All Chunks "Without a File Entry"

An **active** upload can also have written chunks before writing its file metadata. If a cleanup job scans and deletes all "orphan" chunks immediately, it can break legitimate in-progress uploads.

You need:

- A grace period.
- Tracking of upload sessions/states.
- Recent activity checks.
- Tenant/bucket scoping.
- Mark-and-sweep or 2-phase cleanup.
- Alerts and dry-run mode in operations.

### 25.3. File Metadata Exists While Chunks Are Missing

This can happen due to direct collection deletes, operational mistakes, or races. Drivers usually detect invalid chunk sequences/lengths when reading across the damaged region.

Never treat the existence of an `fs.files` document as proof that all chunks are intact.

### 25.4. Integrity Verification

A verification workflow:

1. Read `fs.files.length` and `chunkSize`.
2. Compute expected chunk count.
3. Use the GridFS API to stream the full file and detect missing chunks.
4. Compute SHA-256 and compare with app metadata (if stored).
5. Record audit/error status.
6. Restore from backup or require re-upload if unrepairable.

### 25.5. Backup and Restore

Backups must capture **both `files` and `chunks`** (plus app metadata/`assetVersions` if present) with an appropriate consistency policy. Backing up `fs.files` without `fs.chunks` leaves zero binary content.

### 25.6. Restores Must Synchronize Version Pointers

If the bucket is restored to time T1 while `assets.currentFileId` is at T2, pointers may reference nonexistent files. Backup/recovery plans must coordinate MongoDB data and app metadata, followed by reconciliation.

---

## 26. Conditional Deletion of Old Versions

### 26.1. Retention Policy

Suppose you must:

- Retain every version for 30 days.
- Retain current plus 3 previous versions.
- Never delete versions under legal hold.
- Delete only when no active downloads remain.
- Maintain an audit trail.

These policies **do not exist from `filename`/`revision` alone**. Application metadata is required.

### 26.2. Example Listing Candidates

~~~javascript
db.assetVersions.find({
  tenantId: "tenant-a",
  assetId: "ASSET-101",
  status: "READY",
  createdAt: {
    $lt: ISODate("2026-10-01T00:00:00Z")
  },
  legalHold: {
    $ne: true
  }
}).sort({
  version: 1
});
~~~

This query only lists candidates; before deleting, check `currentVersion`, reference counts, and retention policy. Never turn it blindly into a production `deleteMany()`.

### 26.3. Safe Deletion Workflow

~~~text
1. Select old version candidates.
2. Check authorization/legal hold/current pointer.
3. Mark DELETING in app metadata.
4. Block new reads if policy requires.
5. Wait for grace period / active readers.
6. bucket.delete(fileId).
7. Record DELETED status / audit.
8. Retry on network failures and handle partial deletion.
~~~

### 26.4. When Deletion Partially Fails

Because GridFS `delete` is not wrapped in a multi-document transaction, network errors can leave an ambiguous state. Reconciliation must inspect `files`/`chunks` and execute idempotent cleanup by `fileId` rather than just returning 500 and forgetting it.

### 26.5. Soft Delete vs. Physical Delete

Soft delete hides the asset from the UI while retaining bytes for recovery or legal disputes. Physical delete removes chunks and cannot be undone without backups.

---

## 27. Versioning and Renaming for Signed Documents

### 27.1. Risk of Picking `revision(-1)` When Signing

If a user signs `contract.pdf` at 10:00, and another user uploads a new file with the same name at 10:01, a download request using `revision(-1)` at 10:02 will return **different content** from what was signed.

### 27.2. How to Pin Content

When creating a signature record:

~~~javascript
{
  _id: "SIGN-101",
  assetId: "ASSET-101",
  signedFileId: ObjectId(
    "6914a9aa0000000000000002"
  ),
  signedSha256: "hash-v2",
  signedAt: ISODate("2026-11-14T10:00:00Z"),
  signerId: "user-101"
}
~~~

Afterward, always download by `signedFileId`, never by `filename`, `current`, or `revision(-1)`.

### 27.3. Renaming Does Not Alter Signed Content

If a signature/approval is bound to the **hash and `fileId`**, changing the display name does not change the bytes. However, audit/legal records may require preserving the filename at signing time, so keep `originalFilename` in version metadata.

### 27.4. Rename All Versions or Only Current?

Decide explicitly:

- Global asset `displayName` can be updated once for all UI views.
- Historical GridFS physical `filename` values can remain unchanged for auditability.
- You may not need to call `bucket.rename` on every revision.
- Historical versions keep original names; the current version displays the new name via `assets.displayName`.

Separating business `displayName` from GridFS `filename` avoids unnecessarily renaming hundreds of versions.

---

## 28. Access Control: A File ID Is Not an Authorization Token

### 28.1. An ObjectId Does Not Prove Caller Permission

The URL:

~~~text
GET /files/6914a9aa0000000000000001
~~~

contains a valid `fileId`, yet the server must still verify:

- Is the user authenticated?
- Does the tenant own the asset?
- Does the user's role permit reading?
- Is the asset still `ACTIVE` or was it revoked?
- Is this version allowed to be viewed?
- Have malware scanning and validation completed?
- Are there contract, expiration, or organizational restrictions?

### 28.2. GridFS Metadata Is Not Necessarily the Final Source of Truth for Permissions

You can store `metadata.tenantId` in `fs.files`, yet authorization may still need to check `assets`/`assetVersions` because permissions and states change over time.

### 28.3. Preventing IDOR

IDOR occurs when a user swaps `fileId` in a URL and downloads someone else's file because the backend only checks whether the ID exists. Enforce authorization **before opening the download stream**.

### 28.4. Do Not Expose Raw GridFS Collections

Never grant user clients direct access to `fs.chunks`. The API service owns authentication, range validation, rate limiting, and auditing.

### 28.5. Signed Download URLs

If using signed URLs:

- Bind `fileId`/version/tenant/resource scope.
- Use short expirations and strong signatures.
- Prevent altering range/`fileId` if the signature does not cover protected parameters.
- Support revocation policies if the application requires them.
- Never log full tokens or secrets.

---

## 29. When Should You Change the Chunk Size?

### 29.1. Full-File Download Workloads

If workloads mostly download large PDFs/archives in full, larger chunks can reduce document counts and overhead. However, drivers may use more memory per chunk.

### 29.2. Small Random-Range Workloads

If workloads frequently read random 4 KiB/16 KiB slices, smaller chunks can reduce excess chunk data fetched, depending on implementation and caching. However, more documents increase overhead.

### 29.3. Do Not Arbitrarily Change Defaults Mid-Upload

Chunk size is stored in each file's metadata. An in-progress upload should not change `chunkSize` mid-stream via API. Subsequent uploads can use a different setting.

### 29.4. Meaningful Benchmarks

Measure with realistic datasets:

- 1 MiB, 50 MiB, and 2 GiB files.
- HTTP ranges of 4 KiB, 1 MiB, and 100 KiB suffix.
- Sequential full downloads.
- 1, 10, and 100 concurrent clients.
- MongoDB index size.
- Peak RAM / JVM GC.
- Chunks fetched per request.
- Network bandwidth.
- p95/p99 response latency.

Never compare just the byte size of a single file to declare an optimal chunk size.

---

## 30. GridFS Indexes and `explain`

### 30.1. Inspect Indexes in the Right Bucket

~~~javascript
use media_lab

db.media.files.getIndexes();
db.media.chunks.getIndexes();
~~~

When the bucket name is `media`, do not inspect `fs.files` and conclude the `media` bucket is missing indexes.

### 30.2. Querying Multi-Revision Metadata

~~~javascript
db.media.files.find({
  filename: "report.pdf"
}).sort({
  uploadDate: -1
}).explain("executionStats");
~~~

### 30.3. Querying a Chunk Range

~~~javascript
db.media.chunks.find({
  files_id: someFileId,
  n: {
    $gte: 10,
    $lte: 20
  }
}).sort({
  n: 1
}).explain("executionStats");
~~~

### 30.4. Metrics to Inspect

- Winning plan/index.
- Total keys examined.
- Total docs examined.
- `nReturned`.
- Query latency.
- Bytes read over the network.
- Disk/CPU under many concurrent streams.

### 30.5. Do Not Overuse Direct Chunk Queries

They are suitable for **inspection/diagnostics**. Application code should use the GridFS driver, which validates integrity, orders chunks, and maintains compatibility.

---

## 31. Common Error Handling

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Download by filename returns wrong version | Duplicate name; default newest revision | Use `fileId` or explicit revision |
| Partial download off by 1 byte | Confused exclusive vs. inclusive end | Use `end-start+1` |
| Range past EOF | Unsatisfiable header | Return `416` + `Content-Range: bytes */L` |
| Suffix range wrong | Treated `-500` as negative offset | Return the last 500 bytes |
| `skip(start)` stops early | `skip` returned fewer bytes than requested | Use `skipFully` |
| High RAM on download | Loaded whole file into byte array | Stream with bounded buffer |
| HTTP `206` wrong `Content-Length` | Miscounted or sent whole file | Copy exact range length |
| Resumed download mixes two versions | Unpinned filename/current download | Pin `fileId` URL and `If-Range` |
| File exists but chunk read fails | Missing/out-of-order/corrupt chunk | Driver validation, audit, restore |
| Upload crash leaves chunks behind | No whole-upload commit | Orphan cleanup with grace period |
| Rename did not change content | Rename updates filename metadata only | Upload a new version |
| Deleting by name wiped multiple versions | Broad delete by filename | Target specific `fileId` |
| Cross-tenant name collision | Filename is not unique | Authorization + tenant filter |
| Filename search is slow | Missing index / unoptimized regex | Metadata index/search |
| Missing MD5 hash | Legacy field deprecated | Application-managed SHA-256 |
| File deleted mid-download | Race between `files`/`chunks` | Retention / active-reader grace |
| GridFS upload "transaction" fails | GridFS lacks multi-doc transactions | Upload first, publish app pointer later |
| Lost update on current version bump | Two concurrent uploads | CAS/`generation`, metadata transaction |
| App pointer points to missing file | Published before upload or skewed restore | Activate only after success, reconcile |

---

## 32. Practical HTTP Range Testing

### 32.1. Empty File Test

- Full `GET` returns `200` with 0-byte body.
- `Range: bytes=0-0` has no byte to read; return `416` per policy.

### 32.2. Single-Byte File Test

1-byte file:

- `Range: bytes=0-0` → `206`, one byte.
- `bytes=1-1` → `416`.
- `bytes=-1` → one byte.
- `bytes=0-` → one byte.

### 32.3. Exact Chunk-Boundary Test

C=261120:

- `bytes=261119-261119`: last byte of chunk 0.
- `bytes=261120-261120`: first byte of chunk 1 (when L>C).
- `bytes=261119-261120`: two bytes spanning two chunks.
- `bytes=0-261119`: one full chunk.

### 32.4. End-of-File Test

With L=600000:

- `bytes=599999-599999` → one byte.
- `bytes=599000-999999` → clamp end to 599999.
- `bytes=600000-600100` → `416`.

### 32.5. Suffix Test

- `bytes=-500` → last 500 bytes.
- `bytes=-700000` with L=600000 → all 600,000 bytes in a valid `206` response.
- `bytes=-0` → unsatisfiable per policy.
- `bytes=-999999999999999999999` → parser must guard against numeric overflow/DoS.

### 32.6. Multiple-Range Test

`bytes=0-99,200-299`:

- If the API implements `multipart/byteranges`, verify boundaries and headers for each part.
- If not implemented, return `200` full file rather than faking a partial response with `206`.

### 32.7. Binary Equality Test

With a random-byte file, compare:

~~~text
response bytes == source[start .. endInclusive]
~~~

Do not check `Content-Length` alone. Test across chunk boundaries and with varying chunk sizes.

### 32.8. `If-Range` and `ETag` Test

- Download the first half of v1.
- Upload v2 and switch the current pointer.
- Client sends `Range` with v1's `ETag` to the current URL.
- Response must not splice v2 onto v1.
- The pinned v1 `fileId` URL can continue v1 if still retained and permitted.

---

## 33. Testing Filenames and Revisions

### Test A — Two Files with the Same Filename

Upload `report.pdf` twice and verify `fs.files` has two distinct `_id` values.

### Test B — Revisions `0` and `-1`

Download `revision(0)` and `revision(-1)`; verify bytes match the first and last uploads respectively.

### Test C — Revision `-2`

Upload three versions and download `-2`; verify it is the second newest version.

### Test D — Renaming One Version

Rename only v2's `fileId`. Ensure v1 and v3 stay in the old name group while v2 moves to the new name group.

### Test E — Deleting an Old Version

Delete v1 by ID. Verify v2 still downloads; note that name-based revision numbering can shift.

### Test F — Identical Timestamps

Create records with identical `uploadDate` in a lab environment and verify the UI uses tie-breakers or explicit `logicalVersion` instead of relying on revision ordering as a guaranteed sequence.

### Test G — Tenant Isolation

Two tenants upload `invoice.pdf`. A `tenant-a` user must not be able to download `tenant-b`'s `fileId` even if they know the ID.

### Test H — Concurrent Uploads

Two users upload when `asset.generation=3`. Verify CAS allows only one operation to publish `current`, while the other receives a conflict/merge response.

### Test I — `fileId` Pinning

A user downloads v1 via `/files/{fileIdV1}`, then v2 is created. The v1 URL still returns v1 bytes if retention permits.

### Test J — Retention / Legal Hold

An old version is marked under legal hold; cleanup must not physically delete it.

---

## 34. Application Scenario: Storing Multi-Version Videos

### 34.1. Data Model

~~~javascript
{
  _id: "VIDEO-101",
  title: "MongoDB Course",
  currentFileId: ObjectId("6914a9aa0000000000000002"),
  currentVersion: 2,
  status: "PUBLISHED"
}
~~~

### 34.2. Uploading a New Version

- The video editor uploads v3 via GridFS.
- Wait for upload, virus scan, and transcoding pipeline to succeed.
- Create business version v3.
- Update the current pointer with CAS.
- Retain v2 during the rollback window.
- Browsers use the v3 URL for playback, avoiding mixing ranges between v2 and v3.

### 34.3. HTTP Range

Video players request `bytes=...` depending on container/codec. The server returns `206` with exact `Content-Range`, v3's `ETag`, and an appropriate cache policy.

### 34.4. Do Not Treat GridFS as an Adaptive Streaming Pipeline

For HLS/DASH, generate separate rendition/segment files via a media service. GridFS can store those segments, but does not encode video itself.

---

## 35. Application Scenario: Contracts Requiring History and Auditing

### 35.1. Business Workflow

A contract has v1 draft, v2 reviewed, and v3 signed:

~~~text
Asset: CONTRACT-101
  v1 -> fileId=A, status=DRAFT
  v2 -> fileId=B, status=REVIEWED
  v3 -> fileId=C, status=SIGNED
  currentFileId=C
~~~

### 35.2. Recommended APIs

~~~text
GET /contracts/CONTRACT-101
GET /contracts/CONTRACT-101/versions
GET /contracts/CONTRACT-101/versions/3/download
POST /contracts/CONTRACT-101/versions
POST /contracts/CONTRACT-101/restore?version=2
~~~

APIs should not expose raw `filename` as the sole identifier.

### 35.3. Signing Principles

- Bind signatures/approvals to `fileId` and SHA-256.
- Keep signed bytes immutable.
- Never treat renaming `displayName` as a content update.
- Enforce retention/legal holds.
- Audit every download, delete, and version-publish attempt.
- When restoring v2, emit an event or create a new business revision per policy.

---

## 36. Runbook When a GridFS File Fails to Download

### Step 1 — Identify the Exact ID

Do not just log "report.pdf failed"; record `fileId`, bucket, tenant, logical `assetId`, requested range, and HTTP status.

### Step 2 — Inspect Metadata

~~~javascript
db.media.files.findOne({
  _id: suspectedFileId
});
~~~

Verify `length`, `chunkSize`, `filename`, `uploadDate`, and `metadata`.

### Step 3 — Inspect Indexes

~~~javascript
db.media.chunks.getIndexes();
db.media.files.getIndexes();
~~~

### Step 4 — Inspect Chunks

~~~javascript
db.media.chunks.find(
  {
    files_id: suspectedFileId
  },
  {
    n: 1
  }
).sort({
  n: 1
});
~~~

If the chunk count or sequence is wrong, classify whether it is corruption or partial deletion.

### Step 5 — Reproduce via Driver

Read the full stream in a secure environment, compare against the application-stored checksum, and identify which chunk fails.

### Step 6 — Check for Concurrent Deletion Races

Did a cleanup job or user delete the file while a client was downloading? Are legal holds and grace periods enforced?

### Step 7 — Recover

If bytes are corrupted or missing, restore from backup or the original upload source. Never splice arbitrary chunks without an authentic data source.

### Step 8 — Prevent Recurrence

Add retention safeguards, active-download protection, metrics, orphan cleanup, and failover tests.

---

## 37. Common Misconceptions

**"GridFS only works for files larger than 16 MiB."** Not required; small files can be stored too, though chunk/metadata overhead may not be worthwhile.

**"GridFS automatically compresses video and generates thumbnails."** False. It stores bytes; it does not transcode.

**"Every `filename` is unique."** False. Multiple files can share the same name.

**"`revision(-1)` always points to the same version."** False. Uploading a new version changes which file is latest.

**"`revision(0)` is always business version 1."** Not if revisions were deleted/renamed or policies changed; it is simply the position by `uploadDate` within a filename group.

**"Renaming changes the file's bytes."** False. It only updates the filename in metadata.

**"Deleting by name deletes only the newest version."** Do not assume that; standard GridFS delete uses `fileId`, while by-name helpers vary by driver.

**"Reading 100 bytes requires loading the entire file into RAM."** False. Streaming and partial reads avoid that.

**"`InputStream.skip(n)` always skips all `n` bytes in one call."** False. Check the return value and loop.

**"HTTP Range end is exclusive."** False. `bytes=a-b` includes both `a` and `b`.

**"`Content-Range` is optional when returning `206`."** False. You must report the exact byte span and total size.

**"Any range past the end of the file is always `416`."** False if `start` is valid and only `end` exceeds length; clamp `end`.

**"`bytes=-500` means a negative start offset."** False. It requests the last 500 bytes.

**"Empty files have an empty data chunk."** GridFS only needs `files` metadata with `length=0`, without creating empty chunks.

**"Wrapping an upload in a MongoDB transaction makes all chunks atomic."** False. GridFS does not support multi-document transactions that way.

**"Deleting a file while readers are active is completely safe."** False. A race exists between `files` and `chunks`.

**"GridFS `md5` is a modern security checksum."** False. It is legacy/deprecated; applications should use SHA-256.

**"If `fs.files` has the record, all chunks are guaranteed present."** False. Metadata existence does not prove no chunks are missing.

**"Having a `fileId` means authorization isn't needed."** False. A `fileId` is not a credential.

**"Changing `chunkSizeBytes` re-chunks existing files."** False. Only subsequent uploads use the new setting.

**"Using `filename` as an `ETag` is enough."** False. A filename can point to different content; `ETag` must bind to immutable bytes/versions.

**"Backing up only `fs.files` is enough to recover files."** False. You need both `fs.chunks` and app metadata.

**"Scanning and immediately deleting orphan chunks is harmless."** False. It can delete chunks belonging to in-flight uploads.

---

## 38. Production Design Checklist

### 38.1. Range Reads

- [ ] Use `long` for lengths and offsets.
- [ ] Distinguish inclusive HTTP end from exclusive internal end.
- [ ] Handle `bytes=a-b`, `bytes=a-`, and `bytes=-n`.
- [ ] Handle empty files.
- [ ] Return `206` with accurate `Content-Range` and `Content-Length`.
- [ ] Return `416` for unsatisfiable ranges.
- [ ] Define policies for malformed and multiple ranges.
- [ ] Close GridFS streams when clients disconnect.
- [ ] Never load whole files into memory.
- [ ] Define `ETag`, `If-Range`, and `HEAD` policies.
- [ ] Test at exact chunk boundaries.

### 38.2. Filenames / Revisions

- [ ] Do not treat `filename` as a unique identity.
- [ ] Create a new `fileId` for every upload.
- [ ] Store `assetId`/`logicalVersion` in the app if immutable history is needed.
- [ ] Download by ID for signed/approved versions.
- [ ] Rename by ID.
- [ ] Delete by ID, never arbitrarily by name.
- [ ] Define a policy for renaming revision groups.
- [ ] Handle tie-breaking when `uploadDate` values are equal.
- [ ] Never use `-1` for immutably cached URLs.

### 38.3. Integrity, Security, and Retention

- [ ] Verify tenant/owner/visibility permissions.
- [ ] Sanitize MIME types and filenames.
- [ ] Apply malware/content validation where appropriate.
- [ ] Store SHA-256 when integrity verification is needed.
- [ ] Implement policies for incomplete uploads and orphans.
- [ ] Avoid deleting files with active readers per policy.
- [ ] Enforce legal holds and retention via app metadata.
- [ ] Back up `files`, `chunks`, and app metadata together.
- [ ] Audit downloads and version changes.
- [ ] Never expose raw `chunks` to end users.

### 38.4. Performance

- [ ] Benchmark chunk size.
- [ ] Ensure the compound unique index `files_id,n` exists.
- [ ] Ensure the `filename,uploadDate` index exists.
- [ ] Add metadata indexes if the workload requires them.
- [ ] Monitor database I/O and HTTP bandwidth.
- [ ] Limit concurrent streams and range abuse.
- [ ] Use a CDN/object storage when the workload calls for it.

---

## 39. Hands-On Exercises

### Exercise 1 — Explaining GridFS Structure

Diagram `fs.files` and `fs.chunks` for a 600,000 B file. State the chunk count, `files_id`, and `n`.

### Exercise 2 — Chunk Math

With C=261120 and L=600000, determine `firstChunk`, `lastChunk`, and how many bytes are taken from each chunk for `bytes=260000-263000`.

### Exercise 3 — Chunk Boundaries

Explain how many chunks `bytes=261119-261120` spans. Why is the range 2 bytes long rather than 1?

### Exercise 4 — Java `skip`

Write `skipFully(InputStream,long)` and test it against a mock `InputStream` whose `skip()` advances at most 7 bytes per call.

### Exercise 5 — Java `copyExactly`

Write `copyExactly` with a 64 KiB buffer, testing early EOF, `count=0`, and `count` larger than `Integer.MAX_VALUE`.

### Exercise 6 — HTTP Range Parser

Build a single-range parser. Test `bytes=0-0`, `bytes=500-`, `bytes=-500`, `bytes=599999-999999`, empty files, and numeric overflow.

### Exercise 7 — Correct HTTP Responses

With L=600000 and `Range:bytes=1000-1999`, write the exact status and headers. Why not return `200` when sending only one slice?

### Exercise 8 — Multi-Range

Analyze `bytes=0-99,200-299`. If a gateway does not support `multipart/byteranges`, which response strategy should it choose?

### Exercise 9 — `ETag` When Versions Change

A client downloads the first half from v1, then `current` switches to v2. Design `If-Range` so bytes from the two versions are never stitched together.

### Exercise 10 — Uploading Two Versions with the Same Filename

Upload v1 and v2 of `report.pdf` using Java `GridFSBucket`. Verify the two file IDs are distinct.

### Exercise 11 — Revision Semantics

Upload three versions with the same name. Download with `revision(0)`, `revision(1)`, `revision(-1)`, and `revision(-2)`; compare SHA-256 or raw bytes.

### Exercise 12 — Rename

Rename only v2's `fileId` to `report-reviewed.pdf`. Observe how revisions in both the old and new name groups change.

### Exercise 13 — Delete

Delete v1's `fileId`, ensuring v2 and v3 still download. When must retention/legal hold checks run before deleting?

### Exercise 14 — Metadata Index

Create an index on `metadata.tenantId,metadata.assetId,uploadDate`. Run `explain` on a query listing revisions by tenant.

### Exercise 15 — Business Version vs. Revision

Model `assets` and `assetVersions` for a 5-version document. Explain why `revision(-1)` is not equivalent to `currentVersion=5` in every situation.

### Exercise 16 — CAS Conflict

Two users upload simultaneously when `generation=3`. Write a conditional update ensuring only one user publishes the new version as current.

### Exercise 17 — No GridFS Transactions

Explain why a 2 GB file upload cannot be placed inside a multi-document transaction, and propose an upload-then-pointer pattern.

### Exercise 18 — Orphan Cleanup

Design a job that detects orphan chunks without deleting chunks from active uploads. Specify grace period, dry-run mode, and concurrency controls.

### Exercise 19 — File Checksum

Upload a file and store its SHA-256. Download the full stream to reconcile. Why does downloading a 1 KiB range not verify the whole file?

### Exercise 20 — Tenant Security

Have two tenants upload `invoice.pdf`. Write an API resolution flow using trusted `tenant + assetId + versionId` before opening the GridFS stream.

### Exercise 21 — Video Player

Design versioned URLs, Range handling, `ETag`, and CDN cache policies for multi-version videos. Identify what GridFS does not do automatically (transcoding/HLS).

### Exercise 22 — Backup/Restore

Suppose `media.files` is restored without `media.chunks`; what happens? Design reconciliation between `assetVersions.fileId` and GridFS metadata/chunks.

### Exercise 23 — Stress Test

Run 100 concurrent range downloads and 50 full downloads. Measure latency, RAM, chunk fetches, MongoDB CPU, and client abort rate.

### Exercise 24 — Retain Latest 3 Versions Policy

Design retention keeping current + 3 previous versions, preserving legal holds and avoiding deleting files actively being streamed. Write a runbook for partial deletions.

---

## 40. Review Questions

1. Why does GridFS split files into chunks?
2. Which two collections does the default GridFS bucket use?
3. What is the current default chunk size?
4. What unit is `fs.files.length` measured in?
5. What does `fs.files.chunkSize` help calculate?
6. Which field does `fs.chunks.files_id` point to?
7. What number does `fs.chunks.n` start from?
8. Does an empty file have an empty chunk?
9. Are GridFS chunks directly related to sharding chunks?
10. How many bytes does HTTP `bytes=100-199` contain?
11. Is the HTTP Range end inclusive or exclusive?
12. How is the chunk index containing offset `p` calculated?
13. How does a range spanning two chunks differ from a range inside one chunk?
14. Does `InputStream.skip` guarantee skipping the full amount in one call?
15. Why use a bounded buffer when downloading?
16. In which use cases do `downloadToStream` and `openDownloadStream` differ?
17. When do you return HTTP `200` vs. `206`?
18. What is `Content-Range` used for?
19. When do you return `416`?
20. What does `Range:bytes=-500` mean?
21. If the requested end exceeds file length while `start` is valid, is it `416`?
22. What content type is needed when multiple ranges are supported?
23. Why must `ETag` be tied to the exact version?
24. What bug does `If-Range` prevent?
25. Is `filename` unique in GridFS?
26. How are two files with the same name distinguished?
27. Which version is revision `0`?
28. Which version is revision `-1`?
29. Why is a revision index not an immutable logical version?
30. Does renaming a `fileId` alter its chunks?
31. Does `bucket.delete(fileId)` delete other versions sharing the same filename?
32. What risk arises from deleting concurrently with downloads?
33. Why does GridFS not support multi-document transactions?
34. What kind of leftover data does a mid-upload crash create?
35. Why does an orphan cleaner need a grace period?
36. Should GridFS `md5` be used as a modern security checksum?
37. How should SHA-256 be stored and verified for integrity?
38. Why must both `files` and `chunks` be backed up?
39. Why should applications maintain `assetId` and `assetVersions`?
40. What does CAS prevent during concurrent uploads?
41. Why shouldn't a user be allowed to read a file just by knowing its `ObjectId`?
42. When changing a display name, do you have to rename every GridFS version?
43. Why shouldn't you manually edit `fs.chunks.data` to fix a file?
44. What are the standard GridFS indexes?
45. When are tenant/asset metadata indexes needed?
46. How do small vs. large chunk sizes affect throughput and memory?
47. Does GridFS generate HLS or transcode video?
48. When should you use object storage instead of GridFS?
49. If a client aborts an HTTP download, which resources must be closed?
50. Why does a successful range read not prove the entire file is intact?

---

## 41. Summary

**GridFS** splits file content into multiple documents in `<bucket>.chunks` and stores per-file information in `<bucket>.files`. This enables storing files larger than the BSON document limit and accessing data via streaming.

Three essential areas:

**1. Range reads**

- Use `length` and `chunkSize` to locate the relevant chunks.
- HTTP `Range: bytes=a-b` has both ends **inclusive**.
- With the Java Sync Driver, use `openDownloadStream`, `skipFully`, and `copyExactly`.
- Return `206` with accurate `Content-Range`/`Content-Length`; return `416` when a range is unsatisfiable.
- Avoid loading whole files into RAM; manage `ETag`/`If-Range`, empty files, and multiple ranges.

**2. Filename management**

- `filename` is only a label, **not unique**.
- `fileId` identifies one exact version.
- `rename(fileId,newName)` changes only metadata, not chunks.
- For public URLs or auditing, verify authorization and prefer `fileId`/`versionId`.
- `filename` is not a security boundary, checksum, or cache validator.

**3. Multiple versions**

- GridFS revisions follow `filename` and `uploadDate`: `0` is oldest, `-1` is newest, `-2` is second newest.
- Revision positions can shift on uploads, deletes, or renames—they are not immutable business versions.
- Maintain `assets.currentFileId`, `assetVersions`, and `generation` for rigorous versioning.
- For every byte change, upload a new `fileId`, validate, and then publish the pointer.
- GridFS does not support multi-document transactions for file operations; handle orphan uploads, concurrent readers/deletions, backups, and controlled cleanup.

**Memorable operational rule:** When a client asks to "download 1,000 bytes of **the selected version**," the application must know **the exact `fileId`, byte range, access permissions, and file state**, rather than receiving a `filename` and guessing the newest copy.

## References

- [MongoDB Manual — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/)
- [MongoDB Manual — GridFS Indexes](https://www.mongodb.com/docs/manual/core/gridfs/#gridfs-indexes)
- [MongoDB GridFS Specification — Data Model, Revisions, Partial Reads](https://specifications.readthedocs.io/en/latest/gridfs/gridfs-spec/)
- [MongoDB Java Sync Driver — Large File Storage with GridFS](https://www.mongodb.com/docs/drivers/java/sync/current/crud/gridfs/)
- [MongoDB Java Sync Driver — GridFS API](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/driver-sync/com/mongodb/client/gridfs/package-summary.html)
- [MongoDB Java Sync Driver — Query Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Manual — BSON Document Size Limit](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MDN — HTTP Range Requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Range_requests)
- [MDN — Content-Range](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Range)
- [RFC 9110 — HTTP Semantics, Range Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-range-requests)
