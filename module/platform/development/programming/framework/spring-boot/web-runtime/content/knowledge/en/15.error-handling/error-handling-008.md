# Distinguishing Pre-Handler Errors from Result-Processing Errors in Spring Boot

## 1. Why Identify Which Stage an Error Occurred In?

An HTTP request is not handed directly to a controller method. It can be rejected before a handler is selected, fail while converting argument types, throw an exception in a service, or **the controller can return successfully while the framework still fails to serialize the response**. Both cases yield HTTP 500, yet they have different causes and fixes:

- `GET /orders/7` → service throws `IllegalStateException` before returning a DTO.
- `GET /orders/7` → controller returns a DTO; Jackson calls a getter/custom serializer and throws an exception while writing JSON.

There is another distinction: once status and headers **have committed** (already flushed down to the HTTP layer), you cannot rewrite what was sent into a different status/body, even if the framework catches the later error.

This lesson belongs to the **error handling** topic of web runtime, focusing on Spring Boot 3.5.x with Spring MVC (Servlet stack), followed by a comparison with Spring WebFlux (reactive stack). Readers will gain:
- A lifecycle model of request-processing milestones, distinguishing “handler not yet chosen”, “handler chosen but not invoked”, and “handler returned while body is still being written”.
- A table of error-catching mechanisms across filters, mapping, argument binding, controllers, return-value handlers, converters, views, and streaming.
- A runnable Java 17+ Maven example triggering errors at each milestone along with MockMvc tests.
- Guidance on reading `HandlerExceptionResolver`, `@RestControllerAdvice`, Servlet error dispatch, and `WebExceptionHandler` within their true scopes.
- A practical debugging checklist distinguishing uncommitted vs. committed responses.

## 2. Precisely Defining “Before the Handler”

In engineering discussions, “before the handler” has two meanings:
1. **Handler has not been selected yet**: filters/security or `HandlerMapping` are still running.
2. **Handler has been selected, but the method has not executed**: argument resolvers are binding/converting/validating inputs.

Saying only “the controller didn't run” is true in both cases, yet the error-handling consequences are very different.

| Milestone | Framework Work | Error Example | Handler Chosen? | Controller Called? |
|---|---|---|---|---|
| M0 | Servlet filters, security, internal gateway | Access denied, filter throws exception | Uncertain, usually no | No |
| M1 | `HandlerMapping` selects mapping | 404, 405, 415, or 406 depending on route/media type | Possibly no | No |
| M2 | `HandlerAdapter` resolves parameters | `page=abc`, malformed JSON, `@Valid` fails | Usually yes | No |
| M3 | Handler/controller/service executes | Order not found, business conflict | Yes | Yes |
| M4 | Result/view processing | `ResponseBodyAdvice`, Jackson, template error | Yes | Yes, method may have returned |
| M5 | Body streaming and response committed | Socket closed, error writing later chunk | Possibly finished long ago | Possibly already returned |

M0–M2 are commonly called **pre-controller execution errors**. M4 is a **result processing error**. M5 is a special state: the error may be caught, yet you are no longer free to modify response status or headers.

HTTP status **is not standalone proof of the error milestone**. A 400 can stem from query conversion, malformed JSON, or a filter; a 500 can come from a service or Jackson serialization.

## 3. Spring MVC Lifecycle: Where Each Type of Error Occurs

~~~text
HTTP request
   |
Servlet container
   |
Servlet Filter chain / Spring Security -------- M0
   |
DispatcherServlet
   |
HandlerMapping (selects route/handler) --------- M1
   |
HandlerAdapter
   |
Argument resolvers / conversion / validation -- M2
   |
@Controller / @RestController + service ------- M3
   |
HandlerMethodReturnValueHandler
   |   ResponseEntity / ResponseBodyAdvice
   |   HttpMessageConverter WRITE / ViewResolver
   |   View.render / asynchronous result ------- M4
   |
Servlet response buffer / flush / commit
   |
Streaming / network write --------------------- M5
   |
HTTP client
~~~

The diagram is conceptual; some rendering and streaming happen during async dispatches or on separate threads. Never deduce callback order solely from Java statement order when using asynchronous execution.

