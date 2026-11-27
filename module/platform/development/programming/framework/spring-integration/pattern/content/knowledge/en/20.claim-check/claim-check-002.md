# Message carries only the claim token

In integration systems, a message may contain a document, image, invoice, dossier, or very large and sensitive content. Many intermediate stages only need to know **which job is running**, without needing to see the original data. Passing the raw payload through every Router, Filter, queue, and handler can increase serialization cost, memory usage, transmission time, and data exposure risk.

**Claim Check** is an Enterprise Integration Pattern that **stores the original message in a repository and passes a reference token in place of the original payload**. In Spring Integration, the **Incoming Claim Check Transformer** stores the message in a `MessageStore` and emits a new message with a **UUID claim token as its payload**. The **Outgoing Claim Check Transformer** uses the token to read back the original message when downstream actually needs the content.

The lesson **Message carries only the claim token** belongs to the **Claim check** chapter, **SPRING_INTEGRATION_PATTERN** module. The module aims at building Enterprise Integration Patterns with Spring Integration, combining Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing processing branches in a loosely coupled, extensible manner.

**Key point:** "carries only the token" refers to **the new payload traveling through the flow**. You cannot conclude from this that all headers have been stripped, that the original data has disappeared from the system, or that anyone holding the token is authorized to retrieve the content.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain the **store → token → restore** lifecycle of Claim Check.
2. Distinguish the initial `Message<DocumentRequest>` from the `Message<UUID>` after check-in.
3. Understand that Spring Integration stores the **original message**, not just a business ID string.
4. Use `claimCheckIn(MessageStore)` and `claimCheckOut(MessageStore, boolean)` via Java DSL.
5. Understand the default `removeMessage=false` and when `true` is needed.
6. Write an integration test proving the mid-flow payload is only a UUID, and then retrieving the original data.
7. Distinguish token, business ID, trace ID, and correlation ID.
8. Choose `SimpleMessageStore` or a persistent `MessageStore` appropriate for the lifecycle.
9. Design timeout, expiry, cleanup, retry, idempotency, and missing-token handling.
10. Control headers, authorization, and data protection even when the message carries only a token.

## 2. The problem: not every endpoint needs the original payload

Suppose the application receives a document processing request:

~~~text
Message<DocumentRequest>
  payload:
    documentId = DOC-1001
    customerId = CUST-21
    content = <very large content>
    classification = CONFIDENTIAL
  headers:
    traceId = trace-1001
    businessCorrelationId = DOC-1001
~~~

The flow must classify the job, enqueue it, audit it, and only then open the document. Only the final handler needs `content`.

~~~mermaid
flowchart LR
    IN["Message<DocumentRequest>"] --> CI["Claim Check In"]
    CI --> STORE[("MessageStore")]
    CI --> TOKEN["Message<UUID token>"]
    TOKEN --> ROUTER["Router / queue / audit metadata"]
    ROUTER --> CO["Claim Check Out"]
    CO --> STORE
    CO --> OUT["Message<DocumentRequest>"]
    OUT --> HANDLER["Document Processor"]
~~~

Interpretation:

- **Check-in** retains a message containing the full data in the store.
- **Token message** circulates among endpoints without carrying the document content in its payload.
- **Check-out** uses the token to look up the stored message.
- Not passing the large payload through every channel **does not automatically guarantee** that headers contain no sensitive data.

### 2.1. Baggage claim analogy

| Claim Check | Airport example | Spring Integration |
|---|---|---|
| Original data | Suitcase | Message containing document |
| Storage point | Baggage counter | MessageStore |
| Claim token | Baggage claim tag | UUID |
| Check-in | Checking the bag | ClaimCheckInTransformer |
| Check-out | Claiming the bag | ClaimCheckOutTransformer |
| Missing item | Tag fails to retrieve bag | Missing-token/store failure |

We are not "compressing the suitcase into a tag"; the data remains elsewhere, and the tag is merely a reference.

## 3. What does "Message carries only the token" mean exactly?

Spring Integration creates a **new message** after check-in whose payload is the token:

~~~text
BEFORE
Message<DocumentRequest>
  payload = DocumentRequest(DOC-1001, ...)
  headers = traceId, businessCorrelationId, ...

STORE
MessageStore[token] = Message<DocumentRequest>

AFTER CHECK-IN
Message<UUID>
  payload = token
  headers = appropriate metadata per transformation mechanism
~~~

**True:** the current payload is a `UUID`, not `DocumentRequest`.

**False:** all original information has been deleted, all headers are stripped by default, or security is completely solved.

### 3.1. The token is a UUID, not documentId

According to the `ClaimCheckOutTransformer` API, the message used for check-out has a payload of type `UUID`. A `String` such as `"DOC-1001"` or `"4eab..."` does not automatically become a properly typed token.

~~~java
import java.util.UUID;
import org.springframework.messaging.Message;

void inspect(Message<?> afterCheckIn) {
    Object payload = afterCheckIn.getPayload();

    if (!(payload instanceof UUID token)) {
        throw new IllegalArgumentException(
                "CLAIM_TOKEN_MUST_BE_UUID");
    }

    System.out.println("Claim token acquired");
}
~~~

The code above uses `afterCheckIn` as a message received from the token channel, not a Spring-generated variable. You should not log the token directly in production examples because it is a potentially sensitive reference.

### 3.2. Spring stores the entire Message

