# Customizing Success, Failure, and Logout Responses in Spring Security

> **Context:** Spring Security on **Servlet/Spring MVC**, Spring Boot 3.x, Java 17+. Part of the **Extension Points** group. This lesson explains the exact extension points of the login, failed login, and logout flows; and shows how to customize HTTP responses for HTML UIs and API clients while preserving session, CSRF, and authorization protections.

## 1. Why Customize Responses?

Spring Security already provides useful defaults for form-based web apps: successful login normally redirects to the original or default page; failure normally returns to the login page with an error indicator; logout redirects to the login page. However, an application may need:

- HTML UI: redirect to `/dashboard`, `/login?error`, or `/login?logout`; record state needed by the UI.
- SPAs or API clients: return **200 with JSON** on login success, **401 with JSON** on invalid credentials, **204 with no body** on logout.
- Business policies: classify errors on the server without revealing whether a user exists; record audit events, handle saved requests, or synchronize login state on the UI.
- Distinguish **failed login** from an unauthenticated client calling another endpoint, and distinguish local logout from token revocation in an external system.

Customizing responses changes how **results are delivered to the client** after Spring Security has processed authentication or logout; it does not mean a custom handler may arbitrarily skip authentication, `SecurityContext` persistence, session fixation protection, CSRF, or session cleanup.

### Learning Objectives

After this lesson, you should be able to:

1. Correctly locate `AuthenticationSuccessHandler`, `AuthenticationFailureHandler`, `LogoutHandler`, and `LogoutSuccessHandler` in the filter chain.
2. Distinguish `401` for failed login from `401` for unauthenticated resource access, `403` for missing permissions or invalid CSRF, and `200/204/3xx` for successful responses.
3. Write a Java 17+ `SecurityFilterChain` configuration using the `formLogin`, `logout`, and `exceptionHandling` DSLs.
4. Maintain CSRF with session cookies and understand why a fresh CSRF token must be fetched after login/logout.
5. Test the full flow: success, failure, missing CSRF token, logout, and post-logout access.

## 2. Placing Handlers at the Right Stage

```text
Browser / client
  |
  +-- POST /api/auth/login (username, password, CSRF token)
  |       |
  |       +-- CsrfFilter: requires valid token if CSRF is enabled
  |       |
  |       +-- UsernamePasswordAuthenticationFilter
  |                |
  |                +-- AuthenticationManager.authenticate(...)
  |                          |
  |                          +-- SUCCESS
  |                          |      -> session/security-context processing
  |                          |      -> AuthenticationSuccessHandler
  |                          |           -> 302 redirect or 200 JSON
  |                          |
  |                          +-- FAILURE
  |                                 -> AuthenticationFailureHandler
  |                                      -> 302 redirect or 401 JSON
  |
  +-- GET /api/private (unauthenticated)
  |       -> AuthenticationEntryPoint -> usually 401 or redirect
  |
  +-- GET /api/private (authenticated but missing permission)
  |       -> AccessDeniedHandler -> usually 403
  |
  +-- POST /api/auth/logout (valid CSRF token)
          |
          +-- LogoutFilter -> LogoutHandler(s): clean up session/context/token
          |
          +-- LogoutSuccessHandler -> 302 redirect, 204 or 200 JSON
```

This is a **conceptual model**, not an exhaustive ordering list of every filter. HTTP Basic, Bearer JWT, OAuth2, and form login have different processing components. Ordering and error handling also depend on which `SecurityFilterChain` matches the request.

Four easily confused names:

| Component | When does it run? | Primary responsibility | Response examples |
| --- | --- | --- | --- |
| `AuthenticationSuccessHandler` | The corresponding authentication filter reports success | Decide how to return the result/destination after login | 302 to dashboard or 200 JSON |
| `AuthenticationFailureHandler` | A **login attempt** fails in an authentication filter | Return the result for a bad login attempt | 302 `/login?error` or 401 JSON |
| `LogoutHandler` | During **logout execution** | Clean up `SecurityContext`, session, remember-me, CSRF, related resources | Usually does not directly decide the final body |
| `LogoutSuccessHandler` | After the logout handler chain finishes | Decide the final response after logout | 302, 204, 200 JSON |

Other components have distinct meanings:

- `AuthenticationEntryPoint`: a request reached a protected resource and needs to initiate authentication; there was not necessarily a prior **failed POST login**.
- `AccessDeniedHandler`: a request was denied for insufficient permissions, or an error like invalid CSRF classified accordingly; not a wrong-password attempt.
- `@RestControllerAdvice`: handles exceptions within the MVC lifecycle; responses produced by security filters usually **do not pass through** advice automatically.
- `AuthenticationEventPublisher` or listeners: receive success/failure events decoupled from the servlet response. Use events for auditing or metrics when appropriate; response handlers should not become the home for all business logic.

## 3. Default Behavior of Form Login

With `formLogin` on the Servlet stack, Spring Security uses an authentication filter to process credentials from a form. By default, the login processing request is **POST `/login`** with form parameters `username` and `password`; the login page and redirect targets can be generated or configured by Spring Security.

### 3.1. Successful Login

`SavedRequestAwareAuthenticationSuccessHandler` is commonly used as the default success handler. When a user visits a URL requiring authentication, `ExceptionTranslationFilter` can save the original request via `RequestCache`. After login, the success handler prioritizes sending them back to the saved URL, if present, before falling back to the default target.

Example:

```text
GET /reports/weekly    -> requires login, saves target request
GET /login             -> renders form
POST /login            -> authentication succeeds
302 Location: /reports/weekly
GET /reports/weekly    -> new request now has authenticated session
```

If you replace the success handler with a lambda that always returns 200 JSON, the saved redirect **will no longer happen automatically**. This may be desired for an SPA; the client handles navigation according to the API contract. If you want to preserve returning to the original page on an HTML site, keep or configure `SavedRequestAwareAuthenticationSuccessHandler` rather than hastily writing a new redirect handler.

### 3.2. Failed Login

When `AuthenticationManager` rejects the credentials, the matching filter invokes `AuthenticationFailureHandler`. With Spring Security's default form login configuration, the browser is normally redirected back to the login page with an error parameter (e.g., `/login?error`); with a custom failure handler, status and body can change.

**Do not assume every failed login returns 401:** that is usually the right policy for APIs, whereas web form redirects normally use HTTP 302. If `CsrfFilter` rejects the request before it reaches the authentication filter, the failure handler **is not called** and the result is normally 403.

### 3.3. Logout

Spring Security supports `POST /logout` by default to perform logout. When CSRF is enabled, `GET /logout` may render a confirmation page, while the actual logout request requires the matching HTTP method and CSRF token. After cleanup, the default `LogoutSuccessHandler` normally redirects to `/login?logout`.

The default logout chain can clean up the session, `SecurityContextHolder`, `SecurityContextRepository`, remember-me, and CSRF token via appropriate `LogoutHandler` implementations. **Do not replace this entire chain with a controller that only calls `session.invalidate()`** without understanding all the components that need cleanup.

## 4. Choosing the HTTP Contract for Each Application Type

Both response styles can be right; choose based on invocation method and UI behavior.

| Event | Page-navigating HTML web app | Session-based API for SPA |
| --- | --- | --- |
| Login succeeds | 302 to saved page or dashboard | 200 JSON such as `{"code":"LOGIN_OK"}` |
| Login with wrong credentials | 302 to page with error message | 401 JSON such as `{"code":"INVALID_CREDENTIALS"}` |
| Accessing resource unauthenticated | 302 to login page | 401 `AUTH_REQUIRED` |
| Logged in but lacking permission | 403 or corresponding error page | 403 JSON `FORBIDDEN` |
| Missing/invalid CSRF | 403 | 403, client must fetch a valid token |
| Logout succeeds | 302 `/login?logout` | 204 No Content or 200 JSON |
| Logout rejected due to CSRF | 403 | 403; do not pretend the session was cleared |

**204 No Content** must not include a JSON body. If you need to return a payload like `{"code":"LOGOUT_OK"}`, choose 200. Never return 200 for failed logins merely to make UI handling easier: that breaks HTTP semantics, logging, and error detection.

The JSON payloads in this lesson are **application contract examples**, not response structures auto-generated by Spring Security. For public APIs, standardize schemas, content types, status codes, and stable error codes.

## 5. Customizing Redirects for HTML Web Apps

If the application is a server-rendered website and wants to keep using redirects, a concise configuration is usually enough:

```java
@Bean
SecurityFilterChain htmlSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(form -> form
            .loginPage("/login")
            .defaultSuccessUrl("/dashboard", false)
            .failureUrl("/login?error")
            .permitAll()
        )
        .logout(logout -> logout
            .logoutSuccessUrl("/login?logout")
            .permitAll()
        );
    return http.build();
}
```

