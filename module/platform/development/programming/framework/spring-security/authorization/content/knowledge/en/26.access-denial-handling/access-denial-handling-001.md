# Distinguishing Unauthenticated, Insufficient Permissions, and Non-Existent Resources in Spring Security

In a Spring Security application using **Servlet/Spring MVC**, three commonly confused outcomes are **401 Unauthorized**, **403 Forbidden**, and **404 Not Found**. They reflect three different questions: *has the caller proven their identity?*, *is the caller permitted to perform the operation?*, and *does the requested path or object exist (or is its existence allowed to be disclosed)?* It is necessary to distinguish them before designing APIs, handling exceptions, and writing tests.

## 1. Decision Table

| Case | Commonly Used HTTP Status | Meaning to the Client | Where It Can Be Decided |
| --- | --- | --- | --- |
| Missing credentials or invalid/expired credentials | **401 Unauthorized** | Need to provide or refresh credentials | Authentication filter, `AuthenticationEntryPoint` |
| Authenticated but lacks permission for this operation | **403 Forbidden** | Change permissions/policies; logging in again with the same permissions usually does not help | `AuthorizationFilter`, method security, `AccessDeniedHandler` |
| Unmapped path or requested record does not exist | **404 Not Found** | No matching resource to return | Spring MVC routing, controller/service |
| Object exists, but policy requires hiding its existence from unauthorized users | **404 Not Found** *by design* | Cannot infer whether the object exists | Application-layer security policy |

**401 does not mean "logged in but lacking permission"**, despite the English name `Unauthorized`. This is a **lack of valid authentication** error. According to HTTP, a 401 response includes at least one challenge in the `WWW-Authenticate` header, for example `Basic` or `Bearer`. **403** is a request refusal; in a normal authorization check flow, the caller is authenticated but lacks permission. However, 403 can also be caused by CSRF or other protection policies, so you cannot diagnose a "missing role" solely from a 403 status code. **404** is not a default Spring Security authorization exception.

## 2. Why Can the Same URL Return Different Codes?

The simplified processing flow:

~~~text
HTTP request
  |
  v
Spring Security FilterChainProxy
  |-- Authentication: cookie/session, HTTP Basic, Bearer token...
  |-- URL Authorization: AuthorizationFilter
  |     |-- unauthenticated -> AuthenticationEntryPoint -> usually 401
  |     |-- authenticated, insufficient permissions -> AccessDeniedHandler -> usually 403
  |     '-- allowed -> continue filter chain
  v
DispatcherServlet / HandlerMapping
  |-- no matching route -> 404
  v
Controller -> Service -> Repository
  |-- object not found -> 404
  |-- object-level permission violation -> 403 or 404 depending on policy
  '-- valid -> 2xx
~~~

`ExceptionTranslationFilter` translates `AuthenticationException` or `AccessDeniedException` thrown downstream of it into appropriate HTTP behavior. For `AuthenticationException`, or `AccessDeniedException` when the caller is considered anonymous/remember-me and not sufficiently authenticated, it invokes `AuthenticationEntryPoint`. For a fully authenticated caller that still receives an `AccessDeniedException`, it calls `AccessDeniedHandler`. Some authentication filters handle their own authentication failures before an exception reaches this filter. Therefore, **you should not assume that every 401 goes through the same exception handler**.

`AuthenticationEntryPoint` depends on the authentication mechanism: a REST API using HTTP Basic usually responds with `401` and `WWW-Authenticate: Basic ...`; an OAuth2 Resource Server usually uses a Bearer challenge; an application using form login may redirect `302` to the login page. Thus, you must not assert that "every unauthenticated request is always 401" without inspecting the actual configuration.

**Order matters greatly.** If a rule protecting `/api/reports/**` blocks the request before Spring MVC looks up the route or data, an actually non-existent URL can still return `401` or `403`. Only when the request reaches the layer that determines existence does it have a chance to return `404`.

## 3. Spring Boot Example: Observing 401, 403, 404 on the Same Endpoint

