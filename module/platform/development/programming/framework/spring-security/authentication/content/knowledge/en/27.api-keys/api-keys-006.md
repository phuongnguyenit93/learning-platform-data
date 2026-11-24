# Rotation, Expiration, and Revocation of API Keys in Spring Security

> **Scope:** How to manage the lifecycle of **opaque API keys** issued by an application to clients calling an API: creation, rotation, expiration, revocation, and immediate verification in Spring Security. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x Servlet. An API key is a *bearer secret*: anyone possessing the secret string can send requests with its permissions. TLS, least privilege, rate limiting, and effective revocation are essential requirements.

## 1. Learning outcomes

After this lesson, you will be able to:

1. Distinguish issuance, activation, rotation, expiration, revocation, and metadata purging for API keys.
2. Separate the **public ID** from the **confidential secret**, and know how to store digests/HMACs, owners, scopes, expiration, and status.
3. Perform rotation with a **bounded overlap** so clients migrate from old key K1 to new key K2, or revoke immediately upon suspected exposure.
4. Validate `activatedAt`, `expiresAt`, `revokedAt`, owner/audience, and permissions on **every request**, even when cleanup jobs have not run.
5. Map a verified identity into `Authentication`/`GrantedAuthority` in Spring Security and classify 401/403/429/5xx errors.
6. Properly test boundary timestamps, multi-instance caches/replicas, concurrent operations, lost secrets, and incident response steps.

This lesson focuses on **application API keys**. They differ from OAuth2 access tokens, JWTs, JWT signing keys, user passwords, and TLS private keys. Never blindly apply an API key revocation mechanism to self-contained tokens without evaluating the design.

## 2. States that must be kept distinct

| State/action | Meaning | Behavior |
| --- | --- | --- |
| `ISSUED` / `PENDING` | ID + secret generated, not yet accepted | Reject if `activatedAt` has not been reached |
| `ACTIVE` | Key is usable within its granted scope | Must still verify secret, expiry, owner, and scopes |
| `ROTATING` | Being replaced with a new key | Two keys may temporarily be active |
| `EXPIRED` | `expiresAt` has been reached | Disallow use even if the digest matches |
| `REVOKED` | Proactively disabled before expiry | Block all requests after revocation within SLA |
| `PURGED` | Old metadata deleted per retention | Not a substitute for revocation/auditing |

~~~text
         ISSUE -> PENDING -> ACTIVE ------- expiry -------> EXPIRED
                                 |
                                 +-- rotate -> NEW KEY -> ACTIVE
                                 |               |
                                 +-- grace K1,K2 |
                                 |               |
                                 +-- cutoff ----> REVOKE K1
                                 |
                                 +-- compromise -> REVOKE IMMEDIATELY
~~~

**Rotation does not mean overwriting the secret on the same record.** Issue K2 with its own ID, digest, and timestamps; K1 retains its status/expiry during the overlap window. If K1's secret is overwritten, unmigrated clients fail abruptly, you cannot tell which clients still use K1, and auditing suffers. Revocation should be one-way; if access must be restored, issue a **new key**, never resurrect an old raw secret.

`EXPIRED` can be a **computed state** derived from `expiresAt`; there is no need to rely on a cron job setting a status column to EXPIRED. Cron/scheduled cleanup only maintains operational data, never acting as the security enforcement gate.

## 3. API key format and storage model

An illustrative format:

~~~text
ak_prod_v2_k123456.<32_byte_random_secret_base64url>
|----------------| |--------------------------------|
     key_id                  secret portion
~~~

This is a **notation**, not a real key. `key_id` may be displayed for management; `secret` must never be stored in plaintext in databases or logs. An environment prefix like `prod` aids recognition but does not by itself prove permission for production: server-side metadata must still be checked.

| Metadata | Purpose |
| --- | --- |
| `key_id` (unique/indexed) | Record lookup, auditing, revoking a specific key |
| `secret_digest` / `secret_hmac` | Secret comparison without storing the raw key |
| `owner_id`, `service_id`, `tenant_id` | Identity and accountability of the calling application |
| `environment` / `audience` | Target service and accepted environment |
| `scopes` / `permissions` | Permissions such as `orders:read`, `orders:write` |
| `issued_at` / `activated_at` | Issuance and activation timestamps |
| `expires_at` | Hard expiration, independent of cleanup jobs |
| `revoked_at`, `revoked_by`, `reason` | Revocation trail |
| `rotated_from` / `rotation_group` | K1 -> K2 lineage and cutover schedule |
| `last_used_at` / `version` | Rollout tracking and preventing overwrites from stale snapshots |

