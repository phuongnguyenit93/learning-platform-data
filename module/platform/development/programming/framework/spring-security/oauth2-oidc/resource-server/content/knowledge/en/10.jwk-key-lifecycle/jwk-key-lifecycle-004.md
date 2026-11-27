# JWKS Caching, Lifetime, and Key Data Refresh

When an API using **Spring Security OAuth 2.0 Resource Server** validates asymmetrically signed JWT access tokens, it needs the **public key** corresponding to the private key used by the **Authorization Server** to sign the token. These public keys are typically published via a **JWKS (JSON Web Key Set)** endpoint. Rather than fetching the entire JWKS over the network on every HTTP request, the Resource Server normally **caches the key set** and refreshes it when needed.

JWKS caching sits at the intersection of **performance**, **resilience**, and **key-lifecycle security**. A cache TTL that is too short increases traffic to the Authorization Server; a cache TTL that is too long can prevent the API from picking up new keys or keep old keys active longer than intended. During **key rotation**, how the issuer publishes keys and how the Resource Server refreshes its cache must work in sync.

This lesson covers how JWKS is fetched and used, the different lifetime concepts, refresh mechanisms when encountering a new `kid`, how to orchestrate safe rotation, and configuration considerations for **Spring Security/NimbusJwtDecoder**. Default behavior and configuration APIs can depend on the **versions of Spring Boot, Spring Security, and Nimbus JOSE + JWT**.

## 1. What Problem Does JWKS Solve?

In asymmetric JWT signing, the Authorization Server holds the **private key** to sign tokens, while the Resource Server uses the **public key** to verify signatures. Public keys can be distributed via JWKS.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Spring Security Resource Server
    participant JWKS as JWKS endpoint
    C->>AS: Request access token via allowed grant
    AS->>AS: Sign JWT with K1 private key
    AS-->>C: JWT with JOSE header kid=K1
    C->>RS: GET /api/orders + Bearer JWT
    RS->>JWKS: Fetch public JWKs if cache lacks matching data
    JWKS-->>RS: JWKS containing K1 public key
    RS->>RS: Verify signature, issuer, exp, aud, scope...
    RS-->>C: API response or error
~~~

Common endpoint layout:

~~~text
https://auth.example.com/realms/shop/.well-known/openid-configuration
    |
    +-- jwks_uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

This URL is **illustrative**. Not every Authorization Server uses the same path. With OIDC Discovery or OAuth 2.0 Authorization Server Metadata, the Resource Server can obtain `jwks_uri` from the metadata of a **trusted issuer**; it can also be configured directly with a specific JWKS URL.

A JWKS is a JSON object with a `keys` property containing an array of JWKs:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "key-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_MODULUS_FOR_NEW_KEY",
      "e": "AQAB"
    }
  ]
}
~~~

The `n` values in this example are **placeholders**, not real RSA keys. A JWKS intended for Resource Servers must publish appropriate **public key material**; for RSA, this is typically `n` and `e`. Never publish private keys or secret parameters such as `d`, `p`, or `q` in a public JWKS.

| JWK Field | Role |
| --- | --- |
| `kty` | Key type, e.g., `RSA` or `EC` |
| `kid` | Key identifier used to locate a matching key |
| `use` | Intended purpose, e.g., `sig` for signatures when present |
| `key_ops` | Permitted key operations when present |
| `alg` | Intended algorithm when published |
| `n`, `e` | RSA public key parameters |
| `crv`, `x`, `y` | Public parameters of an elliptic curve key |

Not all attributes are required in every JWK. The Resource Server must use a trusted JOSE/JWT processor to select a key compatible with the header and **configured allowed algorithms**, instead of grabbing any JWK with a matching `kid` and treating it as valid.

## 2. How Does `kid` Relate to the JWKS Cache?

A JWS-based JWT access token typically has the form:

~~~text
BASE64URL(JOSE protected header).BASE64URL(JWT claims).BASE64URL(signature)
~~~

Example header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-02"
}
~~~

`kid` is a **key selection** hint for the JWKS. If the Resource Server's cache currently holds `key-2026-01`, but a new JWT carries `key-2026-02`, the decoder may need to reload the JWKS to locate the new public key.

This **does not mean** a token is trusted merely because `kid` exists in the JWKS:

1. The Resource Server must determine the JWKS endpoint from **trusted issuer configuration**, never from an arbitrary URL supplied by the token.
2. The decoder locates a key with compatible type, algorithm, and attributes.
3. The decoder verifies the **JWT signature** using the trusted public key.
4. Validators check `iss`, `exp`, `nbf`, `aud`, and the token/profile contract.
5. Authorization checks scopes and permissions on the endpoint, tenant, and data objects.

