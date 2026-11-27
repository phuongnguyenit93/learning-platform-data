# The Target Recipient Must Be Permitted and Belong to an Appropriate Audience

## 1. Why Must a Relayed or Exchanged Token Target the Right Recipient?

In a multi-service architecture, a request can traverse multiple Resource Servers. For example, a user calls the Orders API; the Orders API needs to call the Inventory API to read stock. The access token the user sends to the Orders API may only have been issued for **orders-api**. If the Orders API forwards that exact token to the Inventory API, the token may have the wrong audience, the wrong scope, or cross a backend trust boundary.

**OAuth 2.0 Token Exchange** per RFC 8693 allows an OAuth client to send an incoming security token to the Authorization Server (AS) to request a new token suited for a different usage context. The client can specify the target using the **audience** or **resource** parameter while requesting the required scope. The AS verifies the client, subject, actor, and resource policy before issuing the token.

```text
Browser / Mobile
    │ access token for orders-api
    ▼
Orders API (Resource Server A)
    │ subject_token + target inventory-api
    ▼
Authorization Server / Security Token Service
    │ new token for inventory-api
    ▼
Inventory API (Resource Server B)
```

What must be ensured:

1. The client only requests tokens for **permitted resources** in configuration or trust relationships.
2. The AS only issues a token if the client, subject, and actor are permitted to access that target.
3. The new token is restricted to the target resource's audience and the minimal required scope.
4. The target Resource Server independently verifies the new token and checks its own audience.
5. The client calls only configured endpoints and never uses token exchange to send credentials to arbitrary URLs.

> **Core rule:** The audience or resource parameter in a token-exchange request is only a client request. It does not grant permission by itself and does not prove the returned token is intended for that resource. The AS must approve the request; the target Resource Server must verify the actual audience on the received token.

## 2. Token Exchange Differs from Forwarding an Access Token

```text
Option 1 — Forward the incoming token (token relay):

Client ── AT-Orders ──> Orders API ── AT-Orders ──> Inventory API

Option 2 — Token exchange:

Client ── AT-Orders ──> Orders API
                           │
                           ├── subject_token = AT-Orders
                           ├── audience = inventory-api
                           └── scope = inventory:read
                                   │
                                   ▼
                            Authorization Server
                                   │
                                   └── AT-Inventory
                                           │
                                           ▼
                                   Inventory API
```

In the second approach, the AS issues a new token per policy. The output token can preserve the original user as the subject, record Orders API as the actor acting on behalf of the user, contain only the inventory-reading scope instead of all scopes from the input token, have a shorter lifetime, and be a JWT or opaque token per the AS contract.

Token exchange **does not automatically revoke the subject token**. RFC 8693 describes exchange as a one-time event; lifecycle and revocation relationships between the input and output tokens depend on the implementation, profile, and deployment policy.

### 2.1. When Should Token Exchange Be Used?

| Scenario | Consideration |
| --- | --- |
| Two services share the same resource boundary and audience | Token relay may be suitable if the API contract allows it. |
| Service A calls B with a different audience | Use token exchange or a dedicated credential-issuing mechanism for B. |
| Service A calls B on behalf of a user | Exchange helps constrain permissions at B and represent subject/actor. |
| A service needs its own permissions | Client credentials or token exchange per actor/delegation policy. |
| Two services belong to different trust domains | An intermediary AS verifies the input token and issues a token suited for the target trust domain. |

Token exchange is an extension grant; not every AS supports it. The client must know the deployed grant, token types, and policies.

## 3. Components in RFC 8693

RFC 8693 defines the Token Exchange Grant:

```text
urn:ietf:params:oauth:grant-type:token-exchange
```

Key parameters:

| Parameter | Required? | Meaning |
| --- | --- | --- |
| **grant_type** | Yes | The token exchange grant URN. |
| **subject_token** | Yes | Security token representing the subject on whose behalf the new token is requested. |
| **subject_token_type** | Yes | Token type identifier of the subject token. |
| **actor_token** | No | Security token representing the actor performing the action on behalf of the subject. |
| **actor_token_type** | When actor_token is present | Token type identifier of the actor token. |
| **resource** | No | URI of the target protected resource per RFC 8707. |
| **audience** | No | Logical name of the target service where the new token will be used. |
| **scope** | No | Desired scopes in the context of the target resource/audience. |
| **requested_token_type** | No | Desired type of token to be issued. |

Common token type URIs:

```text
urn:ietf:params:oauth:token-type:access_token
urn:ietf:params:oauth:token-type:refresh_token
urn:ietf:params:oauth:token-type:id_token
urn:ietf:params:oauth:token-type:jwt
```

Distinguish **token type** from **token format**: an access token can be represented as a JWT or an opaque string. A JWT is not automatically an access token; it could also be an ID token, client assertion, or another security assertion.

### 3.1. Subject Token

**subject_token** represents the party on whose behalf the new token is requested. In a typical flow:

```text
subject_token = user's access token already verified by Orders API
subject_token_type = urn:ietf:params:oauth:token-type:access_token
```

