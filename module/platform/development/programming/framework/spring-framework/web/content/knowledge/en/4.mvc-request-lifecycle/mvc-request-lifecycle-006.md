# HandlerExceptionResolver and Exception Handling Flow in Spring MVC

## 1. Goals and Position of Error Handling

In Spring Web MVC, a valid request can fail at many stages: handler lookup, parameter conversion, reading JSON, validation, service calls, controller execution, writing the response, or rendering a view. **HandlerExceptionResolver** is Spring MVC's extension point for turning exceptions caught by `DispatcherServlet` into meaningful HTTP responses.

This lesson answers:

- Which steps does an exception pass through before reaching `HandlerExceptionResolver`?
- When is an `@ExceptionHandler` inside a controller invoked versus an `@ControllerAdvice`?
- How do `ExceptionHandlerExceptionResolver`, `ResponseStatusExceptionResolver`, and `DefaultHandlerExceptionResolver` differ?
- What do `null`, an empty `ModelAndView`, or a `ModelAndView` with a view mean as return values?
- How do you build consistent REST API errors with `ResponseEntity`/`ProblemDetail` and test exact HTTP statuses and bodies?
- Which exceptions **do not** go through the MVC resolver chain, or occur after the HTTP response has already been sent?

**Scope:** Spring Framework 6.x / Spring Boot 3.x, Java 17+, Spring MVC (Servlet) web stack. WebFlux is a different stack using `WebExceptionHandler` and corresponding reactive error-handling mechanisms.

## 2. Where Exceptions Arise in the MVC Flow

The diagram below depicts errors occurring **within the scope of a request being processed by `DispatcherServlet`**:

```text
HTTP client
   |
   v
Servlet container (Tomcat)
   |
   v
Servlet Filter chain
   |
   v
DispatcherServlet
   |
   +--> HandlerMapping        --- handler/mapping lookup error?
   |
   +--> HandlerAdapter
   |      |
   |      +--> argument resolver / binding / validation --- 400 error?
   |      |
   |      +--> @Controller -> service/repository -------- business error?
   |      |
   |      +--> return value / message converter --------- serialization error?
   |
   +-- exception caught by DispatcherServlet inside processing block
          |
          v
   HandlerExceptionResolver list (by order)
          |
          +--> resolver 1: can handle? -> response/view
          +--> resolver 2: can handle? -> response/view
          +--> resolver 3: can handle? -> response/view
          |
          +--> no resolver handles it -> exception propagates out
                    |
                    v
            Servlet container / error dispatch
```

When processing inside `DispatcherServlet` throws an error, the Servlet tries the registered `HandlerExceptionResolver` instances. A resolver can set the HTTP status, headers, and body, return an error view, or let the next resolver try.

**Not every exception in the entire process enters here.** For example, a filter positioned before `DispatcherServlet` throwing an error before invoking the servlet, errors during application startup, or background errors in a scheduler/`@Async` outside an MVC request require different mechanisms. This is the first boundary for accurate diagnosis.

## 3. Contract of HandlerExceptionResolver

The key interface resides at `org.springframework.web.servlet.HandlerExceptionResolver`. Its core method has the signature:

```java
ModelAndView resolveException(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler,
        Exception ex
);
```

This is an **illustrative API signature**, not a standalone Java program. `handler` may be whatever handler information the framework identified; do not assume it is always a resolved controller method.

The return value has three distinct meanings:

| Return value | Meaning |
| --- | --- |
| `null` | This resolver **did not resolve the exception**; `DispatcherServlet` tries the next resolver. |
| Empty `new ModelAndView()` | The exception **has been handled**, with no MVC view rendering needed; e.g., the resolver already wrote status/body directly. |
| `ModelAndView` with view and model | The exception **has been handled** by rendering an error view, common in HTML-returning MVC. |

**Common mental error:** `null` does not mean "return an empty response"; it means *let another resolver try*. Conversely, an empty `ModelAndView` tells the framework not to probe further resolvers.

The resolver chain is ordered (`Ordered`/`@Order` or MVC configuration). **The first resolver returning a non-`null` result determines how it is handled.** Therefore, writing a custom resolver catching all `Exception`s at too high a priority can accidentally hijack handling from `@ExceptionHandler` and default resolvers.

## 4. The Three Most Important Built-In Resolvers

Under standard MVC configuration, Spring registers default resolvers; actual configuration typically places them in `HandlerExceptionResolverComposite`, commonly in this order:

| Resolver | Responsibility | Example |
| --- | --- | --- |
| **`ExceptionHandlerExceptionResolver`** | Finds and invokes `@ExceptionHandler` methods in controllers or controller advice | Turns `ProductNotFoundException` into a 404 JSON error. |
| **`ResponseStatusExceptionResolver`** | Maps `@ResponseStatus` and `ResponseStatusException` to HTTP status / reason | An exception annotated with `@ResponseStatus(HttpStatus.NOT_FOUND)`. |
| **`DefaultHandlerExceptionResolver`** | Handles standard Spring MVC exceptions and maps HTTP status/headers per Servlet behavior | Wrong HTTP method (405), missing param, unreadable body, etc. |

Additionally, `SimpleMappingExceptionResolver` can map exception types to error view names for HTML rendering in traditional MVC apps; it is not necessarily the best fit for REST JSON APIs.

**This order does not mean "every exception is processed by all three classes in turn."** If the first resolver handles it, remaining resolvers are not consulted. If an application defines custom resolvers or customizes MVC config, inspect the exact runtime order.

### 4.1. ExceptionHandlerExceptionResolver

This is the engine behind `@ExceptionHandler`. It finds a matching handler method based on exception type, local controller declarations, applicable advice, and advice ordering. The method can return `ResponseEntity`, `ProblemDetail`, a body object, `ModelAndView`, a view name, and other valid MVC return types.

It is the standard choice when turning **business errors** into a stable HTTP contract: status, error code, safe message, correlation ID, and appropriate headers.

### 4.2. ResponseStatusExceptionResolver

This resolver interprets cases such as:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class BookNotFoundException extends RuntimeException {
}
```

Or throwing `ResponseStatusException` at a processing point:

```java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Book not found"
);
```

Both snippets are **illustrative code placed in an application that has imported Spring HTTP/web classes**. They make HTTP status intent clear quickly, yet do not by themselves guarantee a uniform JSON error body across every configuration/container.

If a matching `@ExceptionHandler` catches the exception first, that handler method can decide the response instead of the status resolver. Do not assume `@ResponseStatus` always takes absolute precedence.

### 4.3. DefaultHandlerExceptionResolver

Spring MVC throws protocol/mapping-specific exceptions, such as:

- `HttpRequestMethodNotSupportedException` when an HTTP method is unsupported; typically **405 Method Not Allowed**, possibly with an `Allow` header.
- `HttpMediaTypeNotSupportedException` when a request sends an incompatible `Content-Type`; typically **415 Unsupported Media Type**.
- `HttpMediaTypeNotAcceptableException` when a representation matching `Accept` cannot be produced; typically **406 Not Acceptable**.
- `MissingServletRequestParameterException` if a `@RequestParam(required=true)` is missing; typically **400 Bad Request**.
- `MethodArgumentTypeMismatchException` or related type-conversion errors; typically leads to **400**, though the exact body depends on handler/advice/config.
- `HttpMessageNotReadableException` when JSON cannot be parsed; typically **400 Bad Request**.

Many framework errors also flow through `ResponseEntityExceptionHandler` or `ErrorResponse` to produce detailed HTTP content. At runtime, which resolver takes precedence can change the response body, yet **the right HTTP status does not automatically imply a standardized JSON body**. In some cases the resolver only sets the status or calls `sendError`, and the container/Boot routes to `/error`.

## 5. @ExceptionHandler Inside a Controller: Local Scope

A controller can declare `@ExceptionHandler` to handle its own exceptions:

```java
@RestController
@RequestMapping("/api/invoices")
class InvoiceController {

