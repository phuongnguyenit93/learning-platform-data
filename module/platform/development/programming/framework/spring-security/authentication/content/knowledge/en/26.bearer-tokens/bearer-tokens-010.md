# Token Lifetime, Revocation, and Permission Changes After Token Issuance

> **Context:** Spring Security Authentication, **Bearer token** group, focusing on OAuth2 access tokens for REST APIs. Java examples target Java 17+, Spring Boot 3.x, and Spring Security 6.x on the Servlet stack. Authorization Server/Identity Provider (IdP) mechanisms vary: always verify the provider's actual token, revocation, introspection, and policy contracts.

## Learning Objectives

After this lesson, you will be able to:

1. Correctly interpret `exp`, `nbf`, `iat`, `jti`, `iss`, `aud`, and `scope` in an access token; explain why **token expiration** does not equal **immediate token revocation**.
2. Distinguish **self-contained JWTs** verified locally by the Resource Server from **opaque tokens** introspected at the Authorization Server.
3. Design revocation capabilities for access/refresh tokens after logout, token exposure, account lock, or permission changes.
4. Demonstrate why permissions inside a token can be **staler than current permissions in the database** and choose controls suited to sensitivity.
5. Configure Spring Security Resource Server to validate issuer, audience, signature, timestamps, and authorities; combine with live permission checks when needed.
6. Test cases where a token has not yet expired yet **has been revoked** or the user's **permissions were downgraded**.

## 1. What Is a Bearer Token and What Is the Risk When Permissions Change?

A Bearer token is a credential that any party holding it can use to call APIs within its allowed scope; it does not prove the caller is the original token owner via an extra cryptographic key. Clients typically send:

```http
GET /api/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...example...
```

As long as a stolen token remains valid, another party can replay it unless the system adds sender-constraining mechanisms such as properly implemented mTLS-bound tokens or DPoP. Therefore, protect tokens over TLS, constrain audience/scope and lifetime, and never write raw tokens into URLs, logs, or client-facing errors.

Consider this scenario:

- **09:00:** the server issues an access token with scopes `reports:read reports:delete` and `exp` at **09:15**.
- **09:03:** an administrator revokes the user's `reports:delete` permission.
- **09:04:** the client keeps using the same old access token to call `DELETE /api/reports/7`.
- **09:15:** the access token finally expires per `exp`; exact cutoff may be affected by configured validator clock skew.

If the Resource Server checks only **valid JWT signature, unexpired `exp`, and scope inside the token**, the 09:04 request may still succeed even though the database downgraded permissions at 09:03. This stems from a design where **permissions are snapshotted at token issuance time**.

**The problem has two separate axes:**

- **Token validity:** was the token issued by a trusted issuer? right audience? unexpired? not revoked?
- **Current permission for the action:** is the subject still active? still authorized for this specific resource/tenant? what if policies changed after issuance?

`Authentication` only answers which user or client was authenticated; current authorization must still be evaluated for the specific request and resource.

## 2. Timestamps That Must Be Understood Correctly

An illustrative JWT access token:

```json
{
  "iss": "https://idp.example.org",
  "sub": "user-42",
  "aud": ["https://api.example.org"],
  "iat": 1767229200,
  "nbf": 1767229200,
  "exp": 1767230100,
  "jti": "access-123456",
  "scope": "reports:read reports:delete",
  "authz_version": 7
}
```

The example timestamps illustrate structure only; do not infer a current date or real key from them.

| Claim | Meaning | What to Validate |
|---|---|---|
| `iss` | Token issuer | Trust only configured issuers and match exactly |
| `aud` | Target Resource Server | Token must be issued for **this API**; reject tokens for other apps |
| `sub` | Issuer-scoped subject, typically user or workload | Identifier must be scoped by namespace/tenant; do not infer from email |
| `iat` | Issued at, when the token was minted | Useful for version/timestamp-based revocation checks; does not prove token is still valid |
| `nbf` | Not before: time prior to which token must not be used | Reject before `nbf`, aside from controlled clock tolerance |
| `exp` | Expiration time: when the token ceases to be valid | Reject once verification time reaches/passes `exp` per validator |
| `jti` | Unique token ID if issued by the issuer | Useful for denylists; namespace by issuer and avoid collisions |
| `scope` or `scp` | Scopes granted at issuance time | Only one authorization input; can become stale |
| `authz_version` | **Custom** claim, not mandated by JWT/OAuth2 | Effective only if the API looks up and compares the current permission version |

