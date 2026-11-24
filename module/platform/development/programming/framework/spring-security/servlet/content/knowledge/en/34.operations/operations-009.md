# Performance of Password Hashing, Permission Queries, and External Identity Providers in Spring Security Servlet

## 1. Operational Challenge: Secure Authentication and Authorization That Meet SLOs

A **Spring Security Servlet** application typically has three major cost sources on the authentication/authorization path:

1. **Password hashing/verification**: password hashing functions are intentionally CPU-intensive, and sometimes memory-intensive; this is a security property protecting passwords if data leaks, not simply a performance bug.
2. **Identity and permission queries**: loading `UserDetails`, authorities, groups/roles, and object/tenant policies can cause many SQL queries, N+1 patterns, or stale caches.
3. **External identity provider dependencies**: OIDC/OAuth2 providers, JWKS endpoints, OAuth2 introspection, LDAP, or remote authorization services add network latency and unavailability risk.

When users report "login is very slow", you should not immediately lower the BCrypt work factor or turn off permission checks. Instead, **identify the exact path, measure per-step cost, optimize what does not weaken security, and evaluate concurrent load**.

Examples:

- A POST login page using password authentication: may require querying the user, verifying the password hash, saving the session, and checking account status.
- An HTTP request carrying a JWT: usually verifies the token **locally** after fetching public keys from a JWKS cache; it does not necessarily call the Identity Provider on **every request**.
- An HTTP request carrying an opaque access token: may require calling remote **introspection** on each authentication unless appropriate caching is configured.
- A request to an admin endpoint: may check authorities from a token, session, or a database ACL/role service; this may occur per request or per method call depending on design.
- OAuth2 Login authorization code: interactions with the IdP occur during redirects/callbacks, which does not mean every post-login request calls the IdP.

This article focuses on **measurement, load modeling, practical configuration, caching strategies, and safe operations** for **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC Servlet**.

## 2. Before Optimizing: Map Latency and Trust Boundaries

A password login path might look like this:

~~~text
POST /login
  │
  ├── Servlet filter chain / AuthenticationManager
  │     │
  │     ├── UserDetailsService.loadUserByUsername()
  │     │      ├── SELECT user + account status
  │     │      └── SELECT/group authorities (if needed)
  │     │
  │     ├── PasswordEncoder.matches(raw, encoded)
  │     │      └── Intentional CPU + memory cost
  │     │
  │     └── Authentication success/failure + SecurityContext
  │
  └── HTTP response, session/cookie if present
~~~

A token-bearing HTTP request follows a different path:

~~~text
GET /api/reports
  │
  ├── BearerTokenAuthenticationFilter
  │     │
  │     ├── JWT: JwtDecoder + signature/claims validation
  │     │      └── Key lookup/JWKS typically uses cache
  │     │
  │     └── opaque token: OAuth2TokenIntrospector
  │            └── May require an HTTP request to IdP
  │
  ├── authorizeHttpRequests / @PreAuthorize
  │     └── Existing authority or requires ACL/tenant lookup
  │
  └── Controller, business service, database/downstream
~~~

**Do not conflate the costs of the two flows.** A JWT Resource Server **does not** normally run `PasswordEncoder.matches()` against user passwords on every request. `PasswordEncoder` belongs to password authentication or password changes; Bearer token authentication is a separate flow. Conversely, when an application uses HTTP Basic, passwords may be re-verified per request depending on caching/context mechanisms, making that path heavier than session login.

### 2.1. Place Metrics at the Right Boundaries

| Metric | Meaning | Purpose |
| --- | --- | --- |
| `auth.login.duration` p50/p95/p99 | Total login duration (success/failure) | Detects tail latency and user-facing impact |
| `auth.password.verify.duration` | Time spent in `PasswordEncoder.matches()` | Compares cost/hash implementation/hardware |
| `auth.user.lookup.duration` | Time to look up user + roles | Diagnoses SQL, connections, indexes |
| `auth.authorization.duration` | Time to decide permissions | Spots repeated ACL queries and expensive policies |
| `auth.idp.request.duration` | HTTP to token/introspection/userinfo/JWKS | Shows latency, timeouts, dependency health |
| `db.pool.active/pending` | Connection pool pressure | Detects queueing or pool exhaustion |
| `executor.active/queued`, CPU/GC | Thread, memory, and wait pressure | Checks if password hashing saturates resources |
| Error rates 401/403/429/5xx | Separates bad credentials, missing perms, rate limits, outages | Avoids treating every 401 as a performance bug |
| Token cache/JWKS cache hit/miss | How often remote keys/discovery are fetched | Detects wasted cache misses and key rotations |

`p95` is a percentile of **a request population**, not a mean; step p95s **cannot simply be summed** to derive end-to-end p95 because steps correlate and have different distributions. Use tracing or end-to-end distribution measurements.

**Never put raw passwords, encoded passwords, access tokens, refresh tokens, Authorization headers, session IDs, client secrets, or sensitive identifiers** into metric tags, tracing spans, or logs. Metrics should have bounded label values—such as `outcome=success|failure|timeout` and normalized operation names—never usernames or tokens as labels.

### 2.2. Latency Budgets and Capacity

Set separate SLOs for logins, authenticated requests, and endpoints calling the IdP. For instance, a system **picks** a p95 target for login and budgets time across DB, hashing, session, and proxy; that number must reflect your product and environment—there is no single default applicable to every Spring Security app.

Specifically for password hashing, a key metric is **concurrent verifications**. If one verification takes 200 ms of CPU on running infrastructure and there are 50 new logins/second, that load alone creates CPU demand roughly equivalent to 10 concurrent verifications under a simplified model. This is a **capacity estimate**, before accounting for CPU contention, queueing, garbage collection, or actual core counts.

