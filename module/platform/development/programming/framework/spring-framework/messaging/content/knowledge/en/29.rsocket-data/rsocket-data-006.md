# Distinguishing Data and Metadata MIME Types in RSocket

RSocket splits a `Payload` into two independent parts: **data** and **metadata**. Both are binary data (`ByteBuf`/buffers), but they serve two different purposes and can be encoded in two different formats. MIME types tell the receiver which format to use when interpreting those bytes.

Key point: `dataMimeType` describes the data portion; `metadataMimeType` describes how the metadata portion is packaged. If using Composite Metadata, each metadata entry inside also has its own MIME type.

## 1. How do data and metadata differ?

| Criterion | Data | Metadata |
| --- | --- | --- |
| Role | Primary business content of the message: request objects, returned data, events... | Descriptive or control information for the message: route, authentication, tenant, tracing, correlation id... |
| Location in Payload | Data region | Separate metadata region |
| Connection-level MIME type | `dataMimeType` in `SETUP` | `metadataMimeType` in `SETUP` |
| Format examples | `application/json`, `application/cbor`, `application/octet-stream`, `text/plain` | `message/x.rsocket.composite-metadata.v0` or a single metadata format like `application/vnd.acme.metadata+json` |
| How to send in Spring | `.data(value)` | `.route(...)` and `.metadata(value, entryMimeType)` |

Example: when looking up an order, `OrderQuery` is data; the route `orders.find` and tenant information are metadata. The data part answers "what content is being sent?", while metadata answers "which request does this content belong to, and in what context should it be routed or processed?".

```text
SETUP (once per connection)
├── data MIME type: application/json
└── metadata MIME type: message/x.rsocket.composite-metadata.v0

REQUEST_RESPONSE / REQUEST_STREAM / REQUEST_CHANNEL / REQUEST_FNF
└── Payload
    ├── Metadata
    │   ├── route: message/x.rsocket.routing.v0
    │   ├── authentication: message/x.rsocket.authentication.bearer.v0
    │   └── tenant: application/vnd.acme.tenant+json
    └── Data: JSON bytes of the business object
```

In a frame carrying both data and metadata, metadata precedes data and has its own length field. The Java API `io.rsocket.Payload` also provides separate access to `data()` and `metadata()`. Metadata may be absent; data may also be empty depending on the frame type and request.

## 2. Where are MIME types declared?

When establishing a connection, the initiator sends a `SETUP` frame. This frame separately declares the format of data and metadata. These two MIME types are connection-level settings and apply to messages on that connection; they are not independent per-request MIME type selections.

- `dataMimeType`: format of the data region. For example, `application/json` means both sides agree to interpret data as JSON.
- `metadataMimeType`: outer wrapper format of the metadata region. If using Composite Metadata, the value is `message/x.rsocket.composite-metadata.v0`.

RSocket refers to these values as MIME types, though the protocol layer does not parse JSON, CBOR, or application schemas itself. It forwards bytes and format information; the application or framework must provide matching encoders/decoders. Both ends of the connection must agree on MIME types and support the corresponding encoding.

Because the data MIME type is declared at the connection level, do not assume you can send JSON in one request and CBOR in another over the same connection simply by changing a parameter of `.data()`. If multiple content types are needed, standardize on a single shared format or use an envelope with a discriminator; when different connection-level MIME types are needed, open separate connections.

## 3. Understanding the two layers of metadata MIME types

This is the easiest part to misunderstand. When using Composite Metadata, there are two layers:

1. **Metadata container MIME type**: declared in `SETUP` via `metadataMimeType`. For Composite Metadata, use `message/x.rsocket.composite-metadata.v0`.
2. **Individual metadata entry MIME type**: lives inside the container. Each entry has its own type and content, so a single `Payload` can carry multiple entries in different formats.

Examples of common entries:

| Entry | MIME type | Meaning |
| --- | --- | --- |
| Routing | `message/x.rsocket.routing.v0` | Route name for selecting the handler |
| Bearer authentication | `message/x.rsocket.authentication.bearer.v0` | Bearer token authentication credentials |
| Application metadata | `application/vnd.acme.tenant+json` | Application-defined tenant data, JSON-encoded |
| Tracing | Tracing MIME type per extension or system convention | Trace context for request observability |

In Spring, `RSocketRequester.Builder.metadataMimeType(...)` sets the container's MIME type. Meanwhile, `RequestSpec.metadata(value, mimeType)` sets the MIME type for **a single entry** added by that request. These two parameters are not interchangeable.

Composite Metadata is useful when a single request needs routing, authentication, and tracing together. If a single metadata MIME type is chosen, the entire metadata region is interpreted under that format; there is no container mechanism to automatically separate multiple independent entries. With a non-Composite Metadata configuration, Spring also assumes the route (if any) is encoded according to the configured metadata MIME type.

## 4. Configuration in Spring Framework

Spring provides `RSocketRequester` to construct requests at the object level, and `RSocketStrategies` to select encoders/decoders for data and metadata.

- Basic codecs from `spring-core` support `String`, `byte[]`, and `ByteBuffer`.
- Add `spring-web` to use codecs such as Jackson JSON/CBOR or Protobuf.
- If `dataMimeType` is not specified, Spring infers the default from the first configured decoder (preferring a non-default decoder if present). Therefore, when integrating across languages or multiple applications, configure it explicitly to avoid depending on codec order.
- The default `metadataMimeType` of `RSocketRequester.Builder` is Composite Metadata. Usually there is no need to change this value.

### 4.1. Configuring a client using JSON for data and Composite Metadata

The snippet below illustrates the Spring Framework 6.2 API with Jackson 2. The encoder/decoder classes require `spring-web` and the corresponding Jackson dependencies.

```java
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;

MimeType json = MimeType.valueOf("application/json");
MimeType composite = MimeType.valueOf(
        "message/x.rsocket.composite-metadata.v0");

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .build();

RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(json)
        .metadataMimeType(composite)
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
```

Here, `application/json` applies to data on the connection; `message/x.rsocket.composite-metadata.v0` applies to the metadata container. Codecs are responsible for converting objects to bytes and vice versa. Declaring a MIME type without registering the corresponding codec will not magically provide serialization/deserialization.

With Spring Framework 7 and Jackson 3, use `JacksonJsonEncoder` and `JacksonJsonDecoder` instead of the `Jackson2...` classes in the example. Always choose classes matching the actual Spring and Jackson versions of your project.

### 4.2. Sending data and metadata in the same request

```java
import org.springframework.util.MimeType;

MimeType tenantMime = MimeType.valueOf(
        "application/vnd.acme.tenant+json");

Mono<OrderView> response = requester.route("orders.find")
        .metadata(new TenantContext("tenant-42"), tenantMime)
        .data(new OrderQuery("ORD-42"))
        .retrieveMono(OrderView.class);
```

This is an illustrative snippet assuming the application has declared `TenantContext`, `OrderQuery`, `OrderView`, and configured the JSON codec. `route("orders.find")` creates routing metadata; `.metadata(...)` adds a tenant entry with its own MIME type; `.data(...)` sends the business object using the connection's `dataMimeType`.

### 4.3. Decoding custom metadata on the receiving side

`RSocketMessageHandler` supports Composite Metadata and routing metadata by default. Routing metadata is decoded into a value keyed by `route`. For custom MIME types, you need a decoder and an extraction registration via `MetadataExtractorRegistry`.

```java
MimeType tenantMime = MimeType.valueOf(
        "application/vnd.acme.tenant+json");

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                        tenantMime, TenantContext.class, "tenant"))
        .build();
```

When configuring `RSocketMessageHandler`, pass this `RSocketStrategies` to the handler so the decoder and metadata extractor are used on the responder side. The handler can then receive the extracted value as a header:

```java
@MessageMapping("orders.find")
Mono<OrderView> find(
        @Payload OrderQuery query,
        @Header("tenant") TenantContext tenant) {
    // Process query in the authenticated tenant context.
    return orderService.find(query, tenant);
}
```

`@Header("tenant")` works only when the metadata entry has been decoded and mapped to key `tenant`. Without registering the extractor, sending the entry does not mean Spring automatically turns it into a header.

## 5. When should information go into data vs. metadata?

- Put it in **data** when it is business content the handler needs to process: commands, queries, DTOs, events, return results, or file contents.
- Put it in **metadata** when it is context or directives accompanying the message: route, token, tenant, trace ID, correlation ID, protocol version, or control info.
- Use **Composite Metadata** when a request needs multiple independent metadata groups, each potentially using its own MIME type.
- Use **a single custom metadata document** when both ends agree on a single schema and do not need to combine independent entries. In that case, a matching decoder and extraction logic are required.
- Keep metadata schemas stable, name custom MIME types clearly, and manage versions when structures change.

Do not move entire business DTOs into metadata simply because metadata supports multiple MIME types. Core content should stay in data so handlers have a clear payload; metadata should remain auxiliary.

## 6. Common errors and checks

| Symptom or error | Common cause | Resolution |
| --- | --- | --- |
| JSON decoding error or wrong object type received | Both ends declare different data MIME types, or missing JSON encoder/decoder | Check connection `dataMimeType` and JSON codecs on both sides |
| Route not found | Metadata container is not Composite Metadata as receiver expects, or routing entry is malformed | Check `metadataMimeType` and `message/x.rsocket.routing.v0` entry |
| Custom metadata missing in `@Header` | MIME type not registered with `metadataExtractorRegistry`, or missing matching decoder | Register `metadataToExtract(mimeType, Target.class, "headerName")` and configure decoder |
| Multiple metadata entries not decoded | Using a single metadata MIME type instead of Composite Metadata | Use `message/x.rsocket.composite-metadata.v0` on both ends |
| Client and server read the same bytes differently | MIME type is just a label; codecs or schemas between sides do not match | Align MIME type, schema, and serializer version |

Debugging checklist:

1. Verify the connection's `dataMimeType` and `metadataMimeType`; the server side can inspect these values from `SETUP` information.
2. Check whether `dataMimeType` matches the sent/received objects and registered encoders/decoders.
3. If using Composite Metadata, verify the container MIME type is `message/x.rsocket.composite-metadata.v0` and each entry has the right MIME type.
4. Verify the route is sent as routing metadata; in Spring, `.route(...)` puts the route in metadata, not in data.
5. For custom metadata, check the decoder, `metadataExtractorRegistry`, and mapped key name before using `@Header`.
6. When inspecting at the protocol layer, check the bytes of `Payload.data()` and `Payload.metadata()` separately; do not decode both with the same codec if their MIME types differ.

Metadata may contain tokens or identity information. Use an appropriate secure transport (such as TLS when deploying over untrusted networks), avoid logging raw tokens, and enforce authentication/authorization on the receiving side. Placing a token in metadata does not by itself protect the token.

## 7. Key takeaways

- `dataMimeType` = format of the data content.
- `metadataMimeType` = format of the metadata region at the connection level.
- With Composite Metadata, each entry also has its own MIME type; this is the MIME type passed to `.metadata(value, mimeType)`.
- MIME types do not replace encoders/decoders and do not automatically convert data.
- Spring defaults to Composite Metadata and supports routing; custom metadata requires a decoder and extraction configuration.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework 6.2 API — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Spring Framework 6.2 API — MetadataExtractorRegistry](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractorRegistry.html)
- [RSocket Protocol — Data and Metadata, SETUP](https://rsocket.io/about/protocol/)
- [RSocket Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)