# Multipart Upload, Checksums, and Data Transfer Optimization in Amazon S3

When an application uploads a file of a few kilobytes to Amazon S3, a single `PutObject` call is usually straightforward. However, when transferring a 30 GiB video from a user's machine, a 2 TiB backup from EC2, or thousands of files over an unstable network, sending the entire payload in a single request introduces major drawbacks: a network drop near the end can force restarting from scratch, bandwidth is underutilized, and end-to-end data integrity is harder to verify.

**Multipart upload** splits a large object into multiple **parts**, uploads them independently or in parallel, retries only failed parts, and finally assembles them into a single object in Amazon S3. **Checksums** detect data corruption in transit or when reconciling stored objects. **Data transfer optimization** tunes part sizes, concurrency, network locality, protocols, retries, and measurement tools to balance throughput, reliability, security, and cost.

This lesson belongs to the **S3 Object Storage** chapter of the **CLOUD_PROVIDERS_AWS** module. These techniques apply when Java/Spring Boot applications on EC2, ECS, EKS, or Lambda transfer data to S3, when systems integrating RDS, events, and serverless pipelines ingest files, or when designing backups, monitoring, and recovery across multiple AWS accounts and Regions.

> **Principles:** Use multipart uploads for sufficiently large objects and reliable transfers; select appropriate checksums to verify actual **content integrity**; clean up incomplete multipart uploads; and optimize using real measurements rather than blindly cranking up parallel requests.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the `CreateMultipartUpload → UploadPart → CompleteMultipartUpload` lifecycle, along with `UploadId`, `PartNumber`, and `AbortMultipartUpload` behavior.
2. State the limits on object size, part count, part size, and how to calculate an appropriate part size.
3. Distinguish `ETag` from checksums, and understand `FULL_OBJECT` vs. `COMPOSITE` checksums.
4. Select `CRC64NVME`, `CRC32C`, `SHA256`, or other algorithms based on integrity goals and API support.
5. Use the AWS CLI to perform managed uploads, inspect checksums, list incomplete multipart uploads, and tune transfer parameters.
6. Understand how the AWS SDK for Java 2.x `S3TransferManager` manages large uploads, concurrency, and credentials.
7. Troubleshoot timeouts, `SlowDown`, `BadDigest`, IAM/KMS permission failures, and objects missing after part uploads.
8. Evaluate security, data durability, request/transfer costs, Region placement, and cleanup of failed multipart uploads.

## 2. Object Storage and Why Multipart Upload Helps

An S3 object is identified by its **bucket** and **object key** within that bucket. Buckets are tied to an AWS Region; objects store payload bytes and metadata such as Content-Type, encryption, storage class, and checksums. S3 does not require pre-allocating a block filesystem like EBS, though applications must understand object-level APIs and IAM permissions.

There are two fundamental upload approaches:

| Criterion | Single-part `PutObject` | Multipart Upload |
|---|---|---|
| Data transmission | Single request containing the entire object | Multiple `UploadPart` calls, finalized with `CompleteMultipartUpload` |
| Retry on mid-transfer failure | Typically must re-send the whole object | Re-send only the failed part; keep successful parts |
| Parallelism | One logical upload stream | Can upload multiple parts concurrently |
| Session management | No separate UploadId | Uses `UploadId`, part list, and complete/abort operations |
| Checksum | Full-object checksum | Full-object or composite checksum depending on algorithm |
| Management overhead | Fewer requests | More requests, and orphaned parts can incur storage charges |
| Best suited for | Small files, simple workflows | Large files, unreliable networks, high-throughput requirements |

**AWS recommendation:** Once object size reaches roughly **100 MB**, consider using multipart upload. This is a design guideline, **not** a hard minimum size for multipart uploads; the AWS CLI and SDKs may automatically choose a lower threshold.

### 2.1. Illustrating a 600 MiB File

Suppose you upload a 600 MiB file using a 100 MiB part size:

~~~mermaid
flowchart TD
    F["Source file 600 MiB"] --> P1["Part 1: 100 MiB"]
    F --> P2["Part 2: 100 MiB"]
    F --> P3["Part 3: 100 MiB"]
    F --> P4["Part 4: 100 MiB"]
    F --> P5["Part 5: 100 MiB"]
    F --> P6["Part 6: 100 MiB"]
    P1 --> S["Amazon S3 - UploadId"]
    P2 --> S
    P3 --> S
    P4 --> S
    P5 --> S
    P6 --> S
    S --> C["CompleteMultipartUpload"]
    C --> O["Single object at the target key"]
~~~

If Part 4 fails due to a network drop, the client **does not need** to re-upload the five other parts S3 already received. It retries Part 4 and completes the upload once all parts are accounted for.

This differs from **creating six separate objects**: before completion, parts are tracked under a single multipart upload ID. After completion, applications access the result through **one object key**.

## 3. Multipart Upload API Lifecycle and States

### 3.1. Initiate: `CreateMultipartUpload`

The client submits a request specifying bucket, key, storage class (if any), metadata, `Content-Type`, encryption mode, checksum algorithm/type, and other attributes. S3 returns an **`UploadId`** identifying the active upload session.

Within the same bucket and key, multiple **incomplete** multipart uploads with distinct `UploadId`s can exist simultaneously. Keys do not act as mutex locks: applications still need overwrite controls if multiple producers target the same key.

Metadata and encryption parameters are typically fixed at **initiation time**. To change key properties after uploading parts, you generally must initiate a new multipart upload or run a post-completion copy/metadata update.

### 3.2. Send Data: `UploadPart`

For each part:

- The client sends `Bucket`, `Key`, `UploadId`, `PartNumber` (1–10,000), the part's byte payload, and any required checksum/parameters.
- S3 responds with the **part's ETag** and optionally the part's checksum.
- Parts can be uploaded **out of order**, enabling parallelism.
- Re-uploading the **same `PartNumber` under the same `UploadId`** **replaces** the previously uploaded content for that part number.

Clients must track a mapping of **`PartNumber` → `ETag` and required checksums**, especially when implementing the multipart API directly. Successfully uploading parts **does not yet create a complete object** readable via `GetObject`.

### 3.3. Finalize: `CompleteMultipartUpload`

Once all parts are uploaded, the client submits the list of parts and ETags in **ascending part number order**, along with checksums when required by the checksum mode. S3 validates and assembles the parts into the final object. Upon successful completion, the object becomes immediately accessible under S3's **strong read-after-write consistency** model.

