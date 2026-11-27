# Immutable Messages and Data Passed Through Runtime

In Spring Integration, a message is the unit of data passed between components of an integration flow. A message carries a **payload** (business content) and **headers** (metadata for routing, correlation, replies, error handling, and runtime observability). Properly understanding message immutability helps predict which data is shared between endpoints, avoid race conditions in multi-threaded execution, and design stable retries, splitters, and aggregators.

An essential point to remember from the start: a standard Spring message has an immutable envelope, but that **does not automatically make the payload immutable**. If the payload or a header value is a mutable object, multiple endpoints can still see and modify that same object as the message travels through channels within the same JVM.

## 1. Structure of a message

In Spring Messaging, `Message<T>` represents a payload of type `T` along with a set of headers:

```java
public interface Message<T> {
    T getPayload();
    MessageHeaders getHeaders();
}
```

Example of a message containing an order:

```java
Message<Order> message = MessageBuilder
        .withPayload(order)
        .setHeader("tenantId", "tenant-42")
        .setHeader("correlationId", "checkout-2026-001")
        .build();
```

You can visualize the structure as follows:

```text
Message<Order>
├── payload: Order
│   ├── orderId
│   ├── customer
│   └── lines
└── headers: MessageHeaders
    ├── id
    ├── timestamp
    ├── tenantId
    └── correlationId
```

The payload typically holds the data that a processing step needs to read or transform. Headers describe the message and its processing context: which tenant the message belongs to, which business flow it is in, where to send a reply, or by which criteria it should be routed.

### 1.1. What does envelope immutability mean?

Standard message implementations such as `GenericMessage` do not provide setters to replace the payload after creation. `MessageHeaders` is also designed as a read-only map. Therefore, the following code is not a valid way to update a header:

```java
message.getHeaders().put("priority", 10); // Not supported
```

The headers map does not permit direct writes; this operation typically throws `UnsupportedOperationException`. To change metadata, the application must create a new message using `MessageBuilder`, a header enricher, or an appropriate endpoint.

However, immutability here is **shallow immutability**:

- You cannot change the payload reference or modify the headers map structure of a standard message after creation.
- You can still change the internal state of the payload object if the payload class has setters, mutable collections, or mutable child objects.
- A value stored in a header can also be a mutable object. A map disallowing key/value changes does not mean the object behind that value is immutable.

For example, if the payload is an `ArrayList`, code receiving the message can still call `add()` on that list. If the `routingContext` header contains a `HashMap`, code holding a reference to the map can still modify the map's contents. The envelope was not replaced, yet the data observed by endpoints has changed.

| Component | What is protected | What is not automatically protected |
|---|---|---|
| Standard message | No setter API to replace the payload on a created message | Internal state of the payload |
| `MessageHeaders` | Read-only headers map structure | Internal state of objects used as header values |
| Immutable object payload | Business values do not change after creation | Child objects if they remain mutable |
| Mutable collection payload | No special protection | Elements, ordering, and collection contents |

Therefore, when you need a message that is truly safe to share across multiple threads, you must examine both the payload design and header values, not just `Message<?>` itself.

## 2. Creating a new message when data changes are needed

`MessageBuilder` is the common API for creating messages. Two main usage patterns correspond to two different scenarios.

### 2.1. Creating a new message from a payload

When starting a flow or creating a new payload, use `withPayload()`:

```java
Message<Order> incoming = MessageBuilder
        .withPayload(order)
        .setHeader("source", "checkout-api")
        .setHeader("tenantId", tenantId)
        .setHeader("correlationId", requestId)
        .build();
```

Headers are added to the builder before calling `build()`. After building, the application receives a complete message with the payload and headers set.

### 2.2. Creating a new message based on an existing message

When you only need to add or adjust metadata while keeping the payload, use `fromMessage()`:

```java
Message<Order> prioritized = MessageBuilder
        .fromMessage(incoming)
        .setHeader("priority", 10)
        .setHeader("route", "express")
        .build();
```

The builder creates a new message based on the input message. The old message still exists and is not modified in place. This is the appropriate way to retain the payload and necessary metadata while creating the next version of the message.

### 2.3. Creating a new payload and carrying over necessary headers

