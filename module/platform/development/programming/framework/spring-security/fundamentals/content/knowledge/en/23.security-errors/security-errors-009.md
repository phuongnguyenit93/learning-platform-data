# Consistent Messages, Correlation IDs, and Protecting Internal Details

## 1. Why Must Security Errors Have a Clear Response Contract?

When a request is denied, the browser or client application needs to know **what it can do next**: prompt the user to log in, notify of insufficient permissions, fix input data, or retry later. Operations teams need to know **which request failed** to find logs. Yet a response sent over the Internet must not reveal Java class names, SQL table names, system configuration, detailed authorization rules, account existence, or stack trace contents.

Three goals must go together:

1. **Consistency:** errors of the same kind have a stable HTTP status, public error code, JSON structure, and presentation. Clients rely on `code` and status rather than parsing exception strings.
2. **Traceability:** each request receives a **correlation ID** so users can give it to support and the server can link log records together.
3. **Keeping internal details private:** the response contains only what the caller needs. Technical reasons, stack traces, and diagnostic data belong in protected logs after stripping sensitive data.

For example, never return to users:

```json
{
  "error": "org.postgresql.util.PSQLException",
  "message": "permission denied on relation customer_private",
  "sql": "select * from customer_private where email = ...",
  "stackTrace": ["demo.OrderService.load(OrderService.java:87)"]
}
```

A safer response:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/json
Cache-Control: no-store
X-Correlation-ID: 82b9f5a3-a6aa-4ad5-8baf-61515d9e233a
```

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Unable to process the request at this time.",
  "correlationId": "82b9f5a3-a6aa-4ad5-8baf-61515d9e233a"
}
```

The UUID in the example merely illustrates structure; on real requests the server generates its own value. Users can report that ID to support without sending sensitive error content.

This lesson applies to **Spring Security Servlet, Spring MVC, Java 17+, and Spring Boot 3.x / Spring Security 6.x**. On WebFlux, reactive filters and different context propagation must be used; do not copy `OncePerRequestFilter` or `HttpSecurity` into WebFlux.

## 2. Classifying Errors Before Designing Messages

| Scenario | Usually Suitable HTTP Status | Example Public `code` | User-Facing Message |
| --- | --- | --- | --- |
| Unauthenticated, missing or wrong login credentials | `401 Unauthorized` for APIs requiring authentication | `AUTHENTICATION_REQUIRED` | "Authentication is required to continue." |
| Authenticated but insufficient permissions | `403 Forbidden` | `ACCESS_DENIED` | "You do not have permission to access this resource." |
| Request invalid in syntax/input | `400 Bad Request` | `INVALID_REQUEST` | "The submitted data is invalid." |
| Resource not found, or policy hiding resource existence | `404 Not Found` | `RESOURCE_NOT_FOUND` | "Resource not found." |
| Too many attempts in a short period | `429 Too Many Requests` | `RATE_LIMITED` | "You are sending too many requests." |
| Unexpected server error | `500 Internal Server Error` | `INTERNAL_ERROR` | "Unable to process the request at this time." |
| Dependent service temporarily unavailable | `503 Service Unavailable` | `SERVICE_UNAVAILABLE` | "The service is temporarily unavailable." |

This table is a **recommended policy**, not that every scenario defaults to these statuses. For instance, form-login web apps usually redirect `302` to a login page; JSON APIs may choose `401`. If using HTTP Basic or Bearer, `401` responses must preserve the mechanism-appropriate `WWW-Authenticate` header; never strip challenges just for pretty JSON. On OAuth 2 Resource Server, follow Bearer token rules and avoid crafting non-standard responses.

**Distinguishing three commonly confused cases:**

- **401:** the request has not been authenticated under the mechanism required by the resource. On the client, prompt login or refresh the session/token as designed.
- **403:** the current identity is authenticated, but lacks permission for the operation. Clients should not loop login endlessly to "fix" 403.
- **500:** unexpected server-side error. Clients must never see `NullPointerException`, connection strings, internal hostnames, or SQL, even though internal logs record the event for investigation.

In some cases, an `AccessDeniedException` from an anonymous user is routed by Spring Security to `AuthenticationEntryPoint`, whereas an authenticated user is routed to `AccessDeniedHandler`. Thus **you cannot deduce status from the exception name alone**; you must understand authentication state and where the exception is handled.

For login, forgot-password, and email-lookup errors, avoid responses revealing "this account exists" or "email not in system" if strangers could exploit them to enumerate accounts. Use neutral messages like "If the information matches, we will send instructions" and apply rate limiting.

## 3. Conventions for a Durable Error Response

Choose a unified JSON contract for endpoints belonging to the same client group:

```json
{
  "code": "ACCESS_DENIED",
  "message": "You do not have permission to access this resource.",
  "correlationId": "82b9f5a3-a6aa-4ad5-8baf-61515d9e233a"
}
```

- `code` is a **stable error code** for programmatic handling; never use exception class names as public codes. When display language changes, `code` stays the same.
- `message` is a clear, short sentence guiding the next step and **does not depend on `Exception.getMessage()`**.
- `correlationId` is a random ID carrying no PII, used to match requests and logs. It does not prove access rights, is not a password/token, and must never be used as an authentication source.
- HTTP status is conveyed via the status line; it does not necessarily have to repeat in JSON. If an organization adopts RFC 9457 `ProblemDetail`, keep a consistent format with properties like `type`, `title`, `status`, `detail`, and an extension field `correlationId`; do not mix two formats arbitrarily across endpoints.

For input validation errors, you may include a list of field names and publicly safe validation codes, such as `{"field":"quantity","code":"MUST_BE_POSITIVE"}`. **Never echo back the value the user just entered** if it could contain passwords, access tokens, private emails, or sensitive data. Establish clear rules for which fields may appear.

Never wrap all errors in `200 OK` around `{"success": false}`. Doing so breaks HTTP clients, proxies, caches, metrics, retries, and monitoring alerts.

## 4. Where Do Errors Travel in a Spring Security Servlet App?

Typical flow:

```text
Request
  ↓
CorrelationIdFilter (attaches ID, response header, MDC for logs)
  ↓
Spring Security FilterChain
  ├─ authentication failed / unauthenticated → AuthenticationEntryPoint
  ├─ authenticated but insufficient permissions → AccessDeniedHandler
  ├─ some protective filters (e.g., CSRF) have their own error path
  ↓
DispatcherServlet / Controller
  ├─ exception in Spring MVC → @RestControllerAdvice / MVC error handling
  └─ successful processing → normal response
  ↓
Response with X-Correlation-ID, containing no internal details
```

`@RestControllerAdvice` is typically **not** the sole place to standardize Spring Security errors: requests may already be blocked in filters before reaching a controller. Conversely, configuring `exceptionHandling(...)` in Spring Security alone does not standardize JSON parsing errors, validation errors, or business exceptions inside MVC.

Sensible division of responsibilities:

- `AuthenticationEntryPoint` builds responses for authentication-required errors where Spring Security invokes the entry point.
- `AccessDeniedHandler` builds responses when access is denied in the corresponding processing path.
- MVC exception handlers handle application errors, validation, and unexpected controller errors.
- Other interception points such as custom filters, CSRF, OAuth 2, servlet container, and error dispatches must have dedicated tests, as not every error passes through the three points above.
- A shared response writer keeps paths consistent in JSON structure, headers, and public messages.

## 5. Working Example with Java 17 and Spring Boot 3.x

The small example below builds an API using HTTP Basic for easy testing. It covers three cases: unauthenticated returns 401, authenticated account missing role returns 403, controller error returns 500. Every error response shares the same JSON structure and correlation ID. **Demo accounts are for development machines only; HTTP Basic in real environments must use HTTPS and appropriate credential-management policies.**

The Spring Boot project needs `spring-boot-starter-web` and `spring-boot-starter-security`; tests add `spring-boot-starter-test` and `spring-security-test`. With Gradle Groovy DSL, dependencies in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

All Java classes belong to package `demo.safeerror`. This is code for a Spring Boot application (run via build tools and dependency classpath), **not** standalone classes compiled with bare `javac` without libraries.

### 5.1. Startup Application

File `src/main/java/demo/safeerror/SafeApiErrorApplication.java`:

```java
package demo.safeerror;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeApiErrorApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeApiErrorApplication.class, args);
    }
}
```

### 5.2. Assigning a Correlation ID at Request Start

File `src/main/java/demo/safeerror/CorrelationIdFilter.java`:

```java
package demo.safeerror;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class CorrelationIdFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Correlation-ID";
    private static final String ATTRIBUTE =
            CorrelationIdFilter.class.getName() + ".id";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {
        // Generate a new ID at the trust boundary, avoiding client spoofing of another request's ID.
        String id = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, id);
        response.setHeader(HEADER, id);

        // MDC ensures every log on the same thread carries the correlation ID.
        try (MDC.MDCCloseable ignored = MDC.putCloseable("correlationId", id)) {
            chain.doFilter(request, response);
        }
    }

    public static String id(HttpServletRequest request) {
        return (String) request.getAttribute(ATTRIBUTE);
    }
}
```

Explanation:

- The filter runs before security processing so even 401/403 responses from Spring Security get `X-Correlation-ID`. In Spring Boot, `@Order` sets the order of auto-registered Servlet filters.
- The ID is generated at the application boundary, without trusting arbitrary `X-Correlation-ID` strings supplied by clients. In architectures with a trusted API gateway, a different ID-acceptance/propagation rule can be built with checks on length, characters, origin, and system-wide conventions.
- `request.setAttribute(...)` lets entry points, handlers, and controllers share the same ID; the response header lets clients inspect/record the ID.
- `MDC.putCloseable(...)` cleans up the value after the request, preventing logs from another request from picking up the wrong ID when threads are reused. In async processing or across services, propagate context via appropriate mechanisms; ThreadLocal-based MDC does not automatically propagate across all threads.

If a frontend runs on a different origin and needs to read this header in JavaScript, CORS must expose `X-Correlation-ID` via `Access-Control-Expose-Headers` for allowed origins. Doing so does not by itself open CORS or API access permissions.

### 5.3. A Shared Error Writer

File `src/main/java/demo/safeerror/ApiErrorWriter.java`:

```java
package demo.safeerror;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

@Component
public class ApiErrorWriter {
    private final ObjectMapper mapper;

    public ApiErrorWriter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    public void write(
            HttpServletRequest request,
            HttpServletResponse response,
            int status,
            String code,
            String publicMessage
    ) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        String id = CorrelationIdFilter.id(request);
        mapper.writeValue(
                response.getWriter(),
                new PublicError(code, publicMessage, id)
        );
    }

    public record PublicError(
            String code,
            String message,
            String correlationId
    ) {}
}
```

Never pass `exception.getMessage()` verbatim into `publicMessage`. The writer only accepts messages chosen by policy. The Spring Boot-configured `ObjectMapper` ensures JSON is properly escaped; never hand-concatenate JSON strings from user input.

Note: this example assumes the response has not yet been committed. If an exception occurs **after** the server has already sent headers or part of the body, switching status/body to new JSON cannot be guaranteed; log, monitor, and handle at the corresponding streaming/async boundary.

### 5.4. Producing Consistent 401 and 403 in Spring Security

File `src/main/java/demo/safeerror/SecurityConfig.java`:

```java
package demo.safeerror;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ApiErrorWriter errors
    ) throws Exception {
        AuthenticationEntryPoint unauthorized = (request, response, ex) -> {
            // For HTTP Basic, preserve the challenge required by the client.
            response.setHeader(
                    HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo-api\""
            );
            errors.write(
                    request, response, 401,
                    "AUTHENTICATION_REQUIRED",
                    "Authentication is required to continue."
            );
        };

        AccessDeniedHandler forbidden = (request, response, ex) ->
                errors.write(
                        request, response, 403,
                        "ACCESS_DENIED",
                        "You do not have permission to access this resource."
                );

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/fail").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(basic -> basic.authenticationEntryPoint(unauthorized))
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(unauthorized)
                .accessDeniedHandler(forbidden)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo-reader")
                .password(encoder.encode("demo-only-password"))
                .roles("READER")
                .build()
        );
    }
}
```

This configuration serves a **JSON API**. The `READER` role does not include `ADMIN`, so `GET /api/admin` returns 403 once authenticated. Unauthenticated returns 401. The `/api/fail` path is open publicly in the example solely to reproduce a 500 error without authenticating.

The configuration above **does not disable CSRF**. The example uses `GET` only to focus on the error contract. If adding `POST` with cookies or browser HTTP Basic, CSRF protection must still be considered; responses from `CsrfFilter` may take a separate handling path, so test and integrate the corresponding error formatting. Do not assume all filter errors automatically flow through `exceptionHandling(...).accessDeniedHandler(...)`.

When replacing HTTP Basic with Bearer/JWT, use OAuth2 Resource Server-compatible entry points and access-denied handlers; ensure `WWW-Authenticate: Bearer ...` follows specification. Do not keep the `Basic` challenge from the demo.

### 5.5. Controller and Controlled 500 Response

File `src/main/java/demo/safeerror/DemoController.java`:

```java
package demo.safeerror;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {
    @GetMapping("/private")
    public String privateResource() {
        return "private";
    }

    @GetMapping("/admin")
    public String adminResource() {
        return "admin";
    }

    @GetMapping("/fail")
    public String failure() {
        // Used solely to demonstrate a technical error that must not be returned to clients.
        throw new IllegalStateException("internal-only: db-node=cluster-a");
    }
}
```

File `src/main/java/demo/safeerror/ApiExceptionAdvice.java`:

```java
package demo.safeerror;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.io.IOException;

@RestControllerAdvice
public class ApiExceptionAdvice {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionAdvice.class);

    private final ApiErrorWriter errors;

    public ApiExceptionAdvice(ApiErrorWriter errors) {
        this.errors = errors;
    }

    @ExceptionHandler(IllegalStateException.class)
    public void handleUnexpected(
            IllegalStateException ex,
            HttpServletRequest request,
            HttpServletResponse response
    ) throws IOException {
        String id = CorrelationIdFilter.id(request);
        log.error("Unexpected application error; correlationId={}", id, ex);

        errors.write(
                request, response, 500,
                "INTERNAL_ERROR",
                "Unable to process the request at this time."
        );
    }
}
```

The `@ExceptionHandler(IllegalStateException.class)` snippet handles **only one exception type created for testing**. It does not claim to have standardized all MVC errors. Real applications need policies for validation 400, missing resource 404, unsupported method 405, data conversion errors, and unexpected errors; `ResponseEntityExceptionHandler` / `ProblemDetail` and a shared error converter can be used.

**Never indiscriminately catch every `Exception` and return 500**: doing so easily swallows `AuthenticationException`/`AccessDeniedException` thrown in MVC or turns valid 400/404 errors into 500. Catch only deliberately scoped types; if using a global handler, classify and rethrow security exceptions along Spring Security's proper handling path.

In the example, the stack trace goes into internal logs while the outbound response contains only a neutral error code. Logs must have appropriate access controls and retention; before logging exceptions or requests, avoid logging login credentials, `Authorization`, `Cookie`, tokens, secrets, payment data, or private info. An exception may contain sensitive data right inside its message, so logging entire exceptions must also be evaluated under the system's logging policy.

## 6. Automated Testing: 401, 403, 500, and Correlation ID

File `src/test/java/demo/safeerror/ApiSecurityErrorTests.java`:

```java
package demo.safeerror;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiSecurityErrorTests {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void missingAuthenticationReturnsSafe401() throws Exception {
        MvcResult result = mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate", "Basic realm=\"demo-api\""
            ))
            .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"))
            .andExpect(jsonPath("$.message")
                .value("Authentication is required to continue."))
            .andReturn();

        assertCorrelationMatches(result);
    }

    @Test
    void wrongPasswordDoesNotRevealWhyAuthenticationFailed()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/api/private").with(httpBasic("demo-reader", "wrong"))
            )
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("AUTHENTICATION_REQUIRED"))
            .andExpect(jsonPath("$.message")
                .value("Authentication is required to continue."))
            .andReturn();

        assertCorrelationMatches(result);
        assertFalse(result.getResponse().getContentAsString()
                .contains("BadCredentialsException"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleGets403() throws Exception {
        MvcResult result = mvc.perform(
                get("/api/admin").with(user("demo-reader").roles("READER"))
            )
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.message")
                .value("You do not have permission to access this resource."))
            .andReturn();

        assertCorrelationMatches(result);
    }

    @Test
    void internalExceptionIsMaskedFromClient() throws Exception {
        MvcResult result = mvc.perform(
                get("/api/fail")
                    .header(CorrelationIdFilter.HEADER, "user-supplied-id")
            )
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
            .andExpect(jsonPath("$.message")
                .value("Unable to process the request at this time."))
            .andExpect(header().string("Cache-Control", "no-store"))
            .andReturn();

        assertCorrelationMatches(result);
        String body = result.getResponse().getContentAsString();
        assertFalse(body.contains("internal-only"));
        assertFalse(body.contains("cluster-a"));
        assertFalse(body.contains("IllegalStateException"));
        assertNotEquals(
                "user-supplied-id",
                result.getResponse().getHeader(CorrelationIdFilter.HEADER)
        );
    }

    @Test
    void validCredentialsStillAccessNormalResource() throws Exception {
        mvc.perform(
                get("/api/private")
                    .with(httpBasic("demo-reader", "demo-only-password"))
            )
            .andExpect(status().isOk())
            .andExpect(content().string("private"))
            .andExpect(header().exists(CorrelationIdFilter.HEADER));
    }

    private void assertCorrelationMatches(MvcResult result)
            throws IOException {
        String id = result.getResponse()
                .getHeader(CorrelationIdFilter.HEADER);
        assertNotNull(id);
        assertTrue(id.matches("[0-9a-f-]{36}"));

        String inBody = mapper.readTree(
                result.getResponse().getContentAsString()
        ).path("correlationId").asText();

        assertEquals(id, inBody);
    }
}
```

Run from the root of the Boot project with Gradle wrapper:

```bash
./gradlew test --tests demo.safeerror.ApiSecurityErrorTests
```

If the classes are placed in the right package/paths and dependencies are correct, the five tests verify the following behaviors:

1. **401 missing authentication:** returns status 401, neutral error code, HTTP Basic challenge, and matching correlation ID between header and body.
2. **401 wrong password:** same public message as when no credentials were sent; does not leak exception class name.
3. **403 insufficient permissions:** for an authenticated user lacking `ADMIN`, returns 403 (not confused with 401).
4. **500 internal error:** no exception name or internal details appear in the body; ID is server-generated and does not adopt the client's header ID verbatim.
5. **Success path:** valid accounts can still access; changing error reporting does not break permitted branches.

These tests verify the example's JSON API version specifically; **they do not automatically prove every error path in a real system is unified**. When the application uses CSRF, form login, Bearer tokens, OAuth2, custom filter exceptions, streaming, async, or error dispatches, add corresponding test cases.

For web applications, also test via a real browser: what message does the screen show, are technical responses accidentally displayed in the console/UI, is the login redirect flow reasonable, and can users clearly see the correlation ID to provide when reporting an error?

## 7. Analyzing Correlation IDs and Logging Properly

Suppose three requests arrive close together. Each receives its own ID:

```text
Request A -> X-Correlation-ID: 1b22... -> 401
Request B -> X-Correlation-ID: 94ac... -> 403
Request C -> X-Correlation-ID: 6f41... -> 500
```

In Request C's logs, you can configure a pattern to display the MDC `correlationId` value. Example Spring Boot snippet in `application.yml`:

```yaml
logging:
  pattern:
    level: "%5p [cid:%X{correlationId:-}]"
```

When a request fails, support staff only need to look up `correlationId`, timestamp, and deployment environment. The ID must be indexed or searchable in the logging system. If a request crosses multiple services, a gateway-generated ID is only useful when propagation rules are consistently implemented; in systems using OpenTelemetry, use **trace ID**/W3C Trace Context as the tracing foundation, and clearly define the relationship between public `correlationId` and internal `traceId`.

**Limitations to remember:**

- An ID is not proof of identity or request ownership. Do not hand logs to just anyone simply because they have an ID.
- Never embed emails, phone numbers, access tokens, IP addresses, or account IDs directly in a correlation ID. Random IDs are generally safer.
- Never accept raw IDs from the Internet without trust rules; prevent spoofing, abnormal lengths, newline characters (log injection), and collisions across requests.
- When threads switch, ThreadLocal-based `MDC` does not automatically carry over to `@Async`, `CompletableFuture`, or message consumers; use proper context-propagation mechanisms.
- A request can fail before reaching the application's filters (e.g., rejected immediately by a proxy/ingress). In that case, the gateway needs its own ID and logging strategy; IDs generated in a Servlet filter cannot cover choke points sitting outside it.
- Internal logs can still leak data if access controls, retention, redaction, or collection pipelines are insecure. "Hiding from the response" is only one layer of protection.

## 8. Rules Against Leaking Security Details

**Content that generally should not be returned in public responses:**

| Information Type | Examples to Exclude | Alternative |
| --- | --- | --- |
| Stack trace / exception class | `SQLException`, `ClassNotFoundException`, Java paths and line numbers | `INTERNAL_ERROR` + neutral message |
| Infrastructure | DB hostnames, internal network addresses, buckets, SQL tables, queries | Correlation ID to search internal logs |
| Login info | Whether an account name exists, exact reason for wrong password | Neutral authentication message |
| Authorization rules | Internal role names, secret permission names, ACL details | `ACCESS_DENIED` without listing policies |
| Tokens/secrets | `Authorization`, `Cookie`, API keys, full JWTs, session IDs | Omit from responses and scrub from logs |
| User data | Emails, profiles, accounts, other users' records | Return only permitted, minimal info |
| Debug/stack in HTML | Whitelabel/error HTML pages containing heavy technical details | Controlled error page or standardized JSON API |

Not every detail must be hidden: a 400 error can state that `quantity` must be greater than 0, because that is actionable info. The main question is whether the caller **is already authorized to know that detail**, and whether returning it enables data probing or exposes security policies.

Commonly overlooked mechanisms:

- **404/403 and resource existence inference:** for paths like `/users/{id}/...`, a 403 can tell strangers an account or document exists. You may return 404 per security policy, but be consistent so you do not create an inference channel via status, content, size, or response timing.
- **Login and account recovery:** avoid error codes distinguishing whether an email exists or not for unverified callers; combine with rate limiting and monitoring.
- **Framework debug responses:** never enable displaying exception messages/stack traces in public errors in production. Audit `/error` pages, Actuator endpoints, exception serialization settings, and default error messages.
- **Redirects containing sensitive data:** never put access tokens, session IDs, or full technical errors in error page query strings; URLs enter browser history, Referer headers, and logs.
- **Logging full requests:** avoid middleware that logs all headers/bodies by default, especially Authorization, cookies, passwords, and personal data. Redacting at the source is better than filtering only on dashboards.
- **Response length and structure:** ensure users always receive appropriate error codes, no stack traces, standard headers, and a correlation ID; exact internal details belong in a secure tracing system.

