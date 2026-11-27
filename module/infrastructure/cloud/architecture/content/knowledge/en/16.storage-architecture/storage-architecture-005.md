# Large Uploads, Resumable Transfers, and Time-Limited Access

Applications that store images, videos, documents, or backups frequently need to accept files ranging from hundreds of MB to multiple GB. Sending an entire file through a backend in a single HTTP request can hit timeouts, payload limits, high memory usage, and poor recovery when connections drop. Conversely, issuing a URL for direct uploads to object storage without tight permission controls lets users write to the wrong path, overwrite data, or share links longer than intended.

This lesson focuses on three capabilities: **large uploads**, **resumable uploads**, and **time-limited access**. Within the CLOUD_ARCHITECTURE module, this problem spans storage, networking, compute, identity, security, and operations. Good architecture enables efficient, recoverable transfers, enforces authorization, tracks object lifecycles, and balances cost with reliability.

## 1. Choosing the Transfer Path: Through the Backend or Direct to Storage?

Suppose a user uploads a 2 GB video to a booking platform.

### Proxying Uploads Through the Backend

~~~mermaid
flowchart LR
    C["Browser / Mobile"] -->|"Upload file"| API["Application API"]
    API -->|"Stream bytes"| S[("Object storage")]
    API --> DB[("Metadata database")]
~~~

The backend receives the data and forwards it to storage. This model is useful when inline content transformation is required, clients cannot reach storage directly, or network policy mandates traffic passing through a single control point.

Trade-offs:
- The backend consumes bandwidth, connections, and compute throughout the transfer.
- Proxy, load balancer, and application timeouts must accommodate upload size/duration.
- Long-lived requests tie up workers; traffic spikes reduce capacity for business APIs.
- If a client disconnects, the backend must manage state, clean up partial data, and handle resume.
- The client → backend → storage path can increase transfer or processing costs.

If using a proxy, stream data instead of buffering entire files in RAM; cap concurrency, total duration, minimum throughput, and maximum size.

### Direct Upload via Signed URL

~~~mermaid
sequenceDiagram
    actor U as User
    participant API as Application API
    participant DB as Metadata DB
    participant S as Object storage
    U->>API: Request upload session
    API->>API: Auth, permissions, quota
    API->>DB: Save PENDING session
    API-->>U: Signed upload URL / part instructions
    U->>S: Upload bytes directly
    S-->>U: Part receipt / result
    U->>API: Report completion
    API->>S: Verify object, size, checksum
    API->>DB: Update state
    API-->>U: Upload status
~~~

The backend orchestrates the session and issues pre-signed/signed URLs or upload instructions per storage capabilities. The client transfers bytes directly to object storage. The backend remains responsible for authenticating the user, choosing the object key, checking quotas and ownership, finalizing, and updating metadata.

The advantage is that the backend avoids proxying payloads, leverages multipart/resumable uploads, and scales cleanly across many clients. The trade-off is that the client holds a URL acting as a bearer capability while valid; you must manage CORS, quotas, expiry, temporary objects, content validation, and abandoned sessions.

Signed URLs do not replace authorization at session creation and post-upload object verification.

## 2. Object Model and Upload States

Object storage usually organizes data by bucket/container and object key. The backend should generate keys; never let clients write freely to arbitrary paths.

~~~text
tenant-42/bookings/BK-9081/uploads/up-7f3a/original
tenant-42/bookings/BK-9081/uploads/up-7f3a/preview
~~~

This is an illustrative structure. Avoid embedding sensitive personal data in keys, since keys appear in logs, URLs, and metrics. Use random IDs and store mappings in a metadata database.

The metadata record should include `uploadId`, `ownerId`/`tenantId`, `objectKey`, display filename, `expectedSize`, `expectedChecksum`, `contentTypeClaimed`, `state`, `expiresAt`, `storageUploadId`, `createdAt`, and `completedAt`.

