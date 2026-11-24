# Distinguishing AuthenticationException from AccessDeniedException in Spring Security Servlet

> **Scope:** Spring Security **Servlet stack**, Java 17+, Spring Boot 3.x, Spring Security 6.x. Focus: the two exception families `AuthenticationException` and `AccessDeniedException`, where they originate in the authentication/authorization pipeline, how `ExceptionTranslationFilter` decides to invoke `AuthenticationEntryPoint` or `AccessDeniedHandler`, the distinct role of `AuthenticationFailureHandler`, HTTP 401/403/302, CSRF handling, and method security. The Spring examples require a Boot project with full dependencies; at the end of the lesson is a standalone Java 17 program compiled with `javac` with exact stdout.

## 1. Why Can the Same API Return 401 or 403?

Consider requests to a system where `/private` only requires login, `/admin` requires `ROLE_ADMIN`, and `POST /admin/update` must pass CSRF protection:

1. Client calls `GET /private` without sending credentials.
2. Client sends HTTP Basic with the wrong password.
3. User `bob` logs in validly but only has `ROLE_USER`, and calls `GET /admin`.
4. User `admin` has `ROLE_ADMIN`, but sends `POST /admin/update` without a valid CSRF token.
5. User `admin` sends valid credentials and token, and calls an allowed endpoint.

A commonly observed table in an HTTP Basic API:

| Scenario | Failure point | Common status |
| --- | --- | --- |
| No valid authentication yet | Authentication required | 401 and `WWW-Authenticate`. |
| Wrong username/password | Authentication provider/filter | 401. |
| Logged in but missing role | Authorization manager/filter | 403. |
| Has role but POST lacks CSRF | `CsrfFilter` | 403. |
| Logged in, has role, valid CSRF | Let request through | 200 if controller succeeds. |

**Two 403s do not prove the same root cause.** Case 3 is insufficient access privileges, whereas case 4 is a CSRF check failure before the controller runs. Therefore, you must distinguish *authentication failures*, *authorization failures*, and *other errors returned by the security pipeline*, rather than looking only at the HTTP status code.

## 2. Core Definitions

- **Authentication:** proving identity or the trustworthiness of the current credentials. Related components include `AuthenticationManager`, `AuthenticationProvider`, `UserDetailsService`, credential validators, and authentication filters.
- **Authorization:** deciding whether an already-recognized identity is permitted to perform an action on a URL/method/object. Related components include `AuthorizationManager`, `AuthorizationFilter`, `@PreAuthorize`, `GrantedAuthority`, and resource-level policies.
- **Exception translation:** converting a security exception into concrete HTTP behavior (requesting login, returning a status, redirecting, or returning a body). The key component is `ExceptionTranslationFilter` along with the corresponding handlers/entry points.

In Spring Security:

~~~java
// This is a class-level description, not a re-creation of library classes.
org.springframework.security.core.AuthenticationException
        extends RuntimeException

org.springframework.security.access.AccessDeniedException
        extends RuntimeException
~~~

These two exception types **do not inherit from each other**. Both are unchecked exceptions, but they carry different semantics. Do not use `BadCredentialsException` to describe a user who authenticated properly but lacks permission to view data.

### Comparison Table

| Aspect | AuthenticationException | AccessDeniedException |
| --- | --- | --- |
| Nature | Authentication failed or is insufficient. | Access policy denies the request/action. |
| Package | `org.springframework.security.core` | `org.springframework.security.access` |
| Examples | `BadCredentialsException`, `DisabledException`, `LockedException`, `InsufficientAuthenticationException`. | Denial on `hasRole`/`hasAuthority`; method security denial; related CSRF exceptions. |
| Always a wrong password? | No. | Not directly related to password comparison. |
| Common HTTP handling | Entry point or login failure handler. | Access denied handler, or entry point if user is not sufficiently authenticated. |
| Invariant HTTP status? | No: could be 401 or 302 redirect, etc. | No: could be 403, or 401/302 if routed to authentication. |
| Automatically return raw exception message? | Not recommended. | Not recommended. |

A public error response should say just enough for the client to handle, without leaking credentials, sensitive policy/role names, or information that aids username enumeration.

## 3. Types of AuthenticationException and Their Meanings

