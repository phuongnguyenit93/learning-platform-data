# ProblemDetail, ErrorResponse, and RFC 9457 Error Formatting in Spring MVC

## 1. The Problem: Why Does a REST API Need a Unified Error Contract?

A successful API may return clean JSON DTOs yet return inconsistent error shapes:

```json
{"error":"not_found"}
```

```json
{"message":"Cannot find order","timestamp":"2026-10-21T10:00:00Z"}
```

```json
{"success":false,"data":null,"code":404}
```

Clients must write multiple handling branches and do not know which information is meant for machines versus human explanation. Returning HTTP `200 OK` while placing `"code":404` inside the body also breaks HTTP semantics: caches, monitoring, and HTTP clients may treat it as success.

**RFC 9457 — Problem Details for HTTP APIs** (published July 2023, obsoleting RFC 7807) defines a machine-readable error representation based on HTTP status and standard fields. Spring Framework 6.x supports it directly via:

- `org.springframework.http.ProblemDetail` — object representing a problem.
- `org.springframework.web.ErrorResponse` — contract for exceptions to describe status, headers, and `ProblemDetail`.
- `org.springframework.web.ErrorResponseException` — convenient base exception class implementing `ErrorResponse`.
- `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` — base class for `@ControllerAdvice` to convert common Spring MVC errors into error responses.

This lesson focuses on **Spring Web MVC (Servlet stack)**, not Spring WebFlux. The examples pin **Java 17, Spring Boot 3.3.5, and Spring Framework 6.1.x**, avoiding accidentally relying on extension points introduced only in newer versions.

Learning objectives:

1. Understand the RFC 9457 standard, its fields, and the `application/problem+json` media type.
2. Know when to use `ProblemDetail`, `ErrorResponse`, and `ErrorResponseException`.
3. Handle business errors, validation errors, and common MVC errors in one consistent shape.
4. Use `@RestControllerAdvice` / `ResponseEntityExceptionHandler` with proper scope without losing HTTP statuses.
5. Design extensions like `code`, `errors`, and `traceId` safely, stably, and ready for internationalization and testing.
6. Recognize limits: not every exception, filter, security response, or streaming error automatically becomes a Problem Detail.

## 2. Reading an RFC 9457 Response

Example of a client querying a non-existent order:

```http
GET /api/orders/999 HTTP/1.1
Host: localhost:8080
Accept: application/problem+json, application/json
```

Response under the illustrative contract:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 999",
  "instance": "/api/orders/999",
  "code": "ORDER_NOT_FOUND"
}
```

Standard fields:

| Field | JSON type | Meaning to remember |
| --- | --- | --- |
| `type` | URI string | Identifies the **problem type**: the same error type should use the same stable URI |
| `title` | String | Short, human-readable summary of the **error type**; should not change per occurrence except for language |
| `status` | Number | HTTP status code for the occurrence when the problem is created; **the actual HTTP status remains the primary protocol signal** |
| `detail` | String | Specific explanation for **this occurrence**, helping the client/user understand |
| `instance` | URI string | Identifies the **specific occurrence**; typically the request path or a system-assigned URI |

RFC 9457 does not require every JSON problem to contain all five fields in all cases. `type` defaults to `about:blank` when omitted; `status` is most useful when it matches the HTTP response status; `title` may default from the HTTP reason phrase with `about:blank`. Fields like `detail` and `instance` may be absent if not provided.

**`type` vs. `instance`:** `type` indicates *what kind* of error occurred (e.g., product not found), whereas `instance` indicates *which occurrence* (e.g., request `/api/orders/999`). For the URI `https://api.example.com/problems/order-not-found`, the domain `example.com` is **illustrative only**; in real systems use a URI controlled by your organization, kept stable, and ideally backed by a documentation page explaining how to resolve it.

### Extension Members Beyond Standard Fields

`code` in the JSON above is an application **extension**. The RFC allows adding custom name/value pairs specific to a problem type, for example:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Invalid request",
  "status": 400,
  "detail": "Some submitted fields are invalid",
  "errors": [
    {"field":"quantity","message":"must be greater than or equal to 1"},
    {"field":"sku","message":"must not be blank"}
  ]
}
```

Here `errors` is also an extension, not an official mandatory validation schema from the RFC. Whenever clients are expected to rely on `code` or `errors`, the server must document their types, semantics, and stability. For errors on nested JSON objects, you can use **JSON Pointer** paths such as `"/customer/address/postalCode"` instead of a bare field name that cannot distinguish nested locations.

### Media Type and HTTP Status

- Standard JSON representation uses **`application/problem+json`**.
- The RFC also defines an XML representation `application/problem+xml` when using XML, but Spring Boot Web by default does not necessarily include an XML converter; do not promise XML just because the RFC defines it.
- For `400`, `404`, `409`, `422`, `500`, the **actual status line/headers** must never contradict the body `status`.
- Do not turn every error into `200` just to make frontend parsing easier. API clients should inspect the status first before reading the body.
- `Problem Details` is typically used for 4xx/5xx errors, though the RFC does not mechanically restrict it strictly to those codes. Do not use it to replace normal success representations.

## 3. Spring's Three Abstractions: Relationships and Choices

### 3.1. ProblemDetail Is the Data of an Error

`ProblemDetail` is not an exception. It is a data object holding RFC fields, with factories and setters:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND, "No order exists with id 999");
problem.setType(URI.create(
        "https://api.example.com/problems/order-not-found"));
problem.setTitle("Order not found");
problem.setInstance(URI.create("/api/orders/999"));
problem.setProperty("code", "ORDER_NOT_FOUND");
```

