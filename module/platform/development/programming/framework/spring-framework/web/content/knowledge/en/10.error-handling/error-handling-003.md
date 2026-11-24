# @ControllerAdvice, @RestControllerAdvice, and Scope in Spring MVC

## Lesson Objectives

A REST API with dozens of controllers typically needs a consistent way to return 400, 404, or 500 errors. If each controller writes its own `try/catch` or repeats `@ExceptionHandler`, error formatting easily becomes inconsistent. **`@ControllerAdvice`** and **`@RestControllerAdvice`** let you share MVC callbacks across multiple controllers while allowing you to **restrict the target scope** by package, annotation, or controller type.

After this lesson, you will be able to:

- Explain which callbacks `@ControllerAdvice` supports and what `@RestControllerAdvice` adds.
- Distinguish view rendering from HTTP response bodies when handling exceptions.
- Understand that advice applies **broadly by default**, and actively restrict scope with `basePackages`, `basePackageClasses`, `assignableTypes`, and `annotations`; understand that multiple selectors combine with **OR**.
- Understand precedence between local and global `@ExceptionHandler`, `@Order` across multiple advices, and root vs. cause exceptions.
- Build a Spring Boot 3 / Spring MVC REST API with two separately scoped advices and test it with MockMvc.
- Avoid handlers that swallow all `Exception`s, leak sensitive details, or assume advice handles every error at every layer.

**Technical scope:** Java 17+, Spring Framework 6.x / Spring Boot 3.x, MVC running on the **Servlet stack**. Spring WebFlux has similar annotations, but its reactive processing flow and exception infrastructure differ; the examples below target MVC.

## 1. Before Using Advice: Local Error Handling

Inside a single controller, Spring MVC allows declaring `@ExceptionHandler` to handle exceptions thrown by handlers of **that controller**:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{id}")
    public String find(@PathVariable long id) {
        if (id != 1L) {
            throw new BookNotFoundException("Book " + id + " not found");
        }
        return "Spring MVC";
    }

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<String> handleLocal(BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body("Book not found");
    }
}
~~~

This is an **illustrative snippet**; `BookNotFoundException` and the corresponding imports must be defined. It shows that a controller can manage errors within its own scope. However, if dozens of controllers handle not-found or validation errors the same way, duplicating handlers increases maintenance cost.

At the MVC level, exceptions pass through the `HandlerExceptionResolver` chain. `ExceptionHandlerExceptionResolver` looks for a matching `@ExceptionHandler`; Spring also has resolvers for standard error types, declared statuses, and further error-handling mechanisms. Therefore, not **every** error response necessarily originates from an advice.

## 2. What Is `@ControllerAdvice`?

`@ControllerAdvice` marks a Spring bean containing methods that apply to **multiple controllers**. There are three common callback groups:

| Callback in advice | Purpose |
| --- | --- |
| `@ExceptionHandler` | Convert exceptions into error status, body, headers, or view |
| `@InitBinder` | Customize `WebDataBinder`: conversion, editors, formatters, validators, and allowed fields |
| `@ModelAttribute` on a method | Add or initialize shared model attributes for matching MVC handlers |

Shared exception handling example:

~~~java
@ControllerAdvice
public class SharedErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    public ResponseEntity<Map<String, String>> handle(
            BookNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "BOOK_NOT_FOUND"));
    }
}
~~~

This is also an **illustrative snippet**, requiring imports and a `BookNotFoundException`. When a controller in the advice's scope throws the matching exception, Spring MVC can invoke `handle` and write a 404 response.

`@ControllerAdvice` is meta-annotated with `@Component`, so the class is usually discovered via **component scanning**; it can also be registered directly as a bean. If the advice lives outside the packages Spring scans, it will not take effect automatically just because you created the Java file.

**Default scope:** if no selectors are declared, the advice can apply to **all matching MVC controllers**, including both `@Controller` and `@RestController`. The annotation does not distinguish HTML from REST controllers by default.

## 3. How Is `@RestControllerAdvice` Different?

`@RestControllerAdvice` is a composed annotation semantically equivalent to:

~~~java
@ControllerAdvice
@ResponseBody
public class RestErrorAdvice {
    // @ExceptionHandler methods...
}
~~~

It inherits the functionality and selectors of `@ControllerAdvice`, while giving exception handler methods default **`@ResponseBody`** semantics: normal return values are converted into the HTTP response body using `HttpMessageConverter` (for example, Jackson writing JSON), instead of being interpreted as a view name.

Example:

~~~java
@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(BookNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public ErrorBody notFound(BookNotFoundException ex) {
        return new ErrorBody("BOOK_NOT_FOUND", "Book does not exist");
    }

    public record ErrorBody(String code, String message) {}
}
~~~

The snippet above is illustrative: `ErrorBody` becomes a JSON object with `code` and `message` properties when a JSON converter is present, with status 404 from `@ResponseStatus`.

With plain `@ControllerAdvice`:

~~~java
@ControllerAdvice
public class HtmlErrors {

    @ExceptionHandler(BookNotFoundException.class)
    public String notFound(Model model) {
        model.addAttribute("message", "Book does not exist");
        return "errors/not-found";
    }
}
~~~

This is an **illustration for an HTML application with a `ViewResolver` and an `errors/not-found` template**; it is not a standalone file. A plain `String` is interpreted as a **view name**. If you place logic like that inside `@RestControllerAdvice`, the `String` can be written **as the text response body** `errors/not-found` instead of selecting a template.

**A common misconception:** `@ControllerAdvice` **can still handle REST**. If a method is annotated with `@ResponseBody`, returns `ResponseEntity<SomeDto>`, or uses an appropriate body-oriented return type, it still sends JSON/body without changing the class annotation to `@RestControllerAdvice`. The difference is the **default return-value handling of the handlers**, not the REST/HTML controller scope to which the advice applies.

| Characteristic | `@ControllerAdvice` | `@RestControllerAdvice` |
| --- | --- | --- |
| Spring bean discovered by MVC | Yes | Yes |
| Shares `@ExceptionHandler`, `@InitBinder`, `@ModelAttribute` | Yes | Yes |
| Default scope without selectors | Matching controllers in general | Matching controllers in general |
| Default body serialization for `@ExceptionHandler` returning an object | No implicit class-level `@ResponseBody` | Implicit `@ResponseBody` |
| Returning `String` from an exception handler | Usually a view name unless `@ResponseBody` is present | Usually a response body |
| Returning `ResponseEntity<Dto>` | Supported | Supported |
| Best suited for | HTML MVC, or REST with explicit return types | REST JSON / problem details |

`@RestControllerAdvice` does **not** mean "apply only to `@RestController`". If you want REST-only targeting, you must use a selector, such as `@RestControllerAdvice(annotations = RestController.class)`.

## 4. Target Scope: 4 Selector Groups

Both `@ControllerAdvice` and `@RestControllerAdvice` support these key attributes:

### 4.1. `basePackages`

~~~java
@RestControllerAdvice(basePackages = "com.example.demo.api")
public class ApiErrorAdvice {
    // ...
}
~~~

Applies to controllers in package `com.example.demo.api` or its subpackages. In projects where packages are renamed/refactored, string literals can become stale without compiler warnings.

The `value` attribute is an alias for `basePackages`, e.g., `@ControllerAdvice("com.example.demo.api")`.

### 4.2. `basePackageClasses`

~~~java
@RestControllerAdvice(basePackageClasses = ApiPackageMarker.class)
public class ApiErrorAdvice {
    // ...
}
~~~

This is an **illustrative snippet**; you need an `ApiPackageMarker` class/interface inside the API package and the advice's handler methods. The selector targets the **package containing the specified class** (and subpackages), not just the marker class itself. This is refactor-friendly and compiler-checked compared to package name strings.

### 4.3. `assignableTypes`

~~~java
@RestControllerAdvice(assignableTypes = {
        CatalogController.class, BillingController.class
})
public class BusinessErrorAdvice {
    // ...
}
~~~

