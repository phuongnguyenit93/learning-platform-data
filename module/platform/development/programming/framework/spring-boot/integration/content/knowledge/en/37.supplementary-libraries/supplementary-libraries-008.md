# Cloud Service or Object Store SDKs and Client Lifecycle Management in Spring Boot

In a Spring Boot application, storing PDF invoices, product images, report exports, or attachments often requires an **object store** such as Amazon S3, Google Cloud Storage (GCS), Azure Blob Storage, or an API-compatible system. Java SDKs send requests to the service, sign/authenticate calls, manage HTTP connections, retry, and convert data. However, **creating the SDK client properly and controlling its lifecycle** matters just as much as calling `putObject` or `download`: creating a client per request wastes connection pools; forgetting to close streams can exhaust the pool; mishandling credentials and shutdown leaves the app unable to stop cleanly or suddenly stripped of access.

This lesson belongs to the **Supplementary Libraries** chapter of the **SPRING_BOOT_INTEGRATION** module, which studies how to structure Spring Boot integration flows across HTTP clients, databases, caches, message brokers, and Spring Integration adapters. We treat object storage as an **out-of-process dependency** with its own contracts, failures, limits, costs, and state. The focus is on configuration design, SDK client lifecycles, object/key contracts, retries, idempotency, database–storage transactions, testing, and observability in production operations.

The main examples use **Spring Boot 3.x and AWS SDK for Java 2.x (`S3Client`)**. Comparative sections cover the GCS Java client and Azure Blob Java SDK. APIs, artifact versions, retry strategies, and resource behavior can change across SDKs and transports; always check the documentation for **the version you are running** before deploying.

## 1. From Filesystem to Object Storage: Shifts You Must Understand

A filesystem exposes paths and familiar operations: create files, rename, read a slice, overwrite, delete. Object storage exposes objects identified by **bucket/container + object key/blob name**, plus byte contents and metadata; operations typically go through remote service APIs. The key is realizing this is not a POSIX disk mounted locally:

| Component | S3 | GCS | Azure Blob |
| --- | --- | --- | --- |
| Storage namespace | Bucket | Bucket | Container inside a storage account |
| Content identity | Object key | Object name | Blob name |
| Primary Java client | `S3Client`, `S3AsyncClient` | `Storage`, or alternative API generations as needed | `BlobServiceClient`, `BlobContainerClient`, `BlobClient` and async variants |
| Preferred default auth | AWS default credentials provider chain / workload role | Application Default Credentials (ADC) / workload identity | `DefaultAzureCredential` / managed identity |
| SDK connection management | S3 service client with HTTP transport/pool | Transport selected within the library | HTTP pipeline/client used by Azure SDK |
| Concurrent write control | Conditional requests, ETag, version ID | Generation/metageneration preconditions | ETag, request conditions, leases/versioning per API |

Object keys like `invoices/2026/11/INV-1042.pdf` contain `/`, yet they are usually just **logical names**, with no guarantee of a physical directory tree. Prefix/delimiter listing simply creates a folder-like illusion. Never store objects using local paths and assume `rename`, `append`, `fsync`, or file locking mean the same thing across providers.

### Example Real Integration Flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as invoice-service (Spring Boot)
    participant DB as SQL database
    participant S as Object store
    participant B as Message broker

    U->>A: Request invoice generation
    A->>DB: Insert PENDING job + outbox
    DB-->>A: Commit
    A->>S: Upload PDF to immutable key
    S-->>A: Object metadata / version / checksum
    A->>DB: Update job READY + object key
    A->>B: Publish InvoiceReady (via outbox)
    A-->>U: Download URL or reference ID
~~~

This is a **multi-resource business flow**: SQL, object storage, and the broker **do not automatically share a single transaction**. You must define what happens if upload succeeds while the SQL update fails, or if SQL committed while upload never happened.

## 2. Distinguishing Three Different Lifecycles

The word "lifecycle" has at least three distinct meanings in cloud SDK integrations:

1. **SDK client lifecycle**: when the client is created, reused, allocated HTTP resources, refreshes credentials, and closes when the app stops.
2. **Data-transfer request lifecycle**: opening requests/streams, bounding timeouts, handling retries, and releasing response bodies/connections after reading or cancellation.
3. **Object lifecycle in the store**: creation, versioning, storage class transitions, retention, expiration, deletion, and restoration per bucket/container rules.

This lesson focuses on (1), though a properly closed client will not fix stream leaks in (2) or objects retained forever in (3).

~~~mermaid
flowchart TD
    APP["Spring Boot ApplicationContext"] --> CLIENT["Singleton SDK Client"]
    CLIENT --> POOL["HTTP pool / threads / credential provider"]
    CLIENT --> REQ1["Upload request"]
    CLIENT --> REQ2["Download request"]
    REQ2 --> STREAM["ResponseInputStream"]
    STREAM -->|"Close in finally/try-with-resources"| RELEASE["Return/release HTTP connection"]
    APP -->|"Shutdown -> close()"| STOP["Client releases resources"]
    REQ1 --> OBJECT["Object in bucket/container"]
    OBJECT --> POLICY["Lifecycle rules, retention, versioning"]
~~~

**Do not confuse them:** calling `close()` on a client at shutdown does not delete objects, and deleting an object does not release an open `ResponseInputStream` inside your process.

## 3. Choosing SDKs, Dependencies, and Managing Versions

An application does not strictly need a "cloud starter" to use an SDK. You can declare the official Java SDK directly and integrate it as a Spring `@Bean`. Starters like Spring Cloud AWS, Spring Cloud GCP, or Spring Cloud Azure add auto-configuration, property bindings, and additional adapters; when adopting a starter, verify Spring Boot version compatibility and avoid accidentally declaring two clients for the same role.

