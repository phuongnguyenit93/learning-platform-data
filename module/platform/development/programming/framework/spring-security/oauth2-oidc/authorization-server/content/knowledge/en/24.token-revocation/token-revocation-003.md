# Checking Token Ownership Before Revocation

The Token Revocation Endpoint allows an OAuth client to ask the Authorization Server to invalidate an access token or refresh token that the client no longer needs. This endpoint accepts a high-security-value credential: the token to be revoked. Therefore, before modifying authorization state, the Authorization Server must authenticate the client calling the endpoint and verify that the token was actually issued to that client.

**Token ownership in the context of revocation is the relationship between the token and the OAuth client to which the Authorization Server issued that token.** In Spring Authorization Server, this relationship is stored via `OAuth2Authorization.registeredClientId`. When handling a request, the server compares this value against the internal ID of the `RegisteredClient` bound to the authenticated client. If the two IDs do not match, the server must not invalidate the token.

This check prevents client A from using the Token Revocation Endpoint to invalidate client B's tokens. It also prevents using `principalName`, subject, scopes, or request-supplied data as proof of token ownership.

This lesson belongs to the **Revocation** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, aimed at learning how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot.

After this lesson, you will be able to:

- Distinguish between the authenticated client, the client issued the token, and the resource owner.
- Explain the relationship between `RegisteredClient`, `OAuth2Authorization`, and stored tokens.
- Verify token ownership before any revocation operation.
- Understand the behavior of Spring Authorization Server's `OAuth2TokenRevocationAuthenticationProvider`.
- Handle nonexistent tokens, already-revoked tokens, and tokens belonging to another client per RFC 7009.
- Design policies for public clients, confidential clients, and administrative revocation permissions.
- Test ownership boundaries, race condition handling, token families, and revocation state propagation.

## 1. Why Must Token Ownership Be Checked?

Suppose an Authorization Server issues tokens for two clients:

- `orders-web` is an ordering application.
- `billing-worker` is a payment processing service.

Each token is issued within an authorization tied to a specific client. If `orders-web` learns or guesses `billing-worker`'s token, it must not be permitted to request revocation of that token.

```mermaid
flowchart TD
    AS["Authorization Server"] --> A["Authorization A<br/>registeredClientId = orders-web"]
    AS --> B["Authorization B<br/>registeredClientId = billing-worker"]
    A --> TA["Access/Refresh token A"]
    B --> TB["Access/Refresh token B"]
    C["Authenticated client<br/>orders-web"] --> REQ["POST /oauth2/revoke<br/>token = token B"]
    REQ --> CHECK{"Does Token B belong to<br/>orders-web?"}
    TB --> CHECK
    CHECK -->|No| DENY["Reject revocation<br/>do not modify token B"]
    CHECK -->|Yes| REVOKE["Invalidate token"]
```

If the server simply looks up the token by string and immediately marks it revoked, any client able to submit a valid token could disrupt another client's sessions. This behavior creates an authorization vulnerability right at the credential management endpoint.

Checking ownership ensures:

1. The request is bound to a client authenticated or validly identified according to its client type.
2. The token is found in the authorization store.
3. The authorization containing that token was issued to the exact client requesting revocation.
4. Only after ownership is valid does the server modify the state of the token or token family.

**Knowing a token does not mean owning the token.** A bearer token string can be leaked through logs, telemetry, browser storage, proxies, or other systems. The token value is lookup data, not proof that the client is authorized to revoke it.

## 2. Distinguishing Client, Resource Owner, and Token Owner

Multiple identities appear together in an authorization in OAuth. They should not be conflated into a single concept.

| Component | Meaning | Role in Ownership Check |
| --- | --- | --- |
| `RegisteredClient` | A client registered at the Authorization Server. | The client identity used to match against the token owner. |
| `OAuth2ClientAuthenticationToken` | Authentication representing the client after successful client authentication. | Provides the requester's `RegisteredClient`. |
| `OAuth2Authorization` | Authorization state granted to a client/principal. | Holds `registeredClientId`, `principalName`, grant, scopes, and token metadata. |
| `principalName` | Identity of the resource owner or client depending on the grant. | Not the client's ownership key. |
| Resource owner | User who granted permission in the authorization flow. | May manage consent/delegation via a separate flow; is not automatically the client calling the revocation endpoint. |
| Access/refresh token | Credential issued within the authorization. | Must be traced back to the authorization and the client issued the token. |

