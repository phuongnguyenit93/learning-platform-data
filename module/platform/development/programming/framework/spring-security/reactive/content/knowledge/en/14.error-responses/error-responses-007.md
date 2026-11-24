# Designing Consistent JSON Error Responses and Correlation IDs

**Module:** Spring Security – reactive (Spring WebFlux)  
**Section:** Error Responses  
**Goal:** Design a common JSON error contract for `401`/`403` from Spring Security and `400`/`404`/`500` from WebFlux; attach a **unique correlation ID per HTTP request**; preserve important HTTP headers; prevent leaking passwords, stack traces, or sensitive data; and verify behavior with Java 17+, Spring Boot, `curl`, and `WebTestClient`.

In an authenticated API, the same operation can fail at multiple layers. A request missing credentials is blocked by Spring Security **before the controller**; a logged-in user lacking a role usually receives `403`; invalid parameters, missing resources, or internal errors may originate from WebFlux/handlers. If each layer returns a different format — sometimes HTML, sometimes an empty body, sometimes JSON with internal messages — clients struggle to handle errors reliably and operations cannot easily correlate failed requests with logs.

Proper design solves **two independent yet coordinated problems**:

1. **Consistent JSON error contract:** each error response has an accurate HTTP status, a stable structured body, a machine-readable error code, a safe public message, the request path, and an optional timestamp.
2. **Correlation ID:** a server-managed identifier per request, present in both the response header and JSON body, and recorded in log/trace metadata. When a client reports `correlationId=...`, operators can locate that request without needing the user's password/token.

**Key takeaway:** A correlation ID is **not an authentication token**—it grants no permissions and proves no identity; and statuses `401` and `403` **cannot be used interchangeably** just to make the JSON look uniform.

## 1. Data Contract: Consistent Yet Still HTTP-Compliant

Use the **RFC 9457** Problem Details format with media type `application/problem+json`. The five standard fields are `type`, `title`, `status`, `detail`, and `instance`; applications may add extension fields such as `code`, `correlationId`, and `timestamp`.

Example of an authenticated user without permission to view admin:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store
X-Correlation-Id: 8d9cc0a5-4e2f-49ba-9b01-4e120a13516a

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "You do not have permission to access this resource.",
  "instance": "/api/admin",
  "code": "ACCESS_DENIED",
  "correlationId": "8d9cc0a5-4e2f-49ba-9b01-4e120a13516a",
  "timestamp": "2026-11-07T06:00:00Z"
}
```

This is an **illustrative protocol sample**: IDs/timestamps differ on every run. The `status` field in JSON must reflect the real HTTP status code. `type="about:blank"` is acceptable when no dedicated problem documentation URI is defined; when using a custom type such as `https://api.example.test/problems/access-denied`, manage its docs and versioning accordingly. `instance` can be the request path and should not contain raw query tokens.

**Field naming principles:**

| Field | Purpose | What to avoid |
| --- | --- | --- |
| `type` | Problem type per RFC 9457 | Changing URI/type dynamically per exception text |
| `title` | Stable, short title matching status | Dumping raw stack traces into title |
| `status` | HTTP status in body for clients/observability | Putting 200 inside body on an HTTP 500 |
| `detail` | Safe client description, localizable | Passwords, SQL, internal class names, server paths |
| `instance` | Request URI reference, usually path only | Full URL containing query tokens or sensitive data |
| `code` | Stable business/app code, e.g., `AUTHENTICATION_REQUIRED` | Using mutable English prose as the code |
| `correlationId` | Correlating errors with requests/logs | Using as credential or user identifier |
| `timestamp` | Error response creation time, ISO-8601 UTC | Treating timestamp as proof of global order in distributed systems |

Not every error needs a custom `detail`. For `401`/`403`, use a sufficiently generic message so it does not disclose whether a username exists, secret role names, or whether someone else's resource exists.

### 1.1. Different Statuses Have Different Meanings

| HTTP status | Situation | Suggested `code` | Notes |
| --- | --- | --- | --- |
| `400 Bad Request` | Invalid parameter syntax/value | `INVALID_REQUEST` | Do not return full sensitive input |
| `401 Unauthorized` | Missing/invalid authentication | `AUTHENTICATION_REQUIRED` | With HTTP Basic, must preserve `WWW-Authenticate` challenge |
| `403 Forbidden` | Authenticated but not permitted | `ACCESS_DENIED` | Do not self-grant roles/alter policy just to pass tests |
| `404 Not Found` | Route/resource missing or intentionally hidden per policy | `NOT_FOUND` | Do not leak others' data in detail |
| `405 Method Not Allowed` | URL exists but HTTP method unsupported | `METHOD_NOT_ALLOWED` | Preserve `Allow` header if provided by framework |
| `409 Conflict` | State/version conflict | `CONFLICT` | Helps clients decide conditional retries |
| `422 Unprocessable Content` | Syntactically valid content violating domain rules when app uses this status | `VALIDATION_FAILED` | Needs a policy consistent with 400 |
| `429 Too Many Requests` | Rate limit | `RATE_LIMITED` | May need `Retry-After`/RateLimit headers |
| `500 Internal Server Error` | Unexpected server error | `INTERNAL_ERROR` | Return generic message, log root cause safely separately |
| `503 Service Unavailable` | Critical dependency down / maintenance | `SERVICE_UNAVAILABLE` | `Retry-After` if meaningful |

**Do not force all errors into HTTP 200 + JSON `{"status": 401}`.** Proxies, browsers, client SDKs, and monitoring read the actual HTTP status. Nor should every error become 500; invalid requests, insufficient permissions, missing resources, and infrastructure failures have distinct semantics.

## 2. Two Different Error Paths in Spring WebFlux

An API can receive errors at the **security layer** or the **application layer**:

```text
HTTP request
      |
      v
CorrelationWebFilter (attaches ID and response header at start of request)
      |
      v
Spring Security WebFilters
      |
      +-- missing/wrong credentials
      |      -> ServerAuthenticationEntryPoint
      |         HTTP 401 + WWW-Authenticate + JSON
      |
      +-- authenticated, missing role
      |      -> ServerAccessDeniedHandler
      |         HTTP 403 + JSON
      |
      +-- passes security
             |
             v
         Spring WebFlux Handler/Controller
             |
             +-- invalid input, missing resource
             |      -> ResponseStatusException / WebFlux error handling
             |         HTTP 400/404 + JSON
             |
             +-- unexpected exception
             |      -> ErrorWebExceptionHandler
             |         HTTP 500 + JSON, no stack trace
             |
             +-- success
                    HTTP 200 + X-Correlation-Id
```

### 2.1. Why Is `@RestControllerAdvice` Alone Not Enough?

