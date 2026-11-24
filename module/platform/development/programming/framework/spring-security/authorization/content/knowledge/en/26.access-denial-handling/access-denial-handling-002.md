# ExceptionTranslationFilter and Translating Security Errors into HTTP Responses

In Spring Security for **Servlet**, `ExceptionTranslationFilter` is the bridge between Java security exceptions and how the application responds over HTTP. It helps the system distinguish between a situation where **the user needs to be prompted to authenticate** and a situation where **the user is authenticated but lacks sufficient permissions**. This lesson belongs to the *Access Denial Handling* group of the *Spring Security - authorization* module.

## 1. Position and Responsibilities

When a request passes through `FilterChainProxy`, authentication filters populate `Authentication` in `SecurityContext`; `AnonymousAuthenticationFilter` may set an anonymous identity if no authentication exists yet. Further down the chain, `ExceptionTranslationFilter` wraps the `FilterChain.doFilter(...)` call to catch security exceptions thrown during downstream processing, typically by `AuthorizationFilter`.

Simplified flow (not listing every filter):

~~~text
HTTP request
  -> authentication filter (e.g., BasicAuthenticationFilter)
  -> AnonymousAuthenticationFilter
  -> ExceptionTranslationFilter
       -> AuthorizationFilter / application / method security
       <- may throw AuthenticationException or AccessDeniedException
       -> AuthenticationEntryPoint or AccessDeniedHandler
  -> HTTP response
~~~

`AuthorizationFilter` is the component that evaluates `authorizeHttpRequests` rules and denies access when permissions are insufficient. `ExceptionTranslationFilter` **does not check roles itself, does not verify passwords, and does not create tokens**; it selects how to handle a security exception after it is thrown. Valid requests with no exceptions proceed normally.

**Exception-catching boundary:** the filter only catches exceptions that propagate back through the `doFilter` call it wraps. Errors already handled by a filter **before** it, ordinary business exceptions, or exceptions caught elsewhere will not be automatically translated into 401/403 by it. If the response has already been committed, changing the status code may fail.

## 2. Two Exception Types and Two Handling Points

- `AuthenticationException`: an error or requirement related to authentication. When this exception reaches `ExceptionTranslationFilter`, the filter initiates the authentication request flow via `AuthenticationEntryPoint`.
- `AccessDeniedException`: access denied by an authorization check. The filter inspects the authentication state to choose what to do next: an anonymous or remember-me account may require full authentication via `AuthenticationEntryPoint`; a fully authenticated account that lacks permissions is handed off to `AccessDeniedHandler`.
- `AuthenticationEntryPoint.commence(request, response, exception)`: prompts the client to authenticate, such as returning 401 with `WWW-Authenticate`, or redirecting to a login page.
- `AccessDeniedHandler.handle(request, response, exception)`: handles a denied request, usually returning HTTP 403. `AccessDeniedHandlerImpl` is a commonly used implementation; it can return 403 directly or forward to a configured error page.

The pseudocode below only describes the **decision**, and is not standalone Java code:

~~~text
try:
    process the rest of the filter chain
catch AuthenticationException:
    start authentication using AuthenticationEntryPoint
catch AccessDeniedException:
    if anonymous or remember-me:
        start authentication using AuthenticationEntryPoint
    else:
        delegate to AccessDeniedHandler
~~~

You should not simply check `SecurityContextHolder.getContext().getAuthentication() != null` to conclude that a user is logged in: an anonymous request usually **still has** an `AnonymousAuthenticationToken` object. Spring Security uses `AuthenticationTrustResolver` to distinguish anonymous, remember-me, and other states.

When starting authentication from `ExceptionTranslationFilter`, Spring Security clears the `SecurityContext`, calls `RequestCache.saveRequest(...)` according to the configured strategy, and then invokes `AuthenticationEntryPoint`. Request cache is useful for login UIs so the user can return to the original URL; APIs where the client proactively retries typically use `NullRequestCache`.

## 3. What Do 401, 403, and 302 Mean?

| Scenario | Typical Handling | Common HTTP Status |
| --- | --- | --- |
| Unauthenticated client accessing a resource requiring authentication | `AccessDeniedException` -> entry point | 401 for HTTP Basic/Bearer; 302 when using form login |
| Authenticated but missing `ROLE_ADMIN` | `AccessDeniedException` -> access-denied handler | 403 |
| `AuthenticationException` reaches the filter | Entry point | Usually 401 or redirect |
| Session only has remember-me, resource requires full authentication | May trigger re-authentication | Depends on entry point |
| Request is authorized | Continue to controller | Decided by application, e.g., 200 |

