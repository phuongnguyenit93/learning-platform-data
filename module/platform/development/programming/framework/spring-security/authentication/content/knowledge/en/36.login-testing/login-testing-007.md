# Login Testing: Session Fixation, Concurrent Sessions, Session Expiration, and Access Revocation

## 1. Goal and four testing groups that must not be conflated

When testing login in Spring Security, what matters is not only that a user enters the right password and sees the home page. You must prove **the HTTP session lifecycle after login** is secure: no privilege elevation for a pre-known session ID, no exceeding the concurrent session limit, no continuing access after a session expires, and an access revocation mechanism with the right scope.

This lesson focuses on **Servlet/Spring MVC applications with Spring Security 6.5 and Spring Boot 3.x, Java 17+**, using **Form Login and HttpSession**. APIs/configurations specific to this branch are noted explicitly; when using Spring Security 7/Boot 4, verify the matching version's Javadoc. For stateless Bearer JWT applications, the lifecycle differs and **session fixation/session registry cannot be used to assume a JWT has been revoked**.

Four core testing goals:

| Category | Risk to prevent | Test action | Invariant to prove |
| --- | --- | --- | --- |
| **Session fixation** | Known anonymous session ID reused after victim logs in | Capture ID before login, perform real login, compare IDs, and retry old ID | New ID differs from old ID; old ID cannot access authenticated privileges |
| **Concurrent sessions** | An account logs in past the limit or an evicted old session still works | Log in as the same user from **two separate cookie jars** | Matches "expire old session" or "prevent new login" policy |
| **Session expiration** | Session past idle TTL or marked expired still opens protected pages | Create session, reach TTL boundary or expire per policy | Next request no longer has a valid principal |
| **Access revocation** | Logout, account lock, password change, or admin revoke yet old cookie still works | Logout/revoke on server; replay old cookie in another browser | Session scope is genuinely revoked server-side, not just client cookie deletion |

**Two key concepts to remember:** `Authentication` is the identity held in `SecurityContext`; `HttpSession` is the session data managed by the Servlet container/Spring Session. The `JSESSIONID` cookie (or `SESSION` in some Spring Session configs) contains only **an identifier** for the server to look up the session, not the full roles and authentication state.

An active session cookie is a **bearer credential**: if stolen, it can be used while the session remains valid. Rotating the session ID at login solves *fixation*, yet **does not prevent abuse of the new ID if the new ID is stolen after login**.

## 2. Servlet session architecture: where Spring Security and the container meet

Common path:

```text
Browser A
  Cookie: JSESSIONID=S1
      |
      v
Servlet Container (HttpSession S1; maxInactiveInterval)
      |
      v
SecurityFilterChain
  SecurityContextHolderFilter
      |  reads SecurityContextRepository
      |  typically attaches SecurityContext stored in HttpSession
      v
Authentication (principal=alice, authorities=[ROLE_USER])
      |
      v
AuthorizationFilter / method security
      |
      v
Controller receives request if permitted

POST /login with valid credentials:
  UsernamePasswordAuthenticationFilter -> AuthenticationManager
  -> SessionAuthenticationStrategy (including fixation/concurrency)
  -> saves SecurityContext -> HTTP session/cookie
```

Distinct responsibilities:

- **Servlet container/Spring Session:** generates session IDs, tracks idle TTL, session existence, and session creation/destruction events.
- **Spring Security:** handles authentication, selects fixation protection strategy, enforces concurrency limits, loads/saves SecurityContext, and runs logout handlers.
- **SessionRegistry:** tracks active logged-in sessions per principal for concurrency/expiration; the registry is not always the entire HttpSession store.
- **Client/browser:** holds cookies and sends them per domain/path/Secure/SameSite. Two tabs in **the same browser profile** normally share one cookie jar and therefore **are not two independent sessions**.
- **Business application:** checks resource permissions, disabled/locked accounts, MFA step-up, tenant, and payment/ownership. A live session does not guarantee permissions have not changed since login.

In Spring Security 6, `SecurityContextHolderFilter` reads context by default; if a **custom authentication filter/controller manually sets** `SecurityContextHolder`, persisting it for the next request requires calling `SecurityContextRepository.saveContext(...)` and ensuring `SessionAuthenticationStrategy` runs at the right time. Never assume every `setContext` automatically creates a session or rotates the ID.

## 3. Session fixation: testing IDs before and after privilege elevation

**Session fixation**: an attacker knows or injects an anonymous session ID into the victim's browser before login. If the app keeps using the same ID after the victim enters the right password, the attacker can use the old ID to access the elevated session.

```text
T0: Browser A not logged in, has session ID = S_old
T1: Browser A POST /login with valid password, valid CSRF
T2: Container/Spring Security rotates ID S_old -> S_new
T3: Browser A GET /me with S_new -> 200, principal=alice
T4: Browser B holding only S_old calls /me -> unauthenticated
T5: Browser B uses leaked S_new (negative demonstration)
    -> may still access without additional binding/revocation
```

**What must be asserted:** `S_old != S_new`, the response cookie uses `S_new` (in E2E), session `S_old` is no longer an authenticated session, and the post-login context matches the right user. Do not only assert login returns HTTP 302: **both success and failure** of Form Login can redirect.

Spring Security Servlet supports these strategies:

| Configuration | How it works | Testing notes |
| --- | --- | --- |
| `changeSessionId()` | Calls `HttpServletRequest.changeSessionId()`: rotates ID without creating a new session object | **Default** on Servlet 3.1+; session attributes remain |
| `migrateSession()` | Creates a new session and copies all old attributes | Check pre-login sensitive data, CSRF/pending-MFA |
| `newSession()` | Creates a clean new session, keeping a few Spring Security attributes | Does not clear all other traces/cookies by default |
| `none()` | Disables fixation protection | Not recommended for interactive cookie logins |

Explicitly stating intent:

```java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId()));
```

