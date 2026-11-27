# Controlling JWKS Caching and Handling Clients That Have Not Updated Keys

> **Chapter:** JWK and Key Management  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module goal:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Technical scope:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.x on the Servlet stack. Examples focus on JWT/JWKS and `NimbusJwtDecoder`; verify specific APIs against the deployed version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **JWK**, **JWKS**, `kid`, and the active signing key.
2. Explain why Resource Servers, OIDC Clients, and reverse proxies may hold stale JWKS copies after the Authorization Server rotates keys.
3. Design a three-phase key rotation lifecycle: **pre-publish → switch signing key → retire old key**.
4. Configure JWKS caching in Spring Security/Nimbus and understand the impact of TTL, cache invalidation, HTTP caching, CDNs, and multiple instances.
5. Handle tokens carrying a `kid` not yet known to a consumer while strictly preserving signature verification requirements.
6. Troubleshoot failures after changing keys, distinguishing stale caches from issuer, audience, algorithm, JWK selection, and invalid signature errors.
7. Build both scheduled rotation procedures and emergency response workflows for compromised private keys.
8. Write tests for key rollover, cache misses, unknown `kid`, JWKS endpoint outages, old/new tokens, and clients that have not updated keys.

**Key principle:** When a JWT carries a new `kid` for which a consumer does not yet have the corresponding public key, the safe handling is to **refresh the JWKS from a trusted source under bounded rules and verify again**. If the key is still missing or the signature is invalid, reject the token. Never skip signature verification, never trust a `jku` declared by the token itself, and never accept arbitrary keys just to avoid 401 errors.

## 2. What Are JWK, JWKS, and kid?

### 2.1. JWK Is a Single Key, JWKS Is a Set of Keys

- **JWK (JSON Web Key):** represents one cryptographic key and its descriptive attributes, such as RSA/EC key type, algorithm, and intended use.
- **JWKS (JSON Web Key Set):** a JSON object containing a `keys` array of one or more JWKs.
- **`kid` (Key ID):** identifies a key within a JWK Set. JWTs typically place `kid` in the protected header so verifiers can find the right public key.
- **Private key:** used to sign JWTs; kept strictly inside the Authorization Server's (AS) secure boundary.
- **Public key:** published via JWKS so Resource Servers (RS) or OIDC Relying Parties (RP) can verify signatures.

Abbreviated JWKS example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "as-signing-2026-10",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "as-signing-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "NEXT_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

The modulus values are placeholders, not usable keys. In this example, the AS publishes two public keys so consumers can verify JWTs signed by either the old key or the new key during the transition window.

**The public JWKS must not contain private key parameters** such as RSA `d`, `p`, `q`, `dp`, `dq`, `qi` or corresponding EC/OKP private key material. The JWKS endpoint publishes only the public part of signing keys.

### 2.2. How Does the JWT Header Use kid?

A JWS-signed JWT has a protected header similar to:

~~~json
{
  "alg": "RS256",
  "kid": "as-signing-2026-11",
  "typ": "JWT"
}
~~~

Upon receiving a JWT, the consumer:

1. Reads the header per JWS rules.
2. Uses `kid` to select the corresponding public JWK in the JWKS fetched from a trusted issuer.
3. Checks key type, use/key operations, allowed algorithms, and decoder configuration.
4. Verifies the signature.
5. Validates issuer, audience, expiration, and other claims/policies.

`kid` is merely **an identifier for key selection**, not proof that a token is trustworthy. An attacker can craft a header with any `kid`; the consumer still must verify the signature with a trusted public key.

### 2.3. kid Must Be Unique per Key Material

When generating a new signing key, assign a new `kid`. Never reuse a `kid` for a different key pair.

If you reuse `kid`, consumers may:

- Continue using the old public key from cache.
- Fail to recognize that the same ID now represents different key material.
- Skip refreshing JWKS if the cache lookup still finds a JWK with that `kid`.
- Return invalid-signature errors even after the JWKS endpoint was updated.

Operational rule: **one key material has one stable kid; new key material gets a new kid**. Avoid timestamps that might collide or values prone to reuse in automated pipelines.

## 3. Who Caches the JWKS?

In OAuth2/OIDC systems, "a client that has not updated its keys" is usually a **JWT consumer**, not necessarily the OAuth2 Client calling the token endpoint.

| Component | Why does it need JWKS? | Cache example |
| --- | --- | --- |
| Resource Server | Verify JWT access tokens | `NimbusJwtDecoder`, in-process cache |
| OIDC Client / Relying Party | Verify ID token signatures | OIDC ID token decoder and JOSE library |
| API Gateway | Verify tokens before forwarding | Gateway's own JWKS cache |
| Service mesh / sidecar | Verify JWTs at the network layer | Cache by issuer/JWKS URI |
| Reverse proxy / CDN | Distribute JWKS endpoint faster | HTTP cache, edge cache |
| Centralized verification platform | Share public keys across many services | Distributed cache or local cache |

