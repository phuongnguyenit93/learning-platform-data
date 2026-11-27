# Streaming Uploads, Downloads, and Large File Processing with Azure Blob Storage

## 1. Lesson Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services on AWS, Azure, and Google Cloud, emphasizing identity configuration, access permissions, secret protection, and integration testing. This lesson belongs to the **Azure Storage** chapter and focuses on a very practical problem: **working with large files via data streams** when using Azure Blob Storage.

Suppose a system needs to accept a 3 GiB video, store it in Azure Blob Storage, and serve the video to authorized users. A wrong approach is calling `file.getBytes()` and holding the entire video in a `byte[]` before uploading. If multiple users upload concurrently, the heap can be exhausted. Instead, we must read and write data incrementally, controlling buffers, processing time, connection counts, and recovery after failures.

After this lesson, you will be able to:

- Distinguish between **streaming**, **full-file buffering**, block-based uploads, and **resumable uploads**.
- Configure the Spring Cloud Azure Blob client with the appropriate identity.
- Upload from an `InputStream` or a file on disk using the Azure Storage SDK; understand the requirement when the SDK asks for an input size.
- Download blobs to an `OutputStream`/HTTP response without loading the entire content into the heap.
- Use **stage block → commit block list** to control memory and orchestrate chunked uploads.
- Design timeouts, retries, idempotency, authorization, integrity checks, and tests for large files or interrupted connections.

## 2. Why Process via Streams?

### 2.1. Three Approaches

| Approach | Data Flow | Application Memory | When Appropriate |
|---|---|---|---|
| Read entire file into `byte[]` | File → RAM → Blob | Proportional to file size; prone to OOM | Only small data with strict size limits |
| Upload/download via `InputStream` / `OutputStream` | File/HTTP stream → Azure SDK → Blob | Buffered in app/SDK, no need to hold whole file in RAM | Most standard uploads/downloads |
| Controlled block upload | Read a chunk → `stageBlock` → repeat → `commitBlockList` | Depends mainly on chunk size and concurrent blocks in flight | Very large files needing block control, retries, or checkpoint resume |

Note: the word **streaming** does not mean using **0 bytes of RAM**. The HTTP client, SSL/TLS, Azure SDK, and framework still maintain buffers. The goal is **to prevent RAM usage from growing linearly with the total file size**. Increasing `maxConcurrency` may also increase the number of active buffers and connections.

### 2.2. Streams, MultipartFile, and Direct Uploads

In Spring MVC, an endpoint accepting `MultipartFile` typically goes through the servlet container's multipart parsing step. The data may be spooled temporarily to **disk** or **RAM**, depending on configuration and file size. Afterward, `MultipartFile.getInputStream()` returns a stream reading from the received data.

Therefore:

- Using `getInputStream()` avoids creating **another full copy of the file** as a `byte[]` in business code.
- It **does not guarantee** piping bytes straight from the browser's network socket to Azure without a temporary file.
- For multi-GiB uploads or high concurrency, check **temp disk space**, multipart limits, request timeouts, and server capacity.
- If you want browsers to upload directly to Azure, consider a **SAS restricted to uploading a single blob** or a time-limited delegation model; the backend verifies identity and grants access, then receives a completion callback/confirmation per business rules.

### 2.3. Data Flow

~~~mermaid
flowchart LR
    C[Client] -->|Multipart upload| M[Spring MVC multipart parser]
    M -->|Read InputStream| S[Spring Boot service]
    S -->|Azure Blob SDK| B[(Azure Blob Storage)]
    D[Database] <-->|documentId, blobName, status| S
    C -->|Download request| A[Download endpoint]
    A -->|Authenticate & authorize| D
    B -->|Byte stream| A
    A -->|HTTP response stream| C
~~~

In the download flow, the backend can proxy the data; where performance requirements differ, the client can download directly from Azure via a short-lived SAS URL after the backend verifies authorization.

## 3. Key Azure Blob Concepts for Large Files

