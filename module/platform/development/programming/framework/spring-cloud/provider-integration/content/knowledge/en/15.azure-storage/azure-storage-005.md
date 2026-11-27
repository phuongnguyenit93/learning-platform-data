# ETags, Conditional Writes, and Optimistic Concurrency Control with Azure Blob Storage

## 1. Context and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we learn to integrate Spring Boot with managed services from **AWS, Azure, and Google Cloud**, covering identity and authorization, storage access, messaging, secret protection, integration testing, and cross-provider comparisons. This lesson belongs to the **Azure Storage** chapter and focuses on a common issue when multiple requests read and modify data concurrently: **preventing lost updates**.

Suppose a contract management application stores document contents and metadata in **Azure Blob Storage**:

1. Employee A opens version 1 of a document.
2. Employee B also opens that document.
3. A updates and saves successfully.
4. B saves edits based on the old content, inadvertently **overwriting A's changes**.

If the server simply calls upload with `overwrite=true`, the last writer wins even though that user never saw the prior update. **ETags and request conditions** allow Azure Storage to check the blob's version **at the exact time of write**, rejecting writes based on stale state.

After this lesson, you will be able to:

- Explain **ETags**, **optimistic concurrency**, **conditional requests**, and why calling `exists()` before writing is unsafe.
- Distinguish `If-Match`, `If-None-Match`, time-based conditions, and **leases**.
- Write a Spring Boot API using `BlobRequestConditions` for conditional updates and return **HTTP 412 Precondition Failed** with proper semantics.
- Use creation-only conditions to prevent overwriting existing blobs; choose ways to protect metadata, deletes, and large-file operations.
- Build conflict tests, enforce data-plane permissions, and evaluate boundaries when pairing Azure Blob with databases/queues.

## 2. Why Checking Before Writing Can Still Lose Data

Look at this error-prone code:

~~~java
BlobClient blob = container.getBlobClient("contracts/contract-42.json");

if (blob.exists()) {
    // Another request could update the blob right after this line.
    blob.upload(input, contentLength, true);
}
~~~

The `exists()` call and the `upload()` call are **two independent requests**. Between those two moments, another process can easily alter the content. This is a **time-of-check to time-of-use (TOCTOU)** race condition. Even calling `getProperties()` before `upload()` still suffers from this bug if the upload carries no version condition.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant S as Azure Blob Storage
    A->>S: GET blob (ETag v1)
    B->>S: GET blob (ETag v1)
    A->>S: PUT content A, no condition
    S-->>A: Write succeeded, ETag v2
    B->>S: PUT content B, no condition
    S-->>B: Write succeeded, ETag v3
    Note over S: Content A was overwritten
~~~

The solution is to send the **ETag the client read** inside **the update request itself** via the `If-Match` header. Azure Blob Storage evaluates the condition as part of the operation, eliminating the gap between "check" and "write".

## 3. What Is an Azure Blob Storage ETag?

An **ETag (entity tag)** is an identifier representing a resource's state to support HTTP conditions and concurrency control. Azure Blob Storage returns an ETag when querying properties or performing many read/write operations; the ETag generally changes whenever the blob is modified, including some property and metadata updates.

Illustrative example:

~~~http
HTTP/1.1 200 OK
ETag: "0x8E123456789ABCD"
Last-Modified: Tue, 24 Nov 2026 08:30:00 GMT
Content-Type: application/json
~~~

This is a **fictional** ETag to illustrate structure, not a real resource's ETag. **Never fabricate or infer an ETag**—always use the exact value returned by the Storage SDK response.

| Concept | Meaning | Used For |
|---|---|---|
| **ETag** | Identifies the current version state of a resource | Read/write conditions, optimistic concurrency, cache validation |
| **Last-Modified** | Timestamp when the resource was last modified | Observing changes, certain time-based conditions |
| **Version ID** | Identifies a version when Blob versioning is enabled | Accessing/restoring historical saved versions |
| **Content hash** | Digest computed from content bytes (e.g., app-computed SHA-256) | Integrity verification, content comparison |
| **Lease ID** | Token for an active lease held on a blob | Coordinating access via timed exclusive locks |

