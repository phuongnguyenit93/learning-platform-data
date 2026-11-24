# @ExceptionHandler in Controllers and Handler Selection Rules in Spring MVC

> **Scope:** Spring Web MVC on the Servlet stack, using Java 17+ and Spring Boot 3.x / Spring Framework 6.2.x examples. This lesson focuses on `@ExceptionHandler` **placed in a controller** and the rules Spring uses to select a handler by **local/global scope, exception type, root/cause, advice order, and media type**. Parts related to `@ControllerAdvice` are explained to understand selection order, without replacing the focus on local `@ExceptionHandler`.

## 1. The Problem: An Exception Needs to Become a Meaningful HTTP Response

Suppose a book lookup API:

```http
GET /api/books/13
Accept: application/json
```

If the book does not exist, the service might throw:

```java
throw new BookNotFoundException(13);
```

If left unhandled, the result depends on the default `HandlerExceptionResolver`s, Spring Boot configuration, and exception type; for an unrecognized runtime exception, it usually results in a 500 error. However, "book does not exist" is a business scenario: the API should return **404 Not Found** with a safe explanatory body.

`@ExceptionHandler` allows a controller to declare a method dedicated to handling exceptions:

```java
@RestController
class BookController {

    @GetMapping("/api/books/{id}")
    public BookDto find(@PathVariable long id) {
        throw new BookNotFoundException(id);
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<String> bookNotFound(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
```

This is an **illustrative snippet**; `BookDto` and `BookNotFoundException` must be defined to compile. Exceptions raised while Spring processes a handler belonging to `BookController` will be considered by this local exception handler before applicable global advices. The client receives status 404 and a body, instead of an unclear system error.

**Three key points:**
1. `@ExceptionHandler` is an annotation for an **exception-handling method**, not an annotation for throwing exceptions.
2. The method is selected by the **thrown exception and mapping configuration**, not by method name or declaration order in the Java file.
3. The handler method decides the response itself: typically using `ResponseEntity<?>`, `ProblemDetail`, `@ResponseStatus`, or a corresponding body/view.

## 2. How Spring MVC Invokes @ExceptionHandler

A simplified flow:

```text
HTTP request
    |
    v
DispatcherServlet selects @GetMapping/@PostMapping...
    |
    v
Invoke controller / resolve arguments / conversion / validation
    |
    +------ success -----------> return value -> HTTP response
    |
    +------ exception
               |
               v
       HandlerExceptionResolver chain
               |
               v
       ExceptionHandlerExceptionResolver
               |
               +-- look for matching local @ExceptionHandler in controller
               |
               +-- if unhandled: look for @ExceptionHandler in @ControllerAdvice
               |
               +-- apply exception type, cause, advice order, media type
               |
               v
          selected handler -> response
               |
       If still unhandled:
       other resolvers / servlet container
```

`ExceptionHandlerExceptionResolver` is one `HandlerExceptionResolver` provided by Spring MVC; there are also other mechanisms such as `ResponseStatusExceptionResolver` and `DefaultHandlerExceptionResolver`. An exception not claimed by any `@ExceptionHandler` method may still be handled by another resolver or propagate out to the servlet container.

The handling scope is the **MVC request lifecycle and the exceptions visible to the resolvers**. `@ExceptionHandler` inside a controller does not automatically catch every error occurring outside `DispatcherServlet`, such as errors blocked entirely in a servlet filter before entering MVC. Spring Security has `AuthenticationEntryPoint` and `AccessDeniedHandler` inside its filter chain; do not assume 401/403 errors always reach controller advice.

## 3. Writing a Local @ExceptionHandler in the Same Controller

### 3.1. Specifying the Exception in the Annotation

```java
@ExceptionHandler(IllegalArgumentException.class)
public ResponseEntity<String> badArgument(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("Bad input");
}
```

`@ExceptionHandler(IllegalArgumentException.class)` registers the method to handle `IllegalArgumentException` and matching subtypes; the `ex` parameter lets you inspect the matched exception. If the controller has `@RestController`, the response body is written as a REST body; `ResponseEntity` also allows setting status/headers/body directly.

### 3.2. Inferring the Exception Type from the Parameter

```java
@ExceptionHandler
public ResponseEntity<String> badArgument(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("Bad input");
}
```

When the annotation does not specify the type, Spring can infer the exception type from the method parameter. This is concise when the handler targets **a single clear exception type**. Avoid writing handlers without an inferable exception type or with an overly broad parameter that causes unexpected mappings.

