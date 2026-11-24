# Custom Logout Endpoints and SecurityContextLogoutHandler

> **Module:** Spring Security - authentication. **Group:** Logout. This lesson focuses on **writing a custom Spring MVC/REST logout endpoint** instead of merely configuring `http.logout(...)`. The goal is to understand precisely why `SecurityContextLogoutHandler` must be called, its relationship with `SecurityContextHolder`/`SecurityContextRepository`/`HttpSession`, CSRF, endpoint authorization, default tasks omitted when writing manually, and how to test. Examples use **Java 17, Spring Boot 3.3.5, Spring Security Servlet 6.x, and Maven**.

## 1. When Do You Need a Custom Logout Endpoint?

Spring Security Servlet already provides logout out of the box via `LogoutFilter`. In a typical web configuration, `POST /logout` (requiring a valid token when CSRF is enabled) runs cleanup and redirects to `/login?logout`. If you only need to change the path or return JSON/a status response, customize the **logout DSL**:

```java
// DSL snippet inside HttpSecurity configuration, not a standalone Java file.
http.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setStatus(204);
    })
);
```

This preserves the `LogoutHandler` chain configured by Spring Security: clearing session/context, CSRF, remember-me, and any additional handlers. **This is usually the preferred option.**

However, sometimes a system has a specialized API contract, requires controller-level orchestration, returns a custom JSON object, or attaches actual business logic to the logout request. In that case the app can define `@PostMapping("/api/auth/logout")`. Because a Spring MVC controller executes **after** the security filters, it **does not automatically inherit** all processing from `LogoutFilter`. The controller itself must call the necessary components—at minimum `SecurityContextLogoutHandler`.

**Key takeaway:** merely calling `return ResponseEntity.ok(...)` or `SecurityContextHolder.clearContext()` does not guarantee the user is logged out. If `SecurityContext` still sits in the session/repository, the next request can restore the old authenticated state.

### 1.1. Three Common Approaches

| Approach | Who intercepts the URL? | Who cleans up session/context? | When to use |
| --- | --- | --- | --- |
| `http.logout(...).logoutUrl("/signout")` | `LogoutFilter` | Spring Security's handler chain | Most cases; simple, low risk |
| `http.logout(...).logoutSuccessHandler(...)` | `LogoutFilter` | Still the default handlers | Only want different JSON/HTTP status/redirect |
| `@PostMapping("/api/auth/logout")` | Spring MVC controller | **You explicitly call** `SecurityContextLogoutHandler` and other cleanups | Genuinely required to use a separate controller |

Do not declare both a `LogoutFilter` matcher and a `@PostMapping` on the **same URL** expecting both to run: the filter intercepts the request first, so the MVC controller may never be called. If both mechanisms are needed, paths must differ or the handling must be redesigned clearly.

## 2. Position of a Custom Endpoint in the Filter Chain

### 2.1. Default Logout

```text
Browser POST /logout (valid CSRF, session cookie)
   |
   v
CsrfFilter
   |
   v
LogoutFilter  <-- matcher accepts /logout
   |  - SecurityContextLogoutHandler
   |  - CsrfLogoutHandler
   |  - remember-me handler if any
   |  - logout success event handler
   |  - custom LogoutHandler if registered
   v
LogoutSuccessHandler -> redirect /login?logout or JSON/status
   |
   +-> Does not proceed into a logout Spring MVC controller
```

### 2.2. Custom Spring MVC Endpoint

```text
Browser POST /api/auth/logout (valid CSRF, session cookie)
   |
   v
CsrfFilter
   |  - invalid token -> 403, does not reach controller
   v
LogoutFilter
   |  - does not match this URL -> skips
   v
AuthorizationFilter
   |  - this MVC route must be explicitly permitAll()
   v
DispatcherServlet -> @PostMapping("/api/auth/logout")
   |
   |  - obtain current Authentication from SecurityContext
   |  - call SecurityContextLogoutHandler.logout(request, response, auth)
   |        * invalidate HttpSession if present
   |        * clear Authentication in context
   |        * clear SecurityContextHolder
   |        * clear/save empty context into SecurityContextRepository
   |  - invoke additional cleanup if the app needs it
   v
Controller returns 200 JSON or 204
```

