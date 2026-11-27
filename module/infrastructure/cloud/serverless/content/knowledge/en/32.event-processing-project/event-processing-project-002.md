# Building the File Intake and Event Emission Step

The file intake step is the boundary between client-submitted data and data the system can safely process. A web or mobile application may send images, videos, PDFs, spreadsheets, or attachments. The backend must determine who is allowed to upload, where to upload, which sizes and formats are allowed, whether the file is complete, which object version should be processed, and which event is emitted for downstream workers.

In a serverless architecture, an API function typically creates an upload session and grants time-limited upload permissions. The client transfers bytes directly to object storage to avoid holding long-lived requests or routing binaries through API Gateway. Storage emits a notification when an object is created; a queue receives the notification and triggers a Java function. The function verifies the object against the upload session, records state, and emits a stable business event such as **file.received**. Workers processing images, videos, or documents can subscribe to this event in subsequent steps.

Crucially, a notification from storage only indicates that an object operation occurred. It does not prove that the file belongs to a valid upload session, matches the right tenant, has the right size, matches the checksum, or is safe. The intake step must verify those conditions before publishing an event downstream.

In the **CLOUD_SERVERLESS** module, learners build Java functions triggered by HTTP, messages, or events while handling state, access control, retries, idempotency, cold starts, scaling, and cost. This lesson guides you through building the file intake and event emission step using upload sessions, object storage, a queue, Java functions, and a transactional outbox.

## 1. Goals and Scope of the Intake Step

The intake step is responsible for transitioning an upload from a client-initiated state to a backend-verified object reference ready for processing.

Goals:

- Authenticate the principal and verify upload authorization.
- Enforce quotas by user, tenant, and file type.
- Generate an unpredictable object key bound to the upload session.
- Grant short-lived upload permissions scoped to the exact object and method.
- Detect upload completion via storage events or API completion.
- Verify the actual object using metadata retrieved from storage.
- Detect duplicate uploads, overwritten objects, or late-arriving events.
- Persist durable state and emit an event with a stable schema.
- Ensure retries do not create duplicate upload records or business events.
- Isolate unverified files; never publish download URLs prematurely.

This lesson stops at emitting the **file.received** event after the object passes basic intake verification. Deep malware scanning, OCR, thumbnails, transcoding, and content processing are implemented by downstream consumers. Even so, the object should remain in quarantine or private storage until the security pipeline finishes.

## 2. Overall Architecture

~~~mermaid
flowchart TD
    C[Web / Mobile client] -->|POST create upload| API[API Gateway]
    API --> F1[Java Upload API Function]
    F1 --> IDP[Identity / Authorization]
    F1 --> DB[(Upload session database)]
    F1 -->|Presigned upload URL| C
    C -->|Direct PUT / multipart| S[(Private quarantine object storage)]
    S -->|Object created notification| Q[Ingestion queue]
    Q --> F2[Java Intake Function]
    F2 -->|HEAD / GET exact version| S
    F2 --> DB
    F2 --> OB[(Transactional outbox)]
    OB --> P[Outbox publisher]
    P --> BUS[Event bus / downstream queue]
    BUS --> W[Processing workers]
    F2 --> DLQ[Dead-letter queue]
    Q -. failure after retries .-> DLQ
    F1 --> OBS[Logs / metrics / traces]
    F2 --> OBS
    P --> OBS
~~~

There are three main flows:

1. **Control flow:** the client calls the API to create an upload session; the backend authenticates and grants upload permission.
2. **Data flow:** the client uploads bytes directly into private object storage.
3. **Event flow:** storage notifications are placed into a queue; the intake function verifies the object and emits the business event.

The queue absorbs bursts and decouples upload rates from intake processing rates. The transactional outbox keeps database updates synchronized with the intent to publish events. Downstream workers do not need to parse provider-specific notifications; they receive a unified event contract.

Services in the diagram can be equivalent managed services from a cloud provider. Notification, queue, retry, versioning, and object lock configurations vary by platform; verify the semantics of the actual product in use.

## 3. Components and Responsibility Boundaries

| Component | Responsibility | Should Not Do |
|---|---|---|
| Web/mobile client | Request upload session, transfer bytes, track status | Decide the object key or accepted state |
| API Gateway | HTTPS, routing, auth integration, throttling, request limits | Buffer large binary uploads through functions when direct upload exists |
| Upload API function | Check user/quota, create session, grant permission | Trust client-declared MIME type or file size |
| Upload session database | Store owner, tenant, key, expiry, and state | Store presigned URLs as long-lived credentials |
| Object storage | Store bytes and emit notifications | Make objects public before intake completes |
| Ingestion queue | Buffer notifications, retry, and DLQ | Assume at-most-once / exactly-once message delivery |
| Intake function | Verify object, claim event, update state | Trust all metadata inside the notification |
| Outbox publisher | Publish canonical events and retry | Mark sent before publish succeeds |
| Event bus/downstream queue | Distribute events to workers | Act as the authoritative source of upload session data |
| Observability | Track end-to-end flow and audit | Log presigned URLs or secrets |

Separate the upload API and intake consumer because they have different triggers, timeouts, and scaling profiles. The API needs low latency; the intake consumer scales by queue concurrency and needs object read permissions. Both can share a domain service or repository contract where appropriate.

## 4. States of an Upload Session

