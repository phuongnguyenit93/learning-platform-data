# setupRoute, setupData, and setupMetadata in RSocketRequester

## Learning Objectives

After this lesson, you can:

- Explain the role of the **SETUP** frame when opening an RSocket connection.
- Distinguish connection-level data and metadata from per-request data and metadata.
- Configure initial route, data, and metadata using **RSocketRequester.Builder**.
- Receive and handle these values on the server side using **@ConnectMapping**.
- Choose appropriate MIME types, encoders, decoders, and metadata extractors.

## 1. Where Are the Three Methods Located?

**setupRoute**, **setupData**, and **setupMetadata** are methods on **RSocketRequester.Builder**, not methods on a request that has already been created. The builder is obtained with:

~~~java
RSocketRequester.Builder builder = RSocketRequester.builder();
~~~

These methods configure the payload of the **SETUP** frame sent when the client establishes an RSocket connection. After configuration is complete, the builder creates a requester over a transport such as TCP or WebSocket:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("client.connect")
    .tcp("localhost", 7000);
~~~

The SETUP frame is the initial handshake step of a connection. It can contain optional data and metadata, and declares the MIME types used for data and metadata on that connection. The server can accept or reject the connection based on this information. Only after the connection is established do the two sides exchange requests such as Request-Response, Request-Stream, Channel, or Fire-and-Forget.

A requester can share a single connection across multiple requests. Calling **tcp** or **websocket** creates the requester without necessarily opening the connection immediately; the connection is typically established when the first request is executed. Therefore, **setup*** values belong to connection establishment and are not automatically re-sent with each request.

## 2. Comparing the Three Methods

| Method | Part of SETUP payload | Purpose |
|---|---|---|
| **setupRoute(String route, Object... routeVars)** | Routing metadata | Attach a route to the connection-open event so the server selects a connection handler |
| **setupData(Object data)** | Data | Send an initial value, such as client introduction information |
| **setupMetadata(Object value, MimeType mimeType)** | A metadata entry with its own MIME type | Send connection-level context such as tenant, client, or authentication information |

All three are optional. If you do not call a method, the corresponding part is not set in the SETUP payload.

## 3. setupRoute: Route for the Connection-Open Event

Signature:

~~~java
setupRoute(String route, Object... routeVars)
~~~

**setupRoute** adds a route to the SETUP frame's metadata. The server side can use this route to select the **@ConnectMapping** method that handles the new connection.

The route can contain placeholders. Values passed in **routeVars** are converted to strings via **toString()** and substituted into the placeholders:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("client.connect.{clientId}", "client-42")
    .tcp("localhost", 7000);
~~~

The route sent above is **client.connect.client-42**. Formatting rules match **RSocketRequester.route**. If a route variable contains a dot (**.**), Spring replaces that dot with **%2E** so it is not misinterpreted as a route delimiter on the responder side.

Distinguish the two ways of specifying routes:

- **setupRoute** routes the connection-level SETUP event; the server typically handles it with **@ConnectMapping**.
- **requester.route** routes a specific request; the server typically handles it with **@MessageMapping**.

Therefore, setting a route in SETUP does not mean every subsequent request uses that route. Each request still needs to declare its own route if required by the application protocol.

If the server does not need to classify connections by route, you can omit **setupRoute**. A **@ConnectMapping** method without a declared pattern matches all SETUP and metadata push payloads.

## 4. setupData: Initial Connection Data

Signature:

~~~java
setupData(Object data)
~~~

**setupData** sets the data portion of the SETUP payload. The value is encoded according to the **dataMimeType** configured on the builder. Example:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
    .setupData("app=orders-ui;version=1")
    .tcp("localhost", 7000);
~~~

Here, the initial data is a plain text string. The server side needs to decode it using the same MIME type and can receive this value as the payload of **@ConnectMapping**.

The passed value can be a concrete object or a producer generating **a single value** that can be adapted into a Reactive Streams Publisher through **ReactiveAdapterRegistry**. Because SETUP carries only one initial payload, use a single value or a single-value publisher such as **Mono**; do not use a multi-element **Flux** for this purpose.

