# `@ConnectMapping` and Handling Connection Setup Data

## 1. Position of `SETUP` in the RSocket Lifecycle

RSocket begins by establishing a connection over a transport such as TCP or WebSocket. Once the transport is ready, the requester sends a **SETUP** frame so both sides agree on connection-level information. This frame can contain data, metadata, MIME types, and protocol parameters. Data and metadata in `SETUP` are optional.

Only after the responder accepts `SETUP` do the two sides begin exchanging ordinary requests such as Request-Response, Request-Stream, Channel, or Fire-and-Forget. Therefore, data in `SETUP` has connection-level meaning, whereas a payload sent in a subsequent request belongs to that individual request.

Spring provides **RSocketRequester.Builder** to declare initial setup data:

| API | Role |
|---|---|
| `setupData(Object)` | Data sent in the `SETUP` frame |
| `setupRoute(String, Object...)` | Route metadata of the `SETUP` frame |
| `setupMetadata(Object, MimeType)` | Additional metadata in `SETUP` |
| `dataMimeType(MimeType)` | MIME type for data on the connection |
| `metadataMimeType(MimeType)` | MIME type for metadata on the connection |

For example, the client can send a route identifying the connection type and a device ID upon setup:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("device.connect")
    .setupData("device-001")
    .tcp("localhost", 7000);
~~~

In this example, `device-001` is the data of `SETUP`; `device.connect` is the route located in the metadata of `SETUP`. They are not the data and route of an ordinary request.

Calling `tcp(...)` creates the requester and configures the transport. The actual connection may be established lazily when the requester begins using the connection. When the connection opens, the configured `SETUP` data and metadata are sent during the handshake.

## 2. What Is `@ConnectMapping`?

**org.springframework.messaging.rsocket.annotation.ConnectMapping** is the annotation for mapping connection-level events to a handler method. This annotation handles two frame types:

- **SETUP:** the first frame when a new RSocket connection is established.
- **METADATA_PUSH:** metadata notifications sent afterward, not tied to a specific request.

This is a method-level annotation. `@ConnectMapping` methods accept similar parameter types as `@MessageMapping`, but the data comes from `SETUP` or `METADATA_PUSH`. Common parameters include:

- **@Payload:** frame data, such as a client identifier string or connection configuration DTO.
- **RSocketRequester:** requester representing the current connection, used to send requests back to the other side.
- **@DestinationVariable:** variable extracted from the route if the route pattern contains variables.
- **@Header** and **@Headers:** metadata decoded by `MetadataExtractor` and placed into message headers.

`@ConnectMapping` can declare a route pattern. For example, `@ConnectMapping("device.connect")` only receives events with matching route metadata. If no pattern is declared, the method matches all connections and metadata pushes.

Unlike `@MessageMapping`, a `@ConnectMapping` method **must not return response data**. The return type must be `void` or `Mono<Void>`. On the server side, when returning `Mono<Void>`, the connection is accepted when the publisher completes successfully; if handling emits an error, the new connection is rejected. On the client side, the method acts solely as a callback and does not govern connection establishment.

## 3. Reading `setupData` with `@Payload`

In the previous example, the client sent the route `device.connect` and String data. The server side can receive that data as follows:

~~~java
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Mono;

@Controller
public class DeviceConnectionController {

    private final ConcurrentMap<String, Instant> connectedDevices =
        new ConcurrentHashMap<>();

    @ConnectMapping("device.connect")
    public Mono<Void> onConnect(@Payload String deviceId) {
        if (deviceId == null || deviceId.isBlank()) {
            return Mono.error(
                new IllegalArgumentException("deviceId is required")
            );
        }

        return Mono.fromRunnable(
            () -> connectedDevices.put(deviceId, Instant.now())
        );
    }
}
~~~

When the client sends `SETUP` with route `device.connect`, Spring locates the `@ConnectMapping` method matching the route and decodes the data into a `String` to pass into the `deviceId` parameter. The method validates the data and records the connection timestamp. `Mono.fromRunnable` executes the action when subscribed to and completes without producing a response payload.

This is an illustrative handler example. A real application needs to define how connection lifecycles are managed, handle duplicate client identifiers, and clean up state when connections close. Do not rely on `deviceId` alone as a unique connection identifier if the same device can open multiple concurrent connections.

