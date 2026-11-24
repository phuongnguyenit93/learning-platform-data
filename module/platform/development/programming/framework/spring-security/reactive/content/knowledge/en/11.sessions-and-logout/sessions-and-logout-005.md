# Session Expiration, Invalidation, and the Expired-Session User Experience

## 1. Why Is Session Expiration Both a Security and a UX Problem?

In a Spring Security **reactive/WebFlux** application with form login, logging in successfully does not mean the user stays authenticated forever. The system must decide **how long a session stays valid**, when it must be **invalidated**, and how the browser or API reacts when the session is no longer accepted.

A session that lives too long increases risk if a cookie is stolen or a user leaves a workstation unlocked. Conversely, a session that is too short causes unsaved data loss, workflow interruptions, and frequent re-logins. The right solution is not just picking a number like "30 minutes"; you must also understand *idle timeout*, session storage, logout/invalidation, session cookies, CSRF, 302/401/403 responses, and how to communicate clearly with users.

After this lesson, you will be able to:
- Distinguish `WebSession`, `SecurityContext`, Reactor Context, and session identifier cookies.
- Understand **idle timeout** versus **absolute lifetime** and **cookie lifetime**.
- Configure timeouts for a Spring Boot WebFlux application and recognize differences when using Spring Session.
- Explain `WebSession.invalidate()`, Spring Security logout, and bulk session revocation.
- Design warning screens, login redirects, safe draft saving, and API request handling when a session expires.
- Run a Java 17+ example with Spring Boot 3.3, testing login, cookie reuse, invalidation, logout, and authorization.
- Identify necessary test scenarios without requiring tests to "sleep" waiting for timeouts in CI.

## 2. Related Objects: Do Not Lump Everything into "Session"

~~~text
Browser                                  Spring WebFlux + Spring Security
┌────────────────────┐                   ┌─────────────────────────────────┐
│ Cookie SESSION=... │ ── HTTP request ─►│ WebSessionManager / SessionStore│
│ No password inside │                   │   └── WebSession                  │
└────────────────────┘                   │       ├── id                    │
                                         │       ├── lastAccessTime        │
                                         │       ├── maxIdleTime           │
                                         │       └── attributes            │
                                         │            └── SecurityContext │
                                         │                  └──Authentication
                                         └────────────────┬────────────────┘
                                                          │
                                         Reactor Context per subscription
                                                          │
                                            Authorization / handler
~~~

| Object | Role | Scope |
| --- | --- | --- |
| **Session cookie** | Carries the session ID so the server finds the session again; value is a secret to protect | Browser <-> server across multiple HTTP requests |
| **`WebSession`** | Stores server-side state, with `id`, access timestamps, and idle timeout | Can persist across requests, depending on session store |
| **`SecurityContext`** | Holds `Authentication` representing current identity | Loaded/saved by Spring Security via an appropriate repository |
| **`WebSessionServerSecurityContextRepository`** | Saves/loads `SecurityContext` in `WebSession` | When using a session-based model |
| **Reactor Context** | Propagates `SecurityContext` along the reactive pipeline without relying on a fixed `ThreadLocal` | Subscription/reactive execution of the request |
| **`ServerSecurityContextRepository`** | Abstraction for loading/saving authentication state | Can be `WebSession` or `NoOpServerSecurityContextRepository` |
| **Spring Session** | Can replace `WebSession` store with Redis or a shared backend | Depends on dependencies/config, useful for multiple instances |

### 2.1. WebFlux session is not Servlet's `HttpSession`

WebFlux uses `org.springframework.web.server.WebSession` and `ServerWebExchange.getSession()`, not Spring MVC's default `jakarta.servlet.http.HttpSession` or `HttpServletRequest`.

In reactive code:

~~~java
Mono<WebSession> sessionMono = exchange.getSession();
~~~

This is only a publisher to access the session. After `flatMap` or `map`, you can call `session.getMaxIdleTime()`, `session.getCreationTime()`, `session.getLastAccessTime()`, and `session.invalidate()`.

**Obtaining a `WebSession` via `getSession()` does not automatically emit a session cookie.** By Spring Framework's contract, a new session is only *started* explicitly via `start()` or implicitly by adding an attribute, and then persisted appropriately. Therefore, do not add a dummy attribute on every request just to "measure sessions": doing so can create unnecessary sessions.

### 2.2. Reactor Context does not keep login alive across new requests

While a request is being processed, use:

~~~java
Mono<String> currentName =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

The snippet above is **illustrative** inside a class importing `Mono`, `ReactiveSecurityContextHolder`, and `Authentication`. The publisher reads the identity within the current subscription; when the browser sends the next request, WebFlux must **reload the security context** (usually from `WebSession`) or re-authenticate via another token/mechanism.

A common mistake is assuming a "global" `ReactiveSecurityContextHolder` always retains the principal after a tab is closed, the session expires, or the server restarts.

## 3. Idle Timeout, Absolute Lifetime, and Cookie Lifetime

### 3.1. Idle timeout: distance from the last activity

`WebSession` provides these APIs:

~~~java
Instant lastAccess = session.getLastAccessTime();
Duration idleLimit = session.getMaxIdleTime();
boolean expired = session.isExpired();
~~~

