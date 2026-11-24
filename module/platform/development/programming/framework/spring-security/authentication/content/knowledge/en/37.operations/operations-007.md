# Session Stores, One-Time Token Stores, and Consistency Requirements Across Multiple Nodes

## 1. Why Can a Login App That Works on One Machine Fail on Two?

A Spring Security website with `formLogin()` may work flawlessly on a single instance: the user submits a password, the server creates an `HttpSession`, stores the `SecurityContext`, and the browser receives a session cookie to access protected pages. However, when deployed across **multiple nodes** behind a load balancer, the next request may land on **a different node**. If both nodes keep sessions only in local memory, the second node does not know the user logged in.

Similarly, when a system uses a **one-time token (OTT)** to send an email magic link or a single-use re-authentication token, node A might issue the token and save it in a local `ConcurrentHashMap`; when the user clicks the link and hits node B, B cannot find the token. Even worse, if token data is replicated without **atomic consumption**, two concurrent requests hitting two nodes may both believe the token is unused, causing **replay**.

This lesson belongs to the **Operations** section of **Spring Security - authentication**, focusing on selecting and operating **session stores**, **one-time token stores**, and **consistency requirements** across multiple nodes/pods, failovers, autoscaling, Redis/databases, and gateways. Integration examples use Java 17+ and Spring Boot 3.x/Spring Security 6.x; OTT specifics use Spring Security **6.4+**, as earlier 6.x releases did not include `oneTimeTokenLogin()`.

After this lesson, you should be able to:

1. Distinguish cookies/session IDs, `SecurityContext`, and state storage.
2. Explain why sticky sessions alone do not solve restarts, failovers, or token replay.
3. Configure Spring Session Redis so two instances share the same login session.
4. Use a shared store for OTT; understand how `generate(...)` and `consume(...)` must pair with TTL, uniqueness, and atomicity.
5. Design consistency requirements for login, logout, session ID rotation, MFA step-up, token consumption, and revocation.
6. Test two nodes, concurrent races, expiration, store outages, restarts, rollbacks, and rolling updates.

**First two rules:** sessions must be **read/written via a shared store to survive across nodes**, and a "one-time" token must have **a single atomic consumption decision point**; storing in the same place without atomicity is not enough.

## 2. Sessions Are Not Cookies; OTTs Are Not Access Tokens

| Artifact | Role | Where State Lives | Critical Requirements |
| --- | --- | --- | --- |
| Session cookie (often `SESSION` in Spring Session) | Carries session ID for server lookup | Browser holds the ID, not the full `Authentication` | HTTPS, Secure/HttpOnly/SameSite, cookie scope, rotation |
| `HttpSession` | Server-side session with attributes | Local servlet container or shared session store | Load/save from any node; TTL, invalidation |
| `SecurityContext` | Holds authenticated `Authentication` | In HttpSession/repository or request per config | Accurate principal/authorities; save and restore |
| OTT / magic-link token | Proof exchangeable for authentication **once** | Must use a shared store with consume/expiry policy | Single-use, short-lived, high entropy, anti-replay |
| TOTP/HOTP code | Code derived from authenticator secret/counter | Secret/counter or replay state with dedicated policy | Attempt limits, clock skew checks, anti-replay |
| OAuth2 access JWT | Bearer proof issued by AS | Typically held by client; stateless RS checks per request | Signature, issuer, audience, exp, scopes, revocation model |
| Opaque access/refresh token | Reference value or refresh credential | AS or token store | Introspection/rotation/revocation, replay defense |
| CSRF token | Protects state-changing browser requests | Session/cookie/repository depending on design | Bound to session lifecycle; not authentication |

**Do not lump all artifacts into one Redis key or one TTL.** A session may stay alive for 30 minutes of inactivity; a magic-link OTT may last only 5 minutes; refresh tokens require separate lifecycles and atomic rotation; stateless JWTs should not automatically write to `HttpSession`.

## 3. What Happens to Sessions When a Load Balancer Distributes Across Two Nodes?

Architecture without shared sessions:

```text
                       Load Balancer
                     /               \
                Node A              Node B
             HttpSession A       HttpSession B
               [Alice]              [empty]
                  │                    │
POST /login ──────┘                    │
GET /account ─────────────────────────┘ → anonymous / 302 login
```

Two separate JVMs do not share heap objects. `JSESSIONID` or `SESSION` is only **a lookup key** for a session—it does not magically turn an object in Node A's RAM into data on Node B.

Architecture with shared sessions:

```text
                    Load Balancer
                      /       \
                  Node A      Node B
                      \       /
                  Spring Session
                        |
                 Redis / DB cluster
                        |
              session-id → attributes
                        |
                 SecurityContext Alice
```

A login request on A creates/writes the session to the backend. The next request on B reads the same session ID and restores `Authentication`. **Verify after actual commit/save**; a shared store cannot rescue custom login code that forgets `SecurityContextRepository.saveContext(...)`.

### 3.1. What Are Sticky Sessions and What Are Their Limits?

Session affinity (sticky sessions) tries to route the same browser to one node. It reduces shared-store reads in some designs, yet **provides no consistency guarantee**:

- The "stuck" node can crash, drain, or scale down.
- Browsers switch networks, or proxies/load balancers change routing.
- Rolling deployments shift requests to nodes with different session state.
- A one-time token can be issued on node A and redeemed on node B across different clients/requests; stickiness is not a mutex.
- An administrator logging out a session on one node does not clear sessions on other nodes if each node holds local copies.

Stickiness can serve as a topology optimization alongside a recovery strategy, **never as a replacement** for shared sessions when logins must survive failover.

## 4. Consistency Must Be Defined per Business Operation

"Consistency" has no single meaning across all data. Define **security invariants**:

| Operation | Invariant to Guarantee |
| --- | --- |
| Successful login | Once the client receives a valid session, subsequent requests read the right authenticated principal/authorities per contract |
| Failed login | No session is saved with an authenticated `Authentication` from a failed request |
| Session fixation protection | A pre-login session ID never becomes the entry point into the new authenticated account |
| Logout / invalidation | A destroyed session never keeps granting access simply because another node kept a stale cache |
| Session idle timeout | Once expired, access is denied; never use physical garbage-collection timing as validity time |
| OTT consume | **At most one** request wins the right to consume a valid token |
| OTT expiration | Expired tokens cannot be used even if the record has not been cleaned up yet |
| OTT principal binding | A token issued for subject/account X creates login/step-up only for subject X |
| OTP/MFA step-up | Evidence binds to the right principal, session/transaction, and timestamp; never elevates another user |
| Refresh-token rotation | At most one valid outcome for an old refresh token per policy; replay is detected |
| Password/account revoked | Old sessions/tokens are handled per revocation policy and defined risk window |

