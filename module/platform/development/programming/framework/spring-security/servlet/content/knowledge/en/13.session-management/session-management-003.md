# Session lifecycle from login to expiration or revocation in Spring Security Servlet

## 1. The big picture

In a web application using **Spring Security Servlet** and form login, an HTTP session keeps the browser from having to resend the password on every request. However, “having a cookie”, “the server still has an HttpSession”, “having an Authentication”, “not expired yet”, and “not revoked yet” are **not the same state**.

A session can pass through these stages:

```text
Unauthenticated browser
      |
      | GET public page / intercepted request
      v
HttpSession may not exist yet, or may already be created for CSRF / saved request
      |
      | POST /login + CSRF token + credentials
      v
Authentication succeeds
      |
      +--> session fixation protection (rotates session ID per policy)
      +--> saves SecurityContext into the appropriate repository/session
      +--> browser receives/maintains session cookie
      |
      v
Authenticated session
      |
      +--> each valid request: identifies session,
      |    loads SecurityContext, authorizes, updates access time
      |
      +--> inactive for too long: expires due to timeout
      |
      +--> user sends POST /logout: logout/invalidate
      |
      +--> admin / security incident: revokes session
      |
      +--> concurrent sessions policy: marks old session expired
      |
      v
Request after session is no longer valid:
      anonymous / entry point / log in again (depending on configuration)
```

Lesson objectives:

1. Distinguish **Servlet HttpSession**, **session cookie**, **SecurityContext**, **Authentication**, and **SessionRegistry**.
2. Trace a session accurately from creation, through login and subsequent requests, to logout, timeout, or revocation.
3. Understand **session fixation protection**, session ID rotation, idle timeout, and concurrent-session policies.
4. Distinguish **actually deleting/invalidating the session** from **marking SessionInformation as expired**.
5. Configure and test the session lifecycle in Spring Boot 3 / Spring Security 6 / Java 17.
6. Avoid security mistakes: insecure cookies, GET logout, misidentifying sessions, multi-node management, and unintended authentication restoration.

The primary scope is **HTTP session-based form login**. Stateless HTTP Basic or bearer tokens may not need to store `Authentication` in a session via this mechanism.

## 2. Five easily confused objects

| Component | Role | What must not be inferred |
| --- | --- | --- |
| `HttpSession` | Server-side Servlet session state store, with session ID, attributes, timeout | Having a session does not mean logged in. |
| `JSESSIONID` or other session cookie | How the browser carries the session identifier across requests | The cookie is only an identifier; an old cookie does not guarantee the session still exists. |
| `Authentication` | Principal information, authentication status, and authorities | Not synonymous with session or cookie. |
| `SecurityContext` | Holds the Authentication used while processing a request | Current thread-local does not automatically persist to a new request. |
| `SecurityContextRepository` | Loads/saves SecurityContext in the appropriate place, often with a session-backed delegate | Does not by itself manage all logout, concurrent sessions, and revocation policies. |
| `SessionRegistry` (if used) | Tracks session information to enforce concurrent-session policies | A registry does not automatically delete every HTTP session at the exact moment `expireNow()` is called. |

### 2.1. HttpSession is a Servlet concept, not exclusive to Spring Security

`HttpSession` belongs to `jakarta.servlet.http`. Servlet containers such as Tomcat, Jetty, or Undertow manage the session lifecycle. Typical operations:

```java
HttpSession existing = request.getSession(false);
HttpSession createdIfNeeded = request.getSession(true);
int idleSeconds = createdIfNeeded.getMaxInactiveInterval();
long lastAccessedMillis = createdIfNeeded.getLastAccessedTime();
```

This is an **illustrative snippet placed in code that already has an `HttpServletRequest request` variable**, not a standalone runnable Java class.

- `getSession(false)` returns the existing session if present and valid, otherwise `null`; it does not create a session itself.
- `getSession(true)` creates a session if one does not exist.
- `getMaxInactiveInterval()` returns the maximum inactivity interval in seconds under the active policy; a negative value typically indicates no automatic inactivity timeout.
- `getLastAccessedTime()` is the most recent access timestamp according to the container; do not treat it as absolute proof of user activity, and it is not sufficient to authenticate a session.

### 2.2. Authentication and SecurityContext exist during the current request

Spring Security typically reads the context from `SecurityContextRepository` at the start of processing and makes `Authentication` available via `SecurityContextHolder`. When the request finishes, the processing thread's holder must be cleared according to the framework mechanism.

For example, a logged-in user sends:

```text
GET /account
Cookie: JSESSIONID=<id>

Servlet container locates HttpSession
    |
    v
SecurityContextRepository loads SecurityContext
    |
    v
SecurityContextHolder for current request sees Authentication
    |
    v
AuthorizationFilter checks permissions
    |
    v
Controller receives principal
    |
    v
SecurityContextHolder is cleared when processing finishes
```

`SecurityContextHolder` relies on thread-local by default; it **does not replace the repository**. If you create `Authentication` in a custom login handler without saving the context via the appropriate explicit-save mechanism, the current request may succeed while the next request is treated as anonymous.