This is a Java snippet requiring `java.net.URI`, `org.springframework.http.HttpStatus`, and `org.springframework.http.ProblemDetail`. When returned from an `@ExceptionHandler` in MVC, Spring knows how to render it and set the matching HTTP status from `ProblemDetail.status`. If `instance` is unset, Spring MVC can populate the request path when rendering `ProblemDetail`.

`ProblemDetail.forStatus(HttpStatus.BAD_REQUEST)` creates an error with only the status and defaults. `ProblemDetail.forStatusAndDetail(...)` is convenient when you have a concise message for the client. Note that `detail` is **not** a place to dump raw `exception.getMessage()` from a database, stack traces, tokens, or SQL statements.

#### Dynamic Properties in JSON

`problem.setProperty("code", "ORDER_NOT_FOUND")` stores the extension inside a `Map` on `ProblemDetail`. When using Jackson with Spring MVC, `ProblemDetailJacksonMixin` promotes extensions to **top-level JSON** like `"code"`, rather than nesting `"properties":{"code":...}`. Avoid extension names that collide with standard fields (`type`, `title`, `status`, `detail`, `instance`), as that causes ambiguity.

### 3.2. ErrorResponse Is a Contract for Exceptions Carrying HTTP Info

`ErrorResponse` is an interface in `org.springframework.web` that lets Spring treat an exception as a structured HTTP response. Core members:

```java
HttpStatusCode getStatusCode();
HttpHeaders getHeaders();
ProblemDetail getBody();
```

These signatures are condensed for explanation, not a standalone interface file with full imports. The interface also provides utilities and message codes to support internationalization.

Many Spring MVC exceptions, such as argument/validation or media type errors, implement `ErrorResponse` and can be converted to `ProblemDetail` through MVC's exception handling system. That **does not mean** throwing any `RuntimeException` automatically yields a safe RFC message; arbitrary exceptions still need a mapping policy.

### 3.3. ErrorResponseException Is a Way to Throw Errors Explicitly

`ErrorResponseException` (Spring Framework 6.0+) is a `RuntimeException` implementing `ErrorResponse`. Example:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "This order cannot be placed while the product is locked.");
problem.setType(URI.create(
        "https://api.example.com/problems/product-locked"));
problem.setTitle("Product locked");
problem.setProperty("code", "PRODUCT_LOCKED");

throw new ErrorResponseException(HttpStatus.CONFLICT, problem, null);
```

This is a **snippet** inside a method, not a `main` program. The exception already carries `409 Conflict` and the problem body. With an active `ResponseEntityExceptionHandler`, this exception is rendered according to the RFC. The constructor accepting `status, ProblemDetail, cause` is available in Spring 6.1.

Do not use `ErrorResponseException` indiscriminately for every error: if you want clear domain exceptions, declare `OrderNotFoundException` and map it in `@ExceptionHandler`; both approaches are valid depending on design.

### 3.4. ResponseEntityExceptionHandler Is the Reusable Base

`ResponseEntityExceptionHandler` provides methods handling many exceptions produced by Spring MVC. A subclass uses `@ControllerAdvice` or `@RestControllerAdvice` to:

- Keep consistent handling for `400`, `405`, `406`, `415`, and other MVC errors.
- Override specific handlers, such as `handleMethodArgumentNotValid`, to add `errors`.
- Build custom `ProblemDetail` bodies and adjust `ResponseEntity` construction logic.
- Integrate `MessageSource` to resolve messages by locale.

For Spring MVC 6.1, this is the proper base class for standardizing framework-originated errors. Do not treat it as "catching every `Exception` indiscriminately": it does not catch custom business errors unless you provide matching handlers/types; errors occurring **outside `DispatcherServlet`** (such as parts of the Spring Security filter chain) also follow separate handling paths.

## 4. How Errors Flow Through Spring MVC

```text
HTTP request
    |
    v
DispatcherServlet / HandlerMapping
    |
    v
Handler method / argument resolution / validation
    |
    +---- success ---------------------> controller response
    |
    +---- error: exception
                  |
                  v
        HandlerExceptionResolver chain
                  |
          +-------+--------------------------+
          |                                  |
   @ExceptionHandler in controller     @ControllerAdvice
          |                            / ResponseEntityExceptionHandler
          |                                  |
          +--------------+-------------------+
                         |
                         v
                 ProblemDetail / ResponseEntity
                         |
                         v
                   HttpMessageConverter
                         |
                         v
             HTTP 4xx/5xx + application/problem+json