**Distinguish part upload success from upload completion:** receiving HTTP 200 on individual `UploadPart` calls only proves those parts arrived. Only after `CompleteMultipartUpload` succeeds is the object finalized. Note that `CompleteMultipartUpload` can return an initial HTTP 200 response while assembling and then include an error inside the response body; AWS SDKs handle this automatically. If writing a custom HTTP client, always **parse the full response body**, not just the HTTP status code.

### 3.4. Cancel Session: `AbortMultipartUpload`

When an upload is no longer needed, call `AbortMultipartUpload` with the exact bucket, key, and `UploadId` to release uploaded parts.

Any **in-flight** `UploadPart` requests may finish right after an abort is issued; applications should stop active upload workers first and verify the part/upload list per API guidance if strict cleanup is required. S3 bills storage for uploaded parts from the time they are uploaded until **completion or abort** frees them.

~~~mermaid
sequenceDiagram
    participant C as Client / Transfer Manager
    participant S as Amazon S3
    C->>S: CreateMultipartUpload (bucket, key, checksum)
    S-->>C: UploadId
    par Multiple parts
        C->>S: UploadPart #1
        S-->>C: ETag / checksum #1
    and
        C->>S: UploadPart #2
        S-->>C: ETag / checksum #2
    and
        C->>S: UploadPart #3
        S-->>C: ETag / checksum #3
    end
    alt All parts valid
        C->>S: CompleteMultipartUpload (parts, ETags, checksums)
        S-->>C: Object / VersionId / checksum
    else Canceled or unrecoverable error
        C->>S: AbortMultipartUpload
        S-->>C: Parts freed after cleanup completes
    end
~~~

## 4. Limits to Know Before Splitting Parts

Per current AWS S3 multipart documentation for general purpose buckets:

| Limit | Value |
|---|---|
| Maximum object size | **48.8 TiB** (approx. 50 TB decimal) |
| Maximum number of parts per upload | **10,000** |
| Valid `PartNumber` range | **1 to 10,000** |
| Size of **every part except the last** | **5 MiB** to **5 GiB** |
| Size of the last part | Can be **smaller than 5 MiB** |
| Max results per page for `ListParts` | **1,000 parts** |
| Max results per page for `ListMultipartUploads` | **1,000 uploads** |

Limits may differ for specialized bucket types or tools. When practicing, distinguish **MB, MiB, GB, GiB, TB, and TiB**; 1 MiB = 1,048,576 bytes, whereas 1 MB = 1,000,000 bytes.

### 4.1. Formula for Selecting Part Size

Let:

- `F`: total bytes of the object.
- `P`: bytes per standard (non-final) part.
- `N = ceil(F/P)`: total parts to send.

Requirements:

\[
N = \left\lceil \frac{F}{P} \right\rceil \leq 10{,}000
\]

and `5 MiB ≤ P ≤ 5 GiB` for every non-final part; the last part can be smaller.

**2 TiB example:** choosing a 64 MiB part size gives `2 TiB = 2,097,152 MiB`, so `N = 2,097,152 / 64 = 32,768` parts, which **exceeds the limit**. Choosing `256 MiB` yields `8,192` parts, which is valid. Beyond arithmetic, balance request counts, RAM buffers, retry cost, and link stability.

| File Size | Sample Part Size | Approx. Part Count | Assessment |
|---|---:|---:|---|
| 600 MiB | 100 MiB | 6 | Easy retry management |
| 10 GiB | 64 MiB | 160 | Supports reasonable concurrency |
| 100 GiB | 128 MiB | 800 | Monitor throughput |
| 2 TiB | 64 MiB | 32,768 | **Invalid** |
| 2 TiB | 256 MiB | 8,192 | Valid part count |
| 10 TiB | 1 GiB | 10,240 | **Invalid** |
| 10 TiB | 2 GiB | 5,120 | Valid part count |

Values in the table are **calculation examples**, not universal presets for every network. Part size selection must consider RAM (especially when buffering multiple parts concurrently), network latency, timeouts, and file counts.

### 4.2. Part Numbers and Composite Checksums

Although the API allows uploading parts out of order during transfer, **when using composite/part-level checksums, the part list at completion must be contiguous and start at 1**. AWS warns that completing with non-contiguous part numbers under that mode can fail with `HTTP 500 Internal Server Error`.

Good operational discipline: number parts **1, 2, 3, ...**, record metadata for every part, submit the completion list in ascending order, and validate part counts before completing.

## 5. What Is a Checksum and What Does It Verify?

A checksum is a value computed from data bytes using a deterministic algorithm. During transfer, the client computes the checksum prior to or while uploading; S3 recomputes it over received bytes and compares. On mismatch, S3 rejects the upload rather than storing corrupted data.

A checksum answers **"do the received bytes match the bytes originally fed into the calculation?"** It does not prove who authored the data, nor does it replace TLS, IAM policies, encryption, or cryptographic digital signatures.

### 5.1. Common Algorithms

| Algorithm | Characteristics | Suggested Use |
|---|---|---|
| `CRC64NVME` | 64-bit CRC; default checksum chosen by S3 when none is specified | Fast integrity checks; supports full-object checksums for multipart |
| `CRC32` | 32-bit CRC, fast | Detecting transmission errors; not a tamper-resistant hash |
| `CRC32C` | Castagnoli 32-bit CRC, hardware-optimized on many CPUs | Fast checks; supports both full-object and composite in multipart |
| `SHA1` | Older cryptographic hash with collision risks | Legacy compatibility only; not for tamper resistance |
| `SHA256` | 256-bit cryptographic hash | Comparing content against independent digests; composite in S3 multipart |
| `MD5` | Legacy hash, no longer suitable for security assurances | Legacy compatibility/checks |
| `SHA512`, `XXHASH64`, `XXHASH3`, `XXHASH128` | Additional algorithms supported by S3 depending on API/version | Choose per checksum requirements and supported checksum types |

**Note:** Many systems use SHA256 for independent manifests/digests. However, the `SHA256` checksum returned by S3 for a **`COMPOSITE` multipart upload** does not generally equal `sha256sum` run on the **entire file**. To match a whole-file digest, use an appropriate **full-object checksum** or store an independent whole-file SHA256 digest in manifest/metadata and verify after download.

### 5.2. Automatic Integrity Verification by S3

Current AWS tools typically compute checksums before or during upload, and S3 independently verifies them. If no algorithm is specified and the SDK supplies no checksum, S3 defaults to `CRC64NVME` per current documentation.

