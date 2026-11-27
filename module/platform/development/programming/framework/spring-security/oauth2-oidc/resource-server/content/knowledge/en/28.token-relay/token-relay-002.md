# Relaying an Existing Token Differs from Obtaining a New Token or Refreshing a Token

In an OAuth 2.0 system with a gateway, backend-for-frontend (BFF), or multiple microservices, a request often passes through several components before reaching the final API. When the Orders API needs to call the Inventory API or a gateway forwards a request to a downstream service, the application must decide **whether to use the existing access token, request a new token from the Authorization Server, or refresh an expired token**.

These three actions have different purposes and semantics:

- **Token relay:** forwarding the exact access token that was received. The token value does not change; downstream receives the same credential with the same claims, audience, scope, expiration, and token binding.
- **Obtaining/acquiring a new token:** requesting the Authorization Server to issue a new access token under a grant or authorization flow. The new token may represent the client/service or a user, depending on the grant.
- **Refreshing a token (refresh):** using a refresh token to request a replacement access token when the current access token is expiring or expired, under the permissions and policy previously granted.

In addition to these three, there is **OAuth 2.0 Token Exchange**: using an existing token as a subject/actor input so the Authorization Server issues a different token intended for a downstream resource or delegation context. Token exchange is neither token relay nor a refresh grant.

The most important point: **relay preserves the identity and scope of the current token; obtain/refresh/exchange creates or returns a different access token as decided by the Authorization Server**. Choosing the wrong mechanism can lose user context, send a token with the wrong audience, unintentionally expand privileges, or turn a service-to-service call into an action under a user's identity.

This lesson belongs to the **Token Relay** chapter in the **Spring Security OAuth 2.0 OIDC Resource Server** module. It explains request flows, how to distinguish the grants, choosing between relay and a new token, how to use Spring Security/Spring Cloud Gateway, as well as risks and testing approaches.

> Token data, issuers, keys, and client IDs in these examples are simulated. The goal is to clearly understand the boundary between an existing credential and a new credential issued by the Authorization Server.

## 1. A Request Crossing Multiple Services

Suppose a user logs into Shop Web, calls the Orders API, and the Orders API needs to query the Inventory API:

~~~text
Browser / Shop Web
        |
        | access token T-user
        v
API Gateway
        |
        | token relay?
        v
Orders API
        |
        | call downstream Inventory API
        v
Inventory API
~~~

At each hop, the intermediary component can:

1. **Relay** the received token.
2. **Use the service's own token** to call downstream.
3. **Refresh** the access token if a valid refresh token is available.
4. **Exchange** the incoming token for a new token with the appropriate audience/scope/actor.

There is no single right choice for every system. You must consider **who is the subject of the action**, **whom downstream needs to trust**, **which resource the token is intended for**, and **which grants the Authorization Server supports**.

### 1.1. Example of Relaying an Existing Token

The browser sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: shop.example.test
Authorization: Bearer eyJ...T_USER
~~~

The gateway forwards the exact access token to the Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.internal
Authorization: Bearer eyJ...T_USER
~~~

The value after the scheme in both requests is **the exact same token string**. The gateway does not change the subject, scope, audience, issuer, expiry, or signature. The gateway merely forwards the credential per policy.

### 1.2. Example of Obtaining a New Token with Client Credentials

The Orders API calls the Authorization Server using its service identity:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CLIENT_CREDENTIALS>

grant_type=client_credentials&scope=inventory.read
~~~

The Authorization Server returns a new token intended for the Inventory API:

~~~json
{
  "access_token": "<NEW_SERVICE_ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

This is a **new token**. The token typically represents the Orders service/client and does not automatically retain the identity of the user who called the Orders API.

### 1.3. Example of Refreshing a Token

The client has access token T1 and refresh token R:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN_R>&
client_id=shop-bff
~~~

The Authorization Server can return a new access token T2 and refresh token R2 if rotation is applied. T2 is a new credential; it may retain the authorization grant corresponding to R, but it must not be assumed that every claim, audience, scope, or binding will be identical to T1.

## 2. Distinguishing the Four Actions

| Action | Primary Input | Result | Identity Typically Represented | Does the Token Change? |
|---|---|---|---|---|
| **Relay** | Existing access token | Sends the same token downstream | Subject/caller in the original token | **No** |
| **Obtain a new token** | Authorization code, client credentials, or other grant | New access token | User or service depending on the grant | **Yes** |
| **Refresh** | Refresh token | Replacement access token | Previously issued authorization grant | **Yes** |
| **Token exchange** | Subject token and optionally actor token | New access token for target resource/delegation | Subject/actor per exchange policy | **Yes** |

### 2.1. Relay Is an HTTP-Layer Action

Relay typically just means: taking the existing token from the SecurityContext/session/authorized client and attaching it to the downstream request. It does not ask the Authorization Server to issue a new token.

~~~text
incoming access token
       |
       v
extract token
       |
       v
Authorization: Bearer <same token>
       |
       v
downstream API
~~~

If the token is expired or has the wrong audience, relay still sends that exact token; downstream may reject it. Relay does not mint a new token, modify claims, or add permissions.

### 2.2. Obtaining a New Token Is an Authorization Decision

The client asks the Authorization Server to issue a token under a permitted grant. The AS checks client authentication, grant, consent, user context, scopes, resource/audience, and policy. Issuing a token is not merely copying an existing credential.

### 2.3. Refresh Maintains an Existing Grant

A refresh token is used at the token endpoint to request a replacement access token. It is not an access token for calling a Resource Server. Refresh does not typically mean "escalating privileges" or "switching to another API arbitrarily"; the AS still controls scope/resource and may require the user to re-authenticate or re-consent.

### 2.4. Token Exchange Creates a Token for Another Delegation/Resource

Token Exchange (RFC 8693) lets a client send a subject token, optionally along with an actor token, and request a token suited for a new audience/resource or delegation context. This can be used when the Orders API needs to call the Inventory API **with delegated user context**, but the incoming token was not issued for the Inventory API.

Token exchange can only be used if the Authorization Server supports it and policy permits it. Do not assume every OAuth provider implements RFC 8693 or shares the same semantics.

## 3. The Deciding Question: Whom Does Downstream Need to Trust?

Before writing code, determine which identity downstream needs to see.

### 3.1. Downstream Needs to Act Under the User's Identity

For example, user Alice calls:

~~~text
GET /api/orders/42
~~~

The Orders API needs to call the Pricing API, and the Pricing API needs to check Alice's permissions. You can:

- Relay Alice's access token if the token was issued for both Orders/Pricing or the resource contract permits Pricing to accept it.
- Exchange Alice's token for an access token intended for the Pricing API, keeping Alice as the subject and Orders API as the actor if policy requires delegation.

If you relay a token whose audience is only for the Orders API, the Pricing API should rightly reject it. Do not modify the Pricing API to accept tokens not intended for it.

### 3.2. Downstream Needs Service Identity

For example, the Orders API needs inventory information for an internal calculation. The Inventory API only needs to know the caller is the Orders service:

~~~text
Orders service
    -- client credentials -->
Authorization Server
    -- service token aud=inventory-api -->
Orders service
    -- Authorization: Bearer <service token> -->
Inventory API
~~~

This is obtaining a token via Client Credentials, not relaying a user token. The Inventory API's audit log will reflect the service client; if user context must be recorded, the Orders API can pass a trusted business correlation/actor context per a dedicated design, without forging authentication claims.

### 3.3. Downstream Needs Both User and Service Context

A service may need to prove:

- **Subject:** user Alice initiated the action.
- **Actor:** the Orders API is making the downstream call on Alice's behalf.
- **Audience:** the token is intended for the Inventory API.
- **Scope:** only inventory read permission is granted.

Token exchange is a suitable mechanism if the Authorization Server supports subject/actor delegation. Simply relaying the current token may fail to convey the actor chain or the right audience.

### 3.4. Do Not Decide Solely Based on "Token Not Expired"

An unexpired token may:

- Be intended for a different API.
- Lack downstream scopes.
- Be issued to a client not permitted to call downstream.
- Be bound to a DPoP key or mTLS certificate that the downstream request does not satisfy.
- Lack the necessary actor/delegation context.

Therefore, "the token has not expired yet" is not sufficient reason to relay it.

## 4. Audience and Scope Determine Where a Token Can Be Relayed

Suppose the current access token is:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "alice",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

The token was issued for the Orders API and only has the order-reading scope. The Orders API forwards the exact token to the Inventory API:

~~~http
GET /internal/stock/sku-123 HTTP/1.1
Host: inventory.internal
Authorization: Bearer <SAME_ORDERS_TOKEN>
~~~

The Inventory API checks `aud` and sees the token is intended for the Orders API. It should reject this token, even though the signature and issuer are valid. If the Inventory API skips the audience check just because the request came from the internal network, the resource boundary is weakened.

### 4.1. Relay Cannot Add an Audience Itself

The Gateway or Orders API cannot edit the JWT payload:

~~~text
decode token
change aud from orders-api to inventory-api
encode token
~~~

If the token is a JWS, modifying claims invalidates the signature. If the token is opaque, the client cannot even inspect the claims inside. Only the Authorization Server or a trusted token-issuing mechanism can create a token with a new audience.

### 4.2. Relay Cannot Add Scopes Itself

If the token only has `orders.read`, adding `inventory.read` to a header or request context does not cause the Authorization Server to grant that permission. Scopes must be granted within the access token/authorization context and verified by the Resource Server.

### 4.3. Multi-Audience Tokens

If a token has:

~~~json
{
  "aud": [
    "https://api.example.test/orders",
    "https://api.example.test/inventory"
  ],
  "scope": "orders.read inventory.read"
}
~~~

then relaying it to the Inventory API can be valid if the issuer intentionally issues multi-resource tokens and policy permits it. However, a leaked token has a larger replay blast radius; many systems prefer per-resource tokens or token exchange to narrow permissions.

### 4.4. Relay Preserves Permissions Rather Than Reducing Them

A token with `orders.read orders.write admin` still carries those scopes when relayed. The gateway cannot "strip" `admin` from the token while preserving the signature. If downstream needs narrower permissions, request a new token with minimal scopes via token exchange or an appropriate grant.

## 5. Mechanism Selection Diagram

~~~mermaid
flowchart TD
    A["Have an existing access token"] --> B{"Can and may downstream receive this exact token?"}
    B -->|Yes| C["Relay the same access token"]
    B -->|No| D{"Does downstream need user/delegation identity?"}
    D -->|Yes| E{"Does the AS support Token Exchange / OBO?"}
    E -->|Yes| F["Exchange token for the downstream resource"]
    E -->|No| G["Redesign grant/delegation or require an appropriate user flow"]
    D -->|No, only service identity needed| H["Obtain a new service token via Client Credentials"]
    C --> I["Downstream still verifies aud, scope, expiry, binding"]
    F --> I
    H --> I
~~~

**Refresh** is a separate branch: if the access token needed for the same authorization context is expired/expiring and the client has a valid refresh token, use the refresh flow to get a replacement access token. Refresh is not a default way to switch audiences or turn a user token into a service token.

## 19. Operational and Design Rules for Token Relay

### 19.1. Identify the Token Owner and Downstream Resource

Before relaying, explicitly document:

~~~text
Token owner / subject:
    user, service, workload, or delegated subject

Current resource audience:
    API that accepted the inbound token

Downstream resource:
    API that will receive the outbound request

Required downstream scopes:
    minimum operations required

Token binding:
    Bearer, DPoP, mTLS, or provider-specific
~~~

If the current token was not issued for the downstream resource or does not satisfy the token binding, do not relay. Choose token exchange, client credentials, or another grant according to the identity downstream needs.

### 19.2. Preserve User Context Intentionally

When downstream must enforce authorization per user, you need one of two things:

- An inbound token already issued by the issuer for downstream containing the right permissions/delegation context; or
- A new token issued by the AS via token exchange/OBO, preserving the subject and representing the actor per policy.

Do not take a user ID from the request body and attach it to a header to simulate user context. If using a service token, downstream must understand the caller is the service; user attribution requires a separate authenticated and audited mechanism.

### 19.3. Use Service Tokens for Background Work

Scheduled jobs, message consumers, and asynchronous workers typically do not have a user request's SecurityContext. Do not try to relay a user token saved from a prior request. Use a workload/service identity with client credentials or an appropriate workload identity mechanism, minimal scopes, and the right resource audience.

If the work was initiated by a user and must maintain delegation, store a secure task authorization record or use a time-bounded delegation/token-exchange flow; do not hold onto a user access token as a long-lived credential for a job.

### 19.4. Cache Tokens by the Right Identity

Authorized-client storage/cache must distinguish at least:

- Client registration.
- Principal/service identity.
- Tenant/issuer in multi-tenant setups.
- Resource/audience or token context if the provider supports multiple resources.

Do not use a shared cache key across all users when the token carries user-specific permissions. Never return Alice's token for Bob's request just because both use the same client registration.

### 19.5. Token Relay and Logout/Revocation

Relay does not independently check revocation. With self-contained JWTs, downstream may accept a token until expiration unless introspection/denylist/short-lived-token strategies are in place. With opaque tokens, introspection can reflect active/revoked status per policy.

Logging out at the frontend does not automatically guarantee that every access token already relayed to microservices is immediately invalidated. Design access token lifetimes, refresh tokens, revocation, session invalidation, and downstream caches according to security requirements.

### 19.6. Do Not Keep Tokens Longer Than Necessary

Only store access/refresh tokens in the authorized-client store for the required lifecycle, protected by encryption-at-rest and access controls. Do not copy tokens into custom databases, distributed caches, or message payloads without a concrete need and security design.

### 19.7. Token Relay in Message-Driven Systems

Pushing raw Bearer tokens into Kafka/RabbitMQ messages can spread credentials across brokers, dead-letter queues, tracing, and consumer logs. It is usually better to pass business identity/correlation over a protected internal contract, or use workload identity on the consumer. If per-user delegation is truly needed, use a short-lived, narrowly scoped token delegation mechanism; do not treat messages as a safe place to store tokens by default.

## 20. Practical Request Comparison Examples

### 20.1. Relay: Token Unchanged

~~~http
# Inbound request
GET /api/orders/42 HTTP/1.1
Authorization: Bearer T1

# Outbound request
GET /internal/orders/42 HTTP/1.1
Authorization: Bearer T1
~~~

There is no token endpoint request. If downstream does not accept T1, relay cannot fix the error on its own.

### 20.2. Client Credentials: New Service Token

~~~http
# Orders service obtains a service token
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CREDENTIALS>

grant_type=client_credentials&scope=inventory.read

# Orders service calls Inventory API
GET /api/stock/sku-123 HTTP/1.1
Authorization: Bearer T_SERVICE
~~~

T_SERVICE is a token issued by the AS for the Orders service. It is not the user's T1.

### 20.3. Refresh: Replacement Access Token Within the Same Grant

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=R1

# AS response
{
  "access_token": "T2",
  "refresh_token": "R2",
  "token_type": "Bearer",
  "expires_in": 300
}
~~~

T2 replaces the old access token according to the grant and AS policy. The client must store R2 if refresh token rotation is enforced.

### 20.4. Token Exchange: New Token for a Different Resource

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CREDENTIALS>

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=T_USER_ORDERS&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=inventory-api&
scope=inventory.read
~~~

The AS can return T_INVENTORY with a new resource audience and delegation context if the client, subject token, and policy allow it. This is not default behavior for every issuer.

## 21. Pre-Implementation Mechanism Selection Checklist

### 21.1. Choose Relay When

- [ ] Downstream is permitted to receive the exact inbound token.
- [ ] Audience/resource binding matches downstream.
- [ ] The token has sufficient scopes without carrying overly broad permissions.
- [ ] Subject/actor context in the token matches what downstream needs.
- [ ] Token binding (Bearer/DPoP/mTLS) can be maintained on the outbound request.
- [ ] Outbound hosts are allowlisted and Authorization is not forwarded across redirects.
- [ ] Downstream still verifies the token itself.
- [ ] Logging/tracing/proxies redact credentials.

### 21.2. Choose Client Credentials When

- [ ] Downstream only needs to know the calling service/workload.
- [ ] User-specific delegation in the token is not needed.
- [ ] The service has a protected client registration/credential.
- [ ] The AS issues minimal audience and scopes for downstream.
- [ ] Authorized-client manager/cache is partitioned by service identity.

### 21.3. Choose Refresh When

- [ ] The client holds a valid refresh token belonging to the right authorized client.
- [ ] The access token needs replacement within an already-issued authorization grant.
- [ ] The refresh provider is configured in the authorized-client manager.
- [ ] Refresh token rotation/concurrency is handled safely.
- [ ] Refresh is not expected to add scopes or change audience outside AS policy.

### 21.4. Choose Token Exchange/OBO When

- [ ] Downstream needs user/delegation context.
- [ ] The inbound token is not intended for the downstream resource or needs different scopes.
- [ ] The Authorization Server supports RFC 8693/OBO or an equivalent extension.
- [ ] The subject token and actor/client are permitted to exchange per policy.
- [ ] Target audience/resource and minimal scopes are requested.
- [ ] Downstream verifies subject/actor and the new token.

### 21.5. Testing and Operations

- [ ] Relay test proves downstream receives the exact token T1.
- [ ] Relay test proves the token endpoint is not called and auto-refresh does not occur.
- [ ] Refresh test proves the token endpoint receives a refresh grant and returns T2.
- [ ] Client credentials test proves downstream receives the service identity.
- [ ] Exchange test proves subject/actor/audience/scope match the contract.
- [ ] Wrong-audience and insufficient-scope cases are tested separately.
- [ ] DPoP/mTLS-bound tokens have sender-constraint tests.
- [ ] Refresh token rotation and concurrent refresh are tested.
- [ ] Redirect/SSRF/header leakage are prevented.
- [ ] 401/403 responses are classified without infinite refresh or fallback.
- [ ] Metrics do not use raw tokens, subjects, or refresh tokens as labels.

## 22. Conclusion

The three operations often lumped together as "passing a token" are fundamentally distinct:

~~~text
TOKEN RELAY
    access token T1 → forward T1
    no token endpoint call
    subject/audience/scope/expiry unchanged

OBTAIN A NEW TOKEN
    grant/client authentication → Authorization Server
    → new access token for the granted identity and resource

REFRESH
    refresh token R1 → Authorization Server
    → replacement access token T2 within the existing grant

TOKEN EXCHANGE
    subject token (+ actor token) → Authorization Server
    → new access token for a different resource/delegation context
~~~

In Spring Security, `ServletBearerExchangeFilterFunction` and `ServerBearerExchangeFilterFunction` support relaying an existing Bearer token; Spring Cloud Gateway's `TokenRelay` forwards an access token from an OAuth2 authorized client; `OAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientManager` manage authorization and refreshing per grant/provider; and token exchange requires support from the Authorization Server and appropriate integration.

**Choose based on the identity and resource downstream needs to verify.** If downstream is permitted to receive the same token, relay is sufficient. If only service identity is needed, obtain a service token. If an access token needs replacement within the same grant, refresh. If a new token for a different resource is required while preserving user delegation, use token exchange/OBO where supported. Never modify tokens, add scopes via headers, skip audience checks, or fall back to service privileges just to make a request succeed.

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Cloud Gateway — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Security — ServletBearerExchangeFilterFunction Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServletBearerExchangeFilterFunction.html)
- [Spring Security — ServerBearerExchangeFilterFunction Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServerBearerExchangeFilterFunction.html)
- [Microsoft identity platform — OAuth 2.0 On-Behalf-Of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)

