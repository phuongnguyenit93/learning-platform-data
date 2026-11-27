# The Contract Between Client, Issuer, and API on Audience, Permissions, and Identity

In a Spring Security system using OAuth 2.0 and OpenID Connect (OIDC), an access token is only useful when the **OAuth2 Client**, the **token issuer (Authorization Server/Issuer)**, and the **protected API (Resource Server)** share the exact same contract. That contract answers at least three questions:

1. **Audience:** **Which API** was this token issued for?
2. **Permissions:** **Which actions** may the token perform, and who decides access to each specific resource?
3. **Identity:** **Which user, application, or delegated principal** does the token represent?

If the three parties interpret these differently, the system can suffer hard-to-diagnose 401/403 errors—or worse, accept tokens meant for another API, accept an ID token to call an API, or infer excessive permissions from an identity claim.

> **Design principle:** The Client **requests** permissions and sends the access token; the Authorization Server **decides and issues** the token; the Resource Server **validates the token and enforces** permissions on resources. Having a valid signature is only one part of the access decision.

## 1. Three parties sharing one contract

Suppose an e-commerce application has:

- **Shop Web / Shop BFF:** OAuth2 Client registered with `client_id = shop-web`.
- **Identity Server:** Authorization Server publishing issuer `https://identity.example.test/realms/shop`.
- **Orders API:** Resource Server identified by audience `orders-api`.
- **User:** Subject wishing to view their own orders.

~~~mermaid
sequenceDiagram
    actor User as User
    participant Client as OAuth2 Client (Shop Web)
    participant AS as Authorization Server (Issuer)
    participant API as Resource Server (Orders API)

    User->>Client: View orders
    Client->>AS: Request orders.read for orders-api
    AS->>AS: Authenticate, evaluate Client/scope/audience
    AS-->>Client: Access token with iss, aud, sub, scope
    Client->>API: GET /api/orders/42 + Bearer token
    API->>API: Validate signature, iss, exp, aud
    API->>API: Check scope and permissions on order 42
    API-->>Client: 200 / 401 / 403 / 404
~~~

In an interactive login flow, the Client may receive an authorization code and exchange it for tokens; in service-to-service communication, the Client may use `client_credentials`. Token issuance details vary by grant, yet **the API must still verify the token was issued for itself and enforce permissions**.

| Party | What it must know | What it is responsible for |
| --- | --- | --- |
| **OAuth2 Client** | Issuer/metadata, Client registration, grants, requestable scopes, target Resource Servers, how to manage tokens | Requesting tokens for the right API and needed permissions; sending access tokens securely on requests; handling expiration or rejection |
| **Authorization Server** | Which Clients may request tokens, which resources/audiences may be granted, which scopes/policies apply, how identity is authenticated | Authenticating per grant, issuing tokens with accurate issuer, audience, subject, and permissions |
| **Resource Server** | Trusted issuer and keys or introspection; accepted audience; scope/claim mapping; data access policies | Validating tokens; rejecting wrong audience/issuer; checking scopes, tenant, ownership, and business policies |

The contract must be codified as explicit configuration and validation rules. Documentation stating "the API accepts JWTs" is insufficient because **not every JWT is meant for that API**.

## 2. Understanding the fields of an access token

A JWT access token might carry the following illustrative payload:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "iat": 1893456000,
  "exp": 1893459600,
  "jti": "token-7a1c",
  "tenant_id": "shop-tenant-17"
}
~~~

This is an **example application contract**; not every Authorization Server emits the exact same claims. Some issuers use `scp` instead of `scope`, `azp` instead of `client_id`, a different format for `aud`, or omit `tenant_id`. These differences must be agreed upon and explicitly configured.

