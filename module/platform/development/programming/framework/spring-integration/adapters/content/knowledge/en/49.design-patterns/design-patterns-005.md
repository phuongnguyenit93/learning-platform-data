# Claim Check with Message Store in Spring Integration Adapters

> **Chapter:** Design patterns  
> **Topic:** Claim check with message store  
> **Module scope:** SPRING_INTEGRATION_ADAPTERS — connecting external systems via inbound/outbound adapters, gateways, pollers, and MessageChannels. This lesson focuses on Claim Check in File, SFTP, HTTP, JMS, AMQP, Kafka, and database flows; designing message contracts, storing/retrieving payloads, error handling, security, transactions, and data lifecycle.

## 1. The Problem: Large Payloads When Intermediaries Only Need a Reference

Imagine a system receiving an 80 MB PDF report over HTTP that needs to forward a validation request onto a broker queue and then to an analysis service. The broker enforces a message size limit, and routers only need to inspect a record ID and processing type; there is no reason to haul 80 MB through every orchestration step.

**Claim Check** is an Enterprise Integration Pattern (EIP) that **temporarily stores part or all of a message's content in a repository**, then passes a smaller **reference/claim token** through the integration flow. Where the data is actually needed, the consumer uses the token to **retrieve the original content** from the governed store.

~~~mermaid
sequenceDiagram
    participant P as Producer / Inbound Adapter
    participant IN as Claim Check In
    participant STORE as Message Store
    participant CH as Channel / Broker
    participant OUT as Claim Check Out
    participant H as Business Handler
    P->>IN: Message containing large payload
    IN->>STORE: Store message / payload
    STORE-->>IN: Claim token
    IN->>CH: Message containing claim token
    CH->>OUT: Claim token
    OUT->>STORE: Lookup data by token
    STORE-->>OUT: Original message / payload
    OUT->>H: Restored message
    H-->>OUT: Business result / commit
    Note over STORE,H: Delete claim only when completion policy permits
~~~

### 1.1. Learning objectives

After this lesson, learners can:

1. Present Claim Check and distinguish it from **Message Store**, **Content Enricher**, **Message Filter**, **Splitter**, and **Idempotent Consumer**.
2. Understand the roles of **ClaimCheckInTransformer**, **ClaimCheckOutTransformer**, **MessageStore**, and **MessageChannel** in Spring Integration.
3. Decide between **storing the full Message, storing only the payload, or using external object storage with metadata**, rather than assuming a database can handle arbitrary files.
4. Create a claim token contract including ID, source, tenant, version, access permissions, TTL, and integrity checks.
5. Connect Claim Check flows with File/SFTP, HTTP, JMS, AMQP, Kafka, and database-backed adapters.
6. Distinguish **stored**, **token published**, **retrieved**, **processed/committed**, and **deleted** — non-equivalent states.
7. Handle missing claims, duplicate tokens, post-crash retries, expired tokens, competing consumers, and fan-out.
8. Design security, retention, cleanup, observability, and end-to-end testing.

### 1.2. Lab deliverable

Learners will design a simulated pipeline: a large CSV file or document is received via File/SFTP/HTTP, stored in a shared repository, a **ClaimReference** is sent across MessageChannel/broker, and then a consumer validates permissions and retrieves the data to process. The lab requires a **happy path**, **error paths**, **post-restart recovery**, and **proof that claims are not deleted before consumer completion**.

**Note:** all IDs, endpoints, schemas, and data in this lesson are illustrative. Never use production storage or real personal data when running labs.

## 2. How the Claim Check Pattern Works

In EIP, “claim check” evokes checking luggage at a counter and receiving a ticket to retrieve it later. In systems integration:

- **Luggage** is the original payload or original message.
- **Baggage check counter** is a persistent store or managed repository.
- **Claim ticket** is the claim token/reference.
- **Recipient** is an authorized downstream consumer.

### 2.1. Five basic steps

1. **Receive data:** inbound adapter builds a Message containing the content to process.
2. **Claim check in:** persists the message or large content into the store and generates/receives a stable identifier.
3. **Pass token:** sends a small message containing the claim ID (and minimal metadata) across channels/brokers.
4. **Claim check out:** consumer receives the token, verifies validity, and retrieves the data.
5. **Process and clean up:** handler completes business logic; the claim is retained or cleaned up per **completion, retry, fan-out, audit, and retention policies**.

### 2.2. Why pass a token?

| Problem when passing raw payloads | How Claim Check helps | What Claim Check doesn't solve alone |
| --- | --- | --- |
| Broker restricts record/message size | Sends a small reference | Store must handle writing/reading large payloads |
| Routers/filters only need metadata | Passes token + routing metadata | If a router needs payload fields, data must still be fetched |
| Multiple hops copy large byte arrays | Cuts bytes over intermediate channels | Total I/O still includes writing to and reading from store |
| Data must be kept long-term for retries/audits | Separately governed storage | TTL, backups, access control, and cleanup must be designed |
| Workers run on different instances | Reference to a shared store | Local paths/in-memory stores don't share automatically |
| Payload contains sensitive info | Limits intermediaries from seeing raw content | Claim token can become an unauthorized access vector |

Claim Check is a **trade-off of broker network I/O for store write and retrieval I/O**, not a compression trick, encryption method, or universal performance boost across all workloads.

### 2.3. Distinguishing Claim Check from other patterns

| Pattern | Primary function | How it differs from Claim Check |
| --- | --- | --- |
| **Claim Check** | Store payload/message, pass token, retrieve later | Replaces large content with a temporary/permanent reference |
| **Content Enricher** | Augments data from another source | Does not require storing the initial message and fetching it back |
| **Message Filter** | Keeps or drops messages by condition | Has no content storage/retrieval contract |
| **Splitter/Aggregator** | Splits/combines messages | Does not inherently shrink payloads via references |
| **Idempotent Consumer** | Prevents applying the same operation multiple times | A token pointing to the same payload does not prove business ran once |
| **Message Store** | Provides API to persist/retrieve Messages | Is the storage component; Claim Check is the pattern using it |
| **Transactional Outbox** | Binds DB changes to intent to publish events | Solves atomic publishing; can be paired with Claim Check |
| **Object storage link** | References an externally stored object | Can implement Claim Check if backed by a store/redeem contract |

### 2.4. Do not confuse Claim Check with a queue

The **MessageStore** holding the original message is not itself a **work queue** distributing jobs. A broker/JMS/Kafka/QueueChannel carries the token, while the store holds the actual data. Having a claim in the store does not mean a message is in the broker; deleting a token from the broker does not automatically delete the object in the store.

## 3. Two Separate Lifecycles: Transport Message and Claimed Data

A sound design must track the **delivery lifecycle** and **claim lifecycle** independently.

### 3.1. Token lifecycle in transit through a broker

~~~text
CREATED -> PUBLISHED -> DELIVERED -> PROCESSING -> ACKNOWLEDGED
                         |
                         +--> REDELIVERED / RETRY / DEAD-LETTER
~~~

### 3.2. Content lifecycle in the Message Store

~~~text
PREPARED -> STORED -> AVAILABLE -> RETRIEVED
                         |           |
                         |           +--> IN_USE / COMPLETED
                         |
                         +--> EXPIRED_PENDING_CLEANUP
                                     |
                                     +--> DELETED / RETAINED_FOR_AUDIT
~~~

This is a suggested business model, **not a built-in enum** in Spring Integration. Claim states must be defined in your application if tracking is needed; the MessageStore interface is not a workflow engine by default.

### 3.3. Commonly misunderstood milestones

| Milestone | Meaning | What cannot be concluded yet |
| --- | --- | --- |
| Message stored successfully | Store has the data | Whether the broker received the token |
| Token published successfully | Transport confirmed one step per contract | Whether the consumer retrieved the payload |
| Claim retrieved successfully | Consumer read the content | Whether the business handler committed |
| Handler returned | One processing step completed in call flow | Whether async/out-of-transaction effects finished |
| Broker ack/offset commit | Broker/consumer group recorded progress | Whether the claim was cleaned up on time |
| Claim deleted | Data removed from store on that path | Whether business still needs retries/audits/fan-out |

### 3.4. Typical failure windows

~~~mermaid
flowchart TD
    STORE["Store original message"] --> PUB{"Token publish succeeded?"}
    PUB -->|No| ORPHAN["Orphan claim / pending publish"]
    PUB -->|Yes| TAKE["Consumer receives token"]
    TAKE --> RET{"Claim retrieved?"}
    RET -->|No| MISSING["Missing / expired / unauthorized / store unavailable"]
    RET -->|Yes| PROCESS["Business handler"]
    PROCESS --> COMMIT{"Commit succeeded?"}
    COMMIT -->|No| RETRY["Retry/requeue, keep needed data"]
    COMMIT -->|Yes| ACK["Ack per broker/transport"]
    ACK --> CLEAN["Cleanup when all obligations end"]
    ORPHAN --> RECON["Outbox/reconciliation/garbage collection"]
    MISSING --> RECON
    RETRY --> PROCESS
~~~

**Golden rule:** Never delete data merely because **it was retrieved** if downstream can still fail. Depending on flow behavior, deleting right at Claim Check Out can leave every subsequent redelivery without a payload.

## 4. What Should a Claim Check Token Contain?

A good token should be **small, unguessable, payload-free**, easy to verify, and traceable; yet a token **never replaces authorization**.

### 4.1. Illustrative reference envelope

~~~json
{
  "claimId": "clm-lab-7e8d03ac",
  "claimSchemaVersion": 1,
  "sourceSystem": "partner-sftp-lab",
  "tenantId": "TENANT-LAB-01",
  "payloadKind": "ORDER_CSV",
  "contentType": "text/csv",
  "businessKey": "PARTNER-A/DOC-2026-0041",
  "contentVersion": 2,
  "sizeBytes": 83886080,
  "createdAt": "2026-11-23T10:00:00+07:00",
  "expiresAt": "2026-11-30T10:00:00+07:00",
  "checksumSha256": "<digest-redacted-for-example>"
}
~~~

This is an **application-designed extended contract**, **not the default payload** generated by Spring Integration's ClaimCheckInTransformer. Spring Integration's Claim Check In transformer typically puts **the stored message's ID** into the downstream message's payload; if you want an envelope carrying owner, tenant, expiry, and checksum, you need to add custom metadata/transformers in your flow.

