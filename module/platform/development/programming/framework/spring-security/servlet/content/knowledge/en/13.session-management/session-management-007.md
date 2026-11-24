# Distinguishing expired, invalid, and superseded sessions

In **Spring Security for Servlet applications**, a user can lose their logged-in state for multiple reasons: the HTTP session no longer exists after inactivity; the browser sends a session ID the server does not accept; or a new login caused an old session to be marked expired under concurrent login limits. In addition, Spring Security **changes the session ID after authentication to prevent session fixation**: that action is also often described as “replacing a session”, yet it does not mean the user was logged out, timed out, or kicked out by another login.

The most important takeaway of this lesson: **timeout is a session-lifecycle cause; invalid ID is a request-observable state; concurrency-expired is a state flagged by SessionRegistry; session-ID rotation is a defense at login**. These states can lead to the same symptom of “having to log in again”, but they cannot be handled or explained the same way.

The lesson uses a **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/MVC** context. We will examine Servlet `HttpSession`, the `JSESSIONID` cookie, `SessionRegistry`, `ConcurrentSessionFilter`, `InvalidSessionStrategy`, `SessionInformationExpiredStrategy`, `maximumSessions`, redirect handlers, session fixation protection, configuration examples, testing, and diagnostics. Exact behavior depends on the Spring Security version, filter chain, servlet container, and whether the application uses Spring Session.

## 1. Concepts that must be separated

A stateful login system involves several entities:

- **Session ID**: a secret string identifying the session, typically sent by the browser as the `JSESSIONID` cookie. It acts like a bearer secret: anyone possessing a valid session ID can impersonate the browser's requests without other protections.
- **HttpSession**: server-side session data. It has an ID, attributes, timestamps, and an inactivity limit; it can reside in the servlet container or an external session store.
- **SecurityContext**: holds the current `Authentication`, typically loaded/saved by a `SecurityContextRepository`. Some configurations store the context in the session, though not every application needs a session.
- **SessionRegistry**: a store tracking principals, session IDs, and state for **concurrent session control**. It does not replace session storage itself.
- **SessionInformation**: information about a session known to the registry, including an expired flag for concurrency purposes; that expired flag is not the container's idle timeout.
- **Servlet request**: can report `getRequestedSessionId()` and `isRequestedSessionIdValid()`, which are signals visible at request time, not a full log of why a session disappeared.

~~~text
Browser
  |
  | Cookie: JSESSIONID=S1
  v
Servlet container / Spring Session store
  |-- S1 exists?     -> HttpSession and attributes
  |-- S1 absent?     -> request carries an invalid ID
  |
  +-> SecurityContextRepository
  |      -> loads SecurityContext if present per policy
  |
  +-> SessionRegistry (if concurrent sessions configured)
         -> which principal owns S1?
         -> was S1 marked expired by concurrency policy?
~~~

A timed-out session can cause **the next request** using cookie S1 to be seen as invalid; those are two related conceptual layers, not two independent parallel reasons.

## 2. Comparison table of four situations

| Term | Cause / nature | Observable signals | Related Spring Security handling |
| --- | --- | --- | --- |
| **Session expired due to timeout** | Exceeded idle timeout or container/session store lifecycle policy | Server session disappears; old cookie may still be sent | Next request can become anonymous, reaching an entry point or invalid-session strategy if configured |
| **Requested session ID is invalid** | Client-sent ID resolves to no valid server session (could be timeout, logout, restart, bogus ID, rotation) | `isRequestedSessionIdValid() == false` on a request with a requested ID | `InvalidSessionStrategy` / `invalidSessionUrl` in the active chain |
| **Session superseded by concurrent login** | Policy allows new login and marks old session expired in registry | `SessionInformation.isExpired() == true`; old request detected by concurrency filter | `maximumSessions`, `ConcurrentSessionFilter`, `expiredUrl` |
| **Session ID rotated after login** | Defense against session fixation | Pre/post-authentication IDs differ, valid session continues working | `SessionAuthenticationStrategy`, `sessionFixation(...changeSessionId())` |

The word **expired** appears in both idle timeout and `expiredUrl`, making it very easy to confuse. In Spring Security concurrent-session management, `expiredUrl` is typically the destination for a session **marked expired by the registry** due to session-count policy, **not** a general notice page for every servlet timeout.

A rule for accurate logging: **never assert the reason solely from an HTTP 302 or 401 response**. A redirect to `/login` may simply mean the request was unauthenticated; it does not prove the user was concurrency-expired.

## 3. State 1: HttpSession expires due to timeout

The servlet container/session store can destroy an `HttpSession` after a period of inactivity (idle timeout). Example with a 15-minute timeout:

~~~text
10:00  Alice logs in -> session S1 exists
10:05  Alice requests GET /profile -> session S1 remains active
10:20+ No further interaction for the idle timeout duration
       -> session store/container may delete or expire S1
10:30  Browser sends Cookie JSESSIONID=S1
       -> server cannot find S1
       -> SecurityContext stored in S1 is no longer available to load
~~~

Exact timing depends on the servlet container, session store, and cleanup sweep interval. This is not a fixed timer on the browser; the browser can keep holding the cookie after server-side data has expired.

Spring Boot configuration example:

~~~properties
server.servlet.session.timeout=15m
~~~

This value targets the Servlet session timeout. If using Spring Session Redis/JDBC or configuring sessions elsewhere, compare actual TTL policies, cookie lifetime, infrastructure, and the value accepted by the framework. Do not assume this sets the maximum lifetime for every access token, JWT, or user account.

### How does the post-timeout request respond?

- **Web form login**: a new request to a protected resource typically lacks authentication in the session and may redirect to the login page via 302.
- **JSON API**: may return 401 if the API entry point is configured that way.
- **Invalid-session handling**: when a request carries an old requested session ID and the corresponding filter/strategy is active, it may redirect or return a specific error.
- **No cookie**: usually just a fresh unauthenticated request; hard to distinguish from someone who never logged in.

Session timeout is genuinely an **event in the session store/container**. Merely observing that S1 does not exist does not allow the app to assert it expired from inactivity; logout, admin termination, server restart, or a bad cookie/ID can look identical. Reliable reason codes require recording lifecycle events at the source.

### Timeout differs from access token expiration

A Bearer JWT can expire due to its `exp` claim and the resource server can return 401 without using `HttpSession`. An HTTP session timeout does not automatically revoke previously issued stateless JWTs, nor should `expiredUrl` be used to handle bearer token errors.

## 4. State 2: request carries an invalid session ID

An invalid session ID is determined when the Servlet request enters the server. Causes include:

1. The session genuinely idle-timed out.
2. The user logged out and the server invalidated the session.
3. The session was proactively revoked by an admin or the application.
4. A server restart lost in-memory session data.
5. The client sent a corrupted, forged, truncated, or foreign-store cookie.
6. The session ID was just rotated at login, yet the client still sent the old ID.
7. A load balancer routed the request to a node without shared session data when sticky/shared state was expected.
8. Misconfigured cookie Domain/Path caused the browser to send the wrong cookie.

Servlet API used to observe:

~~~java
// Java fragment running inside a Servlet, not a standalone JDK program.
String id = request.getRequestedSessionId();
boolean valid = request.isRequestedSessionIdValid();
~~~

If there is no requested ID, `id` can be `null`. If `valid=false`, **do not** automatically conclude idle timeout. Session IDs are sensitive data and should not be logged directly in request logs, metrics, or analytics.

### invalidSessionUrl and InvalidSessionStrategy

With a matching Spring Security Servlet configuration:

~~~java
http.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid"));
~~~

This configuration directs the response when **a request presented an invalid ID** and the invalid-session detection mechanism actually executes. `InvalidSessionStrategy` can be used for custom responses:

~~~java
http.sessionManagement(session -> session
    .invalidSessionStrategy(myInvalidSessionStrategy));
~~~

`myInvalidSessionStrategy` is an application-provided object/bean; this is a fragment, not a full class. It can return JSON 401, clear the old cookie, or redirect; design its payload so it does not disclose unproven claims.

**Spring Security 6 specific note:** `SessionManagementFilter` is not present by default in every modern configuration. Some authentication mechanisms proactively invoke `SessionAuthenticationStrategy` without relying on `SessionManagementFilter`'s detection logic. Therefore, declaring `invalidSessionUrl(...)` alone is not enough to infer every URL/chain triggers the strategy; inspect the actual filter chain or run version-accurate integration tests.

### Avoiding redirect loops

If the browser keeps sending the invalid `JSESSIONID` cookie, requests to `/session-invalid` itself can be intercepted by the strategy and redirected right back to `/session-invalid`. To avoid this:

- Ensure the error page is public and has clear rules for handling invalid cookies.
- Delete the old session cookie **with matching name, Path, Domain, and Secure** attributes, or re-establish a valid session per policy.
- For APIs, prefer returning a status/error contract rather than an HTML redirect that clients cannot handle.
- Test on real browsers and reverse proxies. Do not assume deleting a cookie with `Path=/` deletes an earlier cookie scoped to `Path=/portal`.
- Do not create a new session on every request to the error page if doing so causes loops or obscures debugging evidence.

### Logout also makes the old ID invalid