| Claim / attribute | Meaning in the contract | Notes |
| --- | --- | --- |
| `iss` | **Issuer** that minted the token | Resource Server only trusts configured issuers; match expected value strictly |
| `aud` | **Audience**: target recipients permitted to accept the token | Must include the Orders API identifier; never substitute `client_id` for `aud` |
| `sub` | **Subject** represented in the token | Subject interpretation depends on grant, issuer, and token profile; never assume it is always a user |
| `client_id` / `azp` | Client associated with the token, depending on issuance convention | Usable for Client policies, but does not prove "who the user is" |
| `scope` / `scp` | Granted permission scopes | Interpret solely per Authorization Server and Resource Server definitions |
| `exp`, `nbf`, `iat` | Token lifetime and issuance timestamps | Typically checked for expiration / not-before; clocks must be synchronized |
| `jti` | Token identifier if provided by the issuer | Useful for logging/tracing; does not automatically guarantee revocation |
| `tenant_id`, `roles`, business claims | Extended info under a custom contract | Must verify trusted source, semantics, and usage policy |

**Never make decisions just because a payload "looks right."** JWTs can be decoded without knowing any key; the Resource Server must verify the signature and acceptance conditions before trusting claims. With opaque tokens, the API typically obtains status/attributes via introspection rather than decoding a JWT, yet the same contract principles hold.

## 3. Audience: *whom* is the token for?

### 3.1. Audience is not Client ID

Audience (`aud`) specifies the valid target recipients of a token. In our example:

- `client_id = shop-web`: the application **requesting** the token.
- `aud = orders-api`: the API **permitted to receive** the access token.
- `iss = https://identity.example.test/realms/shop`: the issuer **trusted by the API**.

These three values can be completely different. The API must never infer "this token is valid for me" simply because the token was issued to a known Client or signed by a known issuer.

Consider three cases:

| Token | How does Orders API handle it? | Why? |
| --- | --- | --- |
| Valid `iss`, `aud = orders-api`, unexpired | Can proceed to permission checks | Token has the right audience, though scopes and data still must be checked |
| Valid `iss`, `aud = billing-api` | **Reject** | Token is intended for another API, even with the same issuer and signing key |
| `aud = orders-api`, `iss` from an untrusted party | **Reject** | A matching audience does not make an unknown issuer trustworthy |

If a token lists multiple audiences, the API must verify **its own identifier is in the list** and consider its policy on accepting multi-audience tokens. In multi-API architectures, issuing narrowly scoped audiences helps limit abuse if a token leaks.

### 3.2. Client requests a token for the right resource

Some Authorization Servers support **Resource Indicators for OAuth 2.0 (RFC 8707)**: the Client can pass a `resource` parameter to indicate the target resource when requesting permissions.

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&
scope=orders.read&
resource=https%3A%2F%2Fapi.example.test%2Forders
~~~

This shows only a shortened body illustrating `resource`: a real request must also **authenticate the Client** via its registered method, and the Authorization Server must support this parameter. The `resource` value may be a resource URL while `aud` is `orders-api`, if that is the agreed mapping rule. **The Client does not dictate the audience by writing a claim into the token**; the issuer decides what audience is actually minted.

If the Authorization Server does not support `resource`, the system may determine audience via Client registration, scopes, API configuration, or an issuer-specific mechanism. There is no universal rule guaranteeing "if a Client requests scope `orders.read`, the audience automatically becomes Orders API."

### 3.3. Audiences of access tokens and ID tokens differ

OIDC issues an **ID token** to the **OIDC Client** to convey the user authentication outcome. An ID token typically carries the Client's `client_id` (`shop-web`) as `aud`, whereas an access token for the Orders API must carry the Orders API's audience (`orders-api`).

~~~text
ID token (OIDC):         iss = Identity Server
                         aud = shop-web
                         sub = user-842
                         Purpose: Client confirms the user logged in

Access token (OAuth2):   iss = Identity Server
                         aud = orders-api
                         sub = user-842 (in a user flow)
                         scope = orders.read
                         Purpose: Call Orders API
~~~

**Never send an ID token in place of an access token**, even when both are JWTs signed by the same issuer. The API should enforce a token-type / token-purpose validation policy suited to its profile and issuer; a system using a JWT access token profile (e.g., RFC 9068) may additionally enforce the corresponding `typ` header rule, though you should not assume all issuers follow the exact same convention.