```

The diagram above is a high-level model. Spring resolvers are ordered; controller `@ExceptionHandler`s and advices have matching/order rules. An overly broad `@ControllerAdvice` or duplicate handlers can cause an exception to be resolved differently than expected. Once the response is committed, the framework may no longer be able to change its status or body.

| Error source | Example | Typical status | Handling |
| --- | --- | --- | --- |
| Syntactically invalid JSON body | `{"sku":` | `400` | `HttpMessageNotReadableException` |
| Bean Validation failure | `quantity=0` with `@Min(1)` | `400` | `MethodArgumentNotValidException` for `@Valid @RequestBody` |
| Unsupported route/method | `PUT` on a `POST`-only endpoint | `405` | `HttpRequestMethodNotSupportedException` |
| Unsupported request media type | `text/plain` sent to JSON endpoint | `415` | `HttpMediaTypeNotSupportedException` |
| Client rejects output format | `Accept: application/xml` when only JSON is returned | `406` | `HttpMediaTypeNotAcceptableException` |
| Business resource missing | Non-existent order id | `404` | Custom exception + `@ExceptionHandler` |
| Business state conflict | Product is locked | `409` | `ErrorResponseException`/domain mapping |
| Unexpected system error | DB timeout, NPE | `500` | Internal logging; safe body, no stack trace leaked |

**Note:** the exact status can be affected by annotations, custom exception handlers, and configuration. For instance, `422 Unprocessable Content` is sometimes used by APIs for validation instead of `400`; pick the semantics fitting your contract and stay consistent. Do not assume `@Valid` always returns `422` or every controller always returns RFC JSON without configuration.

### Spring Boot 3.3 and Opting into Problem Details

In Spring Boot 3.3, the property:

```properties
spring.mvc.problemdetails.enabled=true
```

enables auto-configuration to handle supported MVC errors as problem details. **The default value of this property in Boot 3.3 is `false`**; do not assume Boot enables it automatically just because the project has `spring-boot-starter-web`.

There are two common implementation approaches:

- **Approach A:** enable the property above and add another advice for business exceptions, paying attention to advice ordering when customizing built-in errors.
- **Approach B:** create your own `@RestControllerAdvice extends ResponseEntityExceptionHandler` to handle MVC errors and custom errors centrally.

**The runnable example in section 5 uses Approach B**, so **do not enable** that property in `application.properties`. Avoid registering multiple beans handling the same group of errors at the same precedence and assuming they will coordinate automatically; define a single owner for your error policy and test it.

## 5. Complete Example: Java 17 + Spring MVC + RFC 9457

Demo order-processing application:

- `POST /api/orders` with JSON `{"sku":"BOOK-1","quantity":2}` returns `201 Created`.
- `sku="MISSING"` throws custom `ProductNotFoundException`, mapped to `404` and code `PRODUCT_NOT_FOUND`.
- `sku="LOCKED"` throws `ErrorResponseException`, returning `409` and code `PRODUCT_LOCKED`.
- `quantity=0` or `sku=""` triggers Bean Validation `400`, returning extension `errors`.
- Malformed JSON triggers a converter error, handled by the base handler as an RFC response.

There is no database, authentication, transactions, or persistence; errors are **controlled simulations** to make the HTTP lifecycle clear.

### 5.1. Maven Structure

```text
problem-details-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/problems/
    │       ├── ProblemDetailsApplication.java
    │       ├── OrderController.java
    │       ├── ProductNotFoundException.java
    │       └── ApiErrorAdvice.java
    └── test/
        └── java/demo/problems/
            └── ApiErrorContractTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>problem-details-demo</artifactId>
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
```

**`src/main/java/demo/problems/ProblemDetailsApplication.java`**

```java
package demo.problems;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProblemDetailsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProblemDetailsApplication.class, args);
    }
}
```

### 5.2. Domain Exception Decoupled from HTTP

**`ProductNotFoundException.java`**

```java
package demo.problems;

public class ProductNotFoundException extends RuntimeException {
    private final String sku;

    public ProductNotFoundException(String sku) {
        super("Product not found");
        this.sku = sku;
    }

