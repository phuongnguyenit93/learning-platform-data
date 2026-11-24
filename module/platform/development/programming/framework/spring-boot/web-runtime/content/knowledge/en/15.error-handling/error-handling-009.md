# Configuring server.error.* and Limiting Exposure of Message, Exception, and Stack Trace

A Spring Boot application may return HTTP 500 when a controller throws an exception, HTTP 404 when a resource is missing, or HTTP 400 when input data is invalid. Error responses must provide **enough information for clients to handle**, without exposing exception class names, SQL statements, passwords, tokens, server file paths, or Java stack traces. In Spring Boot, the `server.error.*` property group controls several attributes included in the **default error response**. Understanding their exact scope prevents accidentally enabling debug output in production and leaking operational details.

This lesson focuses on **Spring Boot 3.3.x, Spring MVC/Servlet web applications, and Java 17+**. We will analyze the `/error` mechanism, distinguish `message`, `exception`, `trace`, and `errors`, examine `never` / `always` / `on_param` values, present a safe production configuration, walk through a runnable example, and test over real HTTP. These options are **one layer of defense for the default error response**; they cannot automatically sanitize every error body constructed by your application or third-party libraries.

## 1. Why Shouldn't You Return Exception Details to Clients?

A service may encounter an error such as:

~~~text
org.springframework.dao.DataIntegrityViolationException
Duplicate key value violates unique constraint "uk_customer_email"
SQL: INSERT INTO customer(email, password_hash) ...
at com.example.billing.CustomerRepository.save(CustomerRepository.java:87)
~~~

These details are useful when engineers investigate inside controlled logs, yet if returned directly to API callers, they can expose:
- Framework, driver, database type, and table/constraint names.
- Package/class names, file paths, and source line numbers.
- Data accidentally embedded in exception messages: emails, tokens, customer details, or SQL queries.
- Internal system flow, helping attackers infer implementation structure.

The rule to follow: **responses provide a safe contract; logs/traces serve internal diagnostics**. A typical server error can return status 500 with a stable error code and correlation ID, while logs record full exception details in an environment accessible only to authorized personnel.

Do not return `200 OK` for exceptions just to “hide errors”: the HTTP status must still reflect the outcome, while the body restricts exposed data.

## 2. How Does Spring Boot Route Failed Requests to /error?

In Servlet/Spring MVC, Spring Boot configures default error handling using components such as `ErrorMvcAutoConfiguration`, `BasicErrorController`, and `ErrorAttributes`.

Simplified diagram:

~~~text
Client -> Servlet container -> Filter chain -> DispatcherServlet
                                          |
                                          +-- request succeeds -> HTTP 2xx
                                          |
                                          +-- error fully handled by MVC
                                          |      -> @ExceptionHandler / advice / resolver
                                          |      -> custom response
                                          |
                                          +-- unhandled error or container error
                                                 -> error dispatch
                                                 -> /error
                                                 -> BasicErrorController
                                                 -> ErrorAttributes
                                                 -> JSON or HTML
~~~

Roles:
- **`DispatcherServlet`** is the Spring MVC front controller; handlers may succeed or throw an exception.
- **`HandlerExceptionResolver` / `@ExceptionHandler` / `@ControllerAdvice`** can handle exceptions directly inside MVC. Once a custom response is created, that flow **does not necessarily** pass through `/error`.
- **The Servlet container** can dispatch errors to the application's default error page.
- **`BasicErrorController`** serves the `/error` endpoint when the corresponding auto-configuration is active.
- **`ErrorAttributes`** gathers attributes used in the error response. The final set of attributes depends on inclusion settings and the actual error.

`server.error.path` defaults to `/error`. That is the application's internal error-handling route, **not** a URL clients are expected to call directly. For instance, if a client calls `GET /api/orders/999` and hits a 404, the response is still for that original request even though the server may dispatch to `/error`.

**Important limitation:** some errors are answered directly by Spring MVC, Spring Security, a reverse proxy, or a custom error handler. `server.error.*` is not a post-processing filter that automatically strips sensitive fields from every response across the system.

## 3. What Does the Default Error Response Usually Contain?

A JSON response from Spring Boot 3.3's default error handling may have a structure like:

~~~json
{
  "timestamp": "2026-11-07T02:30:00.000+00:00",
  "status": 500,
  "error": "Internal Server Error",
  "path": "/api/demo/fail"
}
~~~

This is a **structural illustration**, not fixed output: timestamp, timezone formatting, path, field ordering, and present attributes depend on version, configuration, and error type.

Commonly confused fields:

| JSON Field | Contents | Potential Risk |
|---|---|---|
| `status` | Numeric HTTP status, e.g., 404/500 | Essential for clients |
| `error` | Short label matching status, e.g., Internal Server Error | Usually low sensitivity |
| `timestamp` | Time of error | Helpful for operations |
| `path` | Request path associated with the error | Can expose IDs, internal URLs, or path data |
| `message` | Error message or related info | May contain internal details |
| `exception` | Exception class name | Reveals framework/package/exception type |
| `trace` | Text stack trace | Reveals code structure and call stack |
| `errors` | Binding/validation error details | May contain field names, rejected values, and metadata |

**The JSON field name `trace` differs from the property `include-stacktrace`.** The property controls whether stack trace data is included in the default response; the typical JSON field is named `trace`.

Never assume that lacking `message` makes every response safe. A custom `@RestControllerAdvice` can still return `ex.getMessage()` under `detail`, `reason`, or any other field name.

## 4. The server.error.* Properties in Spring Boot 3.3

According to Spring Boot 3.3's Common Application Properties:

| Property | Default Value | Purpose |
|---|---|---|
| `server.error.include-message` | `never` | When to include the `message` attribute |
| `server.error.include-exception` | `false` | Whether to include the exception class name |
| `server.error.include-stacktrace` | `never` | When to include the `trace` attribute |
| `server.error.include-binding-errors` | `never` | When to include the `errors` attribute |
| `server.error.include-path` | `always` | When to include the `path` attribute |
| `server.error.path` | `/error` | Error controller mapping |
| `server.error.whitelabel.enabled` | `true` | Whether to enable the default fallback HTML error page |

Note the three distinct functional groups:

1. **Controlling attributes in the response:** `include-message`, `include-exception`, `include-stacktrace`, `include-binding-errors`, `include-path`.
2. **Error-handling path:** `path`.
3. **Fallback HTML page:** `whitelabel.enabled`.

Do not use `server.error.path` to control error verbosity; it changes where errors are routed, not which fields are filtered.

Defaults can change between Spring Boot releases. This table targets **3.3.x**; always check the official properties for your running version instead of copying property names from Spring Boot 4.x.

## 5. What Do never, always, and on_param Mean?

The *include attribute* properties—such as `include-message`, `include-binding-errors`, `include-stacktrace`, and `include-path`—support:

| Value | Interpretation |
|---|---|
| `never` | Never include the attribute in the default error response |
| `always` | Include the attribute whenever the data is available |
| `on_param` | Include only when a corresponding query parameter is present per error controller rules |

Example for an isolated debugging environment:

~~~properties
server.error.include-message=on_param
server.error.include-stacktrace=on_param
server.error.include-binding-errors=on_param
~~~

In `BasicErrorController`, the matching query parameters are typically `message`, `trace`, and `errors`. For example, requesting `?trace=true` can append the stack trace when the corresponding setting is `on_param`.

**This is neither authentication nor authorization.** Any caller can append query parameters themselves; therefore `on_param` is **unsafe to enable on public APIs** under the assumption that “only people debugging will know”. It fits only local environments or strictly isolated debug setups, and even then consider whether sensitive data belongs in responses.

`server.error.include-exception` is a boolean `true/false`, **not** `never` or `on_param` like the properties above. Likewise, `server.error.whitelabel.enabled` is a boolean controlling the HTML fallback, not the JSON `trace` field.

## 6. include-message: Why message Is Not Always Safe

`server.error.include-message` controls when the `message` attribute from default error attributes is added.

~~~properties
server.error.include-message=never
~~~

This is a sensible choice for public APIs, especially for 500 errors. When set to:

~~~properties
server.error.include-message=always
~~~

clients can receive messages raised by exceptions or framework error mechanisms, for example:

~~~json
{
  "status": 500,
  "error": "Internal Server Error",
  "message": "Customer lookup failed in private backend",
  "path": "/api/customers"
}
~~~

This is an **illustrative example of a message that could be returned**, not a guarantee every exception produces these exact fields or wording.

Risks:
- Exception messages produced by databases, HTTP clients, or drivers can contain SQL, internal URLs, table names, keys, or input values.
- A message helpful to developers may make no sense to API consumers.
- Messages can change across framework versions, creating brittle client dependencies.

To help clients understand business errors, define **controlled public error codes** such as `BOOK_NOT_FOUND` or `INVALID_BOOK_TITLE` in custom responses/`ProblemDetail`. Do not enable `include-message=always` hoping for user-friendly text across all exceptions.

## 7. include-exception: Class Name vs. Stack Trace

~~~properties
server.error.include-exception=false
~~~

The `false` default prevents adding the `exception` attribute to default responses. If set to `true`, the response can include the exception class name, such as:

~~~json
{
  "status": 500,
  "error": "Internal Server Error",
  "exception": "java.lang.IllegalStateException"
}
~~~

An exception class name is not a full stack trace. Nevertheless, it can still reveal packages, technologies, and internal business classes. Do not assume “exposing only the exception name without the trace” is safe by default.

Also distinguish **exception type** from **HTTP status**. An `IllegalArgumentException` thrown by application logic does not automatically become HTTP 400; without an explicit handler, it can become 500. Accurate error classification belongs to error-mapping rules, not `include-exception`.

## 8. include-stacktrace: Avoiding Exposing the Call Stack

~~~properties
server.error.include-stacktrace=never
~~~

A stack trace typically contains:
- Package, class, method, and Java file names.
- Source code line numbers.
- Libraries/frameworks in use and call paths.
- Exception cause chains and potentially sensitive message fragments.

Setting `always` puts `trace` into default JSON/HTML error responses. This is one of the settings **to strictly avoid in production**. Setting `on_param` does not add controlled debug access either: any caller can try `?trace=true`.

**Alternative:** keep `include-stacktrace=never` in responses, log the stack trace internally via a logger at an appropriate point, and restrict access to logs. With distributed tracing, return a safe correlation ID/trace ID to clients and look up the trace in the backend instead of sending the stack trace.

Do not log unbounded payloads, headers, or authorization tokens simply because responses hide traces. Limiting responses and sanitizing logs are **two independent layers of control**.

## 9. include-binding-errors: Be Careful with rejectedValue

When Spring MVC binding/Bean Validation fails, error metadata can include field names, constraint types, error codes, or the value submitted by the client. Enabling:

~~~properties
server.error.include-binding-errors=always
~~~

can include an `errors` attribute in the default error response when the error source carries binding details, such as invalid field descriptions.

While useful for debugging, this risks exposing:
- Internal field names and bean paths.
- Rejected values, which may contain emails, tokens, or customer data.
- Validation messages never intended for public disclosure.

For production:

~~~properties
server.error.include-binding-errors=never
~~~

At the same time, disabling `errors` in default `/error` **does not prevent** a `@RestControllerAdvice` from manually building `fieldErrors` and returning sensitive values. To return helpful validation feedback, return a curated list (public field names + stable codes + safe messages) and avoid echoing `rejectedValue` by default.

Syntactically invalid JSON also differs from Bean Validation: `@RequestBody` can fail deserialization before reaching validation. Do not rely on `include-binding-errors` as the sole mechanism for managing input errors.

## 10. include-path: URL May Be Visible by Default

Spring Boot 3.3 defaults to:

~~~properties
server.error.include-path=always
~~~

Consequently, default error JSON normally includes `"path": "/api/orders/42"`. This helps clients and logs, but warrants review if the application places sensitive data inside paths.

You can set:

~~~properties
server.error.include-path=never
~~~

to omit the `path` attribute from default error attributes. However:
- URLs may still appear in access logs, tracing, reverse proxies, and browser history.
- Never design tokens, passwords, or secrets into URLs even if response `path` is disabled.
- You can use a correlation ID to link errors to requests instead of broadcasting full paths.

