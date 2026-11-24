# Standard Headers, Application Headers, and Naming Conventions

In Spring Messaging, a Message consists of a payload and a set of headers. The payload contains the primary data that the consumer needs to process; headers contain metadata that helps identify, route, convert, trace, and control how the message is processed.

A header is not merely an arbitrary key-value pair. Depending on its position in the flow, it may be a standard header defined by Spring, an internal header for routing, a protocol header such as JMS/STOMP, or metadata set by the application itself. Understanding these groups helps avoid name collisions, metadata loss during transport transitions, and inadvertently trusting data sent by clients.

## 1. Where Do Headers Live in a Message?

Spring's Message<T> contract has two components:

- **Payload:** the data object, for example OrderCreated, a JSON string, or a command.
- **Headers:** the set of metadata accessed through MessageHeaders.

For example, a message may carry an order ID as its payload while having headers containing a correlation ID, content type, and schema version. The consumer reads the payload to perform business logic; headers help determine which processing flow the message belongs to and how it should be interpreted.

~~~text
Message<T>
├── payload
│   └── OrderCreated(...)
└── headers
    ├── id
    ├── timestamp
    ├── contentType
    ├── appCorrelationId
    └── appSchemaVersion
~~~

Headers do not replace the payload. If data is part of the business contract that the consumer needs to understand, store, or validate, consider placing that data in the payload. Headers are better suited for metadata serving transport, routing, observability, and processing.

## 2. Standard Headers of Spring MessageHeaders

The org.springframework.messaging.MessageHeaders class defines several shared header names. Use the constants on this class instead of typing strings manually to avoid typos.

| Constant | Key name | Meaning and value type |
|---|---|---|
| MessageHeaders.ID | id | UUID identifying a message instance |
| MessageHeaders.TIMESTAMP | timestamp | Long representing message creation time, in epoch milliseconds |
| MessageHeaders.CONTENT_TYPE | contentType | MimeType describing the payload format |
| MessageHeaders.REPLY_CHANNEL | replyChannel | MessageChannel or channel name used for replies |
| MessageHeaders.ERROR_CHANNEL | errorChannel | MessageChannel or channel name used for errors |

### 2.1. id and timestamp

Spring automatically manages id and timestamp when creating regular MessageHeaders. The ID is a UUID to distinguish a message instance; timestamp records when the message was created.

Do not use Spring's id as a business key, idempotency key, or correlation ID across a workflow. When an application creates a new message from an old message, the message instance and system metadata may be regenerated. If you need to identify an order, event, or request across multiple services, create a dedicated business header such as appEventId or appCorrelationId.

Similarly, Spring's timestamp is not necessarily the time the business event occurred. If you need to know when an order was created, store that time in the payload or a business header like appOccurredAt. Do not equate message creation time with the time the event happened.

Do not set MessageHeaders.ID to an arbitrary value yourself. The Javadoc specifies that the ID is auto-generated and should only be explicitly restored when deserializing a previously serialized message.

### 2.2. contentType

contentType describes the payload's format so converters or consumers interpret it properly. For example: application/json, text/plain, or application/octet-stream.

In Spring Messaging, content type is represented by MimeType. Whenever possible, use MessageHeaderAccessor.setContentType or the MessageHeaders.CONTENT_TYPE constant with the corresponding MimeType instead of storing an inconsistent string.

Do not declare contentType as application/json if the actual payload is an object or another format that the converter cannot serialize to JSON. The header is only metadata; the converter and payload must actually be compatible.

### 2.3. replyChannel and errorChannel

replyChannel and errorChannel are metadata used for internal routing in Spring messaging flows. The value may be a MessageChannel or a bean/channel name depending on the mechanism used.

These are not business fields like orderId or tenantId. Such values may reference internal application objects, so they should not be arbitrarily serialized or transmitted intact to a broker or another service.

## 3. MessageHeaders Is Immutable

MessageHeaders implements Map<String, Object>, but this object is immutable. Direct mutating operations such as put, remove, clear, or putAll will throw UnsupportedOperationException.

The following example is invalid:

~~~java
message.getHeaders().put("appCorrelationId", "corr-42");
~~~

To add or change headers, create a new Message using MessageBuilder or use MessageHeaderAccessor.

Simple approach with MessageBuilder:

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-42")
        .setHeader("appCorrelationId", "corr-42")
        .setHeader("appSchemaVersion", 1)
        .build();

Message<String> enriched = MessageBuilder
        .fromMessage(message)
        .setHeader("appSource", "checkout")
        .build();
