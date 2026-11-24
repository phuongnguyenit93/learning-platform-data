# HandlerExceptionResolver and the Exception Handling Chain in Spring MVC

## 1. Lesson Objectives

When a Spring MVC controller encounters an error, catching the exception is only part of turning the failure into an **HTTP response**. Spring MVC includes a central mechanism called **HandlerExceptionResolver** to translate exceptions raised while mapping or executing a handler into an HTTP response with appropriate status, headers, and body.

After this lesson, you will be able to:

1. Trace the flow from **DispatcherServlet** through **HandlerExceptionResolver** to an HTTP response or Servlet error dispatch.
2. Distinguish **ExceptionHandlerExceptionResolver**, **ResponseStatusExceptionResolver**, **DefaultHandlerExceptionResolver**, and custom resolvers.
3. Use **@ExceptionHandler** inside controllers and **@RestControllerAdvice** to standardize API errors.
4. Understand precedence across multiple resolvers, multiple advice beans, root exceptions, and nested causes.
5. Use **ProblemDetail**, **ResponseEntityExceptionHandler**, and consistent HTTP status codes.
6. Recognize that errors occurring in **Filters/Spring Security** or after the response is committed require separate handling.
7. Build a **Spring Boot 3.5, Java 17+** app and verify error behavior using `curl` or `MockMvc`.

The primary scope is **Spring MVC on the Servlet stack** (typically with embedded Tomcat). **Spring WebFlux** has its own exception handling mechanism and should not be conflated with MVC's `HandlerExceptionResolver`.

## 2. Where Do Exceptions Arise in the Spring MVC Flow?

A typical HTTP request passes through these layers:

~~~mermaid
flowchart TD
    A[HTTP client] --> B[Servlet Filter chain]
    B --> C[DispatcherServlet]
    C --> D[HandlerMapping and HandlerAdapter]
    D --> E[Controller]
    E --> F[Service / Repository]
    F --> G{Exception thrown?}
    G -->|No| H[HttpMessageConverter / View]
    G -->|Yes| I[HandlerExceptionResolver chain]
    I --> J{Resolved by a resolver?}
    J -->|Yes| K[Status / Headers / Body / View]
    J -->|No| L[Exception propagates to Servlet container]
    L --> M[Error dispatch /error if configured]
    H --> N[HTTP response]
    K --> N
    M --> N
~~~

In Spring MVC, when an exception occurs during **mapping or handler execution**, `DispatcherServlet` invokes the configured `HandlerExceptionResolver`s in order. Resolvers can handle it via an exception-handler method, attach an HTTP status, produce standard Spring MVC error handling, or return an error view.

**Three layers to distinguish:**

- **Controller/handler:** where the exception is thrown, e.g., product not found.
- **HandlerExceptionResolver:** Spring MVC's machinery for converting exceptions into HTTP responses.
- **Servlet container and Spring Boot `/error`:** the final fallback when an exception remains unresolved or the container performs an error dispatch.

If a resolver handles the exception, the request does not necessarily proceed to `/error`. Conversely, an HTTP 404/500 status and `/error` body do not prove an `@ExceptionHandler` ran.

## 3. The HandlerExceptionResolver Contract

The interface resides at **org.springframework.web.servlet.HandlerExceptionResolver** and conceptually defines:

~~~java
ModelAndView resolveException(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception exception);
~~~

This is an API signature for understanding behavior; it is not a standalone Java program. The **handler** argument may be `null`/unknown if the error happened before a handler was matched.

The return value determines how `DispatcherServlet` proceeds:

| Return value | Meaning | Next behavior |
|---|---|---|
| **null** | Resolver did not handle the exception | Passes to the next resolver |
| **new ModelAndView()** | Exception handled and no view rendering needed | Stops resolver chain; response may already be written / status set |
| **ModelAndView with view** | Exception handled and an error page should be rendered | `DispatcherServlet` renders the specified view |

**Note:** a resolver can directly populate the HTTP response and return an empty `ModelAndView`. Thus an empty `ModelAndView` does not imply the response has no body.

