# Request-Response and a Single Response Result

## Objectives

RSocket supports multiple interaction styles between two endpoints of a connection. With **Request-Response**, the sender sends one request and awaits exactly one response result for that request. In Spring Framework, the receiving side can be implemented with a `@MessageMapping` method returning a single value or `Mono<T>`, and the sending side is invoked with `RSocketRequester.retrieveMono(...)`.

This lesson explains:

- How Request-Response works in the RSocket protocol.
- When to choose Request-Response instead of Request-Stream, Channel, or Fire-and-Forget.
- How to map requests and responses with `@MessageMapping`.
- How to call a route from the client using `RSocketRequester` and receive a `Mono<T>`.
- How to configure routes, codecs, MIME types, and error handling.
- Limitations to keep in mind when using a single response result in reactive applications.

## 1. Request-Response in RSocket

RSocket is a bidirectional, asynchronous communication protocol supporting multiplexing over a TCP connection, WebSocket, or another byte-stream transport. Once the connection is established, both sides can initiate requests. Therefore, in RSocket terminology, the party sending a request is called the **requester**, and the party handling the request is the **responder**; these roles do not necessarily coincide with client and server at the transport layer.

With Request-Response:

1. The requester sends a message containing the request data.
2. The responder processes the request.
3. The responder sends back a single message containing the sole result, or terminates the request with an error.
4. The request ends once the requester receives the response or error. The requester can also cancel an awaiting request.

At the protocol layer, the operation begins with a `REQUEST_RESPONSE` frame. The responder returns a `PAYLOAD` that completes the stream or an `ERROR`. Each request has its own stream ID, so many request-response calls can run concurrently on a single RSocket connection without opening a TCP connection per request.

This can be visualized as:

~~~text
Requester                              Responder
    |                                      |
    |------ REQUEST_RESPONSE -------------->|
    |          request payload              |
    |                                      | processing
    |<------------- PAYLOAD ----------------|
    |          response payload             |
    |                                      |
    |          request completed            |
~~~

Request-Response is suited for operations with a single clear result, such as:

- Looking up product information by code.
- Fetching a user profile by ID.
- Calculating a transaction fee and returning a single result.
- Checking order status at a point in time.
- Sending a command that needs the processing outcome immediately within the same interaction.

Do not use this style if the responder needs to emit multiple results over time. In that case, Request-Stream is a better fit.

## 2. Comparing Interaction Types

RSocket defines four main request types:

| Interaction type | Data sent | Data received | Best suited for |
| --- | --- | --- | --- |
| Request-Response | One message | One response | Lookups or processing needing a single result |
| Request-Stream | One message | A stream of responses | Tracking continuously changing prices, locations, or statuses |
| Channel | A stream of requests | A stream of responses | Continuous data exchange in both directions |
| Fire-and-Forget | One message | No response | Sending events or commands not needing a direct result |

Example with the same lookup domain:

- Request-Response: send a product code and receive one product record.
- Request-Stream: send criteria and receive matching products sequentially.
- Channel: client sends positions continuously while the server concurrently sends computed results.
- Fire-and-Forget: send an event recording an action where the caller needs no response in that interaction.

Do not pick an interaction type solely based on whether the payload is an object. Base the choice on the number of input messages and the number of results the business case actually requires.

## 3. Mapping Request-Response in Spring

Spring uses the cardinality (number of elements) of the request and response to determine the interaction type when handling methods annotated with `@MessageMapping`.

| Input cardinality | Output cardinality | Interaction type |
| --- | --- | --- |
| 0 or 1 | 0 | Fire-and-Forget or Request-Response |
| 0 or 1 | 1 | Request-Response |
| 0 or 1 | Many | Request-Stream |
| Many | 0, 1, or many | Request-Channel |

In this table:

- Cardinality `1`: a concrete value or a single-value publisher such as `Mono<T>`.
- Cardinality `Many`: a multi-value publisher such as `Flux<T>`.
- Cardinality `0`: no input payload, or a method returning no data such as `void` or `Mono<Void>`.

To implement a request with a payload and a single response, use one input value and one output value. A common approach is to accept a DTO and return `Mono<DTO>`.

Example:

~~~java
@Controller
public class ProductRSocketController {

    private final ProductService productService;

    public ProductRSocketController(ProductService productService) {
        this.productService = productService;
    }

    @MessageMapping("products.find-by-id")
    public Mono<ProductResponse> findById(ProductRequest request) {
        return productService.findById(request.productId())
                .map(product -> new ProductResponse(
                        product.id(),
                        product.name(),
                        product.price()
                ));
    }
}
~~~