### 3.1. Account, Container, Blob, and Clients

Azure Blob Storage organizes data by **storage account → container → blob**. In the Java SDK:

- `BlobServiceClient`: accesses the Blob service of an account.
- `BlobContainerClient`: accesses a container, lists blobs, obtains blob clients.
- `BlobClient`: operates on a single blob; upload, download, properties, delete.
- `BlockBlobClient`: specialized for **block blobs**, supporting staging blocks (`stageBlock`) and publishing the block list (`commitBlockList`).

A blob name such as `videos/2026/lecture-123.mp4` is just a prefixed object name in a standard flat namespace; it is not an SMB directory.

### 3.2. Block Blobs and Uncommitted Data

Large files are typically stored as **block blobs**. When uploading by blocks:

1. The application splits data into blocks with distinct IDs.
2. `stageBlock` uploads each block into an **uncommitted** state.
3. `commitBlockList` submits the **ordered list of block IDs** to create or update the visible blob.

If an upload stops before commit, readers will not yet see the new version of the blob from those blocks. For an existing blob, previously committed data continues to be served until a new commit occurs. Uncommitted blocks have a finite service-defined retention window and should not be treated as long-term checkpoint storage.

Maximum block size, block count, and blob size limits depend on the **API version** and blob type. When designing for multi-terabyte files, check the applicable Azure Storage documentation, choose a block size so the block count stays within limits, and do not assume all accounts share the same ceilings.

### 3.3. Single-Pass Upload vs. Resuming After Disconnection

`BlobClient.upload(InputStream, length, false)` is straightforward, but retrying **an internal HTTP request** is different from **resuming an upload from a previous run** after a process crash. True resumable upload requires knowing which blocks succeeded, persisting job/checkpoint state, and committing safely. Without building that mechanism, describe your upload as **streaming with SDK-level retries**, not as automatically recoverable from any crash.

## 4. Configuring Spring Boot and Spring Cloud Azure

### 4.1. Maven and Storage Account Configuration

Example using Spring MVC and the Spring Cloud Azure Blob starter:

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

Choose `spring-cloud-azure.version` according to the project's **Spring Boot/Spring Cloud Azure compatibility matrix**. Do not pick an arbitrary library version simply because it is the latest.

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
  servlet:
    multipart:
      max-file-size: 1GB
      max-request-size: 1100MB
      file-size-threshold: 0B
      location: ${UPLOAD_TEMP_DIR:/tmp}

app:
  blob:
    container: ${BLOB_CONTAINER:private-documents}
~~~

This is an **illustrative** configuration that must be tuned to your infrastructure:

- Multipart limits must align with reverse proxy, ingress, load balancer, servlet container limits, and temporary disk capacity.
- `file-size-threshold: 0B` directs large multipart payloads to disk-backed temporary storage per servlet configuration instead of keeping the whole file in RAM; `UPLOAD_TEMP_DIR` must exist, have sufficient space, and be writable. On Windows or containers, do not assume `/tmp` by default.
- In serverless or container deployments with limited ephemeral storage, carefully evaluate direct-to-Blob upload using SAS.
- `app.blob.container` is an application property; the example assumes the container is **already provisioned** and set to private.

### 4.2. Identity and Data Permissions

Prefer **managed identity** in Azure and **Microsoft Entra ID** with **Storage Blob Data Contributor** for components that need to write blobs, and **Storage Blob Data Reader** for download-only components. Developers can use their Azure CLI identity locally. Roles must be assigned to the **right principal** at the appropriate scope; management-plane permissions do not automatically grant data-plane permissions.

Never commit account keys, production connection strings, client secrets, or SAS tokens to the repository. Also check firewalls, private endpoints/DNS, and TLS; 403/timeout errors can come from permissions **or** networking.

### 4.3. Initializing Shared Clients