An exception is **unresolved** when every resolver returns `null` or cannot handle it. The exception can then propagate to the Servlet container; Spring Boot normally configures an error page pointing to **/error**.

## 4. Key HandlerExceptionResolvers

Spring MVC in a standard configuration registers default resolvers. In common flows, three core resolvers appear in order:

### 4.1. ExceptionHandlerExceptionResolver

This resolver locates methods annotated with **@ExceptionHandler**:

- First checks local **@ExceptionHandler** methods inside the applicable controller.
- If none match, inspects **@ControllerAdvice / @RestControllerAdvice** beans in scope.
- Selects a method by exception type, specificity, root/cause rules, advice ordering, and media type conditions.
- Invokes the method, then uses Spring MVC's return-value handling to build the body, status, headers, or view.

Example:

~~~java
@ExceptionHandler(IllegalArgumentException.class)
public ResponseEntity<String> invalid(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("Invalid input");
}
~~~

Place this inside a controller or advice class with the appropriate Spring imports. This is the most flexible approach when an API needs custom error formats and messages.

### 4.2. ResponseStatusExceptionResolver

This resolver handles statuses expressed via **@ResponseStatus** or **ResponseStatusException** under Spring MVC configuration.

Example defining an exception with status 404:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class DocumentNotFoundException extends RuntimeException {
    public DocumentNotFoundException(String id) {
        super("Document not found: " + id);
    }
}
~~~

This is a standalone class when placed in **DocumentNotFoundException.java** with the Spring Web dependency; it is not a runnable HTTP server by itself.

You can also throw **ResponseStatusException** at runtime:

~~~java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND, "Document not found");
~~~

**Important:** `@ResponseStatus`/`ResponseStatusException` expresses an HTTP status, not automatically a custom JSON body. When **reason** is set or `sendError` is used, the Servlet container may trigger an error dispatch. If you need a consistent structured API body, use `ProblemDetail` or an explicit exception handler.

### 4.3. DefaultHandlerExceptionResolver

This resolver maps many **Spring MVC infrastructure** exceptions to matching HTTP status codes:

| Common error | Typical HTTP status |
|---|---|
| **HttpRequestMethodNotSupportedException** | **405 Method Not Allowed** |
| **HttpMediaTypeNotSupportedException** | **415 Unsupported Media Type** |
| **HttpMediaTypeNotAcceptableException** | **406 Not Acceptable** |
| **MissingServletRequestParameterException** | **400 Bad Request** |
| **MethodArgumentTypeMismatchException** via type conversion failure | **400 Bad Request** |
| **HttpMessageNotReadableException** (malformed JSON body) | **400 Bad Request** |
| **NoHandlerFoundException** / **NoResourceFoundException** when thrown | **404 Not Found** |

Depending on the Spring Framework version, the exact exception list and body representation may vary; the table shows typical mappings.

**Do not** write a global handler catching all **Exception**s and always returning 500, because it can swallow 400/404/405/415 errors that default mechanisms handle properly.

### 4.4. SimpleMappingExceptionResolver

**SimpleMappingExceptionResolver** maps exception class names to **view** names (such as HTML error pages). It is useful in server-side rendered MVC apps and typically configured manually as needed. Modern REST APIs are generally better served by **@RestControllerAdvice** and `ResponseEntity`/`ProblemDetail`.

### 4.5. Custom Resolvers

You can register a bean implementing `HandlerExceptionResolver` when low-level handling logic is genuinely required. However, most APIs do not need this: **@ExceptionHandler**, **@RestControllerAdvice**, and **ResponseEntityExceptionHandler** are far more maintainable extension points.

A custom resolver should only handle exceptions it truly owns, return **null** for anything out of scope, respect committed-response rules, and avoid writing duplicate bodies alongside downstream resolvers.

## 5. Execution Order and Handler Selection

### 5.1. Resolver Ordering

In default Spring MVC, the core trio is tried in order:

~~~text
1. ExceptionHandlerExceptionResolver
       |
       | No matching @ExceptionHandler?
       v
2. ResponseStatusExceptionResolver
       |
       | Not handled by @ResponseStatus / ResponseStatusException?
       v
