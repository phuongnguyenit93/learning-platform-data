# Amazon S3: Streaming data and multipart upload

## Learning objectives

In the `SPRING_CLOUD_PROVIDER_INTEGRATION` module, Spring Boot integrates with managed services across AWS, Azure, and Google Cloud to access storage, messaging, data, and authenticated resources. With **Amazon S3**, a file transfer request might be only a few kilobytes or several gigabytes. If the application reads the entire file into a `byte[]` before processing, memory usage can spike rapidly when many users transfer files concurrently. Two techniques must be distinguished:

- **Streaming:** sequentially processing chunks of data from an `InputStream`, `OutputStream`, or asynchronous API rather than holding the entire object in memory.
- **Multipart upload:** an S3 protocol that splits **one object** into multiple parts, uploads each part separately, and instructs S3 to assemble them into a complete object.

After this lesson, you will know how to stream uploads/downloads in Spring Boot, manually orchestrate multipart uploads with AWS SDK for Java v2, use high-level transfer solutions when appropriate, design retries/cleanup, and test network failures. Examples use `software.amazon.awssdk` (AWS SDK v2) and the Spring Cloud AWS namespace `io.awspring.cloud`; select library versions compatible with your project's Spring Boot version.

> **Key distinction:** Streaming describes how the application **reads and writes data**; multipart describes how **S3 receives a large object across multiple requests**. An upload can use streaming while still being a single PUT. Conversely, multipart can upload parts from small byte arrays with bounded memory.

## 1. Memory challenges when handling large files

Suppose an application allows 50 users to upload 200 MiB files simultaneously. If every request calls `file.getBytes()` and holds the content in RAM, the application can simultaneously retain roughly **10,000 MiB**, not counting framework heap, HTTP buffers, file processing overhead, and GC. This illustrates capacity risk, not an exact prediction of heap allocation in every environment.

~~~java
// For large files, this approach can cause significant memory pressure.
byte[] allBytes = file.getBytes();
s3.putObject(putRequest, RequestBody.fromBytes(allBytes));
~~~

With streaming, each request holds only a fixed-size buffer:

~~~text
Client ──stream──▶ Spring Boot ──stream──▶ Amazon S3
                   64 KiB buffer
                       │
                 does not hold entire file
~~~

With multipart, the backend can also load one part, send it to S3, discard the buffer, and repeat. With an 8 MiB part, resident data depends on **how many parts are held concurrently**, rather than equaling the entire object size. Even so, 100 concurrent requests multiplied by an 8 MiB buffer would consume around 800 MiB excluding overhead; concurrency limits are still necessary.

### 1.1. Common Java types

| API | Role | Notes |
| --- | --- | --- |
| `InputStream` | Sequential read from a source, e.g., file or HTTP upload | Close stream after reading; do not assume it can be rewound |
| `OutputStream` | Sequential write to a destination, e.g., HTTP response or file | Can fail mid-transfer; does not hold the whole file |
| `RequestBody.fromBytes(byte[])` | Send a byte array via sync AWS SDK | Easy for small files; holds payload in RAM |
| `RequestBody.fromInputStream(stream, length)` | Sync SDK sends from a stream of known length | **Requires exact byte count** and stream open throughout the call |
| `RequestBody.fromFile(path)` | Read content from a local file | Useful when the file is already on disk |
| `S3Client.getObject(request)` | Returns `ResponseInputStream<GetObjectResponse>` | Close stream to release the connection |
| `AsyncRequestBody` / `S3AsyncClient` | Asynchronous data transfer | Requires managing callbacks, backpressure, timeouts, and lifecycle |
| `S3TransferManager` | File transfer via AWS SDK v2 high-level API | Suitable when letting the SDK manage upload/download, multipart, and concurrency |

**Distinguish buffering across layers:** using `MultipartFile.getInputStream()` in Spring MVC does not prove the HTTP request is streamed end-to-end from browser to S3 without an intermediary. The servlet container may have buffered the multipart body in RAM or temporary files. Streaming on the S3 side avoids creating another full copy in application code, but you still need to check web-server upload buffering configuration.

### 1.2. Units and practical limits

- **MiB** stands for mebibyte: 1 MiB = 1,048,576 bytes. S3 transfer sizes and limits must be calculated in **bytes**, not by counting text characters.
- For standard S3 multipart uploads, each part must be **at least 5 MiB**, except the last part; a single part can be up to **5 GiB**; and at most **10,000 parts** are allowed per upload. Verify exact object-level quotas and specific features against the AWS documentation for your environment.
- `partSize` determines the **number of parts**, request count, cost, buffer footprint, and retry granularity. An 8 MiB part example is just a learning value; extremely large files require larger parts so you do not exceed the 10,000-part limit.
- S3 provides durable data transfer and strong read-after-write consistency for PUT/GET/LIST after operations succeed; that does not replace handling timeouts, duplicate requests, and indeterminate upload states.

## 2. Preparing Spring Cloud AWS and IAM permissions

### 2.1. Dependencies and configuration

In a Maven project, use the Spring Cloud AWS BOM **compatible with your Spring Boot version**, then declare the S3 starter:

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

