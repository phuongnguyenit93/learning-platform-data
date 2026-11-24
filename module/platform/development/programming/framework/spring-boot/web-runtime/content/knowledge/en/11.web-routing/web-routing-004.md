# Path Variables, Data Types, and Mismatch Cases in Spring Boot

## 1. Goal: separating routing from data type conversion

In a Spring Boot application, an endpoint can use **URI template variables** (path variables), for example `/users/42`, `/orders/PAID`, or `/documents/550e8400-e29b-41d4-a716-446655440000`. Two fundamental steps in Spring MVC and WebFlux are:

1. **Route matching**: matching the HTTP method, URL path, and mapping conditions such as `params`, `headers`, `consumes`, and `produces` to select a handler.
2. **Argument resolution and conversion**: extracting the string value captured from the path and converting it to the handler's Java parameter type, such as `long`, `UUID`, `enum`, or a custom domain type.

This distinction explains an easily confused scenario:

- Path **does not match** pattern → typically HTTP **404 Not Found** if no other handler matches.
- Path **matches**, yet the value cannot be converted to the Java type → typically HTTP **400 Bad Request**.
- Path matches, wrong HTTP method → typically HTTP **405 Method Not Allowed**.
- Request `Content-Type` does not match `consumes` → typically **415 Unsupported Media Type**.
- `Accept` does not match `produces` → typically **406 Not Acceptable**.

The final status and error body also depend on custom exception handlers, Spring Security, the embedded server, reverse proxies, and the Framework version. Do not write API contracts assuming every error returns the exact same body format.

## 2. Path variable processing flow in Spring MVC

Example:

```java
@GetMapping("/users/{id}")
public UserDto get(@PathVariable("id") long id) {
    return new UserDto(id, "Lan");
}
```

With `GET /users/42`, the general process:

```text
HTTP GET /users/42
        |
        v
DispatcherServlet
        |
        v
RequestMappingHandlerMapping
  - Pattern /users/{id} matches URL
  - Method GET matches
  - Captures id = "42"
        |
        v
HandlerAdapter + argument resolver
  - ConversionService: "42" -> long 42
        |
        v
Controller method get(42)
        |
        v
HttpMessageConverter / View rendering
        |
        v
HTTP response
```

If the URL is `/users/abc`, the `/users/{id}` route **still matches** because `{id}` is not numeric by default. The error occurs during conversion of `"abc"` to `long`. The controller is not invoked yet, and by default it normally returns 400.

In WebFlux, `DispatcherHandler`, `HandlerMapping`, and `HandlerAdapter` take on the corresponding roles, though the runtime and exception handling are reactive; do not use `DispatcherServlet` to explain the WebFlux pipeline.

## 3. @PathVariable and variable names

A variable is placed inside curly braces in the mapping:

```java
@GetMapping("/products/{productId}")
public ProductDto find(
        @PathVariable("productId") long productId) {
    return new ProductDto(productId, "Laptop");
}
```

This is an illustrative method inside a `@RestController`, not a standalone Java file. `productId` inside `{productId}` is the variable name captured by the route; `@PathVariable("productId")` specifies which variable is injected into the parameter.

The Java parameter name can differ from the variable name:

```java
@GetMapping("/products/{productId}")
public ProductDto find(@PathVariable("productId") long id) {
    return new ProductDto(id, "Laptop");
}
```

If you omit the name from the annotation, e.g. `@PathVariable long productId`, Spring needs parameter name metadata such as when the compiler enables `-parameters`. Writing the name explicitly keeps examples stable and avoids binding failures caused by compiler settings.

**Distinction:** `/products/7?details=true` has `7` as a path variable, while `details=true` is a query parameter typically read with `@RequestParam`. `@RequestBody` handles the request body and does not substitute for `@PathVariable`.

## 4. PathPattern and segment count

Modern Spring MVC uses `PathPattern` to match URLs by segment structure. Important rules:

| Pattern | URL | Result |
|---|---|---|
| `/users/{id}` | `/users/42` | Matches, captures `id="42"` |
| `/users/{id}` | `/users/abc` | Still matches; conversion runs later |
| `/users/{id}` | `/users` | Does not match because a segment is missing |
| `/users/{id}` | `/users/42/profile` | Does not match because of an extra segment |
| `/shops/{shop}/items/{item}` | `/shops/acme/items/7` | Matches two variables |
| `/assets/*.png` | `/assets/logo.png` | Matches wildcard within one segment |
| `/assets/{*path}` | `/assets/icons/logo.png` | Catch-all, captures multiple segments |

