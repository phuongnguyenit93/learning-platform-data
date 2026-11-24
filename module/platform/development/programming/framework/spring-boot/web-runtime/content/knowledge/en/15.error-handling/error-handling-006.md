# ProblemDetail, ErrorResponse, and Stack-Specific Problem Details Configuration in Spring Boot

## 1. Lesson Objectives

A REST API should never return errors in inconsistent formats across endpoints—such as `{"message":"fail"}`, plain text strings, HTML error pages, or stacktraces. Clients need a **consistent error contract** to read the HTTP status, identify the error type, display a safe message, and correlate with server logs when needed.

Spring Framework supports **Problem Details for HTTP APIs** per **RFC 9457** through three key concepts:

- `ProblemDetail`: an object describing an HTTP error using the standard fields `type`, `title`, `status`, `detail`, and `instance`.
- `ErrorResponse`: a Java contract representing **status + headers + ProblemDetail body**, commonly implemented by framework exceptions.
- `ErrorResponseException`: a built-in exception implementing `ErrorResponse`; `ResponseStatusException` is a familiar subclass.

Spring Boot provides properties to enable Problem Details handling for known HTTP exceptions, but **Spring MVC and Spring WebFlux use different properties**. The goal of this lesson is to understand the RFC 9457 structure, default behavior, how to configure each stack, how to return controlled business errors, security, and testing.

Hands-on examples target **Spring Boot 3.5.x, Spring Framework 6.2.x, Java 17**. For other major versions, check packages, starters, auto-configuration, and error-handling behavior.

## 2. RFC 9457: A Structured Standard Error Response

Example API response for a missing resource:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://example.org/problems/item-not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 27 does not exist",
  "instance": "/api/items/27",
  "code": "ITEM_NOT_FOUND"
}
```

The five standard members of Problem Details:

| Field | Type | Meaning |
|---|---|---|
| `type` | URI reference | Identifies the **problem type**; errors of the same type can share a URI |
| `title` | String | Short description, typically stable for a given problem type |
| `status` | Integer | Corresponding HTTP status, e.g., 400, 404, 409, 500 |
| `detail` | String | More specific explanation for **this occurrence** of the error |
| `instance` | URI reference | Identifies the specific occurrence or context instance of the error |

Fields may be omitted depending on how the response is constructed and serialized; not every response must contain all five. Per the RFC, `type` defaults to `about:blank` when omitted, conveying generic semantics aligned with the HTTP status. `status` in the body should match the **actual HTTP status**; never emit an HTTP 200 response whose JSON claims `"status":404`.

`code` in the example is an application-defined **extension member**, not one of the five standard fields. Using a stable `code` lets clients distinguish `ITEM_NOT_FOUND`, `EMAIL_ALREADY_USED`, or `QUOTA_EXCEEDED` without parsing prose in `detail`.

The standard JSON media type is **`application/problem+json`**. Do not confuse it with regular `application/json` or `application/problem+xml` when appropriate XML codecs are configured.

## 3. ProblemDetail in Spring Framework

Imports:

```java
import org.springframework.http.ProblemDetail;
import org.springframework.http.HttpStatus;
```

Common creation methods:

```java
ProblemDetail a = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

ProblemDetail b = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Resource not found");
```

Setting fields:

```java
b.setTitle("Resource not found");
b.setType(java.net.URI.create(
        "https://example.org/problems/not-found"));
b.setProperty("code", "RESOURCE_NOT_FOUND");
```

Key methods to remember include `forStatus(...)`, `forStatusAndDetail(...)`, `getStatus()`, `setTitle(...)`, `setType(...)`, `setDetail(...)`, `setInstance(...)`, `setProperty(...)`, and `getProperties()`.

In Spring Framework 6.2, when returning `ProblemDetail` from an `@ExceptionHandler`, the framework may automatically populate `instance` with the request path if unset. **This behavior depends on version and rendering path**; do not assume every Spring Framework version or every response from `/error` produces an identical `instance`.

`ProblemDetail` is only a response model object. **Constructing it does not throw an exception on its own.** A controller must return it, return `ResponseEntity<ProblemDetail>`, or throw an exception with an appropriate handler.

`type` does not have to resolve to a live website, though for public APIs you should pick a stable URI managed by your organization, ideally backed by documentation. The URL `https://example.org/problems/...` in this article is merely an illustrative placeholder.

## 4. ErrorResponse: Not Synonymous with ProblemDetail

`ErrorResponse` is an interface at:

```java
import org.springframework.web.ErrorResponse;
```

Important methods:

| API | Meaning |
|---|---|
| `getStatusCode()` | HTTP status of the response |
| `getHeaders()` | Accompanying HTTP response headers |
| `getBody()` | `ProblemDetail` describing the error |
| `getTypeMessageCode()` | Message code used to localize `type` |
| `getTitleMessageCode()` | Message code used to localize `title` |
| `getDetailMessageCode()` | Message code used to localize `detail` |
| `getDetailMessageArguments()` | Arguments for localized messages |

Key distinctions:

- **`ProblemDetail`** is the RFC 9457 body payload.
- **`ErrorResponse`** is the contract carrying **HTTP status, headers, and body**, enabling Spring Framework to represent an exception as a structured HTTP response.
- `ErrorResponse` is a Java interface, not a JSON field or an `/error` endpoint.
- Many built-in Spring MVC/WebFlux web exceptions implement `ErrorResponse`, preserving their standard statuses and headers.

For example, a `405 Method Not Allowed` error may require the `Allow` response header; do not rewrite all 405 errors into custom `ProblemDetail` responses if doing so strips standard headers. `ErrorResponse` preserves required headers.

## 5. ErrorResponseException and ResponseStatusException

`ErrorResponseException` is a built-in implementation of `ErrorResponse` with a constructor taking a status and `ProblemDetail`:

```java
ProblemDetail conflict = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Item code is already in use");
conflict.setType(java.net.URI.create(
        "https://example.org/problems/item-code-conflict"));
conflict.setProperty("code", "ITEM_CODE_CONFLICT");

throw new org.springframework.web.ErrorResponseException(
        HttpStatus.CONFLICT, conflict, null);
```

This code is an **in-method fragment** requiring `HttpStatus` and `ProblemDetail` imports. The third constructor argument is the cause, `null` here. When caught by an appropriate `ErrorResponse` handler, the HTTP status is **409 Conflict** and the body follows Problem Details structure. Do not assume every filter or proxy can process this exception if thrown outside a handler.

`ResponseStatusException` usually fits simpler cases:

```java
throw new org.springframework.web.server.ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Item not found");
```

In Spring Framework 6.2, `ResponseStatusException` extends `ErrorResponseException`; its `reason` value is used as the default `detail`. If you need a `type` URI, `code`, or extra properties, use a custom `ProblemDetail` or a dedicated exception.

For business errors reused across controllers, define dedicated exceptions or error codes rather than repeating `ResponseStatusException` with unstable message strings.

## 6. Enabling Problem Details per Spring Boot Web Stack

In **Spring Boot 3.5**, the following properties have distinct meanings:

| Web stack | Property | 3.5 Default | When Enabled |
|---|---|---|---|
| Spring MVC/Servlet | `spring.mvc.problemdetails.enabled` | `false` | Auto-configures Problem Details handling for built-in MVC exceptions |
| Spring WebFlux/Reactive | `spring.webflux.problemdetails.enabled` | `false` | Auto-configures Problem Details handling for built-in WebFlux exceptions |

**Spring MVC** project example:

```properties
spring.mvc.problemdetails.enabled=true
```

**Spring WebFlux** project example:

```properties
spring.webflux.problemdetails.enabled=true
```

Or in YAML:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

For a WebFlux project, change `mvc` to `webflux`.

**Do not blindly set both properties** when only one web stack is active: the inactive stack's property has no effect on the active stack's exception handling. If an application has both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot typically prefers **SERVLET/MVC**, even if `WebClient` is on the classpath. Inspect the dependency tree and `WebApplicationType` before wondering why enabling the WebFlux property had no effect.

Enabling Problem Details does **not** mean every arbitrary exception, filter failure, or reverse proxy error is turned into RFC 9457. Distinguish the layers in the sections below.

## 7. Error Handling Flow in Spring MVC

Simplified flow with `@RestController`:

```text
HTTP request
    |
    v
Servlet Filter Chain
    |
    v
DispatcherServlet
    |
    v
HandlerMapping -> HandlerAdapter -> Controller
    |
    +-- success --> HttpMessageConverter --> response
    |
    +-- exception
           |
           v
     HandlerExceptionResolver chain
        |
        +-- @ExceptionHandler / @ControllerAdvice
        +-- ResponseStatusExceptionResolver
        +-- DefaultHandlerExceptionResolver
           |
           v
     ProblemDetail / ErrorResponse or handler-specific response
           |
           v
     HTTP status + headers + body
```

Spring Boot also has the **`/error`** path with `BasicErrorController` and `ErrorAttributes` for errors routed by the container/framework to error dispatch. When `spring.mvc.problemdetails.enabled=true` is enabled, Boot auto-configures a `ResponseEntityExceptionHandler` to process built-in MVC exceptions as Problem Details. This **does not replace the entire `/error` mechanism** in all situations.

For instance, an error inside a controller handled by `@RestControllerAdvice` is turned into a response directly during MVC exception resolution. However, exceptions thrown **before entering DispatcherServlet** (Servlet filters, Servlet container) may follow a different path.

Handling order matters: a custom `@ControllerAdvice` covering the same exception types needs appropriate ordering, especially since Spring Boot registers its Problem Details handler at order **0**.

## 8. Error Handling Flow in Spring WebFlux

Spring WebFlux uses `DispatcherHandler` instead of `DispatcherServlet`:

```text
HTTP request
    |
    v
Reactive web server (usually Reactor Netty)
    |
    v
HttpHandler + WebFilter chain
    |
    v
DispatcherHandler
    |
    +-- annotated @RestController / functional RouterFunction
    |
    +-- exception or Mono.error(...)
           |
           +-- @ExceptionHandler / @RestControllerAdvice
           |
           +-- WebExceptionHandler / ErrorWebExceptionHandler
           |
           v
     ProblemDetail / ServerResponse / appropriate response
```

