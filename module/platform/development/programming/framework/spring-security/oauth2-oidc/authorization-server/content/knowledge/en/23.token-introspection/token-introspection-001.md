# Purpose of OAuth2 Token Introspection

## 1. Context: The Resource Server Needs to Know Whether a Token Is Still Valid

In an OAuth 2.0/OpenID Connect system using **Spring Security**, **Spring Authorization Server**, and Spring Boot, the Authorization Server (AS) issues access tokens to an OAuth client. The client sends the token to a Resource Server (RS) to access APIs.

The RS must decide whether the request is authenticated. With a JWT access token, the RS can usually verify the signature, issuer, audience, and expiration locally. However, with an opaque access token, the RS cannot read claims directly from the token. Even a self-contained JWT may need to be checked for revocation status or the latest authorization state.

**OAuth 2.0 Token Introspection** is standardized in **RFC 7662**. It is a protocol for a protected resource to query the Authorization Server about the state of a token. The AS returns a JSON document containing a required `active` field and optionally the metadata needed for the RS to perform authorization.

For example, an e-commerce system has:

- `checkout-service`: Resource Server receiving checkout requests.
- `order-web`: OAuth client obtaining access tokens for users.
- `auth.example.com`: Authorization Server issuing and managing tokens.

When `checkout-service` receives an access token, it calls the AS's Introspection Endpoint to ask whether the token is still active and intended for this service. The AS checks the token state and returns the result. The RS proceeds only when the token is active, has the correct audience, and has sufficient scopes according to policy.

**Introspection is not a grant type for a client to request a new token.** It is an endpoint for checking token state by a protected resource authorized by the AS.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the purpose and role of Token Introspection according to RFC 7662.
2. Distinguish introspection from local token validation, token revocation, and token refresh.
3. Understand the meaning of the `active` field and common metadata included in the response.
4. Identify the role of `token` and `token_type_hint` in the request.
5. Explain why a protected resource must be authenticated and authorized to call introspection.
6. Compare introspection for opaque tokens and JWT access tokens.
7. Configure Spring Authorization Server and Spring Security Resource Server for introspection.
8. Design caching, timeouts, rate limiting, privacy, and error handling.
9. Test active/inactive tokens, audience, scope, revocation, and AS outage scenarios.

## 2. What Problem Does Token Introspection Solve?

An access token is a credential representing access rights. The RS needs to verify at least:

- Was the token issued by a trusted AS?
- Is the token still within its validity period?
- Has the token been revoked or invalidated?
- Was the token issued for the RS receiving the request?
- Does the token have the appropriate scope/authority for the endpoint?
- Is the token bound to a client, subject, tenant, or proof-of-possession?

With an **opaque token**, the RS usually cannot verify this information merely by parsing the token. The token may just be a random string, while the authorization data is stored at the AS.

Introspection allows the RS to send the token to the AS via a protected endpoint. The AS looks up the state and returns information according to policy.

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as checkout-service / Resource Server
    participant AS as Authorization Server
    participant DB as Authorization Store

    C->>RS: API request + access token
    RS->>RS: Identify token to introspect
    RS->>AS: POST /oauth2/introspect<br/>RS authentication + token
    AS->>AS: Authenticate protected resource
    AS->>DB: Look up token and authorization state
    DB-->>AS: Token metadata / state
    AS->>AS: Apply active and resource policy
    AS-->>RS: active + permitted metadata
    RS->>RS: Check audience, scope, subject
    RS-->>C: Allow or reject API request