`include-path` does not alter `server.error.path`. One controls the **`path` attribute in responses**, while the other sets the **error controller's mapping**.

## 11. Safe Production Configuration

An intentional configuration for a public Spring Boot MVC API:

~~~yaml
server:
  error:
    include-message: never
    include-exception: false
    include-stacktrace: never
    include-binding-errors: never
    include-path: never
~~~

These properties control the error attributes of the default mechanism. Setting `include-path=never` here reduces path leakage for apps with strict policies; if clients require `path`, you can keep the default `always` after reviewing your contract and URL contents.

You do not have to set every option if it matches the default; declaring them explicitly makes policy reviews easier. What matters is **testing the actual runtime** and verifying config is not overridden by profiles, environment variables, or deployment settings.

Do not use:

~~~yaml
server:
  error:
    include-message: always
    include-stacktrace: always
    include-binding-errors: always
    include-exception: true
~~~

on public systems. The configuration above is an **unsafe example to avoid**, not instructions for debugging production.

You can create `application-local.yml` for debugging on your local machine when needed. Never use `on_param` as a public customer-support tool: it allows callers to trigger detail disclosure without admin privileges.

## 12. HTML Error Pages and Whitelabel Differ from JSON Responses

Spring Boot can serve a fallback HTML page when a browser sends `Accept: text/html` and the error routes to `/error`. The property:

~~~properties
server.error.whitelabel.enabled=true
~~~

enables the default whitelabel fallback. Setting:

~~~properties
server.error.whitelabel.enabled=false
~~~

disables that fallback page, **which neither disables the `/error` mechanism nor automatically sanitizes every JSON error**. Without a custom error page, the Servlet container or another mechanism may return a different error page; verify actual HTML output.

A solid approach for server-rendered apps is creating friendly custom error pages without exceptions or stack traces, such as `src/main/resources/templates/error.html` when an appropriate template engine is present. The page can display a generic message and support links without attaching infrastructure details.

API consumer payloads should be designed separately; a polished HTML page does not fix a JSON response that leaks data.

## 13. server.error.path and Security Boundaries

By default:

~~~properties
server.error.path=/error
~~~

You can change the error controller mapping when genuinely needed to align with app paths or architecture, provided you verify:
- Servlet container error dispatch is configured properly.
- The security filter chain permits error dispatch instead of causing a 401/403 loop.
- No custom controller/handler conflicts with the mapping.
- No reverse proxy/ingress intercepts and replaces responses with its own error pages beforehand.

Changing `server.error.path` does not turn a 500 into 200 or guarantee every exception is caught. Never “secure” `/error` by moving it to an obscure path: error dispatches can still happen, and responses need a safe data policy.

Spring Security can return 401 or 403 via its own `AuthenticationEntryPoint` / `AccessDeniedHandler`, without necessarily going through `BasicErrorController`. Therefore, test 401/403 bodies alongside 400/404/500 bodies.

## 14. Why Doesn't server.error.* Control Every Error?

Several paths do not necessarily go through `BasicErrorController`:

1. `@ExceptionHandler` on a controller.
2. `@RestControllerAdvice`, `ResponseEntityExceptionHandler`, or a custom error contract.
3. `ResponseStatusException` converted into an HTTP response by another resolver.
4. Problem Details via Spring Framework / `spring.mvc.problemdetails.enabled`.
5. Spring Security authentication/authorization handlers.
6. Reverse proxies, gateways, load balancers, or web application firewalls returning errors before Spring Boot.
7. WebFlux reactive error handlers (different from the Servlet MVC pipeline).

Example of an **unsafe** advice:

~~~java
@ExceptionHandler(Exception.class)
ResponseEntity<Map<String, String>> unsafe(Exception ex) {
    return ResponseEntity.status(500)
        .body(Map.of("detail", ex.getMessage()));
}
~~~

Even with `server.error.include-message=never`, this code still exposes `detail` from the exception message because it builds its own response.

In real applications, map exceptions by business type, return accurate statuses, and use **approved** messages. Avoid catching every exception and automatically returning 500, as that can overwrite legitimate 400/404/409 statuses.

## 15. Designing a Safe API Error Contract