`@ExceptionHandler`/`@RestControllerAdvice` helps for errors thrown **during controller processing** (validation/domain exceptions). However, many `401/403` errors originate from `AuthenticationWebFilter` or `ExceptionTranslationWebFilter` **before the controller runs**, so a regular `@RestControllerAdvice` is not guaranteed to catch them.

With WebFlux/Spring Security, configure:

- `ServerAuthenticationEntryPoint` for **authentication-required** errors — including requests without credentials, and the Basic mechanism's entry point when credentials are invalid.
- `ServerAccessDeniedHandler` for cases **authenticated but denied permission**.
- `ErrorWebExceptionHandler` or Spring Boot's Problem Details/`ErrorAttributes` mechanism to standardize **WebFlux errors outside Security**, including unmapped routes or unhandled controller exceptions.
- A **single shared writer** for content type/body/headers so every path produces the same contract; avoid duplicating JSON strings across filters.

You must test the entire **real HTTP** path, not just controller unit tests; configuring one branch while skipping another can cause 401 to sometimes return JSON and other times return empty/HTML.

### 2.2. HTTP Basic Has Two Sources of 401

With HTTP Basic, `httpBasic(...)` creates its own authentication filter and handles **authentication failures** when passwords are wrong. For consistency, configure the same `ServerAuthenticationEntryPoint` in both:

1. `exceptionHandling(ex -> ex.authenticationEntryPoint(...))`: when a request hits an endpoint requiring login without valid authentication.
2. `httpBasic(basic -> basic.authenticationEntryPoint(...))`: when the Basic converter/manager receives credentials and authentication **fails**.

The `ServerHttpSecurity.HttpBasicSpec.authenticationEntryPoint` API supports the second configuration. If you only set the entry point on `exceptionHandling`, some wrong-password errors may go through Basic's failure handler and return a different format. This is very easy to miss.

For HTTP Basic, **you must preserve** the `WWW-Authenticate: Basic realm="..."` header on status 401. JSON is a **supplementary body** and must not strip the protocol's challenge requirement. For bearer tokens/OAuth2 Resource Server, challenges normally use `WWW-Authenticate: Bearer ...` per RFC 6750; do not copy a Basic header onto Bearer.

### 2.3. Why Should Error Responses Have Cache-Control?

`401/403` responses may include resource paths or metadata. Setting `Cache-Control: no-store` per policy helps prevent intermediate caches or browsers from storing sensitive error responses; however, also verify proxy/CDN caching and never rely on it instead of access control. When handling `429`/`503`, `Retry-After` can be provided with real semantics rather than an arbitrary number.

## 3. Correlation ID: Requirements, Contract, and Lifecycle

A **Correlation ID** is usually a non-secret string (such as UUID v4) linking all logs and responses **of a single HTTP request**. For an incoming API request:

- The server generates or validates/accepts the ID **per trust-boundary policy**.
- Attaches the ID to `ServerWebExchange.getAttributes()` so WebFilters/handlers on the same request can read it easily.
- Can store it in Reactor `Context` so downstream operators/WebClient can access it on subscribe.
- Returns it to the client via the `X-Correlation-Id` header and `correlationId` field in error JSON; successful responses may only need the header.
- Logs the same ID in access/structured logs alongside sanitized status, route template, or operation name.
- When calling downstream services, consider propagating the ID via an internal header per contract, or leveraging the observability stack's trace context.

### 3.1. Do Not Blindly Trust `X-Correlation-Id` from the Internet

A client could send:

```http
X-Correlation-Id: alice-admin-superuser
```

This is **not** proof the caller is Alice or an admin. If the server reflects the raw value into logs/headers, attackers can supply oversized IDs, collide with other users' IDs, inject control characters, or cause log injection (HTTP libraries usually block CRLF, though you should not rely on that alone). The demo policy **always issues a fresh UUID on the server** and ignores client-supplied values.

In systems with a trusted API Gateway/tracing layer, you may **accept incoming correlation IDs** if the gateway validates/bounds length, format, character set, uniqueness policy, and strips untrusted headers. Clearly separate the current hop's `requestId`, the business flow's `correlationId`, and distributed tracing's `traceId`.

### 3.2. Distinguishing Correlation ID, Trace ID, Span ID, and Principal

| Identifier | Purpose | Where it should come from | What NOT to use it as |
| --- | --- | --- | --- |
| `correlationId` | Correlate request/flow with errors/incidents | Trusted server/gateway, explicit format policy | Authentication or authorization token |
| `traceId` | Link multiple spans across services | OpenTelemetry/W3C Trace Context instrumentation | Sensitive data or user identity proof |
| `spanId` | Identify one unit of work in a trace | Tracing SDK/instrumentation | Stable field across multiple requests |
| `userId` / `sub` | Authenticated subject | Verified Spring Security `Authentication`/token | Replacing correlation ID for client support |
| `sessionId` | Cookie/server session | Session infrastructure | Public value in error JSON/logs |
| `access token` / `password` | Credentials | Protected auth source | Log content, response detail, or correlation ID |

**W3C `traceparent` is not the same as `X-Correlation-Id`.** If your organization already uses Micrometer Tracing/OpenTelemetry, include `traceId` in logs and error responses per policy instead of inventing a second system. Do not overwrite instrumentation-managed trace contexts; validate client `traceparent` per trust policy.

### 3.3. Reactor Context Differs from ThreadLocal MDC

WebFlux can interleave multiple requests on the same event-loop thread; manually managed `ThreadLocal`/MDC does not guarantee each callback carries the right ID. If you need to log from async operators, use Reactor Context/Micrometer Context Propagation with official integration, or pass the ID explicitly as a local variable/parameter. Never do:

```java
static String currentCorrelationId; // WRONG: shared across all requests
```

Nor should you call `MDC.put("cid", id)` on entry and hope every `flatMap`/`publishOn` runs on the same thread. If using context propagation, ensure proper accessors/cleanup and test concurrent requests. The demo below logs the captured ID variable directly without depending on MDC.

## 4. Proposed Architecture of the Sample Application

We will build a Spring Boot WebFlux project containing:

- `CorrelationWebFilter`: creates a UUID per request, stores attribute + Reactor Context, attaches header to both success/error responses, logs status with ID.
- `ApiProblem`: Java record holding the 5 standard RFC 9457 fields plus extensions `code`, `correlationId`, `timestamp`.
- `ApiProblemWriter`: **a single place** serializing JSON with Jackson, setting HTTP status, content type, no-store, and required headers.
- `SecurityConfig`: uses the entry point for **both** `httpBasic` and `exceptionHandling`, plus access-denied handler.
- `ApiErrorWebExceptionHandler`: catches unhandled WebFlux errors at `@Order(-2)`, encoding `400/404/500` using the shared contract. Does not attempt a second JSON write if the response is already committed.
- `ApiController`: a few endpoints to trigger every scenario.
- `ApiErrorTests`: `WebTestClient` against a real server, asserting **HTTP status + media type + headers + JSON fields + no internal error leaks + distinct IDs per request**.