An OAuth2 Client that only calls the token endpoint to receive access tokens **does not necessarily** read the JWKS. However, if it is an OIDC RP verifying ID tokens, or also acts as a Resource Server, it too must update public keys.

### 3.1. Cache Layers Can Be Independent

~~~mermaid
flowchart TD
    AS["Authorization Server<br/>JWKSource / JWKS endpoint"]
    CDN["CDN / Reverse proxy<br/>HTTP cache"]
    RS1["Resource Server A<br/>NimbusJwtDecoder cache"]
    RS2["Resource Server B<br/>NimbusJwtDecoder cache"]
    GW["API Gateway<br/>JWKS cache"]
    RP["OIDC Relying Party<br/>ID token decoder cache"]

    AS --> CDN
    CDN --> RS1
    CDN --> RS2
    CDN --> GW
    CDN --> RP
    AS -.->|"May call directly"| RS1
    AS -.->|"May call directly"| RS2
~~~

Clearing caches at the AS **does not automatically clear** caches at CDNs, gateways, RSs, or RPs. When investigating post-rotation errors, know which URL each consumer fetches JWKS from and where it caches keys.

## 4. Why Can JWKS Caching Cause Errors After Rotation?

Suppose the AS is signing JWTs with key `K1`, whose public key has `kid=k1`. An RS has fetched the JWKS and cached K1. Then the AS switches to signing new tokens with `K2` having `kid=k2`.

If the consumer still has only the old JWKS:

- New JWTs have header `kid=k2`.
- The decoder looks up `k2` in its cache and does not find it.
- The consumer may trigger a JWKS refresh; if the refresh fails or the cache/proxy serves stale data, no matching public key exists.
- Signature verification cannot complete; requests are typically rejected as invalid tokens.

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant CDN as CDN / JWKS Cache
    participant RS as Resource Server

    AS->>CDN: JWKS contains K1 (kid=k1)
    CDN-->>RS: Returns old JWKS
    Note over RS: Local cache holds K1
    AS->>AS: Switch to signing with K2 (kid=k2)
    AS-->>RS: New JWT carries kid=k2
    RS->>RS: k2 not found in cache
    RS->>CDN: Refresh JWKS
    alt Cache/proxy already updated
        CDN->>AS: Fetch fresh JWKS
        AS-->>CDN: K1 + K2
        CDN-->>RS: Fresh JWKS
        RS->>RS: Verify signature with K2
    else Cache still stale or endpoint errors
        CDN-->>RS: Stale JWKS / fetch error
        RS-->>AS: Token rejected at API
    end
~~~

This is why you must **publish the new public key before using the new private key to sign tokens**. If you change the signing key and JWKS simultaneously, consumers may receive JWTs before the public key propagates.

### 4.1. Three Types of Errors to Distinguish

| Observed error | Possible cause | How to check |
| --- | --- | --- |
| Unknown `kid` | Consumer has not fetched JWKS containing new key | Compare JWT header against the JWKS actually used by consumer |
| Signature invalid with found `kid` | Wrong key material, reused kid, tampered token, or cache holds old key under same kid | Compare public key, kid, and key rotation history |
| JWKS fetch timeout/5xx | AS, network, DNS, TLS, proxy, or CDN failure | Call the JWKS URL directly from the consumer environment |
| Issuer invalid | JWT `iss` differs from configured issuer | Check issuer/forwarded headers |
| Audience invalid | Token not meant for this API | Check `aud` and audience validator |
| Algorithm rejected | Token uses an algorithm outside allowlist | Compare `alg` header with decoder policy |

Do not blame caching for every 401 after rotation. A token with the right `kid` can still fail due to invalid signature, issuer, audience, expiry, or algorithm.

## 5. Three-Phase Key Rotation Strategy

A safe workflow has three phases:

1. **Pre-publish:** publish the new public key into JWKS while continuing to sign with the old key.
2. **Switch signing key:** switch the AS to sign new tokens with the new private key, retaining the old public key to verify unexpired tokens.
3. **Retire old key:** remove the old public key only after tokens signed with the old key have expired past acceptance limits and consumers have had enough time to update.

~~~mermaid
flowchart LR
    A["Phase 1<br/>JWKS: K1 + K2<br/>Signer: K1"]
    B["Phase 2<br/>JWKS: K1 + K2<br/>Signer: K2"]
    C["Phase 3<br/>JWKS: K2<br/>Signer: K2"]

    A -->|"Consumer caches have time to receive K2"| B
    B -->|"K1-signed tokens expire + margin"| C
~~~

### 5.1. Phase 1 — Pre-Publish the New Public Key

The AS adds K2's public JWK to the JWKS while continuing to sign tokens with K1.

Example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-k1",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_K1",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-k2",
      "use": "sig",
      "alg": "RS256",
      "n": "PUBLIC_K2",
      "e": "AQAB"
    }
  ]
}
~~~

Consumers can fetch the updated JWKS and cache both K1 and K2 before any token using K2 ever appears.

