# SessionRegistry, HttpSessionEventPublisher, and Active Session Tracking

> **Module:** Spring Security - authentication. **Group:** Session Management. This lesson applies to **Spring Security Servlet 6.x**, demonstrated with **Java 17 + Spring Boot 3.3.5**. The goal is to understand accurately how `SessionRegistry` records logged-in sessions, how `HttpSessionEventPublisher` forwards lifecycle events from the Servlet container, and how to observe/limit active sessions without confusing "a record exists" with "the user is definitely online."

## 1. Why Do We Need SessionRegistry?

An account may be logged in from two browsers, a laptop, and a phone. When a user clicks "log out all devices," the security layer needs to check which sessions exist; when the product requires each account to log in from only one place, the system needs to limit **concurrent sessions**.

Three concepts must be separated:

1. **`HttpSession`**: the HTTP session object managed by the Servlet container; usually referenced by the browser via the `JSESSIONID` cookie. It holds application attributes and may hold `SecurityContext`, depending on configuration.
2. **`SecurityContext` / `Authentication`**: the authenticated identity used by Spring Security for authorization. The context can be stored/restored in `HttpSession` via `SecurityContextRepository`.
3. **`SessionRegistry`**: an index of **session IDs** associated with registered **principals**; provides `SessionInformation` (last request timestamp, expired flag). The registry is **not** a store for passwords, cookies, full session contents, or `SecurityContext`.

A record in the registry does not mean a real person has the page open at that exact moment. An "active session" in this context is typically a session **tracked by the registry, not yet marked expired, and not yet notified as destroyed**; the data also depends on lifecycle events, timeouts, filter execution paths, and JVM scope.

### Distinguishing the Components

| Component | What It Holds | Who Updates It |
| --- | --- | --- |
| Servlet `HttpSession` | ID, attributes, container-managed lifetime | Container, application |
| `HttpSessionSecurityContextRepository` | `SecurityContext` preserved across requests when using sessions | Authentication mechanism, logout |
| `SessionRegistryImpl` | Principal → session IDs, `SessionInformation` | `RegisterSessionAuthenticationStrategy`, `ConcurrentSessionFilter`, destroy/id-change events |
| `HttpSessionEventPublisher` | Not a data store; an **event-bridging listener** | Servlet container calls it on session create/destroy/ID change |
| `ConcurrentSessionControlAuthenticationStrategy` | Checks login limits on successful authentication | Authentication mechanism invokes strategy |
| `ConcurrentSessionFilter` | Refreshes last activity time; handles sessions marked expired | Security filter chain on subsequent requests |

**The right mindset:** the session registry is an **index for session control**, does not replace the container's session storage, and does not guarantee a global online picture when the app runs across multiple instances.

## 2. Key Methods of SessionRegistry

The `org.springframework.security.core.session.SessionRegistry` interface has the following APIs:

| API | Meaning | Notes |
| --- | --- | --- |
| `getAllPrincipals()` | Retrieves known principals in the registry | Not automatically all users in the database; should not be exposed publicly |
| `getAllSessions(principal, false)` | Retrieves sessions not marked `expired` for a principal | Destroyed sessions must be removed via events; not a real-time presence metric |
| `getAllSessions(principal, true)` | Retrieves sessions including those **marked expired** but not yet removed | Excludes sessions **already destroyed/removed** |
| `getSessionInformation(sessionId)` | Retrieves metadata by ID, or `null` if absent | ID is sensitive data; avoid exposing in APIs/logs |
| `registerNewSession(sessionId, principal)` | Registers a session in the index | Usually called by strategy on successful login; do not call for unauthenticated clients |
| `refreshLastRequest(sessionId)` | Updates the latest request timestamp | Does not necessarily reflect every UI action or WebSocket activity |
| `removeSessionInformation(sessionId)` | Removes an existing record from the registry | **Not** equivalent to `HttpSession.invalidate()` |
| `SessionInformation.expireNow()` | Marks the record as expired | **Does not** immediately destroy `HttpSession`; handled when the session is checked on its next request |

