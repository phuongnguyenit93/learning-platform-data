# Headers That Must Not Cross Boundaries in Spring Integration

## Learning Objectives

After this lesson, you will be able to:

- Clearly distinguish **internal boundaries between `MessageHandler`s**, **thread/queue boundaries**, **storage/serialization boundaries**, **process/service boundaries**, **protocol boundaries**, **security/tenant boundaries**, and **request/reply response boundaries**.
- Explain why Spring Integration usually **propagates headers** when a message-producing endpoint builds a new output; do not assume secret headers, internal channel objects, or source-specific metadata are automatically stripped.
- List the groups of headers that **must not be passed through verbatim**: Spring `replyChannel`/`errorChannel`, misused `id`/`timestamp`, broker ACK/channel/delivery tags, Kafka offset/`ConsumerRecord` metadata, JMS/AMQP received-only fields, tokens/cookies/PII, raw tenant/role claims, socket/session objects, temporary processing metadata, and non-serializable header types.
- Use `HeaderFilter`, `MessageBuilder.removeHeader/removeHeaders`, `AbstractMessageProducingHandler.setNotPropagatedHeaders(...)`, and Java DSL `notPropagatedHeaders(...)` **in the right places and within their proper limits**.
- Distinguish `notPropagatedHeaders` from `readOnlyHeaders`: configuring read-only headers to restrict copying/overriding during message construction **is not equivalent** to a security allowlist policy at a network boundary.
- Understand how a transformer returning a **payload** versus returning an entire **`Message<?>`** leads to different propagation rules; explain why bridges/routers are not governed by the same `notPropagatedHeaders` rules as message-producing handlers.
- Configure outbound `HeaderMapper`/Spring Kafka header mappers to build **per-protocol allowlists**, distinguishing header mapping from payload conversion, destination routing, and ACK.
- Explain why `HeaderChannelRegistry` can turn a Spring `MessageChannel` into a token in certain message storage/transport flows, yet **is not** a way to hand reply/error routing control to arbitrary external clients or make replies durable across restarts.
- Design policies against **credential leaks, cross-tenant access, SSRF, header injection, replay/dedup with the wrong ID, stale ACK handles, serialization failures, and route overrides**.
- Write JUnit/`IntegrationFlow` tests, inspect headers before and after boundaries, verify wire metadata in HTTP/JMS/AMQP/Kafka, and handle retries/recovery/lifecycles.

This lesson belongs to the **Message Headers** chapter of the **SPRING_INTEGRATION_ADAPTERS** module. Within this module, we connect external systems using inbound/outbound adapters, gateways, pollers, and `MessageChannel`, and practice File, SFTP, HTTP, JMS, AMQP, Kafka, and MongoDB/database integrations. Therefore, header boundaries must be tied to **message contracts, access permissions, ACK/reply paths, error handling, and connection lifecycles**.

> **Scope:** examples use Java 17+, Spring Boot 3.x, and Spring Integration 6.x per a matching BOM. Some Java DSL overloads and behaviors may differ in Spring Integration 7.x/Spring Kafka 4.x. Never use an API without checking the Javadoc for your exact version. All URIs, IDs, partners, and databases are illustrative data.

## 1. The Problem: The Message Has the “Right Payload” Yet Headers Cause Incidents

An HTTP inbound endpoint receives an order from a partner:

~~~http
POST /orders/events HTTP/1.1
Content-Type: application/json
Authorization: Bearer <redacted>
X-Tenant-Id: tenant-a
X-Role: admin
X-Event-Id: evt-1001
X-Trace-Id: tr-9c

{"eventId":"evt-1001","orderId":"ord-101","status":"PAID"}
~~~

Suppose an adapter/gateway creates a Spring Message with:

~~~text
payload:
  order event JSON

headers:
  id = <Spring UUID>
  timestamp = <Spring epoch millis>
  replyChannel = <temporary MessageChannel>
  errorChannel = <error flow MessageChannel>
  Authorization = "<token>"
  X-Tenant-Id = "tenant-a"
  X-Role = "admin"
  X-Event-Id = "evt-1001"
  X-Trace-Id = "tr-9c"
  sourceSystem = "partner-http"
~~~

If the application passes this message through multiple handlers and then sends it onward to **JMS/Kafka/AMQP/HTTP/SFTP**, propagating headers “verbatim” can:

1. **Leak the source token** to an unauthorized partner.
2. Allow an external user to **override tenant/role** if business handlers trust the header values.
3. Pass a Spring `MessageChannel` object as a JMS property, causing serialization/conversion exceptions.
4. Resend broker delivery/ACK metadata into a context where it is **no longer valid**.
5. Use Spring `id` as an idempotency key, creating duplicate records on redelivery/rebuild.
6. Echo RabbitMQ `x-*` federation metadata, causing the broker to mishandle replies.
7. Let a raw header decide the Kafka topic, HTTP URL, or SFTP directory, causing **unauthorized routing/SSRF/path traversal**.
8. Keep debug/attempt headers around too long, corrupting audits/metrics and recovery.

A **header boundary** is where we decide which metadata is allowed to **continue existing**, which metadata has meaning **only within a segment of the flow**, and which metadata must be **converted into a validated application contract**.

## 2. A “Boundary” Is Not Just an HTTP Network Boundary

There are many boundary types with different rules:

| Boundary | Example in Spring Integration | Risk if Headers Are Copied |
|---|---|---|
| **Internal processing** | Transformer → ServiceActivator | Internal tokens/temporary flags travel beyond their needed scope |
| **Thread** | `DirectChannel` → `ExecutorChannel` | `ThreadLocal`/ACK handle/session context becomes invalid |
| **Queue/store** | `QueueChannel` backed by `MessageStore` | Non-serializable object headers or stale state upon restore |
| **Process/restart** | `MessageStore` → new app instance | Temporary `replyChannel` bean/object cannot be resolved |
| **Protocol** | Message → HTTP/JMS/AMQP/Kafka | Incompatible types/formats/semantics |
| **Security/tenant** | Public HTTP ingress → internal tenant-aware service | External headers get promoted to trusted privileges |
| **External partner** | Internal event → partner API | Leaks credentials, PII, topology |
| **Request/reply** | Gateway request → response | Spoofed `replyChannel`/correlation/response metadata |
| **Observability** | Message → logs/metrics/DLQ | Tokens/PII or high-cardinality data leaked |
| **Storage/business** | Message → MongoDB/JDBC row/document | Technical headers stored long-term, or business ID not persisted |

A **`DirectChannel`** boundary is not like a **Kafka broker** boundary. Filtering in the wrong place can strip headers needed for internal routing, or filter too late after a secret has already reached a client.

### 2.1. Example of Dividing Zones

~~~mermaid
flowchart LR
  U["Untrusted input<br/>HTTP/JMS/SFTP"] --> A["Ingress authentication<br/>+ input validation"]
  A --> R["Raw Spring Message<br/>external metadata"]
  R --> N["Normalize / sanitize<br/>trust boundary"]
  N --> B["Business Message<br/>trusted app headers"]
  B --> S["Create outbound DTO<br/>minimal metadata"]
  S --> P["Protocol HeaderMapper<br/>destination allowlist"]
  P --> O["HTTP / Kafka / JMS / AMQP"]
  B --> D["Persistent inbox/outbox<br/>business ID + payload"]
~~~

In the diagram:

- **Ingress** authenticates/validates inputs.
- **Normalizer** converts external keys into canonical application keys.
- **Business flow** uses only trusted state and validated data.
- **Outbound serializer/`HeaderMapper`** picks headers allowed **for each specific target**.
- **Persistence** stores minimal business fields rather than dumping raw `MessageHeaders`.

## 3. How Does Spring Integration Propagate Headers by Default?

Per the Spring Integration Reference, most **message-producing endpoints**, when processing a message and producing a new output, **copy incoming headers to the output** if the output does not already have that key. Specifically:

- If a transformer/service method returns a new **payload**, the framework normally creates a new Spring Message and propagates incoming headers.
- If a transformer returns **a complete `Message<?>`**, the framework treats that message as code-crafted output; the developer explicitly defines the output headers.
- When an incoming header key already exists on the output, the output value takes precedence; default propagation does not overwrite it with the input value.
- `MessageHeaders.ID`/`TIMESTAMP` are read-only core headers, typically generated per new message rather than taken from arbitrary user-supplied values.

**Key takeaway:** automatic propagation **is not a security policy**. If a service merely turns a `String` payload into a DTO, raw `Authorization` or client-controlled `X-Role` can still remain in downstream headers unless the developer filters/removes them.

### 3.1. Example: “Payload-Only Transform” Still Carries Headers

~~~java
import org.springframework.integration.annotation.Transformer;
import org.springframework.messaging.handler.annotation.Payload;

public final class EventTransformer {

    @Transformer(inputChannel = "rawOrders",
                 outputChannel = "normalizedOrders")
    public String transform(@Payload String payload) {
        return payload.trim();
    }
}
~~~

If the source message contains `X-Untrusted-Role`, a transformer returning only a `String` **does not automatically remove** that header. You must add a `HeaderFilter`/propagation policy or build a clean message explicitly.

### 3.2. A Transformer Returning a Message Is a Different Case

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> toCanonicalMessage(
        Message<String> original) {

    String canonicalBody = original.getPayload().trim();

    return MessageBuilder.withPayload(canonicalBody)
        .setHeader("sourceSystem", "partner-http")
        .setHeader(
            "businessEventId",
            verifiedBusinessEventId)
        .setHeader(
            "trustedTenantId",
            authorizedTenantId)
        .build();
}
~~~

This is a **service method fragment**: `verifiedBusinessEventId` and `authorizedTenantId` must be verified beforehand, and when used as a transformer, the return type must actually be `Message<?>`. Because it builds a message **from scratch** with `withPayload(...)`, this code **does not automatically copy all headers** from `original`. Still, check endpoint wiring and propagation behavior for your version to ensure output headers are not unexpectedly merged.

### 3.3. Header Values Can Still Be Mutable

Spring `MessageHeaders` exposes an unmodifiable map interface, yet values themselves can be `List`, `Map`, or mutable objects. Copying a reference is not equivalent to a thread/process-safe deep copy. Before serializing, normalize to `String`/`byte[]`/immutable DTOs or drop them altogether.

## 4. Matrix: Header Groups That Usually Must Not Cross Boundaries

