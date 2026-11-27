# GridFsResource and serving content to the application layer

## 1. Context and objectives

In the **SPRING_DATA_MONGODB** module, we use Spring Data MongoDB to connect, map documents, and interact with MongoDB via `MongoTemplate` or repositories; we also cover queries, aggregations, indexes, transactions, reactive access, testing, and data performance diagnostics. Specifically, the **GridFS** chapter addresses storing and retrieving file contents in MongoDB.

Imagine a case management application: business metadata for documents resides in regular collections, while PDFs, images, or attachments are stored with GridFS. When a user clicks **Download**, the application must locate the right file, verify access rights, retrieve the binary data, and return an HTTP response with appropriate filename, content type, and size.

**GridFsResource** bridges GridFS data and Spring Framework's familiar **Resource** abstraction. Thanks to it, the web layer and file-processing services can consume data as a stream rather than manually assembling chunks into a large byte array.

After this lesson, you will be able to:

1. Distinguish the roles of GridFSFile, GridFsOperations, GridFsTemplate, and GridFsResource.
2. Look up a file by identifier, obtain a GridFsResource, and serve content via Spring MVC.
3. Set Content-Type, Content-Disposition, and Content-Length, and handle nonexistent files.
4. Read content safely via InputStream, avoiding loading entire files into memory.
5. Recognize differences between synchronous reading and ReactiveGridFsResource in WebFlux.
6. Design tests, error handling, and protection for download endpoints in production systems.

## 2. Where does GridFsResource fit in the architecture?

GridFS typically stores file metadata in the **fs.files** collection and split binary data in **fs.chunks** (with the default bucket `fs`). A `GridFSFile` record represents information about a file, such as its ID, filename, length, upload date, and metadata. It is **not** the entire binary content.

Key types:

| Component | Role | Key takeaways |
| --- | --- | --- |
| GridFSFile | Metadata object from MongoDB Java Driver | Contains ID, filename, length, uploadDate, metadata; not itself an HTTP response. |
| GridFsOperations | Spring Data GridFS operations interface | Provides findOne, find, getResource, store, delete. |
| GridFsTemplate | Synchronous implementation of GridFsOperations | Can be injected via the GridFsOperations type. |
| GridFsResource | Resource backed by a GridFSFile | Exposes InputStream, filename, content type, length, and related metadata. |
| Resource | Spring Framework resource abstraction | Widely used across HTTP components, services, and framework APIs. |
| ReactiveGridFsResource | File representation for reactive streams | Provides Flux<DataBuffer>; not the same type as synchronous Resource. |

Download flow diagram:

~~~mermaid
flowchart LR
    A["Client GET /api/files/id/content"] --> B["Controller"]
    B --> C["Verify authentication and permissions"]
    C --> D["Service"]
    D --> E["GridFsOperations.findOne"]
    E --> F[("fs.files")]
    D --> G["GridFsOperations.getResource"]
    G --> H["GridFsResource"]
    H --> I[("fs.chunks")]
    H --> J["Spring HTTP Resource converter"]
    J --> K["HTTP response body"]
~~~

In practice, the driver only reads data chunks when the download stream is consumed. A `GridFsResource` object allows the application layer to hold a reference to the content; it does not mean the whole file has already been loaded into RAM.

### 2.1. Essential APIs

~~~java
// Synchronous API, illustrating core operations.
GridFSFile file = gridFsOperations.findOne(query); // May return null.
GridFsResource resource = gridFsOperations.getResource(file);

boolean available = resource.exists();
String filename = resource.getFilename();
String contentType = resource.getContentType(); // May be null.
long length = resource.contentLength();

// Open stream only when actually reading; consumer must close stream.
try (InputStream input = resource.getInputStream()) {
    input.transferTo(output);
}
~~~

Note: the snippet above assumes **file is non-null**, **resource exists**, and **query** and **output** are already declared. This is an API illustration; a complete example appears in the next section.

**GridFsResource extends InputStreamResource**, so the resource and read stream are single-consumption per handling pass. Do not call `getInputStream` just to probe and then reuse that same resource object for an HTTP response. Calling `contentLength` on `GridFsResource` has a dedicated implementation suited to file size; in an application, if you already hold `GridFSFile`, you can also obtain the length via `getLength`.

### 2.2. Selecting files by filename or ID?

There are two common ways to retrieve a resource:

~~~java
GridFsResource byName = gridFsOperations.getResource("report.pdf");

GridFSFile file = gridFsOperations.findOne(
    Query.query(Criteria.where("_id").is(fileObjectId))
);
GridFsResource byId = gridFsOperations.getResource(file);
~~~

