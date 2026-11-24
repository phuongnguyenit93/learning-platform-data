# Distinguishing JSON Read Errors from Parameter Conversion Errors in Spring Boot MVC

## 1. Problem and Goals

When building REST APIs with Spring Boot, there are many cases where a client sends invalid input and receives **HTTP 400 Bad Request**. Two errors most commonly conflated are:

1. **JSON body read errors**: Spring MVC cannot read or decode the HTTP request body into the Java type required by `@RequestBody`. A typical exception is `HttpMessageNotReadableException`.
2. **Parameter conversion errors**: Spring MVC extracted a value from the URL path, query string, header, or cookie, but could not convert it to the Java parameter type—for example, `"abc"` into `long`. A common exception is `MethodArgumentTypeMismatchException`.

Both can return 400, yet their **execution paths, exceptions, classes to customize, and remedies differ**. JSON that is completely valid *syntactically* can still fail when mapped onto a Java type. Conversely, a query parameter is not JSON, so no JSON parser is involved.

This lesson focuses on the **Spring MVC Servlet stack**, e.g., Spring Boot 3.5.16 + Java 17+ with `spring-boot-starter-web`. The final section briefly compares Spring WebFlux, because the two stacks differ in decoding APIs and exception types.

## 2. Input Data Map and Where Errors Arise

~~~text
HTTP request
  |
  +-- request line: POST /orders/abc?page=no HTTP/1.1
  |      |
  |      +-- path/query/header/cookie -> HandlerMethodArgumentResolver
  |                                      -> ConversionService/WebDataBinder
  |                                      -> parameter conversion error if wrong type
  |
  +-- headers: Content-Type: application/json
  |      |
  |      +-- select HttpMessageConverter matching media type and target type
  |               |
  |               +-- no matching converter: typically 415
  |
  +-- body: {"quantity":"not-a-number"}
         |
         +-- @RequestBody -> HttpMessageConverter (typically Jackson)
                              |
                              +-- malformed JSON / unreadable body
                              +-- valid JSON but cannot construct Java object
                              |      -> typically HttpMessageNotReadableException
                              |
                              +-- Java object created successfully
                                     |
                                     +-- @Valid / Bean Validation
                                            -> typically MethodArgumentNotValidException
                                     |
                                     +-- invoke controller
~~~

This is a high-level map, not every framework internal; Spring MVC has multiple resolvers and converters with different conditions. If handler mapping rejects the request due to a `consumes` mismatch, a 415 error can even occur **before body reading begins**.

### Two Controller Signatures Trigger Two Distinct Branches

~~~java
@PostMapping("/orders")
public OrderResponse create(@RequestBody CreateOrderRequest input) {
    // Reads HTTP body by media type, typically using Jackson for JSON.
}

@GetMapping("/orders/{id}")
public OrderResponse find(@PathVariable("id") long id,
                          @RequestParam("page") int page) {
    // Extracts text values from path/query and converts them to long/int.
}
~~~

These methods are **illustrative**, lacking the enclosing class and imports to run standalone. For `@RequestBody`, data goes through `HttpMessageConverter`; for `@PathVariable` or `@RequestParam`, MVC typically extracts strings from the request and converts types via `ConversionService`/the binder.

## 3. JSON Read Errors: HttpMessageNotReadableException

### 3.1. Path of @RequestBody

When a method takes `@RequestBody CreateOrderRequest request`, Spring MVC typically uses `RequestResponseBodyMethodProcessor` to read the body via a suitable `HttpMessageConverter`. With JSON and Jackson on the classpath, the JSON converter turns the byte stream into a Java object.

~~~text
Content-Type: application/json
           |
           v
Selected HttpMessageConverter
           |
           v
Jackson reads tokens -> maps properties/constructor/record
           |
           +-- success: CreateOrderRequest created
           +-- failure: HttpMessageNotReadableException
~~~

Conditions that can lead to `HttpMessageNotReadableException`:

- **Malformed JSON**: missing braces, missing commas, invalid tokens.
- **JSON structure mismatches the expected Java structure**: sending an array when an object is expected, or an object where a scalar is required, depending on configuration.
- **JSON value cannot be deserialized into the Java type**: e.g., field `quantity` is declared `int`, but the body contains `"quantity":"abc"`.
- **Enum/date/custom deserializer failure**: JSON is syntactically valid, but the format violates the target type or Jackson policy.
- **Missing required body** with `@RequestBody(required = true)`, when the pipeline has no content to read.

**Note:** this exception represents an error *reading the HTTP message*, not exclusively JSON syntax errors. Other media types/converters can throw it as well. In JSON REST apps, it is a useful signal for distinguishing body errors from query/path errors.

### 3.2. Valid JSON Does Not Guarantee a DTO Can Be Created

Suppose Java defines:

~~~java
public record CreateOrderRequest(String product, int quantity) {
}
~~~

The first body is **invalid JSON**:

~~~json
{"product":"book","quantity":
~~~

The second body is **valid JSON**, yet cannot instantiate the record under standard mapping:

~~~json
{"product":"book","quantity":"many"}
~~~

These two bodies have different technical causes inside Jackson, yet MVC typically surfaces both as `HttpMessageNotReadableException` at the `@RequestBody` boundary. A shared error handler can return a business error code like `INVALID_JSON_BODY`; if finer granularity is needed, inspect nested causes (e.g., parse vs. mapping exceptions), without depending tightly on Jackson's exact message text.

A valid body:

~~~json
{"product":"book","quantity":2}
~~~

can construct the record successfully; whether the record satisfies business rules is a **separate step**, such as Bean Validation.

### 3.3. The Parameter Type Decides Whether JSON Is Parsed

Do not assume every method with `@RequestBody` parses JSON into an object. For example:

~~~java
@PostMapping("/raw")
String raw(@RequestBody String input) {
    return input;
}
~~~

This is an illustrative method. `StringHttpMessageConverter` can read the entire body as a plain string without invoking Jackson to check JSON syntax, depending on converters and media type. Then `{"a":` enters the method as text. To enforce JSON parsing, deserialize/validate a JSON target type or parse explicitly as required.

### 3.4. HTTP 400 or 415?

When the `Content-Type` header is unsupported by converters/handlers—such as sending `text/plain` to an endpoint accepting only a JSON DTO—Spring MVC typically returns **415 Unsupported Media Type** via `HttpMediaTypeNotSupportedException`. This is a **media-type selection error**, not a JSON parse error.

When the header is `application/json`, the JSON converter is selected, and if the payload cannot be parsed/mapped, MVC typically returns **400 Bad Request** via `HttpMessageNotReadableException`.

Do not mask every 400/415 behind a single `INVALID_JSON` error code: clients need to know whether to fix **Content-Type**, **body structure**, or **query/path values**.

## 4. Parameter Conversion Errors: MethodArgumentTypeMismatchException

### 4.1. Path of @PathVariable / @RequestParam

~~~java
@GetMapping("/orders/{id}")
String find(@PathVariable("id") long id,
            @RequestParam("page") int page) {
    return id + ":" + page;
}
~~~

For request `GET /orders/not-a-number?page=1`:

1. The router selects the `/orders/{id}` mapping.
2. The `@PathVariable` resolver extracts the string `"not-a-number"`.
3. Spring MVC uses the conversion service/binder to convert it to `long`.
4. Conversion fails and throws `MethodArgumentTypeMismatchException` before the controller runs.

With `GET /orders/42?page=wrong`, the same occurs, except the failing parameter is `page` of type `int`.

Other arguments also go through basic conversion where applicable: `@RequestHeader`, `@CookieValue`, `@MatrixVariable`, and `@RequestParam` values for UUID, Boolean, Enum, LocalDate, etc.

### 4.2. What Information Does the Exception Carry?

In Spring MVC, `MethodArgumentTypeMismatchException` (package `org.springframework.web.method.annotation`) extends `TypeMismatchException`. It typically exposes:

- `getName()`: method parameter name, such as `"page"` or `"id"`.
- `getValue()`: the failing input value (potentially sensitive).
- `getRequiredType()`: target class such as `int`/`long`.
- `getParameter()`: `MethodParameter` metadata.
- `getCause()`: underlying conversion cause.

Returning the field name and a safe message to the client is helpful. **Never return raw `getValue()`, `getCause().getMessage()`, or stack traces** if the input might contain personal data, tokens, or internal implementation details.

### 4.3. Missing Parameters Are Not Conversion Errors

A request `GET /orders/42` when the controller requires `@RequestParam("page") int page` throws `MissingServletRequestParameterException`. No `page` string exists to convert, so it should not be classified as `MethodArgumentTypeMismatchException`.

Similarly, a missing required header can raise `MissingRequestHeaderException`, and a missing cookie can raise `MissingRequestCookieException`. Cases where a required argument converts to `null` can also be handled as a missing-argument exception depending on annotation and target type.

### 4.4. Custom Converters and Formatters

If a value object from a URI or query parameter needs custom conversion, register a `Converter` or `Formatter` for MVC via `WebMvcConfigurer.addFormatters` rather than writing a Jackson deserializer just to fix `@PathVariable`.

Example extension:

~~~java
@Configuration
class MvcConversionConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(String.class, OrderCode.class,
                text -> new OrderCode(text));
    }
}
~~~

