# Routing Metadata and Route Naming Conventions

> Scope: RSocket data in Spring Framework, focusing on how the requester sends routes in metadata, how the responder matches routes, and how to name routes consistently.

## 1. Objectives

After this lesson, you will be able to:

- Distinguish between the route, data payload, and metadata of an RSocket request.
- Explain the `message/x.rsocket.routing.v0` MIME type and its protocol-level tag structure.
- Create requests with `RSocketRequester.route(...)` and map requests with `@MessageMapping`.
- Choose an appropriate route matcher and understand the dot as the default hierarchical separator in Spring RSocket.
- Name routes consistently, extensibly, and in a way that is easy to observe in logs, metrics, and traces.

## 2. Where does the route live in an RSocket message?

RSocket separates **data** and **metadata** within a payload. Data typically carries the business payload to be processed, while metadata carries control information or request descriptors such as the route, authentication credentials, tracing, or correlation IDs.

For example, a product lookup request can be understood as follows:

| Component | Example Value | Role |
| --- | --- | --- |
| Route metadata | `inventory.item.find.{sku}` with `sku = SKU-42` | Selects the handler that will receive the request |
| Data payload | `FindItemRequest` or no payload | Business data of the request |
| Other metadata | token, tenant, trace id | Additional context for the request |

A route is the logical address of a handler inside the application. A route is not an HTTP URL and does not contain host, port, or transport details. RSocket can run over TCP or WebSocket; the same route can be used across different transports.

An RSocket connection starts with a `SETUP` frame. This frame declares the MIME types used for data and metadata on the connection. When the requester initiates an interaction, the route is usually sent in the metadata of the request-initiating frame: `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, or `REQUEST_FNF`. For `REQUEST_CHANNEL`, the route is in the stream-initiating frame; subsequent payloads belong to the same stream.

RSocket supports four main interaction models:

| Model | Meaning | Usage Example |
| --- | --- | --- |
| Request-Response | One request, one response | Find a product |
| Request-Stream | One request, multiple responses | Stream prices or status updates |
| Request-Channel | Both sides exchange streams | Bidirectional data synchronization |
| Fire-and-Forget | One-way send, no business response expected | Send telemetry events |

The route determines the handler. The interaction model is determined by the RSocket frame and the input/output shapes used by the requester and handler; merely renaming a route does not turn a request-response into a request-stream.

## 3. Routing metadata at the protocol level

RSocket defines the Routing Metadata Extension with the MIME type:

```text
message/x.rsocket.routing.v0
```

The extension is currently marked as incubating at version `0`. This means the structure is documented so implementations can interoperate, though applications still need to verify compatibility with the libraries and peers in use.

Routing metadata contains one or more tags. Each tag consists of:

1. A one-byte `Tag Length`: the byte count of the tag as an 8-bit unsigned integer.
2. The `Tag` body: a UTF-8 string with the exact number of declared bytes.

Because the length is represented in 8 bits, a single tag can be at most 255 UTF-8 bytes. Tags are not NUL-terminated. The limit is measured in bytes after UTF-8 encoding, not in visible characters.

The extension allows multiple tags in a single metadata payload. The responder may use one tag, multiple tags, or ignore tags depending on application logic. Valid protocol-level examples include `/person/1`, `person.1`, `ios-client`, or `android-client`; the protocol does not enforce a single naming convention.

In Spring, `RSocketRequester.route(...)` provides the application-level API to build a route for a request. This API takes a route string and optional route variables. When the connection uses composite metadata, Spring encodes the route using the routing MIME type above.

## 4. Composite metadata and Spring Framework

Composite metadata allows a single metadata payload to contain multiple independent entries, each with its own MIME type. As a result, a single request can carry a route, an authentication token, and tracing metadata without mixing them into an unstructured string.

Spring Framework supports composite metadata as the default for `RSocketRequester.Builder`. `RSocketMessageHandler` supports both composite metadata and routing metadata. Thus, in a standard Spring configuration, an application can send the route and other metadata entries in the same request.

Example of adding authentication metadata when sending a request:

```java
String token = obtainAccessToken();
MimeType authMimeType = MimeType.valueOf(
        "message/x.rsocket.authentication.bearer.v0");