`ClaimCheckInTransformer` receives a `Message<?>` and uses `MessageStore` to save it. The store can retain both the payload and original metadata. An application that manually saves `byte[]` into object storage and passes a URL is also applying the Claim Check *idea*, but that is not the exact default behavior of `ClaimCheckInTransformer`.

### 3.3. Headers require separate control

Suppose the original message has:

~~~text
payload = DocumentRequest(...)
headers:
  traceId = trace-1001
  customerEmail = private@example.invalid
  Authorization = SECRET
~~~

If the token flow still passes sensitive headers through another broker, Claim Check still risks leaking information. Design a **header allowlist**, test propagation across real endpoints, and never treat Claim Check as a replacement for authorization or encryption.

## 4. Token lifecycle

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant IN as Check-in
    participant S as MessageStore
    participant T as Token flow
    participant OUT as Check-out
    participant D as Downstream

    P->>IN: Message<DocumentRequest>
    IN->>S: Store original message
    S-->>IN: UUID token
    IN->>T: Message<UUID>
    Note over T: Payload holds only the token
    T->>OUT: Message<UUID>
    OUT->>S: Look up by token
    S-->>OUT: Original Message
    OUT->>D: Message<DocumentRequest>
~~~

Conditions required for the happy path:

1. The store is available and saves successfully.
2. The token is transferred with the correct type across channels/protocols.
3. Check-out accesses the **same backend and namespace** as check-in.
4. The entry has not been deleted or expired.
5. The person or service requesting restoration has passed access control.
6. Downstream can read the original payload type/schema.

A syntactically valid token **does not prove** the store still holds the message.

## 5. How does Claim Check differ from other EIPs?

| Pattern | Responsibility | Difference from Claim Check |
|---|---|---|
| **Claim Check** | Stores content and sends a reference token | Restores the message from MessageStore |
| **Transformer** | Changes payload/message representation | Does not keep the original in a store by default |
| **Content Enricher** | Adds missing data | Does not primarily replace payload with a token |
| **Filter** | Passes or drops messages | Does not implement a store/retrieve mechanism |
| **Router** | Chooses destination channel | Does not store/restore the original |
| **Splitter** | Splits a message into parts | Does not replace payload with a reference |
| **Aggregator** | Combines multiple messages into one result | Requires grouping and a release strategy |
| **Gateway** | Request/reply | May sit before/after Claim Check |
| **Wire Tap** | Copies message to another branch | Can expose payload if placed before check-in |

Claim Check fits when intermediate steps in the flow **do not need the original content**; if every handler must read the document, repeatedly checking in and checking out may only add overhead.

## 6. Two Transformers in Spring Integration

Spring Integration provides:

- `org.springframework.integration.transformer.ClaimCheckInTransformer`.
- `org.springframework.integration.transformer.ClaimCheckOutTransformer`.

### 6.1. Check-in: from Message<T> to Message<UUID>

~~~text
Message<T> --> ClaimCheckInTransformer --> Message<UUID>
                    |
                    +--> MessageStore[token] = Message<T>
~~~

The transformer generates a claim token based on the stored message. In the current implementation, the token is a UUID. The data is stored separately and is not automatically sent to every subsequent endpoint.

### 6.2. Check-out: from Message<UUID> back to original data

~~~text
Message<UUID> --> ClaimCheckOutTransformer --> Message<T>
                    |
                    +--> MessageStore.lookup(token)
~~~

When a token has no matching entry, check-out throws an error; it should not fabricate an empty document and treat that as success.

### 6.3. removeMessage is not enabled by default

`removeMessage` on check-out defaults to **`false`**. Without configuring deletion or another cleanup mechanism, the original message may remain in the store across multiple claims.

| Configuration | Meaning | Risk to consider |
|---|---|---|
| `removeMessage=false` | Content can be retrieved again while entry exists | Store grows without cleanup |
| `removeMessage=true` | Deletes entry when claimed | Token retry/redelivery may fail |
| Separate TTL/cleanup | Deletes upon expiration | Must not be shorter than queue wait and required replay window |

The policy must be determined by business requirements; do not enable deletion solely to free memory without examining the failure window.

## 7. Java 17 Model: DocumentRequest

To focus on the token, we model the document with a record containing a content string. In real systems, the payload can be a binary file, blob, or decoded object.

~~~java
public record DocumentRequest(
        String documentId,
        String customerId,
        String content,
        String classification
) {
    public DocumentRequest {
        if (documentId == null || documentId.isBlank()) {
            throw new IllegalArgumentException(
                    "DOCUMENT_ID_REQUIRED");
        }
        if (customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException(
                    "CUSTOMER_ID_REQUIRED");
        }
        if (content == null || content.isBlank()) {
            throw new IllegalArgumentException(
                    "CONTENT_REQUIRED");
        }
        if (classification == null
                || classification.isBlank()) {
            throw new IllegalArgumentException(
                    "CLASSIFICATION_REQUIRED");
        }
    }
}
~~~

A record has no setters, making it suitable for immutable message examples. With `byte[]` or mutable collections, merely declaring a record **does not create deep immutability**. Consider defensive copying and snapshotting at the store boundary.

### 7.1. Where does validation sit?

- **Before check-in:** validate schema, size limit, upload permissions, and minimal fields.
- **Between check-in/out:** can Filter/Router on **verified** metadata without reading `content`.
- **After check-out:** validate detailed content that only authorized handlers may read.
- **When token is missing:** dedicated error flow; do not treat as a Filter rejection by default.

## 8. Java DSL: check-in and check-out sharing a MessageStore