```

Introspection creates an online check step between the RS and the AS. As a result, the AS can apply the latest authorization state according to the system's storage capabilities and policies.

### 2.1. Token Introspection Is Not Token Issuance

| Operation | Who calls it? | Purpose |
|---|---|---|
| Token issuance | OAuth client | Request the AS to issue a token |
| Token introspection | Protected resource / RS | Ask the AS whether a token is active and retrieve its metadata |
| Token revocation | Authorized OAuth client | Request the AS to revoke a token |
| Refresh | OAuth client | Exchange a refresh token for a new access token |
| UserInfo | OIDC client | Retrieve End-User claims using an access token |

An introspection request does not renew a token, does not extend `exp`, and does not revoke a token itself. It only queries the state at the moment the AS processes the request.

## 3. RFC 7662: Introspection Endpoint

RFC 7662 defines the endpoint that the Authorization Server publishes for protected resources to inspect tokens. The exact URI depends on configuration/metadata; in examples, Spring Authorization Server commonly uses:

```text
POST /oauth2/introspect
```

The endpoint must be protected. The AS needs to authenticate the protected resource calling the endpoint and decide whether that resource is permitted to introspect. Never leave the endpoint public to everyone, as it could become a tool for token scanning or metadata harvesting.

### 3.1. Who Is Allowed to Call Introspection?

Typically, the RS has a dedicated OAuth client registration to authenticate with the AS. This credential represents **the introspection requester service**, not the token being inspected.

For example:

| Credential/Component | Meaning |
|---|---|
| `checkout-service-introspector` | Client identity of the RS when calling introspection |
| Client secret/private key/mTLS credential | Authenticates the RS with the AS |
| `token` in form body | End-user or workload access token being inspected |
| `client_id` in response | OAuth client that requested the introspected token, if provided by the AS |

Do not use the access token being inspected as the client secret for the introspection endpoint. Also do not confuse the RS's `client_id` with the `client_id` in the token's metadata.

### 3.2. The Introspection Endpoint Must Use TLS

Tokens and authorization metadata are sensitive data. The RS must call the introspection endpoint over HTTPS/TLS and verify the AS certificate according to the trust policy. Do not send tokens over unencrypted HTTP or to arbitrary endpoints.

In a multi-service environment, use trusted service discovery/configuration, restrict outbound networking, and authenticate clients. Avoid letting external callers choose the introspection URL themselves.

## 4. Introspection Request

According to RFC 7662 Section 2.1, the request uses HTTP POST with content type `application/x-www-form-urlencoded`. The `token` parameter is required; `token_type_hint` is optional.

Example:

```http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_RS_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=ACCESS_TOKEN_TO_CHECK
&token_type_hint=access_token
```

The token value in the example is only a placeholder. Do not put real tokens into URL query strings, logs, traces, or tickets.

### 4.1. The `token` Parameter

`token` is the token to be inspected. It can be an access token or another token type supported for introspection by the AS. In a Resource Server architecture, the common case is an access token.

The AS needs to look up the token in the authorization store or corresponding token management mechanism. Do not merely decode a JWT and return `active=true`, because the token may have been revoked, expired, not yet valid, or not issued for the querying resource.

### 4.2. The `token_type_hint` Parameter

`token_type_hint` is a hint about the type of token the client is sending. Possible values include:

- `access_token`
- `refresh_token`

This is only a **hint**, not proof of the token type. The AS can use it to choose where to look first. If the token is not found according to the hint, RFC 7662 requires the AS to continue trying other supported token types according to protocol rules.

Do not trust `token_type_hint` to bypass token type checks or return inappropriate metadata. If the endpoint only allows introspecting access tokens, the policy must explicitly enforce that restriction.

### 4.3. Requester Authentication Is Independent of the Introspected Token

The Basic header in the example contains the credential of `checkout-service-introspector`. The AS must:

1. Authenticate the client/resource server calling introspection.
2. Check whether the requester is authorized to call the endpoint.
3. Validate the input token.
4. Return only the metadata that the requester is permitted to know.

An attacker who knows a user's token but lacks the RS's credential must not be allowed to call introspection to probe status or read claims.

## 5. Introspection Response and the active Field

A successful response is typically JSON:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "scope": "orders.read payments.status.read",
  "client_id": "order-web",
  "token_type": "Bearer",
  "exp": 1794825600,
  "iat": 1794825300,
  "sub": "user-42",
  "aud": [
    "https://checkout-api.example.com"
  ],
  "iss": "https://auth.example.com",
  "jti": "token-id-123"
}
```

This is an illustrative response. The AS may add or omit optional metadata depending on token type and policy. The `active` field is required.

### 5.1. Meaning of `active`

`active` must be a JSON boolean:

- `true`: the token is considered active by the AS at the time of introspection under the applied policy.
- `false`: the token is not active, or the AS cannot confirm the token is valid for this protected resource.

According to RFC 7662, an active token must generally have been issued by the AS, not expired, not revoked, and valid for the protected resource performing the introspection. The AS may apply additional policy conditions.

