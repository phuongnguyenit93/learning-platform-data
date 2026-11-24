# Session Fixation and Session Identifier Rotation Strategies

## 1. What Is Session Fixation and Why Does It Relate to Login?

In a web application using HTTP sessions, the browser typically sends a cookie such as `JSESSIONID`. The cookie holds the **session identifier** (*session ID*), not the user's entire identity. The Servlet container uses that ID to look up the `HttpSession` object on the server. When a user logs in successfully, Spring Security can save the `SecurityContext` containing `Authentication` into the session so subsequent requests recognize the user without re-entering the password.

**Session fixation** is a scenario where an attacker obtains or pre-controls a session ID that the victim will use, and then gets the victim to log in on **that exact session**. If the application keeps the same ID across the *unauthenticated → authenticated* boundary, someone who knew the ID beforehand can attempt to reuse it to hijack the authenticated session.

Simplified attack flow:

~~~text
Before authentication                     After authentication
──────────────────────────────────────────────────────────────
Attacker knows session ID "S-OLD"
            │
            └── victim is led to use session "S-OLD"
                                      │
                           Victim enters the right password
                                      │
                      Application DOES NOT change session ID
                                      │
                          Session "S-OLD" is now logged in
                                      │
                 Anyone knowing "S-OLD" can try reusing
                 the session that has been authenticated
~~~

**Core solution:** when a login creates a new authentication state, **change the session ID** so an identifier someone else may have known beforehand is no longer the key to the authenticated session.

~~~text
Pre-login session: S-OLD (anonymous)
          │
          ├── Login fails → no privilege escalation
          │
          └── Login succeeds
                     │
                Session fixation protection
                     │
          New identifier: S-NEW (authenticated)
                     │
          S-OLD cannot be used to access the authenticated
          session after transition
~~~

Distinguish session fixation from:

- **Session hijacking:** an attacker steals a session ID *after* the user has logged in. Changing the ID at login **does not** by itself prevent ID theft afterward.
- **Session replay:** a still-valid ID is reused. Session fixation protection prevents keeping the old ID across login; defending against replay requires HTTPS, secure cookies, XSS protection, and session management.
- **Session timeout:** the server expires a session after a period of inactivity or an absolute lifetime. Rotating the ID at login does not replace timeout.
- **Session logout:** invalidating the logged-in session. Rotating the ID is not a logout operation.
- **CSRF:** abusing the browser's automatic cookie attachment to send unwanted actions. CSRF and session fixation are two distinct problems requiring separate mitigations.

This lesson uses **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Servlet/Spring MVC**. The APIs and strategies below apply to authentication **with HTTP sessions**. A `SessionCreationPolicy.STATELESS` chain that does not use sessions to store `SecurityContext` follows a different model.

## 2. Why Does a Session Exist Before Login?

"Not logged in" does not mean "no session." An anonymous request can still create an `HttpSession` to store:

- A CSRF token (if using `HttpSessionCsrfTokenRepository`).
- Temporary session data such as shopping cart, language, registration wizard, or navigation state.
- Saved request: the URL requested before login, to redirect back after logging in successfully.
- Attributes placed into the session by libraries or the servlet container.

Example:

~~~text
GET /login → cookie JSESSIONID=S-OLD
POST /login + cookie S-OLD + username/password
→ if login succeeds, should switch to S-NEW
GET /me + cookie S-NEW → authenticated identity
GET /me + cookie S-OLD → must not receive that identity
~~~

Keeping **application data** and keeping the **session identifier** are two different things. An application may need to keep a shopping cart when the user logs in while still discarding the old ID. This is why Spring Security provides multiple strategies: changing the ID directly on the existing session, or creating a new session and transferring data according to policy.

## 3. When Does Spring Security Handle Session Fixation?

Spring Security performs protection upon a **successful authentication event** in a login mechanism integrated with session management, such as form login. The authentication mechanism invokes the appropriate `SessionAuthenticationStrategy`; the session fixation strategy executes before completing the login session creation process.

An overview of a form login flow:

~~~text
POST /login + credentials + CSRF token
       │
       ▼
CsrfFilter checks CSRF (if enabled)
       │
       ▼
UsernamePasswordAuthenticationFilter
       │
       ▼
AuthenticationManager / AuthenticationProvider
       │
       ├── Wrong credentials
       │     └── AuthenticationFailureHandler
       │           (no new authenticated session)
       │
       └── Success: valid Authentication
                   │
                   ▼
           SessionAuthenticationStrategy
                └── Session fixation strategy
                    rotates ID or replaces session
                   │
                   ▼
           Saves SecurityContext per filter's mechanism
                   │
                   ▼
           AuthenticationSuccessHandler
                   │
                   ▼
           Browser continues with the new session ID
