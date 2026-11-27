# Self-Contained Tokens and Instant Revocation Limits in Local Verification

A **self-contained access token** allows the Resource Server to verify a token using data embedded in the token and trusted keys, rather than asking the Authorization Server about the status of each token on every request. A signed JWT can carry issuer, audience, subject, scope, and expiration; the Resource Server verifies the signature, checks claims, and creates an `Authentication` locally.

In return, there is an important limitation: **local verification does not automatically know that the Authorization Server has just revoked a token**. Without an additional source of state, an already-issued JWT typically remains valid until expiration, even if the user logs out, the account is locked, or an administrator requests revocation.

This is a trade-off between independence, latency, and revocability:

- **Local JWT validation** reduces network round trips and runtime dependency on the Authorization Server.
- **Online introspection** can reflect fresher token state, but increases latency and depends on AS availability.
- **`jti` denylists, token versions, and revocation events** shorten the window before a JWT is invalidated, but reintroduce shared state into the system.
- **Short access token TTLs and refresh token rotation** bound how long stale permissions remain valid, but are not instant revocation.

This lesson explains the limits of self-contained tokens, lifecycle and revocation design patterns, Spring Security configuration for local JWT verification, and appropriate choices when business requirements demand rapid revocation.

## 1. What Is a Self-Contained Token?

A **self-contained token** carries enough data for the Resource Server to verify and interpret the token without calling the Authorization Server to query each token's active status.

JWT is a common format. A JWT typically has three Base64URL parts:

~~~text
header.payload.signature
~~~

Example payload:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "iat": 1893452400,
  "exp": 1893456000,
  "jti": "token-8f21"
}
~~~

| Claim | Meaning |
|---|---|
| **iss** | Issuer that issued the token |
| **sub** | Subject, the principal represented by the token |
| **aud** | Audience/resource permitted to accept the token |
| **iat** | Timestamp when the token was issued |
| **nbf** | Timestamp when the token becomes valid |
| **exp** | Timestamp when the token expires |
| **jti** | JWT ID, token identifier |
| **scope** | Granted permission scope per the issuer's contract |
| **client_id** | Client issued the token if used by the profile |

Time claims use NumericDate, measured in seconds since the Unix epoch.

### 1.1. JWT Does Not Mean Encrypted Data

A JWT can be protected in different ways:

- **JWS**: signed or integrity-protected. The payload is usually still readable after Base64URL decoding.
- **JWE**: encrypted content so those without the key cannot read it.
- Nested JWT: combines signing and encryption layers by design.

Common Resource Servers typically receive signed JWT access tokens and verify the JWS signature. **A signature proves that the content has not been tampered with and was signed by a trusted key; it does not prove that the token has not been revoked.**

Do not put confidential information in a JWT payload just because the token is signed. Without encryption, anyone holding the token can read its claims.

### 1.2. Self-Contained Does Not Force Offline Verification

A JWT can be verified locally, yet the system can still call an introspection endpoint to check dynamic state or policy. Conversely, an opaque token typically requires introspection, yet the result can be cached.

You must distinguish:

- **Token format**: JWT vs. opaque.
- **Validation strategy**: local verification vs. online introspection.
- **Revocation strategy**: how invalidated tokens are communicated.
- **Authorization strategy**: how endpoint and resource permissions are enforced.

These concepts are related, but they do not replace one another.

## 2. How Does Local JWT Validation Work?

With a signed JWT, the Resource Server typically:

1. Receives the Authorization Bearer token.
2. Reads the header to identify a key identifier such as `kid`.
3. Selects a key from a configured trusted source, typically JWKS.
4. Verifies the signature using an allowed algorithm.
5. Validates issuer, audience, `exp`, `nbf`, and other validators.
6. Converts verified claims into an `Authentication` and authorities.
7. Enforces authorization policies for the request.

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant R as Resource Server
    participant K as JWKS / Key Cache
    C->>R: Authorization: Bearer signed JWT
    R->>R: Parse header and claims
    R->>K: Fetch public key by kid if needed
    K-->>R: Trusted verification key
    R->>R: Verify signature and claims
    R->>R: Map scope to authorities
    R-->>C: Allow or reject request
~~~

Once the public key is cached, per-request verification can happen **without an introspection request to the AS**.

Local validation does not mean the application never touches the network: discovery, JWKS retrieval, key rotation, and cache refresh may still require connecting to the issuer. The difference is **not querying the active/revoked status of each token on every request**.

### 2.1. Benefits

- Reduces network round trips on the authentication path.
- Reduces dependency on AS latency/availability once keys are cached.
- Public keys can be reused by multiple Resource Server instances.
- Reduces load on the introspection endpoint.
- Independent signature verification at each Resource Server.

### 2.2. What a Signature Cannot Tell You

A JWT with a valid signature may still:

- Have been logged out by the user or revoked.
- Belong to a user whose account was just locked.
- Carry stale scopes from before permissions changed.
- Have been issued for a different audience.
- Belong to a different tenant.
- Have been stolen and replayed before `exp`.
- Be signed by a key that is still cached but has been emergency-revoked.

A signature verifies the token content against a trusted key. It does not automatically reflect events that happened **after the token was issued**.

## 3. The Limit of Instant Revocation

Suppose the Authorization Server issues:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "iat": 1893452400,
  "exp": 1893456000,
  "jti": "token-8f21"
}
~~~

The Resource Server verifies the signature and claims at 10:00. At 10:02, an administrator revokes the token or locks the account. If the Resource Server only uses the public key and the data inside the JWT, it has no knowledge of that new event.

~~~mermaid
sequenceDiagram
    participant U as User
    participant AS as Authorization Server
    participant RS as Resource Server
    U->>AS: Request access token
    AS-->>U: JWT exp=10:30
    U->>RS: Request with JWT
    RS->>RS: Verify signature and exp
    RS-->>U: 200 OK
    Note over AS: 10:02: Admin revokes token
    U->>RS: Retry request with old JWT
    RS->>RS: Valid signature, exp not reached
    RS-->>U: May still return 200 OK
~~~

### 3.1. Revocation Cannot Be Inferred from a Signature

A signed token is an immutable message. Changing state at the AS does not alter the already-issued payload or signature.

A local validator can check signature, issuer, audience, `exp`, `nbf`, and claims. But if the signature is still valid, `exp` has not been reached, and the claims have not changed, **the validator cannot know about a revocation event that has not been delivered to it**.

This is an information limitation, not a bug specific to Spring Security.

### 3.2. Statelessness Is a Trade-Off

Local JWT verification relieves the Resource Server from storing state per token. However, if business requirements demand:

- Logout must invalidate access tokens immediately.
- Locking a user must affect all active tokens.
- Administrative privilege revocation must take effect very quickly.
- A lost device must lose access across all APIs.
- A compromised token must not remain usable.

then **purely stateless local validation cannot satisfy that requirement**.

To know about revocation events, the Resource Server must receive additional information: query state, receive events, check a version, or use another proof/state mechanism.

## 4. Expiration Bounds Time, Not Instant Revocation

The **exp** claim defines when the token is no longer accepted under policy.

~~~json
{
  "sub": "user-123",
  "iat": 1893452400,
  "exp": 1893452700
}
~~~

The token has a 5-minute lifetime in this example. After `exp`, the validator rejects the token, potentially applying configured clock skew.

**Short access token TTLs** reduce how long an old token continues to work after revocation, but do not eliminate that window.

| Access token TTL | Benefit | Cost |
|---|---|---|
| Short | Reduces window where stale permissions stay valid | Frequent refreshes, higher AS load |
| Medium | Balances latency and revocation window | Requires refresh/logout design |
| Long | Fewer refreshes, fewer token issuances | Compromised or revoked tokens stay usable longer |

There is no single TTL right for every system. Consider data sensitivity, operation type, AS load, UX, refresh token security, and logout requirements.

### 4.1. Clock Skew Can Extend the Acceptance Window

Resource Servers often allow a small clock skew to avoid rejecting valid tokens due to clock drift. This margin can allow tokens to be accepted near the `exp`/`nbf` boundaries.

Synchronize clocks across the AS, Resource Servers, and infrastructure. Do not configure an overly wide clock skew to mask clock errors, because it also widens the token acceptance window.

### 4.2. TTL Does Not Replace Audience and Scope Validation

A token that lives for only two minutes but has the wrong audience must still be rejected. An unexpired token missing the `write` scope must still be rejected.

**Expiration is a necessary condition, not the entire authorization policy.**

## 5. Refresh Tokens and Access Tokens Have Different Lifecycles

A common architecture:

~~~mermaid
flowchart TD
    L[User logs in] --> AS[Authorization Server]
    AS --> AT[Short-lived access token]
    AS --> RT[Refresh token]
    AT --> API[Resource Server]
    RT --> REF[Token endpoint / refresh]
    REF --> NEW[New access token]
    NEW --> API
    RV[Logout or revoke refresh token] --> REF
~~~

The access token is sent to the Resource Server to access APIs. The refresh token is sent to the Authorization Server to obtain new access tokens and usually has its own lifecycle and protections.

### 5.1. Revoking a Refresh Token Does Not Automatically Delete Old Access JWTs

Suppose an access token has 10 minutes left and the refresh token has a longer lifetime. The user logs out at minute two.

The AS can revoke the refresh token so the client cannot obtain new access tokens. However, the already-issued JWT access token still has a valid signature and can continue to be accepted by the Resource Server until `exp` unless another revocation mechanism exists.

**Stopping new token issuance is different from invalidating already-issued tokens.**

### 5.2. Refresh Token Rotation

A typical rotation flow:

1. Client sends the current refresh token.
2. AS validates the token.
3. Server issues a new access token and a new refresh token.
4. Old refresh token is invalidated.
5. If the old token is reused, the AS can detect reuse and revoke the token family according to policy.

