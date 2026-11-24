# Encoder, Decoder, and Codec Configuration in Spring RSocket

## Objectives

RSocket transmits payloads as bytes and metadata. Spring applications typically work with Java objects such as records, DTOs, or message classes, so a conversion layer between objects and bytes is required. Spring uses `Encoder` to serialize outgoing data, `Decoder` to decode incoming data, and `RSocketStrategies` to group codecs together with supporting strategies for the requester and responder.

Understanding how to configure codecs ensures both ends of a connection understand the same format, handle custom DTOs, use JSON/CBOR/Protocol Buffers properly, and avoid common errors such as a missing `Encoder`, mismatched MIME types, or decoding into the wrong type.

## 1. What are Encoder, Decoder, and codec?

### Encoder

`org.springframework.core.codec.Encoder<T>` converts an object of type `T` into one or more `DataBuffer` instances to send over RSocket. For example, `JacksonJsonEncoder` turns a Java DTO into JSON bytes; `ProtobufEncoder` converts a message generated from Protocol Buffers into Protobuf bytes.

An `Encoder` needs to determine whether it supports the requested data type and MIME type. Spring calls `canEncode(ResolvableType, MimeType)` to check compatibility before using the encoder.

### Decoder

`org.springframework.core.codec.Decoder<T>` performs the reverse direction: it reads a `DataBuffer` and produces a Java object. `JacksonJsonDecoder` can decode JSON into a DTO; `ProtobufDecoder` decodes Protobuf bytes into a `Message`.

A `Decoder` must also determine the target type and MIME type it supports via `canDecode(ResolvableType, MimeType)`. Without a suitable decoder, Spring cannot convert the received payload into a handler parameter or the response type expected by the requester.

### Codec

In this context, codec is a collective term for an encoder and decoder pair. A data format usually needs both an `Encoder` and a `Decoder`:

- Requester sending direction: the `Encoder` on the requester converts the object into bytes.
- Responder receiving direction: the `Decoder` on the responder converts bytes into an object.
- Responder replying direction: the `Encoder` on the responder converts the result into bytes.
- Requester receiving direction: the `Decoder` on the requester converts bytes into the response type.

Therefore, a configuration with only an `Encoder` or only a `Decoder` typically supports only one direction of data exchange. For bidirectional communication, both sides need compatible codecs on both the sending and receiving directions.

## 2. Role of RSocketStrategies

`RSocketStrategies` is where Spring groups the components used to encode and decode data and metadata as well as support message processing. This component can contain:

- A list of `Encoder` and `Decoder` instances.
- A `DataBufferFactory` for allocating data buffers.
- A `ReactiveAdapterRegistry` for adapting reactive types.
- A `RouteMatcher` for matching handler routes.
- A `MetadataExtractor` for converting metadata into application values.

`RSocketRequester.Builder` accepts `RSocketStrategies` to configure the requester. `RSocketMessageHandler` can also use the same configuration to handle the responder. If the client and server reside in the same application, consider declaring a shared `RSocketStrategies` bean to prevent the two configurations from diverging.

### Default codecs in Spring Framework

If only the basic codecs from `spring-core` are used, Spring supports simple types such as:

- String
- byte[]
- ByteBuffer

These basic codecs do not automatically turn arbitrary Java DTOs into JSON. To handle common object types, the application typically needs `spring-web`, which provides implementations such as Jackson JSON, Jackson CBOR, and Protobuf.

### Default codecs in Spring Boot

Spring Boot auto-configures an `RSocketStrategies` bean when `spring-boot-starter-rsocket` is present. According to the Spring Boot 4.1 documentation, the default order is:

1. CBOR codec using Jackson.
2. JSON codec using Jackson.

The starter provides the necessary dependencies for this configuration. Codecs can be added or customized using a bean implementing `RSocketStrategiesCustomizer`. The order of customizers can affect the order in which codecs are registered.

When using Spring Boot, check the default configuration of the exact Boot version in your project before creating a separate `RSocketStrategies` bean. Declaring your own bean may alter or replace the auto-configuration currently used by the application.

## 3. MIME type: format of payload and metadata

RSocket distinguishes between data and metadata. These two parts have separate MIME types declared in the connection's `SETUP` frame:

- `dataMimeType` describes the format of the data part in a payload, for example `application/json`, `application/cbor`, or `application/x-protobuf`.
- `metadataMimeType` describes how metadata is packaged. The default value is typically composite metadata, allowing a single request to carry multiple metadata entries with their own MIME types.