Checksum values can be persisted in object metadata and retrieved via `HeadObject` or `GetObjectAttributes` when supported by permissions and operations. **Having an S3 checksum** verifies integrity over the wire, whereas proving data still matches an external source requires retaining a **trusted source digest** and ensuring both sides use the same algorithm and computation method.

## 6. Full-Object Checksums vs. Composite Checksums

This is the single most important distinction when combining multipart upload with checksums.

### 6.1. `FULL_OBJECT`

A **full-object checksum** is computed across the **entire object byte stream**, from first byte to last. For multipart uploads, S3 supports full-object checksums for CRC algorithms that can be mathematically combined from part checksums without re-reading the entire payload:

- `CRC64NVME`.
- `CRC32`.
- `CRC32C`.

When the client supplies the expected full-object checksum (and object size per API rules), S3 validates it at completion. On mismatch, S3 can reject with `BadDigest`.

### 6.2. `COMPOSITE`

A **composite checksum** is built from the checksums **of individual parts**, aggregated according to an algorithm-specific rule. It validates part-level integrity well, yet **is not equivalent** to running that algorithm across the whole contiguous file.

For example, an object with three parts each having its own SHA256 checksum yields a `COMPOSITE` `ChecksumSHA256` value derived from the part-level digests, which will not equal `sha256sum whole-file.bin` in general.

### 6.3. Supported Combinations

| Algorithm | Full-Object Multipart | Composite Multipart |
|---|---|---|
| `CRC64NVME` | Yes | **No** |
| `CRC32` | Yes | Yes |
| `CRC32C` | Yes | Yes |
| `SHA1` | No | Yes |
| `SHA256` | No | Yes |
| `MD5` | No | Yes |
| `SHA512` and `XXHASH*` | No | Yes |

On single-part `PutObject`, checksums are always full-object. In multipart uploads, choose the **checksum algorithm and checksum type at `CreateMultipartUpload`** and keep parts, uploads, and completion consistent. Some newer algorithms require declaring the algorithm at initiation for the Complete request to be accepted.

### 6.4. Right vs. Wrong Verification Example

Suppose a vendor ships `backup.bin` alongside a manifest `sha256=...`:

- If uploaded via single-part `PutObject` with `SHA256`, you can compare the full-file digest directly under matching encoding rules.
- If uploaded via multipart and S3 stores a `COMPOSITE` `ChecksumSHA256`, **never** compare that string directly against the manifest SHA256 and conclude corruption.
- To verify a manifest SHA256, either download and run whole-file SHA256, use **S3 Batch Operations Compute checksum** where applicable to verify full-object digests, or store the independent source manifest digest with a matching verification workflow.
- If your primary goal is **multipart transfer integrity**, `CRC64NVME FULL_OBJECT` or `CRC32C FULL_OBJECT` is a practical choice.

## 7. ETag Is Not Always the Object's MD5

An **ETag** is an HTTP entity tag used to identify content versions and support conditional requests. While an ETag may resemble a hex hash string, never assume it **always** equals the MD5 of the entire payload.

| Case | Can ETag Equal Whole-Object MD5? |
|---|---|
| Single-part `PutObject` under AWS-documented conditions (e.g., SSE-S3) | May equal |
| Multipart upload | **No** |
| Certain encryption or copy modes | Do not assume |
| Uploads using tools with different part boundaries | ETags can differ even for identical object bytes |

For multipart uploads, the final ETag usually carries a `-N` suffix, such as:

~~~text
"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-8"
~~~

Here `8` typically reflects the number of parts assembled into the object. ETag is not a universal integrity proof for files. Applications needing verification should explicitly record **algorithm, checksum type, versionId/ETag, and digest source**, rather than casually referring to "S3's MD5."

**Important:** Checking `ETag` without inspecting `ChecksumType` can lead to false conclusions. An object uploaded via multipart and later copied differently may receive a different ETag or checksum representation even though its payload bytes never changed.

## 8. Working with AWS CLI: High-Level Managed Multipart Transfers

### 8.1. Prepare Environment

Examples below use AWS CLI v2, an IAM Identity Center profile named `dev`, and an **administrator-authorized bucket** in Region `ap-southeast-1`. Replace `amzn-s3-demo-bucket` with your real bucket name before running.

Verify identity and bucket location:

~~~bash
aws --version
aws sts get-caller-identity --profile dev

aws s3api get-bucket-location \
  --bucket amzn-s3-demo-bucket \
  --profile dev
~~~

Note: `GetBucketLocation` may return `null` for buckets in `us-east-1` due to legacy API conventions. When confirming Region programmatically, use `HeadBucket` per SDK/CLI guidance with an authorized account.

### 8.2. Upload a File with `aws s3 cp`

~~~bash
# Real impact: uploads the file and incurs charges per AWS pricing.
aws s3 cp "./large-video.mp4" \
  "s3://amzn-s3-demo-bucket/uploads/large-video.mp4" \
  --region ap-southeast-1 \
  --profile dev \
  --checksum-algorithm CRC64NVME
~~~

The high-level `aws s3 cp` command automatically chooses single-part vs. multipart based on its threshold, splits the file, uploads parts concurrently, retries failed parts, and completes the object. It is far more convenient than calling `s3api create-multipart-upload` manually for routine tasks.

On Windows PowerShell, the same command written on **one line** avoids Bash line-continuation differences:

~~~powershell
aws s3 cp ".\large-video.mp4" "s3://amzn-s3-demo-bucket/uploads/large-video.mp4" --region ap-southeast-1 --profile dev --checksum-algorithm CRC64NVME
~~~

### 8.3. Download and Verify Checksums

~~~bash
aws s3 cp \
  "s3://amzn-s3-demo-bucket/uploads/large-video.mp4" \
  "./large-video-downloaded.mp4" \
  --region ap-southeast-1 \
  --profile dev \
  --checksum-mode ENABLED
~~~

Depending on the object/checksum type, the CLI retrieves and validates the checksum. Note this is still a **data read incurring GET/transfer fees**. For end-to-end proof against the source system, compare the original file and downloaded file using the same algorithm, e.g.:

~~~bash
# Run in Bash or an environment with sha256sum
sha256sum large-video.mp4
sha256sum large-video-downloaded.mp4
~~~

If the two digests differ, investigate; if they match, both files match byte-for-byte per SHA256. Do not confuse this value with a composite `ChecksumSHA256` returned by S3.

### 8.4. Inspect Metadata and Checksums Without Downloading the Full Object