### 2.3. A session cookie does not contain the entire user profile

In the common model, the browser holds a session identifier while state is kept on the server. Never pack passwords, secrets, or privilege data into cookies. Anyone possessing a valid session ID can hijack the session, so the session ID/cookie must be protected like a secret.

For APIs using self-contained JWT claims or other tokens, the lifecycle/revocation mechanism can be completely different; do not apply `HttpSession.invalidate()` logic to independent tokens.

## 3. Before login: a session may already exist

A common misconception is “an HttpSession is only created when login succeeds”. In many Servlet applications, a session can appear **before authentication**.

For example:

1. Browser opens `GET /private` while unauthenticated.
2. `ExceptionTranslationFilter` may save the original URL via `RequestCache`, e.g. `HttpSessionRequestCache`.
3. The form page may need a CSRF token; depending on `CsrfTokenRepository` and usage, a session can also be created to hold the token.
4. The browser receives a session cookie even though there is no verified `Authentication` yet.

Therefore, equating “has `JSESSIONID` = logged in” causes bugs. Authorization must rely on `Authentication` and policy, not on the presence of a cookie.

A two-request example before login:

```text
GET /private
    -> 302 /login
    -> may create an HttpSession to store SavedRequest

GET /login
    -> 200 login form
    -> may create/retrieve CSRF token from session
    -> user is still unauthenticated
```

The words **“may”** are intentional: session policy, lazy CSRF handling, `RequestCache`, the container, and authentication type affect when a session is created.

## 4. From POST /login to an authenticated session

Suppose the application enables default form login:

```text
POST /login
  username=reader
  password=...
  _csrf=...

UsernamePasswordAuthenticationFilter
       |
       v
AuthenticationManager / AuthenticationProvider
       |
       +-- invalid credentials: authentication failure
       |   typically redirects to /login?error
       |
       +-- valid credentials:
            |
            v
       SessionAuthenticationStrategy
         session fixation protection /
         concurrent-session handling if configured
            |
            v
       Creates SecurityContext holding Authentication
            |
            v
       Saves context via SecurityContextRepository
            |
            v
       AuthenticationSuccessHandler
         redirects to SavedRequest or default success target
```

This is a **conceptual** flow. Exact ordering among strategies or filters depends on version and configuration. Key takeaway: successful authentication is **one event**, whereas writing state, protecting the session ID, and redirecting are related but distinct steps.

### 4.1. Session fixation protection: why rotate the session ID?

Session fixation is an attack where an attacker tries to make a victim use a session ID the attacker already knew before login. If the server keeps that same ID when elevating an unauthenticated session to a privileged one, the attacker can continue using the known ID.

With appropriate Servlet support, Spring Security can invoke the **`changeSessionId()`** strategy after successful authentication to change the session identifier while preserving necessary session data.

```text
Before login:
  HttpSession ID = S_old
  authenticated = false

Successful login:
  session fixation protection

After login:
  HttpSession ID = S_new
  authenticated = true
  S_old is no longer a valid ID for that session
```

**Do not hardcode or log session IDs.** It is an effective browser credential. In tests, you can verify that the session ID changed when the configuration/container supports it; do not depend on a fixed ID string.

### 4.2. Strategies and trade-offs

Common choices in Spring Security Servlet:

- `changeSessionId`: uses the Servlet mechanism to change the existing session's ID; usually suitable for modern Servlet containers.
- `migrateSession`: creates another session and transfers attributes according to the framework strategy.
- `newSession`: creates a new session and avoids arbitrarily copying old application attributes (details depend on implementation).
- `none`: disables session fixation protection; **should not be chosen by default** because it can increase fixation risk.

Do not enable `none` just to keep the same ID in tests. When migration involves session attributes like a shopping cart, language, or saved request, test the chosen strategy in practice to avoid losing state or carrying unwanted data into the new session.

### 4.3. Saving context differs from saving the session ID

`SecurityContextRepository` can save `SecurityContext` in `HttpSession`. `SessionAuthenticationStrategy` supports session policies at login. Cookies/IDs are handled by the Servlet container. These three mechanisms collaborate, but they are not the same API.

In Spring Security 6, `SecurityContextHolderFilter` typically involves **explicit save**; with standard form login, the framework's authentication filter contains context-saving logic. If writing custom authentication, ensure `SecurityContextHolder.setContext` and `securityContextRepository.saveContext(context, request, response)` are executed at the right time before the response commits.

## 5. How is a session used and refreshed?

After login, the browser sends the session cookie on subsequent requests within the cookie's scope:

```text
GET /account  Cookie: JSESSIONID=<id>
  |
  +--> container locates session
  +--> SecurityContextRepository loads Authentication
  +--> Spring Security decides whether permissions are sufficient
  +--> controller returns response
  +--> container updates last access per its semantics
```

This lifecycle is usually a **sliding idle timeout**: each request that properly accesses the session can extend the inactivity expiration deadline. However:

- Not every asset request or background polling request necessarily accesses the same session.
- Continuous SPA requests can inadvertently keep a session alive too long, depending on routing and policy.
- Inactivity expiration is not “exactly 30 minutes after login” if the session is used continuously.
- `HttpSession` does not by default have an **absolute maximum lifetime**; if the product requires sessions to end after an absolute duration, an additional policy is needed.
- JavaScript timers or UI clocks are not the source of truth; the server/container decides whether the session is valid.

### 5.1. Idle timeout differs from absolute timeout

Example:

```text
Idle timeout policy = 30 minutes

10:00  login
10:10  GET /account        -> accessed
10:25  GET /notifications  -> if accessing the session, idle timer is updated again
10:50  GET /account        -> may still be valid because last access was 10:25
11:21  GET /account        -> may expire due to 31 minutes of inactivity
```

**This is a hypothetical example**: exact timestamps and when the container sweeps/invalidates sessions depend on deployment, environment, and how the session is accessed. There is no guarantee a session is deleted at exactly second 1,800 if no request arrives.

**Absolute timeout** places a cap from the originating event (login or session creation), e.g., rejecting sessions older than 8 hours even if the user is continuously active. This is a separate requirement and is not guaranteed solely by `server.servlet.session.timeout`.

### 5.2. Observing timeout with the Servlet API

In code that already has `HttpSession session`:

```java
int seconds = session.getMaxInactiveInterval();
session.setMaxInactiveInterval(30 * 60);
```

This is an example of setting an **idle timeout in seconds for one session**, not a standalone class. Make sure business code does not accidentally override the global session policy.

## 6. Paths that render a session unusable

### 6.1. Expiration due to inactivity (idle expiration)

The container or session store no longer considers the session valid because time since the last access exceeded the threshold. The browser may still send the old ID cookie, but the server can no longer load the corresponding `Authentication`; the request is typically treated as unauthenticated.

Timeout is **not** a user-initiated logout; do not rely on logout events to detect every expired session.

### 6.2. Logout requested by the session owner

A valid POST logout can run `LogoutFilter` and `LogoutHandler`s, clear authentication, invalidate `HttpSession`, clear the `SecurityContext` repository, and delete cookies per configuration. Afterward, the old session should no longer serve as proof that the user is logged in.

**Sending a POST request + CSRF token** is the common default when CSRF is enabled. Do not turn GET `/logout` into a side-effecting logout command without evaluating CSRF.

### 6.3. Revocation by an administrator or security policy

For example, the account is locked, the user reports a lost device, a password is leaked, or the system detects anomalous activity. You need the ability to make one or more sessions unusable.

There are multiple levels:

1. **Mark the session expired** in `SessionRegistry`; concurrent session control configuration can detect and terminate requests when the session is reused.
2. **Actually delete/invalidate the session** in the appropriate session store so new requests cannot restore `Authentication`.
3. **Revoke independent tokens** such as remember-me tokens or bearer tokens, if the application uses them. Invalidating `HttpSession` does not automatically revoke every token.

Saying “revoked” while only updating a boolean in the accounts table while all old sessions remain trusted is **insufficient** if the requirement is to block all subsequent requests immediately.

### 6.4. Invalidation due to concurrent sessions policy

For example, an account is allowed at most one session. When logging in from another browser, the server can reject the new login or mark the old session expired depending on policy. This is **different** from idle timeout and different from manual logout.

### 6.5. Restart, failover, or session store failure

If sessions are stored in a single JVM's memory, a restart can lose sessions. In a multi-node system, a cookie can route a request to another node that does not know the session unless sticky routing or a shared session store is used. That is **loss of session recovery capability**, not equivalent to the user actively logging out.

## 7. Expired, invalid, revoked, and logged out: do not conflate them

| State / phenomenon | Common mechanism | Observable on next request | Notes |
| --- | --- | --- | --- |
| Idle timeout | Servlet container/session store expires due to inactivity | Session ID rejected, anonymous user, or login redirect | Cleanup timing may not match an exact wall-clock mark. |
| Logout | `LogoutFilter` / logout handlers invalidate session and clear context | Does not restore user from destroyed session | Browser may keep stale cookie if cookie clearing mismatches path/domain. |
| SessionInformation.expireNow | `SessionRegistry` marks session info as expired | `ConcurrentSessionFilter` can handle the expired session when the next request passes through | Marking does not immediately delete stored sessions in every system. |
| Deleting session in distributed store | Appropriate session store API such as `SessionRepository` | Next request cannot read the session | Must account for caches, replication, and in-flight request races. |
| Stale cookie/session ID | Client sends an identifier the server no longer recognizes | Anonymous, invalid session handling per config | Never use cookie presence as proof of authority. |
| User locked in DB | Account status changed | New logins usually rejected; old sessions may still work | Need revalidation/revocation policy for active sessions. |
| Deleting separate access token | Blacklist/revocation per token mechanism | Result depends on token verifier | Do not handle via `HttpSession.invalidate()` if the token is independent. |

### 7.1. "Invalid session" does not necessarily mean the user just logged out

An `invalidSessionUrl("/session-invalid")` configuration can handle requests when a client sends an old session ID that is no longer valid. However, after logout, a browser sometimes still carries the old cookie; if not configured carefully, users may see an “invalid session” page even though they just logged out normally.