Example of reading status — an **illustrative Java snippet** only, not a standalone application:

```java
Object trustedPrincipal = authentication.getPrincipal();
List<SessionInformation> active =
        sessionRegistry.getAllSessions(trustedPrincipal, false);

for (SessionInformation info : active) {
    boolean expired = info.isExpired();
    Date lastSeen = info.getLastRequest();
    // Do not include raw sessionId in public responses.
}
```

`Authentication` here must be a **server-authenticated** result; never take an arbitrary userId from a query parameter and use it to list another person's sessions.

### Critically Important: Principal and `equals/hashCode`

`SessionRegistryImpl` uses the principal as a key in an in-memory map. If a custom `UserDetails` lacks stable `equals()` / `hashCode()`, the same person logging in multiple times with distinct object instances can be treated as different principals. Concurrent session limits can therefore malfunction.

- A stable identifier is typically an internal user ID or an immutable principal with valid `equals/hashCode`.
- Do not use mutable data (changing roles, display name, random object identity) as the comparison key without control.
- In multi-tenant systems, the identity key must include **tenant ID** when a username can repeat across organizations.

`UserDetails` built with `org.springframework.security.core.userdetails.User` in the demo has suitable identity comparison; if you write your own implementation, test the equality rules separately.

## 3. Lifecycle of a Session: Login, Access, Expiration, Logout

```text
Browser sends POST /login + username/password + CSRF
   |
   v
UsernamePasswordAuthenticationFilter
   |-- AuthenticationManager -> AuthenticationProvider
   |-- valid credentials -> trusted Authentication
   v
Spring Security's SessionAuthenticationStrategy
   |-- checks maximumSessions(...)
   |-- prevents session fixation (usually changeSessionId)
   |-- registers sessionID / principal with SessionRegistry
   v
SecurityContextRepository saves SecurityContext into HttpSession
   |
   +--> SessionRegistryImpl:
   |      principal alice -> {session-id-1}
   |
   v
GET /api/sessions with session cookie
   |-- Filter retrieves SecurityContext
   |-- ConcurrentSessionFilter refreshLastRequest(session-id-1)
   |-- Controller reads SessionRegistry (metadata only)
   v
Response: activeCount = 1
   |
   +-- Logout / HttpSession timeout / explicit invalidate:
   |      Servlet container fires sessionDestroyed
   |      HttpSessionEventPublisher translates to Spring event
   |      SessionRegistryImpl removes session ID
   |
   +-- When registry marks expireNow():
          SessionInformation.expired = true
          ConcurrentSessionFilter detects on next request
          -> handles expired session, invalidates session (per strategy)
          -> publisher/event removes record
```

### 3.1. `RegisterSessionAuthenticationStrategy`

When logging in via a mechanism configured by Spring Security to support concurrency (such as `formLogin` in the demo), the `SessionAuthenticationStrategy` chain usually includes the session-limit check strategy, session fixation protection, and `RegisterSessionAuthenticationStrategy` to add the newly logged-in session ID to the registry.

**Merely creating a `SessionRegistryImpl` bean does not make every login appear in the list.** If you write a custom JSON-login controller and call `AuthenticationManager.authenticate` directly, you must design/apply an appropriate `SessionAuthenticationStrategy` and persist `SecurityContext` via the repository. Spring Security 6 does not use `SessionManagementFilter` by default to auto-detect success on every request.

### 3.2. `ConcurrentSessionFilter` and `lastRequest`

When concurrent session control is configured, Spring Security can use `ConcurrentSessionFilter` to update the activity timestamp in `SessionInformation`. When the filter sees a record **marked expired**, it runs the expired-session strategy (`SessionInformationExpiredStrategy`) and performs logout/invalidation per the configured flow.