    @GetMapping("/{id}")
    String byId(@PathVariable long id) {
        if (id == 9) {
            throw new IllegalArgumentException("Invalid invoice ID");
        }
        return "invoice-" + id;
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> onInvalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body(ex.getMessage());
    }
}
```

This is an **illustrative controller snippet**; it needs imports for `@RestController`, `@RequestMapping`, `@GetMapping`, `@PathVariable`, `@ExceptionHandler`, and `ResponseEntity` from Spring. For `GET /api/invoices/9`, the response body is the error message and the status is 400.

Pros: controller-specific rules sit close to the controller. Cons: repeating the same error response across many controllers leads to inconsistent, hard-to-maintain code. When multiple controllers share the same JSON error contract, move shared rules to `@RestControllerAdvice`.

### Local vs. Global Precedence

When the same exception has a matching handler both inside the controller and in an `@ControllerAdvice` applicable to that controller, **the local handler takes precedence**. Global advice is considered only when no matching local handler exists.

Within a single controller/advice, exception type specificity and matching on causes (`cause`) affect method selection. **Do not** create two ambiguous `@ExceptionHandler` methods for the same exception in one advice: Spring may report ambiguity when initializing the resolver.

## 6. @ControllerAdvice and @RestControllerAdvice

`@ControllerAdvice` is a Spring component containing logic applied across multiple controllers, including `@ExceptionHandler`. `@RestControllerAdvice` is equivalent to `@ControllerAdvice` combined with `@ResponseBody`: returned objects are serialized into the HTTP body rather than treated as view names.

| Annotation / usage | Scope | Response form |
| --- | --- | --- |
| `@ExceptionHandler` in `@Controller` | Current controller | View, body, or `ResponseEntity` per signature. |
| `@ControllerAdvice` + `@ExceptionHandler` | Selected controllers | Suitable for HTML views, or response bodies with `@ResponseBody`/`ResponseEntity`. |
| `@RestControllerAdvice` + `@ExceptionHandler` | Selected REST controllers | Conveniently returns error objects/JSON. |
| `ResponseEntityExceptionHandler` | Base class used in advice | Already handles Spring MVC exception group; provides override hooks to unify responses. |

You can narrow advice scope with attributes like `basePackages`, `basePackageClasses`, `annotations`, and `assignableTypes`. Do not create a catch-all advice that catches every exception and turns all errors into 200 or 400.

### Multiple ControllerAdvice Beans and Ordering

Spring orders controller advice by `Ordered`/`@Order`. Higher-priority advice is evaluated first. Within **the same advice**, a root exception match typically takes precedence over a cause match; however, **a cause match in higher-priority advice** can beat a root match in lower-priority advice.

An easy-to-follow example:

- Advice A has `@Order(1)`, catching `IllegalArgumentException` inside the cause chain.
- Advice B has `@Order(10)`, catching a more specific outermost exception.
- When A applies and finds a matching handler, A may be used before B even though B matches the root exception.

Therefore, keep business error mappings **specific** within advice with clear scope and ordering; avoid multiple high-priority advice classes catching `Exception.class`.

## 7. ProblemDetail: An Explicit HTTP Error Contract

Rather than returning arbitrary error strings or a `Map` with unstable keys, Spring Framework 6 supports `ProblemDetail` following **RFC 9457** (Problem Details for HTTP APIs).

A problem response contains standard fields:

| Field | Meaning |
| --- | --- |
| `type` | URI identifying the problem type; defaults may be `about:blank`. |
| `title` | Short summary title of the problem type. |
| `status` | Corresponding HTTP status code. |
| `detail` | Brief explanation of the specific occurrence. |
| `instance` | URI identifying the request/problem instance when provided or derived. |
| Extensions like `code` | Application-specific error code for stable client handling. |

The typical media type is `application/problem+json`. The JSON may include `instance` or additional extensions depending on how the controller/converter constructs the response. Clients should rely on **HTTP status + stable error code**, not parse prose in `detail`.

Illustrative error response example:

```json
{
  "type": "about:blank",
  "title": "Product not found",
  "status": 404,
  "detail": "Product 42 not found",
  "code": "PRODUCT_NOT_FOUND"
}
```

**Never expose stack traces, connection strings, filesystem paths, internal SQL, or private data in the `detail` of a 500 error.** Internal logs can retain technical details with proper access controls and attach a request/correlation ID.

## 8. Runnable Lab: Spring Boot + MVC + @RestControllerAdvice

Let us build a Spring Boot **3.5.16**, Java 17+, Maven application. The API exposes easily verifiable response types:

- `GET /api/products/1`: 200 success.
- `GET /api/products/42`: throws a domain exception, converted by advice into 404 with `ProblemDetail`.
- `GET /api/products/0`: throws `IllegalArgumentException`, advice returns 400.
- `GET /api/products/500`: simulates an internal error, advice returns 500 with sanitized public details.

In addition, `GET /api/products/search` without parameter `term` triggers MVC's `MissingServletRequestParameterException`; custom advice extending `ResponseEntityExceptionHandler` can override the corresponding hook.

**Project structure**:

```text
mvc-exception-demo/
├── pom.xml
└── src/
    ├── main/java/example/errors/
    │   ├── ExceptionDemoApplication.java
    │   ├── ProductController.java
    │   ├── ProductNotFoundException.java
    │   └── ApiExceptionHandler.java
    └── test/java/example/errors/
        └── ExceptionFlowTest.java
```

### 8.1. Maven pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mvc-exception-demo</artifactId>
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

No extra library is needed to use `@ExceptionHandler` or `ProblemDetail`: both are included in Spring Web MVC brought in by the starter.

### 8.2. Entry Point

**`src/main/java/example/errors/ExceptionDemoApplication.java`**:

```java
package example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionDemoApplication.class, args);
    }
}
```

`@SpringBootApplication` enables auto-configuration and component scanning in package `example.errors`, so the controller and advice below are discovered.

### 8.3. Domain Exception

**`src/main/java/example/errors/ProductNotFoundException.java`**:

```java
package example.errors;