**The pre-publish duration** must be at least as long as the largest cache/propagation window affecting consumers, plus reasonable retry/operational time. If a CDN has a 10-minute TTL, a decoder caches for 15 minutes, and a service refreshes periodically, do not switch signers after just a few seconds. Measure/know actual TTLs instead of using an arbitrary default.

### 5.2. Phase 2 — Switch Signer to K2

Once enough distribution time has elapsed, the AS switches the active private signing key to K2:

- New JWTs carry `kid=signing-k2`.
- JWKS continues publishing both K1 and K2.
- Updated consumers holding K2 verify new tokens immediately.
- Unupdated consumers may hit an unknown kid; decoders must refresh JWKS from a trusted URL.
- Old JWTs signed with K1 must still verify while unexpired.

Do not remove K1 immediately when starting to sign with K2. Tokens already issued with K1 may still be valid at RSs/RPs.

### 5.3. Phase 3 — Retire K1

Remove public key K1 from the JWKS only after:

- No valid tokens still require verification with K1.
- The maximum TTL of access tokens/ID tokens signed with K1 has passed.
- Consumer clock skew/leeway has been accounted for.
- Propagation delays, rollouts, and slow-updating consumers have been accounted for.
- No valid workloads still rely on old tokens.
- Rollback/incident procedures have been reviewed.

Example planning formula:

~~~text
retire_after >=
    last_issuance_time_using_K1
  + maximum_lifetime_of_tokens_signed_by_K1
  + maximum_clock_skew_or_validation_leeway
  + rollout_and_propagation_margin
~~~

This is an operational formula to determine **the earliest point to consider retirement**, not a fixed RFC standard formula. If tokens have varying TTLs per client, use the largest accepted lifetime. If long-lived ID tokens or special tokens exist, include them too.

### 5.4. Do Not Leave JWKS Missing the Old Key While Old Tokens Are Unexpired

If K1 is removed too early, RSs that refreshed JWKS lose the public key needed to verify old JWTs. This causes widespread errors even though tokens have not expired.

Some consumers still holding K1 in cache temporarily succeed, while others that fetched the updated JWKS fail. The system can exhibit **inconsistent behavior across instances**. Therefore, overlap must be calculated from token lifetimes and rollout times, not merely from when the AS switched signers.

## 6. Configuring the JWKS Endpoint in Spring Authorization Server

### 6.1. JWKSource Is the AS's Key Source

Spring Authorization Server uses `JWKSource<SecurityContext>` to supply key material for JWT signing and the JWK Set endpoint. In standard configurations, the default endpoint is `/oauth2/jwks` when a JWK source is configured and the endpoint is enabled via settings.

Conceptual bean model:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource(KeyMaterialProvider keyMaterialProvider) {
    // Load JWKSet from an application-managed durable key store/KMS/HSM.
    // The JWKSet must hold private key material inside the trusted signing boundary,
    // and public keys to be published in JWKS.
    JWKSet jwkSet = keyMaterialProvider.loadSigningKeySet();

    return (jwkSelector, securityContext) ->
        jwkSelector.select(jwkSet);
}
~~~

`KeyMaterialProvider` is an application-defined abstraction, not a built-in Spring bean. In production, never store private keys in source code, never generate random new keys on every startup, and never expose private keys via the JWKS endpoint.

### 6.2. Publish Public Keys, Keep Private Keys on the AS

A private RSA JWK can contain `d`, `p`, `q`, and other secret parameters. When the endpoint returns JWKS, the response must contain only the public representation.

With Nimbus JOSE, a public view of a JWK can be created via `toPublicJWK()`, and for a JWK Set via `toPublicJWKSet()`. Spring Authorization Server manages the endpoint response per its implementation, yet operators must still verify the live response:

- Contains only public parameters.
- Includes the active key signing new tokens.
- Includes the old key during the overlap window.
- `kid` values are unique and match JWT headers.
- `use`/`key_ops`/`alg` match signing/verification usage.
- Zero private RSA/EC/OKP parameters are exposed.

### 6.3. JWK Set Endpoint and Issuer Metadata

OIDC/OAuth authorization server metadata can publish `jwks_uri` so consumers know the official JWKS endpoint. Consumers should use metadata from a trusted issuer or an administratively configured JWKS URI.

Never take the JWKS URL from a `jku`/`x5u` claim inside an untrusted JWT. If tokens are allowed to self-declare key URLs, attackers can make consumers fetch an attacker-controlled public key and forge valid signatures for that key.

## 7. JWKS Caching in Spring Security and Nimbus

### 7.1. Decoder Fetching JWKS from a Trusted URL

Spring Security can configure a Resource Server with `issuer-uri` for issuer and JWKS URI discovery, or with `jwk-set-uri` configured directly.

Application properties example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
          jwk-set-uri: https://auth.example.test/oauth2/jwks
~~~

Using both issuer and JWK Set URI in Spring Boot versions supporting this configuration lets you specify the key endpoint directly while preserving issuer validation. Verify property binding behavior for your exact version. If declaring a custom `JwtDecoder` bean, configure the corresponding validators explicitly.

### 7.2. Customizing NimbusJwtDecoder and Cache

