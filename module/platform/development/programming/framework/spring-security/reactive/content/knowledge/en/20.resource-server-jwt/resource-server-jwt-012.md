# Limitations of Self-Contained JWTs When Immediate Privilege Revocation Is Required

## 1. Context and Objectives

This lesson belongs to the **Resource Server JWT** section of **Spring Security - reactive / Spring WebFlux**.

A **self-contained JWT** is an access token carrying claims such as `sub`, `scope`, `roles`, `aud`, `iss`, `iat`, `nbf`, `exp` with a digital signature. A Resource Server holding the right verification key can independently verify the signature, issuer, lifetime, and privileges written in claims **without calling the Authorization Server on every request**. This provides major advantages in performance, availability, and scalability.

However, when a user's privileges change or an account must be locked **immediately**, already-issued JWTs generally **do not update their claims automatically**. Even if the backend just deleted the `ADMIN` role in the database, a validly signed access token carrying `scope=reports:approve` still holds the old scope until it expires or the Resource Server rejects it via an **additional stateful mechanism**.

Objectives:

1. Explain accurately the difference between a **cryptographically valid JWT** and **currently valid access privileges under present policy**.
2. Distinguish revoking **one access token**, revoking **all tokens of an account**, changing **roles/permissions**, locking an account, logging out, revoking a **refresh token**, and rotating signing keys.
3. Understand why short `exp` **shrinks the risk window** without guaranteeing immediate revocation.
4. Compare **`jti` denylists**, **authz/version checks**, **introspection for opaque tokens or JWTs**, **central PDPs**, token TTLs, and event-driven caches.
5. Design a state check point after signature/issuer/audience verification without letting lookups block the event loop in Spring WebFlux.
6. Build a **Java 17+, Spring Boot 3.3.5, Spring Security 6.3.x** example featuring a revocation-checking `ReactiveJwtDecoder` and an endpoint revoking **the current access token itself**.
7. Test with `StepVerifier` for the decoder and `WebTestClient` for HTTP authorization, clearly distinguishing tests that **genuinely traverse the decoder** from mocked tests.
8. Evaluate distributed consistency, TTLs, outages, fail-open vs. fail-closed, race conditions, log security, and what “immediate” actually requires.
9. Choose designs tailored to each operation's risk level instead of assuming “JWTs are always stateless so they can never be revoked”.

**Warning:** This lesson includes a denylist stored in a `ConcurrentHashMap` strictly to illustrate **one JVM**. This is not a safe revocation solution across multiple production instances. Making privilege changes take effect system-wide requires a shared state store, clear consistency policies, and matching tests.

## 2. How Do Self-Contained JWTs Work?

Illustrative access token payload:

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-42",
  "aud": ["inventory-api"],
  "jti": "access-7c6f",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000600,
  "scope": "reports:read reports:approve"
}
```

Timestamps and IDs are **dummy explanatory values**, not live tokens expected to run. A JWT has the shape `header.payload.signature` after Base64URL encoding and signing with an algorithm trusted by the issuer/resource server. **Base64URL is not secret encryption**: token holders can read claims, so never place passwords, internal secrets, or unnecessary PII inside access tokens.

In a reactive Spring Security Resource Server, the typical pipeline is:

```text
HTTP Authorization: Bearer <jwt>
           |
           v
AuthenticationWebFilter / Bearer token conversion
           |
           v
ReactiveJwtAuthenticationManager
           |
           v
ReactiveJwtDecoder
    +--> parse JWT safely
    +--> check signature/alg/key
    +--> check iss, exp, nbf
    +--> audience and additional policy if configured
           |
           v
JwtAuthenticationConverter
    +--> scope/scp -> SCOPE_* authorities
           |
           v
ServerHttpSecurity.authorizeExchange(...)
    +--> Authentication / authorities
           |
           v
Controller/Service -> business data
```

With standard `issuer-uri` configuration, Spring Security verifies JWTs using published public keys, checks `iss`, `exp`, and `nbf`, and maps scopes to `SCOPE_`-prefixed authorities. **Audience `aud` must be evaluated per API requirements; do not assume every default config enforces your desired audience.** If the app enforces no `aud` rule, it could accept tokens issued for another resource server under the same issuer.

After verifying a valid signature, `scope=reports:approve` is still merely a string **signed by the issuer at issuance time**. Whether the user is still permitted to approve reports **at request time** is a **different** question.

### What Does a “Valid Signature” Tell Us?

- Claims were signed by a trusted key under the server's algorithm policy.
- Claims were not arbitrarily tampered with since signing.
- `iss`, `aud`, timestamps, and token type are valid **if the corresponding validators are configured properly**.

A signature **does not by itself prove**:
- The account is currently enabled/unlocked.
- The user still holds the roles/permissions described in the token.
- The session at the Authorization Server is still active.
- The access token is absent from a revocation list.
- The refresh token is still valid.
- This resource still belongs to the user (ownership).
- The system has not issued a new emergency policy.

## 3. The “Privileges Changed, Token Still Valid” Problem

Timeline:

```text
09:00  Authorization Server issues JWT:
       sub=user-42, scope=reports:approve, exp=09:15

09:03  Resource Server receives JWT:
       signature ✓   iss ✓   exp ✓   SCOPE_reports:approve ✓
       -> Allows approval

09:04  Admin revokes user-42's approve permission in the database

09:05  Same JWT is re-sent:
       signature ✓   iss ✓   exp ✓   scope claim unchanged
       -> If trusting JWT claims alone: STILL ALLOWED

09:15  JWT expires:
       exp no longer valid -> rejected
