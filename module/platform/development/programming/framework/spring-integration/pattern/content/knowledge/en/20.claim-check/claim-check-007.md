# Handling large payloads via claim check

> **Chapter:** Claim check  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learn to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Practice Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation while testing and observing processing branches. This lesson focuses on **moving large payloads out of the message flow, replacing them with a small reference, and restoring the content at the exact step that needs it**.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain the **Claim Check** pattern from Enterprise Integration Patterns (EIP) and the roles of **check-in**, **claim token/reference**, and **check-out**.
2. Recognize when to replace large payloads with references instead of pushing full byte arrays through every Router, Channel, Transformer, or broker.
3. Distinguish **Spring Integration MessageStore-based Claim Check** from **object/blob storage references** for very large data; understand how they share the same idea yet differ in operational capability.
4. Design safe reference metadata: `tenantId`, `objectKey`, `contentLength`, `checksum`, `contentType`, `schemaVersion`, `businessCorrelationId`.
5. Write a Java service implementing **streaming check-in/check-out**, then integrate it into a Spring Integration flow while keeping clear boundaries between I/O, dispatch, and business logic.
6. Analyze the reference lifecycle: **write succeeds yet fails to publish**, **publish succeeds yet object is lost**, **redelivery**, **premature deletion**, **TTL/reaper**, **late consumers**, and **retries with side effects**.
7. Design tests and observability for data integrity, authorization, storage capacity, retention time, idempotency, and recovery during system failures.

## 2. The problem: a 50 MiB payload traversing a multi-branch flow

Suppose an application receives a 50 MiB business document file. It must go through validation, classification, Router, deduplication check, notification sending, and a final consumer analyzing its content.

If every step passes the raw `byte[]` payload:

~~~text
HTTP upload 50 MiB
    |
    v
Validate -> Enrich -> Router -> Queue -> Analytics -> Archive
          (all of them see the large payload)
~~~

Several problems emerge:

- **Memory:** multiple message copies in RAM, especially when queues hold backlogs, can inflate heap usage.
- **I/O and network:** serialization/copying of data between channels, brokers, or services repeats many times.
- **Broker limits:** some transports enforce maximum message sizes; oversized payloads cause publish failures or costly tuning.
- **Latency:** steps needing only metadata still have to carry huge byte volumes.
- **Security:** sensitive payloads may be replicated across components lacking permission to read full content.
- **Retry/replay:** resending an entire 50 MiB just to execute a metadata step is wasteful.

**Claim Check** replaces large content with **a small “claim ticket”**. Whichever step genuinely needs the content uses that ticket to retrieve data from a managed repository.

~~~mermaid
flowchart LR
    A["Inbound: large payload"] --> CK["Check-in: store data"]
    CK --> ST[("Payload / Object Store")]
    CK --> REF["Small Message<ClaimReference>"]
    REF --> F["Filter / Router / Enricher"]
    F --> Q["Queue / Broker"]
    Q --> CO["Check-out when truly needed"]
    ST -.->|"Read by verified key"| CO
    CO --> H["Content-processing consumer"]
    H --> CL["ACK / cleanup per policy"]
~~~

**Point to remember:** Claim Check **does not make data smaller**. It **relocates storage** of most of the content and sends in the message a reference sufficient to retrieve it later. Total bytes to store and read still exist; the cost is shifted to a more appropriate place.

## 3. How does EIP Claim Check work?

In EIP, Claim Check consists of three concepts:

1. **Check-in:** receives the original message/payload, stores the part to keep in a repository, and generates a claim token.
2. **Substitution:** passes a lightweight message carrying the token/reference through steps that do not need the large content.
3. **Check-out:** uses the token to retrieve the message/payload upon reaching the right consumer, with a policy to retain or delete data afterward.

~~~text
Original:
  payload = LargeDocument(50 MiB)
  headers = businessCorrelationId, tenant, contentType, ...

Check-in:
  store[key-123] = original payload or original message

Traveling message:
  payload = ClaimReference(key-123, length, digest, ...)
  headers = limited routing / tracing metadata

Check-out:
  retrieve store[key-123] -> original payload/message
  validate reference, permissions and integrity
  continue downstream processing
~~~

**Two variants to distinguish:**

- **Message-store claim check:** stores **the whole Message** with necessary headers; tokens typically look up by stored message ID. This aligns closely with Spring Integration's built-in pattern.
- **Blob/object-store claim reference:** stores **the binary body** (or large document) externally, while the traveling message is a metadata/reference DTO. This scales to very large files, multiple instances, and distributed consumers.

Both follow the Claim Check EIP, yet **you should not take an in-memory `MessageStore` example and claim it immediately fits hundreds of MiB payloads and production load**.

### 3.1. Differences from related EIPs

| Pattern | Purpose | Example |
| --- | --- | --- |
| **Claim Check** | Replace large payload with token, retrieve when needed | 50 MiB document → `ClaimReference` |
| **Content Enricher** | Fetch missing info into message | Look up customer profile by ID |
| **Transformer** | Convert payload representation/schema | Partner JSON → canonical DTO |
| **Filter** | Block ineligible messages | Process only permitted file types |
| **Router** | Select processing branch | Valid MIME → image/text pipeline |
| **Recipient List** | Send to multiple recipients | Metadata event → audit and indexing |
| **Splitter** | Split data into independent parts | Split document list into tasks |
| **Aggregator** | Combine child messages | Aggregate per-page processing results |
| **Gateway/Adapter** | Connect transports/external systems | HTTP upload, broker publish, object-store API |

**Do not confuse Claim Check with Content Enricher:** an Enricher fetches data to **augment** a message; check-out uses a token to **restore the part intentionally parked away**. A flow can use both patterns, but must manage their lifecycles separately.

## 4. When does Claim Check fit — and when does it not?

### 4.1. Consider Claim Check when

- Payloads exceed or approach transport/broker safety limits.
- Many intermediate steps need only metadata and **do not need raw bytes**.
- The same payload is read under control by multiple consumers, avoiding sending multiple large copies.
- Upload speed must be decoupled from processing speed to manage backlogs.
- Auditing **who fetched the content, when, and under which execution** is needed.
- You want to retry metadata/dispatch without re-uploading the entire payload.

### 4.2. Do not use it reflexively

- Small payloads and short flows: an external store can add complexity and latency with no clear gain.
- Payloads must be read at **every step**: repeated check-outs and network round trips may be slower than direct transfer.
- Lack of durable storage, authorization checks, and cleanup: tokens easily turn into **orphan references** or leak data.
- Flows needing one-pass streaming with no re-access requirement: direct streaming with limits and backpressure may beat store-then-fetch.
- Documents requiring atomic transactions across two systems: Claim Check **does not create atomic transactions** between object stores and brokers by itself.

### 4.3. Trade-off table

