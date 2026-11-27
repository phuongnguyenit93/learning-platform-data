# Managing Login Sessions with Spring Session and Integration Boundaries

In a Java web application, a **login session** helps the server remember an authenticated user across multiple HTTP requests. If you only use an HTTP session stored in the memory of a single application instance, scaling up replicas, restarting an instance, or routing requests through a load balancer can cause users to lose their login state.

**Spring Session** solves an important part of this problem by replacing the servlet container's default session store with a shared `SessionRepository`. When using **Spring Session Data Redis**, multiple application instances can read, update, and invalidate sessions through Redis; the browser only holds a session ID in a cookie.

However, putting sessions in Redis does not automatically create a complete authentication system. You must distinguish clearly:

- **Spring Security** decides identity, access permissions, login/logout flows, session fixation protection, and `SecurityContext` management.
- **Spring Session** manages the lifecycle and storage of server-side HTTP sessions through the repository, TTL, and session ID.
- **Redis** is the shared session data store, with its own characteristics regarding timeouts, replication, persistence, memory, and failover.
- **The browser cookie** carries the session ID and should not contain passwords, sensitive authorization details, or the entire session content.
- **The database/identity provider** remains the source of truth for accounts, lock status, passwords, roles, and security decisions that must be re-verified.

This lesson implements a sample **Spring MVC (Servlet) + Spring Security + Spring Session Data Redis** application, then dives into integration boundaries with WebFlux, Redis Cluster, tokens, transactions, serialization, and production operations.

## 1. Why Move Login Sessions Out of Application Memory?

Suppose a system has three instances running behind a load balancer:

```text
                     Browser
                        |
                 Cookie: SESSION=abc
                        |
                  Load Balancer
                        |
              +---------+---------+
              |         |         |
              v         v         v
           App A      App B      App C
          Session A  Session B  Session C
          (local)    (local)    (local)
```

If a user logs in through App A but the next request is sent to App B, App B might not know about the session just created on A. Some infrastructures work around this temporarily with **sticky sessions**: keeping a browser's requests on the same instance. This approach has limitations:

- An instance dying or being redeployed can cause sessions to be lost.
- Scaling replicas up/down and load balancing become more complex.
- Session data lives in instance memory, making it hard to invalidate across multiple replicas.
- There is no shared store to administer session lifecycles.

Moving sessions into Redis:

```text
                        Browser
                           |
                   Cookie: SESSION=abc
                           |
                     Load Balancer
                           |
                 +---------+---------+
                 |         |         |
                 v         v         v
               App A     App B     App C
                 |         |         |
                 +---------+---------+
                           |
                           v
                       Redis
                Session id = abc
                SecurityContext
                lastAccessedTime
                maxInactiveInterval
                attributes
```

Each instance receives the same session ID and queries the shared repository. When instances share the **same namespace configuration, serializer, compatible Spring Session/Security versions**, and an appropriate Redis cluster, users can continue their session even when requests are routed to another instance.

**Redis here acts as a shared session store**, not a cookie copy sent to every server. The browser still stores only the session identifier; the application reads session data on the Redis side.

## 2. How Does Spring Session Replace the Default HttpSession Mechanism?

At the Servlet layer, Spring Session provides a filter that routes the application's `HttpSession` through a `SessionRepository`.

```text
HTTP Request
     |
     v
SessionRepositoryFilter
     |
     +-- Read session ID from cookie
     |
     +-- Look up SessionRepository in Redis
     |
     +-- Wrap HttpServletRequest/Response
     |   with HttpSession managed by Spring Session
     |
     v
Spring Security Filter Chain
     |
     +-- Read/write SecurityContext if session is used
     |
     v
Controller / Service
     |
     +-- request.getSession()
     +-- session.setAttribute(...)
     |
     v
SessionRepositoryFilter saves changes per configuration mode
     |
     v
HTTP Response with cookie if needed
```

Key components:

| Component | Role |
|---|---|
| `HttpSession` | Familiar Servlet HTTP session API |
| `SessionRepository<S extends Session>` | Contract for creating, finding, saving, and deleting sessions |
| `RedisSessionRepository` | Implementation that stores sessions in Redis without requiring advanced indexing features |
| `RedisIndexedSessionRepository` | Implementation capable of indexing/looking up sessions by attributes such as principal in suitable configurations |
| `SessionRepositoryFilter` | Connects `HttpSession` with `SessionRepository` at the filter layer |
| `HttpSessionIdResolver` | Defines how the session ID is extracted/returned, usually via cookies |
| `CookieSerializer` | Customizes cookie name, path, domain, and attributes |
| `SecurityContext` | Authentication information managed by Spring Security |
| Redis | Stores session data according to the implementation's structures, keys, and TTL |

Spring Session does not replace `UserDetailsService`, an OAuth2/OIDC provider, or `AuthenticationManager`. It stores the session used by the application and security filters; it does not verify passwords or grant permissions itself.

### 2.1. Having a Session Does Not Mean the User Is Logged In

An application may create an `HttpSession` before a user logs in—for example, to hold a CSRF token or UI preferences. Therefore:

```java
HttpSession session = request.getSession(false);
boolean hasSession = session != null;
```

only answers **whether the request has a current session**, not whether the user is authenticated.

To check login status, use Spring Security mechanisms such as `Authentication` or `SecurityContextHolder` within the appropriate request boundary, and check authentication state according to the application's policy.

### 2.2. Which Model Do Spring Session and HttpSession Follow?

In the main examples of this lesson, we use **Spring MVC / Servlet**. If the application is **reactive Spring WebFlux**, the session API is `WebSession` with the corresponding reactive repository/filter. Do not mix Servlet `HttpSession` with WebFlux `WebSession` as though they were the same interface.

This affects how the principal is obtained, how context is handled, where security is configured, and the Redis storage mechanism.

## 3. Dependencies for a Spring Boot Application