`kid` is not a password, access token, or permission. Nor is it a JWT revocation mechanism. A JWT with an invalid signature must still be rejected even when `kid` matches a key in the JWKS.

**Never automatically follow `jku` or `x5u` headers declared by a token to fetch keys from the Internet.** If these fields are ever handled, allow only explicitly controlled and approved key sources; otherwise, attackers can force the system to fetch keys from untrusted sources or trigger SSRF.

## 3. Why Is JWKS Caching Needed?

Suppose the Orders API receives 1,000 requests/second. If every request fetched the JWKS over the network, the Authorization Server/JWKS endpoint would have to serve 1,000 queries/second solely for signature checks. Meanwhile, most tokens are signed by **a small set of active public keys**.

JWKS caching helps:

- **Reduce authentication latency:** once the appropriate public key is available, JWT signature verification happens locally.
- **Reduce load on the issuer:** avoids generating bursts of repeated JWKS HTTP requests.
- **Improve short-term fault tolerance:** if valid keys are already cached, requests can continue verifying even if the JWKS endpoint is temporarily slow or unreachable, depending on cache/decoder policy.
- **Support controlled key rotation:** during a rotation window, the cache can hold both old and new signing keys to verify unexpired tokens.

However, caching also introduces **synchronization lag**: the Authorization Server may have just published a new key while a Resource Server still holds an older snapshot of the JWKS.

### Three Frequently Confused Concepts

| Concept | Unit / Measure | Meaning |
| --- | --- | --- |
| **JWT expiration (`exp`)** | NumericDate timestamp inside the JWT | When **an access token** expires |
| **JWKS cache TTL** | Time duration, e.g., 5 minutes | When **the cached copy of the key set** reaches its configured retention limit |
| **Key rotation overlap** | Time window publishing multiple public keys together | Ensures tokens signed by the old key remain verifiable after signing switches to the new key |

**An unexpired JWT does not mean the JWKS cache stays valid**, and **an unexpired JWKS cache does not make an expired JWT valid**. The two lifecycles are independent.

## 4. Cache Layers That May Coexist

In a real deployment, multiple layers may exist:

~~~text
Resource Server instance A          Resource Server instance B
        |                                     |
  Nimbus/JWKS cache A                   Nimbus/JWKS cache B
        |                                     |
        +------------------+------------------+
                           |
                 HTTP client / proxy / CDN
                           |
                      JWKS endpoint
                           |
                    Authorization Server
~~~

Common layers include:

| Layer | What Is Cached? | Notes |
| --- | --- | --- |
| **In-JVM decoder cache** | Raw JWKS JSON or parsed JWK set | Usually per decoder/instance; TTL and refresh depend on implementation |
| **Application-provided Spring Cache** | JWKS data via cache adapter if supported by version | Eviction, TTL, and capacity policies are managed by the application |
| **HTTP client cache / proxy / CDN** | HTTP responses from `jwks_uri` if infrastructure caches | May honor `Cache-Control`, `ETag`, `Last-Modified` depending on cache setup |
| **Authorization Server issuer/CDN** | Issuer-published copy of JWKS | Propagation time must be accounted for during rotation |

**Do not assume HTTP `Cache-Control: max-age=300` dictates the TTL inside `NimbusJwtDecoder`.** Nimbus or a cache adapter may enforce internal policies, and HTTP clients do not necessarily honor cache headers the way a browser or CDN does. Determine **which layer is caching, who controls its lifetime, and when it actually refreshes**.

Similarly, if a service runs 20 replicas and each replica maintains its own cache, a warm cache on replica A **does not automatically freshen replica B's cache**. Rotation must account for older replicas, newly started nodes, and rolling updates.

## 5. TTL, Refresh Time, and Expiration Time

### 5.1. TTL (Time-to-Live)

**TTL** is how long a cached entry is retained before policy considers it expired. For example:

~~~text
10:00  Resource Server fetches JWKS; cache now holds K1
10:03  Requests using K1 can verify with the cached key
10:05  Assumed 5-minute TTL expires
10:06  Next access may trigger the cache to reload the JWKS
~~~

With **lazy refresh**, TTL expiration **does not mean** an HTTP request fires at the exact 10:05 mark. Data may only be reloaded when the next verification occurs. Some caches or JWKS sources support proactive or conditional refresh; exact behavior depends on version and configuration.

Commonly distinguished policies:

- **Expire after write:** expires after a fixed duration since the entry was written/updated.
- **Expire after access:** lifetime resets whenever the entry is accessed; if misused for JWKS, stale keys can linger indefinitely when the API has steady traffic.
- **Refresh after write:** after an interval, data becomes eligible for refresh on access; many libraries continue serving the previous value while refreshing.
- **Maximum cache age:** places a hard upper bound on entry age regardless of cache hits.
- **Stale on failure:** temporarily falls back to stale entries when fetching fails, if library and security policies permit.

These mechanisms are **not synonymous**. Specifically, "an entry exists in cache" does not guarantee "that entry is still eligible for verifying tokens." Understand whether your cache serves stale entries, evicts entries, or blocks to fetch before verification.

### 5.2. Distinct Milestones in the JWK Lifecycle

An organization typically needs to track:

| Milestone | Meaning |
| --- | --- |
| **Publish key** | Publish the **new public key** in the JWKS |
| **Start signing** | Authorization Server begins signing new JWTs with the new private key |
| **Stop signing old key** | Stop issuing new JWTs with the old private key |
| **Last old token expires** | The last valid JWT signed with the old key expires |
| **Remove old public key** | Old public key can be removed from JWKS once no valid consumer needs it |
| **Cache convergence** | All Resource Servers have picked up the updated JWKS after propagation/cache refresh |

Calculating only cache TTL while ignoring **token lifetime** is insufficient for choosing when to retire an old key.

### 5.3. Is There a "Standard Mandatory" TTL for JWKS?

**There is no single TTL that fits every OAuth 2.0/OIDC system.** Some Nimbus/Spring Security defaults cache for **a few minutes**; for instance, documentation for certain Spring Security lines notes an in-memory JWKS cache of around **5 minutes**. However, **never treat 5 minutes as a universal guarantee across all versions, decoders, HTTP clients, or custom caches**.

An appropriate TTL depends on:

- Key signing/rotation frequency.
- Access token validity duration.
- Refresh behavior upon encountering an unknown `kid`.
- Availability of the JWKS endpoint.
- Replica count, network latency, and issuer load limits.
- Response-time requirements for emergency revocation or key replacement.
- Additional caching policies in Spring Cache, Nimbus, proxies, or CDNs.

Always **measure and verify behavior in the exact version you run**, and design rotation procedures that do not hinge on a single TTL number.

## 6. Safe Key Rotation with a JWKS Cache

Suppose the Authorization Server currently signs with key **K1** and wants to transition to **K2**.

A controlled rollout:

1. **Generate K2 securely**, keeping K2's private key inside the Authorization Server/KMS/HSM; never put the private key in the JWKS.
2. **Publish K2's public key in the JWKS before** issuing JWTs signed with K2. The JWKS now contains **K1 and K2**.
3. **Wait for propagation** long enough for proxies/CDNs/caches and Resource Servers to observe K2. Safe refresh on unknown `kid` can reduce lag if supported, but do not rely solely on it.
4. **Switch signing to K2**. New JWTs carry `kid: K2`; older JWTs carrying `kid: K1` may still be unexpired.
5. **Retain K1's public key in the JWKS** until the last acceptable old JWT has expired, plus clock skew tolerance and a safety margin.
6. **Remove K1's public key** once no valid consumer needs to verify K1-signed tokens. Handle cache invalidation and emergency key replacement under a dedicated policy.

~~~mermaid
gantt
    title Illustrative Key Lifecycle Transition from K1 to K2
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section K1
    Sign tokens with K1            :a1, 2026-11-01, 7d
    Keep public K1 for verification :a2, 2026-11-08, 4d
    section K2
    Pre-publish public K2          :b1, 2026-11-05, 3d
    Start signing with K2          :b2, 2026-11-08, 8d
~~~

The dates in the chart are **illustrative to show sequencing**, not fixed recommended durations. Real schedules must use your actual issuance windows, maximum JWT lifetime, clock skew, and JWKS synchronization policies.

### Example Calculation for Removing Key K1

Suppose:

- Authorization Server stops signing with **K1** at **12:00 UTC**.
- Access tokens are issued with a maximum lifetime of **15 minutes**.
- Resource Servers allow **60 seconds of clock skew**.
- The system adds a **2-minute safety margin** for propagation delays and operational variance.

Then the last token signed with K1 can remain acceptable until roughly **12:16 UTC**, making a conservative removal point for K1 **12:18 UTC or later**, once assumptions are confirmed. You must also account for actual token lifetimes, `exp` calculation, propagation, and any other token profiles sharing the same key.

