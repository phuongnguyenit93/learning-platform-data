# Authorization Server Downtime and Its Impact on Startup and Verification

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server** system, an outage of the **Authorization Server (AS)** does not necessarily bring every API protected by access tokens to an immediate halt. The actual impact depends on **when connectivity is lost**, **how the Resource Server discovers metadata and verification keys**, **token format**, and **which key data is already available**.

For example, the Orders API accepts JWT access tokens issued by an Identity Server. When the Identity Server experiences an incident, three completely different outcomes can occur:

- **The Orders API is just starting up:** the application may need to call the issuer to discover metadata/JWKS before finishing verifier initialization.
- **The Orders API is already running and holds verification keys:** an unexpired JWT can continue to be verified locally, even while the Identity Server is temporarily down.
- **The Orders API needs to fetch new keys or run introspection:** if no matching key is available, or if the token is an opaque token requiring remote verification, request authentication may fail.

Therefore, the question “If the Authorization Server goes down, does the Resource Server keep working?” has no single **yes/no** answer across all configurations. You must distinguish **discovery**, **decoder initialization**, **JWK retrieval and refresh**, **access token verification**, and **issuing new access tokens**.

> **Security principle:** You can design a Resource Server to reduce startup dependence on the AS, but **never let requests through simply because the AS or JWKS is unreachable**. The API accepts a token only after fully verifying signature, issuer, audience, lifetime, and permissions.

## 1. Participating Components

Suppose the system has:

- **Shop Web:** OAuth2/OIDC Client requesting access tokens for users.
- **Identity Server:** Authorization Server/issuer `https://identity.example.test/realms/shop`.
- **Orders API:** Spring Security Resource Server accepting access tokens with audience `orders-api`.
- **JWKS endpoint:** where the issuer publishes public keys used to verify signed JWT tokens.

A normal flow:

~~~mermaid
sequenceDiagram
    actor User as User
    participant Client as OAuth2 Client
    participant AS as Authorization Server
    participant API as Orders API
    participant JWKS as JWKS endpoint

    User->>Client: View order
    Client->>AS: Request access token (via grant)
    AS-->>Client: Signed access token
    Client->>API: GET /api/orders/42 + Bearer JWT
    opt No matching key in memory/cache yet
        API->>JWKS: Fetch public JWK
        JWKS-->>API: JWKS
    end
    API->>API: Verify signature, iss, aud, exp, and scope
    API->>API: Check order permissions
    API-->>Client: Result or rejection
~~~

In a simple deployment, metadata and JWKS may both be served by the Identity Server; the diagram separates endpoint names to highlight **two network calls with distinct roles**. The AS may go down completely or only one of its endpoints may fail.

### Two Tasks Easily Confused

| Task | Goal | Typical timing | Requires AS online? |
| --- | --- | --- | --- |
| **Discovery** | From the issuer, find metadata such as `jwks_uri` and related endpoints | At decoder construction/startup, depending on version and config | **Yes**, if discovering over the network with no alternative config |
| **JWT signature verification** | Use a trusted public key to verify an access token's signature | When receiving a Bearer JWT | **Not necessarily**, if the right key is already cached; may need JWKS when missing/refreshing keys |

**Issuer URI** is the publisher's identifier and the basis for discovery. **JWKS URI** is the address for fetching public keys. **Audience** identifies the API receiving the token. These three values have distinct functions and cannot substitute for one another.

## 2. What Does Issuer Discovery Do?

Knowing only the issuer:

~~~text
https://identity.example.test/realms/shop
~~~

The Resource Server can use **Authorization Server Metadata** or **OpenID Provider Configuration** mechanisms supported by the library to resolve the issuer's metadata. Metadata may contain:

~~~json
{
  "issuer": "https://identity.example.test/realms/shop",
  "jwks_uri": "https://identity.example.test/realms/shop/protocol/openid-connect/certs",
  "authorization_endpoint": "https://identity.example.test/realms/shop/protocol/openid-connect/auth",
  "token_endpoint": "https://identity.example.test/realms/shop/protocol/openid-connect/token"
}
~~~