An example Spring Boot application running Spring MVC, Spring Security, and Spring Session Redis uses these dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'
}
```

In some ecosystems/versions, starter names or dependency management may vary. What matters is that the Spring Session Redis, Spring Security, Spring Data Redis, and driver libraries are managed compatibly by the Spring Boot version in use.

Typically, Spring Boot can auto-configure Spring Session Redis when dependencies and the Redis connection are set up properly. You should not both enable auto-configuration and manually create multiple overlapping repository/filter beans without clearly defining their roles.

### Basic Configuration in application.yml

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s

  session:
    store-type: redis
    redis:
      namespace: myapp:session

server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        secure: true
        same-site: lax
```

Meaning:

- `spring.data.redis.*`: connection to Redis.
- `spring.session.store-type: redis`: specifies the Redis session store in Spring Boot versions that support this property.
- `spring.session.redis.namespace`: isolates this application's session keyspace from other applications.
- `server.servlet.session.timeout`: maximum inactive interval of the session in standard Servlet configuration.
- `http-only: true`: reduces the risk of JavaScript directly reading the cookie.
- `secure: true`: only sends the cookie over HTTPS; when running over plain HTTP localhost, an appropriate test environment is needed.
- `same-site: lax`: a layer of CSRF mitigation in many browser flows, though it does not replace CSRF protection.

**Environment distinction:** For example, `secure: true` is intended for requests over HTTPS. When developing on HTTP localhost, browsers may not send the cookie as expected depending on browser conditions and policies. In production, use HTTPS from the browser to the TLS termination point and accurately control trusted reverse proxy/forwarded headers.

### Checking Version/Properties

Spring Boot properties and how Spring Session auto-configures itself can differ across versions. When upgrading, check the **configuration metadata and reference guide of the exact version being run**; do not copy a property from an old example and assume it still has effect.

Do not verify success solely by checking that “the application starts up.” You must test logging in across two instances, switching routing, and verifying that the session remains valid.

## 4. Sample Application: Logging In and Preserving State via Redis

A small sample application might consist of:

```text
src/main/java/com/example/sessiondemo/
    SessionDemoApplication.java
    SecurityConfiguration.java
    UserPreferencesController.java

src/main/resources/
    application.yml
```

Assume the application already has a suitable user identification mechanism, such as a separately configured `UserDetailsService` or authentication provider. The examples below do not hardcode production usernames or passwords.

### 4.1. Session-Based Spring Security Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .deleteCookies("SESSION"));

        return http.build();
    }
}
```

This example is based on Spring Security's session-based model. You need to configure a user source or identity provider for login to actually work, as well as properly manage CSRF tokens and the login page/form.

Spring Security typically manages session fixation protection and saves/restores the `SecurityContext` according to the active security configuration. Do not write a custom login controller simply by setting:

```java
session.setAttribute("authenticated", true);
```

and treating that as secure authentication. A manually set session attribute does not replace Spring Security's identity verification and access control flow.

### 4.2. Controller Writing and Reading a Session Attribute

```java
import jakarta.servlet.http.HttpSession;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/me")
public class UserPreferencesController {

    @GetMapping("/session")
    public Map<String, Object> currentSession(
            HttpSession session,
            Authentication authentication) {

        String locale = (String) session.getAttribute("locale");

        return Map.of(
                "authenticatedUser", authentication.getName(),
                "preferredLocale", locale == null ? "vi-VN" : locale,
                "isNewSession", session.isNew());
    }

    @PostMapping("/locale/vi")
    public Map<String, String> setVietnameseLocale(HttpSession session) {
        session.setAttribute("locale", "vi-VN");
        return Map.of("locale", "vi-VN");
    }

    @PostMapping("/locale/en")
    public Map<String, String> setEnglishLocale(HttpSession session) {
        session.setAttribute("locale", "en-US");
        return Map.of("locale", "en-US");
    }
}
```

Requests carrying a valid session ID look up the session via Redis. The `locale` attribute is an example of auxiliary data that can be stored in the session; `Authentication` comes from Spring Security rather than a value trusted blindly by the controller from an unauthenticated request header.

With Spring Security and CSRF enabled by default as appropriate for session-based browser logins, `POST` requests require a valid CSRF token. Do not disable CSRF just so a `curl -X POST` example runs; in tests, send the token issued by the application along with the cookie for that session.

### 4.3. Request Flow Across Multiple Replicas

```text
Request 1:
Browser -- POST /login --> App A
                         |
                         +-- Spring Security authenticates
                         +-- Spring Session saves session to Redis
                         +-- Response Set-Cookie: SESSION=<opaque-id>

Request 2:
Browser -- GET /me/session --> App B
           Cookie SESSION=<same-id>
                         |
                         +-- Spring Session reads data in Redis
                         +-- Spring Security restores Authentication
                         +-- Controller returns user info

Request 3:
Browser -- POST /me/locale/en --> App C
                         |
                         +-- Updates session attribute
                         +-- Spring Session saves changes to Redis
```

If the load balancer routes requests from A to B or C, the session can continue because the data is shared through Redis. The prerequisite is that all instances agree on **namespace, serialization, schema version, security configuration, lifetime, and cookie settings**.

Using the same cookie name while pointing each replica to a different Redis instance does not create a shared session store.

## 5. What Does the Cookie Contain and Why Shouldn't Cookies Be Treated as the Session Store?

With Spring Session's server-side session model, the browser typically receives a cookie like:

```http
Set-Cookie: SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

A session ID is a **bearer secret**: anyone holding a valid session ID may be able to use the session subject to the system's protective controls. Therefore:

- Always use HTTPS to avoid exposing the cookie in transit.
- Set `Secure` and `HttpOnly` appropriately.
- Set `SameSite` according to the login flow and required CSRF protection level.
- Choose the narrowest `Path` and `Domain` necessary.
- Do not place the session ID in URLs, logs, analytics events, or public response bodies.
- Do not log raw `Cookie` or `Set-Cookie` headers containing session secrets.
- Protect against session fixation and session hijacking using appropriate security mechanisms.

A standard cookie **only carries the ID**, not the entire `SecurityContext` or Java objects stored in Redis. This differs from models that store all authentication claims inside a self-contained token such as a JWT.