**This is an architectural policy, not a list the framework blocks 100% automatically.** Depending on the destination, there are deliberate exceptions allowed by design.

| Header or Group | Should Not Cross Which Boundary? | Reason / Alternative |
|---|---|---|
| `replyChannel` as a `MessageChannel` object | Broker, persistent store, remote service | Runtime object reference; use a gateway contract or an internal TTL registry |
| `errorChannel` as a `MessageChannel` object | Broker, external service, restart | Internal routing object; store a durable error event instead of the object |
| `id` / `timestamp` | External business identity | Spring message metadata, not a business key; use `businessEventId` |
| `routingSlip` / runtime route state | External endpoint | Prevent clients from controlling internal routes |
| `Authorization`, Cookie, refresh token | Another partner, logs/DLQ | Audience-scoped secrets/credentials; use separate outbound auth |
| `trustedTenantId`, internal roles | Unauthorized tenant/partner | Tenant isolation and least privilege |
| Raw `X-Tenant-Id` / `X-Role` | Trusted business context | Unauthenticated; use only after validation/authorization |
| JMS delivery/session/provider handles | Outside JMS listener/session | Become invalid; managed by the broker |
| AMQP `deliveryTag`/channel/`redelivered`/received exchange | HTTP/Kafka/JMS or new AMQP publish | Received-only metadata, not outbound control |
| Kafka received offset/partition/topic/consumer ACK | External general-purpose headers | Tied to `ConsumerRecord` and consumer group/lifecycle |
| TCP connection ID / socket | Restart or another partner | Runtime connection context |
| SFTP/FTP session / raw remote path | External routing/persistence | Auth/path scope and traversal risk |
| Spring error `ErrorMessage.payload(Throwable)` | Public API, unprotected DLQ/logs | Exceptions contain stacks, secrets, PII; use safe error codes |
| `MessageHistory`/debug trace | Uncontrolled public wire/logs | Leaks internal flow topology |
| `contentType` mismatched with body | Protocol destination | Verify converter/body; do not copy blindly |
| Java `Class<?>`, `MessageChannel`, `InputStream` objects | JMS/Kafka/JSON serialization | Unsupported/non-serializable/mutable runtime state |
| Internal retry attempts/lease owner | Another downstream partner | Prevent stale worker state from affecting business logic |
| Untrusted `spring_json_header_types` | Cross-trust Kafka boundary | Type metadata requires schema/trusted packages |

### 4.1. Three Decision Levels

When reviewing a specific header, pick one of three categories:

1. **DROP** — the header only has meaning in the source/runtime or contains unnecessary secrets.
2. **TRANSFORM** — convert an external/broker-specific value into a validated application field (e.g., `X-Partner-Event-Id → businessEventId`).
3. **ALLOW** — forward the value **only after validation** and only to destinations authorized by the contract.

For example, `businessEventId` is usually **ALLOW**ed to Kafka/JMS/HTTP, but its type/length and scope must be canonicalized. Inbound `Authorization` must usually be **DROP**ped on outbound; the outbound service can attach a **new** token with the proper partner audience.

### 4.2. There Is No Such Thing as “Safely Copy All MessageHeaders”

A `Message<?>` can carry all of:

~~~text
Reply routing:
  replyChannel, errorChannel

Business:
  businessEventId, schemaVersion

Transport:
  kafka_receivedTopic, kafka_offset, amqp_deliveryTag

Security:
  Authorization, X-Tenant-Id, principal/session

Observability:
  traceId, history

Infrastructure:
  MessageChannel, ClientSession, acknowledgment object
~~~

Sending that entire map to another protocol mixes values with **different types, access permissions, and lifetimes**. The safe approach is building a **destination-specific contract**.

## 5. Mechanism 1 — HeaderFilter in a Spring Integration Flow

`HeaderFilter` is an Enterprise Integration Pattern that removes selected header keys from a Spring Message before it continues downstream.

### 5.1. Java DSL

~~~java
package example.headerboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class InboundBoundaryFlow {

    @Bean
    public IntegrationFlow sanitizeInboundFlow() {
        return IntegrationFlow.from("rawInbound")
            .headerFilter(
                "Authorization",
                "Cookie",
                "X-Untrusted-Role",
                "X-Untrusted-Tenant")
            .channel("sanitizedInbound")
            .get();
    }
}
~~~

This creates **a flow** from `rawInbound` to `sanitizedInbound`. It removes **only exact matching keys**; if the mapper changed casing/names, filter the normalized keys. Never use a Java DSL filter to replace HTTP authentication that must run **before** it.

### 5.2. XML HeaderFilter

~~~xml
<!-- Requires xmlns:int and matching channel beans. -->
<int:header-filter
    input-channel="rawInbound"
    output-channel="sanitizedInbound"
    header-names="Authorization,Cookie,X-Untrusted-Role,X-Untrusted-Tenant"/>
~~~

This is an alternative to Java DSL; do not configure both filtering the same flow without a clear reason.

### 5.3. Limitations of HeaderFilter

- **Does not remove headers at the source system**; it filters the Spring Message at the step where it is placed.
- **Does not stop another producer from re-adding the same header** later.
- **Does not create an automatic allowlist**. An unfamiliar new header will slip past a blocklist unless explicitly listed.
- **Does not cover every boundary**; if another route branch bypasses the filter, that branch still receives the original headers.
- **Does not inspect nested payloads**. If a token sits inside the JSON body, filtering `MessageHeaders` will not strip it from the body.
- **Not a way to arbitrarily alter `id`/`timestamp`**; those two core headers are read-only and have specific configuration constraints.
- **Cannot replace authentication/authorization**: raw tenant/role headers might already affect routing before the filter executes.

**Use blocklists to guard an internal flow with known headers; use allowlists or build clean DTOs at external or multi-tenant boundaries.**

## 6. Mechanism 2 — MessageBuilder, removeHeader, and Building Clean Messages

When you need to clone a message and drop specific headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> stripSecrets(Message<String> input) {
    return MessageBuilder.fromMessage(input)
        .removeHeader("Authorization")
        .removeHeader("Cookie")
        .removeHeader("X-Untrusted-Role")
        .removeHeader("debugInternal")
        .build();
}
~~~

`fromMessage(input)` starts from the input's headers and removes the specified keys. This is a **blocklist**. If a new unlisted header arrives, it may still be copied.

### 6.1. When a Boundary Needs a Stronger Allowlist

Create a **new message from the payload** and copy only a few explicit fields:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public Message<String> toPartnerMessage(
        Message<String> original,
        String trustedEventId,
        String sanitizedTraceId) {

    return MessageBuilder.withPayload(original.getPayload())
        .setHeader("businessEventId", trustedEventId)
        .setHeader("appTraceId", sanitizedTraceId)
        .setHeader("schemaVersion", 2)
        .build();
}
~~~

**Benefits:** the output contains only approved business/application headers (plus core framework headers). **Conditions:** `trustedEventId` and `sanitizedTraceId` are validated, and the developer does not copy `replyChannel` or `errorChannel` from the input into the new builder.

### 6.2. MessageBuilder Does Not Protect Against Self-Contradiction

If you write:

~~~java
Message<?> bad = MessageBuilder.withPayload(payload)
    .setHeader("businessEventId", rawHeaderValue)
    .build();
~~~

then even though you built a new message, the app still **puts untrusted data** into a trusted contract. Building a clean message is safe only with validation/authorization, not simply by calling `withPayload()`.

### 6.3. A Header Value Can Contain Secrets Even If Its Name Looks Harmless

For example, a client uses `X-Trace-Id` to send a token string or JSON PII. Allowlisting **names** is not enough: validate the **value**'s type, charset, maximum length, semantics, and logging policy. Never dump `message.getHeaders().toString()` in production loggers.

## 7. Mechanism 3 — notPropagatedHeaders on Message-Producing Handlers

Spring Integration supports excluding a set of headers from **automatic propagation** on handlers that **produce output messages**.

### 7.1. Java DSL with ConsumerEndpointSpec

~~~java
package example.headerboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class NotPropagatedFlow {

    @Bean
    public IntegrationFlow redactAtServiceActivator() {
        return IntegrationFlow.from("rawEvents")
            .handle(
                String.class,
                (payload, headers) -> payload.trim(),
                endpoint -> endpoint.notPropagatedHeaders(
                    "Authorization",
                    "Cookie",
                    "X-Internal-*",
                    "debug*"))
            .channel("normalizedEvents")
            .get();
    }
}
~~~

The key point: when the handler in the example returns a **payload**, the framework constructs an output message. `notPropagatedHeaders(...)` prevents the selected header names/patterns from being **copied automatically** from input to output.

### 7.2. Java API on Handlers

Handlers extending `AbstractMessageProducingHandler` can support:

~~~java
handler.setNotPropagatedHeaders(
    "Authorization", "X-Internal-*");

// If the version allows appending instead of replacing the list:
handler.addNotPropagatedHeaders("debug*");
~~~

This is a **fragment**: `handler` must be a bean of the right API type, and method availability should be checked per version. Do not apply this API to a one-way `MessageHandler` that produces no outbound message.

### 7.3. XML Service Activator

~~~xml
<!-- When ServiceActivator produces an output message,
     the specified patterns are not copied automatically. -->
<int:service-activator
    input-channel="rawEvents"
    output-channel="normalizedEvents"
    ref="eventTransformer"
    method="normalize"
    not-propagated-headers="Authorization,Cookie,X-Internal-*,debug*"/>
~~~

Use this fragment **instead of** the Java DSL in Section 7.1. The `eventTransformer.normalize(...)` bean must implement suitable logic, and XML namespaces must match the version.

### 7.4. Patterns and the "*" Case

Patterns use simple pattern matching, such as:

~~~text
Authorization     exact key match
X-Internal-*      matches any key starting with X-Internal-
*Token            matches any key ending with Token
*Secret*          matches any key containing Secret
*
                  special case: propagate no headers
~~~

Depending on the version, the pattern matcher supports prefix/suffix/infix matching via `PatternMatchUtils`. If `"*"` is used as a pattern, **no headers are copied automatically**; other patterns may be ignored in that case.

**Be cautious with `"*"`**: it can drop `businessEventId`/correlation headers that the output still needs. Use it only if business code intentionally rebuilds the full contract.

### 7.5. Does Not Apply to Bridges/Routers Like Service Activators