| Criterion | Carrying payload directly | Claim Check |
| --- | --- | --- |
| Message on broker | Can be huge | Small, mostly metadata |
| Memory at intermediate steps | Easily high when buffering many copies | Usually lower |
| Payload read count | May traverse many flow segments | Read from store when needed |
| Complexity | Fewer components | Needs store, ref lifecycle, cleanup |
| Latency for consumer needing bytes | No external fetch needed | Adds check-out operation |
| Retry/replay | May resend large bytes | Resends small reference |
| Security | Payload traverses many channels | Needs ACL/tenant scoping on store |
| Data risk | Message/broker retention | Orphans, dangling references, TTL, object corruption |
| Durability | Depends on broker/transport | Depends on both broker and payload store |

## 5. Designing a small, explicit ClaimReference contract

In a multi-service system, **do not send merely an arbitrary ID string** if consumers must inspect and verify the source contract. For example:

~~~json
{
  "documentId": "DOC-1201",
  "tenantId": "tenant-a",
  "objectKey": "documents/tenant-a/4f...d2",
  "contentType": "application/pdf",
  "contentLength": 52428800,
  "sha256": "hex-digest-of-original-bytes",
  "schemaVersion": "claim-ref-v1"
}
~~~

This is an **illustrative schema**, not JSON with a real valid key/digest. `objectKey` is a **server-generated** identifier, never taken directly from user-supplied filenames or arbitrary paths.

| Field | Purpose | Notes |
| --- | --- | --- |
| `documentId` | Document business ID | Used for correlation, not necessarily the storage key |
| `tenantId` | Authorization boundary | Must compare against verified identity, not trust metadata blindly |
| `objectKey` | Object lookup key | Random/opaque; prevent path traversal/IDOR |
| `contentType` | Source data representation | Not proof of a safe file |
| `contentLength` | Expected size | Verified on write and read |
| `sha256` | Integrity check | Digest does not replace signatures or authorization |
| `schemaVersion` | Claim reference version | Compatibility as services evolve |
| `businessCorrelationId` | End-to-end tracing | Can sit in controlled headers |
| `expiresAt` (if any) | Retrieval deadline | Do not expire before retry/replay windows |

### 5.1. A token is not an access right

An unpredictable object key **is not automatically valid authorization**. Consumers must be authenticated and checked for `tenantId`/role/operation against authoritative data. Avoid building `GET /objects/{id}` endpoints that check only whether the ID exists; that is an **IDOR** (Insecure Direct Object Reference) risk.

If using pre-signed URLs, they act nearly like a **bearer credential** during their validity window. Issue them only to authorized recipients/targets, set short TTLs, restrict HTTP methods/scopes, avoid logging full URLs, and control shareability.

### 5.2. A digest is not a digital signature

`SHA-256` helps detect altered bytes on check-out. Yet if an attacker can modify **both the object and the digest on the reference**, comparing those two values does not prove source authenticity. For tamper-resistant data, add **signatures/HMACs or immutable metadata protected by a trusted source** per your threat model.

### 5.3. Content-Type still needs verification

`contentType=application/pdf` is descriptive metadata; a file may misdeclare its type. For sensitive files, validate allowed formats, size limits, structural checks, or malware scans per policy before handing off to parsers, rather than relying only on filenames or client-sent MIME types.

## 6. A sample lifecycle: upload → store → reference → consume → cleanup

~~~mermaid
sequenceDiagram
    participant U as Upload Client
    participant I as Ingress
    participant S as Object Store
    participant B as Broker
    participant C as Consumer
    participant M as Metadata/State Store
    U->>I: Upload (stream)
    I->>I: AuthN/size/type validation
    I->>S: PUT (server-generated key)
    S-->>I: saved key, size, checksum
    I->>M: Record reference + lifecycle
    I->>B: Publish small ClaimReference
    B-->>C: Deliver ClaimReference
    C->>M: Validate tenant/state/claim
    C->>S: GET object by authorized key
    S-->>C: Content stream
    C->>C: Verify length/digest + process
    C->>M: Record result, ACK intent
    C-->>B: ACK per transport
    M->>S: Cleanup when retention allows
~~~

**Note:** PUT object, writing metadata, and broker publishing **do not sit inside one ACID transaction by default**. Hence you must handle **partial failures**.

### 6.1. Case where data is stored yet reference was not emitted

~~~text
PUT object success
  |
  v
Process crashed before broker publish
  |
  v
Orphan object: data exists yet no consumer knows the key
~~~

How to handle:

- Record `UploadState=STORED_NOT_PUBLISHED` with a retryable operation ID.
- Use the **outbox pattern** if metadata store and outbox can be written atomically, then a publisher emits the reference.
- Run a job finding **unreferenced** objects after a grace period and delete safely, instead of deleting immediately upon seeing “unpublished.”
- Emit metrics `orphanCandidates`, `outboxLag`, `publicationFailures`.

### 6.2. Reference published yet object unreadable

~~~text
Broker delivers reference
  |
  v
Object GET -> 404 / expired / access denied / storage outage
~~~

This could be a **dangling reference**, authorization error, infrastructure outage, or eventual consistency. Never automatically mark the document as successfully processed.

- 404 because object was deleted too early: reconcile and fix retention policy.
- 403 error: inspect principal/tenant authorization; never “skip permission checks” to keep going.
- 5xx/timeout from object store: retry with bounded backoff, maintaining idempotency and proper message visibility.
- Digest/size mismatch: quarantine, trigger integrity alerts, never pass bytes to business handlers.

### 6.3. Consumer ACKs before finishing processing

If the consumer ACKs the broker immediately upon receiving the reference and then crashes before check-out, the message may **lose its retry opportunity**. Define acknowledgments per transport:

~~~text
Receive reference
    -> Validate + fetch + verify
    -> Execute business operation idempotently
    -> Persist outcome / checkpoint
    -> ACK (or outbox/transaction per transport)
~~~

No single ACK order fits every system, yet avoid “ACKing success” when nothing guarantees downstream will continue.

## 7. Spring Integration Claim Check and MessageStore

Spring Integration provides components supporting **Claim Check In/Out** backed by **MessageStore**. Conceptually:

~~~text
Message<LargePayload>
      |
      v
Claim Check In Transformer
      |-- store original Message in MessageStore
      |-- emit claim-check identifier
      v
Message<ClaimId>
      |
   ... routing, delivery ...
      |
      v
Claim Check Out Transformer
      |-- lookup original Message by identifier
      v
Message<LargePayload>
~~~

You can use `ClaimCheckInTransformer` / `ClaimCheckOutTransformer` or corresponding DSL configurations depending on your **Spring Integration version**. In practice, verify APIs and remove-on-check-out policies on the project's exact version.

**Important limitation:** an **in-memory** `MessageStore` only removes the payload from the circulating message; it **does not reduce total data resident in the JVM** and does not recover data after a process restart. It helps illustrate the pattern or fit modest cases, but **does not solve 50 MiB payloads across multiple nodes on its own**.

