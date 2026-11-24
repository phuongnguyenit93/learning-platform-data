# Try-It-Out Restrictions and Streaming Display Limits in the UI

Spring WebFlux supports endpoints returning Mono or Flux, including routes declared with RouterFunction. springdoc-openapi can document these routes in OpenAPI so Swagger UI displays operations, media types, responses, and examples. However, documenting a data stream does not make Swagger UI a real-time event-by-event stream viewer.

When designing documentation for WebFlux, separate three concerns: publishing an accurate HTTP contract, deciding which operations may be invoked via Try it out in Swagger UI, and choosing the right tool to inspect streaming data. This lesson focuses on try-it-out controls, functional routes, and UI display limits for SSE/NDJSON streams.

## 1. What Does Swagger UI Do When Invoking Try It Out?

Swagger UI reads the OpenAPI document and renders an interface where users inspect operations, enter parameters and request bodies, and click Execute. When executed, the UI sends an HTTP request from the browser to the server specified in the document.

Try it out is well suited for:

- Quickly checking endpoints with finite responses.
- Testing query parameters, path parameters, headers, and request bodies.
- Inspecting status codes, response headers, and response bodies.
- Generating sample requests or cURL commands to reproduce calls.
- Verifying APIs in development or test environments with appropriate access.

Try it out is not a specialized tool for reading long-lived streaming connections. With SSE or NDJSON, a response can remain open and transmit multiple chunks of data. The UI may stay in a loading/waiting state, or display data only after the body finishes, depending on the Swagger UI, swagger-client, and browser versions.

Therefore, use Swagger UI to publish the contract and test finite requests; use unbuffered cURL, WebClient, EventSource, or a stream-capable HTTP client to observe individual events.

## 2. Controlling Try It Out via Swagger UI Configuration

springdoc-openapi passes Swagger UI settings under the springdoc.swagger-ui prefix. Two key properties are:

| Property | Meaning |
| --- | --- |
| try-it-out-enabled | Expands the Try it out section by default when opening an operation |
| supported-submit-methods | List of HTTP methods allowed to use Try it out |

Example allowing Try it out only for GET and POST:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
    supported-submit-methods:
      - get
      - post
~~~

try-it-out-enabled only controls the initial UI state. Users can still click Try it out on an operation if its method is in the supported list.

supported-submit-methods restricts which methods display an Execute button. For example, configuring only get prevents users from calling PUT, PATCH, or DELETE from the UI. An empty list disables Try it out for all operations:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

Restricting methods does not hide operations from the documentation. Endpoints still appear in Swagger UI and OpenAPI JSON; only interactive execution from the UI is disabled.

## 3. Restricting Try It Out Is Not API Security

supported-submit-methods is a UI configuration setting. It does not modify RouterFunction, remove HTTP mappings, or block requests to the server.

Users can still invoke endpoints using cURL, Postman, WebClient, or another application. Therefore:

- Use Spring Security or a gateway for authentication and authorization.
- Use CORS to control cross-origin requests from browsers.
- Use appropriate CSRF protection if the API relies on cookies/sessions.
- Do not treat hiding the Execute button as protection for write endpoints.
- Do not publish internal server URLs or real tokens in documentation.

If an API only allows trying GET in Swagger UI, that configuration helps reduce accidental writes from the UI. Permissions to create, modify, or delete data must still be enforced by the server.

## 4. Choosing Appropriate Methods per Environment

You can use profiles to tailor the UI per environment:

application-dev.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    try-it-out-enabled: true
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

application-prod.yml:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: false
    supported-submit-methods: []
~~~

This example only adjusts UI behavior. If production should not expose Swagger UI or OpenAPI endpoints, configure springdoc.swagger-ui.enabled and springdoc.api-docs.enabled separately, and protect documentation paths with Spring Security or a gateway. Disabling the UI does not automatically disable the JSON/YAML endpoints.

Do not enable all methods on shared environments if operations can mutate real data. Use test data, least-privilege accounts, and isolated environments.

## 5. How Does springdoc Detect Functional Routes?

With annotation-based controllers, springdoc can read mappings from @GetMapping, @PostMapping, @RequestMapping, and related annotations. Functional endpoints are declared with RouterFunction and HandlerFunction, so they do not carry the same mapping annotations on controller methods.

To document functional routes, springdoc supports two main approaches:

1. Using @RouterOperation for a single route or @RouterOperations for multiple routes in a RouterFunction bean.
2. Using springdoc's functional DSL to attach OpenAPI metadata directly while building routes.