This is a **fragment** placed inside the method creating `SecurityFilterChain`, not a standalone Java program. On modern Servlets, this line often repeats the default so reviewers can see the policy clearly.

**Watch out for session objects in tests:** `changeSessionId()` can mutate the ID directly **on the same `MockHttpSession` instance**. If you compare `beforeSession.getId()` *after* login against `afterSession.getId()`, both references may point to the same mutated object, causing a false failure. You must **snapshot `String oldId` before login**.

**Boundary warning:** pinning/rotating the ID does not prevent XSS, session cookie theft, stolen remember-me cookies, OAuth access token reuse, or already-revoked roles. Those are separate threats and mechanisms.

## 4. Concurrent sessions: "expire old session" vs. "prevent new login" policies

Spring Security 6.5 supports concurrent session control for Form Login:

### 4.1. Allowing a new login and marking the old session expired

```java
http.sessionManagement(session -> session
    .maximumSessions(1));
```

Under this default policy:

1. Browser A logs in successfully as Alice → session `SA`.
2. Browser B in an **independent/incognito profile** logs in as Alice → session `SB`.
3. Spring Security allows B and **marks `SA` expired** (typically the least recently used session).
4. When A sends a new request, `ConcurrentSessionFilter` sees `SA` is expired and applies `SessionInformationExpiredStrategy`; `SA` loses access.
5. B continues accessing resources with `SB` per its roles.

**Do not say `SA` is always deleted from the store the exact second B logs in**. Spring's `SessionInformation` distinguishes **active**, **expired** (marked for termination), and **destroyed** (session invalidated/removed by container). The filter typically handles `SA` on **the next request**. Tests must send a follow-up request from A.

To redirect to an expiration page on concurrency:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .expiredUrl("/session-expired"));
```

The target page must be publicly accessible and not cause redirect loops. For JSON APIs, use `expiredSessionStrategy(...)` returning an appropriate response instead of an HTML redirect.

### 4.2. Keeping the old session and rejecting the new login

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true));
```

Under this policy:

- A is already logged in as Alice; `SA` is active.
- B enters Alice's **correct** username/password yet **is denied a second session** due to the quota.
- A retains access. Browser B has no authenticated principal for Alice.
- Standard form login sends B to the authentication failure URL; it is not necessarily HTTP 403. Non-interactive mechanisms may return HTTP 401.

**Do not test by opening a new tab in the same browser** because A and "B" can share cookies and thus never create a second session. Use two browser profiles or two cookie jars in E2E; in MockMvc, run two independent login requests that do not carry each other's session.

### 4.3. HttpSessionEventPublisher and SessionRegistry

To track session deletion/expiration events, the Spring Security 6.5 docs instruct registering:

```java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
```

Import `org.springframework.security.web.session.HttpSessionEventPublisher`. It publishes HttpSession lifecycle events to the application context; without it, in-memory `SessionRegistryImpl` can **retain ended session IDs**, miscounting quotas and rejecting new logins even after old sessions genuinely ended.

If using a custom `UserDetails` as principal, implement stable `equals/hashCode` based on identity. `SessionRegistryImpl` uses a Map keyed by principal; if the same account is loaded as "different" objects per `equals`, concurrency quotas can be bypassed. Never use mutable fields/role lists on the principal as equality keys, which makes keys unstable.

**Multi-node limitation:** default `SessionRegistryImpl` is a **single-JVM** in-memory registry and does not coordinate quotas across multiple pods. With Spring Session + Redis/JDBC, configure a **shared session repository**, principal index, and matching registry such as `SpringSessionBackedSessionRegistry`, and test across nodes. Never claim "adding Redis automatically enforces `maxSessions` cluster-wide" without verifying the registry/strategy.

## 5. Session timeout, invalid session, and concurrent expiration do not mean the same thing

Distinguish 5 ways a session ends or stops working:

| Case | Who decides | Condition | Typical observed state |
| --- | --- | --- | --- |
| **Idle timeout** | Servlet container/Spring Session | No access within `maxInactiveInterval` | Session expires/destroys; request with old cookie is invalid/anonymous |
| **Absolute timeout** (if added) | Application policy | Total time since login exceeds limit, even if active | Must be implemented/tested separately; idle timeout is not absolute |
| **Concurrency expiration** | Concurrent session strategy | New login exceeds limit under evict-old policy | `SessionInformation.isExpired()=true`, filter handles on next request |
| **Logout/session.invalidate()** | User/application/container | Intentional session termination | Session invalidated/destroyed; old cookie no longer authenticates |
| **Access token revoked/expired** | OAuth issuer/resource server | Bearer token no longer trusted | Does not imply HttpSession invalid; different auth scheme |

### 5.1. Idle timeout with Spring Boot

In `application.yml` of a Spring Boot 3 project:

```yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

`timeout: 20m` is the **inactivity duration** of the Servlet session (actual timing/granularity depends on container/store). Valid requests within that window can update last-access and extend the session. **This is not a 20-minute absolute lifetime from login**. If policy mandates an 8-hour max session age from login, store a trusted `loginAt` and enforce it separately, even when the user sends steady requests.

`Secure` cookies require HTTPS. During local HTTP development, browsers may refuse to send Secure cookies, making you think the session vanished; use an appropriate test profile. `SameSite=Lax` mitigates some CSRF scenarios, **yet does not replace CSRF tokens** for form POSTs; if OIDC/SAML callbacks need cross-site POSTs, evaluate the cookie policy per flow.

### 5.2. invalidSessionUrl vs expiredUrl

Example:

```java
http.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid")
    .maximumSessions(1)
    .expiredUrl("/session-expired"));
