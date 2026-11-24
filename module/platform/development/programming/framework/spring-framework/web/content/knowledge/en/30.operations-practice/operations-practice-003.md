# Reading 404, 405, 406, 415, Validation, and Asynchronous Exceptions in Spring Web

## 1. Goal: diagnose from the HTTP request to where Spring handles it

When a Spring MVC API returns an error, the **HTTP status is only a symptom**. To pinpoint the root cause, you must trace which stage the request reached: handler selection, method matching, media-type checking, parameter deserialization/binding, validation, controller invocation, async processing, or response writing.

This lesson uses the **Spring MVC / Servlet stack**, Java 17+, Spring Framework 6.x (for example, Spring Boot 3.x). With Spring WebFlux, the HTTP concepts are similar, though the exception classes and execution model differ as noted at the end.

A practical investigation workflow:

1. Record the **method + URI + query string** the client actually sent; distinguish the Spring endpoint from the public URL behind a proxy/context-path.
2. Record **`Content-Type`** (the format of the request body), **`Accept`** (the format the client wants in return), `Origin` if CORS applies, and the exact body sent.
3. Inspect the HTTP status, response headers (`Allow`, `Accept`, `Content-Type`), response body/`ProblemDetail`, and request/correlation ID.
4. Cross-check `@RequestMapping`/`@GetMapping`/`@PostMapping` conditions: path, HTTP method, `params`, `headers`, `consumes`, and `produces`.
5. If the request reached the controller, check data-conversion errors, Bean Validation, business rules, and exception resolvers; if asynchronous, also inspect **async dispatch**, timeouts, and exceptions thrown on a worker thread or publisher.

Do not guess "404 means wrong controller" or "400 means validation" before verifying where the failure occurred. A problem's observable behavior can be altered by Spring Security, filters, the servlet container, a proxy, or a custom `@ControllerAdvice`.

## 2. Request pipeline diagram and quick reference table

~~~text
HTTP client
  |
  v
Reverse proxy / Servlet filters / Spring Security
  |
  v
DispatcherServlet + HandlerMapping
  |-- no handler/resource found ------------------> 404
  |-- matching path, unsuitable HTTP method ------> 405
  |-- @RequestMapping consumes mismatch ----------> 415
  |-- @RequestMapping produces mismatch ----------> 406
  |
  v
HandlerAdapter + argument resolvers + converters
  |-- malformed JSON body, missing param, type mismatch -> typically 400
  |-- @Valid, method validation failed ------------------> typically 400
  |
  v
Controller / service
  |-- business exception -------------------------> advice/resolver
  |-- Callable / DeferredResult / Mono
  |      |-- deferred exception -------------------> async dispatch -> advice
  |      |-- timeout ------------------------------> timeout handling
  |
  v
ReturnValueHandlers + HttpMessageConverter
  |-- no converter found for Accept --------------> 406 / write failure
  v
HTTP response
~~~

This is a common flow, **not a guarantee that an exception always lands in a single category**: mapping check order can depend on other conditions and MVC configuration. For example, a serialization failure late in response writing can raise `HttpMessageNotWritableException`, which is usually a server error rather than 406 by default.

