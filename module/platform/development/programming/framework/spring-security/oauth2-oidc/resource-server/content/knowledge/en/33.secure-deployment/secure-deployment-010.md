# Policy When Discovery, JWKS, or Introspection Is Unavailable

A Spring Security Resource Server depends on identity infrastructure to know how to verify access tokens. Depending on configuration, the application may need to read discovery metadata, fetch public keys from JWKS, or call a token introspection endpoint. When one of these services is unavailable, the Resource Server must decide which requests can still be processed safely, which requests must be rejected, and how to report the outage to clients.

These three dependencies play distinct roles:

- **Discovery** provides metadata about the issuer and related endpoints, such as `jwks_uri` or `introspection_endpoint`.
- **JWKS** provides public keys to verify JWT signatures.
- **Introspection** returns the status of an access token, typically including `active` and permitted attributes.

Operational policy must distinguish configuration errors, invalid tokens, and unavailable identity dependencies. When a token cannot be verified from a trusted source, protected endpoints must preserve the **fail-closed** principle. Caching can let the application continue authenticating for a controlled window, yet must never turn into accepting tokens indefinitely.

This lesson belongs to the **Secure Deployment** chapter and focuses on discovery/metadata failures, JWKS outages, introspection outages, caching and stale data, startup/readiness/runtime behavior, timeouts/retries/circuit breakers, Spring Security configuration, observability, runbooks, and fault-injection testing.

> **Illustrative context:** The Orders API runs Spring Boot 3.x / Spring Security 6.x. The API can verify JWTs with public keys from `https://id.example.com/oauth2/jwks`, or verify opaque tokens via `https://id.example.com/oauth2/introspect`. The Authorization Server publishes metadata at a discovery endpoint. URLs in this lesson are examples; real configurations must use verified issuers and endpoints.

## 1. Distinguishing Discovery, JWKS, and Introspection

### 1.1. Discovery Provides Issuer Configuration Information

OIDC Discovery and OAuth 2.0 Authorization Server Metadata allow clients or Resource Servers to locate an issuer's endpoints and capabilities. The metadata document may publish:

- `issuer`: the issuer identifier.
- `jwks_uri`: where to fetch the JSON Web Key Set.
- `introspection_endpoint`: where to introspect tokens if supported by the issuer.
- `authorization_endpoint` and `token_endpoint` for OAuth client flows.
- Supported signing algorithms and other metadata.

A Resource Server verifying only JWTs may only need `issuer` and `jwks_uri`. A Resource Server using opaque tokens needs the introspection endpoint and credentials to call it. OAuth clients may additionally need authorization/token endpoints.

Discovery is a metadata-retrieval step. It does not verify access token signatures and does not answer whether a specific token is still active.

### 1.2. JWKS Provides Public Keys

JWKS is a JSON document containing JWKs. For asymmetrically signed JWTs, the Resource Server picks the public key matching the protected header and verifies the signature. Afterward, the application must still validate issuer, audience, expiry, algorithm, and access-token conditions.

JWKS does not contain per-token revocation state. Being able to fetch a key does not mean a token has a valid signature, right audience, or valid lifetime.

### 1.3. Introspection Returns Token Status

Under RFC 7662, the Resource Server sends a token to the introspection endpoint. The Authorization Server may return:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 2000000600
}
~~~

The `active` field is the core signal. When `active` is `false`, the token must not be accepted. When the endpoint times out or returns errors, the Resource Server does not know whether the token is active; a dependency error is not equivalent to `active=false`.

### 1.4. Three Caches Serve Different Purposes

| Cache | Data | Cost Reduced | Risk When Data Is Stale |
|---|---|---|---|
| Discovery metadata cache | Issuer and endpoint metadata | Reduces metadata fetches | Old endpoints/key sources used after config changes |
| JWKS cache | Public JWK set or resolved keys | Reduces key fetches and parsing | Removed/compromised keys remain trusted until refresh |
| Introspection result cache | `active` outcome and principal attributes of a token | Reduces remote calls | Revoked tokens may remain accepted during TTL |