Optimization must compare **throughput, p99, CPU, memory, rate-limit hit rates, and security impact**, not just a single hash run on a developer laptop.

## 3. Why Must Password Hashing Be Intentionally Slow?

Passwords are user-chosen secrets with limited entropy, not strong random keys. If a password-hash database leaks, attackers can test huge numbers of guesses offline. **Slow, uniquely salted, computationally expensive password hashing** makes guessing passwords far costlier.

Commonly used algorithm families:

| Algorithm | Properties | Operational notes |
| --- | --- | --- |
| Argon2id | Memory-hard, combines memory/time/parallelism costs | Must measure both CPU and memory; verify compatible libraries/encoders |
| scrypt | Memory-hard, tunable cost/memory size | Can cause memory pressure under heavy concurrent logins |
| bcrypt | Cost tuned by iteration rounds, common in Spring | Measure CPU; remember implementation input-length limits |
| PBKDF2 | Multiple iterations, common in regulated algorithm environments | Needs adequate iteration counts; one round is never enough |
| Direct SHA-256/MD5 | Very fast general-purpose cryptographic hash | **Not safe enough for storing user passwords directly** |

**Do not blindly pick** an algorithm/cost just because an online snippet had nice numbers. Recommended levels evolve with time, hardware, and compliance rules. Consult current Spring Security password storage docs, OWASP, and applicable standards; benchmark on your target environment, then publish a controlled upgrade policy.

### 3.1. Salt, Pepper, and Encoded Passwords

- Every password hash needs an **independent random salt**. Modern encoders typically pack salt, parameters, and output into the encoded string.
- Salt is **not a secret** and can be stored alongside the encoded password; never use one static salt system-wide.
- **Pepper**, if used, is an additional organization-managed secret separate from the DB. You must plan storage/rotation/recovery; pepper does not replace a proper password hashing algorithm.
- Never store plaintext, reversible encrypted passwords for login convenience, or plain `SHA-256(password)`.
- Never log or return encoded passwords to the frontend. Encoded hashes remain security-sensitive data requiring restricted access because they enable offline attacks.

**bcrypt and input length:** many bcrypt implementations enforce an input byte limit (often 72 bytes); handling of long strings, Unicode, versions, and preprocessing depends on the library. Never silently truncate passwords or apply ad-hoc incompatible pre-hashing. Define clear input policies, document them, and test Unicode and algorithm migrations.

### 3.2. CPU/Memory Pressure Is Part of the Threat Model

High work factors resist offline brute force but make online logins CPU-heavy. Attackers can flood login requests to exhaust worker threads. The answer is not weakening the cost factor; it is **rate limiting, admission control, concurrency bounds, edge protection, monitoring, and capacity planning**.

Protections include: rate limiting by account + IP/risk signals (not IP alone), max concurrent logins, sensible timeouts/queues, credential-stuffing detection, and challenges/risk checks when warranted. Avoid locking accounts so aggressively that attackers can trigger denial-of-service against victims.

**Balancing security and operations:** never add an indefinite "password valid for user X" cache to skip hash verification across requests; design sessions/tokens via Spring Security mechanisms so password verification is not repeated unnecessarily.

## 4. Configuring PasswordEncoder in Spring Boot / Security 6

In Spring Security, the core interface is `PasswordEncoder`:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword,
                    String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

This is an abbreviated signature to explain the contract, not instructions to reimplement the framework interface. `encode()` runs when creating/changing passwords, `matches()` runs during verification. `upgradeEncoding()` indicates whether an encoded password should be upgraded under the current encoder policy (depending on implementation).

A common configuration in Spring Boot 3 / Security 6, file `PasswordConfig.java` in package `com.example.demo`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }
}
~~~

`DelegatingPasswordEncoder` distinguishes algorithms by prefix in the encoded value, e.g., `{bcrypt}...`; encoding **new** passwords uses the factory's current-version default algorithm, while matching can accept configured legacy formats. **Never assume** the factory default across every version uses a fixed cost matching your organization's policy: inspect the actual created encoder and benchmark on your target deployment.

If your organization specifies a dedicated bcrypt cost, e.g.:

~~~java
@Bean
PasswordEncoder bcryptEncoder() {
    return new org.springframework.security.crypto.bcrypt
        .BCryptPasswordEncoder(12);
}
~~~

**Treat this strictly as an example of configuring cost 12, not a blanket recommendation.** When switching the bean to a plain `BCryptPasswordEncoder`, check whether stored passwords carry a `{bcrypt}` prefix or are raw bcrypt strings. A plain `BCryptPasswordEncoder` does not automatically strip prefixes; verify encoder changes against stored data and backward compatibility. In real Java code, keep class imports on **one line**, e.g.:

~~~java
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
~~~

If already using `DelegatingPasswordEncoder`, you can configure encoder mappings per policy to generate new standard hashes while still verifying old ones. Never strip prefixes or rewrite encoded DB strings without proving the migration safe.

### 4.1. Rehashing on Successful Login

When increasing work factors or switching algorithms, you do not need to force every user to reset passwords immediately if policy allows **rehash after successful login**:

~~~text
User enters password
  │
  ├─ Load old encoded password from DB
  ├─ PasswordEncoder.matches(raw, oldEncoded) == true
  │
  ├─ Check upgradeEncoding(oldEncoded)
  │     ├─ false -> continue authentication
  │     └─ true  -> encode(raw) under new policy
  │                 -> save new hash safely/atomically
  │
  └─ Return authentication success
~~~

Spring Security provides `UserDetailsPasswordService` integrated with `DaoAuthenticationProvider` to upgrade passwords when configured properly. **Do not just enable `upgradeEncoding()` and assume the database updates itself**: verify the hash-update implementation and transactional/conditional write logic so migration cannot overwrite a concurrently changed password.