~~~

Points easily misunderstood:

1. **Do not rotate the ID on every request.** Identifier rotation is tied to successful authentication; you should not continuously rotate it on every GET because it can break parallel tabs/requests.
2. **Do not promote on wrong password.** A session may still exist for CSRF, error messages, or the shopping cart, but must not be upgraded to an authenticated session.
3. **Not every "has Authentication" is form login.** Stateless Basic/Bearer typically authenticates per request and does not need a fixed session; if you intentionally save them to a session, you must evaluate fixation protection in that custom flow.
4. **Spring Security 6 has an important change:** `SessionManagementFilter` is not used by default; the authentication mechanism itself is responsible for calling `SessionAuthenticationStrategy`. If you write custom JSON login in a controller and only call `AuthenticationManager.authenticate(...)`, do not assume the ID rotation strategy will run automatically.
5. **Fixation protection is one part of the session lifecycle.** It does not provide HTTPS, does not fix insecure cookies, and does not configure all concurrent policies such as concurrent sessions.

## 4. Four Strategies: changeSessionId, migrateSession, newSession, none

Spring Security provides options via the DSL:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
);
~~~

Choose only **one** strategy for a chain that needs session management. On Servlet 3.1+ (including Spring Boot 3's modern Servlet environment), **`changeSessionId` is the default** when session fixation protection is used under standard configuration.

| Strategy | How it works | Pre-login session attributes | Notes |
| --- | --- | --- | --- |
| `changeSessionId()` | Uses container's `HttpServletRequest.changeSessionId()` to swap the ID without creating a new session | **Retained** in the same session and attributes | Default, preferred on Servlet 3.1+; minimal impact on session data. |
| `migrateSession()` | Invalidates old session, creates new session, copies **all** attributes | **Transferred** to the new session | May trigger callbacks/lifecycle events affecting session-bound objects. |
| `newSession()` | Creates a "clean" new session without transferring ordinary app data; Spring Security-related attributes may still be copied | **Does not automatically transfer** ordinary application attributes | Suitable when you want strong separation from pre-login data, though may lose needed state. |
| `none()` | Performs no session fixation protection | Old ID may be kept across login | **Not recommended**: can leave a session fixation vulnerability open. |

### 4.1. changeSessionId() — change ID, keep session

With Servlet 3.1+:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
);
~~~

It uses the servlet container's capability to replace the identifier of an existing session. Conceptually, you can picture it as:

~~~text
Existing HttpSession:
  id = OLD
  attributes = {
     "cartDraft": "Java book",
     "locale": "vi"
  }

Successful authentication + changeSessionId()

HttpSession:
  id = NEW
  attributes = {
     "cartDraft": "Java book",
     "locale": "vi",
     ... post-login security attributes ...
  }
~~~

Key points:

- **No need to copy attributes to a new session** because the existing session has its ID changed in place.
- The pre-login ID is no longer a valid identifier for the logged-in session.
- The application suffers fewer side effects from destroying and recreating the session.
- Can emit an ID change event to `HttpSessionIdListener`, while Spring Security publishes `SessionFixationProtectionEvent` when applying protection.
- Requires Servlet 3.1+; do not use this strategy on overly old containers.

In practice, Spring Boot 3 runs on modern Servlet containers, so this is usually the best choice. How the new ID is sent back to the browser depends on the container/cookies and response; inspect via DevTools rather than manually crafting a `JSESSIONID` cookie.

### 4.2. migrateSession() — create new session, transfer all attributes

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.migrateSession())
);
~~~

Flow:

~~~text
Old Session S1:
    cartDraft = "Java"
    uiLocale = "vi"
    customDraft = ...

      invalidate(S1)
             │
     create new session S2
             │
     copy session attributes
             ▼
New Session S2:
    cartDraft = "Java"
    uiLocale = "vi"
    customDraft = ...
    Post-authentication SecurityContext
~~~

Advantage: protects against fixation while keeping existing anonymous data, convenient for checkout/login or continuing a wizard.

Points to consider:

- This is **not** just changing an ID; invalidating and creating a new session can trigger lifecycle logic.
- Copying attributes can involve `HttpSessionBindingListener`, session-scoped beans, and bind/unbind callbacks. Check whether the application has listeners managing resources.
- All existing attributes (including arbitrary data) are transferred under this policy; if the application does not want pre-login data entering the authenticated session, consider `newSession()` or classifying data explicitly.
- Does not mean "deep-copying the entire server object graph elsewhere"; the API's meaning is transferring attributes within the container-managed session lifecycle.

### 4.3. newSession() — create a new session with application data separated

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.newSession())
);
~~~

Spring Security creates a new session **without copying ordinary application attributes**. However, Spring Security-related attributes may still be transferred so the security mechanism continues to work. Therefore, saying "the new session has absolutely zero attributes" is inaccurate.

Example:

~~~text
Old session:
  cartDraft = "Java"
  anonymousFlow = "step2"
  SPRING_SECURITY_... = ...

Successful login with newSession()

New session:
  (does not automatically contain cartDraft, anonymousFlow)
  (may still contain Spring Security-related attributes)
  SecurityContext = authenticated user
~~~

When choosing `newSession()`, the development team must decide which pre-login data truly needs to carry over to the post-login session. Do not enable it merely because "new" sounds safer: it can drop shopping carts, onboarding steps, redirect info, or UI state. For required data, implement a **validated, bounded, and verified** transfer mechanism instead of arbitrarily copying every attribute.

### 4.4. none() — disable fixation protection

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.none())
);
~~~

This configuration **does not change the ID as a session fixation defense**. It does not mean "no session exists." If logging in with a session while leaving the pre-login ID unchanged, someone who knew the ID beforehand may be able to use the session once it becomes authenticated.

Do not choose `none()` just to preserve `JSESSIONID` for the frontend, avoid "losing state," or fix a failing test. If the system is completely stateless, declare `SessionCreationPolicy.STATELESS` by design; there is no reason to disable fixation protection on an active login web session.

### 4.5. Comparison by Real-World Scenario

| Need | Usually suitable choice | Notes |
| --- | --- | --- |
| Standard web login on Boot 3 / modern Servlet | `changeSessionId()` | Default; keeps pre-login attributes and rotates ID. |
| Older container lacking `changeSessionId` support | `migrateSession()` | May be default on Servlet 3.0 or earlier; not applicable to modern Boot 3 Servlet. |
| Need to keep cart/wizard across login | `changeSessionId()` or `migrateSession()` | Still audit pre-login session contents. |
| Do not want anonymous state carried into authenticated session | `newSession()` | Identify which business data genuinely needs to be kept. |
| Token-authenticated API, completely session-independent | `STATELESS` on API chain | This is a session creation/usage policy, not a fixation strategy. |
| Want to "turn it off so it runs easily" | **Do not choose `none()`** | Find the root cause of the session/cookie/test failure. |

## 5. Choosing a Strategy Does Not Replace Other Session Policies

Several configurations have similar names but solve different problems:

- `sessionFixation(...changeSessionId())`: swaps the ID on authentication to defend against fixation.
- `sessionCreationPolicy(IF_REQUIRED)`: allows creating a session when needed, suitable for web login.
- `sessionCreationPolicy(STATELESS)`: Spring Security does not create a session and does not use a session to retrieve `SecurityContext`, suitable for token-based APIs.
- `maximumSessions(1)`: limits concurrent authenticated sessions, does not replace ID rotation.
- `invalidSessionUrl("/session-expired")`: sends the user to a handler when a request has an invalid session ID; does not itself provide fixation protection.
- `logout().invalidateHttpSession(true)`: invalidates the session on logout, distinct from rotating the ID on login.
- Cookie `HttpOnly`, `Secure`, `SameSite`: protects cookie access/transmission and browser contexts; does not replace a session fixation strategy.

**Why not use only `HttpOnly`?** An `HttpOnly` cookie prevents JavaScript from directly reading the ID, but does not change the fact that an ID could already be known beforehand for many other reasons. Identifier rotation on privilege elevation is still needed. Similarly, `SameSite` helps reduce certain cross-site requests, but does not cure fixation the way ID rotation does.

## 6. Runnable Example: Form Login Automatically Rotates Session ID

Demo objectives:

1. An anonymous user has a pre-login session (e.g., from CSRF or temporary data).
2. When `student` logs in via form, Spring Security uses `changeSessionId()`.
3. The `cartDraft` application attribute in the session is preserved.
4. A post-login request to `GET /me` retrieves the principal from the session.
5. The session ID is not exposed in JSON responses or application logs.

### 6.1. Dependencies and Project Structure