### 3.3. One Handler for Multiple Exception Types

```java
@ExceptionHandler({
        IllegalArgumentException.class,
        IllegalStateException.class
})
public ResponseEntity<String> invalidState(RuntimeException ex) {
    return ResponseEntity.badRequest().body("Invalid request");
}
```

This is an **illustrative method**, grouping two cases when they genuinely share the same HTTP semantics. The parameter type `RuntimeException` is their common superclass; do not declare an `IllegalArgumentException` parameter when the annotation also registers `IllegalStateException` and expect Spring to pass a different exception type into that parameter.

Keeping handlers narrow by business case is usually better:

```java
@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<ApiError> missing(BookNotFoundException ex) { /* ... */ }
```

The `/* ... */` markers indicate unimplemented parts in a **design snippet**, not a standalone runnable program. Avoid catching `Exception.class` in a controller and turning every programming bug into HTTP 400 or 404.

## 4. Rule 1: Local Handlers Are Considered Before Global Advice

- **Local:** an `@ExceptionHandler` method declared in the `@Controller`/`@RestController` itself or in a superclass hierarchy applying to that controller.
- **Global:** an `@ExceptionHandler` method declared in a `@ControllerAdvice` or `@RestControllerAdvice` bean, applicable across multiple controllers via selectors.
- Once a controller has been selected to handle a request, Spring MVC **considers local exception handlers before** applicable global handlers. A local match can be selected even when an advice declares a handler for the same exception.

Example with both places handling `BookNotFoundException`:

```java
@RestController
class BookController {
    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<String> local(BookNotFoundException ex) {
        return ResponseEntity.status(404).body("LOCAL");
    }
}

@RestControllerAdvice
class GlobalErrors {
    @ExceptionHandler(BookNotFoundException.class)
    ResponseEntity<String> global(BookNotFoundException ex) {
        return ResponseEntity.status(404).body("GLOBAL");
    }
}
```

These are **two illustrative classes**, omitting the routes that throw the error. When `BookNotFoundException` arises from a handler inside `BookController`, the local method typically returns `LOCAL`; the same error thrown in another controller without a local match can be handled by the global method returning `GLOBAL`.

Important point to understand: `@Order` on a global advice **does not promote the advice ahead of a matching local handler**. To change policy for a specific controller, modify the local handler or the advice scope; do not use `@Order` to compete with a local match.

### 4.1. How Do @ControllerAdvice and @RestControllerAdvice Differ?

```java
@ControllerAdvice
class ErrorViews {
    @ExceptionHandler(BookNotFoundException.class)
    String page(BookNotFoundException ex) {
        return "book-not-found";
    }
}
```

With `@ControllerAdvice`, a returned string can be a **view name** (requiring a view resolver/template). By contrast, `@RestControllerAdvice` combines `@ControllerAdvice` with `@ResponseBody`: method return values are normally written to the **HTTP response body** except for return types with dedicated handling. Both participate in the exception handler lookup process. Do not use `@ControllerAdvice` and assume `return "error"` always sends the plain text body `error`.

### 4.2. Narrowing Advice Scope

```java
@RestControllerAdvice(basePackages = "com.example.api")
class ApiErrorAdvice {
    // @ExceptionHandler methods for controllers in the target package.
}
```

You can use `basePackageClasses`, `annotations`, or `assignableTypes` to restrict the set of controllers an advice applies to. If multiple selectors are specified simultaneously, they are combined with **OR**: matching at least one selector is enough, rather than requiring all of them to match. By default an advice applies broadly; only add selectors when there is a clear architectural reason.

## 5. Rule 2: More Specific Exception Types Take Precedence Within the Same Handler Set

Suppose a controller has:

```java
@ExceptionHandler(RuntimeException.class)
ResponseEntity<String> general(RuntimeException ex) {
    return ResponseEntity.internalServerError().body("GENERAL");
}

@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> invalid(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("SPECIFIC");
}
```

When `IllegalArgumentException` is thrown directly, both mappings match by inheritance, but `IllegalArgumentException` is **more specific**, so Spring selects the handler returning `SPECIFIC`. There is no rule that "the method declared first runs first". Spring uses `ExceptionDepthComparator` to compare closeness to the exception.

Hierarchy example:

```text
Throwable
  └── Exception
      └── RuntimeException
          └── IllegalArgumentException
```

If there are two separate handlers for `RuntimeException` and `Exception`, an `IllegalArgumentException` also typically selects `RuntimeException` because it is a closer subtype. If there is an exact handler for `IllegalArgumentException`, that handler wins within the same set of valid candidates.

