# Key Overlap Window: Old Keys, New Keys, and Unexpired Tokens

When an **Authorization Server** rotates its JWT signing key, it cannot simply delete the old public key from the JWK Set as soon as it starts signing with the new key. **Access tokens signed with the old key** may still be valid until their `exp` timestamp and actively used by clients calling a **Spring Security OAuth 2.0 Resource Server**. If the Resource Server can no longer find the old verification key, those tokens will be rejected **even though they have not expired**.

The standard solution is a **key rollover with an overlap window**: the Authorization Server publishes the new key before using it, keeps the old key alongside the new key in the **JWKS** while old tokens remain valid, and removes the old key only after all related tokens are no longer acceptable under policy. This lesson explains precisely **when the overlap starts, when it ends, why you cannot look solely at the JWKS TTL**, and how to coordinate the issuing system with Spring Security Resource Server for zero-downtime rotation.

> The primary scope is **JWT access tokens signed with JWS** and verified by a Resource Server using public keys from a **JWK Set**. All issuers, endpoints, key IDs, timestamps, and tokens in the examples are illustrative mock data. If a system uses opaque tokens with introspection, per-request verification works differently, even though JWT key lifecycles in related components still need management.

## 1. From JWT to JWK Set: The Participating Components

A JWT access token in compact JWS form typically consists of three parts:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(JWT_CLAIMS).BASE64URL(SIGNATURE)
~~~

Example JOSE header before encoding:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-signing-2026-11"
}
~~~

Illustrative payload:

~~~json
{
  "iss": "https://idp.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794733200,
  "nbf": 1794733200,
  "exp": 1794735000
}
~~~

The timestamp values in the example serve only to illustrate timing relationships; this is **not** a real token or proof of a valid token. `typ=at+jwt` illustrates a JWT access token conforming to a profile such as RFC 9068; not every Authorization Server emits this exact value, so the Resource Server must know the formal token profile.

| Component | Role in Key Lifecycle | Managed By |
|---|---|---|
| **Signing private key** | Secret key that signs access tokens | Authorization Server; must be kept secret |
| **Public verification key** | Public key used to verify signatures | Published by Authorization Server; retrieved by Resource Server via trusted source |
| **JWK** | JSON format representing a key's parameters, e.g., RSA `n` and `e` | Key/issuer infrastructure |
| **JWKS / JWK Set** | Collection of multiple JWKs, enabling simultaneous publication of old and new keys | Authorization Server |
| **`kid`** | Key identifier in the JOSE header helping locate the right key | Attached at signing time and when publishing the JWK |
| **`alg`** | Signing algorithm declared in the JOSE header | Used by issuer; Resource Server must enforce an allowlist |
| **`iss`** | Issuer that minted the token | Matched by Resource Server against trusted issuers |
| **`exp` / `nbf` / `iat`** | Expiration, not-before, and issued-at timestamps of the token | Token issuance policy and validators |
| **JWKS cache** | Local copy of the public key set held by Resource Server to avoid constant network calls | Resource Server / decoder / infrastructure |

**Removing an old key from the JWKS** does not mean all tokens signed by that key have expired. Conversely, **an old key still being in the JWKS** does not mean a token will be accepted: the JWT must still pass signature verification, issuer, audience, lifetime, token type, and authorization checks.

### 1.1. JWKS Publishes Public Keys, Not Private Keys

Example structure of public RSA JWKs:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-old",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_PUBLIC_MODULUS_OLD>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-key-new",
      "use": "sig",
      "alg": "RS256",
      "n": "<BASE64URL_PUBLIC_MODULUS_NEW>",
      "e": "AQAB"
    }
  ]
}
~~~

The placeholder `n` values are not real RSA public keys. Only appropriate public key fields may be published; **never include private key parameters such as `d`, `p`, or `q`** in a JWKS endpoint. A JWKS can contain multiple keys for rotation and different purposes; the Resource Server must select the right key by `kid`, `kty`, algorithm, and trust policy.

### 1.2. `kid` Is Not Independent Proof of Trust

A token's JOSE header may declare:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-new"
}
~~~

The Resource Server can use `kid` to look up a key in **a JWK Set already configured as trusted**, but must never treat `kid` as proof of issuer, token type, or access rights. An attacker can place any `kid` inside an unverified JWT. **A matching `kid` name is insufficient to authenticate a JWT**; the system must still perform actual signature verification using the right key, permitted algorithm, and associated validators.

## 2. Why Is an Overlap Window Necessary?

Consider a straightforward scenario:

1. The Authorization Server is signing JWTs with private key **K_old**.
2. The Resource Server fetches the JWKS containing public key **K_old** and uses it to verify requests.
3. An access token is signed with K_old at 09:00, with `exp` at 09:30.
4. At 09:10, the Authorization Server begins signing new tokens with **K_new**.
5. If it simultaneously deletes public key K_old from the JWKS, Resource Servers that refresh immediately will lose the key needed to verify tokens issued before 09:10.

The result is **unexpired old tokens failing with 401**, causing intermittent errors across clients depending on when each Resource Server refreshes its JWKS. Instances still caching K_old may temporarily accept the token while other instances reject it—making troubleshooting harder because the same token sometimes works and sometimes fails.

Therefore, the lifecycle of **the key used for signing** and the lifecycle of **the public key retained for verification** are not identical:

~~~text
Signing:
    K_old  ────────────┐
                      └───────────── K_new ───────────────>

Verification JWKS:
    K_old  ───────────────────────────┐
    K_new        ┌────────────────────────────────────────>
                 └───── OVERLAP ─────┘

Tokens:
    K_old-signed tokens ──── may still be unexpired ──────┐
                                                          └─ then remove K_old
~~~

An old private key can be **stopped from signing** as soon as signing switches to K_new, while **its corresponding public key must remain published** as long as K_old-signed tokens can still be valid.

## 3. Four Timestamps That Must Be Aligned

Notation:

| Milestone | Meaning |
|---|---|
| **T_publish_new** | K_new appears in the JWKS so Resource Servers can observe it |
| **T_start_new_signing** | Authorization Server begins signing tokens with K_new |
| **T_last_old_signing** | The **final** timestamp a token is signed with K_old, across **all** issuing nodes |
| **T_remove_old** | K_old is removed from the issuer-published JWKS |

