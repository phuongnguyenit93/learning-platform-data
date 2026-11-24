# AuthenticationFailureHandler and Errors at the Login Endpoint in Spring Security

## 1. Lesson Objectives and Scope

A user submits `POST /login` with a username and password. Password verification fails on the server: a browser should return to the login page with an appropriate message, while an API client may expect HTTP 401 with standardized error JSON. Spring Security provides **`AuthenticationFailureHandler`** to decide **the response immediately after a failed authentication attempt**.

The tricky part is that not every security error comes from the same place. **Failed login at the authentication filter**, **accessing a protected page while unauthenticated**, **insufficient permissions**, **missing CSRF token**, **JSON validation errors**, and **failed OAuth2/OIDC login callbacks** follow different processing paths. Placing a handler in the wrong spot can leak account data, cause redirect loops, make an API return HTML instead of JSON, or trigger unexpected 500s.

This lesson helps you:

1. Locate `AuthenticationFailureHandler` in the `UsernamePasswordAuthenticationFilter` → `AuthenticationManager` → `AuthenticationProvider` flow.
2. Distinguish `AuthenticationFailureHandler` from `AuthenticationEntryPoint`, `AccessDeniedHandler`, and `@ControllerAdvice`.
3. Know the default behavior of `SimpleUrlAuthenticationFailureHandler`, `failureUrl(...)`, `failureHandler(...)`, and when to choose each.
4. Define a login error HTTP/JSON contract without revealing whether a user exists, is locked, or entered the wrong password.
5. Write a Spring Boot 3.5.x / Java 17+ example supporting both form redirect experience and JSON 401 responses.
6. Test failure/success, missing CSRF, unauthenticated access, disabled accounts, bad keys, or service unavailable using MockMvc.
7. Design logging, rate limiting, account lockout, brute-force protection, timing side-channel mitigation, generic error messages, and session hygiene.
8. Understand the boundary: the handler only formats/dispatches failures; **it does not replace credential verification and does not protect endpoints on its own**.

**Scope:** Servlet-based Spring Security with form login; dedicated sections cover custom API filters, bearer tokens, OAuth2, and reactive/WebFlux so you know where handler application differs. In Spring WebFlux, the corresponding interface is `ServerAuthenticationFailureHandler`, rather than reusing Servlet classes directly.

## 2. Failure Flow at POST /login

For traditional Servlet form login, Spring Security provides `UsernamePasswordAuthenticationFilter`, a subclass of `AbstractAuthenticationProcessingFilter`. It intercepts requests matching `loginProcessingUrl` (default POST `/login`), extracts `username` and `password`, and creates an unauthenticated `UsernamePasswordAuthenticationToken`.

```text
Browser or HTTP client
      |
      | POST /login
      | username=learner&password=wrong
      | CSRF token (if using browser session)
      v
SecurityFilterChain
      |
      | CsrfFilter (unsafe request requires token)
      |     |
      |     +-- Invalid/missing CSRF -> 403: NOT auth failure handler
      |
      | UsernamePasswordAuthenticationFilter
      |     |
      |     | attemptAuthentication(request, response)
      |     v
      | AuthenticationManager (typically ProviderManager)
      |     |
      |     v
      | AuthenticationProvider (e.g. DaoAuthenticationProvider)
      |     |
      |     | checks account/password/status
      |     v
      | AuthenticationException
      |
      | unsuccessfulAuthentication(...)
      |   1. SecurityContextHolder.clearContext()
      |   2. RememberMeServices.loginFail(...)
      |   3. AuthenticationFailureHandler.onAuthenticationFailure(...)
      |
      v
HTTP response
  - Browser: 302 Location: /login?error
  - JSON client: 401 + application/json (if explicitly configured)
```

This flow relies on Spring Security's `AbstractAuthenticationProcessingFilter` contract. The filter calls the handler **only when an authentication error enters the unsuccessful authentication branch**. Exceptions thrown by Controllers, databases, the CSRF filter, misordered custom filters, or gateways **do not automatically** pass through this handler.

### 2.1. Steps Spring Security Takes Before Calling the Handler

In the standard mechanism:

- `AuthenticationManager.authenticate(...)` rejects the credentials; an `AuthenticationException` is thrown.
- `unsuccessfulAuthentication(...)` clears `SecurityContextHolder` so the failed request is never treated as having just logged in.
- `RememberMeServices.loginFail(...)` is invoked. If remember-me is not configured, this is normally a no-op.
- `AuthenticationFailureHandler.onAuthenticationFailure(request, response, exception)` decides the redirect URL, forward, HTTP status/body, or other action.

**Never call `SecurityContextHolder.getContext().setAuthentication(...)` inside a failure handler.** A handler must never "rescue" bad credentials by granting a valid Authentication.

### 2.2. The Success Branch Is Completely Different

If login succeeds, Spring Security applies the session strategy, sets/saves `SecurityContext`, invokes remember-me success if configured, and finally reaches `AuthenticationSuccessHandler`. Therefore:

- `AuthenticationFailureHandler` handles only **the failure of a login attempt**.
- `AuthenticationSuccessHandler` controls **the response after a successful login**.
- The same JSON frontend sometimes needs **both handlers** so it does not receive JSON 401 on a wrong password yet receive HTML 302 on a right password.

## 3. What Is the Signature of AuthenticationFailureHandler?

In Servlet Spring Security 6.x/7.x (Jakarta), the interface:

```java
package org.springframework.security.web.authentication;

public interface AuthenticationFailureHandler {
    void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException;
}
```

