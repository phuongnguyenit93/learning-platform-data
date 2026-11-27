# Token Parameter, token_type_hint, and Client Authentication

> **Chapter: Revocation.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module — learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application. The lesson focuses on the **RFC 7009** request contract, the meaning of the `token` and `token_type_hint` parameters, **OAuth client authentication and binding** requirements, Spring Authorization Server configuration, and testing error/abuse cases.

## 1. Purpose and Scope of Token Revocation

When a user logs out, disconnects an application, loses a device, or suspects a refresh token is compromised, the OAuth client can ask the Authorization Server (AS) to invalidate a token **before its expiration time**. The standard mechanism is defined by **RFC 7009 — OAuth 2.0 Token Revocation**.

Running example:

| Component | Illustrative Value | Role |
|---|---|---|
| Authorization Server | `https://login.example.vn` | Issues and manages tokens with Spring Authorization Server |
| Revocation Endpoint | `https://login.example.vn/oauth2/revoke` | Receives token revocation requests |
| Confidential OAuth Client | `portal-web` | BFF that signs users in and stores tokens |
| End User | `user-123` | Subject of the authorization grant |
| Resource Server | `https://api.example.vn` | API that uses access tokens for access control |
| Existing Tokens | `A0` (access token), `R0` (refresh token) | Issued within the same authorization |

When the user disconnects `portal-web`, the client sends `R0` to the revocation endpoint. The AS authenticates the client, verifies that the token **was issued to that exact client**, and updates its state. If successful, the client can no longer use `R0` to obtain new access tokens.

**Three rules to remember:**

1. `token` is the **credential value to revoke**, required in the body.
2. `token_type_hint` is only a **lookup hint**, optional and possibly wrong.
3. Every revocation request must pass **appropriate client authentication and token ownership verification**. Never allow one client to revoke another client's token.

### 1.1. Do Not Confuse Revocation with Other Mechanisms

| Mechanism | Primary Function | Difference from Revocation |
|---|---|---|
| **Token Revocation — RFC 7009** | Requests that a token be invalidated | A **state-mutating** operation |
| **Token Introspection — RFC 7662** | Queries whether a token is active, its scopes, aud, etc. | Primarily **reads state** |
| **Refresh Token grant** | Requests a new access token using a valid refresh token | Not token revocation |
| **OIDC RP-Initiated Logout** | Ends the login session at the OpenID Provider | Does not automatically guarantee all OAuth access tokens are revoked |
| **Deleting tokens on the client** | Client stops holding the credential | Token may still be active at the AS |
| **Deleting an authorization/grant** | Revokes the entire authorization per administrative policy | Can be broader than a single token revocation request |

## 2. HTTP Request per RFC 7009

The client must send an `HTTP POST` to the revocation endpoint obtained from trusted metadata/configuration. The endpoint URL must be **HTTPS**. The request body uses `application/x-www-form-urlencoded`.

Example of a confidential client authenticating with `client_secret_basic`:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.vn
Authorization: Basic REDACTED_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=R0_REDACTED&token_type_hint=refresh_token
~~~

This is an illustrative HTTP request; `R0_REDACTED` and the Basic credentials are not real values. Actual tokens must be properly URL-encoded per form rules. Do not write the body or `Authorization` header to access logs.

### 2.1. Parameter Table

| Parameter | Required | Value | Meaning |
|---|---|---|---|
| `token` | **Yes** | Access token / refresh token string | The specific token the client wants to revoke |
| `token_type_hint` | No | Typically `access_token` or `refresh_token` | Hints the AS to look up the token faster |
| Client authentication | Depends on client type, but must comply with security profile | HTTP Basic, JWT assertion, mTLS, or a supported public-client method | Proves/identifies the caller per RegisteredClient and policy |

Do not send `grant_type=revocation`: the revocation endpoint **is not an OAuth grant type**. Do not rename the `token` field to `refresh_token` just because you want to revoke a refresh token.

### 2.2. Fields That Do Not Belong to the Required Request

- `redirect_uri` and `code_verifier`: belong to Authorization Code/PKCE, not the primary revocation fields.
- `scope`: not used to arbitrarily decide how much scope to revoke.
- `user_id` or `tenant_id` in the body: not proof of revocation authority.
- `client_id` in the form: may be needed in a public-client profile, but cannot replace confidential client authentication.
- `Authorization: Bearer TOKEN_TO_REVOKE`: not a replacement for Basic/private_key_jwt/mTLS client authentication at the revocation endpoint.

