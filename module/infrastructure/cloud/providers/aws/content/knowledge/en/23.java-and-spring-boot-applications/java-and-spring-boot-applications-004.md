# Application File Storage with S3

A Spring Boot application lets users upload avatars, PDF invoices, contract documents, or videos. Storing all bytes on a container's local disk risks data loss when pods/tasks are replaced, makes sharing across instances difficult, and forces the application server to act as storage. **Amazon S3** solves this with scalable, highly durable object storage that integrates directly with IAM, KMS, CloudWatch, EventBridge, and other AWS services.

In Java architectures, applications typically store **object keys and business metadata in a database**, while object bytes live in an S3 bucket. The backend can upload/download via the **AWS SDK for Java 2.x**, or issue a **presigned URL** so browsers/mobile clients transfer files directly to S3. For large files, **multipart upload** and **S3 Transfer Manager** boost throughput, support per-part retries, and avoid routing all bytes through the API server.

This lesson belongs to the **Java and Spring Boot Applications** chapter of the **CLOUD_PROVIDERS_AWS** module. It connects Regions/AZs, IAM, VPCs, compute, databases, serverless, monitoring, resilience, and cost control. Examples use Java 17+, Spring Boot, AWS SDK for Java 2.x, and a private bucket in an externally configured Region.

> **Design principle:** S3 stores **object bytes**; the database stores **ownership and business state**; Spring Boot authenticates users, determines object keys, and orchestrates uploads/downloads. Never use client-supplied filenames as storage paths, never make a bucket public to serve private files, and never hold large files in RAM just to relay them.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain S3 buckets, objects, keys, metadata, tags, versions, and storage classes.
2. Design safe object keys for multi-tenant Spring Boot applications.
3. Integrate AWS SDK for Java 2.x using the Maven BOM and Spring dependency injection.
4. Upload/download objects with `S3Client` and handle streams safely.
5. Enforce size limits, validate MIME/file signatures, and verify access permissions.
6. Distinguish backend-proxied uploads from direct uploads using presigned URLs.
7. Generate presigned GET/PUT URLs and manage expiration, signed headers, and signer permissions.
8. Choose between single PUT, multipart upload, and S3 Transfer Manager based on size/workload.
9. Protect data integrity with checksums; understand why ETag is not always MD5.
10. Design DB metadata, idempotency, upload states, and S3/DB reconciliation.
11. Configure least-privilege IAM, Block Public Access, Object Ownership, SSE-S3/SSE-KMS, TLS, and CORS.
12. Apply Versioning, Lifecycle, replication, backups, and storage classes.
13. Integrate S3 events, SQS/EventBridge/Lambda, and handle duplicate/out-of-order delivery.
14. Observe, troubleshoot, and optimize S3 costs in production.

## 2. File storage architecture in Spring Boot

~~~mermaid
flowchart TD
    USER["Browser / Mobile"] --> API["Spring Boot API"]
    API --> AUTH["Authentication + authorization"]
    AUTH --> DB[("RDS / DynamoDB<br/>File metadata + ownership")]
    API --> SDK["AWS SDK for Java 2.x"]
    SDK --> S3[("Private S3 bucket<br/>Objects / versions")]
    API --> PRESIGN["S3Presigner"]
    PRESIGN -->|"Short-lived URL"| USER
    USER -->|"Direct PUT / GET"| S3
    S3 --> EVT["S3 Event / EventBridge"]
    EVT --> Q["SQS / Lambda / scanner"]
    Q --> DB
~~~

There are two main flows:

- **Backend proxy:** the browser sends a multipart request to Spring Boot; the backend validates it and uploads to S3. Easy to govern requests and fits small/medium files, but the API server bears bandwidth, connection, and disk/RAM pressure.
- **Direct-to-S3:** the backend authenticates, creates a metadata record, and issues a presigned URL; the browser uploads/downloads directly with S3. The backend avoids transferring all bytes, fitting large files or high client concurrency.

In both models, the database maintains records such as `fileId`, `tenantId`, `objectKey`, `originalFilename`, `contentType`, `size`, `checksum`, `status`, `createdAt`, `uploadedAt`. **Do not store file bytes in the DB just because the application uses a relational database**, unless a specialized, evaluated requirement demands it.

### 2.1. Component responsibilities

| Component | Responsibility |
|---|---|
| Spring Controller | Accepts HTTP requests, validates request boundaries, returns responses |
| Authentication/authorization | Identifies user, tenant, and upload/download permissions |
| File service | Generates keys, validates metadata, orchestrates state transitions |
| S3 SDK client | Invokes Put/Get/Head/Delete/List/Copy |
| S3Presigner | Creates temporary URLs scoped to an HTTP method and key |
| S3 bucket | Stores bytes, versions, encryption, lifecycle rules |
| Database | Stores owner, tenant, file status, object key, and business metadata |
| SQS/EventBridge/Lambda | Malware scanning, thumbnail generation, indexing, post-upload processing |
| CloudWatch/CloudTrail | Observes requests, errors, access, and configuration changes |

Do not create buckets on every user upload. Buckets and security settings should be provisioned via IaC (CloudFormation/CDK/Terraform) or a controlled platform workflow; the application operates only on configured buckets.

## 3. S3 object model: bucket, key, and metadata

S3 is **object storage**. An object consists of data, a key, metadata, tags, a version ID, and attributes such as storage class/encryption. Bucket names must be unique within the appropriate namespace; keys identify objects inside a bucket.

~~~text
Bucket: company-private-files-prod
Key:    tenants/tenant-42/invoices/2026/11/01JAZ...pdf
Object: bytes + system metadata + user metadata + tags + version
~~~

### 3.1. Keys are not filesystem paths

S3 has no true directories with filesystem semantics. `/` characters in keys merely organize prefixes and render as folders in the console. A key is a case-sensitive string with specific character/encoding rules.

Do not build keys by direct concatenation:

~~~java
String key = "uploads/" + multipartFile.getOriginalFilename();
~~~

`getOriginalFilename()` comes from the client and can include path segments, special characters, duplicate names, or misleading filenames. Generate keys server-side:

~~~java
String key = "tenants/" + tenantId
        + "/files/" + UUID.randomUUID();
~~~

If you need to preserve the original filename, store it separately in the database or sanitized metadata. Display names are not object identities.

### 3.2. Prefixes and multi-tenancy

A key convention might look like:

~~~text
tenants/{tenantId}/uploads/{yyyy}/{MM}/{fileId}
~~~

- `tenantId` comes from the authenticated security principal, never trusted from a browser-submitted field.
- `fileId` is a server-generated UUID/ULID.
- Do not allow users to pick arbitrary prefixes if cross-tenant read/write risk exists.
- IAM can restrict access by prefix using policy conditions when designed properly, though per-file authorization should still be enforced in the application.
- With massive object counts, avoid creating hot prefixes with fixed key patterns if the workload needs distribution; measure request distribution before designing sharding.

### 3.3. Metadata, tags, and database records

| Storage location | Used for | Characteristics |
|---|---|---|
| System metadata | Content-Type, Content-Length, Last-Modified, ETag, storage class | Managed by S3 |
| User metadata | `x-amz-meta-*`, upload ID, source | Attached at upload; changing metadata usually requires copying the object |
| Object tags | Categorizing retention/cost/access workflows | Updatable independently via the tagging API |
| Application DB | Owner, tenant, original name, status, scan result, business links | Business queries, authorization, and auditing |

