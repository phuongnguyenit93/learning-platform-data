# Payload types and data type contracts

## 1. Why is the payload type part of message system design?

In Spring Integration, a *message* is not merely a JSON snippet passing through a queue. It has a **payload** containing the data to process and **headers** describing the transmission context. Endpoints such as **Gateway, Filter, Transformer, Router, Splitter, Aggregator** interact with messages in different ways. For components to stay loosely coupled, each boundary needs a clear contract: what data type it accepts, which fields are required, what the content means, and what type it emits.

For example, an order processing flow might have these stages:

1. Gateway receives an `OrderPlacedV1` payload.
2. Filter checks content validity.
3. Transformer normalizes it into a `ValidatedOrder` payload.
4. Router inspects the region attribute to pick one of two channels.
5. Splitter creates an `OrderLineTask` payload for each line item.
6. Aggregator collects results sharing the same `orderId` into an `OrderSummary`.

Without publishing types and structures at those steps, a handler might expect `OrderPlacedV1` yet actually receive `String` or `byte[]`. Failures might surface only at runtime, even after the message has passed through several channels.

**Learning objective:** distinguish in-memory data types from wire representations; choose suitable payloads; define versioned data type contracts; practice safe type checking and conversion; test every branch and failure mode when data violates the contract.

## 2. Structure of Message<T> and the role of generics

Spring Messaging defines `Message<T>` with two main parts:

- **`getPayload()`:** returns a value of type `T` per Java declaration; the payload holds the primary business data.
- **`getHeaders()`:** returns `MessageHeaders`, containing information like `id`, `timestamp`, and custom headers.

A concise, self-contained example illustrating an in-memory message only (Section 5 will expand this record into an order contract with line items):

~~~java
record OrderPlacedV1(String eventId, String orderId, String region) {}

OrderPlacedV1 order = new OrderPlacedV1("evt-101", "ord-501", "vn");
Message<OrderPlacedV1> message = MessageBuilder.withPayload(order)
    .setHeader("eventType", "order.placed")
    .setHeader("schemaVersion", 1)
    .setHeader("correlationId", "ord-501")
    .build();

OrderPlacedV1 payload = message.getPayload();
String eventType = (String) message.getHeaders().get("eventType");
~~~

In the example, the payload is an actual `OrderPlacedV1` object, not yet converted to JSON. Headers such as `eventType` or `schemaVersion` provide metadata so components understand the message; they **do not automatically validate** whether the schema matches the payload.

Specifically, the generic parameter `Message<OrderPlacedV1>` helps the compiler check usage where type information exists, yet **does not make every channel accept only `OrderPlacedV1`**. Most Spring Integration flows exchange `Message<?>` objects; when receiving input from an adapter, broker, or another producer, the actual payload type must be verified at runtime.

A message usually has a non-`null` payload; do not use `null` as a business event or group completion signal. Design explicit events/states, such as `OrderCancelled` or `OrderProcessingFailed`.

## 3. Common payload forms

| Payload type | Example | Suitable usage | Risks to manage |
|---|---|---|---|
| POJO, Java record | `OrderPlacedV1` | Internal business flows with known schema | Class changes can break older consumers |
| `String` | Text JSON, CSV, log lines | Receiving text data or initial parsing step | No structural or charset guarantees yet |
| `byte[]` | UTF-8 JSON bytes, files, binary protocols | Transports, adapters, files, and binary content | Must know encoding/schema; array contents can be mutated |
| `Map<String, Object>` | Flexible payload produced by a parser | Dynamic data or temporary compatibility layer | Wrong key names/value types only appear at runtime |
| `List<OrderLineTask>` | List of tasks | Step immediately preceding a Splitter | Must define what an empty list means |
| Library-generated object types | HTTP response, database row | Specialized adapters/integrations | Easily couples the contract to external libraries |

`Message<T>` is the **envelope** for payload and headers, not a distinct business payload type. Prefer **explicit and stable business types** for core processing logic. `String`, `byte[]`, or `Map` fit at data ingestion boundaries, yet every handler should not have to guess formats. A Transformer near the entry point should convert data into a type understood uniformly by downstream steps.

**Important distinction:** the payload type inside the JVM, such as `OrderPlacedV1`, differs from the *wire format* when sent over HTTP, AMQP, or Kafka, such as UTF-8 JSON. A Java record payload does not mean a broker can transmit that record directly; corresponding encoders/serializers and decoders/deserializers are required.

## 4. What layers make up a data type contract?

A good contract answers more questions than just a class name. For an `OrderPlacedV1` event, document explicitly:

| Contract layer | What to describe | Order example |
|---|---|---|
| **Identity** | Message type, originating source, purpose | `eventType=order.placed`, emitted after accepting an order |
| **Shape** | Field names, types, required fields, nullability | `orderId: String` required; `lines: List<LineItem>` |
| **Semantics** | Meaning, units, validity conditions | `quantity > 0`; `region` is market code |
| **Transformation** | Input/output types of each step | `OrderPlacedV1 → ValidatedOrder` |
| **Version** | Version and how consumers handle new versions | `schemaVersion=1`; support rules for v1/v2 |
| **Wire format** | Encoding, serializer, content type, field naming | UTF-8 JSON, `application/json` |
| **Failure contract** | Where missing fields, wrong types, or version errors go | Reject/quarantine, with error code and `eventId` |
| **Operational metadata** | Correlation, idempotency, trace, timestamps | `eventId` distinct from `orderId` |

In a Spring Integration module implementing Enterprise Integration Patterns, this contract connects the endpoints: Filter/Router need to know **which values are valid**, Transformer needs to know the **target type**, Splitter/Aggregator need to know **how to preserve group identity**, and Gateway and adapters need to know **how to marshal data in and out**.

## 5. Designing clear business payloads

Suppose we receive an order-placed event with multiple items. Java records express structural immutability at the field-reference level; however, nested collections still need copying to prevent unintended mutation.

~~~java
record LineItem(String sku, int quantity) {}

record OrderPlacedV1(
    String eventId,
    String orderId,
    int schemaVersion,
    String region,
    List<LineItem> lines
) {
    OrderPlacedV1 {
        lines = lines == null ? null : List.copyOf(lines);
    }
}

record ValidatedOrder(
    String eventId,
    String orderId,
    String region,
    List<LineItem> lines
) {
    ValidatedOrder {
        lines = List.copyOf(lines);
    }
}
~~~

`OrderPlacedV1` represents data **as received**. `ValidatedOrder` represents data **after validation and normalization**. Separating the two types prevents downstream handlers from repeatedly checking whether `region` has been trimmed. `schemaVersion` identifies the producer/consumer contract, while `eventId` identifies the event emission and supports deduplication.

If a real application handles money, use a value type like `BigDecimal` with explicit currency and scale rules; avoid passing `double` for monetary amounts. For timestamps, standardize format, timezone, and representation, such as `Instant` in Java and ISO 8601 strings in JSON.

**Useful convention:** messages notifying of an event that already happened should use past-tense names like `OrderPlaced`; messages requesting an action can use imperative names like `ReserveInventory`. Contracts for commands and events differ in reply expectations, retries, and data ownership.

## 6. Data types flowing through Gateway, Filter, Transformer, and Router