`getResource(String)` is convenient when filenames are unique by application convention. However, GridFS permits multiple files with the same filename (for instance, across updates). For user-facing endpoints, **file identifier** is usually the clearer choice: look up the exact `GridFSFile`, validate metadata and permissions, and obtain the resource from that exact object. If the system tracks versions, tenants, or document statuses, include those criteria in queries or business checks before returning content.

## 3. Complete example: serving GridFS content via Spring MVC

Suppose a Spring Boot application is configured with MongoDB, Spring Web MVC, and Spring Data MongoDB. Files are stored in the default GridFS bucket using MongoDB `ObjectId` identifiers. Endpoint to provide:

~~~text
GET /api/files/{id}/content

200 OK:    File content and corresponding HTTP headers
400:       ID does not match ObjectId format
404:       File not found
500/503:   Storage or read failure (handled/logged at infrastructure layer)
~~~

### 3.1. Service layer: look up metadata and obtain GridFsResource

~~~java
package example.files;

import java.util.NoSuchElementException;

import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;
import org.springframework.core.io.Resource;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.data.mongodb.gridfs.GridFsResource;
import org.springframework.stereotype.Service;

@Service
public class GridFsDownloadService {

    private final GridFsOperations gridFs;

    public GridFsDownloadService(GridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    public DownloadFile load(String hexId) {
        // Example uses ObjectId. Change this strategy if your system uses another ID type.
        if (!ObjectId.isValid(hexId)) {
            throw new IllegalArgumentException("Invalid GridFS file id");
        }

        Query query = Query.query(
            Criteria.where("_id").is(new ObjectId(hexId))
        );

        GridFSFile file = gridFs.findOne(query);
        if (file == null) {
            throw new NoSuchElementException("GridFS file not found");
        }

        // Here: verify access rights, tenant, document status...
        // Do not rely solely on the caller knowing the file ID.

        GridFsResource resource = gridFs.getResource(file);
        if (!resource.exists()) {
            throw new NoSuchElementException("GridFS resource not found");
        }

        return new DownloadFile(
            resource,
            file.getLength(),
            file.getFilename(),
            resource.getContentType()
        );
    }

    public record DownloadFile(
        Resource resource,
        long length,
        String filename,
        String contentType
    ) {}
}
~~~

**Why does the service return a record instead of byte[]?** The record carries only the resource and necessary metadata. Upon receiving it, the controller still has not loaded the entire file content into memory. Reading happens when the response is written.

**Why read length from GridFSFile?** Metadata has already been queried, allowing `Content-Length` to be set without opening and reading the `InputStream`. When storage is changing or a file is deleted between steps, streaming can still fail; that error must be monitored and handled at the infrastructure layer.

### 3.2. Controller layer: build the HTTP response

~~~java
package example.files;

import java.nio.charset.StandardCharsets;
import java.util.NoSuchElementException;

import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.InvalidMediaTypeException;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class GridFsDownloadController {

    private final GridFsDownloadService service;

    public GridFsDownloadController(GridFsDownloadService service) {
        this.service = service;
    }

    @GetMapping("/{id}/content")
    public ResponseEntity<Resource> download(@PathVariable String id) {
        GridFsDownloadService.DownloadFile file;
        try {
            file = service.load(id);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid file id", exception
            );
        } catch (NoSuchElementException exception) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "File not found", exception
            );
        }

        String safeFilename = sanitizeFilename(file.filename());
        ContentDisposition disposition = ContentDisposition.attachment()
            .filename(safeFilename, StandardCharsets.UTF_8)
            .build();

        return ResponseEntity.ok()
            .contentType(resolveMediaType(file.contentType()))
            .contentLength(file.length())
            .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
            .header("X-Content-Type-Options", "nosniff")
            .cacheControl(CacheControl.noStore())
            .body(file.resource());
    }

    private static MediaType resolveMediaType(String raw) {
        if (raw == null || raw.isBlank()) {
            return MediaType.APPLICATION_OCTET_STREAM;
        }
        try {
            return MediaType.parseMediaType(raw);
        } catch (InvalidMediaTypeException exception) {
            return MediaType.APPLICATION_OCTET_STREAM;
        }
    }

    private static String sanitizeFilename(String filename) {
        if (filename == null || filename.isBlank()) {
            return "download";
        }

        // Display only the final filename segment and strip CR/LF from metadata names.
        String normalized = filename.replace('\\', '/');
        String basename = normalized.substring(normalized.lastIndexOf('/') + 1)
            .replace('\r', '_')
            .replace('\n', '_');
        return basename.isBlank() ? "download" : basename;
    }
}
~~~

