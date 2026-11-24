# Documenting `text/event-stream` or an Appropriate Streaming Content Type

In Spring WebFlux, a controller can return `Flux<T>` to emit multiple elements over time. However, the `Flux` return type alone does not determine the HTTP format on the wire. The media type declared via `produces` or chosen through content negotiation determines whether the server sends a complete JSON array, a Server-Sent Events (SSE) stream, or newline-delimited JSON records.

With Springdoc, you need to accurately document the response media type and explain the structure of each element in the stream. If the documentation only shows `application/json` or an array schema while runtime actually returns `text/event-stream`, clients may pick the wrong parser, SDKs may generate incompatible return types, and integrators will not know they must keep the HTTP connection open to receive data.

## 1. Distinguishing Normal JSON Responses from HTTP Streaming

A `Flux<T>` can be written in several ways depending on the media type:

| Media Type | Representation | Common WebFlux Behavior |
|---|---|---|
| `application/json` | A JSON document, usually an array when there are multiple elements | WebFlux collects publisher elements into a collection and serializes as a JSON array |
| `text/event-stream` | Consecutive SSE events, each terminated by a blank line | Writes each event and flushes so clients receive data promptly |
| `application/x-ndjson` | Each line is an independent JSON value | Writes and flushes each element in JSON Lines/NDJSON format |
| `application/jsonl` | JSON Lines | Writes each JSON value per line; requires codec support for this media type |
| `application/stream+json` or `application/json+stream` | Used by some stacks/versions to represent JSON streaming | Use only when your codecs and clients support this exact media type |
| `application/octet-stream` | Byte stream, commonly used for files or binary data | Not a JSON event stream; document under a separate download/binary contract |

Current Spring Framework supports streaming media types such as `application/jsonl` and `application/x-ndjson` for the Jackson JSON encoder; with `text/event-stream`, the encoder writes each event and flushes. Older Spring versions or custom codec setups may use different media types. Always check your Spring Framework version, actual codecs, and the project's client consumers.

Key takeaway: `Flux<T>` combined with `application/json` typically produces a JSON array, whereas `Flux<T>` combined with a streaming media type emits elements over time. Do not conclude an API is streaming merely because the method signature returns `Flux`.

## 2. Choosing the Media Type Based on How Clients Consume Data

### Server-Sent Events: `text/event-stream`

SSE is suitable when the server pushes events unidirectionally to the client over a long-lived HTTP connection. Browsers provide the `EventSource` API, which supports receiving events, automatic reconnection, and protocol-level event ID/retry handling.

An SSE message can contain these fields:

- `event`: event type name.
- `data`: event payload; usually plain text or JSON serialized as a string.
- `id`: event identifier so the client can resume from its previous position upon reconnect.
- `retry`: reconnection delay in milliseconds.
- Lines starting with `:` are comments, commonly used as heartbeats.

Each event ends with a blank line. Example HTTP response:

```text
id: 42
event: order-updated
data: {"orderId":42,"status":"PAID"}

id: 43
event: order-shipped
data: {"orderId":42,"status":"SHIPPED"}

```

The response header must be `Content-Type: text/event-stream`. Data can be sent as multiple events within a single response body; the client keeps the connection open to continue receiving new events.

### NDJSON or JSON Lines: `application/x-ndjson`

NDJSON is suitable when each element is an independent JSON object on its own line. It is a solid choice for large exports, log streams, or sequential pipelines that read records without waiting for an entire JSON array to finish.

Example response:

```text
{"id":101,"status":"PAID"}
{"id":102,"status":"SHIPPED"}
{"id":103,"status":"CANCELLED"}
```

Each line can be parsed as a separate JSON document. There are no `data:`, `event:`, or blank-line markers like in SSE framing. Clients must read line by line and parse each JSON value.

### Standard JSON Array: `application/json`

If clients need a standard JSON response that can be parsed once into a list, use `application/json`:

```json
[
  {"id":101,"status":"PAID"},
  {"id":102,"status":"SHIPPED"}
]
```

In this case, the server may receive items from `Flux` over time, but the response is represented as a complete JSON array. Clients typically have to wait for the complete JSON document before parsing the full array.

## 3. Declaring an SSE Endpoint in an Annotated Controller

