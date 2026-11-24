# Filter Errors Are Not Automatically Handled by @ControllerAdvice in Spring Security

## 1. Common Symptom

A Spring Boot application has an exception handler like this:

```java
@RestControllerAdvice
class ApiExceptionAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_INPUT"));
    }
}
```

When a `@RestController` throws `IllegalArgumentException`, the client receives HTTP 400 with JSON from the advice. Yet when a `Filter` or `OncePerRequestFilter` throws **the exact same exception type**, the client may see HTTP 500, an HTML error page, a default container response, or a dispatch to `/error` instead of the expected JSON.

This is not a bug where "the annotation stopped working". The cause is a **pipeline boundary**: `@RestControllerAdvice` belongs to Spring MVC's exception resolution mechanism, whereas a Servlet Filter runs **outside/around** `DispatcherServlet`. Exceptions thrown before entering `DispatcherServlet` do not automatically flow into MVC's `HandlerExceptionResolver` chain.

**Rules to remember:**

- Errors thrown inside a **Spring MVC handler/controller** are typically handed by `DispatcherServlet` to `HandlerExceptionResolver`, where `@ExceptionHandler`/`@ControllerAdvice` can participate.
- Errors thrown **directly inside a Servlet Filter** are not automatically caught by `DispatcherServlet` and routed to advice.
- **Spring Security** authentication/authorization errors have their own handling paths: `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, or an authentication filter's failure handler.
- Unhandled errors can escape to the **Servlet container**, triggering an ERROR dispatch/`/error` or HTTP 500. That is **not evidence** that advice handled the exception directly from the filter.

This lesson focuses on Spring Boot 3.x / Spring Security 6.x Servlet (Java 17+). A dedicated section at the end covers WebFlux differences.

## 2. Where Do Filters, Spring Security, and Controllers Sit?

A typical Servlet request follows this general order:

```text
HTTP client
   |
   v
Servlet container (Tomcat/Jetty/Undertow)
   |
   v
Container FilterChain
   |
   +-- Application Filter A
   |
   +-- DelegatingFilterProxy
   |      |
   |      v
   |   FilterChainProxy (Spring Security)
   |      |
   |      +-- SecurityContextHolderFilter
   |      +-- CsrfFilter / auth filters / ...
   |      +-- ExceptionTranslationFilter
   |      +-- AuthorizationFilter
   |      +-- custom security filters (position per config)
   |
   +-- Application Filter B
   |
   v
DispatcherServlet
   |
   +-- HandlerMapping
   +-- HandlerAdapter
   +-- @Controller / @RestController
   |      |
   |      +-- Exception during MVC handling?
   |             |
   |             v
   |       HandlerExceptionResolver chain
   |             |
   |             +-- ExceptionHandlerExceptionResolver
   |             |       -> @ExceptionHandler / @ControllerAdvice
   |             +-- ResponseStatusExceptionResolver
   |             +-- DefaultHandlerExceptionResolver
   |
   v
HTTP response
```

This is a role diagram, **not a guarantee of the exact order of every security filter**: the actual chain depends on configuration, Spring Security version, matchers, and how filters are inserted. Inspect `FilterChainProxy` logs or introspect `SecurityFilterChain` when debugging filter ordering.

### An Exception Can Cross Multiple Boundaries

A controller throws `IllegalArgumentException`:

```text
Controller throw
   -> DispatcherServlet catches
   -> HandlerExceptionResolver
   -> @RestControllerAdvice
   -> JSON 400
```

A custom filter throws `IllegalArgumentException` **before calling** `chain.doFilter(...)`:

```text
Custom Filter throw
   -> DispatcherServlet has not been invoked yet
   -> MVC HandlerExceptionResolver is NOT automatically triggered
   -> error bubbles up to FilterChain/container
   -> container error handling (depending on config)
```

A filter wrapping `chain.doFilter` can also catch exceptions bubbling back out from a controller; yet once an exception has been resolved by MVC resolvers, usually **no exception remains to bubble back to the filter**. Conversely, a filter must not rely on MVC mechanisms to automatically handle errors thrown by the filter itself.

## 3. What Does HandlerExceptionResolver Actually Do?

Spring MVC resolves exceptions through `HandlerExceptionResolver` implementations. Common ones:

| Component | Purpose |
| --- | --- |
| `ExceptionHandlerExceptionResolver` | Invokes `@ExceptionHandler` on controllers or `@ControllerAdvice` |
| `ResponseStatusExceptionResolver` | Maps exceptions annotated with `@ResponseStatus` or `ResponseStatusException` in MVC context |
| `DefaultHandlerExceptionResolver` | Translates standard MVC exceptions into appropriate HTTP statuses |
| `HandlerExceptionResolverComposite` | Organizes the resolver chain per configuration |

`@RestControllerAdvice` combines `@ControllerAdvice` and `@ResponseBody`; it applies to **MVC exception resolution**, not as a global servlet container exception handler. `@ExceptionHandler(Exception.class)` is not a magical "try/catch everywhere in the JVM".

Example:

```java
@RestController
class ExampleController {
    @GetMapping("/api/from-controller")
    String fail() {
        throw new IllegalArgumentException("invalid business field");
    }
}

@RestControllerAdvice
class ExampleAdvice {
    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> bad(IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "MVC_BAD_REQUEST"));
    }
}
```

When a request **reaches the MVC handler** and the exception is supported by this resolver, the client receives HTTP 400. That does not imply `@RestControllerAdvice` will catch errors inside `Filter#doFilter`.

