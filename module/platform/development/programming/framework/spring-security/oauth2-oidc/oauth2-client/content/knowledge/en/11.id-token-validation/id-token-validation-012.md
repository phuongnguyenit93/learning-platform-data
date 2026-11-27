# 11.12. Key Caching, Key Rotation, and Handling JWKS Fetch Errors

## 1. Context: ID Tokens Must Be Verified with Trusted Keys

When a **Spring Security OAuth 2.0/OIDC Client** application uses `oauth2Login()` to log in via an OpenID Connect Provider (OP), the application receives an **ID Token** from the Token Endpoint after exchanging the authorization code. An ID Token is usually a digitally signed JWT; the client must verify the token before treating it as trustworthy authentication evidence.

For ID Tokens signed with **asymmetric** algorithms such as `RS256` or `ES256`:

- **The provider holds the private key** to sign ID Tokens.
- **The OAuth2/OIDC Client fetches the matching public keys** published by the provider via a **JSON Web Key Set (JWKS)**.
- The client picks the verification key matching the token's signature, verifies the signature, and then validates OIDC claims such as `iss`, `aud`, `exp`, `iat`, `nonce` (when used), and any other applicable constraints.
- Because providers change keys over time (*key rotation*), the client needs a strategy for **caching, refreshing, and handling JWKS fetch failures** to remain both secure and available for logins.

**Not every ID Token requires JWKS.** When provider and client agree on a symmetric algorithm such as `HS256`, verification involves the corresponding shared secret rather than RSA/EC public JWKS. This lesson focuses on the common OIDC scenario: **asymmetrically signed ID Tokens with client-side JWKS retrieval**.

**Learning objectives:** understand how the client locates the JWKS URI, selects keys by `kid`, operates caching during key rotation, distinguishes network errors from signature errors, executes overlapped key rotation, and handles outages without accepting unverified tokens.

## 2. Distinguishing JWKS, JWK, JWS, JWT, and `kid`

An OIDC system uses the following concepts:

| Term | Role | Example |
| --- | --- | --- |
| **JWT** (*JSON Web Token*) | Token format containing header/claims plus signature or encryption depending on profile | OIDC ID Token |
| **JWS** (*JSON Web Signature*) | Mechanism representing signed messages | JWT signed with `RS256` or `ES256` |
| **JWK** (*JSON Web Key*) | JSON representation of a cryptographic key | Public RSA key with `kty`, `n`, `e` |
| **JWKS** (*JSON Web Key Set*) | Collection of JWKs, usually published at an HTTP endpoint | `{"keys":[...]}` |
| **`kid`** (*Key ID*) | Key label in JWS header / JWK to locate candidate verification keys | `"login-signing-2026-11"` |
| **`alg`** | Algorithm required by the JWS to verify the signature | `RS256` |
| **`use`** / **`key_ops`** | Key usage purpose when declared | `sig` / `verify` |
| **`jwks_uri`** | HTTPS address of the JWKS published in provider metadata | `https://login.example.com/keys` |

Example header of a signed ID Token:

~~~json
{
  "alg": "RS256",
  "kid": "login-signing-2026-11",
  "typ": "JWT"
}
~~~

The header is merely data sent **with the token**. It is **not proof** that the provider signed the token with a trusted key. The client must apply the allowed algorithm and a key fetched from the **trusted source bound to the exact provider**, then execute signature verification.

Example JWKS with two public RSA keys, key material abbreviated for readability:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "login-signing-2026-10",
      "alg": "RS256",
      "n": "<base64url-modulus-old>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "login-signing-2026-11",
      "alg": "RS256",
      "n": "<base64url-modulus-new>",
      "e": "AQAB"
    }
  ]
}
~~~

`n`/`e` are **public** components of an RSA key; the abbreviated placeholders here are not valid keys for running verification. For EC keys you may see `crv`, `x`, and `y`. A public JWKS for verification **must never expose private key material**, such as RSA `d`/`p`/`q` or EC private `d`.

### 2.1. `kid` Helps Select a Key, Not Confirm Token Validity

The logical sequence is usually:

1. Safely read the JWS header to obtain `kid` and `alg`.
2. Look up the trusted public key list of the **corresponding issuer**.
3. Select a candidate key matching `kid`, key type, algorithm, and intended use.
4. Verify the signature over the **exact JWS bytes**.
5. If the signature is valid, continue checking **OIDC claims**.

**A matching `kid` alone does not make a token valid.** Similarly, a JWT can be decoded into JSON without any valid signature; reading the payload never replaces verification.

`kid` is not globally unique across the Internet. Two different issuers can use the same `kid`. Cache keys and trust boundaries should incorporate **the trusted issuer / JWKS source** and required attributes, never merging all providers into one global map keyed solely by `kid`.

### 2.2. Never Trust URLs or Algorithms Self-Proposed by the Token

When a token contains `jku`, `x5u`, or another key URL header, **never automatically fetch from a token-supplied URL** unless that URL is explicitly permitted by client policy and bound to the trusted provider. Otherwise, an attacker could supply their own JWKS endpoint and sign tokens with their own private key.

Likewise, never accept `alg=none` or switch from an asymmetric algorithm to a symmetric one at the token's request. Algorithm policy must come from trusted configuration and IdP support, never from unverified input.

## 3. How Does Spring Security Know Where to Fetch JWKS?

In OIDC, the **issuer** is the provider's canonical identifier, for example:

~~~text
https://login.example.com
~~~

The provider can publish metadata at the corresponding discovery address, such as for a root issuer:

~~~text
https://login.example.com/.well-known/openid-configuration
~~~

Illustrative metadata excerpt:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/keys",
  "id_token_signing_alg_values_supported": ["RS256", "ES256"]
}
~~~