Do not use a single shared TTL across all three. Metadata, key material, and token status have different lifecycles and security impacts.

## 2. Defining Failure Policies Before Deployment

The policy must answer three questions for each dependency:

1. Can requests continue to be processed using trusted cached data?
2. If fresh data must be fetched while the dependency is unavailable, how will the request be rejected?
3. When the dependency recovers, how does the application refresh caches and return to normal state?

A baseline decision matrix:

| Incident | Can Cached Data Be Used? | Behavior for Protected Endpoints |
|---|---|---|
| Discovery unavailable, trusted metadata still in cache | Yes, within policy limits | Continue if endpoint/key source is known and other auth steps succeed |
| Discovery unavailable, required metadata missing | No | Cannot initialize trust configuration; report dependency/config failure |
| JWKS unavailable, matching public key still cached | Yes, per cache policy | Can verify JWT using cached key |
| JWKS unavailable, token carries unknown `kid` | No key to verify | Reject; never skip signature validation |
| Introspection unavailable, active result still cached | Yes, within approved TTL | Can use cached result if revocation policy permits |
| Introspection unavailable, cache miss | No | Token status unknown; fail closed |
| Introspection returns `active=false` | Not applicable | Reject token |
| Wrong introspection client credentials | Not applicable | Fail closed and treat as configuration/identity integration error |

This table describes policy at the architectural level. The final HTTP status also depends on exception types, filter chains, entry points, and API error contracts.

### 2.1. Fail Closed Does Not Mean Every Error Is 401

Fail closed means never granting access without trustworthy authentication evidence. It does not require reporting every dependency failure to clients with the exact same status code.

You can distinguish:

- Missing, invalid-signature, expired, or inactive tokens: authentication failure, typically `401 Unauthorized`.
- Valid authentication but missing scope/authority: authorization failure, typically `403 Forbidden`.
- Unavailable identity dependency preventing the server from determining token status: can be represented as `503 Service Unavailable` per API contract, or via the framework's default authentication failure mapping.
- Misconfigured server, such as wrong introspection client secret: operational/configuration failure requiring alerts and internal remediation.

Regardless of status code, requests must never proceed as authenticated without successful verification.

### 2.2. Never Automatically Fall Back to a Weaker Mechanism

When the JWT decoder fails to fetch JWKS, never automatically skip signature checks or treat the JWT payload as trusted. When introspection times out, never treat the token as active. Never route a protected request to an anonymous handler and permit the operation.

If the architecture supports multiple issuers or verification methods, selecting a method must rely on the application's trust configuration, never on whether the first method just encountered an error.

## 3. Discovery Outages

### 3.1. Discovery Failures Can Happen at Startup or Runtime

Common causes:

- DNS cannot resolve the issuer hostname.
- TLS certificate expired or untrusted chain.
- Metadata endpoint times out or returns HTTP 5xx.
- Metadata JSON is malformed or missing required fields.
- `issuer` value in metadata does not match the configured issuer.
- Proxies, firewalls, or network policies block the connection.
- Issuer recently changed endpoints while metadata cache has not refreshed.

Discovery may occur during decoder/client initialization or lazily when needed, depending on framework version and configuration. Do not assume all Spring Security applications perform discovery at the exact same moment.

### 3.2. Configure Static Endpoints When Appropriate

If the deployment already knows the issuer and JWKS URI, configure them explicitly to reduce reliance on metadata discovery in the startup path.

JWT Resource Server example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

When using `jwk-set-uri` directly, the application must still validate the `iss` claim. Never drop issuer validation just because the JWKS URI is statically configured. Exact behavior of combining `issuer-uri` and `jwk-set-uri` depends on Spring Boot/Spring Security version; verify against your project's pinned version.

For opaque tokens, configure the introspection URI directly instead of relying on metadata discovery:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

This is an endpoint configuration defined and governed by deployment. It does not exempt you from protecting TLS, client credentials, and trust relationships.

### 3.3. Never Use Discovery Fallback to Arbitrary Issuers

