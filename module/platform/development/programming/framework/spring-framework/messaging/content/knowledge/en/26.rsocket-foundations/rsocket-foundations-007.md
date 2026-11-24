# Payloads Containing Data and Metadata

## Objectives

In RSocket, every message carries a **payload** made up of two independent parts: **data** and **metadata**. Data typically holds the business content an application wants to send or receive, while metadata describes routing, authentication, tracing, tenant, or processing context.

For example, a client can send an order creation request as follows:

- Data: `{"productId":"P-100","quantity":2}`
- Routing metadata: `orders.create`
- Authentication metadata: user token
- Tenant metadata: active tenant code

Separating data and metadata keeps business content structured cleanly, while control and contextual information can evolve independently. Spring supports encoding and decoding both parts via `RSocketRequester`, `RSocketStrategies`, `Encoder`, and `Decoder`.

## 1. RSocket Payload Structure

In Java, a protocol-layer payload is represented by `io.rsocket.Payload`. A payload has two data regions:

| Component | Meaning | Example |
|---|---|---|
| Data | Primary message content | Order DTO, JSON, string, or bytes |
| Metadata | Message description/control information | Route, token, tracing, tenant |

A message may carry only data, both data and metadata, or in some cases only metadata. Metadata is not mandatory on every request.

RSocket does not mandate that every application use JSON for both parts. Data and metadata can use different formats. For instance, data may be JSON, routing metadata may use RSocket's standard routing format, and authentication metadata may use its own MIME type.

At the low-level Java layer, `Payload` exposes data and metadata as buffers. At the Spring layer, `RSocketRequester` lets you pass Java objects and delegates conversion to codecs.

## 2. Data and Metadata MIME Types

RSocket declares MIME types for data and metadata in the `SETUP` frame. These two MIME types apply to the connection and are used by both sides to interpret payload contents on that connection.

- **Data MIME type** indicates how to interpret the data portion, such as `application/json`, `text/plain`, or a Protobuf MIME type.
- **Metadata MIME type** indicates how to interpret the metadata portion, such as a single metadata format or composite metadata.

When using composite metadata, the metadata MIME type is typically:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata allows one payload to contain multiple metadata entries, each with its own MIME type. For example:

| Metadata entry | MIME type | Value |
|---|---|---|
| Routing | `message/x.rsocket.routing.v0` | `orders.create` |
| Authentication | `message/x.rsocket.authentication.bearer.v0` | Bearer token |
| Tenant context | `application/vnd.example.tenant+json` | JSON tenant context |
| Tracing | Agreed tracing MIME type | Trace context |

If composite metadata is not used, the connection's metadata MIME type describes a single uniform metadata format. In that case, you cannot freely mix multiple independent metadata formats in the same payload the way composite metadata supports.

Typically, Spring sets the data MIME type from the first configured decoder and defaults to composite metadata for the metadata MIME type. Change the defaults only when both client and server explicitly agree on the format.

## 3. How Do Data and Metadata Differ?

Consider a request to search for a tenant's orders:

~~~text
Data:
{
  "status": "PAID",
  "from": "2026-11-01",
  "to": "2026-11-07"
}

Metadata:
  route = orders.search
  tenant = {"tenantId":"acme"}
  trace = {"traceId":"..."}
~~~

Data describes the search criteria. Route identifies which responder should handle the request. Tenant and trace provide context for permission checks, data selection, and system observability.

Design guidelines:

- Place business fields that the handler must process inside data.
- Place routing information and protocol context inside metadata.
- Do not use metadata as a substitute for authorization checks. A token or tenant ID is meaningful only when the server verifies it and binds it to an authenticated identity.
- Do not send the same information in both data and metadata without a clear reason; two copies can diverge.
- Align schemas, MIME types, and metadata versions between requester and responder.

Metadata is not automatically safe or trustworthy merely because it sits outside data. Both parts arrive from the sender and must be validated before use.

## 4. Sending Data with RSocketRequester

`RSocketRequester` is Spring's high-level API for sending and receiving objects without manually managing `ByteBuf` or constructing `Payload` instances.