### 3.1. HandlerMapping and Errors Before Selecting a Controller

`HandlerMapping` inspects path, HTTP method, headers, `consumes`, `produces`, and mapping conditions. For example:
- No matching URL: typically 404.
- Only GET exists, client sends POST: typically 405.
- Endpoint accepts JSON, client sends `Content-Type: text/plain`: possibly 415.
- Content negotiation finds no representation: possibly 406.

These outcomes occur before any controller is invoked. Not every branch throws the same exception, and not every branch has a specific controller whose local `@ExceptionHandler` can participate.

### 3.2. Argument Resolvers and Errors After Selecting a Handler

Example:

~~~java
@GetMapping("/api/parse")
Map<String, Integer> parse(@RequestParam int age) {
    return Map.of("age", age);
}
~~~

With `GET /api/parse?age=abc`, mapping already chose `parse` as the handler, yet `"abc"` cannot convert to `int`. The error occurs **before the Java method body runs**, typically surfacing as `MethodArgumentTypeMismatchException` and HTTP 400.

Other examples:
- Missing `@RequestParam(required=true)`: `MissingServletRequestParameterException`.
- Structurally invalid JSON body: `HttpMessageNotReadableException`.
- Bean Validation on `@RequestBody`/`@ModelAttribute`: `MethodArgumentNotValidException` or `HandlerMethodValidationException` depending on handler signature.
- Nested data binding failure from type mismatch.

Do not call M2 errors “handler not found”: they are errors **creating arguments for an already selected handler**.

### 3.3. Errors Inside the Handler (M3)

Once the method starts, the service may reject a business condition or hit an infrastructure failure. Example:

~~~java
@GetMapping("/api/orders/{id}")
OrderView order(@PathVariable long id) {
    return service.findOrder(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
}
~~~

This fragment requires `OrderView`, `service`, and `OrderNotFoundException`. The error from `orElseThrow` happens inside the handler and should usually map to 404 via an `@ExceptionHandler` that understands business context. Connection pool errors, null pointers, or serialization failures do not automatically mean 404.

## 4. “Handler Returned” Does Not Mean “Response Sent”

Spring MVC separates the value returned by a method from how the HTTP result is written.

Example:

~~~java
@GetMapping("/api/orders")
ResponseEntity<List<OrderView>> list() {
    return ResponseEntity.ok(service.listOrders());
}
~~~

After `return`, the framework still performs:
1. Choosing a `HandlerMethodReturnValueHandler` based on return type.
2. Applying HTTP status and headers from `ResponseEntity`.
3. Selecting media type and `HttpMessageConverter`.
4. Invoking `ResponseBodyAdvice.beforeBodyWrite` if present.
5. Serializing Java objects into JSON bytes via Jackson.
6. Writing bytes to the Servlet output stream and buffering/flushing.
7. Completing the response.

If a `@Controller` returns a view name, `ViewResolver` and the template engine still have to run `render`. With `StreamingResponseBody`, `ResponseBodyEmitter`, and `SseEmitter`, writing content can take place long after the controller method returns.

### 4.1. Errors Selecting or Running HttpMessageConverter

Causes include:
- No matching converter for the return type/media type.
- A custom serializer throws an exception.
- A DTO getter throws while Jackson inspects it during JSON writing.
- Jackson encounters an unserializable object graph or data type.
- An `IOException` occurs after the converter has already begun writing the body.

You may encounter `HttpMessageNotWritableException`, a wrapped `JsonMappingException`, or a custom converter exception. Do not assume all converter errors share the same class.

### 4.2. Errors from ResponseBodyAdvice

`ResponseBodyAdvice` runs while preparing to write the body, and can alter content or throw an exception. It serves as a clean place to reproduce **post-return errors (M4)** without breaking a real serializer.

While uncommitted, `DispatcherServlet` can still pass the exception to the resolver chain. Once committed, exception handlers cannot rewrite already-sent status and headers.

### 4.3. Errors Rendering HTML Views

Suppose a controller returns `"orders/detail"`, but Thymeleaf/JSP hits a template expression error or missing model attribute. The handler returned successfully; the failure lies in **view rendering**, not mapping or service logic.

If the view already wrote enough HTML to commit the response before failing, a brand-new complete HTML error page cannot replace the bytes already sent. In server-rendered applications, test actual rendering rather than asserting only the returned view name string.

## 5. Errors After Response Commit: Point of No Return

In Servlet, `HttpServletResponse.isCommitted()` indicates whether the response has committed. Operations:

| Operation | Automatically Commits? | Consequence |
|---|---|---|
| `setStatus(...)` / `setHeader(...)` | Not necessarily | Updates intended status/headers |
| `getWriter()` | Not necessarily | Obtains writer; imposes encoding constraints |
| `writer.write("x")` | Not necessarily | May still remain buffered |
| `flushBuffer()` | Yes | Status and headers are committed |
| `writer.flush()` / `stream.flush()` | May commit | Treat as a data-emission boundary |
| Body fills buffer | May commit | Depends on buffer/container size |
| `sendError()` / `sendRedirect()` | Commits per contract | Cannot be called after commit |
| Container finishes HTTP response | Usually commits | Not the same time as controller return |

After commit:
- `setStatus(500)` does not alter the already-sent status.
- `setHeader` cannot add headers to the already-sent head.
- `reset()`, `resetBuffer()`, `sendError()`, and `sendRedirect()` may throw `IllegalStateException` per API contract.
- The client may receive the first part of the body followed by a dropped connection; a valid JSON error is not guaranteed.

Example:

~~~java
response.setStatus(200);
response.setContentType("text/plain;charset=UTF-8");
response.getWriter().write("first chunk\n");
response.flushBuffer();
throw new IllegalStateException("later failure");
~~~

The last line throws after HTTP status 200 has already committed. Resolvers/advice can log the error, **yet cannot turn the sent bytes into HTTP 500**. That is a protocol constraint, not a missing annotation.

Do not confuse `isCommitted=true` on the Servlet container with the client having received all bytes: a reverse proxy downstream may still buffer.

## 6. MVC Exception-Handling Chain

Per the Spring MVC contract, `DispatcherServlet` delegates exceptions raised during request mapping, handler invocation, and result processing to a `HandlerExceptionResolver` chain.

| Resolver / Component | Responsibility |
|---|---|
| `ExceptionHandlerExceptionResolver` | Calls `@ExceptionHandler` on controller or `@ControllerAdvice`/`@RestControllerAdvice` |
| `ResponseStatusExceptionResolver` | Handles `@ResponseStatus` / `ResponseStatusException` |
| `DefaultHandlerExceptionResolver` | Translates many standard MVC framework errors into appropriate statuses |
| Custom `HandlerExceptionResolver` | Resolves a category of errors per app policy and order |
| Servlet container + Boot `/error` | Fallback when status/error dispatch applies or exception remains unresolved |

A resolver may resolve the exception or pass it on for the next resolver to try. An exception handled by a resolver does not necessarily reach `/error`; conversely, a container ERROR dispatch is not a direct call to `@ExceptionHandler`.

### 6.1. @RestControllerAdvice Does Not Automatically Cover All Filter Exceptions

Servlet `Filter`s execute **outside** `DispatcherServlet`. If a filter throws an exception before `chain.doFilter`, do not assume a `@RestControllerAdvice` will catch it. Ownership belongs to:
- The filter or Spring Security entry point/denied handler.
- The Servlet container's error-handling mechanism.
- A custom integration explicitly delegating exceptions into the MVC resolver if truly needed.

By contrast, errors inside `DispatcherServlet`'s `HandlerMapping` can reach the resolver chain. An appropriately scoped global advice may participate depending on the exception; never claim “if no handler was chosen, every advice is useless”.

### 6.2. Controller-Local vs. Global Advice

If a handler is identified and has a matching local `@ExceptionHandler`, it typically runs before global advice. `@RestControllerAdvice` standardizes API responses; `ResponseEntityExceptionHandler` helps customize standard MVC errors and Problem Details.

Never write `@ExceptionHandler(Exception.class)` returning HTTP 400 for everything, because programming bugs, DB failures, and result serialization errors are not malformed client inputs.

## 7. Choosing Error Strategy by Stage

| Case | Did Controller Run? | Preferred Handling | Can Error Status Change? |
|---|---|---|---|
| Filter blocks request | No | Filter/security handler at right layer | Yes if uncommitted |
| Route not matched | No | Mapping defaults, global resolver, `/error` as applicable | Yes if uncommitted |
| Query/path conversion fails | No | MVC resolver/`@RestControllerAdvice` for that exception type | Usually yes |
| Malformed JSON body | No | `HttpMessageNotReadableException` handling | Usually yes |
| Business rule fails in controller | Yes | `@ExceptionHandler` for domain exception | Yes if uncommitted |
| `ResponseBodyAdvice` throws | Yes, already returned | MVC resolver/advice | Yes if uncommitted |
| Jackson/view render error | Yes, already returned | Resolver + simple error response, logs | Depends on commit |
| Streaming fails after first chunk | Possibly returned long ago | Cleanup, logging, app-level error signal if feasible | Cannot change committed status/headers |

**Do not diagnose root cause from status code alone.** You need timeline, exception class/root cause, response commitment state, and request metadata.

## 8. Runnable Demo with Spring Boot 3.5 and Java 17+

The program creates five endpoints:
1. `/api/filter-deny`: filter returns 403 before `DispatcherServlet`.
2. `/api/parse?age=abc`: argument resolver fails to convert, controller does not run; advice returns 400.
3. `/api/business`: controller throws `BusinessFailure`, advice returns 409.
4. `/api/result?explode=true`: controller returns `ResultPayload`, then `ResponseBodyAdvice` throws `ResultProcessingFailure`; advice returns 500 if uncommitted.
5. `/api/late`: controller writes and flushes before throwing; do not expect a fresh 500.

Intentionally throwing inside `ResponseBodyAdvice` is a **reliable way to reproduce an M4 error**, unlike relying on a Jackson serialization quirk that might change across versions.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>error-stage-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 8.2. Complete Java Source

Create `src/main/java/example/stages/ErrorStageApplication.java`:

~~~java
package example.stages;

import java.io.IOException;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.MethodParameter;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

@SpringBootApplication
public class ErrorStageApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorStageApplication.class, args);
    }
}