    public String getSku() {
        return sku;
    }
}
```

This exception knows nothing about HTTP statuses or JSON schemas. `ApiErrorAdvice` decides that when it crosses the REST boundary, status `404` and a specific problem type are used. In applications with multiple transports (REST, batch jobs, messaging), keeping domain exceptions decoupled from Spring Web helps reusability.

### 5.3. Controller Producing Success and Two Kinds of Business Errors

**`OrderController.java`**

```java
package demo.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.ErrorResponseException;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record CreateOrderRequest(
            @NotBlank String sku,
            @Min(1) int quantity) {}

    public record OrderReceipt(long orderId, String sku, int quantity) {}

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderRequest input) {

        if ("MISSING".equals(input.sku())) {
            throw new ProductNotFoundException(input.sku());
        }

        if ("LOCKED".equals(input.sku())) {
            ProblemDetail body = ProblemDetail.forStatusAndDetail(
                    HttpStatus.CONFLICT,
                    "This product cannot be ordered while locked.");
            body.setType(URI.create(
                    "https://api.example.com/problems/product-locked"));
            body.setTitle("Product locked");
            body.setProperty("code", "PRODUCT_LOCKED");
            throw new ErrorResponseException(
                    HttpStatus.CONFLICT, body, null);
        }

        OrderReceipt receipt = new OrderReceipt(
                1001L, input.sku(), input.quantity());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }
}
```

- `@Valid @RequestBody`: the JSON converter reads the request into the record, then validation checks constraints.
- `@Min(1)` on `int quantity`: `0` is invalid, though an **absent field** can become `0` due to the primitive default; in a real API, distinguish missing vs. zero if the contract cares (use `Integer` + `@NotNull`).
- The `MISSING` and `LOCKED` branches simulate states for testing. In production, check ownership, existence, and state in the service/database layer.
- `ResponseEntity<OrderReceipt>` in the success branch does not use the RFC error schema; the response is a normal JSON DTO.
- `ErrorResponseException` is constructed only when a clear HTTP `409` condition arises. It should not contain sensitive internal information.

### 5.4. Advice: Custom 404 and errors Extension for Bean Validation

**`ApiErrorAdvice.java`**

```java
package demo.problems;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail notFound(
            ProductNotFoundException exception,
            HttpServletRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Requested product was not found.");
        problem.setType(URI.create(
                "https://api.example.com/problems/product-not-found"));
        problem.setTitle("Product not found");
        problem.setInstance(URI.create(request.getRequestURI()));
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        return problem;
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                status, "One or more request fields are invalid.");
        problem.setType(URI.create(
                "https://api.example.com/problems/invalid-request"));
        problem.setTitle("Invalid request");
        problem.setProperty("code", "INVALID_REQUEST");

        List<Map<String, String>> errors = exception
                .getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> Map.of(
                        "field", error.getField(),
                        "message", Objects.toString(
                                error.getDefaultMessage(), "Invalid value")))
                .sorted(Comparator.comparing(item -> item.get("field")))
                .toList();

        problem.setProperty("errors", errors);

        return handleExceptionInternal(
                exception, problem, headers, status, request);
    }
}
```

**Explanation of each decision:**

- `@RestControllerAdvice` makes `@ExceptionHandler` methods return JSON bodies; extending `ResponseEntityExceptionHandler` handles framework errors.
- `notFound` is called for the custom business exception and returns `ProblemDetail`. Spring MVC uses `problem.status=404` as the HTTP status and prefers `application/problem+json` for JSON problem bodies.
- `setInstance(URI.create(request.getRequestURI()))` provides the request path to identify the occurrence; never include query strings containing tokens or passwords in `instance`.
- `handleMethodArgumentNotValid` overrides the exact Spring 6.1 signature. For input validation on `@RequestBody`, the default status is typically `400`.
- `getFieldErrors()` yields per-field errors; `sorted(...)` makes the array deterministic in tests. `Objects.toString(...,"Invalid value")` avoids throwing `NullPointerException` when a default message is absent.
- `handleExceptionInternal(...)` preserves the base class's common handling rather than rebuilding everything from scratch.
- The snippet returns only **field name + message**, omitting `FieldError.getRejectedValue()` from the body to avoid inadvertently echoing passwords or PII.
- The `https://api.example.com/...` URIs in this lesson are illustrative addresses. In real deployments, replace them with URIs owned by your system and documented stably.
- Media type errors, malformed JSON, and several other MVC errors are handled by built-in methods of `ResponseEntityExceptionHandler`. There is no need to write `catch (Exception)` for every case in controllers.

### 5.5. Running and Observing Responses

Requires JDK 17+ and Maven. From the `problem-details-demo` directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

These are two commands run **sequentially**, not a single command. Once Spring Boot starts on port `8080`, send the requests below.

**Success — HTTP 201, not a Problem Detail:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"sku":"BOOK-1","quantity":2}'
```

Key part of the response:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"orderId":1001,"sku":"BOOK-1","quantity":2}
```

**Product not found — HTTP 404:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"MISSING","quantity":2}'
```

Illustrative body matching the exact mapping in the example:

```json
{
  "type": "https://api.example.com/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "Requested product was not found.",
  "instance": "/api/orders",
  "code": "PRODUCT_NOT_FOUND"
}
```

The `instance` path is `/api/orders` from `HttpServletRequest.getRequestURI()` in the advice. Key ordering and indentation above are for readability; the JSON serializer normally outputs a single line.

**Product locked — HTTP 409:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"LOCKED","quantity":2}'
```

Expected result includes status `409 Conflict`, `Content-Type: application/problem+json`, and a body with:

```json
{
  "type": "https://api.example.com/problems/product-locked",
  "title": "Product locked",
  "status": 409,
  "detail": "This product cannot be ordered while locked.",
  "instance": "/api/orders",
  "code": "PRODUCT_LOCKED"
}
```

