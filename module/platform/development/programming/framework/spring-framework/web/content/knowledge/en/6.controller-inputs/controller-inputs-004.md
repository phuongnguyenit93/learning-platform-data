# @RequestBody, HttpEntity, and Reading Request Content in Spring MVC

## 1. Objectives and scope

After this lesson, you will be able to read and explain the body of an HTTP request in Spring MVC, choose correctly between `@RequestBody` and `HttpEntity<T>`, understand the role of `HttpMessageConverter`, control `Content-Type` and validation, and know when you need to read `HttpServletRequest` directly. This lesson focuses on **Spring MVC running on the Servlet stack**; Spring WebFlux's reactive mechanisms have different APIs for handling request bodies.

An HTTP request has three common parts:

```http
POST /api/orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Trace-Id: trace-42

{"sku":"JAVA-17","quantity":2}
```

- **Request line** specifies the HTTP method and URL.
- **Headers** provide metadata. `Content-Type` describes the **format of the incoming body**; `Accept` describes the **response format the client wants**.
- **Body** is the data after the blank line separating headers and body. In the example above, the body is JSON; the `sku` and `quantity` values are in the body, not the query string.

`@RequestBody` decodes the body into a Java parameter. `HttpEntity<T>` bundles the decoded body and headers into a single object. Both generally rely on Spring MVC's HTTP message converter system.

## 2. How Spring MVC reads the body

Consider the following controller:

```java
@PostMapping("/orders")
public void create(@RequestBody OrderRequest request) {
    // request has already been read and converted before the method is called
}
```

The processing flow in principle:

```text
Client sends bytes + HTTP headers
  -> Servlet container creates HttpServletRequest
  -> DispatcherServlet selects controller/method by route
  -> HandlerAdapter / argument resolver processes parameter
  -> Selects HttpMessageConverter matching Java type and media type
  -> Converter reads body, e.g., JSON -> OrderRequest
  -> (If @Valid is present) validates constraints
  -> Invokes controller method with Java object
  -> Converts response body using appropriate converter
```

`HttpMessageConverter` is the interface that reads/writes HTTP content by data type and media type. Common choices:

| HTTP input | Parameter type | Common reader |
| --- | --- | --- |
| `application/json` | Java DTO/record | Jackson JSON converter when the appropriate library is present |
| `text/plain` | `String` | String converter |
| `application/octet-stream` | `byte[]` | Byte-array converter |
| JSON array | `List<MyDto>` | JSON converter using generic type information |

Spring can only convert when a converter supports both the target data type and the media type. `Content-Type: application/json` **does not automatically turn JSON into an object** if the application lacks an appropriate JSON converter. In a typical Spring Boot Web application, the Web starter provides common JSON configuration; plain Spring Framework requires ensuring the corresponding dependencies and configuration yourself.

Note that `HttpMessageConverter` and Jackson handle data mapping; validation is a **separate step** after object creation. Validly parsed JSON can still violate `@NotBlank` or `@Min`.

## 3. Using @RequestBody

```java
@PostMapping(path = "/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<OrderResponse> create(
        @Valid @RequestBody OrderRequest request) {
    // ...
}
```

Key points to grasp:

- `@RequestBody` marks the **entire body** to be mapped to the parameter. It does not behave like `@RequestParam` (query/form parameter) or `@PathVariable` (path segment).
- For DTOs/records, JSON fields are typically mapped by name to corresponding properties or constructor/record components. Invalid data types or malformed JSON syntax can throw `HttpMessageNotReadableException` and return `400 Bad Request` under default configuration.
- The `required` attribute defaults to `true`. If the body is required and the request does not provide a valid body, Spring typically returns `400` before calling the controller. `@RequestBody(required = false)` allows an absent body, so the method must handle `null` values. Do not use optional mode to accidentally bypass business-required data.
- `@Valid` from `jakarta.validation.Valid` triggers Bean Validation for compatible objects when a validation provider is present. For typical DTO parameters, constraint violations usually throw `MethodArgumentNotValidException` and return `400`; in some signatures with method validation, `HandlerMethodValidationException` may be used instead.
- `consumes = "application/json"` constrains the request format during handler selection. Sending `text/plain` to a JSON-only endpoint typically results in `415 Unsupported Media Type`. `produces` describes the response media type; clients sending an unsupported `Accept` header may receive `406 Not Acceptable`.
- In real application code, prefer purpose-built request DTOs. Do not bind untrusted JSON directly to persistence entities containing fields the client must not control.