Typical safe ordering:

~~~text
T_publish_new
      |
      |  Time for JWKS caches to pick up the new key
      v
T_start_new_signing
      |
      |  K_old must still remain in JWKS;
      |  some nodes may still sign with K_old during a staggered rollout
      v
T_last_old_signing
      |
      |  Wait for all K_old-signed tokens to expire
      |  + clock skew tolerance + decided safety margin
      v
T_remove_old
~~~

`T_start_new_signing` does not necessarily equal `T_last_old_signing`: in a multi-node cluster, rollouts may be staggered so some nodes still sign with K_old after the first node switches to K_new. Thus, **the anchor timestamp for scheduling old key removal must be the actual last signing time**, not when new-key issuance first started.

### 3.1. Two Distinct Overlap Phases

Two separate intervals typically need tracking:

**Interval A — Prepublication of K_new**: from when the JWKS publishes K_new until the Authorization Server starts signing with K_new. The goal is for Resource Servers/proxies/caches to learn the new key before tokens carrying the new `kid` arrive.

**Interval B — Retaining K_old after signing stops**: from when no node signs with K_old anymore until K_old can be removed from the JWKS. The goal is for **all valid tokens signed with K_old** to continue verifying cleanly.

Interval A depends heavily on **JWKS caching and propagation**. Interval B depends primarily on **maximum token lifetime and time tolerances**. The two intervals **cannot substitute for each other**.

## 4. Calculating a Safe Time to Remove the Old Key

Let:

- `T_last_old_signing`: timestamp when the issuer last signed a token with K_old.
- `L_max_old`: maximum validity lifetime of a token signed with K_old, per the actual token contract.
- `S_validation`: maximum clock skew tolerance permitted by Resource Servers when validating `exp`.
- `M`: additional safety margin for logging lag on issuance timestamps, rolling rollouts, clock differences, or known observation delays.

A **conservative scheduling rule**:

~~~text
T_remove_old >= T_last_old_signing + L_max_old + S_validation + M
~~~

This holds only when:

1. The Authorization Server **truly stops signing with K_old** after `T_last_old_signing`.
2. Every token using K_old obeys the `L_max_old` lifetime limit and has a valid `exp`.
3. Resource Servers bound clock skew within `S_validation`.
4. The contract has no special token types—such as very long-lived tokens or legacy issued tokens lacking `exp`—allowed to use K_old.

If **maximum lifetime cannot be guaranteed**, you cannot derive a key-removal schedule from a single expected TTL number alone. You must audit issuance policies and actual tokens, or apply controlled invalidation/revocation strategies.

### 4.1. Example Calculation in Minutes

Assumptions:

~~~text
Last token signed by K_old: 09:10
Maximum token lifetime:     30 minutes
Verifier clock skew:         2 minutes
Additional safety margin:    8 minutes
~~~

Then:

~~~text
Last K_old token may have exp: 09:40
Verifier may accept until:     09:42
Planned removal time:          from 09:50 onward
                               (09:10 + 30 + 2 + 8)
~~~

Choosing **09:50** is an operational policy example, not a mandatory value from Spring Security or an RFC. If the AS still signs with K_old at 09:25 due to a slow node rollout, **09:10 is no longer accurate**; you must recalculate from the actual last signing time.

### 4.2. Unexpired Tokens Matter More Than the Key-Switch Time

When an issuer signs a JWT at `T_issue`, it embeds `exp`. The Resource Server cannot conclude a token has expired merely because the JWT used K_old. A K_old signature remains completely valid as long as the public key K_old is still trusted.

Conversely, even while K_old **remains in the JWKS**, a JWT with a past `exp` must still be rejected. Only when all of these hold simultaneously:

~~~text
Valid signature with trusted public key
    AND valid issuer/audience/token profile
    AND valid lifetime window
    AND all other required validation conditions
~~~

is the token considered authenticated. Key overlap is a **mechanism to preserve verification capability**, not a way to extend token lifetimes.

## 5. Complete Example Timeline: Transitioning from K_old to K_new

Environment assumptions:

- Issuer: `https://idp.example.test/realms/company`.
- Resource Server: Orders API, expected audience `orders-api`.
- Signing algorithm: `RS256`, distinct key IDs `key-old` and `key-new`.
- Maximum access token TTL: 30 minutes.
- Accepted clock skew: up to 2 minutes.
- JWKS cache staleness across Resource Servers/proxies: up to 5 minutes by known design.
- Additional operational margin before removing K_old: 8 minutes.

| Time | What Does the Authorization Server Do? | Published JWKS | What Must the Resource Server Do? |
|---|---|---|---|
| 08:55 | Signs only with K_old | `[K_old]` | Verifies old tokens normally |
| **09:00** | Generates K_new securely, **publishes K_new without signing yet** | `[K_old, K_new]` | Caches have time to pick up the new JWK |
| **09:10** | Begins signing with K_new; confirms no node signs with K_old | `[K_old, K_new]` | New tokens carry `kid=key-new`; old tokens still verify |
| 09:20 | K_new is the active signing key | `[K_old, K_new]` | Accepts both K_old-signed JWTs (if unexpired) and K_new JWTs |
| **09:40** | Last K_old token reaches assumed maximum `exp` | `[K_old, K_new]` | Skew tolerance may still permit old tokens |
| 09:42 | Assumed 2-minute clock skew window ends | `[K_old, K_new]` | No valid K_old tokens should remain under contract |
| **09:50** | After margin, K_old can be removed under normal process | `[K_new]` | Uses only K_new to verify new valid tokens |

Diagram:

~~~mermaid
gantt
    title Zero-Downtime Rollover Example (Illustrative Times)
    dateFormat HH:mm
    axisFormat %H:%M
    section Signing Keys
    K_old may sign            :a1, 08:55, 15m
    K_new starts signing      :milestone, m1, 09:10, 0m
    K_new signs tokens        :a2, 09:10, 40m
    section Published JWKS
    K_old only                :b1, 08:55, 5m
    K_old and K_new present   :b2, 09:00, 50m
    K_new only                :b3, 09:50, 10m
    section K_old Tokens
    Last token usable window  :c1, 09:10, 32m
    Margin before key removal :c2, 09:42, 8m