Monitor both **upgrade encode time** (which adds cost to certain logins) and verify time. Never put raw passwords into audit logs, metrics, async queues, or retry jobs.

### 4.2. Choosing Work Factors via Conditional Benchmarking

Practical workflow:

1. Identify the algorithm, library, version, and hash formats currently in the DB.
2. Measure `encode()` and `matches()` with synthetic test data (never real passwords) on CPU/memory of a **production-like container/VM**.
3. Measure across concurrency levels, including peak traffic and spikes; record p50/p95/p99, CPU throttling, and memory pressure.
4. Check sustainable logins/second, queueing, and remaining capacity for the application.
5. Test rate limits/overload handling so attackers cannot occupy the entire thread pool.
6. Compare against organizational security requirements; pick a strong cost **without breaking availability**.
7. Plan upgrades/migrations and re-measure after changing CPU sizes, container limits, JVM, or libraries.

**Never benchmark with a single run and call that number p95.** JVM warm-up, CPU schedulers, thermal throttling, and co-tenancy skew results. Run benchmarks outside deployment windows alongside end-to-end load tests.

### 4.3. Safe JUnit Micro-Benchmark Example for Test Environments

File `PasswordCostTest.java` under `src/test/java/com/example/demo/`; it has **no hard-coded expected timing**, because timing must be measured directly on the running machine:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

class PasswordCostTest {

    @Test
    void measureVerifyLatencyOnCurrentMachine() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(12);
        String encoded = encoder.encode("demo-password-only");

        // Short warm-up; formal benchmarks need more samples.
        assertTrue(encoder.matches("demo-password-only", encoded));

        List<Long> samples = new ArrayList<>();
        for (int i = 0; i < 7; i++) {
            long start = System.nanoTime();
            boolean valid = encoder.matches(
                "demo-password-only", encoded);
            long elapsed = System.nanoTime() - start;

            assertTrue(valid);
            samples.add(elapsed);
        }

        Collections.sort(samples);
        double medianMillis = samples.get(samples.size() / 2)
            / 1_000_000.0;

        System.out.printf(
            "bcrypt_verify_median_ms=%.1f%n", medianMillis);
    }
}
~~~

**Meaning:** the test runs real `matches()` and prints the median of seven samples on the **current machine**. This is only a conditional smoke measurement, **not a scientific benchmark or sufficient basis for choosing production cost**. Do not fabricate expected millisecond stdout; run on your deployment target with proper sampling and load tests. Use only non-sensitive test passwords and never log encoded passwords.

## 5. Permission Queries: Reducing Round Trips Without Stale Permissions

### 5.1. Authentication DB and Authorization DB Are Not Always in the Same Step

With form login + `DaoAuthenticationProvider`, `UserDetailsService.loadUserByUsername()` typically runs at authentication time. `UserDetails.getAuthorities()` may hold roles/authorities loaded at login. Afterward, when using HTTP sessions, Spring Security can reuse the session's `SecurityContext` instead of re-querying on every request.

Conversely:

- Stateless Bearer requests may validate JWTs and read authorities from tokens on **every request**.
- `@PreAuthorize` may invoke a custom `PermissionEvaluator`, ACL policy, or repository **each time a service method is called**.
- A single request may fetch 100 resources and check permissions on each one, causing **N+1 queries** even though login ran only one query.
- A user's roles might change while a session is active, while context/claims retain old roles; cutting queries simultaneously raises **stale authorization** risk.

Identify the **source of truth for permissions**: JWT claims, session authorities, local DB, ACL service, policy decision point (PDP), or a combination. Never "cache all permissions" blindly.

### 5.2. N+1 Role Lookups and Pagination

An N+1-prone pattern:

~~~text
SELECT * FROM app_user WHERE username = ?
SELECT authority FROM user_authority WHERE user_id = ?
GET /orders (100 records)
  -> SELECT ... permission ... WHERE order_id = ?   (repeated 100 times)
~~~

Having multiple queries is not automatically wrong; the problem is query counts scaling linearly with object counts or uncontrolled request fan-out.

Ways to improve:

- For user profiles and small authority sets: **join/fetch once** on the auth path instead of querying roles row by row.
- For object-level permissions: use **set-based authorization queries**, e.g., querying the list of orders the user is allowed to view rather than fetching 100 orders and checking 100 times.
- Create **indexes matching real WHERE/JOIN clauses**; inspect `EXPLAIN (ANALYZE, BUFFERS)` in PostgreSQL rather than merely assuming an index helps.
- Bound scopes, pagination, and returned authority counts; avoid stuffing an entire enterprise policy graph into `Authentication`.
- Use parameterized queries; never concatenate username/tenant/resource IDs into raw SQL strings.

### 5.3. Illustrative Schema and Indexes

**PostgreSQL-style SQL** example (other engines may vary):

