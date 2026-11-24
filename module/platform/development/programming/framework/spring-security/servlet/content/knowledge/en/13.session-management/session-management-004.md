# Session fixation and session identifier rotation strategies

> **Context:** Spring Security 6 on the **Servlet stack** (Spring Boot 3.x, Java 17+). This lesson explains *session fixation* attacks, the principle of changing the session ID after successful authentication, compares the four strategies `changeSessionId`, `migrateSession`, `newSession`, and `none`, and covers integration into form login or custom login flows. Focuses on `HttpSession` and session cookies; does not apply verbatim to Spring WebFlux.

## 1. The problem: a session ID created before login can be exploited

**Session fixation** occurs when an attacker tricks a victim into using a **session identifier the attacker already knows or controls** before the victim authenticates. If, after login, the server **keeps the same session ID**, the attacker can use the known ID to access the session that now carries the victim's identity.

Picture an unprotected flow:

```text
(1) Attacker knows session ID S0
       |
       | tries to make the victim use S0
       v
(2) Victim's browser sends session cookie S0
       |
       v
(3) Victim logs in successfully
       |
       v
(4) Server attaches Authentication to session S0
    but DOES NOT change the ID
       |
       v
(5) Attacker uses S0 to access resources
    with the victim's Authentication
```

This is a **threat model**, not a claim that every application can automatically be forced to accept an attacker's session ID: the ability to “fix” an ID also depends on cookie domain/path, how the server accepts IDs, subdomains, URL rewriting, XSS, reverse proxies, and many other conditions.

**Primary defense:** when the identity boundary shifts from unauthenticated to authenticated, the application must **rotate or replace the session ID**, so the pre-login ID no longer represents the newly privileged session. The new session ID must be delivered to the legitimate client via a secure cookie/session mechanism.

**Remember:** Changing or hashing passwords does not replace session fixation protection. The attack does not need to guess passwords; it exploits a session that is elevated in privilege while keeping its old ID.

## 2. Session ID, HttpSession, SecurityContext: three different things

In a Servlet application:

- `HttpSession` is the server-side session object, with an ID, timeout duration, and attributes, typically accessed via `HttpServletRequest.getSession(...)`.
- `JSESSIONID` is typically the cookie name carrying the **session ID** back to the browser, though the cookie name can be customized. This cookie does not necessarily contain the username, password, or `Authentication` directly.
- `SecurityContext` holds the user's `Authentication`; when an application uses `HttpSessionSecurityContextRepository`, the context can be stored in an `HttpSession` attribute so subsequent requests reload it.

```text
Browser
  |
  | Cookie: JSESSIONID=S1
  v
Servlet container
  |
  +--> looks up HttpSession by ID S1
        |
        +--> session attributes ("cart", "locale", ...)
        |
        +--> SecurityContext (if saved)
                |
                +--> Authentication
                        principal / authorities
```

**A session ID is not Authentication.** A pre-login session may exist solely for UI state, a shopping cart, a CSRF token, or a request cache. After login, the same `HttpSession` or a new session can hold an authenticated `SecurityContext`. That exact **state-elevation** moment is when session fixation protection is needed.

Changing the session ID **does not mean** deleting the shopping cart or resetting every attribute; whether old data is preserved depends on the strategy.

## 3. Distinguishing session fixation from other risks

| Risk | Primary mechanism | Corresponding mitigation |
| --- | --- | --- |
| **Session fixation** | Attacker knows ID before login; app keeps that ID after login | Rotate/replace ID after authentication |
| **Session hijacking** | Attacker steals an **already privileged** ID via XSS, logs, network, client machine | HTTPS, Secure/HttpOnly/SameSite per threat model, XSS defense, log protection, session revocation |
| **Session prediction** | Predictable ID or weak randomness | High-entropy ID generation by container/session store |
| **CSRF** | Browser auto-sends cookies on requests triggered by another site | CSRF token, SameSite, request origin controls |
| **Session replay** | Valid ID is reused while not yet revoked | Logout/invalidation, expiry, revocation, appropriate access bindings |
| **Session fixation via URL rewriting** | ID is passed in the URL and can be shared/logged | Prefer cookies, restrict URL-based session tracking |

