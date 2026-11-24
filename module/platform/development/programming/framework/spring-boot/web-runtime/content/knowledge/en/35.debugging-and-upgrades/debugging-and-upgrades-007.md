# 500 Due to Serialization, Templates, or Errors After the Response Is Committed

## 1. Why Does the Controller Finish Yet HTTP Still Fails?

In the Spring Boot web runtime, a controller returning a Java object or a view name **does not mean the HTTP response is complete**. For instance, a controller returns `OrderDto` cleanly, yet Jackson later invokes a getter that throws an exception; or `@Controller` returns `"order/detail"`, yet Thymeleaf cannot resolve the template. Both failures happen **after the controller method returns**. If they happen while the response is still mutable, the server can usually return **HTTP 500**.

Even trickier: when an endpoint has already sent headers or part of the body, and then serialization, template rendering, or streaming fails, the response may already be **committed**. At that point, the server **cannot go back and change HTTP status 200 to 500**, nor replace already-emitted body bytes with a new JSON error. Server logs may record an exception while the client sees status 200 with a truncated body, a closed/reset connection, or unparseable JSON.

This article belongs to **Debugging and Upgrades** and focuses on:
1. Separating errors in controllers, Jackson `HttpMessageConverter`, template view rendering, and streaming/asynchronous responses.
2. Identifying `HttpMessageNotWritableException`, `JsonMappingException`, `InvalidDefinitionException`, `TemplateInputException`, `TemplateProcessingException`, and post-commit exceptions.
3. Understanding `HttpServletResponse.isCommitted()`, `flushBuffer()`, headers, response buffers, and the limits of `@ExceptionHandler`/`/error`.
4. Reproducing failures with **Spring Boot 3.5.x + Java 17+**, Spring MVC, Thymeleaf, and an endpoint that deliberately flushes and then throws.
5. Designing DTOs, handling template nulls/missing resources, bounded payload pre-rendering/validation, and stream error protocols.
6. Comparing Spring MVC and WebFlux; investigating post-commit failures via logs/metrics/traces instead of trusting HTTP status alone.
7. Writing integration tests that distinguish **failures able to return 500** from **already-committed responses whose status cannot change**.
8. Diagnosing errors appearing **after upgrading** Spring Boot/Jackson/Thymeleaf, classpaths, or deployment images.

> **Version scope:** Spring Boot **3.5.x**, Spring Framework **6.2.x**, Java **17+**. The demo uses Spring MVC with embedded Tomcat and Jackson from `spring-boot-starter-web`, plus views from `spring-boot-starter-thymeleaf`. Exception messages, JSON error bodies, and post-commit behavior can vary across versions, embedded servers, proxies, and HTTP/1.1 vs. HTTP/2. Never hardcode a fixed status/body once a response has committed.

## 2. HTTP Pipeline: "Returning an Object" Is Not "Successfully Writing the Body"

~~~text
Client HTTP request
        |
        v
Filter chain / DispatcherServlet / route mapping
        |
        v
Controller method execution
        |
        +---- @RestController / @ResponseBody
        |          |
        |          v
        |    ReturnValueHandler
        |          |
        |          v
        |    HttpMessageConverter (Jackson, String, byte[], ...)
        |          |
        |          v
        |    HTTP response OutputStream / container buffer
        |
        +---- @Controller returns view name
                   |
                   v
             ViewResolver / Thymeleaf
                   |
                   v
             Template evaluation/render
                   |
                   v
             HTTP response Writer / container buffer
                           |
                           v
                     Socket / proxy / client
~~~

A method:

~~~java
@GetMapping("/orders/123")
public OrderDto getOrder() {
    return service.fetchOrder();
}
~~~

can finish without throwing. Only afterwards does `MappingJackson2HttpMessageConverter` serialize the return value. During serialization, Jackson may:
- Invoke a getter that throws an exception.
- Access a JPA lazy property after the Hibernate session has closed.
- Loop infinitely over a bidirectional relationship.
- Encounter a type lacking a matching serializer/module.
- Fail in a custom serializer, Java time module, proxy, or unexpected object graph.

Likewise, a controller:

~~~java
@GetMapping("/order")
public String orderPage(Model model) {
    model.addAttribute("order", service.loadOrder());
    return "order-detail";
}
~~~

only returns a **view name**. Spring still has to locate `templates/order-detail.html` and evaluate Thymeleaf/SpringEL expressions. Failures can occur inside the template, **not on the `return` line**.

### 500 Is an HTTP Signal, Not the Full Business Outcome

HTTP 500 indicates the server could not complete the request. Yet three very different situations exist:
- Controller throws before writing: error resolvers can return a clean 500.
- Controller returns an object, yet Jackson/template fails before commit: can still return 500 via the error path.
- Headers/body already committed before failing: **the status on the wire cannot change**, regardless of backend exception severity. Clients may need to detect incomplete bodies/streams at the application protocol layer.

Do not treat `http.server.requests 5xx` counts as proof that every 200 response finished cleanly: post-commit failures may not show up accurately in HTTP status metrics.

## 3. What Does a "Committed" Response Mean?

In the Servlet API, a response starts **uncommitted**. The server can still change:
- HTTP status.
- Headers and cookies.
- `Content-Type` and `Content-Length` (if known).
- Buffered bytes not yet flushed to the network.

Once the server **commits** the response, the HTTP status and headers have been finalized for transport. After that moment:
- You cannot effectively change the status on the wire.
- You cannot reset the response to send a clean replacement.
- You cannot perform normal redirects/error-forwards if they require changing status/headers.
- You cannot take back bytes already transmitted to the client.

Servlet exposes:

~~~java
HttpServletResponse response = ...;   // fragment inside a servlet/controller
boolean committed = response.isCommitted();
response.flushBuffer();               // explicitly flush and commit
~~~

If the buffer fills up, the container auto-flushes, or code calls `getWriter().flush()`, `getOutputStream().flush()`, or `flushBuffer()`, the response can commit. **"Code wrote a few bytes" does not automatically mean committed** if those bytes sit in an internal buffer. Conversely, a response can be **committed with headers alone**, before any body bytes are written.

### Illustrative State Transitions

~~~text
UNCOMMITTED
  status=200 (default)
  headers mutable
  bytes may be in servlet buffer
     |
     +-- exception here:
     |       handler/error mapping can still set status=500
     |
     +-- buffer full / flushBuffer / writer.flush / streaming
     v
COMMITTED
  status + headers can no longer be modified
  partial body may be visible
     |
     +-- exception here:
             cannot turn previously emitted response into 500
             may close/reset connection, log, or mark stream failed
~~~

**Distinction:** Different container/framework response implementations commit at different exact points. Do not rely on `response.getBufferSize()` to predict exactly which request commits; check `isCommitted()` at the point of failure and observe network behavior.

### Error Messages That Commonly Accompany This

~~~text
java.lang.IllegalStateException:
Cannot call sendError() after the response has been committed
~~~

~~~text
Cannot forward to error page ... as the response has already been committed
~~~

~~~text
Unable to handle the Spring Security Exception because
the response is already committed
~~~

Exact wording varies by version and container. The lines above are normally **secondary errors emitted when an error handler tries to modify an already-committed response**. Find the **first exception / root cause** that triggered the streaming/serialization/template failure rather than only looking at the final `Cannot call sendError` log.

## 4. Quick Classification of 500 and Related Errors