A `SecurityContextLogoutHandler` can invalidate the session on logout. When the browser resends the old cookie, the server no longer recognizes the ID. This is intentional session termination, **not** timeout or concurrency-expiration. Therefore, messaging should remain neutral if the application does not know the exact cause.

## 5. State 3: session evicted by concurrent login policy

Suppose Alice's account is allowed at most **one active session at a time**:

~~~text
Browser A                    SessionRegistry                  Browser B
  | Login Alice -> session S1     |                                |
  |-----------------------------> | register S1                    |
  |                               |                                |
  |                               |       Login Alice -> session S2|
  |                               | <------------------------------|
  |                               | mark S1 expired, register S2   |
  |                               |                                |
  | GET /private with S1          |                                |
  |-----------------------------> |                                |
  |       ConcurrentSessionFilter checks S1 is expired             |
  |       runs logout / invalidate and expired-session strategy    |
  |<----------------------------- |                                |
  | 302 -> /session-replaced (if redirect configured)              |
~~~

Key points:

- `SessionRegistry` holds `SessionInformation` for sessions known to concurrent-session management.
- When the session limit is exceeded and policy allows the new login, an old session may have `expireNow()` called: **marking** it expired in the registry.
- `ConcurrentSessionFilter` detects this state on the next request from the old session, performs logout/invalidation per contract, and invokes `SessionInformationExpiredStrategy` or the configured redirect.
- If browser A sends no new request, A's UI will not necessarily realize it was “kicked out” at the moment B logs in. Updating A's UI instantaneously requires a dedicated event channel; do not assume HTTP filters push real-time notifications.

### Two maximumSessions modes

~~~java
// Allow new login, mark an old session expired.
http.sessionManagement(session -> session
    .maximumSessions(1)
      .maxSessionsPreventsLogin(false)
      .expiredUrl("/session-replaced"));
~~~

~~~java
// Disallow new login if the active session limit has been reached.
http.sessionManagement(session -> session
    .maximumSessions(1)
      .maxSessionsPreventsLogin(true));
~~~

| Policy | Alice logs in on A | Alice logs in next on B | What happens to A |
| --- | --- | --- | --- |
| Unlimited | S1 active | S2 can be active | S1 is normally not evicted by this policy |
| `maximumSessions(1)`, `maxSessionsPreventsLogin(false)` | S1 active | S2 accepted | S1 marked expired, handled when A requests again |
| `maximumSessions(1)`, `maxSessionsPreventsLogin(true)` | S1 active | Login B rejected per policy | S1 keeps working |
| S1 timed out and registry cleaned up | S1 gone | B logs in | Do not conclude “B kicked out A” |

With `maxSessionsPreventsLogin(true)`, the status or error page for browser B depends on the authentication type, provider/strategy, and failure handler; do not assume it is always HTTP 403.

### expiredUrl does not handle ordinary timeouts

When `ConcurrentSessionFilter` sees a session marked expired in the registry, `expiredUrl("/session-replaced")` can route the request to that page. It is **not** a general handler for browsers sending cookies of sessions already purged by container timeout. A destroyed session typically no longer has a live session for the registry/filter to mark and handle along the same path.

### Session destroyed events and HttpSessionEventPublisher

So the registry knows which sessions were destroyed, with Servlet sessions and `SessionRegistryImpl` you can configure:

~~~java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

This code is a fragment inside a Spring `@Configuration` class; import `org.springframework.security.web.session.HttpSessionEventPublisher` and `org.springframework.context.annotation.Bean`. It forwards Servlet session events to interested listeners to clean up the registry in matching setups. If events are not emitted or fail to reach the registry, timed-out sessions can still be counted as active, causing `maximumSessions` to reject logins unfairly.

In **multi-node** systems, an in-memory registry does not synchronize across the cluster. When using Spring Session, integrate a registry backed by a session repository capable of distributed sessions and session events; do not assume registering `HttpSessionEventPublisher` alone synchronizes all nodes.

## 6. Another meaning of “session replaced”: rotating session ID at login

Session fixation is an attack where a bad actor tries to force a victim to use a session ID already known to the attacker. After the user logs in, if the server keeps using that exact old ID, the attacker can exploit it to access the authenticated session.

Spring Security can defend against this using `SessionAuthenticationStrategy`:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId()));
~~~

Illustrative progression:

~~~text
Before login:
  Cookie: JSESSIONID=S-before (anonymous, existing session)

POST /login succeeds:
  SessionAuthenticationStrategy uses changeSessionId()

After login:
  Cookie: JSESSIONID=S-after (authenticated, valid session)
~~~

`S-before` and `S-after` differ; the existing session typically keeps appropriate attributes when using `changeSessionId()`. This is **not** Alice being replaced by browser B, nor is it a session expiring from inactivity.