Rotation reduces the risk of replaying a stolen refresh token, but does not automatically revoke previously issued access JWTs.

### 5.3. Client-Side Logout Does Not Equal Server-Side Revocation

Removing a token from memory, storage, or cookies makes the client stop using it. A stolen copy of the token can still be used elsewhere until `exp` or until the Resource Server rejects it via a revocation mechanism.

OIDC logout primarily handles sessions at the OP/RP according to protocol and configuration. **Do not assume every Resource Server immediately knows an access JWT has been logged out.**

## 6. Strategies to Shorten the Revocation Window

| Strategy | How it works | Revocation freshness | Cost / caveats |
|---|---|---|---|
| **Short-lived access token** | Wait for token to hit `exp` | Up to remaining TTL | Not instantaneous |
| **Opaque token + introspection** | Ask AS for active status | Near real-time per request/cache | Network latency and availability |
| **JWT denylist by jti** | Check revoked token IDs | As fast as store updates | Requires state lookup |
| **User/session token version** | Compare version in JWT with current state | As fresh as state | Requires lookup/cache |
| **Revocation event push** | AS publishes events to Resource Servers | Propagation delay | Event loss/replay/consistency |
| **Signing-key removal** | Stop trusting the key that signed the token | After JWKS cache refreshes | Affects many tokens |
| **Uncached online introspection** | Query AS on every request | Close to current AS state | High AS dependency |

No approach is simultaneously completely offline, completely stateless, and immediately aware of every revocation event. **Revocation information must reach the place making the access decision.**

## 7. Opaque Tokens and Introspection When Fresh State Is Needed

Opaque tokens typically carry no claims for the Resource Server to verify itself. The Resource Server calls the introspection endpoint per RFC 7662:

~~~http
POST /oauth2/introspect
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>
~~~

The Authorization Server may return:

~~~json
{
  "active": false
}
~~~

If the AS has updated the revocation state, the next introspection call can see `active=false`.

### 7.1. Introspection Reduces Revocation Lag but Adds a Dependency

Advantages:

- The AS is the centralized source of truth.
- Can detect revoked/inactive tokens.
- Permission/status changes do not need to wait for JWT `exp`.
- The Resource Server does not need to manage per-token denylists itself if the AS provides authoritative state.

Costs:

- Every request may incur an HTTP round trip.
- The AS becomes a dependency on the authentication path.
- Network failures impact verification capability.
- Requires timeouts, connection pools, retry policies, and monitoring.
- Introspection caching can delay revocation detection.

### 7.2. Introspection Caching Creates a Stale Acceptance Window

For example, caching `active=true` for 60 seconds:

~~~text
10:00:00  introspection -> active=true, cache 60s
10:00:10  AS revokes token
10:00:20  Resource Server cache hit active=true
10:01:00  cache expires
10:01:01  introspection -> active=false
~~~

Revocation lag can be roughly the cache TTL plus propagation/network delays, depending on the invalidation strategy.

**Caching is not merely a performance optimization; it changes security semantics.**

## 8. jti Denylist: Revoking a Specific Token

A JWT can include a **jti** claim as an identifier. When revoking a token, the AS or administrative system records the issuer/token ID pair in a revocation store.

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "jti": "token-8f21",
  "exp": 1893456000
}
~~~

After verifying the signature, the Resource Server can check:

~~~text
Is (iss, jti) in the revocation store?
Yes    -> reject
No     -> continue authorization
~~~

### 8.1. Pair Issuer with jti

Using **issuer + jti** as the key prevents token ID collisions across multiple issuers. Do not use the raw JWT as a Redis key, metric tag, or log entry because the token is a Bearer credential.

### 8.2. Denylist Entry TTL

An entry typically only needs to survive until `exp` plus clock-skew/cleanup margin:

~~~text
revocation key: issuer-id + jti
expires at: token exp + allowed clock-skew margin
~~~

Keeping denylist entries indefinitely causes unbounded growth; deleting them too early can allow a node with clock drift or another cache to still accept the token.

### 8.3. jti Does Not Automatically Enable Revocation

`jti` is only an identifier. If the Resource Server does not check it against a denylist or corresponding state, having `jti` in the JWT **does not revoke the token**.

You must verify the token before trusting `jti`. Never use claims from an unverified raw JWT as the basis for granting permissions or identity decisions.

### 8.4. Local vs. Distributed Denylists

| Store | Characteristics |
|---|---|
| In-memory per instance | Fast, but only knows entries on that node and loses them on restart |
| Shared Redis/database | Multiple instances see the same state, but requires lookup or cache |
| Local cache + revocation events | Reduces remote lookups, has propagation lag |
| Distributed cache with invalidation | Can reduce lag, requires delivery/consistency |

If the denylist is only kept in one instance's RAM, other replicas can still accept the token. That is not cluster-wide revocation.