class BusinessFailure extends RuntimeException {}
class ResultProcessingFailure extends RuntimeException {}

record ResultPayload(String message, boolean explode) {}

@Component
@Order(-100)
class PreDispatchFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        if ("/api/filter-deny".equals(request.getRequestURI())) {
            response.setStatus(HttpStatus.FORBIDDEN.value());
            response.setContentType("text/plain;charset=UTF-8");
            response.getWriter().write("blocked-by-filter");
            return; // does not enter DispatcherServlet / controller
        }
        chain.doFilter(request, response);
    }
}

@RestController
@RequestMapping("/api")
class StageController {

    @GetMapping("/parse")
    Map<String, Integer> parse(@RequestParam int age) {
        return Map.of("age", age);
    }

    @GetMapping("/business")
    String business() {
        throw new BusinessFailure();
    }

    @GetMapping("/result")
    ResultPayload result(
            @RequestParam(defaultValue = "false") boolean explode) {
        return new ResultPayload("ready", explode);
    }

    @GetMapping("/late")
    void late(HttpServletResponse response) throws IOException {
        response.setStatus(HttpStatus.OK.value());
        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().write("first chunk\n");
        response.flushBuffer();
        throw new IllegalStateException("failure after commit");
    }
}

@ControllerAdvice
class ResultPhaseAdvice implements ResponseBodyAdvice<Object> {

    @Override
    public boolean supports(
            MethodParameter returnType,
            Class<? extends HttpMessageConverter<?>> converterType) {
        return true;
    }

    @Override
    public Object beforeBodyWrite(
            Object body,
            MethodParameter returnType,
            MediaType selectedContentType,
            Class<? extends HttpMessageConverter<?>> selectedConverterType,
            ServerHttpRequest request,
            ServerHttpResponse response) {

        if (body instanceof ResultPayload payload && payload.explode()) {
            throw new ResultProcessingFailure();
        }
        return body;
    }
}

