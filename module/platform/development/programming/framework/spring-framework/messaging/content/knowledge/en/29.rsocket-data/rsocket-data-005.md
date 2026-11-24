# MetadataExtractor and Mapping Metadata to Headers

## Objectives

In RSocket, metadata accompanying a payload can carry a route, authentication credentials, tenant, trace, or request context. Spring Framework provides **MetadataExtractor** to decode metadata into name–value pairs and place them into **Spring Message headers**. As a result, handlers can receive values via **@Header** or read all of them via **@Headers**, instead of manually parsing metadata bytes in each method.

After this lesson, you will be able to:

- Distinguish data and metadata in an RSocket payload.
- Explain the roles of `MetadataExtractor`, `DefaultMetadataExtractor`, and `MetadataExtractorRegistry`.
- Register MIME types with a `Decoder` so Spring decodes custom metadata.
- Map a metadata object to a single header or multiple headers.
- Send metadata using `RSocketRequester` and receive metadata in `@MessageMapping`.
- Identify common errors and limitations regarding security and data types.

## 1. Data, metadata, and Spring Message headers

An RSocket request has two independent parts:

- **Data**: the primary business payload, such as `OrderCommand`, chat content, or an object to process.
- **Metadata**: information describing the request, such as route, token, `tenantId`, `traceId`, or protocol version.

Metadata is not an HTTP header. It is a separate section within an RSocket `Payload`. Each metadata entry can have its own format, identified by a MIME type. When using composite metadata, one payload can contain multiple entries with different MIME types, such as one entry for routing and another for request context.

The processing flow on the receiving side can be visualized as follows:

~~~text
RSocket Payload
├── Data: OrderCommand
└── Metadata (composite)
    ├── message/x.rsocket.routing.v0
    │   └── route = "orders.create"
    └── application/vnd.acme.request-context+json
        └── {"tenantId":"acme","traceId":"req-001"}
                    |
                    v
             MetadataExtractor
                    |
                    v
          Map<String, Object>
                    |
                    v
       Spring Message headers
                    |
          +---------+---------+
          |                   |
    @Header("tenantId")   @Headers Map
~~~

**MetadataExtractor** is a strategy that takes an RSocket `Payload` along with the metadata MIME type and returns a `Map<String, Object>`. Spring uses those name–value pairs as headers of the `Message` dispatched to the handler. Thus, the handler works with decoded Java types instead of raw metadata bytes.

Three concepts must be distinguished:

| Component | Responsibility |
|---|---|
| MIME type | Indicates the format of a metadata entry, such as JSON or routing metadata |
| Decoder | Converts encoded data into a Java object |
| MetadataExtractor | Selects metadata to read, applies the appropriate `Decoder`, and puts results into a `Map` by header name |

Metadata becomes an application header only when the extractor can recognize and decode that entry. Sending a custom MIME type from the client alone is not sufficient to produce a header on the server.

## 2. Default MetadataExtractor

Spring provides **DefaultMetadataExtractor**, an implementation of `MetadataExtractor` and `MetadataExtractorRegistry`. It uses configured `Decoder` instances to decode metadata.

By default, the extractor supports routing metadata with MIME type:

~~~text
message/x.rsocket.routing.v0
~~~

The route value is decoded as a `String` and stored under the **route** key, corresponding to **MetadataExtractor.ROUTE_KEY**. `RSocketMessageHandler` uses the route to find the matching `@MessageMapping` method.

For example, when a client sends route `orders.create`, the route feeds into handler selection. This route is RSocket routing information; do not confuse it with the application's `tenantId` or `traceId`.

Other MIME types must be registered explicitly. For example, if a client sends JSON metadata with MIME type `application/vnd.acme.request-context+json`, the server needs to:

1. Have a `Decoder` supporting JSON.
2. Register that MIME type with the target Java type.
3. Specify a header name or a mapper function that writes the result into multiple headers.

Without registration, custom metadata will not automatically appear as the application headers expected by the handler.

## 3. Two ways to map metadata to headers

`MetadataExtractorRegistry` provides overloads of **metadataToExtract**. There are two main ways to use them.

### 3.1. Placing the entire object into one header

