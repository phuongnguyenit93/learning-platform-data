# Masking Sensitive Data and Correlating Logs with a Correlation ID in Spring Security

> **Context:** Spring Security 6.x, Spring Boot 3.x, Spring MVC/Servlet, Java 17+. This lesson teaches how to log for observability and debugging without **leaking passwords, tokens, session IDs, cookies, or personal data**, while attaching a correlation ID (`correlation ID`) to logs belonging to the same HTTP request. Examples use SLF4J, Logback, `MDC`, `OncePerRequestFilter`, HTTP Basic, and MockMvc. A correlation ID is an event lookup tool—**not a credential, authorization mechanism, or guarantee that all logged data is safe**.

## 1. Real-World Problem: Finding the Right Event Without Exposing Secrets

A user calls a protected API:

```http
GET /api/me HTTP/1.1
Authorization: Basic <credential>
X-Correlation-ID: <client-supplied-value>
```

The application may return 401 for failed authentication, 403 for missing permissions, 500 for a server error, or 200 on success. When investigating, we want to answer:

1. Which request failed and when did it occur?
2. Which **category** of endpoint was handled? What were the HTTP method and status code?
3. Which events in filters, controllers, services, and handlers belonged to the same request?
4. Was a 401 an authentication failure, or was a 403 a permission/CSRF issue?
5. How can support be given a lookup code without **sharing passwords, bearer tokens, cookies, or sensitive stack traces**?

A dangerous logging habit is dumping the entire request: headers, query string, form body, or DTOs. `Authorization` and `Cookie` can hold session-hijacking material; `password`, `apiKey`, `refreshToken`, `client_secret`, and one-time codes are also secrets. Even usernames, emails, phone numbers, IPs, or paths containing user IDs can be personal data requiring restricted access.

Instead of logging requests indiscriminately, define an **event schema allowing a minimal set of fields**:

| Log Field | Safe Example | Why Useful |
| --- | --- | --- |
| `timestamp` | Recorded by the logging system | Establishes sequence and incident window |
| `level` | `INFO`, `WARN`, `ERROR` | Separates operational info from exceptions |
| `event` | `http.completed`, `app.failure` | Finds events by type without reading bodies |
| `correlationId` | Newly generated UUID, e.g., `9d9e...` | Joins logs from the same request |
| `method` | `GET`, `POST`, `OTHER` | Analyzes processing path |
| `route` | `public`, `profile`, `admin`, `other` | Classifies endpoints without logging raw paths |
| `httpStatus` | `200`, `401`, `403`, `500` | Matches the failing step |
| `durationMs` | `12` | Evaluates latency |
| `errorCode` | `DEMO_FAILURE` or approved code | Categorizes errors without sensitive text |

Data needing protection is not limited to password-like values. Treat anything arriving from the network, URLs, exception messages, payloads, databases, or external services as **potentially sensitive or capable of manipulating logs** until classified.

**Core principle:** *choosing safe fields to log* (`allowlist logging`) is better than *logging everything and trying to scrub a few sensitive strings*. Redaction/masking still helps as defense in depth, yet cannot fix every case where data was logged upfront.

## 2. Distinguishing Correlation ID, Trace ID, Span ID, and Session ID

These terms often appear side by side, yet are not synonymous:

| Concept | Function | Source in This Guide | Authentication Secret? |
| --- | --- | --- | --- |
| **Correlation ID / request ID** | Lookup label connecting events for a request | Server-generated UUID per inbound HTTP request | No. Never use as proof of identity |
| **Trace ID** | Connects spans of one trace across services | Distributed tracing system, e.g., Micrometer Tracing/OpenTelemetry | Not a credential; may be operational data to keep non-public |
| **Span ID** | Identifies one unit of work within a trace | Tracing system | Not an access token |
| **Session ID** | Points to a login/application session | Servlet/session store | **Sensitive**; never log verbatim |
| **Bearer/access/refresh token** | Proves access rights or renews access | Identity provider / auth system | **Highly sensitive**; never log |
| **User ID/email** | Identifies a user | Data system | Can be PII; log only per approved policy and purpose |

A UUID request ID can find events for **one request** inside one service. To correlate steps *across multiple microservices*, propagate context through HTTP clients, message queues, or proper tracing instrumentation. Generating an ID on server A alone **does not make** server B's logs share that ID.

In systems already using **Micrometer Tracing/OpenTelemetry**, generally reuse the library-provided trace/span context and propagation instead of inventing a second distributed tracing mechanism. Spring Boot supports log correlation when tracing is enabled. This lesson intentionally builds a simple request ID to teach MDC and safety boundaries; it **does not replace distributed tracing**.

## 3. Threat Model: What Must Never Leak Into Logs?

### 3.1. Data Categories Typically Excluded from Logs