~~~sql
CREATE TABLE app_user (
    id BIGINT PRIMARY KEY,
    username VARCHAR(200) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE user_authority (
    user_id BIGINT NOT NULL REFERENCES app_user(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, authority)
);

-- UNIQUE(username) supports login lookup by username.
-- PRIMARY KEY(user_id, authority) supports joins by user_id.

SELECT u.id, u.username, u.password_hash,
       u.enabled, a.authority
FROM app_user u
LEFT JOIN user_authority a ON a.user_id = u.id
WHERE u.username = ?
ORDER BY a.authority;
~~~

The `?` in the final SQL query is a **JDBC bind parameter**, not valid direct syntax when pasted into `psql`. The DDL is a learning example; production needs proper migrations, policies, secrets, backups, tenant modeling, user statuses, and soft deletion.

In multi-tenant data, `username` is not necessarily globally unique. When tenant is part of identity, enforce unique keys and query by **`(tenant_id, username)`**; the tenant ID must come from an authenticated/verified context, never trusting a client-supplied header to read another tenant's authorities.

### 5.4. UserDetailsService Example Using One Join Query

File `DbUserDetailsService.java` for a Boot app with `spring-boot-starter-jdbc`, a datasource, and the tables above. This is a **Spring project class**, not standalone Java. Single join query reading user and authorities:

~~~java
package com.example.demo;

import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class DbUserDetailsService implements UserDetailsService {

    private final JdbcTemplate jdbc;

    public DbUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record AuthRow(String username, String passwordHash,
                           boolean enabled, String authority) {}

    @Override
    public UserDetails loadUserByUsername(String username) {
        String sql = """
            SELECT u.username, u.password_hash, u.enabled, a.authority
            FROM app_user u
            LEFT JOIN user_authority a ON a.user_id = u.id
            WHERE u.username = ?
            ORDER BY a.authority
            """;

        List<AuthRow> rows = jdbc.query(sql,
            ps -> ps.setString(1, username),
            (rs, row) -> new AuthRow(
                rs.getString("username"),
                rs.getString("password_hash"),
                rs.getBoolean("enabled"),
                rs.getString("authority")));

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("User not found");
        }

        AuthRow first = rows.get(0);
        String[] authorities = rows.stream()
            .map(AuthRow::authority)
            .filter(Objects::nonNull)
            .distinct()
            .toArray(String[]::new);

        return User.withUsername(first.username())
            .password(first.passwordHash())
            .disabled(!first.enabled())
            .authorities(authorities)
            .build();
    }
}
~~~

**Explanation:**

- `LEFT JOIN` ensures an account with zero authorities is still found; access to protected resources depends on policy. Never grant `ROLE_USER` automatically if the account/permission store did not grant it.
- `JdbcTemplate` uses prepared statements; `username` is never concatenated directly into SQL.
- Avoids N additional role queries per row. However, a join can multiply rows by authority count; **measure against real data** to see whether one join or two queries is faster.
- `enabled=false` is not bypassed just because SQL returned roles. `DaoAuthenticationProvider` checks `UserDetails` flags as configured.
- Never throw exceptions leaking usernames/SQL secrets into HTTP responses. `UsernameNotFoundException` lets the auth flow handle failure; external messages must prevent account enumeration.
- In environments with role hierarchies, organizations, resources, groups, or tenants, standardize mapping and dedicated authorization checks. Authorities returned from DB **do not guarantee** resource ownership checks.

Additional JDBC dependencies when using the sample above:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

This extends a project already using Spring Security Starter/Web and a datasource. If not using PostgreSQL, swap the driver/DDL accordingly. Running the full flow requires table schemas/migrations, test DB data, and a `PasswordEncoder` matching encoded hashes.

### 5.5. Why Do Indexes and Connection Pools Matter?

A role query using a good index can still be slow due to **connection acquisition**: exhausted HikariCP pool, long-running transactions, row locks, DB network RTT, and queueing. Measure separately:

- Pool wait time vs. actual SQL execution time.
- Query execution plans, rows scanned/returned, full table scans, and sorts.
- Query counts per request and per user (via aggregate metrics; never use user IDs as high-cardinality tags).
- Database CPU, I/O, locks, deadlocks, and connection saturation.
- Transaction boundaries: avoid holding DB connections open while calling a remote IdP or performing long CPU password hashing unnecessarily.

**Never increase pool size indefinitely** to fix latency: databases have finite connection and concurrency limits. Balance Servlet, Hikari, IdP HTTP client thread pools, and service throughput.

## 6. Caching Permissions: Faster Yet Must Preserve Revocation

An authority/ACL cache can cut database queries sharply. However, if an admin revokes `PAYMENT_APPROVE`, serving a stale cached "allow" for too long creates a security vulnerability.

### 6.1. Caching Strategy by Data Type

| Data | Cacheable? | Key risks |
| --- | --- | --- |
| Public/slow-changing user profile | Yes, with suitable TTL | Stale display, view-permission bounds |
| `UserDetails` + authorities in session | Usually already in session context | Role/lock/revocation not reflected immediately |
| Global role definitions and role-to-permission maps | Possible if versioned | Policy changes do not apply instantaneously |
| Object/tenant-level permissions | Cautious, short TTL / explicit invalidation | Cross-tenant leaks or revoked permissions persisting |
| JWT claims | Token is signed and verified; old token claims cannot be edited | Token remaining lifetime creates a staleness window |
| Opaque token introspection result | Possible with policy-bounded TTL | Revoked tokens remain accepted until TTL expires |
| Plaintext passwords or "password matches" results | **Never cache auth to skip verification** | Credential replay or security bypass |
| JWT signing public keys/JWKS | Typically cached by decoder/HTTP client | Key rotation, stale keys, outages, and cache-miss storms |

For role/ACL caches, cache keys must include **stable user ID + tenant + resource/action or policy version** where relevant. Never cache by plain username across multi-tenant systems. Avoid infinite "positive permission caches"; invalidate on role/ACL updates, account disablement, logout/session revocation, or policy rollouts where required.

### 6.2. TTL vs. Immediate Revocation

Suppose roles are cached for **60 seconds** per system policy. If revoked at second 1, stale allow decisions can survive nearly a minute without invalidation. 60 seconds is only a trade-off example, **not a recommended TTL**. High-risk actions may require:

- Fresh permission lookup immediately before business side effects.
- Permission/role version in context checked for staleness.
- Event-driven invalidation on permission updates.
- Short token TTLs with appropriate revocation/introspection mechanisms.
- Centralized PDP access checks with latency budgets and fail-closed fallback.