Example sending a DTO:

~~~java
import java.math.BigDecimal;

public record CreateOrderRequest(
        String productId,
        int quantity,
        BigDecimal unitPrice
) {
}
~~~

Sending a request to route `orders.create`:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.messaging.rsocket.RSocketRequester;

public class OrderClient {

    private final RSocketRequester requester;

    public OrderClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<OrderReceipt> createOrder() {
        CreateOrderRequest request = new CreateOrderRequest(
                "P-100",
                2,
                new BigDecimal("125.50")
        );

        return requester
                .route("orders.create")
                .data(request)
                .retrieveMono(OrderReceipt.class);
    }
}
~~~

Steps:

1. `route("orders.create")` declares the route in the request metadata.
2. `data(request)` supplies the business object to send.
3. `retrieveMono(OrderReceipt.class)` declares the expected response type and selects the Request-Response interaction style.

Spring uses the matching encoder in `RSocketStrategies` to convert the DTO into bytes. The responder uses the corresponding decoder to reconstruct the object. Client and server must agree on the data MIME type and schema.

If a request has no data content, `data(...)` can be omitted and only the route and required metadata sent.

## 5. Adding Per-Request Metadata

When the connection's metadata MIME type is composite metadata, multiple independent entries can be added via `metadata(value, mimeType)`.

Example adding a bearer token and tenant context:

~~~java
import org.springframework.util.MimeType;
import reactor.core.publisher.Mono;

public Mono<OrderReceipt> createOrderWithContext(
        RSocketRequester requester,
        CreateOrderRequest request,
        String accessToken,
        TenantContext tenantContext) {

    MimeType bearerMimeType = MimeType.valueOf(
            "message/x.rsocket.authentication.bearer.v0");

    MimeType tenantMimeType = MimeType.valueOf(
            "application/vnd.example.tenant+json");

    return requester
            .route("orders.create")
            .metadata(accessToken, bearerMimeType)
            .metadata(tenantContext, tenantMimeType)
            .data(request)
            .retrieveMono(OrderReceipt.class);
}
~~~

In this example:

- `route` is encoded by Spring as a routing metadata entry.
- `accessToken` is encoded with the bearer authentication MIME type.
- `tenantContext` is encoded with the application's custom JSON MIME type.
- `request` is encoded as data.

Each metadata value must have a matching encoder in `RSocketStrategies`. If the connection's metadata MIME type is not composite, adding multiple metadata entries with distinct MIME types will not work this way.

Do not invent an arbitrary token format and treat it as authentication. When using Spring Security RSocket, use the authentication metadata mechanisms supported by the security configuration and verify the token on the server.

## 6. Configuring MIME Types in SETUP

`RSocketRequester.Builder` allows declaring the data MIME type and metadata MIME type when establishing a connection:

~~~java
import org.springframework.util.MimeType;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
        .dataMimeType(MimeType.valueOf("application/json"))
        .metadataMimeType(MimeType.valueOf(
                "message/x.rsocket.composite-metadata.v0"))
        .tcp("localhost", 7000);
~~~

These two settings are sent in the `SETUP` frame and apply to the connection:

- `dataMimeType(...)` declares the data format.
- `metadataMimeType(...)` declares the metadata format.

The snippet above creates a requester for a TCP connection. `websocket(URI)` can be used when the server exposes RSocket over WebSocket.

If no data MIME type is specified, Spring infers it from the configured decoders. Metadata defaults to composite metadata. Verify that both sides are compatible; changing the MIME type on one side without updating the other can cause decoding failures.

`setupData(...)`, `setupRoute(...)`, and `setupMetadata(...)` are options for adding content to the SETUP frame itself. This is connection-level information, distinct from data and metadata sent on individual requests.

## 7. Configuring Encoders and Decoders via RSocketStrategies

`RSocketStrategies` manages encoders, decoders, metadata extractors, and conversion components used by RSocket. This is where codecs are configured so both sides can convert the same schemas.

Example registering a Jackson JSON encoder and decoder in an application with the `spring-web` module:

~~~java
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.http.codec.json.JacksonJsonEncoder;
import org.springframework.http.codec.json.JacksonJsonDecoder;

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonJsonEncoder()))
        .decoders(decoders -> decoders.add(new JacksonJsonDecoder()))
        .build();

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

The exact JSON codec classes depend on the Spring and Jackson versions in use. Spring Framework 7 uses the corresponding Jackson 3 codecs; Spring Framework 6.x typically uses Jackson 2 codecs. Do not mix Jackson 2 and Jackson 3 arbitrarily within the same codec configuration.

By default, basic codecs from `spring-core` support `String`, `byte[]`, and `ByteBuffer`. Add `spring-web` to use JSON, CBOR, or other supported codecs.

You can share a single `RSocketStrategies` between requester and responder in the same application to reduce the risk of mismatched codec configurations between the two sides.

## 8. Reading Metadata on the Responder with MetadataExtractor

Metadata received at the RSocket Java layer is still encoded data. Spring uses `MetadataExtractor` to decode metadata entries and map them into key-value pairs accessible inside handlers.

`DefaultMetadataExtractor` natively supports standard routing metadata `message/x.rsocket.routing.v0`, storing the route under the `route` key. Other MIME types require registering a decoder and mapping configuration.

Example registering tenant metadata:

~~~java
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;

MimeType tenantMimeType = MimeType.valueOf(
        "application/vnd.example.tenant+json");

RSocketStrategies strategies = RSocketStrategies.builder()
        .metadataExtractorRegistry(registry ->
                registry.metadataToExtract(
                        tenantMimeType,
                        TenantContext.class,
                        "tenant"))
        .build();
~~~

This example assumes a decoder supporting `TenantContext` is already registered in strategies. When decoded successfully, the metadata entry is placed into the header map under the key `tenant`.

The responder can read metadata via `@Header`:

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<OrderReceipt> create(
            @Payload CreateOrderRequest request,
            @Header("tenant") TenantContext tenant) {

        return orderService.createOrder(request, tenant);
    }
}
~~~

`@Payload` receives data decoded into a DTO. `@Header("tenant")` receives metadata decoded and mapped by the extractor. The route is handled separately by the routing mechanism, not as part of the data body.

If a metadata MIME type has no registered decoder, or the metadata body is invalid, decoding may fail before the handler method is invoked.

## 9. Composite Metadata and Routing Metadata

Composite metadata is a container format for multiple metadata entries. Each entry has its own MIME type and content. This enables one payload to carry route, authentication, tracing, and tenant context simultaneously.

Two key MIME types:

~~~text
message/x.rsocket.composite-metadata.v0
message/x.rsocket.routing.v0
~~~

- `message/x.rsocket.composite-metadata.v0` indicates that payload metadata is composite.
- `message/x.rsocket.routing.v0` represents the request route.

With Spring `RSocketRequester`, when using composite metadata (the default), calling `route("orders.create")` creates a routing metadata entry. You do not need to append the route into data manually.

To add another metadata entry, pass the MIME type for its value:

~~~java
requester.route("orders.search")
        .metadata(tenantContext, tenantMimeType)
        .data(searchCriteria)
        .retrieveFlux(OrderSummary.class);
~~~

If the route or metadata is placed in the wrong section, the responder may fail to locate the handler or decode metadata. For example, sending the route as a JSON field inside data is not equivalent to protocol-level routing metadata.

## 10. Data and Metadata at the Low-Level Java Payload Layer

When working directly with `io.rsocket.Payload`, the application sees data and metadata as `ByteBuf`. The low-level API is useful when integrating directly with RSocket Java or when optimizing buffer operations.

Common operations:

- Read the data region with `payload.data()`.
- Read the metadata region with `payload.metadata()` when the payload has metadata.
- Check whether metadata exists with `payload.hasMetadata()`.
- Create new payloads using RSocket APIs or Spring utilities such as `PayloadUtils.createPayload(...)`.

`Payload` uses reference counting because it may hold underlying Netty buffers. When the application manages payloads directly at the low level, it must follow buffer lifecycle rules: do not use after release; if retained across asynchronous boundaries, retain properly and release the exact matching number of times. Never keep `ByteBuf` references for arbitrary later use after the payload has been released.