| Common subclass | Scenario | Things to remember |
| --- | --- | --- |
| `BadCredentialsException` | Wrong credential. | Never put passwords in logs or response bodies returned to clients. |
| `UsernameNotFoundException` | `UserDetailsService` did not find the user. | `DaoAuthenticationProvider` often masks it as `BadCredentialsException` to reduce account existence disclosure. |
| `DisabledException` | Account is disabled. | Do not automatically re-enable the account when the failure handler runs. |
| `LockedException` | Account is locked. | Recovery UX must follow product policy. |
| `AccountExpiredException` | Account has expired. | Distinct from password/token expiration. |
| `CredentialsExpiredException` | Credential is no longer valid. | May require a credential-change flow. |
| `AuthenticationServiceException` | Certain authentication service errors. | Distinguish infrastructure incidents from wrong credentials in internal metrics. |
| `InsufficientAuthenticationException` | Authentication has not reached the trust level required by policy. | Not necessarily due to a wrong password. |
| `AuthenticationCredentialsNotFoundException` | Required authentication is missing at the protected point. | Can occur in method security. |

Authentication failure can also involve invalid/expired bearer tokens or step-up/MFA requirements. Do not define authentication solely as username/password. A valid non-expired token with insufficient scope is an authorization issue; a token with a forged signature or expired timestamp generally belongs to the authentication branch.

### Why BadCredentialsException Is Not for Missing Roles

~~~java
// CODE SNIPPET used inside a custom AuthenticationProvider:
if (!passwordEncoder.matches(rawPassword, storedPasswordHash)) {
    throw new BadCredentialsException("Invalid credentials");
}
~~~

Here `BadCredentialsException` is appropriate because credential verification failed. This code is a fragment and will not compile standalone without `passwordEncoder`, `rawPassword`, `storedPasswordHash`, and proper imports. In production, you must have brute-force protection, timing protection, strong password hashing, and safe logging.

~~~java
// ANTI-PATTERN: do not do this when permissions are missing.
if (!principalHasRoleAdmin) {
    throw new BadCredentialsException("Not an admin");
}
~~~

The second snippet is **semantically wrong**: a valid user may simply lack the admin role. Throwing the wrong exception pollutes authentication metrics, forces the frontend to prompt for login needlessly, and fails to reflect an authorization denial accurately.

## 4. AccessDeniedException Scenarios

Example in `authorizeHttpRequests`:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated());
~~~

User `bob` with `ROLE_USER` but lacking `ROLE_ADMIN` will be denied by authorization when calling `/admin/**`. When policy uses the standard Spring Security authorization manager, the exception branch can be `AccessDeniedException` or a subclass carrying the corresponding authorization result. Newer Spring Security 6.x releases include `AuthorizationDeniedException`, though constructors/APIs may vary by minor release; this example does not instantiate it directly.

In method security:

~~~java
@PreAuthorize("hasAuthority('REPORT_EXPORT')")
public String exportReport() {
    return "report-data";
}
~~~

If the method is invoked through a Spring-managed proxy and the user lacks `REPORT_EXPORT`, denial occurs **at the service layer** even though outer URL rules may allow authenticated users through. Thus, an `AccessDeniedException` is not necessarily generated by the HTTP `AuthorizationFilter`.

### CSRF Is Related to but Distinct from Role Permissions

`MissingCsrfTokenException` and `InvalidCsrfTokenException` belong to the CSRF exception group related to `AccessDeniedException`, but `CsrfFilter` typically has its own `AccessDeniedHandler` and can return 403 right at that filter.

~~~text
POST /admin/update
Authenticated user: admin
Authorities: [ROLE_ADMIN]
CSRF token: missing
CsrfFilter: reject
HTTP: 403
~~~

Do not conclude that `hasRole("ADMIN")` rejected the request; the request may **never have reached** `AuthorizationFilter`. In HTTP POST tests, to prove that the role check works, send a valid CSRF token, such as `.with(csrf())` in `MockMvc`.

### AccessDeniedException Can Also Be an Object-Level Error

A service checking order/document ownership or tenant boundaries may throw a denied exception if the principal has general read permission but does not own the requested record. You must check **server-side data** and do so before any side effects, never trusting an owner ID or role sent by the client. A policy that returns 404 instead of 403 to avoid disclosing resource existence requires consistent design and must never accidentally leak unauthorized data.

## 5. ExceptionTranslationFilter: The Heart of Translating Exceptions into Responses

`ExceptionTranslationFilter` is a bridge between security exceptions and the HTTP protocol. It **does not verify passwords** and **does not grant authorities**. It wraps part of the downstream filter chain, catches security exceptions bubbling up, and decides which entry point or handler to invoke.

~~~text
ExceptionTranslationFilter
    |
    v
chain.doFilter(request, response)
    |
    +-- AuthenticationException from downstream
    |       -> requires authentication
    |       -> AuthenticationEntryPoint
    |       -> 401 / redirect / scheme-specific response
    |
    +-- AccessDeniedException from downstream
    |       |
    |       +-- Anonymous or insufficient remember-me level
    |       |       -> starts authentication
    |       |       -> AuthenticationEntryPoint
    |       |
    |       +-- Sufficiently authenticated per trust resolver
    |               -> AccessDeniedHandler
    |               -> typically 403
    |
    +-- Exception outside these two families
            -> not automatically translated to 401/403
               by security exception logic