The difference: `LogoutFilter` does not manage routes created by your own controller. `AuthorizationFilter` still evaluates the route; therefore **you must configure permitAll or an equivalent rule**. Official Spring Security documentation advises explicitly permitting custom MVC logout routes; this allows even users with expired sessions or unauthenticated clients to clean up related client state. Even if the route is `permitAll`, **`CsrfFilter` still protects POST** when CSRF is enabled; `permitAll` does not mean bypassing CSRF.

**Do not confuse `permitAll` with disabling security:** that is an authorization-layer decision. Logout requests relying on automatically sent cookies are still subject to CSRF checks, CORS/cookie scope, and HTTP method validation.

## 3. What Does SecurityContextLogoutHandler Actually Do?

The class `org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler` is a Spring Security Servlet `LogoutHandler`. Key API methods:

```java
// Abbreviated signatures for API study, not a complete class.
public void logout(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication);

public void setInvalidateHttpSession(boolean invalidate);
public void setClearAuthentication(boolean clear);
public void setSecurityContextRepository(SecurityContextRepository repository);
```

Both booleans default to `true`; the full code sample in section 6 sets them explicitly for learner visibility. When invoked, the handler is responsible for:

1. **Invalidating the actual HttpSession:** looks up the existing session via `request.getSession(false)` and invalidates it when enabled. Avoids creating a new session just to delete it.
2. **Clearing the current SecurityContext:** removes the existing authentication and clears `SecurityContextHolder`, preventing the request-handling thread from keeping the old principal.
3. **Clearing SecurityContextRepository:** writes an appropriate empty state so the next request cannot reload the saved authentication. `SecurityContextRepository` is the layer deciding how context survives across requests.

In Spring Security 6 apps, storing/reading the context may use `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository`, or a custom implementation. To guarantee cleanup targets **the exact same store**, wire the handler to the actual repository used by the security chain — especially if you configured a custom repository.

### 3.1. Distinguishing Holder, Repository, and Session

| Concept | What it holds | What is needed on logout |
| --- | --- | --- |
| `SecurityContextHolder` | Context of the current request/thread (typically thread-local) | `clearContext()` on logout |
| `SecurityContext` | `Authentication` and related metadata | Stop holding the logged-out principal |
| `SecurityContextRepository` | How context is restored/persisted across requests | Clean stored data, otherwise the next request can restore login |
| `HttpSession` | Server-side browser state, typically linked via `JSESSIONID` cookie | `invalidate()` so the session ID no longer maps to the old session |
| `JSESSIONID` cookie | ID presented by the browser to point to the session | Delete cookie in browser when appropriate; **does not replace** server-side invalidation |

**Security boundary:** logout does not mean merely clearing a Java thread-local. A second request carrying the same session cookie can still read `SecurityContext` from the session if the repository was not cleaned up.

### 3.2. Why Not Call `getSession()` Before Logout?

`request.getSession()` can **create a new session** when none exists. When handling logout, you generally should not create a pointless session only to invalidate it. `SecurityContextLogoutHandler` handles existing sessions automatically. If you need to inspect, use only:

```java
// Illustrative code inside a controller/filter that already has request.
HttpSession existing = request.getSession(false);
boolean hadSession = existing != null;
```

Do not extract the session ID and return it in JSON; a session ID is a credential to protect. The user does not need to see the raw ID to know logout succeeded.

### 3.3. Which `Authentication` Should Be Passed?

A controller can accept `Authentication authentication` injected by Spring MVC/Spring Security. This value is the context loaded by security filters for the request, **not** an object submitted by the client in JSON. An unauthenticated user or timed-out session can yield `authentication == null`, and `SecurityContextLogoutHandler` **accepts null**.

Do not write a handler taking a `userId` parameter supplied by the request to arbitrarily destroy another user's session. Logging out the current session differs from managing/revoking all sessions of an account; the latter requires separate administrative authorization.

## 4. Why Clearing Only SecurityContextHolder Is Wrong

Look at a **broken** controller:

```java
// Illustrates the bug, not a standalone program.
@PostMapping("/api/auth/logout")
ResponseEntity<String> badLogout() {
    SecurityContextHolder.clearContext();
    return ResponseEntity.ok("logged out");
}
```

On that request, the holder was cleared, yet `HttpSession`/`SecurityContextRepository` may still hold `Authentication`. The next request using the old `JSESSIONID` lets filters reload the old security context. The app returns 200 while the user can still access protected resources.

Another mistake:

```java
// Wrong: only asks the browser to delete the cookie; server-side session may still be valid.
response.addHeader("Set-Cookie", "JSESSIONID=; Max-Age=0; Path=/");
return ResponseEntity.noContent().build();
```

If an attacker already captured the old session ID, deleting the cookie in one browser does not invalidate the server-side session. **Server-side invalidation** is what protects against that. Cookies also require matching Path/Domain for exact removal.

Minimum proper flow in a custom endpoint:

```java
// Core snippet; variables are supplied by a controller with appropriate dependencies.
securityContextLogoutHandler.logout(request, response, authentication);
return ResponseEntity.ok(Map.of("message", "logged out"));
```

In Spring Security 6, `SecurityContextLogoutHandler` has `setSecurityContextRepository(...)`. The full example will make both the security chain and the handler share **the exact same repository bean**, avoiding a "filter saves in store A, logout cleans store B" mismatch.

## 5. What Does a Custom Endpoint NOT Do Automatically?

`SecurityContextLogoutHandler` handles context/session cleanup, but **does not automatically reproduce the entire chain** of `LogoutFilter`. A standard logout configuration may also use:

- `CsrfLogoutHandler`: deletes saved CSRF tokens.
- `TokenBasedRememberMeServices` or `PersistentTokenBasedRememberMeServices`: clears remember-me cookies and/or corresponding token state.
- `LogoutSuccessEventPublishingLogoutHandler`: publishes `LogoutSuccessEvent` for listeners.
- `CookieClearingLogoutHandler`: deletes additional application cookies.
- `HeaderWriterLogoutHandler` with `ClearSiteDataHeaderWriter`: instructs the browser to clear cache/storage/cookies per directive.
- Custom `LogoutHandler`: auditing, revoking device sessions, or product-specific tasks.

**In section 6's demo:** we use form login + `HttpSessionSecurityContextRepository` and **default CSRF tokens stored in the HTTP session**. Invalidating the session also clears CSRF state stored in the session. The demo **does not enable remember-me**, has no OAuth/OIDC, does not use a CSRF cookie repository, and needs no business event listener. Thus calling `SecurityContextLogoutHandler` suffices for the defined session-logout scope, while other features must be added explicitly when a real app uses them.

### 5.1. If Switching to CookieCsrfTokenRepository

In that case the CSRF token can reside in a browser-side cookie rather than only in the session. Invalidating `HttpSession` does not guarantee that cookie is deleted. You must integrate `CsrfLogoutHandler` (using **the exact configured CsrfTokenRepository**) or equivalent cleanup. The snippet below is an **illustration where all dependencies are present**, not a standalone Java program:

```java
CsrfLogoutHandler csrfCleanup = new CsrfLogoutHandler(csrfTokenRepository);
csrfCleanup.logout(request, response, authentication);
securityContextLogoutHandler.logout(request, response, authentication);
```

Run cleanup in the designed order and exception policy; handlers must align with the actual repository. Do not blindly delete CSRF cookies while bypassing valid-token checks on state-changing requests.

### 5.2. If Remember-Me Is Enabled

The `remember-me` cookie can outlive `JSESSIONID`. If a custom logout only invalidates the session, the next request still carries the remember-me cookie and `RememberMeAuthenticationFilter` can automatically restore the identity. Therefore a custom endpoint must invoke cleanup on the corresponding `RememberMeServices`/`LogoutHandler`. Token-based remember-me has limitations revoking stolen cookie copies; persistent tokens provide a repository to revoke per design.

### 5.3. If Using JWTs, Refresh Tokens, OAuth2, or OIDC