`instance` can be populated by Spring from the request path when the problem body does not already have one. Do not assume other HTTP headers, key ordering, or JSON whitespace are part of the contract.

**Validation error — HTTP 400 with `errors` array:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"sku":"","quantity":0}'
```

Example result:

```json
{
  "type": "https://api.example.com/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "instance": "/api/orders",
  "code": "INVALID_REQUEST",
  "errors": [
    {
      "field": "quantity",
      "message": "must be greater than or equal to 1"
    },
    {
      "field": "sku",
      "message": "must not be blank"
    }
  ]
}
```

The actual `message` text depends on the Bean Validation provider and locale; the body illustrates common English text. Contract tests should assert **field names, error codes, and HTTP status**, avoiding dependency on exact phrasing if the application supports i18n.

**Malformed JSON — HTTP 400 without necessarily having `errors`:**

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  --data-binary '{"sku":'
```

Spring may throw `HttpMessageNotReadableException` during body parsing, before Bean Validation. The base class handles this error using framework behavior, so the response is usually `400` with a problem body **without the `errors` array from the validation override above**. Do not fabricate field names when JSON is malformed and no DTO could be bound.

### 5.6. Testing the Error Contract with MockMvc

**`src/test/java/demo/problems/ApiErrorContractTest.java`**

```java
package demo.problems;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiErrorContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validRequestReturns201() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"BOOK-1\",\"quantity\":2}"))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.orderId").value(1001))
           .andExpect(jsonPath("$.sku").value("BOOK-1"));
    }

    @Test
    void productNotFoundReturnsProblemDetail() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"MISSING\",\"quantity\":1}"))
           .andExpect(status().isNotFound())
           .andExpect(content().contentTypeCompatibleWith(
                    MediaType.parseMediaType("application/problem+json")))
           .andExpect(jsonPath("$.status").value(404))
           .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
           .andExpect(jsonPath("$.instance").value("/api/orders"));
    }

    @Test
    void lockedProductReturnsConflict() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"LOCKED\",\"quantity\":1}"))
           .andExpect(status().isConflict())
           .andExpect(jsonPath("$.status").value(409))
           .andExpect(jsonPath("$.code").value("PRODUCT_LOCKED"));
    }

    @Test
    void invalidRequestReportsFields() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"\",\"quantity\":0}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
           .andExpect(jsonPath("$.errors[0].field").value("quantity"))
           .andExpect(jsonPath("$.errors[1].field").value("sku"));
    }

    @Test
    void malformedJsonReturns400() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":"))
           .andExpect(status().isBadRequest());
    }
}
```

Run tests:

```bash
mvn test
```

The test suite has **5 test methods**. If configured properly and all pass, Maven exits with code `0`; the summary line typically displays `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`, while timing/logs depend on the environment.

`MockMvc` tests responses through the MVC framework without opening a real server port. Still, contract tests should also cover media type `415`, `405`, `404` for other resources, i18n, access permissions, unexpected errors, and contract-specific headers. Avoid testing errors by comparing raw JSON strings, because JSON object key order is not part of the RFC's semantics.

## 6. @ExceptionHandler, @RestControllerAdvice, and Choosing Scope

A local handler can target a single controller:

```java
@ExceptionHandler(ProductNotFoundException.class)
public ProblemDetail notFound(ProductNotFoundException ex) {
    ProblemDetail p = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
    p.setTitle("Product not found");
    return p;
}
```

This is a snippet meant to live inside a controller/advice with imports. It is not a standalone runnable file. If only one controller has a special error contract, a local handler may be enough.

When there are multiple controllers, use `@RestControllerAdvice` for an API set or module. Key selector parameters on `@ControllerAdvice`:

- `basePackages` or `basePackageClasses` — restrict controllers by package.
- `assignableTypes` — restrict controllers by class/interface.
- `annotations` — apply to controllers bearing a given annotation.
- `@Order` — determine precedence across multiple matching advices.

Never create a global `@ExceptionHandler(Exception.class)` that returns `400` for every error. NPEs, database failures, or internal serialization bugs are not client errors. A fallback 500 handler, if needed, must **log the exception server-side** and return a safe detail without hiding telemetry/incidents. If the application uses Spring Security, `AuthenticationException` and `AccessDeniedException` may be handled by `AuthenticationEntryPoint`/`AccessDeniedHandler` in the filter chain and may not pass through the same MVC advice.

### @ResponseStatus and ResponseStatusException

`@ResponseStatus(HttpStatus.NOT_FOUND)` on an exception or controller method can control the status, but does not design a full RFC error schema on its own. `ResponseStatusException` is a type of `ErrorResponseException` useful for a specific HTTP status; you still need to consider defining `type`, `code`, and public info. For domain exceptions like `ProductNotFoundException`, a dedicated handler usually expresses the contract more clearly.

### Avoiding Conflicts When Enabling Spring Boot Problem Details

