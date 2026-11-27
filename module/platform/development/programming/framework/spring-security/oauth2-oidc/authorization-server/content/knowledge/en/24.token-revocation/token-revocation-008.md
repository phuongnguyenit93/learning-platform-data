# Combining TTL, Introspection, or Supplementary Mechanisms to Enforce Revocation

## Lesson Objectives

In the **Revocation** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson examines how to turn a **token revocation** operation into an effective rejection decision at the **Resource Server**. The context is designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**.

There is a decisive difference:

> **The Authorization Server recording that a token was revoked does not mean every Resource Server will immediately reject the token.** The outcome depends on token format, how APIs validate tokens, caching, synchronization delay, and remaining token lifetime.

With **opaque/reference access tokens**, the Resource Server typically queries the **Token Introspection Endpoint** to check whether the token is still active. With self-contained **JWT access tokens**, the Resource Server may verify only the signature and claims such as `iss`, `aud`, and `exp` without contacting the Authorization Server. In that case, revocation state in the Authorization Server's database does not automatically propagate into signature verification.

After this lesson, you will be able to:

- Distinguish **TTL/expiration**, **revocation**, **introspection**, **denylists**, **session epochs**, and **refresh token rotation**.
- Understand RFC 7009 and RFC 7662 requirements; never treat HTTP 200 from the Revocation Endpoint as proof that APIs stopped accepting a JWT.
- Choose revocation strategies for opaque tokens, self-contained JWTs, refresh tokens, and ID Tokens/login sessions according to security goals.
- Configure Spring Authorization Server with `OAuth2AuthorizationService`, `OAuth2TokenRevocationEndpointConfigurer`, `OAuth2TokenIntrospectionEndpointConfigurer`, and `TokenSettings`.
- Configure Spring Security Resource Server to validate tokens via introspection or JWT plus revocation-state checks.
- Design TTLs and caches to bound **the maximum window a token remains accepted after a revoke event**.
- Coordinate revoking refresh tokens, access tokens, authorization grants, client credentials, and user sessions.
- Design supplementary mechanisms such as a revoked-`jti` store, grant/session versions, event propagation, and dynamic permission checks.
- Test restarts, caching, multiple instances/regions, disconnects, race conditions, and signing-key incidents.

**Running Scenario:** An application `employee-portal` logs in and receives a 15-minute JWT access token along with a 14-day refresh token. The user clicks "Log out all devices." The Authorization Server revokes the refresh token; however, `inventory-api` keeps accepting the old JWT if it only verifies signature and `exp`. We will build a policy to measure and shrink this window.

## 1. Distinguishing Natural Expiration from Proactive Revocation

### 1.1. TTL Is Not Revocation

**TTL (time-to-live)** is how long a token is allowed to live by policy. In JWTs, expiration is typically represented by the `exp` claim. A token expires naturally when its time is up, even without any revocation action.

**Revocation** is a decision by the Authorization Server or an administrator that a token/authorization may no longer be used **before its natural expiration**: for instance, user logout, lost device, detected refresh token leak, locked account, password change, or permission change.

| Scenario | Natural Expiration | Revocation |
|---|---|---|
| Token lives 5 minutes, past `exp` | Unusable | No revoke event needed |
| JWT has 12 minutes left, user logs out | Still unexpired | Requires a mechanism for the Resource Server to learn revocation state to reject early |
| Refresh token lives 14 days, revoked on day 2 | Unexpired | Token Endpoint must reject subsequent refreshes |
| Client disabled, issued JWT has 10 minutes left | `exp` not reached | Offline JWT validator does not automatically know the client was disabled |
| Signing key compromised | `exp` may be far away | Needs incident response; cannot simply wait for TTL if risk is high |

**Revocation has two sides:** blocking **new token issuance** (especially via refresh tokens) and blocking **use of already-issued tokens** at APIs. A system implementing only the first side does not achieve "immediate logout across all APIs."

### 1.2. Tokens Have Different Lifecycles

- **Access token:** credential sent to Resource Servers. Needs checks for `exp`, audience, scope, issuer, and potentially revocation state.
- **Refresh token:** credential used at the Token Endpoint to obtain new access tokens. Needs persisted/queryable state bound to client and authorization/grant; rotation/reuse detection can revoke the entire token family.
- **ID Token:** login assertion for an OIDC Client; not an access token for calling APIs. Revoking access/refresh tokens does not mean an already-issued ID Token disappears from clients.
- **Authorization grant/consent:** long-lived authorization or approved consent state; can affect future token issuance.
- **Login/session cookie:** browser session state; deleting cookies or logging out of the app does not automatically ensure previously issued access tokens are rejected at Resource Servers.

Designing "logout" requires explicitly defining which layers are invalidated, where, and within what timeframe.

## 2. Token Revocation Contract per RFC 7009

RFC 7009 defines an endpoint for clients to ask the Authorization Server to invalidate a token they no longer need.

### 2.1. Valid Requests

The client sends an HTTP POST over HTTPS with an `application/x-www-form-urlencoded` body. `token` is **required**, while `token_type_hint` is **optional** and only aids lookup optimization:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_CREDENTIALS_BASE64>

token=<REFRESH_TOKEN_SAMPLE>&token_type_hint=refresh_token
~~~

`<REFRESH_TOKEN_SAMPLE>` is a placeholder, not a real credential. Authorization Server configuration can change the path; this example uses `/oauth2/revoke`, common in Spring Authorization Server.

RFC 7009 requires authenticating confidential clients and verifying the token was issued to that client before revoking. Never let callers arbitrarily revoke another client's token merely by knowing the token value. Public clients must be handled per authentication/binding policy and framework support; never use an unauthenticated client ID to allow arbitrary system-wide revocation.

### 2.2. Success Responses Do Not Confirm Prior Token Existence