Do not use a single `uploaded` boolean to describe the entire lifecycle. A clear state machine helps determine which requests are valid and which events should be emitted.

| State | Meaning | Valid Transitions |
|---|---|---|
| CREATED | Session created and upload permission granted; object not yet confirmed | UPLOADING, OBJECT_REPORTED, EXPIRED, CANCELLED |
| UPLOADING | Client is sending bytes | OBJECT_REPORTED, EXPIRED, CANCELLED |
| OBJECT_REPORTED | Storage notification or completion hint arrived | VERIFYING |
| VERIFYING | Backend is checking object/version | ACCEPTED, REJECTED, RETRY_PENDING |
| RETRY_PENDING | Transient error, awaiting retry | VERIFYING, FAILED |
| ACCEPTED | Object verified and event recorded in outbox | Terminal for intake |
| REJECTED | Object violated policy | Terminal for intake |
| EXPIRED | Session expired before completion | Terminal |
| CANCELLED | Owner or system cancelled session | Terminal |
| FAILED | Unrecoverable error after retries | Terminal, requires investigation |

With a single PUT, the system may not receive an upload-started signal; the session can transition directly from `CREATED` to `OBJECT_REPORTED` when the storage event arrives. The `UPLOADING` state is useful when the backend manages multipart initiation, receives progress/completion hints, or has an explicit start signal. Do not require an extra request solely to change state if it adds no guarantee.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> UPLOADING
    CREATED --> OBJECT_REPORTED
    UPLOADING --> OBJECT_REPORTED
    OBJECT_REPORTED --> VERIFYING
    VERIFYING --> ACCEPTED
    VERIFYING --> REJECTED
    VERIFYING --> RETRY_PENDING
    RETRY_PENDING --> VERIFYING
    CREATED --> EXPIRED
    UPLOADING --> EXPIRED
    CREATED --> CANCELLED
    UPLOADING --> CANCELLED
    RETRY_PENDING --> FAILED
~~~

The `ACCEPTED` state should have a concrete meaning: the object version has been verified, required metadata has been saved, and the canonical event has been durably written to the outbox in the same transaction. The publisher might not have pushed the event to the bus at that exact instant; the outbox owns retrying until publish confirmation.

If you need to distinguish verified from published, add separate states like `EVENT_PENDING`/`EVENT_PUBLISHED` or keep the upload state as `ACCEPTED` and track outbox delivery independently. Avoid making upload state depend on transient event bus availability.

## 5. Upload Session Design

An upload session is a backend record representing permission to upload a specific object. A session should include fields such as:

| Field | Purpose |
|---|---|
| upload_id | Server-generated unique ID |
| tenant_id | Tenant owning the upload |
| owner_id | Principal that created the session |
| object_bucket/container | Target storage location |
| object_key | Server-generated random key |
| expected_size | Expected size or maximum limit |
| allowed_media_types | Allowed content types |
| expected_checksum | Expected client checksum if used |
| status | Lifecycle state |
| expires_at | Session expiration timestamp |
| object_version_id | Specific verified version |
| actual_size | Size returned by storage |
| actual_checksum | Checksum confirmed by storage |
| detected_media_type | Content type detected from bytes |
| idempotency_key | Prevents duplicate session creation |
| correlation_id | Links requests, events, and traces |
| created_at / updated_at | Lifecycle audit |

Not every field must live in a single table. Session, object metadata, and outbox can be split by access pattern. However, a unique constraint is required so an upload session is not created twice when a client retries a request.

### Object Keys

The server generates keys with a namespaced structure, for example:

~~~text
quarantine/{tenant-id}/{upload-id}/{random-object-id}
~~~

Never use the original filename as the key. Filenames can contain special characters, fake paths, personal information, or duplicate names. Store a sanitized original filename as display metadata if the business needs it; the key must be server-controlled.

Use unpredictable random keys and verify ownership via the session database. Never treat key unpredictability as authorization; IAM and bucket/container policies must still restrict access.

## 6. Creating an Upload Session via HTTP API

The client calls the API to create a session. The backend must:

1. Verify the access token/session.
2. Identify the tenant from the authenticated identity.
3. Verify the user has permission to upload to the target resource.
4. Check quotas, open uploads, and remaining storage capacity.
5. Validate expected file size and declared content type.
6. Generate an upload ID and random object key.
7. Record the session in `CREATED` state.
8. Generate short-lived upload permissions scoped to the exact object/method.
9. Return the upload ID, URL, and expiry to the client.

Example request:

~~~http
POST /v1/uploads
Authorization: Bearer <access-token>
Idempotency-Key: 0d6f4a7c-...
Content-Type: application/json

{
  "fileName": "inspection-photo.jpg",
  "contentType": "image/jpeg",
  "sizeBytes": 2457600,
  "checksumSha256": "base64-checksum"
}
~~~

Example response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "uploadId": "upl-9001",
  "uploadUrl": "https://storage.example/signed-request",
  "method": "PUT",
  "expiresAt": "2026-11-17T10:25:30Z",
  "requiredHeaders": {
    "Content-Type": "image/jpeg"
  },
  "status": "CREATED"
}
~~~

The URL in the example only illustrates structure. A presigned URL is a bearer capability; anyone possessing the URL and matching headers can exercise that permission while it is valid. Never write real URLs to logs, analytics, or error trackers. Responses containing capabilities need `Cache-Control: no-store`.