```

This is the **stale authorization claims** risk: actual privileges changed while the standalone token still describes an old snapshot.

**Distinction:** A validly signed JWT still working is not a Spring Security bug. The Resource Server is checking exactly what it was asked to check: **signed claims**. If product requirements demand “role changes take effect before the next request”, the design must add a **current-state** decision source.

### Cases to Watch

| Event | Can old JWT continue? | Reason |
| --- | --- | --- |
| Admin removes a user's role | Yes, if token holds old roles/scopes | Signed claims remain unchanged |
| User is disabled/locked | Yes, if RS does not check account state | `exp`/signature still valid |
| User logs out of app | Possibly | UI/session logout does not auto-revoke bearer tokens |
| Refresh token is revoked | Current access token may still remain valid | Two tokens have separate lifecycles |
| Admin revokes **one** access token | Yes, if RS is unaware of revocation event | JWT remains self-verifiable |
| Signing key rotates normally | Possibly | Old key may still be accepted during rollover |
| Key removed in emergency | Many JWTs sharing the key get rejected | Very coarse measure, not per-user |
| Resource ownership changes | Possibly | Token does not track live ownership data |

**Dangerous myth:** “We deleted the refresh token so the old access token is instantly invalid.” Revoking a refresh token mainly **prevents minting new tokens**; rejecting current access tokens requires enforcement at the Resource Server/introspection or waiting for token expiry.

## 4. “Immediate” Must Be Defined by Contract

In distributed systems, “immediately” must be translated into a **measurable security SLA**:

- **From what moment?** Admin clicks the button, the revoke transaction commits, or all nodes process the event?
- **Where?** One Resource Server instance, all API gateways, every region, caches/CDNs, and worker services?
- **For which requests?** Requests starting **after** commit, or also in-flight requests that already passed authorization before commit?
- **Maximum lag?** 0 ms ideal, p99 under 1 second, or up to 30 seconds?
- **When the policy store has an outage?** Reject all sensitive requests (fail closed) or keep trusting JWTs (fail open)?
- **When caches hold stale data?** What is max TTL? Is there event invalidation/revisioning?
- **Regarding already-executed side effects?** You cannot undo a completed wire transfer by revoking a token afterward.

When the requirement is **no new request after commit may be approved with old privileges**, you must read from a state source with **sufficiently strong consistency guarantees**, avoid caching allow decisions for too long, and define in-flight request semantics. Self-contained JWTs **do not provide this property on their own**.

In practice, a system might tolerate stale permissions for 5 minutes on public report reads, yet **forbid** it for payment approvals or admin grants. Apply control rigor proportional to each endpoint's risk.

## 5. Revocation Strategies: Full Comparison

| Strategy | Checks fresh state per request? | Revocation lag | Pros/cons |
| --- | --- | --- | --- |
| Short-TTL JWT | No | Until `exp` expires (plus skew/policy) | Scales easily; no true immediacy |
| Block issuing new refresh tokens | Not for old access tokens | Old access tokens live until expiry | Reduces long-term exposure; not immediate |
| Denylist by `iss+jti` | Yes if checked per request | Store visibility and lookup latency | Selective revocation; adds state/latency |
| Denylist by token digest | Yes if checked per request | Store visibility | Useful when `jti` is absent; must protect digest |
| Per-user `authz_version` | Yes if RS fetches current version | Consistency/version lookup latency | Bulk invalidation of old privileges; still stateful |
| Per-user `not_before`/revokedAfter | Yes if cutoff timestamp checked | Store consistency, clock skew | Invalidates many tokens; watch timestamp resolution |
| Resource ownership/policy DB check | Yes on business operations | Data freshness | Fits per-resource permissions; adds DB/PDP load |
| Opaque token introspection | Yes unless cached too long | OP/introspection response | Centralized revocation; adds network/availability dependency |
| JWT via introspection | Yes if OP supports it | OP response | Keeps JWT format while switching to online validation |
| Token event push + cache invalidation | Conditional on cache design | Event propagation + cache TTL | Very fast, but not an absolute instant guarantee |
| Sign with new key and drop old key | Usually in JWT key validation | Key cache/rotation lag | Very broad, affects many tokens |
| Central Policy Decision Point | Yes by design | Consistency/PDP response | Fits sensitive actions; adds latency & ops |

**There is no “one-size-fits-all”.** You can use short-lived tokens for routine endpoints and add central authorization checks for high-risk transactions.

## 6. Strategy A — Short-Lived Access Tokens

Cutting `exp` from one hour down to 5–15 minutes shrinks the window where old tokens remain usable. For example:

```text
Token A issued 12:00, exp=12:05
Role removed 12:01
No revocation check -> token can still be accepted until 12:05
```

**Pros:**
- The Resource Server only verifies signature/timestamps/audience without hitting a database on every request.
- Limits the blast radius of leaked tokens or stale claims.
- Scales easily across many nodes.

**Limitations:**
- Does not guarantee immediate effect when privileges change.
- Shrinking TTL too aggressively increases token/refresh issuance load, impacting UX and availability.
- Clock skew/leeway slightly extends `exp` acceptance.
- Active refresh tokens can mint new access tokens unless the Authorization Server enforces the updated policy; refreshes must be gated.

**Conclusion:** Short TTL is a risk-reduction measure, **not a sufficient solution** when requirements demand “admin revokes → next request is denied”.

## 7. Strategy B — Denylist by `jti` or Token Digest

`jti` (JWT ID) is a claim identifying a specific token. When access tokens carry sufficiently random, unique `jti`s issued by the Authorization Server, you can store **revoked** state in shared Redis/database:

```text
POST /revoke (at an authorized service)
    |
    v
Authenticate + authorize revoke action
    |
    v
Store revoked(issuer, jti) until at least exp + allowed skew
    |
    v
Every Resource Server on every node:
    verify JWT -> check revoked(iss,jti)
          |
        true --> 401 invalid_token
        false -> continue scope/resource policy authorization