~~~bash
aws s3api head-object \
  --bucket amzn-s3-demo-bucket \
  --key uploads/large-video.mp4 \
  --checksum-mode ENABLED \
  --profile dev \
  --region ap-southeast-1 \
  --query '{Bytes:ContentLength,ETag:ETag,ChecksumCRC64NVME:ChecksumCRC64NVME,ChecksumType:ChecksumType,VersionId:VersionId}' \
  --output json

aws s3api get-object-attributes \
  --bucket amzn-s3-demo-bucket \
  --key uploads/large-video.mp4 \
  --object-attributes ETag Checksum ObjectSize ObjectParts \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

These commands require matching permissions such as `s3:GetObject` / `s3:GetObjectAttributes` (and KMS permissions when SSE-KMS is used). Not every object has every checksum field; missing fields are omitted. `ObjectParts` is paginated and reflects how the object was uploaded.

## 9. Tuning AWS CLI for Speed and Resource Usage

High-level AWS CLI S3 commands expose dedicated tuning parameters:

| Parameter | Current CLI Default | Effect |
|---|---|---|
| `multipart_threshold` | `8MB` | File size at which multipart upload triggers |
| `multipart_chunksize` | `8MB` | Part size; minimum `5MB` for uploads |
| `max_concurrent_requests` | `10` | Maximum concurrent data transfer requests |
| `max_queue_size` | `1000` | Queued transfer tasks; affects RAM and progress tracking |
| `max_bandwidth` | Unlimited by default | Caps upload/download throughput |
| `use_accelerate_endpoint` | `false` | Uses S3 Transfer Acceleration when bucket supports it |

These are AWS CLI defaults at the time of writing, **not** performance guarantees, and may vary across CLI versions. Do not confuse the CLI's `multipart_threshold` with S3 API part-size limits.

### 9.1. Example Profile Configuration

~~~ini
[profile dev]
region = ap-southeast-1
output = json
s3 =
    multipart_threshold = 64MB
    multipart_chunksize = 32MB
    max_concurrent_requests = 12
    max_queue_size = 1000
    max_bandwidth = 80MB/s
~~~

*This is an illustrative snippet, not mandatory to apply.* In `~/.aws/config`, indent settings beneath the `s3` key consistently. You can also set them per profile via CLI:

~~~bash
# Modifies local CLI config for profile 'dev'; does not modify the bucket.
aws configure set s3.multipart_threshold 64MB --profile dev
aws configure set s3.multipart_chunksize 32MB --profile dev
aws configure set s3.max_concurrent_requests 12 --profile dev
aws configure set s3.max_bandwidth 80MB/s --profile dev
~~~

Do not alter real user profile settings without understanding their impact; always tune based on benchmarks in your actual environment.

### 9.2. Does Increasing Concurrency Always Boost Throughput?

No. On a 50 Mbps link, raising concurrency from 10 to 100 requests only increases bandwidth contention, RAM pressure, and timeouts. Approximate theoretical transfer throughput limited by link bandwidth:

\[
T_{\max} \approx \frac{B_{\text{effective}}}{8}
\]

If `B_effective = 80 Mbps`, the theoretical ceiling is roughly `10 MB/s` before TCP/TLS, client, and disk overhead. Uploading 10 GiB cannot finish in a few seconds even with 100 parallel parts.

Common bottlenecks include:

- CPU consumed by checksums, encryption, or compression.
- RAM consumed by part buffers and transfer queues.
- Network throughput/latency, proxies, or Internet egress links.
- Source disk IOPS limits, especially on EC2/EBS volumes.
- KMS request rates, S3 API request patterns, proxy connection limits, and retry overhead.
- Rising request costs from unnecessarily small parts.

### 9.3. Choosing Part Size for Your Network

- Parts too **small**: excessive `UploadPart` calls, higher request overhead, risk of hitting the 10,000-part limit.
- Parts too **large**: failed retries re-send more bytes, high RAM use if buffering multiple parts, higher timeout risk on weak links.
- Concurrency too **low**: fails to saturate available uplink bandwidth.
- Concurrency too **high**: overloads CPU/RAM/network, triggering `503 SlowDown` or timeouts.

Start with defaults, measure speed and error rates, and change **one variable at a time**. For example, on a 100 GiB file, test 64 MiB then 128 MiB part sizes with 8 vs. 16 concurrent requests and record empirical results. Avoid assuming a single "universal optimal part size" across all systems.

## 10. AWS SDK for Java 2.x and S3 Transfer Manager

In Java/Spring Boot applications, avoid implementing low-level multipart logic yourself if your goal is simply transferring files. AWS SDK for Java 2.x provides **`S3TransferManager`**, which pairs with the multipart-enabled S3 async client to handle part splitting, concurrency, retries, completion, and progress tracking automatically.

### 10.1. Add Dependencies

Align AWS SDK for Java 2.x versions using the AWS SDK BOM. Include the relevant modules:

~~~xml
<!-- Example dependencies inside an application's pom.xml -->
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3-transfer-manager</artifactId>
</dependency>
~~~

Manage versions via `dependencyManagement` (e.g., AWS SDK BOM) rather than mixing mismatched artifact versions. If using the **CRT-based S3 client**, include its dependencies/runtime per official AWS guidance; the snippet below illustrates the Java-based async client.

### 10.2. High-Level File Upload Example

~~~java
import java.nio.file.Path;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3AsyncClient;
import software.amazon.awssdk.transfer.s3.S3TransferManager;
import software.amazon.awssdk.transfer.s3.model.UploadFileRequest;

public class UploadLargeObject {
    public static void main(String[] args) {
        try (S3AsyncClient s3 = S3AsyncClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .multipartEnabled(true)
                .build();
             S3TransferManager tm = S3TransferManager.builder()
                .s3Client(s3)
                .build()) {

            UploadFileRequest req = UploadFileRequest.builder()
                    .putObjectRequest(p -> p
                            .bucket("amzn-s3-demo-bucket")
                            .key("uploads/archive.bin"))
                    .source(Path.of("archive.bin"))
                    .build();

            var upload = tm.uploadFile(req);
            var done = upload.completionFuture().join();
            System.out.println("Upload completed: " +
                    done.response().eTag());
        }
    }
}
~~~

**This code performs a real upload if executed with a valid bucket and credentials.** In server applications, reuse managed `S3AsyncClient` and `S3TransferManager` instances rather than instantiating new clients on every HTTP request.

