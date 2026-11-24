# Verifying Session Creation, Session ID Rotation, and SecurityContext Persistence

> Scope: form-based login (`formLogin`) in **Spring Security Servlet 6.x**, running on **Spring Boot 3.x / Java 17+**. The goal is to observe three outcomes of a successful login: an HTTP session exists when needed, the session ID is rotated to prevent session fixation, and authentication state is persisted so subsequent requests reuse it. WebFlux/reactive, OAuth2, and JWT behaviors are outside the scope of this lesson.

## 1. What Must Be Proven?

Successful login is not merely receiving HTTP 302 after `POST /login`. Distinguish three independent assertions:

1. **Session creation:** a login request can create an `HttpSession` if none existed previously and policy permits storing state. The indicator is `request.getSession(false) != null` after processing; do not call `getSession()` to check, as that call creates a session itself.
2. **Session ID rotation:** if a session already existed prior to login, successful authentication normally changes `session.getId()`. In Servlet 3.1+, the default `changeSessionId` strategy keeps the session and its attributes while rotating only the ID. This reduces *session fixation* risk.
3. **Persisting and restoring `SecurityContext`:** after authentication, the `SecurityContext` holding `Authentication` is saved via `SecurityContextRepository`. Subsequent HTTP requests sending the matching session cookie must be recognized as the same user **without resending the password**.

| Indicator | What to observe | What cannot yet be concluded |
| --- | --- | --- |
| `HttpSession` exists | Session is present after login | Does not prove authentication created it; CSRF or `RequestCache` may have created it earlier |
| Session ID changed | ID differs before and after login when **a prior session existed** | Does not mean all session attributes were wiped; `changeSessionId` preserves attributes |
| `SecurityContext` saved | Valid authentication in the store and on the next request | Seeing `SecurityContextHolder` hold authentication **within the same request** does not prove persistence |
| Re-accessing a resource | `GET /me` with the same session returns the username | `@WithMockUser` or `with(user(...))` does not test the real login flow |

## 2. Actual Mechanics After `POST /login`

`formLogin` uses `UsernamePasswordAuthenticationFilter` to read `username` and `password` and invoke `AuthenticationManager`. On success, the main flow includes:

```text
Browser                                   Servlet App
    |                                          |
    |-- GET /me (unauthenticated) ------------>|
    |<-- 302 /login ---------------------------| may save SavedRequest/session
    |-- GET /login --------------------------->| login page/CSRF token
    |<-- 200 + form ---------------------------|
    |-- POST /login + CSRF + credentials ----->| UsernamePasswordAuthenticationFilter
    |                                          | 1. AuthenticationManager authenticates
    |                                          | 2. SessionAuthenticationStrategy
    |                                          |    -> changeSessionId() if session exists
    |                                          | 3. Create SecurityContext with Authentication
    |                                          | 4. SecurityContextRepository.saveContext()
    |<-- 302 + session cookie (when needed) ---|
    |-- GET /me + session cookie ------------->| repository reloads SecurityContext
    |<-- 200 "student" ------------------------| authenticated request
```

**Three components easily confused:**

- `HttpSession` is server-side per-session attribute storage; the browser normally holds only a **session ID** in a cookie (`JSESSIONID` by default in Servlet containers, though the name can vary with Spring Session or custom config). The cookie does not contain the entire `SecurityContext`.
- `SecurityContextHolder` is the access point for authentication state **within the current request** (typically using a thread-bound strategy). It is not durable cross-request storage.
- `SecurityContextRepository` controls how the context is **saved/loaded**. Spring Security 6 defaults to `DelegatingSecurityContextRepository`, combining `RequestAttributeSecurityContextRepository` for request/dispatch scope and `HttpSessionSecurityContextRepository` for subsequent requests. When stored in the session, the default attribute key is `SPRING_SECURITY_CONTEXT`.

In Spring Security 6, `SecurityContextHolderFilter` loads the context but **does not automatically save** arbitrary changes. Standard `formLogin` handles saving upon successful login; if authenticating manually in a controller/filter, you must save the context explicitly. Do not assume calling `SecurityContextHolder.setContext(...)` alone suffices for the next request.

### Why Rotate the Session ID?

In a session fixation attack, an attacker tricks a victim into using a session ID known to the attacker and waits for the victim to log in. Rotating the ID upon authentication prevents the pre-login session ID from becoming an access key for the authenticated session.

With Servlet 3.1+ and the default `changeSessionId` strategy:

- **Pre-existing session:** the ID rotates, while the same `HttpSession` retains needed attributes.
- **No pre-existing session:** a session can be created to store post-login state; there is no "old ID" to compare against.
- `migrateSession` creates a new session and copies attributes; `newSession` creates a new session retaining fewer attributes; `none` disables fixation protection and should not be used casually.

This is why a test for **ID rotation** must explicitly supply a pre-login session, whereas a test for **session creation** must start without one.

## 3. Runnable Spring Boot Example

