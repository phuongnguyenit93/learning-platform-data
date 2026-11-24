# Lifetime, Session Expiration, and Logout Operations

## 1. Objectives and Learning Context

This lesson belongs to **Sessions and cookies** in **Spring Security - fundamentals**. Upon completion, you will be able to:

1. Explain the lifecycle of a login session backed by `HttpSession`: creation, authentication, reuse, activity renewal, expiration, and invalidation.
2. Distinguish **idle timeout**, **absolute session lifetime**, **browser cookie lifetime**, **remember-me lifetime**, access/refresh token expirations, and permission revocation timing.
3. Configure inactivity timeout for Servlet sessions via `server.servlet.session.timeout`; understand the limits of this mechanism and avoid confusing it with a fixed lifetime counted from login.
4. Recognize expired sessions or invalid session IDs; understand `invalidSessionUrl`, how subsequent requests are handled, and how it differs from sessions marked expired by concurrent login control.
5. Use Spring Security's standard logout flow: `LogoutFilter`, `POST /logout`, CSRF tokens, invalidating `HttpSession`, clearing `SecurityContext`, deleting cookies, and redirecting.
6. Run a Java 17+ Spring Boot 3.5.12 application, observe sessions/cookies in the browser, test login–logout with `MockMvc`, and explain what those tests cannot prove by themselves.
7. Identify practical risks: session fixation, session hijacking, incorrect auto-logout, UI-only "logout," sessions across multiple devices, SSO, and still-valid tokens.

**Scope:** **Spring MVC/Servlet** applications using `HttpSecurity`, `HttpSession`, and session cookies. WebFlux uses `WebSession`/reactive security contexts and has corresponding configuration APIs, though Servlet classes cannot be copied verbatim into WebFlux. This lesson focuses on **server-backed authentication sessions**, without forcing every use case into JWT/stateless.

## 2. How Does a Login Session Live?

A Servlet authentication session typically goes through the following flow:

```text
User opens a page
    │
    ▼
GET /account while unauthenticated
    │
    └─ Spring Security requires authentication → redirect to /login
                                          │
                                          ▼
                              POST /login + username/password
                              + valid CSRF token
                                          │
                                      authentication succeeds
                                          │
                                          ▼
                              Authentication in SecurityContext
                                          │
                              save context for subsequent requests
                              using appropriate HttpSession
                                          │
                                          ▼
                              Browser receives JSESSIONID cookie
                                          │
               ┌──────────────────────────┴────────────────────────┐
               │                                                   │
        GET /account                                          No activity
        Cookie: JSESSIONID=...                              within timeout
               │                                                   │
               ▼                                                   ▼
        server finds session                              session expires/
        and identifies user                               evicted from store
               │                                                   │
               ▼                                                   ▼
             200 OK                                   subsequent requests cannot
                                                      use the old session
               │
               └── POST /logout + valid CSRF token
                           │
                           ▼
                  invalidate current session
                  clear security context / CSRF token
                  handle cookie
                           │
                           ▼
                  next GET /account
                  requires logging in again
```

**Core idea:** the cookie normally holds the **session ID**, while **login state** (typically comprising `SecurityContext` and `Authentication`) resides on the server/session store. Both *time-based expiration* and *explicit logout* terminate the ability to reuse the session, yet their **causes, mechanics, audit trails, and UX** differ.

**Do not conflate components automatically:** Spring Security authenticates requests, the Servlet container manages `HttpSession`/session ID lifecycles, and the browser decides whether to send cookies according to their scope and attributes. Spring Session can replace session storage with a distributed store. Any real configuration requires knowing which component governs expiration.

## 3. Distinguishing Expiration Types: There Is No Single "Expiry"

| Concept | When does the clock start? | When does it expire? | Typical enforcement point |
| --- | --- | --- | --- |
| **Idle timeout / max inactive interval** | From the last time the session was accessed per the container | Unused for the configured duration | Servlet container / session store |
| **Absolute session lifetime** | Creation time or re-authentication time, per policy | After a maximum duration regardless of ongoing activity | Additional policy in app/IdP |
| **Cookie Max-Age/Expires** | When the browser receives the cookie | Browser should stop sending the cookie after the deadline | Browser |
| **Session cookie (no fixed Max-Age)** | When the browser receives the cookie | Per browser session lifecycle; may be affected by session restore | Browser |
| **Remember-me cookie/token** | When "remember me" is issued | Per remember-me token lifetime and state | Browser + Spring Security / token store |
| **Access token expiry (`exp`)** | Per absolute timestamp inside the token | Resource server rejects token after deadline (per clock skew policy) | OAuth2 Resource Server / IdP |
| **Refresh token expiry/revocation** | Per refresh token policy | Can no longer exchange that token for new access tokens | Authorization Server / IdP |
| **Concurrent-session expiration** | When session count policy marks a session expired | When Spring Security detects/evicts the old session | Session registry and Spring Security |

### Illustrative idle timeout example

Suppose the server configures a **10-minute idle timeout**:

```text
09:00  Log in
09:06  GET /account uses valid session → last accessed timestamp updated
09:14  GET /account uses valid session → still under 10 minutes since last use
09:25  GET /account after >10 minutes of session inactivity
       → old session may have been evicted by container/store
       → request no longer has the previous logged-in identity
```

This is a **behavioral illustration**, not a guarantee at exact second 600. The container/store may reap the session on re-access or via a background cleanup sweep; in-flight requests, timeout granularity, and environment affect the exact observed moment. Expiration is normally evaluated from the last time the session was accessed, and not every request extends it if that request does not touch the session.

**Important question:** a browser running AJAX polling every 30 seconds can unintentionally keep a session alive longer than desired if those polling requests actually access the session. If a requirement says "force re-login after 8 hours regardless of activity," **idle timeout will not satisfy it**; you need an absolute limit enforced at the server/identity layer.

### Idle timeout ≠ absolute lifetime

- **Idle timeout:** "If the user does not use the session for 10 minutes, the session expires."
- **Absolute lifetime:** "A session must not live longer than 8 hours from creation, even if the user interacts continuously."
- **Reauthentication age:** "Before a sensitive operation, the most recent authentication must be within 15 minutes." This is a separate *fresh login* condition that need not invalidate the whole session.

Spring Boot configures the Servlet session inactivity interval; it **does not automatically provide a comprehensive absolute lifetime policy** simply because `server.servlet.session.timeout` is set.

## 4. What Do HttpSession, JSESSIONID, and SecurityContext Actually Hold?

A typical stateful Spring Security Servlet app has the following relationship:

```text
Browser                              Server
┌────────────────────┐              ┌─────────────────────────────────┐
│ Cookie             │              │ HttpSession store               │
│ JSESSIONID=abc...   │ ─── ID ────>│ session[abc...]                 │
│                    │              │   ├─ SecurityContext            │
└────────────────────┘              │   │   └─ Authentication           │
                                    │   │       ├─ principal            │
                                    │   │       └─ authorities          │
                                    │   └─ other session attributes     │
                                    └─────────────────────────────────┘
```

This is the **typical** behavior for session login; not every application configures `SecurityContextRepository` the same way. In Spring Security 6, context-saving/reading filters must be understood according to the exact version; with standard form login, Spring Security saves `Authentication` for restoration on later requests.

**A session cookie is not a "copy of the session."** The browser carries an opaque identifier token (session ID) for the server to look up state. If someone else captures a valid ID, they can try to impersonate the session; therefore, protect the ID cookie and transport channel.

**Never return the session ID via an API just for debugging.** The example below prints only `maxInactiveInterval` and session presence, **never printing the ID or SecurityContext**.

## 5. Configuring Lifetime in Spring Boot

For a Spring Boot application using an embedded Servlet container such as Tomcat:

**`src/main/resources/application.properties`**

```properties
# Idle timeout of Servlet HttpSession in the demo environment
server.servlet.session.timeout=10m

# Cookie settings suited for the demo; production requires HTTPS and Secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

- `10m` means **10 minutes of inactivity**; Spring Boot passes this setting to the servlet container/session manager.
- `HttpSession.getMaxInactiveInterval()` returns the inactivity limit in **seconds** as seen by the session.
- `server.servlet.session.timeout` is the **server-side** session duration, not the cookie's age.
- `server.servlet.session.cookie.max-age` (if set) specifies how long **the browser** retains the cookie; it does not guarantee the corresponding session still exists on the server.
- `server.servlet.session.cookie.secure=true` should be enabled in HTTPS production environments; do not blindly enable it when running `http://localhost:8080` if you need the browser to send cookies during local exercises.
- With Spring Session (Redis/JDBC...), the dedicated repository can manage TTL/session timeout; check `spring.session.timeout` or the repository's policy rather than assuming every session store behaves like embedded Tomcat.

**Session expiration does not mean an automatic response is pushed to the browser.** The server cannot push an HTTP redirect to an idle tab merely because the session just expired. Usually **the next request** discovers it and requires logging in again. If the UI needs a countdown timer or pre-expiration warning, that is an additional UX feature and must stay synchronized with **server-side** decisions, not rely solely on a JavaScript timer.

### Changing timeout per session (illustrative fragment)

```java
HttpSession session = request.getSession(false);
if (session != null) {
    session.setMaxInactiveInterval(600); // 600 seconds = 10 minutes
}
```

This fragment requires `HttpServletRequest request` and Servlet import `jakarta.servlet.http.HttpSession`; it is not a standalone program. `setMaxInactiveInterval` adjusts that session's **idle timeout**; it does not create an absolute TTL. Never set arbitrary timers from user-supplied data when policy must be enforced by the server.

## 6. When a Session Expires, What Happens on the Next Request?

Inactivity expiration scenario:

1. The browser may **still retain** the old `JSESSIONID` cookie if it has not been deleted or expired on the browser side.
2. The Servlet container receives the session ID yet finds no valid `HttpSession`.
3. Spring Security cannot restore the previous session's `Authentication`.
4. If the request is `GET /account` protected by form login, the app typically redirects the user to `/login` (302) or handles it via the configured `AuthenticationEntryPoint`.
5. After logging in again, the server uses a new valid session/ID; it must never "trust" the old cookie.

**Distinction:** "expired session" (the old session is no longer active) differs from "invalid session ID" (stale cookie, forged cookie, wiped session store, logout, non-existent session ID). On an incoming request, these two causes can sometimes look identical. Do not build UX that always asserts "you timed out" when the cause might be an invalid cookie or the user having logged out.

### invalidSessionUrl

Spring Security Servlet supports handling requests that send an invalid session ID:

```java
http.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid")
);
```

This is an **optional fragment**, not included in the runnable demo in section 9. It requires a public route/endpoint `/session-invalid` and must avoid redirect loops; an un-deleted old cookie can cause requests to the handler path itself to be treated as invalid. `invalidSessionUrl` suits some Servlet flows, yet should be tested with your actual session storage and Spring Security version.

**Do not confuse `invalidSessionUrl` with `expiredUrl` inside `maximumSessions(...)`:** `expiredUrl`/`SessionInformationExpiredStrategy` handles sessions marked invalid by **concurrent session control**, typically due to exceeding allowed session counts. A session expiring via **idle timeout** is not the same event as a session "expired" by Spring Security's concurrency policy.

For REST/APIs, HTML redirects are usually not the right UX; consider returning 401 with a standard response asking the client to re-authenticate. For browser form login, redirecting to the login page is usually clearer.

### When in-progress form input needs to be preserved

If a session expires while a user is filling out a form, never silently submit a POST on the user's behalf once the session is gone. A well-designed app can:

- Warn before expiration if security design permits.
- Save non-sensitive drafts in an appropriate, controlled place.
- Require re-login before performing the operation.
- Ensure unsubmitted data is not leaked in URLs/logs.
- Handle stale CSRF tokens after re-authentication, never reusing a token that has been invalidated or belongs to a prior session.

## 7. Proper Logout in Spring Security

**Explicit logout** is a security action: terminating acceptance of the current session and clearing associated state. **Hiding a button** or flipping frontend state to `loggedOut=true` is not enough.

With Spring Security Servlet and default configuration with CSRF enabled:

- `GET /logout` may display a logout **confirmation page**.
- **`POST /logout` with a valid CSRF token** triggers the logout workflow.
- `LogoutFilter` processes logout inside the security filter chain, before most HTTP authorization checks; you normally do not need to write your own logout controller.
- Default `LogoutHandler` implementations perform necessary actions such as **invalidating `HttpSession`**, clearing the relevant `SecurityContextHolder`/`SecurityContextRepository`, cleaning up saved CSRF tokens and remember-me authentication if configured; the logout success handler sends the user to `/login?logout` when using default form login.
- If `deleteCookies("JSESSIONID")` is configured, the server attempts to send a cookie deletion directive; this may require matching cookie Path/Domain depending on the servlet container and proxies. **The primary security effect is server-side session invalidation**, regardless of whether the cookie deletion succeeds client-side.

Visualization:

```text
POST /logout + cookie + CSRF token
              │
              ▼
       Security LogoutFilter
              │
        LogoutHandlers
          ├─ SecurityContextLogoutHandler
          │    ├─ invalidate current HttpSession
          │    ├─ clear Authentication/SecurityContext
          │    └─ clear stored SecurityContext as configured
          ├─ CsrfLogoutHandler (cleanup CSRF token)
          └─ remember-me handler (if remember-me is used)
              │
              ▼
          LogoutSuccessHandler
              │
              └─ 302 Location: /login?logout
```

A request to `GET /logout` **should not be treated as an actual logout** when CSRF is enabled. If CSRF is disabled, GET/logout behavior can differ; never disable CSRF solely to allow logging out via a GET link.

### CSRF on logout: why POST matters

Browsers can automatically attach authentication cookies to cross-site requests depending on `SameSite` and context. If logout happens over GET or an unguarded POST without CSRF checks, another site could force users to log out or trigger unwanted side effects (*logout CSRF*).

Therefore, with browser session cookies, use **POST /logout + CSRF token** and retain Spring Security's default mechanism. With default form login, Spring Security provides the token-generating form automatically. With a custom UI, send the token per your `CsrfTokenRepository`/request handler configuration.

### What needs to be cleared on logout?

| Component | Appropriate action |
| --- | --- |
| Current session on server | Invalidate/delete so the ID cannot be reused |
| `SecurityContext` | Clear in the current request and appropriate repository |
| Session-bound CSRF token | Invalidate/clear so stale state is not reused |
| Browser session cookie | Send deletion directive where appropriate; match Path/Domain |
| Remember-me cookie/token | Revoke/clear per enabled remember-me mechanism |
| Self-contained JWT access token | Web session logout **does not automatically revoke** issued JWTs |
| Refresh token / IdP SSO session | Needs separate revocation/federated logout flow if present |
| Other tabs in the same browser profile | Pick up the change on their next request; UI should handle consistently |
| Sessions on other devices | Not automatically logged out by invalidating only the current session |

**Current-session logout ≠ all-device logout.** If "Log out all devices" is required, you need centralized session management or appropriate token revocation, not merely calling `request.getSession().invalidate()` on one request.

## 8. Cookie and Session Security in Production Deployments

| Risk | Mitigation |
| --- | --- |
| Session ID intercepted in transit | End-to-end HTTPS, `Secure` cookies, prevent downgrades |
| JavaScript reads session cookie via XSS | `HttpOnly` reduces JS cookie theft; still must prevent XSS |
| Forged request from another site | CSRF token, `SameSite`, Origin/Referer checks where appropriate |
| Session fixation | Rotate session ID after login/privilege change; Spring Security provides fixation protection |
| Session valid for too long | Idle timeout, policy-driven absolute lifetime, step-up auth |
| Cookie exists yet server session is gone | UX prompts re-login; never restore privileges from an orphaned cookie |
| Forgetting to clear context in custom logout | Use Spring Security `logout` DSL instead of clearing variables manually |
| ID/token leakage in logs | Never log cookies, session IDs, `Authorization` headers, or JWTs |
| Session lives on a single instance | Shared session store (Spring Session Redis/JDBC) or explicit infrastructure support |
| Permissions revoked while session holds stale authorities | Design session refresh/revalidation/expiration on role changes |

**Cookie Path/Domain note:** if the app runs behind a reverse proxy or on a sub-path, cookie deletion must use the exact matching scope for the browser to honor it. `deleteCookies("JSESSIONID")` is not guaranteed to solve every proxy/container quirk; test in real browsers and avoid reporting "logout broken" solely because a cookie remains visible when the server session is already invalidated.

**Session fixation:** if an attacker pre-fixes a session ID before login and it is not rotated, post-authentication session hijacking can occur. Spring Security configures session fixation protection in the authentication flow; on Servlet 3.1+, rotating the ID does not necessarily discard all session attributes. Verify behavior against application requirements if you customize the authentication flow.

## 9. Runnable Example: Form Login, Idle Timeout, and Logout with CSRF

The following project uses **Java 17+, Spring Boot 3.5.12, Spring Security 6.x, Gradle 8.4+**. It has one `SecurityFilterChain` covering the application, HTTP form login, a 10-minute Servlet session inactivity timeout, one demo account, and standard logout via POST.

The demo includes three endpoints:

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET /public` | Public | Demonstrates an unauthenticated route |
| `GET /account` | Authenticated | Restores user from session |
| `GET /account/session-info` | Authenticated | Views max inactive interval without exposing session ID |

`GET /login` and `GET /logout` use Spring Security's default UI; `POST /login` and `POST /logout` are handled by Spring Security filters. Do not write duplicate controllers for these paths.

### 9.1. Structure

```text
session-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sessionlifecycle/
    │   │   ├── SessionLifecycleApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── AccountController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/sessionlifecycle/
            └── SessionLifecycleTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'session-lifecycle-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

Spring Boot here requires dependencies outside the JDK, so `gradle test`/`gradle bootRun` is the way to run the full project; bare `javac`/`java` without the Spring classpath will not compile. Ensure a compatible Gradle 8.4+, or use a Gradle Wrapper configured with the appropriate version.

### 9.2. Timeout/cookie configuration

**`src/main/resources/application.properties`**

```properties
server.servlet.session.timeout=10m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

The demo configuration runs over localhost HTTP for easy testing. **Do not copy plain HTTP setup to production**: real deployments must use HTTPS and configure `Secure` on session cookies. Ten minutes here is an idle timeout, not cookie `Max-Age` or a fixed 10 minutes from login.

### 9.3. Main application

**`src/main/java/com/example/sessionlifecycle/SessionLifecycleApplication.java`**

```java
package com.example.sessionlifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
```

### 9.4. SecurityFilterChain: standard form login + logout

**`src/main/java/com/example/sessionlifecycle/SecurityConfiguration.java`**

```java
package com.example.sessionlifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/account", "/account/session-info")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }
}
```

**Detailed explanation:**

1. `/public` goes through HTTP authorization `permitAll()`; this does not mean bypassing all security filters.
2. `/account` and `/account/session-info` require valid `Authentication`. Anonymous users hitting these routes are redirected to the default login page.
3. `anyRequest().denyAll()` blocks unlisted endpoints. `formLogin(form -> form.permitAll())` grants access to the standard login UI/mechanism.
4. The `logout` DSL uses `LogoutFilter` and standard handlers. `invalidateHttpSession(true)` destroys the current session, and `clearAuthentication(true)` clears related authentication; Spring Security also handles security context/CSRF storage per logout mechanics. `deleteCookies("JSESSIONID")` attempts to clear the browser cookie in the matching scope.
5. There is no `csrf().disable()`. With this setup, actual logout must use **POST with a valid CSRF token**. Spring Security generates a confirmation page on `GET /logout` and provides the default login form UI.
6. Session timeout is **not inside `HttpSecurity` in this code** because it is set via `server.servlet.session.timeout=10m` for the Servlet container. `SessionCreationPolicy` does not need explicit override for form login to use sessions by default.
7. `{noop}` plaintext password storage is **only for local machine exercises**. Never deploy this account to the Internet/production; use a strong password encoder, secure storage, and secure transport.

**Note on login/logout output:** after login, the browser may redirect to the previously requested URL or the default success URL. After logout, the configuration explicitly redirects to `/login?logout`. Never assume every successful `POST /login` returns a 200 text body; it is normally a redirect.

### 9.5. Controller reading only user and timeout without exposing session ID

**`src/main/java/com/example/sessionlifecycle/AccountController.java`**

```java
package com.example.sessionlifecycle;

import java.security.Principal;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/account/session-info")
    public String sessionInfo(Principal principal, HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "user=" + principal.getName() + ";session=absent";
        }

        return "user=" + principal.getName()
            + ";idleTimeoutSeconds=" + session.getMaxInactiveInterval();
    }
}
```

`request.getSession(false)` **does not create** a new session just to display info; if none exists, it returns `null`. In standard stateful form login, an authenticated request will have a session, yet the code handles `null` anyway to avoid `NullPointerException` if authentication configuration changes.

The endpoint returns only the username and configured inactivity seconds; it does not emit `session.getId()` or cookie values. **The number of seconds is the session's idle timeout**, not "time remaining" until expiration.

### 9.6. Running the application and interacting via browser

Requires **JDK 17+** and **Gradle 8.4+**. In the `session-lifecycle-demo` directory:

```bash
gradle test
gradle bootRun
```

If you have the matching Gradle Wrapper version, use `./gradlew test` and `./gradlew bootRun` (Linux/macOS), or `gradlew.bat test` and `gradlew.bat bootRun` (Windows).

**Test sequence:**

1. Open `http://localhost:8080/public` → body **`public`**.
2. Open `http://localhost:8080/account` while unauthenticated → browser normally redirects to `/login`.
3. Enter username `alice` and password `alice123` in the default form. Spring Security creates/remembers the authenticated session and returns a redirect response.
4. Open `http://localhost:8080/account` → body **`hello alice`**.
5. Open `http://localhost:8080/account/session-info` → body like **`user=alice;idleTimeoutSeconds=600`** once the embedded container applies the 10-minute setting as expected. The number may reflect actual container config if overridden.
6. Open Developer Tools → Application/Storage → Cookies: you may see a session cookie named `JSESSIONID` (depending on container, context path, and cookie settings); do not copy the cookie value into logs or reports.
7. Try opening `http://localhost:8080/logout` in the browser: Spring Security renders a logout confirmation page when CSRF is enabled. Confirming via the form submits **POST /logout** with a valid token.
8. After logging out, reopen `/account` → you must log in again because the current session was invalidated.

**Verifying the 10-minute timeout:** log in, then **send no requests touching the session** for longer than 10 minutes (leave some margin for container/cleanup), then revisit `/account`. You should need to log in again. If the UI/browser polls or another tab keeps calling the server with the session, that does not test idle timeout because the session may be getting renewed.

**Do not wait 10 minutes inside unit tests:** actual session reaping is governed by the container/store; tests checking logout correctness can use `MockMvc`, whereas real expiry timing should use integration/environment tests with an appropriate clock/idle interval and real session store.

### 9.7. Quick verification with curl

`curl` does not automatically complete form login with a CSRF token, so use only simple verifiable requests:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/account

# Missing CSRF token: not a valid login/logout operation
curl -i -X POST http://localhost:8080/logout
```

Expected output:

- `GET /public` → **200**, body `public`.
- `GET /account` when anonymous → **302**, typically with `Location: /login`.
- `POST /logout` without a CSRF token → typically **403** when default CSRF is enabled. This case **does not prove logout happened**.

To automate form login with a real HTTP client, fetch the CSRF token/cookie from the login page, attach the matching cookie jar, and submit the token per the repository/handler config. Never copy a CSRF token from an old session to a new session or disable CSRF just to make a demo work.

### 9.8. MockMvc test suite: session reuse and real logout

**`src/test/java/com/example/sessionlifecycle/SessionLifecycleTests.java`**

```java
package com.example.sessionlifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLifecycleTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginAsAlice() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void publicIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void successfulLoginCreatesReusableSession() throws Exception {
        MockHttpSession session = loginAsAlice();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndSessionRemainsUsable()
            throws Exception {
        MockHttpSession session = loginAsAlice();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));
    }

    @Test
    void validLogoutInvalidatesCurrentSession() throws Exception {
        MockHttpSession session = loginAsAlice();

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutOfOneBrowserSessionDoesNotLogoutAnother()
            throws Exception {
        MockHttpSession sessionOne = loginAsAlice();
        MockHttpSession sessionTwo = loginAsAlice();

        mvc.perform(post("/logout").session(sessionOne).with(csrf()))
            .andExpect(status().is3xxRedirection());

        assertTrue(sessionOne.isInvalid());

        mvc.perform(get("/account").session(sessionTwo))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));
    }
}
```

**Why is this test suite well suited to the lesson?**

- `formLogin()` from `spring-security-test` builds a POST login with a valid CSRF token; thus the tests **do not disable CSRF**.
- `successfulLoginCreatesReusableSession` proves the post-login session can be reused in another call.
- `logoutWithoutCsrfIsRejectedAndSessionRemainsUsable` proves POST logout without CSRF is blocked and does **not** log the user out.
- `validLogoutInvalidatesCurrentSession` verifies the logout redirect and that the `MockHttpSession` object is invalidated. Do not re-attach an already invalidated `MockHttpSession` to a new request: the mock Servlet API can throw an exception; a real browser sends the old cookie and the container decides that ID is no longer valid.
- `logoutOfOneBrowserSessionDoesNotLogoutAnother` shows that default logout targets only the current session; another session of the same account is not automatically destroyed.

**Test limitations:** `MockMvc`/`MockHttpSession` does not fully simulate real expired-session reaper clocks, real cookie stores, TLS, browser SameSite rules, proxies, or Redis session sharing. This suite **does not prove sessions are reaped at exact wall-clock second 600**; real integration tests against the actual container/session store are needed to verify timeout behavior.

## 10. Stepping Up: Absolute Session Control and Sensitive Operations

Some applications require stricter policies than idle timeout:

- **Absolute lifetime:** sessions must expire 8 hours after login. Store the authentication timestamp (trusted server time), evaluate the limit at appropriate entry points, and invalidate the session/require re-login once past the threshold. If using Redis, you may need an absolute TTL or an explicit guard; do not rely only on idle TTL.
- **Step-up reauthentication:** require re-entering password/MFA when transferring money or changing email, even while the session remains active; record the latest authentication timestamp from a trusted source.
- **Concurrent session limit:** cap sessions per principal, such as requiring "only one logged-in device." This mechanism requires a session registry and proper lifecycle tracking, especially across multiple nodes; distinguish "prevent new login" from "expire old session."
- **Global/forced logout:** requires managing all user sessions or token state in a shared store; single-request default logout does not do this automatically.
- **Role changes:** authorities may already be cached in the old session's `Authentication`. When permissions are downgraded, you need a strategy to refresh/revoke sessions rather than assuming every session updates immediately.

### Example fragment capping concurrent sessions

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
);
```

This is a **fragment**, not a complete distributed configuration. It illustrates blocking a second login once one session is active, rather than **setting an idle timeout**. In real applications you must configure a session registry, destroy events, principal equality, and appropriate multi-node/session-store handling. Depending on configuration, when not blocking new logins, Spring Security can mark the old session **expired**; this has different semantics from the container's idle timeout.

**Do not mix up `expiredUrl` in concurrent session control with `invalidSessionUrl` for invalid session IDs**. Test multi-device events, post-idle-timeout requests, and explicit logout separately.

## 11. Remember-Me, JWT, and SSO: Why Can Users Still Log In After Session Expiration?

### Remember-me differs from HttpSession

Spring Security includes a remember-me feature if **enabled and configured**. When the session expires, a valid remember-me cookie can create a new `Authentication` and feel like "still logged in." This does not mean the old session had not expired.

- Remember-me tokens/cookies have their own lifetime and lifecycle.
- Protect the token, consider persistent token stores, rotation, replay protection, and revocation.
- Proper Spring Security logout can invoke remember-me cleanup handlers when the feature is configured.
- For sensitive actions, you can require **fully authenticated** instead of accepting remember-me authentication per policy.

### JWT/access tokens are not destroyed by HttpSession.invalidate()

A browser application that also uses OAuth2/OIDC or issues access tokens for APIs involves multiple state layers. `POST /logout` invalidating the app's session **does not automatically** revoke issued JWTs, refresh tokens, or sessions at the Identity Provider.

Example:

```text
Browser session (App A)        → logged out
JWT access token (API B)       → may still be valid until exp/revocation
IdP SSO browser session       → may still be logged in
Refresh token                 → has its own expiry/revocation
```

If "system-wide logout" is required, design cross-app/federated logout (such as OIDC RP-Initiated Logout or Back-Channel Logout depending on the IdP), revoke tokens/refresh tokens, and log out individual app sessions where permitted.

Never equate "deleting a cookie in this tab" with "access revoked everywhere."

## 12. Real-World Scenarios and Diagnosis

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Login succeeds yet next request asks to log in again | Cookie not sent, session expired, node switch lacking shared store, context repository config | Check Set-Cookie, Path/Domain, Secure/SameSite, session store, and filter chain |
| User stays continuously active yet gets logged out at a fixed mark | Absolute TTL or IdP/token policy exists | Distinguish idle timeout from absolute lifetime; inspect safe logs |
| User is silent for a long time yet remains logged in | AJAX polling renewing session, remember-me, different timeout than expected | Check actual activity, max inactive interval, and remember-me |
| Logged right back in without password immediately after logout | Remember-me, IdP SSO, or another valid token remains active | Trace re-login flow and remaining cookies/tokens |
| `JSESSIONID` cookie still visible after logout | Cookie deletion Path/Domain mismatch, browser hasn't processed it, or session destroyed while cookie remains | Verify server session is no longer valid; don't rely solely on cookie visibility |
| `POST /logout` returns 403 | Missing/invalid CSRF token | Check token/session; use POST with CSRF |
| `GET /logout` shows a confirmation page | CSRF is enabled; this is expected behavior | Confirm to submit a valid POST |
| API returns 401 after browser logout | Authentication is gone; API has its own credential mechanism | Distinguish session, Basic/Bearer, and security chains |
| Sessions drop frequently when scaling multiple servers | Per-instance local store or load balancer routing drops session | Use Spring Session / shared store or chosen strategy |
| User's role was downgraded yet old privileges remain | `Authentication` in session still holds stale authorities | Design session revocation/refresh upon role changes |
| Redirecting to "session expired" repeatedly | `invalidSessionUrl` + stale cookie/redirect loop | Check cookie ID, logout cookie clearing, public URLs, and filter order |
| Very short timeout in unit test never fires | MockMvc lacks real container cleanup timer | Test against an embedded/live container and real session store |

### Pre-production security checklist

1. Decide **idle timeout**, **absolute lifetime**, and **when to force re-authentication** based on business requirements, not one magic number for everything.
2. Protect cookies: HTTPS, `Secure`, `HttpOnly`, appropriate `SameSite`/Path/Domain.
3. Keep **CSRF protection** for form/session-cookie flows and logout; test valid POST and missing-token paths.
4. Verify login has session fixation protection; session IDs are never logged or put in URLs.
5. Logout must **invalidate the server session and clear SecurityContext**; cookie cleanup is supplementary.
6. Check other sessions on the same account: single-session vs. all-device logout, concurrent session limits, device visibility.
7. If remember-me, bearer tokens, or SSO exist, design lifecycles/revocation **separately** for each.
8. Test timeouts and cookies in real browsers in a production-equivalent environment, including behind load balancers.
9. Verify how role updates or account locking affect still-active sessions.
10. Logging/auditing must capture enough detail for investigation **without exposing tokens/session IDs/passwords**.

## 13. Self-Check Questions