Example with authorization code:

- The logged-in resource owner is `alice`.
- The client is `orders-web`.
- The authorization is stored with `orders-web`'s `registeredClientId` and `principalName` set to `alice`.
- The access token is issued to `orders-web` under Alice's authorization.

`alice` is the subject who authorized access, but the request to the RFC 7009 revocation endpoint is sent by the OAuth client. The server must check whether the authenticated client matches the authorization's client.

With `client_credentials`, `principalName` may represent the client/service principal. Even so, the field used to check ownership remains `registeredClientId`, because it links the authorization to the specific registration.

## 3. How Ownership Is Stored in the Spring Authorization Server Model

`OAuth2Authorization` contains key data:

| Field | Meaning |
| --- | --- |
| `id` | Unique ID of the authorization. |
| `registeredClientId` | Internal ID of the `RegisteredClient` granted the authorization. |
| `principalName` | Principal name (resource owner or client). |
| `authorizationGrantType` | Grant used to create the authorization. |
| `authorizedScopes` | Granted scopes. |
| `tokens` | Access token, refresh token, authorization code, and corresponding metadata. |
| `attributes` | Additional information from the authorization flow. |

Among these, `registeredClientId` is the ownership link key to verify. It is the value corresponding to `RegisteredClient.getId()`, **not** `RegisteredClient.getClientId()`.

Example:

```java
RegisteredClient registeredClient = RegisteredClient
    .withId("client-record-91")
    .clientId("orders-web")
    .clientSecret("{bcrypt}...")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://orders.example.com/login/oauth2/code/app")
    .scope("orders.read")
    .build();

OAuth2Authorization authorization = OAuth2Authorization
    .withRegisteredClient(registeredClient)
    .principalName("alice")
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .authorizedScopes(Set.of("orders.read"))
    .build();
```

In this example, the authorization is linked to internal ID `client-record-91`. When the client authenticates as `orders-web`, the server retrieves the corresponding `RegisteredClient` and compares `registeredClient.getId()` with `authorization.getRegisteredClientId()`.

Do not make the wrong comparison:

- `registeredClient.getId()` is the internal registration key.
- `registeredClient.getClientId()` is the identifier the client uses in the protocol.
- `authorization.getPrincipalName()` is the principal name, not the client ID.
- `authorization.getAuthorizedScopes()` represents granted permissions, not proof of ownership.

Two clients may request the same scope or share the same resource owner. That does not make their authorizations the same.

## 4. Token Revocation Endpoint Processing Flow

Per RFC 7009, the client sends an HTTP POST to the revocation endpoint with the token to revoke and an optional `token_type_hint`. The request also includes client authentication information according to the client type.

Example:

```http
POST /oauth2/revoke HTTP/1.1
Host: login.example.com
Authorization: Basic b3JkZXJzLXdlYjpzZWNyZXQ=
Content-Type: application/x-www-form-urlencoded

token=<TOKEN_VALUE>&token_type_hint=refresh_token
```

This is an illustrative request; tokens and credentials must be protected and never written to logs. The endpoint must use HTTPS because the request transmits high-security-value credentials.

Processing flow:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant F as Revocation Endpoint Filter
    participant P as Revocation AuthenticationProvider
    participant S as OAuth2AuthorizationService

    C->>F: POST token + token_type_hint
    F->>P: OAuth2TokenRevocationAuthenticationToken
    P->>P: Authenticate/identify client
    P->>S: findByToken(token)
    S-->>P: OAuth2Authorization or not found
    P->>P: Compare registeredClientId
    alt Client owns token
        P->>P: Verify token and state
        P->>S: Save invalidated authorization
        P-->>F: Revocation succeeded
        F-->>C: HTTP 200
    else Token does not exist or is no longer valid
        P-->>F: Handle no-op per protocol
        F-->>C: HTTP 200
    else Token belongs to another client
        P-->>F: Reject ownership
        F-->>C: OAuth error
    end