Java example using Spring Cache:

~~~java
@Bean
JwtDecoder jwtDecoder(Cache jwkSetCache) {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri("https://auth.example.test/oauth2/jwks")
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .cache(jwkSetCache)
        .build();

    OAuth2TokenValidator<Jwt> issuerValidator =
        JwtValidators.createDefaultWithIssuer(
            "https://auth.example.test");

    decoder.setJwtValidator(issuerValidator);
    return decoder;
}
~~~

Key imports:

~~~java
import org.springframework.cache.Cache;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
~~~

`jwkSetCache` must be an application-configured cache with appropriate, observable TTL/eviction. This snippet only illustrates passing a cache into the builder; it does not create a cache manager or configure TTL itself. The `cache(...)` API and caching details depend on your Spring Security/Nimbus version, so compile and test against your actual version.

**Do not set a very long cache TTL and expect rotation to take effect instantly.** Conversely, do not set an ultra-short TTL causing every API request to hammer the JWKS endpoint, adding latency and load on the AS.

### 7.3. Adding Audience Validation

Correct caching does not mean a JWT is authorized to access the API. Example adding an audience validator:

~~~java
@Bean
JwtDecoder jwtDecoder(Cache jwkSetCache) {
    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri("https://auth.example.test/oauth2/jwks")
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .cache(jwkSetCache)
        .build();

    OAuth2TokenValidator<Jwt> issuer =
        JwtValidators.createDefaultWithIssuer(
            "https://auth.example.test");

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("booking-api")) {
            return OAuth2TokenValidatorResult.success();
        }
        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null);
        return OAuth2TokenValidatorResult.failure(error);
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(issuer, audience));
    return decoder;
}
~~~

This example requires `RS256` and `booking-api` per illustrative policy. If the AS issues tokens with another algorithm, configure a consistent allowlist. Never read `alg` from the JWT and allow every algorithm. Issuer, audience, and expiry must still be validated after the public key is found.

### 7.4. Caches Do Not Have to Live Only in One JVM

You can use:

- Local in-process cache in each Resource Server.
- Spring Cache backed by Caffeine/Ehcache or an appropriate provider.
- Distributed cache, when genuine operational needs exist.
- HTTP caching at CDNs/reverse proxies.
- Internal caching in the JOSE/Nimbus library.

Do not force every system onto a distributed cache. Local caches are often simple and effective; what matters is **well-designed TTL, refresh-on-miss, observability, and key rollout**.

## 8. TTL, HTTP Caching, and CDNs

### 8.1. JWKS Cache-Control

Since JWKS is public key material, it can be cached. The AS/gateway can emit HTTP response headers such as:

- `Cache-Control: public, max-age=...`.
- `ETag` and `If-None-Match` for conditional GETs if endpoint/proxies support them.
- `Last-Modified`/`If-Modified-Since` if supported.
- CDN TTL policies aligned with key rotation and incident response.

No single TTL fits every system. Choosing TTL requires balancing:

| TTL | Pros | Risks |
| --- | --- | --- |
| Too short | Consumers get new keys quickly | Heavy traffic to AS/CDN, added latency and load |
| Moderate | Reduces load with reasonable update window | Requires pre-publish/refresh process |
| Too long | Few JWKS requests | Prolonged unknown kid errors; harder coordinated compromise response |

Do not enable `stale-if-error` or unbounded stale caching without evaluation. If caches keep old JWKs indefinitely during AS failures, the system may continue verifying keys revoked during an incident. If it fails closed too aggressively, a brief network blip can cause the API to reject every token needing a new key. This is a documented risk/availability decision.

### 8.2. CDN Caching Can Mask Updates from the AS

Scenario:

1. AS has published K1 + K2.
2. CDN still caches the old JWKS containing only K1.
3. Consumers fetch from CDN and receive the old JWKS.
4. AS starts signing with K2.
5. Consumers fail to verify new JWTs even though the origin endpoint is updated.

Investigation must compare responses from:

- The AS's direct JWKS endpoint inside a trusted network.
- The JWKS URL actually called by consumers.
- Relevant CDN POPs/edges.
- Cache contents inside the decoder (if safely observable).

Do not simply open the URL from your laptop and assume every consumer sees the same response.

### 8.3. Do Not Rely Solely on Manual Purges

Purging a CDN can push new keys faster, yet it does not clear local caches inside every JVM, gateway, or OIDC RP. Rotation procedures need a sufficiently long pre-publish window and proper refresh mechanics. Purging is only a supplemental operational step.

## 9. Consumer Encounters a New kid: Refresh Then Re-Verify

### 9.1. Expected Behavior

When a JWT carries a `kid` missing from the current cache:

1. The consumer detects no matching key is present.
2. The consumer attempts to refresh the JWKS from the **configured trusted URI** per library mechanics.
3. After successful fetch, the consumer looks up the key again by `kid` and matching attributes.
4. The consumer verifies the signature with an allowlisted algorithm.
5. The consumer proceeds to validate issuer, audience, expiration, and claims.
6. If the key is still missing or fetching fails, the consumer rejects the token.