**1.** A session has a 10-minute idle timeout, and the user sends a request using the session every 5 minutes. Must the session necessarily expire 10 minutes after login?

**Answer:** No. Idle timeout is typically measured from the last time the session was used. If expiration after a fixed deadline from login is required, a separate absolute lifetime is needed.

**2.** If a cookie has a 2-hour Max-Age, is the server session guaranteed to survive for 2 hours?

**Answer:** No. The browser retaining a cookie long-term does not force the server session to stay alive; the server can time it out or invalidate it earlier. Conversely, the server session can still exist after the browser deletes the cookie, though the client normally no longer has the ID to access it.

**3.** A user leaves a tab open without interacting. Does the server proactively push a 302 when the session expires?

**Answer:** No HTTP response is emitted without a request. The next request usually reveals that the session has expired. UI timers are only supplementary and never replace server-side decisions.

**4.** With default Spring Security and CSRF enabled, does `GET /logout` always log out immediately?

**Answer:** No. Spring Security usually displays a confirmation page to submit `POST /logout` with a CSRF token; GET must not be used for state-changing actions.

**5.** Why does `POST /logout` without a CSRF token typically return 403?

**Answer:** The CSRF filter blocks state-changing requests lacking a valid token. In the demo, the old session remains usable after a blocked POST, proving logout did not execute.

**6.** Does deleting the `JSESSIONID` cookie on the frontend guarantee the server destroyed the session?

**Answer:** No. The server session can still exist until timeout, and a previously leaked ID could still be usable. Proper logout must invalidate the server session.

**7.** A user logs out on their laptop. Is the session on their phone guaranteed to be destroyed too?

**Answer:** No. Default logout targets only the current session. Logging out all devices requires managing/revoking all of the user's sessions via a dedicated mechanism.

**8.** When `invalidSessionUrl` is configured, does an invalid session ID definitely mean idle timeout elapsed?

**Answer:** No. An ID can be invalid due to logout, stale cookies, a wiped store, or other reasons. Do not conclude the exact cause from a single redirect alone.

**9.** Is `expiredUrl` in concurrent sessions the same as `invalidSessionUrl`?

**Answer:** No. `expiredUrl` relates to a session marked expired due to session-count limits; `invalidSessionUrl` handles requests carrying an invalid session ID in the applicable context.

**10.** Why can a user sometimes still get logged back in without entering a password after `HttpSession` expires?

**Answer:** If remember-me is enabled or an IdP SSO session remains active, another token/cookie mechanism may re-authenticate them. The old session does not necessarily remain alive.

**11.** Does a JWT access token automatically lose validity when the browser logs out of the web app?

**Answer:** Not by default. You must inspect token expiration, revocation/introspection, and dedicated SSO/resource server logout flows.

**12.** Can `MockMvc` prove the container reaps a session at exact second 600?

**Answer:** No. `MockMvc` tests filter/login/logout/session reuse behavior; real idle timeout depends on the container/store and requires live integration tests with an appropriate time interval or clock setup.

## 14. Summary

- **Idle timeout** is inactivity duration; **absolute lifetime** is maximum duration independent of activity; **cookie lifetime** is how long the browser keeps the cookie. These three are **distinct**.
- In stateful form login, the browser typically carries **`JSESSIONID`**, while the server stores the session and `SecurityContext`. A session can end via inactivity, invalidation, or concurrency policy enforcement.
- `server.servlet.session.timeout=10m` configures Servlet session inactivity duration; it does not auto-generate an absolute TTL or define re-authentication policies.
- **Proper logout:** use `POST /logout` with a valid CSRF token; Spring Security invalidates `HttpSession`, clears context/CSRF, and redirects. Cookie deletion is supplementary, not the sole control.
- **Do not conflate** expired sessions, invalid session IDs, concurrency-expired sessions, and explicit logout.
- **Remember-me, JWTs, refresh tokens, and SSO** have separate lifecycles; destroying one web session does not automatically revoke everything.
- Use **`MockMvc`** for login/logout behavior and **real Servlet container/store tests** for idle expiry, cookies/paths/TLS, and session sharing.
- Session security requires combining CSRF, HTTPS, cookie flags, session fixation protection, least privilege, permission revocation, and multi-device design.

## 15. Official References

- Spring Security — Logout and Logout Handlers: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — Session Management, timeouts, and invalid sessions: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — CSRF protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Remember-me authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html
- Spring Security — Testing Form Login (MockMvc): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing Logout (MockMvc): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html
- Spring Security — Testing CSRF (MockMvc): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Boot 3.5 — Servlet session configuration properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — System requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Session — Distributed session persistence: https://docs.spring.io/spring-session/reference/