**Never fail open** when the permissions DB or PDP errors: if permissions cannot be verified for a sensitive operation, deny temporarily and alert operations instead of treating every principal as an admin. Distinguish missing permissions (403) from dependency failures (usually 5xx/503) in observability, rather than hiding outages as random password errors.

### 6.3. JWT Authorities Differ from Real-Time Permissions

If `JwtAuthenticationConverter` reads scopes from a JWT and produces `SCOPE_reports.read`, Spring Security can authorize without querying a role database. However, already-issued tokens carry old scopes until expiration or system revocation. Updating a role in the DB **does not automatically strip scopes from existing JWTs**.

In multi-tenant environments, tokens may include issuer/organization/tenant claims, yet the resource server must still validate **issuer, audience, subject, tenant membership, and object-level authorization** per trust contract. Never trust a client-sent `X-Tenant-Id` header to pick the wrong permission cache namespace.

## 7. External Identity Providers: Distinguish Which Calls Cross the Network

"The IdP is slow" is not a complete diagnosis. Flows have distinct network costs:

| Flow | When does it hit the IdP over the network? | What to monitor |
| --- | --- | --- |
| OIDC Login authorization code | Redirect/consent/callback, token exchange; UserInfo if configured | Browser round trips, token endpoint p95, login success/failure |
| Resource Server JWT | Fetches discovery/JWKS at startup/cache miss/rotation; JWT verification is local | JWKS hit/miss, signature validation CPU, issuer/audience errors |
| Resource Server opaque token | Introspection per token/request depending on implementation/cache | HTTP latency, `active=false`, upstream 401s, 5xx/timeouts |
| OAuth2 Client `client_credentials` | Token endpoint when a fresh access token is needed | Reuse/expiry, token issuance rate, thundering herd |
| LDAP/remote user directory | User/password/group lookups depending on authentication provider | Bind/search latency, pool, paging, TLS |
| External authorization service/PDP | When decisions require external policy evaluation | p95/p99, cache TTL, fail-closed, request fan-out |

### 7.1. JWT Resource Server: No IdP Call on Every Request

With JWTs, a resource server validates **signatures locally** after loading public keys from JWKS. Example `application.yml` (a **JWT-mode** app):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

The URI is a placeholder for a test IdP. Depending on provider and Spring Security version, the decoder fetches metadata and JWKS to verify signatures. **Do not assume** `issuer-uri` validates your API's specific audience; configure an audience validator if the contract requires `aud=reports-api`.

Right optimizations:

1. Ensure decoder/JWKS caching behaves properly and avoid recreating decoders per request.
2. Monitor JWKS request counts and errors during key rotations or key mismatches.
3. Configure HTTP connect/read timeouts and cache refreshes aligned with the security contract.
4. Never accept invalid signatures or skip issuer validation during temporary IdP outages.
5. Test key rotation from `kid=key-A` to `kid=key-B`, plus JWKS unavailability.
6. Never put tokens in metrics or logs; in traces record only flow type and sanitized error categories.

An HTTP JWKS cache cuts remote calls, **not cryptographic verification**. Every JWT must still pass signature and claims validation in the decoder.

### 7.2. Opaque Token Introspection: Network Is Directly in the Request Path

With opaque tokens, Spring Security can call `OAuth2TokenIntrospector` to check whether a token is active and fetch claims. Example configuration (**alternative to JWT mode**):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: resource-api
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

`${...}` is a Spring placeholder reading the secret from environment configuration at real deployment time. Never put client secrets in source code, tickets, or logs. The `opaquetoken` property belongs to Spring Boot 3 opaque-token resource server config; ensure matching versions and dependencies.

On each Bearer HTTP request, if the introspector implementation does not cache, responses wait on **network RTT + IdP processing + TLS/connection pool**. At several thousand requests/second, this can overload the IdP and spike API p99. Design decisions include:

- When tokens can move to signed JWTs verified locally **per IdP contract**, weigh pros/cons of revocation, key rotation, and claims.
- When opaque tokens are required, consider **introspection caching with TTL aligned to expiry and revocation SLAs**; never cache `active=true` longer than permitted.
- Use HTTP connection pooling/timeouts and bounded retries for transient errors (where library/implementation supports it).
- Track cache hit/miss ratios and introspection requests/second per API node.
- **Never flip `active=false` to true** or "let traffic through temporarily" when the IdP is down.

Important: an HTTP 200 from an introspection endpoint can still contain `{"active":false}`. Authentication depends on `active` and valid claims, not HTTP status alone.

### 7.3. OAuth2 Client Token Endpoint: Avoiding Thundering Herds

When a backend uses `client_credentials`, `OAuth2AuthorizedClientManager` and matching services/repositories can reuse unexpired access tokens and fetch new ones only when needed. If many instances see expiration simultaneously and all request new tokens at once, the authorization server faces a **token storm**.

Consider:

- Using authorized-client storage/caching with clear lifecycles, keyed by `registrationId + principal` as appropriate.
- Refreshing/reauthorizing ahead of expiration with clock skew allowance, without synchronizing thousands of instances to call in the same millisecond.
- Bounding concurrency and retries against the token endpoint with backoff + jitter.
- Monitoring issuance rates, 429s, client authentication failures, and latencies.
- Never reusing a user token for a service identity or vice versa just to reduce IdP calls.

Cluster-synchronized caches must avoid single points of failure and never cache tokens across the wrong tenant/user. Client secrets must rotate per policy.

### 7.4. Ways an Identity Provider Can Fail