The Spring Integration docs clearly state that `notPropagatedHeaders` **does not apply** to endpoints that **do not produce modified messages**, such as bridges and routers. They typically forward the **existing message** or change its destination rather than building a copy through this propagation mechanism.

If you need to guarantee headers are filtered before a router or bridge, place a **`HeaderFilter`/`Transformer`** or build a clean message **upstream** of that route.

### 7.6. Propagation Differs from HeaderMapper

- `notPropagatedHeaders` controls which headers **are not copied from input to output inside a specific internal endpoint**.
- `HeaderMapper` controls which headers are **converted into metadata of the target protocol**.

Both may be needed. A message passing through a router with sensitive headers can still reach an outbound adapter if `notPropagatedHeaders` was configured only on another service activator not on that path.

## 8. Mechanism 4 — readOnlyHeaders Is Not an Outbound Security Allowlist

In Spring Integration, `MessageHeaders.ID` and `MessageHeaders.TIMESTAMP` are considered **read-only** by the default builder/framework. Developers should not override them to force a source's business event ID or timestamp.

Spring Integration also allows specifying additional read-only headers via:

- `MessageBuilder.readOnlyHeaders(...)` when constructing messages in certain use cases.
- The global property `spring.integration.readOnly.headers` / `readOnlyHeaders` in `META-INF/spring.integration.properties` depending on version and factory.

The purpose of this mechanism is to **restrict copying/overriding certain headers when messages are rebuilt**; it **does not serve as a network allowlist**.

### 8.1. Do Not Confuse the Three Tools

| Tool | Scope | Question It Solves |
|---|---|---|
| `HeaderFilter` | Fixed flow step | Which keys to remove from a Spring Message before downstream? |
| `notPropagatedHeaders` | Automatic header copy of an output-producing handler | Which keys/patterns must not transfer from input to **the handler's output**? |
| `readOnlyHeaders` | Message builder/factory | Which headers should not be copied/overridden during message construction per builder semantics? |
| `HeaderMapper` | Protocol boundary | Which headers are converted to HTTP/JMS/AMQP/Kafka wire metadata? |
| DTO/explicit fields | External/stored business contract | Which exact business data is authorized to leave the service? |

**Do not replace a security allowlist with a global `readOnlyHeaders` flag.** Over-filtering at the builder can break business flows; failing to filter at the outbound mapper can leak other data.

### 8.2. HeaderFilter and Core Headers

Do not try to use `HeaderFilter` or `HeaderEnricher` to force arbitrary values onto `id`/`timestamp`. The Spring Integration Reference notes that with `DefaultMessageBuilderFactory` these core names are protected and attempting to manipulate them via filter/enricher config can cause startup errors (depending on version).

If you need to keep the **source ID**, put it in a new key like `sourceMessageId` or `businessEventId`; if you need to keep the **event time**, use `occurredAt` rather than overriding the Spring Message timestamp.
## 9. ReplyChannel, ErrorChannel, and HeaderChannelRegistry

Spring Messaging defines:

~~~java
MessageHeaders.REPLY_CHANNEL   // "replyChannel"
MessageHeaders.ERROR_CHANNEL   // "errorChannel"
~~~

Their values can be a `MessageChannel` instance or a `String` interpreted by the framework as a channel name/registry token. A `MessageChannel` object is a **runtime `ApplicationContext` reference**, not a “reply address” to send over Kafka/JMS/HTTP and reuse in another process.

### 9.1. Inside an Internal Gateway, They May Need to Be Kept

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Spring Gateway
    participant H as Service Handler
    participant R as Temporary Reply Channel
    C->>G: request
    G->>H: Message(replyChannel=R)
    H->>R: reply
    R-->>G: response
    G-->>C: result
~~~

If you strip `replyChannel` **too early** in a request/reply flow, the handler may not know where to send the reply. There is no rule to “delete every `replyChannel` immediately on arrival”. Place the filter at the **boundary where the internal reply is truly no longer needed**.

### 9.2. When Crossing a Persistent Queue or Restart

~~~text
gateway → Message(replyChannel=<temporary object>)
        → QueueChannel backed by MessageStore
        → application restart / another worker
        → handler completes
        → where is the old temporary reply channel?
~~~

Serialization may fail, or the restored object no longer represents the original channel. Even with a name, the gateway caller may have timed out long ago.

### 9.3. HeaderChannelRegistry Is a Scoped Solution

Spring Integration provides `HeaderChannelRegistry` and `HeaderEnricher` to turn `MessageChannel`-typed `replyChannel`/`errorChannel` headers into **String/tokens mapped in a registry**, used in certain flows that must serialize headers or send them via JMS.

An XML example from the Spring Integration Reference:

~~~xml
<int:header-enricher
    input-channel="beforeStore"
    output-channel="afterRegistry">
    <int:header-channels-to-string
        time-to-live-expression="120000"/>
</int:header-enricher>
~~~

This requires a registry with an appropriate lifecycle/TTL. **Do not** mistake the token for a durable cross-service/restart reply protocol:

- The default registry is usually **in-memory**; entries can expire.
- The gateway request/temporary reply channel also has its own timeout.
- A String token must never be treated as a bean routing name that an external client is free to supply.
- For durable request/reply across systems, use a **correlation ID + reply queue/topic/database status** that is explicitly designed and authorized.

### 9.4. Decisions for replyChannel/errorChannel

| Context | Policy |
|---|---|
| Synchronous gateway awaiting a reply | Keep within its exact lifecycle |
| Output event sent one-way to Kafka/JMS | DROP runtime channel objects |
| HTTP outbound to a partner | DROP; HTTP gateway manages responses separately |
| Persistent store with temporary reply | Use registry/token with TTL only if app design permits |
| Message stored in BSON/JDBC | Store business correlation, never serialize channels |
| Async RPC across processes/restarts | Durable correlation protocol, not temporary channels |

External `replyChannel`/`errorChannel` headers sent by users **must never** control internal routing beans/channels.

## 10. Kafka Consumer Metadata: Do Not Carry ACK and Offset Elsewhere

Spring Kafka and Spring Integration Kafka can add:

~~~java
org.springframework.kafka.support.KafkaHeaders
~~~

Common headers include `KafkaHeaders.RECEIVED_TOPIC`, `RECEIVED_PARTITION`, `OFFSET`, `RECEIVED_KEY`, `ACKNOWLEDGMENT` in manual ACK mode, and delivery attempt/consumer metadata depending on the container.

### 10.1. What Should Not Be Forwarded

| Kafka Header | Should Not Be Used As | Why |
|---|---|---|
| ACK callback/object | Serialized JMS/HTTP/Kafka header | Runtime object valid only within listener lifecycle |
| Consumer instance | Persistence/wire header | Non-portable connection/context |
| Received partition/offset | Business event ID | Offset is per topic-partition, not globally unique |
| Received topic | Arbitrary outbound destination | Can bypass topic ACLs/data paths |
| Delivery attempt | Durable business completion | Only retry state of the receive layer |
| JSON class type hints | Trusted domain class | Dangerous during deserialization |

A Kafka offset can be stable for **one record in a topic-partition**, but when republishing to another topic or creating a new record, the offset changes. For idempotency, use `businessEventId` in the event contract rather than relying on Spring Message ID or offsets.

### 10.2. KafkaHeaderMapper Has Exclusions, Not a Complete Security Policy

Spring Kafka `SimpleKafkaHeaderMapper`/JSON mappers usually avoid converting core headers `id`, `timestamp`, and Kafka `ConsumerRecord` metadata into raw headers, **but they do not automatically strip arbitrary secret/custom PII headers**.

Outbound allowlist example:

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;

SimpleKafkaHeaderMapper mapper =
    new SimpleKafkaHeaderMapper(
        "!id",
        "!timestamp",
        "businessEventId",
        "appTraceId",
        "schemaVersion");
~~~

This pattern only defines a name policy. With `SimpleKafkaHeaderMapper`, values exported onto the Kafka wire typically need to be `byte[]`; convert `String`s to UTF-8 bytes or configure the mapper's raw `String` behavior accordingly.

**Never export** `KafkaHeaders.ACKNOWLEDGMENT` or consumer objects; they are not business metadata.

### 10.3. Typed Kafka Headers

The JSON header mapper can use `spring_json_header_types`. When headers arrive from an external broker, do not allow users to dictate arbitrary Java types to deserialize:

- Configure controlled trusted packages/schema registries.
- Limit size and nesting depth.
- Never trust a class name as proof of authenticity.
- Do not forward arbitrary object graphs to JMS/HTTP.
- In `Kafka → JMS/HTTP`, create canonical application DTO/header values before outbound.

### 10.4. ACK Still Belongs to the Listener

Kafka ACK/offset commits are managed by the container/transaction/error policy. Copying an ACK callback to a persisted message or another worker process **does not guarantee the callback remains valid**. If the flow is asynchronous, design a durable inbox and ACK at the right stage; test rebalance/shutdown.

## 11. JMS: Received-Only Metadata and Provider-Owned Fields

| JMS Metadata | Meaning | Rule |
|---|---|---|
| `JMSMessageID` | Provider-assigned ID on send | Do not copy as business key |
| `JMSRedelivered` | Broker signals possible redelivery | Do not manually set to simulate redelivery |
| `JMSDestination` | Where the message was delivered | Outbound destination follows server policy |
| `JMSExpiration` | Expiry timestamp of sent message | Do not blindly copy as TTL of a new message |
| `JMSDeliveryMode`/Priority | Producer QoS | Configure via send API/endpoint |
| `JMSCorrelationID` | Protocol request/reply correlation | Map only when required by the contract |
| `JMSReplyTo` | JMS reply `Destination` | Do not let clients pick unauthorized internal destinations |
| Custom JMS properties | Primitives/`String` | Allowlist and convert to proper types |

`DefaultJmsHeaderMapper` supports selected fields and custom properties; it does not turn provider-owned state into safe application business metadata.

### 11.1. Do Not Use JMSMessageID as Business ID

When an app republishes a JMS message, the broker/provider can assign a new `JMSMessageID`. If downstream uses the provider ID as an idempotency key, the same logical event can be treated as a new one. Create a custom `businessEventId` (`String`) property from the domain contract and preserve it across retries.

### 11.2. JMSReplyTo Differs from Spring replyChannel