In a Spring Boot application, OIDC Client registration typically uses `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://login.example.com
~~~

When the provider supports discovery, Spring Security/Spring Boot can fetch metadata to build `ClientRegistration`, thereby determining `jwks_uri`. Endpoints and issuer must match the provider's official metadata/registration. For issuers with paths or realms, the exact discovery location follows standard metadata rules and provider behavior; never guess by concatenating strings and assuming it is correct.

**Three layers must be clearly distinguished:**

1. **Metadata discovery:** fetching the provider descriptor document, typically occurring when building client registrations / at application startup, which can fail startup if the IdP is unreachable.
2. **JWKS retrieval:** fetching the public key list for signature verification; may happen when creating the decoder or when encountering a token to verify, depending on implementation.
3. **ID Token validation:** selecting the right key, verifying the signature, and validating ID Token claims **each time an ID Token is checked**, even when the public key is already cached.

When using `oauth2Login()` in Spring Security, the framework provides a dedicated **OIDC ID Token decoder** (e.g., per-`ClientRegistration` decoder construction such as `OidcIdTokenDecoderFactory` in versions with this API). **Do not equate it with a `JwtDecoder` bean used solely for Resource Server.** Customizing Resource Server caching does not automatically change how OAuth2 Login validates ID Tokens.

## 4. Flow of Fetching, Selecting, and Caching Public Keys

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as Spring Security OIDC Client
    participant Cache as JWKS / Key cache
    participant P as OIDC Provider

    B->>C: Callback authorization code + state
    C->>P: POST Token Endpoint (code + PKCE if used)
    P-->>C: Token Response with ID Token (JWS, kid=K2)
    C->>Cache: Look up public key for issuer and kid=K2
    alt Cache has matching usable key
        Cache-->>C: Public key K2
    else No matching key / refresh needed
        C->>P: GET jwks_uri over HTTPS
        P-->>C: JWKS containing public keys K1, K2
        C->>Cache: Update key set per policy
        Cache-->>C: Public key K2
    end
    C->>C: Verify signature and OIDC claims
    C-->>B: Complete login or reject
~~~

**The cache here caches public verification keys**, not a "token already valid" outcome shared across users. Every ID Token must still have its signature and claims checked.

### 4.1. Why Is Caching Needed?

If the backend downloads JWKS for **every login**, it creates heavy traffic to the IdP, adds latency, and makes logins strictly dependent on the JWKS endpoint's availability on every request. Proper caching provides:

- Fewer network requests when tokens share a key set.
- Faster logins when the public key is already cached.
- Lower risk of overloading the JWKS endpoint during multi-instance traffic spikes.
- Ability to continue verifying tokens with trusted keys for a **policy-bounded window** if the JWKS endpoint temporarily loses connectivity.

Availability gains must always be balanced against key freshness: **caching too long can miss new keys or the revocation of old keys**.

### 4.2. Caching a JWKS vs. Caching Individual Keys

An implementation may store the entire **JWKS document**, or store parsed keys. These are two representations of the same source data; key selection logic must still depend on issuer and proper criteria.

| Cache Type | Benefit | Caution |
| --- | --- | --- |
| JWKS cached per trusted issuer/JWKS URI | Holds entire key set to resolve `kid` values | Must refresh when key set changes |
| Selected key cached per issuer + `kid` + algorithm/policy | Fast lookup under high token volume | Must update/evict keys when JWKS changes |
| HTTP cache (`ETag`, `Cache-Control`) | Reduces bandwidth, supports revalidation | May be constrained by HTTP client / library version |
| Discovery result cache | Avoids repeated metadata downloads | Does **not** prove JWKS keys are still fresh |
| DNS cache | Reduces DNS lookups | Does not replace JWKS caching or TLS checks |

In projects using Spring Security, part of the caching may be handled by **Nimbus JOSE + JWT** and underlying HTTP client components. **Never assume a fixed TTL or a rule that "unknown `kid` always triggers an immediate reload" across all Spring Security/Nimbus versions**; inspect behavior for your exact dependencies and configuration.

## 5. Sound Caching Strategy: Freshness, TTL, and Refresh

Three timestamps should be distinguished:

| Timestamp | Meaning |
| --- | --- |
| **Fetched at** | Time when the cache successfully retrieved JWKS |
| **Fresh-until** | Window during which cached entries are preferred before revalidating per policy |
| **Hard expiry / maximum staleness** | Cutoff after which stale cache must no longer be used, if controlled stale caching is allowed |

Not every library cache API exposes all three timestamps. This is a conceptual model for balancing **availability** against **rotation/revocation**.

### 5.1. Cache Hit

The ID Token uses `kid=K1`, public key K1 is in the trusted key set, and the cache still satisfies policy. The decoder uses that key to **verify the signature** and validate claims. There is no need to download a fresh JWKS merely because a new token arrived with the same `kid`.

### 5.2. Cache Miss Due to a New `kid`

The provider starts signing with K2 while the cache currently holds only K1. The client can perform a **rate-limited JWKS refresh** to locate K2.

Logic pattern:

~~~text
Received ID Token: issuer=company, alg=RS256, kid=K2

1. Select the configured JWKS source for the company issuer.
2. Search cache for key K2 matching algorithm/usage.
3. If not found:
   - Trigger refresh only per rate-limit / single-flight policy.
   - Fetch JWKS over TLS from the trusted URL.
   - Parse and replace/update key set per policy.
   - Search again for K2.
4. If K2 is still absent -> reject ID Token.
5. If K2 is found -> verify signature + validate OIDC claims.
6. If signature or claims fail -> reject.
~~~

This is an **illustrative algorithm**, not a prescription for the exact refresh sequence of every library version. A specific cache may trigger refreshes based on TTL, key miss, HTTP cache validators, or custom callbacks.

### 5.3. Cache Expired by TTL

Once the cache exceeds its allowed lifetime, the decoder must refresh before relying on cached keys per active policy. When the JWKS endpoint errors out, choosing to **reject** versus **use a last-known-good key within bounds** must be decided from your risk model. Never automatically trust expired keys indefinitely.

Hypothetical timeline:

~~~text
T0      fetch JWKS (K1)
T0+5m   cache reaches revalidation point
T0+6m   JWKS endpoint temporarily fails
T0+7m   ID Token with kid=K1 arrives

If policy disallows stale cache:
    reject because valid verification key cannot be obtained per policy

If policy allows bounded stale cache:
    consider only previously trusted public key K1,
    still enforce signature/issuer/audience/time/nonce verification,
    enforce hard-expiry and monitor the incident
~~~

Using stale keys is a **security trade-off**: if the provider just revoked K1 due to a leaked private key, a client keeping K1 cached could continue trusting signatures from the compromised key. In compromise incidents or strict policies, **fail closed**.

### 5.4. What About ETag and HTTP Cache-Control?

A JWKS endpoint may return:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "jwks-v42"
~~~

On the next revalidation, the HTTP client can send `If-None-Match`; on a valid `304 Not Modified` response, the client reuses cached data per HTTP semantics.

However, **do not assume every JWKS decoder layer automatically uses `ETag`, `Cache-Control`, or `304` identically**. Some caches enforce internal TTLs; some HTTP clients are custom-configured; some implementations discard HTTP response headers. When fine-grained control is needed, check the exact cache API and HTTP transport in your Spring Security/Nimbus version.

### 5.5. Preventing "Thundering Herd" and Unsafe Negative Caching

If many requests simultaneously hit an unknown `kid` during key rotation, hundreds of pods might fetch JWKS at once.

Mitigations include:

- **Single-flight** within a process: only one in-flight JWKS refresh per source at a time, while concurrent requests wait with a timeout.
- **Rate limit / cooldown** for refreshes triggered by unknown `kid`.
- **Timeouts, bounded retries, and backoff with jitter** when the JWKS endpoint errors out.
- **Never cache negative misses for long:** caching "K2 does not exist" too long can prolong login outages during a new key rollout even after the provider updated JWKS.
- **Never let attacker-chosen `kid` values** trigger unbounded outbound network fetches.

Refresh limits defend against DoS, yet **a cache miss must never fall back to accepting unverified tokens**.

## 6. Planned Key Rotation: Overlap Window Between Old and New Keys

Providers regularly rotate keys to reduce risk and satisfy compliance policies. If a provider removes K1 the instant it starts signing with K2, clients caching K1 or verifying older ID Tokens can fail.

Planned rotation model with two keys:

~~~mermaid
flowchart LR
    A["Phase 1\nJWKS: K1\nSign ID Token: K1"] --> B["Phase 2\nJWKS: K1 + K2\nSign ID Token: K1"]
    B --> C["Phase 3\nJWKS: K1 + K2\nSign ID Token: K2"]
    C --> D["Phase 4\nJWKS: K2\nSign ID Token: K2"]
~~~

### 6.1. Recommended Sequence

1. **Prepare new key pair K2** in the provider's key management system. Private keys are never exposed via JWKS.
2. **Publish public key K2 in JWKS** while the provider still signs ID Tokens with K1. This lets clients discover K2 before it is used.
3. **Wait an appropriate propagation window** based on JWKS cache TTL, CDN/proxy caches, client refresh behavior, and network latency. Never assume all clients refresh instantly.
4. **Switch signing key to K2.** New ID Tokens carry header `kid=K2` and signatures created with private K2.
5. **Continue publishing K1** long enough for still-valid K1-signed ID Tokens to verify, accounting for token lifetimes, allowed clock skew, and system characteristics.
6. **Remove K1 from JWKS** once the transition window passes and there is no longer a reason to trust the old key. If marked compromised, do not wait for the normal window.
7. **Monitor** unknown `kid` errors, signature verification failures, JWKS refresh counts, HTTP errors, and login failure rates before, during, and after rotation.

Illustrative timeline:

| Time | Provider JWKS Publishes | Key Signing New Tokens | What Client Must Do |
| --- | --- | --- | --- |
| 09:00 | K1 | K1 | Use/cache K1 |
| 09:10 | K1, K2 | K1 | On refresh, may receive both keys |
| 09:30 | K1, K2 | K2 | Receive K2 token; cache miss may refresh to locate K2 |
| 10:30 | K1, K2 | K2 | Still verifies valid older K1 tokens |
| After overlap window | K2 | K2 | Upon JWKS refresh, stop trusting K1 per policy |

These timestamps are **illustrative scenarios**, not mandatory TTLs or universal OIDC wait times.

### 6.2. How Long Before Removing K1?

No single number fits every system. The provider must weigh:

- Maximum remaining validity of **ID Tokens signed with K1**.
- Clock skew permitted by clients.
- Cache TTL / hard expiry of clients, proxies, CDNs, or JWKS retrieval libraries.
- Multi-region / multi-instance rollout duration.
- Other services verifying signatures with the same key set.
- Rollback feasibility from K2 back to K1 if incidents arise.

What matters is removing K1 **only when policy permits and no old tokens still need acceptance**, unless the key was compromised and trust must stop immediately.

### 6.3. Use a New `kid` When Creating a New Key

Assign a **new, stable Key ID to each signing key**; avoid reusing the same `kid` for different public key material. If a provider publishes K2 while keeping label `kid=K1`, clients may select the wrong cached old key and fail verification or behave unpredictably.

When a single JWKS has multiple keys sharing a `kid` or lacking a `kid`, candidate selection depends on the library and algorithm. A provider actively managing key rotation should publish unambiguous metadata so clients select keys deterministically.

## 7. Emergency Rotation for a Compromised Key vs. Scheduled Rotation

**Key compromise** occurs when the provider suspects a private signing key was leaked, misused, or lost confidentiality. Operational handling differs from planned rotation.

For a compromised K1:

1. Provider **stops signing with K1 immediately** per incident response plan.
2. Generate/activate K2 from a secure key source and publish public K2.
3. **Remove K1 from trusted sources** via emergency revocation procedures, rather than keeping K1 just so old ID Tokens can still log in.
4. Coordinate with clients to **refresh/evict JWKS caches holding K1**; otherwise, clients relying on stale caches could keep accepting signatures from K1.
5. Evaluate **revoking/terminating existing login sessions** and related credentials/tokens according to blast radius.
6. Monitor anomalous logins, signature failures, and revocation propagation time.

One essential point: in a session-based Spring Security web app, **ID Tokens are normally verified at login**, after which the app relies on **session cookies** for subsequent requests. Removing K1 from JWKS **does not automatically destroy already-logged-in app sessions**. If a private key leaks, the organization may need separate session-revocation, reauthentication, and token-handling actions.

**Never rely on stale JWKS indefinitely to keep logins working during a key-compromise incident.** Availability must never be traded for continuing to trust a known-compromised key.

## 8. Spring Security OAuth2 Login: Basic Setup and Decoder Responsibilities

### 8.1. Servlet Application Dependencies

Spring Boot Servlet example:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Security configuration:

~~~java
@Configuration
class OidcLoginSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Classes/annotations use the corresponding Spring Security and Spring Framework imports; imports are omitted for brevity.

Together with `spring.security.oauth2.client.registration.corporate` and provider `issuer-uri` from section 3, Spring Security handles the OAuth2 Login flow and OIDC ID Token validation according to the running version's capabilities.

**What not to do:** manually parse the ID Token from the HTTP response and `Base64`-decode `sub` as an authenticated identity. Signature, issuer, audience, expiration, and nonce checks (when applicable) must live inside a trusted decoder/validator mechanism.

### 8.2. Key Configuration in `ClientRegistration`

In Spring Boot, provider settings can include properties like:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-oidc:
            issuer-uri: https://login.example.com
~~~

`issuer-uri` is the starting point for retrieving standard metadata and building provider details. Configuring `jwk-set-uri` explicitly can be useful in certain scenarios, yet it must point to the **official, trusted** JWKS URL of that issuer. **Never arbitrarily swap in another provider's JWKS** to work around a key-fetch failure.

If endpoints are configured explicitly rather than via discovery metadata, the application must still preserve full OIDC validation, including issuer and ID Token checks. Changing how the JWKS URI is resolved **must never weaken** trust boundaries.

### 8.3. WebFlux

In WebFlux, the security configuration takes an analogous form:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveOidcLoginSecurity {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

`ReactiveClientRegistrationRepository` manages client registrations in WebFlux, while reactive OAuth2/OIDC components execute authorization-code exchange and ID Token validation. Customizing HTTP clients / JWKS retrieval must use **extension points suited to the reactive stack**; never drop blocking Servlet code into a WebFlux pipeline.

### 8.4. Customizing Caching at the Right Extension Point

Two verification flows are easily confused:

| Flow | Token Verified | Component to Adjust When Customizing JWKS |
| --- | --- | --- |
| **OAuth2/OIDC Login** | **ID Token** returned to OAuth2 Client | OIDC ID Token decoder/factory and HTTP retrieval for **OAuth2 Login** |
| **Resource Server** | JWT **Access Token** sent to an API | Corresponding `JwtDecoder` / resource-server JWT configuration |

Configuration like:

~~~java
http.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()));
~~~

is how you **protect an API as a Resource Server**, not the single or default mechanism controlling the ID Token decoder inside `oauth2Login()`.

Similarly, an application-defined `WebClient` bean with proxy, timeout, and retry settings **is not guaranteed** to be used automatically by OIDC Login's JWKS retrieval. The JWKS decoder may use its own HTTP client or cache. If the application genuinely needs to customize TTL, networking, cache store, or JWKS refresh, inspect the **Spring Security and Nimbus JOSE + JWT versions** in your dependency graph and use the exact supported decoder/factory/JWK-source APIs.

Never replace the OIDC authentication provider with custom JWT-verification code solely to tweak TTL: doing so easily drops nonce, issuer, audience, `azp`, expiry, and OIDC constraints.

## 9. Resolving JWKS Fetch Errors: Do Not Treat All Failures the Same

Errors can happen at multiple layers. Each layer demands a different response:

| Scenario | Observable Symptom | Explanation | Priority Action |
| --- | --- | --- | --- |
| Backend DNS fails to resolve JWKS host | `UnknownHostException` or equivalent | Resolver/private DNS lacks record or route | Check DNS from the VM/pod running the app |
| TCP connection to JWKS fails | Connect timeout/reset | Firewall, NAT, route, proxy, or NetworkPolicy | Check egress path and timeouts |
| TLS trust fails | `PKIX path building failed`, certificate error | JVM does not trust CA, missing chain, wrong cert | Fix truststore/CA and hostname |
| JWKS returns `401`/`403` | HTTP unauthorized/forbidden | Endpoint misprotected or gateway blocking | Public JWKS must be reachable per provider contract; check ACL/gateway |
| JWKS returns `404` | Not found | Wrong `jwks_uri`, changed issuer/realm/path | Verify official metadata |
| JWKS returns `429` | Rate limit | Too many refreshes / unknown `kid`s | Backoff, cooldown, cache/single-flight |
| JWKS returns `502`/`503`/`504` | Upstream unavailable | Gateway/IdP down or overloaded | Timeout, bounded retry, alerting |
| JWKS returns HTML/invalid JSON | Parse failure | WAF/login portal returned HTML or error payload | Inspect redacted content-type/body and proxy route |
| Cache has K1, token has `kid=K2` | Unknown key ID | Provider rotated keys or untrusted token | Bounded JWKS refresh; reject if K2 absent |
| K2 in JWKS yet signature fails | Signature verification failure | Tampered token, wrong key, wrong algorithm, or wrong issuer | Reject; never try arbitrary keys |
| JWKS valid yet token `iss`/`aud` wrong | Claims validation failure | Token not issued for expected issuer/client | Reject; check provider and client config |
| `nonce` mismatch | OIDC correlation failure | ID Token does not belong to initiated authorization request | Reject; check flow, state/session, and nonce |
| Fails on only some pods | Cache/network inconsistency | Pods have different versions/caches or egress | Compare cache age, dependencies, proxy, DNS, and rollout |
| Fails right after rotation | Cache still holds old key or misses new key | Provider published key too late or decoder didn't refresh | Check publish timeline, TTL, and refresh behavior |

**Never conclude "JWKS is broken" solely because OIDC Login failed.** Authorization code, PKCE verifier, state/session, client authentication, claim validation, and Resource Server are separate steps. Determine whether the error occurred during **key fetching**, **key selection**, **signature verification**, or **claims validation**.

### 9.1. Unknown `kid` and Invalid Signature Are Two Different Failures

Example:

- Current JWKS has public key K1. Token header declares `kid=K2`. Decoder **cannot find a candidate key**. A valid refresh may retrieve K2.
- JWKS has K2 and token also declares K2, yet signature verification fails. This is **signature invalid**; never "fix" it by disabling verification, accepting the token because payload "looks right," or trying untrusted keys.

An attacker can send floods of JWTs with random `kid` values to force cache misses. Therefore refresh only from the **configured JWKS URI** under proper cooldown/rate limits; **never load a new key server from token header data**.

### 9.2. Distinguishing Transient Network Errors from Trust Errors

Losing network reachability to JWKS is an availability incident; a certificate with the wrong host or untrusted chain is a **server identity failure**. Their fixes differ:

- Network timeout: check proxy/route/firewall, tune bounded timeouts/retries if needed.
- TLS validation error: verify CA and hostname; fix certificates/trust material, never disable verification.
- Unknown `kid` after rotation: verify provider published K2 and decoder refreshes per policy.
- Invalid signature: reject token and investigate integrity / token provenance.

Never use "trust all certificates," "disable hostname verification," or drop `iss`/`aud` checks to get past login errors.

## 10. Policy When the JWKS Endpoint Is Temporarily Unavailable

This is a trade-off between **availability** and **key trust freshness**.

### 10.1. No Matching Trusted Key Available

If the JWKS endpoint is unreachable and the cache **has no matching key** to verify the signature, the client cannot prove the ID Token is valid.

**Safe behavior: reject login** or show a transient error and let users restart the flow once systems recover. Never allow login based on decoded claims alone.

### 10.2. Matching Last-Known-Good Key Available

If the cache still holds K1 previously fetched from the official provider, the application **may** continue verifying ID Tokens signed with K1 for a short period if **security policy permits bounded stale cache usage**. Minimum conditions:

1. K1 came from the configured issuer's JWKS and was previously fetched over a trusted channel.
2. The token actually verifies cryptographically with K1, not just by matching `kid`.
3. All other OIDC checks still run: issuer, audience, expiry, nonce when present, etc.
4. Cache age remains within the policy's hard-expiry bound.
5. There is no signal that K1 was revoked/compromised.
6. Stale cache usage is monitored and time-bounded, never indefinite.

This is **controlled graceful degradation**, not a guaranteed default behavior across Spring Security/Nimbus versions. Some organizations mandate failing closed immediately once the cache is no longer fresh; that policy is also valid, especially for sensitive applications.

### 10.3. When You Cannot Tell Whether a Key Was Pulled from JWKS

If the network is down, the client cannot know whether the provider pulled K1 due to routine rotation or compromise. Every minute spent trusting stale cache carries a defined risk window. For high-security apps, prefer a **short staleness threshold** or fail closed.

A feature that "keeps all old public keys forever until tokens expire" **does not replace** key revocation checks. During a compromise, forged tokens can be signed with the leaked private key well before `exp`. Emergency incident procedures are required outside normal cache TTLs.

### 10.4. Never Retry Infinitely Inside the Authentication Filter

If JWKS retrieval times out, blocking login requests indefinitely or retrying without limits can exhaust worker/thread/event-loop resources. Instead:

- Set connect/read/overall timeouts suited to your infrastructure.
- Bound retry counts and apply backoff with jitter where appropriate.
- Never retry signature/claim validation errors as if they were network errors.
- Apply single-flight / cooldown to cache refreshes.
- Present clear user-facing error messages and log sanitized operational details.

Not every HTTP error warrants retries. For example, a `404` from a wrong JWKS URI or a TLS hostname mismatch requires a **configuration fix**, not aggressive retries.

## 11. Testing JWKS and TLS from the Exact Application Runtime Environment

When an IdP sits on an internal network or behind an egress proxy, test **from the pod/VM/container running Spring Boot or an environment sharing identical DNS, routing, and truststore**. Testing from a laptop only proves the laptop's network path.

Example for a root-path issuer:

~~~bash
# Read verified provider metadata.
curl --connect-timeout 5 --max-time 15 -fsS \
  https://login.example.com/.well-known/openid-configuration \
  | jq -r '.issuer, .jwks_uri, (.id_token_signing_alg_values_supported // [])'
~~~

In the output, confirm `issuer` matches client configuration and `jwks_uri` points to the provider-published endpoint. The discovery path above applies to root issuers; for issuers with paths/realms, use the provider's exact discovery URL.

Fetch the key set using the actual URL from metadata, e.g., if the provider publishes `https://login.example.com/oauth2/keys`:

~~~bash
curl --connect-timeout 5 --max-time 15 -fsS \
  https://login.example.com/oauth2/keys \
  | jq -r '.keys[] | [.kid, .kty, (.alg // "-"), (.use // "-")] | @tsv'
~~~

This command inspects only **public key metadata**; it prints no tokens or credentials. `jq` is an optional JSON tool; on environments lacking `jq`, use another JSON reader.

If the provider uses an internal CA verified by your organization:

~~~bash
curl --cacert /opt/app/certs/corp-root-ca.pem \
  --connect-timeout 5 --max-time 15 -fsS \
  https://login.example.com/oauth2/keys
~~~

To inspect the direct connection's TLS certificate when OpenSSL is available:

~~~bash
openssl s_client \
  -connect login.example.com:443 \
  -servername login.example.com \
  -showcerts
~~~

If real traffic traverses an HTTP CONNECT proxy or TLS inspection, direct connection results may differ. Inspect proxy/DNS/truststore settings of the **HTTP client Spring Security actually uses to fetch JWKS**, rather than relying solely on `curl`.

**Especially:** `curl` succeeding does not prove the JVM will succeed, because CA stores, proxy env vars, HTTP clients, DNS resolvers, and timeouts can differ. `curl -k` simply bypasses TLS validation and proves nothing about secure configuration; never use it in production.