### 7.1. How does a typical MessageStore store messages?

Illustrative example of Spring Integration's core `MessageStore` API with a small payload to understand semantics — this is not the recommended way to store 50 MiB files in RAM:

~~~java
import java.util.UUID;
import org.springframework.integration.store.MessageStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

MessageStore store = new SimpleMessageStore();
Message<String> original = MessageBuilder
    .withPayload("sample-payload")
    .setHeader("businessCorrelationId", "DOC-1201")
    .build();

// Store original message.
store.addMessage(original);

// Stored message ID used to claim it back.
UUID id = original.getHeaders().getId();
Message<?> restored = store.getMessage(id);

if (restored == null) {
    throw new IllegalStateException("CLAIM_NOT_FOUND");
}
~~~

The example illustrates only **store/lookup**; it lacks token security, multi-tenant isolation, expiration, and ACK/retry. When choosing **retain vs delete** after claiming, enforce policies and corresponding `MessageStore` calls without deleting before downstream confirms recoverability of results.

### 7.2. MessageStore vs object storage

| Aspect | MessageStore-based Claim Check | External blob/object store |
| --- | --- | --- |
| Storage unit | Spring `Message<?>` and metadata | Binary object/stream, metadata stored separately |
| Claim ID | Usually tied to message ID | Server-generated object key/ref |
| Best suited for | Internal patterns, moderate payloads, group/message persistence | Large files, binary data, multi-service |
| Header restoration | Can retrieve stored message | Must define metadata/header projection |
| Security | Store ACLs + caller boundary | IAM/ACLs, tenant scoping, encryption |
| Bottleneck | Heap/DB/message serialization | Storage I/O, GET/PUT, request costs |
| Retention | Follows store lifecycle | Object lifecycle + metadata/outbox |
| Shareability | Depends on configured store | Multi-node readable per permissions |

**Do not** treat `JDBC MessageStore` as an optimal object store for all large files. Storing in a database works when contracts and load permit, yet for very large data you must evaluate storage capacity, serialization, indexes, transactions, backups, replication, and cost.

## 8. Java 17 design for an external object store

For large payloads, a **streaming** service design beats calling `Files.readAllBytes(...)` and stuffing a 50 MiB array into a message.

An illustrative boundary:

~~~java
import java.io.IOException;
import java.io.InputStream;

record IncomingDocument(
    String documentId,
    String tenantId,
    String contentType,
    InputStream content
) {}

record StoredObject(
    String objectKey,
    long contentLength,
    String sha256
) {}

record ClaimReference(
    String documentId,
    String tenantId,
    String objectKey,
    String contentType,
    long contentLength,
    String sha256,
    String schemaVersion
) {}

interface LargePayloadStore {
    // Implementation must cap bytes while streaming,
    // verify object size/digest, and commit the object safely.
    StoredObject put(String tenantId, InputStream content,
                     String contentType, long maxBytes) throws IOException;

    // Lookup must be constrained by authenticated tenant.
    InputStream open(String tenantId, String objectKey) throws IOException;

    // Clean up only when lifecycle/retention permits.
    void delete(String tenantId, String objectKey) throws IOException;
}
~~~

**Abstraction limitation:** the interface does not enforce those requirements by itself. The object store implementation is responsible for **safe uploads**, durable metadata, server-generated keys, access control, hashing/verification, and overwrite policies. `InputStream` is typically a **single-read** resource; never push it onto an asynchronous queue hoping the stream remains open when a consumer reads it.

### 8.1. Metadata and immutable values

The records above keep DTOs lightweight, yet validation is still required:

~~~java
import java.util.Objects;

final class ClaimValidation {
    static void validate(ClaimReference ref) {
        Objects.requireNonNull(ref, "claim");
        if (ref.documentId() == null || ref.documentId().isBlank()
            || ref.tenantId() == null || ref.tenantId().isBlank()
            || ref.objectKey() == null || ref.objectKey().isBlank()) {
            throw new IllegalArgumentException("CLAIM_IDENTITY_MISSING");
        }
        if (ref.contentLength() <= 0
            || ref.sha256() == null || !ref.sha256().matches("[0-9a-fA-F]{64}")
            || !"claim-ref-v1".equals(ref.schemaVersion())) {
            throw new IllegalArgumentException("INVALID_CLAIM_METADATA");
        }
    }
}
~~~

The example requires `contentLength > 0` because document business rules forbid empty files. If your system permits empty objects, adjust the rule per contract. The digest regex checks only **64-hex-digit formatting**, not the actual bytes.

### 8.2. Check-in service without buffering the whole payload

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Objects;

final class DocumentClaimService {
    private static final long MAX_UPLOAD_BYTES = 100L * 1024 * 1024;
    private final LargePayloadStore store;

    DocumentClaimService(LargePayloadStore store) {
        this.store = Objects.requireNonNull(store);
    }

    public ClaimReference checkIn(IncomingDocument incoming) {
        if (incoming == null
            || incoming.documentId() == null
            || incoming.documentId().isBlank()
            || incoming.tenantId() == null
            || incoming.tenantId().isBlank()
            || incoming.content() == null) {
            throw new IllegalArgumentException("INVALID_UPLOAD");
        }
        if (!"application/pdf".equals(incoming.contentType())) {
            throw new IllegalArgumentException("UNSUPPORTED_CONTENT_TYPE");
        }

        // InputStream lives only within this synchronous call.
        // store.put implementation must stream and enforce real limits.
        try (InputStream source = incoming.content()) {
            StoredObject saved = store.put(
                incoming.tenantId(), source,
                incoming.contentType(), MAX_UPLOAD_BYTES);

            if (saved == null || saved.contentLength() <= 0
                || saved.contentLength() > MAX_UPLOAD_BYTES) {
                throw new IllegalStateException("INVALID_STORED_OBJECT");
            }

            ClaimReference ref = new ClaimReference(
                incoming.documentId(),
                incoming.tenantId(),
                saved.objectKey(),
                incoming.contentType(),
                saved.contentLength(),
                saved.sha256(),
                "claim-ref-v1");

            ClaimValidation.validate(ref);
            return ref;
        } catch (IOException ex) {
            throw new UncheckedIOException("CLAIM_CHECK_IN_FAILED", ex);
        }
    }
}
~~~

**What is demonstrated:** after check-in, output is a small DTO; the large payload was streamed into `LargePayloadStore`. `DocumentClaimService` does not yet include authentication, metadata transactions, outbox, or cleanup. In production, **caller tenant must never be trusted directly from a client-built DTO**; it must be validated against a trusted principal/context prior to `store.put`.

**Retry limitation:** an already-read `InputStream` usually cannot be reopened. If check-in fails and requires retries, the system needs a reopenable source (safely spooled file, multipart upload session, durable staging area, etc.) rather than reusing a consumed `InputStream` instance.

### 8.3. Integrity inside the store implementation