`{name}` captures a single segment and does not automatically span multiple slash-separated segments. `{*path}` captures the entire remaining multi-segment tail; in Spring documentation, with `/resources/{*file}`, the URL `/resources/images/a.png` can capture `file="/images/a.png"`.

The `**` syntax also matches multiple path segments without binding a variable name. In `PathPattern`, catch-all wildcards like `**` and `{*path}` must appear **at the end of the pattern**; do not place them in the middle of a route followed by another segment.

## 5. ConversionService and common Java types

After the route matches, Spring can convert the URI variable string to the parameter's Java type using `ConversionService`, a `Converter`, or a `Formatter`.

| Parameter type | Example URL | Common failure |
|---|---|---|
| `String` | `/codes/AB-42` | Rarely fails conversion; still needs validation |
| `int` | `/items/42` | Alphabetic string or exceeds 32-bit range |
| `long` / `Long` | `/users/987654321` | Non-numeric or exceeds 64-bit range |
| `UUID` | `/docs/550e8400-e29b-41d4-a716-446655440000` | Cannot parse UUID |
| `enum` | `/orders/PAID` | Value not in enum or wrong case |
| `BigDecimal` | `/prices/19.50` | Value cannot be converted |
| Domain type | `/order-keys/acme-42` | Missing Converter or parser throws an error |

For example, `/users/abc` with route `/users/{id}` and `@PathVariable long id`: Spring MVC can throw `MethodArgumentTypeMismatchException` and resolve it to 400. The value `-7` still parses into `long`, yet whether the API allows negative IDs is a **business** concern, not a type-conversion concern.

A type that parses successfully also does not prove the resource exists in the database. Do not mix input parsing errors (400) with failing to find a record (usually 404).

## 6. Regex constraints on paths before binding

You can constrain a path variable using `{variable:regex}` syntax:

```java
@GetMapping("/numbers/{value:[0-9]+}")
public NumberDto get(@PathVariable("value") long value) {
    return new NumberDto(value);
}
```

Pattern `[0-9]+` matches only one or more ASCII digits. Comparison:

| Request | Matches URL pattern? | Conversion | Typical status |
|---|---|---|---|
| `/numbers/42` | Yes | `long(42)` | 200 if controller succeeds |
| `/numbers/abc` | No | Does not occur | 404 if no other route matches |
| `/numbers/-3` | No | Does not occur | 404 if no other route matches |
| `/numbers/0007` | Yes | `long(7)` | 200 or per business logic |
| `/numbers/999999999999999999999` | Yes | `long` overflow | Typical 400 |

Regex alters **route matching**; the `long` type alters **argument conversion**. Thus, the same string `abc` can produce 404 with a regex route and 400 with a non-regex `/{id}` route. Avoid writing complex regexes unless clearly needed; poorly designed regexes risk expensive processing.

## 7. Complete Spring Boot 3.5 + Java 17 example

Create a Spring Boot 3.5 project with Java 17 and `spring-boot-starter-web`. The dependency snippet in `pom.xml` below assumes the project already has a Spring Boot parent or dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

File structure:

```text
src/main/java/com/example/routes/
    RoutesApplication.java
    RoutingController.java
src/main/resources/
    application.properties
```

File `src/main/java/com/example/routes/RoutesApplication.java`:

```java
package com.example.routes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutesApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoutesApplication.class, args);
    }
}
```

File `src/main/java/com/example/routes/RoutingController.java`:

```java
package com.example.routes;

import java.util.UUID;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RoutingController {

    @GetMapping("/api/users/{id}")
    public UserResponse user(@PathVariable("id") long id) {
        return new UserResponse(id, "user-" + id);
    }

    @GetMapping("/api/numbers/{value:[0-9]+}")
    public NumberResponse number(
            @PathVariable("value") long value) {
        return new NumberResponse(value);
    }

    @GetMapping("/api/documents/{id}")
    public DocumentResponse document(
            @PathVariable("id") UUID id) {
        return new DocumentResponse(id, "document");
    }

    @GetMapping("/api/orders/{status}")
    public OrderResponse order(
            @PathVariable("status") OrderStatus status) {
        return new OrderResponse(status.name());
    }

    public enum OrderStatus { NEW, PAID, SHIPPED }

    public record UserResponse(long id, String name) {}
    public record NumberResponse(long value) {}
    public record DocumentResponse(UUID id, String kind) {}
    public record OrderResponse(String status) {}
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
```

