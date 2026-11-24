# Testing Binding, Validation, ProblemDetail, and ControllerAdvice in Spring MVC

## 1. Goals and the big picture

A proper HTTP API does not just return 200 for valid requests. It must **convert HTTP data into Java objects properly (binding)**, reject input violating constraints (**validation**), return consistent statuses and error structures (**ProblemDetail**), and handle errors centrally without leaking system internals (**@ControllerAdvice**).

Consider an order-creation endpoint accepting JSON with item code `sku` and `quantity`. Cases to test include: valid body, empty body, malformed JSON syntax, wrong Content-Type, whitespace-only `sku`, `quantity` less than 1, query parameter failing numeric conversion, path variable violating a constraint, and order not found.

This lesson uses **Spring MVC (Servlet)** with Spring Framework 6.1 / Spring Boot 3.3.x and Java 17. The focus is using **MockMvc** to exercise the MVC layer along with converters, data binding, Jakarta Bean Validation, exception resolvers, and advice; **no real HTTP port needs to be started** in slice tests.

After finishing, you will be able to:
1. Distinguish binding errors, conversion errors, and Bean Validation errors; know which exception will occur.
2. Use `@WebMvcTest`, `MockMvc`, `@Valid`, `@ModelAttribute`, `@RequestBody`, `@RequestParam`, and `@PathVariable` purposefully.
3. Write a `@RestControllerAdvice` extending `ResponseEntityExceptionHandler` to turn Spring MVC errors into standard `ProblemDetail` responses with field errors.
4. Verify status, `application/problem+json` header, JSON body, and that the controller **does not execute the business branch** when input is invalid.
5. Build a test suite covering both the happy path and validation/conversion/exception failures, while knowing what slice tests do not guarantee.

## 2. How does an HTTP request flow through Spring MVC?

~~~mermaid
flowchart TD
    A[HTTP request] --> B[DispatcherServlet and HandlerMapping]
    B --> C[Argument resolver and HttpMessageConverter]
    C -->|Syntactically valid JSON/form/query/path| D[Data binding and conversion]
    D -->|Has @Valid / constraint| E[Jakarta Bean Validation]
    E -->|PASS| F[Controller method]
    F --> G[Service / business result]
    G --> H[Response serialization]
    C -->|Unreadable JSON| I[Exception resolver]
    D -->|Conversion/required missing| I
    E -->|Validation FAIL| I
    F -->|Domain exception| I
    I --> J[ControllerAdvice / ResponseEntityExceptionHandler]
    J --> K[HTTP status + ProblemDetail JSON]
~~~

This is a conceptual flow. Spring MVC has multiple argument resolvers and exception resolvers, so some steps are nested; the diagram aims to distinguish **where errors originate**. If an error is caught and handled in the controller via `BindingResult`, it may not be routed to advice.

| Input source | Common annotation | How Spring reads it | Example error |
| --- | --- | --- | --- |
| JSON request body | `@RequestBody` | Jackson/HttpMessageConverter | Malformed JSON → `HttpMessageNotReadableException` |
| Query string | `@RequestParam` | Converter + binder | `page=abc` fails int conversion → `MethodArgumentTypeMismatchException` |
| Path | `@PathVariable` | URI template + Converter | `/orders/abc` fails long conversion |
| Form/query bound object | `@ModelAttribute` | DataBinder populates JavaBean/constructor binding | Wrong field type creates binding errors |
| Bean Validation on object | `@Valid` on DTO | Jakarta Validator (when dependency is present) | `@NotBlank`, `@Min` fail |
| Constraint directly on method parameter | `@Min`/`@NotBlank` | Built-in method validation since Spring 6.1 | `HandlerMethodValidationException` |

**Binding differs from validation**: JSON `{"quantity":"abc"}` cannot be decoded into an int, so there is no valid DTO yet to apply `@Min` as usual. By contrast, `{"quantity":0}` decodes into an int but fails the `@Min(1)` constraint.

## 3. DTO validation vs. method validation

### 3.1. Validating an object

Example DTO:

~~~java
public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) int quantity
) {}
~~~