If `spring.mvc.problemdetails.enabled=true`, Boot may register its own advice to handle many built-in errors. When overriding behavior for a group of these exceptions via another advice, you must verify ordering (`@Order`) and how exception handlers are selected. In section 5's example we intentionally extended `ResponseEntityExceptionHandler` and left the property off, giving a single owner for the application's MVC error policy.

## 7. Choosing the Right HTTP Status Code for an Error

| Status | Typical scenario | Important distinction |
| --- | --- | --- |
| `400 Bad Request` | Malformed JSON, invalid field/type, request validation | Request violates the contract |
| `401 Unauthorized` | Missing or invalid authentication credentials | Usually requires `WWW-Authenticate` matching the scheme |
| `403 Forbidden` | Authenticated but insufficient permissions | Do not turn into 200; avoid leaking policy details |
| `404 Not Found` | Resource missing or existence intentionally hidden | May need to avoid revealing enumeration |
| `405 Method Not Allowed` | HTTP method not supported by the route | HTTP `Allow` header is meaningful |
| `406 Not Acceptable` | Cannot produce a representation the client accepts | Distinct from request `Content-Type` |
| `409 Conflict` | Conflicts with current resource state | Not all validation errors |
| `415 Unsupported Media Type` | Request body format unsupported | E.g., sending `text/plain` to a JSON-only endpoint |
| `422 Unprocessable Content` | Server understands media type/syntax, but cannot process content semantically | Distinguish from `400` per contract |
| `429 Too Many Requests` | Client exceeded rate limits | Consider appropriate `Retry-After` |
| `500 Internal Server Error` | Unexpected server failure | `detail` must avoid leaking internals |
| `503 Service Unavailable` | Server temporarily unable to serve | Can use `Retry-After` if known |

Never put `status=404` in JSON while the real HTTP response is still `200`. Likewise, if `ResponseEntity` sets an HTTP status different from `ProblemDetail.status`, fix the inconsistency immediately.

## 8. Designing Problem Types and Extensions as a Long-Term Contract

### 8.1. Choosing Stable type URIs

A URI like `https://api.example.com/problems/order-not-found` represents an **error category**. It is not an occurrence ID and must not contain user-specific data. When using a real namespace:

1. Publish descriptions of the error, status, extensions, causes, and remediation.
2. Keep URIs stable across deployments.
3. Avoid creating new types per parameter/product/id.
4. Never reuse the same URI for completely different semantics.
5. If making breaking error schema changes, update the contract per versioning policy.

RFC 9457 recommends that dereferencing a `type` URI return documentation helping humans understand the error, though it does not require clients to make network requests to the URI when processing responses. Clients should match stable type/code values locally without fetching docs at runtime.

### 8.2. How Do type, code, and title Differ?

Example:

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 999",
  "code": "ORDER_NOT_FOUND"
}
```

- **`type`:** machine-readable identifier in the spirit of the RFC.
- **`code`:** optional application convenience, useful if your organization already uses error codes and SDKs use enums. Not required by the RFC.
- **`title`:** short human-readable label, may be localized; do not use `title` as a stable code.
- **`detail`:** occurrence-specific description, which may vary by language or values; clients should not parse text messages to drive behavior.

If an API already has stable `type` URIs and consumers use them, do not add `code` solely to duplicate the same info without benefit. If both are needed, define consistency rules and test to prevent drift.

### 8.3. Per-Field Validation Errors

RFC 9457 permits an `errors` extension per problem type contract; the shape below is useful for form UIs:

```json
{
  "type": "https://api.example.com/problems/invalid-request",
  "title": "Invalid request",
  "status": 400,
  "errors": [
    {
      "pointer": "/shippingAddress/postalCode",
      "code": "INVALID_FORMAT",
      "message": "Invalid postal code"
    }
  ]
}
```

Here `pointer` is a JSON Pointer as an **application contract proposal**; do not assume Spring automatically converts `FieldError.getField()` into a JSON Pointer. For nested Java Bean paths like `shippingAddress.postalCode`, convert and apply RFC 6901 escaping carefully; do not naively do `replace(".", "/")` if keys contain special characters, slashes, or array indices.

Keep field errors consistent in shape and avoid returning `rejectedValue` containing sensitive data. Some class-level or cross-field constraints only produce global errors without a field path; if the contract needs to report them, design an appropriate extension shape instead of silently dropping them.

### 8.4. Trace ID and Correlation ID

To let users report errors and support teams look up logs, you can include `traceId` from your tracing system:

```json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected server error occurred.",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

This is illustrative JSON only. `traceId` is an extension, not required by the RFC. Do not generate an arbitrary "trace ID" from a random UUID inside each exception and claim it can be looked up in logs if logs do not record that same ID. When using Micrometer Tracing/OpenTelemetry, pull the ID from the active trace/observation and ensure loggers, exporters, and responses correlate.

Never return stack traces, internal file paths, SQL syntax, user emails, access tokens, connection strings, or secrets to clients.

## 9. Internationalization and Safe Message Handling

Problem Details supports localized human-readable `title` and `detail`; clients may send `Accept-Language`. However, `type`, `code`, and HTTP status must maintain **stable meaning** across language changes.