This is a **condensed signature for study**, requiring imports for `jakarta.servlet.*`, `jakarta.servlet.http.*`, `java.io.IOException`, and `org.springframework.security.core.AuthenticationException`; not a standalone compilable class.

Three key inputs:

| Parameter | What Does It Provide? | Notes |
| --- | --- | --- |
| `HttpServletRequest` | Path, method, headers, session, correlation ID, client context | All client-supplied values are untrusted data; never trust `username`/`Origin` as proof |
| `HttpServletResponse` | Ability to set status, headers, body, or redirect/forward | Commit the response only once; avoid redirecting after writing a body |
| `AuthenticationException` | Error from the authentication pipeline, such as bad credentials, disabled, expired, locked account… | Internal messages are unsuitable for returning verbatim to users |

**Core contract:** the handler decides the output. It is not an MVC endpoint, does not re-verify passwords, does not perform authorization, and has no reason to see raw passwords.

### 3.1. Authentication Errors Are a Hierarchy, Not HTTP Statuses

Some `AuthenticationException` subclasses:

| Exception | Meaning on Server | Suggested Public Response |
| --- | --- | --- |
| `BadCredentialsException` | Wrong password/token or masked as bad credentials | Generic message "Sign-in failed" |
| `UsernameNotFoundException` | User absent from user store; may be masked as BadCredentials | Never confirm whether the account exists |
| `DisabledException` | Account disabled | Typically keep a generic message, guide to support via proper channel |
| `LockedException` | Account locked | Needs specific policy; avoid letting attackers enumerate users via the endpoint |
| `AccountExpiredException` | Account expired | Do not return internal details in public login responses |
| `CredentialsExpiredException` | Credentials expired | May open a password-change flow **after sufficient verification**, without arbitrary leakage |
| `AuthenticationServiceException` | Authentication infrastructure or service error | Do not confuse with "wrong password", never expose stack traces; consider 503 and alerting |
| `ProviderNotFoundException` | Manager found no provider supporting the Authentication type | Configuration bug for ops to fix, not normal login behavior |

**Do not assume every error means "wrong password".** At the public boundary, many errors should be grouped to prevent enumeration; at the operational boundary, safe categorization, monitoring, and distinguishing dependency failures remain vital so infrastructure outages are not hidden.

## 4. Built-In Standard Handlers in Spring Security

| Class/Mechanism | Behavior | When Appropriate |
| --- | --- | --- |
| `SimpleUrlAuthenticationFailureHandler` | Redirects to `defaultFailureUrl`; without a URL, can send 401 | Form login, simple redirect |
| `formLogin(form -> form.failureUrl("/login?error"))` | Shortcut configuring failure URL | Only a fixed redirect is needed |
| `formLogin(form -> form.failureHandler(...))` | Uses a custom-supplied handler | JSON responses, logging/metrics, branching |
| `ExceptionMappingAuthenticationFailureHandler` | Maps exception class names to URLs | Different flows for specific error types, must prevent enumeration |
| `DelegatingAuthenticationFailureHandler` | Dispatches to handlers based on exception class | Multiple strategies with clear contracts |
| `ForwardAuthenticationFailureHandler` | Internal forward instead of HTTP redirect | Some server-rendered UIs, check render/dispatcher paths |
| `AuthenticationEntryPointFailureHandler` | Uses `AuthenticationEntryPoint` to handle failed attempts | Unify challenge/status emission for HTTP/APIs |

Note: `SimpleUrlAuthenticationFailureHandler` may store the exception in the request or session depending on redirect/forward and `allowSessionCreation`. Never treat `SPRING_SECURITY_LAST_EXCEPTION` as safe data to render raw stack traces or sensitive contents to users.

### 4.1. Shortest Configuration: failureUrl

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated())
        .formLogin(form -> form
            .failureUrl("/login?error")
            .permitAll())
        .build();
}
```

This is a **snippet** inside Servlet configuration. When using Spring's default login page, `/login?error` normally shows a generic login error. If configuring a custom `loginPage("/login")`, the application must provide a controller/template to render that page.

### 4.2. Alternative Configuration: failureHandler

```java
@Bean
AuthenticationFailureHandler failureHandler() {
    return new SimpleUrlAuthenticationFailureHandler("/login?error");
}