Therefore:
- `lastRequest` is an **HTTP activity timestamp recorded by the filter**, not a sign that a human is sitting in front of the screen.
- A closed tab, lost network, or idle client sending no further requests can leave the record in the registry until a timeout/destroy event occurs.
- `expireNow()` only sets a flag; before the next request, the container's `HttpSession` may not be invalidated immediately.
- If you need immediate revocation of all tokens/devices, you need an invalidation mechanism matching the **credential type**, such as invalidating the actual session and/or a token denylist per your architecture.

### 3.3. What Role Does `HttpSessionEventPublisher` Play?

`HttpSessionEventPublisher` is Spring Security's Servlet listener. It receives `HttpSession` lifecycle events from the **Servlet container** and publishes corresponding events to the Spring application context, including session created/destroyed events and session ID changes when notified by the container.

`SessionRegistryImpl` is a listener for Spring session events, specifically handling **session destroyed** to delete entries. If you **fail to register the publisher** when using the in-memory registry with container sessions, information for timed-out or logged-out sessions may not be cleared in time, causing the system to think an account still holds a login slot.

Event chain:

```text
HttpSession.invalidate(), logout, or container timeout
     -> Servlet HttpSessionListener.sessionDestroyed(...)
     -> HttpSessionEventPublisher
     -> Spring HttpSessionDestroyedEvent
     -> SessionRegistryImpl (ApplicationListener)
     -> removeSessionInformation(sessionId)
```

**Do not confuse:** the publisher does not track "online users" itself; it does not store a session table. And having only the publisher without configuring `SessionRegistry`/concurrency strategy does not automatically create session management. Register the listener **once**; avoid adding both a bean and a second servlet listener registration for the same instance.

## 4. Runnable Project: Tracking Sessions and Blocking Concurrent Logins

### 4.1. Demo Objectives

- One user `alice`, demo password `demo-pass123`, role `USER`.
- Login via the default form provided by Spring Security (`GET /login`, `POST /login`).
- `SessionRegistryImpl` records successful logins.
- `maximumSessions(1).maxSessionsPreventsLogin(true)`: rejects a second login while the first session is still valid.
- `HttpSessionEventPublisher` informs the registry about actual logout/timeout/invalidated sessions.
- `GET /api/sessions` returns **the number of sessions the registry considers active** and limited metadata for **the currently logged-in user only**; it does not return session IDs or list the entire system.

Structure:

```text
session-registry-demo/
├── pom.xml
├── src/main/java/com/example/sessions/SessionRegistryDemoApplication.java
└── src/test/java/com/example/sessions/SessionRegistryDemoApplicationTests.java
```

**`pom.xml`**:

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
    <artifactId>session-registry-demo</artifactId>
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

### 4.2. `src/main/java/com/example/sessions/SessionRegistryDemoApplication.java`

```java
package com.example.sessions;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@SpringBootApplication
public class SessionRegistryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionRegistryDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-pass123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    // Boot registers the Servlet listener bean; do not register it again in web.xml.
    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SessionRegistry registry) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/api/sessions").authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .maximumSessions(1)
                .maxSessionsPreventsLogin(true)
                .sessionRegistry(registry)
            );

        return http.build();
    }

    public record SessionSummary(boolean current, String lastRequestUtc) {}

    public record SessionOverview(
            String username,
            int activeCount,
            List<SessionSummary> sessions
    ) {}

    @RestController
    static class SessionController {
        private final SessionRegistry registry;

        SessionController(SessionRegistry registry) {
            this.registry = registry;
        }

        @GetMapping("/api/sessions")
        SessionOverview currentUserSessions(
                Authentication authentication,
                HttpServletRequest request) {

            HttpSession httpSession = request.getSession(false);
            String currentId = httpSession == null ? null : httpSession.getId();

            // This principal has already been authenticated by Spring Security.
            // Do not take username/sessionId from client-supplied query parameters.
            List<SessionSummary> summaries = registry
                .getAllSessions(authentication.getPrincipal(), false)
                .stream()
                .map(info -> new SessionSummary(
                    currentId != null && currentId.equals(info.getSessionId()),
                    info.getLastRequest().toInstant().toString()
                ))
                .toList();

            // Do not include raw session IDs or credentials in the JSON response.
            return new SessionOverview(
                    authentication.getName(),
                    summaries.size(),
                    summaries
            );
        }
    }
}
```