RFC 7009 Section 2.2 specifies HTTP **200 OK** when revocation succeeds **or** the client submits an invalid/nonexistent token:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
~~~

The body is normally empty; clients do not read a body to determine success. This mitigates token-existence oracles.

Distinguish:

| Situation | Result at Revocation Endpoint |
|---|---|
| Token belongs to client, active | 200 if revocation succeeds |
| Token already revoked earlier | 200 |
| Token invalid/not found, valid caller request | 200 |
| Client authentication fails | OAuth2/client authentication error, never fake 200 |
| Token belongs to another client or permission check fails | Deny caller authority; return appropriate error after security checks |
| Actual token type unsupported for revocation | May return `unsupported_token_type` per RFC 7009 |
| Service unavailable (503) | Client must assume the token **may still exist**, retrying only per `Retry-After`/backoff |

Do not turn `token_type_hint=refresh_token` into proof that the token is actually a refresh token. If the hint is wrong, the server must still perform a valid fallback lookup per the standard.

### 2.3. Cascade Revocation Is Not an Immutable Assumption

Per RFC 7009:
- Implementations **MUST** support revoking refresh tokens.
- Implementations **SHOULD** support revoking access tokens.
- When revoking a refresh token and the server supports access-token revocation, the server **SHOULD** also invalidate access tokens issued from the same authorization grant.
- When revoking an access token, the server **MAY** revoke the related refresh token.

**MUST/SHOULD/MAY does not mean every implementation shares the same cascade policy.** Inspect and test actual behavior for your Spring Authorization Server version, token format, authorization store, and remaining live tokens. Notably, even if access token metadata is marked invalidated at the Authorization Server, **offline JWT Resource Servers do not see that metadata automatically**.

## 3. Three Layers That Must Coordinate for Effective Revocation

The model comprises:

1. **Decision layer:** who is permitted to revoke tokens, why, and at what scope.
2. **State storage layer:** Authorization Server persists invalidated token/authorization state; events/denylist/session version if applicable.
3. **Enforcement layer:** Token Endpoint rejects refreshes; Resource Servers reject revoked access tokens according to the chosen validation mechanism.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User/Admin/Client
    participant AS as Authorization Server
    participant DB as Authorization Storage
    participant R as Resource Server
    U->>AS: Revoke refresh/access token
    AS->>DB: Mark invalidated (and cascade per policy)
    DB-->>AS: Commit
    AS-->>U: 200 OK
    U->>R: API call with old access token
    alt R uses introspection
        R->>AS: POST /oauth2/introspect
        AS->>DB: Check active / invalidated / exp
        AS-->>R: active=false
        R-->>U: 401 invalid_token
    else R only verifies JWT offline
        R->>R: Verify JWS + iss + aud + exp
        R-->>U: May still return 200 if JWT is unexpired
    end
~~~

This is why "instant revocation" cannot be promised solely because the endpoint returned 200. You must determine which branch each Resource Server runs.

## 4. Choosing Token Formats: Self-Contained JWT vs. Opaque/Reference

In Spring Authorization Server, `TokenSettings.accessTokenFormat(...)` controls a `RegisteredClient`'s access token format:

- `OAuth2TokenFormat.SELF_CONTAINED`: typically a JWT signed by `JwtGenerator`.
- `OAuth2TokenFormat.REFERENCE`: an opaque access token, typically generated by `OAuth2AccessTokenGenerator`.

### 4.1. Comparison Table

| Criterion | Self-Contained JWT, Offline Verification | Opaque/Reference + Introspection |
|---|---|---|
| Token acceptance decision | Resource Server verifies signature/claims | Authorization Server returns `active` via introspection |
| Sees fresh revocations at AS | **Not automatically** | When requests hit introspection and receive fresh state |
| API latency | Low, no per-request AS call | Can increase due to network/AS/DB |
| AS dependency during API calls | Typically none | Yes, unless introspection is cached |
| Token validity window after revoke | Potentially until `exp` without supplementary checks | Depends on cache, propagation, and AS availability |
| Claim exposure | JWT payload is decodable (must not hold secrets) | Token string is opaque; metadata stays via AS |
| High throughput | Strong for high-traffic APIs | Needs capacity planning, rate limiting, and tuning caches |
| Low-latency revocation | Needs denylist/state check/introspection | Achievable with small cache or direct introspection |

**Opaque tokens do not automatically "revoke instantly" if Resource Servers cache `active=true` for too long.** Conversely, JWTs can be introspected instead of verified offline if server-side state checking is desired.

### 4.2. Choosing by Risk

- Low-sensitivity internal read APIs tolerating a few minutes' delay: short-TTL JWT with offline verification; residual window may be acceptable.
- Financial/administrative APIs where logout/disable must act fast: opaque + introspection, or JWT + online revocation check/denylist.
- Very high-traffic APIs with tight latency SLAs: short-TTL JWT plus appropriate caching/versioning/events; balance consistency and risk.
- Ultra-sensitive data with per-request changing conditions: token validity alone is insufficient; add **dynamic authorization checks** at APIs.

## 5. TTL: Shrinking the Exposure Window, Not Remote Deletion

TTL is the first and simplest line of defense for self-contained tokens. If an access token lives 5 minutes, after revoking the refresh token, an old JWT can still be accepted by offline APIs for at most roughly 5 minutes from issuance, plus validator clock-skew tolerance.

### 5.1. Practical Formula

Let:
- `t_revoke`: timestamp when the revocation event is confirmed.
- `exp`: access token expiration timestamp.
- `skew`: clock tolerance accepted by the Resource Server.
- `L`: state synchronization/policy update delay, if any.

For an **offline JWT without revocation checks**:

~~~text
Residual window (approx.) =
    max(0, exp - t_revoke + accepted_clock_skew)
~~~