`LargePayloadStore.put(...)` must compute `sha256` during upload and return `StoredObject` only after confirming object commit. Use a **streaming copy** with a small bounded buffer:

~~~text
InputStream → bounded byte buffer → digest + count → object storage PUT
                                               |
                                    reject if > maxBytes

After durable commit:
  return key, countedLength, computedSha256
~~~

Do not rely on client-supplied `Content-Length` as the sole defense against oversized uploads; a streaming request may omit that header or lie. Limits must be enforced **while reading**.

With multipart uploads, the object store implementation must **abort/clean up** partial parts on error and bound part counts/lengths/TTLs.

## 9. Spring Integration Java DSL: separating check-in and dispatch

You can expose the check-in service as a `Service Activator` endpoint inside an `IntegrationFlow`. This uses **Java DSL** and highlights the external I/O boundary without pretending `LargePayloadStore` is a built-in `MessageStore`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ClaimCheckFlowConfiguration {

    @Bean("documents.large.in")
    DirectChannel uploadInput() {
        return new DirectChannel();
    }

    @Bean("documents.claims.out")
    QueueChannel referencesOutput() {
        // Observation point in tests; production uses a broker adapter.
        return new QueueChannel();
    }

    @Bean
    IntegrationFlow checkInDocuments(DocumentClaimService claims) {
        return IntegrationFlow.from("documents.large.in")
            .handle(claims, "checkIn")
            .channel("documents.claims.out")
            .get();
    }
}
~~~

~~~text
documents.large.in
     |
     v
Service Activator: DocumentClaimService.checkIn
     |-- validate MIME/tenant at trusted boundary
     |-- streaming PUT into LargePayloadStore
     |-- return ClaimReference
     v
documents.claims.out (demo QueueChannel)
     |
     v
Router / Broker / Consumer receives ClaimReference
~~~

**This implements Claim Check using a dedicated service.** It does not use the built-in `ClaimCheckInTransformer`; separating I/O into `.handle(...)` clarifies the object-store boundary. The EIP essence is **storing content then forwarding a token**, independent of whether the Java endpoint happens to be named Transformer.

### 9.1. Why shouldn't input be a QueueChannel holding an InputStream?

`IncomingDocument.content` is an `InputStream` that can close when the HTTP request finishes or be consumed once. If `IncomingDocument` sits on a queue before a handler runs later, the stream may no longer be valid. Instead:

- Perform check-in within a **synchronous boundary** while the stream is still open.
- Or spool to a durable reopenable source, then queue **the spool/object reference**.
- Enqueue `ClaimReference` only after the object finishes saving and metadata is valid.

### 9.2. When downstream only needs metadata

After check-in, many steps can read `contentType`, `contentLength`, and `documentId` **without checking out**. Example:

~~~mermaid
flowchart LR
    C["ClaimReference"] --> V{"Filter: size/type/policy"}
    V -->|"OK"| R{"Router"}
    R --> A["Metadata indexer"]
    R --> D["Document processor"]
    D --> O["Check-out stream"]
    O --> P["Parse/scan document"]
    V -->|"Invalid"| E["Reject / audit"]
~~~

**Do not put object keys into public logs/metrics**, especially if the key can access the document. Use correlation identifiers that expose no permissions or sensitive info when tracing.

## 10. Check-out: fetching payloads at the right time with the right permissions

A consumer needing the content will:

1. Receive `ClaimReference`.
2. Verify message/claim origin and check tenant/operation permissions against authoritative state.
3. Validate ref version, file size/type, and object status.
4. Use the store client to read **the stream**.
5. Verify byte count/digest, decrypt/scan/parse per policy.
6. Record business outcome by idempotency key.
7. ACK and clean up per retention, never deleting recklessly right after reading bytes.

### 10.1. Java pseudocode with resource control

To avoid passing an open `InputStream` into asynchronous messages, perform check-out and content processing **within the same scope**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.Objects;

interface DocumentAuthorizer {
    // authenticatedTenant comes from trusted principal/workflow context.
    void requireRead(String authenticatedTenant, ClaimReference ref);
}

interface DocumentProcessor {
    // Consumer must process safely; commit business side effects
    // only after verifying the payload per contract.
    void processVerified(ClaimReference ref, InputStream content)
        throws IOException;
}

final class DocumentClaimConsumer {
    private final LargePayloadStore store;
    private final DocumentAuthorizer authorizer;
    private final DocumentProcessor processor;

    DocumentClaimConsumer(
            LargePayloadStore store,
            DocumentAuthorizer authorizer,
            DocumentProcessor processor) {
        this.store = Objects.requireNonNull(store);
        this.authorizer = Objects.requireNonNull(authorizer);
        this.processor = Objects.requireNonNull(processor);
    }

    void consume(String authenticatedTenant, ClaimReference ref) {
        ClaimValidation.validate(ref);
        authorizer.requireRead(authenticatedTenant, ref);

        try (InputStream stream =
                 store.open(authenticatedTenant, ref.objectKey())) {
            processor.processVerified(ref, stream);
        } catch (IOException ex) {
            throw new UncheckedIOException("CLAIM_CHECK_OUT_FAILED", ex);
        }
    }
}
~~~

**This is an abstraction**, not an assertion that `processVerified(...)` automatically verifies checksums. The `DocumentProcessor` implementation must enforce **byte limits, digests, and schema/malware validation** before committing side effects. If a consumer commits side effects **while streaming** and only detects a bad checksum at the end, detecting the error comes too late.

For workflows forbidding unverified processing, use a **staging/quarantine stream**: download and verify checksum/AV/schema into a safe temporary area, then open the verified source for the side-effect step. This keeps heap usage low while establishing an integrity checkpoint prior to commit.

### 10.2. Avoiding wrong-tenant reads on check-out

In the example, `LargePayloadStore.open(authenticatedTenant, ref.objectKey())` takes the **authenticated tenant**, never taking `ref.tenantId()` to bypass authorization. The implementation must match the reference/object's tenant against identity and policy before GET.

A claim with `tenantId=tenant-b` handed to `tenant-a`'s consumer must be denied, even if the object key exists.

### 10.3. Check-out does not automatically mean delete

If two consumers share a reference for auditing and indexing, consumer A deleting the object immediately after reading causes consumer B to hit 404. Never use “delete on first check-out” when you have:

- Fan-out to multiple recipients.
- Broker redeliveries or multi-day replays.
- Gateways needing post-failure re-queries.
- Audit/retention rules.
- Slow or offline consumers.

Instead, use a separate lifecycle/retention policy—potentially with **reference counting, per-consumer ACKs, leases, or deadlines**—paired with safe garbage collection.

## 11. Message headers: keep what is needed, drop what should not spread

After check-in, the output is no longer document bytes. Therefore the original `contentType` must be modeled explicitly:

~~~text
Original:
  payload: byte[] (application/pdf)
  headers: businessCorrelationId, sourceSystem, contentType