The AS must verify the subject token against issuer, token type, signature or introspection state, and applicable policies. Never just decode the payload and trust claims sent by the client.

### 3.2. Actor Token

**actor_token** represents the party performing the action on behalf of the subject:

```text
Subject = Alice
Actor   = Orders API service
Target  = Inventory API
```

The actor token is optional in the protocol. If the request includes `actor_token`, then `actor_token_type` is required. The AS must verify both the subject token and the actor token according to their respective token types.

Do not confuse an actor token with client authentication:

- **Client authentication** proves which OAuth client is calling the Token Endpoint.
- **Actor token** carries security token information about the actor per the delegation model.
- **Subject token** carries information about the subject on whose behalf permissions are requested.

A request may require both client authentication and an actor token; one does not automatically replace the other.

## 4. resource and audience: Two Ways to Specify the Target Recipient

RFC 8693 allows a client to describe the target service using **audience** or **resource**.

### 4.1. audience: Logical Name of the Service

**audience** is a logical name mutually understood by the client and the AS, for example:

```text
inventory-api
```

This name can be an OAuth client identifier, SAML entity identifier, OIDC issuer identifier, or a deployment-defined service name. Audience values must have unique meaning within the AS's scope to avoid identifier ambiguity.

### 4.2. resource: Resource Indicator URI

**resource** per RFC 8707 identifies the protected resource by URI. The value must be an **absolute URI** and must not contain a fragment. For example:

```text
https://inventory.example.internal/api/
```

Choose a URI specific enough to identify the API. If multiple applications reside on the same host, using only the hostname may be too broad.

### 4.3. resource and audience Are Not Scopes

| Value | Question It Answers |
| --- | --- |
| **resource** | At which protected resource URI is the token requested to be used? |
| **audience** | For which logical target service is the token requested? |
| **scope** | What types of actions does the client want to perform at that resource? |

Example:

```text
resource = https://inventory.example.internal/api/
audience = inventory-api
scope = inventory:read
```

**scope** should not be abused to encode a service address. **inventory:read** describes the permission to read inventory, not necessarily where the token will be redeemed.

### 4.4. Do Not Request Multiple Targets When Only One Is Needed

RFC 8693 notes that when multiple resources/audiences are present, the client is requesting a token usable at all listed targets with the requested scopes. The effective set of permissions can be understood as the Cartesian product of scopes and target services.

For example, requesting:

```text
audience = orders-api
audience = inventory-api
scope = read write
```

can be much broader than:

```text
audience = inventory-api
scope = inventory:read
```

Only request a single specific target when a downstream call only needs one service. The AS may reject overly broad requests with **invalid_target**.

## 5. Token Request and Response

Suppose the Orders API has authenticated the user via an incoming access token and needs to call the Inventory API solely to read stock.

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic <orders-service-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange&
subject_token=<orders-access-token>&
subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token&
resource=https%3A%2F%2Finventory.example.internal%2Fapi%2F&
audience=inventory-api&
scope=inventory%3Aread&
requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
```

If an actor token is needed:

```http
actor_token=<orders-service-actor-token>&
actor_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
```

This is an illustrative request. The client must use the exact client authentication method registered with the AS (HTTP Basic, private_key_jwt, mTLS, or another supported method), rather than assuming every AS uses a client secret.

Successful response:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<inventory-access-token>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "inventory:read"
}
```

**issued_token_type** describes the type of token issued; **token_type** describes how to use the token. Do not confuse these two fields. The AS may issue a JWT or an opaque token; the client should treat the access token as opaque and use it per the response contract.

### 5.1. The New Token Must Be Used for the Right Backend

```http
GET /api/stock/SKU-100 HTTP/1.1
Host: inventory.example.internal
Authorization: Bearer <inventory-access-token>
```

The Inventory API checks:

- The token's signature/issuer or introspection state.
- Audience or resource binding matching the Inventory API.
- Expiration and token profile.
- The **inventory:read** scope.
- Tenant, subject, actor, and policy for the requested record.

A successful token exchange at the AS **does not replace** verification by the target Resource Server.

## 6. The Authorization Server Must Approve the Target

A client may send:

```text
audience=payroll-admin-api
scope=payroll:write
```

but that does not mean the client is permitted to receive such a token. The AS must apply policy based on at least:

1. Verified **client identity**.
2. Valid **subject token** and subject identity.
3. Valid **actor token** if the request includes an actor.
4. Whether the client is permitted to exchange this subject token.
5. Whether the client/actor is permitted to operate on the target resource.
6. Whether the subject has the required grant, consent, or permissions.
7. Whether the requested scopes fall within permitted rights at the target.
8. Token profile, lifetime, and sender constraints if required by the deployment.

Examples:

| Client | Subject | Target | Scope | Result |
| --- | --- | --- | --- | --- |
| Orders service | Alice tenant A | Inventory API | inventory:read | Permitted if Alice and actor are allowed. |
| Orders service | Alice tenant A | Payroll API | payroll:write | Denied if client is not allowed to call Payroll. |
| Reports service | Alice | Inventory API | inventory:admin | Denied if scope exceeds delegated permissions. |
| Orders service | Expired/wrong-issuer subject token | Inventory API | inventory:read | Subject token rejected. |
| Unregistered client | Alice | Inventory API | inventory:read | Client rejected. |