If the token was just issued, the residual window is nearly the access-token TTL plus clock skew. If the token is near expiry, the window is shorter.

Example:

| Access Token TTL | Revoked After Issuance | No Online Check | Expected Outcome |
|---|---|---|---|
| 15 minutes | After 2 minutes | Residual nearly 13 minutes (+skew) | Old JWT still usable |
| 5 minutes | After 2 minutes | Residual nearly 3 minutes (+skew) | Shorter window |
| 60 seconds | After 20 seconds | Residual nearly 40 seconds (+skew) | Requires higher Token Endpoint traffic |

These numbers are illustrative, not an SLA guarantee. If validators have clock skew, caching, network delays, or bugs, reality can differ.

### 5.2. Configuring TTL with TokenSettings

Example registering a confidential client in Spring Authorization Server:

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofDays(7))
        .reuseRefreshTokens(false)
        .build();
~~~

Attach `tokenSettings` to the `RegisteredClient`. This is a configuration snippet, not a full application. `reuseRefreshTokens(false)` enables rotation per framework policy; test persistence and concurrent refresh requests.

**Never alter `expires_in` in the Token Response via a success handler to "change TTL."** True TTL is governed by the token generator/provider and token settings; modifying only the response causes clients and Resource Servers to disagree on expiration.

### 5.3. Trade-offs of Overly Short TTLs

Short TTLs shrink the leaked-token window, yet:
- Increase token/refresh request traffic.
- Risk token stampedes when many workers refresh concurrently.
- Increase dependency on Authorization Server/KMS/DB.
- Can hurt mobile/offline clients.
- If a refresh token is stolen, shortening access token TTL alone does not stop the attacker from minting new tokens.

Pair short TTLs with refresh token rotation, client authentication/sender-constraining, and rate controls.

## 6. Introspection: Checking Token State at Use Time

RFC 7662 defines `POST /oauth2/introspect`. The Authorization Server returns `active=true` when the token is active and the caller is authorized to inspect it; it returns `active=false` for expired, revoked, or nonexistent tokens, or when the caller is not permitted to inspect state.

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <RESOURCE_SERVER_CREDENTIAL>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN_SAMPLE>&token_type_hint=access_token
~~~

Result after revocation:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
~~~

A Resource Server configured for introspection relies on fresh state from the AS rather than offline signature checks alone.

### 6.1. Configuring Spring Security Resource Server Opaque Tokens

On the **Resource Server**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: inventory-api-introspector
          client-secret: ${INVENTORY_INTROSPECTION_SECRET}
~~~

Credentials must come from a secret manager; never commit real secrets to the repository. Introspection callers must be authenticated and authorized per token audience/resource/tenant rather than letting every API inspect every token.

### 6.2. Can JWTs Be Introspected?

**Yes.** Spring Security OAuth2 Resource Server opaque-token support can send JWT strings to the introspection endpoint. The config name `opaquetoken` reflects the **remote validation strategy**, not a requirement that the token itself be opaque.

This helps when you want JWTs yet Resource Servers need near-real-time revocation visibility. The Authorization Server must track JWT state sufficiently for introspection to recognize the token, and each JWT must be verified/matched against stored authorizations. Never assume an AS can introspect arbitrary JWTs issued elsewhere.

### 6.3. Introspection Caching Determines the SLA

Suppose the Resource Server cached:

~~~json
{
  "active": true,
  "exp": 1794861000,
  "scope": "inventory.read"
}
~~~

If the cache stays valid for 30 seconds, the API can keep accepting the token for 30 seconds after revocation, even though direct AS calls already return `active=false`.

Estimate:

~~~text
Observed revocation delay <=
    state propagation delay
    + remaining positive introspection-cache TTL
    + processing/network delays
~~~

This is an **architectural estimate**, not a hard bound when clock drift, network partitions, or non-compliant caches occur.

Principles:
- Never cache `active=true` past the token's `exp`.
- Pick positive cache TTLs below your revoke SLA; e.g., for a sub-30-second target, a 5–10 second cache leaves headroom for propagation/jitter.
- Never use unbounded caches.
- Cache keys must isolate issuer, token identity, and caller/resource context so one API does not reuse another's response.
- Active event-driven cache purging helps, but still keep a TTL fallback.
- Be cautious with negative caching if token/client state can flip back; align with business rules and risk.
- Never log raw tokens when cache keys use hashes/fingerprints.

### 6.4. AS Unreachable: Fail-Open or Fail-Closed?

When a Resource Server needs introspection and the AS/DB is unavailable, that is an **unknown state error**, not evidence that the token is active. For high-security APIs, **fail closed**: reject or return an appropriate service error instead of accepting an unverified token.

An unexpired cached `active=true` entry may be used if policy explicitly permits a short stale window; treat that as an explicit risk decision. Never let an outage become "all bearer tokens are valid."

## 7. Revocation Endpoint and State in Spring Authorization Server

### 7.1. Standard Components

Spring Authorization Server 1.x provides:

- `OAuth2TokenRevocationEndpointFilter`: receives revoke requests.
- `OAuth2TokenRevocationAuthenticationConverter`: parses requests.
- `OAuth2TokenRevocationAuthenticationProvider`: executes revocation.
- `OAuth2AuthorizationService`: looks up and saves authorization/token state.
- `OAuth2Authorization.Token`: stores metadata such as invalidation; `isActive()` considers expiration and invalidated state.
- `OAuth2TokenRevocationEndpointConfigurer`: hooks converters/providers/success/error handlers.

Default configuration is usually sufficient to revoke tokens per the framework. **Do not write a duplicate `/oauth2/revoke` controller** without clear requirements and full RFC 7009 test coverage.

### 7.2. Endpoint and Issuer Configuration

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .tokenEndpoint("/oauth2/token")
            .tokenRevocationEndpoint("/oauth2/revoke")
            .tokenIntrospectionEndpoint("/oauth2/introspect")
            .build();
}
~~~