Note: An access token can be a JWT or an opaque string; `exp` and `scope` in the table refer to **JWT claims**, or corresponding metadata returned by introspection. Never try to decode an opaque token as a JWT.

### TTL Length and Clock Skew

If a token is issued at `t0` with `exp=t0+900 seconds`, its token TTL is **15 minutes**. When the API allows clock skew tolerance, the effective acceptance window extends slightly later; this is why NTP sync and reasonable clock skew settings matter. **Never configure a huge clock skew** to paper over infrastructure drift, as that widens the window where stale tokens remain usable.

Do not conflate:

- **Access token TTL:** how long the credential can call APIs.
- **Refresh token TTL:** how long the credential can request new access tokens; usually longer, governed by different storage/rotation/revocation policies.
- **IdP session:** login state at the identity provider; IdP logout does not guarantee previously issued access tokens are invalidated immediately.
- **App/browser session:** may have its own cookies or server-side session; browser logout does not automatically erase a JWT already copied elsewhere.

`exp` is a **time-based expiration bound**, not a revocation list. A validly signed, unexpired JWT can still be rejected earlier if the system implements revocation checks or fresh permission checks.

## 3. Locally Verified JWTs vs. Opaque Token Introspection

### 3.1. Self-Contained JWT Access Tokens

The Resource Server can verify signatures using public keys/JWKs, check `iss`, `aud`, `exp`, `nbf`, and read authorities from claims. Advantages include minimal per-request network dependency on the Authorization Server, low latency, and easy scaling.

```text
Client ── Authorization: Bearer <JWT> ──► API
                                          │
                                          ├─ Verify signature / trusted JWK
                                          ├─ Validate iss, aud, exp, nbf
                                          ├─ Map scopes / authorities
                                          └─ Check application authorization
                                               │
                                               └─ May NOT query IdP on each request
```

If only those steps run, an old JWT with `roles=["ADMIN"]` still carries that claim after the DB downgraded the role. **Deleting a refresh token at the Authorization Server cannot alter the signature or payload of an already-issued JWT.**

### 3.2. Opaque Tokens + Introspection

An opaque access token is typically a string without directly readable user data. The Resource Server sends the token to a protected introspection endpoint and uses the Authorization Server's answer, for example:

```json
{
  "active": true,
  "sub": "user-42",
  "scope": "reports:read",
  "client_id": "web-client",
  "iss": "https://idp.example.org",
  "aud": "https://api.example.org",
  "exp": 1767230100
}
```

If the IdP tracks revocation and returns `"active": false`, the API rejects it. However, **not every introspection endpoint dynamically updates previously granted roles/scopes**; depending on design, it may simply return metadata captured when the token was issued. The API still needs current permission checks where policy demands them.

```text
Client ── Bearer opaque ──► API
                             │
                             └─ POST token → Authorization Server introspection
                                                   │
                                         active=true/false + metadata
                                                   │
                                      API enforces authorization
```

**Latency and availability:** introspection adds a network hop, depending on auth service availability and timeouts. If introspection results are cached, the system may continue seeing `active=true` until cache expiry even if the token was just revoked. Caches should be short-lived and never exceed token `exp`; highly sensitive endpoints may skip caching or add extra checks.

| Criterion | Locally Verified JWT | Opaque + Introspection |
|---|---|---|
| Per-request signature/token check | Local via trusted keys | Relies on AS/introspection endpoint |
| Per-request AS dependency | Usually none if keys are cached | Usually yes, unless introspection is cached |
| Early access token revocation | Needs denylist, version, live check, JWT introspection, or short TTL | AS can return inactive when revocation is supported |
| Permission changes | Stale claims persist until token becomes invalid | Metadata may also be stale; know IdP behavior and policy |
| Scale/latency | Usually better with local verification | Higher I/O/latency; caching delays state updates |
| AS outage | Already-issued JWTs can still verify | If unable to check, sensitive endpoints must fail closed |