### AWS SDK for Java 2.x

With Maven, use the AWS SDK BOM to keep versions consistent across `s3`, `sts`, and other AWS modules:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>software.amazon.awssdk</groupId>
      <artifactId>bom</artifactId>
      <version>${aws.sdk.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
  </dependency>
</dependencies>
~~~

`aws.sdk.version` must be defined by your project. Depending on the transport selected, you may need to declare the matching HTTP client module—for example, Apache HTTP client for sync or Netty NIO for async. Do not mix SDK v1 `com.amazonaws.*` with SDK v2 `software.amazon.awssdk.*` in the same adapter without a clear reason and migration plan.

### Google Cloud Storage and Azure Blob

Typical dependencies:

~~~xml
<!-- GCS: align versions with google-cloud-libraries-bom
     managed by the project, then add the main module. -->
<dependency>
  <groupId>com.google.cloud</groupId>
  <artifactId>google-cloud-storage</artifactId>
</dependency>

<!-- Azure: align versions using azure-sdk-bom tested
     together with Azure Identity. -->
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-storage-blob</artifactId>
</dependency>
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-identity</artifactId>
</dependency>
~~~

The snippets above only show **module coordinates**, assuming the project already configured dependency management. Without importing a BOM or pinning versions explicitly, Maven will not infer versions from Spring Boot for every cloud library. Lock and inspect the dependency tree, especially when SDKs share Netty, Reactor, gRPC, Jackson, or OpenTelemetry with the application.

### Sync vs. Async?

| Criterion | Synchronous Client | Asynchronous Client |
| --- | --- | --- |
| Common API | `S3Client` | `S3AsyncClient` |
| Execution model | Caller thread waits on I/O | Returns futures/reactive publishers, callbacks/executors |
| In Spring MVC | Easy to integrate for small/medium operations | Can reduce blocked threads under high throughput |
| In WebFlux | Calling directly on the event loop blocks | Better fit when transport and entire pipeline are non-blocking |
| Resource management | HTTP pool, response streams | HTTP pool, event-loop/executors, body publishers/cancellation |
| Complexity | Easy to follow call stacks | Must control backpressure, buffering, timeouts, and cancellation |

Do not pretend a blocking `S3Client` is non-blocking simply by wrapping it in `Mono.fromCallable()`. When using WebFlux alongside a blocking SDK, offload to an appropriate scheduler, cap concurrency, and monitor held threads. For large uploads, consider clients or transfer managers supporting real multipart or async transfers.

## 4. Designing a Singleton Bean for S3Client

AWS SDK for Java 2.x recommends **reusing service clients**, as clients are thread-safe and hold HTTP connection pools that are expensive to initialize. Per HTTP request or broker message, **never** create a fresh `S3Client.builder().build()`. In Spring, a singleton bean owned by the `ApplicationContext` is the natural fit.

### 4.1. Configuration via @ConfigurationProperties

`application.yml`:

~~~yaml
app:
  object-storage:
    bucket: invoice-documents
    region: ap-southeast-1
    max-download-bytes: 10485760  # 10 MiB if loading into memory is needed

# Credentials come from environment/runtime; never put access keys in YAML.
~~~

Configuration class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.object-storage")
public record ObjectStorageProperties(
        String bucket,
        String region,
        long maxDownloadBytes
) {
}
~~~

When placing this record in a standalone source file, match the Java filename and project package. For production, add Bean Validation for bucket/region and size caps so misconfigurations fail fast at startup rather than upon receiving the first message with an empty bucket name. You can rely on the AWS default region chain, though if deployment policy mandates a specific region, declare it explicitly to prevent requests going to the wrong region.

### 4.2. Creating and Closing the Client with the Spring Lifecycle

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ObjectStorageProperties.class)
public class ObjectStorageClientConfiguration {

    @Bean(destroyMethod = "close")
    S3Client s3Client(ObjectStorageProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .overrideConfiguration(config -> config
                        .apiCallTimeout(Duration.ofSeconds(15))
                        .apiCallAttemptTimeout(Duration.ofSeconds(5)))
                .build();
    }
}
~~~

Points to understand:

- `S3Client` is an SDK client safe to share across threads; keep no per-request mutable state inside the bean.
- Spring creates **one singleton bean** here and calls `close()` when the `ApplicationContext` destroys it. `destroyMethod = "close"` states resource ownership explicitly.
- The example **passes no static credentials**. AWS SDK uses the default credentials provider chain when `credentialsProvider` is omitted, resolving credentials from environment mechanisms like dev profiles or infrastructure workload roles/identities.
- `apiCallAttemptTimeout` bounds **a single attempt**; `apiCallTimeout` bounds **the whole API call across attempts**. Choose durations matching your SLA; 5/15 seconds are purely illustrative, not production policy.
- Do not create a second `S3Client` bean for the same role if a starter already auto-configures and injects one; if multiple regions/accounts are genuinely needed, use bean names/`@Qualifier` to select the right client.

If you build a custom `SdkHttpClient` and share it across multiple AWS clients, define **who owns closing the HTTP client**. The SDK will not necessarily close an externally supplied HTTP client passed via `httpClient(...)`. `httpClientBuilder(...)` and `httpClient(...)` carry different resource ownership semantics: follow the SDK contract and test shutdown behavior.

### 4.3. Do Not "Warm Up" Clients with Privileged Operations

Do not call `listBuckets()` or `headBucket()` as a default health check across every application: a service principal may only hold `s3:GetObject`/`s3:PutObject` on one prefix and lack permission to list buckets. Such a probe can report "unhealthy" even when real operations succeed.