Java 17 records are serialized by the Jackson JSON converter under the standard Spring Web starter configuration. This example does not connect to a database: responses are fixed based on input to demonstrate routing.

Run using the Maven Wrapper included in the project:

```bash
./mvnw spring-boot:run
```

## 8. Sending successful requests and expected responses

```bash
curl -s http://localhost:8080/api/users/42
curl -s http://localhost:8080/api/numbers/7
curl -s http://localhost:8080/api/orders/PAID
curl -s http://localhost:8080/api/documents/550e8400-e29b-41d4-a716-446655440000
```

Each command is a separate HTTP request. Expected JSON bodies:

```json
{"id":42,"name":"user-42"}
{"value":7}
{"status":"PAID"}
{"id":"550e8400-e29b-41d4-a716-446655440000","kind":"document"}
```

The responses are shown line by line for readability, not as a byte-for-byte stdout capture of four consecutive `curl -s` commands, because JSON bodies do not necessarily end with a newline.

To inspect status and headers:

```bash
curl -i http://localhost:8080/api/users/42
```

With the example running on port 8080, a valid request typically returns status 200 and a JSON-compatible `Content-Type`.

## 9. Sending invalid requests and distinguishing 400, 404, 405

```bash
curl -i http://localhost:8080/api/users/not-a-number
curl -i http://localhost:8080/api/numbers/abc
curl -i http://localhost:8080/api/orders/paid
curl -i http://localhost:8080/api/documents/not-a-uuid
curl -i -X POST http://localhost:8080/api/users/42
```

Expected in default Spring MVC:

| Request | Status | Reason |
|---|---|---|
| GET `/api/users/not-a-number` | 400 | Path matches, but `long` conversion fails |
| GET `/api/numbers/abc` | 404 | Regex `[0-9]+` does not match |
| GET `/api/orders/paid` | 400 | Default enum has `PAID`, not `paid` |
| GET `/api/documents/not-a-uuid` | 400 | UUID conversion fails |
| POST `/api/users/42` | 405 | Path has a GET handler but no matching POST handler |
| GET `/api/users` | 404 | Route is missing the `{id}` segment |

Error bodies depend on Boot version, `@ControllerAdvice`, `ErrorAttributes`, and Spring Security. When Spring MVC cannot select a handler yet, controller code does not execute; do not use a breakpoint inside the controller as evidence of whether the request reached the server.

## 10. UUID, enum, and stable representation rules

With `@PathVariable UUID id`, Spring can convert UUID strings using its built-in converter. If parsing succeeds yet the resource does not exist in the database, the controller/service must actively return 404. Valid UUID format and ID existence are two different things.

With enums:

```java
public enum OrderStatus { NEW, PAID, SHIPPED }

@GetMapping("/orders/{status}")
public String find(@PathVariable("status") OrderStatus status) {
    return status.name();
}
```

The snippet above illustrates usage inside a controller, not a standalone Java file. With the default converter, `PAID` is valid whereas `paid` is not automatically treated as `PAID`. If an API wants case-insensitivity or slugs like `in-progress`, a custom converter and tested API contract are required.

Choose stable path representations decoupled from internal enum names when an API is published to multiple clients. Renaming an enum can accidentally break paths if URLs rely directly on `enum.name()`.

## 11. Type-valid numbers that are invalid by business rules

`@PathVariable long id` allows values that parse as `long`, including negative numbers or 0; however, many systems require IDs to be positive.

If `/users/0` should return a 400 client error, you can validate in the service/controller or use appropriate Bean Validation.

Example fragment:

```java
if (id <= 0) {
    throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST, "id must be a positive number");
}
```

You need to import `org.springframework.web.server.ResponseStatusException` and `org.springframework.http.HttpStatus` in the method containing that code.

Other scenarios:

- `/users/999999999999999999999999`: `long` overflow, conversion fails → typically 400.
- `/users/0`: parses validly, but disallowed by domain → application decides 400 or another contract.
- `/users/42`: parses validly, but no DB record exists → typically 404 from business lookup.
- `/users/42`: record exists, but user lacks permission → authorization decides 401/403 or an existence-hiding policy.