Place `@Valid` on the controller parameter:

~~~java
@PostMapping
ResponseEntity<OrderResponse> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // Only reaches here if the request decoded and validation passed.
}
~~~

With Spring MVC, when `@Valid @RequestBody` is validated at the object level, it **typically throws `MethodArgumentNotValidException`** if no `Errors`/`BindingResult` follows the parameter and no direct constraints trigger method validation.

**Prerequisite:** the application must have `spring-boot-starter-validation` (Jakarta Validation provider, typically Hibernate Validator). Adding only `jakarta.validation.Valid` without an appropriate validator does not guarantee constraints are enforced.

With `@NotBlank`, null, empty, and whitespace-only strings are rejected. With `@Min(1)`, 0 or negative values are rejected. If a primitive `int` field is omitted, Java may receive default value 0 after deserialization depending on configuration, which `@Min` catches; however, to distinguish **omitted field** from **value 0**, use `Integer` combined with `@NotNull` and `@Min(1)`.

### 3.2. BindingResult alters the handling path

Another controller might write:

~~~java
@PostMapping("/preview")
ResponseEntity<?> preview(
        @Valid @RequestBody CreateOrderRequest request,
        BindingResult bindingResult) {
    if (bindingResult.hasErrors()) {
        return ResponseEntity.badRequest().body("Invalid preview");
    }
    return ResponseEntity.ok("Preview allowed");
}
~~~

This illustrative snippet belongs to a controller with `@RequestMapping`; it needs Java/Spring imports and the DTO from the earlier example. **BindingResult must immediately follow the argument whose errors are captured**. When handling locally, you build the response yourself; advice does not necessarily receive `MethodArgumentNotValidException` for this error. Do not return HTTP 200 for errors just to “return a body”; the status must reflect validity.

### 3.3. Direct validation on method parameters (Spring 6.1+)

~~~java
@GetMapping("/{id}")
OrderResponse getOrder(@PathVariable @Min(1) long id) {
    return service.find(id);
}
~~~

`@Min` placed directly on a method parameter requires **method validation**; Spring MVC 6.1 has built-in support, and input errors typically throw `HandlerMethodValidationException`. Adding class-level `@Validated` can switch to a different AOP method validation mechanism; do not arbitrarily add `@Validated` to the whole controller if the goal is to test this built-in mechanism.

| Scenario | Typical exception | Response to test |
| --- | --- | --- |
| `@Valid @RequestBody` with invalid `@NotBlank` field | `MethodArgumentNotValidException` | 400 and field errors |
| `@Valid @ModelAttribute` with invalid `@Min` field | `MethodArgumentNotValidException` | 400 and field errors |
| `@PathVariable @Min(1)` receives 0 | `HandlerMethodValidationException` | 400 (with input violation) |
| `@RequestParam int page` receives `abc` | `MethodArgumentTypeMismatchException` / type mismatch group | 400 |
| Missing required `@RequestParam` | `MissingServletRequestParameterException` | 400 |
| Malformed JSON or incomplete JSON mapping | `HttpMessageNotReadableException` | 400 |
| `Content-Type: text/plain` for JSON-consuming endpoint | `HttpMediaTypeNotSupportedException` | 415 |
| Business resource does not exist | Custom `OrderNotFoundException` | 404 |
| Client does not accept response media type | `HttpMediaTypeNotAcceptableException` | 406 |

Final statuses/mappings also depend on exception handlers and Spring configuration. Do not rely blindly on a static table and skip testing **the application's actual responses**.

## 4. ProblemDetail: testing an error contract instead of ad-hoc messages

Spring Framework 6 supports `org.springframework.http.ProblemDetail` following **RFC 9457 Problem Details for HTTP APIs**. Typical JSON body:

~~~json
{
  "type": "about:blank",
  "title": "Invalid request",
  "status": 400,
  "detail": "Request validation failed",
  "instance": "/api/orders",
  "errors": {
    "quantity": "must be greater than or equal to 1",
    "sku": "must not be blank"
  }
}
~~~