Beans with `@ConnectMapping` must be detected by **RSocketMessageHandler** and registered as responders. In Spring Boot, appropriate RSocket server configuration integrates the handler via auto-configuration. With plain Spring configuration, you must create `RSocketMessageHandler` and attach its responder to the RSocket server.

## 4. Sending a DTO Instead of a Plain String

Data in `SETUP` is not limited to `String`. The client can send a DTO containing multiple fields:

~~~java
public record DeviceSetup(
    String deviceId,
    String applicationVersion,
    String platform
) {}
~~~

Client configuration:

~~~java
DeviceSetup setup = new DeviceSetup(
    "device-001",
    "2.4.0",
    "desktop"
);

RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("device.connect")
    .setupData(setup)
    .tcp("localhost", 7000);
~~~

Server receives the same structure:

~~~java
@ConnectMapping("device.connect")
Mono<Void> onConnect(@Payload DeviceSetup setup) {
    if (setup.deviceId() == null || setup.deviceId().isBlank()) {
        return Mono.error(new IllegalArgumentException("deviceId is required"));
    }

    return connectionService.register(setup);
}
~~~

The handler snippet above assumes the application already has `connectionService.register(DeviceSetup)` returning `Mono<Void>`. When using DTOs, both sides must have encoders and decoders compatible with the declared MIME type. Spring Core's default codecs only support basic types such as `String`, `byte[]`, and `ByteBuffer`. To send objects, you can add JSON or CBOR codecs from `spring-web`, such as `Jackson2JsonEncoder`/`Jackson2JsonDecoder` or `JacksonCborEncoder`/`JacksonCborDecoder`, and configure them in `RSocketStrategies` on both client and server.

Example configuring strategies with CBOR:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
    .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
    .build();
~~~

The client passes strategies into the builder using `rsocketStrategies(strategies)`. The server must also use a compatible configuration through `RSocketMessageHandler`. If MIME types or codecs do not match, the payload may fail to decode into the desired DTO.

## 5. Distinguishing Data and Metadata in `SETUP`

RSocket distinguishes data from metadata. Data typically contains business content such as device ID, application version, or configuration details. Metadata can contain routes, security credentials, or connection-level control data.

- **setupData(...)** places an object in the data part of `SETUP`.
- **setupRoute(...)** adds route metadata so the responder can select a handler.
- **setupMetadata(...)** adds metadata under a specific MIME type.
- **dataMimeType(...)** and **metadataMimeType(...)** declare how the corresponding content should be interpreted.

The route in `SETUP` can be used to categorize connections, such as `device.connect`, `admin.connect`, or `monitoring.connect`. It does not replace routes of subsequent requests. An ordinary request still selects its own route via `requester.route("...")`.

For custom metadata, the receiving side must configure decoding. **MetadataExtractor** converts encoded metadata into named values so handlers can access them as message headers. `DefaultMetadataExtractor` supports routing metadata out of the box; for other MIME types, register a decoder and map the data type to a header name.

Example registering custom metadata in `RSocketStrategies`:

~~~java
MimeType clientMetadataMimeType =
    MimeType.valueOf("application/vnd.example.client-metadata");

RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
    .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
    .metadataExtractorRegistry(registry ->
        registry.metadataToExtract(
            clientMetadataMimeType,
            ClientMetadata.class,
            "clientMetadata"
        )
    )
    .build();
~~~

Once the encoder, decoder, and `MetadataExtractor` are configured accordingly, the client can call `setupMetadata(value, clientMetadataMimeType)`. The handler can receive the decoded value via `@Header("clientMetadata") ClientMetadata metadata`. The `ClientMetadata` type is an application-defined DTO.

Not all metadata automatically becomes a header. If the MIME type is unsupported or the corresponding decoder and mapping have not been registered, `@Header` will not receive the expected value.

## 6. Filtering Connections with Route Patterns

If an application has multiple client groups, the `SETUP` route can help select the appropriate handler:

~~~java
@Controller
public class TenantConnectionController {

    @ConnectMapping("tenant.{tenantId}.connect")
    Mono<Void> onConnect(
        @DestinationVariable("tenantId") String tenantId,
        @Payload String clientId
    ) {
        return connectionService.register(tenantId, clientId);
    }
}
~~~

The client must send a route matching the pattern, such as `tenant.acme.connect`. Spring extracts `acme` and passes it into `tenantId`. Route patterns are matched according to the `RouteMatcher` configured in `RSocketMessageHandler`; when `spring-web` is available, `PathPatternRouteMatcher` can be used.