```

- `invalidSessionUrl`: defines UX when a request carries **an ID no longer valid** recognized by the session-management mechanism (e.g., timeout or stale ID). It is not limited to idle timeouts: a cookie retained after logout can also trigger confusion.
- `expiredUrl`: defines UX when `ConcurrentSessionFilter` sees a **session marked expired by concurrency policy**. This is a distinct state from a non-existent cookie.
- Do not assume every post-timeout request always redirects to the same URL across all apps: it depends on the filter chain, API/browser mode, whether a cookie is still present, the session store, and custom strategies.
- Both redirect URLs must be **permitAll**, simple pages that do not auto-create a new session/cookie causing a redirect loop.

Spring docs note `invalidSessionUrl` can **mistakenly send users to a "session expired" page after logout** if the old session cookie is still sent by the browser. Test proper cookie deletion (Spring's `deleteCookies("JSESSIONID")` is one option, though not all servlet containers/proxies behave identically). With Spring Session, the cookie name may be `SESSION` rather than `JSESSIONID`.

### 5.3. How to test timeouts reliably

- **Custom absolute timeout unit tests:** use an injectable `Clock`/fixed `Instant`, checking right before/at/after expiry. Avoid `Thread.sleep(20 minutes)` in CI.
- **Servlet integration:** use a test profile with a short timeout and a real embedded container; not every `MockHttpSession` expires automatically just because wall-clock time passes. You can explicitly invalidate in MockMvc to test **invalid** session handling, though that does not prove automatic container idle expiration.
- **Spring Session (Redis/JDBC):** configure a test TTL, verify the backend store drops the entry and requests from the old client lose authentication; key expiry and index cleanup may not happen at the exact nanosecond.
- **Concurrency expiration:** do not wait for TTL; log in with two sessions and then reuse session A to verify `expiredUrl`/unauthenticated behavior.

**Do not confuse "login page returns 200" with "resource is still accessible"**: HTTP clients often follow redirects and show 200 for the login page, even though the initial `GET /me` returned 302.

## 6. Access revocation: logout, admin revoke, password change, and locked accounts

### 6.1. Logging out one web session

With Spring Security Form Login and CSRF enabled, `GET /logout` by default may be a confirmation page, while `POST /logout` with a valid CSRF token performs logout. Per the docs, default logout handlers are responsible for:

- Invalidating the HTTP session (default `SecurityContextLogoutHandler`).
- Clearing `SecurityContext`/repository.
- Cleaning up `remember-me` state if configured.
- Clearing the corresponding CSRF token and publishing `LogoutSuccessEvent`.
- Redirecting to the configured URL, typically `/login?logout` for form login.

Illustrative configuration:

```java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .logoutSuccessUrl("/login?logout"));
```

**Do not only delete the client cookie:** if the server session still exists, anyone holding the old cookie can keep accessing resources. Invalidate the session on the server; cookie clearing only helps the browser stop sending stale tokens. With reverse proxies, context paths/cookie Path/Domain, and Servlet containers, test real `Set-Cookie`.

After logout, a new request has no authenticated principal. **This does not mean** the user was deleted from the DB or all sessions of the user were logged out.

### 6.2. "Log out from all devices"

Logging out a single current session differs from **revoking all sessions of an account**. A "Log out all devices" feature requires:

1. Identifying the stable identity/account ID, tenant/realm, and all registered or shared-store sessions.
2. Invalidating/expiring **every session** server-side or applying a per-user **authorization epoch/version** to reject old sessions on incoming requests.
3. Synchronizing across all nodes; checking admin privileges or re-auth/step-up before this operation.
4. Executing idempotently, safely handling retries and sessions created concurrently during revocation.
5. Testing cookies across browsers A/B/C; not just checking the browser that clicked the button.

On a single JVM with `SessionRegistryImpl`, you can call `getAllSessions(principal, false)` and then `SessionInformation.expireNow()`; this **marks the session as expired** so the filter handles it on incoming requests, without necessarily deleting the physical entry immediately.

A conceptual example (not standalone; only for use inside a service with a properly configured `SessionRegistry`):

```java
for (SessionInformation info :
        sessionRegistry.getAllSessions(principal, false)) {
    info.expireNow();
}
```

Remember to import `org.springframework.security.core.session.SessionInformation`. Admin revocation needs the exact account principal and stable equality; never accept a principal object submitted by the browser and trust it. If you need **immediate blocking** of sessions before the next request, implement appropriate per-request trust/policy checks against a reliable state store rather than relying only on an in-memory registry.

### 6.3. Disabling an account or changing password does not revoke all sessions by default

Once a user logs in, `Authentication`/authorities may already be stored in the session. If an admin sets `enabled=false` or revokes `ROLE_ADMIN` in the DB, **already-authenticated sessions may continue carrying old authorities** unless the app revalidates/revokes them. This requires explicit policy design:

- Locked user: block new logins in `UserDetailsService`/provider and decide whether to revoke old sessions, refresh tokens, and remember-me.
- Password change: depending on risk, revoke all sessions or all except the current one; check old cookies, remember-me, and other sessions.
- Role/tenant change: avoid preserving stale privileges; use a session authorization/version/epoch or invalidation.
- Resource authorization must still check owner/tenant on each request (or cache with proper TTL/invalidation). Never treat an active session as immutable authorization.

### 6.4. Bearer JWTs and OAuth are not revoked by HttpSession.logout()

A Resource Server validating `Authorization: Bearer JWT` via signature, `iss`, `aud`, `exp`, and scopes may have no `HttpSession`. A browser `POST /logout` **does not expire issued JWTs**, nor does it revoke refresh tokens at the Authorization Server or IdP/OIDC sessions. Revoking access tokens before expiry requires an enforced `jti` denylist/blacklist, introspection, sender-constrained tokens, or equivalent mechanisms. Refresh token rotation/reuse detection is a separate workflow.

**Reporting scope:** state explicitly whether "Servlet sessions were revoked" or "OAuth tokens were revoked"; never merge them into a single claim that "the user no longer has access across all systems".

## 7. Spring Boot 3 + Spring Security 6.5, Java 17 example

### 7.1. Dependencies

Create a Spring Boot 3.x project (Java 17+, Servlet/Spring MVC) with Gradle and Spring Security. In `build.gradle` with the Boot plugin/Java toolchain already present:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Do not mix this Servlet code with WebFlux's `ServerHttpSecurity`/`WebSession`. If you plan to use Spring Session Redis, add the corresponding dependency and configure a separate store.

### 7.2. Main application

File `src/main/java/com/example/sessiontests/SessionTestsApplication.java`:

```java
package com.example.sessiontests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionTestsApplication.class, args);
    }
}
```

### 7.3. SecurityConfig with fixation, concurrency, and logout

File `src/main/java/com/example/sessiontests/SecurityConfig.java`:

```java
package com.example.sessiontests;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                "/", "/public/start", "/login",
                                "/session-expired", "/session-invalid")
                        .permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation.changeSessionId())
                        .invalidSessionUrl("/session-invalid")
                        .maximumSessions(1)
                        .expiredUrl("/session-expired"))
                .logout(logout -> logout
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("JSESSIONID")
                        .logoutSuccessUrl("/login?logout"))
                .build();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("alice-pass"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("bob-pass"))
                        .roles("USER")
                        .build());
    }
}
```

**This configuration CHOOSES the allow-new-session policy**: `maximumSessions(1)` + `expiredUrl(...)` expires Alice's old session after Alice logs in from another browser. To **prevent the new session**, replace the concurrency block with:

```java
.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true))
```

Do not put both styles into the same configuration. When choosing the prevent-new-login policy, you can customize the failure handler per UX; default form-login failure must not be assumed to always return HTTP 403.

**SecurityConfig is only a demo**: `alice`/`bob` accounts with test passwords and an in-memory store; not connected to a production database. The BCrypt encoder uses salts/hashes for passwords, avoiding `{noop}` or hardcoding credentials in real repos. `.permitAll()` still runs Spring Security filters and does not disable CSRF.

### 7.4. PageController to observe sessions

File `src/main/java/com/example/sessiontests/PageController.java`:

```java
package com.example.sessiontests;