This is a **configuration snippet inside a `@Configuration` class**, requiring imports for `@Bean`, `HttpSecurity`, and `SecurityFilterChain`. When using `loginPage("/login")`, the application itself must provide the GET `/login` endpoint/view and the login POST form with a CSRF token. Spring Security does not auto-generate HTML for a custom login page.

Meaning of `defaultSuccessUrl("/dashboard", false)`:

- `false`: when a valid *saved request* exists, prioritize that request; otherwise go to `/dashboard`.
- `true`: always use `/dashboard`, even when a saved request exists; consider the UX impact.
- `failureUrl` typically maps to `SimpleUrlAuthenticationFailureHandler`; specific messages should be rendered by the UI, avoiding exception details in query strings.

**Do not configure both `defaultSuccessUrl(...)` and a custom `successHandler(...)` expecting both strategies to drive the response.** The handler configured last can override the previous strategy depending on setup; pick one clear policy and test it.

### 5.1. Redirecting by role or context

An `AuthenticationSuccessHandler` can redirect to different pages based on permissions. Logic example:

```java
AuthenticationSuccessHandler handler = (request, response, authentication) -> {
    boolean isAdmin = authentication.getAuthorities().stream()
        .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    response.sendRedirect(request.getContextPath()
        + (isAdmin ? "/admin/home" : "/dashboard"));
};
```

This snippet is an **optional illustration**: you must register the handler via `formLogin(...successHandler(handler))` and ensure the target routes are protected accordingly. Redirecting by role **does not replace** permission checks on routes and services. For pages that triggered login via an initial URL, role-based redirects may bypass saved requests; consider `SavedRequestAwareAuthenticationSuccessHandler` if you want to preserve that.

**Prevent open redirects:** never call `response.sendRedirect(request.getParameter("next"))` using an arbitrary client-supplied URL. Only allow verified internal paths/allowlists, and still enforce authorization at the destination; never let clients force redirects to external domains or ambiguous URLs.

## 6. Spring Boot Demo: JSON for Login, Failed Login, and Logout

The demo below builds a **session-based API** for the same origin. It demonstrates all handlers in their proper places. Login/logout requests use a session cookie and CSRF token. This is a learning example; hard-coded accounts/passwords are **for local environments only**.

File layout:

```text
security-responses-demo/
  build.gradle
  settings.gradle
  src/main/java/com/example/securityresponses/
    SecurityResponsesApplication.java
    SecurityConfig.java
    DemoApiController.java
  src/test/java/com/example/securityresponses/
    AuthResponseTest.java
```

### 6.1. `settings.gradle`

```groovy
rootProject.name = 'security-responses-demo'
```

### 6.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Requires JDK 17+ and a Gradle version compatible with the plugin in the example; if using the project's Gradle wrapper, run `./gradlew` instead of `gradle`. When integrating into a repo with shared build logic, follow the version management system already in use.

### 6.3. `SecurityResponsesApplication.java`

```java
package com.example.securityresponses;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityResponsesApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityResponsesApplication.class, args);
    }
}
```

### 6.4. `SecurityConfig.java` — complete and self-contained

```java
package com.example.securityresponses;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, ObjectMapper objectMapper) throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/auth/csrf").permitAll()
                .requestMatchers("/api/private").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .loginProcessingUrl("/api/auth/login")
                .successHandler((request, response, authentication) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_OK,
                        Map.of(
                            "code", "LOGIN_OK",
                            "username", authentication.getName()
                        ))
                )
                .failureHandler((request, response, exception) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_UNAUTHORIZED,
                        Map.of("code", "INVALID_CREDENTIALS"))
                )
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((request, response, authentication) ->
                    response.setStatus(HttpServletResponse.SC_NO_CONTENT)
                )
                .permitAll()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, exception) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_UNAUTHORIZED,
                        Map.of("code", "AUTH_REQUIRED"))
                )
                .accessDeniedHandler((request, response, exception) ->
                    writeJson(response, objectMapper,
                        HttpServletResponse.SC_FORBIDDEN,
                        Map.of("code", "FORBIDDEN"))
                )
            );

        // Do not call csrf.disable(): session cookies are used for browsers.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(user);
    }

    private static void writeJson(
            HttpServletResponse response,
            ObjectMapper mapper,
            int status,
            Map<String, String> payload) throws IOException {

        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");
        mapper.writeValue(response.getOutputStream(), payload);
    }
}
```

**What each part does:**

