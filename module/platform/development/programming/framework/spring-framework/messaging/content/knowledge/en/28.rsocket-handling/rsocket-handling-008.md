# `@MessageExceptionHandler` and RSocket Handler Error Mapping

## Objectives

After this lesson, you will be able to handle errors raised in RSocket `@MessageMapping` methods, map exceptions to a stable error structure, distinguish business errors in responses from RSocket protocol errors, and choose the right local or global handling scope.

## 1. Where Do Errors Occur in an RSocket Handler?

In Spring Messaging, `RSocketMessageHandler` finds and invokes `@MessageMapping` methods by route. A handler can:

- Throw an exception directly when validating input or executing synchronous logic.
- Return a `Mono` or `Flux` and emit an error signal inside the reactive pipeline.
- Complete normally and return a payload according to the chosen interaction model.

If errors are not handled appropriately, an exception can become an RSocket-level request error. The requester receives an error signal through the reactive publisher. This differs from the handler actively converting a business error into a response DTO.

`@MessageExceptionHandler` is the annotation accompanying the `@MessageMapping` model. It marks a method that handles exceptions raised when invoking message handlers. The annotation belongs to the package:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
~~~

It belongs to Spring Messaging and does not depend on whether RSocket runs over TCP or WebSocket. With RSocket, these methods execute within the annotated responder infrastructure provided by `RSocketMessageHandler`.

## 2. Declaring Which Exceptions to Handle

There are two ways to declare the exception types:

**Declare directly on the annotation**

~~~java
@MessageExceptionHandler(OrderNotFoundException.class)
public OrderResult handleNotFound(OrderNotFoundException exception) {
    return OrderResult.failure("ORDER_NOT_FOUND", "Order not found");
}
~~~

**Let Spring infer from the exception parameter**

~~~java
@MessageExceptionHandler
public OrderResult handleInvalidQuery(InvalidOrderQueryException exception) {
    return OrderResult.failure("INVALID_QUERY", "Invalid query data");
}
~~~

If the annotation attribute is left empty, the exception types in the parameter list are used as the handled types. Multiple types can be declared in the annotation:

~~~java
@MessageExceptionHandler({
        InvalidOrderQueryException.class,
        IllegalArgumentException.class
})
public OrderResult handleInvalidInput(Exception exception) {
    return OrderResult.failure("INVALID_INPUT", "Invalid request data");
}
~~~

The exception parameter lets you inspect the details needed to decide how to map it. Exception-handler methods also support the same parameter and return types as `@MessageMapping` methods, including appropriate reactive types.

## 3. Scope of Exception Handlers

### Handling Within the Same Controller

By default, `@MessageExceptionHandler` applies to message handler methods within the same `@Controller` class and its class hierarchy. This is appropriate when an error only makes sense for a specific group of routes.

~~~java
@Controller
public class OrderRSocketController {

    @MessageMapping("orders.find")
    public Mono<OrderResult> find(OrderQuery query) {
        // Order lookup logic
        return Mono.empty();
    }

    @MessageExceptionHandler(OrderNotFoundException.class)
    public Mono<OrderResult> handleNotFound(OrderNotFoundException exception) {
        return Mono.just(
                OrderResult.failure(
                        "ORDER_NOT_FOUND",
                        "Order not found"
                )
        );
    }
}
~~~

### Shared Handling with `@ControllerAdvice`

When multiple RSocket controllers need the same error policy, `@MessageExceptionHandler` can be placed in a class annotated with `@ControllerAdvice`.

~~~java
@ControllerAdvice
public class RSocketGlobalExceptionAdvice {

    @MessageExceptionHandler(InvalidOrderQueryException.class)
    public OrderResult handleInvalidQuery(InvalidOrderQueryException exception) {
        return OrderResult.failure(
                "INVALID_QUERY",
                "Invalid query data"
        );
    }
}
~~~