**Do not merge** “session expired”, “session invalid”, and “logout success” messages into a guess about what caused the event. Distinguishing them accurately requires server-side state, cookie/session policy, and event logs.

## 8. Proper logout in Spring Security Servlet

With form login, logout configuration is part of the security chain:

```java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/login?logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
);
```

This is a **configuration snippet** inside a `SecurityFilterChain` bean that has `HttpSecurity http`. It is not a standalone runnable program.

Explanation:

- `logoutUrl("/logout")` specifies the path that processes logout.
- `logoutSuccessUrl("/login?logout")` determines where to redirect after a successful website logout.
- `invalidateHttpSession(true)` requests invalidating the current session.
- `clearAuthentication(true)` clears `Authentication` from the security context during the logout flow.
- `deleteCookies("JSESSIONID")` attempts to instruct the browser to delete the corresponding cookie in the response; cookie deletion depends on the actual name/path/domain.

Spring Security has default logout handlers managing `SecurityContext`; do not just call `SecurityContextHolder.clearContext()` yourself in a controller and call it logout, because the old session or repository may still hold `Authentication`.

**CSRF:** with CSRF protection enabled, POST `/logout` requires a valid token. GET `/logout` in default configuration typically serves a logout confirmation page rather than logging out directly; details depend on Spring Security version and UI.

### 8.1. A logout redirect is not proof the session was invalidated

A 302 response to `/login?logout` only shows the navigation flow. To verify the server invalidated the session, test `MockHttpSession.isInvalid()` after POST logout, or observe the session store/events in a controlled manner.

Conversely, if the cookie fails to delete due to Path/Domain, **server-side invalidation** remains the primary safeguard. A stale cookie must never re-grant access merely because it remains in the browser.

### 8.2. Does logout revoke all devices?

No. Default logout typically handles **the current request's session**. If a user has sessions on both a laptop and a phone, logging out on the laptop does not automatically ensure the phone session is deleted.

A “logout all devices” requirement needs a dedicated design step: managing the session list, revoking in the corresponding repository or registry, defining policy for remember-me/tokens, and ensuring multiple nodes share the same state.

## 9. Session revocation via SessionRegistry and concurrent sessions

### 9.1. What does SessionRegistry store?

Spring Security Servlet provides `SessionRegistry` to track sessions in certain concurrent-session management mechanisms. A common implementation is `SessionRegistryImpl`.

Typical operations:

- `getAllPrincipals()`: looks up principals currently tracked by the registry.
- `getAllSessions(principal, includeExpiredSessions)`: retrieves `SessionInformation` entries registered for the principal.
- `SessionInformation.expireNow()`: **marks** the session information as expired.
- `refreshLastRequest(sessionId)` or framework registry lifecycle management: updates/tracks metadata via the appropriate mechanism.

**Illustrative code** example with `sessionRegistry` and a verified `principal` in an administrative application service:

```java
List<SessionInformation> sessions =
    sessionRegistry.getAllSessions(principal, false);

for (SessionInformation info : sessions) {
    info.expireNow();
}
```

Imports are in `org.springframework.security.core.session` for `SessionRegistry` and `SessionInformation`, along with `java.util.List`. This snippet is **not a complete REST controller** and does not prove every currently executing request has been terminated immediately.

### 9.2. Why expireNow is not immediate session deletion

`expireNow()` sets a flag in the registry. With `ConcurrentSessionFilter` and an appropriate expired-session strategy, **the next request** for the flagged session can be handled, logged out/invalidated, and redirected per configuration.

Risks to remember:

- A request that already started before being flagged may continue if there are no additional checkpoints.
- If a request does not pass through a chain containing `ConcurrentSessionFilter`, the expired flag may not be handled as expected.
- A registry stored only in one node's memory may not cover sessions residing on other nodes.
- An unregistered session or mismatched principal equality will not appear properly in queries.
- Timeout/invalidation events must be reflected into the registry, otherwise data can become stale.

Therefore, if **near-immediate, cross-node revocation** is required, design a shared session store or check revocation status at an appropriate request boundary, rather than merely calling `expireNow` and claiming all sessions disappear instantly.

### 9.3. Limiting concurrent sessions

An example configuration that can be added to a **web chain**:

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(false)
    .expiredUrl("/session-expired")
);
```

With `maximumSessions(1)`, the goal is to limit to one concurrent login session per principal. With `maxSessionsPreventsLogin(false)`, a new login can cause the old session to be marked expired instead of rejecting the new login. `expiredUrl` is the navigation URL of the expired-session strategy when a request is detected as expired.

This is a **configuration fragment** for learning, not behavior enabled in the complete application below. For production use, also review `SessionRegistry`, `HttpSessionEventPublisher`, topology, and how session expiration is handled.

You can register a publisher to handle HTTP session lifecycle events in the appropriate Servlet configuration:

```java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
```

The corresponding types are in `org.springframework.security.web.session.HttpSessionEventPublisher` and `org.springframework.context.annotation.Bean`. When using Spring Boot, verify that the listener is registered and receiving events in the actual runtime environment. Without an appropriate publisher/event tracking, the registry may retain invalidated sessions as if they still exist.

### 9.4. Difference between concurrency control and absolute lifetime

`maximumSessions` limits the number of sessions by policy; it does **not** replace idle timeout or an absolute lifetime limit. A single session can still live very long if accessed continuously without an absolute-expiry policy.

## 10. Revoking sessions in multi-instance systems

Simple deployment model:

```text
Browser JSESSIONID=S1
        |
        v