This is a **synchronous Spring MVC** example. A production application must implement access control checks at the commented spot in the service before allowing content to be opened. If an API serves public files with a dedicated caching strategy, adjust `Cache-Control` as required; the example uses `no-store` to avoid unintended caching of private files.

Key decisions in the controller:

| Detail | Effect | Notes |
| --- | --- | --- |
| ResponseEntity<Resource> | Lets Spring write Resource content to the response | Avoids reading all bytes manually in the controller. |
| Content-Type | Informs the client of content type | Falls back to application/octet-stream if metadata is missing or invalid. |
| Content-Disposition: attachment | Prompts browser to download the file | Can use inline for images/PDFs permitted to render directly. |
| filename with UTF-8 | Supports Unicode/Vietnamese filenames | Input filenames must be sanitized to avoid header/path injection. |
| Content-Length | Announces expected byte count | Uses already-fetched GridFSFile.getLength. |
| X-Content-Type-Options: nosniff | Restricts browser MIME sniffing | Useful when serving user-uploaded content. |
| Cache-Control: no-store | Prevents caching of sensitive files | Can be replaced with a policy suited to the use case. |
| 400 and 404 | Separates malformed ID from not found | Consider hiding resource existence when enforcing authorization. |

Spring MVC uses an appropriate HTTP converter to obtain the stream from `Resource` and copy it to the response. Do not call `getInputStream` before returning `ResponseEntity` because `GridFsResource` is a stream-backed resource meant to be consumed in a single pass.

### 3.3. Testing file download with curl

~~~bash
# Replace ID with a 24-hex-character ObjectId of an existing file.
curl -i "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"

# Save content to disk, taking filename from Content-Disposition.
curl -L -OJ "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"
~~~

Example headers received for a PDF:

~~~http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename*=UTF-8''ho-so.pdf
Content-Length: 145280
X-Content-Type-Options: nosniff
Cache-Control: no-store
~~~

This is only an **illustrative example**; actual filename, header encoding, and size depend on the file, HTTP library, and application configuration. To verify content integrity, compare the SHA-256 hash of the original and downloaded files in a controlled test environment.

## 4. Creating sample data to test the download path

If you need to create a GridFS file yourself, you can write content from an `InputStream` using `GridFsOperations.store`. Example upload service:

~~~java
import java.io.IOException;
import java.io.InputStream;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.gridfs.GridFsOperations;
import org.springframework.web.multipart.MultipartFile;

public class GridFsUploadExample {

    private final GridFsOperations gridFs;

    public GridFsUploadExample(GridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    public String upload(MultipartFile uploadedFile) throws IOException {
        try (InputStream input = uploadedFile.getInputStream()) {
            ObjectId id = gridFs.store(
                input,
                uploadedFile.getOriginalFilename(),
                uploadedFile.getContentType()
            );
            return id.toHexString();
        }
    }
}
~~~

This sample focuses on API usage; before deploying to production, enforce size limits, format/content validation, filename sanitization, authorization, and upload error handling. In particular, a client-sent `Content-Type` is **not proof** that the content actually matches that format. When malware protection is required, scan content per system policy.

Balanced read and write flows:

~~~text
Upload: multipart InputStream → gridFs.store(...) → fs.files + fs.chunks → ObjectId
Download: ObjectId → gridFs.findOne(...) → gridFs.getResource(...)
          → Spring Resource HTTP converter → response OutputStream
~~~

## 5. When the application layer needs to consume files without returning HTTP

The application layer may need to feed a PDF to a text extractor, generate a thumbnail, or write to an `OutputStream` provided by another service. In such cases, the consuming service itself must manage the `InputStream` lifecycle:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import org.springframework.data.mongodb.gridfs.GridFsResource;

public final class FileStreamCopier {

    private FileStreamCopier() {}