Decision dimensions:

- **Availability:** can the system still serve requests when the store fails?
- **Safety:** could it ever accept a used token, invalidated session, or unauthenticated user?
- **Latency:** how many store round trips and what store p99 sit on the authentication path?
- **Durability:** if Redis/DB loses power or fails over, does data already acknowledged as "success" survive?
- **Ordering/linearizability:** if two concurrent requests hit two nodes, is there a strict commit order ensuring only one token is consumed?

In security, **never trade safety for availability by "letting requests pass if Redis does not reply"**. Unverified sessions and one-time tokens generally require failing closed; any degraded mode must be risk-analyzed, bounded, and monitored.

## 5. How Does Spring Security Save and Restore Authentication?

Typical Servlet flow:

```text
POST /login
  UsernamePasswordAuthenticationFilter
    └─ AuthenticationManager / Provider checks credentials
    └─ session fixation strategy
    └─ SecurityContext holds authenticated Authentication
    └─ SecurityContextRepository.saveContext(...)

GET /profile + session cookie
  Spring Session filter replaces HttpSession with Redis-backed implementation
    └─ SecurityContextHolderFilter
       └─ SecurityContextRepository loads SecurityContext
    └─ AuthorizationFilter checks authenticated + authorities
    └─ Controller / service
```

Spring Security 6 uses **explicit saving** in custom flows: calling `SecurityContextHolder.setContext(...)` on one thread **is not enough** for the next request to see the login. Standard login filters normally save the context for you; custom login handlers must coordinate with the repository and session strategy.

### 5.1. Two Distinct Layers

- `SecurityContextRepository` loads/saves `SecurityContext` into `HttpSession` or another backend.
- **Spring Session** replaces the servlet container's `HttpSession` with a Redis/DB-backed object via `springSessionRepositoryFilter`.

You can have Spring Session Redis yet still lose logins if a handler fails to save context. Or you can save `SecurityContext` properly while using only local sessions, leaving node B unable to read it. **Both layers must be right.**

### 5.2. Do Not Open Sessions for Pure Bearer APIs as a "Fix"

An `oauth2ResourceServer().jwt()` chain using `SessionCreationPolicy.STATELESS` builds a `JwtAuthenticationToken` from the token on **every request**, needing no server session sync. Do not accidentally convert stateless APIs to stateful just because a Redis cluster exists. When immediate JWT revocation or cross-session step-up is needed, treat that as a dedicated token/revocation problem with its own lookup cost.

## 6. Configuring Spring Session Redis on Spring Boot 3.x

The example below targets **Java 17 + Spring Boot 3.5.x + Spring Security 6.5.x** (paired with the Spring Session version managed by the Spring Boot BOM). If using Boot 3.0–3.3, check the version matrix and `oneTimeTokenLogin()` availability before copying the OTT section; the OTT framework arrived in Spring Security **6.4**.

### 6.1. Gradle Dependencies

In `build.gradle` of a Spring Boot 3.x project with Spring Boot plugin and dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.session:spring-session-data-redis'

    // Shared store for OneTimeTokenService over JDBC.
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Use BOM-compatible versions; **do not** arbitrarily pin `spring-session-data-redis` out of sync with Boot/Security. For Web MVC/Servlet, Spring Session Redis auto-configures the filter/session repository when Boot detects the dependency and Redis connection. Avoid sprinkling `@EnableRedisHttpSession` across classes when Boot already auto-configures it.

For production, configure Redis AUTH/TLS, network ACLs, connection pools/timeouts, Sentinel/Cluster per topology, DB permissions, and observability. Dependencies alone do not deploy Redis/PostgreSQL servers.

### 6.2. application.yml

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax

spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      # Password, TLS, sentinel/cluster configured via environment secrets/config.

  session:
    store-type: redis
    redis:
      namespace: "training:auth-session:v1"
      repository-type: default
      flush-mode: on_save

  datasource:
    url: ${JDBC_URL}
    username: ${JDBC_USER}
    password: ${JDBC_PASSWORD}

  jdbc:
    template:
      query-timeout: 3s