## 4. Permissions: scopes, roles, and data policies

### 4.1. Scopes define granted operations

Suppose the Orders API contract defines:

| Scope | API operation permitted for consideration |
| --- | --- |
| `orders.read` | Read orders |
| `orders.write` | Create/update orders per policy |
| `orders.cancel` | Cancel orders per policy |

The Authorization Server must know which scopes may be granted to a Client and subject per grant. The Client merely **requests** scopes; the granted result may be narrowed. The Resource Server must check **scopes actually present in the validated access token**, never trusting a separate permission list sent by the Client in the request.

Example:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

If the endpoint requires `orders.read`, a token holding only `orders.write` **does not automatically gain read permission** unless the system explicitly defines a scope hierarchy. Similar names do not imply implicit permission inheritance.

### 4.2. Scope alone is not enough to authorize a specific record

Scope answers "what kind of operation may be **attempted**?" Business authorization also answers "**on which record and under what conditions**?"

For example, `user-842`'s token has `orders.read`, yet `GET /api/orders/42` may be:

- **Allowed** if order 42 belongs to `user-842` and the right tenant.
- **Denied** if order 42 belongs to someone else.
- **Denied** if the user is no longer a member of that tenant or the order is in a restricted state.

Role-based (RBAC), attribute-based (ABAC), tenant, and data-ownership checks are normally enforced by the Resource Server or its business layer. **Do not treat a `roles` claim as global permission** without aligning on which APIs/tenants the roles apply to and how the issuer manages them.

### 4.3. Distinguishing Client permissions from user permissions

In a user-involved flow, a token may be tied to both the Client (`shop-web`) and the user (`user-842`). Effective access rights usually fall within the intersection of **what the Client is allowed to do** and **what the user is allowed to do**.

In `client_credentials`, there may be **no end user**. The token reflects the permissions of the authenticated application/service; how `sub` is populated in this case depends on the Authorization Server and token profile. The Resource Server must never treat every `sub` as a customer ID.

When Backend A calls Backend B on behalf of a user, the contract must explicitly specify how **delegation/token exchange** works or how B receives tokens with the appropriate audience and actor/subject. Never forward tokens from Backend A's incoming request blindly to Backend B, as audience and permissions may be incompatible.

## 5. Identity: who is calling and on whose behalf?

OAuth 2.0 focuses on resource access authorization. OIDC adds user identity authentication for Clients. Therefore, an access token containing `sub` is not enough to conclude an application completed a full OIDC login flow.

### 5.1. Subject is not synonymous with email, username, or Client

For user tokens, `sub` is the subject identifier within the issuer's scope. A safe storage rule is using the **(`iss`, `sub`)** pair as the issuer-provided identity key rather than `sub` or email alone. Two different issuers can assign the same `sub` string to two different people; email addresses can change or be recycled. OIDC can also use **pairwise** subjects, making `sub` differ across Client groups.

Claims like `email`, `preferred_username`, and `name` assist UI display or matching when policy permits; they are not immutable identity keys by default, nor do they automatically grant API permissions.

### 5.2. Distinguishing subject and the application issued the token

Suppose an access token contains:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-842",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Intended meaning under this contract:

- **`sub`:** the user represented in the token.
- **`client_id`:** the application issued the token.
- **`aud`:** the API to which the token may be presented.
- **`scope`:** the granted action group.

In a machine-to-machine token:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "batch-sync-service",
  "client_id": "batch-sync-service",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Both tokens above can share the same scope yet **do not share the same identity semantics**. The API must distinguish a policy of "user viewing their own orders" from "batch service permitted to synchronize orders"; it can use claims indicating principal type, grant type, or Client restrictions per the issuer contract. Never infer those attributes arbitrarily from `sub`.

### 5.3. Token claims vs. changing data

A valid JWT only proves the issuer asserted those claims at issuance time. Account status, roles, and tenant membership can change while the access token remains unexpired. For sensitive permissions requiring immediate effect, the API may need to query live policy state, use short-lived tokens, introspection, or an appropriate revocation mechanism.