This example selects controllers whose types are **assignable** to one of the listed classes/interfaces (taking inheritance hierarchy into account). You can use specific controller classes or a common base controller/interface. This is not a filter by URL path or exception name.

### 4.4. `annotations`

~~~java
@RestControllerAdvice(annotations = RestController.class)
public class RestOnlyErrorAdvice {
    // ...
}
~~~

This selector matches controllers carrying the specified annotation (and Spring's composed/hierarchical annotation lookup). The example above is one way to target REST controllers, though keep in mind a controller can use `@Controller` with `@ResponseBody` on handlers to return API bodies **without** having `@RestController`; in that case this selector will not cover it.

### 4.5. The OR Rule: Two Selectors Are Not AND

~~~java
@RestControllerAdvice(
        basePackages = "com.example.demo.api",
        annotations = RestController.class
)
public class MixedScopeAdvice {
    // ...
}
~~~

When multiple selectors are declared together, Spring combines them with **OR**: matching **at least one** selector is sufficient.

Therefore, the example above can apply to:
- An HTML `@Controller` located in package `com.example.demo.api` even without `@RestController`.
- A `@RestController` in a completely different package.

If the goal is "only `@RestController` classes located **inside** the api package", you cannot assume two attributes on the same advice form an AND. Organize controllers with a dedicated marker annotation or type and use a selector that expresses it accurately; if needed, split into separate advice groups.

Selectors are evaluated at runtime. Using too many selectors or too many advices can make the system harder to reason about and affect handler selection overhead. In simple systems, scope cleanly by package or controller type; in systems with multiple API versions, proactively separate error handlers by API group.

## 5. Precedence and Callback Lifecycle

### 5.1. `@ExceptionHandler` in a Controller Is Considered Before Global Advice

If the same exception has both a local `@ExceptionHandler` in the controller and a global handler in an applicable advice, **the controller's local handler takes precedence**. This is useful when a single controller needs an exceptional response format.

~~~java
@RestController
class OneController {

    @GetMapping("/conflict")
    String action() {
        throw new ItemConflictException("Conflict");
    }

    @ExceptionHandler(ItemConflictException.class)
    ResponseEntity<String> localHandler(ItemConflictException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT).body("local");
    }
}
~~~

This is illustrative; `ItemConflictException` and imports must be declared. Even if a general `@RestControllerAdvice` handles the same exception, the matching local handler is typically selected first.

### 5.2. Multiple Advices: `@Order` and `Ordered`

~~~java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
class SpecificErrors {
    // ...
}

@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
class FallbackErrors {
    // ...
}
~~~

This snippet illustrates ordering (without handler methods yet). Spring evaluates advices in precedence order. `@Order` with a **smaller value has higher precedence**; `Ordered` is the corresponding interface mechanism. For a given exception, Spring can select the **highest-precedence advice with a matching handler**, without waiting for a lower-precedence advice even if the latter's handler looks more specific.

**Root exception vs. cause exception:** within **the same advice**, matching on the root exception usually takes precedence over matching on a cause. However, a **cause match in a higher-precedence advice** can still beat a **root match in a lower-precedence advice**. Place specific business exception mappings in explicitly ordered advices. Avoid scattering handlers for the same exception across multiple advices without controlling order.

A few Spring Framework 6.x details:
- An advice bean implementing `Ordered` takes precedence over `@Order`/`@Priority` metadata according to framework rules.
- `PriorityOrdered` on an advice does not automatically guarantee priority over every `Ordered` the way you might expect from other contexts.
- `Ordered` is **not honored** for scoped advice beans (such as request-scoped or session-scoped beans). Use standard singleton advices when stable precedence coordination is required.
- Do not guess ordering among multiple ambiguous handlers. If a configuration could lead to ambiguous mappings for the same exception and scope, separate exception types/scopes/priorities cleanly and write tests.

### 5.3. For `@ModelAttribute` and `@InitBinder`, the Order Differs

Unlike `@ExceptionHandler`: `@ModelAttribute` and `@InitBinder` from **global advice** are applied **before** the corresponding methods in the controller (within the same context). This is helpful when shared binder/model setup must run first and the controller refines it afterward.