This is an **example of format and values**, not mandatory metadata for every product. A Resource Server verifying JWTs mainly needs to know the **issuer and verification key source**; an OIDC Client may additionally need authorization/token endpoints.

### 2.1. Discovery Is Not Signature Verification

Discovery answers: “Where does the issuer advertise **its keys and endpoints?**” It **does not by itself prove** that an access token sent to the API is valid. After discovery, the Resource Server still must:

1. Fetch or use the appropriate public key from a trusted configured source.
2. Verify the JWS/JWT using allowed algorithms and keys.
3. Validate `iss` against the trusted issuer, `exp`/`nbf` lifetimes, and `aud` against the API.
4. Build principal/authorities only from the verified token.
5. Check scopes and permissions on the business resource.

### 2.2. Discovery Can Affect Startup

When the application declares **only** `issuer-uri`, automatic decoder creation may need to contact the issuer to locate the JWKS endpoint. In an initialization mode that discovers metadata immediately when building the decoder, if the AS is unreachable then **the application cannot finish initializing the verifier**, which can cause a startup failure.

Exact behavior depends on the **Spring Security/Spring Boot version**, how `JwtDecoder` is constructed, and whether component initialization is eager or deferred. Under some configurations, lookup may be deferred until handling the first request. Therefore, do not claim every version “always calls the AS at startup”, nor design availability on the assumption that “discovery is definitely lazy”.

Practical rule: **if startup may require remote discovery, an AS outage can become a Resource Server startup outage**.

## 3. Timeline: When Does the AS Go Down?

### 3.1. Before the Resource Server Starts Up

A common configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
~~~

Spring Security can use the issuer location to automatically discover metadata and locate `jwks_uri`. If this step runs before or during startup while the issuer is down, the decoder fails to initialize and the application may fail to start.

Operational consequences:

- New pods/instances may fail startup or readiness checks.
- A rolling deployment may fail to replace old instances if new instances depend on discovery.
- Autoscaling during an AS incident may spin up additional unready instances.
- Already-running instances do **not necessarily** stop alongside the new ones.

One way to reduce discovery dependence at startup is declaring **both issuer and JWKS URI** per the trust contract, shown in section 5.

### 3.2. After the API Has Started and Holds the Right Keys

Suppose the AS has issued a JWT with an RS256 signature. The Orders API has fetched the corresponding public JWK and currently holds the key in memory/cache.

When the AS goes down:

1. Clients already holding an unexpired access token can still send requests.
2. The API can verify the signature using the existing public key **without calling the AS on every request**.
3. The API still enforces `iss`, `aud`, `exp`, `nbf`, scopes, and data permissions per policy.
4. Valid requests can continue to be processed, provided the verifier has the right key and no other mandatory network dependency arises.

This is a benefit of **self-contained signed JWTs**: the Resource Server does not have to call the Authorization Server for every signature check. However, having and being able to use cached keys depends on the library, configuration, cache lifetimes, and key rotation activity.

**Do not interpret “JWTs enable offline verification” as “every instance can always verify offline”.** Newly launched instances, empty caches, or tokens signed with an unfamiliar key may still need the JWKS endpoint.

### 3.3. When the Resource Server Lacks the Key or Needs to Refresh JWKS

Cases that may require contacting the AS/JWKS again:

- A new instance has never loaded the JWK.
- The JWK cache has expired and the implementation needs to reload.
- A token carries a new `kid` after the issuer rotated keys.
- The verifier cannot find a matching key for the token's `alg`/`kid`.
- Policy or configuration requires contacting another remote data source.

If JWKS is unreachable in these cases, **the API cannot pretend the signature was verified**. Requests depending on an unavailable key must be rejected or fail according to the designed error-handling mechanism.