**`active=true` does not mean the API request is automatically permitted.** The RS still needs to check audience, scope, tenant, subject, sender constraint, and business authorization.

### 5.2. Why Should an Inactive Response Avoid Disclosing Details?

For an inactive token, the AS should return the minimum:

```json
{
  "active": false
}
```

It should not disclose whether the token has an invalid signature, has expired, was revoked, does not exist, or belongs to another client, because such differences can help attackers probe credentials or gather internal information.

The AS can record detailed reasons in access-controlled internal audit logs, but the public response should avoid revealing specific causes.

### 5.3. HTTP 200 and active false Have Two Different Meanings

An inactive token is normally still returned in a successful introspection response with `active=false`. This is not a server error.

| Situation | Meaning |
|---|---|
| HTTP 200, `active=true` | AS confirms the token is active |
| HTTP 200, `active=false` | Valid introspection request, token is not active |
| HTTP 400, `invalid_request` | Request has missing/invalid parameters |
| HTTP 401, `invalid_client` or equivalent mechanism | Requester failed authentication |
| HTTP 5xx/timeout | AS or infrastructure failure; RS cannot confirm status |

Do not turn a timeout into `active=true`. If the RS cannot verify the state according to policy, handle it as a dependency failure and apply the defined availability policy.

## 6. Common Metadata in the Response

RFC 7662 defines several metadata fields that may appear when a token is active:

| Field | Meaning |
|---|---|
| `scope` | Granted scopes, typically a space-delimited string |
| `client_id` | OAuth client that requested the token |
| `username` | Username as defined by the AS, if available |
| `token_type` | Token type according to the OAuth token type registry |
| `exp` | Expiration time (NumericDate) |
| `iat` | Issued-at time |
| `nbf` | Time before which the token is not valid |
| `sub` | Subject of the token |
| `aud` | Audience/resource receiving the token |
| `iss` | Issuer that issued the token |
| `jti` | Token identifier |
| `cnf` | Confirmation claim for sender-constrained tokens or other bindings |

Not all of these metadata fields are necessarily present in every response. The AS must protect privacy and disclose only the information needed by the authenticated protected resource.

### 6.1. `scope`

`scope` describes the granted permissions, usually as a space-delimited string:

```text
orders.read payments.status.read
```

The RS can map scopes to authorities and enforce them per endpoint. Do not infer administrative privileges from an arbitrary scope string without an explicit policy mapping.

### 6.2. `aud`

`aud` helps the RS determine whether the token is intended for itself. If the AS returns an audience, the RS must check that its own identifier is present in the audience according to the contract.

Do not accept a token just because `active=true` when the token was actually issued for a different API. Active is the token's status in the introspection context; audience remains part of the authorization contract.

### 6.3. `sub` and `client_id`

`sub` represents the subject the token refers to; `client_id` indicates the OAuth client that requested the token. With Authorization Code, the subject may be a user; with Client Credentials, the subject may represent a workload according to AS semantics.

Do not confuse the client calling introspection with the client that requested the access token. These two identities are usually different.

### 6.4. `cnf`

For sender-constrained tokens, the `cnf` metadata can carry binding information. For example, a DPoP-bound token has `cnf.jkt`. The RS must still verify the corresponding proof-of-possession; the introspection response returning `cnf` does not itself prove the current request holds the private key.

## 7. Token Introspection vs. JWT Local Validation

There are two common token verification strategies:

1. **Local validation:** The RS verifies the JWT signature, issuer, audience, expiry, and claims itself.
2. **Remote introspection:** The RS asks the AS about the token's state via a protected endpoint.

| Criterion | JWT local validation | Remote introspection |
|---|---|---|
| Network call per request | Not required | Yes, unless cached |
| Opaque token support | Cannot read locally | Yes |
| Latest revocation status check | Requires additional mechanisms | Can reflect latest AS state |
| Latency | Typically low | Depends on network/AS |
| Availability dependency | Depends on JWKS/cache | Depends on introspection endpoint |
| Authorization data | Claims inside the token | Metadata returned by the AS |
| Centralized control | Hard to update issued tokens | AS can apply current state |
| Privacy | Claims may reside in the JWT held by the client | AS can disclose metadata only to authorized RSs |

### 7.1. Opaque Tokens Are the Typical Use Case

Opaque tokens do not contain locally readable claims. The RS cannot verify a JWT signature or read `exp` on its own. Introspection allows the AS to look up the token and return `active` along with metadata.