Even if a token carries a `tenant_id` claim, that does not guarantee the caller can read every record in that tenant. The API must still verify the requested resource and the caller's relationship to the tenant per business policy.

## 6. Writing an explicit contract before configuring Spring Security

An integration contract document should specify concrete values and ownership for every item:

| Item | Example agreement | Responsible party |
| --- | --- | --- |
| Trusted issuer | `https://identity.example.test/realms/shop` | AS publishes; Client/API configure |
| API identifier | `orders-api` | API architecture and AS agree |
| Registered Clients | `shop-web`, `batch-sync-service` | AS registers; Clients use |
| Token type | Signed JWT access token; algorithms/keys per policy | AS issues; API verifies |
| Orders API audience | `aud` must contain `orders-api` | AS emits; API validates |
| Grantable scopes | `orders.read`, `orders.write`, `orders.cancel` | AS configures policy; API defines effect |
| Permission claim mapping | e.g., space-delimited `scope` string | AS emits; API converts to authorities |
| Subject definition | User subject for authorization code, service principal for client credentials | AS publishes; API interprets |
| Tenant identity | `tenant_id` claim or server-side lookup via `(iss, sub)` | AS/API agree on trusted source |
| Token lifetime and revocation | TTL, refresh/introspection/revocation mechanisms as needed | AS defines; Client/API enforce |
| Authorization policy | Endpoint scope **plus** ownership, tenant, roles/attributes | API and business services |
| Rejection behavior | 401 if unauthenticated; 403 if authenticated but lacking permissions | API |

The contract must also document **per-environment audience values** (dev/test/prod), JWKS URI, key rotation conventions, differences between OAuth access tokens and OIDC ID tokens, and how token schema changes are rolled out.

### Example endpoint policy

| Endpoint | Audience | Scope | Additional business condition |
| --- | --- | --- | --- |
| `GET /api/orders/{id}` | `orders-api` | `orders.read` | User owns the order or holds support rights within the tenant |
| `POST /api/orders` | `orders-api` | `orders.write` | Caller is permitted to create orders in the request's tenant |
| `POST /api/orders/{id}/cancel` | `orders-api` | `orders.cancel` | Order is cancellable and caller is order owner/authorized staff |
| `GET /internal/orders/export` | `orders-api` | `orders.export` | Only approved service Clients; audit logged per policy |

Conditions in the last column **cannot be inferred from scopes alone**. A clean practice is separating coarse checks in the security filter from ownership/tenant/state checks in the business service.

## 7. Resource Server enforcing the contract in Spring Security

The example below uses **Spring Boot with Spring Security 6**, where the Orders API accepts JWT access tokens having:

- `iss` matching the agreed issuer;
- `aud` containing `orders-api`;
- unexpired lifetime and valid signature;
- required scope per endpoint;
- permission on the actual record, checked in the business service.

Dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 7.1. Configuring issuer and verification keys

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/shop
          jwk-set-uri: https://identity.example.test/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api
~~~

`issuer-uri` must match `iss` in the token exactly, and `jwk-set-uri` must be the real JWKS endpoint published by the Authorization Server. The path in this example only illustrates one deployment style; other Identity Provider products may use different URLs. When supplying `jwk-set-uri` directly, the API does not need metadata discovery at startup, yet it must still validate the issuer.

### 7.2. Adding audience verification to default JWT validation

In the API, you can define a `JwtDecoder` that verifies signatures with JWKS and applies validators for issuer, lifetime, and audience:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwkSetUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

        // Includes default checks, lifetime, and issuer.
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        // Tokens for other APIs must be rejected, even if signed by the same issuer.
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Token audience is not accepted",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));

        return decoder;
    }

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This snippet focuses on the token contract and endpoint authorization. If this is a REST API using Bearer tokens exclusively, configure CSRF, sessions, and other filter chains according to your real architecture. Never copy API settings to cookie-based web routes while omitting CSRF protection.