| Situation | Local verification capability | Impact when JWKS is down |
| --- | --- | --- |
| JWT signed with a key still in cache and cache is usable | Possible | Request can pass the signature step |
| JWT signed with an unknown `kid` | No matching key | Cannot verify; request fails |
| Cache expired and refresh is required before verification | Depends on library/configuration | May fail even if token is unexpired |
| Newly started instance that never held keys | Typically not yet | First verification may fail |
| Resource Server uses locally distributed public keys | Possible, for tokens signed by those keys | Does not need JWKS for current keys, but lifecycle/rotation must be handled |

Cache policies do not share a single universal duration across all Spring Security/Nimbus JWKS implementations. Do not write application logic assuming “JWKs are always cached for 24 hours” without verifying your exact version and configuration.

### 3.4. When the Authorization Server Recovers

Once the AS/JWKS recovers, instances lacking keys can re-fetch JWKS according to library mechanics and retry/cache policies. Requests that failed earlier **do not automatically succeed retroactively**; Clients may need to retry safely per HTTP/business semantics.

If the AS rotated keys during the outage, ensure new public keys are properly published, old keys remain available for the lifetime of older tokens, and caches refresh as planned.

## 4. Comparing Issuer and JWKS Configurations

| JWT Resource Server configuration | Issuer discovery when building decoder | Issuer check | Possible network dependency during verification |
| --- | --- | --- | --- |
| Only **`issuer-uri`** | May be needed to find `jwks_uri` | Yes, when decoder is configured properly for issuer | May still need to fetch/refresh JWKS |
| **`issuer-uri` + `jwk-set-uri`** | Can avoid discovery lookup at startup | **Still checks `iss`** under compatible Spring config | May need to fetch/refresh JWKS when key is missing |
| Only **`jwk-set-uri`** | No issuer discovery needed | **Does not automatically infer valid issuer** from JWKS URI alone | May need to fetch/refresh JWKS |
| **Locally** distributed public key and explicitly configured decoder | Needs no remote discovery or JWKS to use local key | Must configure issuer/audience validators manually | Needs no key endpoint for tokens using distributed keys, but rotation is your responsibility |

The **issuer + JWKS URI** approach is often helpful when you want the application to start during temporary AS downtime while still validating the issuer claim. This addresses **startup discovery dependence**; it **does not guarantee** every JWT request succeeds while JWKS is down, since key loading may still be needed during token processing.

### Note on Standalone `jwk-set-uri`

If you configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

the API knows the public key source, yet **no `iss` constraint is specified here**. Verifying a signature with a JWK does not replace the issuer condition. If multiple token groups are signed across shared infrastructure, omitting issuer/audience makes it easy to trust the wrong tokens.

Therefore, when omitting `issuer-uri` from auto-configuration, build `JwtDecoder` manually and attach sufficiently strong validators, or use an equivalent configuration mechanism that explicitly checks the issuer.

## 5. Spring Boot Configuration to Reduce Startup Discovery Dependence

Examples use **Spring Boot 3 / Spring Security 6**. Endpoints, issuers, and audiences are illustrative only; replace them with values published by the Identity Server for your real environment.

### 5.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 5.2. Providing Issuer and JWKS URI Separately

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Example environment variables:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

When `jwk-set-uri` is provided directly, the decoder knows the key address **without querying issuer metadata to discover it** during initialization. At the same time, declaring `issuer-uri` preserves issuer validation in compatible Spring Boot/Spring Security auto-configuration.

**Distinction needed:** Skipping discovery at startup **is not synonymous with** already having downloaded the JWKS. A decoder may fetch JWKS when verifying the first request or when a new key is needed. If JWKS is down then and no key is cached, the API cannot verify the signature.

### 5.3. Shared `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This is an example configuration for a REST API **authenticating exclusively via Bearer tokens**, so it disables CSRF and uses stateless sessions in the API filter chain. Applications that also have cookie-based logins or browser endpoints must configure CSRF, sessions, and filter chains appropriately.