### 6.1. Token Exchange Is Not an Arbitrary Audience Selector

Do not build an internal API where the caller decides the target directly:

```java
// DANGEROUS: target comes directly from the caller's query/header.
String target = request.getParameter("audience");
return tokenExchange.exchange(subjectToken, target);
```

If the caller can request any audience, the intermediary service can become a **confused deputy**: it uses its own privileged credentials to obtain a token for a resource the caller is not permitted to call.

Instead:

- Map business operations to configured target registrations.
- Only allow an approved set of audiences/resource URIs.
- Verify the caller is authorized to perform the operation before exchanging.
- The AS must still check client, subject, and target.
- The downstream service must still check audience/scope.

## 7. Audience of the Issued Token and Verification at the Target Resource Server

In a JWT access token, the audience usually appears in the **aud** claim:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "exp": 1893456000
}
```

The Inventory API only accepts the token if **aud** satisfies its contract. If the AS uses the resource URI directly as the audience:

```json
{
  "aud": ["https://inventory.example.internal/api/"]
}
```

The AS may also map a resource URI to a different audience identifier. The client should not assume the resource string will always appear verbatim in the `aud` claim; it must know the AS's mapping contract.

### 7.1. Audience Membership or Exact-Single Audience?

**Membership**: accept if `aud` contains the API's identifier:

```java
boolean intendedForApi =
        jwt.getAudience().contains("inventory-api");
```

**Exact-single**: accept only when the audience list has exactly one element:

```java
boolean onlyThisApi =
        jwt.getAudience().size() == 1
        && jwt.getAudience().contains("inventory-api");
```

Membership is appropriate when the token contract allows multiple audiences. An exact-single policy is stricter and useful when an organization wants to prohibit tokens shared across multiple resources. Choose based on your security contract and AS capabilities.

### 7.2. Do Not Compare Audience by Substring

Do not do:

```java
// WRONG: inventory-api-admin also contains inventory-api.
boolean allowed =
        jwt.getClaims().get("aud").toString()
                .contains("inventory-api");
```

Use exact membership on the parsed audience list:

```java
boolean allowed =
        jwt.getAudience().contains("inventory-api");
```

### 7.3. Audience Differs from Issuer

**iss** answers "who issued the token?". **aud** answers "which resource is the token intended for?". A token with the right issuer but the wrong audience must still be rejected.

```text
iss = https://login.example.test
aud = orders-api

Inventory API:
  expected audience = inventory-api
  result = reject
```

Do not share a single issuer validator and skip audience validation across backend services.

## 8. The resource Parameter per RFC 8707

RFC 8707 defines `resource` so the client can explicitly indicate the protected resource. The value must be an absolute URI with no fragment. Example:

```text
resource=https://inventory.example.internal/api/
```

The AS uses the resource indicator to determine policies applicable to the target, restrict the audience, select token type/content, apply encryption or sender constraints if required by the deployment, and reject unknown or disallowed resources.

### 8.1. A Resource Identifier URI Is Not Necessarily the HTTP Call URL

`resource` is an **identifier** in the OAuth request. The AS can map that URI to an internal logical resource/audience.

```text
OAuth resource identifier:
  https://inventory.example.internal/api/

Configured downstream base URL:
  https://inventory.service.cluster/api/
```

Mapping between these two values belongs in controlled configuration. Do not use a caller-supplied `resource` to construct the HTTP destination directly.

### 8.2. Do Not Introduce SSRF via Resource URIs

If a service takes an arbitrary resource URI and calls it directly, a caller could request:

```text
resource=http://169.254.169.254/latest/meta-data/
```

Countermeasures:

- Allowlist exact resource identifiers.
- Accept only governed/registered URIs.
- Control redirects, TLS, and egress.
- Separate the OAuth resource identifier from the downstream network URL.
- Never allow user-chosen paths/queries to turn into a new audience.

## 9. Scopes Must Match the Target

Scopes describe types of permissions at a resource:

```text
orders-api:
  orders:read
  orders:write

inventory-api:
  inventory:read
  inventory:reserve

payroll-api:
  payroll:read
```

Identically named scopes across two APIs do not necessarily have the same semantics. Do not send Orders' scopes to Inventory and treat them as equivalent permissions.

### 9.1. Token Exchange Should Narrow Permissions

Input token:

```json
{
  "aud": ["orders-api"],
  "scope": "orders:read orders:write profile:read"
}
```

The Orders API only needs to read stock. The output token should have:

```json
{
  "aud": ["inventory-api"],
  "scope": "inventory:read"
}
```

Do not copy all input scopes into the new token. The AS must compute permitted rights from the subject, actor, client, target, and policy.

### 9.2. Do Not Request Multiple Audiences Just for Convenience Across Services

If a workflow calls Inventory and Billing, you can obtain two separate tokens:

```text
Token 1:
  aud = inventory-api
  scope = inventory:read

Token 2:
  aud = billing-api
  scope = billing:charge