### 4.3. Why Are the Configuration Lines Above Important?

1. `@Bean SessionRegistry` provides a **single** registry shared by both concurrent-session control and the monitoring endpoint. If each place calls `new SessionRegistryImpl()`, the data will not match.
2. `@Bean HttpSessionEventPublisher` registers the bridge between the Servlet container and Spring events. When the real session is destroyed, `SessionRegistryImpl` is notified to delete the record.
3. `formLogin(Customizer.withDefaults())` uses the standard authentication filter, supporting applying session authentication strategies upon successful login. This demo **does not write a custom login Controller** and forget to call them.
4. `maximumSessions(1)` sets a limit of one logged-in session per principal. `maxSessionsPreventsLogin(true)` chooses to **reject subsequent logins**, rather than marking the old session expired. Do not confuse the limit with the overflow policy.
5. `sessionRegistry(registry)` makes the concurrency strategy and `ConcurrentSessionFilter` reference the same registry. Do not manipulate the principal → IDs map manually.
6. `GET /api/sessions` requires an authenticated user, uses `authentication.getPrincipal()` to look up **their own** sessions, and publishes only counts/last-request times. Admin APIs listing all principals need explicit authorization to avoid exposing session IDs or other users' data.
7. Spring Security keeps CSRF enabled by default when using form login. Browsers using the framework-generated `/login` form send the CSRF token; do not disable CSRF just to make the demo run.
8. Default session fixation protection can rotate the session ID after login. The registry must track the new ID; the publisher also forwards ID-change events from the Servlet container.

The demo runs inside **one JVM** with an in-memory registry. It does not demonstrate a multi-node system managing sessions together, and the endpoint reports the number of sessions the registry believes are not expired/destroyed — not a real-time presence system.

## 5. Hands-On Browser Walkthrough

Start the app:

```bash
mvn spring-boot:run
```

1. Open `http://localhost:8080/login` in **browser A**, and log in with `alice` / `demo-pass123`. Upon success, Spring Security redirects to the target page by default. You do not necessarily need a custom home page; having no app content at `/` does not make login fail.
2. In the **same browser A**, visit `http://localhost:8080/api/sessions`. Expected JSON has `"username":"alice"`, `"activeCount":1`, and one entry with `"current":true`. The `lastRequestUtc` timestamp changes with actual activity.
3. Open **browser B in an independent profile** (a completely separate cookie jar), and try logging in with the **same alice account**. Because of `maxSessionsPreventsLogin(true)`, this login is rejected, typically redirecting to `/login?error` instead of creating a second login session.
4. Return to browser A and reload `/api/sessions`: session A still exists, and `activeCount` is still 1 (assuming no timeout/logout yet).
5. Log out in A using Spring Security's valid logout form/flow (POST `/logout` with CSRF). When the container destroys the session, the publisher notifies the registry. After logging out, visiting `/api/sessions` will prompt for login again.
6. Afterward, B can log in successfully with the alice account (once the destroy event has updated the registry); if still blocked, check publisher registration, principal equality, real timeouts, and lifecycle synchronization.

Example JSON — **illustrative values only**, not a fixed timestamp definition:

```json
{
  "username": "alice",
  "activeCount": 1,
  "sessions": [
    {
      "current": true,
      "lastRequestUtc": "2026-01-01T08:30:00Z"
    }
  ]
}
```

The timestamp is an example in UTC ISO-8601 format; actual timestamps vary. Never expose real session IDs in the UI or log files, as a session ID is a credential that can be abused if leaked.

**Distinguish status codes:** when `formLogin` fails due to exceeding the session limit, the result is typically a redirect to the login page with an error indicator, not necessarily HTTP 401 JSON. With custom APIs you build, responses must be explicitly designed via success/failure handlers.

