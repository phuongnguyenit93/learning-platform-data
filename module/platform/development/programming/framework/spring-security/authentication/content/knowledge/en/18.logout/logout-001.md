# LogoutFilter, LogoutHandler, and LogoutSuccessHandler

> **Topic:** Spring Security - authentication — **Logout** (Servlet). This lesson explains the path of a logout request in Spring Security, the difference between the request-detection component, cleanup tasks, and the success response; then implements a **Java 17 + Spring Boot 3.3.5 + Spring Security 6.x** application with a logout endpoint returning JSON and tests CSRF/session protection. This is logout for an application using **HTTP session and form login**. JWT revocation, OAuth2/OIDC, and single logout are related but are additional concerns that must be clearly distinguished.

## 1. Three Roles That Must Not Be Confused

A typical `POST /logout` request is not a simple controller command that just "returns OK". It must terminate the authentication state on the server, handle related resources, and only then return a result to the client. Spring Security separates three responsibilities:

| Component | Responsibility | Key takeaway |
| --- | --- | --- |
| `LogoutFilter` | Detects requests matching the logout URL/matcher, orchestrates the cleanup chain, then invokes the success handler | Is a **filter** in `SecurityFilterChain`, running before `AuthorizationFilter` |
| `LogoutHandler` | Performs **one** cleanup task: clear context, invalidate session, delete cookies/tokens, publish an event, or custom cleanup | There can be multiple handlers; should complete normally, **must not throw exceptions** |
| `LogoutSuccessHandler` | Decides the **response after cleanup**: redirect, HTTP status, JSON, or protocol-specific response | Called **after the LogoutHandlers**; should not replace the cleanup step |

For example, if the frontend wants logout to return JSON instead of redirecting, the right solution is usually to **keep `LogoutFilter` and the `LogoutHandler`s**, and only replace `LogoutSuccessHandler`. If you need to add custom behavior such as auditing or deleting a specific cookie, add a `LogoutHandler` instead of rewriting the entire flow.

### Comparison with authentication

- **Login**: `UsernamePasswordAuthenticationFilter` extracts credentials, `AuthenticationManager`/provider verifies them, creates a trusted `Authentication`, and saves `SecurityContext` when needed.
- **Logout**: `LogoutFilter` sees a valid logout request, invokes handlers to **clean up** state/credentials, and then the success handler generates the response. Logout does not call the provider again to "verify the password".
- **Authorization**: `AuthorizationFilter` evaluates URLs requiring auth. Because `LogoutFilter` runs before it, a logout endpoint configured via the default DSL does not need to be explicitly opened with `permitAll` for the filter to handle it.

**A successful logout does not mean all credentials on all devices have been revoked.** Logging out of the current session differs from "logout all sessions", revoking an OAuth refresh token, invalidating an unexpired JWT, or logging out of an IdP.

## 2. Default Logout Request Processing Flow

With Spring Security Servlet 6.x with form login and CSRF enabled:

```text
Logged-in browser:
  Cookie: JSESSIONID=...
  POST /logout + valid CSRF token
        |
        v
SecurityFilterChain
  |
  +-> CsrfFilter
  |      |-- invalid token -> 403
  |      |-- valid token -> continue
  |
  +-> LogoutFilter
         |-- Does URL/method match the logout request matcher?
         |     no  -> continue to remaining filters
         |     yes -> process logout:
         |
         +-> LogoutHandler #1, #2, ... (cleanup)
         |     * SecurityContextLogoutHandler
         |         - invalidate HttpSession if configured
         |         - clear SecurityContextHolder
         |         - clear/save empty SecurityContext per repository
         |     * CsrfLogoutHandler: clear CSRF token
         |     * remember-me logout handler if enabled
         |     * LogoutSuccessEventPublishingLogoutHandler
         |     * custom LogoutHandlers added by the application
         |
         +-> LogoutSuccessHandler
               - default redirect /login?logout
               - or return HTTP 200/204, JSON, etc.
        |
        +-> Response (does not proceed down to a logout MVC Controller)
```

The exact order of cleanup handlers also depends on configuration; the diagram shows **representative tasks**, not a guarantee of the exact position in an immutable internal list. Handlers may be added by configurers, such as remember-me. **Do not rely on an assumed order to turn a faulty handler into a mandatory security mechanism.**