The `findById` method accepts one `ProductRequest` and returns `Mono<ProductResponse>`. Because the input is one message and the output is a single-valued result, Spring maps this method to Request-Response.

If the method returns `Flux<ProductResponse>`, Spring interprets the output as multiple results and the matching interaction becomes Request-Stream. Do not change `Mono` to `Flux` merely to use a reactive API; the publisher type expresses the number of results the contract provides.

## 4. Building Request and Response DTOs

Example using Java 17 records:

~~~java
import java.math.BigDecimal;

public record ProductRequest(String productId) {
}

public record ProductResponse(
        String productId,
        String name,
        BigDecimal price
) {
}
~~~

Request and response are two distinct data types. Separating DTOs keeps the API contract clear and avoids returning internal persistence-layer entities directly.

A response should contain the fields the caller needs to complete the business operation. If you need to represent a business outcome such as product not found, you can define an explicit status field or result type. Avoid forcing callers to infer outcomes from arbitrary null fields.

Extended response example:

~~~java
public record ProductLookupResponse(
        boolean found,
        String productId,
        String name,
        BigDecimal price,
        String message
) {
}
~~~

With this contract, “product not found” can be a valid business result. Infrastructure errors or unexpected processing failures should still be represented via error signals.

## 5. Sending Requests with RSocketRequester

`RSocketRequester` provides a fluent API to construct requests and receive responses as Java objects rather than manipulating byte buffers and protocol frames manually.

Example requester connecting over TCP:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 7000);
~~~

This creates a requester configured to connect to the TCP server on port `7000`. According to the builder's behavior, the connection is established when the first request is executed; it does not necessarily open the connection at requester creation time.

Executing a Request-Response:

~~~java
import reactor.core.publisher.Mono;

Mono<ProductResponse> response =
        requester
                .route("products.find-by-id")
                .data(new ProductRequest("P-100"))
                .retrieveMono(ProductResponse.class);
~~~

Meaning of each step:

- `route("products.find-by-id")` sets the request route in metadata.
- `data(...)` supplies a single input payload.
- `retrieveMono(ProductResponse.class)` declares the expected data type and performs Request-Response.

`retrieveMono(...)` returns `Mono<ProductResponse>`. This is a lazy publisher: the request is usually only executed when the publisher is subscribed to or composed into a reactive chain with a subscriber.

In reactive applications, return the publisher to the calling layer or compose it with operators:

~~~java
public Mono<ProductResponse> getProduct(String productId) {
    return requester
            .route("products.find-by-id")
            .data(new ProductRequest(productId))
            .retrieveMono(ProductResponse.class);
}
~~~

At an imperative integration boundary, `block()` can be used to wait for the result, but do not block on event-loop threads or inside a reactive pipeline:

~~~java
ProductResponse result = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class)
        .block();
~~~

The last snippet is only suitable at a controlled imperative boundary; WebFlux code or reactive services should keep the `Mono<T>` return type.

## 6. Configuring the Responder and RSocket Server

For `@MessageMapping` methods to be discovered, Spring requires `RSocketMessageHandler`. Example handler configuration in Spring Framework:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
public class RSocketServerConfiguration {