Do not stuff entire business records into user metadata. Metadata is no replacement for database indexes, has size limits, and is poorly suited for multi-attribute queries.

### 3.4. An object key can be overwritten

`PutObject` to the same key replaces the existing object (when versioning is off) or creates a new version (when versioning is on). Thus, unique server-generated keys per file ID are safer than keys based on `avatar.jpg` or `invoice.pdf`.

If business logic needs to “replace a file,” consider creating a new file record/version or using S3 Versioning and storing `versionId` in the DB. Never inadvertently let a presigned PUT overwrite an existing object without a policy.

## 4. Choosing an upload model: backend proxy vs. direct-to-S3?

| Criterion | Backend proxy | Presigned direct upload |
|---|---|---|
| Bytes travel via | Browser → Spring → S3 | Browser → S3 |
| Backend network load | Higher | Lower |
| Upload control | Easy to validate/scan before sending | Pre-validation and post-upload verification |
| Large files | Needs streaming/temp disk or transfer manager | Well-suited; multipart can use client/transfer flow |
| Browser IAM credentials | Not needed | Not needed; URL carries a temporary signature |
| Implementation effort | Fewer moving parts | Requires upload session/finalize workflow |
| CORS | Usually no S3 CORS needed if browser only calls API | Requires appropriate CORS for cross-origin browsers |
| Use case | Small/medium files, server-enforced policies | Large files, many clients, offloading backend bandwidth |

No single file-size threshold fits every application. Choose based on file size distribution, throughput, server bandwidth, latency, validation requirements, networking, and cost.

## 5. Configuring Spring Boot multipart uploads

Spring MVC uses a multipart resolver to accept `MultipartFile`. Enforce size limits at the **application layer**, reverse proxy/load balancer, and gateway if present.

### 5.1. Application properties

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=20MB
spring.servlet.multipart.max-request-size=21MB
spring.servlet.multipart.file-size-threshold=1MB
~~~

These values are examples for small/medium upload endpoints. `max-file-size` limits a single file, while `max-request-size` limits the total multipart request. `file-size-threshold` determines when multipart content spills to temporary disk per servlet container configuration. Align limits consistently with ingress/API Gateway, disk capacity, and business policies.

### 5.2. MultipartFile does not always mean the file stays in RAM

Depending on the servlet container/configuration, the multipart resolver may hold small parts in memory and write larger ones to temporary disk. Therefore:

- Avoid `multipartFile.getBytes()` on large files because it allocates the entire byte array on the heap.
- Prefer `getInputStream()` and close streams properly.
- Verify size before uploading and ensure accurate stream length when using APIs requiring content length.
- Clean up temp files if creating intermediate files manually.
- Bound concurrent uploads and request durations; slow uploads can tie up HTTP connections/threads.

### 5.3. Validating files before saving

Client-supplied `Content-Type`, extensions, and original filenames **cannot be trusted**. Combine:

1. Allowlisting allowed file types per use case (PDF, JPEG, PNG, etc.).
2. Checking normalized extensions and sniffing MIME types from bytes/magic signatures.
3. Enforcing size, page count/resolution/duration limits if required by business rules.
4. Scanning for malware with an appropriate service before making files public/downloadable.
5. Guarding against archive bombs, polyglot files, HTML/script uploads, and path traversal.
6. Holding files in a quarantine/pending state until scanning finishes.
7. Never rendering user-uploaded HTML/SVG inline on the same application origin without sanitization.

Browser-side validation only improves UX; the backend must enforce mandatory checks.

## 6. Uploading small/medium files with AWS SDK for Java 2.x

Use `S3Client` and `RequestBody` to upload from a `Path`, `File`, or `InputStream`. The example below uses `MultipartFile` for size-bounded files in Spring.

### 6.1. Maven dependencies

AWS SDK v2 should use the BOM as covered earlier. Declare the `s3` service module without an individual version once the BOM is imported:

~~~xml
<project>
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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
</dependencies>
</project>
~~~

`aws.sdk.version` should be defined in the parent POM or project properties using an approved version. Never copy an unverified old version into production.

### 6.2. S3Client singleton bean

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class S3Configuration {
    @Bean(destroyMethod = "close")
    S3Client s3Client(@Value("${app.aws.region}") String region) {
        return S3Client.builder()
                .region(Region.of(region))
                .build();
    }
}
~~~

The client uses the default credentials provider chain. On Lambda/ECS/EC2/EKS, attach the appropriate workload IAM role; never put access keys/secret keys in `application.properties`.

### 6.3. Upload service

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class S3FileStorageService {
    private final S3Client s3;
    private final String bucket;

    public S3FileStorageService(
            S3Client s3,
            @Value("${app.s3.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String upload(String tenantId, MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File must not be empty");
        }

        String fileId = UUID.randomUUID().toString();
        String key = "tenants/" + tenantId + "/uploads/" + fileId;

        String contentType = file.getContentType() == null
                ? "application/octet-stream"
                : file.getContentType();

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(contentType)
                .contentLength(file.getSize())
                .metadata(Map.of("file-id", fileId))
                .build();

        try (InputStream input = file.getInputStream()) {
            s3.putObject(request,
                    RequestBody.fromInputStream(input, file.getSize()));
        }

        return key;
    }
}
~~~

This sample illustrates **already size-bounded files**. Before production, validate `tenantId` from the principal and normalize it to a key-safe ID (such as a UUID or allowlisted character set), verify MIME/file signatures, upload permissions, quotas, and metadata; do not trust `getContentType()` as proof of true file type. Persist the file record in the DB following a consistent workflow as described later.

### 6.4. Controller

~~~java
import java.io.IOException;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/files")
public class FileUploadController {
    private final S3FileStorageService storage;

    public FileUploadController(S3FileStorageService storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public UploadResponse upload(@RequestPart("file") MultipartFile file) {
        try {
            // Actual tenantId must be extracted from the authenticated security principal.
            String key = storage.upload("tenant-42", file);
            return new UploadResponse(key);
        } catch (IOException | IllegalArgumentException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload", ex);
        }
    }

    public record UploadResponse(String objectKey) {
    }
}
~~~

`tenant-42` is just a placeholder. Multi-tenant applications must extract tenant/user from the authentication context, check permissions before generating keys, and never accept arbitrary `tenantId` values from request bodies.

## 7. Downloading objects and streaming to HTTP responses

For small/medium files, objects can be retrieved with `GetObject`. For large files, avoid `ResponseBytes.asByteArray()` or loading entire objects into `byte[]`. Use `ResponseInputStream` and stream directly to the HTTP response.

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

@RestController
public class FileDownloadController {
    private final S3Client s3;
    private final FileRepository files;
    private final String bucket;

    public FileDownloadController(
            S3Client s3, FileRepository files,
            @Value("${app.s3.bucket}") String bucket) {
        this.s3 = s3;
        this.files = files;
        this.bucket = bucket;
    }

    @GetMapping("/api/files/{fileId}/content")
    public ResponseEntity<StreamingResponseBody> download(
            @PathVariable String fileId,
            Authentication authentication) {

        // Repository method must verify tenant/owner permissions.
        FileRecord file = files.findAuthorized(fileId, authentication);

        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(file.objectKey())
                .build();

        StreamingResponseBody body = output -> {
            try (ResponseInputStream<GetObjectResponse> input =
                         s3.getObject(request)) {
                input.transferTo(output);
            }
        };

        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(file.contentType()))
                .contentLength(file.size())
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(file.safeDownloadName(),
                                        StandardCharsets.UTF_8)
                                .build().toString())
                .body(body);
    }
}
~~~