## 9. Token Version and User/Session Revocation

A JWT can contain a version:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "ver": 7,
  "exp": 1893456000
}
~~~

The system stores the current version:

~~~text
user-123 currentVersion = 7
~~~

When revoking all current tokens for the user:

~~~text
user-123 currentVersion = 8
~~~

The Resource Server compares the `ver` claim against the current version. If they do not match, the token is rejected.

### 9.1. Benefits and Costs

A single update can invalidate many tokens for the same user/session without writing an entry for each `jti`.

In return:

- Requires state lookup or caching.
- Version updates must reach Resource Servers.
- Must distinguish user-wide, per-device session, or per-client versions.
- Nodes that have not received the new version may still accept old tokens.
- Caches cannot live indefinitely if rapid revocation is required.

A version claim in a JWT without a place comparing the current version **provides no revocation capability**.

### 9.2. Revocation by iat Cutoff

A variant stores a revocation timestamp:

~~~text
user-123 revokedAfter = 1893452500
~~~

The Resource Server rejects the token if `iat` is less than or equal to `revokedAfter`.

This can revoke all tokens issued before a given point in time. You must account for clock skew, timestamp precision, issuer scope, and whether `iat` is mandatory on tokens.

## 10. Revocation Events: Pushing State to Resource Servers

An event-driven model:

~~~mermaid
flowchart LR
    AS[Authorization Server] -->|TokenRevoked event| BUS[Message broker]
    BUS --> R1[Resource Server A local denylist]
    BUS --> R2[Resource Server B local denylist]
    BUS --> R3[Resource Server C local denylist]
    R1 --> API1[Local JWT validation]
    R2 --> API2[Local JWT validation]
    R3 --> API3[Local JWT validation]
~~~

Each Resource Server updates its local denylist/cache. New requests can have their signatures verified and local state checked without calling the AS directly.

### 10.1. Event-Driven Is Not Automatically Instant

The revocation window depends on:

- Time for the AS to emit the event after committing.
- Broker delivery latency.
- Consumer processing delay.
- Cache update/invalidation.
- Node restarts or disconnections.
- Duplicate, out-of-order, or lost events.
- Replay/snapshot after reconnecting.

**Event push typically produces eventual consistency** unless stronger synchronization mechanisms exist. Do not advertise instant revocation without defining and measuring propagation SLAs.

### 10.2. Events Need Replay and Idempotency

Example payload:

~~~json
{
  "eventType": "ACCESS_TOKEN_REVOKED",
  "issuer": "https://identity.example.com",
  "jti": "token-8f21",
  "expiresAt": 1893456000,
  "eventId": "evt-00421",
  "occurredAt": "2030-01-01T10:02:00Z"
}
~~~

A real implementation requires:

- Authenticating the event source and protecting transport.
- An event ID for idempotent processing.
- Ordering/keying by issuer, user, or session if needed.
- Replay or snapshot after reconnection.
- Deduplication and handling out-of-date events.
- TTL cleanup based on `exp`.
- Consumer lag metrics.
- Reconciliation when the local cache is lost.

Never allow unauthenticated events to arbitrarily add or remove revocation entries.

### 10.3. When the Event Stream Is Interrupted

There must be a policy:

- Fail closed on sensitive operations if local revocation state is not fresh enough.
- Or continue local validation within an acceptable window while recording revocation lag.
- Or fall back to online introspection when local state is untrusted, if the AS is available.
- When a consumer reconnects, sync snapshot/offset before declaring the node caught up.

## 11. Signing-Key Rotation Is Not How You Revoke a Normal Token

JWTs are signed with a private key; the Resource Server uses the corresponding public key. If the AS removes an old public key from JWKS, tokens signed with that old key can be rejected **after the Resource Server refreshes its key set**.

### 11.1. Normal Rotation

1. Publish the new public key in JWKS with a new `kid`.
2. Wait until Resource Servers can fetch the new key.
3. Start signing tokens with the new private key.
4. Keep the old key long enough for old tokens to expire plus clock-skew/cache margin.
5. Remove the old key after the transition period.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant J as JWKS endpoint
    participant RS as Resource Server
    AS->>J: Publish public key K2
    RS->>J: Refresh JWKS
    J-->>RS: K1 and K2
    AS->>AS: Sign new tokens with K2
    RS->>RS: Verify token kid=K2
    Note over AS,J: K1 tokens expire
    AS->>J: Remove public key K1
    RS->>J: Refresh JWKS
    J-->>RS: Only K2 remains
~~~

### 11.2. Emergency Rotation When a Private Key Is Compromised

If a private key is exposed, the AS must stop signing with it, remove the old public key from trust sources, and switch to a new key. However:

- Resource Servers may cache the old public key.
- JWKS refresh does not necessarily occur immediately on every node.
- The decoder may keep verifying from cache until refreshed.
- Every token signed with that key can be affected, not just one user's token.

Key removal has a **large blast radius** and revocation lag due to caching/propagation.