### 4.2. Fields and responsibilities

| Field | Trusted source | Purpose |
| --- | --- | --- |
| claimId | Trusted store/producer | Looks up data; never serves as authorization proof on its own |
| tenantId | Identity/policy or verified source | Isolates data across tenants |
| sourceSystem | Connector configuration and principal | Audits data origin |
| businessKey | Producer contract | Idempotency and reconciliation |
| contentVersion | Schema/business version | Detects stale/overwrite issues |
| sizeBytes/contentType | From inspected data | Rejects oversized files, controls parsers |
| checksum | Computed after storing content | Verifies integrity upon retrieval |
| createdAt/expiresAt | Server and retention policy | Cleanup/TTL; never blindly raised by clients |
| owner/allowedConsumer | Internal registry or policy | Controls redeem authorization |
| traceId | Trusted tracing context | Correlates request, store, and consumer |

### 4.3. Should the token be an ID or a URL?

- **Opaque claim ID** (an ID revealing no sensitive info) fits when consumers fetch via a store service/adapter enforcing authorization.
- **Object key** in object storage can be stored internally; must prevent cross-tenant access or arbitrary object reads.
- **Time-limited signed URL** can be used in some download flows, yet the URL itself grants access during its validity window: avoid logging widely, bound TTL/scope, and address replay.
- **Local file path** works only when consumers share the exact same storage and security boundary; never portable across pods/servers automatically.

**Never put raw payloads, passwords, or access tokens into a claim token**. If anyone holding a claim ID can fetch contents without authorization, the token becomes a sensitive bearer credential and must be protected accordingly—better yet, enforce identity and authorization checks on redeem.

## 5. Store the Whole Message or Only Part of the Payload?

There are two main choices:

1. **Full-message Claim Check:** persists the Message including payload and headers in MessageStore; the token replaces content across intermediate steps. Spring Integration provides transformers for this style.
2. **Payload/object Claim Check:** stores large bytes in object storage or a dedicated repository, keeping a small metadata envelope. Downstream uses a handler/enricher to read the object and reconstruct required payloads/contracts.

### 5.1. Comparing the two styles

| Criterion | Full-message store | Object/payload store |
| --- | --- | --- |
| Stored data | Spring Message (payload + storable headers) | Blob/object bytes, separate metadata |
| Ease of ClaimCheckIn/Out integration | Can use built-in transformers | Usually requires custom adapters/transformers |
| Very large payloads | Limited by MessageStore serialization/blob/DB | Object storage usually fits large sizes better |
| Versioning | Must manage Java serialization/header compatibility | Can evolve object schemas/content versions independently |
| Security | MessageStore permissions and persisted headers | Bucket/object ACLs and redeem service |
| Cleanup | System-managed MessageStore remove/retention | Object lifecycle + metadata cleanup |
| Fan-out | One message ID readable by multiple branches | One object readable by many readers, shared retention |

### 5.2. Which headers should NOT be blindly stored or restored?

A Spring Message may contain **replyChannel, errorChannel, correlation, transport headers, tracing**, and sometimes live internal channel objects or non-serializable types. Never promise that every header can be serialized and safely restored across JVMs/brokers/restarts.

Specifically:

- An internal **replyChannel** is not a network address that can ship an object instance to another JVM.
- **HTTP/JMS/AMQP/Kafka headers** may hold adapter-specific routing, authentication, or type metadata.
- **SecurityContext/thread-locals** are not automatically restored from MessageStore; re-authenticate/re-authorize when the consumer executes.
- **Trace headers** should propagate properly without becoming client-controllable authorization signals.

### 5.3. When is Claim Check NOT worth using?

If payloads are just a few KB, channels/brokers handle them fine, and no routing steps need to avoid copying, adding a separate store introduces **a new failure point**, I/O, latency, TTLs, and security overhead. Claim Check pays off only when the savings from passing a **reference** outweigh the costs of storing, retrieving, backing up, and cleaning up.

## 6. Claim Check Components in Spring Integration

Spring Integration implements Claim Check via **transformers** collaborating with a **MessageStore**. Distinguish framework class names from the business state machine you design yourself.

### 6.1. Core components

| Component | Role | What to know |
| --- | --- | --- |
| **ClaimCheckInTransformer** | Saves original Message to MessageStore and outputs a claim-check message | Downstream payload is typically the stored message's ID |
| **ClaimCheckOutTransformer** | Uses claim ID to look up and restore original Message from store | Has keep/remove policies on retrieval; must pair with retry design |
| **MessageStore** | Abstraction to store, fetch, and delete Messages by ID | Does not include TTL, cross-broker transactions, or encryption by default |
| **SimpleMessageStore** | In-memory MessageStore suited for demos/tests | Not shared across JVMs and not durable across restarts |
| **JdbcMessageStore** | Database-backed MessageStore | Needs schema, transactions, serializers, data governance, and ops |
| **MessageChannel** | Channel carrying token or payload messages | A channel is not necessarily a persistent store |
| **Service Activator** | Business handler processing restored data | Must fulfill contract before cleanup |

**Important:** These component names belong to the Spring Integration ecosystem, yet constructor APIs, Java DSL helpers, XML attributes, and serialization details can vary across Spring Integration versions. In real applications, consult the exact Spring Integration reference/API for your dependency version rather than assuming one configuration applies verbatim everywhere.

### 6.2. Storage boundaries

~~~mermaid
flowchart LR
    S["File/HTTP/SFTP Inbound"] --> IN["ClaimCheckInTransformer"]
    IN --> STORE[("MessageStore")]
    IN --> TOKEN["Token-only MessageChannel"]
    TOKEN --> BROKER["JMS/AMQP/Kafka Adapter"]
    BROKER --> RECEIVE["Inbound Adapter"]
    RECEIVE --> OUT["ClaimCheckOutTransformer / Redeem Service"]
    STORE --> OUT
    OUT --> HANDLER["Business Handler"]
    HANDLER --> DB[("Business DB")]
    HANDLER --> GC["Cleanup Coordinator"]
    GC --> STORE
~~~

**Cross-JVM scenario:** if the consumer beyond the broker runs in another process, both sides must reach **the same shared store or claim API**, share token interpretation, and hold proper access rights. Declaring separate **SimpleMessageStore** instances in two JVMs does not create a shared store.

### 6.3. Conceptual MessageStore API

~~~text
addMessage(originalMessage)
    -> stores original Message keyed by its message headers ID

getMessage(messageId)
    -> reads original Message without deleting by default

removeMessage(messageId)
    -> fetches/deletes per store contract if permitted
~~~

With built-in claim-check transformers, you usually don't invoke these store methods manually in business handlers. Still, when designing retention, custom adapters, or debugging, remember **MessageStore holds the data**, while token messages are **the transport path**.

### 6.4. MessageStore vs. MessageGroupStore and ChannelMessageStore

Some Spring Integration components use **message group** stores for aggregators/resequencers or persist messages **in a persistent channel**. Those may use different interfaces and schemas than a single Claim Check message. Never assume declaring one MessageStore bean makes every QueueChannel, aggregator, and broker share the exact same store.

Separate responsibilities clearly:

- **Claim store** holds data redeemable by claim ID.
- **Message queue/store** manages ordering, acks, or work delivery.
- **Business DB** stores business outcomes.
- **Audit/metadata store** records publish, retrieve, completion, and cleanup states.

## 7. XML Configuration of Claim Check in a Spring Integration Flow

The following XML shows how to wire claim-check-in/out with a MessageStore inside **one application**. It is conceptual and close to Spring Integration namespaces; when copying into a project, declare compatible schemas/versions and apply your environment's storage policies.

### 7.1. A two-stage in-JVM flow

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/integration
           https://www.springframework.org/schema/integration/spring-integration.xsd">

    <!-- Demo only: store in memory, not durable across restarts. -->
    <bean id="claimMessageStore"
          class="org.springframework.integration.store.SimpleMessageStore"/>

    <int:channel id="largeMessages"/>
    <int:channel id="claimTokens"/>
    <int:channel id="restoredMessages"/>

    <int:claim-check-in
        input-channel="largeMessages"
        output-channel="claimTokens"
        message-store="claimMessageStore"/>

    <int:claim-check-out
        input-channel="claimTokens"
        output-channel="restoredMessages"
        message-store="claimMessageStore"
        remove-message="false"/>
</beans>
~~~

With this configuration, messages sent to **largeMessages** become **claim-check messages**. To keep the example self-contained end-to-end, **claimTokens** connects directly to the restore step. In real designs, you would insert routers, outbound adapters, or brokers there—which requires **shared stores, compatible serialization, and ack/cleanup design**.

**Note on `remove-message`:** keeping the original message upon redeem lets you practice retries without losing data. Enabling automatic removal upon checkout can delete data **before downstream business commit**; verify the entire flow before turning it on. Check exact attribute names and defaults for your Spring Integration version.

### 7.2. When NOT to just chain channels directly

The example above is for learning. In real projects passing tokens over a broker:

~~~text
Producer JVM:
  HTTP/File/SFTP inbound
      → Claim Check In (shared store)
      → token channel
      → JMS/AMQP/Kafka outbound adapter

Consumer JVM:
  JMS/AMQP/Kafka inbound adapter
      → token validation/authorization
      → Claim Check Out (same shared store)
      → business handler
      → acknowledge/commit per contract
      → cleanup coordinator
~~~

**Never** place ClaimCheckOutTransformer on the producer thinking a token crossed the broker, or leave the original binary in another header causing the message to still exceed size limits. Verify **actual bytes on the wire** carry only small metadata.

### 7.3. Why NOT enable delete-on-read before designing retries?

Suppose a consumer checks out a claim, the transformer **deletes the original immediately**, and then the handler hits a DB timeout. The broker may redeliver the token, but the store no longer has the original message. The result is an **unrecoverable job under normal retries**.

A safer policy in many cases:

1. Claim Check Out **reads without deleting**.
2. Handler validates and commits business state.
3. Broker ack/offset commits as appropriate.
4. Claim transitions to cleanup-eligible once no consumers/obligations still need the data.
5. GC deletes per retention/safety window with auditing.

This **does not create an atomic transaction across broker and store**; handle crashes and reconciliation as covered in later sections.

## 8. Java 17: Using MessageStore to Understand Claim Check

