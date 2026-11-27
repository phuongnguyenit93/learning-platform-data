# Uploading and Downloading Data with the Blob Storage SDK

> **Chapter:** Azure SDK for Java  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Exploring the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID through virtual networks, compute, storage, and data services. Learn how to deploy, monitor, secure, and control the costs of an application architecture on Azure.

## Lesson Objectives

Upon completion, you will be able to:

1. Explain the **Azure Storage account → container → blob** model and distinguish Block Blobs, Append Blobs, and Page Blobs.
2. Configure the **Azure Blob Storage SDK for Java**, `BlobServiceClient`, `BlobContainerClient`, and `BlobClient` with Maven/Gradle.
3. Authenticate securely using **Microsoft Entra ID, DefaultAzureCredential, and managed identity** instead of embedding account keys in applications.
4. Write Java code to **upload/download files and streams**, and read properties, ETags, content types, and metadata.
5. Understand **large-file transfers**, chunking, block staging/committing, parallelism, memory usage, timeouts, and retries.
6. Prevent accidental overwrites with overwrite policies and **ETag/conditional requests**, verify data integrity, and prevent path traversal.
7. Classify HTTP 401/403/404/409/412/429/5xx errors and design proper retries and idempotency.
8. Combine RBAC, Private Endpoints, TLS, short-lived SAS tokens, soft delete/versioning, logs, and cost controls.
9. Design test cases, incident response runbooks, and production operational checklists.

## 1. Context: A Java Service Storing and Serving Files

Suppose a Java Spring Boot API receives invoice images, PDFs, and CSVs from users. Each file must be persisted for later download while strictly enforcing per-tenant access control.

~~~mermaid
flowchart LR
    U["Web/mobile client"]
    API["Java API\nAuthenticate + authorize"]
    ID["Microsoft Entra ID\nManaged identity"]
    DB["Metadata database\nOwner, tenant, object ID"]
    ST["Azure Blob Storage\nPrivate container"]
    MON["Azure Monitor\nMetrics + diagnostics"]
    U --> API
    API --> DB
    API -->|"Blob SDK"| ST
    ID -.->|"OAuth token"| API
    API -.-> MON
    ST -.-> MON
~~~

A secure workflow:

1. The app authenticates the user and enforces file size and type limits.
2. The server generates a blob name **independent of the client-supplied filename**, e.g., `tenants/t001/2026/11/<uuid>.pdf`.
3. The Java Blob SDK uploads the file to a private container using the app's credential.
4. Store object ID, blob name, owner, size, ETag, and checksum as needed in a metadata DB.
5. On download requests, **enforce business authorization** by object ID—never trust a blob path submitted by the client.
6. Stream data through the API or issue a tightly scoped, short-lived temporary access URL.

**A successful SDK upload does not mean the application is production-ready.** You still need access controls, monitoring, reliability, retention, and cost budgets—central to designing cloud architectures on Azure.

## 2. Blob Storage Model and Data Types

### 2.1. Account, Container, and Blob

~~~text
Subscription
  Resource group: rg-files-prod
    Storage account: stfilesprod001
      Container: documents (private)
        tenants/t001/invoices/2026/report.pdf
        tenants/t001/images/1234.png
      Container: exports (private)
        daily/2026-11-20/orders.csv
      Container: audit-archive (private)
        year=2026/month=11/....
~~~

- **Storage account:** defines region, SKU, replication/redundancy, network rules, encryption, and account-level policies.
- **Container:** logical grouping of blobs supporting scoped data RBAC assignments.
- **Blob:** an object holding content and properties; the key is `blobName` within the container.
- **Blob URL:** e.g., `https://stfilesprod001.blob.core.windows.net/documents/tenants/t001/report.pdf`. A URL without a token or credential does not grant read access to a private container.
- **Properties:** content length, content type, ETag, last modified, access tier, and HTTP headers.
- **Metadata:** custom key-value pairs; **never treat metadata as business authorization evidence** without DB/policy verification.

### 2.2. Three Common Blob Types

| Blob Type | Best Suited For | Write Pattern |
| --- | --- | --- |
| **Block Blob** | PDFs, images, CSVs, general-purpose large files | Upload whole or split into blocks then commit |
| **Append Blob** | Conditional append-only streams | Append blocks per service semantics |
| **Page Blob** | Random-access page storage, e.g., virtual disk use cases | Write aligned pages/ranges |

This lesson focuses on **Block Blobs**. Never choose Append Blob simply because a filename ends in `.log`; workload patterns, mutability needs, and pricing should drive the blob type choice.

### 2.3. Forward Slashes and Azure Data Lake Storage Gen2

On flat-namespace Blob Storage, `/` is just a character in the blob name creating virtual directories. When a Storage account enables **Hierarchical Namespace (HNS)** for ADLS Gen2, directories have real filesystem semantics and support POSIX-like ACLs.

The Blob SDK targets `<account>.blob.core.windows.net`; filesystem/ACL APIs for HNS typically use the **Azure Storage Data Lake SDK / DFS endpoint**. Do not assume both SDKs are 100% interchangeable without checking feature compatibility.

## 3. Preparing Java, Azure, and Dependencies

### 3.1. Lab Prerequisites

- JDK **17+**, managed via Maven or Gradle.
- An **existing**, authorized Storage account and `documents` container.
- Data-plane principal holding **Storage Blob Data Contributor** for uploads or **Storage Blob Data Reader** for read-only access, at the narrowest scope.
- Entra login configured for dev, managed identity or workload identity in production.
- Working network/TLS connectivity to the Blob endpoint.
- Defined file size limits, timeouts, retry budgets, allowed content types, and resource owners.
- Run billable or mutating operations only in authorized labs/subscriptions.

Never create or reconfigure production resources to run lesson examples.

### 3.2. Maven Dependencies

~~~xml
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
    </dependency>
</dependencies>
~~~

These dependencies require **versions** managed by a parent POM/`dependencyManagement` or the Azure SDK BOM. BOM example:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <azure.sdk.bom.version>REPLACE_WITH_APPROVED_VERSION</azure.sdk.bom.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure</groupId>
            <artifactId>azure-sdk-bom</artifactId>
            <version>${azure.sdk.bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

When pasting into a valid `pom.xml`, choose an organization-approved BOM version using a standard Maven property. Never guess a version: Azure SDK APIs and overloads evolve across versions.

### 3.3. Key Client Classes

| Java SDK Class | Purpose | Notes |
| --- | --- | --- |
| `BlobServiceClient` | Storage account-level operations | Synchronous |
| `BlobContainerClient` | Container operations and blob listing | Synchronous |
| `BlobClient` | Upload/download and properties on one blob | Synchronous |
| `BlobServiceAsyncClient` | Service-level reactive operations | Non-blocking/reactive |
| `BlobContainerAsyncClient` | Reactive container operations | Requires concurrency management |
| `BlobAsyncClient` | Async upload/download | Backpressure and lifecycle |
| `BlockBlobClient` | Manual block staging and block list commits | Use only when genuinely needed |

Spring MVC with blocking I/O can use sync clients. Spring WebFlux should use async clients or dedicated schedulers for blocking file I/O—never run blocking transfers on the main event loop.

### 3.4. Read-Only Azure CLI Preflight

~~~bash
az login
az account show --query "{name:name,id:id,tenantId:tenantId}" -o json
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-files-lab"
ACCOUNT="stfileslabunique001"
CONTAINER="documents"

az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name, location:location, sku:sku, publicNetworkAccess:publicNetworkAccess, allowSharedKeyAccess:allowSharedKeyAccess}" \
  -o json
~~~

Never run `az storage account keys list` just to verify networking or RBAC; its output exposes secrets. Azure management `Reader` does not grant Blob Data Reader when the app authenticates with Microsoft Entra tokens. `listKeys` creates an alternative Shared Key access path and must be tightly restricted.

## 4. Authenticating with Microsoft Entra ID

### 4.1. Token Flow to Blob Storage

~~~mermaid
sequenceDiagram
    participant J as Java application
    participant E as Entra ID / Managed identity
    participant B as Azure Blob Storage
    J->>E: Request OAuth token
    E-->>J: Token
    J->>B: HTTPS request + token
    B->>B: Evaluate RBAC, network and policies
    B-->>J: Result or 401/403
~~~

`DefaultAzureCredential` checks credential sources based on configuration and the Azure Identity SDK version, such as developer logins or managed identities. **Never assume your laptop's `az login` user and the production managed identity are the same principal**.

### 4.2. Client Factory with DefaultAzureCredential

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class BlobClients {
    private BlobClients() {}

    public static BlobContainerClient documents() {
        String account = System.getenv("AZURE_STORAGE_ACCOUNT");
        if (account == null || account.isBlank()) {
            throw new IllegalStateException("AZURE_STORAGE_ACCOUNT is required");
        }

        BlobServiceClient service = new BlobServiceClientBuilder()
            .endpoint("https://" + account + ".blob.core.windows.net")
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();

        return service.getBlobContainerClient("documents");
    }
}
~~~

Prerequisites: account and container exist, identity has data-plane permissions, and DNS/TLS/network policies allow access. **Never instantiate a new client per request** in production: manage clients as singletons or shared beans to reuse HTTP connections and token caches.

### 4.3. Least Privilege