```

### Avoid Storing Raw Bearer Tokens Unnecessarily

Denylist keys can be `issuer + jti` or a safely computed digest of the raw token, depending on your threat model. `jti` must be sufficiently unique and never client-chosen; in multi-tenant/multi-issuer systems, **scope properly by issuer/audience/tenant**. Storing raw JWTs risks leaking claims/credentials if the store is compromised.

If the issuer does **not** include `jti`, do not use raw token values directly as database/log keys. You can store a stable hash/digest/HMAC of the token, while properly managing salts/keys, collisions/formats, and retention.

### Key Limitations

- The store must be **shared across all Resource Servers**; `ConcurrentHashMap` is strictly for demos.
- If a revocation writes to a primary while readers in another region lag, a window accepting old tokens remains. Choose consistency per SLA.
- Denylist TTL should last until the token **can no longer be accepted**, typically `exp + clock skew + propagation margin`. Evicting too early can let a token become valid again inside the skew window.
- Auditing who revoked and under what authority may be needed without logging raw tokens.
- Checking `jti` targets only that token; if a user holds 20 tokens, “revoking the whole account” requires knowing every `jti` or using a user-level version.
- Do not cache `not revoked` results too long if low revocation lag is needed. Negative caches let nodes keep permitting requests during the cache TTL.
- When the store is unreachable, decide fail-open vs. fail-closed **intentionally**. For sensitive actions, fail closed is usually the safer choice.
- Requests authorized right before admin revocation may still be executing. Guard transactions/side effects with policy checks near commit when needed.

## 8. Strategy C — Privilege Versioning, Account State, and Resource Authorization

### 8.1. `authz_version`

The Authorization Server embeds an authorization version in the token:

```json
{
  "sub": "user-42",
  "aud": ["inventory-api"],
  "authz_version": 17,
  "scope": "reports:approve"
}
```

Database / live state store:

```text
current authz_version(user-42) = 18
```

The Resource Server checks:
1. JWT signature/iss/exp/aud are valid.
2. Reads current user/tenant-level version from a store with appropriate freshness.
3. Permits only if `token.authz_version == current_version` (or per designed rule).
4. Otherwise rejects the token and requires fetching a fresh token per policy.

When an admin removes a role, increment the version in the same transaction updating permissions. **All JWTs carrying older versions** are rejected without tracking individual `jti`s.

**Requirement:** The version must be checked **at the Resource Server on every sensitive request or within a tight freshness bound**. If the RS reads the version once at login and caches it indefinitely, stale claims remain the same problem.

Key by `issuer + subject + tenant` in multi-tenant setups; never mix user IDs across tenants. A user whose rights differ per resource may need per-resource/tenant/policy versions rather than only a global user version.

### 8.2. `iat` and Revocation Cutoffs

A variant stores `tokens_valid_after` or `revoked_before` per user. Access tokens with `iat` earlier than the cutoff are rejected.

Risks:
- `iat` has one-second resolution; multiple tokens can share the same second.
- Distributed clocks/clock skew, mid-second updates, and `<` vs. `<=` semantics can misclassify tokens.
- Different issuers have different semantics and do not automatically share synchronized clocks.
- Replays of pre-cutoff tokens must be blocked across all nodes.

Monotonically increasing integer versions can be easier to audit than timestamps, though both require **online state checks**.

### 8.3. Resource Permissions Should Not Live Solely in JWTs

For example, a token carrying `scope=invoice:approve` does not mean the user may approve **every invoice**. Business logic must still check:
- Which tenant does the invoice belong to?
- Does the user have permission on this specific invoice/project?
- Is the invoice already locked, canceled, or approved?
- Does policy require separation of duties?
- Are there conflicting permissions or recent account state changes?

JWT scopes represent **coarse action capabilities**; resource ownership/ABAC normally require querying live state. For ultra-sensitive operations, re-check policy **inside the business transaction** or closer to the side effect.

## 9. Strategy D — Opaque Token Introspection and JWT Introspection

**OAuth 2.0 Token Introspection (RFC 7662)** allows a Resource Server to ask the Authorization Server / Introspection Endpoint whether an access token **is currently active** and retrieve associated metadata. Opaque tokens are non-self-decoding strings, yet **introspection can also be applied to JWTs** if the OP/Authorization Server supports it.

Spring Security reactive includes OAuth2 Resource Server opaque token support. Sample config:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

This is an **alternative to the JWT decoder demo in Section 11**—do not mix both configurations simultaneously and guess which chain gets selected.

Using the opaque token resource-server flow:
1. Resource Server receives the Bearer token.
2. `ReactiveOpaqueTokenIntrospector` calls the endpoint with valid client credentials.
3. OP responds with `active=true/false` and claims/metadata.
4. Spring Security converts active tokens into Authentication/authorities.
5. Resource Server proceeds with authorization.

**Benefit:** The OP can return `active=false` right after a token is revoked, provided OP semantics/consistency meet requirements and the RS **does not cache introspection results too long**.

**Trade-off:** Each request or cache miss incurs a network call, adding latency, OP load, and an availability dependency. Circuit breakers, timeouts, connection pools, caching, outage policies, and metrics must be engineered.

### Introspection with JWTs

When an API requires centralized revocation state while the Authorization Server still issues JWTs, you can choose **introspection for the JWT itself** instead of local signature-only validation. The token format remains JWT, while acceptance becomes an online check.

**Do not confuse:** “Token is signed and has `exp`” does not guarantee the introspection endpoint returns active after revocation; **the OP must actually implement revocation semantics**. Check provider docs and test with real calls.

### RFC 7009 Differs from RFC 7662

- **RFC 7009 — Token Revocation:** authorized clients ask the AS to revoke a token; exact effect and impact on related tokens depend on the AS.
- **RFC 7662 — Token Introspection:** Resource Server asks the AS whether a token is currently **active**.
- **JWT local validation:** checks signature and claims locally without asking the AS about revocation.
- **OIDC Logout:** ends the OP/RP session and does not automatically revoke every OAuth access token.

## 10. Spring WebFlux API Design Principles

### 10.1. Authentication vs. Authorization

In a Resource Server:
- Invalid/expired/revoked token → typically **401 Unauthorized** with an appropriate Bearer challenge.
- Valid token lacking authority/scope → typically **403 Forbidden**.
- Valid token and scope, resource does not belong to user → 403 or 404 per API privacy policy, **never** default 200.
- Revocation state store failure → requests **must not be permitted automatically**; response may be 5xx or a generic 401 depending on classification and internal logging, without exposing token/store internals.

Never write `onErrorResume(e -> Mono.just(jwt))` on a revocation lookup: it turns a database/Redis outage into **fail open**.

### 10.2. Never Block on the Netty Event Loop

Spring WebFlux runs on Reactor. When checking Redis/databases:
- Use reactive clients: `ReactiveRedisTemplate`, R2DBC, or `WebClient`.
- Never call synchronous JDBC, `Thread.sleep`, or `block()` inside `ReactiveJwtDecoder.decode(...)`.
- If forced to integrate a blocking library, isolate with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` with strict bounds, monitoring, and timeouts.
- Never call `subscribe()` inside the auth pipeline; return `Mono<Jwt>` or `Mono<Boolean>` for Spring to manage.
- Use timeouts and cautious retries; unbounded retries during an auth store outage hang requests and amplify DoS.

### 10.3. Verify the Token **Before** Looking Up `jti`

Never trust `jti`, `sub`, or `iss` read from a JWT whose signature has not been verified. If an attacker can send forged tokens with arbitrary `jti`s and trigger store lookups, they can cause enumeration or store exhaustion. Right flow: **verify cryptographic claims first → read trusted claims → check state**.

### 10.4. Do Not Rely on `jti` Alone When All User Privileges Must Be Revoked

Denylisting a single token revokes only that token. If a user holds tokens B and C or tokens for other APIs, changing a user's role does not automatically add every `jti` to the denylist. For global privilege changes, consider user/tenant versioning, live state lookups, or introspection. You can combine per-token denylists for current-token logout with `authz_version` for account lockouts and role changes.

## 11. Runnable Example: Java 17+, Spring Boot 3.3.5, WebFlux

This project illustrates a **JWT Resource Server** with a token-ID denylist. Requirements:
- Test Authorization Server/IdP issues **signed JWT access tokens** with `iss`, `sub`, `aud=inventory-api`, `jti`, `exp`, and `scope`.
- Resource Server receives Bearer tokens, verifies cryptographic validity, and then checks revocation.
- Endpoint `POST /api/token/revoke-current` lets an authenticated principal revoke **that exact bearer token**, never an arbitrary client-supplied `jti`.
- After the endpoint returns 204 and revocation is visible, new requests using **the same token** are rejected.
- `GET /api/reports` requires `SCOPE_reports:read`; `GET /api/me` requires only authentication.
- The **single-JVM in-memory** denylist is strictly for demonstration; production requires a shared store.

### 11.1. Project Structure