### 2.3. Do Not Send the Token in the URL/Query

Do not use:

~~~http
GET /oauth2/revoke?token=R0_REDACTED HTTP/1.1
Host: login.example.vn
~~~

GET/query can expose the token through browser history, Referer headers, proxies, WAFs, and telemetry. RFC 7009 mentions some JSONP/GET techniques for legacy clients, but **they should not be included in new systems** due to security risks. Use a POST body over HTTPS, `no-store`, and log redaction.

## 3. The `token` Parameter: Token Types and Revocation Scope

RFC 7009 §2 requires an Authorization Server to **MUST** support revoking refresh tokens and **SHOULD** support revoking access tokens. Upon receiving `token`, the AS must determine whether the token exists and belongs to the requesting client.

| Value Passed in `token` | Desired Outcome | What Must Be Distinguished |
|---|---|---|
| Refresh token `R0` | `R0` can no longer be used to refresh | May also cascade to access tokens issued from the grant |
| Access token `A0` | `A0` can no longer be used to call APIs | Offline JWTs may not yet know about the revocation |
| Already expired token | Remains invalid | No need to return an error just because it is already expired |
| Already revoked token | Remains invalid | Repeated requests should have idempotent semantics |
| String unknown to the AS | No state needs to be modified | RFC returns HTTP 200 for a valid client |
| Token issued to another client | Caller has no authority over the token | AS must **reject**, never modify another client's token |

### 3.1. Revoking One Token May Affect Other Tokens

RFC 7009 §2.1 specifies:

- When revoking a **refresh token**, if the server supports access token revocation, the server **SHOULD** also invalidate access tokens issued from the same authorization grant.
- When revoking an **access token**, the server **MAY** also invalidate the corresponding refresh token.
- The extent of cascading is an AS policy; you cannot rely on the `token_type_hint` name to decide that all user sessions will be revoked.

Across multiple devices, each device/client may have its own grant and refresh token. A single `token=R0` request is not implicitly a "logout all devices" command.

### 3.2. An Invalid Token Does Not Mean an Invalid Request

A token may be expired or absent from the store. For a **validly authenticated client**, RFC 7009 requires returning `200 OK` for invalid tokens so the endpoint does not leak credential existence. Conversely, a request missing the `token` field or failing client authentication is a genuine error.

## 4. `token_type_hint`: Optional and Potentially Wrong

The RFC defines two common hints:

- `access_token` — the caller guesses `token` is an access token.
- `refresh_token` — the caller guesses `token` is a refresh token.

The hint helps the AS choose which index or token type to look up first. **The hint is not a verified token type, not an authorization, and not a strict filter.**

### 4.1. Mandatory Fallback When the Hint Is Wrong

RFC 7009 requires: **if the AS does not find the token using the hint, it MUST extend the lookup across all token types it supports**. The AS also **MAY ignore the hint** and detect the token type itself.

Example where `R1` is an actual refresh token:

| Request | Valid Processing Path | Expected Outcome |
|---|---|---|
| `token=R1&token_type_hint=refresh_token` | Look up refresh token | Revokes R1 |
| `token=R1&token_type_hint=access_token` | Access lookup misses, fall back to refresh | **Still revokes R1** |
| `token=R1` | Determine token type automatically | Still revokes R1 |
| `token=R1&token_type_hint=unknown_type` | Ignore unrecognized hint | Still revokes R1 |
| `token=A1&token_type_hint=refresh_token` | Fall back to access token | Revokes A1 if AS supports it |
| `token=UNKNOWN&token_type_hint=refresh_token` | Not found in any supported type | HTTP `200` for a valid client |

If a custom provider only looks up by the hint and returns `200` when not found, **an active refresh token could remain unrevoked**. This is an important implementation bug that needs a negative test.

### 4.2. Do Not Confuse with the `unsupported_token_type` Error

RFC 7009 defines `unsupported_token_type` for when the Authorization Server **does not support revoking the actual type of token presented** — for example, a server that does not implement access token revocation.

**Wrong:** sending `token_type_hint=typo` ⇒ returning `unsupported_token_type`.