**Never remove K1 from the JWKS as soon as signing switches to K2.** Doing so causes still-valid K1 tokens to suddenly fail on Resource Servers that just refreshed their JWKS.

### Never Reuse a `kid` for Different Key Material

If K2 reuses K1's `kid` with a different public key, instances with cached entries may pick the wrong key and report invalid signatures. Assign a **new, stable, suitably unique `kid`** for each key material rotation. Never use `kid` as authorization to fetch a public key outside the trusted list.

## 7. What Happens When an Uncached `kid` Appears?

This is the most critical scenario during rotation:

~~~mermaid
flowchart TD
    A["Receive JWT with kid=K2"] --> B["Check current JWKS cache"]
    B --> C{"Matching JWK for K2 present?"}
    C -- "Yes" --> D["Verify signature and validators"]
    C -- "No" --> E{"Does decoder/cache support appropriate refetch?"}
    E -- "Yes" --> F["Fetch JWKS from trusted issuer within retry/cache limits"]
    F --> G{"Valid public key K2 found?"}
    G -- "Yes" --> D
    G -- "No" --> H["Reject authentication"]
    E -- "No / unable to fetch" --> H
    D --> I{"Signature, issuer, exp, aud... valid?"}
    I -- "Yes" --> J["Proceed to authorization"]
    I -- "No" --> H
~~~

Some versions or configurations of Nimbus JWKS sources support **refreshing the cache when a key cannot be found by `kid`**. Be aware of the caveats:

- Not every cache implementation behaves the same on a `kid` miss.
- Plugging in a **custom cache** can change how Nimbus handles cache misses and refreshes.
- Some implementations throttle refresh frequency or timing to prevent attackers from sending endless JWTs with random `kid` values and forcing continuous JWKS fetches.
- If the JWKS endpoint has not yet published K2, refetching still cannot resolve it.
- If a request has a bad signature or violates issuer/algorithm rules, refreshing JWKS **cannot** make it valid.

**Do not rely on the assumption that "Nimbus will always reload the JWKS immediately on an unknown `kid`."** When designing rotation, verify the exact version and behavior of your `RemoteJWKSet`/decoder/cache adapter, and pre-publish new keys before signing as the more reliable strategy.

### Protecting Against Unknown-`kid` Flooding

An attacker can send a flood of forged JWTs with varying `kid` values. If the API tries to fetch JWKS for every unknown `kid`, the issuer can be overloaded and API latency will spike.

Principles to apply:

1. Fetch only from **approved JWKS URIs**.
2. Enforce short HTTP **timeouts**, bounded retries, and request coalescing so concurrent threads do not duplicate refreshes.
3. Use an appropriate JWKS cache lifetime and rate limiting/backoff on failed refreshes.
4. Rate-limit API traffic and monitor unknown-`kid` rates.
5. **Fail closed:** never accept a JWT simply because the JWKS endpoint is currently unreachable.

For JWTs whose key is already cached, the decoder avoids extra fetches. For an unknown `kid`, the API must verify against a trusted key source or reject authentication—**never pick a different key at random** to force acceptance.

## 8. Spring Security: Configuring Issuer and JWKS URI