A system can rotate the ID properly at login yet still suffer hijacking if the cookie is stolen after login. Conversely, using HTTPS while keeping an ID known to an attacker beforehand can still leave a fixation risk. **Defense in depth is required.**

## 4. Where does Spring Security apply protection?

On the Servlet stack, Spring Security's standard authentication mechanisms can apply **`SessionAuthenticationStrategy`** after authentication succeeds, before the success response completes.

```text
POST /login (credentials + CSRF token)
        |
        v
UsernamePasswordAuthenticationFilter
        |
        v
AuthenticationManager.authenticate(...)
        |
        +--> failure: failure handler; does not elevate session
        |
        +--> success:
               |
               v
        SessionAuthenticationStrategy.onAuthentication(...)
               |
               +--> session fixation protection
               |    changes ID or creates new session per policy
               |
               +--> other session strategies (if configured)
               |
               v
        create/set authenticated SecurityContext
               |
        save context to repository when flow requires
               |
        success handler / redirect / response
```

The diagram depicts the typical form login flow in Spring Security 6; exact ordering and components in a given app depend on the authentication filter and configuration. The key point is **changing the ID after successful authentication**, not merely when visiting the login page, not on every ordinary request, and not treating `HttpSession` as authenticated merely because it exists.

### Why choosing the right hook matters

If a custom controller implements `POST /my-login` and only calls:

```java
Authentication authentication =
        authenticationManager.authenticate(loginToken);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// THIS IS NOT A COMPLETE custom login yet.
```

then `AuthenticationManager` returning a valid `Authentication` **does not automatically** ensure `SessionAuthenticationStrategy` runs. In explicit-save mode, `SecurityContextRepository.saveContext(...)` is also required to keep the login across subsequent requests. Use standard filters whenever possible; if a genuinely custom flow is needed, execute the full lifecycle.

## 5. Four session fixation protection strategies

Spring Security provides a DSL in `HttpSecurity`:

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.changeSessionId()));
```

You can replace `changeSessionId()` with `migrateSession()`, `newSession()`, or `none()` depending on compatibility/policy requirements. These statements are **mutually exclusive alternatives**, not four methods called sequentially in the same configuration.

| Strategy | Session ID handling | Existing attributes handling | When to consider |
| --- | --- | --- | --- |
| **`changeSessionId()`** | Uses `HttpServletRequest.changeSessionId()` (Servlet 3.1+) to change the ID on the existing session | Normally **keeps attributes and session object** | **Default preference** on modern Servlet containers; minimal data disruption |
| **`migrateSession()`** | Invalidates old session, creates a new session with a new ID | **Copies** attributes from old session to new | Older compatibility environments or when a new session object is needed while preserving state |
| **`newSession()`** | Invalidates old session and creates a new session | **Does not normally carry over application attributes**, aside from Spring Security internal attributes per library mechanics | When strict separation between pre/post-login state is desired, accepting cart/preferences loss unless restored intentionally |
| **`none()`** | Does not change ID to prevent fixation | Keeps state per current flow | Only with externally proven security justification; **should not be used for session-based browser login** |

### 5.1. changeSessionId: change the ID without destroying the existing HttpSession

On Servlet 3.1+:

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.changeSessionId()));
```

When session ID `S0` already exists before login, successful authentication instructs the container to change it to `S1`. The application typically keeps attributes like `cart` or `locale`, while the old ID is no longer valid for the elevated session.

```text
Before login:
  HttpSession{id=S0, cart="book-42"}

After login:
  HttpSession{id=S1, cart="book-42", SecurityContext=...}
                     ^
                     changes ID, keeps cart data
```

This is a common choice suited for preserving a pre-login shopping cart experience. Spring Security uses this mechanism as the default strategy on Servlet containers supporting `changeSessionId` (such as modern Boot Servlet environments).

**Do not confuse changing the ID with creating a new session object.** `changeSessionId` changes the ID of the existing session; therefore systems indexing data/metrics by session ID must listen for ID change events and update associations properly.