Spring Cloud Azure can auto-configure `BlobServiceClient` from the starter and the configuration above:

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class StorageClients {
    private final BlobContainerClient container;

    public StorageClients(
            BlobServiceClient blobServiceClient,
            @Value("${app.blob.container}") String containerName) {
        this.container =
                blobServiceClient.getBlobContainerClient(containerName);
    }

    public BlobContainerClient container() {
        return container;
    }
}
~~~

`getBlobContainerClient` **does not create the container on Azure**. Provision containers during infrastructure/migration steps; runtime code should not create/delete containers on every request. SDK clients are reusable across requests—avoid re-initializing HTTP pipelines and credentials repeatedly.

## 5. Uploading Large Files with InputStream

### 5.1. Uploading from a File on Disk

For a file already on disk, open an `InputStream` and pass the known **byte count** to the SDK:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class BlobTransferService {
    private final BlobContainerClient container;

    public BlobTransferService(StorageClients clients) {
        this.container = clients.container();
    }

    public void upload(Path source, String blobName) throws IOException {
        long length = Files.size(source);
        BlobClient blob = container.getBlobClient(blobName);

        try (InputStream input = Files.newInputStream(source)) {
            // false: do not overwrite an existing blob with the same name.
            blob.upload(input, length, false);
        }
    }

    public void download(String blobName, Path target) throws IOException {
        BlobClient blob = container.getBlobClient(blobName);
        try (var output = Files.newOutputStream(target)) {
            blob.downloadStream(output);
        }
    }
}
~~~

In this example, `length` is a `long`—do not cast it to `int` because many files exceed 2 GiB. The SDK may split requests into parts and use internal buffers; configure transfer options if you need to tune memory and throughput. **Do not rewrite this** as `Files.readAllBytes(source)` followed by upload, as that loads the entire file onto the heap.

If the input is a local file and manual stream manipulation is unnecessary, the Azure SDK also provides dedicated APIs such as `uploadFromFile(path, overwrite)` or `downloadToFile(path, overwrite)`. These APIs let the SDK manage file I/O, retries, and chunked transfers depending on SDK version/configuration.

### 5.2. Uploading from Spring MVC MultipartFile

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.IOException;
import java.io.InputStream;
import java.util.UUID;
import org.springframework.web.multipart.MultipartFile;

public String uploadMultipart(MultipartFile file) throws IOException {
    if (file == null || file.isEmpty()) {
        throw new IllegalArgumentException("Uploaded file must not be empty");
    }

    String blobName = "uploads/" + UUID.randomUUID();
    BlobClient client = container.getBlobClient(blobName);

    try (InputStream input = file.getInputStream()) {
        client.upload(input, file.getSize(), false);
    }
    return blobName;
}
~~~

This is an **illustrative method inside a service holding a `container` field** as in section 5.1. Production APIs must check authorization, size, content type, malware, and quotas **before** storing the document. The blob name is a server-generated ID; never use raw `getOriginalFilename()` as the blob name. If you need to store the original filename, save it as sanitized display data in the database.

During the multipart step, the server has usually already buffered the payload into memory/temp disk before the service method runs. Therefore, `max-file-size` and scratch disk capacity are part of the design, not just a Spring detail.

### 5.3. When Stream Length Is Unknown Upfront

Do not pass an arbitrary guessed `length` into `upload(InputStream, long, ...)`. The SDK uses this value to determine how many bytes to read; an inaccurate length can cause errors or corrupted content. For HTTP requests without a reliable Content-Length or dynamically generated streams, options include:

1. **Temp-spool** to a file, measure `Files.size`, and then upload from the stream.
2. **Read bounded chunks** and call `stageBlock`; no need to know total size before starting.
3. Design a **direct-to-Blob upload** with sessions and checkpoints so the client controls the parts.

Choose the approach based on file size limits, network speed, resume requirements, and temporary storage cost. Do not buffer the entire file into a `ByteArrayOutputStream` just to measure its length.

## 6. Block-Based Upload for Memory Control

### 6.1. Stage and Commit Workflow