`spring-cloud-aws.version` must be declared with a compatible release version; there is no single fixed version for every Spring Boot release.

~~~yaml
# application.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
  servlet:
    multipart:
      max-file-size: 200MB
      max-request-size: 200MB

app:
  storage:
    bucket: ${S3_BUCKET_NAME}
    prefix: documents/
~~~

`app.storage.*` are application-specific properties. The `spring.servlet.multipart.*` limits are **examples for a Spring MVC endpoint accepting multipart/form-data**, and must be chosen according to business needs and infrastructure limits; they do not govern S3 API maximum sizes. For huge files exceeding web server request limits, consider **direct upload** from client to S3 via presigned URLs or a multipart protocol.

When deploying on AWS, prefer an IAM role attached to the workload. Locally, you can use an AWS profile or temporary credentials via the default credentials provider chain. Do not put access keys/secret keys in source code, config files committed to Git, or logs.

### 2.2. Permissions for PUT, GET, and multipart

| Call | Typical S3 permission | Scope |
| --- | --- | --- |
| `PutObject`, `CreateMultipartUpload`, `UploadPart`, `CompleteMultipartUpload` | `s3:PutObject` | Object ARN |
| `GetObject` | `s3:GetObject` | Object ARN |
| `AbortMultipartUpload` | `s3:AbortMultipartUpload` | Object ARN |
| `ListParts` | `s3:ListMultipartUploadParts` | Object ARN |
| `ListMultipartUploads` | `s3:ListBucketMultipartUploads` | Bucket ARN |
| Standard object listing | `s3:ListBucket` | Bucket ARN |

Minimal policy for a service that needs to upload, read, and abort multipart uploads under the `documents/` prefix:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:AbortMultipartUpload"
      ],
      "Resource": "arn:aws:s3:::training-private-docs/documents/*"
    }
  ]
}
~~~

Replace the sample bucket name with your real bucket before using. If the service also calls `ListParts` or lists incomplete uploads, grant the corresponding actions on the appropriate ARN type. If using SSE-KMS, review KMS permissions such as `kms:GenerateDataKey` and `kms:Decrypt` depending on the operation, along with the actual key policy. Bucket policies, AWS Organizations SCPs, or explicit denies can further narrow effective permissions.

The bucket should remain private with appropriate Block Public Access settings. Spring Boot's IAM role can send data to S3, yet end users must still be **authenticated and authorized by business rules** before the backend reads, writes, or issues URLs for their objects.

## 3. Streaming download with `S3Client`

A `GetObject` call can return a stream from S3. For large files, avoid `getObjectAsBytes` or `readAllBytes` if you do not need the whole file in RAM.

### 3.1. Service that reads via stream

~~~java
import java.io.IOException;
import java.io.OutputStream;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

@Service
public class S3DownloadService {
    private final S3Client s3Client;
    private final String bucket;

    public S3DownloadService(
            S3Client s3Client,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    public void copyTo(String trustedKey, OutputStream destination)
            throws IOException {
        if (trustedKey == null
                || !trustedKey.startsWith("documents/")) {
            throw new IllegalArgumentException("Invalid key");
        }

        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(trustedKey)
                .build();

        try (ResponseInputStream<GetObjectResponse> source =
                     s3Client.getObject(request)) {
            source.transferTo(destination);
        }
    }
}
~~~

Here:

1. `S3Client` is configured and injected by the Spring Cloud AWS starter and reused across requests.
2. Each `getObject` opens a stream reading from S3; **try-with-resources** ensures the stream is closed when copying completes or on error.
3. `transferTo` copies bytes from source stream to destination without allocating a `byte[]` holding the entire content.
4. `destination` is owned by the caller; the service **does not close** the HTTP output stream or caller-supplied stream itself.
5. `trustedKey` must come from a record already checked for **user/tenant permissions**. Checking the prefix only validates key shape; it does not authorize data access.

If you only need to download a slice, S3 supports byte ranges:

~~~java
var request = GetObjectRequest.builder()
        .bucket(bucket)
        .key("documents/large-video.bin")
        .range("bytes=0-1048575") // First 1 MiB, if the object is large enough.
        .build();

try (var firstMegabyte = s3Client.getObject(request)) {
    firstMegabyte.transferTo(destination);
}
~~~

Range GET is suited for media playback, resume support, or reading file format headers. It is **not** a multipart upload part; the two features differ in API and purpose.

### 3.2. Streaming an HTTP response in Spring MVC

With Spring MVC's `StreamingResponseBody`, you can stream data from S3 to the browser:

~~~java
// Snippet illustrating controller flow, where documentService is
// an application-defined business service.
@GetMapping("/documents/{id}/content")
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID id,
        Authentication authentication) {

    DocumentRecord record = documentService
            .requireReadableDocument(id, authentication);

    StreamingResponseBody body = output ->
            s3DownloadService.copyTo(record.objectKey(), output);

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(body);
}
~~~

Types like `DocumentRecord` and `documentService` in the controller snippet **illustrate integration with the project's business layer** rather than standalone copy-paste classes. The core point is **checking permissions before building the response** and calling `copyTo` once MVC starts streaming.