~~~

### Important Case: Denied, Yet the Client Receives 401/302

An **anonymous** request can reach `AuthorizationFilter`, where the manager sees the policy requires an authenticated user and throws `AccessDeniedException`. `ExceptionTranslationFilter` uses `AuthenticationTrustResolver` to recognize that the anonymous/remember-me user does not yet have an adequate authentication level, so it initiates authentication via `AuthenticationEntryPoint` **instead of** returning forbidden immediately.

- HTTP Basic API: typically 401 and header `WWW-Authenticate: Basic ...`.
- Form login: typically 302 redirect to `/login`.
- Bearer resource server: token-appropriate entry point, which may return 401 with a Bearer challenge.

Thus, **`AccessDeniedException` does not guarantee HTTP 403**. An unauthenticated request can trigger an authorization denial while the HTTP response still means "please authenticate".

### AnonymousAuthenticationToken Is Not Equal to a Logged-In User

`AnonymousAuthenticationFilter` may place an `AnonymousAuthenticationToken` into the `SecurityContext`. That token may return `isAuthenticated()` as `true` depending on implementation, yet Spring Security uses a trust resolver to distinguish anonymous users from users authenticated according to policy. Do not look only at that boolean and assume every denial routes to the 403 branch.

### Remember-Me Is Not Always Enough for Sensitive Operations

A user with remember-me authentication may require a full login or step-up authentication under certain policies. When a denial occurs, the entry point can be used to request re-authentication; this does not mean the user just entered a wrong password.

### SecurityContext and RequestCache

When starting authentication, `ExceptionTranslationFilter` may clear the context per the flow, save the `SavedRequest` via `RequestCache`, and trigger the entry point. For form-login apps, `SavedRequest` helps redirect back to the page the user originally tried to access after login; for stateless APIs, you typically need a different request cache policy or no session storage. Do not assume default session-saving behavior for every chain.

## 6. Why ExceptionTranslationFilter Does Not Catch Every Login Error

An authentication filter can sit **in front of `ExceptionTranslationFilter`** in the standard Servlet filter chain and have its own failure flow:

- `UsernamePasswordAuthenticationFilter` extends `AbstractAuthenticationProcessingFilter`. When username/password is invalid, it normally calls `AuthenticationFailureHandler`, for example redirecting to `/login?error`.
- `BasicAuthenticationFilter` has its own failure handling and uses the configured `AuthenticationEntryPoint` for HTTP Basic.
- A bearer token authentication filter has error handling appropriate for the resource server/Bearer scheme.

Therefore, you cannot customize only `ExceptionTranslationFilter` and assume every form-login password failure will pass through it. Identify **which filter handles the request**, **whether that filter catches the exception**, and **which handler actually produces the response**.

### Three Commonly Confused Components

| Component | When it is used |
| --- | --- |
| `AuthenticationFailureHandler` | When **a specific login attempt** fails inside an authentication filter (especially form login). |
| `AuthenticationEntryPoint` | When authentication needs to be **initiated/requested** for a request lacking sufficient credentials; can also be used by authentication filters. |
| `AccessDeniedHandler` | When policy denies a user who is already sufficiently authenticated per the flow. |

A web app may use all three: `POST /login` wrong password → failure handler; `GET /private` anonymous → entry point; `GET /admin` with a user lacking the role → denied handler. They differ in where they originate and what UX is expected.

## 7. 401, 403, and 302 Do Not Have a 1-to-1 Mapping with Exceptions

### 401 Unauthorized

By HTTP semantics, 401 typically indicates the request lacks valid authentication credentials. With HTTP Basic, the response may include:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
~~~

With Bearer, the scheme/header differs. Do not send a Basic 401 without an appropriate challenge when the client needs to authenticate according to protocol.

### 403 Forbidden

403 typically indicates the server refuses to fulfill the request:

~~~http
HTTP/1.1 403 Forbidden
~~~

An authenticated user lacking permissions is the classic case, **not the only one**. CSRF, a gateway/WAF, a controller, or a resource policy can also return 403.

### 302 Redirect

With form login:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Anonymous protected requests are usually sent to the login page, while failed `POST` logins are usually routed by the failure handler to `/login?error`. Do not treat every redirect as successful authentication, and do not assume form-login denial must always be 401.

### Matrix to Remember

| Actual cause | Typical HTTP Basic | Typical Form login |
| --- | --- | --- |
| Calling private without credentials | 401 | 302 login. |
| Wrong credentials | 401 | 302 login?error. |
| Authenticated user missing role | 403 | 403. |
| POST missing CSRF token | 403 | 403. |
| Valid credentials, sufficient permissions | Controller-dependent, usually 200 | Controller-dependent, usually 200. |