**401 Unauthorized** in HTTP semantics generally indicates that valid credentials must be provided. With HTTP Basic, a 401 response should include a `WWW-Authenticate: Basic ...` challenge so the client knows how to authenticate. **403 Forbidden** generally indicates the server understood the request but refuses to authorize it even though identity has been established. **302 Found** is the typical redirect result of a form login entry point; therefore, not every security error returns JSON or always returns 401/403.

Distinguish between **exception type**, **handling point**, and **HTTP status**. There is no immutable mapping "`AuthenticationException` = 401; `AccessDeniedException` = 403": an anonymous `AccessDeniedException` usually goes to the entry point, and the actual status depends on the configured entry point/handler.

## 4. Runnable Example with Spring Boot 3.x, Spring Security 6.x, and Java 17+

Create a Spring Boot Servlet application with dependencies `spring-boot-starter-web` and `spring-boot-starter-security`. In `build.gradle` of a Spring Boot project with plugins already configured, you need at least:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Save the following code at `src/main/java/com/example/securitydemo/SecurityDemoApplication.java`:

~~~java
package com.example.securitydemo;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }

    @GetMapping("/api/public")
    public String publicApi() {
        return "public";
    }

    @GetMapping("/api/admin")
    public String adminApi() {
        return "admin";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint unauthorized = (request, response, error) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE,
                    "Basic realm=\"demo\"");
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"error\":\"unauthorized\"}");
        };

        AccessDeniedHandler forbidden = (request, response, error) -> {
            response.setStatus(HttpServletResponse.SC_FORBIDDEN);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.getWriter().write("{\"error\":\"forbidden\"}");
        };

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .requestMatchers("/api/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(basic -> basic.authenticationEntryPoint(unauthorized))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint(unauthorized)
                        .accessDeniedHandler(forbidden))
                .requestCache(cache -> cache.requestCache(new NullRequestCache()))
                .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails normal = User.withUsername("user")
                .password("{noop}pw")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}pw")
                .roles("ADMIN")
                .build();
        return new InMemoryUserDetailsManager(normal, admin);
    }
}
~~~

Here `hasRole("ADMIN")` checks the `ROLE_ADMIN` authority. User `user` only has `ROLE_USER`; `admin` has `ROLE_ADMIN`. Both handlers intentionally return simple JSON so the handling branch can be clearly observed. `{noop}` is only for demonstration with in-memory accounts; real applications need a `PasswordEncoder` and securely hashed passwords. Basic Auth must run over **HTTPS** in real operations.

The entry point configuration is applied to **both** `exceptionHandling` and `httpBasic`: an unauthenticated request denied by `AuthorizationFilter` may pass through `ExceptionTranslationFilter`; whereas a wrong Basic password is usually caught by `BasicAuthenticationFilter` and invokes its own entry point before reaching the exception translation filter. Omitting the configuration in `httpBasic` may cause the two branches to return different contents. `NullRequestCache` avoids saving the initial request into the session in this API example.

CSRF is not disabled in the example: the endpoints are GET only. When adding state-changing operations, CSRF must be evaluated according to how clients authenticate, especially if browsers automatically send cookies or Basic credentials.

### Running and Verifying