A Spring Boot Servlet application acting as a Resource Server typically includes:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 8.1. Configuring `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

With this configuration, Spring Security uses the issuer to discover metadata and the JWKS URI via the supported mechanism, while also configuring JWT `iss` validation. Depending on the version, discovery may happen at startup or when the first token is processed; do not assume every version has identical startup dependencies on the issuer.

Once the key set is retrieved, the decoder can verify JWTs without calling the issuer on **every request**, provided the matching key remains cached and validation checks succeed.

### 8.2. Configuring Both `issuer-uri` and `jwk-set-uri`

When the JWKS endpoint is known upfront, you can declare:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
          jwk-set-uri: https://auth.example.com/realms/shop/protocol/openid-connect/certs
~~~

In Spring Boot/Spring Security lines that support both, `jwk-set-uri` supplies the key endpoint directly, reducing or avoiding issuer discovery at startup, while `issuer-uri` still informs `iss` claim validation. **Providing a JWKS URI does not automatically teach the API its audience or business permissions**: those rules must be configured separately.

Do not drop `issuer-uri` just because `jwk-set-uri` is set if the API actually needs issuer verification. When building a decoder manually, make sure you explicitly attach equivalent validators.

### 8.3. Separating Key Retrieval from JWT Lifetime

Even when the JWKS cache is "fresh," the Resource Server must still validate every JWT:

- **Signature/algorithm** against a trusted key.
- **Exact issuer** permitted by the API.
- **Lifetime** `exp` and `nbf` (plus any profile-specific time constraints).
- **Audience** issued for the receiving API.
- **Access token type/profile** when required by protocol.
- **Scopes/authorities**, tenant, and object-level permissions.

The JWKS cache only assists with **locating key material for verification**. It does not store "JWT X is authorized" state and does not replace authorization.

## 9. Customizing JWKS Caching with `NimbusJwtDecoder`

In certain Spring Security versions, the `NimbusJwtDecoder.withJwkSetUri(...)` builder provides **`cache(org.springframework.cache.Cache)`** to plug in an application cache. You can supply a bounded cache with a TTL, such as a Caffeine-backed cache.

> **Version note:** The code below illustrates the builder API on versions **that support `cache(Cache)`**. Verify the API in your project's actual dependencies. Cache semantics and how Nimbus handles cache misses/unknown `kid` can vary by version; replace the default cache only after understanding your version's refresh behavior.

### 9.1. Example Cache with TTL

Caffeine and Spring Cache adapter dependencies must match your application's Spring Boot version; the example below assumes `com.github.ben-manes.caffeine:caffeine` and `org.springframework:spring-context-support` are present.

~~~java
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import org.springframework.cache.Cache;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JwksCacheConfiguration {

    @Bean
    Cache jwksCache() {
        return new CaffeineCache(
            "jwks",
            Caffeine.newBuilder()
                .maximumSize(32)
                .expireAfterWrite(Duration.ofMinutes(5))
                .build()
        );
    }
}
~~~

Meaning:

- `expireAfterWrite(Duration.ofMinutes(5))` sets a **TTL for the cache entry** after it is written/updated.
- `maximumSize(32)` caps the number of entries in this cache tier, useful when a cache is shared across a few approved JWKS URIs.
- These are **illustrative values**, not a mandatory recommended TTL.
- A cache entry typically represents the **JWKS returned for a URI**, not "one JWK = one entry" or "one token = one entry."

**Do not blindly use `expireAfterAccess(...)`** if you expect the JWKS to reload after a fixed elapsed time: under continuous API traffic, an entry's TTL gets extended on every access.

### 9.2. Wiring the Cache into the Decoder While Preserving Token Checks

Configuration example for an API verifying JWTs and requiring the `orders-api` audience:

~~~java
import org.springframework.cache.Cache;
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
class OrdersJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://auth.example.com/realms/shop";
    private static final String JWKS_URI =
        "https://auth.example.com/realms/shop/protocol/openid-connect/certs";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder(Cache jwksCache) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .cache(jwksCache)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience is not accepted",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

Key points to understand:

1. `withJwkSetUri(JWKS_URI)` specifies the trusted key source; it does not mean the API accepts every token signed by any key inside it.
2. `cache(jwksCache)` changes how JWKS data is stored/reloaded via the supported adapter; **Caffeine's TTL is not the JWT TTL**.
3. `JwtValidators.createDefaultWithIssuer(ISSUER)` wires standard checks and issuer validation into the decoder. `audienceValidator` ensures the token targets this API.
4. `setJwtValidator(...)` **replaces** the decoder's validator set with the new one: preserve all essential checks instead of validating only audience.
5. If your system uses **RFC 9068 `at+jwt`** or a custom profile, add type/profile validators supported by your version instead of skipping `typ` or required claims.
6. Custom caching can alter **refresh behavior when a new `kid` is missing**; verify the contract of your chosen decoder and cache adapter.

This is an **illustrative** configuration and is not always necessary. For simpler deployments, the decoder's default cache may suffice and reduces operational complexity.

### 9.3. Be Careful with Unbounded / Non-Expiring Caches

For example, creating a `ConcurrentMapCache` without a dedicated expiration mechanism can keep a stale JWKS far longer than expected:

~~~java
// Example without built-in TTL:
// new ConcurrentMapCache("jwks");
~~~

If you attach such a cache to the decoder assuming Nimbus still enforces its default TTL, rotation issues can follow. Any application cache must have **explicit expiry, refresh, capacity, and invalidation policies** aligned with your version's behavior.

## 10. Tuning the HTTP Client for JWKS Fetching

Beyond TTL, the Resource Server must harden network calls to the JWKS endpoint:

- **Connect timeout:** avoid hanging when connections fail.
- **Read timeout:** bound how long to wait for a response.
- **TLS:** connect only to trusted endpoints, verifying certificates and hostnames per configuration.
- **Response size:** prevent endpoints or intermediaries from returning oversized payloads beyond safe bounds.
- **Retry/backoff:** cap retries; avoid request storms when the issuer is degraded.
- **Rate limiting/concurrency:** prevent multiple concurrent threads from simultaneously refetching the JWKS on a cold cache or right after TTL expiration.

In versions that support it, the `NimbusJwtDecoder.withJwkSetUri(...)` builder can accept a `RestOperations` via `restOperations(...)` to control how JWKS is fetched. Check exact API names, HTTP client hooks, and behavior against your Spring Security/Nimbus version.

Conceptual example:

~~~java
// Configuration sketch only; construct RestOperations with timeouts/TLS
// appropriate for your version and system policy:
//
// NimbusJwtDecoder decoder = NimbusJwtDecoder
//     .withJwkSetUri(jwksUri)
//     .restOperations(jwksRestOperations)
//     .build();
~~~

HTTP headers such as `Cache-Control`, `ETag`, and `Last-Modified` only help if **your HTTP client/cache layer actually honors them**. Do not assume conditional `If-None-Match` requests or HTTP 304 responses occur in every Nimbus integration. Verify refresh behavior by inspecting logs and metrics of **actual JWKS fetches**.

## 11. When the JWKS Endpoint Experiences an Outage

Distinguish between a **warm cache** and a **cache missing the key**:

| Scenario | Possible Behavior | Security Decision |
| --- | --- | --- |
| Cache still holds public key K1 matching a K1 token | Can verify locally if cache/decoder permits using that entry | Still validate signature, lifetime, issuer, and audience in full |
| Cold cache, JWKS endpoint unreachable | No key material available for verification | **Never accept** unauthenticated JWTs |
| Cache TTL expired, refresh fails | Depends on implementation: reject, bounded stale fallback, or system error | Never blindly "let through" tokens |
| K2 token arrives, cache only has K1, issuer returns no new JWKS | Cannot locate key to verify K2 | Reject K2 tokens until a trusted key is obtained |
| JWKS returns malformed JSON, missing key, or wrong algorithm | Decoder may raise verification/configuration errors | Never substitute an incompatible key |
| Issuer compromised or key emergency-revoked | Old cache may still hold the withdrawn public key | Requires emergency key procedures and dedicated invalidation/TTL limits |

**Never assume every JWKS fetch error returns 401 or 503.** The exact HTTP status depends on the failure stage, whether an `AuthenticationException` or infrastructure error occurs, entry points, exception handlers, and Spring Security version. The security invariant is **never grant access when a token cannot be verified with a policy-trusted key**.

### Should "Stale-While-Error" Be Used?

Some architectures permit serving a stale JWKS briefly if the issuer temporarily loses connectivity, to preserve availability. However:

- Stale data will not contain newly added keys, so new JWTs cannot be verified.
- Stale data may still hold removed public keys, so tokens signed by older keys may continue passing local verification.
- If **emergency revocation** is triggered due to private key compromise, continuing to use a stale cache is risky.

Therefore, **cap stale age** and define clearly when to fail closed. Never add a "skip signature validation" fallback when the JWKS endpoint errors.

### A JWKS Cache Is Not an Access Token Revocation System

In offline JWT validation, APIs verify signatures and claims rather than querying per-token revocation state. Removing a public key from a JWKS can affect **all JWTs signed by that key** once caches refresh, yet it is not an instantaneous revocation mechanism across all instances. If immediate revocation is needed, systems may require introspection, revocation state, deny lists, or short JWT lifetimes.

## 12. Manual Actions During Emergency Key Replacement

For scheduled rotation, publish the new public key before switching signers and keep the old public key long enough. For **suspected private key compromise**, security requirements may outweigh preserving old tokens:

1. Stop using the compromised private key to sign new JWTs.
2. Issue/publish a replacement public key from the controlled issuer source.
3. Decide how to invalidate tokens signed by the old key per security requirements, accepting that some clients may need to obtain new tokens.
4. **Invalidate the JWKS cache** or force applications to reload via supported mechanisms, accounting for all instances, proxies, and CDNs.
5. Monitor the issuer/Resource Servers and confirm tokens signed by the withdrawn key are handled per policy.

There is no single standard API to "clear the JWKS cache across all Spring Security instances." Invalidation depends on the caches in use: Nimbus's local cache, Spring Cache, proxies, CDNs, rolling restarts, or a pre-built admin hook. Never restart one instance and assume the whole cluster is updated.

**Private key compromise differs from routine rotation:** you may have to stop accepting still-unexpired tokens signed with the old key to protect the system. That is an operational/security decision requiring cluster-wide consistency.

## 13. Observability and Diagnosing JWKS Caching

When `401 Unauthorized` errors spike after a rotation, pinpoint where the failure occurs:

~~~mermaid
flowchart TD
    A["API rejects JWT after key rotation"] --> B{"Which kid does the token have?"}
    B --> C["Inspect trusted issuer's JWKS"]
    C --> D{"New public key published?"}
    D -- "No" --> E["Fix publish/sign ordering on Authorization Server"]
    D -- "Yes" --> F{"Did Resource Server cache the new version?"}
    F -- "No" --> G["Check TTL, cache miss, refresh, proxy/CDN"]
    F -- "Yes" --> H{"Signature and alg/kty match?"}
    H -- "No" --> I["Check signer, key material, and algorithm"]
    H -- "Yes" --> J["Check issuer, exp, nbf, aud, profile"]
    J --> K["Check scope and business permissions"]
~~~

Useful operational signals:

| Signal | What It Helps Detect |
| --- | --- |
| **JWKS fetch** counts and error/timeout rates | Overloaded issuer, network outages, refresh loops |
| **Cache hit/miss**, entry age if cache exposes metrics | Whether TTL aligns with traffic and rotation |
| **Unknown `kid`** per verified issuer/trusted context | Incomplete key-rotation propagation or forged-token load |
| JWT verification time and JWKS fetch latency | Network or cold-cache latency |
| Signature, issuer, audience, and expiry failure counts | Distinguishing key issues from token policy failures |
| Replica counts running which key/decoder config version | Drift during rolling deployments |

**Never log raw JWTs or access tokens.** `kid` can aid diagnostics, but sanitize/bound data logged from untrusted requests to prevent log injection and unbounded metric cardinality. Never create metric labels for every random `kid` sent by an attacker.

### Common Causes of 401 Errors During Rotation

- Issuer began signing with K2 before public K2 reached every JWKS endpoint/CDN.
- API's JWKS cache holds K1 and did not refresh upon seeing K2.
- Custom cache lacks a TTL or is incompatible with the decoder's refresh mechanism.
- New JWT has a `kid` differing from the JWKS value, or public key does not match the signing private key.
- JWT's `alg` differs from the algorithm allowed by the Resource Server.
- Issuer removed K1 too early while K1 tokens were still unexpired.
- JWKS URI or issuer is misconfigured on some replicas.
- TLS, timeouts, or proxies block the API from fetching JWKS.
- Signature and JWK are right, but the JWT fails `aud`, `iss`, `exp`, or token profile checks.

Never "fix" any of these errors by disabling signature verification or relaxing audience/issuer checks.

## 14. Cache Scenario Table and Expected Outcomes

Assume:

- Trusted issuer: `https://auth.example.com/realms/shop`.
- Resource Server: **Orders API**.
- Initial JWKS contains **K1**.
- Later, issuer publishes **K1 + K2** and starts signing with **K2**.
- Access tokens must be unexpired, carry audience `orders-api`, and satisfy the API's JWT/profile rules.