If a RouterFunction contains multiple routes, @RouterOperations must declare the path for each @RouterOperation. Each operation should have a unique operationId. springdoc uses path, HTTP method, produces, and consumes to match descriptions with actual routes; this information must be specific enough to pinpoint a single route.

## 6. Documenting Multiple RouterFunctions with @RouterOperations

Example of a RouterFunction containing an SSE event-stream endpoint and a JSON single-event endpoint:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.RouterOperation;
import org.springdoc.core.annotations.RouterOperations;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration
class EventRoutes {

    @Bean
    @RouterOperations({
        @RouterOperation(
            path = "/api/events/stream",
            method = RequestMethod.GET,
            produces = MediaType.TEXT_EVENT_STREAM_VALUE,
            beanClass = EventHandler.class,
            beanMethod = "stream",
            operation = @Operation(
                operationId = "streamEvents",
                summary = "Receive real-time events",
                responses = @ApiResponse(
                    responseCode = "200",
                    description = "Server-Sent Events stream",
                    content = @Content(
                        mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
                        schema = @Schema(
                            type = "string",
                            description = "Each event may contain id, event, and data; events are separated by a blank line."
                        ),
                        examples = @ExampleObject(
                            name = "orderUpdated",
                            summary = "An order updated event",
                            value = "id: evt-100\nevent: order-updated\ndata: {\"orderId\":\"O-100\",\"status\":\"SHIPPED\"}\n\n"
                        )
                    )
                )
            )
        ),
        @RouterOperation(
            path = "/api/events/{id}",
            method = RequestMethod.GET,
            produces = MediaType.APPLICATION_JSON_VALUE,
            beanClass = EventHandler.class,
            beanMethod = "findById",
            operation = @Operation(
                operationId = "findEventById",
                summary = "Get a single event",
                responses = @ApiResponse(
                    responseCode = "200",
                    description = "Event details",
                    content = @Content(
                        mediaType = MediaType.APPLICATION_JSON_VALUE,
                        schema = @Schema(implementation = EventMessage.class)
                    )
                )
            )
        )
    })
    RouterFunction<ServerResponse> eventRoutes(EventHandler handler) {
        return route()
            .GET("/api/events/stream",
                accept(MediaType.TEXT_EVENT_STREAM),
                handler::stream)
            .GET("/api/events/{id}",
                accept(MediaType.APPLICATION_JSON),
                handler::findById)
            .build();
    }
}
~~~

The example shows two parts that must stay synchronized:

- RouterFunction defines the runtime route, method, and predicates.
- @RouterOperations describes the path, method, media types, and corresponding OpenAPI operation.

beanClass and beanMethod help springdoc reference the handler method to read additional metadata if needed. If a bean has only one route, you can use a standalone @RouterOperation; when there are multiple routes, use @RouterOperations and declare the path for each entry. You can also use springdoc's functional DSL if you prefer describing operations directly at the route builder.

operationId should be unique across the entire OpenAPI document. Do not reuse the same operationId for the SSE route and the JSON route just because they deal with the same event type.

## 7. Functional DSL to Attach Metadata While Building Routes

springdoc also provides a DSL as an alternative to annotations. You can attach operationId, parameters, and responses to the builder:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Bean
RouterFunction<ServerResponse> eventRoutes(EventHandler handler) {
    return route()
        .GET("/api/events/sample", handler::stream, ops -> ops
            .operationId("sampleEvents")
            .tag("Events")
            .response(responseBuilder()
                .responseCode("200")
                .description("A finite event stream for testing.")
            )
        )
        .build();
}
~~~

This is a condensed example; statically import the functional DSL responseBuilder helper matching the springdoc version you use. The DSL is convenient when you want route declarations and metadata close together. For streaming responses that need detailed media types, examples, and event structures, @RouterOperation annotations can be easier to read; you can use OpenApiCustomizer if you need fine-grained control over the OpenAPI model.

When using the DSL, import springdoc builder helpers matching your dependency version. Helper syntax and packages can differ across major versions; consult the v1 or v2 documentation for your project.

## 8. Distinguishing Finite Flux from Streaming Protocols

Flux is simply a Publisher that emits multiple elements. It does not by itself decide how elements are represented over HTTP. Media types and codecs determine body format and how data is written.

| Return Type and Media Type | Common Representation |
| --- | --- |
| Mono<T> with application/json | A single JSON object |
| Flux<T> with application/json | A JSON array; WebFlux collects values into a collection for serialization by default |
| Flux<T> with application/x-ndjson | Each element is a JSON document on its own line |
| Flux<ServerSentEvent<T>> with text/event-stream | Individual SSE events written and flushed |
| Flux<T> with application/stream+json | JSON stream depending on supported codecs and framework version |