Spring supports `MessageSource`. `ResponseEntityExceptionHandler` can look up message codes for `type`, `title`, and `detail` of `ErrorResponse`. Default code patterns typically include:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.<fully-qualified-exception-class>
```

For example, an organization's translation policy might map `INVALID_REQUEST` to a Vietnamese/English title. With custom exceptions and manually constructed `ProblemDetail`, you need to use `MessageSource` or your own policy explicitly rather than expecting hardcoded controller strings to translate automatically.

Principles to follow:

- Never let locale change `type URI`/`code`.
- Never treat `detail` as a fixed machine-parseable format; it may contain localized prose.
- Client-facing messages differ from log messages intended for dev/ops.
- Clients needing rich UX can rely on `code` or `type` to present tailored explanations, avoiding forcing the backend to expose overly detailed info.
- Never pass internal or database exception messages straight into `detail` without safety verification.

## 10. Limits of ProblemDetail in Real Deployments

### 10.1. Does Not Automatically Cover the Entire Stack

Errors in Servlet filters, Spring Security, reverse proxies, API gateways, containers, servlet asynchronous timeouts, SSE/WebSockets, or already-committed response streams can bypass MVC advice. If you require unified JSON errors across layers, coordinate multiple layers and test separately. Do not assume `@RestControllerAdvice` catches authentication/authorization exceptions from the security filter chain.

### 10.2. Do Not Wrap ProblemDetail in Another Arbitrary Envelope

If a global `ResponseBodyAdvice` automatically wraps every response into:

```json
{"success":false,"data":{"type":"...","title":"...","status":400}}
```

then that body **is no longer a top-level Problem Detail** matching the `application/problem+json` schema expected by RFC clients. If a custom envelope is required, change the media type/contract accordingly or exclude `ProblemDetail` from the wrapper. In Spring MVC, the converter is selected **before** `ResponseBodyAdvice.beforeBodyWrite`; swapping object types arbitrarily can cause serialization errors.

### 10.3. Translating 500 Errors Should Not Lose Telemetry

A global fallback handler such as:

```java
@ExceptionHandler(Exception.class)
public ProblemDetail fallback(Exception ex) {
    return ProblemDetail.forStatusAndDetail(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "An unexpected server error occurred.");
}
```

This is an **illustrative snippet**, not a complete file. It gives clients a safe response, but it can make the error count as handled, affecting logging and observation if there is no clear policy. In production, log full server-side details safely without leaking secrets, integrate tracing/metrics, and ensure you do not "swallow" failures operations needs to detect.

### 10.4. Does Not Replace Validation and Authorization

`ProblemDetail` is only an **error representation**. If the server accepts an unauthorized request, returning pretty JSON does not fix the vulnerability. Likewise, DTO validation must run independently; conversion/validation errors are only formatted as problems after being detected. Avoid using `ProblemDetail` as an arbitrary bucket for business failure data without clear HTTP semantics.

### 10.5. Status/Body Consistency with the RFC

- Using `ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND,...)` and returning it from `@ExceptionHandler` normally leads Spring to set the matching status.
- When using `ResponseEntity<ProblemDetail>`, ensure `ResponseEntity.status` and `ProblemDetail.status` match.
- `application/problem+json` is a dedicated JSON media type; keep the body a top-level object rather than returning a hand-concatenated JSON string.
- Do not attach a `ProblemDetail` body to `204 No Content`, `304 Not Modified`, or `HEAD` responses against body semantics.
- Error responses may need cache-control, retry, or rate-limit headers; Problem Details does not generate policy headers automatically.

### 10.6. Do Not Put Sensitive Information into Extensions

`ProblemDetail.setProperty("debug", exception)` or `setProperty("params", request.getParameterMap())` can inadvertently serialize internal details, PII, or secrets. Whitelist safe fields/values and bound lengths. Because Jackson promotes extensions to top-level properties, "adding extra stuff for debugging" has immediate public impact.

## 11. Common Pitfalls and How to Diagnose Them

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| `400` yet body is not RFC | Boot problem-details disabled, no matching handler | Check `spring.mvc.problemdetails.enabled` or custom advice |
| `ProblemDetail` returned with HTTP status `200` | Returned custom JSON DTO / wrong `ResponseEntity` status | Check status line and `ProblemDetail.status` |
| `"properties":{"code":...}` instead of top-level `code` | Missing Spring Jackson mixin/config | Check `ProblemDetailJacksonMixin` and converters |
| `type` is always `about:blank` | `type` URI not set | If distinct machine-readable problems are needed, set stable types |
| Validation error returns `400` without `errors` | Base handler does not define custom extensions | Properly override `handleMethodArgumentNotValid` |
| Business exception returns `500` | Custom exception unmapped | Add `@ExceptionHandler` with clear status/type |
| Security error returns HTML or different response | Exception occurred in filter chain before MVC | Configure separate security handler/gateway |
| `@RestControllerAdvice` does not run | Package scan/scope, handler order/conflict | Check bean, `@Order`, stack trace |
| Unexpected `406` or `415` | Incompatible `Accept`/`Content-Type` | Inspect media types, converters, and endpoint mappings |
| `500` leaks SQL or stack trace | Passed `ex.getMessage()` straight into `detail` | Replace with generic message, log exception internally |
| Clients break parsing `detail` | Clients relied on localized text | Switch clients to `type`/`code` |
| RFC error double-wrapped | Global `ResponseBodyAdvice` also wraps `ProblemDetail` | Exclude `ErrorResponse`/`ProblemDetail` appropriately |
| `instance` leaks tokens | Placed full URL with query string in response | Use safe path or opaque occurrence ID |
| Adding an extension breaks old SDKs | Closed-schema client fails on unknown fields | Maintain contract tests and versioning policy |

A quick inspection workflow:

1. Send a request with `curl -i` to inspect the **actual HTTP status and `Content-Type`**.
2. Identify whether the error originated in argument resolution, validation, controller/service, MVC handler, or filter/gateway.
3. Inspect `@ControllerAdvice` beans, ordering, and `ResponseEntityExceptionHandler` handlers.
4. Verify `type`, `title`, `status`, `detail`, `instance`, and extensions against the contract.
5. Check the server-side root cause in logs/traces without secrets; do not expose stack traces.
6. Run contract tests for at least one business error, validation error, malformed JSON, and unexpected 500.
7. Test older clients against the new error schema, especially if migrating from custom error DTOs.

## 12. Rules for Designing a Sustainable Error Contract

An API using Problem Details should have at least:

- **Problem type catalog:** URIs, titles, and HTTP statuses for each problem type, plus documented extension fields.
- **Clear status rules:** `400` validation, `404` not found, `409` conflict, `500` server error — adapted to business needs yet consistent.
- **Security content rules:** safe public details, never leaking secrets/stack traces/internal identifiers.
- **Stable identifiers for machine consumers:** prefer `type`; supplement with `code` if required by the contract.
- **Validation extension schema:** use `errors` consistently, avoiding varying shapes across endpoints.
- **Locale policy:** title/detail may be localized; type/code stay invariant.
- **Correlation ID:** if needed, link responses to logs/traces; never invent untraceable IDs.
- **Backward compatibility tests:** keep fixtures or published OpenAPI schemas; avoid breaking clients consuming `application/problem+json`.
- **Intentional exceptions:** proxy/security/streaming/legacy responses outside the MVC pipeline need explicit separate policies.
- **Single policy owner:** avoid multiple global advices rewriting errors unpredictably.

## 13. Knowledge Check Exercises

1. How do `ProblemDetail.type` and `ProblemDetail.instance` differ?
2. An endpoint returns `HTTP 200 OK` with body `{"status":404}`. Why is this a broken contract?
3. How does `ErrorResponseException` differ from `ProblemDetail`, which is just data?
4. Which method of `ResponseEntityExceptionHandler` should catch `@Valid @RequestBody` failures in the example?
5. Why does `@RestControllerAdvice` not guarantee replacing every error response from Spring Security or a gateway?
6. Where does `setProperty("code", "...")` appear in JSON when using Jackson/Spring?
7. Should `detail` and `title` serve as stable codes that frontends parse by string matching?
8. When should `409 Conflict` be used instead of `400 Bad Request`?
9. Why can `ProblemDetail` not replace validation, authorization, or business rules?
10. If you enable `spring.mvc.problemdetails.enabled=true` while also having an advice extending `ResponseEntityExceptionHandler`, what must you verify?
11. If an API supports multiple languages, which fields should vary by locale and which should not?
12. Why should `FieldError.getRejectedValue()` and `Exception.getMessage()` not be returned arbitrarily in error bodies?

**Answer hints:** (1) `type` identifies the error category, `instance` identifies the occurrence. (2) Real HTTP status reports success while the body reports an error. (3) An exception carrying status/headers/body via `ErrorResponse`; `ProblemDetail` is the representation object. (4) `handleMethodArgumentNotValid`. (5) Errors can happen outside the MVC handler resolver chain. (6) Top-level JSON extension. (7) No, use `type`/`code`. (8) When a conflict with current resource state prevents the request from executing. (9) It is only an error representation. (10) Handler ordering and collisions. (11) `title`/`detail` may be translated; `type`/`code`/status keep invariant semantics. (12) They can expose sensitive data and implementation details.

## 14. References

- [RFC 9457 — Problem Details for HTTP APIs, IETF](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Spring Framework — Error Responses (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.1.21 — ProblemDetail Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework 6.1.21 — ErrorResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework 6.1.21 — ErrorResponseException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/ErrorResponseException.html)
- [Spring Framework 6.1 — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot — Servlet Web Applications: Problem Details](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [Spring Framework — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)

All code belongs to the Spring MVC/Jackson example and does not apply verbatim to WebFlux. HTTP payloads are contract examples verifiable with `curl`/`MockMvc`; default statuses, error text, and headers outside the example code may still differ by environment, locale, and configuration.