This is an illustrative bean; configuration APIs/paths must match your version. Public issuers/endpoints must use HTTPS and reflect real ingress/reverse-proxy routes. Never set the issuer to an internal pod name.

SecurityFilterChain skeleton example:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(
        HttpSecurity http) throws Exception {

    var server = OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(server.getEndpointsMatcher())
        .with(server, authServer -> authServer
            .tokenRevocationEndpoint(revocation -> {
                // Keep default converters/providers/response handlers.
            })
            .tokenIntrospectionEndpoint(introspection -> {
                // Apply caller-to-token policy when needed.
            }))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated());

    return http.build();
}
~~~

This example omits remaining required beans (`RegisteredClientRepository`, `OAuth2AuthorizationService`, JWK/encoders, login chain). Do not mix imports from Spring Authorization Server 1.x with similarly named classes from other Spring Security generations.

### 7.3. Persistence Must Be Shared Across Instances

`OAuth2AuthorizationService` must persist token state and invalidation metadata durably. If production runs separate per-node `InMemoryOAuth2AuthorizationService` instances:

- Node A can revoke while Node B still holds an unrevoked authorization.
- Introspection behind a load balancer can return conflicting `active` states per node.
- Restarts wipe state and break refresh token handling.
- Token/Revocation/Introspection endpoints disagree on authorizations.

Production should use proper persistent/shared storage, such as JDBC configured with migrations, isolation, backups, and consistent access. If building a custom repository/service, support `findByToken(...)`, `save(...)`, invalidation metadata, concurrency, and lookups for both refresh and access tokens as used by the providers.

### 7.4. Distinguishing AS State from RS Decisions

Example inspecting a stored access token:

~~~java
OAuth2Authorization authorization =
        authorizationService.findByToken(tokenValue, OAuth2TokenType.ACCESS_TOKEN);

if (authorization == null || authorization.getAccessToken() == null) {
    // Token is not recognized by the Authorization Server.
    return;
}

OAuth2Authorization.Token<OAuth2AccessToken> stored =
        authorization.getAccessToken();

boolean activeAtAuthorizationServer = stored.isActive();
boolean revoked = stored.isInvalidated();
~~~

This Java snippet illustrates reading state, not a complete controller/endpoint. Keep `tokenValue` out of logs. `activeAtAuthorizationServer=false` matters only to components that actually **query AS state**; an offline JWS/JWT Resource Server will never run this code automatically.

### 7.5. Refresh/Access Token Cascading Must Be Tested

In verified Spring Authorization Server versions, the revocation provider can invalidate both the refresh token and related access tokens in the authorization. Still, **never extrapolate cascade behavior across all token families, grants, or custom `OAuth2AuthorizationService` implementations**. Test directly:

1. Issue access token A1 and refresh token R1.
2. Revoke R1 using the client that received the token.
3. Call refresh with R1 → must fail.
4. Introspect A1 → expect inactive if cascade policy is enabled.
5. Call the Resource Server with A1 → verify whether the RS rejects or still accepts an offline JWT.
6. Verify A1 issued for other audiences or multiple tokens per grant per your storage model.
7. If policy revokes only R1 without revoking A1, document the residual TTL and risk.

## 8. Offline JWT + Revoked-jti Denylist

If APIs need self-contained JWTs for low latency yet must block certain access tokens before `exp`, you can build a **denylist** keyed by `iss` and `jti`.

### 8.1. How It Works

1. The Authorization Server issues JWTs with unique `jti`, `iss`, `aud`, and `exp`.
2. On revocation, the system writes a revoked record to a shared store with `iss`, `jti`, and expiration timestamp.
3. After verifying JWS + standard claims, the Resource Server queries the denylist.
4. If an active revoke record exists → reject the token.
5. Records are purged via TTL once no valid token remains to block.

~~~mermaid
flowchart LR
    C[Client sends JWT] --> V[Verify signature/issuer/audience/exp]
    V -->|Invalid| X[401]
    V -->|Valid| J[Lookup iss + jti in denylist]
    J -->|Found| X
    J -->|Not found| P[Evaluate scope/authorization]
    P -->|Allowed| OK[API response]
    P -->|Denied| Y[403]
    R[Revocation service] --> E[Durable revoke event]
    E --> S[(Shared revoked-JTI store)]
    S --> J
~~~

The denylist must be **updated from a trusted revocation/admin event path**. Adding a validator at the Resource Server without a writer updating the denylist from the AS does nothing. `jti` does not replace signatures; the Resource Server must verify the JWT before trusting `iss`/`jti`.

### 8.2. Application-Defined Interface

~~~java
import java.time.Instant;

// This is an application-defined interface, NOT a built-in Spring API.
public interface RevokedJwtStore {

    // issuer + token ID (jti) normalized/trusted after signature validation.
    boolean isRevoked(String issuer, String jti);

    // Store record with expiration for cleanup once token can no longer be valid.
    void revoke(String issuer, String jti, Instant expiresAt);
}
~~~

Production requires shared storage (Redis/DB or equivalent) with authentication, encryption-in-transit, persistence/HA, consistent reads, and TTLs. Never use a per-pod local `ConcurrentHashMap` if revocation must work across multiple instances.

### 8.3. Spring Security JwtDecoder Example with Revocation Validator

This is a **Resource Server-side** example. It requires a trusted JWKS source, issuer, audience, and configured shared revoked-`jti` store:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder(RevokedJwtStore revokedJwtStore) {
    String issuer = "https://auth.example.com";
    String jwks = issuer + "/oauth2/jwks";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwks).build();

    OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("inventory-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Wrong audience", null));

    OAuth2TokenValidator<Jwt> notRevoked = jwt -> {
        String jti = jwt.getId();
        if (jti == null || jti.isBlank()
                || revokedJwtStore.isRevoked(issuer, jti)) {
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Token unavailable", null));
        }
        return OAuth2TokenValidatorResult.success();
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    standard, audience, notRevoked));

    return decoder;
}
~~~