Do not infer that an endpoint returning Flux<T> is necessarily streaming on the wire. If you want clients to receive items as they are emitted, select an explicit streaming media type such as application/x-ndjson or text/event-stream and verify the actual response.

With application/json, Spring WebFlux collects Flux elements into a collection by default before serializing. This is a finite JSON array contract, suitable for Swagger UI to display like a regular JSON response.

## 9. SSE Is an Event Stream Protocol

Server-Sent Events uses the text/event-stream media type. Each event is a UTF-8 text block; common fields are:

| Field | Meaning |
| --- | --- |
| id | Event identifier, usable to resume after reconnecting |
| event | Event type name |
| data | Event content; may be a JSON string |
| retry | Suggested delay before client attempts reconnection |

Lines of an event end with a blank line. Example:

~~~text
id: evt-100
event: order-updated
data: {"orderId":"O-100","status":"SHIPPED"}

id: evt-101
event: order-delayed
data: {"orderId":"O-101","reason":"WEATHER"}

~~~

In WebFlux, you can return Flux<ServerSentEvent<EventMessage>>. If you only need to send data, you can return a publisher of values and declare produces as text/event-stream. ServerSentEvent lets you control id, event, retry, and comments.

Example handler:

~~~java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record EventMessage(String id, String orderId, String status) {
}

@Component
class EventHandler {

    public Mono<ServerResponse> stream(ServerRequest request) {
        Flux<ServerSentEvent<EventMessage>> events =
            Flux.interval(Duration.ofSeconds(1))
                .take(5)
                .map(index -> ServerSentEvent.<EventMessage>builder()
                    .id("evt-" + index)
                    .event("order-progress")
                    .data(new EventMessage(
                        "evt-" + index,
                        "O-100",
                        "STEP-" + index
                    ))
                    .build());

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(events, ServerSentEvent.class);
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        String id = request.pathVariable("id");
        EventMessage event = new EventMessage(id, "O-100", "SHIPPED");

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(event);
    }
}
~~~

The stream above emits only five events and completes, making it suitable for a bounded test call. Production endpoints may stay open until the client disconnects or the data source stops.

## 10. NDJSON Delivers One JSON Record per Line

NDJSON (newline-delimited JSON) uses the application/x-ndjson media type. Each line is an independent JSON document:

~~~text
{"id":"evt-100","orderId":"O-100","status":"PACKING"}
{"id":"evt-101","orderId":"O-100","status":"SHIPPED"}
{"id":"evt-102","orderId":"O-101","status":"CREATED"}
~~~

A WebFlux handler can return Flux<EventMessage> with content type application/x-ndjson:

~~~java
Mono<ServerResponse> sample(ServerRequest request) {
    Flux<EventMessage> records =
        Flux.interval(Duration.ofSeconds(1))
            .take(5)
            .map(index -> new EventMessage(
                "evt-" + index,
                "O-100",
                "STATUS-" + index
            ));

    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(records, EventMessage.class);
}
~~~

WebFlux can encode, write, and flush each element with the NDJSON streaming media type. Clients read line by line, parse each JSON object, and process it immediately without waiting for the entire response to finish.

When documenting NDJSON in OpenAPI, clearly state that the schema represents a single record in the stream and the body contains multiple newline-separated records. Do not describe the body as a JSON array if the server does not send square brackets and array commas.

## 11. Documenting Streaming Responses in OpenAPI

OpenAPI describes responses via status codes, media types, schemas, descriptions, and examples. For SSE, the schema can describe the wire body as text/event-stream and the description explains event framing. For NDJSON, the schema can specify the structure of one record while the description explains that each record is on its own line.

YAML example for SSE:

~~~yaml
responses:
  '200':
    description: Server-Sent Events stream
    content:
      text/event-stream:
        schema:
          type: string
          description: SSE sequence consisting of events separated by blank lines.
        example: |
          id: evt-100
          event: order-updated
          data: {"orderId":"O-100","status":"SHIPPED"}
~~~

YAML example for NDJSON:

~~~yaml
responses:
  '200':
    description: JSON stream, each line is an EventMessage
    content:
      application/x-ndjson:
        schema:
          $ref: '#/components/schemas/EventMessage'
        example: |
          {"id":"evt-100","orderId":"O-100","status":"PACKING"}
          {"id":"evt-101","orderId":"O-100","status":"SHIPPED"}
