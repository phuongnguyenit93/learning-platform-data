# Session Fixation and Why Session Identifiers Must Change After Login

> **Topic:** Spring Security – fundamentals → **Sessions and cookies**. This lesson explains **session fixation**, why a user must be issued a **new session ID upon successful authentication**, how Spring Security protects by default, how to choose `changeSessionId` / `migrateSession` / `newSession`, and how to write tests verifying the mechanism actually works. The focus is **Servlet + Spring MVC + Spring Security 6 / Spring Boot 3.x**, along with comparisons to stateless and reactive architectures.

## 1. Foundational Mindset: The Session ID Is the "Key" to the Session

HTTP does not inherently remember independent requests. A form-login application typically uses a **server-side session** to link subsequent requests to an authenticated identity:

1. The server creates an `HttpSession`, bound to a random, unpredictable session identifier.
2. The server sends the identifier to the browser, commonly via the `JSESSIONID` cookie when using the default Servlet container. If using Spring Session or another setup, the name may be `SESSION` or a custom name.
3. The browser sends back the cookie when visiting the same site according to cookie policies.
4. The server looks up the identifier → session data (containing or linking to `SecurityContext` / `Authentication`, depending on configuration).
5. If the server accepts the identifier and the session holds valid authentication, the request is treated as belonging to the logged-in session.

Simplified diagram:

```text
Browser                                      Server
  |  GET /public                            |
  |---------------------------------------->|
  |  Set-Cookie: JSESSIONID=SID_A; ...      |  Session SID_A
  |<----------------------------------------|  not logged in
  |                                         |
  |  POST /login + credentials              |
  |  Cookie: JSESSIONID=SID_A               |
  |---------------------------------------->|
  |  Login succeeds                         |  SecurityContext / Authentication
  |  Set-Cookie: JSESSIONID=SID_B; ...      |  Session bound to SID_B
  |<----------------------------------------|
  |                                         |
  |  GET /account                           |
  |  Cookie: JSESSIONID=SID_B               |
  |---------------------------------------->|
  |  User's private content                 |
  |<----------------------------------------|
```

**Mandatory security requirement:** `SID_A` (the pre-login identifier) and `SID_B` (the identifier used after logging in) **must differ** whenever a pre-authentication session exists and fixation protection is active. Session data does not necessarily have to be wiped; **what must be severed is the ability to keep using the old identifier to access the post-authentication session**.

A session ID is not a password, yet it is a **bearer secret**: anyone holding a valid identifier and presenting it to the server can be treated as the session owner if no additional checks exist. Protecting the session ID is akin to protecting a credential.

## 2. What Is Session Fixation?

**Session fixation** occurs when an attacker forces a victim to **use a session identifier that the attacker already knows or controls before the victim logs in**, and then exploits the server keeping that same identifier after authentication.

Mental scenario:

1. The attacker opens the application and obtains a pre-login session ID, e.g., `SID_FIXED`.
2. Through a weak channel (URL rewriting carrying the session ID, cookie injection on a compromised domain/subdomain, misconfigured proxy/cookies, XSS, or a mechanism accepting client-supplied session IDs), the attacker causes the victim's browser to send `SID_FIXED` to the application. **Being able to plant a session on the victim's browser is a precondition, not something that happens by default on every site.**
3. The victim logs in with their own account.
4. If the application **keeps** `SID_FIXED` and upgrades that session into an authenticated session, the attacker can continue sending `SID_FIXED` to be recognized as the victim.
5. The attacker does not need to know the victim's password, because the identifier has become the "key" to the logged-in session.

Illustration of the vulnerability:

```text
Attacker knows SID_FIXED
           |
           v
Victim browser is pinned to SID_FIXED
           |
           v
Victim logs in successfully
           |
           v
[Weak app] SID_FIXED still points to authenticated session
           |
           v
Attacker uses SID_FIXED → can impersonate victim
```

Illustration of the defense:

```text
Attacker knows SID_FIXED
           |
           v
Victim logs in with SID_FIXED
           |
           v
[Spring Security] changes session ID to SID_NEW
           |
           +--> SID_FIXED is no longer a valid key for the authenticated session
           |
           v
Victim uses SID_NEW; attacker only knows SID_FIXED → cannot enter
```

**Difference from session hijacking:** In hijacking, an attacker obtains an **already valid post-login session ID**, for example via malware, XSS, unencrypted traffic, or leaked logs. In fixation, the attacker **knows the ID beforehand** and tries to make that ID remain valid after login. **Rotating the ID at login is the primary defense against fixation**, though it does not prevent all forms of post-login cookie theft; you still need HTTPS, cookie flags, XSS defenses, logout, timeouts, and other safeguards.

### 2.1. Conditions and limits of the attack scenario

Not every website lets a client dictate an arbitrary session ID. Servlet containers typically only accept an ID matching a real existing session; URLs containing `;jsessionid=...` only work when the corresponding URL-rewriting mode is enabled/accepted. Whether a browser accepts a cookie set by a subdomain also depends on `Domain`, host-only cookies, cookie prefixes, browser policies, and site state. Thus one cannot say "sending any link always hijacks a session."

The defense goal is not to rely on "planting cookies is hard so we're safe," but to establish an **authentication boundary**: an anonymous session identifier **must never become the token of an authenticated session** when a user logs in successfully.

## 3. Why Must the ID Change *After* Login?

### 3.1. The moment of privilege elevation

Before login, the same session might hold a shopping cart, preferences, a return URL, an anti-CSRF token, or public page state. After login, the session becomes what the server looks up for authentication and/or higher-privilege state. That is when **the object granting access to the session changes criticality**.

If the identifier does not change, anyone who knew it during the anonymous phase gets a chance to use it as an authenticated bearer credential. If the ID is rotated to a new value that only the victim receives over a secure connection, an attacker holding the old ID loses access to the logged-in state.

Logical relationship:

```text
Before:
SID_OLD → anonymous session

Login accepted + session fixation protection:
SID_OLD ✕ can no longer be used to access the authenticated session
SID_NEW → same session data preserved (per strategy) + authentication
```

Why **not rotate only at logout**: the moment the victim logs in is precisely the dangerous window. Waiting until logout leaves the attacker time to use the old SID. Why **not change only the cookie on the frontend**: the server must also invalidate the old ID mapping. Swapping the cookie string in the browser while the server still considers the old ID valid is insufficient.

### 3.2. Changing the ID differs from "wiping all session data"

Suppose an unauthenticated guest has `cartId=42` and `theme=dark` in their session. After login, keeping the shopping cart may still be desired. **ID rotation** does not require deleting those attributes.

- `changeSessionId`: changes the identifier on the existing session, typically preserving attributes because the session object itself is not replaced.
- `migrateSession`: creates a new session and copies attributes from the old session.
- `newSession`: creates a cleaner session without arbitrarily migrating application data; necessary Spring Security internal attributes can still be preserved per framework mechanics.

Therefore, a UX requirement to "keep the shopping cart" is never a reason to disable fixation protection. Choose the right strategy and explicitly control which anonymous state is allowed to carry forward into the authenticated session.

### 3.3. Does a failed login rotate the ID?

By default, the fixation strategy runs upon **successful authentication**, not merely because a request targets `/login`. A mistyped password does not constitute "privilege elevation" the way a successful login does. Still, systems may have policies rotating IDs on other triggers; always test actual flows rather than guessing from URLs.

## 4. How Does Spring Security Handle Session Fixation?

In **Servlet/Spring MVC**, Spring Security includes session fixation protection in session-based authentication flows. On Servlet 3.1+ (including modern Servlet containers used in Boot 3.x), the common default choice is **`changeSessionId`**. <cite>See Spring Security Reference, Authentication Persistence and Session Management.</cite>

Standard functional sequence:

```text
GET public page
  |
  v
Pre-login session exists? (may or may not)
  |
  v
Form login filter checks username/password
  |
  +--> Failure: no privilege elevation
  |
  +--> Success:
          |
          v
       SessionAuthenticationStrategy (integrated login filter)
          |
          v
       Session fixation protection
          |
          v
       Session ID is rotated or new session is created
          |
          v
       SecurityContext is saved for subsequent requests
          |
          v
       Response sends appropriate session cookie to browser
```

**Version note:** In Spring Security 6, `SessionManagementFilter` **is no longer installed by default in the filter chain** in the old way; authentication mechanisms such as form login are responsible for invoking `SessionAuthenticationStrategy`. Therefore, with a custom authentication filter/controller, you cannot always expect `SessionManagementFilter` to magically detect login and rotate the session ID. You must integrate the strategy and persistence properly.

### 4.1. Four strategies and the default choice

| DSL in `sessionFixation` | What happens | Application session data | When suitable |
|---|---|---|---|
| `changeSessionId()` | Calls Servlet `HttpServletRequest.changeSessionId()` on the existing session without replacing the session object | Preserves attributes | Common default on Servlet 3.1+; usually the best choice for modern apps |
| `migrateSession()` | Invalidates old session, creates a new session, and copies attributes | Typically copies all attributes | When session migration is needed, or legacy container compatibility; watch lifecycle listeners |
| `newSession()` | Creates a "cleaner" new session replacing the old one | Does not arbitrarily copy app attributes; internal security attributes may be kept | When you want to isolate pre-/post-login anonymous state |
| `none()` | Does not rotate ID via Spring Security fixation strategy | Keeps old session/ID per active mechanism | **Not recommended**, unless an equivalent safeguard is proven and tested |