Load balancer
    |         |
  Node A    Node B
    |         |
  Local      Local
  session    session
  store      store
```

If Node A and Node B have independent session stores, Node B may be unable to find session S1. A system can use sticky routing to mitigate this, but sticky routing by itself creates no global revocation mechanism and does not guarantee survival if a node goes down.

Another design uses a shared session repository, such as **Spring Session** with a suitable backend:

```text
Browser session ID
      |
   Load balancer
      |
   +-- Node A ----+
   |              |
   +-- Node B ----+---- Shared Session Store
   |              |
   +-- Node C ----+
```

In that model, the application can implement revocation using the session store API, e.g., finding session IDs belonging to a user and deleting sessions via `SessionRepository` after verifying authorization. You must account for caches, eventual consistency, transactions, and in-flight requests.

**Never build a public “DELETE /session/{id}” endpoint** letting clients delete arbitrary IDs. Session management features require strong authentication, owner/admin authorization, rate limiting, auditing, and avoiding exposing session IDs.

### 10.1. Revocation when a password changes or an account is locked

Two approaches are commonly considered:

- **Block immediately on the next request:** delete/revoke active sessions or check a security stamp/version at the request boundary.
- **Block on the user's next login:** only update account flags/password in the DB.

These two choices offer different protection levels. If policy states “changing password must log out all devices”, implement or prove a mechanism that actually revokes old sessions; changing the password hash **does not automatically invalidate `Authentication`** already stored in an active session.

### 10.2. Remember remember-me and secondary tokens

If the application enables remember-me or issues separate bearer tokens, the browser may be re-authenticated after the HTTP session expires depending on configuration. Logout/revocation must handle those tokens per policy; otherwise, the session may “come back” due to auto-login.

Do not use `SessionRegistry` to claim a stateless JWT is revoked if every request only checks signature/token expiry with no revocation check.

## 11. Runnable Spring Boot 3.3.5 + Java 17 application

The example below focuses on the typical session lifecycle with **form login, session fixation protection, configured timeout, and logout**. **Concurrent-session control** and **all-device revocation** are kept separate from the runnable app because they require dedicated registries, policies, and topology.

### 11.1. Structure

```text
session-lifecycle-demo/
  pom.xml
  src/
    main/
      java/example/session/
        SessionDemoApplication.java
        SecurityConfig.java
        SessionController.java
      resources/
        application.properties
    test/
      java/example/session/
        SessionLifecycleTest.java
```

### 11.2. Maven configuration

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>session-lifecycle-demo</artifactId>
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
```

### 11.3. Main class

File `src/main/java/example/session/SessionDemoApplication.java`:

```java
package example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
```

### 11.4. SecurityConfig: session-aware form login and logout

File `src/main/java/example/session/SecurityConfig.java`:

```java
package example.session;

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
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("training-only"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId()))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"));

        return http.build();
    }
}
```

Notes:

1. `IF_REQUIRED` allows Spring Security to use a session when needed; it does not require creating a session for every request.
2. `changeSessionId` enables session fixation protection using the corresponding Servlet mechanism.
3. `formLogin(Customizer.withDefaults())` uses the `/login` page provided by Spring Security, without needing to write a custom controller for POST login.
4. `logout` ensures a flow to destroy the current session; **POST `/logout` requires CSRF** when CSRF is enabled.
5. The illustrative account/password is for localhost learning only. Production requires an appropriate user store, HTTPS, secret management, and login abuse controls.
6. Do not configure `SessionCreationPolicy.STATELESS` because this lesson needs to persist `Authentication` across an HTTP session.

### 11.5. Controller with a protected endpoint

File `src/main/java/example/session/SessionController.java`:

```java
package example.session;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/")
    String publicHome() {
        return "home";
    }

    @GetMapping("/account")
    String account(Authentication authentication) {
        return "hello " + authentication.getName();
    }
}
```

`GET /account` only runs after the request is authenticated. Even though the controller does not access `HttpSession` directly, Spring Security has already handled loading `Authentication` from the repository inside the security filter chain.

### 11.6. Idle timeout and cookie policy (application.properties)

File `src/main/resources/application.properties`:

```properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

In this example, `30m` is the desired **inactivity duration**, not an absolute 30 minutes after login. The actual value can be affected by container/session repository and deployment settings. `HttpOnly` restricts JavaScript from reading the cookie, and `SameSite=Lax` helps mitigate some cross-site risks; **neither replaces CSRF tokens and authorization**.

In production running HTTPS, configure the `Secure` attribute for cookies and properly configure reverse-proxy/trust headers. Do not force `Secure` in the HTTP localhost sample because browsers may withhold cookies over mismatched connections. In practice, consider cookie `Path`, `Domain`, `SameSite` policy, TLS, and load balancers.

### 11.7. MockMvc tests: login, session usage, logout, CSRF

File `src/test/java/example/session/SessionLifecycleTest.java`:

```java
package example.session;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicHomeDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/"))
            .andExpect(status().isOk())
            .andExpect(content().string("home"));
    }

    @Test
    void protectedPageRedirectsAnonymousToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void loginCreatesAuthenticatedSessionForNextRequest()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "training-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        HttpSession raw = login.getRequest().getSession(false);
        assertNotNull(raw);

        MockHttpSession session = (MockHttpSession) raw;

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello learner"));
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong-password"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"));
    }

    @Test
    void logoutInvalidatesCurrentSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "training-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsRejected() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "training-only"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        assertTrue(!session.isInvalid());
    }
}
```

Explanation:

- The public test needs no login session.
- The anonymous test checks that the protected route leads to login. **Note:** the redirect URL may be absolute or relative depending on the entry point/test environment; this test uses the default servlet login entry point in Spring Boot 3.3.x and expects `http://localhost/login`. If proxy/base URL changes, assert the equivalent target rather than hardcoding the host.
- The login test uses POST with a valid CSRF token, retrieves `MockHttpSession` after authentication, and reuses it on the next GET.
- The logout test uses POST with CSRF and asserts `session.isInvalid()` rather than only accepting a 302 redirect.
- The missing-CSRF test gets 403 and the session is not logged out; testing a CSRF failure is not testing a password.
- The tests do not simulate 30 minutes of real elapsed time; timeout belongs to the container/session store and should have separate integration tests or a controlled clock/test environment.

### 11.8. Trying it out

In the `session-lifecycle-demo` directory with Maven/JDK 17+:

```bash
mvn test
mvn spring-boot:run
```

If dependencies and environment match, **six tests are expected to pass**. Maven stdout will vary by machine, timestamps, and runtime; do not treat a sample log string as an actual run result.

When running locally, open:

```text
http://localhost:8080/
http://localhost:8080/account
http://localhost:8080/login
```

You can observe the lifecycle with browser devtools: the login request creates/rotates the session ID per policy, subsequent requests send the cookie, logout returns a cookie-clearing response/redirect, and the session is destroyed on the server. **Do not capture/share session cookie values or paste them into public logs.**

## 12. Standalone Java 17: state model distinguishing timeout, revoke, and logout

The following example intentionally avoids Spring; it uses simulated timestamps to produce **deterministic** stdout. This is an **educational model**, not the algorithm of a Servlet container or `SessionRegistry`.

Create `SessionLifecycleModel.java`:

```java
public class SessionLifecycleModel {

    enum State {
        ACTIVE, IDLE_EXPIRED, REVOKED, LOGGED_OUT
    }

    record Session(long lastAccessMillis,
                   boolean revoked,
                   boolean loggedOut) {}

    static State stateAt(Session session, long nowMillis,
                         long idleTimeoutMillis) {
        if (session.loggedOut()) {
            return State.LOGGED_OUT;
        }
        if (session.revoked()) {
            return State.REVOKED;
        }
        if (nowMillis - session.lastAccessMillis() >= idleTimeoutMillis) {
            return State.IDLE_EXPIRED;
        }
        return State.ACTIVE;
    }

    public static void main(String[] args) {
        long minute = 60_000L;
        long idleTimeout = 30 * minute;

        Session initial = new Session(0, false, false);
        System.out.println("just logged in: " +
            stateAt(initial, 0, idleTimeout));

        System.out.println("31 min idle: " +
            stateAt(initial, 31 * minute, idleTimeout));

        Session recentlyUsed = new Session(20 * minute, false, false);
        System.out.println("used recently: " +
            stateAt(recentlyUsed, 31 * minute, idleTimeout));

        Session revoked = new Session(20 * minute, true, false);
        System.out.println("revoked: " +
            stateAt(revoked, 31 * minute, idleTimeout));

        Session loggedOut = new Session(20 * minute, false, true);
        System.out.println("logged out: " +
            stateAt(loggedOut, 31 * minute, idleTimeout));
    }
}
```

Compile/run:

```bash
javac SessionLifecycleModel.java
java SessionLifecycleModel
```

**Exact** stdout on Java 17+:

```text
just logged in: ACTIVE
31 min idle: IDLE_EXPIRED
used recently: ACTIVE
revoked: REVOKED
logged out: LOGGED_OUT
```

The model shows four distinct reasons why the current state changes. In a real Servlet environment, “idle expired” may be decided and processed by the container/remote store during sweeps or when the next request arrives; “revoked” may be a registry marker or store deletion. The model creates no cookies, session IDs, thread-locals, or HTTP filters.

## 13. Common mistakes