This is useful when you want to:

- Hide token structure.
- Keep authorization state at the AS.
- Revoke tokens and reflect the new state faster.
- Return metadata tailored to the protected resource's permissions.
- Support multiple token types in one system.

### 7.2. JWTs Can Also Be Introspected

JWTs can be validated locally, but introspection is still useful if the system needs to check current authorization state, revocation, or dynamic policies. The fact that a token can be decoded does not mean the RS should decide status locally without considering product requirements.

A system can use JWT local validation for most requests and introspection for certain sensitive resources. Avoid having two validation paths with different policies that cause inconsistent results.

### 7.3. Introspection Does Not Provide Immediate Revocation Without Shared State

If the AS stores token state in per-instance memory or an inconsistent authorization store, one node may report active while another node has already revoked the token. For introspection to reflect accurate state, issuance, revocation, and introspection must use the same trusted state source or a well-defined synchronization mechanism.

## 8. Distinguishing Introspection from Revocation and Refresh

| Mechanism | Standard | Who initiates it? | Result |
|---|---|---|---|
| Token Introspection | RFC 7662 | Protected resource | Returns token status and metadata |
| Token Revocation | RFC 7009 | Authorized OAuth client | Requests the AS to invalidate a token |
| Refresh Token Grant | RFC 6749 | OAuth client | Exchanges a refresh token for a new access token |
| JWT validation | RFC 7519/JWS and related profiles | Resource Server | Verifies the token locally |

For example: a user logs out and the client calls the revocation endpoint to revoke the refresh token. Afterward, `checkout-service` introspects the access token. If the AS has updated the state and the token is managed in a way that supports revocation, the response can return `active=false`.

**Introspection is not a revocation operation.** It only tells the RS how the AS views the token at the time of the query.

## 9. Spring Authorization Server: Configuring the Introspection Endpoint

Spring Authorization Server provides the Token Introspection Endpoint among its protocol endpoints. The endpoint is typically protected by client authentication and uses `OAuth2AuthorizationService` to look up authorization/token state.

In modern configurations, you can use the configurer:

```java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.tokenIntrospectionEndpoint(Customizer.withDefaults()));

        return http.build();
    }
}
```

This example focuses on the endpoint configurer, not the entire Authorization Server. The application also needs a registered client repository, authorization service, token generator, JWK source, issuer, and the necessary filter chains/login flows.

In many configurations, the introspection endpoint is already enabled by default by the Authorization Server configurer; calling `tokenIntrospectionEndpoint` is a way to make the customization point explicit. Check the API for your exact dependency version before using it, as packages and signatures can change across release lines.

### 9.1. The Authorization Store Must Persist Token State

Introspection needs to find the token and evaluate its state. Therefore, the AS must have an `OAuth2AuthorizationService` used consistently when issuing, refreshing, revoking, and introspecting tokens.

Common options:

- `InMemoryOAuth2AuthorizationService`: convenient for demos/tests, loses state on process restart, and is unsuitable for multi-instance production.
- `JdbcOAuth2AuthorizationService`: stores authorization/token state in a database; requires appropriate schema, indexes, transactions, and migrations.
- Custom authorization service: can use another database/cache, but must guarantee consistency, lookup, and revocation semantics.

Do not issue a token through one service and introspect it in another service that does not share state while expecting accurate results every time.

### 9.2. Registered Client Calling Introspection

The Resource Server needs a dedicated client registration to authenticate with the AS. Example of a confidential service:

```java
RegisteredClient introspectionClient = RegisteredClient
    .withId("checkout-introspector-internal-id")
    .clientId("checkout-service-introspector")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
    .scope("introspection.call")
    .build();
```

This code illustrates a client identity. The `introspection.call` scope is only a hypothetical business name; the introspection endpoint typically relies on the authenticated client and AS policy, and does not automatically check this scope unless the application implements that check. Do not add grants or scopes that are not used by the framework or policy.

The secret must come from a secret manager. In production environments, you can choose `private_key_jwt` or mTLS depending on your threat model and version capabilities.

### 9.3. Requester Authentication and Endpoint Authorization

The AS must ensure that the client calling introspection is an authorized protected resource. Simply registering an OAuth client does not automatically mean it should be allowed to introspect every token.