The issuer is a trust boundary. Never take an issuer from request parameters, unverified JWT claims prior to validation, tenant inputs, or caller-controlled hostnames and run discovery against that URL.

If supporting multi-tenancy/multi-issuer, maintain a governed allowlist registry or tenant-to-issuer mapping. Validate hostname, scheme, issuer identity, and JWKS URI per policy before creating a decoder. Prevent SSRF by never letting tokens or clients select metadata URLs arbitrarily.

### 3.4. Metadata Cache and Stale Usage Window

While the metadata cache remains valid, the application can keep using known issuer/JWKS/introspection endpoints during brief outages. However, stale metadata might point to replaced endpoints or outdated key sources.

Policy must specify:

- Maximum TTL for metadata.
- Whether stale metadata may be used when fetches fail.
- Maximum stale duration.
- How to detect when an issuer or endpoint has changed.
- Emergency metadata invalidation procedure.
- Behavior when metadata cache is empty at startup.

Never use stale metadata indefinitely. If an issuer is compromised or endpoint trust changes, stale caches can prolong trusting a revoked configuration.

### 3.5. Startup, Readiness, and Liveness

Do not let a transient discovery failure cause liveness probes to fail repeatedly and trigger a restart loop. Liveness answers whether the application is alive and able to make progress; readiness answers whether the instance is capable of serving traffic per policy.

One way to organize probes:

- **Liveness:** check that the process/application event loop is healthy.
- **Readiness:** check that the application has loaded required security configuration and can serve the incoming traffic class.
- **Dependency health:** report issuer metadata, JWKS, and introspection health separately.

If a new instance lacks the metadata/keys needed to verify tokens, readiness may need to stay false for protected traffic. If an instance already has trust configuration and valid cached keys, a brief outage might not require pulling the instance from the load balancer. Design probes around actual capabilities and application policy.

## 4. JWKS Outages

### 4.1. When the Public Key Is Still in Cache

If a JWT carries a `kid` already present in the JWK cache and the key remains permitted by policy, the Resource Server can verify the signature without calling the JWKS endpoint. In that case, a JWKS outage does not necessarily break all JWT requests.

This depends on the JWK source/cache implementation and cache state. A cache hit only supplies the key; signature, issuer, audience, expiry, `nbf`, algorithm, and other validators must still run.

### 4.2. When a Token Carries a New `kid`

If a token carries a `kid` not yet in cache, the JWK source typically needs to refresh or fetch JWKS to locate the key. When the endpoint is unavailable and no matching key is cached, the Resource Server cannot verify the signature.

Safe policy:

1. Perform a bounded refresh according to configured behavior.
2. If the fetch succeeds, locate the key and verify the signature.
3. If the fetch fails or the key still does not exist, reject the token.
4. Record the unknown-`kid` and JWKS dependency failure.
5. Never fall back to another key simply because the key ID was not found.

### 4.3. When JWKS Returns Invalid or Untrusted Data

Cases where a new key set must be rejected:

- TLS validation fails.
- Invalid JSON.
- JWK lacks required public parameters.
- Key type incompatible with the algorithm.
- Key usage/algorithm violates policy.
- Response contains no usable keys.
- Issuer/JWKS URI outside trust configuration.

Never update the cache with a failing or malformed response. Retain an existing valid cached key set only if cache policy permits; never turn malformed data into trust material.

### 4.4. Stale Keys Help Availability Yet Delay Key Revocation

Using cached public keys during an outage keeps serving tokens signed by those keys. Yet if a private signing key is compromised and its public key is removed from JWKS, instances retaining the old key may keep accepting tokens until caches refresh or expire.

Therefore, two distinct policies are needed:

- **Routine outage:** permit cached keys within an approved TTL/stale window.
- **Key compromise:** trigger emergency deny/invalidation to stop trusting the exposed key, even if caches still hold it.

Removing a key from JWKS at the origin does not guarantee immediate revocation across every Resource Server instance.

### 4.5. Do Not Extend Stale Keys Indefinitely

If JWKS is unavailable longer than the maximum stale duration, the application must reject tokens requiring keys unconfirmed under current policy. Never automatically extend cache TTL on every failed fetch. Retaining stale caches must be a bounded, observable choice.