For example, an `@InitBinder` in an advice might trim form inputs for a group of controllers, while a local binder sets `allowedFields` for a specific model. Do not expect `@InitBinder` to convert JSON `@RequestBody` payloads deserialized by Jackson. Advice scope does not change the distinction between **`WebDataBinder`** and **`HttpMessageConverter`**.

### 5.4. Exception Handlers Are Not a Blanket `try/catch` for the Whole Application

`@ControllerAdvice` operates inside the MVC processing flow. Exceptions in an authentication filter or proxy layer can be handled **before reaching `DispatcherServlet`** and are not caught by advice; with Spring Security, authentication/access exceptions in the filter chain have their own mechanisms. Asynchronous failures, exceptions from out-of-request background tasks, or already-committed responses also require separate handling.

Do not catch `Exception.class` globally and turn every error into 200 or 400. Doing so hides server bugs, impairs observability, and can break statuses that Spring MVC maps accurately for input errors.

## 6. Runnable Example: Two Controller Groups with Separate Advices

We will build two endpoint groups—**catalog** and **billing**—that both throw `RecordMissingException` yet return distinct error bodies. At the same time, catalog has a **local `@ExceptionHandler`** for a conflict error to demonstrate that local takes precedence over global.

The Maven project uses **Java 17+**, **Spring Boot 3.x**, the **Spring Web** dependency (`spring-boot-starter-web`), and **Spring Boot Starter Test** (`spring-boot-starter-test`). Create it via Spring Initializr with package `com.example.demo`.

Structure:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/RecordMissingException.java
src/main/java/com/example/demo/CatalogConflictException.java
src/main/java/com/example/demo/CatalogController.java
src/main/java/com/example/demo/BillingController.java
src/main/java/com/example/demo/CatalogErrorAdvice.java
src/main/java/com/example/demo/BillingErrorAdvice.java
src/test/java/com/example/demo/AdviceScopeTest.java
~~~

### 6.1. `DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 6.2. Two Business Exceptions

**`RecordMissingException.java`:**

~~~java
package com.example.demo;

public class RecordMissingException extends RuntimeException {
    public RecordMissingException(String message) {
        super(message);
    }
}
~~~

**`CatalogConflictException.java`:**

~~~java
package com.example.demo;

public class CatalogConflictException extends RuntimeException {
    public CatalogConflictException(String message) {
        super(message);
    }
}
~~~

Do not annotate these two exceptions with `@ResponseStatus`: the status is decided by the handler selected per scope, making the difference easy to observe.

### 6.3. `CatalogController.java` with a Local Handler

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @GetMapping("/{id}")
    public CatalogItem get(@PathVariable long id) {
        if (id != 1L) {
            throw new RecordMissingException("Catalog item not found");
        }
        return new CatalogItem(1L, "Spring MVC");
    }

    @GetMapping("/conflict")
    public String conflict() {
        throw new CatalogConflictException("Catalog state conflict");
    }

    @ExceptionHandler(CatalogConflictException.class)
    public ResponseEntity<Map<String, String>> localConflict(
            CatalogConflictException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "LOCAL_CATALOG_CONFLICT"));
    }

    public record CatalogItem(long id, String title) {
    }
}
~~~

When `/api/catalog/conflict` throws `CatalogConflictException`, the local handler inside this controller returns **409 Conflict**. We will also create a global handler for the same exception in `CatalogErrorAdvice`, and it **will not be selected** in this case.

### 6.4. `BillingController.java`

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/billing")
public class BillingController {

    @GetMapping("/{id}")
    public BillingRecord get(@PathVariable long id) {
        if (id != 1L) {
            throw new RecordMissingException("Billing record not found");
        }
        return new BillingRecord(1L, 750);
    }

    public record BillingRecord(long id, int amount) {
    }
}
~~~

Both controllers throw the same **exception class**. If global handlers are not scoped cleanly, it is easy to apply the wrong error format between catalog and billing.