- `Authorization` headers, Basic credentials, Bearer tokens, OAuth2 authorization codes, refresh tokens, verbatim JWTs.
- Passwords, password-reset tokens, OTP codes, secret questions, API keys, private keys, connection strings with secrets.
- `Cookie`, `Set-Cookie`, `JSESSIONID`, or raw session identifiers.
- Request/response bodies containing payment data, health data, personal identifiers, or internal documents.
- URLs/query strings with `?token=...`, `?password=...`, emails, ID numbers; path parameters can also be PII.
- Values from `exception.getMessage()`, DTO `toString()`, or library-generated exception causes: these can include SQL, file paths, usernames, or secrets.
- Entire environment configs, environment variables, private certificates, database query payloads, and full stack traces from uncontrolled sources.

Do not assume "hashed means public." Direct SHA-256 hashes of passwords, phone numbers, or emails can be dictionary-attacked because their value spaces are small or repetitive. When pseudonymized identity linkage across events is genuinely needed, consider **HMAC with a separately managed key, explicit purpose, and retention limit**; pseudonyms can still constitute personal data. In this example, even hashed usernames are unnecessary.

### 3.2. Log Injection and Spoofing Correlation IDs

Client-supplied values can contain newlines, control characters, or text crafted to look like a new log entry. For example, if an app writes `log.info("cid={}", request.getHeader("X-Correlation-ID"))`, a client can send weird characters to garble logs or pick someone else's ID to **mis-link** unrelated requests.

Therefore, this example **does not trust** client-supplied `X-Correlation-ID`. It **always generates a fresh UUID** and logs only that UUID. If your architecture must accept a request ID from a trusted API gateway, define the trust boundary: the gateway strips client-supplied headers, generates/normalizes the ID, enforces length/character allowlists, and clearly separates **external request ID** from **internal trusted ID**. Format validation alone does not prove an ID's origin.

The `X-Correlation-ID` response header here is solely a lookup key for error reporting. It grants no permissions, creates no session, and cannot serve as a login token. Never embed secrets inside correlation IDs.

### 3.3. Log Levels Are Not a Security Boundary

`DEBUG` or `TRACE` can help analyze `FilterChainProxy`, `AuthenticationManager`, and `AuthorizationFilter`, yet enabling them does not guarantee log redaction. Frameworks, libraries, or custom code may emit extra details. Enable verbose levels only in approved environments with short retention and proper log access controls. Never enable `@EnableWebSecurity(debug = true)` broadly in production just to "inspect requests."

## 4. Designing a Safe Request Logging Flow

We want this structure:

```text
HTTP request
   |
   v
Servlet CorrelationIdFilter (high precedence)
  - generates a fresh server-side UUID
  - sets request attribute: correlationId
  - sets response header X-Correlation-ID
  - puts MDC["cid"] = UUID
  - logs http.started event with classified route
   |
   v
Spring Security / FilterChainProxy
  - if Basic is wrong or missing credentials -> 401
  - if authenticated yet missing role -> 403
   |
   v
@RestController / Service
  - logs business events by event code, no secrets
  - may throw exception
   |
   v
@RestControllerAdvice (for domain errors handled by MVC)
  - public error response without stack trace
  - may include the request's correlation ID
   |
   v
finally in CorrelationIdFilter
  - logs http.completed status + duration
  - clears/restores MDC to avoid polluting the next request
   |
   v
HTTP response + X-Correlation-ID
```

**MDC (`Mapped Diagnostic Context`)** is a set of key/value pairs attached to a thread's logging context, supported by SLF4J/Logback. After `MDC.put("cid", id)`, subsequent `log.info(...)` calls on **the same thread** can print `cid` via the log pattern. `MDC` does not cross threads automatically. Request threads are pooled and reused, so **clearing it in `finally` is mandatory**.

Never just set MDC and forget to restore it: the next request could inherit the previous request's ID, confusing incidents and leaking cross-user associations. This guide uses `String previous = MDC.get("cid")` to restore any prior value rather than wiping MDC data owned by an outer context.

## 5. Runnable Example on Spring Boot 3 and Security 6

### 5.1. Endpoints and Expected Behavior

| Endpoint | Who Can Access? | Behavior |
| --- | --- | --- |
| `GET /public` | Everyone | Returns body `public`, HTTP 200 |
| `GET /api/me` | Authenticated users | Returns `hello reader` or `hello admin` |
| `GET /api/admin` | `ROLE_ADMIN` only | Other authenticated users get 403 |
| `GET /api/fail` | Authenticated users | Demonstrates controlled failure: 500 with JSON error code + correlation ID |

Two **demo** accounts: `reader / reader-pass` with role USER and `admin / admin-pass` with role ADMIN. Never use these hardcoded credentials outside learning environments.

Key design choices:

1. The correlation filter is registered as a high-priority **Servlet Filter**, running ahead of Spring Security's servlet filter; thus even security-generated 401/403 responses carry a lookup ID.
2. Never copy `X-Correlation-ID`/`X-Request-ID` from the client; generate a new UUID.
3. Log routes using a **fixed label set** (`public`, `me`, `admin`, `fail`, `other`); never log raw paths or query strings.
4. Log HTTP method after classification; never log headers, bodies, credentials, usernames, or tokens.
5. Use `MDC.put` / restore in `finally` to attach the ID to logs across synchronous layers on the same thread.
6. Error handlers return public error codes, never `exception.getMessage()`, stack traces, or request details.
7. Demo endpoints use GET only; no need to disable CSRF. For write APIs, design CSRF per the authentication model and caller.

### 5.2. Dependencies

Create a Spring Boot 3.x project with Java 17+ and Gradle. In a `build.gradle` already configured with the Spring Boot plugin/repositories, `dependencies` needs:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is the **dependencies block**, not a full `build.gradle` file. Standard starters include SLF4J/Logback with Spring Boot's default logging setup. If a project swaps in Log4j2 or another logging backend, adapt the pattern syntax accordingly.

### 5.3. Complete Java File

Create **`src/main/java/demo/DemoApplication.java`**:

```java
package demo;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password(encoder.encode("reader-pass"))
                        .roles("USER").build(),
                User.withUsername("admin")
                        .password(encoder.encode("admin-pass"))
                        .roles("ADMIN").build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class CorrelationIdFilter extends OncePerRequestFilter {
    static final String ATTRIBUTE = "demo.correlationId";
    static final String HEADER = "X-Correlation-ID";

    private static final Logger log =
            LoggerFactory.getLogger(CorrelationIdFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String cid = UUID.randomUUID().toString();
        String previous = MDC.get("cid");
        long started = System.nanoTime();

        request.setAttribute(ATTRIBUTE, cid);
        response.setHeader(HEADER, cid);
        MDC.put("cid", cid);

        String route = safeRoute(request.getServletPath());
        String method = safeMethod(request.getMethod());

        try {
            log.info("http.started method={} route={}", method, route);
            filterChain.doFilter(request, response);
        } finally {
            long durationMs =
                    (System.nanoTime() - started) / 1_000_000;

            log.info(
                    "http.completed method={} route={} status={} durationMs={}",
                    method, route, response.getStatus(), durationMs);

            if (previous == null) {
                MDC.remove("cid");
            } else {
                MDC.put("cid", previous);
            }
        }
    }

    private static String safeRoute(String servletPath) {
        return switch (servletPath) {
            case "/public" -> "public";
            case "/api/me" -> "me";
            case "/api/admin" -> "admin";
            case "/api/fail" -> "fail";
            default -> "other";
        };
    }

    private static String safeMethod(String requestMethod) {
        return switch (requestMethod) {
            case "GET" -> "GET";
            case "POST" -> "POST";
            case "PUT" -> "PUT";
            case "PATCH" -> "PATCH";
            case "DELETE" -> "DELETE";
            default -> "OTHER";
        };
    }
}

class DemoFailure extends RuntimeException {
}

record ApiError(String code, String correlationId) {
}

@RestController
class DemoController {
    private static final Logger log =
            LoggerFactory.getLogger(DemoController.class);

    @GetMapping("/public")
    String publicPage() {
        log.info("public.page.viewed");
        return "public";
    }

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        log.info("profile.viewed");
        return "hello " + authentication.getName();
    }

    @GetMapping("/api/admin")
    String adminPage() {
        log.info("admin.page.viewed");
        return "admin";
    }

    @GetMapping("/api/fail")
    String fail() {
        log.warn("operation.failed code=DEMO_FAILURE");
        throw new DemoFailure();
    }
}

@RestControllerAdvice
class ApiFailureHandler {
    private static final Logger log =
            LoggerFactory.getLogger(ApiFailureHandler.class);

    @ExceptionHandler(DemoFailure.class)
    ResponseEntity<ApiError> fail(HttpServletRequest request) {
        log.warn("http.error.translated code=DEMO_FAILURE");

        String cid = (String) request.getAttribute(
                CorrelationIdFilter.ATTRIBUTE);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError("operation_failed", cid));
    }
}
```

**Why this example works:** only `DemoApplication` is `public`; `SecurityConfig`, `CorrelationIdFilter`, `DemoController`, `ApiFailureHandler`, and helper types are package-private top-level types in the `demo` package. `@SpringBootApplication` component-scans the beans, and `@Order(Ordered.HIGHEST_PRECEDENCE)` prioritizes the filter ahead of the default security filter in standard Spring Boot setups. `record`, switch expressions, and imports fit Java 17+.

**Note on filter placement:** `CorrelationIdFilter` here is a **Spring Boot–registered Servlet filter**, not inside `SecurityFilterChain` via `http.addFilterBefore(...)`. Never register **the exact same filter instance** twice in both the servlet container and the Spring Security chain, as it can execute twice and make ordering confusing. Check actual filter registration/ordering when a project has custom filters or overrides `spring.security.filter.order`.

### 5.4. Configuring Format So Logs Actually Show CID

Create **`src/main/resources/application.properties`**:

```properties
spring.application.name=security-log-demo

# Add MDC cid to the level section of Logback console logs.
logging.pattern.level=%5p [cid:%X{cid}]

# Do not enable global DEBUG/TRACE in the example.
logging.level.root=INFO
```

Here `%X{cid}` reads the MDC `cid` value on **the thread writing the log**. Events from the filter or controller during the same request show `[cid:...]`; startup or background logs without a CID show `[cid:]`. For other logging setups, adjust the matching pattern/appender. Creating a UUID and putting it in MDC **does not make logs show the ID** unless the pattern or JSON encoder outputs it.

**Never log raw client-supplied CIDs:** the example generates an internal UUID and returns it in `X-Correlation-ID`; regardless of any `X-Correlation-ID` the client sends, the program still creates a fresh ID. That prevents log injection and mis-linking requests via spoofed headers in the demo.

### 5.5. Running the Application

Using Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

By default unless `server.port` is changed, the app listens at `http://localhost:8080`. From another terminal:

```bash
# Public request: 200 and X-Correlation-ID.
curl -i http://localhost:8080/public

# No credentials: typically 401, still has X-Correlation-ID.
curl -i http://localhost:8080/api/me

# Wrong credentials: 401; password must not appear in app logs.
curl -i -u reader:wrong-password http://localhost:8080/api/me

# Valid credentials: 200, body "hello reader".
curl -i -u reader:reader-pass http://localhost:8080/api/me

# Authenticated yet missing ADMIN role: 403.
curl -i -u reader:reader-pass http://localhost:8080/api/admin

# Sufficient role: 200, body "admin".
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Controlled failure: 500, JSON contains code + CID.
curl -i -u reader:reader-pass http://localhost:8080/api/fail

# Client tries sending custom CID: server still generates a fresh CID.
curl -i -H "X-Correlation-ID: client-picked-value" \
  http://localhost:8080/public
```

If `curl` in PowerShell is aliased to `Invoke-WebRequest`, use `curl.exe`. Trailing `\` is Bash line-continuation syntax; in PowerShell, put each `curl.exe` command on one line or use PowerShell's line continuation.

Expected results:

| Case | HTTP | CID Returned to Client | Safe App Logs |
| --- | --- | --- | --- |
| `/public` | 200 | Fresh UUID | `http.started`, `public.page.viewed`, `http.completed status=200` |
| `/api/me` without credentials | 401 | Fresh UUID | Filter event, status 401; no header logged |
| `/api/me` wrong password | 401 | Fresh UUID | Filter event, status 401; no password logged |
| `/api/me` valid `reader` | 200 | Fresh UUID | `profile.viewed` and status 200 |
| `/api/admin` valid `reader` | 403 | Fresh UUID | Filter event, status 403; no token printed |
| `/api/admin` valid `admin` | 200 | Fresh UUID | `admin.page.viewed` |
| `/api/fail` valid `reader` | 500 | Same CID in header and JSON | `operation.failed`, `http.error.translated`, `http.completed status=500` |
| Client sends custom `X-Correlation-ID` | 200 | **Server-generated UUID, not client value** | Client-supplied value not printed |

An **illustrative format** log sequence (UUIDs, timestamps, and durations change on each run):

```text
INFO [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] http.started method=GET route=fail
WARN [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] operation.failed code=DEMO_FAILURE
WARN [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] http.error.translated code=DEMO_FAILURE
INFO [cid:6ccfaef0-e0f0-4935-9900-60ffb66d2e4c] http.completed method=GET route=fail status=500 durationMs=7
```

These are **illustrative messages and MDC output**, not the full default Spring Boot format; logger names, threads, timestamps, and processing times will vary. Do not assert a fixed duration or fixed UUID.

## 6. Why Does the Code Avoid Exposing Credentials?

### 6.1. Select Log Fields Before Passing Data to the Logger

Safe statement in the filter:

```java
log.info(
        "http.completed method={} route={} status={} durationMs={}",
        method, route, response.getStatus(), durationMs);