After check-in:
  payload: ClaimReference(...)
  headers: businessCorrelationId, trustedSource, refSchemaVersion
  payload.contentType: application/pdf (object metadata)

At check-out:
  payload: stream/verified document
  headers: correlation, processingContext per contract
~~~

If you leave `MessageHeaders.CONTENT_TYPE = application/pdf` on the message while the payload is a `ClaimReference` DTO, downstream components may **misread the payload as binary PDF**. Distinguish the **original object's content type** from the **envelope/ref's content type**; for example, use `originalContentType` or `ClaimReference.contentType`, and let transport serializers declare the reference's actual media type.

**Every original header need not return after check-out.** Keep only contract-permitted headers: correlation, verified source, policy version, and appropriate tenant security context. Tokens, Authorization headers, internal debug data, or secrets must not propagate carelessly.

### 11.1. Header propagation across brokers

Spring Integration message headers may hold non-serializable objects such as `replyChannel` pointing to an in-JVM bean/channel. When a reference traverses Kafka/AMQP/JMS, header mappers may drop or convert them. For cross-service request/reply, use **stably formatted message IDs/correlation IDs** and a contract-defined reply address rather than expecting raw Java channel objects to copy outward.

### 11.2. Correlation differs from object key

`businessCorrelationId` links processing steps; `objectKey` points to content; `MessageHeaders.id` identifies the envelope; `operationId` prevents duplicate side effects. Never merge all four into a single field when their lifecycles and permissions differ.

## 12. Check-in and publish: consistency between two systems

This is the most critical risk when pairing Claim Check with a broker:

~~~text
Step A: PUT large object into ObjectStore
Step B: INSERT metadata/state into database
Step C: PUBLISH ClaimReference to broker
~~~

These steps are normally **not atomic** without coordination.

| Post-failure state | Consequence | Recovery |
| --- | --- | --- |
| PUT succeeds, DB insert fails | Orphan object | Orphan-detection job after grace period |
| DB writes STAGED, PUT fails | Metadata points to missing object | Mark failed, conditionally retry upload |
| PUT+DB succeed, broker publish fails | Reference not yet processed | Outbox/publisher retry; do not blindly re-upload |
| Publish succeeds, consumer crashes | Redelivery may occur | Store retains object; consumer is idempotent |
| Object deleted while message still queued | Dangling reference | Retention + leases/visibility |
| Consumer finishes yet ACK lost | Redelivery of same reference | Stable operation ID and idempotency in business handler |

### 12.1. State machine model

~~~mermaid
flowchart TD
    S["RECEIVING"] -->|PUT durable| ST["STORED"]
    ST -->|Metadata+outbox| PB["PUBLISH_PENDING"]
    PB -->|Publish confirmed| AV["AVAILABLE"]
    AV -->|Consumer lease| PR["PROCESSING"]
    PR -->|Outcome committed| DN["PROCESSED"]
    PR -->|Retryable failure| AV
    AV -->|Retention reached| GC["ELIGIBLE_FOR_CLEANUP"]
    DN -->|Retention reached| GC
    GC -->|Safe delete| DE["DELETED"]
    S -->|Upload error| ER["FAILED / ABORT"]
~~~

**This is a proposed state machine**, not built-in states of Spring Integration Claim Check. Every state transition must fit your actual storage/broker. An application can simplify it while preserving the invariant:

> Never emit a reference marked ready before the object commits; never delete an object while a legitimate consumer still has retry or replay rights within the committed window.

### 12.2. Outbox and cleanup must be idempotent

If the outbox publisher reruns, the same reference may be published twice. Consumers should deduplicate by `(documentId, operationId, consumerName)` or an approved business key. Object store uploads should also detect retried uploads of the same logical document instead of creating hundreds of unowned copies.

Never assume “one message in the queue” means “one side effect at the consumer.”

## 13. TTL, retention, and garbage collection

### 13.1. Why can a 5-minute TTL lose data?

Suppose a consumer is offline for 20 minutes and the broker retains references for 24 hours, yet the object store auto-deletes payloads after 5 minutes:

~~~text
T0:   Upload object; publish reference
T+5:  Object lifecycle deletes object
T+20: Consumer receives reference -> 404
~~~

The message still exists, yet **its content is gone**. Object retention must cover:

- Maximum queue backlog duration.
- Expected retry count and backoffs.
- Supported consumer downtime.
- Replay/audit windows.
- Legal retention or deletion mandates.
- Processing duration across multiple recipients.

### 13.2. Conditional cleanup, not just wall-clock deletion

A policy typically includes:

~~~text
EligibleForDeletion =
    ProcessingFinalized
    AND AllRequiredConsumersAcked (if fan-out)
    AND MinimumRetentionReached
    AND NoActiveLease
    AND NoLegalHold
~~~

This is operational business logic, not Spring Integration syntax. When security policy forces an early TTL cutoff, design late-arriving messages to **be rejected with an explicit reason** instead of retrying forever.

### 13.3. Orphan sweepers and race conditions

An orphan-sweeping job must never conclude “no metadata at scan time” and delete immediately, because the publisher/metadata service may still be committing its transaction. Use grace periods, upload states, leases/CAS, and re-verification before deleting.

**Do not confuse `MessageGroupStoreReaper` with object-store cleanup.** The reaper governs message group lifecycles (Aggregator/Resequencer), whereas Claim Check object cleanup governs separate blob/reference lifecycles.

## 14. Fan-out and multiple consumers sharing a reference

When a claim reference goes to `audit`, `indexing`, and `document-analysis`, only one consumer needs to download the entire file; the other two can process metadata.

~~~mermaid
flowchart LR
    REF["ClaimReference"] --> RL{"Recipient List"}
    RL --> A["Audit: metadata only"]
    RL --> I["Index: metadata only"]
    RL --> D["Analysis: needs payload"]
    D --> CO["Check-out"]
    CO --> ST[("Object Store")]
~~~

This is a major benefit: **only consumers needing the content check out**.

If all three need the payload, each consumer can fetch independently:

- Increases read I/O and GET costs.
- May use bounded key/digest-keyed caching if data is cacheable.
- Must enforce per-recipient access rights rather than one unbounded shared token.
- Clean up only after all recipients' conditions are resolved.

### 14.1. Never put full bytes in every child

If a Splitter creates 1,000 child messages and copies the full 50 MiB `byte[]` into every header, memory/I/O explodes. Instead, send **an object reference + range info**:

~~~json
{
  "objectKey": "objects/opaque-123",
  "part": 17,
  "range": {"start": 1048576, "endExclusive": 1114112}
}
~~~

In production, use range reads only when the storage/format supports them and per-range integrity/checksums are designed; never arbitrarily treat any byte slice as a standalone valid document.

### 14.2. Aggregator must know each consumer's true status