### Idempotency When Creating Sessions

A mobile client may time out after the backend created the session but before receiving the response. On retry with the same `Idempotency-Key`, the backend should return the same `uploadId`/session and a refreshed capability if policy allows, or return the current session state. Never create multiple sessions and consume extra quota for the same user action.

Scope keys by principal, tenant, and operation. If the same key is sent with a different request body, return a conflict instead of silently reusing the old session.

## 7. Issuing Presigned URLs or Secure Upload Tokens

A presigned URL typically grants permission to perform a single storage operation within a bounded window. Restrict:

- Specific bucket/container and object key.
- Specific HTTP method or operation.
- Short expiration aligned with upload UX.
- `Content-Type` or checksum headers if the provider supports signing constraints.
- Maximum size if the upload policy mechanism supports it.
- Disallow listing buckets, reading objects, or deleting objects.
- Disallow writing to processed/public areas.
- Disallow clients from choosing arbitrary server-side encryption keys.

Some providers support presigned POST policies with `content-length-range` conditions; presigned PUT has different semantics. Do not assume every signed URL type enforces size in the same way. The backend must still check actual object size after upload.

If a URL expires mid-upload, the client must request a fresh URL for the same session per policy. A refreshed URL should not generate a new object key or alter the owner. If the session has expired or been cancelled, deny renewal.

## 8. Direct Uploads and CORS

For browsers, the storage bucket/container needs a CORS policy allowing only the application's origins, required methods, and required headers. CORS does not protect storage from mobile clients or non-browser scripts; access control is still enforced by signatures/IAM.

CORS configuration should be minimal:

- Allow specific origins for production/staging.
- Allow only required methods (`PUT`/`POST`/`HEAD`).
- Allow only necessary request headers such as `Content-Type`/checksum.
- Expose only response headers the client truly needs, such as `ETag` if the flow uses it.
- Set a reasonable `max-age` for preflight caching.
- Do not combine wildcard origins with credentials inappropriately.

Never allow all origins just to avoid preflight errors. Separate CORS configs per environment and test with a real browser.

## 9. Simple, Multipart, and Resumable Uploads

A single PUT fits small files on stable networks. For videos or large files, multipart/resumable uploads split data into parts and resume after mobile network drops.

| Criterion | Single PUT | Multipart/resumable |
|---|---|---|
| Request count | Few | Multiple parts plus completion step |
| Retry | Typically re-uploads entire file | Retries individual parts |
| Client complexity | Low | Higher |
| Large files | Bounded by provider/API limits | Better suited |
| State | Single object completion | Upload ID, part list, and completion |
| Cleanup | Delete incomplete object | Abort multipart and clean orphaned parts |

The backend needs to store the multipart upload ID, part constraints, expiry, and state. Clients may only upload authorized parts. Multipart completion must be authenticated and idempotent. Configure lifecycle rules to abort incomplete multipart uploads after an appropriate deadline.

Never treat a multipart ETag as the MD5 of the entire file. Use checksum APIs and semantics documented by the provider.

## 10. Client Completion Signals and Storage Notifications

Two signals are commonly used:

- The client calls `POST /v1/uploads/{id}/complete` after uploading.
- Object storage emits a notification when the object is created or multipart upload completes.

A client callback is helpful for UX, but should never be the sole proof that an object exists. Clients can lie, apps can crash before calling back, or the callback can arrive before storage metadata is consistent under provider semantics.

Storage events are independent signals from the data plane. However, events can duplicate, arrive late, or arrive out of order. Therefore, both signals should feed the session into the same idempotent verification flow. Either signal simply wakes intake; the backend still reads object metadata directly from storage.

### Never Process Incomplete Uploads

For multipart uploads, notifications must correspond to the completed object, not individual parts. Check the event type and upload state. On object storage with eventual consistency or specific notification semantics, issue a versioned `HEAD`/`GET` API call to confirm the object is readable before accepting.

## 11. Configuring Storage Notifications and Ingestion Queues

Typical path:

1. A bucket/container holding only quarantine objects emits `ObjectCreated` events.
2. Rules match only the required prefix and event types.
3. Notifications are routed to a queue or event bus.
4. The queue triggers the Java intake function.
5. The queue provides retry visibility/lease and a DLQ.
6. Consumers process batches and return partial failures if the platform supports them.

Use prefix/suffix filters to avoid event loops. If worker outputs reside in the same bucket and prefix, they can re-trigger intake. Separate quarantine prefixes/buckets from processed prefixes/buckets.

### Why Use a Queue?

Queues absorb upload bursts, decouple storage availability from consumers, and allow concurrency tuning. If functions are throttled or the database is slow, messages wait in the queue instead of being dropped. Queues also support retries and DLQs for investigating poison events.

Choose queue types based on ordering and throughput. Standard queues can deliver duplicates and do not guarantee strict ordering. FIFO/ordered queues have different semantics and distinct throughput limits. Intake should be idempotent regardless of whether the queue supports ordering.

## 12. Normalizing Notifications into Object References

Provider notifications have differing envelopes. The intake adapter should parse raw events into an internal structure:

~~~java
public record StorageObjectCreated(
        String providerEventId,
        String bucket,
        String key,
        String versionId,
        String eventType,
        Instant occurredAt,
        String sequencer,
        String correlationHint) {
}
~~~