A policy can restrict:

- Which clients may call introspection.
- Which token types may be inspected.
- Which tenant/resource scopes are visible.
- Which metadata fields are returned.
- Request rate.
- Accepted network or workload identities.

Do not expose sensitive token metadata to clients unrelated to that resource.

## 10. Resource Server Calling the Introspection Endpoint

Spring Security Resource Server supports opaque token introspection. Configuration via Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: checkout-service-introspector
          client-secret: SECRET_FROM_SECURE_CONFIGURATION
```

`SECRET_FROM_SECURE_CONFIGURATION` is a placeholder. Do not commit real secrets into YAML or Git. Use environment variables/secret managers and protect configuration logs.

Next, configure the Resource Server:

```java
@Bean
SecurityFilterChain resourceServerSecurity(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/health").permitAll()
            .requestMatchers("/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.opaqueToken(Customizer.withDefaults()));

    return http.build();
}
```

Spring Security uses the configured introspector to send the token to the AS, read the response, and create an authenticated principal. Authorities are usually created from the scopes in the response. Verify the actual mapping if the system uses custom claims.

### 10.1. Introspection Requester and Access Token Are Two Different Credentials

When Spring Security calls introspection:

- `client-id`/`client-secret` in the configuration are used for **the Resource Server to authenticate with the AS**.
- The access token in the API request is sent as the `token` parameter for **the AS to inspect**.

Do not use the end-user access token as the introspection client's secret. Do not send the introspection client secret to another Resource Server.

### 10.2. Mapping Scopes to Authorities

If the response contains:

```json
{
  "active": true,
  "scope": "orders.read orders.cancel",
  "sub": "user-42",
  "aud": ["https://checkout-api.example.com"]
}
```

The Resource Server can map these to:

```text
SCOPE_orders.read
SCOPE_orders.cancel
```

Then use `hasAuthority`/method security and check ownership/tenant in the domain layer. Do not treat `active=true` as the final authorization decision.

### 10.3. Checking Audience in the Application

Not every introspection client/library automatically enforces audience based on each API's identifier. Verify the behavior of your Spring Security version and add a validator/policy if needed.

If the AS returns `aud`, the RS must check that the token is intended for itself. If the response has no audience, the RS needs another contract to determine resource binding or require the AS to return active only for the proper requester under the configured semantics.

## 11. Introspection Cache: Balancing Freshness and Performance

If the RS introspects on every API request, each request adds a network round-trip and load on the AS. Results can be cached for a short period, but caching delays visibility of revocations or policy changes.

### 11.1. Positive Cache

A positive cache stores `active=true` results. Keys should be based on a token fingerprint/hash; do not store raw tokens in visible keys or metrics. The TTL must be bounded by:

- Remaining time until `exp`.
- Freshness level required by the product.
- Risk window acceptable after revocation.
- Cache invalidation if the AS has a push/eviction mechanism.
- Audience/tenant/resource context if the response depends on the requester.

For example: if an access token has 60 seconds left, the cache must not keep it active for more than 60 seconds; if policy requires reflecting revocation within 10 seconds, the positive cache should also not exceed that limit.

### 11.2. Negative Cache

You may cache `active=false` for a very short duration to avoid repeated requests with junk tokens. However:

- A newly issued token might not yet have synchronized to the introspection store.
- Caching negative results too long can reject a newly valid token.
- Token fingerprints must be safe and bounded.
- Do not return details on why a token is inactive.

### 11.3. HTTP Cache Headers and Internal Cache

RFC 7662 requires introspection responses to include `Cache-Control: no-store` and `Pragma: no-cache` to prevent HTTP intermediaries/browsers from caching sensitive responses.

That does not mean the RS cannot build an **internal authorization cache** under its own policy. An internal cache is application state with TTL, security controls, and invalidation; the response must not be turned into a publicly cacheable HTTP resource.

### 11.4. Caching Must Not Turn a Timeout into Active

If the AS times out, never take an error response and cache it as `active=true`. You may use a cached positive result within its remaining valid TTL if policy allows. When no sufficiently fresh result exists, the RS must apply a safe failure policy.

## 12. Handling AS Outages and Introspection Errors

Introspection creates a runtime dependency on the AS. Distinguish between these scenarios:

| Situation | Meaning | Handling approach |
|---|---|---|
| HTTP 200, `active=false` | Token is not active | Reject request (typically 401) |
| HTTP 200, `active=true` | Token is active | Continue audience/scope/policy checks |
| HTTP 400 | Malformed introspection request | Investigate integration/config |
| HTTP 401 | Introspection client authentication failed | Check credentials/rotation |
| HTTP 403 | Requester not authorized to introspect | Check policy/registration |
| HTTP 429 | AS rate limiting | Backoff, valid cache, quota |
| HTTP 5xx | AS or dependency failure | Circuit breaker, timeout, fallback policy |
| Network timeout | Unable to confirm status | Do not treat token as active |
| Invalid response/schema | Untrusted result | Fail safely and alert |

### 12.1. Fail-Open or Fail-Closed?

For payment, admin, or sensitive data endpoints, when introspection is unavailable and no valid cache exists, you must typically **fail-closed**: reject or return a temporary error rather than treating the token as active.

Some availability-critical systems may accept using a still-valid positive cache for a short time. That is a bounded policy, not unconditional fail-open.

Distinguish:

- Inactive token: request is unauthenticated, typically return 401.
- AS unavailable: RS cannot verify, may return 503 or an appropriate dependency error.
- Active token missing scope: 403.

Do not return 401 for all AS errors if doing so tricks the client into thinking its credentials are wrong and repeatedly logging in or requesting new tokens.

### 12.2. Timeouts and Retries

Set explicit timeouts for the introspection HTTP client, including connect/read/response deadlines matching SLOs. Retry only on transient errors with bounded attempts and exponential backoff/jitter. Do not retry infinitely or immediately retry every API request during an AS outage.

If 100 concurrent requests need introspection for the same token, consider request coalescing/single-flight per token fingerprint to reduce load. This mechanism must ensure one result is never used for a different token.

### 12.3. Circuit Breaker and Bulkhead

A circuit breaker can stop calling the AS during sustained errors, helping avoid exhausting connection pools. A bulkhead limits concurrent introspection calls. When the circuit is open, use valid positive cache entries if policy allows; otherwise, return a temporary error.

Never bypass validation or mark a token active just because the circuit breaker is open.

## 13. Securing the Introspection Endpoint

### 13.1. Preventing Token Scanning

If the endpoint is public, an attacker can send millions of guessed tokens to identify valid ones. Protections:

- Require authentication of the protected resource.
- Allow only authorized registered resources/clients.
- Rate limit by authenticated client and trusted network source.
- Limit request body, headers, and token length.
- Do not disclose reasons for inactivity.
- Monitor abnormal active/inactive ratios.
- Do not expose the endpoint on a public API gateway if unnecessary.

### 13.2. Least Privilege for the Introspection Requester

Each RS should have its own identity or permissioned identity group. If one RS's credentials are compromised, an attacker should not gain permission to introspect all token types or read unrelated metadata.

You can restrict resource audience, tenant, token type, and response claims. If the AS does not support per-resource introspection policy out of the box, add the policy via an appropriate extension point and test thoroughly.

### 13.3. Credential Protection

- Use a secret manager or private key store.
- Support rotation with overlap if the authentication method permits.
- Do not log HTTP Basic headers.
- Prefer `private_key_jwt` or mTLS when appropriate for the threat model.
- Use TLS and certificate validation.
- Revoke introspection credentials if a service is compromised.

### 13.4. Never Let the Caller Choose the Introspection URL

If the RS receives tokens from external clients, never take the introspection URL from request parameters, arbitrary JWT claims, or caller headers. The endpoint must come from trusted configuration. Otherwise, an attacker could trick the RS into sending the token to an attacker-controlled server, leading to token exfiltration or SSRF.

## 14. Introspection with JWTs and Opaque Tokens in Spring

### 14.1. Opaque Token

For opaque tokens, Spring Security uses `OpaqueTokenIntrospector` to call the AS. The `active` response determines whether the token is considered active; metadata is converted into a principal/authorities.

This is a common approach when the AS holds centralized token state or you want the RS not to know internal token formats.

### 14.2. JWT

For JWTs, Resource Server typically uses `JwtDecoder` for local verification. If the latest revocation status is needed, you can:

- Use introspection for JWT tokens depending on the AS implementation.
- Combine local signature validation with an online status check.
- Use a denylist/event propagation or token version.
- Switch to opaque tokens for use cases requiring centralized state.

Do not assume every AS introspects JWTs the same way. Some implementations only query the authorization store; others may validate tokens depending on configuration. Always verify the actual contract.

### 14.3. Do Not Confuse the Roles of Two Filter Chains

If the same Spring Boot process acts as both Authorization Server and Resource Server:

- The AS chain protects `/oauth2/introspect` and OAuth endpoints.
- The RS chain protects business APIs.
- The RS introspection client is the client credential used when calling the AS.
- The end-user/workload access token is the credential inspected at the API.

Separate the filter chains and matchers in the right order so API requests are not mistakenly handled as OAuth endpoints or vice versa.

## 15. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Making the introspection endpoint public | Token scanning, metadata leakage | Authenticate and authorize the requester |
| Using the inspected token as the Basic credential | Confusing two credentials | Use a dedicated RS identity |
| Trusting `token_type_hint` as proof | Wrong lookup type or policy | Treat as a hint; verify the actual token |
| Treating `active=true` as allowing all APIs | Bypassing audience/scope | RS continues authorization checks |
| Returning detailed reasons for `active=false` | Token enumeration | Minimal response |
| Treating timeout as active | Policy-violating fail-open | Fail safely or use valid cache |
| Caching positive results too long | Slow revocation | Bound TTL by exp and revocation SLO |
| Caching responses via proxies | Leaking metadata/token status | no-store/no-cache |
| Not sharing the authorization store | Nodes return different active/inactive results | Shared consistent state |
| No request size limits | Memory/CPU exhaustion | Cap body/token length |
| Logging token/body/Basic header | Credential leakage | Redaction |
| Introspecting every API request uncached | Higher latency and AS load | Controlled caching or local JWT validation |
| Skipping audience checks | Tokens for other APIs accepted | Verify aud/resource |
| Using introspection instead of revocation | Protocol misunderstanding | Revocation endpoint and introspection are distinct operations |
| Using introspection instead of refresh | No new token obtained | Use refresh grant when permitted |
| Mapping all errors to 401 | Client retry/auth loops | Distinguish inactive from AS unavailable |

## 16. Testing Token Introspection

### 16.1. Request/Response Matrix

| Test case | Input | Expected result |
|---|---|---|
| Active token | Issued token, not expired, not revoked | `active=true` |
| Non-existent token | Random token string | `active=false` |
| Expired token | `exp` in the past | `active=false` |
| Revoked token | Authorization state marked inactive | `active=false` |
| Not-yet-valid token | `nbf` in the future | `active=false` per policy |
| Missing token parameter | No `token` | `invalid_request` |
| Empty token | Blank `token` | Reject request |
| Wrong token_type_hint | Hint differs from actual type | AS still looks up per RFC rules |
| Wrong requester credentials | Invalid Basic/private_key_jwt | Reject authentication |
| Unauthorized requester | Valid client but forbidden by policy | Reject authorization |
| Missing TLS | Request without transport protection | Blocked at deployment boundary |
| Wrong audience token | Token not intended for RS | Rejected by RS |
| Token missing scope | Active but insufficient permissions | RS returns 403 |
| Response missing active | Invalid schema | RS rejects response |
| Response active not boolean | Wrong JSON type | RS rejects response |

### 16.2. Cache and Outage Matrix

| Case | Condition | Result to prove |
|---|---|---|
| Positive cache hit | Active token within cache TTL | No AS call made |
| Cache near TTL end | Token has little time left | Cache does not exceed exp |
| Token revoked | Positive cache still present | Revocation delay stays within chosen SLO |
| Negative cache | Inactive token | No long cache causing false negatives |
| AS timeout | No fresh result | Never treated as active |
| AS 429/503 | Rate limiter/outage | Backoff and circuit breaker |
| Replay request coalescing | Multiple threads with same token | Single introspection request if policy permits |
| Multi-instance | Nodes share same AS/store | Consistent state as designed |
| Credential rotation | RS rotates secret/key | New introspection tokens authenticate properly |

### 16.3. Integration Tests in Spring

With Spring Security Resource Server, configure a mock AS or real test server to verify:

1. API requests with an opaque token call the right introspection URI.
2. The RS authenticates using the introspection client credential.
3. An `active=true` response creates an authenticated principal.
4. Scopes in the response are mapped to authorities.
5. `active=false` causes the request to be rejected.
6. An active token missing scopes results in 403.
7. An active token with the wrong audience is rejected by the validator/policy.
8. Timeouts/5xx are handled according to the failure policy.
9. Access tokens and Basic credentials are not logged.

For Spring Authorization Server, test the real Token Introspection Endpoint through `SecurityFilterChain`, registered client authentication, and `OAuth2AuthorizationService`. Do not merely mock a service lookup and conclude the endpoint is protected.

## 17. Observability and Operations

### 17.1. Metrics to Monitor

- Introspection requests/second by requester client.
- Ratio of `active=true` vs. `active=false`.
- HTTP 400/401/403/429/5xx counts.
- Endpoint p50/p95/p99 latency.
- Database/authorization store lookup latency.
- Timeouts, connection pool exhaustion, and circuit breaker state.
- Cache hit/miss ratio and positive cache age.
- Delay from revocation until RS rejects the token.
- Rejection rate due to audience/scope.
- Credential rotation and authentication failures.

Do not include raw tokens, token strings, secrets, or arbitrary caller-supplied values in metric labels.

### 17.2. Audit Events

You can record events such as `TOKEN_INTROSPECTED`, `TOKEN_INTROSPECTION_DENIED`, `INTROSPECTION_CLIENT_AUTH_FAILED`, and `TOKEN_REVOCATION_OBSERVED`.

Audit records should contain correlation ID, authenticated requester client ID, pseudonymized token fingerprint/JTI when needed, active/inactive result, timestamp, and policy outcome. Do not store raw tokens or Basic headers.

### 17.3. Runbook When Introspection Latency Increases

1. Check RPS by requester and active/inactive ratio.
2. Check DB/authorization store latency, indexes, and connection pools.
3. Check network between RS and AS, TLS handshakes, and DNS.
4. Check cache hit ratio and TTLs.
5. Check client retry storms, timeouts, and circuit breakers.
6. Identify credential rotation errors or AS deployments.
7. If needed, shed load via quotas/backoff and use valid positive cache entries per policy.
8. Never switch to unconditional fail-open just to make the 5xx chart drop.

## 18. Production Checklist

- [ ] Introspection Endpoint only allows authenticated and authorized protected resources/clients.
- [ ] Endpoint uses HTTPS/TLS and RS verifies the AS certificate.
- [ ] Request uses POST form with required `token`.
- [ ] `token_type_hint` is treated as a hint, not proof.
- [ ] Response contains boolean `active`.
- [ ] Inactive responses do not disclose sensitive reasons.
- [ ] RS distinguishes active status from authorization by audience/scope/tenant.
- [ ] Introspection requester has a dedicated identity and protected credentials.
- [ ] Authorization store is shared across issuance, revocation, and introspection.
- [ ] HTTP response includes `Cache-Control: no-store` and `Pragma: no-cache`.
- [ ] Internal cache has TTL bounded by expiry and revocation SLO.
- [ ] Timeouts, retries, circuit breaker, and bulkhead are configured.
- [ ] AS outages never automatically mark tokens as active.
- [ ] Tokens are never sent to caller-specified introspection URLs.
- [ ] Tokens, secrets, Authorization headers, and sensitive request bodies are never logged.
- [ ] Tests cover active/inactive, revoked, expired, invalid requester, wrong audience/scope, and outage scenarios.
- [ ] Latency, active ratio, errors, cache hits, and revocation propagation are measured.

### Core Takeaways

**OAuth 2.0 Token Introspection (RFC 7662) allows a protected resource to query an Authorization Server about the status and metadata of a token.** The request sends the token via POST to a protected endpoint; the AS authenticates the requester and returns JSON with a required `active` field. If the token is inactive, the response should be minimal to avoid disclosing reasons.

In Spring Authorization Server, the Introspection Endpoint uses authorization/token state managed by `OAuth2AuthorizationService`. In Spring Security Resource Server, opaque token support uses an introspector to verify state and build the principal/authorities. Introspection is especially useful for opaque tokens and use cases requiring centralized state; in return, it creates a network dependency and requires timeouts, caching, rate limits, and a failure policy. **`active=true` only confirms token status; the Resource Server must still check audience, scope, and business permissions before granting access.**

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