```

This usually reduces the blast radius if one token is leaked. If a deployment intentionally issues multi-audience tokens, it must know precisely which resources accept the token and which scopes are effective at each location.

## 10. Delegation and Impersonation

RFC 8693 distinguishes two models:

### 10.1. Impersonation

Actor A is issued a token such that, within the granted permission context, the target resource treats itself as interacting with subject B. The identity on the token may remain solely the subject. Impersonation is very powerful and can make auditing unable to distinguish the actor unless the system records the actor elsewhere.

### 10.2. Delegation

Actor A retains its own identity and acts on behalf of subject B. The token can carry both subject and actor:

```json
{
  "iss": "https://login.example.test",
  "sub": "alice",
  "aud": ["inventory-api"],
  "scope": "inventory:read",
  "act": {
    "sub": "orders-service"
  }
}
```

**act** is the actor claim per RFC 8693. In a delegation chain, `act` can be nested; the outermost actor is the current actor, while inner nested actors represent prior history. Resource Servers should use top-level claims and the current actor for access control; nested actor chains are informational history per the RFC.

### 10.3. may_act

The **may_act** claim can indicate that a party is permitted to become an actor on behalf of the subject. The AS can use this claim when deciding an exchange. This is not a claim the client can add itself to grant its own permissions; it must come from a trusted token/source and be verified by the AS.

### 10.4. Client Authentication Does Not Replace Actor Authorization

Successful client authentication via a client secret only proves the client's identity. The AS still needs to check whether that client is permitted to exchange the specific subject token, use the specific target resource, request the specific scopes, and act as an actor/impersonate the subject.

## 11. Service-to-Service Chains

```text
Browser
  │ AT-A (aud=frontend-api)
  ▼
Frontend API
  │ exchange AT-A → AT-B (aud=orders-api)
  ▼
Orders API
  │ exchange AT-B → AT-C (aud=inventory-api)
  ▼
Inventory API
```

Each step requires:

1. The current Resource Server verifies the received token.
2. The service only exchanges for a registered target.
3. The AS verifies subject/actor/client and target policy.
4. The new token contains only the needed audience and scope.
5. The downstream Resource Server verifies the new token.

Do not use a wildcard-audience token across the entire chain just to reduce the number of exchanges. A single compromised service should not be able to use that token at every backend.

## 12. From Which Version Does Spring Security Support Token Exchange?

Spring Security provides OAuth2 Client support for the token-exchange grant starting in **6.3**. This is client-side support for calling the Token Endpoint; it does not mean every AS automatically enables the grant or every Resource Server automatically accepts the output token.

| Stack | Provider | Token Response Client |
| --- | --- | --- |
| Servlet | **TokenExchangeOAuth2AuthorizedClientProvider** | **RestClientTokenExchangeTokenResponseClient** |
| Reactive/WebFlux | **TokenExchangeReactiveOAuth2AuthorizedClientProvider** | **WebClientReactiveTokenExchangeTokenResponseClient** |

The provider handles the token-exchange grant. The subject token is resolved from context; the actor token is not resolved by default in a basic setup. Resolvers can be configured via **setSubjectTokenResolver** and **setActorTokenResolver**.

**Version note:** Specific APIs and automatic provider registration mechanisms may differ across Spring Security releases. Use Spring Boot's dependency management and the Javadoc for the exact version you are running.

## 13. Configuring ClientRegistration

Spring Boot example:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-exchange:
            provider: internal-as
            client-id: orders-service
            client-secret: <secret-from-secret-manager>
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            client-authentication-method: client_secret_basic
        provider:
          internal-as:
            token-uri: https://login.example.test/oauth2/token
```

This is an illustrative configuration for a confidential service client using HTTP Basic. The AS may require `private_key_jwt`, mTLS, or another method; choose according to your issued registration. Never commit secrets to Git.

Targets such as **inventory-api** or the Inventory URI should be configured/allowlisted in the application. Never let callers arbitrarily change the registration or Token Endpoint.

## 14. Servlet: TokenExchangeOAuth2AuthorizedClientProvider

Example manager configuration:

```java
@Configuration
class TokenExchangeClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
                new TokenExchangeOAuth2AuthorizedClientProvider();

        OAuth2AuthorizedClientProvider providers =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .provider(exchangeProvider)
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
```

This is a Servlet OAuth2 Client configuration. By default, the provider resolves the subject token from the principal if the principal is an `OAuth2Token` (e.g., `JwtAuthenticationToken`). If the subject token comes from another source, configure `setSubjectTokenResolver`. An actor token is not resolved by default; if your deployment requires one, configure `setActorTokenResolver`.

## 15. Reactive/WebFlux: Token Exchange Client

Spring Security includes a reactive provider since 6.3. Configuration skeleton:

```java
@Configuration
class ReactiveTokenExchangeConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        TokenExchangeReactiveOAuth2AuthorizedClientProvider exchangeProvider =
                new TokenExchangeReactiveOAuth2AuthorizedClientProvider();

        ReactiveOAuth2AuthorizedClientProvider providers =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .provider(exchangeProvider)
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
```

