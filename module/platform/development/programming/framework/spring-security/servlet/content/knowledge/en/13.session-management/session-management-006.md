# SessionRegistry, HttpSessionEventPublisher, and tracking active sessions in Spring Security Servlet

**Context:** Spring Security 6.x, Spring Boot 3.x, Java 17+, and Jakarta Servlet. This lesson belongs to the **Session Management** group. The goal is to understand how Spring Security registers authenticated login sessions, detects sessions marked expired, receives HttpSession lifecycle events from the Servlet container, and tests session state with real requests.

The core point: **SessionRegistry is not a repository of all HttpSessions**, and **HttpSessionEventPublisher is not an all-device logout mechanism**. Both components fulfill their roles only when properly wired to the session authentication strategy, filters, and Servlet container.

## 1. The problem: one account, multiple sessions

Suppose account <code>alice</code> has logged in from laptop A, laptop B, and phone C. Each browser may hold a <code>JSESSIONID</code> cookie pointing to a different HttpSession. With HttpSession-based form login, subsequent requests retrieve the corresponding Authentication from the saved SecurityContext.

~~~text
Browser A -- cookie JSESSIONID=A1 --+
Browser B -- cookie JSESSIONID=B2 --+--> Servlet container/session store
Phone C   -- cookie JSESSIONID=C3 --+                   |
                                                        v
                                               Spring Security
                                                        |
                                                        v
                                               SessionRegistry
                                               principal: alice
                                               session IDs: A1,B2,C3
~~~

The application might want at most two concurrent sessions; when a third device logs in, it either rejects the new login or allows it and forces the least recently active session to expire. Another feature is “log out other devices”, meaning the current session stays valid while other registered sessions are blocked on their next request.

**Distinguishing devices, browsers, tabs, and sessions:** two tabs in the same browser profile normally share the same cookie and the same HttpSession. Two separate profiles/cookie jars usually have different sessions. SessionRegistry tracks session IDs; it does **not** automatically detect physical device counts.

## 2. Which components participate?

| Component | Function |
| --- | --- |
| <code>HttpSession</code> | Servlet-level session managed by the container or session store, typically accessed via JSESSIONID. |
| <code>SecurityContext</code> | Holds the current Authentication; stateful applications can save it in HttpSession. |
| <code>SessionRegistry</code> | Interface managing the session catalog by principal and session ID. |
| <code>SessionRegistryImpl</code> | Default in-memory implementation within one JVM, holding <code>SessionInformation</code> entries. |
| <code>SessionInformation</code> | Information about a session: sessionId, principal, lastRequest, expired flag. |
| <code>SessionAuthenticationStrategy</code> | Invoked on successful login to enforce session limits, prevent fixation, and register the session. |
| <code>ConcurrentSessionFilter</code> | Checks for expired sessions as subsequent requests pass through and refreshes lastRequest. |
| <code>HttpSessionEventPublisher</code> | Servlet listener that publishes HttpSession lifecycle events to the Spring application context. |
| <code>HttpSessionDestroyedEvent</code> | Spring Security event supporting notification when a session is actually destroyed so the registry cleans up the record. |

Components do not wire themselves merely by creating beans. If you write a custom authentication filter and only call <code>SecurityContextHolder.setContext(...)</code> without invoking the corresponding session authentication strategies, <code>SessionRegistry</code> can remain **empty even though requests are authenticated**.

### Flow when a form login succeeds

~~~text
POST /login with username/password + CSRF
                |
                v
UsernamePasswordAuthenticationFilter
                |
                v
AuthenticationManager verifies credentials
                |
                v
Authentication succeeds
                |
                v
SessionAuthenticationStrategy
   1. Check concurrent session limit
   2. Execute session fixation protection strategy
   3. Register session ID + principal
                |
                v
SecurityContext saved according to stateful policy
                |
                v
Browser sends request with JSESSIONID
                |
                v
ConcurrentSessionFilter checks expired flag and refreshes lastRequest
                |
                v
Controller / authorization / response
~~~

The exact placement of filters and session strategies can depend on version and authentication type. To verify, test the real login path through the Spring SecurityFilterChain rather than manually creating an HttpSession.

## 3. Key API of SessionRegistry

The <code>org.springframework.security.core.session.SessionRegistry</code> interface provides:

~~~java
// Illustrative statements in a class with SessionRegistry injected.
List<Object> principals = registry.getAllPrincipals();

List<SessionInformation> active =
    registry.getAllSessions(principal, false);

List<SessionInformation> allKnown =
    registry.getAllSessions(principal, true);

SessionInformation sessionInfo =
    registry.getSessionInformation(sessionId);

registry.registerNewSession(sessionId, principal);
registry.refreshLastRequest(sessionId);
registry.removeSessionInformation(sessionId);
~~~

Explanation:
- <code>getAllPrincipals()</code> lists principals that currently have session records in the registry; it is **not** all users in the database.
- <code>getAllSessions(principal, false)</code> retrieves registered sessions **not yet marked expired**. “Active” here is registry status, not proof the browser is still open or the user is actively interacting.
- <code>getAllSessions(principal, true)</code> includes expired sessions if still retained by the registry.
- <code>getSessionInformation(id)</code> looks up a session or returns null when the registry has no record.
- <code>registerNewSession(id, principal)</code> is used by <code>RegisterSessionAuthenticationStrategy</code> in a valid concurrency configuration. Controllers normally do not call this method themselves.
- <code>refreshLastRequest(id)</code> records the timestamp of the latest request observed by the registry mechanism; <code>ConcurrentSessionFilter</code> typically executes this on matching session requests.
- <code>removeSessionInformation(id)</code> only deletes the record **inside the registry**; it does not directly invalidate a Servlet container HttpSession.

### Principal and equals/hashCode

SessionRegistryImpl uses the principal as the grouping key. If a custom principal is instantiated fresh on every login while <code>equals()</code>/<code>hashCode()</code> uses object identity or mutable attributes, two sessions for the same account may be counted as two separate groups. Result: wrong per-user session limits and session lists.

A principal used for session tracking should have a stable identifier, such as account ID, with well-designed equality. For multi-tenant users, decide whether session limits apply per account or per account+tenant and ensure tenant permissions are never mixed. The lesson's example uses Spring Security's standard <code>org.springframework.security.core.userdetails.User</code>, avoiding this complexity.

## 4. Expired, destroyed, invalidated, and removed: how do they differ?

| Action | What does the registry know? | Is the Servlet session handled immediately? |
| --- | --- | --- |
| Login succeeds and registers | Has SessionInformation, <code>expired=false</code> | Session was created/registered by the login strategy. |
| Valid request | lastRequest is updated if concurrency filter runs | Session remains active. |
| <code>SessionInformation.expireNow()</code> | Sets <code>expired=true</code> | Does **not** automatically invalidate the session instantly. |
| Subsequent request from expired session | ConcurrentSessionFilter detects and handles it | Typically logs out/invalidates and redirects or returns a failure response. |
| <code>HttpSession.invalidate()</code> | If event reaches the registry, the record is cleaned up | Yes: that specific session is invalidated. |
| Session timeout in container | May receive destroyed event and remove record | Session is destroyed per timeout/session store. |
| <code>registry.removeSessionInformation(id)</code> | Record disappears | **Does not guarantee** the corresponding HttpSession is destroyed. |

The following snippet **only sets a mark**; it is not an instant logout on a remote machine:

~~~java
SessionInformation info = registry.getSessionInformation(otherSessionId);
if (info != null) {
    info.expireNow();
}
~~~

The other browser may still hold the cookie; when it sends a request passing through <code>ConcurrentSessionFilter</code>, Spring Security detects the expired flag and runs the expired-session strategy. If the browser sends no further requests, the expired record can remain until the session actually times out/is destroyed.

Do not use <code>removeSessionInformation(id)</code> as a “revoke” API in place of <code>expireNow()</code>. Removing the record too early can prevent the filter from knowing the session should be rejected.

## 5. HttpSessionEventPublisher and session lifecycle

When the Servlet container creates/destroys a session (or changes a session ID where supported), it invokes registered servlet listeners. <code>HttpSessionEventPublisher</code> bridges those lifecycle events into the Spring Security application context. Specifically, <code>HttpSessionDestroyedEvent</code> enables <code>SessionRegistryImpl</code> to remove destroyed session IDs.

