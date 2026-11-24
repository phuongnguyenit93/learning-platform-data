# Composite Metadata and Multiple Metadata Entries in a Payload

## 1. Why is Composite Metadata needed?

An RSocket `Payload` has two independent parts:

- **Data** contains the business content that the handler processes, such as an order ID, a request object, or a message's payload.
- **Metadata** contains auxiliary information for routing and processing the message, such as the route, authentication credentials, tenant, trace ID, or protocol version.

If a request needs multiple kinds of information at the same time, a single metadata block with a fixed format is hard to extend. For example, the route must be interpreted under the Routing Metadata extension, a token has its own Authentication format, and trace context may use the observability system's format.

**Composite Metadata** is an RSocket extension that allows combining multiple independent metadata entries into the same metadata payload. Each entry has its own MIME type and separately encoded content. Thus, a single request can carry a route, a token, and a trace context simultaneously without stuffing everything into one shared JSON object.

Example of a request:

| Component | MIME type | Sample value |
|---|---|---|
| Route | `message/x.rsocket.routing.v0` | `orders.create` |
| Tenant | `application/vnd.acme.tenant-id.v1` | `tenant-42` |
| Trace | `application/vnd.acme.trace-id.v1` | `trace-7f31` |
| Data | Connection's data MIME type | `order-1001` |

Metadata entries do not replace the data part. They provide context for the responder to route, authenticate, log, or apply policies to the data part.

## 2. Where does Composite Metadata fit in RSocket?

During connection setup, the requester sends a `SETUP` frame declaring the MIME types used for data and metadata; the responder receives these parameters and applies them to the connection. With Spring's `RSocketRequester`, the default metadata MIME type is:

```text
message/x.rsocket.composite-metadata.v0
```

This is the MIME type of the **Composite Metadata container**. It indicates that the metadata payload contains a sequence of entries. The MIME type inside each entry describes how to decode that specific value—for example Routing, Authentication, or an application-defined MIME type.

Three levels must be distinguished:

1. **Connection metadata MIME type**: indicates how to interpret the entire metadata payload. With Composite Metadata, the value is `message/x.rsocket.composite-metadata.v0`.
2. **Entry MIME type**: indicates the format of a single entry inside the container.
3. **Data MIME type**: describes the data portion, independent of metadata.

In a typical request, the route and auxiliary metadata are sent in the metadata of the interaction-initiating frame such as `REQUEST_RESPONSE`, `REQUEST_STREAM`, `REQUEST_CHANNEL`, or `REQUEST_FNF`. The data portion remains separate in the payload.

## 3. Binary structure of a metadata entry

Composite Metadata consists of entries concatenated sequentially. There are no commas, newlines, or separators between entries. Each entry self-describes its MIME type and its data length:

```text
+----------------------+---------------------------+
| M | MIME ID / Length | Custom MIME type          |
+----------------------+---------------------------+
| Metadata Length (24-bit)                         |
+--------------------------------------------------+
| Metadata bytes                                   |
+--------------------------------------------------+
| Next entry ...                                   |
+--------------------------------------------------+
```

Meaning of the fields:

- **M bit** determines how the MIME type is represented.
  - When the M bit is set, the remaining 7 bits are the ID of a well-known MIME type. This saves space because the full MIME type string does not have to be written.
  - When the M bit is unset, the remaining 7 bits represent the length of a custom MIME type; this is followed by the US-ASCII MIME type string, without a null terminator.
- **Metadata Length** is a 24-bit unsigned big-endian integer representing the byte count of the metadata value. The maximum value is 16,777,215 bytes per entry.
- **Metadata bytes** are the content encoded according to that entry's MIME type.

Example of the logical order of a metadata payload:

```text
[Routing entry]
[Tenant entry]
[Trace entry]
[Authentication entry]
```

When decoding, the receiver reads the header to learn the MIME type, reads the length to extract the exact number of bytes for the entry, and then continues at the next byte. Thanks to the explicit per-entry length, a receiver can skip a MIME type it does not support and continue reading subsequent entries.

Several important rules of the extension:

- Multiple entries can exist within the same metadata payload.
- Multiple entries can use the same MIME type.
- Entry order must be preserved when passed to the responder.
- The MIME type and content must align with the encoder/decoder used by both sides.
- The Composite Metadata extension is currently defined at version `v0`.

**Do not confuse entry length with frame metadata length.** An RSocket frame may have a frame-level metadata length field; that field covers the entire composite metadata bytes. Inside that block, each entry has its own 24-bit Metadata Length.

## 4. Sending multiple metadata entries with Spring RSocketRequester

Spring provides `RSocketRequester` to send requests using Java objects instead of manually manipulating `ByteBuf` or assembling bytes. When using Composite Metadata (the default), calling `metadata(value, mimeType)` multiple times appends entries to the same metadata payload.

The example below sends a route, tenant ID, and trace ID in one request:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

public class OrderClient {