```

**Configuration notes:** `server.servlet.session.timeout=30m` is the **session idle timeout**, not magic-link token lifetime. `spring.session.redis.namespace` separates keys across apps/environments so sessions are never shared accidentally. `repository-type: default` uses `RedisSessionRepository`; `indexed` adds user-based lookup and session events alongside extra index/cleanup overhead. `flush-mode: on_save` writes on repository save; `immediate` reduces delay for some mutations but increases writes and does not resolve all concurrent update races.

On HTTPS production, set cookie `Secure=true` and `SameSite`/domain/path policies matching your architecture. For local HTTP labs, enabling `Secure` may prevent browsers from sending cookies as expected; separate dev and prod profiles cleanly and never turn off `Secure` in production.

**Warning:** never commit `JDBC_PASSWORD`, Redis passwords, session IDs, or raw OTT tokens into repos or logs. Infrastructure store credentials must come from a secret manager and be rotated regularly.

### 6.3. RedisSessionRepository or RedisIndexedSessionRepository?

| Option | Useful When | Limitations / Warnings |
| --- | --- | --- |
| `RedisSessionRepository` (Boot's default in common Redis configs) | Need ID-based session lookup and sharing across nodes | Lacks index/event capabilities of indexed implementation |
| `RedisIndexedSessionRepository` | Need to list all sessions for a principal, enforce concurrent sessions, handle created/deleted/expired events | Extra index structures, cleanup, and keyspace-event requirements; Redis Cluster caveats |
| Spring Session JDBC | Already operate durable RDBMS, need DB-backed shared sessions | Different latency/throughput/locking and schema trade-offs vs. Redis |
| Local servlet session | Single node, lab, or explicit local-state architecture | No failover or cross-node access |

Spring Session docs note that `RedisIndexedSessionRepository` with Redis Cluster may subscribe to events from only one random node, leaving indexes uncleaned in some cases. **Never treat "indexed enabled" as proof that all logouts/revocations update instantly in every topology.** If business logic needs active revocation of all sessions, verify the exact mechanism, cluster setup, propagation, and tests.

### 6.4. Illustrative Form Login Code + /me Endpoint

**`SessionDemoApplication.java`** (package `com.example.multinode`):

```java
package com.example.multinode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDemoApplication.class, args);
    }
}
```

**`WebSecurityConfig.java`**:

```java
package com.example.multinode;

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

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("lab-user")
                        .password(encoder.encode("LAB-only-change-me"))
                        .roles("READER")
                        .build());
    }
}
```

**`SessionIdentityController.java`**:

```java
package com.example.multinode;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionIdentityController {

    @GetMapping("/")
    public String home() {
        return "public";
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication auth) {
        return Map.of(
                "username", auth.getName(),
                "authenticated", auth.isAuthenticated());
    }
}
```

These files form a demo web app once Redis and a matching datasource are configured (the OTT DB section below can be configured separately if running sessions only). The static password is **strictly for lab use**, never for production or public deployments. `/me` returns only name and status rather than dumping `SecurityContext` or session IDs.

With Spring Session Redis configured properly, running the same app on **two ports/instances** sharing `spring.session.redis.namespace` and the Redis backend lets a session issued on node A be loaded on node B. This is **an outcome to verify via integration tests**, not assume merely because the app started cleanly.

## 7. Two-Node Testing: Post-Login Requests Must Hit the Other Node

A single-JVM `MockMvc` test verifies form login and `SecurityContextRepository`, yet **does not prove a shared store works**. Multi-node verification requires:

1. Nodes A and B running identical or compatible versions, sharing Redis namespace/credentials, cookie contract, and user store.
2. Browser/client submits form login to **A** and saves the post-login session cookie.
3. Without resending the password, send `GET /me` to **B** with that session cookie.
4. Confirm B returns **the right principal**, without redirecting to login or seeing another user.
5. Alternate `GET` requests between A and B and compare authorities/subject.
6. Kill or drain A; B must still read the session while the backend is up and the session is unexpired.
7. Log out via B, then hit A with the **old cookie**: must no longer be authenticated.
8. Verify behavior when idle timeout expires, when Redis restarts/fails over, when keys are evicted, and during rolling deploys if session classes change.

**Do not hard-code cookie names.** Spring Session commonly uses `SESSION`; standard Servlet sessions commonly use `JSESSIONID`. Inspect real responses because custom `CookieSerializer` configs can rename them.

### 7.1. Conceptual curl Scenario

Assuming `GET /login` creates the CSRF token and session cookie on node A's port:

```text
A: GET /login
   → obtain CSRF token and cookie
A: POST /login (username, password, CSRF, cookie)
   → save cookie after session fixation protection
B: GET /me (cookie only, do not send password)
   → 200, exact principal "lab-user"
A: GET /me (cookie only)
   → 200, exact principal "lab-user"
B: POST /logout (CSRF + cookie)
   → logout
A: GET /me (old cookie)
   → anonymous, no user info left
```

This is a **scenario to automate**, not executed curl commands. Because browser form login enables CSRF, do not just POST username/password and then disable CSRF upon hitting 403. When session ID rotation occurs at login, capture the newest cookie.

Over real HTTP, you can use `curl -c cookies.txt -b cookies.txt` as a cookie jar and extract the CSRF token from `GET /login`; the exact script depends on your login template and CSRF repository.

### 7.2. Testing Two Sessions for Different Users

Log Alice in on A and Bob on B using **two separate cookie jars**. Then send each jar to both A and B. All four requests must preserve the exact identity. A controller holding a principal in a singleton field or a cache keyed only by `"currentUser"` causes cross-user leaks that single-account tests miss.

## 8. Serialization, Versioning, and Rolling Deployments

With Spring Session, `HttpSession` stores application attributes, including Spring Security objects. Writing to Redis involves key choices:

- **JDK serialization** is the default in many Spring Session Redis setups; it requires serializable classes and carries security risks if untrusted data is ever deserialized.
- **JSON serialization** aids portability/debugging but requires Spring Security-compatible serializers and Jackson mixins/modules. Never enable unrestricted default typing for untrusted data.
- Objects inside `SecurityContext` may include custom principals, user details, granted authorities, and session data. During new releases, changing packages, classes, `serialVersionUID`, or object layouts can prevent node B from deserializing sessions written by node A.
- During rolling deploys, two code versions read/write the same namespace concurrently; run compatibility tests, schema migrations, or namespace separation/planned session invalidation with user notice.
- When Redis is unavailable or deserialization fails, **never synthesize a fake authenticated principal** or fall back to a last-seen user in a static field.

**Recommendation:** store minimal attributes; avoid stuffing large JPA entities/proxies or raw access/refresh tokens into sessions. Pick a format with an allowlisted type set and test across both old and new versions. If an incompatible rollout forces logouts, treat it as an explicit UX/security decision rather than silently returning wrong identities.

## 9. Session TTL, Sliding Expiration, and Update Ordering

Session idle timeout measures **inactivity**, distinct from absolute maximum lifetime. In Spring Session, expiration typically follows `lastAccessedTime + maxInactiveInterval`, though closely spaced accesses on A/B, Redis writes, and cleanup events may not occur synchronously.

Example:

```text
Session idle timeout = 30 minutes
09:00 Login A, lastAccessedTime=09:00
09:20 GET /me B, writes updated lastAccessedTime
09:40 GET /me A, still valid if data updated properly
10:11 Inactive for another 31 minutes → must be treated as expired
```

**Never allow an expired session merely because its physical key has not been purged.** Repositories must enforce expiration per contract; Redis key cleanup can lag, yet access must never rely on "the key still exists so it's valid".

### 9.1. Update Races

When two requests share a session concurrently:

- A reads `SecurityContext`/attributes before logout.
- B performs logout/invalidation or updates a factor/role.
- A finishes later and saves its older snapshot.

Depending on repository/flush mode/attribute updates, **stale writes** can overwrite or resurrect mutated state. Do not assume Redis Hash/session saves include transaction versions/CAS protecting all concurrency scenarios by default.

Highly sensitive state (MFA assurance, admin elevation, forced logout, session version) should use a **server-side source of truth/version**: e.g., `userAuthVersion`/`sessionEpoch` or a revocation index checked on critical requests, alongside CAS/transactions on updates. Mutating a field inside a session object is insufficient if parallel requests commit afterward.

### 9.2. Invalidation and Concurrent Sessions

- Logout invalidates/deletes the session per config, yet an in-flight request may have already passed authorization before logout ran. Define the acceptable window and re-check sensitive operations at commit time.
- Forced logout from another node must delete the session in the shared repository or write a revocation marker checked by every node.
- Limiting concurrent sessions per user requires proper indexes/queries; `RedisIndexedSessionRepository` supports `findByPrincipalName(...)`, though index cleanup and Redis topology require verification.
- Session fixation protection normally rotates the session ID on login; pre-login cookies must never retain privileges of the elevated session.
- Password resets or account disables may need to bump `authVersion` and invalidate old sessions per policy, rather than only updating the password hash in the DB.

## 10. OTT: Issued on Node A, Verified on Node B

Spring Security **6.4+** supports `oneTimeTokenLogin()` on Servlet. Flow:

```text
POST /ott/generate at Node A
  └─ OneTimeTokenService.generate(request)
     └─ creates high-entropy token, username, and expiresAt
        └─ saves to SHARED STORE (JDBC/Redis/...)
           └─ OneTimeTokenGenerationSuccessHandler sends token via trusted channel