## 14. Security When Relaying Access Tokens

Relaying causes a principal's credential to traverse additional processes and network hops. Each new hop can become a point of leakage or abuse.

### 14.1. Only Relay to Trusted Downstream Services

Do not use a WebClient that automatically attaches an Authorization header to call arbitrary URLs:

~~~java
// ANTI-PATTERN: URL comes from user-controlled data.
webClient.get()
    .uri(userSuppliedUrl)
    .retrieve();
~~~

If a token relay filter is attached to this client, a user can arrange for the token to be sent to an unintended host. This is a combined credential exfiltration/SSRF risk.

You should:

- Use a fixed base URL for each downstream client.
- Allowlist appropriate scheme/host/port/path combinations.
- Do not forward Authorization across redirects to another origin.
- Do not use a global client with a bearer relay filter for arbitrary external URLs.
- Separate WebClients by trust boundary and credential policy.

### 14.2. Do Not Log the Authorization Header

An access token is a bearer credential. Do not log:

~~~text
Authorization: Bearer eyJ...
Authorization: DPoP eyJ...
refresh_token=...
~~~

Inspect access logs, reverse proxies, tracing, HTTP wiretap, exception messages, and CI output. Redact headers before storing them. Likewise, do not write refresh tokens to logs, as they can be long-lived and used to request new access tokens.

### 14.3. Limit Relay Hops and Service Scope

Relaying a user token across many services increases the blast radius if the token is leaked. Only relay to services that genuinely need user context. If downstream only needs an internal operation, a narrowly scoped service token is easier to constrain.

### 14.4. Do Not Trust Self-Asserted Identity Headers

If the Orders API relays a token to the Inventory API, the Inventory API must verify the token under its own trust policy. Do not replace it with:

~~~http
X-User-Id: alice
X-Roles: admin
~~~

Self-asserted identity headers from upstream may only be used within an internal trust boundary that has service-to-service authentication, header stripping, and explicit policy. They do not replace token verification in an independent Resource Server.

### 14.5. Token Relay Does Not Reduce Privileges

A token with multiple scopes keeps all of those scopes when relayed. The gateway cannot edit a JWT to remove permissions. If downstream only needs `inventory.read`, use a new token with minimal scope instead of relaying a user token containing broader permissions.

### 14.6. Do Not Forward All Inbound Headers

A gateway typically only needs to forward a defined set of headers. Do not copy all request headers downstream—especially proxy, cookie, host, authorization, or unnecessary identity headers. Define an explicit header allowlist policy and handle duplicate Authorization headers.

### 14.7. Do Not Use a User Token in a Background Job

A background job is no longer inside the user's request/security context. Do not save Alice's access token and reuse it hours later to run a batch job without fresh authorization. Use a service identity or a time-bounded, explicitly scoped delegation/task authorization mechanism.

## 15. Handling 401/403: Do Not Refresh or Relay Reflexively

HTTP status codes help diagnose issues, but not every error is solved by refreshing.

| Downstream Response | Possible Cause | How to Handle |
|---|---|---|
| 401 expired token | Access token expired | If an authorized client/refresh token exists, the manager can refresh per policy |
| 401 invalid signature/issuer | Token is not trusted | Fix issuer/key/config; refreshing may not resolve it |
| 401 wrong audience | Token intended for a different resource | Obtain/exchange a token for the right audience |
| 401 missing/invalid DPoP proof | Sender constraint not satisfied | Generate a valid proof or obtain an appropriate token; do not fall back to Bearer |
| 403 insufficient scope | Valid token but lacking permissions | Request the appropriate grant/scope or deny; refreshing does not add permissions |
| 403 tenant/owner policy | Business policy does not allow it | Handle authorization; do not refresh indefinitely |
| 5xx/timeout | Downstream/upstream error | Retry per idempotency/backoff; do not request a new token every time |

### 15.1. Do Not Refresh Indefinitely on 401

A client may attempt a single refresh when a token expires if a refresh token exists and the manager supports it. However, if the 401 response is caused by a wrong audience, wrong issuer, or revoked token, repeated refreshes will not fix the root cause and will add load to the Authorization Server.

Avoid:

~~~text
while downstream returns 401:
    refresh token
    retry request
~~~

Classify errors, limit retries, and do not repeat non-idempotent business requests without an idempotency strategy.

### 15.2. 403 Is Not a Refresh Signal

A 403 usually indicates the principal is authenticated but lacks permission or was denied by policy. Refreshing a token does not automatically increase scopes. If additional permissions are needed, an appropriate authorization/consent/admin process is required.

### 15.3. Relay Failure Must Not Automatically Fall Back to a Service Token