When a transformer converts a payload from one type to another, create a message with the resulting payload and copy the headers that need to be forwarded:

```java
Message<NormalizedOrder> normalized = MessageBuilder
        .withPayload(normalize(incoming.getPayload()))
        .copyHeaders(incoming.getHeaders())
        .setHeader("normalizationVersion", 1)
        .build();
```

`copyHeaders()` helps preserve metadata during transformation. Copying the headers map copies the map structure; objects referenced by header values are not necessarily deep-cloned. If a header contains a mutable collection or object, the new message and the old message may both reference that same object.

System headers such as `id` and `timestamp` are managed by Spring according to the message creation API rules. Do not use them as order IDs, payment IDs, or idempotency keys. Pass separate business identifiers such as `orderId`, `requestId`, or `correlationId`.

### 2.4. What should headers contain?

Headers are suited for small metadata that is meaningful across the processing flow:

- `correlationId`: links messages belonging to the same business process or request.
- `tenantId`: identifies the tenant context when the system supports multi-tenancy.
- `contentType`: describes the content format when converters need this information.
- `replyChannel` and `errorChannel`: provide the reply destination or error destination in flows that support the corresponding mechanisms.
- `sequenceNumber` and `sequenceSize`: support processing message groups produced by splitters and aggregators.

Avoid putting entire large business objects into headers. Primary data belongs in the payload; headers should describe how the runtime routes or processes the message. Also be cautious when placing channel objects, connections, sessions, or non-serializable objects into headers if the message might pass through a message store or system boundary.

## 3. Designing immutable payloads

If multiple endpoints may read the same payload, the safest approach is to use immutable objects. In Java, `record` is a concise choice for DTOs containing only immutable values:

```java
public record OrderLine(String sku, int quantity) {}

public record Order(String id, List<OrderLine> lines) {
    public Order {
        lines = List.copyOf(lines);
    }
}
```

`List.copyOf()` creates a list that cannot be modified through the reference stored in the record. This example is safe when `OrderLine` elements are also immutable. If elements are mutable objects, copying the list is still only a shallow copy; you need to create immutable copies of each element or convert them into immutable data types.

Some practical guidelines:

1. Prefer `record`, classes with only `final` fields, and immutable collections for DTOs passed through a flow.
2. Copy collections at the ingestion boundary; do not retain references to mutable collections owned by the caller.
3. Do not provide setters or methods that mutate business state after the payload has been placed into a message.
4. When updates are needed, create a new payload from the old payload instead of mutating a shared object.
5. Avoid placing mutable objects in headers; if needed, use simple values or immutable objects.

If an immutable payload cannot be used, clearly define which endpoint owns write permissions and where a defensive copy must be made. This convention must be applied consistently across the entire flow; even a single endpoint mutating data can make another endpoint's outcome depend on execution order.

## 4. How are messages passed through the runtime?

A flow typically receives data from an inbound adapter or gateway, creates a message, passes the message through channels, and hands it to endpoints for processing:

```mermaid
flowchart LR
    A[Inbound adapter / Gateway] --> B[Message]
    B --> C[MessageChannel]
    C --> D[Transformer / Router / Filter]
    D --> E[MessageChannel]
    E --> F[Service Activator]
    F --> G[Outbound adapter]
```

A channel is the mechanism that hands off messages between components. Channels do not by default clone payloads, serialize messages, or convert data types. For channels running within the same JVM, the payload typically continues to be the same object reference created at the start of the flow, unless a specific endpoint, interceptor, or integration mechanism creates a new message/payload.

Therefore, distinguish **a message being passed through a channel** from **data being copied or transformed**. These two are not synonymous.

### 4.1. Differences between common channels

| Channel | Delivery mechanism | Consequence for mutable payloads |
|---|---|---|
| `DirectChannel` | Invokes the handler synchronously on the sending thread | The handler executes immediately on the sending thread and typically receives the same payload reference |
| `QueueChannel` | Places the message into a queue for a consumer to retrieve later | The in-memory queue holds the message/reference; processing time differs from send time, but it does not automatically make a deep copy |
| `ExecutorChannel` | Dispatches processing via a `TaskExecutor` | The handler may run on a different thread; sharing a mutable payload can cause race conditions |
| `PublishSubscribeChannel` | Broadcasts the message to multiple subscribers | Multiple subscribers may observe the same payload; if running concurrently, mutating the payload can conflict |

`PublishSubscribeChannel` can be configured with an executor for asynchronous processing. Without an executor, broadcasting to subscribers typically occurs synchronously. `DirectChannel` typically dispatches a message to a single subscriber selected according to the dispatcher/load-balancing configuration; it does not have broadcast semantics like `PublishSubscribeChannel`.

`QueueChannel` can use a message store as its storage backend. When using a persistent store or an adapter communicating with a broker/external system, data may be mapped, serialized, or deserialized depending on configuration. Beyond that boundary, you should not rely on the Java object identity of the original payload.

### 4.2. Synchronous and asynchronous execution do not determine immutability

Synchronous only describes the timing and thread of handler execution. Asynchronous only means sending and processing can be decoupled. Neither turns a mutable payload into an immutable payload.

For example, if two endpoints both hold a reference to an `ArrayList`, passing through an `ExecutorChannel` can cause one endpoint to read while the other adds elements. The outcome may depend on thread scheduling, causing hard-to-reproduce bugs.

```java
// Risk: payload contains a mutable list.
List<OrderLine> lines = new ArrayList<>(order.getLines());
Message<List<OrderLine>> message = MessageBuilder
        .withPayload(lines)
        .build();

// If multiple consumers receive the message, one consumer modifying the list
// can affect the remaining consumers.
```

The solution is to convert the payload to immutable data before broadcasting to multiple consumers, or create a separate copy for each branch if each branch needs write access. If mutable state must be synchronized, an explicit synchronization mechanism must be designed; do not expect the channel to solve this problem automatically.

## 5. How do endpoints affect messages?

Endpoints in Spring Integration have different roles. Distinguishing their roles helps identify which step merely forwards a message and which step creates new data.

| Endpoint | Typical behavior | What to check |
|---|---|---|
| Router | Selects target channel(s) based on payload or headers | Which branch the message is routed to; whether routing headers are correct |
| Filter | Lets the message proceed or discards it | Filter condition; whether discarded messages are handled via a discard flow |
| Transformer | Converts the payload or adds metadata, typically creating a result message | Input/output payload types and headers to retain |
| Splitter | Splits a single payload into multiple child messages | Correlation and sequence metadata for reassembly |
| Aggregator | Combines related messages into a single result | Correlation strategy, release strategy, and group state |
| Service Activator | Invokes a business method with payload/headers; may produce a reply | Parameter types, header binding, and return value |
| Bridge | Connects two channels and forwards messages | Target channel and interceptors along the path |

A DSL flow illustrating enriching metadata and then transforming the payload:

```java
@Bean
IntegrationFlow normalizeOrders() {
    return IntegrationFlow.from("orders.input")
            .enrichHeaders(headers -> headers
                    .header("source", "checkout")
                    .header("schemaVersion", 1))
            .transform(Order.class, this::normalize)
            .channel("orders.normalized")
            .get();
}
```

Here, the header enricher adds metadata to the message in the flow. The transformer calls `normalize` to produce the normalized payload. When the payload changes type or content, check which headers must be retained so subsequent steps continue to route, correlate, and process properly.

### 5.1. Splitter and aggregator

A splitter typically turns a single input message into multiple child messages. The child messages need correlation and ordering metadata so the aggregator knows they belong to the same group. Spring Integration uses headers such as `correlationId`, `sequenceNumber`, and `sequenceSize` in these scenarios.

An aggregator collects messages in the same group according to a correlation strategy, checks release conditions using a release strategy, and then creates the result message. When building a custom splitter or aggregator, do not arbitrarily remove or overwrite correlation headers. If the business domain requires a custom correlation key, define that key clearly and ensure all branches forward it consistently.

## 6. Messages, conversion, and system boundaries

A channel within the same application typically passes message objects. Format conversion usually occurs at adapters, gateways, or endpoints configured with converters. For example, an inbound adapter can convert data from an external protocol into a Java payload; an outbound adapter can map the payload and certain headers into data sent to the target system.

Do not assume every internal header will automatically cross system boundaries. A header mapper may only allow a specific set of headers, rename them, or drop unsuitable headers. Values like `replyChannel` and `errorChannel` may represent runtime objects inside the application, not protocol data suitable for sending to another system.

When a message is stored in a message store or sent via a broker, clearly verify:

- Whether the payload can be serialized/deserialized with the configured mechanism.
- Which headers need to be restored upon reading back.
- Which headers are only meaningful in the current JVM and must be removed or mapped.
- How the payload schema version is managed when producer and consumer are deployed at different times.
- Whether data is copied at that boundary or only held by reference in memory.

Serialization is no substitute for schema design. A Java class that is serializable today can still cause issues when packages change, fields change, or application versions are upgraded. For inter-system flows, use an explicit data contract and configured converters rather than relying on internal object details.

## 7. Impact on retries, transactions, and correlation

Immutability makes message reprocessing more predictable. When an endpoint fails and a retry mechanism re-invokes the logic, an immutable payload preserves the original business input. If the previous attempt mutated a shared mutable object, the retry may start from the altered state and produce a different result.

A transaction manages the commit/rollback of transactional resources. A transaction does not automatically undo changes to an in-memory Java object. If code mutates the payload and then the database transaction rolls back, the payload object may still retain the modified state. Therefore, rollback should not be treated as a payload recovery mechanism.

Correlation and idempotency must also be distinguished:

- `correlationId` links messages within the same request or processing group.
- `MessageHeaders.ID` identifies a specific message according to Spring's mechanism.
- An idempotency key is a business identifier defined by the application to recognize whether a request has already been processed; for example, `paymentRequestId` or `orderId` combined with operation type.

Do not use the message ID as an idempotency key if the business logic needs to recognize two re-submissions of the same request. A new message can have a different message identity while still representing the same business request.

When a flow has retries, a message store, or an aggregator, keep the payload and correlation metadata stable. If processing state needs to be recorded, create new metadata or events intentionally; avoid implicitly mutating a shared object.

## 8. Observing and diagnosing data at runtime

When a message traverses multiple endpoints, observe both the payload type and metadata. Useful logs typically record:

- The name of the flow, endpoint, or channel currently processing.
- `id` and `correlationId` if present.
- Payload type (`payload.getClass().getName()`) and a business identifier that is safe to log.
- Relevant routing headers or schema version.
- Thread name and processing timestamp when investigating concurrency issues.

Do not log the entire payload or headers by default if they might contain sensitive information, tokens, or personal data. Select the necessary fields and mask data according to the application's policy.

When output data is not as expected, check in this order:

1. What payload type does the inbound adapter/gateway create, and are any converters involved?
2. Is the channel synchronous, queued, or executor-backed; how many consumers are there?
3. Which endpoint transforms the payload or adds/removes headers?
4. Does any `ChannelInterceptor` alter the message at `preSend` or block the message?
5. Does the message cross a message store, broker, or serialize/deserialize boundary?
6. Do multiple consumers hold references to a mutable payload or header value?

In particular, if an error only appears when enabling an executor or increasing the number of subscribers, check payload ownership and mutability before concluding that the channel is losing data.

## 9. Design rules to apply

- Treat a message as an envelope consisting of payload and headers; use the payload for business data and headers for runtime metadata.
- Treat standard messages and `MessageHeaders` as immutable; use builders or endpoints to create a new message when changes are needed.
- Design immutable payloads, including nested collections and objects, before sharing across multiple branches or threads.
- Do not assume channels within the same JVM will clone, deep-copy, or serialize payloads.
- Clearly define channels and execution models to understand whether messages are processed synchronously, via a queue, or via an executor.
- Preserve required correlation/sequence headers when transforming, splitting, and aggregating.
- Do not use message `id` or `timestamp` as a business identifier or idempotency key.
- Define payload/header contracts at message store and external system boundaries; only pass headers that are actually needed.
- When debugging, track correlation, payload type, endpoint, and thread; check interceptors if messages change unexpectedly.

By following these principles, messages become a predictable unit of exchange at runtime. An immutable envelope prevents endpoints from accidentally overwriting message structure; an immutable payload lets multiple endpoints and threads read data safely; and understanding channels and conversion boundaries pinpoints exactly where data is preserved, transformed, or persisted.