Logical rule:

~~~text
expiresByIdle ≈ lastAccessTime + maxIdleTime
If no valid activity refreshes it before this point:
  the session is no longer accepted by the session store.
~~~

- `maxIdleTime` is the **maximum inactivity interval** between the last access and when the session is considered expired.
- When the session is accessed on a valid request, the session store can update `lastAccessTime`; that is the nature of an activity-based timeout, not an absolute clock measured from login.
- When a new request carries a cookie for an expired session, the session manager normally does not return the old session and treats it as a new/unauthenticated session.
- The browser may still hold the old cookie; **cookie presence does not guarantee a valid session**.

Example with a **15-minute** idle timeout:
- 09:00 login, 09:10 a request accesses the session -> the idle deadline can shift to roughly 09:25.
- No further activity afterward; at 09:27 the user clicks Save -> the server treats the session as expired.
- The HTML page open since 09:10 still shows old data until the client makes a request, redirects, or the UI updates itself. The server **does not push a notification to the tab** merely because time ran out.

*The example above illustrates timing, not a promise that every request refreshes the session identically.* Reverse proxies, caches, WebSockets, background polling, or actual session access patterns can cause activity to be counted differently than expected. Always verify with your actual stack, session store, and traffic.

### 3.2. Absolute lifetime: limit measured from login

A security policy might require: "Even if the user is continuously active, after 8 hours they must log in again." That is an **absolute lifetime** or *maximum authentication age*, **distinct** from an idle timeout.

`WebSession.getCreationTime()` reflects when the session was created, which **does not always match login time**: an anonymous session may have been created earlier for CSRF, a saved request, or other data. If the policy is "8 hours from successful authentication", store a separate **trusted authentication time**, apply an appropriate policy/reauthentication mechanism, and enforce it on the server.

Do not treat `getMaxIdleTime()` as an automatic solution for absolute lifetime. A session kept alive by frequent access can extend past the absolute mark if you do not enforce an additional policy.

### 3.3. Cookie lifetime is not server-side session lifetime

For example, a browser cookie with `Max-Age=3600` states how long the cookie can be kept in the browser. It does not force the backend to retain the session for 3,600 seconds, nor does it promise the backend session has not been revoked.

| Limit | Controlled at | Meaning |
| --- | --- | --- |
| Idle timeout | `WebSession.maxIdleTime` / session store | When the server session expires due to inactivity |
| Absolute login age | Application/IdP authentication policy | Forces re-login even while active |
| Cookie `Max-Age` / `Expires` | Session ID resolver, response cookie | How long the browser keeps the identifier |
| JWT `exp` | Resource server token verifier per clock/claim | When a Bearer token is no longer accepted |
| Logout/invalidate | Server logout handler/session store | Proactively terminates the session before timeout |

**Avoid confusion:** `server.reactive.session.cookie.max-age` is Boot's cookie configuration; it does not replace `server.reactive.session.timeout`. `server.servlet.session.timeout` belongs to Servlet, not the parameter to use for WebFlux.

## 4. Configuring Timeout in Spring Boot WebFlux

### 4.1. Configuration for standard WebFlux

With Spring Boot **3.3.13** and WebFlux using the default `WebSession`, place in `src/main/resources/application.properties`:

~~~properties
# WebSession idle timeout: 2 minutes (for demo only).
server.reactive.session.timeout=2m

# Cookie settings for illustration; not a server-side timeout mechanism.
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
~~~

In production applications using HTTPS, enable `server.reactive.session.cookie.secure=true` when the reverse proxy and HTTPS setup are properly configured; **do not set `secure=true` in a local HTTP demo**, because Secure cookies may not be sent by browsers over plain HTTP per browser policy. You can add domain/path per deployment, but evaluate cookie isolation and SameSite/CSRF before changing them.

The default `server.reactive.session.timeout` in Spring Boot 3.3 is **30 minutes** when not overridden. `2m` is set here so learners can easily test expiration behavior; it is not a fixed timeout recommendation for all systems.

**Practical verification:** inside a handler accessible only to logged-in users, you can read `session.getMaxIdleTime().toSeconds()`. If the result differs from your configuration, check whether `Spring Session`, a custom `WebSessionManager`, or a custom session store is overriding the default.

### 4.2. With Spring Session/WebFlux using Redis or another store

When adding Spring Session for WebFlux, a different `WebSessionManager` can use `ReactiveSessionRepository`. Multi-instance applications can thereby share session state instead of losing sessions when requests shift nodes.

Spring Boot/Spring Session provides `spring.session.timeout` to configure timeouts when Spring Session is auto-configured. **Do not assume** `server.reactive.session.timeout` always wins over every custom repository; read the configuration, actual precedence, and inspect `getMaxIdleTime()` or store metadata.

Do not confuse instructions for `@EnableRedisHttpSession` (Servlet) with `@EnableRedisWebSession` (reactive). With Spring Session auto-configuration, adding the annotation manually can cause Boot auto-configuration to back off. Configure the repository only in the way your app actually uses, without enabling overlapping session management mechanisms.

### 4.3. Changing max idle timeout for a specific session

WebFlux API:

~~~java
exchange.getSession()
    .doOnNext(session ->
        session.setMaxIdleTime(Duration.ofMinutes(15)))
    .then();
~~~

This is an **illustrative snippet**, not a complete endpoint. `setMaxIdleTime` changes the timeout **for that session**, while the repository decides how it is persisted. Use this when a policy requires distinguishing specific sessions, not arbitrarily on every request.

Note that `.then()` on `Mono` returns `Mono<Void>` for the framework to execute; never call `block()` on the event loop. A session requiring an absolute lifetime policy still needs separate handling.

## 5. When Does a Session "Become Invalid"?

Different events can end the ability to reuse an identity:

| Event | Typical mechanism | Expectation on next request |
| --- | --- | --- |
| Inactive beyond `maxIdleTime` | Session store marks `WebSession` expired | Cannot load old authentication; must re-authenticate |
| User actively logs out | Spring Security logout handler clears context, optionally invalidates `WebSession` | Old cookie/session can no longer authenticate |
| Code calls `WebSession.invalidate()` | Removes all session state from store | Must log in again for a new authenticated session |
| Session store loses data, app using in-memory store restarts | Old session record no longer exists | May be treated as anonymous |
| Account disabled/password changed/roles revoked | **Does not necessarily auto-invalidate all sessions** | Requires designing permission/session revocation or refresh |
| Session ID rotated | `WebSession.changeSessionId()` | Old ID is replaced; session may remain valid under new ID |
| JWT token expired | Resource server `exp`/decoder check | Token rejected; not `WebSession` expiring |

### 5.1. `WebSession.invalidate()`

`WebSession.invalidate()` returns `Mono<Void>` and is the API for **proactively invalidating the current session**. It removes the session from storage per the contract, unlike merely clearing an attribute.

~~~java
Mono<Void> invalidateCurrentSession(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::invalidate);
}
~~~

The method above is **illustrative** in a class importing `ServerWebExchange`, `WebSession`, and `Mono`. Do not use `session.getAttributes().clear()` as a full substitute: clearing attributes differs from invalidating the session, rotating IDs/cookies, and integrating with logout.

**Warning:** calling `invalidate()` during an in-flight request cannot "recall" responses already sent. The current `Authentication` can also still exist in the Reactor Context of the **running request**. What matters is that the **next request** cannot restore the old context. For systems with long-running sensitive operations, verify permission/session cancellation near commit boundaries and handle race conditions.

### 5.2. Spring Security reactive logout

In Spring Security WebFlux, `GET /logout` normally renders a confirmation page; `POST /logout` with a valid CSRF token performs logout under the default flow.

According to Spring Security reactive documentation:
- Default logout removes state from `ServerCsrfTokenRepository` and `ServerSecurityContextRepository`, then redirects to login.
- If you want to **explicitly invalidate the entire `WebSession`**, configure `WebSessionServerLogoutHandler`.
- When customizing the logout handler, keep the step that clears `SecurityContext` rather than only deleting the browser cookie.
- Logging out of the application **does not automatically mean** logging out of all SSO Identity Providers, all devices, or revoking all JWTs; those mechanisms require separate integration.

Example:

~~~java
DelegatingServerLogoutHandler logoutHandler =
    new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler()
    );

http.logout(logout ->
    logout.logoutHandler(logoutHandler));
~~~

This is an illustrative configuration snippet at the `ServerHttpSecurity` level, not a standalone program. The two handlers sequentially clear the security context and invalidate `WebSession`. The complete project below uses this same configuration.

### 5.3. `changeSessionId()` is not invalidation

`WebSession.changeSessionId()` returns `Mono<Void>` and generates a new ID for the **same session**. It can be part of **session fixation** protection at login. However, rotating the ID does not delete authentication/attributes and **is not logout**.

When configuring session fixation protection, let supported Spring Security/Framework mechanisms manage it and test old/new cookies; avoid rolling your own session IDs or placing IDs in URLs or logs.

## 6. Expired-Session Experience: Browser vs. API

### 6.1. Browser using form login

With `formLogin` and a protected HTML page:
1. User logs in and context is saved in `WebSession`.
2. User opens `/account` and views content.
3. After inactivity exceeding the timeout, the server session expires.
4. User clicks a link or reloads a protected URL; Spring Security cannot restore `Authentication`.
5. The form-login authentication entry point typically sends the user to the login page (HTTP 302).
6. After logging back in, the saved request may be restored depending on configuration; **there is no guarantee** that every failed POST is automatically replayed safely.

**The page currently displayed does not vanish automatically** when the backend session expires; timeout is usually detected on a new request. This matters for long forms or open admin screens.

### 6.2. Fetch/AJAX/SPA: do not infer from HTML body

If an API expected to return JSON gets redirected 302 to `/login` by the form-login entry point, browser `fetch` may follow the redirect automatically and end up receiving **200 with an HTML body**. Frontend code calling `response.json()` may throw a parse error instead of showing "Session expired".

In a combined browser + API application, design separately:
- HTML navigation: redirect to login appropriately.
- `/api/**` APIs: return **401 Unauthorized** with a safe JSON body when authentication is missing/expired; `403 Forbidden` when logged in but lacking permissions.
- Use dedicated entry points or configured security chains/exception handlers instead of making the frontend guess from `Location` or HTML page text.
- Do not assume a non-standard 419 "Session Expired" status is a Spring Security default.