`StreamingResponseBody` runs under Spring MVC's async processing mechanism, yet synchronous `S3Client` reads can still tie up a worker thread for the duration of the transfer. Configure the executor, timeouts, and connection count appropriately; do not assume this is reactive or non-blocking I/O.

In addition, if response headers have already been sent and the stream later fails, the API can no longer switch to a standard error JSON response. The system should log the request ID, handle client disconnects, and close the S3 source; for large files, consider presigned GET URLs so clients download directly from S3.

### 3.3. Can `S3Template` and Spring `Resource` stream?

Spring Cloud AWS also provides object-reading abstractions:

~~~java
// S3Template is injected via the S3 starter.
Resource object = s3Template.download(
        "training-private-docs", "documents/report.pdf");

try (InputStream input = object.getInputStream()) {
    input.transferTo(destination);
}
~~~

Or use `ResourceLoader` if the application already has the S3 resource scheme integrated:

~~~java
Resource resource = resourceLoader.getResource(
        "s3://training-private-docs/documents/report.pdf");

try (InputStream input = resource.getInputStream()) {
    input.transferTo(destination);
}
~~~

`S3Template`/`Resource` is helpful when the rest of the application already works with `Resource`. However, **do not treat `Resource.getFile()` as a local file**: an S3 object is a remote resource, and calls like `exists()`, `contentLength()`, or `getInputStream()` can trigger network requests. When you need Range requests, conditional requests, checksums, or detailed response metadata handling, using `S3Client` directly is usually clearer.

## 4. Streaming upload with a single PUT when length is known

S3 multipart upload is **not mandatory** for every file. For small or medium files, a single PUT via `InputStream` can be simpler and sufficient.

### 4.1. Uploading from an `InputStream` with exact `contentLength`