When metadata is decoded into a single object, that object can be bound under one name:

~~~java
registry.metadataToExtract(
        CLIENT_CONTEXT_MIME,
        ClientContext.class,
        "clientContext");
~~~

Then the handler receives the object using:

~~~java
@MessageMapping("orders.create")
public Mono<String> create(
        @Header("clientContext") ClientContext context) {
    return Mono.just(context.tenantId());
}
~~~

This approach fits well when fields belong to one concept and the handler wants a strongly typed object.

### 3.2. Splitting an object into multiple headers

When metadata contains multiple independent fields, the overload accepting a mapper lets you place individual fields into the output `Map`:

~~~java
registry.metadataToExtract(
        CLIENT_CONTEXT_MIME,
        new ParameterizedTypeReference<Map<String, String>>() {},
        (context, headers) -> {
            String tenantId = context.get("tenantId");
            String traceId = context.get("traceId");

            if (tenantId != null) {
                headers.put("tenantId", tenantId);
            }
            if (traceId != null) {
                headers.put("traceId", traceId);
            }
        });
~~~

Here, JSON metadata is decoded into `Map<String, String>`. The mapper selects two allowed fields and writes them into the headers `Map`. The handler can receive them directly:

~~~java
@MessageMapping("orders.create")
public Mono<String> create(
        @Payload OrderCommand command,
        @Header("tenantId") String tenantId,
        @Header(name = "traceId", required = false) String traceId) {

    return Mono.just("accepted for tenant " + tenantId);
}
~~~

Use **ParameterizedTypeReference** when the target type has generic parameters such as `Map<String, String>`. Passing only `Map.class` loses generic type information due to Java type erasure, and the `Decoder` will not receive the full expected element types.

The mapper is also the right place to normalize header names, filter out unnecessary fields, and convert types. Avoid dumping all client-sent keys into headers via `putAll` if the application only needs a fixed set of fields; explicitly selecting `tenantId` and `traceId` helps avoid unexpected headers or collisions with internal headers.

## 4. Configuring RSocketStrategies

`RSocketStrategies` brings together components used to encode and decode data, metadata, and `MetadataExtractor`. The builder provides **metadataExtractorRegistry** to register custom metadata while keeping default configuration, including route handling.

The example below uses JSON metadata and maps two fields to two headers. `Jackson2JsonEncoder` and `Jackson2JsonDecoder` belong to Spring Web; the application needs Jackson and the corresponding RSocket dependencies. With Spring Boot, the RSocket starter provides the base codec infrastructure; strategies can be customized to suit application needs.

### 4.1. Declaring shared MIME types

~~~java
import org.springframework.util.MimeType;

public final class RSocketMetadataTypes {

    public static final MimeType REQUEST_CONTEXT =
            MimeType.valueOf(
                    "application/vnd.acme.request-context+json");

    private RSocketMetadataTypes() {
    }
}
~~~

The MIME type name must match between sender and receiver. Using a vendor-specific MIME type helps distinguish the application's request context structure from other JSON metadata.

### 4.2. Registering the Decoder and mapper

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;

@Configuration
public class RSocketMetadataConfig {

    @Bean
    RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders ->
                        encoders.add(new Jackson2JsonEncoder()))
                .decoders(decoders ->
                        decoders.add(new Jackson2JsonDecoder()))
                .metadataExtractorRegistry(registry ->
                        registry.metadataToExtract(
                                RSocketMetadataTypes.REQUEST_CONTEXT,
                                new ParameterizedTypeReference<
                                        Map<String, String>>() {},
                                (context, headers) -> {
                                    String tenantId =
                                            context.get("tenantId");
                                    String traceId =
                                            context.get("traceId");

                                    if (tenantId != null) {
                                        headers.put("tenantId", tenantId);
                                    }
                                    if (traceId != null) {
                                        headers.put("traceId", traceId);
                                    }
                                }))
                .build();
    }
}
~~~

In the example, `Encoder` serves the side sending JSON metadata; `Decoder` serves the receiving side. If the application only receives metadata on one side, only the needed codecs must be configured on that side. When using the same `RSocketStrategies` for both client and server in one application, both sides can share the same configuration.