The MIME types in `SETUP` apply to the connection. Therefore, `dataMimeType` is not simply an HTTP `Content-Type` per request. When a requester sends a JSON DTO, the responder must have a `Decoder` compatible with the corresponding MIME type and Java type.

With composite metadata, each metadata entry can have its own MIME type. For example, the route and authentication credentials can be separate metadata entries. Do not confuse the MIME type of a metadata entry with the payload's `dataMimeType`.

`RSocketRequester.Builder` provides the following methods:

- `dataMimeType(MimeType)`: sets the MIME type for the connection's data.
- `metadataMimeType(MimeType)`: sets the MIME type for the connection's metadata.
- `setupData(Object)`: adds data to the `SETUP` frame.
- `setupMetadata(Object, MimeType)`: adds a metadata entry to the `SETUP` frame.
- `setupRoute(String, Object...)`: adds a route to the `SETUP` frame.

In most applications using the default routing and composite metadata, there is no need to change `metadataMimeType`. If there are multiple `Decoder` instances in the registry, set `dataMimeType` explicitly when you want to fix the exchange format. If not set, the default data MIME type is inferred from the first configured `Decoder`.

## 4. Configuring the JSON codec with Spring Framework

The following example uses the Spring Framework 7.0 API and Jackson 3. `spring-web` along with the corresponding Jackson dependencies are required.

### Declaring RSocketStrategies

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.json.JacksonJsonDecoder;
import org.springframework.http.codec.json.JacksonJsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
class RSocketCodecConfiguration {

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
            .encoders(encoders -> encoders.add(new JacksonJsonEncoder()))
            .decoders(decoders -> decoders.add(new JacksonJsonDecoder()))
            .routeMatcher(new PathPatternRouteMatcher())
            .build();
    }
}
~~~

`JacksonJsonEncoder` handles converting DTOs to JSON; `JacksonJsonDecoder` handles converting JSON to DTOs. `PathPatternRouteMatcher` is a route matcher from `spring-web`, useful when the application needs pattern-based route matching. If it is not needed, the default route matcher can be used.

### Using the same strategy for the responder

For a Spring Framework application that configures the responder manually, `RSocketStrategies` can be attached to `RSocketMessageHandler`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;

@Bean
RSocketMessageHandler rsocketMessageHandler(RSocketStrategies strategies) {
    RSocketMessageHandler handler = new RSocketMessageHandler();
    handler.setRSocketStrategies(strategies);
    return handler;
}
~~~

`RSocketMessageHandler` uses the `Encoder` and `Decoder` instances in the strategy to process payloads for `@MessageMapping` and `@ConnectMapping` methods. When starting `RSocketServer` manually via the low-level API, the responder from the handler must be attached to the server transport. With Spring Boot, the handler and server infrastructure can be auto-configured based on dependencies and application properties.

### Configuring the requester

~~~java
import org.springframework.http.MediaType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

`dataMimeType` is explicitly set to `application/json` so both sides agree on the data format. `requester` uses the same strategy to encode requests and decode responses. The TCP connection in the example is only the transport; the codec determines how objects are represented as bytes.

## 5. Example of transferring a JSON DTO over RSocket

Define simple DTOs:

~~~java
public record DeviceEvent(
    String deviceId,
    long sequence,
    double temperatureC
) {}

public record DeviceAck(
    String deviceId,
    String status
) {}
~~~

Responder:

~~~java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class DeviceController {

    @MessageMapping("telemetry.accept")
    Mono<DeviceAck> accept(DeviceEvent event) {
        return Mono.just(new DeviceAck(event.deviceId(), "accepted"));
    }
}
~~~

Requester:

~~~java
Mono<DeviceAck> response = requester.route("telemetry.accept")
    .data(new DeviceEvent("sensor-17", 42, 28.6))
    .retrieveMono(DeviceAck.class);
~~~

When the request is executed, `JacksonJsonEncoder` serializes `DeviceEvent` into JSON. On the server side, `JacksonJsonDecoder` recreates `DeviceEvent` so the `accept` method receives an object of the right type. The `DeviceAck` value returned by the handler is encoded on the server side, then decoded into `DeviceAck` by the requester.

With the sample data above, the response object looks like:

~~~text
DeviceAck[deviceId=sensor-17, status=accepted]
~~~

The code snippets above are parts of a Spring application that already configures transport, strategies, and routes; they are not standalone Java programs that can simply be run with `javac`. In tests or command-line applications you can block to retrieve the result, whereas in a reactive pipeline you should return `Mono`/`Flux` to the calling layer.

## 6. Configuring codecs with Spring Boot

