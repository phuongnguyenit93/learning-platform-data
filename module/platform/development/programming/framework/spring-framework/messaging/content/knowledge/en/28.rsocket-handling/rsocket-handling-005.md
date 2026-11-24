# `@Payload`, `@Header`, `@Headers`, and `@DestinationVariable` for RSocket

In Spring Messaging, a method annotated with `@MessageMapping` can receive data from multiple parts of an RSocket request. The four annotations in this lesson clearly distinguish the data source: the message's data section, decoded metadata, or the route used to select the handler. Choosing the right annotation makes the method signature accurately express the communication contract between requester and responder.

## 1. Quick Overview of the Four Data Sources

| Annotation | Gets data from | Use when |
|---|---|---|
| @Payload | The data (payload) part of the request | You need to receive a DTO, string, or business data stream |
| @Header | A metadata value placed into the header map by MetadataExtractor | You need a specific value such as tenant-id or correlation-id |
| @Headers | All decoded and extracted metadata values | You need to read multiple metadata entries in the same handler |
| @DestinationVariable | Variable matched from the @MessageMapping route pattern | The route contains an identifier or routing parameter |

Key point to remember: payload and metadata are two distinct parts of an RSocket message. The route is also transmitted via metadata, but Spring uses the route to locate the handler and extract route variables for @DestinationVariable. @Header and @Headers work with metadata values that have been decoded into key-value pairs.

## 2. @Payload — Receiving the Request Data

@Payload marks the parameter that receives the data content of the message. This content is typically decoded into a DTO by a Decoder registered in RSocketStrategies.

~~~java
@MessageMapping("orders.create")
public Mono<OrderView> create(@Payload CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

In this example, the requester sends a CreateOrderRequest in the data section; Spring decodes the data into the request object and passes it to the request parameter.

Important points:

- @Payload can accept a concrete object or a reactive type such as Mono<T> and Flux<T>.
- This annotation can be omitted when the parameter is a complex type, does not belong to another special parameter category, and is inferred by Spring as the payload. Using @Payload explicitly makes the signature easier to read, especially when the method has multiple parameters.
- For simple types such as String, byte[], or scalar types, declare @Payload explicitly rather than relying on inference.
- If a request only needs the route or metadata and carries no data, the handler can omit any @Payload parameter.

Do not put tenant-id, token, or route into a DTO just to read them inside the handler. Keep the payload for business data and use metadata or routes for their intended purpose.

## 3. @Header — Receiving a Single Metadata Value

@Header retrieves a single value from the header map that MetadataExtractor builds after decoding the metadata of the RSocket message.

~~~java
@MessageMapping("orders.create")
public Mono<OrderView> create(
        @Payload CreateOrderRequest request,
        @Header(name = "tenant-id", required = false) String tenantId) {

    return orderService.createForTenant(request, tenantId);
}
~~~

In this example, tenant-id is the key name registered by the application in MetadataExtractor. `required = false` allows requests without this value; in that case, the parameter can receive null. If the value is mandatory, keep the default `required` setting or provide a `defaultValue` appropriate for the application's contract.

@Header in RSocket does not mean an HTTP request header. An RSocket message has its own metadata section. Spring must decode the metadata and map it to a key before a handler can receive it via @Header.

### Registering Custom Metadata

DefaultMetadataExtractor supports routing metadata out of the box and puts the route under the `route` key. For custom metadata, you need a Decoder matching the metadata's MIME type and must register a mapping from that MIME type to the key name used by the handler.

Example registration in RSocketStrategies:

~~~java
.metadataExtractorRegistry(registry ->
    registry.metadataToExtract(tenantMimeType, String.class, "tenant-id"))
~~~

Here tenantMimeType is the MIME type the requester uses when sending metadata. The corresponding Decoder must be configured in strategies. The requester side also needs a matching Encoder to serialize the metadata value. The key name `"tenant-id"` must match the name in @Header.

## 4. @Headers — Receiving All Extracted Metadata

@Headers is typically declared with Map<String, Object>. Spring passes in a map containing metadata values decoded and registered by MetadataExtractor.

~~~java
@MessageMapping("orders.create")
public Mono<OrderView> create(
        @Payload CreateOrderRequest request,
        @Headers Map<String, Object> metadata) {

    Object route = metadata.get("route");
    Object tenantId = metadata.get("tenant-id");

    // Metadata can be used for logging, tracing, or context checking.
    return orderService.create(request, tenantId);
}
~~~

Distinguishing the two approaches:

- `@Header(name = "tenant-id")` retrieves only one specific key, suitable when the handler depends directly on that value.
- `@Headers Map<String, Object>` receives multiple extracted keys, suitable when inspecting metadata contextually or forwarding a set of metadata.

This map is not a raw copy of all metadata bytes on the wire. It contains the values that MetadataExtractor has decoded and placed into the map. Therefore, if a metadata MIME type has not been registered or lacks a matching Decoder, you cannot assume that key will appear in the map.

## 5. @DestinationVariable — Extracting Variables from the Route

@DestinationVariable extracts a segment of the route matched against a placeholder in the @MessageMapping pattern. It does not retrieve values from the payload or a custom metadata key.

~~~java
@MessageMapping("orders.{orderId}.status")
public Mono<OrderStatus> status(
        @DestinationVariable("orderId") String orderId) {

    return orderService.findStatus(orderId);
}
~~~

If the requester sends the route `orders.ord-100.status`, Spring matches the pattern `orders.{orderId}.status` and passes `ord-100` into `orderId`.

Requester example:

~~~java
Mono<OrderStatus> result = requester
        .route("orders.ord-100.status")
        .retrieveMono(OrderStatus.class);
~~~

An RSocket route is a logical route in metadata, not an HTTP URL. The default route matcher uses a dot (`.`) as the separator. Therefore, keep the pattern and the route sent by the requester consistent with the application's route matcher configuration. If you change the route matcher or separator convention, verify how patterns are matched.

Use @DestinationVariable for routing components such as orderId, userId, or roomId. If the data is business content of the request, place it in the payload; if it is custom metadata, use @Header or @Headers.

## 6. Combined Example

The following controller demonstrates all four annotations in a simple context. The records use Java 17 syntax. This is a handler example, not a standalone RSocket application: the application still needs to register the controller, configure RSocketMessageHandler/server, and provide matching Encoders and Decoders.

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<OrderView> create(
            @Payload CreateOrderRequest request,
            @Header(name = "tenant-id", required = false) String tenantId,
            @Headers Map<String, Object> metadata) {

        String route = Objects.toString(metadata.get("route"), "unknown");

        return Mono.just(new OrderView(
                "ord-100",
                request.sku(),
                request.quantity(),
                tenantId,
                route
        ));
    }

    @MessageMapping("orders.{orderId}.status")
    public Mono<OrderStatus> status(
            @DestinationVariable("orderId") String orderId) {

        return Mono.just(new OrderStatus(orderId, "CONFIRMED"));
    }

    public record CreateOrderRequest(String sku, int quantity) {}

    public record OrderView(
            String orderId,
            String sku,
            int quantity,
            String tenantId,
            String route) {}

    public record OrderStatus(String orderId, String status) {}
}
~~~