This is a controller skeleton: `FileRepository`, `FileRecord`, and authorization are application-specific. Never accept `objectKey` from the client; the client sends `fileId` so the backend looks up an authorized record. For large responses, configure Spring MVC and reverse proxy async executors/timeouts appropriately.

### 7.1. Downloading via presigned GET

If proxying content through Spring is unnecessary, the backend can issue a presigned GET URL after verifying ownership. The browser downloads directly from S3, saving backend bandwidth and threads. The URL acts as a temporary bearer token and must never be recorded in logs, analytics, or sent to unauthorized users.

### 7.2. Range requests and resume

S3 supports reading byte ranges of an object. For media players or large downloads, pass the `Range` header to S3 or use a presigned GET with matching request headers. If the backend proxies requests, forward HTTP `206`, `Content-Range`, and `Accept-Ranges` properly; do not advertise resume support if the controller always downloads the entire object.

### 7.3. Content-Disposition and untrusted content

- Use sanitized filenames in `Content-Disposition`.
- Serve user-uploaded files as `attachment` unless inline display is explicitly required.
- Never concatenate raw filenames into HTTP headers.
- Consider serving user-generated content from a separate domain to mitigate same-origin risks.
- Determine MIME types via validation, not merely extensions or client headers.

## 8. Database metadata and S3/DB consistency

S3 and RDS/DynamoDB do not participate in a single ACID transaction. Therefore, you cannot assume an S3 object upload and a DB metadata write commit or roll back atomically.

A metadata table might look like:

~~~sql
CREATE TABLE stored_files (
    file_id          VARCHAR(36) PRIMARY KEY,
    tenant_id        VARCHAR(100) NOT NULL,
    object_key       VARCHAR(1024) NOT NULL UNIQUE,
    original_name    VARCHAR(255) NOT NULL,
    content_type     VARCHAR(150) NOT NULL,
    content_length   BIGINT NOT NULL,
    checksum_sha256  VARCHAR(128),
    status           VARCHAR(30) NOT NULL,
    s3_version_id    VARCHAR(1024),
    created_at       TIMESTAMP NOT NULL,
    uploaded_at      TIMESTAMP,
    scanned_at       TIMESTAMP
);

CREATE INDEX ix_stored_files_tenant_created
    ON stored_files (tenant_id, created_at);
~~~

This is an illustrative schema; column lengths, timezone handling, encryption, retention, and indexes must reflect business and query patterns.

### 8.1. Backend proxy upload workflow

~~~mermaid
sequenceDiagram
    participant U as User
    participant API as Spring Boot
    participant DB as File metadata DB
    participant S3 as Private S3
    participant SCAN as Malware scanner
    U->>API: POST multipart
    API->>API: Authenticate + validate + quota
    API->>DB: Create PENDING_UPLOAD record
    API->>S3: PutObject / multipart
    S3-->>API: ETag / VersionId / success
    API->>DB: Set UPLOADED_PENDING_SCAN
    API-->>U: fileId + status
    S3-->>SCAN: Object-created event
    SCAN->>S3: Read / scan object
    SCAN->>DB: Set AVAILABLE or REJECTED
~~~

### 8.2. Why are states necessary?

Failure cases:

- DB writes `PENDING` successfully, then S3 upload fails.
- S3 upload succeeds, then DB update times out.
- Upload succeeds, then the scan event is delayed or retried by the consumer.
- The user retries the request and creates a duplicate second object.
- The client disconnects after S3 receives all bytes but before the backend sends a response.

Use a state machine such as:

~~~text
PENDING_UPLOAD
UPLOADED_PENDING_SCAN
SCANNING
AVAILABLE
REJECTED
FAILED
DELETE_PENDING
DELETED
RECONCILIATION_REQUIRED
~~~

Transition to `AVAILABLE` only after the object exists, metadata is verified, and mandatory security checks pass. Never issue presigned GET URLs for files in `PENDING_UPLOAD`, `SCANNING`, or `REJECTED`.

### 8.3. Idempotency and reconciliation

- Upload APIs accept an idempotency key/request ID; the same business request maps to the same `fileId`/object key.
- Generate unique keys server-side rather than minting a new key blindly on every retry.
- If S3 succeeded while the DB lagged, a reconciliation job uses `HeadObject` on the saved key to verify whether the object exists.
- If a DB `PENDING` record expires and the object does not exist, mark it `FAILED` or permit retry per policy.
- If an orphaned object lacks a DB record, cleanup workflows must check ownership/retention before deleting.
- Use outbox/inbox patterns when publishing business events; S3 notifications do not share a transaction with the DB.

**Never delete an object immediately on an API call timeout.** A timeout only means the client did not receive a response; it does not prove S3 failed to complete `PutObject`.

## 9. Direct uploads with presigned PUT URLs

Presigned URLs allow browsers to upload/download private objects for a limited window without needing AWS credentials. The backend signs the URL using an IAM principal authorized for that operation. Anyone holding the URL can execute the signed request until it expires or the signer's credentials become invalid.

### 9.1. Workflow for issuing an upload URL

1. The client calls an API to create an upload session with filename, expected size, content type, and business reference.
2. The backend validates user permissions, quota, file type, and size limits.
3. The backend generates a unique `fileId` and object key, and saves a `PENDING_UPLOAD` record.
4. The backend creates a short-lived presigned PUT URL with required signed headers.
5. The browser PUTs bytes directly to S3.
6. The browser calls a finalize API; the backend runs `HeadObject` to verify key, size, and expected metadata/checksum.
7. The backend transitions the record to `UPLOADED_PENDING_SCAN`; an event/worker scans the file and marks it `AVAILABLE`.

### 9.2. Generating presigned PUT URLs with SDK v2

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.PutObjectPresignRequest;
import software.amazon.awssdk.services.s3.presigner.model.PresignedPutObjectRequest;

@Component
public class S3UploadUrlService {
    private final S3Presigner presigner;
    private final String bucket;

    public S3UploadUrlService(
            S3Presigner presigner,
            @Value("${app.s3.bucket}") String bucket) {
        this.presigner = presigner;
        this.bucket = bucket;
    }

    public String createPutUrl(String objectKey, String contentType) {
        PutObjectRequest putObject = PutObjectRequest.builder()
                .bucket(bucket)
                .key(objectKey)
                .contentType(contentType)
                .build();

        PutObjectPresignRequest presignRequest =
                PutObjectPresignRequest.builder()
                        .signatureDuration(Duration.ofMinutes(10))
                        .putObjectRequest(putObject)
                        .build();

        PresignedPutObjectRequest signed =
                presigner.presignPutObject(presignRequest);

        return signed.url().toExternalForm();
    }
}
~~~

Register `S3Presigner` as a shared bean configured with the same Region and credentials chain as the application, and close it on shutdown. In production, `objectKey` must be generated and authorized by the backend before calling this method. If the signed request includes `Content-Type` or checksum headers, the client PUT must send those exact signed headers.

### 9.3. S3Presigner bean

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration
public class S3PresignerConfiguration {
    @Bean(destroyMethod = "close")
    S3Presigner s3Presigner(
            @Value("${app.aws.region}") String region) {
        return S3Presigner.builder()
                .region(Region.of(region))
                .build();
    }
}
~~~