When using `spring-boot-starter-rsocket`, Boot auto-configures `RSocketStrategies`, `RSocketMessageHandler`, and `RSocketRequester.Builder` matching the available dependencies.

A standalone TCP server can be configured in `application.properties`:

~~~properties
spring.rsocket.server.transport=tcp
spring.rsocket.server.port=7000
~~~

For WebFlux running on Reactor Netty, RSocket can be mounted over WebSocket:

~~~properties
spring.rsocket.server.mapping-path=/rsocket
spring.rsocket.server.transport=websocket
~~~

In cases where Boot has already auto-configured JSON/CBOR codecs, there is no need to add the Jackson codecs again if the default configuration meets the requirements. When additional codecs are needed, use `RSocketStrategiesCustomizer`:

~~~java
import org.springframework.boot.rsocket.messaging.RSocketStrategiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.codec.protobuf.ProtobufDecoder;
import org.springframework.http.codec.protobuf.ProtobufEncoder;

@Bean
RSocketStrategiesCustomizer protobufCodecs() {
    return strategies -> {
        strategies.encoder(new ProtobufEncoder());
        strategies.decoder(new ProtobufDecoder());
    };
}
~~~

The customizer adds the Protobuf encoder and decoder to the strategy that Boot is building. Customizer order can be set with `@Order` if the application has multiple customizers and registration order needs to be controlled.

Boot also provides `RSocketRequester.Builder` as a prototype bean. Each injection point receives a separate builder because the builder holds configuration state. Create the requester from the builder injected into the service that needs the connection, avoiding reusing one configured builder across multiple connections with different settings.

## 7. Using Protocol Buffers as the payload format

Protocol Buffers is suitable when a clear schema, small payload, and cross-language compatibility are needed. Spring Web provides `ProtobufEncoder` and `ProtobufDecoder` to work with Java classes generated from `.proto` files.

Message classes are generated using `protoc` and implement `com.google.protobuf.Message`. The `protobuf-java` dependency must be present in the application.

Register `ProtobufEncoder` and `ProtobufDecoder` in `RSocketStrategies` or via `RSocketStrategiesCustomizer` as shown in the previous section. When creating the requester, set the appropriate data MIME type:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.parseMimeType("application/x-protobuf"))
    .tcp("localhost", 7000);
~~~

`ProtobufEncoder` and `ProtobufDecoder` support `application/x-protobuf` and `application/octet-stream`. For a single value, Protobuf uses the standard message format. For a multi-message `Flux`, Spring uses the delimited format: each message's size is written before the message content so the decoder can properly separate element boundaries.

`ProtobufDecoder` defaults to a maximum message size limit of 256 KB. This can be adjusted using `setMaxMessageSize(int)` if application requirements need a different limit; choose the limit intentionally to avoid receiving oversized payloads. Do not assume that a Protobuf `Flux` can be read as a single Protobuf message without delimiting information.

## 8. Building a custom Encoder and Decoder

When a data format is not provided out of the box by Spring, you can implement your own `org.springframework.core.codec.Encoder<T>` and `Decoder<T>`.

An implementation needs to fulfill these key responsibilities:

1. Determine the Java type and MIME type supported by the codec in `canEncode` or `canDecode`.
2. Advertise the list of supported MIME types via `getEncodableMimeTypes` or `getDecodableMimeTypes`.
3. Convert objects into `DataBuffer` on the encode side; convert `DataBuffer` into objects on the decode side.
4. Handle formatting errors, missing data, invalid data, and payload size.
5. Properly support both single-value paths and multi-value streams if the application needs both.

Registering a custom codec:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoder(new MoneyEncoder())
    .decoder(new MoneyDecoder())
    .build();
~~~

The names `MoneyEncoder` and `MoneyDecoder` here represent two application-written implementations. When writing a codec, use the passed-in `DataBufferFactory` to create buffers, and do not assume a single MIME type for all payloads. The codec must check the actual MIME type and data type before processing.

Do not use Java native serialization for payloads over the network. Schema-based or standard formats such as JSON, CBOR, and Protobuf make it easier to control compatibility, input limits, and multi-language support.

## 9. Metadata and metadata codecs

Metadata can carry a route, authentication token, or contextual information. `RSocketRequester` supports adding metadata to a request using `metadata(value, mimeType)`:

~~~java
import org.springframework.util.MimeType;

MimeType bearerMimeType =
    MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Mono<DeviceAck> response = requester.route("telemetry.accept")
    .metadata(accessToken, bearerMimeType)
    .data(event)
    .retrieveMono(DeviceAck.class);