- **Storage Blob Data Reader**: read blobs at the assigned scope.
- **Storage Blob Data Contributor**: read/write/delete blobs; assign at container scope or the narrowest supported scope rather than subscription-wide.
- **Storage Blob Data Owner**: elevated role capable of managing data permissions where supported; do not grant to standard upload apps.
- **Azure Contributor/Owner**: management-plane roles that do not replace business authorization.

If an upload returns 403, check **tenant/principal object ID, role assignment, scope, RBAC propagation, network rules, and exact Blob endpoint** before raising permissions. With private containers, the SDK never needs container `public access`.

### 4.4. Endpoints and Private Networking

Example endpoint:

~~~text
https://stfileslabunique001.blob.core.windows.net/
~~~

When using a **Private Endpoint**, DNS resolves to a private IP, yet the SDK must still use the Blob Storage hostname to preserve TLS hostname verification. Never replace the SDK URL with an internal IP address or disable certificate verification.


## 5. Uploading a File with BlobClient

### 5.1. Practical Java Upload Program

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobProperties;

import java.nio.file.Files;
import java.nio.file.Path;

public final class UploadFileExample {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: UploadFileExample <local-file> <safe-blob-name>"
            );
        }

        Path source = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(source) || !Files.isReadable(source)) {
            throw new IllegalArgumentException("Source not readable");
        }

        String name = args[1];
        if (name.isBlank() || name.startsWith("/")
                || name.contains("..") || name.contains("\\")) {
            throw new IllegalArgumentException("Unsafe blob name");
        }

        BlobContainerClient container = BlobClients.documents();
        BlobClient blob = container.getBlobClient(name);

        // Do not overwrite an existing object with the same name.
        blob.uploadFromFile(source.toString(), false);

        BlobProperties properties = blob.getProperties();
        System.out.println("Uploaded: " + name);
        System.out.println("Size: " + properties.getBlobSize());
        System.out.println("ETag: " + properties.getETag());
    }
}
~~~

`BlobClients` is the factory from section 4. The blob name check above is only for lab use, not a full production validator. Servers should generate names from opaque IDs and verified tenant identities rather than trusting user-supplied blob paths. `uploadFromFile(path, false)` forbids overwriting. If the name already exists, the request fails per service conditions; **never flip it to `true` inside a `catch` block**.

### 5.2. Generating Blob Names Independent of User Filenames

~~~java
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class BlobNames {
    private BlobNames() {}

    public static String newPdfName(String authorizedTenantId) {
        if (!authorizedTenantId.matches("[a-zA-Z0-9-]{1,64}")) {
            throw new IllegalArgumentException("Invalid tenant ID");
        }
        LocalDate day = LocalDate.now(ZoneOffset.UTC);
        return "tenants/" + authorizedTenantId
            + "/" + day.getYear()
            + "/" + String.format("%02d", day.getMonthValue())
            + "/" + UUID.randomUUID() + ".pdf";
    }
}
~~~

Unique names prevent collisions, yet **UUIDs do not replace authorization** and a `.pdf` suffix does not prove the payload is a valid PDF. Enforce file-size caps, malware scanning, content sniffing, data classification, and retention policies before publishing.

### 5.3. Should You Create the Container on Upload?

Do not call `createBlobContainer` or `createIfNotExists` on every HTTP request. Pre-provision containers via IaC or admin workflows: runtime uploaders should not hold broad permissions to create containers. `getBlobContainerClient("documents")` only creates a local client handle; it does not verify container existence.

## 6. Upload Headers, Metadata, and Overwrite Prevention

### 6.1. HTTP Headers

| Header/Property | Purpose | Warning |
| --- | --- | --- |
| `Content-Type` | Declares MIME type, e.g., `application/pdf` | Never trust client-supplied MIME types alone |
| `Content-Disposition` | Suggests file download/attachment | Reduces risk of rendering unsafe inline content |
| `Cache-Control` | Caching directives | Be cautious with private files and shared caches |
| `ETag` | Optimistic concurrency / conditional requests | Not a content checksum |
| User metadata | IDs, correlation, business metadata | Never use as an authorization source |
| Blob index tags | Search/filtering where supported | Separate from metadata with its own billing and permissions |

For files uploaded by untrusted users, set `Content-Disposition: attachment` where appropriate to avoid rendering untrusted HTML or scripts inline in browsers.

### 6.2. Creating Safely with If-None-Match

Example options API in supporting `azure-storage-blob` versions:

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobHttpHeaders;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobUploadFromFileOptions;

import java.time.Duration;
import java.util.Map;

public final class UploadWithOptions {
    public static void createPdf(
            BlobClient blob, String localPath, String documentId) {

        BlobHttpHeaders headers = new BlobHttpHeaders()
            .setContentType("application/pdf")
            .setContentDisposition("attachment");

        BlobUploadFromFileOptions options =
            new BlobUploadFromFileOptions(localPath)
                .setHeaders(headers)
                .setMetadata(Map.of("documentid", documentId))
                .setRequestConditions(
                    new BlobRequestConditions().setIfNoneMatch("*")
                );

        blob.uploadFromFileWithResponse(
            options, Duration.ofMinutes(10), Context.NONE
        );
    }
}
~~~

**Version note:** verify `BlobUploadFromFileOptions` and the `uploadFromFileWithResponse` overload for your exact SDK version before deploying. `If-None-Match: *` requires the blob not to exist yet; otherwise the request fails with `412 Precondition Failed` or an equivalent condition error. Never handle every `BlobStorageException` by overwriting.

### 6.3. Upload Succeeds Yet the Client Times Out

A tricky scenario:

~~~text
Client sends upload + conditional create
    → Azure commits the blob
    → Network response is lost
    → Client assumes the upload failed
~~~

How to handle it:

1. Record an operation ID/idempotency key in the metadata DB with status `PENDING`.
2. On timeout, **do not assume the blob does not exist**.
3. Query properties using the deterministic blob name and valid credentials.
4. Compare size, ETag, checksum/manifest, or verified metadata.
5. If committed accurately, mark complete; otherwise retry with the same key and bounded conditional create.
6. Never generate a brand-new blob name on each retry, creating unintended duplicates.

### 6.4. Metadata Is Not a Secret Store

Never store raw access tokens, Storage account keys, signed SAS URIs, government IDs, or other secrets in blob metadata. Metadata can be read by any principal with property-read permissions, logged in diagnostics, or copied alongside the blob.

When updating headers post-upload, note that `setHttpHeaders` replaces header properties as a set: omitting `Content-Disposition` or `Cache-Control` can wipe them out. Prefer setting headers in upload options and enforcing concurrency conditions where appropriate.

## 7. Downloading a Blob to a Local File

### 7.1. Download Example Without Overwriting Local Files

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;

import java.nio.file.Files;
import java.nio.file.Path;

public final class DownloadFileExample {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: DownloadFileExample <authorized-blob-name> <output>"
            );
        }

        // Production: server looks up blob name from metadata DB
        // after authenticating user/object owner.
        String blobName = args[0];
        Path target = Path.of(args[1]).toAbsolutePath().normalize();
        if (target.getParent() == null) {
            throw new IllegalArgumentException("Invalid destination");
        }

        Files.createDirectories(target.getParent());

        BlobContainerClient container = BlobClients.documents();
        BlobClient blob = container.getBlobClient(blobName);

        // Do not overwrite an existing local file.
        blob.downloadToFile(target.toString(), false);

        System.out.println("Downloaded " + Files.size(target) + " bytes");
    }
}
~~~

Never take raw `blobName` or `output` directly from user requests in production: an arbitrary blob name can leak another tenant's files, and an arbitrary output path causes **local path traversal**. The backend must authorize the object ID, generate a safe local filename, set filesystem permissions, and manage cache cleanup.

### 7.2. Constraining Download Paths

~~~java
import java.nio.file.Path;
import java.util.UUID;

Path root = Path.of("/app/download-cache")
    .toAbsolutePath().normalize();

String safeName = UUID.randomUUID() + ".pdf";
Path target = root.resolve(safeName).normalize();

if (!target.startsWith(root)) {
    throw new SecurityException("Outside allowed directory");
}
~~~

In real environments, also handle **symlinks, filesystem mounts, concurrent access, disk quotas, race conditions, and file cleanup**. Consider downloading into a securely created temp file and atomically renaming after verification.

### 7.3. Large Downloads and the Archive Tier

Blobs in online access tiers can be read directly when authorized. **Archive tier** blobs require rehydration to an online tier before downloading, incurring latency and retrieval charges. Never place objects in Archive if users expect downloads within a few seconds.

### 7.4. ETag vs. Data Integrity

ETags indicate server-side version/concurrency changes; **they are not SHA-256 content hashes**. Matching `Content-Length` alone does not prove identical bytes either. For critical files, maintain an independent checksum/manifest and verify after download.

## 8. Uploading and Downloading via Streams

### 8.1. Uploading an InputStream with Exact Length

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class StreamUploadExample {
    public static void upload(Path source, BlobClient blob) throws Exception {
        long size = Files.size(source);
        try (InputStream in = Files.newInputStream(source)) {
            blob.upload(in, size, false);
        }
    }
}
~~~

`size` must be the exact total byte length of the stream—never use `InputStream.available()` as a file length. With `MultipartFile`, read `getSize()` only after enforcing file-size quotas, authentication, and validation. Non-rewindable streams complicate retries and parallel uploads; the SDK may buffer depending on configuration, so measure memory and temporary disk usage.