This mini-lab uses **SimpleMessageStore**, MessageBuilder, and `MessageHeaders.ID` to clearly inspect store and retrieval steps. It is **not** a production Spring Boot app and has no security, TTL, or broker.

### 8.1. Snippet illustrating the store API

~~~java
import java.util.UUID;

import org.springframework.integration.store.MessageStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class ClaimStoreLab {

    public static void main(String[] args) {
        MessageStore store = new SimpleMessageStore();

        Message<String> original = MessageBuilder
                .withPayload("large-payload-placeholder")
                .setHeader("businessKey", "DOC-LAB-0041")
                .build();

        // Store a Message; the original MessageHeaders ID is its lookup key.
        store.addMessage(original);
        UUID claimId = original.getHeaders().getId();

        // Token travels separately; for demonstration use a UUID value.
        System.out.println("Claim token: " + claimId);

        Message<?> restored = store.getMessage(claimId);
        if (restored == null) {
            throw new IllegalStateException("Missing claim");
        }
        System.out.println("Restored: " + restored.getPayload());

        // Cleanup only after an explicitly verified completion in real flows.
        store.removeMessage(claimId);
        System.out.println("After cleanup: " + store.getMessage(claimId));
    }
}
~~~

Running this in a project with compatible **spring-integration-core** prints a lookup ID, restores the payload, and returns null after removal. This is a **store API** experiment—without an actual ClaimCheckInTransformer or MessageChannel transporting tokens.

### 8.2. From API experiment to framework transformers

Real Claim Check In/Out flows should use Spring Integration's transformers when they fit. Conceptually:

~~~text
ClaimCheckInTransformer:
  original Message
    → MessageStore.addMessage(...)
    → Message whose payload is the claim ID

ClaimCheckOutTransformer:
  Message with claim ID payload
    → MessageStore.getMessage(...)
    → restored original Message
    → optionally removes stored message per configuration
~~~

This is a logical diagram, not a guarantee that every header or data type shares identical shapes across all versions. Custom transformers must explicitly define **header propagation, ID canonicalization, error behavior, and retention**; never replace built-in implementations with a few lines of code while omitting those aspects.

### 8.3. Limitations of SimpleMessageStore

- **Data lives in RAM**, vanishes on application stop, and is not shared across pods.
- Unsuitable for large volumes of 80 MB files without a memory budget.
- Lacks encryption at rest, backups, or retention policies of a durable store.
- Two instances creating SimpleMessageStore get **two independent ID sets**.
- Cannot pass tokens over Kafka/JMS and redeem from another process.

This experiment only teaches the **message store API**; it does not prove cross-service durability.

## 9. Durable MessageStore and External Object Storage

### 9.1. When choosing JdbcMessageStore

A **JdbcMessageStore** stores messages in a relational database, fitting flows needing restart/recovery. However:

| Aspect | Must be defined |
| --- | --- |
| Schema/tables | Create schema compatible with your Spring Integration and DB versions |
| Serialization | Payload/headers remain serializable and compatible across Java/class upgrades |
| Transactions | When do add/get/remove commit? Which transaction do they join? |
| Capacity | BLOB/table growth, indexes, backups, vacuum/maintenance |
| Connection pool | Claim-in/out rate, concurrency, and DB saturation |
| Security | Least-privilege DB user, encryption, backup governance |
| Expiry/cleanup | Who deletes per retention; is it safe for checkpoints/fan-out? |
| Availability | What do producers/consumers do when the DB is temporarily offline? |

**Do not treat JdbcMessageStore as infinite object storage**. If each message is a video or multi-GB dataset, serializing entire Messages into the DB causes bottlenecks, heavy backups, and serialization breakage across releases.

### 9.2. Storing large objects externally

For large files/binaries, an alternative design stores payloads in **object storage or a shared durable file repository**, using a metadata store for claim ID, object key, owner, size, checksum, TTL, and status.

~~~mermaid
flowchart LR
    IN["HTTP/SFTP/File inbound"] --> OBJ["Upload immutable object"]
    OBJ --> BLOB[("Shared Object Storage")]
    OBJ --> META[("Claim Metadata DB")]
    META --> TOKEN["Claim Reference"]
    TOKEN --> BROKER["Broker / MessageChannel"]
    BROKER --> AUTH["Validate claim + caller"]
    AUTH --> META
    AUTH --> FETCH["Fetch + checksum verify"]
    BLOB --> FETCH
    FETCH --> BIZ["Business processing"]
    BIZ --> CLEAN["Retention / Cleanup"]
    CLEAN --> BLOB
    CLEAN --> META
~~~

**Note:** This is a custom-designed Claim Check implementation—configuring ClaimCheckInTransformer with JdbcMessageStore **does not automatically give you an object storage bucket**. You must build the service/adapters managing object keys, storage permissions, metadata, streaming, and cleanup.

### 9.3. Ensuring the object is complete before publishing the token

When uploading payloads:

1. Receive data into a **staging** area; enforce content-length limits, type checks, and anti-malware scans per policy.
2. Write the complete object; verify checksum/size and durable write per storage contract.
3. Persist claim metadata with status AVAILABLE and an immutable object key.
4. Publish the token only after both object and metadata are truly ready.
5. If publishing fails, keep a pending/outbox record to retry rather than dropping the intent to emit the token.

Never publish a token pointing to a partially uploaded file. With remote object storage, understand provider semantics for object visibility, multipart uploads, and final object publication.

### 9.4. Immutable objects and content versions

Avoid overwriting the same object key while a token may still be redeemed by consumers. Each claim ID should point to an **immutable or versioned content revision** so retries with the same token never return two different payloads. When data must change, create a new version/claim with clear business linkage.

### 9.5. Checksums verify integrity, not source authenticity

SHA-256 detects changed bytes after storage/transit. However, if an attacker can tamper with both payload **and** unprotected metadata checksums, checksums provide no security guarantee. Combine metadata write controls, trusted origins, object integrity, and auditing. Highly sensitive content may need signatures or MACs per threat model.

## 10. Integrating Claim Check with Each Adapter and Protocol

Claim Check solves **passing references** without changing the delivery nature of the source adapter. File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC differ sharply in data detection, acks, access rights, and timeouts.

### 10.1. File inbound adapter

~~~text
Shared folder / incoming file
    → File inbound MessageSource is polled
    → verify file ready + schema
    → store content in claim store
    → emit claim token to MessageChannel/broker
    → downstream receives token, fetches data, processes
    → archive/delete source per completion policy
~~~

If files already sit on a **shared durable filesystem** readable by all consumers, tokens may reference an object/path there, subject to path-traversal checks, permissions, and overwrite/delete hazards. **Producer local paths do not automatically exist inside consumer containers**.

**Do not mark files processed immediately at claim-in** if the token hasn't been published and processed yet; if you must, use an outbox/reconciliation to ensure the pipeline continues.

### 10.2. SFTP inbound/streaming adapter

SFTP suits large files, with two phases to separate:

1. **Download from SFTP to staging/object store:** finish transfer, verify size/checksum or marker per producer contract.
2. **Publish processing token:** only once data is complete and readable wherever consumers run.

SFTP streaming adapters allow reading streams rather than local copies, yet require managing **session/stream lifecycles**. Serializing an open `InputStream` or file handle into a MessageStore fails after restarts or in another JVM. Persist **durable bytes/objects** and metadata, passing only the token.

### 10.3. HTTP inbound gateway and outbound gateway

With HTTP:

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant IG as HTTP Inbound Gateway
    participant S as Storage Service
    participant MQ as Work Broker
    participant W as Worker
    C->>IG: Upload content
    IG->>S: Store complete object + metadata
    S-->>IG: claimId
    IG->>MQ: Publish reference
    IG-->>C: 202 Accepted + jobId
    MQ->>W: Deliver reference
    W->>S: Authorized redeem
    S-->>W: Content
    W->>W: Validate + business commit
~~~

For large uploads:

- Enforce request size limits, streaming/multipart, and upload timeouts.
- Avoid buffering entire binaries in heap just because an HTTP converter produces `byte[]`.
- If an HTTP client retries uploads after timeout, use idempotency keys or job state to avoid duplicate objects and duplicate work.
- **HTTP 202 Accepted** must explicitly reflect what was durably stored. Creating a token in RAM and returning 202 is insufficient if recoverability is required.
- When an HTTP outbound gateway calls another service with a token, clarify whether that service expects a **fetch URL** or raw binary. A service unaware of Claim Check won't understand `claimId`.

### 10.4. JMS Queue

JMS is well suited to distributing **work tokens** rather than huge binary messages:

~~~text
ClaimCheckIn + shared store
   → JMS outbound adapter (payload = claim token)
   → durable queue per configuration
   → JMS message-driven inbound adapter
   → ClaimCheckOut/redeem
   → idempotent handler
   → broker acknowledgment per container/transaction
~~~

Design points:

- Tokens are held/redelivered by the broker per JMS contract; this **does not automatically protect data in the claim store**.
- JMS listener timeouts or crashes can redeliver a token.
- Do not delete data as soon as the listener receives the token if handlers may still retry.
- The message store and JMS broker are **two distinct resources** with no default atomic transaction.
- If a durable message survives past claim TTL, broker redelivery hits a **missing claim**.

### 10.5. AMQP/RabbitMQ Queue

RabbitMQ incurs limits and overhead on huge messages; claim references keep the broker lightweight. However:

- **Prefetch** can hold many unacked tokens on one worker; if each claim loads hundreds of MB, total I/O/storage concurrency can explode despite small broker messages.
- Ack/nack/requeue must align with **business commit** or a designed durable handoff.
- Dead-letter queues hold **tokens**, not necessarily original payloads. You cannot replay a DLQ if claims were deleted before triage.
- With fan-out across multiple queues, every subscription may need to redeem the same payload. Cleanup must wait for all obligations or use **separate claims/references**.

### 10.6. Kafka topic

Kafka is a partitioned log. Instead of putting large binaries into records, publish small **claim envelopes** to the topic:

~~~json
{
  "eventId": "EVT-LAB-0119",
  "eventType": "DocumentReady",
  "claimId": "clm-lab-7e8d03ac",
  "tenantId": "TENANT-LAB-01",
  "documentVersion": 2
}
~~~

**Kafka specifics:** records can be re-read from older offsets, retained for long periods, and consumed by multiple **consumer groups** at different times. Deleting a claim when group A finishes can leave group B or historical replays without data.