Create a Spring Boot 3.x (Java 17+) application with these dependencies:

```groovy
// build.gradle - dependencies section of a Spring Boot project with plugins configured
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Create three Java files in the same package `example.sessioncheck`. The config explicitly writes out `SessionCreationPolicy.IF_REQUIRED` and `changeSessionId` for visibility, even though these are also the usual defaults for stateful form login.

**`src/main/java/example/sessioncheck/SessionCheckApplication.java`**

```java
package example.sessioncheck;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCheckApplication.class, args);
    }
}
```

**`src/main/java/example/sessioncheck/SecurityConfig.java`**

```java
package example.sessioncheck;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
            );
        // Keep default CSRF enabled; POST /login requires a CSRF token.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password("{noop}test-pass")
                .roles("USER")
                .build()
        );
    }
}
```

`{noop}` is only to keep this example simple—**never use plaintext passwords in real environments**; use a proper `PasswordEncoder` (such as BCrypt). `formLogin` generates `GET /login` and handles `POST /login` automatically; no login controller is needed for the example to run.

**`src/main/java/example/sessioncheck/WhoAmIController.java`**

```java
package example.sessioncheck;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/me")
    String me(Authentication authentication) {
        return authentication.getName();
    }
}
```

When `GET /me` is authenticated via `student`'s session, the exact response body is:

```text
student
```

When unauthenticated, `/me` is protected and normally redirects to the login page. Do not rely on a single login `302` response alone to conclude that the context was persisted.

## 4. Testing All Three Properties with MockMvc

Create **`src/test/java/example/sessioncheck/FormLoginSessionTest.java`**. This is an integration test loading the real `SecurityFilterChain` and exercising real form login: do not use `@WithMockUser`, because mocking a user per request bypasses authentication and session ID rotation.

```java
package example.sessioncheck;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class FormLoginSessionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginCreatesSessionAndPersistsContext() throws Exception {
        // Pass no session into POST: verify a session exists after authentication.
        MvcResult login = mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "test-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"))
                .andReturn();

        HttpSession session = login.getRequest().getSession(false);
        assertNotNull(session, "A session must exist after login to store context");

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
        assertInstanceOf(SecurityContext.class, saved);
        SecurityContext context = (SecurityContext) saved;
        assertNotNull(context.getAuthentication());
        assertEquals("student", context.getAuthentication().getName());

        // Second request uses only the session; DO NOT resend username/password.
        mvc.perform(get("/me").session((MockHttpSession) session))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("student"))
                .andExpect(content().string("student"));
    }

    @Test
    void successfulLoginChangesIdOfExistingSession() throws Exception {
        MockHttpSession beforeLogin = new MockHttpSession();
        beforeLogin.setAttribute("shoppingCart", "book");
        String originalId = beforeLogin.getId();

        mvc.perform(post("/login")
                    .session(beforeLogin)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "test-pass"))
                .andExpect(status().is3xxRedirection())
                .andExpect(authenticated().withUsername("student"));

        assertNotEquals(originalId, beforeLogin.getId(),
                "changeSessionId must rotate the ID after authentication");
        assertEquals("book", beforeLogin.getAttribute("shoppingCart"),
                "changeSessionId preserves attributes of the old session");
        assertNotNull(beforeLogin.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY));
    }

    @Test
    void rejectedLoginDoesNotEstablishAuthenticatedContext() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "wrong"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?error"))
                .andExpect(unauthenticated());

        assertNull(session.getAttribute(
                HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY));
        mvc.perform(get("/me").session(session))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void postWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/login")
                    .param("username", "student")
                    .param("password", "test-pass"))
                .andExpect(status().isForbidden());
    }
}
```

Run in the root directory **of the example app**:

```bash
./gradlew test --tests example.sessioncheck.FormLoginSessionTest
./gradlew bootRun
```

On Windows, use `gradlew.bat` accordingly. A successful test run produces **4 passing tests**; Gradle logs and report paths vary by project, so no fixed stdout snippet is quoted.

**Why these assertions are trustworthy:**

1. The first test verifies that a session exists **after** login, then inspects the context key in the session; the next request returning `student` proves the context was reloaded.
2. The second test explicitly supplies a pre-existing session and captures `originalId` **before** login. Seeing a different ID afterward proves session fixation protection. The intact `shoppingCart` attribute proves `changeSessionId` did not wipe the whole session.
3. The wrong-password test verifies no authenticated context is stored and the follow-up request remains blocked. A session may still exist for other reasons; never treat "session exists" as proof of successful login.
4. The missing-CSRF test proves submitting valid credentials alone is insufficient for `POST /login`. Never disable CSRF just to make tests pass easily.

`MockMvc` uses mock Servlet requests/sessions; it tests Spring Security behavior inside the app, yet **does not replace** verifying real cookies, domain/path, `Secure`, `HttpOnly`, `SameSite`, and reverse proxies in a real browser/container.

## 5. Observing in the Browser (Without Confusing Sessions with Cookies)

After starting the app at `http://localhost:8080`, open a private browser window and DevTools → **Network** and **Application/Storage → Cookies**:

1. Visit `/me` while unauthenticated. You will typically see a redirect to `/login`. A session may already appear due to saving `SavedRequest` or CSRF; note it if present, but do not conclude it is an authenticated session.
2. On `/login`, note **the session cookie name and pre-login ID** (if present). The default form includes a CSRF token.
3. Log in with `student` / `test-pass`. Observe the `POST /login` request, redirect response, and post-login session cookie value. If a pre-login ID existed, the post-login ID must differ due to `changeSessionId`. In standard Servlet containers, the cookie may be `JSESSIONID`; cookie name and attributes depend on infrastructure.
4. Load `/me` with **the same browser/cookie**. The response body is `student`. Verify the request sends the active session cookie and does not resend username/password.
5. Log out via the UI or execute `POST /logout` with a CSRF token, then revisit `/me`. The old session must no longer grant access.

Never copy real session IDs into logs, issues, shared screenshots, or chats: an active session ID is sensitive credential material. Automated tests can compare IDs in memory without printing them.

### Interpreting Easily Misunderstood Observations

| Observation | Proper explanation / next check |
| --- | --- |
| Cookie exists before login | Normal: request cache, CSRF, or app code may create a session before authentication |
| Login succeeds yet no "ID rotation" observed | Likely **no session existed** before login to rotate; retry with a pre-existing session or run `successfulLoginChangesIdOfExistingSession` |
| After login, `SecurityContextHolder` has authentication, yet `GET /me` redirects to login | Check `saveContext`, session policy, context repository, whether the cookie is sent back, and whether the session expired |
| `Set-Cookie` appears, yet next request is unauthenticated | Check cookie domain/path/`Secure`/`SameSite`, load balancer/session store, proxy, timeout, and whether the response wrote the new session ID |
| `GET /me` works when test uses `@WithMockUser` | That injects a mocked test identity without testing form login, ID rotation, or persistence |
| `POST /login` returns `403` | First check the CSRF token; in `MockMvc` you need `with(csrf())` |
| Session exists before/after without `SPRING_SECURITY_CONTEXT` | Check repository config, whether authentication truly succeeded, or whether the app uses a custom store |

## 6. Distinguishing Session Creation Policies

`SessionCreationPolicy` controls how **Spring Security** uses sessions, and does not automatically prevent other application components from creating an `HttpSession`:

| Policy | Meaning for Spring Security | Impact on tests |
| --- | --- | --- |
| `ALWAYS` | Always creates a session | Seeing a session exist does not prove login created it |
| `IF_REQUIRED` | Creates when needed; fits stateful form login | Can create at login if none existed earlier |
| `NEVER` | Security does not create one itself, yet may use an existing session | Can be affected by sessions created by MVC, CSRF, or request cache |
| `STATELESS` | Neither creates a session nor reads `SecurityContext` from one | Default stateful persistence tests do not apply; other components may still create sessions independently |

Therefore, before concluding the app "doesn't create sessions" or "drops context", inspect `SessionCreationPolicy`, `SecurityContextRepository`, `RequestCache`, CSRF config, and the active authentication path together. Do not apply stateful form-login conclusions to bearer-token APIs.

## 7. If You Write a Custom Login API

The snippet below **illustrates only saving the context**, not a standalone controller. After `AuthenticationManager` returns an authenticated `Authentication`, an app using Spring Security 6 can do:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
```

The variables `authentication`, `securityContextRepository`, `request`, and `response` must be supplied in your actual filter/controller. In a custom login filter, invoke the appropriate `SessionAuthenticationStrategy` **before saving** if session fixation protection is needed, and coordinate success/failure handlers, CSRF, errors, and redirects in order. Standard `formLogin` already performs these login steps, so **you do not need** to call `saveContext` again in the Section 3 example.

Key takeaway: `SecurityContextHolder.setContext(context)` only sets state for the current processing thread; `securityContextRepository.saveContext(context, request, response)` is the persistence step when explicit save is required. Never let the response complete/commit before saving.

## 8. Lesson Completion Checklist

- [ ] Executed a real login via `POST /login` with valid credentials **and a valid CSRF token**.
- [ ] Starting without a session, an `HttpSession` exists after login and its context holds a valid `Authentication`.
- [ ] Starting with a pre-created session, the pre-login and post-login IDs **differ**, while attributes are preserved under `changeSessionId`.
- [ ] Inspected the `SPRING_SECURITY_CONTEXT` session attribute directly (under the default repository).
- [ ] A follow-up `GET /me` carrying only that session still returns `student`.
- [ ] Wrong passwords and missing CSRF both fail to establish an **authenticated** session.
- [ ] Tested real browser cookies when verifying servlet container/proxy behavior.

### Official Source References

- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security — MockMvc Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