### 8.2. Downloading into an OutputStream

~~~java
import com.azure.storage.blob.BlobClient;
import java.io.OutputStream;

public final class StreamDownloadExample {
    public static void copyTo(BlobClient blob, OutputStream target)
            throws java.io.IOException {
        blob.downloadStream(target);
        target.flush();
        // Caller owns target, e.g., Servlet container.
    }
}
~~~

In Spring MVC/Servlets, authorize before setting response headers and streaming. If an error occurs after headers and bytes start flowing, you cannot always return a JSON `500`: clients must detect truncated transfers and have retry/resume logic. Track partial downloads and cancellations rather than counting every HTTP 200 header as a completed transfer.

### 8.3. Avoid Loading Entire Large Files onto the Heap

Suppose 100 concurrent downloads each buffer a 200 MiB file completely into a byte array:

~~~text
100 × 200 MiB = 20,000 MiB (≈ 19.5 GiB)
before counting allocations, HTTP buffers, and JVM overhead
~~~

Avoid `readAll()` or full byte arrays for large files; prefer streaming/chunking or async SDK APIs with bounded concurrency and backpressure.

## 9. Reading Blob Properties and Syncing Business Metadata

### 9.1. Reading HEAD / Properties

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = BlobClients.documents()
    .getBlobClient("tenants/t001/reports/report.pdf");

BlobProperties props = blob.getProperties();
System.out.println("Size=" + props.getBlobSize());
System.out.println("ETag=" + props.getETag());
System.out.println("LastModified=" + props.getLastModified());
System.out.println("ContentType=" + props.getContentType());
~~~

`getProperties()` issues a network request that incurs transaction charges and can fail with 403, 404, or a timeout. Avoid repeating HEAD calls per chunk needlessly.

### 9.2. ETag and Version ID Differ

- **ETag:** HTTP concurrency validator; changes on updates.
- **Version ID:** identifier for a specific blob version when Blob Versioning is enabled and supported.
- **SHA-256 / checksum:** cryptographic hash verifying payload bytes against a trusted reference.
- **Business object ID:** application key used to look up metadata and verify ownership.

Never use an ETag as a content checksum or user authorization token. For auditable data, store traceable upload metadata and a checksum computed from a trusted source.

### 9.3. Blob Upload and Metadata DB Write Are Not One ACID Transaction

A resilient workflow:

1. Insert `upload_intent` into the DB with status `PENDING` and an object ID.
2. Upload to the deterministic blob name using `overwrite=false` or conditional create.
3. Verify size, checksum, and ETag per policy.
4. Transition DB status to `READY` along with the captured blob version/ETag.
5. On crashes between steps 2 and 4, a reconciliation worker inspects existing blobs and DB state.
6. Clean up orphaned or stale `PENDING` entries after a grace period with audit logs.
7. Block user downloads for documents in non-`READY` states.

**Never assume Storage upload and SQL INSERT form an automatic distributed ACID transaction.** Retries require idempotency keys and verification against business intent.


## 10. Large File Transfers: Block Uploads, Chunking, and Concurrency

### 10.1. Why Not Send Large Files as a Single Byte Array?

Suppose a service processes 10 concurrent uploads of 2 GiB each. Holding full payloads in RAM requires **20 GiB** before JVM/HTTP overhead. With Block Blobs, the SDK splits files into blocks and commits them as a single blob.

~~~mermaid
flowchart LR
    F["Large file"]
    S["SDK scheduler\nSplit into blocks"]
    A["Put Block A"]
    B["Put Block B"]
    C["Put Block C"]
    D["Commit Block List"]
    F --> S
    S --> A
    S --> B
    S --> C
    A --> D
    B --> D
    C --> D
~~~

**Prefer the high-level `uploadFromFile` method** when custom resumable protocols are unnecessary. The SDK automatically chooses single-shot upload or block chunking based on file size, options, version, and service limits. Never hard-code assumptions about a single universal threshold across all SDK versions.

### 10.2. Single Upload vs. Multipart Upload

| Operation | Description | When to Use |
| --- | --- | --- |
| Put Blob | Single request uploading full content within API size limits | Small files or SDK-chosen one-shot |
| Put Block | Stages one chunk identified by a block ID | Large files or resumable flows |
| Put Block List | Commits an ordered list of staged block IDs | Finalizes the blob content |
| `uploadFromFile` | SDK automatically schedules the transfer | Most applications |
| `stageBlock` + `commitBlockList` | App manages block IDs and chunks manually | Specialized flows needing custom checkpoints |

Uncommitted staged blocks **do not become downloadable** as a finished blob. Block count, block size, and uncommitted-block retention limits depend on REST service versions; verify limits before transferring huge files.

### 10.3. Higher Parallelism Is Not Always Better

Some SDK options let you tune:

- Block/chunk size.
- Maximum concurrent block requests.
- Single-upload threshold.
- HTTP timeout and retry strategies.
- Connection pools and SDK client lifecycles.

Base tuning on load tests. Excessive concurrency causes throttling, 503s, excessive retries, higher RAM usage, and contention with other traffic.

Hypothetical estimate:

~~~text
chunk size = 8 MiB
max concurrent block requests per upload = 4
simultaneous uploads = 6

payload buffer baseline ≈ 8 × 4 × 6 = 192 MiB
~~~

This is only a **rough baseline**; real memory also includes HTTP buffers, retry copies, JVM heap overhead, and application state. Monitor heap, GC, open sockets, throughput, and 429/503s under load.

### 10.4. Configuring Parallel Transfers per SDK Version

In supporting `azure-storage-blob` versions, options such as `ParallelTransferOptions` and `BlobParallelUploadOptions` customize uploads. Parameters worth benchmarking:

~~~text
block size: 4–8 MiB as a lab measurement baseline
max concurrency: 2–4 as a starting point
end-to-end timeout: sized to file size and bandwidth
retry budget: bounded exponential backoff
max simultaneous uploads: coordinate with per-upload concurrency
~~~

These numbers are **initial benchmark starting points**, not universal defaults or service recommendations. Exact builder names and overloads vary by SDK version; check Javadoc and benchmark before production rollout.

### 10.5. Example: Staging Two Blocks and Committing

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.specialized.BlockBlobClient;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;

public final class ManualBlockDemo {
    public static void main(String[] args) {
        BlobClient blob = BlobClients.documents()
            .getBlobClient("lab/blocks/demo.txt");
        BlockBlobClient block = blob.getBlockBlobClient();

        byte[][] chunks = {
            "Hello ".getBytes(StandardCharsets.UTF_8),
            "Azure!".getBytes(StandardCharsets.UTF_8)
        };
        List<String> ids = new ArrayList<>();

        for (int i = 0; i < chunks.length; i++) {
            // Raw block IDs must have uniform length before Base64 encoding.
            String id = Base64.getEncoder().encodeToString(
                String.format("%06d", i).getBytes(StandardCharsets.UTF_8)
            );
            block.stageBlock(
                id,
                new ByteArrayInputStream(chunks[i]),
                chunks[i].length
            );
            ids.add(id);
        }
        block.commitBlockList(ids);
        System.out.println("Committed blocks=" + ids.size());
    }
}
~~~

**Run only against a dedicated lab blob.** Committing a block list alters existing blob content. Production use requires tracking upload IDs, ordered block IDs, session ownership, concurrency preconditions, integrity checks, retries, and cleanup of uncommitted blocks. Never build a manual block scheduler if high-level SDK uploads meet your needs.

### 10.6. Resumable Transfers vs. Request Retries

**Retry:** on a transient error, the SDK resends the request per policy within one invocation.

**Resumable:** after a process crash/restart, the app knows which blocks were already staged, uploads only the missing blocks, and commits a valid manifest.

A resumable design persists:

~~~text
upload_session_id
authorized_tenant_id + object_id
blob_name
expected_file_size + checksum
block_size
ordered_block_ids
staged_block_progress
expiration / cleanup policy
~~~

Never trust a client-supplied block manifest without validation, and never assume uncommitted blocks survive indefinitely or without limits. Use `getBlockList` or your SDK version's equivalent to inspect staged blocks when reconciling.

## 11. ETags, Optimistic Concurrency, and Conditional Downloads

### 11.1. Lost Update Scenario

~~~text
10:00 Worker A reads ETag E1
10:01 Worker B reads ETag E1
10:02 Worker B updates blob -> ETag E2
10:03 Worker A overwrites based on E1
Result: Worker B's update is silently lost.
~~~

`If-Match` requires the blob to still match the expected ETag. If modified, the server rejects with a precondition error (typically HTTP **412**), forcing business conflict resolution instead of stripping the condition and overwriting blindly.

### 11.2. Conditional Upload with If-Match

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobUploadFromFileOptions;
import java.time.Duration;

public final class ConditionalUpdate {
    public static void replaceIfUnchanged(
            BlobClient blob, String file, String expectedETag) {
        BlobUploadFromFileOptions options =
            new BlobUploadFromFileOptions(file)
                .setRequestConditions(
                    new BlobRequestConditions().setIfMatch(expectedETag)
                );

        blob.uploadFromFileWithResponse(
            options, Duration.ofMinutes(10), Context.NONE
        );
    }
}
~~~