~~~java
import java.io.InputStream;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class S3SinglePutService {
    private final S3Client s3Client;
    private final String bucket;

    public S3SinglePutService(
            S3Client s3Client,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    public String uploadKnownLength(
            InputStream input,
            long contentLength,
            String contentType) {

        if (contentLength < 0) {
            throw new IllegalArgumentException(
                    "Exact byte size must be known");
        }

        String key = "documents/" + UUID.randomUUID();

        PutObjectRequest request = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(contentType)
                .build();

        s3Client.putObject(
                request,
                RequestBody.fromInputStream(input, contentLength));

        return key;
    }
}
~~~

**Important conditions:**

- `contentLength` is the **byte count**, not character count or an estimate. If the declared byte count does not match the actual stream, the request may fail, hang waiting for bytes, or produce unexpected content.
- The caller must keep the stream open until `putObject` returns and is responsible for closing the source stream. `putObject` is a synchronous call that holds the thread while sending data.
- `contentType` should be verified/normalized from the actual file format; do not set it blindly from client-declared headers.
- Do not use `RequestBody.fromContentProvider` without length assuming it always keeps memory low: the synchronous SDK may need to buffer in order to determine length. For unknown-length sources, use a controlled temporary file or **multipart upload by parts**.
- Record the key only after PUT succeeds; if coordinating with a database, you may need retry/idempotency mechanisms and object cleanup when another transaction fails.

### 4.2. Using `MultipartFile` in a controller

Spring MVC provides `MultipartFile.getInputStream()` and `MultipartFile.getSize()`:

~~~java
try (InputStream input = multipartFile.getInputStream()) {
    String objectKey = s3SinglePutService.uploadKnownLength(
            input,
            multipartFile.getSize(),
            validatedContentType);
    // Record objectKey in the database alongside owner/tenant.
}
~~~

The servlet container's `max-file-size`/`max-request-size` settings must match. A `MultipartFile` may already have been buffered to disk before the controller executes; calling `getInputStream` **does not guarantee end-to-end streaming from the browser**.

For very large files or many concurrent clients, routing data through the backend consumes bandwidth, connections, and threads. When server-side scanning or transformation is unnecessary, you can choose **direct-to-S3** uploads via presigned URLs issued by the backend after authentication.

### 4.3. Single PUT vs. multipart

| Criterion | Single PUT | Multipart upload |
| --- | --- | --- |
| Number of upload requests | One PUT request | Initiate + multiple UploadPart + Complete |
| Byte-by-byte transfer via Java stream | Possible | Possible |
| Retry on mid-upload network error | Usually resend entire PUT request | Can retry only the **failed part** |
| Parallel upload | Not split into parts at S3 level | Can send multiple parts concurrently |
| Failure cleanup management | Simpler | Must Abort or use lifecycle rules to clean incomplete parts |
| Best suited for files | Small/medium, stable connection | Large, requiring retry/resume or parallelism |
| Overwriting same key | Updates current version | Complete creates/updates current object |

There is no single multipart threshold that fits every product. The decision depends on file size, network environment, throughput targets, resource limits, request costs, and SLAs.

## 5. How does multipart upload on S3 work?

### 5.1. Multipart lifecycle

A multipart upload has at least three stages:

1. **CreateMultipartUpload:** specify bucket/key and metadata like Content-Type, receiving an `uploadId` that identifies the ongoing upload session.
2. **UploadPart:** send data for each part with **partNumber** (1–10,000) and `uploadId`; S3 returns a distinct `ETag` for each successful part.
3. **CompleteMultipartUpload:** send the list of parts in **ascending partNumber order**, along with their corresponding ETags; S3 assembles the parts into a complete object.

If the upload fails or the user cancels, call **AbortMultipartUpload** to clean up transferred parts. An `uploadId` that has not been completed or aborted is not a finished object and cannot be fetched via GET by key.

~~~mermaid
stateDiagram-v2
    [*] --> NotStarted
    NotStarted --> Uploading: CreateMultipartUpload
    Uploading --> Uploading: UploadPart #1, #2,...
    Uploading --> Completed: CompleteMultipartUpload
    Uploading --> Aborted: AbortMultipartUpload
    Completed --> [*]: Object ready
    Aborted --> [*]: Parts cleaned up
~~~

~~~mermaid
sequenceDiagram
    participant A as Spring Boot
    participant S as Amazon S3

    A->>S: CreateMultipartUpload(bucket, key, metadata)
    S-->>A: uploadId
    A->>S: UploadPart(uploadId, partNumber=1, bytes)
    S-->>A: ETag #1
    A->>S: UploadPart(uploadId, partNumber=2, bytes)
    S-->>A: ETag #2
    A->>S: UploadPart(uploadId, partNumber=3, bytes)
    S-->>A: ETag #3
    alt all parts succeed
        A->>S: CompleteMultipartUpload(parts + ETags)
        S-->>A: Object completed
    else unrecoverable error
        A->>S: AbortMultipartUpload(uploadId)
        S-->>A: Abort incomplete upload
    end
~~~

Parts can be uploaded **out of order** or re-uploaded with the same `partNumber`. S3 uses the latest successfully uploaded part for that partNumber within the same uploadId. When completing, the application must send the exact ETags of the final accepted parts sorted by ascending partNumber.

### 5.2. Size rules and limits

| Property | Rule to remember |
| --- | --- |
| Part number | Integer from **1 to 10,000** |
| Part size | Typically **5 MiB to 5 GiB**; the **last part** may be smaller than 5 MiB |
| Maximum number of parts | **10,000** in a single multipart upload |
| Upload ID | Issued by S3; binds an upload session to a bucket/key |
| Part ETag | Value returned by UploadPart; must be reused verbatim in Complete |
| Object ETag after Complete | **Not by default the MD5** of the entire content |
| Object metadata | Attributes like Content-Type are declared when **initiating multipart** |
| Incomplete data | Uploaded parts not yet Completed/Aborted can still incur storage charges |

A 100 MiB object with 8 MiB parts needs 13 parts, where the 4 MiB final part is allowed. Using 8 MiB parts for an object larger than roughly 78 GiB would hit the 10,000-part limit; real designs must **compute part size based on expected object size** or let the SDK transfer layer choose the partitioning.

## 6. Implementing multipart upload manually with `S3Client`

This section uses the **synchronous AWS SDK v2** to illustrate the multipart lifecycle and memory management. The code reads at most 8 MiB per iteration, uploads each part sequentially, and then calls Complete. This is great for learning or controlled upload flows; when higher throughput is needed, consider `S3TransferManager` in the next section.

### 6.1. Sample service with Abort on failure

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.AbortMultipartUploadRequest;
import software.amazon.awssdk.services.s3.model.CompleteMultipartUploadRequest;
import software.amazon.awssdk.services.s3.model.CompletedMultipartUpload;
import software.amazon.awssdk.services.s3.model.CompletedPart;
import software.amazon.awssdk.services.s3.model.CreateMultipartUploadRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.UploadPartRequest;
import software.amazon.awssdk.services.s3.model.UploadPartResponse;

@Service
public class BoundedMultipartUploader {
    private static final int PART_BYTES = 8 * 1024 * 1024;
    private static final int MAX_PARTS = 10_000;

    private final S3Client s3;
    private final String bucket;

    public BoundedMultipartUploader(
            S3Client s3,
            @Value("${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String upload(InputStream source, String verifiedContentType)
            throws IOException {

        String key = "documents/" + UUID.randomUUID();

        // Pre-read one chunk to handle small or empty files.
        byte[] firstChunk = source.readNBytes(PART_BYTES);

        if (firstChunk.length < PART_BYTES) {
            // Smaller than 8 MiB: a single PUT is enough, including 0-byte files.
            s3.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .contentType(verifiedContentType)
                            .build(),
                    RequestBody.fromBytes(firstChunk));
            return key;
        }

        String uploadId = s3.createMultipartUpload(
                CreateMultipartUploadRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .contentType(verifiedContentType)
                        .build()
        ).uploadId();

        List<CompletedPart> completed = new ArrayList<>();
        int partNumber = 1;

        try {
            byte[] chunk = firstChunk;
            while (chunk.length > 0) {
                if (partNumber > MAX_PARTS) {
                    throw new IllegalArgumentException(
                            "Exceeded 10,000 parts: increase PART_BYTES");
                }

                UploadPartResponse result = s3.uploadPart(
                        UploadPartRequest.builder()
                                .bucket(bucket)
                                .key(key)
                                .uploadId(uploadId)
                                .partNumber(partNumber)
                                .build(),
                        RequestBody.fromBytes(chunk));

                completed.add(CompletedPart.builder()
                        .partNumber(partNumber)
                        .eTag(result.eTag())
                        .build());

                partNumber++;
                chunk = source.readNBytes(PART_BYTES);
            }

            s3.completeMultipartUpload(
                    CompleteMultipartUploadRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .uploadId(uploadId)
                            .multipartUpload(
                                    CompletedMultipartUpload.builder()
                                            .parts(completed)
                                            .build())
                            .build());
            return key;
        } catch (IOException | RuntimeException failure) {
            // If an uploadId was created, attempt to abort incomplete parts.
            try {
                s3.abortMultipartUpload(
                        AbortMultipartUploadRequest.builder()
                                .bucket(bucket)
                                .key(key)
                                .uploadId(uploadId)
                                .build());
            } catch (RuntimeException abortFailure) {
                failure.addSuppressed(abortFailure);
            }
            throw failure;
        }
    }
}
~~~

**Explaining each design choice:**

- `readNBytes(PART_BYTES)` reads until enough bytes are collected, EOF is reached, or an error occurs; the example requires Java 11+ (modern Spring Boot usually uses Java 17+). Only **one or a few part arrays** live in RAM, never a byte array of the entire file.
- If the file is smaller than 8 MiB, the service uses a single PUT. If the file is exactly 8 MiB, this example uses a one-part multipart upload; that is valid, though it uses an extra request, so production code can choose a different branch depending on requirements.
- Each `UploadPartResponse.eTag()` is stored with its partNumber. The `completed` list is appended sequentially, so it is already sorted in ascending order before Complete.
- `PART_BYTES = 8 MiB` satisfies the 5 MiB minimum for every part except the last. In this sequential example, every non-final chunk is guaranteed to be 8 MiB.
- If an IOException occurs while reading the source, or an SDK error happens during part upload or Complete, the `catch` block attempts to call Abort. If Abort also fails, that error is attached as a **suppressed exception** to preserve the original root cause.
- The service intentionally **does not close `source`** because the stream is owned by the caller. Calling code must use try-with-resources or close it according to its lifecycle.
- If Complete times out after S3 has actually processed it successfully, the outcome may be **ambiguous to the client**. Real systems should re-query via `HeadObject`/version ID, perform controlled retries, and reconcile state instead of blindly assuming total failure.

The code above only illustrates the upload mechanics. For production deployment, add file validation, rate/concurrency limits, maximum source length enforcement, dynamic part sizing, controlled logging of uploadId, timeouts, checksums, and upload state monitoring. Never invoke `upload(InputStream, ...)` directly on unbounded data without quotas.

### 6.2. How to retry a single part?

Example when part #3 experiences a transient error:

~~~text
uploadId = "u-123"
part 1 → succeeded → ETag-A
part 2 → succeeded → ETag-B
part 3 → connection lost
part 3 → retried with partNumber=3 → succeeded → ETag-C
part 4 → succeeded → ETag-D

Complete: [(1, ETag-A), (2, ETag-B), (3, ETag-C), (4, ETag-D)]
~~~

Retrying with the same `uploadId` and `partNumber` can **replace the earlier part** if S3 already received it; be sure to update the ETag from the successful response you intend to keep. The AWS SDK already has configurable retry logic, so do not stack arbitrary extra retries across multiple layers.

If uploading in parallel, parts can finish in any order, but **Complete requires the list sorted in ascending partNumber order**. Data for each part must be reliably re-readable on retry; a local file or a per-part buffer is far easier to retry than a one-way, non-seekable input stream.

### 6.3. Abort permissions and cleaning up abandoned uploads

The Abort call only runs if the application still knows the `uploadId` and reaches its error handler. If the process is killed, the host loses power, or the container is evicted, the `catch` block never runs. Therefore, complement it with an **S3 Lifecycle rule with `AbortIncompleteMultipartUpload`** after a policy-appropriate number of days.

~~~text
Lifecycle rule (concept):
- Prefix: documents/
- Abort incomplete multipart uploads after: N days
- N is chosen according to valid upload duration and recovery requirements.
~~~

Do not confuse this rule with deleting completed objects. Incomplete parts can incur storage costs; periodic cleanup rules eliminate stale fragments. If your system supports resuming uploads after many hours or days, pick a sufficiently long lifecycle window and persist `uploadId` and partNumber/ETag state in durable storage per policy.

## 7. S3 Transfer Manager: high-level option for large files

Instead of writing the Create → UploadPart → Complete → Abort loop manually, AWS SDK v2 provides **`S3TransferManager`** to handle file transfers, multipart orchestration, progress tracking, and many retry details. It fits well when the source is already a `Path` or when the project needs high throughput and managed uploads/downloads.

Conceptual example using Transfer Manager for a local file:

~~~java
import java.nio.file.Path;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.transfer.s3.S3TransferManager;
import software.amazon.awssdk.transfer.s3.model.UploadFileRequest;

// Requires AWS SDK v2 dependency: s3-transfer-manager and
// compatible HTTP/CRT libraries for the chosen S3AsyncClient.
try (S3AsyncClient asyncClient =
             S3AsyncClient.crtBuilder()
                     .region(Region.AP_SOUTHEAST_1)
                     .build();
     S3TransferManager manager =
             S3TransferManager.builder()
                     .s3Client(asyncClient)
                     .build()) {

    UploadFileRequest request = UploadFileRequest.builder()
            .source(Path.of("reports/large-report.csv"))
            .putObjectRequest(p -> p
                    .bucket("training-private-docs")
                    .key("documents/reports/large-report.csv")
                    .contentType("text/csv"))
            .build();

    manager.uploadFile(request).completionFuture().join();
}
~~~

The snippet above is an **API-level illustration**. To build, add `software.amazon.awssdk:s3-transfer-manager` matching the AWS SDK v2 BOM and the **appropriate AWS CRT dependency** if using `S3AsyncClient.crtBuilder()`; verify the exact artifacts/versions for your project. The AWS SDK also provides other async multipart client configurations depending on the version.

In a long-running Spring Boot application, do not create and close `S3TransferManager` and `S3AsyncClient` per request as shown in the `try-with-resources` demo. Configure them as **shared beans**, let Spring manage their lifecycle, and inject them into services. The transfer library handles uploads/downloads from files or supported sources; you still need to bound concurrency, bandwidth, quotas, and track completion results.

**Do not assume `S3Template.upload` automatically uses multipart for every `InputStream`.** The Spring Cloud AWS abstraction reduces boilerplate, yet exact upload mechanics depend on the API and version. When guaranteed multipart, concurrency, and part-level retries are required, using an explicitly configured SDK transfer API is easier to verify.

## 8. Direct upload from browser: presigned PUT and presigned multipart

When clients upload large files, Spring Boot does not have to receive and relay every byte. The backend can manage only permissions and upload sessions while the **browser/mobile app sends data straight to S3**.

### 8.1. Single presigned PUT

~~~mermaid
sequenceDiagram
    actor U as Client
    participant A as Spring Boot API
    participant D as Database
    participant S as Private S3 bucket

    U->>A: Request upload (name, type, size)
    A->>A: Authenticate, check quota, generate key
    A->>D: Save PENDING_UPLOAD status
    A-->>U: Presigned PUT URL + key (short-lived)
    U->>S: PUT file directly using URL
    S-->>U: PUT result
    U->>A: Notify completion
    A->>S: HEAD object, verify attributes
    A->>D: Transition to READY status if valid
~~~

A presigned PUT URL only permits executing the signed request within the expiration window/signing constraints; it **does not make a private bucket public**. The URL acts as a bearer capability: anyone holding an unexpired URL can use it within its signed scope. Avoid logging full URLs and never issue URLs before verifying user/tenant permissions.

With a PUT URL, signed headers must match the request the client sends. If strict request-level size limits must be enforced, consider a mechanism supporting size conditions such as **presigned POST policy**, or post-upload size checks and quota enforcement. Do not assume a presigned PUT prevents oversized uploads merely because the URL has a short expiration.

### 8.2. Presigned multipart for very large files

A common implementation pattern:

1. Spring Boot checks permissions, generates a key, and calls `CreateMultipartUpload` to obtain an `uploadId`.
2. The backend issues a **presigned UploadPart URL** for each allowed partNumber, bound to the exact bucket/key/uploadId.
3. The client splits the file and PUTs each part directly to S3, collecting the **ETag** from each UploadPart response.
4. The client sends the list of partNumbers/ETags to the backend. The backend validates the upload session, owner, quota, and submitted parts before calling `CompleteMultipartUpload`.
5. If the user cancels, the backend calls `AbortMultipartUpload`; add lifecycle cleanup in case the client never returns.

~~~mermaid
flowchart LR
    Browser["Browser: split file into parts"] -->|"request URL per part"| API["Spring Boot: authenticate and sign"]
    API -->|"CreateMultipartUpload / presign"| S3["Private S3 bucket"]
    API -->|"Presigned UploadPart URLs"| Browser
    Browser -->|"PUT parts #1..N directly"| S3
    Browser -->|"Per-part ETag + complete"| API
    API -->|"CompleteMultipartUpload"| S3
~~~

Proper **S3 CORS** configuration is required when a browser calls S3 cross-origin. For JavaScript clients to read the ETag from response headers, CORS typically needs to expose `ETag`. CORS **does not grant S3 permissions**; requests must still be properly signed and permitted by IAM/bucket policies.

Presigned multipart adds responsibilities: limiting URL lifetimes, tracking `uploadId`, preventing cross-user part mixing, blocking unauthorized Complete calls, aborting abandoned uploads, and handling per-part retries. Never allow clients to pass an arbitrary `uploadId`/key for the backend to Complete without verifying ownership.

## 9. Integrity, metadata, timeouts, and cost

### 9.1. Integrity checks

A successfully stored object does not automatically mean it matches the expected business document. To verify:

- Use **checksums** supported by AWS SDK/S3 during upload, such as SHA-256 or CRC depending on feature and algorithm. Multipart checksum rules can differ from a single PUT and require consistent metadata/checksums across parts and Complete.
- Inspect `Content-Length`, `Content-Type`, version ID, and checksums through appropriate APIs/responses.
- For applications requiring byte-for-byte proof, compute an independent hash at the source and after re-reading a sample; choose algorithms and workflows suited to object size and security requirements.

**Do not assume ETag equals the MD5 of the entire object**. Multipart object ETags are usually computed differently, and encryption settings/upload configuration also affect ETag semantics. Each part's ETag from `UploadPartResponse` must still be recorded accurately for Complete.

### 9.2. When is metadata set?

With multipart, attributes such as `Content-Type`, `Content-Disposition`, user-defined metadata, and encryption options are typically declared during **CreateMultipartUpload**. `UploadPart` transfers part bytes; it is not the place to reset object-level metadata.

Example:

~~~java
var created = s3.createMultipartUpload(
        CreateMultipartUploadRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("application/pdf")
                .metadata(java.util.Map.of("source", "portal"))
                .build());
~~~

Once Complete succeeds, the final object carries the metadata matching those declared attributes. Avoid putting secrets, access tokens, sensitive personal data, or information that should not appear in S3 headers into metadata.

### 9.3. Controlling timeouts and retries

For large files, distinguish between:

- **Connection timeout:** time allowed to establish a TCP/TLS connection.
- **API call timeout:** maximum time for the entire SDK call.
- **Read/idle timeout:** an open connection making no byte progress.
- **Retry/backoff:** retry count, jitter, and total elapsed cap.
- **HTTP client connection pool / concurrency:** number of concurrent data transfers.

Do not set overly short timeouts for all large files, nor allow uploads to hang indefinitely. Timeout rules must reflect maximum file size, expected network speed, and resume/abort capabilities. When a caller cancels an HTTP request, backend upload work may continue unless cancellation is propagated; design explicit lifecycles.

### 9.4. Sources of cost

Streaming or multipart does not eliminate S3 costs. Potential charges include:

- Request counts for PUT/UploadPart/Complete/HEAD/GET.
- Storage for completed objects and **storage for incomplete multipart parts**.
- Data transfer across services, across Regions, or out from the cloud.
- SSE-KMS requests, lifecycle/replication/storage-class charges depending on configuration.

Smaller parts increase request counts and overhead; larger parts increase per-task memory, retry duration, and the impact of part failures. Monitor throughput, total part count, and cost instead of picking a fixed `partSize` blindly.

## 10. Controlled testing of streaming and multipart

### 10.1. Testing layers

| Testing level | Suitable scope | Limitations |
| --- | --- | --- |
| Unit test (mock) | Chunk boundaries, partNumber, ETag list, Abort called on error | Does not verify S3 actually assembles parts |
| Integration test with S3-compatible emulator | Multi-part upload, Complete, GET bytes, Abort, proper stream closing | Does not guarantee identical IAM/KMS or AWS edge cases |
| AWS sandbox | Permissions, timeouts, checksums, versioning, lifecycle, aborted uploads, and cost | Requires test bucket/quotas, least-privilege role, data cleanup |

Recommended test scenario:

1. Create a dedicated sandbox bucket, random keys under `documents/lab-<id>/`, and a role with exact PUT/GET/Abort permissions.
2. Upload a file **smaller than part size** to exercise the single-PUT branch and a file **larger than 2× part size** to exercise multiple UploadParts.
3. GET the object via stream and compare **bytes** or a reliable checksum against the source data.
4. Simulate failure on the second part via mock or fault-injecting test setup; verify Abort is called with the right `uploadId`.
5. Test an empty file, a file equal to `partSize`, a file 1 byte larger than `partSize`, and a file whose final part is under 5 MiB.
6. Verify metadata, Content-Type, response status, IAM permissions, and key state after Complete.
7. Verify lifecycle cleanup for abandoned uploads on the AWS sandbox and delete all test objects/versions.

Do **not** use production buckets, real user files, or production keys for fault injection and delete/abort tests.

### 10.2. Illustrative content-verification test

This is example logic to plug into a test framework's setup/teardown; it does not provision a real AWS environment:

~~~java
byte[] expected = new byte[20 * 1024 * 1024 + 123];
new java.util.Random(42).nextBytes(expected);

String key;
try (var input = new java.io.ByteArrayInputStream(expected)) {
    key = uploader.upload(input, "application/octet-stream");
}

byte[] actual;
try (var source = s3.getObject(b -> b
        .bucket(bucket)
        .key(key))) {
    actual = source.readAllBytes(); // Only do this in size-bounded tests.
}

if (!java.util.Arrays.equals(expected, actual)) {
    throw new AssertionError("Multipart upload integrity mismatch");
}
~~~

`readAllBytes()` is used **only in size-bounded tests** for straightforward comparison. Production downloads of large files should copy streams or compare checksums incrementally. In real tests, clean up keys in `finally` and abort incomplete uploads; if versioning is enabled on the bucket, handle version cleanup explicitly.

### 10.3. Resilience and failure-mode testing

Several scenarios should be designed upfront:

- Client drops connection mid-`UploadPart`: retry the individual part if `uploadId` remains valid and the source data can be re-read.
- Application loses connectivity after `CompleteMultipartUpload`: inspect the result via HEAD/version/reconciliation to avoid creating duplicate business objects.
- Process is killed before Abort: lifecycle rules clean up expired incomplete parts.
- Browser finishes uploading but never notifies the backend: the backend needs a `PENDING_UPLOAD` state, timeouts, and verification logic to transition to `READY`.
- User cancels while multiple parts are in flight: stop in-flight tasks, then Abort; some running requests may need to finish before cleanup completes.

## 11. Comparison with Azure and Google Cloud

All three clouds support large file transfers and API-based ingestion, though **chunking protocols and authentication differ**:

| Problem | AWS / Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Streaming read | S3 GET stream / range | Blob download stream/range | Object read/range |
| Standard object upload | PutObject | Upload blob | Upload/create object |
| Large file with part-level recovery | S3 Multipart Upload (UploadPart + Complete) | Block blob: stage blocks + commit block list | Resumable upload session |
| Application identity | IAM role / AWS SDK credentials | Managed identity / Azure Identity | Service account / Application Default Credentials |
| Temporary URL for clients | Presigned URL | Shared Access Signature (SAS) | Signed URL |
| Cleaning incomplete transfers | AbortMultipartUpload + lifecycle cleanup | Uncommitted blocks managed per provider policy | Unfinished sessions managed per provider protocol |

The **SPRING_CLOUD_PROVIDER_INTEGRATION** module can use an application interface such as:

~~~java
public interface ObjectTransferPort {
    String upload(java.io.InputStream source,
                  long knownLength,
                  String contentType) throws java.io.IOException;

    void download(String trustedObjectKey,
                  java.io.OutputStream destination)
            throws java.io.IOException;
}
~~~

The AWS adapter uses `S3Client`/`S3TransferManager`; Azure or GCP adapters use their corresponding SDKs. However, **do not force every provider to share the exact `uploadId`/`partNumber`/`ETag` terminology**. The business contract should describe size, ownership, streams, and outcomes; multipart/resume strategies, checksums, and signed-upload details belong inside each adapter.

When evaluating multi-cloud options, also compare cross-region transfer fees, quotas, secret/identity setup, retry behavior, emulator testing experience, IAM/RBAC permissions, and provider cleanup processes.

## 12. Practice exercises and review questions

### Exercise 1 — Measuring memory

Build a Spring Boot endpoint in a sandbox that accepts a 30 MiB file. Compare the flow using `MultipartFile.getBytes()` against `getInputStream()` with `RequestBody.fromInputStream(..., size)`. Observe heap usage, processing time, and concurrent request limits. Explain why `getInputStream()` does not guarantee the servlet container never buffered the multipart form.

### Exercise 2 — Manual multipart

Using the sample uploader, sequentially upload an empty file, 2 MiB, 8 MiB, 8 MiB + 1 byte, 20 MiB, and 50 MiB; record part counts, final part sizes, durations, and HEAD results. Verify downloaded bytes match the source. Predict the part count before running.

### Exercise 3 — Fault injection and cleanup

Use a mock client or S3 emulator to make the second part return an error. Verify the code does not call Complete, does call Abort, and preserves the original exception. Also simulate Abort failing and inspect the suppressed exception. Explain why lifecycle cleanup is still required.

### Exercise 4 — Browser direct upload

Design an API that creates an upload session, signs UploadPart URLs, verifies ETags/owner before Complete, and supports aborting sessions. Specify which endpoints require authentication, how URL lifetimes are bounded, how clients read ETags via CORS, and how to prevent completing another user's `uploadId`.

### Exercise 5 — Multi-cloud evaluation

Create a plan table for uploading a 2 GiB file on AWS, Azure, and GCP: transfer mechanism, resume support, workload identity, access control, and cleanup. Propose a shared business interface and identify which capabilities must remain provider-specific.

### Self-check questions

1. At what layer do streaming and multipart upload differ?
2. Why should you avoid reading an entire `MultipartFile` into a byte array when many users upload concurrently?
3. What can happen if `RequestBody.fromInputStream` receives an inaccurate `contentLength`?
4. In which steps of multipart upload are `UploadId`, `partNumber`, and `ETag` used?
5. Why must `CompletedPart` entries be ordered by `partNumber` when calling Complete?
6. When is the final part allowed to be smaller than 5 MiB?
7. When an upload terminates abruptly and `catch` never runs, how are leftover parts cleaned up?
8. Why should the ETag of a multipart object not be treated as the MD5 of its content?
9. Why does `StreamingResponseBody` not automatically turn synchronous `S3Client` into non-blocking I/O?
10. When should you prefer `S3TransferManager` or presigned multipart over writing a manual UploadPart loop?
11. Which errors warrant retrying individual parts and which should halt to inspect IAM/quotas?
12. Why should a multi-cloud interface abstract upload/download while keeping multipart mechanics inside adapters?

By the end of this lesson, you can build memory-bounded file transfer pipelines in Spring Boot, understand the full **CreateMultipartUpload → UploadPart → Complete/Abort** lifecycle, control access, retries, checksums, and orphaned resources, and select the right transfer strategy across cloud providers.