Example of an **application-defined JSON contract** (not auto-generated by Spring Security):

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Your login session is no longer valid."
}
~~~

If you want to distinguish **never logged in** from **prior session expired**, the backend needs an additional signal of appropriate reliability. Never assert "timeout" solely from a 401 code: the cookie may have been deleted, the account logged out, the browser blocked cookies, or the session store failed. Avoid leaking sensitive causes in API responses.

### 6.3. Countdown UX: the server is always the source of truth

You can display a notice:

> "You may need to log in again if inactive. Save your changes before the session ends."

However, a frontend timer is usually **only an estimate**. It does not know the server's exact `lastAccessTime`, requests from other tabs, heartbeats, or store behavior. Therefore:
- Do not show countdown seconds as guaranteed fact without a server-side synchronization mechanism.
- Do not send continuous heartbeats just to keep a session alive forever without explicit business need and user consent.
- When other activity occurs, the message may become inaccurate; consider displaying an estimated time phrased with "may".
- With multi-tab applications, synchronize logout/session-expiry state via appropriate client events, while the **backend still enforces permissions on every request**.
- If the product enforces an absolute lifetime, the UI must reflect that separate policy; user activity does not extend an absolute deadline.

### 6.4. Preserving unsaved data properly

Sensitive operations/long forms need a strategy before timeout:

- Server-side autosave **while the session is still valid**, within permission boundaries and user expectations.
- For client-side drafts, store only permitted data and avoid saving PII/credentials into `localStorage`. Temporary memory or policy-compliant encrypted storage can be used, though client encryption is not an absolute defense against XSS.
- When a Save request returns 401, stop treating it as "saved successfully"; keep content in an unsaved state, notify clearly, and prompt re-login.
- After re-logging in, verify the owner/tenant of the draft before resubmitting.
- Do not automatically replay a payment/order POST just because the user logged back in: risk of duplicate actions/double-submit; use an idempotency key and required confirmation.
- Avoid keeping secrets/form passwords in logs, history, or URLs.

### 6.5. Safe redirect after re-login

If the UI wants to return to the page being viewed, use only validated internal paths. Never accept an arbitrary `returnUrl=https://attacker.example` from query params and redirect to it, as that creates an **open redirect**. Ensure the return route is valid for the newly authenticated user; **do not reopen the previous user's data** if the account changed.

## 7. Runnable Project: WebFlux, Form Login, Timeout, and Invalidation

Java **17+** example, Gradle 8.x, **Spring Boot 3.3.13** with Spring Security reactive. Versions are pinned to illustrate the API; in production use a supported version and run corresponding tests.

Idea:
- `/public` page for anonymous users.
- `/account` and `/api/session-info` require login.
- `/admin` requires `ROLE_ADMIN`.
- `POST /demo/invalidate` lets you **proactively simulate session loss** for learning without waiting 2 minutes; this URL **must not be kept in production**.
- `POST /logout` uses Spring Security logout and invalidates `WebSession`.
- Configure a 2-minute idle timeout; tests check the **timeout configuration** and **effect of invalidation**, without conflating those two with a wall-clock expiry sleep test.
- All POSTs have CSRF protection; do not disable CSRF to "make it run".

### 7.1. Structure

~~~text
webflux-session-lifecycle/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SessionLifecycleApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/
        └── SessionLifecycleTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-session-lifecycle'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Because this is WebFlux, do not add `spring-boot-starter-web` just to get a login page. Spring Security WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain`, not Servlet's `HttpSecurity`/`HttpSession`.

### 7.2. Session configuration

`src/main/resources/application.properties`:

~~~properties
# Demo: after 2 minutes of inactivity the session is considered expired.
server.reactive.session.timeout=2m

# Session cookie; use HTTPS + Secure cookie in real deployments.
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.same-site=lax
~~~