Spring Integration Java DSL offers `claimCheckIn(MessageStore)` and `claimCheckOut(MessageStore, boolean)`. The following demo configuration uses an in-memory `SimpleMessageStore` for easy JUnit testing.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.store.MessageStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
public class ClaimCheckConfiguration {

    @Bean
    public MessageStore claimMessageStore() {
        return new SimpleMessageStore();
    }

    @Bean(name = "claims.in")
    public MessageChannel checkInInput() {
        return new DirectChannel();
    }

    @Bean(name = "claims.token")
    public PollableChannel tokenOutput() {
        return new QueueChannel();
    }

    @Bean(name = "claims.checkout")
    public MessageChannel checkOutInput() {
        return new DirectChannel();
    }

    @Bean(name = "claims.restored")
    public PollableChannel restoredOutput() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow checkInFlow(
            MessageStore claimMessageStore) {
        return IntegrationFlow.from("claims.in")
                .claimCheckIn(claimMessageStore)
                .channel("claims.token")
                .get();
    }

    @Bean
    public IntegrationFlow checkOutFlow(
            MessageStore claimMessageStore) {
        return IntegrationFlow.from("claims.checkout")
                .claimCheckOut(claimMessageStore, true)
                .channel("claims.restored")
                .get();
    }
}
~~~

Here:

1. `claims.in` receives the original message.
2. `claimCheckIn(store)` saves the message and emits a UUID token.
3. `claims.token` is a QueueChannel test fixture holding token messages.
4. `claims.checkout` receives a UUID to retrieve the data.
5. `claimCheckOut(store, true)` restores and **deletes the entry** per the claim-once option.
6. `claims.restored` receives the restored message.

**Note:** This is a demo with `removeMessage=true`, not the only configuration. If replay is needed, consider `claimCheckOut(store, false)` along with another cleanup policy.

### 8.1. Why must both endpoints use the same store?

~~~text
CORRECT
  Claim Check In  --> Store A
  Claim Check Out <-- Store A

INCORRECT
  Claim Check In  --> Store A
  Claim Check Out <-- Store B
~~~

Two stores with the same class or bean name on **two different JVMs** do not automatically share data. For cross-instance operation, you need a shared backend or a key-based routing mechanism to the same instance with proper lifecycle management.

### 8.2. Corresponding XML namespace

~~~xml
<int:claim-check-in
    id="checkin"
    input-channel="claimsIn"
    output-channel="claimsToken"
    message-store="claimMessageStore"/>

<int:claim-check-out
    id="checkout"
    input-channel="claimsCheckout"
    output-channel="claimsRestored"
    message-store="claimMessageStore"
    remove-message="true"/>
~~~

The XML example assumes the `int` namespace is already declared in a valid Spring XML context; it is not a standalone XML file. Use XML or Java DSL per your project; do not register two duplicate endpoints.

## 9. Original message and token message

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

void submit(MessageChannel input) {
    DocumentRequest document = new DocumentRequest(
            "DOC-1001",
            "CUST-21",
            "Confidential document body",
            "CONFIDENTIAL");

    Message<DocumentRequest> original =
            MessageBuilder.withPayload(document)
                    .setHeader("traceId", "trace-1001")
                    .setHeader(
                            "businessCorrelationId", "DOC-1001")
                    .build();

    input.send(original);
}
~~~

After check-in:

- `MessageStore` holds a message with payload `DocumentRequest`.
- `claims.token` receives a new message with payload `UUID`.
- `DocumentRequest.content` is **not** the payload of the token message.
- A valid check-out restores the original payload.

Do not confuse **`documentId`** (business ID) with **`UUID token`** (entry reference). A document can be checked in again and receive a new token; the business ID should remain stable for idempotency and auditing.

## 10. Integration test proving token-only payload

Tests must run through real Spring channels. Do not just call the transformer directly and assume wiring is correct.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.store.MessageStore;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ClaimCheckConfiguration.class)
class ClaimCheckFlowTest {

    @Autowired @Qualifier("claims.in")
    MessageChannel in;

    @Autowired @Qualifier("claims.token")
    PollableChannel tokens;

    @Autowired @Qualifier("claims.checkout")
    MessageChannel checkout;

    @Autowired @Qualifier("claims.restored")
    PollableChannel restored;

    @Autowired
    MessageStore claimMessageStore;

    @Test
    void checkInUsesUuidPayloadAndCheckOutRestoresDocument() {
        DocumentRequest document = new DocumentRequest(
                "DOC-1001", "CUST-21",
                "Confidential document body",
                "CONFIDENTIAL");

        Message<DocumentRequest> original =
                MessageBuilder.withPayload(document)
                        .setHeader("traceId", "trace-1001")
                        .build();

        assertTrue(in.send(original));

        Message<?> tokenMessage = tokens.receive(1000);
        assertNotNull(tokenMessage);
        assertInstanceOf(UUID.class, tokenMessage.getPayload());
        assertNotEquals(document, tokenMessage.getPayload());

        UUID token = (UUID) tokenMessage.getPayload();
        Message<?> stored = claimMessageStore.getMessage(token);

        assertNotNull(stored);
        assertEquals(document, stored.getPayload());

        assertTrue(checkout.send(
                MessageBuilder.withPayload(token).build()));

        Message<?> claimed = restored.receive(1000);
        assertNotNull(claimed);
        assertEquals(document, claimed.getPayload());

        // Config uses removeMessage=true.
        assertNull(claimMessageStore.getMessage(token));
        assertNull(tokens.receive(0));
        assertNull(restored.receive(0));
    }
}
~~~