~~~

The new Message preserves the payload and copied headers, then adds or replaces the appSource value. The original message is not mutated directly.

Commonly used operations:

- setHeader(name, value): sets or replaces a header value.
- setHeaderIfAbsent(name, value): sets only if the key has no value yet.
- removeHeader(name): removes a header.
- copyHeaders(map): copies multiple headers and may overwrite existing keys.
- copyHeadersIfAbsent(map): copies only keys that do not yet exist.
- removeHeaders(patterns): removes headers matching patterns.

When using copyHeaders, understand its overwriting behavior. If metadata comes from multiple sources, prefer copyHeadersIfAbsent or copy only allowlisted keys.

## 4. Using MessageHeaderAccessor for Controlled Header Operations

MessageHeaderAccessor is a wrapper providing an API to read and modify headers. It also has specialized accessors for native headers, STOMP, JMS, and other protocols.

Example creating a new message:

~~~java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("appCorrelationId", "corr-42");
accessor.setHeaderIfAbsent("appSource", "checkout");
accessor.setContentType(MimeTypeUtils.APPLICATION_JSON);

MessageHeaders headers = accessor.getMessageHeaders();
Message<String> message = MessageBuilder.createMessage(
        "{\"orderId\":\"order-42\"}",
        headers
);
~~~

When getMessageHeaders() is called, the accessor by default finalizes header construction and no longer permits edits through that accessor itself; the returned MessageHeaders is also immutable. This behavior prevents a message already handed off to another component from being silently modified.

If there is a technical reason to leave headers mutable during a short initialization phase, MessageHeaderAccessor provides setLeaveMutable(true). Once finished, setImmutable() must be called to close modification capability. This approach suits initialization within a single thread; a mutable header set should not be passed across multiple threads or shared among multiple components.

To modify an existing message, you can obtain a mutable accessor:

~~~java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(message);

accessor.setHeader("appTenantId", "tenant-7");

Message<String> updated = MessageBuilder.createMessage(
        message.getPayload(),
        accessor.getMessageHeaders()
);
~~~

Only modify metadata that the current component owns. If a header contains authentication or tenant information established by the system, do not let data from the client overwrite it.

## 5. Standard, Framework, and Application Headers

In a real-world system, headers should be categorized by origin and scope of use.

| Group | Examples | Who defines it? | Handling rules |
|---|---|---|---|
| Spring core | id, timestamp, contentType, replyChannel, errorChannel | Spring Framework | Use standard constants/APIs; avoid manually overwriting |
| Spring messaging/SIMP | destination, message type, session ID, subscription ID, user | Spring messaging | Use specialized accessors; do not treat as business metadata |
| Protocol-native | JMS correlation ID, STOMP destination, receipt, content-type | Protocol/provider | Use corresponding adapter/accessor |
| Application-specific | appCorrelationId, appTenantId, appSchemaVersion | Application | Have a namespace, data type, and documented contract |

Do not lump everything into one "custom header" group. A value may be a standard header at the Spring layer yet be converted into a native header at the transport layer. Conversely, headers sent by a broker may exist only in the native headers section and not yet be promoted into application business headers.

## 6. Native Headers and Protocol Headers

NativeMessageHeaderAccessor provides a mechanism for storing headers obtained from external sources such as a broker. These headers are held in a separate sub-map under the key NativeMessageHeaderAccessor.NATIVE_HEADERS (the key value is nativeHeaders).

Separating them helps Spring distinguish:

- **Processing headers:** metadata Spring uses for internal routing or processing.
- **Native headers:** metadata belonging to the protocol or message broker, which must be preserved when encoding/decoding or sending/receiving over the transport.

NativeMessageHeaderAccessor provides operations such as setNativeHeader, addNativeHeader, getNativeHeader, getFirstNativeHeader, removeNativeHeader, and toNativeHeaderMap. Several protocols have specialized accessors extending this class.

### 6.1. JMS Headers

When using spring-jms, JmsHeaders and JmsMessageHeaderAccessor help work with Jakarta Messaging metadata. Properties you may encounter include:

- correlation ID;
- destination;
- delivery mode;
- expiration;
- message ID;
- priority;
- reply-to;
- redelivered;
- type;
- timestamp.

Use JmsHeaders and JmsMessageHeaderAccessor instead of guessing key names. Example reading a correlation ID mapped into a Spring Message:

~~~java
JmsMessageHeaderAccessor jmsAccessor =
        JmsMessageHeaderAccessor.wrap(message);

String correlationId = jmsAccessor.getCorrelationId();
Boolean redelivered = jmsAccessor.getRedelivered();
~~~

JMS properties may be mapped between JMS message headers, JMS properties, and Spring Message headers depending on the property type. Do not assume every application header automatically becomes a JMS property. Check the MessageConverter configuration and the integration mapping in use.

JMS property names have syntax restrictions following Java identifier rules. Avoid dots, hyphens, or spaces if a header needs to traverse JMS. In addition, JMS-reserved prefixes such as JMSX and JMS_ should not be used for application-defined business headers.

### 6.2. STOMP and WebSocket Headers

When using STOMP over WebSocket, StompHeaderAccessor manages STOMP frame headers. This class extends SimpMessageHeaderAccessor and NativeMessageHeaderAccessor.

Protocol headers you may encounter include destination, content-type, subscription, receipt, ack, message-id, and heart-beat. Spring processing headers may include destination, message type, session ID, session attributes, subscription ID, and user.

Some commonly used APIs:

- StompHeaderAccessor.getDestination() or setDestination(...).
- StompHeaderAccessor.setNativeHeader(name, value).
- StompHeaderAccessor.getFirstNativeHeader(name).
- SimpMessageHeaderAccessor.getSessionId() and getUser().

Example reading a native header sent by a STOMP client:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
String clientVersion = accessor.getFirstNativeHeader("appClientVersion");
String destination = accessor.getDestination();
~~~

The STOMP destination header and Spring's processing destination have a mapping relationship, but you should not modify the raw map directly when the accessor already provides a specialized API. Translating from processing headers to a STOMP frame also depends on the command and message direction.

### 6.3. Do Not Confuse Native Headers with Application Headers

Native headers reflect the external protocol. Application headers reflect metadata defined by the application's contract.

For example, appCorrelationId is a business header that may need to persist when an event travels through JMS and is then forwarded over STOMP. By contrast, JMS correlation ID or STOMP receipt are metadata specific to each protocol. When bridging between two protocols, the application must determine which headers need to be mapped, renamed, normalized, or dropped.

Do not copy the entire nativeHeaders map verbatim from one protocol to another. A key that is valid in STOMP may be invalid or meaningless in JMS. Use an intentional allowlist mapping.

## 7. Application Header Naming Conventions

Header names are part of the contract between producer and consumer. Without conventions, modules easily create colliding keys, mismatched data types, or interpret the same name with two different meanings.

### 7.1. Use a Dedicated Namespace

Add a prefix to headers owned by the application. For example:

| Header | Meaning | Suggested type |
|---|---|---|
| appCorrelationId | ID linking messages in a workflow | String |
| appCausationId | ID of the message/event that caused the current message | String |
| appEventId | Stable ID of the business event | String or string-formatted UUID |
| appTenantId | Tenant verified by the server | String |
| appSchemaVersion | Version of the payload contract | Integer or String |
| appSource | Name of the service or component emitting the message | String |
| appOccurredAt | Business occurrence timestamp | Instant in payload or epoch/string per contract |
| appTraceId | Trace ID for observability | String |

The app prefix is only an example. In systems with multiple teams, a short agreed-upon organizational prefix such as order, billing, or an organization namespace can be used. The important thing is not to use generic keys like type, source, status, or id if they easily collide with framework or protocol headers.

### 7.2. Choose Rules Compatible Across Multiple Transports

Header names in Spring are Strings and can be formatted in many naming styles. However, if a message will traverse multiple transports, choose a character set with broad compatibility.

Recommended conventions for headers shared across Spring, JMS, and STOMP:

- Start with a letter.
- Use only ASCII letters, digits, and underscores if needed.
- Use consistent camelCase, for example appCorrelationId.
- Do not use spaces, dots, or hyphens in keys that need to map to JMS properties.
- Preserve exact casing across all producers and consumers.
- Do not rename a header just to suit a local code layer; if a protocol requires a different name, map it at the adapter.

If a header exists only within STOMP, a name like app-correlation-id may be readable, but do not assume it is compatible with JMS properties. A camelCase name like appCorrelationId is generally smoother when the same metadata must traverse multiple protocols.

### 7.3. Avoid Reserved Namespaces

Do not define application headers that collide with the following groups:

- Standard Spring headers such as id, timestamp, contentType, replyChannel, and errorChannel.
- Internal SIMP headers such as simpSessionId, simpDestination, simpMessageType, or simpSubscriptionId.
- STOMP protocol headers such as destination, content-type, receipt, subscription, ack, and message-id.
- JMS properties or reserved prefixes such as JMSMessageID, JMSCorrelationID, JMSXDeliveryCount.
- Internal keys such as nativeHeaders.

Do not use prefixes like jms, stomp, simp, or spring for application business metadata. Those namespaces belong to adapters/frameworks and can alter protocol-specific handling.

### 7.4. Standardize Data Types

Headers can hold a Java Object, but not every transport can serialize every object type.

Prefer simple, stable types:

- String for IDs, service names, tenants, and symbolic versions.
- Integer/Long for counters, business priorities, or epoch milliseconds if specified by the contract.
- Boolean for simple flags.
- MimeType for Spring's standard contentType.
- UUID only when all parties agree on how to serialize and deserialize it.

Avoid storing a JPA entity, Spring bean, MessageChannel, HttpServletRequest, or large object in an application header. Such objects are not durable transport metadata and may fail to serialize.

Do not use a key as a String in one place and an Integer in another. Producers and consumers must agree on the data type. When passing through JMS or STOMP, some converters may turn values into Strings; verify the actual type after passing through the adapter.

## 8. Distinguishing Common IDs

Messaging systems often confuse message ID, correlation ID, causation ID, and business ID.

| ID type | Purpose | Lifecycle |
|---|---|---|
| Spring message id | Identifies a Message instance in Spring | Generated by Spring; not a business key |
| JMS message ID | Identifies a message according to the JMS provider | Managed by the provider |
| Correlation ID | Links request/reply or multiple messages in the same workflow | Preserved by producer/application per contract |
| Causation ID | Indicates which message produced the current message | Usually equals the ID of the preceding event/command |
| Business ID | Identifies a business entity such as orderId | Follows the entity's lifecycle |
| Trace ID | Links spans/logs in a distributed trace | Follows trace context and the tracing system |

Example:

~~~text
OrderCreated
  appEventId       = evt-100
  appCorrelationId = corr-900
  appCausationId   = null
  orderId          = order-42

PaymentRequested
  appEventId       = evt-101
  appCorrelationId = corr-900
  appCausationId   = evt-100
  orderId          = order-42
~~~

Correlation ID helps locate all messages belonging to a workflow. Causation ID captures causal relationships. Business ID identifies the business entity. These values are not interchangeable.

If idempotency is needed, choose a stable event ID or business key and store the corresponding processing result. Do not rely solely on the Spring message id because a message may be transformed, recreated, or replayed through a broker.

## 9. Propagation Rules When Messages Cross Multiple Services

A message may pass through multiple layers:

~~~text
HTTP / WebSocket / JMS
          |
          v
    Inbound adapter
          |
          v
   Spring Message
          |
          v
     Business handler
          |
          v
   Outbound adapter
          |
          v
  Another protocol/service
~~~

Each adapter may transform payloads and headers. Not every header is preserved intact. Some headers are renamed, some become native headers, and some cannot be represented in the target transport.

Establish clear mappings:

| Application header | JMS mapping | STOMP mapping |
|---|---|---|
| appCorrelationId | JMSCorrelationID or JMS property per contract | Native STOMP header |
| appEventId | JMS property per contract | Native STOMP header |
| appSchemaVersion | JMS property per contract | Native STOMP header |
| contentType | JMS `content_type` property via `JmsHeaderMapper.CONTENT_TYPE_PROPERTY`; distinct from `JMSType` (`JmsHeaders.TYPE`) | STOMP `content-type` and Spring `contentType` |
| replyChannel | Do not transfer raw channel object | Do not transfer raw channel object |

In Spring JMS, `SimpleJmsHeaderMapper` maps `MessageHeaders.CONTENT_TYPE` to the JMS `content_type` property. The `JMSType` property is the JMS-level message type and is represented by Spring as `JmsHeaders.TYPE`; it is not the payload's content type.

This table is a design example. The exact mapping must be implemented in the adapter or MessageConverter and tested against a real provider.

Propagation principles:

1. Forward only the headers that the recipient actually needs.
2. Preserve meaning and data types according to the contract.
3. Normalize correlation IDs at system boundaries.
4. Do not transmit Spring internal channel/session objects across brokers.
5. Do not copy authentication headers or sensitive information to logs or services that do not need them.
6. Define behavior when a header is missing, mistyped, or invalid.
7. Version application headers when contracts change.

When copying headers is needed, copyHeaders or copyHeadersIfAbsent can be used on builders/accessors. In systems with differing trust boundaries, create a new map containing an allowlist instead of copying all headers from the inbound message.