If relaying a user token downstream results in 403, automatically falling back to a service token can execute the user's request with the service's broader privileges. This is **privilege escalation/confused deputy**. A fallback may only be designed if the business logic explicitly defines which operations may run under service identity and auditing accurately records the actor.

## 16. Testing: Proving Relay, Refresh, and Obtain Are Three Distinct Paths

Tests should observe both the **token endpoint** and the **downstream request**, rather than merely asserting downstream returns 200.

### 16.1. Testing That Relay Preserves the Token

Fixture:

~~~text
Inbound access token = T1
Downstream mock server captures Authorization header
Token endpoint mock server records requests
~~~

Scenario:

1. Send a request into the application with `Authorization: Bearer T1`.
2. The application calls downstream via the bearer relay filter.
3. The mock downstream records the Authorization header.
4. Assert that the token value received downstream is exactly T1.
5. Assert that the token endpoint was not called.

Expected result:

~~~text
downstream Authorization = "Bearer " + T1
token endpoint calls = 0
~~~

This proves that relay **does not obtain a new token or refresh**.

### 16.2. Testing That Relay Does Not Auto-Refresh Expired Tokens

Create a token T1 that is expired according to a test clock, send a request through the bearer relay filter, and have the mock downstream return 401:

~~~text
Inbound T1 expired
    → relay filter forwards T1
    → downstream returns 401
    → token endpoint call count remains 0
~~~

This test confirms the relay filter only forwards the credential. If the application wants refresh behavior, it must use an OAuth2 Client manager and test that path separately.

### 16.3. Testing the Refresh Provider

Create an authorized client with:

~~~text
access token  = T1 (expired)
refresh token = R1
registration = shop-bff
principal = alice
~~~

The mock token endpoint receives `grant_type=refresh_token` and `refresh_token=R1`, and returns T2 (and R2 if rotated). Then assert:

- The manager sends the correct refresh grant.
- Downstream receives T2, not T1.
- Authorized client storage is updated with the new token/refresh token per the manager.
- The old refresh token is not reused after rotation.

### 16.4. Testing Client Credentials

When the authorized client registration is `inventory-service`:

- The mock token endpoint receives `grant_type=client_credentials`.
- The AS returns service token T-service with the Inventory API audience.
- Downstream receives T-service.
- The subject/client identity reflects the service, not Alice.
- The token is reused until re-authorization is needed per expiry/provider policy.

### 16.5. Testing Token Exchange

If the AS supports RFC 8693/OBO, the mock token endpoint verifies the request has the right subject token, proper actor/client authentication, right target audience/resource, and valid requested scope. Assert the new token is sent downstream and the subject/actor context matches the contract.

Do not use a mock that returns T2 regardless of request parameters to conclude that exchange policy is protected; tests must verify request parameters and negative cases.

### 16.6. Regression Matrix

| Case | Input | Mechanism | What to Assert |
|---|---|---|---|
| T-01 | Valid inbound token T1, matching audience | Relay | Downstream receives exact T1; token endpoint not called |
| T-02 | Expired inbound T1 | Relay filter | Still forwards T1; downstream rejects; no auto-refresh |
| T-03 | Authorized client with expired T1 + R1 | OAuth2 client manager | Refresh grant returns T2; downstream receives T2 |
| T-04 | No authorized client, valid service registration | Client credentials | Token endpoint issues a new service token |
| T-05 | User token with Orders audience, Inventory downstream | Relay | Inventory rejects wrong audience |
| T-06 | User token with Orders audience, needs Inventory context | Token exchange/OBO | AS issues new token for Inventory per delegation policy |
| T-07 | Token missing downstream scope | Relay | Downstream 403; no self-added scope |
| T-08 | DPoP-bound token | Relay with DPoP support | New proof for downstream URI/method |
| T-09 | mTLS-bound token | Relay via proxy | Certificate binding is maintained or request is rejected |
| T-10 | Redirect to host outside allowlist | Relay | Does not forward Authorization token to another host |
| T-11 | Downstream 403 | Error handling | No infinite refresh or out-of-policy fallback to service token |
| T-12 | Two requests sharing refresh token rotation | Refresh | Does not concurrently use the old refresh token causing a race/reuse |

### 16.7. Do Not Use Test Helpers to Confuse Relay with Authentication

If you use `mockJwt()` or `@WithMockUser`, tests can check authorization/controllers, but do not prove the inbound request actually carried an access token to relay. For relay integration tests, construct a request with a real Bearer token or an authenticated test context holding an explicit access token, and inspect the downstream header itself.

## 17. Complete Architecture Example: BFF Calling Two Downstream APIs

Suppose a BFF has two downstream services:

| Downstream | Required Identity | Audience | Mechanism |
|---|---|---|---|
| Orders API | User Alice | `orders-api` | Relay user token if already intended for Orders |
| Inventory API | Orders service | `inventory-api` | Client credentials |
| Pricing API | Alice, but inbound token is only for Orders | `pricing-api` | Token exchange/OBO if AS supports it |

Flow:

~~~mermaid
flowchart TD
    U["Alice / Browser"] --> BFF["Shop BFF"]
    BFF -->|"T-user, aud=orders-api"| O["Orders API"]
    O -->|"Service token, aud=inventory-api"| I["Inventory API"]
    O -->|"Subject token + actor Orders"| AS["Authorization Server"]
    AS -->|"T-pricing, aud=pricing-api"| O
    O -->|"T-pricing"| P["Pricing API"]
~~~

### 17.1. Orders API Does Not Use a Single WebClient for Everything

You can separate:

~~~text
userRelayWebClient:
    forwards current inbound user bearer token
    allowed host = orders downstream

inventoryServiceWebClient:
    OAuth2AuthorizedClientManager
    registration = inventory-service
    grant = client_credentials

pricingDelegationClient:
    token exchange/OBO provider integration
    subject token = current user token
    audience = pricing-api
    scope = pricing.read
~~~

Each client has an explicit credential policy. Do not let a single filter automatically relay tokens across all outbound requests.

### 17.2. Auditing Must Preserve the Right Actor

When the Inventory API receives a service token, audits should record the Orders service as the caller; if user attribution is needed, record a designed business correlation/actor context. When the Pricing API receives an exchanged token with subject Alice and actor Orders service, audits can distinguish the user and the middle-tier service based on trusted claims/profiles.

Do not record "Alice called Inventory directly" if Inventory only authenticated the service identity. Nor should you record "Orders service is the user" if token exchange preserves separate subject and actor claims.

### 17.3. Downstream Remains an Independent Resource Server

Each API must independently verify issuer, signature/introspection, audience, expiry, scope, and appropriate token binding. An internal network or an already-authenticated gateway does not make an access token valid for every downstream service.

## 18. Diagnosing Relay or Token Acquisition Failures

| Symptom | Possibility | How to Fix |
|---|---|---|
| Downstream receives no Authorization | SecurityContext has no access token, filter not attached, or context lost | Check authentication type, filter registration, and execution context |
| Downstream receives token but returns 401 | Expired, wrong issuer/audience, signature/key, or wrong token binding | Identify the reason at the Resource Server; relay does not fix tokens |
| Downstream returns 403 | Valid token but missing scope/role or domain permission | Check grant/authorization; do not self-add scopes |
| Relay filter does not call token endpoint | Normal behavior | Relay only forwards the existing token |
| OAuth2 client manager returns null/authorization failure | Wrong registration, provider, client credentials, or repository | Check registration/secret/token endpoint and manager provider |
| Refresh returns invalid_grant | Refresh token expired/revoked/rotated or client mismatch | Handle re-auth/recovery per policy; do not retry R1 indefinitely |
| Service token has unexpected subject/client | Using client credentials | Downstream receives service identity; use exchange/OBO if user delegation is needed |
| New token still has wrong audience | Client registration/resource request did not ask for the right resource | Configure API/resource identifier and issuer policy |
| Downstream receives user token on service route | Relay filter or TokenRelay applied to an inappropriate route | Separate service OAuth2 client and relay policies |
| Two concurrent requests refresh the same token | Race during refresh rotation | Coordinate refreshes by authorized-client key and update storage atomically |
| Token is sent to another host | Redirect/dynamic URL/client sharing a filter | Allowlist hosts and block cross-origin credential forwarding |
| Downstream DPoP rejects proof | Inbound proof was reused or htu/htm mismatch | Create a new proof for the downstream request using the token-bound key |