### 11.3. Do Not Rotate Keys on Every Logout

A signing key typically serves many users and clients. Rotating a key to revoke a single token can invalidate countless other tokens and cause an outage.

Use key rotation for key lifecycle/compromise. Use `jti`, token version, introspection, or short TTLs for narrower revocation.

## 12. Spring Security Local JWT Verification

Spring Security Resource Server uses **JwtDecoder** to verify signed JWTs and validators to check claims.

Example Servlet configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfiguration {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer = "https://identity.example.com";

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
                return OAuth2TokenValidatorResult.success();
            }

            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The required audience is missing",
                null
            );
            return OAuth2TokenValidatorResult.failure(error);
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
        );

        return decoder;
    }
}
~~~

Wiring into the Resource Server:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults())
    );
~~~

This example assumes the Resource Server dependency and remaining configuration are already in place.

### 12.1. Default Validators and Custom Policies

**JwtValidators.createDefaultWithIssuer(issuer)** combines Spring Security's default validators, including timestamp validation and issuer validation per the release line. The audience validator in the example adds a check that the token is intended for `orders-api`.

Depending on the token profile, additionally check:

- JWS algorithm allowlist.
- Audience/resource.
- Token type/profile, access token rather than ID Token.
- Client/resource binding.
- Tenant and permission contract.
- Any other mandatory claims.

Never read the `alg` claim from the JWT header and trust it as the algorithm policy. Key sources and algorithms must be constrained by trusted configuration.

### 12.2. Local Validation Still Depends on Key Lifecycle

When using issuer discovery/JWKS, the decoder may fetch metadata or public keys from the trusted endpoint. Once keys are cached, verifying individual tokens does not require introspection. When a new `kid` is encountered or the cache refreshes, network activity can still occur.

That is **key distribution**, which is distinct from querying the active status of each individual token.

## 13. jti Denylist in Spring Security

An `OAuth2TokenValidator` can check revoked `jti` values after the JWT passes signature/claim validation.

Simplified Servlet example:

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

class LocalJtiRevocationValidator implements OAuth2TokenValidator<Jwt> {

    private final Set<String> revokedIds =
        ConcurrentHashMap.newKeySet();

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String issuer = jwt.getIssuer().toString();
        String tokenId = jwt.getId();
        String key = issuer + ":" + tokenId;

        if (tokenId != null && revokedIds.contains(key)) {
            OAuth2Error error = new OAuth2Error(
                "invalid_token",
                "The access token has been revoked",
                null
            );
            return OAuth2TokenValidatorResult.failure(error);
        }

        return OAuth2TokenValidatorResult.success();
    }

    public void revoke(String issuer, String tokenId) {
        revokedIds.add(issuer + ":" + tokenId);
    }
}
~~~

This is an **in-memory demo**, not a distributed production solution:

- Each instance has its own set.
- Restarts lose entries.
- No event propagation.
- No TTL cleanup based on `exp`.
- Does not revoke an entire user/session.
- Requires a policy if a token lacks `jti`.

Production requires a revocation store with clear lifecycle, TTL, namespacing, and consistency policies.

### 13.1. Attaching the Validator to the Decoder

~~~java
LocalJtiRevocationValidator revocationValidator =
    new LocalJtiRevocationValidator();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator,
        revocationValidator
    )
);
~~~

The validator only detects a revoked token if the entry has already been updated on the instance handling the request.

### 13.2. Synchronous Validators and Remote Lookups

`OAuth2TokenValidator` in Servlet is synchronous. If every request makes a blocking call to a remote Redis/database, you place a network lookup in the request path and risk tying up servlet threads.

- Local cache is fast but has propagation lag.
- Shared synchronous lookup provides fresher state but needs timeouts, bulkheads, and an availability policy.
- Do not call reactive Redis/WebClient and call `block()` inside a validator.

If WebFlux needs a reactive revocation store, place the check in the reactive authentication/conversion pipeline after `ReactiveJwtDecoder` verifies the token, rather than forcing a publisher into a synchronous result.

## 14. WebFlux and Asynchronous Revocation Lookups

WebFlux uses **ReactiveJwtDecoder** and **ReactiveAuthenticationManager**. If a revocation check must query a shared reactive store, do not perform blocking lookups on the event loop.

Model:

~~~text
Bearer token
  -> ReactiveJwtDecoder
       -> verify signature, issuer, audience, timestamps
  -> Reactive revocation lookup
       -> revoked: reject authentication
       -> not revoked: build Authentication
  -> AuthorizationWebFilter
       -> scope/role/domain policy
~~~

You can use **JwtReactiveAuthenticationManager** with a reactive converter or a custom `ReactiveAuthenticationManager`:

- Only perform the revocation lookup **after the JWT has been verified by the decoder**.
- Key by `issuer + jti` or user/session version.
- Return an error `Mono` if revoked.
- Propagate timeouts/cancellation; do not fail open.
- Enforce bounded concurrency/caching/timeouts for the state store.
- Do not call `block()` or manually `subscribe()`.