~~~

This timeline **assumes a maximum 5-minute cache staleness**. Pre-publishing K_new 10 minutes early provides a buffer, but in real systems you must verify JWKS refresh timings, gateway/CDN caches, network partitions, unknown-`kid` handling, and the state of all nodes. Never apply a fixed schedule blindly without knowing those bounds.

### 5.1. Why Not Simply "Wait 5 Minutes Because JWKS Cache TTL Is 5 Minutes"?

**JWKS cache TTL** answers "how long can the Resource Server keep a fetched copy of the key set?" **JWT TTL** answers "until when is an issued token valid?" The two quantities have different meanings:

~~~text
JWKS cache TTL = 5 minutes
JWT TTL        = 30 minutes
~~~

After 5 minutes, the Resource Server can pick up the new key. Yet a JWT signed with K_old **at the very end of its issuance window** remains valid for another 30 minutes plus clock skew. Deleting K_old after 5 minutes breaks verification of unexpired tokens.

Conversely, keeping K_old for 30 minutes without pre-publishing K_new long enough—or without cache refresh on unknown `kid`—still causes initial K_new tokens to fail. **Both halves of the rollover must be handled together.**

## 6. JWKS Caching, Propagation, and New `kid`s

A Resource Server generally does not fetch the JWKS over the network for **every JWT**. The decoder may hold keys in memory or rely on a cache managed by the library or JWK source. When running multiple instances, each instance also maintains **its own cache state**.

~~~mermaid
flowchart LR
    AS["Authorization Server<br/>JWKS: K_old + K_new"] --> CDN["CDN / reverse proxy cache<br/>(if present)"]
    CDN --> RS1["Resource Server instance A<br/>JWKS cache"]
    CDN --> RS2["Resource Server instance B<br/>JWKS cache"]
    CDN --> RS3["Resource Server instance C<br/>JWKS cache"]
    C["Client sends JWT<br/>kid=K_new"] --> LB["Load balancer"]
    LB --> RS1
    LB --> RS2
    LB --> RS3
~~~

If instance A has refreshed its JWKS while instance B has not, a new token with `kid=K_new` may succeed on A and fail on B. If K_old was deleted while instance A still caches the old key set, the reverse occurs: A can still verify old tokens while B has already refreshed and lost K_old.

### 6.1. Factors That Increase Propagation Lag

| Layer | Source of Lag | Consequence During Rollover |
|---|---|---|
| Authorization Server cluster | Nodes publish JWKS or switch signing keys asynchronously | One node signs with K_new while another still serves only K_old |
| CDN/reverse proxy | Cache-Control, TTL, stale-while-revalidate, uneven purging | Updated JWKS has not reached Resource Servers |
| Resource Server JVM | In-memory cache of decoder/JWK source | Individual instances see different key sets |
| Networking | DNS/TLS/timeouts/proxies/firewalls | Unable to fetch JWKS when a new key appears |
| Clocks | Time drift across nodes | Expands or shrinks `exp`/`nbf` acceptance windows |
| Deployment | Rolling rollouts, mixed config versions | K_old may still be used past the planned cutoff |

Therefore, when sizing **T_publish_new → T_start_new_signing**, base it on the actual bounds of the entire pipeline, not merely the HTTP `max-age` returned by one issuer node.

### 6.2. Handling Tokens with an Unknown `kid`

When a Resource Server receives a JWT signed with K_new while its cache holds only K_old, the decoder/JWK source may **attempt a JWKS refresh** if the implementation supports it. However:

- Not every version or custom decoder refreshes identically.
- A proxy or CDN might still serve a **stale JWKS copy** even when the decoder sends a fresh GET.
- The refresh itself can fail due to DNS, TLS, or timeouts.
- If the issuer publishes K_new **after** signing with K_new, refreshes before publication are futile.
- If K_new uses an algorithm outside the decoder's allowlist, having the new key still will not allow authentication to succeed.

**Do not skip prepublication on the assumption that "unknown `kid` will auto-refresh."** The safe rollout path is publishing K_new early enough, confirming Resource Servers see the key, and only then activating signing with K_new.

### 6.3. Paying Attention to JWKS Endpoint Response Caching

A JWKS endpoint might return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "jwks-version-17"
~~~

Here `max-age=300` equals 5 minutes under HTTP caching, yet **that does not mean every Java decoder automatically adopts that exact TTL**, nor does it guarantee proxies have no extra caching rules. `ETag` supports conditional requests if clients/proxies apply HTTP caching appropriately.

Specifically, **`Cache-Control` permits caching public keys, never private signing keys**. Never place client secrets or private key material in a JWKS response simply because the endpoint is reachable.

### 6.4. Synchronizing Caches Across Multiple Resource Servers

In a multi-service architecture, establish:

1. Which issuer's JWKS each service consumes?
2. Is there a shared proxy/CDN, or does each service call the issuer directly?
3. How long are caches valid, and do they refresh on a new `kid`?
4. Can the AS safely roll back to K_old if needed?
5. How far in advance is a new key published before actual signing begins?
6. How do we observe that every service/instance has updated its JWKS without logging tokens?
7. During a JWKS endpoint outage, can services verify JWTs whose valid keys are already cached, and when must they fail closed?

A good way to de-risk rollouts is using a staging environment matching production networking and caching, issuing test JWTs with K_new, and confirming authorized Resource Servers verify them cleanly **before promoting K_new to primary signing key**.

## 7. Configuring Spring Security Resource Server to Live Through Rollovers

In Spring MVC/Servlet, Spring Security typically uses `NimbusJwtDecoder` to verify JWTs against a JWK Set. When configured by issuer, the application can retrieve keys via the trusted issuer's metadata/discovery. When the JWK Set path is known upfront, both issuer and JWKS URI can be declared together.

### 7.1. Required Dependencies

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 7.2. Configuring Issuer and JWK Set URI

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/company
          jwk-set-uri: https://idp.example.test/realms/company/protocol/openid-connect/certs