Reference states:
- `PENDING`: session created, no data transferred yet.
- `UPLOADING`: currently receiving parts or byte ranges.
- `COMPLETING`: client reported done; server is verifying completion.
- `QUARANTINED`: object received, awaiting scanning/validation.
- `COMPLETE`: passed mandatory checks, approved for use.
- `FAILED` or `EXPIRED`: failed or timed out.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> UPLOADING
    UPLOADING --> COMPLETING
    COMPLETING --> QUARANTINED
    COMPLETING --> FAILED
    QUARANTINED --> COMPLETE
    QUARANTINED --> FAILED
    PENDING --> EXPIRED
    UPLOADING --> EXPIRED
~~~

Separating `QUARANTINED` from `COMPLETE` helps when files must pass antivirus, format checks, or moderation. Grant read access only to objects that have passed all mandatory checks.

## 3. Multipart Upload and Resumable Upload

### Multipart Upload

The client splits a file into parts. Storage retains each part within an upload session; once all required parts arrive, the client/backend issues a complete command to assemble the final object.

~~~mermaid
flowchart TB
    F["2 GB File"] --> SPLIT["Split into parts"]
    SPLIT --> P1["Part 1"]
    SPLIT --> P2["Part 2"]
    SPLIT --> P3["Part 3"]
    SPLIT --> PN["Part N"]
    P1 --> S[("Upload session")]
    P2 --> S
    P3 --> S
    PN --> S
    S --> COMPLETE["Complete multipart"]
    COMPLETE --> OBJ[("Final object")]
~~~

Typical operations:
1. Initiate: create a multipart session; storage returns an upload ID.
2. Upload part: send each part, usually with a part number and checksum/ETag depending on the service.
3. List parts: fetch the list of parts already acknowledged by storage.
4. Complete: submit the list of parts/identifiers to finalize the object.
5. Abort: cancel the session when no longer needed or expired.

If part 17 fails, the client can re-upload just that part. Multipart does not automatically guarantee browser/device resume across restarts; the application must persist the upload ID, part state, and corresponding authorization.

### Resumable Upload

Resumable upload continues transferring after a connection drop. It can be built on multipart APIs, session URI/offset APIs, or custom protocols.

A session should store:
- Session ID/URI and validity expiration.
- Storage-side upload ID or destination object.
- Total size, chunk size, and expected checksum.
- Parts/offsets confirmed by the server.
- Owning user/tenant.
- Completion or cancellation status.

Do not save progress only in the browser and assume the server received those exact bytes. On reconnect, the client must query the server/storage for how much was received via list parts, offset/status, or the equivalent API. Local progress can be wrong if a response was lost after storage accepted a chunk.

### Chunk Size and Concurrency

Chunks that are too small inflate request counts, HTTP/TLS overhead, and metadata. Chunks that are too large force retries to re-send many bytes, increasing buffering and wait time. Uploading too many parts in parallel increases throughput at the cost of sockets, CPU, bandwidth, and throttling.

For example, a 1 GiB file with 16 MiB chunks needs roughly 64 parts (ignoring unit differences and provider limits). Four concurrent parts can improve throughput while consuming more connections. This is a quantitative illustration, not a universal default.

### Orchestration Pseudocode

~~~text
session = POST /uploads {fileName, size, checksum}

while parts remain:
    part = next part within allowed concurrency
    response = PUT signed_part_url(part)
    if success:
        save part number and provider receipt
    else if retryable:
        retry with bounded backoff
    else:
        stop and report failure

serverParts = GET /uploads/{uploadId}/parts
reconcile local progress with serverParts
result = POST /uploads/{uploadId}/complete
verify object metadata and checksum
~~~

If `complete` times out after storage already finalized the object, do not assume the upload failed. Client/server must query object/session status before calling `complete` again.

## 4. Checksums, Integrity, and ETags

Transferring the right byte count does not prove received content matches the source.

- Checksums like CRC32C or SHA-256 can detect data corruption under supported semantics.
- An ETag is a storage-returned validator/identifier; never assume an ETag is always the MD5 of the whole object.
- Multipart checksums may be per-part checksums or a composite checksum.
- Size validation confirms actual byte length.
- Content validation inspects true file format from bytes, not just the client-declared MIME type.