~~~

In the NDJSON example, the schema references EventMessage to describe each record's structure per documentation conventions. Clarify that the HTTP body is a line-delimited sequence of records, not a single JSON object or a JSON array.

For SSE, the string-typed schema describes the text framing of the response. If you want to describe the JSON payload inside the data field, create a separate schema for the payload and link it via description or component; do not confuse the full SSE frame with a JSON object.

## 12. Swagger UI Is Not a Dedicated SSE/NDJSON Reader

Try it out sends requests through Swagger UI's HTTP client. It displays responses according to how the swagger-client version in use handles response bodies. A non-terminating SSE request can leave the Execute button spinning indefinitely; an NDJSON stream may also appear only after the response completes.

Limitations to keep in mind:

- The UI does not provide a numbered event list with arrival timestamps like a dedicated stream inspector.
- The UI does not guarantee incremental updates as each event arrives.
- With unbounded connections, users may never see a completed response panel.
- Stopping the request or closing the tab may be the only way to end a pending call in some versions.
- Browsers, proxies, and gateways may buffer data even when the server flushes each event.

Swagger UI remains useful for viewing endpoints, media types, descriptions, and examples. Use stream-aware tools to verify arrival timing, ordering, content, and disconnection handling.

## 13. Using cURL to Observe Partial Data

For SSE, use cURL with the -N flag to disable client-side buffering in cURL:

~~~bash
curl -N \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/events/stream
~~~

For NDJSON:

~~~bash
curl -N \
  -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/events/ndjson
~~~

If the endpoint requires a bearer token in a test environment, supply a test token via environment variables or a shell secret store; do not hardcode real tokens directly into docs, committed scripts, or terminal screenshots.

Observing headers:

~~~bash
curl -iN \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/events/stream
~~~

Verify that Content-Type returns the right media type. If cURL only displays data after the stream ends, check the -N option, proxy buffering, compression, and server-side flushing configuration.

## 14. Testing Streams with WebTestClient

WebTestClient can verify status codes, headers, and elements emitted by WebFlux endpoints. For finite streams, you can assert the event count and completion:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class EventStreamTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void emitsFiniteSseEvents() {
        var result = webTestClient.get()
            .uri("/api/events/stream")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
            .returnResult(new ParameterizedTypeReference<
                ServerSentEvent<EventMessage>>() {});

        StepVerifier.create(result.getResponseBody())
            .expectNextCount(5)
            .verifyComplete();
    }
}
~~~

This example demonstrates testing a finite stream. In a real project, import ParameterizedTypeReference and configure WebTestClient to match your application. If the endpoint never terminates, use StepVerifier with thenCancel after receiving the expected number of events and verify cancellation.

For NDJSON, you can read the response body as EventMessage or String depending on codec configuration. Verify both Content-Type and individual records, not just status 200.

## 15. Verifying Routes Generated into OpenAPI

After adding @RouterOperations, fetch the document:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
~~~

Inspect paths:

~~~json
{
  "paths": {
    "/api/events/stream": {
      "get": {
        "operationId": "streamEvents",
        "responses": {
          "200": {
            "content": {
              "text/event-stream": {}
            }
          }
        }
      }
    }
  }
}
~~~

Checklist:

1. Do all routes intended for publishing appear under paths?
2. Do HTTP methods match RouterFunction?
3. Are operationId values unique?
4. Do produces and response content types match runtime media types?
5. Is SSE documented as text/event-stream?
6. Is NDJSON documented as application/x-ndjson?
7. Do schemas and examples explain the structure of each event/record?
8. Are any paths mismatched when multiple routes share a handler?
9. Are appropriate response statuses and errors documented for the route?

If a route does not appear, check whether @RouterOperation(s) is placed on the right RouterFunction bean, whether path/method/produces match the route, and whether operationId is declared. If one annotation could match multiple routes, add method, produces, or consumes criteria to identify it uniquely.

## 16. Separating Documentation Errors from Streaming Runtime Errors

An operation that renders properly in Swagger UI while failing to stream can stem from the HTTP/runtime layer:

| Symptom | Possible Cause to Check |
| --- | --- |
| No events appear | Accept header, Content-Type, handler, Flux source, or error before response commit |
| Events only appear when the stream ends | Buffering at proxy, gateway, compression layer, or client |
| Swagger UI waits forever | Infinite stream and UI is waiting for response body completion |
| cURL prints everything at once | Missing -N or an intermediate layer is buffering |
| Client gets a JSON array instead of individual lines | Server uses application/json instead of a streaming media type |
| Connection closes unexpectedly | Timeout, idle timeout, source error, client cancel, or proxy |
| Client misses events after reconnect | Missing id/Last-Event-ID or resume logic |
| Route missing from OpenAPI | Missing @RouterOperation(s), mismatched path, or missing operationId |