`type`, `title`, `status`, `detail`, and `instance` are standard members; `errors` is an application extension. The example shows the **expected shape**; validator messages and locale can vary. When writing tests, assert exact messages only when the message is part of a fixed API contract, avoiding coupling to arbitrary framework text.

- **type:** URI identifying the problem type; if unset, usually `about:blank`.
- **title:** short, categorizing error name.
- **status:** numeric HTTP status in the body; must match the status line.
- **detail:** safe explanation for callers, containing no SQL, stack traces, or internal details.
- **instance:** URI of the failed request; Spring can populate the current path if the app does not set it.
- **extensions:** add error codes, field errors, or controlled correlation IDs. Jackson configured by Spring usually serializes `ProblemDetail.setProperty("errors", ...)` at the **top-level JSON**, not necessarily nested under `properties`.

When `ProblemDetail` is returned from `@ExceptionHandler` or a controller, Spring MVC prefers media type `application/problem+json` during content negotiation. Use `contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)` in MockMvc to tolerate an inconsequential charset parameter.

**Do not assume “all Spring Boot errors automatically return ProblemDetail”**. There are two options:
1. Spring Boot has `spring.mvc.problemdetails.enabled=true` to configure framework error handling with ProblemDetail.
2. The application declares a `@RestControllerAdvice` extending `ResponseEntityExceptionHandler` to handle MVC errors and extend responses explicitly.

The complete example in this lesson uses **option 2**, without needing to enable the property. Avoid configuring multiple advice classes with overlapping responsibilities without defining `@Order`. If Boot's ProblemDetail auto-configuration is enabled, consider the precedence of custom advice relative to the auto-configured handler.

### 4.1. What must not be leaked through errors

Never return `exception.getMessage()` directly for all 500 exceptions: messages may contain SQL, file paths, class/package names, internal hosts, or tokens. Field errors should contain only **field names the client is allowed to see** and vetted safe messages. When adding `traceId`, use a correlation ID generated by your observability system; do not allow clients to overwrite trusted fields freely.

Do not return 500 for 400 input errors, nor turn every exception into 400. Error classification affects retry behavior, UX, caching, and operations.

## 5. @RestControllerAdvice and ResponseEntityExceptionHandler

`@ControllerAdvice` centralizes shared handling across controllers, including `@ExceptionHandler`, `@InitBinder`, and `@ModelAttribute`. `@RestControllerAdvice` is the `@ControllerAdvice` equivalent with response-body semantics, convenient for JSON APIs.

`ResponseEntityExceptionHandler` provides built-in handlers for many Spring MVC exceptions (unreadable body, wrong media type, binding/validation, unsupported method, etc.). When extending it:
- **Override protected methods** such as `handleMethodArgumentNotValid` and `handleHandlerMethodValidationException` to customize framework errors.
- Add `@ExceptionHandler` **only for your own business exceptions** like OrderNotFoundException.
- Avoid adding `@ExceptionHandler(MethodArgumentNotValidException.class)` alongside a ResponseEntityExceptionHandler subclass, because the base handler already registers that exception group; competing mappings can cause an ambiguous exception mapping error.
- Return `ResponseEntity` with consistent status and body; use `handleExceptionInternal` to preserve the base class's centralized handling flow.
- Do not add a catch-all `@ExceptionHandler(Exception.class)` without clear requirements and a logging/500 plan, as it can mask programming bugs, framework errors, and proper statuses.

Example override signature for **Spring Framework 6.1**:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        status, "Request validation failed");
    problem.setTitle("Invalid request");
    return handleExceptionInternal(ex, problem, headers, status, request);
}
~~~

`HttpStatusCode` (no longer `HttpStatus` in that parameter position) is critical to compile cleanly on Spring 6.1. This is an integration snippet; the complete class appears in the example below.

## 6. Complete practice project: Spring MVC + ProblemDetail + MockMvc

The demo provides a POST endpoint to create an order, GET to look up an order, GET search using ModelAttribute, and GET quote using RequestParam. There is no database to keep the exercise focused on request mapping and HTTP errors. The application uses Spring Boot **3.3.13**, Java 17+, Maven; the validation dependency is declared explicitly.