Do not confuse Spring successfully converting an ID with Spring having checked the database or access permissions.

## 12. Multiple variables, missing segments, and required=false

Route with multiple variables:

```java
@GetMapping("/tenants/{tenantId}/orders/{orderId}")
public OrderDto findOrder(
        @PathVariable("tenantId") String tenantId,
        @PathVariable("orderId") long orderId) {
    return service.find(tenantId, orderId);
}
```

GET `/tenants/acme/orders/42` provides both values. GET `/tenants/acme/orders` does not match because one segment is missing.

If you need all variables by name:

```java
@GetMapping("/route-info/{tenant}/{resource}")
public Map<String, String> pathVars(
        @PathVariable Map<String, String> vars) {
    return vars;
}
```

This is an illustrative method inside `@RestController`; import `java.util.Map` and related Spring annotations. With `/route-info/acme/products`, the Map normally contains two entries `tenant=acme` and `resource=products`.

**Note:** `@PathVariable(required=false)` does not make the pattern `/products/{id}` automatically match `/products`. Route matching happens first. If you need both collection and detail views, use separate `@GetMapping("/products")` and `@GetMapping("/products/{id}")`; or define multiple explicit patterns and handle nullability according to your contract.

`MissingPathVariableException` when a method has already been selected yet an annotation-required variable is absent can indicate a server configuration bug, unlike a client data-type error. Do not unconditionally force both to 400.

## 13. Route specificity and mapping conflicts

Suppose:

```java
@GetMapping("/users/me")
public Profile me() { /* ... */ }

@GetMapping("/users/{id}")
public Profile byId(@PathVariable("id") String id) { /* ... */ }
```

On GET `/users/me`, the literal route `/users/me` is more specific than `/users/{id}`, so it is typically prioritized. Method declaration order inside the Java file is not the deciding factor.

Principles:

- Literal paths are typically more specific than `{id}` variables.
- Single-segment wildcards differ from multi-segment catch-alls.
- `PathPattern` applies specificity rules when multiple patterns can match.
- Duplicate handler mappings can cause `Ambiguous mapping` errors at startup or dispatch.
- HTTP method, `params`, `headers`, `produces`, and `consumes` conditions also influence handler selection.

If an application has `/users/me` and `/users/{id}`, avoid accidentally letting the literal `me` be converted to `long`; use explicit routes and write tests. If a pattern has an overly narrow regex, a supported path can get 404 before the controller ever receives data.

## 14. Custom converters for domain types

Sometimes a URL ID has a custom structure, such as `/order-keys/acme-42`. Rather than parsing manually in every controller, you can register a `Converter<String, OrderKey>`.

File `src/main/java/com/example/routes/OrderKey.java`:

```java
package com.example.routes;

public record OrderKey(String tenant, long number) {
}
```

File `src/main/java/com/example/routes/OrderKeyConverter.java`:

```java
package com.example.routes;

import org.springframework.core.convert.converter.Converter;

public final class OrderKeyConverter
        implements Converter<String, OrderKey> {

    @Override
    public OrderKey convert(String text) {
        String[] parts = text.split("-", 2);
        if (parts.length != 2 || parts[0].isBlank()) {
            throw new IllegalArgumentException("Invalid order key");
        }
        try {
            long value = Long.parseLong(parts[1]);
            if (value <= 0) {
                throw new IllegalArgumentException("Invalid order key");
            }
            return new OrderKey(parts[0], value);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid order key", ex);
        }
    }
}
```

File `src/main/java/com/example/routes/RoutingConversionConfiguration.java`:

```java
package com.example.routes;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class RoutingConversionConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new OrderKeyConverter());
    }
}
```

A `@RestController` in the same project can accept:

```java
@GetMapping("/order-keys/{key}")
public OrderKey find(@PathVariable("key") OrderKey key) {
    return key;
}
```

`acme-42` converts to `OrderKey("acme", 42)`; `acme-abc` triggers a conversion error. Converters should be pure, fast, and avoid database or HTTP calls. If tenants are allowed to contain `-`, the example parser will not suffice; a different grammar with a clear specification is needed.

## 15. Conversion errors and returning stable error responses