`SecurityContextLogoutHandler` **does not turn an issued JWT into an expired token**, does not revoke OAuth2 refresh tokens, and does not log out of an identity provider. With stateless JWTs, every request carries its own bearer credential; dedicated behaviors are required such as client-side token deletion, revocation/denylist/introspection, short-lived access tokens, and refresh-token revocation at the authorization server. With OIDC SSO, local logout is not equivalent to IdP single logout.

Do not promise "log out of all devices" if you only invalidate the current session.

### 5.4. If Using Multiple Servers / Distributed Session Stores

An `HttpSession` is managed by Tomcat/Redis/JDBC/Spring Session depending on infrastructure. The handler must operate through the exact session/repository/session store in use. Clearing an in-memory map or context holder on the current pod is insufficient if the session remains alive in a shared store or if JWTs remain valid. Testing from a real client through a load balancer is necessary.

## 6. Runnable Example: Custom JSON Logout Endpoint + Shared Repository

### 6.1. Goals and Scope

The app has a demo user `alice` with password `demo-pass123`. Spring Security handles `POST /login` via form login and persists the context in the session. We intentionally define `POST /api/auth/logout` using Spring MVC.

Implementation principles:

1. Keep default CSRF enabled. POST missing CSRF receives **403** before reaching the controller.
2. `/api/auth/logout` is `permitAll`, allowing logout handling even when the session has expired. This is only an authorization rule; CSRF is still checked.
3. Use **the same `HttpSessionSecurityContextRepository` bean** for both the Spring Security chain and `SecurityContextLogoutHandler`.
4. `SecurityContextLogoutHandler` invalidates the session and clears authentication and context; the controller returns JSON **after** cleanup.
5. Disable the default logout DSL **intentionally in this demo only**, so no `/logout` route runs alongside. As a result, the demo does not automatically inherit `LogoutFilter`'s remember-me/CSRF-cookie/event cleanup; when extending the app, add them explicitly.
6. `GET /api/me` works only when logged in; a new request after logout without a session redirects to the login page.

The project contains only these files:

```text
custom-logout-demo/
├── pom.xml
├── src/main/java/com/example/customlogout/CustomLogoutApplication.java
└── src/test/java/com/example/customlogout/CustomLogoutApplicationTests.java
```

### 6.2. pom.xml

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
    <artifactId>custom-logout-demo</artifactId>
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

### 6.3. Java Application

Create **`src/main/java/com/example/customlogout/CustomLogoutApplication.java`**:

```java
package com.example.customlogout;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@SpringBootApplication
public class CustomLogoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomLogoutApplication.class, args);
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

    // Same repository for saving context on login and clearing it on logout.
    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityContextLogoutHandler customSecurityContextLogoutHandler(
            SecurityContextRepository repository) {
        SecurityContextLogoutHandler handler = new SecurityContextLogoutHandler();
        handler.setInvalidateHttpSession(true);
        handler.setClearAuthentication(true);
        handler.setSecurityContextRepository(repository);
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository) throws Exception {

        http
            .securityContext(context -> context
                .securityContextRepository(repository)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/api/auth/logout", "/public")
                    .permitAll()
                .requestMatchers("/api/me").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/api/me", true)
            )
            // Demo only: the MVC endpoint manages cleanup itself.
            // Normal apps should keep LogoutFilter/DSL if possible.
            .logout(AbstractHttpConfigurer::disable);

        // CSRF is NOT disabled: POST /login and /api/auth/logout require a token.
        return http.build();
    }

    public record Identity(String username, boolean authenticated) {}

    @RestController
    static class AuthController {
        private final SecurityContextLogoutHandler logoutHandler;

        AuthController(SecurityContextLogoutHandler logoutHandler) {
            this.logoutHandler = logoutHandler;
        }

        @GetMapping("/public")
        String publicResource() {
            return "public";
        }

        @GetMapping("/api/me")
        Identity me(Authentication authentication) {
            return new Identity(authentication.getName(),
                    authentication.isAuthenticated());
        }

        @PostMapping("/api/auth/logout")
        ResponseEntity<Map<String, String>> logout(
                Authentication authentication,
                HttpServletRequest request,
                HttpServletResponse response) {

            // Do not take userId, token, or authenticated status from JSON.
            // Use the Authentication loaded by Spring Security for this request.
            logoutHandler.logout(request, response, authentication);

            // Build response only after handler cleanup has run.
            return ResponseEntity.ok(Map.of("message", "logged out"));
        }
    }
}
```