- `authorizeHttpRequests`: permits fetching a CSRF token before login; `/api/private` requires authentication; all other paths are denied except the login/logout endpoints opened by their respective configurers via `permitAll()`.
- `formLogin.loginProcessingUrl("/api/auth/login")`: the filter accepts **POST form-urlencoded** with `username` and `password` params after passing CSRF; it **does not automatically parse JSON** such as `{"username":"...","password":"..."}`.
- `successHandler`: when authentication succeeds, returns **200** and JSON containing `code` and `username`. Spring Security completes the standard authentication steps before this handler writes the response; the handler does not save `SecurityContext` itself.
- `failureHandler`: when credentials are invalid or the authentication filter reports failure, returns **401** with a generic error code, never returning `exception.getMessage()` verbatim.
- `logout.logoutUrl`: uses the framework's `LogoutFilter`; with CSRF enabled, logout is performed via **POST** with a valid token.
- `logoutSuccessHandler`: after cleanup, returns **204** with no body. `authentication` in the logout success handler may be `null`, so do not rely on it to assert a prior valid session.
- `exceptionHandling.authenticationEntryPoint`: when another request needs login, returns `401 AUTH_REQUIRED`. This case is **distinct** from `401 INVALID_CREDENTIALS` on a failed login attempt.
- `exceptionHandling.accessDeniedHandler`: returns `403 FORBIDDEN` when Security denies permissions or CSRF. Production systems may want a dedicated CSRF error code in server logs while avoiding unnecessary information disclosure.
- `PasswordEncoder` and `UserDetailsService`: the demo `learner` account stores a BCrypt password in memory; use a real database/identity provider when deploying.
- `ObjectMapper`: serializes JSON properly instead of string concatenation; every JSON response uses UTF-8 encoding and avoids caching.

**Note:** the demo password is fixed only for ease of testing. Never ship this configuration as-is to production. Some products need an HTML login page or different paths; when switching to a JSON schema, callers must clearly understand the session and CSRF contracts.

### 6.5. `DemoApiController.java`

```java
package com.example.securityresponses;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoApiController {

    @GetMapping("/api/auth/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @GetMapping("/api/private")
    public Map<String, String> privateData(Authentication authentication) {
        return Map.of(
            "message", "Hello",
            "username", authentication.getName()
        );
    }
}
```

`/api/auth/csrf` is the endpoint to obtain the CSRF token issued by Spring Security for the request. The result contains fields corresponding to `token`, `headerName`, and `parameterName`. For session-based applications, the client keeps the accompanying session cookie; on state-changing requests it must send the token in the matching header/parameter. This is the pattern documented by Spring Security for clients that actively fetch CSRF tokens.

**Do not confuse a CSRF token with an access token:** it protects cookie/session-dependent operations from cross-site request forgery; it is not a login credential and does not grant resource access. A client is considered authorized only when both the session cookie and the appropriate authentication mechanism succeed.

### 6.6. Verifiable HTTP Sequence

With the application running on `localhost:8080`, preserve the cookie jar **across all requests**. On a Bash environment with `curl` and `jq`, use the following example:

```bash
# 1) Obtain session cookie and CSRF token before login.
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/auth/csrf | jq -r '.token')

# 2) Send login credentials as form parameters, along with the CSRF token.
curl -i -c cookies.txt -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo-password" \
  http://localhost:8080/api/auth/login

# 3) The cookie jar from login now holds the authenticated session.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/private

# 4) Fetch a fresh CSRF token after login (the old token may have been rotated).
TOKEN=$(curl -sS -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/auth/csrf | jq -r '.token')

# 5) Logout via POST with the token; 204 only, no body.
curl -i -X POST -c cookies.txt -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  http://localhost:8080/api/auth/logout

# 6) Logged-out session: the private route no longer returns data.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/api/private
```

In step 2, the sample code supports only `application/x-www-form-urlencoded`: `--data-urlencode` tells curl to send a proper POST form. You cannot swap the body for JSON and expect `UsernamePasswordAuthenticationFilter` to read it. If an app needs **JSON login**, you must implement a mechanism to convert the request into an `Authentication` and test security context persistence, session fixation, and failure handling; that is a different authentication design.

**Expected status/body:** login success response has `200` and JSON `LOGIN_OK`; private GET has `200` and name `learner`; POST logout has `204` and empty body; private GET after logout has `401 AUTH_REQUIRED`. Session cookie headers and tokens are dynamic values; do not hard-code or compare them against sample strings.