**Key generation:** `SecureRandom` generates at least 32 bytes (256 bits) as the secret, encoded in URL-safe Base64 or hex. Never use timestamps, usernames, `Random`, counters, or a single UUID in place of a 256-bit secret. The ID can use a UUID or unique random ID; the secret must be generated independently.

**Hashing:** For a truly random 256-bit secret, a SHA-256 digest fits lookup and is practically impossible to brute-force. HMAC-SHA-256 with a **pepper in a secret manager separate from the DB** can strengthen defense if the DB leaks; this requires versioning and a pepper rotation plan. Never use plain SHA-256 for low-entropy **user passwords**: passwords require a KDF like Argon2id/bcrypt/scrypt. Fixed-length digests can be compared with `MessageDigest.isEqual`.

**Display:** The raw secret is delivered **once** at creation/rotation over a secure channel. Listing APIs return only key ID, label, owner, scopes, expiry, and status. If a secret is forgotten, rotate it; never design a `GET /keys/{id}` endpoint to read back raw secrets.

## 4. Acceptance conditions on every request

~~~text
Client --HTTPS + X-API-Key--> Spring Security / API gateway
         |
         v
Parse key ID + secret (format, length, charset)
         |
         v
Lookup key ID in controlled store
         |
         v
Check secret digest/HMAC
         |
         v
activatedAt <= now < expiresAt and revokedAt == null
         |
         v
Owner still active + right tenant/environment/audience
         |
         v
Create Authentication with server-side scopes
         |
         v
hasAuthority(...) -> allow or 403
~~~

A complete logical check:

~~~text
accepted = format_ok AND id_exists AND secret_matches
           AND activated_at <= now AND now < expires_at
           AND revoked_at IS NULL AND owner_active
           AND environment_matches AND audience_matches
           AND requested_operation_in_scopes
~~~

**At the exact `expiresAt` instant, the key is expired:** `now.isBefore(expiresAt)` must be true to be accepted. Use server UTC time as an `Instant`; never let clients supply a custom time, and never rely on `LocalDate` which drops time-of-day. A matching digest with a disabled owner, missing scope, or revoked key still must **not** grant access.

If the key store is unavailable, authentication cannot establish identity. The system must **fail closed** and report an infrastructure error; never serve stale `valid=true` results from an unbounded cache to allow access.

## 5. Rotation with a bounded overlap

Suppose the `billing-worker` integration currently uses K1. Scheduled rotation plan:

1. **Inventory:** identify owner, workload, environment, scopes, infrequently running jobs, K1 expiration, and concurrent key limits.
2. **Approval:** verify the actor is authorized to rotate; K2 must not silently inherit broader scopes than K1.
3. **Issue K2:** new ID/secret, new digest, new `expiresAt`, and `rotatedFrom=K1`. Use transactions, versioning, and idempotency on the admin API.
4. **Distribute K2:** deliver via secret manager/secure channel; clients install K2 and roll out gradually.
5. **Verify:** call the least-privileged permitted endpoint using K2, confirm 2xx or expected business code; monitor by key ID without logging the raw secret.
6. **Overlap:** K1 and K2 are temporarily valid together so client instances can switch over; enforce a clear cutoff.
7. **Cutover:** revoke K1, propagate invalidation/version updates to caches, and prove K1 is rejected across all regions/gateways.
8. **Close the loop:** update audits, inventory, and alert if K1 usage continues.

| Stage | K1 | K2 | What to monitor |
| --- | --- | --- | --- |
| Before rotation | ACTIVE | Not issued | K1 expiry and last used |
| Right after issuing K2 | ACTIVE | PENDING/ACTIVE | K2 safely received by client |
| Transitioning | ACTIVE until cutoff | ACTIVE | K1 traffic falling, K2 rising |
| After cutoff | REVOKED/EXPIRED | ACTIVE | K1 consistently rejected |
| Later | Never reactivated | ACTIVE until its own expiry | Alerts before K2 expiry |

Bounding can use `old_effective_expiry = min(old_original_expiry, rotation_cutoff)`. If the cutoff is enforced by a job setting `revokedAt`, handle failed/late jobs; even better, evaluate the cutoff timestamp directly in the authentication path. Never extend overlap indefinitely because one client forgot to update.