Define:

1. **How many consumer groups** need the payload, and for how long?
2. Does claim retention match broker/topic retention and replay requirements?
3. Should originals be kept longer, or can they be snapshotted/rebuilt from the source?
4. When offsets commit, has business commit actually completed?
5. Could high consumer lag expire claims before they are even read?
6. If a new consumer group starts from an old offset, how is authorization handled for redeeming older claims?

The **Kafka consumer client poll** beneath the listener does not turn Claim Check into a QueueChannel PollingConsumer; a Kafka message-driven inbound adapter still receives records from its listener container.

### 10.7. JDBC/database

Databases can play **two separate roles**:

- **Claim storage:** `JdbcMessageStore` or a claim metadata table holding data/references.
- **Business storage/outbox:** domain tables plus outbox/processed inbox rows ensuring results and token emission intent.

Do not cram all states into one table with an ambiguous status column. If the DB stores large objects, plan BLOB schemas, backups, and size caps. If the DB stores only object keys, ensure **consistency between object store and metadata DB**.

### 10.8. Integration selection table

| Source/transport | Where is the claim stored? | What to guard against |
| --- | --- | --- |
| File → JMS | Shared object/DB store | Incomplete files, token publish failures |
| SFTP → AMQP | Durable shared store | Session errors, duplicate downloads, DLQ payload loss |
| HTTP → Kafka | Object store + metadata | Client retries, consumer lag, multi-group replay |
| JDBC outbox → broker | Shared claim store/outbox | Crash between persist and publish, duplicate tokens |
| In-JVM QueueChannel | SimpleMessageStore works for labs | Restarts losing claims, memory pressure |
| HTTP gateway → remote processor | Object store or raw payload if required | Unauthorized redeems, timeouts/unknown effects |

## 11. Atomicity: Storing Payloads and Publishing Tokens Are Not One Operation

This is the top reliability challenge in Claim Check. Saving payloads to a DB/object store and publishing tokens to JMS/AMQP/Kafka **usually hit two independent systems**.

### 11.1. Four failure windows

| Window | What happens | Consequence without recovery |
| --- | --- | --- |
| **A: store OK → publish not run** | Process dies after saving claim | Orphan claim; work never runs |
| **B: publish OK → producer ACK lost** | Unclear if broker got token | Re-publishing may create duplicate token deliveries |
| **C: token reaches consumer → store unreachable** | DB/network/auth error or data not AVAILABLE | Work stalls, retries, or hits DLQ |
| **D: business commit OK → cleanup not run** | Consumer dies before marking/deleting claim | Lingering data in store, wasted cost |

Never resolve window A by **immediately deleting the claim when publish fails** if there is any chance the broker actually received the token. Use state/correlation to reconcile and design idempotent retries.

### 11.2. Claim + Outbox in the same DB

If original messages, claim metadata, and outbox records are saved in **one DB transaction under a shared TransactionManager**:

~~~text
BEGIN TRANSACTION
    insert stored payload / claim metadata
    insert outbox event {claimId, messageType, tenant}
COMMIT

Outbox relay:
    read pending event
    publish claim token to broker
    mark outbox sent (with retry)
~~~

If the relay publishes successfully and dies before marking sent, it may publish **the same claimId/eventId again**. Consumers must be idempotent. If object storage lives outside the DB, the DB transaction is not atomic with object uploads; use PREPARED/AVAILABLE states plus garbage collection.

### 11.3. Never use try/catch as a distributed transaction

~~~text
try:
    store.save(payload)
    broker.publish(token)
catch:
    store.delete(payload)
~~~

This is **unsafe** if the broker received the token while the ack response was lost. Deleting leaves the consumer holding an unredeemable token. Use **outbox, idempotent publishing, retries, and reconciliation** instead of relying on API call order inside a try/catch.

### 11.4. When can a transaction manager help?

Depending on JDBC, JMS, and transaction setup, some components can join coordinated transactions within specific scopes. Still, there is **no default** atomic transaction spanning SFTP, HTTP, object storage, Kafka, and DB. Even with transaction advice on pollers, verify which sources/targets truly participate and how recovery works per contract.

### 11.5. Suggested metadata states

~~~text
PREPARING
  → AVAILABLE
  → PUBLISHED
  → IN_USE
  → COMPLETED
  → ELIGIBLE_FOR_CLEANUP
  → DELETED

  Possible branches: PUBLISH_RETRY, RETRIEVE_RETRY,
                     QUARANTINED, ORPHAN_CANDIDATE
~~~

**This is an application state machine**, not a built-in Spring Integration enum. Define what **COMPLETED** means in terms of consumer counts/subscriptions and business outcomes, especially when a claim serves multiple groups.

## 12. Retries, Duplicate Tokens, and Business Idempotency

### 12.1. Two different kinds of duplicates

- **Duplicate token delivery:** the same claimId appears multiple times on the broker or is replayed.
- **Duplicate business command:** two different claimIds carry the exact same business operation.

Deduplicating solely by claimId allows the second kind to repeat side effects. Use proper business keys and, when needed, verify payload hashes/versions.

### 12.2. Safe consumer handling on token receipt

~~~text
consume(token):
    validateSourceAndTenant(token)
    metadata = loadClaimMetadata(token.claimId)
    authorizeConsumerForClaim(metadata)
    require(metadata.status == AVAILABLE or permitted equivalent)

    payload = fetchClaimContent(metadata)
    verifySizeChecksumSchema(payload, metadata)

    with businessTransaction:
        if processedInbox.exists(consumerName, businessKey):
            return ALREADY_COMPLETED
        processIdempotently(payload)
        processedInbox.insert(consumerName, businessKey, resultRef)
        commit

    acknowledgeTransportAccordingToContract()
    recordClaimConsumerCompletion(token.claimId, consumerName)
    cleanupLaterWhenSafe()
~~~

This pseudocode **does not** replace locking/unique constraints, transaction isolation, exception mapping, or adapter ack mechanics. **Never** delete claims inside a `finally` block lest failures destroy retry data.

### 12.3. Retry policy by error category

| Error | Example | Action |
| --- | --- | --- |
| **Store temporarily offline** | JDBC timeout / HTTP 503 from claim service | Retry/backoff; no false success ack |
| **Claim not yet AVAILABLE** | Object upload uncommitted | Bounded wait/retry; investigate publish-before-ready |
| **Claim missing** | Bad token, premature delete, expired TTL | Classify data loss, quarantine/escalate |
| **Wrong tenant/unauthorized** | Consumer accesses out-of-scope claim | Reject and audit; do not retry to bypass controls |
| **Checksum mismatch** | Object altered/corrupted | Quarantine; never process untrusted bytes |
| **Schema invalid** | CSV/JSON violates contract | DLQ/quarantine; no infinite retries |
| **Business transient** | Target DB unreachable | Retry/idempotency; retain claim |
| **Business permanent** | Command violates domain rules | Clear outcome; retain per policy |
| **Cleanup failure** | Object delete API timeout | Retry cleanup independently; do not flip business state to FAILED |

### 12.4. DLQs hold tokens, not raw payloads

If a poison message enters the DLQ on day two while the claim expired/deleted on day one, operators cannot inspect or replay the data. Therefore **claim retention** must cover **queue backlog, retry windows, DLQ dwell time, and incident triage windows**.

For sensitive data requiring early deletion, you cannot simply extend TTLs forever for debugging convenience; balance retention policies, alternative replay paths, or retaining permitted audit metadata without full payloads.

### 12.5. When one token fans out

~~~mermaid
flowchart TD
    CLAIM["Claim ID C1"] --> TOPIC["Kafka topic / AMQP exchange"]
    TOPIC --> BILL["Billing group/queue"]
    TOPIC --> ANALYTICS["Analytics group/queue"]
    TOPIC --> SEARCH["Search index group/queue"]
    BILL --> STORE[("Shared Claim Store")]
    ANALYTICS --> STORE
    SEARCH --> STORE
~~~

**Wrong:** Billing redeems and deletes the claim immediately; Analytics receives the token later with no content left.

**Right:** use policies tracking required subscribers, consumer-specific completion markers, TTL/safety windows, or **separate claims** if each branch needs independent lifecycles. For Kafka, new consumer groups/historical replays are special cases: explicitly document **historical replay limits** of claims.

## 13. Concurrency and Claim Check in Competing Consumers

Claim Check frequently pairs with Competing Consumers to distribute lightweight tokens over brokers while large data stays in storage. More workers mean **higher concurrent access to the claim store**.

### 13.1. Can one token be delivered to two workers?

In standard queues, one delivery goes to one consumer, yet ack failures, session timeouts, or worker crashes can redeliver a token to another worker. If consumer A is still processing slowly when B receives it, **both can access the claim simultaneously**.

With **destructive get/delete** on first redeem, B fails to read. Keeping the claim lets both read; **business idempotency/concurrency** must protect side effects. Never use delete-on-read as a business lock without proper atomic contracts.

### 13.2. Strategies

| Strategy | Best fit | Limitation |
| --- | --- | --- |
| **Read-only shared claim** | Immutable payload, multiple readers/retries | Requires TTL/cleanup and business idempotency |
| **One-time redeem** | Single-shot work needing no retries/fan-out | Easily loses retry capability if deleted early |
| **Claim lease** | Tracking which worker holds work | Lease expiry creates concurrency; needs fencing |
| **Per-subscriber completion** | Multi-domain fan-out | Must know required subscriptions and retention |
| **Separate claims** | Independent consumer lifecycles | Extra storage overhead and reference tracking |

### 13.3. In-JVM QueueChannel

If a **QueueChannel** carries claim IDs and multiple **PollingConsumers** pull from it, popping a message from the queue **does not mean** the store payload was processed. In-memory QueueChannel offers no durable ack/retry. Critical workloads need durable brokers/message stores or explicit recovery/claim mechanisms.

### 13.4. Kafka partition ordering does not protect claim lifecycles

Kafka preserves per-partition record order per contract, yet two claim references can point to **the same object version or two versions**. Handlers still need **business version** checks; never let a late-redeemed claim overwrite newer state with stale data.

## 14. Securing Claim Check: Tokens Are Not Licenses to Read Data