### Demo Endpoint Matrix

| Endpoint | Authentication | Behavior |
| --- | --- | --- |
| `GET /public/ping` | Public | `200 pong` + `X-Correlation-Id` |
| `GET /api/me` | Required | `200 hello:alice` if Alice uses valid password |
| `GET /api/admin` | `ROLE_ADMIN` | Alice with valid password still gets `403` |
| `GET /api/parse?n=-1` | Required | Emits `ResponseStatusException(BAD_REQUEST)`, becomes `400` JSON |
| `GET /api/fail` | Required | Deliberate simulated error, becomes safe `500` JSON |
| `GET /api/not-here` | Required | No mapping, becomes `404` JSON if authenticated |
| `GET /api/me` no Basic/wrong Basic | Rejected | `401` JSON + Basic challenge |

Accounts for **localhost only**: `alice / alice123` (role USER) and `admin / admin123` (role ADMIN). Passwords are hashed with `PasswordEncoder`, never `{noop}`.

## 5. Complete Java 17+ Spring Boot WebFlux Application

Uses **JDK 17+**, Maven, and **Spring Boot 3.5.7** as the example baseline; in production, choose a supported version and patches per security policy. Do not add the Spring MVC starter to a WebFlux project.

### 5.1. Structure

```text
reactive-json-errors/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/errors/
    │   │   ├── ErrorApiApplication.java
    │   │   ├── CorrelationWebFilter.java
    │   │   ├── ApiProblem.java
    │   │   ├── ApiProblemWriter.java
    │   │   ├── SecurityConfig.java
    │   │   ├── ApiController.java
    │   │   └── ApiErrorWebExceptionHandler.java
    │   └── resources/application.properties
    └── test/java/demo/errors/
        └── ApiErrorTests.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-json-errors</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

The Spring Boot WebFlux starter provides Jackson and JSON integration used in the example. With Java 17, `record` is supported directly. In a real dependency graph, verify the Jackson/Boot BOM so no manually overridden versions conflict.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-json-errors
server.port=8080
```

### 5.2. Application Class

`src/main/java/demo/errors/ErrorApiApplication.java`:

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorApiApplication.class, args);
    }
}
```

### 5.3. CorrelationWebFilter: Issuing an ID per Request

`src/main/java/demo/errors/CorrelationWebFilter.java`:

```java
package demo.errors;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationWebFilter implements WebFilter {
    static final String ATTRIBUTE_KEY = "demo.correlationId";
    static final String CONTEXT_KEY = "demo.correlationId";
    static final String HEADER = "X-Correlation-Id";

    private static final Logger log =
        LoggerFactory.getLogger(CorrelationWebFilter.class);

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        // Demo only trusts server-generated IDs; does not copy client headers.
        String id = UUID.randomUUID().toString();
        exchange.getAttributes().put(ATTRIBUTE_KEY, id);
        exchange.getResponse().getHeaders().set(HEADER, id);

        return chain.filter(exchange)
            .contextWrite(context -> context.put(CONTEXT_KEY, id))
            .doFinally(signal -> log.info(
                "request-finished status={} correlationId={}",
                exchange.getResponse().getStatusCode(), id));
    }

    static String id(ServerWebExchange exchange) {
        return exchange.getAttributeOrDefault(
            ATTRIBUTE_KEY, "unavailable");
    }
}
```

**Observations:**

- `@Order(Ordered.HIGHEST_PRECEDENCE)` places the filter very early in the WebFlux pipeline, before standard Basic/authorization checks, so 401/403 responses also get an ID. If there are external gateways/filters outside the app, they have their own lifecycles and ordering; do not promise every error before WebFlux handlers start has the same ID.
- `exchange.getAttributes()` is **per-request**, not a mutable singleton field. `contextWrite` lets downstream Reactor operators read the ID when subscribed with Context; request A and request B never share an ID.
- The logger records status and correlation ID, **not** passwords, `Authorization` headers, raw queries, bodies, or `SecurityContext`. Full logging data in an observability stack needs its own policy.
- `doFinally` runs when the pipeline terminates, covering complete/error/cancel; status code may be null if the response was not finalized when an error happened very early. This is a technical log, not an unconditional success log.
- `unavailable` is a defensive fallback in demo code if a handler runs outside the filter flow. `ApiProblemWriter` below still generates a fresh UUID if missing so responses never lack correlation.

### 5.4. ApiProblem: Stable JSON Schema

`src/main/java/demo/errors/ApiProblem.java`:

```java
package demo.errors;

public record ApiProblem(
    String type,
    String title,
    int status,
    String detail,
    String instance,
    String code,
    String correlationId,
    String timestamp
) {}
```

The record is purely a data model containing no secrets or `Throwable`. Jackson serializes fields via record accessors; there is no manual string concatenation `"{" + ... + "}"` risking escaping bugs or JSON injection. Because field names are uniform, clients can parse by `code` and display `detail`.

### 5.5. ApiProblemWriter: One Place Standardizing Status, Headers, and JSON

`src/main/java/demo/errors/ApiProblemWriter.java`:

```java
package demo.errors;