When processing paginated documents, a Splitter generates multiple tasks referencing the same object. An Aggregator may wait for `N` results, yet one failed child or 404 check-out can hang the group. Define release/timeout/partial-result policies, per-execution correlation, and explicit error states so exceptions never turn into unexplained “no reply.”

## 15. Error channel, retry, and Claim Check error classification

| Error | Location | Should retry? | Handling direction |
| --- | --- | --- | --- |
| Upload exceeds size | Ingress/check-in | No with same data | Reject with `SIZE_LIMIT_EXCEEDED` |
| Disallowed MIME/schema | Validate | No | Reject/quarantine |
| AuthN/AuthZ failed | Ingress/check-out | Never bypass permissions | 401/403 or equivalent error |
| ObjectStore 5xx/timeout | PUT/GET | Yes, bounded | Exponential backoff, stable operation ID |
| Object 404 due to TTL | Check-out | Do not retry forever | Dangling reference/reconcile |
| Digest mismatch | Check-out | Do not process payload | Quarantine/integrity alert |
| Broker publish failed | After check-in | Yes via outbox | Never re-upload uncontrollably |
| Consumer side effect timeout | After check-out | Query status first | Idempotency/reconciliation |
| Delete failed | Cleanup | Conditional retry | Never corrupt committed business outcomes |

With `DirectChannel`, check-in exceptions may propagate back to callers; with pollers/executors/brokers, errors may travel via `ErrorMessage`/error channels per configuration. **Do not assume a single `errorChannel` handles all errors across all adapters and boundaries.**

### 15.1. Retrying GET differs from retrying a business POST

Check-out GET only reads the object, whereas processing its content can trigger side effects. If a consumer crashes after writing to the database but before ACK, redelivery of the same reference invokes the consumer again. You need **idempotency** on the business operation, not only on storage GET.

### 15.2. Gateway request–reply

If a Gateway awaits document analysis while check-in returns only a `ClaimReference`, define the **reply contract**: does the Gateway receive `UploadAccepted(claimId)` early or wait for `DocumentProcessed`? The two options carry different SLAs and states.

Never report “processing finished” merely because the object saved or the reference published. Usually it fits better to return **202 Accepted/processing ID** (if the API contract permits) and report completion via an event/status endpoint.

## 16. Unit testing the check-in service

To test flow logic without real cloud dependencies, use a **fake store** with small payloads. It is **strictly for tests**, not proof that in-memory storage solves 50 MiB payloads.

### 16.1. Simple fake store for JUnit

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

final class FakeLargePayloadStore implements LargePayloadStore {
    private final Map<String, byte[]> data = new HashMap<>();

    @Override
    public StoredObject put(String tenant, InputStream input,
                            String contentType, long maxBytes)
            throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int count;
        while ((count = input.read(buf)) != -1) {
            if (output.size() + (long) count > maxBytes) {
                throw new IOException("SIZE_LIMIT_EXCEEDED");
            }
            output.write(buf, 0, count);
        }

        byte[] bytes = output.toByteArray();
        String key = tenant + "/" + UUID.randomUUID();
        data.put(key, bytes);
        return new StoredObject(
            key, bytes.length, sha256(bytes));
    }

    @Override
    public InputStream open(String tenant, String key) throws IOException {
        if (!key.startsWith(tenant + "/")) {
            throw new IOException("ACCESS_DENIED");
        }
        byte[] bytes = data.get(key);
        if (bytes == null) {
            throw new IOException("OBJECT_NOT_FOUND");
        }
        return new ByteArrayInputStream(bytes);
    }

    @Override
    public void delete(String tenant, String key) throws IOException {
        if (!key.startsWith(tenant + "/")) {
            throw new IOException("ACCESS_DENIED");
        }
        data.remove(key);
    }

    private static String sha256(byte[] data) {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(data));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

**Limitations of the fake:** it uses `ByteArrayOutputStream` and `HashMap` for small test fixtures; **never use it for large production documents**—it has no real security, concurrency, transactions, persistence, or TTL.

### 16.2. JUnit 5: check-in, reference, and intact data

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;

class DocumentClaimServiceTest {

    @Test
    void checkInStoresPayloadAndReturnsSmallReference()
            throws Exception {
        FakeLargePayloadStore store = new FakeLargePayloadStore();
        DocumentClaimService claims = new DocumentClaimService(store);

        byte[] content = "%PDF-demo-content".getBytes(
            StandardCharsets.UTF_8);

        ClaimReference ref = claims.checkIn(
            new IncomingDocument(
                "DOC-1201", "tenant-a", "application/pdf",
                new ByteArrayInputStream(content)));

        assertEquals("DOC-1201", ref.documentId());
        assertEquals("tenant-a", ref.tenantId());
        assertEquals("application/pdf", ref.contentType());
        assertEquals(content.length, ref.contentLength());
        assertEquals("claim-ref-v1", ref.schemaVersion());

        try (var fromStore =
                 store.open("tenant-a", ref.objectKey())) {
            byte[] restored = fromStore.readAllBytes();
            assertArrayEquals(content, restored);
            String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(restored));
            assertEquals(digest, ref.sha256());
        }
    }

    @Test
    void rejectsWrongContentTypeBeforeUploading() {
        DocumentClaimService claims =
            new DocumentClaimService(new FakeLargePayloadStore());

        assertThrows(IllegalArgumentException.class, () ->
            claims.checkIn(new IncomingDocument(
                "DOC-1202", "tenant-a", "text/plain",
                new ByteArrayInputStream(new byte[] {1, 2, 3}))));
    }

    @Test
    void refusesReadingAnotherTenantsObject() throws Exception {
        FakeLargePayloadStore store = new FakeLargePayloadStore();
        ClaimReference ref =
            new DocumentClaimService(store).checkIn(
                new IncomingDocument(
                    "DOC-1203", "tenant-a", "application/pdf",
                    new ByteArrayInputStream(new byte[] {1, 2, 3})));

        assertThrows(java.io.IOException.class, () ->
            store.open("tenant-b", ref.objectKey()));
    }
}
~~~

The example `"%PDF-demo-content"` is not a valid PDF file. The unit test checks only **how bytes and metadata are stored/restored**, not PDF parsers or antivirus. Real applications need valid PDF fixtures and separate scan/validation tests.

### 16.3. Testing size limits and mid-stream failures

Fake store tests can allocate small arrays and pass a low `maxBytes` when calling the store directly. Required cases:

- Exactly `maxBytes`: accepted per policy if valid.
- Exceeding `maxBytes` by 1 byte: rejected and **does not commit a complete object**.
- `InputStream.read(...)` throws `IOException` mid-stream: upload aborts/cleans up.
- Store PUT succeeds yet metadata/audit write fails: orphan reconciliation handles it.
- Digest is computed from **actually stored bytes**, not client-declared `Content-Length`.

## 17. Spring Integration test: payload turns into a reference