### 2.1. What Does Spring Security Provide by Default?

When Spring Security Servlet is configured normally:

- `GET /logout`: if CSRF is enabled and the default page is provided, Spring Security renders a **logout confirmation page** containing a POST form and a CSRF token. Visiting this GET endpoint **does not log out automatically**.
- `POST /logout`: a request with a valid CSRF token is processed by `LogoutFilter`.
- `SecurityContextLogoutHandler`: by default invalidates the associated HTTP session, clears `SecurityContextHolder` and the repository.
- `CsrfLogoutHandler`: clears the server-side CSRF token.
- Remember-me integration, if enabled, cleans up the remember-me cookie/related data according to the active mechanism.
- `LogoutSuccessEventPublishingLogoutHandler`: publishes `LogoutSuccessEvent` for listeners.
- Default `LogoutSuccessHandler`: redirects to `/login?logout`.

**When CSRF is disabled** in a given configuration, the logout matcher semantics may change; in the default configuration, logging out via GET may be accepted. Therefore **do not arbitrarily disable CSRF** for applications using automatically sent cookies. For an SPA using session cookies, the frontend must fetch and send the CSRF token properly when POSTing to logout.

### 2.2. Why Does LogoutFilter Run Before AuthorizationFilter?

This matters when a user already has an expired session or an invalid cookie: `LogoutFilter` handles logout according to its matcher before reaching the HTTP authorization rules.

For example:

```java
// Illustrates URL configuration; not a standalone Java class.
http.logout(logout -> logout.logoutUrl("/logout"));
```

There is no need to add `requestMatchers("/logout").permitAll()` **solely because** the route is handled by `LogoutFilter`. Conversely, if you write `@PostMapping("/logout-custom")` yourself in Spring MVC, that endpoint sits after the security filters and requires appropriate authorization — though the general recommendation is still to use the logout DSL so cleanup is not missed.

### 2.3. Input Authentication Can Be Null

`LogoutFilter` typically retrieves the current `Authentication` from the context and passes it to the handlers. An unauthenticated client can still send a valid logout request; in that case `authentication` may be `null`. A custom `LogoutHandler` or `LogoutSuccessHandler` **must not assume a principal is always present**.

Therefore, do not use:

```java
// Wrong in a custom LogoutHandler: may throw NullPointerException.
String username = authentication.getName();
```

Instead, check:

```java
// Illustration inside a handler that has received authentication.
String username = authentication == null ? null : authentication.getName();
```

Do not expose the username, session ID, or raw token in the logout response. The client does not need to know how many sessions the server is holding to perform the current logout.

## 3. LogoutHandler: Where Actual Cleanup Happens

The `org.springframework.security.web.authentication.logout.LogoutHandler` interface has the method:

```java
void logout(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication authentication);
```

The signature above is an **API illustration** and needs imports if placed in a Java file. The handler can access the request/response and the `Authentication` of the current session. Each handler addresses one clear responsibility; when there are multiple handlers, Spring Security can compose them using `CompositeLogoutHandler`.

### 3.1. Built-in Handlers

| Name | What it does | What should not be assumed |
| --- | --- | --- |
| `SecurityContextLogoutHandler` | Clears authentication/context, invalidates `HttpSession` when enabled, saves an empty context appropriately | Does not automatically revoke JWT/refresh tokens in other stores |
| `CsrfLogoutHandler` | Removes the stored CSRF token so a new session does not reuse the old token | Does not replace the CSRF filter or handle authorization |
| `CookieClearingLogoutHandler` | Sends `Set-Cookie` to expire the specified cookies | Does not destroy server-side state merely by deleting cookies |
| `LogoutSuccessEventPublishingLogoutHandler` | Publishes `LogoutSuccessEvent` | Is not by default a durable audit system |
| `TokenBasedRememberMeServices` / `PersistentTokenBasedRememberMeServices` | Cleans up remember-me according to the implementation | With token-based, a copied cookie may still be replayed until expiration/key change/password change |
| `HeaderWriterLogoutHandler` + `ClearSiteDataHeaderWriter` | Sends `Clear-Site-Data` so the browser clears cookies/storage/cache per directive | Browser support policies and origin scope must be understood |

### 3.2. `SecurityContextLogoutHandler` Is Most Important for Sessions

`SecurityContextLogoutHandler` handles the core of session-based logout:

1. **Invalidate `HttpSession`** if configuration permits, making the active session ID no longer reference that login state.
2. **Clear `SecurityContextHolder`** so the current request/thread no longer has authentication.
3. **Clear `SecurityContextRepository`** according to the active context storage mechanism, preventing an old context from being reloaded on the next request.

If you only call `SecurityContextHolder.clearContext()` in a controller while skipping the session/repository, the next request can still read the saved context and treat the user as still logged in.

If you only send an empty cookie while leaving the server session alive, anyone holding a copy of the previous session ID can still use it, depending on configuration. **Server-side invalidation is the critical step for session cookies.**

### 3.3. Deleting Cookies and Deleting Sessions Are Two Different Things

The following configuration adds an instruction for the browser to delete the cookie named `JSESSIONID`:

```java
// Illustrative DSL snippet, not a standalone application.
http.logout(logout -> logout.deleteCookies("JSESSIONID"));
```

This *does not replace* `invalidateHttpSession(true)`. Furthermore, cookie deletion must match the appropriate `Path`/`Domain` for the browser to actually remove it; when deployed behind a reverse proxy, the cookie scope may differ from the default. Spring Security notes that configuring `JSESSIONID` deletion is usually **unnecessary** once the session is invalidated; the example below uses explicit `deleteCookies` as an illustration, not as a core security measure.

If using a custom application cookie (e.g., non-credential `PREFS`) and there is a reason to clear it on logout, use `CookieClearingLogoutHandler` or the `deleteCookies` DSL. Do not accidentally delete essential cookies belonging to other applications sharing the domain.

### 3.4. Custom LogoutHandler: Adding Auditing or Auxiliary Cleanup

Example of registering a handler using the DSL:

```java
// Illustrates a callback function: must receive the required dependencies in an actual class.
http.logout(logout -> logout.addLogoutHandler(
    (request, response, authentication) -> {
        if (authentication != null) {
            auditService.recordLogout(authentication.getName());
        }
    }
));
```

**Important principle:** Spring Security defines `LogoutHandler` as a cleanup task and it **should not throw exceptions** to block the logout chain. If DB auditing fails, you should use a reliable audit solution with proper failure/asynchronous handling; do not let a logging error cause the server to skip session deletion. If there is a legal requirement not to return success until an external system confirms, design a dedicated orchestration — do not accidentally turn `LogoutHandler` into a distributed transaction.

Do not include raw authentication or session IDs in audit logs without security controls. You can record the authenticated internal user ID, timestamp, request ID, and outcome (in accordance with privacy policy).

## 4. LogoutSuccessHandler: Only Decides How to Return the Result

The `org.springframework.security.web.authentication.logout.LogoutSuccessHandler` interface has the method:

```java
void onLogoutSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication authentication) throws IOException, ServletException;
```

This is an **illustrative API signature**. This handler is invoked after the cleanup chain has run. It is suitable for:

- Traditional web browsers: **redirect** to `/login?logout` or a logout confirmation page.
- SPAs/JSON APIs using session cookies: return **200 OK** with JSON, or **204 No Content** so the client handles navigation itself.
- Certain SSO protocols: coordinate the logout sequence to the IdP using a dedicated implementation, but do not assume local logout automatically revokes the IdP session.

Example of changing only the status:

```java
// When only HTTP 200 is needed instead of a redirect.
http.logout(logout -> logout
    .logoutSuccessHandler(new HttpStatusReturningLogoutSuccessHandler())
);
```

JSON example:

```java
// The lambda signature is (request, response, authentication).
http.logout(logout -> logout.logoutSuccessHandler(
    (request, response, authentication) -> {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("application/json");
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write("{\"message\":\"logged out\"}");
    }
));
```

If you only want a redirect URL, use `logoutSuccessUrl("/login?logout")`; **do not combine both strategies and expect both a redirect and JSON simultaneously**.

**The name "success" has a limited meaning:** when the browser receives HTTP 200 after local logout, it does not prove that all devices, previously issued access tokens, OIDC sessions, or third-party caches have been revoked.

## 5. Spring Boot Example: Form Login + LogoutFilter + Custom Handler and JSON Success

This example uses the standard logout configuration rather than writing `@PostMapping("/logout")`.

Goals:

- `alice` / `demo-pass123` is a **demo** account (do not use hardcoded credentials in production).
- `POST /login` with valid CSRF creates an authenticated `HttpSession`.
- `GET /api/me` requires an authenticated user.
- `POST /logout` with valid CSRF:
  - `LogoutFilter` invokes the default cleanup and a custom `LogoutHandler` that records an in-memory audit counter.
  - The session is invalidated and the context is cleared.
  - `LogoutSuccessHandler` returns **200 + JSON**.
- `POST /logout` **without CSRF** is blocked with 403 before cleanup runs.
- Accessing the protected endpoint again **without sending a valid session** prompts for login.

### 5.1. Project Structure

```text
logout-filter-demo/
├── pom.xml
├── src/main/java/com/example/logout/LogoutDemoApplication.java
└── src/test/java/com/example/logout/LogoutDemoApplicationTests.java
```

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>logout-filter-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

### 5.2. Java Application

Create **`src/main/java/com/example/logout/LogoutDemoApplication.java`**:

```java
package com.example.logout;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.concurrent.atomic.AtomicInteger;

@SpringBootApplication
public class LogoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("demo-pass123"))
                        .roles("USER")
                        .build()
        );
    }

    // Uses a counter to test that the custom LogoutHandler is invoked.
    // This is NOT a durable audit store in production.
    @Bean
    LogoutAuditService logoutAuditService() {
        return new LogoutAuditService();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LogoutAuditService auditService) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            // Default form login; redirects directly to an existing endpoint.
            .formLogin(form -> form
                .defaultSuccessUrl("/api/me", true)
            )
            .logout(logout -> logout
                // LogoutFilter, not a Spring MVC controller.
                .logoutUrl("/logout")
                // Additional custom handler; does not replace the default cleanup.
                .addLogoutHandler((request, response, authentication) ->
                    auditService.onLogout(authentication)
                )
                // Both options default to true; written explicitly for illustration.
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                // May be redundant once the session is already invalidated.
                .deleteCookies("JSESSIONID")
                // Replaces only the post-cleanup response; does not remove default handlers.
                .logoutSuccessHandler((request, response, authentication) -> {
                    response.setStatus(HttpServletResponse.SC_OK);
                    response.setContentType("application/json");
                    response.setCharacterEncoding("UTF-8");
                    response.getWriter().write(
                            "{\"message\":\"logged out\"}"
                    );
                })
            );

        // Do not disable CSRF: form login/logout require a valid token.
        return http.build();
    }

    static final class LogoutAuditService {
        private final AtomicInteger completedForKnownUsers = new AtomicInteger();

        void onLogout(Authentication authentication) {
            // Unauthenticated logout may pass null; avoid NullPointerException.
            if (authentication != null) {
                completedForKnownUsers.incrementAndGet();
            }
        }

        int completedCount() {
            return completedForKnownUsers.get();
        }
    }

    public record WhoAmI(String username, boolean authenticated) {}

    @RestController
    static class DemoController {

        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/api/me")
        WhoAmI me(Authentication authentication) {
            return new WhoAmI(authentication.getName(), authentication.isAuthenticated());
        }
    }
}
```

### 5.3. Explaining the Choices in the Example

1. **Do not create your own LogoutFilter.** Spring Security's `http.logout(...)` builds the filter, matcher, cleanup handlers, and success handler. Writing a custom servlet filter and inserting it in the wrong position can bypass CSRF or leave context cleanup incomplete.
2. **Default CSRF remains enabled.** Because session cookies are sent automatically by the browser, a malicious website must not be allowed to log out a user via a forged request. Form/login/logout all have appropriate CSRF mechanisms.
3. **Add a handler, do not replace default handlers.** `addLogoutHandler` only adds the audit counter. `SecurityContextLogoutHandler` remains responsible for invalidating the session and clearing the context, without needing to be called manually inside this callback.
4. **Avoid exceptions during cleanup.** The demo handler only increments an `AtomicInteger`; in a real application, durable auditing should follow a pattern with failure handling. Do not call external systems with operations that can block indefinitely inside a logout handler.
5. **The JSON response does not determine session validity.** `logoutSuccessHandler` runs after cleanup and returns `200`. It does not delete the session itself, so the code does not use it for core security processing.
6. **No need for `requestMatchers("/logout").permitAll()`** because `LogoutFilter` intercepts logout before AuthorizationFilter. `/api/me` requires authentication; `/public` allows anonymous access.
7. **The `JSESSIONID` cookie is not the sole proof.** The app has invalidated the session, and `deleteCookies` only sends an instruction to delete the browser cookie. An old copy of the session ID will no longer reference the destroyed session in a proper session store.
8. **Successful form login redirects to `/api/me`**, avoiding `/` for which the demo provides no endpoint.
9. **The logout URL does not accept a client-supplied username.** All cleanup must rely on the current authentication loaded from the request's `SecurityContext`/session, not on `?user=alice` or a self-declared JSON body.
10. **After logout**, a new request without a valid session to `/api/me` is redirected to the login page because the demo enables `formLogin`. For a REST API with a custom entry point, this could be HTTP 401 instead of a redirect.