### 9.4. Browser upload

~~~javascript
const response = await fetch(presignedUrl, {
  method: "PUT",
  headers: {
    "Content-Type": file.type
  },
  body: file
});

if (!response.ok) {
  throw new Error("S3 upload failed: " + response.status);
}
~~~

If `Content-Type` was signed, the actual header must match the value used when generating the URL. The browser needs S3 CORS configured for the corresponding origin/method/headers. CORS is strictly a browser cross-origin policy; **CORS does not replace IAM authorization** and does not make a bucket public.

### 9.5. Limits and protecting presigned URLs

- A presigned URL is a **bearer token**: anyone holding the URL can exercise the signed permissions while it remains valid.
- The URL can be reused multiple times before expiration; a PUT to the same key can overwrite the object.
- Maximum validity depends on credential/signing type; SDK/CLI SigV4 supports up to 7 days, though temporary role credentials often expire sooner. Keep expirations short (e.g., 5–15 minutes) matching the workflow.
- Never log full URLs, leak them to analytics/referrers, or store them in tickets or chat.
- Scope the object key, HTTP method, signed headers, and signer IAM permissions.
- To enforce file size limits in policy, evaluate presigned POST policies with `content-length-range`; simple presigned PUTs do not enforce all POST policy conditions.
- Post-upload, verify size/checksum/content metadata and scan before marking `AVAILABLE`.

### 9.6. Presigned GET URLs

Use `GetObjectPresignRequest` with `GetObjectRequest` and an appropriate duration. Before issuing the URL, the backend must look up `fileId`, check tenant/owner/business permissions, and verify file status. Never let clients send an object key for the backend to sign without authorization.

## 10. Bucket and object security

Buckets storing private files should be **private** by default. Access should be governed via IAM policies, bucket policies, VPC endpoint policies, and AWS Organizations guardrails. Avoid relying on ACLs for new use cases.

### 10.1. Block Public Access and Object Ownership

For new general-purpose buckets, S3 enables **Block Public Access** and **Bucket owner enforced Object Ownership** by default:

- The bucket owner owns all objects in the bucket.
- ACLs are disabled; access is managed through policies.
- PUT requests must not send ACLs such as `public-read`.
- Sending an incompatible ACL when Bucket owner enforced is enabled causes S3 to return `AccessControlListNotSupported`.
- Keep all four Block Public Access settings enabled at the account/bucket level per security baselines; modify only for reviewed public use cases.

### 10.2. Least-privilege IAM for the application role

A role uploading/downloading within an application prefix may need these actions (adjust policy to actual features):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UploadAndReadTenantFiles",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:AbortMultipartUpload",
        "s3:ListMultipartUploadParts"
      ],
      "Resource": "arn:aws:s3:::company-private-files-prod/tenants/*"
    },
    {
      "Sid": "ListOnlyTenantPrefix",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::company-private-files-prod",
      "Condition": {
        "StringLike": {
          "s3:prefix": ["tenants/*"]
        }
      }
    }
  ]
}
~~~

This policy illustrates a multi-tenant role; the application must still enforce tenant/file authorization in the DB. Do not grant `s3:*` or bucket-wide access unnecessarily. Omit `s3:ListBucket` if listing is unused; if using Transfer Manager/multipart, verify required multipart permissions in the IAM reference.

### 10.3. Bucket policy enforcing HTTPS

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::company-private-files-prod",
        "arn:aws:s3:::company-private-files-prod/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
~~~

Denying insecure transport rejects unencrypted HTTP requests. In production systems, bucket policies may add conditions for VPC endpoints, principals, encryption headers, or organization IDs; review carefully so legitimate service integrations are not blocked.

### 10.4. Encryption at rest

S3 automatically encrypts new objects with **SSE-S3** by default. Options include:

| Mode | When appropriate | Notes |
|---|---|---|
| SSE-S3 | Most standard files | S3 manages keys |
| SSE-KMS | Need key policies, auditing, and KMS control | Requires KMS permissions and key lifecycle/cost management |
| DSSE-KMS | Dual-layer encryption required by policy | Higher cost/latency |
| SSE-C | Customer supplies keys per request | Complex key operations; avoid without clear requirements |
| Client-side encryption | Data must be encrypted before reaching S3 | Application manages encryption/decryption/key lifecycle |

With SSE-KMS, the application role may need `kms:GenerateDataKey` on upload and `kms:Decrypt` on download (depending on API/encryption path); the key policy must also permit the principal. Never accept a KMS key ID from client requests. Never store plaintext encryption keys in object metadata or logs.

### 10.5. Bucket CORS for direct browser uploads

Example CORS rule restricted to a specific frontend origin:

~~~xml
<CORSConfiguration>
    <CORSRule>
        <AllowedOrigin>https://app.example.com</AllowedOrigin>
        <AllowedMethod>PUT</AllowedMethod>
        <AllowedMethod>GET</AllowedMethod>
        <AllowedMethod>HEAD</AllowedMethod>
        <AllowedHeader>content-type</AllowedHeader>
        <AllowedHeader>x-amz-checksum-*</AllowedHeader>
        <ExposeHeader>ETag</ExposeHeader>
        <ExposeHeader>x-amz-checksum-sha256</ExposeHeader>
        <MaxAgeSeconds>300</MaxAgeSeconds>
    </CORSRule>
</CORSConfiguration>
~~~

CORS settings must match the methods and headers signed in presigned requests. Allow only required origins; never treat a wildcard origin as an authorization mechanism. Clients cannot bypass URL/IAM restrictions through CORS.

## 11. Versioning, Object Lock, and recovery

### 11.1. S3 Versioning

When Versioning is enabled:

- PUTting an object to the same key creates a new version while retaining old versions.
- DELETE without a version ID creates a **delete marker**, making the object appear deleted to standard GETs.
- Permanently deleting a version requires specifying the version ID and having corresponding permissions.
- Each version incurs separate storage charges; versioning improves recoverability while potentially increasing costs.

Store `versionId` in the DB if workflows need to reference an exact revision. When uploading a replacement object, update the metadata record to the new version after verification succeeds.

### 11.2. S3 Object Lock

Object Lock provides per-version WORM retention with Governance/Compliance modes and Legal Holds. Enable only for immutability, audit, or legal requirements. Object Lock requires bucket versioning and can block permanent deletion of protected versions. It is not a default setting for ordinary file uploads.

### 11.3. Versioning does not replace backups

Versioning protects against accidental overwrites/deletes, yet does not protect against account compromise, lifecycle misconfigurations, or region-wide disasters. Evaluate S3 Replication, AWS Backup for S3, cross-account copies, retention policies, and restore drills per RPO/RTO. Replication is not an independent backup if deletions or corruption are replicated as configured.

## 12. Lifecycle and storage classes for cost control

S3 offers multiple storage classes for varying access patterns:

| Storage class | Access pattern | Trade-offs |
|---|---|---|
| S3 Standard | Frequent access | Millisecond access, standard storage pricing |
| S3 Intelligent-Tiering | Unpredictable/changing patterns | Automatic tiering; monitoring/automation fees apply |
| S3 Standard-IA | Infrequent access needing fast retrieval | Retrieval fees, minimum storage duration, minimum billable size |
| S3 One Zone-IA | Reproducible data tolerating single-AZ | Stored in one AZ; unsuitable for sole critical copies |
| S3 Glacier Instant Retrieval | Archive needing millisecond retrieval | Retrieval fees/minimum duration |
| S3 Glacier Flexible Retrieval | Archive tolerating restore latency | Restore requests and wait times |
| S3 Glacier Deep Archive | Long-term retention, rare access | Longest restore times, retrieval costs |