Some Nimbus Remote JWK Set implementations can refresh the JWKS when no matching key is found in cache. Exact behavior, retries, caching, and concurrency must be verified for your version/configuration. **Do not assume every JWT decoder or gateway refreshes immediately on its own.**

### 9.2. kid Not Found After Refresh

Safe outcome:

~~~text
JWT kid = signing-k3
Cached JWKS: k1, k2
Refresh JWKS from trusted issuer URI
Fetched JWKS: k1, k2

signing-k3 not found
=> Reject token
=> Record unknown_kid metric
=> Do not skip signature validation
~~~

Never accept a JWT merely because `iss` matches or the AS shares the same domain. Without a matching public key, the signature cannot be proven.

### 9.3. If JWKS Refresh Fails Due to Network Issues

Distinguish two cases:

- **Token uses a cached kid and the key is still policy-valid:** the decoder can continue verifying using the valid cache, depending on cache policy.
- **Token uses a new kid not yet in cache:** no key exists to verify it, so that token must be rejected. Retries with backoff/health policies can be used, but never skip signature verification.

Never turn a JWKS fetch error into `permitAll()` or accept unverified tokens. If availability is critical, harden the JWKS endpoint, CDN, caching, and rollout instead of lowering authentication standards.

### 9.4. Preventing Refresh Storms from Unknown kid

Attackers can send floods of forged JWTs with random `kid` values to trigger JWKS refreshes and overload the AS. Consumers/gateways should:

- Use single-flight or request coalescing so concurrent requests with the same unknown kid share one fetch.
- Rate-limit refreshes when unknown kids arrive continuously.
- Use short-lived negative caching or controlled cooldowns.
- Never let `kid` dictate the URL to fetch.
- Configure timeouts, retry/backoff, and response size limits.
- Emit metrics/alerts on abnormal unknown-kid spikes.
- Still allow legitimate refreshes when new keys are pre-published/rolled out.

Too long a negative cache can block legitimate newly published keys; balance cooldowns with the pre-publish plan.

## 10. Scheduled Rotation Procedure for Spring Authorization Server

### 10.1. Before Rotation

- Identify the issuer and JWKS URI used by every consumer.
- Inventory Resource Servers, OIDC RPs, gateways, sidecars, and CDNs.
- Measure TTLs of decoder caches and HTTP/CDN caches.
- Check the maximum access token/ID token lifetime.
- Check consumer clock skew/leeway.
- Prepare the new key pair in a secure key store and generate a new `kid`.
- Verify algorithm/key size/curve against policy.
- Prepare a plan to roll back the signer and update JWKS.

### 10.2. During Rotation

1. Publish public K2 alongside K1 in JWKS.
2. Verify the origin endpoint returns both public keys.
3. Verify responses from CDNs/proxies and a representative group of consumers.
4. Wait out the full pre-publish window.
5. Switch the AS signer to private K2.
6. Issue a test JWT with `kid=k2` and verify across every consumer group.
7. Monitor unknown-kid, signature-invalid, 401/5xx, and JWKS fetch metrics.
8. Retain K1 to verify older tokens.

### 10.3. After Rotation

- Wait for the last K1-signed token to expire plus clock skew and margin.
- Confirm no valid workloads still require K1.
- Remove K1 from JWKS in waves if multiple issuers/consumers exist.
- Retain audit records of key IDs, publish, activate, and retire timestamps, and approving person/process.
- Do not delete private K1 from backups/secure key lifecycle until retention/incident policies permit.
- Update operational docs and tests for the next rotation.

### 10.4. State-Based Runbook

| State | JWKS | Signing key | Transition condition |
| --- | --- | --- | --- |
| Stable | K1 | K1 | K2 prepared |
| Pre-published | K1 + K2 | K1 | Caches/consumers had time to receive K2 |
| Switched | K1 + K2 | K2 | All K1 tokens expired per policy |
| Retired | K2 | K2 | Consumer checks complete |
| Emergency | Per incident policy | New clean key | Plan exists to revoke/deny compromised key |

## 11. When a Client/Resource Server Has Not Updated Keys

### 11.1. Handling by Impact Level

| Scenario | Symptoms | Resolution |
| --- | --- | --- |
| Single instance has stale cache | Partial traffic gets 401, other instances succeed | Refresh/evict JWKS cache on failing instance; inspect TTL |
| CDN returns stale JWKS | Many consumers miss new kid simultaneously | Purge/invalidate edge cache; check origin and max-age |
| Decoder does not refresh on unknown kid | New tokens rejected despite key on origin | Fix refresh/cache config or upgrade library |
| Consumer uses wrong JWKS URI | Fetches another issuer/environment | Inspect discovery metadata and issuer configuration |
| Consumer uses old kid but signature fails | Kid reused or key material out of sync | Assign a new kid; check JWK thumbprints/key pairs |
| Consumer hard-pins static public key | Does not auto-fetch JWKS | Execute trust-store distribution/update workflow |
| Consumer blocks new algorithm | Key present but decoder disallows alg | Align algorithm allowlists before rotation |
| Consumer skips issuer/audience | Signed token accepted in wrong place | Configure validators; never weaken validation |