This is a reactive manager skeleton using `ServerOAuth2AuthorizedClientRepository`. Service/background flows without a `ServerWebExchange` can use the corresponding service-backed reactive manager. Verify the exact package/imports for your version; do not mix the Servlet `OAuth2AuthorizedClientManager` into WebFlux.

### 15.1. Adding Audience to the Token-Exchange Request

You can customize `WebClientReactiveTokenExchangeTokenResponseClient`:

```java
@Bean
WebClientReactiveTokenExchangeTokenResponseClient tokenExchangeResponseClient() {
    WebClientReactiveTokenExchangeTokenResponseClient client =
            new WebClientReactiveTokenExchangeTokenResponseClient();

    client.addParametersConverter(grantRequest -> {
        MultiValueMap<String, String> parameters =
                new LinkedMultiValueMap<>();

        if ("inventory-exchange".equals(
                grantRequest.getClientRegistration().getRegistrationId())) {
            parameters.set(OAuth2ParameterNames.AUDIENCE,
                    "inventory-api");
        }

        return parameters;
    });

    return client;
}
```

If the AS requires an RFC 8707 resource indicator, you can add the `resource` parameter with an approved URI:

```java
parameters.set(
        "resource",
        "https://inventory.example.internal/api/");
```

Only send both `audience` and `resource` when the AS contract specifies how they are interpreted. Having both parameters present can signify multiple target services and is not always two interchangeable ways of writing the same target. When only one target is needed, usually configure only the single parameter agreed upon with the AS.

### 15.2. Wiring the Response Client into the Provider

```java
exchangeProvider.setAccessTokenResponseClient(
        tokenExchangeResponseClient);
```

This needs to be wired into the manager configuration above.

### 15.3. Subject Token and Actor Token in a Reactive Flow

Resolvers can be configured:

```java
exchangeProvider.setSubjectTokenResolver(context -> {
    Object principal = context.getPrincipal().getPrincipal();

    if (principal instanceof Jwt jwt) {
        return Mono.just(jwt);
    }

    return Mono.error(new IllegalStateException(
            "No trusted subject token is available"));
});

exchangeProvider.setActorTokenResolver(context ->
        actorTokenService.currentActorToken(context));
```

`actorTokenService` is an application-implemented abstraction. Never read an actor token from an arbitrary header or unverified request body. If no actor token is needed, do not configure the resolver and do not send the actor token parameter.

### 15.4. Calling the Downstream API

Example reactive service:

```java
public Mono<InventoryDto> getInventory(
        Authentication authentication,
        String sku) {

    OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory-exchange")
                    .principal(authentication)
                    .build();

    return authorizedClientManager.authorize(authorizeRequest)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException(
                            "Token exchange did not produce an authorized client")))
            .flatMap(authorizedClient ->
                    webClient.get()
                            .uri(inventoryBaseUrl + "/stock/{sku}", sku)
                            .headers(headers -> headers.setBearerAuth(
                                    authorizedClient.getAccessToken()
                                            .getTokenValue()))
                            .retrieve()
                            .bodyToMono(InventoryDto.class));
}
```

`authorizedClientManager`, `webClient`, `inventoryBaseUrl`, and `InventoryDto` are configured by the application. The new token is obtained from the `inventory-exchange` registration; the downstream URL comes from approved service configuration.

Do not do:

```java
// WRONG: taking target URL from user query parameter.
.uri(request.getParameter("resource"))
```

The OAuth resource identifier and the HTTP destination URL must be bound via configuration mapping.

## 16. The Target Resource Server Must Verify the New Token

Token exchange is the OAuth2 Client's responsibility; the Inventory API remains an independent Resource Server. For JWTs, configuration must preserve issuer and audience validation:

```java
OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(inventoryIssuer);

OAuth2TokenValidator<Jwt> audience = jwt ->
        jwt.getAudience().contains("inventory-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Token is not intended for Inventory API",
                                null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                defaults, audience));
```

Do not check only the issuer. A token issued by the right issuer but carrying `aud=orders-api` is not intended for the Inventory API.

With opaque tokens, the introspection response must provide resource/audience information or the AS must enforce resource binding per a verified contract. A Resource Server must not infer that because a token is active at the AS, it can call every API.

## 17. Multi-Tenant Resources and Audiences

For multi-tenant APIs, the resource identifier sometimes needs to include the tenant or namespace:

```text
https://api.example.test/tenants/alpha/inventory/
https://api.example.test/tenants/bravo/inventory/
```

If the two URIs represent two distinct security boundaries, the AS can issue different audiences. RFC 8707 recommends that the client supply the most specific resource URI it knows.

### 17.1. Tenant ID Is Not a Client-Selectable Parameter

Do not take `tenant=bravo` from a request and construct Bravo's resource URI yourself. The application must verify that the subject has membership in the tenant, that the client is permitted to exchange for that tenant, and that the AS has a corresponding policy.

### 17.2. The Right Audience Is Still Not Enough for Object Authorization

A token with `aud=inventory-api` and `inventory:read` only indicates the token is for the API and carries read functional rights per contract. The API must still verify which tenant's SKU or warehouse the user/service is permitted to read.