Exact class and option names vary by SDK version. Test **large-file/block transfers** to confirm how conditions apply to the final commit; never extrapolate from a tiny one-shot upload test that multi-stage operations behave atomically with external systems.

### 11.3. Conditional Download

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobRequestConditions;
import com.azure.storage.blob.options.BlobDownloadToFileOptions;
import java.time.Duration;

public final class ConditionalDownload {
    public static void run(
            BlobClient blob, String target, String expectedETag) {
        BlobDownloadToFileOptions options =
            new BlobDownloadToFileOptions(target)
                .setRequestConditions(
                    new BlobRequestConditions().setIfMatch(expectedETag)
                );

        blob.downloadToFileWithResponse(
            options, Duration.ofMinutes(10), Context.NONE
        );
    }
}
~~~

This illustrates conditional APIs in supporting SDK versions. When a precondition fails, **never retry by dropping `If-Match`**. If Blob Versioning is enabled and workflows need stable reads, you can target a **version-specific blob client** after checking version IDs, API behavior, and retention policies.

### 11.4. Leases vs. Optimistic Concurrency

Blob leases coordinate exclusive writers in specific scenarios, yet require managing renewals, releases, expirations, stale leases, and recovery. In typical applications, **unique blob names + create-only + ETags** are much simpler. If using leases, maintain clear runbooks and authorization checks.

## 12. Data Integrity, Checksums, and Result Verification

### 12.1. Differences Between Verification Layers

| Signal | Useful For | Does Not Replace |
| --- | --- | --- |
| TLS | Transport encryption and server identity | Authorization or business file validation |
| `Content-Length` | Checking byte count | Cryptographic integrity |
| `ETag` | Optimistic concurrency | Content SHA-256 |
| Transactional MD5/CRC64 (where supported) | Per-transfer integrity per service semantics | Trusted source signatures |
| SHA-256 from trusted manifest | Verifying bytes match trusted source | Auth, NAC, or malware scans |
| Malware scan | Detecting known dangerous payloads | Guaranteeing zero risk |

### 12.2. Computing SHA-256 in Java Without Loading the Whole File in RAM

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class FileDigest {
    public static String sha256(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[1024 * 1024];

        try (InputStream in = Files.newInputStream(path)) {
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (n > 0) md.update(buffer, 0, n);
            }
        }
        return HexFormat.of().formatHex(md.digest());
    }
}
~~~

In a **lab with an immutable file**:

~~~java
String expected = FileDigest.sha256(sourcePath);
blob.uploadFromFile(sourcePath.toString(), false);
blob.downloadToFile(downloadPath.toString(), false);
String actual = FileDigest.sha256(downloadPath);

if (!expected.equalsIgnoreCase(actual)) {
    throw new IllegalStateException("Content integrity mismatch");
}
~~~

Prerequisite: the source file must not mutate between hashing and uploading. Production systems may snapshot or copy to an immutable staging file, or hash inline within a controlled upload stream. **Never treat a SHA-256 stored inside mutable blob metadata as a tamper-proof manifest**; store expected digests inside a properly protected trust boundary.

### 12.3. Cost of Round-Trip Verification

Uploading 100 GiB and immediately downloading 100 GiB just to verify consumes bandwidth, time, and egress charges when running outside Azure. Match verification to criticality using SDK transport checks, ETag/size checks, signed manifests, sampling, and periodic audits rather than applying expensive full re-downloads to every blob.

### 12.4. Quarantine and Screening Uploaded Files

For uploads from untrusted users:

~~~mermaid
flowchart LR
    IN["Upload"]
    Q["Quarantine container"]
    SCAN["Scan + validate"]
    READY["Approved container"]
    META["Metadata READY"]
    DENY["Reject / investigate"]
    IN --> Q --> SCAN
    SCAN -->|"Pass"| READY --> META
    SCAN -->|"Fail"| DENY
~~~

Publish objects only after scanning and validation policies pass. Malware scanning reduces risk, yet does not render every file harmless. Account for data residency, scanner permissions, and scanning latency.


## 13. Blob Storage SDK Errors and Retry Policies

### 13.1. Not Every Error Should Be Retried

| HTTP Status / Symptom | Likely Cause | Action |
| --- | --- | --- |
| `400 Bad Request` | Invalid blob name, headers, conditions, or size | Fix request; do not retry verbatim |
| `401 Unauthorized` | Invalid or expired token/key | Inspect identity/credential and refresh properly |
| `403 Forbidden` | Missing data role, SAS permission, network ACL, or policy | Separate auth vs. firewall before raising permissions |
| `404 Not Found` | Missing account/container/blob or wrong name | Verify URI, casing, and object state |
| `409 Conflict` | Lease, immutability policy, blob type, or state conflict | Inspect error code and resolve condition |
| `412 Precondition Failed` | Stale ETag/`If-Match`/`If-None-Match` | Never retry by dropping conditions; resolve concurrency |
| `416 Range Not Satisfiable` | Invalid download byte range | Check file size and version |
| `429 Too Many Requests` | Service or gateway throttling/rate limit | Backoff/jitter, shed load, review quotas |
| `500/503` | Transient error or service/dependency overload | Bounded retry; check Azure status and metrics |
| Network timeout / connection reset | Dropped link before, during, or after transfer | Commit state unknown; verify idempotency |
| `UnknownHostException` | Broken DNS, Private Endpoint, or endpoint typo | Fix DNS/routing, not data roles |
| TLS handshake error | CA trust, hostname, or network interception | Fix trust/DNS; never disable TLS validation |
| File not writable / local `AccessDeniedException` | Local filesystem permissions or path conflict | Fix local host environment; unrelated to Blob RBAC |

An HTTP 403 can stem from firewall or network policies, not solely Azure RBAC. Inspect error codes, substatuses, and diagnostics **without printing secrets into errors**.

### 13.2. Handling BlobStorageException in Java

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobStorageException;

import java.nio.file.Path;

public final class SafeUploadErrors {
    public static void run(Path source, BlobClient blob) {
        try {
            blob.uploadFromFile(source.toString(), false);
        } catch (BlobStorageException ex) {
            int status = ex.getStatusCode();
            String code = String.valueOf(ex.getErrorCode());

            // Production: use structured logs with request IDs;
            // never log URLs with SAS tokens or headers with credentials.
            System.err.println(
                "Blob upload failed: status=" + status
                + " code=" + code
            );

            if (status == 403) {
                throw new SecurityException(
                    "Storage authorization or network policy denied request"
                );
            }
            if (status == 409 || status == 412) {
                throw new IllegalStateException(
                    "Blob exists or precondition not satisfied"
                );
            }
            throw ex;
        }
    }
}
~~~

**This illustrates error classification**, not a complete production exception mapper. Also handle client cancellations, non-storage exceptions, dependency timeouts, and committed operations whose responses dropped; HTTP 403 maps to several distinct Storage error codes.

### 13.3. SDK Retries vs. Application-Layer Retries

The Azure SDK includes a **retry policy** for errors considered transient by its version and transport. Before adding an outer retry loop:

1. Check how many retries and what backoff the SDK already performs.
2. Enforce a total **deadline** for the user request or job.
3. Use exponential backoff + jitter per service guidance.
4. Never retry permission `401/403` or concurrency `412` errors as transient.
5. Never multiply retries uncontrolled across API gateway × app × SDK.
6. Attach idempotency keys to operations with side effects.
7. Measure attempt counts, success-after-retry rates, retry latency, and request costs.

Layered retry amplification example:

~~~text
API Gateway:    3 retries
Application:    3 retries
SDK:            4 attempts

Worst case (if not capped globally):
3 × 3 × 4 = 36 HTTP attempts for 1 logical operation
~~~

That is why you need a **request-wide** retry budget rather than per-library limits alone.

### 13.4. Timeouts to Track

- Connection timeout: TCP/TLS setup.
- Read/response timeout: waiting for server data.
- Per-request timeout: bounding one HTTP operation.
- Overall transfer deadline: total upload/download duration.
- Business request deadline: maximum HTTP API response time for users.
- Job deadline: batch or background worker limit.

Too-short timeouts fail valid uploads; overly long timeouts pin resources indefinitely. For multi-GB files, prefer **asynchronous jobs + status polling** over holding a single HTTP request open.

### 13.5. Structured Logs Without Leaking Credentials

Telemetry should capture:

~~~json
{
  "operation": "blob.upload",
  "container": "documents",
  "blobCategory": "invoice",
  "bytes": 1058576,
  "durationMs": 812,
  "attemptCount": 2,
  "statusCode": 201,
  "result": "success",
  "requestId": "opaque-correlation-id"
}
~~~

This is an **application-defined schema**, not default JSON emitted by the Azure SDK. Never log account keys, SAS query strings, OAuth tokens, full user-supplied file paths, PII, or payload bytes. If logging blob names containing tenant IDs, enforce log read permissions and retention limits.

## 14. Sync vs. Async: Choosing the Right Transfer Model

### 14.1. Sync BlobClient

Easy to read and test:

~~~java
BlobClient blob = BlobClients.documents()
    .getBlobClient("lab/examples/hello.txt");

blob.uploadFromFile("data/hello.txt", false);
blob.downloadToFile("data/hello-downloaded.txt", false);
~~~

In Servlet MVC apps, blocking uploads hold a thread until completion. Under high traffic, enforce concurrency caps, size thread pools carefully, set limits, and offload long transfers to background workflows.