public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(long id) {
        super("Product " + id + " not found");
    }
}
```

This exception represents the domain error "product not found"; it is **not coupled to Servlet or HTTP status**. The API layer decides to map it to 404 via advice. Thus the domain does not have to depend on Spring Web's `ResponseStatusException`.

### 8.4. Controller Generating Error Cases

**`src/main/java/example/errors/ProductController.java`**:

```java
package example.errors;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @GetMapping("/{id}")
    public Map<String, Object> get(@PathVariable long id) {
        if (id == 42) {
            throw new ProductNotFoundException(id);
        }
        if (id <= 0) {
            throw new IllegalArgumentException("id must be greater than 0");
        }
        if (id == 500) {
            throw new IllegalStateException("Internal system details");
        }
        return Map.of("id", id, "name", "Notebook");
    }

    @GetMapping("/search")
    public Map<String, String> search(@RequestParam String term) {
        return Map.of("term", term);
    }
}
```

When calling `/api/products/42`, the method is mapped and enters the branch throwing `ProductNotFoundException`. `DispatcherServlet` hands the error to the resolver chain; `ExceptionHandlerExceptionResolver` finds `@ExceptionHandler(ProductNotFoundException.class)`.

When calling `/api/products/search` without `term`, the exception arises during **argument binding** before `search` executes. Because the error still occurs within MVC handling, it can be handled by `ResponseEntityExceptionHandler` inside the advice.

### 8.5. Advice Holding the Error Contract

**`src/main/java/example/errors/ApiExceptionHandler.java`**:

```java
package example.errors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(ProductNotFoundException ex) {
        return problem(HttpStatus.NOT_FOUND, "Product not found",
                ex.getMessage(), "PRODUCT_NOT_FOUND");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalid(IllegalArgumentException ex) {
        return problem(HttpStatus.BAD_REQUEST, "Invalid request",
                ex.getMessage(), "INVALID_PRODUCT_ID");
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ProblemDetail> unexpected(IllegalStateException ex) {
        log.error("Internal error occurred while processing product", ex);
        return problem(HttpStatus.INTERNAL_SERVER_ERROR, "Server error",
                "Unable to complete the request", "INTERNAL_ERROR");
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                status, "Missing parameter: " + ex.getParameterName());
        body.setTitle("Missing required parameter");
        body.setProperty("code", "MISSING_PARAMETER");
        return handleExceptionInternal(ex, body, headers, status, request);
    }

    private ResponseEntity<ProblemDetail> problem(
            HttpStatus status, String title, String detail, String code) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(status, detail);
        body.setTitle(title);
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }
}
```

Explanation:

- `@RestControllerAdvice` applies these shared error handlers to matching controllers and responds via message converters.
- The `ProductNotFoundException` handler returns **404** and stable code `PRODUCT_NOT_FOUND`; `IllegalArgumentException` returns **400**.
- The `IllegalStateException` handler logs the internal stack trace, while returning a sanitized public message with **500**. In a real application, this exception type is just a simulation, and you should not assume every `IllegalStateException` is always a 500 error if the business domain gives it another meaning.
- Because the advice **extends `ResponseEntityExceptionHandler`**, to customize the response for `MissingServletRequestParameterException` we **override** `handleMissingServletRequestParameter`. Do not add a separate `@ExceptionHandler(MissingServletRequestParameterException.class)` in the same advice: the base class already registers that exception group, which would cause an ambiguous mapping.
- `handleExceptionInternal` preserves the framework's response and header handling for MVC exceptions instead of bypassing default contracts.
- The sample intentionally **does not enable** `spring.mvc.problemdetails.enabled=true` auto-configuration; endpoints returning `ProblemDetail` directly still work. If you enable that setting, evaluate the default advice and corresponding precedence order.

Specific handlers are selected by Spring according to exception type. The example avoids a catch-all `@ExceptionHandler(Exception.class)` because overly broad catch-alls easily mask protocol errors already supported by the framework.

### 8.6. Running and Observing

From the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Keep the app running in the first terminal. In a second terminal:

```bash
# 200: valid product
curl -i http://localhost:8080/api/products/1

# 404: product does not exist
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/42

# 400: invalid id
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/0

# 500: simulated error and sanitized public body
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/500

# 400: missing @RequestParam term (framework binding error)
curl -i -H "Accept: application/problem+json" \
  http://localhost:8080/api/products/search