**An important nuance:** if an exception is thrown *inside a controller/method security*, an overly broad `@ControllerAdvice` like `@ExceptionHandler(Exception.class)` can sometimes **intercept security errors** before they reach `ExceptionTranslationFilter`. Avoid swallowing `AuthenticationException`/`AccessDeniedException` and turning them into meaningless 500s. Keep a clear boundary between business exceptions and authentication/authorization failures.

## 4. How Does Spring Security Handle 401/403 at the Filter Layer?

Spring Security Servlet provides `ExceptionTranslationFilter`. By contract, this filter translates `AuthenticationException` and `AccessDeniedException` **thrown from the downstream chain segment it wraps** into HTTP behavior.

```text
ExceptionTranslationFilter
     |
     +-- chain.doFilter(request, response)
             |
             +-- Downstream AuthorizationFilter
             +-- Downstream MVC / method security
             +-- Filters positioned AFTER ExceptionTranslationFilter
     |
     +-- catch AuthenticationException
     |       -> AuthenticationEntryPoint.commence(...)
     |
     +-- catch AccessDeniedException
             |
             +-- user unauthenticated/anonymous?
             |       -> AuthenticationEntryPoint
             |
             +-- user authenticated yet lacking permission?
                     -> AccessDeniedHandler.handle(...)
```

Key point: `ExceptionTranslationFilter` cannot wrap **filters running before it**, because exceptions from upstream filters occur before control enters its `chain.doFilter` call. Neither is it a **generic exception handler** for arbitrary `RuntimeException`, `IOException`, or DB failures.

### AuthenticationEntryPoint and AccessDeniedHandler

| Scenario | Appropriate Component | Typical HTTP |
| --- | --- | --- |
| Request to protected resource while unauthenticated | `AuthenticationEntryPoint` | 401 JSON/Bearer challenge or login redirect (browser) |
| Invalid authentication | Entry point or `AuthenticationFailureHandler` depending on filter | 401 or response per login flow |
| Authenticated user lacking permissions | `AccessDeniedHandler` | 403 |
| Bad controller input | `@ControllerAdvice`/`HandlerExceptionResolver` | 400/422 per contract |
| Custom filter rejects header/request | Filter-local handler, writer, or resolver bridge | 400/401/403 depending on nature |
| Filter throws `NullPointerException` | Should not be turned into 401/403 | 500 + internal log, no stack trace leaked |
| CSRF from `CsrfFilter` | Check `CsrfFilter`'s own handler and active chain | Usually 403 |
| URL rejected by `StrictHttpFirewall` | `RequestRejectedHandler`/container layer | Usually 400 per configured handler |

**Do not treat every filter error as 401.** 401 means **unauthenticated/cannot authenticate**, whereas 403 means **authenticated yet denied by authorization** (with anonymous/browser exceptions), 400 means bad client request, and 500 means unexpected server error.

### Distinguishing Three "Failure Hooks"

- `AuthenticationEntryPoint` starts authentication when a request is not authenticated or a security error requires a challenge.
- `AuthenticationFailureHandler` usually belongs to a **login-processing filter**, such as `UsernamePasswordAuthenticationFilter`, to handle wrong username/password. This error may be caught by the filter before reaching `ExceptionTranslationFilter`.
- `AccessDeniedHandler` handles denied access for an already authenticated user within its scope.

In Bearer API systems, Spring Security provides RFC 6750 standard handlers such as `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler`; do not replace them with hand-rolled JSON that drops protocol-significant `WWW-Authenticate` headers.

## 5. Filter Order: Why Can addFilterBefore Change the Outcome?

Suppose:

```java
http.addFilterBefore(customFilter, UsernamePasswordAuthenticationFilter.class);
```

In the typical Spring Security Servlet order, `UsernamePasswordAuthenticationFilter` sits **before** `ExceptionTranslationFilter`. A custom filter inserted at this position that directly throws `AuthenticationException` or `AccessDeniedException` should not expect `ExceptionTranslationFilter` to catch it by default.

A misleading example:

```java
// WRONG / INSUFFICIENT if filter runs before ExceptionTranslationFilter:
if (tokenMissing) {
    throw new BadCredentialsException("Missing credential");
}
```

A developer thinks "`BadCredentialsException` is an `AuthenticationException`, so Spring Security will definitely return 401". Yet **exception type alone does not decide where it is caught**; filter position and surrounding handling code decide.

Right solutions typically are:

1. For **bearer tokens**, use Spring Security's standard resource server filter/configuration instead of writing a custom parser.
2. For **custom authentication flows**, invoke `AuthenticationManager`/`AuthenticationEntryPoint` or `AuthenticationFailureHandler` at that filter's boundary.
3. For **non-authentication validation**, write structured 400 directly or explicitly invoke `HandlerExceptionResolver` when reusing MVC mechanisms is desired.
4. If intentionally letting exceptions bubble to the container, use container/`/error` error handling, while verifying exact dispatch behavior and response schema; do not assume `@ControllerAdvice` caught it directly.

## 6. Java 17 Exercise: Modeling Exception Boundaries Accurately

Goal of this **pure Java** example with no Spring dependency: clearly see why the same `IllegalArgumentException` produces different results when thrown in a controller vs a filter.

Create **`FilterBoundaryDemo.java`**:

```java
public final class FilterBoundaryDemo {
    record Result(int status, String source) {}

    static final class Unauthenticated extends RuntimeException {}
    static final class Forbidden extends RuntimeException {}

    // Container is the final boundary: escaped errors become a generic error.
    static Result container(String path, boolean authenticated, boolean admin) {
        try {
            return outerFilter(path, authenticated, admin);
        } catch (RuntimeException ex) {
            return new Result(500, "CONTAINER_ERROR");
        }
    }

    // Filter outside DispatcherServlet and the security translator.
    static Result outerFilter(String path, boolean authenticated, boolean admin) {
        if (path.equals("/filter-error")) {
            throw new IllegalArgumentException("bad value before MVC");
        }
        return securityBoundary(path, authenticated, admin);
    }

    // Simulates ExceptionTranslationFilter; not a Spring implementation.
    static Result securityBoundary(
            String path, boolean authenticated, boolean admin) {
        try {
            if (!authenticated) {
                throw new Unauthenticated();
            }
            if (path.equals("/admin") && !admin) {
                throw new Forbidden();
            }
            return dispatcherServlet(path);
        } catch (Unauthenticated ex) {
            return new Result(401, "AUTH_ENTRY_POINT");
        } catch (Forbidden ex) {
            return new Result(403, "ACCESS_DENIED_HANDLER");
        }
    }

    // Simulates DispatcherServlet + MVC HandlerExceptionResolver.
    static Result dispatcherServlet(String path) {
        try {
            if (path.equals("/mvc-error")) {
                throw new IllegalArgumentException("bad controller input");
            }
            return new Result(200, "CONTROLLER");
        } catch (IllegalArgumentException ex) {
            return new Result(400, "MVC_CONTROLLER_ADVICE");
        }
    }

    private static void show(String label, Result result) {
        System.out.println(label + "="
                + result.status() + ":" + result.source());
    }

    public static void main(String[] args) {
        show("controllerException",
                container("/mvc-error", true, false));
        show("filterException",
                container("/filter-error", true, false));
        show("missingAuthentication",
                container("/hello", false, false));
        show("missingRole",
                container("/admin", true, false));
        show("success",
                container("/hello", true, false));
    }
}
```

Run with JDK 17+:

```bash
javac FilterBoundaryDemo.java
java FilterBoundaryDemo
```

**Deterministic stdout:**

```text
controllerException=400:MVC_CONTROLLER_ADVICE
filterException=500:CONTAINER_ERROR
missingAuthentication=401:AUTH_ENTRY_POINT
missingRole=403:ACCESS_DENIED_HANDLER
success=200:CONTROLLER
```

**Meaning of each line:**

- `controllerException`: exception thrown inside the DispatcherServlet model and converted to 400 by the resolver.
- `filterException`: exception thrown before DispatcherServlet; bypasses MVC advice and bubbles to the container.
- `missingAuthentication`: security boundary detects required authentication and invokes the 401 entry point.
- `missingRole`: authenticated yet lacking role, handler returns 403.
- `success`: request traverses all layers without exception.

This is an **educational model**, not using `jakarta.servlet.Filter` or real Spring Security classes. The simulation does not prove every URL, filter placement, or default status on Spring Boot; the section below uses real framework configuration.

## 7. Spring Boot 3.x Project Illustrating Real Error Types

Let's build a minimal Servlet app with:

- `/api/controller-error`: throws `IllegalArgumentException` **inside controller**, handled by `@RestControllerAdvice`.
- `/api/filter-error`: intercepted by a **custom filter** which writes JSON 400 itself.
- `/api/hello`: requires HTTP Basic authentication; missing credentials return JSON 401 from `AuthenticationEntryPoint`.
- `/api/admin`: requires role ADMIN; ordinary users receive JSON 403 from `AccessDeniedHandler`.
- `/api/public`: public access.

**Note:** HTTP Basic + in-memory users with sample passwords are for study/test environments only. Production must use safe encoders, HTTPS, protected credential storage, and appropriate authentication mechanisms.

### 7.1. Gradle Dependencies

In a Spring Boot **3.x**, Java 17+ project with matching Spring Boot/Dependency Management plugins configured, add:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Do not add `spring-boot-starter-webflux` to this project just to reuse snippets; this is **Servlet/MVC**. Use Jakarta Servlet (`jakarta.servlet.*`), not `javax.servlet.*`, when running Spring Boot 3.x.

### 7.2. Main Application

File **`src/main/java/demo/boundary/FilterBoundaryApplication.java`**:

```java
package demo.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterBoundaryApplication.class, args);
    }
}
```

### 7.3. Controller and MVC Advice

File **`src/main/java/demo/boundary/ApiController.java`**:

```java
package demo.boundary;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/hello")
    String hello() {
        return "hello";
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }

    @GetMapping("/api/controller-error")
    String controllerError() {
        throw new IllegalArgumentException("invalid request parameter");
    }
}
```

File **`src/main/java/demo/boundary/ApiExceptionAdvice.java`**:

```java
package demo.boundary;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<Map<String, String>> invalid(IllegalArgumentException ex) {
        // Do not return ex.getMessage() arbitrarily to avoid internal leaks.
        return ResponseEntity.badRequest()
                .body(Map.of("code", "MVC_BAD_REQUEST"));
    }
}
```

This advice has **global MVC scope**. It catches `IllegalArgumentException` only when MVC exception resolution runs; there is no automatic wiring connecting exceptions from arbitrary Filters.

### 7.4. Custom Filter Handling Its Own Errors Responsibly

File **`src/main/java/demo/boundary/EarlyFailureFilter.java`**:

```java
package demo.boundary;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class EarlyFailureFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if ("/api/filter-error".equals(request.getServletPath())) {
            // Filter responds proactively; DO NOT throw an exception hoping
            // @ControllerAdvice will handle it automatically.
            ApiSecurity.json(response, 400, "FILTER_REJECTED");
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Why write the response directly:

- The filter knows which request condition failed and which error type it is handling.
- `ApiSecurity.json(...)` sets status/Content-Type/no-store and a stable error code, avoiding sensitive data leaks.
- `return` immediately after writing the response so **the controller does not run next**. Never both write and call `chain.doFilter`.
- The filter is not annotated with `@Component` in the example: it is instantiated **once inside `SecurityFilterChain`** to prevent simultaneously auto-registering in the servlet container and inserting into the security chain. Double registration can cause surprising ordering or double invocation.

In production, not every error originating in a Filter is 400: classify accurately and route to the responsible handler when involving authentication, CSRF, rate limiting, firewalls, or server errors.

### 7.5. SecurityFilterChain and Entry Point / Denied Handler

File **`src/main/java/demo/boundary/ApiSecurity.java`**:

```java
package demo.boundary;

import java.io.IOException;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration(proxyBeanMethods = false)
public class ApiSecurity {

    static void json(HttpServletResponse response, int status, String code)
            throws IOException {
        if (response.isCommitted()) {
            return; // must log internally; too late to change HTTP response
        }
        response.setStatus(status);
        response.setCharacterEncoding("UTF-8");
        response.setContentType("application/json");
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        // Code is a SERVER-CHOSEN CONSTANT in this example.
        response.getWriter().write("{\"code\":\"" + code + "\"}");
    }

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {

        AuthenticationEntryPoint unauthenticated = (request, response, ex) -> {
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo-api\"");
            json(response, 401, "UNAUTHENTICATED");
        };

        AccessDeniedHandler forbidden = (request, response, ex) ->
                json(response, 403, "FORBIDDEN");

        return http
                .authorizeHttpRequests(auth -> auth
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        .requestMatchers("/api/public", "/api/filter-error")
                            .permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(unauthenticated))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(unauthenticated)
                        .accessDeniedHandler(forbidden))
                .addFilterBefore(new EarlyFailureFilter(),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }

    @Bean
    UserDetailsService demoUsers() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password("{noop}alice-pass")
                        .roles("USER")
                        .build(),
                User.withUsername("root")
                        .password("{noop}root-pass")
                        .roles("ADMIN")
                        .build());
    }
}
```

**Configuration limitations:**

- This is a **GET-only** HTTP example, so it does not demonstrate sending CSRF tokens. Spring Security still enables CSRF by default; **do not** blindly call `csrf.disable()` for browser HTTP Basic just because the API serves JSON, since browsers can still auto-send Basic credentials to the site.
- `{noop}` passwords are for testing only. Use BCrypt/Argon2/PBKDF2 per policy and proper secrets management in real deployments.
- `DispatcherType.ERROR` is permitted through authorization rules so the container can perform error dispatches when needed; never turn `/error` into a stack-trace leak. Verify filter registrations with dispatcher types on your real container.
- `AuthenticationEntryPoint` sets `WWW-Authenticate: Basic ...` matching HTTP Basic context; never use a Basic header for bearer JWTs. The two mechanisms have different challenge protocols.
- `HttpSecurity.exceptionHandling(...)` configures authentication/authorization error paths within the protected scope; it is **not** a catch-all handler for `NullPointerException` from a custom filter.
- `EarlyFailureFilter` is placed before `UsernamePasswordAuthenticationFilter`; if it **throws** an exception itself with no local handler, do not count on downstream `ExceptionTranslationFilter` to catch it.
- If session/form login, CORS, OAuth2 login, or resource server are needed, adjust filter chains and entry points for that flow; never enable conflicting mechanisms expecting them all to emit the same error.
- In multi-`SecurityFilterChain` systems, `@Order` and `securityMatcher` decide which chain handles a request. A request passes through only the first matching chain; it does **not** automatically traverse all chains.

## 8. Expected HTTP Outcomes When Running the Spring Boot Demo

Run the application:

```bash
./gradlew bootRun
```

On Windows:

```powershell
./gradlew.bat bootRun
```

Test the URLs:

```bash
# Public endpoint
curl -i http://localhost:8080/api/public

# Unauthenticated: entry point
curl -i http://localhost:8080/api/hello

# User has USER role, yet endpoint requires ADMIN
curl -i -u alice:alice-pass http://localhost:8080/api/admin

# MVC error: advice handles it
curl -i -u alice:alice-pass http://localhost:8080/api/controller-error

# Filter error: Filter returns JSON 400 itself
curl -i http://localhost:8080/api/filter-error

# User with sufficient permissions
curl -i -u root:root-pass http://localhost:8080/api/admin
```

Corresponding statuses and response bodies:

| Endpoint | Authentication | Status | Typical Body | Handler Source |
| --- | --- | --- | --- | --- |
| `/api/public` | None needed | 200 | `public` | Controller |
| `/api/hello` | None | 401 | `{"code":"UNAUTHENTICATED"}` | AuthenticationEntryPoint |
| `/api/admin` | alice/USER | 403 | `{"code":"FORBIDDEN"}` | AccessDeniedHandler |
| `/api/controller-error` | alice/USER | 400 | `{"code":"MVC_BAD_REQUEST"}` | @RestControllerAdvice |
| `/api/filter-error` | None needed | 400 | `{"code":"FILTER_REJECTED"}` | EarlyFailureFilter |
| `/api/admin` | root/ADMIN | 200 | `admin` | Controller |

The HTTP Basic example with `http://localhost:8080` is strictly for local/test machines. **Never** send passwords over plaintext public HTTP: production requires HTTPS. Demos need dedicated cookie/session policies if browser login is added; do not conclude the Basic code above is production-ready.