**However:** do not define two handlers duplicating **the exact same exception mapping and same media type** within a single controller/advice. For example:

```java
@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> first(IllegalArgumentException ex) { /* ... */ }

@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> second(IllegalArgumentException ex) { /* ... */ }
```

This is an **intentionally invalid** snippet; Spring may report an **ambiguous `@ExceptionHandler` method mapping** when initializing the resolver/controller advice. Java allowing different method names does not resolve duplicate mappings. Distinguish this case from two handlers with exception types at **different inheritance depths** as in the valid example above.

## 6. Rule 3: Root Exception and Cause Exception

An exception can wrap another exception:

```java
throw new IllegalStateException(
        "Load failed",
        new BookNotFoundException(13));
```

Here:
- The **root/top-level exception** thrown to MVC is `IllegalStateException`.
- The **cause** inside `getCause()` is `BookNotFoundException`.
- Since Spring Framework 5.3, `@ExceptionHandler` can match at nested cause levels, not only the immediate exception.

Suppose the controller has two methods:

```java
@ExceptionHandler(IllegalStateException.class)
ResponseEntity<String> top(IllegalStateException ex) {
    return ResponseEntity.status(409).body("ROOT");
}

@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<String> nested(BookNotFoundException ex) {
    return ResponseEntity.status(404).body("CAUSE");
}
```

With the `IllegalStateException` wrapper example above, the handler for the **root** takes precedence within the same controller/advice: returning `ROOT`. Conversely, if there is no local handler matching the root, the handler for the cause `BookNotFoundException` can be selected and return `CAUSE`.

An important edge case: a very broad handler such as `@ExceptionHandler(Exception.class)` is still a **root match** for `IllegalStateException`, so within the same advice it can take precedence over a handler matching a deep cause even though the latter is a more specific exception type. Do not design around the assumption that "the most specific type anywhere in the cause chain always wins". Spring evaluates root and cause according to its actual selection rules.

### 6.1. Which Object Does the Exception Method Receive?

If an `@ExceptionHandler(BookNotFoundException.class)` method is selected via a cause, the `BookNotFoundException ex` parameter normally receives the corresponding exception from the cause chain. When using a multi-type mapping or a very broad superclass parameter, the passed object may be the root/wrapper in valid cases. It is best to give handlers **dedicated, specific** signatures to reduce ambiguity.

Do not base business decisions solely on `exception.getMessage()` strings; define specific exception types/domain codes and structured properties such as the missing ID.

## 7. Rule 4: Ordering Across Multiple @ControllerAdvice Beans

When multiple controller advices apply to a request, Spring processes them in advice bean priority order:

```java
@RestControllerAdvice
@Order(10)
class HighPriorityAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> handle(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("HIGH");
    }
}

@RestControllerAdvice
@Order(100)
class LowPriorityAdvice {
    @ExceptionHandler(Exception.class)
    ResponseEntity<String> handle(Exception ex) {
        return ResponseEntity.internalServerError().body("LOW");
    }
}
```

These are **two independent illustrative advices**; when `IllegalArgumentException` arrives and the controller has no local match, the advice with `@Order(10)` is consulted before `@Order(100)`. **Lower order values have higher precedence.**

Subtle root/cause rule:

- **Within one controller/advice**: a root exception match takes precedence over a cause match, alongside type specificity.
- **Between two advices with different priorities**: a **cause match in a higher-priority advice** can be selected before a **root match in a lower-priority advice**.
- Therefore, place handlers for root business exceptions primarily in appropriately ordered advices and design advice scopes to avoid conflicts.

Selection summary table, assuming the controller has no local handler:

| Scenario | Typically selected handler |
| --- | --- |
| Advice A `@Order(1)` matches `IllegalArgumentException` directly, Advice B `@Order(10)` matches `Exception` | Advice A |
| Advice A `@Order(1)` matches **cause** `BookNotFoundException`, Advice B `@Order(10)` matches **root** `IllegalStateException` | Advice A can win due to bean ordering |
| Within the **same** advice with handlers for `Exception` and `BookNotFoundException`, root is `IllegalStateException` wrapping cause `BookNotFoundException` | Root-match `Exception` usually wins |
| Controller has a matching local handler, while advices also match | Local controller handler is considered first |

Be aware of special cases such as scoped advice beans that can affect how Spring applies the `Ordered` interface; do not rely on class scanning order by chance. Set explicit `@Order` when multiple advices could handle overlapping exceptions and verify with integration tests.