~~~text
Logout / invalidate / session timeout
                 |
                 v
          Servlet container
                 |
          HttpSessionListener
                 |
          HttpSessionEventPublisher
                 |
          HttpSessionDestroyedEvent
                 |
          SessionRegistryImpl
                 |
       removeSessionInformation(id)
~~~

Without the listener, an in-memory registry can retain sessions already destroyed by the container, causing inaccurate statistics or causing <code>maxSessionsPreventsLogin(true)</code> to keep thinking the user is at the limit. The listener is not a background scanner for the registry, nor does it turn a local registry into a cluster-wide registry.

In embedded Servlet Spring Boot, you can register the listener like this:

~~~java
@Bean
ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
    return new ServletListenerRegistrationBean<>(
        new HttpSessionEventPublisher());
}
~~~

When moving to a standalone Servlet container with different listener registration rules, ensure **exactly one registration**. When using session fixation protection or <code>changeSessionId()</code>, verify the registry reflects the session ID **after successful login**, rather than assuming the pre-authentication ID remains the active key.

## 6. Two policies for maximumSessions

**Allow new login while expiring an old session:**

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
        .maxSessionsPreventsLogin(false)
        .sessionRegistry(registry));
~~~

Once two non-expired sessions exist and browser C logs in, the concurrency strategy selects the least recently active session to mark expired, then registers session C. The flagged session will be handled when its next request passes through the filter.

**Prevent new login once the limit is reached:**

~~~java
http.sessionManagement(session -> session
    .maximumSessions(2)
        .maxSessionsPreventsLogin(true)
        .sessionRegistry(registry));
~~~

In this mode, a new login exceeding the limit is rejected while existing sessions keep working. Form login may redirect to an error screen; do not assume a single fixed HTTP status across every Spring Security configuration.

In both cases, <code>maximumSessions</code> controls **authenticated sessions registered by the session management mechanism**, not every session created manually by the application or every JWT stored on clients. The limit should be chosen based on security needs and user experience.

## 7. Runnable example: tracking two sessions of one account

The example uses **Java 17+, Spring Boot 3.3.5 (Spring Security 6.x), Maven**, form login, HttpSession, and SessionRegistryImpl. It intentionally runs on **a single JVM** so the registry lifecycle is easy to observe.

Requirements:
1. <code>alice</code> logs in with at most two concurrent sessions.
2. <code>GET /me</code> returns the username after login.
3. <code>GET /sessions/count</code> returns the number of **non-expired** sessions for the current principal.
4. <code>POST /sessions/revoke-others</code> marks other sessions expired while keeping the current session.
5. When an expired browser sends a new request, it is redirected to <code>/login?expired</code>.
6. CSRF is enabled by default on POST requests.

Project structure:

~~~text
session-registry-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/sessionregistry/
    │   ├── SessionRegistryApplication.java
    │   ├── SecurityConfiguration.java
    │   └── SessionController.java
    └── test/java/com/example/sessionregistry/
        └── SessionTrackingTest.java
~~~

### 7.1. pom.xml

~~~xml
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
    <version>1.0.0</version>
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
~~~

### 7.2. Application entry point

Create <code>src/main/java/com/example/sessionregistry/SessionRegistryApplication.java</code>:

~~~java
package com.example.sessionregistry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionRegistryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionRegistryApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfiguration.java

Create <code>src/main/java/com/example/sessionregistry/SecurityConfiguration.java</code>:

~~~java
package com.example.sessionregistry;

import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.security.core.session.SessionRegistryImpl;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("local-password-1234"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    ServletListenerRegistrationBean<HttpSessionEventPublisher> sessionEvents() {
        return new ServletListenerRegistrationBean<>(
            new HttpSessionEventPublisher());
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SessionRegistry registry) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(sessions -> sessions
                .maximumSessions(2)
                    .maxSessionsPreventsLogin(false)
                    .expiredUrl("/login?expired")
                    .sessionRegistry(registry))
            .build();
    }
}
~~~