## 6. Testing Exact Logout Behavior with MockMvc

Create **`src/test/java/com/example/logout/LogoutDemoApplicationTests.java`**:

```java
package com.example.logout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    LogoutDemoApplication.LogoutAuditService auditService;

    private MockHttpSession logIn() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void logoutRunsCleanupAndReturnsJsonInsteadOfRedirect() throws Exception {
        MockHttpSession session = logIn();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true));

        int previousAuditCount = auditService.completedCount();

        mvc.perform(post("/logout").session(session).with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"logged out\"}"));

        // MockHttpSession is invalidated: cannot use this session for a new request.
        assertTrue(session.isInvalid());
        assertTrue(auditService.completedCount() > previousAuditCount);

        // A request without an authenticated session must be sent to login.
        mvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void postLogoutWithoutCsrfDoesNotDestroySession() throws Exception {
        MockHttpSession session = logIn();

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        // Proper cleanup at the end of the test.
        mvc.perform(post("/logout").session(session).with(csrf()))
                .andExpect(status().isOk());
        assertTrue(session.isInvalid());
    }

    @Test
    void publicResourceRemainsAccessibleToAnonymousClient() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn test
```

**Meaning of the tests:**

- The first test does not just check the JSON response. It performs a real login through `UsernamePasswordAuthenticationFilter`, uses that session to access a protected endpoint, logs out via `LogoutFilter`, verifies `MockHttpSession.isInvalid()`, and confirms the audit callback was called. A new request sent without a session is no longer considered logged in.
- The second test attempts **POST logout without CSRF**, receives 403, and verifies the session has not been cleared. Then it sends a valid CSRF token to actually log out.
- The third test shows that the public endpoint does not depend on a session.

**Testing limitations:** `MockMvc` uses simulated servlet requests/sessions. It proves the filter chain path and `MockHttpSession` invalidation, and **does not replace** tests against a real HTTP container, cookie Path/Domain, reverse proxy, and Redis/distributed session store. The Maven tests in this lesson are code for the learner to run; they should not be treated as already executed merely because they appear in the documentation.

### How to Read the HTTP Response After Logout

Per the demo configuration, the expected valid logout result is **200 OK**:

```http
HTTP/1.1 200 OK
Content-Type: application/json;charset=UTF-8

{"message":"logged out"}
```

This illustrates the typical part of the response. A `Set-Cookie` header to delete `JSESSIONID` may appear; `Path`/`Expires`/`Max-Age` values depend on the session container and configuration. Do not hard-code the entire response byte-by-byte. A POST missing CSRF will return **403 Forbidden** in the demo configuration; a protected GET without a session will redirect to the login page.

## 7. Trying It Out with a Browser or curl

### 7.1. Safest Way to Test with a Browser

1. Run `mvn spring-boot:run`.
2. Open `http://localhost:8080/login` and log in with `alice` / `demo-pass123`. The default form page includes a CSRF token.
3. After logging in, the browser goes to `/api/me` and receives JSON for user `alice`.
4. Open `http://localhost:8080/logout` via GET: in the default CSRF configuration, Spring Security may show a logout confirmation page, **without destroying the session yet**.
5. Submit the logout confirmation form via POST with the CSRF token. Because of the custom `LogoutSuccessHandler`, the response is `{"message":"logged out"}` instead of the default redirect.
6. Visit `/api/me` again: the user is prompted to log in again.
7. If testing `POST /logout` via JavaScript, remember to send the CSRF token from the source provided by the actual application. Adding a GET URL that destroys the session is discouraged to prevent CSRF/logout-by-link.