| Mistake | Consequence | Understanding / fix |
| --- | --- | --- |
| “Having JSESSIONID means logged in” | Anonymous/CSRF sessions get treated as authenticated | Rely on Authentication/authorization and server-side state. |
| “No session exists before POST login” | Confuses sessions used for CSRF or SavedRequest | A session may be created before login. |
| “Keeping the same session ID on successful login is always fine” | Risk of session fixation | Use appropriate session fixation protection. |
| “Changing the session ID deletes all old state” | May mispredict attribute migration | Test the `changeSessionId`/`migrate`/`newSession` strategy. |
| “Setting timeout=30m logs out exactly 30m after login” | Confuses inactivity with absolute lifetime | Distinguish idle vs. absolute timeout. |
| “Expired cookie means server state is deleted” | Server may retain the session for a period | Manage server-side lifecycle, not just UI/cookies. |
| “Deleting JSESSIONID with JS is logout” | Server can still hold a valid session if the ID is known | Protected POST logout, server-side invalidate/clear context. |
| “clearContext is enough” | Context in session/repository may remain | Use standard `LogoutFilter`/logout handlers. |
| “GET logout is always safe” | Can be triggered unintentionally / via CSRF | Keep CSRF protection for logout actions. |
| “expireNow() destroys sessions immediately on every node” | Only marks the registry; other requests may remain alive | Design request-time enforcement or delete from shared store. |
| “Locking a user in DB expires all sessions immediately” | Old Authentication in sessions may still work | Implement explicit revoke/revalidation for active sessions. |
| “maximumSessions(1) equals absolute timeout” | A single session can live long if active | Add a separate absolute policy if required. |
| “SessionRegistryImpl is cluster-wide” | Sessions/expirations across nodes are out of sync | Use a suitable shared registry/store or another distributed design. |
| “Logging out one device logs out all devices” | Other sessions are not destroyed | Manage session list and authorized/audited revoke-all functionality. |
| “HttpOnly prevents CSRF automatically” | Browsers still attach cookies automatically | Use CSRF protection, SameSite, and an appropriate threat model. |
| “SameSite replaces CSRF tokens” | Some browsers/scenarios are insufficiently protected | Design defense in depth. |
| “Destroying the session also kills tokens/JWTs” | Independent tokens may remain valid | Manage token revocation/expiry separately. |
| “MockMvc 302 redirect proves the session logged out” | Redirect can happen without invalidating the session | Assert server-side invalidation/session store. |
| “Putting session IDs in analytics logs helps safe debugging” | Leaks credentials capable of session hijacking | Never log raw session identifiers; use trace IDs instead. |

## 14. Session security and incident response

### 14.1. Cookies and transport

- Enforce HTTPS in production; session cookies should have appropriate `Secure` and `HttpOnly` flags.
- Set `SameSite` according to legitimate application needs and CSRF policy.
- Restrict `Domain` and `Path` to avoid sending cookies unnecessarily to other apps/subdomains.
- Never put session IDs in URLs to prevent leaks via history, logs, `Referer`, or copied links.
- Use a session fixation protection strategy; never hardcode or issue predictable session IDs.
- Never output session cookies in response bodies or metric labels.

### 14.2. Defending against session hijacking

Anomalous signals such as a session used on an unfamiliar device, sudden IP/device changes, or account takeover must be evaluated with appropriate false-positive handling. The system can require reauthentication for sensitive actions, rotate session IDs at appropriate times, revoke sessions, and audit events.

**Reauthentication** is not merely checking `SecurityContextHolder.getContext().getAuthentication().isAuthenticated()`: the authenticated status from the session may already be stale. For sensitive actions, enforce a policy to re-verify credentials/MFA or check controlled authentication freshness.

### 14.3. In-flight requests during revocation

Nothing guarantees that a revoke command at time T can “strip authorization” from a request already authorized before T. Sensitive operations may need to check account/permission state at the executing transaction or commit point, especially when policy demands immediate blocking.

This is the difference between **stopping new requests from gaining access** and **canceling all work currently in progress**. Session invalidation typically handles the first part; long-running tasks, async jobs, streams, or WebSockets require additional consideration.

### 14.4. Protecting session management endpoints

Features such as “view active sessions”, “log out other devices”, or “revoke all sessions” must:

1. Verify the session owner's identity and admin privileges if applicable.
2. Have CSRF protection or API authentication matching the threat model.
3. Prevent users from arbitrarily choosing/guessing another user's session identifier.
4. Audit critical events without writing real session IDs to logs.
5. Apply rate limiting to prevent abuse disrupting other accounts.
6. Clarify revocation for remember-me tokens, refresh tokens, or sessions on other applications.

## 15. Symptom-based diagnostics

### 15.1. Login succeeds but the next request is anonymous

Check in order:

1. Did HTTP `POST /login` actually succeed or just redirect to `/login?error`?
2. Did session fixation protection change the ID; is the browser/test using the new cookie/session?
3. Did `SecurityContextRepository` save `Authentication` after login? Did a custom login handler forget explicit save?
4. Do the cookie's Domain/Path/SameSite/Secure attributes match the HTTPS/proxy environment?
5. Is the browser sending the cookie on the next request? Are third-party cookies blocked or did domains change?
6. Did the application configure `SessionCreationPolicy.STATELESS` or `NullSecurityContextRepository` for that route?
7. Did the request pass through a different `SecurityFilterChain`?
8. Was the session store lost due to restart, failover, or too short a timeout?