### 14.2. Creating an Async Client

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobAsyncClient;
import com.azure.storage.blob.BlobServiceAsyncClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String account = System.getenv("AZURE_STORAGE_ACCOUNT");

BlobServiceAsyncClient service =
    new BlobServiceClientBuilder()
        .endpoint("https://" + account + ".blob.core.windows.net")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildAsyncClient();

BlobAsyncClient blob = service
    .getBlobContainerAsyncClient("documents")
    .getBlobAsyncClient("lab/examples/hello.txt");
~~~

This snippet only **constructs the client**; it has not executed any upload yet. Async APIs use Reactor (`Mono`/`Flux`), requiring data sources to be modeled as proper reactive streams. **Never call `block()` on the WebFlux event loop** just to say you are "using async." Verify schedulers, bounded concurrency, backpressure, and cancellation.

### 14.3. Async Does Not Guarantee Higher Speed

Async lets servers use fewer blocking threads for many I/O-bound operations—it **does not increase network bandwidth or storage throughput**. For a single large file, high-level sync transfers with internal parallelism may suffice; for thousands of concurrent uploads, reactive workloads help when the entire pipeline is non-blocking.

Metrics to compare in benchmarks:

- Throughput (MB/s and requests/s).
- p95/p99 transfer latency.
- Heap, GC pauses, and open connections.
- Thread counts and CPU saturation.
- 429/503 counts and retry rates.
- Client cancellations and backpressure behavior.
- Transaction and cross-region egress costs.

### 14.4. Browser Direct Upload with SAS: An Alternative Pattern

For large files over the Internet, proxying every byte through the API overloads backends. Instead:

1. Web client requests permission to upload.
2. Backend authenticates the user, checks quotas, file type, and tenant.
3. Backend generates a safe object ID and blob name.
4. Backend issues a **narrow, short-lived SAS token** or supported delegated upload capability.
5. Browser uploads directly to Blob Storage subject to SAS scope, CORS, and network rules.
6. Backend verifies the committed blob, size, checksum, malware scan, and metadata.
7. Marks the object `READY`; frontends use the object only after verification.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Java API
    participant S as Blob Storage
    B->>A: Request upload permission
    A->>A: Auth, tenant, quota, safe name
    A-->>B: Short-lived scoped upload capability
    B->>S: Upload file (HTTPS)
    S-->>B: Upload result
    B->>A: Notify completion
    A->>S: Verify blob/size/metadata
    A-->>B: Object READY or reject
~~~

**Risks:** a SAS is a bearer credential; anyone holding the URL can use it within its bounds. Enforce tight scopes, short expirations, start-time clock skew buffers, CORS, network allowlists, and max-size checks. A SAS granting `write` or `create` does not stop a malicious user from uploading oversized or invalid content—always validate server-side post-upload.

### 14.5. User Delegation SAS vs. Account SAS

| Type | Signed With | Characteristics |
| --- | --- | --- |
| Service/account SAS | Typically Shared Key | Depends on account key and access policies |
| **User delegation SAS** | User delegation key tied to Microsoft Entra | Preferred when avoiding Shared Keys |
| URL without SAS | No token in URL | Private containers still require auth |

Java backends can generate **user delegation SAS** tokens using supported APIs and permissions. The identity needs the required role/action to request a user delegation key, and the SAS must be scoped strictly to the exact blob and short time window. Never issue a container-wide SAS when only one object is authorized, and never log full signed URLs.

**If the storage account disables Shared Key authorization**, Shared-Key-signed SAS tokens fail; user delegation SAS has its own support requirements. Check account policies before designing browser uploads.

## 15. Security for Production Uploads and Downloads

### 15.1. Defense in Depth

| Layer | Mechanism | Does Not Replace |
| --- | --- | --- |
| Business auth | User/tenant/object permissions in API | App's Entra data role |
| Managed identity | OAuth/Entra principal without static keys | End-user business authorization |
| Azure RBAC data plane | Reader/Contributor at narrowest scope | Tenant-level content isolation |
| Private Endpoint / firewall | Restricts network data paths | Authentication |
| HTTPS/TLS | Transport encryption and hostname verification | Business authorization |
| Content validation/scanning | Inspects untrusted uploaded payloads | Network security |
| Versioning / soft delete | Recovery options for accidental deletes/overwrites | Preventing active unauthorized edits |
| Immutability / retention | Prevents modification/deletion during policy period | Preventing unauthorized reads |
| Audit / alerts | Detects anomalous activity | Automated data recovery |

### 15.2. Private Endpoints and DNS

A Blob endpoint:

~~~text
stfilesprod001.blob.core.windows.net
~~~

With Private Endpoints and Private DNS configured properly, the hostname resolves to a private IP per architecture. The associated zone is typically `privatelink.blob.core.windows.net`. Clients must sit inside a routed VNet or use proper hybrid DNS/forwarding.

Linux/macOS:

~~~bash
ACCOUNT="stfilesprod001"
nslookup "$ACCOUNT.blob.core.windows.net"
nc -vz "$ACCOUNT.blob.core.windows.net" 443
~~~

PowerShell:

~~~powershell
Resolve-DnsName stfilesprod001.blob.core.windows.net
Test-NetConnection stfilesprod001.blob.core.windows.net -Port 443
~~~

**Valid DNS/TCP does not prove valid RBAC**. Verify Storage firewall/public network access policies and Private Endpoint connection approval separately. Never fix private DNS issues by disabling TLS certificate validation.

### 15.3. Shared Keys and Account Key Rotation

Prefer Entra ID. When legacy apps genuinely require account keys:

- Store keys in Key Vault/secret managers—never commit to source control.
- Grant least-privilege Key Vault read access and enforce rotation policies.
- Isolate keys across dev, staging, and production.
- Plan primary/secondary key rotation with testing.
- Never print `AZURE_STORAGE_CONNECTION_STRING` or full keys into logs.
- Evaluate disabling `allowSharedKeyAccess` once all clients migrate.

Never regenerate an active key without a rollout plan for all consumers. Account-key-signed SAS tokens are also invalidated when their signing key rotates.

### 15.4. Blob Soft Delete, Versioning, and Immutable Data

**Soft delete** and **versioning** (where supported by SKU/account features) assist recovery from accidental deletes or overwrites, yet do not replace full backup/DR or compliance plans. Understand retention windows, restore semantics, extra storage costs, and account policies.

Some containers or blobs enforce **immutability policies or legal holds** blocking edits and deletes for a retention period or legal mandate. This can cause overwrite or delete attempts to fail with 409/403 even when the app holds Contributor RBAC. **Never remove an immutability policy** to "fix" an upload error on regulated records.

### 15.5. Data Classification, Scanning, and Content-Disposition

- Authenticate users before every upload and download.
- Enforce MIME, size, extension, and file-signature validation.
- Never serve user-uploaded HTML/SVG inline as trusted content without sanitization.
- Scan for malware before publishing.
- Use `attachment` disposition and safe naming for untrusted downloads.
- Never embed secrets or PII inside filenames, metadata, or SAS logs.
- Enforce object expiration/retention per compliance rules.
- Where strict tenant isolation is required, consider separate containers or accounts per threat model.

### 15.6. Never Use Public Containers to Bypass Authorization

Public container access exposes blobs without user tokens per account/container settings. **Never enable public containers for invoices, HR records, or sensitive reports**. Even genuinely public assets need controlled upload permissions and lifecycle management.


## 16. Performance: Latency, Throughput, and Capacity Planning

### 16.1. Measure the Right Units

For upload/download operations:

- **End-to-end duration:** from when the app initiates the transfer until completion and verification.
- **Payload bytes:** actual file bytes transferred.
- **Throughput:** MiB/s per transfer or aggregate transfers.
- **Concurrent transfers:** active uploads/downloads in flight.
- **Retry count:** extra attempts caused by transient failures.
- **p50/p95/p99 latency:** latency broken down by file-size bucket, region, and operation.
- **Failure / partial transfer rate:** failed or truncated transfers.
- **Memory/heap peak:** byte buffers across concurrent files.
- **Remote dependency latency:** Blob service/HTTP time vs. local file processing.

For a 1,024 MiB file transferred in 16 seconds:

\[
\text{Throughput} = \frac{1024\ \mathrm{MiB}}{16\ \mathrm{s}}=64\ \mathrm{MiB/s}
\]

This is a basic **payload throughput** calculation; it excludes retry bytes, encoding, network overhead, and scan/hash time if omitted from the timer.

### 16.2. Timing Uploads with System.nanoTime

~~~java
import com.azure.storage.blob.BlobClient;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public final class TimedTransfer {
    public static void upload(Path source, BlobClient blob)
            throws Exception {
        long bytes = Files.size(source);
        long start = System.nanoTime();

        blob.uploadFromFile(source.toString(), false);

        long elapsedNanos = System.nanoTime() - start;
        double seconds = elapsedNanos / 1_000_000_000.0;
        double mibPerSec = (bytes / 1_048_576.0) / seconds;

        System.out.printf(
            "bytes=%d durationMs=%d throughputMiBs=%.2f%n",
            bytes,
            TimeUnit.NANOSECONDS.toMillis(elapsedNanos),
            mibPerSec
        );
    }
}
~~~