**More precisely:** `changeSessionId()` requires a Servlet container supporting the Servlet 3.1+ API; on very old containers lacking this API, Spring Security may default to `migrateSession`. Choosing a strategy does not create a session in every situation: there must be an existing session or an appropriate session creation policy. When logging in without any prior session, comparing "before ID vs. after ID" is not meaningful as a rotation from an old ID.

### 4.2. Common configuration in Spring Security 6

The Java snippet below is a **`@Bean` method** placed inside a `@Configuration` or Boot configuration class; it is not a standalone file:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**", "/login").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form.permitAll())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId()))
        .build();
}
```

When running on a modern Servlet container, Spring Security normally already applies this protection by default. Declaring it explicitly helps when learning, auditing, or avoiding ambiguity in configuration.

Switching to `newSession`:

```java
.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.newSession()))
```

Switching to `migrateSession`:

```java
.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.migrateSession()))
```

**Never use `.none()` to "fix" session, iframe, login-loop, or cookie issues**. Those problems require tracing the session store, cookie Path/Domain/Secure/SameSite, proxies, HTTPS, and the filter chain. Disabling fixation protection trades a UX symptom for a session hijacking risk.

### 4.3. SessionCreationPolicy is related but not synonymous

Familiar values:

- `ALWAYS`: Spring Security creates a session.
- `IF_REQUIRED`: creates a session when needed; usually appropriate for form login.
- `NEVER`: Spring Security does not create a session itself, yet may use an existing session created by another component.
- `STATELESS`: Spring Security neither creates nor uses `HttpSession` to obtain `SecurityContext` per policy semantics; usually pairs with properly designed bearer token / stateless APIs.

**`STATELESS` does not mean "an existing session without ID rotation that still stores authentication in it."** If authentication is genuinely stateless, there is no cookie-backed server-side authenticated session, so fixing `JSESSIONID` to climb into that session does not apply the same way. Still, you must protect bearer tokens, refresh tokens, token-bearing cookies, and login/privilege changes per the corresponding design.

Do not put `STATELESS` on a form-login session demo and expect the browser to stay authenticated on the next call via `JSESSIONID` alone: the two architectures have different contracts.

## 5. Complete Example: Spring Boot 3.x / Java 17+ / Form Login

We build an application with an endpoint that **creates a pre-login session**. Upon successful login, tests must prove:

1. The pre-login session ID changed.
2. The valid `draftColor` attribute is preserved under `changeSessionId`.
3. Post-login requests use the new session and receive the right username.
4. Unauthenticated requests cannot access the private endpoint.

The example uses an in-memory user so it runs out of the box; `{noop}` passwords are **for local learning environments only**. Never use this password storage approach in real products.

### 5.1. Create a Gradle project

Create a project with **Spring Initializr**, Java 17+, Spring Boot 3.x, selecting *Spring Web* and *Spring Security*. The `dependencies` block in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the dependencies block of a Boot project that already has plugins, repositories, and toolchain configured; do not use it as a standalone `build.gradle` file.

### 5.2. Runnable Java file

Create `src/main/java/example/sessionfix/SessionFixationDemoApplication.java`:

```java
package example.sessionfix;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionFixationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionFixationDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form.permitAll())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fix -> fix.changeSessionId()))
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class DemoController {

    @GetMapping("/public/bootstrap")
    public String bootstrap(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        // Public data before login, intended to keep after login.
        session.setAttribute("draftColor", "blue");
        return "anonymous session ready";
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication authentication,
                                  HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        String draft = session == null
            ? "missing" : String.valueOf(session.getAttribute("draftColor"));
        return Map.of(
            "username", authentication.getName(),
            "draftColor", draft);
    }
}
```

**Reading the configuration:**

- `/public/**` and `/login` are accessible before login. `/api/me` requires authentication.
- `formLogin(...)` uses Spring Security's form-login filter, **not a controller authenticating manually**.
- `SessionCreationPolicy.IF_REQUIRED` allows the framework to use a session needed for form login.
- `changeSessionId()` automatically rotates the ID **when a prior session exists and login succeeds**.
- `GET /public/bootstrap` proactively creates an `HttpSession` so the test has a pre-login ID.
- `GET /api/me` does not return the sensitive ID in JSON; it only returns the username and a known public attribute. Real applications should likewise never log or return session tokens to clients.
- CSRF is not disabled in the config. Form login POST must send a valid CSRF token; tests use the `csrf()` helper.

**Note:** There is no Controller mapping for `GET /login` here; Spring Security generates the default login page. The login form submits `POST /login` with default username/password field names. If a real project has a custom login page, authentication provider, SSO, reverse proxy, or multiple filter chains, test the actual paths and session strategy separately.

### 5.3. Running the app and observing in a browser

In a project with Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Manual observation steps in a development environment:

1. Open a fresh browser window to `http://localhost:8080/public/bootstrap`. Verify body `anonymous session ready`.
2. Open Developer Tools → **Application/Storage → Cookies**. With the default embedded Servlet container, you will typically see `JSESSIONID`. **View the value only on your local machine; never capture/send real session IDs to others**. Record locally to compare the old ID and new ID.
3. Visit `/api/me`. Because you are not logged in, the server directs you to the login page via the form-login entry point.
4. Log in with `alice` / `demo123` on the default login page.
5. Inspect the session cookie after authentication: the ID must **differ** from the ID noted in step 2. The browser sends the new cookie on the next request.
6. Visit `http://localhost:8080/api/me`. Expected JSON body contains `"username":"alice"` and `"draftColor":"blue"`.
7. In DevTools → Network, inspect the **response headers** on the login call. Seeing `Set-Cookie` with a new ID confirms the app returned a replacement cookie. Exact headers depend on the container, cookie repository, and proxy.

Never copy a real ID into chats/logs, and never run attack demos against others. For apps using Spring Session, the cookie name may be `SESSION`, and ID history should be compared per the actual repository mechanics.

### 5.4. Integration test confirming the ID changes

Create `src/test/java/example/sessionfix/SessionFixationDemoTest.java`:

```java
package example.sessionfix;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulLoginRotatesIdButKeepsSafeAttribute()
            throws Exception {

        // A real anonymous session from the controller.
        MvcResult bootstrapped = mvc.perform(get("/public/bootstrap"))
            .andExpect(status().isOk())
            .andExpect(content().string("anonymous session ready"))
            .andReturn();

        MockHttpSession preLoginSession =
            (MockHttpSession) bootstrapped.getRequest().getSession(false);

        assertThat(preLoginSession).isNotNull();
        String oldId = preLoginSession.getId();
        assertThat(preLoginSession.getAttribute("draftColor"))
            .isEqualTo("blue");

        // POST /login: valid CSRF, reusing pre-login session.
        MvcResult loggedIn = mvc.perform(
                post("/login")
                    .session(preLoginSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession postLoginSession =
            (MockHttpSession) loggedIn.getRequest().getSession(false);

        assertThat(postLoginSession).isNotNull();
        assertThat(postLoginSession.getId()).isNotEqualTo(oldId);

        // changeSessionId does not drop attributes to keep.
        assertThat(postLoginSession.getAttribute("draftColor"))
            .isEqualTo("blue");

        // Authenticated session is used for the next request.
        mvc.perform(get("/api/me").session(postLoginSession))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.draftColor").value("blue"));
    }

    @Test
    void anonymousCannotReadPersonalEndpoint() throws Exception {
        // Form-login typically returns a redirect to /login.
        mvc.perform(get("/api/me"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Run:

```bash
./gradlew test
```

Windows: `.\gradlew.bat test`. This is an **integration test** running the Spring Boot application, MockMvc with security filters, and the session strategy. It does not merely call a controller method, so it can catch login configurations that bypass ID rotation.

**Test limitations:** `MockHttpSession` simulates Servlet sessions and does not replace end-to-end testing with real cookies, HTTPS, load balancers, or Spring Session stores. In a real Servlet container, also test that the old ID cannot access the authenticated session; you can use browser automation or your app's test environment without turning a learning example into an attack tool.

## 6. Try Switching Strategies to Observe Different Behavior

In the application class from section 5, swap just **one** line of `sessionFixation` and run tests with matching expectations.

### 6.1. `changeSessionId()`

```java
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.changeSessionId()))
```

Expected when a pre-login session exists: the ID changes and the `draftColor` attribute remains. This is the behavior tested in section 5.4.

### 6.2. `migrateSession()`

```java
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.migrateSession()))
```

Expected: the old session is invalidated, a new session is created, and application attributes are transferred. Differs from `changeSessionId` in **session object lifecycle**: `HttpSessionBindingListener` or session-scoped beans may receive remove/add events, causing cleanup or lifecycle callbacks to fire differently than expected. Test shopping carts, CSRF storage, saved requests, session-scoped objects, and listeners before adopting it.

### 6.3. `newSession()`

```java
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.newSession()))
```

Expected: the post-login session ID differs, yet **do not expect `draftColor` to be preserved** from the anonymous session. This is not a bug: it is the exact reason for choosing `newSession`. Internal Spring Security attributes can still be retained per framework policy, so do not interpret it as "a completely stateless session."

### 6.4. `none()`: for analysis only, do not use in live demos

```java
// UNSAFE CONFIGURATION UNLESS PROVEN EQUIVALENT SAFEGUARDS EXIST:
.sessionManagement(session -> session
    .sessionFixation(fix -> fix.none()))
```

When the app has no equivalent ID rotation mechanism, this option can leave a session fixation vulnerability open. Do not deploy that configuration into a running system; use it only to recognize the risk in code reviews.

## 7. Auth Transitions and Custom Login: Places Prone to Missing Safeguards

### 7.1. Default form login vs. manual authentication

Spring Security handles invoking `SessionAuthenticationStrategy` in built-in authentication mechanisms. However, systems may authenticate via:

- A custom REST endpoint receiving credentials and saving `Authentication` into `SecurityContext`.
- A custom `OncePerRequestFilter`.
- An SSO/OAuth2/OIDC callback.
- An API gateway passing an assertion while the app creates a session itself.
- Two-step login or "step-up authentication" flows.

If you implement login manually by constructing `Authentication` and saving `SecurityContext`, **do not assume this rotates the session ID**. In Spring Security 6, custom flows must integrate the appropriate strategy/handler, invoke it at the right moment when authentication succeeds, persist context via `SecurityContextRepository`, and test the ID. Merely configuring `sessionFixation` on `HttpSecurity` while bypassing authentication filters may fail to produce the desired effect.

Illustrative pseudo-flow, **not a standalone program**:

```text
Receive credentials → authentication succeeds (Authentication)
     |
     v
Run session authentication strategy
  - session fixation protection
  - if needed: concurrent session control
     |
     v
Save SecurityContext via SecurityContextRepository
     |
     v
Send response so client uses new session ID
```

Exact ordering depends on authentication framework/version, success handlers, and transaction/response commitment. Never write a custom filter that only calls `SecurityContextHolder.setContext(...)` and assume the session is persisted and rotated.

### 7.2. Re-login, switching users, MFA, and privilege elevation

If a session changes privilege level (e.g., regular user elevating to admin role, completing MFA, switching identity), organizations may require rotating the session identifier at other critical boundaries, not only initial login. The policy must be designed consistently with the authentication mechanism and how the app binds identity. Do not arbitrarily call `changeSessionId()` on every request "just to be safe": doing so causes churn, confuses clients, increases session store load, and does not substitute for proper identity control.

### 7.3. Observable events when rotating the session ID

Spring Security can publish `SessionFixationProtectionEvent` when protection executes. With `changeSessionId`, Servlet's `HttpSessionIdListener` can also be notified. If your system listens to both, avoid double handling, such as auditing "one login = two rotations." Do not log **real session ID values** as long-lived debug info; if log correlation is needed, use an independent event/trace ID and protect log data.

## 8. What Do Cookies Do and Not Do in Fixation Prevention?

| Cookie configuration | Primary effect | Does it replace rotating the session ID at login? |
|---|---|---|
| `HttpOnly` | Restricts JavaScript cookie access, reducing some script-based token theft paths | **No** |
| `Secure` | Browser sends cookie only over HTTPS connections (with relevant platform exceptions/details) | **No** |
| `SameSite=Lax/Strict/None` | Controls cookie sending in cross-site contexts, reducing some CSRF vectors | **No** |
| Strict `Path`/`Domain` | Limits cookie sending/sharing scope, reducing subdomain cookie injection | **No** |
| Cookie prefixes like `__Host-` where applicable | Enforces Secure, `Path=/`, and no Domain per browser rules | **No** |
| Session ID rotation on successful authentication | Severs link between pre-login identifier and privileged session | **Yes — this is the core of fixation defense** |

Use HTTPS throughout the session, never send auth/session cookies over HTTP, never cache or log credentials, and never put session IDs in query strings. When the Servlet container supports URL rewriting with `;jsessionid=...`, consider configuring **COOKIE-only tracking mode** unless there is a legitimate requirement for URL-based session tracking, to reduce accidental ID leakage via URLs, browser history, referrers, and logs.

Example **Spring Boot Servlet** configuration for an HTTPS environment (`application.properties`, relevant properties only, not a full config):

```properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.tracking-modes=cookie
server.servlet.session.timeout=30m
```

Conditions: `secure=true` requires HTTPS or a reverse proxy with proper scheme/trust handling; on local `http://localhost`, browser and proxy behavior may differ. `SameSite=Lax` does not suit every cross-site OIDC/iframe/SSO flow; test against real requirements. When using Spring Session or a custom cookie serializer, container properties may not be the sole configuration point. Do not treat these properties as a complete security configuration.

## 9. CSRF, XSS, Logout, and Timeouts Must Not Be Confused with Session Fixation

### 9.1. CSRF

CSRF exploits the browser **automatically attaching** session cookies to requests so another site triggers unintended actions. Session fixation exploits **an identifier known before authentication**. Even though both involve cookies, their mechanics and controls do not overlap.

- Rotating the session ID at login **does not replace** CSRF tokens.
- CSRF tokens **do not replace** rotating the session ID.
- Form login POSTs and state-changing requests must be handled by CSRF protection according to your threat model.
- When running MockMvc, use `with(csrf())` for POST form login instead of disabling protection to simplify tests.

### 9.2. XSS and post-login session hijacking

An `HttpOnly` cookie reduces the chance of scripts reading the session cookie directly, yet an XSS payload executing inside the valid origin can still issue requests using the user's cookie to perform actions. Rotating the ID at login also does not revoke a session ID leaked **after login**. You still need output encoding, an appropriate CSP, input handling, step-up authentication where needed, and server-side authorization checks.

### 9.3. Logout

Proper logout must render the **current authenticated session invalid**, clear `SecurityContext` per policy, and where appropriate, invalidate the session and return a delete/overwrite cookie to the browser. Having only the client delete the cookie while the server still accepts the old identifier can be insufficient. Spring Security provides logout handlers; exact side effects depend on the session store, cookie setup, and token model.

### 9.4. Expiration and concurrent sessions

Timeouts limit how long a session stays valid during inactivity; concurrent session control limits the number of sessions per user; session fixation protection severs identifiers **before vs. after authentication**. These three features serve different purposes and do not replace one another. If "log out all devices" is required, implement a mechanism to revoke all corresponding sessions/tokens across the system.

### 9.5. No pre-login session exists

Some browsers hitting `/login` for the first time will get a session created for a CSRF token, saved request, or another feature; other flows have no session until login succeeds. If there is no pre-login ID, the system cannot "prove A differs from B" by comparing two IDs. Fixation tests should **proactively create an anonymous session** like `/public/bootstrap`, then verify the post-authentication result. Skipping that precondition can cause a test to pass or fail due to session initialization details without actually testing rotation.

## 10. Production: Proxies, Session Stores, and Multiple Instances

Safe ID rotation requires looking at **the entire session lifecycle**, not a single config line.

### 10.1. Load balancers and distributed deployments

In multi-node deployments, sessions may live in per-node memory, sticky sessions, Redis, or Spring Session. After the ID changes, the browser uses the new cookie; nodes, load balancers, and the session repository must recognize the new mapping. If the old ID still works on another node due to slow replication or faulty invalidation, protection effectiveness suffers. Test behavior at the real session store layer rather than concluding from unit tests alone.

### 10.2. Cookies with the same name but different Path/Domain

Browsers can store multiple cookies with the same name under different `Path`/`Domain` scopes; proxies or frontends may send unexpected cookies. The result is login loops, "lost" sessions, or sessions pinned to the wrong scope. Audit `Set-Cookie` on login responses and `Cookie` on subsequent requests in a test environment while protecting sensitive data. Never "fix" it by disabling the fixation strategy.

### 10.3. Reverse proxies and HTTPS termination

If TLS terminates at a proxy, the backend app must be configured to trust forwarded headers/scheme properly so it recognizes HTTPS requests and emits secure cookies. Never trust `X-Forwarded-*` headers from Internet clients bypassing authorized proxies. Test behavior in the actual deployment topology, especially login redirects, `Secure` cookies, and SameSite.

### 10.4. Session attributes and lifecycle listeners

With `migrateSession`, invalidating the old session and copying attributes to a new session can trigger `HttpSessionBindingListener`, session-scoped beans, or disposable lifecycle callbacks unexpectedly. `changeSessionId` is usually simpler when attributes do not need clearing; `newSession` is cleaner when isolating old state. Strategy choices must be tested with real shopping carts, drafts, and session objects.

### 10.5. Never leak tokens through observability

Avoid logging raw `JSESSIONID`, `SESSION`, `Cookie`, or `Set-Cookie` values in logs, traces, analytics, error reports, and monitoring dashboards; if tools automatically capture headers, configure redaction. A session ID is a live credential while the session is active.

## 11. Do Not Confuse Servlet `HttpSession` with WebFlux `WebSession`

The explanations and runnable code above target the **Servlet stack** (`HttpSecurity`, `SecurityFilterChain`, `HttpSession`, Servlet cookies). In **WebFlux/reactive**, the session concept is `WebSession` and security integration uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and reactive contexts; do not copy `HttpServletRequest.changeSessionId()` straight into WebFlux.

Things to verify when deploying reactive apps:

1. Is the application actually running **WebFlux** or Spring MVC? Simply having a controller return `Mono` does not guarantee the app uses the reactive web stack.
2. Session store mechanics, ID creation/rotation, and login authentication success in the current framework version.
3. Cookie scope/tracking, session invalidation, reverse proxies, and `WebSession` lifecycle.
4. Integration tests verifying a pre-login anonymous session cannot become authenticated under the **same known ID** after login.

If an API is **completely stateless** and stores no authentication in server-side sessions, focus on bearer/refresh token lifecycles, token rotation/revocation, and token-bearing cookies (if any). Do not assume Servlet `HttpSession` strategies secure tokens.

**Maintenance note:** Spring Framework/WebFlux releases may include security updates related to session management. Monitor Spring security advisories and upgrade to appropriate patched versions; do not treat this fundamentals lesson as a substitute for production CVE/version checks.

## 12. Test Matrix Recommended When Reviewing Login Features

| Scenario | Setup | Expected |
|---|---|---|
| Anonymous user has pre-login session → login succeeds | Record ID beforehand, send valid POST login | Post-login ID differs from pre-login ID |
| Public attribute exists before login, using `changeSessionId` | Set `draftColor=blue` | Attribute remains after login |
| Using `newSession` | Set same attribute before login | New session ID, old app data may be gone |
| Wrong password | Submit failed login | No authenticated identity created; not treated as privilege elevation |
| Old ID presented after login | Access test environment with locally recorded old ID | Cannot fetch protected resource as newly logged-in user |
| New request with post-login ID | Use new cookie/session | Resolves to the authenticated identity |
| Expired session | Expire/timeout | Cannot access resource using expired cookie alone |
| Logout | Log out per contract | Authenticated session is no longer accessible |
| Multiple nodes/caches | Log in on one node, request hits another | Consistent invalidation/rotation in the session store |
| Reverse proxy | HTTPS frontend, backend app | Secure `Set-Cookie`, new cookie works; no login loop |
| Login with CSRF protection | POST with valid/invalid token | Auth and CSRF work together properly; never disable CSRF to fix tests |
| Custom authentication flow | Auth without default login filter | Strategy integrated and ID verified to actually rotate |
| Multiple sessions/cookies with same name | Differing Path/Domain | No wrong cookie sent causing bypass or session mix-ups |

The highest-value tests are **negative security tests**: capture the pre-login anonymous ID, then after login verify **the old ID cannot access the newly logged-in user's privileges**. A test saying "login succeeds and API returns 200" does not prove fixation protection.

## 13. Common Misconceptions and How to Fix Them

| Misconception | Why it is wrong | Proper practice |
|---|---|---|
| "We already use HTTPS so rotating the session ID is unnecessary." | HTTPS protects transport; it does not eliminate a pre-fixed ID. | Keep fixation protection + TLS. |
| "An unpredictable session ID prevents fixation." | The attacker may already know a valid ID without guessing. | Rotate upon privilege elevation. |
| "Adding HttpOnly prevents fixation." | HttpOnly does not invalidate an ID the attacker knew beforehand. | Cookie hardening + rotation. |
| "Swapping the cookie on the client is enough." | The server must revoke usability of the old ID. | Use a server-side session strategy. |
| "Deleting the entire session is the only safe option." | State can be kept safely with a rotated ID. | `changeSessionId`/`migrateSession` when needed. |
| "`changeSessionId` wipes the whole shopping cart." | It does not create a new session object and usually preserves attributes. | Test safe state retention after login. |
| "`none()` fixed login errors so we should use it." | It can reopen fixation vulnerabilities. | Diagnose cookie/proxy/session store root causes. |
| "`SessionManagementFilter` handles all custom logins." | Spring Security 6 no longer installs this filter by default like before. | Integrate `SessionAuthenticationStrategy` in custom auth flows. |
| "Login returning 200 proves fixation protection." | It does not test the old ID. | Integration test rotation + old-ID rejection. |
| "A CSRF token is enough." | CSRF and fixation have different threat models. | Keep both. |
| "Stateless JWT works identically to `HttpSession`." | Authentication lifecycles differ. | Design tokens/sessions per real mechanics. |
| "Rotating ID at login means logout doesn't need invalidation." | Login rotation does not replace logout or session expiration. | Revoke sessions per contract. |

## 14. Implementation Checklist

- [ ] Know whether the app uses Servlet `HttpSession` or reactive `WebSession`, `JSESSIONID` or a repository-configured cookie.
- [ ] Identify boundaries for login, account switching, MFA/step-up, or privilege elevation.
- [ ] Enforce a session fixation protection strategy on **successful authentication**; never disable it without a verified equivalent safeguard.
- [ ] On Servlet 3.1+, consider `changeSessionId()`; understand when to use `migrateSession()` and `newSession()`.
- [ ] Enable proper method/HTTP authorization; session rotation alone does not enforce endpoint or object permissions.
- [ ] Custom authentication integrates the proper strategy and `SecurityContext` persistence, not just setting the holder context.
- [ ] Tests start with an anonymous session that has an ID; verify the ID changes after login and safe state is kept or cleared intentionally.
- [ ] Test that the old ID cannot be used to access authenticated resources in a real integration environment.
- [ ] Form login, CSRF, saved requests, session-scoped objects, and listeners behave properly after rotation.
- [ ] Cookies have `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, and tracking mode matching requirements behind a properly schemed proxy.
- [ ] Logout, timeouts, revocation, concurrent sessions, multi-node setups, and session stores operate properly.
- [ ] Never expose real session IDs in URLs, logs, screenshots, or error bodies.
- [ ] Monitor security advisories and verify actual Spring Security, Servlet container, and Spring Session/WebFlux versions.

## 15. Reasoning Exercises and Answers

**Question 1.** An attacker knows the anonymous session ID `ABC`. After the victim logs in, the server still accepts `ABC` to access the victim's account. What risk is this?

**Answer:** Session fixation. The pre-authentication session identifier was "elevated" without changing, allowing someone who already knew the ID to keep using the post-login session.

**Question 2.** Why is `changeSessionId` usually a better fit than forcing users to lose their shopping cart on login?

**Answer:** It changes the session access "key" while preserving valid attributes (such as `cartId`), both preventing reuse of the old identifier and keeping needed state.

**Question 3.** Is the ID guaranteed to visibly change if no session existed before login?

**Answer:** There is no old ID to compare against. To test fixation protection, create an anonymous session before login and then run the authentication flow using that exact session.

**Question 4.** Why is seeing `HttpOnly` on `JSESSIONID` not enough?

**Answer:** `HttpOnly` primarily restricts JavaScript from reading the cookie; it does not invalidate an identifier the attacker may already have known before the victim logged in.

**Question 5.** In a Spring Security 6 app with a custom login controller that manually builds `Authentication` and saves context, is ID rotation guaranteed by default?

**Answer:** You cannot assume so. Check whether the controller/filter integrates `SessionAuthenticationStrategy` and the appropriate session repository/persistence, then test old/new IDs with real requests.

**Question 6.** Login succeeds and the ID changes, yet afterward the user loses the `cartId` attribute. Is this always a bug?

**Answer:** No. If `newSession` was chosen to isolate old state, dropping application attributes is intentional. If the product needs to preserve the cart, consider `changeSessionId`, `migrateSession`, or a safely verified state-transfer mechanism.

## 16. Official References

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation, the three recommended strategies, Spring Security 6 behavior with custom authentication and session persistence.
- [Spring Security — FAQ: Why does my session ID change when I authenticate?](https://docs.spring.io/spring-security/reference/servlet/appendix/faq.html): explains why the ID rotates by default on login.
- [Spring Security — SessionFixationConfigurer API](https://docs.spring.io/spring-security/site/docs/6.1.7/api/org/springframework/security/config/annotation/web/configurers/SessionManagementConfigurer.SessionFixationConfigurer.html): `changeSessionId`, `newSession`, `migrateSession`, `none`.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): form login authentication and filter flow.
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): testing with MockMvc and Spring Security.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): explains protecting state-changing requests.
- [Spring Framework — Web Session (WebFlux)](https://docs.spring.io/spring-framework/reference/web/webflux-websession.html): distinguishing `WebSession` and Servlet `HttpSession`.

**Remember:** The solution does not lie in "just creating a new session," but in ensuring **a session identifier known prior to authentication can never represent an authenticated session**. Rotate the ID at authentication boundaries, test with both old and new sessions, and protect the entire cookie/session lifecycle in real deployment environments.
