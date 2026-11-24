# AuthenticationException and AccessDeniedException in Spring Security

> Scope: Spring Security for Servlet applications (Spring MVC), illustrated with Spring Boot 3.x / Spring Security 6.x and Java 17+. These are two groups of security exceptions with different meanings: **identity authentication** and **access authorization**.

## 1. Distinguishing the Two Security Questions

When processing a request, a system typically needs to answer in order:

1. **Who are you?** — Verify credentials, tokens, sessions, etc. to build a valid `Authentication` object.
2. **What are you allowed to do?** — Evaluate `Authentication`, `GrantedAuthority`, and the access policy of the resource or method.

`AuthenticationException` indicates a problem with the **authentication** process or state. `AccessDeniedException` indicates **access is denied**, usually due to insufficient permissions; some other mechanisms such as CSRF also use this exception branch. Therefore, you cannot look at the exception name alone and conclude for certain whether the HTTP status code is 401 or 403.

| Criterion | `AuthenticationException` | `AccessDeniedException` |
| --- | --- | --- |
| Primary meaning | Unable to authenticate, or authentication proof is invalid/insufficient | Security policy does not allow the request |
| Java class | `org.springframework.security.core.AuthenticationException` | `org.springframework.security.access.AccessDeniedException` |
| Class kind | Abstract class extending `RuntimeException` | Concrete class extending `RuntimeException` |
| Examples | Wrong password, invalid token, locked account, missing required authentication info | Missing `ROLE_ADMIN`, failing `@PreAuthorize` condition, invalid CSRF token |
| Servlet web handling | Can be routed to `AuthenticationEntryPoint` or the login mechanism's failure handler | `AccessDeniedHandler` if the user is sufficiently authenticated; can fall back to `AuthenticationEntryPoint` if not fully authenticated |
| Common HTTP status | 401 for Basic/Bearer APIs; form login may redirect | 403 when authenticated but not permitted |
| Client-side action | Supply/fix credentials, log in again, or obtain a valid token | Check permissions/scopes or policy conditions; do not blindly retry with the same credentials |

**Visual example:** Calling `GET /admin`. No credentials sent: the system usually requests authentication (401 with HTTP Basic). Successfully logged in with an account having only `ROLE_USER`: the system denies permission (403). Logged in with an account having `ROLE_ADMIN`: the request is allowed through (200 if the endpoint succeeds).

## 2. AuthenticationException: Authentication-Related Errors

`AuthenticationException` is the abstract superclass for exceptions when the `Authentication` object or verification process is invalid. They commonly originate from `AuthenticationManager`, `AuthenticationProvider`, or authentication filters (Basic, form login, Bearer token, etc.). Some representative exceptions:

| Exception | Typical Scenario |
| --- | --- |
| `BadCredentialsException` | Wrong username/password or authentication proof was rejected |
| `UsernameNotFoundException` | User not found when loading account details; some configurations intentionally mask the cause as a credentials error |
| `DisabledException`, `LockedException` | Account is disabled or locked |
| `CredentialsExpiredException`, `AccountExpiredException` | Credentials or account have expired |
| `AuthenticationCredentialsNotFoundException` | An operation requires an authentication object, but none exists in the context |
| `InsufficientAuthenticationException` | The current level of authentication is not strong enough to access the resource |
| `AuthenticationServiceException` | Failure in the authentication service itself, distinct from the user merely entering wrong input |

You should not instantiate `new AuthenticationException(...)` directly because the class is `abstract`. When writing a custom `AuthenticationProvider`, use an appropriate subclass, such as `BadCredentialsException` for rejected credentials. Do not return overly detailed messages such as "account exists but wrong password" to the client because it can leak user information.

`AuthenticationException` does not simply mean "the user has not logged in": the user may have sent a token that is expired, has an invalid signature, was revoked, or fails authentication conditions; the response depends on the mechanism in use.

## 3. AccessDeniedException: Unauthorized Access

`AccessDeniedException` typically occurs when the authorization mechanism evaluates the request and concludes there are insufficient permissions. With the common `authorizeHttpRequests` configuration, `AuthorizationFilter` applies `AuthorizationManager` rules; method security such as `@PreAuthorize` can also deny access before the method runs.

Examples:

- The rule `.requestMatchers("/admin").hasRole("ADMIN")` requires the `ROLE_ADMIN` authority. `hasRole("ADMIN")` automatically adds the `ROLE_` prefix by default convention; `hasAuthority("ROLE_ADMIN")` checks the exact authority name.
- A user who has `ROLE_USER` and is authenticated, but lacks `ROLE_ADMIN`, will be denied.
- In Spring Security 6.3+, `AuthorizationDeniedException` is a subclass of `AccessDeniedException`; this exception can carry an `AuthorizationResult`.
- `CsrfException` and its subclasses such as `MissingCsrfTokenException` and `InvalidCsrfTokenException` also belong to the `AccessDeniedException` branch. These are request-protection errors and do not necessarily reflect a missing role. `CsrfFilter` can invoke `AccessDeniedHandler` directly.

**Common pitfall:** An `AccessDeniedException` does not prove the caller is logged in. When the current principal is anonymous, or the remember-me level is insufficient, Spring Security may decide to **initiate authentication** instead of immediately returning 403.

## 4. How Does ExceptionTranslationFilter Turn Exceptions into HTTP Behavior?

Within a Servlet application's `SecurityFilterChain`, `ExceptionTranslationFilter` bridges security exceptions to web responses. It **does not enforce authorization policies itself**; that belongs to components like `AuthorizationFilter`, method security, or specialized filters.

Simplified flow:

```text
Request
  -> SecurityFilterChain
      -> Authentication filters (Basic/Form/Bearer...)
      -> ExceptionTranslationFilter
          -> downstream filters / AuthorizationFilter / controller
              -> AuthenticationException
                   -> AuthenticationEntryPoint: request authentication
              -> AccessDeniedException
                   -> anonymous / insufficient remember-me?
                        -> AuthenticationEntryPoint
                   -> sufficiently authenticated?
                        -> AccessDeniedHandler: deny access
              -> no security error
                   -> continue normal processing
```

Three components to distinguish:

- **`AuthenticationEntryPoint`**: initiates an authentication mechanism. For example, `BasicAuthenticationEntryPoint` sends 401 and `WWW-Authenticate: Basic ...`; `LoginUrlAuthenticationEntryPoint` can redirect to the login page; Bearer tokens use an entry point compliant with the Bearer specification.
- **`AccessDeniedHandler`**: produces the response when a request has passed authentication but is blocked; the basic handling is usually 403, or forwarding to a configured access-denied page.
- **`AuthenticationFailureHandler`**: handles failure of a specific login flow, especially in form login. Not every `AuthenticationException` passes through `ExceptionTranslationFilter`: an authentication filter positioned before it can catch the error itself and invoke its failure handler/entry point.

Therefore, the formula "`AuthenticationException` is always 401; `AccessDeniedException` is always 403" is **incorrect**. The outcome depends on authentication state, request type, where in the filter chain the error occurs, and the configured handlers.

### 401, 403, and Redirects: Reading the Meaning Correctly

| Scenario | Common Outcome |
| --- | --- |
| Calling an HTTP Basic API without credentials when the endpoint requires login | `401 Unauthorized`; accompanied by a `WWW-Authenticate` challenge header |
| Sending a wrong password over HTTP Basic | `401 Unauthorized` as the Basic filter handles the failure |
| Authenticated but lacking permission to access `/admin` | `403 Forbidden` |
| Anonymous user hitting a rule requiring `ROLE_ADMIN` | Usually initiates authentication, e.g., 401 with HTTP Basic, not necessarily 403 |
| Form login failure | Redirects back to the login page with an error indicator or responds per the failure handler |
| Expired/invalid Bearer token | Usually 401 with a Bearer challenge |
| Valid Bearer token but missing scope | Usually 403; may include `insufficient_scope` info per the Bearer spec |
| POST request blocked due to missing/invalid CSRF token | Usually 403; may be handled directly by `CsrfFilter` calling the handler |

HTTP 401 usually needs a `WWW-Authenticate` header matching the authentication scheme. If customizing a JSON body, do not accidentally strip headers or behavior needed for HTTP Basic/Bearer. With form login using cookies/sessions, redirecting is normal behavior.

## 5. Runnable Example: Two Accounts, One Role-Protected Endpoint