Explanation:
- <code>InMemoryUserDetailsManager</code> provides UserDetails with a principal having stable equality. Passwords are hashed via <code>DelegatingPasswordEncoder</code>, never stored in plaintext.
- <code>SessionRegistryImpl</code> is the shared session registry inside the **demo JVM**.
- <code>HttpSessionEventPublisher</code> receives session-destroyed/timeout events from the Servlet container so the registry can purge gone records.
- <code>maximumSessions(2)</code> enables concurrent session registration and control. <code>maxSessionsPreventsLogin(false)</code> expires old sessions when needed instead of blocking new logins.
- <code>expiredUrl("/login?expired")</code> handles the next request from an expired session.
- <code>anyRequest().authenticated()</code> protects endpoints inspecting session state; anonymous users cannot read the list.
- Spring Security protects CSRF by default. Do not disable CSRF merely to test POSTs from the command line.
- This is a demo, not a production solution using hardcoded users/passwords or a local registry in a cluster.

### 7.4. SessionController.java

Create <code>src/main/java/com/example/sessionregistry/SessionController.java</code>:

~~~java
package com.example.sessionregistry;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    private final SessionRegistry registry;

    public SessionController(SessionRegistry registry) {
        this.registry = registry;
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/sessions/count")
    public String count(Authentication authentication) {
        int active = registry.getAllSessions(
            authentication.getPrincipal(), false).size();
        return Integer.toString(active);
    }

    @PostMapping("/sessions/revoke-others")
    public ResponseEntity<String> revokeOthers(
            Authentication authentication, HttpServletRequest request) {

        HttpSession current = request.getSession(false);
        if (current == null) {
            return ResponseEntity.badRequest().body("No active HttpSession");
        }

        String currentId = current.getId();
        int revoked = 0;

        for (SessionInformation info :
                registry.getAllSessions(authentication.getPrincipal(), false)) {
            if (!currentId.equals(info.getSessionId())) {
                info.expireNow();
                revoked++;
            }
        }

        return ResponseEntity.ok("revoked:" + revoked);
    }
}
~~~

The controller resolves the principal from the Spring Security-managed <code>Authentication</code> rather than trusting a client-supplied username. It only counts/expires sessions of the currently authenticated user. Never emit raw session IDs in HTTP responses to avoid increasing session credential exposure risk.

<code>POST /sessions/revoke-others</code> does not immediately destroy all HttpSessions in other browsers. It sets the expired flag on registry entries; <code>ConcurrentSessionFilter</code> acts when those browsers send their next requests. In real products, this is also a sensitive operation that may require re-authentication, auditing, rate limiting, and cross-node revocation mechanisms.

## 8. Testing with two independent browser profiles

Run from the directory containing <code>pom.xml</code>:

~~~bash
mvn test
mvn spring-boot:run
~~~

Open a normal window and a private window (or two independent browser profiles), visit <code>http://localhost:8080/login</code>, and enter <code>alice / local-password-1234</code> in both. Each profile has a distinct session cookie.

| Action | Browser A | Browser B |
| --- | --- | --- |
| GET /me before login | Redirect to login | Redirect to login |
| Log in | Session A registered | Session B registered |
| GET /me after login | <code>alice</code> | <code>alice</code> |
| GET /sessions/count | <code>2</code> | <code>2</code> |
| A sends POST /sessions/revoke-others with valid CSRF | <code>revoked:1</code> | Session B marked expired |
| B calls GET /me next | A still works | B redirects to <code>/login?expired</code> |
| A calls GET /sessions/count | <code>1</code> | B is no longer an active session per registry |

You must send the server-generated CSRF token on POST. If using curl with cookies only and no CSRF token, a 403 response is **correct for the demo configuration**, not a SessionRegistry bug. Logging in across two tabs sharing a cookie may create only one session, so test with separate cookie jars.

Log in with browser C while A and B still have two non-expired sessions: the <code>maximumSessions(2)</code> configuration selects the older/less active session to expire, then registers C. Which session is chosen depends on <code>lastRequest</code> and is not necessarily the browser that logged in first if it just made a recent request.

## 9. Automated testing with MockMvc

Create <code>src/test/java/com/example/sessionregistry/SessionTrackingTest.java</code>:

~~~java
package com.example.sessionregistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.core.session.SessionInformation;
import org.springframework.security.core.session.SessionRegistry;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SessionTrackingTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    SessionRegistry registry;

    private MockHttpSession login() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "local-password-1234"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertThat(session).isNotNull();
        return session;
    }

    @Test
    void twoSessionsCanBeTrackedAndOneExpired() throws Exception {
        MockHttpSession a = login();
        MockHttpSession b = login();

        assertThat(a.getId()).isNotEqualTo(b.getId());
        assertThat(registry.getSessionInformation(a.getId())).isNotNull();
        assertThat(registry.getSessionInformation(b.getId())).isNotNull();

        mvc.perform(get("/sessions/count").session(a))
            .andExpect(status().isOk())
            .andExpect(content().string("2"));

        // Missing CSRF: revocation is not permitted.
        mvc.perform(post("/sessions/revoke-others").session(a))
            .andExpect(status().isForbidden());

        mvc.perform(post("/sessions/revoke-others")
                .session(a).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("revoked:1"));

        SessionInformation other =
            registry.getSessionInformation(b.getId());
        assertThat(other).isNotNull();
        assertThat(other.isExpired()).isTrue();

        mvc.perform(get("/sessions/count").session(a))
            .andExpect(status().isOk())
            .andExpect(content().string("1"));

        mvc.perform(get("/me").session(b))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?expired"));

        mvc.perform(get("/me").session(a))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void aThirdLoginLeavesAtMostTwoNonExpiredSessions()
            throws Exception {
        MockHttpSession a = login();
        MockHttpSession b = login();
        MockHttpSession c = login();

        assertThat(registry.getSessionInformation(c.getId())).isNotNull();

        long stillActive = java.util.stream.Stream.of(a, b, c)
            .map(s -> registry.getSessionInformation(s.getId()))
            .filter(s -> s != null && !s.isExpired())
            .count();

        assertThat(stillActive).isLessThanOrEqualTo(2);
    }
}
~~~

Why does the test perform real POST logins? <code>@WithMockUser</code> is convenient for testing authorization, but it does not necessarily run <code>SessionAuthenticationStrategy</code> and does not automatically create registry entries. The test must go through the form login filter to prove session registration.

<code>@DirtiesContext</code> here isolates the in-memory registry state between the two tests; if a shared registry were reused and logins from the previous test were not destroyed, the next test could unintentionally hit the session limit.

**MockMvc limitation:** it does not necessarily fire Servlet lifecycle events identically to real embedded Tomcat. The tests above confirm registration/expired behavior, but do not 100% prove <code>HttpSessionEventPublisher</code> cleans up records after real timeout/logout on a Servlet container. For that purpose, write integration tests on a real server (<code>@SpringBootTest(webEnvironment = RANDOM_PORT)</code> or an HTTP client against a running server), perform logout/invalidation/timeout, and verify the registry no longer holds the record.

## 10. Tracking online sessions is not the same as counting non-expired sessions

When calling <code>getAllSessions(principal, false)</code>, “active” means **not yet marked expired by the registry**. It does not assert the user still has the tab open or interacted recently; the browser may have closed while the session has not yet timed out. A manually created HttpSession that bypassed session registration may also be absent from the registry.

<code>SessionInformation.getLastRequest()</code> is the timestamp when the registry was refreshed as requests passed through the concurrency mechanism. <code>HttpSession.getLastAccessedTime()</code> is Servlet container metadata. The two timestamps are not always strictly identical because filter chains, dispatchers, session stores, and request types can differ.

Do not use <code>SessionRegistry.getAllPrincipals().size()</code> as an exact measure of “currently online” users or all accounts holding sessions across all servers. For monitoring, you can additionally track session store counts, login successes/failures, expired entries awaiting cleanup, session-destroyed events, and revocation latency.

Do not expose raw principals or session IDs in public dashboards. Session IDs are sensitive credentials; if a “logged-in devices” UI is needed, return only minimal metadata verified by the server as belonging to the logged-in account and never let users specify another account's username.

## 11. Logout, timeout, and HttpSessionDestroyedEvent

A typical stateful logout flow:

~~~text
POST /logout + CSRF token
      |
Spring Security logout handler
      |
SecurityContext is cleared
      |
Current HttpSession is invalidated
      |
Servlet container fires sessionDestroyed
      |
HttpSessionEventPublisher converts to Spring event
      |
SessionRegistryImpl removes session ID from registry
~~~