import java.security.Principal;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PageController {

    @GetMapping("/")
    public String home() {
        return "session test home";
    }

    @GetMapping("/public/start")
    public String start(HttpServletRequest request) {
        request.getSession(true); // create anonymous session to test fixation
        return "anonymous session created";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/session-expired")
    public String expired() {
        return "concurrent session expired";
    }

    @GetMapping("/session-invalid")
    public String invalid() {
        return "invalid or timed-out session";
    }
}
```

Public endpoints return fixed bodies and **never return `JSESSIONID`**, CSRF tokens, or sensitive session attributes. The `/session-expired` and `/session-invalid` pages allow anonymous access so authorization does not create redirect loops; real behavior with stale cookies still needs testing.

### 7.5. Timeout and cookies in application.yml

```yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Applies to production HTTPS. Over local HTTP you may need a **test-only profile** adjusting Secure cookies so the test browser sends the cookie; never lower TLS standards in real environments. Cookie attributes limit certain exposure/usage vectors without providing proof-of-possession.

### 7.6. Trying it out

In a project with the Gradle wrapper:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Open two completely independent browser profiles. In browser A:

1. Visit `/public/start` and observe the anonymous cookie; record it **only in fixtures/test tooling**, never logging real IDs.
2. Visit `/me` → redirects to login; log in as `alice/alice-pass` via Form Login (with CSRF).
3. After login: `/me` → `hello alice`, and the session ID has rotated.
4. Browser B logs in as `alice/alice-pass` from its own cookie jar. Return to browser A and call `/me`: A hits the expired strategy and can no longer enter `/me`. B still gets in.
5. Browser B POSTs `/logout` with valid CSRF. Retry the old cookie from the test fixture in a new request → unauthenticated.
6. Test idle session expiry using a short-timeout profile in an embedded container; never wait 20 minutes in CI.

**Never copy session cookies/test passwords into screenshots, shared logs, or public bug tickets**. Credentials and URLs here are for local/test only.

## 8. MockMvc: testing session fixation with real login, not a mock principal

Place `src/test/java/com/example/sessiontests/SessionLoginTest.java` in the project above. Spring Security Test provides `csrf()`, `authenticated()`, and request builders. The example uses a test class with the Spring application context; to keep tests from affecting each other's session registry, you can use `@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)` in small test projects; that is slow, so production CI should reset registries/fixtures explicitly.

```java
package com.example.sessiontests;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionLoginTest {

    @Autowired
    MockMvc mvc;

    @Test
    void sessionIdChangesWhenUserLogsIn() throws Exception {
        MvcResult beforeResult = mvc.perform(get("/public/start"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession existingSession =
                (MockHttpSession) beforeResult.getRequest().getSession(false);
        assertThat(existingSession).isNotNull();
        String originalId = existingSession.getId();

        MvcResult loginResult = mvc.perform(post("/login")
                    .session(existingSession)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "alice-pass"))
                .andExpect(authenticated())
                .andReturn();

        MockHttpSession afterSession =
                (MockHttpSession) loginResult.getRequest().getSession(false);
        assertThat(afterSession).isNotNull();
        assertThat(afterSession.getId()).isNotEqualTo(originalId);

        mvc.perform(get("/me").session(afterSession))
                .andExpect(status().isOk())
                .andExpect(content().string("hello alice"));
    }
}
```

This is the test **for the exact code example** in section 7. Static import `authenticated()` is in `org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers`. To verify properly, do not use `@WithMockUser` or `.with(user("alice"))` because they inject a principal directly into the test, **skipping** real login/session strategies.

**Additional E2E testing is needed** with an HTTP embedded container + cookie jars:

- Inspect the new session `Set-Cookie` value on the response; verify the old ID is no longer an authenticated session.
- Do not reuse the same `MockHttpSession` reference to simulate a browser carrying the old ID: its ID may have been mutated in place.
- When the old cookie is sent from a second jar, verify the initial response is a redirect/401 per the entry point rather than mistaking a 200 login page for success if the client follows 302.

MockMvc validates logic at the Spring/Test Servlet layer, while an embedded server validates cookie behavior, reverse proxies, and container session lifecycles.

## 9. MockMvc: testing concurrent sessions across two independent sessions

Continuing inside a separate integration class (or adding a method to `SessionLoginTest` if the application context is isolated):

```java
@Test
void secondLoginExpiresFirstSession() throws Exception {
    MvcResult resultA = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(authenticated())
            .andReturn();
    MockHttpSession sessionA =
            (MockHttpSession) resultA.getRequest().getSession(false);

    mvc.perform(get("/me").session(sessionA))
            .andExpect(status().isOk());

    MvcResult resultB = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "alice-pass"))
            .andExpect(authenticated())
            .andReturn();
    MockHttpSession sessionB =
            (MockHttpSession) resultB.getRequest().getSession(false);

    assertThat(sessionA.getId()).isNotEqualTo(sessionB.getId());

    // Concurrency filter handles the old session on the next request.
    // Exact response depends on expiredUrl/strategy and proxy.
    mvc.perform(get("/me").session(sessionA))
            .andExpect(status().is3xxRedirection());

    mvc.perform(get("/me").session(sessionB))
            .andExpect(status().isOk());
}
```

This is an **additional method** for the class in section 8 using the declared imports/beans; not a standalone Java file. In the demo project with `expiredUrl("/session-expired")`, you can also assert the redirect Location to that route. Use `SessionRegistry` or `SessionInformation.isExpired()` to distinguish *marked expired* from *destroyed*. If framework test setup/custom expired strategies differ, status assertions must adjust to match configured behavior.

### Opposite policy: prevent new login

To test `maxSessionsPreventsLogin(true)`, create **a separate test application configuration**:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true));
```

Expectations with two cookie jars when the real Alice logs in on A first:

- A remains authorized at `/me`.
- B enters the right password yet **is not authenticated**, per the form-login failure handler.
- After A logs out or its real session is destroyed and the registry receives the event, B can log in if policy allows.
- If B keeps getting rejected after A has genuinely logged out, check `HttpSessionEventPublisher`, stale `SessionRegistry`, custom `UserDetails` `equals`/`hashCode`, and multiple nodes.
- An HTTP 302 on B **does not prove login succeeded**: Form Login failure also redirects. Assert `unauthenticated()` and protected access on session B.

Never mix the evict-old policy and the prevent-new-login policy in the same `SecurityFilterChain` without explicitly choosing the desired semantics.

## 10. Session expiration: testing timeouts and invalid cookies without false positives

### 10.1. Manual invalidation ≠ natural idle timeout

In unit/MockMvc tests you can check:

```java
MockHttpSession session = new MockHttpSession();
session.setAttribute("marker", "test");
session.invalidate();
assertThat(session.isInvalid()).isTrue();
```

This is an **invalidation action test** and does not test the container automatically removing sessions past timeout. For real idle TTL, use an embedded Servlet container with a small session timeout in a test profile, verifying expired cookie behavior and authenticated state. For app-implemented absolute timeouts, use an injectable `Clock` and test boundaries.

### 10.2. Verifying invalidSessionUrl UX properly

A browser request carrying an old cookie after timeout can route to `/session-invalid`, whereas a request without a cookie may route to `/login`. Never assert "any anonymous request goes to `/session-invalid`"; that logic applies when an **invalid ID is presented**. In tests, prepare a cookie jar/stale cookie ID and test against the real filter chain.

Note that Spring Security 6 does not use `SessionManagementFilter` in the same default way as Spring Security 5; some older session management hooks have no effect or were replaced. Rely on the Spring Security 6.5 reference/version in use rather than guessing strategy calls after custom authentication.

### 10.3. Testing concurrency expiration

A session expired by `SessionInformation.expireNow()` differs from a session timed out by the container. Thus you can test the rule through the registry/session strategy without waiting on a clock:

- Log in A creating `SA`, confirming `SA` can access `/me`.
- Log in B as the same user, marking `SA` expired.
- Send GET with `SA`, confirming access to the resource is denied and the configured redirect/strategy runs.
- Send GET with `SB`, confirming the right user still has access.
- Assert no side effects occurred from the expired `SA` request.

Never treat "marked expired" as proof that "the physical HttpSession was immediately invalidated"; test the follow-up request and store state.

## 11. Access revocation: how to test logout and multi-device revocation

### 11.1. Logging out the current session

In an integration test you can log in and then send:

```java
mvc.perform(post("/logout")
        .session(sessionA)
        .with(csrf()))
    .andExpect(status().is3xxRedirection());