### 18.1. Downstream 401 May Be Wrong Audience, Not Expiration

Do not refresh just because you see a 401. Check error challenges/responses and Resource Server logs/metrics. If a token has the Orders audience but calls Inventory, refreshing under the same grant may still return the Orders audience; you need token exchange or a different client/resource request supported by the AS.

### 18.2. Authorized Client Manager Is Not an Unlimited Token Broker

The manager can only use the registrations, grant providers, and credentials configured by the application. It cannot unilaterally decide that a user token can be exchanged for a token for any resource. Resource/scopes, provider extensions, and delegation policies must be declared explicitly.

## 6. Relaying an Existing Access Token in Spring Security

Spring Security provides components to relay a Bearer token from the current SecurityContext to a `WebClient` call. This is suitable when downstream is permitted to receive **the exact access token authenticating the inbound request**.

### 6.1. Servlet: `ServletBearerExchangeFilterFunction`

For Servlet/Spring MVC applications, `WebClient` can be configured as:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class DownstreamWebClientConfiguration {

    @Bean
    WebClient downstreamWebClient() {
        return WebClient.builder()
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

When there is an authenticated request in the Servlet SecurityContext and the Authentication holds an appropriate Bearer access token, the filter can add that token to the WebClient request's Authorization header.

Example downstream call:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
class OrdersInventoryClient {

    private final WebClient downstreamWebClient;

    OrdersInventoryClient(WebClient downstreamWebClient) {
        this.downstreamWebClient = downstreamWebClient;
    }

    InventoryItem getStock(String sku) {
        return downstreamWebClient.get()
            .uri("https://inventory.internal/api/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(InventoryItem.class)
            .block();
    }
}
~~~

The `block()` example is only for illustrating synchronous calls from a Servlet application. Do not use blocking calls in the WebFlux event loop. Also ensure the WebClient only calls configured trusted downstream hosts; because the filter can attach credentials to requests, do not use an arbitrary global client for user-controlled URLs.

### 6.2. WebFlux: `ServerBearerExchangeFilterFunction`

For WebFlux applications:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveDownstreamWebClientConfiguration {

    @Bean
    WebClient downstreamWebClient() {
        return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
    }
}
~~~

When calling inside a reactive security context:

~~~java
Mono<InventoryItem> getStock(String sku) {
    return downstreamWebClient.get()
        .uri("https://inventory.internal/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

This filter retrieves the access token from the current reactive context and forwards it as a Bearer token according to Spring Security's mechanism. It does not automatically convert a Bearer access token into a token with a different audience.

### 6.3. Relay Filters Do Not Refresh Access Tokens

`ServletBearerExchangeFilterFunction` and `ServerBearerExchangeFilterFunction` are meant to **forward the current Bearer token**. They are not OAuth2 authorized-client managers and do not automatically call the token endpoint to refresh a token when the access token expires.

Therefore:

~~~text
Valid inbound token T1:
    relay → downstream receives T1

Expired inbound token T1:
    relay → downstream still receives T1
    downstream rejects if token is expired
~~~

If you want to obtain a new or refreshed token, you must use an OAuth2 Client and the appropriate authorized-client manager. Do not expect that merely adding a bearer exchange filter provides refresh behavior.

### 6.4. When Does the Relay Filter Find No Token?

If there is no authenticated principal containing an OAuth2 access token in the SecurityContext, the filter cannot synthesize a credential. Common cases:

- The inbound request had no Bearer token.
- The Authentication is another type, such as session/user authentication without an associated access token.
- The SecurityContext was not propagated properly across threads or the reactive context.
- The call runs in a background job with no user request context.

In these cases, select an appropriate grant/service identity or authorized client rather than fabricating a fake Authorization header string.

## 7. Spring Cloud Gateway: TokenRelay GatewayFilter

Spring Cloud Gateway provides the `TokenRelay` GatewayFilter Factory to forward the access token from a user's OAuth2 authorized client to a downstream route. This is a gateway-level relay mechanism.

Example route configuration:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: http://orders-service:8080
          predicates:
            - Path=/api/orders/**
          filters:
            - TokenRelay=
~~~

In an OAuth2 Login setup, the gateway can obtain the logged-in user's access token and attach it to requests sent to the Orders service. The gateway must be configured with OAuth2 Client and authorized-client/session storage according to the guide for your Spring Cloud Gateway version.

### 7.1. What Does TokenRelay Do?

~~~text
Browser
  Authorization: Bearer <user access token>
       |
       v
Gateway authenticates user / has OAuth2AuthorizedClient
       |
       v
TokenRelay filter obtains existing authorized client's access token
       |
       v
Downstream request:
  Authorization: Bearer <relayed access token>
~~~

The filter is named TokenRelay because it **forwards the access token already held by the authorized client**. The gateway does not modify the audience/scope or re-sign the token.

### 7.2. With and Without clientRegistrationId

TokenRelay can be configured to use the authorized client associated with the current user or a specified registration, depending on the API/version and flow. When specifying a client registration, be clear about which OAuth2 Client registration and user principal the token comes from:

~~~yaml
filters:
  - TokenRelay=inventory-client
~~~

This example merely illustrates the structure for a registration named `inventory-client`. It does not mean the current user's token is automatically exchanged for the Inventory API. Exact behavior depends on how the gateway integrates `OAuth2AuthorizedClientManager` and the registration/provider.

### 7.3. TokenRelay Does Not Replace Audience Design

If the gateway relays an access token with:

~~~text
aud = gateway-api
~~~

to the Orders API, the Orders API may reject it. Configuring TokenRelay does not automatically ask the issuer to issue tokens with the Orders audience. The client/issuer must issue a token suitable for the downstream resource, or the gateway must use a different token-acquisition mechanism.

### 7.4. Route-Specific Relay and Trust Boundaries

Do not apply TokenRelay unconditionally to every route. Only relay to trusted downstream hosts that have a token-acceptance policy, matching audience, and logging protection. Routes to public websites or user-controlled URLs must never automatically receive an Authorization header.

### 7.5. Storing OAuth2 Authorized Clients

The gateway needs to retain authorized client access tokens per principal/registration. With session-based OAuth2 Login, sessions/cookies and the authorized-client repository must be protected; logout, session invalidation, token expiry, and refresh lifecycles must be handled properly. TokenRelay is not an independent token store; it relies on the authorized client managed by OAuth2 Client.

## 8. Obtaining a New Token Using OAuth2 Client in Spring

When downstream needs a service token or a different authorized client than the inbound token, use **OAuth2 Client** instead of relay. Spring Security provides `OAuth2AuthorizedClientManager` for Servlet and `ReactiveOAuth2AuthorizedClientManager` for WebFlux to manage authorized clients, including obtaining/refreshing access tokens via configured providers.

### 8.1. Declaring a Client Registration for a Service

Example application YAML for a client credentials registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: shop-issuer
            client-id: orders-service
            client-secret: ${ORDERS_SERVICE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          shop-issuer:
            token-uri: https://login.example.test/oauth2/token
~~~

This is an illustrative configuration; provider/discovery properties and authentication methods must match your actual Authorization Server. Client secrets must come from a protected secret manager/environment and never be committed to the repository.

### 8.2. Servlet: Configuring the Authorized-Client Manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

@Configuration
class OAuth2ClientManagerConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .refreshToken()
                .authorizationCode()
                .build();

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Only enable the grants needed on the provider. `clientCredentials()` allows the manager to fetch service tokens; `refreshToken()` allows refreshing a user's authorized client when a valid refresh token is present; `authorizationCode()` participates in the authorization code lifecycle. For active web requests, `DefaultOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientRepository` can be used; choosing the manager depends on the execution context.

### 8.3. Using the Manager to Obtain a Service Token

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
class InventoryServiceTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    InventoryServiceTokenProvider(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String accessToken(String servicePrincipalName) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-service")
                .principal(servicePrincipalName)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException(
                "Could not authorize inventory-service client");
        }
        return client.getAccessToken().getTokenValue();
    }
}
~~~

With client credentials, `principal` is typically a stable service principal used to store the authorized client, not the current user. If there are multiple tenants/service identities, choose an appropriately scoped principal/cache key so tokens are not shared under the wrong identity.

### 8.4. New Tokens via Client Credentials Represent the Service

When using the `inventory-service` registration, downstream typically receives a token carrying the Orders service's client/service identity. If downstream needs to know that user Alice initiated the action, do not manually inject `sub=alice` into the token. Use token exchange/OBO if the issuer supports it, or design a trusted audit/delegation context.

## 9. OAuth2AuthorizedClientManager and Refresh Tokens

An authorized-client manager can decide whether to obtain a new token or refresh an existing one depending on the registration, existing authorized client, and enabled providers. This is the **token acquisition lifecycle**, not raw relay.

### 9.1. The Refresh Provider Requires a Refresh Token

In an authorization code flow, an authorized client can store:

~~~text
OAuth2AuthorizedClient:
    access token  = T1
    refresh token = R1
    registration  = shop-bff
    principal     = alice
~~~

When the access token is about to expire and the manager is configured with `refreshToken()`, the manager can call the token endpoint with R1 to obtain T2 (and possibly R2). Exact refresh timing depends on the provider implementation, clock skew, and token lifecycle.

### 9.2. Refresh Is Not a Way to Create a Service Identity

If the current token is Alice's user token, refreshing generally continues the authorization grant tied to Alice/client. It does not turn into a token for the Orders service. To obtain a service identity, use client credentials or an appropriate grant.

### 9.3. Refresh Is Not a Way to Arbitrarily Change Audience

The refresh grant typically continues an already-issued authorization grant; the AS may allow a narrower scope or resource parameter depending on policy/provider, but the client must not assume it can switch to any audience by adding a parameter. If a token for a different resource is needed, check provider support and consider token exchange or a new authorization.

### 9.4. Rotation and Concurrency

Some Authorization Servers enforce refresh token rotation: each use of R1 returns R2 and invalidates R1. If two parallel requests refresh R1 simultaneously, one request may succeed while the other is rejected or flagged as token reuse. The client must:

- Use the authorized-client manager/storage to coordinate the token lifecycle.
- Avoid multiple threads refreshing the same authorized client simultaneously.
- Update the new refresh token atomically.
- Handle invalid_grant/reuse per policy, which may require re-authentication.
- Never retry indefinitely using an old refresh token.

### 9.5. Relay Filters and OAuth2 Client Filters Have Different Behaviors

| Component | Purpose | Calls Token Endpoint? | Can Refresh? |
|---|---|---:|---:|
| `ServletBearerExchangeFilterFunction` | Relay Bearer token in Servlet context | No | No |
| `ServerBearerExchangeFilterFunction` | Relay Bearer token in reactive context | No | No |
| `TokenRelay` GatewayFilter | Relay authorized client's access token to a route | Does not change audience; lifecycle depends on authorized-client integration | Do not assume; check manager/version |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | Obtain authorized client/token for Servlet WebClient | Yes (potentially) | Yes if manager/provider enables refresh |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Obtain authorized client/token for reactive WebClient | Yes (potentially) | Yes if reactive manager/provider enables refresh |

Key takeaway: the name "OAuth2 client filter" does not mean it always refreshes every token. Behavior depends on the authorized-client manager, registration, grant, refresh token availability, and providers.

## 10. OAuth2 Client WebClient: Obtain/Refresh Instead of Raw Relay

When the application needs an **authorized client token** rather than the inbound access token, use an OAuth2 Client filter with a manager.

### 10.1. Servlet: `ServletOAuth2AuthorizedClientExchangeFilterFunction`

You can attach an authorized-client manager to a WebClient filter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class OAuth2WebClientConfiguration {

    @Bean
    WebClient inventoryOAuth2WebClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

When calling downstream with a client registration:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<InventoryItem> stock(String sku) {
    return inventoryOAuth2WebClient.get()
        .uri("https://inventory.internal/api/stock/{sku}", sku)
        .attributes(clientRegistrationId("inventory-service"))
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

This pattern uses an authorized client registration named `inventory-service`. The filter/manager can authorize the client under that registration and obtain or refresh the access token per the configured providers. The token will be that registration's credential, not necessarily Alice's inbound token.

### 10.2. User Authorized Client vs. Service Authorized Client

If downstream must receive the current user's access token, the manager must be called with the right user principal/authorized client and matching registration. Do not switch to `inventory-service` client credentials and expect downstream to still see `sub=alice`.

Conversely, if downstream only needs service identity, do not relay a user token just for convenience. Use a client credentials registration with minimal scopes.

### 10.3. Reactive: `ServerOAuth2AuthorizedClientExchangeFilterFunction`

In WebFlux, use the reactive manager and filter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveOAuth2WebClientConfiguration {

    @Bean
    WebClient inventoryOAuth2WebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .filter(oauth2)
            .build();
    }
}
~~~

When calling:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<InventoryItem> stock(String sku) {
    return inventoryOAuth2WebClient.get()
        .uri("https://inventory.internal/api/stock/{sku}", sku)
        .attributes(clientRegistrationId("inventory-service"))
        .retrieve()
        .bodyToMono(InventoryItem.class);
}
~~~

Overload/constructor names and static helpers may vary by Spring Security version. Consult the Javadoc/reference for your pinned dependency. The architectural point remains unchanged: the reactive manager resolves the authorized client and the filter attaches the appropriate access token; this is not an unconditional verbatim copy of the inbound token string.

### 10.4. Reactive Manager with Providers

Example configuration of a provider supporting client credentials and refresh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
class ReactiveAuthorizedClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .refreshToken()
                .authorizationCode()
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

The provider should reflect the grants the application actually uses. Background workers or service-to-service calls without a `ServerWebExchange`/user session may need a manager/repository suited for service contexts rather than `DefaultReactiveOAuth2AuthorizedClientManager` tied to web requests.

### 10.5. Choosing the Right Filter for the Right Purpose

~~~text
Need exactly the inbound bearer token?
    → ServletBearerExchangeFilterFunction
    → ServerBearerExchangeFilterFunction

Need a registered OAuth2 client token, service identity,
authorization-code authorized client, or managed refresh?
    → OAuth2AuthorizedClientManager + OAuth2 client WebClient filter

Need a token for a different audience while retaining user delegation?
    → OAuth2 Token Exchange / provider-specific OBO flow
~~~

Do not place two filters that both write the Authorization header onto the same WebClient and hope execution order yields the right identity. Each client should have a clear purpose and credential policy.

## 11. Token Exchange and On-Behalf-Of

When the Orders API receives Alice's access token intended for Orders, but the Inventory API needs a new token intended for Inventory while still requiring user context, relay cannot solve the audience mismatch. One option is **token exchange**.

### 11.1. RFC 8693: Subject Token and Actor Token

Token Exchange describes a token endpoint request that can contain:

- `subject_token`: token representing the subject being delegated.
- `subject_token_type`: type of the input token.
- `actor_token` (optional): token representing the actor performing the exchange.
- `actor_token_type` (optional).
- `requested_token_type` (optional).
- `audience`/`resource` or scope per supported extensions/policies.

Illustrative request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CLIENT_CREDENTIALS>

grant_type=urn:ietf:params:oauth:grant-type:token-exchange&
subject_token=<ALICE_ORDERS_ACCESS_TOKEN>&
subject_token_type=urn:ietf:params:oauth:token-type:access_token&
requested_token_type=urn:ietf:params:oauth:token-type:access_token&
audience=https%3A%2F%2Fapi.example.test%2Finventory&
scope=inventory.read
~~~

The AS verifies that the Orders service client is authorized to exchange that subject token and issues a new token per policy. The new token can retain Alice as the subject while setting the audience to the Inventory API and narrowing scopes appropriately.

Resource/audience parameters, actor tokens, and delegation permissions must follow the RFC/provider contract. Not every Authorization Server accepts this exact set of parameters.

### 11.2. Subject and Actor Are Not Identical

~~~text
sub = alice
act.sub = orders-service
aud = inventory-api
scope = inventory.read
~~~

The payload above only illustrates the concept. The subject is the delegated user; the actor is the service acting on behalf of the user. The exact claim structure must follow your token profile and how the AS issues tokens. Downstream needs to check delegation policy when actor context is present, rather than only reading `sub`.

### 11.3. On-Behalf-Of (OBO) Is a Provider-Specific Flow Name

Some providers call this exchange/delegation flow **On-Behalf-Of**. For example, in the Microsoft identity platform, a middle-tier API can exchange a received access token for an access token intended for a downstream API in the user's context. OBO is a provider-specific flow/API contract; do not assume all IdPs share the same request format or token claims.

### 11.4. Token Exchange Differs from Refresh

| Criterion | Refresh Grant | Token Exchange |
|---|---|---|
| Input | Refresh token | Subject token, optionally actor token |
| Goal | Issue a replacement access token within an existing grant | Issue a new token under subject/actor/resource delegation |
| Change audience | Not by default; depends on AS grant/policy | Can request a new audience/resource if allowed by AS |
| Change actor | Not a typical goal | Can represent actor/delegation |
| Can narrow scope | Per refresh policy | Per exchange policy |
| Used when | Old access token is expiring | Downstream needs a different token suited to its resource/delegation |

### 11.5. What If the AS Does Not Support Token Exchange?

Do not simulate exchange by:

- Decoding the inbound token and minting a new JWT yourself.
- Copying `sub`, `scope`, or `aud` into a self-signed token that downstream trusts.
- Adding a custom header saying "on behalf of Alice" that downstream treats as authentication.

Instead, choose a grant/architecture supported by the issuer: client credentials for service identity, a dedicated authorization flow, API composition, or a designed and verified delegation mechanism. If downstream strictly requires user context with no trusted delegation mechanism available, the contract between the services must change.

## 12. Client Credentials, Authorization Code, and Refresh in Context

### 12.1. Client Credentials

Used when a confidential client calls an API using its **application/service identity**. The client authenticates with the AS and receives an access token for the granted resources and scopes. No user session is automatically attached to the token.

Example:

~~~text
orders-service
    → client_id=orders-service
    → grant_type=client_credentials
    → scope=inventory.read
    → token aud=inventory-api
~~~

Advantage: simple for background/service tasks; avoids relaying user tokens. Limitation: downstream lacks a trusted user identity in the token, so it is unsuitable if user-specific authorization must be enforced unless another delegation model is used.

### 12.2. Authorization Code

Used when user authorization via browser/interactive login is required. The client exchanges an authorization code (and PKCE verifier for public clients) for an access token, optionally alongside a refresh token per policy. This is **obtaining a token via an authorization grant**, not relay.

A BFF can hold Alice's authorized client and relay the token if downstream is permitted to receive that exact token; or use token exchange/OBO to obtain a token intended for downstream.

### 12.3. Refresh Token Grant

Uses a refresh token issued by the AS to obtain a new access token within an already-issued authorization grant. The client must protect refresh tokens more strictly than access tokens because refresh tokens can be longer-lived and used to obtain further access tokens.

### 12.4. Token Exchange

Used when a service has an existing subject token but needs a new token for a different resource or actor context, provided the AS supports it. It is not a grant that every Spring Security deployment has available automatically.

### 12.5. Concise Selection Rules

| Need | Typically Appropriate Mechanism |
|---|---|
| Downstream is permitted to receive the same access token | Relay |
| Downstream only needs service identity | Client Credentials |
| Access token is expiring, same grant | Refresh |
| Need a token for another resource while preserving user delegation | Token Exchange/OBO if supported |
| No user grant yet, need user consent/login | Authorization Code + PKCE |
| Background job with no user context | Client Credentials or service-specific grant |

## 13. DPoP and mTLS-Bound Tokens During Relay

Relaying a token is not always just copying a string into the Authorization header. If a token is bound to a key or certificate, the downstream request must satisfy the corresponding sender constraint.

### 13.1. DPoP-Bound Access Tokens

With DPoP, the access token is bound to a public key thumbprint and the request requires:

~~~http
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <NEW_PROOF_FOR_THIS_DOWNSTREAM_REQUEST>
~~~

Forwarding **only the access token** is insufficient. Nor can the inbound request's proof usually be relayed verbatim downstream because `htm`/`htu` differ; `ath` may be the same if the token is the same, but the proof must be signed for the downstream method/URI. The component performing the relay must possess the corresponding private key and generate a new proof, or use token exchange to obtain an appropriate binding.

### 13.2. mTLS Certificate-Bound Tokens

If the access token is bound to a client certificate thumbprint, downstream must see the matching client certificate/private key in the TLS handshake or via a trusted proxy delegation architecture. Simply copying the access token over HTTP does not preserve certificate binding.

### 13.3. Do Not Strip Sender Constraints for Relay Convenience

Do not downgrade a DPoP/mTLS token to the Bearer scheme or drop the proof/certificate to avoid errors. If downstream cannot satisfy the current binding, use a new token suited to the resource/connection or redesign the trust boundary.
# Relaying an Existing Token Differs from Obtaining a New Token or Refreshing a Token

In an OAuth 2.0 system with a gateway, backend-for-frontend (BFF), or multiple microservices, a request often passes through several components before reaching the final API. When the Orders API needs to call the Inventory API or a gateway forwards a request to a downstream service, the application must decide **whether to use the existing access token, request a new token from the Authorization Server, or refresh an expired token**.

These three actions have different purposes and semantics:

- **Token relay:** forwarding the exact access token that was received. The token value does not change; downstream receives the same credential with the same claims, audience, scope, expiration, and token binding.
- **Obtaining/acquiring a new token:** requesting the Authorization Server to issue a new access token under a grant or authorization flow. The new token may represent the client/service or a user, depending on the grant.
- **Refreshing a token (refresh):** using a refresh token to request a replacement access token when the current access token is expiring or expired, under the permissions and policy previously granted.

In addition to these three, there is **OAuth 2.0 Token Exchange**: using an existing token as a subject/actor input so the Authorization Server issues a different token intended for a downstream resource or delegation context. Token exchange is neither token relay nor a refresh grant.

The most important point: **relay preserves the identity and scope of the current token; obtain/refresh/exchange creates or returns a different access token as decided by the Authorization Server**. Choosing the wrong mechanism can lose user context, send a token with the wrong audience, unintentionally expand privileges, or turn a service-to-service call into an action under a user's identity.

This lesson belongs to the **Token Relay** chapter in the **Spring Security OAuth 2.0 OIDC Resource Server** module. It explains request flows, how to distinguish the grants, choosing between relay and a new token, how to use Spring Security/Spring Cloud Gateway, as well as risks and testing approaches.

> Token data, issuers, keys, and client IDs in these examples are simulated. The goal is to clearly understand the boundary between an existing credential and a new credential issued by the Authorization Server.

## 1. A Request Crossing Multiple Services

Suppose a user logs into Shop Web, calls the Orders API, and the Orders API needs to query the Inventory API:

~~~text
Browser / Shop Web
        |
        | access token T-user
        v
API Gateway
        |
        | token relay?
        v
Orders API
        |
        | call downstream Inventory API
        v
Inventory API
~~~

At each hop, the intermediary component can:

1. **Relay** the received token.
2. **Use the service's own token** to call downstream.
3. **Refresh** the access token if a valid refresh token is available.
4. **Exchange** the incoming token for a new token with the appropriate audience/scope/actor.

There is no single right choice for every system. You must consider **who is the subject of the action**, **whom downstream needs to trust**, **which resource the token is intended for**, and **which grants the Authorization Server supports**.

### 1.1. Example of Relaying an Existing Token

The browser sends:

~~~http
GET /api/orders/42 HTTP/1.1
Host: shop.example.test
Authorization: Bearer eyJ...T_USER
~~~

The gateway forwards the exact access token to the Orders API:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.internal
Authorization: Bearer eyJ...T_USER
~~~

The value after the scheme in both requests is **the exact same token string**. The gateway does not change the subject, scope, audience, issuer, expiry, or signature. The gateway merely forwards the credential per policy.

### 1.2. Example of Obtaining a New Token with Client Credentials

The Orders API calls the Authorization Server using its service identity:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <ORDERS_SERVICE_CLIENT_CREDENTIALS>

grant_type=client_credentials&scope=inventory.read
~~~

The Authorization Server returns a new token intended for the Inventory API:

~~~json
{
  "access_token": "<NEW_SERVICE_ACCESS_TOKEN>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory.read"
}
~~~

This is a **new token**. The token typically represents the Orders service/client and does not automatically retain the identity of the user who called the Orders API.

### 1.3. Example of Refreshing a Token

The client has access token T1 and refresh token R:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN_R>&
client_id=shop-bff
~~~

The Authorization Server can return a new access token T2 and refresh token R2 if rotation is applied. T2 is a new credential; it may retain the authorization grant corresponding to R, but it must not be assumed that every claim, audience, scope, or binding will be identical to T1.

## 2. Distinguishing the Four Actions

| Action | Primary Input | Result | Identity Typically Represented | Does the Token Change? |
|---|---|---|---|---|
| **Relay** | Existing access token | Sends the same token downstream | Subject/caller in the original token | **No** |
| **Obtain a new token** | Authorization code, client credentials, or other grant | New access token | User or service depending on the grant | **Yes** |
| **Refresh** | Refresh token | Replacement access token | Previously issued authorization grant | **Yes** |
| **Token exchange** | Subject token and optionally actor token | New access token for target resource/delegation | Subject/actor per exchange policy | **Yes** |

### 2.1. Relay Is an HTTP-Layer Action

Relay typically just means: taking the existing token from the SecurityContext/session/authorized client and attaching it to the downstream request. It does not ask the Authorization Server to issue a new token.

~~~text
incoming access token
       |
       v
extract token
       |
       v
Authorization: Bearer <same token>
       |
       v
downstream API
~~~

If the token is expired or has the wrong audience, relay still sends that exact token; downstream may reject it. Relay does not mint a new token, modify claims, or add permissions.

### 2.2. Obtaining a New Token Is an Authorization Decision

The client asks the Authorization Server to issue a token under a permitted grant. The AS checks client authentication, grant, consent, user context, scopes, resource/audience, and policy. Issuing a token is not merely copying an existing credential.

### 2.3. Refresh Maintains an Existing Grant

A refresh token is used at the token endpoint to request a replacement access token. It is not an access token for calling a Resource Server. Refresh does not typically mean "escalating privileges" or "switching to another API arbitrarily"; the AS still controls scope/resource and may require the user to re-authenticate or re-consent.

### 2.4. Token Exchange Creates a Token for Another Delegation/Resource

Token Exchange (RFC 8693) lets a client send a subject token, optionally along with an actor token, and request a token suited for a new audience/resource or delegation context. This can be used when the Orders API needs to call the Inventory API **with delegated user context**, but the incoming token was not issued for the Inventory API.

Token exchange can only be used if the Authorization Server supports it and policy permits it. Do not assume every OAuth provider implements RFC 8693 or shares the same semantics.

## 3. The Deciding Question: Whom Does Downstream Need to Trust?

Before writing code, determine which identity downstream needs to see.

### 3.1. Downstream Needs to Act Under the User's Identity

For example, user Alice calls:

~~~text
GET /api/orders/42
~~~

The Orders API needs to call the Pricing API, and the Pricing API needs to check Alice's permissions. You can:

- Relay Alice's access token if the token was issued for both Orders/Pricing or the resource contract permits Pricing to accept it.
- Exchange Alice's token for an access token intended for the Pricing API, keeping Alice as the subject and Orders API as the actor if policy requires delegation.

If you relay a token whose audience is only for the Orders API, the Pricing API should rightly reject it. Do not modify the Pricing API to accept tokens not intended for it.

### 3.2. Downstream Needs Service Identity

For example, the Orders API needs inventory information for an internal calculation. The Inventory API only needs to know the caller is the Orders service:

~~~text
Orders service
    -- client credentials -->
Authorization Server
    -- service token aud=inventory-api -->
Orders service
    -- Authorization: Bearer <service token> -->
Inventory API
~~~

This is obtaining a token via Client Credentials, not relaying a user token. The Inventory API's audit log will reflect the service client; if user context must be recorded, the Orders API can pass a trusted business correlation/actor context per a dedicated design, without forging authentication claims.

### 3.3. Downstream Needs Both User and Service Context

A service may need to prove:

- **Subject:** user Alice initiated the action.
- **Actor:** the Orders API is making the downstream call on Alice's behalf.
- **Audience:** the token is intended for the Inventory API.
- **Scope:** only inventory read permission is granted.

Token exchange is a suitable mechanism if the Authorization Server supports subject/actor delegation. Simply relaying the current token may fail to convey the actor chain or the right audience.

### 3.4. Do Not Decide Solely Based on "Token Not Expired"

An unexpired token may:

- Be intended for a different API.
- Lack downstream scopes.
- Be issued to a client not permitted to call downstream.
- Be bound to a DPoP key or mTLS certificate that the downstream request does not satisfy.
- Lack the necessary actor/delegation context.

Therefore, "the token has not expired yet" is not sufficient reason to relay it.

## 4. Audience and Scope Determine Where a Token Can Be Relayed

Suppose the current access token is:

~~~json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "alice",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

The token was issued for the Orders API and only has the order-reading scope. The Orders API forwards the exact token to the Inventory API:

~~~http
GET /internal/stock/sku-123 HTTP/1.1
Host: inventory.internal
Authorization: Bearer <SAME_ORDERS_TOKEN>
~~~

The Inventory API checks `aud` and sees the token is intended for the Orders API. It should reject this token, even though the signature and issuer are valid. If the Inventory API skips the audience check just because the request came from the internal network, the resource boundary is weakened.

### 4.1. Relay Cannot Add an Audience Itself

The Gateway or Orders API cannot edit the JWT payload:

~~~text
decode token
change aud from orders-api to inventory-api
encode token
~~~

If the token is a JWS, modifying claims invalidates the signature. If the token is opaque, the client cannot even inspect the claims inside. Only the Authorization Server or a trusted token-issuing mechanism can create a token with a new audience.

### 4.2. Relay Cannot Add Scopes Itself

If the token only has `orders.read`, adding `inventory.read` to a header or request context does not cause the Authorization Server to grant that permission. Scopes must be granted within the access token/authorization context and verified by the Resource Server.

### 4.3. Multi-Audience Tokens

If a token has:

~~~json
{
  "aud": [
    "https://api.example.test/orders",
    "https://api.example.test/inventory"
  ],
  "scope": "orders.read inventory.read"
}
~~~

then relaying it to the Inventory API can be valid if the issuer intentionally issues multi-resource tokens and policy permits it. However, a leaked token has a larger replay blast radius; many systems prefer per-resource tokens or token exchange to narrow permissions.

### 4.4. Relay Preserves Permissions Rather Than Reducing Them

A token with `orders.read orders.write admin` still carries those scopes when relayed. The gateway cannot "strip" `admin` from the token while preserving the signature. If downstream needs narrower permissions, request a new token with minimal scopes via token exchange or an appropriate grant.

## 5. Mechanism Selection Diagram

~~~mermaid
flowchart TD
    A["Have an existing access token"] --> B{"Can and may downstream receive this exact token?"}
    B -->|Yes| C["Relay the same access token"]
    B -->|No| D{"Does downstream need user/delegation identity?"}
    D -->|Yes| E{"Does the AS support Token Exchange / OBO?"}
    E -->|Yes| F["Exchange token for the downstream resource"]
    E -->|No| G["Redesign grant/delegation or require an appropriate user flow"]
    D -->|No, only service identity needed| H["Obtain a new service token via Client Credentials"]
    C --> I["Downstream still verifies aud, scope, expiry, binding"]
    F --> I
    H --> I
~~~

**Refresh** is a separate branch: if the access token needed for the same authorization context is expired/expiring and the client has a valid refresh token, use the refresh flow to get a replacement access token. Refresh is not a default way to switch audiences or turn a user token into a service token.