### 7.2. Why `curl -X POST /logout` Is Not Enough

`curl` does not automatically fetch a CSRF token, enter a username/password, or maintain a cookie jar unless instructed. The standalone command:

```bash
curl -i -X POST http://localhost:8080/logout
```

is typically blocked by the CSRF filter with **403**, which does not prove that logout is broken. To test manually with curl, you need to:

- Use `-c cookies.txt` / `-b cookies.txt` to maintain the session cookie (do not commit the cookie jar to the repository).
- Obtain the `_csrf` token from the login/logout page or an endpoint provided by the application that issues CSRF tokens.
- POST `/login` and `/logout` along with the session cookie and valid token, keeping the right `Content-Type`, form parameters, and URL.
- Do not copy raw `JSESSIONID`, CSRF tokens, or remember-me cookies into public chats/logs.

The automated `MockMvc` test example in section 6 generates valid CSRF tokens and manages the session for each request, making it more convenient than curl in this lesson.

## 8. Advanced Scenarios: Custom Logout Endpoints and Integrating Multiple Mechanisms

### 8.1. Why Writing Your Own `@PostMapping("/logout")` Is Discouraged

The following snippet is **wrong/incomplete**:

```java
// Wrong: clearing a local reference does not guarantee the session store has been cleaned.
@PostMapping("/custom-logout")
String logout() {
    SecurityContextHolder.clearContext();
    return "ok";
}
```

If `SecurityContext` is still stored in `HttpSession` or a repository, a subsequent request can still restore the authentication. With session login, you should use the logout DSL.

When a dedicated MVC endpoint is genuinely required (e.g., a special protocol/contract), you must invoke the equivalent Spring Security handlers; the illustration below shows **part of the core work**, not a complete controller:

```java
// Only illustrates inside a handler/controller that already has dependencies.
SecurityContextLogoutHandler contextHandler = new SecurityContextLogoutHandler();
contextHandler.setInvalidateHttpSession(true);
contextHandler.logout(request, response, authentication);
```

You must handle CSRF, remember-me, custom cookies, events, responses, security context repositories, and access permissions according to the actual configuration. **Do not create a parallel mapping on `/logout` alongside LogoutFilter**: the filter usually intercepts the request before MVC so the controller will not be invoked; this analysis helps avoid misdirected debugging.

### 8.2. Distinguishing `logoutUrl`, `logoutSuccessUrl`, and `logoutSuccessHandler`

| DSL Option | Effect | Example |
| --- | --- | --- |
| `logoutUrl("/signout")` | Changes the URL recognized by **LogoutFilter** | POST /signout |
| `logoutSuccessUrl("/signed-out")` | After cleanup, **redirects** to the target URL | 302 Location: /signed-out |
| `logoutSuccessHandler(...)` | Customizes the callback that generates the response | 200 JSON or 204 |
| `addLogoutHandler(...)` | Adds extra **cleanup** before the response | Write audit, delete app cookie |
| `deleteCookies("PREFS")` | Adds a cookie-clearing logout handler | Set-Cookie expiring the cookie |
| `invalidateHttpSession(true)` | Specifies invalidating the session | Server-side effect |
| `clearAuthentication(true)` | Clears the held authentication | Does not automatically revoke external tokens |

**Note:** if redirecting to a custom MVC endpoint after logout, the target endpoint needs `permitAll` or `logout(...).permitAll()` per the configuration so anonymous users can access it; otherwise they may be redirected back to login. If returning JSON directly from `LogoutSuccessHandler`, no success controller endpoint is needed.

### 8.3. Logging Out One Session Is Not Logging Out All Devices

Suppose alice has session A on a laptop and session B on a phone. `POST /logout` from A typically invalidates only **session A**. Session B can remain valid unless the application has a policy to revoke all sessions and can enforce it in the corresponding session store.

`SessionRegistry` can help mark other sessions as expired, but `SessionInformation.expireNow()` **does not immediately destroy `HttpSession` across all nodes**. For still-alive sessions, `ConcurrentSessionFilter` processes the expired flag on the next request. If immediate "logout all devices" is required, an architecturally sound real and distributed session/token revocation solution is needed; do not merely delete registry metadata.

### 8.4. Logout with a Remember-Me Cookie