### 11.1. JVM Truststore and Private CAs

If you see errors like:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

inspect the provider's certificate chain and Java trust material. You can build a dedicated verified truststore:

~~~bash
keytool -importcert \
  -alias corporate-root \
  -file corp-root-ca.pem \
  -keystore corporate-truststore.p12 \
  -storetype PKCS12
~~~

Then configure the JVM or relevant HTTP client to use that truststore. Replacing the global JVM truststore can drop default public CAs if the new file omits them; ensure other endpoints remain properly trusted.

**Note:** the truststore holds CAs for verifying **server TLS certificates**, not the JWKS public key cache. Successful TLS trust does not make JWKS contents safe if the issuer/JWKS URI was misconfigured; conversely, a valid JWKS never justifies skipping TLS hostname verification.

### 11.2. Watch Out for Proxy/CDN Caching

An HTTP proxy or CDN in front of the JWKS endpoint might keep serving **the old key set** even after the provider published K2. Check:

- Has the provider backend published K2 yet?
- Does the proxy/CDN cache JWKS with its own TTL?
- Do HTTP response headers align with rotation policy?
- Do clients across regions see the same JWKS version?
- Do proxy authentication or allowlists affect the JWKS URI?

Do not force "always fresh" by disabling caching entirely under heavy traffic; prefer a TTL/refresh strategy aligned with rotation timing and request budgets.