import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class ApiProblemWriter {
    private final ObjectMapper mapper;

    public ApiProblemWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public Mono<Void> write(
            ServerWebExchange exchange,
            HttpStatusCode status,
            String code,
            String publicDetail,
            boolean basicChallenge) {

        var response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.error(new IllegalStateException(
                "Cannot render an error after response commit"));
        }

        String id = exchange.getAttribute(
            CorrelationWebFilter.ATTRIBUTE_KEY);
        if (id == null) {
            id = UUID.randomUUID().toString();
            exchange.getAttributes().put(
                CorrelationWebFilter.ATTRIBUTE_KEY, id);
        }

        HttpStatus knownStatus = HttpStatus.resolve(status.value());
        String title = knownStatus == null
            ? "HTTP Error" : knownStatus.getReasonPhrase();

        ApiProblem body = new ApiProblem(
            "about:blank",
            title,
            status.value(),
            publicDetail,
            exchange.getRequest().getPath()
                .pathWithinApplication().value(),
            code,
            id,
            Instant.now().toString()
        );

        byte[] json;
        try {
            json = mapper.writeValueAsBytes(body);
        } catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().setCacheControl(
            CacheControl.noStore());
        response.getHeaders().set(
            CorrelationWebFilter.HEADER, id);

        if (basicChallenge) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"demo\"");
        }

        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(json)));
    }
}
```

**Why doesn't the writer accept a Throwable to turn into JSON?** Only **controlled** messages are exposed publicly. Passing `Throwable.getMessage()` to the client can leak SQL/JDBC errors, server hostnames, usernames, or internal logic. `ApiProblemWriter` accepts only policy-selected `code` and `publicDetail`. In server logs, exception stacks can be logged in an appropriate, access-restricted location—never sent over the network.

**Technical note:** The code places a `response.isCommitted()` guard before writing. Once the HTTP body starts streaming, you **cannot change status 200 to 500 and write a complete JSON body**; handle errors inside the stream or terminate the connection per transport semantics. Long-lived `Flux`/streaming endpoints need dedicated design, such as SSE error events with a different contract; never try to append a Problem JSON at the end of an already committed stream.

### 5.6. SecurityConfig: Both Authentication Entry Point and Access-Denied

`src/main/java/demo/errors/SecurityConfig.java`:

```java
package demo.errors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http, ApiProblemWriter writer) {

        ServerAuthenticationEntryPoint entryPoint =
            (exchange, exception) ->
                writer.write(
                    exchange,
                    HttpStatus.UNAUTHORIZED,
                    "AUTHENTICATION_REQUIRED",
                    "Authentication is required.",
                    true
                );

        ServerAccessDeniedHandler denied =
            (exchange, exception) ->
                writer.write(
                    exchange,
                    HttpStatus.FORBIDDEN,
                    "ACCESS_DENIED",
                    "You do not have permission to access this resource.",
                    false
                );

        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .pathMatchers(HttpMethod.GET, "/api/**")
                    .authenticated()
                .anyExchange().denyAll()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(denied))
            .httpBasic(basic ->
                basic.authenticationEntryPoint(entryPoint))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Four decisions to preserve:**

1. `httpBasic(...authenticationEntryPoint(entryPoint))` also handles authentication failures caused by wrong passwords (Basic filter), while `exceptionHandling(...authenticationEntryPoint(entryPoint))` handles requests without valid authentication reaching protected resources. Same writer → same schema.
2. `ServerAccessDeniedHandler` is used for a user with a valid Authentication who lacks `ROLE_ADMIN`; differs from `401` in both body code and status.
3. `hasRole("ADMIN")` maps to the `ROLE_ADMIN` authority from `User.roles("ADMIN")`; roles come from a trusted source, not an `X-Role` header.
4. `anyExchange().denyAll()` prevents exposing undeclared routes. For `/api/not-here`, once authenticated, the `GET /api/**` matcher lets the request reach WebFlux so 404 is seen. When anonymous, security normally blocks with 401 before routing.

The example keeps default CSRF for state-changing methods; all test endpoints are GET only. When adding POST/PUT/DELETE using cookies/sessions, configure and test CSRF properly rather than disabling CSRF to "fix" 403.

### 5.7. ApiController: Producing Success and Three Types of Application Errors

`src/main/java/demo/errors/ApiController.java`:

```java
package demo.errors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(value = "/api/me",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName())
            .map(name -> "hello:" + name);
    }

    @GetMapping(value = "/api/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }

    @GetMapping(value = "/api/parse",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> parse(@RequestParam("n") int number) {
        if (number < 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Internal validation detail not for client"));
        }
        return Mono.just("n=" + number);
    }

    @GetMapping(value = "/api/fail",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> fail() {
        return Mono.error(new IllegalStateException(
            "simulated-internal-secret-must-not-leak"));
    }
}
```

`/api/fail` is an intentionally simulated error to **verify the response does not leak exception messages**. Never throw errors containing real credentials; the string above is only a test sentinel. In production, unexpected errors require redacted logging/observability rather than catching and printing them raw to the client.

`ResponseStatusException` is suitable for errors with an explicit HTTP status; when the exception's `reason` contains internal details, the writer still sends a generic detail. In larger apps, rather than constructing `ResponseStatusException` in every service, use domain exceptions/`@RestControllerAdvice` mapped to stable codes.

### 5.8. ApiErrorWebExceptionHandler: Standardizing 400, 404, and 500

`src/main/java/demo/errors/ApiErrorWebExceptionHandler.java`:

```java
package demo.errors;

import org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
@Order(-2)
public class ApiErrorWebExceptionHandler
        implements ErrorWebExceptionHandler {

    private final ApiProblemWriter writer;

    public ApiErrorWebExceptionHandler(ApiProblemWriter writer) {
        this.writer = writer;
    }

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange, Throwable error) {

        if (exchange.getResponse().isCommitted()) {
            return Mono.error(error);
        }

        HttpStatusCode status =
            error instanceof ResponseStatusException ex
                ? ex.getStatusCode()
                : HttpStatus.INTERNAL_SERVER_ERROR;

        // Preserve meaningful HTTP headers attached by the framework
        // (e.g., Allow on 405), then writer sets Content-Type.
        if (error instanceof ResponseStatusException ex) {
            exchange.getResponse().getHeaders()
                .putAll(ex.getHeaders());
        }

        String code;
        String safeDetail;
        switch (status.value()) {
            case 400 -> {
                code = "INVALID_REQUEST";
                safeDetail = "The request is invalid.";
            }
            case 404 -> {
                code = "NOT_FOUND";
                safeDetail = "The requested resource was not found.";
            }
            case 405 -> {
                code = "METHOD_NOT_ALLOWED";
                safeDetail = "This HTTP method is not supported.";
            }
            case 409 -> {
                code = "CONFLICT";
                safeDetail = "The request conflicts with current state.";
            }
            case 429 -> {
                code = "RATE_LIMITED";
                safeDetail = "Too many requests.";
            }
            case 503 -> {
                code = "SERVICE_UNAVAILABLE";
                safeDetail = "The service is temporarily unavailable.";
            }
            default -> {
                if (status.is4xxClientError()) {
                    code = "REQUEST_REJECTED";
                    safeDetail = "The request cannot be completed.";
                } else {
                    code = "INTERNAL_ERROR";
                    safeDetail = "An unexpected error occurred.";
                    status = HttpStatus.INTERNAL_SERVER_ERROR;
                }
            }
        }

        return writer.write(
            exchange, status, code, safeDetail, false);
    }
}
```

`ErrorWebExceptionHandler` is an extension point of WebFlux exception handling. `@Order(-2)` puts the custom handler ahead of Spring Boot's default handler; when a custom bean exists, Boot may skip creating the default error handler depending on auto-configuration. This is a **low-level** hook; preserve correct behavior for existing exceptions/statuses and test thoroughly when upgrading framework versions.