Reactive Spring Boot provides an error handler based on `ErrorWebExceptionHandler`; `DefaultErrorWebExceptionHandler` and `ErrorAttributes` supply the default error mechanism when no specific handler applies. Enabling `spring.webflux.problemdetails.enabled=true` adds RFC 9457 handling for built-in WebFlux exceptions in the controller stack.

Distinguish three groups:

1. **Annotated controllers:** use `@ExceptionHandler`/`@RestControllerAdvice`; Spring WebFlux supports `ProblemDetail`.
2. **Functional endpoints:** can handle errors via Reactor operators, handler functions, or let exceptions reach the reactive error infrastructure.
3. **WebFilter/HTTP server/parser:** errors can arise before a controller handler is selected; not every error passes through `@RestControllerAdvice`.

Do not call `.block()` inside a WebFlux handler just to build an error response; return `Mono.error(...)`, `ProblemDetail`, or `Mono<ResponseEntity<...>>` matching the method signature.

## 9. Returning ProblemDetail from @ExceptionHandler

A flexible pattern is catching a business exception and returning `ProblemDetail`:

```java
@ExceptionHandler(ItemNotFoundException.class)
public ProblemDetail handleNotFound(ItemNotFoundException ex) {
    ProblemDetail pd = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Item " + ex.getItemId() + " not found");
    pd.setTitle("Item not found");
    pd.setType(URI.create(
            "https://example.org/problems/item-not-found"));
    pd.setProperty("code", "ITEM_NOT_FOUND");
    return pd;
}
```

This snippet is a method inside a `@RestControllerAdvice` class, requiring `ItemNotFoundException` with `getItemId()`, and imports for `URI`, `ProblemDetail`, `HttpStatus`, and `ExceptionHandler`. The full MVC example is below.

When returning `ProblemDetail`, Spring Framework 6.2 uses the object's `status` to set the HTTP status and prefers dedicated media types like `application/problem+json` when JSON serialization is available.

**Do not return `ResponseEntity.ok(problem)`** if `problem.getStatus()` is 404: an HTTP **200** response carrying a 404 body is inconsistent. If using `ResponseEntity`, set the matching status:

```java
return ResponseEntity.status(HttpStatus.NOT_FOUND).body(pd);
```

When headers like `Retry-After`, `WWW-Authenticate`, or `Allow` are needed, preserve required headers per the HTTP contract. Never replace built-in exception responses just to alter a title/message if doing so drops essential headers.

## 10. Spring Boot MVC: Java 17 Sample Project

Create a **Spring Boot 3.5.x**, Java 17 Maven project with a Boot parent or dependency management. Dependencies:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

This is only the `<dependencies>` section for a `pom.xml` whose versions are already managed by Spring Boot, not a full standalone POM.

Structure:

```text
src/main/java/com/example/problem/mvc/
    MvcApplication.java
    ItemController.java
    ItemNotFoundException.java
    ItemProblemAdvice.java
src/main/resources/
    application.properties
src/test/java/com/example/problem/mvc/
    ItemControllerTest.java
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
spring.mvc.problemdetails.enabled=true

# Prevent exposing exceptions/stacktraces by default in /error
server.error.include-exception=false
server.error.include-stacktrace=never
server.error.include-message=never
```

The `server.error.*` properties relate to Boot's error attributes mechanism, not how every `ProblemDetail` created by `@ExceptionHandler` is customized. To customize Problem Details content, use advice, `MessageSource`, or appropriate extension hooks.

## 11. MVC: Main Class and Domain Exception

File `src/main/java/com/example/problem/mvc/MvcApplication.java`:

```java
package com.example.problem.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
```

File `src/main/java/com/example/problem/mvc/ItemNotFoundException.java`:

```java
package com.example.problem.mvc;

public class ItemNotFoundException extends RuntimeException {

    private final long itemId;

    public ItemNotFoundException(long itemId) {
        super("Item not found");
        this.itemId = itemId;
    }

    public long getItemId() {
        return itemId;
    }
}
```

This exception stores only `itemId` so the advice can construct a controlled response. Never stuff sensitive data, SQL exceptions, or tokens into client-facing `detail`. If you need to log the underlying error, log on the server with a request ID rather than exposing the full `exception.getMessage()`.

## 12. MVC: @RestController and Request Validation

File `src/main/java/com/example/problem/mvc/ItemController.java`:

```java
package com.example.problem.mvc;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{id}")
    public Item find(@PathVariable("id") long id) {
        if (id == 7) {
            return new Item(7, "Java Book");
        }
        throw new ItemNotFoundException(id);
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Item> create(
            @Valid @RequestBody NewItem input) {
        Item created = new Item(8, input.name());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    public record Item(long id, String name) {
    }

    public record NewItem(@NotBlank String name) {
    }
}
```

This controller illustrates error handling only:

- `GET /api/items/7` returns normal JSON.
- `GET /api/items/27` throws `ItemNotFoundException` so the advice returns Problem Details.
- `POST /api/items` accepts JSON and runs `@Valid` on `NewItem`.
- JSON with an empty `name` triggers a validation error; with `spring.mvc.problemdetails.enabled=true`, the built-in MVC exception handler can return 400 Problem Details.
- The example has no database; creating item ID 8 is illustrative only and not a complete item persistence service.

## 13. MVC: @RestControllerAdvice for Business Errors

File `src/main/java/com/example/problem/mvc/ItemProblemAdvice.java`:

```java
package com.example.problem.mvc;

import java.net.URI;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(-1)
public class ItemProblemAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ProblemDetail itemNotFound(ItemNotFoundException ex) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Item " + ex.getItemId() + " not found");

        pd.setTitle("Item not found");
        pd.setType(URI.create(
                "https://example.org/problems/item-not-found"));
        pd.setProperty("code", "ITEM_NOT_FOUND");
        return pd;
    }
}
```

`@Order(-1)` lets this advice be evaluated before Boot's default Problem Details advice, which has order 0 (in Boot 3.5). In the demo, the advice catches only `ItemNotFoundException`, not all `RuntimeException` or `Exception` types. Framework errors like validation or wrong HTTP methods still pass through the default handler.

If a system has multiple `@ControllerAdvice` beans, verify their order and scope. Never create a catch-all at `@Order(HIGHEST_PRECEDENCE)` that accidentally turns `MethodArgumentNotValidException` or `HttpRequestMethodNotSupportedException` into 500.

When Jackson serializes `ProblemDetail`, extension properties are promoted to top-level JSON fields thanks to Spring's registered `ProblemDetailJacksonMixin`. For example, the response contains `"code":"ITEM_NOT_FOUND"` rather than always nesting inside a `"properties":{...}` object.

## 14. Running and Testing MVC with curl

In the project directory containing the Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Valid request:

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/7
```

Expected body:

```json
{"id":7,"name":"Java Book"}
```

Missing item request:

```bash
curl -i -H 'Accept: application/problem+json' \
  http://localhost:8080/api/items/27
```

In this sample setup, the HTTP status is 404, `Content-Type` is compatible with `application/problem+json`, and the main fields may look like:

```json
{
  "type": "https://example.org/problems/item-not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 27 not found",
  "instance": "/api/items/27",
  "code": "ITEM_NOT_FOUND"
}
```

`instance` in Spring Framework 6.2 is populated from the path when the response passes through `@ExceptionHandler` and `instance` was not set. On other versions, test against actual framework output and your RFC contract rather than treating every default detail as immutable.

Invalid request body:

```bash
curl -i -X POST \
  -H 'Accept: application/problem+json' \
  -H 'Content-Type: application/json' \
  --data '{"name":""}' \
  http://localhost:8080/api/items
```

With a Bean Validation provider installed, the result is typically HTTP 400 from built-in exception handling. Do not predict the exact `detail` of validation errors: it can vary by locale, `MessageSource` config, or Spring Framework version.

Valid JSON request:

```bash
curl -i -X POST \
  -H 'Accept: application/json' \
  -H 'Content-Type: application/json' \
  --data '{"name":"Pen"}' \
  http://localhost:8080/api/items
```

Expected 201 Created, body:

```json
{"id":8,"name":"Pen"}
```

These response codes and bodies assume requests reach the demo server directly without Spring Security, reverse proxies, or extra custom exception handlers.

## 15. MockMvc: Testing RFC 9457 on MVC

Add the test dependency in a Maven project with dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/problem/mvc/ItemControllerTest.java`:

```java
package com.example.problem.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void itemNotFoundReturnsProblem() throws Exception {
        mvc.perform(get("/api/items/27")
                .accept(MediaType.valueOf("application/problem+json")))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ITEM_NOT_FOUND"))
            .andExpect(jsonPath("$.type").value(
                    "https://example.org/problems/item-not-found"));
    }

    @Test
    void beanValidationReturnsBadRequest() throws Exception {
        mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.valueOf("application/problem+json"))
                .content("{\"name\":\"\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json")))
            .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void validGetReturnsJson() throws Exception {
        mvc.perform(get("/api/items/7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Java Book"));
    }
}
```

Run:

```bash
./mvnw test
```

The tests check only reliable contract fields (status, media type, error code). Avoid asserting the entire JSON payload or i18n messages when they are not part of a fixed contract. To test byte-level HTTP behavior, add integration tests with a real embedded server, since MockMvc does not open a socket.

If Spring Security is present in a project, configure test authentication/CSRF appropriately; these tests assume the security starter is not added.

## 16. Spring WebFlux: Separate Reactive Project

To demonstrate configuring the other web stack, create a **second project** using Spring Boot 3.5, Java 17, with only `spring-boot-starter-webflux` and the test starter. Do not put both MVC and WebFlux examples with identical routes in the same application context.

In `pom.xml` with Boot-managed versions:

```xml
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
```

Structure:

```text
src/main/java/com/example/problem/reactive/
    ReactiveApplication.java
    ReactiveItemController.java
    ReactiveProblemAdvice.java
src/main/resources/
    application.properties
src/test/java/com/example/problem/reactive/
    ReactiveItemControllerTest.java
```

Properties file:

```properties
server.port=8080
spring.webflux.problemdetails.enabled=true
```

This is the right property for **Reactive**. Using `spring.mvc.problemdetails.enabled=true` in a reactive project does not replace this setting.

## 17. WebFlux: Main Class and Reactive Controller

File `src/main/java/com/example/problem/reactive/ReactiveApplication.java`:

```java
package com.example.problem.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
```

File `src/main/java/com/example/problem/reactive/ReactiveItemController.java`:

```java
package com.example.problem.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ReactiveItemController {

    @GetMapping("/{id}")
    public Mono<Item> get(@PathVariable("id") long id) {
        if (id == 7) {
            return Mono.just(new Item(7, "Java Book"));
        }
        return Mono.error(new MissingItem(id));
    }

    public record Item(long id, String name) {
    }

    public static class MissingItem extends RuntimeException {
        private final long itemId;

        public MissingItem(long itemId) {
            super("Item not found");
            this.itemId = itemId;
        }

        public long getItemId() {
            return itemId;
        }
    }
}
```

`Mono.error(new MissingItem(id))` emits an error signal in the reactive pipeline. Never call `.block()` inside an annotated controller.

In real apps, `Mono<Item>` typically comes from a reactive repository or upstream `WebClient`; you can use `switchIfEmpty(Mono.error(...))` to turn a missing-result case into an exception. Do not assume `Mono.empty()` automatically becomes 404: if a not-found contract is required, express it explicitly.

## 18. WebFlux: @RestControllerAdvice Creating ProblemDetail

File `src/main/java/com/example/problem/reactive/ReactiveProblemAdvice.java`:

```java
package com.example.problem.reactive;

import java.net.URI;

import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(-1)
public class ReactiveProblemAdvice {

    @ExceptionHandler(ReactiveItemController.MissingItem.class)
    public ProblemDetail notFound(
            ReactiveItemController.MissingItem error) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Item " + error.getItemId() + " not found");

        pd.setTitle("Item not found");
        pd.setType(URI.create(
                "https://example.org/problems/item-not-found"));
        pd.setProperty("code", "ITEM_NOT_FOUND");
        return pd;
    }
}
```

This is a practical `@RestControllerAdvice` for an annotated WebFlux controller. To integrate WebFlux built-in errors as Problem Details, `spring.webflux.problemdetails.enabled=true` is enabled.

The handler returns a **ProblemDetail object**, and the framework converts it into HTTP 404. No manual JSON encoding or `ResponseEntity.ok(...)` is needed.

To handle exceptions from **functional WebFlux endpoints**, use `onErrorResume`/`ServerResponse` in the pipeline or an appropriate `ErrorWebExceptionHandler`. A `@RestControllerAdvice` is not a global guarantee covering all errors from functional routes and `WebFilter`s.

## 19. WebTestClient: Testing WebFlux

File `src/test/java/com/example/problem/reactive/ReactiveItemControllerTest.java`:

```java
package com.example.problem.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveItemControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void missingItemReturnsProblem() {
        client.get()
            .uri("/api/items/27")
            .accept(MediaType.valueOf("application/problem+json"))
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.valueOf("application/problem+json"))
            .expectBody()
            .jsonPath("$.status").isEqualTo(404)
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void validItemReturnsJson() {
        client.get()
            .uri("/api/items/7")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.name").isEqualTo("Java Book");
    }
}
```

`RANDOM_PORT` starts an embedded reactive server on a random port, testing real HTTP over the server. Test package names and auto-configuration APIs here target **Spring Boot 3.5** and do not automatically match imports in Spring Boot 4.x.

Run inside the WebFlux project:

```bash
./mvnw test
```

Do not run both the MVC and WebFlux demos simultaneously on `server.port=8080` on the same machine unless you want a port conflict.

## 20. ResponseEntityExceptionHandler: When Is It Needed?

Spring Framework provides `ResponseEntityExceptionHandler` to handle common web exceptions with `ErrorResponse`/Problem Details structure.

The two web stacks have **different packages**:

```java
// Spring MVC
org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler
```

```java
// Spring WebFlux
org.springframework.web.reactive.result.method.annotation
        .ResponseEntityExceptionHandler
```

These two snippets show **qualified names wrapped across lines for readability**, not literal valid Java imports. In real Java code, an import statement must stay on a single line.

In **Boot 3.5**, when `spring.mvc.problemdetails.enabled=true` or `spring.webflux.problemdetails.enabled=true`, Boot auto-configures a `ResponseEntityExceptionHandler` for built-in errors of the active stack.

Therefore:

- If you only need **a few business errors**, use a separate `@RestControllerAdvice` with `@ExceptionHandler(MyDomainException.class)` as shown, avoiding taking over all built-in exceptions.
- If you need to customize **specific built-in exceptions**, write an advice ordered ahead of Boot's advice (order less than 0), or explicitly manage a `ResponseEntityExceptionHandler` subclass per application config.
- If subclassing and overriding multiple methods, use the method signatures for the **exact Spring Framework version**, since MVC and WebFlux parameters differ (`WebRequest` vs. `ServerWebExchange`).
- Avoid multiple advices catching `Exception.class` without explicit ordering: it can easily turn 400/404 into 500 or unintentionally change response headers.

