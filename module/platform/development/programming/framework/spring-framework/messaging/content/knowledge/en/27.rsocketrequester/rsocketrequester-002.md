# Configuring Shared RSocketStrategies

## Objectives

`RSocketStrategies` is the collection of strategies that Spring uses when encoding, decoding, and routing RSocket messages. Instead of configuring codecs separately for each requester and responder, an application can create one centralized configuration and reuse it on both sides.

Within the same Spring process, the common approach is to declare `RSocketStrategies` as a singleton bean. `RSocketRequester.Builder` uses that bean to build clients; `RSocketMessageHandler` uses the same bean to handle incoming server requests. When the client and server run in separate processes, each process creates its own bean, but they must agree on the data format, MIME types, and metadata on the wire.

## What Does RSocketStrategies Manage?

`RSocketStrategies` groups the following components into a single configuration:

| Component | Role |
| --- | --- |
| `Encoder` | Converts Java objects into byte data in the payload or metadata. |
| `Decoder` | Converts received byte data into Java objects. |
| `RouteMatcher` | Matches routes in metadata against route patterns declared on handlers. |
| `MetadataExtractor` | Reads payload metadata and turns entries into named values for handlers to access. |
| `DataBufferFactory` | Allocates `DataBuffer` instances when Spring creates or processes payloads. |
| `ReactiveAdapterRegistry` | Helps Spring work with reactive types such as `Mono`, `Flux`, and types with registered adapters. |

These components are interrelated. For example, `DefaultMetadataExtractor` uses the configured list of decoders to decode metadata. Therefore, adding a decoder only for data while forgetting a decoder needed for metadata can result in data working while custom metadata fails.

`RSocketStrategies.builder()` creates a builder with default settings. `build()` produces the instance used in the application. If you need to create a variant based on an existing configuration, you can call `strategies.mutate()` and then build a new instance.

## Default Codecs and Object Codecs

At the Spring Framework level, the default configuration includes basic codecs for `String`, `byte[]`, `ByteBuffer`, and `DataBuffer`. These types are suitable for simple payloads. To send DTOs or Java records, you need to register codecs matching the format supported by both ends of the connection.

Codecs for JSON, CBOR, and several other formats are provided in `spring-web`. For example, in Spring Framework 7 with Jackson 3:

```java
import org.springframework.http.codec.cbor.JacksonCborDecoder;
import org.springframework.http.codec.cbor.JacksonCborEncoder;
```

With Spring Framework 6.x using Jackson 2, the corresponding classes are named `Jackson2CborDecoder` and `Jackson2CborEncoder`. Similarly, JSON uses `JacksonJsonDecoder` and `JacksonJsonEncoder` in Framework 7; in Framework 6.x they are `Jackson2JsonDecoder` and `Jackson2JsonEncoder`. Use the codec classes corresponding to the Spring and Jackson versions managed by your project.

Required dependencies depend on how the application is built:

- `spring-messaging` provides `RSocketStrategies`, `RSocketRequester`, and `RSocketMessageHandler`.
- `spring-web` provides many encoders, decoders, and `PathPatternRouteMatcher`.
- With Spring Boot, `spring-boot-starter-rsocket` is a convenient starting point because the starter provides the RSocket infrastructure and Boot-supported codec dependencies.

## Declaring a Shared Bean in Spring Framework

