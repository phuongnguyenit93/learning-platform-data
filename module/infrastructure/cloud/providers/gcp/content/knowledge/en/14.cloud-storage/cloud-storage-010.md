# Resumable Uploads, Compose, and Large File Handling

An online learning platform may need to receive multi-GiB videos, training datasets, backups, or continuously generated analytics files. Sending an entire file in a single HTTP request means a connection drop near the end can force the user to re-upload from scratch. For flows split into multiple chunks, the application also needs to assemble them **in the exact order**, prevent accidental overwrites, and prove the final content is intact.

In the **CLOUD_PROVIDERS_GCP** module, **Cloud Storage** provides mechanisms for this problem: **resumable uploads** to resume transfers after interruptions, **compose** to concatenate objects already in a bucket, and **parallel composite uploads** to accelerate uploads in suitable scenarios.

This lesson belongs to the **Cloud Storage** chapter in the Google Cloud learning path spanning projects, IAM, and VPCs through Compute Engine, GKE, Cloud Run, storage, deployment, security, and monitoring reliability and cost. The focus is not just the upload command: learners must understand data correctness, permissions, product limits, network paths, and temporary object lifecycles.

**After this lesson, you will be able to:**

1. Distinguish resumable upload, compose, parallel composite upload, and XML API multipart upload.
2. Describe a resumable session's lifecycle, how to query persisted byte offsets, and how to resume without writing at wrong offsets.
3. Combine objects with compose in exact order and understand the 32-source-per-request limit.
4. Use generation preconditions, CRC32C, and application-level checks to prevent overwrites, race conditions, and data corruption.
5. Design large-file upload flows through a backend or directly from clients with secure IAM, session URIs, and access controls.
6. Estimate the cost impact of network traffic, API operations, temporary objects, retention, soft delete, and Object Versioning.
7. Practice uploading, composing, verifying outputs, and cleaning up resources in a lab bucket.

## 1. Large Files in Cloud Storage Are Objects, Not Disk Blocks

Cloud Storage stores data as **objects** inside a **bucket**. Each object has a name, content, metadata, generation, and management attributes. Unlike Hyperdisk, an object is not mounted as a block device for arbitrary in-place sector edits; changing content generally produces a new object version via the corresponding write, compose, or rewrite operation.

| Concept | Meaning in This Lesson |
| --- | --- |
| **Bucket** | Container for objects with location, default storage class, IAM, lifecycle, and data protection policies. |
| **Object name** | Logical path, e.g., `videos/course-42/lesson-01.mp4`; folder-like prefixes are not automatically OS directories. |
| **Generation** | Identifier of an object **content** version; used as a precondition against overwrites and race conditions. |
| **Metageneration** | Version of object metadata changes, distinct from data generation. |
| **CRC32C** | Checksum used to detect data corruption during transit or storage. |
| **Resumable session URI** | URL of an open upload session, acting as a bearer secret. |
| **Composite object** | A new object created by concatenating the bytes of source objects in the same bucket in exact order. |

**Size limit:** Cloud Storage limits a single object to **5 TiB**, whether created via simple upload, resumable upload, compose, or XML multipart upload. To store larger datasets, design multiple objects with a manifest/index instead of trying to exceed the per-object limit.

### 1.1. Three Different Scenarios

**Scenario A — Unstable network:** a user uploads a 6 GiB video from a laptop and needs to resume from the bytes already persisted by Cloud Storage after a disconnect. Choose **resumable upload**.

**Scenario B — Data already split across objects:** the system received `part-0001`, `part-0002`, and `part-0003` in a bucket and needs one new object containing those parts in sequence. Choose **compose**.

**Scenario C — Saturating multiple network streams:** a machine has ample CPU, disk, and bandwidth. The tool splits the source file into segments, uploads them **in parallel to temporary objects**, and composes the final object. This is a **parallel composite upload**—not the same as a single resumable session.

### 1.2. Method Selection Table

| Method | Model | Recovery | Notes |
| --- | --- | --- | --- |
| **Simple/multipart request** (JSON API) | Sends the object in one request; JSON API multipart also attaches metadata. | If the request fails, you usually retry sending the whole payload. | Good for small objects; "JSON API multipart" is not multi-stream parallel upload. |
| **Resumable upload** | Creates a session, then sends bytes in one or more sequential requests. | Queries the server for saved offset and resumes. | Ideal for large uploads, unstable networks, and streaming sources. |
| **Compose** | Combines existing objects server-side. | Does not re-transfer source bytes through the client. | 1–32 sources per call, same bucket, order matters. |
| **Parallel composite upload** | Splits file, uploads temporary objects in parallel, composes final object. | Can retry individual part uploads per tool logic. | Creates/deletes temporary objects; needs compatible IAM, checksums, and bucket policies. |
| **XML API multipart upload** | Initiates an upload, sends parts via XML API, completes or aborts. | Can retry/resume at the part level per protocol. | Differs from JSON API multipart and from compose; consider where tooling supports it. |

No single method fits every file. Choose based on **size, network stability, integrity requirements, IAM, bucket features, pricing, and client capabilities**.

## 2. Resumable Upload: Lifecycle and States

With the JSON API, a resumable upload typically has two phases: **session initiation** and **content transfer**. The session remembers accepted bytes so the client can resume after disconnects.

~~~mermaid
sequenceDiagram
    participant C as Client / uploader
    participant S as Cloud Storage
    C->>S: POST create resumable session (authenticated)
    S-->>C: 200 OK + Location: SESSION_URI
    C->>S: PUT chunk 0..N (SESSION_URI)
    S-->>C: 308 Resume Incomplete + Range
    Note over C,S: Disconnect or timeout
    C->>S: PUT status query, Content-Range: bytes */TOTAL
    S-->>C: 308 + Range: bytes=0-K
    C->>S: PUT bytes K+1..end, exact Content-Range
    S-->>C: 200/201 + object metadata
    C->>S: GET metadata / verify checksum
    S-->>C: Generation, size, CRC32C
~~~

### 2.1. Session Initiation

An authenticated client calls the JSON API endpoint with `uploadType=resumable`. Cloud Storage returns a **`Location` header** containing the session URI. Subsequent PUT chunk requests can use this URI without re-signing each chunk under normal initiation flows.

**The session URI is a secret carrying upload authority.** Anyone holding a valid URI can continue uploading data to the session's target without extra credentials on chunk requests. Therefore:

- Use HTTPS exclusively; never downgrade the URI to HTTP.
- Never log the URI to application logs, public URLs, analytics, crash reports, or untrusted locations.
- If persisted to resume uploads across app restarts, encrypt and protect it like a bearer token with strict expiration and ownership checks.
- Never share session URIs across users or unrelated uploads.
- If a URI may have leaked, cancel the session when possible and create a new one.

**Expiration:** a session URI expires **one week** after initiation. For invalid or expired sessions, the API may return `410 Gone` or `404 Not Found` depending on timing/case. When that happens, initiate a fresh session and restart from byte 0 rather than reusing old offsets.

### 2.2. Sending Data in One Request or in Chunks

A resumable session can receive all bytes in **one PUT** or multiple sequential PUTs. When chunking, every chunk **except the final chunk** must be a multiple of **256 KiB**. Google Cloud documentation recommends considering chunks **starting around 8 MiB** to avoid excessive overhead; larger chunks require more memory or buffering.