Spring's `RSocketRequester` and annotated responders are generally preferable for application code because encoders/decoders manage conversion and the framework handles payload lifecycles. Use raw APIs only with clear technical justification.

## 11. Connection-Level Metadata vs. Request-Level Metadata

Not all metadata belongs to an individual request:

| Scope | How to send | Purpose |
|---|---|---|
| Connection | `setupMetadata(...)` in SETUP | Initial context or connection-level security information |
| Request | `metadata(value, mimeType)` on RequestSpec | Route, token, tenant, or tracing for a specific request |
| Metadata push | `sendMetadata(...)` | Connection-level metadata notification not tied to a specific request |

`METADATA_PUSH` is a dedicated RSocket frame. On the responder side, `@ConnectMapping` can handle SETUP and subsequent metadata pushes. Do not confuse `sendMetadata()` with `metadata(...)` on a request: one is a connection-level notification, while the other is metadata on a request payload.

Do not send tokens on every request if the system uses connection-bound authentication with an appropriate refresh policy. Conversely, if tokens can change per request, clearly define the metadata and server-side verification mechanism.

## 12. Testing Data and Metadata

An integration test should verify that both parts are encoded and decoded accurately:

1. Start an RSocket server with route `orders.create`.
2. Configure client and server to use the same data MIME type and metadata MIME type.
3. Register decoders for the data DTO and tenant metadata.
4. Have the client send the route, data DTO, and tenant metadata.
5. Verify on the server that the route matches, data fields are intact, and metadata maps to the expected key.
6. Have the server return a response DTO; verify the client decodes the response properly.
7. Test unsupported metadata MIME types and malformed payload schemas to confirm errors are clearly observable.

Beyond the happy path, test missing metadata, empty metadata, mismatched MIME types, missing routes, and invalid tokens. Do not check only the final object; verify MIME types, routes, and metadata mappings as well because they are all parts of the protocol.

## Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Server cannot find handler | Route placed inside data instead of routing metadata | Use requester's `route(...)` |
| Data decoding fails | Data MIME type does not match encoder/decoder | Align MIME types and codecs on both sides |
| Metadata does not appear in `@Header` | MIME type not registered in MetadataExtractor | Add `metadataToExtract` and matching decoder |
| Only route gets decoded | Default extractor only natively extracts common routing metadata | Register extractors for custom metadata |
| Composite metadata fails to parse | One side uses a non-composite MIME type or malformed entry | Check `metadataMimeType` and each entry's MIME type |
| JSON tenant metadata fails to deserialize | Missing decoder for TenantContext or incompatible JSON mapper | Register appropriate decoder in RSocketStrategies |
| Token present in metadata yet still rejected | Metadata is just data; server lacks corresponding authentication config | Configure Spring Security RSocket and verify tokens |
| Handler receives wrong data type | Incorrect `getPayloadType` or decoder type | Declare target types and codecs consistently |

## Key Takeaways

- An RSocket payload has two parts: data and metadata.
- Data carries business content; metadata carries route, token, tenant, tracing, or protocol context.
- Data and metadata MIME types are declared in SETUP and apply to the connection.
- Composite metadata allows multiple metadata entries with independent MIME types.
- Spring's `RSocketRequester` provides `data(...)`, `metadata(...)`, and `route(...)` to build high-level payloads.
- `RSocketStrategies` manages encoders, decoders, and metadata extractors.
- `DefaultMetadataExtractor` natively recognizes routing metadata; custom metadata must be registered.
- Metadata must be authenticated and validated just like any other input.
- Raw `Payload` uses reference-counted buffers; retain/release must be managed properly.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/7.0/rsocket.html)
- [RSocketRequester API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [MetadataExtractor API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractor.html)
- [DefaultMetadataExtractor API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/DefaultMetadataExtractor.html)
- [PayloadUtils API](https://docs.spring.io/spring-framework/docs/7.0.9/javadoc-api/org/springframework/messaging/rsocket/PayloadUtils.html)