Audience restricts the **resource server**, scope restricts the **action**, and domain policy restricts the **data object**.

## 18. Token Exchange Errors

RFC 8693 defines `invalid_target` when the AS cannot or will not issue a token for the requested resource/audience.

| Error | Possible Cause | Action |
| --- | --- | --- |
| invalid_request | Missing subject token/type, actor token missing actor type, invalid or unacceptable input token. | Check the request/token contract. |
| invalid_target | Resource/audience unknown, client not allowed to request it, or disallowed by policy. | Stop; inspect target registration and permissions. |
| invalid_scope | Invalid scope or exceeds granted permissions. | Narrow scopes or perform appropriate authorization/consent. |
| invalid_client | Invalid client authentication at the AS. | Fix client registration/secret/certificate. |
| unauthorized_client | Client not permitted to use the token-exchange grant. | Check AS grant policy. |
| unsupported_grant_type | AS does not support the grant or misconfiguration. | Confirm AS capability/version. |
| HTTP 429 | Rate limit at the AS. | Back off per policy. |
| HTTP 5xx/timeout | AS or network unavailable. | Fail closed; classify dependency failure. |

### 18.1. invalid_target Should Not Be "Fixed" with Wildcards

If the AS rejects a target, do not send more audiences, use wildcards, drop scopes hoping a token gets issued, pick a resource URL from another caller input, or disable target validation. Inspect client-target authorization and resource registration.

### 18.2. Do Not Fall Back to the Input Token

If exchange fails because the target is not permitted, do not send the subject token to the downstream API to "see if it works." That is the exact boundary token exchange is protecting.

## 19. Testing Matrix: Target Must Be Permitted and Audience Must Match

### 19.1. Target/Audience Matrix

| Case | Client Requests | AS Policy | Output Token | Result |
| --- | --- | --- | --- | --- |
| TE-01 | Inventory URI, inventory:read | Client and subject permitted | aud=inventory-api | Inventory API accepts. |
| TE-02 | audience=payroll-api | Orders client not permitted | Not issued; invalid_target | Do not call Payroll API. |
| TE-03 | Unregistered resource URI | Unknown resource | invalid_target | Do not call unknown target. |
| TE-04 | Inventory, inventory:admin | Subject only has read | Denied or constrained per policy | Do not grant admin rights. |
| TE-05 | Inventory, read | Subject token expired/wrong issuer | Rejected per AS contract | Do not issue token. |
| TE-06 | Inventory, read | Wrong client authentication | invalid_client | Fix client credentials. |
| TE-07 | Inventory | Actor not allowed to represent subject | Denied | Do not impersonate/delegate unlawfully. |
| TE-08 | Inventory | AS returns aud=orders-api | Downstream rejects | Do not trust AS HTTP 200 alone. |
| TE-09 | Inventory | Token has right audience but missing scope | Authentication may pass | 403. |
| TE-10 | Inventory | Right audience/scope but wrong tenant | Domain policy rejects | 403/404. |

### 19.2. Target Resource Server Matrix

| Token Received by Inventory API | Issuer | Audience | Expected |
| --- | --- | --- | --- |
| Valid token | Trusted AS | inventory-api | Passes authentication if other claims are valid. |
| Orders token | Trusted AS | orders-api | 401 invalid_token. |
| Payroll token | Trusted AS | payroll-api | 401 invalid_token. |
| Multi-audience token containing Inventory | Trusted AS | [orders-api, inventory-api] | Per membership/single-audience policy. |
| Untrusted-issuer token | Untrusted AS | inventory-api | 401. |
| Invalid-signature token | Claimed issuer valid | inventory-api | 401. |
| Expired token | Trusted AS | inventory-api | 401. |
| Right audience but missing scope | Trusted AS | inventory-api | 403. |

### 19.3. Anti-Confused-Deputy Matrix

Tests must verify:

1. Callers cannot change the audience via request headers/queries.
2. Callers cannot change the resource via arbitrary URLs.
3. Clients cannot exchange a subject token for a target outside the allowlist.
4. The AS rejects unauthorized client-target combinations.
5. When token exchange fails, the downstream service is not called.
6. The client does not fall back to the input token.
7. Downstream URLs always come from approved configuration.
8. Subject/actor identities are recorded per delegation policy.

## 20. Testing Spring Security

### 20.1. Verifying Token Request Parameters

The Mock Token Endpoint should assert:

```text
grant_type = urn:ietf:params:oauth:grant-type:token-exchange
subject_token = verified incoming token
subject_token_type = urn:ietf:params:oauth:token-type:access_token
audience = inventory-api (if used by the deployment)
resource = configured URI (if used by the deployment)
scope = inventory:read
client authentication = matches registration
```

If an actor token is present, assert both `actor_token` and `actor_token_type`. Never log raw tokens or client secrets in test logs.

### 20.2. Verifying the Token Response

When the mock AS returns a new token:

- The client reads `access_token`.
- The client handles `issued_token_type` and `token_type`.
- The client stores expiry/metadata in the authorized-client store.
- The client calls the exact configured downstream URL.
- The outbound header contains the output token, not the subject token.