| Symptom | Possible cause | Diagnosis |
| --- | --- | --- |
| Browser login stalls at callback | Token endpoint, UserInfo, proxy, TLS, or session persistence | Trace each step, redirect URI, and IdP metrics |
| Previous JWTs work, new `kid` returns 401 | Rotation/JWKS cache miss or unpublished key | Check JWKS and algorithms against trusted issuer |
| Opaque token p99 suddenly spikes | Slow introspection service, exhausted connection pool | Test upstream latency, HTTP pool/timeouts/cache |
| Introspection returns 401 | Resource server's introspection client credentials wrong/expired | Check client auth/secret; do not tell users to change passwords |
| Introspection returns `active=false` | Token expired/revoked/unrecognized | Return 401 properly; never "retry until active" |
| Valid JWT yet 403 | Insufficient scopes/roles/audience/authorization policy | Check converter and policy; token refresh won't fix every 403 |
| IdP 5xx or DNS timeout | Dependency outage | Circuit breaker, timeouts; separate dependency faults from bad credentials |
| JWKS returns 200 yet decoder still fails | Key set lacks matching `kid`, wrong algorithm/issuer | Test rotation/metadata/validation |
| Scope mapping breaks after IdP update | Claims contract changed | Contract tests against test/staging IdP |

## 8. Timeouts, Retries, Circuit Breakers, and Failure Modes Need Explicit Policies

### 8.1. Timeouts Aligned to Latency Budgets

An external HTTP request needs **connection timeout, response/read timeout, and an overall deadline** aligned with SLOs. Infinite timeouts risk pinning Servlet threads and connection pools; overly tight timeouts trigger false failures during minor IdP slowdowns.

Depending on implementation, HTTP clients are configured on Spring Security's introspector/decoder or organization-managed connectors; **builder APIs and HTTP client wiring vary by version**, so verify via integration tests and exact version contracts. Never take an illustrative pair of timeout numbers and assume they fit every network.

If an API has a 1-second total budget, you cannot give each dependency 3 retries at a 1-second timeout and still meet a 1-second SLO. Bound total time along the critical path and fail fast appropriately.

### 8.2. Retry Only Recoverable Errors

- **Consider bounded retries for:** connection resets, brief timeouts, upstream 429/503 with backoff/jitter when requests are safe to repeat.
- **Never retry indefinitely:** wrong client secret (401 from token/introspection endpoint), `invalid_grant`, `active=false`, invalid JWT signature, issuer/audience mismatch.
- **Never equate a Resource Server HTTP 401 with an IdP outage.** Record client status and upstream errors under their distinct causes.
- Use **circuit breakers/bulkheads** to protect application pools when providers go down; never turn an open circuit breaker into "accept users without verification".

For sensitive requests, when tokens/permissions cannot be verified, the rule is **fail closed**. Return 503 or an appropriate application error so clients retry later; never serve private data simply because the IdP is temporarily offline.

### 8.3. Caching Is Not a Way to Disable Validation

Caching public signing keys still requires validating JWTs. Caching introspection results requires TTLs and revocation contracts. Caching authorities requires invalidation on updates. Per-tenant role caches must isolate keys. Password caching **must never become permanent proof of login**.

For distributed caches, test behavior across deploys/restarts, TTL drift, eviction, key namespacing, serialization/versioning, race conditions, and fan-out when entries expire together. Cache-miss stampedes often hit at the exact moment an IdP slows down or rotates keys.

## 9. Operational Formulas: Measure Before Changing Any Parameter

### 9.1. Two Common Latency Profiles

**Password login:**

~~~text
login wall time
  ≈ request parsing
  + wait for DB connection
  + load user/authorities
  + password matches CPU/memory
  + session/audit
  + response/queueing
~~~

**Opaque-token API needing DB permissions:**

~~~text
request wall time
  ≈ bearer parsing
  + introspection HTTP latency
  + permission lookup
  + business operation
  + response/queueing
~~~

The `≈` represents a mental model of a **sequential path**, not that summing individually measured steps equals p95/p99. Some steps run concurrently, hit caches, or queue on pools.

### 9.2. When DB Optimization Has Only Small Impact

If a login spends 170 ms in password hashing and 15 ms querying the user, cutting the query from 15 ms to 5 ms saves ~10 ms on **one illustrative sequential path**; it will not fix CPU saturation caused by hashing. Conversely, if a resource server endpoint does no password hashing yet runs 30 permission queries, fixing N+1 eliminates most of the latency.

Lesson: **never tune auth systems from a vague diagnosis like "Spring Security is slow"**; measure where time is actually spent, cut query counts, add indexes, cache with proper TTLs, and preserve hash strength.

### 9.3. Little's Law and Resource Contention

Under steady load, average work in progress is `L ≈ λ × W`, where `λ` is throughput and `W` is time spent in the system. At 100 verifications/second taking 0.2 s each under idealized conditions, ~20 verifications are in flight on average. **This is not a direct formula for thread pool sizing**: real CPU cost, core counts, queueing, and bursty traffic alter behavior.

With memory-hard hashing, concurrent verifications are also bounded by **actual container RAM**. Never tune concurrency from CPU utilization alone until the JVM or kernel OOMs.

## 10. Pure Java 17 Example to Understand Latency Budgets

File `AuthLatencyModel.java` in any directory, runnable with JDK 17+ without Spring. Numbers are **hypothetical model values**, not production benchmarks or SLOs.

~~~java
public class AuthLatencyModel {

    record Budget(int hashMs, int dbMs, int idpMs) {
        int passwordLoginMs() {
            return hashMs + dbMs;
        }

        int remoteAuthorizationMs() {
            return dbMs + idpMs;
        }

        Budget fasterDatabase(int newDbMs) {
            return new Budget(hashMs, newDbMs, idpMs);
        }
    }