### 5.1. Cookie Domain and Sharing Across Subdomains

Suppose there are two applications:

```text
app1.example.com
app2.example.com
```

If you set the cookie domain too broadly, such as `.example.com`, the cookie may be sent to both applications. That alone does not make the two applications share a valid session: they still need the same session namespace/repository and security contract, and sharing cookies expands the blast radius if one subdomain is compromised.

In many systems, cookies should be kept **host-only** rather than domain-wide unless there is an SSO/session-sharing requirement that has been separately designed and security-reviewed.

### 5.2. Do Not Roll Your Own Session ID

Do not construct a session ID from a user ID, timestamp, or incrementing number:

```text
sessionId = "user-1001-2026-11-13"     // predictable, unsuitable
```

Use the ID generation mechanism provided by Spring Session/Servlet integration, which is designed for session identifiers. Do not use an email address, phone number, or user ID as the session ID.

## 6. Lifecycle of a Login Session

A session can pass through these states:

```text
No session yet
       |
       v
Create session when needed
       |
       v
Authentication succeeds (login)
       |
       +-- Spring Security applies session fixation protection
       |
       v
Valid session, holding SecurityContext state
       |
       +-- Multiple requests read/update session
       |
       +-- lastAccessedTime/TTL managed
       |
       +-- ID may change/rotate per security policy
       |
       v
One of the termination events:
       |
       +-- User logout
       +-- Session timeout
       +-- Administrator revoke
       +-- Repository/session deleted
       +-- Redis data/session lost
       |
       v
Session is no longer valid
       |
       v
Next request must re-authenticate
```

You must distinguish between **session exists**, **session has not expired**, and **user is currently still allowed to log in**. A user may have been locked in the database while the session in Redis is still alive. If business requirements demand that account locking take effect immediately, the system needs an appropriate revoke/revalidation mechanism rather than relying solely on TTL.

## 7. Session Timeout and Redis TTL

`server.servlet.session.timeout: 30m` usually represents the **maximum inactive interval** of an HTTP Servlet session, not necessarily an absolute 30-minute lifetime from the moment of login.

For example:

```text
10:00 user login
10:10 user request  -> session still active
10:20 user request  -> session still active
10:49 no request for long enough -> session may have expired
```

If the application needs both an **idle timeout** and an **absolute maximum lifetime** (for example, forcing re-login after 8 hours regardless of activity), you must design an additional absolute session-age policy. Relying on max inactive interval alone cannot satisfy that requirement.

### 7.1. Redis TTL Can Differ from Simple Time Subtraction

Spring Session uses keys, metadata, and storage/expiration strategies to implement sessions. In specific versions/configurations, the physical TTL of certain internal keys may be set longer than the max inactive interval to support expiration events or cleanup.

Therefore, do not assume:

```text
Redis key TTL = 1800 seconds
=> User definitely has exactly 1800 seconds of access left.
```

Whether a session is still valid must be evaluated through `SessionRepository` and the session's timing attributes, not by looking at a single physical Redis key. Key prefixes, indexes, and internal data may differ by repository implementation/version.

### 7.2. Do Not Modify TTL/Session Keys Directly with StringRedisTemplate

Avoid writing a side service that does:

```java
redis.expire("spring:session:sessions:" + sessionId, Duration.ofHours(4));
```

and believing you have properly changed the session policy. Doing so bypasses Spring Session's internal/index data and expiry rules. If you need to change the timeout, use the supported session/repository APIs and configuration, for example:

```java
session.setMaxInactiveInterval(30 * 60);
```

and let Spring Session persist it according to the implementation's mechanism. If you need to change the default timeout for all sessions, configure it at the application layer instead of “tweaking Redis keys by hand.”

## 8. Session Save Modes: Flush Mode and Save Mode

Spring Session Data Redis provides mechanisms controlling **when changes are written to Redis** and **which attributes are considered dirty/needing persistence**.

Concepts to distinguish:

- **Flush mode**: when changes are written to Redis, e.g., `ON_SAVE` or `IMMEDIATE` depending on supported configurations.
- **Save mode**: the scope of attributes written—such as only attributes that were actually updated versus a broader set of attributes depending on the mode/implementation.

Specific options depend on the Spring Session version, but the architectural trade-offs remain the same:

| Aspect | Deferred Save Until End of Request | Early Save on Change |
|---|---|---|
| Number of Redis writes | Usually fewer | Potentially more |
| When other requests see the new value | Likely after the current request finishes | Potentially sooner |
| Request fails mid-way | Some changes may not have flushed yet | Changes may already have been written |
| Concurrent updates | Risk of lost updates depending on save mode | Still races if multiple requests modify the same attribute |

Do not assume `IMMEDIATE` turns every `setAttribute` into a safe cross-request transaction. It only affects write timing; it does not introduce a distributed lock across the whole session.

### 8.1. Mutable Objects Are a Trap

Suppose you store a mutable object:

```java
CartState cart = (CartState) session.getAttribute("cart");
cart.addItem("sku-1");  // only mutates the object in memory
```

Depending on the save mode, the framework may not detect that the attribute was modified if `setAttribute` is not called again, and the change might not be persisted as expected.

More explicitly:

```java
CartState current = (CartState) session.getAttribute("cart");
CartState next = current.withAddedItem("sku-1");
session.setAttribute("cart", next);
```

Even so, two concurrent requests can still read the same stale copy and overwrite each other. For a shopping cart with high consistency requirements, storing the cart in a domain store with versioning/atomic operations usually makes more sense than treating the session as a transactional database.

## 9. Spring Security Integration: SecurityContext and Session ID Rotation

Spring Security can store the `SecurityContext` via a security context repository backed by the HTTP session in session-based authentication. Spring Session provides the underlying `HttpSession` layer so appropriate data can be persisted and restored via Redis.

Important points:

1. **Spring Security authenticates** the user and creates `Authentication`.
2. The security framework manages saving/restoring `SecurityContext` according to the active filter chain.
3. Spring Session persists the session data held by `HttpSession` to Redis.
4. The browser receives the session ID to reference the session on subsequent requests.