```

The `\` character is line continuation for Bash-style shells; in Windows PowerShell you can write each `curl.exe` command on one complete line.

Expected results table:

| Request | HTTP status | Evidence in body |
| --- | --- | --- |
| `GET /api/products/1` | **200** | JSON with `id=1`, `name="Notebook"`. |
| `GET /api/products/42` | **404** | `code="PRODUCT_NOT_FOUND"`, `detail="Product 42 not found"`. |
| `GET /api/products/0` | **400** | `code="INVALID_PRODUCT_ID"`. |
| `GET /api/products/500` | **500** | `code="INTERNAL_ERROR"`; does **not** contain internal error string. |
| `GET /api/products/search` | **400** | `code="MISSING_PARAMETER"`, `detail` mentions `term`. |

Do not assert exact JSON field ordering or every header across all environments: serializers/containers may add `instance`, headers, or standard fields depending on configuration. What to verify is status, error code, and stable contract fields.

### 8.7. Testing with MockMvc

**`src/test/java/example/errors/ExceptionFlowTest.java`**:

```java
package example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExceptionFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void productExists() throws Exception {
        mvc.perform(get("/api/products/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.name").value("Notebook"));
    }

    @Test
    void domainExceptionBecomes404() throws Exception {
        mvc.perform(get("/api/products/42"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("PRODUCT_NOT_FOUND"))
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void missingParamIsHandledByBaseClassOverride() throws Exception {
        mvc.perform(get("/api/products/search"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MISSING_PARAMETER"));
    }

    @Test
    void internalMessageIsHiddenFromClient() throws Exception {
        mvc.perform(get("/api/products/500"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
                .andExpect(jsonPath("$.detail")
                        .value("Unable to complete the request"));
    }
}
```

Run:

```bash
mvn test
```

This is an integration test running the MVC stack inside the test ApplicationContext; `MockMvc` does not need to start a real HTTP listener. The tests verify the success path, domain exception, framework binding exception, and the policy of hiding internal details. If the system includes Spring Security filters, configure test authentication/authorization properly; do not disable security just to test error handling.

## 9. Tracing Each Request in the Lab

### Case A: Business error `/api/products/42`

```text
GET /api/products/42
  -> DispatcherServlet
  -> HandlerMapping: ProductController.get(...)
  -> @PathVariable converts to long 42
  -> controller throws ProductNotFoundException
  -> DispatcherServlet invokes HandlerExceptionResolver chain
  -> ExceptionHandlerExceptionResolver:
       finds @ExceptionHandler(ProductNotFoundException.class)
       calls ApiExceptionHandler.notFound(...)
  -> ResponseEntity<ProblemDetail>
  -> Jackson serializes body
  -> HTTP 404 + JSON problem response
```

No `try/catch` is needed in every controller. `DispatcherServlet` coordinates resolvers according to the MVC contract.

### Case B: Parameter mapping error `/api/products/search`

```text
GET /api/products/search
  -> HandlerMapping: ProductController.search(...)
  -> HandlerAdapter prepares @RequestParam term
  -> missing term -> MissingServletRequestParameterException
  -> ExceptionHandlerExceptionResolver:
       invokes advice extending ResponseEntityExceptionHandler
       hook handleMissingServletRequestParameter(...)
  -> HTTP 400 + ProblemDetail
```

Key point: the controller logic of `search` **was never invoked** because binding already failed. This exception is not a business service error.

### Case C: No handler found

`GET /does-not-exist` can lead to 404 depending on mapping/static-resource/Servlet container configuration. Depending on the Spring Boot generation, static resource config, and `DispatcherServlet`, the application may use `NoHandlerFoundException`, `NoResourceFoundException`, or Boot error handling fallback.

**Do not assume `@ExceptionHandler(ProductNotFoundException.class)` handles all 404s.** A 404 due to "no matching route" has a different origin from a domain error "record not found". Test both paths separately.

## 10. ResponseEntityExceptionHandler and ErrorResponse

Spring Framework 6 provides `ErrorResponse` for exceptions carrying HTTP status, headers, and a `ProblemDetail` body. `ResponseEntityExceptionHandler` is a base class helping handle Spring MVC exceptions and `ErrorResponseException`, exposing `handle...` methods for customization.

Hooks commonly worth knowing:

- `handleMethodArgumentNotValid(...)`: Bean Validation errors when binding `@Valid @RequestBody`.
- `handleHttpMessageNotReadable(...)`: invalid/unreadable JSON request body.
- `handleMissingServletRequestParameter(...)`: missing query/form parameter.
- `handleTypeMismatch(...)`: failed parameter type conversion.
- `handleHttpRequestMethodNotSupported(...)`: unsupported HTTP method.
- `handleHttpMediaTypeNotSupported(...)`: incompatible request content type.
- `handleExceptionInternal(...)`: builds the shared internal response and preserves relevant metadata.

Override signatures depend on the Spring generation; for example, Spring 6 generally takes `HttpStatusCode` instead of `HttpStatus` in relevant hooks. **Always check the exact signature for your Spring version**, using `@Override` so the compiler catches changes.

### Do Not Turn Every Framework Error into an Arbitrary 400 JSON

An HTTP 405 must retain its meaning "method not supported"; 415 must preserve Content-Type semantics, 406 Accept negotiation, and 500 server error. When overriding a hook, generally use the `status` passed by the framework and keep required headers such as `Allow`. Do not arbitrarily treat all error requests as 400.

Pseudo-code illustrating a deliberate override:

```java
// Illustrative inside a ResponseEntityExceptionHandler subclass.
// Not a standalone Java program.
@Override
protected ResponseEntity<Object> handleHttpRequestMethodNotSupported(
        HttpRequestMethodNotSupportedException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    ProblemDetail body = ProblemDetail.forStatusAndDetail(
            status, "HTTP method is not supported");
    body.setProperty("code", "METHOD_NOT_ALLOWED");
    return handleExceptionInternal(ex, body, headers, status, request);
}
```

We pass along the `headers` supplied by the framework instead of dropping `Allow`. Imports and base class match the earlier lab, adding the corresponding `HttpRequestMethodNotSupportedException`.

## 11. Do Not Confuse @ResponseStatus with an API Response Body

Example:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
class ResourceGoneException extends RuntimeException {
    ResourceGoneException(String message) {
        super(message);
    }
}
```

The annotation on the exception declares which status the error type maps to. It suits certain concise cases, yet does not by itself guarantee a body containing `code`, `type`, `detail`, and the API's designed JSON contract.

For REST APIs requiring a uniform error schema, `@RestControllerAdvice` + `ResponseEntity<ProblemDetail>` is typically easier to control. For small request-specific error statuses, `ResponseStatusException` lets you throw a status inline, though you must evaluate how the body is constructed under your current Spring Boot configuration.

**Mistake:** assuming every `@ResponseStatus` exception goes through `ResponseStatusExceptionResolver` regardless of controller advice. If an `@ExceptionHandler` handles the exception first, the status resolver will not be called.

## 12. Relationship with Spring Boot `/error` and Servlet ERROR Dispatch

There are **two layers** frequently conflated:

1. **Spring MVC exception resolution**: `DispatcherServlet` tries `HandlerExceptionResolver`. The outcome may write JSON/body/view directly or only set status and consider the exception resolved.
2. **Servlet container error handling**: when an exception is unhandled by MVC or the Servlet sends/marks an error, the container may perform an **ERROR dispatch** to an error page. Spring Boot on the Servlet stack typically configures an `/error` endpoint (e.g., `BasicErrorController`) as a fallback.

```text
Exception occurs inside DispatcherServlet
    |
    +-- HandlerExceptionResolver handles it
    |      |
    |      +-- response body + status -> client
    |
    +-- unhandled / error dispatch triggered
           |
           v
        container ERROR dispatch
           |
           v
        Boot's /error or configured error page
           |
           v
        HTML/JSON response per request and config
```

This structure explains why an API sometimes returns `ProblemDetail` JSON produced by advice, while another request returns Boot's default JSON or an HTML error page. These are **different paths**, not necessarily "Spring ignoring the handler."

However, **not every 4xx/5xx response status necessarily triggers `/error`**. If advice already built the response with status and body, the container normally sends that response. Error dispatch behavior depends on `sendError`, exception propagation, container, and response state; verify empirically.

### Enabling Global Problem Details in Boot

Spring Boot offers the option:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

This option enables Problem Details formatting for framework-handled MVC errors. It is **not required** if you return `ProblemDetail` directly in `@ExceptionHandler` as in the lab. When combining it with a custom `@ControllerAdvice` extending `ResponseEntityExceptionHandler`, evaluate precedence and coverage to avoid competing handlers or inconsistent bodies.

## 13. Errors That Should Not Be Handled by MVC HandlerExceptionResolver

| Error source | Why it may sit outside the MVC chain | Where to handle |
| --- | --- | --- |
| Servlet `Filter` throws before calling `DispatcherServlet` | Servlet has not yet received request dispatch | Filter error policy, Servlet error dispatch; for Spring Security use security exception handling/filter chain. |
| Spring Security authentication/authorization | Typically controlled by `ExceptionTranslationFilter` and `AuthenticationEntryPoint`/`AccessDeniedHandler` | Corresponding Spring Security configuration; 401 and 403 per contract. |
| `@Async` fire-and-forget | No MVC request waiting on the exception | `AsyncUncaughtExceptionHandler`, future completion, logging/observability. |
| `@Scheduled` task | Runs on a scheduler thread, no HTTP request | Scheduler error handler, retries/alerts. |
| Startup/config/database connection failure at init | App context not ready to serve HTTP | Startup logs, health/readiness, fail deployment. |
| Error occurs after response is already committed | Status/headers/partial body already sent; cannot replace response cleanly | Log, close connection, design streaming/transaction boundaries, metrics. |

**Exceptions from async MVC requests differ from standalone `@Async` background errors.** With `Callable`/`DeferredResult`/`WebAsyncTask`, errors can be re-dispatched back to Spring MVC for resolver handling during the async dispatch phase. Test the specific case, especially when the response is already committed or timed out.

## 14. Design Mistakes and Practical Traps

### Trap 1: Catching Exception and Returning HTTP 200

```java
// WRONG example: client does not know the request failed.
try {
    return service.load(id);
} catch (Exception ex) {
    return "ERROR";
}
```

An HTTP client seeing 200 may treat the request as successful, breaking retries, caching, and monitoring. Let domain exceptions flow to MVC handlers and return proper statuses, or explicitly return `ResponseEntity.status(...)` for a clearly designed branch.

### Trap 2: A Global Handler Catching Everything and Returning 400

```java
// WRONG example: masks server errors, protocol 405/415, etc.
@ExceptionHandler(Exception.class)
ResponseEntity<String> everything(Exception ex) {
    return ResponseEntity.badRequest().body(ex.getMessage());
}
```

Internal failures get tagged 400, sensitive message details leak, and specific framework handlers can be shadowed or behave unexpectedly under resolver ordering. If a 500 fallback is needed, write an explicit mapping, retain logs/correlation IDs, and ensure standard errors remain properly handled.

### Trap 3: Adding an @ExceptionHandler That Collides with Base Class

When `extends ResponseEntityExceptionHandler` is used, the base class already defines `@ExceptionHandler` mappings for framework exception groups. Adding `@ExceptionHandler(HttpMessageNotReadableException.class)` in the subclass instead of overriding `handleHttpMessageNotReadable` can cause ambiguous exception handler methods. For Spring MVC exceptions that have built-in hooks, **override the hook**.

### Trap 4: Returning HTML Views in REST Advice

Returning a string `"error"` from `@ControllerAdvice` may be interpreted as a view name rather than a JSON body; `@RestControllerAdvice`, or `@ResponseBody` with `ResponseEntity`, clarifies the response type.

### Trap 5: Confusing null ModelAndView with Handled

In a custom resolver, returning `null` asks subsequent resolvers to continue. If you already wrote status/body yourself yet return `null`, downstream resolvers may try writing again, causing response conflicts. Instead, return `new ModelAndView()` to mark it handled once the response is complete.

### Trap 6: Trying to Handle Exceptions After Response Is Sent

If a streaming endpoint has already sent part of the body, even if advice is called, status/headers may no longer be modifiable. You cannot turn a half-sent response into clean JSON error output as if zero bytes were sent. Design stream-specific error protocols and proper logging.

### Trap 7: Confusing Causes of 404

**404 from a non-existent route** differs from **404 from a non-existent record**. A wrong endpoint path may hit resource handlers or Boot's error fallback, whereas a domain error is typically `ProductNotFoundException` in controller/service. Test both paths separately.

### Trap 8: Losing Helpful Client Info or Leaking Too Much

400 errors should carry stable business error codes and helpful details (field names, validation rules) without exposing sensitive data. 500 errors should return a generic message, never stack traces. The backend must log enough context (correlation ID, exception type, relevant request metadata) without logging tokens/passwords.

## 15. HTTP Error Classification Strategy in APIs

| Error category | Typical HTTP status | Example | Appropriate handler |
| --- | --- | --- | --- |
| Invalid input, type, JSON, or validation | 400 | `id=-1`, malformed JSON | Specific advice or `ResponseEntityExceptionHandler` hook. |
| Unauthenticated | 401 | Missing bearer token | Security filter/entry point. |
| Authenticated but unauthorized | 403 | Insufficient role | Spring Security access denied handler or appropriate app policy. |
| Business resource missing | 404 | Product ID 42 absent | Domain exception + `@ExceptionHandler`. |
| Method not supported | 405 | POST to GET-only endpoint | Resolver/framework behavior, keeping `Allow`. |
| Conflict with current state | 409 | Duplicate identifier on entity create | Domain conflict exception/advice. |
| Unsupported media type | 415 | XML sent to JSON-only endpoint | Framework mapping/resolver. |
| Validation fails business rules | 422 when API contract chooses it | Fields have valid types but violate business rule | Domain exception/advice; choose status consistent with API. |
| Unexpected system failure | 500 | Service down, bug | Sanitized fallback error, logging. |
| Upstream dependency unresponsive | 502/503/504 per gateway role/context | Dependency timeout/unavailable | Exception translation at proper boundary; do not assume every timeout = 504. |

This is a suggested mapping; the HTTP contract should be defined consistently between client and server. Specifically for 401/403, handling inside the Spring Security filter chain usually takes priority over global MVC advice.

## 16. When Should You Actually Write a Custom HandlerExceptionResolver?

Most REST APIs should start with:

- Local `@ExceptionHandler` for highly specific behavior.
- `@RestControllerAdvice` for shared domain errors.
- `ResponseEntityExceptionHandler` to standardize framework exception groups.
- `ProblemDetail` to standardize bodies.

Only write a custom `HandlerExceptionResolver` when there is a very specific requirement, such as compatibility with a legacy error mechanism, mapping by a particular handler type, or integrating with an error pipeline carrying a custom contract. If writing a custom resolver:

1. Claim only exceptions within its responsibility; return `null` for others.
2. Check `response.isCommitted()` before modifying status/headers/body.
3. Preserve accurate HTTP status/headers and avoid double-writing.
4. Pick `order` deliberately; do not accidentally block `ExceptionHandlerExceptionResolver`.
5. Test both the case where the resolver handles the error and the case where it defers to the default MVC chain.

In Spring MVC configured via `WebMvcConfigurer`, `extendHandlerExceptionResolvers(...)` appends to the existing list. Meanwhile `configureHandlerExceptionResolvers(...)` can replace or set the list yourself per configuration contracts; misusing it can drop default resolvers. Therefore, prefer built-in annotation mechanisms when the goal is simply producing HTTP JSON errors.

## 17. Testing and Observing in Real Environments

### Functional Testing

- Successful endpoints still return **2xx** and normal bodies.
- Specific business errors return expected status/code/detail.
- Framework errors (missing param, malformed JSON, unsupported method/media type) return proper statuses without losing important headers.
- Internal errors return 500 **without leaking** stack traces or sensitive contents.
- Controllers with local `@ExceptionHandler` override global advice in the expected order.
- Route 404s from missing handlers are tested separately, not conflated with domain 404s.
- For async/streaming, test both before and after response commit if the application uses those models.

### Production Observability

Log stack traces server-side for 5xx errors; distinguish expected errors (such as domain 404/400) from unexpected exceptions to avoid noisy logs. Attach request ID/trace ID via logging context or an observability system. Record metrics by HTTP status, exception type, and endpoint pattern; do not use full URLs containing sensitive IDs as metric labels.

When receiving a report "API returns 500 without hitting advice", first check **whether the error occurred in a filter or in the dispatcher**, whether the response was already committed, whether the advice class is inside component scan, whether the exception is wrapped in a cause chain, which advice order catches first, and whether the container forwarded the request to `/error`.

## 18. Self-Assessment Questions

**Question 1:** A custom resolver returns `null` after inspecting an exception—does that mean the error has been handled?  
**Answer:** No. `null` means unhandled; Spring tries the next resolver.

**Question 2:** Both `@ExceptionHandler` in a controller and `@RestControllerAdvice` catch `IllegalArgumentException`—which takes precedence?  
**Answer:** The local handler inside the controller is evaluated first if applicable.

**Question 3:** When a `@RequestParam` is missing, is the controller invoked first before throwing an error?  
**Answer:** Usually no. The exception can occur while `HandlerAdapter` prepares arguments before calling the method.

**Question 4:** Why might a 405 status include an `Allow` header?  
**Answer:** Per HTTP, it advertises which methods the resource supports. Custom handlers should not strip this standard header.

**Question 5:** Should you add `@ExceptionHandler(HttpMessageNotReadableException.class)` inside a subclass of `ResponseEntityExceptionHandler`?  
**Answer:** Override the `handleHttpMessageNotReadable` hook instead to avoid competing mappings with the base class.

**Question 6:** If a Spring Security filter throws an authentication exception before `DispatcherServlet`, does global MVC advice always catch it?  
**Answer:** No. The security chain has its own handling mechanisms such as `AuthenticationEntryPoint` and `AccessDeniedHandler`.

**Question 7:** Why does an API sometimes return the default body from `/error` instead of custom `ProblemDetail`?  
**Answer:** The exception may not have been handled by MVC resolvers, or the container performed an error dispatch. Trace the actual execution flow.

**Question 8:** What should a 500 error return?  
**Answer:** The proper status, a stable error code, a safe message, and a request/trace ID if available; never send stack traces, SQL/passwords, or internal system details.

## 19. Reference Sources

- [Spring Framework — Exceptions / Chain of Resolvers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html).
- [Spring Framework — @ExceptionHandler methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html).
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html).
- [Spring Framework — Error Responses and ProblemDetail](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html).
- [Spring Boot 3.5 — Servlet Web Applications / Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html).
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).

**Key takeaway:** `HandlerExceptionResolver` lets `DispatcherServlet` convert exceptions in Spring MVC into **intentional HTTP responses**. Choosing the right handling layer by error source, understanding resolver/advice ordering, and testing status, body, headers, and trust boundaries will give your API a stable and safe error contract.