The test proves three states:

| Point in time | Readable payload | Where original content resides |
|---|---|---|
| Before check-in | `DocumentRequest` | Input message |
| After check-in | `UUID` | `MessageStore` |
| After check-out | `DocumentRequest` | Output message; store entry was deleted in demo |

**Do not infer that all headers disappear** just because the test only asserts the payload. If policy requires stripping PII from token messages, add separate assertions for headers.

### 10.1. Testing header propagation independently

~~~java
// Illustrative snippet in test after receiving tokenMessage:
Object traceId = tokenMessage.getHeaders().get("traceId");
Object correlation =
        tokenMessage.getHeaders().get("businessCorrelationId");
~~~

This is an observation snippet, not a standalone Java method. When data crosses an external boundary, test both **allowed headers** and **headers that must not exist**.

## 11. Unit test for token validation

Spring provides the Claim Check Transformer itself; the application should test its token-control policy at ingress.

~~~java
import java.util.UUID;

public final class ClaimTokenPolicy {

    public UUID requireToken(Object payload) {
        if (!(payload instanceof UUID token)) {
            throw new IllegalArgumentException(
                    "CLAIM_TOKEN_MUST_BE_UUID");
        }
        return token;
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;

import org.junit.jupiter.api.Test;

class ClaimTokenPolicyTest {

    private final ClaimTokenPolicy policy =
            new ClaimTokenPolicy();

    @Test
    void acceptsUuid() {
        UUID token = UUID.randomUUID();
        assertEquals(token, policy.requireToken(token));
    }

    @Test
    void rejectsDocumentIdString() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.requireToken("DOC-1001"));
    }

    @Test
    void rejectsOriginalDocument() {
        DocumentRequest document = new DocumentRequest(
                "DOC-2001", "CUST-22",
                "Example body", "INTERNAL");
        assertThrows(IllegalArgumentException.class,
                () -> policy.requireToken(document));
    }
}
~~~

The validator confirms only the **payload type**; it does not prove the token exists or that the sender is authorized to read the content. Authorization must rely on authenticated principal/tenant and server-controlled metadata.

## 12. Router, Filter, and queue flows accepting only tokens

~~~mermaid
flowchart LR
    IN["DocumentRequest"] --> CI["Claim Check In"]
    CI --> ST[("MessageStore")]
    CI --> TK["Message<UUID>"]
    TK --> ROUTE{"Router by trusted headers"}
    ROUTE --> Q["Token queue"]
    Q --> FILT{"Filter: permissions/status"}
    FILT --> CO["Claim Check Out"]
    CO --> ST
    CO --> PROC["Document handler"]
~~~

### 12.1. Router cannot read document.content from a UUID

Example of a Router after check-in wrongly expecting `DocumentRequest`:

~~~java
import org.springframework.integration.annotation.Router;

@Router(inputChannel = "claims.token")
public String route(DocumentRequest document) {
    return document.classification().equals("CONFIDENTIAL")
            ? "restricted"
            : "standard";
}
~~~

This snippet is an **anti-pattern**: the input channel carries a `UUID`, not a `DocumentRequest`.

Two proper approaches:

1. Route **before check-in** when attributes from the original payload are truly required.
2. Compute and attach **trusted, minimal** metadata to the token message before routing.

If `classification` is also sensitive, do not assume turning it into a header is safe; control where headers are sent.

### 12.2. Filter after check-in

A Filter after check-in can inspect token format, request status, or processing permissions via trusted metadata. It cannot read the document body without checking out.

When a Filter rejects a token **before check-out**, the original entry may remain in `MessageStore`. A cleanup policy is needed, otherwise storage will leak.

### 12.3. Durable queue and non-durable store

If the token is sent to a durable broker while the underlying store is an in-JVM `SimpleMessageStore`, after a restart the queue may still contain tokens whose original messages are gone. The lifetime and durability of the **token flow and the store** must be designed consistently.
## 13. Choosing a MessageStore: in-memory or persistent?

`MessageStore` is the abstraction for storing and retrieving messages in Spring Integration. Using Claim Check **does not automatically make data durable**: recoverability depends on the chosen store.

| Solution | Storage mechanism | When appropriate | Risks |
|---|---|---|---|
| `SimpleMessageStore` | In JVM memory, Map-based | Demos, unit/integration tests, short-lived expendable data | Restart loses content; increases RAM |
| `JdbcMessageStore` | Relational database via JDBC | Need longer retention and shared backend | Schema, transactions, serializer, migration |
| Custom `MessageStore` | Application-implemented | Custom backend and specialized lifecycle | Must fulfill Spring's contract |
| Object storage + metadata store | Custom-designed Claim Check | Very large files, cross-service | Does not match default transformer behavior directly |

### 13.1. When multiple instances participate

~~~text
Instance A:
  Incoming Claim Check
       -> SHARED MESSAGE STORE
       -> UUID token -> broker

Instance B:
  broker -> UUID token
       -> SHARED MESSAGE STORE
       -> Outgoing Claim Check
~~~

If A and B create two separate `SimpleMessageStore` instances, a token created by A will not appear in B's store. To operate distributedly, you need a shared backend or a key-based routing mechanism directing tokens back to where the data is stored.

### 13.2. A persistent store does not eliminate all issues

Even with a database:

- Data must be serialized/deserialized with the right types.
- Java schemas and stored formats can evolve across deployments.
- Message headers may contain non-serializable internal objects.
- Transactions adding the entry and emitting the token may not synchronize with the broker.
- Keeping data too long makes the database grow continuously.
- Deleting the entry before the consumer commits can prevent retry recovery.