### 6.1. Structure

~~~text
mvc-errors-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── MvcErrorsApplication.java
    │   ├── OrderController.java
    │   └── ApiProblemAdvice.java
    └── test/java/demo/
        └── OrderControllerWebTest.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>mvc-errors-demo</artifactId>
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
~~~

The three dependencies provide: Spring MVC + Jackson; Jakarta Bean Validation + Hibernate Validator; JUnit 5/MockMvc/assertions. The example does not install Spring Security, because an authentication/CSRF FilterChain would change statuses and test setup; projects with Security must test real security rather than disabling filters by default.

### 6.3. MvcErrorsApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcErrorsApplication.class, args);
    }
}
~~~

### 6.4. OrderController.java

~~~java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record CreateOrderRequest(
        @NotBlank String sku,
        @Min(1) int quantity
    ) {}

    public record OrderResponse(long id, String sku, int quantity) {}

    public static class SearchCriteria {
        @Min(1)
        private Integer page;

        public Integer getPage() {
            return page;
        }

        public void setPage(Integer page) {
            this.page = page;
        }
    }

    public static class OrderNotFoundException extends RuntimeException {
        public OrderNotFoundException(long id) {
            super("Order " + id + " was not found");
        }
    }

    @PostMapping(consumes = "application/json")
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest input) {
        OrderResponse output = new OrderResponse(
            42L, input.sku(), input.quantity());
        return ResponseEntity.status(HttpStatus.CREATED).body(output);
    }

    @GetMapping("/{id}")
    public OrderResponse find(@PathVariable @Min(1) long id) {
        if (id != 42L) {
            throw new OrderNotFoundException(id);
        }
        return new OrderResponse(42L, "A-7", 2);
    }

    @GetMapping("/search")
    public String search(@Valid @ModelAttribute SearchCriteria filter) {
        return "page=" + filter.getPage();
    }

    @GetMapping("/quote")
    public String quote(@RequestParam int quantity) {
        return "quantity=" + quantity;
    }
}
~~~

**Why it is written this way intentionally:**
- `create` demonstrates `@RequestBody` + Jackson + Bean Validation `@NotBlank`/`@Min`, returning HTTP 201 on success.
- `find` puts `@Min` directly on the method argument to illustrate `HandlerMethodValidationException`; **no `@Validated` is placed on the class**, avoiding changing Spring MVC 6.1's built-in mechanism.
- `search` binds query `page` into a bean via `@ModelAttribute`; `page=0` binds to Integer yet fails `@Min(1)`.
- `quote` takes `int`, used to test conversion errors like `quantity=abc` or missing parameter.
- OrderNotFoundException represents a business error. Keeping responses fixed without database persistence keeps tests independent of persistence; a real app calls a service, while MVC tests can mock that service separately.

**GET mapping note:** `/search` and `/quote` are literal paths, and Spring prioritizes literal paths over `/{id}`. `/api/orders/abc` selects pattern `/{id}` but cannot bind to long, producing a conversion error, unlike `/api/orders/999` which parses to long and leads to domain 404.

### 6.5. ApiProblemAdvice.java

~~~java
package demo;

import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import demo.OrderController.OrderNotFoundException;

@RestControllerAdvice
public class ApiProblemAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status, "Request validation failed");
        problem.setTitle("Invalid request");

        Map<String, String> fieldErrors = new TreeMap<>();
        ex.getBindingResult().getFieldErrors().forEach(error ->
            fieldErrors.putIfAbsent(
                error.getField(),
                error.getDefaultMessage() == null
                    ? "Invalid value" : error.getDefaultMessage()));

        problem.setProperty("errors", fieldErrors);
        return handleExceptionInternal(
            ex, problem, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            status, "Method parameter validation failed");
        problem.setTitle("Invalid parameter");

        return handleExceptionInternal(
            ex, problem, headers, status, request);
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleOrderNotFound(
            OrderNotFoundException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND, "Requested order does not exist");
        problem.setTitle("Order not found");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
~~~