`JMSReplyTo` has type `jakarta.jms.Destination`, whereas `replyChannel` is a Spring `MessageChannel`/`String`. They have **different types and lifecycles**. A JMS outbound gateway normally manages correlation/replies via configuration rather than copying raw Spring channel objects into JMS properties.

### 11.3. JMS Properties Do Not Accept Arbitrary Objects

Headers of type `MessageChannel`, `InputStream`, `Map<String,Object>`, `Class<?>`, or acknowledgment handles are not guaranteed valid as generic JMS properties. Normalize `businessEventId`/`appTraceId`/`schemaVersion` to `String`/primitives; drop runtime objects. Test against a **real JMS provider**, because unit mapper tests do not prove the broker accepts the types.

## 12. AMQP/RabbitMQ: deliveryTag, Received Fields, and x-*

AMQP inbound can carry:

~~~text
amqp_deliveryTag
amqp_redelivered
amqp_receivedExchange
amqp_receivedRoutingKey
amqp_receivedDeliveryMode
amqp_consumerQueue
amqp_consumerTag
amqp_channel
x-received-from
~~~

These are received/broker runtime metadata, **not** a default contract for new publishes.

### 12.1. Why Not Copy deliveryTag/channel?

- `amqp_deliveryTag` is meaningful only on **that exact AMQP channel/delivery**.
- `amqp_channel` is a runtime object, unusable as a durable remote reference.
- `amqp_redelivered` is set by the broker, not a flag a producer should toggle arbitrarily.
- `amqp_receivedExchange`/`amqp_receivedRoutingKey` describe inbound routing, not authorization to choose an outbound destination.
- `amqp_receivedDeliveryMode` is received information; it does not automatically change producer delivery mode.

### 12.2. Federation Header x-received-from

RabbitMQ federation can attach `x-received-from`. If a gateway mirrors that header verbatim in a reply/publish, the broker may treat the message as a loop and drop it. The Spring Integration Reference recommends filtering broker-proprietary headers or using explicit header names.

~~~java
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

DefaultAmqpHeaderMapper mapper =
    new DefaultAmqpHeaderMapper();

mapper.setRequestHeaderNames(
    "STANDARD_REQUEST_HEADERS",
    "businessEventId",
    "appTraceId",
    "!x-*",
    "!Authorization");
~~~

Some versions exclude `x-*` by default, but a **custom wildcard mapper can alter that policy**. If a broker plugin requires a specific `x-*` header, add a controlled exception rather than allowing all of them.

### 12.3. HeaderMapper Does Not ACK RabbitMQ

Having a Spring header `amqp_deliveryTag` does not mean the app can ACK by sending it over HTTP or Kafka. Broker ACK requires an active channel, the right tag, and the right mode. Across services/brokers, use durable state/idempotency event keys instead of stale tags.

### 12.4. contentType Can Be Kept, If It Matches the Payload

AMQP `contentType` is a common header without an `amqp_` prefix. It can pass between HTTP/AMQP/Kafka if the actual body matches that format. `contentType=application/json` does not automatically serialize a Java object payload into valid JSON; you need a `MessageConverter` and schema validation.

## 13. HTTP: Secret Headers, Spoofed Claims, Hop-by-Hop, and SSRF

An HTTP ingress request can carry:

~~~http
Authorization: Bearer <token>
Cookie: session=...
X-Tenant-Id: tenant-b
X-Role: admin
X-Forwarded-For: 10.0.0.1
X-Target-Url: http://127.0.0.1:8080/internal
X-Request-Id: client-generated
~~~

### 13.1. Do Not Mirror to Outbound HTTP

- **Authorization/Cookie:** credentials for `client → service`, not `service → downstream partner`.
- **X-Tenant-Id/X-Role:** unverified raw claims.
- **X-Forwarded-For/Host:** trust only with a trusted reverse proxy policy.
- **X-Target-Url:** never pick an arbitrary outbound host from client input (SSRF).
- **X-Request-Id:** trace hint that must be validated, not automatically a business ID.
- **Hop-by-hop headers** like `Connection`/`Transfer-Encoding`/`Upgrade`: the HTTP client should manage them per new request, never copy them from old requests.

### 13.2. Building Trusted Context from Authentication

~~~java
Message<?> clean =
    MessageBuilder.fromMessage(incoming)
        .removeHeader("Authorization")
        .removeHeader("Cookie")
        .removeHeader("X-Tenant-Id")
        .removeHeader("X-Role")
        .setHeader("trustedTenantId", authenticatedTenantId)
        .build();
~~~

This fragment requires `authenticatedTenantId` to come from a security principal/verified claims. Never accept a raw client header and merely rename it to trusted.

### 13.3. Audience-Scoped Outbound Authorization

If outbound HTTP calls a partner API requiring an OAuth token, use an outbound authorized client/credential provider with the partner's audience/scopes; **do not reuse the inbound token**. Test that the partner HTTP stub never sees raw source tokens in requests, logs, or error payloads.

### 13.4. HTTP Mapper Allowlist

~~~java
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

DefaultHttpHeaderMapper mapper =
    DefaultHttpHeaderMapper.outboundMapper();

mapper.setOutboundHeaderNames(
    "Content-Type",
    "Accept",
    "X-Event-Id",
    "X-Trace-Id");
~~~

`setInboundHeaderNames(...)` on an **HTTP outbound gateway** controls headers received from the **response**, not the outgoing request. Avoid wildcard mapping to partners without a security review.

## 14. File/FTP/SFTP/SMB, TCP/UDP, and MongoDB/JDBC Boundaries

| Adapter | Control Header/Metadata | Risk if Copied Blindly |
|---|---|---|
| File writer | `FileHeaders.FILENAME` | Path traversal/overwrite when user picks the name |
| FTP/SFTP output | remote directory/filename expression | Upload to wrong tenant/path |
| FTP/SFTP input | remote file/path/host-port | Not automatically a business identity |
| TCP | connection ID/IP/port | Stale after reconnect |
| UDP | packet source address | Spoofing/reflection |
| MongoDB outbound | business ID in payload/document | Header does not automatically become a BSON field |
| JDBC outbound | SQL params from headers if configured | Never use raw headers as SQL identifiers |
| Logs/DLQ | full headers | Leaks secrets, PII, runtime handles |

### 14.1. SFTP: Remote Directory Only from Server Allowlist

~~~java
public String remoteDirectoryFor(String tenant) {
    return switch (tenant) {
        case "tenant-a" -> "/partners/a/exports";
        case "tenant-b" -> "/partners/b/exports";
        default -> throw new IllegalArgumentException(
            "Unauthorized tenant");
    };
}
~~~

Call this helper only with an authorized tenant. Never take raw `X-Remote-Path` from a client as an SFTP `remoteDirectory` expression. `SessionFactory` also needs host-key verification, credentials, and timeouts.

### 14.2. Filename and Idempotency

When `FileWritingMessageHandler` falls back to a filename from the Spring Message UUID, retries can generate new filenames for the same business event. Derive filenames from a validated event ID and pick an appropriate `fileExistsMode`/checksum/temporary rename strategy.

~~~java
Message<String> fileMessage =
    MessageBuilder.withPayload(
            "{\"eventId\":\"evt-1001\"}")
        .setHeader(
            org.springframework.integration.file.FileHeaders.FILENAME,
            "evt-1001.json")
        .build();
~~~

Disallow path separators/`..`/control chars in filenames, and never write outside the root directory.

### 14.3. Do Not Persist Raw MessageHeaders into MongoDB/JDBC

A `businessEventId` sitting only in a Spring header **is not automatically persisted** by a MongoDB storing adapter or JDBC row insert; if the DB needs deduplication, bind it explicitly to a domain object/unique index or SQL parameter.

Never store `replyChannel`, `errorChannel`, ACK handles, raw tokens, exception objects, or provider delivery metadata in BSON/SQL, as that is a long-lived **persistent boundary**.

### 14.4. UDP Source Address Is Not a Trusted Destination

A UDP datagram's source IP/port can be spoofed or changed by NAT; reflecting data back to a raw source address can cause reflection/SSRF-like abuse. Use trusted destination policies, rate limits, and application-level authentication; UDP does not provide reliable delivery by itself.
## 15. Building a Canonical Header Contract Before Crossing Boundaries

Suppose events arrive from HTTP/JMS/Kafka and must be sent to partners; we should not keep every protocol header. Design a **minimal** application contract:

| Application Header | Type | Issued/Validated By | Allowed Outbound to Partner? |
|---|---|---|---|
| `businessEventId` | String | Producer contract + canonical validator | Yes, if partner needs idempotency |
| `appTraceId` | String | Tracing layer/validation | Yes, if required by tracing contract |
| `schemaVersion` | int/String | Versioned event schema | Yes, if used downstream |
| `sourceSystem` | Enum/String | Server-configured ingress identity | Conditionally |
| `trustedTenantId` | String | Authenticated identity + ACL | Only if partner is authorized; may map to externalTenant |
| `receivedAt` | Instant | Server clock | Only if domain contract needs it |
| `replyChannel` | MessageChannel/String | Spring runtime | **No**, except internal reply lifecycle |
| `errorChannel` | MessageChannel/String | Spring runtime | **No** |
| `Authorization` | String secret | HTTP client/request | **No**; separate outbound auth |
| `kafka_offset` | Long | Kafka consumer | **No** as business metadata |
| `amqp_deliveryTag` | Long | RabbitMQ delivery | **No** |
| `jms_redelivered` | Boolean | JMS provider | **No** as outbound business status |

### 15.1. A Transport-Neutral DTO

A record containing only the business facts that need to move between services:

~~~java
package example.headerboundary;

import java.time.Instant;

public record CanonicalOrderEvent(
        String tenantId,
        String eventId,
        String orderId,
        String status,
        int schemaVersion,
        Instant occurredAt) {
}
~~~

The key principle is **using a domain DTO** instead of serializing the entire Spring `Message<?>` or `MessageHeaders` to a broker/DB. Source-specific ACK handles, reply/error channels, and credentials never appear in the domain DTO.

### 15.2. Normalizing Headers Across Multiple Protocols

Example of building a message after auth/validation:

~~~java
package example.headerboundary;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public final class CanonicalEventMessageFactory {

    public Message<CanonicalOrderEvent> build(
            CanonicalOrderEvent event,
            String authorizedTenant,
            String validatedTraceId) {

        if (event == null
                || authorizedTenant == null
                || !authorizedTenant.equals(event.tenantId())
                || event.eventId() == null
                || !event.eventId().matches(
                    "[A-Za-z0-9_-]{1,128}")) {
            throw new IllegalArgumentException(
                "Invalid event identity/tenant");
        }

        return MessageBuilder.withPayload(event)
            .setHeader(
                "businessEventId", event.eventId())
            .setHeader(
                "trustedTenantId", authorizedTenant)
            .setHeader("appTraceId", validatedTraceId)
            .setHeader(
                "schemaVersion", event.schemaVersion())
            .build();
    }
}
~~~

This is an instructional example: you must also validate `orderId/status/occurredAt`, trace ID length/type, and business tenant rights. If `validatedTraceId` is `null`, the Spring builder may omit the header per its semantics; production needs an explicit required/optional contract.

**Never copy source `MessageHeaders` wholesale** into output. If you must keep a protocol-specific field for auditing, turn it into an explicitly selected field with retention limits and restricted read access.

## 16. Allowlisting at Outbound HeaderMapper, Not Only Internal Filtering

Even after using `HeaderFilter` inside the flow, you still need a mapper at the external protocol boundary that permits **only the exact headers to send**.

### 16.1. HTTP Outbound

~~~java
import org.springframework.integration.http.support.DefaultHttpHeaderMapper;

DefaultHttpHeaderMapper mapper =
    DefaultHttpHeaderMapper.outboundMapper();

mapper.setOutboundHeaderNames(
    "Content-Type",
    "Accept",
    "X-Event-Id",
    "X-Trace-Id");
~~~

If the Spring application uses `businessEventId` while the partner expects `X-Event-Id`, use a `HeaderEnricher`/custom mapper for **controlled renaming**; do not expect `DefaultHttpHeaderMapper` to automatically rename arbitrary custom fields.

### 16.2. JMS Outbound

JMS properties should be **supported `String`/primitive types**. If a service carries `String` `businessEventId` and `String` `appTraceId`, a custom JMS mapper should allow only those two fields if default mapping is too broad. Provider-owned JMS fields like `JMSMessageID`/`JMSRedelivered` must never be duplicated to fake delivery state.

### 16.3. AMQP Outbound

~~~java
import org.springframework.integration.amqp.support.DefaultAmqpHeaderMapper;

DefaultAmqpHeaderMapper mapper =
    new DefaultAmqpHeaderMapper();

mapper.setRequestHeaderNames(
    "STANDARD_REQUEST_HEADERS",
    "businessEventId",
    "appTraceId",
    "!x-*",
    "!Authorization");
~~~

`STANDARD_REQUEST_HEADERS` may include standard AMQP properties depending on the mapper/version; if any field should not be exported, add an explicit policy or build a fresh message to avoid retained fields. Never use wildcard `*` for all custom headers.

### 16.4. Kafka Outbound

~~~java
import org.springframework.kafka.support.SimpleKafkaHeaderMapper;

SimpleKafkaHeaderMapper mapper =
    new SimpleKafkaHeaderMapper(
        "!id", "!timestamp",
        "businessEventId", "appTraceId");
~~~

With the simple mapper, convert custom values to raw UTF-8 bytes/the appropriate type for your version. The JSON Kafka mapper carries type metadata and needs trusted schemas/packages. Kafka's header map does not replace record key/topic/partition controls.

### 16.5. Synchronizing HeaderMapper with MessageConverter

An HTTP/JMS/AMQP/Kafka mapper only handles metadata. The body may be transformed by a converter; `contentType` from the original message may **no longer match** after conversion. Verify the actual wire payload and accompanying `contentType`/encoding headers, especially when converting from `Object` to JSON, Avro/Protobuf, or `byte[]`.

### 16.6. Boundary Double Check

Putting certain business fields in both headers and payload can assist routing, yet risks contradictions:

~~~text
Header businessEventId = evt-101
Payload eventId        = evt-202
~~~

**Never silently pick one side and proceed.** Validate consistency, reject conflicts, or apply an explicit canonical policy with signatures and clear precedence. For tenancy, the trusted value must come from authenticated identity, not a raw user header.

## 17. Do Not Propagate Headers Across Threads, Queues, or Persistent Stores

### 17.1. A Thread Boundary Does Not Make Data “Safe”

`DirectChannel` usually executes on the caller thread, whereas `ExecutorChannel`/`QueueChannel` can hand the message off to another thread. The header map may travel with the message, yet:

- `SecurityContext`/MDC `ThreadLocal` does not automatically follow executor/Reactive contexts.
- `MessageChannel` and provider ACK handles have their own lifecycle/thread affinity.
- An `InputStream` or session object may already be closed when a consumer processes it.
- Never store a mutable object in a header and let multiple workers mutate it.
- `send()==true` into an in-memory queue does not mean downstream transport committed.

**Solution:** propagate correlation ID/tracing via proper context propagation, choose immutable data, and ACK the source after durable processing per contract.

### 17.2. Persistent MessageStore Does Not Magically “Serialize Every Java Object”

When a `QueueChannel` is backed by a persistent `MessageStore`, the store/serializer may have to serialize both payload and headers. Risks:

- Headers contain non-serializable `MessageChannel`, JMS `Destination`, socket/session, or acknowledgment callbacks.
- Java object deserialization resolves to a different runtime context or fails on a new version.
- Payload/header schemas evolve across deploys, breaking reads.
- Tokens/secrets stay persisted in the database longer than security policy permits.
- Serialization succeeds, yet the temporary `replyChannel`'s caller is already gone.

Therefore, prefer storing **canonical business messages/data**, or use a separate durable inbox/outbox table/document with a minimal schema rather than persisting raw runtime message graphs.

### 17.3. If You Truly Need a Reply After a Durable Queue

Some designs can use `HeaderChannelRegistry` to store a `String` token for reply/error channels **within TTL and registry scope limits**. However, if the business needs replies after hours, restarts, or across regions, use a **durable reply destination + correlation ID + status store**, not temporary channels.

### 17.4. Example Pipeline Filtering Before a Durable Queue

~~~mermaid
flowchart LR
    I["Inbound Message<br/>token + replyChannel + eventId"] --> V["Validate + authorize"]
    V --> S["Sanitize/normalize"]
    S --> O["Canonical inbox/outbox<br/>eventId + payload"]
    O --> W["Async worker"]
    W --> M["Destination-specific HeaderMapper"]
    M --> B["Broker/Partner"]
~~~

**Order matters:** if `QueueChannel`/`MessageStore` sits **before** the sanitizer, raw secrets/runtime handles are already durably persisted and cannot be “unsent” merely by a later `HeaderFilter`.

## 18. ErrorMessage, Stack Traces, and DLQ: Observability Boundaries Must Filter Too

A Spring Integration `ErrorMessage` typically carries a `Throwable` payload whose nested causes/messages can expose endpoint URLs, credentials, input identifiers, or PII.

**Never forward raw `ErrorMessage.getPayload()` or `Throwable.toString()` to public HTTP responses, public Kafka topics, partner DLQs, or unprotected logs.**

### 18.1. Creating a Safe Error Envelope

~~~java
package example.headerboundary;

import java.time.Instant;

public record SafeFailureEvent(
        String eventId,
        String errorCode,
        boolean retryable,
        Instant failedAt) {
}
~~~

When catching errors, application classification builds a new event:

~~~java
SafeFailureEvent safeFailure =
    new SafeFailureEvent(
        verifiedBusinessEventId,
        "DOWNSTREAM_TIMEOUT",
        true,
        Instant.now());
~~~

This is a **fragment** requiring a validated `eventId` and classified error. Do not stuff raw exception messages/stacks into `errorCode`. If internal diagnostics are needed, keep them in a restricted store/tracing system with dedicated retention and redaction.

### 18.2. DLQ/Quarantine Is Not Automatically Safe

A durable DLQ can hold messages for days and be inspected by multiple teams/tools. If original headers retain Bearer tokens, Cookies, principals/sessions, authorization claims, or sensitive raw payloads, sending them straight to the DLQ widens data exposure.

Recommended policy:

1. Build a **safe failure payload** with `eventId`/errorCode/correlation.
2. Store the original payload only in a restricted encrypted bucket/store when replay truly requires it.
3. Scrub headers before storing or sending.
4. Enforce retention, access auditing, and GDPR/PII policies.
5. Never use an `ErrorMessage` carrying provider channel objects as a durable replay record.
6. Replay must reconstruct a clean business message from validated data rather than rehydrating arbitrary runtime objects.

### 18.3. Error Channel Is Not Broker Dead-Letter ACK

`errorChannel` is a Spring Messaging concept; sending an `ErrorMessage` to `errorChannel` **does not automatically mean JMS/Kafka/AMQP durably dead-lettered the message**. If an error handler merely logs and returns, the source may ACK depending on the adapter/container. Define explicit transaction/error propagation/durable DLQ policies and test retries and poison-message loops.

## 19. Security Review: Boundary Threat Model

### 19.1. Tenant/Role Spoofing via External Headers

A client sends:

~~~http
X-Tenant-Id: tenant-b
X-Role: admin
X-Target-Topic: finance.sensitive
~~~

If the app trusts these headers to pick a MongoDB collection or Kafka topic, a user in tenant A can access tenant B's data.

**Mitigation:**

- Authenticate/authorize from a trusted security context.
- Bind `trustedTenantId` to verified claims/ACLs.
- Allow destinations only from the tenant's server-side allowlist.
- Use explicit names/DTOs; never map raw `X-Target-Topic` to `KafkaHeaders.TOPIC`.
- Check tenant header/payload mismatches and audit conflicts.
- Test a tenant A user trying to tamper with headers to reach tenant B.

### 19.2. Reply/Error Channel Injection

An external client sends `replyChannel="adminControlChannel"` or `errorChannel="sensitiveLogs"`. If a mapper/custom handler copies those names into Spring's internal routing context, replies/errors can be misrouted.

**Mitigation:** block external headers from overwriting reserved keys; let the gateway/server supply internal reply/error channels, and restrict dynamic routes to allowlisted/authorized bean names.

### 19.3. HTTP SSRF and SFTP Path Traversal

Raw headers like `X-Target-Url=http://localhost:8080/admin` or `X-Remote-Directory=../../secrets` must never become direct outbound destination expressions. Use a server-side mapping from authenticated partner IDs to fixed URLs/remote directories, enforce egress restrictions, and validate paths.