If route-based categorization is unnecessary, `@ConnectMapping` can be used with no value. However, that default handler will then receive all `SETUP` and metadata push events. In applications with multiple connection types, declaring specific routes helps prevent one handler from unintentionally processing different client groups.

## 7. Using `RSocketRequester` in Handlers

A `@ConnectMapping` method can accept an `RSocketRequester` parameter. This is the requester bound to the current connection, allowing the server to send requests back to the client. This is useful in models where both sides can initiate requests.

Note that `@ConnectMapping` handles `SETUP`, and `SETUP` must complete before ordinary requests can begin on the connection. Therefore, do not block `SETUP` handling waiting for a new request sent through that same connection's `RSocketRequester`. If you need to actively send a request to the client as soon as the connection opens, launch that work independently of the `SETUP` handling flow, such as switching to another scheduler and subscribing separately. The `SETUP` handler must still return `void` or `Mono<Void>` for the connection to be accepted.

Do not use `block()` inside a reactive handler. For database or external service calls, prefer reactive APIs and bound processing time. If the handler completes too slowly, connection establishment is also delayed.

## 8. How Do `@ConnectMapping` and `@MessageMapping` Differ?

| Criterion | `@ConnectMapping` | `@MessageMapping` |
|---|---|---|
| Timing | When receiving `SETUP` or `METADATA_PUSH` | When receiving an individual request |
| Scope | Connection-level | Request-level |
| Route | Route in `SETUP` or metadata push metadata | Request route |
| Payload | `SETUP` data; metadata push mainly carries metadata | Request data |
| Return type | `void` or `Mono<Void>` | Can return object, `Mono`, `Flux`, `void`, or `Mono<Void>` |
| Purpose | Initialize, validate, record, or update connection state | Process business logic and return request results |

Example: the client sends `device.connect` along with `deviceId` in `SETUP`. `@ConnectMapping` receives and validates `deviceId` once when the connection is established. Afterwards, the client sends a request with route `device.status`; this request is handled by a corresponding `@MessageMapping` method. The two methods serve two different phases.

## 9. Data Validation, Security, and Common Pitfalls

Data sent by a client in `SETUP` is still untrusted input. You should not treat a self-reported `tenantId`, `userId`, or `role` from the client as an authenticated identity. If metadata carries a token or credentials, the server must verify them using an appropriate security mechanism, such as Spring Security RSocket, before granting access. Do not log tokens or sensitive secrets.

Common errors:

- **Handler is not invoked:** check whether the controller is detected and `RSocketMessageHandler` is registered as the responder.
- **Route does not match:** compare the client's `setupRoute(...)` with the value/pattern in `@ConnectMapping`.
- **Handler receives empty payload:** check whether the client calls `setupData(...)` and whether the right `SETUP` data is being sent.
- **Unable to decode DTO:** check encoder, decoder, and MIME types on both sides; `String` working does not mean DTOs will decode automatically.
- **Unable to read custom metadata:** check composite metadata, MIME type, decoder, and `MetadataExtractor` registration.
- **Connection rejected:** check errors emitted by the handler. On the server, an error in `@ConnectMapping`'s `Mono<Void>` causes `SETUP` to fail.
- **Connection hangs:** avoid `block()`, long synchronous operations, and awaiting new requests over `RSocketRequester` during `SETUP` handling.
- **Handler executes multiple times:** besides the initial `SETUP`, `@ConnectMapping` also handles `METADATA_PUSH`. Do not assume every invocation represents a new connection.

When testing, use a real RSocket client and server to verify routes, payloads, metadata, and connection accept/reject outcomes. Separately test cases with missing `setupData`, wrong routes, wrong MIME types, and handler errors. If metadata push is used, verify that the logic distinguishes connection setup events from post-connection metadata notifications.

## 10. Summary

`@ConnectMapping` is the entry point for connection-level RSocket events in Spring. The client declares initial data via `setupData(...)`, route via `setupRoute(...)`, and custom metadata via `setupMetadata(...)`. The server uses `@ConnectMapping` to read data via `@Payload`, retrieve decoded metadata via headers, and perform validation or connection state initialization.

The method only returns `void` or `Mono<Void>`; the server accepts the connection when processing completes successfully and rejects it when processing errors. Once the connection is open, business requests proceed through `@MessageMapping`. Keep a clear boundary between `SETUP` data and individual request payloads, configure compatible codecs/metadata extractors, and validate all client-supplied data.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [ConnectMapping Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
