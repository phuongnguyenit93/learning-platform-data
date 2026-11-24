# Parameterized Routes and Per-Request Metadata in Spring RSocket

## 1. Roles of Routes and Metadata

In Spring RSocket communication, a request can carry pieces of information with different purposes:

- **Route** identifies the handler or processing flow on the server side. The route is transmitted as RSocket routing metadata.
- **Route variables** supply values to complete a route pattern, such as an order ID or user ID.
- **Payload** contains the business data that the handler needs to process, such as search filters or command contents.
- **Application metadata** carries auxiliary information attached to the request, such as tenant, correlation id, locale, or authentication information according to the configured mechanism.

Routes and metadata do not replace the payload. For example, for a request fetching events of an order, the route might be **orders.{orderId}.events**, the route variable is **orderId**, the payload is a status filter, and metadata might contain the current tenant.

Spring provides **RSocketRequester** to build requests in this way. Each request can select a route, pass variables, attach metadata when needed, send a payload, and choose how to receive the result.

## 2. Declaring a Parameterized Route

Use **route(String route, Object... routeVars)** to declare a route template and replacement values for placeholders enclosed in curly braces.

~~~java
Mono<OrderSummary> result = requester
    .route("orders.{orderId}.summary", orderId)
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

In this example:

- **orders.{orderId}.summary** is the route template.
- **orderId** is the replacement value for the **{orderId}** placeholder.
- **data(...)** sets the request payload.
- **retrieveMono(...)** requests a single result.

When there are multiple placeholders, pass the values in the exact order they appear in the route template:

~~~java
Mono<OrderSummary> result = requester
    .route("customers.{customerId}.orders.{orderId}",
           customerId, orderId)
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

Do not pass a map object expecting Spring to look up values by placeholder name. The API accepts route variables as a varargs list; therefore, the argument order must match the placeholder order.

On the server side, the corresponding route template is declared with **@MessageMapping**. You can retrieve placeholder values with **@DestinationVariable**:

~~~java
@Controller
class OrderRSocketController {

    private final OrderService orderService;

    OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("customers.{customerId}.orders.{orderId}")
    Mono<OrderSummary> summary(
            @DestinationVariable("customerId") String customerId,
            @DestinationVariable("orderId") String orderId,
            @Payload SummaryQuery query) {

        return orderService.summary(customerId, orderId, query);
    }
}
~~~

The client-side route and server-side route pattern must agree. If a route does not match a registered handler, the request is not routed to the desired method. Use stable, structured, business-meaningful route names; avoid arbitrarily concatenating strings from unvalidated input.

## 3. Attaching Metadata Per Request

Metadata is added to a request using **metadata(Object metadata, MimeType mimeType)**. The metadata object is encoded according to the specified MIME type. The receiving side must have a matching decoder and metadata extraction configuration.

For example, define tenant metadata:

~~~java
public record TenantMetadata(String tenantId) {
}
~~~

Declare a custom MIME type for this metadata:

~~~java
private static final MimeType TENANT_MIME_TYPE =
    MimeTypeUtils.parseMimeType(
        "application/vnd.example.tenant+json");
~~~

Attach metadata to a request:

~~~java
Flux<OrderEvent> events = requester
    .route("orders.{orderId}.events", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new OrderFilter("PAID"))
    .retrieveFlux(OrderEvent.class);
~~~

The request above has distinct parts:

- Route **orders.{orderId}.events** selects the order's event stream.
- **orderId** completes the route template.
- **TenantMetadata** provides the tenant context.
- **OrderFilter** is the business payload.
- **retrieveFlux(OrderEvent.class)** receives a stream of events.

Metadata should contain concise information that describes or controls the request. Large business data, search parameters, and processing commands should stay in the payload. The MIME type must be agreed upon by both sides; the example above uses a custom JSON media type for tenant metadata.

## 4. Adding Metadata Only When the Request Needs It

Metadata is optional at the request level. You can create a request spec first, then add metadata only when there is a value to send:

~~~java
RSocketRequester.RequestSpec spec =
    requester.route("orders.{orderId}.summary", orderId);

if (tenantId != null && !tenantId.isBlank()) {
    spec = spec.metadata(
        new TenantMetadata(tenantId),
        TENANT_MIME_TYPE);
}

Mono<OrderSummary> result = spec
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

This approach is useful when one route serves multiple scenarios:

- An internal request that already has a tenant context sends tenant metadata.
- A request without a tenant context omits the optional metadata.
- Another kind of request needing a correlation id or locale attaches the corresponding metadata according to the agreed contract.

If the server requires metadata, validate that condition on the server and return a clear error when it is missing or invalid. Do not rely on the client always sending metadata to skip input validation.

## 5. Configuring MIME Types and Metadata Extraction

RSocket distinguishes the MIME type of data from the MIME type of metadata. When using composite metadata, a metadata payload can contain multiple entries with their own MIME types. Composite metadata enables routing metadata and application metadata to coexist in a single request.

Example configuring a client using JSON for data and composite metadata for the metadata section:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"))
    .connectTcp("localhost", 7000)
    .block();
~~~

The snippet demonstrates establishing a TCP connection and obtaining an **RSocketRequester**. In a real application, manage the connection lifecycle with the application lifecycle and do not call **block()** on an event loop or inside a reactive request processing thread.

On the server side, register how to decode and map the metadata MIME type to a message header. The following example maps tenant metadata to a header named **tenant**:

~~~java
@Bean
RSocketStrategies rSocketStrategies() {
    return RSocketStrategies.builder()
        .metadataExtractorRegistry(registry ->
            registry.metadataToExtract(
                TENANT_MIME_TYPE,
                TenantMetadata.class,
                "tenant"))
        .build();
}
~~~

Ensure **RSocketStrategies** has encoders/decoders matching the metadata MIME type and data type. If using JSON for **TenantMetadata**, both sides must have compatible JSON encoders/decoders. The client's strategies configuration must encode with the exact MIME type; the server's strategies must decode and extract to the exact data type.

Once metadata has been mapped to a message header, the handler can receive it using **@Header**:

~~~java
@MessageMapping("orders.{orderId}.events")
Flux<OrderEvent> events(
        @DestinationVariable("orderId") String orderId,
        @Header("tenant") TenantMetadata tenant,
        @Payload OrderFilter filter) {

    return orderService.eventsFor(
        tenant.tenantId(), orderId, filter);
}
~~~

Here **@Header("tenant")** reads the header created by the metadata extractor. Without registering the metadata mapping, do not assume a custom metadata MIME type will automatically appear as a header named **tenant**.

## 6. Choosing the Interaction Model Based on Expected Result

After configuring the route, metadata, and payload, choose the request terminal method according to the interaction model:

| Method | Result type | Use case |
|---|---|---|
| **retrieveMono(Type.class)** | A single value or empty completion | Request-response |
| **retrieveFlux(Type.class)** | A stream of multiple values | Request-stream |
| **send()** | **Mono<Void>** | Fire-and-forget, no response payload needed |

Request-response example:

~~~java
Mono<OrderSummary> summary = requester
    .route("orders.{orderId}.summary", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

Request-stream example:

~~~java
Flux<OrderEvent> events = requester
    .route("orders.{orderId}.events", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new OrderFilter("PAID"))
    .retrieveFlux(OrderEvent.class);
~~~

Fire-and-forget command example:

~~~java
Mono<Void> sent = requester
    .route("orders.{orderId}.refresh", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new RefreshCommand())
    .send();
~~~

Choosing **retrieveMono**, **retrieveFlux**, or **send** must match the interaction model provided by the server. **send()** is only suitable when the client does not need to read response data; transport or processing errors still need to be handled through the reactive pipeline.

## 7. Distinguishing Route Variables, Payload, and Metadata

| Component | Question answered | Example |
|---|---|---|
| Route | Which function or handler to invoke? | **orders.{orderId}.events** |
| Route variable | Which object or resource? | **orderId = "ORD-42"** |
| Payload | What data needs to be processed? | **OrderFilter("PAID")** |
| Metadata | What auxiliary context does the request have? | **TenantMetadata("tenant-a")** |

A practical rule is to place routing identifiers in route variables, business data in the payload, and shared context or control information in metadata. Do not put the entire payload into the route or use metadata to hold a large business object.

Do not put passwords, tokens, or sensitive data in route variables. Routes often appear in logs, metrics, or diagnostic info; use appropriate RSocket authentication and security mechanisms instead. Custom metadata such as **TenantMetadata** also does not automatically provide authentication or authorization. The server must verify the tenant and access rights before returning data.

## 8. Common Errors and How to Check Them

**Route template does not match**

- Compare the client route against the server-side **@MessageMapping**.
- Check the count and order of route variables.
- Avoid manually concatenating route segments from unvalidated input.

**Metadata does not reach the handler**

- Check whether the client called **metadata(...)** on the right request spec.
- Check the metadata MIME type and composite metadata MIME type.
- Check whether the server has a metadata extractor for that MIME type.
- Check whether a decoder supports the requested metadata type.
- Check that the header name in **metadataToExtract(...)** matches the name in **@Header(...)**.

**Metadata or payload decoding error**

- Confirm both sides agree on data MIME type and metadata MIME type.
- Confirm the JSON encoder/decoder supports the corresponding Java type.
- Check that the outgoing data structure is compatible with the receiving DTO.

**Missing required metadata**

- Determine whether metadata is required or optional in the request contract.
- If required, validate on the server and return a meaningful error when missing.
- If optional, handle the case where the header is absent instead of assuming a value is always present.

**Not receiving the expected response**

- Use **retrieveMono** for a single result, **retrieveFlux** for a stream of results, and **send** when no response data is needed.
- Observe errors in the reactive pipeline using operators such as **doOnError** and handle them at the appropriate boundary.
- Check that the server handler actually returns the data type requested by the client.

## 9. Implementation Checklist

1. Define the route and required placeholders.
2. Pass route variables in the exact placeholder order.
3. Declare the corresponding route pattern on the server with **@MessageMapping**.
4. Choose an appropriate payload type and data MIME type.
5. Only add metadata when the request needs it; specify the MIME type for each metadata type.
6. If using composite metadata, configure compatible metadata MIME types on client and server.
7. Register encoders/decoders and metadata extractors for custom metadata.
8. Use **@DestinationVariable**, **@Payload**, and **@Header** in their proper roles.
9. Choose **retrieveMono**, **retrieveFlux**, or **send** according to the interaction model.
10. Validate metadata on the server before using it for tenant isolation, authentication, or authorization.

**RSocketRequester** lets you build requests flexibly per call: the route selects the handler, route variables identify the specific target, the payload carries business data, and metadata adds context when needed. Designing a clear contract for each part helps client and server work together reliably, testably, and extensibly.