### 6.4. Analyzing the Runnable Code

**`SecurityContextRepository` is the centerpiece.** In the example, `HttpSessionSecurityContextRepository` is created once and used for both:

- `http.securityContext(...securityContextRepository(repository))`: `SecurityContext` is loaded/saved via the chain's session mechanism.
- `handler.setSecurityContextRepository(repository)`: on logout, the handler knows precisely which store to clean. If the app uses a custom repository, swap both places consistently rather than letting the chain read from A while the controller cleans B.

**`formLogin(...)`** provides `UsernamePasswordAuthenticationFilter` to verify passwords and save the authenticated context after login. The demo does not verify passwords manually in a controller. The BCrypt password is generated at startup for learning; real apps must use database password hashes, proper account lifecycle management, and never hardcode users.

**`permitAll("/api/auth/logout")`** ensures the MVC endpoint passes through the authorization layer. Keeping `anyRequest().denyAll()` prevents unintended access to paths outside the demo. `permitAll` does not skip CSRF and does not let the client self-assign privileges.

**`logout(AbstractHttpConfigurer::disable)`** intentionally disables the default `LogoutFilter` in the demo so the custom route is the **only logout path**. This is acceptable only within the narrow scope of pure session login. When adding remember-me or other mechanisms, add their cleanups or return to the logout DSL; never copy the disable line into production while forgetting the remaining tasks.

**The custom MVC controller** does not return `Authentication` or the session ID in JSON; the output is a secret-free message. `Authentication` can be null if the request arrives from an anonymous client; `SecurityContextLogoutHandler` supports that case. The lesson discourages calling `getSession()` to create a new session on logout.

**Session fixation and CSRF:** Spring Security's form login includes standard session fixation protections; default CSRF uses request tokens. When a user logs out, session invalidation renders session attributes — including the session CSRF token if using the default repository — invalid.

### 6.5. Why Must You Still Call the Handler When Returning 204 Instead of 200?

Changing the output does not change the responsibility to clean up state. You can replace the last two lines of the endpoint with:

```java
// Controller snippet, keeping the logoutHandler.logout(...) call above.
return ResponseEntity.noContent().build();
```

With this code, the controller method's return type signature must be adjusted accordingly (e.g., `ResponseEntity<?>`). Security context/session cleanup behavior does not change because cleanup happens before returning.

## 7. Automated Testing with Spring Security MockMvc

Create **`src/test/java/com/example/customlogout/CustomLogoutApplicationTests.java`**:

```java
package com.example.customlogout;

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
class CustomLogoutApplicationTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass123"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void customMvcLogoutInvalidatesSessionAndReturnsJson() throws Exception {
        MockHttpSession session = login();

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true));

        mvc.perform(post("/api/auth/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"logged out\"}"));

        // Session created by MockMvc must be invalidated server-side.
        assertTrue(session.isInvalid());

        // Do not pass the invalidated session into a new request.
        mvc.perform(get("/api/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void csrfFailureCannotTriggerCustomLogout() throws Exception {
        MockHttpSession session = login();

        mvc.perform(post("/api/auth/logout").session(session))
                .andExpect(status().isForbidden());

        // Without valid CSRF -> controller is not executed, session remains active.
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        // End the session properly in the test.
        mvc.perform(post("/api/auth/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().isOk());
        assertTrue(session.isInvalid());
    }

    @Test
    void anonymousLogoutIsHandledWithoutNullAuthenticationFailure()
            throws Exception {
        mvc.perform(post("/api/auth/logout").with(csrf()))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"message\":\"logged out\"}"));
    }

    @Test
    void getDoesNotPerformLogout() throws Exception {
        MockHttpSession session = login();

        // Only @PostMapping exists; GET is not a logout action.
        mvc.perform(get("/api/auth/logout").session(session))
                .andExpect(status().isMethodNotAllowed());

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk());

        mvc.perform(post("/api/auth/logout").session(session).with(csrf()))
                .andExpect(status().isOk());
    }

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }
}
```