Spring Boot auto-configures the Spring Messaging infrastructure for RSocket and supports `@ControllerAdvice` for exception handling. Messaging advice registration support in Spring Framework has been available since version 5.3.5. If creating `RSocketMessageHandler` manually outside Spring Boot auto-configuration, register the appropriate advice via `registerMessagingAdvice(...)`; `spring-messaging` does not depend directly on `spring-web` to automatically pick up every `@ControllerAdvice` style.

## 4. Designing an Application Error Contract

Do not send raw exceptions or stack traces to the client. Convert business errors into a structure with stable fields, for example:

~~~java
public record ErrorInfo(
        String code,
        String message
) {
}
~~~

For Request-Response, use the same response type for both success and failure cases. That way the client only needs to decode a single data type:

~~~java
public record OrderQuery(String orderId) {
}

public record OrderView(
        String orderId,
        String status
) {
}

public record OrderResult(
        OrderView data,
        ErrorInfo error
) {
    public static OrderResult success(OrderView data) {
        return new OrderResult(data, null);
    }

    public static OrderResult failure(String code, String message) {
        return new OrderResult(
                null,
                new ErrorInfo(code, message)
        );
    }
}
~~~

Conventions of this example:

- Success: `data` has a value, `error` is `null`.
- Mapped business failure: `data` is `null`, `error` contains a stable code and message.
- Protocol error or error outside the mapping policy: the requester receives an error signal rather than a normal `OrderResult`.

Codes such as `ORDER_NOT_FOUND`, `INVALID_QUERY`, and `INTERNAL_ERROR` are application-defined business codes, not HTTP status codes. Keep codes stable so clients can handle them without relying on display text wording.

## 5. Complete Example: Mapping `OrderNotFoundException`

Suppose the order lookup service returns `Mono<OrderView>`. When no order is found, the service emits `Mono.empty()`. The handler converts that case into a business exception for a `@MessageExceptionHandler` method to process.

### 5.1. Exception

~~~java
public final class OrderNotFoundException extends RuntimeException {

    private final String orderId;

    public OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

### 5.2. Service Contract

~~~java
import reactor.core.publisher.Mono;

public interface OrderService {
    Mono<OrderView> findById(String orderId);
}
~~~

### 5.3. RSocket Controller

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderResult> find(OrderQuery query) {
        return orderService.findById(query.orderId())
                .map(OrderResult::success)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(query.orderId())
                ));
    }

    @MessageExceptionHandler(OrderNotFoundException.class)
    public Mono<OrderResult> handleNotFound(
            OrderNotFoundException exception) {

        return Mono.just(OrderResult.failure(
                "ORDER_NOT_FOUND",
                "Order not found"
        ));
    }
}
~~~

Explanation:

1. `@MessageMapping("orders.find")` maps requests with route `orders.find` to the `find` method.
2. `findById(...)` returns a publisher so lookup executes within the reactive pipeline.
3. `switchIfEmpty(Mono.error(...))` turns a missing order into an error signal. It does not subscribe on its own and does not block.
4. When a matching exception is emitted during handler execution, Spring locates the corresponding `@MessageExceptionHandler` method.
5. The handler method returns a failure `OrderResult`. For Request-Response, this is a normal response payload for the request, not an RSocket ERROR frame.

In this example, `OrderQuery`, `OrderView`, `ErrorInfo`, `OrderResult`, `OrderService`, and `OrderNotFoundException` are application-specific types. Place each `public` type in its identically named Java file when splitting into an actual project.

### 5.4. Client Calling the Route

~~~java
Mono<OrderResult> result = requester
        .route("orders.find")
        .data(new OrderQuery("ORD-42"))
        .retrieveMono(OrderResult.class);
~~~

The client reads `OrderResult`:

- If `result.data()` is non-`null`, process the order data.
- If `result.error()` is non-`null`, handle the business error code.
- If the publisher emits `onError`, handle the RSocket error or unmapped error.

Using a unified response envelope keeps the client from having to guess whether the response is `OrderView` or `ErrorInfo` depending on the server outcome.