This is an **illustrative excerpt** requiring the `OrderCode` record and imports. It converts String inputs for matching parameters; it does not cause Jackson to use that converter automatically when decoding `@RequestBody`. JSON inputs normally require `ObjectMapper` configuration, modules, Jackson annotations, or proper custom deserializers.

For `LocalDate` in queries, Spring MVC supports `@DateTimeFormat` and formatters. For date fields in JSON DTOs, Jackson mechanisms such as `@JsonFormat` and the Java Time module apply.

## 5. Common Error Reference Table

| Request / failure | Primary processing path | Typical exception | Typical default HTTP status |
|---|---|---|---|
| `@RequestBody` receives JSON missing closing brace | JSON message converter | `HttpMessageNotReadableException` | 400 |
| Valid JSON, but `int quantity` receives `"abc"` | Jackson JSON → Java | `HttpMessageNotReadableException` | 400 |
| `@RequestBody(required=true)` has no body | Body resolver/converter | `HttpMessageNotReadableException` | 400 |
| JSON types match, but `@Valid` fails `@Min` | Bean Validation after deserialization | `MethodArgumentNotValidException` | 400 |
| `@RequestParam int page` receives `page=abc` | MVC ConversionService | `MethodArgumentTypeMismatchException` | 400 |
| `@PathVariable long id` receives `id=nope` | MVC ConversionService | `MethodArgumentTypeMismatchException` | 400 |
| Required `@RequestParam page` is missing | Argument resolver | `MissingServletRequestParameterException` | 400 |
| Required `@RequestHeader` is missing | Header resolver | `MissingRequestHeaderException` | 400 |
| Body has `Content-Type: text/plain`, handler/converter expects JSON DTO | Media type mapping/converter | `HttpMediaTypeNotSupportedException` | 415 |
| `Accept` requests a response type the server cannot produce | Response content negotiation | `HttpMediaTypeNotAcceptableException` | 406 |
| `@ModelAttribute` form field has invalid type | Data binder + BindingResult | Binding error / `MethodArgumentNotValidException` depending on signature | Usually 400 or method handles `BindingResult` |
| Constraint directly on controller method param fails | Method validation | `HandlerMethodValidationException` | Usually 400 for request input |

This table reflects **typical default behavior** in modern Spring MVC. Global exception handlers, `@ControllerAdvice`, `BindingResult`, method signatures, custom converters, Spring Security, and Spring Boot settings can alter how responses are rendered.

**Important:** do not treat every `TypeMismatchException` across the application as a controller parameter error. Type mismatches can occur in other binding contexts. Handling `MethodArgumentTypeMismatchException` specifically avoids catching too broadly.

## 6. Distinguishing from Validation and Business Rule Errors

JSON/body conversion errors, parameter conversion errors, validation errors, and business rule errors belong to four distinct stages.