## 5. Introspection Outages

### 5.1. Introspection Cache Hit

If the Resource Server holds an introspection result `active=true` still within TTL, it can use that result per policy. TTL must be capped by:

- Remaining time until token expiry.
- Acceptable revocation staleness window.
- Security policy's maximum TTL.
- Validity duration of related metadata/issuer policies.

For example, if an API requires token revocations to take effect within at most 10 seconds, a 60-second active cache does not meet the requirement. Once a cache entry expires, the Resource Server must introspect again before continuing to accept the token.

### 5.2. Introspection Cache Miss

On a cache miss when the AS is unreachable, the Resource Server has no proof the token is active. Never infer `active` from prior acceptance, never accept based on the token string alone, and never return default authorities.

Protected requests must fail closed. The API may return `503` per dependency error contract if the server determines the introspection service is unavailable; if the framework maps the error to an authentication failure, the response may be `401`. Write integration tests for the actual status returned.

### 5.3. Introspection Returns `active=false`

This is a valid verification result from the AS indicating the token is inactive. Reject the token and never cache it as active. Short-lived negative caching may be used to reduce repeated lookups, yet inactive responses must be cleanly distinguished from timeouts/5xx errors.

### 5.4. Broken Introspection Credentials or Client

Errors such as wrong client ID, expired client secret, disabled client, or AS returning 401/403 are usually integration/configuration failures. Do not retry infinitely and do not treat them as an inactive end-user token.

Appropriate actions:

- Fail closed.
- Alert operations immediately.
- Inspect secret rotation and client registration.
- Check the resource server client's permissions on the introspection endpoint.
- Avoid logging secrets or request bodies containing tokens.

### 5.5. Malformed Introspection Response

If the response is not valid JSON, misses `active`, has wrong data types, or violates the protocol contract, do not create an authenticated principal. Never interpret a response missing fields as `active=true`.

If the AS returns insufficient metadata to construct the principal/authorities per application contract, reject or report an integration error per defined policy.

## 6. Timeouts, Retries, and Circuit Breakers

### 6.1. Every Remote Call Needs a Finite Deadline

Discovery, JWKS fetches, and introspection are all network dependencies. Define connect timeouts, TLS handshake timeouts if supported separately by the HTTP client, response/read timeouts, connection pool acquisition timeouts, an overall deadline fitting the request budget, and response size limits.

Never leave request threads waiting indefinitely on a hung identity endpoint.

### 6.2. Retry Only Appropriate Transient Errors

Retries may be considered for network resets, brief timeouts, or certain HTTP 5xx responses. Never retry indefinitely and never retry every response.

| Error | Handling |
|---|---|
| DNS timeout or connection reset | Bounded retry if within request deadline |
| HTTP 502/503/504 | Budgeted retry with backoff if policy allows |
| HTTP 400 from metadata/introspection | Inspect request/configuration; do not blindly retry |
| HTTP 401/403 from introspection client | Fix credentials/registration; do not keep retrying |
| Invalid JWT signature | Reject token; never retry JWKS hoping an invalid token becomes valid |
| Unknown `kid` | Bounded refresh per JWK source policy |
| HTTP 429 | Honor `Retry-After` if within deadline and client behavior |

Retries can double traffic during an outage. Use exponential backoff with jitter, cap total attempts, and stay within the request deadline.

### 6.3. Circuit Breakers Protect Dependencies

A circuit breaker can stop calling a consistently failing endpoint, reducing queues and protecting connection pools. When the circuit is open:

- Discovery cannot provide fresh metadata.
- JWKS cannot provide new keys.
- Introspection cannot provide fresh status for cache misses.

A circuit breaker never manufactures authentication evidence. Still-valid cache entries may continue to be used per policy; cache misses must fail closed. Never configure a fallback returning `active=true`, default authorities, or skipping signature validation.

### 6.4. Bulkheads and Connection Pools