### 5.2. migrateSession: create a new session and migrate state

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.migrateSession()));
```

Typical flow:

```text
Old session S0: cart="book-42", locale="vi-VN"
     |
     +--> invalidate S0
     +--> create new session S1
     +--> copy appropriate attributes
     v
New session S1: cart="book-42", locale="vi-VN"
```

Strength: preserves pre-login data in environments requiring a new session. Caveat: invalidating the old session and copying/rebinding attributes can trigger side effects for objects implementing `HttpSessionBindingListener` or older container/framework integrations. Test shopping carts, session-backed caches, Spring Session, and application listeners.

Unlike `changeSessionId`, this replaces the **session object** and transfers state rather than just swapping the identifier.

### 5.3. newSession: create a cleaner session after authentication

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.newSession()));
```

With `newSession`, the application does not automatically carry over regular **application attributes** from the pre-login session (such as `cart`, `wizardStep`, or `uiDraft`). Spring Security may preserve its own internal attributes per its contract. Therefore, do not interpret `newSession()` as “wiping every byte related to Spring Security”.

**When to use it?** When anonymous pre-login data is untrusted and must not be merged directly into the newly privileged session—for instance, sensitive workflows requiring completely fresh state after login. The trade-off is that the UI may lose the cart or in-progress step unless a dedicated recovery mechanism is designed.

**Do not accidentally pick `newSession` and then file a bug that “the cart disappears”** without realizing that is the requested behavior.

### 5.4. none: disable the strategy's fixation protection

```java
http.sessionManagement(session -> session
        .sessionFixation(fixation -> fixation.none()));
```

This **disables the session fixation protection provided by this strategy**. If the application retains the same session ID before and after login, this can reopen fixation risks. Consider this only with clear architectural proof that session fixation is controlled by an equivalent reviewed mechanism.

**Never use `none()` to “fix” a lost-session bug** when the real cause is cookie/path/domain, CSRF, reverse proxy, custom login missing `saveContext`, or application state keyed to the old ID. Investigate first and keep ID rotation intact.

## 6. Detailed scenarios that are easily confused

### 6.1. What if there is no HttpSession before login?

Session fixation protection needs an **old session ID** to rotate. If the client had no session prior to authenticating, there is no `S0` to replace. Some flows create a new session when saving context or generating a CSRF token; those situations depend on `SessionCreationPolicy` and the repository.

**Fixation tests must proactively create a session before login**, record the old ID, and then log in within **the same session**. Logging in from a request with no prior session and seeing a new cookie does not prove the code protects against a fixed session.

### 6.2. Does a changed session ID mean the user logged in successfully?

You cannot generalize backwards. Other actors can change session IDs, and the session fixation strategy may not run if there was no old session. To verify login, check that `Authentication` was properly saved/loaded, authorization allows the protected endpoint, and the cookie is sent back.

### 6.3. Does the ID need to change on every HTTP request?

**No.** The goal is to rotate at trust-elevation events, typically successful authentication. Changing the ID on every GET can break session persistence, client concurrency, and multiple tabs, increase container load, and distort observability.

When switching roles/privileges or performing sensitive re-authentication steps, additional rotation may fit the threat model, but must not replace protection at login.

### 6.4. Does a session ID change break the CSRF token?

The CSRF token and session ID are two different things. Under common Spring Security mechanics, when authentication succeeds, `CsrfAuthenticationStrategy` may clear the old CSRF token so a new one is issued; hence forms or SPAs may need to **fetch a fresh CSRF token after login**. Do not confuse token rotation with the session fixation strategy alone.

If an application uses a custom login, integrate CSRF/session strategies according to policy rather than automatically disabling CSRF to make forms work.

### 6.5. Can the old session ID still grant access?

In a proper session fixation protection flow, the pre-login ID must **no longer represent the authenticated session**. With `changeSessionId` the container must remap the session to the new ID; with `migrateSession`/`newSession` the old session is invalidated. Test on the actual container/session store if the application uses a session cluster, reverse proxy, or Spring Session.

**Never accept** a state where both the old and new IDs concurrently access the same authenticated session, unless observing an infrastructure bug to fix. Above all, keep session IDs out of URLs/logs and response caches.

### 6.6. Does changing the ID log out other sessions?