Spring Security can map `scope` or `scp` claims in supported formats into `SCOPE_...` authorities. The `orders.read` condition protects the operation type; it does not replace checking owner/tenant on specific orders.

### 5.4. When Explicit Audience Validation Is Needed

The right issuer can still issue JWTs for other APIs. The Orders API must reject tokens whose `aud` does not contain `orders-api`. An example decoder with custom validators:

~~~java
import org.springframework.beans.factory.annotation.Value;
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
class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        // JWKS URI comes from configuration; no discovery needed to find this address.
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        // Includes default JWT rules and issuer validation.
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        // Validly signed tokens meant for another API must still be rejected.
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token audience is not accepted",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));
        return decoder;
    }
}
~~~

This example clarifies two distinct responsibilities: `NimbusJwtDecoder` uses trusted JWKs to **verify signatures**, while validators determine whether **the token is accepted by the API** based on issuer, lifetime, and audience. Before moving to production, configure permitted algorithms, token type/profile, and mandatory claims per the publisher contract.

Never “handle an outage” by removing `JwtDecoder`, dropping `iss`/`aud` validation, or fabricating a mock `Authentication` with full privileges. When the decoder cannot verify a token, the request must fail securely.

### 5.5. If You Want to Eliminate Request-Time JWKS Fetching Too

In some architectures, an organization may **distribute trusted public keys via configuration or files** alongside the application instead of fetching JWKS dynamically. The API can then verify tokens signed by distributed keys without contacting a JWKS endpoint.

Conditions that must be managed carefully:

- Public keys must be provisioned from a trusted administrative source, never taken from token headers or requests.
- The verifier must still restrict algorithms and validate issuer, audience, expiration, and token type.
- **Key rotation** requires a process to update and publish new public keys before the AS starts signing with the new key.
- If only **one** public key is distributed, tokens signed with a new key may be rejected until the Resource Server is updated.
- A public key alone does not identify which issuer a token belongs to; the application must still enforce issuer policy.

Local key distribution can suit environments with strict independence requirements, but weigh operational overhead and the risk of trusting old keys for too long. Do not choose it to bypass rotation or revocation mechanisms.

## 6. AS Downtime Is Not Identical to JWKS Endpoint Downtime

Within an identity provider, multiple endpoints may share infrastructure yet serve different purposes:

| Endpoint / capability | Who is impacted when down? | Can a running JWT Resource Server continue? |
| --- | --- | --- |
| **Authorization endpoint** | Users/Clients cannot easily start authorization code flows or new logins | Possible, with existing JWT tokens and matching keys |
| **Token endpoint** | Clients cannot exchange codes, refresh tokens, or request `client_credentials` tokens | Possible, with already-issued unexpired access tokens |
| **Discovery metadata** | Instances/decoders needing metadata discovery may fail | Possible, if discovery already completed or JWK endpoint is explicitly configured |
| **JWKS endpoint** | APIs needing to fetch/refresh public keys may fail | Possible, if valid permitted keys are already cached |
| **Introspection endpoint** | Resource Servers using opaque tokens struggle to verify requests | Usually **no**, if fresh introspection is required each time without a designed fallback |
| **Revocation endpoint** | Clients/AS cannot process token revocations via that endpoint | Already-issued JWTs still rely on lifecycle policies |

A full AS outage can affect all functions simultaneously. An incident affecting only the authorization UI does not necessarily take JWKS offline. When diagnosing an outage, identify **exactly which endpoint failed**.

## 7. JWT Resource Server Differs from Opaque-Token Resource Server

### 7.1. Signed JWT: Capable of Local Verification

Asymmetrically signed JWT access tokens allow the Resource Server to:

- Verify JWS using a trusted public key.
- Check `iss`, `aud`, `exp`, `nbf` on the token.
- Map valid scopes/claims into authorities.
- Check permissions and business data.