**Mandatory notes:**
- `RevokedJwtStore` is a custom interface; without an implementation/bean the example will not run.
- JWKS URIs must come from real metadata/configuration; do not assume every issuer uses `/oauth2/jwks`.
- Never take the issuer from an unverified JWT to pick an arbitrary JWKS/DB domain.
- `JwtValidators.createDefaultWithIssuer(...)` runs standard checks; audience validation is added explicitly.
- Never leak tokens/JTIs in responses; keep error messages brief/generic.
- Under a **mandatory denylist** policy, if the shared store is unreachable, enforce **fail-closed** or an approved degraded policy—never default to "not revoked."
- Tokens without `jti` are rejected in this example; enforce the token contract rather than loosening checks to allow missing IDs.
- This example omits the revocation-event writer adapter; implement the **writer** at the AS/revocation service and test end-to-end.

### 8.4. Denylist Cleanup and TTL Calculation

The denylist only needs to keep records while the token could still be accepted. For a JWT with `exp` and clock-skew tolerance, retention must cover:

~~~text
denylist retention >=
    max(0, exp - revoke_time)
    + accepted_clock_skew
    + propagation/safety margin
~~~

If a record is purged before the JWT expires, the token can become accepted again. If the record is written after returning 200 and propagation lags, a post-revoke acceptance window remains; measure that latency and ensure read/write consistency meets SLA.

### 8.5. Trade-offs

A denylist makes JWT validation no longer purely offline, unless Resource Servers keep local caches or receive store events. Caching cuts I/O but widens the post-revoke staleness window. This is a deliberate trade-off, not free security.

## 9. Session Versions, Revocation Epochs, and Dynamic Permission Checks

Per-`jti` denylists fit revoking specific tokens. For logout-all-devices, disabling users, or invalidating all tokens of a tenant, consider **versions/epochs**.

### 9.1. Revocation Epoch

When issuing a JWT, the AS embeds trusted metadata, e.g.:
- `auth_time`: when the session was authenticated.
- `session_id`/`sid`: session identifier.
- `token_version`: version of the token family/session.
- `iat`: token issuance timestamp.

When the user selects "logout all":
1. Increment `token_version` or set `valid_after` for the user/session in a shared store.
2. The Resource Server compares the token's version/`iat` against server-side state.
3. If the token predates the current threshold, reject it.

Mental model:

~~~text
user42's token has token_version = 7
User triggers logout-all -> policy store token_version = 8
Resource Server:
    if jwt.token_version < current_token_version: reject
~~~

`token_version` is a **custom-defined claim**, not a mandatory standard OAuth2/OIDC claim. Looking up the current version still requires state/caching; if an API trusts the JWT version without checking current state, revocation is not achieved.

### 9.2. Session-Bound Tokens

When storing `sid` or a session ID:
- A single device session can be revoked without affecting all user sessions.
- Authorization grant state can help identify the refresh token family.
- Guard against correlation/PII exposure.
- If tokens lacked `sid` at issuance time, adding DB state later will not retroactively populate old JWTs with that claim.

### 9.3. Business Permissions Requiring Dynamic Checks

For instance, a user loses the Approver role while an old JWT still carries `roles=["APPROVER"]`. If the API trusts claims alone, that privilege persists until expiry unless supplemented.

Solutions may include:
- Short TTLs for sensitive permissions.
- Policy Decision Point (PDP) / authorization database lookup on high-risk requests.
- Resource permission version inside the token compared against a shared policy version.
- Events invalidating permission caches.
- Step-up authentication for sensitive actions.

**Distinguish token validity from authorization:** a validly signed, unrevoked token does not mean the user still holds permission on a specific resource when the API processes the request.

## 10. Refresh Token Rotation, Grant Revocation, and Access Token Relationships

### 10.1. What Does Revoking a Refresh Token Prevent?

Once refresh token R1 is invalidated:
- The Token Endpoint must not mint new access tokens from R1.
- When rotation is enabled, an old refresh token may be invalidated after valid use and the new token persisted.
- The client must re-authorize or use another credential/grant per policy.

**Do not infer that an already-issued access token A1 becomes invalid across all APIs.** If A1 is a self-contained JWT and Resource Servers check no external state, A1 may remain accepted until `exp`.

### 10.2. Token Families and Reuse Detection

Refresh token rotation can form a chain R1 → R2 → R3. If an attacker replays R1 after R1 was already rotated, the server can treat this as a replay signal and revoke the token family/authorization per policy.

What to test:

| Case | Expectation |
|---|---|
| R1 active, refresh succeeds | New access token; R2 if rotation enabled |
| R1 revoked | Refresh with R1 fails |
| Already-rotated R1 reused | Rejected; triggers replay policy if applicable |
| Two concurrent refresh requests | No two valid branches of the token family against policy |
| R2 revoked | R2 cannot refresh; cascading scope verified |
| R1's access token A1 before `exp` | Offline JWT API may still accept without revocation check |
| User logout-all | Revokes all matching authorizations + access-token enforcement strategy |

### 10.3. Do Not Arbitrarily Delete Records When Audits/Revocation Are Needed

Deleting the entire `OAuth2Authorization` can cause Token/Introspection endpoints not to find tokens (typically inactive), yet destroys audit trails, replay detection data, or incident evidence. Prefer invalidation/revocation APIs and business retention policies; purge permanently only after traceability windows expire.

### 10.4. Client Credentials

With `client_credentials`, a client can typically request a new access token whenever its client authentication remains valid. Revoking one access token **does not stop the client from obtaining another** while credentials stay active and the grant is allowed.