## 6. Two Ways to Propagate Errors to the Requester

Clearly distinguish the following two contracts.

| Handling approach | What the requester receives | How the client handles it |
|---|---|---|
| `@MessageExceptionHandler` returns a DTO | A normal response payload if the interaction has a response | Decode the DTO and inspect `error.code` |
| Exception continues to be emitted | A request error signal propagated via RSocket | Handle via `onErrorResume`, `doOnError`, or an equivalent mechanism |

### Mapping to a Response DTO

This is appropriate when the error is part of the business contract. For example: order does not exist, invalid input data, or business state does not allow the operation.

The advantage is that the client receives a structure with a stable error code. However, at the protocol layer, the request completed with a normal response. The client must check the `error` field; it cannot rely solely on `onError` to detect this business error.

### Keeping Errors at the Protocol Layer

If no matching exception handler exists, or the handler itself returns an error publisher, the request still fails and the requester receives an error signal.

~~~java
Mono<OrderResult> result = requester
        .route("orders.find")
        .data(new OrderQuery("ORD-42"))
        .retrieveMono(OrderResult.class)
        .doOnError(error ->
                log.warn("RSocket request failed", error)
        );
~~~

This is appropriate for errors preventing request completion, such as unexpected processing failures or errors that should be governed by client retry/timeout policies. Do not assume that server-side Java exception classes will be transferred intact to a client JVM; rely on the protocol error contract and stable information intentionally sent by the application.

## 7. Errors in a Reactive Pipeline

For handlers returning `Mono` or `Flux`, exceptions can arise after the method has returned the publisher. Keep errors within the same reactive chain:

~~~java
@MessageMapping("orders.create")
public Mono<OrderResult> create(CreateOrder command) {
    return orderService.create(command)
            .map(OrderResult::success)
            .onErrorMap(
                    DuplicateOrderException.class,
                    ex -> new OrderConflictException(command.orderId())
            );
}
~~~

An exception transformed within the pipeline can be mapped by `@MessageExceptionHandler` if the final exception type matches a declared handler.

Do not call `subscribe()` yourself inside `@MessageMapping` just to trigger work:

~~~java
@MessageMapping("orders.create")
public void create(CreateOrder command) {
    orderService.create(command).subscribe();
}
~~~

That style detaches the work from the request lifecycle. The framework no longer receives a publisher representing the processing to manage completion and errors for that request. Return `Mono` or `Flux` from the handler.

Also do not silently replace errors with `Mono.empty()` if the client needs to know the operation failed. When using `onErrorResume`, convert intentionally to a response envelope or propagate the error according to the chosen contract.

## 8. Choices by Interaction Model

`@MessageExceptionHandler` does not change the interaction nature of a request.

| Interaction | Error design notes |
|---|---|
| Request-Response | Can return an error envelope as the response payload for the client to inspect |
| Request-Stream | An error can terminate the stream; if errors must be represented as part of the data, clearly design the element type and stream termination behavior |
| Channel | Need to define whether an error applies to the entire interaction or a single stream element; maintain the convention on both sides |
| Fire-and-Forget | No response payload for the requester to read an error DTO; rely on logs, metrics, events, or a separate confirmation route |

In particular, do not use the return value of an exception handler as an ACK for Fire-and-Forget. If the sender needs to know whether the server succeeded or failed in business processing, choose Request-Response or design a separate confirmation mechanism with a correlation ID.

## 9. Error Classification and Mapping Policy

A practical policy can classify errors as follows:

| Error category | Suggested application code | Behavior |
|---|---|---|
| Malformed input or missing data | `INVALID_REQUEST` | Return an error envelope with a displayable message |
| Resource not found | `NOT_FOUND` | Return an error envelope with a stable error identifier |
| Business rule violation | `BUSINESS_RULE_VIOLATION` | Return a controlled business error |
| Insufficient permissions | `FORBIDDEN` | Do not disclose sensitive resource details |
| Unexpected error | `INTERNAL_ERROR` | Log full details on server, return generic message or let error propagate per protocol policy |
| Connection loss, requester timeout | Not a business exception handler code | Handle at the client/transport layer |

Do not return `exception.getMessage()` by default for all error types. Exception messages may contain SQL, table names, internal paths, tokens, or infrastructure details. Log full details on the server, generate a correlation ID if tracing is needed, and send only information permitted for disclosure.

## 10. Common Implementation Mistakes

**Mistakenly using Spring MVC/WebFlux's `@ExceptionHandler`**

`@ExceptionHandler` handles exceptions in HTTP controller flows. For Spring Messaging methods annotated with `@MessageMapping`, use `@MessageExceptionHandler`.

**Defining a global handler without registration infrastructure**

A `@ControllerAdvice` class is only useful when the RSocket message handler receives that messaging advice. Spring Boot auto-configuration supports this setup; if configuring `RSocketMessageHandler` manually, verify advice registration.

**Catching only synchronous exceptions**

A handler can return `Mono` or `Flux`. Errors emitted later still need to stay inside the returned publisher for the framework to handle. Do not detach work via `subscribe()` and expect the request's exception handler to catch errors from an independent subscription.

**Returning two inconsistent DTO types**

If success returns `OrderView` while errors return `ErrorInfo`, a client decoding a fixed type will have difficulty handling both. Use a common envelope or leave errors at the protocol layer.

**Treating an error envelope as a protocol error**

When an exception handler returns a DTO, the requester receives a normal response. If the client only attaches `onErrorResume` without inspecting the `error` field, mapped business errors will be missed.

**Expecting exception handlers to catch all connection errors**

This annotation serves message handler exceptions. It does not replace handling connection failures, timeouts, request cancellations, or transport errors on the requester side.

## 11. Testing

Test at least three cases using integration tests with a real RSocket requester/responder and Reactor Test (`StepVerifier`):

1. Route succeeds: requester receives an envelope with `data` and no `error`.
2. Route throws `OrderNotFoundException`: exception handler executes and requester receives an envelope with code `ORDER_NOT_FOUND`.
3. Route emits an unhandled exception: requester receives an error signal, not a fake success envelope.

For Request-Stream or Fire-and-Forget, add dedicated tests for the corresponding interaction. Do not extrapolate the behavior of one interaction from a Request-Response test.

Example verifying a response envelope:

~~~java
StepVerifier.create(
        requester.route("orders.find")
                .data(new OrderQuery("missing"))
                .retrieveMono(OrderResult.class)
)
.expectNextMatches(result ->
        result.data() == null
                && result.error() != null
                && "ORDER_NOT_FOUND".equals(result.error().code())
)
.verifyComplete();
~~~

This test proves the client receives a response payload containing a business error and the publisher completes normally. It does not prove that a request failing at the protocol level would also complete normally.

## 12. Checklist

- [ ] Use `@MessageExceptionHandler` for `@MessageMapping` exceptions.
- [ ] Explicitly declare exception types in the annotation or method parameter.
- [ ] Choose local scope or global scope via `@ControllerAdvice`.
- [ ] Confirm `RSocketMessageHandler` receives global advice.
- [ ] Use stable error codes and messages that do not leak internal details.
- [ ] Keep errors inside the reactive pipeline and return the publisher to the framework.
- [ ] Distinguish error envelopes from RSocket error signals.
- [ ] Design according to the interaction model; do not use Fire-and-Forget to expect an ACK.
- [ ] Test both mapped errors and unhandled errors.

## References

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketMessageHandler`, annotated responders, `@MessageMapping`, interaction models, and return types.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): Spring Messaging auto-configuration and `@ControllerAdvice` support.
- [Spring Framework Javadoc — MessageExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageExceptionHandler.html): `value` attribute and annotation contract.
- [Spring Framework Javadoc — MessageMappingMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/MessageMappingMessageHandler.html): registering global messaging advice.