Mono<Item> item = requester.route("inventory.item.find.{sku}", "SKU-42")
        .metadata(token, authMimeType)
        .retrieveMono(Item.class);
```

The snippet above assumes the corresponding encoder and metadata configuration are registered in `RSocketStrategies`. The metadata MIME type must be understood the same way by both sides. Never send secret tokens inside the route because routes often appear in logs, traces, or metrics.

`DefaultMetadataExtractor` supports routing metadata out of the box. It decodes the route into a `String` and places the value under the `route` key in the metadata map. Other MIME types require a corresponding decoder and registration with the extractor, for example:

```java
DefaultMetadataExtractor extractor =
        new DefaultMetadataExtractor(metadataDecoders);

extractor.metadataToExtract(fooMimeType, Foo.class, "foo");
```

Once extracted, metadata can be accessed like headers in annotated handlers, such as with `@Header` or `@Headers Map<String, Object>`. Registering a decoder only handles decoding; the application must still validate values and enforce appropriate security policies.

## 5. Sending and receiving routes with Spring

### 5.1. Sending requests with RSocketRequester

`RSocketRequester` is a fluent API for building a request, attaching the route, data, and metadata, and declaring the expected response type. Example:

```java
Mono<Item> item = requester
        .route("inventory.item.find.{sku}", "SKU-42")
        .retrieveMono(Item.class);
```

`route(...)` initiates a request with the target route. `retrieveMono(...)` declares that the caller expects a single value of type `Item`. To send data, add `.data(requestObject)` before `retrieveMono(...)`. To expect multiple values, use `retrieveFlux(...)`.

A route can be a template with placeholders. Variables passed to `route(...)` are formatted using `toString()` and substituted into the placeholders. If a variable value contains a dot `.`, Spring replaces that dot with `%2E` so it is not mistaken for a route separator. Pass raw values and let `RSocketRequester` handle escaping; avoid pre-encoding manually and accidentally double-encoding.

### 5.2. Mapping routes with @MessageMapping

The responder can declare handlers with `@MessageMapping`. The following example uses a Java 17 record and Reactor `Mono`:

```java
record Item(String sku, String name) {}

@Controller
class InventoryResponder {