The adapter's only job is parsing and normalizing. It does not decide whether the object is valid or whether the user is authorized for it. Those decisions require the session database and metadata read directly from storage.

Preserve provider event IDs, request IDs, or sequencers when available to investigate duplicates and ordering. Do not assume every provider supplies `versionId` or `sequencer`. When fields are missing, use a deduplication strategy based on upload ID, key, event type, and appropriate object metadata.

## 13. Never Trust Notification Payloads

Storage notifications may include bucket, key, version, size, ETag, and event time. These fields are useful for routing but should not be treated as sufficient proof.

The intake function must:

1. Verify the event source and event type are on the allowlist.
2. Decode the object key using the provider's encoding rules.
3. Extract the upload ID from the key or server-side metadata.
4. Load the upload session by upload ID.
5. Verify bucket/key match the session exactly.
6. Check tenant/owner and session state.
7. Read `HEAD` metadata for the exact object version if available.
8. Verify size, checksum, encryption, and required metadata.
9. Verify the session is not expired/cancelled per policy.
10. Only then accept the object.

Never allow a client to submit an arbitrary bucket/key and ask the function to `HEAD` or `GET` it. That can create a confused deputy or cross-tenant object access. Object references must match a server-created session.

## 14. Verifying Object Metadata

Use `HEAD` or an equivalent API to fetch metadata from storage. Verify:

- Correct bucket/container.
- Key matches the session.
- Version ID matches the event or session.
- Object exists and is complete.
- Actual size does not exceed quota or limits.
- Checksum if the provider stores a trusted checksum.
- Appropriate encryption settings.
- Correct upload ID/session marker metadata if attached.
- Declared content type is only a hint; bytes must be sniffed in validation.
- Object was not deleted or replaced between event emission and consumer read.

### ETag and Checksums

An ETag is a storage entity tag, not always a cryptographic checksum of the bytes. Multipart uploads, server-side encryption, and differing implementations can cause ETags not to equal the whole-object MD5.

Prefer checksum algorithms natively supported by storage and explicitly passed/verified. If full-content verification is needed, a worker can stream the object and compute SHA-256. Weigh the cost of re-reading the whole file; never load an entire file into the intake function's memory.

## 15. Object Versioning and Overwrites

A presigned PUT may be used multiple times before expiration. If the same key is overwritten, the current object may differ from the object that emitted the first event. If a consumer only runs `HEAD` on the current key, an older event might accidentally process newer bytes.

Mitigations:

- Enable object versioning if supported and appropriate for the provider.
- Use dedicated keys; never reuse keys across uploads.
- Store the specific `versionId` in the session.
- Read the exact version referenced by the event.
- Use conditional writes or write-once policies if supported by the service.
- Never treat an ETag as a version ID.

On storage without versioning, design single-use object keys and block overwrites via policy/credential scope if possible. If write-once cannot be guaranteed, implement a locked completion protocol with metadata verification and explicitly document race-condition boundaries.

## 16. Content Inspection and Quarantine

The intake step can check basic metadata and move the object into a scan-pending state. Files must still be treated as untrusted until downstream processors finish.

Early checks:

- Actual size.
- Extension and declared content type.
- Magic bytes/content signature if partial streaming is possible.
- Checksum.
- Archive/decompression limits in a dedicated processor.
- Empty or truncated files.
- Metadata containing sensitive information.
- Tenant quotas and concurrent uploads.

Never decompress archives or run complex parsers in the API intake. Use a sandboxed worker with CPU, memory, time, and network egress limits for those steps.

## 17. Canonical Event Contract

Downstream consumers should not depend directly on each storage provider's notification envelope. The intake function emits an internal event with a stable schema.

Example:

~~~json
{
  "eventId": "evt-82c1",
  "eventType": "file.received",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T10:15:30Z",
  "publishedAt": "2026-11-17T10:15:32Z",
  "source": "serverless.file-intake",
  "tenantId": "tenant-42",
  "uploadId": "upl-9001",
  "ownerId": "user-17",
  "object": {
    "bucket": "private-quarantine",
    "key": "quarantine/tenant-42/upl-9001/obj-random",
    "versionId": "v-17",
    "sizeBytes": 2457600,
    "checksumAlgorithm": "SHA256",
    "checksum": "base64-value"
  },
  "declaredContentType": "image/jpeg",
  "correlationId": "corr-31",
  "traceId": "trace-71"
}
~~~

A canonical event should contain:

- A unique `eventId` stable across publish retries.
- Event type and schema version.
- Timestamp when the object was received and timestamp when the event was published.
- Source/service emitting the event.
- Tenant, upload, and owner references.
- Object reference including bucket/key/version.
- Verified size and checksum.
- Correlation/trace references.
- No file bytes, presigned URLs, access tokens, or secrets.

Include the original filename in the event only if downstream truly needs it and privacy policies permit. Typically, display metadata can be fetched from the upload record via `uploadId`.

### Event Versioning

Adding optional fields is usually more backward-compatible than changing the meaning of existing fields. When a breaking change is needed, increment `schemaVersion` or the `eventType` version, deploy supporting consumers first, and only then emit the new version. Store schemas in a registry or reviewed repository when multiple producers/consumers exist.

## 18. Reliable Event Emission with a Transactional Outbox