**Right:** an unrecognized hint is **ignored** and does not alter the response meaning. `unsupported_token_type` refers to the **ability to revoke the actual token type**, not a typo in the hint.

### 4.3. Note for Spring

Spring Authorization Server exposes `OAuth2TokenRevocationAuthenticationToken.getToken()` and `getTokenTypeHint()`. With `OAuth2AuthorizationService.findByToken(...)` or custom storage, test a correct hint, wrong hint, absent hint, and nonsensical hint. Do not infer from the method name that lookup automatically follows fallback rules for every custom token type.

## 5. Client Authentication at the Revocation Endpoint

RFC 7009 requires confidential clients to send authentication credentials as specified in OAuth 2.0. The AS authenticates the client **first**, then verifies the token was issued **to that exact client**, before invalidating it.

There are two **independent** security questions:

1. Is the caller actually `portal-web`, using its registered authentication method and credentials?
2. Does token `R0` belong to an `OAuth2Authorization` of `portal-web`?

Another client such as `billing-job` must not revoke `portal-web`'s token merely because it is also a valid confidential client.

### 5.1. Methods in Spring Authorization Server

Spring Authorization Server 1.5.x supports client authentication methods shared across token/introspection/revocation endpoints:

| Method | Mechanism | Things to Note |
|---|---|---|
| `client_secret_basic` | Client ID + secret in HTTP Basic | Use TLS, secret store, do not log Authorization header |
| `client_secret_post` | Client ID + secret in form body | Only use if registration allows, avoid body logging |
| `private_key_jwt` | Client JWT assertion signed with private key | Validate `iss/sub/aud/exp/nbf`, prevent replay |
| `client_secret_jwt` | Assertion signed with secret | Requires strong secret and short lifetime |
| `tls_client_auth` | Client PKI certificate in mTLS | Validate certificate chain and identity mapping |
| `self_signed_tls_client_auth` | Certificate registered in client JWKS | Validate registered certificate, do not trust arbitrary certs |
| `none` | Public client without client secret | Verify behavior/policy; do not treat self-asserted `client_id` as security proof |

Do not embed a client secret in SPA JavaScript or a mobile app and call it a confidential client. Public-client revocation must be handled by the AS under a policy suited to the threat model and exact deployment version; RFC 7009 has a dedicated section on public client risks.

### 5.2. Token Ownership Must Be Bound to RegisteredClient

A typical server-side check is:

~~~text
authenticated caller's registeredClient.id
    ==
looked-up token's authorization.registeredClientId
~~~

Do not use user email, display client name, or an unauthenticated `client_id` in place of this check. If the token belongs to another client, do not modify the record, do not terminate someone else's session, and do not leak token contents.

### 5.3. PKCE Does Not Replace Client Authentication

PKCE proves the client holds the `code_verifier` matching the `code_challenge` when exchanging an authorization code. It is **not** a confidential client authentication method at the revocation endpoint, nor does it by itself prove authority to revoke any token.

DPoP and mTLS can be used to sender-constrain tokens per profile; if the revocation policy requires proof-of-possession, implement the proper protocol check. Do not assume that passing a DPoP-bound token in `token` automatically proves possession of the private key.

## 6. Secure Request-Processing Algorithm

~~~mermaid
flowchart TD
    A["POST HTTPS /oauth2/revoke"] --> B["Validate form and required token"]
    B -->|Missing/invalid| Bad["invalid_request"]
    B --> C["Client authentication per registration"]
    C -->|Failed| AuthErr["invalid_client"]
    C --> D["Look up token; hint only aids lookup"]
    D --> E{"Token exists?"}
    E -->|No| Ok["HTTP 200, no state leak"]
    E -->|Yes| F{"Belongs to this registered client?"}
    F -->|No| Forbidden["Reject, do not modify token"]
    F -->|Yes| G{"Token type supported?"}
    G -->|No| Unsupported["unsupported_token_type"]
    G -->|Yes| H["Invalidate token + cascade per policy"]
    H --> I["Commit authorization/token state"]
    I --> Ok
~~~

Processing order:

1. The client obtains `revocation_endpoint` from trusted discovery/registration and verifies HTTPS.
2. The server receives the POST form, validates `token`, content type, and length/body size limits.
3. The client authentication filter identifies the RegisteredClient and a valid authentication method.
4. The AS looks up the token by hint if needed, falling back when the hint is wrong/misses.
5. If found, the AS verifies the token/authorization belongs to the calling RegisteredClient.
6. Apply the revocation policy for the token type and related tokens/grants.
7. Perform invalidation and persist state durably; design transactions if contention is possible.
8. Return HTTP 200 for revoked/unknown tokens from a valid client, or the corresponding OAuth error.

**Do not:** build a public controller that accepts `token`, searches the DB, and deletes arbitrarily without knowing which client the caller is.

## 7. HTTP Responses: 200, Protocol Errors, and 503

### 7.1. HTTP 200 for Revoked or Unknown Tokens

RFC 7009 §2.2 requires HTTP 200 for successful revocation **or invalid tokens**. Clients must not rely on the body to tell whether a token ever existed.

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Pragma: no-cache
Content-Length: 0
~~~

Do not create a revocation API returning:

~~~json
{
  "token_exists": true,
  "revoked_now": true,
  "subject": "user-123"
}
~~~

That response can be used to enumerate tokens/identities. Do not turn RFC success into an oracle leaking internal state.

### 7.2. Handling Matrix

| Case | Expected Result | Explanation |
|---|---|---|
| Valid client, active token owned by it | `200` | Token is invalidated |
| Valid client, unknown token | `200` | Avoids confirming whether the token exists |
| Valid client, already expired/revoked token | `200` | Idempotent toward desired state |
| Wrong/nonsensical hint | Still processes actual token | Hint is non-binding |
| Missing `token` or malformed form | `invalid_request` or appropriate protocol error | Request lacks required input |
| Wrong secret/JWT client assertion | `invalid_client` (typically 401) | Caller is not authenticated |
| Token belongs to another client | Reject per policy, do not revoke | Disallow cross-client mutation |
| AS does not support revoking actual token type | `unsupported_token_type` | Not a hint error |
| Server returns HTTP 503 | Token may still be active | Retry with backoff per RFC |

**Do not return 200 for every failure.** If client authentication fails and the server returns 200, the client may think the token is safe while the AS never executed revocation.

### 7.3. Timeouts and Retries

If the revocation endpoint returns `503`, RFC 7009 requires the client to **assume the token may still exist** and retry only after a reasonable interval, respecting `Retry-After` when present.

If a request times out after being sent, the client does not know whether the AS committed the revocation. Since revocation has idempotent semantics, controlled retries can be appropriate, with:

- Bounded retry count, exponential backoff, and jitter.
- Never logging the raw token in retry logs.
- Never treating an HTTP timeout as confirmation that the token was revoked.
- If the user has logged out, blocking further use of the credential **on the client** per local policy, without confusing local cleanup with server revocation.
- Having a server-side reconciliation/retry mechanism for systems requiring guaranteed revocation.

## 8. Spring Authorization Server 1.5.x Configuration

Spring Authorization Server provides the Revocation Endpoint by default at `/oauth2/revoke` via `AuthorizationServerSettings`; **OIDC does not need to be enabled**. Related components:

| Component | Role |
|---|---|
| `OAuth2TokenRevocationEndpointFilter` | Receives revocation requests |
| `OAuth2TokenRevocationAuthenticationConverter` | Extracts `token`/`token_type_hint` from the form |
| `OAuth2TokenRevocationAuthenticationToken` | Carries token string, hint, and client principal |
| `OAuth2TokenRevocationAuthenticationProvider` | Processes revocation |
| `OAuth2ClientAuthenticationFilter` | Authenticates the client per registration |
| `OAuth2AuthorizationService` | Finds/saves authorization and token metadata |
| `OAuth2TokenRevocationEndpointConfigurer` | Customizes converters/providers/response handlers |
| `AuthorizationServerSettings` | Endpoint paths, issuer |

### 8.1. SecurityFilterChain

Spring Authorization Server 1.5.x / Spring Security 6.x configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.web.SecurityFilterChain;

class AuthorizationServerRevocationConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer server =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(server.getEndpointsMatcher())
                .with(server, authorizationServer ->
                        authorizationServer.tokenRevocationEndpoint(
                                Customizer.withDefaults()))
                .authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated());
        return http.build();
    }

    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
                .issuer("https://login.example.vn")
                .tokenRevocationEndpoint("/oauth2/revoke")
                .build();
    }
}
~~~