In the Spring Boot project directory containing the Gradle wrapper, run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`), then execute the following commands:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/admin
curl -i -u user:pw http://localhost:8080/api/admin
curl -i -u admin:pw http://localhost:8080/api/admin
curl -i -u admin:wrong http://localhost:8080/api/admin
~~~

Results to observe (extracting only relevant lines; other headers may vary):

| Command in Order | HTTP Status | Expected Body | Why |
| --- | --- | --- | --- |
| Public, no credentials | 200 | `public` | `permitAll()` |
| Admin, no credentials | 401 | `{"error":"unauthorized"}` | Anonymous denied -> entry point |
| Admin, `user:pw` | 403 | `{"error":"forbidden"}` | Authenticated successfully, missing `ROLE_ADMIN` |
| Admin, `admin:pw` | 200 | `admin` | Sufficient permissions |
| Admin, `admin:wrong` | 401 | `{"error":"unauthorized"}` | Basic authentication failed |

For the 401 lines, the illustrative handler also sends the header:

~~~http
WWW-Authenticate: Basic realm="demo"
~~~

The example has two 401 scenarios taking **different paths**: missing credentials are handled via `AuthorizationFilter -> ExceptionTranslationFilter -> AuthenticationEntryPoint`; wrong password is handled immediately within `BasicAuthenticationFilter -> AuthenticationEntryPoint`. Identical HTTP outcomes do not prove the same filter caught the error.

## 5. Applying in Real Projects

**Consistent error responses for REST APIs:** configure `exceptionHandling(ex -> ex.authenticationEntryPoint(...).accessDeniedHandler(...))` in the corresponding `SecurityFilterChain`. Write a response with the right HTTP status, appropriate `Content-Type`, and JSON matching the API contract (e.g., error code, safe message, correlation id). Do not expose passwords, token contents, stack traces, or internal permission details. For HTTP Basic, OAuth2 Resource Server, or other mechanisms, preserve the challenge headers/error formats required by the protocol.

**Multiple SecurityFilterChains:** each chain has its own `securityMatcher` and exception handling configuration; whichever chain a request matches determines which configuration is used. If web pages use `formLogin` while `/api/**` uses API authentication, scope entry points appropriately to avoid having an API return 302 to an HTML login page when the client expects JSON.

**OAuth2 Bearer token:** missing tokens or insufficient scopes can lead to a `WWW-Authenticate: Bearer` challenge and appropriate error details. Malformed, expired, or invalid tokens are typically handled by the corresponding authentication filter before `ExceptionTranslationFilter` sees them. Do not blindly impose the Basic JSON from the example onto a Resource Server.

**Method security:** a `@PreAuthorize` annotation may throw `AccessDeniedException` while the request is still traversing the wrapped filter segment; when the exception propagates outward, `ExceptionTranslationFilter` can handle it. If MVC code handles/transforms the exception itself before it escapes, the result depends on that code. This is not a general exception handler for every application layer.

**Error pages and forwards:** `AccessDeniedHandlerImpl` can forward to a configured 403 page. The target page must be properly permitted; with `AuthorizationFilter`, dispatches such as `FORWARD`/`ERROR` can also undergo authorization checks. Forgetting to configure this easily causes error loops or secondary 403s.

## 6. Diagnosing Common Errors

1. **"Not logged in yet getting 403, not 401."** Check whether the entry point is a type that returns 403 (such as a pre-auth/custom configuration) and check which `SecurityFilterChain` the request matches. Do not infer from the status that Spring Security chose the wrong branch.
2. **"Logged in but keep getting 401."** Check whether authentication is actually valid on this request, whether the context is loaded, whether the cookie/token reaches the server, and whether remember-me is being required to upgrade to full authentication.
3. **"I configured AccessDeniedHandler, but wrong login does not go through it."** Invalid credentials are an authentication failure, typically handled by the authentication filter and invoking the entry point; `AccessDeniedHandler` is for access permission denials.
4. **"Exception in custom filter is not translated."** Check filter ordering: if it runs before `ExceptionTranslationFilter`, the exception is outside the `doFilter` scope caught by this filter. Do not arbitrarily change filter order; choose the proper error-handling mechanism where the error occurs.
5. **"ControllerAdvice cannot catch security errors."** Most request authorization occurs in the servlet security filter chain before the controller. Handle it in `SecurityFilterChain` first, then consider exceptions that actually belong to MVC.
6. **"API receives HTML/302 instead of JSON/401."** The current entry point might be form login or the web page's chain. Cross-check `securityMatcher`, `exceptionHandling`, and authentication type.
7. **"Has permission yet still gets 403."** Check the `ROLE_` prefix when using `hasRole`, actual `GrantedAuthority` values, `requestMatchers` ordering, method security, and CSRF if the request uses POST/PUT/DELETE.

To trace the filter chain in a development environment, you can enable `logging.level.org.springframework.security=DEBUG` and inspect the `DefaultSecurityFilterChain` log at startup. Use `TRACE` selectively, avoiding putting sensitive request data into operational logs.

## 7. Mastery Checklist

- Identify **where access is denied** (`AuthorizationFilter`/method security) and **where exceptions are translated into responses** (`ExceptionTranslationFilter`).
- Explain why an anonymous `AccessDeniedException` differs from an authenticated user's `AccessDeniedException`.
- Know that `AuthenticationEntryPoint` typically serves authentication requests while `AccessDeniedHandler` handles insufficient permissions, though the HTTP status depends on the implementation.
- Distinguish 401 from missing credentials in the exception translation branch vs. 401 caught directly by an authentication filter.
- Reproduce 200/401/403 yourself, verify `WWW-Authenticate`, and avoid configuring handlers that break the Basic/Bearer contract.

### Official References

- Spring Security — Servlet Architecture / Handling Security Exceptions: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — HTTP Basic: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