~~~

Explanation:

- `issuer-uri` identifies the **trusted issuer** and enables Spring Security to enforce the appropriate issuer policy.
- `jwk-set-uri` specifies the fixed JWK Set URL published by the Identity team. Depending on the Boot/Security version, setting both avoids discovery dependencies at startup while retaining issuer validation.
- The JWK Set can contain **both K_old and K_new simultaneously**. The decoder picks the matching key from the set according to the JOSE header and verification policy; the application should never hardcode a single `kid` during rollover.

**Critical:** `jwk-set-uri` is not a substitute for `issuer-uri`. When manually constructing a `JwtDecoder` from a JWKS URI, preserve an explicit issuer validator. Beyond issuer, the Resource Server should also check audience per the API contract.

### 7.3. Endpoint Protection Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

With this configuration, the JWT is authenticated before `orders.read` scope is mapped to `SCOPE_orders.read`. A token signed with K_old **can still be accepted** if public key K_old remains in the trusted source, the signature is valid, expiration has not passed, issuer/audience match, and scopes suffice. The same holds for a token signed with K_new.

Spring Security **does not issue, rotate, or delete signing keys itself**. Publishing the JWK Set and deciding which private key signs JWTs belong to the Authorization Server. The Resource Server is responsible for maintaining a trusted key source and validating requests according to policy.

### 7.4. Customizing `JwtDecoder` While Allowing Multiple JWKs

Suppose the Orders API also needs audience validation and signing-algorithm restriction:

~~~yaml
app:
  security:
    jwt:
      issuer: https://idp.example.test/realms/company
      jwk-set-uri: https://idp.example.test/realms/company/protocol/openid-connect/certs
      audience: orders-api
~~~

`app.security.jwt.*` is a namespace defined by this sample application, **not** built-in Spring Boot auto-configuration properties.

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwks,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> expectedAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token not intended for Orders API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                expectedAudience
            )
        );
        return decoder;
    }
}
~~~

This **replaces the Boot auto-configured decoder**. When this bean is registered, the application's `JwtDecoder` bean is normally used, and default properties are not automatically merged into every validator of the custom bean. That is why the example explicitly calls `JwtValidators.createDefaultWithIssuer(...)` to retain issuer and time checks, then adds the audience validator.

During rollover, a JWKS holding both K_old and K_new lets the decoder find the corresponding public keys; **no Java code changes are needed per `kid`**. If the AS switches to a new JWS algorithm, allowed algorithms must be agreed upon and explicitly configured; merely publishing another JWK does not expand the algorithm allowlist.

**Never write a custom "key-selecting" decoder that fetches a JWK URL from an unverified JWT `jku` header.** The JWKS URI must originate from trusted configuration or issuer metadata, never from arbitrary client input.

### 7.5. Nimbus and Spring Security Cache Durations

Across different Spring Security/Nimbus versions, there may be default JWK caching, cache customization hooks, HTTP client options, and unknown-`kid` refresh behaviors. Never rely on a blanket constant like "JWKS is always cached for 5 minutes" across all deployments.

When exact bounds are needed, determine:

- The exact `spring-security-oauth2-jose` and Nimbus versions in use.
- Whether the decoder is Boot auto-configured or application-defined.
- Which HTTP cache/proxy and custom `Cache` are present.
- Behavior when a token arrives with a `kid` absent from the cache.
- Retry, timeout, and reload policies toward the JWKS endpoint.
- How successful key refreshes are monitored across all instances.

Cache bounds are **operational parameters** for sizing `T_publish_new`, never a reason to skip token expiration or issuer checks.

## 8. Spring WebFlux: Key Lifecycle Principles Remain Unchanged

On Spring WebFlux, the Resource Server uses `ReactiveJwtDecoder`—typically `NimbusReactiveJwtDecoder`—and the security chain uses `SecurityWebFilterChain`.

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

`issuer-uri` and `jwk-set-uri` properties remain part of JWT Resource Server configuration. If defining a reactive decoder manually, use `ReactiveJwtDecoder`/`NimbusReactiveJwtDecoder` with appropriate issuer/time/audience validators; never register a Servlet `JwtDecoder` bean in a WebFlux stack expecting it to process reactive requests.

Rollover must still ensure:

1. K_new is published early enough before signing.
2. K_old stays published until no K_old JWT can still be valid.
3. Source, algorithm, issuer, and audience are still validated.
4. Reactive caches and HTTP clients are properly configured and monitored.

The difference between Servlet and WebFlux lies mainly in **programming APIs and HTTP processing models**, not in JWT key lifecycle security rules.

## 9. Routine Key Rotation, Key Revocation, and Key Compromise Are Three Different Scenarios

An overlap plan makes sense when K_old is **not compromised** and the organization rotates keys on schedule. If the old private key has been compromised, security requirements may **prioritize immediate revocation** even if valid tokens experience disruption.

| Scenario | Goal | K_old in JWKS |
|---|---|---|
| **Routine rotation** on schedule | Zero disruption verifying unexpired tokens | Retain until K_old tokens expire + skew/margin |
| **Emergency rotation** due to suspected private key leak | Block attackers from forging JWTs | May need immediate removal/trust revocation per incident response |
| **Old key reaches usage-period limit** without compromise | Stop issuing new tokens, preserve existing tokens | Decouple new signing authority from old-token verification |
| **Revoking one specific access token** | Block a leaked or de-authorized token | Do not necessarily remove K_old entirely; requires a token revocation policy |
| **Changing issuer/tenant trust boundaries** | Migrate trusted issuing authority | Requires a dedicated migration policy; not merely changing `kid` |

### 9.1. Why Can't You Just Keep K_old If the Private Key Leaked?

Once private key K_old is compromised, an attacker can mint fresh JWTs signed with K_old, setting arbitrary `exp`, `scope`, and other claims. If Resource Servers keep trusting public key K_old, merely "waiting for old tokens to expire" **is not enough to stop forged tokens** unless other controls exist such as denylists, token age caps, token inventories, or disabling the signing key at the verifier layer.

In that situation, incident responders may choose to:

- Remove K_old from the JWKS and force Resource Servers to refresh/invalidate caches.
- Revoke trust in K_old at the decoder/configuration level if supported.
- Revoke sessions/tokens and require clients to acquire new tokens via valid flows.
- Shorten acceptance windows for older tokens or temporarily block sensitive endpoints.
- Audit trails to determine blast radius.

**This may cause unexpired K_old tokens to return 401**. It is a deliberate availability-versus-security trade-off during incident response. Never mechanically apply routine rollover rules once compromise is evidenced.

### 9.2. Why Does Removing a Public Key from JWKS Not Take Effect Immediately?

Resource Servers may still hold a JWKS snapshot containing K_old in cache. Simply deleting K_old from the issuer endpoint without refreshing trust/caches on verifiers lets some instances keep accepting tokens signed with K_old.

During an incident:

~~~text
AS removes K_old from JWKS
    |
    +--> RS instance A refreshes right away, stops trusting K_old
    |
    +--> RS instance B still caches K_old, continues verifying old tokens
    |
    +--> Gateway/CDN holds a stale copy returning K_old
~~~

Hence, emergency revocation procedures must include **cache/trust invalidation plans** across Resource Servers and proxy layers, or compensating architectural controls. "The JWKS changed" reflects only the publishing source, not that every verifier has updated state.

### 9.3. Distinguishing Signing Keys from Revoked Access Tokens

Self-contained JWTs are typically verified **locally** by the Resource Server. When an Authorization Server revokes a single access token, the Resource Server cannot tell from the signature and `exp` alone without dedicated revocation propagation, denylists, or introspection.

Removing K_old from the JWKS impacts **all tokens signed with K_old**, not just one stolen token. If the objective is revoking an individual token, you need an appropriate token revocation strategy—such as short access token TTLs, `jti` denylists in certain architectures, or real-time validation per policy.

## 10. Controlled Key Rollover Deployment Procedure

Routine rollover requires coordination among at least three parties: the **Authorization Server team**, the **Resource Server team**, and the **infrastructure/caching operations team**. In enterprises with many APIs, one issuer may serve dozens of Resource Servers, so merely announcing "a new key was created" is not enough.

### Phase A — Preparation Before Publishing the New Key

The Authorization Server team verifies:

1. Official issuer and JWKS URI for the environment.
2. Currently active signing keys, their `kid`s, and algorithms.
3. **Actual maximum** access token TTL; are there any grant, client, tenant, or token-profile exceptions?
4. Whether JWTs require `exp`, and what clock skew tolerance is allowed.
5. Whether all issuing nodes share the same signing key configuration.
6. Which team has authority to activate K_new, retire K_old, and trigger emergency revocation.

The Resource Server team confirms:

1. Which JWKS URI the decoder fetches public keys from, and whether issuer/audience are validated.
2. Whether JWKS caching happens only in the JVM or also in gateways/CDNs/proxies.
3. Whether the runtime refreshes keys upon seeing a new `kid`.
4. Whether key rotation entails any changes to `alg`, token profile, audience, or issuer.
5. Whether any system pins public key K_old statically rather than following dynamic JWKS.
6. Whether telemetry classifies validation/JWKS failures without exposing tokens.

If a service pins a static public key with no update plan, merely publishing K_new in the JWKS **does not guarantee** that service will accept K_new-signed JWTs. The trust source must be updated across every affected Resource Server.

### Phase B — Generate K_new and Pre-Publish

Generate the key pair using an approved key management system (KMS/HSM or authorized solution), protect the private key, and assign a new `kid` **never reused for another key**. Publish **public JWK K_new** alongside K_old:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-old",
      "alg": "RS256",
      "use": "sig",
      "n": "<OLD_PUBLIC_MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-new",
      "alg": "RS256",
      "use": "sig",
      "n": "<NEW_PUBLIC_MODULUS>",
      "e": "AQAB"
    }
  ]
}
~~~

During this phase, the Authorization Server **continues signing tokens with K_old**. The goal is to give verifiers time to load K_new while clients see no change in issued tokens.

### Phase C — Activate K_new for Signing

Once the prepublication window is safely complete:

- Switch signing configuration to K_new, while **retaining K_old in the JWKS**.
- Confirm all Authorization Server nodes have stopped signing with K_old.
- Record **T_last_old_signing** from reliable audit/metric sources rather than guessing from rollout start time.
- Monitor unknown-`kid`, invalid-signature, issuer/audience, and 401 metrics on Resource Servers.
- If a brief rollback to K_old occurs, record the new final signing timestamp and keep both public keys in the JWKS.

When K_new becomes the active signer, do not invalidate previously K_old-signed tokens merely because clients haven't refreshed yet. Clients remain entitled to use K_old access tokens until they expire or are revoked under policy.

### Phase D — Wait for Old Tokens to Expire

Continue publishing **both K_old and K_new**. Compute retirement timing from:

~~~text
Last actual signing with K_old
+ longest legitimate lifetime of K_old JWT
+ maximum accepted clock skew
+ documented safety margin
~~~

Do not rely solely on default token TTL if the system has:

- Longer-lived service-to-service tokens than user tokens.
- Special-scope tokens with differing lifetimes.
- Unsynchronized Authorization Server cluster nodes.
- An issuer signing both access tokens and other JWT types with K_old that Resource Servers still expect to verify.
- Tokens renewed without re-signing or with distinct age acceptance rules.

**Refresh tokens are usually not JWT access tokens and are not verified by the Resource Server's same pipeline.** If the issuer shares the same key pair across other JWT types, the retirement schedule must cover **every token type still allowed to verify with that key**, not just Orders API access tokens.

### Phase E — Remove K_old and Monitor

Once time and policy safety conditions are satisfied:

1. Remove public JWK K_old from the JWKS.
2. Verify signing services can no longer sign with private key K_old.
3. Monitor JWKS refreshes, `kid=key-old` errors, and rejected requests after cutover.
4. Execute old private key management/decommissioning per organizational policy; do not necessarily purge required audit/backup records.
5. Update key lifecycle records with activation, signing-stop, retirement timestamps, and approvers.