3. DefaultHandlerExceptionResolver
       |
       | Still unresolved?
       v
4. Servlet container / error dispatch
~~~

This is the **common standard order**, not an immutable structure in every app. Custom beans with **order** can shift precedence, and resolvers can be grouped inside a **HandlerExceptionResolverComposite**. In Spring, **lower order values have higher priority**; the first resolver returning a handled result stops the chain.

### 5.2. Local @ExceptionHandler vs. Global Advice

When a controller defines a matching **@ExceptionHandler** method, it usually takes precedence over a global method in **@ControllerAdvice**. For instance, a specific controller can return a custom HTML error page while application-wide advice returns JSON for APIs.

Use **@RestControllerAdvice** when the response body is written directly as JSON or `ProblemDetail`. It is functionally equivalent to **@ControllerAdvice + @ResponseBody** for handler methods declared in the advice.

When scoping to a specific group of controllers, narrow the target:

~~~java
@RestControllerAdvice(basePackages = "com.example.catalog.api")
public class CatalogErrorAdvice {
    // @ExceptionHandler methods apply only to matching controllers.
}
~~~

This is an annotation illustration, not a standalone runnable application.

### 5.3. Multiple @ControllerAdvice Beans: @Order and Exception Types

With multiple advice classes, use **@Order** or **Ordered** to declare priority. A higher-priority advice can match a **nested cause** before a lower-priority advice matches the **root exception**.

Within a single advice, a root match takes precedence over a cause match according to exception depth. Across multiple advice beans, however, **advice order** can beat root-vs-cause specificity between two different advices.

Example:

~~~java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class BusinessErrorAdvice {
    // Handles specific business errors.
}
~~~

Required imports: **org.springframework.core.Ordered**, **org.springframework.core.annotation.Order**, and **org.springframework.web.bind.annotation.RestControllerAdvice**.

Avoid registering multiple `@ExceptionHandler`s competing for the same exception type in the same advice under the same media type conditions. Spring can reject ambiguous mappings and fail to initialize the resolver properly.

### 5.4. Exceptions in the Cause Chain

Suppose a service throws **new IllegalStateException("wrapper", new IOException("disk"))**. A handler targeting **IOException** can match the nested cause; Spring Framework supports inspecting causes across multiple levels.

Whether the handler receives the root or cause object as its parameter depends on how the parameter is declared. Declare exception parameters as specifically as possible. Never funnel every failure into **@ExceptionHandler(Exception.class)** and classify by message strings; define clear, typed business exceptions instead.

An `@ExceptionHandler` can **rethrow the original exception** to opt out of handling and let the resolver chain continue. Do not treat throwing an arbitrary new exception as a safe way to delegate onward.

## 6. Producing Standardized HTTP Error Responses

An error response has at least three parts:

1. **HTTP status**: 400 for invalid input, 404 for missing resource, 409 for conflict, 500 for unexpected failure.
2. **Headers**: `Content-Type`, and where appropriate special headers like `Allow` or `Retry-After`.
3. **Body**: machine-readable details following a consistent API contract.

### 6.1. ProblemDetail per RFC 9457

Modern Spring Framework supports **ProblemDetail**, a standard representation for HTTP API problem details:

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Product 42 was not found",
  "instance": "/api/products/42",
  "errorCode": "PRODUCT_NOT_FOUND"
}
~~~

Common standard fields: **type**, **title**, **status**, **detail**, and **instance**. **errorCode** is an application extension property, not a mandatory RFC field.

When a handler returns **ProblemDetail**, Spring uses **status** to set the HTTP status, prefers **application/problem+json** for JSON, and can populate **instance** from the current request path if unset.

### 6.2. ErrorResponse and ResponseEntityExceptionHandler

**ErrorResponse** is Spring's contract describing HTTP status, headers, and `ProblemDetail`. Several Spring MVC infrastructure exceptions implement `ErrorResponse`.

**ResponseEntityExceptionHandler** is a convenient base class for **@ControllerAdvice**. It provides built-in handlers for standard errors like unreadable bodies, validation failures, wrong HTTP methods, or unsupported media types, with overridable hooks for customization.