This is a filter-chain skeleton, not a complete standalone Authorization Server: you still need `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generators, signing keys if issuing JWTs, and other chains/user authentication. `tokenRevocationEndpoint(Customizer.withDefaults())` highlights the extension point; this endpoint is already configured in the default endpoint chain.

### 8.2. RegisteredClient Using Client Secret Basic

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

static RegisteredClient portalClient(String encodedSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientSecret(encodedSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(
                    AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .build())
            .build();
}
~~~

`encodedSecret` must be a value hashed by a `PasswordEncoder`, not a plaintext secret. Store the client via `RegisteredClientRepository`. **There is no `REVOCATION` grant type to add to `RegisteredClient`.** Revocation is not an OAuth grant.

### 8.3. Controlled Customization

`OAuth2TokenRevocationEndpointConfigurer` supports:

- `revocationRequestConverter(...)` / `revocationRequestConverters(...)`.
- `authenticationProvider(...)` / `authenticationProviders(...)`.
- `revocationResponseHandler(...)`.
- `errorResponseHandler(...)`.

If you add a custom `AuthenticationProvider` to enforce a tenant/token-family policy, never let the new provider skip client authentication and ownership verification. A provider added **after** the default provider may never run if the default provider already handled the request; verify actual ordering and behavior.

Do not implement a public `@PostMapping("/oauth2/revoke")` that bypasses Spring's filter chain.

### 8.4. Discovery

The AS may publish:

~~~json
{
  "issuer": "https://login.example.vn",
  "revocation_endpoint": "https://login.example.vn/oauth2/revoke",
  "revocation_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt",
    "tls_client_auth"
  ]
}
~~~

This is only a metadata sample; values must match runtime configuration. Clients obtain the address from a trusted source and verify HTTPS/issuer. Do not take the revocation URL from a user-supplied query parameter, avoiding SSRF/token exfiltration.

## 9. Ownership and Token Metadata in OAuth2AuthorizationService

`OAuth2Authorization` stores the RegisteredClient ID, principal, grant, scopes, and token metadata. `OAuth2AuthorizationService.findByToken(token, tokenType)` can look up an authorization by token value. `OAuth2Authorization.Token.isActive()` relies on expiration and invalidated metadata.

**Core security point:** after finding the token, the AS must compare:

~~~text
authenticatedRegisteredClient.getId()
       ==
authorization.getRegisteredClientId()
~~~

Do not match tokens by username/email to decide revocation authority, because multiple OAuth clients can serve the same user.

### 9.1. Ownership Verification Service Pattern

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

final class OwnedTokenLookup {
    private final OAuth2AuthorizationService authorizationService;

    OwnedTokenLookup(OAuth2AuthorizationService authorizationService) {
        this.authorizationService = authorizationService;
    }

    OAuth2Authorization findOwned(
            RegisteredClient authenticatedClient,
            String rawToken) {

        // null: lookup across token types supported by the store.
        OAuth2Authorization authorization =
                authorizationService.findByToken(rawToken, null);

        if (authorization == null) {
            return null; // 200 for unknown token after valid auth.
        }

        if (!authorization.getRegisteredClientId()
                .equals(authenticatedClient.getId())) {
            throw new SecurityException("Revocation not permitted");
        }
        return authorization;
    }
}
~~~

This is an example of **read and ownership verification only**, not a complete controller or provider. `authenticatedClient` must come from successful client authentication. If custom storage does not support `findByToken(token, null)` for every token type, implement fallback per RFC 7009 instead of treating the hint as a mandatory filter.

### 9.2. Invalidating the Token After Authentication and Authorization

Spring Authorization Server 1.4+ provides `OAuth2Authorization.Builder.invalidate(OAuth2Token)`. Skeleton example at the **internal service layer**:

~~~java
import org.springframework.security.oauth2.core.OAuth2Token;
import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;

// Only run AFTER authenticating the client and verifying ownership!
OAuth2Authorization.Token<? extends OAuth2Token> entry =
        authorization.getToken(rawToken);

if (entry != null && entry.isActive()) {
    OAuth2Authorization updated = OAuth2Authorization.from(authorization)
            .invalidate(entry.getToken())
            .build();
    authorizationService.save(updated);
}
~~~

This snippet **does not replace the default provider**: it does not yet handle cascading, transactions/CAS, errors, auditing, token type policy, refresh races, or multi-node synchronization. Use it only to understand how token metadata is marked. With `JdbcOAuth2AuthorizationService`, persisting data in the DB **does not by itself guarantee** that every read–invalidate–save operation is atomic across multiple pods.

## 10. Impact on JWTs, Opaque Tokens, and Logout

### 10.1. Refresh Token Revocation and Token Families

When the AS revokes refresh token `R0`, refresh grants using `R0` must be rejected. If the AS applies rotation, the client may already hold successor `R1`; when the user wants to end the **entire authorization grant**, you must define a mechanism to revoke the token family/authorization rather than just marking the `R0` string as consumed.

Revocation policies may affect access tokens based on the same grant. Measure/verify against your exact provider and storage version rather than treating HTTP 200 as proof that every token in the same family vanished automatically.

### 10.2. JWT Access Tokens

A Resource Server verifying JWTs purely offline (signature, issuer, audience, expiry, scopes) **does not automatically know** that the AS just invalidated the token. An already-issued JWT still has a valid signature until `exp`. If fast revocation is required, consider short TTLs, introspection/status checks, denylists, or propagation events. Cache/replication delays may apply.

### 10.3. Opaque/Reference Access Tokens

A Resource Server using introspection can receive `active=false` after revocation. If the API caches introspection responses, the token may still be accepted during the cache TTL. Define the propagation SLO, TTL, and cache invalidation strategy.

### 10.4. Local Logout and OIDC Logout

A user clicking logout in `portal-web` does not necessarily invalidate the OP's SSO session. Conversely, OIDC RP-Initiated Logout does not automatically guarantee revocation of every client's access/refresh tokens.

A logout flow may include: clearing the local session, revoking the refresh token, handling access tokens/grants per policy, and performing OIDC logout if needed. **Do not use `token_type_hint=refresh_token` as a logout-all-devices command.**

## 11. Concurrency: Refresh Concurrent with Revoke

Suppose request A is exchanging `R0` for `R1` while request B requests revocation of `R0`. If two AS pods read an old snapshot and write state without version checks, a revoked token/grant risks being "resurrected".

~~~mermaid
sequenceDiagram
    autonumber
    participant C1 as Client refresh request
    participant C2 as Client revoke request
    participant AS1 as AS pod 1
    participant AS2 as AS pod 2
    participant DB as Shared authorization store

    C1->>AS1: POST /oauth2/token (R0)
    C2->>AS2: POST /oauth2/revoke (R0)
    AS1->>DB: Read version v1
    AS2->>DB: Read version v1
    AS2->>DB: Commit revoke v1->v2
    AS1->>DB: Attempt to commit rotation from v1
    DB-->>AS1: CAS conflict / version mismatch
    AS1-->>C1: invalid_grant or policy error
    AS2-->>C2: HTTP 200
~~~

This is a **system-designed versioned/CAS storage model**, not a claim that Spring provides CAS out of the box for every backend.

Important invariants:

- If revoke commits first, the subsequent refresh must be rejected per policy.
- If refresh commits first, revoking the grant/family must handle the already-issued successor.
- Do not let a stale writer overwrite a revoked field with active state.
- All AS pods must use shared storage or replication with appropriate consistency guarantees.
- Do not let a client retry a revoked refresh token just because another request was still in flight.
- Revocation of one token must not spill over to another `RegisteredClient`'s tokens.

## 12. Test Matrix

| # | Scenario | Expected Result |
|---|---|---|
| 1 | Revoke refresh token R0 with correct hint | HTTP 200; R0 inactive |
| 2 | Revoke access token A0 with correct hint | HTTP 200 if server supports it |
| 3 | Revoke R0 **without** hint | R0 still becomes inactive |
| 4 | Revoke R0 with wrong hint `access_token` | Fallback, R0 still becomes inactive |
| 5 | Revoke A0 with wrong hint `refresh_token` | Fallback, A0 inactive if supported |
| 6 | Revoke R0 with hint `made_up_type` | Ignore hint, still processes token |
| 7 | Revoke random/nonexistent token | HTTP 200 after valid auth |
| 8 | Revoke already revoked/expired token | HTTP 200, no stale state leak |
| 9 | Missing `token` | `invalid_request`/appropriate request error |
| 10 | Empty `token=` | Reject invalid request |
| 11 | Form has two `token` fields | Must not revoke wrong token; test converter validation |
| 12 | Confidential client missing secret | `invalid_client`; token unchanged |
| 13 | Wrong/rotated secret | `invalid_client`; token unchanged |
| 14 | Basic differs from registered method | Client authentication fails |
| 15 | JWT client assertion wrong aud/exp | Client authentication fails |
| 16 | mTLS certificate does not match client | TLS/OAuth client authentication fails |
| 17 | Client A revokes Client B's token | Not revoked, token B remains active |
| 18 | Same user, two different clients | Do not let A control B's grant |
| 19 | Public client method `none` | Follows policy; no arbitrary cross-client revoke |
| 20 | Actual token type unsupported | `unsupported_token_type` if applicable |
| 21 | Token endpoint/DB service returns 503 | Client assumes token may still be active |
| 22 | Wrong hint on custom authorization store | Token is still found and revoked |
| 23 | Revoke R0 then call refresh R0 | `invalid_grant`/valid error; no token issued |
| 24 | Revoke A0, RS verifies JWT offline only | Clearly determine window token remains usable |
| 25 | Revoke R0 and cascade A0 | Verify actual policy at AS/RS |
| 26 | Concurrent revocation and refresh | No grant resurrection after revoke commit |
| 27 | Revoke on AS pod 1, lookup on pod 2 | State consistent after commit |
| 28 | Cross-tenant/cross-user request | Must not affect other authorizations |
| 29 | Gateway logging/tracing enabled | No raw token, client secret, or Authorization header leaked |
| 30 | Oversized/burst requests | Rate limit, size bounds, no DoS |

### 12.1. Testing Wrong Hints Properly

Do not test a wrong hint by **revoking the same token a second time**, because the token is already inactive. Create a fresh token R2, send `token_type_hint=access_token`, and verify:

1. The endpoint authenticates the client properly.
2. Token R2 is still found in the refresh-token store.
3. The server returns 200.
4. Attempting to refresh R2 no longer issues a new token.
5. Authorization metadata records invalidation properly; no other client is affected.

### 12.2. Testing Ownership in Java (Skeleton)

~~~java
@Test
void cannotRevokeAnotherClientsToken() {
    RegisteredClient clientA = registeredClient("portal-web");
    RegisteredClient clientB = registeredClient("billing-job");

    String tokenB = issueRefreshTokenFor(clientB);

    assertThrows(SecurityException.class, () ->
            ownedTokenLookup.findOwned(clientA, tokenB));

    assertTrue(isTokenActive(tokenB));
}
~~~

The helpers and fixtures `registeredClient(...)`, `issueRefreshTokenFor(...)`, and `isTokenActive(...)` are defined by the application's test suite. This test only checks the ownership helper; integration tests must also send real HTTP requests through the Spring filter chain to test client authentication.

## 13. Troubleshooting, Auditing, and Runbook

| Symptom | Possible Cause | Resolution |
|---|---|---|
| 404 at `/oauth2/revoke` | Wrong path, security matcher/proxy routing | Check AuthorizationServerSettings/metadata |
| `invalid_client` | Wrong credentials, mismatched client auth method | Check RegisteredClient, secret hash, and method |
| `invalid_request` | Form missing token, bad encoding, empty token | Check Content-Type and parser |
| HTTP 200 but R0 can still refresh | Lookup hint bug, non-durable save, race | Check service/store, transactions, and tests |
| HTTP 200 but JWT A0 can still call APIs | RS verifies offline, unaware of revocation | Short TTL, introspection/denylist/caching |
| Unknown hint returns `unsupported_token_type` | Implementation treats hint as actual type | Fix per RFC 7009 |
| Client A makes token B inactive | Missing ownership check in custom provider | Block rollout and fix authorization matching |
| Increasing 503s | DB down, replica lag, or overload | Retry with backoff; do not claim token is revoked |
| Same request works intermittently across pods | Divergent store or config | Shared persistence and rollout check |
| Token value appears in APM | Overly broad body/header logging | Redact, rotate exposed credentials, and audit |

### 13.1. Metrics and Logs

Suggested metrics: `revocation_requests_total{outcome}`, `revocation_client_auth_failures_total`, `revocation_lookup_miss_total` (internal), `revocation_latency_seconds`, `revocation_store_failures_total`, `revocation_cascade_errors_total`, `revocation_race_conflicts_total`.

Audit logs can record request/correlation ID, allowed client ID, **verified** token type, and outcome. Do not put raw access tokens, refresh tokens, Basic headers, emails, user IDs, or high-cardinality identifiers into metric labels; do not store verbatim request bodies.

### 13.2. Suspected Token Theft

1. Identify client/issuer/token type and incident scope without pasting raw credentials into tickets.
2. Verify the caller/operator's authority over the authorization.
3. Revoke the token/authorization per policy, potentially including the token family and related access tokens.
4. Assess which Resource Servers may still accept the token (offline JWT/introspection/cache).
5. If client secret/private key/mTLS certificate was also exposed, rotate credentials; token revocation does not replace key rotation.
6. Re-verify negative cases (refresh after revoke, API call after revoke, multi-node).
7. Preserve the audit timeline and complete root-cause analysis.

## 14. Production Checklist and Self-Assessment

- [ ] `/oauth2/revoke` is exposed only over HTTPS, accepts POST form bodies, and does not log tokens.
- [ ] The exact required `token` field is used; not confused with parameter name `refresh_token`.
- [ ] `token_type_hint` only optimizes lookup; wrong/missing/nonsensical values are handled per RFC.
- [ ] `unsupported_token_type` is reserved for actual types that do not support revocation.
- [ ] Confidential client authentication follows RegisteredClient; anonymous requests cannot revoke tokens.
- [ ] `authorization.registeredClientId` is compared against the authenticated client before mutation.
- [ ] Public clients are handled per dedicated policy; PKCE or self-asserted `client_id` is not treated as confidential client authentication.
- [ ] HTTP 200 is returned for unknown/already-revoked tokens from a valid client; never discloses token existence.
- [ ] Authentication failures, malformed requests, and backend outages are not masked as fake 200s.
- [ ] Refresh/access token cascading and revocation propagation are documented and tested.
- [ ] Offline JWT, opaque introspection, and cache behaviors have been evaluated.
- [ ] Refresh/revoke races, multi-pod shared store, and transaction consistency have negative tests.
- [ ] Issuer/revocation endpoint/auth method metadata matches runtime.
- [ ] Legacy GET/JSONP revocation is not enabled unless required; CORS follows an allowlist.
- [ ] Auditing, metrics, alerts, and runbooks are in place without logging secrets.
- [ ] Clients stop using tokens after receiving 200; 503/timeouts are handled with bounded retries.

**Self-Check Questions**

1. Why must revoking a refresh token still send the `token` field rather than `refresh_token`?
2. When R0 is a refresh token but the hint is `access_token`, how does RFC 7009 require the server to handle it?
3. Why is a nonsensical hint not a reason to return `unsupported_token_type`?
4. How does a nonexistent token receiving 200 differ from invalid client authentication?
5. Why is valid client authentication still insufficient without checking token ownership?
6. Can PKCE replace client authentication at the revocation endpoint?
7. Does revoking a refresh token guarantee an already-issued JWT A0 immediately stops working at the RS?
8. How should a client handle 503 and timeouts?
9. When refresh and revoke on the same R0 happen concurrently, what transactional invariant is required?
10. How can you test hint fallback without a "false pass" caused by an already-revoked token?

## References

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): §2.1–2.2 on `token`, `token_type_hint`, client authentication, HTTP 200/503, and errors.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication, token types, and OAuth errors.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): `active` status and introspection.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): `revocation_endpoint` and auth methods metadata.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): protecting clients and refresh tokens.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OAuth2TokenRevocationEndpointConfigurer` and providers.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): revocation path and client authentication.
- [Spring Authorization Server 1.5.8 — Core Model](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2Authorization` and `OAuth2AuthorizationService`.
- [Spring Authorization Server 1.5.8 — OAuth2Authorization.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/OAuth2Authorization.Builder.html): `invalidate(OAuth2Token)`.
- [Spring Authorization Server 1.5.8 — OAuth2TokenRevocationAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenRevocationAuthenticationToken.html): `getToken()` and `getTokenTypeHint()`.