Note that **not every 401 with `kid=key-old` after retirement is an error**: if the token is already expired, rejecting it is right. What matters is whether contract-valid tokens are rejected due to premature retirement or unexpected key-source/cache behavior.

## 11. Rollback: What Happens If You Must Revert to K_old?

Distinguish two kinds of rollback:

**Signing rollback**: the Authorization Server temporarily reverts to signing with K_old because K_new hit an issue. This is viable only if **private key K_old remains uncompromised, has not been deactivated**, and K_old is still present in the JWKS. After rollback, `T_last_old_signing` must be updated to the new final K_old signing time.

**JWKS publication rollback**: the JWKS accidentally drops K_old/K_new or publishes malformed data and must be restored. Restoring an older JWKS containing only K_old while the Authorization Server is already signing with K_new will immediately break K_new tokens on refreshed instances. Restoration must account for **every active signing key and unexpired token**.

| Scenario | Risk | Principled Handling |
|---|---|---|
| K_new already issued, JWKS rolled back to K_old only | New JWTs fail verification | Restore JWKS containing both K_old and K_new |
| Signer rolled back to K_old after retirement was calculated | New K_old tokens have later `exp` | Recalculate `T_last_old_signing` and `T_remove_old` |
| K_old was compromised and revoked | Reverting to K_old reopens exposure | Never roll back to a compromised key; deploy another safe key |
| Resource Server cached a broken JWKS | Inconsistent auth results across instances | Restore JWKS/trust source and trigger controlled cache refresh |
| Changed `alg` alongside key rotation | Decoders reject the new algorithm | Update verifier allowlists before switching signer per policy |

In a well-governed architecture, **key rollover is a versioned change with a rollback plan**. Never reuse an old `kid` for new key material to "avoid touching clients"; that introduces ambiguity in key selection and caching and makes incidents hard to diagnose.

## 12. Changing the Signing Algorithm or Key Type Simultaneously

Rotating K_old → K_new with the **same algorithm** is simpler than switching RSA to EC or `RS256` to `ES256` at the same time. When changing algorithms:

~~~text
Before:
  K_old = RSA / RS256

After:
  K_new = EC / ES256
~~~

Ensure the Resource Server:

- Trusts a JWK Set containing both the old RSA key and the new EC key during the overlap window.
- Allows the exact required JWS algorithms; never open up arbitrary algorithms.
- Runs JOSE library/JDK versions supporting the new algorithm.
- Continues validating `iss`, `aud`, `exp`, `nbf`, and token type.
- Does not use a custom RSA-only verifier to validate EC tokens.

A safe rollout typically proceeds as:

~~~text
1. Prepare Resource Servers to accept both approved RS256 and ES256.
2. Publish the new EC public JWK alongside the old RSA public JWK.
3. Wait for propagation/caching.
4. Switch the Authorization Server to sign with ES256.
5. Wait for remaining valid RS256 tokens to expire, plus skew and margin.
6. Remove the old RSA public JWK; only then remove RS256 support if policy permits.
~~~

Do not update the signer to ES256 only to discover Spring Security is configured with:

~~~java
NimbusJwtDecoder.withJwkSetUri(jwks)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

In this example, the decoder is pinned to RS256, so it rejects ES256-signed tokens even when the JWKS contains the new EC key. Updating the algorithm allowlist is an explicit part of the rollout plan—it never adapts automatically just because K_new appears.

**Changing `alg` also does not change `iss`, `aud`, or scopes.** Other token-contract changes require separate migrations to avoid stacking multiple failure modes onto a single key release.

## 13. Multiple Issuers: Overlap Must Be Calculated per Trust Source

Suppose Orders API accepts tokens from:

~~~text
Issuer A: https://idp.example.test/realms/company
Issuer B: https://partners.example.test/oauth2/default
~~~

Each issuer has its own JWKS, `kid`s, rotation schedule, token TTLs, and policies. Never pool keys from multiple issuers into one shared set and drop `iss` checks. Issuer A's `kid` could collide in name with Issuer B's `kid`, yet they are not the same key identity.

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Read iss as untrusted routing hint"]
    B --> C{"Is issuer in allowlist?"}
    C -->|No| D["Reject"]
    C -->|Yes| E["Select that issuer's decoder and JWKS"]
    E --> F["Look up kid in the matching JWKS"]
    F --> G["Verify JWS and iss/aud/time validators"]
    G --> H["Build Authentication"]
~~~

Spring Security Servlet offers issuer-based resolution such as `JwtIssuerAuthenticationManagerResolver`; production systems must configure a trusted issuer registry and per-issuer audience and algorithm mappings. **An unverified `iss` claim may serve as a routing hint to pick a resolver, never as proof of trust before signature validation succeeds.**

Issuer A's `T_last_old_signing` does not determine retirement for Issuer B. Each issuer may be in a completely different phase of rollover.

## 14. Relationship Between JWKS Rollover and OIDC

In OpenID Connect, an OpenID Provider publishes `jwks_uri` in discovery metadata and may use those signing keys for **ID tokens**, JWT access tokens, or other JWTs depending on issuer setup. However:

- **ID tokens target the OIDC client**, not a Resource Server's access token.
- Resource Servers must validate access tokens issued for the API's audience under the accepted token profile.
- Never send an ID token to an API simply because its signature verifies against the same JWKS.
- If an issuer shares signing keys across multiple JWT types, K_old retirement must account for **all unexpired tokens** accepted by responsible relying parties and verifiers.
- Some providers separate signing keys across ID tokens, access tokens, or environments/tenants; consult the metadata and contract for each token type.

Key rollover manages **signature verification material**, not a license to blur semantics across OAuth 2.0 access tokens, OIDC ID tokens, and refresh tokens.

## 15. Operational Symptoms When Overlap Timing Is Wrong

### 15.1. K_new Tokens Return 401 Immediately After Switching Signer

Common causes:

1. K_new is not yet in the JWKS retrieved by the Resource Server.
2. JWKS caches/CDNs still serve the old key set.
3. Resource Server does not refresh on an unknown `kid`.
4. New signing algorithm is outside the decoder's allowlist.
5. JWK `kid`, `use`, `kty`, or key material is misconfigured.
6. Token has a mismatched issuer/audience/profile unrelated to JWKS itself.

