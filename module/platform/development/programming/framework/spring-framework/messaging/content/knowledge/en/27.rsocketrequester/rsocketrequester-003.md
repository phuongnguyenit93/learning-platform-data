# dataMimeType, metadataMimeType, and Data Negotiation

## Objectives

After this lesson, you can:

- Distinguish the Data and Metadata sections of an RSocket payload.
- Explain the roles of `dataMimeType` and `metadataMimeType`.
- Understand where the two MIME types are declared, what scope they apply to, and how Spring selects defaults.
- Configure Encoders, Decoders, and `RSocketStrategies` so both sides exchange data in the same format.
- Send additional metadata, register custom metadata decoding, and receive that value on the responder.

## 1. Data and Metadata Are Two Distinct Parts of a Payload

An RSocket payload can contain two independent parts:

| Part | What is it for? | Examples |
|---|---|---|
| Data | Business content that the request or response needs to transmit | `OrderQuery`, `OrderView`, strings, byte arrays |
| Metadata | Information describing or controlling how the message is processed | route, tenant, authentication token, tracing context |

For example, when calling `orders.find`:

- Data might be `{"orderId":"ORD-100"}`.
- Metadata might contain the route `orders.find` and the tenant `tenant-42`.

Data and Metadata can use different formats. Therefore, RSocket declares a separate MIME type for each part.

A MIME type is a label describing the data format or structure, for example:

- `application/json`: JSON data.
- `application/cbor`: CBOR data.
- `application/octet-stream`: binary data.
- `message/x.rsocket.composite-metadata.v0`: RSocket composite metadata.
- `message/x.rsocket.routing.v0`: metadata containing a route according to the RSocket Routing extension.

The RSocket protocol does not automatically convert JSON to CBOR or interpret business structures. Encoding and decoding belong to the application and the codecs it registers.

## 2. dataMimeType: Format of the Data Part

`dataMimeType` specifies the MIME type used to encode the Data portion on an RSocket connection.

In Spring, this setting is on `RSocketRequester.Builder`:

```java
RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
        .tcp("localhost", 7000);
```

When setting `application/json`, both sides must have matching Encoders and Decoders to convert between Java objects and JSON bytes.

Key points to remember:

1. The MIME type is sent in the `SETUP` frame when establishing the connection.
2. This MIME type applies to Data for requests on that connection, not as a separate choice for each `route(...)` call.
3. The MIME type does not automatically create codecs. If you choose JSON without a matching JSON Encoder/Decoder, writing or reading objects will fail.
4. If not explicitly set, Spring takes the MIME type from the first configured non-default Decoder; if none exists, it takes it from the first Decoder. Thus the default depends on the actual codec list, and you should not assume every application defaults to JSON.

It is good practice to set the MIME type explicitly when connecting with another system, especially when the two sides use different libraries or codec configurations.

## 3. metadataMimeType: Outer Format of the Metadata Part

`metadataMimeType` specifies how the Metadata portion of a payload is encoded on the connection.

Spring Framework defaults to:

`message/x.rsocket.composite-metadata.v0`

This is the Composite Metadata format. It allows a single Metadata section to contain multiple independent entries; each entry has its own MIME type and content. This fits well when a request needs a route, authentication details, tenant, or tracing simultaneously.

For example, a request might have:

| Metadata entry | MIME type | Meaning |
|---|---|---|
| Route | `message/x.rsocket.routing.v0` | Selects the `orders.find` handler |
| Tenant | `text/plain` | Tenant identifier |
| Authentication | `message/x.rsocket.authentication.bearer.v0` | Bearer token |

Therefore, two concepts should be distinguished:

- `metadataMimeType`: the outer format of the entire Metadata region on the connection.
- The MIME type passed to `metadata(value, mimeType)`: the format of an individual entry inside Composite Metadata.

When using Composite Metadata, Spring can combine a route with multiple different metadata entries. If you change `metadataMimeType` to another single MIME type, Spring treats that MIME type as the format of the route if the request has a route. In that case, there is no longer a composite mechanism to combine multiple independent entries. Only change this default when a partner system requires a specific single metadata format and both sides have agreed on how to decode it.

## 4. MIME Type Negotiation Happens at the Connection Level