Do not alter schemas to fix proxy buffering issues. Do not adjust server timeouts just so Swagger UI completes a stream designed to stay open long-term.

## 17. Timeouts, Heartbeats, and Connection Cancellation

A long-lived stream must handle client disconnections and infrastructure idle-connection closures:

- Use periodic heartbeats if allowed by the protocol and business requirements.
- With SSE, emit comment events or heartbeat events to keep connections alive and detect disconnected clients.
- Observe subscription cancellation to stop upstream work when clients cancel.
- Configure timeouts consistently across server, gateway, and load balancer to match expected stream durations.
- Do not hold connections open indefinitely if the business case only requires a finite dataset.
- For resumable SSE, emit stable event IDs and handle Last-Event-ID.

If a stream is only for preview or manual testing, create a sample endpoint with a bounded number of events that completes on its own. Production endpoints can continue running long-term as designed.

## 18. Browser Limitations and CORS

Swagger UI runs inside the browser. If the Swagger UI page and the API are on different origins, requests may require CORS. Try it out being blocked by the browser is not necessarily an OpenAPI error.

With SSE:

- Native EventSource primarily uses GET and does not allow arbitrary Authorization headers.
- If the API requires a bearer token in headers, use fetch streaming or an SSE client that supports headers.
- Cookies can be sent according to same-site/credentials policies and appropriate CORS setup.
- Do not place sensitive tokens in query strings just for EventSource compatibility, because URLs can appear in logs and history.

With NDJSON, you can use fetch and read response.body with a stream reader. Ensure CORS allows the required methods/headers and exposes any response headers clients need to read.

## 19. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Functional route missing from Swagger UI | Missing @RouterOperation or @RouterOperations | Add annotations for routes and operationIds |
| Multiple routes produce only one operation | Single @RouterOperation used for a multi-route RouterFunction | Use @RouterOperations and declare path per route |
| Route matches wrong metadata | Path/method/produces do not uniquely identify the route | Add route-matching attributes |
| Flux does not stream incrementally | Using application/json or a non-streaming media type | Choose NDJSON or SSE and verify codecs |
| Try it out hangs | Endpoint is a long-lived stream | Use cURL -N or a stream-capable client |
| Stream appears only after completion | UI/client or proxy buffers the response | Test with a stream-aware client and inspect proxy config |
| Disabling Try it out still shows the operation | supported-submit-methods only disables Execute | This is expected behavior; use security to protect endpoints |
| Endpoint is still callable via cURL | Swagger UI config does not block server requests | Protect routes with Spring Security/gateway |
| Response schema wrongly shows an array | Collection schema used for an NDJSON body | Document individual records and line-delimiting rules |
| SSE events lack resume info | Not emitting id or not handling Last-Event-ID | Design event IDs and a resume policy |

## 20. Workflow for Designing WebFlux Docs and Try-It-Out

1. Determine whether the route is a finite response, SSE, or NDJSON.
2. Choose a media type matching the actual wire format.
3. Declare RouterFunction and handlers with the right method, path, and produces.
4. Use @RouterOperation or @RouterOperations to document routes; assign unique operationIds.
5. Document response content, schemas, and examples matching the wire format.
6. Use try-it-out-enabled and supported-submit-methods to control the UI try-it-out experience.
7. Keep endpoint security in Spring Security/gateway; do not rely on UI restrictions.
8. Use Swagger UI for finite requests and reviewing contracts.
9. Use cURL -N, WebTestClient, or a stream-aware client to inspect individual events.
10. Verify timeouts, heartbeats, cancellation, CORS, and proxy buffering.

By separating the OpenAPI contract, try-it-out permissions, and streaming protocols, integrators can understand WebFlux endpoints accurately and pick the right tools. Swagger UI helps explore and test APIs; verifying data arriving event by event requires a client capable of reading streams.

## References

- [springdoc-openapi v2 – WebFlux/WebMvc.fn Functional Endpoints](https://springdoc.org/v2/features.html)
- [Swagger UI – Configuration: tryItOutEnabled and supportedSubmitMethods](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework – WebFlux Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html)
- [Spring Framework – Reactive Core, Jackson JSON and Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [MDN – Using Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [Swagger UI – SSE support discussion](https://github.com/swagger-api/swagger-ui/issues/4761)