```

These four fields are: method normalized to fixed choices, route label from a literal `switch`, status from the response, and duration via monotonic clock. There is no `request.getHeader("Authorization")`, `request.getQueryString()`, `request.getParameterMap()`, raw URI, request body, or password.

**Anti-pattern never to use in production:**

```java
// DO NOT DO THIS: exposes secret values.
log.info("login username={} password={}", username, password);
log.debug("raw Authorization={}", request.getHeader("Authorization"));
log.info("all request params={}", request.getParameterMap());
```

This is an **anti-pattern snippet**, not part of the runnable program. Even at DEBUG level, logs can be re-enabled, shipped to aggregators, retained long-term, or read by support staff. Never justify keeping secrets in log statements with "DEBUG is off right now."

Beware of `@Data`/`@ToString` (Lombok), Java records holding passwords, logging entities, and `log.error("{}", exception)`: a `toString()` or exception message can attach bodies or secrets without the caller realizing it.

### 6.2. CID Appears Even When Spring Security Blocks the Request

Because the correlation filter runs at the servlet level **before Spring Security** in the demo config, it sets the CID before handing off to `FilterChainProxy`. If `BasicAuthenticationFilter` returns 401 or `AuthorizationFilter` denies with 403, the request still unwinds through the correlation filter's `finally` block, emitting the completion log with the same CID and setting the response CID header.

That is why the example does not assign CIDs only inside `@RestControllerAdvice` or controllers: security filters can reject requests before MVC runs, leaving controllers/advice no chance to tag those errors. For method security or MVC exceptions, the request still executes under the filter, so MDC and the request attribute remain available.

**Limitation:** errors rejected **before reaching servlet filters** (gateways, load balancers, TLS handshakes, upstream WAFs) will not carry this CID. Upstream systems need their own correlation/tracing.

### 6.3. Cleaning Up MDC Properly

The `MDC` value here belongs only to the currently executing thread. With servlet thread pools, request A and request B can reuse the same worker thread at different times:

```text
Thread "http-nio-8080-exec-3"
  Request A -> MDC cid=A -> logs(A) -> finally restore/remove A
  Request B -> MDC cid=B -> logs(B) -> finally restore/remove B