    private static final MimeType TENANT_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.tenant-id.v1");

    private static final MimeType TRACE_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.trace-id.v1");

    private final RSocketRequester requester;

    public OrderClient() {
        this.requester = RSocketRequester.builder()
                .tcp("localhost", 7000);
    }

    public Mono<String> createOrder(String orderId,
                                    String tenantId,
                                    String traceId) {
        return requester.route("orders.create")
                .metadata(tenantId, TENANT_ID_MIME)
                .metadata(traceId, TRACE_ID_MIME)
                .data(orderId)
                .retrieveMono(String.class);
    }
}
```

In this example:

- `route("orders.create")` adds Routing Metadata so the responder locates the right handler.
- The first `metadata` call adds the tenant ID with its own MIME type.
- The second `metadata` call adds the trace ID with its own MIME type.
- `data(orderId)` sends the business content in the data portion.
- `retrieveMono(String.class)` declares the expected response data type.

Spring encodes object values using an appropriate `Encoder` registered in `RSocketStrategies`. Spring's basic codecs support `String`, `byte[]`, and `ByteBuffer`. If metadata is a POJO or JSON, register the corresponding encoder on the sending side and the corresponding decoder on the receiving side.

`metadata(value, mimeType)` can only be used when the connection uses Composite Metadata. If the connection is configured with a single metadata MIME type, Spring may throw `IllegalArgumentException` when calling this method. When using the default Composite Metadata, the route is also encoded as an entry with MIME type `message/x.rsocket.routing.v0`.

## 5. Declaring how to decode metadata on the responder

Sending an entry with a custom MIME type is not enough for Spring to automatically turn that value into a header. The responder must register how to decode the entry and the header name the handler will receive.

`RSocketMessageHandler` supports Composite Metadata and Routing Metadata by default. `DefaultMetadataExtractor` handles Routing Metadata out of the box: it decodes the route into a `String` and stores it under the `route` key. For custom MIME types, register the corresponding decoder and mapping.

Example server configuration mapping two entries to headers `tenantId` and `traceId`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketMessageHandler;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

@Configuration
public class RSocketMetadataConfig {

    static final MimeType TENANT_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.tenant-id.v1");

    static final MimeType TRACE_ID_MIME =
            MimeTypeUtils.parseMimeType("application/vnd.acme.trace-id.v1");

    @Bean
    RSocketStrategies rsocketStrategies() {
        return RSocketStrategies.builder()
                .metadataExtractorRegistry(registry -> {
                    registry.metadataToExtract(
                            TENANT_ID_MIME, String.class, "tenantId");
                    registry.metadataToExtract(
                            TRACE_ID_MIME, String.class, "traceId");
                })
                .build();
    }

    @Bean
    RSocketMessageHandler rsocketMessageHandler(
            RSocketStrategies strategies) {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        return handler;
    }
}
```

The MIME types on the server must match the client-side MIME types exactly. The names `tenantId` and `traceId` are the key names chosen by the application to access the decoded values; they are not MIME type names.

The handler can receive those values with `@Header`:

```java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    @MessageMapping("orders.create")
    public Mono<String> create(
            @Payload String orderId,
            @Header("tenantId") String tenantId,
            @Header("traceId") String traceId) {

        String result = "accepted order=" + orderId
                + ", tenant=" + tenantId
                + ", trace=" + traceId;

        return Mono.just(result);
    }
}
```

With the configuration above, Spring executes the following processing flow:

```text
Client
  route("orders.create")
  metadata(tenantId, TENANT_ID_MIME)
  metadata(traceId, TRACE_ID_MIME)
  data(orderId)
        |
        v
Composite Metadata in request
  [routing] [tenant] [trace]
        |
        v
MetadataExtractor
  route    -> orders.create
  tenantId -> tenant-42
  traceId  -> trace-7f31
        |
        v
@MessageMapping("orders.create")
  @Payload orderId
  @Header tenantId
  @Header traceId
```

The configuration above consists of components of a Spring application with an RSocket responder. It is not a standalone Java program runnable with just `javac`: the application requires Spring Messaging/RSocket dependencies, Reactor, transport configuration, and an active RSocket connection. With Spring Boot, the appropriate auto-configuration can be used; if configuring Spring Framework manually, `RSocketMessageHandler` must be registered as the responder for the RSocket server.

## 6. POJO or JSON metadata

Metadata does not have to be a string. An application can send a structured object, provided both sides agree on the MIME type and have matching encoders/decoders.

Example metadata object:

```java
public record ClientContext(String appVersion, String region) {
}
```

The sender can invoke:

```java
.metadata(
    new ClientContext("2.4.0", "ap-southeast-1"),
    MimeTypeUtils.parseMimeType("application/vnd.acme.client-context+json"))
```

When using JSON, configure `RSocketStrategies` with `Jackson2JsonEncoder` on the sending side and `Jackson2JsonDecoder` on the receiving side. The responder registers that MIME type with the target type:

```java
registry.metadataToExtract(
        CLIENT_CONTEXT_MIME, ClientContext.class, "clientContext");
```

The handler can then receive the object via `@Header("clientContext")`. The header name is the key registered by the application in the extractor. Do not assume Spring will decode a custom MIME type unless the corresponding decoder and mapping exist.

For JSON metadata containing multiple fields, you can also register a mapper to place decoded fields into the output map. This is useful when mapping individual fields to headers, though you must establish clear naming conventions and avoid overwriting existing keys.

## 7. Multiple entries with the same MIME type and ordering

Per the Composite Metadata extension, the same MIME type may appear across multiple entries and entry order is preserved. This is useful when an application protocol defines a list of metadata entries of the same type.

However, distinguish wire-protocol capabilities from the Spring-layer data model. `MetadataExtractor` returns name-value pairs in a `Map`; if multiple entries map to the same key, the application should not assume they automatically become a list. Explicitly define how to collect values using a custom mapper or use distinct keys. If ordering carries business meaning, test the actual decoding and mapping behavior.

Do not use multiple entries of the same MIME type to send a large list when the data portion or a single metadata structure is more appropriate. Metadata should remain small context that can be processed before or independently of the data portion.

## 8. When should you use Composite Metadata?

Suitable use cases:

- **Routing**: select a handler or logical endpoint via a route.
- **Authentication**: pass authentication credentials following an agreed extension or security mechanism.
- **Tenant context**: identify the tenant to apply data scoping and policies.
- **Tracing**: pass a trace ID or tracing context to connect spans across multiple services.
- **Versioning/capability**: advertise the protocol version or capabilities required by a request.
- **Content hints**: carry small processing hints that do not belong to the main business data.

Keep the data portion for content that the handler needs to process as a business message. Only put information into metadata when it is genuinely context or a processing directive.

## 9. Common errors

| Error | Cause | Resolution |
|---|---|---|
| Can only send one metadata type | Connection uses a single metadata MIME type | Use Composite Metadata on both sides |
| Calling `metadata()` throws `IllegalArgumentException` | `RSocketRequester` does not use Composite Metadata | Check the connection's `metadataMimeType` |
| Handler does not receive custom header | MIME type not registered with `MetadataExtractor` | Add `metadataToExtract` for that MIME type |
| Encode/decode error | Missing encoder/decoder or MIME type mismatch | Configure matching codecs on both sides |
| Route cannot find handler | Route does not match `@MessageMapping` or route matcher | Check route, separator, and route matcher config |
| Metadata value is misinterpreted | MIME type describes the wrong byte format | Align the MIME type and actual encoding |
| Metadata is too large | Putting business data into metadata | Move large data to the data portion |
| Duplicate entries lost during mapping | Multiple entries write to the same map key | Use a mapper or explicit collection structure |

Several operational notes:

1. Define versioned MIME types, such as `application/vnd.acme.trace-id.v1`, so schemas can evolve without silently breaking older decoding logic.
2. Avoid overly generic MIME type names like `text/plain` for different meanings if the responder must distinguish each metadata type.
3. Validate incoming metadata as untrusted input. A tenant ID or trace ID does not itself prove identity or access rights.
4. Do not use tenant metadata as the sole authorization mechanism. Authenticate the principal and verify that the principal has permission to access the requested tenant.
5. Never log access tokens, credentials, or sensitive metadata.
6. Keep metadata small to reduce encoding, transmission, and decoding overhead.
7. Test cases for missing required metadata, unsupported MIME types, malformed values, and unauthorized requests.

## 10. Verification checklist

- [ ] Connection declares `message/x.rsocket.composite-metadata.v0` if multiple entries are needed.
- [ ] Each entry has its own MIME type and content encoded in the right format.
- [ ] Client and server agree on MIME types, schemas, and versions.
- [ ] Custom metadata entries are registered in `MetadataExtractor`.
- [ ] Handler accesses the exact keys via `@Header` or `@Headers`.
- [ ] Route is decoded and matches `@MessageMapping`.
- [ ] Repeated metadata entries are handled by explicit rules without accidental overwriting.
- [ ] Metadata does not replace the data portion and does not carry unnecessary large data.
- [ ] Access permissions are verified independently of client-supplied metadata values.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket — Composite Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/CompositeMetadata.md)
- [RSocket — Routing Metadata Extension](https://github.com/rsocket/rsocket/blob/master/Extensions/Routing.md)
- [Spring Framework 6.1 — RSocketRequester.MetadataSpec](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.MetadataSpec.html)
- [Spring Framework 6.1 — RSocketStrategies.Builder](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.Builder.html)
- [Spring Framework 6.1 — MetadataExtractorRegistry](https://www.springframework.org/spring/docs/6.1.11/javadoc-api/org/springframework/messaging/rsocket/MetadataExtractorRegistry.html)