A Claim Check design keeps **sensitive payloads off the broker**, yet introduces **an API fetching data by claimId**. Allowing any caller with an ID to fetch contents creates a BOLA/IDOR (Broken Object Level Authorization) vulnerability.

### 14.1. Assets to protect

| Asset | Risk | Controls |
| --- | --- | --- |
| Claim token | Read from logs or broker messages | Unguessable IDs, redaction, queue/topic ACLs |
| Claim metadata | Tampered tenant/owner/expiry/object key | Strict write ACLs, auditing, immutable fields |
| Payload in store | Unauthorized reads or byte tampering | Authentication, authorization, encryption, checksums |
| Service credentials | Abused to download all objects | Least privilege, rotation, never inside messages |
| Object URLs | Forwarded or reused beyond scope | Short TTL/scope, governed signed URL policies |
| File paths | Path traversal or reading arbitrary files | Path canonicalization/allowlists; never trust paths in tokens |
| Original Message headers | Carry reply channels, identities, or secrets | Header filtering, serialization policies |
| Audit/debug logs | Expose raw payloads or sensitive claim keys | Redaction and appropriate retention |

### 14.2. Secure redeem workflow

~~~text
receive(token):
  authenticateConsumerService()
  validateTokenShapeAndVersion(token)
  metadata = trustedClaimRegistry.lookup(token.claimId)
  require(metadata.tenantId == authorizedTenantContext)
  authorize(consumerIdentity, metadata.allowedOperations)
  require(claimNotExpiredOrExplicitlyRetained(metadata))
  require(metadata.status in allowedStates)
  streamObjectFromTrustedKey(metadata.objectKey)
  verifyPayloadIntegrityAndSchema()
  logSafeAuditEvent()
~~~

**Never take tenant or allowedOperations solely from an unverified JSON token.** Token fields serve routing/observability; access decisions must rely on authenticated identity and trusted metadata.

### 14.3. Opaque IDs still carry risk

Random UUIDs are harder to guess than sequential IDs, yet still leak in:

- Broker topics readable by multiple applications.
- HTTP access logs, exception traces, or message headers.
- DLQ dashboards, centralized logs, support tickets.
- Emails/chats containing debug links.
- Application metrics if claimId is used as a label.

Thus, **unguessability does not replace authorization**. For highly sensitive claims, pass minimal references and never allow unauthenticated object reads by claimId.

### 14.4. Encryption and key lifecycles

- **Encryption in transit:** TLS when calling object stores, DBs, HTTP APIs, or brokers where required.
- **Encryption at rest:** aligned with data classification; remember backups and snapshots must also be protected.
- **Key rotation:** design version/key IDs so still-valid retention data remains readable during rotation.
- **Data deletion:** deletion requests must cover objects, metadata, caches, backups, fan-out copies, and DLQs per policy.
- **Secret management:** never embed SFTP passwords, DB passwords, or cloud secrets inside ClaimReference.

### 14.5. Untrusted files and parsers

Files from SFTP/HTTP may be huge, malformed, zip-bombed, or carry malicious payloads. Claim Check does not sanitize data. Enforce:

1. Content length and max expanded size on decompression.
2. Actual content type, file extension, and schema checks.
3. Parser time/memory limits.
4. Antivirus/malware scanning if required by threat model.
5. Quarantine for data failing safety checks.
6. Filesystem/temp-file permissions and staging cleanup.

### 14.6. Auditing without exposing content

Audits should log **restricted claimId references, consumer identity, verified tenant, action STORE/REDEEM/DELETE, timestamp, outcome, and correlation/trace ID**. If claim IDs themselves grant direct access, hash/redact IDs in standard logs and restrict full lookup to a dedicated audit store.

## 15. TTL, Retention, and Garbage Collection

A stored claim that is never deleted becomes **lingering data waste**. A claim deleted too early breaks downstream retries. Design the lifecycle upfront.

### 15.1. Mental model for retention duration

~~~text
requiredRetention >=
  expectedQueueWait
  + maximumProcessingAndRetryWindow
  + incidentReviewOrDLQReplayWindow
  + safetyMargin
~~~

This is a **design relationship**, not a rigid SLA formula. With multiple consumer groups or multi-month Kafka replay, retention must cover the **longest-dependent group** or support rebuilding from origin—while never exceeding legal/data-deletion limits.

### 15.2. Four questions before deleting

1. Has **business completion** been verified?
2. Are there **pending tokens, retries, unacked messages, or DLQ entries** still needing the claim?
3. Do **other subscribers/groups** still need to redeem the content?
4. Is there a **retention/audit/legal hold** requiring keeping or purging within a specific timeframe?

Never adopt “claim fetched once → delete immediately” as a blanket rule, because retrieval and successful processing are two distinct events.

### 15.3. Reference cleanup state set

| State | Condition | Action |
| --- | --- | --- |
| **AVAILABLE** | Payload fully persisted | Authorized consumers can redeem |
| **PUBLISH_PENDING** | Data ready, token publish unconfirmed | Retry/outbox; do not delete early |
| **IN_USE** | One or more consumers processing | Track leases/attempts; do not delete blindly |
| **COMPLETED** | Business obligations met per contract | Evaluate retention and related groups |
| **CLEANUP_ELIGIBLE** | No dependencies left, no holds, past safe window | Hand off to deletion job |
| **DELETING** | Deleting object/metadata | Idempotent retry on failure |
| **DELETED** | Deletion verified within scope | Minimal deletion audit marker |
| **ORPHAN_CANDIDATE** | Stored data lacks valid work path past threshold | Reconcile before deleting |

A basic `MessageStore` **does not have to provide these states**; they are suggestions for application metadata/claim services managing complex flows.

### 15.4. Garbage collectors must never guess

A scheduled GC job can look for:

- Claims COMMITTED/ACKED past retention.
- Claims stuck **PREPARED/PUBLISH_PENDING** too long, requiring outbox/broker reconciliation.
- Claims missing metadata or metadata missing objects.
- Tokens still in DLQ whose objects are nearing expiration.
- Superseded object versions no consumer still needs.

A GC job must:

- Delete only when criteria are verified **from a trusted source**.
- Enforce batch limits, rate limits, and retries.
- Audit counts checked/deleted/skipped and reasons.
- Support dry-run/report mode during initial rollout.
- Never undercut committed consumer replay windows.

### 15.5. Object deletion and metadata deletion are not atomic

If object storage deletes cleanly while DB metadata update fails, deletion retries should treat missing objects as **already satisfied** if allowed by contract. If DB metadata deletes first while the object remains, **orphan objects** accumulate without audit/cleanup trails. Choose ordering, `DELETING` states, and reconciliation to avoid losing track.

### 15.6. GDPR/retention is more than changing a TTL

Privacy policies may require deletion per user/data subject/tenant or bounded retention. Claim Check can multiply copies across payloads, caches, logs, backups, and DLQs. Maintain a **data inventory** covering every storage location, not just MessageStore rows.

## 16. Performance Cost, Streaming, and Backpressure

Claim Check reduces broker traffic while adding **one write and one read** of the data—or more with retries/fan-out.

### 16.1. Simple estimation

Suppose files are **80 MiB** each at **100 files/hour**:

~~~text
Input bytes ≈ 80 MiB × 100 = 8,000 MiB / hour

Without Claim Check, one or more transport hops may carry
most of that payload along the integration path.

With Claim Check, the broker mainly carries tiny tokens; the object store
writes ~8,000 MiB/hour and reads at least that much if each file
is consumed once.
~~~

If three consumer groups each redeem full content, **total read throughput** is roughly three times input volume before retries. Thus Claim Check does not make total I/O bytes disappear; it **relocates where load lands**.

### 16.2. Common bottlenecks

| Component | Symptom | Measure |
| --- | --- | --- |
| Claim-in storage | High upload latency, full connection pools | Streaming, bounded concurrency, storage tuning |
| Broker | Oversized messages/poor throughput | Tiny tokens, bounded headers |
| Claim-out store | Too many readers, 429/503, DB locks | Read concurrency caps, controlled caching |
| Consumer heap | Huge byte arrays, OOM | Stream/chunk files, lower concurrency |
| Disk staging | Uncleaned temp files, full disk | Cleanup, quotas, monitoring |
| Metadata DB | Slow claim lookup/cleanup | Indexes, batched GC, avoid hot rows |
| Security scanning | High CPU/time on large files | Bounded pipelines, scheduling, timeouts |

### 16.3. Does streaming truly solve memory?

Streaming avoids holding entire objects in a single `byte[]`, yet:

- Streams must close cleanly on success and failure.
- Retries usually require **opening a fresh stream** from object storage; exhausted InputStreams cannot be reused.
- Data validation/checksums may need chunk-by-chunk computation.
- Multipart uploads/downloads have chunk boundaries and custom resume logic.
- Consumers may need streaming parsers or durable staging.

Never send an `InputStream` object over JMS/Kafka expecting the other side to read it. Transports carry **references**, and consumers open streams at redeem time.

### 16.4. Bounded concurrency

If each consumer opens an 80 MiB file and 20 run concurrently, I/O, heap, disk, parser, and store connection pressure spikes. Throttle both layers:

1. **Dispatched work tokens** (broker prefetch, listener concurrency, QueueChannel capacity).
2. **Large payloads actively redeemed/processed** (separate semaphores/bulkheads).

Optimal concurrency depends on file sizes, store throughput, parse CPU, and sink speed. Never spin up 100 workers merely because broker tokens are tiny.

### 16.5. Caching claim content?

Caching cuts repeated reads at the cost of extra sensitive data copies and staleness risks:

- Cache keys need claim ID **plus version/tenant** per contract.
- Never cache sensitive content unbounded in RAM.
- Enforce TTLs and eviction policies.
- Prevent consumers from reading stale data if object keys get overwritten.
- Account for every cache inside data retention/privacy scopes.

## 17. Startup, Shutdown, and Claim Store Lifecycle

### 17.1. Startup

- [ ] Shared MessageStore or object store is ready before taking work needing redeems.
- [ ] Producers/consumers agree on claim ID contracts, schemas, serializers, and object versions.
- [ ] Read/write/delete permissions are separated by service role.
- [ ] Metadata/claim registries have current-version migrations/indexes.
- [ ] Health checks verify **store lookup/write/read** rather than just TCP pings.
- [ ] If tokens survive in the broker across restarts, the store retains their corresponding claims.
- [ ] TTL/cleanup jobs are configured without prematurely deleting pending work.
- [ ] Dev/test environments never accidentally point to production stores/queues.