Spring Boot 3.5 can auto-configure RFC 9457 handling when enabled:

~~~yaml
spring:
  mvc:
    problemdetails:
      enabled: true
~~~

When enabled, Boot can register a default advice/handler for built-in MVC exceptions; if you also want custom handling for those same exceptions, control your advice's **@Order** relative to the default handler. For domain/business errors, a dedicated **@RestControllerAdvice** with specific handlers is usually enough.

**Avoid creating two overlapping error layers**: both enabling Boot problem details and extending `ResponseEntityExceptionHandler` to override everything without checking order. That can cause bodies and statuses to shift depending on which advice wins.

### 6.3. Distinguish sendError from setStatus

**response.setStatus(404)** merely sets the response status code. **response.sendError(404)** signals an error to the Servlet container and can trigger an error page or error dispatch. When an error dispatch occurs, Spring Boot may route the request to **/error**.

This explains why two endpoints both returning status 404 can return different bodies. Never guess which resolver ran based on status alone; inspect logs, breakpoints, or HTTP body and headers.

## 7. Runnable Spring Boot MVC Example

This example uses **Java 17**, **Spring Boot 3.5.0**, **Maven**, and **embedded Tomcat**. It demonstrates a business exception handled by `@ExceptionHandler`, MVC errors handled by built-in `ProblemDetail` support, and a normal controller response.

### 7.1. Project Structure

~~~text
exception-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/exceptiondemo/
    │   │   ├── ExceptionDemoApplication.java
    │   │   ├── ProductController.java
    │   │   ├── ProductNotFoundException.java
    │   │   └── ApiExceptionHandler.java
    │   └── resources/application.yml
    └── test/java/com/example/exceptiondemo/
        └── ProductApiTest.java
~~~

### 7.2. Maven pom.xml

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>exception-demo</artifactId>
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

This is the POM for a complete application. Starter test supplies JUnit Jupiter, Spring Test utilities, and `MockMvc` matching Boot 3.5.

### 7.3. Main Class

**ExceptionDemoApplication.java**

~~~java
package com.example.exceptiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionDemoApplication.class, args);
    }
}
~~~

### 7.4. Controller and Business Exceptions

**ProductNotFoundException.java**

~~~java
package com.example.exceptiondemo;

public class ProductNotFoundException extends RuntimeException {
    private final long id;

    public ProductNotFoundException(long id) {
        super("Product " + id + " was not found");
        this.id = id;
    }

    public long getId() {
        return id;
    }
}
~~~

**ProductController.java**

~~~java
package com.example.exceptiondemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{id}")
    public Product find(@PathVariable long id) {
        if (id != 7) {
            throw new ProductNotFoundException(id);
        }
        return new Product(7, "Pen");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Product create(@RequestBody NewProduct request) {
        if (request.name() == null || request.name().isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        return new Product(8, request.name().trim());
    }

    public record Product(long id, String name) {
    }

    public record NewProduct(String name) {
    }
}
~~~

Explanation:

- **GET /api/products/7** returns a valid `Product`.
- **GET /api/products/42** throws `ProductNotFoundException`.
- **POST /api/products** with a blank name throws `IllegalArgumentException`.
- **GET /api/products/not-a-number** fails when converting the path variable to `long`; this is a binding/mapping exception inside Spring MVC, not from an `if` branch in the controller.

### 7.5. Global Handler Using ProblemDetail

**ApiExceptionHandler.java**

~~~java
package com.example.exceptiondemo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail productMissing(ProductNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
        problem.setTitle("Product not found");
        problem.setProperty("errorCode", "PRODUCT_NOT_FOUND");
        return problem;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidInput(IllegalArgumentException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
        problem.setTitle("Invalid request");
        problem.setProperty("errorCode", "INVALID_PRODUCT");
        return problem;
    }
}
~~~

Both handlers cover only **well-defined business exceptions**. Do not add a default `@ExceptionHandler(Exception.class)` returning 500 because it can shadow infrastructure exception handling.

In production services, never blindly expose `ex.getMessage()` for arbitrary exceptions. Use controlled messages only, avoiding stack traces, SQL queries, secrets, or internal paths. For unexpected errors, log with a correlation ID and return a generic message.

### 7.6. Enabling Standard Error Handling

**application.yml**

~~~yaml
server:
  port: 8080

spring:
  mvc:
    problemdetails:
      enabled: true

server.error.include-message: never
~~~

This snippet is valid YAML: **server.error.include-message** is a dotted root-level property key, which Spring Boot binds cleanly. For readability, **error.include-message** can also be nested under **server**, provided there are no duplicate keys. This setting restricts exposing uncontrolled default error messages in error responses routed through Boot's `/error`.

### 7.7. Running the Application

Requires JDK 17+ and Maven. In the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Or package it:

~~~bash
mvn clean package
java -jar target/exception-demo-1.0.0.jar
~~~

**Testing a successful request**

~~~bash
curl -i http://localhost:8080/api/products/7
~~~

Expected status: **HTTP 200**. Expected JSON body:

~~~json
{"id":7,"name":"Pen"}
~~~

**Testing product not found**

~~~bash
curl -i http://localhost:8080/api/products/42
~~~

Expected status: **HTTP 404**; `Content-Type` is typically **application/problem+json**. Body includes these fields (**instance** is populated by Spring from the request path):

~~~json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Product 42 was not found",
  "instance": "/api/products/42",
  "errorCode": "PRODUCT_NOT_FOUND"
}
~~~