### 19.4. Header Injection, Type Injection, and Size DoS

- HTTP values containing `\r`/`\n` can cause header injection or client rejection.
- Kafka JSON type hints can deserialize unauthorized classes if trusted packages are too broad.
- AMQP/JMS headers have size/type limits; arbitrary Java objects break converters.
- Hundreds of custom headers or large values can hit message/broker limits, cause memory pressure, or bloat logs.
- Header values can hold secrets even when the header name is allowlisted; validate length/content.

### 19.5. Logging/Metrics Boundary

Never log `message.getHeaders()` intact. Emit **low-cardinality** metrics: protocol, allowlisted destination ID, outcome, error category; never use individual `eventId`s or tenant-sensitive tokens as labels. Correlation IDs can go into redacted traces/logs with defined retention and access controls.

### 19.6. Per-Boundary Security Checklist

| Check | Question |
|---|---|
| Ownership | Who created the header? External client, broker, or server? |
| Trust | Has it been authenticated/validated/authorized? |
| Lifetime | Is the header still valid after a thread switch or restart? |
| Type | Can it serialize cleanly to the target protocol? |
| Semantics | Does the receiver interpret it with the same meaning? |
| Sensitivity | Does it leak tokens/PII/topology/roles? |
| Destination | Is this header authorized to influence routing? |
| Retry | On redelivery, does the value remain accurate and stable? |
| Audit | Does it need long-term retention, and under what policy? |
| Test | Have we asserted its absence on the wire/logs/store? |
## 20. Automated Testing: Verifying Headers Do Not Cross Boundaries

To prove a header **does not cross a boundary**, unit/integration tests must assert the **header is absent from the output**, not merely that the handler succeeded. Good tests also assert that required **`businessEventId`/tracing fields remain intact**.

### 20.1. JUnit Test for MessageBuilder Creating an Allowlisted Message

~~~java
package example.headerboundary;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class MessageBoundaryTest {

    @Test
    void onlyBusinessMetadataIsCopied() {
        Message<String> input =
            MessageBuilder.withPayload("order-paid")
                .setHeader("Authorization", "secret")
                .setHeader("X-Untrusted-Role", "admin")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("appTraceId", "trace-01")
                .build();

        Message<String> outbound =
            MessageBuilder.withPayload(input.getPayload())
                .setHeader("businessEventId",
                    input.getHeaders().get(
                        "businessEventId", String.class))
                .setHeader("appTraceId",
                    input.getHeaders().get(
                        "appTraceId", String.class))
                .build();

        assertEquals("evt-1001",
            outbound.getHeaders()
                .get("businessEventId", String.class));

        assertEquals("trace-01",
            outbound.getHeaders()
                .get("appTraceId", String.class));

        assertFalse(outbound.getHeaders()
            .containsKey("Authorization"));

        assertFalse(outbound.getHeaders()
            .containsKey("X-Untrusted-Role"));
    }
}
~~~

**Limitation:** this test verifies builder policy. It does not prove that the **entire `IntegrationFlow`** goes through this builder or that no later handler re-adds forbidden headers.

### 20.2. Integration Test for HeaderFilter with QueueChannel

Test configuration in a Spring context:

~~~java
package example.headerboundary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration
@EnableIntegration
class BoundaryFilterTestConfig {

    @Bean("rawInbound")
    MessageChannel rawInbound() {
        return new DirectChannel();
    }

    @Bean("sanitizedInbound")
    PollableChannel sanitizedInbound() {
        return new QueueChannel(10);
    }

    @Bean
    IntegrationFlow sanitizeInboundFlow() {
        return IntegrationFlow.from("rawInbound")
            .headerFilter(
                "Authorization",
                "Cookie",
                "X-Untrusted-Role")
            .channel("sanitizedInbound")
            .get();
    }
}
~~~

Test class:

~~~java
package example.headerboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(BoundaryFilterTestConfig.class)
class HeaderFilterIT {

    @Autowired
    @Qualifier("rawInbound")
    MessageChannel input;

    @Autowired
    @Qualifier("sanitizedInbound")
    PollableChannel output;

    @Test
    void secretsAreRemovedBeforeNextChannel() {
        Message<String> source =
            MessageBuilder.withPayload("order-paid")
                .setHeader("businessEventId", "evt-1001")
                .setHeader("Authorization", "secret")
                .setHeader("Cookie", "sid=secret")
                .setHeader("X-Untrusted-Role", "admin")
                .build();

        assertTrue(input.send(source));

        Message<?> result = output.receive(2000);
        assertNotNull(result);

        assertEquals("evt-1001",
            result.getHeaders()
                .get("businessEventId", String.class));

        assertFalse(result.getHeaders()
            .containsKey("Authorization"));

        assertFalse(result.getHeaders()
            .containsKey("Cookie"));

        assertFalse(result.getHeaders()
            .containsKey("X-Untrusted-Role"));
    }
}
~~~

Requirements: the test needs `spring-integration-core` and `spring-test`/JUnit Jupiter on the classpath. Each test should use a clean context/queue to avoid stale messages. `QueueChannel(10)` here is **in-memory** and does not replace persistent store/broker integration tests.

### 20.3. Testing notPropagatedHeaders on the Target Endpoint

Configuration illustrating a **separate flow** to avoid colliding with the test beans/channels above:

~~~java
@Bean
IntegrationFlow noSecretPropagation() {
    return IntegrationFlow.from("rawTransformInput")
        .handle(
            String.class,
            (payload, headers) -> payload.toUpperCase(),
            e -> e.notPropagatedHeaders(
                "Authorization", "debug*"))
        .channel("noSecretOutput")
        .get();
}
~~~

This is a **fragment**; declare the channels in the corresponding context. The test should assert that `Authorization` and `debugTrace` are absent from the output while `businessEventId` remains. Importantly, because the handler returns a **payload**, automatic propagation runs and `notPropagatedHeaders` takes effect. Do not extrapolate from this test to conclude routers/bridges filter too.

### 20.4. Testing That Bridges/Routers Do Not Filter Automatically

Create a flow:

~~~java
@Bean
IntegrationFlow bridgeOnly() {
    return IntegrationFlow.from("bridgeInput")
        .bridge()
        .channel("bridgeOutput")
        .get();
}
~~~

If the source message carries `Authorization`, a bridge typically forwards the message as-is; **do not** rely on `notPropagatedHeaders` on another handler to strip it. Place a `HeaderFilter` before or after the bridge where all paths pass through.

### 20.5. Testing HTTP Outbound Wire Metadata

Use an HTTP test server (WireMock, MockWebServer, or an embedded server) and an outbound gateway **injected with the allowlist mapper**. Verify:

1. Request body contains the exact business payload.
2. `X-Event-Id` header carries the verified `businessEventId`.
3. No raw inbound `Authorization` or `Cookie` is present.
4. No Spring `replyChannel`/`errorChannel`/`id` appears in HTTP headers.
5. `Content-Type` matches the converted payload.
6. Partner response headers map only allowed fields.
7. Sending an event without an ID fails before any network call.

### 20.6. Wire-Level Testing for Kafka, JMS, and AMQP

| Protocol | Unit Mapper Assertion | Integration Assertion |
|---|---|---|
| Kafka | `RecordHeaders.lastHeader("businessEventId")` has right bytes, no `internalRole` | Real `ConsumerRecord` headers, right topic/key, retry/ACK |
| JMS | Allowed `String` property from Spring header | JMS listener receives right property; no Spring channel object |
| AMQP | `DefaultAmqpHeaderMapper.fromHeaders` produces no `x-received-from`/`internalRole` | Real RabbitMQ message properties, confirm/return |
| SFTP | Sanitized filename and trusted directory expression | Remote file at right path, no traversal |
| Persistent store | Headers have serializable/canonical types | Message restores across restart with valid reply/error policy |

A mock unit test does not prove the broker ACKed, the Kafka offset committed, or the SFTP upload finalized. Also test **failure paths** when the broker is down or the network times out.

## 21. Retry, ACK, and Recovery Matrix After Filtering Headers

| Stage | On Failure | Headers Kept for Retry | Headers Never Persisted |
|---|---|---|---|
| Ingress parse/validate | Reject/HTTP 4xx or quarantine | `sourceEventId`, sanitized source ID | Raw token, untrusted role |
| Durable inbox write | Retry/reconcile same key | `businessEventId`, authorized tenant, schema | Temporary `replyChannel`, Kafka ACK |
| Queue/process boundary | Recover pending work | Business fields/attempt count in durable store | JMS session, AMQP channel/`deliveryTag` |
| HTTP outbound | Idempotent retry | `businessEventId`, safe trace | Inbound `Authorization`/`Cookie` |
| Kafka producer | Retry/outbox/ack policy | Kafka key, event ID, schema | Consumer offset/ACK object |
| JMS/AMQP producer | Broker retry/confirm/returns | `businessEventId` | Inbound delivery tags/`redelivered` |
| Persistent DLQ | Manual replay after triage | Safe event ID/error code | `Throwable` stack/raw token |
| App restart | Rebuild canonical message | Domain DTO/transaction status | In-memory channels/session refs |

### 21.1. Why Can the Same Header Be Valid at One Step and Wrong at Another?

A `replyChannel` valid inside a **sync gateway** becomes invalid when persisted to a **Kafka outbox**. A `kafka_offset` is useful for debugging the listener but invalid when sent to a **partner HTTP** endpoint. A `trustedTenantId` may be required for internal database authorization yet forbidden from being sent to a single-tenant partner.

That is why you should never write a blanket rule like “ban every header A” or “copy every header B”; instead evaluate **source, destination, trust, lifetime, and contract**.

### 21.2. Recovering After a Lost ACK

Suppose the partner HTTP service committed, yet the response timed out. The app retries with the **same `businessEventId`** and canonical payload; the partner/destination uses idempotent logic to return `ALREADY_ACCEPTED` or a business conflict.

Never generate a new Spring Message UUID as a substitute business ID. Filtering `id` across boundaries is right when it was misused, whereas the business event ID must be **preserved and durably stored**.

### 21.3. Do Not Store Broker ACK Handles in MessageStore

A Kafka acknowledgment object, AMQP `deliveryTag`/channel, or JMS session is a **runtime capability** bound to a listener/connection/transaction. After a restart or on another worker, it is not a durable replay mechanism. Commit/roll back within the listener's own lifecycle or transition to a well-designed durable inbox/outbox and recovery policy.