**Testing bad credentials separately:** before a successful login, fetch the CSRF token as in step 1 and send `password=wrong` to `/api/auth/login`. Expect `401 INVALID_CREDENTIALS`, not `401 AUTH_REQUIRED`. If you omit the CSRF header, the request may be blocked with `403 FORBIDDEN` **before** password verification, so that test would not exercise the failure handler.

### 6.7. Why Fetch a New CSRF Token After Login and Logout?

In Spring Security, strategies such as `CsrfAuthenticationStrategy` and `CsrfLogoutHandler` normally discard the old CSRF token upon successful login or logout. This supports a token lifecycle tied to authentication state. Consequently, an SPA/session client should:

1. Fetch a token on app startup or before the first unsafe request.
2. Send the token along with the session cookie on the login POST.
3. **Re-fetch the token after login** before subsequent unsafe requests.
4. Send the new token on the logout POST.
5. **Re-fetch the token after logout** before subsequent write operations, if the UI remains interactive.

In Spring Security 6.x, CSRF tokens may be processed via `XorCsrfTokenRequestAttributeHandler` to protect against BREACH. Use the token returned by the Spring Security endpoint; **do not guess or alter the encoding**. CSRF token exchange differs across server-rendered apps, SPAs, and cookie repositories. Configuring `CookieCsrfTokenRepository.withHttpOnlyFalse()` so JavaScript can read the cookie also requires careful review of SPA handlers and your security policy; do not swap it into session endpoints casually.

## 7. Testing with MockMvc

The demo project already includes `spring-security-test`. File `src/test/java/com/example/securityresponses/AuthResponseTest.java`:

```java
package com.example.securityresponses;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthResponseTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginSuccessReturnsJson200() throws Exception {
        mvc.perform(post("/api/auth/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-password"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("LOGIN_OK"))
            .andExpect(jsonPath("$.username").value("learner"));
    }

    @Test
    void wrongPasswordReturnsJson401() throws Exception {
        mvc.perform(post("/api/auth/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("INVALID_CREDENTIALS"));
    }

    @Test
    void anonymousPrivateRequestUsesEntryPoint() throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("AUTH_REQUIRED"));
    }

    @Test
    void missingCsrfTokenReturns403() throws Exception {
        mvc.perform(post("/api/auth/login")
                .param("username", "learner")
                .param("password", "demo-password"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void logoutReturns204WithoutBody() throws Exception {
        mvc.perform(post("/api/auth/logout")
                .with(user("learner"))
                .with(csrf()))
            .andExpect(status().isNoContent());
    }
}
```

These tests prove **the exact response-handling extension points**. `with(csrf())` is a test utility supplying a valid CSRF token, not an indication that production can omit tokens. `with(user("learner"))` creates a user context for the logout test; real cookie and live session behavior still needs HTTP verification as in section 6.6. Never use `@WithMockUser` to "test login": it bypasses the credential verification being tested.

For stricter verification, add tests checking session persistence after successful login, inability to reach private endpoints after logout, fixation protection, absence of leaked credential messages, and cookie attributes in a real environment. `MockMvc` does not replace reverse proxy/HTTPS/browser cookie behavior.

Commands to run the example:

```bash
# In a project with Gradle wrapper:
./gradlew test
./gradlew bootRun

# On a machine with compatible Gradle without a wrapper:
gradle test
gradle bootRun
```

You do not need to compile individual Spring classes with `javac` because the program uses Spring Boot dependencies and auto-configuration; Gradle manages the classpath. Tests have no fixed stdout; pass/fail results are reported by the JUnit/Gradle runner.

## 8. Adding Business Logic Around Login/Logout Properly

### 8.1. What should be done inside a success handler?

Do:

- Choose a valid internal redirect or an appropriate JSON body.
- Read `Authentication.getName()` or needed authorities to **display** minimal information for the UI.
- Wire a safe monitoring/audit mechanism if required, ensuring metric recording does not accidentally break the authentication response.
- Maintain proper content type, status, and error structure.
- If using a request cache, decide clearly how saved requests and navigation are handled.

Avoid:

- Storing plaintext passwords or tokens back into the response body/logs.
- Calling `SecurityContextHolder.setContext(...)` ad hoc to "finish logging in"; that is the authentication mechanism's job.
- Granting elevated privileges merely because `successHandler` ran; permissions must come from trusted authentication/authorization sources.
- Writing a response and then sending a second redirect/JSON payload.
- Redirecting to a client-supplied URL without validation.
- Running non-essential DB/remote calls in a way that stalls every login if an external system briefly fails.

### 8.2. What should be done inside a failure handler?