Resolve by inspecting the **actual JWKS observed by each instance**, key selection, and validator results. Never disable signature validation or allow every algorithm as a quick workaround for 401s.

### 15.2. K_old Tokens Start Returning 401 After Removing the Public Key

This indicates K_old may have been **removed too early** while unexpired tokens remained. Typical causes:

- Measuring from `T_start_new_signing` instead of `T_last_old_signing`.
- Assuming a 15-minute default TTL while some clients receive 60-minute tokens.
- Forgetting clock skew or token profiles with longer lifetimes.
- An Authorization Server node kept signing with K_old after the rollout.
- Removing K_old from JWKS while clients hold valid older tokens.

If K_old was **not compromised**, recovery may involve temporarily re-publishing public JWK K_old under an approved plan and adjusting the retirement timestamp. If K_old was compromised, never restore trust solely to reduce 401s.

### 15.3. Same Token Alternates Between 200 and 401

This happens when a Resource Server sits behind a load balancer and instances hold diverging JWKS caches:

~~~text
Instance A: [K_old, K_new]  -> K_new JWT valid
Instance B: [K_old]         -> K_new JWT missing key
Instance C: [K_new]         -> unexpired K_old JWT fails
~~~

Test with a policy-compliant test token, inspect each instance's config and caching path, and confirm what the issuer JWKS currently publishes. Do not treat sticky sessions as a fix; they merely mask cache divergence across instances.

### 15.4. Valid Signature, Yet 403

If a JWT authenticates with a matching `kid` but lacks a required scope or role, the Resource Server usually returns **403 Forbidden**. That is an authorization issue, not necessarily related to key rollover. Separate three layers:

| Layer | Handler | Typical Signal |
|---|---|---|
| Missing key/issuer/time/audience | Authentication / JWT decoder | Usually 401 |
| Valid token, missing scope/role | HTTP/method authorization | Usually 403 |
| Valid token and scope, lacks resource ownership | Domain authorization | 403 or 404 per policy |

For network failures fetching JWKS, the HTTP status may differ from an invalid-token response depending on exception handling. Regardless of HTTP status, **never let a request with an unverified JWT enter business logic as an authenticated principal**.

## 16. Scenario Matrix for Rollover Integration Testing

Testing one successful K_new token is not enough to prove the overlap works safely. Cover each phase:

| Scenario | JWKS Observed by Resource Server | JWT Sent | Expected Behavior |
|---|---|---|---|
| Before prepublication | K_old only | K_old-signed token, unexpired, policy-valid | Authentication succeeds |
| Just published K_new | K_old + K_new | K_old-signed token | Still authenticates |
| During overlap | K_old + K_new | K_new-signed token | Authentication succeeds |
| During overlap | K_old + K_new | Expired K_old token | Rejected due to `exp` despite key presence |
| Unrefreshed cache | K_old only | New K_new-signed token | May need refresh; outcome must be controlled |
| K_old removed too early | K_new only | Unexpired K_old token | Risk of 401 — undesirable in routine rotation |
| After scheduled retirement | K_new only | Expired K_old token | Rejected by time validation; no longer relies on K_old |
| After retirement | K_new only | Valid K_new token | Authentication succeeds |
| Tampered signature/payload | K_old + K_new | Modified JWT | Rejected |
| Wrong issuer | K_old + K_new | JWT signed with known key, wrong `iss` | Rejected |
| Wrong audience | K_old + K_new | JWT meant for Billing API | Rejected at token validation |
| Disallowed algorithm | JWK exists, disallowed `alg` | JWT signed with another algorithm | Rejected |
| Same token across 2 instances | One warm new cache, one old cache | K_new-signed token | Surface inconsistency; prevent alternating failures |
| JWKS endpoint timeout | Cache has or lacks needed key | Valid JWT | Never pass unverified tokens; observe network failures separately |
| Emergency compromise | K_old trust revoked | Unexpired K_old-signed token | Rejected per incident policy |

### 16.1. Distinguishing Decoder Tests from HTTP Authorization Tests

A Spring Security test might mock `JwtAuthenticationToken` or use the `jwt()` request post-processor to test `hasAuthority("SCOPE_orders.read")`. Such tests **bypass signature verification and JWKS lookup**, so they do not prove key rollover works.

To test **actual JWKS rollover**, an integration suite can:

1. Generate two dedicated test key pairs K_old and K_new.
2. Run a test issuer/JWKS endpoint capable of serving `[K_old]`, `[K_old, K_new]`, and `[K_new]`.
3. Mint test JWTs with the matching private keys and appropriate `kid`, `iss`, `aud`, `exp`, and `scope`.
4. Have the real Resource Server (or real decoder) verify against the test JWKS endpoint.
5. Simulate stale caches and key-switch timing.
6. Confirm unexpired JWTs succeed throughout overlap while expired JWTs are still rejected.

Never use production private keys in integration tests. If tests manipulate time, inject an explicit clock into supporting components rather than altering the host OS clock.

### 16.2. Which Telemetry Should You Observe?

Use safe metadata-level metrics, traces, and audits:

- Timestamp when K_new is published in JWKS.
- Timestamp when K_new signing starts and **when K_old was last actually used to sign**.
- Token issuance counts by `kid` and token TTL/profile category, **without logging raw tokens**.
- Counts of unknown `kid`, missing key, signature, issuer, audience, and expired-token errors.
- JWKS fetch/refresh durations and network error rates.
- Divergence across Resource Server instances.
- HTTP 401 and 403 counts per service before, during, and after cutover.

When logging `kid` as metadata, log only from controlled key sets/issuers or enforce strict sanitization bounds because `kid` in an unverified request token can contain arbitrary input. Never record complete JWTs, private keys, or other credentials in dashboards or traces.

## 17. Practical Decision Formulas

For an old key used to sign JWT access tokens, separate two gates:

### 17.1. Condition to Start Signing with the New Key