`src/main/java/demo/SessionLifecycleApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig: form login, authorities, and logout that truly deletes the session

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http,
                                   ReactiveAuthenticationManager manager) {

        DelegatingServerLogoutHandler logoutHandler =
            new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new WebSessionServerLogoutHandler()
            );

        return http
            .authenticationManager(manager)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            // Focus on form login + session flow; do not use Basic.
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.logoutHandler(logoutHandler))
            .build();
    }
}
~~~

**Explanation:**
1. `ReactiveUserDetailsService` provides two demo accounts with BCrypt hashes and `ROLE_USER`/`ROLE_ADMIN` authorities. Never use these passwords in production.
2. The manager verifies the password; Spring Security form login sets `Authentication` and uses the appropriate repository for session login.
3. `/public` is public. `/account` and `/api/session-info` are protected by `anyExchange().authenticated()`; `/admin` requires `ROLE_ADMIN`.
4. `formLogin(...)` lets Spring Security handle `POST /login`, with no need to write a custom password-receiving controller.
5. `httpBasic(...disable())` avoids mixing HTTP Basic's 401 behavior into the form-login redirect demo. This is a demo design choice.
6. `logoutHandler` performs both clearing the security context and invalidating `WebSession`. Do not assume default framework logout invalidates the **entire** `WebSession` unless configured to do so.
7. **CSRF remains enabled**. POST `/logout` and POST `/demo/invalidate` must carry a valid CSRF token; `GET /logout` does not log out directly.
8. `@EnableWebFluxSecurity` configures reactive security infrastructure; it does not replace defining authorization rules.

### 7.4. DemoController: reading state safely and proactively invalidating

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    // Do not return session ID/cookie to the client.
    public record SessionInfo(long maxIdleSeconds) {}

    @GetMapping("/public")
    Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/account")
    Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getName)
            .map(name -> "Hello " + name);
    }

    @GetMapping("/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin-only");
    }

    @GetMapping("/api/session-info")
    Mono<SessionInfo> sessionInfo(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(s -> new SessionInfo(s.getMaxIdleTime().toSeconds()));
    }

    // FOR DEMO/TEST ONLY: simulates a WebSession expiring
    // immediately, not a production endpoint.
    @PostMapping("/demo/invalidate")
    Mono<String> invalidateSession(ServerWebExchange exchange) {
        return exchange.getSession()
            .flatMap(WebSession::invalidate)
            .thenReturn("session-invalidated");
    }
}
~~~

Notes:
- `/api/session-info` only returns the **configured idle limit** (120 seconds in the demo), **not** the remaining seconds; the request calling this endpoint may count as activity.
- Never return `session.getId()`, raw cookies, CSRF tokens, or the `Authentication` object in DTOs.
- `/demo/invalidate` must sit behind authentication and CSRF; it intentionally terminates `WebSession` and is not a production logout URL. The request that just called it may still hold authentication in Reactor Context until it completes, but the next request cannot reuse the old session.
- In production, use Spring Security logout so cleanup/redirect/middleware steps are executed completely.
- Never call `session.invalidate().subscribe()` in a controller; return the `Mono` for WebFlux to coordinate.

## 8. Running in a Browser and Observing Session State

Requires JDK 17+, Gradle 8.x, and connectivity to download dependencies on first run. From the project directory:

~~~bash
gradle bootRun
~~~

Or `./gradlew bootRun` (Unix/macOS) / `gradlew.bat bootRun` (Windows) if the Gradle Wrapper is present.

Try in sequence:
1. Open `http://localhost:8080/public` -> body `public`.
2. Open `http://localhost:8080/account` in an unauthenticated browser -> normally redirected to `/login`.
3. Log in with `reader` / `reader-pass` on the Spring Security-generated page. The browser automatically submits the valid form CSRF token.
4. Return to `/account` with the session cookie -> body `Hello reader`.
5. Open `/api/session-info` -> JSON with `maxIdleSeconds` equal to `120`.
6. Open `/admin` while logged in as `reader` -> HTTP **403** due to missing `ROLE_ADMIN`.
7. Leave the browser **without sending any session-interacting requests** for more than two minutes. Then reload `/account` -> must log in again under the default configuration, unless background requests or a different session store/config alter behavior.
8. Log back in, try `POST /logout` via the form with a valid CSRF token. The active session must lose access to protected URLs.
9. To simulate expiration **immediately**, send POST `/demo/invalidate` with valid CSRF while logged in, then try `/account`. Demo URLs must not be used in production.

**Caution:** 2 minutes is only **inactivity** duration. Repeatedly refreshing `/account` or calling `/api/session-info` can extend the timer; therefore, when measuring timeout, stop all requests.

### 8.1. About cookie names and inspecting with DevTools

WebFlux's default in-memory session resolver typically uses the `SESSION` cookie. In the Network tab, you can observe `Set-Cookie` and the cookie sent on subsequent requests, but:
- The cookie name may be changed by configuration/reverse proxy/session store.
- **Never paste cookie values into screenshots/tickets/logs**: the session ID is a valuable credential.
- An `HttpOnly` cookie is still sent automatically by the browser; JavaScript does not need to read the ID.
- Deleting the browser cookie may prevent the client from finding the session, yet **does not guarantee the server-side session was invalidated**. Proper logout requires calling server-side logout/invalidation.

### 8.2. Why does curl POST /logout usually return 403?

With CSRF enabled, a bare request like:

~~~bash
curl -i -X POST http://localhost:8080/logout
~~~

lacks a CSRF token or valid session authentication and therefore **is not a valid logout test**. Use the browser form carrying the Spring Security-issued token, or use `WebTestClient` with `spring-security-test` as shown in the next section. Never disable CSRF to "fix" an incomplete test.

## 9. Integration Testing: Valid Session vs. Invalidated Session

We verify real behavior with Spring Security Test + `WebTestClient`, without sleeping for 120 real seconds in every test. Similarly in production, keep separate tests for timeout configuration and for invalidation/logout consequences.