Some built-in errors require keeping framework statuses/headers—for example, 405 needs `Allow`, 415 needs accepted media types, and 401 needs `WWW-Authenticate` per the security mechanism. A catch-all returning `ProblemDetail.forStatus(INTERNAL_SERVER_ERROR)` for every exception is bad design.

## 21. Validation Errors: 400 Does Not Mean Arbitrary Business Error

In Spring MVC:

```java
@PostMapping("/api/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // ...
}
```

When `@Valid` detects a Bean Validation violation without an adjacent `BindingResult` parameter for the handler to inspect, Spring MVC normally throws `MethodArgumentNotValidException`. Spring Framework 6.1+ adds `HandlerMethodValidationException` for method-level validation under separate rules.

With WebFlux annotated controllers, binding/validation errors are represented by `WebExchangeBindException`, or `HandlerMethodValidationException` when method validation applies.

Do not assume the default built-in `ProblemDetail` provides a stable public schema for field-level errors. If the frontend needs a per-field error list:

```json
{
  "type": "https://example.org/problems/validation",
  "title": "Invalid data",
  "status": 400,
  "detail": "Please fix the highlighted fields",
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field": "name", "code": "NotBlank"}
  ]
}
```

`violations` is an **API-designed extension**, not a standard RFC 9457 field or guaranteed in every Boot app by default. Decide whether exposing field names and rejected values is acceptable; strictly avoid returning passwords, access tokens, and raw request bodies in validation errors.

For unparseable JSON, `HttpMessageNotReadableException` (MVC) can occur before any object is instantiated; never pass raw parser messages containing payloads directly into `detail` sent to clients.

## 22. Adding Extension Fields and Correlation IDs

`ProblemDetail.setProperty("code", "ITEM_NOT_FOUND")` adds extension fields. With Spring-configured Jackson, the `properties` map is **unwrapped** to top-level JSON fields.

Common extensions:

- `code`: machine-readable error code, stable across API versions.
- `traceId`: trace identifier linking to logs/metrics; never place sensitive data inside.
- `requestId`: request correlation ID generated or verified by the server.
- `violations`: field error list with a clear schema.
- `retryable`: only when retry semantics are clearly contracted, never blindly attached to all 500s.

Example:

```java
ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.CONFLICT);
pd.setProperty("code", "DUPLICATE_ITEM");
pd.setProperty("traceId", traceId);
```

This is a fragment; `traceId` must come from real, controlled tracing/observability infrastructure. Never copy an arbitrary client-supplied header directly into `traceId` without validation.

Spring Framework 6.2 provides **`ErrorResponse.Interceptor`** to add or customize Problem Details data from a central hook. It can be registered through `WebMvcConfigurer` or `WebFluxConfigurer` as appropriate. This is useful for attaching tracking IDs across many error responses instead of duplicating code in every advice; check the exact callback signature for your Framework version.

## 23. I18n: type, title, and detail via MessageSource