WebFlux does not automatically make revocation faster. Store consistency and event propagation still govern state freshness.

## 15. Token Version and User State

A JWT may contain a version:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "ver": 12,
  "exp": 1893456000
}
~~~

Current state:

~~~json
{
  "subject": "user-123",
  "currentTokenVersion": 13,
  "enabled": false
}
~~~

After verifying the JWT, the Resource Server can check the version and user status. If the version mismatches or the user is disabled, reject the request.

This is a **stateful check**. It can revoke multiple tokens for the same user/session, but requires:

- State lookup/caching.
- Propagating updates to all nodes.
- Distinguishing user-wide, per-device session, or per-client versions.
- A cache TTL aligned with the revocation SLA.
- A policy for when the store is unavailable.

A version claim in a JWT without a place comparing the current version **provides no revocation capability**.

### 15.1. Revocation by iat Cutoff

A variant stores `revokedAfter` for the user:

~~~text
user-123 revokedAfter = 1893452500
~~~

The Resource Server rejects the token if `iat` is less than or equal to that timestamp. You must handle clock skew, timestamp precision, issuer scope, and require `iat` to be present.

### 15.2. Revoking a Token vs. Revoking a Session

- **Single token**: one `jti`.
- **Single device/session**: all tokens of a session/device.
- **All user sessions**: all tokens of a user.
- **Client/application**: tokens issued to a client.
- **Issuer/key**: all tokens signed by an affected key or issuer.

Choose the right state scope. A user-level version can log out all devices; a `jti` denylist requires managing many entries if revoking an entire user.

## 16. Revocation Events: Pushing State to Resource Servers

The Authorization Server can emit an event when a token, user, or session is revoked:

~~~mermaid
flowchart LR
    AS[Authorization Server] -->|TokenRevoked event| BUS[Message broker]
    BUS --> R1[Resource Server A local denylist]
    BUS --> R2[Resource Server B local denylist]
    BUS --> R3[Resource Server C local denylist]
    R1 --> API1[Local JWT validation]
    R2 --> API2[Local JWT validation]
    R3 --> API3[Local JWT validation]
~~~

Nodes update their local cache/denylist. New requests can have signatures verified and local state checked without calling the AS directly.

### 16.1. Event Push Is Not Automatically Instant

The revocation window depends on:

- Time to emit the event after the AS commits.
- Broker delivery latency.
- Consumer processing delay.
- Cache update/invalidation.
- Node restarts or disconnections.
- Duplicate, out-of-order, or lost events.
- Replay/snapshot after reconnection.

Event push typically results in **eventual consistency**. Do not claim instant revocation without measuring propagation SLAs.

### 16.2. Events Need Authentication, Replay, and Idempotency

Illustrative payload:

~~~json
{
  "eventType": "ACCESS_TOKEN_REVOKED",
  "issuer": "https://identity.example.com",
  "jti": "token-8f21",
  "expiresAt": 1893456000,
  "eventId": "evt-00421",
  "occurredAt": "2030-01-01T10:02:00Z"
}
~~~

A real implementation requires:

- Authenticating the event source and securing transport.
- Event IDs for idempotent processing.
- Ordering by issuer/user/session if needed.
- Replay or snapshot after reconnection.
- Deduplication and handling stale events.
- TTL cleanup based on `exp`.
- Consumer lag metrics.
- Reconciliation if the local cache is lost.

If the event stream is interrupted, define a policy: fail closed for sensitive operations, accept a measured stale window, or fall back to online introspection. When the consumer reconnects, reconcile state before declaring the node caught up.

## 17. Signing-Key Rotation and JWKS Caching

JWTs are signed with a private key; the Resource Server uses the corresponding public key. The `kid` claim/header helps select a key in JWKS, but **`kid` does not by itself prove a key is trustworthy**. The JWKS URI must belong to the configured issuer.

### 17.1. Normal Rotation

1. Publish the new public key in JWKS.
2. Wait until Resource Servers can fetch the key.
3. AS starts signing tokens with the new private key.
4. Keep the old key long enough for old tokens to expire plus clock-skew/cache margin.
5. Remove the old key after the transition period.

### 17.2. Emergency Rotation

If a private key is compromised, the AS must stop signing with it, remove the public key from trust sources, and switch to a new key. However, Resource Servers may cache the old key, so rejection does not necessarily happen immediately.

Removing a key can affect **every token** signed with that key, not just one user. This has a large blast radius and requires coordinated cache refresh/propagation.

### 17.3. Do Not Rotate Keys to Revoke One Token

A signing key typically serves many users and clients. Rotating keys on every logout can invalidate countless tokens and cause an outage. Use key rotation for key lifecycle/compromise; use `jti`, token versions, introspection, or short TTLs for narrower revocation.

## 18. RFC 7009 Token Revocation Endpoint