### 6.5. `CatalogErrorAdvice.java`: REST Body and ProblemDetail

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice(assignableTypes = CatalogController.class)
public class CatalogErrorAdvice {

    @ExceptionHandler(RecordMissingException.class)
    public ResponseEntity<ProblemDetail> missing(
            RecordMissingException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "Catalog item not found");
        problem.setTitle("Catalog lookup failed");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(problem);
    }

    // Illustrative only: if the controller did NOT have a local handler,
    // this advice could handle CatalogConflictException.
    @ExceptionHandler(CatalogConflictException.class)
    public ResponseEntity<Map<String, String>> globalConflict(
            CatalogConflictException ex) {
        return ResponseEntity.unprocessableEntity()
                .body(Map.of("error", "ADVICE_CATALOG_CONFLICT"));
    }
}
~~~

`ProblemDetail` is a Spring Framework 6.x type supporting error responses per **RFC 9457**. Under typical Jackson and MVC configuration, the response prefers `application/problem+json`, containing fields like `type`, `title`, `status`, `detail`, and optionally `instance`. Do not write internal error codes or sensitive data verbatim into `detail` for clients.

This advice applies only to `CatalogController` via `assignableTypes`. `@Order(HIGHEST_PRECEDENCE)` expresses priority between advices when scopes overlap; in this example the two advices have disjoint scopes, so correctness comes primarily from the selectors.

### 6.6. `BillingErrorAdvice.java`: `@ControllerAdvice` Still Returns JSON

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

@ControllerAdvice(assignableTypes = BillingController.class)
public class BillingErrorAdvice {

    @ExceptionHandler(RecordMissingException.class)
    public ResponseEntity<Map<String, String>> missing(
            RecordMissingException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of(
                        "error", "BILLING_NOT_FOUND",
                        "message", "Billing record not found"));
    }
}
~~~

This demonstrates that `@ControllerAdvice` is **not only for HTML views**: a method returning `ResponseEntity<Map<...>>` is handled by Spring as a normal HTTP body. If you change the return type to a `String` without `@ResponseBody`, handling may switch to view-name resolution.

Both advices match the same `RecordMissingException` class, yet **do not collide** because `assignableTypes` separates the catalog and billing controllers.

## 7. Running and Comparing HTTP Status/Body