With block blobs, the low-level API lets you read **one fixed chunk at a time**, send it to Azure, and retain the block ID. The example below uses 8 MiB chunks sent sequentially, with fixed-format IDs to avoid collisions:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.specialized.BlockBlobClient;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

public void uploadBlocks(
        BlobClient blobClient,
        Path source) throws IOException {

    BlockBlobClient blockBlob = blobClient.getBlockBlobClient();
    final int chunkSize = 8 * 1024 * 1024; // 8 MiB
    byte[] buffer = new byte[chunkSize];
    List<String> blockIds = new ArrayList<>();
    int index = 0;

    try (InputStream input = Files.newInputStream(source)) {
        int read;
        while ((read = input.readNBytes(buffer, 0, buffer.length)) > 0) {
            String rawId = String.format("%08d", index++);
            String blockId = Base64.getEncoder().encodeToString(
                    rawId.getBytes(StandardCharsets.UTF_8));

            try (InputStream chunk = new ByteArrayInputStream(
                    buffer, 0, read)) {
                blockBlob.stageBlock(blockId, chunk, read);
            }
            blockIds.add(blockId);
        }
    }

    // Only commit after every required block has been staged successfully.
    blockBlob.commitBlockList(blockIds);
}
~~~

**Key points to understand accurately:**

- `readNBytes(buffer, 0, chunkSize)` reads up to one chunk. The example uses Java 17+; the final read may hit EOF so `read` can be smaller than 8 MiB.
- `blockId` must be Base64-encoded and unique within a blob; IDs for the same blob must have a uniform unencoded length. The example uses an 8-digit sequence number, sufficient to illustrate a typical file.
- The payload buffer in this code is **a single 8 MiB array** (plus network/SDK buffers). `blockIds` still uses RAM proportional to the **number of blocks**, which is far smaller than holding the entire file.
- **The order in `commitBlockList` determines the assembled data order.** Committing with a missing ID or wrong order produces missing/corrupted content. Never commit while blocks are still failing.
- Committing a new list can **replace all committed content** of a blob with the same name. Ensure unique blob names or write/ETag preconditions when business rules forbid overwriting.
- For empty files, this example stages no blocks; define a dedicated branch and verify the commit API behavior if your system permits zero-byte files.

This is an **illustrative low-level example**, not a complete resumable upload engine. Prefer the SDK's high-level upload APIs for routine large-file uploads; use stage/commit when you genuinely need block orchestration, checkpoints, and progress control.

### 6.2. What Is Needed to Resume After Process Interruption?

A resumable system must persist `uploadId`/`jobId`, target blob, block size, block ID list/order, acknowledged status, expiration, and owner. On restart, it must verify that staged data still exists, re-upload missing blocks, and **only commit when the list is complete**. Never trust a client-stored block list without reconciling state against Azure.

~~~mermaid
flowchart TD
    S[Start upload session] --> R[Read a chunk]
    R --> T[Stage block with stable ID]
    T --> X{Stage succeeded?}
    X -->|No| K[Retry with backoff / record state]
    K --> T
    X -->|Yes| P[Save checkpoint]
    P --> N{More data?}
    N -->|Yes| R
    N -->|No| V[Verify complete blocks + order]
    V --> C[Commit block list]
    C --> F[Mark complete and save metadata]
~~~

When integrating with queue workers, attach a job ID to prevent the same file from being processed or committed multiple times unintentionally. Concurrent upload sessions must be bounded according to CPU, RAM, bandwidth, and storage account quotas.

### 6.3. Choosing Block Size and Concurrency

No single `chunkSize` fits every system:

- **Small** chunks: use less RAM per worker, but increase request count and overhead, risking hitting block count limits.
- **Large** chunks: often improve throughput on reliable networks, but increase RAM, per-chunk retry time, and latency.
- **High** concurrency: improves aggregate bandwidth if the network and service handle it, but increases buffers, connections, and upstream load.