Do not put profile photos opened daily into Glacier. Storage classes affect retrieval latency, fees, minimum durations, availability design, and restore workflows.

### 12.1. Lifecycle rules

A bucket can use prefix/tag-based lifecycle rules to:

- Transition aging objects to appropriate storage classes.
- Expire temporary files after a retention period.
- Move noncurrent versions to cheaper tiers or delete them after allowed intervals.
- Abort incomplete multipart uploads.
- Clean up expired delete markers when appropriate.

### 12.2. Be careful with Versioning + Expiration

In a versioned bucket, expiring the current version typically inserts a delete marker; the object data becomes a noncurrent version and continues consuming storage. To remove old versions, a separate `NoncurrentVersionExpiration` lifecycle action is required. Setting only “expire current objects after 30 days” does not permanently purge all bytes.

### 12.3. Retention aligned with business records

Never let Lifecycle delete objects before the corresponding business record's retention period ends. When legal holds, audits, or invoice retention apply, align policies across DB records, S3 object tags, versioning, and lifecycle rules. Before deploying expiration rules, test on a sandbox prefix and inspect noncurrent versions and delete markers.


## 13. Multipart upload and S3 Transfer Manager for large files

For large objects, S3 supports **multipart upload**: splitting an object into parts, uploading parts in parallel or retrying individual parts, and calling `CompleteMultipartUpload` to assemble the object. If a single part fails, only that part is re-uploaded instead of the entire file.

Current multipart limits:

| Parameter | Limit |
|---|---:|
| Maximum object size | 48.8 TiB |
| Maximum number of parts | 10,000 |
| Part number | 1–10,000 |
| Size per part | 5 MiB–5 GiB |
| Last part | May be smaller than 5 MiB |
| Parts returned per ListParts | 1,000 |
| Multipart uploads returned per ListMultipartUploads | 1,000 |

AWS recommends **considering multipart upload for objects around 100 MB or larger**. This is a performance guideline, not a hard requirement. Choose part sizes and concurrency so parts stay within 10,000 and the app does not exhaust RAM or network capacity.

### 13.1. Multipart upload lifecycle

~~~mermaid
flowchart TD
    A["CreateMultipartUpload"] --> B["UploadPart 1..N"]
    B --> C{"All parts uploaded?"}
    C -->|"Yes"| D["CompleteMultipartUpload"]
    D --> E["One S3 object visible"]
    C -->|"No / failure"| F["Retry failed parts"]
    F --> B
    F -->|"Cancel / unrecoverable"| G["AbortMultipartUpload"]
    G --> H["Delete uploaded parts"]
~~~

Steps:

1. `CreateMultipartUpload` initiates the upload and returns an `uploadId`.
2. `UploadPart` sends each chunk with its part number.
3. The client records each part's `ETag`/checksum for completion.
4. `CompleteMultipartUpload` assembles the parts into the final object.
5. If cancelling, call `AbortMultipartUpload` to release uploaded parts.

S3 creates the final object only after `CompleteMultipartUpload` succeeds. Incomplete parts remain stored and **incur storage charges**. Always complete or abort.

### 13.2. S3 Transfer Manager

**S3 Transfer Manager** is a high-level utility in AWS SDK for Java 2.x for file and directory uploads/downloads. It uses multipart uploads and byte-range fetches when configured with an appropriate client, provides transfer progress listeners, and supports pause/resume per API.

Add the module:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3-transfer-manager</artifactId>
</dependency>
~~~

The SDK v2 BOM manages this module's version. You can use a Java-based `S3AsyncClient` with multipart enabled or the AWS CRT-based S3 client. When using CRT, add `software.amazon.awssdk.crt:aws-crt` with an explicit compatible CRT version; the SDK v2 BOM does not manage the CRT artifact version.

### 13.3. Uploading files with Transfer Manager

~~~java
import java.nio.file.Path;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.transfer.s3.S3TransferManager;
import software.amazon.awssdk.transfer.s3.model.CompletedFileUpload;
import software.amazon.awssdk.transfer.s3.model.FileUpload;
import software.amazon.awssdk.transfer.s3.model.UploadFileRequest;

public final class LargeFileUploader {
    public static String upload(
            String bucket, String key, Path source, Region region) {

        try (S3AsyncClient s3 = S3AsyncClient.builder()
                     .region(region)
                     .multipartEnabled(true)
                     .build();
             S3TransferManager manager = S3TransferManager.builder()
                     .s3Client(s3)
                     .build()) {

            UploadFileRequest request = UploadFileRequest.builder()
                    .putObjectRequest(b -> b
                            .bucket(bucket)
                            .key(key))
                    .source(source)
                    .build();

            FileUpload upload = manager.uploadFile(request);
            CompletedFileUpload result =
                    upload.completionFuture().join();

            return result.response().eTag();
        }
    }
}
~~~

This example reads from a filesystem path; with Spring multipart uploads, a controlled temporary file can be passed to Transfer Manager, provided disk quotas are bounded and temp files are deleted upon completion. For large files, direct browser-to-S3 avoids writing large files onto the Spring API server's disk.

### 13.4. Choosing part size and concurrency

- Larger part sizes reduce request/part counts while increasing per-upload buffer/memory usage.
- Higher concurrency increases throughput when network/CPU/S3 capacity permits, at the cost of more buffers and connection pressure.
- Estimate peak transfer memory from `partSize × concurrentParts × concurrentUploads`, plus overhead.
- Never raise concurrency solely to chase single-benchmark throughput; monitor P95/P99, throttles, heap, direct memory, file descriptors, and network saturation.
- Set sensible timeouts and retries; do not keep uploads running indefinitely after client disconnects.

### 13.5. Aborting incomplete uploads with Lifecycle

Configure an S3 Lifecycle rule with `AbortIncompleteMultipartUpload` to purge incomplete multipart uploads after a set number of days (e.g., 7 days). This prevents forgotten parts from accumulating storage costs. Still abort proactively in exception/cancellation paths; lifecycle serves as a safety net.

### 13.6. Large downloads and byte-range fetches

Transfer Manager can download files or directories using parallel byte-range requests. Ensure adequate disk space, cap concurrent transfers, and verify checksums/versions before passing files to downstream business workflows. Never load an entire object into `byte[]` just to write it to disk.

## 14. Data integrity: checksums and ETag

S3 supports checksums to verify data integrity during uploads and downloads. The AWS SDK can compute checksums automatically per configuration/version, or applications can specify the algorithm and precomputed checksum value.

### 14.1. Checksum algorithms

S3 supports algorithms such as CRC-64/NVME, CRC32, CRC32C, SHA-1, SHA-256, MD5, and certain XXHash/SHA-512 algorithms per current API support. For critical files:

- Choose a checksum algorithm aligned with compliance/performance needs.
- Send checksums with uploads or let the SDK compute them per current defaults.
- Persist verified checksums in the metadata DB for business reconciliation.
- On download, request checksum validation where supported by the API/SDK.
- For composite/part-level multipart checksums, part numbers must be contiguous starting at 1.

### 14.2. ETag is not always MD5

ETag is useful as an entity tag/identifier, yet **it cannot be assumed to equal the whole-object MD5**. For multipart uploads, the ETag is derived from the parts' checksums with a part-count suffix; under certain encryption modes and upload patterns, the ETag is likewise not a plain MD5.