Create a Spring Boot 3.x project with Java 17+, Spring Web, Spring Security, and Spring Boot Test dependencies. In a Gradle project with the Spring Boot plugin, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The snippet above is the `dependencies` and test configuration section, **not a standalone `build.gradle` file**. The package used throughout is `com.example.sessionfixation`:

~~~text
src/main/java/com/example/sessionfixation/
  SessionFixationApplication.java
  SecurityConfig.java
  WebController.java

src/test/java/com/example/sessionfixation/
  SessionFixationTest.java
~~~

### 6.2. SessionFixationApplication.java

~~~java
package com.example.sessionfixation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionFixationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionFixationApplication.class, args);
    }
}
~~~

### 6.3. SecurityConfig.java

~~~java
package com.example.sessionfixation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Explanation:

- `changeSessionId()` is written explicitly to learn how to configure it, even though on Servlet 3.1+ this is usually the default.
- `IF_REQUIRED` allows Spring Security to create a session when saving `SecurityContext`; do not use `STATELESS` for web form login.
- `formLogin` registers the standard authentication filter and success/failure handling. That mechanism executes `SessionAuthenticationStrategy` upon successful authentication.
- `logout` handles invalidating the session and clearing the security context. Logout does not need `changeSessionId` to address fixation.
- The demo password is one-way hashed with BCrypt when creating the user; hardcoded accounts are strictly for learning.

When using this as a foundation for production, configure a real user store, password policy, timeout, HTTPS, cookie flags, login attempt limits, secure logging, and endpoint permissions. The example does not address those requirements automatically.

### 6.4. WebController.java

~~~java
package com.example.sessionfixation;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WebController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "public");
    }

    @GetMapping("/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

Here `Principal` is supplied by Spring Security from the authenticated login session. The controller does not need to and **must not** return the session ID to the browser in JSON. A session ID is a secret equivalent in value to session access.

### 6.5. Running the Application

In the project directory containing the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Visit `http://localhost:8080/me` while unauthenticated; the application redirects to the login page. Log in as `student` / `demo-pass` using Spring Security's form; afterward, `GET /me` returns JSON:

~~~json
{"username":"student"}
~~~

HTTP on `localhost` here is for testing only. When deploying, **you must use HTTPS**. Never use demo accounts or passwords in real environments.

## 7. Automated Testing with MockMvc: ID Changes, Data Remains

MockMvc allows testing the `POST /login` flow and `HttpSession` without writing session IDs to logs. We pre-initialize an anonymous session so the test has a **pre-login** ID; without a pre-login session, there is no old ID to compare against.

File `src/test/java/com/example/sessionfixation/SessionFixationTest.java`:

~~~java
package com.example.sessionfixation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginChangesExistingSessionId() throws Exception {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute("cartDraft", "java-book");
        String beforeLoginId = session.getId();

        MvcResult login = mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "demo-pass")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession afterLogin =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(afterLogin);

        // Compare IDs only in the test; do not print this token to logs.
        assertNotEquals(beforeLoginId, afterLogin.getId());

        // changeSessionId preserves pre-existing application session data.
        assertEquals("java-book", afterLogin.getAttribute("cartDraft"));

        mvc.perform(get("/me").session(afterLogin))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void failedLoginDoesNotPromoteAnonymousSession() throws Exception {
        MockHttpSession session = new MockHttpSession();
        String beforeLoginId = session.getId();

        mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "wrong-password")
            )
            .andExpect(status().is3xxRedirection());

        // No successful authentication to trigger ID rotation.
        assertEquals(beforeLoginId, session.getId());

        mvc.perform(get("/me").session(session))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void subsequentGetDoesNotRotateSessionAgain() throws Exception {
        MockHttpSession session = new MockHttpSession();

        MvcResult login = mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "demo-pass")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession afterLogin =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(afterLogin);
        String authenticatedId = afterLogin.getId();

        mvc.perform(get("/me").session(afterLogin))
            .andExpect(status().isOk());

        assertEquals(authenticatedId, afterLogin.getId());
        assertFalse(afterLogin.isInvalid());
    }

    @Test
    void logoutInvalidatesAuthenticatedSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "student")
                    .param("password", "demo-pass")
            )
            .andExpect(status().is3xxRedirection());

        mvc.perform(
                post("/logout")
                    .session(session)
                    .with(csrf())
            )
            .andExpect(status().is3xxRedirection());

        // Logout invalidates the session, unlike rotating the ID on login.
        assertFalse(!session.isInvalid());
    }
}
~~~

Explanation of each test:

| Test | Check | Expected |
| --- | --- | --- |
| `successfulLoginChangesExistingSessionId` | Anonymous session exists before login; valid credentials | `beforeLoginId != afterLogin.getId()`, `cartDraft` still exists, user accesses `/me` successfully. |
| `failedLoginDoesNotPromoteAnonymousSession` | Wrong password submitted | No authentication success; session is not escalated. |
| `subsequentGetDoesNotRotateSessionAgain` | GET after successful login | ID stays the same across normal GETs. |
| `logoutInvalidatesAuthenticatedSession` | POST logout with CSRF | Session is invalidated. |

In a large test suite, avoid state dependencies between tests and avoid exposing session IDs in assertion failures outside internal environments. `MockHttpSession` simulates the lifecycle; to verify **real cookies** and whether a client can replay an old ID, add integration tests using an embedded Servlet container/browser.

Run the tests:

~~~bash
./gradlew test --tests com.example.sessionfixation.SessionFixationTest
~~~

Or on Windows:

~~~powershell
.\gradlew.bat test --tests com.example.sessionfixation.SessionFixationTest
~~~

If the project has all dependencies and every assertion passes, Gradle reports `BUILD SUCCESSFUL`; this is the **expected** outcome, not an executed test log. The code depends on Spring Boot/Security, so `javac` without the corresponding classpath will not compile standalone.

### 7.1. Case With No Session Before Login

When login occurs before the browser has a session, the backend may **create a new session** to store the authenticated state. In that case there is no "pre-login anonymous ID" to compare against; this is **not** proof that fixation protection failed to run. That is why the test intentionally establishes an anonymous session before login.

### 7.2. How to Verify migrateSession and newSession?

Change a single configuration line in `SecurityConfig`:

~~~java
.sessionFixation(fixation -> fixation.migrateSession())
~~~

or:

~~~java
.sessionFixation(fixation -> fixation.newSession())
~~~

Then adjust the test assertions according to their semantics:

- `migrateSession()`: new session object, new ID, `cartDraft` is copied over; do not keep a reference to the old session as an authentication source.
- `newSession()`: new session object, new ID, `cartDraft` is not automatically copied; Spring Security-related attrs may remain per framework mechanism.
- `changeSessionId()`: same session kept, new ID, `cartDraft` remains in the same session.

**Do not apply all three in the same chain.** They are mutually exclusive options. If you want to compare them automatically across multiple test classes, use separate test configurations or separate sample applications for each strategy rather than mutating live config while multiple tests run in parallel.

## 8. Browser Verification: What Must Be Observed?

In DevTools → Network / Application → Cookies, check in the local demo environment:

1. Before login: if the application already created a session, the browser holds a session cookie. Note the **change** in ID for testing purposes, but **never copy real IDs into tickets, chat, or logs**.
2. Submit the login form properly with the CSRF token provided by Spring Security.
3. After login: the response may contain `Set-Cookie` updating the session ID; the browser sends the new ID in the `GET /me` request.
4. The request to `/me` while authenticated returns the username JSON.
5. If you test sending the **old ID** from before login in an isolated test environment, it must not represent the logged-in session. Never test against real user sessions or production environments.
6. Log out via the standard flow: the post-login session is invalidated; neither the old nor new ID remains an authenticated session.

Use DevTools to inspect `Set-Cookie`, `Cookie`, and cookie attributes, while keeping in mind that JavaScript typically **cannot read `HttpOnly` cookies**. That is the intended behavior. The browser and Servlet container control cookie lifecycle; Spring Security decides the session management strategy.

### 8.1. Why Shouldn't JavaScript Send the Session Cookie Manually?

For session-based applications, keep the cookie `HttpOnly` and let the browser attach it automatically when valid. Never put `JSESSIONID` in login JSON, `localStorage`, or a custom header to "keep the session after rotation." Those approaches expose the ID to XSS, logs, telemetry, or frontend code.

On same-origin frontends, the browser sends cookies automatically. For cross-origin frontends, `fetch` needs appropriate `credentials` settings and proper CORS/cookie policies; those issues are **separate** from rotating the ID at login.

### 8.2. Does Each Tab Have Its Own ID?

Normally, tabs within the same browser profile share cookies for the same domain/path. Rotating the session ID in one tab can affect requests from another tab if it sends the old cookie or runs concurrently.

In applications with many AJAX requests, test login/logout boundaries across multiple tabs and concurrent requests. Do not rotate the ID on every API request to "increase security": doing so easily causes races and random 401s.