## 8. Rule 5: Media Type of an Exception Handler (Spring Framework 6.2+)

Since **Spring Framework 6.2**, the `@ExceptionHandler` annotation has a `produces` attribute. This allows registering **two handlers for the same exception type** when rendering different representations:

```java
// Standalone snippet illustrating Spring Framework 6.2+ API.
@ExceptionHandler(
        value = BookNotFoundException.class,
        produces = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<ErrorDto> json(BookNotFoundException ex) {
    return ResponseEntity.status(404)
            .body(new ErrorDto("NOT_FOUND", "Book not found"));
}

@ExceptionHandler(
        value = BookNotFoundException.class,
        produces = MediaType.TEXT_PLAIN_VALUE)
public ResponseEntity<String> text(BookNotFoundException ex) {
    return ResponseEntity.status(404)
            .body("Book not found");
}
```

The two methods above are **not considered exact duplicates** because each declares a distinct media type. An `Accept: application/json` header routes to the JSON handler; `Accept: text/plain` routes to the text handler if content negotiation is satisfied. With `Accept: */*` or complex media type lists, test the concrete outcome under current ordering and negotiation rules rather than assuming one handler arbitrarily.

`@ExceptionHandler(produces=...)` **does not exist** in Spring Framework versions older than 6.2. If you use Boot 3.x but actually depend on Spring Framework 6.0/6.1, the code above **will not compile**. Check the actual dependency/version; if you cannot upgrade yet, use a single handler that decides a valid response using available APIs instead of copying the new annotation attribute.

Distinction:

- `@GetMapping(produces=...)`: selects the **controller endpoint** before execution.
- `@ExceptionHandler(produces=...)`: selects the **error representation handler** during exception handling (Spring 6.2+).
- `ResponseEntity.contentType(...)`: sets the **response header**; it does not register a new exception mapping.
- `@RestControllerAdvice`: affects scope/global body semantics, not media type selection.

If the request `Accept` header is incompatible with any error representation, Spring may need another fallback mechanism; do not assume exceptions are always returned as a specific JSON regardless of `Accept`.

## 9. Rule 6: Rethrowing to Decline Handling the Current Case

A handler can accept a broad exception type and discover the current instance falls outside its intended scope:

```java
@ExceptionHandler(IllegalStateException.class)
public ResponseEntity<String> selective(IllegalStateException ex) {
    if (!"known-state".equals(ex.getMessage())) {
        throw ex; // Rethrow the exact original object.
    }
    return ResponseEntity.status(409).body("Known conflict");
}
```

This is an **illustrative snippet**. Rethrowing **the same exception instance** lets Spring treat it as if the handler declined the match, allowing the rest of the exception resolution mechanism to continue. Do not construct a new exception just to forward it and assume all stack trace/cause metadata remain intact.

However, rethrowing based on message text is fragile; production code should use exception subtypes or structured error codes:

```java
class InventoryConflictException extends RuntimeException {
    InventoryConflictException(String message) {
        super(message);
    }
}
```

Creating clear semantic exception types and writing `@ExceptionHandler(InventoryConflictException.class)` is more predictable. Do not use rethrowing as a loop to probe handlers one by one; know clearly which resolver is responsible.

## 10. What Parameters Can @ExceptionHandler Accept and What Can It Return?

These methods resolve arguments and return values similarly to MVC handlers, though not every normal handler input can be retrieved again. The request body may already have been read before the error occurred.

Useful parameters:

| Parameter | Purpose |
| --- | --- |
| `BookNotFoundException ex` / `Exception ex` | Read the matched exception object |
| `HttpServletRequest request` | Inspect URI, method, request headers; note the `jakarta.servlet.http.*` namespace in Boot 3 |
| `WebRequest` / `NativeWebRequest` | Request context without depending on the Servlet API for every operation |
| `Locale locale` | Obtain locale from resolver to internationalize error messages |
| `Principal principal` | Inspect identity if present; does not guarantee authorization by itself |
| `HandlerMethod handlerMethod` | Information about the failing controller handler when available |
| `Model model` | Attach data for an error view (view-style methods) |

Common return values:

```java
@ExceptionHandler(BookNotFoundException.class)
ResponseEntity<ApiError> error(BookNotFoundException ex) {
    return ResponseEntity.status(404)
            .body(new ApiError("NOT_FOUND", "Book not found"));
}
```

Or `ProblemDetail`:

```java
@ExceptionHandler(BookNotFoundException.class)
ProblemDetail problem(BookNotFoundException ex) {
    ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Book not found");
    body.setTitle("Requested book not found");
    return body;
}
```

In Spring Framework 6+, `ProblemDetail` is supported to render errors per **RFC 9457**; the status inside `ProblemDetail` determines the HTTP status when returned via Spring's standard path. You can choose `ResponseEntity<ProblemDetail>` if you need to set headers or status explicitly. With `@ResponseStatus(HttpStatus.NOT_FOUND)` and a DTO body, the annotation sets a fixed status. If a method returns `String` in a regular `@Controller` without `@ResponseBody`, the string is normally a view name; in `@RestControllerAdvice` or a method with `@ResponseBody`, it represents body text.

Do not try to add `@RequestBody` to an exception handler to re-read the entire request: the stream may already be consumed, or parsing the body itself may be the cause of the exception.

## 11. Runnable Spring Boot 3.x Example: Local, Global, Generic, and Cause

Runnable example with **Java 17+**, **Spring Boot 3.x + Spring Web**, using Spring Framework 6.x. It does not depend on a database, Security, or validation starter; all error responses are returned explicitly by our code. The goal is to verify **which method Spring selects**, shown clearly via the `X-Error-Source` header and JSON body.