As an estimate, with **N concurrent uploads**, each holding **C blocks in flight** of size **B bytes**, payload buffers alone can reach roughly `N × C × B`, **excluding** SDK, servlet, and network overhead. For example, N=8, C=4, B=8 MiB means payload buffers alone are around **256 MiB**; budget headroom and worker limits before deploying.

## 7. Streaming Downloads

### 7.1. Avoid Buffering the Whole Blob in Memory

For large files, avoid:

~~~java
// Only use for small files with enforced size limits.
byte[] wholeFile = blobClient.downloadContent().toBytes();
~~~

Instead, use an output stream:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path destination = Path.of("report-large.zip");
try (OutputStream output = Files.newOutputStream(destination)) {
    blobClient.downloadStream(output);
}
~~~

Or open an `InputStream` from the blob and transfer via stream:

~~~java
import java.io.InputStream;
import java.io.OutputStream;

try (InputStream input = blobClient.openInputStream();
     OutputStream output = Files.newOutputStream(destination)) {
    input.transferTo(output); // Java 9+
}
~~~

In both cases, the file never needs to exist as one giant `byte[]`. However, the SDK may still issue range requests and use internal buffers/retries; reading a **stream sequentially** does not mean only one HTTP request occurs on the wire.

### 7.2. Returning Files from Spring MVC over HTTP

Example streaming download endpoint. Here `DocumentRepository`, `DocumentRecord`, and `CurrentUser` are business components **assumed to exist** for authorization checks:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobProperties;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentDownloadController {
    private final BlobContainerClient container;
    private final DocumentRepository documents;
    private final CurrentUser currentUser;

    public DocumentDownloadController(
            StorageClients clients,
            DocumentRepository documents,
            CurrentUser currentUser) {
        this.container = clients.container();
        this.documents = documents;
        this.currentUser = currentUser;
    }

    @GetMapping("/{documentId}/download")
    public void download(
            @PathVariable String documentId,
            HttpServletResponse response) throws IOException {

        // Lookup must check owner/tenant permissions and return 404/403 appropriately.
        DocumentRecord doc = documents.requireReadableBy(
                documentId, currentUser.id());
        BlobClient blob = container.getBlobClient(doc.blobName());
        BlobProperties properties = blob.getProperties();

        String contentType = properties.getContentType();
        response.setContentType(contentType != null
                ? contentType : MediaType.APPLICATION_OCTET_STREAM_VALUE);
        response.setContentLengthLong(properties.getBlobSize());
        response.setHeader(
                HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=\"document.bin\"");

        blob.downloadStream(response.getOutputStream());
        response.flushBuffer();
    }
}
~~~

**Implementation notes:** the example above uses **blocking I/O** on a servlet thread; a long download holds the thread for a long time. Limit concurrent downloads, configure timeouts, and monitor busy thread counts. If using Spring MVC `StreamingResponseBody`, configure an appropriate **TaskExecutor** and still handle client disconnects. With WebFlux, consider Azure **async clients** with backpressure, avoiding sync SDK calls on the event loop.

`BlobProperties` is fetched before sending content to set Content-Length/Content-Type. However, the blob could change **between fetching properties and downloading**. For documents requiring strict consistency, use version ID/ETag and appropriate access conditions, or design version-immutable blobs.

### 7.3. Range Downloads and Resuming Downloads

Browsers or video players often use HTTP `Range` to request **a portion** of a file, e.g., `Range: bytes=1048576-2097151`. This is the foundation of download resume and video seeking. A proper Range-capable endpoint must:

- Parse/validate `Range`, including invalid ranges, suffix ranges, byte bounds, and multi-range requests.
- Return **206 Partial Content** and accurate `Content-Range`/`Content-Length` for the served slice; handle **416 Range Not Satisfiable** when appropriate.
- Ensure byte ranges belong to the **same blob version**, using ETag/If-Range or version ID per API policy.
- Call SDK APIs that read **specific ranges** (e.g., `BlobRange` and download options); do not download the whole blob and slice it in RAM.