If **dataMimeType** is not configured, Spring infers the MIME type from the first registered non-default decoder; if no non-default decoder exists, it uses the first decoder. When sending complex objects such as DTOs or JSON, client and server need corresponding encoders/decoders in **RSocketStrategies**. Merely setting the MIME type to JSON does not automatically create a JSON encoder.

The data MIME type declared in SETUP applies to data across the entire connection. Therefore, if you choose **text/plain** as in the example above, data for requests sent over that connection must also be compatible with this configuration.

## 5. setupMetadata: Additional Connection Metadata

Signature:

~~~java
setupMetadata(Object value, MimeType mimeType)
~~~

**setupMetadata** adds a metadata entry to the SETUP payload. The first parameter is the value to send; the second parameter describes the MIME type of that metadata entry itself:

~~~java
MimeType tenantMimeType = MimeTypeUtils.TEXT_PLAIN;

RSocketRequester requester = RSocketRequester.builder()
    .setupMetadata("tenant=acme", tenantMimeType)
    .tcp("localhost", 7000);
~~~

Metadata can be used to pass information tied to the whole connection, such as client identifier, tenant context, authentication info, or session initialization data. The value can be a concrete object or a single-value producer adaptable via **ReactiveAdapterRegistry**. The corresponding encoder must support the chosen data type and MIME type.

### Composite Metadata and Combination Requirements

By default, RSocketRequester's **metadataMimeType** is:

~~~text
message/x.rsocket.composite-metadata.v0
~~~

Composite metadata lets a single payload carry multiple independent metadata entries, each with its own MIME type. The route generated by **setupRoute** is also encoded as a routing metadata entry inside composite metadata.

Therefore, composite metadata must be used when:

- Calling **setupMetadata** multiple times to add multiple metadata entries.
- Combining **setupMetadata** with **setupRoute**.

If you set **metadataMimeType** to a single MIME type other than composite metadata, Spring assumes that MIME type is also the format of the route if a route is provided. Such a configuration is not suitable for mixing a route with multiple metadata entries of distinct formats. When you need a route alongside additional metadata, keep the default composite metadata or explicitly configure the composite MIME type on both sides.

The connection MIME type and individual metadata entry MIME types serve different roles:

- **metadataMimeType** specifies the overall metadata format of the connection.
- The **mimeType** parameter of **setupMetadata** specifies the format of a specific metadata entry inside composite metadata.

## 6. How Does the Server Receive SETUP Information?

Spring provides **@ConnectMapping** to handle the SETUP frame at connection start and subsequent metadata push notifications. This annotation supports route patterns to accept only connections with a matching route.

The arguments to **@ConnectMapping** are similar to **@MessageMapping**, except the data comes from SETUP or METADATA_PUSH:

- **@DestinationVariable** receives variables extracted from the route.
- **@Payload** receives data from SETUP.
- **@Header** receives metadata decoded and mapped to header names by **MetadataExtractor**.

For metadata with a custom MIME type, the server needs a matching decoder and must register how to extract the metadata in **RSocketStrategies**. For example, a `text/plain` metadata entry can be mapped to the header **tenant-info**:

~~~java
@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .metadataExtractorRegistry(registry ->
            registry.metadataToExtract(
                MimeTypeUtils.TEXT_PLAIN,
                String.class,
                "tenant-info"))
        .build();
}
~~~

Make sure the server-side **RSocketMessageHandler** uses this **RSocketStrategies**. Example handler:

~~~java
@Controller
class ClientConnectionController {

    @ConnectMapping("client.connect.{clientId}")
    Mono<Void> onConnect(
            @DestinationVariable String clientId,
            @Payload String setupData,
            @Header("tenant-info") String tenantInfo) {

        // Validate client and tenant information before accepting the connection.
        return Mono.empty();
    }
}
~~~

The pattern **client.connect.{clientId}** matches the route sent by the client via **setupRoute**. **setupData** is received via **@Payload**; the registered `text/plain` metadata entry is received via the **tenant-info** header.

On the server side, the handler can return **void** or **Mono<Void>**. If SETUP handling terminates with an error, the new connection can be rejected. Do not make connection handling wait for another request running over that same connection; if you need to initiate requests from a connection callback, decouple that work from the SETUP handling flow.

## 7. Combined Client-Side Example