Do not place all user permissions into a custom attribute object and skip Spring Security authorization checks. If permissions can change while a session is alive, you need a policy for refreshing or invalidating authentication state.

### 9.1. Session Fixation Protection

A session fixation attack tries to trick a victim into logging in using a session ID already known to the attacker. Spring Security supports strategies to change the session ID upon successful authentication when properly configured.

Do not force keeping the same session ID before and after login just to “avoid losing the cart” if doing so breaks fixation protection. If the application needs to carry pre-login session data into the authenticated session, choose an appropriate migration/copy strategy and never blindly copy untrusted attributes.

### 9.2. Logout and Session Invalidation

Spring Security's logout configuration can invalidate the current session and delete cookies as requested. This is different from merely returning:

```java
return ResponseEntity.ok("Logged out");
```

If you only return HTTP success without clearing `SecurityContext`, invalidating the session, or applying the corresponding policy, the browser can keep using the old session.

In the form-login example with CSRF enabled, logout is typically a `POST` request with a valid CSRF token; do not expose logout via `GET` by default as a side-effecting endpoint.

### 9.3. Deleting the Cookie Does Not Guarantee the Redis Session Was Revoked

`Set-Cookie` with a past expiration stops the browser from sending that ID anymore. However, if the server-side session still exists, someone who already captured the valid ID beforehand may still be able to use it in certain scenarios.

**Secure logout must handle the server-side session per policy**, not just clear the client-side cookie.

Conversely, deleting the session in Redis without updating the cookie means the browser still sends the invalidated ID; the server should treat that request as having no authenticated session and require re-login.

## 10. Managing Multiple Login Sessions for One User

A user may simultaneously be logged in on a laptop, phone, and another browser. Business requirements may include:

- Displaying a list of devices/sessions.
- Revoking a specific session.
- Logging out all sessions.
- Limiting the number of concurrent login sessions.
- Deleting all sessions when a password changes or an account is locked.

These requirements **are not automatically met** just because sessions are stored in Redis. To look up sessions by principal, you need an appropriate indexed repository/strategy.

### 10.1. RedisSessionRepository vs. RedisIndexedSessionRepository

A basic repository focuses on operations by **session ID**. An indexed repository supports lookups by index, such as principal, with its own characteristics and index-maintenance overhead.

In Spring Session Data Redis, configurations such as `@EnableRedisIndexedHttpSession` or selecting the corresponding repository type can be used to enable indexing depending on the version. However, do not enable this annotation arbitrarily alongside Spring Boot's auto-configured session repository without checking the resulting beans and behavior.

Indexing has trade-offs:

- Writing/deleting a session can create additional metadata/index operations.
- Logout/revoke by principal depends on reading the index accurately.
- Expiration event handling and index cleanup have limits based on topology/notifications.
- Redis Cluster setups have specific limitations related to per-node event/index delivery.
- Index consistency after failures must be measured and reconciled when security requirements are strict.

### 10.2. Example: Revoking Known Sessions by Principal

If the project has configured a suitable `FindByIndexNameSessionRepository`, you can retrieve the principal's sessions and delete those other than the current one:

```java
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public class AccountSessionRevocationService {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public AccountSessionRevocationService(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public void revokeOtherSessions(
            String authenticatedPrincipalName,
            String currentSessionId) {

        sessions.findByPrincipalName(authenticatedPrincipalName)
                .values()
                .stream()
                .filter(session -> !session.getId().equals(currentSessionId))
                .forEach(session ->
                        sessions.deleteById(session.getId()));
    }
}
```

**Never accept `authenticatedPrincipalName` directly from a user-supplied request body and allow arbitrary session deletion.** The principal must originate from the verified security context with proper authorization. Likewise, APIs for administering other users' sessions require dedicated authorization checks.

This snippet demonstrates repository usage; it does not guarantee that the entire index always reflects every state instantaneously across every Cluster/failover scenario. If urgent revocation is required, design an additional check on incoming requests, such as a session version/revocation epoch.

### 10.3. Limiting Concurrent Sessions

Spring Security has concurrent session control mechanisms in some configurations; however, when using Spring Session, you must verify how `SessionRegistry`/repository components integrate with the shared session store.

Do not assume that enabling `maximumSessions(1)` on a local instance coordinates sessions across the entire cluster if the registry resides in each instance's local memory.

In large systems, races also occur: two simultaneous logins on two nodes can both check and then create sessions. If “only one session” is a mandatory security invariant, you need coordination at a chosen authoritative store rather than comparing session counts across two non-atomic commands.

## 11. Expiration and Logout Events Are Not a Business Event Log

Spring Session can publish session lifecycle events such as creation, deletion, or expiration, depending on the repository and notification mechanism used. This is useful for cleaning up auxiliary data or observability.

However, understand the limitations:

- Redis key expiration may not be notified **at the exact millisecond TTL hits 0**; key cleanup depends on Redis's expiration mechanism.
- Redis keyspace/keyevent notifications are based on Pub/Sub, so **there is no durable queue** for offline listeners.
- In Redis Cluster, a node's events are not automatically broadcast and received as a cluster-wide event log.
- A failure or deployment can cause listeners to miss some expiration events.
- You should not rely on a session-destroyed event to fulfill a mandatory exactly-once business obligation.

Bad example:

```text
User session expires
        |
        v
SessionDestroyedEvent
        |
        v
Must deduct funds or close transaction ledger
```

If an event is missed, business logic may fail to complete. Mandatory side effects should rely on a durable transactional source, a reconciling scheduler, or a queue with ACK/retry—never treat a session expiration event as the sole trigger.

### 11.1. Keyspace Notifications May Be Restricted

Some indexed session repository modes leverage Redis's ability to emit key deletion/expiration events or maintain structures supporting expiration. In managed Redis environments, permission to modify `notify-keyspace-events` may be restricted; in Cluster, event delivery also depends on individual nodes and Spring Session's mechanism.