Workflows should compute or receive expected checksums, send checksums per supported APIs, verify results on storage, compare after `complete`, and quarantine objects on mismatch. Checksums detect unintended alterations; **they do not authenticate the sender** or prove a file is safe.

## 5. Signed Upload URLs and Time-Limited Write Access

A pre-signed upload URL typically authorizes a client to perform a specific action on an object/part within a signed time window and set of constraints.

Secure flow:
1. Client authenticates with the Application API.
2. Backend checks permission to upload to the resource/tenant.
3. Backend validates quota, size, and allowed file types.
4. Backend creates a hard-to-guess object key and session.
5. Backend issues a signed URL with the proper method, key, headers/constraints, and expiry.
6. Client uploads directly.
7. Backend verifies the outcome and moves the object to usable status only after checks pass.

**A signed URL is a bearer capability:** anyone possessing a valid URL can exercise its signed permissions until expiry or until the underlying credential/policy is invalidated per provider semantics.

Controls:
- Short expiration matched to the use case.
- Scoped to a single object key/part; never grant bucket-wide access.
- Constrain HTTP method and critical headers.
- Enforce content length/type where the provider supports it; otherwise verify post-upload.
- Transmit over HTTPS; prevent URLs from appearing in referrers, analytics, and application logs.
- Never let clients pick arbitrary buckets, tenant prefixes, or object keys.
- Enforce quotas and rate limits before issuing URLs.
- Control overwrites/versioning so old URLs cannot overwrite critical data.

Some services do not enforce every content-length condition or one-time-use rule in the way you might expect. If stricter bounds are required, use upload policies/forms, gateways, or post-upload verification. Never claim a URL is one-time-use if it is merely time-bounded and repeatable.

## 6. Time-Limited Downloads and Signed URLs

For private objects, the backend authenticates the user, checks file authorization, and issues a signed download URL. The client downloads directly from storage/CDN.

~~~mermaid
sequenceDiagram
    actor U as User
    participant API as Application API
    participant DB as Authorization DB
    participant S as Private storage
    U->>API: Request download for fileId
    API->>DB: Verify ownership, tenant, state
    DB-->>API: Authorized + object key
    API->>S: Generate short-lived signed GET URL
    S-->>API: URL + expiry
    API-->>U: Temporary URL
    U->>S: GET object
    S-->>U: Object bytes
~~~

Distinguish clearly:
- A signed URL may continue working until expiry even if the user just logged out.
- Deleting application metadata does not automatically revoke the object or an active URL.
- Changing policies, rotating keys, or deleting the object may invalidate URLs, but can carry a broad blast radius.
- A CDN may keep serving cached content after URL expiry if cache policies allow it.

If immediate revocation is required, plain signed URLs may fall short because they are self-contained capabilities with an expiry. You can proxy downloads through an API/gateway that checks authorization per request; use revocable CDN tokens/cookies; bind URLs to revocable credentials/policies; or choose short expiries and accept a bounded revocation window.

Access lifetime depends on the data and use case. A preview image link may live longer than a contract or personal record download link.

## 7. Range Requests, Streaming, and Resumable Downloads

HTTP Range lets clients request a byte slice of an object, commonly used for resuming downloads or video scrubbing:

~~~http
GET /files/video.mp4 HTTP/1.1
Range: bytes=1048576-2097151
~~~

The server can respond with `206 Partial Content`, `Content-Range`, and the requested byte slice.

Ranges are helpful for download resume, audio/video seeking, fetching part of a large file, or downloading ranges in parallel. Pair them with `ETag`/`Last-Modified` and `If-Range` so slices from two different object versions are never stitched together. If the object changes mid-download, the assembled file can be corrupted.

Streaming processes bytes incrementally rather than buffering an entire object in RAM. When proxying downloads, limit concurrency, apply backpressure, and enforce timeouts. When serving directly from storage/CDN, manage authorization and caching.

## 8. Differences Across Object Storage Services

| Platform | Large/resumable upload mechanism | Signed access | Things to verify |
|---|---|---|---|
| **Amazon S3** | Multipart upload, upload part, list parts, complete/abort | Pre-signed URLs for uploads/downloads and parts | Part size/count, lifecycle cleanup of incomplete multiparts, checksums, expiry, and signing permissions |
| **Azure Blob Storage** | Block blob uploads via block IDs then commit block list; SDK transfer options | SAS scoped by resource, permissions, and time; user delegation SAS backed by Entra credentials where appropriate | Block size/count, SAS permissions/start/expiry, CORS, and identity |
| **Google Cloud Storage** | Resumable upload via session URI, continuing byte ranges | Signed URLs for uploads/downloads; signed policy documents for certain form uploads | Session URI is a sensitive capability; chunk alignment/progress, signing identity, expiry, and checksums |

Do not treat these mechanisms as identical:
- S3 multipart uses an upload ID and part identifiers; incomplete uploads persist until aborted or cleaned up by lifecycle rules.
- Azure block blobs stage blocks by block ID and then commit a block list; distinguish SAS types, permissions, and validity windows.
- GCS resumable uploads use a session URI to resume sending bytes; the session URI must be protected like a credential for that upload session.

SDKs can automatically split parts, retry, or resume to some degree. Clarify what the SDK manages versus what the application must persist durably. When upgrading SDKs, check behavior, retries, and checksums.

## 9. Managing Upload Sessions and Cleaning Up Abandoned Resources

Sessions can be abandoned when users close browsers, devices run out of battery, networks drop for long periods, or apps fail to send complete/abort. Temporary parts can still consume storage and incur charges.

Required practices:
- Bind each session to a specific user/tenant and object key.
- Store `createdAt`, `expiresAt`, and `state`.
- Limit concurrent sessions per user/tenant.
- Automatically expire/abort inactive sessions.
- Use storage lifecycle rules to purge incomplete multiparts if supported.
- Clean up corresponding metadata without accidentally deleting completed objects.
- Write audit logs when aborting/cleaning up important data.
- Handle races between cleanup and a client actively uploading or completing.

A scheduler can find expired `PENDING`/`UPLOADING` sessions, check storage status, abort the upload, and mark `EXPIRED`. Do not rely on a database flag alone if the storage-side upload remains active.

### Idempotency for Create and Complete

Clients may retry session creation if they miss a response. If the API creates a new session every time, abandoned uploads pile up. Use an idempotency key per user and operation, or allow looking up sessions by request ID.

`Complete` can time out after storage already finalized the object. The API must check session/object state before calling `complete` again. Cleanup jobs must also be idempotent.

## 10. File Inspection Before Publishing

Storage confirming upload completion does not mean the content is safe.

1. Size: compare actual size against quotas and business limits.
2. Checksum: verify integrity.
3. File signature: verify format from magic bytes, not solely the client-sent MIME type.
4. Malware scan: run an appropriate scanning service/engine.
5. Content validation: restrict archives, nested payloads, macros, or disallowed formats.
6. Data classification: assign data type, retention, and permissions.
7. Metadata sanitization: do not trust client-supplied filenames or metadata.

~~~mermaid
flowchart LR
    U["Client upload"] --> Q[("Quarantine storage")]
    Q --> V["Size / checksum / file type"]
    V --> SCAN["Malware / content scan"]
    SCAN -->|"Pass"| CLEAN[("Approved object")]
    SCAN -->|"Fail"| HOLD[("Rejected / isolated")]
    CLEAN --> DB[("Metadata = COMPLETE")]
~~~

Never serve public URLs for quarantined objects. If scanning is asynchronous, users should see `PROCESSING` or `QUARANTINED`; finished byte transfer does not mean the file is approved.

## 11. URL Security, CORS, and Tenant Isolation

**CORS is not authorization.** CORS is a browser mechanism controlling which origins may read responses on certain cross-origin requests. It does not block non-browser clients from calling storage endpoints.

Configure explicit allowed origins, required methods/headers, and expose only necessary headers such as ETag/checksum receipts. Never rely on CORS to enforce object read/write permissions; signed URLs/SAS, IAM, and bucket/container policies govern storage access.

The backend must verify:
- Does the user belong to the tenant owning the resource?
- Are they authorized to upload/download this file type in its current state?
- Is user/tenant quota available?
- Does the object belong to an authorized resource?
- Has the object passed scanning?
- Does the link carry the right action, key, method, and expiry?

Never accept an arbitrary object key from a client and sign it directly. The backend should map a system-issued `fileId`/`uploadId` to the object key after checking permissions.

Signed URLs can leak via application/proxy/CDN logs, browser history/referrers, analytics, error reports, screenshots, or support tickets. Reduce exposure by redacting signatures/tokens, enforcing HTTPS, avoiding unnecessary third-party analytics, setting proper `Referrer-Policy` headers, keeping expiries short, and logging object ID/action/issuer/expiry rather than the full URL.

In multi-tenant systems, object keys have distinct namespaces, yet prefixes are not the sole control. Authorization must verify tenants in both the API and storage policies; signed URLs must never reach another tenant's objects; audits must record principal/tenant context without exposing tokens. Encrypt at rest/in transit and manage keys by data classification.

## 12. Downloads, Caching, and CDNs

A CDN reduces latency and direct origin egress, yet misconfigured caching can serve content after application permissions change.

Check:
- Does the cache key include required tokens/cookies/headers?
- Does the edge check signed URL expiry on every request or only on cache misses?
- Does cache TTL exceed the permitted sharing duration?
- When an object is deleted or permissions are revoked, how long does purge/invalidation take?
- Can signed cookies or tokenized CDN URLs be used instead of raw storage URLs?
- Are range requests and partial caching supported?
- Does `Content-Disposition` set a safe download filename?

Public, immutable objects can be cached for long periods. Private objects require cache policies tied to authorization and sensitivity. Never set broad public `max-age` headers on private user content solely to speed up downloads.

## 13. Quotas, Limits, and Abuse Prevention

Uploads can be abused to exhaust storage, request budgets, bandwidth, or scanning capacity. Enforce per-file-type size limits, per-user and per-tenant storage/object quotas, concurrent session caps, parallel part limits, session creation rate limits, session/URL TTLs, allowed file types, download rate limits, and URL issuance caps.

Check quotas before issuing sessions and reconcile upon completion. If you only deduct quota on session creation, abandoned uploads lock up capacity; if you only count after completion, concurrent sessions can exceed quota. Use expiring quota reservations/holds or atomic accounting to prevent races.

## 14. Observability and Incident Response

Do not just log "upload failed." Track by `uploadId`/correlation ID without logging signed URLs or sensitive bytes.

| Metric | Meaning | Detects |
|---|---|---|
| Upload initiation rate | Session creation rate | Spikes/abuse |
| Active upload sessions | Open sessions | Orphaned sessions |
| Upload completion rate | Completion ratio | Network, quota, or client failures |
| Bytes uploaded / throughput | Volume and transfer speed | Bottlenecks |
| Part retry count | Retried parts | Unstable networks |
| Checksum mismatch count | Digest mismatches | Transmission/payload corruption |
| Session age / expired count | Session age and expirations | Abandoned uploads |
| Incomplete multipart bytes | Temporary part waste | Cost leakage |
| Malware scan latency/failure | Inspection pipeline delay | Scanning bottlenecks |
| Signed URL issuance/denial | Issued vs. rejected links | Permission/quota anomalies |
| Download range/egress | Downloaded bytes and repeat fetches | Cost/performance issues |

Upload investigation procedure:
1. Identify user/tenant, `uploadId`, and timestamp.
2. Inspect session record, object key, and storage upload ID.
3. Query storage for acknowledged parts/offsets.
4. Check provider error codes, request IDs, and redacted network/browser logs.
5. Verify checksums, sizes, and completion conditions.
6. Verify quotas, IAM/SAS, signature expiry, CORS, and DNS.
7. Resume valid parts; retry transient part failures with backoff.
8. If the session is unrecoverable, abort/expire it and create a new session idempotently.
9. Check whether the object already completed before retrying `complete`.
10. Record root cause, re-transmitted bytes, and cost impact.

For 403 download errors, trace user auth → file/tenant permissions → object state → expiry/method → signature/headers → IAM/storage policy → CDN/cache → DNS/network. Never blindly extend expiries before identifying the root cause.

## 15. Recovery, Versioning, and Object Lifecycle

Object storage may support versioning, replication, retention locks, and lifecycle rules. These aid recovery while increasing storage consumption and governance needs.

Determine:
- Can objects be overwritten or does each upload create a new version?
- Are prior versions kept for rollback/auditing?
- Do delete markers differ from physical deletion?
- Do compliance retention rules block deletion?
- Which object versions and metadata does replication copy?
- Do backups/restores preserve ACLs, tags, encryption key references, and ownership?
- Is cleanup of incomplete multipart uploads configured separately?

Signed URLs may target an object key or a specific version depending on the provider. If a key is overwritten, an older link might return newer content under provider semantics; consider immutable/versioned keys for critical data.

## 16. Well-Architected Trade-Offs

| Aspect | Benefit | Risk / cost | Evidence |
|---|---|---|---|
| **Reliability** | Multipart/resume, checksums, per-part retries | Broken sessions, complete timeouts, lost parts, or expired URLs | Resume tests, checksums, recovery drills |
| **Security** | Narrowly scoped signed URLs, private storage, quarantine | Leaked URLs, overwrites, malicious files | IAM reviews, redaction, malware scans, negative tests |
| **Performance** | Direct upload, streaming, parallel parts, and CDN | High connection counts, poor chunk sizing, throttling | Throughput, p95 completion, retry rates |
| **Cost** | Avoid unnecessary byte proxying; purge incomplete uploads | Egress, CDN, requests, scanning, and version storage | Storage inventory, abandoned bytes, cost/GB |
| **Operations** | Session state, owners, alerts, and runbooks | Orphaned sessions, hard post-timeout reconciliation | Session dashboards, request IDs, runbook drills |
| **Sustainability** | Per-part retries avoid re-sending whole files; lifecycle purges temp data | Storing redundant versions and excessive scanning | Object age, retention, lifecycle metrics |

Trade-offs:
- Proxy uploads centralize control at the cost of backend compute/network.
- Direct uploads scale well but require managing URL capabilities and object lifecycles.
- Smaller chunks shrink retry payloads while raising request/metadata overhead.
- More parallel parts boost throughput but can trigger congestion.
- Short expiries limit leak exposure while risking failures on slow networks.
- Versioning aids recovery while raising storage costs.
- Pre-publish scanning improves safety while adding latency.

No single chunk size, expiry, or retention fits every system. Measure against actual file sizes, client networks, regions, SDKs, and SLOs.

## 17. Design Process and ADR

Reference process:
1. Determine file sizes, concurrent uploads, client networks, data types, and SLAs.
2. Choose proxy streaming vs. direct-to-object-storage.
3. Pick multipart/resumable protocols per SDK/provider.
4. Design buckets/containers, keys, metadata, versioning, and quarantine.
5. Design authorization, signed URLs/SAS, expiry, methods, keys, tenants, and quotas.
6. Design session persistence, part reconciliation, idempotency, retries, and aborts.
7. Design checksums, file validation, and malware scanning.
8. Design downloads, Range support, CDN/caching, and revocation options.
9. Design cleanup, retention, versioning, and deletion.
10. Design metrics, log redaction, alerts, runbooks, and ownership.
11. Test large files, dropped connections, expired URLs, quotas, duplicate `complete` calls, and cross-tenant access.

### Illustrative ADR — Direct Multipart Upload

> **Context:** Users upload profiles up to 5 GB. The backend currently proxies bytes and times out under heavy load.
>
> **Option A:** Keep proxy streaming and raise timeouts/compute. Easy to keep traffic passing through the backend, but expensive in compute/network and hard to scale concurrently.
>
> **Option B:** Issue time-limited multipart upload access to object storage. The backend holds metadata/sessions and verifies the object on completion. Clients retry individual parts.
>
> **Illustrative decision:** Choose Option B because the workload is primarily byte transfer and storage supports multipart. The backend acts as the control plane for permissions, quotas, sessions, and state.
>
> **Trade-offs:** Must manage sessions, bearer URL capabilities, incomplete part cleanup, CORS, checksums, and quarantine.
>
> **Validation:** Upload across dropped networks, resume after page reload, send `complete` twice, supply bad checksums, expire URLs, attempt cross-user URL use, and exceed quota.
>
> **Revisit conditions:** If inline content transformation is required or compliance mandates every byte pass through a gateway, evaluate a proxy/processing pipeline.

## 18. Practice Exercise: Profile Video Upload Platform

A booking platform lets property owners upload videos up to 3 GB. Users access it over unstable mobile networks. A Java backend currently receives files via REST and forwards them to object storage. Requests frequently time out after 20 minutes and users have to start over. Download links are stored in the database and live indefinitely. New files become visible immediately without scanning.

**Requirements:**
1. Identify bottlenecks and risks in the current proxy upload flow.
2. Propose direct multipart or resumable uploads.
3. Design APIs for creating sessions, issuing URLs, listing parts/status, completing, and aborting.
4. Describe resuming after a browser restart without trusting local progress.
5. Define checksums, file validation, and quarantine state.
6. Replace long-lived download links with time-limited access; explain how to support immediate revocation.
7. Design quotas, expirations, and cleanup of abandoned sessions.
8. Build metrics, alerts, and tests for network drops, expired URLs, duplicate `complete` calls, checksum mismatches, and cross-tenant access.

### Solution Direction

- Remove the backend from the byte data path; the API creates sessions and issues narrowly scoped URLs to server-chosen object keys.
- Use multipart/resumable APIs; persist upload IDs, part numbers, checksums, and expiries.
- After a browser restart, call the API to retrieve authoritative progress from storage and resume only unconfirmed parts.
- Make `complete` idempotent; if a response times out, query object/session status before retrying.
- Upload into quarantine; validate size, checksum, file signature, and malware before transitioning to downloadable status.
- Have the backend authenticate users and check file permissions before issuing short-lived signed download URLs. If immediate revocation is needed, consider a proxy/authorized gateway or revocable tokenized CDN; raw signed URLs cannot necessarily be revoked individually.
- Cap active sessions, held quota, concurrency, part sizes, and expiries; configure lifecycle rules to abort incomplete uploads.
- Monitor completion rates, bytes transferred, part retries, oldest session age, incomplete bytes, checksum mismatches, scan latency, and URL denials.
- Test cases where storage completed the object even though the client missed the response; prevent duplicate objects or double-triggered workflows.

### Self-Check Questions

1. Why does direct upload reduce backend load without eliminating backend authorization responsibilities?
2. How does multipart upload differ from application-level resumable upload?
3. Why must you reconcile against server/storage progress after a reconnect?
4. Is an ETag always the MD5 of the complete object?
5. Is a signed URL a one-time URL? When can it be revoked?
6. Why is CORS not authorization?
7. Why must objects be quarantined before publishing?
8. How do Range requests enable resumable downloads, and why are validators needed when objects change?
9. What costs do incomplete multipart uploads incur, and at which layer should cleanup live?
10. If `complete` times out after storage already created the object, what should client and server do?

A reliable large-file transfer architecture combines **a resumable upload protocol, integrity verification, time-bounded read/write permissions, and explicit object lifecycle management**. Multipart/resumable transfers enable per-part recovery; signed URLs offload the backend while remaining capabilities that must be protected; checksums, quarantine, idempotency, cleanup, and observability turn byte transfers into a secure, operable storage workflow.