Example for a **20,000,000-byte** file using an initial **8 MiB = 8,388,608-byte** chunk:

~~~http
PUT SESSION_URI HTTP/1.1
Content-Length: 8388608
Content-Range: bytes 0-8388607/20000000

<first 8,388,608 bytes of the file>
~~~

The response when the server has not yet received the entire object looks like:

~~~http
HTTP/1.1 308 Resume Incomplete
Range: bytes=0-8388607
~~~

**Distinguish the status:** Cloud Storage's `308 Resume Incomplete` indicates an **in-progress** upload, not an HTTP redirect to follow. Receiving `200 OK` or `201 Created` after the final PUT means the object finished per protocol and its metadata/checksum should be verified.

### 2.3. The Server Is the Source of Truth for Persisted Offsets

Suppose a client sent 8 MiB and lost connectivity before receiving a response. The client **must neither guess** the whole chunk persisted nor assume zero bytes arrived. Instead, send a **status query** to the exact session URI:

~~~http
PUT SESSION_URI HTTP/1.1
Content-Length: 0
Content-Range: bytes */20000000
~~~

If the server responds:

~~~http
HTTP/1.1 308 Resume Incomplete
Range: bytes=0-4194303
~~~

then the server confirms **4,194,304 bytes** are saved, with the last saved byte at index **4,194,303**. The next PUT must start at **byte 4,194,304**, not jump ahead to 8 MiB.

If `308` returns **without a `Range` header**, zero bytes have been persisted and the client sends from byte 0. If the server returns `200`/`201`, the upload already finished; do not send more PUTs. If the session is gone or expired, start a new session and re-upload from the source.

### 2.4. Never Alter Source Content Between Resumes

Once Cloud Storage persists a byte range in a session, it does not allow overwriting that range with new content. If the source file changes mid-upload, sending the remaining tail from the modified version produces a **corrupted object stitched from two incompatible versions**.

Safeguards:

1. Lock or snapshot the source file client-side for the entire upload lifecycle.
2. Store the source file's **size, mtime, and fingerprint/checksum** alongside the upload job; refuse to resume if the source changed.
3. Upon completion, compare the final object's checksum and size against the immutable source.
4. If source modification is suspected, abort the session and restart cleanly.

### 2.5. Small Chunks, Large Chunks, and Network Stability

| Decision | Benefit | Cost / Trade-Off |
| --- | --- | --- |
| Single large PUT in a resumable session | Minimal round trips and overhead. | Retries may need to check/resume larger intervals on drops. |
| 256 KiB chunks | Minimal memory buffer; fits constrained clients. | Many requests and offset checks; high overhead. |
| 8–64 MiB chunks | Usually balances throughput and memory for large files. | Needs larger buffers; actual speed depends on network/SDK. |
| Uploading multiple independent files in parallel | Better bandwidth and CPU utilization. | Requires managing concurrency, rate limits, quotas, and retries. |
| Parallel composite upload for one file | Can speed up when bandwidth and disk I/O allow. | Temporary objects, compose, CRC32C checksums, delete permissions, and cost. |

Choose chunk sizes based on **bandwidth, RTT, link stability, RAM, and retry budget**, not one magic number for every app. Libraries also have differing default buffer/chunk sizes; check your SDK's configuration.

## 3. Use `gcloud` CLI or Client Libraries Instead of Hand-Rolling HTTP

For standard workloads, **prefer the Google Cloud CLI or official client libraries**, as they handle resumable session mechanics, retries, streaming, and integrity verification. Writing raw REST clients is justified only when an environment cannot run an SDK, requires a specialized protocol, or needs per-request control.

### 3.1. Uploading a File with `gcloud`

Assuming your organization provided an authorized **lab bucket** and upload permissions, in Bash or Cloud Shell:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export BUCKET_NAME="YOUR_APPROVED_LAB_BUCKET"

# Read-only check of active project configuration
gcloud config get-value project

# Check local source file and size before uploading
ls -lh ./large-video.mp4

# Write operation to an authorized bucket
gcloud storage cp \
  ./large-video.mp4 \
  "gs://$BUCKET_NAME/uploads/large-video.mp4"

# Read back object metadata after upload
gcloud storage objects describe \
  "gs://$BUCKET_NAME/uploads/large-video.mp4" \
  --format="yaml(name,size,generation,crc32c,md5Hash,contentType)"
~~~

**Important note:** `gcloud storage cp` can automatically pick **resumable upload** or **parallel composite upload** depending on file size, CLI configuration, and bucket policies. Therefore, **never assume every `cp` invocation creates a single resumable session**. To test one specific mechanism deterministically, inspect and configure the exact tool flags in your lab environment against current documentation.

For critical data, apply **generation preconditions** or a non-overwriting publication pattern, especially when multiple jobs might target the same name. Seeing a new `generation` does not prove a job targeted the right business version.

### 3.2. Principles for Using Client Libraries

Use a client library as follows:

1. Read from an **immutable source stream or file** across the entire upload.
2. Set object name, content type, checksum/precondition, and appropriate timeouts.
3. Initiate the resumable session via the SDK and let it handle offsets/retries where supported.
4. Apply bounded exponential backoff for transient errors; never retry infinitely.
5. Verify metadata on completion: **bucket, name, size, generation, CRC32C**.
6. Mark the job successful in your app database/index **only after** verifying the object.

Example separation of responsibilities:

~~~mermaid
flowchart LR
    JOB["Upload job / manifest"] --> SDK["Cloud Storage SDK"]
    SDK --> GCS["Cloud Storage object"]
    GCS --> VERIFY["Verify size, generation,<br/>CRC32C, or content"]
    VERIFY --> PUB["Mark READY<br/>in database"]
    SDK -->|"Transient error"| RETRY["Retry with backoff,<br/>resume same session"]
    RETRY --> SDK
~~~

If an upload succeeds yet the database update fails, you get an "object exists, job not READY" state. Design **idempotent** handling that reads metadata back and checks generation rather than blindly re-uploading.

### 3.3. JSON API Protocol When Building a Custom Client

This is a **conceptual HTTP template**, containing no real access tokens or session URIs. When initiating a resumable upload, the caller needs valid credentials and can attach a precondition to prevent overwriting an existing object:

~~~http
POST /upload/storage/v1/b/YOUR_BUCKET/o?uploadType=resumable&name=videos%2Flesson.mp4&ifGenerationMatch=0 HTTP/1.1
Host: storage.googleapis.com
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json; charset=UTF-8
X-Upload-Content-Type: video/mp4
X-Upload-Content-Length: 20000000
Content-Length: 2

{}
~~~

A successful initiation response returns:

~~~http
HTTP/1.1 200 OK
Location: https://storage.googleapis.com/upload/storage/v1/b/YOUR_BUCKET/o?uploadType=resumable&upload_id=SECRET_SESSION_ID
~~~

`ifGenerationMatch=0` requires **creating only if no live object with that name exists at commit time**, preventing a retry or concurrent upload from clobbering an existing file. For conditional updates, pass the observed **specific generation** and handle `412 Precondition Failed`.

In practice, initiation headers, object name encoding, and body fields depend on the API/metadata used. Any custom client must follow the full JSON API spec for initiation, chunk upload, status queries, and session cancellation—never copy an illustrative snippet while skipping error handling.