~~~

With the default composite metadata, each metadata entry is packaged with its own MIME type. The metadata value must also have a suitable `Encoder`. On the receiving side, `MetadataExtractor` and the registered `Decoder` instances are used to convert metadata into application values or headers.

A route is a metadata entry in RSocket's routing format. Therefore, if changing `metadataMimeType` to another format, ensure both sides still understand how to represent the route and the required metadata entries. In most applications using `route(...)`, keep the default composite metadata.

## 10. Codec troubleshooting workflow

When encountering encode/decode errors, check in order:

1. Is the payload's Java type supported by the `Encoder`/`Decoder`?
2. Is the codec registered in the `RSocketStrategies` actually used by both the requester and responder?
3. Does `dataMimeType` in `SETUP` match the codec format on both sides?
4. If the payload is metadata, is the MIME type of each metadata entry correct and does the metadata extractor decode that entry?
5. Do both ends use the same schema, field names, numeric types, enums, and nullability rules?
6. Are there multiple codecs supporting the same type and MIME type, causing registration order to pick an unintended codec?
7. Does the message size or payload structure exceed decoder limits?

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No encoder for ... | Appropriate Encoder is not registered or Java type is unsupported | Add the corresponding codec and check `canEncode` |
| No decoder for ... | Missing Decoder or unsupported MIME type | Register the Decoder and check `canDecode` against the actual MIME type |
| DecodingException or Jackson error | Malformed payload, incompatible DTO, or schema mismatch between endpoints | Inspect the payload, DTO types, and mapper configuration |
| Connection succeeds but request fails when sending DTO | Only basic String/byte[]/ByteBuffer codecs are present | Add `spring-web` codecs or use the Spring Boot starter |
| Server decodes wrong format | Requester's `dataMimeType` does not match server-side codec | Set MIME type explicitly and align both ends |
| Metadata is not mapped | Missing Decoder, wrong entry MIME type, or metadata extractor not registered | Check composite metadata and extractor configuration |
| Protobuf stream fails framing | Flux sent/read as a single message instead of delimited messages | Use compatible `ProtobufEncoder`/`Decoder` and verify stream format |
| Large payload is rejected | Decoder message size limit exceeded | Adjust the limit appropriately and control input size |

## 11. Testing and deployment checklist

An integration test should verify at least:

- Sending a DTO and receiving the expected response type back.
- Sending multiple elements if the route supports streaming.
- Verifying JSON or CBOR is decoded properly in both directions.
- Testing custom codecs or Protobuf with the right MIME type.
- Sending payloads with missing fields, invalid fields, or incompatible types to confirm errors are handled.
- Verifying route metadata and business metadata.
- Testing payloads exceeding configured limits.
- Ensuring client and server share the same schema and required codec configuration.

Pre-deployment checklist:

1. Choose a clear data format and MIME type.
2. Confirm dependencies provide the corresponding `Encoder`/`Decoder`.
3. Register both `Encoder` and `Decoder` in `RSocketStrategies`.
4. Use the same strategy configuration for requester and responder when possible.
5. Set `dataMimeType` explicitly if the connection uses multiple formats or decoder order could change.
6. Keep `metadataMimeType` compatible with routing/composite metadata.
7. Define payload size limits and validate incoming data.
8. Run round-trip tests over an actual RSocket connection.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocketStrategies — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html)
- [JacksonJsonEncoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/json/JacksonJsonEncoder.html)
- [JacksonJsonDecoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/json/JacksonJsonDecoder.html)
- [ProtobufEncoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/protobuf/ProtobufEncoder.html)
- [ProtobufDecoder — Spring Framework API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/protobuf/ProtobufDecoder.html)
- [RSocketStrategiesCustomizer — Spring Boot API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/rsocket/messaging/RSocketStrategiesCustomizer.html)

## Version compatibility notes

Some Jackson codec names change across Spring Framework lines:

- Spring Framework 6.x uses Jackson 2, e.g., `Jackson2JsonEncoder`, `Jackson2JsonDecoder`, `Jackson2CborEncoder`, and `Jackson2CborDecoder`.
- Spring Framework 7.x switches to Jackson 3, using `JacksonJsonEncoder`, `JacksonJsonDecoder`, `JacksonCborEncoder`, and `JacksonCborDecoder`. The older Jackson2 codecs are deprecated as of Spring Framework 7.0.

Use class names and dependencies matching your project's Spring Framework/Spring Boot version. Do not mix Jackson 2 and Jackson 3 codecs in the same configuration example without explicit compatibility intent.