| Scenario | Expected Outcome |
| --- | --- |
| Valid K1 token, cache holds public K1 | Local verification succeeds if all other checks pass |
| Valid K2 token, cache already holds public K2 | Verification succeeds if all other checks pass |
| Valid K2 token, cache holds only K1, refresh succeeds | Verified once public K2 is fetched, if decoder supports this refresh path |
| Valid K2 token, cache holds only K1, refresh does not happen / fails | Cannot verify; must reject request |
| Token `kid=K2` with forged signature | Rejected even though public K2 is available |
| Expired K1 token while public K1 is still cached | Rejected due to `exp`, regardless of cached key |
| Unexpired K1 token, but public K1 was removed and cache refreshed to K2 only | K1 token may fail verification, indicating premature removal for normal rotation |
| JWKS unreachable, cold cache | Cannot verify; block the request |
| JWKS unreachable, cache holds trusted key still eligible for use | May continue verifying matching JWTs depending on cache/decoder policy |
| Valid token and key, missing `orders.write` scope | Authentication may succeed, but write operation returns 403 |

This table reflects **expected security-principled behavior**; exact fetch timing, cache hit/miss behavior, and HTTP codes on infrastructure failures depend on specific configuration and versions.

## 15. Notes on Integration Testing and Production Rollout