@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        AuthenticationFailureHandler failureHandler)
        throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().authenticated())
        .formLogin(form -> form
            .failureHandler(failureHandler)
            .permitAll())
        .build();
}
```

If only a static redirect is needed, `failureUrl(...)` is concise enough; do not invent unnecessary new classes. On one `FormLoginConfigurer`, `failureUrl(...)` is a shortcut that selects a handler; mixing both `failureUrl` and `failureHandler` easily causes confusion about which takes effect last. Pick one primary style and test it.

### 4.3. Redirect vs Forward?

| Criterion | Redirect (usually 302) | Forward (server-internal) |
| --- | --- | --- |
| Browser URL after failure | Changes to failure URL | Can retain original request URL |
| HTTP round trips | One redirect response + new GET | One internal request |
| Request method | Target page GET is usually issued by browser | Forward preserves request context/method per servlet dispatch |
| Exception/flash state | Can be stored in session depending on handler | Can retain request attributes |
| Suitability for SPA/API | Usually poor if API expects JSON | Also poor if API expects JSON |
| Concerns | Open redirect if URL comes from unsafe input | Path, dispatch/authorization, template rendering, and method |

Never redirect to arbitrary URLs taken from a client's `next`/`redirect` query parameter. If post-login redirection is needed, use `RequestCache`/internal destination allowlists or trusted mappings.

## 5. AuthenticationFailureHandler Differs from EntryPoint, AccessDeniedHandler, and ControllerAdvice

This is the most important debugging insight: **the login failure handler is not responsible for every 401/403**.

| Scenario | Primary Component | Typical Outcome |
| --- | --- | --- |
| `POST /login` wrong password, valid CSRF | `UsernamePasswordAuthenticationFilter` → `AuthenticationFailureHandler` | 302 `/login?error` or custom 401 JSON |
| `GET /private`, no Authentication yet | `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | Browser 302 to `/login`; API 401 |
| `GET /admin`, logged in yet missing role | `AuthorizationFilter` → `AccessDeniedHandler` | 403 |
| `POST /login` missing CSRF token | `CsrfFilter`/CSRF access-denied handling | 403, typically **never calls** failure handler |
| Controller `@RequestBody` fails JSON parsing | MVC exception resolver / `@ControllerAdvice` | 400 or defined validation error |
| Custom filter before login filter throws exception | That filter/entry point/chain configuration | Does not automatically call form login's failure handler |
| OAuth2/OIDC callback reports IdP error | Dedicated OAuth2 authentication filter and `oauth2Login` handler | Redirect/error per OAuth2 login config |
| Invalid Bearer token at resource server | Bearer authentication entry point/filter | 401 with `WWW-Authenticate: Bearer` per contract, not form handler |

**Quick mnemonic:** `AuthenticationFailureHandler` is **the result of a failed login attempt**, whereas `AuthenticationEntryPoint` is **the start of login when a user tries to access a protected resource without sufficient authentication**.

### 5.1. Example Distinguishing Three Requests

```http
GET /private/me HTTP/1.1
Host: localhost:8080
```

If anonymous: usually receives `302 Location: /login`. That is the EntryPoint flow, **not** a login failure.

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=learner&password=wrong
```

If CSRF is missing in a CSRF-enabled app: usually receives **403 before the password is checked**. Here the login failure handler does not run.

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...
X-CSRF-TOKEN: <valid-session-token>

username=learner&password=wrong
```

If CSRF is valid and the password is wrong: `AuthenticationFailureHandler` handles it, e.g. redirecting to `/login?error`.

**Common debugging pitfall:** seeing 403 on `POST /login` and trying to fix `failureHandler` is looking in the wrong place. Check the CSRF token, cookie/session, and security chain first.

## 6. Designing Safe Responses for Login Failures

No single HTTP format fits every client type. A **clear** and consistent **contract** is needed.

### 6.1. Form UI: Redirect with a Generic Message

Example:

```http
HTTP/1.1 302 Found
Location: /login?error
Cache-Control: no-store
```

The `/login?error` page can say: **"Unable to sign in. Check your information or try again later."** Avoid:

- "Username does not exist";
- "Password is correct, but user is locked";
- "This email belongs to an administrator";
- Backend details such as SQL exceptions, provider classes, LDAP DNs, or token secrets.

Overly specific messages aid **user enumeration** and account targeting. If a recovery flow exists, make it consistent: e.g., "If the account is valid, instructions will be sent" rather than confirming email existence.

### 6.2. API Client: HTTP 401 + Stable JSON

Illustrative public response for a login endpoint accepting form params yet requesting JSON:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json;charset=UTF-8
Cache-Control: no-store

{"error":"invalid_credentials","message":"Sign-in failed"}
```

This is output **explicitly programmed** in `AuthenticationFailureHandler`, **not formLogin's default JSON**. The JSON body needs a stable error code for the frontend; avoid echoing `request.getParameter("password")` or `exception.getMessage()`.

### 6.3. How Should 401, 403, 429, and 503 Be Interpreted?

- **401 Unauthorized:** authentication request was not accepted; suitable for API login with wrong password or bad token in many contracts.
- **403 Forbidden:** user is authenticated without permission or CSRF validation failed; can appear on POST login missing CSRF even before checking the password.
- **429 Too Many Requests:** rate limiter rejected due to exceeding quota; define an appropriate retry window and avoid enumeration; rate limiting is usually placed **before or around** authentication rather than solely inside the failure handler.
- **503 Service Unavailable:** authentication dependency is unavailable, distinct from a user typing the wrong password; do not turn every outage into 401 and lock out accounts en masse.

**Do not pick statuses mechanically from exception names alone**; consider trust boundaries, threat model, caller, retry behavior, and the API contract. Especially, avoid creating observable response/timing differences between "user exists but disabled" and "user does not exist" when that leaks information.

### 6.4. Headers and Sensitive Data

- `Cache-Control: no-store` to prevent caching responses containing auth-related data.
- `Content-Type: application/json` when returning JSON; set charset/encoding explicitly.
- Never echo tokens, passwords, raw exceptions, stack traces, or internal user IDs.
- When using session cookies, configure `Secure`, `HttpOnly`, appropriate `SameSite`, and HTTPS.
- If responses include a correlation ID, generate it server-side or sanitize before logging; never allow user input to inject dangerous headers.
- CORS allow origins only for trusted frontends; CORS does not replace authentication or CSRF.

## 7. Runnable Example: Spring Boot 3.5.16, Spring Security 6.5, Java 17

This example provides a standard login form that can:

- Fail from a regular browser → redirect to `/login?error`.
- Fail from an HTTP client sending `Accept: application/json` → status 401 + generic JSON.
- Miss CSRF on `POST /login` → 403 before the handler, illustrating the boundary.
- Succeed on login → default Spring SecurityContext/session and grant access to `/private/me`.
- Disabled users receive the exact same **public failure contract** as wrong passwords.

This lesson uses **in-memory users and demo passwords** for local execution; never use this literal data in production. Real projects use a database/directory/IdP and secrets management.

### 7.1. Directory Structure

```text
failure-handler-demo/
├── pom.xml
└── src/
    ├── main/java/demo/login/LoginFailureApplication.java
    └── test/java/demo/login/LoginFailureApplicationTests.java