### 20.3. Verifying the Target Resource Server

Use genuinely signed test JWTs or an opaque introspection mock:

1. `aud=inventory-api` and `scope=inventory:read` → positive.
2. `aud=orders-api` → reject.
3. `aud=payroll-api` → reject.
4. Right `aud` but missing scope → 403.
5. Right `aud`/scope but wrong tenant → 403/404.
6. Wrong issuer/signature/expired → reject.

Do not use `mockJwt()` and conclude that the audience validator ran; mock principals can bypass the decoder. Send a signed test JWT through the filter chain when testing full authentication.

## 21. Security Considerations

### 21.1. Least Privilege

Request a single target and the smallest scopes needed. Short-lived, per-resource output tokens; never grant administrative privileges just because the intermediary service is highly privileged.

### 21.2. Client Authentication at the Token Endpoint

RFC 8693 emphasizes that client authentication allows the AS to evaluate which clients are permitted to receive delegation/impersonation. Never enable anonymous token exchange without a clear rationale and a tightly controlled trust model.

### 21.3. Validate Subject and Actor Tokens

The AS must verify token type, issuer, signature/introspection state, expiry, and policy for both subject tokens and actor tokens. Never use `sub` from an unverified payload.

### 21.4. Protect Tokens in Transit

Both subject tokens and actor tokens are sent to the Token Endpoint. Use TLS, do not log form bodies or Authorization headers, and do not store raw tokens in traces/exceptions.

### 21.5. Restrict Targets and Scopes

Do not request multiple targets just for convenience. Each additional target expands the token's usage surface. The AS should maintain an allowlist/resource registry and policies per client/subject/actor.

### 21.6. Do Not Treat resource as a Network Call Target

A resource indicator is an identifier for AS policy. It must never directly determine the host a service connects to. Downstream destinations require independent configuration and network egress controls.

### 21.7. Preserve the Actor in Audit Logs

With delegation, record both the verified subject and actor. Do not record only the subject if you need to trace which service performed the action. Token claims should contain only the minimum necessary information.

### 21.8. Revocation and Token Lifetime

Token exchange does not automatically expire the input token. Output tokens can live independently; if revocation propagation is needed, the AS/Resource Servers must implement explicit mechanisms such as introspection, short lifetimes, token families/versions, or event propagation.

## 22. Common Mistakes

1. **Treating the audience request parameter as permission:** `audience=inventory-api` is only a request; the AS must approve it and the Resource Server must verify it.
2. **Using scope instead of resource:** `inventory:read` describes a permission, not which API the token is redeemable at.
3. **Forwarding the original token to backends:** the input token may only be intended for the current API.
4. **Issuing overly broad multi-audience tokens:** multiple targets increase the blast radius.
5. **Letting the client pick the resource URI:** easily leads to confused deputy/SSRF vulnerabilities.
6. **Authenticating only the client without checking the subject:** recognizing the client does not mean any arbitrary subject token can be exchanged.
7. **Confusing client identity with actor identity:** they are distinct concepts in delegation.
8. **Omitting the audience validator downstream:** the AS returning a token does not exempt the Resource Server from verifying `aud`.
9. **Output token having broader scopes than input:** never self-escalate; the AS must decide per policy.
10. **Ignoring issued_token_type:** token type and token representation have different meanings.
11. **Assuming every AS supports RFC 8693:** verify that the AS implements the grant and the client is authorized to use it.
12. **Assuming the output token is always a JWT:** the AS may issue an opaque token.
13. **Treating token exchange as a refresh grant:** exchange swaps a security token for a new subject/actor/target, rather than merely renewing an old token.
14. **Defaulting to a high-privilege actor:** bind the actor accurately to the action and policy.

## 23. Practical Scenarios

### A. Orders API Reading Inventory

The Orders API verifies a user token with audience Orders. It exchanges the subject token for a token with `aud=inventory-api`, `scope=inventory:read`. The Inventory API verifies audience and scope before returning stock.

### B. Orders API Requesting Payroll

The client sends `audience=payroll-api`, but AS policy prohibits the Orders service from calling Payroll. The AS returns `invalid_target`; the application halts and does not try the original token at Payroll.

### C. Output Token Has the Wrong Audience

The AS is misconfigured and returns a token with `aud=orders-api` even though the request asked for Inventory. The client should not trust it merely because of HTTP 200; the Inventory API must reject the token. Integration tests catch the mismatch.

### D. Delegation from User to Service

Alice calls the Orders API. The Orders API is the actor; Alice is the subject. The AS issues a token with subject Alice and actor Orders service, scoped only to reading inventory. The Inventory API audits both identities.

### E. Impersonation for a Legacy System

A legacy system only understands user identities. The AS can issue a time- and scope-limited impersonation token to the service. Because impersonation is powerful, enable it only for approved clients/targets and audit it.

### F. Multi-Tenant Resource URI

The Orders API needs tenant Alpha's Inventory. It may select Alpha's resource URI only after verifying the subject's membership. A caller cannot switch the URI to tenant Bravo via a header.