// If using MockHttpSession from the same fixture:
assertThat(sessionA.isInvalid()).isTrue();
```

The snippet above is a **fragment** inside a test class that already has `MockMvc mvc` and `MockHttpSession sessionA`, not a standalone test. An invalidated `MockHttpSession` should not be passed back via `.session(sessionA)` to try testing a new request: it may throw in the test machinery. To test **old cookies** over the wire, use a browser/HTTP test with an embedded container + second cookie jar, or query the session store via its API.

HTTP E2E tests should verify **the logout response**, **that the store no longer holds a valid session**, and **that `GET /me` with the old cookie is unauthenticated**. Deleting `JSESSIONID` only in the browser without checking the server-side store can miss post-logout session hijacking.

### 11.2. Admin revoke all sessions

Create at least two sessions A/B for the same account in an environment **allowing >=2 sessions** (do not use `maximumSessions(1)`, otherwise A expires before the test). Then invoke the revoke operation via an admin or step-up-authenticated account owner:

1. Identify the exact account ID; never allow user A to submit `username=bob` and arbitrarily revoke Bob.
2. Revoke A and B in the registry/shared store, or bump a per-user revocation epoch checked on every request.
3. Replay cookies A/B from two browsers against a protected resource; **both must lose access**.
4. Verify request C from another user still works; do not accidentally revoke the entire system.
5. Use cross-node synchronization and check handling of in-flight requests; a request already started before revocation may need a dedicated policy to halt critical side effects.
6. If the system has remember-me/OAuth tokens, test independently whether they are revoked per requirements.

### 11.3. Password change, account disablement, and revoked permissions

Use a fixture with Alice logged in and Alice's password changed/account disabled in the database. A test must distinguish:

- **New login:** the provider must reject old credentials or disabled users per policy.
- **Existing session:** if only an Authentication snapshot is stored without revalidation/revocation, the cookie may still be accepted. That is a behavior to design explicitly, never assuming a password change automatically logs out all sessions.
- **Remember-me auto-login:** if enabled, test persistent token stores/hash-based token lifecycles separately.
- **JWT access tokens:** can remain valid until expiry without introspection/denylists; do not conclude clearing HttpSession revokes JWTs.
- **Role/resource authorization:** a user whose `ROLE_ADMIN` was revoked while a session still caches `ROLE_ADMIN` needs session invalidation or policy reading latest state as required.

## 12. Spring Session Redis and multi-node: testing is mandatory

With multiple instances, each instance has its own local HttpSession and `SessionRegistryImpl`, so the same Alice can log in on two pods while each pod thinks only one session exists. Sticky sessions reduce routing issues but do not create a **shared registry** or solve revoke-all.

Spring Session replaces `HttpSession` with a centralized repository offering Redis/JDBC adapters. With Spring Session Redis, the cookie is commonly named `SESSION`; this affects cookie jar tests, logout cookie names, and invalidation flows.

To use Spring Session (configuration depends on Spring Boot/Spring Session line), add the BOM-managed starter, e.g., in a supported project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-session-data-redis'
}
```