This snippet may print `Infinity` or skewed numbers for tiny files where elapsed time nears zero; use it only in labs. Production systems should use Micrometer/OpenTelemetry histograms and spans tagged by file-size bucket and operation—never put full filenames or user IDs into high-cardinality metric labels.

### 16.3. Meaningful Benchmarking

To compare transfer options fairly:

1. Use representative file sizes: 64 KiB, 1 MiB, 64 MiB, 1 GiB.
2. Keep region and network route constant; measure RTT and egress bandwidth.
3. Record JVM version, SDK version, HTTP transport, and app replica count.
4. Test concurrency 1, 4, 8... within safe limits.
5. Record p95/p99 latency, throughput, heap/GC, 429/503s, and retries.
6. Test under simulated packet loss and throttling in staging.
7. Never benchmark by flooding a production storage account.
8. Compare **cost and correctness**, not just raw MB/s.

If tuning increases throughput by 10% at the cost of 3× RAM, 429 errors, and higher charges, it is a bad trade-off for production.

### 16.4. Region Affinity

Placing apps and Storage in different regions raises latency, egress charges, data sovereignty risks, and overall cost. Co-locate compute with Storage whenever requirements permit. When using cross-region replication, understand the **account redundancy model** and RPO/RTO: replication does not replace accidental-delete recovery or backups.

### 16.5. Optimizing Range Downloads and Resumability

For large-file downloads, Azure Blob supports **range reads** via the API. A client can checkpoint progress, ETag/version, and fetch missing ranges, provided it:

- Pins the blob version or uses conditional requests (`If-Match`).
- Validates offsets, lengths, and total file size.
- Never stitches together ranges from two different ETags.
- Verifies a full-file checksum upon completion.
- Bounds parallel range downloads and backpressure.
- Accounts for transaction charges generated by many range calls.

Never use range downloads blindly on a mutating file without version/ETag checks, or you will assemble corrupted bytes across versions.

### 16.6. Choosing Sync vs. Async by Concurrency

| Context | Starting Choice | Why |
| --- | --- | --- |
| CLI utility transferring 1–20 files | Sync `BlobClient` | Simple to write and effective |
| Spring MVC API for small/medium uploads | Sync with thread pool/quotas | Straightforward lifecycle management |
| WebFlux reactive pipeline | `BlobAsyncClient` + reactive streams | Avoids blocking event loops when end-to-end async |
| Uploading many large files | High-level parallel upload + quota-bounded scheduler | Controls concurrent transfers |
| Multi-GiB browser uploads | Scoped SAS + direct-to-Blob + server verification | Avoids proxying bytes through Java |
| Continuous data ingestion | Batch/event-driven app + checkpoints | Enables idempotency and long-term ops |

Never adopt async simply because traffic feels "high": let actual workload benchmarks justify complexity.

## 17. Monitoring, Logging, and Blob Storage Costs

### 17.1. Three Observability Layers

1. **Application telemetry:** operation, payload size, duration, retries, errors, opaque object IDs, client cancellations.
2. **Azure Storage metrics:** transactions, ingress/egress, latency, availability, and error/throttling patterns per service-supported metrics.
3. **Control-plane/security logs:** resource, network, role, and key changes, diagnostic settings, access failures, and audits.

Azure Monitor does not know **which application end user** accessed an object unless your backend logs correlation metadata safely. Likewise, Azure Activity Log **is not a log of every data-plane Blob operation**; enable appropriate Storage diagnostic categories per policy.

### 17.2. Metrics Worth Putting on Dashboards

| Metric | Signal |
| --- | --- |
| Upload duration p95 by size bucket | Are large files slowing down abnormally? |
| Download duration p95 | How long do users wait? |
| MiB/s and operations/s | Are throughput targets met? |
| 401/403/404/409/412 | Authentication, authorization, missing paths, conflicts |
| 429/503 and retry counts | Throttling or service/network saturation |
| Client cancellations / partial transfers | Abandoned users or dropped links |
| Storage availability | Is the service returning errors? |
| Success E2E latency vs. server latency | Service latency vs. client/network overhead |
| Storage capacity and egress | Growth and budget tracking |
| Failed malware scans | Content safety and quality |
| SAS/key/role changes | Policy violations or configuration drift |
| Soft delete / version counts | Heavy overwrite or deletion churn |

Exact metric names and dimensions vary by resource and version. Use `az monitor metrics list-definitions` or the Azure Portal to verify—never assume every metric exists across all SKUs.

### 17.3. Reading Metric Definitions with Azure CLI

~~~bash
STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query id -o tsv)

az monitor metrics list-definitions \
  --resource "$STORAGE_ID" \
  -o table
~~~

Some **Blob service metrics** live at the child resource scope per API/provider; inspect the actual resource ID and metric definitions before querying specific names. Do not treat empty output at the storage account scope as "Storage has no metrics."

### 17.4. Application Insights and Distributed Traces

For Java on Azure, use the **Application Insights Java agent**, **OpenTelemetry instrumentation**, or approved integrations. Link spans end-to-end:

~~~text
Trace: POST /documents/upload
  Span: authentication
  Span: validate-file
  Span: blob.upload
    bytes: 157286400
    container: documents
    blobCategory: invoice
    status: success
    durationMs: 1850
    attemptCount: 2
  Span: database.update-metadata
  Span: send-response
~~~

Never record blob contents, account keys, SAS query strings, access tokens, or PII in span attributes. Capture `attemptCount` from actual instrumentation rather than hard-coding `1` when the SDK retries internally.

### 17.5. HTTP Logging Must Protect Secrets

The Azure SDK supports configurable HTTP logging. Never enable full request/response body or sensitive header logging in production. If logging URLs, **redact SAS query parameters**. Azure diagnostics can capture client IPs and context; restrict Log Analytics workspace permissions and retention.

### 17.6. Cost Drivers

| Cost Item | Driver |
| --- | --- |
| Stored GiB/month | Capacity, redundancy, access tier |
| Write operations | Put Blob, Put Block, Put Block List, and other requests |
| Read operations | Get Blob, Get Properties, and range reads |
| Data retrieval | Depends on online/cold tier and operation type |
| Egress | Data downloaded to Internet or cross-region per pricing |
| Early deletion | Minimum retention windows on certain cold/archive tiers |
| Versioning / soft delete | Retaining extra versions and soft-deleted blobs |
| Storage transactions | Many small files, retries, or frequent metadata HEADs |
| Monitoring | Diagnostic logs and Log Analytics ingestion |
| Private Endpoint / networking | Endpoint and network data processing charges |
| App compute | CPU/RAM, replicas, and transfer workers |

**Never cite static USD figures** as Azure pricing, since rates depend on region, tier, redundancy, date, and agreements. Use the Azure Pricing Calculator, Cost Management, and real resource usage metrics.

### 17.7. Rough Throughput/Cost Estimation Formula

Suppose an app ingests 10,000 files/day averaging 5 MiB each:

\[
10{,}000 \times 5\ \mathrm{MiB} = 50{,}000\ \mathrm{MiB/day}
\]

That equals roughly 48.8 GiB of payload per day (since 1 GiB = 1,024 MiB), **excluding versions, replication/storage redundancy, and metadata**.

Over 30 days with no deletions:

\[
48.8\ \mathrm{GiB/day} \times 30 \approx 1{,}464\ \mathrm{GiB}
\]

This is a hypothetical capacity planning illustration, not a billing quote. Total cost also includes reads/writes, retrieval, networking, soft delete/versioning, and monitoring.

### 17.8. FinOps and Security Go Together

- Never turn off critical audit/diagnostic logs to save money without checking compliance requirements.
- Apply lifecycle policies only after verifying business retention and retrieval SLAs.
- Pick access tiers based on access frequency and rehydration latency tolerance.
- Never issue long-lived SAS tokens just to save one API call.
- Optimize block sizes and batch small files when transaction charges dominate.
- Clean up temp files and orphaned uploads after review without deleting legal-hold data.
- Tag storage accounts with owners, budget alerts, and capacity forecasts.


## 18. Pre-Production Testing for Uploads and Downloads

### 18.1. Test Matrix

| Test | Expected Result |
| --- | --- |
| Upload 1 KiB file with Blob Data Contributor | Succeeds; content length matches |
| Download file with Blob Data Reader | Exact bytes returned |
| Re-upload same blob name with `overwrite=false` | Rejected; original blob unchanged |
| Upload with read-only Reader identity | Rejected |
| Download non-existent blob | 404 or matching error |
| Upload with stale ETag | 412 / precondition failure |
| Network drop near end of upload | Zero duplicates; state reconciled |
| File exceeding max size | Rejected before consuming excessive resources |
| `.pdf` containing malicious payload | Blocked from publishing; caught by scan/validation |
| Download to existing local file with `overwrite=false` | Existing file untouched |
| Output path outside allowed directory | Rejected |
| User A attempts to download tenant B's object | Denied by business authorization |
| Upload 5 GiB file via stream/file transfer | Does not load whole file onto heap |
| Raising concurrency | Throughput improves or stays safely bounded |
| Transient 429/503 | Bounded retries; metrics record attempts |
| Permanent 403 | Never retried infinitely |
| Archived blob | Not expected to download instantaneously |
| Soft-deleted / versioned object | Restored per policy without breaking retention |
| Checksum mismatch after download | Fails validation; never transitions to `READY` |
| Expired or out-of-scope SAS | Rejected |
| Client cancels mid-stream | Partial transfer recorded and cleaned up |
| Private-only network | DNS/TLS and Private Endpoint work from workload |