```

Steps must be executed in order:

1. Parse the request and extract `token` and `token_type_hint`.
2. Authenticate the client or identify a public client per configuration.
3. Locate the authorization containing the token.
4. Match the requesting client against the authorization's `registeredClientId`.
5. Inspect the located token and its state.
6. Only when ownership is valid, invalidate the token and save the authorization.
7. Return the response per RFC 7009 and the endpoint's error policy.

**Never invalidate first and check the client afterward.** The ownership check must precede any side effects such as marking the token invalidated, revoking related refresh tokens, disabling the authorization, or emitting revocation events.

## 5. Ownership Rules per RFC 7009

RFC 7009 §2.1 specifies that the Authorization Server authenticates the confidential client's credentials, then verifies whether the token was issued to the client requesting revocation. If validation fails, the request is rejected. The Security Considerations section also states that the revoked token must belong to the client making the request.

### 5.1. Confidential Clients

A confidential client must authenticate using its registered method, for example:

- `client_secret_basic`
- `client_secret_post`
- `private_key_jwt`
- `client_secret_jwt`
- `tls_client_auth`
- `self_signed_tls_client_auth`

After authentication succeeds, the server obtains `RegisteredClient` from the authentication principal. Do not use `client_id` from the body as the authenticated identity when the client authentication filter has already provided a trusted principal.

### 5.2. Public Clients

A public client unable to keep a secret credential can identify itself with `client_id` under the public client mechanism permitted by RFC 7009. The Authorization Server must still validate that `client_id` is valid and match the token against that public client's registration.

`client_id` is not a secret. Knowing a public client ID does not allow a party to revoke a confidential client's or another public client's tokens.

A public client may require PKCE in the authorization code flow to protect authorization codes. PKCE does not replace the ownership check at the revocation endpoint; the server must still bind the token to the proper `RegisteredClient`.

### 5.3. Invalid Client Credentials vs. Token Owned by Another Client

Two scenarios must be distinguished:

| Scenario | Meaning | Handling |
| --- | --- | --- |
| Client authentication fails | Invalid credentials, invalid client, or client is not allowed to use the submitted method. | Reject authentication, typically `401 invalid_client` per OAuth client authentication. |
| Client authenticates validly, but token belongs to another client | Requester does not have authority to revoke that token's authorization. | Do not invalidate token; reject ownership per policy/implementation. |
| Token does not exist or is not found | Server has no matching authorization. | Return `200 OK` per RFC 7009, without revealing whether the token exists. |
| Token is already revoked/expired | Token is no longer active. | Handle idempotently; a success response does not reactivate the token. |

In Spring Authorization Server, the default revocation provider checks the authenticated client and compares the internal ID of `RegisteredClient` with `OAuth2Authorization.registeredClientId`. When another client owns the token, the current default provider rejects with the OAuth error `invalid_client`. Verify the exact behavior for the library version your application uses.

## 6. token_type_hint Is Only a Lookup Hint

RFC 7009 defines two common values:

- `access_token`
- `refresh_token`

A client may send a hint so the Authorization Server can optimize token lookup. The hint is not proof that the token actually belongs to the declared type.

If the token cannot be found using the hint, the server must expand the search across supported token types. The server may also ignore the hint if it can recognize the token on its own.

Example client request:

```http
POST /oauth2/revoke
Content-Type: application/x-www-form-urlencoded

token=<TOKEN_VALUE>&token_type_hint=access_token
```

If the actual value is a refresh token, the server must not assume the token does not exist merely because the access token lookup failed.

In Spring Authorization Server, `OAuth2AuthorizationService.findByToken(token, tokenType)` is the authorization query point. The default provider can search by token without restricting the type (`tokenType` is `null`), thereby avoiding full dependence on the hint. When implementing custom persistence, ensure RFC 7009-equivalent fallback.

Do not use `token_type_hint` to pick the client or bypass the ownership check. A client cannot turn another client's token into its own by declaring a different hint.

## 7. Algorithm for Checking Ownership Before Invalidating

The logic can be described in pseudocode:

```text
request = parseRevocationRequest()
requester = authenticateOrIdentifyClient(request)

authorization = authorizationService.findByToken(
    request.token,
    resolveTokenTypeHint(request.token_type_hint)
)

if authorization == null:
    return HTTP 200

