# Copying, Adding, Removing, and Restricting Sensitive Headers

In Spring Messaging, headers are metadata attached to a Message. When a message passes through multiple handlers or is forwarded to JMS, STOMP, or another service, an application often needs to copy certain headers, add processing details, remove metadata that is no longer meaningful, and prevent sensitive data from crossing unauthorized boundaries.

These operations require explicit rules. Copying all headers can accidentally carry along internal channels, session objects, authentication details, or client-declared data. The safe approach is to determine which headers belong to the application contract and forward only permitted keys.

## 1. Principle of Immutability

MessageHeaders implements Map<String, Object>, yet the headers of a created message are normally immutable. Do not modify them directly using put, remove, or clear:

~~~java
message.getHeaders().put("appCorrelationId", "corr-42");
~~~

The operation above will throw UnsupportedOperationException. To modify headers, create a new message using MessageBuilder or use MessageHeaderAccessor.

This approach prevents one component from silently altering metadata that another component is reading. Every header addition or removal produces an inspectable, testable processing step.

## 2. Copying Headers from an Existing Message

### 2.1. Using MessageBuilder.fromMessage

fromMessage creates a builder for a new message, keeping the payload and copying headers from the source message:

~~~java
Message<String> forwarded = MessageBuilder
        .fromMessage(inbound)
        .build();
~~~

This is a convenient way to create a new message with the same payload and metadata. However, it also copies headers that the current component should perhaps not forward, such as replyChannel, errorChannel, simpSessionAttributes, or an adapter's internal headers.

Therefore, before using fromMessage across service or protocol boundaries, specify clearly which headers are permitted at the destination.

### 2.2. Using copyHeaders

copyHeaders(Map<String, ?>) copies key-value pairs from a map into the builder. Values from the map overwrite headers with matching names already present in the builder. The two system headers id and timestamp are not overwritten.

~~~java
Map<String, Object> extraHeaders = new HashMap<>();
extraHeaders.put("appSource", "order-service");
extraHeaders.put("appSchemaVersion", 2);

Message<String> enriched = MessageBuilder
        .fromMessage(inbound)
        .copyHeaders(extraHeaders)
        .build();
~~~

In the example, appSource and appSchemaVersion are added to the message. If the source message already had either key, the value from extraHeaders replaces the old value.

Use copyHeaders when the current component is the authoritative source for the keys being written. Do not use it arbitrarily with maps received directly from clients or untrusted systems.

### 2.3. Using copyHeadersIfAbsent

copyHeadersIfAbsent(Map<String, ?>) only copies keys that do not yet have a value. Headers already present in the builder are preserved.

~~~java
Message<String> enriched = MessageBuilder
        .fromMessage(inbound)
        .copyHeadersIfAbsent(extraHeaders)
        .build();
~~~

This approach fits when adding default metadata. For example, a handler can set appSource if an upstream producer has not already provided it.

Distinguish the two methods:

| Method | When key already exists | Suitable use case |
|---|---|---|
| copyHeaders(map) | Overwrites old value | Current component owns the new value |
| copyHeadersIfAbsent(map) | Preserves old value | Supplying default values |
| setHeader(name, value) | Writes new value; if value is null, removes key | Updating a specific header |
| setHeaderIfAbsent(name, value) | Sets only when key has no value yet | Adding a single header |

Note: copyHeaders does not mean every header may be overwritten. id and timestamp are system headers protected by Spring according to MessageBuilder's rules.

## 3. Adding and Updating Headers

### 3.1. setHeader

setHeader sets or replaces a header's value:

~~~java
Message<String> message = MessageBuilder
        .withPayload("order-42")
        .setHeader("appCorrelationId", "corr-900")
        .setHeader("appSource", "checkout")
        .setHeader("appSchemaVersion", 2)
        .build();
~~~

Each key should have one consistent meaning and data type. For instance, appSchemaVersion should always be Integer or always be String per the chosen contract; do not let producers send a number in one place and a string in another.

### 3.2. setHeaderIfAbsent

To add a default value without replacing an existing value, use setHeaderIfAbsent:

~~~java
Message<String> message = MessageBuilder
        .fromMessage(inbound)
        .setHeaderIfAbsent("appSource", "unknown-producer")
        .build();
~~~

This is useful when multiple handlers enrich metadata. Downstream handlers will not overwrite a valid value already set by an upstream handler.

### 3.3. setHeader with null

In MessageBuilder and MessageHeaderAccessor, setting a null value means removing that header:

~~~java
Message<String> sanitized = MessageBuilder
        .fromMessage(inbound)
        .setHeader("appTemporaryFlag", null)
        .build();
~~~

If a genuinely null business value needs to be represented, define that convention in the payload or schema. A header map does not distinguish a key with a null value from a removed key in a way usable as a stable contract.

## 4. Removing One or Multiple Headers

### 4.1. Removing a single key

Use removeHeader when you know the exact key to remove:

~~~java
Message<String> sanitized = MessageBuilder
        .fromMessage(inbound)
        .removeHeader("appInternalRoute")
        .build();
~~~

removeHeader fits when a header is meaningful only at one processing layer. For example, an internal adapter has finished using appInternalRoute and does not want to pass that metadata to the next service.

### 4.2. Removing by pattern

removeHeaders(String... headerPatterns) removes multiple keys matching simple patterns. Spring supports these forms:

- xxx*: keys starting with xxx.
- *xxx: keys ending with xxx.
- *xxx*: keys containing xxx.
- xxx*yyy: keys starting with xxx and ending with yyy.

Example:

~~~java
Message<String> sanitized = MessageBuilder
        .fromMessage(inbound)
        .removeHeaders(
                "authorization",
                "cookie",
                "*token*",
                "*secret*",
                "appInternal*"
        )
        .build();
~~~

Patterns help remove a group of headers sharing a naming convention. Use them deliberately; an overly broad pattern can remove metadata needed for tracing or correlation.

Header names in MessageHeaders are Map keys and must match the exact names the application uses. Do not assume every adapter normalizes letter casing identically.

### 4.3. Removing headers with MessageHeaderAccessor

MessageHeaderAccessor provides a similar API for editing headers:

~~~java
MessageHeaderAccessor accessor =
        MessageHeaderAccessor.getMutableAccessor(inbound);

accessor.removeHeader("appInternalRoute");
accessor.setHeaderIfAbsent("appSource", "order-service");

Message<String> sanitized = MessageBuilder.createMessage(
        inbound.getPayload(),
        accessor.getMessageHeaders()
);
~~~

getMutableAccessor creates an editable accessor for an existing message and attempts to preserve the original accessor type so downstream components continue understanding specialized metadata.

By default, when getMessageHeaders() is called, the accessor finalizes header construction and transitions them to an immutable state. If setLeaveMutable(true) is set, headers remain mutable after retrieving MessageHeaders; once finished, setImmutable() must be called. Keeping headers mutable should only be used during a short initialization phase, usually within a single thread; do not let a mutable message travel across multiple threads or independent components.

## 5. Restricting Sensitive Headers When Forwarding Messages

### 5.1. Why not copy all headers?

An inbound message may contain many kinds of metadata:

- Business headers such as appCorrelationId, appEventId, or appSchemaVersion.
- Internal headers such as replyChannel, errorChannel, or session information.
- Transport headers such as destination, receipt, or broker correlation IDs.
- Authentication headers such as authorization, cookie, access token, or API key.
- Client-declared headers that have not yet been verified by the server.

When forwarding a message to another service, some headers may no longer be meaningful. Others may leak information if they appear in logs, brokers, or tracing systems.

In particular, do not place access tokens, refresh tokens, passwords, session cookies, API keys, or broker connection credentials into business headers merely for convenience across services. If a transport requires credentials at the connection layer, let the transport's security mechanism manage them separately and do not copy them into application messages.

### 5.2. Prefer an allowlist

An allowlist specifies exactly which headers are permitted to cross a boundary. This is an easily controlled approach when messages arrive from browsers, public APIs, external brokers, or another service.

Example forwarding only correlation ID, event ID, and schema version:

~~~java
private static Map<String, Object> allowedHeaders(Message<?> inbound) {
    Map<String, Object> allowed = new HashMap<>();

    for (String name : List.of(
            "appCorrelationId",
            "appEventId",
            "appSchemaVersion"
    )) {
        Object value = inbound.getHeaders().get(name);
        if (value != null) {
            allowed.put(name, value);
        }
    }

    return allowed;
}
~~~

Create the outbound message from the payload and filtered map:

~~~java
Message<?> outbound = MessageBuilder
        .withPayload(inbound.getPayload())
        .copyHeaders(allowedHeaders(inbound))
        .setHeader("appForwardedBy", "order-service")
        .build();
~~~

The outbound message receives only allowlisted keys and headers set by the current service itself. Because the builder starts with withPayload, unselected internal headers are not carried over. Spring generates system metadata for the new message per its default mechanism.

If appCorrelationId or appEventId comes from an external source, validate length, format, and data type before putting it into the allowlist. If appTenantId is a server-established value, do not take it from a client header and forward it as trusted data.

### 5.3. Denylist is only an additional filtering layer

Within a trusted internal flow, you can copy the message and strip known sensitive keys:

~~~java
Message<?> outbound = MessageBuilder
        .fromMessage(inbound)
        .removeHeaders(
                "authorization",
                "cookie",
                "set-cookie",
                "*token*",
                "*secret*",
                "appPrivate*"
        )
        .build();
~~~

A denylist is useful when the system already has a relatively stable header contract and wants to strip specific groups. However, a new sensitive header can appear with a name not yet on the list. Thus, a denylist does not replace an allowlist when transferring data across trust boundaries.

Do not copy everything and strip only a few keys if the input source can create arbitrary headers. Restrict the accepted key list upfront.

## 6. Native Headers Require Separate Handling

Some adapters store external protocol headers in a native header map, separated from the processing headers Spring uses internally. For example, STOMP frames have their own native headers.

Consequently, calling removeHeaders on MessageBuilder only handles keys at the corresponding MessageHeaders level; do not assume it removes keys nested inside the native header map.

For STOMP, use StompHeaderAccessor or NativeMessageHeaderAccessor to manipulate native headers:

~~~java
StompHeaderAccessor accessor = StompHeaderAccessor.wrap(inbound);

accessor.removeNativeHeader("authorization");
accessor.removeNativeHeader("appPrivateToken");

Message<?> sanitized = MessageBuilder.createMessage(
        inbound.getPayload(),
        accessor.getMessageHeaders()
);
~~~

If the message is forwarded over JMS, use the corresponding JMS accessors/header mappers and verify the provider's actual mapping. Do not copy STOMP native headers verbatim into JMS or vice versa: key names, value types, and protocol semantics can differ.

An allowlist at the application layer is still necessary. Removing sensitive native headers is an extra safeguard for the adapter, not a reason to forward all native headers.

## 7. Ownership and Trustworthiness of Headers

Not all headers in a message carry the same level of trust.

| Header source | Handling approach |
|---|---|
| Generated by Spring such as id and timestamp | Leave to Spring management; do not use in place of business IDs |
| Created by the current service | May update if this service owns that contract |
| Sent by another internal service | Validate schema, data type, and ownership before overwriting |
| Sent by WebSocket/HTTP client | Treat as untrusted input; authenticate and validate |
| Sent by broker or protocol adapter | Use specialized accessors and verified mappings |
| Authentication/credential headers | Do not place in application headers or logs; handle at security/transport layer |

A header named appTenantId or appUserId does not prove the sender belongs to that tenant or user. The server must obtain identity from SecurityContext or an authenticated principal and resolve permitted values itself.

Similarly, client-sent appRole, appPermission, or appIsAdmin must never be used to grant privileges. Headers are data; access permissions must be decided by server-side authentication and authorization mechanisms.

## 8. Limiting Count, Size, and Data Types

In addition to restricting which keys are copied, applications should enforce limits on inbound header data:

- Limit the number of accepted headers.
- Limit the length of key names and values.
- Allow only data types that serialize stably.
- Reject arbitrary objects, Spring beans, channels, servlet requests, or large entities.
- Limit total metadata size before sending across a broker or WebSocket.
- Normalize and validate formats for IDs, versions, tenants, and correlation values.
- Drop or reject keys outside the contract if the sender is not allowed to extend headers.

Specific limits depend on protocol and infrastructure. JMS providers, STOMP brokers, reverse proxies, and applications may have different thresholds. Do not assume one global Spring limit automatically protects every transport.

Also consider data types after serialization. An Integer in a Spring Message may become a String after traversing an adapter or broker. Contracts should define types at every boundary and include tests for actual mappings.

## 9. A Safe Header-Processing Flow

Example of an API gateway receiving a message from a client and forwarding it to a business service:

~~~text
Client
  |
  | payload + client-sent headers
  v
Inbound validation
  |
  | authenticate principal, validate key/value
  | keep only permitted application headers
  v
Application Message
  |
  | add appSource, appCorrelationId
  | strip internal/sensitive headers
  v
Outbound adapter
  |
  | map to JMS/STOMP per contract
  v
Downstream service
~~~

An appropriate processing sequence:

1. Receive the message and identify the sender.
2. Authenticate identity at the security layer.
3. Validate keys, data types, lengths, and total header size.
4. Select permitted application headers using an allowlist.
5. Attach metadata owned by the current service.
6. Remove internal or protocol headers unsuitable for the destination.
7. Map native headers at the target adapter.
8. Log using correlation/event IDs, without logging credentials or sensitive data.

Do not pass raw MessageHeaders across every service merely because all services use Spring. Each boundary should have its own contract and receive only the metadata it needs.

## 10. Testing Header Copying and Filtering

Have unit tests for allowlist/denylist logic and integration tests for adapters.

Important scenarios:

1. copyHeaders overwrites a matching application header as expected.
2. copyHeadersIfAbsent preserves an existing value.
3. setHeaderIfAbsent does not overwrite a source value.
4. setHeader with null and removeHeader remove the exact key.
5. removeHeaders handles supported patterns accurately.
6. id and timestamp are not overwritten via copyHeaders.
7. authorization, cookie, token, and secret headers do not appear in the outbound message.
8. Non-allowlisted headers are stripped when crossing a public boundary.
9. replyChannel, errorChannel, and session metadata are not forwarded to unrelated services.
10. Sensitive native STOMP headers are removed using the appropriate accessor.
11. Client-sent tenant/user headers cannot replace server-authenticated identity.
12. Mistyped, oversized, or excessive headers are rejected according to policy.
13. JMS/STOMP mapping preserves valid application headers and does not carry unauthorized protocol metadata.

Unit tests only verify in-memory logic. To verify native headers and serialization, run integration tests against the corresponding adapter/provider or broker.

## 11. Checklist Before Forwarding a Message

- Is the payload preserved according to the contract?
- Which headers does the target service actually need?
- Which headers belong to internal Spring or the source protocol?
- Are there authentication, cookie, token, secret, or PII headers?
- Is the sender authorized to set those headers?
- Is an allowlist or denylist appropriate for the trust boundary?
- Which values could copyHeaders overwrite?
- Which native protocol headers must be mapped?
- Are data types and sizes valid on the target transport?
- Could logs or tracing accidentally record sensitive metadata?
- Are there tests proving unauthorized headers are removed?

## 12. References

- [Spring Framework 6.1 — MessageBuilder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework 6.1 — MessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- [Spring Framework 6.1 — MessageHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- [Spring Framework 6.1 — NativeMessageHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html)
- [Spring Framework 6.1 — StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework Reference — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)

A practical, maintainable rule of thumb is: copy selectively, overwrite only headers owned by the current component, strip internal metadata across boundaries, and never let credentials travel inside application messages.