You must evaluate whether features depending on expiration events work **properly on your production topology**. Do not modify production Redis configuration on a whim just to make a listener “appear to work” while ignoring administrative boundaries and operational impact.

## 12. Redis Cluster and Sentinel for Session Storage

One reason to choose Redis as a session store is so multiple instances can share it. When Redis is deployed with Sentinel or Cluster, however, you must understand the distributed behavior.

### 12.1. Sentinel: Failover Does Not Mean Zero Session Loss

```text
Spring instances
       |
       v
Lettuce/Sentinel discovery
       |
       v
Current Redis primary
       |
       v
Replica(s)
```

Redis replication can be asynchronous. A session written to the primary just before a failover might not yet exist on the replica promoted to the new primary, depending on replication/persistence state at the time of failure.

Consequences:

- Users may have to log in again after a failover.
- A recently revoked session could reappear in recovered data unexpectedly if no additional safeguards exist.
- An in-flight request saving a session can time out with an **unknown** outcome.
- Lettuce reconnect does not guarantee session writes were executed exactly once across all scenarios.

For sensitive authentication data, evaluate the possibility of **lost/reappearing sessions and revocation state**. You can choose Redis for sessions, but you must establish clear availability and security expectations during failover.

### 12.2. Redis Cluster: Keys Are Not Necessarily in the Same Slot

Spring Session may store session, metadata, index, and expiration-related keys according to its implementation rules. Do not assume every key for a session or all indexes reside in the same hash slot just because they share a prefix.

```text
myapp:session:sessions:<id-1> -> slot A
myapp:session:sessions:<id-2> -> slot B
myapp:session:index:...      -> may be another slot
```

Key names are illustrative only; implementations may organize them differently by version. If a repository uses multi-key operations requiring atomicity or Lua, Redis Cluster slot constraints must be verified.

Especially for **indexed repositories** and session lifecycle notifications, check the documentation and behavior of your specific Spring Session version against Redis Cluster. Do not infer from a single successful `GET sessionId` that principal lookup, index cleanup, and expiration events also work across all nodes.

### 12.3. Reading from Replicas Can Return Stale Sessions

If Lettuce is configured to read from replicas to offload traffic, replication lag can cause a request to observe stale session state:

```text
App A writes logout/invalidate on primary
                        |
                 Async replication
                        |
App B reads from an out-of-date replica
                        |
                 May observe stale state
```

For authentication sessions, seeing a stale non-revoked state can be a security risk. Therefore, **session read paths should have an explicit consistency policy**; do not enable replica reads for sessions solely to boost throughput without proving semantics around logout, account locking, and permission changes.

For sensitive access decisions, prioritize authoritative state checks and reliable revocation mechanisms.

## 13. Redis Session Storage Is Resource-Bounded

Contrary to the mindset “Redis is fast, so put all objects in the session,” every session consumes Redis memory, and every request may generate reads, writes, and TTL extensions.

A session holding large objects can cause:

- Redis memory usage to surge with the number of online users.
- Slow serialization/deserialization.
- Higher network bandwidth between app and Redis.
- More bytes replicated to replicas.
- Increased Java GC pauses if sessions hold large object graphs.
- Difficulty running multiple application versions reading the same sessions.

Unsuitable example:

```java
session.setAttribute("allOrders", orderRepository.findAllByUser(userId));
session.setAttribute("cartHistory", hugeObjectGraph);
session.setAttribute("fullUser", entityWithRelations);
```

Instead of storing thousands of records or lazy-loading JPA entities, you can store:

```java
session.setAttribute("currentWorkspaceId", workspaceId);
session.setAttribute("preferredLocale", "vi-VN");
```

Core business data should be read from the database or a dedicated cache by ID, with authorization checked per request.

### 13.1. Redis maxmemory-policy and Session Eviction

If Redis approaches its memory limit and `maxmemory-policy` allows key eviction, session data may be evicted before its inactivity timeout expires. The usual symptom is users being logged out unexpectedly or losing attributes.

Do not share a Redis instance configured for **aggressive cache eviction** with authentication sessions and expect sessions to survive their full TTL. You must evaluate:

- Memory budget for peak concurrent sessions.
- An appropriate eviction policy—generally never evicting active sessions arbitrarily.
- Alerts for high memory usage, rejected writes, or Redis overload.
- Fallback behavior when Redis is temporarily unavailable.
- Backup/persistence/replication aligned with availability and security requirements.

A system may deliberately accept losing sessions during a Redis outage (forcing re-login) rather than trying to keep sessions alive with untrusted stale data. That decision must be grounded in the threat model and SLOs.

## 14. Serialization and Application Upgrades

Sessions contain multiple Java attributes. Spring Session Data Redis needs a serializer to persist them to Redis. The actual default serializer depends on version and configuration; some common setups use **Java native serialization** if left uncustomized.

Risk during rolling deployments:

```text
App v1:
    session attribute class UserPreferencesV1

App v2:
    session attribute class UserPreferencesV2
    field structure changed

Both read the same Redis:
    deserialization may fail or misinterpret old data
```

Without schema management, users may lose their sessions after deployment or encounter access errors due to incompatible objects.

### 14.1. Helpful Rules

- Only store attributes genuinely needed for the session.
- Avoid putting JPA entities, large object graphs, sockets/connections, beans, or non-serializable data into the session.
- Design small, versionable DTOs, or store primitives/IDs.
- Do not swap serializers between two versions without a migration strategy.
- Verify compatibility with the `SecurityContext`/`Authentication` used by Spring Security.
- Never deserialize session data from an untrusted Redis source; assess Java deserialization risks and Redis access controls.
- When using a JSON serializer, define explicit type metadata, allowlists/type mappings, and secure structures—never enable broad polymorphic deserialization arbitrarily.

### 14.2. Custom Spring Session Serializer

In Spring Session Data Redis, a conventionally named serializer bean such as `springSessionDefaultRedisSerializer` can be used to customize serialization in supported configurations/versions.

Illustrative direction:

```java
// Configuration pseudocode:
// @Bean("springSessionDefaultRedisSerializer")
// RedisSerializer<?> sessionSerializer() {
//     return serializerConfiguredSafelyForSpringSecurity();
// }
```

Do not copy the pseudocode above as a complete configuration: the serializer must be compatible with every attribute, especially `SecurityContext` and authentication subtypes. If choosing JSON, you need Spring Security modules/mixins matching your library version, schema migration handling, and testing across login, logout, and rolling deployments.

**Changing the serializer while live sessions exist is a data migration**, not just swapping a bean. You may need a dual-read phase, a new namespace, or an intentional forced re-login with notice.

## 15. Sessions and Business Data: Integration Boundaries

A session may hold transient state such as locale, current tab, or flow ID, but should not become the source of truth for:

- Account balances or transaction history.
- Inventory counts or final order prices.
- Roles/access permissions requiring immediate enforcement.
- Invoices, audit records, or events that must not be lost.
- Distributed locks or long-running workflow state.
- Secret tokens that do not belong in the session.

The reason is that a session can:

1. Expire due to inactivity timeout.
2. Be revoked on logout.
3. Be evicted by Redis or lost during an outage.
4. Be overwritten by concurrent requests.
5. Not commit atomically alongside the database.
6. Be serialized per application version and become incompatible across deployments.

**Authentication state and business data have different lifetimes, guarantees, and owners.** Spring Session should hold the minimum data required for the session experience, while the database/identity store holds durable data with business invariants.

## 16. Concurrent Requests Can Cause Lost Session Updates

Two requests from the same browser can arrive simultaneously:

```text
Request A                           Request B
    |                                   |
Reads old session version          Reads old session version
    |                                   |
locale = "vi"                     theme = "dark"
    |                                   |
Writes session                     Writes session
    |                                   |
    +----------> Redis <---------------+
```

Depending on the repository, flush/save mode, and how attributes are stored, one update can overwrite state or cause subsequent requests to observe out-of-sync data. Especially when **the same mutable attribute** is modified by two requests, do not expect Spring Session to automatically provide optimistic locking for business logic.

For critical features like adding/removing cart items, use a dedicated data structure and design atomic updates, versioning, or transactions at the source of truth. Do not rely on sessions being shared in Redis as proof that session mutations are race-free.

### 16.1. Do Not Hold a Long-Running Lock Over the Entire HttpSession

Locking the entire session from the start to the end of a request can hurt concurrency and cause deadlocks or long waits if a request calls an external API. When coordination is necessary, lock or constrain only the operations requiring consistency, bound the duration, and design explicit error handling.

## 17. Transaction Boundaries Between Database and Redis Session

A login or profile-update request might execute:

```text
1. Database transaction: update profile.
2. Session: write display-name attribute.
3. HTTP response: return success.
```

If the database rolls back after the session is saved, the session may display data inconsistent with the source of truth. If the database commits but writing to Redis fails, the session may retain stale data or force the user to log in again.

JPA/JDBC/R2DBC `@Transactional` **does not create an atomic transaction spanning both the database and Spring Session Redis**. The Redis session and the database are separate resources.

Design approaches:

- Treat the database as the source of truth.
- Never let a session attribute authorize a financial change or critical permission without checking the source of truth.
- When a profile changes, invalidate/refresh cached display info in the session per policy.
- For permission changes, design revalidation or session revocation matched to the urgency level.
- If reliable post-commit events are required, use an outbox or durable event mechanism; never use `HttpSession.setAttribute` as an event log.
- For multi-step transactional workflows, persist workflow state in an appropriate database rather than keeping it only in the session.

A session update might succeed and then the request fails; client retries can also trigger other side effects. Choose idempotency keys and transaction boundaries for business logic—do not treat the session repository as a transaction coordinator.

## 18. Integration Boundaries with JWT, OAuth2, and OpenID Connect

Spring Session typically fits **server-side session authentication**, where the server holds the `SecurityContext` and the browser carries a session cookie. JWT/OAuth2/OIDC play different roles:

| Concept | Role |
|---|---|
| Spring Session | Stores/manages server-side sessions via Redis or another store |
| Spring Security | Authentication, authorization, security filters, session management |
| Session cookie | Carries the session identifier of the server-side session |
| OAuth2 access token | Credential to access a resource server under system scopes/rules |
| Refresh token | Credential to obtain a new access token under authorization server rules |
| ID token (OIDC) | Represents user authentication assertions from an identity provider per OIDC |
| JWT | Self-contained signable token format; not synonymous with a Redis session |

### 18.1. A JWT Resource Server Does Not Automatically Use Spring Session

An API that only validates a bearer access token on each request can operate statelessly without an `HttpSession`. Enabling Spring Session Data Redis **does not automatically store all JWTs in Redis**, and deleting a Spring Session does not automatically revoke issued access tokens.

If your goal is to revoke JWTs or refresh tokens, you must use token revocation, introspection, short token lifetimes, token versioning, or an appropriate authoritative authorization server.

### 18.2. Browser OAuth2 Login Can Still Use Sessions

A web application performing OAuth2/OIDC login may create a session once the authentication callback completes; Spring Security stores the `SecurityContext` in the session. This is a normal combination: **OIDC handles login, while Spring Session stores the web application's login state**.

Even so, you still need to manage:

- OAuth2 flow `state`/`nonce` using appropriate security mechanisms.
- Callback URLs, cookie `SameSite`, and HTTPS.
- Session fixation protection.
- Application logout versus identity provider logout.
- Access/refresh token lifecycle if the application actually stores or uses those tokens.
- Authorization when a user's permissions are revoked at the IdP while the local session is still alive.

Local logout does not automatically guarantee global single logout across all clients or identity providers.

## 19. Boundary with WebFlux Reactive Sessions

In **Spring WebFlux**, Servlet `HttpSession` is not used. Applications typically use `WebSession` and `WebSessionManager`; Spring Session provides reactive Redis integration via the corresponding repository and configuration.

Comparison:

```text
Spring MVC (Servlet)                 Spring WebFlux (Reactive)
--------------------                 -------------------------
HttpSession                          WebSession
SessionRepositoryFilter              WebSessionManager/integration
RedisSessionRepository                Reactive Redis session repository
Spring Security servlet filters      Spring Security WebFilterChain
Servlet SecurityContext handling     Reactive SecurityContext handling
```

A WebFlux controller can accept `WebSession`:

```java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;

@RestController
public class ReactiveSessionController {

    @GetMapping("/session/locale")
    public Map<String, String> locale(WebSession session) {
        String locale = session.getAttribute("locale");
        return Map.of(
                "locale", locale == null ? "vi-VN" : locale);
    }
}
```

This example illustrates the WebFlux API style; the application needs appropriate reactive security and session store configuration. Do not put blocking `RedisTemplate` calls onto the event loop to manage WebFlux sessions. Use the reactive integration supported by Spring Session for your project's framework version.

### 19.1. Do Not Arbitrarily Mix Servlet and WebFlux Sessions Across Two Systems

Suppose a frontend calls both:

```text
mvc.example.com    -> Servlet HttpSession
api.example.com    -> WebFlux WebSession
```

Even with the same Redis instance and the same cookie name, do not assume both systems share the same session format, repository, `SecurityContext` serialization, or auth rules. Sharing a session across different frameworks is a compatibility/SSO problem that must be designed intentionally—it does not happen automatically just by sharing Redis.

Usually, it is easier to control by using an identity provider/SSO and letting each application manage its own session.

## 20. Redis Key Structure: Do Not Depend on Internal Implementations

When using Spring Session Data Redis, you may observe keys carrying the namespace prefix along with session/index/expiry data. In some configurations/versions, key names may resemble:

```text
myapp:session:sessions:<session-id>
myapp:session:expirations:...
myapp:session:index:...
```

These are only **illustrative examples of layouts you may encounter**, not a stable public API contract. Key details, Redis types (hash/string/set), TTLs, and indexing mechanisms vary by repository and version.

Do not build business logic by:

- Calling `GET` on internal keys and deserializing them manually outside Spring Session.
- Directly editing the `sessionAttr:SPRING_SECURITY_CONTEXT` field without going through Spring Security.
- Running `DEL` on all keys matching a pattern and assuming every index is properly revoked.
- Running `KEYS myapp:session:*` against a large production Redis instance.
- Manually setting TTLs on individual internal keys and expecting the session lifecycle to behave correctly.

Use `SessionRepository`, `HttpSession`, or supported administrative APIs. When inspecting Redis via CLI, keep operations read-only and target specific keys.

## 21. Observing Sessions in Production

If the session store is an authentication dependency, measure:

| Metric | Meaning |
|---|---|
| Login success/failure rate | Health of the auth flow and identity provider |
| Rate of requests with a valid session | Ability to maintain login state |
| Session create/delete/expire rate | Lifecycle velocity and signs of abnormal changes |
| Redis session read/write latency | Impact on every session-dependent request |
| Session lookup misses | Expired sessions, revocations, data loss, or namespace errors |
| Redis timeout/connection errors | Risk of failed request authentication |
| Reconnect/failover count | Detects unstable infrastructure |
| Serializer errors | Incompatible session attributes across versions |
| Memory usage and eviction rate | Sessions evicted before timeout due to memory pressure |
| Session size distribution | Detects oversized sessions |
| Index lookup/revocation failures | Correctness of “logout all devices” functionality |
| Logout-to-revocation latency | Delay between revocation and old requests being rejected |
| Replica lag | Risk of stale sessions when reading from replicas |

Redis statistics commands:

```bash
redis-cli INFO stats
redis-cli INFO memory
redis-cli INFO clients
redis-cli INFO commandstats
```

If you want to inspect the TTL of **one precisely identified key** in an appropriate environment:

```bash
redis-cli TTL 'myapp:session:sessions:<session-id>'
```

However, never log real session IDs or dump entire session attributes into observability systems. A session ID is sensitive data; use a separate correlation ID for tracing.

### 21.1. Health Checks and Policies When Redis Is Unavailable

If Redis loses connectivity, an application using Spring Session Data Redis cannot look up sessions to authenticate requests. Never automatically “let through” every request when session lookup fails: doing so turns an outage into an auth bypass.

Choose an explicit policy:

- For endpoints requiring authentication, typically **fail closed** when a valid session cannot be verified.
- For public endpoints, continue serving without session dependence if security policy permits.
- For services needing high availability, deploy HA Redis with tuned timeouts, weighing the impact of forcing re-logins.
- Never issue an in-memory “fallback” session ID and pretend it shares the same guarantees as the Redis shared store.

Session store failures must be detected and metered; do not lump all Redis timeouts into “session expired” and hide the incident.

## 22. Testing the Sample Application Across Multiple Instances

A realistic test suite must verify both **session sharing** and **integration limits**.

### 22.1. Test Login via Instance A, Read on B

1. Start App A and App B with the same Redis namespace and serializer.
2. Perform a valid login through App A.
3. Securely store the test client's cookie jar.
4. Send an authenticated request to App B with the same cookie.
5. Confirm Spring Security on B receives a valid authentication.
6. Modify a session attribute on B.
7. Read it back on A and observe consistent state according to flush/save mode.

Do not rely on load balancer sticky sessions in this test; force requests to actually hit different instances to verify the shared store.

### 22.2. Test Logout/Revoke

1. Log in and verify the cookie and session are valid.
2. Invoke logout with the proper HTTP method and CSRF token.
3. Resend a request to a different instance using the old cookie.
4. Confirm the request is not accepted as authenticated.
5. If “logout all devices” exists, test with multiple distinct session IDs and measure revocation timing.

Do not only verify that the browser deleted the cookie; confirm that the **server-side session** is no longer accepted.

### 22.3. Test TTL and Inactivity

1. Configure a short timeout in tests.
2. Log in and wait past the inactivity duration.
3. Send a new request with the old cookie.
4. Confirm the system requires re-authentication.
5. Send a request within the valid window and verify the session refreshes per policy.