The example below is **a single complete Java file** for a Spring Boot 3.x project that already includes `spring-boot-starter-web` and `spring-boot-starter-security`, using Java 17+. Save it at `src/main/java/demo/DemoApplication.java`.

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        return new InMemoryUserDetailsManager(
                User.withUsername("member")
                        .password("{noop}demo")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}demo")
                        .roles("ADMIN")
                        .build()
        );
    }
}

@RestController
class DemoController {
    @GetMapping("/public")
    String open() {
        return "public";
    }

    @GetMapping("/profile")
    String profile() {
        return "profile";
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }
}
```

Explanation:

1. `/public` is open to everyone; `/profile` only requires authentication; `/admin` requires `ROLE_ADMIN`.
2. Spring Security creates the `ROLE_USER` and `ROLE_ADMIN` authorities corresponding to `.roles("USER")` and `.roles("ADMIN")`.
3. `httpBasic` enables the authentication flow based on the `Authorization: Basic ...` header.
4. `InMemoryUserDetailsManager` and the `{noop}` prefix are for demonstration only; **never use plaintext passwords or hardcoded accounts in production**. In practice, use an appropriate user store and a secure `PasswordEncoder` such as BCrypt.

Run the application using the project's Boot task, for example:

```bash
./gradlew bootRun
```

Once the application starts at `http://localhost:8080`, verify:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u member:wrong http://localhost:8080/profile
curl -i -u member:demo http://localhost:8080/profile
curl -i -u member:demo http://localhost:8080/admin
curl -i -u admin:demo http://localhost:8080/admin
```

| Command | Expected HTTP | Body on success | Explanation |
| --- | --- | --- | --- |
| `GET /public` (anonymous) | 200 | `public` | `permitAll` |
| `GET /profile` (anonymous) | 401 | — | Authentication required |
| `GET /profile` (wrong password) | 401 | — | Authentication failed |
| `GET /profile` (member:demo) | 200 | `profile` | Authenticated |
| `GET /admin` (member:demo) | 403 | — | Has identity, but missing `ROLE_ADMIN` |
| `GET /admin` (admin:demo) | 200 | `admin` | Correct role |

The codes in the table are the expected results of this demo configuration, not fixed codes tied to each exception class. Actual headers and bodies may vary by configuration or version. `curl -i` lets you see both status and headers; observe `WWW-Authenticate` in the 401 responses.

## 6. Customizing Error Responses for REST APIs

For REST APIs, a consistent JSON body is often desired: `401` so the client knows to authenticate, and `403` so the client knows permissions were denied. The configuration below is a **replacement for the `securityFilterChain` method** in `SecurityConfig` from the previous example; add imports for `AuthenticationEntryPoint` and `AccessDeniedHandler` from `org.springframework.security.web` / `org.springframework.security.web.access`. This is a configuration snippet to place inside the class, **not a standalone Java program**.

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    AuthenticationEntryPoint unauthorized = (request, response, cause) -> {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.setHeader("WWW-Authenticate", "Basic realm=\"demo\"");
        response.getWriter().write("{\"error\":\"unauthorized\"}");
    };

    AccessDeniedHandler forbidden = (request, response, cause) -> {
        response.setStatus(403);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"forbidden\"}");
    };

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .requestMatchers("/admin").hasRole("ADMIN")
                    .anyRequest().authenticated())
            .httpBasic(basic -> basic.authenticationEntryPoint(unauthorized))
            .exceptionHandling(ex -> ex
                    .authenticationEntryPoint(unauthorized)
                    .accessDeniedHandler(forbidden))
            .build();
}
```

Additional imports needed:

```java
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.access.AccessDeniedHandler;
```

- The `exceptionHandling` configuration handles exceptions reaching the `ExceptionTranslationFilter` path. Configuring `httpBasic` separately ensures wrong-password errors from `BasicAuthenticationFilter` also return the desired 401 body.
- `WWW-Authenticate: Basic realm="demo"` is preserved in the 401 response so clients receive the proper HTTP Basic challenge. If switching to Bearer/JWT, use the dedicated Bearer entry point/denied handler and preserve the relevant standard headers; do not reuse the Basic header.
- Do not echo sensitive details from `cause.getMessage()` back to the client. Log controlled diagnostic details on the server, distinguishing credential errors, configuration errors, and authorization errors to aid investigation.
- The example uses GET, so CSRF does not need to be disabled. **Do not add `csrf.disable()` as a "quick fix" when hitting 403**: first determine whether the application is truly a stateless API or uses cookies/sessions, and understand the CSRF threat model.

