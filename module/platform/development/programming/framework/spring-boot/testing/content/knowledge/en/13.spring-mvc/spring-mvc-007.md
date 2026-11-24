# @ControllerAdvice, Exception Handlers, and ProblemDetail in Spring MVC

## 1. Goal: Turning Exceptions into Clear HTTP Contracts

A REST API does not only have a happy path. If a client requests a nonexistent product, sends malformed JSON, violates data constraints, or requests a quantity exceeding stock, the server must respond with the **right HTTP status** and a **stable, safe, machine-friendly error body**. Rather than scattering `try/catch` blocks across every controller, Spring MVC provides **@ExceptionHandler**, **@ControllerAdvice / @RestControllerAdvice**, and **ProblemDetail**.

After this lesson, you will be able to:

- Understand the exception flow from **DispatcherServlet → HandlerExceptionResolver** to the HTTP response.
- Distinguish **controller-local** handlers from **shared handlers in @ControllerAdvice**, and know when to use **@RestControllerAdvice**.
- Map domain exceptions to HTTP **400, 404, 409, 500** under a defined policy.
- Use Spring Framework 6's **org.springframework.http.ProblemDetail** to return **RFC 9457** responses with `type`, `title`, `status`, `detail`, and `instance`.
- Customize responses with **ProblemDetail.setProperty(...)** and understand the impact on JSON.
- Handle validation for **@Valid @RequestBody**, distinguishing **MethodArgumentNotValidException** from unreadable JSON or path/query type-conversion errors.
- Understand **ResponseEntityExceptionHandler**, Spring Boot 3.3's **spring.mvc.problemdetails.enabled** property, and ordering across multiple advice classes.
- Write **MockMvc integration tests** verifying status codes, Content-Type, error JSON, and normal responses.

This hands-on lesson uses **Java 17, Spring Boot 3.3.5, Spring MVC, JUnit Jupiter, Gradle**. It targets **Spring MVC (servlet stack)**. Spring WebFlux has corresponding primitives, though you must apply the reactive stack's APIs rather than copying servlet flows directly to WebFlux.

## 2. Three Core Building Blocks

### 2.1. @ExceptionHandler: Catching Exceptions at the Web Layer

**@ExceptionHandler** is placed on a method inside a controller or advice class. Spring locates a matching method when request-handling code throws an exception:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
ProblemDetail handleNotFound(ProductNotFoundException ex) {
    ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Product does not exist");
    body.setTitle("Product not found");
    return body;
}
~~~

This is an **illustrative snippet inside a controller/advice class**, not a standalone Java file. It converts a specific exception type into a `ProblemDetail` with status 404. Returning **ProblemDetail** is supported by Spring MVC, and its `status` field sets the HTTP status of the exception handler's response.

### 2.2. @ControllerAdvice: Shared Handling Across Multiple Controllers

**@ControllerAdvice** is a Spring component registered in the `ApplicationContext` that can contain:

- `@ExceptionHandler`: shared error handling.
- `@InitBinder`: custom data binding.
- `@ModelAttribute`: shared model attributes for matching controllers.

When returning JSON bodies for REST APIs, **@RestControllerAdvice** combines **@ControllerAdvice + @ResponseBody**. That means handler return values are written directly to the HTTP response via message converters rather than resolved as view template names.

~~~java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    ProblemDetail handle(ProductNotFoundException ex) {
        return ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
    }
}
~~~

This snippet illustrates the structure; you can add `type`/`title`/`detail` and imports as shown in the complete project in Section 5. **@ControllerAdvice does not automatically handle every exception**: there must be a matching handler, inherited Spring support, or another resolver/fallback.

### 2.3. ProblemDetail: Representing Errors per RFC 9457

**ProblemDetail** is Spring's standard model for "Problem Details for HTTP APIs." RFC 9457 obsoletes and replaces the earlier RFC 7807. Five standard fields are commonly used:

| Field | JSON Type | Meaning | Example |
|---|---|---|---|
| **type** | URI string | Identifies the **error category**, should stay stable across requests | `"https://example.org/problems/product-not-found"` |
| **title** | string | Short summary describing the error category | `"Product not found"` |
| **status** | number | HTTP status code for this error occurrence | `404` |
| **detail** | string | Human-readable explanation for **this specific occurrence** | `"Product 99 does not exist"` |
| **instance** | URI string | Identifies the specific occurrence, often the request path | `"/api/products/99"` |

Explicitly defined example response:

~~~json
{
  "type": "https://example.org/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "Product 99 does not exist",
  "instance": "/api/products/99",
  "errorCode": "PRODUCT_NOT_FOUND"
}
~~~

This is an **intentional JSON example**, not a claim that every Spring Boot setup emits these exact six fields. `errorCode` is a custom API extension, not one of the five standard fields. The **type** value can be a URI managed by your organization; `example.org` here is purely illustrative, not a live documentation endpoint.

**Do not equate the HTTP status line with the JSON status field.** In an ideal response, both stay consistent; clients should rely on HTTP status for transport-level success/failure classification and `type`/`errorCode` for programmatic business handling.

## 3. How Do Exceptions Flow Through Spring MVC?

High-level diagram in a servlet application:

~~~text
HTTP request
     |
     v
Servlet filters / Spring Security (if present)
     |
     v
DispatcherServlet
     |
     v