The controller in section 7.2 demonstrates a **full 200 OK download** and **does not yet support HTTP Range**. If you need video seeking or resume, use a component/proxy with standard Range support or implement range handling properly and test thoroughly; do not just add an `Accept-Ranges: bytes` header and assume it is supported.

## 8. Error Handling, Timeouts, and Retries

### 8.1. Where Can Errors Occur?

| Stage | Typical Errors | Remediation |
|---|---|---|
| Receiving multipart | File exceeds limit, temp disk full, client aborts request | Return appropriate status code; bound size/concurrency and clean up temp files |
| Azure authentication | Invalid token, missing RBAC | Identify effective principal; fix data-plane role/credentials |
| Block upload | Timeout, network drop, 429/503 throttling | Retry with backoff on idempotent blocks; persist checkpoint if resumable |
| Commit block list | Lost response after server already committed | Read state/ETag and reconcile before blindly re-committing |
| Database write | Blob exists but record does not | Retry/reconcile orphan blobs and job state |
| Download | Blob deleted/version changed, client disconnects | Enforce version/ETag; log, clean up; do not try to write JSON error after bytes started |
| Checksum verification | Source/destination contents mismatch | Mark failed, do not publish file; retry or reconcile data |

**Once HTTP has sent part of the body, you cannot arbitrarily change the status to 500 and return a JSON error as you could before streaming began.** When a client disconnects, the server may encounter an `IOException`; log with correlation ID and cancel further reading. Avoid logging full stack traces repeatedly for every client-initiated download cancellation.

### 8.2. Idempotency and Consistency

An upload request may succeed in Azure while the client times out and retries. If every retry generates a new UUID, the result is **multiple blobs with duplicate content**. A reliable design needs:

1. Generating a stable `documentId` or `idempotencyKey` for the same request.
2. Persisting `PENDING → UPLOADING → READY` states in the database/queue as needed.
3. Recording the blob name tied to the document ID; only marking `READY` once upload is confirmed.
4. On retry, checking existing state or blob properties instead of unconditionally creating a duplicate copy.
5. Periodically cleaning up or reconciling unlinked blobs after a reasonable timeout.

Blob Storage and the database **do not have cross-service transactions**. With block uploads, staged blocks succeeding does not mean the new blob is committed. With downloads, ETag is an object change version, **not a content hash**.

### 8.3. Integrity Verification and Checksums

For documents with high integrity requirements, the backend can compute **streaming SHA-256**, store the hash in business metadata (database), and re-verify on receipt/download:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public static byte[] sha256(Path file)
        throws IOException, NoSuchAlgorithmException {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    byte[] buffer = new byte[64 * 1024];

    try (InputStream input = Files.newInputStream(file)) {
        int read;
        while ((read = input.read(buffer)) != -1) {
            digest.update(buffer, 0, read);
        }
    }
    return digest.digest();
}
~~~

Only store checksums when you know exactly **which byte payload was hashed** and how to verify it: local file before upload, response after download, or client-supplied digest. Never equate ETag with MD5/SHA-256. The Azure SDK offers transport-level integrity checks for applicable operations, though coverage depends on API/request type and configuration; application-level checksums remain valuable for end-to-end verification.

## 9. Security Design for Large Uploads/Downloads

### 9.1. Protecting Containers and Private Data

- Use **private** containers. A blob name is not a password; knowing a URL path does not grant download permission.
- The backend verifies **user, tenant, ownership, file status, and quota limits** before uploading or downloading.
- Manage credentials via Microsoft Entra ID/managed identity whenever possible. If secrets are unavoidable, store them in a secret manager like Azure Key Vault and rotate appropriately.
- Never log raw file contents, account keys, SAS tokens, or Authorization headers.
- Configure TLS and private endpoints/firewalls as appropriate; CORS only governs browser policy and **does not replace authentication/authorization**.