Once public keys and required configuration are present, these steps **do not require calling the AS on every request**. However, the API may still depend on other systems to look up dynamic permissions, policies, or data; outages of those systems are a separate concern.

### 7.2. Opaque Token: Typically Requires Introspection

With opaque access tokens, the API normally cannot read/verify contents locally via JWS; it must call an introspection endpoint:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Corresponding security chain:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

This is an **alternative configuration** to JWT processing in the earlier example; do not enable both simultaneously expecting the framework to guess token types without an explicit design.

~~~mermaid
sequenceDiagram
    participant Client as OAuth2 Client
    participant API as Opaque Resource Server
    participant AS as Introspection endpoint

    Client->>API: Bearer opaque token
    API->>AS: Introspect token with appropriate credentials
    alt AS returns trusted result
        AS-->>API: active and metadata
        API->>API: Check active, audience, scope, policy
    else AS unreachable
        API--xAS: Timeout / connection error
        API-->>Client: Cannot authenticate / appropriate error
    end
~~~

If the introspection endpoint is down and the API needs a fresh response to verify tokens, it must **fail closed**: never assume all opaque tokens remain active. Some systems design introspection result caches, but caching trades off freshness of revocation status, lifetimes, permission changes, and security requirements. **Never extend `active = true` indefinitely** when the endpoint stops responding.

### 7.3. A Valid JWT Is Not Automatically “Allowed” Under Latest State

Offline JWT verification brings resilience, yet introduces a trade-off: an unexpired token can still be accepted even if the account was just disabled, permissions just changed, or the session just logged out, if the API checks only the local JWT.

Risk-based mitigations can include:

- Short-lived access tokens.
- Checking user/tenant/permission state against a live data source.
- Introspection or a revocation/status signaling mechanism by design.
- Protecting sensitive operations strictly with up-to-date policies and business state.

No single option eliminates every trade-off: **local verification** lowers network dependence but may react slowly to changes; **online status verification** updates faster but depends on the availability of the checking service.

## 8. Impact on OAuth2 Clients and OIDC Login

When the AS is down, not only the Resource Server is affected. **Clients** usually need the AS to request new tokens:

| Client flow | AS-dependent step | When AS is temporarily down |
| --- | --- | --- |
| **Authorization Code + OIDC login** | Auth redirect, consent, exchanging code for token | New logins/code exchanges typically fail |
| **Refresh token** | Sending refresh token to token endpoint | Cannot obtain new access tokens |
| **Client Credentials** | Service requesting access token from token endpoint | Cannot obtain new tokens |
| **Client holding an unexpired access token** | Sending token to API | Can still call JWT API if API can verify it and permissions hold |

In OIDC, an **ID token** is used by the OIDC Client to process login results; it is **not** an access token for calling a Resource Server. AS downtime blocks new logins/refreshes, but that does not mean the Resource Server should accept ID tokens in place of access tokens.

If a system maintains a user session on the web application side, that session may have its own expiration policy. **Having a web session does not guarantee** the application still holds a valid access token to call APIs, especially when refreshing requires reaching a downed AS.

## 9. Designing for Availability Without Trading Away Security

### 9.1. Clear Goals: Startup Independence, Verification, or Token Issuance?

An availability plan should separate three goals:

1. **Startup independence:** New instances can build security components even if the AS metadata endpoint is temporarily down.
2. **Verification availability:** Running instances hold the right keys to verify JWTs per contract.
3. **Token issuance availability:** Clients can obtain/refresh new access tokens.

Declaring `issuer-uri + jwk-set-uri` primarily helps goal **1**. Key distribution/caching/rotation mechanisms help goal **2**. Goal **3** depends on the availability of the AS/token endpoint and cannot be solved solely by changing Resource Server config.

### 9.2. Never Fail Open When Losing the AS

Wrong ways to handle unreachable JWKS/introspection:

~~~text
If unable to fetch JWK -> skip signature check.
If AS down -> trust any token with sub and scope.
If introspection times out -> default active = true.
If issuer does not respond -> accept tokens from any issuer.
~~~