You must test **restart/recovery**, not just the happy path in a single JVM.

### 13.3. A token is not an external URL

A system can design its own claim token as an opaque ID pointing to a blob in object storage. That can fit very large files, but requires a custom adapter and access control. Do not feed a URL into `ClaimCheckOutTransformer` expecting a Spring Integration UUID token and treat the two mechanisms as equivalent.

## 14. Deletion policy: false or true?

### 14.1. Default: do not delete

~~~java
@Bean
IntegrationFlow reusableClaimFlow(MessageStore store) {
    return IntegrationFlow
            .from("claims.checkout.reusable")
            .claimCheckOut(store)
            .channel("claims.restored.reusable")
            .get();
}
~~~

The `claimCheckOut(store)` overload has `removeMessage=false`. If the same document needs to be restored multiple times by multiple consumers, this option is useful. However, explicit retention/cleanup is required; otherwise, the store becomes an ever-growing archive.

### 14.2. Claim once and delete entry

~~~java
@Bean
IntegrationFlow oneTimeClaimFlow(MessageStore store) {
    return IntegrationFlow
            .from("claims.checkout.once")
            .claimCheckOut(store, true)
            .channel("claims.restored.once")
            .get();
}
~~~

This is the option used in `ClaimCheckConfiguration` earlier. One successful check-out retrieves the message while deleting the entry per policy.

### 14.3. Failure window on early deletion

~~~mermaid
flowchart TD
    T["Receive UUID token"] --> CO["Check-out remove=true"]
    CO --> ST["Entry deleted from store"]
    ST --> DB["Business handler writes DB"]
    DB --> F{"Commit succeeded?"}
    F -->|Yes| OK["Complete"]
    F -->|No| R["Broker redelivers token"]
    R --> MISS["No entry left to claim"]
~~~

**Deleting from MessageStore does not mean the handler completed the business transaction.** If retries rely on the same token, `remove=true` can cause subsequent attempts to fail. Depending on requirements, solutions include:

1. Keep `removeMessage=false` during the window requiring replay, cleaning up after processing confirmation.
2. Use appropriate transactions/acks between store and consumer.
3. Use a durable idempotency key to prevent duplicate side effects.
4. Design an outbox/saga when multiple systems do not share a single transaction.
5. Have a recovery path when the token no longer has an entry yet the business state is unknown.

No single option guarantees exactly-once across broker, store, and database by default.

### 14.4. Decision table

| Business need | Design direction |
|---|---|
| Single worker reads once; no replay | May consider remove=true |
| Multiple workers need same payload | remove=false with cleanup |
| Token may be redelivered by broker | Replay policy or transaction/idempotency |
| Data may only be kept for a limited time | Controlled retention/TTL |
| Document retention laws apply | Choose policy matching compliance requirements |
| Highly sensitive data | Least privilege, encryption, and timely deletion |

## 15. Missing, mistyped, or expired tokens

A UUID-shaped token does not guarantee it points to an existing message in the store.

| Situation | Possible cause | Handling direction |
|---|---|---|
| Token payload is String | Serializer/adapter converted type wrongly | Convert to UUID with validation or reject |
| UUID never checked in | Forged token/wrong namespace | Lookup failure/audit |
| UUID already checked out with remove=true | One-time claim | Cannot replay successfully with same token |
| Entry deleted by TTL | Retention too short for queue | Expired/recovery flow |
| Temporary store error | Database/network outage | Bounded retry, backoff |
| Store not shared across instances | Miswiring | Fix backend/namespace |
| Entry fails deserialization | Schema/version mismatch | Compatibility/migration |
| Token belongs to another tenant | Unauthorized | Deny/audit |
| Two consumers claim same token | Race | Transaction/locking & policy |
| Stored payload was mutated | Mutable object/in-memory reference | Snapshot/immutability |

### 15.1. Missing token is not a Filter rejection

A Filter returning `false` because a valid message does not belong to a processing branch is a **normal business decision**. Failing to retrieve a message because the token is invalid, already deleted, or the store errored is a **lookup/lifecycle failure**. Proper classification prevents hiding data incidents under a "skipped" metric.

### 15.2. Retrying the right error types

- Store timeout/network failure: can perform bounded retry.
- Mistyped or malformed token: do not retry indefinitely.
- Expired or deleted token: retrying the same token will not bring the entry back.
- Business handler error after check-out: needs a replayable policy or compensation.
- Unauthorized token: do not use retries to bypass authorization.

On a `DirectChannel`, exceptions may bubble up to the sender. In asynchronous flows, errors may route through an error channel/adapter depending on topology. **Do not assume every error automatically routes to errorChannel merely because the header is present.**

## 16. Is a claim token a secret?

A token is a **reference for looking up data**. A UUID is harder to guess than a sequential number, but it **is not an authentication or authorization mechanism**. If a check-out endpoint accepts a token from an external party and returns content without checking permissions, the token can be abused as a bearer capability.

### 16.1. Required layers of protection

1. **Authentication**: identify the user/service requesting check-out.
2. **Authorization**: verify permission to view the corresponding content.
3. **Tenant isolation**: look up only data belonging to a valid tenant.
4. **Least privilege**: only endpoints needing the payload may read the store.
5. **Encryption at rest/in transit**: protect originals in the store and over the network.
6. **Audit**: track successful/failed claim attempts.
7. **Retention**: define when data must be deleted or archived.
8. **No token leakage**: avoid tokens in public URLs/logs/metrics.

A cross-service solution can place a **Claim Access Service** between token consumers and the store to enforce permissions before looking up data; do not let clients send arbitrary UUIDs directly to an unprotected endpoint.

### 16.2. Token payload does not mean safe data

~~~text
Message:
  payload = UUID token
  headers:
    customerEmail = private@example.invalid
    rawContentPreview = ...
    accessToken = SECRET
~~~

Even without the original payload, these headers can still leak data. Define a **header allowlist** at the channel/broker boundary instead of trusting check-in to strip all metadata automatically.

### 16.3. Do not log tokens indiscriminately

Claim tokens have high cardinality and may be sensitive references. In metrics, use `flow`, `result`, `reasonCode`; in controlled logs/traces, record tokens only when truly needed for debugging and with appropriate redaction/retention policies.

## 17. Headers, traceId, and correlation

A Spring message has both payload and headers. Claim Check intentionally replaces the payload; metadata must be managed separately.

| Metadata | Role | Principle |
|---|---|---|
| `traceId` | Track stages | Preserve per observability contract |
| `businessCorrelationId` | Tie processing to document/order | Do not conflate with claim token |
| `replyChannel` | Gateway reply path | Be careful across brokers/cross-JVM |
| `errorChannel` | Exception handling path | Do not blindly copy internal objects |
| `tenantId` | Data scope | Use only after authentication |
| `contentType` | Payload type | May need changing when payload becomes UUID |
| `MessageHeaders.ID` | Instance ID | Do not use as business ID |
| `schemaVersion` | Payload format | May need two versions: stored message and token protocol |

### 17.1. contentType may no longer fit after check-in

If the original message declares `contentType=application/pdf`, yet the payload after check-in is a UUID, downstream adapters might misinterpret the token as PDF bytes. When bridging brokers/HTTP, define the codec for the token message and corresponding header mapping. Do not carry over headers from the original payload without checking their new meaning.

### 17.2. Gateway reply and tokens

A Gateway can send a request and wait for a reply. But if Claim Check In pushes the token into a broker, a worker takes minutes to process, and then Claim Check Out runs, a temporary `replyChannel` from the old request may have expired.

A more suitable pattern for long-running processing:

~~~text
POST /documents
  -> 202 Accepted + trackingId

DocumentRequest -> Check-in -> Token queue
  -> Worker -> Check-out -> Process
  -> DocumentProcessed event
  -> Status store

GET /documents/DOC-1001/status
  -> Processing status
~~~

The API's `trackingId` is a workflow identifier, not necessarily the internal UUID token. Do not expose internal tokens to external clients without proper access control policies.

### 17.3. businessCorrelationId differs from claim token

A business process might check in multiple times and receive multiple tokens across processing rounds. If you use the token as the overall business idempotency key, the same document could be treated as multiple distinct requests. Keep a stable `documentId`/`eventId` in business state, separate from the store lookup key.

## 18. Immutability of stored payloads

A Java object can be modified unintentionally if the payload or nested fields are mutable.

~~~java
public final class MutableDocument {
    private byte[] content;

    public MutableDocument(byte[] content) {
        this.content = content;
    }

    public byte[] getContent() {
        return content;
    }

    public void setContent(byte[] content) {
        this.content = content;
    }
}
~~~

If the object is shared across multiple handlers and an in-memory store holds a reference, modifying `content` after check-in can cause retrieved data to differ from what was expected.

Recommendations:

- Use immutable DTOs if possible.
- Defensively copy mutable arrays/collections.
- Use a serializer to store an appropriate snapshot when persistence is needed.
- For large blobs, consider content checksums and immutability in object storage.
- Check schema/serialization compatibility across upgrades.

Claim Check **does not automatically make every payload immutable**.

## 19. Claim Check with Splitter and Aggregator

If a message containing `List<InvoiceLine>` is checked in first and then sent straight to a Splitter, the Splitter only sees the **UUID token**, not the original collection.

~~~text
List<InvoiceLine> -> Check-in -> UUID token -> Splitter
                                         (no List left to split)
~~~

Two common places to use Claim Check:

### 19.1. Split then check in each part

~~~mermaid
flowchart LR
    IN["Batch<List<Line>>"] --> SP["Splitter"]
    SP --> CI["Check-in each part"]
    CI --> Q["Token queue"]
    Q --> CO["Check-out"]
    CO --> AG["Aggregator"]
~~~

Pros: each part avoids carrying a large payload on the queue. Cons: creates many entries in the store; correlation/sequence headers must be preserved so the Aggregator groups correctly. **Each part may have its own token while sharing the same business correlation key.**

### 19.2. Aggregate then check in large output

~~~mermaid
flowchart LR
    M["N parts"] --> AG["Aggregator"]
    AG --> D["Large aggregated payload"]
    D --> CI["Check-in"]
    CI --> STORE[("MessageStore")]
    CI --> Q["Token queue"]
    Q --> CO["Check-out"]
~~~

Makes sense when a group's output is large while many subsequent steps only need tracking metadata. Do not use each part's individual token as `correlationId` in place of the business group key.

### 19.3. Filter dropping a token can leave an orphan entry

~~~text
Original -> Check-in -> Token -> Filter rejects
                             -> No check-out
                             -> Original remains in MessageStore
~~~

If a message is dropped before check-out, there must be an appropriate retention/cleanup policy. Do not delete prematurely if another Publish–Subscribe branch is still using the same token.

## 20. Measuring capacity, latency, and cleanup