Key points to remember:

- **ETag is not a checksum.** The two goals "file is uncorrupted" and "file has not been modified by someone else" require different mechanisms.
- Do not predict the next ETag, increment ETags like integers, or use ETags as business IDs.
- In REST, ETags may include double quotes. With the SDK, preserve the exact ETag string returned by Azure when setting `If-Match`—avoid stripping quotes or adding wrong prefixes.
- ETags only protect **conditional resources and operations**. If another client writes unconditionally, it can still modify the blob.
- Azure Blob Storage provides **strong consistency** at the service-acknowledged operation level; however, ETags **do not create cross-resource transactions** spanning multiple blobs, databases, or queues.

## 4. Common HTTP Conditions

Azure Storage supports request conditions on applicable operations; not every header applies to every API or blob type. For common Blob operations:

| Condition | Meaning | Use Case |
|---|---|---|
| `If-Match: "<etag>"` | Execute only if current ETag **matches** the client's ETag | Preventing overwrites of another user's changes |
| `If-None-Match: *` | Execute only if the resource **does not yet exist** per operation condition semantics | Creating a new blob with a fixed name without overwriting |
| `If-None-Match: "<etag>"` | Execute when current ETag **does not match**; typically conditional read/cache | Avoiding re-sending unchanged content |
| `If-Unmodified-Since` | Execute only if resource was not modified after the specified timestamp | Time-based condition; less precise than ETag |
| `If-Modified-Since` | Execute only if resource was modified after the specified timestamp | Conditional queries/reads |
| **Lease ID** | Requires supplying the lease ID when a blob has an active lease requiring it | Pessimistic concurrency on a locked blob |

When `If-Match` fails, Blob APIs typically return **HTTP 412 Precondition Failed**. With `If-None-Match: *` on create operations, how the SDK maps the operation can yield **412 or 409** depending on the API/scenario (e.g., blob already exists). At the application layer, inspect `BlobStorageException` and the Azure Storage error code to distinguish **condition conflicts** from authorization, network, or blob-not-found errors.

Do not rely on `Last-Modified` when exact version accuracy matters: timestamps do not directly represent the version token a client read and have resolution/ordering limits.

## 5. Optimistic Concurrency Mechanism with If-Match

The **optimistic concurrency** model assumes contention is relatively rare, allowing multiple parties to read concurrently and **logically locking only at write time** via an ETag condition.

~~~mermaid
sequenceDiagram
    participant A as User A
    participant B as User B
    participant API as Spring Boot API
    participant ST as Azure Blob Storage
    A->>API: GET /documents/42
    API->>ST: Read blob and ETag
    ST-->>A: Content + ETag v1 (via API)
    B->>API: GET /documents/42
    API->>ST: Read blob and ETag
    ST-->>B: Content + ETag v1 (via API)
    A->>API: PUT + If-Match: v1
    API->>ST: Upload with If-Match v1
    ST-->>API: Success, ETag v2
    API-->>A: 200 OK / ETag v2
    B->>API: PUT + If-Match: v1
    API->>ST: Upload with If-Match v1
    ST-->>API: 412 Precondition Failed
    API-->>B: 412; must reload or merge
~~~

**Backend workflow:**

1. Client calls the read API and receives **content + ETag**.
2. Client edits the content based on the read version.
3. Client sends the update along with the **old ETag** in `If-Match`.
4. Backend checks authentication/authorization and passes the ETag into `BlobRequestConditions` in **the same write request**.
5. Azure Storage checks the current ETag. Match → write; mismatch → reject.
6. On 412, backend returns a precondition conflict; client reloads the latest version and decides to **intentionally overwrite, merge, or cancel**.

**A 412 error is a normal business outcome under contention**, not necessarily a system failure. Never automatically retry by fetching the fresh ETag and re-sending the stale payload: doing so defeats optimistic concurrency and can wipe out someone else's update.

## 6. Preparing Spring Boot and the Azure Blob Client