**Stage A — Decode/deserialize:** Can the JSON be parsed? Can the Java object be constructed?

~~~json
{"product":"book","quantity":"many"}
~~~

If Java expects `int quantity`, this JSON is syntactically valid yet fails deserialization. The controller is not invoked.

**Stage B — URL/header conversion:** Can query `?page=xyz` be converted to `int`? If not, the controller is not invoked.

**Stage C — Validation on the created object:** The body:

~~~json
{"product":"book","quantity":0}
~~~

maps onto the Java record, yet if the field has `@Min(1)` and the method has `@Valid`, it violates the constraint, typically throwing `MethodArgumentNotValidException`. Do not call this a JSON parser error.

**Stage D — Business rule:** The body is valid and passes Bean Validation, yet the product is out of stock or the order cannot transition state. That is a business decision of the service/controller, which may return 409 or 422 per the API contract. The framework **does not automatically return 422** simply because a field fails a business check.

For `@Min`/`@NotBlank` placed directly on method parameters, Spring Framework 6.1+ also raises `HandlerMethodValidationException`. Do not write a handler catching only `MethodArgumentNotValidException` and assume it covers all validation.

## 7. Complete Example: Spring Boot 3.5.16, Java 17+, Maven

This demo builds a REST controller with two endpoints:

- `POST /api/orders`: reads a JSON body via `@Valid @RequestBody`.
- `GET /api/orders/{orderId}?page=...`: reads path/query and converts them to `long` and `int`.

Add `@RestControllerAdvice` to return **two distinct error codes** for JSON read failures and parameter conversion failures. Validation and 415 errors are left to Spring MVC's default handling so you can observe them taking separate branches.

### 7.1. Directory Structure

~~~text
request-error-demo/
  pom.xml
  src/
    main/
      java/com/example/inputerrors/
        RequestErrorApplication.java
        OrderController.java
        RequestErrorAdvice.java
    test/
      java/com/example/inputerrors/
        RequestErrorMvcTest.java
~~~

### 7.2. pom.xml

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
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>request-error-demo</artifactId>
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

The example uses Spring Boot 3.5.16 for consistent APIs and packages. Production projects should select a supported Boot line kept current per security policy; when upgrading to 4.x, audit starters, module layout, APIs, and tests.

### 7.3. Entry Point

File `src/main/java/com/example/inputerrors/RequestErrorApplication.java`:

~~~java
package com.example.inputerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestErrorApplication.class, args);
    }
}
~~~

### 7.4. REST Controller and Record DTO

File `src/main/java/com/example/inputerrors/OrderController.java`:

~~~java
package com.example.inputerrors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    public record CreateOrderRequest(
            @NotBlank String product,
            @Min(1) int quantity) {
    }

    public record CreateOrderResponse(String product, int quantity) {
    }

    @PostMapping("/api/orders")
    public CreateOrderResponse create(
            @Valid @RequestBody CreateOrderRequest request) {
        return new CreateOrderResponse(
                request.product(), request.quantity());
    }

    @GetMapping("/api/orders/{orderId}")
    public String read(
            @PathVariable("orderId") long orderId,
            @RequestParam("page") int page) {
        return "orderId=" + orderId + ";page=" + page;
    }
}
~~~

Explanation:

- For `create`, Spring reads the body, Jackson constructs `CreateOrderRequest`, and then validation checks `@NotBlank`/`@Min`. The method is called only when all required input stages succeed.
- For `read`, MVC extracts path/query from the URL, converts them to `long`/`int`, and then calls the method. JSON body decoding is not involved.
- Returning a record is automatically serialized to JSON by Jackson when converters and content negotiation support it. The example has no database; its purpose is separating request error branches.

### 7.5. Global Advice: Two Separate Error Codes

File `src/main/java/com/example/inputerrors/RequestErrorAdvice.java`:

~~~java
package com.example.inputerrors;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class RequestErrorAdvice {

    public record ApiError(
            String code, String field, String message) {
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadableBody(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_JSON_BODY",
                        "body",
                        "Request body is unreadable or does not match expected data types"));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiError> invalidParameter(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_PARAMETER",
                        ex.getName(),
                        "Parameter cannot be converted to the required type"));
    }
}
~~~