No. Rotating the ID of **one session** after login does not automatically revoke other sessions belonging to the same user. To limit concurrent logins or log out all devices, use `SessionRegistry`, session management/persistence, or a dedicated revocation mechanism suited to your deployment.

## 7. Runnable project: default form login and session ID rotation

Uses **Java 17+**, **Spring Boot 3.3.5 / Spring Security 6.x**, **Gradle 8.5**. The example has three endpoints:

- `GET /visit`: permitted before login, proactively creates an `HttpSession` and saves `cart="book-42"`.
- `POST /login`: form login handled by Spring Security; after successful authentication, uses `changeSessionId`.
- `GET /me` and `GET /cart`: accessible only to authenticated users; proves the ID changed while old data was retained.

The project **does not write a custom login filter** because the standard mechanism exists; this also avoids forgetting `SessionAuthenticationStrategy` or `SecurityContextRepository`.

### 7.1. Directory tree

```text
session-fixation-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    SessionFixationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'session-fixation-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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

### 7.2. Main application

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 7.3. SecurityConfig: keep CSRF, use changeSessionId

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/visit").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED)
                        .sessionFixation(fixation ->
                                fixation.changeSessionId()))
                .build();
    }
}
```

Explanation:

1. `formLogin` creates the default login page and handles `POST /login`; no custom controller is needed for this endpoint.
2. `SessionCreationPolicy.IF_REQUIRED` allows a session when needed. Even though the configuration does not manually specify a repository, form login's standard authentication filter handles context persistence per Spring Security 6 mechanics.
3. `sessionFixation(...changeSessionId())` requires rotating the ID when a session exists prior to successful authentication.
4. `csrf.disable()` is not configured: for form login using session cookies, CSRF is an essential defense; tests must supply a valid CSRF token for `POST /login`.
5. The learning password is hashed with BCrypt before `InMemoryUserDetailsManager` uses it; production must manage accounts/secrets per policy rather than hardcoding.

**Note:** This example only introduces login/session fixation. Real products require policies for session timeout, cookie security, authorization, logout, CSRF, password-guessing protection, and multi-container testing.

### 7.4. Controller creating an anonymous session before login

`src/main/java/demo/DemoController.java`:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/visit")
    public String visit(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("cart", "book-42");
        return "visit-ok";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/cart")
    public String cart(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return "missing-session";
        }
        return String.valueOf(session.getAttribute("cart"));
    }
}
```

`/visit` creates a session before the user authenticates and stores a sample attribute. Because `/visit` has `permitAll()`, the client is not forced to log in there. `/cart` is accessible only to authenticated users; after login, if `changeSessionId` preserves cart data, the body is `book-42`.

### 7.5. MockMvc: verifying old and new IDs

`src/test/java/demo/SessionFixationTest.java`:

```java
package demo;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginChangesSessionIdButKeepsCart()
            throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(get("/visit").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("visit-ok"));

        String beforeLoginId = session.getId();

        MvcResult result = mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        HttpSession loggedInSession =
                result.getRequest().getSession(false);

        assertNotNull(loggedInSession);
        assertNotEquals(beforeLoginId, loggedInSession.getId());
        assertEquals("book-42",
                loggedInSession.getAttribute("cart"));

        // Independent request after login: same session with changed ID.
        mvc.perform(get("/me")
                        .session((MockHttpSession) loggedInSession))
                .andExpect(status().isOk())
                .andExpect(content().string("learner"));

        mvc.perform(get("/cart")
                        .session((MockHttpSession) loggedInSession))
                .andExpect(status().isOk())
                .andExpect(content().string("book-42"));
    }

    @Test
    void anonymousCannotAccessProtectedEndpoint() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void missingCsrfTokenRejectsFormLogin() throws Exception {
        mvc.perform(post("/login")
                        .session(new MockHttpSession())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                        .session(session)
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "wrong"))
                .andExpect(status().is3xxRedirection());

        mvc.perform(get("/me").session(session))
                .andExpect(status().is3xxRedirection());
    }
}
```

**Expected result for the demo configuration:** 4 tests PASS. The first test is the primary proof: we **proactively have a session before login**, capture `beforeLoginId`, log in successfully, then compare it with the post-login ID while checking that the `cart` attribute still exists and the subsequent request is authenticated. The test avoids `@WithMockUser`, because that annotation can pre-populate `Authentication` **without running through the login/session fixation strategy**.

**Note on MockMvc:** MockMvc simulates requests/sessions for Spring MVC unit/integration tests. It proves lifecycle behavior at the application layer, but does not replace real browser/cookie/container testing upon deployment, especially in systems using load balancers, Redis/Spring Session, or multiple nodes.

### 7.6. Running the project

From the `session-fixation-demo` directory, with JDK 17+ and a compatible Gradle installed:

```bash
gradle test
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew test` and `./gradlew bootRun` (macOS/Linux), or `.\gradlew.bat test` and `.\gradlew.bat bootRun` (Windows).

To observe in a browser at `http://localhost:8080`:

1. Open `/visit` to create an anonymous session and set the `cart` attribute.
2. Open `/login`, use `learner` / `study123`. The default login page generated by Spring Security includes a hidden CSRF token field in the form.
3. Log in, then visit `/me`; the expected body is `learner`.
4. Visit `/cart`; the expected body is `book-42`.
5. In DevTools Network/Application, compare the session cookie before and after login. **The ID value is generated at runtime, not predictable beforehand**; the cookie may be updated via a `Set-Cookie` header.
6. Never share real cookie values or session IDs in docs/screenshots/logs.

You can use `curl` with a cookie jar, but you must extract and send the **actual CSRF token** from the `GET /login` form when POSTing; you cannot hardcode a shared token. The browser demo automatically submits the hidden form field matching the generated page. Calling POST `/login` without a CSRF token usually yields 403, not proof that the session fixation strategy is broken.

## 8. Want to switch to migrateSession or newSession: what to do?

On the same project, change just **one line of configuration**:

```java
// Variant A: create new session, copy attributes
.sessionFixation(fixation -> fixation.migrateSession())

// Variant B: create new session, do not keep regular application attributes
.sessionFixation(fixation -> fixation.newSession())

// Variant C: disable the strategy's fixation-protection mechanism
.sessionFixation(fixation -> fixation.none())
```

These are **alternative fragments**, not three lines to place together in Java.

For `migrateSession`, tests must confirm the session ID differs and `cart` still has a value if attributes are migrated. For `newSession`, the ID must differ while `cart` is usually **absent** in the new session. For `none`, an existing anonymous session can retain the same ID across login, which is an **anti-pattern** unless an equivalent protection layer exists.

Do not change the `assertNotEquals` assertion to `assertEquals` just to “make the test PASS” when disabling protection. Tests should encode security intent: if policy requires rotating the ID, `none` must **be treated as failing requirements**, not as equally valid behavior.

### Session data and listeners

With `migrateSession`, when invalidating/copying the session, objects listening via `HttpSessionBindingListener` can receive bind/unbind callbacks; those events can affect application data. When switching from `migrateSession` to `changeSessionId`, test session attribute consumers, listeners, and the session store instead of just checking for status 200.

If the application uses session state to preserve workflows/shopping carts, pick a strategy that preserves data appropriately and test session **identity** before and after on a real container.

## 9. Custom login: must invoke SessionAuthenticationStrategy manually

In Spring Security 6, standard authentication filters know to call the session strategy in the success lifecycle. If you write a custom controller calling `AuthenticationManager.authenticate(...)`, you must ensure **session strategy and persistence** are executed completely.

A Java fragment in the recommended order:

```java
// Illustrative code INSIDE a custom login handler that already has dependencies.
Authentication verified = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, password));

// Session fixation/concurrency/CSRF strategies according to the application's configuration.
sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context =
        SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// In an explicit-save flow, save before the response commits/redirects.
securityContextRepository.saveContext(context, request, response);

// Only after that return a success response or redirect.
```

The code above is **not** a standalone program; `username`, `password`, `request`, `response`, and dependencies must be supplied by the actual handler. Do not copy it in place of standard `formLogin()` unless custom login is truly required.

A strategy bean solely illustrating how to change the ID:

```java
@Bean
SessionAuthenticationStrategy customLoginSessionStrategy() {
    return new ChangeSessionIdAuthenticationStrategy();
}
```

This fragment requires imports for `@Bean`, `SessionAuthenticationStrategy`, and `ChangeSessionIdAuthenticationStrategy`. **Note:** if replacing the composite strategy of a flow that already supports concurrency control/CSRF, using `ChangeSessionIdAuthenticationStrategy` alone may omit those features. In a real application, combine the fixation strategy with `CsrfAuthenticationStrategy` and other session strategies per policy.

### Why order matters

- Saving `SecurityContext` into the session **before** rotating the ID/invalidating the session under a migration strategy can produce unpredictable behavior or lose context in custom setups.
- Committing the response/redirect **before** saving context can prevent the session cookie from updating properly.
- If authentication fails, do not run the success path and do not attach an invalid `Authentication` to a session presumed authenticated.
- Calling the same session strategy **twice** (framework filter and controller) can rotate the session more times than necessary and break cookies/attributes.
- Modifying `SecurityContextHolder` alone without saving under `requireExplicitSave(true)` can cause the next request to lose login even though the session ID changed successfully.

With a custom authentication filter, you can use `AuthenticationFilter`/`AbstractAuthenticationProcessingFilter` and Spring Security's extension points to get clear success/failure handling. Writing a custom login controller also requires planning for remember-me, success handlers, saved requests, session concurrency, CSRF, and logout; **a session fixation strategy does not replace them**.

## 10. SessionAuthenticationStrategy and concurrent-session policy

`SessionAuthenticationStrategy` is the contract applied after an authentication is deemed successful:

```java
void onAuthentication(Authentication authentication,
                      HttpServletRequest request,
                      HttpServletResponse response)
        throws SessionAuthenticationException;
```

The signature above is an illustrative API, not a standalone Java class. `SessionAuthenticationException` is a session-management-related exception that can occur when a concurrent-sessions policy rejects creating another session.

An application may need a **composite session strategy** to perform multiple tasks at the login boundary: enforcing session limits, session fixation protection, session registration, and CSRF token handling. Do not assume that merely calling `changeSessionId` means the application automatically:

- limits a user to logging in on one device;
- invalidates all old sessions after a password change;
- handles session timeout;
- prevents CSRF;
- revokes cookies in other browsers.

If the application uses `SessionRegistry`, Spring Session, or clustering, ID rotation must be compatible with how session state is stored and synchronized. Test these transitions specifically, especially if the system records session IDs in an auxiliary mapping or database.

## 11. SessionCreationPolicy and its impact on fixation

| Policy | Meaning regarding `HttpSession` | Fixation notes |
| --- | --- | --- |
| `ALWAYS` | Spring Security creates sessions per policy | If a session existed before login, rotation is still required |
| `IF_REQUIRED` | Creates a session when needed | Common with form login; does not automatically ensure custom logins invoke the strategy |
| `NEVER` | Spring Security creates no new session itself but may use an existing one | **Not synonymous with stateless**; if a pre-existing session is used then logged in, fixation must still be analyzed |
| `STATELESS` | Spring Security neither creates nor uses sessions to obtain `SecurityContext` | If auth is genuinely not stored in a session, **auth session** fixation is not the main mechanism; still inspect sessions created by other code |

`STATELESS` does not forbid another servlet/controller from creating an `HttpSession`. It only indicates Spring Security does not rely on the session to restore authentication under that policy. If an application uses genuinely stateless bearer tokens/JWTs, login-cookie session fixation is not the same threat model; instead focus on token replay/revocation, XSS, storage, and CSRF depending on how credentials are sent.

**A reasoning mistake:** seeing `JSESSIONID` in a response and concluding for certain that Spring Security stores `Authentication` there. The cookie may come from CSRF, MVC, request cache, or application code. Check the repository and follow-up requests carrying only the session cookie (without Basic/form credentials) to verify authentication persistence.

## 12. Events when session ID changes and auxiliary systems

On Servlet containers supporting `HttpServletRequest.changeSessionId()`, the container can emit ID-change events to registered `HttpSessionIdListener`s:

```java
// Sample signature illustrating the Servlet callback:
@Override
public void sessionIdChanged(
        HttpSessionEvent event, String oldSessionId) {
    String newId = event.getSession().getId();
    // Synchronize mappings in a controlled way if the application tracks secondary data by ID.
}
```

This is a **fragment** inside a listener implementing `jakarta.servlet.http.HttpSessionIdListener`, not a standalone file. Spring Security's `SessionFixationProtectionEvent` can also be published along the corresponding strategy flow.

Auxiliary systems easily overlooked:

1. **Audit/session registries** recording the old session ID: must understand ID-change events so a user does not appear to “vanish” or create duplicate sessions.
2. **Spring Session/Redis clusters:** test that the new session ID is stored and synchronized; check replication/race impacts.
3. **Load balancer sticky sessions:** if keyed on session ID or cookie, ensure ID rotation still routes to the right node.
4. **Shopping carts and workflow state:** with `migrateSession`/`newSession`, test whether attributes persist or drop per policy.
5. **WebSockets/SSE or parallel multi-tab requests:** a request holding the old ID right at rotation time can race; do not allow reusing the old session as an indefinite “grace period”.
6. **CSRF tokens/cookies:** the frontend must update to the new token/session cookie after login instead of reusing pre-login IDs/tokens.

Never write **session ID values** into public logs/metrics. If audit correlation is needed, use an internal non-bearer identifier or a representation that cannot be replayed to access the session.

## 13. Logout, idle timeout, and password changes: no substitute for fixation protection

### Logout

Standard logout typically clears `SecurityContext`, invalidates the session, and may delete cookies per configuration. **Rotating the ID at login does not replace invalidation at logout.** If the browser keeps sending an old cookie, the server must reject it or treat it as an unprivileged session.

### Idle timeout

A rotated session can still expire due to timeout. Timeout is not a direct fixation defense: if an old ID is used to elevate privileges within the valid window, the risk exists even if the session eventually expires. Both timeout and rotation are required.

### Password change or account lock

A session that already holds `Authentication` can remain valid after the account changes password or is disabled, unless the application revalidates/revokes sessions. Rotation at login does not solve subsequent **session revocation**. Establish clear policies for logging out devices or requiring re-login after sensitive changes.

### Cookie security

For production: use HTTPS, appropriate `Secure`/`HttpOnly`/`SameSite` cookies, restricted domain/path, avoid URL rewriting for session identifiers when unnecessary, and defend against XSS/CSRF. Session IDs should be randomly generated by a reputable Servlet container/session framework; never build IDs from usernames, emails, timestamps, or predictable tokens.

## 14. Common implementation errors

| Symptom / bad practice | Problem | How to fix |
| --- | --- | --- |
| Login succeeds yet ID does not change despite prior session | Fixation protection disabled, custom flow skips strategy, or wrong chain | Check `sessionFixation(...)`, authentication filter, session strategy, and test before–after |
| Only running tests without a pre-login session | No old ID to detect fixation | Create an anonymous session before login and compare IDs |
| Using `none()` to keep the cart | Risks preserving the pre-login ID | Choose `changeSessionId()` or `migrateSession()` to rotate ID while keeping attributes |
| Using `newSession()` and losing the cart | Application attributes not migrated by policy | Pick another strategy or selectively migrate verified data |
| Custom controller calls only `AuthenticationManager` | Does not automatically run full session strategy and persistence | Invoke strategy and `saveContext`, or use standard filters |
| Using `changeSessionId` yet client does not save new cookie | Misconfigured client/proxy/cookie | Check `Set-Cookie`, domain/path, `Secure`, `SameSite`, and redirects |
| Rotating ID on every HTTP request | Session/cookie races, unnecessary | Rotate at auth boundaries and intentional privilege-elevation points |
| Writing session ID into query parameters | Can be logged/shared/read from history | Use protected cookies; restrict URL rewriting |
| Confusing rotated CSRF token with session ID | Two separate mechanisms that can both change after login | Inspect each token separately and fetch a new CSRF token when needed |
| Logout only calls `SecurityContextHolder.clearContext()` | Saved session may still hold authentication | Use policy-compliant logout/invalidate context/session |
| Pre-login session cookie acts as authenticated after login | Potential fixation vulnerability if ID truly did not change | Test old-ID reuse on the container and enforce security policy |
| App has multiple SecurityFilterChains, checking the wrong chain | One chain has protection, another does not | Test per matcher/`@Order` and actual login mechanism |