~~~text
Allowed to start signing K_new
    =
    K_new is published in the trusted JWKS
    AND required verifiers can retrieve K_new
    AND algorithm/key type is supported by Resource Servers
    AND issuer/audience/profile are not unexpectedly altered
    AND error observability and approved rollback exist
~~~

Do not rely on a single criterion like "added the JWK to JWKS once" when your architecture spans multi-tier caches and multiple nodes.

### 17.2. Condition to Remove the Old Key

~~~text
Allowed to remove K_old in normal rotation
    =
    No issuer node is still signing with K_old
    AND actual last K_old signing time is known
    AND all potentially valid K_old JWTs are past exp
    AND clock skew and safety margin have elapsed
    AND no other token profile/client still needs K_old verification
    AND operational policy permits retirement
~~~

When maximum lifetime is strictly bounded:

~~~text
T_remove_old >=
    T_last_old_signing
    + L_max_old
    + S_validation
    + M
~~~

If a key is compromised, **"preserving unexpired tokens"** may yield to incident response policy: revoke K_old trust early, invalidate caches, and accept the impact on availability.

## 18. Common Misconceptions

**"We rotated the private signing key, so we can delete the old public key immediately."** False for routine rotation. Previously signed tokens remain valid until `exp` and need the old public key for verification.

**"JWKS cache TTL is 5 minutes, so keeping the old key for 5 minutes is enough."** False. Cache TTL governs how often verifiers refresh keys, whereas retaining K_old depends on the lifetime of K_old-signed tokens.

**"Old tokens automatically re-sign themselves when clients refresh."** No. An issued JWT is an immutable string; it keeps its K_old signature. Clients can obtain a **new** token via the proper flow, but existing tokens are never re-signed in place.

**"Keeping the old key in the JWKS lets expired tokens keep working."** No. Resource Servers still check `exp`, `nbf`, and other validators. The public key only enables signature verification.

**"Deleting K_old from the JWKS makes every verifier stop trusting K_old instantly."** Not necessarily: JVM, gateway, or CDN caches may retain older copies. Emergency revocation requires corresponding cache/trust invalidation.

**"`kid` is globally unique across the Internet."** No. It is a key identifier within the scope of a JWK Set/issuer and must be kept unambiguous within system boundaries. Never use `kid` in place of issuer validation.

**"Allowing all algorithms avoids errors during key changes."** No. Resource Servers must maintain an approved algorithm allowlist; changing algorithms is a deliberate migration.

**"If the JWT signature is valid, it is definitely meant for this API."** No. The token can still fail `iss`, `aud`, token type, or scope checks. Signature verification is only one condition of authentication.

**"We can always roll back to K_old even if its private key leaked."** Unsafe. Once K_old is compromised, the priority is revoking trust and replacing it with another secure key.

**"All JWTs share the same TTL as user access tokens."** No. An issuer may mint several JWT types with different lifetimes and audiences. If the same signing key is shared, retirement must wait for every valid verifier/token served by that key.

## 19. Practice Scenarios

Suppose a system has these parameters:

~~~text
Issuer:              https://idp.example.test/realms/company
Orders API audience: orders-api
Old signing key:     K_old
New signing key:     K_new
Max JWKS cache staleness (measured/defined): 7 minutes
Max access token TTL:                        45 minutes
Max validator clock skew:                    3 minutes
Operational safety margin:                   5 minutes
~~~

### Question 1 — K_new is published at 10:00; can we start signing with K_new at 10:01?

Do not assume it is safe. If some Resource Server JWKS caches can remain stale for up to 7 minutes, they may not observe K_new at 10:01. Wait long enough for policy-defined propagation (with verification) before activating K_new; in this example, choose a window longer than 7 minutes rather than one minute.

### Question 2 — Every node stops signing with K_old at 10:12. When can K_old be removed by formula?

~~~text
T_last_old_signing = 10:12
L_max_old          = 45 minutes
S_validation       =  3 minutes
M                  =  5 minutes

T_remove_old >= 10:12 + 45 + 3 + 5 = 11:05
~~~

This is the **earliest time under the stated assumptions**, not an unconditional guarantee. If another token type signed with K_old has a longer TTL, or a node keeps signing past 10:12, 11:05 must be recalculated.

### Question 3 — At 10:50, JWKS still holds K_old and K_new; will a K_old JWT with `exp=10:40` be accepted?

No, once past expiration and allowed skew tolerance. Having K_old in the JWKS only enables **signature verification**; it never extends a token's validity window.

### Question 4 — At 10:50, a client holds a K_old JWT with `exp=10:55`; is it safe to delete K_old immediately?

For **routine rotation**, no: the JWT remains valid until `exp` plus skew, so removing the old key risks unexpectedly rejecting valid requests. If **private key K_old was compromised**, early removal may be required under incident policy.

### Question 5 — K_new tokens return 401 while K_old tokens work; should we relax rules to `permitAll`?

No. Inspect the JWKS source seen by the Resource Server, the new `kid`, allowed `alg`, issuer/audience/time validators, and cache refresh behavior. Disabling authentication or setting `permitAll` breaks the API's security boundary.

## 20. Conclusion

In a JWT-based OAuth 2.0/OIDC Resource Server system:

- **The new signing key is published before use** so Resource Servers can learn the key and prepare caches/algorithms.
- **The old signing key can stop minting tokens as soon as the switch occurs**, yet the old public key **must remain published** during routine rotation while K_old-signed tokens can still be valid.
- **How long the old key stays depends on actual final signing time, maximum token lifetime, clock skew, and operational margin**, not solely on JWKS cache TTL.
- **Spring Security Resource Server must continue validating signature, key source, issuer, audience, lifetime, token profile, and scopes**, even while the JWKS holds both old and new keys.
- **Key compromise is the critical exception**: when a private key leaks, security may require revoking trust early, actively invalidating unexpired old tokens, and purging cached keys no longer permitted for trust.

The two intervals requiring separate management are **prepublication of K_new** and **post-signing retention of K_old**. Designing both properly allows rotating JWT signing keys without creating rejection windows for still-valid access tokens, and without relaxing mandatory authentication checks to preserve availability.

## References

- [RFC 7517 — JSON Web Key (JWK) and JWK Set](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — NimbusJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
