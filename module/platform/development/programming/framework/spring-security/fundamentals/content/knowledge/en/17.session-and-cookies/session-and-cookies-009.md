# Multiple Sessions, Multiple Devices, and Access Revocation Requirements

> **Context:** Spring Security – fundamentals / **Sessions and cookies**. This lesson focuses on **Spring MVC/Servlet** applications using `HttpSession` and session identifier cookies, explaining how to control logins across multiple browsers/devices and revoke access when users log out, lose a device, change passwords, get locked out, or explicitly choose "log out other devices." An extended section contrasts Spring Session/Redis with JWT access tokens. Hands-on examples use Java 17, Spring Boot 3.5.0, and Spring Security 6.x.

## 1. What Is the Real Problem?

A user logs into the same account on their work laptop, phone, and personal computer. Each browser profile can hold its own session cookie; if the user does not log out, those sessions can remain usable.

Common requirements:

- **Allow multiple sessions:** A user may be logged in concurrently on several devices, such as up to two or five sessions.
- **Cap sessions:** Upon reaching the threshold, choose to *reject new sessions* or *allow the new session and expire an older one*.
- **Log out current device:** Destroy only the session attached to the current request.
- **Log out other devices:** Destroy/reject all other sessions while keeping the current session alive.
- **Log out all devices:** Destroy both the current session and all other sessions.
- **Emergency revocation:** When a stolen cookie is detected, password is changed, an account is locked, or an employee leaves, old sessions must lose access even if the cookies remain on those devices.
- **Visibility and auditing:** Show users last active timestamps, *approximate* device/location info, and what revocation actions occurred without exposing session IDs.

**Key takeaway:** Deleting a cookie in one browser **is not synonymous with** revoking all sessions of the same account. To cut off access on the server, the backend must invalidate session state or check a reliable revocation mechanism on incoming requests.

## 2. Session, Cookie, and "Device" Are Not the Same Concept

### 2.1. Cookies carry identifiers; authentication state lives on the server

A typical form login flow looks like this:

```mermaid
sequenceDiagram
    participant U as Browser A
    participant S as Spring Security
    participant Store as Session store
    U->>S: POST /login + credentials + CSRF token
    S->>S: Authenticate user
    S->>Store: Create/update SecurityContext in HttpSession
    S-->>U: Set-Cookie: JSESSIONID=...; HttpOnly; ...
    U->>S: GET /api/me + Cookie: JSESSIONID=...
    S->>Store: Look up session by ID, verify still valid
    Store-->>S: SecurityContext
    S-->>U: Permitted account information
```

In a Servlet container's default configuration, the cookie is commonly named **JSESSIONID**. It is a **session identifier**, not a password; however, an attacker capturing a still-valid ID can try to hijack the session, so treat this value as a **high-sensitivity authentication secret**. Never put the ID into URLs, logs, public telemetry, or return raw IDs from a device-listing API.

The backend stores `HttpSession`, which can hold `SecurityContext` managed by Spring Security. Using the session store, the server knows whether a session still exists, has timed out, was marked expired, or was deleted.

### 2.2. One user ≠ one session ≠ one device

| Concept | Example | Key point to remember |
| --- | --- | --- |
| User/account | alice | One identity can have multiple sessions |
| Session | Login session after a form login | Tied to server-side state and an ID in a cookie |
| Cookie | `JSESSIONID=...` in browser profile A | Browser sends it back so the server finds the session |
| Physical device | Laptop | Multiple profiles or browsers can mean multiple sessions |
| Tabs in same browser profile | Tab 1, Tab 2 | Usually share the same cookie/session |
| Remember-me token | Long-lived login-memory cookie | Can re-authenticate when session expires; needs separate revocation |
| JWT access token | Bearer token | If stateless auth, it is not an `HttpSession` |

A unique physical device cannot be reliably identified solely from `User-Agent` or IP: those values can collide, change, or be spoofed. When displaying "My Devices," clarify that these are **approximate recognized login sessions/devices**; if stable identification is needed, design explicit device registration with privacy risks evaluated.

## 3. Concurrent Session Policies in Spring Security

For **Spring MVC/Servlet**, Spring Security supports **concurrent session control**. Two common examples:

```java
// Configuration sample inside HttpSecurity.sessionManagement(...)
.maximumSessions(2)
.maxSessionsPreventsLogin(false)
```

Meaning:

- At most **two** login sessions are tracked per principal.
- When a third login succeeds, Spring Security can mark the least recently used older session as expired to make room for the new one. The old session is typically handled by `ConcurrentSessionFilter` on its next request.
- `maxSessionsPreventsLogin(false)` is the strategy that permits new logins and expires old sessions beyond the limit; it does not mean every browser gets pushed an immediate notification.