## 6. Testing with MockMvc and Testing the Registry API

Create `src/test/java/com/example/sessions/SessionRegistryDemoApplicationTests.java`:

```java
package com.example.sessions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionRegistryDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry registry;

    @Autowired
    UserDetailsService userDetailsService;

    @Test
    void tracksFirstLoginAndBlocksSecondOne() throws Exception {
        // spring-security-test's formLogin() submits a valid CSRF token.
        MvcResult first = mvc.perform(
                    formLogin().user("alice").password("demo-pass123"))
                .andExpect(authenticated().withUsername("alice"))
                .andReturn();

        MockHttpSession browserA =
                (MockHttpSession) first.getRequest().getSession(false);
        assertNotNull(browserA);

        Object alice = userDetailsService.loadUserByUsername("alice");
        assertEquals(1, registry.getAllSessions(alice, false).size());

        mvc.perform(get("/api/sessions").session(browserA))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.activeCount").value(1))
                .andExpect(jsonPath("$.sessions[0].current").value(true));

        // Different browser: no old session attached. Policy blocks the second login.
        mvc.perform(formLogin().user("alice").password("demo-pass123"))
                .andExpect(unauthenticated());

        // Session A is still allowed to access.
        mvc.perform(get("/api/sessions").session(browserA))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.activeCount").value(1));
    }

    @Test
    void expiredMarkerIsNotTheSameAsRemovingSessionRecord() {
        SessionRegistryImpl isolated = new SessionRegistryImpl();
        isolated.registerNewSession("test-session-1", "alice");

        SessionInformation info =
                isolated.getSessionInformation("test-session-1");
        assertNotNull(info);
        assertFalse(info.isExpired());
        assertEquals(1, isolated.getAllSessions("alice", false).size());

        // Mark expired: entry still exists when includeExpired = true.
        info.expireNow();
        assertTrue(info.isExpired());
        assertEquals(0, isolated.getAllSessions("alice", false).size());
        assertEquals(1, isolated.getAllSessions("alice", true).size());
        assertNotNull(isolated.getSessionInformation("test-session-1"));

        // Remove registry entry: not found even when includeExpired = true.
        isolated.removeSessionInformation("test-session-1");
        assertNull(isolated.getSessionInformation("test-session-1"));
        assertEquals(0, isolated.getAllSessions("alice", true).size());
    }
}
```

Run:

```bash
mvn test
```

What the tests **prove**:
- Successful form login is registered in `SessionRegistry` and subsequent requests can read info for the authenticated principal.
- With `maximumSessions(1).maxSessionsPreventsLogin(true)`, the same username logging in from a second client is rejected, while the old session remains usable.
- `expireNow()` is a **flag** in the registry; it differs from `removeSessionInformation(...)`.

What the tests **do not prove**: whether a real Servlet container fires events upon timeout, and whether `HttpSessionEventPublisher` forwards events in the deployed environment. `MockHttpSession` is a simulation and cannot replace integration tests running a real server waiting for timeouts/logouts. When you need to test the real publisher, use `@SpringBootTest(webEnvironment = RANDOM_PORT)` or a real container environment and observe record removal; avoid concluding solely from unit tests.

## 7. Frequently Confused Questions

### 7.1. Why Is SessionRegistry Configured, Yet `getAllSessions` Is Always Empty?

Possible reasons:
- Declared `@Bean SessionRegistryImpl` without **linking** it to the concurrent session authentication strategy.
- The login mechanism is a custom controller/filter that does not call `SessionAuthenticationStrategy` or fails to save `SecurityContext` properly.
- Querying with a principal object **not equal** to the registered principal; e.g., `getAllSessions("alice", false)` when the registry stores a `UserDetails` object.
- Using stateless JWT/HTTP Basic that does not create login sessions, so there is no session to register; do not expect every Bearer request to produce an `HttpSession`.
- Multiple instances exist, and the request and registry bean live in two different JVMs.
- The session was destroyed and an event already removed it from the registry.