HandlerMapping -> Controller -> Service
                           |
                           | throws Exception
                           v
                HandlerExceptionResolver chain
                           |
                           +-- ExceptionHandlerExceptionResolver
                           |      local @ExceptionHandler
                           |      @ControllerAdvice/@RestControllerAdvice
                           |
                           +-- ResponseStatusExceptionResolver
                           |      @ResponseStatus / ResponseStatusException
                           |
                           +-- DefaultHandlerExceptionResolver
                                  framework MVC exceptions
                           |
                           v
                  HTTP status / headers / body
                           |
                           +-- If still unhandled: may reach
                               servlet container / Spring Boot /error
~~~

This is a **conceptual model**, not a guarantee that every application has an immutable resolver list or order. Custom configuration can alter the resolver chain.

**Local handler or advice?** An `@ExceptionHandler` method inside a controller is typically evaluated **before** global `@ControllerAdvice` for exceptions originating in that controller. This helps when one controller has a bespoke error contract, while shared advice handles error types spanning many controllers.

**Multiple advice classes:** **`@Order`** or the `Ordered` interface establishes precedence. When multiple advice classes can handle the same exception, define an explicit ordering policy. A broad `Exception.class` advice with high precedence can swallow exceptions intended for a specialized lower-precedence advice.

**Scope:** `@ControllerAdvice` primarily covers Spring MVC request processing. Errors occurring in a servlet filter **before reaching `DispatcherServlet`**, in background schedulers, manually spawned threads, or components outside MVC may require separate handling. Spring Security authentication/authorization failures are normally routed through entry points or access denied handlers in the security filter chain.

## 4. @ControllerAdvice, @RestControllerAdvice, @ResponseStatus, and ResponseEntityExceptionHandler

| Tool | Purpose | When to Use |
|---|---|---|
| **@ExceptionHandler** | Selects a method to handle one or more exceptions | Specific business exceptions or MVC errors |
| **@ControllerAdvice** | Shared handlers/binders/models without automatic `@ResponseBody` | MVC apps mixing HTML views and REST endpoints |
| **@RestControllerAdvice** | `ControllerAdvice` with response-body semantics | REST APIs returning JSON/`ProblemDetail` |
| **@ResponseStatus** | Assigns a fixed HTTP status to a method or exception class | Simple cases needing only a status code |
| **ResponseStatusException** | Throws an exception carrying an HTTP status from the web layer | Short web-layer flows without custom domain exceptions |
| **ResponseEntity<ProblemDetail>** | Explicit control over status, headers, and body | Handlers needing custom headers like `Retry-After`, `Location`, etc. |
| **ResponseEntityExceptionHandler** | Spring base class handling standard MVC exceptions with override hooks | Standardizing built-in framework exceptions or customizing validation/binding errors |
| **ProblemDetail** | RFC 9457 body supporting standard and extension properties | Structured error contracts for HTTP clients |

For many APIs, the cleanest separation is **domain/service throwing meaningful exceptions**, while the web layer via `@RestControllerAdvice` decides HTTP 404/409/400. Pure Java services do not need to depend on `HttpStatus` or `ResponseStatusException`; decoupling keeps business logic tests and HTTP contract tests independent.

**Do not reflexively slap `@ResponseStatus(HttpStatus.NOT_FOUND)` onto every domain exception.** It is concise, but couples the domain to HTTP knowledge and does not guarantee a `ProblemDetail` with your `type`/`errorCode`. For tiny web-only code, `ResponseStatusException` can fit; for multi-endpoint APIs, advice is usually easier to govern.

## 5. Complete Example: Spring Boot 3.3.5 Returning Consistent ProblemDetail

The sample application exposes:

- **GET /api/products/1** → 200, product.
- **GET /api/products/99** → 404, `ProblemDetail` with `type=product-not-found`.
- **POST /api/products/availability-checks** with `productId=1, quantity=2` → 200, availability result.
- POST to the same path with `productId=2, quantity=1` → 409, `ProblemDetail` with `type=insufficient-stock`.
- POST with `quantity=0` or missing `productId` → 400, `ProblemDetail` with `type=invalid-request` and a `violations` array.
- GET with a path variable unparseable as `long`, or POST with malformed JSON → 400, handled by Spring Boot's framework exception support returning `ProblemDetail` when configured.

**Data model:** Product 1 has 5 in stock; product 2 has 0 in stock. The availability-check endpoint **creates no reservations, deducts no stock, and writes no database**, so tests require no cleanup. This keeps the exercise focused on exception handling rather than concurrency and persistence.

### 5.1. Files and Dependencies

~~~text
settings.gradle
build.gradle
src/main/resources/application.properties
src/main/java/demo/errors/ErrorsApplication.java
src/main/java/demo/errors/Product.java
src/main/java/demo/errors/AvailabilityRequest.java
src/main/java/demo/errors/AvailabilityResult.java
src/main/java/demo/errors/ProductNotFoundException.java
src/main/java/demo/errors/InsufficientStockException.java
src/main/java/demo/errors/CatalogService.java
src/main/java/demo/errors/ProductController.java
src/main/java/demo/errors/ApiErrorAdvice.java
src/test/java/demo/errors/ProductApiErrorTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'mvc-problem-detail-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Why is `spring-boot-starter-validation` needed?** Spring Boot 3.x does not automatically include Jakarta Bean Validation with `starter-web` alone. In this example, **`@NotNull`** and **`@Min`** on the request DTO require the Bean Validation provider brought in by `starter-validation`. Without this dependency, do not assume `@Valid` enforces constraints as designed.

**src/main/resources/application.properties**

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