In RSocket, agreeing on the Data and Metadata formats is tied to connection establishment:

1. The client opens a transport such as TCP or WebSocket.
2. The client sends a `SETUP` frame. This frame declares the MIME types for Data and Metadata, along with other connection setup parameters.
3. The server processes `SETUP`. The server can accept the connection or reject the setup if it cannot work with the requested configuration.
4. Once the connection is established, both sides exchange requests and responses using the declared MIME types.

Thus, the word "negotiation" here should be understood as both sides agreeing on a format contract at the connection level. This is not HTTP content negotiation:

- There is no new `Accept` choice per RSocket request.
- RSocket does not automatically pick the best codec based on the Java class.
- A single connection does not switch `dataMimeType` between messages.
- Both sides must have codecs compatible with the agreed MIME types.

If you need to exchange multiple different Data formats, design an explicit contract: use connections with matching MIME type configurations or use a business envelope with a format discriminator field. Do not expect `dataMimeType` to change automatically per message.

## 5. Encoder, Decoder, and RSocketStrategies

A MIME type only describes the format. Encoders and Decoders perform the actual data conversion:

- Encoder: Java object → DataBuffer/bytes for sending.
- Decoder: DataBuffer/bytes → Java object when receiving.

Spring groups these components in `RSocketStrategies`. `RSocketRequester.Builder` uses strategies to encode Data and Metadata and decode responses.

Basic codecs from `spring-core` support `String`, `byte[]`, and `ByteBuffer`. When you need JSON, CBOR, or Protobuf, add the corresponding codecs; Jackson's JSON/CBOR implementations are in `spring-web`.

Example JSON configuration for a Spring Framework 6.1 application:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeTypeUtils;

@Configuration
class RSocketClientConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
                .build();
    }

    @Bean
    RSocketRequester rsocketRequester(RSocketStrategies strategies) {
        return RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
                .metadataMimeType(MimeTypeUtils.parseMimeType(
                        "message/x.rsocket.composite-metadata.v0"))
                .tcp("localhost", 7000);
    }
}
```

This is a bean configuration used inside a Spring application, not a standalone program run only with `javac`. Compatible dependencies for Spring Messaging, Spring Web with Jackson, and the RSocket transport are required. The responder side also needs compatible Encoder/Decoder configuration; if in the same application, a single `RSocketStrategies` bean can be reused.

In the example, `dataMimeType` is explicitly set to JSON. `metadataMimeType` is explicitly set to Composite Metadata even though it is also Spring's default, in order to make the connection contract explicit. Creating the `RSocketRequester` does not necessarily open the connection immediately; the shared connection is established when an actual request runs.

## 6. Sending Data and Multiple Metadata Entries in One Request

Suppose the client needs to find an order by ID and also send a tenant:

```java
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

record OrderQuery(String orderId) {}
record OrderView(String orderId, String status) {}

Mono<OrderView> result = requester.route("orders.find")
        .metadata("tenant-42", MimeTypeUtils.TEXT_PLAIN)
        .data(new OrderQuery("ORD-100"))
        .retrieveMono(OrderView.class);
```

In the code snippet:

- `route("orders.find")` creates routing metadata so the responder finds the right handler.
- `metadata("tenant-42", MimeTypeUtils.TEXT_PLAIN)` adds a metadata entry with MIME type `text/plain`.
- `data(new OrderQuery(...))` sends the business object. With the configuration from the previous section, this object is encoded as JSON.
- `retrieveMono(OrderView.class)` declares the expected response type and returns `Mono<OrderView>`.

This call works because the default metadata is Composite Metadata. The tenant value is a separate metadata entry, not mixed into the `OrderQuery` object.

## 7. Decoding Metadata on the Responder

The responder needs to know which MIME type to read and what name will be assigned to the decoded value. Spring provides `MetadataExtractorRegistry` via `RSocketStrategies.Builder`.

Example registering `text/plain` metadata as header `tenantId`:

```java
RSocketStrategies serverStrategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new Jackson2JsonEncoder()))
        .decoders(decoders -> decoders.add(new Jackson2JsonDecoder()))
        .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                        MimeTypeUtils.TEXT_PLAIN,
                        String.class,
                        "tenantId"))
        .build();