### 17.2. Graceful shutdown

~~~text
Stop accepting new tokens
    ↓
Allow consumers currently redeeming/processing to finish within grace window
    ↓
Commit or roll back/let broker redeliver per contract
    ↓
Close input streams, temp files, and connections
    ↓
Leave claims intact if work is not truly complete
    ↓
Shut down service/container
~~~

If a process is killed between business commit and broker ack, tokens may redeliver. Business idempotency blocks duplicate effects; claim data must outlive retries. If **cleanup runs independently**, it must observe in-flight/retry status rather than relying solely on the last GET timestamp.

### 17.3. Rolling deploys and schema evolution

During rolling deployments, new producers may talk to old consumers or vice versa. Claim metadata, object serialization, and payload schemas need **version/capability strategies** so both sides stay compatible through the rollout window. Notably, Java object serialization via `JdbcMessageStore` breaks easily across class/package/`serialVersionUID` changes; prefer stable versioned payload schemas or explicit migrations.

### 17.4. Store/region failover

When the primary store disconnects:

- Consumers must never treat **missing due to outage** as genuinely nonexistent data.
- Apply retry with backoff, circuit breakers, and alerts.
- Never ack tokens as successful if business criteria weren't met.
- If failing over to a replica, verify consistency/replication lag and object versions.
- Never mint an unrelated new claim ID when retrying the same job.

### 17.5. Broker availability alone is not enough

The broker may run flawlessly and deliver tokens immediately while the claim store is unreachable. Health dashboards must evaluate **end-to-end** from token through payload retrieval to business commit—not just queue depth or connected consumers.

## 18. Observability: Measuring Both Tokens and Content

A dashboard showing only **broker messages published/consumed** misses many Claim Check failures. Separate metrics across **transport**, **claim store**, and **business processing**.

### 18.1. Metrics to watch

| Metric | Meaning | Anomaly signal |
| --- | --- | --- |
| **claims stored** | Objects/messages persisted successfully | Store accepts many yet broker doesn't publish |
| **claim bytes stored** | Total bytes written to store | Rapid growth, quota/backup overload risk |
| **claim publish pending** | Claims ready with unconfirmed token publish | Stalled outbox/relay, orphan candidates |
| **tokens published** | Tokens accepted by broker per contract | Large gap vs. claims stored |
| **tokens delivered** | Tokens handed to consumers | Can rise during redelivery |
| **claim redeem success** | Successful valid content fetches | Proves retrieval only, not business commit |
| **claim redeem denied** | Blocked by authn/authz | Misconfigured service role or abuse |
| **claim missing/expired** | Not found or expired token | Premature deletion, wrong store, bad TTL |
| **checksum mismatch** | Retrieved bytes differ from metadata | Corruption, overwrite, or tampering |
| **business commit success** | Completed business units | Flat despite high token consumption |
| **duplicate business suppressed** | Dedupe blocked repeat side effects | Spikes after restarts/rebalances |
| **oldest unprocessed token age** | Delay of oldest pending job | Exceeds business SLA |
| **DLQ pending/age** | Tokens awaiting human triage | Tokens nearing expiry before triage |
| **orphan claim count/bytes** | Stored data lacking valid publish/replay paths | Stalled cleanup or lost outbox |
| **cleanup eligible/deleted** | Eligible claims and actual deletions | Eligible rising while deletes stall |
| **store latency P50/P95/P99** | Object/DB read/write latency | Store bottleneck/overload |
| **active redeem streams** | Concurrent active downloads/streams | I/O and memory pressure |

Group metrics by **flow, source, target, type, environment**, and error; avoid putting raw claimIds or businessKeys into metric labels due to high cardinality and leak risks.

### 18.2. Cross-system trace

~~~text
traceId=TRACE-LAB-47
  span A: sftp.receive         → 2.1 s
  span B: claim.store          → 1.7 s
  span C: broker.publish       → 0.08 s
  span D: broker.wait          → 0.9 s
  span E: claim.redeem         → 1.4 s
  span F: business.validate    → 0.12 s
  span G: database.commit      → 0.25 s
  span H: claim.cleanup        → async later
~~~

This is a simulated trace. Cross-broker correlation requires propagating controlled **trace context**, not serializing raw thread-locals. `broker.wait` relies on trusted timestamps; clocks across hosts skew, so define measurement rules carefully.

### 18.3. Illustrative audit event

~~~json
{
  "claimIdRef": "claim-hash-lab-7a0e",
  "action": "REDEEM",
  "consumerService": "invoice-worker",
  "tenantId": "TENANT-LAB-01",
  "source": "partner-sftp-lab",
  "objectVersion": 2,
  "sizeBytes": 83886080,
  "outcome": "SUCCESS",
  "traceId": "TRACE-LAB-47",
  "occurredAt": "2026-11-23T14:05:00+07:00"
}
~~~

**This is not framework-generated log output.** If claim IDs or object keys are considered sensitive, log only safe reference hashes in general logs and restrict lookup to a privileged audit store. Never log raw tokens/service credentials or sensitive payloads.

### 18.4. Incident: “tokens consumed OK yet business commits are zero”

Troubleshooting sequence:

1. Compare **tokens delivered** against **claim redeem success**.
2. If redeems fail, check missing/expired/denied/store unavailable.
3. If redeems succeed, compare **business commit success** against parse errors/DB failures.
4. If business commits succeed yet the broker keeps redelivering, check acks/offsets and idempotency.
5. If business completes yet claim bytes never drop, check cleanup eligibility/GC.

### 18.5. Three useful alerts

- **Missing claim after publish:** received tokens returning NOT_FOUND/EXPIRED exceed threshold.
- **Orphan storage growth:** stored claim bytes climb steadily while token publishing or cleanup falls behind.
- **No business progress:** source still holds tokens while `last business commit` goes stale, regardless of broker health.

## 19. Claim Check Incident Runbooks

### 19.1. Runbook A — Consumer receives token but cannot find payload

1. Record claimId (per security policy), source, consumer, tenant, publish time, and target store.
2. Distinguish **true 404**, **transient store outage**, **permission denied**, **expired token**, and **metadata not yet AVAILABLE**.
3. Check whether producer and consumer point to **the same environment/region/store namespace**.
4. Verify object existence/version and whether GC deleted it early.
5. If origin data still exists, restore the object/claim via authorized procedures preserving business keys.
6. Never ack “success” without the payload; preserve exceptions/DLQ/retries with an owner.
7. Fix TTL/cleanup/publish ordering and add regression tests.

### 19.2. Runbook B — Message store out of capacity

1. Measure claim counts/bytes by source, age, status, and orphan candidates.
2. Inspect broker backlogs, DLQs, and incomplete consumer groups.
3. Determine whether GC is failing, delete permissions are broken, metadata drifted, or retention policies are overly broad.
4. Temporarily raise quotas if authorized to restore forward progress.
5. Delete only **eligible, reconciled** claims; never run blind bulk age-based deletes.
6. Optimize file sizes, streaming, appropriate compression, and TTL policies.

### 19.3. Runbook C — Duplicate tokens after broker restart

1. Look up workId/businessKey and pre-restart token publish/ack audits.
2. Check consumer idempotency; did business logic already commit?
3. If already processed, mark duplicate per contract and ack cleanly; **create no new side effects**.
4. If unprocessed, redeem the claim and process again.
5. Never delete claims merely to suppress duplicates if other consumers still need them.

### 19.4. Runbook D — DLQ cannot replay because claim expired

1. Verify whether the claim was truly deleted or merely denied/store unavailable.
2. Check if the original data source or valid backups allow reconstruction.
3. If recoverable, mint a new claim **explicitly linked to the business key/event ID** so business effects don't double.
4. If unrecoverable, log a data-loss incident at proper severity and notify the owner.
5. Update retention to cover DLQ investigation/replay windows.
6. Avoid keeping all sensitive data indefinitely as a crude error-handling workaround.

### 19.5. Runbook E — Fan-out: one group finished, another sees missing claim

Check **per-subscriber completion**, cleanup timing, recognized groups, and claim ownership. If claims were deleted after the first group finished, fix policy: retain until all required groups complete, issue independent claims, or guarantee origin replay.

### 19.6. Runbook F — Payload fails checksum

Quarantine the object/claim, halt business processing of untrusted bytes, inspect object versions/overwrites, metadata writes, serialization, and security boundaries. Never update the checksum to match corrupted bytes just to “turn tests green” without verifying the true source.

### 19.7. Runbook G — HTTP client times out during upload

Check staging/object completion, AVAILABLE metadata, published tokens, and job status. If a retry carries the same idempotency key, return stored status/results rather than creating duplicate objects or tokens unconditionally. Safely clean up orphaned staging files.

### 19.8. Runbook H — Rollback/redeploy causes deserialization errors

Identify original Message schema/class versions, serializers, Java library versions, and producer/consumer compatibility. You may need compatible consumers/transformers to migrate or read older records; avoid bulk-deleting claims or unsafe deserialization. Prefer versioned, interoperable payload schemas across JVMs going forward.

## 20. Hands-On Project: Claim Check in a Document Pipeline

**Lab goal:** take a mock large-payload file, persist it durably in a claim store, pass a small token to a consumer, restore the data, commit business results idempotently, and clean up the claim **after completion**. Start with an in-memory store to learn the API, then expand to a shared store/test broker.

### 20.1. DemoDocs system

A simulated organization receives partner CSV reports. Each file has an immutable **documentId** and version. The goal is validating schemas and writing valid rows to a test database. One worker indexes data for search; another generates audit reports (optional fan-out).

Fixture:

~~~csv
document_id,document_version,order_id,amount
DOC-LAB-0041,2,ORDER-LAB-087,120000
DOC-LAB-0041,2,ORDER-LAB-088,175000
~~~

**Data is synthetic.** Never use real customer data, real tokens, production credentials, or production buckets in practice.

### 20.2. Two-phase lab architecture