When a session times out naturally, the container can also fire a destroyed event and the registry cleans up the record. Without the listener, the registry risks retaining sessions that no longer exist, which is especially hazardous with <code>maxSessionsPreventsLogin(true)</code>: users can be locked out of logging in because the registry thinks they still occupy all slots.

Distinguish concurrency-based expiration:
- <code>expireNow()</code> sets the expired flag without immediately deleting the session.
- The expired browser sends a request; <code>ConcurrentSessionFilter</code> executes the expired strategy, typically logging out/invalidating the session.
- The container fires a destroyed event when the session is destroyed; the publisher lets the registry drop the record.

If the browser stops sending requests, the expired record can persist until real timeout/session destruction occurs. **Do not** conclude that the presence of an expired record means the user is still active.

## 12. Session fixation and session ID rotation

Upon successful authentication, Spring Security typically applies session fixation protection on modern Servlets, potentially using <code>changeSessionId()</code>. The pre-login session has ID <code>PRE</code>, and post-login has <code>POST</code>. The registry must track the ID **after** rotation.

If custom authentication code registers a session too early, then changes the ID itself or omits calling the corresponding strategy, the registry can become out of sync. When writing custom filters, ensure SessionAuthenticationStrategy, SecurityContextRepository, and the session fixation strategy work together in harmony.

Tests should inspect <code>registry.getSessionInformation(session.getId())</code> on the session obtained **after login**, rather than capturing a pre-login ID and assuming the registry keeps it unchanged. Never write session IDs into URLs, public logs, or debug responses.

## 13. Multi-node systems and Spring Session

In a cluster:

~~~text
                    +-- App node A / SessionRegistryImpl A
Client -> gateway --+-- App node B / SessionRegistryImpl B
                    +-- App node C / SessionRegistryImpl C
                            |
                       Shared database
~~~

Even with a shared user database, each in-memory SessionRegistryImpl knows only sessions registered in **its own process**. A 2-session limit can turn into “2 sessions per node” rather than 2 sessions cluster-wide. Calling <code>expireNow</code> on node A does not automatically propagate the expired flag to node B. HttpSessionEventPublisher inside node A does not automatically broadcast to B/C either.

When cluster-wide session management is required, you can use:
- Spring Session with Redis/JDBC or a shared session store.
- A repository supporting principal indexing to look up sessions belonging to the same account.
- Distributed registry/concurrency integration matching the repository, such as <code>SpringSessionBackedSessionRegistry</code> in supported versions.
- A shared credential/session version or revocation state if you must guarantee all old sessions are blocked on their next request.
- Testing across multiple instances and routing through a load balancer, not just testing a single JVM.

**Note:** adding Spring Session Redis does not automatically turn an in-memory <code>SessionRegistryImpl</code> into a cluster-wide registry. Distributed registry integrations have their own semantics and limitations; consult the exact version documentation and test thoroughly.

Pseudocode example for a principal-indexed repository (not a standalone Java file):

~~~java
var sessions = indexedRepository.findByPrincipalName(username);
for (String sessionId : sessions.keySet()) {
    indexedRepository.deleteById(sessionId);
}
~~~

To use this in practice requires <code>FindByIndexNameSessionRepository</code> or an equivalent contract, accurate principal indexing, a <code>username</code> from a trusted server source, and restricted permissions. Deleting a session directly in the store differs from marking <code>SessionInformation.expireNow()</code> in the registry.

If the system uses stateless JWTs, SessionRegistry does not manage access tokens held by clients. Revocation depends on expiry, refresh-token revocation, token versions, denylists/introspection, or another suitable mechanism.

## 14. Common errors and how to handle them