@RestControllerAdvice
class StageErrors {

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<Map<String, String>> badParameter(
            MethodArgumentTypeMismatchException error) {
        return ResponseEntity.badRequest().body(Map.of(
                "phase", "argument-resolution",
                "error", "invalid-parameter"));
    }

    @ExceptionHandler(BusinessFailure.class)
    ResponseEntity<Map<String, String>> business(
            BusinessFailure error) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of(
                "phase", "handler",
                "error", "business-conflict"));
    }

    @ExceptionHandler(ResultProcessingFailure.class)
    ResponseEntity<Map<String, String>> result(
            ResultProcessingFailure error) {
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of(
                        "phase", "result-processing",
                        "error", "render-failure"));
    }
}
~~~

Package-private classes in `example.stages` are component-scanned by Boot; only `ErrorStageApplication` is public matching the filename. Exceptions carry no messages to prevent data leaks in the demo. `ResponseBodyAdvice` throws only when the body is `ResultPayload` with `explode=true`; when the error handler returns a `Map`, the advice does not throw again, preventing an error-response loop.

`late` exists solely to demonstrate the post-commit boundary; never use this pattern for production error handling.

### 8.3. Run and Observe

~~~bash
mvn spring-boot:run
~~~

Open another terminal:

~~~bash
curl -i http://localhost:8080/api/filter-deny
curl -i "http://localhost:8080/api/parse?age=abc"
curl -i http://localhost:8080/api/business
curl -i "http://localhost:8080/api/result?explode=true"
curl -i "http://localhost:8080/api/result?explode=false"
~~~

Key results (JSON key order and some HTTP headers depend on runtime):

| Request | Status | Main Body | Stage |
|---|---:|---|---|
| `/api/filter-deny` | 403 | `blocked-by-filter` | M0 |
| `/api/parse?age=abc` | 400 | JSON `phase=argument-resolution` | M2 |
| `/api/business` | 409 | JSON `phase=handler` | M3 |
| `/api/result?explode=true` | 500 | JSON `phase=result-processing` | M4 |
| `/api/result?explode=false` | 200 | JSON with `message=ready`, `explode=false` | Normal |

Call `curl -i http://localhost:8080/api/late` separately to observe the post-`flushBuffer()` case. You may see HTTP 200 and partial body before the stream closes; the container may log the exception. **Do not** expect a JSON 500 replacing the already-sent status.

## 9. MockMvc Tests Distinguishing the Stages

File `src/test/java/example/stages/ErrorStageApplicationTests.java`:

~~~java
package example.stages;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorStageApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void filterRejectsBeforeDispatcher() throws Exception {
        mvc.perform(get("/api/filter-deny"))
                .andExpect(status().isForbidden())
                .andExpect(content().string("blocked-by-filter"));
    }

    @Test
    void argumentConversionFailsBeforeController() throws Exception {
        mvc.perform(get("/api/parse").param("age", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.phase")
                        .value("argument-resolution"));
    }

    @Test
    void handlerExceptionUsesBusinessStatus() throws Exception {
        mvc.perform(get("/api/business"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.phase").value("handler"));
    }

    @Test
    void resultPhaseFailureHappensAfterControllerReturn() throws Exception {
        mvc.perform(get("/api/result").param("explode", "true"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.phase")
                        .value("result-processing"));
    }

    @Test
    void normalResultCanBeSerialized() throws Exception {
        mvc.perform(get("/api/result").param("explode", "false"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("ready"))
                .andExpect(jsonPath("$.explode").value(false));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

These tests verify **HTTP behavior** of a real MVC app inside the test context. To prove a controller/service did not run on the M2 branch in a production project, add a mocked service with `verifyNoInteractions(service)` instead of relying only on log checks. The demo needs no service.

MockMvc does not fully simulate sockets, networks, or streaming; for post-commit errors, write integration tests with a real embedded server and HTTP client. Never assert that a post-commit error returns a fresh JSON 500.

## 10. Spring WebFlux: Similar Distinctions, Reactive Error Flow

On Reactor Netty, Spring WebFlux does not use `DispatcherServlet` or Servlet `HandlerExceptionResolver`. Conceptual flow:

~~~text
Reactive HttpHandler
   |
WebExceptionHandler wrappers
   |
WebFilter chain ------------------ pre-handler errors
   |
DispatcherHandler
   | HandlerMapping -------------- mapping
   | HandlerAdapter -------------- arguments/controller
   | HandlerResultHandler -------- result processing
   |
ServerHttpResponse commit -------- stream/write
~~~

Key points:
- `WebFilter` can emit `Mono.error` before a handler is selected. `@RestControllerAdvice` should not be treated as a guaranteed catch-all for every filter error outside dispatch.
- `WebExceptionHandler` in the `WebHandler` chain can handle errors unresolved downstream, per its order and contract.
- WebFlux's `HandlerAdapter`/annotated controllers handle exceptions, including certain errors while processing `HandlerResult`; `DispatcherHandler` also has `DispatchExceptionHandler` in supported framework cases.
- A controller can return `Mono<T>` or `Flux<T>` before the reactive work is actually subscribed and executed.
- `ServerHttpResponse.isCommitted()` still determines whether status/headers can be changed. Once the stream emits and commits, there is no “going back” to construct a clean HTTP 500.

Fragment example:

~~~java
@GetMapping("/events")
Flux<ServerSentEvent<String>> events() {
    return service.events();
}
~~~

This is an illustrative snippet in a WebFlux controller with `service` and imports. Exceptions from `service.events()` may appear upon subscription, after the method returns. For SSE, an **application-protocol-level** error event can be sent while the stream is still open, yet the committed HTTP status remains unchanged.

### 10.1. onErrorResume Is Not a Response Reset Button

~~~java
return service.load()
        .onErrorResume(ProductNotFoundException.class,
                ex -> Mono.empty());
~~~

This fragment turns the error into an empty completion, which can yield HTTP 200 with an empty body unless status is explicitly designed. Once the first chunk is sent, `onErrorResume` cannot retract status/headers/body already sent. For domain errors requiring 404, choose the response before starting to write the body or use handler-level error handling.

### 10.2. beforeCommit in WebFlux

~~~java
exchange.getResponse().beforeCommit(() -> {
    exchange.getResponse().getHeaders()
            .set("X-Request-Observed", "yes");
    return Mono.empty();
});
~~~

This is a fragment inside a `WebFilter` with `ServerWebExchange exchange` and `Mono` imported. The callback must be registered early. `beforeCommit` prepares metadata before committing, not as a mechanism to change status after a stream has already emitted data.

## 11. Designing Error Responses by Layer

**Filter/security:** handle 401/403 responsibly using authentication entry points/access denied handlers when using Spring Security. Do not expect controller advice to handle every pre-mapping rejection.

**Argument binding:** 400 for invalid syntax/type conversion; 415 for unsupported media types; 405/406 per routing/negotiation contracts. Never include stack traces or sensitive raw payloads in responses.

**Business handler:** map domain exceptions to accurate statuses, such as 404 for missing resources or 409 for conflicts. Infrastructure failures are generally not 400.

**Result processing:** log the real cause (converter, serializer, `ResponseBodyAdvice`, view), and avoid loops where the error response itself fails to serialize. Return a simple error DTO and check whether the response is already committed.

**After commit/streaming:** do not attempt `sendError` or `resetBuffer` to write a fresh response. Log with correlation ID, clean up, terminate the stream, or emit an in-band error signal if the protocol supports it.

In Spring MVC, `ProblemDetail` and `ResponseEntityExceptionHandler` provide a consistent error contract, though they do not replace filter/security error handling or HTTP commit mechanics.

## 12. Debugging Procedure for “Controller Ran, Yet Client Received 500”

1. Capture method/path, key headers, trace ID, and actual HTTP status from the client using `curl -i`.
2. Check whether filter/security already decided the response; check if controller logs appeared.
3. Check which handler `HandlerMapping` selected; if none, look at 404/405/415/406.
4. If the method never ran, inspect argument conversion, validation, and `@RequestBody` deserialization.
5. If the method returned, inspect `HandlerMethodReturnValueHandler`, `ResponseBodyAdvice`, `HttpMessageConverter`, and view rendering.
6. If streaming, find where the body was written and `flushBuffer` called; log `response.isCommitted()` at the error-handling point.
7. Check whether another `HandlerExceptionResolver` or controller advice caught the exception first; check whether `/error` dispatch occurred.
8. Find the root cause rather than just the outer exception; serializer, database, and client disconnect failures can all appear with status 500 in logs.
9. Verify whether the error DTO itself caused a second failure in the converter.
10. Use MockMvc/WebTestClient for HTTP semantics and real integration tests when commit, proxies, async, or networking are involved.

Log `requestId`, handler name when available, stage M0–M5, exception class, root cause, response committed state, and elapsed time. Avoid logging access tokens, cookies, or full bodies containing sensitive data.

## 13. Common Mistakes

1. **“Pre-controller error means no handler was found.”** False: argument binding can fail after mapping.
2. **“Controller return means the HTTP response is finished.”** False: converter, advice, view, and async steps remain.
3. **“@RestControllerAdvice catches every Servlet Filter error.”** Not automatically.
4. **“Every HTTP 400 is Bean Validation.”** It can be conversion, malformed JSON, or a missing parameter.
5. **“Every 500 is service/database.”** It can be Jackson or view rendering after return.
6. **“As long as the full body isn't sent, status can still change.”** False once headers/status have committed.
7. **“sendError after flush can fix the error.”** It can throw `IllegalStateException`.
8. **“An exception handler can always write a new body.”** The error DTO's converter can also fail, or the response may already be committed.
9. **“Using Exception.class to return 400 for everything.”** Masks system bugs and breaks the HTTP contract.
10. **“WebFlux exceptions always happen before method return.”** Publishers are usually lazy.
11. **“onErrorResume can fix HTTP status after the first chunk.”** Sent bytes cannot be retracted.
12. **“MockMvc simulates all network errors.”** Use real-container HTTP integration tests for commit/streaming.
13. **“Seeing controller logs proves the bug is inside the controller.”** Logs may precede serialization.
14. **“No controller logs means the request never entered Spring.”** Filter/mapping/binding could have rejected it earlier.
15. **“On a 404 route, some controller's @ExceptionHandler always runs.”** No guarantee when no handler was chosen.
16. **“Enabling stack traces in error JSON makes debugging easier.”** Can expose sensitive data.
17. **“View rendering errors are the same as input validation errors.”** Different stage, cause, and recovery strategy.

## 14. Error-Handling Implementation Checklist

- [ ] Clearly distinguish filter, mapping, argument, handler, result, and committed-response stages.
- [ ] Never conflate “handler selected” with “controller method executed”.
- [ ] Include tests for 400 conversion, 409/404 business rules, and 500 result processing.
- [ ] Handle filter/security errors within their proper scopes.
- [ ] Controller advice catches only intentional exceptions, never forcing all errors to 400.
- [ ] Error response DTOs are simple enough to avoid secondary serializer failures.
- [ ] Test paths involving body converters, templates, or async streaming.
- [ ] Never attempt to change status/headers after commit.
- [ ] Ensure logging/tracing and cleanup when streaming fails.
- [ ] Include HTTP integration tests when network, buffering, or reverse proxies matter.
- [ ] In WebFlux, distinguish reactive error signals from method return.
- [ ] Keep secrets and stack traces out of production responses.

## 15. Conclusion

**The stage where an error occurs is just as important as the exception type.** Servlet filter errors before the dispatcher, mapping/binding errors before the controller, business handler errors, and serialization/rendering errors after the controller returns are distinct situations. Spring MVC provides `HandlerExceptionResolver` to resolve many dispatch-time errors; WebFlux provides a reactive pipeline with `WebExceptionHandler` and dedicated result handling. On either stack, once a response **is committed**, status and headers cannot be altered. Proper handling requires confirming the timeline, finding how far execution got, checking the root cause, and testing outcomes over HTTP.

## Official References

- Spring Framework — Spring MVC exception resolvers: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Framework — @ExceptionHandler: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MVC return values: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/return-types.html
- Spring Framework — MVC async/streaming: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
- Spring Framework — WebFlux DispatcherHandler: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html
- Spring Framework — WebFlux exception handling: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html
- Jakarta Servlet — HttpServletResponse: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletresponse