# Handling Method Security Errors Through the Web Layer While Preserving Status Codes

> **Scope:** Spring Security for **Servlet + Spring MVC/REST** applications, especially when `@PreAuthorize`, `@PostAuthorize`, or business code throws authorization exceptions from a service. The goal is to preserve proper **HTTP status** and authentication semantics while returning a consistent error body if the API requires one. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5, and MockMvc; the principles apply to newer versions upon checking the corresponding APIs.

## 1. Real-World Problem and Target Outcome

Suppose a document-reading API has a protected service method:

```java
@PreAuthorize("hasAuthority('document:read')")
public Document find(long id) { ... }
```

If an HTTP request calls this method without sufficient permission, the method-security interceptor denies it before the method executes. A common mistake is routing every exception from controllers/services into a catch-all error handler and always returning `200 OK`, `400 Bad Request`, or `500 Internal Server Error`, even when the true cause is missing login/permissions. The result breaks the HTTP contract, misleads clients (e.g., showing "system broken" instead of prompting for login), masks authorization bugs, and makes security tests unreliable.

**Status contract to test:**

| Scenario | Appropriate HTTP Status | Responsible Component |
| --- | --- | --- |
| Unauthenticated, accessing an operation requiring permissions | Usually **401 Unauthorized** in REST APIs | `AuthenticationEntryPoint` |
| Invalid or expired Basic/Bearer credentials | **401 Unauthorized** (with scheme-appropriate challenge/header) | Authentication filter + `AuthenticationEntryPoint` |
| Authenticated, but missing authority, scope, or resource ownership | **403 Forbidden** | `AccessDeniedHandler` or explicitly defined error policy |
| Has permission to view, but resource does not exist | **404 Not Found** | Business exception handler |
| Invalid input | **400 Bad Request** or **422 Unprocessable Content** per API contract | Validation + MVC exception handling |
| Unexpected non-security error | **5xx**, usually **500** | Error handler / monitoring infrastructure |
| Valid operation | Expected success code (`200`, `201`, `204`, …) | Controller |

**Note on 401 and 403:** "401" in HTTP is formally named *Unauthorized*, but its semantics primarily mean **missing or invalid authentication**; "403" means **not permitted to perform the operation**. In applications using form login, unauthenticated users may be redirected `302` to the login page: that is the behavior of a redirect-based `AuthenticationEntryPoint`. The example below designs a **REST API using HTTP Basic**, so it selects explicit `401`/`403` responses; do not apply one status rule universally to every UI style.

## 2. How Do Exceptions from Method Security Travel Through the Web Layer?

### 2.1. Standard Path

```text
HTTP request
  │
  ▼
Spring Security FilterChainProxy
  ├─ authentication filter (HTTP Basic/Bearer/session...)
  ├─ ExceptionTranslationFilter
  └─ AuthorizationFilter (HTTP URL authorization)
       │
       ▼
  DispatcherServlet (Spring MVC)
       │
       ▼
  @RestController
       │ calls another bean through a Spring AOP proxy
       ▼
  @Service + @PreAuthorize / @PostAuthorize
       │
       ├─ allowed ──> logic / success response
       │
       └─ denied ──> AccessDeniedException
                          │
                          ├─ if MVC does not swallow/handle the exception
                          │      ▼
                          │  ExceptionTranslationFilter
                          │      ├─ anonymous/unauthenticated ──> AuthenticationEntryPoint
                          │      └─ authenticated ──────────────> AccessDeniedHandler
                          │
                          └─ if @ControllerAdvice catches and writes a response
                                 └─ the filter no longer sees that exception
```

`@EnableMethodSecurity` activates method authorization; Spring Boot Starter Security does not automatically enable `@PreAuthorize` merely by adding the dependency. With `@PreAuthorize`, Spring AOP evaluates permissions **before** invoking the method; when denied, Spring Security throws `AccessDeniedException` (modern versions may use `AuthorizationDeniedException`, a subclass of `AccessDeniedException`). With `@PostAuthorize`, the check runs **after** the method executes, so side effects inside the method may already have occurred even though the final HTTP outcome is 403.

`ExceptionTranslationFilter` only translates **`AuthenticationException` or `AccessDeniedException`** occurring within the filter chain scope into appropriate HTTP behavior. It does not perform authorization itself. For `AuthenticationException`, it calls `AuthenticationEntryPoint`; for `AccessDeniedException`, it uses `AuthenticationTrustResolver` to distinguish insufficiently trusted anonymous/remember-me identities from properly authenticated users, then calls either the entry point or the access-denied handler.

This principle applies to HTTP requests passing through the filter chain. A direct service call from a scheduler, message listener, CLI, unit test, or background task has no HTTP layer to automatically turn exceptions into `401`/`403`; the adapter calling the service must decide how to represent errors for its protocol.

### 2.2. Why Does `@ControllerAdvice` Easily Break Status Codes?

Spring MVC routes exceptions through the `HandlerExceptionResolver` chain. An `@ExceptionHandler` on a controller or `@ControllerAdvice` can **resolve the exception before it escapes back to the filter chain**. Once a handler has written a response, `ExceptionTranslationFilter` has nothing left to handle.

**Incorrect** example:

```java
@RestControllerAdvice
class DangerousAdvice {

    @ExceptionHandler(Exception.class)
    ResponseEntity<String> everyError(Exception ex) {
        return ResponseEntity.ok("Something went wrong");
    }
}
```

If the handler above catches `AccessDeniedException`, unauthorized users may receive **200 OK**. Changing `ok` to `internalServerError` is also wrong: authorization errors would turn into **500**. Another example:

```java
@ExceptionHandler(AccessDeniedException.class)
ResponseEntity<String> denied(AccessDeniedException ex) {
    return ResponseEntity.status(403).body("Forbidden");
}
```

This handler can cause **anonymous callers to receive 403 instead of 401**, because it bypasses `AuthenticationEntryPoint` branching logic. It can also omit the `WWW-Authenticate` challenge, API/browser separation, or specific bearer token handling.

**Safe rule for Web MVC:** let `AccessDeniedException`/`AuthenticationException` reach the default security handling or security handlers configured in `HttpSecurity.exceptionHandling(...)`; use `@RestControllerAdvice` for **narrowly defined business errors** like not-found/validation. When you must handle security at the MVC layer due to specific architectural requirements, explicitly reproduce the anonymous/authenticated conditions, scheme/challenge, and status, and test both 401 and 403.

## 3. Runnable Example: REST API Authorized at the Service Layer

The example has 3 identities:

- `reader` has authority `document:read`, allowed to read documents.
- `viewer` can log in but only has `document:list`, not allowed to read.
- Anonymous has no credentials.

To **genuinely test method security**, the URL layer permits `GET /api/documents/**` through; specific permissions are enforced by `@PreAuthorize` on the service. Undeclared routes are denied at the HTTP layer. This setup serves illustration: real projects can add HTTP policies independently alongside method security.

Dependencies in Maven (`pom.xml`) with versions managed by Spring Boot:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The dependencies snippet above is meant to be inserted into a **Spring Boot Maven project that already has a suitable parent/BOM and plugins**, not a complete `pom.xml`. All Java classes below are in package `example.methodsecurity`. Each block lists its corresponding filename.

### 3.1. Starting the Application

**`src/main/java/example/methodsecurity/DemoApplication.java`**