In Spring Boot 3.3, this property enables `ProblemDetail` responses for built-in HTTP/MVC exceptions auto-configured by Boot. The example **does not rely on this property to build bodies for domain exceptions handled by `ApiErrorAdvice`**: that handler returns `ProblemDetail` directly. The property mainly ensures framework errors such as invalid JSON or type conversion emit consistent problem details.

In Spring Boot 3.3, Boot automatically registers a `ResponseEntityExceptionHandler` for framework exceptions when this property is enabled. The custom advice in this example uses **`@Order(Ordered.HIGHEST_PRECEDENCE)`** so our validation handler runs before Boot's framework handler. If a project already defines advice with a different order or overlapping exceptions, check precedence and avoid duplicate mappings.

### 5.2. Application and Domain DTOs

**src/main/java/demo/errors/ErrorsApplication.java**

~~~java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorsApplication.class, args);
    }
}
~~~

**src/main/java/demo/errors/Product.java**

~~~java
package demo.errors;

public record Product(long id, String name, int available) {
}
~~~

**src/main/java/demo/errors/AvailabilityRequest.java**

~~~java
package demo.errors;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

public record AvailabilityRequest(
        @NotNull Long productId,
        @Min(1) int quantity) {
}
~~~

**src/main/java/demo/errors/AvailabilityResult.java**

~~~java
package demo.errors;

public record AvailabilityResult(
        long productId,
        int requestedQuantity,
        boolean available) {
}
~~~

**Java 17 records** keep DTOs concise and immutable across their fields. Using `Long` (wrapper) for `productId` distinguishes **null** from a numeric value; using `int` for `quantity` with `@Min(1)` rejects `0` or negative numbers. Jakarta validation annotations execute when the controller applies `@Valid` to the request body.

### 5.3. Two HTTP-Independent Business Exceptions

**src/main/java/demo/errors/ProductNotFoundException.java**

~~~java
package demo.errors;

public final class ProductNotFoundException extends RuntimeException {

    private final long productId;

    public ProductNotFoundException(long productId) {
        super("Product " + productId + " was not found");
        this.productId = productId;
    }

    public long productId() {
        return productId;
    }
}
~~~

**src/main/java/demo/errors/InsufficientStockException.java**

~~~java
package demo.errors;

public final class InsufficientStockException extends RuntimeException {

    private final long productId;

    public InsufficientStockException(long productId) {
        super("Insufficient stock for product " + productId);
        this.productId = productId;
    }

    public long productId() {
        return productId;
    }
}
~~~

Named exceptions with structured fields help the web layer choose status codes and public messages. Domain code never imports `HttpStatus.NOT_FOUND` or `HttpStatus.CONFLICT`. In real systems, public `detail` content must follow **security policies**: never expose SQL, stack traces, tokens, passwords, or customer PII in responses.

### 5.4. Service Running with Fixed In-Memory Data

**src/main/java/demo/errors/CatalogService.java**

~~~java
package demo.errors;

import java.util.Map;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final Map<Long, Product> products = Map.of(
            1L, new Product(1L, "Keyboard", 5),
            2L, new Product(2L, "Mouse", 0)
    );

    public Product getProduct(long productId) {
        Product product = products.get(productId);
        if (product == null) {
            throw new ProductNotFoundException(productId);
        }
        return product;
    }

    public AvailabilityResult checkAvailability(
            AvailabilityRequest request) {
        Product product = getProduct(request.productId());
        if (request.quantity() > product.available()) {
            throw new InsufficientStockException(product.id());
        }

        return new AvailabilityResult(
                product.id(), request.quantity(), true);
    }
}
~~~

**Scope note:** the controller validates the request before calling the service. If a Java caller **bypasses the controller** and passes an `AvailabilityRequest` with `productId=null`, unboxing will throw a `NullPointerException`. In production, enforce clear service contracts and validate at the service boundary if multiple callers use it. This sample relies on web-validated data to keep the focus on **Spring MVC error responses**.

`Map.of` creates an immutable map with no database or mutable singleton counters, keeping tests independent and order-agnostic.

### 5.5. Controller: Handling the Happy Path, Letting Exceptions Bubble Up

**src/main/java/demo/errors/ProductController.java**

~~~java
package demo.errors;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final CatalogService catalog;

    public ProductController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/{id}")
    public Product getById(@PathVariable long id) {
        return catalog.getProduct(id);
    }

    @PostMapping("/availability-checks")
    public ResponseEntity<AvailabilityResult> check(
            @Valid @RequestBody AvailabilityRequest request) {
        AvailabilityResult result = catalog.checkAvailability(request);
        return ResponseEntity.ok(result);
    }
}
~~~

The controller has **no `try/catch`** around each call. When `CatalogService` throws `ProductNotFoundException` or `InsufficientStockException`, Spring MVC delegates to exception resolution. When `@Valid` fails on `@RequestBody`, Spring MVC throws **`MethodArgumentNotValidException`** before `check(...)` executes. Those are three distinct error sources; the advice maps them to a uniform contract.

**Processing order:** on `GET /api/products/not-a-number`, converting `"not-a-number"` to `long` fails while resolving `@PathVariable`, so `getById` never runs. That is a framework binding error, distinct from `ProductNotFoundException` when a valid numeric ID has no matching record.

### 5.6. @RestControllerAdvice Returning ProblemDetail with Stable Type and errorCode

**src/main/java/demo/errors/ApiErrorAdvice.java**

~~~java
package demo.errors;