| Status | Common scenario | Exception/clue in MVC | What to check first |
| --- | --- | --- | --- |
| `404 Not Found` | No handler for path; static resource missing; business logic returns 404 | `NoHandlerFoundException` or `NoResourceFoundException` when thrown by the corresponding resolver/handler, or application explicitly returns 404 | URI after rewrite, context path, mappings, static resources, security, custom advice |
| `405 Method Not Allowed` | Path has a mapping, but the HTTP method is not accepted | `HttpRequestMethodNotSupportedException` | Actual method, `Allow` response header, `@GetMapping`/`@PostMapping` |
| `406 Not Acceptable` | Cannot produce a representation matching `Accept`/`produces` | `HttpMediaTypeNotAcceptableException` | `Accept`, `produces`, converters, response content |
| `415 Unsupported Media Type` | Request body `Content-Type` is not accepted by mapping/converter | `HttpMediaTypeNotSupportedException` | `Content-Type`, `consumes`, converters, charset |
| `400 Bad Request` | Malformed JSON syntax, missing field/param, conversion or Bean Validation failure | `HttpMessageNotReadableException`, `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `MethodArgumentTypeMismatchException`... | Actual body and constraints, binding/field errors |
| `500/503/other` | Business/infra error, async exception, timeout | Exception from `Callable`, `DeferredResult.setErrorResult(...)`, `AsyncRequestTimeoutException`... | Exception root cause, async dispatch, timeout, whether response is already committed |

There is no single mapping **"async exception = HTTP 500"**. An `@ExceptionHandler` can turn it into 422/503; MVC timeout defaults typically to 503 if the response is not yet committed; an unhandled application error can become 500. Inspect the actual configuration and code executed.

## 3. 404: distinguishing missing handlers from resources and business not-found

A sample endpoint:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {
    @GetMapping("/{id}")
    Book find(@PathVariable long id) {
        return repository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

The snippet above is illustrative; `repository` and business classes must be provided. There are at least three distinct kinds of 404:

- `GET /api/boks/42` (typo in `books`): the request may match no controller; Spring returns 404 from handler mapping/static-resource handling.
- `GET /api/books/42`: mapping matches, but the service throws `BookNotFoundException` and advice translates it to 404.
- `GET /assets/logo.png`: if the static handler is mapped but the file does not exist, `NoResourceFoundException` (Spring 6.1+) may be raised and result in 404.

`NoHandlerFoundException` **does not appear on every 404**. `DispatcherServlet` can send 404 directly, and Spring Boot's default static resource mapping can claim the path first and throw `NoResourceFoundException`. Do not build `@ExceptionHandler(NoHandlerFoundException.class)` assuming it will catch every 404 in the application.

Test command:

~~~bash
curl -i http://localhost:8080/api/boks/42
~~~

When investigating 404, verify that the controller is scanned, what prefix class-level `@RequestMapping` defines, whether a proxy strips a prefix, whether trailing slashes match, whether the API version is right, and whether Spring Security or a gateway altered the path. **A 404 from a gateway** does not necessarily pass through the application's `DispatcherServlet`.

If the requirement is "record not found," returning 404 from business logic is appropriate. However, do not turn database/timeout exceptions into 404 just to spare clients a 500: doing so hides the true operational root cause.

## 4. 405: right URI, wrong HTTP method

Example endpoint that only allows POST:

~~~java
@PostMapping(path = "/api/items")
ResponseEntity<Void> create(@RequestBody CreateItem command) {
    return ResponseEntity.noContent().build();
}
~~~

This request can trigger 405:

~~~http
GET /api/items HTTP/1.1
Accept: application/json
~~~

Spring can throw `HttpRequestMethodNotSupportedException` and write an `Allow` header listing accepted methods, e.g., `POST`. `Allow` is a critical clue when reading a 405 error.

Things to check:

- Did the frontend send `GET` or `POST`? `fetch` defaults to GET if `method` is omitted.
- HTML forms support a limited set of methods; is `HiddenHttpMethodFilter` in use or is the REST endpoint expecting PUT/PATCH/DELETE?
- Did a reverse proxy alter the method, or was a preflight `OPTIONS` blocked before reaching the endpoint?
- `HEAD` is typically supported based on GET mappings; `OPTIONS` can be handled automatically by Spring, so do not lump every non-GET method into expecting 405 in tests.
- If the controller has `params`/`headers` conditions, the request may fail on another condition, not solely on method.

Contrast test:

~~~bash
curl -i -X GET http://localhost:8080/api/items
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: application/json" -d '{"name":"Pen"}'
~~~

Read `Allow`, not just the status. Never fix a 405 by adding `@GetMapping` to a write operation; fix the client or the API contract so the method matches.

## 5. 406: Accept requests a format the server cannot produce

`Accept` expresses the media types the client can receive. Controller:

~~~java
@GetMapping(
    path = "/api/items/1",
    produces = MediaType.APPLICATION_JSON_VALUE
)
Item get() {
    return new Item(1L, "Pen");
}
~~~

If the client sends:

~~~http
GET /api/items/1 HTTP/1.1
Accept: application/xml
~~~

while the endpoint only produces JSON, Spring can respond with `406 Not Acceptable` via `HttpMediaTypeNotAcceptableException`. Switching to `Accept: application/json` usually resolves it when the endpoint actually returns JSON.

**Do not confuse `Accept` with `Content-Type`:**

- `Accept` describes the **response representation** the client wants.
- `Content-Type` describes the **request body** the client is sending.
- `produces` constrains the ability to **return data**.
- `consumes` constrains the ability to **accept a body**.

Common 406 scenarios:

1. A browser or API client sends `Accept: application/xml` while the server only produces JSON.
2. The endpoint declares `produces="application/json"` while the client restricts to incompatible media types.
3. Response DTO/converters or content negotiation are misconfigured; inspect the actual exception, because a converter write failure can surface as 500 instead of 406.
4. The handler requires a specific media type via `produces`, while the browser/WebClient sends a different header.

Try:

~~~bash
curl -i http://localhost:8080/api/items/1 -H "Accept: application/xml"
curl -i http://localhost:8080/api/items/1 -H "Accept: application/json"
~~~

Do not change `produces` to `*/*` just to make 406 disappear if the application can still only serialize JSON. Supported response representations must be an explicit contract.

## 6. 415: unsupported Content-Type or body format

Endpoint:

~~~java
@PostMapping(
    path = "/api/items",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
Item create(@RequestBody CreateItem input) {
    return service.create(input);
}
~~~

If the client sends text data when the endpoint only accepts JSON:

~~~http
POST /api/items HTTP/1.1
Content-Type: text/plain
Accept: application/json

{"name":"Pen"}
~~~

Spring typically returns `415 Unsupported Media Type` with `HttpMediaTypeNotSupportedException`. **A body that looks like JSON is not enough**: the request still declared `text/plain`.

With `Content-Type: application/json` but invalid JSON syntax:

~~~http
POST /api/items HTTP/1.1
Content-Type: application/json

{"name":
~~~

the response is typically **400** due to `HttpMessageNotReadableException`, not 415, because the media type was accepted and the error occurred during parsing.

Notes:

- `application/json`, `application/x-www-form-urlencoded`, and `multipart/form-data` are not arbitrarily interchangeable.
- Multipart requires matching part names, parsers, `@RequestPart`/`@RequestParam`, and the media type for JSON parts. A missing part or parse error can cause 400; an overall request media type that mismatches `consumes` is usually 415.
- A charset or custom vendor media type like `application/vnd.acme+json` may require checking converter/compatibility; do not assume Spring always accepts it.
- If the HTTP method/path is already wrong, Spring may fail before checking the body media type. When debugging, keep everything else valid and change **one header** at a time to isolate the issue.

## 7. Validation: multiple error types can all become 400

Validation spans multiple stages, so distinguish the exception and where it is handled.

### 7.1. @Valid @RequestBody and MethodArgumentNotValidException

~~~java
public record NewItem(
        @NotBlank String name,
        @Size(max = 80) String description) {}

@PostMapping("/api/items")
Item create(@Valid @RequestBody NewItem input) {
    return service.create(input);
}
~~~

When the request JSON is syntactically valid but `name` is blank or `description` is too long, Spring MVC usually throws `MethodArgumentNotValidException` if the command object parameter is validated under a supported setup. With Spring Boot 3.x, a compatible Bean Validation dependency is required (commonly `spring-boot-starter-validation`). Imports are `jakarta.validation.Valid` and `jakarta.validation.constraints.*`, not `javax.validation.*` on Boot 3.

If a parameter places `BindingResult`/`Errors` immediately after the argument to handle errors manually, the controller can receive the errors instead of an automatic exception; tests must match the actual controller signature.

### 7.2. Method parameter validation: HandlerMethodValidationException

An endpoint validating a query parameter directly:

~~~java
@GetMapping("/api/items")
List<Item> list(@RequestParam @Min(1) int page) {
    return service.findPage(page);
}
~~~

From Spring Framework 6.1+, MVC has built-in method validation support; if the signature requires validation on parameters such as `@Min` and the request sends `page=0`, `HandlerMethodValidationException` may be thrown (typically 400 for input errors, 500 for return-value validation errors). Actual mechanics depend on configuration: class-level `@Validated` can activate different AOP method validation, so inspect your app's actual exceptions rather than hardcoding one class across versions.

### 7.3. Conversion/parsing differs from validation

- `GET /api/items/not-a-number` with `@PathVariable long id`: type conversion fails, yielding `MethodArgumentTypeMismatchException`/`TypeMismatchException` → 400.
- Missing `@RequestParam(required=true)`: `MissingServletRequestParameterException` → typically 400.
- Malformed JSON or undecodable body: `HttpMessageNotReadableException` → typically 400.
- Missing `@RequestBody(required=true)`: also typically 400 when reading the body.
- Entity/database constraints (unique key, foreign key) are storage-layer concerns; they do not automatically become a standard HTTP 400 validation error without appropriate business mapping.

To return a reusable error format, standardize `ProblemDetail`, error codes, and a list of field violations, while **never returning sensitive content** from internal exceptions. Return field names, codes, and approved messages instead of stack traces.

Example custom application error payload:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request validation failed",
  "code": "INVALID_INPUT",
  "errors": [
    {"field": "name", "message": "must not be blank"}
  ]
}
~~~

This is a **custom contract example**, not a guarantee that every Spring project returns these exact fields automatically. Spring `ProblemDetail` supports extension properties, while the exact format depends on the application's error-handling configuration.

## 8. Exception handling in Spring MVC: who handles it?

An exception usually passes through the `HandlerExceptionResolver` chain, including:

1. `ExceptionHandlerExceptionResolver` looks for `@ExceptionHandler` in the controller or `@ControllerAdvice`.
2. `ResponseStatusExceptionResolver` handles `@ResponseStatus`/`ResponseStatusException` and certain matching causes.
3. `DefaultHandlerExceptionResolver` translates standard Spring MVC exceptions into appropriate statuses.

`ResponseEntityExceptionHandler` is a useful base class for centralizing handling of known MVC exceptions; newer Spring versions support `ProblemDetail` per RFC 9457 (previously commonly referred to as RFC 7807). `@RestControllerAdvice` can be used to produce JSON responses for business exceptions.

Example:

~~~java
@RestControllerAdvice
class ApiExceptionAdvice {
    @ExceptionHandler(DependencyUnavailable.class)
    ProblemDetail dependencyDown(DependencyUnavailable ex) {
        ProblemDetail p = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        p.setTitle("Dependency unavailable");
        p.setDetail("Please retry later");
        p.setProperty("code", "UPSTREAM_UNAVAILABLE");
        return p;
    }
}
~~~

This is an integration snippet: `DependencyUnavailable` must be defined and `ProblemDetail`, `HttpStatus`, `ExceptionHandler` imported. The full demo is in section 10.

In Spring Boot 3.x, `spring.mvc.problemdetails.enabled=true` can enable `ProblemDetail` handling for MVC exceptions via auto-configuration; a separate `@ControllerAdvice` must consider **precedence order** and subclassing `ResponseEntityExceptionHandler` to avoid overlapping handlers. Do not create an `@ExceptionHandler(Exception.class)` that swallows every exception and always returns 200/400: that breaks the protocol and hides server bugs.

### 404/405/406/415 with advice

You do not have to write handlers for everything manually. You can let Spring handle built-in exceptions and only override when a specific error contract is needed. If overriding `handleHttpRequestMethodNotSupported` and omitting the `Allow` header, clients lose essential information. Likewise, media-type errors may carry relevant headers; preserve Spring-provided headers when customizing.

## 9. Asynchronous exceptions: requests can finish on a different dispatch

Spring MVC uses Servlet async with `Callable<T>`, `DeferredResult<T>`, `WebAsyncTask<T>`, and adapters for certain reactive return types. On initial entry, a controller can return an object representing unfinished work; `DispatcherServlet` releases the servlet thread while the request is in async state. When a result/error arrives, the Servlet container performs an **ASYNC dispatch** so MVC can complete the response.

### 9.1. Callable: exception thrown on a worker

~~~java
@GetMapping("/api/async/call")
Callable<String> call() {
    return () -> {
        // Executed later in AsyncTaskExecutor.
        throw new DependencyUnavailable();
    };
}
~~~

An exception inside `Callable` is **not thrown directly on the controller's initial call stack**. Spring MVC captures the exception result and routes it through exception handling after the async dispatch. An `@ExceptionHandler(DependencyUnavailable.class)` can generate the appropriate response.

Right mental model:

~~~text
GET /api/async/call
  -> Initial DispatcherServlet
  -> controller returns Callable
  -> startAsync; servlet request thread is released
  -> AsyncTaskExecutor runs Callable
  -> Callable throws DependencyUnavailable
  -> asyncDispatch back to MVC
  -> @RestControllerAdvice converts to HTTP 503 ProblemDetail
~~~

### 9.2. DeferredResult: setErrorResult to route errors back to MVC

~~~java
@GetMapping("/api/async/pending")
DeferredResult<String> pending() {
    DeferredResult<String> result = new DeferredResult<>(10_000L);
    taskRegistry.register(result);
    return result;
}

// When the external work fails:
result.setErrorResult(new DependencyUnavailable());
~~~

`taskRegistry` is an illustrative component. `setErrorResult(exception)` instructs Spring to complete the async request with an error result and pass the exception through resolvers upon dispatch. **Do not just log the error in a callback and leave the request unfinished**. Also cancel/clean up the task/registry in `onTimeout` and `onCompletion`.

### 9.3. Timeouts differ from business errors

Timeouts can occur at multiple layers:

- `DeferredResult(timeoutMillis)` or `WebAsyncTask`: limits Servlet async request processing time.
- `spring.mvc.async.request-timeout`: default MVC async timeout configuration (if the app uses Boot with that property).
- HTTP client (WebClient/RestClient): connect/read/response timeouts to upstream, occurring independently of MVC timeouts.
- Gateway/reverse proxy: may return 504 before Spring MVC finishes the response.
- Reactive `Mono.timeout(...)` when a controller returns a publisher: emits a Reactor timeout signal, which can be mapped to another response.

In default Spring MVC, `AsyncRequestTimeoutException` is typically handled as **503 Service Unavailable** if the response is not yet committed. Custom `@ExceptionHandler`s or interceptors can turn it into a different response. If the client already disconnected, the stream already sent headers/body, or the response is committed, **you can no longer arbitrarily change status/body**.

Do not assume 503 always means an async timeout: 503 can also come from server maintenance, overload, or app-specific mapping. Identify the exception class and execution timing.

### 9.4. Common async handling mistakes

- **Forgetting `asyncDispatch` in tests:** `MockMvc` reports that the initial request started async, while the test never observes the final HTTP status.
- **Blocking on the event loop:** if an MVC controller returns a `Mono` using WebClient, calling `block()` on a Reactor event loop can throw `IllegalStateException`. Compose publishers with `flatMap`/`zip` and only block at imperative boundaries on allowed threads.
- **Timeout occurred while worker keeps running:** an HTTP request timeout does not necessarily cancel external work or roll back remote operations; explicit cancellation/idempotency is needed.
- **Losing MDC/trace IDs:** requests may cross threads/dispatches. Use supported tracing/context propagation rather than assuming `ThreadLocal` carries everywhere.
- **Filters running only on REQUEST:** in Servlet async, mapping for the `ASYNC` dispatcher type may be needed to handle tracing/security properly, depending on configuration.

## 10. Spring Boot 3.x demo and MockMvc testing

The demo uses Spring Boot 3.x, Java 17+, Spring MVC, JUnit 5, and Bean Validation. Endpoints intentionally trigger conditions to observe each status and a business exception occurring in both `Callable` and `DeferredResult`.

Maven structure:

~~~text
spring-web-errors/
├── pom.xml
├── src/main/java/demo/ErrorDemoApplication.java
├── src/main/java/demo/DiagnosticController.java
├── src/main/java/demo/ApiErrorAdvice.java
└── src/test/java/demo/DiagnosticControllerTest.java
~~~

### 10.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>spring-web-errors</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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

### 10.2. src/main/java/demo/ErrorDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorDemoApplication.class, args);
    }
}
~~~

### 10.3. src/main/java/demo/DiagnosticController.java

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicReference;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
public class DiagnosticController {
    private final AtomicReference<DeferredResult<Item>> pending =
            new AtomicReference<>();

    public record Item(long id, String name) {}
    public record NewItem(@NotBlank String name) {}

    @GetMapping(
            path = "/api/items/1",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Item getItem() {
        return new Item(1, "Pen");
    }

    @PostMapping(
            path = "/api/items",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Item create(@Valid @RequestBody NewItem input) {
        return new Item(2, input.name());
    }

    @GetMapping("/api/quantity")
    public String quantity(@RequestParam @Min(1) int amount) {
        return "amount=" + amount;
    }

    @GetMapping("/api/async/callable")
    public Callable<Item> fromCallable() {
        return () -> {
            throw new DependencyUnavailable();
        };
    }

    @GetMapping("/api/async/deferred")
    public DeferredResult<Item> fromDeferred() {
        DeferredResult<Item> result = new DeferredResult<>(10_000L);
        pending.set(result);
        result.onCompletion(() -> pending.compareAndSet(result, null));
        return result;
    }

    // Package-scoped hook solely for the demo test to trigger the event.
    void failPending() {
        DeferredResult<Item> current = pending.get();
        if (current == null) {
            throw new IllegalStateException("No pending request");
        }
        current.setErrorResult(new DependencyUnavailable());
    }
}

class DependencyUnavailable extends RuntimeException {}
~~~

In `fromDeferred()`, a real application should not store a **single pending request in an AtomicReference** when serving multiple concurrent clients; it needs a per-request-ID registry, completion/timeout cleanup, and task limits. This demo structure is solely for testing one request at a time.

### 10.4. src/main/java/demo/ApiErrorAdvice.java

~~~java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorAdvice {
    @ExceptionHandler(DependencyUnavailable.class)
    public ProblemDetail dependencyUnavailable(DependencyUnavailable error) {
        ProblemDetail detail = ProblemDetail.forStatus(
                HttpStatus.SERVICE_UNAVAILABLE);
        detail.setTitle("Dependency unavailable");
        detail.setDetail("Please retry later");
        detail.setProperty("code", "UPSTREAM_UNAVAILABLE");
        return detail;
    }
}
~~~

This advice handles only **one business exception**, letting Spring MVC emit built-in statuses like 405, 406, 415, and validation 400 on its own. Because the returned `ProblemDetail` carries status 503, Spring MVC uses that status for the response. Do not include stack traces or internal details in the body.

### 10.5. src/test/java/demo/DiagnosticControllerTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(DiagnosticController.class)
class DiagnosticControllerTest {
    @Autowired MockMvc mvc;
    @Autowired DiagnosticController controller;

    @Test
    void missingRouteIs404() throws Exception {
        mvc.perform(get("/api/does-not-exist"))
            .andExpect(status().isNotFound());
    }

    @Test
    void wrongHttpMethodIs405() throws Exception {
        mvc.perform(post("/api/items/1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"X\"}"))
            .andExpect(status().isMethodNotAllowed())
            .andExpect(header().string(
                    HttpHeaders.ALLOW, containsString("GET")));
    }

    @Test
    void unacceptableAcceptIs406() throws Exception {
        mvc.perform(get("/api/items/1")
                .accept(MediaType.APPLICATION_XML))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void unsupportedContentTypeIs415() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.TEXT_PLAIN)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Pen\"}"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void validRequestSucceeds() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Pen\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(2))
            .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void malformedJsonIs400() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidBeanValidationIs400() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidMethodParameterIs400() throws Exception {
        mvc.perform(get("/api/quantity")
                .param("amount", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void callableErrorIsResolvedAfterAsyncDispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/callable"))
                .andExpect(request().asyncStarted())
                .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("UPSTREAM_UNAVAILABLE"))
            .andExpect(jsonPath("$.detail").value("Please retry later"));
    }

    @Test
    void deferredErrorIsResolvedAfterAsyncDispatch() throws Exception {
        MvcResult pending = mvc.perform(get("/api/async/deferred"))
                .andExpect(request().asyncStarted())
                .andReturn();

        controller.failPending();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("UPSTREAM_UNAVAILABLE"));
    }
}
~~~

`@WebMvcTest(DiagnosticController.class)` loads the MVC controller and `@ControllerAdvice` beans in the slice if they are component-scanned into the web slice. If a project customizes component scanning, `@Import(ApiErrorAdvice.class)` or slice-specific configuration may be required so the advice is present; tests can verify via the 503 response containing `code`.

**Most important detail when testing async:** the first `mvc.perform(get(...))` **is not the final response** when the method returns `Callable`/`DeferredResult`. Assert `request().asyncStarted()`, capture `MvcResult`, trigger the simulated outcome if needed, and then run `asyncDispatch(...)` to assert the final HTTP status/body. Without the second step, tests easily draw wrong conclusions about whether advice works.

### 10.6. Running Maven and checking results

Use JDK 17+ and Maven in the directory containing `pom.xml`:

~~~bash
mvn test
~~~

If classes are in the right packages and dependencies match what is shown, Maven is expected to finish with `BUILD SUCCESS`, 10 tests passing, and zero test failures. This is an **expectation from the illustrative code**, not output measured directly in this environment. If a test fails, read `target/surefire-reports` to inspect the actual exception and configuration; do not tweak expected statuses without understanding the source of the error.

Run the live API:

~~~bash
mvn spring-boot:run
~~~

Quick check:

~~~bash
curl -i http://localhost:8080/api/does-not-exist
curl -i -X POST http://localhost:8080/api/items/1 -H "Content-Type: application/json" -d '{"name":"X"}'
curl -i http://localhost:8080/api/items/1 -H "Accept: application/xml"
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: text/plain" -d '{"name":"Pen"}'
curl -i -X POST http://localhost:8080/api/items -H "Content-Type: application/json" -d '{"name":""}'
~~~

In the order above, the expected statuses are **404, 405, 406, 415, 400**. The async endpoints that throw an exception will return `503` via `ApiErrorAdvice`, provided the request finishes before timeout and the response has not yet been committed.

The `curl` example commands use common Bash CLI syntax; in Windows PowerShell, use `curl.exe` and that shell's JSON quoting rules.

## 11. Reading logs properly instead of guessing from status

During a real incident, collect these fields per request:

| Group | Example | Why it is needed |
| --- | --- | --- |
| Request | method, URI, query, `Accept`, `Content-Type` | Distinguish mapping/converter errors |
| Response | status, `Allow`, media type, duration | Pinpoint 405/406/415 and latency |
| Trace | request ID, trace ID, span ID | Link gateway → MVC → upstream |
| Exception | class, root cause, stack trace in server log | Distinguish validation, async timeout, upstream failure |
| Async | dispatcher type `REQUEST`/`ASYNC`, timeout config, completion | Tell whether the request switched thread/dispatch |
| Backend | database, HTTP client status/latency, thread pool/queue | Identify which layer actually failed |

Do not log tokens, passwords, private contents, or entire multipart files just to debug 400/415. When encountering `HttpMessageNotReadableException`, log safely with just enough detail to reproduce the schema/sample body with sensitive data masked.

A concrete investigation flow:

1. If **404**, verify gateway routing, controller scanning, path variables, and static mappings; compare against paths in request logs.
2. If **405**, inspect `Allow` and check the actual request method, including whether a browser sent preflight `OPTIONS` or a client sent the request.
3. If **406**, print `Accept`, `produces`, and the list of converters supported by the app.
4. If **415**, print `Content-Type`, `consumes`, and body shape; retry with the right header.
5. If **400 validation**, read field/type/constraint errors and separate JSON parser errors.
6. If **5xx/async timeout**, trace initial dispatch, worker/publisher, async dispatch, and advice; check whether the response was committed, proxy timeouts, and external services.

In Spring Boot, you can use Actuator HTTP server metrics and tracing if configured, combined with request correlation IDs. Do not turn on DEBUG/TRACE across all traffic long-term in production when sensitive data is present.

## 12. Common misconceptions

### 12.1. "404 means my @ExceptionHandler failed to catch the business exception"

The endpoint may not have routed to the controller, or the static resource handler emitted 404. Distinguish using traces, handler mappings, and exception types; not every 404 is a business exception.

### 12.2. "405 means the controller does not exist"

405 usually means the path was recognized, while the HTTP method did not match. Inspect the `Allow` response header and request method, then check `@GetMapping`/`@PostMapping`.

### 12.3. "If the JSON body is valid, it cannot return 415"

The declared `Content-Type` determines the `consumes`/converter check. JSON text labeled `text/plain` can still fail with 415; broken JSON with the right content type usually produces 400.

### 12.4. "Getting 406 on Accept: application/xml means data is missing"

406 is about response representation, not missing records. When reporting that a record does not exist, business logic returns 404 independently of the client choosing a valid media type.

### 12.5. "Every 400 comes from @Valid"

Missing parameters, wrong path variable types, and malformed JSON bodies are also common 400s. Check the exception class and test each failure boundary.

### 12.6. "If an exception happens in CompletableFuture/Callable, @ControllerAdvice won't run"

For async return types supported by Spring MVC when the exception is **passed into the MVC lifecycle** (e.g., `Callable` throws or `DeferredResult.setErrorResult(exception)`), the request is async-dispatched and handled normally by exception resolvers. However, an exception swallowed inside a fire-and-forget thread/`@Async void` will not automatically alter an already-completed request response.

### 12.7. "Async request timeout is always HTTP 504"

Default MVC typically returns 503 for `AsyncRequestTimeoutException` when uncommitted; 504 usually comes from a gateway/proxy or custom mapping. Check which layer produced the response.

### 12.8. "Tests only need to assert exceptions thrown by controller methods"

In MVC, errors can happen **before the method is invoked** (mappings, converters, binding) or **after initial dispatch** (async). `MockMvc` exercises the whole request pipeline and requires `asyncDispatch` for asynchronous results.

## 13. Notes on WebFlux and reactive errors

In Spring WebFlux, instead of Servlet `DispatcherServlet`, there is reactive `DispatcherHandler` along with `WebFilter`/`WebExceptionHandler` components. HTTP semantics remain 404/405/406/415/400, while exception classes typically belong to different reactive/server packages, such as `ResponseStatusException`, `ServerWebInputException`, or `WebExchangeBindException` for binding/validation. Do not apply the MVC exception list verbatim to WebFlux.

With a controller returning `Mono`/`Flux`:

~~~java
@GetMapping("/api/reactive/item")
Mono<Item> reactive() {
    return webClient.get()
            .uri("/upstream/item")
            .retrieve()
            .bodyToMono(Item.class)
            .onErrorMap(WebClientRequestException.class,
                    error -> new DependencyUnavailable());
}
~~~

This is an integration snippet (requiring `webClient` and `Item`/`DependencyUnavailable` classes). If the exception is a **reactive error signal** from a publisher subscribed by Spring WebFlux during the request lifecycle, it can be handled by an exception handler; if the application calls `subscribe()` manually and returns 200 immediately, errors raised outside the lifecycle cannot retroactively change the sent status. Likewise, do not block the Reactor event loop while fixing async errors; compose publishers with operators.

Use `WebTestClient` or reactive integration tests to assert actual status/body, and distinguish `WebClientResponseException` (upstream returned an HTTP error response) from `WebClientRequestException` (request/network failure). If forwarding the raw upstream status to the client is desired, make an explicit business decision rather than defaulting to 500.

## 14. Practical checklist

- [ ] Record the exact method, URL, `Content-Type`, `Accept`, query, payload shape, and request ID before changing code.
- [ ] For 404: verify mappings, static resources, and business not-found separately.
- [ ] For 405: read `Allow`; check the HTTP method and mappings.
- [ ] For 406: check `Accept`, `produces`, and response-side message converters.
- [ ] For 415: check `Content-Type`, `consumes`, and input-side converters.
- [ ] For 400: separate parse/binding/validation; report field errors in a controlled manner.
- [ ] For `Callable`/`DeferredResult`: ensure exceptions flow into the async result and use `asyncDispatch` in MockMvc.
- [ ] For timeouts: verify whether the timeout occurred in MVC, HTTP client, or gateway; check whether the response was already committed.
- [ ] For `@ControllerAdvice`: preserve standard statuses/headers and check handler conflicts/precedence; do not swallow all errors.
- [ ] Maintain negative/boundary tests, request correlation, safe logging, and grouped error-rate metrics.

**Key principle:** identify **which stage the request failed at** before editing controllers or advice. 404/405 are routing clues, 406/415 are negotiation/converter issues, validation is typically 400, and async exceptions require the follow-up dispatch and a transparent error-handling policy.

## 15. Official references

- Spring Framework — Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — REST Error Responses and `ProblemDetail`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework — MVC Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Method Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Exception Handling: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Spring Framework — MockMvc Async Requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110.html