**Diagnosis:** first verify which authentication mechanism creates the session, whether the strategy invokes the exact registry bean, and the actual principal type/equality; never conclude "the user is not logged in" solely from an empty list.

### 7.2. Why Is `activeCount = 1` Still Shown After Logout?

Suspects:
- `HttpSessionEventPublisher` is not registered with the container or is registered improperly.
- Logout does not actually invalidate the session (custom logout only deleted a client cookie).
- The session was marked expired but not yet destroyed, or `includeExpiredSessions=true` is displaying flagged entries too.
- Different registry/Servlet container instances, or an application restart skewed observation.
- The same principal has **another** active session.

Do not patch over symptoms by calling `removeSessionInformation` on every logout while ignoring the real session: deleting metadata does not invalidate the cookie/session. Use `LogoutFilter`/`SecurityContextLogoutHandler` properly and ensure the publisher/events work.

### 7.3. Does `expireNow()` Kick the User Out Immediately?

**Not immediately.** `expireNow` flags `SessionInformation` as expired. `ConcurrentSessionFilter` checks that flag when that session sends its next request and handles it via `SessionInformationExpiredStrategy`. If you want to immediately terminate a quiet device's session, you need a mechanism owning the real `HttpSession`/session store to invalidate it or disable credentials; the registry alone does not hold the `HttpSession` object to call `invalidate()` directly.

### 7.4. How Does `maxSessionsPreventsLogin(true)` Differ from the Default?

With `maximumSessions(1)`:
- Default (without `maxSessionsPreventsLogin`): a new login can succeed and an existing session (usually the least recently used) is marked expired. When the old session sends its next request, the filter handles expiration.
- `maxSessionsPreventsLogin(true)`: rejects the new login attempt once the limit is reached; the existing session stays valid.

Both rely on the registry having **accurate** counts. If the publisher fails to remove dead sessions or principal equality is broken, limit decisions will also be wrong.

### 7.5. Do Session Timeout and SessionInformation Expired Differ?

- **Servlet timeout**: the container decides the HTTP session expired due to inactivity; the publisher forwards the destroy event so the registry deletes the record.
- **Concurrency expired**: the registry sets `SessionInformation.expired=true` per policy (such as a new login replacing an old session); normally the filter handles it when that session sends another request.
- **Logout**: can invalidate `HttpSession` and clear `SecurityContext`. The destroy event ensures the registry no longer retains the entry.

`SessionInformation.getLastRequest()` is not the exact clock for when the container will time out, because the container has its own idle timeout configuration and the app may receive requests that bypass that filter.

### 7.6. Can a Single-Server Registry Be Used Across Multiple Servers?

The default `SessionRegistryImpl` is **per-JVM in-memory**. If the app is deployed on multiple nodes behind a load balancer, each node can only see a subset of sessions. Even `sticky session` does not turn two independent registries into a global registry.

You need a shared session architecture (such as Spring Session with Redis/JDBC) and a session registry/event strategy compatible with that deployment. Sessions/tokens may be evicted outside the JVM, so verify events, eviction, and concurrency policies in a clustered environment; do not assume adding Redis automatically makes `SessionRegistryImpl` distributed.

### 7.7. Should You Build an Admin "List All Sessions" API?

Only with a clear business requirement and strict authorization. `getAllPrincipals()` and `getAllSessions(...)` can expose identities, activity, access timestamps, and session IDs. Never give raw session IDs to regular clients; even admin interfaces should return minimal information, audit access, and use controlled revocation mechanisms rather than letting clients submit arbitrary session IDs to delete.

An "online users" dashboard based on the registry can be **misleading**: an existing session does not mean the user is online, and WebSocket traffic or stateless tokens are not necessarily counted by the registry. If you need near-real-time presence, design dedicated heartbeats and SLAs.

## 8. Deployment Scenarios and Checklist