```java
package example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 3.2. Configuring Spring Security, 401/403 Branching, and Error Bodies

**`src/main/java/example/methodsecurity/ApiSecurityConfig.java`**

```java
package example.methodsecurity;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint unauthenticated = (request, response, cause) -> {
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"documents\"");
            sendProblem(response, 401, "Unauthorized");
        };

        AccessDeniedHandler forbidden = (request, response, cause) ->
                sendProblem(response, 403, "Forbidden");

        return http
                .authorizeHttpRequests(auth -> auth
                        // Avoid errors when the container dispatches to the error page.
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        // Allow reaching the controller; @PreAuthorize must still decide.
                        .requestMatchers(HttpMethod.GET, "/api/documents/**").permitAll()
                        .anyRequest().denyAll())
                // Wrong credentials also go through the 401 entry point with Basic challenge.
                .httpBasic(basic -> basic.authenticationEntryPoint(unauthenticated))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(unauthenticated)
                        .accessDeniedHandler(forbidden))
                .build();
    }

    private static void sendProblem(
            HttpServletResponse response, int status, String title) throws IOException {
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);

        // title is a server-chosen constant; do not insert the exception message into JSON.
        response.getWriter().write(
                "{\"type\":\"about:blank\",\"title\":\"" + title
                        + "\",\"status\":" + status + "}");
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader-pass")
                        .authorities("document:read")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}viewer-pass")
                        .authorities("document:list")
                        .build());
    }
}
```

**Design explanation:**

1. `@EnableMethodSecurity` enables AOP checks for `@PreAuthorize`. The service must be called via a Spring-managed proxy; `this.someSecuredMethod()` calls inside the bean itself can bypass the proxy interceptor.
2. `requestMatchers(GET, "/api/documents/**").permitAll()` only lets requests pass **HTTP URL authorization**, and does not grant `document:read`. Readers are not permitted if `@PreAuthorize` denies them.
3. `AuthenticationEntryPoint` returns `401` with `WWW-Authenticate: Basic realm="documents"`. This preserves the scheme-compliant Basic challenge. If using OAuth2 Resource Server/JWT, use the corresponding entry point to preserve Bearer headers and error descriptions; **do not** replace it with Basic.
4. `AccessDeniedHandler` returns `403` when authenticated but lacking permission. The `application/problem+json` body has `status` matching the HTTP status. The body contains no stack trace, username, or sensitive technical message.
5. These error handlers are configured in both `HttpSecurity.exceptionHandling` and the HTTP Basic branch. Thus errors originating from authentication or method authorization both route to the consistent handler pair.
6. `DispatcherType.ERROR` is permitted so downstream error handling is not accidentally blocked by `anyRequest().denyAll()`. In projects with multiple `SecurityFilterChain` beans, ensure the corresponding policy applies to the chain actually matching the API.
7. `{noop}` with passwords in source code is **only for local/test examples**. In real systems, use a strong password encoder or identity provider, keep secrets out of source code, enforce HTTPS, and manage sessions/tokens properly.
8. CSRF is not disabled wholesale in the example. The illustrated requests are GET only, so no CSRF token is needed; APIs with state-changing operations must design CSRF according to their authentication method.

If custom error JSON is unnecessary, you can omit the `unauthenticated`/`forbidden` lambdas and just enable `httpBasic(Customizer.withDefaults())`: Spring Security still chooses 401 or 403 by default. Status accuracy **does not depend** on writing a `@ControllerAdvice` for `AccessDeniedException`.

### 3.3. Secured Service, Controller Simply Delegates to Service

**`src/main/java/example/methodsecurity/DocumentService.java`**

```java
package example.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    public record Document(long id, String title) {}

    @PreAuthorize("hasAuthority('document:read')")
    public Document find(long id) {
        if (id == 404L) {
            throw new DocumentNotFoundException(id);
        }
        return new Document(id, "Guide " + id);
    }
}
```

Here `404L` is a fixture simulating a non-existent document to help tests distinguish **business 404** from **authorization 403**; a real application queries the database and throws not-found when no record exists.

**`src/main/java/example/methodsecurity/DocumentNotFoundException.java`**

```java
package example.methodsecurity;