## 12. Tracking Library Versions and Actual Cache Behavior

Spring Security can use multiple library layers for OIDC/JWT, where JWT/JWK handling typically involves **Nimbus JOSE + JWT**. Specific behavior varies by version:

- Does caching live at the decoder, JWK source, JWKS document, or HTTP client layer?
- What is the default TTL?
- Does an unknown `kid` trigger an immediate refresh, or wait for TTL?
- Is refresh rate-limited when unknown `kid`s arrive continuously?
- Are `ETag`/HTTP cache headers honored?
- Are stale keys accepted during network errors, and within what bounds?
- Is a decoder created **per `ClientRegistration`**, per issuer, or shared depending on app configuration?
- Are there hooks to supply a custom HTTP client, proxy, cache, or validator?
- Does OIDC login behavior match Resource Server decoder behavior?

**Never treat a default TTL like "5 minutes" as an immutable rule** without checking your actual version and configuration. Likewise, never promise "unknown `kid` always refreshes immediately" without verifying the implementation.

When behavior changes are needed, prefer official Spring Security/Nimbus mechanisms: custom OIDC decoder/factory/JWK source or version-appropriate HTTP retrieval APIs. Never strip OIDC claim validation just to plug in a custom cache.

### 12.1. Structural Outline for a Custom Cache (Pseudocode)