`src/test/java/demo/SessionLifecycleTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionLifecycleTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    // Return session ID for test verification; NEVER log or expose via real API.
    private String loginAndGetCookie(String username, String password) {
        EntityExchangeResult<Void> login = client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", username)
                .with("password", password))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody().isEmpty();

        ResponseCookie cookie = login.getResponseCookies().getFirst("SESSION");
        assertThat(cookie).as("session cookie after login").isNotNull();
        return cookie.getValue();
    }

    @Test
    void anonymousCanVisitPublicButIsRedirectedFromAccount() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");

        client.get().uri("/account")
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueMatches("Location", ".*/login.*");
    }

    @Test
    void loginPersistsAuthenticationForNextRequest() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.get().uri("/account")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("Hello reader");
    }

    @Test
    void configuredMaxIdleTimeIsNotRemainingSeconds() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.get().uri("/api/session-info")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.maxIdleSeconds").isEqualTo(120);
    }

    @Test
    void logoutInvalidatesSessionAndOldCookieNoLongerAuthenticates() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.mutateWith(csrf())
            .post().uri("/logout")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().is3xxRedirection();

        client.get().uri("/account")
            .cookie("SESSION", session)
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void explicitInvalidationAlsoRemovesAccessOnNextRequest() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.mutateWith(csrf())
            .post().uri("/demo/invalidate")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("session-invalidated");

        client.get().uri("/account")
            .cookie("SESSION", session)
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void csrfIsRequiredToInvalidateViaPost() {
        String session = loginAndGetCookie("reader", "reader-pass");

        client.post().uri("/demo/invalidate")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/account")
            .cookie("SESSION", session)
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validSessionStillNeedsTheRightRole() {
        String reader = loginAndGetCookie("reader", "reader-pass");
        client.get().uri("/admin")
            .cookie("SESSION", reader)
            .exchange()
            .expectStatus().isForbidden();

        String admin = loginAndGetCookie("admin", "admin-pass");
        client.get().uri("/admin")
            .cookie("SESSION", admin)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-only");
    }
}
~~~

**Explaining the tests:**
- `bindToApplicationContext` + `springSecurity()` wires WebFlux Security `WebFilter`s in a mock server; no real network server is needed for these tests.
- `mutateWith(csrf())` is a test helper attaching a valid CSRF token; **it does not disable CSRF**.
- After a successful POST login, the test extracts the demo `SESSION` cookie and sends it again on the next GET request.
- The logout test sends POST with the cookie and CSRF; it then retries the **old cookie** to verify authentication is gone.
- The explicit invalidation test achieves the same effect on the next request without sleeping for 2 minutes.
- The missing-CSRF test ensures there is no unprotected POST way to end a session in the demo.
- The role test verifies a valid session **does not** equal `ADMIN` privileges.
- If the session resolver's cookie name changes, adjust tests to match actual config. Never hardcode the assumption that every WebFlux deployment uses `SESSION`.

Run:

~~~bash
gradle test
~~~

If using Gradle Wrapper, run `./gradlew test` / `gradlew.bat test`. Expect **seven** test methods to pass and Gradle exit code 0; exact stdout/logs depend on environment. The code is written to run with the listed dependencies, though final results must still be confirmed by running tests in the actual project.

### 9.1. Why isn't this a "wall-clock expiration" test yet?

Test `configuredMaxIdleTimeIsNotRemainingSeconds` verifies the **120-second** limit parameter. Test `explicitInvalidation...` proves an **invalidated** session revokes login access on the next request.

They **do not** prove a session automatically expires after exactly 120 seconds in production. To test real time:
- Configure a test profile with a very short timeout and isolated session store, or use a controllable clock in the store implementation.
- Ensure no background request refreshes `lastAccessTime`.
- Check requests just before and after the timeout threshold with a reasonable margin, avoiding fixed sleeps that make CI flaky.
- If using Redis, also check TTL, clock skew, cleanup, and failover behavior across nodes.
- Do not infer "timeout tested" from a single `invalidate()` call.

## 10. Handling Flow When a Session Truly Expires

### 10.1. For server-rendered HTML

~~~text
GET /account + old session cookie
    └── SessionStore finds no valid context
          └── Unauthenticated
                └── Form login entry point
                      └── 302 /login
                            └── User logs in again
                                  └── GET /account allowed if authorized
~~~

Exact redirect behavior depends on `ServerAuthenticationEntryPoint`, the success handler, and the saved request. It **does not** default to a `/session-expired` page; that is custom UX you build yourself.

### 10.2. For APIs/SPAs

Recommended client-side flow:
1. Receive HTTP **401** from the API per defined contract.
2. Mark the UI session invalid and stop calling authenticated APIs with stale credentials.
3. Display a polite message: "Your login session has ended. Please log in again to continue."
4. Keep unsaved data **in safe memory** if policy allows, without storing passwords/tokens in persistent storage.
5. Navigate to login via a validated internal URL, never accepting arbitrary external redirects.
6. After logging in, confirm the current user/tenant matches the draft before resubmitting.
7. If the request has non-idempotent effects, prompt for confirmation or enforce duplicate-submission protection.

Distinguish **401** (missing/invalid authentication) from **403** (authenticated but lacking permission, or rejected by CSRF filter). Do not show "Session expired" for every 403.

### 10.3. Designing pre-expiration warnings

If wanting to warn after roughly 10 minutes of inactivity:
- Track activity **within the tab** and show a predictive reminder; never claim exact seconds remaining on the backend.
- You can expose an authenticated-only "session status" API, though calling that API might itself count as activity and inadvertently **extend** the idle timeout. Evaluate before deploying polling.
- A "Continue session" button must execute a valid, server-authenticated request, not merely reset a client-side counter.
- For banking/sensitive data admin apps, disallow infinite renewal if an **absolute lifetime** exists; require reauthentication when due.
- Across multiple tabs or devices, synchronize UI state so one tab does not keep displaying the old user after another tab logs out.

## 11. Production Issues: Multiple Instances, Permission Updates, and Network Failures

### 11.1. Multi-server environments

When using an in-memory `WebSession` store:
- Redeploying/restarting an instance can lose sessions.
- Requests hitting another node do not necessarily have the corresponding session record.
- Sticky sessions only mitigate part of the symptom and do not replace durable session persistence.

With multiple instances, consider Spring Session WebFlux and `ReactiveSessionRepository` backed by Redis or a suitable store. Evaluate timeouts, TTLs, latency, retries, disconnect resilience, Redis security, and session deletion on logout. If the repository fails, choose a **fail-closed** policy for sensitive resources rather than granting access because the store is unreadable.

### 11.2. Single-device logout differs from all-device logout

`WebSession.invalidate()` handles the **current session**. A requirement to "log out all devices" requires a system managing account <-> session IDs or a session index plus revocation authority; it cannot be achieved solely by calling `getSession().invalidate()` on the current request.

Similarly, changing a password or disabling an account is not guaranteed to clear every security context already stored in sessions. If policy requires immediate revocation, actively invalidate sessions or re-verify account status/authorities on protected operations.

### 11.3. OAuth2/OIDC, JWT, and WebSocket

- OAuth2/OIDC login can involve both an **application session** and an **Identity Provider session**. Local logout does not necessarily log out of the IdP; use OIDC logout/back-channel mechanisms when needed and configured.
- Stateless JWTs have `exp` and independent verification. `WebSession.invalidate()` does not revoke issued Bearer tokens; short TTLs, revocation lists/token introspection, or dedicated token designs are needed.
- WebSockets have their own connection lifecycle. HTTP session expiration due to inactivity **does not always automatically close an open WebSocket connection**. For sensitive actions, verify authorization at message boundaries and design reconnect/revocation policies.

### 11.4. Difference between network errors and session expiration

A network timeout when a user clicks Save does not prove the session expired. Avoid logging the user out immediately on a 500/503 error or transient network drop. The frontend should separate:
- Explicit 401 per API contract -> prompt re-authentication.
- 403 -> missing permission or CSRF (must distinguish).
- 5xx/network timeout -> safe/idempotent retry or error notice, never assuming session expiration.
- HTML redirect from a form entry point -> handle in navigation flows, never assume JSON API output.

## 12. Common Mistakes and Fixes

| Mistake | Why is it wrong? | How to fix |
| --- | --- | --- |
| Using `server.servlet.session.timeout` for WebFlux | Belongs to Servlet stack, may have no effect | Use `server.reactive.session.timeout` for default Boot WebFlux |
| Treating cookie `Max-Age` as backend idle timeout | Cookie may still exist after server session expires | Separate cookie TTL from `WebSession` `maxIdleTime` |
| Treating `maxIdleTime` as absolute limit from login | Active requests can extend the idle timeout | Design a separate absolute authentication age |
| Creating a session on every public GET to measure users | Wastes sessions and may emit unnecessary cookies | Create/save sessions only when state actually exists |
| Setting a 30-minute JavaScript timer and treating it as truth | Tabs/requests/stores maintain separate state | Treat client timer as an estimate; server decides |
| Polling heartbeat every 5 seconds indefinitely | Keeps sessions alive unintentionally | Use only with explicit business rules and monitoring |
| Deleting browser cookie to "log out" | Server record may still remain active | POST logout with CSRF, clear context/invalidate session |
| Only rotating session ID to terminate a session | `changeSessionId` does not clear data | Use `invalidate` or proper logout |
| Calling `subscribe()` manually on `invalidate()` | Leaves request lifecycle and may not finish | Return `Mono` via WebFlux |
| Reading ThreadLocal `SecurityContextHolder` in WebFlux | Same thread is not guaranteed | Use `ReactiveSecurityContextHolder` |
| Thinking 403 always means session expired | 403 can be missing role or CSRF | Distinguish authN / authZ / CSRF |
| Thinking 302 always means login succeeded | Redirect could be login prompt or error page | Inspect `Location`, session, and subsequent request |
| Using default form login for JSON API while parsing response as JSON | `fetch` may follow 302 to HTML | Use a 401 + JSON entry point for APIs |
| Resubmitting a payment draft immediately after login | Risk of double charge/duplicate action | Idempotency key, confirmation, and transaction controls |
| Auto-replaying a POST that failed on timeout | Previous POST state may already have committed | Verify idempotency/backend state |
| Assuming local logout also revokes JWT/IdP sessions | External auth systems have separate lifecycles | Design token revocation/SSO logout separately |
| Putting session ID in logs/URLs | Leaks access credentials | Appropriate HttpOnly/Secure/SameSite cookies, TLS, log filtering |
| Forgetting to test after invalidation | Old authentication might still load | Resend old cookie and assert protected routes are blocked |

## 13. Exercises and Answers

1. **What does `WebSession.getMaxIdleTime()` measure?** The maximum inactivity interval since last access before the session expires, not the remaining seconds at call time.
2. **With a 15-minute idle session, what can a request at minute 10 cause?** Updates `lastAccessTime` and pushes back expiration, if the store counts that request as valid activity.
3. **Does setting `server.reactive.session.cookie.max-age=1h` guarantee the session lives 1 hour?** No. That is the browser cookie lifetime, separate from the backend session.
4. **Correct Boot WebFlux 3.3 config for a 10-minute idle timeout?** `server.reactive.session.timeout=10m` when using the default WebFlux session manager.
5. **Why is `server.servlet.session.timeout` wrong for this lesson?** It belongs to the Servlet/`HttpSession` stack.
6. **Distinguish `WebSession.invalidate()` and `changeSessionId()`?** `invalidate` renders the session invalid; `changeSessionId` only rotates the ID of a session that may remain valid.
7. **After logging out in one tab, do `WebSession`s on other devices auto-expire?** Not necessarily. All-device logout requires a dedicated server-side mechanism.
8. **Why is `WebSessionServerLogoutHandler` needed when wanting to delete the entire `WebSession`?** Because default logout focuses on clearing security context/CSRF; full `WebSession` invalidation must be configured explicitly per reactive docs.
9. **Session expired yet the browser still shows the old page—is that a contradiction?** No. The server checks on incoming requests; the old HTML still sits in tab memory.
10. **With form login, what does an anonymous request to a protected route normally receive?** A redirect to login, typically 302; depends on the entry point.
11. **Should a JSON API return an HTML login page when the session expires?** No; define a 401 JSON contract and handle it on the client.
12. **Does HTTP 403 mean "session expired"?** No. The user may be logged in yet missing a role or failing CSRF.
13. **What can continuously calling `/api/session-info` do?** The request itself can record activity and extend the idle timer.
14. **With stateless JWTs, does calling `WebSession.invalidate()` revoke tokens?** No.
15. **Why isn't an invalidation test a time-based expiry test?** Invalidation is proactive revocation; it does not verify the idle clock exceeding the threshold and the store detecting expiry.
16. **Should an order POST be automatically re-sent after login?** No, unless idempotency/duplicate protection is guaranteed and the user confirms when needed.
17. **What is needed to enforce an 8-hour total cap regardless of activity?** An absolute lifetime/reauthentication policy anchored on a trusted authentication timestamp, not just `maxIdleTime`.
18. **Why is Redis or a shared session store needed for clusters?** So requests across nodes can access the same session state, avoiding lost logins on instance switches.
19. **Should you log the `SESSION` cookie for debugging?** No. It is a secret that can be replayed to hijack sessions.
20. **If logout returns 403, what should you check before disabling CSRF?** HTTP method, CSRF token, session cookie, domain/path, and login/logout configuration.

## 14. Design and Operations Checklist

- [ ] Clearly decide idle timeout, absolute authentication age, and cookie policy **separately**.
- [ ] Choose timeouts based on product risk, device type, task completion time, and compliance requirements.
- [ ] Use `WebSession`/`ServerWebExchange` for the reactive stack; do not apply Servlet configuration.
- [ ] Ensure session repository and authentication repository are consistent.
- [ ] Form login uses HTTPS, CSRF protection, and appropriate session fixation defense.
- [ ] Logout uses valid POST, clears `SecurityContext`, and invalidates `WebSession` when required.
- [ ] Never return session IDs, credentials, raw tokens, or passwords in responses/logs.
- [ ] UI provides clear feedback when auth is invalid, without conflating network errors with logout.
- [ ] APIs return 401 with a JSON contract; HTML navigation performs sensible redirects.
- [ ] A strategy exists to protect drafts/saving flows before and after timeout.
- [ ] Sensitive transactions are never replayed automatically; idempotency is enforced.
- [ ] Test old cookies after invalidation/logout, CSRF, missing roles, timeouts, multiple tabs, and multiple instances.
- [ ] Plan to delete/revoke old sessions upon password reset or account disabling.
- [ ] For centralized sessions, verify Redis/store TTLs and failure policies.
- [ ] Monitor session counts, auth failure/401 rates, and session store errors without collecting secrets.
- [ ] For SSO/OIDC/JWT/WebSocket, define logout/revocation independently for each mechanism.

## 15. Official Documentation

- Spring Boot 3.3 — Common Application Properties (`server.reactive.session.timeout`, session cookies, Spring Session): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Spring Session Integration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html
- Spring Framework 6.1 — `WebSession` API (`invalidate`, `getMaxIdleTime`, `getLastAccessTime`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Security — Reactive Logout and `WebSessionServerLogoutHandler`: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security — Reactive WebFlux Configuration: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security — WebFlux CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive WebTestClient CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Session — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html

**Key takeaway:** A WebFlux session primarily expires due to **prolonged inactivity** (`maxIdleTime`), **proactive invalidation/logout**, or eviction from the session store. Cookies and UI timers do not determine whether the user remains authenticated. Design **server policy, security context, API behavior, and draft-saving/re-login UX** as coherent parts of a single session lifecycle.