Spring MVC can turn type conversion errors into a default 400. If a consistent API body is needed, you can create a `@RestControllerAdvice`:

File `src/main/java/com/example/routes/PathErrorAdvice.java`:

```java
package com.example.routes;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class PathErrorAdvice {

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<Map<String, String>> mismatch(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.badRequest().body(
                Map.of("error", "INVALID_PATH_VARIABLE"));
    }
}
```

When this advice catches a conversion mismatch, the JSON response contains the equivalent of:

```json
{"error":"INVALID_PATH_VARIABLE"}
```

Do not expose sensitive contents, stack traces, SQL, tokens, or system internals in error bodies. If detailed error info is needed, use `ProblemDetail` or a standardized error schema with error codes and a request ID.

This kind of advice **does not handle** the case where a URL fails to match any route before a handler is chosen. Handling 404 requires dedicated not-found/error handling rather than relying on `MethodArgumentTypeMismatchException`.

## 16. Spring WebFlux: @PathVariable and functional routing

WebFlux annotated controllers also support type conversion:

```java
package com.example.reactive;

import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    @GetMapping("/api/docs/{id}")
    public Mono<Document> document(
            @PathVariable("id") UUID id) {
        return Mono.just(new Document(id, "ready"));
    }

    public record Document(UUID id, String state) {}
}
```

The Java code above is a controller running in a Spring Boot WebFlux project with `spring-boot-starter-webflux`. When a UUID fails to convert, the input error normally becomes 400 in the default reactive error flow. Unmatched paths remain a routing problem and normally produce 404.

Functional WebFlux routing differs in how variables are read:

```java
@Bean
RouterFunction<ServerResponse> router() {
    return RouterFunctions.route(
        RequestPredicates.GET("/api/items/{id}"),
        request -> {
            try {
                long id = Long.parseLong(
                        request.pathVariable("id"));
                return ServerResponse.ok().bodyValue(
                        Map.of("id", id));
            } catch (NumberFormatException ex) {
                return ServerResponse.badRequest().bodyValue(
                        Map.of("error", "INVALID_ID"));
            }
        });
}
```

This fragment is a method inside a `@Configuration` class, requiring imports for `java.util.Map`, `org.springframework.context.annotation.Bean`, and `org.springframework.web.reactive.function.server.*`. In this functional route, `request.pathVariable("id")` returns a `String` so the parser is called **manually**, unlike an annotated method whose `long` parameter is converted automatically.

A Spring Boot app with both `spring-boot-starter-web` and `spring-boot-starter-webflux` typically prefers MVC by default; do not assume a reactive runtime just because a controller returns `Mono`.

## 17. Dots, trailing slashes, and URL encoding

A URL segment may contain dots:

```text
/files/report.v2.pdf
```

Modern Spring MVC does not by default use suffixes like `.pdf` or `.json` to infer representations, nor should you assume view names or media types change automatically based on file extensions.

Trailing slashes require testing: in Spring Framework 6.x, matching an appended `/` at the end of a path is no longer the default as in some legacy apps. `/users/42` and `/users/42/` may not match the same mapping. Define canonical URLs and align clients/proxies consistently.

For `%2F` (encoded slash), `%2e`, or encoded backslashes, decoding behavior can differ across reverse proxies, servlet containers, and WebFlux servers. Do not rely on encoded slashes always remaining within a single segment. `PathPattern` processes paths segment by segment to reduce ambiguity, yet you should still test against your exact runtime and network setup.

**Safety:** Do not pass `@PathVariable` directly as a file path, SQL fragment, or redirect URL. Verify access permissions against the actual resource after normalizing the ID to avoid discrepancies between proxies, Spring Security, and handler routing. Never put tokens or sensitive info in URLs because URLs readily appear in access logs.

## 18. Testing with MockMvc: distinguishing unmatched paths from conversion failures

In the MVC project from section 7, add `spring-boot-starter-test` using the standard Maven configuration:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

File `src/test/java/com/example/routes/RoutingControllerTest.java`:

```java
package com.example.routes;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RoutingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validIdConvertsToLong() throws Exception {
        mvc.perform(get("/api/users/42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42));
    }

    @Test
    void invalidLongIsBadRequest() throws Exception {
        mvc.perform(get("/api/users/not-a-number"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void regexRejectsNonDigitBeforeConversion() throws Exception {
        mvc.perform(get("/api/numbers/abc"))
            .andExpect(status().isNotFound());
    }

    @Test
    void numericOverflowFailsAfterRegexMatch() throws Exception {
        mvc.perform(get("/api/numbers/999999999999999999999"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void invalidUuidIsBadRequest() throws Exception {
        mvc.perform(get("/api/documents/not-a-uuid"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void enumCaseMattersByDefault() throws Exception {
        mvc.perform(get("/api/orders/paid"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongMethodReturnsMethodNotAllowed() throws Exception {
        mvc.perform(post("/api/users/42"))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void missingSegmentDoesNotMatch() throws Exception {
        mvc.perform(get("/api/users"))
            .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
./mvnw test
```

This test suite uses Spring MVC `MockMvc` without opening a real HTTP port. If the project includes Spring Security, custom error handlers, or other mappings, adjust the test context/expectations accordingly. For WebFlux, use `@WebFluxTest` and `WebTestClient` instead of `MockMvc`.

## 19. Mismatch cases: diagnostic table

| Case | Cause | How to handle |
|---|---|---|
| 404 for `/users/abc` with digits regex | Pattern does not accept letters | Check `{id:regex}` and URL contract |
| 400 for `/users/abc` with `long` type | Post-match conversion fails | Check input and converter |
| 400 with very large number | Exceeds Java type limit | Pick the right type or bound ID length |
| 404 for `/users` | Missing required path segment | Add a separate route for the collection |
| 400 for `/orders/paid` | Default enum is case-sensitive | Standardize canonical slug/case or custom converter |
| 404 for `/users/42/profile` | Extra segment | Check route nesting |
| 405 for POST to a GET route | HTTP method not mapped | Add a valid mapping if needed |
| 406 when client only accepts XML | `Accept` does not match `produces` | Check supported representations |
| 415 when POSTing `text/plain` | `Content-Type` does not match `consumes` | Send the right input media type |
| Controller does not run, gets 401/403 | Security filter blocks request | Check authentication/authorization |
| Status differs in production | Proxy/gateway rewrites or errors before Spring | Check logs and URL after proxy |
| Ambiguous mapping | Multiple competing handlers | Design specific, non-overlapping patterns |

Distinguishing **routing**, **conversion**, **validation**, **resource lookup**, **security**, and **content negotiation** keeps errors at their proper layer rather than catching everything and returning 400.

## 20. Debugging workflow and design checklist

1. Read the **actual** HTTP method and URL reaching the application, not just the browser URL.
2. Confirm the handler mapping including literal segments, `{id}`, regex, or catch-alls.
3. Check whether the route matches; do not rush to debug the controller if no handler was selected.
4. Cross-check `@PathVariable("...")` names against template variables.
5. Check `String` → `int/long/UUID/enum/custom domain` conversion, including overflow.
6. Separate syntactic conversion errors from business validation (positive ID, valid tenant, valid enum).
7. Separate non-existent resources (404 decided by service) from invalid input.
8. Check HTTP methods and `produces/consumes` to distinguish 405/406/415.
9. Test dots, trailing slashes, encoded slashes, and proxy rewrites when your system uses them.
10. Align route matching with Spring Security; do not log path secrets.
11. Use `WebMvcConfigurer.addFormatters` for MVC custom converters; avoid `@EnableWebMvc` if you only want to extend config.
12. Write tests for happy paths, type mismatches, missing segments, non-matching regexes, bad UUIDs, bad enums, wrong methods, and not-found resources.

**Remember:** `/{id}` captures the string first and parses afterward; `/{id:[0-9]+}` excludes non-digits right at routing. With `long`, a path containing letters normally becomes 400, whereas one rejected by regex before parsing normally becomes 404. Error behavior is part of the API contract and must be documented and tested.

## 21. References

- Spring Framework — Mapping Requests, URI patterns, regex, and specificity: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — Type Conversion for controller arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — URI Variables and @PathVariable: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/uri-variables.html
- Spring Framework — MVC Path Matching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/path-matching.html
- Spring Framework — WebFlux annotated request mapping: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — WebFlux Type Conversion: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/typeconversion.html
- Spring Boot — Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9110 — HTTP Semantics (400, 404, 405, 406, 415): https://www.rfc-editor.org/rfc/rfc9110