Ensure `RSocketMessageHandler` on the receiving side uses the configured strategies. When creating the handler manually in Spring configuration, set it with:

~~~java
RSocketMessageHandler handler = new RSocketMessageHandler();
handler.setRSocketStrategies(rSocketStrategies);
~~~

If the framework or Spring Boot already created the handler, configure the exact handler being used by the server. An `RSocketStrategies` bean has no effect on a handler if the active handler is still using different strategies.

## 5. Sending metadata from RSocketRequester

`RSocketRequester` provides a fluent API to build requests. With composite metadata, call **metadata(value, mimeType)** to add a metadata entry; then declare the data and response type.

~~~java
import java.util.Map;

import reactor.core.publisher.Mono;

import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(rSocketStrategies)
        .tcp("localhost", 7000);

Map<String, String> context = Map.of(
        "tenantId", "acme",
        "traceId", "req-001");

Mono<String> response = requester.route("orders.create")
        .metadata(context, RSocketMetadataTypes.REQUEST_CONTEXT)
        .data(new OrderCommand("SKU-01", 2))
        .retrieveMono(String.class);
~~~

The example assumes a server is listening over TCP at `localhost:7000`, the requester is configured with the corresponding `Encoder`, and `OrderCommand` is an application payload type. The call creates a request with route `orders.create`, JSON metadata containing `tenantId` and `traceId`, and `OrderCommand` as data.

The receiving object can be a Java record:

~~~java
public record OrderCommand(String sku, int quantity) {
}
~~~

Illustrative handler:

~~~java
import reactor.core.publisher.Mono;

import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<String> create(
            @Payload OrderCommand command,
            @Header("tenantId") String tenantId,
            @Header(name = "traceId", required = false) String traceId) {

        return Mono.just(
                "accepted for tenant " + tenantId
                        + ", sku " + command.sku());
    }
}
~~~

When the request reaches the handler, the expected bound values are:

| Location | Value |
|---|---|
| route | orders.create |
| tenantId | acme |
| traceId | req-001 |
| command.sku() | SKU-01 |
| command.quantity() | 2 |

These are values bound to handler parameters, not stdout of a standalone program. The code snippets are parts of a Spring application with an RSocket server/client and the required dependencies.

## 6. Reading all metadata with @Headers

If a handler needs multiple registered metadata entries, it can receive all of them as a `Map`:

~~~java
@MessageMapping("orders.inspect")
public Mono<String> inspect(
        @Headers Map<String, Object> headers) {

    Object tenantId = headers.get("tenantId");
    Object traceId = headers.get("traceId");

    return Mono.just(
            "tenant=" + tenantId + ", trace=" + traceId);
}
~~~

**@Header** is suitable when the handler knows the exact values it needs. **@Headers** fits logging, auditing, or shared logic that needs to inspect the set of extracted headers. This `Map` contains Spring Message headers, not a copy of the original metadata bytes.

If a header may be absent, set `required=false` on `@Header` or handle a nullable type appropriately. By default, `@Header` requires the header to be present; missing a required header can cause parameter binding to fail before the handler body runs.

## 7. Request-level vs. connection-level metadata

Metadata is usually attached per request, such as route, tenant, or trace ID. RSocket also carries metadata in the `SETUP` frame when establishing a connection. Spring supports connection-level event handling via **@ConnectMapping**; this method can read data and metadata from `SETUP`, as well as metadata pushed via `METADATA_PUSH`.

Choose the right scope:

- Data meaningful only to a single request, such as `traceId` or request version, should be sent with that request.
- Data describing the connection, such as client initialization info, can live in `SETUP` and be handled by `@ConnectMapping`.
- Metadata push is a connection-level notification, not a header of a specific business request.

Do not store per-request state in `SETUP` metadata if that value changes from request to request. Conversely, there is no need to repeat static connection-level data on every request if the protocol and security policy permit connection-level handling.

## 8. When should you write a custom MetadataExtractor?

Most applications only need **DefaultMetadataExtractor** with **metadataExtractorRegistry**. This preserves Spring's built-in routing logic while adding the required decoding rules.