For API applications, clients should receive:
- The right HTTP status.
- A stable error code, such as `BOOK_NOT_FOUND` or `VALIDATION_FAILED`.
- A controlled public description (not raw exception messages).
- A correlation ID if the system has a generation/recording mechanism for it.
- A list of field errors containing **only public field names**, never sensitive values.

Illustrative contract example:

~~~json
{
  "code": "BOOK_NOT_FOUND",
  "message": "The requested book was not found",
  "requestId": "req-7f3a"
}
~~~

This JSON is **application-designed**, not `BasicErrorController`'s default shape and not auto-generated by `server.error.*`. `requestId` here is a placeholder; real systems must generate and attach IDs to logs/traces for lookup.

500 errors should generally return a generic message, whereas expected business errors can offer specific descriptions once verified not to leak data. Internal logs can record sanitized exception causes and context; clients never need to know which Java class threw the error.

## 16. Runnable Spring Boot Example: Observing Default Error Responses

Create a **Spring Boot 3.3.x, Java 17+** project with dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This snippet is only the dependencies block, not a full Gradle build file; add the Spring Boot/Java plugins and wrapper as appropriate.

Create `src/main/java/com/example/demo/SafeErrorApplication.java`:

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeErrorApplication.class, args);
    }
}

record CreateAccountRequest(@NotBlank String displayName) {}

@RestController
@RequestMapping("/api/demo")
class DemoController {

    @GetMapping("/fail")
    public String fail() {
        // Intentionally sensitive string ONLY to test non-leakage in this demo.
        throw new IllegalStateException(
            "PRIVATE_INTERNAL_DETAILS_DO_NOT_RETURN");
    }

