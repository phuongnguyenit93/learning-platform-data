# WebExceptionHandler for Out-of-Controller Errors in Spring WebFlux

## 1. Why Is an Error-Handling Layer Outside the Controller Needed?

Spring WebFlux involves multiple layers when processing an HTTP request: the server adapter, the \`WebFilter\` chain, \`WebHandler\` (typically \`DispatcherHandler\`), handler mapping, the controller or functional endpoint, and finally writing the response. An exception can arise at any layer.

For example:

- A \`WebFilter\` validates a token and encounters an error while calling an authentication service.
- A filter that logs or reads metadata fails before the request is dispatched to a controller.
- An infrastructure component resolving tenant, session, or routing information throws an exception.
- A handler mapping or functional endpoint raises an error.
- A controller returns a \`Mono\` whose publisher emits \`onError\` after the method has returned.
- A response write operation fails during encoding or sending data.

\`@ExceptionHandler\` and \`@ControllerAdvice\` are very useful for exceptions in the annotated controller model. However, they operate through the controller handler mechanism. An exception raised in a \`WebFilter\` before the request reaches a controller is outside the scope of that controller advice.

**\`WebExceptionHandler\` is an abstraction at the WebHandler API layer**, sitting outside the filter chain and target WebHandler. It provides a centralized place to handle exceptions propagating from these components, including errors that did not originate from a controller.

The goal is usually to map known exceptions to safe HTTP statuses and response bodies, log with correlation, and let out-of-scope exceptions continue to the next handler.

## 2. Position of WebExceptionHandler in the Request Lifecycle

Spring Framework builds the low-level processing chain using \`WebHttpHandlerBuilder\`. The builder can auto-detect beans in the \`ApplicationContext\`, including multiple \`WebExceptionHandler\` beans, multiple \`WebFilter\` beans, and a target \`WebHandler\`.

Conceptual model:

~~~text
HTTP server adapter
        |
        v
WebExceptionHandler chain
        |
        v
WebFilter chain
        |
        v
Target WebHandler
        |
        +-- DispatcherHandler
        |      |
        |      +-- annotated controller
        |      +-- functional endpoint
        |
        v
HTTP response
~~~

Exceptions raised in a filter or target WebHandler propagate outward. The \`WebExceptionHandler\` chain receives the exception and tries handlers in order.

A handler can:

- Handle it successfully: set status/headers, write the response, and complete the publisher.
- Decline responsibility for the exception: return an error-emitting publisher so the next handler tries to handle it.
- Be unable to write a response because the response has already committed: must not write a second response; log and let the runtime observe the error.

This is a layer wrapping request processing. It does not replace controllers, filters, services, or security; it only decides what to do with exceptions that escape those layers.

## 3. The Key Contract of WebExceptionHandler

Spring Framework interface:

~~~java
public interface WebExceptionHandler {
    Mono<Void> handle(ServerWebExchange exchange, Throwable ex);
}
~~~

The method receives:

- \`ServerWebExchange\`: the current request/response along with attributes, session, principal, and related state.
- \`Throwable\`: the exception being propagated.

The \`Mono<Void>\` return value represents the **outcome of exception handling**, not a data body:

| Return value | Meaning for the exception chain |
| --- | --- |
| \`Mono.empty()\` or a publisher completing normally after handling the response | The handler took responsibility; the exception is considered handled |
| \`Mono.error(ex)\` | This handler did not handle the exception; the exception continues to the next handler |
| Publisher emitting another error | The handler's own processing failed; the new error continues propagating |

This is the easiest point to get wrong. If an exception is outside a handler's scope, **do not return \`Mono.empty()\`** just to ignore it. Doing so tricks the framework into thinking the exception was handled even though no proper response was produced.

Correct example in principle:

~~~java
@Override
public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
    if (ex instanceof KnownApplicationException) {
        // Build the response for this exception.
        return writeErrorResponse(exchange);
    }

    // Out of scope: let the next handler handle it.
    return Mono.error(ex);
}
~~~

\`writeErrorResponse\` here is an illustrative method. In real code, it must complete after status/headers/body have been written successfully.

## 4. How WebExceptionHandler Differs from @ExceptionHandler and @ControllerAdvice

The three mechanisms have different scopes and abstraction levels:

| Mechanism | Location | Suitable Use Case |
| --- | --- | --- |
| \`@ExceptionHandler\` in a controller | Inside annotated controller handling | Errors specific to a controller or endpoint group |
| \`@RestControllerAdvice\` | Applied globally to annotated controllers | Standardizing controller validation, domain, and HTTP errors |
| \`WebExceptionHandler\` | Outside the WebFilter chain and target WebHandler | Filter errors, WebHandler-layer errors, or exceptions unhandled by inner layers |

Controller advice example:

~~~java
@RestControllerAdvice
public class ApiControllerAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ApiError> handleBadInput(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(
            new ApiError("BAD_INPUT", "The request is invalid.")
        );
    }

    public record ApiError(String code, String message) {}
}
~~~

This mechanism suits exceptions raised in annotated controllers. However, if \`AuthenticationWebFilter\` or a custom \`WebFilter\` emits an error before \`DispatcherHandler\` invokes a controller, controller advice is not the right handling layer.

Filter example:

~~~java
@Component
public class TokenFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        if (tokenIsInvalid(exchange)) {
            return Mono.error(new InvalidTokenException());
        }

        return chain.filter(exchange);
    }
}
~~~

\`InvalidTokenException\` originates in the filter. A \`WebExceptionHandler\` can map this error to 401 or 403 per the security contract. For real authentication, prefer Spring Security's entry point / access-denied handler mechanisms rather than writing a custom token authenticator in a demo filter.

**Not every controller exception goes straight to WebExceptionHandler.** WebFlux has internal exception handling inside HandlerAdapter and controller advice. Only exceptions left unhandled by inner layers continue propagating to outer layers.

## 5. When Is an Exception Routed to WebExceptionHandler?

We can classify by where the exception originates:

| Origin | Mechanism typically handling first | Role of WebExceptionHandler |
| --- | --- | --- |
| \`WebFilter\` before invoking the chain | No controller handler exists at that point | Primary layer for handling exceptions escaping the filter |
| \`WebFilter\` after invoking the chain and downstream publisher errors | Filter may handle via operators if designed to | Receives the error if the filter does not handle it and it propagates outward |
| Handler mapping or dispatch | Internal dispatch/exception handling if any | Handles exceptions still escaping WebHandler |
| Annotated controller | \`@ExceptionHandler\`, \`@ControllerAdvice\`, HandlerAdapter | Fallback for unhandled errors |
| Functional endpoint | Handler/router may handle errors in the pipeline | Receives exceptions still escaping the target WebHandler |
| Response writing after headers/body committed | Cannot create a new HTTP response | Cannot alter status/body; log/observe and terminate stream per runtime capability |

An error originating in a reactive publisher can occur **after the method has already returned**. For example:

~~~java
@GetMapping("/data")
public Mono<Data> data() {
    return service.fetch()
        .map(this::transform);
}
~~~

If \`service.fetch()\` emits \`onError\` when the subscription runs, the error still belongs to the request-processing pipeline. If not handled by operators or inner handlers, it can propagate to WebExceptionHandler.

Conversely, an exception on a background thread detached from the request lifecycle via an independent \`subscribe()\` does not automatically return to the original request's exception chain. This is one reason not to call subscribe manually inside controllers or filters.

## 6. Processing Order and Passing Errors to the Next Handler

WebFlux allows registering multiple \`WebExceptionHandler\` beans. Order can be controlled with \`@Order\` or the \`Ordered\` interface.

A handler should handle a **specific exception scope**:

~~~java
if (ex instanceof InvalidTokenException) {
    return writeUnauthorized(exchange);
}
return Mono.error(ex);
~~~

Do not catch every \`Throwable\` and always return 500, because doing so can:

- Hide statuses already determined by \`ResponseStatusException\`.
- Override Spring or Spring Boot default handling.
- Turn cancellation errors, response-write errors, or infrastructure failures into an inappropriate generic response.
- Make programming bugs harder to spot.

### How does the handler chain work?

Suppose there are three handlers in order:

~~~text
CustomApiExceptionHandler
          |
          | does not claim exception -> Mono.error(ex)
          v
BootErrorWebExceptionHandler
          |
          | cannot handle -> Mono.error(ex)
          v
Framework response-status handler
~~~

This is an illustrative model of how exceptions are tried sequentially; exact order also depends on the application's beans and configuration. Each handler must follow the complete/error contract so the chain knows whether the exception has been handled.

Do not use \`onErrorResume(ex -> Mono.empty())\` as a way to "ignore errors" inside a handler. It can swallow the exception without setting a response status or body.

## 7. Built-in Spring Framework Handlers

Spring WebFlux includes built-in implementations:

### ResponseStatusExceptionHandler

\`ResponseStatusExceptionHandler\` handles \`ResponseStatusException\` instances by setting the corresponding HTTP status on the response. It fits when the application only needs to map an exception to a status code.

Example:

~~~java
return Mono.error(
    new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Resource not found"
    )
);
~~~

The corresponding handler can set status 404. Whether an error body is included depends on another error-rendering layer.

### WebFluxResponseStatusExceptionHandler

\`WebFluxResponseStatusExceptionHandler\` extends the mechanism above and can determine the status from the \`@ResponseStatus\` annotation on an exception class. Spring WebFlux Config registers this implementation.

Example:

~~~java
@ResponseStatus(HttpStatus.CONFLICT)
public class DuplicateOrderException extends RuntimeException {
}
~~~

When this exception escapes and is handled by the status handler, the response gets status 409.

These two handlers are not full JSON renderers. If a consistent response body is needed, use controller advice, Boot's error handler, or a custom WebExceptionHandler depending on scope.

## 8. Handling the Response: Status, Headers, and Body

A custom \`WebExceptionHandler\` works directly with \`ServerWebExchange\` and \`ServerHttpResponse\`. A basic JSON response needs to:

1. Check that the response has not yet committed.
2. Select the status based on the exception type.
3. Set \`Content-Type\`.
4. Serialize the error payload.
5. Write a \`DataBuffer\` to the response and return the publisher from \`writeWith\`.

Skeleton example:

~~~java
ServerHttpResponse response = exchange.getResponse();

response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

byte[] json = objectMapper.writeValueAsBytes(errorBody);

return response.writeWith(
    Mono.just(response.bufferFactory().wrap(json))
);
~~~

This illustrative snippet requires \`ObjectMapper\`, \`Mono\`, \`ServerHttpResponse\`, and the error DTO. There is no need to call \`subscribe()\`: the publisher from \`writeWith\` is composed by the framework into the response lifecycle.

If the response has no body, set status/headers and return \`response.setComplete()\`. Do not write JSON \`null\` when the contract expects an empty response.

### Using Problem Details

Spring Framework supports RFC 9457 Problem Details via \`ProblemDetail\` and \`ErrorResponse\`. Example payload:

~~~json
{
  "type": "https://example.org/problems/upstream-unavailable",
  "title": "Upstream unavailable",
  "status": 503,
  "detail": "A required upstream service is temporarily unavailable."
}
~~~

With annotated controllers, you can return \`ProblemDetail\` from \`@ExceptionHandler\` or use \`ResponseEntityExceptionHandler\`. At a lower layer, a custom handler can construct a body with the same schema and set \`Content-Type: application/problem+json\`.

Never put stack traces, SQL, internal hostnames, tokens, or sensitive data into public responses. Error details for clients should be stable, actionable, and not reveal internal structure.

## 9. Committed Responses: An Irreversible Boundary

An HTTP response may already be committed once status/headers have been sent or the body has begun writing. After that point, the server cannot send a second HTTP response to change 200 to 500 or replace the already-sent body.

Custom handlers should check:

~~~java
if (exchange.getResponse().isCommitted()) {
    return Mono.error(ex);
}
~~~

If the response has already committed:

- Do not try to set a new status.
- Do not try to append a JSON error document onto the current body.
- Do not call \`setComplete()\` expecting it to replace the already-sent body.
- Log/record metrics with the request correlation ID.
- Let the error propagate or let the stream terminate per server capability.

Especially with SSE, NDJSON, file downloads, or long-lived streaming responses, an error occurring after part of the body has reached the client cannot change the initial HTTP status. If the protocol allows, the application can send an **application-level error event** before the stream ends; this is a stream-level design, not a new HTTP response.

## 10. Spring Boot: ErrorWebExceptionHandler and DefaultErrorWebExceptionHandler

Spring Boot adds error-rendering abstractions and configuration on top of WebFlux:

- \`ErrorWebExceptionHandler\` is Boot's marker interface extending Framework \`WebExceptionHandler\`, used for error-response rendering components.
- \`AbstractErrorWebExceptionHandler\` is a convenience base class for building error handlers in functional endpoint style.
- \`DefaultErrorWebExceptionHandler\` is Boot's default implementation.
- \`ErrorWebFluxAutoConfiguration\` creates \`ErrorAttributes\` and the default error handler when a reactive application qualifies and no replacement bean exists.

Boot places its default error handler at order \`-1\`. A custom handler can run before it with a higher-priority order (smaller number), handle specific errors, and return \`Mono.error(ex)\` for other errors so Boot continues handling them.

### Add a WebExceptionHandler or Replace Boot's Error Renderer?

These are two different intentions:

| Implementation Approach | Consequence |
| --- | --- |
| Bean implementing only Framework \`WebExceptionHandler\` | Can handle specific exceptions at the outer layer; Boot can still register its default error renderer |
| Bean implementing Boot \`ErrorWebExceptionHandler\` | Marked as an error renderer; default auto-configuration may back off under missing-bean conditions |
| Extending \`AbstractErrorWebExceptionHandler\` | Provides helpers to route errors with \`RouterFunction\` and create JSON/HTML responses |
| Customizing \`ErrorAttributes\` | Alters error data used by Boot's existing renderer without rewriting the whole handler |

If you only need to catch a specific infrastructure error from a filter, adding a narrowly scoped Framework \`WebExceptionHandler\` bean is usually enough. There is no need to replace Boot's entire error renderer.

If replacing Boot's renderer with \`ErrorWebExceptionHandler\`, the application takes broader responsibility for status mapping, content negotiation, bodies, logging, views, and fallbacks.

### Problem Details in Spring Boot

WebFlux Problem Details support can be enabled via a property:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

For supported standard exceptions, Spring can render responses as \`application/problem+json\`. Before writing a custom Boot error handler, check whether \`ProblemDetail\`, \`ErrorResponse\`, \`ResponseEntityExceptionHandler\`, or customizing \`ErrorAttributes\` already meets your goal.

## 11. Complete Java 17+ Example with Spring Boot WebFlux

This example demonstrates the exact out-of-controller boundary:

- A \`WebFilter\` emits \`EdgeFailureException\` before the request reaches a controller.
- A custom \`WebExceptionHandler\` at order \`-2\` maps that exception to HTTP 503 JSON.
- Other exceptions are forwarded using \`Mono.error(ex)\`.
- The controller has its own \`@ExceptionHandler\` to handle errors originating inside the controller, returning HTTP 400.

Structure:

~~~text
web-exception-handler-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/errorhandling/
    │   ├── ErrorHandlingApplication.java
    │   ├── EdgeFailureException.java
    │   ├── EdgeFailureFilter.java
    │   ├── ApiWebExceptionHandler.java
    │   └── DemoController.java
    └── test/java/com/example/errorhandling/
        └── ErrorHandlingTest.java
~~~

File \`pom.xml\` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>web-exception-handler-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File \`src/main/java/com/example/errorhandling/ErrorHandlingApplication.java\`:

~~~java
package com.example.errorhandling;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorHandlingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/errorhandling/EdgeFailureException.java\`:

~~~java
package com.example.errorhandling;

public final class EdgeFailureException extends RuntimeException {
    public EdgeFailureException() {
        super("A required upstream dependency is unavailable");
    }
}
~~~

File \`src/main/java/com/example/errorhandling/EdgeFailureFilter.java\`:

~~~java
package com.example.errorhandling;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class EdgeFailureFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String path = exchange.getRequest().getPath().value();

        if ("/api/edge-failure".equals(path)) {
            return Mono.error(new EdgeFailureException());
        }

        return chain.filter(exchange);
    }
}
~~~

File \`src/main/java/com/example/errorhandling/ApiWebExceptionHandler.java\`:

~~~java
package com.example.errorhandling;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebExceptionHandler;

import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class ApiWebExceptionHandler implements WebExceptionHandler {

    private static final Logger log =
        LoggerFactory.getLogger(ApiWebExceptionHandler.class);

    private final ObjectMapper objectMapper;

    public ApiWebExceptionHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> handle(ServerWebExchange exchange, Throwable ex) {
        if (!(ex instanceof EdgeFailureException)) {
            return Mono.error(ex);
        }

        ServerHttpResponse response = exchange.getResponse();

        if (response.isCommitted()) {
            log.error("Cannot render edge error because response is committed: {}",
                exchange.getLogPrefix(), ex);
            return Mono.error(ex);
        }

        ApiError body = new ApiError(
            "UPSTREAM_UNAVAILABLE",
            "A required upstream service is temporarily unavailable."
        );

        final byte[] json;
        try {
            json = objectMapper.writeValueAsBytes(body);
        } catch (JsonProcessingException serializationError) {
            return Mono.error(serializationError);
        }

        response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        log.warn("Mapped edge failure for {}", exchange.getLogPrefix(), ex);

        return response.writeWith(
            Mono.just(response.bufferFactory().wrap(json))
        );
    }

    public record ApiError(String code, String message) {}
}
~~~

File \`src/main/java/com/example/errorhandling/DemoController.java\`:

~~~java
package com.example.errorhandling;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DemoController {

    public record ControllerError(String code, String message) {}

    @GetMapping("/ok")
    public Mono<Map<String, String>> ok() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/controller-failure")
    public Mono<String> controllerFailure() {
        return Mono.error(new IllegalArgumentException("invalid input"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ControllerError> handleBadInput(
            IllegalArgumentException ex) {

        return ResponseEntity.badRequest().body(
            new ControllerError(
                "BAD_INPUT",
                "The controller request is invalid."
            )
        );
    }
}
~~~

Run from the \`web-exception-handler-demo\` directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

### Testing an Error Raised Outside the Controller

~~~bash
curl -i http://localhost:8080/api/edge-failure
~~~

Expected response:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
~~~

JSON body:

~~~json
{
  "code": "UPSTREAM_UNAVAILABLE",
  "message": "A required upstream service is temporarily unavailable."
}
~~~

The request is intercepted by the filter before reaching the controller. \`ApiWebExceptionHandler\` catches \`EdgeFailureException\`, sets status 503, and writes the JSON response.

### Testing an Error Handled Inside the Controller

~~~bash
curl -i http://localhost:8080/api/controller-failure
~~~

Expected response:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

JSON body:

~~~json
{
  "code": "BAD_INPUT",
  "message": "The controller request is invalid."
}
~~~

This error is handled by \`@ExceptionHandler\` inside the controller. It demonstrates the different scopes between controller-level exception handling and WebExceptionHandler.

### Testing a Normal Endpoint

~~~bash
curl -i http://localhost:8080/api/ok
~~~

JSON body:

~~~json
{"status":"ok"}
~~~

### Why Does the Example Still Keep Boot's Default Error Handler?

The custom class only implements Framework \`WebExceptionHandler\`, not Boot's marker \`ErrorWebExceptionHandler\`. Therefore Boot can still create the default error renderer. The custom handler has order \`-2\`, running before Boot's default handler at order \`-1\`; it handles only \`EdgeFailureException\`, while other exceptions are forwarded.

## 12. Testing with WebTestClient

Both error paths can be verified with integration tests. File \`src/test/java/com/example/errorhandling/ErrorHandlingTest.java\`:

~~~java
package com.example.errorhandling;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ErrorHandlingTest {

    @Autowired
    WebTestClient client;

    @Test
    void filterFailureIsHandledByWebExceptionHandler() {
        client.get()
            .uri("/api/edge-failure")
            .exchange()
            .expectStatus().isEqualTo(503)
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("UPSTREAM_UNAVAILABLE");
    }

    @Test
    void controllerFailureIsHandledByExceptionHandler() {
        client.get()
            .uri("/api/controller-failure")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code").isEqualTo("BAD_INPUT");
    }

    @Test
    void normalRequestStillWorks() {
        client.get()
            .uri("/api/ok")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

The tests confirm:

1. The exception emitted by the filter is mapped to 503 by the custom WebExceptionHandler.
2. The exception from the controller is mapped to 400 by the local \`@ExceptionHandler\`.
3. Normal requests still work.

These are integration tests relying on Spring Boot test and the embedded reactive server. When testing the handler in isolation, you can use \`MockServerWebExchange\` and inspect \`Mono<Void>\`/response; however, integration tests are more useful for verifying the actual ordering across filters, controllers, custom handlers, and Boot's default handler.

## 13. Deeper Customization of Boot Error Rendering

If the requirement is to standardize **every unhandled error** into a custom schema, consider Boot's \`AbstractErrorWebExceptionHandler\`. This base class provides functional routing for error responses and access to \`ErrorAttributes\`, message readers/writers, and view resolvers.

An implementation following this approach typically:

1. Extends \`AbstractErrorWebExceptionHandler\`.
2. Injects \`ErrorAttributes\`, resource properties, and \`ApplicationContext\`.
3. Configures message readers/writers from \`ServerCodecConfigurer\`.
4. Overrides \`getRoutingFunction(...)\` to select JSON/HTML error routes.
5. Returns a \`ServerResponse\` with the appropriate status and body.

Boot also provides \`DefaultErrorWebExceptionHandler\`, which can be subclassed to override specific behaviors. Classes and constructors may change across major Boot versions; always use APIs matching your project's version.

When you only need to modify the default error payload, examine the \`ErrorAttributes\` bean first. When you want RFC 9457, consider \`ProblemDetail\` and the \`spring.webflux.problemdetails.enabled\` property. Only replace the error renderer when you truly need full control over the entire response.

## 14. Logging, Correlation, and Security

An error handler is a suitable place to record errors not handled by inner layers. However, logs must provide enough information for operations without turning into a secret store.

You should:

- Log the exception type, request path, status, and correlation/request ID.
- Use \`exchange.getLogPrefix()\` to associate logs with requests in WebFlux.
- Record stack traces in server logs according to appropriate severity.
- Return stable error codes to clients.
- Never return \`ex.getMessage()\` directly if it could contain SQL, hostnames, tokens, or personal data.
- Never log authorization headers, cookies, session IDs, or sensitive request bodies.
- Use metrics to distinguish mapped errors from unhandled errors.

Not every exception is a 500. Map according to cause and contract:

| Error Category | Common Status |
| --- | --- |
| Invalid request | 400 |
| Unauthenticated | 401 |
| Authenticated but lacks permission | 403 |
| Resource not found | 404 |
| Business conflict | 409 |
| Payload too large | 413 |
| Unsupported media type | 415 |
| Temporary upstream dependency failure | 502 or 503 depending on context |
| Unexpected server error | 500 |

Do not use 401/403 interchangeably and do not turn every exception into 500. If using Spring Security, let the authentication entry point and access-denied handler handle security errors at the proper layer.

## 15. Common Mistakes

1. **Using \`@ControllerAdvice\` to catch errors from a WebFilter:** filters sit outside controller dispatch. Use WebExceptionHandler or the corresponding Security mechanism.
2. **Returning \`Mono.empty()\` for unhandled exceptions:** the framework treats it as handled even though no response may have been produced. Return \`Mono.error(ex)\` to forward.
3. **Catching every Throwable and returning 500:** masks status-bearing errors, cancellations, and programming bugs. Only map exceptions within scope.
4. **Failing to declare order:** a custom handler may run after Boot's default or in an unintended order. Specify order explicitly with \`@Order\`/Ordered.
5. **Placing a custom handler before Boot without yielding errors:** Boot's default loses its chance to handle other exceptions. For unrecognized errors, return \`Mono.error(ex)\`.
6. **Confusing WebExceptionHandler with ErrorWebExceptionHandler:** the second interface is Boot's marker. Registering it may cause Boot's default renderer to back off conditionally.
7. **Assuming WebExceptionHandler only handles controllers:** it wraps the WebFilter chain and target WebHandler; filter errors are also in scope.
8. **Trying to change status after the response commits:** already-sent HTTP headers/body cannot be recalled. Check \`response.isCommitted()\`.
9. **Writing the body twice:** can corrupt the response or close the connection. Only one handler should write a response.
10. **Calling \`block()\` or \`subscribe()\` in a handler:** blocks the event loop or detaches response writing from the lifecycle. Return the publisher from \`writeWith\`.
11. **Returning raw exception messages:** can leak internal details. Use safe error codes/messages and log details server-side.
12. **Failing to handle error-body serialization failures:** the error renderer itself can fail. Provide a minimal fallback or propagate the serialization error.
13. **Assuming post-commit errors can become JSON 500:** once a stream has started, HTTP status cannot be changed; design in-band errors if the protocol supports them.
14. **Using a generic handler instead of Spring Security:** authentication/authorization errors need proper entry points/access-denied handlers.
15. **Not testing filter exceptions:** testing controller advice does not prove filter errors are handled.
16. **Not checking cancellation:** client disconnects are usually cancellations, not necessarily exceptions for WebExceptionHandler to handle.
17. **Creating a custom ErrorWebExceptionHandler too early:** can accidentally replace all of Boot's error rendering. First consider ErrorAttributes/ProblemDetail or add a narrowly scoped Framework handler.
18. **Failing to distinguish logged errors from handled errors:** logging does not handle an exception; the handler must complete the response or yield the error.

## 16. WebExceptionHandler Design Checklist

Before shipping a handler to production, verify:

- Which exceptions are this handler's responsibility?
- Which exceptions must be forwarded?
- Does the handler run before or after Boot's default?
- Does the handler properly satisfy the \`Mono<Void>\` contract?
- Has the response already committed?
- Do status and content type match the error contract?
- Does the error body avoid leaking internal information?
- Are correlation IDs and server-side logging present?
- Are controller, filter, security, and functional endpoint errors distinguished?
- Are response serialization/write failures handled?
- Is Boot's default behavior preserved for other exceptions?
- Are WebFilter errors, controller errors, unknown errors, and committed responses tested?
- Are \`block()\`, \`subscribe()\`, and duplicate response writes avoided?

## 17. Self-Check Questions

**1.** Which layer does \`WebExceptionHandler\` belong to? The WebHandler API, wrapping the WebFilter chain and target WebHandler.

**2.** What does the \`handle\` method receive? \`ServerWebExchange\` and \`Throwable\`, returning \`Mono<Void>\`.

**3.** What does \`Mono<Void>\` completion mean? The exception has been handled by the handler.

**4.** What does \`Mono.error(ex)\` mean? The current handler did not handle it; the exception is passed to the next handler.

**5.** Why doesn't \`@ControllerAdvice\` catch exceptions thrown by a WebFilter before the controller? Because controller advice operates via HandlerAdapter/annotated controllers, whereas filters sit outside dispatch.

**6.** Can WebExceptionHandler catch errors from functional endpoints? Yes, if the error escapes the handler/router and propagates out of the target WebHandler.

**7.** What is \`@Order\` used for? Specifying the ordering of WebExceptionHandler/WebFilter beans in their respective chains.

**8.** What does \`ResponseStatusExceptionHandler\` do? Maps \`ResponseStatusException\` to HTTP status; WebFlux has an extension supporting \`@ResponseStatus\`.

**9.** Does \`ErrorWebExceptionHandler\` belong to Framework or Boot? It is a Spring Boot marker interface extending Framework WebExceptionHandler.

**10.** Why should a custom handler return \`Mono.error(ex)\` for unknown errors? So the next handler, such as Boot's default, can continue handling it.

**11.** Can status be changed after the response has committed? No. Already-sent headers/body cannot be replaced with a new response.

**12.** Why shouldn't \`ex.getMessage()\` be returned to the client? The message can leak SQL, hostnames, tokens, or internal details.

**13.** When should AbstractErrorWebExceptionHandler be used? When customizing Boot error rendering using functional RouterFunction and ErrorAttributes.

**14.** If you only want to handle one filter exception in Boot, do you need to replace DefaultErrorWebExceptionHandler? Usually no; add a narrowly scoped Framework WebExceptionHandler and let Boot handle the remaining errors.

**Key Takeaways:** \`WebExceptionHandler\` is the exception-handling layer outside the WebFilter chain and target WebHandler. \`Mono<Void>\` completion means handled; \`Mono.error(ex)\` means yielding the error to the next handler. \`@ControllerAdvice\` is for errors inside annotated controllers; WebExceptionHandler suits filter errors and out-of-controller infrastructure errors. In Boot, understand the ordering relative to the default error renderer, catch only in-scope errors, never write responses after commit, and never leak internal details.

**Official documentation:**
- [Spring Framework 6.2 — Reactive Core, WebHandler API and Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebExceptionHandler.html)
- [Spring Framework 6.2 — Controller Exceptions](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html)
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-advice.html)
- [Spring Boot 3.5 — Reactive Web Applications and Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html)
- [Spring Boot 3.5 — ErrorWebFluxAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/error/ErrorWebFluxAutoConfiguration.html).