Only consider implementing `MetadataExtractor` directly when a specialized metadata format cannot be expressed through existing registrations, such as a proprietary binary layout or decoding rules spanning multiple entries. The implementation must read `Payload` metadata, determine the MIME type, decode the format properly, and return a `Map<String, Object>`.

When replacing the default extractor with a custom implementation, preserve route extraction if the server still uses standard routing metadata. Otherwise, the handler may fail to resolve routes even when the client sends the right route. In most cases, extending via `metadataExtractorRegistry` is simpler and less risky.

## 9. Common errors and checks

| Symptom | Common Cause | What to Check |
|---|---|---|
| `@Header` does not receive `tenantId` | MIME type not registered or mapper does not write the `tenantId` key | Check `metadataExtractorRegistry` and key names in the mapper |
| JSON decoding fails | Missing JSON Decoder or MIME type mismatch | Check the Decoder, client-sent MIME type, and registered MIME type |
| Map decoded to unexpected type | Using `Map.class` and losing generic info | Use `ParameterizedTypeReference<Map<String, String>>` |
| `@MessageMapping` not found | Invalid routing metadata or custom extractor dropped the route | Check route, routing MIME type, and `MetadataExtractor.ROUTE_KEY` |
| Required header missing | Client did not send the field or mapper skipped it | Check sent data, mapper, and `required` on `@Header` |
| Header has wrong value | Two metadata entries write the same key or mapper overwrites values | Use distinct header names and explicitly define which fields can be written |

A helpful checklist for troubleshooting:

1. Confirm the client sends the exact MIME type and metadata structure.
2. Confirm the client has an `Encoder` and the server has a corresponding `Decoder`.
3. Confirm the server handler uses `RSocketStrategies` with `metadataExtractorRegistry` configured.
4. Confirm the mapper writes the exact header names and value types.
5. Temporarily accept `@Headers Map<String, Object>` to inspect extracted headers.
6. Separately check the route to ensure routing metadata is still being processed.

Undecodable metadata can trigger a decode error. Invalid routing metadata can also cause a request to fail before the handler is invoked. Never catch and silently discard required metadata, as doing so can mask protocol or configuration mismatches between both sides.

## 10. Design and security considerations

- **Metadata does not replace payload**: place only control information or small context in metadata. Large business objects still belong in data.
- **MIME type is a communication contract**: client and server must agree on MIME type, JSON structure, field names, and schema version.
- **Limit mapped fields**: only create the headers the handler actually needs. Avoid passing an entire client-sent `Map` directly into headers without validation.
- **Avoid name collisions**: do not overwrite keys used for routing or internal framework headers. Use clear namespaces for application-specific headers when needed.
- **Do not trust `tenantId` solely because it is in metadata**: clients can forge this value. Tenant authorization must rely on an authenticated identity verified on the server; metadata is merely input data.
- **Do not use `traceId` as a credential**: `traceId` serves log correlation and request observability, not identity proof.
- **Control size**: metadata should be small and bounded. Do not send files, large lists, or business payloads in metadata.
- **Maintain version compatibility**: when changing metadata structure, coordinate MIME type or schema versions so older clients and newer servers do not misinterpret each other.

## 11. Key takeaways

`MetadataExtractor` bridges RSocket protocol metadata and Spring Message headers. `DefaultMetadataExtractor` handles standard routing metadata and uses `Decoder` instances to decode registered entries. `MetadataExtractorRegistry` lets you map one object to one header or use a mapper to populate multiple headers. Once `RSocketStrategies` is configured properly on the receiving side, handlers can access values via `@Header` or `@Headers`.

When debugging, check in order: the MIME type, `Decoder`, `metadataToExtract` registration, mapper, and the `RSocketStrategies` used by the handler. If a request does not reach the right handler, also inspect routing metadata and preserve default route extraction behavior.

## References

- [RSocket — Spring Framework Reference](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [MetadataExtractor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html)
- [DefaultMetadataExtractor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/rsocket/DefaultMetadataExtractor.html)
- [MetadataExtractorRegistry — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractorRegistry.html)
- [RSocketStrategies.Builder — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
- [RSocketRequester — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