Neither format solves revocation and permission updates automatically on its own. The choice trades off **risk window, network cost, consistency, and control**.

## 4. Token Revocation Under OAuth2 RFC 7009

RFC 7009 defines the **Token Revocation Endpoint**, allowing clients to ask the Authorization Server to invalidate an access or refresh token:

```http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<opaque-or-refresh-token>&token_type_hint=refresh_token
```

This is an **illustrative request**; exact paths and client authentication methods vary by IdP; never send secret tokens in URLs or logs. Revocation must use HTTPS. RFC 7009 requires supporting **refresh token** revocation and recommends **access token** revocation; depending on AS policy, revoking one token may revoke related tokens in the same grant.

**Distinguishing outcomes:**

1. Revoking a **refresh token** prevents using that credential to mint new access tokens. It **does not guarantee** that an old JWT access token checked offline by the API stops working immediately.
2. Revoking an **access token** at the Authorization Server is observed promptly by the API only if the API checks revocation, uses introspection, or shares state.
3. A successful HTTP status from the revocation endpoint **does not prove the token ever existed**; per spec, requests to revoke invalid tokens may also return 200 to prevent token probing.
4. If the Authorization Server spans multiple nodes or regions, replication lag may exist; docs and SLOs should state it.
5. Never rely on clearing a token from browser memory to "revoke" it; a stolen copy on another machine remains usable while valid unless the API enforces additional checks.

### 4.1. Refresh Token Rotation

For refresh tokens at risk of theft (especially in public clients), many systems use **rotation**: each successful refresh issues a new refresh token and invalidates the previous one. If an old token is reused against policy, the Authorization Server can detect replay and revoke the entire token family/grant.

Rotation protects the **new token issuance** window; it does not invalidate already-issued tokens inside the API immediately. Configure the real IdP properly, accounting for concurrent refresh calls and client characteristics. Do not force one universal TTL across all systems: evaluate risk, client type, UX, access duration, and organizational policy.

### 4.2. Exposed Token: Action Must Cover Both Sides

If an access token may have leaked:

- Stop the **exposed token** from calling APIs: revoke/introspect, denylist `jti`/token hash, bump session/version, or adjust permissions per implemented mechanisms.
- Stop minting **new tokens** with exposed credentials: revoke refresh tokens, grants/sessions, rotate keys, or force re-authentication as needed.
- Find the leak source: logs, browser storage, proxies, TLS errors, URLs, monitoring, or build artifacts.
- Audit requests during the exposure window and remediate any unauthorized actions.

For multi-user incidents, rotating signing keys is a heavy hammer that invalidates many JWTs, yet works only once all Resource Servers stop trusting the old key; normal key rotation often keeps the old key for unexpired tokens. Never use "rotate signing key" as a per-user revocation mechanism without planning its blast radius.

## 5. Permission Changes After Access Token Issuance

**Difference between authentication and authorization:** `JwtAuthenticationToken` is built once the JWT is valid; `GrantedAuthority` instances normally come from the token's `scope`/`scp`. `hasAuthority("SCOPE_reports:delete")` relies on the token's scope unless live permission checks exist. It does not automatically query the database to check if the user's role was just revoked.

Three common permission layers:

1. **OAuth2 Scope:** bounds what a client/token grant is permitted to do, e.g., `reports:read`. Scope is an upper bound on actions, not an absolute live entitlement list.
2. **Role/group:** e.g., `ROLE_MANAGER`, `GROUP_FINANCE`; can change in the IdP or local database after token issuance.
3. **Contextual data permissions:** e.g., "user-42 may approve invoice #815 in tenant A", "owner of report #10." Even if the token carries the right scope, per-resource access requires checking live data.

**Principle:** for sensitive actions, a request must satisfy **valid token**, **minimum scope**, **active account**, and **current permission on the resource/tenant**. A valid token is necessary, not sufficient.

### 5.1. Synchronization and Revocation Options