With `ClaimCheckFlowConfiguration` (section 9), verify the flow accepts an `IncomingDocument` on the input channel and emits a `ClaimReference` without **sending a large `byte[]`** to the downstream channel.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

@SpringJUnitConfig(classes = {
    ClaimCheckFlowConfiguration.class,
    DocumentClaimFlowTest.FakeStoreConfig.class
})
class DocumentClaimFlowTest {
    @Configuration
    static class FakeStoreConfig {
        @Bean LargePayloadStore store() {
            return new FakeLargePayloadStore();
        }
        @Bean DocumentClaimService claims(LargePayloadStore store) {
            return new DocumentClaimService(store);
        }
    }

    @Autowired @Qualifier("documents.large.in")
    MessageChannel input;

    @Autowired @Qualifier("documents.claims.out")
    PollableChannel output;

    @Test
    void flowReplacesLargeBodyWithSmallClaimReference() {
        byte[] payload = "document bytes".getBytes(
            StandardCharsets.UTF_8);

        IncomingDocument upload = new IncomingDocument(
            "DOC-1301", "tenant-a", "application/pdf",
            new ByteArrayInputStream(payload));

        assertTrue(input.send(MessageBuilder.withPayload(upload)
            .setHeader("businessCorrelationId", "DOC-1301")
            .build()));

        Message<?> message = output.receive(1000);
        assertNotNull(message);
        assertInstanceOf(ClaimReference.class, message.getPayload());

        ClaimReference ref = (ClaimReference) message.getPayload();
        assertEquals("DOC-1301", ref.documentId());
        assertEquals(payload.length, ref.contentLength());
        assertEquals("DOC-1301",
            message.getHeaders().get("businessCorrelationId"));

        assertNull(output.receive(0), "No duplicate reference");
    }
}
~~~

**Integration test limitation:** this is a single-JVM demo with a fake store; it does not prove broker publish/ACK, real AuthN/AuthZ, restart durability, or validated PDF bytes. It proves only **wiring and message shape after check-in**.

For flows using built-in `MessageStore`, write a matching integration test for **Claim Check In → claim token → Claim Check Out**, verifying accurate message restoration and explicit **remove/retain policy** per framework version.

## 18. Comprehensive test matrix

| Scenario | Input/state | What to verify |
| --- | --- | --- |
| Happy path | Valid payload, healthy store | Small reference, object reads back identically |
| 0-byte input | Empty file | Reject or accept per explicit contract |
| Exact threshold size | `maxBytes` | Boundary behavior |
| Oversized input | `maxBytes + 1` | Upload aborts, no object committed |
| Wrong Content-Type | Claims PDF yet invalid bytes | Validation/scan at proper layer |
| SHA mismatch | Tampered object | Side effects never commit |
| Wrong tenant | Consumer A fetches tenant B's object | Access denied |
| Unknown/forged ref | Non-existent key | Error/quarantine; never guess another object |
| ObjectStore outage | PUT or GET 5xx | Bounded retry, workflow not lost |
| Stale object | Object already deleted by TTL | Dangling reference/reconcile |
| Upload crash | PUT finished, publish incomplete | Orphan/outbox recovery |
| Duplicate publish | Outbox retry | Consumer idempotent |
| Consumer crash | Read finished, ACK incomplete | Redelivery produces no duplicate side effects |
| Fan-out | Two consumers share ref | Object not deleted while another consumer still needs it |
| Multi-instance | Consumer on different node than ingress | Shared store, valid ACLs |
| Broker header mapper | Ref crosses Kafka/AMQP | Correlation/serialization contract preserved |
| Stream close | HTTP InputStream closes early | Synchronous check-in or staging |
| Retry InputStream | Second attempt with consumed stream | Reopen source; never reuse old stream |
| Object delete race | Cleanup runs during consumer GET | Leases/retention prevent premature deletion |
| Legal hold | Document must be retained | Lifecycle policy does not delete unlawfully |
| Metadata leakage | Logs/metrics/outbound responses | No object key/token/PII leaked |
| Restart | Reference queued, process restarts | Object survives and recovers properly |
| Integrity + malware | Malicious PDF | Scanned/validated before risky parsing |

### 18.1. Test against **disallowed behaviors**

Do not assert only that a reference was sent. Assert:

~~~text
After check-in:
  output message payload is ClaimReference
  no raw large byte[] goes to broker-facing channel
  unauthorized tenant cannot check-out
  invalid digest does not reach business processor
  repeated delivery does not run side effect twice
  deletion cannot happen before required retention/ACK
~~~

A test checking only `output != null` can miss severe bugs if the large payload still gets copied into an auxiliary header or log.

## 19. Observability and capacity calculations

### 19.1. An approximate calculation

Suppose 1,000 uploads/hour, each 50 MiB:

~~~text
Object bytes/hour
  = 1,000 × 50 MiB
  = 50,000 MiB ≈ 48.8 GiB/hour

If references are ~1 KiB:
  broker payload/hour
  ≈ 1,000 × 1 KiB
  ≈ 0.98 MiB/hour

Total storage/GET traffic still depends on
retention, read count, retry and consumer fan-out.
~~~

This is an **illustrative calculation** omitting object metadata, replication, compression, network protocols, broker overhead, and GET counts. Claim Check can sharply reduce **bytes traversing the broker**, yet does not shrink required object store capacity.

### 19.2. Metrics to measure

| Component | Suggested metric / log | Purpose |
| --- | --- | --- |
| Ingress | Upload count, bytes, rejected-size | See actual demand |
| Check-in | PUT latency, size, checksum failures | Detect storage bottlenecks |
| Object store | Capacity, GET/PUT error rates, lifecycle deletes | Track durability and cost |
| Reference publisher | Outbox lag, publish retries | Spot stored-not-published |
| Broker | Backlog, age, redelivery count | Assess safe retention |
| Check-out | Fetch latency, 403/404/5xx, checksum mismatches | Detect dangling/corrupt data |
| Business consumer | Success/errors, idempotency duplicates | Never mistake GET for success |
| Cleanup job | Orphans, retention-expired, delete failures | Prevent leaks/early deletion |
| Security audit | Principal, tenant, operation, decision | Trace data access |
| End-to-end | Document processing SLA, stuck claims | Verify workflow completion |

**Do not** use unbounded `objectKey`, `documentId`, `tenantId`, or `businessCorrelationId` as high-cardinality metric tags. In logs/traces, restrict sensitive fields, enforce access control, and format without exposing pre-signed URLs or tokens.

### 19.3. Reporting “upload accepted” is not “document processed”

At minimum distinguish:

- **RECEIVED:** upload source started/received.
- **STORED:** object saved and verified.
- **PUBLISHED:** reference placed into processing channel per broker semantics.
- **PROCESSING:** consumer fetching/parsing.
- **PROCESSED:** business action committed per contract.
- **FAILED/QUARANTINED:** error needing intervention.
- **DELETED:** retention cleanup completed.