To suspend an M2M service:
- Disable/revoke the `RegisteredClient` or credentials per policy.
- Revoke active tokens/authorization state.
- Enforce pre-`exp` invalidation at Resource Servers if immediate blocking is needed.
- Monitor token issuance to verify nothing re-mints after disabling.

## 11. Logout, OIDC Sessions, and Related Tokens

Application logout often spans multiple independent actions:

| Component | Automatically Revoked on User Logout? |
|---|---|
| Browser app session cookie | May be cleared by app logout, but does not expire API tokens |
| Client's refresh token | Must be explicitly revoked to stop session refreshes |
| Opaque access token | Needs AS invalidation and RS introspection/short cache |
| JWT access token | Needs TTL wait or introspection/denylist/epoch |
| OIDC ID Token | Already issued to client; has its own expiry, not an API access token |
| Authorization consent | May be long-lived grant/consent; logout does not necessarily revoke consent |
| SSO session at Authorization Server | May persist if only local app logout ran |
| DPoP/mTLS-bound token | Sender-constraining still needs separate revocation/expiry policy |

OIDC RP-Initiated Logout, Back-Channel Logout, and Front-Channel Logout coordinate/notify login sessions across apps. They **do not replace RFC 7009 or Resource Server access-token revocation enforcement**.

Before promising "Log out all devices," ensure you have:
- A list of authorizations/refresh sessions to revoke.
- A way to identify related access tokens.
- An enforcement mechanism blocking tokens at every API.
- Propagation SLA targets and unavailable-node behavior.
- Synchronized tests across web, mobile, and background jobs.

## 12. Caches, Revocation Events, and Distributed Systems

### 12.1. Event-Driven Model

Once a revocation commits in the store:
1. The transaction writes the invalidation/epoch/denylist entry.
2. An outbox or reliable event mechanism emits the revoke event (without raw tokens).
3. Gateways/Resource Servers consume the event, updating state or purging caches.
4. APIs continue checking state from the shared store or versioned local caches.
5. If an event is lost, TTLs/sync/reconciliation ensure convergence.

~~~mermaid
flowchart TD
    A[Revoke request or admin policy event] --> B[AuthorizationService transaction]
    B --> C[(Revocation state DB)]
    B --> D[Transactional outbox]
    D --> E[Message broker]
    E --> F[RS A invalidates local cache]
    E --> G[RS B invalidates local cache]
    E --> H[Gateway updates policy cache]
    C --> I[Online introspection / revoked-JTI store]
    I --> F
    I --> G
~~~

Never emit events before state is persisted and 200 is returned, as early events cause inconsistent reads. Without a transactional outbox, you need retries, idempotency, replay, and lag monitoring.

### 12.2. Idempotency and Ordering

- Revoking the same token multiple times never reactivates it.
- Duplicate events must be processed idempotently.
- Out-of-order events must never overwrite a newer version with an older one.
- When a user is disabled and later re-enabled, explicitly define whether old tokens resurrect; **by default, never resurrect revoked tokens**.
- If the store uses TTLs, never purge denylist records earlier than `exp`.
- Every instance must share consistent policy versions and issuer/tenant mappings.

### 12.3. Stale Cache Windows Are Architectural Limits

If an application targets "revocation under 2 seconds" yet Resource Servers cache introspection for 5 minutes, the configuration contradicts itself. Define:
- Target maximum revocation latency, per sensitivity tier.
- Token and cache TTLs.
- Cross-region propagation/consistency SLAs.
- Cost of online checks on the critical path.
- Fail-open vs. fail-closed behavior when the state backend is unreachable.

Latency must **be measured from revocation commit until every RS begins rejecting the token**, not merely until the AS returns 200.

## 13. Designing a Strategy by Requirement

| Requirement | Approach | Controls Required |
|---|---|---|
| High-speed, low-risk API tolerating minutes' delay | Short-lived JWT + revoke refresh token | Residual access TTL, key rotation, grant policy |
| Sensitive API requiring near-instant revocation | Opaque token + direct/very short-cached introspection | AS/DB HA, latency, fail-closed, caller permissions |
| Want JWTs yet fast revocation | JWT + `jti` denylist / session epoch check | Shared store, event propagation, stale caches, jti contract |
| Logout-all | Revoke authorizations/refresh sessions + session version/denylist | Enforced across all RSs and devices |
| Compromised client secret | Disable credential/client + revoke associated grants/tokens | Existing offline JWTs still need RS enforcement |
| User stripped of roles | Dynamic authorization/policy version, optionally revoke tokens | Do not rely solely on stale JWT scopes/roles |
| Risk of leaked token replay | Sender-constrained tokens like DPoP/mTLS + TTL/revocation | Does not replace revoke if private key is also leaked |
| Outages must not grant unauthorized access | Fail-closed introspection/denylist | Availability, degraded-mode policy, error handling |
| Multi-region systems | Events + shared state + bounded caches | Consistency, ordering, replay, reconciliation |

**No single formula fits every system.** Shorter TTLs shrink the residual window at the cost of higher Token Endpoint load and dependency. Online checks deliver fresh state at the cost of latency and service coupling. Event-driven designs cut calls but require operating consistency and recovery.

## 14. End-to-End Revocation Testing

### 14.1. Scenario Matrix