Isolate resource limits for identity HTTP calls from other outbound calls when needed. Concurrency limits keep an introspection outage from exhausting the API's request threads or connection pools. Size pools adequately for valid traffic with a hard cap; monitor pool saturation and pending acquisitions.

### 6.5. Do Not Stack Retries Across Multiple Layers Without a Total Budget

If the HTTP client retries 3 times, the service wrapper retries 3 times, and the gateway retries on top, one request can trigger many more calls than intended. Pick one layer to own the retry policy or calculate a total retry budget end to end.

## 7. Configuring Spring Security Resource Server

### 7.1. JWT with Issuer and JWKS URI

Spring Boot configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

Security filter chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/health/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

`issuer-uri` preserves the issuer as part of the trust policy. `jwk-set-uri` directly specifies the key endpoint. Check your Spring Boot/Spring Security version for exact startup discovery and decoder initialization behavior.

### 7.2. Creating a Decoder with an Issuer Validator

When direct control over the decoder is needed:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://id.example.com";
    String jwkSetUri = "https://id.example.com/oauth2/jwks";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

This example retains default timestamp validators alongside issuer validation. If the API needs an audience validator, compose the additional validator instead of inadvertently overwriting the entire policy.

Never write a custom decoder that skips signatures or parses payloads manually to build a `JwtAuthenticationToken`.

### 7.3. Opaque Token Introspection

Spring Boot configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Security filter chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

Client credentials are used by the Resource Server to call the introspection endpoint. They are not the end user's Bearer token. Secrets must be supplied via a secret manager or environment injection.

### 7.4. Intentional Use of Static Endpoints vs. Discovery

To reduce dependency on discovery in the startup path, configure the JWKS URI or introspection URI directly. In return, endpoints and issuer metadata become deployment configuration that must be updated, governed, and audited.

Do not scatter hard-coded production endpoints across multiple classes. Use configuration properties, validate values at startup, and manage changes through the deployment process.

### 7.5. Timeouts and HTTP Clients

Nimbus decoders/JWK sources and introspection clients expose different HTTP transport configuration hooks depending on the Spring Security/Nimbus version. Configure connect/read timeouts, TLS trust, and connection pooling using the APIs supported by your project's version. Never assume one timeout property applies to every HTTP client used by the framework.

If supplying a custom HTTP client, verify it is actually wired into the decoder/introspector in the filter chain. An HTTP client bean not wired into the identity component will not change runtime timeouts.

## 8. Startup and Deployment Strategy

### 8.1. Distinguishing Valid Configuration from Temporary Dependency Unavailability

Startup should validate local configuration:

- Issuer URI is valid and uses HTTPS per policy.
- JWKS/introspection endpoints have expected hostnames.
- Client ID is non-empty.
- Secret is provisioned.
- Algorithm allowlist and audience policy are declared.
- Timeout/retry/cache policies are bounded.

A temporarily unavailable dependency does not necessarily require a restart loop if the application already has valid trust configuration and can use cached data. Conversely, misconfiguration or lacking any trustworthy key/metadata source must never be treated as a safe degraded state.

### 8.2. Controlled Cache Warm-Up

For JWTs, you can proactively verify the JWKS endpoint or load the key set during deployment warm-up to catch errors before receiving traffic. Never use fake tokens to conclude the decoder is ready if tests bypass real signature verification.

For introspection, you cannot warm an arbitrary token to substitute for live caching. You can health-check the endpoint using an AS-supported mechanism, yet health checks must use real client authentication and never fabricate token state.

### 8.3. Readiness Must Reflect Serving Capability

A new instance lacking public keys and unable to reach JWKS may not yet be ready for protected JWT traffic. An instance already holding valid cached keys may continue serving per stale policy. Readiness must reflect actual state and policy, not merely ping an endpoint.

Avoid tying identity dependency checks to liveness if failures cause continuous pod restarts and amplify an outage.

### 8.4. Rollout and Rollback

Before deployment:

- Verify discovery metadata/JWKS/introspection endpoints from the production network zone.
- Verify TLS chains and credentials.
- Verify key rotation overlap.
- Configure timeouts/retries/circuit breakers.
- Confirm cache policy and revocation SLA.
- Prepare rollback for issuer/endpoint configuration if a change goes wrong.