### 6.1. Dependencies

Spring Cloud Azure helps Spring Boot configure clients with appropriate Azure Identity. Maven example (pick a BOM compatible with your Spring Boot version):

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-azure.version` must be defined in the project's POM/build. Do not choose versions arbitrarily since Spring Boot and Java compatibility depend on the BOM.

### 6.2. Application Configuration

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  documents:
    container: ${DOCUMENTS_CONTAINER:documents}
~~~

The `documents` container must be pre-created in **private** mode. On Azure, prefer **managed identity** and the `Storage Blob Data Contributor` data-plane role if the application needs to update blobs; local machines can use developer identity via Azure CLI per Azure Identity configuration. Also verify storage firewalls, private endpoints, and DNS.

Never hardcode account keys or SAS tokens in source code; **an ETag is not a credential** and grants no read/write permissions. Having a valid ETag without Blob permissions will still be rejected.

### 6.3. Shared Client

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DocumentBlobContainer {
    private final BlobContainerClient client;

    public DocumentBlobContainer(
            BlobServiceClient blobServiceClient,
            @Value("${app.documents.container}") String containerName) {
        this.client = blobServiceClient
                .getBlobContainerClient(containerName);
    }

    public BlobContainerClient client() {
        return client;
    }
}
~~~

`getBlobContainerClient` only creates an SDK handle pointing to the container; it does not create the container on Azure. SDK clients are reusable across requests and already carry configured HTTP pipelines/credentials, so do not instantiate a new client on every call.

## 7. Conditional Blob Updates with Azure SDK for Java

### 7.1. Reading the ETag

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = container.getBlobClient("contracts/contract-42.json");
BlobProperties properties = blob.getProperties();

String currentETag = properties.getETag();
System.out.println("Current ETag: " + currentETag);
~~~

`getProperties()` retrieves the ETag and system metadata, but does not lock the content. When a client needs to read **content and ETag belonging to the exact same state**, design the read operation accordingly: use the ETag returned from the download response or pass blob conditions/version when downloading after reading properties. Merely reading an ETag via HEAD and then issuing an unconditional download allows the blob to change between requests, mismatching content and ETag.

### 7.2. Uploading with If-Match

The sample below uses `BlobParallelUploadOptions` for uploading and `BlobRequestConditions` so Azure validates the ETag. Small payloads use `BinaryData.fromString` to keep the focus on concurrency; large documents should use streaming/transfer options while keeping the same condition principles.

~~~java
import com.azure.core.util.BinaryData;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobContentInfo;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobParallelUploadOptions;
import java.time.Duration;

public static String replaceIfUnchanged(
        BlobClient blob, String json, String expectedETag) {
    if (expectedETag == null || expectedETag.isBlank()
            || "*".equals(expectedETag.trim())) {
        throw new IllegalArgumentException("A specific ETag from the read version is required");
    }

    BlobRequestConditions condition = new BlobRequestConditions()
            .setIfMatch(expectedETag);

    BlobParallelUploadOptions options =
            new BlobParallelUploadOptions(BinaryData.fromString(json))
                    .setRequestConditions(condition);

    BlobContentInfo result = blob.uploadWithResponse(
            options, Duration.ofSeconds(60), Context.NONE).getValue();
    return result.getETag();
}
~~~

The `setIfMatch(expectedETag)` condition is sent **with the write request**; Azure decides whether to permit the upload based on the ETag present at execution time. This is critically different from:

~~~java
// WRONG for atomicity: HEAD and upload are two separate requests.
if (blob.getProperties().getETag().equals(expectedETag)) {
    blob.upload(new java.io.ByteArrayInputStream(bytes), bytes.length, true);
}
~~~

**On length/streaming:** the `BinaryData.fromString` example fits only small payloads. Large files require `InputStream`/parallel upload APIs that support conditions or applying conditions on block list commits. If staging blocks manually with `stageBlock`, never check the ETag only at job start and then call `commitBlockList` **unconditionally**: another worker could modify the blob while blocks are being uploaded.

### 7.3. Detecting Conflicts

~~~java
import com.azure.storage.blob.models.BlobStorageException;

try {
    String newETag = replaceIfUnchanged(blob, newJson, oldETag);
    System.out.println("Saved successfully, new ETag: " + newETag);
} catch (BlobStorageException ex) {
    if (ex.getStatusCode() == 412) {
        // Do not overwrite with stale payload using overwrite=true.
        System.out.println("Document changed; reload required");
    } else {
        throw ex;
    }
}
~~~

Distinguish `412` (precondition failed) from `403` (permissions), `404` (blob missing), and transient errors like `503`. For specific operations, also inspect the storage error code when the HTTP status alone is insufficient for diagnosis.

## 8. Designing a Spring Boot REST API with If-Match

To let browser/mobile clients participate in optimistic concurrency, expose the ETag on read HTTP responses and accept the ETag back on update requests.

### 8.1. API Conventions

~~~http
GET /api/documents/42

HTTP/1.1 200 OK
ETag: "0x8E123456789ABCD"
Content-Type: application/json

{"title":"Contract A","status":"DRAFT"}
~~~

~~~http
PUT /api/documents/42
If-Match: "0x8E123456789ABCD"
Content-Type: application/json

{"title":"Contract A revised","status":"DRAFT"}
~~~

On successful save, the API can return `204 No Content` with the **new ETag**. When the client sends a stale ETag, return `412 Precondition Failed`. If the client omits `If-Match` when the API mandates version checks, return `428 Precondition Required`. Distinguish:

- **409 Conflict**: business-rule conflict (e.g., contract status transition disallowed).
- **412 Precondition Failed**: HTTP `If-Match`/`If-None-Match` condition failed.
- **428 Precondition Required**: the API requires a precondition that the client omitted.

### 8.2. Condensed Controller

Example using Spring Boot 3 / Java 17+. `DocumentAuthorization` is an **assumed** business service: it maps `documentId` to a blob name after authenticating the user and checking tenant/permissions. Never accept raw client-supplied blob names directly.

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobStorageException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/documents")
public class DocumentVersionController {
    private final BlobContainerClient container;
    private final DocumentAuthorization authorization;

    public DocumentVersionController(
            DocumentBlobContainer documentBlobContainer,
            DocumentAuthorization authorization) {
        this.container = documentBlobContainer.client();
        this.authorization = authorization;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> get(@PathVariable String id) {
        String name = authorization.requireReadAccess(id);
        BlobClient blob = container.getBlobClient(name);

        // Example for small JSON: read and verify ETag before/after.
        // If the resource changes during the read, retry up to three times.
        String content = null;
        String etag = null;
        for (int attempt = 0; attempt < 3; attempt++) {
            String before = blob.getProperties().getETag();
            String candidate = blob.downloadContent().toString();
            String after = blob.getProperties().getETag();
            if (before.equals(after)) {
                content = candidate;
                etag = after;
                break;
            }
        }
        if (etag == null) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "Document is changing; please reload");
        }

        return ResponseEntity.ok()
                .header(HttpHeaders.ETAG, etag)
                .contentType(MediaType.APPLICATION_JSON)
                .body(content);
    }

    @PutMapping(value = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> put(
            @PathVariable String id,
            @RequestHeader(value = HttpHeaders.IF_MATCH, required = false)
                    String expectedETag,
            @RequestBody String json) {
        if (expectedETag == null || expectedETag.isBlank()
                || "*".equals(expectedETag.trim())) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_REQUIRED,
                    "If-Match with a specific ETag is required");
        }

        String name = authorization.requireWriteAccess(id);
        BlobClient blob = container.getBlobClient(name);
        try {
            String newETag = replaceIfUnchanged(blob, json, expectedETag);
            return ResponseEntity.noContent()
                    .header(HttpHeaders.ETAG, newETag)
                    .build();
        } catch (BlobStorageException ex) {
            if (ex.getStatusCode() == 412) {
                throw new ResponseStatusException(
                        HttpStatus.PRECONDITION_FAILED,
                        "Document was updated by another actor");
            }
            throw ex;
        }
    }
}
~~~

`replaceIfUnchanged` is the method from section 7.2 (in a real project place it inside an injected `@Service`), while `DocumentAuthorization` and business data must be implemented separately. **The GET above illustrates comparing ETags before and after reading a small JSON document**: if the blob changes mid-read, it retries a bounded number of times and then returns 409. This makes multiple Storage calls and `downloadContent()` loads the body into memory; for large payloads or high-contention systems, use download APIs with **request conditions** or read by **version ID** to bind content and ETag to a single version efficiently.

Production APIs also need JSON/schema validation, request size bounds, filtering editable fields, Content-Type checks, audit logging, and hiding sensitive SDK error details. ETags enforce concurrency, **not document ownership checks**.

### 8.3. UX When Receiving 412

When a conflict occurs, the frontend should:

1. Preserve the user's unsaved edits.
2. Inform the user that the document was updated by someone else.
3. Fetch the latest version and new ETag.
4. Let the user compare, merge, or choose to overwrite **after explicit confirmation**.
5. Send a new request with the ETag matching the newly viewed version.

Never turn 412 into a blind retry. For operations that can be merged automatically (such as editing independent fields), merge logic requires explicit rules and tests; Azure only guards a single resource and does not understand JSON business semantics.

## 9. Creating Without Overwriting: If-None-Match

Multiple requests may concurrently try to create a blob with the same name, e.g., `exports/monthly-2026-11.csv`. The wrong pattern is calling `exists()` and then uploading. The right pattern is sending a **create-only condition** with the request:

~~~java
import com.azure.core.util.BinaryData;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobParallelUploadOptions;

BlobRequestConditions createOnly = new BlobRequestConditions()
        .setIfNoneMatch("*");

BlobParallelUploadOptions options = new BlobParallelUploadOptions(
        BinaryData.fromString("month,total\n2026-11,1520\n"))
        .setRequestConditions(createOnly);

blob.uploadWithResponse(options, null, Context.NONE);
~~~

Meaning: the blob is created only when the **does not exist** condition holds. If two workers race to create the same name, the server lets at most one creation succeed at the point of contention; the other must handle the precondition/already-exists error per the specific API.

With the high-level `upload(..., overwrite=false)` SDK method, apps also get non-overwriting creation for standard cases. `If-None-Match: *` is useful for expressing explicit **concurrency intent** alongside request options. Multi-block upload APIs involve staging followed by commit; ensure the constraint is enforced at the **final commit step**, not only during preparation.

## 10. Conditional Metadata Updates, Deletes, and Downloads

### 10.1. Metadata and HTTP Properties

Calling `setMetadata` or modifying blob HTTP headers can change the ETag. Thus, if user A is editing content while worker B attaches metadata, the ETag can change even though content bytes did not.

The design must distinguish:

- **Blob data**: PDF, JSON, image, export file.
- **Blob metadata/HTTP properties**: content type, cache control, custom metadata.
- **Business metadata in the database**: owner, approval status, permissions, and document relationships.

For concurrent metadata updates, use SDK overloads supporting `BlobRequestConditions.setIfMatch(etag)`. `setMetadata` does not automatically append a single key: passing a new map can **replace all existing custom metadata**. Read/merge with conditions when preserving existing keys is required.

### 10.2. Conditional Blob Deletion

A delete API must account for a client reading v1 while someone else updates to v2. Deleting **unconditionally** could remove a version the deleting client never saw. Principle:

~~~java
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.models.DeleteSnapshotsOptionType;
import com.azure.core.util.Context;

BlobRequestConditions onlyIfUnchanged =
        new BlobRequestConditions().setIfMatch(expectedETag);

// With SDKs supporting this overload, the condition is sent on the DELETE request.
blob.deleteWithResponse(
        DeleteSnapshotsOptionType.INCLUDE,
        onlyIfUnchanged,
        null,
        Context.NONE);
~~~

`DeleteSnapshotsOptionType.INCLUDE` applies when snapshots exist; **Blob versioning, soft delete, immutability policies, or legal holds** can alter delete lifecycle behavior from "immediate permanent deletion". Before deleting, verify authorization, retention policies, and business state.

### 10.3. Conditional Reads and Caching

`If-None-Match` is also used when a client checks whether a cached copy is still fresh. A read API can return **304 Not Modified** if unchanged, or return fresh content with the new ETag if changed. This is **cache validation**, distinct from lost-update prevention on writes.

Large file reads should use **streaming** and can use request conditions or version IDs to keep data consistent. If HTTP Range is needed for download resume, properly support `Range`/`If-Range`/`206 Partial Content` and ensure byte ranges come from the same blob version; loading the whole file into RAM to slice it is unsuitable for large files.

## 11. When to Use a Lease Instead of an ETag

Optimistic concurrency fits when write collisions are infrequent and users can resolve conflicts. When a task needs exclusive write ownership for an extended period (such as a process updating multiple parts of a blob), consider a **Blob lease** for **pessimistic concurrency**.

| Criterion | ETag / If-Match | Blob Lease |
|---|---|---|
| Coordination style | Allows concurrent reads/drafts; checks version at write time | Acquires a lease on the blob; protected writes/deletes require the lease ID |
| Best suited for | Document, JSON, metadata edits; rare conflicts | A single worker needing exclusive write access to one blob during processing |
| Cost | Minimal coordination state; handles 412 on contention | Must acquire/renew/release leases and handle expiry/crashes |
| Limitations | Does not lock or block unconditional writes from other clients | Does not replace authorization, nor lock databases or other blobs |

Conceptual Azure SDK example:

~~~java
import com.azure.storage.blob.specialized.BlobLeaseClient;
import com.azure.storage.blob.specialized.BlobLeaseClientBuilder;

BlobLeaseClient lease = new BlobLeaseClientBuilder()
        .blobClient(blob)
        .buildClient();

String leaseId = lease.acquireLease(30); // 30 seconds
try {
    // Every write operation must include request conditions with the matching leaseId.
    // For long processing, renew the lease before it expires.
} finally {
    lease.releaseLease();
}
~~~

**Warning:** a lease may expire or be broken before entering `finally`, so `releaseLease()` itself can throw an exception. Production code must handle this and use `try/finally` with appropriate logging. Leases do not block all **read** operations on a blob; their primary purpose is coordinating operations that require a lease ID. A leased blob name does not automatically act as a system-wide distributed lock.

Do not use a lease merely to stop two employees from editing JSON simultaneously when the system already handles 412 in the UI. Conversely, if you need to lock **multiple blobs plus a database**, neither ETag nor a single lease provides a multi-resource transaction.

## 12. Versioning, Snapshots, and Multi-Service Concurrency Limits

### 12.1. ETag vs. Blob Versioning

When **Blob versioning** is enabled, a write can create a new version with a `versionId`, enabling retrieval or restoration of older contents. ETag remains the token checking whether the target resource changed since the client read it.

- **ETag + If-Match**: prevents writing stale edits onto the current blob.
- **Versioning/snapshots**: preserves or pins historical content versions when configured.
- **Soft delete**: enables recovery within retention periods per account policy.

Enabling versioning **does not replace concurrency checks**: an unconditional overwrite still replaces current content, even though the old version is retained. Also avoid mechanically substituting version ID for ETag, as condition semantics and access patterns depend on the SDK/REST API.

### 12.2. One ETag Guards Only One Resource

Suppose "update contract" involves:

1. Writing the contract JSON to Blob.
2. Updating the status record in the database.
3. Sending an Azure Queue message for a PDF-generation worker.

`If-Match` makes only **step 1** atomically conditional on the blob. There is no shared transaction across Blob Storage, a relational database, and Storage Queue. If the Blob write succeeds but DB or Queue fails, the system can end up out of sync.

The architectural solution uses a **business state** (`PENDING`/`READY`/`FAILED`), a stable request/job ID, idempotent retries, an outbox, or a reconciliation job. When retrying, distinguish:

- Network error where write outcome is unknown: re-read state or ETag to verify.
- Genuine 412 because another client updated: **never** strip the write condition.
- Blob write succeeded but Queue enqueue failed: retry enqueuing by job ID instead of blindly re-writing the Blob.

### 12.3. Practical Limitations to Consider

- Do not update a partial JSON field using "merge field" semantics solely with ETag; ETag guards **the entire resource**, while merging is business logic.
- If many writers contend on one blob, 412 rates can climb; consider sharding data into separate blobs, event-driven design, or application-level serialization.
- A blob's ETag can change when metadata/properties change, increasing **false conflicts from a business perspective** even when content bytes didn't change. This is resource-level consistency protection.
- For large multi-block uploads, attach the condition to the **final commit** operation so you don't overwrite a version modified mid-upload; pick the right SDK overload and test the race condition directly.
- With immutable storage or legal hold enabled, write permissions and conditions cannot override immutability/retention policies.

## 13. Integration Testing and Diagnostics

### 13.1. Basic Conflict Test

**Azurite** works well for testing routine Blob APIs locally, but cannot replace real Azure for RBAC/managed identity, private endpoints, scale, or every Blob service capability. The test below uses two stale ETags to verify a conflicting update is rejected.

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobStorageException;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

// blob points to a unique name in an Azurite/Azure test container.
byte[] original = "version-1".getBytes(StandardCharsets.UTF_8);
blob.upload(new ByteArrayInputStream(original), original.length, true);

String etagA = blob.getProperties().getETag();
String etagB = blob.getProperties().getETag();

String afterA = replaceIfUnchanged(blob, "version-2-by-A", etagA);
if (afterA.equals(etagA)) {
    throw new AssertionError("Expected ETag to change after write");
}

boolean rejected = false;
try {
    replaceIfUnchanged(blob, "version-2-by-B", etagB);
} catch (BlobStorageException ex) {
    if (ex.getStatusCode() == 412) {
        rejected = true;
    } else {
        throw ex;
    }
}
if (!rejected) {
    throw new AssertionError("Write with stale ETag must be rejected");
}
~~~

This illustrative snippet sits inside a test class providing `BlobClient blob` and the `replaceIfUnchanged` helper from section 7.2. In real JUnit tests, use an assertion framework, generate unique blob names per test, clean up in `finally`, and also verify **the final content remains `version-2-by-A`**. Never run overwrite/delete tests against a production container.

### 13.2. Real Concurrency Testing

A sequential test only checks stale-ETag rejection. To test a true race, have two tasks read **the same ETag**, synchronize them to start updating almost simultaneously, and verify:

- Only **one** conditional write succeeds for a given base ETag.
- The other receives a condition error and does not overwrite the winning update.
- Final content and ETag match the accepted write.
- No automatic retry strips `If-Match`.

Tune iteration count and concurrency to the test environment to avoid network-induced flakiness; for load or latency testing, use an Azure staging account with monitoring.

### 13.3. Error Matrix to Distinguish

| Symptom | Possible Cause | Remediation |
|---|---|---|
| **412 Precondition Failed** | ETag changed, read/write condition failed | Reload version, merge, or prompt user |
| **428 from application API** | Missing `If-Match` when endpoint requires it | Client must send the ETag from its read |
| **409 Conflict** | Blob already exists, active lease, or API-specific conflict | Inspect Azure error code, lease/overwrite settings |
| **404 Not Found** | Blob deleted/renamed or wrong container/account | Verify resource ID, deletion/version state |
| **403 Forbidden** | Principal lacks data-plane role, invalid/expired SAS, firewall | Verify identity/RBAC, SAS, networking |
| **Timeout/5xx** | Network/service disruption or SDK retry | Reconcile whether write succeeded before retrying |
| **Frequent 412s despite few human edits** | Background worker frequently updates metadata/properties | Revisit resource model and separate business metadata |

### 13.4. Security and Observability

Measure **412 rates**, successful request counts, latency, retries, payload sizes, concurrent edits per document, and error breakdown by operation. Log `documentId`, request/correlation IDs, and version/ETag if logging policies permit, but never log sensitive data, JWTs, account keys, or SAS URLs.

When using managed identity, authenticating app identity and assigning **Storage Blob Data Contributor** at the right scope are prerequisites for updates. The API must still check **owner/tenant/business role** before permitting blob edits or deletes. ETags do not replace authentication/authorization.

## 14. Scenario Exercises and Self-Check Questions

**Scenario A — Two users editing a contract:** Both A and B read the same ETag. A saves first, B receives 412. Design a UI showing diffs and a merge workflow, and explain why the backend must never silently re-save B's payload without the condition.

**Scenario B — Unique report export job:** Multiple workers concurrently generate `exports/2026-11.csv`. Use `If-None-Match: *` or non-overwriting upload to ensure only one actor commits the fixed-name file; handle conflicts without deleting already-created data.

**Scenario C — 5 GiB block upload:** Worker A starts staging blocks while worker B updates the blob mid-upload. Explain **why checking the ETag at job start is insufficient**, and which condition must be attached to the final block list commit.

**Scenario D — 403 error after adding If-Match:** The app reads and writes blobs locally but fails to modify them on Azure. Distinguish permission errors involving **managed identity**, data-plane roles, container scope, and firewalls from ETag-based 412 errors.

**Scenario E — Multi-cloud deployment:** Moving from Azure Blob Storage to **Amazon S3** or **Google Cloud Storage** still requires lost-update protection, though APIs differ. S3 offers HTTP conditions like `If-Match`/`If-None-Match` on certain operations; GCS uses **generation/metageneration** conditions. Do not assume ETags across all three providers share identical semantics or applicability.

### Self-Check Questions

1. **Why does calling `exists()` before uploading still have a race condition?** Because check and write are two separate requests; another party can alter data in between.
2. **Which ETag should `If-Match` carry?** The ETag of the exact version the user read and edited—not a fresh ETag re-read by the server right before writing to "bypass" conflicts.
3. **Should you immediately retry a 412 with the new ETag?** No. You must inspect the new content and resolve the business conflict.
4. **Is an ETag the blob's content hash?** No; an ETag is a resource state token, whereas a hash verifies raw bytes.
5. **What does `If-None-Match: *` solve?** Create-only semantics, preventing requests from accidentally overwriting an existing resource.
6. **Does a lease block others from reading a blob?** Normally no; leases primarily guard write/delete operations covered by the lease.
7. **Does versioning replace If-Match?** No; versioning retains history/enables recovery, while conditional writes prevent lost updates.
8. **Does an ETag keep a database and Queue consistent with Blob?** No; you must use business states, outbox/retries/reconciliation.

## 15. Conclusion and References

When multiple actors edit a blob concurrently, **read the ETag and send it back inside the write request using `If-Match`**. Azure Blob Storage validates the condition server-side, accepting valid updates and returning 412 on concurrent changes. Use **`If-None-Match: *`** to express create-only intent; consider **leases** when exclusive write ownership is required; and use **versioning/snapshots** to retain history rather than as a substitute for concurrency control.

In Spring Boot, Spring Cloud Azure handles client/credential configuration while the Azure Storage SDK provides `BlobRequestConditions` and conditional write overloads. Combine them with **managed identity, least-privilege RBAC, business authorization checks, idempotent retries, and integration tests**. This is an essential principle when running object storage on Azure and when comparing against S3/GCS, even though concrete APIs differ.

### Official References

- [Microsoft Learn — Manage concurrency in Blob Storage](https://learn.microsoft.com/azure/storage/blobs/concurrency-manage)
- [Microsoft Learn — Specify conditional headers for Blob service operations](https://learn.microsoft.com/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations)
- [Microsoft Learn — Blob versioning](https://learn.microsoft.com/azure/storage/blobs/versioning-overview)
- [Microsoft Learn — Azure Storage Blob Java client library](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java)
- [Microsoft Learn — Azure Blob Storage authorization with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use Azurite for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