Wrong passwords, non-existent accounts, locked accounts, or expired accounts can raise subclasses of `AuthenticationException`. You can classify them **on the server** for auditing/support, but public responses should avoid helping attackers guess whether an account exists.

For example, the demo handler always returns a generic `INVALID_CREDENTIALS` code. If the UI needs to distinguish cases like "temporarily locked after too many attempts", coordinate with brute-force protection policies, generic messaging, and channel controls; never return raw exception details.

Distinguish:

- **Login failure**: reached the authentication filter and credentials failed; `AuthenticationFailureHandler`.
- **Missing CSRF**: request blocked before authentication; not a "wrong password" mechanism.
- **Unauthenticated user hitting /private**: `AuthenticationEntryPoint`.
- **Authenticated user missing permissions**: `AccessDeniedHandler`.
- **Code/DB error during login**: do not arbitrarily turn every exception into 401; investigate server errors and return the proper status.
- **HTTP Basic/Bearer**: authentication and challenge headers differ from form login; do not assume `formLogin`'s failure handler runs for every scheme.

### 8.3. How do LogoutHandler and LogoutSuccessHandler differ?

A `LogoutHandler` is called **to perform cleanup actions**: session, context, remember-me cookie, related session data, or defined side effects. Spring Security recommends that `LogoutHandler` implementations normally **do not throw exceptions** so cleanup can proceed reliably.

A `LogoutSuccessHandler` decides **the final response** after cleanup. Example:

```java
.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .logoutSuccessHandler((request, response, authentication) ->
        response.setStatus(HttpServletResponse.SC_NO_CONTENT)
    )
)
```

The code above only changes how the response is returned; Spring Security's default cleanup handlers still run. If additional cookies must be deleted, you can configure:

```java
.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .deleteCookies("JSESSIONID", "remember-me")
    .logoutSuccessHandler((request, response, authentication) ->
        response.setStatus(HttpServletResponse.SC_NO_CONTENT)
    )
)
```

This is **an alternative version** of the `logout` section; do not attach both at the same time in the chain. Cookie deletion via `Set-Cookie` must match name, Path, Domain, and deployment characteristics; Spring Security's docs note that deleting the session cookie via the configurer is not guaranteed to behave identically across every servlet container. Once 204 returns, the client can update local UI state; verify with tests that the browser actually drops the cookie.

**Do not make `LogoutSuccessHandler` the sole place revoking sessions**: if cleanup is skipped, the app might report `LOGOUT_OK` while the next request still carries a valid security context. Keep processing routed through `LogoutFilter` and `LogoutHandler` rather than creating a custom endpoint that calls an arbitrary service and returns 200.

## 9. Cookies, Sessions, and Safe Logout

### 9.1. Session-based form login

Successful login is normally paired with a session cookie (such as `JSESSIONID`), storing authentication state per the app's architecture. The system includes **session fixation** protection and `SecurityContext` persistence; customizing the success handler **must not break** them.

Items to verify:

- `Secure`/`HttpOnly`/`SameSite`/`Path`/`Domain` cookie attributes match HTTPS and cross-origin policies.
- Logout invalidates session/context so the client can no longer use old session data.
- CSRF tokens are rotated after login/logout.
- Browsers and CDNs do not cache responses containing sensitive data.
- If running behind a proxy, configure forwarded headers/trusted proxies properly; never infer scheme/host blindly from client-supplied headers.
- If the system uses "remember me", verify the remember-me cookie/token is cleared as well.

### 9.2. Stateless JWT/Bearer

An API using self-contained access tokens (JWT) and `SessionCreationPolicy.STATELESS` behaves very differently. When a client "logs out" by deleting a local JWT:

- The client stops sending the token, yet issued tokens **may remain valid** until expiration unless the resource server has a rejection/revocation mechanism.
- Session `LogoutFilter` does not automatically revoke every access token, refresh token, or authorization server session.
- If early revocation is required, design token revocation/denylist/short lifetimes, refresh-token management, and provider coordination per protocol.
- With OAuth2/OIDC/SAML, single logout from the identity provider is a separate flow; logging out only the application session does not end system-wide SSO.

Do not use the session-cookie example above as automatic instructions for a JWT API; clarify stateful vs. stateless before choosing handlers.

### 9.3. CSRF and logout

When browsers automatically send authentication cookies, CSRF still needs handling even when the API returns JSON. **Never disable CSRF entirely just to make login/logout POSTs easier.**

Spring Security offers options for server-rendered clients, SPAs, and non-cookie clients. Configuration should match the threat model: not every API needs the exact same policy. For the cookie-session demo, the solution is an endpoint to fetch the CSRF token and sending it in the standard header.