## 9. Custom JSON Login: You Must Call SessionAuthenticationStrategy Yourself

A real-world mistake is writing a controller like this:

~~~java
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(username, password));

SecurityContextHolder.getContext().setAuthentication(authentication);

// Missing sessionAuthenticationStrategy.onAuthentication(...)
// Possibly missing securityContextRepository.saveContext(...)
~~~

This is only an **incomplete illustrative snippet**, demonstrating a design flaw. `AuthenticationManager.authenticate(...)` verifies credentials; it **does not automatically ensure** a custom controller runs session ID rotation logic and persists the result for subsequent requests.

In Spring Security 6, when authenticating manually, invoke the appropriate session strategy **after successful authentication** and save `SecurityContext` to the repository:

~~~java
// Java/Spring pseudocode: dependencies are injected from the real configuration.
Authentication authentication = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        input.username(), input.password()));

sessionAuthenticationStrategy.onAuthentication(
    authentication, servletRequest, servletResponse);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(
    context, servletRequest, servletResponse);
~~~

If using `ChangeSessionIdAuthenticationStrategy`, the core logic is `HttpServletRequest.changeSessionId()` on the existing session. However, in a real application, the session strategy may also include CSRF token rotation, concurrency control, and session registration. Do not replace the entire composite with a single call and accidentally drop important steps.

To implement JSON login safely:

- Configure the custom flow's `SessionAuthenticationStrategy` to match session fixation, CSRF, and concurrent session requirements.
- Call `onAuthentication` only **after** authentication succeeds, before saving/completing the response.
- Save context via `SecurityContextRepository`; in Spring Security 6, `SecurityContextHolderFilter` does not auto-save changes by default.
- Keep CSRF protection for POST login when relying on session cookies, and issue a new token after authentication per the CSRF lifecycle.
- Whenever possible, use built-in authentication filters or framework-supported strategies to avoid manually orchestrating multiple lifecycle hooks.
- Do not generate session IDs yourself with UUIDs or write them to `Cookie`; let the Servlet container manage IDs/cookies.

You should also avoid calling `request.getSession().setAttribute("SPRING_SECURITY_CONTEXT", ...)` directly as the entire solution. Session/context persistence must stay consistent with the configured repository and filter chain.

## 10. Events and Listeners: Observing Rotation Properly

When Spring Security applies session fixation protection, the framework can publish `SessionFixationProtectionEvent`. With `changeSessionId()` on a compatible Servlet container, the Servlet API's `HttpSessionIdListener` also receives ID change notifications.

Important points for operations:

| Hook | Where it appears | What is it used for? |
| --- | --- | --- |
| `SessionFixationProtectionEvent` | Spring application context | Observing that Spring Security applied protection upon successful authentication. |
| `HttpSessionIdListener` | Servlet container | Receiving notifications when a session ID changes via the Servlet mechanism. |
| `HttpSessionListener` | Servlet container | Tracking session creation/destruction; does not mean every rotation is a destroy/create pair. |
| HTTP `Set-Cookie` | Browser/network | Verifying the browser received the new session ID and cookie attributes. |

If the application registers **both** Spring and Servlet listeners, avoid double-counting the same login rotation event. `changeSessionId` does not create a new session, so do not expect matching `sessionDestroyed` / `sessionCreated` events. Conversely, `migrateSession`/`newSession` can trigger a different lifecycle because sessions are destroyed/created.

**Never log full old/new session IDs.** A session ID is a sensitive credential. Log only timestamps, strategy type, non-sensitive request correlation ID, success status, and masked metadata. Avoid putting session IDs in URLs, analytics, or client error responses.

## 11. Protecting Cookies and Sessions Beyond Fixation

Changing the ID at login is necessary but not sufficient. With Spring Boot, you can configure cookie attributes for HTTPS production environments:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
~~~

These values are **examples to adjust according to architecture**. `SameSite=Lax` is often helpful when frontend and backend are on the same site; when truly cross-site, review the cookie model, CORS, CSRF, and browser third-party cookie policies.

A production checklist:

| Layer | Control | Does session fixation replace it? |
| --- | --- | --- |
| Transport | Proper end-to-end HTTPS, never send session cookies over HTTP | **No.** |
| Cookie | `HttpOnly`, `Secure`, `SameSite`, scoped `Path`/`Domain` | **No.** |
| XSS | Output escaping, proper CSP, prevent script injection | **No.** |
| CSRF | Token/request checks for state-changing operations | **No.** |
| Session fixation | Rotate ID on authentication elevation | This is the direct control. |
| Logout | Invalidate session, clear context and cookies per policy | **No.** |
| Timeout | Idle timeout/absolute lifetime based on risk | **No.** |
| Authorization | Authorization per principal/authority, checked on every request | **No.** |
| Session store | Clustered session management, replication, Redis if needed | **No.** |
| Monitoring | Track login failures, session anomalies, never log secret IDs | **No.** |

**Tip:** if the application allows a user to elevate from a regular role to a sensitive role after re-authentication, also evaluate the **privilege elevation** step. Some business flows must rotate the session ID when raising the assurance level or switching principals, not only on the initial form login. Never assume the framework automatically rotates IDs for every application-driven privilege transition.

## 12. Common Mistakes and How to Handle Them

### Mistake 1: Seeing the ID change after login and thinking "the session was lost"

With `changeSessionId()`, **the ID changes while application attributes remain**. If data is lost, check whether the application uses `newSession()`, manually invalidates the session, has a listener clearing attributes, resets the session store, or the browser sends the wrong cookie.

Do not disable fixation protection to "keep JSESSIONID unchanged." Fix the lifecycle/session handling instead.

### Mistake 2: Choosing migrateSession and seeing strange behavior in session-scoped beans

Because the old session is invalidated and a new session is created with copied attributes, `HttpSessionBindingListener` callbacks or session lifecycle events can run differently from `changeSessionId`. If session objects manage resources, explicitly test bind/unbind callbacks and copyability. On modern Servlets, consider `changeSessionId()` if you need to preserve attributes with minimal side effects.

### Mistake 3: Using newSession and losing the shopping cart

`newSession()` does not automatically copy ordinary app attributes. If the shopping cart is a business requirement, choose `changeSessionId()`/`migrateSession()` or implement a **validated and audited** data transfer step. Also check whether any untrusted pre-login data should be discarded.

### Mistake 4: JSON login returns 200, yet the session ID does not rotate

Check whether the custom controller/filter calls `SessionAuthenticationStrategy.onAuthentication(...)`. Spring Security 6 does not run `SessionManagementFilter` by default to catch every custom login. If you manually call `SecurityContextHolder.setContext(...)` and forget the strategy, fixation protection may not execute.

### Mistake 5: JSON login returns 200, yet the next request still gets 401

A different bug: the context was only placed on the current thread without saving via `SecurityContextRepository.saveContext(...)`. This is a **persistence** issue distinct from fixation; both can happen simultaneously. Check cookies, repository, session policy, proxies, and browser credentials.

### Mistake 6: Using STATELESS for session-based web login

`SessionCreationPolicy.STATELESS` stops Spring Security from using sessions to obtain `SecurityContext`. That is a choice for stateless APIs, not a way to rotate web form login session IDs. Split token APIs and web sessions into separate chains with distinct matchers and session policies if the application uses both mechanisms.

### Mistake 7: Set-Cookie is present, yet the session does not persist

Check `Secure` on plain HTTP environments, `SameSite`/domain/path, cross-origin `fetch credentials`, reverse proxies, and session store config. Rotating the ID cannot force a browser to send a cookie blocked by browser policies.

### Mistake 8: Confusing 401/302 after logout with fixation

Logout normally invalidates the session, requiring re-login. Rotation on login invalidates the old ID. Both can lead to redirects/401s when a request uses an old ID, but **the causes and tests differ**. Use the "pre-login / post-login / post-logout" checkpoints and inspect responses + cookies rather than guessing from status codes.

### Mistake 9: Enabling listeners and double-counting events

A single ID rotation via `changeSessionId` can emit both `SessionFixationProtectionEvent` and `HttpSessionIdListener`. Counting both as "two logins" skews metrics. Choose one authoritative source or deduplicate.

### Mistake 10: Putting session IDs into logs for debugging

Do not log full `Cookie`, `Set-Cookie`, or raw session IDs. When testing ID rotation, compare inside internal tests instead of copying secrets. If correlation is required, generate a separate non-sensitive request ID; do not use the session ID as a public request-tracking ID.

### Mistake 11: Rotating the ID on every request instead of on elevation

Multiple parallel requests from a browser may send the old cookie right as one request rotates the ID; continuous rotation easily causes races and random logouts/401s. Session fixation protection should be tied to **authentication success** or an explicitly designed privilege elevation event, not placed in a `OncePerRequestFilter` on every request.

### Mistake 12: Believing copying all attributes is always safe