### One body, multiple representations

```java
@PostMapping(path = "/payload/text", consumes = MediaType.TEXT_PLAIN_VALUE)
public String text(@RequestBody String body) {
    return "length=" + body.length();
}

@PostMapping(path = "/payload/binary",
             consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public int binary(@RequestBody byte[] body) {
    return body.length;
}
```

These are **two illustrative methods** to place inside a `@RestController` with an appropriate mapping, not a standalone Java program. `String` is text decoded with the charset applied by the converter; `byte[]` is suitable when raw bytes are needed. `String.length()` counts UTF-16 code units, not byte count or always the number of user-perceived characters.

## 4. HttpEntity<T>: body with headers

`HttpEntity<T>` is an object holding a **request body** of type `T` and `HttpHeaders`. Example:

```java
@PostMapping(path = "/orders/entity",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<String> inspect(HttpEntity<OrderRequest> entity) {
    OrderRequest body = entity.getBody();
    String traceId = entity.getHeaders().getFirst("X-Trace-Id");
    // Process body and header...
    return ResponseEntity.ok(traceId == null ? "missing" : traceId);
}
```

In Spring MVC, `HttpEntity<OrderRequest>` as a controller parameter is resolved by the framework and reads the body through message converters, similar to `@RequestBody OrderRequest`, while also preserving headers. You do not add `@RequestBody` to the same `HttpEntity<T>` parameter. `getBody()` can be `null` when the request has no body; check before accessing it. If data validation is needed, do not assume Bean Validation runs just because the body is inside `HttpEntity`: design an explicit validation flow, or use `@Valid @RequestBody` when appropriate.

| Need | Parameter to choose |
| --- | --- |
| Receive JSON as DTO, with `@Valid` | `@Valid @RequestBody MyDto body` |
| Receive DTO and read multiple request headers as a bundle | `HttpEntity<MyDto> entity` |
| Read only a single header | `@RequestHeader("X-Trace-Id") String traceId` alongside `@RequestBody` |
| Need direct control over Servlet body stream | `HttpServletRequest` and `getInputStream()` |
| Receive `application/x-www-form-urlencoded` form fields | Typically use `@RequestParam` or `@ModelAttribute` |

**Do not confuse `HttpEntity<T>` with `ResponseEntity<T>`:** `HttpEntity` models body + headers; `ResponseEntity` extends that idea and adds an HTTP status for the **response**. A controller can accept `HttpEntity<RequestDto>` and return `ResponseEntity<ResponseDto>`.

## 5. Complete, runnable example: Spring MVC + Java 17

The example uses **Spring Boot 3.3.5 (Spring Framework 6.x)** and Java 17 for a small MVC application. Spring Boot only handles bootstrapping, auto-configuring Jackson and validation; the controller API belongs to Spring MVC. Use Maven and this structure:

```text
web-body-demo/
├── pom.xml
└── src/main/java/demo/webbody/
    ├── WebBodyApplication.java
    └── OrderController.java
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
    <artifactId>web-body-demo</artifactId>
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

**`src/main/java/demo/webbody/WebBodyApplication.java`**

```java
package demo.webbody;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebBodyApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebBodyApplication.class, args);
    }
}
```

**`src/main/java/demo/webbody/OrderController.java`**

```java
package demo.webbody;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    public record OrderRequest(@NotBlank String sku,
                               @Min(1) int quantity) {}

    public record OrderResponse(long id, String sku, int quantity) {}

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody OrderRequest request) {
        OrderResponse result =
                new OrderResponse(7L, request.sku(), request.quantity());
        return ResponseEntity.status(HttpStatus.CREATED).body(result);
    }

    @PostMapping(path = "/entity",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> inspect(HttpEntity<OrderRequest> entity) {
        OrderRequest request = entity.getBody();
        if (request == null) {
            return ResponseEntity.badRequest().build();
        }
        String traceId = entity.getHeaders().getFirst("X-Trace-Id");
        String value = traceId == null ? "missing" : traceId;
        return ResponseEntity.ok("sku=" + request.sku() + ", trace=" + value);
    }

    @PostMapping(path = "/raw",
                 consumes = MediaType.TEXT_PLAIN_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public String raw(@RequestBody String body) {
        return "length=" + body.length();
    }

    @PostMapping(path = "/bytes",
                 consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Integer> bytes(@RequestBody byte[] body) {
        return Map.of("bytes", body.length);
    }
}
```

Both `record`s are declared nested inside `OrderController`, yet remain valid Java types that Jackson can map. `@NotBlank` is used for SKU and `@Min(1)` for quantity. `id = 7` is a fixed illustrative value; there is no database or real order creation. The `/entity` endpoint only illustrates accessing headers/body; it **does not have `@Valid`**, so the example does not promise the same validation as the `create` endpoint.

Run from the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Once the application is listening on the default port `8080`, test it in Bash (Linux/macOS/Git Bash):

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"sku":"JAVA-17","quantity":2}'
```

Key result (omitting environment-dependent HTTP headers):

```http
HTTP/1.1 201
Content-Type: application/json

{"id":7,"sku":"JAVA-17","quantity":2}
```

Test `HttpEntity` with a custom request header:

```bash
curl -i -X POST http://localhost:8080/api/orders/entity \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/plain' \
  -H 'X-Trace-Id: trace-42' \
  -d '{"sku":"SPRING","quantity":1}'
```

Response body:

```text
sku=SPRING, trace=trace-42
```

Test receiving plain text and bytes:

```bash
curl -s -X POST http://localhost:8080/api/orders/raw \
  -H 'Content-Type: text/plain' --data-binary 'hello'
curl -s -X POST http://localhost:8080/api/orders/bytes \
  -H 'Content-Type: application/octet-stream' --data-binary 'ABC'
```

Respectively receive:

```text
length=5
{"bytes":3}
```

In PowerShell, you can send JSON with a single-line command:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/orders' -ContentType 'application/json' -Body '{"sku":"JAVA-17","quantity":2}'
```

The numbers above are fixed based on the example's data and logic; headers like `Date`, `Transfer-Encoding`, and the default error body format may differ depending on configuration.

## 6. When you need to read HttpServletRequest directly

In Servlet MVC, `HttpServletRequest.getInputStream()` provides the byte stream of the body; `getReader()` provides character reading. Direct reading is useful when handling custom formats, verifying signatures over **raw bytes**, or having special streaming requirements. An example **alternative method** you can add to the controller; this is an illustrative snippet requiring imports `jakarta.servlet.http.HttpServletRequest`, `java.io.IOException`, and `java.io.InputStream`:

```java
@PostMapping(path = "/stream",
             consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public ResponseEntity<String> readStream(
        HttpServletRequest request) throws IOException {
    try (InputStream input = request.getInputStream()) {
        byte[] data = input.readAllBytes();
        return ResponseEntity.ok("bytes=" + data.length);
    }
}
```

**Note:** `readAllBytes()` loads all data into RAM and is only sensible when request size is bounded. The body is normally a single-consumption stream; do not simultaneously read via `@RequestBody` and manually call `getInputStream()` for the same data. Filters or interceptors that read the stream beforehand can also leave the controller seeing an empty body. `ContentCachingRequestWrapper` only caches data **that has already been read**, rather than automatically making the body an infinitely re-readable stream. For large file uploads, consider appropriate upload/streaming solutions instead of turning everything into one large `byte[]`.

When reading ordinary JSON, `@RequestBody` is better because it handles mapping and format errors; drop down to the Servlet API only when true byte-level control is required.

## 7. Distinguishing JSON body, query, form, and multipart

These are different data sources:

| Incoming request | Spring MVC typically uses | Example |
| --- | --- | --- |
| `/orders?limit=10` | `@RequestParam int limit` | Query parameter |
| `/orders/123` | `@PathVariable long id` | Path segment |
| `Content-Type: application/json` | `@RequestBody OrderRequest dto` | JSON body |
| `Content-Type: application/x-www-form-urlencoded` | `@RequestParam` or `@ModelAttribute` | Form fields |
| `Content-Type: multipart/form-data` | `@RequestPart`, `MultipartFile`, or form binding | Multipart parts |

As noted by Spring MVC, `application/x-www-form-urlencoded` form requests should be handled as parameter/form binding; the Servlet API may parse the body when accessing request parameters, making subsequent body reads unreliable. `@RequestPart` is useful when a multipart part contains JSON and requires a separate converter for that part.

`@RequestBody` is typically used for POST, PUT, and PATCH requests with bodies; HTTP does not restrict this annotation strictly to those three methods, but API design should respect the semantics of each method.

## 8. Common errors and how to diagnose them

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `400 Bad Request`, controller did not run | Malformed JSON, missing required body, failed type mapping, or failed validation | Inspect raw body, DTO/record, actual exception, and constraints |
| `415 Unsupported Media Type` | `Content-Type` does not match `consumes` or converter | Send the right media type, register a converter if needed |
| `406 Not Acceptable` | `Accept` does not match any producible response | Check `produces` and response converters |
| Field is `null` or default value | JSON is missing the field, property name mismatch, or primitive default value | Inspect JSON and add constraints matching your intent |
| `@Valid` has no effect | Missing Bean Validation provider/starter or validation does not apply in this flow | Add dependency and place validation properly on the DTO |
| Empty body even though client sent it | Stream already consumed by another filter/handler | Audit components intercepting the request |
| Corrupted binary data | Reading bytes as `String` with wrong charset encoding/decoding | Use `byte[]` or stream for binary data |

When `@Valid @RequestBody` fails normally, Spring returns `400` via its default handler, but **the error response JSON body does not have a single uniform format** across all versions/configurations. To standardize errors, an application can use `@RestControllerAdvice` / `@ExceptionHandler` or `ResponseEntityExceptionHandler`. Do not catch every exception and return `200 OK`, as that hides request failures from clients.

Additionally, limit body size at the appropriate layer, avoid logging sensitive payloads, and do not assume Java types and validation annotations can replace business rules or authorization checks.

## 9. Self-check questions

1. A client sends `Content-Type: text/plain` to a method specifying `consumes = "application/json"`. Why is the method typically not invoked?
2. When do you choose `HttpEntity<OrderRequest>` instead of `@RequestBody OrderRequest`? If you only need a single header, what shorter alternative exists?
3. What three distinct roles do `@Valid`, Jackson, and `HttpMessageConverter` play?
4. Why should you not have both `@RequestBody String body` and manually read `request.getInputStream()` on the same request?
5. When do you use `@RequestParam`, `@ModelAttribute`, or `@RequestPart` instead of `@RequestBody`?

**Answer hints:** (1) Media type does not match the mapping/converter, typically `415`. (2) `HttpEntity` when you need body along with headers; for a single header you can add `@RequestHeader`. (3) Converter reads bytes and deserializes, Jackson performs JSON mapping, and Bean Validation checks constraints afterward. (4) The body stream may already be consumed. (5) Query/form/multipart correspond to different binding mechanisms.

## 10. Official references

- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring MVC — HttpEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/httpentity.html)
- [Spring MVC — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)

The links above point to current Spring Framework documentation; the runnable example pins Spring Boot 3.3.5 so the Maven command runs in a deterministic environment.