### Why Can a Custom Filter Return the Same JSON Shape?

You can share an **error schema** (e.g., `code`, `message`, `traceId`, `timestamp`) via a shared `ErrorResponseWriter`; however, **sharing a format does not mean sharing the catch location**. `@ControllerAdvice` handles MVC, entry points handle auth, denied handlers handle authorization, and filter-specific handlers handle filter-level issues. Each of these can call a shared serializer function or a uniformly configured `ObjectMapper`.

If writing JSON by string concatenation, it is **safe only with server-defined constant codes** as in the demo. Never splice `exception.getMessage()`, user input, headers, or URLs directly into JSON; use a Jackson serializer and an error-code allowlist.

## 9. MockMvc Integration Tests Proving the Handling Paths

Here are tests for the application just built, using `spring-security-test` and `spring-boot-starter-test`. File **`src/test/java/demo/boundary/ApiErrorBoundaryTest.java`**:

```java
package demo.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ApiErrorBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void controllerErrorsUseMvcAdvice() throws Exception {
        mvc.perform(get("/api/controller-error")
                    .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MVC_BAD_REQUEST"));
    }

    @Test
    void filterErrorsUseFilterWriter() throws Exception {
        mvc.perform(get("/api/filter-error"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("FILTER_REJECTED"));
    }

    @Test
    void anonymousRequestsUseAuthenticationEntryPoint() throws Exception {
        mvc.perform(get("/api/hello"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    }

    @Test
    void authenticatedWithoutRoleUsesAccessDeniedHandler()
            throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("alice", "alice-pass")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void authenticatedAdminCanAccess() throws Exception {
        mvc.perform(get("/api/admin")
                    .with(httpBasic("root", "root-pass")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }
}
```

Run:

```bash
./gradlew test --tests demo.boundary.ApiErrorBoundaryTest
```

If the project has Spring Boot 3.x, Java 17+, right dependencies, and runs the code above, **5 tests are expected to PASS**. This is a logic- and API-reviewed integration-test design; the lesson environment does not provide a Spring Boot/Gradle project to compile/run all of this end-to-end. The pure Java unit example in section 6 was run and verified separately.

**What this test actually proves:** HTTP status/body differ by where the exception/handler executes. Do not use this test to claim all system-wide filter errors are caught by MVC advice.

### An Additional Test for When a Filter Throws an Exception

If you temporarily change the filter implementation to:

```java
if ("/api/filter-error".equals(request.getServletPath())) {
    throw new IllegalArgumentException("thrown before DispatcherServlet");
}
```

then `filterErrorsUseFilterWriter()` no longer holds: the Filter no longer calls the writer. The outcome may become a servlet container ERROR dispatch to `/error`, a 500 error, or vary by environment. **Do not claim every container returns the exact same body**, because it depends on error page registrations, dispatcher types, Boot error handling, and response commitment.

In real tests, you can attach a spy/counter to `@RestControllerAdvice` to prove that handler is **not invoked directly** for the Filter exception; inspect error dispatch separately if needed.

## 10. Can Filter Errors Be Explicitly Delegated to HandlerExceptionResolver?

Yes — yet this is an **explicit action**, not Spring automatically wiring the two pipelines together.

A filter can inject MVC's proper `HandlerExceptionResolver` bean and **call `resolveException(request, response, handler, exception)`**. A global `@RestControllerAdvice` can then participate via `ExceptionHandlerExceptionResolver` if the exception matches and the resolver is configured properly.

Illustrative **Filter snippet**:

```java
public final class MvcDelegatingValidationFilter extends OncePerRequestFilter {

    private final HandlerExceptionResolver resolver;

    public MvcDelegatingValidationFilter(HandlerExceptionResolver resolver) {
        this.resolver = resolver;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        if ("/api/invalid-header".equals(request.getServletPath())) {
            IllegalArgumentException problem =
                    new IllegalArgumentException("invalid header");

            if (response.isCommitted()) {
                return; // log internally: cannot alter response
            }

            ModelAndView handled =
                    resolver.resolveException(request, response, null, problem);

            if (handled == null && !response.isCommitted()) {
                response.setStatus(400);
                response.setContentType("application/json");
                response.getWriter().write("{\"code\":\"FILTER_BAD_REQUEST\"}");
            }
            return;
        }

        chain.doFilter(request, response);
    }
}
```

Required imports: `jakarta.servlet.FilterChain`, `jakarta.servlet.ServletException`, `jakarta.servlet.http.HttpServletRequest`, `jakarta.servlet.http.HttpServletResponse`, `java.io.IOException`, `org.springframework.web.filter.OncePerRequestFilter`, `org.springframework.web.servlet.HandlerExceptionResolver`, and `org.springframework.web.servlet.ModelAndView`.

Inject the MVC bean via `@Qualifier("handlerExceptionResolver")` when wiring it; do not instantiate an empty resolver expecting all advice to be present. `handler=null` because the Filter may not have a selected MVC handler yet; advice restricted by controller/package/annotation selectors may not match. `resolveException(...)` returning `null` means the resolver **could not handle it**. If a handler already wrote the response, calling the resolver again is unsafe.