**Why preserve headers?** `ResponseStatusException.getHeaders()` may carry `Allow` for 405 or other useful headers; the shared writer only overrides content type/cache/correlation. In a large API, also map `ErrorResponseException`/validation exceptions and versioned headers, supporting redacted structured validation details, CORS headers, and 422/429 per policy.

**Why not attempt writing 500 after the response is committed?** WebFlux may begin streaming SSE/Flux and send 200 before an error occurs. At that point, a new HTTP 500 + Problem JSON body cannot be sent on the same response. The handler returns the error to the outer layer instead of producing corrupted concatenated JSON; design streaming errors separately.

## 6. Running the Application and Observing with curl

From the project directory:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Once Netty is running on 8080, open a second terminal. `curl -i` shows status/headers/body:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/me
curl -i --user alice:wrong http://localhost:8080/api/me
curl -i --user alice:alice123 http://localhost:8080/api/admin
curl -i --user admin:admin123 http://localhost:8080/api/admin
curl -i --user alice:alice123 'http://localhost:8080/api/parse?n=-1'
curl -i --user alice:alice123 http://localhost:8080/api/not-here
curl -i --user alice:alice123 http://localhost:8080/api/fail
```

| Request | Expected | What to verify |
| --- | --- | --- |
| `/public/ping` public | 200, `pong` | Has `X-Correlation-Id` even without an error body |
| `/api/me` anonymous | 401 | `WWW-Authenticate: Basic ...`, JSON code `AUTHENTICATION_REQUIRED` |
| `/api/me` Alice valid | 200, `hello:alice` | Header ID is a server-issued UUID |
| `/api/me` Alice wrong | 401 | Same schema/headers as anonymous; no user/password leak |
| `/api/admin` Alice | 403 | JSON code `ACCESS_DENIED`, no mandatory Basic challenge |
| `/api/admin` admin | 200, `admin-ok` | Role loaded from user store |
| `/api/parse?n=-1` | 400 | JSON code `INVALID_REQUEST`, no internal reason leak |
| `/api/not-here` after auth | 404 | JSON code `NOT_FOUND`, path contains no query secrets |
| `/api/fail` | 500 | JSON code `INTERNAL_ERROR`, does not leak `simulated-internal-secret-must-not-leak` |

For the errors above, content type is `application/problem+json`, JSON status equals HTTP status, and header `X-Correlation-Id` equals field `correlationId`. Timestamps and UUIDs change across requests, so **do not assert against fixed values** in tests.

Older PowerShell may require `curl.exe` instead of the `curl` alias. Use demo passwords only over localhost; Basic sends credentials in Base64 and requires **HTTPS** in real environments. Never put real passwords or Bearer tokens into shell history.

### 6.1. Verifying the Server Does Not Trust Client-Declared Correlation IDs

```bash
curl -i --user alice:alice123 \
  -H 'X-Correlation-Id: attacker-picked-id' \
  http://localhost:8080/api/me
```

The response header must be a server-issued UUID, **different from** `attacker-picked-id`. This avoids reflecting arbitrary strings from the Internet into logs or errors. If your organization wants to keep correlation IDs from a trusted gateway, enforce validation/trust boundaries at ingress and test it separately.

### 6.2. HTTP/JSON Should Not Be Wrongly "Homogenized"

- For HTTP Basic 401, **`WWW-Authenticate` is a protocol element** that cannot be omitted just because the body looks clean.
- For HTTP 403, the client is logged in but missing a role; do not send a credential challenge as if the password were wrong.
- For 404 after authentication, the request reaches an unmapped route; if security blocks early via default deny, you may see 401/403 instead of 404. Design matchers intentionally.
- For 500, public messages are always generic and root causes must be logged server-side with proper access controls.
- For validation errors, a `violations` list containing only field names and safe messages can be added without echoing raw passwords/tokens.

## 7. Automated WebTestClient Testing

To properly test **HTTP filters** rather than calling controllers directly, use `@SpringBootTest(webEnvironment = RANDOM_PORT)`. `WebTestClient` sends requests to a real server without mocking Authentication via test-only headers.

The test suite verifies key JSON fields, not only status codes. `ObjectMapper` parses JSON; avoid asserting the whole raw string since field order, timestamps, and UUIDs are not constants.

`src/test/java/demo/errors/ApiErrorTests.java`:

```java
package demo.errors;

import java.util.UUID;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ApiErrorTests {

    @Autowired
    WebTestClient client;

    @Autowired
    ObjectMapper mapper;

    private JsonNode assertProblem(
            EntityExchangeResult<byte[]> result,
            int status, String code) throws Exception {

        assertEquals(status, result.getStatus().value());
        assertEquals(MediaType.APPLICATION_PROBLEM_JSON,
            result.getResponseHeaders().getContentType());

        String id = result.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        assertNotNull(id, "Missing X-Correlation-Id header");
        assertEquals(UUID.fromString(id).toString(), id);

        String cacheControl = result.getResponseHeaders()
            .getFirst(HttpHeaders.CACHE_CONTROL);
        assertNotNull(cacheControl);
        assertTrue(cacheControl.contains("no-store"));

        JsonNode json = mapper.readTree(result.getResponseBody());
        assertEquals("about:blank", json.path("type").asText());
        assertEquals(status, json.path("status").asInt());
        assertEquals(code, json.path("code").asText());
        assertEquals(id, json.path("correlationId").asText());
        assertFalse(json.path("title").asText().isBlank());
        assertFalse(json.path("detail").asText().isBlank());
        assertFalse(json.path("timestamp").asText().isBlank());
        return json;
    }

    @Test
    void anonymousRequestGets401JsonAndBasicChallenge() throws Exception {
        var result = client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody().returnResult();

        JsonNode json =
            assertProblem(result, 401, "AUTHENTICATION_REQUIRED");
        assertEquals("/api/me", json.path("instance").asText());
        String challenge = result.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE);
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic "));
    }

    @Test
    void wrongPasswordHasSameSafe401Contract() throws Exception {
        var result = client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "incorrect"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody().returnResult();

        JsonNode json =
            assertProblem(result, 401, "AUTHENTICATION_REQUIRED");
        assertTrue(json.toString().contains("AUTHENTICATION_REQUIRED"));
        assertFalse(json.toString().contains("incorrect"));
        assertNotNull(result.getResponseHeaders()
            .getFirst(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void authenticatedReaderGets403Problem() throws Exception {
        var result = client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 403, "ACCESS_DENIED");
        assertEquals("/api/admin", json.path("instance").asText());
    }

    @Test
    void invalidInputGets400Problem() throws Exception {
        var result = client.get().uri("/api/parse?n=-1")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 400, "INVALID_REQUEST");
        assertEquals("/api/parse", json.path("instance").asText());
        assertFalse(json.toString().contains(
            "Internal validation detail not for client"));
    }

    @Test
    void nonexistentApiPathGets404Problem() throws Exception {
        var result = client.get().uri("/api/not-here")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isNotFound()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 404, "NOT_FOUND");
        assertEquals("/api/not-here", json.path("instance").asText());
    }

    @Test
    void unexpectedErrorIs500WithoutInternalException() throws Exception {
        var result = client.get().uri("/api/fail")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().is5xxServerError()
            .expectBody().returnResult();

        JsonNode json = assertProblem(result, 500, "INTERNAL_ERROR");
        assertFalse(json.toString().contains(
            "simulated-internal-secret-must-not-leak"));
        assertFalse(json.toString().contains("IllegalStateException"));
    }

    @Test
    void successfulRequestAlsoHasCorrelationHeader() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().exists(CorrelationWebFilter.HEADER)
            .expectBody(String.class).isEqualTo("hello:alice");
    }

    @Test
    void clientSuppliedCorrelationIdIsNotTrusted() {
        var result = client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("alice", "alice123"))
            .header(CorrelationWebFilter.HEADER, "attacker-picked-id")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello:alice")
            .returnResult();

        String returned = result.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        assertNotNull(returned);
        assertEquals(UUID.fromString(returned).toString(), returned);
        assertNotEquals("attacker-picked-id", returned);
    }

    @Test
    void separateRequestsReceiveDifferentIds() {
        var first = client.get().uri("/public/ping")
            .exchange().expectStatus().isOk()
            .expectBody().returnResult();
        var second = client.get().uri("/public/ping")
            .exchange().expectStatus().isOk()
            .expectBody().returnResult();

        String a = first.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        String b = second.getResponseHeaders()
            .getFirst(CorrelationWebFilter.HEADER);
        assertNotNull(a);
        assertNotNull(b);
        assertNotEquals(a, b);
    }

    @Test
    void adminCanUseAdminEndpoint() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Run:

```bash
mvn test
```

With the test class above alone, **the goal is 10 passing tests** when dependencies, environment, and configuration are accurate. This is tutorial code to run yourself; **do not claim tests were executed on the reader's machine**. When failures occur, check which status/header/JSON path mismatched and the server-side exception; never relax tests to assert only 200/401 and abandon the contract.

### 7.1. Why Are These Tests More Valuable Than Checking HTTP Status Alone?

- Anonymous 401 **and** wrong-password 401: verify both authentication error sources pass through the same schema and still carry the Basic challenge.
- Alice calling admin: valid Authentication, yet `403` from access denied, not returning 401 like a password error.
- Invalid input/non-existent route/unexpected error: tests that the shared writer is invoked from the WebFlux layer, not only Spring Security.
- Error 500 without message or internal class name: verifies the **no server-detail leakage** policy.
- `X-Correlation-Id` header and JSON `correlationId` match; the string parses as a valid UUID.
- Two requests get two distinct IDs; arbitrary client-sent IDs do not alter the server-issued ID.
- 200 success tests also carry an ID — helpful for investigating non-error requests that exhibit slowness or wrong data.

**Limitation:** Local tests do not prove API gateways/nginx/service meshes preserve headers or redact properly. Before deploying, run end-to-end tests from public ingress to backend and distributed tracing.

## 8. When to Use Built-in ProblemDetail Instead of a Manual Writer?

Spring Framework provides `org.springframework.http.ProblemDetail` and RFC 9457 support. Spring Boot WebFlux can enable:

```properties
spring.webflux.problemdetails.enabled=true
```

This is an **alternative option** for application error handling; it does not automatically ensure Spring Security entry points, HTTP Basic failure handlers, and all error mappings add your organization's `code`/`correlationId` extensions. When using `ProblemDetail`/`ErrorResponse`, standardize via `@ControllerAdvice`, `ErrorAttributes`, or corresponding hooks, combined with Security handlers using the same schema.

The sample project above uses a consistent custom writer for both security and general errors to illustrate each layer's responsibility. **Do not stack two independent error pipelines** without knowing their order: it can produce inconsistent responses, double body writes, or changed Content-Types. In production apps, pick **one clear convention**, test all paths, and prefer framework mechanisms when they meet requirements.

### 8.1. @RestControllerAdvice Remains Useful for Domain Exceptions

For instance, if the domain has `ResourceAlreadyExistsException`, controller advice can map it to `409 Conflict` with code `CONFLICT`. Still, pre-controller security errors must go through `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler`. With a custom `@RestControllerAdvice`, you can construct an `ApiProblem` via a shared factory and return `ResponseEntity<ApiProblem>`, while still keeping `Content-Type`, `X-Correlation-Id`, and logging policies aligned.

Do not place `@ExceptionHandler(Exception.class)` in every controller hiding all errors as empty 200s, as that loses accurate statuses and prevents clients from distinguishing retries/permissions/input.

## 9. Propagating IDs Through WebClient and Distributed Systems

`ServerWebExchange.getAttributes()` is convenient **within the current request**. When WebFlux code calls another service via `WebClient`, do not try reading exchange attributes inside a request-less singleton bean. Since `CorrelationWebFilter` placed the ID into the Reactor Context, an `ExchangeFilterFunction` can read the Context on subscription to attach the outbound header in a controlled way.

**Illustrative fragment**, requiring imports `WebClient`, `ClientRequest`, `ExchangeFilterFunction`, `Mono`, and corresponding bean config:

```java
@Bean
WebClient internalWebClient(WebClient.Builder builder) {
    ExchangeFilterFunction propagate = (request, next) ->
        Mono.deferContextual(context -> {
            String id = context.getOrDefault(
                CorrelationWebFilter.CONTEXT_KEY, "");
            ClientRequest.Builder outbound =
                ClientRequest.from(request);
            if (!id.isBlank()) {
                outbound.headers(headers ->
                    headers.set(CorrelationWebFilter.HEADER, id));
            }
            return next.exchange(outbound.build());
        });

    return builder
        .filter(propagate)
        .build();
}
```

This is **not a file to add to the runnable project**: the demo system has no downstream service. In real use, propagate only to trusted services per policy; if using OpenTelemetry, prefer official instrumentation to pass `traceparent`/baggage. A Correlation ID only aids correlation and grants no authorization for outbound calls.

For calls out to Kafka/queues/background tasks, do not rely on the Reactor Context of a finished request. Pass the correlation ID as validated metadata/message headers, preserve appropriate TTL, and never stuff access tokens/PII into it. Receiving systems generate their own span/request IDs if needed and link back to the root trace/correlation per contract. A single user clicking multiple actions can generate multiple request IDs; never reuse one fixed ID for an entire user session.