MessageStore is not an infinite store that needs no operations. A system with many large documents needs to track:

| Metric | Purpose |
|---|---|
| `claim_check_in_total` | Messages stored |
| `claim_check_out_total` | Messages claimed |
| `claim_check_lookup_failure_total` | Missing tokens or lookup errors |
| `claim_check_store_entries` | Remaining stored entries |
| `claim_check_store_bytes` | Bytes currently used |
| `claim_check_entry_age_seconds` | Entry age |
| `claim_check_expired_total` | Entries expired |
| `claim_check_cleanup_failure_total` | Cleanup errors |
| `claim_check_restore_latency_seconds` | Restoration latency |
| `claim_check_access_denied_total` | Unauthorized access attempts |

### 20.1. TTL must match queue backlog

If the store retains entries for 5 minutes while a token is processed from the broker after 30 minutes, the consumer receives a validly formatted UUID with no remaining entry. Retention must be chosen based on **maximum queue wait time, retries, dead-letter, and recovery window**, or have a clearly published expired-token flow.

### 20.2. Do not equate remove=true with a full retention policy

Data may remain in backups, replicas, and logs even after the primary entry is deleted. For personal data or financial/legal documents, a system-wide retention/deletion policy is required, not just a transformer setting.

### 20.3. Structured logs with limited data

~~~text
flow=document-claim
operation=CHECK_OUT
documentId=DOC-1001
claimResult=SUCCESS
storeBackend=jdbc
durationMs=24
traceId=trace-1001
~~~

This example omits the document payload and token. If `documentId` is also sensitive, logs must follow identifier protection policies.

## 21. Common pitfalls

### Pitfall 1 — Thinking check-in only adds a token header

**Symptom:** A downstream Router still tries to accept `DocumentRequest`, while the payload is already a UUID.

**Fix:** Check the payload type after check-in and update endpoint contracts.

### Pitfall 2 — Thinking all headers disappear

**Symptom:** Token messages still carry PII/authorization in headers.

**Fix:** Design a header allowlist and test propagation.

### Pitfall 3 — Token is a String while check-out expects a UUID

**Symptom:** An adapter serialized UUID to String without decoding before check-out.

**Fix:** Add a String → UUID converter at the boundary, with validation and tests.

### Pitfall 4 — Two endpoints use two different stores

**Symptom:** UUID looks valid, yet lookup always fails.

**Fix:** Verify backend/namespace and actual bean wiring.

### Pitfall 5 — Using SimpleMessageStore cross-instance

**Symptom:** Instance B lacks the message checked in by Instance A.

**Fix:** Shared/persistent store or appropriate key routing.

### Pitfall 6 — Early deletion breaks retries

**Symptom:** Check-out uses `remove=true`, handler fails, broker redelivers, yet the entry is gone.

**Fix:** Transaction/replay policy, or `remove=false` with cleanup after business success.

### Pitfall 7 — No cleanup causes memory growth

**Symptom:** `SimpleMessageStore` keeps entries from every check-in.

**Fix:** `remove=true` where appropriate or explicit TTL/retention/cleanup.

### Pitfall 8 — Using the token as an access credential

**Symptom:** Anyone with a UUID can view documents from a public API.

**Fix:** Authentication, authorization, tenant isolation, audit.

### Pitfall 9 — Durable broker paired with non-durable store

**Symptom:** Restart loses original data even though tokens remain on the queue.

**Fix:** Align durability/lifecycle of both sides.

### Pitfall 10 — Keeping the old contentType

**Symptom:** Adapter attempts to deserialize the token as the original PDF/JSON document.

**Fix:** Design an explicit codec/token message schema.

### Pitfall 11 — Filter drops token without cleanup

**Symptom:** No check-out happens, leaving the stored message orphaned.

**Fix:** Outcome-based cleanup, accounting for other consumers that might still need the token.

### Pitfall 12 — Token replaces business ID

**Symptom:** Re-checking in a document produces a new token, causing downstream to treat it as a different business request.

**Fix:** Keep `documentId`/`eventId` stable for idempotency.

### Pitfall 13 — Successful check-out mistaken for business completion

**Symptom:** Marking DONE right upon retrieving the message, even though the subsequent handler has not committed.

**Fix:** Measure business outcome downstream.

### Pitfall 14 — Store entry contains a mutable object

**Symptom:** Restored data differs from its content at check-in time.

**Fix:** Immutable DTOs, defensive copying, or serialized snapshots.

## 22. Practice exercises

**Exercise 1 — Verify token:** Send `DocumentRequest` into `ClaimCheckConfiguration`; assert the token channel receives a `UUID` payload, not `DocumentRequest`.

**Exercise 2 — Verify store:** Take the UUID from output and call `MessageStore.getMessage(token)`; confirm the original message has the right content.

**Exercise 3 — Check-out:** Send the token to the checkout channel; confirm the payload is restored; with `remove=true`, confirm the entry is gone afterward.

**Exercise 4 — Multiple claims:** Create a `claimCheckOut(store, false)` flow and try claiming again; propose a cleanup policy for this case.

**Exercise 5 — Wrong token:** Send a String document ID, then an un-checked-in UUID; distinguish payload type errors from lookup errors.

**Exercise 6 — Headers:** Send input with `traceId` and a custom sensitive header; inspect the token message and design an allowlist before publishing through a broker.

**Exercise 7 — Router:** Route by verified classification using only minimal metadata after check-in; do not assume the Router can read content from a UUID.