Pre-login session data may have been influenced by an anonymous user. After login, the app must validate any transferred data before using it in sensitive actions. `migrateSession` speaks only to *preserving attributes*, not certifying their safety.

## 13. QA Matrix: Covering Every Case

| Code | Setup | Behavior to observe |
| --- | --- | --- |
| FIX-01 | Anonymous session before login, valid password | Before/after IDs differ with `changeSessionId`. |
| FIX-02 | Anonymous session before login, wrong password | Session is not promoted to authenticated. |
| FIX-03 | Successful login, subsequent GETs | ID does not rotate on normal GETs. |
| FIX-04 | Use pre-login ID via separate test HTTP client | Cannot access with the newly logged-in identity. |
| FIX-05 | `changeSessionId()` with `cartDraft` | ID changes, data remains. |
| FIX-06 | `migrateSession()` with `cartDraft` | New session, new ID, data transferred. |
| FIX-07 | `newSession()` with `cartDraft` | New session, new ID, ordinary attribute not auto-transferred. |
| FIX-08 | `none()` in an isolated learning environment | Demonstrates lack of rotation compared to other strategies; **do not deploy**. |
| FIX-09 | Custom JSON login | Calls strategy and saves context in order; ID rotates and next request is authenticated. |
| FIX-10 | Logout after login | Authenticated session invalidated; cannot access with old cookie. |
| FIX-11 | Multi-tab browser / concurrent requests | No random session loss from misconfigured rotation. |
| FIX-12 | Production HTTPS, hardened cookies | Browser sends new cookie with proper `Path`/`SameSite`/`Secure`. |
| FIX-13 | Session listeners/events | Events not double-counted; old/new IDs not exposed. |
| FIX-14 | Stateless bearer-token API | Does not rely on HTTP session to retrieve `SecurityContext`. |

For each test, distinguish **session ID**, **session data**, **SecurityContext**, **session cookie**, and **authentication state**. A test checking only a `200` response is not enough to confirm session fixation is prevented.

## 14. Limitations to Keep in Mind

- **Rotating the ID does not erase user data.** With `changeSessionId`, the goal is to discard an identifier that might already be known, not destroy the session.
- **Does not solve all session hijacking.** If the new ID is stolen after login, you still need HTTPS, HttpOnly, XSS defense, timeouts, and anomaly detection.
- **Does not replace CSRF.** Cookies can still be automatically attached by browsers to requests; CSRF tokens must be properly managed.
- **Not the same as refresh token rotation.** An HTTP session ID is a container-managed session identifier; OAuth2 access/refresh tokens have their own lifecycle and revocation mechanisms.
- **Does not apply automatically to every custom login.** In Spring Security 6, custom filters/controllers must coordinate SessionAuthenticationStrategy and SecurityContextRepository.
- **Does not mean only one session exists.** Concurrent session control is an independent feature; each browser/device can hold its own session per policy.
- **Does not guarantee distributed network control.** In multi-node clusters, a proper session store/replication is required. Rotating an ID on one node with inconsistent stores/cookies still causes errors.
- **Should not be disabled for convenience.** If rotation exposes state-handling bugs, fix the data-transfer logic and cookies instead of enabling `none()`.

## 15. Summary

**Session fixation occurs when a potentially pre-known session identifier is kept across the login boundary.** Spring Security prevents this risk by rotating the session ID upon successful authentication.

- `changeSessionId()`: **recommended default on modern Servlets**; changes the ID on the existing session, preserves attributes.
- `migrateSession()`: replaces the session, transfers all attributes; requires testing listeners and pre-login data.
- `newSession()`: replaces the session and does not copy ordinary application attributes; may still retain required Spring Security attributes.
- `none()`: disables fixation protection, not recommended for session-based web apps.
- `SessionCreationPolicy.STATELESS`: policy for non-session APIs, **distinct** from choosing an ID rotation strategy.
- Standard form login integrates session strategy; **custom JSON login must invoke the strategy and save SecurityContext** if using HTTP sessions.

The most reliable verification is to **create an anonymous session before login, log in with valid credentials, compare old/new IDs, and verify the new session is authenticated**, while confirming attributes are kept/dropped per policy and the old cookie is rejected in integration tests.

### References

- Spring Security Reference 6.5 — Authentication Persistence and Session Management (Session Fixation Protection): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security Reference 6.5 — Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security Reference 6.5 — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security Reference 6.5 — Testing with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Security Reference 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Jakarta Servlet API — HttpServletRequest.changeSessionId(): https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