AWS SDK v2 uses the default credentials provider chain (IAM Identity Center profile locally, IAM role on EC2, ECS task role, IRSA/Pod Identity on EKS, Lambda execution role, etc.). Never hardcode access keys or secret keys in source code.

### 10.3. Additional Design Considerations for Java Services

1. **Idempotency:** use keys containing a unique upload/job ID or conditional writes so client retries do not unintentionally overwrite objects.
2. **Progress and cancellation:** track job status, progress, and failures; when canceling, ensure abandoned multipart uploads are aborted cleanly.
3. **Memory pressure:** cap concurrent large uploads; uploading 20 large files simultaneously can blow RAM budgets even when each file is chunked.
4. **Timeouts and retries:** let the SDK manage standard retries; any custom retry logic must use exponential backoff + jitter to avoid thundering herds.
5. **Checksums/metadata:** choose required algorithms and content types; validate checksum and object size upon completion.
6. **Transactional workflow:** mark the database record `READY` only after confirming S3 object completion. If the DB commit fails after S3 completes, implement orphan cleanup or reconciliation.
7. **Security:** scope role permissions strictly to `s3:PutObject` on the assigned prefix plus KMS permissions if needed; never make buckets public.

When Spring Boot handles web uploads, avoid buffering entire files in JVM heap; stream or use size-bounded temp files, enforce MIME/antivirus policies, and offload large transfers to async jobs. For Internet clients, issue short-lived **presigned URLs** so browsers/mobile apps upload parts directly to S3, keeping API servers off the heavy data path. The server must validate user permissions, file sizes, content types, keys/prefixes, and cleanup.

## 11. When You Need the Low-Level Multipart API

Usually, high-level SDKs and CLIs are the best choice. Still, knowing the raw API helps when inspecting logs, implementing custom part-level retries, or integrating custom clients.

### 11.1. Manually Initiate Multipart Upload

~~~bash
# ILLUSTRATION WITH REAL SIDE EFFECTS - requires authorized permissions and bucket.
aws s3api create-multipart-upload \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --checksum-algorithm SHA256 \
  --checksum-type COMPOSITE \
  --profile dev \
  --region ap-southeast-1
~~~

The response returns an `UploadId`. Set metadata and encryption parameters here. Never expose an `UploadId` publicly if doing so could allow an authorized principal to tamper with an active upload.

### 11.2. Upload Parts

~~~bash
# Replace UPLOAD_ID and files with real values in a lab environment.
aws s3api upload-part \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --part-number 1 \
  --body part-001.bin \
  --checksum-algorithm SHA256 \
  --profile dev \
  --region ap-southeast-1
~~~

Repeat for `part-number 2, 3, ...`, recording the returned **ETag** and **`ChecksumSHA256`** for each part. In this example using `COMPOSITE` with `SHA256`, part numbers at completion must be **contiguous starting from 1**.

### 11.3. Complete and Abort

With the AWS CLI, `complete-multipart-upload` expects JSON listing parts in order. **Illustrative `complete-parts.json`** (placeholder ETag/checksum values; do not use verbatim):

~~~json
{
  "Parts": [
    {
      "PartNumber": 1,
      "ETag": "\"EXAMPLE_ETAG_1\"",
      "ChecksumSHA256": "EXAMPLE_BASE64_PART_CHECKSUM_1"
    },
    {
      "PartNumber": 2,
      "ETag": "\"EXAMPLE_ETAG_2\"",
      "ChecksumSHA256": "EXAMPLE_BASE64_PART_CHECKSUM_2"
    }
  ]
}
~~~

After filling in **real** values from every part and verifying completeness:

~~~bash
# Real impact: finalizes the object if all data/metadata is valid.
aws s3api complete-multipart-upload \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --multipart-upload file://complete-parts.json \
  --checksum-type COMPOSITE \
  --profile dev \
  --region ap-southeast-1

# Or, if canceling instead of completing:
aws s3api abort-multipart-upload \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --profile dev \
  --region ap-southeast-1
~~~

**Never** both complete and abort the same `UploadId`. Prefer SDK/high-level transfer managers whenever possible; manual steps easily leave orphaned uploads incurring charges if cleanup is forgotten. Note differences in **JSON quoting** between Bash and PowerShell when passing inline `--multipart-upload`; `file://...` is usually cleaner.

## 12. Read-Only Commands to Inspect Multipart Uploads and Checksums

No new upload is required to practice these commands, provided your account has an existing bucket/object and read permissions.

### 12.1. List Incomplete Uploads

~~~bash
aws s3api list-multipart-uploads \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Uploads[].{Key:Key,UploadId:UploadId,Initiated:Initiated,StorageClass:StorageClass}' \
  --output table
~~~

This list will be empty if no incomplete uploads exist. It requires `s3:ListBucketMultipartUploads` on the bucket. Results are paginated; when auditing thoroughly, do not use `--no-paginate` or cap `--max-items` without following pagination tokens.

### 12.2. List Parts of an Upload

~~~bash
aws s3api list-parts \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --upload-id UPLOAD_ID \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Parts[].{PartNumber:PartNumber,Bytes:Size,ETag:ETag}' \
  --output table
~~~

Requires `s3:ListMultipartUploadParts`. S3 paginates past 1,000 parts, so handle pagination properly. `ListParts` inspects in-progress uploads; once completed, use `GetObjectAttributes` to view part metadata where supported.

### 12.3. Inspect a Completed Object

~~~bash
aws s3api head-object \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --checksum-mode ENABLED \
  --profile dev \
  --region ap-southeast-1

aws s3api get-object-attributes \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --object-attributes ETag ObjectSize Checksum ObjectParts \
  --profile dev \
  --region ap-southeast-1
~~~

If `NoSuchKey` is returned, distinguish between an uncompleted upload, wrong key, wrong bucket/account, or access errors masked as 404. If the object uses SSE-KMS, requesting checksums may require KMS permissions; never disable encryption to "make checksums easier."

## 13. Controlling Costs of Incomplete Multipart Uploads

### 13.1. Why Do Incomplete Uploads Cost Money?

From the moment the first part is uploaded, S3 stores real data. If a client crashes after uploading 95% of a 100 GiB file and **never completes or aborts**, the uploaded parts remain stored under that `UploadId` and **incur storage, request, and transfer charges**. Seeing nothing in normal bucket object listings does not mean zero billable data remains.

### 13.2. Lifecycle Rule `AbortIncompleteMultipartUpload`

You can configure **S3 Lifecycle** on a bucket to automatically abort incomplete multipart uploads N days after initiation. Illustrative JSON rule:

~~~json
{
  "Rules": [
    {
      "ID": "AbortIncompleteMultipartUploadsAfter7Days",
      "Status": "Enabled",
      "Filter": {
        "Prefix": ""
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    }
  ]
}
~~~

This is **a single sample rule**, not a complete bucket lifecycle policy. **Never run `put-bucket-lifecycle-configuration` to overwrite a live policy** without reading and merging existing rules first; the API replaces the entire lifecycle config. Let IaC or the bucket owner manage it.

Inspect existing rules with a read-only command:

~~~bash
aws s3api get-bucket-lifecycle-configuration \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1
~~~

Pick the timeout window based on your slowest legitimate upload duration. If valid uploads take more than 7 days while a rule aborts at 7 days, active uploads will be canceled mid-flight. Conversely, setting it too long keeps failed-upload storage charges accumulating.

### 13.3. Layered Cost Breakdown

| Component | Potential Charges |
|---|---|
| `CreateMultipartUpload` / `UploadPart` / `CompleteMultipartUpload` | API requests per storage class/Region |
| Incomplete parts | Temporary storage until completed or aborted, billed per storage class |
| Completed object | Storage capacity, class tiers, and minimum storage duration (where applicable) |
| Data transfer | Egress out of S3, cross-Region, cross-AZ, or network path charges |
| S3 Transfer Acceleration | Surcharge when using accelerated endpoints for eligible traffic |
| KMS | AWS KMS API requests and key fees if applicable |
| CloudWatch / logging | Metrics, logs, auditing, tracing, and monitoring services |

**Aborting incomplete uploads** via Lifecycle does not trigger early-deletion charges for incomplete parts; however, storage and request fees already incurred prior to abort still apply. For Glacier storage classes, in-progress upload parts have specific staging billing rules.

## 14. Network Performance: Same-Region Locality, Parallelism, and Byte-Range Reads

### 14.1. Place Clients Close to the Bucket When Possible

For applications on EC2/ECS/EKS:

- Keeping services and buckets in the same Region improves latency and avoids cross-Region data transfer fees.
- In VPC private subnets, consider an **S3 Gateway VPC Endpoint** to route S3 traffic over AWS's private backbone instead of traversing a NAT Gateway, where routes, policies, and Regions permit.
- Configure endpoint policies, bucket policies, IAM roles, and KMS key policies consistently; a VPC endpoint does not grant bucket permissions by itself.
- Routing heavy S3 traffic through a NAT Gateway can add substantial per-GB data processing charges; benchmark authorized paths before optimizing.

### 14.2. Parallel Uploads and Parallel Downloads

Multipart uploads send parts in parallel to boost aggregate throughput. On the download side, use **`GetObject` with the `Range: bytes=start-end` header** or parallel range fetches via tools that support it. `S3TransferManager` supports parallel byte-range downloads.

Example reading the first 1 MiB of an object (saved to file rather than printing binary to terminal):

~~~bash
aws s3api get-object \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --range bytes=0-1048575 \
  --profile dev \
  --region ap-southeast-1 \
  first-megabyte.bin
~~~

This retrieves real object bytes, requiring read permissions and incurring GET/transfer fees. Do not expect `head-object` to return payload bytes.

### 14.3. Prioritize Measurement

A benchmark run should capture:

- **Throughput:** successful bytes / elapsed time.
- **P50/P95/P99 part upload latency**, retry rate, and HTTP 503 count.
- **Network utilization** on EC2/host and proxies.
- **CPU/RAM**, disk read throughput, and EBS throttling.
- **Request counts**, KMS API counts, transfer costs, and uncleaned part count.

For a 100 GiB upload, if 8 concurrent workers reach 450 MB/s while 32 workers only reach 460 MB/s with 4x more retries, 8 workers is far better for cost and stability.

## 15. S3 Transfer Acceleration and When to Use It

**Amazon S3 Transfer Acceleration** routes **long-distance** uploads/downloads from Internet clients to S3 general purpose buckets over AWS/CloudFront edge locations. Once enabled on a compatible bucket, clients use endpoints like:

~~~text
bucket-name.s3-accelerate.amazonaws.com
~~~

For dual-stack IPv4/IPv6:

~~~text
bucket-name.s3-accelerate.dualstack.amazonaws.com
~~~

Prerequisites:

1. Bucket resides in a Region supporting Transfer Acceleration.
2. Bucket owner or authorized principal enabled the feature.
3. Bucket name is DNS-compliant and **contains no periods**.
4. Clients/tools target the accelerated endpoint properly.
5. Business accepts the surcharge for accelerated transfers.

S3 Transfer Acceleration is **not always faster** than standard endpoints, especially when clients are already in the same Region or over well-peered paths. AWS offers a **Speed Comparison tool** to test from your actual user locations. Enabling the feature can take time to propagate; never judge from a single immediate test.

CLI configuration:

~~~bash
# Updates local profile config; the bucket must have acceleration enabled first.
aws configure set s3.use_accelerate_endpoint true --profile dev
~~~

Use `Transfer Acceleration` for globally distributed clients uploading large files into a centralized bucket. For EC2 instances in the same Region, **direct S3 access over an appropriate endpoint** is usually the better starting point.

## 16. Security: IAM, KMS, and Overwrite Protection

### 16.1. Required Permissions by Operation

| Operation | Typical IAM Action |
|---|---|
| Upload objects / multipart upload | `s3:PutObject` on the granted prefix object ARN |
| List active multipart uploads in bucket | `s3:ListBucketMultipartUploads` on the bucket ARN |
| List parts of an active upload | `s3:ListMultipartUploadParts` |
| Abort a multipart upload | `s3:AbortMultipartUpload` |
| Read or download object | `s3:GetObject` (and `s3:GetObjectVersion` for specific versions) |
| Inspect checksum/object part attributes | `s3:GetObjectAttributes` or equivalent API permission |
| Manage bucket lifecycle | `s3:GetLifecycleConfiguration` / `s3:PutLifecycleConfiguration` |

Permissions must be scoped strictly by **bucket/prefix** and align with bucket policies, SCPs, permissions boundaries, and guardrails. For SSE-KMS multipart uploads, **AWS KMS** permissions such as `kms:GenerateDataKey` and `kms:Decrypt` are required across stages. If `UploadPart` succeeds yet `CompleteMultipartUpload` or reading checksums fails with `AccessDenied`, inspect **both S3 IAM policies and KMS key policies/permissions**.

### 16.2. Encryption and Integrity Are Distinct Layers

- **TLS (HTTPS):** protects data in transit against eavesdropping and tampering.
- **SSE-S3 or SSE-KMS:** encrypts data at rest in S3.
- **Checksums:** verify byte integrity, not caller identity.
- **IAM/bucket policies:** control who can upload, read, or overwrite.
- **S3 Object Lock / versioning:** mitigate accidental/malicious overwrites or deletions per policy, though governed independently.

Never enable public read/write on a bucket just to simplify uploads. Frontends can use tightly scoped, short-lived **presigned URLs** to upload parts directly while a backend API orchestrates `UploadId`, part numbers, checksums, and completion. The backend must enforce user authorization, file sizes, content types, keys/prefixes, and cleanup.

### 16.3. Preventing Same-Key Overwrites

If multiple clients concurrently upload to `exports/report.zip`, whichever `CompleteMultipartUpload` finishes last can overwrite the existing object depending on versioning/conditional writes. Strategies:

- Use unique keys, such as `uploads/{job-id}/report.zip` (illustrative naming convention).
- Pass `If-None-Match: *` on `CompleteMultipartUpload` where supported by the API to create the object only if the key does not yet exist.
- Enable versioning when historical versions must be retained, paired with proper permissions and lifecycle cleanup.
- Store `VersionId`, ETag, or checksum references in a database to enforce idempotency.

Avoid claiming only one `UploadId` can exist per key; S3 allows multiple concurrent uploads targeting the same key.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `EntityTooSmall` on complete | A non-final part is smaller than 5 MiB | Check part boundaries/sizes and re-upload valid parts |
| `InvalidPart` | Wrong ETag, missing part, or mismatched `UploadId`/key | Run `ListParts`; verify exact `UploadId` and real ETags |
| `InvalidPartOrder` | Completion part list is not in ascending order | Sort by `PartNumber` before completing |
| HTTP 500 on composite complete | Part numbers not contiguous/starting at 1, or transient error | Check part numbering, checksum docs, and retry logic |
| `BadDigest` | Checksum mismatch against bytes received by S3 | Recompute checksum, verify `FULL_OBJECT`/`COMPOSITE` mode and Base64 encoding |
| `AccessDenied` on upload/complete | Insufficient IAM, bucket, or KMS policy | Check actions for every stage, bucket/prefix, and KMS permissions |
| `NoSuchUpload` | `UploadId` already completed/aborted, expired, or wrong key | Check upload state and ID rather than retrying blindly |
| `NoSuchKey` when reading after part uploads | `CompleteMultipartUpload` was not successfully called | Verify completion result via `HeadObject` / `GetObjectAttributes` |
| `503 SlowDown` | Sudden request rate spike, excessive client requests, or S3 scaling | Exponential backoff + jitter, lower concurrency, re-benchmark |
| Frequent timeouts / `Connection reset` | Unstable network/proxy or oversized parts | Retry failed parts, consider smaller part size/concurrency, tune timeouts |
| Uploaded ETag differs from local MD5 | Multipart upload, SSE, or copy operation | Use an explicit checksum with matching algorithm and type |
| S3 `ChecksumSHA256` differs from `sha256sum` | S3 stores `COMPOSITE`, while local digest is whole-file | Compare matching checksum types or use full-object/independent manifest digests |
| Storage costs rising despite few visible objects | Accumulated incomplete multipart uploads | Run `ListMultipartUploads`, abort stale uploads, add lifecycle cleanup |
| Slow downloads despite healthy S3 | Client disk/CPU/network bottleneck or single-stream download | Benchmark parallel range GETs, match Region, inspect NIC/EBS |
| Transfer Acceleration is no faster | Client already near bucket or overhead outweighs gain | Benchmark standard vs. accelerated endpoints and compare costs |
| SSE-KMS checksum/complete failure | Missing KMS permissions or key policy issue | Verify `kms:GenerateDataKey`/`kms:Decrypt` and key policy |

### 17.1. Ordered Troubleshooting Workflow

1. Confirm **AWS account, IAM principal, and Region/bucket** via CLI/Console.
2. Determine whether a **completed object exists** or only an in-progress multipart upload.
3. Inspect `UploadId`, part list, ETags, checksum algorithm/type, part count, and part sizes.
4. Read error details from response bodies and AWS request IDs / extended request IDs; never print tokens or credentials.
5. Check S3/KMS permissions; grant only the exact missing permissions, never temporary wildcard admin access.
6. Use SDK retries with backoff; for logic/data errors, fix payload/checksums instead of retrying endlessly.
7. When canceling tasks, abort cleanly and verify cleanup; monitor incomplete-part storage usage.
8. Instrument metrics for throughput, errors, retries, incomplete upload volume, and cost.

## 18. Practice Lab: Designing a Large-File Upload Strategy

### 18.1. Context

A Java/Spring Boot service on ECS receives camera files from users across multiple countries and stores them in an S3 bucket in Singapore. Each file is 30 GiB; client connections drop occasionally. The system must:

- Avoid re-uploading entire files after a single part failure.
- Ensure bytes stored in S3 match the bytes sent by the client.
- Prevent unfinished parts from accumulating and inflating storage bills.
- Avoid long-lived IAM access keys inside containers.
- Provide observability into upload success/failure, retries, and completion duration.

### 18.2. Recommended Design

1. Backend authenticates users, assigns unique object keys, and enforces size/quota limits.
2. Use multipart upload; e.g., **64 MiB** parts for a 30 GiB file yields **480 parts**, well within limits.
3. Choose **CRC64NVME `FULL_OBJECT`** checksums for S3 transfer integrity; if an independent SHA256 digest is needed to prove original content, maintain a separate SHA256 manifest with a matching verification step.
4. Issue short-lived presigned `UploadPart` URLs or upload through a service using `S3TransferManager`, avoiding unnecessary proxying through backend servers when direct upload is viable.
5. Allow part-level retries, cap concurrent workers based on benchmarks, and persist `UploadId`, parts, and ETags as needed.
6. Call complete after verifying all parts; mark the DB object `READY` only after completion and metadata verification succeed.
7. Clean up via job state and a Lifecycle `AbortIncompleteMultipartUpload` rule (e.g., 7 days if aligned with SLAs).
8. Use an ECS task role with least-privilege IAM, KMS permissions, and TLS; monitor CloudWatch, CloudTrail, and S3 metrics.
9. Benchmark standard vs. Transfer Acceleration endpoints for distant clients; choose based on throughput, retry rates, and cost.

### 18.3. Calculation Exercises

**Exercise A — Part Size:** For a 1.5 TiB file using 32 MiB/part, how many parts are created? Is that valid? Pick a valid part size that stays under 10,000 parts.

Hint:

\[
1.5\ \text{TiB} = 1{,}572{,}864\ \text{MiB}
\]

- `1,572,864 / 32 = 49,152` parts — invalid.
- Choosing `256 MiB/part` yields `6,144` parts — valid.

**Exercise B — Checksum Verification:** A multipart object has `ChecksumSHA256` with `ChecksumType = COMPOSITE`; the client runs whole-file `sha256sum` and gets a mismatch. Can you conclude the data is corrupted? Explain `ChecksumType` and how to verify the whole file.

**Exercise C — Cost:** A system has 100 failed 10 GiB upload sessions abandoned around 80%. Roughly **800 GiB** of incomplete part data may be stored and billed until cleaned up. Name two ways to prevent this accumulation.

**Exercise D — Performance:** With an effective link speed of 160 Mbps, theoretical throughput is roughly **20 MB/s**. Uploading 10 GiB over this link takes at least roughly **9 minutes** due to bandwidth limits before protocol overhead. Can raising concurrency from 8 to 64 workers drop upload time below 1 minute? Why or why not?

### 18.4. Read-Only Lab Commands

If you have read access to an existing bucket, run:

~~~bash
# 1. Verify account and principal
aws sts get-caller-identity --profile dev

# 2. Check incomplete multipart uploads
aws s3api list-multipart-uploads \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1 \
  --output json

# 3. Inspect existing bucket lifecycle rules
aws s3api get-bucket-lifecycle-configuration \
  --bucket amzn-s3-demo-bucket \
  --profile dev \
  --region ap-southeast-1

# 4. Inspect metadata/checksums on a completed object
aws s3api get-object-attributes \
  --bucket amzn-s3-demo-bucket \
  --key uploads/archive.bin \
  --object-attributes ObjectSize ETag Checksum \
  --profile dev \
  --region ap-southeast-1
~~~

If you do not have a lab bucket or permissions, analyze the sample outputs above; **you do not need to provision real AWS resources**. Even read-only commands may incur tiny request charges depending on account and operation type.

## 19. Self-Check Questions

1. How does multipart upload differ from creating multiple separate S3 objects?
2. What are the required steps from initiating an upload until the object is readable via `GetObject`?
3. What are `UploadId` and `PartNumber` used for? What happens if you re-upload the same part number?
4. Why is `CompleteMultipartUpload` required, and why isn't HTTP 200 on `UploadPart` enough?
5. Why are `AbortMultipartUpload` and lifecycle cleanup important?
6. Is 5 MiB a hard minimum for every single part, or is there an exception?
7. Why is a 2 TiB file with 64 MiB parts invalid?
8. When can an `ETag` differ from a file's whole-object MD5?
9. How do `FULL_OBJECT` and `COMPOSITE` checksums differ?
10. Which algorithms support full-object checksums for S3 multipart uploads?
11. Why shouldn't you compare a `COMPOSITE` `ChecksumSHA256` against whole-file `sha256sum`?
12. Which configuration parameters affect throughput in AWS CLI `s3 cp`?
13. When increasing concurrency causes frequent `SlowDown` errors, what should you do?
14. When is S3 Transfer Acceleration a better fit than standard Regional endpoints?
15. Why can SSE-KMS cause `CompleteMultipartUpload` to fail even after `UploadPart` calls succeeded?
16. Which IAM permissions are needed to list and abort multipart uploads?
17. When EC2/ECS and S3 are in the same Region, how can the network path be optimized?
18. Why is `S3TransferManager` generally preferable to implementing low-level multipart calls manually in Spring Boot?

### Answer Guidelines

- **Multipart** uses an `UploadId` and parts, becoming a single object only upon completion.
- **Core limits:** max 10,000 parts, each non-final part from 5 MiB to 5 GiB; max object size ~48.8 TiB.
- **Checksums:** match algorithm and `ChecksumType`; `ETag` is not whole-object MD5 proof for multipart uploads.
- **Optimization:** tune part size, concurrency, retry/backoff, Region placement, network path, and transfer manager using empirical benchmarks.
- **Operations:** configure proper IAM/KMS permissions, clean up incomplete parts, guard against overwrites, and track both S3 and data transfer costs.

## 20. Official AWS Documentation

1. [Uploading and copying objects using multipart upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html) — Create/upload/complete/abort lifecycle, retries, and incomplete-part charges.
2. [Amazon S3 multipart upload limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html) — Object/part sizes and the 10,000-part limit.
3. [Checking object integrity for data uploads](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html) — Checksum algorithms, full-object/composite modes, and ETag behavior.
4. [Checking object integrity in Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity.html) — Retrieving and verifying checksums.
5. [AWS CLI S3 configuration](https://docs.aws.amazon.com/cli/latest/topic/s3-config.html) — Multipart threshold, part size, concurrency, and bandwidth settings.
6. [AWS CLI `s3 cp`](https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html) — Uploads/downloads and checksum options.
7. [AWS CLI `get-object-attributes`](https://docs.aws.amazon.com/cli/latest/reference/s3api/get-object-attributes.html) — Object size, ETag, checksum, and part metadata.
8. [S3 Transfer Manager for AWS SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/transfer-manager.html) — Parallel uploads and downloads.
9. [Performance guidelines for Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-guidelines.html) — Benchmarking, parallelism, and range GETs.
10. [Performance design patterns](https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance-design-patterns.html) — Throughput, caching, retries, and request patterns.
11. [S3 Transfer Acceleration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/transfer-acceleration.html) — Endpoints, prerequisites, and pricing.
12. [Abort incomplete multipart uploads using a lifecycle rule](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-abort-incomplete-mpu-lifecycle-config.html) — Automated cleanup of unfinished parts.
13. [CompleteMultipartUpload API](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CompleteMultipartUpload.html) — Part list, error handling, and checksums.
14. [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/) — Storage, requests, transfer, and related charges.

> **Key Takeaway:** **Uploading parts successfully does not mean the object is ready.** A solid design manages `UploadId`, retries per part, validates checksums **using the right algorithm and type**, completes and verifies the object, and cleans up abandoned uploads. Optimal speed comes from **empirically measured** part size, concurrency, network locality, and retries—paired with proper IAM/KMS permissions, monitoring, and cost governance.