If a browser keeps sending `S-before` after rotation, the subsequent request can report an invalid session ID. Concluding “this was a rotated ID” requires evidence of the **rotation event**, not merely `isRequestedSessionIdValid()==false`.

In a custom `AuthenticationFilter` or custom login controller, verify that the session fixation strategy actually runs after authentication. Do not assume every authentication mechanism automatically executes form login's strategies.

### Comparing the two forms of “replacement”

| Criterion | Session ID rotation | Concurrent-session replacement |
| --- | --- | --- |
| Trigger | The browser currently logging in | Another browser/session logging in as the same principal and exceeding policy |
| What changes | The session's identifier at login | The old session's status in the registry |
| Goal | Prevent session fixation | Limit concurrent sessions |
| Is the old account logged out? | Not the purpose of this operation | Can be logged out/invalidated on next request |
| Related APIs | `sessionFixation(...changeSessionId())` | `maximumSessions`, `SessionRegistry`, `ConcurrentSessionFilter` |

Both mechanisms can run during the same login B: B's ID is rotated and session A is marked expired. Therefore they must never be conflated into a single cause.

## 7. Spring Security components and key responsibilities

| Component | When involved | What not to misunderstand |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Loads/prepares context for the request, clears holder from thread afterward | Does not prove a session timed out |
| `SecurityContextRepository` | Reads/saves context in the session or another repository | Not the concurrency SessionRegistry |
| `AuthenticationEntryPoint` | Unauthenticated request requiring authentication | Redirect to `/login` does not mean concurrency-expired |
| `SessionManagementFilter` | When configured in the chain, can detect requested invalid session IDs and invoke strategy | Not present by default in every Spring Security 6 chain |
| `InvalidSessionStrategy` | Request with invalid session ID, responds with 302/401/JSON | Does not always distinguish timeout from logout/fake ID |
| `SessionRegistry` | Tracks principal/sessionInfo and expired flag | Not the Servlet session store |
| `ConcurrentSessionFilter` | Checks expired sessionInfo when a request arrives | Does not push real-time notices to idle browsers |
| `SessionInformationExpiredStrategy` | Response handler when concurrency-expired | Not a handler for every timeout |
| `SessionAuthenticationStrategy` | Post-login work: ID rotation, registration, concurrency | Does not verify username/password itself |
| `LogoutHandler` | User logout or concurrency filter policy handling | Not a servlet timeout in every case |

An application can have multiple `SecurityFilterChain`s. Each request passes through the first matching chain; an API chain using only Bearer tokens may **not** include the same session/concurrency filters as the web form login chain. When analyzing logs, determine which chain handled the request and which filters actually executed.

### URLs handling different events

~~~java
// DSL fragment; the URLs have different meanings.
.formLogin(form -> form
    .defaultSuccessUrl("/private"))
.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid")
    .maximumSessions(1)
      .maxSessionsPreventsLogin(false)
      .expiredUrl("/session-replaced"))
~~~

- `defaultSuccessUrl`: target after **successful login**.
- `invalidSessionUrl`: for **invalid requested session IDs** if the strategy applies.
- `expiredUrl`: for **sessions marked expired by concurrency policy**.
- `failureUrl`: for **failed login** (wrong credentials, provider rejection).
- `logoutSuccessUrl`: for **successful logout**.
- Session fixation ID change **does not need** an error redirect page.

## 8. Spring Boot 3 / Spring Security 6 session configuration example

The example uses form login with a demo user, a 15-minute timeout, and a single active session limit. `/session-replaced` and `/session-invalid` are public pages. In a real environment, add stale-cookie cleanup and redirect-loop prevention.

### 8.1. Maven dependencies

In `pom.xml` of a project with the matching Spring Boot parent/BOM:

~~~xml
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
~~~

Do not arbitrarily mix Spring Security versions outside the BOM. Spring classes depend on the classpath and **cannot run with plain JDK `javac` alone**; a standalone plain-Java example is provided in section 11.

### 8.2. application.properties

Create `src/main/resources/application.properties`:

~~~properties
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
# For production using HTTPS, configure secure cookie per deployment:
# server.servlet.session.cookie.secure=true
~~~

### 8.3. Main class

Create `src/main/java/com/example/session/SessionLifecycleApplication.java`:

~~~java
package com.example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig

Create `src/main/java/com/example/session/SecurityConfig.java`:

~~~java
package com.example.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-pass"))
                .roles("USER")
                .build());
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/session-invalid",
                                 "/session-replaced").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private")
                .permitAll())
            .sessionManagement(session -> session
                .invalidSessionUrl("/session-invalid")
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                    .maxSessionsPreventsLogin(false)
                    .expiredUrl("/session-replaced"));
        return http.build();
    }
}
~~~