Logging out via `GET /logout` as a state-changing action without CSRF is dangerous; it can lead to logout CSRF. By default with CSRF enabled, `GET /logout` usually serves only confirmation while POST performs logout. If you change `logoutRequestMatcher`, understand the security impact before allowing GET to perform logout.

## 10. UI Design to Avoid Common Pitfalls

### 10.1. For SPA/session clients

A simple state machine:

```text
APP_START
  -> GET /api/auth/csrf       (keep cookie + token)
  -> UNKNOWN / ANONYMOUS

LOGIN_SUBMIT
  -> POST /api/auth/login     (form-urlencoded + CSRF)
       200 -> AUTHENTICATED, refresh CSRF, load profile
       401 -> ANONYMOUS, generic credential error
       403 -> CSRF_ERROR, refetch CSRF, retry only when safe
       5xx -> SERVER_ERROR, do not treat as wrong password

REQUEST_PRIVATE
  -> 200 -> render data
  -> 401 -> require login/refresh auth state
  -> 403 -> insufficient permission, do not log out blindly

LOGOUT_SUBMIT
  -> POST /api/auth/logout    (new CSRF + cookie)
       204 -> clear local auth UI/cache, refetch CSRF if needed
       403 -> check CSRF/session, do not falsely declare logout
       5xx -> logout state unknown; re-verify session
```

With a 204 response, the frontend **must not parse JSON**; calling `response.json()` on an empty body can throw a parse error and cause the UI to report logout failure even though the server cleared the session. Branch by status code.

A UI should avoid "immediately logging out on any 401" when multiple concurrent requests are in flight during CSRF/token refresh. Track auth state per endpoint contracts and distinguish a login-attempt 401 from a protected-resource 401.

### 10.2. For HTML forms

- Use `defaultSuccessUrl`/`failureUrl`/`logoutSuccessUrl` when navigation is all that is needed.
- Include the CSRF token in POST forms via your framework/template engine support.
- Show friendly error messages; never copy raw internal exception messages into URLs.
- Ensure destination pages enforce actual authorization checks.
- After logout, prevent browsers from revisiting sensitive pages via cached responses; configure cache headers and server-side auth checks.

### 10.3. Why should redirects and JSON not be mixed haphazardly?

A login endpoint that sometimes returns 302 HTML and sometimes 200 JSON depending on `Accept` or other headers requires an explicit contract and dedicated tests. If the client is an SPA using `fetch`, automatic browser redirect following can cause the client to receive an HTML login page and fail trying to parse it as JSON. If an app needs both web UI and APIs, define separate routes/security chains or explicit request matchers, or configure clear response handlers per client type. Never rely on header guessing for authorization.

## 11. Customizing Form Login and JSON Login Are Not the Same

Default form login reads form parameters; swapping success/failure handlers **only changes post-authentication behavior**. It does not turn the input mechanism into JSON.

If an SPA sends:

```http
POST /api/auth/login HTTP/1.1
Content-Type: application/json

{"username":"learner","password":"demo-password"}
```

then `formLogin.loginProcessingUrl(...)` in the demo **does not provide a JSON username/password converter out of the box**. A proper JSON login design may need an `AuthenticationFilter`/`AuthenticationConverter` or a dedicated authentication mechanism, along with session management, CSRF, failure responses, brute-force protection, and tests. Do not write a controller that accepts a password and calls `SecurityContextHolder.setAuthentication(...)` while bypassing persistence/session strategies.

Likewise, customizing `formLogin.successHandler(...)` does not automatically apply to:

- HTTP Basic authentication filters;
- bearer token/JWT resource-server filters;
- OAuth2/OIDC redirect login filters;
- SAML2 login;
- other custom authentication schemes.

Each mechanism has its own handlers or adapter configurations, such as `oauth2Login(oauth2 -> oauth2.successHandler(...))`; claims, redirects, and logout with external providers require their own flows.

## 12. Implementation Pitfalls to Avoid