If the application enables remember-me, a long-lived cookie can automatically recreate authentication after the old session is gone. Standard logout configuration integrates `RememberMeServices` to delete the cookie and, for persistent-token, clean up the record according to the implementation. If you write a custom logout and only delete `JSESSIONID`, the remaining remember-me cookie can automatically log the user back in.

**Be cautious with token-based remember-me:** deleting the cookie in the browser **does not revoke** a stolen copy of the cookie; because there is no store to revoke per cookie, the token may remain usable until expiration or a key/password hash change. Persistent tokens allow more effective revocation policies when backed by a properly managed repository.

### 8.5. Logout with JWT/Bearer Access Tokens

With a stateless Resource Server, each request sends an independent Bearer token. Deleting `HttpSession` does not naturally strip the signature from an issued JWT or expire its `exp`. "Logout" may include:
- The browser removing the access token from memory/secure storage.
- The Authorization Server revoking the **refresh token** per the supported protocol.
- Keeping access tokens short-lived; if immediate revocation is required, using a revocation list/denylist, introspection, or another policy synchronization mechanism.
- The client ceasing to send the token and the application handling expired tokens properly.

Do not claim that `SecurityContextLogoutHandler` can invalidate every JWT in the system.

### 8.6. OAuth2/OIDC Single Logout, SAML, and IdP

Logging out of the local application **does not necessarily** log out of the identity provider. If the user signed in via SSO, they can immediately log back in through the IdP while its session remains active. For OIDC, `OidcClientInitiatedLogoutSuccessHandler` exists to coordinate **RP-initiated logout** on supporting providers; for SAML/CAS, dedicated single-logout mechanisms exist.

That is a **multi-system workflow** with its own redirects and conditions; do not replace it with a callback that always returns JSON. This lesson explains local Spring Security Servlet logout first, then outlines the boundaries so the two concepts are not conflated.

## 9. Common Errors and How to Find the Root Cause

### 9.1. POST /logout Returns 403

Most likely **a missing or invalid CSRF token**, especially when an SPA frontend simply calls `fetch("/logout", {method: "POST"})` without sending the header/token. Check in order:
1. Is CSRF still enabled? With forms/session cookies, this is usually the right configuration.
2. Has the client fetched the token from the server and sent back the token bound to the same session?
3. Is the browser sending the appropriate session cookie? Are Path, Domain, SameSite, and fetch credentials mode configured correctly?
4. Was the token rotated/cleared by a previous login/logout?

Do not rush to add `csrf.disable()` to the application to "fix" 403. The test intentionally omits CSRF and expects 403.

### 9.2. Logout Returns 200 but Refreshing Still Shows Logged In

Check:
- Are you using `LogoutFilter` or a custom controller that only returns 200?
- Did `SecurityContextLogoutHandler` actually run, invalidate the session, and clear the context/repository?
- Does the browser still have a valid **remember-me cookie** that logs the user right back in?
- Is a proxy/cache returning stale authenticated data? Are there multiple instances with an unsynchronized session store?
- Are other access tokens/refresh tokens still being sent by the browser?
- Is the client keeping a JWT in localStorage and still attaching an Authorization header after logout?

**Do not treat HTTP status 200 as sole proof that credentials have been revoked.** Tests should issue a new request and evaluate based on the credentials actually remaining in the request.

### 9.3. GET /logout Does Nothing

When CSRF is enabled, GET typically opens a confirmation page and **does not destroy the session**. That protects against logout via links/images on other sites. POST with CSRF is the actual action. If the system disables CSRF, the matcher may differ, but you should not design state-changing logout via GET in a cookie-based app.

### 9.4. Redirect Loop After Logout

If `logoutSuccessUrl("/signed-out")` points to an endpoint requiring `authenticated()`, the context has been cleared so the user is redirected to login; if login then redirects to the wrong page, it can form a loop. Grant public access to the post-logout page or return JSON/204 directly.

### 9.5. Logout Handler Throws an Exception and the Session Is Not Cleaned Up

`LogoutHandler` is meant for cleanup and **should not throw**. For example, calling a remote audit service without a timeout can interrupt the chain. Separate non-critical tasks or apply appropriate error handling. For security-critical callbacks, verify ordering/durable state per policy; do not assume an empty `try/catch` is sufficient.