### 9.2. Direct-to-Blob Upload with SAS

For large files and web/mobile clients with a reliable path to Azure, you can avoid making the backend a relay bottleneck:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant B as Azure Blob Storage
    participant D as Database
    C->>A: Request upload session (file size, MIME, auth)
    A->>D: Create PENDING document / blobName
    A-->>C: Blob URL + scoped/time-limited SAS
    C->>B: Upload blocks directly
    B-->>C: Upload result
    C->>A: Report upload complete
    A->>B: Verify blob exists, size, metadata
    A->>D: Update to READY if valid
    A-->>C: Complete
~~~

When issuing a SAS:

- Scope to **the exact blob**, only the required **create/write** permissions, and a short lifetime; never grant delete/list when unnecessary.
- Where feasible, prefer **user delegation SAS** over account-key-signed SAS; verify permission and lifetime limits of the chosen mechanism.
- Never trust a client's "upload finished" claim blindly: the backend verifies the blob, size, and required content/metadata before publishing.
- Enforce total size, duration, concurrent session limits, and cleanup for abandoned uploads; consider malware scanning before transitioning to READY.

A SAS is temporary access to a resource, not end-user authentication itself. Issuing a SAS only occurs after backend authorization checks.

## 10. Integration Testing and Observability

### 10.1. Testing with Azurite

**Azurite** emulates many core Blob APIs for local testing. For tests requiring RBAC/managed identity, networking/private endpoints, performance, or real Azure limits, a dedicated Azure test storage account is still required.

Example **file-based round-trip** check, avoiding full-file `byte[]` comparisons:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.UUID;

// Only use the Azurite connection string in test environments.
String connection = System.getenv("AZURITE_STORAGE_CONNECTION_STRING");
BlobServiceClient service = new BlobServiceClientBuilder()
        .connectionString(connection)
        .buildClient();

var container = service.getBlobContainerClient("stream-test");
container.createIfNotExists();

String blobName = "roundtrip/" + UUID.randomUUID();
var blob = container.getBlobClient(blobName);
Path source = Path.of("test-data/large-sample.bin");
Path target = Files.createTempFile("blob-roundtrip-", ".bin");
try {
    blob.uploadFromFile(source.toString(), false);
    blob.downloadToFile(target.toString(), true);

    if (Files.size(source) != Files.size(target)
            || !Arrays.equals(sha256(source), sha256(target))) {
        throw new AssertionError("Downloaded content does not match");
    }
} finally {
    blob.deleteIfExists();
    Files.deleteIfExists(target);
}
~~~

`sha256` is the method from section 8.3; this snippet is an **API integration sample** and assumes `test-data/large-sample.bin` is prepared. In real test suites, use JUnit assertions, isolated Azurite/container lifecycles, bounded test data, and cleanup in `finally`. Running direct SDK tests does not fully verify Spring Cloud Azure configuration—add Spring Boot context tests when targeting auto-configuration.

### 10.2. Required Test Matrix

| Case | Expected Verification |
|---|---|
| Very small file, multi-hundred MiB / max allowed file | Exact byte upload/download without duplicating whole file in RAM |
| Empty file | API rejects or handles per consistent business rules |
| Multipart exceeds `max-file-size` | Appropriate HTTP error, no orphan blob created |
| Duplicate blob name, `overwrite=false` | Does not silently overwrite |
| Network drop during block staging | Uncommitted blocks are not exposed as a complete file |
| Client timeout after commit | Retry/reconciliation does not create duplicate documents |
| Client disconnects during download | Does not hold threads/sockets indefinitely, useful logs emitted |
| Multiple concurrent uploads/downloads | RAM, CPU, temp disk, and request latency stay within thresholds |
| Managed identity lacks permissions | Auth/authz error surfaced cleanly, no fallback to hardcoded secrets |
| File modified between properties check and download | ETag/version policy protects data consistency |
| Post-download SHA-256 differs from source | Document marked invalid, retry/alert triggered |