Run:

```bash
mvn test
```

The tests verify:
- **Real flow:** form login → `SecurityContext` in session → controller logout → invalidate `HttpSession` → new request requires login.
- **CSRF:** missing token on POST logout → 403, active login session remains valid.
- **Anonymous:** controller does not assume `Authentication` is always non-null.
- **HTTP method:** GET on the same URI does not log out; this is a POST-accepting API, not a state-changing GET link.
- **Public endpoint:** not every route requires login; authorization is scoped properly.

**Limitations:** `MockMvc` tests run in a simulated servlet environment; these are examples for learners to copy and run `mvn test`, **not a claim that Maven was executed here**. In real environments, E2E testing is still needed for cookie path/domain, HTTPS, distributed session stores, revocation, and additional logout handlers.

### 7.1. Why Not Reuse an Invalidated MockHttpSession?

After the logout call, `MockHttpSession.isInvalid()` can be `true`. Passing that exact object via `.session(oldSession)` into another request can throw an exception due to simulating an invalid session. That is not a security handler bug. To verify the user is logged out, issue a **new request without an authenticated session**, or run real HTTP integration tests with the old cookie and confirm the container does not restore the session.

### 7.2. Checking Only HTTP 200 Is Insufficient

A test that only asserts JSON `{"message":"logged out"}` will **pass even if the controller skips cleanup**, leaving the vulnerability intact. Directly assert session invalidation and test a new request without an authenticated session; in real systems, verify that the **old cookie/session ID** no longer grants access.

## 8. Running Manually and Observing Responses

Start:

```bash
mvn spring-boot:run
```

In a browser:

1. Open `http://localhost:8080/login` and log in with `alice` / `demo-pass123`. Spring Security's default login page supplies the CSRF token.
2. After login, `GET /api/me` returns JSON from the authenticated session.
3. To invoke **custom REST logout**, the frontend sends `POST /api/auth/logout` with the session cookie and a valid CSRF token.
4. On success, the server returns JSON and invalidates the session. Accessing `GET /api/me` again with the expired session prompts for login.
5. If you try `GET /api/auth/logout`, the controller does not perform logout because the mapping only accepts POST. Never use GET to perform logout in browser-cookie-based apps.

Illustrative response while logged in:

```json
{"username":"alice","authenticated":true}
```