```

### 7.2. pom.xml File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>failure-handler-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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

No separate artifact is needed for `AuthenticationFailureHandler`: it belongs to `spring-security-web`, pulled in by `spring-boot-starter-security`. `BCryptPasswordEncoder` and `DaoAuthenticationProvider` are also part of standard Spring Security.

### 7.3. LoginFailureApplication.java File

```java
package demo.login;

import java.nio.charset.StandardCharsets;
import java.security.Principal;
import java.util.Map;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LoginFailureApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoginFailureApplication.class, args);
    }
}

@Configuration
class LoginSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("suspended")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .disabled(true)
                .build()
        );
    }

    @Bean
    AuthenticationFailureHandler loginFailureHandler() {
        var browserRedirect =
            new SimpleUrlAuthenticationFailureHandler("/login?error");

        return (request, response, failure) -> {
            // Identical public error payload for missing/locked/disabled/
            // wrong password; never echo failure.getMessage().
            response.setHeader("Cache-Control", "no-store");

            String accept = request.getHeader("Accept");
            boolean wantsJson =
                accept != null && accept.contains("application/json");

            if (wantsJson) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.setCharacterEncoding(
                    StandardCharsets.UTF_8.name());

                response.getWriter().write(
                    "{\"error\":\"invalid_credentials\","
                    + "\"message\":\"Sign-in failed\"}");
                return;
            }

            // HTML browser: preserve default formLogin experience.
            browserRedirect.onAuthenticationFailure(
                request, response, failure);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthenticationFailureHandler loginFailureHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .requestMatchers("/private/**").authenticated()
                .anyRequest().authenticated())

            // CSRF enabled by default. POST /login must include a CSRF token.
            .formLogin(form -> form
                .failureHandler(loginFailureHandler)
                .permitAll())

            .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/private/me")
    Map<String, String> currentUser(Principal principal) {
        return Map.of("user", principal.getName());
    }
}
```

**Reading the code:**

1. `UserDetailsService` has two entries: `learner` enabled; `suspended` disabled. Both have BCrypt password hashes to demonstrate failure paths clearly.
2. `formLogin(...).failureHandler(loginFailureHandler)` registers the handler on the **login processing filter**; the handler is not placed in an MVC controller.
3. `SimpleUrlAuthenticationFailureHandler("/login?error")` provides standard browser/redirect handling; Spring's default UI reads the `error` query param.
4. When a request sends `Accept: application/json`, the custom handler writes a generic 401 JSON response. This is **branching on the Accept header**, not browser authentication or authorization.
5. `HttpSecurity` keeps CSRF enabled by default; without a token, POST is blocked before reaching the provider, so the status code can be 403.
6. The `/private/me` controller receives the user only after Spring authenticates; `Principal` cannot be spoofed with an arbitrary username from the request.
7. The code **does not** tell the user whether the account is disabled or the password was wrong. A production service should log the internal cause per policy without writing passwords or stack traces to public responses.

**Important limitation:** the example branches on `Accept` using a simple substring check. Applications serving multiple content types should use proper `MediaType` parsing/negotiation, handle `q` values, and keep contracts uniform across the API. It also lacks rate limiting/lockout/audit storage.

### 7.4. Running the Application

Requires Java 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

Open `http://localhost:8080/private/me` in a browser: Spring redirects to `/login`. Use:

```text
Username: learner
Password: local-demo-password
```

After successful login, opening `/private/me` yields an illustrative response:

```json
{"user":"learner"}
```

Entering the wrong password redirects the browser to `/login?error`. User `suspended` with the right demo password is also rejected rather than granted a session.

**Do not deploy hardcoded passwords or the username "learner" to real environments.** Secret stores, password policies, HTTPS, rate limiting, and managed user stores are required.

## 8. Detailed Testing with MockMvc

Tests must accurately distinguish the handler from failure paths occurring before or after it. Spring Boot 3.5 uses `@SpringBootTest`, `@AutoConfigureMockMvc`, and `spring-security-test`.

Create `src/test/java/demo/login/LoginFailureApplicationTests.java`:

```java
package demo.login;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginFailureApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ok"));
    }

    @Test
    void anonymousRequestUsesEntryPointNotFailureHandler()
            throws Exception {
        mvc.perform(get("/private/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login")
                /* MockMvc's Location may be relative in some setups */);
    }

    @Test
    void badPasswordRedirectsToGenericLoginError()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void nonexistentUserAlsoGetsGenericLoginError()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "unknown")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void disabledAccountDoesNotRevealCause()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "suspended")
                .param("password", "local-demo-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void jsonClientGets401WithoutInternalError()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .accept(MediaType.APPLICATION_JSON)
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error")
                .value("invalid_credentials"))
            .andExpect(jsonPath("$.message")
                .value("Sign-in failed"));
    }

    @Test
    void missingCsrfIsRejectedBeforeLoginFailureHandler()
            throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validPasswordIsNotHandledAsFailure()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-demo-password"))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Note on redirect tests**: MockMvc can display `Location: /login` or an absolute URL depending on servlet/mock/redirect strategy and proxy context. For tests that remain stable across configurations, replace the exact assertion in the second test with a status check combined with asserting `Location` ends with `/login`, or use `redirectedUrlPattern("**/login")` if the project standardizes URL format. Best practice is not hardcoding `http://localhost/login` when the environment's actual response is `/login`.