### 9.1. Logging JSON/Structured Logs

Minimal error logs should link `correlationId`, timestamp, service name, operation/route, status, error code, and trace/span IDs if present. Sample format:

```json
{
  "event": "api_request_failed",
  "service": "report-api",
  "status": 403,
  "code": "ACCESS_DENIED",
  "correlationId": "8d9cc0a5-4e2f-49ba-9b01-4e120a13516a",
  "route": "/api/admin"
}
```

Never log `Authorization`, cookies, Basic credentials, refresh tokens, full request bodies, database connection strings, or raw stack traces into public logs. Server-side stack traces, if needed, belong in access-controlled/retention-managed logs, not error responses. Log **route templates** (e.g., `/reports/{id}`) rather than full paths if paths contain PII; never put email/SSN into `correlationId`.

### 9.2. Exceptions to the One-Request-One-ID Rule

- One request with multiple internal retries: keep the incoming correlation ID and create a distinct span for each downstream call.
- One batch request containing multiple items: one request ID for the HTTP request, plus separate item IDs for individual business errors if needed.
- An asynchronous job outliving the response: preserve the job's correlation/causation ID in durable metadata and create new request/job event IDs when processing.
- A CDN returning 4xx/5xx **before the request reaches the app**: the WebFlux filter does not run; the CDN/gateway must have its own error contract and ID or coordinate.

## 10. Security of Error Responses

### 10.1. Do Not Disclose Authentication Details

For 401, avoid responses distinguishing `"unknown user"` from `"wrong password"` when username enumeration is a risk. Use `AUTHENTICATION_REQUIRED` and a generic detail, logging the internal error type at an appropriate security level. Passwords must never be reflected in error JSON.

### 10.2. Do Not Disclose Internal Permissions via 403

Users normally only need to know `ACCESS_DENIED`. Avoid sending full authority lists, internal roles, policy evaluation traces, database table names, or other users' resources. Some APIs return 404 to hide resource existence, which is a separate **domain/security policy decision**; never turn 403 into 404 arbitrarily just to "match JSON".

### 10.3. Do Not Leak Exceptions in 500

`IllegalStateException: databasePassword=...`, stack traces, SQL, internal hosts, or Java package names must never be sent out. `INTERNAL_ERROR` responses still carry `correlationId` so the team can investigate in properly restricted logs. Use protected exception capture/tracing systems rather than relying on clients sending back raw stacks.

### 10.4. Preserve Protocol Statuses and Headers

Standardizing JSON errors does not mean dropping `WWW-Authenticate`, `Allow`, `Retry-After`, `Vary`, CORS, `Content-Language`, or cache directives when meaningful. The sample handlers preserve `ResponseStatusException.getHeaders()` and the writer standardizes content type; real systems must also test middleware/proxies, especially when CORS preflight or rate limiting responses are generated by outer filters.

### 10.5. Control Inputs and Outputs

Clients can pass Unicode/control chars or long strings in queries/paths. Never embed raw input into JSON via string concatenation: Jackson's serializer handles escaping, while validation/length limits belong in domain rules. Never reflect client `X-Correlation-Id` directly. For `instance`, use path without query; if the path contains secrets or sensitive IDs, use the route template instead.

### 10.6. Do Not Create a New Response After Commit

A stream that already emitted HTTP 200 and partial data cannot switch to a traditional `500 application/problem+json`. For SSE/NDJSON/WebSocket, define a dedicated error/event contract and clear close/retry semantics. Never call `response.writeWith` a second time after commit.

## 11. Distinguishing Business Error Handling

**Validation:** For JSON requests with invalid fields, an extension `violations` array such as `[{"field":"amount","code":"MUST_BE_POSITIVE"}]` can be added after filtering sensitive info. Never echo passwords or raw payloads. Choose 400 vs 422 consistently.

**Resource ownership:** When user A requests B's resource, `@PreAuthorize` or service/repository may return 403/404 per policy. Provide no details that let callers infer another user's resources exist.

**Concurrency:** An optimistic locking conflict is normally 409 with code `CONFLICT`, not 500. Return a stable code so the client can reload or ask the user to resolve.

**Rate limiting:** When exceeding limits, APIs can return 429 with `Retry-After` per policy; never output a guessed number of seconds. Correlation IDs help investigate throttled requests.

**Timeout/dependency failure:** Downstream 503/504 errors need retryability distinction; do not treat every network error as a user error. Never let bodies expose hostnames/URLs containing secrets.

**Cancelled requests:** When a client closes the connection before the response, the server cannot reliably send Problem JSON. Log `cancel` with `correlationId` if observability requires it, without claiming every failure has a wire body.

## 12. Acceptance Testing Matrix

| Scenario | Status | JSON code | Headers to check | Security test |
| --- | --- | --- | --- | --- |
| GET public | 200 | Error JSON not required | `X-Correlation-Id` | Leaks no auth info |
| GET protected anonymous | 401 | `AUTHENTICATION_REQUIRED` | `WWW-Authenticate` + correlation ID | Leaks no user info |
| Basic wrong password | 401 | `AUTHENTICATION_REQUIRED` | `WWW-Authenticate` | Does not echo raw password |
| Logged-in user missing role | 403 | `ACCESS_DENIED` | Correlation ID | Leaks no policy internals |
| Invalid parameter | 400 | `INVALID_REQUEST` | Correlation ID | Does not echo raw secret input |
| Unmapped route, logged in | 404 | `NOT_FOUND` | Correlation ID | Leaks no filesystem paths |
| Unexpected exception | 500 | `INTERNAL_ERROR` | Correlation ID | No stack trace/internal message |
| Forged correlation header | Per business logic | Per business logic | Server-issued ID | Client ID is untrusted |
| Two consecutive requests | Per business logic | Per business logic | **Two distinct IDs** | No static variable used |
| Streaming response errors after commit | Transport-dependent | Dedicated streaming contract | ID/logs | Does not write JSON after commit |

### 12.1. Investigation Order When JSON Is Inconsistent

1. Check the exact **HTTP status and Content-Type** of the divergent response; did a filter generate a response before the controller?
2. Check whether the request lacked Basic, had wrong Basic, lacked a role, or reached the controller; identify the 401/403 source first.
3. Verify `ServerHttpSecurity.httpBasic.authenticationEntryPoint` and `exceptionHandling.authenticationEntryPoint` use the **same** handler.
4. Verify `ServerAccessDeniedHandler` uses the shared writer and preserves status 403.
5. Verify `ErrorWebExceptionHandler` is selected by Spring Boot before the default handler; if 404 still returns HTML, check route error handlers/Accept headers.
6. Verify `CorrelationWebFilter` runs before security and the ID is not stripped or regenerated unintentionally by a proxy.
7. Verify bodies are never written after response commit; use a different strategy for SSE/streaming.
8. Run tests covering all 401/403/400/404/500 cases, checking headers and JSON fields rather than snapshots alone.
9. In deployed environments, check whether gateways/CDNs/ingress generate their own errors and how header propagation policies behave.
10. Correlate logs by ID, checking redaction, sampling, and retention. If logs lack the ID, first identify which hop produced the response.