**Compromise/leak:** When K1 is suspected compromised, **revoke K1 immediately**, giving zero grace window to attackers. Issue K2 to the legitimate client over a fresh channel and investigate K1 usage trails. This is an emergency procedure distinct from scheduled rotation.

## 6. Expiration, activation, and real time

Distinguish `issuedAt`, `activatedAt`, `expiresAt`, `rotationCutoff`, `idleTimeout` if present, and audit metadata retention. Hard expiration must not be extended automatically by continuous API requests unless the system has a **newly approved renewal policy**; the safest, most auditable approach is issuing a new key.

Common mistakes:

- Comparing `LocalDate` instead of `Instant`, leaving the key valid into the next day.
- Using `now.isAfter(expiresAt)` to reject, allowing usage at the exact expiry instant. Use `now.isBefore(expiresAt)` as the acceptance condition.
- Relying solely on a cron job to delete expired rows; if cron fails, keys stay valid if auth does not check `expiresAt`.
- Letting clients modify `expiresAt` in requests or trusting client-supplied timestamps.
- Caching Authentication/metadata without bounds and ignoring expiration timestamps.
- Ignoring clock skew and replica lag in distributed architectures.

Send alerts at T-14/T-7/T-1 days for long TTLs; remind owners that keys do not auto-renew. Server clocks must be synchronized, timestamps stored in UTC, and tests written at `expiresAt.minusNanos(1)`, `expiresAt`, and `expiresAt.plusSeconds(1)`.

## 7. Premature revocation

**Revocation** is a proactive server-side action taken when a client is lost, an employee/partner is offboarded, a leak is suspected, abuse occurs, or the key is no longer needed. If `revokedAt != null`, the key must be rejected **even when cryptography and expiry are still valid**.

Revocation should satisfy:

- **Idempotent:** calling revoke repeatedly keeps the state REVOKED without reactivating the key.
- **Terminal:** never allow re-enabling the same raw secret; issue a new ID+secret to restore access.
- **Atomic:** transactions/compare-and-set/versioning prevent rotation jobs from overwriting the revoked state.
- **Auditable:** actor, reason, key ID, owner, timestamp, and correlation ID; logs contain no raw secret.
- **Propagated:** caches, gateways, and regions receive the revocation within the committed SLA.
- **Scoped:** able to revoke a single key or all keys belonging to an owner/tenant after authorization checks.

Illustrative one-way SQL update, parameter syntax depends on the repository:

~~~sql
UPDATE api_keys
SET revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP),
    revoked_by = COALESCE(revoked_by, :operator)
WHERE key_id = :key_id AND revoked_at IS NULL;
~~~

Parameters must come from an authenticated administrative context with ownership checks; never trust a client-declared actor. If the system stores `version`, increment `version` in the same transaction to prevent lost updates.

**Deleting a key from the client ≠ revoking on the server.** If someone copied the secret before deleting the file, the key remains usable until the server marks it revoked or expired. Scrubbing secrets from Git history, pods, tickets, CI variables, and rotating deployments does not replace revoking at the authoritative store.

## 8. Standalone Java 17 example demonstrating lifecycle

The program below generates 256-bit keys, stores SHA-256 digests (because these are high-entropy random secrets), compares digests with `MessageDigest.isEqual`, and uses `Instant` for deterministic testing without sleeping. Uses only the JDK; **never** prints real keys. This is an in-process learning model without a DB, permissions, key-ID collision handling, or distributed concurrency checks.

File `ApiKeyLifecycleDemo.java`:

~~~java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class ApiKeyLifecycleDemo {
    private static final SecureRandom RANDOM = new SecureRandom();

    record Stored(String owner, byte[] digest,
                  Instant expiresAt, Instant revokedAt) {}

    static final class Registry {
        private final Map<String, Stored> keys = new ConcurrentHashMap<>();

        String issue(String owner, Instant issuedAt, Duration ttl) {
            if (ttl.isZero() || ttl.isNegative()) {
                throw new IllegalArgumentException("TTL must be positive");
            }
            byte[] secret = new byte[32];
            RANDOM.nextBytes(secret);
            try {
                String id = "ak_demo_" +
                        UUID.randomUUID().toString().replace("-", "");
                keys.put(id, new Stored(owner, sha256(secret),
                        issuedAt.plus(ttl), null));
                return id + "." + Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(secret);
            } finally {
                Arrays.fill(secret, (byte) 0);
            }
        }

        boolean accepts(String presentedKey, Instant now) {
            if (presentedKey == null) {
                return false;
            }
            int dot = presentedKey.indexOf('.');
            if (dot < 0 || dot != presentedKey.lastIndexOf('.')) {
                return false;
            }
            Stored stored = keys.get(presentedKey.substring(0, dot));
            if (stored == null || stored.revokedAt() != null
                    || !now.isBefore(stored.expiresAt())) {
                return false;
            }

            byte[] supplied;
            try {
                supplied = Base64.getUrlDecoder()
                        .decode(presentedKey.substring(dot + 1));
            } catch (IllegalArgumentException badEncoding) {
                return false;
            }
            try {
                return supplied.length == 32
                        && MessageDigest.isEqual(
                                stored.digest(), sha256(supplied));
            } finally {
                Arrays.fill(supplied, (byte) 0);
            }
        }

        void revoke(String keyId, Instant at) {
            keys.computeIfPresent(keyId, (id, old) ->
                    new Stored(old.owner(), old.digest(),
                            old.expiresAt(),
                            old.revokedAt() == null ? at : old.revokedAt()));
        }

        private static byte[] sha256(byte[] bytes) {
            try {
                return MessageDigest.getInstance("SHA-256").digest(bytes);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();
        Instant t0 = Instant.parse("2026-11-06T00:00:00Z");

        String k1 = registry.issue("billing-worker", t0,
                Duration.ofDays(7));
        System.out.println("old before rotation: " +
                registry.accepts(k1, t0.plusSeconds(1)));

        Instant rotation = t0.plus(Duration.ofDays(1));
        String k2 = registry.issue("billing-worker", rotation,
                Duration.ofDays(7));
        Instant overlap = rotation.plusSeconds(10);
        System.out.println("old during overlap: " +
                registry.accepts(k1, overlap));
        System.out.println("new during overlap: " +
                registry.accepts(k2, overlap));

        String oldId = k1.substring(0, k1.indexOf('.'));
        registry.revoke(oldId, rotation.plusSeconds(20));
        Instant after = rotation.plusSeconds(21);
        System.out.println("old after revoke: " +
                registry.accepts(k1, after));
        System.out.println("new after revoke: " +
                registry.accepts(k2, after));
        System.out.println("new at expiry: " +
                registry.accepts(k2, rotation.plus(Duration.ofDays(7))));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ApiKeyLifecycleDemo.java
java ApiKeyLifecycleDemo
~~~

**Exact expected stdout**, regardless of random secrets:

~~~text
old before rotation: true
old during overlap: true
new during overlap: true
old after revoke: false
new after revoke: true
new at expiry: false
~~~

First K1 is valid, after generating K2 both are valid, and after `revoke` only K2 remains valid. At K2's exact expiry timestamp, `now.isBefore(expiresAt)` evaluates to false. K1's state cannot be re-enabled.

**Limitations:** Registry uses `ConcurrentHashMap`, so data is lost on process restart, does not enforce scopes/owner/tenant, lacks multi-region transactions, and has no auditing or anti-abuse. `record Stored` holds an internal `byte[]` for simplicity; production needs defensive copies and memory protection. For real products, use a durable DB, secret manager, and appropriate HMAC/digest versioning. Never let clients dictate `now`; the example passes `Instant` for testing, whereas server code needs a trusted `Clock`.

## 9. Passing a valid key into Spring Security

In the Servlet stack, a `OncePerRequestFilter` can read the header, invoke an `ApiKeyVerifier` to obtain server-side identity, and place `Authentication` into `SecurityContext`. Build authorities from **server metadata**, never trusting user-supplied scopes.

Contract (must provide a real repository/DB implementation):

~~~java
package example.security;

import java.util.Optional;
import java.util.Set;

public interface ApiKeyVerifier {

    // empty only when credential is invalid; store errors must raise a system error.
    Optional<KeyIdentity> verify(String rawKey);

    record KeyIdentity(String serviceId, Set<String> authorities) {}
}
~~~

Filter `ApiKeyFilter.java`:

~~~java
package example.security;

import java.io.IOException;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyFilter extends OncePerRequestFilter {
    private final ApiKeyVerifier verifier;

    public ApiKeyFilter(ApiKeyVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {

        List<String> headers = Collections.list(request.getHeaders("X-API-Key"));
        if (headers.isEmpty()) {
            chain.doFilter(request, response);
            return;
        }
        if (headers.size() != 1 || headers.get(0).isBlank()
                || headers.get(0).contains(",")) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        Optional<ApiKeyVerifier.KeyIdentity> identity =
                verifier.verify(headers.get(0));
        if (identity.isEmpty()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        var authorities = identity.get().authorities().stream()
                .map(SimpleGrantedAuthority::new).toList();
        Authentication auth = new UsernamePasswordAuthenticationToken(
                identity.get().serviceId(), null, authorities);
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Requirements omitted from the sample filter must reside inside `verifier.verify`: format/max-length validation, ID lookup, digest/HMAC check, active, expiry, revoked, owner/tenant/environment/audience, and scopes. The filter does not distinguish why a key failed in public responses, returning 401; a database outage must never be turned into `Optional.empty()`.

**Note:** The filter is instantiated via `new ApiKeyFilter(verifier)` when attached to `HttpSecurity`; annotating the filter with `@Component` or declaring another filter bean may cause Spring Boot to register it again in the servlet container, running it twice or out of order. If a bean must be used, disable container auto-registration.

`ApiSecurityConfig.java`, illustrative Spring Security 6 Servlet configuration:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http,
            ApiKeyVerifier verifier) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(ex -> ex
                        .authenticationEntryPoint((req, res, e) ->
                                res.sendError(401)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/status").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                        .hasAuthority("orders:read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                        .hasAuthority("orders:write")
                        .anyRequest().authenticated())
                .addFilterBefore(new ApiKeyFilter(verifier),
                        UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}
~~~

**This is a Spring configuration snippet, not standalone-compilable with `javac`.** It needs a Spring Boot application, real repository/verifier, controllers, and tests. `csrf.disable` makes sense only for stateless APIs using header API keys without browser cookies as ambient authentication; never disable CSRF across an entire site with forms/OIDC. If a web UI exists, define separate SecurityFilterChains with valid matchers and order.

In WebFlux, use `SecurityWebFilterChain` and `WebFilter`/reactive verifiers, never Servlet's `OncePerRequestFilter`. If the verifier relies on a blocking database client, isolate I/O appropriately; never block the event loop. Custom opaque keys are not automatically OAuth2 Bearer/JWT tokens.

## 10. Handling errors for clients and operations

| Scenario | Typical response | Notes |
| --- | --- | --- |
| Missing key on protected endpoint | 401 Unauthorized | Do not create an authenticated principal |
| Wrong ID, secret, malformed, inactive | 401 Unauthorized | Never confirm which key IDs exist |
| Expired/revoked | 401 Unauthorized | Generic public response, do not leak metadata |
| Valid key lacking `orders:write` | 403 Forbidden | Authorization failure, not wrong key |
| Exceeded quota/rate limit | 429 Too Many Requests | May include `Retry-After` per policy |
| Key store unavailable/timeout | 503 or appropriate 5xx | Fail closed, never disguise as 401 |
| Owner/service offboarded | Reject per auth policy | Revoke all associated keys |
| Staging key sent to prod | 401 | Even if format is valid, wrong audience/environment |

Never return raw keys, digests, exact `revokedAt`, or `expiresAt` to unauthenticated callers. Properly authorized admin APIs may display appropriate metadata. A custom filter placed before Spring's `ExceptionTranslationFilter` must handle its error boundary explicitly, without assuming downstream converters will catch every exception.

## 11. Multiple instances, caching, and consistency

Writing a revocation successfully to the database **does not guarantee** all API instances immediately reject the key. For example, instance A caches `valid(K1)=true` for 10 minutes while B already sees `revokedAt`; requests hitting A may still succeed. Latency between source-of-truth, replicas, gateways, and caches **is part of the revocation SLA**.

| Model | Advantage | Risks to address |
| --- | --- | --- |
| Read authoritative store per request | Fast revocation effect, easy to reason about | DB latency/load and outages |
| Short-TTL metadata cache | Reduces load | Max staleness roughly TTL + replica lag |
| Pub/sub invalidation + version | Pushes updates quickly | Missed events, out-of-order delivery, offline consumers |
| Centralized gateway/introspection | Single enforcement point | HA, preventing gateway bypass |
| Short-TTL keys | Narrows exposure window | Does not replace emergency revocation before expiry |

If revocation is required within seconds, a 10-minute cache TTL fails the requirement. Use versions/sequences, acknowledged invalidation, or read-through; measure the time until **every region** truly rejects the key.

Dangerous race condition:

~~~text
T1: read K1=ACTIVE before rotation
T2: leak detected -> REVOKE K1, commit
T1: writes stale snapshot K1=ACTIVE  <-- BUG, key revives
~~~

Fix with transactions or optimistic locking and one-way state transitions:

~~~sql
UPDATE api_keys
SET revoked_at = :now, version = version + 1
WHERE key_id = :id AND revoked_at IS NULL AND version = :expected_version;
~~~

If 0 rows update, read the latest state and decide rather than forcing ACTIVE. Rotation inserts K2 and updates K1's cutoff conditionally. Cache invalidation should carry versions so stale events never revert caches back to active.

Define policy for requests that started before the revoke transaction committed. A valid lookup prior to commit does not necessarily terminate an in-flight request immediately; if long-running jobs/streams must also be cut off, re-check authorization or close sessions/connections at appropriate boundaries.

## 12. Client rollout and updating secrets

Even after the backend accepts K2, callers may still send K1 if:

- Kubernetes pods or services load secrets at startup and have not restarted.
- CI/CD variables, Vault, cloud secret managers, or External Secrets update slowly.
- Month-end batches, infrequent cron jobs, standby environments, or ops scripts still hold the old key.
- SDK singletons/connection pools cache credential headers for hours.
- Staging/prod services mix up secrets or proxies fail to forward headers properly.

During overlap, track K1/K2 usage **by key ID** in audits, never logging raw secrets. At cutoff, verify all expected jobs switched to K2; then revoke K1 and monitor any remaining K1 requests. If a rare job needs extra time, handle it in an approved change plan before cutoff rather than opening infinite grace windows.

## 13. Lifecycle management API

The following endpoints are **application-designed**; Spring Security does not create them automatically:

| Endpoint | Role | Requirements |
| --- | --- | --- |
| `POST /admin/api-keys` | Create key, return secret once | Admin/owner authentication and scope authorization |
| `GET /admin/api-keys` | List metadata, no raw keys | Management permission and auditing |
| `POST /admin/api-keys/{id}/rotate` | Issue K2, link K1 | Idempotency, no privilege escalation |
| `POST /admin/api-keys/{id}/revoke` | Revoke prematurely | Atomic, idempotent, audited |
| `POST /admin/owners/{id}/revoke-all` | Offboard owner and keys | High privilege, blast-radius limits |

Management APIs should use OIDC with MFA/RBAC, mTLS, or strong service identities, separate from regular API keys. Never allow an operational key to mint higher-privileged keys for itself. Accept owners and scopes only after server-side permission checks.

**Retries/idempotency:** If K2 creation commits yet the response drops, blind retries may mint K3. Use idempotency keys/secure key-delivery workflows and policies for partially issued keys. Never store raw secrets long-term just to replay responses: if the raw key is lost, revoke the orphaned record and reissue with auditing.

## 14. Auditing, alerting, and incident response

Record issuance, rotation, revocation, expiration, reuse of revoked keys, actor, reason, key ID, owner, and correlation ID. Logs must minimize sensitive data, enforce access control, prevent tampering, and follow clear retention rules.

~~~text
event=key_rotated at=2026-11-06T09:00:00Z
owner=billing-worker old_id=ak_prod_****2f new_id=ak_prod_****83
event=key_revoked at=2026-11-06T09:15:00Z
owner=billing-worker id=ak_prod_****2f reason=cutover
~~~

Masked IDs are for illustration only; they contain no secrets. Never include raw headers, secrets, full digests, tokens, or sensitive usernames in logs/tracing/metrics or URLs. Metric labels should use bounded sets such as `result=valid|invalid|expired|revoked|infra_error` and `environment`; avoid key IDs as high-cardinality labels.

Observe: keys nearing expiration, K1 usage after cutoff, p95/p99 auth latency, 401/403 per client, store 5xx, invalidation lag, regions with inconsistent auth outcomes, and clock drift. Upon detecting a key leak, the priority order is **revoke, verify multi-region enforcement, securely issue a replacement, update clients, audit/assess impact, and fix the leak source**.

## 15. Testing

**Unit tests with `Clock.fixed` or server-supplied `Instant`:**

1. Generating K1/K2 yields distinct keys; store holds no raw secret; secrets have sufficient entropy.
2. Off-by-one-char secret, non-existent key ID, oversized/malformed inputs are all rejected.
3. `now=expiresAt.minusNanos(1)` is valid; `now=expiresAt` and later are invalid.
4. Before `activatedAt` is rejected; revoked keys are rejected even before expiry.
5. K1/K2 accepted properly during overlap, K1 blocked after cutoff, valid K2 continues working.
6. Revoking twice does not revive the key; concurrent rotate and revoke never lose updates.
7. Disabled owner, cross-environment, wrong audience, and missing scopes are blocked.
8. Store timeouts do not let requests pass and raise infrastructure errors.
9. Missed/delayed cache invalidation events still meet the revocation SLA.
10. Multi-instance/region requests produce consistent decisions after revocation.

**Spring Security integration tests via `MockMvc`:**

| Request | Security outcome |
| --- | --- |
| `GET /api/orders/1` without header | 401 |
| Valid key with `orders:read`, GET request | Authentication succeeds, accurate principal |
| Key with only `orders:read`, POST requiring `orders:write` | 403 |
| Expired, revoked, or wrong-secret key | 401, no session created |
| Duplicate `X-API-Key` headers | 401 |
| Key store failure | 5xx/503 per error policy, never 200 |
| K1 after cutoff / valid K2 | K1: 401; K2: authenticated |
| Quota exceeded | 429 via rate limiter |

Test security statuses separately from business statuses (an authorized controller can still return 404). For WebFlux, use `WebTestClient` instead of `MockMvc`. In staging, perform live rotations across 2 client versions, testing un-restarted clients, monthly jobs, replica lag, clock skew, and measuring revocation latency to every instance.

## 16. Common mistakes

| Anti-pattern | Risk | Fix |
| --- | --- | --- |
| Overwriting secret on the same key ID during rotation | Clients break mid-cutover, lost audit lineage | Separate ID + record per key version |
| Allowing infinite overlap | K1 remains usable long after K2 exists | Bounded cutoff and monitoring |
| Only running a cron job to delete expired keys | Cron failure leaves keys valid | Check expiry on every request |
| Waiting for grace window to end after a leak | Attacker continues using the key | Emergency revocation |
| Storing raw keys in DB/logs | Database/log leak becomes credential leak | Store digest/HMAC and display once |
| Caching `valid=true` too long | Revocation exists only on paper | Invalidation or SLA-compliant TTL |
| Allowing writes setting ACTIVE after revoke | Old keys revive | Terminal state, transactions/versioning |
| Skipping owner/scope checks | Privilege escalation | Authorities from server metadata |
| Mapping all exceptions to 401 | Masks DB outages | 5xx/503 and fail closed |
| Putting keys in URL query | Exposed in logs and browser history | HTTPS headers, redaction |
| Reusing prod keys in staging | Expands secret blast radius | Environment-isolated keys |

## 17. Pre-production checklist

- [ ] Random secret at least 256 bits; public ID separated; digest/HMAC stored with version management.
- [ ] Keys have owner, scopes, environment, activated/expired/revoked timestamps, rotation lineage, and audits.
- [ ] Raw key delivered once over a secure channel; zero plaintext in DB, Git, logs, URLs, or CI/CD.
- [ ] Auth checks UTC time and status per request, enforcing `now < expiresAt`.
- [ ] Semantically accurate 401/403/429/5xx; never fail open when key store is unavailable.
- [ ] Rotation issues K2 independently, bounded overlap, client rollout, cutoff, and K1 rejection tests.
- [ ] Revocation is idempotent/terminal, atomic, audited; propagates to all instances within SLA.
- [ ] Rate limits/quotas, anomaly monitoring, minimal error disclosure.
- [ ] Admin API uses strong auth/dedicated RBAC and handles lost keys/offboarding.
- [ ] Tests cover boundary timestamps, revoke races, dropped cache events, multi-region, and infrequent rotation clients.

**Key takeaway:** Rotation means **issuing a new key and cutting off the old key under control**; expiration is a condition **enforced immediately at authentication time**, while revocation disables keys prematurely and must propagate across every API instance. Spring Security places the client into `SecurityContext` only after verifying the key, then uses `GrantedAuthority` to enforce permissions; time handling, auditing, secrets, and consistency determine real-world security.

## References

- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Servlet Filter Chain Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Java 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html)
- [Java 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html)