### G. Opaque Downstream Token

The AS issues an opaque access token instead of a JWT. The Inventory API introspects the token and checks `active`, audience/resource binding, and scope. The Orders API does not decode the token or infer claims itself.

### H. Multi-Hop Token Exchange

The Orders API receives a token from the Gateway and exchanges it for Inventory. If Inventory subsequently calls Warehouse, it only exchanges again if policy permits and must preserve the appropriate delegation chain. Never blindly propagate all scopes/actor history.

## 24. Self-Check Questions

**1. Why is token exchange needed when calling another backend?** The input token may only be intended for the current API; exchange issues a new credential suited for the target resource.

**2. What is the grant type URI of RFC 8693?** `urn:ietf:params:oauth:grant-type:token-exchange`.

**3. What is subject_token?** The token representing the subject on whose behalf the new token is requested.

**4. What is actor_token?** The token representing the actor performing the action on behalf of the subject; optional, but when present, `actor_token_type` is required.

**5. Does client authentication replace an actor token?** No. It identifies the OAuth client at the Token Endpoint; the actor token represents the actor per the delegation contract.

**6. How do audience and resource differ?** `audience` is the logical name of the target service; `resource` is a resource indicator URI.

**7. What does scope identify?** Desired actions/permissions at the resource, not where the token is redeemed.

**8. If a client sends audience=inventory-api, must the AS issue the token?** No. The AS must verify client, subject, actor, target, and scope policies; it may return `invalid_target`.

**9. Is the output token always a JWT?** No; it can be an opaque token or another token type.

**10. Must the target Resource Server verify aud?** Yes. The new token must be intended for the right resource and pass all other checks.

**11. Should multiple audiences be requested to call multiple backends?** Only when policy intentionally permits it; normally request one target per downstream call.

**12. What is act?** The actor claim per RFC 8693, which can represent the current actor and delegation chain.

**13. Does may_act grant permission to the client by itself?** No. It is information about permitted actors from a verified token/policy.

**14. Does token exchange automatically revoke the subject token?** No; revocation relationships depend on the deployment.

**15. From which version does Spring Security support the token-exchange client?** Servlet and reactive providers are available starting in Spring Security 6.3.

**16. Does the reactive provider resolve the actor token by default?** No; an actor token resolver must be configured if the deployment requires it.

**17. Can a resource URI from a query parameter be used to call downstream?** No. Targets must be in an allowlist/configuration, and HTTP destinations must be controlled independently.

**18. If an input token has orders:write, can it be exchanged for inventory:admin?** Only if AS policy explicitly permits it; a client cannot escalate its own privileges.

**19. Why must the new token have an appropriate lifetime?** To reduce the window of exposure if a credential is leaked and bound delegated authority.

**20. When the AS returns invalid_target, should we fall back to the input token?** No. You must stop because the target is disallowed or invalid.

## 25. References

- **RFC 8693 — OAuth 2.0 Token Exchange:** grant type, subject/actor tokens, resource/audience/scope, response, and delegation/impersonation claims. https://www.rfc-editor.org/rfc/rfc8693
- **RFC 8707 — Resource Indicators for OAuth 2.0:** resource URI, audience restriction, and invalid_target. https://www.rfc-editor.org/rfc/rfc8707
- **RFC 6749 — OAuth 2.0 Authorization Framework:** client authentication, token endpoint, and access token request/response. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 7662 — OAuth 2.0 Token Introspection:** active state and opaque token metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** using access tokens at a Resource Server. https://www.rfc-editor.org/rfc/rfc6750
- **Spring Security Reference 7.0 — Servlet OAuth2 Client Authorization Grants / Token Exchange:** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html
- **Spring Security Reference 6.5 — Reactive OAuth2 Client Authorization Grants / Token Exchange:** https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- **Spring Security API — TokenExchangeOAuth2AuthorizedClientProvider:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/TokenExchangeOAuth2AuthorizedClientProvider.html
- **Spring Security API — TokenExchangeReactiveOAuth2AuthorizedClientProvider:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/TokenExchangeReactiveOAuth2AuthorizedClientProvider.html
- **Spring Security API — TokenExchangeGrantRequest:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/endpoint/TokenExchangeGrantRequest.html

## 26. Conclusion

When a service needs to call another backend on behalf of a user or another service, **token exchange** lets it swap a subject token for a new credential suited to the target recipient. The client describes the target with a resource URI or logical audience while requesting minimal scope. The AS must verify the client, subject, actor, and target access rights; the target Resource Server must check the actual audience of the new token.

Spring Security supports the token-exchange grant in OAuth2 Client starting in **6.3**, for both Servlet and reactive stacks. Token-exchange providers manage the flow, while response clients allow customizing request parameters such as `audience` when required by the AS.

A target recipient is only safe when controlled through an **allowlist/resource registry**, approved by the AS, and verified by the target Resource Server. Never use arbitrary caller-supplied targets, never issue overly broad audiences/scopes, and never fall back to the input token when exchange is denied. Every downstream call requires a token with the right audience, scope, subject/actor, and tenant.