A common mistake is updating the upload session to `ACCEPTED` and then calling the event bus. If the database commit succeeds but publishing fails, the upload is accepted while downstream remains unaware. If publishing succeeds and the database rolls back, downstream receives an event for uncommitted state.

A transactional outbox closes this gap when the session database supports transactions:

1. Claim the event/notification in the inbox.
2. Verify the object and session.
3. Update the upload session to `ACCEPTED`.
4. Insert the canonical `file.received` event into the outbox.
5. Commit both in the same transaction.
6. The publisher reads unsent outbox rows.
7. Publish the event with a stable `eventId`.
8. After broker confirmation, mark the outbox record as sent.

~~~mermaid
sequenceDiagram
    participant Q as Ingestion Queue
    participant I as Intake Function
    participant D as Database
    participant O as Outbox Publisher
    participant B as Event Bus

    Q->>I: Storage object-created event
    I->>D: Claim inbox + load upload session
    I->>I: HEAD exact object version / validate
    I->>D: Update session + insert outbox
    D-->>I: Commit
    I-->>Q: Acknowledge source message
    O->>D: Read pending outbox record
    O->>B: Publish file.received
    B-->>O: Accepted / publish result
    O->>D: Mark outbox sent
~~~

The outbox publisher can crash after the broker accepts the event but before marking it sent. On restart, the event may be published twice. Hence `eventId` must be stable and downstream consumers must be idempotent.

If your database and broker offer a native transactional integration, you may use it, provided you understand its actual guarantees. Never assume calling a publish API inside the same Java method forms a distributed transaction.

## 19. Inbox and Idempotency in the Intake Consumer

Queue/storage notifications typically have at-least-once delivery or retry semantics that can generate duplicates. The intake consumer needs a durable inbox/deduplication record.

Possible dedupe keys:

- Provider event ID if guaranteed stable across redeliveries.
- Bucket + key + `versionId` + event type.
- Upload ID + object version + event type.
- Sequencer or generation number if provided with suitable semantics.

Do not use bucket + key alone if objects can be overwritten. Do not use ETag alone because identical content can yield identical ETags across distinct uploads.

The inbox record has a unique constraint. Within a single transaction, the consumer claims the record, updates the session, and writes the outbox entry. If the event is already completed, acknowledge the duplicate without producing a second business event. If another worker is processing the event, use a lease/conditional update to prevent two functions from claiming it simultaneously.

### Conditional State Transitions

Only allow transitions if the current status is valid. For example, `ACCEPTED` must never revert to `VERIFYING` because an old notification arrived late. Use compare-and-set or optimistic versioning to guard updates.

## 20. Java Domain Model for Upload Intake

A minimal domain model:

~~~java
public enum UploadStatus {
    CREATED,
    UPLOADING,
    OBJECT_REPORTED,
    VERIFYING,
    RETRY_PENDING,
    ACCEPTED,
    REJECTED,
    EXPIRED,
    CANCELLED,
    FAILED
}

public record UploadSession(
        String uploadId,
        String tenantId,
        String ownerId,
        String bucket,
        String objectKey,
        long maxSizeBytes,
        Instant expiresAt,
        UploadStatus status,
        String objectVersionId,
        String checksumSha256) {
}

public record VerifiedObject(
        String bucket,
        String key,
        String versionId,
        long sizeBytes,
        String checksumSha256,
        String declaredContentType) {
}
~~~

These records only describe data. Repositories must enforce tenant scoping and optimistic/conditional updates. Never expose internal entities directly in API responses.

## 21. Java Intake Handler

The handler receives messages from the queue, normalizes provider events, and delegates to the service. Queue adapters and storage SDKs are provider-dependent; business logic should not be coupled to notification JSON envelopes.

~~~java
public final class StorageEventHandler {
    private final StorageEventMapper mapper;
    private final FileIntakeService intakeService;

    public BatchResult handle(QueueBatch batch) {
        List<String> failedMessageIds = new ArrayList<>();

        for (QueueMessage message : batch.messages()) {
            try {
                StorageObjectCreated event =
                        mapper.toStorageObjectCreated(message.body());

                intakeService.accept(event);
            } catch (RetryableIntakeException ex) {
                failedMessageIds.add(message.messageId());
            } catch (PermanentIntakeException ex) {
                // Record the rejection or route to a quarantine/DLQ path.
                // Do not retry a permanently invalid event forever.
                intakeService.recordPermanentFailure(message, ex);
            }
        }

        return BatchResult.partialFailures(failedMessageIds);
    }
}
~~~

This is pseudocode. For queues supporting partial batch responses, return only failed message IDs so only those records are retried. If the adapter does not support partial failures, batch processing must ensure successful records do not incur repeated side effects when the whole batch is redelivered. Permanent errors should be recorded and acknowledged or routed to a DLQ per policy.

Never catch every exception and return success; that can drop events. Likewise, never infinitely retry configuration errors such as a missing bucket or revoked IAM permissions.

## 22. Java Verification and Outbox Service

The example below illustrates transaction boundaries. The storage `HEAD` call typically occurs outside the database transaction to avoid holding locks during slow network calls; afterward, the service opens a short transaction to claim and commit state/outbox. In real implementations, re-check the session version after reading the object to prevent races.