import java.net.URI;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail missing(
            ProductNotFoundException ex, HttpServletRequest request) {

        return problem(
                HttpStatus.NOT_FOUND,
                "Product not found",
                "Product " + ex.productId() + " does not exist",
                "product-not-found",
                "PRODUCT_NOT_FOUND",
                request);
    }

    @ExceptionHandler(InsufficientStockException.class)
    public ProblemDetail unavailable(
            InsufficientStockException ex, HttpServletRequest request) {

        return problem(
                HttpStatus.CONFLICT,
                "Insufficient stock",
                "Cannot fulfill request for product " + ex.productId(),
                "insufficient-stock",
                "INSUFFICIENT_STOCK",
                request);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail validation(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {

        ProblemDetail body = problem(
                HttpStatus.BAD_REQUEST,
                "Invalid request",
                "Request body violates validation constraints",
                "invalid-request",
                "INVALID_REQUEST",
                request);

        List<Map<String, String>> violations =
                ex.getBindingResult().getFieldErrors().stream()
                    .map(field -> Map.of(
                            "field", field.getField(),
                            "message", Objects.toString(
                                    field.getDefaultMessage(),
                                    "Invalid value")))
                    .toList();

        body.setProperty("violations", violations);
        return body;
    }

    private static ProblemDetail problem(
            HttpStatus status,
            String title,
            String detail,
            String typeSlug,
            String errorCode,
            HttpServletRequest request) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(status, detail);

        body.setTitle(title);
        body.setType(URI.create(
                "https://example.org/problems/" + typeSlug));
        body.setInstance(URI.create(request.getRequestURI()));
        body.setProperty("errorCode", errorCode);

        return body;
    }
}
~~~

**Technical details to understand:**

1. **@RestControllerAdvice** is discovered by Spring Boot component scanning because it sits under package `demo.errors` below `ErrorsApplication`.
2. Three `@ExceptionHandler` methods match exact exception types; the `MethodArgumentNotValidException` handler covers validation on `@Valid @RequestBody`, not all possible request errors.
3. `@Order(Ordered.HIGHEST_PRECEDENCE)` prioritizes this advice ahead of the framework advice Boot configures when problem details are enabled. Do not add a catch-all `@ExceptionHandler(Exception.class)` carelessly that masks specific errors.
4. **ProblemDetail.forStatusAndDetail(status, detail)** constructs the body with the matching status. When `@ExceptionHandler` returns `ProblemDetail`, Spring MVC uses its status to set the HTTP response status.
5. **setType(...)** sets the URI identifying the error category; **setInstance(...)** uses the current request path. These two fields serve different purposes.
6. **setProperty("errorCode", ...)** adds an extension field. With Spring MVC's Jackson mixin for `ProblemDetail`, extension properties serialize as **top-level JSON properties**, such as `errorCode` and `violations`.
7. **Objects.toString(message, "Invalid value")** handles null default validation messages. The `violations` array includes only field names and public messages, avoiding `rejectedValue` which might hold sensitive data.
8. **`PRODUCT_NOT_FOUND` / `INSUFFICIENT_STOCK` / `INVALID_REQUEST`** are this example's contract codes, not built-in Spring enums.

**About `@Order`:** if a project has multiple advice beans, maintain a clear precedence rule. A high-precedence global advice catching broad `Exception` can steal exceptions from a lower-precedence domain advice. Never mark every advice as `HIGHEST_PRECEDENCE`; conflicting advice beans become hard to predict and maintain.

## 6. Complete Test Suite with @SpringBootTest and MockMvc

In this example we want to test **both the real `CatalogService` and `ApiErrorAdvice`**, so we use `@SpringBootTest` + `@AutoConfigureMockMvc`: it loads the real application context, while **`mvc.perform`** uses mock servlet requests **without starting an embedded server on a real TCP port**. That suffices to verify Spring MVC's HTTP status/JSON contract in the sample app.

**src/test/java/demo/errors/ProductApiErrorTest.java**