Spring WebFlux supports returning `Flux<ServerSentEvent<T>>`. The `ServerSentEvent` wrapper lets you set `id`, `event`, `retry`, comments, and data. If you only need to send data, you can return `Flux<T>`, but the mapping must still declare `produces = text/event-stream`.

Example event DTO:

```java
import java.time.Instant;

public record OrderEvent(
    Long orderId,
    String status,
    Instant occurredAt
) {
}
```

Controller:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/orders")
class OrderEventController {

    private final OrderEventService eventService;

    OrderEventController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @GetMapping(
        value = "/{orderId}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    @Operation(
        operationId = "streamOrderEvents",
        summary = "Track order events",
        description = "Keeps the HTTP connection open and receives SSE events as the order status changes.",
        responses = @ApiResponse(
            responseCode = "200",
            description = "Continuous SSE stream. Each event may contain id, event, and data; data is OrderEvent JSON.",
            content = @Content(
                mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
                schema = @Schema(type = "string"),
                examples = @ExampleObject(value = """
                    id: 42
                    event: order-updated
                    data: {"orderId":42,"status":"PAID","occurredAt":"2026-11-20T10:15:30Z"}

                    """)
            )
        )
    )
    Flux<ServerSentEvent<OrderEvent>> stream(@PathVariable Long orderId) {
        return eventService.eventsFor(orderId)
            .map(event -> ServerSentEvent.<OrderEvent>builder(event)
                .id(event.orderId() + "-" + event.occurredAt())
                .event("order-updated")
                .build());
    }
}
```

`produces` specifies the response media type. `Flux<ServerSentEvent<OrderEvent>>` tells Spring to write each element as an SSE event. The `@ApiResponse` annotation documents the response as `text/event-stream`; the example illustrates the wire framing.

In OpenAPI 3.0/3.1, the `type: string` schema represents the text content of the stream, and the example shows one event frame. The `OrderEvent` DTO is the business payload model inside `data`, though a string schema does not directly bind the DTO structure to each event. If client generators need per-event typing, use OpenAPI 3.2 `itemSchema` when your toolchain supports it, or publish components/extensions following a convention agreed upon by project consumers.

If returning only data without SSE metadata:

```java
@GetMapping(value = "/{orderId}/updates", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<OrderEvent> updates(@PathVariable Long orderId) {
    return eventService.eventsFor(orderId);
}
```

Spring WebFlux can write each element as a data event when the media type is `text/event-stream`. Use `ServerSentEvent<T>` when you need control over event name, ID, retry, or comments.

## 4. Documenting NDJSON in OpenAPI and Springdoc

Controller returning each `OrderEvent` as one JSON record per line:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/exports")
class OrderExportController {

    private final OrderExportService exportService;

    OrderExportController(OrderExportService exportService) {
        this.exportService = exportService;
    }

    @GetMapping(value = "/orders", produces = "application/x-ndjson")
    @Operation(
        operationId = "streamOrdersAsNdjson",
        summary = "Export orders in NDJSON format",
        description = "Each line in the response is an independent OrderEvent JSON object.",
        responses = @ApiResponse(
            responseCode = "200",
            description = "NDJSON stream; each line is an OrderEvent.",
            content = @Content(
                mediaType = "application/x-ndjson",
                schema = @Schema(type = "string"),
                examples = @ExampleObject(value = """
                    {"orderId":101,"status":"PAID","occurredAt":"2026-11-20T10:15:30Z"}
                    {"orderId":102,"status":"SHIPPED","occurredAt":"2026-11-20T10:16:00Z"}
                    """)
            )
        )
    )
    Flux<OrderEvent> streamOrders() {
        return exportService.streamOrders();
    }
}
```

Here, the `string` schema together with the multi-line example describes the text body on the wire in OpenAPI 3.0/3.1. The Java model `OrderEvent` describes the structure of each JSON record; the description must clarify that each line is parsed independently. If you need a standard record schema linked to the stream, use `itemSchema` in OpenAPI 3.2 when supported by your toolchain. Do not document this response as a JSON array if runtime actually emits NDJSON.

If your Spring Framework and codecs support `application/jsonl`, you can choose that media type instead of `application/x-ndjson`. Both formats represent line-delimited JSON values, so ensure clients and gateways support the exact media type advertised by the server.

## 5. Using `itemSchema` When Documents Can Target OpenAPI 3.2

OpenAPI 3.2 adds `itemSchema` for sequential media types such as `text/event-stream`, `application/jsonl`, and `application/x-ndjson`. This field describes the schema of each repeated item in the stream instead of treating the entire body as a single JSON object.

NDJSON example in OpenAPI 3.2:

```yaml
openapi: 3.2.0
paths:
  /api/exports/orders:
    get:
      operationId: streamOrdersAsNdjson
      responses:
        '200':
          description: NDJSON stream; each line is an order.
          content:
            application/x-ndjson:
              itemSchema:
                $ref: '#/components/schemas/OrderEvent'
components:
  schemas:
    OrderEvent:
      type: object
      properties:
        orderId:
          type: integer
          format: int64
        status:
          type: string
        occurredAt:
          type: string
          format: date-time
```

An SSE example in OpenAPI 3.2 can describe both the SSE envelope and the JSON inside the `data` field:

```yaml
openapi: 3.2.0
paths:
  /api/orders/{orderId}/events:
    get:
      operationId: streamOrderEvents
      responses:
        '200':
          description: Server-Sent Events stream.
          content:
            text/event-stream:
              itemSchema:
                $ref: '#/components/schemas/OrderSseEvent'
components:
  schemas:
    OrderSseEvent:
      type: object
      required: [data]
      properties:
        id:
          type: string
        event:
          type: string
        retry:
          type: integer
          minimum: 0
        data:
          type: string
          contentMediaType: application/json
          contentSchema:
            $ref: '#/components/schemas/OrderEvent'
    OrderEvent:
      type: object
      properties:
        orderId:
          type: integer
          format: int64
        status:
          type: string
        occurredAt:
          type: string
          format: date-time
```

`itemSchema` is an OpenAPI 3.2 feature. Do not add this field to documents declaring `openapi: 3.0.x` or `3.1.x`. Support for emitting OpenAPI 3.2 depends on the versions of Springdoc, Swagger Core, and downstream tools. If your current stack does not support it yet, use 3.0/3.1-compatible descriptions as in the earlier examples and document each event/record structure clearly in the description and examples.

Do not assume your Swagger UI or client generator already renders and generates code from `itemSchema` completely. Verify validators, rendered docs, and generated SDKs before standardizing on OpenAPI 3.2 in your pipeline.

## 6. Functional Routes Also Need Media Type Documentation

Springdoc supports Spring WebFlux functional endpoints. With `RouterFunction`, routes are not placed on `@GetMapping` methods; therefore, metadata must be supplied using `@RouterOperation`/`@RouterOperations` or Springdoc's functional DSL.

Example handler returning SSE:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
class OrderEventHandler {

    private final OrderEventService eventService;

    OrderEventHandler(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @Operation(
        operationId = "streamOrderEventsFunctional",
        summary = "Track order events",
        responses = @ApiResponse(
            responseCode = "200",
            description = "SSE stream; data contains OrderEvent JSON.",
            content = @Content(
                mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
                schema = @Schema(type = "string"),
                examples = @ExampleObject(value = """
                    event: order-updated
                    data: {"orderId":42,"status":"PAID"}

                    """)
            )
        )
    )
    Mono<ServerResponse> stream(ServerRequest request) {
        Long orderId = Long.valueOf(request.pathVariable("orderId"));
        Flux<ServerSentEvent<OrderEvent>> events = eventService.eventsFor(orderId)
            .map(event -> ServerSentEvent.<OrderEvent>builder(event)
                .event("order-updated")
                .id(event.orderId() + "")
                .build());

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(BodyInserters.fromServerSentEvents(events));
    }
}
```

Declaring metadata on the Router bean:

```java
import org.springdoc.core.annotations.RouterOperation;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.http.MediaType;

@Bean
@RouterOperation(
    path = "/api/orders/{orderId}/events",
    method = RequestMethod.GET,
    produces = MediaType.TEXT_EVENT_STREAM_VALUE,
    beanClass = OrderEventHandler.class,
    beanMethod = "stream"
)
RouterFunction<ServerResponse> orderEventRoutes(OrderEventHandler handler) {
    return RouterFunctions.route(
        RequestPredicates.GET("/api/orders/{orderId}/events")
            .and(RequestPredicates.accept(MediaType.TEXT_EVENT_STREAM)),
        handler::stream
    );
}
```

`@RouterOperation` uses `path`, `method`, and `produces` to identify the route; `beanClass`/`beanMethod` allows Springdoc to read Swagger annotation metadata on the handler method. For a Router bean with multiple routes, use `@RouterOperations` and declare each `@RouterOperation` with its matching path. You can use Springdoc's functional DSL if you want to describe the operation right in the route builder.

`produces` in the metadata must match the route's `accept(...)` and the response's `contentType(...)`. If a route only accepts `text/event-stream` while the docs publish `application/json`, Springdoc misrepresents how clients must call it.

## 7. An Operation Supporting Multiple Response Media Types

If the same resource can return either a JSON or SSE representation depending on `Accept`, declare multiple media types on the mapping:

```java
@GetMapping(
    value = "/api/orders/events",
    produces = {
        MediaType.APPLICATION_JSON_VALUE,
        MediaType.TEXT_EVENT_STREAM_VALUE
    }
)
Flux<OrderEvent> events() {
    return eventService.allEvents();
}
```

When the client sends `Accept: application/json`, WebFlux can serialize multiple items into a JSON array. When the client sends `Accept: text/event-stream`, WebFlux streams the items as SSE. OpenAPI documentation should describe both media types and explain the difference in how they are read.

OpenAPI 3.0/3.1 example:

```yaml
responses:
  '200':
    description: >
      With application/json, the response is a complete JSON array.
      With text/event-stream, the server keeps the connection open and sends individual SSE events.
    content:
      application/json:
        schema:
          type: array
          items:
            $ref: '#/components/schemas/OrderEvent'
      text/event-stream:
        schema:
          type: string
        examples:
          oneEvent:
            value: |
              event: order-updated
              data: {"orderId":42,"status":"PAID"}
```

If the controller returns `Flux<ServerSentEvent<OrderEvent>>`, avoid declaring `application/json` on the same method unless runtime actually supports and properly serializes that media type. Test content negotiation with requests carrying explicit `Accept` headers.

## 8. How Does Springdoc Infer Schemas from `Flux`?

Springdoc inspects return types, mappings, and annotations to build response content. However, stream representations have nuances that a single Java type does not fully express:

- `Flux<OrderEvent>` indicates multiple emitted values, but does not state whether clients receive a JSON array, NDJSON, or SSE.
- `produces` defines the media type and is an important signal for determining how responses are written.
- `ServerSentEvent<OrderEvent>` carries event metadata, while `OrderEvent` is the data payload.
- `application/x-ndjson` transmits individual JSON records per line, not a JSON array.
- OpenAPI 3.0/3.1 has no standard `itemSchema` for sequential media types; OpenAPI 3.2 introduces this field.

Therefore, for streaming endpoints, declare response content explicitly with `@ApiResponse`/`@Content` when inferred schemas do not accurately reflect the contract. Then inspect the generated document rather than assuming Springdoc will always infer exact stream framing from `Flux`.

Do not use `@ArraySchema` for SSE or NDJSON simply because the method returns `Flux`. `@ArraySchema` describes a JSON array; it does not describe event framing or JSON Lines on the wire.

## 9. Inspecting the Generated OpenAPI Document

After running the application, open `/v3/api-docs` or the corresponding group document. Inspect response `content`:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/orders/{orderId}/events"].get.responses["200"].content'
```

For SSE in OpenAPI 3.0/3.1, you should see the `text/event-stream` media type and its corresponding description/schema. For NDJSON, you should see `application/x-ndjson` or your chosen JSON Lines media type.

Verify that the operation is not mistakenly documented as a JSON array:

```bash
curl -s http://localhost:8080/v3/api-docs \
  | jq '.paths["/api/exports/orders"].get.responses["200"].content | keys'
```

If using OpenAPI 3.2, verify that `itemSchema` exists under the appropriate media type and that the document declares `openapi: 3.2.x`. Do not put `itemSchema` into a 3.0/3.1 document.

For functional routes, verify that the path, HTTP method, `produces`, and operationId appear in the document. If a route is missing, review `@RouterOperation`/`@RouterOperations` or the functional DSL and route identification criteria.

## 10. Testing Streams with HTTP Clients

### Using cURL with SSE

```bash
curl -N \
  -H 'Accept: text/event-stream' \
  http://localhost:8080/api/orders/42/events
```

`-N` disables cURL buffering so events appear as soon as they are received. Without `-N`, cURL or the terminal may make it look like the server has not sent events even though data is buffered on the client.

### Using cURL with NDJSON

```bash
curl -N \
  -H 'Accept: application/x-ndjson' \
  http://localhost:8080/api/exports/orders
```

Clients read line by line and parse each JSON object individually. Do not use a JSON array parser for NDJSON.

### Testing with WebTestClient

For SSE, you can verify the response media type, read a few events, and then cancel the subscription:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest
@AutoConfigureWebTestClient
class OrderEventStreamTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void streamsOrderEventsAsSse() {
        FluxExchangeResult<ServerSentEvent<OrderEvent>> result = webTestClient
            .get()
            .uri("/api/orders/42/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(new ParameterizedTypeReference<ServerSentEvent<OrderEvent>>() {});

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "order-updated".equals(event.event()) && event.data() != null
            )
            .thenCancel()
            .verify();
    }
}
```

Stream tests should use controllable test event data, appropriate timeouts, and cancel subscriptions after verification. If the publisher is an infinite stream, do not use `expectComplete()` as you would for a finite response.

## 11. Browser and SSE Client Limitations

Browsers can use `EventSource` to consume SSE:

```javascript
const source = new EventSource("https://api.example.com/api/orders/42/events");

source.addEventListener("order-updated", (event) => {
  const order = JSON.parse(event.data);
  console.log(order.status);
});

source.onerror = () => {
  console.log("SSE connection interrupted; browser may reconnect automatically.");
};
```

Native `EventSource` does not allow setting arbitrary `Authorization` headers. If an API requires a Bearer token in a header, browser apps can use `fetch` streaming with `ReadableStream`, an SSE library that supports custom headers, or an appropriate cookie mechanism. Do not put long-lived tokens in query strings just to work around this limitation.

If Swagger UI displays a Try it out button, it can send an HTTP request, but it will not necessarily display an infinite stream like a dedicated SSE client. Use cURL, WebTestClient, or a real client application to test continuous events and reconnect behavior.

## 12. Heartbeats, Reconnects, and Proxy Buffering

An SSE connection can remain open for a long time. Proxies, load balancers, or firewalls may close idle connections if no data flows for a period. You can emit comment heartbeats:

```text
: keep-alive

```

Comments do not trigger events in client application logic, yet keep periodic traffic flowing on the stream. When using `ServerSentEvent`, you can emit comment events using the builder API of your Spring Framework version.

Factors to verify:

- Whether reverse proxies buffer responses; buffering can cause events to arrive only in batches.
- Whether gateway/load balancer idle timeouts exceed the heartbeat interval.
- Whether clients handle `Last-Event-ID` and whether the server can resume from the corresponding event ID.
- Whether the publisher honors cancellation when the client disconnects.
- Whether stream connections are bounded in duration or count by system policy.
- Whether the server emits periodic data to detect closed connections.

SSE provides client-side reconnection, but the server must design event IDs and replay behavior appropriately if clients must not miss events during disconnections.

## 13. Handling Errors After the Stream Has Started

With streaming responses, HTTP status and headers are typically already sent once the first element is written. If the publisher emits an error afterward, the server cannot go back to change the status to `500` or replace the already-sent body with a normal JSON error response.

Therefore:

- Authenticate, authorize, and validate parameters before starting the stream whenever possible.
- For business errors that may happen mid-stream, define an error event such as `event: error` with a clearly specified payload schema.
- For severe infrastructure failures, you can terminate the connection; clients must handle broken streams.
- Document stream-initialization errors using HTTP statuses such as 400, 401, 403, or 404 before the body begins.
- Do not promise that every mid-stream error will be returned as Problem Details JSON like synchronous responses.

Example error event:

```text
event: error
data: {"code":"UPSTREAM_UNAVAILABLE","message":"Unable to receive updates at this time"}

```

If you have an error event, include the error payload schema in the OpenAPI document and state that it is an event within the `200 text/event-stream` flow rather than a new HTTP response status.

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Flux<T>` returns a JSON array instead of a stream | Mapping uses `application/json` | Choose a streaming media type such as `text/event-stream` or `application/x-ndjson` |
| Client receives a large chunk after a long delay | Client, proxy, or gateway is buffering | Use cURL `-N`, inspect proxy buffering and flush behavior |
| SSE has no `event` or `id` | Returning `Flux<T>` instead of `Flux<ServerSentEvent<T>>` | Use `ServerSentEvent<T>` when event metadata is needed |
| OpenAPI shows a JSON array for SSE | Schema inferred from `Flux` or array annotation | Declare response content/media type explicitly and inspect the document |
| NDJSON fails to parse | Client uses a JSON array parser or media type mismatch | Read line by line and parse each JSON value |
| Server returns 406 | `Accept` header does not match `produces` | Send the right Accept header or declare media types the API truly supports |
| Functional route missing from Swagger UI | Missing `@RouterOperation`/`@RouterOperations` or metadata fails to match route | Declare exact path, method, produces, and operationId |
| Event stream closes when idle | Proxy timeout or no heartbeats | Emit heartbeats and tune timeouts accordingly |
| Client cannot send Bearer token with EventSource | Native EventSource does not support custom Authorization headers | Use fetch streaming, a header-capable SSE client, or appropriate cookies |
| Error occurs after first event without HTTP 500 | Response is already committed | Define an in-stream error event or close connection per contract |
| `itemSchema` rejected by validator | Document declares OpenAPI 3.0/3.1 | Use `itemSchema` only with OpenAPI 3.2 and compatible toolchains |

## 15. Checklist for Documenting Streaming Responses

- [ ] Chosen the media type matching how clients consume data: SSE, NDJSON/JSON Lines, or JSON array.
- [ ] Controller or functional route `produces` matches runtime `Content-Type`.
- [ ] Clients send an `Accept` header matching the published media type.
- [ ] SSE uses `text/event-stream`; NDJSON uses a media type supported by codecs and clients.
- [ ] Distinguished `Flux<T>` from JSON arrays and wire-level streams.
- [ ] OpenAPI response includes the right media type under `content`.
- [ ] Description explains long-lived streaming, framing, and how to parse each element.
- [ ] Example accurately illustrates SSE frames or NDJSON lines.
- [ ] Did not use `@ArraySchema` to substitute for sequential media type descriptions.
- [ ] If using OpenAPI 3.2, `itemSchema` describes a single event/record and the full toolchain supports it.
- [ ] Functional routes are documented via `@RouterOperation`, `@RouterOperations`, or the functional DSL.
- [ ] Inspected `/v3/api-docs` or the group document after running the application.
- [ ] Tested with cURL `-N`, WebTestClient, or a real stream client.
- [ ] Considered heartbeats, reconnects, cancellation, and proxy buffering.
- [ ] Documented how errors are handled once the response has started sending data.

`text/event-stream` describes SSE with event framing, whereas `application/x-ndjson` or `application/jsonl` describes line-delimited JSON records. `application/json` typically represents a complete JSON array even when the method returns `Flux`. In Springdoc, declare the right media type, explain the structure of each event or record, and verify the generated document. If your entire ecosystem supports OpenAPI 3.2, use `itemSchema` to describe each item in a sequential stream; with OpenAPI 3.0/3.1, use compatible schemas/examples and clearly note representation limits.

## References

- [Spring Framework – WebFlux Controller Return Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework – Reactive Core and JSON Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Springdoc OpenAPI v2 – WebFlux and Functional Endpoints](https://springdoc.org/v2/features.html#spring-webflux-webmvc-fn-with-functional-endpoints)
- [OpenAPI Specification 3.2.1 – Sequential Media Types](https://spec.openapis.org/oas/v3.2.1.html#sequential-media-types)
- [OpenAPI Specification 3.2.1 – Special Considerations for Server-Sent Events](https://spec.openapis.org/oas/v3.2.1.html#special-considerations-for-server-sent-events)