### 11.2. Steps to Help a Client Update

1. Inspect the JWT header (stripping sensitive token payload) or use internal tooling to read only `kid` and `alg`.
2. Fetch the JWKS the client actually reaches from inside the client's own environment.
3. Compare `kid` in the JWT against `kid` values in the JWKS.
4. Check HTTP cache headers, CDN Age, ETag, DNS, and TLS.
5. Check decoder cache TTL and unknown-kid refresh behavior.
6. If safe, evict caches or restart one instance per runbook; avoid mass restarts that cause outages.
7. Retry requests with a fresh token after keys update.
8. If errors persist, verify signature, issuer, audience, alg, and expiration; never assume caching solely from a 401 status.

**Do not ask clients to download a public key over email/chat and import it manually** if the architecture uses JWKS. If key pinning is unavoidable, maintain an authenticated key distribution channel, rotation workflow, and dedicated rollback procedure.

### 11.3. Client Cannot Update Immediately: Should We Keep Using the Old Key?

For scheduled rotation, you can keep K1 in JWKS and hold off issuing K2 tokens until consumers have had time to update. If K2 is already active while a legacy client lacks support, you can pause rollout or upgrade the client per plan.

**Never sign two parallel access tokens for the same request** just to appease an unupdated client unless the protocol/application explicitly specifies it. Never distribute a private key to a client for self-verification or signing.

In a key-compromise incident, priorities differ: you must disable the compromised key and accept that some outdated clients will be rejected. Never keep an exposed key solely for compatibility.

## 12. Handling a Compromised Key

### 12.1. Emergency Rotation Differs from Scheduled Rotation

If private signing key K1 is exposed, attackers can forge JWTs with valid signatures under public K1 until consumers stop trusting K1 or another control blocks them.

Simply adding K2 and switching the signer to K2 **is not enough** if attackers can still sign with K1 and consumers still trust public K1.

Response workflow may include:

1. Activate incident response and scope affected keys/issuers/clients/tokens.
2. Stop using private K1 immediately; isolate/revoke the key in KMS/HSM/secure store.
3. Generate K2 from a clean environment, publish public key K2, and switch the signer.
4. Remove public K1 from JWKS urgently per incident policy.
5. Purge CDN/proxy caches and instruct consumers to refresh JWKS.
6. Invalidate/denylist affected tokens if a token registry exists; consider introspection/online validation or shortening token lifetimes.
7. Notify and monitor unupdated clients/RSs; fail closed on K1-signed tokens.
8. Investigate logs, audits, and leak vector; rotate related credentials if they could have been accessed concurrently.
9. Document decisions, timestamps, scope, and post-incident checks.

### 12.2. Caching Delays the Effect of Key Removal

Once K1 is removed from the JWKS origin:

- CDNs may still serve stale responses.
- Decoders may still hold K1 in memory caches.
- Some consumers may not refresh until TTL expiry.
- Forged JWTs signed with K1 may still be accepted by consumers retaining public key K1 if other validators pass.

Therefore, emergency response must **proactively purge/invalidate caches** and provide mechanisms for consumers to refresh or deny compromised `kid` values. You cannot update the JWKS origin and assume every consumer picked up the change instantaneously.

### 12.3. Self-Contained JWTs Lack Built-In Instant Revocation

If an RS verifies JWTs locally with a public key, it can continue accepting previously signed valid tokens until `exp` or until the key leaves caches/allowlists. Revoking a refresh token does not automatically invalidate already-issued JWT access tokens.

For sensitive APIs, consider:

- Short access token TTLs.
- Denylists by `jti` or token version where appropriate.
- Introspection/opaque tokens when online state control is required.
- Account/authorization state checks for high-risk actions.
- Key ID denylists when needing to block all tokens signed by a compromised key.

Each mechanism carries its own availability, latency, and operational costs.

## 13. Testing JWKS Caching and Rotation

### 13.1. Test Matrix