    public static void copy(GridFsResource source, OutputStream target)
            throws IOException {
        if (!source.exists()) {
            throw new java.io.FileNotFoundException(source.getFilename());
        }

        // Close the read source; caller retains ownership of target.
        try (InputStream input = source.getInputStream()) {
            input.transferTo(target);
        }
    }
}
~~~

Important principles:

- **Do not use readAllBytes()** for large files: this can pull the entire payload onto the heap and cause `OutOfMemoryError`.
- **Close streams** where data is directly read; in the `ResponseEntity<Resource>` example, Spring handles copying and closing the stream while writing the HTTP response.
- **Do not reuse the same InputStream** across multiple consumers. If reprocessing is needed, perform a new lookup and open a new Resource/stream.
- **Do not call available() to determine size**: it does not return total file size. Use `GridFSFile.getLength` or `GridFsResource.contentLength`.
- **Do not convert files to String arbitrarily**: data may be a PDF, image, or archive; decode to text only when charset and format are known.
- **Do not swallow mid-stream read errors**: if the MongoDB connection drops or a chunk is missing, log and report the error properly; never treat a truncated response as success.

## 6. Metadata and retrieval conditions

Download paths typically start from a **business document** containing the file ID, for example:

~~~json
{
  "_id": "application-120",
  "ownerId": "user-42",
  "attachmentGridFsId": "507f1f77bcf86cd799439011",
  "status": "APPROVED"
}
~~~

The proper flow is typically: identify caller → look up business document per permissions → extract authorized `attachmentGridFsId` → look up `GridFSFile` by ID → obtain resource → return content. Querying `fs.files` solely by ID without checking owner/tenant easily creates an **IDOR** vulnerability (users accessing other users' files by changing the ID in the URL).

Besides the ID, auxiliary metadata can be stored in GridFS on upload (business category, version, custom checksum, owner ID...). Metadata helps with filtering and verification, though it does not replace business-layer authorization rules. When using `filename` to find multiple versions:

~~~java
Query query = Query.query(
    Criteria.where("filename").is("statement.pdf")
);

GridFSFile oneFile = gridFsOperations.findOne(query);
~~~

Do not rely on `findOne` returning the newest version when multiple files share a name. Store the chosen copy's ID in the business document or use a well-defined versioning rule. For metadata-heavy queries, consider appropriate indexes on `fs.files`; measure with `explain`/monitoring under realistic load before optimizing.

## 7. Reactive reads with Spring WebFlux

For reactive applications, use **ReactiveGridFsOperations** (typically implemented by `ReactiveGridFsTemplate`) and **ReactiveGridFsResource**. Unlike synchronous `GridFsResource`, `ReactiveGridFsResource` exposes a **Flux<DataBuffer>** stream via `getDownloadStream`; there is no synchronous `Resource` return type to pass directly into `ResponseEntity<Resource>`.

Minimal WebFlux endpoint example, still using `ObjectId`:

~~~java
package example.files;

import org.bson.types.ObjectId;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsOperations;
import org.springframework.data.mongodb.gridfs.ReactiveGridFsResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/reactive-files")
public class ReactiveGridFsDownloadController {

    private final ReactiveGridFsOperations gridFs;

    public ReactiveGridFsDownloadController(ReactiveGridFsOperations gridFs) {
        this.gridFs = gridFs;
    }

    @GetMapping("/{id}/content")
    public Mono<ResponseEntity<Flux<DataBuffer>>> download(
            @PathVariable String id) {
        if (!ObjectId.isValid(id)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid file id"
            ));
        }

        Query query = Query.query(
            Criteria.where("_id").is(new ObjectId(id))
        );

        return gridFs.findOne(query)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "File not found"
            )))
            .flatMap(file -> gridFs.getResource(file)
                .filter(ReactiveGridFsResource::exists)
                .map(resource -> ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_OCTET_STREAM)
                    .contentLength(file.getLength())
                    .body(resource.getDownloadStream())
                )
            )
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "File not found"
            )));
    }
}
~~~

The reactive example returns a default MIME type to focus on the data stream; in a production API, add authorization, `Content-Disposition`, verified MIME type, caching policy, and tests just like the MVC version.

**Do not call `block()` or obtain `Mono<InputStream>` to buffer the entire file in RAM** inside WebFlux request handlers. The `ReactiveGridFsResource` API documentation states that `getInputStream` may buffer data in memory; for large files, prefer `getDownloadStream`. Reactive content is normally **single-consumption**, so do not manually subscribe beforehand and then hand the same stream to the framework.

When handling `DataBuffer` directly outside framework-managed HTTP pipelines, understand buffer release semantics (especially pooled buffers) to prevent memory leaks; never casually cache or hold long-lived references to emitted `DataBuffer` instances.

## 8. Common errors and diagnostics