```text
reactive-jwt-revocation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/jwtrevoke/
    │   │   ├── JwtRevocationApplication.java
    │   │   ├── ReactiveRevocationStore.java
    │   │   ├── InMemoryRevocationStore.java
    │   │   ├── RevocationAwareJwtDecoder.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/dev/example/jwtrevoke/
        ├── RevocationAwareJwtDecoderTests.java
        └── JwtApiHttpTests.java
```

### 11.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-jwt-revocation-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-oauth2-resource-server` pulls in the components needed for Resource Server JOSE/JWT validation under Boot's dependency management. Never add `spring-boot-starter-web`, preventing Spring Boot from switching to Servlet/MVC when targeting WebFlux.

### 11.3. `application.yml`

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

app:
  security:
    issuer-uri: ${JWT_ISSUER_URI}
    audience: inventory-api
```

Environment variable `JWT_ISSUER_URI` must be the **real issuer URI of a test Authorization Server** publishing OIDC/OAuth metadata and a JWK Set. In this example, the `@Bean` decoder uses that issuer and **may contact the discovery endpoint at app startup**. This is not a dummy JWT-minting service; real E2E testing requires a matching issuer.

Never accept JWTs signed by an arbitrary issuer. Trusted issuer/alg/audience settings must be server-managed; never read issuers from user-sent request headers or query params.

### 11.4. Main Class

`src/main/java/dev/example/jwtrevoke/JwtRevocationApplication.java`:

```java
package dev.example.jwtrevoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtRevocationApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtRevocationApplication.class, args);
    }
}
```

### 11.5. ReactiveRevocationStore Contract

`src/main/java/dev/example/jwtrevoke/ReactiveRevocationStore.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import reactor.core.publisher.Mono;

public interface ReactiveRevocationStore {

    Mono<Boolean> isRevoked(String issuer, String jti);

    Mono<Void> revoke(String issuer, String jti, Instant expiresAt);
}
```

This is a **business abstraction**: the Resource Server needs to know whether a token was revoked. It is not a built-in Spring Security interface. Production implements it over reactive Redis/databases or a policy service with suitable consistency.

### 11.6. Single-JVM Demo-Only Store

`src/main/java/dev/example/jwtrevoke/InMemoryRevocationStore.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class InMemoryRevocationStore
        implements ReactiveRevocationStore {

    private record TokenKey(String issuer, String jti) {
    }

    private final ConcurrentHashMap<TokenKey, Instant> denied =
            new ConcurrentHashMap<>();

    @Override
    public Mono<Boolean> isRevoked(String issuer, String jti) {
        return Mono.fromSupplier(() -> {
            TokenKey key = new TokenKey(issuer, jti);
            Instant until = denied.get(key);

            if (until == null) {
                return false;
            }
            if (Instant.now().isAfter(until)) {
                denied.remove(key, until);
                return false;
            }
            return true;
        });
    }

    @Override
    public Mono<Void> revoke(
            String issuer, String jti, Instant expiresAt) {

        return Mono.fromRunnable(() -> {
            // Keep deny entry for 120 seconds past exp:
            // demo margin for clock skew/propagation.
            Instant until = expiresAt.plusSeconds(120);
            TokenKey key = new TokenKey(issuer, jti);
            denied.merge(key, until,
                    (oldUntil, newUntil) ->
                            oldUntil.isAfter(newUntil)
                                    ? oldUntil : newUntil);
        }).then();
    }
}
```

**Important notes:**
- Keys are `(issuer, jti)` pairs, never raw JWTs.
- Entries persist until `exp + 120s` to avoid premature eviction within clock skew. **120 seconds is strictly a demo parameter**; production calculates it from accepted clock skew, propagation, and actual policy.
- `Mono.fromSupplier`/`Mono.fromRunnable` perform no blocking I/O: in-memory map access is fast.
- `ConcurrentHashMap` is shared only within **one JVM**; restarts wipe entries and other replicas cannot see them. **Never use this implementation to promise production logout/revocation.**
- TTL purging here is lazy on lookup; production stores should use automatic expiry/TTL, memory bounds, and monitoring.
- The store always emits a `Boolean`; production stores must never silently emit `Mono.empty()` when lookups fail.

### 11.7. Decoder Adding State Checks **After** JWT Verification

`src/main/java/dev/example/jwtrevoke/RevocationAwareJwtDecoder.java`:

```java
package dev.example.jwtrevoke;

import java.net.URI;
import java.time.Instant;

import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