JSON key ordering is insignificant and may vary. Verify HTTP status, `Content-Type`, and individual field values.

**Testing binding failure**

~~~bash
curl -i http://localhost:8080/api/products/not-a-number
~~~

Expected status: **HTTP 400**. With Problem Details enabled, the response can be **application/problem+json** handled by MVC/Boot. This error happens when Spring tries to convert the string into a number, before entering the controller body. It must not return 500 because it is an input error.

**Testing unsupported HTTP method**

~~~bash
curl -i http://localhost:8080/api/products
~~~

In this example **/api/products** only has a `POST` handler. Sending `GET` to that path typically returns **HTTP 405 Method Not Allowed**, possibly with an **Allow** header listing supported methods.

**Testing POST with valid data**

On Bash:

~~~bash
curl -i -H 'Content-Type: application/json' \
  -d '{"name":"Book"}' \
  http://localhost:8080/api/products
~~~

Expected status: **HTTP 200** (because the controller returns `Product` directly without `@ResponseStatus(CREATED)`). Body:

~~~json
{"id":8,"name":"Book"}
~~~

To return `201 Created` in a real resource-creation API, use **ResponseEntity.created(location).body(product)**, construct a proper `Location` URI, and ensure the resource was persisted.

**Testing POST with invalid name**

~~~bash
curl -i -H 'Content-Type: application/json' \
  -d '{"name":"  "}' \
  http://localhost:8080/api/products
~~~

Expected status **HTTP 400**; `ProblemDetail` contains **errorCode=INVALID_PRODUCT**.

**Testing malformed JSON**

~~~bash
curl -i -H 'Content-Type: application/json' \
  --data-binary '{"name":' \
  http://localhost:8080/api/products
~~~

Expected status: **HTTP 400** because the JSON body cannot be parsed. Infrastructure handles **HttpMessageNotReadableException** before the controller is invoked.

The multi-line `curl` commands above use Bash syntax. On Windows PowerShell, use **curl.exe** and a UTF-8 payload file to avoid quote-escaping pitfalls.

## 8. Automated Testing with MockMvc

**ProductApiTest.java**

~~~java
package com.example.exceptiondemo;

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
class ProductApiTest {

    @Autowired
    MockMvc mvc;