    public static void main(String[] args) {
        Budget baseline = new Budget(170, 15, 90);
        Budget tuned = baseline.fasterDatabase(5);

        System.out.println(
            "login-before=" + baseline.passwordLoginMs() + "ms");
        System.out.println(
            "login-after=" + tuned.passwordLoginMs() + "ms");
        System.out.println(
            "remote-before="
                + baseline.remoteAuthorizationMs() + "ms");
        System.out.println(
            "remote-after="
                + tuned.remoteAuthorizationMs() + "ms");
        System.out.println(
            "db-saved="
                + (baseline.passwordLoginMs()
                   - tuned.passwordLoginMs()) + "ms");
    }
}
~~~

Compile/run:

~~~bash
javac AuthLatencyModel.java
java AuthLatencyModel
~~~

**Exact** stdout:

~~~text
login-before=185ms
login-after=175ms
remote-before=105ms
remote-after=95ms
db-saved=10ms
~~~

The code merely illustrates **breaking down a hypothetical latency budget** and the impact of optimizing only the DB step. It does not measure thread scheduling, network latency distributions, p99, cache hit ratios, concurrency, transaction costs, or password-hashing quality. Never use these numbers as timeout or hash-cost configs.

## 11. Instrumentation in Servlet Applications

For useful telemetry, place timers at trusted boundaries: `UserDetailsService`, `PasswordEncoder` calls, authorization repositories/services, introspection HTTP clients, JWKS fetches, and login endpoints. With Micrometer/Spring Boot Actuator, configure timers/histograms compatibly with your version.

Example wrapper service measuring verify latency **without logging passwords/hashes** (class assuming Micrometer dependency in the project):