Conversely:

```java
// Reject new login when two active sessions already exist.
.maximumSessions(2)
.maxSessionsPreventsLogin(true)
```

Once the limit is reached, the system blocks a new login instead of evicting an old session. With form login, the app typically reports this via the authentication failure flow; do not assume every authentication mechanism returns the exact same HTTP status.

**Product decision:** For workplace apps, allowing new logins and revoking old sessions often prevents users from getting locked out when they forget to log out. For finance/high-sensitivity apps, you may require MFA and authorization confirmation before altering sessions. Session limits should be explicit business policies backed by clear tests, not arbitrary numbers.

### 3.1. SessionRegistry is where sessions are tracked

`org.springframework.security.core.session.SessionRegistry` provides methods such as:

- `getAllSessions(principal, includeExpiredSessions)`: finds registered sessions for a principal.
- `getSessionInformation(sessionId)`: looks up information for one session.
- `SessionInformation.getLastRequest()`: the most recently recorded request timestamp.
- `SessionInformation.expireNow()`: **marks the session as expired**, not an API that directly deletes cookies in every browser.
- `refreshLastRequest(sessionId)` and `registerNewSession(...)`: updates session lifecycle tracking.

A single-node deployment typically uses `SessionRegistryImpl`, keeping the registry in memory. When a session is destroyed by timeout/logout, `HttpSessionEventPublisher` publishes an event so the registry removes stale entries.

**Limitation:** per-JVM `SessionRegistryImpl` is not a distributed session store. If an app runs multiple instances without a shared session/registry mechanism, session A created on node 1 and session B on node 2 may not be visible consistently. A "two sessions" limit on a single node **does not automatically become a cluster-wide policy**.

### 3.2. How marking expired differs from deleting a session

Distinguish two styles of operation:

1. **Mark expired (`SessionInformation.expireNow()`):** Sets a flag in the registry. With the concurrent session filter, the next request for that session is detected and rejected/invalidated per the expiration strategy. An in-flight request may have already passed the check; users are not necessarily "kicked out" instantaneously over a push channel.
2. **Delete/invalidate server-side session:** Removes session data from the shared store via the session repository or invalidates the current session directly. Subsequent requests no longer have a valid `SecurityContext` to continue accessing resources. Still account for concurrent requests, caches, and in-flight work.

Consequently, product APIs should use accurate wording like **"marked other sessions for revocation; access will be blocked on their next request"** if calling only `expireNow()`, rather than promising sessions vanished everywhere at the instant of the 200 response.

## 4. Defining Access Revocation Requirements Before Writing Code

| Event | Usually desired scope | How to implement at the session layer |
| --- | --- | --- |
| User clicks "Log out" | Current session | Spring Security logout, invalidate session, clear cookie |
| Clicks "Log out other devices" | Account's sessions excluding current | Query registry/repository, expire/delete each other session |
| Clicks "Log out everywhere" | All sessions of the account | Revoke other sessions, then log out current session |
| Password changed due to suspected leak | Usually all prior sessions | Account-wide revocation and require re-authentication |
| Account disabled / role revoked | Any session no longer eligible | Revoke sessions/tokens + check current account/permissions |
| Stolen cookie detected | At least compromised session, possibly all | Invalidate server-side, audit, and rotate credentials if needed |
| Session timeout due to inactivity | One session | Server expires session per idle timeout |
| User switches devices, exceeding limit | One or more older sessions | Concurrent session control with explicit policy |

**Do not confuse logout with permission revocation:** If Alice's role is downgraded from ADMIN to USER yet the old `SecurityContext` still holds previous authorities, the app may keep trusting stale info until refresh/re-authentication. Revoking sessions or checking current version/permissions on critical requests is mandatory in systems requiring immediate permission updates.

## 5. Complete Example: Limiting Two Sessions and Revoking Others

We build a Spring Boot Servlet application with:

- `POST /login` handled by Spring Security form login;
- `GET /api/me` returning only the username, **never returning the session ID**;
- `GET /api/sessions` listing sessions currently tracked by the registry, containing only a current-session flag and last active timestamp;
- `POST /api/sessions/revoke-others` marking expired all sessions belonging to the **authenticated user** except the calling session;
- `POST /logout` using standard logout handlers, requiring a CSRF token when CSRF is enabled.

Demo account `alice` can log into at most two sessions in the same JVM. The code is for local/learning purposes, not a production device-management service.

### 5.1. Project structure

```text
multi-session-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/sessions/
    │   │   ├── MultiSessionApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── SessionController.java
    │   └── resources/application.properties
    └── test/java/demo/sessions/
        └── SessionRevocationTest.java
```