In the Maven project directory, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`; if there is no Maven Wrapper, run `mvn spring-boot:run` after installing Maven.

### Catalog Missing Record

~~~bash
curl -i http://localhost:8080/api/catalog/99
~~~

Expected result **404 Not Found**, media type compatible with `application/problem+json`, JSON equivalent to:

~~~json
{
  "type": "about:blank",
  "title": "Catalog lookup failed",
  "status": 404,
  "detail": "Catalog item not found"
}
~~~

`instance` may be added by Spring from the path depending on context; do not rely on the entire JSON body or property order being fixed. If the server has custom Jackson/other advices, the representation may also differ.

### Billing Missing Record

~~~bash
curl -i http://localhost:8080/api/billing/99
~~~

Expected result **404 Not Found** with JSON:

~~~json
{
  "error": "BILLING_NOT_FOUND",
  "message": "Billing record not found"
}
~~~

Same exception, same 404 status, yet **different body** because a different advice is selected per controller.

### Local Exception Handler Beats Advice

~~~bash
curl -i http://localhost:8080/api/catalog/conflict
~~~

Expected result **409 Conflict** and JSON:

~~~json
{"error":"LOCAL_CATALOG_CONFLICT"}
~~~

If the local handler were not considered first, the catalog advice would return **422 Unprocessable Entity** with `ADVICE_CATALOG_CONFLICT`. Because the local handler exists, the global branch does not run for this request.

### Success Cases

~~~bash
curl -i http://localhost:8080/api/catalog/1
curl -i http://localhost:8080/api/billing/1
~~~

Both responses have status **200 OK**, containing respectively:

~~~json
{"id":1,"title":"Spring MVC"}
~~~

~~~json
{"id":1,"amount":750}
~~~

Because the example uses no database, data is completely static for convenient testing. On Windows PowerShell, use `curl.exe` to avoid the `curl` alias in some environments.

## 8. Testing Scope with MockMvc

Add the `spring-boot-starter-test` dependency. Create **`src/test/java/com/example/demo/AdviceScopeTest.java`**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(controllers = {
        CatalogController.class, BillingController.class
})
@Import({CatalogErrorAdvice.class, BillingErrorAdvice.class})
class AdviceScopeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void catalogErrorUsesCatalogAdvice() throws Exception {
        mockMvc.perform(get("/api/catalog/99"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.title")
                        .value("Catalog lookup failed"))
                .andExpect(jsonPath("$.detail")
                        .value("Catalog item not found"));
    }

    @Test
    void billingErrorUsesBillingAdvice() throws Exception {
        mockMvc.perform(get("/api/billing/99"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error")
                        .value("BILLING_NOT_FOUND"))
                .andExpect(jsonPath("$.message")
                        .value("Billing record not found"));
    }

    @Test
    void localExceptionHandlerWinsOverGlobalAdvice() throws Exception {
        mockMvc.perform(get("/api/catalog/conflict"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error")
                        .value("LOCAL_CATALOG_CONFLICT"));
    }

    @Test
    void successfulRequestsStillReturnNormalResponses() throws Exception {
        mockMvc.perform(get("/api/catalog/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Spring MVC"));

        mockMvc.perform(get("/api/billing/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.amount").value(750));
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

These tests verify **observable behavior**, not merely whether classes carry annotations. Specifically:
1. Catalog 404 uses RFC 9457 `ProblemDetail`, not billing's JSON.
2. Billing 404 uses billing's body, not catalog's `ProblemDetail`.
3. The local handler for `CatalogConflictException` returns 409, not 422 from the global advice.
4. Non-error paths continue responding normally.

`@WebMvcTest` builds only the web MVC test slice; `@Import` ensures both advices are present in the context. If a real project has Spring Security and CSRF, add matching authentication setup to tests that require it. Because this example only uses Spring Web + Starter Test, no real HTTP server needs to start.

## 9. A Dedicated HTML Advice with `ModelAndView`

An application serving both web pages and REST APIs can use an advice dedicated to HTML controllers:

~~~java
@ControllerAdvice(basePackageClasses = PageController.class)
public class HtmlPageAdvice {

    @ExceptionHandler(RecordMissingException.class)
    public ModelAndView missingPage(RecordMissingException ex) {
        ModelAndView mav = new ModelAndView("errors/not-found");
        mav.setStatus(HttpStatus.NOT_FOUND);
        mav.addObject("message", "Page does not exist");
        return mav;
    }
}
~~~

**This is an illustrative pattern**, not part of the runnable application in section 6: you need to create `PageController`, have a view resolver / `errors/not-found` template, and import `ModelAndView`, `HttpStatus`, and the relevant annotations.

`basePackageClasses = PageController.class` selects **the entire package containing** `PageController`, not only that class. If both API and HTML controllers share a package, this selector may include API controllers too; when you need to restrict strictly to one controller, use `assignableTypes = PageController.class`.

A common organization pattern:

- HTML controllers in `com.example.web.pages` are handled with views by `@ControllerAdvice(basePackages="com.example.web.pages")`.
- REST controllers in `com.example.web.api` are handled with JSON/`ProblemDetail` by `@RestControllerAdvice(basePackages="com.example.web.api")`.

This package layout makes scopes easy to read, though you should test carefully because subpackages and OR selectors can widen scope beyond expectations.

## 10. `ResponseEntityExceptionHandler` and Built-in Spring MVC Errors

Not every HTTP error is a custom business exception. Spring MVC also raises errors for missing request parameters, wrong HTTP methods, malformed JSON, unsupported media types, validation failures, binding errors, and other situations.

Spring Framework 6.x provides **`ResponseEntityExceptionHandler`**, a base class that `@ControllerAdvice` can extend to handle many Spring MVC exceptions and `ErrorResponse` exceptions consistently. When using it, override the appropriate protected hooks to customize status/body, and declare additional `@ExceptionHandler` methods for your own business exceptions.

**Do not** create a high-priority `@ExceptionHandler(Exception.class)` method just to turn every error into 400. Doing so easily masks real system errors, can interfere with statuses the framework already maps accurately, and produces an incorrect JSON contract for clients.

### `ProblemDetail` and RFC 9457

`ProblemDetail` has standard fields such as `type`, `title`, `status`, `detail`, and `instance`. Spring MVC can derive the status from `ProblemDetail`/response and use the `application/problem+json` media type when Jackson serializes it.

When adding business fields, use `problem.setProperty("code", "CATALOG_NOT_FOUND")` and test JSON serialization; never inject stack traces or SQL. Example:

~~~java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "Resource does not exist");
problem.setTitle("Resource not found");
problem.setProperty("code", "RESOURCE_NOT_FOUND");
~~~

This is an **illustrative snippet inside a method** (imports required). Spring supports serializing extension fields alongside standard RFC 9457 fields.

Spring Boot has the `spring.mvc.problemdetails.enabled` property in compatible 3.x versions to enable Problem Details support for many built-in errors. However, how Boot auto-configures its advice, handler ordering, and existing configs varies by version. **Do not flip a property and assume every custom exception maps to your desired body automatically**; test your specific API contract.

### Is Returning REST Error JSON with Plain `@ControllerAdvice` Valid?

Yes. In section 6's example, `BillingErrorAdvice` uses `@ControllerAdvice` and still returns `ResponseEntity<Map<String,String>>`. The return value is processed as a JSON body thanks to `ResponseEntity`. `@RestControllerAdvice` mainly avoids adding `@ResponseBody` on methods returning DTOs/Strings as bodies.

## 11. When an Exception Handler Does Not Run

Check the processing flow in the following cases before concluding an advice "isn't working":

| Case | Why advice might not handle it | How to verify |
| --- | --- | --- |
| Error thrown in a Servlet filter or Spring Security filter before MVC | Does not pass through MVC controller exception resolution | Check Security filter chain, authentication entry point, access denied handler |
| Client disconnects or response is already committed | Can no longer write status/body normally | Check logs, commit timing, and how response is streamed |
| Background task failure outside request | Not part of MVC handler execution | Use error handling for async executor, message consumer, scheduler |
| Controller does not match selector | Advice does not apply to that handler | Check package/type/annotation on controller and OR rules |
| Advice is not registered as a Spring bean | Class is outside component scan or excluded by profile/config | Check application context and startup logs |
| Local `@ExceptionHandler` exists | Local handler takes precedence before advice | Inspect controller/hierarchy |
| Another advice has higher precedence | Handler in earlier advice already matched | Check `@Order`, `Ordered`, root/cause exceptions |
| Handler returns a view name in REST | `@ControllerAdvice` + `String` lacks body semantics | Return `ResponseEntity`, add `@ResponseBody`, or use `@RestControllerAdvice` |

An `@ExceptionHandler` can rethrow **the exact exception** it received to decline handling a specific case; Spring MVC allows subsequent resolvers to continue evaluation. Only use this technique when needed, because it reduces readability and should be tested.

## 12. Common Scope Pitfalls

### 12.1. Thinking `@RestControllerAdvice` Only Catches Errors from `@RestController`

False: **the default scope does not distinguish** REST from HTML. If you want it to apply only to `@RestController`, set `annotations = RestController.class` or organize packages and configure selectors explicitly.

### 12.2. Thinking Two Selectors Combine with AND

False: `basePackages="..."` together with `annotations=RestController.class` creates an OR condition. This can make the advice broader than intended and return JSON for HTML controllers. Fix it by using a single precise criterion or grouping controllers/advices by marker/group.

### 12.3. Adding `@Order` Expecting to Override a Local Handler

No. `@Order` controls priority **among advices**; a matching local `@ExceptionHandler` inside a controller is evaluated before global advices. To change local behavior, modify the controller/hierarchy itself.

### 12.4. Generic Handler Catching All Errors and Returning 200

Anti-pattern example:

~~~java
@ExceptionHandler(Exception.class)
public ResponseEntity<String> catchEverything(Exception ex) {
    return ResponseEntity.ok("Oops");
}
~~~

This snippet is **not to be used**. It turns system failures into fake successes, hurting monitoring and clients. If you build an actual fallback handler, place it at low precedence, return 500 when appropriate, log a correlation ID, and do not reveal secrets to clients.

### 12.5. Using Internal Exception Messages as Public JSON

`ex.getMessage()` sometimes contains internal IDs, file paths, SQL, user info, or stack context. Return curated public messages while logging safely with a separate trace/correlation ID. `@RestControllerAdvice` does not sanitize sensitive text in strings you return.

### 12.6. Assuming Advice Turns Every Validation Error into the Same Exception

Errors from `@Valid @RequestBody`, `@Validated` on methods, missing `@RequestParam`, unparseable JSON, and binding failures can produce **different exception classes**. When standardizing errors, inspect the actual exceptions and `ResponseEntityExceptionHandler` hooks; avoid a single catch-all handler that ignores status codes.

### 12.7. Using `@ControllerAdvice` for Errors on Arbitrary Threads

Advice is tied to Spring MVC's request mechanism. Scheduled jobs, `@Async` executions running outside the request, or message listeners have their own error handlers. Handle exceptions in the appropriate execution context.

## 13. Review Questions

**1. Does `@RestControllerAdvice` automatically apply only to `@RestController`?**

No. It has the same default scope as `@ControllerAdvice` plus `@ResponseBody` semantics. To target only REST controllers, use an appropriate selector.

**2. If both a controller and an advice have `@ExceptionHandler` for the same exception, which does Spring prioritize?**

The controller's local handler takes precedence. This is an important behavior tested by `/api/catalog/conflict` in the example.

**3. If an advice declares both `basePackages` and `annotations`, how does Spring select controllers?**

Combined with OR: matching at least one selector is enough. Not AND.

**4. Why does `BillingErrorAdvice` use `@ControllerAdvice` and still return JSON?**

Because its exception handler returns `ResponseEntity<Map<...>>`, which has explicit HTTP response body semantics without needing class-level default `@ResponseBody`.

**5. If two advices handle the same exception and both apply, what factors should you check?**

`@Order`/`Ordered` precedence, root vs. cause matching, exception type specificity, whether a local handler exists, and whether the advice is actually present in the application context.

**6. What if you want to share `@InitBinder` without affecting every controller?**

Place `@InitBinder` in an advice with a narrow selector, or keep the binder method directly on the controller. Test the actual model attributes and converters/formatters used.

## 14. Project Adoption Checklist

1. Group REST controllers, HTML controllers, API versions, and domains cleanly if error formats differ; scope advices accordingly.
2. For REST returning DTOs or ProblemDetail, use `@RestControllerAdvice` or `@ControllerAdvice` explicitly returning `ResponseEntity`.
3. For HTML views, consider `@ControllerAdvice` + view resolver/`ModelAndView`.
4. Remember the default selector is global and multiple selectors combine with OR; choose `basePackageClasses` or `assignableTypes` to avoid brittle package strings during refactoring.
5. Avoid scattering handlers for the same exception without clear `@Order` rules and tests; local handlers still run before global ones.
6. Distinguish business exceptions from framework, filter/security, and background-task exceptions; handle each at the right layer.
7. Test **status, content type, JSON response, and advice scope** together; also test that unintended controllers are not affected.
8. Return minimal public error info without exposing stack traces/SQL/secrets; use correlation IDs and safe logging where needed.

## Official Reference Documentation

- [Spring Framework 6.2 — Controller Advice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Framework 6.2 — `@ExceptionHandler`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html)
- [Spring Framework 6.2 — `@InitBinder`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — REST Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 Javadoc — `ControllerAdvice`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/ControllerAdvice.html)
- [Spring Framework 6.2 Javadoc — `RestControllerAdvice`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/annotation/RestControllerAdvice.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