Create a project on [Spring Initializr](https://start.spring.io/), choose Java 17+ and the **Spring Web** dependency. Replace the entire content of `src/main/java/com/example/demo/DemoApplication.java` with the following code:

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

record ItemDto(long id, String name) {
}

record ApiError(String code, String message, String path) {
}

class ItemNotFoundException extends RuntimeException {
    private final long id;

    ItemNotFoundException(long id) {
        super("Item " + id + " not found");
        this.id = id;
    }

    long getId() {
        return id;
    }
}

@RestController
@RequestMapping("/api/items")
class ItemController {

    @GetMapping("/{id}")
    public ItemDto find(@PathVariable("id") long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        if (id == 13) {
            throw new ItemNotFoundException(id);
        }
        if (id == 99) {
            throw new IllegalStateException(
                    "wrapped lookup failure",
                    new ItemNotFoundException(id));
        }
        return new ItemDto(id, "item-" + id);
    }

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ApiError> localNotFound(
            ItemNotFoundException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "ITEM_NOT_FOUND",
                "Item " + ex.getId() + " does not exist",
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .header("X-Error-Source", "controller")
                .body(body);
    }
}

@RestController
@RequestMapping("/api/other")
class OtherController {

    @GetMapping("/items/{id}")
    public ItemDto find(@PathVariable("id") long id) {
        if (id == 13) {
            throw new ItemNotFoundException(id);
        }
        if (id == 99) {
            throw new IllegalStateException("internal simulated failure");
        }
        return new ItemDto(id, "other-" + id);
    }
}

@RestControllerAdvice
class GlobalErrorAdvice {

    @ExceptionHandler(ItemNotFoundException.class)
    public ResponseEntity<ApiError> missing(
            ItemNotFoundException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "ITEM_NOT_FOUND",
                "Item " + ex.getId() + " does not exist",
                request.getRequestURI());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .header("X-Error-Source", "advice")
                .body(body);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> badArgument(
            IllegalArgumentException ex,
            HttpServletRequest request) {

        ApiError body = new ApiError(
                "BAD_ARGUMENT",
                "id must be positive",
                request.getRequestURI());

        return ResponseEntity.badRequest()
                .header("X-Error-Source", "advice")
                .body(body);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> internal(
            Exception ex,
            HttpServletRequest request) {

        // Do not send ex.getMessage() for system errors.
        ApiError body = new ApiError(
                "INTERNAL_ERROR",
                "Unexpected server error",
                request.getRequestURI());

        return ResponseEntity.status(
                        HttpStatus.INTERNAL_SERVER_ERROR)
                .header("X-Error-Source", "advice")
                .body(body);
    }
}
```

**Key points in the code:**
- `ItemController` has **one local** `@ExceptionHandler(ItemNotFoundException.class)`.
- `GlobalErrorAdvice` has three handlers: `ItemNotFoundException`, `IllegalArgumentException`, and `Exception`. These mappings are **unambiguous** because they have distinct types with specificity relationships, so Spring selects the appropriate method.
- `OtherController` has no local exception handler, so when it throws `ItemNotFoundException`, the global handler claims it.
- `find(99)` in `ItemController` intentionally throws a wrapper `IllegalStateException` containing the cause `ItemNotFoundException`: the local cause match is evaluated before the broad global handler, so the error is still returned from the controller.
- The generic `Exception.class` handler returns 500 with a controlled message; this is an intentional example to distinguish unknown failures. In a real application, log the exception with a correlation ID and follow security policies; never return stack traces or internal messages.
- There is no Security or data store; business/persistence correctness and authorization are outside the scope of this demo.

### 11.1. Running the Application

In the Spring Initializr project root directory:

```bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell or Command Prompt
mvnw.cmd spring-boot:run
```

Once the server starts on default port 8080, try each request. Use `curl -i` to inspect the status and custom header; in PowerShell, use `curl.exe`.

### 11.2. Result 1: Normal Request

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/7
```

HTTP status **200 OK**, expected JSON body:

```json
{"id":7,"name":"item-7"}
```

There is no `X-Error-Source` header because no exception occurred and no exception handler ran.

### 11.3. Result 2: Controller Has a Local Handler

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/13
```

Status **404 Not Found**, header:

```http
X-Error-Source: controller
```

Body:

```json
{"code":"ITEM_NOT_FOUND","message":"Item 13 does not exist","path":"/api/items/13"}
```

Even though the global advice also has a handler for `ItemNotFoundException`, the local handler wins. This is not because it appears higher up in the Java source code.

### 11.4. Result 3: Same Exception Type in Another Controller

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/other/items/13
```

Status **404**, `X-Error-Source: advice`; body:

```json
{"code":"ITEM_NOT_FOUND","message":"Item 13 does not exist","path":"/api/other/items/13"}
```

`OtherController` has no matching local handler, so the advice handles it.

### 11.5. Result 4: Specific Exception Beats Generic

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/0
```

Status **400 Bad Request**, `X-Error-Source: advice`, body:

```json
{"code":"BAD_ARGUMENT","message":"id must be positive","path":"/api/items/0"}
```

The advice has both `@ExceptionHandler(IllegalArgumentException.class)` and `@ExceptionHandler(Exception.class)`. The more specific handler is selected for the top-level `IllegalArgumentException`.

### 11.6. Result 5: Local Match on Nested Cause

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/items/99
```

Status **404**, `X-Error-Source: controller`, and body:

```json
{"code":"ITEM_NOT_FOUND","message":"Item 99 does not exist","path":"/api/items/99"}
```

The top-level exception is `IllegalStateException`, and the cause is `ItemNotFoundException`. The controller only has a local mapping for the cause, so the local handler matches. If a local handler for the top-level `IllegalStateException` were added to the same controller, the result would change according to the rule that a root match takes precedence over a cause match.

### 11.7. Result 6: Generic Fallback for Unknown Errors

```bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/api/other/items/99
```

Status **500 Internal Server Error**, `X-Error-Source: advice`, body:

```json
{"code":"INTERNAL_ERROR","message":"Unexpected server error","path":"/api/other/items/99"}
```

There is no local handler in `OtherController` and no specific global handler for `IllegalStateException`, so `@ExceptionHandler(Exception.class)` matches the root exception. The actual exception message `"internal simulated failure"` is not sent to the client.

Other headers such as `Date`, `Connection`, `Content-Type`, and the order of fields/headers depend on the servlet container, message converter, and version. The JSON above shows the **expected payload values**, without requiring byte-for-byte header order matching.

## 12. Testing Selection Rules with MockMvc

To avoid "adding a new handler and accidentally changing which method gets selected", tests should verify **status + source-identifying header + body**. Add the `spring-boot-starter-test` dependency via Spring Initializr or `pom.xml`, then create `src/test/java/com/example/demo/ExceptionSelectionTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExceptionSelectionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void localHandlerWins() throws Exception {
        mvc.perform(get("/api/items/13"))
                .andExpect(status().isNotFound())
                .andExpect(header().string(
                        "X-Error-Source", "controller"))
                .andExpect(jsonPath("$.code")
                        .value("ITEM_NOT_FOUND"));
    }

    @Test
    void globalHandlerHandlesOtherController() throws Exception {
        mvc.perform(get("/api/other/items/13"))
                .andExpect(status().isNotFound())
                .andExpect(header().string(
                        "X-Error-Source", "advice"))
                .andExpect(jsonPath("$.path")
                        .value("/api/other/items/13"));
    }

    @Test
    void specificExceptionBeatsGenericInAdvice() throws Exception {
        mvc.perform(get("/api/items/0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BAD_ARGUMENT"));
    }

    @Test
    void localHandlerMatchesNestedCause() throws Exception {
        mvc.perform(get("/api/items/99"))
                .andExpect(status().isNotFound())
                .andExpect(header().string(
                        "X-Error-Source", "controller"));
    }

    @Test
    void genericAdviceHandlesUnknownFailure() throws Exception {
        mvc.perform(get("/api/other/items/99"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("INTERNAL_ERROR"));
    }
}
```

Run with:

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

The tests assume Spring Boot 3.x without adding a Spring Security filter requiring login. This tests the **method selection rules**, and does not verify all security scenarios or every framework error. When upgrading Spring versions or adding advices, add tests for any new overlapping cases.

## 13. Common Pitfall: Exceptions Raised Before the Controller Method Runs

Not every HTTP error is caused by code executing `throw` inside a method body. For example:

- `@RequestBody` failing to parse JSON can raise `HttpMessageNotReadableException` while reading the body.
- `@Valid` failing can raise `MethodArgumentNotValidException`.
- A missing required request parameter can raise `MissingServletRequestParameterException`.
- A `consumes`/`produces` mismatch or missing handler can raise errors across different mapping/dispatch phases.

An appropriate exception resolver **can** handle these errors, but a local `@ExceptionHandler` is not always applicable: when the framework has not resolved a controller method yet, there may be no specific handler from which to look up local mappings. Global advice or default resolvers are usually suited for general error policies.

When you want to customize **a specific group of framework errors**, use `@RestControllerAdvice` or extend `ResponseEntityExceptionHandler` at the API level. If extending `ResponseEntityExceptionHandler`, inspect the `protected` methods the framework provides to override; do not arbitrarily add an `@ExceptionHandler` duplicating a broad mapping already declared in the superclass, as it can cause ambiguity.

With `ResponseStatusException` or exception types annotated with `@ResponseStatus`, Spring has a dedicated resolver; a matching `@ExceptionHandler` can intercept earlier in the default resolver chain. Do not treat `@ResponseStatus` on an exception as taking absolute priority when custom/global exception handlers are present.

## 14. Choosing Safe HTTP Error Responses

| Scenario | Common appropriate status | Suggestion |
| --- | --- | --- |
| Resource does not exist | 404 | `ItemNotFoundException` → 404 |
| Invalid business parameter | 400 or 422 per contract | Return safe error code and field context |
| Resource state conflict | 409 | `ConflictException` → 409 |
| Client lacks authentication | 401 | Usually handled via Spring Security entry point if present |
| Client is not authorized | 403 | Authorization handler; avoid leaking resource info |
| JSON parsing / request body error | 400 | Dedicated error advice for parsing/validation |
| Unknown server error | 500 | Generic message, internal log with correlation ID |

Do not return `ex.getMessage()` from `SQLException`, `NullPointerException`, or stack traces directly to clients. For expected exceptions with safe messages, you can extract filtered error codes/context; for system errors, use a generic message. Never catch every `Exception` and return 200 or 400 because doing so hides bugs and breaks HTTP semantics.

Create a consistent error response, for example:

```json
{
  "code": "ITEM_NOT_FOUND",
  "message": "Item 13 does not exist",
  "path": "/api/items/13"
}
```

Or following Problem Details:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Item 13 does not exist",
  "instance": "/api/items/13"
}
```

These are **structural examples**, without guaranteeing every field appears by default if not populated. For multilingual applications, error messages can be resolved from `MessageSource` using `Locale`; the exception handler's role is to translate errors into HTTP responses, not contain all business logic.

## 15. Common Mistakes When Declaring @ExceptionHandler

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Local handler does not run in another controller | Local only applies to that controller/superclass | Use an advice if shared scope is needed |
| Global handler does not run despite matching type | A local handler handled it first | Check local mappings and inheritance |
| `Exception.class` handler intercepts cause errors unexpectedly | Generic root-match in the same advice outranks cause | Narrow the generic handler or design advice ordering |
| A high-priority advice handles a cause instead of another advice handling the root | `@Order` between advices has its own precedence | Design priority intentionally, add tests |
| Application reports ambiguous handler mapping | Two methods duplicate exception type and media type | Merge/change mapping; use `produces` (6.2+) for distinct representations |
| Copied `@ExceptionHandler(produces=...)` fails to compile | Spring Framework below 6.2 | Upgrade version or use supported APIs |
| `return "error"` triggers view lookup | `@ControllerAdvice` without `@ResponseBody` | `@RestControllerAdvice` or `ResponseEntity` |
| Exception handler returns status 200 with error body | Forgot to set status | Use `ResponseEntity.status(...)` / `ProblemDetail` |
| Handler tries to read `@RequestBody` again and fails | Body stream already consumed | Use exception, request metadata, and controlled captured input |
| Added Spring Security but handler does not catch 401/403 | Error handled in filter chain before MVC | Configure Security entry point/denied handler |
| Handler does not catch errors thrown by a filter | Error occurs outside DispatcherServlet scope | Handle in the filter or delegate via the right mechanism |
| Changed `@ExceptionHandler` but status is still unexpected | Another handler resolver or separate error config | Check resolver logs, run real HTTP tests |

### 15.1. Sequence for Debugging an Unselected Handler

1. Identify the **root exception type** thrown into MVC and the full `getCause()` chain (in server logs).
2. Determine whether a controller method was actually matched or the exception occurred before mapping.
3. List local `@ExceptionHandler` methods in the controller and its hierarchy, checking class assignability.
4. If there is no local match, list global advices **applicable to that controller**, including selectors.
5. Check `@Order` across advices; within each advice inspect root/cause/specificity.
6. Check `produces` (Framework 6.2+), request `Accept`, and response converters.
7. Check for duplicate exception mappings and verify method signatures have compatible exception parameters.
8. Write MockMvc tests pinning down status, error code, and custom headers to prevent regressions.

If a handler method **rethrows** the exception itself, keep checking downstream resolvers instead of seeing "handler selected" in the logs and assuming the error was handled.

## 16. Knowledge Check

**Question 1.** Both a controller and a `@RestControllerAdvice` have `@ExceptionHandler(IllegalArgumentException.class)`. The exception is thrown from that controller; which handler is tried first?

**Answer:** The **local** handler in the controller is considered first if it matches.

**Question 2.** The same controller has mappings for `RuntimeException` and `IllegalArgumentException`. The root exception is `IllegalArgumentException`. Which is chosen?

**Answer:** The `IllegalArgumentException` handler, because its mapping is more specific.

**Question 3.** Root `IllegalStateException` contains cause `ItemNotFoundException`; the same advice has mappings for `Exception` and `ItemNotFoundException`. What might be surprising?

**Answer:** `Exception` matches the **root**, whereas `ItemNotFoundException` matches the **cause**. A root match within an advice usually takes precedence, even though the cause type is more specific.

**Question 4.** Advice A `@Order(1)` handles the cause, Advice B `@Order(100)` handles the root. The controller has no local handler. Is B guaranteed to be chosen because of the root?

**Answer:** No. Higher-priority Advice A can handle the cause first, even though B has a root mapping.

**Question 5.** Are two methods in the same controller both declaring `@ExceptionHandler(IllegalArgumentException.class)` with the same media type valid?

**Answer:** No; their mappings are ambiguous. Starting from Framework 6.2, they can be separated using different `produces` values if the API truly needs multiple error representations.

**Question 6.** Why is `@ExceptionHandler(Exception.class)` returning 400 for every exception dangerous?

**Answer:** It swallows server errors, misleads clients, and prevents monitoring from distinguishing bugs from invalid input.

**Question 7.** A Spring Security filter blocks a request before it reaches `DispatcherServlet`. Does a local handler automatically handle that 403?

**Answer:** Not by default. Security filters typically handle it via their own authentication/authorization mechanisms; `@ExceptionHandler` operates within Spring MVC exception handling.

## 17. Official References

- [Spring Framework 6.2 — Exceptions / @ExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): mapping types, root/cause, rethrow, `produces`, method arguments, and return values.
- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): local and global scope, `@RestControllerAdvice`, selectors.
- [Spring Framework 6.2 — DispatcherServlet Exception Resolvers](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html): `HandlerExceptionResolver` chain and MVC default resolvers.
- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, and `ResponseEntityExceptionHandler`.
- [Spring Framework 6.2 — `@ExceptionHandler` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/ExceptionHandler.html): annotation parameters `value`, `exception`, and `produces`.
- [Spring Framework — `@Order` and advice ordering](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html): precedence across advice beans.

**Key takeaway:** To predict which `@ExceptionHandler` method runs, evaluate in order: **handler inside the controller first → matching global advice by priority order → compare root/cause and exception specificity within each group → matching media type → method produces HTTP response**. Write semantically meaningful business exception types, avoid global catch-alls returning wrong statuses, and test duplicate mappings, nested causes, and advice overlap.