Rolling back endpoints never means rolling back to an untrusted issuer or compromised key. Only revert to verified, still-valid trust configuration.

## 9. Distinguishing Identity Errors from Authorization Errors

A Resource Server must keep layers distinct:

1. **Authentication:** was the token verified and was a principal created?
2. **Authorization:** does the principal hold the required authority/scope?
3. **Dependency availability:** are metadata/key/introspection sources reachable?

| Scenario | Outcome |
|---|---|
| Invalid JWT signature | Authentication failure |
| Expired JWT | Authentication failure |
| Introspection `active=false` | Authentication failure |
| Valid token missing `SCOPE_orders.write` | Authorization failure |
| JWKS timeout with no cached key | Dependency/authentication failure |
| Introspection timeout and cache miss | Dependency/authentication failure |
| Malformed discovery metadata | Identity configuration/dependency failure |

Never return `403 insufficient_scope` when the token has not been verified. Never report `invalid_token` as if the token is definitely bad when the real cause is an unavailable introspection service, if the API is able to distinguish the two errors.

### 9.1. Statuses and Bearer Challenges

Per Bearer token semantics:

- `401` is typically used for missing or invalid tokens.
- `403` with `insufficient_scope` is used when authentication succeeds but scopes are insufficient.
- `503` may be used for identity dependency outages if the API gateway/error contract supports distinguishing them.

Spring Security has default entry points and access-denied handling. If a different status is needed for a dependency exception, customize error mapping carefully and test it through the filter chain. Never return stack traces, internal endpoints, AS response bodies, or tokens in error responses.

## 10. Observability for Identity Dependencies

### 10.1. Discovery Metrics

Track metadata fetch success/failure, metadata fetch latency, metadata cache hit/miss/age, issuer mismatches, metadata parse/validation errors, and timestamp of last successful refresh.

### 10.2. JWKS Metrics

Track JWKS fetch success/failure and latency, JWKS cache hit/miss/age, unknown `kid` counts, signature verification failures, key set size, last successful JWKS refresh, and TLS/DNS/HTTP error categories.

### 10.3. Introspection Metrics

Track introspection QPS and p50/p95/p99 latency, active/inactive outcomes, HTTP/network failures, cache hit/miss/eviction/expiry, in-flight requests, connection pool saturation, timeout/retry/circuit breaker states, and last successful introspection response.

### 10.4. Do Not Log Credentials or Create High-Cardinality Labels

Never log `Authorization` headers, raw JWTs, opaque tokens, introspection request bodies, client secrets, or full claims. Never use token hashes, `sub`, `jti`, session IDs, or caller-supplied `kid`s as metric labels.

You can log request correlation IDs, dependency names (`discovery`, `jwks`, `introspection`), error categories, normalized HTTP statuses, cache hit/miss, configured issuer aliases, and circuit breaker states.

If a specific token must be investigated, use a protected audit mechanism and controlled identifiers; never put credentials into regular logs.

### 10.5. Impact-Based Alerts

Useful alerts include sustained discovery/JWKS/introspection failures, spikes in unknown `kid`, spikes in signature failures after rotation, introspection p99 latency exceeding budget, cache stale age exceeding threshold, connection pool saturation, rejected client credentials, and circuit breakers open too long.

Do not alert on a single error during a planned rollout; combine error rate, duration, affected instances, and request impact.

## 11. Incident Response Runbooks

### 11.1. Discovery Endpoint Unreachable

1. Confirm configured hostname/issuer URI.
2. Check DNS, routing, proxies, and firewalls.
3. Check TLS certificate chain, hostname, and expiry.
4. Check HTTP status and metadata response body.
5. Verify the issuer in the document matches configuration.
6. Determine whether the metadata cache is still valid or past its stale window.
7. If using static endpoints, confirm JWKS/introspection URIs remain accurate and trusted.
8. Restore the endpoint or deploy verified metadata/configuration.

Never fall back to a different issuer merely because the current issuer is unavailable.