    @MessageMapping("inventory.item.find.{sku}")
    Mono<Item> find(@DestinationVariable String sku) {
        return Mono.just(new Item(sku, "Demo item"));
    }
}
```

When the client sends route `inventory.item.find.SKU-42`, Spring can match the pattern `inventory.item.find.{sku}` and bind the variable portion to the `sku` parameter via `@DestinationVariable`. This example illustrates the handler; a real application must register the responder with `RSocketMessageHandler` and provide the required beans, codecs, and transport.

In Spring RSocket, `@MessageMapping` supports one or more route patterns. Common parameters include:

- `@Payload`: the data payload of the request; can be an object, `Mono`, or `Flux` depending on the interaction model.
- `@DestinationVariable`: a value extracted from a placeholder in the route pattern.
- `@Header`: a metadata value decoded and registered by `MetadataExtractor`.
- `@Headers Map<String, Object>`: all extracted metadata values.
- `RSocketRequester`: the requester bound to the current connection for sending requests back to the other side.

### 5.3. Choosing a route matcher

By default, `RSocketMessageHandler` uses `SimpleRouteMatcher`, which is based on `AntPathMatcher`. Spring recommends using `PathPatternRouteMatcher` from the `spring-web` module for more efficient route matching.

Illustrative configuration:

```java
@Bean
RSocketMessageHandler rSocketMessageHandler() {
    RSocketMessageHandler handler = new RSocketMessageHandler();
    handler.routeMatcher(new PathPatternRouteMatcher());
    return handler;
}
```

Both matchers are configured by default with the dot `.` as the separator. Therefore, hierarchical routes like `inventory.item.find` fit Spring's defaults well. RSocket routes can be hierarchical, but they are not URL paths: Spring does not automatically perform URL decoding as it does when handling HTTP URLs.

If a system chooses to use `/` as a convention, explicitly define the route matcher and encoding/decoding rules on both sides. Do not assume that `/items/42` will automatically share the same pattern semantics as an HTTP endpoint.

### 5.4. @RSocketExchange and @ConnectMapping

`@RSocketExchange` is an alternative for declaring an RSocket service via a Java interface. Method-level routes must be concrete routes; an annotation at the interface level can declare a shared prefix. This fits well when sharing a contract between a requester proxy and a responder.

`@ConnectMapping` is intended for connection-level events: `SETUP` frames when a connection starts and metadata notifications via `METADATA_PUSH`. It does not replace `@MessageMapping` for regular individual requests. `@ConnectMapping` returns no data and methods must have a return type of `void` or `Mono<Void>`.

## 6. Route naming conventions

RSocket does not require applications to follow a single route naming pattern. It is an application convention, so it should be agreed upon across requesters, responders, API documentation, logs, and tests.

### 6.1. Recommended pattern

With Spring's default matcher, prefer dot-separated hierarchical routes:

```text
<domain>.<resource>.<action>
<domain>.<resource>.<action>.{variable}
```

Examples:

| Route | Meaning |
| --- | --- |
| `inventory.item.find.{sku}` | Find an item by SKU |
| `inventory.item.create` | Create an item |
| `inventory.item.reserve` | Reserve an item |
| `inventory.stock.watch.{warehouseId}` | Watch inventory stock of a warehouse |
| `billing.invoice.get.{invoiceId}` | Retrieve an invoice by ID |
| `identity.session.revoke` | Revoke a session |

Each segment should have a clear role. The domain prefix prevents naming collisions when an application has multiple functional areas; the resource identifies the business object; the action describes the operation.

### 6.2. Practical rules

1. Use lowercase and a consistent character set, typically ASCII letters, digits, and hierarchical dots. Simple conventions reduce discrepancies across languages and systems.
2. Pick one form for resources, such as singular nouns `item`, `invoice`, `session`, and apply it uniformly.
3. Use specific verbs for actions like `find`, `create`, `reserve`, `watch`, `revoke`. Avoid generic names such as `process`, `handle`, or `do` when they fail to convey business meaning.
4. Keep routes stable according to the contract. Changes to internal class or package structures should not force clients to change routes.
5. Put IDs and variable values in placeholders rather than concatenating them into static route names. For instance, use `inventory.item.find.{sku}` instead of creating a separate route per SKU.
6. Do not arbitrarily mix dots and slashes within the same namespace. Choose one convention and configure the matcher accordingly.
7. Do not place tokens, passwords, personal data, or long business payloads inside routes. Use separate metadata for context and data payloads for business content.
8. Include a version in the route only when parallel incompatible contracts must be maintained, e.g. `billing.v2.invoice.get`. Do not bump the version merely for internal refactoring.
9. Keep route cardinality low and stable so logs, metrics, and traces can group by route pattern. Do not create a new static route for each user or record.
10. Document the route, payload types, RSocket interaction model, and additional metadata in the contract specification.

These are recommended design conventions, not mandatory requirements of the RSocket protocol. What is mandatory is that both sides agree on the actual route, metadata format, and how routes are interpreted.

### 6.3. Route patterns and variables

Keep the fixed part of the route to express the operation, while placing varying values in placeholders:

```text
inventory.item.find.{sku}
inventory.warehouse.stock.{warehouseId}
billing.invoice.get.{invoiceId}
```

With route `inventory.item.find.{sku}`, the route pattern indicates the handler needs to find an item; the `sku` value is simply an identifying parameter. This separation allows multiple requests to pass through the same handler pattern and reduces the number of routes to manage.

The dot is the default separator in Spring RSocket. Hence, a route variable containing a dot must be escaped following `RSocketRequester` rules. If constructing routing payloads at a low level with RSocket Java, ensure tag strings and escaping remain consistent with the responder's matcher.

## 7. Complete request flow example

Suppose the Inventory service provides an item lookup operation. Client and server agree on the contract:

- Route: `inventory.item.find.{sku}`
- Route variable: `sku`
- Request payload: optional in this example
- Response: a single `Item`
- Interaction: Request-Response

Handler:

```java
record Item(String sku, String name) {}

