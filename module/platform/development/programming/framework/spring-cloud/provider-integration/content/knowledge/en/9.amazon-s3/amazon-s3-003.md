# Amazon S3: Uploading, downloading, listing, and deleting S3 objects

## Lesson objectives

In the `SPRING_CLOUD_PROVIDER_INTEGRATION` module, Spring Boot applications connect to managed services across AWS, Azure, and Google Cloud to store data, exchange messages, and execute business workflows. For **Amazon S3**, the four most common operations are **upload (PUT), download (GET), list (LIST), and delete (DELETE)**. This lesson demonstrates how to perform these operations with **Spring Cloud AWS + AWS SDK for Java v2**, while explaining pagination, streaming, IAM permissions, versioning, common errors, and integration testing.

After this lesson, you will be able to:

- Choose sensible buckets and object keys for application data.
- Upload and download objects without accidentally reading large files entirely into memory.
- List objects by prefix, iterate across pages, and understand the limitations of LIST.
- Delete objects intentionally, distinguishing deletions in buckets with versioning enabled vs. disabled.
- Design S3 operation flows with authorization, error handling, and testing.

> Examples use the `io.awspring.cloud` namespace of modern Spring Cloud AWS and `software.amazon.awssdk` of AWS SDK v2. Configuration requires a Spring Cloud AWS version **compatible with the project's actual Spring Boot version**; this document does not pin a single version number for all systems.

## 1. Data model and the four basic operations

S3 is an **object storage** service. Each object resides in a **bucket** and has a unique **key** within that bucket at a given time. A key is a character string that may contain `/` characters, though it does not require real directories on the server.

Example:

~~~text
s3://training-private-docs/documents/2026/invoice-42.pdf
     └────── bucket ──────┘└──────── object key ────────┘
~~~

An object consists of data (body), accompanying information such as content type and user metadata, and S3-managed state. Mapping business needs to AWS APIs:

| Need | AWS SDK v2 | Typical IAM permission | Outcome |
| --- | --- | --- | --- |
| Upload or replace content | `S3Client.putObject` | `s3:PutObject` | Object is stored by bucket/key |
| Download content | `S3Client.getObject` | `s3:GetObject` | Byte stream and response metadata |
| Inspect info without downloading body | `S3Client.headObject` | `s3:GetObject` | Size, content type, metadata, ETag, etc. |
| List by prefix | `S3Client.listObjectsV2` | `s3:ListBucket` | One page of keys and summary metadata |
| Delete by key | `S3Client.deleteObject` | `s3:DeleteObject` | Delete operation accepted by S3 |

**Two things to remember upfront:** PUT to the **same bucket/key** does not by default create a new file; it may replace the current version. DELETE also does not always mean wiping bytes from S3, especially when the bucket has versioning enabled.

### Typical flow in Spring Boot

~~~mermaid
flowchart LR
    C["Client"] -->|"Authenticate + upload/download request"| A["Spring Boot API"]
    A -->|"Check document permissions"| D["Business database"]
    D -->|"Owner/tenant + object key"| A
    A --> S["Storage service"]
    S -->|"AWS SDK v2, IAM role"| B["Private S3 bucket"]
    B -->|"Object / metadata"| S
~~~

The database usually stores the mapping `documentId → bucket/key, owner, tenant, status`. The key is the storage identifier, while **user access permissions** must be verified by the application before the service calls GET or DELETE on an object.

## 2. Preparing Spring Boot and access permissions

### 2.1. Dependencies and configuration

With Maven, import the Spring Cloud AWS BOM and add the S3 starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
</dependencies>
~~~

The project must declare `spring-cloud-aws.version` according to the compatibility matrix for the Spring Boot version in use. The starter configures AWS SDK clients via Spring Boot auto-configuration; the examples below use the `S3Client` bean directly so each request is clearly visible.

~~~yaml
# application.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1

app:
  storage:
    bucket: ${S3_BUCKET_NAME}
    prefix: documents/
~~~

`app.storage.*` is custom application-defined configuration. The example bucket `training-private-docs` must exist in the appropriate Region, and `S3_BUCKET_NAME` must be provided in the runtime environment. Do not hard-code access keys/secret keys in YAML: the AWS SDK uses the **default credentials provider chain**, so use an IAM role/workload identity when deploying; when studying on a personal machine, you can use a valid AWS profile or temporary credentials.