### 11.2. JWKS Fetch Failures

1. Identify the token's `kid` and algorithm; use the header strictly for diagnostics.
2. Confirm the key ID exists in the JWKS origin.
3. Check JWK source cache age and last refresh.
4. Check DNS/TLS/HTTP status from the Resource Server.
5. Check key type, `use`, `alg`, and public parameters.
6. If the key is cached, apply stale policy.
7. If the key is absent and cannot be fetched, reject the token.
8. Check whether a rotation skipped publish-before-sign.

Never disable signature validation to restore traffic.

### 11.3. Introspection Endpoint Failures

1. Confirm the introspection URI.
2. Check client ID/secret and secret expiration.
3. Check the Resource Server client's permissions on the endpoint.
4. Check TLS, DNS, proxy, connection pool, and timeouts.
5. Inspect cache hits/misses and age of active results.
6. If an active result is within TTL, use it only per policy.
7. On cache miss, fail closed and return a dependency error per contract.
8. Monitor QPS/latency once the AS recovers.

Never interpret a timeout as `active=true`.

### 11.4. After Dependency Recovery

- Confirm metadata/JWKS responses are valid.
- Let JWK sources/caches refresh per policy.
- Confirm new keys or new endpoints have been picked up.
- Verify introspection responses with a managed valid test token.
- Monitor cache hit/miss and failure rates.
- Confirm circuit breakers close per recovery policy.
- Verify no retry storm occurs after recovery.

## 12. Testing Failure Behavior

### 12.1. Discovery Tests

Use a mock HTTP server or WireMock to simulate successful metadata fetches, timeouts, HTTP 404/500/503, TLS/DNS failures if supported by the test harness, malformed metadata JSON, missing `jwks_uri` or required introspection endpoints, issuer mismatches, and endpoints changing after refresh.

Verify startup/readiness behavior matches policy and the application never trusts arbitrary issuers.

### 12.2. JWKS Tests

Create test key pairs and a controllable JWKS endpoint:

- Key in cache, endpoint goes down.
- Cache miss, endpoint unavailable.
- Unknown `kid`, refresh succeeds.
- Unknown `kid`, refresh fails.
- New key published before new tokens are signed with it.
- Old key retained during overlap.
- Old key removed after token lifetime.
- Invalid signature even though `kid` exists.
- Malformed JWKS or incompatible key type.

Use a real decoder to test signature verification. Mocking `JwtDecoder` does not prove JWK fetching, parsing, or signature checks work.

### 12.3. Introspection Tests

Use a mock introspection endpoint:

- `active=true` with valid metadata.
- `active=false`.
- HTTP 401/403 from client authentication.
- HTTP 429/5xx.
- Timeouts and connection resets.
- Malformed response or missing `active`.
- Cache hit during AS outage.
- Cache miss during AS outage.
- Cache expiry after revocation.
- Concurrent misses and concurrency limits.

Confirm dependency failures never turn into authenticated principals and are never mis-cached as inactive responses.

### 12.4. Testing Status Mapping Through the Filter Chain

Use `MockMvc` and the real security filter chain to confirm invalid tokens return contractual statuses, missing scopes return 403, JWKS/introspection dependency outages return designed statuses, no controller/service side effects occur when authentication fails, and error responses contain no tokens/secrets/internal details.

### 12.5. Do Not Use Long Sleeps or Internet-Dependent Tests

Use mock servers, controllable clocks, and test cache providers to control TTLs/failures. Tests must never call a production Authorization Server or rely on public Internet access. This makes outages reproducible and lets you test exact cache expiration boundaries.

## 13. Example Policy Matrix by Dependency