Then configure the Redis connection/session repository per the exact Boot documentation you are running. **Never put Redis credentials into code**; use secret management. For concurrency control to work **across a cluster**, consider `SpringSessionBackedSessionRegistry` with a `FindByIndexNameSessionRepository` having a principal index. Verify consistent principal name mapping, event forwarding, and per-node policies.

Cluster E2E checklist:

| Scenario | Pod A | Pod B | Expectation |
| --- | --- | --- | --- |
| Session A login | Creates session A | Reads session A | Same identity if store is shared |
| Session B login same Alice | Registry/store knows A | Logs in B | `maxSessions` policy enforced cross-node |
| A expired | Receives old cookie A | Handled at B | No longer authenticated |
| A logout | Invalidates A in shared store | GET with A hits B | B rejects |
| Admin revokes Alice | Revokes all A/B | Requests hit both A/B | Both reject |
| Node restart | A loses in-memory cache | B retains shared store | Policy follows durable/revocation store |
| Redis outage | Cannot fetch session | Bypass disallowed | Fail closed per policy, metrics/alerts |

Never assert that adding `spring-boot-starter-session-data-redis` **automatically** turns `SessionRegistryImpl` into a distributed registry. Test with **two HTTP clients, two app instances, and a real session repository**. In-memory Mockito tests cannot substitute for this proof.

## 13. Pure Java 17: simulating session ID rotation, concurrency, and revocation

The following example compiles on **JDK 17+ without Spring**, using an in-memory store with synchronized methods to model behavior. It separates:

- Anonymous session `S0` and authenticated session `S1`;
- ID rotation on login, removing `S0` from the store;
- `maxSessions=1` under an evict-old policy invalidating the prior session;
- Idle expiration after 20 minutes of inactivity;
- Logout removing the session;
- Another user Bob unaffected by revoking Alice.

**Limitation:** `synchronized` covers only **one object in one JVM** and does not prove concurrency safety in Redis/JDBC/multi-node setups. Production uses Servlet/Spring Security, never a hand-rolled session store from lab code.

Save as `SessionLifecycleLab.java`:

```java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public final class SessionLifecycleLab {

    private static final Duration IDLE = Duration.ofMinutes(20);
    private static final SecureRandom RANDOM = new SecureRandom();

    record Session(String principal, Instant lastAccess) {}

    private final Map<String, Session> sessions = new HashMap<>();
    private final Map<String, String> activeByUser = new HashMap<>();

    private static String newId() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    synchronized String anonymous(Instant now) {
        String id = newId();
        sessions.put(id, new Session(null, now));
        return id;
    }

    synchronized String loginRotate(
            String anonymousId, String username, Instant now) {
        Session before = sessions.remove(anonymousId);
        if (before == null || before.principal() != null) {
            throw new IllegalStateException("Not an anonymous session");
        }

        String authenticatedId = newId();
        String priorId = activeByUser.put(username, authenticatedId);
        if (priorId != null) {
            // Models the maxSessions=1 policy evicting the old session.
            sessions.remove(priorId);
        }
        sessions.put(authenticatedId, new Session(username, now));
        return authenticatedId;
    }

    synchronized boolean authorized(
            String id, String username, Instant now) {
        Session s = sessions.get(id);
        if (s == null || !Objects.equals(username, s.principal())) {
            return false;
        }
        if (!now.isBefore(s.lastAccess().plus(IDLE))) {
            sessions.remove(id);
            activeByUser.remove(username, id);
            return false;
        }
        sessions.put(id, new Session(s.principal(), now));
        return true;
    }

    synchronized void logout(String id) {
        Session removed = sessions.remove(id);
        if (removed != null && removed.principal() != null) {
            activeByUser.remove(removed.principal(), id);
        }
    }

    public static void main(String[] args) {
        Instant t0 = Instant.parse("2026-11-06T00:00:00Z");
        SessionLifecycleLab lab = new SessionLifecycleLab();

        String anonymous = lab.anonymous(t0);
        System.out.println("preLoginAllowed=" +
                lab.authorized(anonymous, "alice", t0));

        String first = lab.loginRotate(anonymous, "alice", t0);
        System.out.println("rotated=" + !anonymous.equals(first));
        System.out.println("oldIdRejected=" +
                !lab.authorized(anonymous, "alice", t0));
        System.out.println("newIdAllowed=" +
                lab.authorized(first, "alice", t0));

        String second = lab.loginRotate(
                lab.anonymous(t0), "alice", t0.plusSeconds(60));
        System.out.println("firstExpiredBySecond=" +
                !lab.authorized(first, "alice", t0.plusSeconds(61)));
        System.out.println("secondAllowed=" +
                lab.authorized(second, "alice", t0.plusSeconds(61)));

        System.out.println("idleExpired=" +
                !lab.authorized(second, "alice",
                        t0.plus(Duration.ofMinutes(25))));

        String third = lab.loginRotate(
                lab.anonymous(t0), "alice", t0);
        lab.logout(third);
        System.out.println("logoutRevoked=" +
                !lab.authorized(third, "alice", t0));

        String bob = lab.loginRotate(
                lab.anonymous(t0), "bob", t0);
        System.out.println("anotherUserUnaffected=" +
                lab.authorized(bob, "bob", t0));
    }
}
```