How to read the `create` signature:

1. `CreateOrderRequest request` comes from the request data via `@Payload`.
2. `tenantId` comes from the `tenant-id` metadata key registered with `MetadataExtractor` via `@Header`.
3. `metadata` contains decoded metadata values; for example, `route` is a key supported out of the box by `DefaultMetadataExtractor`.
4. The handler returns `Mono<OrderView>`, an asynchronous single result for request-response.

How to read the `status` signature:

1. The route pattern declares the placeholder `{orderId}`.
2. The requester sends the concrete route `orders.ord-100.status`.
3. `@DestinationVariable("orderId")` receives the matched segment `ord-100`.
4. The handler needs no payload if the route alone suffices to look up status.

The requester side can send payload and metadata as follows (`tenantMimeType` must match the MIME type registered on the responder side):

~~~java
Mono<OrderRSocketController.OrderView> created = requester
        .route("orders.create")
        .metadata(tenantId, tenantMimeType)
        .data(new OrderRSocketController.CreateOrderRequest("SKU-01", 2))
        .retrieveMono(OrderRSocketController.OrderView.class);
~~~

In the request above, route selects the handler, metadata supplies `tenant-id`, and data carries `CreateOrderRequest`. These three parts have distinct roles and are resolved by Spring into the corresponding parameters.

## 7. Relationship to the RSocket Interaction Model

The interaction model is determined from the input and output cardinality of the method:

- A single payload and a single result such as `Mono<T>` fit Request-Response.
- A single payload and a multi-element result such as `Flux<T>` fit Request-Stream.
- A multi-element input payload such as `Flux<T>` fits Request-Channel.
- A method with no payload can handle requests based solely on route or metadata.

Therefore, `@Payload` does not merely determine the input data type; the reactive type of the parameter and the return type also influence which interaction model the handler supports. `@Header`, `@Headers`, and `@DestinationVariable` only determine how parameters are extracted and do not themselves change the interaction model.

## 8. Common Errors and How to Check

| Error | Cause | How to fix |
|---|---|---|
| `@Header` always receives null or key is missing | Metadata MIME type is not decoded or key is not registered | Check MIME type, Decoder, and `metadataToExtract` on responder; check Encoder and MIME type on requester |
| `@Header` does not receive HTTP header | Confusing RSocket metadata with HTTP headers | Send metadata via RSocket and register `MetadataExtractor` |
| `@Headers` lacks expected key | Map only contains decoded and extracted values | Check extractor; do not assume raw metadata appears automatically in the Map |
| `@DestinationVariable` does not match | Requester route does not match pattern or uses different separator convention | Compare actual route with `@MessageMapping` and route matcher configuration |
| Payload parameter receives wrong type or fails to bind | Data is incompatible with Decoder/DTO or `@Payload` is missing for simple type | Check data MIME type, Encoder/Decoder, DTO structure, and `@Payload` declaration |
| Handler is not invoked | Route does not match or annotated responder is not registered | Check `@Controller`, `RSocketMessageHandler`, and route pattern |

When debugging, check in order:

1. Did the requester send the right route?
2. Does the data part have a type and MIME type supported by the Decoder?
3. Was metadata sent with the appropriate MIME type?
4. Did `MetadataExtractor` map custom metadata to the right key?
5. Does the placeholder name in `@MessageMapping` match the name in `@DestinationVariable`?

## 9. Rules for Choosing Annotations

- Need the business content of the request: use `@Payload`.
- Need a single extracted metadata value: use `@Header`.
- Need multiple extracted metadata values: use `@Headers Map<String, Object>`.
- Need a segment of the route: use `@DestinationVariable`.

Do not use one annotation to substitute for another annotation's data source. Separating payload, metadata, and route keeps RSocket APIs clear, easier to test, and less coupled to message serialization details.

## References

- Spring Framework Reference — RSocket, Annotated Responders, RSocketRequester, and MetadataExtractor: https://docs.spring.io/spring-framework/reference/rsocket.html
- RSocket Protocol: https://rsocket.io/about/protocol/