~~~java
public void accept(StorageObjectCreated event) {
    UploadSession session =
            uploadRepository.findByObjectReference(
                    event.bucket(), event.key());

    if (session == null) {
        throw new PermanentIntakeException("Unknown upload object");
    }

    if (!session.bucket().equals(event.bucket())
            || !session.objectKey().equals(event.key())) {
        throw new PermanentIntakeException("Object/session mismatch");
    }

    if (session.status() == UploadStatus.ACCEPTED) {
        if (Objects.equals(session.objectVersionId(), event.versionId())) {
            return;
        }
        throw new PermanentIntakeException(
                "Unexpected object version for accepted upload");
    }

    VerifiedObject object =
            storageVerifier.headExactVersion(
                    event.bucket(), event.key(), event.versionId());

    validateSize(session, object);
    validateVersion(event, object);
    validateExpectedChecksum(session, object);

    transaction(() -> {
        boolean claimed = inboxRepository.insertIfAbsent(
                dedupeKey(event, object));

        if (!claimed) {
            return;
        }

        UploadSession current =
                uploadRepository.findForUpdate(session.uploadId());

        requireAcceptableState(current);
        uploadRepository.markAccepted(
                current.uploadId(), object);

        FileReceivedEvent canonical =
                FileReceivedEvent.from(current, object);

        outboxRepository.insert(canonical.eventId(), canonical);
    });
}
~~~

This is pseudocode; the storage verifier must read the exact version if the provider supports versioning. If the event lacks a `versionId`, the adapter needs an explicit write-once/completion protocol. Never default to `HEAD` latest when the key could be overwritten between the event and processing.

If the inbox is claimed inside the transaction while object validation occurs before the transaction, duplicate events may run `HEAD` in parallel; the transaction's unique constraint ensures only one outbox record is created. If validation is expensive, claim with a lease beforehand and complete later, ensuring the lease has an expiry and crash recovery.

## 23. Completion API as a Complementary Signal

Some flows require the client to call a complete endpoint so the UX knows the upload finished. That endpoint should never take the client's word that the object uploaded successfully.

Flow:

1. Client calls `POST /v1/uploads/{uploadId}/complete`.
2. Backend verifies owner/tenant and session.
3. Backend runs `HEAD` on the object by key/version.
4. Check actual size/checksum and multipart completion.
5. Record the completion hint or invoke the same intake service.
6. If the storage notification arrives later, it becomes a valid duplicate.

If the object event arrives before the completion API, intake can still verify and accept. The completion API then returns the current state. Both trigger paths must share the same state machine and idempotency key to prevent emitting two `file.received` events.

Never emit an event solely because the client called complete. An event is emitted only after reading and verifying the object in storage.

## 24. Handling Out-of-Order or Late Events

Events may arrive after a session has expired, been cancelled, or after the object was deleted. A single upload key may emit multiple events due to overwrites or multipart retries.

Rules:

- Terminal sessions like `EXPIRED`/`CANCELLED` must never transition to `ACCEPTED`.
- An older version event must never overwrite a newer selected version.
- Already-processed duplicate events must be acknowledged.
- Events with no session or mismatched keys must be rejected and audited.
- Events arriving after the retention window need an explicit policy: reject, quarantine, or investigate.
- Events for deleted object versions must record a clear error state.

Do not delete sessions immediately on expiration. Retain tombstones/metadata long enough to recognize late events and prevent replay. Lifecycle cleanup can delete object bytes while keeping smaller metadata records per retention policy.

## 25. Retries, Visibility Timeouts, and DLQs

Retry policies must distinguish transient failures from permanent errors.

| Error Type | Behavior |
|---|---|
| Storage timeout/throttling | Retry with backoff |
| Database transient failure | Bounded transaction retry |
| Event bus unavailable | Outbox stays pending and retries |
| Object not immediately readable | Short retry per consistency/notification semantics |
| Unknown upload ID | Permanent reject or quarantine |
| Bucket/key mismatch | Security event; do not blind-retry |
| File exceeds size limit | `REJECTED`; do not retry |
| Checksum mismatch | `REJECTED` or request re-upload per policy |
| Configuration permission denied | Alert and retry after fix; avoid hot loops |

Visibility timeouts or message leases must be long enough for maximum processing time plus buffer. If a function can run longer than the visibility timeout, the message may be delivered to another consumer while the first is still running. Use heartbeats/lease extensions if supported, or shrink per-batch processing time.

The DLQ retains events that fail after max attempts. Set up alerts for DLQ ingress and oldest message age, a runbook to inspect root causes, and a controlled redrive process. Never bulk-redrive before fixing the underlying cause.

## 26. Security and IAM

Separate permissions by role:

- Upload API: create sessions and issue signed requests; does not need read access to all objects.
- Client signed URL: `PUT` only to a single object key within a specific window.
- Storage notification service: send events to the queue/event bus.
- Intake function: read metadata/bytes in quarantine, update sessions, and write to outbox.
- Outbox publisher: publish canonical events to the designated topic/bus.
- Downstream processor: read only the target object and write outputs to a separate prefix.
- Auditor/operator: read logs and status per granted permissions.

Additional controls:

- Private buckets/containers; block public access.
- Encryption at rest and TLS in transit.
- Least-privilege KMS key policies.
- Short signed URL TTLs; never log them.
- Network endpoints/private access where appropriate.
- Validate tenant/owner on the backend.
- Audit URL issuance, completion, rejections, and redrives.
- Avoid wildcard resources on functions when scoping by bucket/prefix is possible.