An operational configuration can define the following bounds (values are illustrative only; choose per your system's SLA/security policy):

| Component | Normal | Brief Outage | Extended Outage |
|---|---|---|---|
| Discovery metadata | Fetch/refresh per cache | Use trusted metadata within TTL | Never use stale metadata indefinitely; keep instance degraded/not ready if endpoint cannot be determined |
| JWKS | Cache key set and refresh as needed | Use cached keys per stale policy | Reject tokens needing unavailable keys or keys past stale limit |
| Introspection | Call endpoint and briefly cache active results | Use active results within TTL if policy allows | Reject cache misses; alert and report dependency outage |
| Client credentials | Managed and rotated secrets | Continue while credential remains valid | Fail closed, restore secret/registration |
| HTTP client | Bounded pool/timeouts | Budgeted transient retries | Circuit breaker/bulkhead, no unbounded queues |

TTLs and stale windows must be documented as explicit policy, not left for each instance or module to decide independently.

## 14. Common Mistakes

1. **Lumping discovery, JWKS, and introspection into one dependency:** they supply different data and require different cache policies.
2. **Assuming a discovery outage always breaks every JWT request:** static endpoints and metadata caches can allow continuity within policy bounds.
3. **Assuming a JWKS outage breaks every JWT request immediately:** matching keys may still be cached.
4. **Accepting tokens with a new `kid` when public keys cannot be fetched:** signatures cannot be verified.
5. **Using stale keys indefinitely:** compromised keys could stay trusted.
6. **Treating JWKS removal as instant revocation:** instances with caches may keep using the old key.
7. **Treating an introspection timeout as `active=false`:** timeouts do not reveal token state.
8. **Treating an introspection timeout as `active=true`:** that is failing open.
9. **Caching dependency exceptions:** network errors can outlive the actual outage.
10. **Unbounded retries:** amplifies incidents and triggers retry storms.
11. **Circuit breakers with allow fallbacks:** breakers cannot fabricate authentication evidence.
12. **Tying dependency outages to liveness:** restart loops can widen the outage.
13. **Taking issuer or JWKS URLs from untrusted input:** creates SSRF/trust confusion.
14. **Not testing status mapping:** clients may receive non-contractual 401/403/500 responses.
15. **Logging raw tokens or introspection bodies:** leaks credentials.
16. **Checking only the AS health endpoint:** a live endpoint does not prove the Resource Server can fetch metadata/keys or introspect with real credentials.

## 15. Secure Deployment Checklist

- [ ] Distinguish discovery metadata, JWKS key material, and introspection state.
- [ ] Use only issuers and endpoints from verified configurations/trust registries.
- [ ] Never let callers control discovery URLs, `jku`, or `x5u`.
- [ ] Set separate TTLs for metadata, JWKS, and introspection results.
- [ ] Define stale windows and emergency invalidation.
- [ ] Enforce signature, issuer, audience, expiry, and algorithm validation.
- [ ] Unknown `kid`s perform bounded refreshes and fail closed if still missing.
- [ ] Introspection cache misses during AS outages fail closed.
- [ ] Never cache timeouts/5xx as inactive or active tokens.
- [ ] Configure connect/read timeouts and request deadlines.
- [ ] Bound retries, concurrency, and connection pools.
- [ ] Use circuit breakers to protect dependencies, never as allow fallbacks.
- [ ] Separate liveness, readiness, and dependency health.
- [ ] Separate authentication failures, authorization failures, and dependency outages.
- [ ] Collect metrics for caches, latency, failures, unknown `kid`s, and circuit states.
- [ ] Never log tokens, secrets, or introspection request bodies.
- [ ] Write fault-injection tests for discovery, JWKS, and introspection.
- [ ] Maintain runbooks for recovery and key/credential compromise.

## 16. References

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): metadata discovery and issuer configuration.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): Authorization Server metadata.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK and JWKS format.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and claims.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response and `active`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token error semantics.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/key validation and JWT security practices.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer, JWKS, and validators.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): opaque token introspection.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Servlet Resource Server configuration.

**Conclusion:** When discovery, JWKS, or introspection fails, a Resource Server may continue authenticating only with still-valid trusted data under an approved cache policy. JWTs can continue to be verified using cached public keys; tokens carrying an unknown `kid` must be rejected if keys cannot be retrieved. Introspection may use only active results still within TTL; cache misses when the endpoint is unavailable must fail closed. Timeouts, retries, circuit breakers, readiness, status mapping, and observability must be designed together to protect both security boundaries and API availability.