Example test independent of absolute Location:

```java
@Test
void anonymousRequestIsRedirectedForAuthentication()
        throws Exception {
    mvc.perform(get("/private/me"))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string("Location",
            org.hamcrest.Matchers.endsWith("/login")));
}
```

To use this snippet, add the static import `MockMvcResultMatchers.header`; it can replace the second test when environment URLs vary.

Run:

```bash
mvn test
```

**Expectation:** after adjusting the `Location` assertion to match your actual Spring/MockMvc configuration, **8 tests pass** given a matching project and dependencies. This is a MockMvc-level HTTP/chain check; it **does not** measure real-world brute-force resilience, real secret stores/IdPs, TLS, or proxy headers.

### 8.1. Why Not Assert Exception.getMessage()?

- Messages depend on provider, locale, user store, and version.
- Detailed content can expose user existence/account status.
- Backends such as LDAP/AD or IdPs have their own error codes.
- Public contracts should be stable around defined **error codes** or error URLs, while server logs hold safe structured reason codes.

### 8.2. Additional Production Tests to Include

- JSON clients with a nonexistent user, wrong password, and disabled account must receive **equivalent public responses** (under the defined policy).
- Invalid CSRF token even with a valid session still returns 403, never invoking the password handler.
- If account lockout/rate limiting exists, test quotas, concurrency, reset windows, time boundaries, and absence of user enumeration.
- Test when the user store is down: must never return 200, and must not lock out users en masse due to fake "bad passwords".
- Test that a session after failure never holds a successful authentication; after success, it holds the right principal.
- Test CORS preflight/login endpoints through ingress when the frontend has a different origin.
- Test that redirects reject external URLs or CRLF characters from query params.
- Test that API/frontend contracts handle 302/401/403 properly, never treating status 200 after a fetch redirect as login success.

## 9. When the Frontend Wants to Send a JSON Body Instead of form-urlencoded

`UsernamePasswordAuthenticationFilter` reads `username` and `password` form-login request parameters by default. It **does not automatically deserialize a JSON body** like:

```http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"learner","password":"secret"}
```

Attaching `failureHandler(...)` changes only **the response when authentication fails**, not the **input reader**. If a frontend genuinely wants JSON login, you can:

1. Design a custom authentication filter using Spring Security's `AuthenticationManager`; the filter parses/validates JSON, invokes the manager, and then uses the same failure/success handlers.
2. Use another standard mechanism fitting the architecture, such as OIDC Authorization Code + PKCE with a backend session or an OAuth2 token flow for eligible clients.
3. Implement a dedicated auth controller, while actively designing `SecurityContextRepository`, CSRF, session fixation, security events, and exception behavior; do not merely call `authenticate()` and issue a DIY cookie.

**Never accidentally turn GET into login using password query parameters.** Passwords must never enter URLs due to browser history, proxy logs, analytics, and Referer headers. If an API accepts a JSON request body, content type, payload limits, request validation, and error contracts must be enforced right at the input filter.

### 9.1. Successful JSON Responses Also Need Design

An SPA might expect:

```json
{
  "user": "learner",
  "authenticated": true
}
```

If you only configure a JSON failure handler while keeping the HTML default success handler, a valid login typically redirects to the saved request or default URL rather than returning the JSON above. For a fully JSON contract, configure a matching **`AuthenticationSuccessHandler`** and ensure Spring Security actually persists the context/session or issues tokens per architecture.

In particular, never return a JWT inside a failure handler or set `"success":true` when the manager rejects credentials.

## 10. When to Use AuthenticationEntryPoint Instead of FailureHandler?

**Case 1 — protected resource, not logged in:**

```text
GET /private/me
  -> AuthorizationFilter: anonymous is insufficient
  -> ExceptionTranslationFilter
  -> AuthenticationEntryPoint
  -> Redirect to login form or HTTP 401
```

**Case 2 — wrong credentials submitted during a login attempt:**

```text
POST /login + valid CSRF
  -> UsernamePasswordAuthenticationFilter
  -> AuthenticationManager
  -> BadCredentialsException
  -> AuthenticationFailureHandler
  -> 302 /login?error or 401 JSON
```

For an API to return 401 instead of redirecting on a sessionless resource, configure an entry point separately:

```java
// Servlet SecurityFilterChain snippet for a truly stateless API:
http.exceptionHandling(ex ->
    ex.authenticationEntryPoint(
        new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)));
```

Imports needed: `org.springframework.http.HttpStatus` and `org.springframework.security.web.authentication.HttpStatusEntryPoint`. This snippet **does not control** the POST login failure branch of a form filter configured with `AuthenticationFailureHandler`.

Use multiple `SecurityFilterChain` beans when a web UI uses form login/sessions while a REST API uses bearer tokens, JSON, and a stateless policy. Never configure a global JSON entry point and accidentally make browser form login return confusing JSON.

## 11. Errors from CSRF, CORS, and AuthorizationFilter Do Not Belong to the Same Handler

### 11.1. CSRF

Session-based form login is an unsafe `POST`, so Spring Security requires a CSRF token by default. When the token is missing/wrong:

- `CsrfFilter` handles and rejects the request, usually with 403.
- `UsernamePasswordAuthenticationFilter` never receives the request to test the password.
- `AuthenticationFailureHandler` has no `BadCredentialsException` to handle.

**Do not disable CSRF** app-wide just to watch the failure handler trigger in Postman. Obtain a valid CSRF token, preserve the session cookie, and send it on POST; in MockMvc, use `with(csrf())` for both login success and failure tests.

### 11.2. CORS

Preflight OPTIONS requests to a login endpoint usually carry no session cookie; CORS must be handled before authentication. When a cross-origin frontend sees a "CORS" error, do not fix it by having a handler return `Access-Control-Allow-Origin: *` or treating origin as identity.

Configure CORS using a trusted allowlist, `http.cors(...)`, and an appropriate `CorsConfigurationSource`. The backend still needs credential checks on POST login and CSRF for browser-session requests.

### 11.3. Missing Role

Being logged in without the required role is an **authorization failure**. `AccessDeniedHandler` (typically via `ExceptionTranslationFilter`) handles it and can return 403. Never send users back to `/login?error` as if their password were wrong; that causes confusion and endless login loops.

## 12. Handling Exceptions by Type: Prevent User Enumeration

Spring provides `ExceptionMappingAuthenticationFailureHandler` and `DelegatingAuthenticationFailureHandler` to route based on `AuthenticationException` subclasses. Conceptual example:

```java
// Configuration snippet, not a standalone Java class.
var handler = new ExceptionMappingAuthenticationFailureHandler();
handler.setDefaultFailureUrl("/login?error");
handler.setExceptionMappings(Map.of(
    CredentialsExpiredException.class.getName(),
    "/account/recovery"));
```

This can help applications with a dedicated secure flow for expired credentials. However, the **risk** is that an attacker tries many usernames and watches redirects to learn which accounts exist/have expired.

Principles:

1. Transition to a special flow only after the caller provides sufficient proof of identity, or the flow is designed to resist enumeration.
2. Keep response content/timing similar between nonexistent users and wrong passwords whenever feasible.
3. Even when showing a generic error, you can log internal reason codes with minimal metadata for incident response.
4. Never return exception class names, LDAP codes, DB IDs, or stack traces to public clients.
5. For infrastructure errors, manage statuses/retries separately; do not downgrade them to `BadCredentialsException` if that masks outages and triggers false lockouts.

**Bad idea:** "On DisabledException redirect to /disabled-user?username=alice, on BadCredentialsException to /wrong-password". That creates an account-enumeration oracle.

## 13. Failure Handler and Remember-Me/Session Boundaries

A failed login request must not create a new successful Authentication. However, session design needs a broader view:

- A browser might already hold a **previously authenticated session** and submit another login attempt; depending on chain and security context lifecycle, test reauthentication policy and existing session handling rather than guessing from status codes alone.
- `unsuccessfulAuthentication(...)` clears the SecurityContext for the request and calls `RememberMeServices.loginFail(...)`, yet requirements to log out, invalidate sessions, or clear custom cookies must be explicitly designed for your threat model.
- CSRF tokens can rotate on login/logout per Spring's strategy; after a successful login, an SPA frontend may need to fetch the new token.
- Never store raw passwords in the session or `SPRING_SECURITY_LAST_EXCEPTION`; avoid rendering exception objects directly in templates.
- When using `SimpleUrlAuthenticationFailureHandler`, pay attention to `allowSessionCreation`, `useForward`, and the failure URL; do not blindly invalidate every session on a bad login if that breaks state needed by the login UI or causes DoS.

For high-security requirements, after multiple failed logins you can enforce reauthentication, clear remember-me, or invalidate sessions per policy. **Do this intentionally and with tests**, never inside a generic handler without analyzing UX and session fixation.

## 14. Brute Force, Credential Stuffing, and Rate Limiting

A handler returning a neat message **is not brute-force protection**. Credential-attempt limits are needed before or around the authentication flow.

### 14.1. Defense Layers

- Rate limit by IP, IP range, normalized user identifier, and device/client signals where appropriate; prevent attackers from rotating IPs to evade quotas.
- Account lockout policies with DoS mitigation (attackers intentionally locking out other users).
- Progressive delays/step-up challenges in risky scenarios; avoid creating differences strong enough for enumeration.
- Monitor failure counts, login success/failure ratios, anomalous traffic sources, and password spraying.
- Use proper password hashes like Argon2id/bcrypt/scrypt for stored passwords; never compare plaintext.
- Enforce HTTPS, session/cookie security, MFA, and passkeys when appropriate.
- After password reset or account recovery, consider invalidating sessions/tokens per policy and notifying the user.

### 14.2. Why Not Just Sleep Inside AuthenticationFailureHandler?

Anti-pattern:

```java
// WRONG for production: blocks servlet worker threads while attackers spam.
Thread.sleep(5000);
```

If every failed login holds a request thread for 5 seconds, attackers can trigger **denial-of-service**. Rate limiting should be implemented by a gateway/service storing proper state with concurrency control and circuit breakers. If done in-process in Java, account for multiple instances/restarts and avoid per-username/IP memory leaks.

### 14.3. Safe Logging

Log **events**, never log secrets:

```text
event=AUTH_LOGIN_FAILURE
request_id=<server-generated-id>
result=DENIED
reason_code=BAD_CREDENTIALS
client_ip=<validated-proxy-aware-address>
user_ref=<safe-pseudonymous-reference>
provider=form_password
```