| Mechanism | Benefit | Trade-offs / Latency to Measure |
|---|---|---|
| Short access token TTL | Window for stale JWTs ends sooner | Not instantaneous; increases refresh traffic |
| Revoke refresh token/grant | Blocks minting new access tokens from old grant | Already-issued access tokens may work until `exp` |
| Per-request opaque introspection | AS can return `active=false` close to revocation | Depends on AS/network; caches retain stale state |
| `jti` or hash denylist | Precisely blocks specific JWTs before `exp` | API must check shared store; needs TTL cleanup, avoid `jti` collisions |
| `authz_version` / `session_version` | Invalidates an entire group of user/session tokens on bump | Token needs claim; API must fetch current version or invalidate cache |
| `revoked_before` via `iat` | Blocks tokens issued before an event timestamp | Needs precise clocks; same-second and in-flight issuance races |
| Live role/permission lookup | Downgrades take effect as soon as DB/cache reflects change | Adds I/O, needs cache/outage handling; doesn't block stolen tokens if permission remains |
| Push event invalidation | Events update caches across Resource Servers | Events can lag or drop; needs reconciliation and recovery |

In systems handling sensitive data, teams often **combine** layers: short TTLs as an upper bound, revocation for leaked tokens, refresh token rotation, and live permission checks on high-impact endpoints.

### 5.2. Two Types of Changes: "Permission Downgrade" vs. "Session Revocation"

If an admin **downgrades a user's role** while still allowing lower-privilege actions, a live permission check enforces the remaining permissions immediately, whereas a version-invalidation policy forces the user to acquire a fresh token. Both are valid depending on product requirements.

If a user account is **locked** or a session appears compromised, checking roles alone may not suffice: invalidate related sessions/tokens via version bumps, introspection/revocation, denylists, or combined measures.

### 5.3. Stale-Validity Window Formulas

With **locally verified JWTs relying only on `exp`**, the maximum window an old token can stay accepted after a permission change is roughly **remaining TTL + allowed clock skew**. For example, a 15-minute token whose permission changes at minute 3 leaves ~12 minutes (plus any clock skew).

With **introspection cached for 60 seconds**, the API may continue serving cached `active=true` for its remaining cache TTL; depending on when the entry was cached, update lag is roughly cache TTL plus propagation delay, while the token remains unexpired. Never claim "instant revocation" when a 60-second cache sits in front.

With **permission caches** on each API node, downgrades take effect only once caches refresh or invalidate. Total lag is bounded by every cache and policy-distribution hop along the request path.

## 6. Spring Security Resource Server: Validating JWT Issuer, Audience, and Time

Examples use Spring Boot 3.x, Spring Security 6.x, and Java 17+. This configures a **Resource Server accepting access tokens**; it does not issue tokens or expose a revocation endpoint.

### 6.1. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

### 6.2. application.yml

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: https://api.example.org
```

`issuer-uri` verifies tokens come from the right issuer; `audiences` ensures tokens were minted for this API. Resource Server fetches JWKs/metadata via issuer discovery when configured properly. Infrastructure must reach metadata/JWKS endpoints, or configure a matching trusted `jwk-set-uri`. Never configure a decoder to skip signature verification for testing convenience.

**Spring Security Resource Server defaults:** JWTs are checked for signatures, `exp`/`nbf`, and `issuer-uri` if configured. Signature verification relies on trusted algorithms and keys. Audience is guaranteed to be checked only when **you configure** `audiences` or an equivalent custom validator.

### 6.3. SecurityFilterChain Accepting Bearer JWTs

`src/main/java/com/example/security/ResourceServerConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports:read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

This configuration class works in a Spring Boot app with real dependencies and a real issuer. `SessionCreationPolicy.STATELESS` avoids storing Authentication in HTTP sessions; bearer tokens are evaluated per request. `hasAuthority("SCOPE_reports:read")` reflects **the token's scope**, not whether the user is still authorized for a specific database report.