| Test | Expectation |
|---|---|
| Revoke valid refresh token via rightful client | 200; subsequent refresh fails |
| Revoke same token again or unknown token | 200, does not disclose existence |
| Revoke using wrong client credentials | 401 or corresponding OAuth2 client-auth error |
| Revoke token belonging to another client | Rejected per security policy |
| Revoke R1 and introspect same-grant A1 | Outcome matches committed cascade policy; must test |
| Revoke A1 while refresh token stays active | New tokens may be issued if policy doesn't cascade; must document |
| Opaque A1 after revoke, uncached introspection | `active=false` |
| Opaque A1 after revoke, 10s RS cache | Acceptance window never exceeds defined budget |
| JWT A1 after revoke, offline-only RS | May still be accepted before `exp` (test illustrating limit) |
| JWT A1 after revoke, RS with denylist | Returns 401 once state propagates |
| JWT A1 with wrong issuer/audience/exp | Returns 401 even when unrevoked |
| Disable M2M client | No new tokens issued; old tokens blocked per policy |
| Refresh token rotation and replay | Old R1 rejected; token family handled per policy |
| User logout-all | All policy-covered sessions/tokens rejected by APIs past SLA |
| AS/DB unavailable during API introspection | Fail-closed or approved degraded mode |
| Duplicate, out-of-order revoke events | State never resurrects |
| RS restart/scale-out | Revocation state preserved beyond local memory |
| Multi-region failover | New region rejects revoked tokens within SLA |

### 14.2. Testing RFC 7009 with MockMvc