Compile/run from the directory containing the file:

```bash
javac SessionLifecycleLab.java
java SessionLifecycleLab
```

**Deterministic** stdout (IDs are randomly generated, though the program does not print them):

```text
preLoginAllowed=false
rotated=true
oldIdRejected=true
newIdAllowed=true
firstExpiredBySecond=true
secondAllowed=true
idleExpired=true
logoutRevoked=true
anotherUserUnaffected=true
```

Explanation:

- `preLoginAllowed=false` and `oldIdRejected=true` show an anonymous ID does not become an authenticated ID after login.
- `rotated=true`: session ID was rotated. `newIdAllowed=true` shows the new session receives Alice's access.
- `firstExpiredBySecond=true`: the `maxSessions=1` model forbids two concurrent Alice sessions.
- `secondAllowed=true`: the new login remains valid.
- `idleExpired=true`: after 25 minutes of inactivity, the session is no longer valid under the 20-minute TTL.
- `logoutRevoked=true`: removing the session server-side prevents the old ID from granting access.
- `anotherUserUnaffected=true`: revoking Alice must not drop Bob's session.

**Do not confuse this example with Spring's session registry:** the lab code deletes the prior session immediately on a new login, whereas Spring Security may **mark it expired and handle it on the next request**. The lab code uses no HTTP, CSRF, cookies, official session fixation strategies, `SessionRegistry`, or Redis. It is purely for verifying mental models and boundaries.

## 14. Login and revocation test matrix

| ID | Context | Action | Expectation |
| --- | --- | --- | --- |
| S01 | Anonymous session SA | Real login with right password | ID changes to SB, right principal |
| S02 | Successful login | Send old SA cookie from another HTTP client | Sees no authenticated data |
| S03 | Successful login | Send new SB cookie | Authorized per role |
| S04 | Wrong password login | Compare ID/authentication | Must not elevate anonymous session to authenticated |
| S05 | App uses custom login filter | Successful login | `SessionAuthenticationStrategy` and persistence actually applied |
| C01 | Alice logs in A | Alice logs in B, default `maximumSessions(1)` | B passes, A expires on next request |
| C02 | Alice logs in A | Alice logs in B, `maxSessionsPreventsLogin(true)` | B fails, A still passes |
| C03 | Alice logs out A | Alice logs in B after logout | B can log in if quota released properly |
| C04 | Broken custom `UserDetails` equality | Two logins same account | Test catches registry miscounting |
| C05 | Alice uses two tabs in same browser | Access A/B | Only one session; do not use as concurrency test |
| T01 | Session idle under timeout | Protected GET | Passes |
| T02 | Session idle past timeout | Protected GET with stale cookie | Unauthenticated; proper invalid UX |
| T03 | User continuously active | Past app's custom absolute timeout | Re-auth required if policy demands |
| T04 | Session expired by concurrency | GET with old session cookie | Expired strategy, does not enter controller |
| T05 | Cookie lost yet client uses old URL | GET /me | Login/401 per chain; never treat 200 login page as pass |
| R01 | A logged in | POST /logout + CSRF | Session invalidated, context cleared |
| R02 | A logged out | Replay cookie A in second browser | Unauthenticated |
| R03 | A and B on same account (policy >=2) | Admin revokes all sessions | Both A and B lose access |
| R04 | Alice and Bob have separate sessions | Revoke Alice | Bob is unaffected |
| R05 | Alice account disabled | New login and old session cookie | New login blocked; old session follows designed revocation policy |
| R06 | Alice password changed | Replay remember-me cookie | Handled by dedicated revocation; do not assume |
| R07 | Alice web logout | Use independent valid Bearer JWT | May remain valid without token revocation |
| M01 | Two-pod app, shared store | Login at A, request at B | Same authentication/session state |
| M02 | Two-pod app, quota 1 | Concurrent Alice logins via A/B | Does not exceed cluster quota policy |
| M03 | Two-pod app, revoke Alice | Use cookie at both A/B | Both deny, no stale state |
| M04 | Redis store timeout | GET /me | Fail closed or per security policy; never auto-bypass |

**Testing technique:** fixation tests use one browser/session before and after login; concurrency tests use **two independent browsers/cookie jars**; revocation tests use **actually issued cookies** after logout/revocation; timeout tests need clocks/expiry at the proper layer. Never use `@WithMockUser` to prove login/session strategies: it only injects a mocked principal, bypassing credential verification and session lifecycles.