Never grant clients read access to quarantine objects. Downloads are granted only after pipeline processing and policy checks determine the object's state.

## 27. Quotas and Abuse Prevention

Uploads can incur significant storage, scanning, and compute costs. Enforce quotas before issuing signed URLs:

- Maximum file size by type.
- Total pending upload volume per tenant.
- Total stored volume.
- Concurrent upload sessions.
- Session creation requests per user/IP.
- Multipart part count limits.
- Expiration for incomplete sessions.
- Limit on URL re-issuance count.
- Processing admission control when downstream backlog is high.

Quotas must be enforced on the backend with transactions/conditional updates so concurrent requests cannot exceed limits. If using eventually consistent quota counters, decide whether slight overshoot is acceptable or strict reservation is required.

When a session is accepted, convert reserved quota into actual usage. When rejected, cancelled, or expired, release the reservation and clean up objects per policy. Avoid leaking quota permanently to orphaned sessions.

## 28. Observability and Auditing

Maintain a correlation ID from the session creation API through object notifications, intake, outbox, and downstream events.

Key metrics:

- Upload sessions created/completed/expired/rejected.
- Uploaded bytes by tenant/file type.
- Time from session creation to object event.
- Queue depth and oldest message age.
- Intake processing duration and retry count.
- Unknown object/session mismatches.
- Checksum/size validation failures.
- Duplicate notification count.
- Outbox pending count and oldest pending age.
- Publish success/failure.
- DLQ ingress.
- Cost per accepted upload.

Structured logs should include `uploadId`, a tenant-safe reference, object version, event ID, queue message ID, correlation ID, and function version. Do not log presigned URLs, tokens, raw file bytes, or sensitive filenames unnecessarily.

Audit events must record who created a session, who cancelled it, which policy rejected it, which objects were accepted/rejected, and which operator redrove the DLQ. Audit archives should have separate access permissions and appropriate retention.

## 29. Cost and Optimization

Intake costs may include:

- API Gateway requests and Upload API function invocations.
- Object storage `PUT`/`GET`/`HEAD` requests and quarantine storage volume.
- Storage notifications or event bus ingestion.
- Queue send/receive/delete operations and retention.
- Intake function duration/concurrency.
- Database writes for sessions, inbox, and outbox.
- KMS requests and network transfer.
- Logs, metrics, traces, and DLQ storage.
- Incomplete multipart parts and orphaned objects.

Optimizations:

- Upload bytes directly to storage rather than proxying through functions.
- Use `HEAD` metadata rather than downloading entire objects during intake.
- Use appropriate checksum/streaming verification.
- Batch queue messages when latency allows.
- Set lifecycle rules for expired/rejected objects and incomplete multipart uploads.
- Avoid logging large payloads.
- Clean up orphaned sessions/objects via scheduled cleanup.
- Cap concurrency according to database and downstream capacity.
- Track cost per accepted upload and cost per GB received.

Never skip verification or security boundaries just to save a request. If byte scanning is needed, account for that cost in the corresponding processor and read/stream only as many times as necessary.

## 30. Testing

### Unit Tests

- Generate object keys without using client filenames.
- Validate quotas, file sizes, and content type allowlists.
- Perform valid state transitions and reject invalid transitions.
- Generate canonical events with stable `eventId` values.
- Produce distinct dedupe keys for distinct object versions.
- Map provider notifications into internal events.
- Reject tenant, bucket, or key mismatches.

### Integration Tests

- Create a session and upload an object to test storage.
- Storage notification arrives in the queue.
- Intake function reads the exact object version.
- Database session transitions to `ACCEPTED`.
- Outbox record is created.
- Publisher emits the event and marks it sent.
- Duplicate notifications do not create a second business event.
- Late events after `EXPIRED`/`CANCELLED` are handled per policy.

### Failure Tests

| Scenario | Expected Outcome |
|---|---|
| Client times out after session creation | Retrying with same key returns same session |
| Signed URL expires | Controlled renewal or rejection based on session |
| Oversized upload | Not `ACCEPTED`; quota handled properly |
| Duplicate object event | Only one canonical event |
| Object key overwritten | Exact version processed or rejected |
| Storage `HEAD` timeout | Retried; no premature event emitted |
| DB commit failure | Queue message retries; no lost event |
| Event bus publish failure | Outbox remains pending |
| Publisher crashes after publish | Downstream deduplicates duplicate publish |
| Intake function crashes | Queue retries; state transitions stay safe |
| Unknown upload ID | Permanent reject/quarantine and audit |
| DLQ redrive | Only eligible events are reprocessed |

Test with dummy objects and non-sensitive data. Also test partial batch success/failure when the queue supports partial batch responses.

## 31. Step-by-Step Deployment

1. **Create quarantine storage:** private access, encryption, versioning if needed, and lifecycle rules.
2. **Create upload session database:** schema, unique keys, state, and quota reservations.
3. **Deploy Upload API:** auth, authorization, idempotency, and signed URLs.
4. **Configure CORS:** only necessary origins, methods, and headers.
5. **Configure storage notifications:** filter exact bucket/prefix/event types.
6. **Create ingestion queue:** retries, visibility timeout, retention, and DLQ.
7. **Deploy Java intake function:** parse events, verify objects, update state.
8. **Create inbox/outbox:** unique constraints, transactions, and publisher.
9. **Define canonical event:** schema version, event ID, and object reference.
10. **Connect downstream test consumer:** confirm events can be read and deduplicated.
11. **Set up dashboards/alerts:** queue age, outbox backlog, rejections, and DLQ.
12. **Run integration/failure tests:** duplicates, overwrites, timeouts, and publish outages.
13. **Production canary:** limit tenants/traffic and watch costs/errors.
14. **Scale gradually:** raise concurrency and quotas based on observed capacity.