**Exercise 8 — Filter rejection:** Have a Filter drop a token before check-out; determine where to clean up the stored message without affecting other consumers.

**Exercise 9 — Retry:** Make the handler fail after `check-out(remove=true)`; identify the failure window and propose a recovery policy.

**Exercise 10 — Multi-instance:** Check in on JVM A, check out on JVM B; explain why two separate `SimpleMessageStore` instances do not work.

**Exercise 11 — TTL:** Tokens may sit in the queue for 30 minutes and retry for 2 hours; design retention, expired-token outcome, and metrics.

**Exercise 12 — Security:** Simulate a tenant B user holding tenant A's UUID token; design authorization before reading the store.

**Exercise 13 — Splitter/Aggregator:** Split a batch into three parts, check in each part, verify correlation metadata, and avoid grouping by UUID token.

**Exercise 14 — Object storage:** Design a custom Claim Check for very large blobs and compare it with the built-in `MessageStore`.

### Self-check questions

1. How does Claim Check differ from payload compression?
2. Does Spring Claim Check In store the message or only the payload?
3. What type is the payload after check-in?
4. Is the token placed in a header instead of the payload by default?
5. Why does "token only" not mean all headers have been removed?
6. How does a claim token differ from `documentId`, `traceId`, and `correlationId`?
7. What conditions does check-out require to retrieve successfully?
8. Does `removeMessage` default to `true` or `false`?
9. When does `remove=true` cause retries to fail?
10. Is `SimpleMessageStore` durable across restarts?
11. Does a UUID token automatically grant permission to view the document?
12. If a token turns into a String via JSON, what must be done before check-out?
13. Why is a durable broker with a volatile store a risky combination?
14. What storage problem occurs when a Filter rejects a token before check-out?
15. Why shouldn't `contentType=application/pdf` be kept for every UUID token?
16. Does check-out prove the downstream DB has committed?
17. Which metrics are needed to detect store growth and lookup failures?
18. In Splitter/Aggregator, can a token replace the correlation key?

## 23. Implementation checklist

- [ ] Clearly defined original message payload, store entry, and UUID token payload.
- [ ] Check-in and check-out share the same backend/namespace.
- [ ] `MessageStore` durability matches queue/retry/restart requirements.
- [ ] `removeMessage=true/false` configured intentionally.
- [ ] TTL, retention, cleanup, and store quotas in place.
- [ ] UUID token is serialized/deserialized with the proper type across protocols.
- [ ] Token is not used in place of `documentId`/`eventId`.
- [ ] Validation, authentication, and authorization enforced at check-out.
- [ ] Tenant isolation, encryption, and auditing in place.
- [ ] Header allowlist configured; no PII/tokens leaked in logs/metrics.
- [ ] `contentType`/token message schema rules defined.
- [ ] Retry/ack/transactions do not delete data before a recovery path exists.
- [ ] Idempotency implemented on handlers with side effects.
- [ ] Integration tests cover Spring Integration channels and `MessageStore`.
- [ ] Tests cover wrong token, missing/expired token, second claim, and restart.
- [ ] Metrics cover entry count, store bytes, token age, and restore latency.
- [ ] With Splitter/Aggregator, correlation/sequence headers remain valid.
- [ ] Cleanup policy exists when tokens are rejected by a Filter.
- [ ] Data retention/deletion aligns with compliance requirements.

## 24. Summary

**Message carries only the claim token** is shorthand for Claim Check: **the new message traveling through the flow has only a UUID token as its payload**, while **the original message is saved in a `MessageStore`** for later restoration. `ClaimCheckInTransformer` performs check-in and `ClaimCheckOutTransformer` performs check-out. They can be configured with the Java DSL `claimCheckIn(store)` and `claimCheckOut(store, removeMessage)`.

A token-only payload must not be misunderstood as meaning all headers are clean or security is automatically solved. `removeMessage=false` is the default; enabling `true` helps claim-once scenarios but can break replay if downstream fails. Store lifecycle, cleanup, transactions, TTL, read permissions, business correlation, and idempotency all require explicit design.

In the **SPRING_INTEGRATION_PATTERN** module, Claim Check enables Routers, Filters, and metadata-processing steps to transport **small references instead of large payloads**, while Transformers, Splitter/Aggregator, Gateways, retries, and error channels continue collaborating under their own contracts. Restore data only where truly needed, test tokens and stores together, and clearly distinguish **claimed** from **business-completed**.

### References

- Spring Integration Reference — Claim Check: https://docs.spring.io/spring-integration/reference/claim-check.html
- Spring Integration Reference — Message Store: https://docs.spring.io/spring-integration/reference/message-store.html
- Spring Integration Reference — Java DSL: https://docs.spring.io/spring-integration/reference/dsl.html
- Spring Integration API — ClaimCheckInTransformer: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ClaimCheckInTransformer.html
- Spring Integration API — ClaimCheckOutTransformer: https://docs.spring.io/spring-integration/api/org/springframework/integration/transformer/ClaimCheckOutTransformer.html
- Spring Integration API — BaseIntegrationFlowDefinition: https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html
- Spring Integration API — MessageStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/MessageStore.html
- Spring Integration API — SimpleMessageStore: https://docs.spring.io/spring-integration/api/org/springframework/integration/store/SimpleMessageStore.html
- Spring Integration Reference — Router: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference — Aggregator: https://docs.spring.io/spring-integration/reference/aggregator.html
- JUnit 5 User Guide — JUnit Jupiter: https://junit.org/junit5/docs/current/user-guide/