User opens magic link → Node B
  └─ submits token (default POST /login/ott)
     └─ OneTimeTokenService.consume(authenticationToken)
        ├─ invalid, expired, used → null → no login
        └─ valid → returns OneTimeToken and ATOMICALLY marks used
             └─ authentication flow creates web session if stateful
```

Spring Security's `OneTimeTokenService` provides:

```java
// API INTERFACE TO UNDERSTAND (6.4+), signature illustration:
OneTimeToken generate(GenerateOneTimeTokenRequest request);

@Nullable
OneTimeToken consume(OneTimeTokenAuthenticationToken authenticationToken);
```

This is an explanatory signature, **not a standalone compilable Java file**. The real interface lives in `org.springframework.security.authentication.ott`. `consume` returns `null` if the token is invalid. Do not confuse this token with TOTP/HOTP: OTT is a single-use token typically sent via email/magic link without a shared client authenticator secret.

### 10.1. Why Is InMemoryOneTimeTokenService Unsuitable for Multi-Node?

Spring Security uses `InMemoryOneTimeTokenService` by default when no dedicated bean/service is provided. If A and B are separate JVMs, each node has its own map; a token issued on A won't be recognized on B, and tokens vanish when A restarts.

For production, the framework docs recommend `JdbcOneTimeTokenService` or another shared implementation. Do not simply "sync maps every few seconds": async replication lets **two nodes both consume the same token** before receiving the used status. Use a shared store **and** atomic consume semantics.

### 10.2. Invariants of a One-Time Token

A valid OTT requires:

1. CSPRNG with high entropy; never use usernames, timestamps, or sequential IDs as secrets.
2. Store records bind the token to **the exact account/tenant/flow/purpose**.
3. Expiration checked inside the consume operation itself (TTL/database time), not only via periodic cleanup.
4. At most one successful consume under concurrency.
5. Prevent password-reset tokens from acting as login tokens or vice versa.
6. Never trust account/email parameters sent by the client at redeem time: derive the subject from the server-created, validated record.
7. Rate-limit token issuance and redemption attempts to prevent enumeration, replay, and mail bombing.
8. Once consumed, never reuse the token even if the HTTP response or login session save fails; define dedicated recovery/idempotency rules.
9. Never log raw tokens in URLs, logs, tracing, analytics, referrers, or tickets; enforce HTTPS, `Referrer-Policy`, and avoid loading third-party content before token exchange completes.

## 11. Integrating JdbcOneTimeTokenService with Spring Security 6.5

In a **Spring Security 6.5** project with Spring JDBC and a shared datasource across nodes, `JdbcOneTimeTokenService` accepts `JdbcOperations` (e.g., `JdbcTemplate`) and implements `OneTimeTokenService`.

**`OneTimeTokenStoreConfig.java`**:

```java
package com.example.multinode;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.authentication.ott.JdbcOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeTokenService;

@Configuration
public class OneTimeTokenStoreConfig {

    @Bean
    OneTimeTokenService oneTimeTokenService(JdbcOperations jdbc) {
        return new JdbcOneTimeTokenService(jdbc);
    }
}
```

The framework detects this bean for the `oneTimeTokenLogin()` DSL when enabled, or you can pass the service explicitly across multiple `SecurityFilterChain` configs:

```java
// Snippet inside an HttpSecurity config (Security 6.5).
.oneTimeTokenLogin(ott -> ott
        .tokenService(oneTimeTokenService)
        .tokenGenerationSuccessHandler(safeTokenDeliveryHandler))