RSocketMessageHandler handler = new RSocketMessageHandler();
handler.setRSocketStrategies(serverStrategies);
```

When using these strategies for the responder, Spring still supports default routing while also knowing how to decode tenant metadata. A handler can receive the value via `@Header`:

```java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import reactor.core.publisher.Mono;

@MessageMapping("orders.find")
Mono<OrderView> find(
        @Payload OrderQuery query,
        @Header("tenantId") String tenantId) {

    return Mono.just(new OrderView(query.orderId(), "ACCEPTED"));
}
```

This illustrates the handler; in a real application, the result usually comes from a service or repository. If metadata uses a custom MIME type, a Decoder supporting that MIME type is required and must be registered with `metadataToExtract(...)`. Sending metadata from the client alone is not enough for the responder to automatically know how to turn bytes into a Java value.

## 8. When to Keep Defaults vs. When to Change Them

| Scenario | How to configure |
|---|---|
| Both sides use JSON for business objects | Set `dataMimeType(application/json)` and register Jackson JSON Encoder/Decoder on both sides |
| Need route together with token, tenant, or tracing | Keep `message/x.rsocket.composite-metadata.v0` |
| Only sending `String` or `byte[]` | Basic codecs may suffice; still need to agree on MIME type |
| Partner strictly requires a single metadata format | Set `metadataMimeType` per contract and configure how route/metadata are read accordingly |
| Metadata has its own data type | Register Encoder when sending, Decoder and MetadataExtractor when receiving |

Normally, keep Composite Metadata and only change `dataMimeType` when selecting a specific Data format or ensuring a contract with another system.

## 9. Common Errors and How to Check Them

**Client sends JSON but responder cannot read the object**

- Check `dataMimeType` in the `SETUP` frame.
- Check that both sides have compatible JSON Encoders/Decoders.
- Check whether the configuration uses the right `RSocketStrategies`.
- Do not assume that having Jackson on the classpath makes every `RSocketStrategies` automatically register JSON codecs.

**Route works but custom metadata does not appear in handler**

- Check whether the connection uses Composite Metadata.
- Check the MIME type of the metadata entry when sending.
- Check that a Decoder supports the exact MIME type and target type.
- Register the entry with `metadataExtractorRegistry(...)` and read the exact name with `@Header("tenantId")`.

**Set metadataMimeType but still cannot send multiple metadata entries**

- Check whether the value is still `message/x.rsocket.composite-metadata.v0`.
- A single metadata format does not have an independent entry structure like Composite Metadata.
- If calling `setupMetadata(...)` multiple times or combining `setupRoute(...)` with `setupMetadata(...)`, Composite Metadata must be used.

**Both applications use the same MIME type yet remain incompatible**

- Having the same MIME type does not guarantee two codecs represent data the same way.
- Check schemas, data types, Jackson settings, versions, and null/field handling rules.
- Check both request and response directions; both sides need the corresponding encode/decode capabilities.

## 10. Recommended Configuration Process

1. Decide the Data format both applications will use, such as JSON or CBOR.
2. Register the corresponding Encoder and Decoder in `RSocketStrategies` on both sides.
3. Set `dataMimeType` explicitly if a stable contract or cross-language connection is needed.
4. Keep Composite Metadata if you need routes and multiple metadata entries.
5. Register a Decoder and MetadataExtractor for each custom metadata MIME type.
6. Test requests, responses, routes, and metadata over a real connection between both ends.

## Conclusion

`dataMimeType` describes how Data is encoded; `metadataMimeType` describes how the Metadata region is encoded. Both are declared at the connection level in the `SETUP` frame. In Spring, `RSocketStrategies` provides Encoders/Decoders, while `MetadataExtractor` helps the responder turn metadata into values accessible via headers.

Treat MIME types, codecs, and schemas as part of the contract between requester and responder. Only when both sides agree on all three factors can business data and metadata be exchanged accurately.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework 6.1 — RSocketRequester.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Spring Framework 6.1 — RSocketStrategies.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
- [RSocket Protocol — SETUP frame](https://github.com/rsocket/rsocket/blob/master/Protocol.md#setup-frame)