Do not rely on `ETag` as your sole business integrity checksum without understanding the upload/encryption mode. Use an explicit checksum algorithm and store the verified value explicitly.

### 14.3. Post-upload verification

For presigned uploads, the backend can call `HeadObject` to verify Content-Length, metadata, VersionId, and returned checksum fields. HEAD only confirms object metadata; it **does not replace malware scanning** and does not prove the payload actually matches the client-declared MIME type. Inspect bytes in a scanning pipeline when security requires it.

## 15. S3 Event Notifications and post-upload processing

Once an object is created, applications can emit events for thumbnailing, OCR, malware scanning, metadata extraction, indexing, or notifications. S3 can send notifications to SQS, SNS, Lambda, and Amazon EventBridge depending on bucket configuration.

~~~mermaid
flowchart LR
    APP["Spring Boot / Browser"] --> S3["S3 PutObject"]
    S3 --> EVT["S3 ObjectCreated event"]
    EVT --> EB["EventBridge / SQS"]
    EB --> SCAN["Malware scan"]
    EB --> THUMB["Thumbnail / OCR"]
    EB --> META["Metadata extraction"]
    SCAN --> DB["Update file status"]
    THUMB --> DB
    META --> DB
~~~

### 15.1. Event delivery is not exactly-once

Amazon S3 Event Notifications provide **at-least-once** delivery. Notifications usually arrive quickly, yet may be delayed, duplicated, or arrive out of order. Consumers must be idempotent.

A consumer should:

1. Parse bucket, object key, event type, version ID, and event metadata.
2. URL-decode the object key according to the notification format.
3. Use event ID or business file ID as a deduplication key.
4. Inspect `sequencer` when ordering events for the **same object key**; never compare sequencers across different keys.
5. Record processed/inbox state alongside the business update.
6. Retry transient failures, route poison messages to a DLQ, and support controlled replay.

### 15.2. Avoiding event loops

If a Lambda triggered by `ObjectCreated` writes a thumbnail back into the same bucket/prefix matching the notification rule, it can trigger itself infinitely. Use a separate bucket or explicit prefix filters such as:

~~~text
uploads/       → trigger scanner
derived/       → do not trigger scanner
thumbnails/    → trigger downstream workflow only if needed
~~~

EventBridge helps route and filter events; SQS provides buffering/backpressure and DLQs. Choose based on retry, fan-out, ordering, and operational requirements.

### 15.3. S3 events do not share a transaction with the database

If Spring Boot writes DB status `UPLOADED` after `PutObject`, the event can arrive before the DB transaction commits. Conversely, if the upload succeeds and the API crashes, the event still fires even though the browser received no response. Consumers should look up file records by key/fileId and handle transitional states rather than assuming strict ordering between API responses and notifications.

## 16. Observability and auditing

| Source | Data to track | Goal |
|---|---|---|
| Application metrics | Upload success/failure, file size, duration, queue time | User experience SLOs |
| AWS SDK | Request ID, retry count, service errors, latency | Diagnosing API calls |
| S3 CloudWatch | Storage bytes, request metrics, 4xx/5xx, latency when enabled | Bucket health |
| S3 Storage Lens | Storage usage, object count, activity, cost optimization | Org-wide trends |
| CloudTrail data events | Object-level API access per configuration | Auditing who read/wrote/deleted objects |
| S3 server access logs | Request-level records per configuration | Access forensics |
| SQS/Lambda | Queue age, DLQ depth, Lambda errors/throttles | Post-upload processing |
| Database | Pending uploads, orphan records, scan backlog | Business consistency |

### 16.1. CloudTrail data events

CloudTrail management events and **S3 data events** differ in scope and cost. To audit operations such as `GetObject`/`PutObject`, configure data event selectors for the relevant buckets/prefixes and manage retention on the CloudTrail destination. Never assume object-level access is logged unless data events are explicitly enabled.

### 16.2. Do not log sensitive data

Never log presigned URLs, authorization headers, AWS credentials, raw file bytes, sensitive metadata, or object contents. Log correlation IDs, `fileId`, authorized tenant IDs, bucket/prefix (if policy permits), operation, AWS request ID, status, duration, and error code.

### 16.3. Useful alerts

- Abnormal spike in upload failures or 5xx responses.
- `PENDING_UPLOAD` lingering past SLA.
- Growing `UPLOADED_PENDING_SCAN` backlog.
- SQS oldest message age/DLQ crossing threshold.
- Unusual S3 storage growth or noncurrent version counts.
- Rising incomplete multipart uploads.
- Unexpected public access/config changes or access-denied spikes.

## 17. Cost and performance optimization

S3 cost is more than per-GB storage pricing. Account for **storage + requests + retrieval + data transfer + replication + KMS + incomplete multipart + versioning**.

### 17.1. Cost drivers

| Component | Cost impact |
|---|---|
| Storage class and GB-months | Bytes across all current/noncurrent versions |
| PUT/GET/LIST/HEAD requests | Per-operation API request charges |
| Multipart | Create/UploadPart/Complete requests and orphaned parts |
| Retrieval | Per-GB retrieval fees from IA/Glacier tiers by class |
| Data transfer | Egress, inter-Region transfer, CDN/origin traffic |
| Replication | Destination storage and transfer, replication requests |
| SSE-KMS | KMS request volume and key charges |
| Versioning | Every version stores full object bytes |
| Object Lock | Retention keeps data longer |
| Inventory/Storage Lens/logging | Reporting, monitoring, and destination storage |

### 17.2. Disciplined cost reduction

- Use presigned direct uploads to offload backend bandwidth/compute; still budget for S3 requests and data transfer.
- Choose storage classes based on access frequency and retrieval SLAs.
- Apply Lifecycle rules to temporary files, noncurrent versions, and incomplete multipart uploads.
- Enforce per-tenant file size limits, quotas, and upload rate limits.
- Never LIST the entire bucket per UI page load; query DB indexes or scoped prefixes.
- Use CloudFront for widely distributed content; evaluate cache policies and signed cookies/URLs.
- Use checksums and multipart wisely to avoid re-uploading whole files after network hiccups.
- Clean up orphaned objects via reconciliation with ownership/retention guardrails—never purge blindly by age.

### 17.3. Latency optimization

- Place buckets and applications in matching Regions; avoid unnecessary cross-Region transfers.
- Reuse S3 clients/HTTP connections.
- Use multipart/Transfer Manager for large files with bounded concurrency.
- For public/cacheable downloads, evaluate CloudFront; for private content, use Origin Access Control and signed access by design.
- Measure P50/P95/P99, retries, connection pool saturation, and bytes transferred.
- Avoid passing files through the database or base64-encoding in JSON when streaming/direct object transfer is viable.

## 18. Troubleshooting S3 in Java/Spring Boot