~~~mermaid
flowchart TD
    FILE["Phase A: Local file / HTTP mock"] --> VALID["File readiness + validation"]
    VALID --> STORE["Claim In: store payload"]
    STORE --> BLOB[("Shared Store / Phase A memory")]
    STORE --> REF["Claim token envelope"]
    REF --> TRANSPORT["Phase A channel / Phase B broker"]
    TRANSPORT --> AUTH["Validate tenant + claim"]
    AUTH --> FETCH["Claim Out: retrieve"]
    BLOB --> FETCH
    FETCH --> PROCESS["Parse CSV + idempotent DB commit"]
    PROCESS --> ACK["Ack / status commit"]
    ACK --> GC["Cleanup after completion/retention"]
    GC --> BLOB
    FETCH -->|Invalid content| DLQ["Quarantine + owner"]
~~~

### 20.3. Phase A — Learn store and retrieve with SimpleMessageStore

1. Create an in-memory **MessageStore** (see Java in section 8).
2. Build a Message carrying a mock String/file metadata payload with businessKey.
3. Store the Message and take **`MessageHeaders.ID`** as the claim token.
4. Put the token in a separate message sent through a test DirectChannel or QueueChannel.
5. Consumer looks up the token, retrieves the original message, and checks payload and headers.
6. Do not delete the claim before the consumer reports business success.
7. Delete the claim after verification; try retrieving again and record expected `NOT_FOUND`.

**Limitation:** the in-memory lab does not prove restart recovery, cross-instance sharing, or broker durability.

### 20.4. Phase B — Use a shared store

1. Pick **JdbcMessageStore** or object store + metadata DB in an authorized test environment.
2. Define serializers/schemas, object size limits, and retention.
3. Create the claim in a producer process.
4. Start a separate consumer process/JVM accessing **the same store** and redeem successfully.
5. Shut down the producer; the consumer must still redeem the claim if required by contract.
6. Audit-log claimId ref, version, size, checksum, and store/read timestamps.
7. Test store outage: consumer retries/backs off without losing the token prematurely.

### 20.5. Phase C — Send tokens via a broker

1. Choose a **JMS or RabbitMQ test broker** and configure an appropriately durable queue.
2. Claim-in accepts the file; persists original before publishing.
3. Publish the small token via an outbound adapter, logging correlation/workId.
4. A message-driven inbound adapter delivers the token to the consumer.
5. Consumer validates tenant/owner, performs claim-out, and parses.
6. Handler writes DB using business key **partner + documentId + version** and a unique constraint.
7. Ack broker only after commit criteria per listener contract; do not delete the claim early.
8. Clean up claims once required consumer statuses and retention permit.

### 20.6. Phase D — Test failure windows

| Test | How to simulate | Expected |
| --- | --- | --- |
| **D1** | Producer dies after STORE before PUBLISH | Outbox/pending state enables republish or safe orphan GC |
| **D2** | Broker gets token while producer misses ACK | Repetitive publish with same token/eventId remains safe |
| **D3** | Store offline during consumer retrieve | Retry/backoff; no false success ack |
| **D4** | Business DB commits then consumer dies before ack | Redelivery produces no duplicate rows |
| **D5** | Consumer retrieves then parser throws | Claim retained for retry/quarantine per policy |
| **D6** | Claim TTL expires before DLQ replay | Gap detected; never report recovery if payload is gone |
| **D7** | Fan-out to two consumers; consumer A finishes first | Claim not deleted while B still needs it |
| **D8** | Consumer passes another tenant's claim ID | Authorization DENY; no payload leaked |
| **D9** | Object bytes modified while metadata stays old | Checksum mismatch; quarantined |
| **D10** | 100 concurrent jobs, connection-limited store | Backpressure, no OOM, metrics visible |

### 20.7. Testing actual token size

Create a message with a 5 MiB mock payload and a claim token of a few dozen bytes. Inspect **wire payload bytes sent over the broker**, not just in-memory Java object sizes. Routing headers, serializers, and protocol overhead make wire messages larger than raw tokens, yet they must **not carry the 5 MiB binary** if Claim Check aims to keep binaries off the broker.

### 20.8. Testing completion timelines

Record timestamps for milestones:

~~~text
claimStoredAt
tokenPublishedAt
tokenReceivedAt
claimRedeemedAt
businessCommittedAt
brokerAcknowledgedAt
claimCleanupEligibleAt
claimDeletedAt
~~~

Never observe **claimDeletedAt before businessCommittedAt** in retryable models needing data. With multiple consumers, cleanup eligibility must also check completion across all required groups.

### 20.9. Lab deliverables

| Deliverable | Minimum evidence |
| --- | --- |
| Pipeline diagram | Source, claim store, broker, consumer, business DB, GC |
| Message contract | Claim reference, version, tenant, business key |
| Claim store config | Store type, retention, serializer, ACLs, resource limits |
| Producer flow | File readiness, store-before-publish, outbox/retries |
| Consumer flow | Authn/authz, retrieve, checksum, idempotent commit |
| Test run | Expected/Actual, safe logs/traces, failure injection |
| Cleanup plan | Retain/delete rules across retry/DLQ/fan-out, audits |
| Runbook | Missing claim, store offline, duplicate, expired, orphan |
| Known limits | What remains unverified against real infrastructure |

## 21. Claim Check with Message Store Test Matrix

The test IDs below represent **expected requirements**, not claims that tests were executed. For each case, record **Input, Expected, Actual, Result, Evidence, Owner**; without experimental evidence, keep **PENDING/UNKNOWN**.

### 21.1. Contract and storage

| ID | Scenario | PASS condition |
| --- | --- | --- |
| **CL-01** | ClaimCheckIn receives original Message | Outputs claim ID; store holds original under matching key |
| **CL-02** | Outbound token message | Transport does not unintentionally carry large original binary |
| **CL-03** | ClaimCheckOut receives valid token | Accurately restores supported payload and metadata |
| **CL-04** | Nonexistent token ID | Returns classified missing error; does not fabricate empty payload |
| **CL-05** | SimpleMessageStore inside one JVM | Store/retrieve works while JVM stays up |
| **CL-06** | Restart JVM with SimpleMessageStore | Limitation documented: in-memory claims lost |
| **CL-07** | Producer and consumer have separate SimpleMessageStores | Consumer cannot find producer's claims; test confirms misconfiguration |
| **CL-08** | Shared durable store | Separate consumer JVM redeems cleanly across restarts |
| **CL-09** | Non-serializable payload in JdbcMessageStore | Clear error/rejection; broken token not published |
| **CL-10** | Change schema/class version and redeploy | Explicit compatibility/migration handling |
| **CL-11** | Original vs. restored bytes | Content hash/size matches contract |
| **CL-12** | Object altered in store without changing version | Mismatch/invalid overwrite detected |

### 21.2. Delivery and failure handling

| ID | Scenario | PASS condition |
| --- | --- | --- |
| **CL-13** | Producer crashes after store, before publish | Outbox/reconciliation detects unpublished claim |
| **CL-14** | Broker publish succeeds yet producer misses ACK | Retry produces no duplicate side effects |
| **CL-15** | Token published before object is AVAILABLE | Consumer does not process incomplete object; defect surfaced |
| **CL-16** | Store temporarily unavailable | Retry/backoff; no false success ack |
| **CL-17** | Retrieve succeeds yet parse/DB fails | Claim not deleted early; retry/quarantine operates |
| **CL-18** | DB commit succeeds, broker ack lost | Safe redelivery via idempotency |
| **CL-19** | Token re-sent with different message ID | Business key detects duplicate accurately |
| **CL-20** | Two distinct claim IDs for same business command | Unique key protects business side effects |
| **CL-21** | Same claimId with conflicting metadata/payload | Rejected/investigated; wrong content not read |
| **CL-22** | Poison payload/unsupported schema | DLQ/quarantine with owner; no infinite retries |
| **CL-23** | DLQ token replayed after code fix | Claim still present; business processed once |
| **CL-24** | Token expired before DLQ replay | No false success; data-loss/recovery procedure triggered |

### 21.3. Security, concurrency, and lifecycle

| ID | Scenario | PASS condition |
| --- | --- | --- |
| **CL-25** | Tenant A consumer redeems tenant B token | Authorization DENY; payload not leaked |
| **CL-26** | Token appears in logs | Standard logs redact/hash sensitive claim keys |
| **CL-27** | Client alters allowedConsumer in metadata | Server uses trusted metadata; access denied |
| **CL-28** | Signed URL expired or used out of scope | Access denied per policy |
| **CL-29** | Content checksum mismatch | Processing halted, quarantined, audited |
| **CL-30** | Compressed file exceeds expanded-size limit | Parser blocked before resource exhaustion |
| **CL-31** | JMS/AMQP queue redelivers token to another worker | Store still holds data; business idempotent |
| **CL-32** | Two workers redeem same claim concurrently | No premature deletion; no business duplicates |
| **CL-33** | Kafka two groups need the same claim | Group A finishing does not delete B's payload |
| **CL-34** | Kafka replays old offset past claim TTL | System honors published retention contract |
| **CL-35** | Owner Mover/Leaver or revoked service permissions | Unauthorized access blocked; pending claims handled |
| **CL-36** | Post-completion cleanup | Deletion runs after safety conditions with audit |
| **CL-37** | Transient cleanup failure | Idempotent retry without corrupting business status |
| **CL-38** | Object deleted while metadata remains | Cleanup job retries and reconciles safely |
| **CL-39** | MessageStore hits quota | Backpressure/alerts; no tokens emitted for broken claims |
| **CL-40** | Shutdown/restart mid-processing | Recovers or reports UNKNOWN per contract without silent loss |
| **CL-41** | Many stored claims never published | Orphan metrics/GC detect them |
| **CL-42** | Consumer gets token while store is in wrong region | Error/fallback/reconciliation; never reads wrong claim with colliding ID |
| **CL-43** | One fan-out branch fails for prolonged period | Clear retention/ownership; other branches don't delete claim early |
| **CL-44** | Object key points outside allowed path | Rejects path traversal/unauthorized object |

### 21.4. Sample report for a hard test case

~~~yaml
testCase: CL-18
claimId: clm-lab-7e8d03ac
businessKey: PARTNER-A/DOC-2026-0041
scenario: "DB commit success; consumer crashes before broker ack"
expected: >
  The token is redelivered; payload can still be redeemed;
  business effect remains one; cleanup waits for completion.
actual: "Fill with actual observations"
result: PENDING
evidenceRef: "lab://tests/CL-18"
owner: claim-check-lab
verifiedAt: null
~~~