~~~java
package demo.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ProductApiErrorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void knownProductReturns200() throws Exception {
        mvc.perform(get("/api/products/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Keyboard"))
                .andExpect(jsonPath("$.available").value(5));
    }

    @Test
    void missingProductReturns404Problem() throws Exception {
        mvc.perform(get("/api/products/99"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.type").value(
                        "https://example.org/problems/product-not-found"))
                .andExpect(jsonPath("$.title").value("Product not found"))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.detail").value(
                        "Product 99 does not exist"))
                .andExpect(jsonPath("$.instance").value("/api/products/99"))
                .andExpect(jsonPath("$.errorCode")
                        .value("PRODUCT_NOT_FOUND"));
    }

    @Test
    void validAvailabilityRequestReturns200() throws Exception {
        mvc.perform(post("/api/products/availability-checks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"productId":1,"quantity":2}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.productId").value(1))
                .andExpect(jsonPath("$.requestedQuantity").value(2))
                .andExpect(jsonPath("$.available").value(true));
    }

    @Test
    void noStockReturns409Problem() throws Exception {
        mvc.perform(post("/api/products/availability-checks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"productId":2,"quantity":1}
                                """))
                .andExpect(status().isConflict())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(409))
                .andExpect(jsonPath("$.title").value("Insufficient stock"))
                .andExpect(jsonPath("$.errorCode")
                        .value("INSUFFICIENT_STOCK"));
    }

    @Test
    void invalidQuantityReturns400WithViolations() throws Exception {
        mvc.perform(post("/api/products/availability-checks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"productId":1,"quantity":0}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.errorCode")
                        .value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("quantity"));
    }

    @Test
    void missingProductIdReturns400WithViolations() throws Exception {
        mvc.perform(post("/api/products/availability-checks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"quantity":1}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.errorCode")
                        .value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.violations[0].field")
                        .value("productId"));
    }

    @Test
    void malformedJsonReturnsFramework400() throws Exception {
        mvc.perform(post("/api/products/availability-checks")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"productId\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void invalidPathVariableReturnsFramework400() throws Exception {
        mvc.perform(get("/api/products/not-a-number"))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Total tests in file:** 8 `@Test` methods. The last two tests **assert only status 400** to avoid coupling to a specific error body shape that is not the focus of those two cases. When `spring.mvc.problemdetails.enabled=true`, the framework can produce `ProblemDetail` for JSON parsing/type conversion errors; exact `detail`/`title` values depend on configuration, message sources, and Spring version. Custom handlers in `ApiErrorAdvice` are where the application explicitly defines `errorCode` and `type`.

**Why `@SpringBootTest` instead of `@WebMvcTest` here?** Because `CatalogService` holds a real product map and needs no external dependencies. `@SpringBootTest` verifies the full controller → service → exception advice path. If you only want to test the web layer independently of data/services, `@WebMvcTest` with `@MockBean` for dependencies is faster.

**Not every HTTP 400 comes from the same exception:** `quantity=0` passes Jackson → DTO → `@Valid` and throws `MethodArgumentNotValidException`; path `"not-a-number"` fails type conversion; truncated JSON triggers `HttpMessageNotReadableException`. Same HTTP status, **different causes and handlers**.

### 6.1. Running the Tests

In the directory containing `build.gradle`, if the project has a Gradle Wrapper:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you created the project by copying the files above, **Gradle Wrapper scripts/files are not listed**, so `./gradlew` works only if you generated a Wrapper. If not, run **`gradle test`** with a Gradle version compatible with Spring Boot 3.3.x or generate the Wrapper first.

You can run the test class alone:

~~~bash
./gradlew test --tests demo.errors.ProductApiErrorTest
~~~

Gradle HTML reports typically appear at **`build/reports/tests/test/index.html`**. With the exact sample files and no other tests, you will see **8 JUnit Jupiter tests**. No database or external service is needed, and results do not depend on execution order. If Spring Security is on the classpath or a real project has its own `ControllerAdvice`, adjust fixtures/expectations to match the active contract and handler ordering.

### 6.2. Interpreting a 404 Error in the Response

For example, `GET /api/products/99` returns:

~~~json
{
  "type": "https://example.org/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "Product 99 does not exist",
  "instance": "/api/products/99",
  "errorCode": "PRODUCT_NOT_FOUND"
}
~~~

The HTTP response status is **404**; `Content-Type` is compatible with **`application/problem+json`**. `type` stays consistent across the entire "product not found" category; `instance` varies per request; `detail` can include the ID for diagnostics without revealing stack traces or secrets. 409 and 400 errors use distinct `type` and `errorCode` values so clients can handle them differently even though all are failures.

**RFC note:** the five standard field names are supported, yet not every response requires developer-supplied values for all five. Spring supplies defaults for `type`/`title`/`instance` in certain cases; if you want a fixed API contract, set them explicitly and verify them with integration tests as above.

## 7. @WebMvcTest + @MockBean When Testing Advice/Controller in Isolation

If you only want to verify Spring MVC exception mapping without loading the full context, you can use a test slice:

~~~java
// Illustrative snippet in Spring Boot 3.3, not part of the Section 5
// example files: requires full imports and test class structure.
@WebMvcTest(ProductController.class)
class ProductControllerWebSliceTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    CatalogService catalog;

    @Test
    void missingProductIsMappedTo404() throws Exception {
        when(catalog.getProduct(99L))
                .thenThrow(new ProductNotFoundException(99L));

        mvc.perform(get("/api/products/99"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode")
                        .value("PRODUCT_NOT_FOUND"));
    }
}
~~~

**`@WebMvcTest`** picks up matching web components, including `@ControllerAdvice` within slice scope, while `@MockBean` overrides `CatalogService` so the controller gets its dependency. If advice lives outside component scan/slice boundaries in a particular app, you may need **`@Import(ApiErrorAdvice.class)`** explicitly. In Spring Boot 3.3, `@MockBean` lives in package **`org.springframework.boot.test.mock.mockito`**; on newer Boot releases, check **`@MockitoBean`** before copying code.

**Coverage distinction:** a web slice does not verify `CatalogService`'s real logic. It verifies how the controller and advice translate simulated exceptions into HTTP responses. Service unit tests should verify when `ProductNotFoundException`/`InsufficientStockException` are thrown.

## 8. ResponseEntityExceptionHandler and Framework Exceptions

Beyond business exceptions, Spring MVC raises many exceptions **before the controller executes**:

| Error Category | Common Exception | Typical HTTP Status |
|---|---|---|
| `@Valid @RequestBody` fails constraint | `MethodArgumentNotValidException` | 400 |
| Malformed or unconvertible JSON | `HttpMessageNotReadableException` | 400 |
| Missing required `@RequestParam` | `MissingServletRequestParameterException` | 400 |
| `@PathVariable`/`@RequestParam` conversion failure | `MethodArgumentTypeMismatchException` or `TypeMismatchException` family | 400 |
| Unsupported HTTP method | `HttpRequestMethodNotSupportedException` | 405 (often with `Allow` header) |
| Unsupported `Content-Type` | `HttpMediaTypeNotSupportedException` | 415 |
| `Accept` cannot match response format | `HttpMediaTypeNotAcceptableException` | 406 |
| Missing handler or resource | `NoHandlerFoundException` / `NoResourceFoundException`, depending on MVC/resource mapping | 404 |

In Spring Framework 6.1+, **`ResponseEntityExceptionHandler`** is a base class containing `@ExceptionHandler` methods for standard MVC exceptions and protected hooks for customization.

Example of **an alternative strategy**—do not place this class into the project alongside `ApiErrorAdvice` unless ordering and handler ownership are clearly defined:

~~~java
// Abbreviated snippet needing full imports in a separate project:
@RestControllerAdvice
public class FrameworkErrorAdvice
        extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail body = ex.getBody();
        body.setTitle("Request validation failed");
        body.setProperty("errorCode", "INVALID_REQUEST");

        return handleExceptionInternal(
                ex, body, headers, status, request);
    }
}
~~~

With inheritance, you **override the base class hook** rather than adding `@ExceptionHandler(MethodArgumentNotValidException.class)` to the overridden method. The base class already defines that `@ExceptionHandler`, and duplicating it causes ambiguous handler mappings.

**Do not mix the two strategies blindly:**

- Strategy A: Enable `spring.mvc.problemdetails.enabled=true` so Boot handles framework exceptions, and write `@RestControllerAdvice` specifically for domain exceptions and select custom cases.
- Strategy B: Extend `ResponseEntityExceptionHandler` yourself to customize most MVC exceptions, explicitly owning your handlers and how they interact with auto-configuration.

Pick one consistent policy, write tests proving **the right handler executes**, and avoid two advice beans claiming the same exception without explicit precedence.

## 9. `spring.mvc.problemdetails.enabled` and Its Scope

In Spring Boot 3.3.x:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

This setting enables `ProblemDetail` support for **built-in HTTP/MVC exceptions** via auto-configuration. It does not automatically turn every `RuntimeException` in the business layer into a custom-typed `ProblemDetail`. Business exceptions like `ProductNotFoundException` should still be mapped explicitly via advice or intentional `ErrorResponse`/`ResponseStatusException` mechanisms.

Do not assume **disabling this property means you cannot return `ProblemDetail`**. An `@ExceptionHandler` you write can return `ProblemDetail` directly without this property. Conversely, enabling the property does not guarantee that responses from Spring Security filters, custom servlet filters, or non-MVC errors share the same body.

**Regarding Spring Boot `/error`:** Boot provides fallback error handling including `BasicErrorController` and error attributes. Unhandled exceptions may pass through servlet error dispatch to `/error` instead of a custom `@RestControllerAdvice` response. The exact path depends on the error, servlet container, framework version, and configuration. Never describe `@ControllerAdvice` as an application-wide catch-all.

**Status does not guarantee body:** a framework exception might resolve to 404/405 with a body differing from your custom contract. If the API requires `errorCode` on every error, design and test all key exception categories, including authentication/security and non-MVC errors if covered by your published contract.

## 10. Choosing the Right HTTP Status for Business Semantics

| Status | Meaning | Reasonable Example |
|---|---|---|
| **400 Bad Request** | Structurally or semantically invalid request input | `quantity=0`, missing `productId`, malformed JSON |
| **401 Unauthorized** | Missing or invalid authentication | No valid access token |
| **403 Forbidden** | Authenticated but lacking permission | User lacks authority for the action |
| **404 Not Found** | Resource does not exist, or concealing existence per security policy | Product 99 does not exist |
| **405 Method Not Allowed** | Resource exists, HTTP method unsupported | PUT to a GET-only endpoint |
| **409 Conflict** | Request conflicts with resource state | Requested quantity exceeds stock in this sample model |
| **422 Unprocessable Content** | Syntactically valid body rejected by business rules | Appropriate if defined in the API contract |
| **500 Internal Server Error** | Unexpected server failure | Unhandled `NullPointerException`/bug |

No single status table applies universally across all domains. For instance, "insufficient stock" can use **409** or **422** depending on the contract; this lesson picks 409 and tests that expectation. **Never return 200 with `success=false`** for an error where the API specifies 4xx; clients, monitoring, and HTTP caches will misinterpret it.

From the web layer, domain exceptions should map consistently. If multiple endpoints have "not found" errors with distinct meanings, use distinct exception types, error codes, and type URIs rather than one generic `IllegalArgumentException` everywhere.

## 11. Designing ProblemDetail for Clients and Long-Term Compatibility

### 11.1. Type URIs Should Be Durable

`type` identifies the **error category**; clients can switch on it programmatically. If you choose a real URI (such as your organization's API documentation site), host documentation explaining its semantics, status, extension fields, and remediation. Never vary `type` based on exception messages or request data.

**`instance`** identifies the **error occurrence**. It can be the request path as in the sample or an occurrence-specific URI. When paths contain sensitive values, avoid leaking secrets in `instance`; consider a non-sensitive trace ID instead.

### 11.2. `errorCode` and `violations` Are Extension Fields

**`ProblemDetail.setProperty("errorCode", "...")`** and **`setProperty("violations", ...)`** attach application-specific data. Spring's Jackson mixin serializes them as top-level JSON fields. Clients should depend only on fields **documented in the API spec**, not guess ad-hoc fields per exception.

Validation error example:

~~~json
{
  "type": "https://example.org/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request body violates validation constraints",
  "instance": "/api/products/availability-checks",
  "errorCode": "INVALID_REQUEST",
  "violations": [
    {
      "field": "quantity",
      "message": "must be greater than or equal to 1"
    }
  ]
}
~~~

**Do not lock tests onto literal message strings above** when generated by a Bean Validation provider/locale; messages can change under localization settings. In tests, assert field names. If clients need stable per-field error codes, define explicit constraint codes instead of relying on English messages.

### 11.3. Never Leak Internal Information

In Internet-facing responses, avoid:
- Stack traces, internal class names, filesystem paths, SQL statements, or JDBC connection strings.
- Passwords, session tokens, API keys, secret cookies, or full request bodies holding personal data.
- Raw low-level exception messages **`ex.getMessage()`** unless sanitized for clients.
- Debug details from databases or external services.

Emit concise public details and log full causes **server-side** with a correlation ID. When handling unexpected exceptions, return a sanitized 500 `ProblemDetail` without stack traces. However, a global `@ExceptionHandler(Exception.class)` must be carefully designed and ordered so it does not swallow framework 400/404/405 or security errors.

### 11.4. Observability, Logging, and Tracing

Exceptions caught by `@ExceptionHandler` may no longer look like unhandled errors to certain metrics/observability tools. If your system needs accurate metrics/traces, inspect how Spring/Micrometer Observations record handled exceptions. Avoid logging the same exception multiple times across controller, service, advice, and servlet filters; prefer a single well-contextualized log point per project policy with a safe `traceId`.

### 11.5. Internationalization (i18n)

Spring supports `MessageSource` and message codes for `ErrorResponse`/`ResponseEntityExceptionHandler`. If an API supports multiple languages, determine rules from `Accept-Language` or user locale. **`type`/`errorCode` should remain stable**; `title`/`detail` may be translated. Never let clients key logic off translated `title`/`detail` strings.

## 12. Handler Priority, Cause Matching, and Multiple Advice Classes

**Local vs. global precedence:** if a controller defines a matching `@ExceptionHandler`, the local handler usually takes precedence over global advice. For example, one controller might intentionally render a custom HTML error view while most REST controllers share a global `ProblemDetail` advice. If such narrow scoping must be preserved, write dedicated tests for that controller.

**Cause matching:** `@ExceptionHandler` can match either the top-level exception or nested causes along the cause chain. Within a single advice, a match on the root exception normally wins over deeper cause matches. Across multiple advice beans, ordering can cause a cause match in a higher-precedence advice to beat a root match in a lower-precedence advice. Therefore avoid high-precedence catch-all handlers when you want domain-specific specialization.

**Restricting advice scope:** `@ControllerAdvice` can target controllers by package, marker annotation, or type. Syntax example:

~~~java
@RestControllerAdvice(basePackageClasses = ProductController.class)
class CatalogOnlyErrorAdvice {
    // @ExceptionHandler methods here target controllers in
    // ProductController's package.
}
~~~

Illustrative snippet, not part of the runnable project above. You can use `basePackages`, `assignableTypes`, or `annotations` to scope applicability; verify exact behavior against real controllers and avoid scoping wider than intended.

**Watch for ambiguous mappings:** two `@ExceptionHandler` methods in **the same controller/advice** mapping the exact same exception without distinction can fail at startup or when initializing the exception resolver. Across two separate advice classes, `@Order` resolves precedence, though ownership of each error should still stay clear.

## 13. Tricky Cases: Exceptions Outside Controllers

| Where the Error Occurs | Does `@RestControllerAdvice` Always Handle It? | Mechanism to Check |
|---|---|---|
| Inside `@RequestMapping` handler or MVC argument resolver | Usually yes, if a handler matches | `@ExceptionHandler` / `HandlerExceptionResolver` |
| `@Valid @RequestBody` | Yes, via `MethodArgumentNotValidException` | Advice or `ResponseEntityExceptionHandler` |
| Servlet filter before `DispatcherServlet` | **Not guaranteed** | Servlet container error handling, filter/security handlers |
| Spring Security Authentication/AccessDenied | Does not share MVC advice by default | `AuthenticationEntryPoint`, `AccessDeniedHandler` |
| Spring `@Scheduled` | No | Task error handling and logging |
| `@Async` or `CompletableFuture` outside request | Not automatically | Future/completion handlers, executor error handling |
| Server already wrote/committed response body | Cannot reliably alter status/body afterward | Logging, async/error dispatch, streaming design |
| WebSocket/message consumer | Not by default | Messaging stack exception handling |
| WebFlux reactive controller | Different mechanism from servlet MVC | Reactive exception handling / `WebExceptionHandler` |

This matters whenever teams assume "the entire system always emits the same error JSON." MVC advice does not cover every boundary. With Spring Security, if the API requires RFC 9457 for 401/403, configure `AuthenticationEntryPoint`/`AccessDeniedHandler` to emit `ProblemDetail` or an equivalent contract, and verify with real requests.

## 14. Common Mistakes When Learning and Implementing

| Mistake | Consequence | Fix |
|---|---|---|
| Every controller duplicates `try/catch` | Repeated logic, inconsistent error bodies | Use typed exceptions + `@RestControllerAdvice` |
| Using `@ControllerAdvice` expecting methods to auto-return JSON | Return values may be treated as view names without `@ResponseBody` | Use `@RestControllerAdvice` for REST APIs |
| Creating `ProblemDetail` with the wrong HTTP status | Clients/monitoring misinterpret outcomes | Use `forStatusAndDetail` + status assertions |
| Confusing `type` with `instance` | Clients struggle to classify error types | `type` is the category, `instance` is the occurrence |
| Assuming `spring.mvc.problemdetails.enabled` maps all `RuntimeException`s | Domain errors remain unmapped | Write `@ExceptionHandler` for domain exceptions |
| Multiple advice beans competing for the same exception | Unpredictable ordering, broken contract | Clear ownership and explicit `@Order` |
| Overly broad `@ExceptionHandler(Exception.class)` | Swallows 400/404/405, returns wrong 500s | Specific handlers first; catch-all with extreme care |
| Returning raw `ex.getMessage()` from DB/stack | Leaks internal details | Sanitize public detail; log internals separately |
| Omitting `starter-validation` yet expecting `@Valid` to enforce `@Min` | Constraints silently skipped | Add `spring-boot-starter-validation` |
| Putting `@NotNull` on primitive `int` | Can never be null | Use wrapper `Integer` or an appropriate constraint |
| Hardcoding English validation messages in tests | Flaky across locales/providers | Assert stable field names and `errorCode` |
| Comparing raw JSON strings by key order | Brittle, unnecessary failures | Use JSONPath / `JsonNode` |
| Conflating malformed JSON with validation errors | Binding edge cases go untested | Separate test cases per layer |
| Putting `@ResponseStatus` on domain exceptions expecting `errorCode` | Custom properties are not auto-generated | Use advice / `ProblemDetail` |
| Never testing real HTTP status | Right Java exception, wrong API contract | MockMvc or real HTTP client tests |
| Assuming `@RestControllerAdvice` formats filter/security errors | 401/403 keep a different format | Configure dedicated security handlers |

## 15. Checklist for Applying to a Real Spring MVC Project

1. **Categorize errors by root cause:** request binding/validation; resource not found; business conflict; dependency failure; unexpected server error.
2. **Create a mapping table: exception → HTTP status → type URI → errorCode**, with clear owners and body contracts.
3. **Keep the domain layer HTTP-independent** where possible; throw meaningful exceptions instead of generic `IllegalArgumentException` everywhere.
4. **Pick a Spring MVC strategy:** `@RestControllerAdvice` for domain errors; decide between `ResponseEntityExceptionHandler` or Boot's `problem-details` auto-config for framework errors.
5. **Set `type`/`title`/`detail`/`instance` intentionally**, add extension fields via `setProperty`, and document which fields belong to the API contract.
6. **Never expose sensitive data**; log/trace server-side per policy without duplicate logs.
7. **Check `@Order` and existing handlers:** ensure no catch-all advice swallows specific errors.
8. **Test all critical paths:** 200 success, 400 validation and malformed JSON, 404 resource, 409 conflict, 405 method, 401/403 when security is enabled.
9. **Use MockMvc for most MVC contract tests;** when real sockets/server/headers/container filters matter, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` with an HTTP client.
10. **Review CI reports:** assert not just body text, but status, `Content-Type`, `type`/`errorCode`, and `instance` when contracted.
11. **Check client compatibility:** changing status, `errorCode`, `type`, or JSON extensions can break clients. Plan versioning or migration when evolving contracts.

## 16. Self-Study Exercises

**Exercise 1.** Add `ProductDiscontinuedException`. For a discontinued product, would you choose HTTP 409 or 410 Gone? Explain based on a real contract, then add its `@ExceptionHandler`, `type`, and `errorCode`.

**Exercise 2.** When POST omits `quantity`, a record using primitive `int` receives `0`. How does `@Min(1)` detect it? If you need to distinguish "not sent" from "sent 0," how must you change the DTO type and constraints?  
*Hint:* Use `Integer` with `@NotNull` and `@Min(1)`, then test both cases.

**Exercise 3.** Suppose one `@ControllerAdvice` has a high-precedence `@ExceptionHandler(Exception.class)` and another advice handles `ProductNotFoundException` at lower precedence. Why must you check `@Order` so 404s do not turn into 500s?

**Exercise 4.** An HTTP 401 from a Spring Security filter lacks the JSON format of your MVC 404 errors. Can modifying `ApiErrorAdvice` alone guarantee it gets invoked?  
*Hint:* Not automatically; configure `AuthenticationEntryPoint`/`AccessDeniedHandler` and test with real security requests.

**Exercise 5.** Add tests for malformed JSON, missing `@RequestParam`, and unsupported HTTP methods. Identify the corresponding exceptions/framework handlers and assert only fields guaranteed to stay stable.

**Summary tip:** A production-grade API needs both **accurate business rules** and **explicit HTTP error contracts**. `@ControllerAdvice` centralizes handlers, `@ExceptionHandler` matches exact exceptions, and `ProblemDetail` provides a standard structure. Verify integration via MockMvc and add real-server tests where required so correctness goes beyond Java theory.

## 17. References

- [Spring Boot 3.3 — Servlet Web Applications: Error Handling](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html) — `/error` and `spring.mvc.problemdetails.enabled`.
- [Spring Framework — @ControllerAdvice and @RestControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html) — global advice scope, ordering, and local handlers.
- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html) — handler selection and return values.
- [Spring Framework — ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) — RFC 9457 and extension fields.
- [Spring Framework 6.1 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html) — customization hooks for MVC errors.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) — semantics of `type`/`title`/`status`/`detail`/`instance`.

**Remember:** In Spring MVC, **`@RestControllerAdvice + @ExceptionHandler`** is a clean way to map meaningful exceptions to RFC 9457 **`ProblemDetail`**. Spring Boot can handle many framework exceptions when enabled, yet domain errors and filter/security errors still require explicit policies. Tests must verify **HTTP status, media type, and JSON contract** together—never just check that Java threw an exception.