@Controller
class InventoryResponder {

    @MessageMapping("inventory.item.find.{sku}")
    Mono<Item> find(@DestinationVariable String sku) {
        return Mono.just(new Item(sku, "Demo item"));
    }
}
```

Requester:

```java
Mono<Item> result = requester
        .route("inventory.item.find.{sku}", "SKU-42")
        .retrieveMono(Item.class);
```

When the request is executed, Spring creates routing metadata for the expanded route. The responder decodes the metadata, extracts the route, finds the matching mapping, binds `SKU-42` to `sku`, invokes the handler, and encodes the result as the response payload. `Mono<Item>` represents a single response; if the handler returned `Flux<Item>`, the contract would be a streaming response.

To send a business payload, add `.data(request)` on the requester and receive the corresponding payload with `@Payload` in the handler. Do not stuff JSON objects into the route; the route should only route to the handler.

## 8. Common errors and diagnosis

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| Handler not found | Client route and `@MessageMapping` do not match | Compare the route after variable expansion against the mapping pattern |
| Route split into wrong segments | Dots in variables or inconsistent separator convention | Check the matcher and how `RSocketRequester` escapes variables |
| Metadata cannot be decoded | Mismatched metadata MIME type or format | Check `metadataMimeType` in `SETUP` and the metadata extractor configuration |
| Custom metadata missing in handler | Missing decoder registration or `metadataToExtract` | Check `RSocketStrategies` and `MetadataExtractor` |
| Route works in one client but not another | Endpoints use different conventions or metadata MIME types | Check route contract, MIME type, and library versions |
| Using `METADATA_PUSH` expecting a request handler to run | Confusing connection-level metadata with request metadata | Use `@ConnectMapping` for metadata push; use `@MessageMapping` for requests |
| Metrics produce too many series | Embedding IDs or dynamic values into static route names | Use stable route patterns and record IDs in separate fields |

Practical debugging workflow:

1. Confirm the connection completed `SETUP` and both sides agree on data/metadata MIME types.
2. Identify whether the request-initiating frame is `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, or `REQUEST_FNF`.
3. Verify the metadata of the initiating frame contains a routing entry with MIME type `message/x.rsocket.routing.v0`.
4. Inspect the route after variables have been expanded; compare it directly against `@MessageMapping` or the route declared in `@RSocketExchange`.
5. Check the separator and route matcher on the responder.
6. If other metadata is present, verify the MIME type, encoder, decoder, and registration in `MetadataExtractor`.
7. Check logs/traces without logging tokens or sensitive data.

## 9. Route design checklist

- [ ] Route has a clear domain or namespace prefix.
- [ ] Segments follow a single lowercase and separator convention.
- [ ] Route name describes a specific resource and action.
- [ ] Dynamic values are declared using placeholders and route variables.
- [ ] Requester and responder use the same route pattern.
- [ ] Spring's matcher is configured with the appropriate separator.
- [ ] Metadata MIME type and composite metadata are supported by both sides.
- [ ] Custom metadata has the required encoder, decoder, and registration.
- [ ] Route does not contain tokens or business payloads.
- [ ] Integration tests cover the route, route variables, and corresponding interaction model.

## 10. References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketRequester`, annotated responders, route matcher, `MetadataExtractor`, and RSocket Interface.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html): `route(String, Object...)` contract, template variables, and dot escaping rules.
- [RSocket Routing Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Routing.md): MIME type, tag encoding, and tag length limit.
- [RSocket Protocol](https://github.com/rsocket/rsocket/blob/master/Protocol.md): SETUP, request frames, payload data, and metadata.

When implementing, consult the documentation for the exact versions of Spring Framework and RSocket Java used by your application; the examples above describe current Spring APIs and application-level route conventions.