## 10. Security and Sensitive Data in Headers

Headers are often logged, surfaced in tracing, or stored in broker metadata. Therefore, secrets should not be put into headers simply because it is convenient.

Values to restrict:

- access tokens, refresh tokens, session cookies, and passwords;
- API keys or broker connection credentials;
- unnecessary personal information;
- authorization data that could be spoofed by clients;
- large payloads or sensitive business data.

Headers like appTenantId, appUserId, or role do not automatically become trustworthy just because they reside in MessageHeaders. If a value comes from a WebSocket client or an untrusted source, authenticate the principal and resolve tenant/permissions on the server side. Do not use client-sent headers to grant access to topics or queues.

When logging messages, log correlation ID, event ID, and necessary operational metadata; mask or omit secret headers. Also review log levels because some accessors can produce log messages containing metadata.

## 11. Example Design of an Application Header Set

Suppose the Order service publishes an OrderCreated event. A centralized set of keys can be defined:

~~~java
public final class OrderMessageHeaders {

    public static final String CORRELATION_ID = "appCorrelationId";
    public static final String EVENT_ID = "appEventId";
    public static final String SCHEMA_VERSION = "appSchemaVersion";
    public static final String SOURCE = "appSource";

    private OrderMessageHeaders() {
    }
}
~~~

Creating a message:

~~~java
Message<OrderCreated> message = MessageBuilder
        .withPayload(event)
        .setHeader(OrderMessageHeaders.CORRELATION_ID, correlationId)
        .setHeader(OrderMessageHeaders.EVENT_ID, eventId)
        .setHeader(OrderMessageHeaders.SCHEMA_VERSION, 1)
        .setHeader(OrderMessageHeaders.SOURCE, "order-service")
        .build();
~~~

Reading a message:

~~~java
String correlationId = message.getHeaders().get(
        OrderMessageHeaders.CORRELATION_ID,
        String.class
);

Integer schemaVersion = message.getHeaders().get(
        OrderMessageHeaders.SCHEMA_VERSION,
        Integer.class
);
~~~

A constants set ensures producers and consumers use the same keys. In multi-module systems, place this contract in a shared package/module with explicit versioning. If multiple services cannot share the same library, manage header names and types in schema documentation or contract tests.

Do not create a single shared constants class across all protocols if those keys only have meaning in JMS or STOMP. Keep application headers and protocol headers separate so boundaries remain clear.

## 12. Testing Header Contracts

A header test suite should verify name, type, default values, and propagation behavior.

Cases to include:

1. Created messages include all required application headers.
2. The standard contentType header has the correct MimeType.
3. ID and timestamp are generated by Spring according to configuration.
4. Consumers read headers with the expected type.
5. setHeaderIfAbsent does not overwrite an existing value.
6. copyHeaders and copyHeadersIfAbsent behave properly on duplicate keys.
7. MessageHeaders cannot be mutated directly after building.
8. Internal headers such as replyChannel or simpSessionId are not leaked externally unless permitted.
9. JMS mapping preserves correlation ID, event ID, and value types specified by the contract.
10. STOMP native headers are encoded/decoded properly over WebSocket.
11. Missing or mistyped headers are handled according to an explicit policy.
12. Clients cannot spoof tenant or user identity using application headers.

Unit tests can verify MessageBuilder and MessageHeaderAccessor. Integration tests must use a real adapter/provider or corresponding test environment to confirm native header mapping, because testing in-memory Message instances does not prove the transport preserves metadata.

## 13. Checklist Before Releasing a New Header

- Does the header name have a namespace owned by the application?
- Does it collide with Spring core, SIMP, JMS, or STOMP names?
- Is the name compatible with all transports in the flow?
- Have the data type and unit of measurement been defined?
- Is the header truly metadata, or should it belong in the payload?
- Which producers are allowed to set the header?
- Which consumers read it, and is missing-header handling implemented?
- Is the header kept, renamed, or dropped at each adapter?
- Could it leak tokens, PII, or authorization details?
- Have contract tests verified mapping and propagation?

## 14. References

- [Spring Framework 6.1 — MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework 6.1 — MessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework 6.1 — NativeMessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html)
- [Spring Framework 6.1 — JmsMessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/support/JmsMessageHeaderAccessor.html)
- [Spring Framework 6.1 — StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)

A good header has one clear meaning, one owner, one stable data type, and one testable propagation rule. When those four properties hold, services can exchange messages across multiple transports without depending on ad-hoc key names or an adapter's internal metadata.