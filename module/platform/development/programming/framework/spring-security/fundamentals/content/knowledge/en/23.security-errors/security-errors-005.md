# AccessDeniedHandler: Handling Access Denial Decisions

> Scope: Spring Security for **Servlet / Spring MVC** applications. This lesson belongs to the "Security Errors" group, focusing on how to return safe responses when a request is denied and how to avoid configurations that handle 403 errors improperly. In WebFlux, the corresponding mechanism uses `ServerAccessDeniedHandler`; the Servlet interface in this lesson is not used directly.

## 1. Understanding Responsibilities Correctly

**`AccessDeniedHandler` does not decide whether a user has permission.** Authorization decisions are usually made by `AuthorizationManager` via `AuthorizationFilter` or by method-level protection such as `@PreAuthorize`. When access is denied, Spring Security can throw `AccessDeniedException`. `ExceptionTranslationFilter` translates security exceptions into appropriate HTTP behavior; for a fully authenticated user lacking permissions, it invokes `AccessDeniedHandler`.

The handler is responsible for **responding to the denial**: setting the HTTP status, providing safe error content, forwarding to a 403 page if appropriate, and preserving protocol-required headers. The handler **must not** replace authorization rules, grant permissions itself, or continue processing the denied resource.

Components to distinguish:

| Component | Primary Responsibility |
| --- | --- |
| `Authentication` / login mechanism | Verifies identity, creates the authentication object |
| `AuthorizationManager` / `AuthorizationFilter` | Evaluates URL access rules and produces grant/deny decisions |
| Method Security (`@PreAuthorize`, ...) | Checks permissions at method invocation boundaries |
| `AccessDeniedException` | Signal that access was denied |
| `ExceptionTranslationFilter` | Routes security exceptions to the authentication-request flow or the access-denied flow |
| `AuthenticationEntryPoint` | Initiates an authentication mechanism when authentication state is missing or insufficient |
| `AccessDeniedHandler` | Builds the response for access-denial cases that should return 403 |

## 2. Processing Flow and the Meaning of 401/403

A typical flow for an HTTP request:

```text
GET /reports
    |
    v
SecurityFilterChain
    |
    +--> Authentication filters: read credentials, set Authentication
    |
    +--> AuthorizationFilter / AuthorizationManager
               |
               +--> Sufficient permissions --> continue to controller
               |
               +--> Denied: AccessDeniedException
                            |
                            v
                  ExceptionTranslationFilter
                            |
              +-------------+----------------+
              |                              |
       Unauthenticated /               Sufficiently authenticated,
       needs more authentication       but missing permissions
              |                              |
      AuthenticationEntryPoint        AccessDeniedHandler
              |                              |
      401 or login redirect                 403
```

`ExceptionTranslationFilter` wraps the downstream part of the filter chain, catches security exceptions, and selects the handling path. For anonymous callers, or when the authentication state is not trusted enough per configuration, an `AccessDeniedException` can lead to `AuthenticationEntryPoint`. When authenticated but missing required authorities, it is delegated to `AccessDeniedHandler`.

| Scenario | Common Response | Handler |
| --- | --- | --- |
| No credentials sent, calling an API requiring login with HTTP Basic | `401 Unauthorized` and `WWW-Authenticate` | `AuthenticationEntryPoint` |
| Wrong password sent via HTTP Basic | `401 Unauthorized` | Authentication mechanism / entry point |
| Logged in as `VIEWER` but URL requires `ADMIN` | `403 Forbidden` | `AccessDeniedHandler` |
| Logged in as `ADMIN` and allowed | `200 OK` in the example | Controller |
| Form login unauthenticated, accessing a page requiring authentication | Usually redirects to the login page | Form login's entry point |
| POST missing CSRF token when CSRF protection is enabled | Usually 403, but the cause is CSRF | CSRF's `AccessDeniedException` handling mechanism |

**Do not conclude that every 403 is due to a missing role.** `CsrfFilter` can reject a POST for a missing/invalid token; reverse proxies, CORS, application code, or other layers can also produce denial responses. Diagnosis must be based on the actual filter and exception.

Nor should you write "every `AccessDeniedException` is 403": `ExceptionTranslationFilter` also checks authentication state before choosing the entry point or access-denied handler. An exception caught and handled earlier by the application will not necessarily reach Spring Security's handler.

## 3. The `AccessDeniedHandler` Contract

The Servlet interface declares the method:

```java
void handle(
    HttpServletRequest request,
    HttpServletResponse response,
    AccessDeniedException accessDeniedException
) throws IOException, ServletException;
```

The three arguments are, in order, the denied request, the response to return, and the security cause. From the exception, internal logs can be recorded after filtering sensitive details, but **never return `exception.getMessage()` verbatim to the client** because it may reveal resource names, permission structures, or internal details.

When uncustomized, Servlet Spring Security uses `AccessDeniedHandlerImpl` as a common default implementation: sending HTTP error 403. If `errorPage` is configured, it performs an **internal forward** to the error page; `SecurityContextHolder` remains populated during that request and the exception is stored under the request attribute `WebAttributes.ACCESS_DENIED_403`. `forward` is not the same as `redirect`: a redirect creates a new request and easily results in status 302 instead of 403 if designed carelessly.

Application-specific usage:

- REST API: keep HTTP 403 and return a short, consistent JSON body without leaking information.
- HTML UI: display an access-denied page via a controlled forward/renderer; preserve 403 semantics.
- OAuth2 Resource Server: respect Bearer standards, especially `WWW-Authenticate` and `insufficient_scope`; avoid arbitrarily overriding dedicated handlers.
- Multi-tenant systems: deciding which tenant may be accessed belongs in permission checks; the handler only formats the error and must not reveal whether a tenant or resource exists.

## 4. Spring Boot / Spring Security 6 Example — Runnable on Java 17+

Create a Spring Boot 3.x project using Java 17 or later, with dependencies `spring-boot-starter-web` and `spring-boot-starter-security`. In a Maven project you can run it with `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`). The example is a practice app with in-memory users; usernames and passwords are for local machines only.

Create `src/main/java/com/example/denied/SecurityDeniedDemoApplication.java`:

```java
package com.example.denied;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDeniedDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDeniedDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AccessDeniedHandler jsonAccessDeniedHandler)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                // Allow internal dispatch so the application renders standard errors.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers("/public").permitAll()
                .requestMatchers("/reports").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .exceptionHandling(errors ->
                errors.accessDeniedHandler(jsonAccessDeniedHandler)
            );
        return http.build();
    }

    @Bean
    AccessDeniedHandler jsonAccessDeniedHandler() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.getWriter().write(
                "{\"error\":\"access_denied\",\"message\":\"Forbidden\"}"
            );
        };
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}demo123").roles("VIEWER").build();
        UserDetails admin = User.withUsername("admin")
            .password("{noop}demo123").roles("ADMIN").build();
        return new InMemoryUserDetailsManager(viewer, admin);
    }

    @RestController
    static class ReportController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public ok";
        }

        @GetMapping("/reports")
        String reports() {
            return "reports ok";
        }
    }
}
```

**Why does the example separate responsibilities properly?**

1. `.requestMatchers("/reports").hasRole("ADMIN")` enforces the permission rule: `hasRole("ADMIN")` looks for the `ROLE_ADMIN` authority. This is where access is decided, not in the handler.
2. HTTP Basic clarifies the difference between anonymous and logged-in users. Not overriding the entry point lets Spring Security handle authentication challenges according to the Basic protocol.
3. `.exceptionHandling(...accessDeniedHandler(...))` only decides **how to respond** when access is denied and the processing flow selects `AccessDeniedHandler`.
4. The handler returns the proper 403, `Content-Type: application/json` header, stable error code, and generic message. It does not return stack traces, usernames, missing role lists, or resource details.
5. `.dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` allows the Servlet container's error dispatch flow to occur; this does not by itself allow users to access `/reports`.
6. `.anyRequest().denyAll()` closes undeclared paths, preventing accidental exposure of new resources. Add corresponding rules when adding valid endpoints.

**Example limitations:** `{noop}` stores plaintext passwords for easy local testing and **must not be used in production**; real deployments need a secure password encoder and an appropriate identity store. The example only tests GET and does not disable CSRF protection as a "quick fix" for 403 errors on POST.

### Running and Comparing HTTP Statuses