```

Forgetting `finally` can cause request B's logs to carry request A's CID. Overwriting another tracing framework's or component's MDC without restoring it can drop outer context. The `previous` + `finally` pattern preserves any prior `cid` on **the same thread**; when none existed, `MDC.remove("cid")` clears the key.

Do not roll your own `ThreadLocal` to replace MDC if your logging system already supports MDC, unless there is a specific reason and strict lifecycle management.

## 7. Testing Correlation and Zero Credential Leakage

`MockMvc` sends requests through the test app's MVC + servlet filters without opening a network port. The tests below verify:

- `X-Correlation-ID` appears on both successful responses and responses rejected by Spring Security.
- CID is valid UUID syntax; two independent requests receive distinct IDs.
- A client-forged `X-Correlation-ID` header is never echoed back by the server.
- Logs for a request contain the CID yet **do not contain the test password**.
- The error handler returns JSON with the same CID as the response header and leaks no exception details.
- A valid principal denied `/api/admin` due to missing role is distinguished from a password failure.

Create `src/test/java/demo/CorrelationLoggingTest.java`:

```java
package demo;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@ExtendWith(OutputCaptureExtension.class)
class CorrelationLoggingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRequestsReceiveFreshServerGeneratedIds()
            throws Exception {
        MvcResult first = mvc.perform(get("/public")
                        .header("X-Correlation-ID", "client-forged-id"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"))
                .andReturn();

        MvcResult second = mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andReturn();

        String a = first.getResponse().getHeader("X-Correlation-ID");
        String b = second.getResponse().getHeader("X-Correlation-ID");

        assertNotNull(a);
        assertNotNull(b);
        UUID.fromString(a);
        UUID.fromString(b);
        assertNotEquals(a, b);
        assertNotEquals("client-forged-id", a);
    }

    @Test
    void unauthenticatedRequestStillHasId() throws Exception {
        MvcResult result = mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized())
                .andReturn();

        String cid = result.getResponse().getHeader("X-Correlation-ID");
        assertNotNull(cid);
        UUID.fromString(cid);
    }

    @Test
    void successfulUserRequestHasIdAndSafeBody() throws Exception {
        MvcResult result = mvc.perform(get("/api/me")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("hello reader"))
                .andReturn();

        assertNotNull(result.getResponse().getHeader("X-Correlation-ID"));
    }

    @Test
    void forbiddenAdminRequestStillHasId() throws Exception {
        MvcResult result = mvc.perform(get("/api/admin")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isForbidden())
                .andReturn();

        assertNotNull(result.getResponse().getHeader("X-Correlation-ID"));
    }

    @Test
    void appErrorUsesSameIdInBodyAndHeader() throws Exception {
        MvcResult result = mvc.perform(get("/api/fail")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isInternalServerError())
                .andReturn();

        String cid = result.getResponse().getHeader("X-Correlation-ID");
        assertNotNull(cid);
        assertThat(result.getResponse().getContentAsString())
                .contains("\"code\":\"operation_failed\"")
                .contains("\"correlationId\":\"" + cid + "\"")
                .doesNotContain("DemoFailure")
                .doesNotContain("reader-pass");
    }

    @Test
    void logsLinkByIdWithoutEchoingWrongPassword(
            CapturedOutput output) throws Exception {
        String secretFromClient = "DO_NOT_LOG_bad-password_7271";

        MvcResult result = mvc.perform(get("/api/me")
                        .with(httpBasic("reader", secretFromClient)))
                .andExpect(status().isUnauthorized())
                .andReturn();

        String cid = result.getResponse().getHeader("X-Correlation-ID");
        assertNotNull(cid);
        assertThat(output.getOut())
                .contains("cid:" + cid)
                .contains("http.completed")
                .doesNotContain(secretFromClient)
                .doesNotContain("Authorization: Basic");
    }
}
```

**Testing note:** the test uses `OutputCaptureExtension` from `spring-boot-starter-test` to capture JVM console logs. The `cid:...` assertion depends on `logging.pattern.level` in the properties file above; if you switch to a JSON appender or different log format, update the test to match the actual schema rather than **deleting the assertion verifying CID presence**.

`doesNotContain(secretFromClient)` only checks the current test log path and test environment; it does not prove every logger, profile, or dependency cannot log credentials. In larger apps, add logging policy code reviews, regression tests on bodies/headers/exceptions, log-aggregation audits, pipeline DLP/redaction, and real access-control reviews.

Run tests:

```bash
./gradlew test
```

Run only this class:

```bash
./gradlew test --tests demo.CorrelationLoggingTest
```

Equivalent command on Windows:

```powershell
.\gradlew.bat test --tests demo.CorrelationLoggingTest
```

**Expected outcome:** assertions pass with the exact project, files, and configuration from the example. No fixed UUIDs, timings, or stdout should be hardcoded; IDs vary per request.

## 8. Debugging Authentication and Authorization Errors with a Correlation ID

Suppose a user reports: "The API returned 403, correlation ID `8a7...`." Safe investigation steps:

1. **Verify the ID** came from the server-issued header rather than an arbitrary client-supplied string. In the demo, the server always generates a UUID. Real systems may generate/tag IDs at a trusted gateway.
2. **Search logs by CID** within the right time window and environment. Never ask the user to send passwords, tokens, or session cookies "to check."
3. Inspect `event=http.completed` or equivalent messages for method, route category, status, and duration; no raw PII-bearing URL is needed.
4. If HTTP 401, check the authentication mechanism (Basic/form/Bearer), **without logging credentials**. Use a generic error code like `AUTH_FAILURE` alongside a restricted internal reason category.
5. If HTTP 403, check authorization, CSRF, request matchers, roles/authorities, and method security; never assume "missing role" from status alone.
6. If 500, look up `app.failure` and error code, and inspect metrics/traces with proper access; never send sensitive stack traces to clients.
7. If the request crossed multiple services, follow the trace ID/span ID or a propagation ID secured across trust boundaries; never expect one service's local CID to appear automatically in another service.
8. Once resolved, document the error code and fix, turn off any temporary TRACE/DEBUG, and purge unneeded logs per retention policy.

### Security Event Logs Should Be Structured

A real system may need audit events like `authentication.succeeded`, `authentication.failed`, `authorization.denied`, `account.locked`, or `token.revoked`. Each event should define a **schema**, severity, approved internal reason codes, correlation ID, and actor-identifier protection.

Never pack sensitive data into event details to speed up debugging. For instance, `BAD_CREDENTIALS` is completely different from logging the raw password. Also never skip events from "trusted internal users"—insiders and third-party integrations still require proper auditing.

Security events from filters can be emitted through Spring Security's supported event handlers/listeners or observation hooks rather than catching every `AuthenticationException` and logging raw exceptions. Note that many authentication errors are handled **before MVC controllers**, so `@RestControllerAdvice` does not cover all of them.

## 9. MDC in Async, Task Pools, and Microservices

### 9.1. Why Can MDC Disappear Across Thread Switches?

`MDC` is normally thread-bound. If a controller spawns an `@Async` task, uses `CompletableFuture`, submits to a thread pool, or publishes a message, that work may run on another thread. A request ID set in a servlet filter **does not automatically appear on async threads**. Thread pools also reuse threads, so copying MDC without restoring/clearing it can attach the wrong CID to another task.

The right implementation depends on the executor/framework. With Spring's `TaskDecorator`, you can copy and **restore** context within the task's scope. The snippet below illustrates the principle and is **not automatically wired into the demo app**:

```java
@Bean
TaskDecorator copyMdcForTask() {
    return task -> {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    };
}
```

This requires importing `java.util.Map`, `org.slf4j.MDC`, `org.springframework.core.task.TaskDecorator`, and `org.springframework.context.annotation.Bean` inside a `@Configuration` class. For it to take effect on a specific executor, you must **configure that executor to actually use the TaskDecorator**. Do not drop this in mechanically if your system already uses tracing context propagation or multiple executors.

### 9.2. Propagation Across HTTP and Messages

In microservices, a request may call A → B → C. Two approaches exist:

- Use **Micrometer Tracing/OpenTelemetry** and W3C Trace Context (`traceparent`/`tracestate`) so instrumentation creates and propagates trace/span IDs cleanly.
- Use a custom request ID with **strict propagation rules**: separate client-provided, gateway-generated, and internal IDs; validate length/character sets, record provenance, bound trust, and prevent clients from injecting themselves into another request's logs.

Never use a correlation ID as a cache key, proof of authorization, or let users retrieve internal details merely because they know an ID. If returning a CID in error responses, any lookup endpoint still requires separate authentication and authorization.

### 9.3. Error Dispatches, Async Dispatches, and Filter Ordering

`OncePerRequestFilter` ensures filter logic runs once **per configured dispatch scope**; it does not mean "every thread and every dispatch of a request automatically shares the same MDC." By default, `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()` may skip additional dispatches depending on servlet/container config.

This example handles only **synchronous requests** with controllers returning strings or MVC handlers returning `ResponseEntity`; the CID is attached during the `REQUEST` dispatch and logged on completion. For async controllers, streaming responses, `ERROR` dispatches, or gateway-side errors, test the real lifecycle, watching when the response commits and how CID propagates. When configuring a filter for multiple dispatches, avoid generating **a brand-new CID** for each step of the same logical request; reuse the existing request attribute instead.

## 10. Redaction/Masking in Large Systems

### 10.1. Prioritize Safe Log Design at the Source

Define a **clear schema** for security/app events using fixed keys such as `event`, `cid`, `status`, `durationMs`, and `errorCode`. Never log `HttpServletRequest` objects or full DTOs. If user-related data is strictly needed, classify PII, define who may view it, level of detail, retention, and lawful-basis checks.

**Structured logging** (JSON) makes field-based searching easier and can help scrub sensitive keys in the logging pipeline. Yet structured logging **is not automatically safe**: `log.atInfo().addKeyValue("password", password)` still leaks the secret. The golden rule is **never put secrets into log events**.

### 10.2. When Display Masking Is Required

Some systems have approved audit requirements, such as showing the last four characters of a *non-secret* transaction reference or logging a standard error code. Apply **type-aware** masking rules rather than vague regexes across unstructured text. A regex matching `password` can miss `pwd`, `clientSecret`, nested JSON, encodings, or library-emitted lines.

For tokens, sessions, and passwords, the default choice is **do not log them at all**, rather than logging them with the last three characters masked. Even a partial token can still pose a risk or aid activity correlation.

### 10.3. Additional Layers of Control

1. **Least privilege:** log-viewer accounts do not automatically get access to every environment or tenant.
2. **Retention:** keep logs only as long as operational needs and policy dictate; enforce automated expiration.
3. **Encryption and transport:** protect logs in transit and at rest.
4. **Access auditing:** record who accessed, downloaded, or exported sensitive logs.
5. **Aggregator-level redaction:** serves as a fallback for third-party dependencies outside your control, never a substitute for blocking secrets at the source.
6. **DLP/secret scanning:** scan log streams to detect newly introduced leak formats.
7. **Never log arbitrary response bodies:** they can contain tokens, customer data, document contents, or banking details.
8. **Standardize event codes:** enables incident lookup without storing raw exception messages.
9. **Rate limiting/sampling for logs:** prevents log floods and cost spikes without dropping mandatory audit events.
10. **Separate audit logs from debug logs:** purposes, retention, and viewer permissions differ; never let a temporary TRACE capture turn into permanent audit storage.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Logging all headers/bodies "to debug faster" | Exposes `Authorization`, `Cookie`, PII, passwords | Log only allowlisted fields; omit sensitive headers/bodies |
| Logging `request.getRequestURI()` verbatim | Path may contain PII or log-injection input | Log classified route templates/fixed labels |
| Trusting `X-Request-ID` from any client | Clients can spoof CIDs, tangle logs, inject control characters | Generate internal IDs; accept only from trusted gateways with validation |
| Treating CID as a credential | Unauthorized access if a lookup API relies solely on CID | CID is for lookup only; endpoints must still enforce permissions |
| Setting MDC without formatting the logger | Logs omit CID even though code put it | Configure log pattern or JSON layout to emit MDC |
| Forgetting to clear MDC | Previous request's CID bleeds into the next request | Use `finally` to restore/remove; test repeated requests |
| Assigning CID only inside controllers | SecurityFilterChain 401/403 responses lack an ID | Place observability filter appropriately ahead of security |
| Registering the same filter in both servlet and Spring Security chains | Double execution, unpredictable ordering/lifecycle | Pick one registration mechanism and test it |
| Logging exception messages unconditionally | User input, SQL, or secrets can leak | Use error codes and classified exceptions |
| Leaving `TRACE` on long-term across all packages | High volume, leaks, and higher cost | Enable scoped temporarily; restrict access and retention |
| Assuming MDC crosses `@Async` automatically | Lost CID or leaked wrong CID | Propagate via executor/tracing context and clean up in `finally` |
| Using MD5/SHA-256(password) to "hide passwords" | Hashes can be cracked and remain sensitive data | Never log passwords, neither plaintext nor hashed |
| Returning raw stack traces in error JSON | Exposes internals/data | Return generic error code + CID; keep details in protected logs |
| Testing CID only on HTTP 200 | Unknown whether 401/403/500 carry an ID | Test all branches, including filter-level rejections |
| Assuming a local correlation ID joins all microservices | No context propagation across services | Use Micrometer Tracing/OpenTelemetry or trusted propagation |

## 12. Deployment Checklist and Practice Exercises

### Pre-Production Checklist

1. Log schema includes event code, CID, method/route/status/duration, and **zero unnecessary credentials/PII**.
2. Servlet filter/middleware runs early enough that security-rejected requests still receive an ID; avoid duplicate registration.
3. CIDs are generated from a trusted source; client headers are never trusted blindly; IDs enforce size and character constraints.
4. MDC has a clear lifecycle, is restored/cleared in `finally`, and propagates across async boundaries when needed.
5. The pattern or structured log encoder actually emits CID; field names and formats are consistent.
6. HTTP responses include the right correlation ID for support lookup without exposing internal exceptions or stack traces.
7. All major HTTP statuses (200, 401, 403, 500) have tests verifying CID presence; wrong credentials never appear in logs.
8. Authn/authz event codes classify accurately; never assume every 403 is a role denial.
9. Debugging, auditing, and tracing are separated and governed; TRACE is restricted in production.
10. Log storage and pipelines enforce ACLs, retention, encryption, access auditing, secret scanning, and compliance checks.
11. In microservices, trace propagation and trust boundaries are explicitly designed; CIDs are never used for security.
12. Support runbooks are clear: ask customers for **CID and timestamp**, never passwords, access tokens, session cookies, or screenshots containing secrets.

### Self-Check Questions

1. Why should the `Authorization` header never be logged even when the user is authenticated?
2. Can `correlationId` replace a login token or `SecurityContext`?
3. Why can a client-chosen `X-Correlation-ID` break log correlation?
4. In the example, why does a request without credentials still receive `X-Correlation-ID` even though the controller does not run?
5. If logs show CID in the controller yet it is missing from file output, which configuration should you check?
6. Why does an ID placed in MDC disappear when calling `@Async`?
7. If requests A and B run sequentially on the same servlet pool thread, what happens if MDC is not cleared?
8. When a user reports 403, why can you not be sure the cause is `hasRole("ADMIN")`?
9. Why does regex masking `password=...` alone not prove logs are safe?
10. Why does `doesNotContain(secret)` in one test not prove every profile or dependency is safe?
11. If a system enables Micrometer Tracing, how should CID relate to `traceId`/`spanId`?
12. When returning HTTP 500, why is a public error code + CID better than a verbatim stack trace?
13. How do you verify CIDs cannot be spoofed across a gateway?
14. Should you log raw `JSESSIONID` to correlate multiple requests from the same user?
15. Which protections should apply to log aggregators and support staff?

**Answer guide:** (1) it can carry credentials; (2) no, it is only a lookup label; (3) clients can spoof another's ID or perform log injection; (4) the servlet filter runs before security; (5) MDC pattern/appender; (6) MDC is thread-bound and needs propagation; (7) the next request's logs are polluted by the old CID; (8) it could be CSRF, method security, or a custom filter; (9) blocklisting misses unknown field names/encodings; (10) it only verifies the tested path; (11) prefer tracing instrumentation and never use CID for authentication; (12) reduces implementation leakage while preserving investigation; (13) establish trust boundaries, strip forged client headers, verify propagation; (14) no, session IDs are sensitive; (15) ACLs, retention, encryption, and auditing.

## References

- [OWASP — Logging Cheat Sheet: data to exclude from logs, log injection, monitoring](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Spring Boot 3.5 — Logging and MDC configuration in logging.pattern.level](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot 3.5 — Micrometer Tracing and correlation IDs](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Framework 6.2 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Security 6.5 — Servlet Architecture and filter chains](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [W3C — Trace Context (traceparent/tracestate)](https://www.w3.org/TR/trace-context/)