### 3.4. Handling Status Codes

| Scenario | Common HTTP Response | Action |
| --- | --- | --- |
| Create resumable session | `200 OK` with `Location` | Store session URI securely and begin upload. |
| Chunk incomplete | `308 Resume Incomplete` | Read `Range`; send remaining bytes starting after the last saved byte. |
| Upload complete | `200 OK` or `201 Created` | Verify size, checksum, generation, and business state. |
| Invalid initiation token | `401 Unauthorized` or `403 Forbidden` | Check credentials, IAM, and bucket policies. |
| Generation precondition conflict | `412 Precondition Failed` | Re-read current object; resolve per business rules without blind overwrites. |
| Old session expired/aborted | `404 Not Found` or `410 Gone` depending on case | Initiate a new session from scratch; discard old offsets. |
| `429` or transient `5xx` | Rate limit or service/network error | Backoff with jitter; query session status before resending bytes. |
| Invalid `Content-Range` | `400 Bad Request` | Fix offset/range logic and confirm session validity. |

**Safe retries:** after a timeout or dropped response, distinguish "server received nothing," "server saved partial bytes," and "object already completed." With conditional writes, retrying with the **same generation precondition** prevents duplicate jobs from corrupting committed data.

## 4. Compose: Server-Side Object Concatenation in Exact Order

**Compose** creates a new object whose content is the **direct byte concatenation** of source objects. Cloud Storage performs the concatenation server-side, so the app never has to download all parts and re-upload the combined file.

Example:

~~~text
gs://course-bucket/parts/video/0001   -> "AAA"
gs://course-bucket/parts/video/0002   -> "BBB"
gs://course-bucket/parts/video/0003   -> "CCC"
                                      -----------------
gs://course-bucket/videos/final.bin   -> "AAABBBCCC"
~~~

Compose **is not** a video muxer, ZIP archiver, or schema-aware CSV merger. It strictly concatenates raw bytes. If every part carries its own file header, naive concatenation produces a corrupt file. Ensure your format supports raw byte concatenation, or split parts so concatenating them yields a valid file.

### 4.1. Conditions and Limits of a Compose Call

1. Each request accepts **1 to 32 source objects**; concatenation follows the **exact declared order**.
2. Source objects must reside in the **same bucket** and share the **same storage class**. The destination resides in that same bucket per Compose API rules.
3. A source can itself be a **composite object** from an earlier compose, allowing multi-level compose trees when part counts exceed 32.
4. The destination object remains subject to the **5 TiB** limit and all bucket constraints.
5. Source objects **are not automatically deleted** after compose by default; manage cleanup explicitly.
6. If the destination object name may already exist, use **generation preconditions** to prevent accidental overwrites.
7. Once composed, the destination's content is independent: deleting or overwriting sources does not alter the finished destination bytes.

### 4.2. Compose Example with `gcloud`

Assuming three objects already exist in a lab bucket and are safe to byte-concatenate:

~~~bash
export BUCKET_NAME="YOUR_APPROVED_LAB_BUCKET"

# Read-only: confirm parts, sizes, and generations
gcloud storage objects describe "gs://$BUCKET_NAME/parts/demo/0001"
gcloud storage objects describe "gs://$BUCKET_NAME/parts/demo/0002"
gcloud storage objects describe "gs://$BUCKET_NAME/parts/demo/0003"

# Write operation: concatenate the three objects in LISTED ORDER
gcloud storage objects compose \
  "gs://$BUCKET_NAME/parts/demo/0001" \
  "gs://$BUCKET_NAME/parts/demo/0002" \
  "gs://$BUCKET_NAME/parts/demo/0003" \
  "gs://$BUCKET_NAME/final/demo.bin"

# Read-only: verify final object
gcloud storage objects describe \
  "gs://$BUCKET_NAME/final/demo.bin" \
  --format="yaml(name,size,generation,componentCount,crc32c,md5Hash,contentType)"
~~~

This is a basic demonstration. **When multiple uploaders share part or destination names, never run precondition-free compose in production workflows.** Specify each part's exact generation and the destination's `ifGenerationMatch` via the API/client library or supported tool flags to guard consistency.

### 4.3. Composite Objects Lack MD5 Metadata

After compose, the result is a **composite object**. Key differences:

- Composite objects include a Cloud Storage **CRC32C** checksum, yet **have no MD5 metadata field**.
- Never assume a composite object's **ETag** equals a content MD5.
- `componentCount` tracks the constituent component count in metadata and grows across multi-level composes.
- Custom download tools must validate **CRC32C** or an application-managed end-to-end hash rather than expecting an MD5 field in Cloud Storage.

CRC32C detects **accidental transit/storage corruption**, not intentional tampering. If you need tamper resistance or provenance verification, use digital signatures or trusted hashes stored in an authenticated manifest alongside CRC32C.

### 4.4. Object Metadata After Compose

The destination object has its own metadata, including `Content-Type`, cache headers, custom metadata, generation, and storage class. With `gcloud storage objects compose`, the destination's `Content-Type` defaults to the first source object's type unless configured otherwise.

Consequently, if you compose three video parts whose first part has `application/octet-stream`, do not expect browsers to automatically recognize the output as `video/mp4`. Verify and set destination metadata using supported options. For objects served through Cloud CDN, content type and cache headers directly affect delivery.

Never place sensitive secrets, passwords, or upload session URIs in custom metadata. Consider who can read metadata via IAM, signed URLs, or public configurations.

## 5. Combining More Than 32 Parts and Preventing Race Conditions

### 5.1. Multi-Level Compose

The **32-source-per-request** limit does not cap a composite object at 32 raw parts. A compose call can consume composite objects produced by earlier composes. Suppose you have 75 objects `part-0000` through `part-0074`:

~~~mermaid
flowchart TB
    A["part-0000 ... part-0031<br/>32 parts"] --> T1["intermediate-A"]
    B["part-0032 ... part-0063<br/>32 parts"] --> T2["intermediate-B"]
    C["part-0064 ... part-0074<br/>11 parts"] --> T3["intermediate-C"]
    T1 --> F["final-object<br/>compose A,B,C"]
    T2 --> F
    T3 --> F
~~~

Execution flow:

1. Upload/verify all 75 parts in the same bucket and storage class, ensuring total size does not exceed 5 TiB.
2. Compose parts 0–31 into `intermediate-A`.
3. Compose parts 32–63 into `intermediate-B`.
4. Compose parts 64–74 into `intermediate-C`.
5. Compose the three intermediates in order A → B → C to publish the result.
6. **Only after verifying the final object**, clean up intermediate and temporary parts per data policy and delete permissions.

This example uses **4 compose calls** (three intermediate, one final). Account for operation charges, temporary storage, and lifecycle rules rather than summing only the final file size. Component count in a composite object can exceed 32, while **each individual compose call** stays at ≤ 32 sources and the final object stays ≤ 5 TiB.

### 5.2. Clear Part Naming for Ordering

An easily audited naming scheme:

~~~text
staging/uploads/UPLOAD_ID/manifest.json
staging/uploads/UPLOAD_ID/parts/000000
staging/uploads/UPLOAD_ID/parts/000001
staging/uploads/UPLOAD_ID/parts/000002
...
staging/uploads/UPLOAD_ID/intermediate/000000
published/videos/lesson-042.mp4
~~~

Notes:

- `UPLOAD_ID` must uniquely isolate each upload job; never let all clients share one flat staging prefix.
- Use **zero-padded** part numbers to avoid lexical ordering bugs like `part-1, part-10, part-2`.
- **Manifest** should record part index, source object name, **generation**, size, checksum, and expected total size.
- Never trust arbitrary object listing order; always compose in **manifest order**.
- Never accept client-supplied object paths into another tenant's namespace without backend ownership validation.

### 5.3. Generation Preconditions to Prevent Source Mutation

**Race condition:** between validating `part-0001` and running compose, another worker uploads different bytes to the same name. Composing "the latest live object" without generation checks silently mixes mismatched data.

**Solution:** record each part's generation after upload, pass **exact generations** to compose, and require the destination not to exist yet (or match an expected generation).

**Conceptual JSON API** example (use real metadata generations, never guess):

~~~http
POST /storage/v1/b/YOUR_BUCKET/o/final%2Fdemo.bin/compose?ifGenerationMatch=0 HTTP/1.1
Host: storage.googleapis.com
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json

{
  "sourceObjects": [
    {
      "name": "parts/demo/0001",
      "generation": "1700000000000001",
      "objectPreconditions": {"ifGenerationMatch": "1700000000000001"}
    },
    {
      "name": "parts/demo/0002",
      "generation": "1700000000000002",
      "objectPreconditions": {"ifGenerationMatch": "1700000000000002"}
    }
  ],
  "destination": {"contentType": "application/octet-stream"}
}
~~~

This illustrates request structure—**it contains no real generations or tokens** and should never be run directly against critical data. For each source, generation/preconditions guard against reading a changed version; for the destination, `ifGenerationMatch=0` rejects writes if a live destination already exists.

If you receive **`412 Precondition Failed`**, never drop conditions and blindly retry. Verify:

- Did another uploader already publish successfully under that name?
- Was a source object replaced or deleted?
- Is this a duplicate retry for the same upload ID or a different request?
- Should you report "already completed" after verifying the existing object's manifest/checksum, or publish to a new destination name?

**Idempotent publishing:** if a timeout occurs after the server finishes compose but before the client sees the response, retrying with `ifGenerationMatch=0` returns `412`. That may indicate **the desired result already exists**, not an error requiring overwrite. Read destination metadata and reconcile generation, size, manifest, and checksum before deciding.

### 5.4. Upload Job States and Part Deletion Conditions

A resilient workflow might track states like:

~~~mermaid
flowchart LR
    NEW["NEW"] --> UP["UPLOADING"]
    UP --> READY["PARTS_VERIFIED"]
    READY --> CP["COMPOSING"]
    CP --> DONE["PUBLISHED"]
    UP --> FAIL["FAILED / ABORTED"]
    CP --> REVIEW["RETRY / CHECK DESTINATION"]
    REVIEW --> CP
    DONE --> CLEAN["CLEANED"]
~~~

Never delete source objects merely because **the compose call was sent**. Delete only after API/metadata verification and **when data policy permits**, or use intentional deletion workflows after validation. Ensure cleanup workers cannot delete temporary parts while another compose worker is still reading them.

## 6. Parallel Composite Uploads: Uploading Chunks Concurrently

**Parallel composite upload (PCU)** combines both mechanisms:

1. Split the source file into up to **32** segments for a final compose per tool logic.
2. Upload multiple segments **in parallel** as temporary objects.
3. Run `compose` to build the final composite object.
4. Clean up temporary objects per policy after verifying completion.

~~~mermaid
flowchart LR
    FILE["One large file on client"] --> SPLIT["Split segments"]
    SPLIT --> C1["Chunk 1 → tmp object 1"]
    SPLIT --> C2["Chunk 2 → tmp object 2"]
    SPLIT --> C3["Chunk N → tmp object N"]
    C1 --> CP["Cloud Storage compose"]
    C2 --> CP
    C3 --> CP
    CP --> FINAL["Final composite object"]
    CP -. "After verification, clean up temp parts" .-> TMP["Temporary objects"]
~~~

When WAN bandwidth and local disk read speeds are high, parallel streams can cut total upload time compared to a single stream. On a weak laptop link, slow disk, or throttled connection, spawning many streams can **fail to speed things up** while increasing cost and error rates.

### 6.1. `gcloud storage` Behavior

Per current `gcloud storage cp` documentation, PCU activation depends on configuration and compatibility checks. Key properties:

| `gcloud` Property | Meaning |
| --- | --- |
| `storage/parallel_composite_upload_enabled` | Enables, disables, or uses default PCU mode. |
| `storage/parallel_composite_upload_threshold` | Minimum file size for `gcloud` to consider PCU; defaults to **150 MiB** per current docs. |
| `storage/parallel_composite_upload_component_size` | Target max size per temporary part; tool still respects the 32-part limit. |
| `storage/parallel_composite_upload_component_prefix` | Prefix for naming temporary objects. |
| `storage/parallel_composite_upload_compatibility_check` | Enables bucket compatibility checks before PCU per tool safety policy. |

`gcloud` verifies compatibility conditions such as **Standard storage class**, **no bucket retention policy**, and **no default object holds** when compatibility checks are active. If the caller lacks `storage.buckets.get` to inspect the bucket, the tool may **fall back to a regular upload** instead of PCU.

**Never disable compatibility checks just to force PCU on a production bucket** without understanding soft delete, retention, part-delete permissions, and cost consequences. Enabling PCU is not mandatory for every upload—treat it as a benchmark-driven performance choice.

### 6.2. PCU IAM Permissions Differ from Single-Object Uploads

A resumable upload creating a new object usually only needs appropriate **object creation** permissions. PCU additionally must:

- Create multiple temporary objects.
- Read source metadata/preconditions and potentially inspect bucket configuration.
- Compose the sources.
- Delete temporary objects after completion.

Consequently, a principal with only `roles/storage.objectCreator` may **succeed on regular uploads** while lacking permissions for the full PCU lifecycle. A role like `roles/storage.objectUser` covers most object operations, yet the CLI's **bucket-level compatibility check** may still require `storage.buckets.get` depending on configuration. Scope permissions to approved buckets/prefixes where IAM allows rather than granting project-wide Storage Admin to silence a CLI error.

### 6.3. PCU Does Not Always Replace Resumable Uploads

| Criterion | Single Resumable Session | Parallel Composite Upload |
| --- | --- | --- |
| Byte transfer | One stream, optionally split into sequential PUTs | Multiple temporary objects uploaded in parallel |
| Resume | From server-confirmed offset in the session | Each part has its own upload/retry flow; tool tracks completed parts |
| Final object | Standard non-composite object (depending on upload) | **Composite object** |
| MD5 metadata | Available on standard uploads when supported | **Absent** on composite objects |
| CRC32C | Used for integrity verification | Especially vital for every part and the final object |
| Intermediate bucket objects | No temporary source objects created | Yes; requires lifecycle and delete permissions |
| Retention / soft delete | Applies to final object | Also affects every temporary object |
| Best fit | Large uploads, reliable resume, simpler permissions | Very large files, fast network, compatible bucket and IAM |

PCU can accelerate transfers, yet adds **operation fees, temporary storage, retained-object overhead, and cleanup complexity**. Benchmark duration, operation count, and total cost before enabling broadly.

### 6.4. When Not to Use PCU