Assume the test app has a confidential `RegisteredClient` `employee-portal`, `CLIENT_SECRET_BASIC`, valid tokens in `OAuth2AuthorizationService`, and `/oauth2/revoke`.

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TokenRevocationContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void revokeKnownRefreshTokenReturnsSuccess() throws Exception {
        mvc.perform(post("/oauth2/revoke")
                .with(httpBasic("employee-portal", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", "TEST_REFRESH_TOKEN")
                .param("token_type_hint", "refresh_token"))
            .andExpect(status().isOk());
    }

    @Test
    void unknownTokenStillReturnsSuccessForValidCaller() throws Exception {
        mvc.perform(post("/oauth2/revoke")
                .with(httpBasic("employee-portal", "test-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("token", "UNKNOWN_TEST_VALUE"))
            .andExpect(status().isOk());
    }
}
~~~

This is an **assertion template**, not a standalone runnable test: you must configure `RegisteredClient` fixtures, encoders, authorization records, and JUnit/MockMvc/Spring Security Test imports. For known-token revocation, assert **post-response effects**: refresh grants fail, `OAuth2AuthorizationService` or introspection confirms state, and Resource Servers enforce rejection. Waiting only for 200 **does not prove revocation took effect**.

### 14.3. Testing JWT Resource Servers

For JWT access tokens:
1. Issue an unexpired token A1 with `jti`, `iss`, `aud`, and `exp`.
2. Call the API with A1: 200 with sufficient scopes.
3. Revoke A1/authorization at the AS, verifying persistence.
4. Call an offline JWT-only API: note A1 **may still be accepted**; document this limitation.
5. Enable the denylist validator or introspection, ensuring revocation records/events are written.
6. Call the API again with A1: 401 after propagation, within the latency budget.
7. Verify unrevoked tokens continue working.
8. Advance past `exp`; validator rejects even once the denylist entry expires per TTL.
9. Test wrong audience, wrong issuer, wrong signature; all rejected.
10. Restart replicas and confirm state survives.

### 14.4. Testing Opaque Resource Servers

1. Issue opaque token O1; introspection reports `active=true`.
2. Call API with O1 successfully.
3. Revoke O1 or related refresh token per policy.
4. Re-introspect: `active=false` after state commit.
5. Call API with O1; confirm 401 past the chosen cache TTL.
6. Test network timeouts, 503s, malformed bodies, and bad introspection credentials; ensure no fail-open.
7. Load-test concurrent introspection requests and per-caller rate limits.

### 14.5. Measuring Revocation SLO

Suggested test metric:

~~~text
revocation_effective_at =
    first_timestamp_when_every_relevant_resource_server_rejects_token

revocation_latency =
    revocation_effective_at - revocation_commit_timestamp
~~~

In production, avoid storing raw tokens to measure this; use synthetic test tokens or internal token fingerprints/IDs under strict access and retention controls. Measure p95/p99 and worst-case latency during rolling deployments and network partitions, not just a single local test.

## 15. Common Implementation Mistakes

| Symptom | Cause | Remediation |
|---|---|---|
| Revocation Endpoint returns 200, API still returns 200 | Offline JWT verification, no revocation check | Shorter TTL or introspection/denylist/epoch |
| Refresh R1 fails, yet A1 still accesses APIs | Only stopped new token issuance | Design access-token enforcement |
| Revoked opaque token still accepted by API | Long active introspection cache | Lower cache TTL, event purge, measure SLA |
| One replica sees revoke, another does not | In-memory authorization/denylist | Shared persistent store, propagation & HA |
| JWT denylist entry deleted before token expiry | Record TTL too short | Retain past `exp` + clock skew + safety margin |
| JWT stays valid after disabling client | Offline RS does not check client status | Session/client epoch or introspection |
| JWT validator rejects all tokens during DB outage | Fail-closed with low availability | Design HA, circuit breakers, degraded-mode policy |
| Revocation events lost | Fire-and-forget publishing | Durable outbox, retries, reconciliation |
| Access token revoked, yet client mints a new one | Grant/credentials still active | Disable client/revoke grant per incident scope |
| Deleting JWK breaks all tokens | Using key rotation as revocation | Reserve emergency rotation for compromises per plan |
| `active=false` still leaks details | Introspection adds extra error details/claims | Minimal response per RFC 7662 |
| User logs out of local app, still has SSO/refresh | Missing link between app session and AS | Implement OIDC logout + grant/refresh revocation |
| Client Credentials worker keeps minting tokens | Revoked one token while client keeps access | Disable client/policy, rotate compromised credentials |
| Resource Server cache does not isolate callers | Shared state across tenants/issuers | Cache key includes issuer, resource/tenant, token |
| Old scopes/roles keep working after role removal | Stale JWT claims | Dynamic authorization, epochs, or short TTLs |
| Revocation HTTP 503 treated as success | Conflating outage with 200 | Retry/backoff, alerting, and state confirmation |

## 16. Practice Exercise

**Context:** A retail system has:
- `employee-portal`: Authorization Code + OIDC, JWT access token TTL 15 minutes, refresh token TTL 14 days.
- `inventory-worker`: Client Credentials, JWT TTL 5 minutes.
- `billing-api`: sensitive API requiring revocation to take effect within 10 seconds.
- `reporting-api`: high-traffic API permitting up to a 5-minute residual window.

**Requirements:**

1. Describe token issuance and revocation flows for each client; specify which tokens can outlive logout.
2. Choose an approach for `billing-api`: introspection with very short cache or JWT + shared denylist/epoch.
3. Choose an approach for `reporting-api`: short-TTL JWT with offline verification or supplementary controls by risk.
4. Configure `TokenSettings` appropriately without altering `expires_in` in response handlers.
5. Configure `OAuth2AuthorizationService` with shared persistence and verify `isActive()`/`isInvalidated()`.
6. Test the RFC 7009 Revocation Endpoint: 200 for valid/unknown tokens, wrong-credential errors, and `token_type_hint` handling.
7. For opaque tokens, configure Resource Server introspection and confirm `active=false` post-revocation.
8. For JWTs, implement `RevokedJwtStore`, an event writer, and a Resource Server validator; measure event/cache latency.
9. Add logout-all logic via grant/refresh session revocation or session versions.
10. Test refresh rotation/replay, client disabling, role removal, and key compromise separately.
11. Run two Resource Server replicas and two Authorization Server replicas; test restarts, outages, and duplicate events.
12. Write `logout-all` and `compromised-client-secret` runbooks including SLAs, metrics, rollback, and owners.

**Completion Criteria:** Never confuse HTTP 200 from the Revocation Endpoint with API enforcement; `billing-api` rejects revoked tokens within 10 seconds under tests, `reporting-api` stays within chosen TTL/risk; revoked refresh tokens mint no new tokens; errors/outages never expand access.

## 17. Pre-Production Checklist

- [ ] Distinguish TTL, revocation, introspection, authorization, and logout.
- [ ] RFC 7009 POST over HTTPS with required `token`; `token_type_hint` treated purely as a hint.
- [ ] 200 response for valid already-revoked and unknown tokens, without creating a token-existence oracle.
- [ ] Client authentication and token ownership verified; callers cannot revoke another client's tokens.
- [ ] Revocation/Introspection Endpoints live on the proper public issuer over TLS.
- [ ] `AuthorizationService` is persistent/shared; invalidation metadata persists durably.
- [ ] Access/refresh grant cascading tested per policy and framework version.
- [ ] Clear answer exists for already-issued unexpired access JWTs after revocation.
- [ ] Access token and refresh token TTLs match risk, with refresh rotation where needed.
- [ ] If using introspection, cache TTL is below the revoke SLA and never exceeds `exp`.
- [ ] If using a JWT denylist, both writer/event propagation and reader validator are wired.
- [ ] Denylist record retention covers `exp`, clock skew, and safety margin.
- [ ] If using session/version epochs, Resource Servers check current version state.
- [ ] Resource Servers validate signature, issuer, audience, expiry, and scopes/permissions—not solely revocation state.
- [ ] Routine key rotation is never used as a per-token revocation mechanism.
- [ ] Policy covers AS/introspection/denylist backend unavailability; never silently fails open.
- [ ] Revocation events are idempotent with retry/replay, ordering, and reconciliation.
- [ ] Token/cache state never leaks via logs, metrics, headers, or error descriptions.
- [ ] End-to-end tests verify from revoke commit to API 401 across all replicas.
- [ ] p95/p99 revocation latency measured and verified against SLO.
- [ ] Runbooks exist for logout, compromise, client disabling, and signing-key loss.
- [ ] Completing this lesson is not mistaken for full security QA/production readiness sign-off.

## Summary

**TTL** bounds how long a token may be accepted, but does not perform proactive revocation. The **Revocation Endpoint** per RFC 7009 updates token/authorization state at the Authorization Server and blocks future operations such as refreshes; **Resource Servers** must have a way to observe that state to reject already-issued access tokens before expiration.

With **opaque/reference tokens**, RFC 7662 introspection directly checks state, while caching and network calls govern latency. With **self-contained JWTs**, offline signature checks cannot detect revocations: you need sufficiently short TTLs or supplementary introspection, revoked-`jti` denylists, session epochs, dynamic authorization checks, and event/cache invalidation. Each mechanism trades off latency, availability, and operational cost differently.

In production systems, success is measured not by "the revoke API returned 200," but by **whether every Resource Server rejects the revoked token within the committed timeframe**, even across restarts, warm caches, and rolling deployments.

## References

1. [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation requests, 200 responses, `token_type_hint`, cascade policy, and implementation notes on self-contained tokens.
2. [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): `active`, caller authorization, privacy, caching, and TLS.
3. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Revocation/Introspection configurers and standard hooks.
4. [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2AuthorizationService`, `OAuth2Authorization`, `TokenSettings`, and token formats.
5. [Spring Authorization Server 1.5.8 — OAuth2TokenRevocationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenRevocationAuthenticationProvider.html): standard provider handling revocation.
6. [Spring Authorization Server 1.5.8 — OAuth2Authorization.Token API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Token.html): `isActive()`, `isInvalidated()`, and token metadata.
7. [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection for opaque tokens and also JWTs when online validation is needed.
8. [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, signature/issuer validation, and custom validators.
9. [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): `exp`, `iat`, `jti`, and JWT claims.
10. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): sender-constrained tokens, refresh rotation, and replay/compromise handling.
11. [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): JWT algorithms, issuer/audience, and validation.
12. [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): OIDC logout protocol at Client/OP, distinct from access-token revocation.