Algorithmic outline of a safe key resolver:

~~~text
resolveSigningKey(issuer, allowedAlgorithms, tokenHeader):
    assert issuer is configured and trusted
    assert tokenHeader.alg belongs to allowedAlgorithms

    cache = keySetCache.forIssuer(issuer)
    key = cache.findCandidate(
        kid=tokenHeader.kid,
        alg=tokenHeader.alg,
        use="sig"
    )

    if key absent:
        if refreshPolicy.allowsAttempt(issuer):
            refreshOnceWithTimeout(
                jwksUri=configuredMetadata[issuer].jwksUri
            )
            key = cache.findCandidate(...)

    if key absent:
        fail("No trusted signing key available")

    if cache too stale under active security policy:
        fail("Trusted key freshness requirement not met")

    return key
~~~

This is **architectural pseudocode**, not a built-in API to copy into Spring Security. It handles only **key selection**; higher layers must still verify the signature and **all OIDC ID Token claims**. If you build this logic yourself, carefully evaluate trust boundaries, concurrency, TTLs, and JOSE edge cases; configuring a maintained, vetted library is usually safer.

## 13. Old Keys, Login Sessions, and Token Lifetimes: Three Separate Lifecycles

Operations teams sometimes notice "we removed K1 from JWKS, yet users who logged in earlier are still inside the app." That is not necessarily a JWKS cache bug.