**Points to note:**

- The two `@ExceptionHandler` methods catch **two different exception types**. Both return HTTP 400, yet the JSON error carries distinct `code` values so the frontend can guide users accurately.
- The handlers do not return the failing body, raw query, stack trace, or `ex.getMostSpecificCause().getMessage()`. That is a safer choice when inputs might contain sensitive data.
- `ex.getName()` is the Java parameter name such as `orderId` or `page`. If you need to guarantee alignment with public `@PathVariable`/`@RequestParam` names, verify annotation metadata and your system's mapping conventions.
- This demo intentionally does not catch `MethodArgumentNotValidException`, `HttpMediaTypeNotSupportedException`, or other exceptions. That is **by design**: Spring Boot/MVC handles them with defaults; clients should not expect every error response to share the `ApiError` structure until a unified policy is added.
- Never use `@ExceptionHandler(Exception.class)` to turn every error into 400. Bugs, database errors, timeouts, or server-side exceptions must be classified properly.
- When enabling Problem Details or using multiple `@ControllerAdvice` beans, verify advice ordering so handlers do not conflict. In this sample project, default settings are simple and this advice directly handles the two target exceptions.

### 7.6. Running and Calling with curl

In the project directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

If the project includes the Maven Wrapper, you can use `./mvnw spring-boot:run` or `mvnw.cmd spring-boot:run` on Windows.

**Valid JSON:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":2}'
~~~

Expected HTTP **200 OK** and JSON body equivalent to:

~~~json
{"product":"book","quantity":2}
~~~

Whitespace/key ordering in serialized JSON is not a strict contract; the two fields and their values are what matter.

**Malformed JSON:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":'
~~~

Expected HTTP **400** and body produced by the advice:

~~~json
{
  "code": "INVALID_JSON_BODY",
  "field": "body",
  "message": "Request body is unreadable or does not match expected data types"
}
~~~

**Valid JSON, but quantity cannot map to int:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":"many"}'
~~~

Expected HTTP **400**, also with `code=INVALID_JSON_BODY`. Never call this `MethodArgumentTypeMismatchException` merely because the field is an `int`: the data source is the **JSON body**, handled by Jackson.

**Wrong type in path parameter:**

~~~bash
curl -i "http://localhost:8080/api/orders/abc?page=1"
~~~

Expected HTTP **400**, body:

~~~json
{
  "code": "INVALID_PARAMETER",
  "field": "orderId",
  "message": "Parameter cannot be converted to the required type"
}
~~~

**Wrong type in query parameter:**

~~~bash
curl -i "http://localhost:8080/api/orders/42?page=xyz"
~~~

Expected HTTP **400**, `code=INVALID_PARAMETER`, `field=page`.

**Missing query parameter:**

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Expected HTTP **400** due to missing parameter, though the body may **differ** from the custom `ApiError` structure because the demo defines no handler for `MissingServletRequestParameterException`.

**Body maps cleanly, but validation fails:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":0}'
~~~

Expected HTTP **400** from Bean Validation, not `INVALID_JSON_BODY`. If a uniform error contract is required, add handling for `MethodArgumentNotValidException`.

**Wrong Content-Type:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: text/plain" \
  -d '{"product":"book","quantity":2}'
~~~

Expected **415 Unsupported Media Type** because data sent to `@RequestBody CreateOrderRequest` has no matching converter for `text/plain` under default configuration.

`curl -i` prints the status line, headers, and body; the JSON blocks above illustrate only the **response body**, not the entire curl output.

## 8. MockMvc Tests: Proving the Two Errors Take Different Branches

MockMvc invokes the Spring MVC pipeline without binding a TCP port. To test converters, argument resolvers, and advice together in the same context, use Boot 3.5's `@SpringBootTest` + `@AutoConfigureMockMvc`.

File `src/test/java/com/example/inputerrors/RequestErrorMvcTest.java`:

~~~java
package com.example.inputerrors;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class RequestErrorMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validJsonIsAccepted() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.product").value("book"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void malformedJsonIsReportedAsBodyError() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON_BODY"))
                .andExpect(jsonPath("$.field").value("body"));
    }

    @Test
    void validJsonWithWrongFieldTypeIsAlsoBodyError() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":\"many\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_JSON_BODY"));
    }

    @Test
    void invalidPathVariableIsArgumentTypeMismatch() throws Exception {
        mvc.perform(get("/api/orders/abc").param("page", "1"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.field").value("orderId"));
    }

    @Test
    void invalidQueryParameterIsArgumentTypeMismatch() throws Exception {
        mvc.perform(get("/api/orders/42").param("page", "wrong"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"))
                .andExpect(jsonPath("$.field").value("page"));
    }

    @Test
    void validPathAndQueryAreAccepted() throws Exception {
        mvc.perform(get("/api/orders/42").param("page", "3"))
                .andExpect(status().isOk())
                .andExpect(content().string("orderId=42;page=3"));
    }

    @Test
    void missingQueryParamIsNotTypeMismatch() throws Exception {
        mvc.perform(get("/api/orders/42"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void jsonValidationErrorIsNotJsonReadFailure() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"product\":\"book\",\"quantity\":0}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedContentTypeIsNotMalformedJson() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("{\"product\":\"book\",\"quantity\":2}"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

With the required dependencies, these tests distinguish 400 from body decoding, 400 from path/query conversion, 400 from validation, 400 from missing parameters, and 415 from media types. The tests assert the `ApiError` body only for the cases handled by the sample advice, avoiding coupling to Boot's default error messages.

In a real project, also verify statuses and error codes via `RANDOM_PORT` HTTP integration tests, since MockMvc does not exercise the TCP stack, reverse proxies, TLS, or real HTTP clients.

## 9. Designing a Structured API Error Contract

Rather than returning arbitrary library exception messages, the backend should return stable fields that clients can handle programmatically:

| Field | Example | Notes |
|---|---|---|
| `code` | `INVALID_JSON_BODY`, `INVALID_PARAMETER`, `VALIDATION_ERROR` | Stable and documented |
| `message` | Short human-readable description | No stack trace, SQL, tokens, or raw body |
| `field` or `errors[]` | `page`, `orderId`, `quantity` | Expose only permitted metadata |
| `requestId` | ID from tracing system | For internal log lookup; never expose secrets |
| `status` | 400, 415, 422 per contract | Do not collapse distinct causes into one code |

**A unified contract does not mean a single error code.** The system can return HTTP 400 for both JSON and query conversion while keeping distinct business `code` values. Never expose raw `JsonMappingException.getPathReference()` if DTOs contain sensitive fields or internal class names.

### Problem Details per RFC 9457

Spring Framework supports `ProblemDetail`, `ErrorResponse`, and `ResponseEntityExceptionHandler` to represent standardized errors (typically containing `type`, `title`, `status`, `detail`, and `instance`).

With Spring Boot 3.5, you can opt into built-in Spring MVC support via:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

When enabled, Boot auto-configures `ResponseEntityExceptionHandler` for built-in MVC exceptions. If the application also defines a custom `@ControllerAdvice` catching those same exceptions, check **advice ordering and handler scope**, especially if your custom advice should take precedence over Boot's default configuration (usually order 0). The demo above leaves this flag off to keep separating the two exceptions straightforward.

Alternatively, you can adopt **`ProblemDetail` for the entire contract** instead of an `ApiError` record. Example isolated excerpt inside an `@ExceptionHandler`:

~~~java
ProblemDetail problem = ProblemDetail.forStatus(
        HttpStatus.BAD_REQUEST);
problem.setTitle("Invalid request parameter");
problem.setDetail("A query or path parameter has an invalid type");
problem.setProperty("code", "INVALID_PARAMETER");
return problem;
~~~

This is an illustrative snippet requiring `ProblemDetail` and `HttpStatus` imports inside a handler method. Spring can serialize `ProblemDetail` under media type `application/problem+json` when converters are configured properly.

If you extend `ResponseEntityExceptionHandler`, prefer overriding its protected handler hooks rather than declaring duplicate `@ExceptionHandler` methods for the same built-in exceptions in a way that causes ambiguity.

## 10. Fast Debugging Following the Data Path

### 10.1. When POST JSON Returns 400

Check in order:

1. Is `Content-Type` `application/json` or another converter-supported media type?
2. Are the body bytes/encoding valid? Did a filter or gateway consume them before `@RequestBody`?
3. Is the JSON syntax valid?
4. Does the JSON structure match the DTO/record, property names, and constructors?
5. Can enums, dates, numbers, or custom deserializers convert the values?
6. If decoding succeeded, did a `@Valid` or method validation constraint fail?
7. Inspect the **first meaningful exception type** in logs; do not guess the failure merely from seeing status 400.

Step 1 may reveal a 415 rather than a 400; step 6 indicates validation, not a JSON parser error.

### 10.2. When GET Path/Query Returns 400

Check:

1. Did handler mapping match the path and HTTP method?
2. Is the `@PathVariable` or `@RequestParam` value present?
3. Was the value URL-encoded properly? For example, `+` in a query can be interpreted differently from a literal plus sign.
4. What Java type is expected: `int`, `UUID`, `LocalDate`, `Enum`?
5. Is `ConversionService`, `@DateTimeFormat`, a `Converter`, or a custom formatter being applied?
6. Is the exception `MethodArgumentTypeMismatchException`, `MissingServletRequestParameterException`, or another binding error?

For instance, `GET /api/orders/42?page=abc` has no JSON body, so tweaking `ObjectMapper` will not resolve it.

### 10.3. Distinguishing Wire-Level Boundary Errors from Nested Causes

When Jackson fails to parse JSON, the nested cause may be `JsonParseException`, `JsonMappingException`, or a subclass. Yet at the `@RequestBody` boundary, Spring MVC normally wraps it in `HttpMessageNotReadableException`. When reading logs, distinguish **the Spring MVC exception driving the HTTP response** from **the underlying Jackson cause**.

For query/path values, the nested cause might be `NumberFormatException` or a conversion failure; however, proper advice catches `MethodArgumentTypeMismatchException` at the MVC layer rather than catching every `NumberFormatException` application-wide.

**Never catch `RuntimeException` and return 400 for everything**, as that hides logic bugs, null pointers, transaction failures, or server errors that should return 500.

## 11. Misconceptions to Avoid

- **"Valid JSON cannot throw HttpMessageNotReadableException."** False. Syntactically valid JSON can still fail to map to a Java type or be rejected by a custom deserializer.
- **"Any invalid int value throws MethodArgumentTypeMismatchException."** False. An `int` inside a JSON body is decoded by Jackson; an `int` from query/path goes through MVC conversion.
- **"Both return 400, so use a single error code."** Not recommended. Clients generally need to know whether to fix the body or a parameter.
- **"`@Valid` is the JSON parser."** False. Validation runs after the object/argument is created; its exceptions differ.
- **"Missing `page` is a type mismatch."** False. It normally falls under missing-parameter errors, not conversion errors.
- **"Wrong `Content-Type` is a JSON syntax error."** False. Usually 415 due to media type mismatch.
- **"Adding `Converter<String, T>` makes Jackson use it for JSON."** Not guaranteed; MVC converters and Jackson deserializers are separate mechanisms.
- **"`@RequestBody String` always validates JSON."** False; the string converter can accept the raw body directly as a String.
- **"An invalid `@ModelAttribute` form field always throws MethodArgumentTypeMismatchException."** False. Binding errors may be collected in `BindingResult` or throw an exception based on the method signature.
- **"To make debugging easier, return the full stack trace and request body."** Unsafe. Log internally in a controlled way, and return safe error codes and descriptions.
- **"Spring Boot always returns 422 for validation."** False. The default is typically 400; 422 is an explicit contract choice when appropriate.
- **"Servlet MVC exceptions are identical in WebFlux."** False. WebFlux uses reactive readers/codecs and handles exceptions according to its own stack.

## 12. Connection to Spring WebFlux

Spring WebFlux also accepts JSON bodies and converts path/query parameters, yet does not use the Servlet MVC `HttpMessageConverter` pipeline in all cases.

| Layer | Spring MVC | Spring WebFlux |
|---|---|---|
| Reading `@RequestBody` | `HttpMessageConverter` | `HttpMessageReader`/reactive codecs |
| Body decoding errors | Typically `HttpMessageNotReadableException` | Typically `ServerWebInputException` with codec/decoding cause |
| Body validation | Typically `MethodArgumentNotValidException` | `WebExchangeBindException` in many cases |
| Query/path conversion | MVC ConversionService/binder | Reactive controller argument resolvers and ConversionService |
| Error advice | MVC `@RestControllerAdvice`, MVC exception types | WebFlux advice/error handling with matching exception types |
| Problem Details property | `spring.mvc.problemdetails.enabled` | `spring.webflux.problemdetails.enabled` |

Do not copy an `@ExceptionHandler(HttpMessageNotReadableException.class)` from an MVC project into WebFlux and assume it handles all JSON decoding errors. In WebFlux, check `ServerWebInputException`, `DecodingException`, `WebExchangeBindException`, `WebExceptionHandler`, and the endpoint's specific reactive parameter types.

The demo deliberately uses Spring MVC to isolate the two target exceptions; do not add `spring-boot-starter-webflux` to the project unnecessarily.

## 13. Production API Checklist

1. **Standardize errors by input source:** keep JSON body, path/query/header, validation, Content-Type, and business rules distinct.
2. **Choose meaningful HTTP statuses:** 400 for invalid input by default, 415 for unsupported media types, 404 for missing resources, 409 for state conflicts, 500 for server errors. Never infer every case solely from exception class names.
3. **Design stable error codes:** `INVALID_JSON_BODY`, `INVALID_PARAMETER`, `MISSING_PARAMETER`, `VALIDATION_ERROR`, `UNSUPPORTED_MEDIA_TYPE`.
4. **Keep messages safe:** never expose raw bodies/secrets, stack traces, internal class paths, or SQL.
5. **Customize at the right layer:** Jackson/`HttpMessageConverter` for JSON, MVC `ConversionService` for query/path, Bean Validation for constraints, service layer for business rules.
6. **Test both JSON syntax and JSON mapping:** many test suites check only missing braces without testing wrong field types inside valid JSON.
7. **Test path/query conversions:** invalid numbers, invalid UUID/enum/date values, missing required params, required=false, and `Optional`.
8. **Test Content-Type and Accept:** verify 415/406 are not turned into 400 by an overly broad handler.
9. **Test `@Valid` and method validation:** per your Spring Framework version, cover both `MethodArgumentNotValidException` and `HandlerMethodValidationException` where applicable.
10. **Verify custom advice and Problem Details:** avoid handler conflicts, keep response contracts consistent, and avoid 500s caused by advice bugs.
11. **Check logs and trace IDs:** log internal causes under security policies; avoid logging full request bodies containing sensitive data.
12. **Audit when upgrading Boot/Framework:** imports, starters, Jackson major versions, exception behavior, and default formats can change.

**Conclusion:** to distinguish errors accurately, ask **where is the data coming from and which component processes it?** If from a **JSON body via `HttpMessageConverter`**, a read/deserialization failure is typically `HttpMessageNotReadableException`. If from **query/path/header via type conversion**, a conversion failure is typically `MethodArgumentTypeMismatchException`. Validation and media types are two separate categories; the API should represent each case cleanly and have tests proving it.

## Official References

- Spring Framework — `@RequestBody` and `HttpMessageConverter`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — Type Conversion for path/query/header: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — Validation and `MethodArgumentNotValidException`/`HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@ExceptionHandler`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — Error Responses / RFC 9457 Problem Details: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.2 — `MethodArgumentTypeMismatchException` API: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/method/annotation/MethodArgumentTypeMismatchException.html
- Spring Boot 3.5 — Servlet Web Applications and Error Handling: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework — WebFlux `@RequestBody` and validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html