| Symptom | Typical failing step | Likely cause |
|---|---|---|
| `HttpMessageNotWritableException` | Spring MVC writing response body | Serializer error, incompatible type/converter |
| `JsonMappingException` | Jackson serializing/deserializing object | Failing getter, graph cycle, field mapping |
| `InvalidDefinitionException` | Jackson resolving serializer/deserializer | Missing serializer/module, unsupported type |
| `StackOverflowError` / Jackson nested reference | Object graph traversal | Bidirectional cycle, recursion |
| `LazyInitializationException` | Jackson touching JPA lazy proxy | Closed persistence session/transaction |
| `TemplateInputException` | Thymeleaf loading/resolving template | Wrong name, missing from JAR, resolver misconfig |
| `TemplateProcessingException` | Thymeleaf rendering expression/fragment | SpringEL failure, null, expression syntax |
| `SpelEvaluationException` | SpringEL evaluation in view | Property/method on null or invalid access |
| `HttpMessageNotReadableException` | **Reading request body**, not writing response | Malformed input JSON, usually 400 |
| `HttpMediaTypeNotAcceptableException` | Content negotiation | Cannot satisfy `Accept`, typically 406 |
| `HttpMediaTypeNotSupportedException` | Unsupported request `Content-Type` | Usually 415 |
| `IllegalStateException: response already committed` | Error handler tries to alter response post-commit | Side effect of failure after flush |
| `ClientAbortException`, broken pipe, connection reset | Client/proxy disconnects while server writes | May be client-initiated, not necessarily a code bug |
| HTTP 200 + incomplete JSON/HTML/CSV | Partial body written then failed | Needs logs and client completeness checks |
| 500 despite controller logging success | Converter/view stage failed **after controller** | Inspect outermost/root stack trace |

**Important:** not every `JsonMappingException` produces HTTP 500. When **deserializing an inbound JSON request**, the error usually becomes `HttpMessageNotReadableException` and HTTP 400 (bad client input); when **serializing a server response**, it typically becomes a server 500. Always check data direction and the stack trace.

## 5. Jackson Output Serialization: Why Can It Fail After Return?

In Spring MVC, `@RestController` equals `@Controller` + `@ResponseBody`. The returned object is converted to JSON by an `HttpMessageConverter` when the negotiated `Content-Type` matches. Boot's Jackson mapper is auto-configured with modules detected on the classpath.

Example failing getter:

~~~java
public final class UnsafeDto {
    public String getId() {
        return "o-42";
    }

    public String getStatus() {
        throw new IllegalStateException("Getter failed");
    }
}
~~~

The controller returns `new UnsafeDto()` without error. Only when Jackson calls `getStatus()` does the exception occur. Depending on serializer and container buffering, some JSON tokens may already have been written; if uncommitted, the error mapper can still return 500. Once committed, no replacement JSON error can be sent.

### Common Cause Groups

**A. Getters performing business logic or I/O**

Bad design:

~~~java
public BigDecimal getTotal() {
    return billingApi.calculateTotal(orderId); // network I/O inside getter
}
~~~

Response serialization can now fail due to downstream timeouts. DTO getters should return **precomputed data**, never trigger database or network calls during serialization.

**B. Returning JPA entities directly**

~~~java
@GetMapping("/orders/{id}")
public OrderEntity order(@PathVariable long id) {
    return repository.findById(id).orElseThrow();
}
~~~

This is a **snippet** omitting entity/repository definitions. If the entity has lazy relationships whose transaction/session closed before Jackson reads them, `org.hibernate.LazyInitializationException` occurs. Returning entities directly also exposes internal fields, cycles, and DB schema.

**Better approach:** map into immutable DTOs or service projections inside the proper transaction; fetch needed associations deliberately via `join fetch`/`EntityGraph`/query projections rather than "enabling open-in-view to silence errors" without considering N+1 and security.

**C. Cyclic graphs**

~~~text
Order -> Customer -> List<Order> -> Customer -> ...
~~~

Jackson recurses deeply and throws or overflows the stack. Prefer API DTOs that do not expose full entity graphs; consider `@JsonIgnore`, `@JsonManagedReference`/`@JsonBackReference`, or `@JsonIdentityInfo` when semantics require them. Do not hide cycles by bumping heap/stack sizes until the error stops.

**D. Missing Java Time module or custom mapper diverging from Boot**

Java time types like `LocalDateTime` require proper Jackson datatype support. Boot's JSON starter registers available modules; instantiating `new ObjectMapper()` outside Boot configuration can omit modules or consistent policies. Prefer injecting the Boot-managed mapper or configuring modules explicitly.

**E. Types lacking serializers or mismatched converters**

DTOs without property accessors, generated proxies, records with custom visibility rules, broken polymorphic type info, or returning a type with no matching converter can cause `InvalidDefinitionException`/`HttpMessageNotWritableException`. Sometimes the real problem is an `Accept`/`produces` mismatch (406), not Jackson serialization.

**F. Security data leaks via `toString`/getters**

Never let Jackson traverse password/token/credential fields. Use explicit output DTOs with whitelisted fields, and avoid logging entire object graphs on serialization failure.

## 6. Thymeleaf: Controller Returns a View Name, Rendering Fails Later

Spring MVC view resolution runs after the `@Controller` method finishes:

~~~java
@Controller
class PageController {
    @GetMapping("/page/profile")
    String profile(Model model) {
        model.addAttribute("name", "Linh");
        return "profile";
    }
}
~~~

With `spring-boot-starter-thymeleaf`, the default template path is `classpath:/templates/` with `.html` suffix. The code above requires `src/main/resources/templates/profile.html`.

### Typical Template Failures

1. Wrong view name: returning `"profile"` while the file is named `Profile.html`; Linux/containers are case-sensitive.
2. Template file placed in the wrong folder or omitted when building the JAR.
3. Another view resolver intercepts the name, or `spring.thymeleaf.prefix`/`suffix` was misconfigured.
4. Thymeleaf `th:replace` points to a missing fragment.
5. SpEL null dereference: `user.profile.name` when `user` is absent from the model.
6. Model object getter throws during template evaluation.
7. Circular fragments / recursive inclusion causing stack overflow.
8. Newer Thymeleaf/SpringEL versions enforcing stricter expression/security checks.
9. Wrong HTML encoding/escaping or unsafe `th:utext` creating XSS risks.
10. Template parsing/syntax error only surfacing at runtime, or slice tests not packaging resources the same way.

### Distinguishing Two Error Types

| Thymeleaf exception | Where to look first |
|---|---|
| `TemplateInputException` | Template not found, unreadable input, or parse failure |
| `TemplateProcessingException` | Expression, property access, or fragment/method evaluation during rendering |
| Nested `SpelEvaluationException` | Property/method expression on `null` or wrong type |
| Nested `IllegalStateException` | Getter/business method invoked by template failed |

Do not assume "500 means Thymeleaf failed" solely because the endpoint returns HTML. Inspect the **exception chain** and template filename/line/column in logs, and confirm the resource exists inside the packaged JAR.

## 7. Template Missing When Packaged in a Container

A classic upgrade/deploy incident:
- Page works in local IDE.
- JAR in Docker returns 500.
- Logs report `Error resolving template [profile]`.

Steps:
1. Verify `src/main/resources/templates/profile.html` exists in source.
2. Confirm the build tool packages resources into the executable JAR.
3. Check case-sensitive filenames on Linux (`Profile.html` != `profile.html`).
4. Check profile-specific `spring.thymeleaf.prefix` and `suffix`.
5. Confirm the template engine dependency is present and not excluded.
6. In multi-module builds, ensure the module holding templates is on the JAR's runtime classpath.
7. If `jar` is available in JDK tools, inspect packaged resources:

~~~bash
jar tf build/libs/app.jar | grep 'templates/'
~~~

The command above is for Bash/Linux/macOS. In Windows PowerShell, use:

~~~powershell
jar tf .\build\libs\app.jar | Select-String 'templates/'
~~~