`postSend(sent=true)` on the reference channel **does not prove the consumer read the bytes or completed the business work**.

## 20. Common anti-patterns

| Anti-pattern | Consequence | How to avoid |
| --- | --- | --- |
| Storing 100 MiB in `SimpleMessageStore` thinking heap is light | Payload still sits in JVM | Use durable external store when appropriate |
| Putting `InputStream` into async queue | Stream closed/consumed before reading | Check in synchronously, send reference |
| Copying payload into headers “for debugging” | Loses all Claim Check benefits, increases leak risk | Send minimal metadata only |
| Using client filename as object key | Traversal/collisions/IDOR | Server-generated opaque keys |
| Treating token as authorization | Anyone with token reads data | AuthN/AuthZ by tenant/operation |
| Deleting immediately on check-out | Other consumers or retries hit 404 | Lifecycle + retention + per-consumer completion |
| Object TTL shorter than broker retention | Dangling references | Align retention/replay policies |
| PUT finishes, publish fails, ignored | Orphan objects, lost workflow events | Metadata/outbox + sweeper |
| Publishing before object commit | Consumer gets 404 or partial bytes | Publish only after durable commit confirmed |
| Retrying upload with consumed InputStream | Empty/corrupt retry | Reopen source or replayable staging |
| Checking length only without digest | Wrong data can share same length | Digest + protected metadata |
| Continuing side effects on digest mismatch | Processing corrupted content | Quarantine before commit |
| Keeping `contentType=application/pdf` when payload is ref DTO | Consumer misparses format | Separate object MIME and envelope MIME |
| Using `MessageHeaders.id` for business idempotency | Retries mint new message IDs | Stable operation/document keys |
| Scanning and deleting orphans immediately when DB record missing | Races with in-flight metadata commit | Grace period, leases, recheck |
| Overusing Claim Check for 2 KiB payloads | Unnecessary complexity and latency | Measure first, then pick strategy |
| Testing fake store and treating as production-verified | Lacks real durability/auth/concurrency | Contract/integration/failure tests against real backends |

## 21. Implementation checklist

- [ ] **Measurable reason** exists to move payload out of messages: size, queue backlog, broker limit, or security.
- [ ] Clearly chose **MessageStore claim check** vs **object-store reference** without conflating capacity and durability.
- [ ] Large payloads upload via **streaming with real byte limits**, avoiding full heap buffering.
- [ ] References carry only needed metadata, stay small, and declare explicit schema versions.
- [ ] Storage keys are server-generated; access is authorized by tenant/operation.
- [ ] Content type validation, SHA/length integrity checks, and business-required scanning exist.
- [ ] Explicit contracts exist for missing objects, hash mismatches, timeouts, and access denials.
- [ ] Objects commit durably before consumers can process references.
- [ ] Metadata/outbox or recovery exists for partial PUT/DB/publish failures.
- [ ] Correlation/idempotency keys remain stable across retries/redeliveries.
- [ ] Clear ACK boundary: check-in success differs from business processing success.
- [ ] Fan-out has a multi-consumer policy; objects are not deleted when only one consumer finishes.
- [ ] Object retention >= guaranteed retry/queue/replay window, barring designed legal exceptions.
- [ ] Cleanup/orphan sweepers use grace periods, TTLs, leases, and audits.
- [ ] Header mapping, envelope MIME, and original metadata are cleanly separated.
- [ ] Unit/integration, failure, and security tests exist alongside GET/PUT/storage cost monitoring.
- [ ] Tokens, pre-signed URLs, and sensitive payloads never appear in public logs, metrics, or errors.
- [ ] Playbooks cover dangling references, corrupted objects, broker redeliveries, and premature deletion.

## 22. Applied exercise

A platform ingests **100 MiB PDF dossiers** for text extraction, compliance checks, and archiving. The system has three consumers:

- **Audit:** needs only metadata; must not read the whole document.
- **Extraction:** must download the PDF, verify integrity, and extract text.
- **Compliance:** reads content only when the dossier is flagged for review.

**Requirements:**

1. Draw the flow `HTTP upload → Claim Check In → Broker → Recipient List → Check Out on demand → Consumer`.
2. Design `ClaimReference` containing document ID, tenant, object key, size, SHA-256, content type, and version; indicate which fields must not be trusted from clients.
3. Choose object store, `MessageStore`, or hybrid; explain why 100 MiB should not sit on every service's heap.
4. Write a Java `LargePayloadStore` abstraction and a streaming check-in service with a 100 MiB limit.
5. Describe how to verify the digest **before** executing risky side effects (e.g., committing official analysis results).
6. Design an outbox and orphan cleanup when PUT succeeds yet reference publishing fails.
7. Given three consumers running at different speeds, design retention/leases/ref counting or equivalent policies so Audit cannot cause payload deletion before Extraction/Compliance.
8. Write unit tests for a fake store and a Spring Integration integration test verifying the output is a reference.
9. Design failure tests: wrong tenant, 404 object, digest mismatch, oversized upload, GET timeout, broker redelivery, cleanup race.
10. When Compliance decides **it does not need to read the payload**, prove it performs no check-out (reducing I/O and minimizing privilege).
11. Explain why retrying document processing must not duplicate **an already-committed business record**, even when fetching the same object again.
12. Propose metrics for `storedBytes`, `objectAge`, `danglingRef`, `orphanCandidates`, `fetchLatency`, and `processingOutcome`.

**Hint:** use an **opaque object key**, verify tenant permissions from the principal, and separate an **execution/operation ID** from the key. During fan-out, the stored object must not be deleted by the first consumer. For large files, prefer streaming and verified staging over passing bytes in message headers.

## 23. Summary

**Claim Check** is an EIP solution for **parking large payloads in a managed store and carrying a small reference through the message flow**, then restoring the data exactly where needed. In Spring Integration, Claim Check In/Out components build on `MessageStore`; for very large data, a variant using **external object/blob storage** usually fits better when paired with proper permissions, integrity, retention, and cleanup.

The primary benefits are **reducing bytes crossing intermediate steps and brokers, limiting sensitive data exposure, and decoupling upload speed from processing**. Yet Claim Check does not automatically provide transactions between object stores and brokers, safe authorization, orphan handling, or side-effect-safe retries. Combine Filter, Router, Transformer/Enricher, Gateway, Recipient List, Splitter/Aggregator, retry, error channel, correlation, idempotency, and observability to ensure **valid references, intact payloads, no data loss from premature cleanup, and no duplicate business processing**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Claim Check, Message Store, Content Enricher, Message Translator); Spring Integration Reference on [Claim Check](https://docs.spring.io/spring-integration/reference/claim-check.html), Message Stores, Transformers, Java DSL, Error Handling, and Testing; Spring Messaging on `MessageHeaders`; Java SE on `InputStream`, `MessageDigest`, `BigDecimal`, and resource management.