public final class RevocationAwareJwtDecoder
        implements ReactiveJwtDecoder {

    private final ReactiveJwtDecoder delegate;
    private final ReactiveRevocationStore store;
    private final String expectedAudience;

    public RevocationAwareJwtDecoder(
            ReactiveJwtDecoder delegate,
            ReactiveRevocationStore store,
            String expectedAudience) {
        this.delegate = delegate;
        this.store = store;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public Mono<Jwt> decode(String rawToken) {
        // Process claims ONLY AFTER delegate.decode verifies signature,
        // issuer, and timestamps per the configured decoder.
        return delegate.decode(rawToken)
                .flatMap(jwt -> validateCurrentState(jwt));
    }

    private Mono<Jwt> validateCurrentState(Jwt jwt) {
        if (!jwt.getAudience().contains(expectedAudience)) {
            return Mono.error(new BadJwtException(
                    "JWT audience is not accepted"));
        }

        URI issuer = jwt.getIssuer();
        String jti = jwt.getId();
        Instant expiresAt = jwt.getExpiresAt();

        if (issuer == null || jti == null || jti.isBlank()
                || expiresAt == null) {
            return Mono.error(new BadJwtException(
                    "Required token claims are missing"));
        }

        return store.isRevoked(issuer.toString(), jti)
                .flatMap(revoked -> Boolean.TRUE.equals(revoked)
                        ? Mono.<Jwt>error(new BadJwtException(
                                "Access token has been revoked"))
                        : Mono.just(jwt))
                // Do not treat unknown status as "not revoked".
                .switchIfEmpty(Mono.error(new BadJwtException(
                        "Revocation status unavailable")));
    }
}
```

Key points:
1. `delegate.decode(rawToken)` runs via Spring Security's JWT decoder and must verify **cryptographic signature + issuer + exp/nbf** per trusted policy. Never Base64-parse and trust `jti` yourself.
2. Afterward, the decoder verifies `audience == inventory-api` and requires `iss`, `jti`, and `exp`. This is this demo API's specific policy, not a requirement of every valid JWT.
3. `store.isRevoked(iss,jti)` runs **on every Bearer JWT request** passing through the decoder.
4. If revoked, throws `BadJwtException`; the Resource Server normally turns authentication failure into **401** for new requests.
5. If the store emits `Mono.empty()`, the code fails closed rather than allowing access. Real store errors propagate as errors; there is no `onErrorResume(... -> jwt)` turning outages into allowances.
6. Never log `rawToken`, raw claims, or error messages containing tokens. Client-facing errors must stay generic.
7. This wrapper does not solve **changing roles across all JWTs of a user**; it revokes only the specific `jti`s stored in the denylist.
8. In-flight requests that already passed the decoder before revocation may continue. If an action requires pre-commit guarantees, re-check policy near the transaction boundary.

**Alternative:** When requirements call for role changes rather than revoking individual tokens, implement an `authz_version` check in the wrapper or business policy service; do not try to find every token of a user from JWTs if the issuer maintains no session/token index.

### 11.8. Spring Security Chain

`src/main/java/dev/example/jwtrevoke/SecurityConfig.java`:

```java
package dev.example.jwtrevoke;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.issuer-uri}") String issuer,
            @Value("${app.security.audience}") String audience,
            ReactiveRevocationStore store) {

        ReactiveJwtDecoder verifiedDecoder =
                ReactiveJwtDecoders.fromIssuerLocation(issuer);

        return new RevocationAwareJwtDecoder(
                verifiedDecoder, store, audience);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Demo ONLY for stateless API using Authorization: Bearer,
                // NOT using cookie/browser session authentication.
                .csrf(csrf -> csrf.disable())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/reports")
                            .hasAuthority("SCOPE_reports:read")
                        .pathMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .pathMatchers(HttpMethod.POST,
                                "/api/token/revoke-current")
                            .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

**CSRF Warning:** `csrf.disable()` is appropriate only for **stateless APIs using explicit Bearer tokens in `Authorization` headers, with no automatic cookies/sessions**. In mixed apps with browsers/OIDC login/sessions or automatic cookie credentials, keep/enable CSRF and configure separate security chains as needed. Never copy this disable into browser session apps just to make POST work.

`ReactiveJwtDecoders.fromIssuerLocation(issuer)` may contact issuer metadata to fetch the JWK Set URI; real apps require a trusted HTTPS issuer. Never replace this decoder with test `Jwt.withTokenValue(...)` in production: the test builder does not verify signatures.

### 11.9. Controller with Endpoint Revoking **the Current Token Itself**

`src/main/java/dev/example/jwtrevoke/DemoController.java`:

```java
package dev.example.jwtrevoke;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final ReactiveRevocationStore store;

    public DemoController(ReactiveRevocationStore store) {
        this.store = store;
    }

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public-ok");
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports-read-ok");
    }

    @PostMapping("/api/token/revoke-current")
    public Mono<ResponseEntity<Void>> revokeCurrent(
            @AuthenticationPrincipal Jwt jwt) {

        return store.revoke(
                        jwt.getIssuer().toString(),
                        jwt.getId(),
                        jwt.getExpiresAt())
                .thenReturn(ResponseEntity
                        .status(HttpStatus.NO_CONTENT)
                        .<Void>build());
    }
}
```

**Scope of the demo revoke feature:** The current Bearer JWT already passed authentication and carries `jti`; the caller may only request revoking **that exact token**. Clients **cannot** submit an arbitrary `jti`, user ID, or another raw token to revoke someone else's access.

HTTP 204 proves only that **the store finished writing the entry during the request**. For production stores, define write durability and cross-replica visibility; never assume all nodes see it instantaneously. After revoking, the client should stop reusing the token and clear it from memory/storage per flow.

With real business data, do not expose token IDs, raw claims, or unnecessary permissions in `/api/me`. Return an allowlisted DTO.

## 12. Running the App with a Test Authorization Server

You need a JWT issued by the **test issuer** matching `JWT_ISSUER_URI` containing:

- Exact matching `iss`.
- `aud` containing `inventory-api`.
- Unique `jti` and future `exp`.
- `sub` as the subject.
- `scope` containing `reports:read` when expecting GET `/api/reports` to return 200.
- Signing algorithm/key trusted by the Resource Server via issuer/JWK metadata.

**You cannot create a valid JWT merely by editing the payload strings above:** it must be signed by the Authorization Server with a valid private key and paired with a JWKS serving the matching public key.

Set the environment variable using your environment's secret/config management and run:

```bash
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew bootRun` (Linux/macOS) or `gradlew.bat bootRun` (Windows). Use HTTPS in production. Never copy real access tokens into shell history, URL queries, or support chats.

### 12.1. Testing with cURL — Without Printing Real Tokens

In the lab, put a test token from the issuer into a temporary environment variable (e.g., `ACCESS_TOKEN`) and avoid printing its value to terminals/logs. The commands below assume the variable is safely populated:

```bash
curl -i http://localhost:8080/public

curl -i http://localhost:8080/api/me

curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me

curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports

curl -i -X POST \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/token/revoke-current

curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me
```

**Expected with a valid token and single-JVM store:**
1. `/public` without Bearer → 200, `public-ok`.
2. `/api/me` without Bearer → 401.
3. `/api/me` with unrevoked token → 200, JSON subject.
4. `/api/reports` requires `reports:read` scope; if present → 200, if absent → 403.
5. POST `/api/token/revoke-current` with valid token → **204 No Content**, writes deny entry.
6. GET `/api/me` **again with the same token** → **401** (once the store has written/read the entry).

These outcomes are **code expectations**, not a report from running against a real issuer. In production, a client that revoked a token should discard it and run login/refresh per policy; the test re-sends the token solely to confirm the denylist works.

### 12.2. Why Not Put Tokens in URLs?

A Bearer token is a credential: anyone holding it can attempt to use it within its lifetime and scope. Query parameters easily leak into browser history, access logs, Referrer headers, analytics, and monitors. Use `Authorization: Bearer` over TLS, with gateway/log redaction.

## 13. Unit Tests for RevocationAwareJwtDecoder

Tests **do not use a real Authorization Server**. We supply a **fake delegate** returning a pre-built `Jwt` to test **post-decode policy logic**, without pretending the fake delegate verified signatures. Testing real signatures/issuer/timestamps requires signed test JWTs + test public keys/JWKS.

File `src/test/java/dev/example/jwtrevoke/RevocationAwareJwtDecoderTests.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RevocationAwareJwtDecoderTests {

    private static final String ISSUER =
            "https://issuer.example.test";

    private Jwt jwt(String jti, String audience) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("signed-jwt-fixture")
                .header("alg", "RS256")
                .issuer(ISSUER)
                .subject("alice")
                .audience(List.of(audience))
                .jti(jti)
                .issuedAt(now.minusSeconds(2))
                .expiresAt(now.plusSeconds(300))
                .claim("scope", "reports:read")
                .build();
    }

    private RevocationAwareJwtDecoder decoder(
            Jwt fixture, InMemoryRevocationStore store) {

        // Fake delegate: simulates completed crypto verification step.
        ReactiveJwtDecoder verifiedFake =
                ignoredToken -> Mono.just(fixture);

        return new RevocationAwareJwtDecoder(
                verifiedFake, store, "inventory-api");
    }

    @Test
    void allowsValidNonRevokedToken() {
        var store = new InMemoryRevocationStore();
        Jwt fixture = jwt("jti-101", "inventory-api");

        StepVerifier.create(
                decoder(fixture, store).decode("test-token"))
                .assertNext(value ->
                        assertEquals("jti-101", value.getId()))
                .verifyComplete();
    }

    @Test
    void rejectsSameTokenAfterRevocation() {
        var store = new InMemoryRevocationStore();
        Jwt fixture = jwt("jti-102", "inventory-api");
        var target = decoder(fixture, store);

        StepVerifier.create(target.decode("test-token"))
                .expectNextCount(1)
                .verifyComplete();

        StepVerifier.create(store.revoke(
                ISSUER, fixture.getId(), fixture.getExpiresAt()))
                .verifyComplete();

        StepVerifier.create(target.decode("test-token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void doesNotRevokeOtherJtiForSameIssuer() {
        var store = new InMemoryRevocationStore();
        Jwt revoked = jwt("jti-103", "inventory-api");
        Jwt other = jwt("jti-104", "inventory-api");

        StepVerifier.create(store.revoke(
                ISSUER, revoked.getId(), revoked.getExpiresAt()))
                .verifyComplete();

        StepVerifier.create(decoder(other, store).decode("other"))
                .expectNextCount(1)
                .verifyComplete();
    }

    @Test
    void rejectsJwtForAnotherAudience() {
        var store = new InMemoryRevocationStore();
        Jwt anotherApi = jwt("jti-105", "payments-api");

        StepVerifier.create(
                decoder(anotherApi, store).decode("token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void rejectsTokenWithoutJti() {
        var store = new InMemoryRevocationStore();
        Instant now = Instant.now();

        Jwt missingJti = Jwt.withTokenValue("fixture")
                .header("alg", "RS256")
                .issuer(ISSUER)
                .subject("alice")
                .audience(List.of("inventory-api"))
                .expiresAt(now.plusSeconds(120))
                .build();

        StepVerifier.create(
                decoder(missingJti, store).decode("token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void rejectsWhenTrustedDelegateRejectsSignature() {
        var store = new InMemoryRevocationStore();
        ReactiveJwtDecoder badSignature =
                ignoredToken -> Mono.error(
                        new BadJwtException("Invalid signature"));

        var target = new RevocationAwareJwtDecoder(
                badSignature, store, "inventory-api");

        StepVerifier.create(target.decode("forged-token"))
                .expectError(BadJwtException.class)
                .verify();
    }

    @Test
    void sameJtiUnderAnotherIssuerIsIndependent() {
        var store = new InMemoryRevocationStore();
        Jwt fixture = jwt("jti-106", "inventory-api");

        StepVerifier.create(store.revoke(
                "https://another-issuer.example.test",
                "jti-106", fixture.getExpiresAt()))
                .verifyComplete();

        StepVerifier.create(decoder(fixture, store).decode("token"))
                .expectNextCount(1)
                .verifyComplete();
    }
}
```

Expected: **7 passing tests**, no network issuer required. This tests only the added logic after a **fake-delegate-simulated** decode/crypto step; it **does not verify** JWT signatures, issuer discovery, JWKS rotation, or real OP-issued access tokens.

### Why Does Signature Testing Require a Separate Test Suite?

A `Jwt` built with `Jwt.withTokenValue(...)` is not a valid signed access token. Unit tests mocking a successful decoder let us focus on:
- Does `aud` match the API?
- Is `jti` required?
- Once revoked in the store, does `decode` return an error?
- Are only the matching `jti`/issuer rejected?
- Are `BadJwtException` errors from the delegate decoder preserved rather than swallowed?

Cryptographic verification must be tested using key fixtures/signed JWTs with `NimbusReactiveJwtDecoder` and test issuer/JWKS, or integration tests against a test Authorization Server. Never use `mockJwt()` to claim “revocation has been tested”: `mockJwt` bypasses the decode path by design.

## 14. HTTP Tests with WebTestClient — Distinguishing Mocks from Real Decoders

Spring Security test lets you mock `ReactiveJwtDecoder` to quickly test routing/authorization without an issuer. The HTTP tests below deliberately **mock the decoder**, so they only confirm 200/401/403 at the HTTP layer. They **do not** verify that `RevocationAwareJwtDecoder`'s revocation filter is called, because the decoder bean is mocked.

File `src/test/java/dev/example/jwtrevoke/JwtApiHttpTests.java`:

```java
package dev.example.jwtrevoke;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@TestPropertySource(properties = {
        "app.security.issuer-uri=https://issuer.example.test",
        "app.security.audience=inventory-api"
})
class JwtApiHttpTests {

    @Autowired
    WebTestClient client;

    // Valid MockBean in Spring Boot 3.3.5; replaces the @Bean decoder,
    // does NOT run JWT signature verification or the revocation wrapper.
    @MockBean
    ReactiveJwtDecoder decoder;

    private Jwt jwt(String jti, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("mock-" + jti)
                .header("alg", "RS256")
                .issuer("https://issuer.example.test")
                .subject("alice")
                .audience(List.of("inventory-api"))
                .jti(jti)
                .issuedAt(now.minusSeconds(1))
                .expiresAt(now.plusSeconds(300))
                .claim("scope", scope)
                .build();
    }

    @BeforeEach
    void setup() {
        when(decoder.decode(anyString()))
                .thenReturn(Mono.error(
                        new BadJwtException("Invalid token")));

        when(decoder.decode("reader-token"))
                .thenReturn(Mono.just(
                        jwt("http-101", "reports:read")));

        when(decoder.decode("no-scope-token"))
                .thenReturn(Mono.just(
                        jwt("http-102", "profile:read")));
    }

    @Test
    void publicGetDoesNotNeedBearerToken() {
        client.get().uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public-ok");
    }

    @Test
    void privateGetWithoutTokenIs401() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validMockJwtCanReadOwnSubject() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void scopeAllowsReports() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("reports-read-ok");
    }

    @Test
    void missingScopeReturns403() {
        client.get().uri("/api/reports")
                .headers(h -> h.setBearerAuth("no-scope-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void decoderRejectedTokenReturns401() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth("invalid-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void revokeEndpointReturns204ForAuthenticatedRequest() {
        client.post().uri("/api/token/revoke-current")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isNoContent();
    }
}
```

Expected: **7 passing HTTP tests** on Boot 3.3.5. They verify mapping from Bearer Authentication to status/authorities and controllers. There is **no** assertion that “after revoking, `reader-token` gets 401” in this suite, because the mock decoder **keeps returning a `Jwt` for `reader-token` on every call**. That would be a broken test if advertised as testing revocation.

### Running Tests

```bash
gradle test
```

Expected total: **14 tests** (7 `StepVerifier` + 7 `WebTestClient`) passing. This is an **expectation from the code**, not a claim that Gradle was run. Run in your IDE or project terminal and inspect test reports to confirm.

### Real End-to-End Revocation Testing

To prove a JWT was **cryptographically verified and revoked on a real request**, add an integration test:
1. Use a test issuer/JWKS with standard signed JWTs or a private/public key fixture in the test environment.
2. Keep the real `RevocationAwareJwtDecoder`; **do not mock the decoder**.
3. Send GET `/api/me` with a valid signed token → 200.
4. Send POST `/api/token/revoke-current` with the same token → 204.
5. Re-send GET `/api/me` with **the same signed token** → 401.
6. Send another token of the matching user/issuer → behavior per policy, without accidentally revoking all tokens.
7. With multiple app instances, send the final request to **another instance** and verify shared denylist store visibility.
8. Simulate store timeout/outage and verify **no fail-open**.

This test still requires an appropriate environment/store; never infer from unit/mock tests that a production cluster has immediate revocation.

## 15. Replacing the Single-JVM Store with Redis/Reactive DB in Production

The `ReactiveRevocationStore` contract need not change; the implementation must move to a source visible across **all nodes**.

A Redis diagram:

```text
Admin/Auth Service ---- revoke(iss,jti) ----> Redis primary / durable store
                                                |
                         +----------------------+----------------+
                         |                                       |
                    RS instance A                           RS instance B
                    read revoked                            read revoked
                         |                                       |
                    deny token                               deny token
```

### TTL and Keys

- Keys should combine `issuer + jti` (or a controlled token digest); avoid collisions across issuers/tenants.
- TTL lasts at least `exp + accepted clock skew + propagation margin`.
- Namespace-prefix Redis keys and avoid putting raw tokens/PII into keys/logs.
- If Redis lacks SLA-grade durability or uses lagging read replicas, you cannot promise global immediate revocation.
- A revoke event must be idempotent; revoking the same token multiple times must not misbehave.
- Record/log audit events (who, why, policy) **without logging raw bearer tokens**.
- Monitor TTLs and store size; denylists can grow large under high token volumes.

### Caching and Negative Lookups

If using a 30-second local “not revoked” cache, a revoked user can still access the API for those 30 seconds. Achieving “effective before next authorized request” requires eliminating stale allow caches or bounding TTL strictly, paired with consistent push invalidation.

**Event-driven invalidation alone gives no strong guarantee:** an event can arrive late, be dropped, replayed, or miss newly scaled-out instances. Fallbacks/sync/reconciliation and bounded stale windows are required.

### Outage Policy

Choose an explicit policy:
- **Fail closed:** store unavailable → deny operations requiring revocation checks; increases false denials/availability cost while limiting security risk.
- **Fail open:** store unavailable → temporarily trust JWT; helps availability but defeats immediate revocation during outages.
- **Risk-tiered:** low-sensitivity GETs may degrade per policy, while approval/payment POSTs always require a fresh check.

Never implement a silent `onErrorResume` fallback and then claim “instant revocation”.

### Cost Optimization

- Keep access token TTL short enough that denylist retention stays brief.
- Use per-user/tenant versions for bulk privilege-change events.
- Apply state checks selectively by endpoint sensitivity rather than adding heavy lookups to every public route.
- Use reactive drivers, connection pooling, timeouts, and bulkheads to keep the event loop healthy.
- Track consistency and P95/P99 latency; measure from revoke commit to the first denied request across every region.

## 16. Revoking User Privileges vs. Revoking One Token

With the demo `/api/token/revoke-current` endpoint, only the calling token is marked revoked. If the user holds another token on another device, that token is **not yet** denied.

When an admin removes the `reports:approve` role:
- If you track all active `jti`s of the user: you can revoke each token, provided the index is reliable and synchronized.
- Without a token index: use `authz_version` or `tokens_valid_after` to invalidate a broad class of tokens via live state checks.
- If privileges depend on an invoice/project: check resource state/ABAC in the business layer rather than relying solely on role claims.
- With trusted Authorization Server introspection: the RS can query live token active/permission status, aligning semantics with the OP.

A hybrid pattern:

```text
1. Local validation of JWT signature/issuer/aud/exp
2. Denylist jti for logout/revoking a specific token
3. User/tenant authz_version check for role changes/lockouts
4. Resource ownership/policy check near the transaction
5. Short token TTL + proper refresh policy
```

Each layer mitigates a different risk scope; latency and availability must be budgeted. Never assume step 2 suffices for all permission changes.

## 17. Common Pitfalls

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Admin removes role, yet JWT still gets in | Stale scope in old JWT still trusted | Add current-policy/version check or introspection |
| User logs out, yet JWT still calls API | Local logout/refresh revoke does not affect access token | Revoke access token or wait for TTL |
| RS accepts token meant for another API | Missing `aud` validator | Validate expected audience |
| Claim role is ADMIN, policy expects SCOPE_ADMIN | Wrong role/scope mapping | Check `JwtGrantedAuthoritiesConverter` and claim source |
| Denylist works on node A, passes on B | In-memory store or replication lag | Shared store + consistency tests |
| Server restart lets revoked token work again | Entries lived only in RAM | Durable/shared store with TTL |
| Token becomes valid again near `exp` | Denylist entry expired before clock skew | Retain until `exp` + proper margin |
| Store timeout returns 200 | Fail-open fallback present | Fail closed on sensitive APIs |
| Returns 403 instead of 401 | Token authenticated, lacking authority | Separate authentication vs. authorization |
| Resource Server event loop slows down | Sync DB/blocking call in decoder | Reactive driver or controlled `boundedElastic` |
| Empty `jti` renders revocation ineffective | AS omits `jti` or RS fails to reject | Require `jti` per contract or use digest strategy |
| `mockJwt()` tests PASS, production revoke fails | Mock bypasses decoder | Add signed-token integration tests |
| Access token stays active after RFC 7009 refresh revoke | Access token not auto-revoked | Check AS policy + introspection/denylist |
| JWKS key rotation logs every user out | Key rotation/deletion is not per-user revocation | Pick right-granularity strategy |
| Permissions stale via local cache | `authz_version`/not-revoked cached too long | Invalidation + bounded freshness |
| User disabled, yet JWT still accepted | RS ignores current user state | User state/version/introspection |
| Claims leak PII in logs | Logging full JWT/`Authorization` | Redact credentials; keep PII out of tokens |
| Revoke vs. transaction race | Request passed check before revoke commit | Enforce near side effect; consistency/locking as needed |

## 18. Production Review Checklist

1. JWT verifier uses trusted issuer/JWKS/algorithms; rejects `alg=none` and unverified token-supplied keys.
2. `iss`, `exp`, `nbf`, and `aud` are validated; token type/scopes match the API contract.
3. Authorization separates user roles/scopes from resource/tenant permissions.
4. A **revocation SLA** is defined from commit to visibility across all nodes.
5. Token TTL fits the threat model without claiming to be instant revocation.
6. For single-token revocation, `jti` is a unique, sufficiently random ID or backed by a digest strategy.
7. Denylist stores no raw tokens; TTL covers accepted clock skew.
8. Store is shared across all replicas/regions; consistency and durability verified.
9. “Not revoked” is never cached longer than the allowed window.
10. Store outage policy is defined; no silent fail-open.
11. Account locks, role changes, and tenant removals trigger **per-user/resource policy checks**, not just single-`jti` denylisting.
12. Access token and refresh token revocation are handled separately per OP policy.
13. Bearer tokens travel only via HTTPS/headers and are redacted from logs/URLs/APM.
14. Reactive code never calls `block()` on the event loop.
15. 401 for invalid/revoked tokens; 403 for valid tokens lacking scope; error responses leak no secret causes.
16. Fake-decoder unit tests are clearly separated from cryptographic signed-token tests.
17. HTTP tests cover 200/401/403 and CSRF accurately per client authentication model.
18. Tested reusing an old token after revocation on another instance and across restarts/failover.
19. In-flight requests/side effects accounted for in the threat model.
20. Rollout includes metrics: revoke lag, store latency, error rate, p95/p99, cache hit/staleness.
21. IdP/Authorization Server token lifetime/introspection/revocation policies confirmed against provider docs.
22. Incident playbook covers token leakage, key compromise, and privacy of security logs.

## 19. Self-Check Questions

**1. Why can a self-contained JWT still work after a role is revoked?**  
Because the token carries a signed snapshot of claims; verifying the signature and `exp` does not query live privileges.

**2. Is a JWT with a 5-minute `exp` immediate revocation?**  
No. It only narrows the window during which old tokens remain acceptable.

**3. Does deleting a refresh token immediately block old access tokens?**  
Not by default; active access tokens require separate enforcement.

**4. How does 401 differ from 403?**  
401 is for invalid/revoked/expired authentication tokens; 403 is for an authenticated principal lacking permission.

**5. What scope does a `jti` denylist cover?**  
Revoking a **specific token** with a known ID, provided all Resource Servers check a shared store with adequate freshness.

**6. Why keep denylist entries until `exp + clockSkew`?**  
To avoid deleting an entry while a verifier still accepts the token due to clock skew leeway.

**7. Which scenario does `authz_version` solve?**  
It invalidates all tokens carrying older versions when a user/tenant's privileges are updated, provided the RS checks the current version.

**8. If a local cache holds `authz_version` for 60 seconds, are privilege changes “immediate”?**  
No; the cache can permit stale privileges for up to 60 seconds unless reliably invalidated.

**9. Can introspection be used only with opaque tokens?**  
No. Spring Security can introspect JWT-formatted tokens too when supported by the Authorization Server; validation becomes online.

**10. Does RFC 7009 revocation automatically inform a local JWT Resource Server decoder that a token was revoked?**  
No. The RS needs a state lookup, introspection, or another update mechanism.

**11. Why not check `jti` before verifying the signature?**  
Because unverified claims can be forged, causing wrong decisions and lookup abuse.

**12. Is `@AuthenticationPrincipal Jwt` in a controller the final authority on permissions?**  
No. `Jwt` holds verified claims, yet business authorization may need live user/resource state.

**13. Can a `ConcurrentHashMap` denylist be used in multi-node production?**  
No. Restarts wipe entries and other nodes will not see them.

**14. During a Redis outage, is returning 200 based on JWT claims safe for payment approval?**  
Usually not if the contract requires immediate revocation; design fail-closed/risk-tiered policies.

**15. Do `mockJwt()` tests verify cryptographic decoder signatures?**  
No; they simulate authentication, fitting authorization tests without proving the revocation pipeline.

**16. Can a token revoked after a request starts still cause side effects?**  
Possibly, if the request already passed authorization; enforce policies near transaction commit when strictly required.

**17. What does a “valid” JWT signature prove?**  
That claims were not altered since being signed by a trusted issuer/key; it does not prove current role/account status.

**18. When an API serves multiple tenants, what must be watched?**  
Key state and claims by issuer/subject/tenant/resource; never mix identities or permissions across tenants.

### Hands-On Exercises

1. Run `RevocationAwareJwtDecoderTests` and explain why after `store.revoke` the same `jti` is rejected while a different `jti` is accepted.
2. Write a test where the store returns `Mono.empty()` and confirm the wrapper does not turn unknown status into an allowance.
3. Add a custom `authz_version` claim and a fake `ReactiveUserVersionStore`; test that token versions lower than the current version are denied.
4. Move the demo denylist to Redis using a reactive driver with `TTL = exp + margin`; test two instances reading the same entry.
5. Simulate a store outage; verify there is no `onErrorResume` letting sensitive requests pass.
6. Use a test authorization server to issue a JWT with the wrong `aud`; confirm the decoder rejects it before authorization.
7. Build a signed test JWT/JWKS fixture and real integration test: initial 200 → POST revoke 204 → same token 401.
8. Write an HTTP test for a valid token lacking `reports:read` and distinguish 403 from a revoked 401.
9. Simulate disabling a user in the database and compare local-JWT-only vs. live-state-check outcomes.
10. Compare a 5-minute TTL vs. a 30-second introspection cache: what is the worst-case staleness of each?
11. Test concurrent revocation and business writes; propose policy checks at the transaction boundary.
12. Write policies for three tiers—public read, private read, payment approval—with matching revocation SLAs.
13. Verify logs/gateways redact `Authorization`, token values, and raw claims.
14. Explain why signing JWTs with a new key and deleting the old key is too coarse to replace per-token denylists.

## 20. References

- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): signature verification, issuer/exp/nbf, `ReactiveJwtDecoder`, scope mapping, and validators.
- [Spring Security — Reactive Opaque Token Introspection](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector`, active flag, ability to introspect JWTs too.
- [Spring Security — Reactive OAuth2 Tests](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` and limits of mock authentication.
- [Spring Security 6.3 Jwt.Builder API](https://docs.spring.io/spring-security/site/docs/6.3.8-SNAPSHOT/api/org/springframework/security/oauth2/jwt/Jwt.Builder.html): `jti`, `audience`, `issuer`, `expiresAt` in fixtures.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT registered claims `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithms, validation, and JWT pitfalls to avoid.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): structure and requirements for JWT access tokens.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation semantics.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): verifying `active` and metadata at the AS.
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): denylist, token storage, and revocation considerations.
- [Spring Security — Reactive WebFlux](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` and reactive HTTP security.

**Remember:** **Self-contained JWTs carry a signed snapshot of privileges; a valid signature and `exp` do not prove current privileges have not been revoked.** When immediate effect across all Resource Servers is needed, add a **state check with appropriate consistency** (`jti` denylist, `authz_version`, resource authorization, introspection/PDP), engineer TTLs/caches/outages, and test from revoke commit to subsequent requests. Short TTLs help, yet **do not equal immediate revocation**.