In an HTTP-session-based web app:

1. User completes OIDC Login. Client verifies the ID Token using public K1.
2. Spring Security creates `Authentication` and stores it in the application session.
3. Subsequent browser requests can use the **session cookie**, without fetching JWKS or re-validating the ID Token on every request.
4. Provider removes K1 from JWKS. **Already-authenticated app sessions can remain active** until expired or invalidated per session policy.

Additionally:

- **ID Token expiration** governs when the ID Token remains acceptable as an assertion per policy.
- **Access token expiration** governs the lifetime of credentials used to call APIs.
- **JWKS cache lifetime** governs how fresh the public key set is.
- **Application session lifetime** governs how long the user's session at the application lasts.

These four horizons can differ. When a signing key is compromised, evaluate the impact on **existing logged-in sessions**, not just JWKS replacement.

## 14. Deployment Scenarios and Analysis

### Scenario A — Provider Prepares to Rotate K1 to K2

Provider publishes a JWKS containing K1 and K2 before switching signing to K2. Spring Boot instances across regions hold different JWKS caches.

**Approach:** publish K2 early enough for clients to refresh; compute wait times from actual cache policies/rollouts; then switch signing and monitor unknown `kid`. Keep K1 during the overlap window so valid older ID Tokens can still verify. Never swap private/public key material while reusing the same `kid` out of habit.

### Scenario B — After Rotation, a Group of Pods Fails with Unknown `kid=K2`

Some pods have K2; others keep using cached K1 or are blocked from JWKS by an egress proxy.

**Approach:** compare library versions, cache age, refresh capability, proxy, and DNS per pod. Confirm the JWKS endpoint truly serves K2 and requests from failing pods reach the right trusted URL. Never fix by letting clients accept unverified ID Tokens.

### Scenario C — JWKS Endpoint Returns 503 During Peak Logins

IdP authentication / Token Endpoint still responds, while JWKS is unavailable.

**Approach:** if clients hold a valid key under policy, they may continue verifying ID Tokens signed by that cached key **within the allowed window**. For unknown `kid`s or missing keys, reject. Bound retries and monitor the outage. If policy mandates always-fresh JWKS, fail closed when unable to refresh.

### Scenario D — JWT Has Matching `kid` Yet Invalid Signature

JWKS publishes K1 and the token also declares `kid=K1`, yet the signature fails.

**Approach:** reject the ID Token. Never assume it is merely a "stale cache," as the token may be tampered with, signed by another private key, misrouted from another issuer, or the provider mismanaged keys. Verify issuer/algorithm/key config and investigate after blocking the token.

### Scenario E — JWKS URL Uses an Enterprise CA Certificate

`curl` succeeds on a laptop, while the Spring Boot container throws PKIX errors.

**Approach:** inspect the CA chain and hostname, import the trusted CA into the truststore/SSL context **actually used by the HTTP client fetching JWKS**, and inspect proxy interception and pod DNS. Never use "trust all" to bypass TLS errors.

### Scenario F — Key K1 Compromised While App Allows Long Stale Cache

IdP removes K1, yet the client still accepts K1-signed tokens because hard TTL has not expired.

**Approach:** trigger emergency procedures to invalidate/refresh caches, stop trusting K1, and evaluate issued sessions/tokens. Stale caching meant to survive ordinary outages must never prevent revoking a compromised key.

### Scenario G — Token from Another Issuer Has the Same `kid`

A multi-tenant app uses two OIDC Providers A and B, both naming their key ID `current`.

**Approach:** cache and select keys by **trusted issuer/JWKS URI**, never by `kid` alone. An ID Token from provider B must never be verified with provider A's key or matched to a different `ClientRegistration` simply because key labels collide.

### Scenario H — Session Survives After Provider Removes Signing Key

A user who logged in before rotation continues accessing the website via session.

**Approach:** this reflects the difference between **login-time ID Token validation** and **per-request session validation**. If forced re-authentication is needed, enforce session/reauthentication policy or revoke sessions rather than relying on JWKS rotation alone.

## 15. Monitoring and Operational Alerting

A reliable OIDC Client system should separate **JWKS fetch errors**, **key selection errors**, **signature errors**, and **claim errors** rather than collapsing them into a single "login failed" metric.

| Suggested Metric/Event | Meaning |
| --- | --- |
| `jwks_fetch_success` / `jwks_fetch_failure` | Success/failure rate contacting the JWKS endpoint |
| `jwks_fetch_duration` | Latency fetching the key set |
| `jwks_cache_hit` / `jwks_cache_miss` | Rate of serving keys from cache |
| `jwks_refresh_trigger{reason=ttl_or_unknown_kid}` | Reason for reload; keep label cardinality bounded |
| `jwks_unknown_kid` | Token lacked a matching key in the trusted source |
| `id_token_signature_failure` | Invalid signature despite finding a matching key |
| `id_token_claim_failure` | Invalid issuer/audience/time/nonce or other OIDC check |
| `oidc_login_success` / `oidc_login_failure` | Overall authentication outcome |

These metric names are illustrative suggestions, not default Spring Security metrics. Never put raw `kid`, `state`, `nonce`, or tokens into metric labels with unbounded cardinality; attacker-sent fake `kid` values can blow up monitoring costs.

In incident logs, helpful non-sensitive fields include:

- **Normalized** registration ID / issuer and JWKS hostname.
- Failure stage: discovery, TCP, TLS, HTTP, JSON parse, key selection, signature, OIDC claim validation.
- HTTP status, exception type, and request duration.
- Cache age / cache hit/miss and timestamp of last successful refresh.
- Internal correlation ID of the login flow, carrying no credentials.

**Never log** raw ID Tokens, access tokens, authorization codes, client secrets, private keys, session cookies, PKCE verifiers, or nonces; even payloads containing identity attributes can be sensitive data.