`ErrorResponse` provides message codes so Spring can use `MessageSource` to localize messages. In Spring Framework 6.2, default rules typically derive from the fully qualified exception class name:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.<fully-qualified-exception-class>
```

The message code for `detail` can also include specific suffixes for cases like unsupported media types or validation.

Example application-defined messages in `src/main/resources/messages_vi.properties`:

```properties
problemDetail.org.springframework.web.bind.MethodArgumentNotValidException=Submitted data is invalid
```

This line merely **illustrates the class-based message code structure**; for a specific built-in exception, verify the exact class name and message arguments in your MVC/WebFlux version. In particular, Spring Framework distinguishes request body validation classes from method validation classes.

`title` typically describes the problem category and can be translated; `detail` explains the specific occurrence. Avoid using `detail` prose as an **identifier** for frontend branching because wording can change by locale. Clients should rely on `type`/extension `code`.

If the app switches locales by `Accept-Language`, test message selection and caching headers whenever responses vary in language per request. Never assume exceptions are automatically translated without configuring `MessageSource`.

## 24. Distinguishing ErrorResponse, ErrorAttributes, and /error

In Boot, multiple handling layers exist:

| Component | MVC or WebFlux? | Role |
|---|---|---|
| `ProblemDetail` | Both | RFC 9457 error body model |
| `ErrorResponse` | Both | Java contract: HTTP status, headers, ProblemDetail |
| `ErrorResponseException` | Both | Exception implementing ErrorResponse |
| `ResponseStatusException` | Both | Exception setting HTTP status/reason |
| `ResponseEntityExceptionHandler` | Separate class per stack | Handles built-in web exceptions |
| `BasicErrorController` | MVC/Servlet Boot | Handles errors via `/error` mechanism |
| `ErrorAttributes` | Boot, stack-specific packages | Collects data for default error responses |
| `ErrorWebExceptionHandler` | WebFlux Boot | Handles errors in reactive HTTP handler chain |
| `@RestControllerAdvice` | Annotated controllers | Handles exceptions in controller pipeline |

`ErrorAttributes` is **not** `ErrorResponse`. Setting `server.error.include-message=always` does not produce Problem Details and can expose internal messages from `/error`. Never enable `server.error.include-stacktrace=always` in production just for debugging convenience.

When customizing domain errors for REST controllers, prefer advice. When controlling error responses across the entire reactive handler chain (including functional endpoints or pre-controller errors), look at `ErrorWebExceptionHandler`. In MVC, inspect the Servlet/filter/container and `/error` mechanisms.

## 25. HTTP Status, Content-Type, and Content Negotiation

RFC 9457 does not replace HTTP semantics. Use appropriate statuses:

| Status | Typical Scenario |
|---|---|
| 400 Bad Request | Invalid input syntax or failed validation |
| 401 Unauthorized | Unauthenticated, may require `WWW-Authenticate` |
| 403 Forbidden | Client identified but access denied |
| 404 Not Found | Missing resource or existence concealed by policy |
| 405 Method Not Allowed | Method forbidden; preserve `Allow` |
| 409 Conflict | Conflict with current resource state |
| 415 Unsupported Media Type | Request `Content-Type` unsupported |
| 422 Unprocessable Content | Syntactically valid payload but semantically unprocessable per contract |
| 429 Too Many Requests | Rate limited, optionally add `Retry-After` |
| 500 Internal Server Error | Unexpected error, omit technical details |
| 503 Service Unavailable | System temporarily unavailable |

Problem Details JSON responses typically use `Content-Type: application/problem+json`. However, the actual output still depends on `Accept`, converters/writers, error handlers, and proxies. A browser requesting `text/html` may receive an HTML error page if the request goes through another handling path.

**Do not attach `Content-Type: application/problem+json` to every exception if the actual body is HTML or empty.** Also never set HTTP 200 for an error just because a method returned a Java object.

If the same URL can return HTML or JSON depending on `Accept`, check caching policies and `Vary` properly, especially when error data involves authenticated users.

## 26. Security and Exception-Handling Boundaries

`@RestControllerAdvice` sits inside the annotated controller pipeline. Some errors originate in other layers:

- Servlet Filters (before `DispatcherServlet`).
- Spring Security authentication/authorization.
- Reverse proxies, WAFs, gateways, or embedded HTTP parsers.
- WebFlux `WebFilter`, reactive server, and network connections.
- Background jobs or async tasks outside the HTTP request-response lifecycle.

Those errors are **not guaranteed** to pass through `@RestControllerAdvice`. Spring Security has `AuthenticationEntryPoint` and `AccessDeniedHandler` on Servlet; WebFlux has corresponding reactive security handlers. If your API requires Problem Details for 401/403, configure the **security layer** properly while preserving required headers.

For 500 errors, never expose `SQLException`, table names, file paths, internal hosts, stacktraces, tokens, unfiltered downstream messages, or raw request bodies in `detail`. Clients can receive a safe message such as `"An error occurred, please try again"`, while server logs retain the full exception with a correlation ID.

Be careful with `instance`: if it contains the full request URL including query strings, it can accidentally leak tokens or PII. A normalized request path or opaque error occurrence URI is safer for public responses.

`type` should be managed as part of the **public error contract**, not pointing to resources that disappear on each deployment.

## 27. Functional WebFlux: Exceptions Must Be Handled in the Right Flow

Functional endpoints are not annotated `@RestController`s. A handler returns `Mono<ServerResponse>`:

```java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route(
        RequestPredicates.GET("/api/check"),
        request -> Mono.error(
            new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid request")));
```

This is an illustrative **fragment** requiring imports for `RouterFunction`, `ServerResponse`, `RouterFunctions`, `RequestPredicates`, `Mono`, `ResponseStatusException`, and `HttpStatus`, registered as a bean in a WebFlux project. The exception goes through reactive error handling; there is no guarantee an `@ExceptionHandler` inside controller advice catches every case.

To actively build RFC 9457 responses from functional routes, map exceptions with `onErrorResume` and create `ServerResponse.status(...).contentType(MediaType.valueOf("application/problem+json")).bodyValue(problemDetail)`. Verify handling order, error status, body writer, and cancellation behavior.

For unhandled errors in the reactive chain, Boot uses `ErrorWebExceptionHandler`. Customizing at that layer is a broad architectural decision and should not be done just to change a single domain exception message.

## 28. Testing a Realistic Error Matrix

Do not test only one 404 response. Your matrix should cover:

| Scenario | What to Verify |
|---|---|
| Resource exists | HTTP 200, normal JSON body |
| Resource does not exist | HTTP 404, accurate `type`/extension `code` |
| Request JSON missing required field | HTTP 400 and `application/problem+json` when configured |
| Unparseable JSON | HTTP 400, no parser details or stacktrace leaked |
| Missing route URL | Check 404 mechanism and presence/absence of Problem Details in real runtime |
| Wrong HTTP method | HTTP 405, `Allow` preserved |
| Client sends incompatible Content-Type | HTTP 415 |
| Client requests unsupported media type | Check 406 and content negotiation contract |
| Resource conflict | HTTP 409, stable error code |
| Unexpected backend failure | HTTP 500, safe detail, trace in logs |
| Missing authentication | HTTP 401 from Security layer, accurate headers |
| Insufficient permissions | HTTP 403 or 404 per policy, no data leaks |
| Browser Accept text/html | Verify HTML/error page or problem JSON per chosen contract |
| WebFlux functional route | Verify not missed by annotated-controller-only advice |
| Locale switch | `title/detail` translated if i18n enabled, `code/type` unchanged |

Use `MockMvc` for MVC controller-level tests, `WebTestClient` for reactive controllers, and integration tests for proxies, security filters, unmatched 404s, and unexpected errors. If tests mock the framework directly, do not treat them as proof that embedded server errors share the exact same body.

## 29. Common Issues and Fixes

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Enabled `spring.webflux.problemdetails.enabled` but MVC unchanged | App actually runs SERVLET/MVC | Use `spring.mvc.problemdetails.enabled` |
| All errors still return old format | Property inactive, another advice catches exception, or routed via `/error` | Check profiles, condition report, and exception handler order |
| Problem JSON has `status=404` but HTTP 200 | Code used `ResponseEntity.ok(problem)` | Align actual HTTP status with body |
| Using `@RestControllerAdvice` yet 401/403 unchanged | Error comes from Spring Security filter chain | Configure security-specific handlers |
| Functional WebFlux errors miss advice | Advice binds to annotated controller infrastructure | Handle in functional route or reactive error handler |
| Extension `code` missing | ObjectMapper lacks Spring's MixIn or different serialization | Check Jackson setup and `setProperty` |
| Every exception becomes 500 | Catch-all advice overrides built-in handling | Catch only domain exceptions, preserve status/headers |
| `detail` leaks SQL/stacktrace | Using `ex.getMessage()` from internal errors | Return safe messages, log details on server |
| 404 lacks `application/problem+json` | Error originates from `/error` or outside controllers | Test at the proper layer; configure corresponding error handler |
| Unexpected XML/HTML appears | `Accept`/content negotiation or template/error renderer | Check active media types and converters |
| `title/detail` changes by language | `MessageSource`/i18n | Use `type`/`code` for client branching |
| Missing `instance` | Version/framework path or handler didn't populate it | Set a safe `instance` explicitly if required by contract |

## 30. Implementation Checklist

1. Determine whether the application runs **Spring MVC** or **Spring WebFlux**; do not guess from a `WebClient` dependency alone.
2. Enable the right property: `spring.mvc.problemdetails.enabled` or `spring.webflux.problemdetails.enabled`.
3. Use `ProblemDetail` for the RFC 9457 body and understand `ErrorResponse` as the status+headers+body contract.
4. Use `ErrorResponseException`/`ResponseStatusException` when throwing exceptions with explicit statuses.
5. For domain errors, return `ProblemDetail` from advice with specific exception mappings and proper ordering.
6. Preserve HTTP statuses, media types, and important response headers.
7. Establish stable `type` URIs and `code` values documented in your API contract.
8. Use i18n for `title/detail`, never message text for client branching.
9. Never leak SQL, stacktraces, secrets, tokens, or sensitive rejected values in error bodies.
10. Distinguish annotated controller errors from `/error`, Servlet Filters, WebFilters, Security, and proxy errors.
11. Test on the right stack: MVC `MockMvc`, reactive `WebTestClient`, integration tests for network/security.
12. Verify 400/401/403/404/405/409/415/429/500, `application/problem+json`, `Allow`, correlation IDs, and cache behavior.
13. When upgrading Spring Boot major versions, re-check default properties, Javadoc, and how `instance` is set.

## 31. Summary

**`ProblemDetail` describes the error**, **`ErrorResponse` defines how an error carries status/headers**, and **Spring Boot Problem Details auto-configuration** converts many built-in web exceptions into RFC 9457 responses.

In Spring Boot 3.5, MVC uses `spring.mvc.problemdetails.enabled=true`; WebFlux uses `spring.webflux.problemdetails.enabled=true`. Create focused advice for **business errors**, preserve built-in framework handling, check `@ControllerAdvice` ordering, and never assume a single annotation catches every HTTP error across all layers.

A strong error contract is more than pretty JSON: it aligns **actual HTTP status, content type, error codes, type URI docs, security, localization, and testability**.

## 32. References

- Spring Boot 3.5 — Servlet Error Handling & Problem Details: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Reactive Error Handling & Problem Details: https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Framework 6.2 — Spring MVC Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — Spring WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2 — ProblemDetail Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/http/ProblemDetail.html
- Spring Framework 6.2 — ErrorResponse Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/ErrorResponse.html
- Spring Framework 6.2 — ErrorResponseException Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/ErrorResponseException.html
- Spring Framework 6.2 — ResponseEntityExceptionHandler (MVC): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.2 — ResponseEntityExceptionHandler (WebFlux): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110