The Java DSL example below illustrates a single-application flow. Common Java/Spring/Spring Integration imports are omitted; the records from the previous section are reused here.

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
interface OrderGateway {
    void submit(OrderPlacedV1 event);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OrderTypeFlows {
    @Bean
    IntegrationFlow validateTransformRoute() {
        return IntegrationFlow.from("orders.in")
            .filter(OrderPlacedV1.class, this::isValid,
                spec -> spec.discardChannel("orders.rejected"))
            .transform(OrderPlacedV1.class,
                e -> new ValidatedOrder(
                    e.eventId(),
                    e.orderId(),
                    e.region().trim().toUpperCase(Locale.ROOT),
                    e.lines()))
            .route(ValidatedOrder.class, ValidatedOrder::region,
                spec -> spec.channelMapping("VN", "orders.vn")
                    .defaultOutputChannel("orders.other"))
            .get();
    }

    private boolean isValid(OrderPlacedV1 event) {
        return event.schemaVersion() == 1
            && event.eventId() != null && !event.eventId().isBlank()
            && event.orderId() != null && !event.orderId().isBlank()
            && event.region() != null && !event.region().isBlank()
            && event.lines() != null && !event.lines().isEmpty()
            && event.lines().stream().allMatch(line ->
                line != null && line.sku() != null
                    && !line.sku().isBlank() && line.quantity() > 0);
    }

    @Bean
    IntegrationFlow vnOrders() {
        return IntegrationFlow.from("orders.vn")
            .handle(message ->
                System.out.println("VN: " + message.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow otherOrders() {
        return IntegrationFlow.from("orders.other")
            .handle(message ->
                System.out.println("OTHER: " + message.getPayload()))
            .get();
    }

    @Bean
    IntegrationFlow rejectedOrders() {
        return IntegrationFlow.from("orders.rejected")
            .handle(message ->
                System.out.println("REJECTED: " + message.getPayload()))
            .get();
    }
}
~~~

The flow executes as follows:

~~~mermaid
flowchart LR
    G["Gateway: OrderPlacedV1"] --> F{"Filter: valid?"}
    F -->|"No"| X["orders.rejected: OrderPlacedV1"]
    F -->|"Yes"| T["Transformer: ValidatedOrder"]
    T --> R{"Router: region"}
    R -->|"VN"| V["orders.vn: ValidatedOrder"]
    R -->|"Other"| O["orders.other: ValidatedOrder"]
~~~

For example, input `region=" vn "` is valid and normalized to `"VN"`, then routed to `orders.vn`. A message rejected by Filter and sent to `orders.rejected` still carries the **original payload** `OrderPlacedV1`, since it has not passed through the Transformer. Both destination channels after the Router receive the **new payload** `ValidatedOrder`. That is why each branch must explicitly document which type the final endpoint can receive.

The snippet illustrates a Gateway with a `void` method. When the flow processes synchronously, the call may still block until handlers finish; `void` does not imply a message was durably persisted or processed asynchronously.

**Limits of type protection:** `.filter(OrderPlacedV1.class, ...)` states the type the endpoint expects; it does not automatically convert arbitrary incoming bytes/Strings into `OrderPlacedV1`. If a producer pushes another type into `orders.in`, the system may raise a conversion error or fail when invoking the handler. Validate types at ingress, configure explicit converters, and establish suitable error-handling workflows.

## 7. Transformer as a contract-changing boundary

A Transformer does not only change values; it can **change the payload type itself**:

~~~text
byte[] (JSON) --decode--> OrderPlacedV1
OrderPlacedV1 --validate/normalize--> ValidatedOrder
ValidatedOrder --split--> OrderLineTask
List<LineResult> --aggregate--> OrderSummary
OrderSummary --encode--> byte[] (JSON)
~~~

Each arrow needs its own input/output contract. A converter handles **representation** (for example `byte[]` ⇄ Java object); a business Transformer handles **semantics** (normalizing region codes, calculations, transforming domain models). Separating these two responsibilities keeps tests clear and avoids coupling business logic to transport details.

A common mistake is assuming you can turn a `String` into `OrderPlacedV1` by casting:

~~~java
Object incoming = "{\"orderId\":\"ord-501\"}";
// Wrong: incoming is a String, not OrderPlacedV1
// OrderPlacedV1 event = (OrderPlacedV1) incoming; // ClassCastException
~~~

To obtain a Java object, you must **parse** using a suitable serializer and validate the schema. For example, with Jackson:

~~~java
ObjectMapper mapper = new ObjectMapper();
OrderPlacedV1 event = mapper.readValue(jsonBytes, OrderPlacedV1.class);
// After parsing, business constraints must still be validated.
~~~

The snippet above illustrates parsing, not a complete flow. You must configure the mapper, handle exceptions, enforce message size limits, and validate data constraints according to the real system. With Spring Integration adapters, choose the appropriate converter/transformer; do not assume the library automatically infers classes from every payload.

## 8. Wire format boundary: JSON, byte[], and contentType

Suppose another service emits a JSON event:

~~~json
{
  "eventId": "evt-101",
  "orderId": "ord-501",
  "schemaVersion": 1,
  "region": "vn",
  "lines": [
    { "sku": "SKU-10", "quantity": 2 },
    { "sku": "SKU-22", "quantity": 1 }
  ]
}
~~~

If the adapter receives the payload as `byte[]`, the decode step must understand UTF-8 encoding, JSON format, schema version 1, and how to map to `OrderPlacedV1`. If the adapter already decoded it into an object, avoid decoding it a second time.

The `contentType=application/json` header describes the **wire representation**, not runtime proof that the payload is `OrderPlacedV1`. Attaching a JSON header to an in-memory POJO does not automatically serialize that POJO either. Similarly, Java class names are not a compatibility contract across services written in multiple languages.

| Boundary | Payloads you may encounter | What to do |
|---|---|---|
| HTTP inbound | JSON text/bytes or decoded POJO | Define the decode step; validate schema and size |
| AMQP inbound | bytes or POJO depending on converter | Choose content type, converter, header mapping, and retry |
| Kafka inbound | bytes/String/POJO depending on deserializer | Declare serializer/deserializer and compatibility |
| JDBC outbound | DTO/command or parameters | Map fields explicitly; verify transactions/idempotency |
| Internal message channel | POJO/record | Use stable Java contracts between endpoints |

When crossing a broker or another process, not every internal header is preserved. Configure header mappers or place **truly required** metadata into the wire contract: `eventId`, `orderId`, schema version, correlation, and trace context. Do not use Java class names or default object serialization as a long-term integration protocol when multi-version or multi-language compatibility is needed.

## 9. Versioning and safe contract evolution

Payloads evolve over time. For instance, version 2 may need currency code and shipping fee added. Changing fields or altering field semantics can cause older consumers to misprocess even if the JSON still parses.

| Change | Potential impact | Handling approach |
|---|---|---|
| Adding an optional field with a clear default | Older consumers can ignore it if configured | Verify receiver parser; document default value explicitly |
| Renaming/removing a required field | Older consumers fail to read or lose data | Create a new schema version and migration |
| Changing `quantity` from integer to string | Type mismatch or logic error | Bump version, add conversion adapter |
| Changing `region` meaning from country code to warehouse zone | Risk of severe silent bugs | Rename field or event, run a transition period |
| Adding an enum value | Older consumers may encounter an unknown value | Have an unknown/default branch and alerting |
| Changing correlation mechanism | Misgrouping or incomplete messages | Keep compatible keys, test across versions |

There is no rule that **every new field is backward compatible**. Compatibility depends on serializer behavior, unknown-field handling, schema registry (if used), default values, and business behavior. Test against a **producer v1/v2 × consumer v1/v2** matrix before rollout.

A safe strategy is **reading older versions during a transition period and emitting the new version once consumers are ready**, or using a dedicated adapter to translate v1 → a unified internal model. Decide whether version lives in the payload or metadata when designing the contract; avoid letting two version sources contradict each other.

## 10. Splitter and Aggregator must preserve both type and group identity

When transforming `ValidatedOrder` into multiple `OrderLineTask`s, input and output differ in type; at the same time, the relationship across line items must be preserved:

~~~java
record OrderLineTask(
    String orderId,
    String eventId,
    int lineIndex,
    String sku,
    int quantity
) {}

record LineResult(
    String orderId,
    int lineIndex,
    boolean reserved
) {}

record OrderSummary(
    String orderId,
    List<LineResult> results
) {}
~~~

Splitter can generate sequence headers like `correlationId`, `sequenceNumber`, and `sequenceSize`; Aggregator can use them to group and release results per its release condition. When child messages cross a broker or Transformer, inspect header mapping and how correlation is re-established.

A real-world problem needs clear definitions: **`orderId` is the business key**, **`eventId` is the event identifier**, and **`correlationId` is the message-grouping key for one processing run**. They may share values by design, yet are not synonymous by default. With two orders processed concurrently, choosing the wrong correlation will mix results together.

The `LineResult` payload indicates which line item finished; headers indicate which group or processing attempt is underway. Relying solely on `sequenceSize` is insufficient to handle duplicate messages, late messages, or a line item failing before returning a result. You need policies for **timeouts, release, expired-message handling, message stores, and deduplication**.

## 11. Type mismatch, schema violation, and business error are three distinct failure groups

Suppose an adapter receives the string `"hello"` while the flow expects `OrderPlacedV1`. This is an **input representation/type error**, not a valid order with a negative quantity. Recognize and record it at the ingress boundary.

| Scenario | Classification | Reference handling approach |
|---|---|---|
| Malformed JSON payload | Deserialize/parse error | Reject or quarantine; do not retry infinitely |
| Valid JSON but missing `orderId` | Schema/contract violation | Report error code, event ID if present; do not enter main flow |
| Message has `String` payload yet handler expects record | Type mismatch/conversion error | Check converter/adapter and appropriate error channel |
| Schema-valid record yet `quantity=-1` | Business validation | Filter → discard/rejected channel, store reason |
| New region with no branch | Routing contract | Explicit default branch, alert if needed |
| Valid data yet warehouse times out | Dependency/transient failure | Bounded retry, backoff, idempotency |
| Duplicate `eventId` | Delivery/reprocessing | Check idempotency key before executing side effects |

In Spring Integration, a **Filter's discard channel** is used for messages that fail the filter predicate. Exceptions inside handlers follow a separate path: they may propagate back to the caller in synchronous flows or reach an error channel depending on endpoint, poller, and asynchronous adapter configuration. Do not assume all errors go to the same place. Design explicit error handling and ack/retry conditions for each boundary.

With untrusted external payloads, avoid deserializing into arbitrary classes named by a client-supplied class field. Use an allowlist of permitted schemas/events, validate payload size and nesting depth, and avoid logging sensitive full contents onto the error channel.

## 12. Testing data contracts from Gateway to distributed flows

Valuable tests verify **types**, **semantics**, **branching**, **error paths**, and **compatibility**, rather than merely calling a method without throwing an exception.

| Test | Input data | What to verify |
|---|---|---|
| Happy path | `OrderPlacedV1` with `region=" vn "` | Transformer produces `ValidatedOrder` with `region="VN"` |
| Filter invalid | Quantity equals 0 or empty `lines` | Appears only on rejected branch with original payload |
| Runtime type mismatch | Producer sends `String` to record-expecting channel | Does not silently cast; produces error with diagnostic context |
| JSON parse | Malformed bytes or missing required field | Parse/schema error classified, does not reach business handler |
| Router unknown | Unsupported region | Reaches default channel or designated rejection path |
| Split/aggregate | Two `orderId`s with interleaved line results | No misgrouping; output has exact type `OrderSummary` |
| Version compatibility | Producer/consumer on different versions | Compatibility policy executes properly |
| Broker redelivery | Same `eventId` published twice | No duplicate side effects; correlation stays intact |

A unit test example for the normalization step can explicitly compare the output structure:

~~~java
OrderPlacedV1 input = new OrderPlacedV1(
    "evt-101",
    "ord-501",
    1,
    " vn ",
    List.of(new LineItem("SKU-10", 2))
);

ValidatedOrder actual = new ValidatedOrder(
    input.eventId(),
    input.orderId(),
    input.region().trim().toUpperCase(Locale.ROOT),
    input.lines()
);

assertEquals("VN", actual.region());
assertEquals("ord-501", actual.orderId());
assertEquals(2, actual.lines().get(0).quantity());
~~~

The snippet above tests the normalization logic on sample data; real integration tests must boot the flow and observe output channels/handlers. Using Spring Integration Test or Spring Boot Test, you can replace handlers or attach interceptors to record messages reaching target branches; with a broker, test serialization, header mapping, and redelivery in an integration environment.

For every test, clearly record **input type**, **output type**, **headers to preserve**, **expected branch**, and **error behavior**. This also aids per-endpoint metric tracking and correlation ID tracing across services.

## 13. Hands-on exercise: designing contracts for an order processing system

Build a flow consisting of Gateway → Filter → Transformer → Router → Splitter → Aggregator, then replace the Gateway input with an adapter receiving JSON from another process.

**Input requirements:** event `OrderPlacedV1` with `eventId`, `orderId`, `schemaVersion`, `region`, and a list of line items. Each line has `sku` and `quantity`. Specify supported versions, code length constraints, empty-list handling, payload size limits, and how unknown regions are handled.

**Processing requirements:** only valid messages are converted by the Transformer into `ValidatedOrder`; Splitter emits `OrderLineTask` items; each worker produces `LineResult`; Aggregator produces `OrderSummary` with accurate correlation. Design separate flows for parse errors, business errors, and dependency failures.

**Distributed deployment requirements:** encode as UTF-8 JSON; publish schema to consumers; preserve `eventId` and `orderId` across adapters; simulate message redelivery and worker restart. Test an older consumer receiving a new-version event under the chosen compatibility policy.

**Completion criteria:**

1. Contract table for each channel, specifying input/output payload types and headers to preserve.
2. Tests for valid data, missing fields, wrong types, unknown regions, and incompatible versions.
3. Test for two orders splitting/aggregating interleaved without mixing groups.
4. Description of JSON parsing, codec configuration, and routing parse errors to an appropriate handling channel.
5. Logs/traces or metrics showing which branches an `eventId` traversed and what outcome it received.
6. Evidence that redelivery does not trigger unintended duplicate business actions.

## 14. Takeaways when choosing payloads and designing contracts

**Java types, data schemas, and wire formats are three separate layers:** `Message<T>` expresses types in code; the schema defines which values are valid; the serializer moves data across process boundaries. They must be designed cohesively, yet do not substitute for one another.

**Transformers publish target types; Routers/Filters know the types they handle; Splitters/Aggregators preserve correlation keys.** Each step should have a small, clear contract so transports can be swapped or components split into separate services while remaining testable.

**Contracts do not stop at the happy path.** You need versioning, unknown-field rules, error codes, deduplication identifiers, correlation information, and tests covering all processing branches. That is the foundation for building loosely coupled, extensible, and reliable message flows with Spring Integration.