| Need | Proper Usage |
| --- | --- |
| Count only the logged-in user's sessions | `registry.getAllSessions(auth.getPrincipal(), false).size()` with access control |
| View last-accessed session metadata | `SessionInformation.getLastRequest()`, avoid exposing session IDs |
| Limit to one session/user | `maximumSessions(1)` + matching registry/publisher + principal equality |
| Keep old session, reject new login | `maxSessionsPreventsLogin(true)` |
| Prefer new login | Keep default concurrency behavior, understand expire-on-next-request |
| Keep index clean on logout/timeout | Servlet listener `HttpSessionEventPublisher` and proper session lifecycle |
| Log out all devices | Design real session invalidation / credential revocation; `expireNow()` is not instant |
| Multiple nodes or external session store | Use a registry and event stream compatible with shared architecture |
| Custom JSON login | Invoke full authentication strategy + save context, not just authenticate |
| Report genuinely online users | Do not rely solely on SessionRegistry; requires dedicated heartbeat/presence |

Pre-production checklist:

- [ ] Authentication mechanism creates real sessions, not pure stateless JWT/Bearer.
- [ ] A single shared `SessionRegistry` is wired to the concurrency strategy, filter, and inspection code.
- [ ] `HttpSessionEventPublisher` is properly registered with the Servlet container, exactly once.
- [ ] Tested real logout, invalidation, and session timeout on a container with the listener active.
- [ ] `UserDetails.equals/hashCode` are stable; if multi-tenant, principals do not collide across tenants.
- [ ] CSRF protection remains active for cookie-based requests; session fixation protection is not disabled.
- [ ] Inspection API returns only the user's own sessions or requires explicit admin authorization.
- [ ] Raw session IDs are never put in logs, JSON responses, metrics labels, or URLs.
- [ ] Dedicated design exists if the application runs across multiple JVMs/pods.
- [ ] Clear understanding of differences between `expireNow`, `removeSessionInformation`, and `HttpSession.invalidate`.

## 9. Knowledge Self-Assessment

1. Why is `SessionRegistryImpl` not a store for `SecurityContext` or `HttpSession` contents?
2. What is the exact job of `HttpSessionEventPublisher`, and which layer does it receive events from?
3. How does `getAllSessions(principal, false)` differ from `getAllSessions(principal, true)`?
4. Does `expireNow()` delete the `HttpSession` immediately? Which component reacts on the next request?
5. Why can a custom `UserDetails` missing `equals/hashCode` break the max sessions policy?
6. Why shouldn't you call `getAllSessions("alice", false)` if the registry keys are `UserDetails` objects?
7. What is the difference between `maxSessionsPreventsLogin(true)` and the default policy when limiting to one session?
8. Why is a MockMvc test not enough to prove Servlet timeout events work in production?
9. With 3 pods behind a load balancer, does the default `SessionRegistryImpl` count all sessions?
10. Why can an account with a registered session still be considered offline by real-world presence standards?

**Core answers:** (1) the registry only holds an index/metadata; (2) forwards lifecycle events from the Servlet container to the Spring application context; (3) `true` includes entries marked expired that have not yet been removed; (4) no, the filter handles it when the session sends its next request; (5) principal map keys may compare unequal; (6) wrong type/equality; (7) blocking new logins vs. marking the old session expired; (8) mocks do not replace real container listeners/timeouts; (9) no, it is per-JVM in-memory; (10) session existence does not guarantee the user is currently active.

## 10. Official References

- Spring Security — Authentication Persistence and Session Management (Servlet, version 6.5): https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — `SessionRegistry` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/session/SessionRegistry.html
- Spring Security — `SessionRegistryImpl` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/session/SessionRegistryImpl.html
- Spring Security — `HttpSessionEventPublisher` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/session/HttpSessionEventPublisher.html
- Spring Security — `ConcurrentSessionFilter` API: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/session/ConcurrentSessionFilter.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Session — Reference (shared sessions and integration): https://docs.spring.io/spring-session/reference/