The example uses **Java 17+, Spring Boot 3.x/Spring Security 6.x**, Servlet/MVC API, HTTP Basic, and two in-memory users. In a Spring Boot project that already has Maven/Gradle, add the `spring-boot-starter-web` and `spring-boot-starter-security` dependencies. The test section additionally uses `spring-boot-starter-test` and `spring-security-test`. The files below are complete example code in package `com.example.demo`; `{noop}` passwords are for demo purposes only, **do not use in production**.

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/demo/ApiSecurityConfig.java`**

~~~java
package com.example.demo;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("REPORT_READ")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader123")
                .authorities("REPORT_READ")
                .build(),
            User.withUsername("guest")
                .password("{noop}guest123")
                .authorities("OTHER")
                .build()
        );
    }
}
~~~

The rule `GET /api/reports/**` requires the exact authority `REPORT_READ`. User `guest` authenticates successfully but only has `OTHER`, so the request is denied. Configuring `DispatcherType.ERROR` allows Spring Boot to forward to the error handler without accidentally turning a 404 error into a new authorization denial; in a real application, you must review dispatcher rules in accordance with the entire system.

**`src/main/java/com/example/demo/ReportController.java`**

~~~java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    @GetMapping("/{id}")
    public Report get(@PathVariable long id) {
        if (id != 42L) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Report not found");
        }
        return new Report(42L, "Quarterly");
    }

    public record Report(long id, String title) {}
}
~~~

Assuming the application runs on `localhost:8080` (`mvn spring-boot:run` in a Spring Boot-configured Maven project), run the following commands in a shell that supports `curl`:

~~~bash
# Missing credentials -> 401
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/reports/42

# Valid identity but wrong permissions -> 403
curl -s -o /dev/null -w '%{http_code}\n' -u guest:guest123 \
  http://localhost:8080/api/reports/42

# Correct permissions, record does not exist -> 404
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 \
  http://localhost:8080/api/reports/99

# Correct permissions and record exists -> 200
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 \
  http://localhost:8080/api/reports/42
~~~

**Expected stdout** (each command prints one line; excluding HTTP body):

~~~text
401
403
404
200
~~~

For a successful request, the endpoint returns JSON `{"id":42,"title":"Quarterly"}`. If you omit credentials when calling `/api/reports/99`, the result is **401 before the controller checks `id`**; `99` must not be used as evidence that the API should return 404 for every caller.

## 4. 401: Handling Authentication Requirements

- **Not logged in / missing credentials**: for endpoints requiring an identity, enter the authentication challenge mechanism. HTTP Basic APIs typically use `WWW-Authenticate: Basic realm="..."`; Bearer APIs use `WWW-Authenticate: Bearer`.
- **Wrong or expired password/token**: authentication fails; for Bearer tokens, an `invalid_token` error is usually 401. The client can request a new token or prompt the user to log in, depending on the mechanism.
- **Do not emit 403 just because a token was rejected**: if identity has not been proven, you cannot conclude that the caller is authenticated but lacks permissions.
- **Do not send sensitive details**: return a stable error code, generic message, and request id in the body; avoid disclosing whether a username exists.

Example Bearer response following HTTP/OAuth principles (actual attributes depend on configuration and error type):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

When customizing an API, `AuthenticationEntryPoint` is the starting point for authentication. Do not replace `BearerTokenAuthenticationEntryPoint` with a simple JSON handler that drops the standard challenge if OAuth2 clients depend on `WWW-Authenticate`.

## 5. 403: Handling Authenticated but Denied Requests

- **URL-based permissions**: `requestMatchers(...).hasAuthority("REPORT_READ")` or `hasRole("ADMIN")`.
- **Method-based permissions**: `@PreAuthorize("hasAuthority('REPORT_READ')")` and method security rules when `@EnableMethodSecurity` is enabled.
- **Object-based permissions**: a user can read reports in general, but does not have permission for a specific `reportId`. This decision must be based on the current user and object data, not just the URL.
- **Other reasons**: a missing/invalid CSRF token on state-changing requests can cause 403. When seeing 403 on POST/PUT/DELETE, check the CSRF configuration as well instead of checking only roles.

Distinguish `hasRole("ADMIN")` (typically checks the `ROLE_ADMIN` authority) from `hasAuthority("ADMIN")` (exact match on the string `ADMIN`). A default JWT Resource Server typically maps scopes to authorities with the `SCOPE_` prefix; a token with `scope=report.read` does not automatically have `REPORT_READ` without a converter. Therefore, **a valid token with mismatched authority mapping still returns 403**.

`AccessDeniedHandler` handles denials at the Spring Security layer. `@RestControllerAdvice` normally only participates in exceptions within the MVC layer; it should not be used as the sole place to catch errors blocked by filters before reaching the controller.

For OAuth2 Bearer, a valid token with insufficient scopes may return:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

This is an authorization error, unlike `invalid_token` for 401.

## 6. 404: Non-Existent Resources and Hiding Policies

404 occurs when no matching route is found after passing through the required filters, or when looking up by `id` finds no record. In a controller/service, you can use `ResponseStatusException(HttpStatus.NOT_FOUND)` (as in the example), `ResponseEntity.notFound().build()`, or a domain exception explicitly mapped to 404.

**Do not conflate "not allowed to view" with "does not exist".** Define your API policy clearly:

1. For resources whose existence may be disclosed, return **403** when the object exists but the user lacks permission; return **404** when it is genuinely not found. Users and operations teams can distinguish permission errors from data errors.
2. For private resources (e.g., profiles, files belonging to another tenant), you can intentionally return **404** for both "does not exist" and "not allowed to see" to prevent ID enumeration. Maintain consistency across list queries, detail queries, and error messages.
3. Enforce ownership/tenant checks **on the backend**. For example, have the repository query using both the object key and the currently logged-in user/tenant; if no matching record is found, return 404, and do not allow the client to arbitrarily pass another user's tenant.

An illustrative query expression (table/column names depend on schema):

~~~sql
SELECT id, title
FROM report
WHERE id = :reportId AND owner_id = :currentUserId;
~~~

Returning 404 on an empty result can cover both non-existent IDs and IDs belonging to another owner. This approach is **only appropriate if that is the chosen policy**; for systems that require clear reporting of missing permissions, decide 403 in the authorization layer after verifying the object. Regardless of the choice, internal logs must record the actual reason and avoid leaking sensitive data in the response.

**Note:** A non-existent route is not guaranteed to return 404 immediately. If `anyRequest().denyAll()` blocks all unknown requests, the result may be 401/403 before `DispatcherServlet`. Do not relax security rules just to force every unknown URL to return 404.

## 7. Testing Status, Permissions, and Existence Together

When a project has `spring-boot-starter-test` and `spring-security-test`, integration tests can be written with `MockMvc`:

**`src/test/java/com/example/demo/ReportSecurityTests.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsReturns401() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidCredentialsReturn401() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutPermissionReturns403() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("guest", "guest123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void permittedUserWithMissingReportGets404() throws Exception {
        mvc.perform(get("/api/reports/99")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void permittedUserWithExistingReportGets200() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

Run `mvn test` in the Maven project. `httpBasic(...)` sends an actual Basic header to test the authentication flow; `@WithMockUser` is useful for testing authorization but does not verify real password authentication. When testing Bearer APIs, substitute requests with an appropriate Bearer token/`jwt()` and check the `WWW-Authenticate` header along with scopes/authorities.

## 8. Debugging Checklist When Returned Status Differs from Expectations

1. **Is there a real user or only anonymous?** Check the authentication provider, session, bearer expiration, and `SecurityContext`, and do not log credentials/tokens.
2. **Which URL rule matches first?** Inspect `SecurityFilterChain` and `requestMatchers` ordering; check for other chains, `securityMatcher`, or `anyRequest().denyAll()`.
3. **What actual authorities does the user have?** Compare exact `ROLE_`, `SCOPE_`, permission names, and method/object-level rules.
4. **Did the request reach the controller?** If it has not reached MVC, do not expect a controller's `@ExceptionHandler` to produce 404.
5. **Is CSRF or ERROR dispatch involved?** Especially when POST returns 403 or the original error is changed into 401/403 during `/error` processing.
6. **Is 404 truly not found or caused by an object-hiding policy?** Verify repository/tenant checks with safe logging and write dedicated tests for cross-tenant cases.
7. **Does the response preserve proper semantics?** 401 must include the corresponding authentication challenge; 403 must not tell the client to keep refreshing its token; 404 must not accidentally leak private objects.

In production implementations, define all three scenarios consistently in the API contract, standardize the error body structure (Problem Details can be used), use the appropriate `AuthenticationEntryPoint`/`AccessDeniedHandler`, and map domain errors to 404 in the MVC/service layer. Always include tests for anonymous, authenticated without permissions, authenticated with permissions but non-existent ID, and successful access.

## Official References

- [Spring Security — Servlet Architecture, Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html)
- [Spring Security — OAuth2 Bearer Token Failure](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