### 2.2. Minimal IAM permissions for a prefix

The following policy allows the service only to list and read/write/delete under `documents/`. Replace the sample bucket with a bucket in your test account:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListDocumentPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::training-private-docs",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["documents/", "documents/*"]
        }
      }
    },
    {
      "Sid": "ManageDocumentObjects",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::training-private-docs/documents/*"
    }
  ]
}
~~~

`s3:ListBucket` applies to the **bucket ARN**; GET/PUT/DELETE require the **object ARN**. The `s3:prefix` condition controls LIST, not GET/PUT/DELETE; the boundary for those three operations is in the object ARN. If the service does not actually have a delete feature, remove `s3:DeleteObject` from the role. If using SSE-KMS, also consider permissions on the KMS key. Bucket policies, SCPs, explicit denies, and other security conditions can still cause requests to be rejected.

## 3. Building an S3 service with AWS SDK v2

The example below uses the **synchronous client** `S3Client`, backend-generated keys on upload, and the `documents/` prefix. Four methods correspond to PUT/GET/LIST/DELETE; `head` is included to read metadata.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Request;
import software.amazon.awssdk.services.s3.model.ListObjectsV2Response;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class DocumentS3Service {
    private static final String PREFIX = "documents/";
    private final S3Client s3;
    private final String bucket;

    public DocumentS3Service(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    // Upload a new object and return the key to store in the business database.
    public String upload(
            InputStream content, long exactSize, String contentType) {
        if (exactSize < 0) {
            throw new IllegalArgumentException("Size must be >= 0");
        }

        String key = PREFIX + UUID.randomUUID();
        String safeType = (contentType == null || contentType.isBlank())
                ? "application/octet-stream" : contentType;

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(safeType)
                .build();

        s3.putObject(request,
                RequestBody.fromInputStream(content, exactSize));
        return key;
    }

    // GET and stream progressively to the caller-provided stream.
    public void downloadTo(String trustedKey, OutputStream destination)
            throws IOException {
        ensureDocumentKey(trustedKey);

        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build();

        try (ResponseInputStream<GetObjectResponse> source =
                     s3.getObject(request)) {
            source.transferTo(destination);
        }
    }

    // HEAD returns metadata without downloading content.
    public HeadObjectResponse head(String trustedKey) {
        ensureDocumentKey(trustedKey);
        return s3.headObject(HeadObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build());
    }

    // LIST exactly one page. An empty nextToken means the first page.
    public ListObjectsV2Response listPage(
            String nextToken, int pageSize) {
        if (pageSize < 1 || pageSize > 1000) {
            throw new IllegalArgumentException(
                    "pageSize must be between 1 and 1000");
        }

        ListObjectsV2Request.Builder request =
                ListObjectsV2Request.builder()
                        .bucket(bucket)
                        .prefix(PREFIX)
                        .maxKeys(pageSize);

        if (nextToken != null && !nextToken.isBlank()) {
            request.continuationToken(nextToken);
        }

        return s3.listObjectsV2(request.build());
    }

    // Delete the current object by key.
    public void delete(String trustedKey) {
        ensureDocumentKey(trustedKey);
        s3.deleteObject(DeleteObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build());
    }

    private static void ensureDocumentKey(String key) {
        if (key == null || !key.startsWith(PREFIX)
                || key.length() <= PREFIX.length()) {
            throw new IllegalArgumentException("Key is outside documents/");
        }
    }
}
~~~

**Requirements for using the code properly:**

- The upload `InputStream` must remain open when `putObject` is called. The caller owns and closes the input stream; the service closes the stream it opens to read S3 inside `downloadTo`.
- `RequestBody.fromInputStream(content, exactSize)` requires the **exact byte size**. If an incorrect byte count is provided, the upload may be truncated, rejected, or fail. For streams of unknown size or large files, choose an appropriate upload strategy instead of guessing the byte count.
- `contentType` in the example is the passed-in value; production systems must verify the actual file format, filename, size, permissions, and suspicious content before accepting uploads.
- `trustedKey` must only be obtained after an **authorization** step using business data. The prefix check inside the service is a basic guard, not proof that a user has access to that object.
- `S3Client` is injected and reused. Avoid creating a new client for each HTTP request.
- DELETE does not return object content; to respond with a business-level 404, the backend must verify the **document record and access permissions** in its own system.

The following sections explain why each method is designed this way.

## 4. Uploading objects: PUT

### 4.1. What information goes into an S3 upload request?

A typical PUT request requires:

- The target **bucket**, such as `training-private-docs`.
- The **object key** inside the bucket, such as `documents/7c1d...`.
- The **byte content** and exact byte length when using a synchronous input stream via `fromInputStream`.
- Appropriate **metadata** such as `Content-Type`, `Content-Disposition`, `Cache-Control`, or custom metadata.
- **Credentials and IAM permissions** for `s3:PutObject`.

Example uploading small text directly from a byte array:

~~~java
byte[] payload = "Hello from Spring Boot"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

var putResult = s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key("documents/demo.txt")
                .contentType("text/plain; charset=UTF-8")
                .metadata(java.util.Map.of("source", "lesson-003"))
                .build(),
        RequestBody.fromBytes(payload));

System.out.println(putResult.eTag());
~~~

`RequestBody.fromBytes` is simple but holds the entire payload in RAM; it is only suitable for small files. If you upload again to the **same key**, S3 updates the current content; in a versioning-enabled bucket, older versions may still be retained.

**Safe key generation:** the backend can use `documents/{opaqueId}/{UUID}` or generate a random UUID. Do not append the client-submitted `originalFilename` directly into the key as a security mechanism, because filenames can collide, contain sensitive data, or include characters requiring sanitization. S3 keys have a UTF-8 byte length limit; prefixes are a naming convention rather than physical folders.

### 4.2. Uploading from a Spring MVC endpoint

In an application with Spring Web, a controller can pass a `MultipartFile` to the service. This example only illustrates the file path; in a real system, **authentication, authorization, size limits, and content validation** are required before the upload step.

~~~java
import java.io.IOException;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
public class DocumentUploadController {
    private final DocumentS3Service storage;

    public DocumentUploadController(DocumentS3Service storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, String> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("Empty file");
        }

        try (var input = file.getInputStream()) {
            String key = storage.upload(
                    input, file.getSize(), file.getContentType());
            // In a real application, save the key along with owner/tenant in the database.
            return Map.of("key", key);
        }
    }
}
~~~

`MultipartFile.getSize()` provides the byte count for the received upload part; the web server and Spring MVC must also be configured with appropriate **max-file-size/max-request-size** limits. When an API accepts uploads from external users, you must also decide allowed file types, scan content per policy, and handle cases where the S3 upload succeeds but the database transaction fails.

### 4.3. When is multipart upload needed?

S3 multipart upload splits a large object into parts, uploads them, and completes by assembling the parts on S3. Consider it when:

- The file is large, uploaded over an unreliable connection, or needs parallel uploads.
- You need per-part retries instead of re-transmitting the entire object.
- You need to avoid loading the whole object into backend RAM.

In AWS SDK v2, you can use **S3 Transfer Manager** (paired with an appropriate async/transfer client) or invoke the multipart APIs directly. If orchestrating multipart yourself, the application must handle **CompleteMultipartUpload** once all parts are uploaded and **AbortMultipartUpload** when abandoning an upload session to avoid incurring storage charges for incomplete parts. For browser/mobile clients, another approach is for the backend to verify permissions and issue a short-lived PUT/multipart **presigned URL** so the client uploads directly to S3.

### 4.4. Controlling overwrites

If a key already exists, a normal PUT to the same key updates the current content. To prevent two requests from accidentally overwriting each other, you can:

1. Generate a new key per UUID and record the key in the database along with the document record.
2. Use **conditional writes** (for example `If-None-Match: *` when supported by the API/SDK) if business rules require creating the object only when the key does not yet exist.
3. Enable S3 Versioning if content history must be preserved.
4. Design a dedicated **idempotency key** for the business request if clients may retry after timeouts.

Do not simply call HEAD followed by PUT and assume the object will not be created between those two calls; that is a **race condition** under concurrent requests.

## 5. Downloading objects: GET and HEAD

### 5.1. Streaming GET

`getObject` lets you receive content via `ResponseInputStream<GetObjectResponse>`. Use try-with-resources to close the stream even when the connection fails:

~~~java
GetObjectRequest request = GetObjectRequest.builder()
        .bucket(bucket)
        .key("documents/demo.txt")
        .build();

try (var source = s3.getObject(request);
     var destination = java.nio.file.Files.newOutputStream(
             java.nio.file.Path.of("downloaded-demo.txt"))) {
    source.transferTo(destination);
}
~~~

The example above suits a **local file download** in a practice program. In a web API, you typically stream content to the HTTP response or issue a time-limited presigned GET URL without creating a local file.

If returning a file via Spring MVC, set appropriate HTTP response headers such as `Content-Type`, `Content-Disposition`, and length from trusted metadata; avoid passing through dangerous client-supplied headers/filenames directly. If the object is very large, the API should stream in chunks or let the client download directly from S3.

### 5.2. HEAD to fetch metadata only

~~~java
var info = s3.headObject(HeadObjectRequest.builder()
        .bucket(bucket)
        .key("documents/demo.txt")
        .build());

System.out.println("Type: " + info.contentType());
System.out.println("Size: " + info.contentLength());
System.out.println("ETag: " + info.eTag());
System.out.println("Version: " + info.versionId());
~~~

HEAD is suitable when you need size, content type, version ID, and selected metadata without downloading the body. However, HEAD is still an **S3 request**, requiring proper permissions, adding latency, and incurring request charges.

**Be careful with HTTP 403/404:** when accessing a non-existent key, S3 can return **404** if the caller has `s3:ListBucket`, or **403** if lacking bucket listing permission. A 403 error can also come from a denying policy or KMS. Therefore, you cannot conclude an object definitely exists merely because you received a 403.

### 5.3. Downloading a byte range

When handling large files, media, or resumable downloads, S3 supports **HTTP Range**. For example, requesting the first 1,024 bytes:

~~~java
var rangeRequest = GetObjectRequest.builder()
        .bucket(bucket)
        .key("documents/large-object.bin")
        .range("bytes=0-1023")
        .build();

try (var part = s3.getObject(rangeRequest)) {
    byte[] firstBytes = part.readAllBytes(); // Read only the requested range.
    System.out.println(firstBytes.length);
}
~~~

In some cases S3 may return fewer bytes than requested due to object size, or return an error if the range is invalid; the client must inspect the response. `Range` is a GET feature, distinct from **part number** in multipart uploads.

### 5.4. Presigned GET URL

Instead of routing many gigabytes through Spring Boot, the backend can authenticate the user, map `documentId` to a key, and generate a short-lived **presigned GET URL**. This URL allows whoever holds it to perform the signed request within its validity window; avoid logging it and avoid sharing it externally.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant A as Spring Boot API
    participant DB as Business database
    participant S3 as Private S3 bucket

    U->>A: Request to download documentId=42
    A->>DB: Check owner/tenant and fetch key
    DB-->>A: Valid permission + key
    A-->>U: Short-lived presigned GET URL
    U->>S3: GET using signed URL
    S3-->>U: Object content
~~~

A presigned URL **does not turn a bucket public**. It represents the permissions of the signing identity and should only be issued after a business authorization check; URL expiration is also bounded by the lifetime of the credentials used to sign it.

## 6. Listing objects: LIST and pagination

### 6.1. How does LIST work?

`ListObjectsV2` returns a **summary list of objects** in a bucket, optionally filtered by prefix:

~~~text
documents/2026/invoice-001.pdf
documents/2026/invoice-002.pdf
documents/2025/invoice-100.pdf
images/avatar-101.png
~~~

With prefix `documents/2026/`, LIST returns only keys starting with that string. The `/` in keys is merely a conventional delimiter character; the bucket has no mandatory physical folder structure.

~~~java
var response = s3.listObjectsV2(
        ListObjectsV2Request.builder()
                .bucket(bucket)
                .prefix("documents/2026/")
                .maxKeys(100)
                .build());

for (var object : response.contents()) {
    System.out.println(object.key()
            + " | " + object.size()
            + " bytes");
}
~~~

Returned `S3Object` items contain summary properties such as key, size, last modified, and ETag; they **do not contain the object body** and do not provide full user metadata like HEAD. Do not use LIST to search by text content or arbitrarily filter on custom metadata; applications should use a separate database/index for business queries.

### 6.2. Handling pagination properly

Each LIST page has a key limit; requests typically use `maxKeys` (up to 1,000 in the `ListObjectsV2` API). If more data remains, S3 returns `nextContinuationToken`. Do not confuse this token with an **object key** or assume you can compute the next page's token.

Using `listPage` in the service:

~~~java
String token = null;

do {
    var page = storage.listPage(token, 100);

    for (var entry : page.contents()) {
        System.out.println(entry.key());
    }

    token = page.nextContinuationToken();
} while (token != null);
~~~

`nextContinuationToken()` is the cursor for retrieving the next batch. In a real API, return **one page + nextToken** to the client and cap `pageSize` instead of trying to read the entire bucket in a single HTTP request.

AWS SDK v2 also supports paginators:

~~~java
var request = ListObjectsV2Request.builder()
        .bucket(bucket)
        .prefix("documents/")
        .maxKeys(100)
        .build();

for (var page : s3.listObjectsV2Paginator(request)) {
    for (var object : page.contents()) {
        System.out.println(object.key());
    }
}
~~~

Paginators are convenient for batch jobs, yet still issue **multiple network requests** and can take a long time if a bucket has many objects. Bound the number of pages, execution duration, or number of keys processed per use case.

### 6.3. Prefix and delimiter

Adding `delimiter("/")` to `ListObjectsV2` groups keys into `CommonPrefixes`, simulating a directory-level listing:

~~~java
var response = s3.listObjectsV2(
        ListObjectsV2Request.builder()
                .bucket(bucket)
                .prefix("documents/")
                .delimiter("/")
                .build());

response.commonPrefixes().forEach(
        p -> System.out.println(p.prefix()));
~~~

`CommonPrefixes` is simply a grouping by key string, not a real folder type. When using a delimiter, the returned item count can include both keys and prefix groups; make sure you understand `contents()`, `commonPrefixes()`, pagination, and `keyCount()`.

### 6.4. Consistency, ordering, and user experience

S3 provides **strong read-after-write consistency** for PUT/DELETE and subsequent GET/LIST calls after an operation succeeds. However, paginating across multiple requests is **not a transactional snapshot**: objects can be added or deleted between pages, so applications must design how to handle concurrent modifications.

Do not assume lexicographical key ordering applies uniformly to every bucket type without checking the bucket features in use; for instance, directory buckets differ from general-purpose buckets. If the UI needs a list sorted by creation date, payment status, or owner, query the **business database** rather than relying on S3 LIST order.

## 7. Deleting objects: DELETE and Versioning

### 7.1. DELETE without versioning

~~~java
s3.deleteObject(DeleteObjectRequest.builder()
        .bucket(bucket)
        .key("documents/demo.txt")
        .build());
~~~

For a bucket without versioning enabled, deleting the current object by key is an action that must be protected. Standard `DeleteObject` is **idempotent in the sense of a key-deletion request**: the server can return success even when the key no longer exists. Therefore, do not rely solely on `deleteObject` succeeding to infer that data existed previously.

### 7.2. DELETE when versioning is enabled

If **Versioning** is enabled:

- A PUT to the same key normally creates a new version.
- A DELETE **without specifying a version ID** normally inserts a **delete marker** and makes the object appear deleted in the default view.
- Data from previous versions can still exist and incur storage charges.
- Permanently deleting a specific version requires specifying the version ID and having the appropriate permission (such as `s3:DeleteObjectVersion`). This is a separate operation requiring controlled workflows.

~~~text
Versioning-enabled bucket:

PUT key=documents/a.txt   → version v1
PUT key=documents/a.txt   → version v2 (current)
DELETE documents/a.txt    → delete marker (current)
GET documents/a.txt       → usually does not see a current object
GET version v1/v2         → still accessible if permitted
~~~

In a bucket with **suspended versioning**, null versions and delete markers follow their own rules; do not describe all buckets with history as behaving identically to the example above. Settings such as **Object Lock**, retention policies, or legal holds can prevent deleting versions even when the role has S3 permissions.

### 7.3. Safe deletion workflow in an application

When a user wants to delete a document, a typical workflow is:

1. Authenticate the user, look up the record by `documentId`, and check delete permissions.
2. Decide by business rules whether to perform a **soft delete**, delete the current object, or permanently delete data per retention policy.
3. Record a business state (such as `DELETING`) and execute the deletion via a worker or outbox if retry capability is needed.
4. Update the record when the S3 operation succeeds; monitor and handle errors for any remaining steps.
5. For versioned data, decide how to handle old versions, lifecycle rules, retention, and cost.

**S3 and the database do not share an ACID transaction.** You cannot assume both roll back if one step fails. When strong business consistency is required, use a state machine, outbox, controlled retries, and idempotency instead of trying to hide that deletion occurs outside the database transaction.

### 7.4. Deleting multiple objects

The AWS SDK supports `DeleteObjects` to send multiple keys in a single request within API limits. When batch deleting:

- Check **each error entry** in the response; HTTP-level success does not guarantee all keys were deleted.
- With versioning, be explicit about whether you are deleting from the current view or targeting specific versions.
- Split batches within API limits, apply controlled retries, and avoid deleting by an untrusted client-supplied prefix.
- Write business audit logs for bulk operations if required by the system.

Demonstrating batch delete as an unverified "delete entire prefix" operation is discouraged, especially in shared environments.

## 8. Error handling and retries

S3 APIs can raise errors from the SDK, HTTP layer, IAM permissions, configuration, or network.

| Symptom | Likely cause | How to handle |
| --- | --- | --- |
| 403 `AccessDenied` | Missing IAM permission, bucket policy deny, SCP, KMS, endpoint policy | Check action, bucket/object ARN, and effective policies |
| 404 `NoSuchKey` on GET | Key does not exist or is hidden by a current delete marker | Verify key and business state; do not guess from stale LIST results |
| 403 on HEAD for non-existent key | Caller lacks LIST permission to distinguish missing keys | Do not use 403 to assert a key exists |
| Redirect/Region mismatch | Client targets the wrong bucket Region | Check bucket Region and SDK config |
| `SlowDown`/throttling or 5xx errors | High load or transient service condition | Bounded backoff and retry |
| Upload size mismatch | `Content-Length` does not match actual stream | Supply exact byte size; avoid guessing |
| Browser does not download file as expected | Incorrect `Content-Type` or `Content-Disposition` | Fix metadata and HTTP headers |
| Slow LIST | Bucket has many objects, iterating all pages | Narrow prefix, tune maxKeys, and use a business index |

Example of catching S3 errors for safe logging:

~~~java
try {
    storage.head(trustedKey);
} catch (software.amazon.awssdk.services.s3.model.S3Exception ex) {
    // Log operation, AWS requestId, and error code; avoid logging credentials/signed URLs.
    System.err.println("S3 HEAD failed, status=" + ex.statusCode()
            + ", requestId=" + ex.requestId());
    throw ex;
}
~~~

**Do not retry every operation unconditionally:** retrying GET/HEAD/LIST on transient errors is usually straightforward; retrying PUT with a fixed key, DELETE, or operations with side effects requires evaluating idempotency and versioning policies. The AWS SDK already has built-in retry strategies; adding extra application-level retries without understanding SDK behavior can multiply call counts unexpectedly.

## 9. Integration testing Spring Boot with S3

To learn provider integration thoroughly, test both **Java code** and **managed-service permissions and behavior**.

| Testing level | What it verifies | Limitations |
| --- | --- | --- |
| Unit test with mocked `S3Client` | Key generation, request parameters, business checks before GET/DELETE | Does not prove real S3 APIs or IAM work |
| Integration test with S3 emulator | PUT → HEAD → GET → LIST → DELETE, streaming, and pagination | Emulators do not necessarily replicate IAM, KMS, versioning, or consistency accurately |
| Integration test on AWS sandbox | Real role, private bucket, Region, SSE-KMS, versioning, and access failures | Creates resources/costs; requires cleaning up test data |

### Test scenario for an object

~~~mermaid
flowchart TD
    A["Generate random key under test/"] --> B["PUT sample content"]
    B --> C["HEAD: size + Content-Type"]
    C --> D["GET: compare bytes"]
    D --> E["LIST by prefix + pagination"]
    E --> F["DELETE key"]
    F --> G["Verify current state"]
    G --> H["Clean up test data/versions"]
~~~

Example of test verification logic:

~~~java
String key = storage.upload(
        new java.io.ByteArrayInputStream("abc".getBytes(
                java.nio.charset.StandardCharsets.UTF_8)),
        3L,
        "text/plain");

var metadata = storage.head(key);
if (metadata.contentLength() != 3L) {
    throw new AssertionError("Unexpected object size");
}

var target = new java.io.ByteArrayOutputStream();
storage.downloadTo(key, target);

if (!java.util.Arrays.equals(
        target.toByteArray(),
        "abc".getBytes(java.nio.charset.StandardCharsets.UTF_8))) {
    throw new AssertionError("Downloaded content does not match");
}

storage.delete(key);
~~~

The snippet above illustrates end-to-end logic; in real tests, use an assertion framework, dedicated sandbox resources, `finally`/teardown cleanup, and proper handling when versioning is enabled. Avoid using production buckets for integration tests. Do not run delete tests against real user keys.

### Negative cases to include

- PUT with a stream whose declared size is wrong or whose file exceeds application limits.
- GET/DELETE on a key not authorized by the application, even though the backend role can access it.
- Paginated LIST when more than 1,000 objects exist and when the prefix is empty.
- HEAD on a non-existent key with a role that has vs. lacks `s3:ListBucket`.
- Re-PUTting the same key to observe overwrites and how versioning preserves history.
- Transient failures and retries when the app loses network connectivity mid-upload/download.

## 10. Comparison with Azure Blob Storage and Google Cloud Storage

When building a module that integrates multiple cloud providers, business operations are often equivalent while APIs, identities, and permission models differ.

| Need | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Upload | `PutObject` | Upload blob | Upload/create object |
| Download | `GetObject` | Download blob | Read object |
| List | `ListObjectsV2` with prefix + continuation token | List blobs with continuation | List objects with paging |
| Delete | `DeleteObject` | Delete blob | Delete object |
| Identification | Bucket + object key | Storage account + container + blob name | Bucket + object name |
| Identity | IAM role/SDK credentials | Managed identity/Azure RBAC | Service account/Google IAM |
| Short-lived URL | Presigned URL | SAS | Signed URL |

Business workflows can use an application-specific abstraction:

~~~java
public interface ObjectStoragePort {
    String upload(InputStream source, long length, String mediaType);

    void downloadTo(String objectKey, OutputStream destination)
            throws IOException;

    void delete(String objectKey);
}
~~~

This is an illustrative contract; listing, metadata, versioning, and error mapping may need separate interfaces if clouds differ semantically. An AWS adapter implements it with `S3Client` or `S3Template`, while Azure/GCP adapters use their respective provider SDKs. **Do not assume** all providers share identical policy models, pagination tokens, delete semantics, or Spring configuration property names.

## 11. Practice exercises

**Exercise 1 — Basic PUT/GET.** In a private sandbox bucket, create an endpoint accepting a small text file. The backend generates a UUID key, uploads to S3, and saves the key in a test document table. Download it back by business ID (after checking permissions) and compare content hashes. Explain why you should never return an arbitrary user-requested key.

**Exercise 2 — Metadata and streaming.** Upload a file larger than a few MB via streaming, setting an appropriate `Content-Type`; call HEAD to verify `Content-Length`. Compare memory usage between `RequestBody.fromBytes` and a streaming design, and explain when multipart should be used.

**Exercise 3 — Multi-page listing.** Create multiple objects under `documents/lab-<uuid>/`, and use `maxKeys=10` to iterate across pages. Inspect `nextContinuationToken` and test `delimiter("/")`. Explain why LIST is not a business-metadata search API.

**Exercise 4 — DELETE and Versioning.** In a dedicated test bucket, enable versioning, PUT twice to the same key, and then DELETE without a version ID. Observe the delete marker and previous versions. Clarify the condition for granting `s3:DeleteObjectVersion` if you want to clean up test versions.

**Exercise 5 — Permission boundaries.** Create a role with only `s3:GetObject`, then attempt LIST and DELETE. Record the errors. Next, compare with a role granted `s3:ListBucket` for the prefix and GET/PUT/DELETE on the corresponding object ARN.

### Self-check questions

1. Distinguish between a new PUT and a PUT to an existing bucket/key.
2. Why does `RequestBody.fromInputStream` require an exact byte size?
3. Why must `ResponseInputStream` be closed after GET?
4. How does `HEAD` differ from `GET` and `LIST` in returned data and IAM permissions?
5. Is `nextContinuationToken` an object key or a page number?
6. What does a DELETE without a version ID do when the bucket has Versioning enabled?
7. Why does a successful DELETE result not prove the object existed beforehand?
8. How do you avoid an S3 deletion succeeding while the database update fails?
9. Why should the application check user permissions even when the IAM role already allows `s3:GetObject`?
10. Which verifications are missing from local emulator tests and should be performed on a real AWS sandbox?

By the end of this lesson, you can implement and explain the **PUT → HEAD/GET → LIST → DELETE** flow in Spring Boot, understand the semantics of each S3 operation, and design the safety boundaries needed when introducing object storage into systems with real data.