1. **Overusing one handler for all HTTP 401/403 responses:** failed login, unauthenticated access, missing permissions, and invalid CSRF have different origins. Attach handlers to the right filters/extension points.
2. **Disabling CSRF because fetching tokens feels inconvenient:** dangerous for apps using cookies/sessions in browsers. Use a CSRF endpoint or proper form integration.
3. **Breaking security session handling when switching to JSON responses:** a success handler does not replace `SessionAuthenticationStrategy`, persistence, and session fixation protection.
4. **Returning `204` and still writing JSON:** violates `No Content` semantics; clients may fail to parse or misread the response.
5. **Forgetting `return` or writing twice:** a handler decides the final response; never both `sendRedirect(...)` and write JSON in the same branch.
6. **Leaking overly detailed authentication reasons:** exposing "user does not exist" vs. "wrong password" enables account enumeration.
7. **Relying on the logout success body to claim JWT/SSO revocation:** session logout does not inherently revoke tokens or identity-provider sessions.
8. **Creating a custom POST `/logout` controller instead of `LogoutFilter`:** easy to miss default cleanup, remember-me, CSRF, and security context clearing.
9. **Assuming handlers always receive a non-null `Authentication`:** failure handlers have no authenticated principal; logout success handlers may receive `null`.
10. **Custom redirecting to an unverified query URL:** can introduce open redirects sending users to untrusted sites.
11. **Expecting `failureHandler` to catch invalid CSRF:** `CsrfFilter` can block the request before authentication.
12. **Configuring multiple `SecurityFilterChain` beans that miss login/logout routes:** `securityMatcher` selects the chain; if a URL is not handled by the right chain, you can get 404, 403, or confusing behavior.
13. **Registering conflicting success/failure handlers across multiple configurers without knowing which takes effect:** specify one contract and test every route.
14. **Returning exception messages verbatim to clients:** can leak credentials, account types, or system internals.
15. **Testing only with mocks without checking real cookies:** session ID rotation, Path/SameSite/Secure, proxies, and logout cookies must be tested via browser/live HTTP.

## 13. QA Checklist for Every Response Change

| Check item | Question to confirm |
| --- | --- |
| Matching | Do `POST login` and `POST logout` match the intended `SecurityFilterChain` and filter? |
| Form body | Are `username`/`password` params named properly with the right content type? If using JSON, is there a proper converter? |
| Login success | Are status/body/redirect right; are cookie/session and context persisted; is request cache contract clear? |
| Login failure | Are 401/redirect right; is account info protected from leaks; do rate limiting/monitoring still work? |
| Anonymous resource | Does `AuthenticationEntryPoint` return 401 or redirect appropriately for the client? |
| Authorization fail | Does `AccessDeniedHandler` return 403 without being confused with 401? |
| CSRF | Are missing tokens blocked; are tokens refreshed after login/logout; do browsers send cookies and headers properly? |
| Logout | Do default `LogoutHandler` instances still run; are cookies/context/session genuinely unusable afterward? |
| Response body | Is JSON content type set; does 204 have no body; is there no double write? |
| HTTP headers | Are cookies secure, caching appropriate, and Basic/Bearer challenges preserved if using those schemes? |
| Integration | Tested with both MockMvc and live HTTP/browser through real proxy config? |
| Audit | Do logs exclude passwords, bearer tokens, raw cookies, and internal error details? |

### Self-Check Questions

1. Why does `AuthenticationFailureHandler` not handle a POST login request missing a CSRF token?
2. What is the difference between `AuthenticationFailureHandler` and `AuthenticationEntryPoint`?
3. Why can replacing `AuthenticationSuccessHandler` with a JSON response lose the redirect back to the saved request?
4. Can `LogoutHandler` and `LogoutSuccessHandler` replace each other?
5. Why should a client not call `response.json()` when logout returns `204`?
6. When using session cookies, why is a new CSRF token needed after login and logout?
7. Why does deleting a JWT cookie on the client not guarantee the JWT is invalidated on the server?
8. If an app uses default `formLogin`, why does a JSON login body not work out of the box?
9. When redirecting based on permissions, why must destination routes and services still be protected?
10. Why must replacing the default HTTP Basic/Bearer entry point preserve the proper challenge headers?

**Hints:** (1) `CsrfFilter` can block before authentication; (2) failed login attempt vs. unauthenticated request needing to initiate auth; (3) the new handler does not automatically use `RequestCache`; (4) one performs cleanup, the other decides the post-cleanup response; (5) empty body; (6) the old token is cleared by authentication/logout strategies; (7) the token stays valid until expiration/revocation; (8) the filter reads form params; (9) response routing does not grant permissions; (10) protocol requirement for clients to authenticate properly.

## Official Reference Documentation

- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — `AbstractAuthenticationProcessingFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html
- Spring Security — Logout: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — Authentication Events: https://docs.spring.io/spring-security/reference/servlet/authentication/events.html
- Spring Security — MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