Do not deduce outcomes solely from `TTL` on internal Redis keys; test actual HTTP behavior.

### 22.4. Test Rolling Deployment and Serializers

1. Log in using App v1.
2. Read the same session using App v2 while both versions are running.
3. Ensure `SecurityContext` and required attributes deserialize properly.
4. Test rolling back to App v1 if the deployment plan allows it.
5. Evaluate migration strategies or forced re-login when schemas are incompatible.

### 22.5. Test Failover and Redis Failures

1. Trigger a Redis primary failover in a test environment.
2. Observe both login requests and already-authenticated requests.
3. Check whether session state is lost or becomes stale.
4. Attempt revocation right around failover and verify the security boundary.
5. Verify timeouts and error responses do not turn into an auth bypass.

### 22.6. Test Concurrency

Send two requests that update the same session attribute concurrently. Observe the result under the chosen repository mode. If business logic requires atomic updates, move that data to a store with concurrency control rather than expecting the session store to solve it automatically.

## 23. Common Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Using only in-memory sessions with multiple replicas | Users lose login when routed to another node | Spring Session Redis/shared store |
| Treating Spring Session as an authentication provider | Bypasses authentication/authorization | Use Spring Security/IdP properly |
| Treating every HttpSession as logged in | Unauthorized access when session only holds transient data | Check SecurityContext/authorization |
| Storing entire object graphs in the session | High Redis memory, serializer errors | Store IDs/small DTOs |
| Sharing cookies across the whole domain unnecessarily | Expands cookie hijack scope | Minimal cookie scope |
| Putting session IDs in URLs/logs | Exposes session credentials | Secure cookies, never log secrets |
| Logout only deletes the cookie | Server session may remain valid | Revoke/invalidate server-side |
| Relying solely on TTL when an account is locked | Old sessions may retain permissions | Revalidate or revoke per policy |
| Using a Redis cache eviction policy for sessions | Sessions deleted before TTL | Proper memory budget and session policy |
| Modifying Spring Session keys manually with RedisTemplate | Corrupts index/expiry/security state | Use repository/HttpSession |
| Changing serializer without migration | Old sessions fail to deserialize | Versioning/compatibility plan |
| Relying strictly on Redis expiration events | Offline listeners miss events | Reconciliation/durable source for mandatory obligations |
| Treating Sentinel/Cluster as absolute persistence | Sessions may be lost/stale on failover | Assess durability and failover |
| Reading sessions from lagging replicas | Revocations may not be visible immediately | Consistency policy for auth |
| Storing cart/stock/financials in the session | Lacks proper transactions/consistency | Dedicated business store |
| Believing `@Transactional` spans both DB and Redis session | Both resources can still commit out of sync | Outbox/reconciliation/source of truth |
| Mixing Servlet HttpSession with WebFlux WebSession | Wrong abstraction and security filter | Pick integration matching the stack |
| Using sessions to revoke JWTs | JWTs remain valid independently | Token revocation/IdP policy |
| Using a local session registry for cluster-wide limits | Instances count sessions separately | Appropriate indexed repository/registry |
| Folding Redis outages into expired sessions | Hard to investigate and risks wrong handling | Classify errors, fail closed when needed |

## 24. Decision Tree for Designing Login Sessions

```text
Does the application have server-side login state?
                      |
                +-----+-----+
                |           |
               Yes          No
                |           |
                v           v
         Need HttpSession?  Bearer token/stateless?
                |           |
                v           v
         Multiple replicas? Choose dedicated token/IdP
                |           lifecycle
           +----+----+
           |         |
          Yes        No
           |         |
           v         v
     Use shared     Local session may suffice
     session store  when limitations are acceptable
           |
           v
    Spring Session Data Redis
           |
           v
     Spring MVC or WebFlux?
        +--+-----------+
        |              |
      MVC            WebFlux
        |              |
        v              v
    HttpSession      WebSession
        |              |
        +------+-------+
               |
               v
        Spring Security manages
        authentication/authorization
               |
               v
        Secure cookies and session IDs
               |
               v
        TTL, serializer, namespace,
        Cluster/Sentinel, memory policy
               |
               v
       Need logout on all devices?
               |
          +----+----+
          |         |
         Yes        No
          |         |
          v         |
      Indexed repository/
      revocation policy
          |         |
          +----+----+
               |
               v
       Test multi-replica, logout,
       timeout, failover, and deploy
```

## 25. Conclusion

**Spring Session Data Redis** helps Spring applications manage `HttpSession` outside individual instance memory, enabling session sharing when scaling horizontally, lifetime configuration, and centralized logout/revocation through a repository. It is a useful **application pattern** when implementing session-cookie login with Spring Security.

However, integration boundaries must remain clear:

1. **Spring Security authenticates and authorizes; Spring Session stores sessions; Redis holds session data.** Do not use Redis sessions as an identity provider system.
2. **A session cookie is a bearer secret.** HTTPS, `HttpOnly`, `Secure`, `SameSite`, and proper cookie scoping are required; never log session IDs.
3. **Sessions have TTLs and consistency limits.** Do not treat sessions as a business database, and never assume concurrent requests updating attributes are always safe.
4. **Logout and permission revocation must take effect according to security policy.** Do not merely clear cookies, and do not rely blindly on expiration events or stale replicas.
5. **Redis HA/Cluster is not absolute transactions and durability.** Failover, eviction, indexing, and serializers must be tested on real infrastructure.
6. **Servlet and WebFlux use different abstractions.** Pick `HttpSession` or `WebSession` with its matching integration; never mix them arbitrarily.
7. **OAuth2/JWT have independent lifecycles.** Deleting a Spring Session does not automatically revoke self-contained access tokens.

A reliable implementation proves more than just “log in on App A, read on App B.” It must also prove that **logout takes effect, sessions are not leaked, timeouts follow policy, data survives appropriate rolling deployments, and Redis failures do not break authentication boundaries**.