To run in a Spring Boot project with `@SpringBootApplication` and matching endpoints: `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Obtain a valid access token from a trusted Authorization Server; the example generates no tokens and has no fixed HTTP output without a live IdP, keys, and endpoints.

**Common mistakes:**

- API accepting an OIDC login **ID Token** instead of an **access token** issued for this resource: verify token type/audience/protocol; never use ID Tokens to call APIs just because they are JWTs.
- Only Base64-decoding the payload while skipping signature verification or trusting disallowed `alg` headers: vulnerable to forged tokens.
- Checking only `exp` while skipping `iss` and `aud`: allows tokens from other issuers/clients.
- Skipping `scope` or data-level checks: token is valid yet unauthorized for the action.

## 7. Spring Security: Checking Live Permissions Beyond Token Scopes

Suppose `/api/reports/**` requires `reports:read`, yet report #815 belongs to tenant A and `user-42` was just removed from the read group. `hasAuthority("SCOPE_reports:read")` alone would still allow the call because the claim inside the token hasn't changed.

**Solution:** enforce method/request authorization at the business layer using **current permissions** from your data store. The design below is **project integration code** requiring a real `CurrentPermissionRepository` and application endpoints/services; it is not a standalone runnable Java file.

```java
package com.example.security;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("liveReportPermission")
public class LiveReportPermission {

    private final CurrentPermissionRepository repository;

    public LiveReportPermission(CurrentPermissionRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long reportId) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        var jwt = jwtAuth.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        // May also need tenant, owner, and current user active status.
        return repository.isCurrentlyAllowed(
            jwt.getIssuer().toString(), jwt.getSubject(), reportId);
    }
}
```

`CurrentPermissionRepository` in the example is an **application-defined business interface**, for instance:

```java
package com.example.security;

public interface CurrentPermissionRepository {
    boolean isCurrentlyAllowed(
        String issuer, String subject, long reportId);
}
```

Production implementations must verify active user status, tenant, current report permissions, and DB policies, never trusting `reportId` alone as ownership. Provide a bean implementing this interface. Deny access when unable to verify permissions on sensitive endpoints; never return `true` on cache/DB failures.

Enable method security in Spring configuration:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

Imports: `org.springframework.context.annotation.Configuration` and `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`. Then on a **Spring-managed service** (not self-invoked within the same class), apply:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports:read') " +
    "and @liveReportPermission.canRead(authentication, #reportId)"
)
public ReportDetails readReport(
        @P("reportId") long reportId) {
    return repository.loadAuthorizedReport(reportId);
}
```

This snippet illustrates service-layer security checks, requiring `org.springframework.security.access.prepost.PreAuthorize` and `org.springframework.security.access.method.P`. `ReportDetails`/`repository` are project-specific domain types/beans, so the snippet cannot compile standalone. If production uses a repository query combining permission and data loading, check within the same query/transaction where appropriate to limit TOCTOU races; also consider permission changes happening mid-request.

**Explanation:** the same unexpired JWT still passes through `isCurrentlyAllowed` to fetch the latest permissions. Once an admin revokes access, the next request is blocked after the source of truth/cache updates. Token `scope` remains useful as a baseline bound, yet does not replace dynamic business authorization.

### Consistency of the Permission Store

If using Redis or a permission cache, implement reliable invalidation, clear TTLs, tenant-isolation safeguards, and fail-closed behavior. For financial, administrative, or sensitive data APIs, authoritative DB lookups or policy engines with tight revocation SLOs may fit better than long-lived caches. Never load permissions at login and cache them indefinitely.

## 8. Spring Security: Using Opaque Introspection When Centralized Revocation Is Needed

If the Authorization Server supports standard RFC 7662 introspection, the Resource Server can use opaque access tokens and verify active state:

`src/main/resources/application.yml` (an **alternative to the JWT config** in section 6.2; do not mix both in the same simple Resource Server demo):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

In `SecurityFilterChain`, replace `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` with:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

`Customizer` is imported as in the JWT example. Configure the introspection endpoint and credentials securely via environment/secret manager, TLS, and timeouts; each check must distinguish `active=true` from `active=false`. Never assume a token is valid just because the endpoint returned HTTP 200: **the introspection body** determines whether the token is active.

By default, Spring Security maps `scope` from introspection to `SCOPE_...` authorities. The introspection server must authenticate the Resource Server and minimize returned data. If caching responses at the client or an intermediary, define the effective revocation lag and keep cache TTL shorter than token expiration.

Nothing prevents a Resource Server from using **JWTs while still introspecting** or checking a dedicated revocation store. That is an architectural choice requiring real custom validation/introspection. If a request cannot confirm the token is active on a route requiring introspection, reject it rather than silently accepting all tokens.

## 9. Revocation and Permission-Version Checking Patterns

Systems needing to invalidate issued tokens before `exp` can use:

### 9.1. Token ID Denylist

The Authorization Server mints JWTs with unique `jti` values. Upon revocation, store `(issuer, jti)` or a securely computed token hash in Redis/shared storage. The Resource Server must check the denylist on every token/request and reject on match.

- Set denylist TTL to `exp` plus necessary clock margin to prevent unbounded table growth.
- Namespace by issuer to avoid `jti` collisions across different issuers.
- If not all tokens carry `jti`, define another safe identifier or reject non-compliant tokens.
- Never keep the denylist only in single-node local memory while other nodes continue accepting the token.
- If caching "token not revoked" results, that introduces denylist lag; invalidate or set an appropriate TTL.

### 9.2. Permission Version / Session Version

At issuance, the Authorization Server embeds an internal claim such as `authz_version=7` or `session_version=3`. The permission/state store holds the latest version. When a user is downgraded or a session is locked, bump the version to 8 or 4. The Resource Server compares the claim against current state and rejects mismatched versions.

- With **`authz_version`**, changing roles can invalidate all older user tokens; the user needs a new token after policy updates.
- With **`session_version`**, all tokens tied to a specific session/device can be revoked if tokens and storage share a secure session ID.
- Across multiple issuers/tenants, namespace version keys by issuer, subject/tenant/client as appropriate.
- **Adding the claim to the JWT is not enough**: the API must perform the lookup/comparison; otherwise stale versions sit unchecked in valid JWTs.
- Do not rely solely on `iat >= revoked_before` when clock drift, second-level rounding, skew, or concurrent token issuance can leave gaps; monotonically increasing integer versions are easier to reason about in many cases.

### 9.3. Where to Place the Check

Version/denylist checks can live in a custom `OAuth2TokenValidator<Jwt>` attached to `JwtDecoder`, in an appropriate `AuthenticationProvider`/authorization component, or at the policy layer; decide clearly whether a token is considered **invalid (401)** or valid yet **lacking permission (403)**. Revoked tokens are usually best rejected as invalid credentials before issuing an Authentication. Simply lacking permissions on a valid token fits HTTP 403 better.

Never place checks only in a post-controller filter or only on the login screen; API callers can present tokens directly without touching the UI.

## 10. Java 17: Simulating Lifetime, Revocation, and Permission Changes

The standalone program below illustrates **state checks** on a hypothetical token whose signature is already assumed verified. It does not generate real JWTs, replace Spring Security, or simulate distributed servers. Save as `BearerTokenPolicyDemo.java`:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class BearerTokenPolicyDemo {

    record Token(
        String subject,
        String tokenId,
        long permissionVersion,
        Instant notBefore,
        Instant expiresAt
    ) {}

    static boolean accepted(
        Token token,
        Instant now,
        Map<String, Long> currentVersions,
        Set<String> revokedIds
    ) {
        return !now.isBefore(token.notBefore())
            && now.isBefore(token.expiresAt())
            && !revokedIds.contains(token.tokenId())
            && token.permissionVersion()
                == currentVersions.getOrDefault(token.subject(), -1L);
    }

    public static void main(String[] args) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        Map<String, Long> versions = new HashMap<>();
        Set<String> revokedIds = new HashSet<>();
        versions.put("user-42", 1L);

        Token original = new Token(
            "user-42", "jti-old", 1L, issued, issued.plusSeconds(300));

        System.out.println("Initially: " +
            accepted(original, issued.plusSeconds(10), versions, revokedIds));

        // User permissions downgraded: version changes immediately in the data store.
        versions.put("user-42", 2L);
        System.out.println("After permission change: " +
            accepted(original, issued.plusSeconds(20), versions, revokedIds));

        Token refreshed = new Token(
            "user-42", "jti-new", 2L, issued, issued.plusSeconds(300));

        System.out.println("New token: " +
            accepted(refreshed, issued.plusSeconds(30), versions, revokedIds));

        revokedIds.add("jti-new");
        System.out.println("After revocation: " +
            accepted(refreshed, issued.plusSeconds(40), versions, revokedIds));

        System.out.println("At expiry: " +
            accepted(original, issued.plusSeconds(300), versions, revokedIds));
    }
}
```

Compile and run with JDK 17+:

```bash
javac BearerTokenPolicyDemo.java
java BearerTokenPolicyDemo
```

Exact stdout:

```text
Initially: true
After permission change: false
New token: true
After revocation: false
At expiry: false
```

**Why is this example useful?** When `permissionVersion` increments, the old token immediately stops passing even before `expiresAt`. When the new token is added to the revocation list, it is rejected immediately before `exp`. At `exp`, the token is no longer valid under `now.isBefore(expiresAt)`.

**Demo limitations:** `HashMap`/`HashSet` live in one JVM's memory, not surviving restarts or multi-node runs; real apps use a reliable distributed store or database. `Token` in the demo is already assumed authenticated; production must **verify signature/issuer/audience** with Spring Security before applying these policies. The demo also omits multi-issuer handling, clock skew, and refresh tokens; never copy this logic directly as a JWT validator without all those controls.

## 11. HTTP 401/403 and Client Behavior When Tokens Are Invalid

| Scenario | Primary Decision | Expected Response in Standard API |
|---|---|---|
| No bearer token on endpoint requiring auth | Unauthenticated | 401 (challenge) |
| Forged token, bad signature/`iss`/`aud` | Invalid credential | 401 |
| Past `exp`, before `nbf` | Time-invalid credential | 401 |
| Revoked/inactive token | Credential no longer valid | 401 |
| Valid token missing `reports:read` | Insufficient scope/permission | 403, may specify `insufficient_scope` per RFC 6750 |
| Valid token, right scope, DB downgraded report #815 access | Lacks current data permission | 403 |
| Introspection required yet AS times out | Cannot verify token | Fail closed; exact HTTP status (401/503) per policy/error handler, never accept token |
| Revoked refresh token | Grant cannot mint new tokens | Usually requires user re-authentication; response per token endpoint |

Do not program clients to retry infinitely on 401 when a token is revoked; attempt at most one controlled refresh if the grant remains valid, handle `invalid_grant`, and guide the user to re-authenticate when needed. Never confuse 403 insufficient permission with 401 needing refresh; repeated refreshes will not restore permissions revoked by an admin.

## 12. Lifecycle Behavior Testing

### 12.1. Minimum Tests for JWT Validation

- Valid, unexpired token with right issuer/audience/scope: enters matching endpoint if business permissions also hold.
- Flip one byte in JWT payload/signature: rejected.
- Token from a different issuer or with another API's audience: rejected.
- Token past `exp`: 401; token with future `nbf`: rejected per validator/clock skew.
- Unexpired token present in denylist: no Authentication granted.
- Token with older `authz_version` than DB: rejected, even with valid signature and `exp`.
- Unexpired token after user removed from team/tenant: requests touching team/tenant resources denied by live permission check.
- Token with only `reports:read` calling endpoint requiring `reports:delete`: 403.
- Locked user: all related access tokens blocked per policy, refresh grants invalidated.
- In multi-session systems, revoking one session must not accidentally invalidate other sessions unless intended by policy.

### 12.2. Testing Introspection and Caching

- Introspection returns `active=true` and valid attributes: Resource Server grants only accepted permissions.
- Introspection returns `active=false`: fails authentication.
- Introspection returns HTTP 200 yet JSON lacks `active=true`: never allow by default.
- AS timeout, 5xx, TLS failure, or wrong client credentials: fail closed; operational alert triggers.
- Revoke token immediately after API caches `active=true`: measure exact time until API begins rejecting; compare with SLO.
- Once `exp` arrives, cache must not extend token validity.
- Login/refresh immediately after permission downgrade: new token must not carry revoked permissions.
- Two API nodes running concurrently: denylist/version updates take effect consistently; track propagation lag.

### 12.3. The Crucial Test: Changing Permissions While a Token Is Unexpired

An integration test should follow this sequence:

1. Issue a token to a user with `reports:delete` (or equivalent resource permission).
2. Call the API to delete a test report, verifying it succeeds under initial policy.
3. Revoke the user's role/permission in the source of truth; **do not issue a new token**.
4. Call the API again with **the exact same old token, still before `exp`**.
5. For endpoints requiring immediate enforcement, the call must be rejected. If still allowed, the system uses stale authorization; inspect token claims, resource permission caches, and revocation integration.
6. Measure elapsed time from the permission change until the first blocked old request; record SLO/risk-window bounds.
7. Repeat across each API node, with warm caches, flaky network conditions, and tokens minted just before revocation.

If a system **intentionally** updates permissions only upon token re-issuance, document that limitation, pick an acceptable TTL, and classify which endpoints tolerate stale permissions. Never claim real-time revocation while still accepting old JWTs until `exp`.

## 13. Operations: Required Policies and Audit Trails

1. **Choose TTLs based on risk.** Profile-read endpoints may tolerate short windows; money transfers, deletions, and admin actions generally require near-real-time state and permission checks. No single universal TTL fits every product.
2. **Separate access and refresh tokens.** Store refresh tokens securely per client type with appropriate rotation/reuse detection; revoke on logout, suspected exposure, or user lock.
3. **Defend against replay.** Copied Bearer tokens can be replayed; consider mTLS/DPoP for high-risk contexts alongside expiration/revocation.
4. **Operate key rotation cleanly.** Resource Servers must track JWKS rotation; never delete old keys unannounced or retain old keys forever. Key rotation does not equal user revocation.
5. **Bound all caches.** Introspection, permission, denylist, and security-version caches need TTLs/invalidation and error handling; measure real propagation lag.
6. **Never log secrets.** Avoid logging bearer tokens, refresh tokens, authorization codes, cookies, or private signing keys. For token correlation, use an appropriately hashed reference and restrict log access.
7. **Maintain audit trails.** Record issuance, revocation, refresh reuse, permission downgrades, session invalidation, 401/403 events, cache refreshes, and correlation IDs; avoid dumping full PII claims into general logs.
8. **Fail closed on sensitive data.** When revocation/permission services are unavailable, never fall back to allowing access. Return appropriate operational statuses and retry behavior instead of treating every error as a bad password.
9. **Enforce multi-tenant isolation.** Bind `sub` to the right issuer/tenant; a token for tenant A must never grant access to tenant B even with identical users/scopes.
10. **Exercise incident drills.** Simulate leaked tokens, disabled users, and stripped admin roles to verify exactly when old requests get blocked across all nodes.

## 14. Knowledge Self-Check

**Question 1.** Why does changing a role from ADMIN to USER in the database not automatically invalidate a JWT holding `ROLE_ADMIN`?  
**Answer:** Signatures and claims inside an already-issued JWT do not change by themselves. A Resource Server verifying offline may continue accepting the token until `exp` unless it checks live permissions/versions/revocation.

**Question 2.** Does revoking a refresh token guarantee that a JWT access token held by the client immediately stops working?  
**Answer:** No. Revoking the refresh token stops minting new access tokens from that grant, while old JWTs can keep working when the Resource Server only verifies locally.

**Question 3.** Which mechanisms should be considered to block an access token immediately after revocation?  
**Answer:** Up-to-date opaque introspection, `jti` denylists, security/authz versions, custom validation, or live state checks; combined with short TTLs and appropriate caching policies.

**Question 4.** Why can a 5-minute introspection cache undermine centralized revocation?  
**Answer:** The API may retain a cached `active=true` response after the AS revoked the token until the cache expires or invalidates; that lag must be accounted for.

**Question 5.** What is the difference between a scope inside a JWT and permission to read report #815?  
**Answer:** Scope reflects permissions granted to the token; permission for report #815 also depends on the current account, tenant, ownership, and business rules.

**Question 6.** When should 401 be returned vs. 403?  
**Answer:** 401 when the token is missing, invalid, expired, or revoked per policy; 403 when the token authenticated successfully yet lacks sufficient permissions for the resource. Introspection service outages need dedicated error/fail-closed policies.

**Question 7.** What happens if `authz_version` is incremented in the database yet the Resource Server never reads the version?  
**Answer:** It has no effect; the old JWT still carries the old version while the API never compares and rejects it.

## References

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): bearer token properties, `Authorization: Bearer`, `invalid_token`, and `insufficient_scope`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation endpoint, refresh/access tokens, and revocation policy.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): `active`, metadata, caching, and security implications.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer/audience, timestamps, and scope mapping.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and `active`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and dynamic authorization.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): protecting access/refresh tokens, replay, and OAuth security.