| Symptom | Possible cause | What to check |
|---|---|---|
| `NoSuchBucket` | Wrong bucket name/Region/account | Bucket ARN, Region, environment config |
| `NoSuchKey` | Key typo/case/prefix mismatch or version mismatch | DB object key, URL decoding, VersionId |
| `AccessDenied` | IAM/bucket/KMS/VPC endpoint policy deny | Caller identity, role, bucket/key policy, KMS key policy |
| `SignatureDoesNotMatch` | Region, signed headers, re-encoded/modified URL, or clock drift | Region, method, Content-Type, checksum header, NTP/proxy |
| Presigned URL returns 403 | URL expired, signer credentials expired, policy deny, or header mismatch | Expiration, role session, exact HTTP method/headers |
| Browser CORS error | CORS rule missing origin/method/header/expose header | Bucket CORS and preflight response |
| Upload timeout | Oversized request, proxy timeout, network, pool/concurrency | Upload path, SDK timeout, multipart, client disconnect |
| Spring `MaxUploadSizeExceededException` | Multipart limits below file/request size | `max-file-size`, `max-request-size`, ingress limits |
| Heap OOM during upload | `getBytes()`/buffering whole file or excessive concurrency | Streaming, temp disk, concurrency, heap profile |
| S3 object exists, DB still pending | API timed out after S3 success or DB failure | Reconciliation using `HeadObject`/`VersionId` |
| DB record exists, object missing | S3 upload failed or object deleted | State transitions, S3 events, delete audit trail |
| Incomplete multipart parts billing | Upload never completed/aborted | `ListMultipartUploads`, Abort, Lifecycle rule |
| ETag differs from expected MD5 | Multipart/encryption/checksum behavior | Use explicit checksums instead of ETag |
| File scan not running | Event destination permissions/config or DLQ | S3 notifications, EventBridge/SQS policy, queue age |
| Object unexpectedly public | Public access settings/policy/ACL | Block Public Access, Object Ownership, bucket policy |
| Wrong download filename/MIME | Incorrect metadata/DB record or unsafe header | Safe filename, Content-Type validation |
| Versioning inflating storage | Accumulating noncurrent versions and delete markers | Lifecycle noncurrent expiration, Storage Lens |
| Archived object unavailable immediately | Glacier class requires restore | Storage class, restore status, and SLA |

### 18.1. Layered diagnosis

1. Verify caller identity, account, Region, bucket, and object key.
2. Read the service error code/request ID; separate service errors from client/network exceptions.
3. Check IAM roles, bucket policies, KMS key policies, Block Public Access, and endpoint policies.
4. Check signed method/headers/URL expiry if using presigned URLs.
5. Check multipart upload ID, completed parts, and incomplete-upload Lifecycle rules.
6. Check DB status/version, event queues/DLQs, and audit trails.
7. Cross-check checksum/`VersionId` and reconcile before retrying or deleting.

Never grant `s3:*` or open a bucket publicly to quickly silence an `AccessDenied` error. Identify the exact denied action/resource/condition and apply the minimal policy fix.

## 19. Read-only AWS CLI inspection for buckets/objects

The following commands use an example `dev` profile and Region. They are metadata/config read operations; some APIs still incur request charges. Access only authorized buckets.

### 19.1. Verifying identity and bucket

~~~bash
aws sts get-caller-identity --profile dev

aws s3api head-bucket \
  --bucket company-private-files-prod \
  --profile dev \
  --region ap-southeast-1

aws s3api get-bucket-location \
  --bucket company-private-files-prod \
  --profile dev
~~~

### 19.2. Inspecting security configuration

~~~bash
aws s3api get-public-access-block \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-ownership-controls \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-encryption \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-versioning \
  --bucket company-private-files-prod \
  --profile dev

aws s3api get-bucket-lifecycle-configuration \
  --bucket company-private-files-prod \
  --profile dev
~~~

If a configuration has not been set, certain APIs return errors like `NoSuchPublicAccessBlockConfiguration`/`ServerSideEncryptionConfigurationNotFoundError`/`NoSuchLifecycleConfiguration`; distinguish “unconfigured” from permission/network failures.

### 19.3. Head object and bounded prefix listing

~~~bash
aws s3api head-object \
  --bucket company-private-files-prod \
  --key tenants/tenant-42/uploads/example-file-id \
  --profile dev \
  --region ap-southeast-1

aws s3api list-objects-v2 \
  --bucket company-private-files-prod \
  --prefix tenants/tenant-42/uploads/ \
  --max-keys 20 \
  --profile dev \
  --region ap-southeast-1
~~~

`HeadObject` fetches metadata without downloading bytes. `ListObjectsV2` returns object keys and metadata; bound prefix and `MaxKeys` rather than listing an entire bucket just to debug. Never print presigned URLs or PII into shell history.

### 19.4. Listing incomplete multipart uploads

~~~bash
aws s3api list-multipart-uploads \
  --bucket company-private-files-prod \
  --prefix tenants/tenant-42/ \
  --max-uploads 20 \
  --profile dev \
  --region ap-southeast-1
~~~

This command reads the list of in-progress multipart uploads. **Do not** invoke `abort-multipart-upload` in a read-only audit; aborting mutates state and purges uploaded parts.

## 20. Hands-on lab: designing file storage for a Spring Boot app

### 20.1. Lab A — Backend-proxied invoice upload

Requirements:

- Endpoint `POST /api/files` accepts a PDF file.
- Only authenticated users belonging to a valid tenant may upload.
- Enforce a 20 MB size limit and validate the PDF file signature.
- Backend generates `fileId`/object key; never use the original filename as the key.
- Write a `PENDING_UPLOAD` record, upload to S3, then update to `UPLOADED_PENDING_SCAN`.
- A worker scans the file and transitions to `AVAILABLE` only upon passing checks.
- Download endpoint accepts `fileId`, authorizes access, and streams the object to the client.

Draw a sequence diagram and explain how to handle the case where S3 upload succeeds yet the DB update fails.

### 20.2. Lab B — Direct image/video upload

1. Build an API creating an upload session, checking quota/size/type.
2. Save a pending DB record with a backend-generated object key.
3. Generate a presigned PUT URL expiring in 10 minutes.
4. Browser PUTs the file directly to S3 with headers matching the signature.
5. Browser calls the finalize API.
6. Backend runs `HeadObject` to verify size/metadata/checksum and enqueues for scanning.
7. Worker updates status to `AVAILABLE` or `REJECTED`.

Explain why a presigned URL is not a user identity, why the URL must be protected like a bearer token, and why CORS does not replace authorization.

### 20.3. Lab C — Multipart upload

Using a large sandbox file:

- Upload a 200 MB file with S3 Transfer Manager.
- Test varying part sizes/concurrency and measure throughput/P95.
- Interrupt a part in the test environment and observe retry behavior.
- Cancel an upload and verify `AbortMultipartUpload` frees parts.
- Configure Lifecycle to abort incomplete uploads after 7 days.
- Inspect ETag and checksum; explain why ETag is not always MD5.

Never run large tests against production buckets or sensitive files.

### 20.4. Lab D — Bucket security audit

Using read-only AWS Console/CLI, verify:

- Block Public Access at account and bucket levels.
- Object Ownership set to Bucket owner enforced.
- Default encryption set to SSE-S3 or SSE-KMS per policy.
- Bucket policy denies insecure transport.
- Application role has only required actions/resources.
- CORS permits only approved frontend origins.
- Versioning/Lifecycle match retention policy.
- CloudTrail data events are enabled if object-level auditing is required.

### 20.5. Lab E — Reconciliation and duplicate events

Simulate:

1. Object upload succeeds, yet API times out before DB update.
2. S3 notification is delivered twice.
3. Worker receives an older event after a newer event.
4. Scan worker crashes after updating DB but before ACKing SQS.

Design idempotency keys, inbox tracking, file states, sequencer/version checks, and reconciliation jobs so no object is mis-scanned, mislabeled, or wrongly deleted.