if authorization.registeredClientId != requester.registeredClient.id:
    reject ownership
    do not mutate authorization
    return OAuth error

token = authorization.findToken(request.token)

if token == null or token is not active:
    return HTTP 200

updatedAuthorization = invalidateAccordingToPolicy(
    authorization,
    token
)

authorizationService.save(updatedAuthorization)
return HTTP 200
```

Several points must be preserved when translating pseudocode into real code:

- `requester` comes from successful client authentication.
- `authorization.registeredClientId` is the registration's internal ID.
- The token is looked up from the authorization store, not by inferring the owner from the token string.
- If the token is not found, do not return an error disclosing whether the token exists.
- If the token is found but owned by another client, do not call `invalidate(...)`, do not save the authorization, and do not trigger side effects.
- If the token is already invalidated or expired, the request can be handled idempotently.
- If the token is active and the owner matches, apply the policy to revoke the token and related tokens.

### 7.1. Compare Internal IDs, Do Not Compare principalName

Principally correct example:

```java
boolean ownsAuthorization(
        OAuth2ClientAuthenticationToken clientPrincipal,
        OAuth2Authorization authorization) {

    RegisteredClient requester = clientPrincipal.getRegisteredClient();

    return requester != null
        && requester.getId().equals(authorization.getRegisteredClientId());
}
```

This is an illustrative helper for the ownership predicate. In a real endpoint, only invoke it after the client principal has been authenticated; never accept a request-forged `OAuth2ClientAuthenticationToken`.

Wrong example:

```java
// Wrong: two clients can share the same principalName.
if (authorization.getPrincipalName().equals(requester.getName())) {
    authorizationService.save(authorization.invalidate(token));
}
```

`principalName` is typically the resource owner in the authorization code flow. Alice can grant access to multiple different clients; sharing `principalName = alice` does not allow client A to revoke client B's token.

### 7.2. Do Not Use Scope as Ownership

Two clients can both be granted `orders.read`. Scopes describe resource access permissions, not token management rights. Do not write logic like:

```java
// Wrong: the same scope does not prove the same client.
if (authorization.getAuthorizedScopes().contains("orders.read")) {
    revoke(token);
}
```

Ownership must rely on the stored authorization-client relationship.

## 8. Default Behavior in Spring Authorization Server

Spring Authorization Server exposes the Token Revocation Endpoint via `OAuth2TokenRevocationEndpointConfigurer`. The endpoint filter converts the HTTP request into an `OAuth2TokenRevocationAuthenticationToken`, and then the provider handles authentication and revocation.

Related components:

| Component | Responsibility |
| --- | --- |
| `OAuth2TokenRevocationEndpointFilter` | Receives HTTP requests and coordinates endpoint processing. |
| `OAuth2TokenRevocationAuthenticationConverter` | Converts request parameters into an authentication request object. |
| `OAuth2TokenRevocationAuthenticationToken` | Carries the token and token type hint during processing. |
| `OAuth2TokenRevocationAuthenticationProvider` | Authenticates the requester, finds the authorization, checks client ownership, and invalidates the token. |
| `OAuth2AuthorizationService` | Looks up and persists authorization/token state. |
| `RegisteredClientRepository` | Provides authenticated client registrations. |

The default provider performs critical ownership logic:

1. Extracts the authenticated client from the revocation authentication context.
2. Retrieves the corresponding `RegisteredClient`.
3. Looks up the `OAuth2Authorization` containing the token.
4. Compares `RegisteredClient.getId()` with `OAuth2Authorization.getRegisteredClientId()`.
5. If they differ, rejects with an OAuth error instead of invalidating the token.
6. If they match, locates the token metadata and invalidates the corresponding token.
7. Saves the updated authorization.

This means an application using the default provider and standard `OAuth2AuthorizationService` already has basic ownership verification. However, the application must still ensure accurate persistence lookups, proper client authentication, and that no custom provider bypasses the ownership condition.

### 8.1. Endpoint Configuration and Extension Points

You can configure the endpoint through the Authorization Server configurer:

```java
@Bean
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.tokenRevocationEndpoint(revocation ->
                revocation
                    .revocationRequestConverters(converters -> {
                        // Keep the default converter or add converters
                        // per controlled protocol extensions.
                    })
                    .authenticationProviders(providers -> {
                        // Keep the default provider with ownership check.
                        // Only change when authentication + ownership policy
                        // is fully implemented and tested.
                    })
            )
        );

    return http.build();
}
```

This example illustrates the endpoint's extension points. In production configuration, ensure other filter chains do not accidentally allow access to the revocation endpoint while bypassing client authentication. Do not remove the default provider unless a replacement custom provider implements all equivalent checks.

### 8.2. When Is a Custom AuthenticationProvider Needed?

A custom provider is only needed if business requirements go beyond default behavior, for example:

- A delegated client model with explicitly governed parent/child relationships.
- Separately granted administrative revocation permissions.
- Auditing or cascade revocation across an authorization family.
- A custom authorization store requiring special transactions or lookups.

If adding delegated permissions, enforce a clear policy—for instance, client B is authorized to revoke client A's tokens within a specific tenant or authorization group. Do not widen permissions with loose conditions such as the same principal name, a request-supplied tenant header, or the same scope.

## 9. Nonexistent Tokens, Already-Revoked Tokens, and Tokens Owned by Another Client

These three situations have different security goals and responses.

| Situation | Authorization Found? | Ownership? | Invalidate? | Typical Response |
| --- | --- | --- | --- | --- |
| Token does not exist | No | Unknown | No | `200 OK` |
| Token expired/already revoked | Possibly | May match | No change needed | `200 OK` |
| Active token of requester | Yes | Yes | Yes | `200 OK` |
| Active token of another client | Yes | No | **No** | OAuth error per RFC/implementation; default SAS uses `invalid_client` |

RFC 7009 returns `200 OK` when a token is successfully revoked or when the submitted token is invalid/nonexistent. This spares clients from having to distinguish expired, already revoked, or never-issued tokens.

A token belonging to another client is a failed ownership validation case, which RFC 7009 §2.1 describes as a request that must be rejected with an error returned to the client. Do not merge this case with nonexistent tokens or accidentally revoke another client's token.

Do not return a response body containing the owning client ID, principal name, scopes, token expiration, or detailed internal reasons. Error responses must follow the OAuth endpoint contract and disclose no more data than necessary.

## 10. Revoking Related Tokens Within the Same Authorization

An authorization may contain both an access token and a refresh token. The revocation policy must define whether revoking one token invalidates related tokens.

RFC 7009 §2.1 specifies:

- When the submitted token is a refresh token and the AS supports access token revocation, the AS **SHOULD** invalidate access tokens based on the same authorization grant.
- When the submitted token is an access token, the AS **MAY** revoke the corresponding refresh token.
- Policy may revoke additional related tokens or the authorization grant if system design requires it.

This is a cascade policy applied after ownership has been verified. Never cascade across different authorizations merely because they share a resource owner, client name, or scope.

```mermaid
flowchart TD
    REQUEST["Revocation request"] --> OWNER{"Requester owns authorization?"}
    OWNER -->|No| STOP["Do not modify any token"]
    OWNER -->|Yes| TYPE{"Submitted token"}
    TYPE -->|Refresh token| REF["Invalidate refresh token"]
    REF --> ACCESS["Per RFC: SHOULD invalidate<br/>access tokens in same grant"]
    TYPE -->|Access token| AT["Invalidate access token"]
    AT --> MAY["Per policy: MAY invalidate<br/>corresponding refresh token"]
    ACCESS --> SAVE["Save authorization atomically"]
    MAY --> SAVE