### 9.6. Cookie Still Appears in DevTools

The browser may retain cookies under a different scope (path/domain) or display expired cookies before a refresh. In particular, cookie deletion must match Path/Domain. More importantly, use server-side session invalidation to block reuse of an old `JSESSIONID`; deleting only the browser cookie offers no protection if the cookie was copied.

### 9.7. MockMvc Test After Logout Throws Session Invalid Error

Once `MockHttpSession` is invalidated, trying to pass **the same object** via `.session(oldSession)` into the next request may throw a mock error because the session is no longer valid. This is not a logout bug. To verify logout, assert `session.isInvalid()` and issue **a new request without an authenticated session**; in real HTTP integration tests, send the old cookie and verify the container rejects it or creates a new session.

## 10. Implementation and Security Checklist

- [ ] Logout is handled by `http.logout(...)`/`LogoutFilter` rather than a controller arbitrarily clearing a variable.
- [ ] State-changing logout requests use **POST + CSRF** when the browser sends session cookies.
- [ ] `SecurityContextLogoutHandler` properly clears `SecurityContextHolder`, the repository, and invalidates the session.
- [ ] Custom cookies, remember-me, CSRF tokens, or token stores are cleaned up **if the application actually uses them**.
- [ ] Additional `LogoutHandler`s have clear responsibilities, handle `authentication == null`, and do not throw exceptions that interrupt logout.
- [ ] `LogoutSuccessHandler` only controls the response; do not assume HTTP 200 revokes all credential types.
- [ ] If success redirects to an MVC endpoint, that endpoint has appropriate anonymous access permissions.
- [ ] Do not log/echo session IDs, raw cookies, access tokens, or refresh tokens.
- [ ] Include tests for 403 when CSRF is missing, session invalidation, new requests requiring login, and remember-me if used.
- [ ] If multi-device logout is required, use a real distributed session/token revocation mechanism rather than relying on deleting the current cookie.
- [ ] If using OAuth2/OIDC/SAML, design logout with the IdP and refresh/access tokens separately.
- [ ] Verify HTTPS, cookie Secure/HttpOnly/SameSite, cache-control, and reverse-proxy handling in a real deployment environment.

## 11. Knowledge Self-Check

1. Why does `LogoutFilter` typically handle `POST /logout` before `AuthorizationFilter` evaluates the request?
2. How do the three responsibilities of `LogoutFilter`, `LogoutHandler`, and `LogoutSuccessHandler` differ?
3. Which handler invalidates `HttpSession` and clears `SecurityContext`?
4. Why might calling only `SecurityContextHolder.clearContext()` in a controller be insufficient?
5. In an app with CSRF, how do `GET /logout` and `POST /logout` differ?
6. When is `addLogoutHandler(...)` used; does it replace all default cleanup?
7. Is a custom handler allowed to assume `authentication != null`?
8. If you want to return `204` instead of redirecting, which component should you replace?
9. Why does deleting `JSESSIONID` in the browser not mean a stolen session has been destroyed?
10. Why does a successful logout not necessarily revoke a JWT or log out all devices?
11. When an app uses remember-me, what must you watch out for to prevent the user from automatically logging back in immediately after logout?
12. How can you verify logout at the filter chain level without mistaking HTTP 200 for security state?

**Answer hints:** (1) the filter runs before authorization; (2) detection/orchestration, cleanup, response; (3) `SecurityContextLogoutHandler`; (4) repository/session still holds the context; (5) GET shows confirmation, only valid POST logs out; (6) adds cleanup without replacing defaults; (7) no, it can be null; (8) `LogoutSuccessHandler`/`HttpStatusReturningLogoutSuccessHandler`; (9) the server-side session must be invalidated; (10) distributed credentials have different lifecycles; (11) remember to delete/revoke remember-me per the mechanism; (12) log in with a session, POST logout with CSRF, assert session invalid, verify a new request requires authentication.

## 12. Official Documentation

- Spring Security 6.5 — Handling Logouts (architecture, handlers, success handlers, cookies, CSRF, endpoints): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — LogoutFilter API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutFilter.html
- Spring Security — LogoutHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutHandler.html
- Spring Security — LogoutSuccessHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutSuccessHandler.html
- Spring Security — SecurityContextLogoutHandler API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
- Spring Security — Testing Logout with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Remember-Me: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