OAuth 2.0 Token Revocation under RFC 7009 defines an endpoint for clients to request that the AS revoke a token.

~~~http
POST /oauth2/revoke HTTP/1.1
Host: identity.example.com
Authorization: Basic <client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<token-to-revoke>&token_type_hint=access_token
~~~

The endpoint can accept an access token or refresh token depending on the AS policy.

### 18.1. A Successful Response Does Not Prove Every Resource Server Knows About the Revocation

RFC 7009 is designed so clients cannot easily probe whether a token is valid; the server typically returns success even if the token is already invalid or unrecognized per RFC semantics.

Even once the AS processes the revocation:

- A Resource Server using online introspection can see `active=false` on the next check.
- A Resource Server using pure local JWT verification may continue accepting the token until `exp`.
- A Resource Server with denylist/event integration may reject it once state propagates.
- A Resource Server using caches may still hold stale results.

**Calling the revocation endpoint does not automatically create a mechanism to propagate state to every Resource Server.**

### 18.2. Revoking Refresh Tokens and Related Access Tokens

The AS may manage token families and relationships between refresh and access tokens. Revoking a refresh token prevents new issuances; the AS may also revoke related access tokens per policy. However, clients and Resource Servers must not assume every AS behaves identically. Check the AS documentation and how Resource Servers learn about state changes.

## 19. OIDC Logout Does Not Automatically Invalidate Every Access JWT

OIDC includes RP-Initiated Logout, Front-Channel Logout, and Back-Channel Logout depending on support.

These mechanisms primarily manage sessions at the OP/RP. An API performing only offline JWT verification **does not automatically receive logout notifications** unless explicitly integrated.

If logging out of a portal must cause APIs to reject old tokens quickly, design one of the following:

- Opaque token + introspection.
- `jti` denylist / shared revocation store.
- User/session version check.
- Back-channel or event propagation to Resource Servers.
- Short access token TTL if the remaining window is acceptable.

Do not confuse **RP session logout** with **access token revocation across every Resource Server**.

## 20. Proof-of-Possession Reduces Replay but Does Not Replace Revocation

A Bearer token can be used by whoever holds it. If stolen, an attacker can replay it until it expires or is rejected.

Measures to reduce replay:

- **DPoP**: proof-of-possession binding requests/tokens to a client key per RFC 9449.
- **Mutual TLS-bound access tokens**: binding tokens to certificates per RFC 8705.
- TLS, secure token storage, and XSS prevention.
- Sender-constrained token validation.

Proof-of-possession answers: "Does the request prove possession of the associated key/certificate?". Revocation answers: "Is this token or session still allowed to be used?".

A revoked token must still be rejected even if proof-of-possession is valid. An unrevoked stolen token is much harder to replay if sender constraints are properly implemented.

## 21. Claims and Permissions Can Become Stale

A JWT may contain:

~~~json
{
  "sub": "user-123",
  "scope": "orders.read orders.write",
  "department": "finance",
  "role": "APPROVER",
  "exp": 1893456000
}
~~~

After issuance, a user might change departments, have a role revoked, have their account locked, have their tenant disabled, or see a policy change. If the Resource Server only checks claims in the token, it can rely on stale authorization data until `exp`.

### 21.1. Separate Static and Dynamic Permissions

- Rarely changing permissions with short token TTLs: can be included in the access token.
- Permissions needing rapid updates: check a policy/entitlement service.
- Record-level permissions: check in the domain/service layer.
- Users/sessions needing revocation: check a version/status store or introspection.

Do not put all business data into a JWT merely to avoid database lookups. The more dynamic permissions a token carries, the greater the risk of stale authorization.

### 21.2. Re-check Permissions for Sensitive Operations

For money transfers, approvals, or resource deletion, an unexpired JWT with broad scopes is not necessarily enough. A service may need to verify active user status, tenant, transaction limits, approval state, ownership, and MFA freshness.

An authentication token is one piece of evidence; it does not replace all domain rules.

## 22. Testing Local Validation and Revocation

### 22.1. Testing JWT Validation

Use a JWT signed with a test key to verify:

- Valid signature, valid issuer/audience, unexpired `exp`: authenticates successfully.
- Invalid signature: rejected.
- Wrong issuer: rejected.
- Wrong audience: rejected.
- `exp` passed beyond clock skew: rejected.
- `nbf` in the future beyond clock skew: rejected.
- Disallowed algorithm: rejected.

### 22.2. Demonstrating Local Revocation Limits

A useful integration test:

1. Issue a JWT with a distant `exp`.
2. Send a request to a local-verify-only Resource Server and assert success.
3. Revoke the token at the AS without updating the Resource Server.
4. Resend the old token.
5. Observe that the Resource Server may still accept it because signature/claims did not change.
6. Update the denylist or switch to introspection.
7. Resend the token and assert rejection.

This test demonstrates that **revocation at the issuer and revocation visibility at the Resource Server are two distinct things**.

### 22.3. Testing Denylist Propagation