### 21.4. Error Channel Does Not Automatically Mean Durable DLQ

An error handler receiving an `ErrorMessage` and returning normally may cause upstream to ACK per container policy. If the message has not yet been safely persisted to durable quarantine, do not assume retries will continue. A DLQ needs an owner, retention, redaction, idempotent replay, and metrics.

## 22. Observability, Log Security, and Lifecycle

### 22.1. Useful Metrics

The following names are **suggestions**, not emitted automatically by the framework:

| Metric | Meaning |
|---|---|
| `boundary_header_filtered_total` | Headers stripped per policy |
| `boundary_header_rejected_total` | Invalid/forbidden headers causing event failure |
| `boundary_header_type_error_total` | Serialization/conversion failures |
| `boundary_untrusted_tenant_attempt_total` | Attempts to tamper with tenant/route |
| `boundary_reserved_header_attempt_total` | Headers attempting to overwrite reply/error/channel |
| `boundary_wire_header_leak_total` | Contract violations caught in tests/monitoring |
| `boundary_outbound_send_total` | Transport send counts |
| `boundary_outbound_unknown_total` | Timeouts/ambiguous ACKs |
| `boundary_dlq_depth` | Safe quarantined events waiting |
| `boundary_recovery_success_total` | Events successfully recovered |
| `boundary_business_committed_total` | Completed business effects |

Never use raw `eventId`s/tokens/dynamic URLs as high-cardinality metric labels. For tracing, valid correlation IDs can go into structured logs/spans per retention policy.

### 22.2. Suggested Logs

~~~text
ingress_received     source=http-partner
header_validated     allowed=4 rejected=2
canonicalized        hasBusinessEventId=true
persisted_inbox      status=accepted
outbound_started     protocol=kafka destination=orders.events
broker_ack           result=success
business_committed   result=pending_downstream
~~~

These logs **contain no raw credentials**, sensitive payloads, or arbitrary object `toString()` output. Do not log full `message.getHeaders()` just to debug production.

### 22.3. Lifecycle/Threads

- HTTP requests/gateways have short timeouts and reply lifetimes.
- JMS/AMQP listeners have session/channel delivery lifetimes; handles are not portable across reconnects.
- Kafka consumers have rebalance/offset lifecycles; acknowledgment handles are not durable task IDs.
- `QueueChannel`/`ExecutorChannel` introduces an async context boundary; `ThreadLocal`/MDC does not propagate automatically.
- SFTP/FTP sessions have remote connection lifecycles; raw session objects are not durable.
- `MessageStore` introduces serialization/schema/restart boundaries.
- Outbound HTTP/Kafka/JMS/AMQP endpoints have separate delivery/confirmation lifecycles.

`HeaderFilter`/mappers do not start/stop pollers, drain in-flight messages, or create an outbox. On deploy/restart, ensure durable pending work, idempotent replay, and graceful shutdown.

### 22.4. Periodically Re-Checking Policy on Schema Changes

When adding a new `internalApprovalRole` header, if an app relies on a blocklist that only strips `Authorization`, the new header can leak to partners. Before every release, run contract tests like **“unknown headers must not appear on the wire”**. Destination allowlists are far easier to verify than growing blocklists.
## 23. Case Study: HTTP Inbound → MongoDB Inbox → Kafka → JMS/HTTP Partner

### 23.1. Business Requirements

A system receives `OrderPaid` via HTTP from a partner. Then:

1. Authenticate tenant and signature/token.
2. Persist a durable MongoDB inbox document with the business event ID.
3. Have a worker publish to Kafka `orders.paid` with `businessEventId`.
4. Another consumer forwards to JMS queue `accounting.paid`.
5. Another partner receives an HTTP POST confirming status.
6. Every step must support retry/redelivery after crashes or lost ACKs.

### 23.2. Incoming Headers

~~~text
HTTP ingress headers:
  Authorization = Bearer <token>
  X-Tenant-Id = tenant-a
  X-Role = admin
  X-Event-Id = evt-1001
  X-Trace-Id = tr-9c

Spring framework / transport headers:
  id = <new UUID>
  replyChannel = <temporary MessageChannel>
  errorChannel = <MessageChannel>
  http_requestUrl = /orders/events
  http_requestMethod = POST
~~~

### 23.3. Policy at Each Point

| Point | DROP | TRANSFORM/KEEP |
|---|---|---|
| HTTP ingress → trusted business | `Authorization`, `Cookie`, `X-Role`, raw `X-Tenant-Id` | `authenticatedTenantId → trustedTenantId`, `X-Event-Id → businessEventId`, validated trace |
| Business → MongoDB inbox | `replyChannel`/`errorChannel`, raw HTTP request metadata | Canonical DTO, unique business ID, `schemaVersion` |
| MongoDB outbox → Kafka | Runtime DB/worker/lease objects | Kafka key by `orderId`, custom `businessEventId` bytes |
| Kafka consumer → JMS producer | Kafka ACK/`ConsumerRecord`/topic/offset metadata | `businessEventId` String, `appTraceId` String |
| JMS consumer → HTTP partner | `JMSMessageID`/`Redelivered`/`JMSReplyTo`, raw tokens | `X-Event-Id`, `X-Trace-Id`, JSON body, new outbound token |
| Any error → DLQ | `Throwable` object, raw headers, secrets | Safe `errorCode`, `eventId`, `retryable` flag |
| Replay after restart | Temporary channels/ACK handles | Stable event ID, durable pending status |

### 23.4. End-to-End Design

~~~mermaid
flowchart TB
  H["HTTP request"] --> SEC["Auth + tenant validation"]
  SEC --> N["Sanitize external headers"]
  N --> C["CanonicalOrderEvent<br/>+ businessEventId"]
  C --> DB["MongoDB Inbox/Outbox<br/>durable transaction"]
  DB --> W["Outbox worker"]
  W --> K["Kafka producer<br/>custom allowed headers"]
  K --> KC["Kafka consumer"]
  KC --> J["JMS producer<br/>JMS-friendly properties"]
  J --> JC["JMS consumer"]
  JC --> PH["HTTP partner<br/>new auth, selected headers"]
  W -. failure .-> D["Safe DLQ / retry"]
  KC -. failure .-> D
  JC -. failure .-> D
~~~

### 23.5. Crash Windows

**Scenario A — DB commit succeeds, HTTP client times out:** client retries with the same `X-Event-Id`; MongoDB unique key detects the existing record. Never use a new Spring Message UUID as the event ID.

**Scenario B — Kafka broker ACKs, but outbox worker crashes before marking SENT:** the event may be republished. The consumer deduplicates by `businessEventId`; Kafka offset neither needs to nor should be copied to JMS/HTTP as event identity.

**Scenario C — JMS consumer receives redelivered message:** `JMSRedelivered` aids observation, not proving whether the previous business side effect occurred. The accounting service's durable inbox arbitrates duplicate processing.

**Scenario D — Partner HTTP API returns 202 and connection drops:** do not treat 202 as business completion. Reconcile with the same `eventId`/partner status; never invent a new token/trace/event ID for a “clean retry”.

**Scenario E — Application restart:** temporary `replyChannel` and ACK callbacks from the previous process are gone. The durable outbox/inbox recovers via business IDs, not by deserializing runtime callback objects.

### 23.6. Acceptance Criteria

- No token/role/raw tenant header travels to Kafka/JMS/partner.
- No Spring `replyChannel`/`errorChannel` objects exist in persisted inbox/outbox documents.
- Kafka wire headers carry only allowed fields with proper encoding.
- JMS custom properties carry only `String`/primitives per contract.
- AMQP `x-received-from`/`deliveryTag` are not mirrored if RabbitMQ is in the pipeline.
- Partner receives only an audience-scoped outbound token, `X-Event-Id`, and valid body.
- Redeliveries keep the same `businessEventId` and cause no second business effect.
- Missing/mismatched event IDs are rejected/quarantined rather than retried indefinitely.
- Error logs/DLQ contain no secrets or raw exception stacks per policy.
- Async queue receipt != transport/business ACK; metrics distinguish the checkpoints.

## 24. Troubleshooting: Header Crossed the Wrong Boundary or Disappeared

| Symptom | Cause | How to Check and Fix |
|---|---|---|
| `Authorization` appears at partner HTTP | Wildcard copy / overly broad default mapper | Enable outbound allowlist, redact at ingress |
| Spring `replyChannel` header appears in JMS property | Serialized raw headers or custom mapper | Exclude runtime objects; use JMS gateway correlation |
| `HeaderFilter` has no effect | Flow bypasses filter, wrong key/casing | Capture message before/after, verify wiring |
| `notPropagatedHeaders` does not filter router | Router/bridge forwards message without output copy | Place `HeaderFilter`/transformer before route |
| `notPropagatedHeaders` drops `businessEventId` | Used `*` or overly broad pattern | Specify exact patterns, assert required headers |
| `readOnlyHeaders` mistaken for outbound denylist | Confused builder vs. network scope | Use destination `HeaderMapper` allowlist |
| Payload-only transformer retains secrets | Automatic propagation | `HeaderFilter`, `notPropagatedHeaders`, or build clean `Message` |
| `Message`-returning transformer loses correlation | Forgot to copy required headers | Explicitly copy correlation fields, test gateway |
| Persistent queue serialization error | Header holds `MessageChannel`/`InputStream`/ACK callback | Canonical DTO, `HeaderChannelRegistry` with TTL if appropriate |
| Reply after restart never reaches caller | Temporary `replyChannel` lost or TTL expired | Durable reply destination + correlation ID |
| Kafka ACK handle sent into JMS | Copied runtime Kafka headers | Drop listener context, commit at consumer |
| Kafka offset used as `eventId` | Confused log position with business identity | Stable `businessEventId` |
| `JMSMessageID` changes after republish | New provider-generated ID | Custom `businessEventId` `String` |
| JMS property conversion fails | Unsupported Java object type | Normalize/allowlist JMS primitives/`String` |
| AMQP `deliveryTag` invalid after reconnect | Tag bound to old channel | ACK on active channel; never persist tag |
| RabbitMQ reply dropped | `x-received-from` federation header mirrored | Exclude `x-*` or filter deliberately |
| Dangerous Kafka JSON type header | Trusted packages too broad | Schema/trusted types allowlist |
| HTTP client calls internal endpoint via `X-Target-Url` | SSRF from raw header | Server route allowlist/egress policy |
| SFTP uploads to wrong tenant directory | Remote path from untrusted header | Trusted tenant → fixed allowed directory |
| Header named `id` unexpectedly dropped | Core read-only/header rebuild semantics | Separate `businessEventId` from Message ID |
| `Content-Type` mismatches body | Converter changed payload after mapping | Wire-level body/header test |
| DLQ contains tokens/PII | Saved `ErrorMessage`/full headers | Safe envelope + restricted data store |
| Error flow only logs yet source ACKs | Recovery callback swallowed exception | Durable DLQ or propagate error per contract |
| `QueueChannel.send` true yet outbound didn't run | Async RAM queue | Durable outbox/ACK at right stage |
| Unit tests pass yet network leaks | Tested builder only, not `HeaderMapper`/endpoint | Capture HTTP/JMS/AMQP/Kafka wire metadata |
| Metrics cardinality spikes | Used `eventId`/token as labels | Low-cardinality dimensions |