The following example sends a route, a data value, and a metadata entry when creating a requester:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.util.MimeTypeUtils;

RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
    .metadataMimeType(MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"))
    .setupRoute("client.connect.{clientId}", "client-42")
    .setupData("app=orders-ui;version=1")
    .setupMetadata("tenant=acme", MimeTypeUtils.TEXT_PLAIN)
    .tcp("localhost", 7000);
~~~

When the connection is opened, the SETUP payload contains:

1. Route **client.connect.client-42** in routing metadata.
2. Data **app=orders-ui;version=1** encoded as **text/plain**.
3. Metadata entry **tenant=acme** with MIME type **text/plain**, packaged inside composite metadata.

Once the connection is ready, the client creates normal requests using the request-level API:

~~~java
Mono<String> response = requester.route("orders.ping")
    .data("hello")
    .retrieveMono(String.class);
~~~

In this example, **orders.ping** and **hello** belong to the individual request. They are not the route and data of the SETUP frame.

## 8. When Should Each Method Be Used?

| Need | Should use | Reason |
|---|---|---|
| Select a handler to run when a client just connects | **setupRoute** | The route is tied to the SETUP event and @ConnectMapping patterns |
| Send a client introduction message during handshake | **setupData** | Data is only needed at the connection level |
| Send tenant, client context, or authentication info at the connection level | **setupMetadata** | Metadata has its own MIME type and multiple entries can be combined via composite metadata |
| Send route, payload, or metadata that varies per operation | **route**, **data**, **metadata** | These are request-level APIs applied to each individual request |

A value suitable for SETUP is usually information that remains relatively stable over the connection's lifetime. If a token or context needs to change per request, consider request-level metadata or re-establishing the connection. Do not treat a client-sent tenant ID as proof of authentication; the server must still verify identity and access permissions. If transmitting sensitive information, protect the transport appropriately and avoid logging secrets.

## 9. Common Errors and How to Handle Them

1. **Using setupRoute instead of route on every request.**  
   **setupRoute** only declares a route in SETUP. Call **requester.route(...)** for each request that needs routing.

2. **Expecting setupData to appear in every request.**  
   **setupData** belongs only to the connection initialization payload. If a request needs its own payload, use **data(...)** on the request spec.

3. **Combining setupRoute and setupMetadata while disabling composite metadata.**  
   When adding metadata beyond the route, use **message/x.rsocket.composite-metadata.v0**. Otherwise, the route and individual metadata entries cannot be represented in the composite format Spring expects.

4. **Server cannot read custom metadata.**  
   Check the MIME type, decoder, and registration in **MetadataExtractorRegistry**. Sending a metadata entry does not automatically make it a named header in the handler.

5. **Both sides disagree on MIME types.**  
   Data MIME type and metadata MIME type are declared at the connection level. Client and server must support the same formats and corresponding codecs.

6. **Passing a multi-element Flux into setupData or setupMetadata.**  
   These two methods accept a single value or single-value producer. Use **Mono** if the value is produced asynchronously.

7. **Waiting for another request to complete inside @ConnectMapping.**  
   **@ConnectMapping** processes SETUP before normal requests can begin. Complete connection handling quickly; if you need to launch requests, decouple that from SETUP processing.

8. **Sending a token once and expecting it to refresh automatically.**  
   Metadata in SETUP is sent during the connection handshake. If credentials expire or change while the connection remains open, you need a refresh strategy, per-request metadata, or connection re-establishment.

## 10. Configuration Checklist

Before running the application, check:

- **setupRoute**, **setupData**, and **setupMetadata** are called on the builder before requester creation methods like **tcp** or **websocket**.
- The route sent by the client matches the server-side **@ConnectMapping** pattern.
- Data MIME type and metadata MIME type are compatible between both sides.
- If using **setupRoute** together with **setupMetadata**, the overall metadata is composite.
- Encoders/decoders support the actual data types.
- Custom metadata MIME types are registered in **MetadataExtractorRegistry** if handlers need to read them via **@Header**.
- Values placed in SETUP are genuinely stable at the connection level; data that varies per request is sent using request-level APIs.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocketRequester.Builder — Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [ConnectMapping — Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
- [RSocketRequester — Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