These behaviors turn an availability incident into an **authentication vulnerability**. The safe approach is using only trusted keys already held and still policy-compliant, or rejecting unverifiable requests. If returning a status indicating an unavailable dependency, design proper error handling while still **not executing the protected action**.

### 9.3. Timeouts, Retries, and Circuit Breakers

For calls to metadata, JWKS, or introspection:

- Choose **connection timeout** and **read timeout** according to latency budgets and environment characteristics.
- Retry only likely transient errors within strict bounds; avoid creating a retry storm when the AS is struggling.
- Use backoff/circuit breakers at the appropriate layer to protect threads and resources while the dependency is down.
- Monitor JWKS refresh failure rates, introspection latency, and metadata fetch errors.
- Ensure network errors are never translated into “valid token”.

Do not build custom cache and retry wrappers around JOSE libraries without understanding how the library manages `kid`, `Cache-Control`, TTLs, and key updates. Exact behavior must be tuned to the library/version in use.

### 9.4. Readiness and Liveness

An API can be **alive** yet not **ready** to handle a class of requests because JWKS could not be loaded:

- **Liveness** should reflect that the process is healthy; avoid tying liveness to an external AS so all pods do not mass-restart whenever the AS goes down.
- **Readiness** reflects service readiness per system requirements, but carefully weigh whether coupling readiness tightly to the AS causes **cascading outages** and blocks rollouts/autoscaling.
- Use checks on mandatory issuer/audience config and separate observability on verification key state to assess true availability.

No single readiness setup fits every environment: an API verifying JWTs with cached keys differs sharply from one requiring introspection on every request. Metrics should distinguish **AS down**, **API missing keys**, and **genuinely invalid tokens**.

## 10. Monitoring, Diagnostics, and Error Messages

Incident symptoms can surface at different layers:

| Symptom | Likely cause | What to check |
| --- | --- | --- |
| New instance fails startup during AS outage | Discovery during decoder init depends on remote metadata | `issuer-uri` config, stack trace, lookup timing |
| Old instances still process JWTs, new instances fail | Old instances have JWK cache, new instances do not | JWKS URI, keys/`kid`, cache, and rotation |
| Old JWTs work, new JWTs signed with different `kid` are rejected | New key not fetched yet | JWKS response, refresh, issuer, algorithms |
| All opaque-token requests fail during AS outage | Introspection endpoint unresponsive | Connection/timeouts, credentials, cache policy |
| Clients cannot log in or refresh | Authorization/token endpoint down | Redirect/token exchange errors |
| JWT has valid signature, yet API returns 401 | Wrong issuer/audience, expired, or wrong token type | Token contract and validators |
| Valid JWT, yet API returns 403 | Insufficient scopes/permissions or denied by data policy | Authority mapping, ownership/tenant |
| API starts up, but first request hits 401/connection error | JWKS loaded on demand during verification | JWT decoder and JWKS retrieval logs |

**Do not infer solely from HTTP status codes.** A network error fetching JWKS can flow through different authentication/error-handling paths depending on framework and configuration, producing 401 or another service error; missing scope typically yields 403. Analyze decoder logs and metrics to identify the real cause while avoiding leaking unnecessary details to Clients.

### Safe Logging

You may log:

- Request/correlation ID and endpoint.
- Error category: discovery failure, JWKS fetch failure, unknown `kid`, issuer/audience mismatch, expired token, insufficient scope.
- **Configured** issuer/audience and verified facts, following the organization's logging policy.
- Dependency status and latency calling metadata/JWKS/introspection.

Never log **raw access tokens**, refresh tokens, client secrets, private keys, or unnecessary sensitive claims. Before signature verification, `iss`/`sub`/`kid` in a token are **sender-controlled data** and must be logged and handled with appropriate caution.

## 11. Realistic Scenarios by Phase

### Scenario A — New Deployment During AS Outage