### 15.2. User gets logged out unexpectedly

Could be idle timeout, concurrent-session expired strategy, actual logout, lost connection to the session store, deploy/restart, or mis-sent cookies. Distinguish via proper event logs/metrics rather than relying solely on the client seeing the login screen.

### 15.3. User logged out yet remains authenticated upon returning

Check:

- Did the request actually hit `POST /logout` with valid CSRF and enter the right security chain?
- Is a custom handler only redirecting without invalidating the session?
- Does `SecurityContextRepository` still hold `Authentication` due to custom code?
- Is the old cookie still tied to a valid server session?
- Is there remember-me, SSO, or a token automatically logging back in?
- Are there other sessions on other devices still valid?

### 15.4. Revoked a session yet requests from another node still succeed

Evaluate whether the session store is shared or local, which node's `SessionRegistry` was updated, shared registry/replication, caches, and request-time revocation checks. Review race conditions and session expiration events before concluding a single `expireNow()` call suffices.

### 15.5. Enabling logging at the right level

In development environments you can use:

```properties
logging.level.org.springframework.security=DEBUG
```

DEBUG logs help observe the security chain, authentication, and certain filter decisions; they do not mean the framework always logs every session event. To confirm timeouts and revocations, inspect container/session repository metrics, event listeners, and integration tests. **Never log passwords, raw session IDs, cookies, or bearer tokens.**

## 16. Reasoning exercises and answers

**1.** A user has not logged in yet, but the browser receives `JSESSIONID` after opening `/login`. Is that a bug?

**Answer:** Not necessarily. A session may be created to hold a CSRF token or saved request, even while the user remains anonymous.

**2.** The browser receives a new session ID upon successful login. Why?

**Answer:** Session fixation protection reduces the chance an attacker reuses an ID known before the victim logged in. It is not a sign the user logged themselves out.

**3.** Idle timeout is configured to 30 minutes. A user calls `/account` every 10 minutes for 2 hours. Is the session guaranteed to expire 30 minutes after login?

**Answer:** No. Idle timeout depends on inactivity duration, not absolute maximum lifetime. Requests that properly access the session can refresh last-access time.

**4.** After POST logout with valid CSRF, the browser still sends the old `JSESSIONID` cookie. Is the user still logged in?

**Answer:** No. If the server session was invalidated, a stale cookie cannot prove valid Authentication. Check server-side state.

**5.** An admin calls `SessionInformation.expireNow()` while the browser has a long-running request in flight. Is that request terminated immediately?

**Answer:** No guarantee. The expired marker may be processed on the next request by the concurrent-session mechanism; a previously authorized request may continue. Additional check policies are needed for sensitive operations.

**6.** One account has two sessions, A and B. The user sends POST logout on A. Is B deleted?

**Answer:** Not by default. Current logout normally only handles the request's session; revoking all devices requires a dedicated mechanism.

**7.** An account is locked after login. Does an existing session containing `Authentication` automatically become invalid?

**Answer:** Do not assume so. If business policy requires blocking requests after locking, explicit session revocation/revalidation is needed.

**8.** The session cookie has `HttpOnly` and `SameSite=Lax`. Can all CSRF protection be removed?

**Answer:** No. `HttpOnly` does not stop the browser from attaching cookies; `SameSite` mitigates some cross-site requests but does not always replace CSRF tokens and other controls.

**9.** In a multi-node system, does calling `expireNow()` on Node A's local registry guarantee Node B rejects that session?

**Answer:** No. Shared state or a revocation design enforced across all nodes is needed, along with understanding synchronization latency.

**10.** Why does a test asserting only a redirect to `/login?logout` fail to prove logout is secure?

**Answer:** Redirect is only navigation. You must verify the server session was invalidated and context is no longer restored on the next request, while also analyzing secondary tokens.

## 17. Practical summary

- **Before login**, `HttpSession` may already be created for CSRF/`SavedRequest`; having a cookie does not imply having `Authentication`.
- **After login**, Spring Security authenticates, applies session fixation protection, saves `SecurityContext`, and responds; the browser uses the session cookie on subsequent requests.
- **During the session**, every request still passes through authentication context loading and authorization; idle timeout depends on last access, not absolute expiry from login.
- **Logout** must run the proper `LogoutFilter` flow, typically POST with CSRF, invalidating `HttpSession` and clearing context; do not replace it with deleting cookies in JavaScript.
- **Inactivity expiration**, **logout**, **concurrent-session expired**, and **intentional revocation** differ in cause and mechanism.
- `SessionInformation.expireNow()` **marks** the session in the registry; do not claim it immediately deletes sessions across all nodes or halts in-flight requests.
- For **logout all devices / account compromise**, a registry or shared session store, access control, auditing, and management of secondary tokens outside the HTTP session are required.
- Minimum tests: anonymous cannot access protected pages, login creates an authenticated session, subsequent requests use the right session, logout genuinely invalidates the session, and logout without CSRF is blocked.