In Spring Security, when receiving a JWT with a `scope` or `scp` claim in a supported format, default authorities carry the `SCOPE_` prefix. Thus `orders.read` in the token matches `hasAuthority("SCOPE_orders.read")`. If your issuer uses custom claim names or role conventions, configure a `JwtAuthenticationConverter` rather than assuming default mapping always fits.

**Crucial boundary:** `hasAuthority("SCOPE_orders.read")` only protects the operation category. The service handling `/api/orders/{id}` must still check whether the current user/service is allowed to view that **specific order**.

### 7.3. Checking permissions on the resource

To pass the verified identity from the access token into business logic:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orders;

    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    OrderDto getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        return orders.getVisibleOrder(
                id,
                jwt.getIssuer().toString(),
                jwt.getSubject());
    }
}
~~~

`getVisibleOrder` must look up the record within the caller's allowed scope and check ownership, tenant, roles, or other conditions, denying access if unmet. The snippet above illustrates **passing the verified subject/issuer** to the service; it does not prove the service performed authorization checks itself. If the API also supports Clients without end users, distinguish principal type, Client, and service-to-service policies before querying data.

### 7.4. If using opaque access tokens

When using opaque tokens, the Resource Server can validate tokens via introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://identity.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
~~~

The API must verify the token's `active` status and **ensure audience, permissions, and identity from the introspection result satisfy the contract**. Not every introspection response returns the same fields; if details needed to confirm the token targets the Orders API are missing, align with the Authorization Server on how to publish/verify them rather than skipping the audience condition. Introspection does not eliminate the responsibility to enforce business-level permissions.

## 8. Separating the OIDC login contract from the API call contract

In an Authorization Code flow with OIDC, a Client may request `openid profile` while also requesting `orders.read` to access the Orders API. The contract must separate:

| Concern | OIDC Client (login) | OAuth2 Resource Server (calling API) |
| --- | --- | --- |
| Primary token used | **ID token** to confirm login | **Access token** to protect the API |
| Expected audience | OIDC Client's `client_id` | API identifier, e.g., `orders-api` |
| Identity data | `sub` and OIDC claims, validated per OIDC | Subject/Client/scopes in the access token per API contract |
| API permission checks | Does not decide on behalf of the API | Validates token and enforces policy |
| Other key claims | `nonce` when applicable, `auth_time` when requested, related OIDC checks | `iss`, `aud`, lifetime, scope/authority, tenant, and business permissions |

The Client must only treat an ID token as authentication proof after running the **proper OIDC validation steps** (signature, issuer, audience, nonce, and related conditions). The Resource Server must not accept an ID token as an API access credential.

If Shop BFF both logs users in with `oauth2Login()` and calls Orders API with `oauth2Client()`, those two configurations handle the Client side. The Orders API—whether in a separate process or the same process—must still enable `oauth2ResourceServer()` for endpoints receiving Bearer tokens.

## 9. Scenarios illustrating contract violations

### Scenario A — Valid issuer, wrong audience

The Client receives a token with `aud = payments-api` and sends it to Orders API. The signature is valid and the user identity is valid, yet Orders API must reject it (typically 401 because the token is invalid for this API). The fix is for the **Client to request a token for the right resource** and the Authorization Server to issue the right audience—never relax Orders API rules to accept any token from the same issuer.

### Scenario B — Valid audience, missing permission

A token has `aud = orders-api`, `scope = orders.read`. The Client sends `POST /api/orders`, which requires `orders.write`. The API denies with 403. The Client must request the proper scope per policy; the Authorization Server grants it only if the Client/subject is allowed. Never bypass permissions via Client-sent headers like `X-Role: admin`.

### Scenario C — Sufficient scope, data belongs to another subject

`user-842`'s token has `orders.read` and the right audience, yet order 42 belongs to `user-999`. The API must deny it (403 or 404 depending on resource-hiding policy). Relying solely on scope causes cross-user/cross-tenant data leaks.

### Scenario D — Using an ID token to call an API

Shop Web receives an ID token with `aud = shop-web` and sends it to Orders API. The API must reject it because it is a login token for the Client, not an authorized token for Orders API.