Explanation:

1. `formLogin` sets up form login and can use the default GET `/login` page. The demo user/password are for **local use only**; never hardcode production credentials.
2. `maximumSessions(1)` sets a one-session limit per principal recognized by the registry.
3. `maxSessionsPreventsLogin(false)` permits login B and marks session A expired.
4. `expiredUrl("/session-replaced")` handles A's request when the concurrency filter sees the session marked expired.
5. `invalidSessionUrl("/session-invalid")` configures the invalid requested ID branch, which only takes effect when invalid-session detection actually runs in the chain.
6. `sessionFixation(...changeSessionId())` protects the ID upon successful login; it is not the policy that kicks out session A.
7. `HttpSessionEventPublisher` supports registry cleanup via Servlet session lifecycle events.

**Note:** In some Spring Security 6 configurations or custom authentication filters, the invalid-session strategy may not run as expected if `SessionManagementFilter` is absent. Inspect the filter chain and write integration tests rather than claiming every browser redirects to `/session-invalid` based on a snippet alone.

### 8.5. Endpoints

Create `src/main/java/com/example/session/SessionPages.java`:

~~~java
package com.example.session;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionPages {
    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/private")
    public String privatePage() {
        return "private";
    }

    @GetMapping("/session-invalid")
    public String invalid() {
        return "Session ID is no longer valid";
    }

    @GetMapping("/session-replaced")
    public String replaced() {
        return "Session ended by concurrent-login policy";
    }
}
~~~

The two notice pages here simply return plain text and require no authentication; real products should use appropriate views/JSON, implement stale-cookie handling, and avoid disclosing unproven details.

### 8.6. Trying with two independent windows

Run with the appropriate Maven Wrapper/JDK:

~~~bash
./mvnw spring-boot:run
~~~

1. Open browser profile A, visit `/private`, and log in as `alice`. Verify access to private content.
2. Open an independent browser profile B (not sharing a cookie jar) and log in as the same `alice`.
3. Once B is accepted, return to A and **send a new request** to `/private`. With concurrency policy/registry/filter active, A is handled by the expired strategy and may redirect to `/session-replaced`.
4. B can still access private content.
5. Switch to `maxSessionsPreventsLogin(true)` in a test profile and repeat: B will be rejected from logging in while A remains active.
6. Test a stale cookie after logout/session timeout: if the invalid session handler runs, it can go to `/session-invalid`. Watch for any redirect loops.
7. Check the session ID before and after a valid login (without exposing the ID) to verify session fixation protection.

**Two tabs in the same profile are not two independent sessions** because browsers normally share cookies. Use two different profiles/private windows or two HTTP clients with separate cookie jars.

## 9. MockMvc testing and simulation limits

MockMvc lets you test the form login path with two independent `MockHttpSession` instances. This is an integration test of the Spring Security filter chain, **not** proof that a production Redis/session store expires on schedule as configured.

### 9.1. Concurrent login test

Create `src/test/java/com/example/session/ConcurrentLoginTest.java`:

~~~java
package com.example.session;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConcurrentLoginTest {
    @Autowired MockMvc mvc;

    @Test
    void secondLoginExpiresPriorSession() throws Exception {
        MockHttpSession browserA = new MockHttpSession();
        MockHttpSession browserB = new MockHttpSession();

        mvc.perform(post("/login").session(browserA).with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/private").session(browserA))
            .andExpect(status().isOk());

        mvc.perform(post("/login").session(browserB).with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-pass"))
            .andExpect(status().is3xxRedirection());

        // Only A's next request reveals the expired status.
        mvc.perform(get("/private").session(browserA))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/session-replaced"));

        mvc.perform(get("/private").session(browserB))
            .andExpect(status().isOk());
    }
}
~~~

The assertions above are **expectations for the illustrative configuration and compatible Spring Security filter/registry behavior**. If a test fails, first check session registration in the registry, request matchers/chains, policy B, session ID rotation, lifecycle events, and how MockMvc simulates sessions. Do not drop the test merely because container and mock behaviors differ.

Concurrency tests should not run concurrently with other tests sharing the same username and registry without resetting state. Preferably use an isolated application context, distinct test principals, or proper state cleanup.

### 9.2. How to test idle timeout?

Do not use `Thread.sleep(15 * 60 * 1000)` inside MockMvc and treat it as a reliable test: mock sessions do not run schedulers/TTLs like an embedded container or distributed store. Better approaches:

- Unit test `InvalidSessionStrategy` to check status, body, cookie cleanup, and absence of redirect loops.
- Integration test with a **real embedded servlet container/session store**, a short timeout profile, a real request sequence, and real cookie jars.
- Separately test concurrency expiration with two sessions.
- Test session fixation by observing that the session ID rotated after login without logging its value.
- Test real browsers for cookie Path/Domain/SameSite/Secure behavior, especially after logout and with invalid cookies.

### 9.3. A bogus cookie in MockMvc is not always enough

Sending a `Cookie: JSESSIONID=bogus` header with MockMvc does not necessarily give the mock request the same `getRequestedSessionId()` and `isRequestedSessionIdValid()` behavior as a real servlet container. Therefore, do not infer “MockMvc sent a bogus cookie so `invalidSessionUrl` must run”. To verify invalid requested IDs, use a real container or test the strategy directly with a properly populated mock request.

### 9.4. @WithMockUser does not prove session concurrency

`@WithMockUser` can place a pre-built Authentication on the test thread. It is useful for authorization, yet does not create two browser sessions/logins via `SessionAuthenticationStrategy`. The “browser B kicks browser A” scenario must go through the real authentication flow and registry registration.

## 10. When should you return 302, 401, or 403?

There is no single one-to-one mapping between session reason and HTTP status:

- Web form login usually uses `302 Location: /login` for requests lacking authentication.
- APIs not using browser redirects usually return `401 Unauthorized` and a JSON/error contract.
- `403 Forbidden` typically reflects an authenticated user lacking permissions, or a POST rejected by the CSRF filter; do not treat every 403 as session expiration.
- Concurrency-expired can redirect to `expiredUrl`, or use a custom `SessionInformationExpiredStrategy` returning JSON/401.
- Browser B rejected at login for hitting `maximumSessions` goes through authentication failure handling, not guaranteed to be a fixed 401/403.

Never display “Someone else logged into your account” just because you see a 401. If the application needs to report a specific reason, obtain the reason code from a trusted event/concurrency handler rather than guessing from cookies or URLs.

### Handling error pages safely

Pages like `/session-invalid` and `/session-replaced` should be public. Verify invalid cookies are cleared or the strategy skips the error routes properly to avoid loops. A custom session strategy returning JSON can be clearer for SPAs; however, never expose session IDs, cookies, passwords, principals, or internal state in the response.

### Logout differs from timeout and superseded sessions

Proactive logout is an intentional action. It can invalidate the session, clear authentication, and delete cookies; it is not idle timeout. After logout, if the client resends the old `JSESSIONID`, the ID can be invalid. Do not use `expiredUrl` to represent logout as well.

### RequestCache and deep links

If a request is redirected to login, Spring Security may store the request in `RequestCache`. When the old session expires, the saved request may also be lost. When the user logs in again, never trust an arbitrary client-supplied `next` parameter to redirect externally; use controlled targets. Redirects do not grant access: the new request still passes through authorization.

## 11. Standalone Java 17: recognizing server-known signals

The following program **runs with JDK 17 alone**, simulating decisions based on: whether there is a requested session ID, whether the server still has the session, whether the registry marked it concurrency-expired, and whether a trusted ID rotation event occurred.

Notably, it **does not try to distinguish timeout from a fabricated ID** when both yield the exact same signal “session lookup failed”. This is the central lesson on the limits of observation.

Save file `SessionStatusDecisionDemo.java`:

~~~java
public class SessionStatusDecisionDemo {

    record Snapshot(boolean hasRequestedId,
                    boolean serverSessionExists,
                    boolean registryExpired,
                    boolean idWasRotated) {}

    static String classify(Snapshot s) {
        if (s.idWasRotated()) {
            return "ROTATED_ID_NOT_TIMEOUT";
        }
        if (!s.hasRequestedId()) {
            return "NO_SESSION_ID";
        }
        if (!s.serverSessionExists()) {
            return "INVALID_OR_EXPIRED_UNKNOWN_REASON";
        }
        if (s.registryExpired()) {
            return "CONCURRENCY_EXPIRED";
        }
        return "ACTIVE";
    }

    public static void main(String[] args) {
        System.out.println("new: " + classify(
            new Snapshot(false, false, false, false)));
        System.out.println("stale: " + classify(
            new Snapshot(true, false, false, false)));
        System.out.println("unknown-id: " + classify(
            new Snapshot(true, false, false, false)));
        System.out.println("superseded: " + classify(
            new Snapshot(true, true, true, false)));
        System.out.println("rotation: " + classify(
            new Snapshot(true, true, false, true)));
        System.out.println("active: " + classify(
            new Snapshot(true, true, false, false)));
    }
}
~~~

Compile and run:

~~~bash
javac SessionStatusDecisionDemo.java
java SessionStatusDecisionDemo
~~~

**Exact** stdout:

~~~text
new: NO_SESSION_ID
stale: INVALID_OR_EXPIRED_UNKNOWN_REASON
unknown-id: INVALID_OR_EXPIRED_UNKNOWN_REASON
superseded: CONCURRENCY_EXPIRED
rotation: ROTATED_ID_NOT_TIMEOUT
active: ACTIVE
~~~

The `classify` method is not a Spring API. It is a simple JDK model demonstrating that `stale` after timeout and `unknown-id` that never existed **cannot be distinguished when you only know lookup failed**. Accurate classification requires collecting lifecycle events, audits, or server-managed registry state—never trusting client-supplied request bodies/headers as proof.

## 12. Production incident diagnostics

When a user reports “I got kicked out of the system”, investigate:

1. **What authentication type does the request use?** Form login/session, HTTP Basic, OAuth2 login, or stateless Bearer JWT? If not session-based, do not start by debugging SessionRegistry.
2. **Is there a requested session ID?** Missing cookie differs from a bad old cookie. Avoid logging ID values.
3. **Did the server find an HttpSession?** Check TTL, session store, load balancer, restarts, and cookie attributes.
4. **Is there a session timeout/destruction event?** Only assert “idle timeout” based on trustworthy events.
5. **Does SessionRegistry know the session?** If the registry shows `SessionInformation.isExpired()` and the concurrency policy flagged it, that is solid evidence of “superseded”.
6. **Is maxSessionsPreventsLogin true or false?** Distinguish rejecting a new login vs. evicting an old session.
7. **Is HttpSessionEventPublisher/Spring Session integration wired properly?** Stale registry entries can skew active session counts.
8. **Was there session fixation rotation after login?** A changed ID can be normal security behavior.
9. **Which SecurityFilterChain is handling the request?** Are filters like `SessionManagementFilter` or `ConcurrentSessionFilter` running?
10. **Who generated the response?** `AuthenticationEntryPoint`, `InvalidSessionStrategy`, `SessionInformationExpiredStrategy`, `AccessDeniedHandler`, or failure/logout handler?
11. **Is there a redirect loop?** Check cookie path/domain and public error pages.
12. **Multiple nodes?** An in-memory registry may not see sessions on other nodes; proper distributed session coordination is needed.
13. **Re-test with two cookie jars**; avoid two tabs sharing the same cookie misleading your conclusions.

Example **application-defined** reason codes, not a built-in Spring Security enum:

~~~text
SESSION_IDLE_TIMEOUT
SESSION_ID_INVALID
SESSION_CONCURRENCY_EXPIRED
SESSION_ID_ROTATED
USER_LOGOUT
SESSION_REVOKED_BY_ADMIN
~~~

Emit `SESSION_IDLE_TIMEOUT` only when backed by evidence from the session store/lifecycle; `SESSION_ID_INVALID` merely reflects the request and should not assign an arbitrary cause. When correlating logs, use request IDs and safe metadata; **never log session cookies, raw session IDs, JWTs, or SecurityContexts containing credentials**.

## 13. Common mistakes

| Mistake | Consequence | Best practice |
| --- | --- | --- |
| “expiredUrl handles all timed-out sessions” | Concurrency page does not run on idle timeout | Use invalid-session/entry point as appropriate |
| “invalidSessionUrl proves idle timeout” | Misattributes logout/fake ID/rotation | Keep messaging neutral without a lifecycle event |
| “isRequestedSessionIdValid=false means kicked by login B” | Confuses a request signal with registry policy | Check SessionRegistry/concurrency events |
| “JSESSIONID changed after login means another login replaced me” | Confuses fixation protection with concurrent login | Distinguish session ID rotation |
| “maximumSessions(1) always forbids new logins” | Wrong UX/security expectations | Choose `maxSessionsPreventsLogin` per policy |
| “Two browser tabs are two different sessions” | Flawed concurrent-login tests | Two independent profiles/cookie jars |
| “RegistryExpired means session destroyed immediately” | Misunderstands when the filter acts | Test the old session's next request |
| “SessionRegistryImpl auto-syncs across all nodes” | Session limits bypassed across nodes | Use a cluster-compatible registry/store |
| “Old cookie auto-expires when server deletes session” | Stale cookies cause errors/loops | Invalidate cookies with matching Path/Domain |
| “Logout or invalidSessionStrategy is identical to timeout” | Inaccurate audit reports | Separate reason codes per event |
| “Expired JWT needs ConcurrentSessionFilter” | Mixes token validation with HttpSession | Handle bearer auth independently |
| “MockMvc definitely simulates real timeout” | Weak or misleading tests | Embedded server/session store integration |
| “Expired page still requires old authentication” | Redirect loops or repeated 401/302 | Public notice page and cookie cleanup |
| “401 is always a timeout” | Misdiagnoses password/token/session issues | Inspect entry point, provider, and safe logs |

## 14. Self-check exercises

**Question 1.** Alice logs in on browser A and stays idle past timeout. Later the browser sends the old cookie and the server finds no session. Can we conclude Alice was kicked out by browser B?

**Answer:** No. The server sees the requested ID is no longer valid; only a reliable timeout event lets you clearly state idle timeout. There is no evidence a concurrency policy replaced it.

**Question 2.** Alice logs in on A and B with `maximumSessions(1).maxSessionsPreventsLogin(false)`. Is B normally accepted or blocked?

**Answer:** B is accepted; the registry may mark session A expired per policy. When A sends a new request, `ConcurrentSessionFilter` handles it via the expired-session strategy.

**Question 3.** Switch to `maxSessionsPreventsLogin(true)`. Is A kicked out?

**Answer:** While A remains active and the limit is reached, B is denied the new login per policy; A continues working unless another cause invalidates it.

**Question 4.** A session ID changes after successful form login. Is that a timeout?

**Answer:** No. It is likely session fixation protection `changeSessionId()`. A new ID for the same authenticated session prevents session fixation; there is no need to report “session expired”.

**Question 5.** The browser sends `JSESSIONID=bogus` that never existed and receives a 302 to `/session-invalid`. Can we tell how long ago it timed out?

**Answer:** No. An ID that never existed can also be considered invalid. The strategy only has the invalid-ID signal; stating timeout duration requires other trustworthy server data.

**Question 6.** Why can a redirect loop to `/session-invalid` occur?

**Answer:** The browser keeps sending the invalid cookie to `/session-invalid` itself, and the strategy redirects again. You need public route handling and cookie cleanup with matching Path/Domain, rather than believing `permitAll` alone solves every case.

**Question 7.** An API uses Bearer JWTs, a token expires, and the server returns 401. Should you configure `expiredUrl` to handle it?

**Answer:** Not necessarily, and usually wrong. JWT token expiration belongs to bearer authentication/resource server, not `SessionRegistry` concurrency-expiration of HTTP sessions.

**Question 8.** An app runs two nodes with a shared Redis session store, yet `SessionRegistryImpl` lives in RAM on each node. Can you rely on `maximumSessions` to enforce a cluster-wide limit?

**Answer:** Not by default. Registry/cleanup must be integrated with a distributed session repository and matching events; one node's in-memory registry cannot automatically see sessions on other nodes.

**Question 9.** A test uses two tabs in the same browser; when tab B logs in again, tab A still appears logged in. Does that prove `maximumSessions` is broken?

**Answer:** No. Two tabs normally share cookies and may share a single session. Test with two profiles or two HTTP clients with separate cookie jars.

**Question 10.** A 403 response occurs after POST login. Can you conclude the session timed out?

**Answer:** No. The CSRF filter may have blocked the POST, authorization may have denied it, or another policy applied. Inspect which filter generated the response before determining the cause.

## 15. Adoption checklist

- [ ] Identify whether the system uses HTTP sessions, Spring Session, or Bearer JWTs; never use session handlers for unrelated token lifecycles.
- [ ] Understand that idle timeout and cookie lifetime are separate scopes; avoid guessing causes from cookies alone.
- [ ] Distinguish **timeout**, **invalid requested ID**, **concurrency expired**, and **fixation ID rotation** in events and UX.
- [ ] Verify whether `invalidSessionUrl/InvalidSessionStrategy` has an active filter running in your Spring Security 6 chain.
- [ ] Configure `maximumSessions` + `maxSessionsPreventsLogin` per requirements; do not overlook the true/false choice.
- [ ] Ensure `ConcurrentSessionFilter`/SessionRegistry works and session-destroyed events are reflected accurately.
- [ ] With multiple nodes, use a compatible distributed registry/session store integration; avoid local registries for cluster-wide policies.
- [ ] Enable appropriate session fixation protection, especially in custom authentication flows.
- [ ] Clear invalid cookies with matching Path/Domain/Secure/SameSite; keep error pages public and free of redirect loops.
- [ ] Test two cookie jars, new logins, subsequent requests on old sessions, logout, timeout, and ID rotation.
- [ ] Separate API status/JSON responses from browser redirects; never treat 401/302/403 as root-cause diagnostics.
- [ ] Log safely using evidence-backed reason codes without exposing session IDs or authentication secrets.

**Conclusion:** **Expired session** is a session-store lifecycle event; **invalid session** means the requested ID no longer resolves to a valid session; **superseded session due to concurrent login** is a state managed by `SessionRegistry`; **session ID rotation at login** is session fixation defense. Only by accurately distinguishing these four phenomena should you choose `invalidSessionUrl`, `expiredUrl`, UI messages, and testing strategies.