When a request is denied, assert **no side effects**: no payment changed, no private data read, no sensitive service called. Seeing HTTP 302 or 403 alone may be insufficient if the test was blocked by CSRF or redirected to a login page.

## 15. Troubleshooting: second logins, old sessions, and logout failures

| Symptom | Possible cause | Diagnostic steps |
| --- | --- | --- |
| Login A then B, both still access | `maximumSessions` not configured, registry not shared, or broken `equals`/`hashCode` | Check `SessionRegistry`, chain config, principal equality, cluster |
| Login B rejected even after A logged out | `SessionRegistry` still holds old session due to missing events or unhandled timeout | Check `HttpSessionEventPublisher` and session lifecycle |
| Second tab login not blocked | Two tabs share the same session | Use two independent cookie jars |
| Fixation test sees ID unchanged | Strategy disabled, custom filter skipped strategy, test compares same `MockHttpSession` ref | Snapshot ID before login, use real login |
| Old ID still works after login | Container/proxy/session store accepts old ID or test did not separate jars | E2E check stale ID and `Set-Cookie` |
| A logged out when B logs in despite wanting to block B | Using default evict-old policy | Switch to `maxSessionsPreventsLogin(true)` and retest |
| B login returns 302 so assumed passing | Form Login failure also redirects | Check principal/Location/authenticated result |
| A marked expired yet record remains in store | Spring has an expired state before destroyed | Send request with A so `ConcurrentSessionFilter` processes it |
| `invalidSessionUrl` reports expired right after logout | Browser still sends stale cookie | Cookie clearing + custom invalid strategy, real test |
| POST logout returns 403 | Missing/invalid CSRF | Send real CSRF token, never disable globally |
| Cookie deleted yet copied cookie still works | Server session not invalidated | Check store and `SecurityContextLogoutHandler` |
| Password changed yet old session still enters | No revocation/recheck policy for existing sessions | Revoke session/epoch; test all devices |
| Session drops while HTTP is active | Cookie Secure/SameSite/path mismatch, proxy, app restart, store TTL | Inspect browser `Set-Cookie`, server session repository |
| Session never expires while user is active | Only idle timeout exists, no absolute timeout | Implement separate absolute timeout if needed |
| Redis session uses `SESSION` cookie, code deletes `JSESSIONID` | Wrong cookie name | Check Spring Session cookie serializer |
| User revoked yet JWT still has access | Servlet session revocation does not affect JWTs | Separate introspection/denylist/token lifecycle |
| Configured `SessionCreationPolicy.STATELESS` with Form Login | Fails to save `SecurityContext` into `HttpSession` as expected | Separate filter chains / stateless API vs. web login |
| MockMvc timeout test does not expire with clock | `MockHttpSession` does not simulate natural container TTL | Embedded container/store test or custom `Clock` |
| Custom login POST returns 200 yet next request is anonymous | `SecurityContext` not saved, session strategy did not run | Check `SecurityContextRepository`, `SessionAuthenticationStrategy` |
| API returns HTML redirect when 401 expected | API uses `formLogin` entry point | Separate chains and entry points per auth scheme |

## 16. Implementation, monitoring, and conclusion checklist

- [ ] **Session fixation:** snapshot ID before login; perform real login; post-login ID differs, old ID has no privileges.
- [ ] **Concurrent sessions:** clear policy ("evict old" vs. "prevent new"); test with two independent cookie jars, same and different principals.
- [ ] **Registry lifecycle:** `HttpSessionEventPublisher` registered when using in-memory registry; proper principal `equals`/`hashCode`; events clean up stale sessions.
- [ ] **Timeout:** distinguish idle timeout, separate absolute lifetime, concurrency expired, and invalid ID; test boundaries/UX per mechanism.
- [ ] **Logout:** POST with CSRF, server invalidates, `SecurityContext` cleared; old cookie denied when replayed.
- [ ] **Revoke all:** mechanism exists to revoke all sessions issued to a user, handling races/other nodes while preserving other users' sessions.
- [ ] **Account changes:** disabled/locked, password change, role change have plans for existing sessions/remember-me and other tokens.
- [ ] **Cookies:** HTTPS, `Secure`/`HttpOnly`/`SameSite`, proper `Domain`/`Path`; never log or share `JSESSIONID`.
- [ ] **Spring 6.x:** custom authentication explicitly saves `SecurityContext` and runs `SessionAuthenticationStrategy`; do not copy v5 patterns blindly.
- [ ] **Cluster:** Spring Session + shared registry/principal index tested cross-node; do not rely solely on local `SessionRegistryImpl`.
- [ ] **API/JWT:** never equate servlet session revocation with JWT/access/refresh token revocation; state measure scope explicitly.
- [ ] **Tests:** MockMvc verifies login/session strategy, embedded-container E2E verifies cookies, Redis/database verifies cluster and expiry.
- [ ] **Observability:** track login successes/failures, session ID rotations, concurrent expirations, timeouts/revocations; log correlation IDs only, never session IDs/raw cookies.
- [ ] **Security incidents:** if session cookie theft is suspected, ability exists to revoke a specific user or all sessions and check alerts; update MFA policies if needed.

**Final takeaway:** **Session fixation** requires rotating IDs at the login boundary; **concurrent sessions** require a registry and a choice between "evict old" or "prevent new"; **session expiration** requires understanding idle/absolute timeouts and expired/destroyed states; **revocation** must happen server-side rather than only deleting cookies. An app that only passes a right-password login test has not proven session lifecycle safety.

### Official documentation and references

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — SessionManagementConfigurer.ConcurrencyControlConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/SessionManagementConfigurer.ConcurrencyControlConfigurer.html)
- [Spring Security 6.5 — SessionInformation (active / expired / destroyed)](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html)
- [Spring Security — SessionRegistryImpl](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/session/SessionRegistryImpl.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — MockMvc Authentication Tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Session — SpringSessionBackedSessionRegistry](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/security/SpringSessionBackedSessionRegistry.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