### Pre-Traffic Checks

- Signed URLs do not grant `GET`/`DELETE`/list permissions.
- Quarantine is not public.
- Object keys are server-generated.
- Events contain no secrets or signed URLs.
- Functions do not trust client metadata.
- Outbox publisher has retries and idempotency.
- DLQ has alerts and a runbook.
- Lifecycle cleanup does not delete in-flight objects.
- IAM roles and KMS policies have been reviewed.
- Quotas cannot be bypassed by concurrent requests.

## 32. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Proxying full files through API functions | Higher latency, memory, and cost | Direct upload to object storage |
| Using filename as object key | Collisions, path manipulation, info leaks | Server-generated random key |
| Trusting client-sent MIME type | Format spoofing | Sniff content and validate |
| Trusting client complete callback | Fake events or wrong session state | Verify object directly in storage |
| Public bucket for easy client uploads | Object leaks and abuse | Private bucket + signed URL |
| No upload session | Unknown owner, quota, and expiry | Durable session record |
| Using overwritable keys | Old events may read new bytes | Versioning or write-once keys |
| Assuming ETag is always MD5 | Incorrect checksums | Use official checksum semantics |
| Treating storage events as exactly-once | Duplicate side effects | Inbox/idempotency |
| Publishing event after DB commit without outbox | Lost events when broker fails | Transactional outbox |
| Marking outbox sent before publish | Lost events | Mark sent after broker acknowledgement |
| Same prefix for quarantine and output | Event loops | Separate buckets/prefixes and filter |
| No DLQ | Poison events retry infinitely | Retry cap, DLQ, and runbook |
| `HEAD` latest instead of exact version | Wrong object version processed | `VersionId`/immutable keys |
| Not keeping session tombstones | Late events go unrecognized | Retain session metadata per policy |
| No quota reservation | Concurrent requests exceed quota | Atomic reservation/conditional update |
| Logging signed URLs | Leaks bearer capabilities | Redact and omit query strings |
| Cleaning up objects too early | Workers cannot read objects | Pipeline-state-aware lifecycle |

## 33. Production Checklist

- **Upload authorization:** users/tenants are authenticated and authorized to upload to the resource.
- **Session:** tracks `uploadId`, owner, tenant, object key, quota, expiry, and state.
- **Idempotency:** create-session and complete operations tolerate client retries.
- **Object key:** server-generated; never uses client filenames.
- **Signed URL:** scoped method/key, short TTL, no read/list/delete permissions.
- **Storage:** private, encrypted, versioning/write-once strategy, and appropriate lifecycle rules.
- **CORS:** origins/methods/headers restricted.
- **Notification:** filtered by exact event/prefix; queue buffer and retries configured.
- **Verification:** `HEAD` exact object/version; verify size, checksum, owner, and session.
- **Content:** declared MIME treated as a hint; scan/parse in a sandboxed worker.
- **State machine:** conditional transitions; terminal states never overwritten.
- **Inbox:** duplicate notifications produce no repeated side effects.
- **Outbox:** session `ACCEPTED` and canonical event intent committed in the same transaction.
- **Publisher:** retries, stable `eventId`, and publish acknowledgements.
- **Event contract:** schema version, object reference, tenant/upload ID, and correlation ID.
- **Security:** least-privilege IAM, KMS, no public access, and never log signed URLs.
- **Quota:** reservation, release, concurrent uploads, and cleanup controlled.
- **Reliability:** visibility timeout, partial batch failures, retry caps, and DLQ.
- **Observability:** upload-to-event latency, queue age, outbox backlog, rejections, and cost.
- **Testing:** duplicates, late events, overwrites, timeouts, publish outages, DLQ redrive, and security tests.
- **Operations:** dashboards, alerts, runbooks, replay, and lifecycle reviews have owners.

## 34. Conclusion

The file intake step must separate upload initiation permissions from object processing permissions. The backend creates an upload session, checks identity/quotas, and issues a scoped signed URL. The client transfers bytes directly into private quarantine storage. Storage notifications flow through a queue so the Java intake function can verify the actual object against the session, version, size, and checksum. Once verified, the function updates state and writes a canonical `file.received` event to a transactional outbox.

Storage notifications can duplicate, arrive late, or arrive out of order; client callbacks can time out or be spoofed. Intake must therefore use a state machine, inbox/idempotency, exact object versions, and conditional updates. An outbox guarantees the intent to emit an event is persisted in the same transaction as the `ACCEPTED` state; the publisher retries and downstream consumers deduplicate by `eventId`.

This design establishes a stable contract between upload and downstream processors. Images, videos, and documents can be processed independently without coupling to the upload API or provider notification envelopes. With quotas, security, lifecycle rules, observability, and failure tests built in from the start, the pipeline scales with load while preserving ownership, integrity, and traceability for every file.