These values are **typical**, not a guarantee for every project: a custom entry point/handler, multiple chains, or an API framework can change the response.

## 8. Spring Boot 3 and Java 17 Example: HTTP Basic API

This example uses HTTP Basic to distinguish anonymous requests, wrong credentials, and missing roles without needing cookies or a browser. CSRF remains enabled by default to illustrate that **a 403 from CSRF is not a 403 from a role**. Method security is enabled to demonstrate denial at the service layer.

### Dependencies and Structure

Create a Java 17+ Spring Boot 3.x project with:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-aop       (highlights method proxy mechanism)
spring-boot-starter-test      (test scope)
spring-security-test         (test scope)
~~~

Place the code in the same package `com.example.exceptionlesson`:

~~~text
src/main/java/com/example/exceptionlesson/
  ExceptionLessonApplication.java
  SecurityConfig.java
  ReportService.java
  DemoController.java

src/test/java/com/example/exceptionlesson/
  SecurityExceptionIntegrationTest.java
~~~

**Note:** Spring Boot 3.x is compatible with specific Spring Security 6.x minor versions managed by the BOM. Do not upgrade an individual Security artifact independently without checking compatibility. This demo uses no database and no real passwords.

### 8.1. SecurityConfig.java

~~~java
package com.example.exceptionlesson;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-demo-only"))
                .authorities("ROLE_ADMIN", "REPORT_EXPORT")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("bob-demo-only"))
                .authorities("ROLE_USER")
                .build();

        return new InMemoryUserDetailsManager(admin, bob);
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/admin/update")
                    .hasRole("ADMIN")

                // HTTP: only requires authenticated.
                // Service: must have REPORT_EXPORT.
                .requestMatchers(HttpMethod.GET, "/reports/export")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // Keep CSRF enabled so the demo accurately demonstrates 403 from token.
        return http.build();
    }
}
~~~

The rules:

1. `/public` is public.
2. `GET /private` requires authentication but does not require the admin role.
3. `GET /admin` and `POST /admin/update` require the `ROLE_ADMIN` authority via `hasRole("ADMIN")`.
4. `GET /reports/export` requires login at the HTTP layer, after which `@PreAuthorize` on the service checks `REPORT_EXPORT`.
5. `anyRequest().denyAll()` protects undeclared routes/methods.
6. `httpBasic(...)` lets tests send Basic credentials directly. Do not use Basic over plaintext HTTP in production; use TLS and protect credentials.
7. `BCryptPasswordEncoder` is suitable for demo passwords; the strings `admin-demo-only` and `bob-demo-only` are test accounts only—never put them in real environments.

### 8.2. ReportService.java

~~~java
package com.example.exceptionlesson;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_EXPORT')")
    public String export() {
        return "report-data";
    }
}
~~~

Calls must go through the Spring-managed bean/proxy for method security to apply. If you instantiate `new ReportService()` yourself or self-invoke within the same bean, AOP method advice may not run. Do not use `@PreAuthorize` as a substitute for record-level owner/tenant checks in business services.

### 8.3. DemoController.java

~~~java
package com.example.exceptionlesson;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final ReportService reports;

    public DemoController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "hello:" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }

    @PostMapping("/admin/update")
    public String updateAdmin() {
        // Demo only returns a string, does not modify DB.
        return "updated";
    }

    @GetMapping("/reports/export")
    public String export() {
        return reports.export();
    }
}
~~~

### 8.4. ExceptionLessonApplication.java

~~~java
package com.example.exceptionlesson;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionLessonApplication.class, args);
    }
}
~~~

With the project's Maven Wrapper, run:

~~~bash
./mvnw spring-boot:run
~~~

You can test directly with curl (only on localhost with dummy credentials):

~~~bash
# Public:
curl -i http://localhost:8080/public

# Anonymous requiring authentication:
curl -i http://localhost:8080/private

# Valid Bob but lacking admin role:
curl -i -u bob:bob-demo-only \
  http://localhost:8080/admin

# Valid Admin:
curl -i -u admin:admin-demo-only \
  http://localhost:8080/admin
~~~

According to the demo configuration, the corresponding logical statuses are 200, 401, 403, and 200. Never put real credentials on the command line (they can leak in shell history/process lists); the examples use local dummy users. Actual HTTP headers/bodies generated by the server also depend on version/container, so there is no fixed transcript.

## 9. MockMvc: Proving Both Authentication and Authorization

The following tests run through the `SecurityFilterChain`, not merely by calling mocked Java methods. With Spring Boot 3 and `spring-security-test`, create `src/test/java/com/example/exceptionlesson/SecurityExceptionIntegrationTest.java`:

~~~java
package com.example.exceptionlesson;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityExceptionIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointDoesNotNeedAuthentication()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousPrivateRequestGets401() throws Exception {
        mvc.perform(get("/private"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongPasswordGets401() throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("bob", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicAuthenticationCanAccessPrivate()
            throws Exception {
        mvc.perform(get("/private")
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:bob"));
    }

    @Test
    void validUserWithoutAdminAuthorityGets403()
            throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdminEndpoint() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void missingCsrfGives403DespiteHavingAdminRole()
            throws Exception {
        mvc.perform(post("/admin/update")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void missingRoleGives403AfterValidCsrf()
            throws Exception {
        mvc.perform(post("/admin/update")
                .with(csrf())
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithValidCsrfCanPost() throws Exception {
        mvc.perform(post("/admin/update")
                .with(csrf())
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }

    @Test
    void methodSecurityAlsoRaisesAuthorizationDenial()
            throws Exception {
        mvc.perform(get("/reports/export")
                .with(httpBasic("bob", "bob-demo-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/reports/export")
                .with(httpBasic("admin", "admin-demo-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-data"));
    }
}
~~~

**How to read the assertions:**

- Anonymous `GET /private` 401 and wrong password 401 are **two different causes** sharing the same status.
- Bob accessing `/private` with valid credentials proves the user actually authenticated.
- Bob lacking `ROLE_ADMIN` on `GET /admin` results in a 403 denial.
- Admin with sufficient role accesses `GET /admin` and gets 200.
- Admin `POST` missing CSRF gets 403 despite having the right role. This test does **not** verify `hasRole`.
- Bob `POST` with valid `csrf()` but missing role also gets 403: the CSRF condition does not mask the authorization result.
- Admin `POST` with `csrf()` gets 200, confirming both protection layers.
- Bob passes HTTP-level `authenticated()` but is denied by `@PreAuthorize` at the service layer, showing that method security also produces a denied flow.
- `@WithMockUser` is a good tool for unit-testing authorization, but is not sufficient for testing wrong credentials: it can bypass the authentication provider and Basic filter.

Run in the Maven project:

~~~bash
./mvnw test
~~~

The tests describe expectations under the stated configuration and dependencies, **without claiming that tests were already executed on a specific project**. When multiple `SecurityFilterChain` beans or custom exception handlers exist, statuses can differ and must be verified against the real chain.

## 10. Customizing Responses for REST APIs

A frontend may require a structured error body (for example `application/problem+json`). Design a consistent response, but **do not collapse** authentication, authorization, CSRF, validation, and server errors into the same branch.

### AuthenticationEntryPoint

When a request requires authentication, the entry point can produce 401. With HTTP Basic, you must preserve the challenge:

~~~java
// CODE SNIPPET for an AuthenticationEntryPoint bean.
// Import javax/jakarta according to your project's Servlet API;
// Spring Boot 3 uses jakarta.servlet.
@Bean
AuthenticationEntryPoint apiEntryPoint() {
    return (request, response, exception) -> {
        response.setStatus(401);
        response.setHeader(
            "WWW-Authenticate", "Basic realm=\"demo\"");
        response.setContentType("application/problem+json;charset=UTF-8");
        response.getWriter().write(
            "{\"title\":\"Unauthorized\",\"status\":401}");
    };
}
~~~

This snippet must be placed in a `@Configuration` class and import `org.springframework.context.annotation.Bean` and `org.springframework.security.web.AuthenticationEntryPoint`. Do not log the raw `exception` or echo exception message details back to the client.

### AccessDeniedHandler

~~~java
// CODE SNIPPET for an AccessDeniedHandler bean.
@Bean
AccessDeniedHandler apiDeniedHandler() {
    return (request, response, exception) -> {
        response.setStatus(403);
        response.setContentType("application/problem+json;charset=UTF-8");
        response.getWriter().write(
            "{\"title\":\"Forbidden\",\"status\":403}");
    };
}
~~~

Requires importing `org.springframework.security.web.access.AccessDeniedHandler`. This mechanism handles denials routed to the handler; it **does not define the entire authorization policy**.

Attach the beans to the chain (a configuration replacement snippet—do not mix into the initial demo without testing):

~~~java
http
    .exceptionHandling(ex -> ex
        .authenticationEntryPoint(apiEntryPoint)
        .accessDeniedHandler(apiDeniedHandler))
    .httpBasic(basic -> basic
        .authenticationEntryPoint(apiEntryPoint));
~~~

In the snippet above, `apiEntryPoint` and `apiDeniedHandler` are interface-typed parameters injected into the configuration method; avoid confusing them with calling `@Bean` factory methods directly. Note that `httpBasic` has its own entry point for credential errors in the Basic filter, so it must be wired on the proper channel.

### Form Login Also Has a Separate Failure Handler

If the application uses form login, for example:

~~~java
http.formLogin(form -> form
    .failureUrl("/login?error"));
~~~

then a `POST /login` with a wrong password is normally routed by `UsernamePasswordAuthenticationFilter` to the failure handler, rather than being handled solely by a custom entry point. To standardize JSON responses for a login API, identify the authentication mechanism and configure its failure handler properly; do not merely replace `AccessDeniedHandler`.

### CSRF Error Handler Also Has Its Own Path

`CsrfFilter` normally uses its own `AccessDeniedHandler`. A JSON denied handler registered under `exceptionHandling(...)` must not be assumed by default to format every CSRF failure. If clients need the same error schema for CSRF, review the CSRF-specific handler configuration compatible with your Spring Security version and test `POST` requests with missing/invalid tokens.

## 11. HTTP Protocol Notes for Basic and Bearer

401 is not just a status code:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
~~~

An HTTP Basic client needs to know which scheme the server requires. With Bearer, the challenge typically uses `Bearer`, and a resource server can return error information conforming to the relevant OAuth2 specification. Do not apply a Basic challenge to a JWT endpoint or vice versa.

403 is a refusal even though the client understood the request:

~~~http
HTTP/1.1 403 Forbidden
~~~

It may be a missing role/scope or another security layer. In a browser app, an HTTP redirect to login can be convenient for anonymous users; for REST clients, use consistent status codes and bodies per the contract. When an authenticated user lacks permission, avoid exposing the list of missing roles in the public response.

## 12. Form Login Flow: Same Exception, Different Responses

A web application with form login typically has these branches:

~~~text
GET /private anonymous
  -> authorization requires authentication
  -> ExceptionTranslationFilter initiates login
  -> AuthenticationEntryPoint
  -> typically 302 Location: /login

POST /login wrong password, valid CSRF
  -> UsernamePasswordAuthenticationFilter
  -> BadCredentialsException
  -> AuthenticationFailureHandler
  -> typically 302 Location: /login?error

POST /login missing CSRF
  -> CsrfFilter rejects
  -> typically 403

GET /admin after login with only ROLE_USER
  -> Authorization manager denies
  -> AccessDeniedHandler
  -> typically 403
~~~

In this flow, a failure handler dedicated to `POST` login differs from the entry point that initiates login for a protected request. Test both, especially when customizing the login endpoint or migrating to an SPA.

**Do not mix HTTP 302 redirects and HTTP 401 across all clients without distinguishing requests.** A browser frontend needs a redirect, whereas an API client may need 401 JSON to decide whether to refresh a token or display a login prompt. Choose explicit security chains and entry points if the application supports both UI/session and token APIs.

## 13. Common Pitfalls to Avoid

| Misconception | Why it is wrong | How to verify |
| --- | --- | --- |
| `AuthenticationException` is always 401 | Form login may redirect; failure handler differs from entry point. | Test the actual filter. |
| `AccessDeniedException` is always 403 | Anonymous/remember-me may be routed to the entry point. | Check trust resolver/context. |
| Every 403 is missing permissions | CSRF, gateway, or controller can also return 403. | Test CSRF separately and trace error source. |
| `BadCredentialsException` to report missing admin role | Wrong semantics, metrics, and UX. | Use authorization policy/denial. |
| One `@ControllerAdvice(Exception.class)` catches everything | Errors in security filters can occur before MVC. | Use security handlers at the proper layer. |
| Disabling CSRF because POST without permission is always 403 | Masks failures instead of testing the role. | Use `csrf()` in MockMvc. |
| Using `@WithMockUser` to test passwords | Mock user bypasses credential validation. | Send credentials from test fixtures. |
| JSON handler echoes raw exceptions | Can leak sensitive information. | Generic client error + redacted internal audit. |
| Basic 401 without `WWW-Authenticate` | Violates HTTP authentication challenge expectations. | Assert headers. |
| Turning 403 into 200 with an error body | Clients may treat the request as successful. | Keep standard status codes. |
| Counting proxy 403 errors as Spring authorization | Requests may never have reached the app. | Correlate gateway and application logs. |
| Access denied after service mutation | 403 does not roll back prior changes. | Check authorization before side effects and transactions. |

## 14. Semantically Accurate Logging and Metrics

Metrics can be grouped by their actual source:

~~~text
security.authentication.failure
security.authorization.denied
security.csrf.rejected
http.server.requests{status="401"}
http.server.requests{status="403"}
~~~

These names are **suggestions** only; there is no claim that Spring creates all of them automatically. To distinguish causes:

- Authentication failures can be captured via `AuthenticationEventPublisher`, failure handlers, or Basic/Bearer instrumentation depending on the flow.
- Authorization denials can be observed via `AuthorizationEventPublisher` and denied events when integrated properly, or via access-denied handling.
- CSRF failures need instrumentation suited to `CsrfFilter`, rather than treating every 403 as CSRF.
- HTTP server metrics measure the final status; a 403 alone does not pinpoint the error source.
- A single request can trigger multiple authorization checks. Total events do not necessarily equal unique HTTP requests.

Never log passwords, tokens, API keys, session cookies, the `Authorization` header, or CSRF tokens. Avoid logging raw `exception.toString()`/`Authentication.toString()` unless you control the attached data. Audits may record internal error codes, route templates, HTTP method, correlation ID, service, policy ID, and a pseudonymized principal if needed, subject to appropriate retention and access controls.

## 15. Diagnostic Sequence for 401/403

1. **Confirm the exact service and SecurityFilterChain**: URL, context path, method, and `securityMatcher`.
2. **Inspect the authentication mechanism**: form/session, HTTP Basic, bearer, custom filter.
3. **Confirm credential/authentication state**: anonymous, remember-me, authenticated, or invalid token/credentials.
4. **Identify where the exception came from**: authentication provider/filter, authorization manager, method security, `CsrfFilter`, gateway/controller.
5. **Verify GrantedAuthority**: `ROLE_ADMIN` and `ADMIN` differ; scopes also often carry the `SCOPE_` prefix.
6. **Check the entry point/handler**: `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, CSRF-specific handler.
7. **If testing POST**: is there a valid CSRF token? If not, a 403 does not confirm the WRITE rule.
8. **If using method security**: are `@EnableMethodSecurity` and proxies active?
9. **Check the response contract**: status, challenge header, redirect, content type, no leaked secrets.
10. **Test both positive and negative cases**: valid authorized users must get through; wrong passwords and missing roles must be handled differently per the contract.
11. **Separate observability**: do not conflate authentication, authorization, CSRF, and gateway metrics.
12. **Do not loosen permissions to fix errors**: never use `permitAll()`, disable CSRF, or grant `ROLE_ADMIN` to all users just because you saw a 403.

## 16. Standalone Java 17: Simulating Both Exception Branches

Create `ExceptionBoundaryDemo.java`. This is a **Java SE model** with no Spring library imports; the two exceptions in the code merely illustrate the two error categories.

~~~java
public final class ExceptionBoundaryDemo {

    static final class DemoAuthenticationFailure
            extends RuntimeException {
    }

    static final class DemoAccessDenied
            extends RuntimeException {
    }

    static String request(
            boolean credentialsPresented,
            boolean credentialsValid,
            boolean hasAdminRole) {
        try {
            if (!credentialsPresented || !credentialsValid) {
                throw new DemoAuthenticationFailure();
            }
            if (!hasAdminRole) {
                throw new DemoAccessDenied();
            }
            return "200 ALLOWED";
        } catch (DemoAuthenticationFailure e) {
            return "401 AUTHENTICATION_REQUIRED";
        } catch (DemoAccessDenied e) {
            return "403 ACCESS_DENIED";
        }
    }

    public static void main(String[] args) {
        System.out.println("anonymous="
                + request(false, false, false));
        System.out.println("wrongPassword="
                + request(true, false, false));
        System.out.println("missingRole="
                + request(true, true, false));
        System.out.println("admin="
                + request(true, true, true));

        // Distinguish CSRF error at a different layer.
        System.out.println("missingCsrf=403 CSRF_REJECTED");
    }
}
~~~

Run on JDK 17 or higher:

~~~bash
javac ExceptionBoundaryDemo.java
java ExceptionBoundaryDemo
~~~

**Exact** stdout:

~~~text
anonymous=401 AUTHENTICATION_REQUIRED
wrongPassword=401 AUTHENTICATION_REQUIRED
missingRole=403 ACCESS_DENIED
admin=200 ALLOWED
missingCsrf=403 CSRF_REJECTED
~~~

This code does not perform real HTTP/CSRF and does not fully reflect `ExceptionTranslationFilter`: in real Spring Security, `AccessDeniedException` for an anonymous user can still trigger 401 or 302; form login failure can redirect; statuses depend on the handlers and authentication mechanism in use. The program serves to reinforce **error sources** and the distinction between authentication, authorization, and CSRF, not to replace integration tests.

## 17. Summary Test Matrix

| Scenario | Basic demo status | Meaning |
| --- | --- | --- |
| Anonymous GET /public | 200 | PermitAll. |
| Anonymous GET /private | 401 | Start authentication. |
| GET /private with wrong password | 401 | Authentication failure. |
| Bob GET /private with right password | 200 | Authenticated. |
| Bob GET /admin | 403 | Missing ROLE_ADMIN. |
| Admin GET /admin | 200 | Has ROLE_ADMIN. |
| Admin POST /admin/update missing CSRF | 403 | CSRF reject. |
| Bob POST /admin/update with CSRF | 403 | Authorization reject. |
| Admin POST /admin/update with CSRF | 200 | Passed both layers. |
| Bob GET /reports/export | 403 | Method security reject. |
| Admin GET /reports/export | 200 | Has REPORT_EXPORT. |
| Form login anonymous accessing private | Typically 302 | Entry point login page. |
| Form login wrong password | Typically 302 /login?error | AuthenticationFailureHandler. |
| Wrong/expired Bearer token | Typically 401 | Bearer authentication entry point. |
| Valid Bearer token missing scope | Typically 403 | Access denied. |

Other outcomes may come from custom handlers, gateways, CSRF configuration, or multi-chain setups; do not infer a unique exception type from status alone.

## 18. Review Questions

**Q1. Do the two exceptions inherit from each other?** No; both are unchecked exceptions, but they belong to different branches and represent different semantics.

**Q2. Which handler does a wrong password in form login usually hit?** The authentication filter's `AuthenticationFailureHandler`, not necessarily `ExceptionTranslationFilter`.

**Q3. Is a properly authenticated user missing `ROLE_ADMIN` a `BadCredentialsException`?** No. That is an authorization denial, typically `AccessDeniedException` or an appropriate subclass.

**Q4. Why can an `AccessDeniedException` lead to 401 or a redirect?** `ExceptionTranslationFilter` may treat an anonymous/remember-me user as insufficiently authenticated and invoke the entry point.

**Q5. Does an HTTP 403 prove the authorization manager denied the request?** No. `CsrfFilter`, a gateway, a controller, or the business layer can return 403.

**Q6. Is `InsufficientAuthenticationException` always caused by a wrong password?** No. It can indicate an insufficient level of authentication.

**Q7. If you want to test a POST missing WRITE authority and encounter a CSRF 403, what should you do?** Send a valid CSRF token, such as `.with(csrf())`, to test the denial caused by the missing authority.

**Q8. Does `@ControllerAdvice` replace all security filter handlers?** No, many errors are handled before MVC by security filters.

**Q9. What header must a custom Basic 401 pay attention to?** `WWW-Authenticate` with the appropriate scheme/realm.

**Q10. Why should raw exceptions not be logged?** They can unexpectedly expose account, policy, token, cookie, or request details.

**Q11. Can method security produce `AccessDeniedException` even if HTTP rules passed?** Yes, when `@PreAuthorize` or service-level authorization denies the call.

**Q12. Should 403 be replaced with 200 and a JSON "forbidden" message?** No; that violates protocol semantics and clients may treat the request as successful.

## 19. Pre-Release Checklist

- [ ] Distinguish authentication failure from authorization denial in the API contract.
- [ ] Do not hard-map `AuthenticationException = 401` and `AccessDeniedException = 403` for every authentication mechanism.
- [ ] Understand how `ExceptionTranslationFilter` uses `AuthenticationTrustResolver` with anonymous/remember-me users.
- [ ] Know that `AuthenticationFailureHandler`, `AuthenticationEntryPoint`, and `AccessDeniedHandler` are not the same thing.
- [ ] Check filter ordering because upstream authentication filters may handle errors locally.
- [ ] Have separate tests for wrong credentials, anonymous access, missing roles, sufficient roles, and CSRF.
- [ ] Have method security tests if the application uses `@PreAuthorize`.
- [ ] Do not disable CSRF or add `permitAll()` to work around authorization errors.
- [ ] Preserve the proper `WWW-Authenticate` header for Basic/Bearer.
- [ ] Ensure error bodies never contain passwords, tokens, cookies, sensitive roles/policies, or raw exception messages.
- [ ] Classify logs/metrics by error source rather than counting every 403 as an authorization denial.
- [ ] Run real tests against the actual `SecurityFilterChain`, context path, and HTTP method.
- [ ] If mixing form login/SPA/API, give each flow a clear failure handler and entry point.
- [ ] Check resource owner/tenant at a trusted layer; enforce denial before side effects.
- [ ] Include positive tests proving users with proper permissions can actually access endpoints.

**Conclusion:** `AuthenticationException` is about **failed or insufficient authentication**; `AccessDeniedException` is about **a decision to deny access**. The final response depends on **the error source, filter position, authentication state, and the active entry point/handler**. A secure application separates 401/302/403, CSRF, authentication failure, and authorization denial through clear logic and tests, rather than guessing the cause from a single status code.