### When NOT to Use a Resolver Bridge?

- **Authentication/authorization** errors: use `AuthenticationEntryPoint`/`AccessDeniedHandler` or authentication failure hooks to preserve protocol compliance.
- **`StrictHttpFirewall`/`RequestRejectedException`** errors: have a dedicated handler at the firewall layer.
- Filter whose response is already committed or streaming: the resolver cannot "rewind" already-sent bytes.
- Filter running on requests that never go to MVC, such as static resources, non-MVC servlets, or certain ERROR/ASYNC dispatches: invoking advice may lack the same context and depends on resolver implementation.
- To mask a filter bug: fix exception handling at the source instead of swallowing every `Exception` into HTTP 400.

**Preference:** share an `ErrorResponseWriter`/`ErrorResponse` DTO for uniform JSON, while keeping **the right handler in the right layer**. Use a resolver bridge only with clear justification and integration tests.

## 11. Login Failures Need a Dedicated AuthenticationFailureHandler

A request passing through `UsernamePasswordAuthenticationFilter` can fail due to a wrong password, locked account, or nonexistent account. Login filters **typically catch their own authentication errors** and invoke `AuthenticationFailureHandler`, without waiting for `@ControllerAdvice`.

Browser app form login example:

```java
http.formLogin(form -> form
        .failureHandler((request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"code\":\"LOGIN_FAILED\"}");
        }));
```

This is a configuration snippet for Servlet `HttpSecurity`, not replacement code for the entire `SecurityFilterChain` in section 7's Basic project. For browser forms, redirecting to `/login?error` may be better than JSON; for APIs, JSON may fit. Always limit error details to prevent **username enumeration**, avoiding unnecessary differences between "user does not exist" and "wrong password".

**Distinguish:**

- Failed login attempt: login filter may invoke failure handler.
- Unauthenticated request to protected URL: `AuthenticationEntryPoint`.
- Validly logged-in user lacking permissions: `AccessDeniedHandler`.
- Validation/data error in controller: `@RestControllerAdvice`.
- Custom filter error occurring before those handlers: **the filter's own handler** or an intentional bridge.

## 12. 401, 403, 400, and 500: Do Not Confuse HTTP Statuses

**401 Unauthorized** usually means authentication is required or credentials are missing/invalid. HTTP Basic requires `WWW-Authenticate: Basic ...`; OAuth 2.0 RFC 6750 bearer tokens use `WWW-Authenticate: Bearer ...`. Browser flows may redirect to login instead of 401.

**403 Forbidden** usually means authenticated yet not permitted. However, for anonymous users encountering `AccessDeniedException`, `ExceptionTranslationFilter` can invoke the entry point (401/redirect) instead of returning 403. CSRF failures also typically return 403, yet are handled at a different spot in the chain.

**400 Bad Request** is for invalid client input, such as a malformed header caught by custom validation. Never turn a null pointer or DB connection failure into 400; that is a server error.

**500 Internal Server Error** is for unexpected system failures. Log an internal correlation ID, never returning stack traces, SQL, secrets, or exception class names to clients.

### Error JSON Contract

Generic shape example:

```json
{
  "code": "UNAUTHENTICATED",
  "message": "Authentication is required",
  "traceId": "safe-correlation-id"
}
```

These values are server-generated and contain no usernames/passwords/tokens/stack traces. If the app uses Spring `ProblemDetail` per RFC 9457, you can unify on `application/problem+json`, yet each layer must proactively render it properly or delegate to a shared writer. Never set content type `application/problem+json` and emit a body violating the Problem Details structure.

## 13. Special Exceptions at the Security Layer

### 13.1. CsrfFilter

`CsrfFilter` can handle an `AccessDeniedException` caused by a missing/invalid CSRF token through its own configured handler. It sits in the security filter chain, yet **do not assume every CSRF error flows into `ExceptionTranslationFilter`**. When consistent JSON 403 is needed, inspect the exact `CsrfFilter`/`AccessDeniedHandler` mechanism and run integration tests for `POST` missing/invalid CSRF tokens.

Never disable CSRF just to "fix" an HTML error page when the frontend expects JSON. If browsers send session cookies, CSRF remains a real threat. Identify the actual handling path before changing handlers.

### 13.2. StrictHttpFirewall and RequestRejectedException

Spring Security's `FilterChainProxy` can use `StrictHttpFirewall` to reject anomalous request URLs before entering normal filters. `RequestRejectedException` has its own handling path via `RequestRejectedHandler`/container config. It can fire **before MVC and even before ExceptionTranslationFilter**, so do not expect `@ControllerAdvice` or global `.exceptionHandling(...)` to automatically turn it into JSON 400.

Never loosen the firewall carelessly just because one URL was rejected; check URL encoding/path traversal/semicolons and routing contracts.

### 13.3. Authentication Filters Catch Errors Themselves

Filters like `UsernamePasswordAuthenticationFilter` and `BearerTokenAuthenticationFilter` can handle authentication failures according to their own contracts. For OAuth2 resource servers, prefer standard `oauth2ResourceServer(jwt/opaque)` configuration and standard entry points/denied handlers; do not catch `AuthenticationException` broadly and swap responses in ways that drop `WWW-Authenticate` or `invalid_token` codes.

### 13.4. Method Security from Controllers/Services