## 21. Pre-merge review checklist

### API and data model

- [ ] Tenant/user extracted from authentication context?
- [ ] Object key server-generated and free of client-controlled paths?
- [ ] DB record stores owner, object key, version/checksum, size, content type, and state?
- [ ] Idempotency key guards against request retries?
- [ ] Reconciliation handles unclear S3/DB outcomes?
- [ ] Download URLs never issued for pending/rejected/quarantined files?

### Upload/download

- [ ] Multipart request limits configured in Spring and ingress?
- [ ] Avoided `getBytes()`/buffering entire files on the heap?
- [ ] Streams closed and temp files cleaned up?
- [ ] File types verified via bytes/signatures, not extension alone?
- [ ] Large files use multipart/Transfer Manager or direct-to-S3?
- [ ] Presigned URLs are short-lived, unlogged, and headers match signature?
- [ ] Downloads authorize via `fileId` and stream/Range properly if supported?

### S3 security and operations

- [ ] Bucket private with Block Public Access enabled?
- [ ] Object Ownership set to Bucket owner enforced, no public ACLs?
- [ ] Least-privilege IAM scoped to bucket/prefix?
- [ ] HTTPS enforced and appropriate encryption at rest configured?
- [ ] SSE-KMS key policy/KMS permissions configured when used?
- [ ] CORS restricted to intended origins/methods/headers?
- [ ] Versioning/Lifecycle/Object Lock aligned with retention?
- [ ] Incomplete multipart cleanup configured?
- [ ] S3 events handle duplicate/out-of-order delivery?
- [ ] CloudWatch/CloudTrail/DLQ/Storage Lens monitoring in place?
- [ ] Cost model accounts for storage, requests, retrieval, transfer, versions, KMS, and replication?

## 22. Self-assessment questions

1. Why should uploaded files generally store bytes in S3 and metadata in a database?
2. How do bucket, object, key, and prefix differ?
3. Why shouldn't object keys use the original filename directly?
4. Does S3 have real filesystem folders or only key prefixes?
5. How do backend proxy and direct presigned uploads differ in bandwidth and validation?
6. What risk does `MultipartFile.getBytes()` pose for large files?
7. Why set both `max-file-size` and `max-request-size` limits?
8. Why is browser-supplied `Content-Type` insufficient to verify file type?
9. What must `RequestBody.fromInputStream` know about content length?
10. Why should `S3Client` be reused as a Spring singleton bean?
11. What does it mean that a presigned URL is a bearer token?
12. Can a presigned PUT URL be used multiple times before expiration?
13. What can happen if a presigned PUT writes to the same key a second time?
14. Why can temporary role credentials expire a URL earlier than its configured duration?
15. Does CORS replace IAM authorization?
16. When should multipart upload be used?
17. What are the minimum part size (excluding the last part) and maximum number of parts?
18. Which transfer types does S3 Transfer Manager support?
19. Why do incomplete multipart parts still incur charges?
20. Is ETag always the MD5 of the entire object?
21. What do S3 checksums protect against?
22. Why don't S3 and RDS share a single ACID transaction?
23. Why do files need `PENDING`/`SCANNING`/`AVAILABLE` states?
24. Do S3 Event Notifications guarantee exactly-once and ordered delivery?
25. How do you handle duplicate and out-of-order events?
26. What risks do Block Public Access and Bucket owner enforced mitigate?
27. When should SSE-KMS be chosen over SSE-S3?
28. How does Versioning handle DELETE?
29. Does Lifecycle expiration on a versioned bucket permanently delete noncurrent versions?
30. When should you use S3 Standard, Intelligent-Tiering, or Glacier?
31. Which cost drivers exist beyond storage GB-months?
32. How do CloudTrail data events differ from management events?
33. Why should presigned URLs never be logged?
34. What should be done when S3 upload succeeds yet the DB update times out?
35. Why do upload retries require idempotency keys and reconciliation?

### Answer guide

- **Architecture:** S3 stores bytes; DB stores owner/key/status; Spring Boot coordinates authorization and metadata.
- **Upload:** `MultipartFile` size limits, streaming, MIME sniffing, presigned URLs or Transfer Manager depending on file size.
- **Security:** Private bucket, Block Public Access, Bucket owner enforced, least-privilege IAM, TLS, SSE-S3/SSE-KMS, narrow CORS.
- **Consistency:** S3 and DB are not atomic; use states, idempotency, outbox/inbox, and reconciliation.
- **Reliability:** Multipart retry/abort, checksums, idempotent event consumers, versioning/backups/lifecycle.
- **Cost:** Storage classes, requests, retrieval, data transfer, KMS, replication, incomplete parts, and object versions.

## 23. Official AWS and Spring documentation

1. [Amazon S3 examples using AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_s3_code_examples.html) — PutObject/GetObject, presigned URLs, multipart, Transfer Manager.
2. [Work with Amazon S3 using SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3.html) — Upload streams, cross-Region, checksums, client performance, and events.
3. [S3 pre-signed URLs with SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/examples-s3-presign.html) — Generate GET/PUT URLs and use them.
4. [S3 Transfer Manager for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/transfer-manager.html) — Multipart transfers, progress, directory transfers, and CRT.
5. [AWS CRT-based S3 client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/crt-based-s3-client.html) — Performance, multipart, and stream behavior.
6. [S3 multipart upload overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html) — Upload lifecycle, parts, and pricing.
7. [S3 multipart upload limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html) — Object/part limits.
8. [Abort incomplete multipart uploads with Lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html) — Cleanup and cost.
9. [Checking object integrity for uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html) — Checksum algorithms and ETag behavior.
10. [S3 presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html) — Permissions, expiry, credentials, and URL reuse.
11. [Uploading objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html) — PUT upload semantics.
12. [S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html) — Public access, ACLs, encryption, and auditing.
13. [S3 Object Ownership](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html) — Bucket owner enforced and disabled ACLs.
14. [S3 access management](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-management.html) — IAM, bucket policies, and object access.
15. [S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html) — Versions, overwrites, and delete markers.
16. [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) — WORM retention and legal holds.
17. [S3 storage classes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html) — Access patterns and minimum durations.
18. [S3 Lifecycle configuration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html) — Transitions, expiration, and noncurrent versions.
19. [S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html) — Destinations and at-least-once delivery.
20. [S3 event message structure](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html) — Key encoding and sequencer ordering.
21. [S3 CloudWatch metrics](https://docs.aws.amazon.com/AmazonS3/latest/userguide/cloudwatch-monitoring.html) — Request and storage metrics.
22. [S3 CloudTrail data events](https://docs.aws.amazon.com/AmazonS3/latest/userguide/cloudtrail-logging.html) — Object-level API auditing.
23. [Spring Boot multipart properties](https://docs.spring.io/spring-boot/appendix/application-properties/) — Servlet/WebFlux multipart limits.
24. [AWS SDK for Java 2.x credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — IAM role/profile credentials.
25. [AWS SDK for Java 2.x Maven setup](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/setup-project-maven.html) — BOM and service module dependencies.

> **Final takeaway:** S3 is object storage; object keys are server-generated and the DB manages ownership/status. For small files, Spring Boot can stream through the SDK; for large files, evaluate presigned direct uploads and multipart/Transfer Manager. Private buckets, least-privilege IAM, Block Public Access, encryption, checksums, lifecycle rules, and idempotent event processing are essential for secure, resilient, cost-controlled file storage.