### 15.1. Watching Alerts Over Time

A spike in `unknown_kid` right when a provider rotates keys suggests caches are not refreshing quickly enough. A spike in `jwks_fetch_failure` with network errors points to JWKS endpoint / egress issues. A spike in `signature_failure` while JWKS loads normally can indicate key misconfiguration, wrong issuer, wrong algorithm, or forged tokens; never weaken security policies automatically just to "turn the dashboard green."

## 16. Common Misconceptions

**"The token's `kid` is in the JWKS, so the ID Token is valid."** No. `kid` only identifies a candidate key; signature and claims must still be verified.

**"Caching keys means skipping signature checks on subsequent logins."** No. Caching avoids repeated network key downloads; it never skips verifying each new token.

**"Enabling `oauth2ResourceServer().jwt()` configures the cache for OIDC Login."** No. Resource Server verifies incoming API access tokens; OAuth2 Login verifies ID Tokens through its own flow/decoder.

**"When seeing an unknown `kid`, fetch JWKS from the token's `jku` URL."** No. The JWKS source must remain bound to the trusted issuer/provider, never taken from an unverified token.

**"A cache miss definitely means the provider just rotated keys."** No. It could be a forged token with an arbitrary `kid`, an issuer mismatch, or an out-of-sync JWKS endpoint.

**"The JWKS endpoint returned 503, so skip signature verification."** No. Without a matching trusted public key, reject. If using stale cache, follow a bounded policy and still verify signature and claims.

**"Rotating the signing key automatically logs out all users."** No. Existing login sessions can be independent of verifying new ID Tokens; manage sessions separately.

**"Fetching JWKS over HTTPS is enough; skip issuer/audience validation."** No. JWKS is only part of validation; tokens must come from the right issuer for the right client.

**"Any `invalid_grant` error comes from JWKS."** No. `invalid_grant` usually involves token exchange, authorization code, redirect URI, PKCE, or grant state; JWKS is used during signature verification after receiving the ID Token.

**"Share one `kid`-keyed cache across all tenants to save memory."** Unsafe. Always scope by issuer / JWKS source to avoid mixing keys across providers.

## 17. Self-Check Questions

**Q1.** An ID Token declares `alg=RS256` and `kid=K2`, yet the cache only has K1. Should the application auto-accept the token because the provider is rotating keys?

**Answer:** No. The application can refresh JWKS from the trusted source per policy. If no matching K2 is found or signature verification fails, reject.

**Q2.** A provider prepares to rotate K1 to K2. Which order minimizes login failures?

**Answer:** Publish public K2 in JWKS **before** signing new tokens with private K2 so caches have time to update; switch signing to K2; retain public K1 for an appropriate transition window; only then remove K1 once no old tokens need verification, except in a compromise.

**Q3.** If the JWKS endpoint is down yet K1 is cached, can you skip `iss` and `aud` checks to keep logins running?

**Answer:** No. Even when using a cached key under policy, the client must verify the signature and all mandatory OIDC claims, including issuer, audience, timestamps, and nonce when applicable.

**Q4.** Why is the JWKS cache TTL not synonymous with ID Token expiration?

**Answer:** Cache TTL governs freshness of **public keys**; `exp` in the ID Token governs whether the token is still valid. An expired token does not become valid just because its key is cached, and an overly stale key can be rejected by policy even if the token has not expired.

**Q5.** Can you use a Resource Server `JwtDecoder` bean to reliably alter ID Token caching in `oauth2Login()`?

**Answer:** You cannot assume that. Identify the exact decoder/factory and HTTP/JWK cache for **OIDC Login**, according to your Spring Security version and stack.

**Q6.** Why do HTTP `503` from the JWKS endpoint and `signature verification failed` require two different responses?

**Answer:** `503` is an availability failure on key retrieval; it may call for bounded retries and checking egress/cache policy. Signature failure is a token verification failure; reject it without blind retries or disabling checks.

**Q7.** In a multi-tenant OIDC Client, can two issuers share the same `kid`?

**Answer:** Yes. `kid` is a key identifier within a key set, not a global identifier. Caches must bind keys to the trusted issuer / JWKS source.

**Q8.** When a private signing key leaks and the IdP removes its public key from JWKS, should the application keep accepting keys from stale cache?

**Answer:** No. Execute emergency revocation policy, refresh/evict caches, and assess affected sessions/tokens. Controlled stale caching for routine network outages must never override compromise signals.

**Q9.** `curl` fetches JWKS successfully on a laptop, yet the app in Kubernetes fails with TLS errors. What should you inspect?

**Answer:** Pod DNS/routing, egress proxies, server certificate SAN/chain, and the CA truststore or SSL context of the HTTP client actually fetching JWKS; laptops and containers may have different trust material.

**Q10.** A user who logged in with a K1-signed ID Token remains on the website after K1 is removed from JWKS. Is that proof the cache failed to update?

**Answer:** Not necessarily. The web app may be using a session cookie to authenticate subsequent requests rather than re-verifying the ID Token every time. Session management and revocation are separate mechanisms.

## 18. References

- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OidcIdTokenDecoderFactory](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/oidc/authentication/OidcIdTokenDecoderFactory.html)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0 — jwks_uri](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

**Key takeaway:** JWKS is the **trusted public-key source bound to the exact issuer** for verifying asymmetrically signed ID Tokens. Caching lowers load and latency, yet requires freshness bounds and proper refresh mechanisms when new keys appear. Providers must rotate keys with a **public-key overlap window**; when a key is compromised, revoke it under emergency procedures. Whenever no valid trusted key is available or signature/claims fail, the application **rejects authentication** rather than skipping validation to keep logins working.