### 18.2. Unit Tests, Integration Tests, Chaos Tests

**Unit tests:** mock the wrapper around the Blob client to test business authorization, tenant-scoped paths, `PENDING`/`READY` transitions, retry decisions, quotas, and exception mapping. Never treat mocks as proof that Azure networking or RBAC works.

**Integration tests:** run against a real lab storage account testing uploads, downloads, and preconditions using actual Entra identities. Never use Shared Keys to "prove" a Blob Data Reader cannot write.

**Chaos/performance tests:** inject network drops, simulated 503/throttling, high file concurrency, memory limits, and recovery flows. Run only in approved environments and load windows.

### 18.3. Testing Idempotency

~~~text
Given:
  Object ID O1, blob name tenants/t001/O1.pdf
  Local file content F, upload_intent=PENDING

When:
  First upload commits on Azure, client loses response

Then:
  Retry must not accidentally create O2
  App inspects O1, checks size/checksum/properties
  If matching: PENDING -> READY
  If mismatched: report conflict / integrity failure
~~~

### 18.4. Mandatory Negative Authorization Tests

~~~text
Given:
  User A is authorized to view O1 in tenant A
  User B is NOT authorized to view O1

When:
  User B calls GET /documents/O1

Then:
  API rejects before calling the Blob SDK
  Never leaks account keys, signed URLs, or blob names
~~~

**An app identity holding Blob Data Contributor does not mean every end user can download every blob.** Business-layer authorization must always precede storage access.

### 18.5. Cleanup Without Breaking Shared Data

Use an isolated prefix like `integration-tests/<run-id>/` and track created objects for cleanup. Require approval before deletion; remember soft delete and versioning may continue billing retained data. Never delete production containers/resource groups or remove legal holds for test cleanup.

## 19. Layered Incident Troubleshooting Runbook

### 19.1. Collecting Safe Diagnostics

Capture non-sensitive context:

~~~text
timestamp_utc
subscription_id, resource_group
storage_account, container
opaque_object_id, safe_blob_name
auth_mode (Entra / SAS / Shared Key)
principal_object_id (if permitted)
sdk_version, app_release
http_status, StorageErrorCode
x-ms-request-id, client_request_id
elapsed_ms, bytes, attempts
~~~

Never paste raw account keys, OAuth tokens, SAS URLs, or private documents into logs or tickets.

### 19.2. Step 1 — Verify the Target Azure Account

~~~bash
az account show \
  --query "{name:name,id:id,tenantId:tenantId}" -o json

az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,location:location,publicNetworkAccess:publicNetworkAccess,allowSharedKey:allowSharedKeyAccess}" \
  -o json
~~~

Your laptop CLI may use a developer identity while the AKS/App Service app uses a separate managed identity. Never assume runtime permissions based on local CLI success.

### 19.3. Step 2 — DNS and TCP/TLS

~~~bash
nslookup "$ACCOUNT.blob.core.windows.net"
nc -vz "$ACCOUNT.blob.core.windows.net" 443
~~~

For private-only accounts, run checks from the actual VNet, Pod, or VM. Verify Private Endpoint approval, Private DNS Zone links, hybrid DNS forwarding, NSGs, routes, and firewalls. Valid DNS/TCP **is not enough** to prove read/write RBAC permissions.

### 19.4. Step 3 — Inspect Status and Error Codes

| Condition | Investigation Focus |
| --- | --- |
| 401 | Identity token and credential |
| 403 | RBAC data role, SAS scope/expiry, network ACL |
| 404 | Container/blob name, casing, object state |
| 409 | Lease, immutability, blob type, concurrent operation |
| 412 | ETag, `If-Match`, `If-None-Match` |
| 416 | File size, range, version |
| 429/503 | SDK retries, quotas, network/service load |
| Timeout | Unknown commit state on server |
| Local filesystem error | Local file permissions/path/disk space, not Azure RBAC |

Never use the account primary key or enable public containers as a blanket workaround for 403 errors.

### 19.5. Step 4 — Verify Commit State After Timeout

1. Keep the object ID and blob name unchanged.
2. Query properties using a valid identity.
3. Compare size, ETag, trusted checksum/manifest, and upload intent.
4. If already committed accurately, mark `READY`.
5. If not present, retry with the same idempotency key and conditional create within deadline.
6. If content differs, halt and raise an integrity conflict.
7. Clean up orphaned blocks/files after a grace period and authorization review.

### 19.6. Step 5 — Investigate Performance

- Are Blob operations tracked by p50/p95/p99 across file-size buckets?
- Are files split into overly tiny blocks or range calls?
- Are concurrency, heap, GC, or HTTP connections saturated?
- Are excessive retries or double retries happening?
- Are the client and Storage co-located in the same region or crossing regions?
- Are blobs in Archive/Cold tiers needing rehydration?
- Is there a network or Private Endpoint bottleneck?
- Is the SDK client being recreated per request?
- Are malware scans or checksum calculations dominating end-to-end latency?

Fix bottlenecks backed by evidence; never crank up concurrency or huge timeouts just to mask bugs.

### 19.7. Step 6 — Post-Check

- Upload/download latencies meet targets.
- SHA-256/manifest checks pass per policy.
- RBAC, tenant authorization, and private networking remain intact.
- 429/5xx/retries and partial transfers stay within normal baselines.
- Zero orphaned or duplicate objects created by retries.
- Storage, egress, and transaction costs align with forecasts.
- Alerts, auditing, soft delete/versioning, and retention remain active.


## 20. Comprehensive Lab: Upload, Download, and Verify SHA-256

### 20.1. Sample Environment

~~~text
Module: Azure SDK for Java
Language: Java 17+
Storage account: stfileslabunique001
Container: documents (private)
Identity: Microsoft Entra ID / managed identity
Azure data role: Storage Blob Data Contributor, scoped appropriately
Local source: data/sample.pdf
Blob: lab/java-sdk/<uuid>.pdf
Download: downloads/sample-copy.pdf
~~~

Resource names are **illustrative**; run only if you have an authorized lab Storage account and permissions. Without Azure access, work through the design exercises without provisioning resources.

### 20.2. Execution Steps

| Step | Action | Evidence |
| --- | --- | --- |
| 1 | Check `az account show`/subscription | Correct Azure context |
| 2 | Inspect Storage account with `show` | Account, region, network policy |
| 3 | Confirm `documents` container is private | No anonymous reads allowed |
| 4 | Verify principal's data-plane role | Reader/Contributor at right scope |
| 5 | Verify DNS/TLS/private route | Connects to right Blob endpoint |
| 6 | Add Maven dependencies/BOM | Build resolution succeeds |
| 7 | Build `BlobClients` with `DefaultAzureCredential` | No account key needed |
| 8 | Generate unique object name | Collision-free, independent of user filename |
| 9 | Upload via `uploadFromFile(..., false)` | Valid ETag and size returned |
| 10 | Read `BlobProperties` | Content type, length, ETag |
| 11 | Download to a new local filename | Does not overwrite existing output |
| 12 | Compute SHA-256 of source and downloaded file | Hashes match |
| 13 | Retry upload to the same blob name | Rejected; existing content unchanged |
| 14 | Test upload with a Reader-only identity | Rejected |
| 15 | Test downloading a non-existent blob | 404 handled cleanly |
| 16 | Test update with a stale ETag | 412 handled cleanly |
| 17 | Inspect Azure Monitor / SDK telemetry | Latency, failures, bytes |
| 18 | Clean up lab prefix when authorized | Other data untouched |

### 20.3. Putting the Java Classes Together

Use a single project containing `BlobClients`, `UploadFileExample`, `DownloadFileExample`, and `FileDigest` from earlier sections.

Flow:

~~~text
Local source file
  ↓ calculate trusted SHA-256 (source stable)
UploadFileExample: create-only
  ↓ get ETag/size
Metadata DB: mark pending/ready after validation
  ↓
DownloadFileExample: new destination
  ↓ calculate SHA-256
Compare expected vs downloaded
  ↓
Record result and cleanup lab
~~~

If checksums mismatch, the lab **fails**. Never copy expected hashes from user-controlled metadata when trusted integrity verification is required.

### 20.4. Verifying Throughput

Select representative files such as 1 MiB, 64 MiB, and 1 GiB. Time with `System.nanoTime()` and compute:

\[
\text{MiB/s}=\frac{\text{bytes}/1{,}048{,}576}{\text{duration seconds}}
\]

Uploading 64 MiB in 4 seconds yields throughput ≈ **16 MiB/s**. This is solely a calculation on hypothetical numbers and does not guarantee any particular SKU/network throughput.

### 20.5. Scenario A — OutOfMemoryError on Large Uploads

**Symptom:** Spring Boot accepts a 5 GiB file, calls `MultipartFile.getBytes()`, and concurrent HTTP requests spike heap usage.

**Fix:** stream/file-backed uploads, cap concurrent transfers, enforce request size limits and quotas, and monitor heap/GC. For massive streams, evaluate direct browser uploads via short-scoped SAS tokens with server-side verification.

### 20.6. Scenario B — Upload Times Out Yet Blob Already Exists

