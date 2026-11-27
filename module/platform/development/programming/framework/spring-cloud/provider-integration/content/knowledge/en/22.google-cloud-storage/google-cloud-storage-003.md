# Uploading, Downloading, Listing, and Deleting Google Cloud Storage Objects

## 1. Context and Objectives

A Spring Boot application often needs to store user files, download documents on demand, list files within a business scope, and delete data when retention expires. On Google Cloud, **Cloud Storage** provides these operations through buckets and objects. The Java client library provides the **Storage** interface along with **BlobInfo**, **BlobId**, and **Blob** types so applications can perform operations on objects.

This lesson belongs to the **Google Cloud Storage** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on practicing Spring Boot integration with managed services on AWS, Azure, and Google Cloud through the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. This lesson focuses on the object operation lifecycle: **upload, download, list, and delete** using the Google Cloud Storage Java client in a Spring Boot application.

After this lesson, you will be able to:

- Configure the Google Cloud Storage Java client and inject **Storage** into a Spring service.
- Upload small content with **Storage.create** and large files with **WriteChannel**.
- Download objects to files or stream data using **ReadChannel**.
- List objects by prefix, paginate, and handle large listings.
- Delete objects safely using generation preconditions.
- Understand IAM permissions for create/get/list/delete and avoid overly broad grants.
- Handle 403, 404, 412, timeouts, and network errors with proper semantics.
- Write safe adapters and integration tests for dev/test/production environments.

> **Version scope:** Examples use the Google Cloud Storage Java client (artifact **com.google.cloud:google-cloud-storage**) and Spring Boot integration conventions. Manage versions using a BOM compatible with your project's Java/Spring baseline. APIs, transports, and options may change across releases; refer to the Javadoc for the exact resolved version. Buckets, projects, and object names in examples are illustrative data.

## 2. Object Operation Model

Cloud Storage stores data in buckets. An object is identified by bucket and object name; generation identifies a specific data version. When performing operations, distinguish **object metadata** from **object bytes**.

~~~mermaid
flowchart TD
    APP["Spring Boot service"] --> CLIENT["Storage Java client"]
    CLIENT --> CREATE["Upload / create"]
    CLIENT --> READ["Download / read"]
    CLIENT --> LIST["List by bucket / prefix"]
    CLIENT --> DELETE["Delete object"]
    CREATE --> GCS["Google Cloud Storage"]
    READ --> GCS
    LIST --> GCS
    DELETE --> GCS
    IAM["ADC / workload identity + IAM"] -. "Authenticates and authorizes" .-> CLIENT
~~~

| Component | Role |
| --- | --- |
| Project | Contains buckets, IAM, billing, and quotas |
| Bucket | Container holding objects |
| Object name | Identifier of an object within a bucket |
| BlobId | Identifies bucket/object, optionally including generation |
| BlobInfo | Metadata describing an object when creating or updating |
| Blob | Snapshot of an existing object's metadata and related operations |
| Storage | Client executing RPCs to Cloud Storage |
| ReadChannel | Channel for streaming bytes when reading |
| WriteChannel | Channel for streaming bytes when writing |

The URI **gs://training-documents-dev/reports/2026/report.pdf** only describes the object's location. It does not grant access permissions and does not mean the object has a public HTTP URL.

### 2.1. Choosing an API by Size and Use Case

| Requirement | Commonly used API | Characteristics |
| --- | --- | --- |
| Upload small in-memory content | Storage.create with byte array | Simple; entire content already resides in a byte array |
| Upload large file/stream | Storage.writer with BlobWriteOption | Writes via WriteChannel, suited for streaming/resumable upload |
| Read metadata | Storage.get with BlobId | Fetches Blob; does not automatically download all bytes |
| Download to file | Blob.downloadTo or Storage.downloadTo | SDK manages the download operation |
| Streaming download | Storage.reader with BlobId | Uses ReadChannel, actively transfers data |
| List objects | Storage.list with BlobListOption | Returns Page<Blob>, supports prefix and pagination |
| Delete object | Storage.delete with BlobSourceOption | Can use generation precondition |

**Do not use a byte array for large files just because the API is shorter.** Loading entire files onto the heap can increase memory pressure, cause long GC pauses, or trigger OutOfMemoryError when multiple upload/download requests run concurrently.

## 3. Preparing Dependencies, Project, and Credentials

### 3.1. Java Client Dependency

If the project uses Maven and has imported a BOM managing Google Cloud libraries:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>google-cloud-storage</artifactId>
    </dependency>
</dependencies>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("com.google.cloud:google-cloud-storage")
}
~~~