Do not "fix" missing runtime resources by copying templates randomly into the working directory; the Spring Boot executable JAR classpath is the standard source. Production template caches can hold compiled views, so ensure the new image actually contains the updated resources and the rollout completed.

### Do Not Confuse `@RestController` with `@Controller`

~~~java
@RestController
class WrongViewController {
    @GetMapping("/page")
    public String page() {
        return "profile";
    }
}
~~~

Here the response body is the literal string `profile` (when negotiated), **not** rendered by Thymeleaf as a view. Use `@Controller` when returning view names. Conversely, if a JSON/text API returns a plain string, do not switch it to `@Controller` and wonder why view resolution fails.

## 8. Commit Timing: Before or After the Error?

| Failure point | Is response committed? | Can HTTP status/body still change? |
|---|---|---|
| Controller throws before writing | Usually no | Can return 500/`ProblemDetail` |
| Jackson fails while pre-serializing `byte[]` before HTTP write | No | Can return a clean 500 |
| Jackson fails after converter begins writing | Depends on buffer/flush | Yes if uncommitted; no if committed |
| Thymeleaf fails before writing output | Usually no | Can return 500/error view |
| Thymeleaf fails after writer flushed | Committed | Cannot replace already-sent output |
| `StreamingResponseBody` flushes then throws | Committed | Cannot turn into a new error response |
| `SseEmitter` sends events then fails | Usually committed | Cannot change HTTP status; needs stream protocol |
| WebFlux `Flux` emits chunks then `onError` | Usually committed | Cannot alter wire headers/status |
| Proxy already forwarded headers to client | Client may already see status | Backend cannot "take it back" |
| Client disconnects before completion | Possible | Server can no longer deliver error body to client |

**Never claim all JSON serialization occurs "all at once" before commit.** Jackson/Servlet converters can serialize and write incrementally into buffers/streams. For small payloads, the container buffer usually holds enough to allow a clean 500; large payloads, flushes, or streaming make post-commit risks explicit.

### `setStatus` Has No Effect After Commit

In Servlet:

~~~java
// Fragment inside controller/filter with HttpServletResponse response
response.setStatus(500); // if already committed, does not change sent status
~~~

Calling `sendError(500)` after commit can throw `IllegalStateException`. Handlers trying to reset the buffer after commit may fail. Adding `@RestControllerAdvice` helps **pre-commit** failures, not responses the client has already begun receiving.

## 9. Runnable Demo: Spring Boot 3.5 MVC + Thymeleaf + Post-Commit Failures

We build a project to observe each path first-hand:
- `GET /api/ok`: normal JSON.
- `GET /api/serialize-error`: returns a bean whose getter intentionally throws **during Jackson serialization**.
- `GET /api/serialize-prechecked`: proactively serializes **before returning the response**; on failure, returns a small error body with consistent status 500.
- `GET /api/committed-error`: writes `part-1`, calls `response.flushBuffer()`, and then throws.
- `GET /api/stream-error`: `StreamingResponseBody` writes/flushes a chunk and then fails asynchronously.
- `GET /page/ok`: successful Thymeleaf view.
- `GET /page/broken`: Thymeleaf view evaluating a property on null.
- `GET /page/missing`: view name with no backing template file.

**Warning:** the `*-error` endpoints are built to trigger exceptions on purpose. Run **locally/in tests only**, never expose in public/production deployments.

### 9.1. Gradle Dependencies

Scaffold from Spring Initializr:
- Boot **3.5.x**, Java **17+**, Gradle Groovy, artifact `commit-error-demo`.
- Dependencies: **Spring Web**, **Thymeleaf**, **Spring Boot Actuator** (optional for metrics), and **Spring Boot Starter Test**.

In Initializr's `build.gradle`, the `dependencies` block looks like:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a **Gradle snippet**; keep the plugins, repositories, versions, and wrapper generated by Initializr. Do not pin Jackson versions manually; Spring Boot dependency management keeps versions aligned.

### 9.2. Complete Java File

Create `src/main/java/demo/commiterror/CommitErrorApplication.java`:

~~~java
package demo.commiterror;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonPropertyOrder;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class CommitErrorApplication {

    public static void main(String[] args) {
        SpringApplication.run(CommitErrorApplication.class, args);
    }
}

@RestController
class DemoApiController {

    private static final byte[] SAFE_ERROR = (
        "{\"type\":\"about:blank\","
        + "\"title\":\"Internal Server Error\","
        + "\"status\":500}"
    ).getBytes(StandardCharsets.UTF_8);

    private final ObjectMapper mapper;