## 13. Common Misconceptions

**"Just `@RestControllerAdvice` makes 401 and 403 JSON too."** Not guaranteed. Spring Security usually rejects inside WebFilters before the controller; reactive entry points/denied handlers are required.

**"401 and 403 both mean permission denied so share one status."** No. `401` is for needing authentication/challenges, while `403` is insufficient permission per policy. HTTP semantics must be preserved.

**"Since 401 returns JSON, we can drop WWW-Authenticate."** Not for standard HTTP Basic. The challenge header is a key part of the protocol.

**"Correlation ID only appears on errors."** Bad practice if end-to-end tracing is the goal: successful responses should also carry the ID.

**"Use email or username as correlation ID for convenience."** No. That is PII/identity, risks leakage, and fails to distinguish multiple requests from the same user.

**"Having a UUID grants API access."** No. The UUID here is an observability label with zero authentication or authorization role.

**"Using MDC.put makes WebFlux preserve the right ID across threads automatically."** No. Reactor Context/Micrometer Context Propagation or explicit passing is needed.

**"For consistency, return 500 for every error."** No. Keep a uniform body, while statuses still reflect input, permissions, resources, or infrastructure.

**"`ApiProblemWriter` can always write an error body whenever given a `Throwable`."** Not once the response is committed or if the error happens outside WebFlux. Handle per lifecycle/transport.

**"Adding a client-sent correlation header to logs is harmless."** Unsafe. It can be abused for log injection, huge payloads, or ID spoofing. Enforce trust boundaries and validation.

## 14. Production Adoption Checklist

1. Lock down the `application/problem+json` contract, standard RFC 9457 fields, `code`/`correlationId` extensions, and versioned error codes.
2. Distinguish 400/401/403/404/409/429/500/503 per HTTP semantics, preserving mandatory headers such as `WWW-Authenticate`.
3. Use a single service/writer to emit JSON; never build JSON with manual string concatenation.
4. Wire both HTTP Basic failure and missing-authentication entry points, plus the access-denied handler.
5. Standardize WebFlux/validation/domain errors, avoiding conflicts among `@RestControllerAdvice`, Boot default error handling, and custom `ErrorWebExceptionHandler`.
6. Generate correlation IDs early enough, scoped per request, without trusting unvalidated client values; return the header on both success and errors.
7. If tracing is present, align correlation IDs with trace/span infrastructure instead of overwriting `traceparent`.
8. Never write credentials, session cookies, tokens, SQL, or stack traces to responses/public logs.
9. Account for streaming/cancel/post-commit errors and define a separate contract if using SSE/WebSockets.
10. Automate tests for 401/403/400/404/500, challenges, content type, status-vs-body parity, ID header/body parity, distinct IDs across requests, and message redaction.
11. Test end-to-end through gateways/CDNs, forwarded headers, CORS, rate limits, and reverse proxies; do not treat localhost tests as sufficient for the full system.
12. When upgrading Spring Security/Boot versions, rerun integration tests because filter ordering, error handling, and default headers can change.

## 15. Self-Check Questions

**Question 1.** A user sends no Basic credentials to `/api/me`. Which layer usually generates 401?  
Spring Security's `ServerAuthenticationEntryPoint` when authorization requires authentication, without necessarily invoking any controller method.

**Question 2.** A user enters a wrong password and also receives 401. Where do you configure it so the JSON matches the missing-credentials case?  
Configure the same entry point in both `httpBasic(...authenticationEntryPoint(...))` **and** `exceptionHandling(...authenticationEntryPoint(...))`.

**Question 3.** Alice is logged in without ADMIN and calls `/api/admin`. Why 403 instead of 401?  
Authentication succeeded, authorization lacked permissions; `ServerAccessDeniedHandler` handles it without issuing a Basic challenge as if credentials were missing.

**Question 4.** Why isn't `@RestControllerAdvice` guaranteed to catch all Security errors?  
Because Security WebFilters execute before the controller layer; many 401/403 errors are never thrown from handler methods.

**Question 5.** Can `correlationId` contain a Bearer token or session ID?  
**No.** It is tracing metadata, not a storage place for credentials or sensitive information.

**Question 6.** Should an HTTP 500 response return `SQLException.getMessage()` to the client?  
**No.** Return `INTERNAL_ERROR`/a safe detail and log the root cause in an access-restricted store correlated by correlation ID.

**Question 7.** One WebFlux thread serves multiple requests. Should a static variable store the current correlation ID?  
**No.** Use exchange attributes/Reactor Context or tracing integration scoped per request/subscriber.

**Question 8.** An API already sent half a Flux body with HTTP 200, then an exception occurred. Can it switch to 500 Problem JSON?  
**No** if the response is already committed. A streaming-specific error strategy/close semantics is needed.

**Question 9.** If a client sends `X-Correlation-Id: attacker-picked-id`, what will the demo return?  
A new server-issued UUID, ignoring the untrusted client string.

**Question 10.** Once using `application/problem+json`, can standard HTTP status codes be omitted?  
**No.** The body aids diagnostics, while the HTTP status and protocol headers remain the network contract.

### Official Documentation

- RFC 9457, *Problem Details for HTTP APIs*: https://www.rfc-editor.org/rfc/rfc9457
- Spring Boot, *Reactive Web Applications — Error Handling*: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework, *Error Responses / ProblemDetail*: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Security, *WebFlux Security*: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security API, `ServerHttpSecurity.HttpBasicSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security API, `ServerHttpSecurity.ExceptionHandlingSpec`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security API, `ServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- Spring Security API, `ServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- Spring Boot API, `ErrorWebExceptionHandler`: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/reactive/error/ErrorWebExceptionHandler.html
- W3C, *Trace Context*: https://www.w3.org/TR/trace-context/
- Spring Framework, *WebTestClient*: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html

**Key takeaway:** Consistent JSON errors take more than a record. You need the same schema/writer for **Spring Security 401/403 and WebFlux 4xx/5xx**, accurate HTTP statuses/headers, **per-request correlation IDs**, distrust of unvalidated client IDs, no credential/stack-trace leaks, and integration tests across layers. That gives clients predictable errors while operations can pinpoint requests in logs without weakening security.