### 10.3. Metrics and Operations

Track **active upload/download counts**, bytes transferred, latency by file size, retries/throttling, 403/404/409/412/429/503 error rates, throughput, heap/GC, temp disk usage, thread pools, and egress traffic. Distinguish client, app, Azure SDK, network, and storage service errors using correlation IDs; avoid logging sensitive data.

For infrequently accessed data, evaluate **access tiers and lifecycle policies**; for large, frequently downloaded files, evaluate egress cost, CDN/caching, and direct access requirements. Never assume every video should be proxied through Spring Boot or that all content must move to the Archive tier.

## 11. Practice Scenarios

**Scenario A — Uploading a 2 GiB video through Spring MVC:** First verify whether the container/ingress allows large requests and has enough temp disk space. Use `MultipartFile.getInputStream()` and `getSize()` to upload, never `getBytes()`. If large uploads happen frequently, evaluate direct-to-Blob upload to reduce backend load.

**Scenario B — Flaky network requiring resume:** Design an upload session with stable block IDs, persist checkpoints, and inspect staged blocks before resuming. Only commit once all data is present, with reconciliation if the server committed while the client missed the response.

**Scenario C — Serving video for seeking to minute 30:** Full 200 OK streaming download is insufficient. Standard HTTP Range 206 is needed, fetching the corresponding range from Azure while keeping a consistent version/ETag.

**Scenario D — 10 users uploading 4 GiB files concurrently:** Use `concurrent uploads × parallel blocks × block size` to estimate payload buffer RAM, plus servlet/SDK overhead; enforce concurrency caps and measure under real load tests.

### Self-Check Questions

1. **Why is `getInputStream()` better than `getBytes()` for large files?** Because code can consume data sequentially without allocating a `byte[]` copy as large as the entire file.
2. **Does Spring MVC `MultipartFile` guarantee 100% socket-to-Azure streaming?** No. The multipart resolver may buffer/spool before the service receives the stream.
3. **What happens if blocks are uploaded without calling `commitBlockList`?** The blocks remain uncommitted and are not visible as a complete blob.
4. **Is a Blob ETag the SHA-256 of the content?** No. ETag supports conditional access/versioning; content integrity requires a hash or separate verification mechanism.
5. **Why distinguish request retries from resumable uploads?** Retries handle transient failures; resuming after a restart requires checkpoints, block state, and commit logic.
6. **Why doesn't a download controller automatically support HTTP Range?** Streaming the entire blob to `OutputStream` is a full download; Range requires header parsing, byte-range selection, and accurate 206/416 responses.

## 12. Summary

For large files, **incremental streaming** is the core principle when integrating Spring Boot with Azure Blob Storage. Use `InputStream`/`OutputStream` to avoid holding whole files in the heap; use **block blobs** and `stageBlock`/`commitBlockList` when you need chunk control or custom resumable uploads. Clearly distinguish **multipart spooling**, **SDK retries**, and **crash recovery resume**, while protecting data with managed identity/RBAC, private containers, ETag/versioning, idempotency, and realistic load testing.

In multi-cloud comparisons, object storage and multipart/block upload models share similarities with **Amazon S3** and **Google Cloud Storage**, though APIs, IAM permissions, resume protocols, and specific limits differ. Master byte-stream, memory, and state management principles before moving to another provider's library.

### References

- [Microsoft Learn — Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Microsoft Learn — Upload a blob with Java](https://learn.microsoft.com/azure/storage/blobs/storage-blob-upload-java)
- [Microsoft Learn — Download a blob with Java](https://learn.microsoft.com/azure/storage/blobs/storage-blob-download-java)
- [Microsoft Learn — Put Block (REST)](https://learn.microsoft.com/rest/api/storageservices/put-block)
- [Microsoft Learn — Put Block List (REST)](https://learn.microsoft.com/rest/api/storageservices/put-block-list)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use Azurite for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