**Possible Cause:** the server committed the blob while the response dropped. **Fix:** reuse the same upload ID/name, verify properties/checksum, and finalize pending metadata instead of creating a second blob for the same business record.

### 20.7. Scenario C — Client Has Azure Reader Yet Fails to Download

**Possible Cause:** management-plane `Reader` does not grant Blob data read access, or a firewall, SAS, or credential issue is blocking it. **Fix:** check auth mode, data RBAC Reader/container scope, endpoint, and network—never fall back to Shared Keys.

### 20.8. Scenario D — Worker Overwrites Cause Lost Updates

Two workers update the same blob concurrently. **Fix:** enforce `If-Match` and ETag optimistic concurrency; handle 412 as a business conflict rather than retrying unconditional overwrites.

### 20.9. Scenario E — Blob Download Checksum Mismatch

**Fix:** halt publishing and compare the trusted manifest SHA-256 against downloaded bytes. Verify whether the source changed, check ETag/version consistency, and confirm the SDK transfer was not truncated.

### 20.10. Scenario F — Overly Broad SAS Issued to Browser

The API issued a container-wide SAS instead of a single-blob short-lived SAS. **Fix:** authenticate user/tenant, restrict scope/permissions tightly, cap TTL, validate content post-upload, and never log signed URIs.

### 20.11. Scenario G — Archive Download Fails

**Fix:** check access tier, rehydration semantics, and early-deletion/retrieval costs. Inform the user of asynchronous progress instead of infinitely retrying `downloadToFile`.

### 20.12. Scenario H — Costs Climb After Enabling Versioning

**Cause:** overwrites accumulate versions, retention keeps soft-deleted data, and operations/egress grow. **Fix:** inventory version counts and usage, review lifecycle/retention policies in Cost Management, and never delete legally required records just to cut bills.

## 21. Self-Check Questions

**Q1.** How do `BlobServiceClient`, `BlobContainerClient`, and `BlobClient` differ?

**Answer:** They scope to the storage account, container, and individual blob respectively; uploads/downloads typically run via `BlobClient`.

**Q2.** When should you use Block Blobs?

**Answer:** For most standard files like PDFs, images, and CSVs; the SDK automatically splits large payloads into blocks.

**Q3.** Is Append Blob right for every `.log` file?

**Answer:** No. Base the choice on write/append semantics, size, mutability needs, API limits, and pricing.

**Q4.** Can you construct a `BlobClient` before the container exists?

**Answer:** You can build the client handle, yet operations will fail if the container does not exist or permissions are missing.

**Q5.** Why prefer `DefaultAzureCredential`/managed identity?

**Answer:** Eliminates embedding long-lived Storage account keys in applications and allows central governance via Microsoft Entra and Azure RBAC.

**Q6.** Can Azure management `Reader` read private blobs using an Entra token?

**Answer:** No. You need a data-plane permission such as `Storage Blob Data Reader` or another valid auth mechanism.

**Q7.** What does `uploadFromFile(path, false)` mean?

**Answer:** Uploads from a local file while forbidding overwriting an existing blob; helpful for preventing collisions.

**Q8.** Should you use `blob.exists()` followed by upload as your sole race-condition guard?

**Answer:** No. Another request can create the blob in between; use create-only / `If-None-Match` as a server-side precondition.

**Q9.** How do `If-None-Match: *` and `If-Match: ETag` differ?

**Answer:** `If-None-Match` requires the blob not to exist yet; `If-Match` allows updates only if the blob still matches the expected ETag.

**Q10.** When receiving HTTP 412, should you retry without the condition?

**Answer:** No. It indicates a concurrency/precondition conflict requiring business resolution.

**Q11.** Is an ETag a SHA-256 checksum?

**Answer:** No. ETags handle concurrency and caching; use a trusted hash to verify content bytes.

**Q12.** Why not use `InputStream.available()` as content length?

**Answer:** It only estimates bytes readable without blocking per stream implementation, not total stream size.

**Q13.** Why not load an entire 10 GiB file into a byte array?

**Answer:** Exhausts heap, spikes GC, and fails under concurrent uploads; use streams or SDK file/chunk transfers.

**Q14.** Does staging a block commit it into the blob?

**Answer:** No. Staged blocks must be committed via an ordered block list to form blob content.

**Q15.** Is a request retry the same as resumable upload across process crashes?

**Answer:** No. Resumability requires persistent checkpoints/manifests and verifying staged/committed parts across sessions.

**Q16.** After an upload timeout, can you assume the blob does not exist?

**Answer:** No. Azure may have committed it; verify the object via its idempotency key.

**Q17.** What does `downloadToFile(path, false)` prevent?

**Answer:** Prevents overwriting an existing local file, though the app must still prevent path traversal and manage filesystem permissions.

**Q18.** When should you use `BlobAsyncClient`?

**Answer:** When your pipeline is non-blocking/reactive and concurrent workloads benefit, with proper backpressure and lifecycle management; it does not automatically outrun sync on single transfers.

**Q19.** Why never log full SAS URLs?

**Answer:** A SAS is a bearer credential; leaked URLs grant access within the token's scope and lifetime.

**Q20.** Should you issue a container-wide read SAS when a user only has access to one invoice?

**Answer:** No. Scope permissions and TTL strictly to the authorized object and enforce business authorization.

**Q21.** Why does Private Endpoint not replace RBAC?

**Answer:** Private Endpoints govern network routing; identity and data RBAC still govern read/write permissions.

**Q22.** Does HTTP 403 always mean a missing data role?

**Answer:** No. It can also stem from network ACLs, SAS expiry/scope, or other policies; inspect the error code and request context.

**Q23.** How do you download a blob in the Archive tier?

**Answer:** Rehydrate it to an online tier via supported mechanisms, accounting for latency and costs; never treat it as instant download.

**Q24.** Do Blob soft delete and versioning prevent all accidental deletions?

**Answer:** They aid recovery when enabled within retention windows, yet do not replace authorization, backup/DR, or immutability policies.

**Q25.** Why can uploading a blob and inserting a SQL row become inconsistent?

**Answer:** The two services do not share an automatic ACID transaction; use `PENDING`/`READY` states, idempotency, and reconciliation.

**Q26.** Which metrics should you inspect when uploads slow down?

**Answer:** Duration by file size, MB/s, concurrency, retries, 429/503s, networking, heap/GC, SDK version, and Storage metrics.

**Q27.** Which factors determine Storage pricing?

**Answer:** Capacity, redundancy, tier, read/write transactions, retrieval, network egress, versions/soft delete, and monitoring, varying by region and date.

**Q28.** When should you use user delegation SAS instead of proxying bytes through a Java API?

**Answer:** For direct-to-Blob flows where the backend can issue narrow Entra/user-delegation permissions, validate files post-upload, and satisfy network/CORS/security policies.

## 22. Pre-Production Checklist

- [ ] Storage account/container are private in the right region and redundancy tier.
- [ ] Managed identity/Entra configured; data RBAC applied at narrowest scope.
- [ ] Zero account keys or long-lived SAS tokens in code, images, or logs.
- [ ] Azure Blob SDK/BOM versions pinned and compatibility-tested.
- [ ] `BlobServiceClient`/`BlobContainerClient` reused across requests.
- [ ] Blob names generated server-side; object IDs and tenants authorized.
- [ ] File size/MIME limits, malware scanning, and quarantine policies enforced.
- [ ] Create-only or conditional update semantics applied per business rules.
- [ ] Idempotency and reconciliation handle post-commit timeouts.
- [ ] Download paths/output files sandboxed without arbitrary overwrites.
- [ ] Streaming/chunking and concurrency capped to prevent OOM.
- [ ] SHA-256, ETags, and versions used for their proper purposes.
- [ ] Retry budgets, timeouts, cancellations, and partial transfers handled.
- [ ] Private Endpoints, DNS, TLS, and public access policies verified.
- [ ] Soft delete, versioning, retention, and restore drills match data risk.
- [ ] Metrics, logs, alerts, cost budgets, and owners defined.
- [ ] Negative tests cover Reader roles, cross-tenant access, and stale ETags.
- [ ] Recovery and safe cleanup runbooks documented.

## Key Takeaways

- The **Azure Blob Storage SDK for Java** provides clients at service, container, and blob scopes; **Block Blobs** are the standard choice for files.
- **DefaultAzureCredential + managed identity + Storage Blob Data RBAC** eliminate hard-coded secrets, yet applications must still enforce end-user and tenant authorization.
- `uploadFromFile(..., false)`, `downloadToFile(..., false)`, and **`If-None-Match`/`If-Match`** prevent accidental overwrites and resolve optimistic concurrency cleanly.
- **Large files** require streaming/chunking and bounded concurrency. The SDK can stage and commit blocks automatically; manual block uploads are needed only for custom checkpoint/resumable workflows.
- **ETags are not SHA-256 hashes**. For critical data, verify bytes against a trusted manifest and scan user-supplied files.
- A timeout does not mean an upload failed: enforce **idempotency, commit verification, and reconciliation**.
- **Private Endpoints, TLS, Azure RBAC, short-lived SAS tokens, soft delete/versioning, and auditing** are complementary defense layers—none replaces another.
- Production readiness requires **throughput/latency/error metrics, retry budgets, cost analysis, tests, alerts, runbooks, and clear ownership**.