| Test case | Setup | Expected result |
| --- | --- | --- |
| Stable key | JWKS has K1, JWT signed with K1 | Consumer verifies successfully |
| Pre-publish | JWKS has K1 + K2, signer still K1 | K1 tokens stay valid; consumer fetches K2 |
| Switched signer | Signer K2, JWKS keeps K1 + K2 | K2 tokens verify; unexpired K1 tokens stay valid |
| Unknown kid | Token carries unpublished kid K3 | Bounded refresh, then rejected when still missing |
| Stale local cache | Cache has only K1, token uses K2 | Refresh JWKS and re-verify if endpoint has K2 |
| Stale CDN | Origin has K2, CDN lacks it | Detected via live response check; purge/update edge |
| JWKS endpoint timeout | Cache has K1, token uses K1 | Follows cache policy; never skips signature |
| JWKS endpoint timeout with K2 | Cache lacks K2 | Rejects K2 token, safe retry/backoff |
| Same kid, different key | Improper kid reuse | Test detects signature/key mismatch; process forbids reuse |
| Wrong algorithm | Token alg outside allowlist | Rejected |
| Wrong issuer | JWT iss mismatch | Rejected |
| Wrong audience | JWT aud meant for another API | Rejected |
| Premature K1 retirement | Remove K1 while K1 tokens unexpired | Test catches valid-token failures |
| Timely K1 retirement | K1 tokens expired + margin | K2 tokens keep working |
| Emergency K1 compromise | Remove K1/purge cache | Consumer stops trusting K1 tokens per incident policy |
| Multi-instance decoder | One instance has fresh cache, one stale | Detects fragmented behavior and verifies rollout |
| OIDC ID token rotation | RP receives ID token with new kid | RP refreshes JWKS and verifies issuer/audience/nonce |
| JWKS private key leak | Inspect endpoint response | Zero private parameters |

### 13.2. Testing JWKS Fetch over HTTP

Use integration tests or a test environment to:

1. Call the live JWKS endpoint and parse `keys`.
2. Assert public keys K1/K2 have exact `kid` values.
3. Assert no private RSA parameters (`d`, `p`, `q`, `dp`, `dq`, `qi`) are present.
4. Obtain an AS-issued JWT and read `kid` and `alg`.
5. Verify the signature against the matching public key from JWKS.
6. Verify issuer/audience/expiry independently.

Do not assert only HTTP 200; a JWKS response returning empty JSON or missing keys is still an operational failure.

### 13.3. Testing Cache Misses and Refreshes

Design a test with a mock JWKS server whose response changes over time:

- Initially return K1; consumer fetches and caches it.
- Update response to K1 + K2.
- Send a JWT with kid K2.
- Verify the decoder fetches fresh JWKS per configured/version behavior.
- Verify the K2 token succeeds.
- Keep returning JWKS without K3 and send a K3 JWT; verify the decoder rejects it.
- Simulate JWKS endpoint 503/timeout; verify cache behavior and fail-closed handling for unknown keys.

This tests library behavior, so pin Spring Security/Nimbus versions in your build. Do not assume refresh-on-unknown-kid behaves identically across every version.

### 13.4. Tests Must Not Skip Signature Validation

Do not mock `JwtDecoder` as "always valid" in rotation tests and conclude caching works. Test with real/fixture JWKs having matching private/public keys and genuinely signed tokens to prove both key selection and signature verification.

## 14. Monitoring and Diagnostics in Production

### 14.1. Recommended Metrics

| Metric | Purpose |
| --- | --- |
| JWKS fetch count/latency | Detect overly frequent consumer refreshes or slow endpoints |
| JWKS fetch failures by status | Detect network, TLS, DNS, CDN, or AS outages |
| Unknown kid count | Detect stale consumers or anomalous tokens |
| Signature verification failures | Distinguish key mismatches, forged tokens, or algorithm errors |
| JWKS cache age/remaining TTL | Track freshness of cached key material |
| 401s by instance/issuer/client group | Isolate failures affecting a single consumer |
| Key publish/activate/retire events | Audit key lifecycle |
| CDN cache age / invalidation status | Detect edges serving stale responses |
| Token issuance by kid | Confirm which key is signing new tokens |

Never place raw JWTs or sensitive token payloads in metric labels. Logging `kid` is acceptable as a public key identifier, though cardinality and untrusted header inputs still require bounds.

### 14.2. Logging Rotation Events

Record:

- Configured issuer and JWKS URI.
- `kid` published, active signer, and retired.
- Timestamps and deployment versions.
- Cache purges/invalidations and outcomes.
- Verified consumer groups.
- Error rates before/after switch.
- Approving person/workflow and linked incident/change tickets.

Never log private key material, raw access tokens, or client secrets.

### 14.3. Quick Diagnostics Table

| Symptom | First check |
| --- | --- |
| Only one pod gets 401 after rotation | Compare cache state, image/version, and JWKS response on that pod |
| All pods get 401 on new tokens | Compare token kid against JWKS origin and CDN |
| Only gateway gets 401, internal services succeed | Gateway has its own cache/issuer/JWKS URI |
| OIDC login fails while API access tokens work | RP may cache JWKS or validate ID tokens differently |
| Old tokens fail right after rotation | Old public key removed too early or issuer/alg changed |
| Sudden spike in unknown kid | Check rotation, issuer mismatch, or forged JWTs causing refresh storm |
| Signature invalid despite existing kid | Check kid reuse, key material, alg, and token tampering |
| JWKS 200 yet decoder still fails | Does actual response have the right key? Is cache stale? Do key use/alg match? |