| Symptom | Cause to check | Resolution |
| --- | --- | --- |
| Returns 404 despite filename existing | Querying wrong ID, wrong bucket, duplicate filenames, or mismatched metadata | Check ID/bucket/database and search criteria; prefer explicit IDs. |
| Returns 400 immediately | ID is not a valid hex ObjectId in the example | Match the ID type actually used by the application when saving. |
| Downloads succeed but filename/MIME is wrong | Missing metadata, unsanitized name, or bad Content-Disposition | Send proper headers, fallback MIME, and sanitize filename. |
| Heap spikes under concurrent downloads | Using byte[], readAllBytes, or collecting full Flux | Return Resource/Flux and monitor traffic, connections, and heap. |
| InputStream already consumed | Opening stream to inspect beforehand; logging content or reading twice | Open only when needed; perform a fresh retrieval per consumption. |
| Downloaded file is missing bytes | Network drop, missing chunk data, client aborted request | Check logs, actual length, MongoDB errors, and retry at appropriate layer. |
| Client requests Range but does not get 206 | Endpoint has not implemented byte-range retrieval | Implement Range/ResourceRegion support explicitly if required; do not assume GridFsResource handles it. |
| User can view unauthorized files | Checking ID only without checking business ownership | Authorize before retrieving content; test cross-tenant/owner cases. |
| Slow downloads under heavy load | Chunk reads, bandwidth, connection pool, or metadata query bottleneck | Monitor latency, pool, network, file sizes, DB metrics, and queries. |

For errors occurring after the body starts streaming, it may no longer be possible to change the HTTP status from 200 to 500. Therefore, monitor aborted connections, actual bytes transferred, and stream errors at the server or gateway rather than counting only final status codes.

## 9. Recommended test scenarios

Once sample GridFS data and working endpoints are in place, use integration tests against a real MongoDB instance in a test environment (such as MongoDB via Testcontainers) to verify driver + Spring Data + HTTP behavior:

| Scenario | Expected result |
| --- | --- |
| File exists, small content | 200; downloaded bytes equal original bytes; appropriate filename, Content-Type, Content-Length. |
| File larger than one GridFS chunk | 200; no lost/reordered chunks; output SHA-256 matches original data. |
| Malformed ID | 400; does not query MongoDB with an invalid ObjectId. |
| Valid ID that does not exist | 404; does not return empty body as success. |
| File with missing or invalid Content-Type | Content-Type header falls back to application/octet-stream. |
| File with Unicode/special characters in name | Download filename is properly encoded without CR/LF header injection. |
| Caller lacks permission on business document | 403 or 404 per policy; no content emitted. |
| Read interrupted mid-stream | Error logged, connection handled properly; not treated as a complete transfer. |
| Multiple concurrent download requests | Memory does not grow linearly with total size of all in-flight files. |

Quick verification via commands:

~~~bash
# Inspect response headers only (HEAD requires explicit support depending on server).
curl -I "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"

# Save returned file and inspect headers and status code.
curl -sS -D headers.txt -o downloaded.bin \
  "http://localhost:8080/api/files/507f1f77bcf86cd799439011/content"
~~~

To prove streaming truly avoids buffering entire files, inspect heap/GC and profile while concurrently downloading files significantly larger than the allowed heap size. A test comparing only a few bytes of a small file will not catch a `readAllBytes` bug.

## 10. Implementation principles in production systems

1. **Keep clear boundaries:** the business layer decides *who may download which file*; `GridFsOperations` handles querying and reading; the controller defines the HTTP contract.
2. **Use stable IDs:** filenames are only for display and headers; when multiple versions exist, store the exact referenced ID in business records.
3. **Stream data:** avoid collecting files into `byte[]` or `String`, especially when sizes are unknown in advance and concurrent requests are high.
4. **Handle metadata deliberately:** MIME types taken straight from clients are untrusted; filenames must be safe for headers and paths.
5. **Manage stream lifecycles:** services that read directly must close `InputStream`; controllers return `Resource` so Spring manages writing; reactive endpoints use `Flux<DataBuffer>` per subscription lifecycle.
6. **Enforce limits and observability:** set appropriate timeouts, track MongoDB/HTTP errors, throughput, latency, and user quotas; choose caching strategies based on content sensitivity.
7. **Advertise Range only when implemented:** download resume, video seeking, or PDF range requests are separate requirements needing byte-range reads and proper `206`/`Content-Range` headers.

`GridFsResource` is valuable because it preserves Spring's unified `Resource` interface while `GridFsOperations` handles finding and opening data stored in MongoDB. A solid endpoint does not merely download bytes—it selects the right file, enforces authorization, provides proper HTTP metadata, and streams content with controlled resource usage.

## 11. References

- [Spring Data MongoDB – GridFS Support](https://docs.spring.io/spring-data/data-mongo/reference/mongodb/template-gridfs.html): synchronous/reactive GridFS configuration and operations.
- [GridFsOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsOperations.html): findOne, getResource, store, and delete.
- [GridFsResource API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/GridFsResource.html): properties and InputStream access.
- [ReactiveGridFsOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/ReactiveGridFsOperations.html): Mono/Flux operations.
- [ReactiveGridFsResource API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/gridfs/ReactiveGridFsResource.html): getDownloadStream and consumption notes.
- [Spring Framework – ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html): returning Resource content from controllers.