- Bucket has a **retention policy** blocking timely cleanup of temporary parts.
- Bucket enables **default object holds**, requiring holds to be released before deleting parts.
- Soft delete or Object Versioning causes deleted temp parts to remain retained and billable.
- Downstream consumers strictly expect **`md5Hash` metadata** on objects.
- Uploader bandwidth or source disk I/O only saturates one stream.
- Workloads require end-to-end checksum/format pipelines incompatible with current PCU tooling.

If a bucket uses a storage class with a **minimum storage duration**, deleting temporary objects early incurs early deletion charges. That is why Standard storage should be evaluated for temporary parts; any class or policy changes must be approved by the bucket owner.

## 7. Integrity Verification: Size, Generation, CRC32C, and Manifests

"Upload reported success" is not the final proof of data correctness. For large files transferred over minutes or hours, apply **pre-, mid-, and post-upload checks** to catch modified source files, network corruption, out-of-order parts, or invalid compose outputs.

### 7.1. CRC32C and MD5 Differ

| Property | Standard Uploaded Object | Composite Object | Meaning |
| --- | --- | --- | --- |
| `size` | Present | Present | Compare actual byte count with manifest or source file. |
| `generation` | Present | Present | Identifies the accepted content version. |
| `crc32c` | Present per product metadata | Present | Detects payload corruption; compute client-side to compare. |
| `md5Hash` | May be present depending on upload method/metadata | **Absent** | Cannot rely on MD5 metadata for composite objects. |
| `componentCount` | Not primary | Present | Indicates component count in composite metadata. |
| `ETag` | Present | Present | Never assume ETag equals MD5—especially false for composite objects. |

**CRC32C is not a tamper-proof signature.** If you must detect an adversary intentionally altering content and recomputing checksums, use an independent authenticity mechanism (such as a verified signature or hash stored in an authenticated manifest).

### 7.2. Three Distinct Verification Levels

1. **Per part:** compute or record checksum and byte count right after upload; record generation in the manifest.
2. **Post-compose:** verify final object size, generation, and CRC32C against the expected checksum of the **full ordered byte stream**.
3. **At download/consumption:** have consumers verify checksums of received bytes, especially if clients do not auto-verify. For video, CSV, archives, or database dumps, add **application-level format validation**.

For PCU, Google Cloud emphasizes verifying both components and the final composed object. For independent end-to-end verification, compare the immutable source file's checksum against the final object or validate the assembled object in a secure verifier.

### 7.3. Computing CRC32C Client-Side in Python

Example using Python's `google-crc32c` library to compute a file's CRC32C (runs on a host **with local access to the source file**, requiring no Google Cloud access):

~~~python
import base64
import google_crc32c

source_file = "/path/to/source-file.bin"
checksum = google_crc32c.Checksum()

with open(source_file, "rb") as stream:
    while True:
        block = stream.read(8 * 1024 * 1024)
        if not block:
            break
        checksum.update(block)

crc32c_base64 = base64.b64encode(checksum.digest()).decode("ascii")
print(crc32c_base64)
~~~

Where `google-crc32c` is not installed yet, install it in an approved virtual environment. Cloud Storage's CRC32C metadata is encoded as the **Base64 of the big-endian 32-bit value**; `checksum.digest()` is Base64-encoded here to match the object's `crc32c` field directly.

**Do not treat CRC32C like MD5/SHA-256:** they differ in algorithm and representation. If you track an internal SHA-256 for source data, store it in an authenticated manifest and verify it against end-to-end bytes rather than looking for a default SHA-256 field in Cloud Storage metadata.

### 7.4. Multi-Level Compose Checksum Considerations

The final object's CRC32C corresponds to the **concatenated byte stream**, not a string concatenation of per-part CRC32Cs. Mathematically combining per-part CRC32Cs is possible; if your app does not implement and test CRC32C combination, compute CRC32C over the original source file or over an ordered stream of parts and compare against the final object.

For formats that do not allow arbitrary byte concatenation, a matching checksum **does not guarantee a usable file**. For instance, concatenating two valid ZIP files will not produce a single valid ZIP listing all entries. Validate both manifest and file format.

## 8. Designing Secure Large-Upload Architectures

### 8.1. Proxy All Bytes Through Backend vs. Direct Client Upload?

| Architecture | Advantages | Risks / Work Required |
| --- | --- | --- |
| **Client → backend → Cloud Storage** | Backend centralizes auth, inspection, and validation in one pipeline. | Consumes backend bandwidth and compute, especially for large videos; gateway timeouts/body limits. |
| **Client → Cloud Storage via backend-issued access** | Bytes bypass app servers; scales smoothly to many uploaders. | Must secure session URIs, upload permissions, object names, CORS, and post-upload verification. |
| **Uploader on Compute Engine/GKE → Cloud Storage** | Suits backend pipelines with service accounts and co-located networks. | Must manage concurrency, retries, location, IAM, and costs. |
| **Batch part uploads then compose** | Resumable per part and parallel bandwidth scaling. | Manifests, race conditions, temp objects, integrity checks, and operation costs. |

Example direct video upload flow:

~~~mermaid
sequenceDiagram
    participant U as Authenticated client
    participant A as Application backend
    participant S as Cloud Storage
    participant Q as Job DB / manifest
    U->>A: Request upload for lesson-42
    A->>A: Check business IAM, quota,<br/>type, size, object path
    A->>S: Initiate conditional upload session
    S-->>A: Session URI
    A->>Q: Save upload ID and owner
    A-->>U: Scoped upload grant / session URI
    U->>S: PUT bytes, resumable
    S-->>U: 308 or 200/201
    U->>A: Report completion (upload ID)
    A->>S: Read object metadata
    S-->>A: Generation, size, CRC32C
    A->>Q: Mark READY only after valid verification
~~~

Crucial rule: the backend **never trusts** a client claiming an upload succeeded. The backend inspects the object using an authorized identity, confirming exact bucket, prefix, generation, size, checksum/manifest, and business ownership.

### 8.2. A Signed URL Is Not a Session URI

A **signed URL** authorizes one Cloud Storage operation scoped by signed method, resource, and expiration. In supported upload flows, a server can issue a signed URL to **initiate** a resumable upload; once the session exists, the client uses the **session URI** returned by Cloud Storage.

| Property | Signed URL | Resumable Session URI |
| --- | --- | --- |
| Issuer | Signing party authorized for a scoped operation | Returned by Cloud Storage upon session creation |
| Authority | Signed method/resource/headers/expiration | Continue sending bytes in **that specific upload session** |
| Security | Access-granting URL; keep secret until expiry | Bearer secret; anyone holding the URI can use the session |
| Lifecycle | Governed by signature expiry and signing key | Session typically expires after one week or upon cancellation |

Never expose session URIs in browser analytics logs or public source code. When browsers talk directly to Cloud Storage endpoints, configure **CORS** on the bucket allowing only required origins and methods—never treat CORS as authentication replacing IAM or signed authorization.

### 8.3. Scoping Permissions to Prevent Cross-Tenant Access

A multi-tenant system must enforce:

- Clients can only write into a **namespace bound to their own account/job**; never accept `../../tenant-other` from unvalidated user input.
- **Generation preconditions** prevent overwriting another user's object or a finalized job.
- Backend service accounts hold scoped **bucket/prefix** IAM roles; avoid project-wide Storage Admin unless truly required.
- Temporary part cleanup targets **only the upload ID owned by that job**, never broad wildcards that could touch other users' objects.
- Enforce **size limits, file-type checks, app quotas, concurrent upload caps**, and rate limits to prevent abuse and cost spikes.
- Post-upload, inspect raw bytes for true file type (beyond filename extensions) and run malware scans where required.
- Promote objects from `staging` to `published` only after checks pass; viewers can only access authorized content.

**Data residency:** when handling sensitive videos or documents, pick a bucket location matching policy and verify where uploaders, analyzers, CDNs, logs, and replicas run. Keeping parts in the same bucket for compose cuts client transfer, yet does not automatically satisfy every residency mandate.

## 9. Performance, Reliability, and Total Upload Cost

### 9.1. Measure Timing Instead of Watching Progress Bars

A large upload can bottleneck in several places:

| Signal | Possible Cause | How to Measure / Tune |
| --- | --- | --- |
| Slow client source reads | Local disk, CPU, antivirus, or network-mounted source | Measure sustained sequential read speed; cut I/O contention. |
| High RTT with tiny chunks | Per-request and offset-check overhead | Increase chunk size reasonably to reduce round trips. |
| WAN packet loss | Frequent upload retries and low throughput | Track retries, RTT, packet loss; use resumable + backoff. |
| Single stream underutilizes bandwidth | Single-connection ceiling in that environment | Benchmark PCU or bounded parallel file uploads. |
| PCU uses many parts yet runs slower | Temp create/delete/compose overhead, socket contention, slow disk | Benchmark identical files and lower concurrency. |
| Upload finishes yet publishing lags | Checksums, scanning, metadata queries, multi-level compose | Instrument `upload`, `compose`, `verify`, and `publish` separately. |
| Frequent `412` retries | Colliding object names/generations across workers | Fix idempotency and isolate upload IDs. |
| Uploads time out after hours | Session expired, lost state, or source file changed | Persist state securely; track session age and file fingerprint. |

### 9.2. Where the Resumable Session Is Initiated Affects Speed

A resumable upload session is **bound to the geographic location where it was initiated** per service behavior. For instance, a backend in a distant region initiating a session can route upload traffic through that region. If clients are in Asia while the initiating server sits in the US, uploads may incur extra RTT and suboptimal routing.

For globally distributed users:

1. Identify where bytes are actually uploaded from.
2. Design session initiation and bucket placement around data requirements.
3. Measure p50/p95 upload times, actual throughput, and RTT across client regions.
4. Do not distribute session URIs initiated in a distant location without measuring impact.

**Location optimization does not override data residency rules.** Always verify bucket location, processing locations, access controls, and network paths.

### 9.3. Cost Categories to Budget

| Component | What Generates Charges? | Risk Reduction |
| --- | --- | --- |
| **Final object** | Storage capacity by class, location, and duration | Pick class matching actual read lifecycle. |
| **Temporary parts** | Separate storage before/after compose until deleted | Clean up after verification; avoid orphaned parts. |
| **Upload / compose requests** | Per-operation fees, especially with tiny chunks or multi-level compose | Track request counts; avoid needlessly small chunks. |
| **Download / validation** | Egress and read operations depending on location and target | Compute checksums at source when possible; verify efficiently. |
| **Soft delete / Object Versioning** | Retained deleted copies and noncurrent versions continue billing | Configure temp prefixes/buckets intentionally per policy. |
| **Retention / minimum duration** | Early deletion fees or blocked cleanup of temp parts | Avoid PCU where incompatible; check bucket policies before uploading. |
| **Logging, Monitoring, job DB** | Log ingestion, storage, state tracking, metrics | Never log session tokens; set deliberate log retention. |
| **Compute / Cloud Run / GKE** | CPU/RAM/I/O for splitting, scanning, transcoding, checksums | Tune autoscaling, quotas, timeouts, and concurrency. |

Exact rates vary by location, storage class, and current pricing. **Budget alerts do not impose hard spending caps.** For bulk video pipelines, forecast job counts, file sizes, staging dwell time, and failed-upload overhead.

### 9.4. Operational Metrics Worth Tracking

Emit metrics and state logs **without session URIs**:

- `upload_started`, `upload_completed`, `upload_aborted`, and per-stage durations.
- Bytes sent by clients vs. **bytes confirmed saved by the server**, rather than trusting local progress bars.
- `308` frequency, retry counts, `429/5xx` rates, and expired sessions.
- Compose duration, part counts, compose depth, and `412` precondition conflicts.
- Orphaned temp objects exceeding age thresholds, staging bytes, and soft-deleted/noncurrent bytes.
- Jobs uploaded yet stuck before verification or publication.
- Checksum mismatch rates, size/format rejections, failed scans, and successful recoveries/retries.

Slice dashboards by **client type, geography, file type, bucket, and uploader version** to spot localized regressions. Never put PII-bearing object names into high-cardinality metric labels.

## 10. Hands-On Lab: Uploading Parts and Composing Safely

### 10.1. Objective and Prerequisites

This lab uses three tiny ASCII files to prove **compose concatenates bytes in exact order**. Once the flow is clear, you can apply the same pattern to large files. The goal is correctness and operational verification, not throughput benchmarking.

**Prerequisites:**

- An **organization-approved** lab project/bucket with an active Cloud Billing account.
- Permissions to create, describe, download, and delete **objects you created yourself**; if you lack delete permissions, arrange admin support for cleanup.
- The bucket has no retention policies or holds that would block lab cleanup or create significant charges. If such policies exist, stop before creating parts.
- Running `gcloud` in Bash or Cloud Shell under an authorized identity.
- Never run labs inside prefixes used by production apps or reuse someone else's upload ID.

### 10.2. Prepare Three Local Parts and a Simple Manifest

On **your own machine**, create three non-sensitive files:

~~~bash
export PROJECT_ID="YOUR_LAB_PROJECT_ID"
export BUCKET_NAME="YOUR_APPROVED_LAB_BUCKET"
export UPLOAD_ID="lab-unique-id-you-own"

gcloud config set project "$PROJECT_ID"
gcloud storage buckets describe "gs://$BUCKET_NAME" \
  --format="yaml(name,location,storageClass,softDeletePolicy,retentionPolicy)"

printf 'AAA' > part-0001.bin
printf 'BBB' > part-0002.bin
printf 'CCC' > part-0003.bin
printf 'AAABBBCCC' > expected.bin

wc -c part-0001.bin part-0002.bin part-0003.bin expected.bin
~~~

You should see 3 bytes per part and 9 bytes for `expected.bin`. `UPLOAD_ID` must be **unique** to you/this job (for example, adding a team handle and timestamp); it namespaces objects to avoid colliding with others and is not a credential.

Inspect the bucket before uploading to confirm location, storage class, soft delete/retention, and permissions. If you lack `storage.buckets.get` to inspect the bucket, ask an admin to confirm policies—**never skip verifying whether temp parts can be cleaned up**.

### 10.3. Upload the Three Parts Sequentially

~~~bash
gcloud storage cp part-0001.bin \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin"

gcloud storage cp part-0002.bin \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin"

gcloud storage cp part-0003.bin \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin"
~~~

Read back metadata:

~~~bash
gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin" \
  --format="yaml(name,size,generation,crc32c,storageClass)"

gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin" \
  --format="yaml(name,size,generation,crc32c,storageClass)"

gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin" \
  --format="yaml(name,size,generation,crc32c,storageClass)"
~~~

Confirm each part is **3 bytes**, properly named, in the same storage class, and has its own generation. In a real application, save these generations in your manifest to prevent mixing parts across jobs.

### 10.4. Compose into a New Object

~~~bash
gcloud storage objects compose \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin"
~~~

**Race note:** run this example only after verifying `final.bin` does not exist yet and no other job writes under the same prefix. In production, replace this with **compose using generation preconditions on both sources and destination** as shown in Section 5.3.

Verify output:

~~~bash
gcloud storage objects describe \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin" \
  --format="yaml(name,size,generation,componentCount,crc32c,md5Hash)"

gcloud storage cp \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin" \
  ./downloaded-final.bin

cmp expected.bin downloaded-final.bin
wc -c expected.bin downloaded-final.bin
~~~

The expected result is silent `cmp` output with **exit code 0**, and both files measuring **9 bytes**. The final object's metadata includes `crc32c`, while `md5Hash` may be **absent** because it is a composite object.

If you swapped source order to put `part-0002` before `part-0001`, the bytes would differ (`BBBAAACCC`) even though every part uploaded fine. That is why ordering and manifests are business-critical, not mere implementation details.

### 10.5. Completion Criteria Check

| Criterion | How Proven |
| --- | --- |
| Source objects exist with exact names | Metadata of all three parts under your isolated prefix |
| Sources remain unchanged by compose | Re-read generations and sizes after compose |
| Final object concatenated in exact order | `cmp expected.bin downloaded-final.bin` succeeds |
| Final object has exact size | `size=9` bytes |
| Integrity verifiable | `crc32c` metadata; matches checksum of downloaded bytes |
| Understands race protection | Can explain `ifGenerationMatch=0` and source generations |
| Temp objects cleaned up | Verified permissions and policies before deleting, then re-checked |

### 10.6. Clean Up Only Your Lab Objects

**Only after verifying results**, inspect the exact listing:

~~~bash
gcloud storage ls "gs://$BUCKET_NAME/staging/$UPLOAD_ID/"
~~~

In a lab bucket with no unexpected retention or holds, delete **each specific object**:

~~~bash
# Delete operation: ONLY for the exact upload ID and objects you created
gcloud storage rm \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0001.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0002.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/part-0003.bin" \
  "gs://$BUCKET_NAME/staging/$UPLOAD_ID/final.bin"

gcloud storage ls "gs://$BUCKET_NAME/staging/$UPLOAD_ID/"
~~~

If **soft delete** or **Object Versioning** is enabled, deletion may retain deleted/noncurrent copies that keep incurring minor charges. If a retention policy blocks deletion, **never modify or disable a shared bucket's policy** just to make the lab "clean"; notify the administrator and document the remaining objects.

Local files `part-*.bin` and `downloaded-final.bin` on your machine do not disappear when deleting from Cloud Storage. Keep them as study artifacts or remove only your lab files after verification.

## 11. Troubleshooting Common Issues

| Symptom | Likely Cause | Controlled Resolution |
| --- | --- | --- |
| Upload stalls after network drop | Client did not persist session URI or failed to query saved offset | Use resumable-capable SDK/CLI, or send status query to session URI and resume from `Range`. |
| Session returns `404` or `410` | Session expired, canceled, or no longer valid | Start a new session, verify source file is unchanged, and re-upload from byte 0. |
| Upload gets `308` and client treats as redirect error | Custom HTTP code misinterprets status | Parse `Range` from `Resume Incomplete`; never follow as a redirect. |
| Mid-upload returns `400` on `Content-Range` | Invalid offset, total size, header, or chunk alignment | Stop sending, run status query to check session state; start new session if needed. |
| Final object has wrong size | Missing, duplicate, or out-of-order part, or source mutated mid-upload | Check manifest, generations, sizes, and checksums; rebuild from verified sources. |
| Compose fails with too many sources | Exceeded 32 source objects in one request | Break into multi-level composes with ≤ 32 sources per call. |
| Compose fails due to invalid source | Source in different bucket/class, generation changed, or deleted | Verify each source's metadata, generation preconditions, and bucket policy. |
| Compose succeeds yet output is invalid | Parts out of order or file format incompatible with byte concatenation | Compare checksums/bytes and test opening with an application parser. |
| `412 Precondition Failed` | Destination already exists or source generation changed | Re-read manifest/object; reconcile idempotently instead of dropping preconditions. |
| PCU does not trigger on large file | Incompatible bucket, missing `storage.buckets.get`, or CLI/size config below threshold | Check CLI logs, threshold, permissions, storage class, retention/holds; accept fallback if appropriate. |
| PCU upload leaves temp objects behind | Job failed before compose or cleanup skipped | Locate exact upload ID/prefix, reconcile job state, and clean up per policy if permitted. |
| Cannot delete temp parts | Retention, hold, or permissions protect objects | Never break production policies; coordinate with bucket owner and track residual cost. |
| Total bucket size grows despite deleting parts | Soft delete or Object Versioning retains deleted/old copies | Check retention/versioning state and billing; evaluate appropriate lifecycle rules. |
| Consumer reports missing MD5 on composite object | Composite objects lack MD5 metadata | Use CRC32C; verify via supported libraries or independent source hashes. |
| Upload speed stays low even with PCU | Slow source disk/network, excessive concurrency, or heavy retries | Benchmark each stage, reduce contention, and tune settings empirically. |
| App reports "completed" yet no valid object exists | Trusted client signal without verifying destination metadata or generation | Have backend verify object metadata before marking job READY. |

### 11.1. Investigating an Upload with Unknown Completion Status

When the client loses the final response:

1. **Do not immediately resend everything** if the session may still be active.
2. Query the resumable session status; note `308` and `Range` if incomplete.
3. If the server confirms completion, inspect destination metadata and compare against the manifest.
4. If the session is gone/expired, check whether the destination object already exists with the expected generation, size, and checksum—the earlier attempt may have succeeded.
5. If no valid object exists, start a new upload with the appropriate generation precondition.
6. Log job state, timestamps, server-confirmed bytes, and retry cause.

For compose, if a request times out, **never blindly re-compose to the same name without checking**. Inspect destination metadata and generation first; the server may have completed the compose before the connection dropped.

### 11.2. Diagnosing IAM Errors

Distinguish each step:

- **Initiate resumable upload:** principal needs object creation/write permissions and must satisfy bucket policies.
- **PUT to session URI:** a valid session URI carries upload authority for that session; do not inject another user's credentials trying to fix it.
- **Compose:** requires destination creation permission plus source read permissions per the Compose API/SDK.
- **Cleanup:** deleting temporary objects requires delete permissions while respecting retention/holds.
- **Reading back metadata and validation:** requires object read permissions per bucket setup.
- **PCU via `gcloud`:** bucket compatibility checks may require bucket-read permission (`storage.buckets.get`), unlike simple single-object uploads.

Identify **which exact step lacks which permission** and grant least-privilege access there. Never treat project-wide Storage Admin as a safe default fix.

## 12. Design Scenario: Uploading Large Course Videos

A Java learning platform uses a Cloud Run API, Cloud Storage for videos, a database for lesson metadata, and Cloud CDN for approved content. Users upload from many countries over flaky links. Each video is 1 to 20 GiB; requirements call for zero data loss, never publishing another owner's video, and clear cost observability.

### 12.1. Proposed Architecture for Analysis

~~~mermaid
flowchart LR
    USER["Author / uploader"] --> API["Cloud Run API<br/>auth, quota, manifest"]
    API --> DB[("Job DB")]
    API --> SES["Initiate resumable session<br/>with generation precondition"]
    SES --> GCS["Cloud Storage staging"]
    USER -->|"Upload bytes / resume"| GCS
    GCS --> SCAN["Verify checksum, size,<br/>type, malware scan"]
    SCAN --> PUB["Published object<br/>or READY state"]
    PUB --> CDN["Load balancer / Cloud CDN"]
    CDN --> STUDENT["Authorized learners"]
~~~

This is a logical model. In real implementations, decide whether moving from staging to published uses **conditional copy/rewrite, an application state flip, or another publish path**; Cloud Storage does not offer a universal POSIX-like object rename across all bucket configurations.

A sound design must answer:

1. **Identity:** who may initiate upload sessions, and into which prefixes?
2. **Continuity:** does the client store the session URI safely and resume across refreshes or disconnects?
3. **Consistency:** if the user swaps the source file mid-resume, does the system catch it?
4. **Correctness:** is final metadata verified against the manifest and checksum before marking READY?
5. **Concurrency:** can two people publishing the same lesson overwrite each other?
6. **Delivery:** how does the system ensure only scanned/approved videos reach the CDN?
7. **Cost:** could orphaned temp objects or long-retained versions accumulate?
8. **Availability:** if a Cloud Run instance restarts, do the upload session and job state survive?
9. **Security:** could tokens, session URIs, or object paths leak into logs or wrong tenants?
10. **Operations:** which metrics, alerts, and runbooks catch jobs stuck in `COMPOSING` or `VERIFYING`?

### 12.2. Quantitative Exercises and Design Choices

**Exercise A — Calculating parts and compose calls.** A system splits a 45 GiB file into **45 parts of 1 GiB each** already uploaded to a bucket. Each compose accepts at most 32 sources. Propose a minimal-depth compose plan:

- Compose the first 32 parts into `intermediate-A`.
- Compose the remaining 13 parts into `intermediate-B`.
- Compose A then B into the final object.

This takes **3 compose requests** total. The final object remains under 5 TiB; parts and intermediates must share the bucket and compatible storage class, with generation preconditions and checksum checks.

**Exercise B — Disconnect after sending 32 MiB.** A client sends 32 MiB and receives no response. A status query returns:

~~~http
HTTP/1.1 308 Resume Incomplete
Range: bytes=0-25165823
~~~

What is the first byte of the next upload request? **Answer:** byte **25,165,824** (24 MiB), because the server confirmed byte 25,165,823 as the last saved byte. Never jump ahead to 32 MiB based on client progress.

**Exercise C — Comparing two designs:** for an app ingesting 500 videos/day of 4 GiB each, compare single-stream resumable upload per video against PCU. Measure upload speed, retry counts, temporary objects, operation counts, checksum mismatch rates, costs, and operational effort; adopt PCU only if benchmarks prove a net benefit.

**Exercise D — Accidental overwrites:** two uploaders both try publishing `videos/lesson-42.mp4`. Use distinct upload IDs and `ifGenerationMatch=0` (or an expected destination generation) to protect publishing. Describe what happens when one side receives `412`.

### 12.3. Self-Check Questions

**1. Are resumable uploads and parallel composite uploads the same thing?**  
No. A resumable upload writes to a single session capable of resuming from persisted offsets; PCU uploads multiple temporary objects in parallel and composes them into the final object.

**2. Does `308 Resume Incomplete` mean a permanent upload failure?**  
No. It indicates the server has not yet received the entire payload; read `Range` and resume from the next offset.

**3. When a `308` response has no `Range` header, where must the client start?**  
At byte 0, because the server has not yet persisted any bytes.

**4. How many source objects can one compose call accept at most?**  
At most **32**; multi-level compose using intermediate composite objects handles larger counts.

**5. Does compose parse MP4, ZIP, or CSV syntax to merge files validly?**  
No. It performs raw byte concatenation; the application is responsible for format compatibility and ordering.

**6. Why should you not require MD5 metadata on a composite object?**  
Because composite objects do not have MD5 metadata; use CRC32C and appropriate end-to-end verification.

**7. Why can a `412` on a compose request actually be a good sign?**  
Because preconditions prevented an overwrite or caught a mutated source—or a prior attempt already succeeded cleanly. Re-read metadata to confirm.

**8. Does deleting source parts always stop storage charges immediately?**  
No. Soft delete, versioning, retention, minimum storage durations, and billing rules may keep data retained or incur charges.

**9. Can a session URI be made public since it is just an API endpoint path?**  
No. It is a bearer secret authorizing uploads to that session; keep it confidential and HTTPS-only.

**10. Should the backend trust a client's "upload succeeded" message?**  
No. The backend must verify the object, generation, size, checksum, and ownership before publishing.

## 13. Official Google Cloud Documentation

- **Resumable uploads:** https://cloud.google.com/storage/docs/resumable-uploads — session URI, expiry, chunking, performance, and security.
- **Perform resumable uploads:** https://cloud.google.com/storage/docs/performing-resumable-uploads — HTTP initiation, status queries, resuming, and canceling.
- **Compose objects:** https://cloud.google.com/storage/docs/composing-objects — `gcloud`/SDK usage, compose limits, and source cleanup.
- **Composite objects:** https://cloud.google.com/storage/docs/composite-objects — CRC32C, MD5, ETag, metadata, and composite semantics.
- **Parallel composite uploads:** https://cloud.google.com/storage/docs/parallel-composite-uploads — parallel strategy, `gcloud` settings, permissions, and temporary costs.
- **Data validation and change detection:** https://cloud.google.com/storage/docs/data-validation — checksums, data protection, and completion checks.
- **Generation preconditions:** https://cloud.google.com/storage/docs/request-preconditions — write/compose conditions preventing race conditions.
- **Cloud Storage quotas and limits:** https://cloud.google.com/storage/quotas — 5 TiB max object size and 32 sources per compose.
- **JSON API compose:** https://cloud.google.com/storage/docs/json_api/v1/objects/compose — request schema and source generations.
- **Cloud Storage pricing:** https://cloud.google.com/storage/pricing — operations, storage, network, retention, and related fees.
- **Cloud Storage IAM:** https://cloud.google.com/storage/docs/access-control/iam — bucket and object access permissions.
- **Object Lifecycle Management:** https://cloud.google.com/storage/docs/lifecycle — lifecycle rules, timing, and conditions.
- **Signed URLs:** https://cloud.google.com/storage/docs/access-control/signed-urls — time-limited client access operations.
- **Cloud Storage CORS:** https://cloud.google.com/storage/docs/cross-origin — configuring browser access.

`gcloud` defaults, SDK options, IAM details, limits, upload methods, and pricing are subject to change. When deploying to live systems, verify official documentation for your **exact API, client library, bucket policy, and location**. A sound large-file upload pipeline can **safely resume after interruptions**, assemble final objects with **exact bytes and exact generations**, protect credentials, and track temporary objects, costs, and recovery readiness.