To test JWKS caching properly, distinguish two test categories:

**Testing token validation through the real decoder:** use JWTs signed with test keys, a test JWKS server, and K1 → K2 scenarios; observe JWKS fetch counts, behavior when a new `kid` arrives, fetch failures, and TTL timing.

**Testing authorization:** use pre-built `Authentication` or mock JWTs to verify scopes, endpoints, and business permissions. Spring Security Test helpers like `jwt()` typically bypass JWKS loading and real signature verification, so they **do not prove** cache refresh or key rotation works.

A realistic test suite should cover:

1. **Cold start:** empty cache, healthy issuer, valid K1 token.
2. **Cache hit:** consecutive K1 JWT requests do not trigger per-request JWKS fetches.
3. **TTL expiration:** verify which request triggers refresh after the actual TTL elapses.
4. **Prepublish K2:** issuer publishes K1 + K2; API still verifies K1 tokens.
5. **Unknown `kid` K2:** observe whether decoder/cache refreshes before TTL expires.
6. **Remove K1 after overlap:** all valid K1 tokens have expired before JWKS leaves only K2.
7. **Temporary outage:** distinguish warm vs. cold cache and verify fail-closed errors.
8. **Concurrent requests:** simultaneous new requests with the same `kid` do not trigger a fetch storm if coalescing/throttling is present.
9. **Bogus `kid` flood:** forged requests cannot steer fetches to any JWKS URL outside the allowlist.
10. **Bad JWT claims/signature:** having keys cached still never allows tokens with bad signatures, issuers, audiences, or lifetimes to pass.