This class is error handling configuration **tailored for Spring 6.1**. `ResponseEntityExceptionHandler` continues handling unreadable JSON, missing query parameters, wrong Content-Type, and other built-in errors we did not override. `@RestControllerAdvice` is component-scanned in package demo when running the app. The custom 404 exception sets a machine-readable error code `ORDER_NOT_FOUND`; there is no need to expose an exception message containing a real ID if that information should not be disclosed.

`TreeMap` keeps field name ordering deterministic for human readability, yet **JSON tests should not depend on field order**. `putIfAbsent` picks the first message per field; a single field can violate multiple constraints. Systems needing detailed UI feedback can return a **list of errors per field** instead of a single string, provided the contract is defined up front. Spring's Jackson mix-in renders extensions `errors` and `code` at the top level of JSON.

### 6.6. OrderControllerWebTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
@Import(ApiProblemAdvice.class)
class OrderControllerWebTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validJsonReturns201AndMappedDto() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"A-7","quantity":2}
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$.sku").value("A-7"))
            .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void invalidBodyReturnsProblemWithFieldErrors() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"   ","quantity":0}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.title").value("Invalid request"))
            .andExpect(jsonPath("$.errors.sku").exists())
            .andExpect(jsonPath("$.errors.quantity").exists());
    }

    @Test
    void malformedJsonIsRejectedBeforeBeanValidation() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{broken json"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void unsupportedContentTypeReturns415() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.TEXT_PLAIN)
                .content("sku=A-7"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void modelAttributeValidationReturns400() throws Exception {
        mvc.perform(get("/api/orders/search")
                .param("page", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title").value("Invalid request"))
            .andExpect(jsonPath("$.errors.page").exists());
    }

    @Test
    void validQueryBindsToModelAttribute() throws Exception {
        mvc.perform(get("/api/orders/search")
                .param("page", "2"))
            .andExpect(status().isOk())
            .andExpect(content().string("page=2"));
    }

    @Test
    void malformedQueryNumberReturns400() throws Exception {
        mvc.perform(get("/api/orders/quote")
                .param("quantity", "abc"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredQueryReturns400() throws Exception {
        mvc.perform(get("/api/orders/quote"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void directMethodConstraintUsesMethodValidation() throws Exception {
        mvc.perform(get("/api/orders/0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.title").value("Invalid parameter"))
            .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void notFoundDomainErrorReturns404Problem() throws Exception {
        mvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.status").value(404))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void existingResourceReturnsSuccessfulJson() throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sku").value("A-7"));
    }
}
~~~

Run in directory `mvc-errors-demo`:

~~~bash
mvn -q test
~~~

The codebase provides **11 JUnit @Test methods**. When passing, Maven returns exit code 0 and Surefire generates reports in `target/surefire-reports/`. `-q` mode may suppress summary lines on stdout; **do not assume tests PASS without running them on a real machine**. When a test fails, read the stack trace along with MockMvc's resolved exception/response; do not tweak assertions merely to hide unexpected behavior.

Run the real server:

~~~bash
mvn spring-boot:run
~~~

Sample request commands:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-7","quantity":2}'

curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":" ","quantity":0}'

curl -i http://localhost:8080/api/orders/999
~~~

With this demo, the first command's response is expected to be **HTTP 201** with a body like (ignoring headers, timestamp, and whitespace):

~~~json
{"id":42,"sku":"A-7","quantity":2}
~~~

The second command is expected to return **HTTP 400** and a ProblemDetail containing `title: "Invalid request"` along with two field errors for sku/quantity. The third command is expected to return **HTTP 404** and `code: "ORDER_NOT_FOUND"`. Fields like `detail` or validation messages may be localized depending on validator configuration; tests do not lock down that text unnecessarily.

**On runnability:** this is a standalone sample Maven project designed for Spring 6.1 APIs. Writing the tests in the lesson helps readers run verification on their own machines; this lesson does not claim test execution evidence outside the described environment.

## 7. Why use @WebMvcTest and when must you run full tests?

`@WebMvcTest(OrderController.class)` loads an MVC slice: controller, mapping/argument resolvers, converters, MVC configuration, validation, and related advice. `@Import(ApiProblemAdvice.class)` makes explicit that the API's own advice is used during the test (even if scanning changes). MockMvc creates requests/responses at the simulated Servlet layer without binding a TCP port.

| Testing approach | What is checked | Limitations |
| --- | --- | --- |
| Unit test calling `controller.create(dto)` directly | Java logic inside the method | Does not run JSON binding, validation, mapping, or advice |
| MockMvc `standaloneSetup` | Minimal MVC mapping, fast tests, manual advice registration | Must configure converters/validators/resolvers manually; easily drifts from production |
| `@WebMvcTest` + MockMvc | MVC slice, validation, Jackson, advice, handler mappings | Does not load all services/databases/infrastructure |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | Full app config with MockMvc | Heavier, still does not prove sockets/TLS/proxies |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` + HTTP client | Full app over local TCP, real HTTP serialization | Resource-intensive, still depends on how infra is mocked and test config |
| Contract/E2E | Producer-consumer compatibility and real deployment | Slow, requires test data and environment management |

If a controller injects a service, `@WebMvcTest` **does not auto-load** all `@Service`, repository, or business beans. With Spring Boot 3.3 you can use `@MockBean` to supply dependencies in a slice test or `@Import` necessary test configs; note that mock annotation APIs change in newer Boot branches, so avoid using an annotation not belonging to your project version.

When using Spring Security, `@WebMvcTest` can load the FilterChain. POST requests may get 403 due to CSRF **before** reaching the controller, and 401/403 may come from authentication. Write proper security tests with `spring-security-test` using users/CSRF as needed; do not disable security arbitrarily and conclude that the production endpoint handles validation fine.

## 8. Deeper testing of data binding and validation

### 8.1. Separating three error sources

Suppose a POST endpoint accepts int quantity:
- `{"quantity":2}`: valid JSON, binding OK, `@Min` OK.
- `{"quantity":0}`: valid JSON, binding OK, Bean Validation FAIL.
- `{"quantity":"not-a-number"}`: Jackson/type conversion FAILS before validation.
- `{"quantity":null}`: behavior depends on primitive/wrapper type and Jackson configuration; test your contract instead of assuming.
- Empty body with `@RequestBody(required=true)`: usually `HttpMessageNotReadableException` leading to 400.
- Missing Content-Type or `text/plain`: may cause 415 due to `consumes="application/json"`; check both body and request headers.

Two errors both having status 400 **do not mean the same category**. For public APIs, use machine-readable codes distinguishing `VALIDATION_FAILED`, `INVALID_JSON`, and `INVALID_PARAMETER` if clients genuinely need them; do not infer codes from English text in `detail`.

### 8.2. Errors in @ModelAttribute can be binding or validation

With `@Valid @ModelAttribute SearchCriteria`:
- `?page=2`: String "2" converts to Integer 2, passes `@Min(1)`.
- `?page=0`: converts to Integer 0, fails validation.
- `?page=abc`: conversion to Integer fails; the binder records a field error, which depending on signature exception resolution can become `MethodArgumentNotValidException` with BindingResult.
- `?page=`: may bind to null when using `Integer`, and `@Min` **does not replace `@NotNull`**; if page is required, add `@NotNull`.
- Unknown query parameters: if there is no matching property, they are usually not bound, though this is not a sufficient security policy for every DTO.

For mutable objects, **avoid mass assignment**: never bind directly onto an entity containing fields like `admin`, `price`, `role`, or `ownerId` from untrusted input. Use dedicated DTOs, constructor binding, or restrict `DataBinder.setAllowedFields(...)` in `@InitBinder` where appropriate. DTO unit tests cannot catch this issue unless the MVC binder runs on real requests.

### 8.3. Validation groups and custom constraints

`@Validated(SomeGroup.class)` can select a Bean Validation group different from default `@Valid` when applied to an object parameter. If an application has POST create and PATCH update with different field rules, test **each group** and missing/null cases separately. For custom `ConstraintValidator`, test at least:
1. Valid and invalid values;
2. Null/blank per policy;
3. Unicode, numeric boundaries, length;
4. Message/code and locale if part of the API contract.

**Bean Validation cannot replace stateful business checks**: unique SKU in the DB, order modification permissions, balances, or inventory require service/database/race-condition tests. Avoid stuffing DB queries into a ConstraintValidator, which creates hidden dependencies during request binding.

### 8.4. Asserting that business side effects did not happen

When a controller injects a service, invalid-input tests should verify the service **was not called**. Integration snippet using Mockito:

~~~java
mvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"sku\":\" \",\"quantity\":0}"))
    .andExpect(status().isBadRequest());

verifyNoInteractions(orderService);
~~~

This is not a standalone snippet; `orderService` is a Mockito mock injected into the controller and requires static import of Mockito.verifyNoInteractions. For demos without a service, check only status/body as in the complete example. Ensuring the service is not invoked is a safety criterion when validation guards real data mutations.

## 9. Testing a stable ProblemDetail contract

A good assertion set separates the **schema contract** from accidental details:
- Verify HTTP status and body status match;
- Content-Type header compatible with `application/problem+json`;
- `type` (when defined by the app) and domain error `code` are stable;
- `title`/field errors exist with the right keys/shape;
- `instance` matches the request path without sensitive query parameters;
- No stack traces, package names, credentials, or SQL in the response;
- No dependency on JSON property order or field-error ordering;
- Test with another locale if messages are internationalized.

If a public API has published a specific `type` URI like `https://api.example.test/problems/validation-error`, test that exact URI and document it long-term. If none is published, `about:blank` is a valid default; **do not invent a fake URI** just to populate all five fields.

### Localized messages

Spring MVC uses `MessageSource` to resolve validation messages and ProblemDetail detail/title. Test locales via `Accept-Language` if supported by the app. Avoid asserting exact default messages like "must not be blank" if they can change across Hibernate Validator versions, Spring versions, or locales; instead check field names and error codes. If a real UI relies on message strings, **own and version those messages** rather than letting framework internals decide them.

### Interaction of multiple ControllerAdvices

An application may have advice dedicated to REST APIs and another for HTML MVC. `@RestControllerAdvice(basePackages=...)`, `assignableTypes`, `annotations`, and `@Order` scope/prioritize them. Test across multiple controllers to ensure HTML responses do not accidentally receive JSON ProblemDetail, and one module's domain errors are not intercepted prematurely by another module's catch-all advice.

In Spring Boot when `spring.mvc.problemdetails.enabled=true` is enabled, the auto-configured handler may also handle framework exceptions. Design overrides and ordering explicitly rather than copying a `@RestControllerAdvice` and assuming it is always chosen first.

## 10. Common mistakes when writing MockMvc tests

1. **Calling the controller directly only:** does not test Servlet binding, Jackson, or advice; add MockMvc requests with real HTTP headers/bodies.
2. **Forgetting spring-boot-starter-validation:** `@NotBlank`/`@Min` appear in code without a validator. Add an invalid input test and verify it returns 400.
3. **Confusing conversion with validation:** testing `quantity=abc` while expecting the same field error as `quantity=0`; verify the exact exception path.
4. **Class-level @Validated changing the method validation path:** avoid it if you intend to test Spring MVC 6.1's built-in HandlerMethodValidationException.
5. **Writing @ExceptionHandler overlapping ResponseEntityExceptionHandler:** can cause ambiguous exception mapping; override the right protected handler instead.
6. **Asserting every character of default messages:** fragile across locales/validator versions; test contracts you own.
7. **Forgetting Content-Type or Accept:** an endpoint with `consumes=application/json` may return 415 before body decoding.
8. **Skipping empty and malformed body cases:** testing only type-valid validation misses an important group of 400s.
9. **Returning HTTP 200 with `{"success":false}` for validation:** misleads clients, caching, and metrics; return 400/422 per the API contract.
10. **Wrapping every exception into HTTP 500 with raw messages:** leaks system internals; classify errors and log internal details separately.
11. **Using @WebMvcTest and assuming real database/transactions were tested:** slice tests cover MVC only; add service/persistence/integration tests based on risk.
12. **Disabling filters to bypass 403 errors:** hides the real security path; test authentication/CSRF purposefully.
13. **Mocking all MVC converters:** loses real Jackson/config behavior and creates false positives; prefer slices using production-like configuration.
14. **Assuming every 400 returns the exact same schema:** MissingServletRequestParameterException, malformed JSON, and method validation may hit different handlers; establish a unified API contract if needed and test each type.
15. **Not checking status-body consistency:** body `status:400` on an HTTP 200 line is a broken contract.
16. **Asserting only the exception class:** inspect the response JSON and content type that real clients read, because advice can map things wrong even when the exception is right.

## 11. Recommended test matrix for a REST controller

| Input/path | Expected | Why it is needed |
| --- | --- | --- |
| Complete, valid JSON body | 201/200 with response DTO | Proves mapping and serializer |
| JSON missing required field | 400 field errors | Blocks missing data |
| Blank, negative, or out-of-bounds field | 400 field errors | Proves Bean Validation runs |
| Syntactically broken JSON | 400 ProblemDetail | Proves parsing errors are handled |
| JSON field with wrong type | 400, business service not called | Blocks invalid conversion |
| Unsupported Content-Type | 415 | Proves media type contract |
| Query parameter fails type conversion | 400 | Binding errors outside body |
| Missing required query parameter | 400 | Rejects absent values |
| Invalid `@ModelAttribute` | 400 field errors | Proves binder + validator |
| `@PathVariable` violating `@Min` | 400 | Proves Spring 6.1 method validation |
| Non-existent resource | 404 with business code | Proves custom ControllerAdvice |
| Unexpected service error | 500 response without stack trace | Proves error boundary |
| Unauthenticated/unauthorized request | 401/403 if security enabled | Proves filters/advice do not break security |
| Incompatible Accept | 406 when contract applies | Proves content negotiation |
| Locale vi/en | Messages in right language if supported | Reduces UI/i18n risks |

Choose tests suited to the actual endpoint; the goal is not inflating assertion count, but **covering distinct mechanisms** and protecting the contract clients depend on.

## 12. Workflow when a test fails

1. Inspect the generated HTTP request (method, URL, Content-Type, Accept, JSON, query). 415 errors usually happen before validation.
2. Read MockMvc's **resolved exception**; distinguish HttpMessageNotReadableException, MethodArgumentNotValidException, HandlerMethodValidationException, and business exceptions.
3. Check which advice was component-scanned/imported, `@Order` precedence, and whether duplicate mappings exist.
4. Check validation/provider dependencies, Bean Validation groups, annotations directly on method parameters, and BindingResult placement.
5. Inspect the response HTTP status, ProblemDetail body, and content type; negotiation errors can alter the body from expectations.
6. Only after identifying the root cause should you fix code or tests; never simply change expected 400 to 500 to make a test green.
7. When changing an API contract, re-test consumer expectations, especially keys `errors`, `code`, `type`, nullable fields, and semantics.

## 13. Conclusion

A reliable Spring MVC test suite must cover **HTTP binding → conversion → validation → controller → exception resolver/ControllerAdvice → ProblemDetail response**. `@WebMvcTest` + MockMvc is lightweight enough to verify most MVC-layer mechanisms, while real service/database/security/transport behavior needs corresponding tests.

`ProblemDetail` standardizes error payloads, yet does not fix API design on its own: the application must remain consistent on statuses, field errors, business codes, information security, and advice ordering. Particularly critical since Spring 6.1 is handling **both `MethodArgumentNotValidException` and `HandlerMethodValidationException`**, because the method signature determines which validation layer is triggered.

## References

- Spring Boot 3.3 — Testing Spring Boot Applications / @WebMvcTest: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 API — @WebMvcTest: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html
- Spring Framework — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — Error Responses / RFC 9457 ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework 6.1 — ResponseEntityExceptionHandler Javadoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework 6.1 — ProblemDetail Javadoc: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/ProblemDetail.html
- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