    @Test
    void found() throws Exception {
        mvc.perform(get("/api/products/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("Pen"));
    }

    @Test
    void missingProductIsProblemDetail() throws Exception {
        mvc.perform(get("/api/products/42"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.errorCode").value("PRODUCT_NOT_FOUND"))
            .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void typeMismatchIsClientError() throws Exception {
        mvc.perform(get("/api/products/not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidNameIsClientError() throws Exception {
        mvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"   \"}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.errorCode").value("INVALID_PRODUCT"));
    }

    @Test
    void unsupportedMethodIs405() throws Exception {
        mvc.perform(get("/api/products"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

When all tests pass, Maven Surefire exits cleanly with zero test failures. Summary log formatting depends on the Maven plugin; this guide does not assume fixed stdout text.

Key testing principles:

- Error tests should assert **HTTP status**, **media type**, and **errorCode** fields, not merely that an exception was thrown.
- **MockMvc** runs the Spring MVC pipeline inside a test environment without opening a real HTTP socket. To test Servlet container error dispatches, connectors, and reverse proxies, add integration tests with an embedded server on a real port or deployment-environment tests.
- Do not assert that every Boot error response shares the exact same body without checking **spring.mvc.problemdetails.enabled** and registered advice beans.

## 9. When Should You Extend ResponseEntityExceptionHandler?

If an API needs a unified error format across both business exceptions and **Spring MVC framework** errors like malformed JSON, validation, or type mismatch, you can create an advice extending **ResponseEntityExceptionHandler**.

The following example **should not be installed alongside another default handler without designing order**, to avoid competing handlers:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@ControllerAdvice
public class JsonErrorAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, "Malformed JSON request");
        problem.setTitle("Invalid JSON");
        return handleExceptionInternal(ex, problem, headers, status, request);
    }
}
~~~

This snippet belongs in an application package with the proper dependencies. If Boot's problem details are already enabled, consider creating a dedicated **@RestControllerAdvice** with specific `@ExceptionHandler`s and higher **@Order** precedence over Boot's handler only where customization is actually required. Avoid mixing multiple strategies out of habit.

The advantage of extending the base class is inheriting built-in handling for many infrastructure exceptions and overriding specific hooks. The downside is easily colliding with existing advice if the architecture is inconsistent.

## 10. Limitations of HandlerExceptionResolver

### 10.1. Exceptions in Servlet Filters and Spring Security

An exception thrown inside a **Filter before `DispatcherServlet` is invoked** does not automatically pass through Spring MVC's `HandlerExceptionResolver` chain. For instance, Spring Security authentication/authorization errors are normally handled in the filter chain via **ExceptionTranslationFilter**, **AuthenticationEntryPoint**, or **AccessDeniedHandler**.

Therefore, a `@RestControllerAdvice` handling **AccessDeniedException** is not guaranteed to intercept every 401/403 from Spring Security.

To reuse an error format between filters and MVC, explicitly design an integration point or use the corresponding security handlers. Never catch every exception in a filter and return status 200 with error JSON.

### 10.2. Non-Existent Endpoints and Static Resources

When a URL matches no controller, Spring MVC can throw **NoHandlerFoundException** if configured to raise exceptions. However, in Boot apps, static resource mappings may claim unmatched paths first; if no static file exists, **NoResourceFoundException** may be thrown instead. Other setups route to **/error**.

Thus, **there is no guarantee** that `@ExceptionHandler(NoHandlerFoundException.class)` catches every 404. Test specifically against your static resource config, Boot version, and actual routes.

### 10.3. Response Already Committed

If response headers or body have already been flushed/committed, the server cannot change the status or write a fresh error body. When streaming responses, sending large files, or failing after partial output has already gone out, resolvers can no longer build a clean JSON error response.

Never attempt to write a second error body into a committed response. Check logs, metrics, connections, and design protocol-appropriate streaming error handling.

### 10.4. Async and Exceptions on Other Threads

With asynchronous requests or work offloaded to separate threads, exceptions can be routed back into Servlet async dispatch depending on the integration. However, an exception thrown inside an unmanaged background task outside the request lifecycle **does not automatically** reach `@ExceptionHandler`.

Use `Future`/`CompletableFuture` or properly managed async mechanisms, capture task failures, and design explicit error propagation rather than expecting `DispatcherServlet` to catch everything.

### 10.5. WebFlux Uses a Different Mechanism

In WebFlux, error handling relies on reactive abstractions such as **WebExceptionHandler**, **ErrorWebExceptionHandler**, and `@ExceptionHandler` in reactive controllers. Do not implement **org.springframework.web.servlet.HandlerExceptionResolver** expecting it to work on Reactor Netty/WebFlux.

## 11. Operations and Practical Error Triage

| Symptom | Common cause | What to check |
|---|---|---|
| API returns HTML instead of JSON | Container error page or Boot `/error` renders HTML based on `Accept` | Check `Accept`, `Content-Type`, `/error`, and problem details config |
| Business error becomes 500 | Missing matching `@ExceptionHandler`; wrapped exception mismatch | Check root/cause types, package scan, advice scope |
| 400/405 errors turn into 500 | Catch-all handler swallows infrastructure exceptions | Remove overly broad handlers, preserve Spring defaults |
| Exception handler never runs | Exception thrown in a Filter or before `DispatcherServlet` | Check Servlet Filter chain and Spring Security |
| Wrong handler called among multiple advices | Competing `@Order`, media type conditions, or exception mappings | Check order, selectors, and mappings across advices |
| A 404 bypasses `NoHandlerFoundException` | Static resource handler or Boot error dispatch | Check `NoResourceFoundException` and `/error` mapping |
| Duplicate error logs or double-written body | Multi-layer logging, response already committed | Log only at appropriate boundaries and check `isCommitted` |
| Sensitive details leaked | Returning raw `ex.getMessage()` of internal errors | Map safe messages, never return SQL/stack traces |
| API body changes across environments | ProblemDetail toggle or different Boot versions | Check properties, dependencies, and integration tests |

### Logging and Observability

- For expected **4xx** errors, log useful context at an appropriate level without creating noise or logging sensitive data.
- For unexpected **5xx** errors, log the exception and correlation/request ID at the handling boundary. Avoid logging the same stack trace multiple times across controller, service, and filter.
- Track metrics by status, endpoint, and error type; monitor 4xx/5xx rates, latency, and spikes.
- Keep the response contract stable: HTTP codes and **errorCode** for clients, internal details in logs.
- Never include internal class names, SQL, access tokens, passwords, or stack traces inside external `ProblemDetail` payloads.

## 12. Design Principles for the Exception Handling Chain

1. **Define meaningful business exceptions**, e.g., `ProductNotFoundException`, `DuplicateOrderException`, `InsufficientBalanceException`.
2. **Map accurately to HTTP statuses** with targeted handlers. Avoid a catch-all returning one status for everything.
3. **Use `ProblemDetail` or consistent DTOs** for REST APIs; distinguish recoverable client errors from system failures.
4. **Preserve Spring MVC infrastructure handlers** for framework errors unless there is a deliberate reason to override.
5. **Control `@Order`**, advice scope, and root/cause matching when multiple advices exist.
6. **Do not use exceptions for normal business branching** when an explicit return type fits better.
7. **Keep filter/security errors separate from MVC** so authentication and authorization are handled properly.
8. **Respect commit/async lifecycles**, avoiding writing bodies after output has started.
9. **Test status, headers, body, and safe messaging** in both `MockMvc` and real HTTP environments.
10. **Maintain API documentation** so clients know what 400, 404, 409, 422, 500, or 503 mean for each operation.

## 13. Official Documentation

1. Spring Framework – Exception Resolvers in DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
2. Spring Framework – `@ExceptionHandler`, Root/Cause, and Multiple Advice: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
3. Spring Framework – `@ControllerAdvice` and `@RestControllerAdvice`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html
4. Spring Framework – Error Responses, `ProblemDetail`, and `ResponseEntityExceptionHandler`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
5. Spring Boot 3.5 – Servlet Web Applications, Error Handling: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
6. Spring Boot 3.5 – Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
7. RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457

**Conclusion:** `HandlerExceptionResolver` is the error-resolution chain at the **DispatcherServlet** layer, where `ExceptionHandlerExceptionResolver` handles `@ExceptionHandler`, `ResponseStatusExceptionResolver` handles status-annotated exceptions, and `DefaultHandlerExceptionResolver` handles MVC infrastructure errors. Spring Boot adds the Servlet container **/error** mechanism. Good design picks the right resolver/advice, sets accurate statuses, returns standardized bodies, protects sensitive details, and tests real failure paths.