Use JDK 17+ and Maven 3.9+. The Spring Boot parent is pinned so the sample is easy to reproduce; in real usage, keep up with supported maintenance/patch releases.

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>multi-session-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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

### 5.3. Application entry point

`src/main/java/demo/sessions/MultiSessionApplication.java`:

```java
package demo.sessions;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultiSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(MultiSessionApplication.class, args);
    }
}
```

### 5.4. SecurityConfig: one registry, form login, and a two-session limit

`src/main/java/demo/sessions/SecurityConfig.java`:

```java
package demo.sessions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SessionRegistry registry) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(2)
                .maxSessionsPreventsLogin(false)
                .sessionRegistry(registry)
            )
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
            )
            .build();
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-demo"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-demo"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }
}
```

**Explanation of each component:**

- `formLogin` uses form-based authentication and stores `SecurityContext` in the session per standard config.
- `sessionFixation(...changeSessionId())` rotates the session ID after successful authentication; do not reuse an unauthenticated ID that someone else might control. This also helps mitigate session fixation risk.
- `maximumSessions(2)` allows up to two tracked sessions for the same principal.
- `maxSessionsPreventsLogin(false)` permits new sessions and marks excess older sessions as expired.
- `sessionRegistry(registry)` ensures Spring Security and the controller share the **exact same** registry.
- `HttpSessionEventPublisher` publishes session-destroyed events so registry data can be cleaned up when a session is invalidated or times out.
- `logout` keeps the behavior of invalidating the session and clearing the cookie of the **current browser**, without automatically invoking "log out other sessions."
- `anyRequest().denyAll()` avoids accidentally leaving unapproved endpoints open. Real configurations must add public assets, custom login pages, etc. per actual needs.

**Note:** in-memory `SessionRegistryImpl` is suitable **only for single-JVM** demos. In a cluster, use a shared session store and compatible registry such as Spring Session; session limits can break if each instance keeps its own registry. When using a custom `UserDetails` as principal, implement `equals()/hashCode()` consistently because `SessionRegistryImpl` keys by the principal.

### 5.5. API to list and revoke other sessions without leaking session IDs

`src/main/java/demo/sessions/SessionController.java`:

```java
package demo.sessions;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class SessionController {

    private final SessionRegistry registry;

    public SessionController(SessionRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }

    @GetMapping("/sessions")
    public List<SessionView> list(
            Authentication authentication, HttpSession current) {

        return registry.getAllSessions(
                    authentication.getPrincipal(), false)
            .stream()
            .map(info -> new SessionView(
                info.getSessionId().equals(current.getId()),
                info.getLastRequest().toInstant()))
            .toList();
    }

    @PostMapping("/sessions/revoke-others")
    public Map<String, Integer> revokeOtherSessions(
            Authentication authentication, HttpSession current) {

        int marked = 0;

        for (SessionInformation info : registry.getAllSessions(
                authentication.getPrincipal(), false)) {

            if (!info.getSessionId().equals(current.getId())) {
                info.expireNow();
                marked++;
            }
        }

        return Map.of("markedForExpiration", marked);
    }

    public record SessionView(boolean current, Instant lastRequest) {
    }
}
```

This pattern is intentionally designed to prevent **IDOR on session management**:

1. The controller never accepts the target username to revoke from the request; it always uses `authentication.getPrincipal()`.
2. It never returns `SessionInformation.getSessionId()` to the client, as that is a sensitive value capable of acting as a session credential.
3. When running "revoke others," only sessions belonging to the **current principal** are considered; it never accepts a client-supplied list of IDs.
4. Comparing the current session ID happens **on the server** to preserve the calling session.
5. `expireNow()` **marks for revocation**, hence the response field `markedForExpiration`, avoiding false claims of immediate deletion in every store.
6. This "list sessions" feature provides only `current` and `lastRequest`; if picking a specific session is needed, use a **public opaque handle that is not a session token**, mapped server-side and ownership-checked prior to revocation.

In real products, revoking all sessions is a sensitive action; require recent authentication/MFA for high-risk accounts, CSRF protection, and abuse prevention (rate limiting). Keep security audits and notify users if policy requires, without logging raw session IDs/cookies.

### 5.6. Session timeout configuration for the demo

`src/main/resources/application.properties`:

```properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

This is only a local setup over HTTP. Production must run **HTTPS** and enable **`Secure`** cookies, for example:

```properties
# Production environment over HTTPS:
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
```

For session cookies:

- **Secure**: browser sends the cookie only over HTTPS. Never disable in production.
- **HttpOnly**: restricts JavaScript from reading the cookie; does not block all XSS vectors, so XSS prevention is still mandatory.
- **SameSite=Lax/Strict/None**: helps restrict certain cross-site scenarios; `SameSite=None` requires `Secure`. Do not treat SameSite as a substitute for CSRF protection.
- **Path/Domain**: cookie scope should be the minimum required; watch out for apps sharing the same domain.
- **Timeout**: limits session inactivity; this lesson uses 30 minutes. If an "absolute maximum session duration" is required, enforce a separate policy because idle timeout is not absolute lifetime.

Depending on the system, the cookie name may be `JSESSIONID` or `SESSION` (e.g., Spring Session). When changing session stores, verify the actual cookie name instead of hardcoding the old name in browser cookie deletion.

## 6. Testing with Spring Security Test and MockMvc

The goal is not only verifying login succeeds, but also proving:

1. Two distinct sessions for the same account coexist simultaneously.
2. Each session uses its own cookie/identifier.
3. Calling "revoke others" from session B marks session A.
4. Session A is rejected on its **next request**, while session B keeps working normally.
5. Anonymous callers cannot invoke the session management API.

`src/test/java/demo/sessions/SessionRevocationTest.java`:

```java
package demo.sessions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionRevocationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void twoSessionsAndRevokeOthers() throws Exception {

        MvcResult firstLogin = mvc.perform(formLogin()
                .user("alice").password("alice-demo"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession first = (MockHttpSession)
            firstLogin.getRequest().getSession(false);

        MvcResult secondLogin = mvc.perform(formLogin()
                .user("alice").password("alice-demo"))
            .andExpect(authenticated())
            .andReturn();

        MockHttpSession second = (MockHttpSession)
            secondLogin.getRequest().getSession(false);

        assertThat(first).isNotNull();
        assertThat(second).isNotNull();
        assertThat(first.getId()).isNotEqualTo(second.getId());

        mvc.perform(get("/api/me").session(first))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/me").session(second))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(post("/api/sessions/revoke-others")
                .session(second)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.markedForExpiration").value(1));

        MvcResult expired = mvc.perform(
                get("/api/me").session(first))
            .andReturn();

        // Do not tie to a specific strategy's redirect/status.
        // Security invariant: old session can no longer succeed on GET /api/me.
        assertThat(expired.getResponse().getStatus()).isNotEqualTo(200);
        assertThat(expired.getResponse().getContentAsString())
            .doesNotContain("alice");

        mvc.perform(get("/api/me").session(second))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void anonymousCannotManageSessions() throws Exception {
        mvc.perform(get("/api/sessions"))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Explanation of points requiring caution:**

- `formLogin()` is a Spring Security Test request builder capable of executing the authentication flow in MockMvc; two logins do not pass the old session to the new request, so they create two separate `MockHttpSession` instances.
- `@AutoConfigureMockMvc` wires the security filter chain into the Spring Boot integration test.
- `with(csrf())` is required for the POST request to pass the CSRF filter; omitting it causes a 403 that only proves CSRF works, not that the session policy ran.
- The test intentionally **does not assert an exact HTTP status** for the expired session's request: the expired-session strategy might return a redirect or another error. The invariant is that the sensitive endpoint cannot be read and no payload leaks.
- With default form login, anonymous requests to the API may redirect to the login page (common in browser apps). If configuring an API entry point returning 401, adjust expectations to match the API contract.
- This simple suite uses an in-memory registry and simulates HTTP via MockMvc; to test `Set-Cookie` headers, real timeouts, sticky sessions, multiple nodes, and race conditions, write integration tests against the actual container/store/infrastructure.

**Run:**

```bash
mvn test
mvn spring-boot:run
```

With JDK 17+ and Maven installed, both test methods in `SessionRevocationTest` are expected to pass when using this exact configuration without port conflicts or interfering tests. This is an **expectation based on the example code**, not an executed build log in this lesson.

### 6.1. Manual testing with two browser profiles

1. Open browser profile A at `http://localhost:8080/login`; log in as `alice` / `alice-demo`.
2. Open an independent browser profile B or a truly private window with a separate cookie jar; log in with the same account.
3. Both can access `http://localhost:8080/api/me`.
4. In B, send a **POST** request to `/api/sessions/revoke-others` with a valid CSRF token. Do not just type the URL in the address bar because this operation uses POST and requires CSRF.
5. In A, refresh `/api/me`; the next request must be rejected or redirected to login. In B, refreshing must still succeed.

Opening two tabs in **the same browser profile** normally shares cookies/sessions rather than representing two logical devices. If testing with `curl`, manage **two independent cookie jars** and handle the CSRF/form flow properly; form login typically cannot be simulated completely with a single GET command.

## 7. Policies for "Log Out" and "Revoke Other Sessions"

### 7.1. Logging out the current session

Spring Security logout normally handles `POST /logout` (when CSRF is enabled), invoking logout handlers to clear the security context and invalidate `HttpSession`; custom controllers should never just delete cookies while ignoring server state. For a servlet app, configuration:

```java
// Configuration snippet inside HttpSecurity DSL.
.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
)
```

Setting `Set-Cookie` to expire cookies on the client can depend on Path/Domain/container. Always test in real browsers, especially behind reverse proxies and when multiple apps share a domain. Consider `Clear-Site-Data` for logout policies fitting the domain scope.

### 7.2. Revoke all: do not delete the current session before handling others

Sensible business flow:

```text
POST /account/logout-all
    -> re-authenticate/MFA if policy requires
    -> resolve principal from SecurityContext
    -> retrieve all valid sessions of principal
    -> revoke other sessions (mark expired or delete in store)
    -> logout/invalidate current session via LogoutHandler
    -> return confirmation and audit, never return raw session IDs
```

**Avoid** APIs that accept a username in the request body and delete all sessions for that username unless the caller has appropriate privileges. That can become a vulnerability letting users arbitrarily log others out. If admins are allowed to revoke another user's sessions, enforce strict role, tenant, reason, and audit checks.

### 7.3. Revoking only one chosen session

You can let users select an entry like "MacBook • active recently" in the UI, yet the API **should never return the raw `JSESSIONID`** as the selection ID. Use a metadata table:

```text
session_handle (random UUID, not a credential)
owner_user_id
session_id (secret, stored server-side only)
created_at
last_seen_at
device_label
revoked_at
```

On `POST /account/sessions/{handle}/revoke`:

1. Require an authenticated caller; check CSRF/MFA where appropriate.
2. Verify `handle` belongs to **that exact user/tenant**.
3. Look up the secret session ID **strictly on the backend**.
4. Revoke in the session store/registry and record an audit event.
5. Never expose other users' handles, session IDs, full IPs, or account metadata.

Even though a handle is not a credential, it must still be unpredictable and ownership-checked; an unpredictable ID does not replace authorization.

## 8. Spring Session + Redis for Multiple Instances

The `SessionRegistryImpl` example in section 5 only tracks sessions within a single JVM. In a load-balanced system running two or more backends, you need a **shared session store** and an **integrated registry** so the whole cluster sees the same sessions.

Spring Session can persist `HttpSession` in Redis. With Spring Boot, a common dependency setup is:

```xml
<!-- Add dependency to application pom.xml when deploying Redis -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
```

Spring Boot auto-configuration adds the Spring Session filter when store configuration meets conditions. Typical setup requirements include a running Redis server, securely managed credentials, a dedicated namespace, network TLS if supported, and a TTL policy.

**Illustrative configuration** (do not mix into the local demo unless Redis is running):

```properties
spring.data.redis.host=redis.internal.example
spring.data.redis.port=6379
spring.session.redis.namespace=myapp:session
server.servlet.session.timeout=30m
```

The hostname above is a **documentation example only**. Spring Session typically uses a cookie named `SESSION`; verify the actual cookie rather than assuming the demo's `JSESSIONID`.

### 8.1. SpringSessionBackedSessionRegistry

When using Spring Session's `FindByIndexNameSessionRepository`, Spring Security can integrate concurrent session control via a distributed registry:

```java
// Integration illustration code, not a standalone class runnable in the local demo.
@Autowired
FindByIndexNameSessionRepository<? extends Session> repository;

// Initialize SpringSessionBackedSessionRegistry with the appropriate repository.
// Then pass the instance as SessionRegistry to HttpSecurity.sessionManagement(...).
```

In a real project, declare generic types and beans matching the concrete session repository (e.g., Redis `IndexedSessionRepository`) and consult the docs for your exact version. **Do not keep a local `SessionRegistryImpl` while assuming the Spring Session cookie magically makes all registry state cluster-wide**.

Spring Session provides ways to find sessions by indexed username and delete by ID in the shared store. Pattern checking ownership before deletion:

```java
// Pseudocode, repository has type FindByIndexNameSessionRepository<S>.
Map<String, S> owned = repository.findByPrincipalName(currentUsername);
for (String id : owned.keySet()) {
    if (!id.equals(currentSessionId)) {
        repository.deleteById(id);
    }
}
```

The snippet above is **Java pseudocode**, not a standalone compilable file: you must declare generic `S extends Session`, the repository, and the authenticated username from a trusted source. Never delete an ID without verifying it belongs to the right principal. With Spring Session, deleting a session directly from the store prevents subsequent requests from finding valid state; in-flight requests still need safe handling if sensitive operations happen concurrently.

### 8.2. Consistency, timeouts, and reliability

- **Multiple nodes:** test login through node A, request through B, revoke through C, then request again through A/B. Do not test only sticky sessions on a single instance.
- **Session index:** finding "all sessions of a principal" relies on the proper index in the store. If changing serializers or authentication procedures, ensure the username/owner index stays updated.
- **TTL and cleanup:** an expired session is not necessarily physically deleted at the exact same instant; understand Redis cleanup/TTL mechanics and expiration events.
- **Race conditions:** a new login and revoke-all occurring simultaneously can create a new session right after the list to revoke was fetched. For strict requirements (security incidents), use an **account session epoch/version** or generation mechanism so every request compares against a central revocation marker.
- **Failure modes:** when the session/permission store is unavailable, never silently treat a session as valid just because a local cache still holds data; define fail-closed behavior suited to your system's sensitivity and availability needs.
- **Concurrency cap:** `maximumSessions` limits concurrent sessions at login time; it is **not** the sole security boundary replacing per-request revocation policies.

## 9. Stronger Revocation Using Session Version / Epoch

For requirements like "when an account is locked or password changed, all devices lose access on the very next request," you can use a server-managed **version** or timestamp:

```text
User:
    id = alice
    securityVersion = 9

Session:
    principal = alice
    issuedSecurityVersion = 8

Request:
    session exists AND
    user.enabled == true AND
    session.issuedSecurityVersion == user.securityVersion
      -> accept
    else
      -> deny and invalidate
```

When a revoke-all is needed, increment `securityVersion` in a consistent data store. Any session carrying an older version is rejected when the next request is checked. This is a **design pattern**, not a Spring Security feature that turns itself on when you add a field to an entity. You must place the filter/authorization check in the right spot, pick a reliable version lookup source, and design cache invalidation/acceptable propagation latency.

Advantage: reduces the risk of missing a new session created concurrently with listing and deleting. Trade-off: every sensitive request needs the current version; if cached too long, "immediate revocation" becomes an empty promise.

If you only want to revoke **one** session while keeping others, you need per-session state (revocation list/session store) or per-device epochs; an account-wide version logs out everyone.

## 10. Special Case: JWT Access Tokens and Refresh Tokens

Do not confuse **server-side sessions** with **stateless JWTs**:

| Property | HttpSession + cookie | Self-verifying signed JWT access token |
| --- | --- | --- |
| Primary auth data | Server-side session | Signed claims inside the token |
| Cookie/browser | Session ID cookie | May be sent via Bearer header or cookie depending on design |
| Revoke one session | Delete/expire session on server | Cannot remotely erase an issued JWT if verifier checks only signature/expiry |
| Revoke all devices | Find sessions or bump version | Revoke refresh tokens + denylist/version/introspection for access tokens if immediate needed |
| Multi-node | Needs shared store or suitable model | Can be stateless, yet strong revocation needs extra state |
| Per-request check | Read session/security context | Verify signature, issuer, audience, expiry, and matching permissions |

If a JWT access token is still within its validity window and the resource server **checks only signature and `exp`**, "logging out" in one browser or deleting the refresh token at the authorization server **does not immediately invalidate old access JWTs**. Options:

1. **Short-lived access tokens** and refresh token rotation: shrinks the exposure window of leaked tokens, though it does not revoke an access token at the exact instant of logout.
2. **Refresh token revocation** at the authorization server per session/device/grant; controls ability to obtain new access tokens. Handle replay and rotation properly.
3. **Denylist of `jti` / token IDs**, or **per-user `tokenVersion`/security epoch** checked by resource servers on every request: enables near-instant revocation if distributed state/caching has acceptable latency.
4. **Token introspection** for opaque tokens or stateful validation architectures: the authorization server can report a token inactive, trading network call cost and HA requirements.
5. **OIDC logout/back-channel logout** in SSO ecosystems: logging out of the IdP does not automatically guarantee every app's local session and JWT are cleared unless the corresponding mechanisms/events are fully implemented and propagated.

**Principle:** For policies requiring rapid revocation, define the **maximum acceptable revocation latency** and how each resource server checks revocation. Never claim "deleting the refresh token = all access tokens are immediately invalid" when that is false.

## 11. Lost Devices, Password Changes, and Session Hijacking Incidents

### 11.1. Lost device

When a user reports a lost phone:

1. Protect the current account with MFA/re-authentication where feasible.
2. Revoke the potentially exposed session or all sessions, depending on risk and ability to identify the exact device.
3. Revoke related remember-me/refresh tokens and reset "trusted/remembered device" channels if needed.
4. Inspect anomalous activity, recent login events, and changed permissions.
5. Clearly communicate which sessions were revoked, approximate timestamps, and next steps.

If an attacker still has a **valid password**, they can log back in after being kicked out. Therefore, session revocation often must accompany password resets/MFA and locking compromised credentials.

### 11.2. Password change

There is no universal guarantee that "changing a password automatically invalidates all logged-in sessions" across every Spring Security setup. You must choose and implement the product behavior:

- Keep the current session and revoke all other sessions?
- Revoke the current session too and require re-login?
- Require MFA and rotate remember-me/refresh tokens?
- Bump a security version so all old sessions/tokens become invalid?

If the app includes payment, money transfer, or admin privilege granting steps, **fresh authentication** may still be required even when the session is allowed to continue.

### 11.3. Disabled account or role change

An authenticated session may hold a `SecurityContext` with old authorities. Simply updating `user.enabled` or roles in the database without revoking sessions or re-evaluating current permissions allows subsequent requests to continue running under the old context. Your design needs:

- Revocation of sessions/tokens for disabled users;
- Critical routes/operations checking live status or security version at the right moment;
- Monitoring, auditing, and tests after role changes to ensure stale authorities are not honored.

### 11.4. Boundary between revocation and in-flight requests

If a money transfer request has already passed authorization and an admin revokes the session at the same moment, deleting the session **does not automatically roll back** the executing payment. For ultra-sensitive actions, check permissions at the final commit/write point with proper transactions, idempotency, and state guards. Never promise "revoking means every in-progress task is aborted."

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Clearing browser cookie and calling it all-device logout | Other sessions remain alive on the server | Revoke sessions in the store, scoped to the principal |
| Returning raw session IDs in a "devices" API | Exposes highly sensitive auth material | Use a separate non-credential handle; never log raw IDs |
| Using `SessionRegistryImpl` across multiple nodes without shared state | Session limits/revocation diverge per node | Spring Session + shared registry or equivalent distributed design |
| Calling `expireNow()` and claiming session data is deleted immediately | Registry only marks it expired | Distinguish marking expired from delete/invalidate; test next request |
| Accepting `username` or `sessionId` in request body without authorization | Users can revoke other users' sessions | Resolve principal from SecurityContext; verify ownership before deleting |
| Treating two tabs in the same browser as two devices | Tabs usually share cookies | Test with two independent cookie jars/profiles |
| Disabling CSRF when using cookie auth in browsers | Forged requests can revoke sessions or trigger actions | Keep proper CSRF, test with `csrf()` |
| Capping concurrent sessions with no emergency revocation mechanism | Cannot respond to lost-device incidents | Implement logout-others/all and session/token versioning |
| Using `User-Agent` as the sole permission identifier | Easily spoofed or changed | Display metadata is informational only; trust server-side checks |
| Not updating registry after timeout/logout | Active session count drifts | `HttpSessionEventPublisher` or matching lifecycle integration |
| Confusing `maxSessionsPreventsLogin(true)` with expiring old sessions | That strategy blocks new logins | Choose the intended product behavior |
| Revoking refresh token and claiming JWT access tokens died instantly | Access tokens remain accepted until `exp` if stateless | Denylist/introspection/versioning or short TTLs |
| Changing password without re-checking authorities/sessions | Old sessions can keep using stale privileges | Revoke or check user security epoch/roles |
| Renaming cookie from `JSESSIONID` to `SESSION` while logout still deletes old name | Browser cookie may linger | Verify actual cookie name and invalidate server-side |
| Session cookie missing `Secure`/`HttpOnly` | Higher cookie exposure risk | Configure properly over HTTPS; guard against XSS/CSRF |
| Testing only locally on one JVM | Misses multi-node sync bugs | Integration test through a load balancer and Redis |
| Logging `Cookie` header or session ID | Leaks credentials and raises hijacking risk | Redact/omit credentials; audit events instead of raw token values |

## 13. Recommended Test Matrix for Real Projects

| Test case | Expected |
| --- | --- |
| Browser A and B log into the same account | Two independent sessions, same principal |
| Open another tab in browser A | Usually shares the same session; session count does not rise |
| Limit 2, third login, expire-old mode | Old session loses access on its next request |
| Limit 2, prevent-new mode | New login is rejected; old sessions remain valid |
| Logout in browser A | A loses access; B keeps working if policy is current-only |
| Revoke others in browser B | A loses access, B remains valid |
| Revoke all | Both A/B and the calling session lose access |
| POST revoke missing CSRF token | Rejected per CSRF policy; no accidental revocation |
| Bob tries to revoke Alice's session | Rejected; Alice is unaffected |
| Session expires from idle timeout | Old `SecurityContext` cannot be used |
| Password change under revoke-all policy | Old tokens/sessions lose access within SLA |
| Disabled user | Cannot access via old session |
| Role change | Revoked privilege not retained beyond SLA |
| Revoke on node A, call again via B/C | Access is consistently revoked |
| Stolen cookie copied and replayed after revoke | Access denied; audited if required |
| Unexpired JWT after refresh revocation | Known bounded window or blocked by denylist/introspection |
| In-flight request during revocation | Does not commit unauthorized operations per business policy |

For distributed session stores, test **stress/race conditions**: two concurrent logins near the limit; revoke-all racing with a new login; Redis disconnect; TTL expiration; delayed invalidation events; session present in index without data and vice versa. Base conclusions on defined **security invariants**, not just counting HTTP 200s.

## 14. Architecture and Operations Checklist

- [ ] Identify whether the app uses **`HttpSession`**, Spring Session, or OAuth2/JWT; never apply the wrong revocation model.
- [ ] Define maximum sessions per user/tenant and choose "new login replaces old" vs. "prevent new."
- [ ] Explicitly define behavior for logout-current, logout-others, logout-all, password change, and disabled accounts.
- [ ] Distinguish **session** from **physical device**; never use IP/User-Agent as a security key.
- [ ] Never expose session IDs/cookies/tokens in responses, logs, URLs, or client-facing device lists.
- [ ] Keep CSRF for cookie-based browser flows, HTTPS transport encryption, and proper `Secure`/`HttpOnly`/`SameSite` cookies.
- [ ] If single-JVM, configure registry and lifecycle events; if clustered, use a proper shared session store/registry.
- [ ] If immediate revocation is needed, define per-request revocation checks and cache/propagation SLAs.
- [ ] Check ownership before revoking a session; cross-account admin actions require role/tenant/audit enforcement.
- [ ] Revoke remember-me/refresh tokens separately when policy requires; never assume auxiliary tokens vanish automatically.
- [ ] Test multiple browser profiles, multiple nodes, timeouts, and race conditions; verify **users cannot revoke each other's sessions**.
- [ ] For sensitive in-flight operations, verify permissions/transaction preconditions at commit/write time.
- [ ] Record audit entries with actor, action, outcome, timestamp, and redacted handles; never store raw secrets.
- [ ] Verify login/logout/session-list/revoke with automated integration tests before release.

## 15. Knowledge Self-Check

1. **If Alice logs in across two tabs in the same Chrome window, are they definitely two sessions?** No. Two tabs in the same profile usually share cookies; a session is not synonymous with a tab or physical device.
2. **What does `maximumSessions(2).maxSessionsPreventsLogin(false)` mean?** Allows up to two tracked sessions; logins exceeding the limit can expire an older session to make room for the new one.
3. **Does logging out on a laptop automatically log out the phone?** No under default current-session logout; doing so requires revoking other sessions/tokens.
4. **Does `SessionInformation.expireNow()` immediately delete cookies from other browsers?** No. It marks the session expired in the registry; the next request detects and handles it per the filter/strategy.
5. **Why shouldn't `sessionId` be returned in a device list?** Because the ID is a credential that can be replayed to hijack a session if leaked; use an opaque handle and enforce ownership checks.
6. **Does `SessionRegistryImpl` running across three nodes automatically share registry state?** No. A distributed store/registry or equivalent consistent architecture is required.
7. **If only the refresh token is revoked, are already-issued access JWTs still valid?** Potentially until expiration if the resource server verifies only signature/expiry; early revocation requires additional state.
8. **Why might changing a password not be enough to invalidate old sessions?** The `SecurityContext` inside an existing session can remain valid; the system must actively revoke sessions or check a security version/updated permissions.
9. **Does a revoke POST returning 403 for missing CSRF prove the revocation code works?** No. You must test with valid CSRF to actually execute the revocation logic.
10. **If a session is revoked while a write command is executing, does that work automatically roll back?** No. Enforce authorization at appropriate business boundaries, along with transactions and race-handling strategies.

## 16. Official References

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): concurrent session control, `maximumSessions`, `maxSessionsPreventsLogin`, lifecycle, and session fixation.
- [Spring Security — Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): logout handlers, session invalidation, and cookie deletion.
- [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF for browser/cookie-based authentication.
- [Spring Session — Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html): `SpringSessionBackedSessionRegistry` and distributed concurrent session control.
- [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): integrating Redis session store and cookies.
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html): indexing by principal and ownership-checked single-session revocation.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): protecting session identifiers, cookies, and session lifecycles.