```

**Mandatory requirements to run for real:**

- Requires **the exact migration schema for the library version**; `JdbcOneTimeTokenService` expects the table defined in `classpath:org/springframework/security/core/ott/jdbc/one-time-tokens-schema.sql`. Copy/adapt the migration for your PostgreSQL setup and apply it before enabling the feature. Never invent a table with guessed column names and expect the service to work.
- All nodes share **the same datasource/schema**, compatible pools/timeouts, and transaction semantics.
- Requires an `OneTimeTokenGenerationSuccessHandler` implementation delivering tokens over secured email/SMS. Spring Security **does not automatically know recipient addresses or secure delivery channels**.
- OTT must be configured via `oneTimeTokenLogin()` on the chain covering the generate/submit URLs. Defaults are `POST /ott/generate`, submit page `GET /login/ott`, and login processing `POST /login/ott`; keep CSRF enabled when using web sessions.
- **Verify concurrency of the exact JDBC implementation/version and database isolation** under load. Never claim "having JDBC means guaranteed exactly-once" without testing. When writing a custom service, use conditional updates/deletes inside transactions or equivalent constraints.

### 11.1. Can Redis Sessions and JDBC OTT Be Separated?

**Yes.** Sessions in Redis paired with one-time tokens in PostgreSQL is a valid architecture:

| State | Store | Rationale |
| --- | --- | --- |
| HTTP session | Redis via Spring Session | Fast session-ID lookup, TTL, shared across pods |
| OTT | PostgreSQL via `JdbcOneTimeTokenService` | Shared DB, explicit schema, transactions/constraints |
| Identity/password/account state | User DB or IdP | Dedicated identity source of truth |
| JWT verification keys | Controlled JWKS cache | Resource Server verifies tokens without session mixing |
| Audit events | Outbox/audit sink | Separate durability requirements |

Not all "auth" data belongs in one store; what matters is recognizing that related steps span **separate transaction boundaries**, requiring careful consistency handling when transitioning from a consumed OTT to a logged-in session.

## 12. Atomic Consume: The Core Problem of One-Time Tokens

Typical anti-pattern:

```java
// ANTI-PATTERN, do not use in multi-node:
Token token = repository.find(tokenValue);
if (token != null && !token.isExpired()) {
    repository.delete(tokenValue);
    return login(token.username());
}
```

Two requests on A and B can both read the row before either deletes it. Race order:

```text
A: SELECT token → found
B: SELECT token → found
A: DELETE token
B: DELETE token (0 rows or affectedRows unchecked)
A: login success
B: login success     ← SINGLE-USE VIOLATED
```

A single delete **can be atomic**, yet `read → check → delete → grant` as separate steps is not. You need a single operation where **only one caller** claims the token and retrieves valid subject data while all other callers receive invalid/used.

With a database, use conditional atomic `DELETE ... RETURNING` or transactions with row locks and affected-row checks (engine-dependent). With Redis, use an atomic Lua script or suitable Redis command. **Never use JVM `synchronized` locks** across nodes: each JVM has its own lock.

### 12.1. Illustrative PostgreSQL SQL for a CUSTOM Service

If building a custom OTT store, a minimal table might look like:

```sql
CREATE TABLE single_use_login_token (
    token_digest BYTEA PRIMARY KEY,
    subject_id VARCHAR(150) NOT NULL,
    purpose VARCHAR(50) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX single_use_login_token_expiry
    ON single_use_login_token (expires_at);
```

Generate raw tokens with a CSPRNG and store only a digest/HMAC; store the internal `subject_id` resolved from the account directory and an allowlisted `purpose` enum. PostgreSQL supports conditional deletion returning metadata in one statement:

```sql
DELETE FROM single_use_login_token
WHERE token_digest = :digest
  AND purpose = 'LOGIN'
  AND expires_at > CURRENT_TIMESTAMP
RETURNING subject_id;
```

With a unique primary key and PostgreSQL row-level locking, two racing transactions deleting the same row cannot both receive **the same deleted row**. One statement returns the subject to the winner; the other receives **0 rows** and must reject. Proper input preparation, isolation, and client retries on DB timeouts still require handling.

This is a **custom store model**, not the internal SQL schema or query of `JdbcOneTimeTokenService`. Never swap the framework schema for this illustrative table and expect the JDBC service to recognize it.

### 12.2. Redis Lua: Fetch Subject and Delete in One Atomic Operation

With high-entropy tokens, the server can derive the key from a token **digest/HMAC**, never using the raw token as the key. Issue via `SET key subject NX PX ttlMillis` (after validating subject/purpose/tenant and rate limits), relying on Redis TTL for expiration.

Illustrative atomic redeem Lua script:

```lua
-- KEYS[1]: key derived from HMAC/sha256 of token secret (not raw token)
local subject = redis.call("GET", KEYS[1])
if not subject then
    return false
end
redis.call("DEL", KEYS[1])
return subject
```

If two nodes run this script on **the same key against the same Redis primary**, only the first request gets the subject; the second gets null. Redis checks TTL on key access, so expired keys are not returned as valid tokens.

Watch out for:

- Partition keys by `purpose` and tenant to prevent token confusion.
- An attacker can consume a leaked raw token; protect delivery channels and enforce rate limits.
- Redis Cluster runs a Lua script only across keys in the same hash slot. A single key avoids cross-slot issues, while checking/updating multiple keys requires slot co-location or a different transaction design.
- Redis failover can lose **acknowledged writes not yet replicated/persisted**, potentially resurrecting a deleted token on a promoted replica depending on topology/config. If strict single-use across failovers is mandatory, use stronger durability/consistency or a transactional DB/consensus store and test promotion scenarios.
- If the script succeeds but the network response drops, the client does not know whether redemption succeeded; retrying returns "used". Design safe UX recovery **without opening a branch that accepts already-used tokens**.
- Never record raw tokens in metric labels, Redis MONITOR logs, traces, or audit output.

## 13. Runnable Java 17: Only One Consumer Wins per Token

To see the invariant independently of any framework, the program below models **two nodes sharing one store inside a single JVM**. `ConcurrentHashMap.remove(key, expectedValue)` performs an atomic compare-and-remove in this simulation. **This is not a real network/Redis/DB simulation.**

**`SingleUseTokenDemo.java`**:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class SingleUseTokenDemo {

    record Entry(String subject, long expiresAt) {}

    static final class SharedStore {
        private final ConcurrentHashMap<String, Entry> tokens =
                new ConcurrentHashMap<>();

        void issue(String value, String subject, long expiresAt) {
            tokens.putIfAbsent(value, new Entry(subject, expiresAt));
        }

        boolean consume(String value, String expectedSubject, long now) {
            Entry record = tokens.get(value);
            if (record == null
                    || now >= record.expiresAt()
                    || !record.subject().equals(expectedSubject)) {
                return false;
            }
            return tokens.remove(value, record);
        }
    }

    public static void main(String[] args) throws Exception {
        SharedStore shared = new SharedStore();
        shared.issue("lab-token-1", "alice", 10_000);

        CountDownLatch start = new CountDownLatch(1);
        AtomicInteger accepted = new AtomicInteger();

        Runnable attempt = () -> {
            try {
                start.await();
                if (shared.consume("lab-token-1", "alice", 9_000)) {
                    accepted.incrementAndGet();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread nodeA = new Thread(attempt, "node-A");
        Thread nodeB = new Thread(attempt, "node-B");
        nodeA.start();
        nodeB.start();
        start.countDown();
        nodeA.join();
        nodeB.join();

        System.out.println("accepted = " + accepted.get());

        shared.issue("lab-token-2", "bob", 10_000);
        System.out.println("expired = "
                + shared.consume("lab-token-2", "bob", 10_000));

        shared.issue("lab-token-3", "carol", 10_000);
        System.out.println("wrong-subject = "
                + shared.consume("lab-token-3", "alice", 9_000));
        System.out.println("correct-subject = "
                + shared.consume("lab-token-3", "carol", 9_000));
    }
}
```

Commands:

```bash
javac SingleUseTokenDemo.java
java SingleUseTokenDemo
```

Exact stdout:

```text
accepted = 1
expired = false
wrong-subject = false
correct-subject = true
```

Although thread scheduling is non-deterministic, **exactly one** `remove(value, expectedValue)` call succeeds, so `accepted=1` is deterministic. A token at exact `expiresAt` is expired due to `now >= expiresAt`. Trying with the wrong subject does not consume the token in this demo; real systems must still rate-limit guesses and pick anti-enumeration semantics.

**Never use `lab-token-1` in production.** The demo uses predictable strings for deterministic stdout; real tokens require CSPRNGs and digest/HMAC storage per policy.

## 14. Issuing, Delivering, and Verifying Tokens on Another Node

The token store is only **part** of the flow. Issuance, delivery, and redemption must also be solid:

1. Magic-link generation hits `POST /ott/generate`; rate-limit by account, IP/source, recipient count, tenant, and email/SMS budget.
2. The service resolves the account/verified recipient from a **trusted directory**, never accepting arbitrary target emails from query parameters.
3. The token has high entropy, proper scope/purpose, and short TTL; persisted successfully before sending the link to the user.
4. `OneTimeTokenGenerationSuccessHandler` delivers via a trusted mail/SMS provider or reliable outbox with deduplication/rate limits.
5. The user opens the link on any node. The browser typically loads a submit page and submits the token via a login request matching filter/CSRF contracts.
6. `OneTimeTokenService.consume(...)` validates and atomically consumes the token; the auth flow verifies the user is still active and creates the session.
7. The session is saved to the **shared session store** before the browser needs it on the next request.
8. The next request on another node reads the session and sees the right principal and authorities.

### 14.1. What If Issuance Succeeds but Sending Email Fails?

If the token was saved but the mail provider failed, the record sits until TTL. Never return the raw token in error bodies or logs. You may retry sending via a dedicated outbox while avoiding unbounded token creation per account or sending already-expired links. Per policy, revoke undeliverable tokens and let the user request a new one.

### 14.2. What If Token Consume Succeeds but Session Creation Fails?

This is a **critical consistency boundary between two stores**:

```text
DB/Redis OTT: consume succeeded (token gone)
             ↓
Session Redis: save context failed
             ↓
Client: login failed, retries token → token already used
```

Do not automatically "revert the token to unused": that opens replay windows during races/failovers. Safe UX informs the user to request a new magic link (subject to rate limits), or uses an audited handoff/idempotency flow bound by expiry and subject. If business requirements demand end-to-end exactly-once semantics, analyze transactions across the token and session stores; a DB transaction does not cover a Redis session commit.

### 14.3. Can a Token Survive a Response Network Timeout?

If the OTT was consumed but the `302` response or session cookie was lost in transit, the client sees an error even though the backend already created the session. Retrying the raw token is still rejected; that is the right anti-replay behavior. Log an event/correlation ID, guide the user to check the protected page, and request a fresh link if no session exists. Never add a "retry button" that reuses an already-consumed token without a security-reviewed idempotency design.

## 15. Races Between Sessions, Permissions, and User Data

Beyond OTTs, multiple security operations can run concurrently across nodes:

| Race | Potential Consequence | Mitigation |
| --- | --- | --- |
| A logs out while B has an in-flight request using old session | Sensitive action executes after logout | Check revocation/roles at sensitive commit points, token epoch/version |
| A changes password while B continues old session | Old session keeps privileges unless revoked | Invalidate sessions / revoke all sessions per policy |
| A updates MFA assurance while B saves old snapshot | New factor lost or old factor restored | CAS/versioned state; centralized step-up store |
| A and B rotate session ID concurrently | Cookie ID/repository mapping desyncs | Test session fixation strategy and concurrent logins |
| A issues new OTT while B consumes old OTT | Old token remains usable unless revoked | Per-account nonce/generation version if "latest link only" |
| A and B refresh the same refresh token | Replay/double issuance without atomic rotation | Conditional compare-and-swap + token families |
| A reads roles before change while B revokes role | A acts on stale decision | Define consistency window, re-check permissions at sensitive operations |
| A/B update `lastAccessedTime` on same session | Inconsistent TTL/last-access writes | Store policy/timestamps, monitor session expiration |

**Storage location is not the whole story.** Sharing Redis between A and B solves *visibility* but does not automatically guarantee *per-field atomicity* or *cross-store transactions*. Pick invariants and primitives for each security decision.

## 16. Consistency Requirements During Redis/DB Failover

### 16.1. Read-After-Write

Once login returns success, node B must be able to read the session from the primary/shared store. Reading from an asynchronous replica with lag can cause B to see missing/stale sessions. Configure read/write routing consistently per session contract; never place auth state into eventually consistent caches/replicas implicitly.

### 16.2. Atomicity

Token consumption must be **decided in a single place**. Single-key Redis Lua executes atomically on the primary at execution time. PostgreSQL conditional `DELETE`/`UPDATE` inside a transaction picks one winner. Multi-primary setups with eventual conflict resolution can yield two winners without coordination; unsuitable for strict single-use.

### 16.3. Durability and Acknowledgment

Standard Redis replication is often asynchronous; a write acknowledged by the primary may not be durable on the promoted node after failover. `WAIT`/`WAITAOF` and AOF/replication tuning narrow the loss window but do not turn Redis into a consensus protocol for all failure models. For strict replay prevention across failovers, consider stores with durable transactions/consensus and test failover promotion explicitly.

### 16.4. Clock Consistency

- Session expiration, OTT TTL, and TOTP windows must define their time source.
- Never use untrusted client clocks. With Redis TTL, the store checks lifetime natively; with SQL, use DB time in consume conditions where appropriate.
- Synchronize NTP across nodes, DBs, IdPs, and metrics; record UTC timestamps and distinguish event time from processing time.
- Some libraries expose an injectable `Clock` (such as `JdbcOneTimeTokenService#setClock`), useful for deterministic tests; prevent large clock skew across nodes.
- Never grant access merely because scheduled cleanup has not purged expired tokens yet.

### 16.5. Partitions and Timeouts

When the store is unreachable, the app must choose **fail closed or a protected degraded mode**. For unverified sessions and one-time tokens, **never authenticate successfully without a trustworthy answer**. Return HTTP 503/401 depending on cause, avoiding misleading "wrong password" errors during Redis outages.

Never add a local OTT cache to "cushion Redis errors" if that cache could let consumed tokens be reused after a partition.

## 17. Redis Eviction, Memory, and TTL Do Not Guarantee Absolute Safety

Redis uses `maxmemory`/eviction policies. If configured to evict session/OTT keys before expiry, users suffer unexpected logouts or broken magic links. That is primarily an availability/UX issue; however, if an old Redis replica is promoted, deleted keys can reappear, creating a safety issue.

Monitor:

- `used_memory`, `maxmemory`, `evicted_keys`, expired keys, memory fragmentation.
- Session and OTT `GET`/`SET`/`DEL` throughput and p95/p99 latency.
- Actual session and OTP TTLs, active session counts, pending tokens by purpose.
- Redis connection pools, timeouts, retries, rejected calls, replication lag, and failover duration.
- Key cardinality: attackers generating many username/token requests can push state to OOM.
- Serializer failures and session deserialization errors across rolling deployments.
- Auth successes/401s/403s, login redirects, invalid/used/expired OTTs, and duplicate redemption attempts.

**Never pick Redis `maxmemory-policy` and TTLs by guesswork.** Isolate namespaces/instances/DBs, plan capacity, enforce ingress quotas, and throttle token issuance. For sessions that must not be evicted prematurely, operate storage against matching SLOs.

## 18. Multi-Node and Concurrency Testing Is Non-Negotiable

### 18.1. Mandatory Matrix

| Scenario | Expectation |
| --- | --- |
| Login on A, `GET /me` on B with same session cookie | Exact user/authorities; no re-login |
| Login on A, kill A, `GET /me` on B | Session remains valid while shared store is up and unexpired |
| A and B log in two different users, interleaved GETs | Zero identity/cross-session leaks |
| Logout on B, then access A with old session | No longer authenticated |
| Session past idle timeout | Protected requests lose access |
| A issues OTT, B redeems | B accepts valid token and creates session |
| A and B concurrently redeem same OTT | **At most one** request succeeds |
| Consume OTT then retry same link | Rejected as used/invalid |
| Expired token whose DB row/Redis key still exists | Rejected |
| Account A's OTT used to log in as B | No subject confusion |
| Login for disabled user or revoked password | Blocked per account policy |
| Session ID rotation at login | Old session ID does not become an authenticated session |
| Redis failover during session write/delete | No phantom sessions or resurrected revoked sessions |
| Token store DB timeout during consume | Never defaults to allowing access |
| Two app versions running concurrently | Compatible session/OTT deserialization or safe failure |
| One node has major clock skew | Expiry/TTL policies remain enforced |
| Retried email sends | No token reuse or unbounded spam |
| Token consumed but session save fails | UX prompts for new token without reviving old one |
| Redis/DB pool exhausted | Never turns into authentication bypass |
| Redis Cluster/index event skew | Index cleanup events never treated as absolute revocation proof |

### 18.2. Separating Test Types

**Unit tests** check token algorithms, CAS/conditional deletes, exact expiry boundaries, and subject policies. The Java demo in section 13 shows the JVM invariant, **not** the Redis/JDBC implementations.

**MockMvc** tests real form login, `SecurityContextRepository`, and POST→GET with the same `MockHttpSession`. It runs inside a single Spring context unless specially rigged.

**Multi-node integration tests** run two app processes/containers sharing Redis/PostgreSQL, forcing traffic directly to A and B instead of relying on sticky LBs. Parallel tests use barriers/latches, verifying at most one redemption succeeds and inspecting post-test DB state.

**Chaos/failover tests** simulate killing nodes, Redis failover, DB replica lag, network partitions, pod restarts, autoscaling, Redis evictions, and multi-version rollouts. Reports must verify whether safety invariants held, not merely HTTP 200 rates.

### 18.3. How Can Atomic Consumption Tests Mislead?

If a concurrency test sends two requests sequentially, even a non-atomic `find → delete` passes (the second request sees the token gone), creating **false confidence**. Fire hundreds or thousands of concurrent attempts behind a barrier across **two real nodes** and count successes per token.

If the load balancer retries on 502/timeout, ensure retrying a POST redeem never re-executes an already-succeeded request under old credentials. Log correlation/event IDs to distinguish network retries from users double-clicking links, without logging raw tokens.

## 19. Securing Cookies, Tokens, and Data at Rest

### 19.1. Cookies and Sessions

- Require HTTPS and `Secure` cookies in production.
- Configure `HttpOnly`, `SameSite`, and `Path`/`Domain` matching login/SSO architecture.
- Never use a broad cookie domain exposing sessions to untrusted subdomains.
- Enforce CSRF protection on cookie/session-backed state-changing web requests.
- Enforce session fixation protection on login; never log cookies/session IDs or put IDs in URLs.
- Handle invalidation on logout/timeout/role changes across all clients/sessions per explicit policy.
- Protect session stores with encryption in transit, ACLs, restricted admin commands, and backup/restore policies.

### 19.2. OTT / Magic Links

- High-entropy, short-lived, single-use tokens with subject/purpose binding.
- Raw tokens must never enter analytics, third-party link previews, access logs, traces, or browser referrers. Set `Referrer-Policy: no-referrer` on link-landing pages and avoid third-party scripts before token processing completes.
- If email security scanners pre-click magic links, a plain GET **should not immediately consume the token** when designed as a GET submit page followed by a CSRF-protected POST consume. Never trigger auth side effects on GETs hit by external scanners.
- Never redirect magic links to unvalidated query-parameter URLs; prevent open redirects.
- Rate-limit issuance/verification and return generic messages to prevent username enumeration.
- If a store retains raw tokens, evaluate switching to hashes/HMACs per threat model, encryption, and DB permissions; never assume JDBC/Redis removes sensitive data automatically.

### 19.3. Securing Redis/DB

Anyone able to read Redis sessions can inspect `SecurityContext` or session attributes; anyone able to write can forge state. **Redis is not harmless** merely because it sits in a private subnet. Use mTLS/TLS where supported, IAM/ACLs, network segmentation, zero public exposure, least privilege, secret rotation, and access auditing. Backups/restores must preserve expiry/revocation semantics; restoring an old snapshot can **resurrect revoked state** unless checked against `authVersion`/ledgers.

## 20. Common Implementation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Local `HttpSession` only across multiple pods | Users logged out when hitting another node | Spring Session shared store or explicit stateless design |
| Relying solely on LB sticky sessions | Fails on node death/rolling deploys | Shared store + failover integration tests |
| Having Redis but forgetting to save `SecurityContext` in custom login | Next request is anonymous | `SecurityContextRepository.saveContext(...)` |
| Using `InMemoryOneTimeTokenService` per node | Issued on A, unredeemable on B | Shared JDBC/Redis `OneTimeTokenService` |
| Non-atomic read-then-delete on tokens | Two nodes log in from one token | Conditional delete/transaction/Lua |
| Skipping TTL check during consume | Expired tokens usable before cleanup | Enforce expiry inside consume logic |
| Using `synchronized` to lock OTTs | Locks only one JVM | Shared-store atomic primitives |
| Treating async Redis replication as durable exactly-once | Failover resurrects consumed state | Evaluate durability/replay, test promotion |
| Setting session TTL equal to OTT TTL | Users logged out fast or links live too long | Separate lifecycles per artifact |
| Using stateless JWTs like stateful sessions | Skips signature/audience or adds needless state | Proper JWT decoder and authorization |
| Reading auth state from stale replicas | Post-login GET misses session | Read-after-write consistency per contract |
| Serializing whole entities/proxies in sessions | Rolling deploy crashes, data leaks | Minimal snapshots, controlled serializers |
| Skipping session fixation protection | Pre-login session ID gets elevated | Session ID rotation and cookie security |
| Skipping principal check during OTP redemption | Account confusion / phishing | Bind subject/tenant/purpose to token |
| Unthrottled OTT issuance | Mail bombing and key-store bloat | Account/source/global quotas |
| Reviving token when consume succeeds but session save fails | Opens replay backdoor | Safe recovery/new token, idempotency design |
| Logging raw tokens/cookies | Credential replay | Redact at source, audit with hashed IDs |
| Caching authorization revocations locally too long | Revoked on A, still active on B | Epoch/version checks, bounded TTL, critical rechecks |
| Treating cleanup events as source of truth for expiry | Events lag or drop | Enforce expiry against repository state |
| Skipping real multi-node tests | Misses races and cross-node bugs | 2+ node integration, chaos, and concurrency tests |
| Redis outage → `permitAll()` | Authentication bypass | Fail closed with clear UX/error contract |

## 21. Deployment and Operations Checklist

Before rollout, verify you can answer yes to each:

- [ ] Classified sessions, OTTs, CSRF, refresh tokens, and JWTs and assigned store ownership?
- [ ] Every node shares the same session namespace/store, cookie contract, and `SecurityContextRepository`?
- [ ] Proven `GET /me` on node B reads the right identity after login on A?
- [ ] Tested logout on B revokes access on A and old requests?
- [ ] OTT uses CSPRNG, TTL, subject/purpose binding, rate limits, and a shared store?
- [ ] Verified **atomic consumption** across 2+ nodes under real concurrent requests?
- [ ] Expiration enforced at consume time, independent of scheduled cleanup?
- [ ] OTT DB schema matches Spring Security 6.4+ and is managed via migrations?
- [ ] Verified CSRF on OTT POSTs, verified recipient delivery, and prevented scanners from consuming tokens via GET?
- [ ] Redis/session serialization works across two app versions during rolling deploys?
- [ ] Redis eviction, failover, replication lag, and memory capacity have limits and alerts?
- [ ] Defined fail-closed behavior when auth state or token stores are unreachable?
- [ ] Handled permission revocation, MFA step-up, and refresh rotation with concurrency/versioned state?
- [ ] Metrics track p95/p99 session reads, token consumption, invalid/used/expired counts, login failures, and retries?
- [ ] Logs exclude session IDs, raw OTT tokens, passwords, refresh/access tokens, and sensitive payloads?
- [ ] Tested two cookie jars/users, node kills, snapshot restores, and failovers?
- [ ] Documented exact consistency/durability guarantees rather than vaguely claiming "we use Redis"?

## 22. Self-Practice Exercises

1. Take the Spring Boot 3.x form login project in section 6 and run 2 instances A/B sharing Redis. Log in on A and access `/me` on B. Then kill A and keep hitting B.
2. Swap Redis back to local `HttpSession`. Why do single-node tests pass while B fails? Do sticky sessions fix every failure mode?
3. Enable `oneTimeTokenLogin()` in Spring Security 6.5, register `JdbcOneTimeTokenService` with the framework schema table and a safe mail handler. Issue on A, redeem on B.
4. Write a concurrent integration test firing 10–100 simultaneous requests for one OTT. Assert the invariant **max successes = 1** across both nodes and under retries.
5. Replace a custom `read → delete` token store with PostgreSQL conditional `DELETE RETURNING` or atomic Redis Lua. Explain the difference when two requests read the same row.
6. Inject a fault: token consume succeeds while Redis session save times out. Design recovery UX without reusing the old token; verify consume count stays 1.
7. Test a Redis restart/failover right after deleting an OTT. Compare acknowledged writes when replicas lag, and choose a store when strict anti-replay is required.
8. Test a rolling deploy of two app versions with differing custom `UserDetails` structures. Add migration/serializer compatibility tests to prevent lost identities or deserialization errors.
9. Design revoke-all-sessions on password change using `authVersion` per user and session. At which steps must the version be verified?
10. Compare OTT login, TOTP MFA, refresh token rotation, and stateless JWTs from the angles of shared state, TTL, and replay.

## 23. Summary and Official Sources

- For multi-node form/session websites, **share `HttpSession` and `SecurityContext` via a shared store**; Spring Session Redis is a standard choice.
- **Sticky sessions are only a routing optimization**; they do not replace shared visibility or failover. Spring Security 6 custom logins also require explicit context saving.
- OTT in Spring Security **6.4+** uses `OneTimeTokenService`; the default in-memory implementation is not multi-node. Use JDBC or a proper shared service with schema, expiry, and atomic consumption.
- **Shared store ≠ atomicity; atomicity ≠ durability.** Redis Lua/conditional SQL resolve races; replica failovers and network timeouts still demand explicit consistency design.
- Every artifact has its own **lifecycle and requirements**: session idle TTL, short single-use OTT expiry, stateless JWTs, refresh rotation, MFA assurance, and logout/revocation.
- Declare authentication successful only with complete proof. Never fall back to `permitAll()` if Redis/DB fails; enforce subject checks and anti-replay.
- Protect cookies/tokens, monitor latency/backlog/eviction, and **test across two real nodes** for concurrency, expiration, rolling deploys, and failover.

**Official documentation to verify by version:**

- [Spring Session 3.5 — Spring Boot + Redis](https://docs.spring.io/spring-session/reference/3.5/guides/boot-redis.html)
- [Spring Session 3.5 — Redis configuration and repository types](https://docs.spring.io/spring-session/reference/3.5/configuration/redis.html)
- [Spring Session 3.5 — Spring Session with Spring Security](https://docs.spring.io/spring-session/reference/3.5/guides/java-security.html)
- [Spring Security 6.5 — Session Management and explicit SecurityContext save](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html)
- [Spring Security 6.5 — OneTimeTokenService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html)
- [Spring Security 6.5 — JdbcOneTimeTokenService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/JdbcOneTimeTokenService.html)
- [Spring Security 6.5 — HttpSessionSecurityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)