    DemoApiController(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public record GoodPayload(String message, int count) { }

    @JsonPropertyOrder({"first", "second"})
    public static final class BrokenPayload {
        public String getFirst() {
            return "ok";
        }

        public String getSecond() {
            throw new IllegalStateException(
                "Deliberate failure inside a JSON getter");
        }
    }

    @GetMapping(
        path = "/api/ok",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public GoodPayload ok() {
        return new GoodPayload("ok", 1);
    }

    @GetMapping(
        path = "/api/serialize-error",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public BrokenPayload serializeError() {
        // Controller completes; Jackson invokes getSecond later.
        return new BrokenPayload();
    }

    @GetMapping(
        path = "/api/serialize-prechecked",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<byte[]> serializePrechecked() {
        try {
            // Do JSON work BEFORE HttpMessageConverter starts writing.
            byte[] json = mapper.writeValueAsBytes(
                new BrokenPayload());

            return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(json);
        } catch (JsonProcessingException ex) {
            // Deliberately return a minimal, non-sensitive error.
            // The HTTP response has not been written here yet.
            return ResponseEntity.status(
                    HttpStatus.INTERNAL_SERVER_ERROR)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(SAFE_ERROR);
        }
    }

    @GetMapping(
        path = "/api/committed-error",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public void committedError(HttpServletResponse response)
            throws IOException {

        response.setStatus(HttpStatus.OK.value());
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");

        response.getWriter().write("part-1\n");
        response.flushBuffer(); // explicitly COMMIT 200 + headers
        System.out.println(
            "DEMO_AFTER_COMMIT=" + response.isCommitted());

        // Spring cannot replace the already-sent status/body with 500.
        throw new IllegalStateException(
            "Deliberate error after flushBuffer");
    }

    @GetMapping(
        path = "/api/stream-error",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public StreamingResponseBody streamError() {
        return output -> {
            output.write(
                "first-chunk\n".getBytes(StandardCharsets.UTF_8));
            output.flush(); // commits response
            throw new IOException("Deliberate streaming failure");
        };
    }
}

@Controller
class DemoPageController {

    @GetMapping("/page/ok")
    public String ok(Model model) {
        model.addAttribute("name", "Linh");
        return "ok";
    }

    @GetMapping("/page/broken")
    public String broken() {
        // broken.html tries to evaluate a missing model variable.
        return "broken";
    }

    @GetMapping("/page/missing")
    public String missing() {
        // No corresponding templates/missing.html file.
        return "missing";
    }
}
~~~

### 9.3. Notes on Why This Source Is Runnable

- The file has a single public top-level class `CommitErrorApplication`, matching the filename.
- The two package-private classes `DemoApiController` and `DemoPageController` are in the same package and get component-scanned.
- `ObjectMapper` is constructor-injected from Spring Boot's configured Jackson mapper; do not construct `new ObjectMapper()`.
- `BrokenPayload.getSecond()` reliably throws when Jackson serializes `second`. Wrapping it as `JsonProcessingException` matches Jackson mapping semantics; the HTTP status on the direct endpoint still depends on commit/error handling.
- `@JsonPropertyOrder` enforces property order intentionally, yet **does not** guarantee the same commit state across different transports/buffering.
- `serializePrechecked()` calls `mapper.writeValueAsBytes(...)` inside the controller, catching serialization failures **before handing a body to the HTTP writer**. The catch block returns a small UTF-8 array with status 500 and `application/problem+json`. This demo illustrates deterministic error responses, **not a recommendation to pre-serialize huge payloads**.
- `committedError()` calls `flushBuffer()` to force the response committed before throwing. `DEMO_AFTER_COMMIT=true` is expected at that point per the Servlet API. **Do not expect clients to receive a JSON 500.**
- `StreamingResponseBody` has an async lifecycle; Spring MVC may need a configured `AsyncTaskExecutor` in production. Failing after flush illustrates the failure path, not a useful streaming endpoint.
- `@Controller` returns template names rather than raw text like `@RestController`.
- The `Map` import is unused and only kept for easy extension; Java compilers allow unused imports, though IDEs may warn.

### 9.4. Thymeleaf Templates

Create `src/main/resources/templates/ok.html`:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="utf-8">
  <title>Valid Page</title>
</head>
<body>
  <h1 th:text="${name}">Fallback</h1>
</body>
</html>
~~~

When `/page/ok` is requested, Thymeleaf replaces the fallback with `Linh`, HTML-escaped as text. Returning HTML containing `Linh` confirms rendering succeeded. Do not assert exact HTML whitespace/formatting in tests.

Create `src/main/resources/templates/broken.html`:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="utf-8">
  <title>Intentionally Broken Page</title>
</head>
<body>
  <p>Page before expression.</p>
  <p th:text="${user.profile.name}">Missing user</p>
</body>
</html>
~~~

The `/page/broken` controller never adds a `user` model attribute. Thymeleaf/SpringEL attempts to dereference `user.profile.name` on null → throws during template processing. Commit timing depends on template output buffering; do not assert an exact error body.

**Do not create** `templates/missing.html`. `/page/missing` returns view name `missing` so Thymeleaf raises `TemplateInputException` when the file is absent. Creating that file stops the endpoint from reproducing the error.

### 9.5. `application.yml`

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-stacktrace: never
    include-exception: false

spring:
  thymeleaf:
    cache: false

management:
  endpoints:
    web:
      exposure:
        include: "health,metrics"
~~~

- `server.error.include-message=never` and `include-stacktrace=never` limit error details sent to clients.
- `spring.thymeleaf.cache=false` is for **development/testing**, making template edits easier to inspect; production should enable caching appropriately.
- Expose only Actuator health/metrics locally; production must protect management endpoints via auth/network policies and never make diagnostics public.
- Never enable `server.error.include-stacktrace=always` to debug production; use authorized server logs/traces.
- Disabling cache will not fix templates missing from a packaged JAR.

### 9.6. Running the Application

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once started, the app listens on `http://localhost:8080`.

## 10. Observing Four Different Response Behaviors with `curl`

### 10.1. Successful JSON Endpoint

~~~bash
curl -sS -i \
  -H 'Accept: application/json' \
  http://localhost:8080/api/ok
~~~

Expect status **200** and body fields:

~~~json
{"message":"ok","count":1}
~~~

Field ordering is not guaranteed, while names and values match the above.

### 10.2. Serialization Failure After Controller

~~~bash
curl -v \
  -H 'Accept: application/json' \
  http://localhost:8080/api/serialize-error
~~~

Inspect server logs: `getSecond()` throws, and Jackson wraps it into `JsonMappingException`/`HttpMessageNotWritableException`. If the response is uncommitted, the framework/container can return HTTP 500 with error JSON/HTML per negotiation and Boot error handling. If already committed, the outcome can differ. **Do not assume a specific 500 JSON output as guaranteed across every version.**

### 10.3. Pre-Validation Before Writing the Response

~~~bash
curl -sS -i \
  http://localhost:8080/api/serialize-prechecked
~~~

In this demo, `mapper.writeValueAsBytes(new BrokenPayload())` throws `JsonProcessingException`, and the controller **explicitly** returns status 500 with body:

~~~json
{"type":"about:blank","title":"Internal Server Error","status":500}
~~~

This output is generated by the demo code itself, independent of Boot's automatic `/error` format. Still, if an error occurs after bytes are returned or filters/proxies intervene, commit rules still apply; do not call this a **global guarantee** across all networks/servers.

### 10.4. Deliberately Committing 200 and Then Throwing

~~~bash
curl -v \
  http://localhost:8080/api/committed-error
~~~

The server called `flushBuffer()` before throwing. Demo logs should show:

~~~text
DEMO_AFTER_COMMIT=true
~~~

The response typically has status **200** with a body starting:

~~~text
part-1
~~~

Then the connection may close, an async/servlet error may be logged, or the client may receive a truncated body. There is no guarantee a clean terminating line appears; **the invariant is that committed status/headers cannot be changed to 500**. If you see a server stack trace alongside HTTP status 200, this is exactly why diagnosing solely via HTTP status metrics fails.

### 10.5. Streaming Error

~~~bash
curl -v -N \
  http://localhost:8080/api/stream-error
~~~

The body starts with `first-chunk` followed by `IOException`. `curl` may report a receive error, transfer closed unexpectedly, or no specific message depending on framing and server. `-N` disables curl's output buffering so chunks show up sooner; it does not force Spring to flush if the server hasn't sent bytes yet.

### 10.6. Valid and Broken Templates

~~~bash
curl -sS -i http://localhost:8080/page/ok
curl -v http://localhost:8080/page/broken
curl -v http://localhost:8080/page/missing
~~~

Expect `/page/ok` to return 200 and HTML containing `Linh`. The other two endpoints trigger template rendering/resolution errors and can return 500 if the response is still mutable. Inspect Thymeleaf stack traces to distinguish **missing template** from **null expression**, instead of relying on identical HTTP statuses.

## 11. `@ExceptionHandler`, `/error`, and `ProblemDetail` Only Help Before Commit

Spring MVC uses a chain of `HandlerExceptionResolver`s such as:
- `ExceptionHandlerExceptionResolver`: `@ExceptionHandler` / `@ControllerAdvice`.
- `ResponseStatusExceptionResolver`.
- `DefaultHandlerExceptionResolver`.
- Boot also provides `/error` mapping and `BasicErrorController`/error pages per config.

When an exception is caught before commit, the framework can build a clean error response. Example snippet:

~~~java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ProblemDetail> handle(IllegalArgumentException ex) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, "Invalid request");
        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Required imports:
- `org.springframework.web.bind.annotation.RestControllerAdvice`.
- `org.springframework.web.bind.annotation.ExceptionHandler`.
- `org.springframework.http.ProblemDetail`.
- `org.springframework.http.ResponseEntity`.
- `org.springframework.http.HttpStatus`.

This is a **standalone snippet separate from the main demo**. It shows that errors occurring **before HTTP write** can be mapped to RFC 9457 `ProblemDetail`. It **cannot save** a response that has already committed. `ProblemDetail` itself must also be serialized; if an error occurs inside a custom error converter/serializer, the error handler can fail too.

### Problem Details Is Not a Root-Cause Cure

Spring MVC supports RFC 9457, and Boot 3.x has properties enabling Problem Details for certain framework exceptions depending on version. Turning the property on changes the **pre-commit error response shape**, not the laws of HTTP:
- It cannot alter a status already sent.
- It cannot retract JSON tokens already emitted.
- It cannot turn an SSE/`Flux` mid-stream failure into HTTP 500.
- It cannot undo database side effects committed before a network error.

### When Requests Pass Through a Proxy

Suppose the application sends `HTTP/1.1 200 OK` and a few kilobytes of JSON to a reverse proxy. The proxy may:
- Forward status 200 to the client immediately and close the stream later.
- Buffer the response and emit 502 if upstream drops mid-transfer (depending on config).
- Deliver a partial body or log `upstream prematurely closed connection`.
- With HTTP/2, reset the stream while browser DevTools still shows the initial status.

Never assume "proxies always return 502." Correlate client headers, proxy access/error logs, upstream logs, and request IDs.

## 12. Once Committed, What Is the Right Handling?

**Do not** attempt `sendError(500)`, `sendRedirect(...)`, or serializing a new error object into the middle of an already-started JSON body—none of those can produce a valid HTTP 500 response. Instead:

1. Log the error in the component where it actually occurred, including phase, route, request/trace ID, and committed state if available.
2. Never log full bodies, tokens, cookies, or sensitive data.
3. Per framework/transport lifecycle, terminate the stream / close the connection cleanly; do not write arbitrary bytes after `IOException`.
4. For protocols supporting message-level errors, emit a **structured error event** if the stream is still writable and an error frame is valid.
5. Clients must verify **application-level completeness**, never equating "status 200" automatically with "complete file/result."
6. Side-effecting operations need operation IDs, idempotency, or status lookups; post-commit failure does not mean the transaction failed.
7. Design retry/backoff/resume semantics for streaming downloads/SSE on disconnect.
8. Track post-commit failures separately from HTTP 5xx metrics.

### HTTP Body vs. Application Protocol

An API returning **a single JSON object** cannot remain valid if it suddenly appends:

~~~text
{"data":[1,2,
{"error":"failed"}
~~~

That produces invalid JSON. With **NDJSON**, a protocol can define a final line like `{"type":"error",...}`; with SSE, `event: error`—but there must be an explicit contract defining a **terminal success/error signal** checked by clients.

Example NDJSON protocol concept:

~~~text
{"type":"item","value":1}
{"type":"item","value":2}
{"type":"error","code":"UPSTREAM_TIMEOUT"}
~~~

The client knows the stream failed because of the error record; **HTTP status may still be 200** due to commit. If the connection drops before sending the error record, the client detects the missing terminal completion marker or times out. Never emit a fake error record shaped like a business item if downstream parsers lack a discriminating schema.

## 13. Spring WebFlux: Failures After `Flux` Begins Emitting

WebFlux uses `HttpMessageWriter`, Reactor `Mono`/`Flux`, and `ServerHttpResponse`. Similar boundary:
- `Mono.error(...)` **before** headers/body commit: the framework error handler can return 500.
- `Flux` emits several `DataBuffer`/NDJSON/SSE frames, the writer flushes, and then `onError` fires: the HTTP response may already be committed; status cannot change.
- `ServerHttpResponse.isCommitted()` checks commit state on the reactive response abstraction.
- `setStatusCode(...)` returns `false` when the status change cannot apply because the response is already committed (per API contract).
- `beforeCommit(...)` registers an action to run prior to commit, not a hook to fix status **after** commit.

WebFlux snippet:

~~~java
// Fragment inside a WebFlux handler with ServerHttpResponse response.
if (!response.isCommitted()) {
    response.setStatusCode(HttpStatus.INTERNAL_SERVER_ERROR);
    return response.setComplete();
}

// Response already committed: do not attempt to rewrite status/body.
return Mono.error(originalFailure);
~~~

Imports:
- `org.springframework.http.server.reactive.ServerHttpResponse`.
- `org.springframework.http.HttpStatus`.
- `reactor.core.publisher.Mono`.

This is a **snippet**, where `originalFailure` is the existing exception; it is not a standalone global `WebExceptionHandler`. A real `WebExceptionHandler` must integrate properly with the chain, logging, cancellation, and data buffers. Repeated logging across layers can duplicate stack traces.

### Common Reactive Cases

~~~java
// Illustrative publisher stream snippet (not a full controller):
Flux<String> source = Flux.just("a", "b")
    .concatWith(Flux.error(
        new IllegalStateException("late reactive error")));
~~~

If written as NDJSON/SSE with elements flushed as emitted, the client may see `"a"`, `"b"`, and then an errored stream; response status does not turn into 500. If the codec **aggregates** the publisher before writing (depending on `Content-Type`/return type), the error occurs before commit. **Do not deduce commit state solely from `Flux`**: observe media type, writer, and flush boundaries.

### Managing `DataBuffer` Ownership

When custom reactive handlers allocate/consume `DataBuffer`s, follow pooled-buffer retain/release semantics. A post-emit serialization error can also leak buffers if the app retains `DataBuffer` references or ignores cancellation. Let the framework writer own handed-off buffers; release inbound buffers you consume yourself when required. Never call `DataBufferUtils.release` prematurely while the outbound writer is still reading.

## 14. Thymeleaf Errors: Preventing Failures Before Commit

Useful rules:
- Never invoke database or web clients from getters of objects rendered in templates.
- Prepare the view model **before** returning the template name.
- For optional data, use null-safe expressions compatible with your SpringEL/Thymeleaf version, or supply defaults from the controller.
- Verify template presence inside the packaged artifact during builds.
- Test fragments, layout dialects, and differences across Thymeleaf upgrades.
- Use `th:text` for user text so HTML is escaped; use `th:utext` only for trusted, pre-sanitized HTML per security policy.
- Never rely on disabling template caching to fix missing resources.
- Use consistent view-name casing; avoid ambiguous resolvers or fragment paths.
- For high-reliability HTML pages, you may pre-render into a buffer before commit **if size/latency allow**, though templates needing request/web context must receive the real context rather than mechanically becoming static strings.

### Error Templates Can Fail Too

If `templates/error/500.html` accesses a null model attribute or missing fragment, error handling fails a second time. Keep error pages **simple, self-contained, and free of DB/remote calls**, rather than rendering complex views that repeat the same failure.

Boot supports custom error templates/static resources in the `error` directory by status (e.g., `500.html` or `5xx`). These pages only render during error dispatch when the response **is still replaceable**; they cannot overwrite already-flushed HTML bodies.

## 15. Why Do Errors Appear Only After an Upgrade?

Upgrade regression categories:
- Boot/Spring Framework/Jackson/BOM versions **out of sync** due to manual dependency overrides.
- Changed Jackson module/serializer behavior or incompatible custom getters.
- Missing `jackson-datatype-jsr310` when creating a custom mapper or dropping starters.
- Altered Hibernate/JPA lazy fetching due to transaction boundaries or OSIV settings.
- Stricter Thymeleaf/SpringEL expression checks or deprecated syntax.
- Template files dropped after changing build/multi-module/container image layouts.
- Legacy `javax.servlet.*` code brought into Boot 3 (`jakarta.servlet.*`) causing classloading/method mismatches.
- Custom `HttpMessageConverter`/`WebMvcConfigurer` unintentionally replacing default converters.
- Changes to content negotiation, controller return types, `produces`, or `Accept` headers.
- Filters/interceptors calling `flushBuffer`/`getWriter().flush` earlier, or altered compression/proxy buffering.
- Spring Security exception handling behavior when an auth error occurs after streaming has committed.

### Distinguishing Source Bugs from Dependency Drift

If you see `NoSuchMethodError`, `ClassNotFoundException`, `NoClassDefFoundError`, or `LinkageError` after upgrading, check **runtime dependency graph / BOM alignment** first. Never paper over it by catching `Exception.class` and returning a generic 500.

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

Use the project's dependency management properly, remove unnecessary Jackson/Spring version overrides, run clean rebuilds/tests, and compare the packaged JAR against IDE classpath. An external-servlet-container WAR has different dependency/classloader behavior from an executable JAR; verify against your target packaging.

## 16. Testing the Right Things

**Four non-interchangeable test categories:**

1. **Unit serialization tests**: serialize real DTOs/records using the Boot-injected `ObjectMapper` to catch accessors/modules/cycles before HTTP.
2. **MVC view integration tests**: render Thymeleaf with complete and missing model attributes, fragments, and packaged resources.
3. **Real HTTP integration tests**: start an embedded server, use a real HTTP client, and verify status + body + socket behavior.
4. **Streaming/cancellation/proxy tests**: use a real HTTP client through container/ingress to test partial responses, completion markers, disconnects, and error metrics.

Never rely solely on `MockMvc` to claim a response committed over a socket; mock response buffers and container-specific flush behavior differ across Tomcat/Jetty/Netty.

### 16.1. Complete Java 17 Integration Test

Create `src/test/java/demo/commiterror/CommitErrorApplicationTests.java`:

~~~java
package demo.commiterror;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CommitErrorApplicationTests {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private HttpResponse<String> get(String path) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:" + port + path))
            .GET()
            .build();
        return client.send(
            request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void validJsonEndpointWorks() throws Exception {
        HttpResponse<String> response = get("/api/ok");
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"message\":\"ok\""));
        assertTrue(response.body().contains("\"count\":1"));
    }

    @Test
    void jacksonFailureExistsIndependentOfHttp() {
        assertThrows(JsonProcessingException.class, () ->
            mapper.writeValueAsBytes(
                new DemoApiController.BrokenPayload()));
    }

    @Test
    void prevalidatedFailureHasStable500Body() throws Exception {
        HttpResponse<String> response =
            get("/api/serialize-prechecked");

        assertEquals(500, response.statusCode());
        assertTrue(response.body().contains("\"status\":500"));
        assertTrue(response.body().contains(
            "\"title\":\"Internal Server Error\""));
    }

    @Test
    void validThymeleafPageRenders() throws Exception {
        HttpResponse<String> response = get("/page/ok");
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("Linh"));
    }
}
~~~

Tests run with JUnit 5, Java 17 HTTP client, random embedded port, and Boot-injected `ObjectMapper`. Do not assert JSON field ordering. `/api/serialize-prechecked` guarantees status 500 because the controller serializes before returning. Conversely, **do not** write a test expecting a fixed 500 status for `/api/committed-error` or `/api/stream-error`, because they deliberately commit first and then fail, meaning the test HTTP client may observe the earlier status or a network exception.

Run:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**Do not claim tests ran** in every environment; these are instructions and code for the learner to execute. When running them, inspect logs of the intentional failure endpoints separately to recognize error-handling double logging.

### 16.2. Template Test Coverage

Consider adding tests (via HTTP tests or MVC testing):
- View `/page/ok` exists, model has `name` → 200 + expected text.
- View `/page/broken` hits null expression in Thymeleaf, logs show template/line.
- View `/page/missing` fails due to missing resource in packaged JAR.
- Re-test rendering after deploying JAR/image, not only in IDE.
- Test custom error templates when an exception occurs **before commit**.
- Test a failing getter in a template without exposing secret values.
- Test fragment/layout changes when upgrading Thymeleaf.
- When content negotiation applies, test both `Accept: text/html` and `Accept: application/json` over HTTP.

Never assert an HTML stack trace returned to clients. Production must avoid leaking exception types or stack traces.

### 16.3. What Should Post-Commit Tests Observe?

For `/api/committed-error`:
- Java logs `DEMO_AFTER_COMMIT=true`.
- Java logs the initial root error thrown after flush.
- Client already received initial status/headers; may see 200 and partial body.
- If a proxy buffers the full response, the client may see 502, reset, or another status.
- No valid JSON 500 replaces the emitted portion.
- HTTP 5xx metrics may **not increment** for post-commit business failures.

For `/api/stream-error`:
- Client may see `first-chunk` before failure.
- Servlet async error dispatch may run, yet cannot rewrite committed headers.
- Log the `stream_write` stage and committed state; record a separate stream-completion flag if business logic requires it.
- Keep a clean, completing stream as a control case for comparison.

## 17. Designing to Detect Errors Before HTTP Write

For small, business-critical JSON responses:
1. Perform validation and mapping into response DTOs inside the service.
2. Never make DTO getters call databases or networks.
3. If serialization certainty is required, use the injected Boot `ObjectMapper` to create a bounded `byte[]` before returning.
4. If serialization fails, return 500/`ProblemDetail` with a small, safe message.
5. Return `byte[]` via `ByteArrayHttpMessageConverter` with a consistent content type.
6. Test DTO shapes and null/missing values at the integration layer.

**Trade-off:** pre-serialization adds memory allocation and copies, especially for large responses at high concurrency. Do not apply it to large files or streams; use NDJSON/SSE streaming protocols with completion semantics, or background jobs + status URLs instead.

### Pre-Validating Template Rendering

For very small pages that must be guaranteed to render before headers are sent, you can render the template to a `String`/`byte[]` **before** returning. However:
- Thymeleaf templates need the right context; web-specific expressions, CSRF attributes, request locale, and link rewriting depend on the request.
- Doubles memory/copy cost on large pages.
- Can increase latency/GC pressure.
- Never advise "rendering every template to a String" as a blanket rule.

Usually a better approach is **testing packaged resources/models + keeping templates minimal + avoiding I/O in getters**.

## 18. Observability: A 5xx Counter Is Not Enough

A helpful log entry might include:

~~~text
level=ERROR
event=response_write_failed
route=/api/orders/{id}
phase=jackson_serialization
response_committed=true
bytes_written=8192
trace_id=<opaque-id>
exception=JsonMappingException
~~~

This is an **illustrative log schema**, not a default Spring Boot log line. Never log raw order IDs, JWTs, cookies, or JSON bodies. For template errors:

~~~text
level=ERROR
event=template_render_failed
view=order-detail
phase=thymeleaf_process
response_committed=false
exception=TemplateProcessingException
trace_id=<opaque-id>
~~~

### Metrics to Categorize

| Metric / label you can instrument | Meaning |
|---|---|
| `http.server.requests` | HTTP status/latency seen by the framework |
| `app.response.serialization.failures` | Jackson response serialization failures |
| `app.template.render.failures` | Template engine failures |
| `app.response.after_commit.failures` | Exceptions after response committed |
| `app.stream.completed` | Whether streams achieved terminal success |
| `app.stream.partial.failures` | Streams failing before completion marker |
| `app.error.handler.failures` | Error rendering/dispatch itself failing |
| `app.client.disconnected` | Broken pipes / client cancellations as detectable |

`app.*` names are **suggested metric names**, not created by Boot by default. Avoid unbounded label cardinality (raw URLs, raw trace/request/user IDs). A backend returning HTTP 200 whose stream completion marker is missing must be tracked as a **business failure** even when absent from 5xx counters.

### Root Cause vs. Secondary Exception

Look in logs for:
1. The **earliest** exception matching the trace/request ID.
2. Class and stack location of the Jackson/Thymeleaf/business getter.
3. If `response already committed` appears, find **who called flush/write** prior to the exception.
4. Check async threads/coroutines/`Flux` chains and context propagation.
5. Cross-check proxy access/error logs at the same timestamp.
6. Compare client evidence: status, headers, body length, transfer error.
7. Separate routine client aborts from preceding business bugs.

Enable targeted DEBUG logs in test environments if needed; **never** enable full HTTP body logging or sensitive stack traces in production.

## 19. Post-Commit Failures with Filters, Compression, and Security

Besides controllers and converters, responses can be committed by:
- A filter calling `response.flushBuffer()`.
- Logging/filter wrappers copying bodies and flushing early.
- Security filters writing an error/redirect or CSRF response and continuing the chain.
- Compression layers streaming data out early.
- Server `sendfile` / large file transfers.
- `ResponseBodyEmitter`/`SseEmitter` emitting events.
- View engines rendering HTML incrementally.
- Async processing combined with servlet container buffer capacity.
- Proxy buffering / HTTP/2 frame handling.

If a filter calls `sendError(401)` **after** a handler already wrote/flushed 200, you get a "response already committed" exception instead of status 401; that is a lifecycle-ordering bug. Authentication/authorization must execute **before** writing protected responses. Never fix this by ignoring the exception or trying to send a second response body.

### `ContentCachingResponseWrapper` Can Mask Symptoms Without Fixing the Root Cause

Some filters use `ContentCachingResponseWrapper` to buffer the response and copy the body at the end. It can delay commit in certain cases, yet:
- Adds memory overhead proportional to body size and concurrency.
- Breaks unbounded streams, SSE, and large downloads.
- Can distort streaming flush semantics.
- Forgetting `copyBodyToResponse()` yields an empty response body.
- Does not fix failing Jackson getters, missing templates, or downstream I/O errors.

Do not install a global wrapper just to "force every response into a clean 500."

## 20. Handling Streams with Completion Protocols

### 20.1. NDJSON / Line-Delimited Protocol

Example response protocol:

~~~text
{"type":"start","streamId":"s1"}
{"type":"item","index":1,"value":100}
{"type":"item","index":2,"value":200}
{"type":"complete","count":2}
~~~

If an exception occurs before `complete`:
- If frames can still be written, the server may emit `{"type":"error","code":"UPSTREAM_FAILURE"}`.
- If the network already broke, no frame can be sent; the client sees the missing terminal marker and treats the stream as incomplete.
- HTTP status may already be 200; clients **must not treat 200 + the first two items as full success**.

Clients should implement timeouts, max byte caps, ack/resume cursors, and idempotency policies. Never send a terminal error frame in a stream that downstream parsers mistake for a business item.

### 20.2. SSE

SSE can use:
- `event: item`, `id: ...` for data.
- `event: error` with a safe error code if the connection is still writable.
- `event: complete` before closing cleanly when the protocol calls for it.

If the connection drops before `complete`, client reconnects using `Last-Event-ID` work **only if the server stores an event log/replay state**. Never configure infinite requests expecting graceful shutdown to keep sockets open forever.

### 20.3. File Downloads

For file downloads:
- Providing an accurate `Content-Length` lets some clients detect truncated bodies.
- HTTP chunked/trailers and proxy behavior vary across stacks.
- Attach a checksum/content hash when the contract supports it.
- Download to a temporary file and rename to final only after full byte count/hash verification.
- For heavy operations, consider async generation and serving the completed file rather than serializing within a single HTTP request.

HTTP 200 alone never proves file integrity.

## 21. Upgrade Checklist: Diagnose by What Changed, Not Guesswork

When 500s appear right after an upgrade:
1. Record Boot/Spring/Jackson/Thymeleaf/Hibernate versions before and after.
2. Inspect the runtime dependency graph, especially overrides conflicting with the Boot BOM.
3. Read the root stack trace; classify converter, template, or post-commit failure.
4. Test response DTOs with Boot's `ObjectMapper` against production-representative object graphs.
5. Check JPA lazy loading, N+1, and entity exposure after fetch-policy changes.
6. Verify template resources, fragment names, and casing **inside the executable JAR**.
7. Check template security changes: SpringEL, method calls, and null expressions.
8. Check `Content-Type`/`Accept`, `produces`, and converter order.
9. Compare filter/interceptor logic, response wrappers, and flush calls.
10. Run real HTTP tests right before/after changing server stacks or proxies.
11. Check Java `jakarta.servlet` migration if moving from Boot 2.x to Boot 3.x.
12. Verify container images build from the new source rather than stale Docker layers.
13. Maintain a rollback/canary plan, monitoring both 5xx **and** post-commit failures.
14. Never relax Jackson strictness or expose public stack traces just to "pass QA."

**If errors occur only in production**, inspect real payload shapes, proxy buffering, HTTPS/compression, timeouts, concurrency, JPA data cycles, and sizes exceeding servlet response buffers. Tiny test payloads often fail to trigger commit timing.

## 22. Practical 10-Step Investigation Workflow

1. **Identify the endpoint** and response type: JSON, HTML/Thymeleaf, stream, SSE, or file.
2. **Reproduce** with `curl -v`, recording headers, status, bytes, and transfer errors; never paste private tokens.
3. **Find the earliest exception** by `traceId` in app logs.
4. **Classify the stage**: handler → converter → template → transport/write → error handler.
5. **Check `isCommitted()`** where the error is caught if API/context permits, without instrumentation altering commit timing.
6. **Read the nested cause**: Jackson getter, lazy init, template line/fragment, `IOException` client abort.
7. **Correlate proxy logs** to see what the client actually received.
8. **Unit test** `ObjectMapper` serialization and template model rendering.
9. **Fix the root cause** (DTO/mapper/template/stream protocol) instead of just catching exceptions.
10. **Add regression tests + metrics** for both pre-commit 500 and post-commit partial responses.

### Safe Command to Inspect Headers and Body

~~~bash
curl --verbose --show-error \
  --output response.bin \
  http://localhost:8080/api/committed-error
~~~

Inspect `response.bin` if created, comparing against expected body bytes. Locally you can check:

~~~bash
wc -c response.bin
~~~

If `curl` exits nonzero due to a connection error, **do not equate "a file was created" with success**. With HTTP/2/Ingress, a connection can reset after headers and clients report differing errors.

### Should Client Disconnect Errors Count as 500?

Not automatically. A browser closing a tab mid-stream can trigger `IOException: Broken pipe` even when the app is healthy; continuing to write after disconnect raises an exception. Separate `client_aborted` from `serialization_failure` and `application_stream_failure`. Use rate and impact to gauge severity; not every disconnect deserves a pager alert.

## 23. Anti-Pattern and Alternative Matrix

| Anti-pattern | Consequence | Better approach |
|---|---|---|
| Returning JPA Entities directly as JSON | Lazy proxies, cycles, data leaks | Map to DTO/projection |
| DTO getters calling DB/HTTP | I/O failures during Jackson write | Compute data in service before return |
| Catching all Exceptions and returning 200 + `{"error":...}` | Breaks HTTP semantics, hides alerts | Return 4xx/5xx while uncommitted |
| `@ExceptionHandler` calling `sendError` after flush | Secondary `IllegalStateException` | Stop writing; log, design stream protocol |
| Unnecessary early `flushBuffer()` | Cannot roll back error responses | Flush only for real streaming |
| Writing error objects into mid-stream JSON arrays | Body becomes invalid JSON | Use NDJSON/SSE with typed terminal frames |
| Returning view names from `@RestController` | Emits literal string instead of HTML | Use `@Controller` |
| Template expressions dereferencing null | Thymeleaf processing errors | Validate model / null-safe fallbacks |
| Missing templates inside JAR | Runtime 500 | Build/resource packaging tests |
| Disabling Thymeleaf cache to fix production | Doesn't fix missing resources, adds cost | Fix template paths/build |
| Creating `new ObjectMapper()` ad-hoc | Missing Boot modules/config | Inject configured mapper |
| Pre-serializing 500 MiB into `byte[]` before HTTP | Heap/GC/OOM pressure | Streaming / async generation |
| Using `ContentCachingResponseWrapper` on all streams | Memory bloat / broken buffer semantics | Targeted instrumentation; don't cache everything |
| Alerting only on HTTP 5xx | Misses 200 + partial body | Track stream completion / post-commit errors |
| Returning stack traces on 500 | Leaks paths/classes/secrets | Safe `ProblemDetail` + server logs |
| Asserting fixed status 500 post-commit | Flaky tests / wrong protocol | Assert committed state + observed truncation behavior |
| Blindly retrying POST after dropped connection | Duplicate side effects | Idempotency keys / status lookups |
| Upgrading Jackson/Spring outside the BOM | Linkage / runtime serializer bugs | Align dependency versions, add regression tests |

## 24. Review Questions

**1.** Why can a controller return `OrderDto` cleanly yet the HTTP call still end in 500?

**Answer:** Jackson response serialization runs after the controller returns. Getters, modules, or object graphs can fail while `HttpMessageConverter` writes the body.

**2.** Does returning a valid template view name guarantee Thymeleaf renders cleanly?

**Answer:** No. Spring still has to resolve the resource and evaluate expressions/fragments; templates may be missing or model properties null.

**3.** What is a committed response?

**Answer:** Status and headers have been sent or finalized by the container HTTP response lifecycle; they can no longer be changed into a different error response.

**4.** Does writing a few bytes to the response always mean it is committed?

**Answer:** Not necessarily. Bytes can sit inside the servlet buffer. `flushBuffer`, buffer overflow, or explicit flushes trigger commit.

**5.** When an exception occurs after commit, can `@ExceptionHandler` still return 500?

**Answer:** It cannot change the already-sent HTTP status. It can log/clean up, not rewrite the response already delivered to the client.

**6.** Is `Cannot call sendError() after the response has been committed` the root cause?

**Answer:** No. It is usually a secondary error caused by an error handler attempting to change the response; locate the earlier Jackson/template/stream/client-abort exception.

**7.** Why can HTTP 200 still represent a failure?

**Answer:** The body may be truncated after headers, missing a terminal marker, or unparseable; the server may have logged a severe exception without changing the wire status.

**8.** Which direction does `HttpMessageNotReadableException` usually belong to?

**Answer:** Deserializing an **inbound request body**; malformed JSON typically returns 400, unlike `HttpMessageNotWritableException` when serializing output.

**9.** What does `TemplateInputException` typically point to?

**Answer:** Missing/unreadable template or input parsing error; check classpath files, casing, resolvers, and JAR packaging.

**10.** How should `LazyInitializationException` during serialization be fixed?

**Answer:** Design DTOs/projections and fetch associations inside the right transaction; never return entities/proxies directly for Jackson to traverse.

**11.** Why can the demo's `serialize-prechecked` endpoint reliably return 500?

**Answer:** `ObjectMapper` serialization runs **before** the HTTP writer receives the body; the controller catches the exception and returns a `ResponseEntity` with a small error `byte[]` and status 500.

**12.** Should you pre-serialize every 100 MiB response to avoid post-commit errors?

**Answer:** No. Memory, copying, and GC spikes would be severe. Use bounded payloads or streaming protocols with completion semantics.

**13.** When a `Flux` has already emitted NDJSON items and then triggers `onError`, can HTTP status change to 500?

**Answer:** No if the response already committed. Clients should rely on error/completion frames and detect disconnects.

**14.** Does returning `"profile"` from `@RestController` render `profile.html`?

**Answer:** No, it normally returns the literal body `profile`. Use `@Controller` for view resolution.

**15.** Is testing committed responses with `MockMvc` sufficient instead of a real socket test?

**Answer:** No. Mock response buffering/flushing differs from real container/proxy behavior. Real HTTP tests are required for post-commit scenarios.

**16.** Why can 500 metrics miss streaming failures?

**Answer:** The request already emitted status 200 before failing, so status metrics cannot retroactively flip to 500. Instrument application-level stream outcomes separately.

**17.** If a browser loses the response after a DB commit on POST, is retrying safe?

**Answer:** Not necessarily. Use idempotency keys and operation-status checks to avoid duplicate side effects.

**18.** Why shouldn't `server.error.include-stacktrace=always` be enabled in production?

**Answer:** Stack traces can expose class names, file paths, internal data, or secrets. Log to access-controlled server logs and return safe error bodies.

**19.** When upgrading Boot 2 to Boot 3, which servlet imports must be updated?

**Answer:** Migrate `javax.servlet.*` to `jakarta.servlet.*` and align servlet API dependencies/runtimes.

**20.** What is the first step upon seeing "cannot sendError after committed"?

**Answer:** Find the **original root exception** and where the response was flushed/committed—inspecting serializers/templates/streams rather than bumping timeouts or calling `sendError` again.

### Hands-On Exercises

1. Call `/api/serialize-error` and locate the stack trace pointing directly to getter `getSecond`.
2. Call `/api/serialize-prechecked` and compare its clean 500 status/JSON body against the direct endpoint.
3. Call `/api/committed-error` and compare the server log `DEMO_AFTER_COMMIT=true` with the HTTP client's status and body.
4. Call `/api/stream-error` via `curl -v -N`, recording received bytes and transfer errors; do not assume a fixed status.
5. Create `templates/missing.html` and re-test `/page/missing` to observe template resolution.
6. Fix `broken.html`: pass a valid `user` and nested profile via the model, or use safe fallbacks.
7. Add a DTO with bidirectional references, write an `ObjectMapper` unit test catching the cycle, and fix it with an API projection.
8. Add a DTO with `LocalDateTime`, compare Boot's injected mapper against a bare mapper missing `JavaTimeModule` in a controlled test.
9. Test HTTP compression / proxy buffering to see what status/body/connection state the client observes when an error happens post-commit.
10. Design NDJSON with `type=item`, `type=error`, and `type=complete`; test the client catching a missing `complete` marker.
11. Add separate Micrometer counters for serialization failures and post-commit failures (bounded tags, no raw URLs).
12. Build the executable JAR and inspect `BOOT-INF/classes/templates/` to catch missing templates before container deployment.
13. Run `dependencyInsight` if a Jackson/module version is overridden, and restore BOM-managed versions.
14. Simulate a client disconnect mid-stream; distinguish broken pipe due to client abort from internal business failures.

## 25. Official Reference Sources

- [Spring Framework 6.2 — Spring MVC `@ResponseBody` and `HttpMessageConverter`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — Exception Resolvers, Servlet Error Dispatch](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/exceptionhandlers.html)
- [Spring Framework 6.2 — Asynchronous Requests, `StreamingResponseBody`/`SseEmitter`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html)
- [Spring Framework 6.2 — Web MVC Error Responses, `ProblemDetail`](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux Reactive Core and Codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — `ServerHttpResponse` API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html)
- [Spring Boot 3.5 — Servlet Web Applications, Error Handling and Template Engines](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Common Application Properties: `server.error`, `spring.thymeleaf`](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Thymeleaf 3.1 — Using Thymeleaf](https://www.thymeleaf.org/doc/tutorials/3.1/usingthymeleaf.html)
- [Jackson — `ObjectMapper`, `JsonMappingException`](https://github.com/FasterXML/jackson-databind)
- [Jakarta Servlet — `ServletResponse.isCommitted` / `flushBuffer`](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/servletresponse)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)

**Conclusion:** An **HTTP 500** can happen **after the controller**, while Jackson serializes the body or Thymeleaf renders a template. The critical boundary is **uncommitted vs. committed response**. Before commit, error handlers can return 500/`ProblemDetail`; **after commit, status and headers cannot be rewritten**, so clients may observe **200 with a truncated body** or a connection error. The proper fix is **resolving the DTO/template/serialization root cause, avoiding premature flushes, designing streaming protocols with completion signals, testing with real HTTP clients, and tracking post-commit failures separately from 5xx**.