The following example uses CBOR for object payloads and `PathPatternRouteMatcher` for routes. This is a Spring Framework 7 configuration; if the project uses Framework 6.x, replace the codec class names according to the version note above.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.cbor.JacksonCborDecoder;
import org.springframework.http.codec.cbor.JacksonCborEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketConfiguration {

    @Bean
    public RSocketStrategies rSocketStrategies() {
        return RSocketStrategies.builder()
                .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
                .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
                .routeMatcher(new PathPatternRouteMatcher())
                .build();
    }

    @Bean
    public RSocketMessageHandler rSocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
```

`rSocketStrategies()` creates the configuration only once in the application context. Spring injects the same bean into the handler and into services that need to create requesters. Calling `setRSocketStrategies` synchronously configures the encoder, decoder, route matcher, metadata extractor, and reactive adapter registry of `RSocketMessageHandler`.

In an application that builds a server manually with Spring Framework, `RSocketMessageHandler` must also be attached as the responder for the RSocket server, for example:

```java
CloseableChannel server = RSocketServer.create(handler.responder())
        .bind(TcpServerTransport.create("localhost", 7000))
        .block();
```

This bind snippet requires the appropriate RSocket transport dependencies and needs lifecycle management when the application shuts down. If using Spring Boot, the server and `RSocketMessageHandler` are usually auto-configured; do not create an additional manual handler unless you need to replace the default configuration.

## Using That Bean on the Requester Side

`RSocketRequester.Builder.rsocketStrategies(...)` accepts the created instance. Example of a client sending a SKU and receiving an object:

```java
import org.springframework.http.MediaType;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

public record InventoryItem(String sku, String status) { }

public class InventoryClient {

    private final RSocketRequester requester;

    public InventoryClient(RSocketStrategies strategies) {
        this.requester = RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .dataMimeType(MediaType.parseMediaType("application/cbor"))
                .tcp("localhost", 7000);
    }

    public Mono<InventoryItem> findBySku(String sku) {
        return requester.route("inventory.find")
                .data(sku)
                .retrieveMono(InventoryItem.class);
    }
}
```

`dataMimeType` is set explicitly here so the example clearly shows the CBOR contract. If this setting is omitted, Spring infers the data MIME type from the first configured decoder. When multiple formats are present, check the codec order and the MIME type that the requester sends in the `SETUP` frame.

On the responder side, the corresponding route can be received with an annotated handler:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class InventoryResponder {

    @MessageMapping("inventory.find")
    public Mono<InventoryItem> find(String sku) {
        return Mono.just(new InventoryItem(sku, "AVAILABLE"));
    }
}
```

The example illustrates the same DTO so it is easy to follow. In real deployments, the requester and responder may reside in two different applications; the two sides do not share Java objects in memory and must agree on the schema and wire serialization.

## Configuration When Using Spring Boot

Spring Boot auto-configures an `RSocketStrategies` bean along with the required codecs. Current Boot documentation describes the default order as CBOR with Jackson first, followed by JSON with Jackson. `spring-boot-starter-rsocket` provides the relevant dependencies.

When using Boot, it is usually best to extend the auto-configured builder using `RSocketStrategiesCustomizer`. The following example replaces the route matcher while keeping Boot's default codecs:

```java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketBootConfiguration {

    @Bean
    @Order(0)
    public RSocketStrategiesCustomizer routeMatcherCustomizer() {
        return builder -> builder.routeMatcher(new PathPatternRouteMatcher());
    }
}
```

`RSocketStrategiesCustomizer` receives `RSocketStrategies.Builder`, so you can add encoders, decoders, a route matcher, or metadata extractors before Boot builds the final bean. If there are multiple customizers, `@Order` affects the order of application; codec order can affect which codec is selected.

Boot also auto-configures `RSocketMessageHandler` for the server and `RSocketRequester.Builder` for the client. This builder is a prototype bean: each injection point receives a new instance because the builder is stateful. Avoid reusing one already-configured builder for multiple requesters with different setup settings. You can inject the builder into a service and apply the appropriate strategies before calling `tcp(...)` or `websocket(...)`.

Do not both manually declare an `RSocketStrategies`/`RSocketMessageHandler` bean and keep the auto-configuration unchanged without checking back-off conditions and bean ordering. Choose a clear extension point: use `RSocketStrategiesCustomizer` when you only need to supplement Boot's configuration, or manage the beans yourself when intentionally replacing the infrastructure.

## Route Matchers and Route Rules

`RouteMatcher` determines whether a received route matches a route pattern on a handler. By default, Spring uses `SimpleRouteMatcher` based on `AntPathMatcher` with a dot (`.`) as the hierarchy delimiter. `PathPatternRouteMatcher` from `spring-web` is a more efficient option when complex route patterns are needed.

An RSocket route is a hierarchical route name, not an HTTP URL. For example, `inventory.find` and `inventory.{action}` are valid routes following the dot convention. Do not blindly apply HTTP URL path, URL encoding, or slash conventions to RSocket routes.

An important point is that the requester only sends the route in metadata; the responder uses `RouteMatcher` to match that route against `@MessageMapping` methods. If a route does not reach the handler, check the route spelling, pattern rules, and the route matcher on the responder.

## Custom Metadata

An RSocket payload has two independent parts: data and metadata. Metadata typically contains the route, authentication information, trace context, or control information. Default metadata usually uses composite metadata, allowing a single payload to carry multiple entries with their own MIME types.

`DefaultMetadataExtractor` already supports reading routing metadata. When you need to decode another metadata entry, register the MIME type, Java type, and header name using `metadataExtractorRegistry`. The example below shows additional configuration for a CBOR-encoded `TraceContext`; a CBOR decoder must be present in the strategies:

```java
.metadataExtractorRegistry(registry -> registry.metadataToExtract(
        MediaType.parseMediaType("application/cbor"),
        TraceContext.class,
        "traceContext"))
```

Handlers can receive the extracted value through the corresponding header. Both sides need to agree on the entry's MIME type and the decoded data type. If metadata uses a different format, register a decoder supporting that exact MIME type; do not assume the data decoder will automatically decode all metadata.

When you need to replace the entire metadata extraction mechanism, you can use `metadataExtractor(...)` to supply a custom `MetadataExtractor`. When only adding one or a few metadata types, `metadataExtractorRegistry(...)` is usually easier to maintain because it preserves the default behavior.

## Data MIME Type and Metadata MIME Type

`dataMimeType` and `metadataMimeType` describe the payload formats negotiated at the connection level in the `SETUP` frame:

- Data MIME type applies to the data portion of requests on the connection. The default value is inferred from the first decoder in strategies; the requester can set it explicitly with `RSocketRequester.Builder.dataMimeType(...)`.
- Metadata MIME type describes how metadata is packaged. The default is composite metadata, allowing multiple metadata entries with individual MIME types.
- Connection-level MIME types do not replace registering encoders/decoders. Codecs must still support the actual Java object type and MIME type of the data.
- Both ends of the connection must be compatible. One side sending CBOR while the other only has a JSON decoder will fail to decode object payloads.

Only change MIME types when required by the communication contract. If changing formats, update the requester, responder, codecs, and other consuming systems together.

## Codec Ordering and Organization

The builder provides two groups of methods:

- `encoder(...)` and `decoder(...)` add one or more codecs to the list.
- `encoders(Consumer<List<Encoder<?>>>)` and `decoders(Consumer<List<Decoder<?>>>)` let you manipulate the existing codec list directly.

Order matters when multiple codecs can handle the same type or MIME type. Place specific codecs before general codecs when the application needs to prioritize them. Avoid registering the same codec twice or adding a decoder without a corresponding encoder when the application also needs to send that data type.

Do not create a new `RSocketStrategies` on every request call. Strategies are typically a shared configuration that stays stable throughout the application lifecycle. If a variant configuration is needed, use `mutate()` to copy the current configuration, modify the new builder, and then call `build()`.

## Troubleshooting Common Issues

| Symptom | Causes to check |
| --- | --- |
| Cannot find encoder for DTO | No encoder registered for the data type or MIME type; missing codec dependency; DTO not supported by codec. |
| Cannot decode payload | Decoder does not match sender's format, mismatched MIME type, or incompatible schema. |
| Client runs but server reports decode error | Client and responder are using different strategies or different MIME type configurations. |
| `@MessageMapping` is not invoked | Wrong route sent, route pattern does not match, or responder uses a different route matcher than expected. |
| Custom metadata does not appear in handler | Metadata MIME type not registered in extractor, missing appropriate decoder, or header name does not match registered name. |
| Boot has duplicate codecs or wrong codec priority | Multiple `RSocketStrategiesCustomizer` beans exist; check `@Order` and the codec list after customizers run. |

A troubleshooting checklist should proceed in this order:

1. Confirm the classpath contains `spring-messaging`, `spring-web`, and the required codec dependencies.
2. Check the encoder/decoder list and registration order in `RSocketStrategies`.
3. Confirm the requester sends the expected data MIME type and metadata MIME type in `SETUP`.
4. Check whether the route string on the requester matches `@MessageMapping` and the route matcher.
5. For custom metadata, confirm the MIME type, decoder, Java type, and registered header name.
6. Check both sides of the connection. Codec changes on one side need to be reflected in the other side's communication contract.

## Design Notes

- Use one `RSocketStrategies` bean for requesters and responders in the same application that share an encoding and routing contract.
- For applications in separate processes, create equivalent configurations on each side; no Java singleton is shared over the network.
- Keep codec configuration separate from transport configuration. `RSocketStrategies` does not determine host, port, TCP/WebSocket, TLS, keepalive, or session resumption; those settings belong to the requester builder or RSocket connector/server.
- Keep composite metadata if the application needs multiple independent metadata types such as route, authentication, and tracing.
- Only add codecs when there is a specific format requirement. Extra codecs make configuration harder to understand and can affect selection order.
- With Spring Boot, prefer customizers when only extending auto-configuration; avoid creating a second configuration that collides with beans Boot already provides.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketStrategies](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [Spring Framework Javadoc — RSocketRequester.Builder](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot API — RSocketStrategiesCustomizer](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/rsocket/messaging/RSocketStrategiesCustomizer.html)