## 9. Testing Checklist for a Real-World API

| Test Case | Acceptance Criteria |
| --- | --- |
| Unauthenticated call to protected resource | Correct 401 or redirect policy; JSON APIs have public `code`; valid challenge if using Basic/Bearer. |
| Authenticated but insufficient permissions | 403 or 404 per policy, no leaked internal role/permission names. |
| Wrong credentials / non-existent user | No message or error code aiding account enumeration; appropriate rate limit. |
| Business / validation error | Proper status; exposes only non-sensitive fields and rules; never echoes secret data. |
| Controller error | Clean 500 response; technical details reside in protected logs. |
| Spring Security filter error | Consistent structure/message; do not assume it passes through `@RestControllerAdvice`. |
| CSRF and OAuth2 auth errors | Verify status, challenge, and format per filter/mechanism; do not break protocol standards. |
| Correlation ID | Header/body carry matching ID; ID is valid, random, PII-free; logs are searchable by ID. |
| Client-supplied ID header | Strangers cannot hijack another request's ID or inject characters into logs. |
| Successful request | Normal response logic unaltered; still includes correlation ID when required by system. |
| Streaming, async, non-MVC error handling | Trace ID and error policy tested at real execution boundaries. |
| Production | No debug stacks or internal error pages; logs, metrics, and alerts contain no secrets. |

To evaluate a change, run both **positive tests** (authorized users still succeed) and **negative tests** (unauthorized callers gain no extra details). You can combine MockMvc, integration tests with a real proxy, inspecting responses in DevTools, and searching logs by correlation ID.

## 10. Common Implementation Mistakes

1. **Returning `ex.getMessage()` to clients.** Messages can contain passwords, table names, query data, or internal paths. Select public messages via defined error codes.
2. **Using HTTP 200 for all errors.** Clients and monitoring systems lose the ability to classify errors accurately.
3. **Using status 403 for all security errors.** Loses the 401/403 distinction; clients do not know whether authentication is required.
4. **Using only `@ControllerAdvice`.** Errors in Spring Security filters may go unstandardized.
5. **Using only `exceptionHandling(...)`.** MVC/validation errors may have a different format.
6. **Customizing responses while removing `WWW-Authenticate`.** Breaks HTTP Basic/Bearer contracts.
7. **Using arbitrary client-sent correlation IDs and writing them straight to logs.** Risks spoofing, ID collisions, or log injection.
8. **Failing to clear MDC when a thread finishes a request.** Another request's logs can inherit the old ID by mistake.
9. **Having a correlation ID that cannot be searched in logs.** The ID becomes purely decorative; configure log/search pipelines and context propagation.
10. **Hiding details from responses while dumping all secrets into logs.** Data protection applies to logs, monitoring, and traces too.
11. **Catching all exceptions and turning them into 500.** Can disable 400/404 handling and MVC-side security rules.
12. **Assuming MockMvc covers proxies, browsers, async, and all filters.** Test at the corresponding real boundaries.

A design meets requirements when users get **short, actionable messages**, clients get **stable statuses/error codes**, operations can find **the relevant request**, and attackers **gain no extra internal information** from the same error.

## References

- Spring Security — [Servlet Architecture / Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html).
- Spring Security — [Authentication Architecture and AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html).
- Spring Security — [Authorize HTTP Requests and AccessDeniedException](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/).
- Spring Framework — [Error Responses, ProblemDetail, and RFC 9457](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html).
- IETF — [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457).