    @Bean
    RSocketMessageHandler rsocketMessageHandler(
            RSocketStrategies strategies) {

        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRSocketStrategies(strategies);
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
~~~

`RSocketMessageHandler` detects controller beans with `@MessageMapping` methods and builds the responder for the RSocket server. `PathPatternRouteMatcher` is Spring's recommended choice when the `spring-web` module is present.

At the Java RSocket API level, the handler is attached to the server:

~~~java
RSocketMessageHandler handler =
        applicationContext.getBean(RSocketMessageHandler.class);

CloseableChannel server = RSocketServer.create(handler.responder())
        .bind(TcpServerTransport.create("localhost", 7000))
        .block();
~~~

This is an illustrative bind snippet. In real applications, manage the `CloseableChannel` lifecycle alongside the ApplicationContext lifecycle and close the server on application shutdown. If using Spring Boot, the RSocket server can be auto-configured via `spring-boot-starter-rsocket` and `spring.rsocket.server` properties; in that case, manual binding as above is unnecessary.

## 7. Routes and Metadata

A route is a logical address used by the responder to find the handler method. In the example, the route is `products.find-by-id`. It is transmitted as RSocket message metadata, not an HTTP URL path.

Key points to remember:

- The route must match between `RSocketRequester.route(...)` and `@MessageMapping`.
- Routes can be hierarchical, commonly using dots as separators.
- `SimpleRouteMatcher` uses `AntPathMatcher` by default; `PathPatternRouteMatcher` can be used when `spring-web` is present.
- RSocket's route matcher does not process routes like URL paths and does not perform HTTP-style URL decoding.
- Routes do not replace authentication or authorization. The server must still verify the caller and data access permissions.

Routes with variables can be declared:

~~~java
@Controller
public class ProductRSocketController {

    @MessageMapping("products.{productId}.details")
    public Mono<ProductResponse> details(
            @DestinationVariable String productId) {

        return productService.findById(productId)
                .map(product -> new ProductResponse(
                        product.id(),
                        product.name(),
                        product.price()
                ));
    }
}
~~~

The requester calls the corresponding route:

~~~java
Mono<ProductResponse> response = requester
        .route("products.P-100.details")
        .retrieveMono(ProductResponse.class);
~~~

Use a payload DTO when the request has multiple fields or needs an extensible contract. Use a destination variable when the value is genuinely part of routing.

## 8. Serialization, Codecs, and MIME Types

RSocket transmits data and metadata as byte buffers. Spring requires encoders and decoders to convert Java objects to payloads and vice versa.

By default, `RSocketStrategies` only includes basic codecs from `spring-core` for `String`, `byte[]`, and `ByteBuffer`. When passing DTOs like `ProductRequest` and `ProductResponse`, the application needs appropriate codecs, typically from the `spring-web` module such as Jackson JSON or CBOR codecs.

Both sides must agree on serialization:

- Data MIME type describes the payload format, such as JSON or CBOR.
- Metadata MIME type describes how metadata is encoded. By default, composite metadata is typically used to carry multiple metadata types on the same request.
- MIME types are declared in the SETUP frame and apply to the connection.
- Routing and security metadata can use dedicated metadata formats; do not mix metadata with the business payload.

Example configuring strategies with Jackson CBOR codecs:

~~~java
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.http.codec.cbor.JacksonCborEncoder;
import org.springframework.http.codec.cbor.JacksonCborDecoder;

RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
        .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
        .build();
~~~

Compatible configurations must be applied to both requester and responder. If an encoder or decoder does not support the data type or selected MIME type, the request can fail during the encode/decode step.

Spring Boot with `spring-boot-starter-rsocket` can auto-configure `RSocketStrategies` along with Jackson CBOR/JSON codecs. With plain Spring Framework, register appropriate encoders/decoders and configure shared strategies for `RSocketRequester` and `RSocketMessageHandler`.

## 9. Error Handling and Timeouts

Request-Response can end with a response or an error. On the requester side, errors from the responder or transport errors are translated into a Reactor `Mono` error signal.

A timeout can be set on the calling side:

~~~java
import java.time.Duration;

Mono<ProductResponse> response = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class)
        .timeout(Duration.ofSeconds(3));
~~~

`timeout` emits an error if no result arrives within the specified duration. Choose timeouts based on SLAs and actual business latency; a timeout that is too short causes false failures under heavy load, whereas one that is too long holds requests and resources longer than necessary.

Errors can be handled with Reactor:

~~~java
Mono<ProductResponse> response = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class)
        .onErrorResume(error -> {
            log.warn("Product lookup failed", error);
            return Mono.error(
                    new ProductLookupException("Unable to look up product", error));
        });
~~~

In this example, the error is converted into an application-layer exception. For expected business outcomes, a response with an explicit status can be returned; for unexpected errors, system errors, or communication failures, preserve the error signal so the caller can retry, log, or return an appropriate error.

Do not include stack traces, SQL messages, or sensitive internal details in responses sent to callers. Map exceptions to stable error codes and messages.

## 10. Request Cancellation and Limits of a Single Response

Because the requester receives the result as `Mono<T>`, cancelling the subscription can cancel the pending request on the RSocket side. The protocol provides a `CANCEL` frame allowing the requester to signal that the response is no longer needed. The responder should stop cancellable work if the business logic and implementation support it.

However, cancelling a request does not mean all side effects have been rolled back. If the responder has already started writing data or calling external systems, cancellation may arrive after the side effect has occurred. For write commands or critical transactions, proper transactions and idempotency are required.

Request-Response has only one response. If multiple results are needed, do not pack many elements into one giant object merely to keep this interaction type; consider Request-Stream. If continuous bidirectional exchange is needed, consider Channel.