~~~java
package com.example.demo;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class TimedPasswordVerifier {

    private final PasswordEncoder delegate;
    private final MeterRegistry registry;

    public TimedPasswordVerifier(
            PasswordEncoder delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public boolean matches(CharSequence raw, String encoded) {
        return registry.timer("auth.password.verify")
            .record(() -> delegate.matches(raw, encoded));
    }
}
~~~

This is a **sample wrapper**; Spring Security does not automatically use it just because it is a bean. To measure `DaoAuthenticationProvider`'s path, wire the wrapper appropriately while avoiding duplicate `PasswordEncoder` beans that cause ambiguous injection or circular dependencies. In Boot, Micrometer usually comes with Actuator or matching starters; verify actual libraries and bean registrations before compiling.

**Never attach tags like `user=username`, `passwordHash=...`, or `token=...`.** Avoid putting raw JWT claims into metric labels. Emit only aggregate measurements, route templates, allowlisted IdP registrations, and sanitized outcome/error categories. Measure **failures too**, since wrong passwords or invalid tokens can generate significant CPU/network load.

### 11.1. Which Question Does Each Metric Answer?

- If password verify p95 rises alongside CPU throttling, check container CPU quotas, hash algorithm, work factor, and login spikes.
- If DB lookup p95 rises while SQL execution stays fast, check Hikari acquisition, locks, pool exhaustion, and proxy/network.
- If authorization query counts grow with response DTO count, check for N+1/per-row ACL checks.
- If a JWT API slows down alongside the IdP yet JWKS has zero cache misses, the bottleneck may **not** be the IdP: check business DBs/external services first.
- If opaque-token API p99 rises with introspection p99, inspect HTTP connection pools, retries, and endpoint health.
- If already-authenticated users suddenly trigger `PasswordEncoder.matches()` on every GET, review Basic authentication, stateless/session config, and caching rather than lowering hash costs.
- If 401s spike after an IdP rotation, inspect issuer, audience, JWKS `kid`, clock skew, and validation config; never "fix" it by skipping signature verification.

## 12. Performance and Failure Testing Along Three Axes

### 12.1. Hashing Benchmarks Under CPU and Concurrency

Test in an environment as close to production as possible, with:

1. Test accounts actually encoded with the target algorithm/cost.
2. Separate measurements for `encode` and `matches`.
3. Both successful and failed login workloads; never let tests trigger credential stuffing against a public IdP.
4. Controlled concurrency ramps measuring CPU, memory, active threads, pending queues, GC, and p95/p99 latency.
5. Burst/rate-limiter tests, lockout policies, and recovery once load drops.
6. Password migration tests: old prefix/algorithm/cost still matches, and rehash runs safely on successful login.
7. Unicode, long passwords, mixed hash algorithms, and no information leaks via errors/timing.

Never run large synthetic brute-force tests against unauthorized external infrastructure; load tests must stay within approved environments and scopes.

### 12.2. Permission DBs at Scale and Multi-Tenancy

Create fixtures with users holding many roles, groups, and resource ACLs; verify:

- SQL query count per login/request; ensure it does not scale with result-set size when set-based queries apply.
- Query plans and index usage on realistic data distributions.
- When changing roles or disabling accounts, caches invalidate and session/token policies take effect properly.
- When tenants A and B share usernames/resource IDs, cache keys/policies never leak data across tenants.
- When the DB pool exhausts connections or locks stall, auth flows fail safely rather than failing open.
- For users with 0 authorities, the app never grants elevated default permissions.

### 12.3. Testing IdPs in Isolated Environments

CI/unit integration tests can use JWKS HTTP stubs, test token endpoints, or local introspection stubs; to verify vendor contracts, supplement with a **staging IdP or containerized IdP**. Scenarios:

| Scenario | Expected |
| --- | --- |
| JWT with valid issuer/audience/scope | Resource Server allows when business policy passes |
| JWT with wrong signature/expired/other issuer | Rejected; no data access |
| JWKS rotation/cached old key | Refreshes cleanly without accepting untrusted keys |
| Introspection `active=true` | Authentication holds right principal/authorities |
| Introspection `active=false` | Token rejected |
| Introspection 401 due to bad client credentials | Reports dependency/config error safely; rejects token |
| IdP timeout/5xx | Bounded retries, circuit breaker, never fail open |
| Token issued with narrower scopes | 403/authorization denial per policy |
| Multiple nodes renewing `client_credentials` concurrently | No token storm or rate-limit breach |
| Role revocation/change in IdP | System honors TTL/cache and permission contracts |

MockMvc tests with `jwt()` or `opaqueToken()` only verify authorization **with pre-built authentication**. To test the real path, send Bearer headers through the Spring Security filter chain with a real `JwtDecoder` or `OAuth2TokenIntrospector` and an HTTP stub, followed by E2E IdP tests. Never claim "we benchmarked the IdP" because a Mockito mock returned in 1 ms.

### 12.4. Measuring Properly Under Realistic Load

Run tests in stages:

~~~text
Warm up JVM, DB pool, JWKS cache
    ↓
Steady state: target throughput
    ↓
Burst/spike: login or opaque-token peak
    ↓
Failure injection: IdP timeout, DB pool pressure, rotation
    ↓
Recovery: reduce load and observe service recovery
    ↓
Re-verify no wrong permissions were granted / credentials logged
~~~

Record JVM/CPU quotas, memory limits, library/JDK versions, DB engine, replica counts, and network topology. A performance result without environment details or latency distributions is hard to compare after deployment.

## 13. Common Operational Mistakes

| Symptom | Cause to inspect | Fix |
| --- | --- | --- |
| Slow logins, high CPU | Password hashing cost/concurrency, CPU quota, or credential stuffing | Benchmark, capacity plan, rate limit; never weaken cost blindly |
| Slow logins, low CPU, rising DB pending | Exhausted JDBC pool, query locks/long transactions | Measure acquisition, indexes, transactions, pool sizing |
| Role queries jump 100x on list views | N+1 in `PermissionEvaluator` or ACL service | Set-based fetch/check; cap fan-out |
| Demoted admin still performs actions | Stale session authorities/JWT/cache | Role versioning, revocation/invalidation, step-up/fresh checks |
| Tenant A user sees Tenant B permissions | Cache key/query lacks tenant binding | Bind verified tenant; write cross-tenant tests |
| JWT API calls IdP constantly | Decoder/JWKS cache recreated or key/rotation mismatch | Preserve decoder lifecycle; monitor JWKS requests |
| Opaque API hits IdP every request with bad p99 | Introspection HTTP RTT/cache misses | Pooling/timeouts, controlled TTL cache, revisit trust design |
| API accepts any token when IdP errors | Dangerous fail-open fallback | Fail closed; return 503 when auth cannot be verified |
| Token endpoint returns 429 after deploy | Multiple instances refreshing simultaneously | Token reuse, bounded concurrency, jitter/backoff |
| Lost client secret reported as wrong user passwords | Conflating upstream client auth failures with end-user auth | Separate error types, internal alerts, safe responses |
| Fast authority cache serving wrong data | Missing invalidation or risk-unaligned TTL | Define revocation SLA and fresh checks |
| "Optimizing" `matches` with plain SHA-256 | Mistaking intentional slow hash for a bug | Keep standard password KDF; curb online abuse/query cost |
| Metrics explode cardinality | Putting username/JWT/subject in tags | Bounded labels; correlation IDs in secure logs |
| Good local p95, bad prod p99 | Container throttling, connection queueing, network tails | Production-like load tests and distributed tracing |
| Overly huge timeouts | Servlet threads pinned, cascading failures | End-to-end deadlines, bounded retries/bulkheads |
| Every request fails after key rotation | Bad JWKS cache TTL/refresh, issuer/kid/alg mismatch | Contract tests with IdP; test key rollover |

### Pre-Production Checklist

- [ ] Measure every step on the auth path: `UserDetailsService`, hash verify, authority decisions, JWKS/introspection, pool waits.
- [ ] Hash passwords with a standard KDF and unique salts; base work factors on threat model and target hardware benchmarks.
- [ ] Enforce rate limiting, admission control, concurrency limits, and credential-stuffing/DoS defenses.
- [ ] Use `DelegatingPasswordEncoder`/migration plans properly without breaking legacy password verification.
- [ ] Rehash only after successful login with safe conditional updates.
- [ ] Index user/authority queries properly; measure N+1s, DB time, and connection acquisition.
- [ ] User/tenant/resource permission caches use proper keys and clear TTL/invalidation/revocation policies.
- [ ] JWT validation always verifies signature/issuer/expiry and contract audience; JWKS is cached without skipping crypto validation.
- [ ] Opaque introspection has proper latency/timeout/cache plans and never treats `active=false` as success.
- [ ] OAuth2 Clients avoid token storms via reuse and bounded retries.
- [ ] If IdP/PDP/DB is unavailable, authenticated/authorized operations **fail closed**.
- [ ] Continuously observe p50/p95/p99 metrics, query counts, error categories, connection pools, and CPU/memory.
- [ ] Never log passwords/hashes/raw tokens/session IDs/secrets/PII into traces or metric tags.
- [ ] Test concurrency, role revocation, key rotation, expired JWTs, introspection outages, stale caches, and multi-tenant boundaries.
- [ ] Maintain a runbook separating authentication failures, authorization denials, network/provider outages, and overload.
- [ ] Re-verify performance tuning after changing Spring Security versions, JVMs, container resources, DB indexes, or provider contracts.

**Conclusion:** Operating Spring Security efficiently is not about "making password hashes fast" or "caching every permission". You must keep **strong password hashing**, eliminate **unnecessary permission queries and N+1s**, and manage **IdP latency, caching, timeouts, key rotation, and failure modes** along trust boundaries. Measure the real path with telemetry and load tests, ensuring every optimization preserves authentication validation, authorization, and permission revocation.