This is an **illustrative log schema**, not Spring's default output. Internal reason codes can be more detailed than public responses yet must comply with privacy/retention policies; avoid logging raw usernames unnecessarily. Never log passwords, CSRF tokens, session IDs, bearer tokens, or stack traces containing sensitive data.

**Note:** `request.getRemoteAddr()` is the servlet's actual socket peer address, which may be a reverse proxy; trust `X-Forwarded-For`/Forwarded only when rewritten by a managed proxy and the application configures a proper trust boundary. Never trust arbitrary headers from the internet as authoritative rate-limiting keys.

## 15. API Error Contract and Problem Details

For backends serving SPAs, you can use stable error codes and optionally RFC 9457 Problem Details:

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Sign-in failed",
  "instance": "/login"
}
```

If using media type `application/problem+json`, apply appropriate schema/serialization, content negotiation, and HTTP status; this is an **illustrative contract design**, not something Spring form login generates out of the box. Never stuff raw `AuthenticationException.getMessage()` into `detail`.

Distinguish request format errors from auth errors:

| Scenario | Suggested Contract | Goes Through Form Failure Handler? |
| --- | --- | --- |
| Malformed JSON in custom JSON login filter | 400 Bad Request | Depends on custom filter/exception handler |
| Properly formatted username/password, wrong credentials | 401 Unauthorized (JSON) | Yes, if filter routes `AuthenticationException` to failure handler |
| POST missing CSRF token | 403 Forbidden | Usually no |
| Login throttled by quota | 429 Too Many Requests | Depends on where limiter sits; not by default |
| Auth backend disconnected | 503 Service Unavailable if contract/policy fits | Possibly if wrapped as AuthenticationException, yet monitor separately |
| Logged in, missing role | 403 Forbidden | No; AccessDeniedHandler |
| Protected GET, not logged in | 302 `/login` or 401 API | No; AuthenticationEntryPoint |

**Never build an API contract dependent on a localized error message.** Frontends should rely on `error`/`type` and HTTP status; display text can vary by language.

## 16. Custom Authentication Filters Must Handle Errors in the Right Place

Not every login uses `UsernamePasswordAuthenticationFilter`. When writing a custom API key/JWT login filter:

1. Read and validate credentials from the request.
2. Build an unauthenticated `Authentication`.
3. Call `AuthenticationManager.authenticate(...)`.
4. On failure, **invoke the appropriate failure handler or entry point**; do not let exceptions bubble up into a 500 by default.
5. On success, populate SecurityContext, apply the right session strategy/repository or token issuance per architecture, and invoke the success handler.
6. Clear sensitive credentials, clear context when needed, and never log secrets.

Illustrative **logic snippet inside a custom filter**, not a full runnable class:

```java
try {
    Authentication accepted = authenticationManager.authenticate(
        new UsernamePasswordAuthenticationToken(username, password));

    SecurityContext context =
        SecurityContextHolder.createEmptyContext();
    context.setAuthentication(accepted);
    SecurityContextHolder.setContext(context);

    // Stateful login also requires session strategy,
    // SecurityContextRepository.saveContext(...),
    // success handler, CSRF/session lifecycle.
} catch (AuthenticationException failed) {
    SecurityContextHolder.clearContext();
    failureHandler.onAuthenticationFailure(
        request, response, failed);
    return;
}
```

This code is **not standalone** and **not complete for a production login filter**: it lacks declarations for `authenticationManager`, `failureHandler`, request/response, context/session persistence steps, remember-me, and success handling. Its sole purpose is showing where to handle the exception.

**Never treat a catch-all `Exception` returning 401 as safe.** Null pointers, DB errors, IOException, serialization issues, or internal bugs are not credential failures. Catch `AuthenticationException` per contract, and route technical faults into a controlled error pipeline with monitoring and 5xx responses when appropriate.

## 17. OAuth2/OIDC, Bearer Tokens, and WebFlux Have Their Own Handlers

### 17.1. OAuth2/OIDC Login

In Spring Security Servlet, `oauth2Login()` has its own authentication filter handling authorization responses/callbacks. You can configure:

```java
// Configuration snippet, requires OAuth2 Client dependencies and a real IdP:
http.oauth2Login(oauth -> oauth
    .failureHandler(customOAuth2FailureHandler));
```

Do not assume `formLogin(...).failureHandler(...)` automatically handles `invalid_state`, OAuth2 callbacks, token exchanges, or OIDC ID Token validation errors. Redirect back to the frontend only with **generic error codes**, never putting authorization codes, ID tokens, or raw provider error details in URLs/logs.

### 17.2. Resource Server / Bearer

An API accepting bearer tokens on resource calls does not necessarily have a "login endpoint" using the same filter. Invalid bearer tokens are usually handled by `BearerTokenAuthenticationEntryPoint`, returning HTTP 401 with `WWW-Authenticate: Bearer`; missing scopes/permissions can become 403. Never return HTML `/login?error` to a machine client calling a REST API.

### 17.3. WebFlux/Reactive

In WebFlux, the interface is:

```java
// Reactive API signature (illustrative, not a full class):
Mono<Void> onAuthenticationFailure(
    WebFilterExchange webFilterExchange,
    AuthenticationException exception);