If the application uses Spring Framework on Google Cloud, you can use the BOM and Storage starter to auto-configure the Storage bean; this was introduced in the client and Spring Resource integration lesson. When importing Java client classes directly in source code, check your project's dependency policy and declare the artifact directly if required. Do not pin a separate version incompatible with the BOM.

### 3.2. Application Default Credentials

The Java client typically uses **Application Default Credentials (ADC)**:

~~~java
Storage storage = StorageOptions.getDefaultInstance().getService();
~~~

In local development, developers can set up ADC with:

~~~bash
gcloud auth application-default login
gcloud config set project training-platform-dev
~~~

The two commands serve different purposes: the first creates credentials for applications; the second sets the default project for the CLI. The project configuration used by the Java client must still be verified across StorageOptions, ADC, and the application's Spring configuration.

When running on Google Cloud, prefer a service account attached to the workload or appropriate Workload Identity Federation. Do not package JSON private keys into source code, container images, or artifacts.

### 3.3. Creating a Storage Bean in Spring

If the Spring Framework on Google Cloud Storage starter has already auto-configured a Storage bean, inject that bean:

~~~java
import com.google.cloud.storage.Storage;
import org.springframework.stereotype.Service;

@Service
public class CloudStorageOperations {

    private final Storage storage;

    public CloudStorageOperations(Storage storage) {
        this.storage = storage;
    }
}
~~~