## 11. Testing Request-Response

Both responder logic and actual RSocket connectivity should be tested.

### Unit Testing the Handler

Handler methods can be tested with Reactor Test:

~~~java
@Test
void returnsProductDetails() {
    ProductRequest request = new ProductRequest("P-100");

    StepVerifier.create(controller.findById(request))
            .expectNextMatches(response ->
                    response.productId().equals("P-100"))
            .verifyComplete();
}
~~~

This test verifies that the handler's reactive logic returns one result and completes. It does not yet verify route mapping, transport, serialization, or the RSocket protocol.

### Integration Testing

An integration test should:

1. Start the RSocket server on an appropriate TCP or WebSocket transport.
2. Create an `RSocketRequester` pointing to the server.
3. Send a request to the target route with the input DTO.
4. Use `StepVerifier` to assert that exactly one response is received and the publisher completes.
5. Verify error behavior when the route does not exist or the responder throws an exception.
6. Verify encode/decode failures if the two sides configure incompatible MIME types or codecs.
7. Test timeouts and cancellation in reproducibly stable scenarios.

Example asserting a single element:

~~~java
StepVerifier.create(
        requester.route("products.find-by-id")
                .data(new ProductRequest("P-100"))
                .retrieveMono(ProductResponse.class)
)
.expectNextMatches(response ->
        response.productId().equals("P-100"))
.verifyComplete();
~~~

`expectNextMatches` combined with `verifyComplete` verifies that the publisher emits one matching result and then terminates. If multiple results are received, a `Mono` publisher cannot emit them as a multi-element stream.

## 12. Common Pitfalls

### Route Finds No Handler

Check whether the route string in `requester.route(...)` matches `@MessageMapping`. Verify that `RSocketMessageHandler` is registered, the controller is inside the ApplicationContext, and the route matcher is configured properly.

### retrieveMono Fails with a Multi-Element Request Publisher

Request-Response is a single-request input and single-response output model. `retrieveMono` does not support multi-valued input publishers like `Flux<T>`. If sending multiple request elements, use Request-Channel or another suitable interaction.

### Unable to Serialize DTO

Verify that encoders/decoders support the DTO class and MIME type. Default codecs only handle basic types; DTOs require codecs such as Jackson JSON/CBOR or custom codecs. Ensure requester and responder use compatible formats.

### Client Waits Forever Without a Response

Check whether the responder actually returns a single value, whether it hangs on a reactive dependency, and whether a requester-side timeout is set. Avoid creating publishers that never emit a terminal signal.

### Calling block() Inside a Reactive Pipeline

`block()` blocks the thread waiting for a result. Calling it on an event-loop thread can cause stalls or runtime errors. Keep data in `Mono<T>` and compose with reactive operators.

### Retries Causing Duplicate Processing

If a timeout occurs after the responder has performed a side effect but before the caller receives the response, the caller cannot be sure whether the operation completed. Retrying may execute the business operation a second time. For write commands, send a request ID/idempotency key and deduplicate on the responder.

## 13. Usage Guidelines

- Use Request-Response when each request has exactly one business result.
- Use `Mono<T>` for a single-value response; use `Flux<T>` when a stream of multiple results is needed.
- Use clear and consistent routes between requester and responder.
- Use separate DTOs for requests and responses to keep contracts stable.
- Configure identical encoders/decoders and MIME types on both sides.
- Set timeouts matching SLAs and handle error signals.
- Avoid `block()` inside reactive pipelines.
- Do not blindly retry requests with side effects; use idempotency keys.
- Do not confuse receiving a response with distributed transactions or exactly-once guarantees.
- Test routes, codecs, errors, timeouts, and transports with integration tests.

## 14. Summary

Request-Response is an interaction where the requester sends one message and receives a single response or an error. In Spring Framework, the responder is typically a `@MessageMapping` method taking a payload and returning a value or `Mono<T>`. The requester calls the route via `RSocketRequester` and uses `retrieveMono(ResponseType.class)` to perform Request-Response.

Core pattern:

~~~java
Mono<ProductResponse> response = requester
        .route("products.find-by-id")
        .data(new ProductRequest("P-100"))
        .retrieveMono(ProductResponse.class);
~~~

To work properly, both sides must agree on the route, payload types, encoders/decoders, and MIME types. Keep results reactive, handle timeouts and errors explicitly, and design idempotency for requests with side effects.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Javadoc — RSocketRequester.RetrieveSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.RetrieveSpec.html)
- [RSocket Protocol — Request-Response](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