`@PreAuthorize` can throw `AccessDeniedException` during MVC method invocation. If your advice catches `Exception.class`, it may block the exception from bubbling out to `ExceptionTranslationFilter`. Avoid generic exception handlers that swallow 403s. If uniform error JSON is wanted, use intentional security exception handling and test it for real.

### 13.5. Errors from OncePerRequestFilter

`OncePerRequestFilter` prevents re-executing a filter across certain dispatches per configuration; it does **not** create a `try/catch` boundary routing all errors to MVC advice. For ASYNC/ERROR dispatches, whether the filter runs again also depends on dispatcher registrations and methods like `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`. If the response is already committed, do not try writing a second error body.

## 14. ERROR Dispatch, BasicErrorController, and /error

When an exception goes **unhandled** in a filter or servlet, the Servlet container may trigger an **ERROR dispatch** to a configured path such as `/error`. Spring Boot MVC typically provides `BasicErrorController` or an equivalent error handling mechanism there.

```text
Filter throw unhandled exception
   |
   v
Servlet container
   |
   +-- Error page mapping
           |
           +-- ERROR dispatch to /error
                 |
                 v
             DispatcherServlet
                 |
                 v
             BasicErrorController / custom ErrorController
```

Key point: **error dispatch is a separate request phase**; it does not prove the original exception was caught directly by `@RestControllerAdvice` inside `Filter#doFilter`. The error page may be JSON/HTML depending on Accept headers, Boot config, auth, container, and response commit state.

Common pitfalls:

- `/error` itself requires authentication in Spring Security, leading to **401/403 instead of the original error**.
- Custom filter runs again during the ERROR dispatch and throws another exception.
- Response already wrote a partial body before failing, so the container cannot cleanly replace the response.
- Application calls `sendError` and then continues writing body bytes; results vary by container.

**When debugging**, inspect `DispatcherType.REQUEST`/`ERROR`, the URL path, the selected filter chain, content committed state, and the stack trace of the **root exception**, rather than looking only at the final status.

## 15. Once the Response Is Committed, You Cannot Fix Errors as If Nothing Happened

`HttpServletResponse.isCommitted()` indicates status/headers have already been sent to the client or flushed. If a downstream filter throws an exception after commit, switching from 200 to JSON 500 or 401 is nearly impossible.

Rules:

1. Check mandatory conditions before starting to stream/download a response.
2. Never write error JSON **after** already sending part of a CSV, ZIP, file, SSE, or response stream.
3. Whenever possible, use a shared error writer **before commit**.
4. After commit, mainly log and terminate/close the connection per server behavior; handle retries on the client if protocol supports it.
5. Avoid calling `response.reset()` unconditionally; after commit it can throw `IllegalStateException` and obscure the original error.

With `sendError(status)`, the container may trigger error page handling; with `setStatus(status)` + body, the application owns the output directly. The two approaches are not always equivalent regarding ERROR dispatches.

## 16. Filter Registration and Order Are Part of Correctness

There are two common ways to register a custom Servlet Filter:

1. **Container-level Filter** via `@Component`, `@WebFilter`, or `FilterRegistrationBean`; it runs in the servlet container filter chain.
2. **Security filter** added via `HttpSecurity.addFilterBefore/After/At(...)` and participating inside `FilterChainProxy`.

Never accidentally register the same filter both ways unless intentional. That complicates ordering and can cause duplicate authentication, double response writing, or confusing request dispatch debugging. `OncePerRequestFilter` is not a complete fix for accidental double registration.

**Verify proper filter placement:**

- Custom credential-reading filters must coordinate with `AuthenticationManager` and proper failure handling.
- Correlation ID/logging filters should usually not make authentication decisions themselves.
- Preliminary validation filters must return proper statuses and check whether the response is committed.
- Custom authorization filters should usually defer to `AuthorizationManager`/method security before writing bespoke rule filters.
- Filters outside `FilterChainProxy` cannot expect `ExceptionTranslationFilter` to handle their exceptions.

Helpful logging configuration:

```yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security: INFO
```

When deeper tracing is needed, enable logging briefly in test environments and **redact tokens/cookies/passwords**; never leave TRACE enabled indefinitely in production, as it can expose sensitive request metadata.

## 17. WebFlux: Same Principles, Different Handling APIs

Spring WebFlux does not use `DispatcherServlet`/`HttpSecurity`. It has its own WebFilter pipeline, `WebExceptionHandler`, `DispatcherHandler`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and exception-handling components.

Equivalent counterparts:

| Servlet/MVC | Reactive WebFlux |
| --- | --- |
| `Filter` / `OncePerRequestFilter` | `WebFilter` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` |
| `AccessDeniedHandler` | `ServerAccessDeniedHandler` |
| `SecurityContextHolder` (ThreadLocal-based) | `ReactiveSecurityContextHolder` |
| `HandlerExceptionResolver` | WebFlux stack exception handling and reactive error handlers |
| `HttpServletResponse` | `ServerHttpResponse` |

`@RestControllerAdvice` in WebFlux applies when handling exceptions inside controllers/handlers via WebFlux mechanisms; it is also **not a global try/catch for every WebFilter**. Use `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler`, and `WebExceptionHandler` at the right layers instead of forcing Servlet patterns into a reactive pipeline.

With `Mono/Flux`, errors can occur **after** a handler returns and downstream subscribes; understand `onErrorResume` operators, transactions, and committed responses so wrong statuses/bodies are not emitted. Never call `block()` on the event loop just to turn an error into a synchronous response.

## 18. Quick Diagnostic Matrix

| Symptom | Check First | Right Layer Fix |
| --- | --- | --- |
| Controller throws, advice returns expected JSON | Mapping and resolver are working | Keep advice for MVC errors |
| Filter throws, advice never runs | Was exception thrown before `DispatcherServlet`? | Filter writer, entry point, failure handler, or resolver bridge |
| Missing login gets HTML instead of JSON | Which entry point is active? `formLogin` or Basic/Bearer? | Choose API entry point, preserve protocol headers |
| Logged-in user gets 401 instead of 403 | Anonymous state/Authentication type/entry point? | Check security context and authorization |
| Wrong login password bypasses global advice | Login filter handles errors internally | `AuthenticationFailureHandler` |
| CSRF 403 differs from JSON denied handler | `CsrfFilter` handler and position | Configure right CSRF handler/SPA token flow |
| Firewall 400 skips MVC | `StrictHttpFirewall`, `RequestRejectedHandler` | Use firewall-layer handler, do not disable firewall carelessly |
| 500 at `/error`, original exception missing | Container ERROR dispatch | Read root stack trace and dispatcher type, avoid blocking `/error` |
| Filter throws while streaming | `response.isCommitted()` | Validate before streaming, log and abort properly |
| One request writes response twice | Does filter call `chain.doFilter` after writing? | `return` immediately after sending error |
| Filter runs twice | Both `@Component` and `addFilterBefore`? | Pick one registration |
| Security exception turned into 500 by advice | Is there a generic `@ExceptionHandler(Exception.class)`? | Do not swallow authn/authz errors |
| Controller test passes yet production filter test fails | Does MockMvc run the real FilterChain? | Use `@AutoConfigureMockMvc` and production config |
| Bearer error loses headers | Did custom entry point overwrite them? | Use RFC 6750 Bearer handlers |
| Async/ERROR dispatch mishandled by filter | DispatcherType/`OncePerRequestFilter` hooks | Tune filter dispatch behavior appropriately |

### Step-by-Step Debugging Workflow

1. Record **request method + URL + authenticated state** in test environments without collecting raw credentials.
2. Identify the first exception thrown: in a **Filter**, **SecurityFilterChain**, **DispatcherServlet**, controller, or service.
3. Identify filter ordering and which handler actually ran: `EntryPoint`, `AccessDeniedHandler`, `FailureHandler`, `HandlerExceptionResolver`, or `/error`.
4. Check whether the response was already committed before a handler wrote a body.
5. Check `DispatcherType.REQUEST/ERROR/ASYNC` and whether the filter gets invoked again.
6. Write **negative tests** for every critical error path.
7. Standardize JSON schemas via a shared helper rather than forcing everything into one `@ControllerAdvice`.
8. Log correlation ID, error category, and sensitive-data-scrubbed route; never log exception messages containing tokens/passwords.

## 19. Production Project Checklist

- [ ] Architecture diagram of `Filter → Spring Security → DispatcherServlet → Controller` matches the actual app.
- [ ] `@RestControllerAdvice` is used for MVC exceptions, not expected to catch all filter errors.
- [ ] `AuthenticationEntryPoint` handles 401/redirects properly for browsers, Basic, or Bearer.
- [ ] `AccessDeniedHandler` handles 403 when an authenticated user is denied.
- [ ] Login filter has `AuthenticationFailureHandler` matching the flow.
- [ ] Custom filter errors have an explicit writer/handler instead of throwing exceptions hoping advice catches them.
- [ ] `HandlerExceptionResolver` bridge (if any) is invoked explicitly, has a fallback, and is tested with null handlers.
- [ ] `AuthenticationException`/`AccessDeniedException` are never swallowed by generic MVC advice.
- [ ] CSRF/firewall errors are handled at their right layers without disabling controls just for prettier error responses.
- [ ] Never write an error response when `isCommitted()` is true; never both write and call `chain.doFilter`.
- [ ] Filters are not double-registered; `REQUEST/ERROR/ASYNC` dispatches are verified.
- [ ] API JSON errors preserve Basic/Bearer `WWW-Authenticate` headers.
- [ ] 400/401/403/500 carry accurate semantics, with messages free of stack traces, tokens, or PII.
- [ ] MockMvc integration tests cover controller errors, filter errors, auth errors, denied errors, and success.
- [ ] In WebFlux, `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`/`WebExceptionHandler` follow the reactive pipeline.

### Official References for Lookup

- Spring Security 6.5 — Servlet Security Architecture and Handling Security Exceptions: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security 6.5 — `ExceptionTranslationFilter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html
- Spring Security 6.5 — HTTP Basic: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html
- Spring Security 6.5 — Servlet OAuth2 Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/index.html
- Spring Framework — MVC Exception Handlers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — DispatcherServlet Exception Resolvers and Error Dispatch: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/exceptionhandlers.html
- Spring Boot — Error Handling in Servlet Web Applications: https://docs.spring.io/spring-boot/reference/web/servlet.html#error-handling
- Spring Security — Test Support, MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html

**Conclusion:** exceptions thrown from a Filter **do not automatically enter** `@ControllerAdvice`. For MVC exceptions, use `HandlerExceptionResolver`/advice; for Spring Security authentication and authorization errors, use entry points, denied handlers, or authentication failure handlers; for custom Filters, handle errors proactively inside the filter or invoke a resolver bridge only when truly needed. Understanding the exact **exception origin** and **filter order** ensures responses carry the right status, the right JSON, and never bypass security controls.