For these cases, observe actual **HTTP JWKS fetches** and configured decoder behavior rather than guessing from controller logs. Building and running integration tests is separate implementation and QA work; this lesson explains the mechanics and scenarios to understand.

## 16. Common Misconceptions

**"JWKS cache TTL is 5 minutes, so JWTs expire after 5 minutes."**  
No. JWT lifetime is defined by `exp` and the Authorization Server's token issuance policy. JWKS TTL is the age of **public key** data in the cache.

**"When a new `kid` arrives, Nimbus is guaranteed to reload immediately."**  
There is no universal guarantee across all versions or custom caches. Verify actual behavior, and **pre-publish K2 before signing** to minimize reliance on miss-triggered refreshes.

**"Removing K1 from the JWKS immediately invalidates all K1 tokens."**  
No. Resource Servers may still cache K1; removing the key can also break valid unexpired tokens on instances that have already refreshed.

**"Using HTTP `Cache-Control` automatically configures Spring Security's TTL."**  
Not necessarily. HTTP headers and Nimbus/Spring Cache internals can be governed independently.

**"`kid` is the public key itself, so no JWKS is needed."**  
False. `kid` is only an identifier/key-selection hint and contains no cryptographic material for verifying signatures.

**"If the API loses JWKS connectivity, let requests pass to preserve availability."**  
No. When no trusted key is available to verify a token, you must **fail closed**. Whether bounded stale caching is allowed is a separate policy, never skipping signature checks.

**"Having public key K2 in the JWKS guarantees K2 tokens are valid."**  
No. The API must still verify signature, algorithm, issuer, audience, expiry, type/profile, and access permissions.

**"JWKS is where refresh tokens are stored."**  
No. JWKS publishes keys (typically public keys) for JOSE/JWT; refresh tokens are separate OAuth 2.0 credentials used by clients with the Authorization Server when granted.

## 17. Design Principles to Keep in Mind

When designing a Resource Server around JWTs and JWKS, establish clearly:

1. **Trusted key sources:** which issuers are permitted, where JWKS URIs come from, and which HTTPS/TLS and algorithms are accepted.
2. **Where caching occurs:** inside decoder/Nimbus, Spring Cache, HTTP client, or CDN; who controls lifetime and refresh.
3. **New key handling:** whether an unknown `kid` triggers a fetch, and how frequency/timeouts/retries are bounded.
4. **Rotation schedule:** pre-publish new public keys before switching signers; retain old public keys until the last old token is no longer valid.
5. **Outage handling:** warm cache, cold cache, stale policies, and key compromise events all require explicit fail-closed decisions.
6. **Independent verification rules:** signature, issuer, audience, time, token profile, and business authorization remain mandatory even when JWKS is cached.
7. **Observability:** measure fetches, cache misses, unknown `kid` rates, latency, fetch errors, and replica synchronization without exposing tokens.

**Key takeaway:** JWKS caching lets Spring Security Resource Server verify JWTs efficiently and maintain availability within defined bounds. However, a proper cache must be tied to the **issuer's key lifecycle**, **version-verified TTL/refresh behavior**, and a **rotation process with an overlap window**. Safe design relies on proactive key publication and retirement rather than assuming a decoder will always refresh at the right instant.