## 15. Security testing checklist

A test suite should prove:

- **Before login:** hit a public endpoint, create an anonymous session and store sample `cart` data; record ID `S0`.
- **Valid login:** send `POST /login` with valid credentials and CSRF; authentication succeeds.
- **After login:** obtain session ID `S1`, verify `S1 != S0` under `changeSessionId`/`migrateSession`/`newSession`.
- **Attribute policy:** `changeSessionId` and `migrateSession` retain valid data; `newSession` does not carry over ordinary application attributes.
- **Old ID:** on a real container, ID `S0` cannot access the authenticated session.
- **Subsequent requests:** the new session cookie accesses protected endpoints without resending credentials in session-based configurations.
- **Wrong login:** failed authentication creates no newly privileged session; the session fixation strategy must not be treated as succeeded.
- **CSRF:** missing token on POST login is rejected when CSRF is enabled; the new token is managed properly after login.
- **Logout:** the authenticated session is invalidated per policy; the old cookie/session ID no longer grants access.
- **Chains:** verify the session policy on each `SecurityFilterChain`; do not extrapolate from a single URL's result.
- **Infrastructure:** test on a production-like container/browser/proxy/session store, not only MockMvc.

Do not merely assert `response.status == 302` on login: a redirect can represent failure, and status 200 alone does not prove the ID changed. Tests should verify **before–after sessions, authenticated context, and session data** as shown in the example.

## 16. Self-check

1. **What is session fixation?** An attacker makes a victim use a session ID known to the attacker before login; if the ID stays unchanged after login, the attacker can use that ID to exploit the elevated session.
2. **Why does rotating the session ID after login reduce risk?** The old ID no longer points to the authenticated session, so an attacker knowing the pre-login ID cannot gain access.
3. **How does `changeSessionId()` differ from `migrateSession()`?** `changeSessionId` uses the Servlet API to change the existing session's ID; `migrateSession` invalidates the old session and creates a new one, copying attributes.
4. **Does `newSession()` keep the whole shopping cart?** No; it does not transfer regular application attributes, though it may keep internal Spring Security attributes.
5. **Is `none()` safe for browser session login?** Usually not without another equivalent control; it disables the strategy's fixation protection.
6. **Why should tests create a session before login?** There must be a session ID `S0` to prove it was replaced; logging in cold without a prior session does not properly test fixation risk.
7. **Does Spring Security `formLogin` usually integrate a session strategy?** Yes; the standard authentication filter runs it in the successful authentication flow.
8. **Is calling `SecurityContextHolder.setContext` alone sufficient in a custom controller?** No; you may need to invoke `SessionAuthenticationStrategy.onAuthentication` and `SecurityContextRepository.saveContext` in an explicit-save flow.
9. **If the session ID changes, are all other sessions logged out?** No, session fixation rotation applies only to the session currently authenticating.
10. **Does `STATELESS` require session fixation rotation for session-based login?** If genuinely no auth session is used, auth-session fixation does not apply in the same way; still evaluate any other sessions created by the application.
11. **Does HTTPS automatically protect against fixation?** Not completely; TLS protects transport but does not fix a server retaining a session ID known to an attacker before login.
12. **Should you change the strategy to preserve UI state without security testing?** No. Choose the policy based on security and data behavior, and test both the new ID and attribute migration.

**Takeaway:** Session fixation protection guards **the moment a session elevates in privilege**. On modern Servlet containers, prefer `changeSessionId()`: it rotates the session ID after successful authentication while typically keeping attributes. `migrateSession()` creates a new session and migrates state; `newSession()` separates pre/post-login application state; `none()` disables protection and requires extreme caution. If writing custom login, integrate `SessionAuthenticationStrategy` and `SecurityContext` saving in the proper lifecycle. Test with **an anonymous pre-login session and an authenticated post-login session**, not merely by checking HTTP status codes.