The Orders API is configured with only `issuer-uri`. The decoder needs to discover metadata at startup, but the metadata endpoint is unresponsive.

**Possible outcome:** the instance fails to complete startup. The fix for systems needing reduced startup dependency is declaring a trusted `jwk-set-uri` alongside the issuer or using a suitable key-distribution mechanism. After changing config, still test JWT acceptance and key rotation; starting up successfully does not mean every token will verify.

### Scenario B — AS Goes Down After JWTs Were Already Verified

An Orders API instance already holds the active public JWK. Shop Web holds an unexpired access token with a known `kid` and `aud = orders-api`.

**Possible outcome:** the API continues verifying JWTs and enforcing scopes/data permissions without calling the AS. Once the access token expires, Shop Web may be unable to refresh until the token endpoint recovers.

### Scenario C — AS Rotates Keys Right Before an Outage

The AS begins signing JWTs with key `kid = new-key`, while the Orders API only holds `old-key`. Meanwhile, the JWKS endpoint is unresponsive.

**Correct outcome:** the API refuses JWTs it cannot verify. A sound rotation procedure publishes new public keys before signing with them, allows caches to update, and keeps old keys long enough for older tokens.

### Scenario D — JWT with Valid Signature but Wrong Audience

The AS issued a valid token for `billing-api`, and a Client sends it to the Orders API. The AS is down, but the Orders API holds the old key.

**Correct outcome:** reject the token on the `aud` check. Having local verification keys is no excuse to skip audience checks.

### Scenario E — Opaque Tokens and Introspection Disrupted

The Orders API uses `opaque-token` and must call introspection for each new token. The AS does not respond.

**Correct outcome:** forbid protected operations when token status cannot be verified. If the system caches introspection results, behavior must follow an approved TTL/expiration/revocation policy; never “treat every token as still active” during an outage.

### Scenario F — One Instance Has Keys While Another Does Not

A load balancer distributes requests across two pods: pod A already downloaded JWKS, while pod B just restarted with an empty cache. The AS is down.

**Possible outcome:** the exact same JWT may succeed on A and fail on B. This is a **per-instance key state** issue, not permissions changing randomly on the token. Inspecting per-pod logs, `kid`, JWKS cache state, and rollout strategy identifies the root cause.

## 12. Tests to Have Before Deployment

To verify the architecture, design integration/chaos test scenarios in a test environment—no need to disrupt the production Authorization Server:

| Scenario | What to observe |
| --- | --- |
| Start API with only issuer when metadata endpoint is unreachable | Actual startup behavior for the exact version/framework |
| Start API with issuer + JWKS URI when discovery endpoint is down | Decoder builds without discovery; does not yet imply first request will succeed |
| API holds cached keys, then AS/JWKS goes down | Whether JWTs signed with known keys remain accepted per cache policy and lifetime |
| JWT has new `kid` while JWKS is down | Unverifiable token must be rejected |
| JWT has valid signature but wrong `iss` | Rejected |
| JWT has right issuer but wrong `aud` | Rejected |
| JWT expired or has future `nbf` | Rejected |
| Valid JWT missing scope | Rejected at authorization |
| API uses opaque tokens, introspection unresponsive | Protected operations are not executed |
| OIDC Client refreshes token during AS outage | Clear failure, with UX status/recovery handling |
| JWKS key rotation after AS recovers | API picks up new keys per process without disabling signature checks |

The critical tests here are **behavior with/without network connectivity and differences between startup and runtime**. A test that merely checks whether the `jwk-set-uri` property has a value does not prove the Resource Server actually degrades safely when the issuer is unavailable.

## 13. Runbook When the Authorization Server Goes Down

### Step 1 — Determine Incident Scope

Check the metadata endpoint, JWKS, token endpoint, authorization endpoint, and introspection endpoint individually. A single label like “AS down” can cover very different failure modes.

### Step 2 — Identify the API's Verification Path

The API is using:

~~~text
(A) Signed JWT + issuer discovery
(B) Signed JWT + explicit issuer-uri and jwk-set-uri
(C) Signed JWT + local public keys
(D) Opaque token + introspection
~~~

For (A), check startup discovery dependence. For (B)/(C), check key state matching `kid` and caching. For (D), check introspection and fault-tolerance policy.

### Step 3 — Protect Requests During the Incident

Keep cryptographic, issuer, audience, and permission checks intact. Never accept unverified JWTs or opaque tokens without introspection/trusted basis. If degraded mode is required, run only **operations requiring no new authentication or covered by pre-designed trusted permission mechanisms**—never invent temporary permissions on the fly.

### Step 4 — Limit Impact on Startup and Rollouts

If the decoder requires discovery at startup, consider pausing non-essential changes causing mass restarts during the outage, keeping healthy existing instances running when safe and operationally sound. Longer term, configuring issuer + JWKS URI or key distribution can lower rollout risk, subject to testing key rotation separately.

### Step 5 — Recover and Verify

Once the AS recovers, confirm Clients can obtain new tokens, APIs can fetch JWKS, tokens signed with the current `kid` pass verification, issuer/audience match, and endpoints still enforce scopes/data permissions. Review metrics to spot any requests or instances still tied to old keys or misconfiguration.

### Step 6 — Capture Lessons on Dependency Boundaries

Document explicitly **how independent startup must be**, **how independent verification must be**, and **what SLA token issuance requires**. Those goals lead to different solutions; there is no single config flag that makes all of OAuth2/OIDC work completely offline.

## 14. Common Misconceptions

**“If the Authorization Server is down, the JWT Resource Server is definitely down.”** Not necessarily. The Resource Server can verify JWTs using existing public keys. However, discovery/JWKS/introspection or other dependencies may cause some instances/requests to fail.

**“Having `jwk-set-uri` means every JWT is verified offline.”** No. The JWKS URI only tells the API **where to fetch** keys; with an empty cache or a new `kid`, the API may still need to call that endpoint.

**“No issuer needed since JWKS is already known.”** False under a normal contract. JWKS verifies signatures, yet does not replace rules checking `iss`, `aud`, and token profile.

**“As long as the token decodes, we can grant access while AS is down.”** False. Base64URL decoding does not prove integrity or origin. Never fail open.

**“The Resource Server calls the token endpoint to verify every JWT.”** Signed JWTs are typically verified locally with public JWKs without calling the token endpoint per request. Opaque tokens using introspection are a separate mechanism.

**“When the AS goes down, existing users are immediately logged out of all apps.”** Not by default. Application sessions and issued access tokens have their own lifetimes. However, new logins/token refreshes may fail while the AS is unavailable.

**“JWTs never need the AS again after the first time.”** Not completely. JWKS refreshes/key rotation and revocation policies may require further interaction. A validly signed JWT also does not automatically reflect all latest permission changes.

**“Returning 200 to keep the system running during an outage is acceptable.”** If credentials cannot be verified, returning protected data creates a vulnerability. Availability must never be bought by dropping authentication/authorization.

**“Readiness failing means we should immediately restart all pods.”** Not necessarily. Mass restarts while metadata/JWKS are down can turn instances holding cached keys into empty-cache instances, widening the outage. Liveness/readiness must be designed around dependency types and serving requirements.

---

**Key takeaway:** A Spring Security Resource Server with `issuer-uri` may need **metadata discovery** from the Authorization Server when initializing the decoder; if the AS is down, that can affect **startup**. Adding a trusted **`jwk-set-uri`** skips the discovery lookup to locate keys at initialization while still allowing **`iss`** validation. During **runtime JWT verification**, the Resource Server can continue processing issued tokens if it holds matching keys and tokens are valid, yet will run into trouble when fetching/refreshing JWKS is required. With **opaque tokens**, introspection creates a more direct dependency on the AS. In every case, grant access only after tokens are verified and resource permissions are fully enforced.