```

In the current Spring Authorization Server source, the default provider looks up the authorization with `findByToken(token, null)`, verifies ownership, and calls `invalidate(...)` on the located token. Therefore, do not assume every version/configuration automatically cascades across the entire token family. RFC 7009 recommends (SHOULD) revoking access tokens in the same grant when a refresh token is revoked and the AS supports access-token revocation. Check the exact version in use and write integration tests verifying that related access tokens are also invalidated; if policy requires cascading and the implementation does not do it, add handling after the ownership check within the same transaction.

## 11. Race Conditions and Authorization Store Consistency

The ownership check must execute within a transaction or consistency mechanism aligned with updating the token.

Example of two concurrent requests:

- Request A from the rightful client submits a token to revoke.
- Request B from another process performs a token refresh or updates the authorization.
- If both read/write operations are uncoordinated, a lost update can occur or a new token can still be issued after the authorization was revoked.

Recommendations:

1. Use a transaction for lookup, ownership check, and persistence update when the storage supports it.
2. Consider optimistic locking/version column or row-level locking when concurrent refresh/revoke can happen.
3. Do not perform the ownership check on a stale replica and then write to the primary without re-checking the version.
4. Publish revocation events after the transaction commits; consumers must be idempotent.
5. Synchronize caches/token state at Resource Servers per SLA.
6. With refresh-token rotation, ensure the refresh provider does not reuse revoked authorization state.

If ownership does not match, the transaction must not write any token changes. Do not emit revocation events or evict caches for an authorization belonging to another client.

## 12. JWTs, Opaque Tokens, and Revocation Effectiveness

The ownership check occurs at the Authorization Server. Whether the Resource Server detects that a token has been revoked depends on token format.

| Token Format | Resource Server Verification | Impact of Revocation |
| --- | --- | --- |
| Opaque/reference token | Typically calls introspection or checks centralized state. | Can reflect revoked status quickly, depending on caching and consistency. |
| Self-contained JWT | Verifies signature and claims offline. | Previously issued JWTs may continue to be accepted until `exp` if the API does not check a denylist/introspection. |

For offline JWTs, updating `OAuth2Authorization` at the AS alone does not inform every Resource Server that the token was revoked. If near-immediate revocation is required, additional mechanisms are needed, such as:

- Short-lived access tokens.
- Token introspection or a centralized authorization check.
- A denylist keyed by `jti` or a normalized token identifier.
- Event-driven cache invalidation with delivery/ordering guarantees.
- A token version or authorization version checked by the Resource Server.

Do not use raw tokens as cache keys/log keys unnecessarily. For JWTs, `jti` is only useful if the system has a corresponding lookup/denylist mechanism; merely having the claim present does not implement revocation.

## 13. Protecting the Endpoint Against Token Guessing and Abuse

Because the revocation endpoint accepts tokens from clients, it can be abused to guess tokens or overload the authorization store.

Measures to consider:

- Require proper client authentication/identification per client type.
- Use HTTPS and obtain the endpoint URI from trusted metadata/documentation.
- Do not accept tokens via query string; use a POST body with `application/x-www-form-urlencoded`.
- Never log raw tokens, refresh tokens, or client secrets in application logs, tracing, or error messages.
- Rate limit by client, IP, and appropriate abuse signals; avoid rate limiting solely by token, since attackers can submit random tokens.
- Use high-entropy tokens and properly indexed storage lookups.
- Bound token input sizes and the number of fallback lookups.
- Do not allow an arbitrary token type hint to trigger unbounded queries.
- Return responses that do not reveal whether a token does not exist or which client owns it.
- Audit revocation events using the authorization ID, authenticated client ID, token type, and outcome; avoid storing raw credentials.

RFC 7009 notes that the revocation endpoint can be used to guess tokens and cause denial of service. Ownership checking is necessary, but must be paired with rate limiting and persistence-layer protection.

## 14. Testing Token Ownership

Ownership tests must verify both the HTTP outcome and **the authorization state after the request**. Asserting only the response code is insufficient; an endpoint could return an error after having mistakenly invalidated the token earlier.

### 14.1. Test Matrix

| Scenario | Expected Result |
| --- | --- |
| Client A authenticates and revokes A's access token | Token A is invalidated. |
| Client A authenticates and revokes A's refresh token | Refresh token A is invalidated; access tokens cascade per policy/RFC. |
| Client A submits Client B's token | Ownership rejected; Authorization B unchanged. |
| Client B submits Client A's token | Ownership rejected; Authorization A unchanged. |
| Wrong client secret | `invalid_client`; no lookup or mutation for unauthenticated requester. |
| Public client sends valid client_id and its own token | Request processed per public client policy. |
| Public client submits another client's token | Ownership mismatch; other token not revoked. |
| Nonexistent token | `200 OK`; does not disclose whether token exists. |
| Already revoked token | `200 OK` per idempotent handling. |
| Expired token | Not active; response does not leak internal state. |
| Correct `token_type_hint` | Optimized lookup for the right token type. |
| Wrong `token_type_hint` but token belongs to another type | Server falls back per RFC 7009. |
| Same principalName across two different clients | Must not be treated as the same owner. |
| Same scope across two different clients | Must not be treated as the same owner. |
| Token refresh rotation just occurred | Revoke and refresh produce consistent state per transaction policy. |
| Two concurrent revoke requests for the same token | Idempotent result; does not restore active state. |
| Token in another tenant with same client ID | Only revoke if authorization ownership/policy truly permits; never trust tenant headers. |
| Custom provider registered | Preserves client authentication and ownership validation. |
| Database lookup returns wrong authorization due to index bug | Test verifies token value matches actual token metadata before mutating. |
| Offline JWT after revocation | Resource Server handles per designed TTL/denylist/introspection policy. |

### 14.2. Integration Test with Two Clients

Setup:

- Client A: `orders-web`.
- Client B: `billing-worker`.
- Authorization A contains token A and A's `registeredClientId`.
- Authorization B contains token B and B's `registeredClientId`.

Steps:

1. Authenticate Client A.
2. Send token A to the revocation endpoint.
3. Verify token A is marked invalidated.
4. Recreate Authorization B or use an active token B.
5. Still using Client A, send token B to the endpoint.
6. Verify the request is rejected per ownership policy.
7. Re-read Authorization B and assert the access/refresh tokens remain active.
8. Authenticate Client B and send token B.
9. Verify token B is invalidated.
10. Verify audit logs contain no raw tokens.

### 14.3. Testing Without Relying on principalName

Create two authorizations:

- Authorization A: `registeredClientId = client-A`, `principalName = alice`.
- Authorization B: `registeredClientId = client-B`, `principalName = alice`.

Then authenticate Client A and submit token B. The outcome must be an ownership mismatch even though both authorizations share `principalName = alice`.

This test catches the common mistake of using the resource owner name as a substitute for client ownership.

## 15. Implementation Checklist

- [ ] Revocation endpoint accepts POST over HTTPS only.
- [ ] Clients are authenticated/identified properly per confidential or public client policy.
- [ ] Requester is taken from the authenticated client principal, not arbitrary body/header fields.
- [ ] Tokens are looked up in `OAuth2AuthorizationService`.
- [ ] Ownership check compares `RegisteredClient.getId()` against `OAuth2Authorization.getRegisteredClientId()`.
- [ ] Ownership check runs before any `invalidate`, `save`, event emission, or cache mutation.
- [ ] `principalName`, scopes, subject DN, or tenant headers are never used as proof of ownership.
- [ ] Nonexistent and already-revoked tokens are handled idempotently per RFC 7009.
- [ ] Tokens belonging to another client are rejected; the owner's authorization remains unchanged.
- [ ] `token_type_hint` is used only for lookup optimization with RFC-compliant fallback.
- [ ] Cascade policy for access/refresh tokens in the same authorization is clearly defined.
- [ ] Custom providers preserve client authentication, ownership checks, and protocol response semantics.
- [ ] Transactions/locking prevent races between revoke and refresh.
- [ ] Resource Server caches/introspection/JWTs have clear revocation propagation policies.
- [ ] Rate limiting and lookup bounds protect the endpoint from token guessing/DoS.
- [ ] Logs/audits never store raw access tokens, refresh tokens, or client secrets.
- [ ] Integration tests include Client A attempting to revoke Client B's token and verifying token B remains active.

**Remember:** The Authorization Server may revoke a token only after verifying that the requester is the client to which that token was issued. In Spring Authorization Server, use `OAuth2Authorization.registeredClientId` and the internal ID of `RegisteredClient` as the basis for ownership. The token value only locates the authorization; `principalName`, scopes, and request data cannot substitute for this check.

**References:**

- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): §2.1 requires verifying client and token ownership; §2.2 specifies the response; §5 discusses token guessing.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Revocation Endpoint, converter, authentication provider, and response handler.
- [Spring Authorization Server — Core Model and Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, `OAuth2AuthorizationService`, and token state.
- [OAuth2TokenRevocationAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/docs/current/api/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenRevocationAuthenticationProvider.html): default provider for revocation.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): client authentication and client types.