public class DocumentNotFoundException extends RuntimeException {
    public DocumentNotFoundException(long id) {
        super("Document " + id + " does not exist");
    }
}
```

**`src/main/java/example/methodsecurity/DocumentController.java`**

```java
package example.methodsecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentService.Document get(@PathVariable long id) {
        return service.find(id); // Called through Spring bean/proxy.
    }
}
```

No `try/catch(AccessDeniedException)` is needed in the controller. If the service denies access, the exception propagates through MVC and Spring Security handles it according to the scheme. If the service succeeds, the controller returns the document JSON with HTTP `200`.

### 3.4. Handling Only Business Errors in MVC

**`src/main/java/example/methodsecurity/DomainErrorAdvice.java`**

```java
package example.methodsecurity;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DomainErrorAdvice {

    @ExceptionHandler(DocumentNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(DocumentNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Document not found");
        problem.setDetail("The requested document does not exist");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
```

This advice **does not accept** `AccessDeniedException`, `AuthenticationException`, or `Exception.class`; therefore, it never turns permission errors into 404/500/200. In real APIs, narrow handlers can be added for validation (`MethodArgumentNotValidException`, etc.) with appropriate statuses. Keeping the exception scope specific helps surface unexpected errors as 5xx rather than silently reporting success.

## 4. End-to-End Testing in Spring MVC with Full Security Filter Chain

Unit-testing a method with `@PreAuthorize` alone is not enough: you must test the **actual HTTP status** after MVC, `SecurityFilterChain`, and handlers process it. With Spring Boot 3.x, you can use `@SpringBootTest` + `@AutoConfigureMockMvc`; `spring-security-test` must be on the test classpath.

**`src/test/java/example/methodsecurity/MethodSecurityHttpStatusTest.java`**

```java
package example.methodsecurity;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityHttpStatusTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private DocumentService documents;

    @Test
    void anonymousRequestDeniedByMethodSecurityReturns401() throws Exception {
        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate", "Basic realm=\"documents\""))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void wrongBasicCredentialsReturn401() throws Exception {
        mvc.perform(get("/api/documents/42")
                        .with(httpBasic("reader", "wrong-pass")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate", "Basic realm=\"documents\""))
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void authenticatedButMissingAuthorityReturns403() throws Exception {
        mvc.perform(get("/api/documents/42")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status").value(403))
                .andExpect(jsonPath("$.title").value("Forbidden"));
    }

    @Test
    void authorizedRequestReturns200AndDocument() throws Exception {
        mvc.perform(get("/api/documents/42")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Guide 42"));
    }

    @Test
    void authorizedButMissingDocumentRetains404() throws Exception {
        mvc.perform(get("/api/documents/404")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.title").value("Document not found"));
    }

    @Test
    @WithMockUser(username = "viewer", authorities = "document:list")
    void directServiceCallThrowsSecurityExceptionNotHttpResponse() {
        assertThrows(AccessDeniedException.class, () -> documents.find(42L));
    }
}
```

The test cases prove different behaviors:

- No credentials on a `permitAll` URL: the request **reaches method security**, is blocked at `@PreAuthorize`, and returns `401`. This distinguishes method security from cases where the URL filter rejects up front.
- Wrong credentials: fails at the HTTP Basic authentication layer, also `401`, without needing to call the method.
- Valid credentials but missing authority: passes HTTP, is denied by the service, and receives `403`; the body also has `status=403`.
- Correct authority: the method runs and returns `200` with data.
- Has permission but missing document: passes `@PreAuthorize`, then throws the business exception, and MVC returns `404`.
- Direct service call under `@WithMockUser` missing authority: receives a Java `AccessDeniedException` instead of automatically producing an HTTP response.

**Run tests** in the Spring Boot Maven project containing the configuration and files above:

```bash
./mvnw test -Dtest=MethodSecurityHttpStatusTest
```

Or:

```bash
mvn test -Dtest=MethodSecurityHttpStatusTest
```

If using Gradle, run the corresponding test class via the Gradle test task. **Expectation**: all 6 test methods pass; check the actual runner log rather than concluding from illustrative stdout. If using Spring Boot 4 or later, the locations of some test annotations may change; confirm packages against your project version and update imports while keeping the verification logic intact.

## 5. Separating Layers to Pinpoint Root Causes When Statuses Are Wrong

### 5.1. Case A: Anonymous Receives 403 Instead of 401

Common causes:

1. A `@RestControllerAdvice` with `@ExceptionHandler(AccessDeniedException.class)` directly returned `403` before the filter; the anonymous case no longer goes through the entry point.
2. The API is configured with `Http403ForbiddenEntryPoint` from another authentication model (this entry point intentionally returns 403), or a different `SecurityFilterChain` matched the request.
3. The test is annotated with `@WithMockUser`, so the request **is treated as authenticated** even if the test author thought it was anonymous.
4. The HTTP client automatically sends an old cookie/token; browser or test fixture leaks security context.

How to diagnose: reproduce with a request **without** Authorization/Cookie, check which handler runs (`AuthenticationEntryPoint` or `AccessDeniedHandler`), inspect `SecurityContextHolder`, and check which chain matched the route. Ensure tests include a positive control with valid credentials.

### 5.2. Case B: Insufficient Permissions Yet Returns 500

Check in order:

1. Is `@EnableMethodSecurity` enabled? If not, `@PreAuthorize` is ignored, usually causing a data leak/`200` rather than `403`.
2. Is the method called **through a Spring proxy**? Self-invocation, instantiating the service with `new`, or not being a Spring bean can bypass the interceptor.
3. Is the exception truly `AccessDeniedException` (or a subclass)? Throwing `IllegalStateException("Forbidden")` is just a regular runtime error, defaulting to `500`.
4. Did `@ExceptionHandler(Exception.class)` catch the security exception and turn it into 500?
5. Is there an unusual filter/async boundary preventing the exception from reaching `ExceptionTranslationFilter`?
6. Was the response already committed (streaming, writing the body too early) before denial? At that point the server cannot safely alter headers/status.

Place controlled breakpoints/logs in `AuthorizationManagerBeforeMethodInterceptor`, `ExceptionHandlerExceptionResolver`, `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, and `AccessDeniedHandler`. Never log credentials/tokens. In Spring Security, you can temporarily enable DEBUG for security packages while debugging, then turn it off in production.

### 5.3. Case C: Permission Errors Turned into 200

Typically looks like:

```java
try {
    return ResponseEntity.ok(service.find(id));
} catch (Exception ex) {
    return ResponseEntity.ok(Map.of("success", false, "message", "Error"));
}
```

This is an **anti-pattern**: `@PreAuthorize` denies access, yet the API emits `200`. If the business contract mandates a fixed envelope, **the HTTP status must still be correct**:

```json
{
  "code": "FORBIDDEN",
  "message": "Insufficient permission",
  "status": 403
}
```

The body above is only an example shape of an error envelope; the actual HTTP response must be **403**, not 200. Do not use `catch(Exception)` to write an envelope before checking the exception class or permissions.

### 5.4. Case D: Non-Existent Resource Returns Wrong 403/404

A `404` only means "not found" **after** appropriate access permissions have been checked (depending on policy). If anonymous and under-privileged users call the same document, check ordering can alter what is observed:

```text
Anonymous -> GET /api/documents/404
  -> @PreAuthorize denies first -> 401

Viewer authenticated, missing document:read -> GET /api/documents/404
  -> @PreAuthorize denies first -> 403

Reader authenticated, has document:read -> GET /api/documents/404
  -> service runs, document missing -> 404
```

This is an intentional outcome of the example. Some products intentionally return 404 instead of 403 to avoid disclosing resource existence, but that must be an approved policy tested consistently; do not let an exception handler alter it arbitrarily.

### 5.5. Case E: 404/500 Error Turns into 403 During `/error` Dispatch

An already authorized request can throw an exception causing the container to perform a `DispatcherType.ERROR` dispatch to render an error response. If `AuthorizationFilter` also denies the error dispatch (due to `anyRequest().denyAll()`), the original error may be masked by a new authorization failure. That is why the example permits `DispatcherType.ERROR` instead of permitting only the initial request. In real applications, also consider FORWARD/ASYNC dispatches if those mechanisms are used, and test error paths for both authenticated and anonymous callers.

## 6. Two Ways to Standardize Error Bodies While Preserving Statuses

### Option 1 — Let Security Handle 401/403, MVC Handle Domain Errors

This is the approach used in the example:

- `AuthenticationEntryPoint`: missing or wrong auth → status 401, add appropriate challenge.
- `AccessDeniedHandler`: authenticated without permission → status 403.
- `@RestControllerAdvice` for not-found/validation → 404/400 per business logic.
- Infrastructure errors must not be turned into 2xx; provide a 5xx error handler and proper logging/tracing.

You can use `ProblemDetail`, fixed JSON, or your organization's error envelope. The core principle is that **the actual HTTP status**, `Content-Type`, and the `status` field in the body do not contradict each other; do not put stack traces, sensitive paths, or internal reasons into public responses.

### Option 2 — Custom Entry Point / Denied Handler per Authentication Scheme

A system may use multiple schemes, e.g., `/api/**` with Bearer tokens and `/admin/**` with form login. In that case:

- Each `SecurityFilterChain` must define its `securityMatcher` and chain order accurately.
- OAuth2 Resource Server provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` to generate Bearer-compliant challenges and error codes; custom handlers must preserve those headers/challenges.
- Form login can redirect to the login page (`302`) per the UI contract rather than forcing `401 JSON` like an API.
- If a request is handled by the application **without going through SecurityFilterChain** (standalone MVC test or another adapter), do not expect security filters to translate exceptions.

**Do not put `@ResponseStatus(403)` on every `AccessDeniedException` as a blanket solution.** It cannot distinguish anonymous from authenticated callers, does not handle Basic/Bearer login errors, and can strip challenge details.

## 7. Security Layer Testing Checklist

| Layer | Recommended Test | What It Verifies |
| --- | --- | --- |
| Method security | Call Spring-managed service with sufficient/insufficient authorities | `@PreAuthorize` actually protects the business method |
| HTTP authentication | Anonymous, wrong or expired password/token | `AuthenticationEntryPoint` returns 401/challenge per scheme |
| HTTP authorization → method | HTTP URL matcher lets request reach controller, but method denies | 401/403 originates from method security, not blocked earlier by HTTP |
| Standalone HTTP authorization | URLs outside whitelist, wrong role at filter | `SecurityFilterChain` still protects endpoints |
| MVC error handling | Business not-found/validation | 404/400, not hijacked by security handlers |
| Unexpected exceptions | Simulate real system failure | Preserves 5xx, not converted to 2xx/403 |
| Output contract | Assert HTTP status **and** body status/headers | No status mismatch, no detail leaks |
| Asynchronous/streaming | Exception occurs after response commit | Application-specific mechanism exists; do not assume status can change post-commit |

For APIs with write operations, add tests proving denial happens before saving to the DB or sending messages. Be cautious with `@PostAuthorize`: a post-execution check can return 403 **after side effects have already occurred**; if the operation mutates state, prefer pre-execution authorization and control transactions/rollbacks accordingly.

For resource-level security, beyond `hasAuthority`, also test ownership such as `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")` with owning and non-owning users. That policy depends on business code, so provide a real `documentPolicy` bean and test the full path from controller through proxy, rather than stopping at hardcoded mock statuses.

## 8. Mistakes to Avoid When Writing Tests

1. **MockMvc without connecting SecurityFilterChain.** `MockMvcBuilders.standaloneSetup(...)` creates a standalone MVC setup; without adding `springSecurity()`/filters, 401/403 test statuses do not represent the real app. In the example using `@SpringBootTest + @AutoConfigureMockMvc`, filters are configured in the context.
2. **Mocking the service loses `@PreAuthorize` logic.** If you mock the AOP-protected bean itself, the real interceptor may no longer execute as in production. Use the real service bean or place mocks on dependencies beneath the service.
3. **`@WithMockUser` for an "anonymous" test.** This annotation explicitly attaches an authenticated user and is unsuitable for testing the 401 branch from anonymous callers.
4. **Asserting only `status=403` in the JSON body.** The server could still be returning HTTP 200. Always assert `status().isForbidden()` alongside the body.
5. **Asserting only 403 without checking 200.** A deny-all configuration also passes negative tests; include positive tests with valid permissions to prove the route works.
6. **Testing only at the URL layer.** If an HTTP matcher blocks early, it does not prove `@PreAuthorize` works. Use a controlled `permitAll` route to test the service, or unit-test the method proxy separately.
7. **Catching all exceptions in Advice** and turning them into 500. This is one of the main causes of losing method security's 401/403 signals.
8. **Confusing `hasRole("ADMIN")` with `hasAuthority("ADMIN")`.** `hasRole("ADMIN")` defaults to looking for `ROLE_ADMIN`; the example's authority uses the full name `document:read`, so check `hasAuthority("document:read")`.
9. **Not testing error dispatch / multi-chain.** 404/500 statuses can be altered by URL rules on dispatches or another chain.
10. **Expecting every exception to automatically become 401/403.** Business and programming errors are not `AccessDeniedException`/`AuthenticationException`; mapping must match the right class and layer.
11. **Forgetting committed responses.** Once the body has streamed, handlers cannot reliably change the status; design authorization before generating the response.
12. **Not restricting details in body/logs.** Security exception messages may contain policy info; output only safe messages and a correlation ID, keeping details in controlled logs.

## 9. Extension Exercises You Can Apply Immediately

### 9.1. Intentionally Add Broken Advice and Catch It with Tests

Temporarily add an `@ExceptionHandler(Exception.class)` snippet returning `ResponseEntity.status(500)`. Re-run the anonymous/insufficient-authority tests: tests relying on method security propagation must detect the status changing to 500. Remove that handler, replace it with narrow handlers for specific business errors, and re-run the tests. This is a **controlled experiment in test code**, not a configuration to keep in production.

### 9.2. Switch from Basic to Bearer Token

Replace `httpBasic` with a Resource Server/JWT configuration suited to your project, then verify: missing/invalid token → 401 with `WWW-Authenticate: Bearer ...`; valid token lacking scope → 403 and appropriate challenge/details; valid token with sufficient scope → 200; missing entity → 404. Do not copy the Basic handler from the example into a Bearer environment.

### 9.3. Add Ownership and Side-Effect Checks

Use two users both having `document:read` while documents belong to different owners, and test `@PreAuthorize` against `documentId` and `Authentication`. For update endpoints, assert the DB is unchanged after 403; verify that checks run before mutations and unexpected results are not masked by a `ResponseEntity.ok(...)` wrapper.

## 10. Reference Documentation

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, interceptors, and denied exceptions.
- [Spring Security — Servlet Architecture / Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `ExceptionTranslationFilter` position and authentication/authorization branching.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): `AuthenticationEntryPoint` and `AccessDeniedHandler`.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matchers, ordering, and `DispatcherType.ERROR`.
- [Spring Framework — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ExceptionHandler`, `@ControllerAdvice`, and resolvers.
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): testing with `MockMvc` and security filters.

**Completion criteria:** When access is denied at the **service/method**, the web layer must accurately distinguish **401 for anonymous or invalid credentials**, **403 for authenticated users lacking permissions**, and preserve **404/400/500** for other error types. Tests must verify HTTP status, headers, error bodies, and traversal through the method-security proxy rather than looking only at exception messages.