Start the application, then run each command:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/reports
curl -i -u viewer:demo123 http://localhost:8080/reports
curl -i -u admin:demo123 http://localhost:8080/reports
```

Expected output from the endpoints above (listing only the example's stable status/body; technical headers like `Date` may vary):

| Command | Status | Main body |
| --- | --- | --- |
| `GET /public` without credentials | 200 | `public ok` |
| `GET /reports` without credentials | 401 | Body depends on entry point; has `WWW-Authenticate: Basic ...` challenge |
| `GET /reports` with `viewer` | 403 | `{"error":"access_denied","message":"Forbidden"}` |
| `GET /reports` with `admin` | 200 | `reports ok` |

Note: **401 unauthenticated** goes through the authentication-request mechanism; **403 authenticated without `ROLE_ADMIN`** goes through the custom `AccessDeniedHandler`. Changing the handler does not make `viewer` an `admin` and must not let the controller execute after denial.

## 5. HTML Error Pages and Safe Forwarding

When an application has HTML views and wants to use the built-in handler:

```java
@Bean
AccessDeniedHandler htmlAccessDeniedHandler() {
    AccessDeniedHandlerImpl handler = new AccessDeniedHandlerImpl();
    handler.setErrorPage("/access-denied");
    return handler;
}
```

This snippet is a **configuration fragment**, not a standalone Java file: import `org.springframework.security.web.access.AccessDeniedHandlerImpl` and register the handler in `exceptionHandling` like the previous example. The `/access-denied` path must have a valid controller/view and sufficient access permissions for `FORWARD` dispatch if authorization filters that dispatch type. Verify that the application still returns HTTP 403 and does not enter an error loop.

A redirect such as `response.sendRedirect("/login")` inside the handler is usually wrong for the **authenticated but lacking permissions** case: it causes confusion with 401, easily creates redirect loops, and can turn a denied response into 302. If product design genuinely requires a page transition, carefully evaluate browser and API semantics; do not use redirects to mask access denial.

## 6. Common Security and Integration Mistakes

### Mistake A — Checking Permissions in the Handler

**Wrong mindset:** "Inside `AccessDeniedHandler`, check roles and let the request proceed if it passes." The handler is called **after** the denial decision has occurred; at this point you should not replace `AuthorizationManager`, mutate `SecurityContext`, or invoke the controller. Actual rules must live in `authorizeHttpRequests`, method security, or business-layer access checks, especially when permissions depend on resource ownership.

**Right:** configure appropriate `hasRole`, `hasAuthority`, or authorization manager rules; the handler only writes the denial response.

### Mistake B — Always Returning 403 for All Login Errors

**Wrong:** assigning a single 403 JSON page for missing credentials, wrong passwords, and missing roles alike. HTTP clients may mistakenly think the user authenticated successfully. With HTTP Basic/Bearer, authentication errors also need protocol challenge headers.

**Right:** let `AuthenticationEntryPoint` handle missing or invalid authentication flows; only customize `AccessDeniedHandler` for corresponding access-denial cases. In form-login apps, the entry point may return a redirect instead of 401.

### Mistake C — Returning `200 OK` with `{"success":false}`

HTTP status 200 can cause frontends, caches, API gateways, or monitoring tools to treat the request as successful even when the body says failure. You must return status 403 at the HTTP level, using the body only to supplement clear details.

### Mistake D — Leaking Data in Error Responses

Do not concatenate `accessDeniedException.getMessage()`, `Authentication`, the full role list, tenant names, file paths, stack traces, or query data directly into the response. An unauthorized user should not be able to use errors to probe identities or resource existence. Use generic error codes; if diagnostic info is needed, log internally while stripping tokens, passwords, and personal data.

### Mistake E — Writing the Response Twice or Continuing the Filter Chain

After setting the status and writing the body, the handler must return. Do not call `filterChain.doFilter` after denial; nor call `sendError` after the body is committed, or attempt to forward/redirect once the response is committed. Such actions can cause exceptions, corrupted bodies, or resource leaks.

### Mistake F — Assuming "Every 403 Is Missing Permissions"

If POST/PUT/DELETE returns 403 while GET succeeds, check CSRF before changing roles. When CSRF is enabled, `CsrfFilter` can invoke the access-denied handler for an invalid token. Do not disable CSRF just to turn 403 into 200; configure token delivery and verification properly for your client type and cookie/session state.

If the browser hits a CORS error before seeing a 403 response, check CORS/preflight separately. Error codes in the Network tab can also come from a reverse proxy or another filter, not necessarily from the handler.

### Mistake G — Wrong `ROLE_` Authority and Rule Ordering

`hasRole("ADMIN")` maps by default to `ROLE_ADMIN`, whereas `hasAuthority("ADMIN")` checks the exact string `ADMIN`. Confusing these two often causes 403 even when the user appears to have the role. Additionally, matchers are evaluated in order; a broad rule placed first can shadow a specific rule.

### Mistake H — Forgetting OAuth2 Bearer Characteristics

For Resource Server, Spring Security provides `BearerTokenAccessDeniedHandler` to produce RFC 6750-compliant responses; when a token is valid but lacks scope, the `WWW-Authenticate` header can indicate `insufficient_scope`. Replacing the entire handler with an arbitrary JSON handler can strip protocol metadata that clients expect. When custom bodies are needed, preserve status/headers/protocol behavior and test invalid tokens, expired tokens, and valid tokens lacking scopes.

### Mistake I — Catching Exceptions Too Early or Mixing Up Stacks

A `@ControllerAdvice` catching `AccessDeniedException` and turning it into 200/500 can lose 403 semantics and bypass the filter handler as expected. Exceptions occurring outside the scope wrapped by `ExceptionTranslationFilter` (such as independent async tasks) do not automatically pass through it either. Spring WebFlux uses `ServerAccessDeniedHandler` and reactive web filters; the Servlet example above does not apply directly to WebFlux.

## 7. Testing Behavior Rather Than Just Reading Configuration

In the example above, minimal tests must prove all **three states**: anonymous 401, authenticated with insufficient permissions 403, authenticated with sufficient permissions 200. Also assert the JSON body on the 403 branch, `Content-Type`, and prove the controller is not executed when denied. When adding POST, write a separate CSRF test; when enabling OAuth2, add Bearer header tests.

If the project has `spring-security-test` and `spring-boot-starter-test`, you can create `src/test/java/com/example/denied/AccessDeniedBehaviorTest.java`:

```java
package com.example.denied;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessDeniedBehaviorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousMustAuthenticate() throws Exception {
        mvc.perform(get("/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerReceives403Json() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("viewer", "demo123")))
            .andExpect(status().isForbidden())
            .andExpect(content().json(
                "{\"error\":\"access_denied\",\"message\":\"Forbidden\"}"
            ));
    }

    @Test
    void adminCanReadReports() throws Exception {
        mvc.perform(get("/reports").with(httpBasic("admin", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports ok"));
    }
}
```

Run `./mvnw test` (Windows: `mvnw.cmd test`). All three tests must pass in the demo application and configuration. Do not test only the 403 code: if the handler returns valid JSON while the URL was accidentally opened in certain cases, an authorization vulnerability still exists.

When diagnosing in development, enable appropriate logging for `org.springframework.security` at DEBUG/TRACE briefly to inspect the security filter chain, the matcher actually applied, authentication state, and the `AccessDeniedException` cause. Never log tokens or credentials in production logs.

## 8. Practical Procedure for Handling a Real-World 403 Error

1. **Verify the request**: method, URL, which security filter chain applies, and whether the endpoint was rejected by a proxy/gateway before reaching the app.
2. **Verify authentication**: anonymous, HTTP Basic, session, or Bearer; is the user authenticated yet; is there a remember-me state or invalid credentials?
3. **Verify authorization**: matchers and their order, actual roles/authorities, tenant/resource-level permissions, method security if present. Do not infer permissions from whether the client hides/shows UI buttons.
4. **Verify the exception source**: `AuthorizationFilter`, method security, CSRF, or another application layer. Specifically distinguish 403 due to CSRF from 403 due to a missing role.
5. **Verify the response**: HTTP status, `Content-Type`, body, `WWW-Authenticate` if using Basic/Bearer, no leaked details, and no downstream processing after denial.
6. **Regression test**: anonymous, user lacking permissions, user with sufficient permissions; also cover state-changing requests and other tenants if applicable.

## 9. Things to Remember

- **Authorization decides whether to allow or deny; `AccessDeniedHandler` presents the denial result.**
- **401/entry point** typically relates to requiring authentication; **403/access-denied handler** typically means authenticated without permission. Actual status depends on the authentication mechanism and exception type.
- The handler must keep the response safe, leak no data, never turn 403 into 200, and never continue processing the resource after denying.
- Distinguish 403 caused by authorities, CSRF, dispatches, or external components before changing configuration.
- For Resource Server, preserve HTTP Bearer semantics; do not lose `WWW-Authenticate` just for a uniform JSON format.

## Official References

- Spring Security, Servlet Architecture — Handling Security Exceptions: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security, Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security, CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- `AccessDeniedHandlerImpl` Java API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandlerImpl.html
- Spring Security, OAuth2 Bearer Token Failure: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html