## 7. Practical Step-by-Step Error Diagnostics

1. **Check status, redirects, and headers**: does `401` have `WWW-Authenticate`? Does `302` point to login? On which request does `403` appear? Do not mechanically guess the exception type from the status.
2. **Check the authentication mechanism**: did the client send the right Authorization header/cookie/token; are credentials still valid; does `AuthenticationProvider` match the token type?
3. **Check identity and authorities**: inspect `Authentication` details in a safe debug environment; `hasRole("ADMIN")` requires `ROLE_ADMIN`, not just `ADMIN`.
4. **Check where policies are enforced**: URL matchers and the order of `requestMatchers`, `@PreAuthorize`, custom `AuthorizationManager`, method security. An endpoint can pass HTTP authorization and still be blocked at the method level.
5. **Check other blocking branches**: CSRF tokens on POST/PUT/DELETE, CORS/preflight, multiple `SecurityFilterChain` beans with different `securityMatcher` rules; do not blame every 403 on a missing role.
6. **Check the actual error handler**: `AuthenticationEntryPoint`, `AuthenticationFailureHandler`, `AccessDeniedHandler`; which filter detected the error and whether it sits after `ExceptionTranslationFilter`.
7. **Confirm with contrasting tests**: anonymous, wrong credentials, valid user lacking permissions, user with sufficient permissions; state-changing endpoints should also be tested for CSRF as designed.

Debug note: `AnonymousAuthenticationToken` can be an `Authentication` present in `SecurityContext`. Thus, crudely checking only `getAuthentication() != null` or `isAuthenticated()` can lead to false conclusions that a user is logged in; Spring Security uses `AuthenticationTrustResolver` to distinguish anonymous, remember-me, and appropriate authentication levels.

## 8. Common Mistakes and How to Fix Them

- **Equating errors directly with status codes**: `AuthenticationException` is not always 401 (form login may redirect); `AccessDeniedException` is not always 403 (anonymous may be prompted to log in). Inspect the authentication mechanism and handlers.
- **Turning every 403 into 401**: this hides real missing-permission errors. When authenticated but missing a scope/role, 403 is usually the right signal.
- **Using `@ControllerAdvice` as the sole place to catch security errors**: many errors are intercepted directly inside the filter chain before the request enters Spring MVC; `@ExceptionHandler` in a controller does not replace security handler configuration.
- **Throwing `AccessDeniedException` for every business error**: a normal data validation error should use the corresponding domain/API error type. Only use security exceptions when a security policy denies the operation.
- **Using `new BadCredentialsException` to report insufficient permissions**: wrong layer of responsibility. Role/permission checks belong in authorization and may raise `AccessDeniedException`.
- **Leaking sensitive causes**: do not return whether an account name exists, token values, stack traces, or overly detailed lock statuses to clients.
- **Disabling CSRF to "get rid of 403" without understanding context**: this can weaken protection for applications using cookies/sessions.

## 9. Self-Check Exercises

1. An unauthenticated user accesses `/admin` with HTTP Basic: predict the status and the role of `AuthenticationEntryPoint`.
2. A logged-in user has `ROLE_USER` but lacks `ROLE_ADMIN`: identify the `AccessDeniedHandler` branch and explain why 401 should not be returned.
3. A user with sufficient roles sends a POST missing a CSRF token in an app with CSRF enabled: why can it still return 403?
4. A form login with the wrong password returns a redirect instead of 401: which part of the login flow can determine this behavior?
5. An app has custom JSON for `exceptionHandling`, yet HTTP Basic with a wrong password still produces a different body: what additional configuration needs to be checked?

**Check answers:** (1) usually 401 and the entry point invites authentication; (2) 403 because authenticated but lacking permissions; (3) blocked by the CSRF protection mechanism; (4) the form login failure handler; (5) entry point / failure handling configured on `httpBasic`.

## Official Documentation

- [Spring Security — Servlet Architecture and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — In-Memory Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/in-memory.html)