```

Use `ServerAuthenticationFailureHandler` and `SecurityWebFilterChain` accordingly. Do not import `jakarta.servlet.http.HttpServletResponse` to handle reactive login.

## 18. Common Pitfalls and Debugging Workflow

| Symptom | Likely Cause | How to Distinguish |
| --- | --- | --- |
| POST /login wrong password returns 403 instead of redirect | Missing/invalid CSRF token | Check CsrfFilter, session cookie, and token |
| POST /login returns 404 | Wrong `loginProcessingUrl`, matcher/filter chain, or conflicting MVC route | Check URL, method, SecurityFilterChain |
| Handler never runs despite wrong password | Request did not match login filter or was blocked by an earlier filter | Enable controlled DEBUG logs and inspect filter order |
| Handler runs but causes redirect loop | Failure URL also requires authentication or misconfigured EntryPoint | `formLogin(...).permitAll()` and login page mapping |
| JSON frontend receives HTML /login?error | Handler redirects instead of JSON or Accept mismatch | Check Content-Type/Accept and handler config |
| JSON login wrong password gets 401, right password gets 302 | Changed only failure handler, forgot success handler | Design both success and failure branches |
| Nonexistent username returns different response than locked user | Overly specific exception mapping | Standardize public responses, consider timing |
| No 401/302 when unauthenticated hitting protected resource | Overly broad authorization matcher, `permitAll()` hides route | Check `authorizeHttpRequests` and multiple chains |
| Disabled account can still log in | Provider/custom authentication skips account status check | Check UserDetailsChecker/provider contract |
| All infrastructure errors return "wrong password" | Catch-all converts exceptions to BadCredentials | Preserve service error classification and monitoring |
| 500 when custom filter encounters bad key | Exception escapes filter before ExceptionTranslationFilter | Custom filter catches AuthenticationException, invokes handler |
| Failed browser login retains old user | Misconfigured session/security context lifecycle | Test reauthentication, context clearing, and session policy |
| Logged error contains plaintext password | Handler/logging records raw request params | Redact secrets in app, proxy, APM, and error pipeline |
| Rate limiting ineffective across multiple nodes | Counters kept only in per-node memory | Use an appropriate store/distributed limiter |
| Mixing up credential errors and user permissions | Using AuthenticationFailureHandler to handle 403 authorization | Use proper AccessDeniedHandler |

Inspection checklist order:

1. Does the request enter **the right SecurityFilterChain**? Do path, method, and context path match?
2. For form login, does the POST carry a valid CSRF token and matching session cookie?
3. Does `UsernamePasswordAuthenticationFilter` intercept the request?
4. Which provider is `AuthenticationManager` calling? What exact exception appears in internal logs?
5. Does `unsuccessfulAuthentication(...)` invoke the configured `AuthenticationFailureHandler`?
6. Does the handler return 302/401/JSON matching `Accept` and contract?
7. Is the failure URL anonymously accessible? Does the browser enter a redirect loop?
8. Does any gateway/CORS/proxy alter Location, cookies, headers, or caching?
9. Are username existence, account status, passwords, tokens, or exception details leaked?
10. Are rate limiting, auditing, and concurrency tests in place?

Spring Security debugging in test environments can raise security log categories, but **never enable wire request logging recording usernames/passwords/session tokens in production**.

## 19. Self-Check Exercises

1. **What is typically invoked on wrong password at `POST /login`?** `AuthenticationFailureHandler` inside the authentication filter that processed the request.
2. **Which handler handles unauthenticated GET `/admin`?** Usually `AuthenticationEntryPoint` following the `ExceptionTranslationFilter` flow.
3. **How is a logged-in user lacking `ROLE_ADMIN` handled?** Authorization/access-denied (typically 403), not the form failure handler.
4. **Why does POST /login missing CSRF return 403 even with a wrong password?** `CsrfFilter` rejects the request before the authentication attempt.
5. **What is the default `failureUrl` for form login?** Usually `/login?error`.
6. **Why should `exception.getMessage()` not be returned to the client?** It can expose account status, provider details, or internal data, aiding enumeration.
7. **For a JSON SPA, is replacing only failureHandler enough?** No; success handler, input parsing, and session/token contracts must also match.
8. **Is a JSON body `{"username":...}` read automatically by UsernamePasswordAuthenticationFilter?** No; the form filter reads request parameters by default.
9. **How does `SimpleUrlAuthenticationFailureHandler` differ from `AuthenticationFailureHandler`?** The interface is the contract; the class is a common implementation for redirect/forward/401.
10. **Should DisabledException always redirect publicly to a separate URL?** No; account enumeration and recovery flows must be evaluated.
11. **Can `@ControllerAdvice` catch every exception from authentication filters?** Not guaranteed; authentication filters execute before MVC controllers/exception resolvers.
12. **Should rate limiting live only inside the failure handler?** No. Limits are needed at the request/authentication/gateway layer with proper state and DoS protection.
13. **Why must a failed login never produce a valid SecurityContext?** Because credential verification failed; issuing a session would bypass authentication.
14. **Why does a Resource Server normally not redirect to `/login?error`?** Machine clients expect 401/403 and bearer challenges, not HTML login pages.
15. **When should a custom handler be used?** When custom response contracts, metrics/audits, or safe custom routing are needed—not just to change a simple failure URL.

## 20. Official References

- Spring Security – Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security – Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – AuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html
- Spring Security – SimpleUrlAuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html
- Spring Security – AbstractAuthenticationProcessingFilter API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
- Spring Security – ExceptionMappingAuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/ExceptionMappingAuthenticationFailureHandler.html
- Spring Security – DelegatingAuthenticationFailureHandler API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationFailureHandler.html
- Spring Security – AuthenticationEntryPoint API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
- Spring Security – CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – MockMvc Security Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Credential Stuffing Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Credential_Stuffing_Prevention_Cheat_Sheet.html
- RFC 9457 – Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