## 15. Common Mistakes

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Switching signer and deleting old key simultaneously | Unexpired old JWTs rejected | Pre-publish, overlap, and retire later |
| Reusing `kid` for a new key | Consumers keep old key under same ID | New kid per key material |
| Publishing K2 after signing K2 JWTs | Consumers lack public key | Publish first and wait for cache/propagation |
| Setting cache TTL too long | Consumers hold stale JWKS too long | Reasonable TTL and refresh-on-miss |
| Setting cache TTL too short | JWKS endpoint hammered continuously | Balance caching and rollout |
| Purging only CDN | Local caches stay stale | Check decoders/gateways/RPs too |
| Trusting `jku` inside JWTs | Attacker can specify key server | Use configured trusted JWKS URI |
| Accepting tokens without a public key | Skips signature verification | Fail closed |
| Allowing any `alg` from header | Algorithm confusion/downgrade | Pin algorithm allowlist |
| Deleting K1 before K1 tokens expire | Valid tokens fail | Wait max token lifetime + skew + margin |
| Keeping compromised K1 for compatibility | Attackers keep forging tokens | Emergency revoke, purge caches, fail closed |
| Confusing unknown kid with invalid audience | Fixing cache does not fix error | Diagnose per validator |
| Testing only JWKS HTTP 200 | Misses missing keys/private key leaks | Parse and verify JWKS contents |
| Testing only one RS instance | Misses fragmented caching | Test multiple instances/consumers |
| Skipping OIDC RP tests | APIs work while OIDC login fails | Test ID token signature rotation too |

## 16. Self-Check Questions

**Q1.** How do JWK and JWKS differ?

**A:** A JWK represents a single key; a JWKS is a collection of JWKs, typically published via an endpoint so consumers can verify JWTs.

**Q2.** Is `kid` a secret or proof of a valid signature?

**A:** No. It only identifies a key to select the public JWK; consumers must still verify the signature and claims.

**Q3.** Why must public K2 be published before the AS begins signing with K2?

**A:** So Resource Servers/OIDC RPs have time to fetch and cache the new key before receiving JWTs carrying kid K2.

**Q4.** When switching the signer to K2, can public K1 be removed immediately?

**A:** No, if tokens signed with K1 are still within their accepted lifetime. Retain K1 during the overlap window and retire it after max TTL, clock skew, and margin.

**Q5.** What should a consumer do if it receives a JWT whose kid is still missing after refreshing JWKS?

**A:** Reject the token, record diagnostic metrics, and enforce bounded refresh/retry rules. Never skip signature validation.

**Q6.** Does purging a CDN clear the JWKS cache inside `NimbusJwtDecoder` on every JVM?

**A:** No. CDNs and local caches are independent layers; each layer must be managed.

**Q7.** Why should a kid not be reused when changing key material?

**A:** Consumers may use stale caches because they still match the same kid, selecting the wrong public key and failing signatures. Each new key material requires a new kid.

**Q8.** When a private key is compromised, should its public key remain in JWKS until all tokens expire like a normal rotation?

**A:** Not necessarily. Emergency response must prioritize revoking trust in the compromised key, purging caches, and accepting rejection of tokens signed by that key.

**Q9.** Is a valid JWT signature sufficient for a Resource Server to accept a token?

**A:** No. It must also validate issuer, audience, expiry, algorithm, scopes, and business policies.

## 17. Pre-Rotation Operations Checklist

- [ ] JWK Set publishes only public key material.
- [ ] Every key material has a distinct, stable `kid`.
- [ ] JWTs use an algorithm within the allowlist.
- [ ] Consumers fetch JWKS from trusted issuer/JWKS URIs, never from JWT header URLs.
- [ ] All decoders, gateways, OIDC RPs, CDNs, and cache layers are inventoried.
- [ ] TTLs of local caches and HTTP/CDN caches are known and measured.
- [ ] Public K2 is pre-published before switching the signer.
- [ ] K1 is retained during overlap while old tokens remain valid.
- [ ] Retirement timing accounts for max token lifetime, clock skew, and rollout margin.
- [ ] Tests cover unknown kid, cache misses, fetch outages, invalid signatures, and issuer/audience.
- [ ] Observability covers kid, JWKS fetches, cache age, and signature failures.
- [ ] Procedures exist to purge/evict caches per consumer when needed.
- [ ] An emergency runbook exists for private key compromise.
- [ ] No tokens are accepted when signatures cannot be verified.
- [ ] Multi-instance AS/RS deployments share consistent key sets and cache policies.
- [ ] Both JWT access tokens and OIDC ID tokens are tested if OIDC is enabled.

## 18. References and Conclusion

Standards and framework documentation:

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Nimbus JOSE + JWT — Remote JWK Set](https://connect2id.com/products/nimbus-jose-jwt/examples/remote-jwk-set)

**Conclusion:** JWKS caching avoids having consumers fetch public keys on every request, yet it introduces update lag when the AS rotates keys. The safe workflow is **publish the new public key first, switch the signer later, retain the old key until old tokens expire, and only then retire it**. When a consumer encounters a new `kid`, refresh JWKS from a trusted URI and re-verify; if the key is absent or the signature fails, reject the token. Managing local caches, CDNs, issuer metadata, algorithm allowlists, and emergency revocation together keeps OAuth 2.0/OIDC JWT verification reliable across both routine rotations and key-compromise incidents.