**Never** flip result to PASS merely because idempotency code exists on paper. Inject crashes at the exact spot and verify **business DB**, **claim store**, **broker state**, and cleanup outcomes.

### 21.5. Most critical tests

Six cases reliably expose design flaws:

1. **CL-13:** store OK yet publish unconfirmed.
2. **CL-17:** claim retrieved yet handler fails.
3. **CL-18:** business commit OK yet broker ack lost.
4. **CL-25:** cross-tenant token cannot be redeemed.
5. **CL-33:** first subscriber group finishes while later groups still need data.
6. **CL-36:** cleanup never runs before obligations end.

Without evidence for these cases, a “works on the happy path” Claim Check diagram is not enough to declare the flow reliable.

## 22. Anti-Patterns and Pre-Production Checklist

### 22.1. Common mistakes

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| **Using Claim Check for tiny few-byte messages** | Pointless store I/O and latency | Use only when benefits clearly outweigh costs |
| **Leaving binary in a header after claim-in** | Broker still receives huge payloads | Inspect serialized transport envelopes |
| **Using SimpleMessageStore across two JVMs** | Consumer cannot find data | Shared durable store/API |
| **Storing File/InputStream objects expecting post-restart reads** | Handles/sessions become invalid | Persist durable bytes/objects + metadata |
| **Deleting claims during Claim Check Out retrieval** | Handler retries lack payloads | Clean up after completion/retention |
| **Deleting claims immediately on publish timeout** | Broker may have received the token | Outbox + reconciliation; no blind deletes |
| **Treating MessageStore as a durable work queue** | Lacks broker acks/dispatch | Separate claim storage from work transport |
| **Trusting claimId as authorization proof** | BOLA/IDOR, cross-tenant data leaks | Authn/authz on every redeem |
| **Using guessable object keys with public read** | Payload snooping | Private buckets, service proxies/ACLs, governed signed URLs |
| **Omitting schema/version in claims** | Consumers misread payloads during rollouts | Version contracts and migrations |
| **Deduplicating solely by claimId** | Two claims for same business command duplicate effects | Business idempotency keys |
| **Sending tokens to Kafka with ultra-short object TTLs** | Historical replay/lag loses payloads | Retention contracts or origin rebuild |
| **Sharing claims and deleting after first subscriber** | Other subscribers hit missing payloads | Per-consumer completion/retention |
| **No orphan cleanup** | Object store grows unbounded | Reconciled, audited GC |
| **GC deleting everything older than X days** | Destroys DLQ/retry/legal hold data | State- and obligation-based cleanup |
| **Putting full payloads into debug logs** | Data leaks and huge log bills | Log safe metadata |
| **Loading every object into byte[]** | OOM/GC pressure | Bounded streaming/chunking |
| **Bounding broker concurrency without bounding redeems** | Store melts down despite tiny tokens | Separate bulkheads for store reads |
| **Treating checksums as source authentication** | Attacker alters both data and metadata | Protect metadata, enforce authorization/signatures |
| **Conflating store 404 with store outage** | Marks data lost on mere timeouts | Explicit error taxonomy and retries |
| **Returning HTTP 202 before durable persistence** | Client thinks work is safe while crashes lose it | Persist job/claim/outbox before accepted |
| **Using local paths cross-container** | Consumers can't find files or hit wrong paths | Shared object store + scoped keys |

### 22.2. Design checklist

- [ ] Clear technical/economic rationale exists for Claim Check over direct payload transfer.
- [ ] Explicitly decided what gets stored: full Message, payload, or object bytes.
- [ ] Tokens are small, immutable per content/version, and secret-free.
- [ ] Trusted metadata tracks source, tenant, object version, TTL, and checksum.
- [ ] Consumers are authenticated and authorized **on every redeem**, not just by holding claimId.
- [ ] Store is shared and durable whenever tokens cross JVMs/brokers.
- [ ] Incompatible or sensitive headers/channels/contexts are not serialized.
- [ ] Payloads are complete/AVAILABLE before tokens are published.
- [ ] Outbox/retries/reconciliation cover the gap between storing and publishing.
- [ ] Business-level idempotency covers token redelivery.
- [ ] Broker acks/offsets align with business commit criteria.
- [ ] Failures after retrieve and before business commit are tested.
- [ ] Failures after business commit and before broker ack are tested.
- [ ] Claims are never deleted before all required consumer groups finish per contract.
- [ ] Retention covers backlogs, retries, DLQs, and committed replays.
- [ ] Garbage collector enforces eligibility, states, auditing, and dry-run modes.
- [ ] Logic distinguishes missing, expired, unauthorized, and store unavailable.
- [ ] Streaming/size limits prevent OOM and malicious payloads.
- [ ] Redeem concurrency is bounded to store/DB/object throughput.
- [ ] Temp files/objects, backups, caches, and logs are governed by data lifecycle policies.
- [ ] Metrics cover store/publish/redeem/commit/cleanup, not just broker receives.
- [ ] Runbooks exist for missing claims, orphans, duplicates, fan-out, and DLQ expiry.
- [ ] Producer/consumer restarts and schema version changes are tested.
- [ ] Evidence of negative tests, readback, and cleanup exists in authorized environments.

### 22.3. Claim Check decision tree

~~~mermaid
flowchart TD
    START{"Payload large / sensitive / multi-hop?"}
    START -->|Negligible| DIRECT["Pass message directly if appropriate"]
    START -->|Yes| STORE{"Where is the payload stored?"}
    STORE -->|Moderate Spring Message| MSG["MessageStore + ClaimCheckIn/Out"]
    STORE -->|Very large file/object| OBJ["Object storage + metadata + custom redeem"]
    MSG --> SHARED{"Do consumers run in other JVMs?"}
    OBJ --> SHARED
    SHARED -->|Yes| DURABLE["Shared durable store + authz"]
    SHARED -->|No| LOCAL["Labs may use in-memory; production evaluates durability"]
    DURABLE --> SAFE["Store before publish + recovery"]
    LOCAL --> SAFE
    SAFE --> DELIVERY["Ack + business idempotency + retry"]
    DELIVERY --> RETAIN["Retention + DLQ/fan-out + GC"]
    RETAIN --> VALIDATE["Test crashes, unauthorized redeems, missing data"]
~~~

If you cannot yet explain **“how long does a claim live and who is permitted to delete it?”**, do not treat publishing a small UUID as completing the Claim Check Pattern.

## 23. Practice Rubric, Questions, and Summary

### 23.1. Self-assessment rubric

Score each criterion **0–3**: 0 missing; 1 described only; 2 implemented without full verification; 3 empirically tested with evidence and error handling.

| Criterion | What Level 3 must prove |
| --- | --- |
| **Pattern mastery** | Distinguishes Claim Check, MessageStore, brokers, and idempotency |
| **Message contract** | Token carries ID/version/tenant/business key without leaking payload |
| **Store design** | Picks in-memory/JDBC/object store matching scale and durability |
| **Claim-in** | Object complete before publish; outbox/recovery present |
| **Claim-out** | Authorized redeem, checksum/schema checks, missing-claim handling |
| **Business semantics** | Commit and ack align per contract; side effects idempotent |
| **Multi-consumer** | Fan-out/competing/replay never deletes claims prematurely |
| **Retention** | Stateful TTL/cleanup with reconciliation |
| **Security** | Blocks cross-tenant access; protects objects/credentials/logs |
| **Performance** | Measures store throughput, streaming/memory, bounded concurrency |
| **Operations** | Metrics, runbooks, DLQs, orphan detection |
| **Validation** | Fault injection, restarts, evidence, negative tests |

**Illustrative maximum total: 36 points.** This rubric aids self-study and is not an official Spring Integration standard or certification.

### 23.2. Self-check questions

1. How does Claim Check differ from **message compression** and **message filtering**?
2. Which storage component does Spring Integration's `ClaimCheckInTransformer` use to save the original Message?
3. Why does a **separate SimpleMessageStore per JVM** fail when tokens cross a broker to another service?
4. Does `ClaimCheckOutTransformer` successfully restoring data prove business logic committed?
5. What happens if the original Message is deleted on retrieval and the handler subsequently throws an exception?
6. Why does an unguessable UUID token still require authorization at redeem time?
7. If the producer stores successfully yet broker publishing fails, how should orphans be handled?
8. With three Kafka consumer groups, why can deleting the claim after the first group cause failures?
9. How does a DLQ containing only claim IDs without original payloads impact replay?
10. Is idempotency by claimId sufficient when the same business command arrives under two different claims?
11. Why should HTTP 202 Accepted be backed by durable state/job records per contract?
12. When handling large files, why shouldn't you serialize an `InputStream` as a shared object?
13. Which metrics distinguish broker token-send failures from store redeem failures?
14. Does a checksum verify that the file sender was authorized?
15. When object deletion and metadata deletion span two systems, what must be accounted for?

**Hints:** (1) stores content and sends a reference; (2) `MessageStore`; (3) in-memory isn't shared and is lost on restart; (4) no; (5) retries lose the payload; (6) claim ID is not authorization; (7) stateful outbox/reconciliation/GC; (8) other groups/replays still need it; (9) unrecoverable without another origin; (10) no, need business keys; (11) crash recovery; (12) stream handles aren't portable or durable; (13) publish pending vs. redeem failures; (14) no; (15) deletion states, idempotent retries, orphan reconciliation.

### 23.3. Summary

**Claim Check with Message Store** lets you keep original messages/payloads in a managed location while passing only **small references** across adapters, gateways, pollers, and MessageChannels. In **Spring Integration**, `ClaimCheckInTransformer` and `ClaimCheckOutTransformer` support storing/restoring Messages via **MessageStore**; for very large payloads or cross-JVM consumers, a **shared durable store or object storage + claim metadata/service** is required instead of memory.

This pattern shines when combining **File/SFTP/HTTP inbound** with **JMS/AMQP/Kafka brokers** or **JDBC business storage**, yet it does not automatically deliver exactly-once semantics, security, cross-system transactions, or safe cleanup. A reliable design must address **store-before-publish, outbox/retries, per-redeem authorization, commit-level business idempotency, retention for DLQs/fan-out, GC, and observability**.

**Final principle:** *Tokens merely point the way to data; system correctness is proven when data remains readable by the right party, at the right version, at the right time—and is cleaned up only after all valid processing obligations are complete.*