    @PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateAccountRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
~~~

Because `fail()` throws an exception not handled by any custom handler in the demo, in a standard embedded Servlet runtime the error enters default error handling. The test below verifies the response **does not contain** internal details.

Create `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  error:
    include-message: never
    include-exception: false
    include-stacktrace: never
    include-binding-errors: never
    include-path: never
~~~

The application contains no custom `@RestControllerAdvice` or `ErrorController` because this demo specifically tests **Boot's default error path**. If an advice catching `Exception` is added, the flow changes and tests must be updated accordingly.

### 16.1. Running and Calling the API

Linux/macOS:

~~~bash
./gradlew bootRun
~~~

PowerShell on Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Call the failing endpoint:

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/demo/fail
~~~

Expected status `500 Internal Server Error`. The body may include common fields like `timestamp`, `status`, and `error`, while omitting `message`, `exception`, `trace`, `errors`, or `path` under this configuration.

Try with query parameters attempting to request debug info:

~~~bash
curl -i -H "Accept: application/json" \
  "http://localhost:8080/api/demo/fail?trace=true&message=true&errors=true"
~~~

With `never` values, this request **must not be able to activate** sensitive attributes in the default error response.

Try body validation:

~~~bash
curl -i -X POST http://localhost:8080/api/demo/accounts \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"displayName":""}'
~~~

Expected 400 due to `@NotBlank`. With `include-binding-errors=never`, the default response should not include an `errors` list echoing rejected input values.

**Note:** exact error responses depend on version, content negotiation, and error mapping. Never take an illustrative JSON body and write a client rigidly parsing every field. The goal of this demo is verifying statuses and the **absence of sensitive fields**.

## 17. Real HTTP Integration Test to Confirm No Leaks

For `/error` handling, **MockMvc does not always fully simulate Servlet container error dispatch** like a request over a real HTTP port. An unresolved exception in MockMvc can bubble out of the test rather than being forwarded to `BasicErrorController`. Therefore, the example below uses `@SpringBootTest(webEnvironment = RANDOM_PORT)` with `TestRestTemplate` to test the error boundary on a real embedded server.

Create `src/test/java/com/example/demo/SafeErrorApplicationTest.java`:

~~~java
package com.example.demo;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.error.include-message=never",
        "server.error.include-exception=false",
        "server.error.include-stacktrace=never",
        "server.error.include-binding-errors=never",
        "server.error.include-path=never"
    })
class SafeErrorApplicationTest {

    @Autowired
    TestRestTemplate client;

    @Autowired
    ObjectMapper mapper;

    private static HttpHeaders jsonHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        return headers;
    }

    private void assertNoSensitiveFields(JsonNode body) {
        assertFalse(body.has("message"));
        assertFalse(body.has("exception"));
        assertFalse(body.has("trace"));
        assertFalse(body.has("errors"));
        assertFalse(body.has("path"));
    }

    @Test
    void unexpectedExceptionReturns500WithoutInternals()
            throws Exception {
        ResponseEntity<String> response = client.exchange(
            "/api/demo/fail?trace=true&message=true&errors=true",
            HttpMethod.GET,
            new HttpEntity<Void>(jsonHeaders()),
            String.class);

        assertEquals(500, response.getStatusCode().value());
        assertNotNull(response.getBody());
        JsonNode body = mapper.readTree(response.getBody());

        assertEquals(500, body.path("status").asInt());
        assertNoSensitiveFields(body);
        assertFalse(response.getBody().contains(
            "PRIVATE_INTERNAL_DETAILS_DO_NOT_RETURN"));
    }

    @Test
    void invalidBodyReturns400WithoutRejectedValues()
            throws Exception {
        HttpHeaders headers = jsonHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        ResponseEntity<String> response = client.exchange(
            "/api/demo/accounts",
            HttpMethod.POST,
            new HttpEntity<String>(
                "{\"displayName\":\"\"}", headers),
            String.class);

        assertEquals(400, response.getStatusCode().value());
        assertNotNull(response.getBody());
        JsonNode body = mapper.readTree(response.getBody());
        assertNoSensitiveFields(body);
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

This test provides much stronger verification than merely trusting config files:
1. It runs on a **real embedded server** with a random port.
2. JSON requests go through full HTTP/Servlet processing.
3. Asserts statuses 500 and 400.
4. Asserts `message`, `exception`, `trace`, `errors`, and `path` are absent.
5. Asserts the intentionally sensitive string never appears in the response.
6. Includes `?trace=true&message=true&errors=true` to verify the `never` policy cannot be bypassed by callers.

These tests do not prove logs are safe or that all custom error handlers are locked down. Add separate tests for Spring Security 401/403, business exception handlers, gateways/proxies, and Problem Details if your app uses them.

## 18. Problem Details and @RestControllerAdvice

Spring Framework 6 supports RFC 9457 Problem Details with media type `application/problem+json`. In Spring Boot 3.3 MVC, you can enable:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

Depending on the exception and framework handling, bodies can contain `type`, `title`, `status`, `detail`, and `instance`. Those fields are **distinct** from the `message`/`trace` fields of default error attributes. `server.error.include-message=never` does not guarantee every `ProblemDetail.detail` is suppressed.

When designing custom advice, you can use `ProblemDetail` while controlling public text yourself:

~~~java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(BookNotFoundException.class)
    ProblemDetail notFound(BookNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested book was not found");
        problem.setTitle("Book not found");
        return problem;
    }
}
~~~

This is an **illustrative snippet**, requiring imports and a `BookNotFoundException` definition. It is omitted from the runnable example in Section 16 because it would change the error flow.

Avoid:

~~~java
ProblemDetail.forStatusAndDetail(
    HttpStatus.INTERNAL_SERVER_ERROR, ex.getMessage());
~~~

for internal exceptions. Returning `ex.getMessage()` for 500 opens a new leak channel even when every `server.error.include-*` setting is restrictive.

## 19. WebFlux, Proxies, and Cases Outside MVC Scope

Spring WebFlux has its own reactive error-handling pipeline with `ErrorWebExceptionHandler`/`ErrorAttributes` and response behavior distinct from Servlet MVC's `BasicErrorController`. Some `server.error.*` settings still govern error attributes in Boot, but never assume identical MVC behavior, error dispatch, or JSON shape. For Problem Details in WebFlux, the appropriate property is:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

When behind a proxy/ingress/load balancer:
- HTTP 502/504 can be generated by the proxy before reaching Spring Boot.
- The proxy may replace application error bodies or serve a different HTML page.
- CORS/security layers may emit 401/403 independently.
- Changing `server.error.include-stacktrace` has no effect on bodies generated by gateways.

Test along the **real public path** across all hops, not only against `localhost:8080`.

## 20. Safe Logging and Investigation Support

Hiding stack traces from clients does not mean omitting essential diagnostics on the backend. A balanced strategy:
- Error responses carry status, public error code, and request/correlation ID.
- Internal logs carry timestamp, trace ID, and relevant exceptions.
- Never log raw request bodies, passwords, tokens, API keys, or identifying data without strict justification.
- Define retention, masking, access controls, and auditing for logging systems.
- Maintain dashboards for HTTP 4xx/5xx rates, latency, and system routes.
- Provide support workflows anchored on request IDs rather than exception contents.

Spring Boot Actuator/Micrometer/OpenTelemetry can provide observability when matching dependencies and configs are present. Do not assume those components are automatically enabled in full in every app.

Distinguish log levels from error responses: `logging.level.root=DEBUG` does not automatically insert stack traces into HTTP bodies, and `server.error.include-stacktrace=always` does not guarantee backend logs are properly recorded or monitored.

## 21. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `include-message=always` in production | May expose internal messages | Use `never`, define custom public error codes |
| `include-exception=true` | Leaks exception class/package names | Keep `false` |
| `include-stacktrace=on_param` on public APIs | Callers can request `?trace=true` | Use `never` |
| `include-binding-errors=always` | May expose fields and `rejectedValue` | Use `never` and map safe field errors |
| Confusing `include-path` with `path` | Alters the wrong error endpoint behavior | Distinguish body field from endpoint mapping |
| Only disabling whitelabel | JSON errors can still leak data | Test JSON and HTML separately |
| Assuming `server.error.*` protects custom advice | Custom responses still leak `ex.getMessage()` | Review `@RestControllerAdvice`/`ProblemDetail` |
| Switching profiles without testing deployed config | Production retains debug overrides | Run integration tests and verify environment settings |
| Relying on MockMvc for all error-dispatch tests | Differs from real servlet container behavior | Test with `RANDOM_PORT` and an HTTP client |
| Returning HTTP 200 for all exceptions | Clients/monitoring misinterpret failures | Map proper 400/404/409/500 statuses |
| Logging raw credentials to debug | Leaks through logs despite safe responses | Masking, filtering, least privilege |

## 22. Pre-Release Checklist

- [ ] Confirmed Spring Boot version and Servlet vs. Reactive web stack.
- [ ] `server.error.include-message=never` in public environments.
- [ ] `server.error.include-exception=false`.
- [ ] `server.error.include-stacktrace=never`, without public `on_param`.
- [ ] `server.error.include-binding-errors=never`.
- [ ] Explicit decision made on `include-path` based on API contract and URL data.
- [ ] Tested both `Accept: application/json` and `Accept: text/html`.
- [ ] Custom `@ExceptionHandler`/`@RestControllerAdvice` never echoes raw exception messages.
- [ ] Problem Details, security handlers, and proxy responses tested separately.
- [ ] Error statuses 4xx/5xx are accurate, never wrapping all errors as 200.
- [ ] Errors can be traced via request IDs and protected logs.
- [ ] Public responses contain no passwords, tokens, SQL, stack traces, or internal hostnames.
- [ ] Real embedded-server HTTP tests (beyond MockMvc) exist for 400/404/500.

## 23. Official Documentation

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.error.include-*`, `server.error.path`, and `whitelabel.enabled` with defaults.
- [Spring Boot 3.3 — Servlet Web Applications / Error Handling](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): `/error` mechanism, error controller, HTML/JSON responses, and Problem Details.
- [Spring Boot 3.3 — BasicErrorController API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/error/BasicErrorController.html): error attributes and methods controlling display of message, path, errors, and trace.
- [Spring Framework — MVC Exceptions](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ExceptionHandler` and MVC exception handling.
- [Spring Framework — Error Responses / Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): RFC 9457 `ProblemDetail` and `ErrorResponse`.

**Remember:** `server.error.*` **limits sensitive data inside default error responses**, especially `message`, `exception`, `trace`, and `errors`. Keep sensitive attributes disabled for clients in production, avoid public `on_param`, and test both custom error handlers and real HTTP error dispatches. The goal is **clients understand errors accurately without seeing system internals**.