With multiple instances:

- Send a valid token through nodes A and B.
- Revoke the `jti` in the store.
- Verify both nodes see the new state within the SLA.
- Simulate broker disconnects and node restarts.
- Test replay/snapshot reconciliation.
- Test TTL cleanup based on `exp` and clock skew.
- Ensure duplicate events are idempotent.
- Ensure unauthenticated events cannot mutate the denylist.

### 22.4. Testing Cache Lag

If introspection/revocation state is cached:

- Revoke immediately after a cache hit.
- Measure how long the old token continues to be accepted.
- Test invalidation events.
- Test cache backend outages.
- Test fail-open/fail-closed behavior.
- Verify TTL never exceeds `exp`.

### 22.5. Testing Key Rotation

- Token K1 is accepted while K1 remains in JWKS.
- K2 is published before the AS starts using K2.
- Token `kid=K2` is verified after refresh.
- Token K1 continues working during the normal overlap window.
- After K1 is removed and the Resource Server refreshes its key set, token K1 is rejected.
- For emergency rotation, measure cache invalidation/propagation and blast radius.

Use test private/public keys and a JWKS server; do not use a mocked decoder to conclude that production key caching works properly.

## 23. Common Misconceptions

**"A signed JWT can never be revoked."** It can be revoked via state, introspection, events, or key policy; pure local verification simply does not see the event automatically.

**"Logging out deletes the token from the browser so the token is dead."** A copy of the token elsewhere can still be used until `exp` unless a revocation mechanism exists.

**"Revoking a refresh token immediately invalidates old access JWTs."** Not necessarily; refresh revocation primarily prevents issuing new tokens.

**"Having a `jti` automatically enables revocation."** `jti` is only an identifier; a store/check is required.

**"Removing a key from JWKS revokes just one user."** It can affect every token signed with that key and depends on cache propagation.

**"Introspection is always instantaneous."** Caching, networking, AS replication, and propagation can return stale results.

**"Short TTL is instant revocation."** TTL bounds the window by `exp`/clock skew, not zero lag.

**"Once the event bus publishes a revocation, every node knows."** You must account for consumer lag, missed events, replay, and reconnects.

**"DPoP/mTLS replaces revocation."** They mitigate replay; they do not provide revocation state on their own.

**"Stateless means you cannot check dynamic permissions."** You can look up state, though the decision is then no longer purely stateless.

**"In-flight requests automatically roll back when a token is revoked."** Revocation typically affects subsequent decisions; in-flight work needs its own cancellation/transaction policy.

## 24. Process for Designing Lifecycle and Revocation

**Step 1 — Classify tokens.** JWT signed access token, opaque access token, ID Token, refresh token, or internal token? Never use an ID Token as an access token.

**Step 2 — Choose a validation strategy.** Local JWT validation, online introspection, or local validation combined with state lookups/events.

**Step 3 — Define the revocation SLA.** Revoke a single token, a session, a user, a client, or a signing key? How much lag is acceptable?

**Step 4 — Choose access token TTL.** Balance how long stale permissions remain valid against refresh traffic and UX.

**Step 5 — Design the refresh lifecycle.** Protect refresh tokens, rotation, reuse detection, token family revocation, and logout.

**Step 6 — Choose a revocation mechanism.** `jti` denylist, user/session version, introspection, revocation events, or emergency key rotation.

**Step 7 — Design consistency.** Shared store, cache TTL, event replay, node restarts, broker outages, and fail-open/fail-closed behavior.

**Step 8 — Validate claims and key lifecycle.** `iss`, `aud`, `exp`, `nbf`, `iat`, `jti`, token type, algorithm allowlist, and JWKS rotation.

**Step 9 — Separate authentication from domain authorization.** Re-check tenant/ownership/entitlements for sensitive operations.

**Step 10 — Test failure modes.** Revocation between requests, stale caches, AS outages, key compromise, event loss, multi-node propagation, and in-flight requests.

## Conclusion

**Self-contained JWTs allow a Resource Server to verify signatures and claims locally, but do not automatically detect a recent revocation event at the Authorization Server.** If you use only local validation without supplemental state or events, tokens generally continue to be accepted until `exp`, plus configured clock skew.

You can shrink that window with **short access token TTLs**, but faster revocation requires propagating state to Resource Servers via **introspection, `jti` denylists, token versions, revocation events, or emergency key rotation**. Each option carries costs in networking, state, consistency, caching, and blast radius.

In Spring Security, **JwtDecoder** and its validators verify signature, issuer, audience, and timestamps. They do not replace a revocation store on their own. With WebFlux, keep lookups reactive and never block the event loop.

**A sound design must explicitly state how long a token may still be accepted after revocation, how the Resource Server learns of revocation, and how the system reacts when the state propagation mechanism fails.** If those three questions cannot be answered, "instant revocation" has no concrete technical guarantee.

### References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — OAuth2TokenValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2TokenValidator.html)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
- [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html)