### Scenario E — Treating Client Credentials as a user

A sync job uses `client_credentials` with scope `orders.read`. API code takes `sub`, looks up a customer profile with that ID, and applies user order-viewing rules. That breaks the subject model: the API must enforce a **service-principal policy** allowing only explicitly granted operations/data sources.

### Scenario F — Forwarding tokens across multiple APIs

A Client calls Gateway API with `aud = gateway-api`; Gateway wants to call Orders API. Forwarding the raw token is only valid if Orders API's contract **genuinely** permits that audience and delegation model. The standard approach is requesting a dedicated access token for Orders API or using token exchange supported by the Authorization Server.

## 10. Error conventions, logging, and contract evolution

To help Clients diagnose causes, APIs should standardize error behavior per the Bearer token specification (RFC 6750):

| Condition | Typical response | Party usually needing to act |
| --- | --- | --- |
| Missing token, expired, invalid signature/issuer/audience | **401 Unauthorized**, possibly with `WWW-Authenticate: Bearer ...` | Client obtains valid token / logs in again; AS/API verify configuration |
| Valid token lacking required scope | **403 Forbidden**, possibly noting `insufficient_scope` | Client requests proper permissions; AS decides grant |
| Valid token and scope, lacking record permission | **403** or **404** per security policy | API enforces policy; Client cannot self-escalate |
| Valid token, sufficient scope and business permissions | **2xx** or matching business code | API processes request |

When logging for diagnostics, record **request/correlation ID, issuer, audience, Client, verified subject (when policy permits), error type, and scope names**, avoiding logging raw Bearer tokens or sensitive token contents. In multi-tenant systems, restrict log access appropriately.

Contracts evolve when adding APIs, adding audiences, migrating issuers, or changing claim formats. Rollouts must be coordinated across parties:

1. **Align on version/change:** The API defines the new audience and permissions; the Authorization Server configures issuance capability; the Client prepares to request new tokens.
2. **Support controlled transition windows:** Accept multiple issuers/audiences **only if** policy truly permits it and each side is fully validated; avoid wildcards or disabling checks just to "make it work."
3. **Rotate keys safely:** The API fetches/refreshes JWKS via library mechanisms and trusts only approved algorithms; never pin a single public key forever.
4. **Evaluate revocation and lifetimes:** Locally validated JWTs remain valid until `exp` unless additional revocation controls are added; choose lifetimes and policies based on risk.
5. **Monitor 401/403 spikes during deployment:** Sudden increases may reveal mismatched issuer, audience, scope, or claim-mapping configuration.

## 11. Contract template for teams implementing together

An API integration document can provide a concise yet verifiable template like this:

~~~yaml
api: orders-api
issuer: https://identity.example.test/realms/shop
accepted_token_use: oauth2_access_token
access_token_format: jwt
expected_audience:
  - orders-api
accepted_clients:
  - shop-web
  - batch-sync-service
scopes:
  orders.read: Read orders allowed by the caller's data policy
  orders.write: Create or update orders allowed by policy
identity:
  user: "Pair (iss, sub); tenant membership checked by API"
  service: "client_credentials subject/client mapped to service policy"
authorization:
  GET /api/orders/{id}: "orders.read + ownership/tenant policy"
  POST /api/orders: "orders.write + tenant creation policy"
errors:
  invalid_or_missing_token: 401
  insufficient_scope_or_permission: 403
~~~

This is a **contract documentation template**, not a standard configuration format automatically read by Spring Security or OAuth 2.0. Teams must translate each clause into Client registrations, Authorization Server issuance rules, Resource Server validator configuration, and business-layer authorization checks.

When defining the contract, always evaluate four questions together: **"Who issued it?"** (`iss`), **"Whom is the token for?"** (`aud`), **"What is permitted?"** (`scope` and policies), and **"Whom does it represent?"** (`sub`, Client, and grant context). In a Spring Security Resource Server, accept a token only after all relevant conditions are verified, then enforce permissions on the actual resources.