### 24.1. Ordered Diagnostic Procedure

~~~text
1. External source + raw metadata
2. Security filter / producer ACL / tenant validation
3. HeaderMapper.toHeaders or native inbound adapter headers
4. Raw Spring Message
5. HeaderFilter / Transformer / notPropagatedHeaders
6. Canonical Spring Message & domain DTO
7. Persistent queue/inbox/outbox serialization
8. Outbound HeaderMapper.fromHeaders
9. Actual HTTP/JMS/AMQP/Kafka/SFTP wire payload & headers
10. Transport ACK/confirm/return
11. Business consumer commit
12. Retry, DLQ and recovery after crash/restart
~~~

Test **each boundary**, rather than checking only the start and end messages. When a leak occurs, inspect the exact path: a Spring header may have taken a branch that bypassed the filter or used a different gateway/mapper bean than the one tested.

## 25. Practice Exercise

Build a lab system with two branches: **HTTP → canonical event → Kafka** and **JMS/AMQP → canonical event → partner HTTP**, then verify headers are stripped at every boundary.

### Part A — Spring Message Propagation

1. Create a message with `Authorization`, `X-Untrusted-Role`, `businessEventId`, and `appTraceId`.
2. Build a payload-only transformer; observe which headers propagate.
3. Build a transformer returning a new `Message` via `MessageBuilder.withPayload(...)`; compare.
4. Use `HeaderFilter` to remove `Authorization`/`Cookie`/`Role`.
5. Test `notPropagatedHeaders("Authorization","debug*")` on an output-producing service activator.
6. Put a bridge/router before the filter and verify why filtering must cover all paths.
7. Try `"*"` in `notPropagatedHeaders` in the **lab**, and explain why required headers can be lost.
8. Verify `id`/`timestamp` are read-only and use a separate `businessEventId`.

### Part B — Reply/Error and Durable Boundaries

1. Send a request/reply message through a synchronous gateway and observe `replyChannel`.
2. Put a message containing a runtime `MessageChannel` into a test `MessageStore`; analyze serialization/lifecycle.
3. Try `HeaderChannelRegistry` to convert `replyChannel` into a `String` token with TTL.
4. Prove the token/temporary reply does not become durable cross-service RPC after a restart.
5. Design a reply queue + correlation ID/persisted status for long-running requests.
6. Test that an external `replyChannel="internalAdminChannel"` header cannot override internal routing.

### Part C — Kafka/JMS/AMQP Metadata

1. Send a Kafka record and read `KafkaHeaders.OFFSET`/`RECEIVED_TOPIC` in the listener.
2. Rebuild a canonical message and assert no consumer ACK/offset objects appear in outbound Kafka headers.
3. Build a JMS outbound message with a custom `businessEventId` property instead of the old provider `JMSMessageID`.
4. Verify an unsupported JMS property type fails before/at the provider.
5. Receive an AMQP message with `amqp_deliveryTag` and `x-received-from`, and strip them before outbound.
6. Test publisher confirms/returns separately from message header mapping.
7. Measure a redelivered event ID and verify idempotency.

### Part D — HTTP/SFTP and Security

1. Receive an HTTP request with `Authorization`, `X-Role`, and `X-Tenant-Id`.
2. Authenticate user as tenant A while sending a spoofed tenant B header; assert `trustedTenantId` does not change.
3. Call the partner HTTP stub; assert no inbound token/cookie/role leaks.
4. Configure an allowlisted outbound API URL; test that `X-Target-Url` SSRF is rejected.
5. Derive the SFTP remote directory from `authenticated tenant → fixed config`, never raw user paths.
6. Derive filename from validated `businessEventId` and test replaying the same ID.
7. Test `Content-Type` and body together at the wire level.

### Part E — Persistence, DLQ, and Operations

1. Persist canonical event + business ID into a MongoDB inbox/outbox.
2. Ensure no `replyChannel`/`errorChannel`/`Throwable`/raw token is stored in the document.
3. Simulate a crash after broker ACK before marking SENT, verifying the event can be replayed.
4. Add an idempotent consumer with a unique business key.
5. Build a safe DLQ envelope with `errorCode`, `eventId`, and `retryable` flag.
6. Add metrics for dropped/rejected headers, transport ACKs, unknown outcomes, and DLQ backlog.
7. Run a restart test with a persistent store and verify messages recover cleanly.
8. Design retention/access control for logs/DLQ and graceful drain.

### 25.1. Self-Assessment Questions

- Does “headers that must not cross boundaries” mean the framework blocks all sensitive headers automatically?
- How does a payload-returning transformer differ from a `Message`-returning transformer regarding propagation?
- How does `HeaderFilter` differ from `notPropagatedHeaders` and `HeaderMapper`?
- Why doesn't `notPropagatedHeaders` cover all router/bridge paths?
- How do `readOnlyHeaders` and `MessageHeaders.ID/TIMESTAMP` relate?
- What happens when using the `*` pattern with `notPropagatedHeaders`?
- Why shouldn't Spring `replyChannel` be serialized to Kafka/JMS?
- Does `HeaderChannelRegistry` make replies durable across restarts?
- Should Kafka ACK callbacks/offsets/consumer objects be sent to partners?
- Can `JMSMessageID` change upon republishing?
- What errors can AMQP `deliveryTag` and `x-received-from` cause?
- Why can't inbound HTTP `Authorization` become outbound `Authorization`?
- Is a header named `trustedTenantId` trustworthy just because it exists?
- What issues can a client-supplied SFTP path cause?
- Does the MongoDB storing handler automatically save all Spring headers?
- Why are wire-level tests more important than mapper unit tests alone?
- Can `HeaderFilter` remove secrets already inside the payload?
- Why isn't an `errorChannel` that only logs automatically a durable DLQ?
- Should redelivery deduplicate using Spring Message ID or `businessEventId`?
- When `QueueChannel.send()` succeeds, has the broker ACKed?

## 26. References

- [Spring Integration — Message and Header Propagation](https://docs.spring.io/spring-integration/reference/message.html): read-only headers, propagation, `notPropagatedHeaders`, and limitations with bridges/routers.
- [Spring Integration — Transformer and Header Filter](https://docs.spring.io/spring-integration/reference/transformer.html): Header Filter EIP, Java DSL/XML, transform outputs.
- [Spring Integration — Header Enricher and HeaderChannelRegistry](https://docs.spring.io/spring-integration/reference/content-enrichment.html): converting `replyChannel`/`errorChannel` to tokens, TTL, and registry.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): persistence, serialization, store types, and lifecycle.
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): `DirectChannel`/`QueueChannel`/`ExecutorChannel` and thread boundaries.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel`, error flows.
- [Spring Integration — HTTP Header Mapping](https://docs.spring.io/spring-integration/reference/http/header-mapping.html): `DefaultHttpHeaderMapper` inbound/outbound allowlists.
- [Spring Integration — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): default JMS header mapper, message-driven/outbound, correlation.
- [Spring Integration — AMQP Message Headers](https://docs.spring.io/spring-integration/reference/amqp/message-headers.html): `x-*`/federation, received-only fields, request/reply header patterns.
- [Spring Integration — AMQP Outbound](https://docs.spring.io/spring-integration/reference/amqp/outbound-channel-adapter.html): RabbitMQ publisher confirms and returns.
- [Spring Integration — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): inbound/outbound Kafka adapters and converters.
- [Spring Kafka — Message Headers](https://docs.spring.io/spring-kafka/reference/kafka/headers.html): Simple/JSON `KafkaHeaderMapper`, header exclusions, patterns, and typed headers.
- [Spring Integration — File Writing](https://docs.spring.io/spring-integration/reference/file/writing.html): `FileHeaders.FILENAME`, `FileNameGenerator`, `FileExistsMode`.
- [Spring Integration — SFTP](https://docs.spring.io/spring-integration/reference/sftp.html): remote paths, session management, file delivery.
- [Spring Integration — TCP and UDP](https://docs.spring.io/spring-integration/reference/ip.html): IP headers and network connection metadata.
- [Spring Framework — MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html): reserved/core headers and typed access.
- [Spring Integration API — HeaderMapper](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/mapping/HeaderMapper.html): `toHeaders`/`fromHeaders`.

## 27. Conclusion

**Headers that must not cross boundaries** are not a ceremonial blocklist. They are decisions based on **origin, trust level, lifetime, data type, semantics, destination permissions, and retry/replay requirements**. Spring Integration normally propagates headers across message-producing endpoints, so we must actively decide where to filter them.

In **SPRING_INTEGRATION_ADAPTERS**, combine **`HeaderFilter`/`MessageBuilder`** for internal messages, **`notPropagatedHeaders`** when handlers create new outputs, and **destination-specific `HeaderMapper`s/DTOs** at HTTP/JMS/AMQP/Kafka/file/database boundaries. Never serialize Spring `replyChannel`/`errorChannel` or broker ACK handles as business metadata; never forward source credentials, raw tenant claims, stale delivery tags, or arbitrary Java objects. Keep **`businessEventId` stable**, export only validated data, and test the absence of forbidden headers at the **wire/store/log/DLQ**.

**A successfully sent message does not prove headers are safe; a properly filtered header does not prove downstream ACKed or business committed.** To preserve data across crashes, pair boundary policies with a durable inbox/outbox, idempotent consumers, retry/backoff, recovery, and observability.