On valid logout:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"message":"logged out"}
```

Other headers depend on the container/proxy. The session cookie may still appear in the browser until cleared client-side, but a server-invalidated session ID no longer points to the old login session.

### 8.1. Why Does `curl -X POST` Return 403?

A command without saved cookies or a CSRF token:

```bash
curl -i -X POST http://localhost:8080/api/auth/logout
```

in the demo configuration typically receives **403 Forbidden**. This is expected behavior from `CsrfFilter`, not a controller bug. To test manually with an HTTP client, obtain the cookie and CSRF token from the same session, then send a POST with the corresponding header/form token. `MockMvc` uses `.with(csrf())` to test this flow reliably.

Do not disable CSRF just to make a curl command easier to run in a browser-session app. If you want a stateless bearer-token API without cookies, that is a different architecture requiring separate CSRF/credential revocation evaluation.

### 8.2. Fetch from a Frontend SPA

An SPA using session cookies must ensure it sends cookies (e.g., `credentials: "include"` when cross-origin is permitted), a valid CSRF token, and only treats logout as successful after the server response. **Illustrative**, not a standalone snippet because `csrfTokenFromServer` must come from the app's token-issuing mechanism:

```javascript
const response = await fetch("/api/auth/logout", {
  method: "POST",
  credentials: "same-origin",
  headers: { "X-CSRF-TOKEN": csrfTokenFromServer }
});
if (!response.ok) {
  throw new Error("Logout failed");
}
window.location.assign("/login");
```

If `CookieCsrfTokenRepository` or an SPA CSRF configuration uses a different header, use the exact header name and token source. Do not grab an arbitrary value from localStorage and assume it matches the CSRF repo; exact parameters belong to the app configuration.

## 9. Advanced Scenarios and Avoiding Design Flaws

### 9.1. Keeping LogoutFilter While Adding a Different MVC Route

You could leave default `/logout` enabled while adding a separate MVC `/api/auth/logout`. Two routes will exist: `/logout` handled by `LogoutFilter`, and `/api/auth/logout` handled by the controller. **Danger**: differing cleanup behaviors; default includes remember-me/event/CSRF cleanup that the custom controller does not invoke.

If keeping both routes, test both across all supported auth mechanisms. Never accidentally let the "easier-to-use path" skip revoking remember-me/tokens; when no difference is needed, consolidating everything onto the logout DSL is easier to maintain.

### 9.2. Omitting `setSecurityContextRepository`

`SecurityContextLogoutHandler` defaults to `HttpSessionSecurityContextRepository`. If the chain also uses the simple HTTP session repository, it usually works. However, with a `DelegatingSecurityContextRepository` or custom repository (Redis/DB/context propagation), cleanup may miss the persistence path; explicitly configuring the same repository avoids drift. Compatibility between the repository and context-saving mechanism should be tested per deployment.

### 9.3. Is `request.getSession().invalidate()` Enough?

That acts on the session, yet misses holder/repository cleanup and other handlers. In custom code, someone might think:

```java
// Illustrates the bug: not equivalent to the full SecurityContextLogoutHandler.
request.getSession().invalidate();
SecurityContextHolder.clearContext();
```

It can also **create a new session** if none exists. `SecurityContextLogoutHandler` uses `getSession(false)` and cleans up the repository/context more consistently.

### 9.4. Single-Device Logout vs. All-Device Logout

A custom controller with `SecurityContextLogoutHandler` acts on the **current request's session**. It does not iterate over all other sessions of the user. If the product requires "Log out all devices", you need a policy managing `SessionRegistry`/stores, session/token revocation, and identity, permission, and multi-node propagation checks. `SessionInformation.expireNow()` only marks a session expired and may require the next request to take effect rather than immediately destroying every container session.

### 9.5. Session Fixation and Cookie Path/Domain

After login, Spring Security has session fixation protection; the session ID may change. Logout must invalidate the **current session**, not rely on an ID stored in an external variable. When the browser retains an old cookie, the server must treat that session ID as no longer bound to authentication; clean cookie clearing for good UX also requires matching Path/Domain.

Never expose `JSESSIONID` in URLs, query parameters, logs, or JSON; cookies are credentials, and anyone holding that value can attempt to hijack an un-destroyed session.

### 9.6. Race Conditions with In-Flight Requests

Logout request A may arrive concurrently with request B that already loaded `SecurityContext` before A invalidated the session. `SecurityContextLogoutHandler` cleans A's state and the session, **without necessarily halting B's in-progress work immediately**. For especially sensitive operations, perform authorization/ownership checks at commit time or use centralized token/session revocation with clear semantics. Do not promise that logout instantaneously cancels all concurrent HTTP requests.

### 9.7. Anonymous Logout Should Still Be Safe

You can allow an unauthenticated client to send a POST logout **with valid CSRF**, having the controller invoke the handler with `authentication == null` and return an idempotent 200/204. That helps frontends manage state when a session times out while the UI still shows logged-in controls. Do not create a new session just to log out, and do not disclose whether a username exists.

### 9.8. SSO, OAuth2/OIDC, and Logout Redirects

In SSO, local logout does not mean the IdP has ended its session. OIDC provides an RP-initiated logout flow for supporting providers. If IdP logout is required, a controller returning plain JSON **cannot replace** the proper redirect/protocol flow. Evaluate both local cleanup and IdP/logout callbacks, CSRF/state, and valid redirect URIs.

## 10. Comparing Two Implementations Matching the Same API Contract

### Option A — Preferred in Production

When you only need `POST /api/auth/logout` and a JSON/status response, configure via the DSL:

```java
// Configuration snippet inside SecurityFilterChain.
http.logout(logout -> logout
    .logoutUrl("/api/auth/logout")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("application/json");
        response.getWriter().write("{\"message\":\"logged out\"}");
    })
);
```

Advantages: Spring Security manages the default handlers, easier maintenance, less risk of missing cleanup when enabling remember-me. Unless business logic must run inside a controller, this is the approach to choose.

### Option B — Custom Endpoint for a Clear Reason

This is the `@PostMapping("/api/auth/logout")` from section 6, subject to these conditions:
- Separate the route so `LogoutFilter` does not intercept it first.
- Permit the route in `AuthorizationFilter` (typically `permitAll`).
- Protect POST with CSRF in cookie-based apps.
- Invoke `SecurityContextLogoutHandler` properly with the matching repository.
- Add other cleanups depending on which authentication mechanisms are actually enabled.
- Test not only the response, but also session invalidation/repository state and subsequent requests.

**It is false that "Option B is always more flexible".** If you need to add logic on logout, you can add a `LogoutHandler` in Option A while keeping the full pipeline intact.

## 11. Security Review Checklist

- [ ] There is a clear reason to write an MVC logout endpoint instead of `http.logout()`.
- [ ] Use `POST`/unsafe method with proper CSRF protection in cookie-based web apps; never log out via GET.
- [ ] Custom route has an explicit authorization rule; do not confuse `permitAll` with bypassing CSRF.
- [ ] `SecurityContextLogoutHandler` is invoked in the controller **before returning success**.
- [ ] Handler uses the same repository as the chain's `SecurityContextRepository` configuration.
- [ ] Existing session is invalidated; never call `getSession()` to create a new session just to destroy it.
- [ ] `SecurityContextHolder` and authentication in the repository are cleared, not just browser cookies.
- [ ] `authentication == null` is handled safely; never accept a principal from the client as proof.
- [ ] Accounted for special CSRF token repos, remember-me, logout events, custom cookies, and external token revocation if applicable.
- [ ] Never include `JSESSIONID`, auth cookies, CSRF tokens, or JWT/refresh tokens in responses/logs.
- [ ] Tests verify POST without CSRF returns 403 and does not log out.
- [ ] Tests verify valid POST invalidates the session and a new request requires login.
- [ ] GET on the same URI does not change login state.
- [ ] Multi-node/session stores, race conditions, and SSO/IdP logout are tested per required scope.

## 12. Knowledge Self-Check

1. Why does Spring Security recommend the logout DSL over writing a custom MVC controller?
2. Under what condition must a custom `@PostMapping` have a `permitAll` rule? Does that rule disable CSRF?
3. Why is `SecurityContextHolder.clearContext()` **alone** not a complete logout?
4. Which three state objects/systems does `SecurityContextLogoutHandler` act upon?
5. Why should the **same** `SecurityContextRepository` be used for both the security chain and the logout handler?
6. When `request.getSession(false) == null`, how should the handler behave?
7. In the demo, why was no extra CSRF cookie deletion configured? When is it needed?
8. If a user enabled remember-me, what happens when a custom logout only invalidates the session?
9. Why does returning HTTP 200 after logout not prove a JWT token was revoked?
10. Does `GET /api/auth/logout` perform logout in the demo? Why?
11. Why should tests assert `session.isInvalid()` and subsequent request behavior?
12. What is the difference between a custom MVC logout and a custom `LogoutSuccessHandler`?

**Answer hints:** (1) the DSL includes the built-in cleanup pipeline; (2) controllers run after authorization, and permitAll does not disable CSRF; (3) repository/session may still hold the old context; (4) HttpSession, SecurityContextHolder, and SecurityContextRepository; (5) avoids saving in store A while clearing store B; (6) do not create a pointless session, allow anonymous; (7) session CSRF tokens vanish when the session invalidates, whereas cookie repos need a dedicated handler; (8) the remember-me cookie can auto-login; (9) JWTs have independent validity; (10) no, only PostMapping exists; (11) HTTP 200 can be faked in buggy code; (12) custom success handler changes output while a controller must clear state itself.

## 13. Official Documentation

- Spring Security 6.5 — Handling Logouts, section *Creating a Custom Logout Endpoint*: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security API — `SecurityContextLogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html
- Spring Security API — `SecurityContextRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html
- Spring Security API — `LogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/LogoutHandler.html
- Spring Security — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Security — CSRF Protection (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