| Error / symptom | Cause | Remediation |
| --- | --- | --- |
| SessionRegistry bean exists yet session list is empty | Login path does not invoke session registration strategy | Enable concurrency management, test real POST /login |
| Logged out yet registry still holds the session | Missing publisher or event cleanup | Register HttpSessionEventPublisher and test on a real container |
| Called expireNow yet the other browser keeps its cookie | That operation only sets a flag | Test the next request through ConcurrentSessionFilter |
| Called removeSessionInformation to log out | Registry forgets session yet HttpSession may still work | Use proper logout/invalidation or revocation |
| Two logins of the same user counted as two principals | Unstable custom principal equals/hashCode | Use a stable account identifier |
| Treating multiple tabs as multiple sessions | Tabs share cookies | Test with two browser profiles/cookie jars |
| MockMvc @WithMockUser creates no session registry entry | Bypasses form login strategy | Perform real login via MockMvc |
| User locked out of login despite timeout | Registry does not receive session destroyed events | Check listener, timeout, and prevents-login config |
| Local tests pass yet production fails | Multiple app replicas, local registry | Use shared session/index and test cross-node |
| “Online count” exceeds active browsers | Sessions not yet timed out or expired entries not cleaned up | Distinguish online presence from active-in-registry |
| Custom authentication fails to register sessions | Skips SessionAuthenticationStrategy | Integrate and test custom filter |
| Changing session ID after registration desyncs registry | Fixation/registration strategies out of sync | Use Spring Security session strategies in proper order |
| Endpoint exposes raw session IDs | Leaks sensitive identifiers | Return only necessary metadata, enforce access control |
| Thinking stateless JWTs are tracked by registry | No corresponding HttpSession login | Design dedicated token management |
| Multiple SecurityFilterChains with registration on the wrong chain | Request enters a different chain | Check first-matching chain and filter order |

## 15. Testing and operations checklist

1. Confirm the application uses session-based authentication; if solely stateless JWT, SessionRegistry is not an equivalent token management tool.
2. Declare SessionRegistry and attach it to the **right SecurityFilterChain** handling form login or custom authentication.
3. Enable concurrency/session authentication strategy, choosing maxSessions and expire-versus-prevent mode.
4. Register HttpSessionEventPublisher with the Servlet container exactly once.
5. Test two separate sessions for the same account using independent browser profiles; verify the registry records the exact two session IDs.
6. Test expireNow and the expired session's next request; the session must no longer gain access.
7. Test logout/session timeout and record cleanup in a real container; MockMvc is not sufficient alone.
8. Test CSRF protection and access control on view/revoke session endpoints without exposing session IDs.
9. With multiple nodes, verify shared session registry behavior and cluster-wide policy consistency.
10. Keep logs/metrics minimal; never emit cookies, session IDs, or unnecessary personal data.
11. Whenever changing authentication filters or session fixation strategies, test session IDs before and after login.
12. When increasing/decreasing maximumSessions, consider user experience and existing sessions.

## 16. Self-check questions

**Question 1:** <code>getAllSessions(principal, false)</code> returns two sessions. Are two people definitely using the app?  
**Answer:** No. Those are two sessions known to the registry and not yet expired; the browser may have closed while the session has not timed out.

**Question 2:** Does <code>expireNow()</code> instantly delete the HttpSession and cookie on another browser?  
**Answer:** No. It marks the session expired; the filter handles it on the next request. The session may only be destroyed when the expired strategy or timeout triggers.

**Question 3:** Why is <code>HttpSessionEventPublisher</code> needed?  
**Answer:** So session-destroyed events from the Servlet container reach Spring Security, enabling the registry to purge dead session information.

**Question 4:** You already have a SessionRegistry bean; is additional configuration needed to register sessions on login?  
**Answer:** Yes. Concurrency/SessionAuthenticationStrategy integration or a custom flow invoking registration is required. Creating the bean alone is not enough.

**Question 5:** What do <code>maximumSessions(2)</code> and <code>maxSessionsPreventsLogin(false)</code> mean?  
**Answer:** Once two sessions exist, a new login is permitted while an older/less active session is marked expired.

**Question 6:** Three nodes share one database, each running SessionRegistryImpl. Is the two-session limit enforced cluster-wide?  
**Answer:** No. RegistryImpl only holds information within its own JVM; a shared mechanism and cross-node testing are needed.

**Question 7:** Calling <code>removeSessionInformation(id)</code> instead of invalidating—does that guarantee logout?  
**Answer:** No. That only removes the registry record; the HttpSession can still exist with a valid Authentication.

**Takeaway:** <code>SessionRegistry</code> tracks registered sessions, <code>SessionInformation</code> records request timestamps and the expired flag, <code>ConcurrentSessionFilter</code> handles sessions marked expired, and <code>HttpSessionEventPublisher</code> delivers Servlet container session-destruction events to Spring Security. Never confuse **expired, destroyed, invalidated, and removed**, and never treat a local registry as a cluster-wide session store.