When readiness checks an external dependency, pick a minimal check **aligned with permissions and SLAs**; distinguish **startup validation** from **health probes running every few seconds** to avoid API costs and cascading restarts during brief cloud blips.

## 5. Credentials, Regions, Endpoints, and Permissions

An SDK client typically requires four configuration groups: **identity**, **service address/region**, **transport/TLS**, and **request policies**.

### 5.1. Prefer Workload Identities

Preferred authorization approaches:

- **AWS**: workload role (e.g., instance/container task role or workload identity), default credentials chain; use personal profiles only in dev.
- **GCP**: Application Default Credentials with a service account / workload identity scoped to required buckets/objects.
- **Azure**: `DefaultAzureCredential` and managed identity or workload identity on supported runtimes, granting RBAC roles on the target storage account/container.
- **Self-hosted S3-compatible**: endpoints, regions, signing, and credentials matching the provider's implementation; never assume compatibility with every AWS S3 feature.

Never commit access keys, secret keys, connection strings with passwords, or SAS tokens into code, test fixtures, or logs. Never grant account-wide owner/admin rights as a quick fix for 403 errors. Separate read/write/list/delete permissions and prefixes by business boundary.

**Credentials rotation**: whether the SDK refreshes credentials automatically depends on the provider in use. Workload credential providers normally auto-refresh; if you construct `StaticCredentialsProvider` with hardcoded keys, the SDK cannot tell when a secret rotates. Rotating static credentials may require rebuilding the provider/client or performing controlled restarts. Test rotation in practice.

### 5.2. Endpoint Overrides for Emulated Environments

Some tests use MinIO, LocalStack, or S3-compatible servers. In those cases you may configure:

~~~java
S3Client testClient = S3Client.builder()
        .region(Region.US_EAST_1)
        .endpointOverride(URI.create("http://localhost:9000"))
        .forcePathStyle(true)
        .credentialsProvider(
                StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test-key", "test-secret")))
        .build();
~~~

`Region`, `URI`, `StaticCredentialsProvider`, and `AwsBasicCredentials` come from the JDK/AWS SDK. This snippet is **test configuration only**—plaintext HTTP and static keys are discouraged in production. `forcePathStyle(true)` is useful for certain emulators, not a flag to enable blindly on every S3 service.

When overriding endpoints, signing region, host headers, TLS certificates, and routes must align. Never "fix" TLS failures by disabling certificate verification or trusting all hostnames.

## 6. Business Adapters Isolate the SDK from the Rest of the App

Controllers, RabbitMQ/Kafka listeners, and Spring Integration flows should not build SDK requests or handle cloud exceptions directly in many places. Create a **port/adapter** with a clean application contract:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.util.Map;

public interface DocumentStore {
    StoredDocument putSmall(
            String objectKey, byte[] content, String contentType);
    void downloadTo(String objectKey, OutputStream target)
            throws IOException;
    void delete(String objectKey);
}

public record StoredDocument(
        String bucket,
        String objectKey,
        String versionId,
        String eTag
) {
}
~~~

`objectKey` is an application-controlled identifier; never concatenate raw user-supplied paths directly. `versionId` and `eTag` help track results, yet **do not replace a business checksum**. Never assume an ETag is always the payload's MD5, especially with multipart uploads or server-side encryption.

S3 adapter for small objects:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Component
public class S3DocumentStore implements DocumentStore {

    private static final int MAX_SMALL_UPLOAD = 8 * 1024 * 1024;

    private final S3Client s3;
    private final ObjectStorageProperties settings;

    public S3DocumentStore(
            S3Client s3, ObjectStorageProperties settings) {
        this.s3 = s3;
        this.settings = settings;
    }

    @Override
    public StoredDocument putSmall(
            String key, byte[] content, String contentType) {

        if (content.length > MAX_SMALL_UPLOAD) {
            throw new IllegalArgumentException(
                    "Use streaming/multipart upload for large files");
        }

        var request = PutObjectRequest.builder()
                .bucket(settings.bucket())
                .key(key)
                .contentType(contentType)
                .build();

        var response = s3.putObject(
                request, RequestBody.fromBytes(content));

        return new StoredDocument(
                settings.bucket(), key,
                response.versionId(), response.eTag());
    }

    @Override
    public void downloadTo(String key, OutputStream target)
            throws IOException {

        var request = GetObjectRequest.builder()
                .bucket(settings.bucket())
                .key(key)
                .build();

        try (var input = s3.getObject(request)) {
            input.transferTo(target);
        }
    }

    @Override
    public void delete(String key) {
        s3.deleteObject(DeleteObjectRequest.builder()
                .bucket(settings.bucket())
                .key(key)
                .build());
    }
}
~~~

This example is intentionally simple to highlight **client and stream ownership**:

- The adapter **never closes `s3`** after individual methods; Spring closes the singleton bean at shutdown.
- `getObject()` returns a stream tied to the HTTP response; `try-with-resources` closes it on every exit path, including if `transferTo` throws.
- `OutputStream target` is passed in by the caller. The adapter does not close the caller's stream; whoever created it owns closing or flushing per contract.
- `putSmall` takes a `byte[]`, so it fits only small files already in memory. The 8 MiB limit is an illustrative choice here, not an S3 limit.
- `deleteObject` on a versioned bucket may insert a **delete marker** rather than permanently purging every version. Object lock/retention or policies may forbid deletion. Never assume "delete succeeded" erased every byte and version.
- The methods do not yet map cloud exceptions to domain exceptions or cap downloaded bytes. Later sections add production-ready policies.

### Caution When Reading Streams into Memory

If an API genuinely needs a `byte[]`, enforce a **size cap**. Loading an entire object from a bucket into the heap based solely on client input can cause `OutOfMemoryError`. For HTTP download responses, streaming and backpressure fit better; for large files, serve directly from the object store via short-lived signed URLs if the security model permits.

A safer read might check `HeadObject` first, yet object size can change between HEAD and GET if the key is overwritten. Therefore, byte-count enforcement must still happen inside the **streaming loop**, or by reading a pinned version/generation.

## 7. HTTP Response Lifecycles and Multipart Uploads

Resource bugs occur far more often on **individual requests** than during client creation.

### 7.1. Streams Must Be Consumed or Closed

With AWS `S3Client#getObject`, `ResponseInputStream<GetObjectResponse>` holds an HTTP connection until fully read or closed. If code reads only a few header bytes to sniff a file type and drops the stream, the connection cannot return cleanly to the pool or must be aborted; under load, other callers block waiting for free connections.

~~~java
try (var stream = s3.getObject(
        GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build())) {

    // Stream processing; closes automatically.
    stream.transferTo(destination);
}
~~~

If a downstream HTTP client aborts mid-download, `try-with-resources` still executes and releases the stream. With async clients, managing future/publisher cancellation, memory buffers, subscribers, and event loops is just as critical as closing synchronous `InputStream` instances.

### 7.2. Large File Uploads Need a Different Strategy

With sync APIs, `RequestBody.fromInputStream(input, contentLength)` requires an **exact content length**. Passing too small a number truncates bytes; passing too large a number can hang or fail. When a server-managed temp file already exists on disk, `RequestBody.fromFile(path)` lets the SDK read the file cleanly:

~~~java
var request = PutObjectRequest.builder()
        .bucket(bucket)
        .key(objectKey)
        .contentType("application/pdf")
        .build();

s3.putObject(request, RequestBody.fromFile(pdfPath));
~~~

`pdfPath` is a `java.nio.file.Path` verified for origin, size, and permissions. Temp files also have a lifecycle: create them in a restricted directory, process success/failure, and delete in a matching `finally` block.

For large objects, high concurrency, or resumable uploads after failure, consider **multipart uploads and S3 Transfer Manager**. Multipart adds upload IDs, part numbers, per-part ETags/checksums, and a complete step. If a multipart upload is abandoned without abort/cleanup, incomplete parts still incur storage charges. Buckets should have lifecycle rules to clean up **incomplete multipart uploads**, alongside abort logic on error paths.

### 7.3. Never Stuff Resources into Unbounded Global Caches

A service should not cache thousands of clients per tenant or bucket when all share the same identity, region, and transport. Distinguish the **client** from the **request target**: normally one S3 client works across many buckets in the same region/policy. If multi-tenancy demands separate identities/regions, use a bounded cache with safe eviction/closing—ensuring you never close a client currently in use by an active request.

## 8. Timeouts, Retries, and Load Limits

SDKs typically include default retries for errors considered transient. Stacking `@Retryable`, `RetryTemplate`, Reactor `retryWhen`, or broker retries on top can **multiply attempts** unintentionally. A single failing request spanning multiple layers can trigger dozens of real HTTP calls.

### Distinct Timeout Scopes

| Parameter | Scope | Consequence If Omitted |
| --- | --- | --- |
| TCP connect timeout | Time to open connection to endpoint | Threads/calls hang waiting to connect |
| TLS handshake timeout | Time to negotiate TLS | Hard to separate slow networks from cert/handshake issues |
| Socket/read timeout | Wait interval reading/writing on HTTP transport | Individual attempt stalls indefinitely |
| API call attempt timeout | One SDK retry attempt | Unbounded cost per retry |
| API call timeout | Entire API operation including retries/backoff | Upstream SLA expires while SDK keeps retrying |
| Business deadline | Whole business flow across DB, object store, and broker | Independent dependencies add up past API limits |

Example time budget: an API generating files must finish within 10 seconds; the SDK gets a 3-second attempt timeout and 7-second total API call timeout, leaving room for validation, SQL, and response serialization. These numbers are illustrative; large files or cross-region networks need different budgets.

Low-level client configuration specifying HTTP timeouts on the transport builder:

~~~java
import java.time.Duration;
import software.amazon.awssdk.http.apache.ApacheHttpClient;

var client = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .httpClientBuilder(
                ApacheHttpClient.builder()
                        .connectionTimeout(Duration.ofSeconds(2))
                        .socketTimeout(Duration.ofSeconds(4)))
        .overrideConfiguration(o -> o
                .apiCallAttemptTimeout(Duration.ofSeconds(6))
                .apiCallTimeout(Duration.ofSeconds(15)))
        .build();
~~~

Add the `software.amazon.awssdk:apache-client` artifact if not already present. The snippet illustrates timeout relationships, not universal defaults: pick thresholds based on traffic, response sizes, retry counts, and SLAs. For large streaming downloads, socket/read timeouts must distinguish "waiting for the next chunk" from total file transfer duration.

### Error Classification and Retries

| Outcome/Exception | Common Meaning | Handling Approach |
| --- | --- | --- |
| `404` / `NoSuchKeyException` | Key missing or deleted | Handle not-found; do not retry blindly |
| `403 AccessDenied` | Insufficient permissions or policy denial | Check identity, bucket policy, KMS, network policy; do not assume key absence |
| `400` bad request | Bad region/metadata/key/header/contract | Fix caller/config; do not retry indefinitely |
| `409 Conflict` or `412 Precondition Failed` | Conditional write conflict / state changed | Check optimistic concurrency; do not overwrite blindly |
| `429`/`503 SlowDown` or certain `5xx` | Throttling, overload, or transient error | Bounded retry + exponential backoff/jitter |
| `SdkClientException` / network reset | Transport, DNS, TLS, or client-side issue | Classify cause; retry only when operation is safe |
| Timeout after upload | Unclear whether server received/stored object | Check key/version/checksum and idempotency mechanism |
| Expired/invalid credentials | Identity chain/rotation failure | Investigate refresh and permissions; do not keep retrying with bad tokens |

Exact HTTP codes, exception hierarchies, and retryability depend on the cloud SDK. Some S3 read calls return `403` instead of `404` when the principal lacks list/visibility permissions on the bucket. **Never infer object existence from status 403 alone.**

### Bulkheads and Concurrency

HTTP pools, thread pools, servlet threads, Reactor schedulers, and concurrent uploads are all finite resources. When cloud storage slows down, internal request queues can back up and break unrelated APIs. Enforce limits on:

- Concurrent uploads/downloads and total in-flight bytes.
- File size per user/tenant.
- Connection pool size and acquisition timeout.
- Retry attempt counts and total wait budget.
- Concurrent multipart uploads.
- Temp memory/disk usage and job queue depth.

For heavy file processing, offloading PDF generation or uploads to a queue/worker with backpressure, persisted state, and monitoring is usually far easier to control than holding a synchronous HTTP request open indefinitely.

## 9. Overwrites, Reconciliation, and Object Idempotency

A `PUT` to the same object key typically overwrites existing content (depending on permissions and preconditions), making the **object key itself part of the business contract**.

Example key designs:

| Key Pattern | Characteristics | Caveats |
| --- | --- | --- |
| `orders/{orderId}/invoice.pdf` | Easy to look up by order | Retries/re-writes can overwrite; needs versioning/conditional writes |
| `orders/{orderId}/invoices/{version}.pdf` | Business-versioned | Manage cleanup/retention of old versions |
| `documents/{documentId}/{sha256}.bin` | Tied to immutable content | Metadata DB must store `documentId`, hash, content type |
| `uploads/{uuid}` | Avoids random key collisions | Retries must reuse the **same UUID** to avoid duplicates |

For create-only writes, use **conditional writes** supported by the provider. S3 supports `If-None-Match: *` on `PutObject` to prevent overwriting an existing key, depending on SDK/API version. GCS offers generation preconditions such as `doesNotExist()`; Azure offers matching ETag/request conditions. Handle conflict/precondition errors as inspectable business outcomes rather than retrying blindly.

**ETag does not always equal the object's MD5.** When verifying content integrity, store a mutually agreed checksum algorithm verified end-to-end—such as SHA-256 in system-managed metadata. A timeout can occur **after** the server finished the `PUT`; retrying with a newly randomized key breaks idempotency.

### Document State Machine

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> UPLOADING
    UPLOADING --> READY: upload confirmed + DB metadata saved
    UPLOADING --> RETRYABLE_FAILURE: timeout/5xx
    RETRYABLE_FAILURE --> UPLOADING: retry with same ID
    UPLOADING --> FAILED: unrecoverable + manual action
    READY --> DELETING: retention/legal policy allows
    DELETING --> DELETED: storage delete verified
~~~

`READY` should only be reached once both the object and business metadata align per contract. If an upload finishes yet DB update fails, a reconciliation job should catch the **orphan object**; if the DB shows `READY` while the object was deleted out-of-band, detect and alert on the inconsistency.

## 10. SQL Transactions Do Not Span Object Storage

A classic pitfall:

~~~java
@Transactional
public void registerDocument(DocumentRequest request) {
    documentRepository.save(...);
    s3.putObject(...); // Network call outside the database transaction.
}
~~~

`@Transactional` manages the SQL transaction via `PlatformTransactionManager`—**it does not fold `PutObject` into the same ACID transaction**. If SQL rolls back after upload, the object still lingers. If SQL commits and upload fails, the row exists without a file. Never assume XA/2PC is feasible with object storage.

A clearer managed flow:

1. SQL writes `documentId`, immutable key, expected checksum, and `PENDING` status in one transaction; for async processing, also write an outbox event.
2. A worker picks up the job and uploads the object; every retry reuses the same document ID/key with proper conditional writes.
3. Once upload is confirmed, update SQL to `READY` with version/ETag/checksum and emit an event via the outbox.
4. On transient errors, keep a retryable state with backoff; on permanent data/permission errors, mark `FAILED` for handling.
5. Run a reconciliation job detecting stale `PENDING` rows, orphan objects, and metadata mismatches; delete only per retention policy.

This mirrors other broker integrations: **at-least-once processing + idempotency + durable state**, rather than assuming exactly-once delivery. For invoices, the data contract must also define who may read the object and for how long.

## 11. Presigned URLs and Direct Browser Uploads

For large files, routing *browser → Spring Boot → object store* turns the application into a byte-shuffling proxy, burning bandwidth and connections. Switch to **presigned URLs** or signed upload policies:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Spring Boot API
    participant S as Object Store
    participant D as Metadata DB

    B->>A: Request upload permission (size/type/business ID)
    A->>D: Save pending upload, random object key
    A-->>B: Time-limited Presigned PUT URL
    B->>S: Direct PUT over TLS
    S-->>B: HTTP success + headers
    B->>A: Notify completion with documentId
    A->>S: HEAD/checksum/metadata to verify
    A->>D: Mark READY after verification
~~~

With S3 SDK v2, use `S3Presigner` to sign time-limited requests:

~~~java
import java.time.Duration;
import java.net.URL;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;

public URL presignUpload(
        S3Presigner presigner, String bucket, String key) {

    var put = PutObjectRequest.builder()
            .bucket(bucket)
            .key(key)
            .contentType("application/pdf")
            .build();

    var signed = PutObjectPresignRequest.builder()
            .signatureDuration(Duration.ofMinutes(5))
            .putObjectRequest(put)
            .build();

    return presigner.presignPutObject(signed).url();
}
~~~

Create `S3Presigner` as a shared bean with matching region/credentials and close it with the application lifecycle when the implementation requires `close()`:

~~~java
@Bean(destroyMethod = "close")
S3Presigner s3Presigner(ObjectStorageProperties properties) {
    return S3Presigner.builder()
            .region(Region.of(properties.region()))
            .build();
}
~~~

A signed URL is a **bearer capability**: anyone holding the URL can perform the permitted action until it expires and any other constraints fail. Never log full URLs, avoid overly long expiration windows, and scope keys and policies per user/tenant. If the signed request includes `Content-Type` or specific headers, the browser must send **the exact signed header values** or signature verification will fail.

Never treat the browser calling "upload complete" as proof of a valid object. The backend must verify size, content type, object existence, checksum/metadata, tenant ownership, and race conditions against concurrent uploads. Presigned uploads do not scan for viruses or malicious content automatically; add scanning/quarantine and transition to `READY` only after safety checks pass.

## 12. Comparing Java Client Lifecycles Across Three Ecosystems

A rule claiming "every SDK client implements `Closeable`" is **false**. Inspect whether each specific client exposes `close()`, and who owns the HTTP transport and credential provider.

### 12.1. AWS S3: `S3Client` and `S3Presigner`

- `S3Client` and `S3AsyncClient` have AWS SDK lifecycle/`close()`. With Spring singletons, close on `ApplicationContext` shutdown.
- `S3Presigner` should be reused when issuing URLs frequently; close when the bean is destroyed.
- `ResponseInputStream` from each `getObject` must be closed **per request**.
- SDK-created HTTP clients vs. **caller-supplied** HTTP clients differ in ownership; design resource beans explicitly.

### 12.2. Google Cloud Storage: ADC and `Storage`

Example creating `Storage` from default credentials/configuration:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GcsConfiguration {

    @Bean(destroyMethod = "close")
    Storage gcsStorage() {
        return StorageOptions.getDefaultInstance().getService();
    }
}
~~~

This example uses `com.google.cloud.storage.Storage` from the Java library; modern versions expose `close()` to release transport resources. Exact closing behavior can depend on transport and version, so check Javadocs. Other Google Cloud clients—especially gRPC `*Client` classes—often use `close()`/`shutdown()` and sometimes require awaiting termination; never assume identical lifecycles across clients merely because they carry the Google Cloud name.

Google ADC resolves credentials from the environment. In production, prefer service accounts / workload identity with least privilege on buckets; avoid distributing JSON service account keys.

When writing to GCS, use generation preconditions to avoid overwrites:

~~~java
BlobInfo info = BlobInfo.newBuilder(
        BlobId.of(bucketName, objectName))
        .setContentType("application/pdf")
        .build();

storage.create(
        info,
        payloadBytes,
        Storage.BlobTargetOption.doesNotExist());
~~~

This code illustrates uploading bytes; `BlobInfo`, `BlobId`, and `Storage` belong to `com.google.cloud.storage`. If the object already exists, the SDK raises a precondition error; the application must decide whether to re-read metadata or reject. Never upload unbounded file sizes as raw byte arrays.

### 12.3. Azure Blob: Service, Container, and Blob Clients

The Azure SDK commonly uses a hierarchical client design:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

BlobServiceClient serviceClient = new BlobServiceClientBuilder()
        .endpoint("https://account-name.blob.core.windows.net/")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();

var container = serviceClient.getBlobContainerClient("documents");
var blob = container.getBlobClient("invoices/INV-1042.pdf");
~~~

`BlobServiceClient` is the entry point for a storage account; `BlobContainerClient` and `BlobClient` narrow the resource scope. These clients are designed to be reused. **Do not habitually attach `close()` to `BlobServiceClient` if the API does not define it.** Underlying HTTP transport, Reactor/Netty resources, and credential provider lifecycles follow the Azure SDK contract and how any custom `HttpClient` was supplied. If you instantiate a shared HTTP client or event loop yourself, that owner is responsible for shutting it down on app stop.

Registering as a Spring bean:

~~~java
@Bean
BlobServiceClient azureBlobServiceClient(
        @Value("${app.azure.blob.endpoint}") String endpoint) {
    return new BlobServiceClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
}
~~~

The SDK and framework manage default resources. For custom HTTP clients or credentials needing cleanup, declare beans for them and manage their lifecycles per that resource type's guidance. **Never blindly set `@Bean(destroyMethod = "close")` on a type without a `close()` method.**

### Usage Design Comparison

| Topic | AWS S3 SDK v2 | Google Cloud Storage Java | Azure Blob SDK |
| --- | --- | --- | --- |
| Long-lived shared client | `S3Client` / `S3AsyncClient` | `Storage` | `BlobServiceClient` and child clients |
| Constructed via | `S3Client.builder()` | `StorageOptions...getService()` | `BlobServiceClientBuilder` |
| Default auth | Credential provider chain | ADC | `DefaultAzureCredential` |
| Closing client | `close()` when no longer needed | Per `Storage.close()` / transport version | Check HTTP pipeline/transport owner; never assume `close()` exists on every client |
| Region/endpoint selection | Region and endpoint override | Project/options/endpoint | Storage account endpoint |
| Conditional writes | `If-None-Match`/ETag/version | Generation preconditions | ETag/request conditions |
| Large transfers | Multipart / Transfer Manager | Resumable upload/streaming per API | Block blob staged blocks / parallel upload |

## 13. Object Lifecycle: Retention, Versioning, and Safe Deletion

Even when the client closes properly, objects persist under storage policies. Separate **data lifecycle** from JVM lifecycle.

| Policy | Purpose | What to Evaluate |
| --- | --- | --- |
| Versioning | Keep versions to recover from overwrites/deletes | Cost of old versions, permission to delete versions |
| Lifecycle expiration | Auto-delete objects by age/tags/prefix | Avoid prematurely deleting legally retained documents |
| Storage class transition | Move infrequently read data to cheaper tiers | Restore delays, retrieval fees, minimum storage durations |
| Incomplete multipart cleanup | Purge uncompleted parts | Avoid breaking legitimate long-running uploads |
| Object Lock/retention/legal hold | Prevent deletes/edits during retention period | Policy mutability, admin permissions |
| Delete markers/soft delete | Recover after delete operations | Logical delete differs from permanently purging all versions |
| Replication/cross-region | DR and locality needs | Replication lag, cost, access permissions |

A key like `users/{userId}/avatar.jpg` may be overwritten many times. If the bucket enables versioning, prior versions still consume storage; deleting the key does not erase historical versions. For sensitive data with deletion policies, know your versioning, replication, retention, object lock, and purge workflows.

Never set an object expiration rule based solely on creation date while the database still references those objects without synchronization; align business data state and retention policies first.

## 14. Error Classification, Observability, and Security

### Errors by Layer

| Layer | Symptoms | What to Check |
| --- | --- | --- |
| Startup/beans | Client fails to build, empty region, dependency conflict | Properties, dependency management, providers |
| Credentials | Access denied, expired token, ADC failure | Identity, roles, KMS keys, credential rotation |
| Network/HTTP | DNS, TLS, connect timeout, pool wait | Endpoint, proxy, NAT, connection pool, certificates |
| Object API | 404, 409, 412, 429, 503 | Keys, conditions, quotas, service policies |
| Streams | Pool exhaustion, abandoned response bodies | `ResponseInputStream.close()`, cancellation, concurrency |
| Data contract | MIME mismatch, checksum drift, oversized object | Validation, scanning, metadata, bounded reads |
| Business consistency | DB READY while object missing, orphan objects | State machine, outbox, reconciliation |
| Lifecycle | Rising costs, data expiring early, orphaned multiparts | Lifecycle rules, retention, versioning, cleanup |

### Metrics and Logs

Observe both **SDK requests** and **business outcomes**:

- Request counts, HTTP statuses, and operation types (`PutObject`, `GetObject`, `HeadObject`, `DeleteObject`).
- Latency p50/p95/p99, API call attempts, retry delays, timeouts by type, connection acquisition waits.
- Concurrent uploads/downloads, bytes transferred, throughput, active multiparts, and incomplete uploads.
- Credential refresh/auth failures, throttling/5xx, region/signature errors.
- Counts/ratios of `PENDING`, `READY`, `FAILED`, orphan objects, and checksum mismatches.
- Storage/API request/egress costs by workload, bucket, and authorized prefix.

Never log secret keys, bearer tokens, SAS tokens, full presigned URLs, file contents, or metadata containing personal data. Object keys sometimes carry customer identifiers, so log sanitized keys or internal document IDs when needed. Traces should record operation details and correlation IDs; never place credentials into span attributes.

### Key Security Requirements

Secure transport with HTTPS/TLS, verify endpoints, scope bucket/prefix permissions tightly, enable server-side encryption per policy, and protect KMS keys. Validate file types by actual content/threat model rather than trusting browser-supplied `Content-Type`. Never build object keys from unvalidated paths like `../../secret`, never let users choose arbitrary buckets or endpoints (SSRF/exfiltration risk), and never grant object access merely because a caller knows the key name.

For presigned URLs, restrict expiration, allowed actions, keys, and sizes/content types per API/policy capabilities and verify the result after upload. If a CDN/cache sits in front, align invalidation and access control consistently.

## 15. Testing Client Lifecycles and Integration Flows

### 15.1. Unit Tests for Adapters

Mock `S3Client` or use a fake adapter to verify:

- Keys/metadata are constructed in the right format.
- Small files upload from bytes; large files are rejected or routed to streaming.
- S3 responses map to `StoredDocument`, preserving version ID/ETag.
- `404`, `403`, timeouts, and `412` are classified cleanly without retrying permanent errors.
- Singleton `S3Client` is never closed after individual requests.
- `downloadTo` closes the stream even when `OutputStream` throws `IOException`.

To verify bean lifecycle, spin up a small `ApplicationContext` with an `AutoCloseable` test double or mock client, close the context, and assert `close()` was called on shutdown. Do not test only a `@Bean` factory method returning an object while ignoring actual shutdown behavior.

### 15.2. Integration Tests with a Real Object Store or Emulator

| Case | How to Test | Expectation |
| --- | --- | --- |
| Basic upload/download | PUT file with SHA-256, GET back | Bytes and metadata match; stream always closes |
| Separate read/write permissions | Use a least-privilege identity | 403/AccessDenied classified cleanly; never escalate permissions blindly |
| Missing object | GET a random key | Not found or 403 per permissions; no wrong inferences |
| Concurrent writes to same key | Use conditional put / generation precondition | Only one create wins; other caller gets clear conflict |
| Timeout after server commit | Drop response at critical moment | Retry with same document ID/key; no duplicate created |
| Broken stream mid-download | Kill connection while GET reads | Stream released, errors metered |
| Pool exhaustion | Open parallel requests and intentionally hold streams | Warnings/concurrency limits trigger; whole service doesn't hang |
| Credentials rotation | Rotate identity/token in test env | Client refreshes cleanly or restarts per policy |
| Large upload | Multipart/parallel + cancel | Incomplete uploads cleaned up; orphans don't accumulate |
| Versioning and delete | Create multiple versions then delete | Delete markers, retention, and restore work as expected |
| SQL/object consistency | Inject fault between upload and DB commit | Reconciliation brings state back to consistency |
| Presigned upload | Sign URL, upload with valid/invalid headers | Only valid requests within window/constraints succeed |
| Shutdown lifecycle | Close Spring context during active requests | No client/pool/executor leaks; in-flight handled per SLA |

**An emulator is not the real cloud service.** MinIO/LocalStack can differ from AWS in IAM, ACLs, checksums, versioning, multipart, object lock, or presigning; Azurite and GCS fakes have similar gaps. Run fast feedback tests on emulators, plus a focused contract/integration suite on real cloud environments to verify production features.

Cost and latency benchmarks must run in real regions/networks; a fast local test does not prove an API will meet SLAs for multi-GB objects or cross-region egress.

## 16. Common Design Pitfalls

**"Isn't creating `S3Client` inside a service method with `try-with-resources` safer?"**

Not for services handling frequent requests. Repeatedly creating and tearing down HTTP pools adds heavy overhead and defeats connection reuse. Use a long-lived singleton bean, closing only on shutdown or when no longer needed. `try-with-resources` belongs on each request's *response stream*.

**"If `S3Client` closes on Spring shutdown, can connection leaks still happen?"**

Yes. Forgetting to close response streams while the server is running can exhaust the pool long before shutdown. Release resources at *both the request lifecycle and the client lifecycle*.

**"If I put `@Transactional` around an upload, will the upload roll back with SQL?"**

No. Object storage lives outside database transactions. Use durable states, outboxes, bounded retries, and reconciliation.

**"Doesn't the SDK auto-retry guarantee uploads won't duplicate?"**

No. Retries cover certain transport/service failures, yet failures after commit leave uncertain outcomes. Object keys, conditional writes, checksums, and business idempotency determine final state.

**"Does 404 always mean the key doesn't exist, and should 403 be fixed with admin credentials?"**

No. Permissions and providers can mask object existence. Fix IAM using least privilege and inspect the intended action rather than escalating privileges to hide contract issues.

**"Do Azure `BlobServiceClient`, Google `Storage`, and AWS `S3Client` all close the same way?"**

No. Read the API and ownership contract of **the specific client/transport**. AWS `S3Client` supports `close()`, Google Cloud `Storage` supports `close()` in modern versions, while Azure Blob clients manage pipelines differently and do not expose `close()` on every layer.

**"Does deleting an object via the SDK erase the data permanently?"**

Not when versioning, delete markers, soft delete, retention, object lock, or replication are enabled. Design data lifecycles around actual storage policies.

**"Once a presigned URL is handed to the browser, can the file be marked `READY` immediately?"**

No. Confirm the upload actually occurred, matches the expected object/key, checksum/size, and owner permissions, and passed validation/scanning if required.

### Production Readiness Checklist

1. Select a supported SDK/BOM, align dependency versions, and decide sync vs. async for the traffic profile.
2. Create service clients at singleton scope or bounded tenant scope; document owners of clients, HTTP transports, credentials, and shutdown.
3. Use default identity chains/workload identities with least privilege; avoid static keys in apps and test rotation.
4. Configure buckets/containers, regions/endpoints, TLS, KMS, and validation for object keys/metadata.
5. Set per-attempt and total API call timeouts; cap retries, pools, concurrency, and file sizes.
6. Close response streams on every GET; manage temp files, multipart uploads, cancellation, and pools.
7. Define immutable keys, conditional writes/versions, checksums, and idempotency for every retryable operation.
8. Keep SQL–object storage–broker consistent via state machines, outboxes, retries, and reconciliation.
9. Design short-lived presigned URLs, upload completion checks, access control, and payload security.
10. Configure object lifecycles, retention, versioning, and multipart/orphan cleanup per data policy.
11. Monitor errors/latency/retries/bytes/pools and business states; test with emulators **and** real cloud contracts where appropriate.

### Technical References to Cross-Check by Version

- [AWS SDK for Java 2.x – Client Best Practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html): reusing thread-safe service clients and closing response streams.
- [AWS SDK for Java 2.x – Singleton Service Clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/singleton-service-clients.html): sharing one client across the application.
- [AWS SDK for Java 2.x – Timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html): `apiCallTimeout` and `apiCallAttemptTimeout`.
- [AWS SDK for Java 2.x – Uploading Streams](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices-s3-uploads.html): content length and streaming.
- [AWS SDK for Java 2.x – Presigned URLs](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3-presign.html): temporary upload/download access.
- [Google Cloud Java – Storage API](https://docs.cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage.html): lifecycle and precondition-based object operations.
- [Microsoft Learn – Azure Blob Storage Java Quickstart](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-java-how-to-use-blob-storage): clients, identities, and storage account/container/blob structure.

**Key takeaway:** An **SDK client** is an integration component living alongside the application, managing connections and identities; a **request/response stream** is short-lived and must be consumed or closed; and an **object** lives under storage policies independent of the JVM. Designing all three lifecycles properly—together with idempotency, timeouts, transactions, and testing—keeps Spring Boot cloud storage integrations stable.