If creating the bean manually, configure it once in the ApplicationContext:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GcsConfiguration {

    @Bean
    Storage storage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

Do not create a new Storage client per request. The client can be reused; manage its lifecycle via Spring configuration and close it on application shutdown if you own the client directly.

### 3.4. Configuring Bucket and Project

Place the bucket name in a property:

~~~yaml
app:
  gcs:
    bucket: APP_DOCUMENT_BUCKET
~~~

**APP_DOCUMENT_BUCKET** is the environment variable name provided by the deployment. The local value might be **training-documents-dev**; staging and production need separate buckets. A bucket name is not a secret, but you should not hard-code a production bucket in shared source code or allow client requests to arbitrarily choose a bucket.

## 4. IAM Permissions for Each Operation

Cloud Storage uses IAM to determine whether a principal can operate on objects. Fundamental permissions to understand:

| Operation | Primary permission | Notes |
| --- | --- | --- |
| Upload new object | storage.objects.create | Permission to create objects in the bucket |
| Download/read object | storage.objects.get | Read bytes and metadata |
| List objects | storage.objects.list | Bucket listing permission; a prefix in code does not replace IAM |
| Delete object | storage.objects.delete | Can be blocked by retention/holds |
| View bucket metadata | storage.buckets.get | Does not imply permission to read objects |
| Create bucket | storage.buckets.create | Typically a provisioning role, not runtime |

Common predefined roles:

- **roles/storage.objectViewer:** read objects and metadata within the granted scope; suitable for read-only services.
- **roles/storage.objectCreator:** create new objects; does not implicitly grant read, delete, or overwrite on existing objects.
- **roles/storage.objectUser:** provides a broader set of object permissions per the current role definition; suitable for workloads needing multiple object operations.
- **roles/storage.objectAdmin:** administer objects within the granted scope.
- **roles/storage.admin:** broad bucket/object administration; intended for infrastructure admin tasks, not default for runtime.

When overwriting an existing object, Cloud Storage may require both create permission and delete permission on the old object depending on operation semantics. Grant permissions matching actual operations and test with the runtime principal. Do not use roles/storage.admin to work around a single upload failure.

### 4.1. Prefixes Are Not Security Boundaries

For example, a service passes only the prefix **tenant-a/** to a list call. That only limits the results requested by the code; if the service account has permission to list/read the entire bucket, the principal can still request another prefix. To isolate tenants, enforce application-level authorization, appropriate IAM conditions, or separate buckets/projects based on security requirements.

### 4.2. UBLA and Public Access Prevention

For buckets using Uniform bucket-level access (UBLA), manage permissions through IAM rather than object/bucket ACLs. Public Access Prevention helps prevent unintended public grants. Do not create public ACLs to make upload/download "easy to test." If end users need to download objects, the backend can issue time-limited signed URLs after verifying business permissions.

## 5. Uploading Small Objects with Storage.create

### 5.1. Creating BlobInfo

BlobInfo describes the object before uploading. You can set content type, cache control, and custom metadata:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import java.util.Map;

BlobInfo blobInfo = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName))
    .setContentType("application/pdf")
    .setCacheControl("private, max-age=0")
    .setMetadata(Map.of(
        "source-system", "document-api",
        "document-id", documentId))
    .build();
~~~

Do not place secrets, access tokens, or sensitive data in custom metadata. Metadata does not replace a database; if complex queries are needed, store indexes in a database.

### 5.2. Uploading with a Byte Array

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;

public Blob uploadText(
        Storage storage,
        String bucket,
        String objectName,
        String text) {

    BlobInfo info = BlobInfo.newBuilder(
            BlobId.of(bucket, objectName))
        .setContentType("text/plain; charset=utf-8")
        .build();

    return storage.create(
            info,
            text.getBytes(StandardCharsets.UTF_8),
            Storage.BlobTargetOption.doesNotExist());
}
~~~

doesNotExist is a precondition: the request succeeds only if no live object with the same name exists yet. If the object already exists, GCS rejects the operation instead of silently overwriting. This prevents race conditions better than calling storage.get to check first and uploading afterward.

The resulting Blob contains metadata of the newly created object, including its generation. You can persist the generation in a database if business logic needs to reference an exact data version.

### 5.3. Conditional Overwrite

If business rules allow replacing an object only when its generation still matches the value read earlier:

~~~java
BlobInfo info = BlobInfo.newBuilder(
        BlobId.of(bucket, objectName))
    .setContentType("application/pdf")
    .build();

Blob replaced = storage.create(
        info,
        content,
        Storage.BlobTargetOption.generationMatch(expectedGeneration));
~~~

If another worker has written a new version, the generation no longer matches and the request is rejected with a precondition error. Do not drop the condition just to force the write to succeed; re-read state and decide whether to merge or return a conflict.

### 5.4. Content-Type and Checksums

- Set Content-Type based on validated content, not solely by trusting user-supplied extensions.
- When uploading via APIs that support it, use CRC32C to verify data integrity.
- Do not assume ETag is always an MD5 hash.
- For compressed data or encrypted files, understand which bytes the checksum is validating.
- Do not log sensitive payloads when debugging upload failures.

## 6. Uploading Large Files with WriteChannel

For large files or data coming from an HTTP request stream, use Storage.writer to write via WriteChannel, avoiding allocating a byte array containing the entire content.

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void uploadStream(
        Storage storage,
        BlobInfo blobInfo,
        InputStream source) throws IOException {

    try (WriteChannel writer = storage.writer(
                blobInfo,
                Storage.BlobWriteOption.doesNotExist());
         OutputStream output = Channels.newOutputStream(writer)) {
        source.transferTo(output);
    }
}
~~~

WriteChannel supports streaming/resumable upload behavior depending on client and transport configuration. Closing the channel finalizes the operation and releases resources. If source is owned by the caller, clearly decide which layer closes source; the example above closes only the writer/output created in the method, leaving source managed by the caller.

### 6.1. Choosing an Upload Method by Data Type

| Data type | Appropriate approach | Notes |
| --- | --- | --- |
| Text/JSON of a few KB | Storage.create with byte array | Simple |
| Small images or size-bounded files | Storage.create with byte array | Check size before allocating |
| Multipart upload from HTTP | Storage.writer | Stream from request, do not read all into heap |
| Large local file | Files.newInputStream(path) + WriteChannel or appropriate upload API | Limit concurrency and timeouts |
| Data needing advanced resume/retry | Resumable upload/transfer tooling per SDK | Check version, chunk size, retries, and cost |

Do not grow upload threads indefinitely. Each concurrent upload consumes connections, buffers, CPU, and network bandwidth; set concurrency limits appropriate for the service's resources.

### 6.2. Uploading from a Local File

~~~java
import com.google.cloud.WriteChannel;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.file.Files;
import java.nio.file.Path;

public void uploadFile(
        Storage storage,
        BlobInfo info,
        Path sourceFile) throws Exception {

    try (InputStream input = Files.newInputStream(sourceFile);
         WriteChannel writer = storage.writer(
                 info, Storage.BlobWriteOption.doesNotExist());
         OutputStream output = Channels.newOutputStream(writer)) {
        input.transferTo(output);
    }
}
~~~

The example assumes the file has already been checked for access permissions, content type, and size. If the file was uploaded by a user, do not use the raw filename as a local path or object name; generate a stable ID and validate the content.

## 7. Downloading Objects to Files

### 7.1. Fetching Metadata Before Downloading

Storage.get(BlobId) returns a Blob if the object exists, or null if not found. This is a metadata read operation; it does not mean the bytes have been downloaded.

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public Blob findObject(
        Storage storage,
        String bucket,
        String objectName) {

    return storage.get(BlobId.of(bucket, objectName));
}
~~~

When Blob is null, return an appropriate not-found result. When receiving 403, do not turn it into not-found if the system needs to distinguish access denial from missing data.

### 7.2. Downloading Directly to a Path

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public boolean downloadToFile(
        Storage storage,
        String bucket,
        String objectName,
        Path destination) {

    Blob blob = storage.get(BlobId.of(bucket, objectName));
    if (blob == null) {
        return false;
    }

    blob.downloadTo(destination);
    return true;
}
~~~

downloadTo(Path) is a simple option for medium/small files or when a local file is required. In production, verify:

- The destination directory exists and the process has write permission.
- The destination file is not accidentally overwritten.
- Disk space is sufficient for the object.
- The filename is generated from validated data, without directly concatenating untrusted input.
- Temporary files are cleaned up if the download fails mid-way.
- Size and download duration limits are enforced.

If you need to read the exact recorded generation, build BlobId with generation instead of using only the live object name.

### 7.3. Downloading a Specific Generation

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.nio.file.Path;

public boolean downloadGeneration(
        Storage storage,
        String bucket,
        String objectName,
        long generation,
        Path destination) {

    BlobId versionedId = BlobId.of(bucket, objectName, generation);
    Blob blob = storage.get(versionedId);

    if (blob == null) {
        return false;
    }

    blob.downloadTo(destination);
    return true;
}
~~~

Generation is useful when a workflow must guarantee it downloads the exact bytes recorded by an earlier step. If only the object name is used, a new upload could cause the application to download a different live generation than the original version.

### 7.4. Do Not Load Entire Files into Heap

APIs such as getContent or readAllBytes are convenient for small objects, but they return a byte array. Do not use them for unbounded large files. For large objects, stream directly to a file or response output stream.

## 8. Streaming Downloads with ReadChannel

ReadChannel allows reading an object incrementally and is well suited when data must be forwarded to an HTTP response, a file, or another streaming processor.

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.channels.Channels;

public void streamTo(
        Storage storage,
        String bucket,
        String objectName,
        OutputStream destination) throws IOException {

    BlobId blobId = BlobId.of(bucket, objectName);

    try (ReadChannel reader = storage.reader(blobId);
         InputStream input = Channels.newInputStream(reader)) {
        input.transferTo(destination);
    }
}
~~~

This method does not close destination, because the output stream is usually managed by the controller/HTTP framework. It closes the ReadChannel and input wrapper created within the method.

### 8.1. Streaming Objects in Spring MVC

A controller can return StreamingResponseBody to avoid holding the entire content on the heap:

~~~java
import com.google.cloud.ReadChannel;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import java.io.InputStream;
import java.nio.channels.Channels;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@RestController
public class DocumentDownloadController {

    private final Storage storage;

    public DocumentDownloadController(Storage storage) {
        this.storage = storage;
    }

    @GetMapping("/documents/{id}/content")
    public ResponseEntity<StreamingResponseBody> download(
            @PathVariable String id) {

        String bucket = "training-documents-dev";
        String objectName = "documents/" + id + ".pdf";

        StreamingResponseBody body = output -> {
            try (ReadChannel reader = storage.reader(
                        BlobId.of(bucket, objectName));
                 InputStream input = Channels.newInputStream(reader)) {
                input.transferTo(output);
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"document.pdf\"")
                .body(body);
    }
}
~~~

This is a skeleton example. Before creating the stream, authenticate the user, verify access permissions for the document ID, confirm the object exists, and retrieve the appropriate content type/size. Do not allow clients to pass arbitrary buckets or access objects simply by guessing IDs.

With WebFlux, the Storage Java client is a blocking API. Do not call it directly on the event loop; offload blocking tasks to an appropriate scheduler or design a dedicated asynchronous adapter.

### 8.2. Range Downloads and Resuming

If the application needs to download chunks or resume downloads, review ReadChannel and the range/seek APIs supported by your client library release. Resolve the generation before downloading multiple chunks; if the live object changes between requests, the reassembled data may not come from the same version. Use a specific generation or precondition to preserve consistency.

## 9. Listing Objects by Bucket and Prefix

### 9.1. Listing Objects

Storage.list(bucket, BlobListOption...) returns Page<Blob>. Example:

~~~java
import com.google.api.gax.paging.Page;
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.Storage;

public void listAll(Storage storage, String bucket) {
    Page<Blob> page = storage.list(
            bucket,
            Storage.BlobListOption.pageSize(100));

    for (Blob blob : page.iterateAll()) {
        System.out.printf(
                "%s | %d bytes | generation=%d%n",
                blob.getName(),
                blob.getSize(),
                blob.getGeneration());
    }
}
~~~

iterateAll() traverses subsequent pages using the client's paging mechanism. This is convenient for batch jobs that must process all results, but you should not collect every object into a single List if the bucket holds millions of objects. Process items individually, write results in batches, or narrow the prefix scope.

### 9.2. Listing by Prefix

~~~java
Page<Blob> page = storage.list(
        bucket,
        Storage.BlobListOption.prefix("reports/2026/"),
        Storage.BlobListOption.pageSize(100));

for (Blob blob : page.iterateAll()) {
    System.out.println(blob.getName());
}
~~~

Prefix is an object-name filter, not a physical directory in a flat namespace and not an IAM boundary. Use prefixes to organize data, process by tenant, or group by date; access control is still governed by IAM.

### 9.3. Directory-Like Mode

If you need to display listings by folder level, combine BlobListOption.currentDirectory() with prefix:

~~~java
Page<Blob> page = storage.list(
        bucket,
        Storage.BlobListOption.prefix("reports/"),
        Storage.BlobListOption.currentDirectory());

for (Blob blob : page.iterateAll()) {
    System.out.println(blob.getName());
}
~~~

This mode uses a delimiter to group results into objects and sub-prefixes per API semantics. With a flat namespace, a sub-prefix is not necessarily an independent folder resource. If the bucket enables hierarchical namespace, consult the corresponding documentation and choose APIs matching that bucket structure.

### 9.4. Explicit Pagination

When an application API needs to return pages to users, do not call iterateAll() and slice the list afterward. Use page size and page tokens/cursors supported by the API to fetch one page at a time.

~~~java
Page<Blob> page = storage.list(
        bucket,
        Storage.BlobListOption.prefix(prefix),
        Storage.BlobListOption.pageSize(50));

List<BlobSummary> summaries = new ArrayList<>();

for (Blob blob : page.getValues()) {
    summaries.add(new BlobSummary(
            blob.getName(),
            blob.getSize(),
            blob.getGeneration()));
}

String nextPageToken = page.getNextPageToken();
~~~

In the application's web API, you can return nextPageToken to the client and use that token to fetch the next page. Verify how page tokens are passed according to your BlobListOption version; do not construct tokens from object names yourself.

### 9.5. Fetch Only Needed Metadata

List returns object metadata and does not download each object's bytes. You can therefore use list to display name, size, content type, generation, and update timestamp without downloading every file. If content must be read, execute a separate operation after verifying permissions and enforcing request limits.

### 9.6. Avoid Listing the Entire Bucket in User Requests

Listing an entire bucket can return massive result sets, consume quota, and increase latency. You should:

- Always specify a prefix scoped to the business domain whenever possible.
- Use an appropriate page size.
- Avoid calling list repeatedly on every screen render if metadata/indexes can be cached.
- Do not use GCS list like a database query over custom metadata.
- Cap the number of objects returned in a single HTTP request.
- Use a database/index when complex sorting, filtering, or search is required.

## 10. Controlled Object Deletion

### 10.1. Deleting by Bucket and Object Name

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public boolean deleteObject(
        Storage storage,
        String bucket,
        String objectName) {

    return storage.delete(BlobId.of(bucket, objectName));
}
~~~

Returning true indicates deletion succeeded; false may indicate the object did not exist. Permission errors, retention blocks, or service errors may be thrown as StorageException; do not catch all exceptions and return false because that hides real errors.

### 10.2. Deleting the Exact Generation

When a workflow has read object generation G1, but the object might be replaced before deletion, use a generation precondition:

~~~java
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;

public boolean deleteIfUnchanged(
        Storage storage,
        String bucket,
        String objectName,
        long expectedGeneration) {

    return storage.delete(
            BlobId.of(bucket, objectName),
            Storage.BlobSourceOption.generationMatch(
                    expectedGeneration));
}
~~~

If the live generation has changed, the request is rejected instead of accidentally deleting the new version. This protects against concurrent operations by multiple workers or users.

### 10.3. Deleting a Specific Object Version

If the bucket has Object Versioning enabled and business logic needs to delete a specific generation, use BlobId with the corresponding generation and SDK-supported options. Distinguish between:

- Deleting the current live object.
- Deleting a noncurrent generation.
- Soft delete according to bucket configuration.
- Permanent deletion when allowed by retention policies.

Do not assume a delete call always makes bytes vanish immediately. Object Versioning, soft delete, retention policies, event-based holds, or temporary holds can alter retention outcomes and recoverability.

### 10.4. Deletion Is Not a Rollback Operation

Once an application deletes an object, recoverability depends on bucket policies and retention configuration. Before deleting at a user's request:

1. Authenticate the principal and verify document ownership.
2. Identify the target bucket/object/generation.
3. Check retention/hold rules if required by business logic.
4. Record an audit event per policy without logging sensitive content.
5. Use a generation precondition if the object can be updated concurrently.
6. Handle false, 403, 404, 412, and service errors distinctly.

Do not expose bulk deletion APIs based on arbitrary prefixes without proper limits, confirmation, and auditing.

## 11. Encapsulating Operations in a Storage Adapter

A Spring Boot service should encapsulate GCS operations in an adapter instead of letting controllers call the SDK directly. Example:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.BlobInfo;
import com.google.cloud.storage.Storage;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentObjectAdapter {

    private final Storage storage;
    private final String bucket;

    public DocumentObjectAdapter(
            Storage storage,
            @Value("${app.gcs.bucket}") String bucket) {
        this.storage = storage;
        this.bucket = bucket;
    }

    public Blob uploadText(String objectName, String text) {
        BlobInfo info = BlobInfo.newBuilder(
                BlobId.of(bucket, objectName))
            .setContentType("text/plain; charset=utf-8")
            .build();

        return storage.create(
                info,
                text.getBytes(StandardCharsets.UTF_8),
                Storage.BlobTargetOption.doesNotExist());
    }

    public Blob find(String objectName) {
        return storage.get(BlobId.of(bucket, objectName));
    }

    public boolean delete(String objectName, long generation) {
        return storage.delete(
                BlobId.of(bucket, objectName),
                Storage.BlobSourceOption.generationMatch(generation));
    }
}
~~~

This example focuses on upload/find/delete; listing should be exposed via a paginated API instead of returning all objects in a single List. The bucket is injected via properties rather than hard-coded. A real adapter must map StorageException to meaningful application errors, validate object names, enforce size limits, and prevent users from picking buckets outside an allowlist.

## 12. End-to-End Workflow Example: Upload, List, Download, and Delete

A document management flow can execute in sequence:

~~~mermaid
sequenceDiagram
    participant API as Spring Boot API
    participant IAM as Workload identity / IAM
    participant GCS as Cloud Storage

    API->>IAM: Acquire workload credentials
    API->>GCS: Upload object (create + precondition)
    GCS-->>API: Blob metadata + generation
    API->>GCS: List by prefix
    GCS-->>API: Page<Blob>
    API->>GCS: Download object/generation
    GCS-->>API: Object bytes
    API->>GCS: Delete with generation match
    GCS-->>API: deleted=true/false
~~~

The business design should persist at minimum:

- The application's document ID.
- Bucket and object name (or an internal identifier mapped to them).
- Generation if the exact version must be downloaded/deleted later.
- Content type and size if needed for display.
- Business status and audit metadata in the database.

It is not necessary to store all Blob metadata in the database; persist only fields needed for business logic and recoverability.

## 13. Using gcloud for Quick Verification

The Java client is the integration path inside applications; gcloud storage is useful for manual inspection or debugging.

### 13.1. Upload

~~~bash
gcloud storage cp ./sample.pdf gs://training-documents-dev/reports/sample.pdf
~~~

### 13.2. Download

~~~bash
gcloud storage cp gs://training-documents-dev/reports/sample.pdf ./downloaded-sample.pdf
~~~

### 13.3. List

~~~bash
gcloud storage ls --recursive gs://training-documents-dev/reports/
~~~

### 13.4. Delete

~~~bash
gcloud storage rm gs://training-documents-dev/reports/sample.pdf
~~~

These commands use gcloud's current project/credentials. Before running them, verify the active project and principal to avoid modifying a production bucket by mistake. CLI success does not automatically prove the Java process uses the same ADC or IAM identity.

## 14. Testing Upload/Download/List/Delete

### 14.1. Unit Tests

Unit tests focus on business logic and adapters:

- Validate object names and prefixes.
- Build metadata with the right content type.
- Reject uploads exceeding size limits.
- Handle duplicate objects when the doesNotExist precondition fails.
- Map not found, permission denied, and precondition conflicts.
- Verify the adapter closes streams properly.
- Verify delete is called only after business permissions are confirmed.

Mock Storage or define a DocumentStorage interface to test services without needing a real GCP project.

### 14.2. Integration Tests on a Dedicated GCP Project

A real integration test can verify:

1. Upload an object with a unique name in a test bucket.
2. Read back metadata and generation.
3. Download the object and compare checksums/bytes.
4. List by prefix and verify the object appears.
5. List with a different prefix and confirm unrelated objects are not returned.
6. Delete the object with generation match.
7. Attempt to delete again and handle the not-found result.
8. Attempt to delete using an old generation after the object has been replaced; expect precondition failure.
9. Clean up test resources according to dedicated procedures.

Do not run destructive tests on production buckets or shared buckets owned by other teams. Tests need a dedicated service account/workload identity with least-privilege permissions.

### 14.3. Testing Large Payloads and Streaming

For large uploads/downloads, also test:

- Data larger than the heap budget for a single request.
- Multiple concurrent uploads/downloads within concurrency limits.
- Network interruption mid-stream.
- Client closing the stream early.
- Timeouts and retries.
- Checksums/bytes after downloading.
- Disk full or destination file write errors.

Do not test only a few-KB file and conclude that streaming works properly for multi-GB files.

### 14.4. Testing IAM

Verify each principal has the exact expected permissions:

| Test principal | Expected operations |
| --- | --- |
| Upload-only | Create new objects; cannot list or delete unless granted |
| Read-only | Get objects; cannot upload/delete |
| List/read | List prefix and download objects; cannot modify/delete |
| Cleanup role | Delete test objects within a dedicated bucket/prefix |
| Production runtime | Only permitted business operations |

IAM permission tests must be verified via real operations against test resources. Do not assume local fakes or mocks can prove real GCP policies.

## 15. Common Errors and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| 403 Forbidden on upload | Principal lacks storage.objects.create or blocked by policy | Check ADC/workload identity and IAM scope |
| New object upload succeeds but overwrite fails | Principal lacks permission to delete old object or precondition mismatch | Check IAM and generation |
| 404 Not Found on download | Wrong bucket/object name or generation does not exist | Verify identifier and object version |
| 403 on download | Missing storage.objects.get | Verify principal and role |
| List returns empty but get object succeeds | Missing storage.objects.list, wrong prefix, or different bucket | Check list permission and prefix |
| List is too slow | Listing entire bucket, too many objects, unsuitable page size/concurrency | Use prefixes, paging, indexes/caches |
| 412 Precondition Failed | Generation/metageneration no longer matches | Re-read state and resolve conflict |
| Delete returns false | Object does not exist or generation is no longer the live object | Verify bucket/object/version |
| Delete rejected | Missing storage.objects.delete, retention/hold, or policy block | Check IAM, retention, and holds |
| Download causes OOM | Loading entire bytes into heap | Use ReadChannel/streaming |
| Large upload fails mid-way | Timeout, non-replayable stream, network, or chunk configuration | Check resumable upload, retries, and transport |
| Java and gcloud access different projects | ADC differs from CLI config or overridden project property | Check project ID and Java principal |
| Object name with `/` behaves unexpectedly | Confused prefix with real folder or wrong encoding | Verify full name and bucket namespace |

### 15.1. Distinguishing 403, 404, and 412

- **403:** the request is authenticated, but the principal lacks permission or a policy/condition denies it.
- **404:** the resource/object/version does not exist or the API returns not found in context.
- **412:** the precondition failed; object state changed relative to the caller's assumption.

Do not retry 403/412 indefinitely. For 412, re-read the generation and handle the conflict. For 403, fix IAM permissions. For 404, check identifiers and object lifecycle.

### 15.2. Safe Logging

Log fields useful for investigation such as operation, bucket alias, internal object ID, generation, status code, latency, and request correlation ID. Do not log file contents, credentials, signed URLs, or sensitive metadata. If object names contain personal data, consider logging a hash or internal identifier instead.

## 16. Retention, Versioning, and Cost

Deleting an object does not always mean data is permanently removed immediately. The outcome depends on:

- Object Versioning.
- Soft delete.
- Retention policy and Bucket Lock.
- Event-based hold or temporary hold.
- Lifecycle rules.
- Which specific generation was deleted.

When versioning is enabled, overwriting or deleting a live object can leave the old generation as a noncurrent version. Soft delete can retain deleted objects for a configured period. Retention policies can block deletion before the required duration. Therefore, the application's delete API must accurately reflect business intent: "mark deleted," "hide from users," "delete live object," or "permanently delete" are distinct concepts.

### 16.1. Lifecycle Cleanup

If a bucket retains many objects/versions, design lifecycle rules to transition storage classes or delete objects/noncurrent generations over time. Check rule conditions, minimum storage class durations, retention, and legal requirements before applying.

### 16.2. Operation Costs

Upload, list, get, and delete operations may be billed according to Cloud Storage operation/usage tiers. Frequent full-bucket listings or repeated downloads of large files can increase request and network costs. Incorporate prefixes, caching/indexing, and streaming downloads into your design to avoid unnecessary costs.

## 17. Comprehensive Hands-On Exercise

**Context:** Build a Spring Boot application `document-api` that manages documents for multiple tenants. Files are stored in bucket `training-documents-dev`, with object names following the pattern `documents/{tenantId}/{documentId}/{fileName}`. The application supports uploading, listing documents, downloading files, and deleting documents.

### Task A — Upload

1. Create a Storage bean via ADC or the Spring Framework on Google Cloud starter.
2. Write an upload API with size limits, content type validation, and safe object naming.
3. Upload small files using Storage.create.
4. Upload large files using WriteChannel.
5. Use doesNotExist to prevent unintended object overwrites.
6. Save generation and necessary metadata into the database.

### Task B — Download

1. Look up the document by ID and check tenant authorization.
2. Fetch Blob metadata and determine content type/size.
3. Stream bytes using ReadChannel to the HTTP response.
4. If the exact approved version must be downloaded, use the stored generation.
5. Design safe response headers and avoid exposing internal bucket/object names.

### Task C — List

1. List objects by tenant prefix.
2. Use pageSize and page tokens for pagination.
3. Do not download bytes when only metadata is needed.
4. Explain why prefixes do not automatically protect tenant data.
5. Design an index/database if searching by status or business metadata is needed.

### Task D — Delete

1. Check delete permissions and document status.
2. Delete the object with generation match.
3. Handle cases where generation has changed.
4. Distinguish deleting the live object from soft delete/version retention.
5. Log audit events and handle database consistency when GCS deletion fails.

### Task E — Testing

- Unit test upload, download, list, and delete via a fake adapter.
- Integration test on a dedicated GCP bucket.
- Test doesNotExist and generation mismatch.
- Test list pagination with many objects.
- Test large file streaming and memory bounds.
- Test principals missing each individual permission.
- Verify lifecycle/retention behavior in an appropriate test environment.

**Pass criteria:** The application can upload/download/list/delete objects via the Java client; handles streaming and pagination properly; does not overwrite or delete the wrong generation; defines clear per-operation IAM permissions; and includes integration tests verifying real Cloud Storage semantics.

## 18. Comparison with AWS S3 and Azure Blob Storage

| Operation | Google Cloud Storage | Amazon S3 | Azure Blob Storage |
| --- | --- | --- | --- |
| Upload | Storage.create, Storage.writer | S3Client.putObject, multipart upload | BlobClient.upload, block blob upload |
| Download | Storage.reader, Blob.downloadTo | getObject, response stream | downloadToFile, openInputStream |
| List | Storage.list with prefix/page | listObjectsV2 with prefix/continuation token | listBlobs with prefix/paging |
| Delete | Storage.delete with generation precondition | deleteObject with version ID/conditional semantics | delete, snapshot/version options |
| Identity | ADC/service account/workload identity | IAM role/credential provider | Managed Identity/Entra ID |
| Versioning | Generation and metageneration | Version ID/ETag | Version ID/ETag/lease |

Even though all three are object storage services, pagination tokens, version identifiers, preconditions, soft delete, and deletion semantics differ. A multi-cloud adapter should standardize required business behaviors, while each provider adapter preserves the specific API and guarantees of its service.

## 19. Key Takeaways

- Storage.create suits small content; Storage.writer and WriteChannel suit streaming/large file uploads.
- Storage.get reads metadata; Blob.downloadTo or ReadChannel downloads bytes.
- Storage.list returns Page<Blob>; use prefixes and pagination, and do not list the entire bucket on user requests.
- Storage.delete can use a generation precondition to avoid deleting a newer version created by another worker.
- IAM must match operations: create, get, list, and delete; prefixes are not security boundaries.
- Versioning, soft delete, retention, and holds affect delete outcomes and recoverability.
- In Spring Boot, inject a single Storage bean and encapsulate logic in an adapter; do not create a client per request.
- Test both adapter logic and real IAM/semantics on a dedicated GCP test project.

### References

- [Google Cloud Storage Java client — Storage interface](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
- [Google Cloud Storage Java client — Blob class](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Blob)
- [Google Cloud Storage Java client — BlobTargetOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobTargetOption)
- [Google Cloud Storage Java client — BlobWriteOption](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.BlobWriteOption)
- [Google Cloud Storage — Upload objects](https://cloud.google.com/storage/docs/uploading-objects)
- [Google Cloud Storage — Download objects](https://cloud.google.com/storage/docs/downloading-objects)
- [Google Cloud Storage — List objects](https://cloud.google.com/storage/docs/listing-objects)
- [Google Cloud Storage — Delete objects](https://cloud.google.com/storage/docs/deleting-objects)
- [Application Default Credentials](https://cloud.google.com/docs/authentication/application-default-credentials)
