# Trust Boundaries Between Token Issuer, API, and Downstream Services

In a system using **Spring Security OAuth 2.0 Resource Server**, an access token is not a "system-wide master pass." A token represents a set of claims asserted by a **trusted issuer**, meant for **one or more specific resources**, within a **valid time window**. Each API receiving a token must determine for itself whether those assertions suffice to permit the requested operation.

This is a matter of **trust boundaries**: whenever data or identity crosses from one domain of control to another, the receiving party must validate what it relies on to make decisions. This occurs at least three times in a multi-service application:

1. The token issuer (Authorization Server/Identity Provider) issues assertions that an API can verify.
2. The Resource Server receives a request from a client, verifies the token, and decides permissions on its own resources.
3. The Resource Server calls a downstream API/service, where a new authentication and authorization boundary begins.

The goal of this lesson is to clarify **who trusts whom, what they trust, why that trust is bounded**, and how to express those boundaries when implementing Spring Security.

## 1. Parties and responsibilities

Consider a retail system with a web application, an order management service, and a payments service:

| Component | Role | What this component controls |
|---|---|---|
| **Client** (web, mobile, another backend) | Requests tokens and calls APIs | How tokens are stored and sent; the HTTP requests it constructs |
| **Authorization Server/IdP** | Authenticates principals per appropriate flow, applies issuance policies, and issues tokens | Signing keys, metadata, issuer, granted audience/scopes, token lifetimes |
| **Orders API** (*Resource Server A*) | Protects order data and business logic | Endpoint access conditions, which orders can be viewed/modified, how downstream services are called |
| **Payments API** (*Resource Server B*) | Protects payment data and business logic | Access conditions for payment operations, caller identity, permissions on payment records |
| **Gateway / service mesh** (if present) | Routing, transport protection, optional edge authentication | Network configuration, TLS/mTLS, access control at ingress points |

**The Authorization Server is not every API**. In OAuth 2.0, it issues access tokens; the Resource Server accepts tokens to protect resources. A system can use the same IdP for multiple APIs, yet **each API still makes its own authorization decisions**.

OIDC (OpenID Connect) adds an identity authentication layer on top of OAuth 2.0. In particular, distinguish:

| Token type | Primary purpose | Intended consumer |
|---|---|---|
| **Access token** | Grants access to resources/APIs within issued scopes | The matching Resource Server |
| **ID token** (OIDC) | Conveys user authentication results to the OIDC client | The OIDC client, typically with `aud` set to the app's `client_id` |
| **Refresh token** | Requests a new access token per issuance policy | OAuth client exchanging with the Authorization Server |

Never use an ID token in place of an access token to protect an API. Even an ID token with a valid signature does not prove the bearer is permitted to call `Orders API`; its `aud` typically targets the client application. Likewise, never send a refresh token to a Resource Server as a bearer credential.

### Boundary diagram

```mermaid
flowchart LR
    C["Client\nWeb / Mobile"] -->|"1. Obtain access token"| I["Authorization Server / IdP"]
    I -->|"Token A: iss, aud=orders-api, scope"| C
    C -->|"2. Bearer Token A"| A["Orders API\nResource Server A"]
    A -->|"3. Token B or service credential"| B["Payments API\nResource Server B"]
    I -.->|"Metadata / JWKS or introspection"| A
    I -.->|"Metadata / JWKS or introspection"| B
    subgraph T1["Boundary 1: Issuer → Orders API"]
      A
    end
    subgraph T2["Boundary 2: Orders API → Payments API"]
      B
    end
```

The dashed arrows from the IdP to the APIs represent the ability to **verify token provenance** via JWKS or introspection; they do not mean every access token issued by the IdP is valid for every API.

## 2. Boundary one: how far does an API trust the token issuer?

Suppose a client sends:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

The `Authorization: Bearer ...` header is merely data supplied by the caller. **Possessing a token does not prove the token is valid**. Orders API must verify the token according to preconfigured policies.

### 2.1. When the access token is a JWT

Illustrative JWT payload example (shortened, not a usable real token):

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "iat": 1794600000,
  "nbf": 1794600000,
  "exp": 1794603600
}
```

A JWT-based Resource Server must validate these layers:

1. **Allowed issuer**: `iss` matches the exact trusted issuer configured for the API. Never pick an arbitrary issuer simply because the payload declares it.
2. **Signature and algorithm**: the signature matches a key published by the trusted issuer; the signing algorithm belongs to the allowed set. Treat `kid` as a selector within the trusted JWKS, never as an arbitrary key source address.
3. **Validity window**: `exp` has not passed, `nbf` has been reached, and applicable time checks succeed. Small, intentional clock skew may be permitted.
4. **Token audience (`aud`)**: Orders API accepts only tokens whose configured audience includes it, such as `orders-api`.
5. **Permissions and business constraints**: scopes/authorities suffice for the operation; the principal has rights over the specific order and tenant.

Common claims:

| Claim | Question it helps answer | Boundary notes |
|---|---|---|
| `iss` | Who issued the token? | Must match the configured list of trusted issuers |
| `aud` | Which API/resource is the token meant for? | Missing or wrong audience must be rejected for this API |
| `sub` | Which subject does the token refer to? | Does not imply access to every record; in multi-issuer environments, pair `iss` + `sub` |
| `exp`, `nbf`, `iat` | Is the token valid in time? | `iat` is useful for policies; does not replace `exp`/`nbf` |
| `scope` / `scp` | What permission scopes did the issuer grant? | Input to authorization, insufficient by itself for per-resource access |
| `client_id`, `azp` (if present) | Which app/client is associated with the token? | Representation depends on issuer; do not treat as default access rights |
| `tenant_id`, `roles` (custom claims) | Tenant/role context per system contract? | Trust only after token validation and policy checks, never accept from client-set headers |
| `jti` (if present) | Token identifier for correlation/auditing? | Does not create replay protection or revocation by itself |

For JWTs where `aud` is an array, the API checks for **the presence of its specific audience** in the array. Issuing a token for multiple audiences may be valid under an issuance contract, yet also widens the blast radius if stolen; prefer narrow audiences aligned with your architecture.

**A valid signature only proves the token was not tampered with after being signed by a party holding the corresponding key**. A signature does not by itself prove the token was issued for the current API, is unexpired, or authorizes the user to view order `ord-123`.

### 2.2. Public keys, discovery, and JWKS

With asymmetrically signed JWTs, the IdP keeps the private key to sign; the API uses the public key to verify. The API typically retrieves issuer metadata and JWKS over HTTPS:

```text
Configured trusted issuer:
  https://idp.example.com/realms/shop

OIDC/OAuth Metadata:
  issuer       -> expected issuer name
  jwks_uri     -> source of keys to verify signatures

JWT header:
  alg          -> signing algorithm
  kid          -> key to select from the trusted JWKS
```

Critical boundary: **trusted configuration sources must originate from the API itself or its configuration system**, never from an `iss`, `jku`, `x5u`, or arbitrary URL inside an unverified token. Never allow an attacker's token to dictate which server the API fetches verification keys from; otherwise, an attacker can stand up their own key source or trigger unintended network requests.

Practical deployment points:

- Use HTTPS, verify TLS certificates, and protect issuer/JWK endpoint configuration.
- Support key rotation: JWKS may contain multiple keys, with `kid` selecting the matching key; align cache/refresh with library mechanics and the IdP's rotation schedule.
- Restrict accepted algorithms; never accept "token says `alg=none`, so skip signature verification."
- JWKS fetch failures can affect validation of tokens signed by newly rotated keys; design for temporary IdP/JWKS disruptions.
- Treat JWKS as **public keys to verify issuer authenticity**, not a directory of users or access permissions.

### 2.3. When the access token is an opaque token

An access token **does not have to be a JWT**. If the token is an opaque string that cannot be parsed locally, the Resource Server can use **token introspection** per agreement with the Authorization Server:

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Orders API
    participant I as Authorization Server
    C->>A: Bearer opaque access token
    A->>I: Introspection (API authenticates itself)
    I-->>A: active, scope, aud, sub, iss... per implementation
    A->>A: Validate active + audience + permissions + resource
    A-->>C: API result
```

Introspection returns status and metadata per the IdP contract. The API must still validate audience/scopes and business authorization where available; an `active: true` result must never be treated as system-wide permission. The credentials the Resource Server presents to the introspection endpoint must be managed as a service secret.

Comparing the two approaches:

| Characteristic | Self-verified JWT | Opaque token + introspection |
|---|---|---|
| Token verification | Primarily at the API using verification keys and claims | API queries the Authorization Server |
| Request-time dependency on IdP | Usually lower once needed keys are cached | Higher when introspecting online on every request |
| Revocation before `exp` | Hard to enforce immediately with offline JWT checks alone | Can observe revoked status via introspection |
| Visible data | Claims embedded inside the JWT | Metadata returned by the introspection endpoint |
| Cost/latency | Local cryptographic verification | Network call, introspection auth, cache considerations |

If caching introspection results for performance, you must accept the delay window between revocation and cache expiration. Even with JWTs, achieving near-immediate revocation typically requires adding short token lifetimes, server-side state, or other mechanisms rather than relying on signatures alone.

## 3. Boundary two: a valid token does not mean the operation is permitted

Once Spring Security authenticates a bearer token, the API learns certain facts about the subject and issued permissions. It **does not automatically know** whether that subject may view a specific order, edit a shipping address, or issue a refund.

Example:

```text
Valid token:
  iss   = trusted IdP
  aud   = orders-api
  sub   = user-842
  scope = orders.read

GET /api/orders/ord-123

Order ord-123:
  owner = user-901
  tenant = tenant-b
```

The `orders.read` scope indicates the client may invoke the order-reading capability, yet **is not permission to read someone else's order**. Orders API must enforce policies on the specific entity—for example, that the owner matches the current subject, or the user holds sufficient business permissions within the right tenant. Never accept a `tenant_id` from a URL/header and treat it as proof the caller belongs to that tenant.

You can think of the allow decision as an intersection:

```text
Allow request
  = token is authenticated and intended for this API
  AND has permission to invoke the action (scope/authority)
  AND has permission on the data object (owner, tenant, status, business rules)
  AND satisfies additional conditions (if any)
```

### 3.1. HTTP 401 and 403

These two cases express the boundary:

- **401 Unauthorized**: no valid authentication for the protected resource; for example, missing bearer token, invalid signature, wrong issuer, wrong audience, or expired token.
- **403 Forbidden**: authenticated, yet lacking permissions for the operation/resource, such as a missing scope or not owning the order. An API may return `404` in some cases to avoid disclosing resource existence, depending on policy.

The `WWW-Authenticate: Bearer` header may carry OAuth error codes such as `invalid_token` or `insufficient_scope`; never put tokens, secrets, or sensitive internal details in responses.

### 3.2. Example Resource Server configuration with Spring Security 6

This example is for a REST API accepting bearer **JWTs**. The API accepts tokens from the configured issuer and requires the `orders-api` audience. Replace the issuer and audience names with values matching your deployment environment.

```yaml
# application.yml
app:
  security:
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
```

```java
@Configuration
@EnableMethodSecurity
public class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        return http
            // Suitable for REST APIs accepting only Bearer headers, not using login session
            // cookies to authenticate state-changing operations.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String requiredAudience) {

        // Fetch key configuration from an issuer the application explicitly trusts.
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

        // Check default conditions (including timestamps)
        // and require an exact issuer match.
        OAuth2TokenValidator<Jwt> defaultChecks =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
            jwt.getAudience().contains(requiredAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token is not intended for this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultChecks, audienceCheck));
        return decoder;
    }
}
```

Classes in the example belong to `org.springframework.security.*` packages, while `@Configuration`, `@Bean`, `@Value`, and `HttpMethod` belong to Spring Framework. This configuration pattern uses the Spring Security 6 API style; align with your specific version when applying it.

Notable details:

- `oauth2ResourceServer().jwt()` configures bearer JWT authentication for the API. The API does not handle interactive login or token issuance here.
- `JwtDecoder` is created from an **issuer configured by the application**, then validates issuer, timestamps, and audience. When providing a custom `JwtDecoder` bean, ensure all required validators are attached properly.
- By default, Spring Security converts scopes into authorities prefixed with `SCOPE_`, such as `orders.read` becoming `SCOPE_orders.read`. If the IdP uses a different claim/format, configure a corresponding converter.
- URL rules provide authorization **at the operation level**. Endpoints must still look up permissions for each specific order, tenant, and business condition.
- Disabling CSRF in the example is appropriate only when endpoints authenticate strictly via explicitly sent bearer tokens rather than automatically attached cookies. If the application also uses sessions/cookies, design CSRF protection for that flow.

An object-level permission check in the service layer can follow this pattern:

```java
public OrderDto getOrder(String orderId, Jwt jwt) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    // Example only: a real application may use a policy service
    // to evaluate tenant, admin roles, and order status.
    boolean ownerMatches = order.getOwnerSubject().equals(jwt.getSubject());
    boolean tenantMatches =
        order.getTenantId().equals(jwt.getClaimAsString("tenant_id"));

    if (!ownerMatches || !tenantMatches) {
        throw new AccessDeniedException("Order access denied");
    }

    return toDto(order);
}
```

Here `jwt` is the JWT **already validated by Spring Security**, obtained from the endpoint/controller authentication context—not a payload decoded and passed in by the caller. Storing `ownerSubject` must preserve identifier scoping: if multiple issuers are accepted, never treat `sub` alone as a globally unique identifier.

### 3.3. A bearer token authenticates the bearer

A bearer token works like this: whoever holds it can use it, within API policy limits, until it expires or is invalidated through an appropriate mechanism. The API generally **does not know whether the current HTTP sender is the original party that obtained the token**.

Therefore, enforce HTTPS across transport hops, avoid writing raw tokens into logs, URLs, analytics, errors, or traces; keep token lifetimes short and protect storage locations. When replay resistance or binding a token to a specific sender is required, consider sender-constrained mechanisms such as mTLS-bound access tokens or DPoP, keeping in mind that **the Resource Server and infrastructure must actually verify that proof of binding**. Merely seeing a claim stating the token "is bound" is not enough.

## 4. Boundary three: Orders API calls Payments API

This is where it is very easy to confuse "a service inside the internal network" with "a trusted service."

Suppose:

```text
Client ── Token A (aud=orders-api) ──▶ Orders API
Orders API ── ? ──▶ Payments API
```

Orders API has validated Token A. That **does not automatically grant Orders API the right to use Token A to call Payments API**. Payments API has its own audience, scopes, allowed callers, and resource policies.

If Orders API forwards Token A as-is when `aud=orders-api`, Payments API must reject that token because **the token is not intended for it**, even if both APIs trust the same IdP and use the same JWKS.

### 4.1. Three strategies for establishing identity on downstream calls

| Approach | When appropriate | What does Payments API identify? | Boundary that must hold |
|---|---|---|---|
| **Token relay / pass-through** | The inbound token is **permitted for Payments API** under the issuance contract and both APIs' policies | The principal and permissions already carried in the forwarded token | Payments API independently verifies `iss`, `aud`, lifetime, and permissions; never relay purely for convenience |
| **Token exchange / on-behalf-of** | Payments API needs the user's authorization context, yet the inbound token is meant only for Orders API | A new token meant for `payments-api`, carrying user subject and actor/delegation info per IdP support | The IdP decides whether exchange is allowed, plus target audience and scopes; Payments API accepts only the new token |
| **Client credentials** | Orders API performs a service function independent of user permissions, e.g. recording a system event | The service client identity of Orders API | Issue only minimal machine-to-machine scopes; Payments API does not infer an end user from a service token |

Another strategy is using platform workload identity or service identities, provided the receiver has an appropriate verification mechanism. **TLS/mTLS protects the channel or authenticates the service, yet does not replace OAuth authorization for users/resources**.

#### Approach A: Intentional token relay

Forward the inbound access token only if the token and multi-party contract allow Payments API to accept it. For instance, the IdP issues a token whose `aud` includes both `orders-api` and `payments-api` with sufficiently narrow scopes. Payments API still independently authenticates and authorizes.

Limitation: the same bearer credential passing through multiple services increases exposure surface; broader audiences increase impact if a token is stolen. Never relay ID tokens or refresh tokens to downstream APIs.

#### Approach B: Token exchange / on-behalf-of

In a flow supported by the IdP, Orders API exchanges Token A for Token B targeted at Payments API. For example:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant I as Authorization Server
    participant O as Orders API
    participant P as Payments API
    C->>I: Request access token for orders-api
    I-->>C: Token A: aud=orders-api
    C->>O: Request + Token A
    O->>O: Verify Token A and order permissions
    O->>I: Token exchange Token A, request aud=payments-api
    I-->>O: Token B: aud=payments-api, limited scope
    O->>P: Call API + Token B
    P->>P: Verify Token B + payment permissions
    P-->>O: Result
    O-->>C: Request result
```

Here **the Authorization Server decides** whether exchange is permitted, which audience can be targeted, maximum scopes, and whether user context is preserved. IdP products use different names/mechanisms; never assume every IdP supports RFC 8693 or an equivalent on-behalf-of flow. The new token must be verified at Payments API like any other access token.

Expected example:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["payments-api"],
  "scope": "payments.create",
  "exp": 1794600900
}
```

The payload above only illustrates the target token's `aud` and `scope`. How actor/delegation, client, and subject are represented varies by protocol, IdP, and policy; **never infer "acting on behalf of user" authority from `sub` alone**.

#### Approach C: Client credentials between services

If Orders API calls Payments API under its own service identity:

```text
Orders API ── client_credentials ──▶ Authorization Server
Orders API ◀── Token S (aud=payments-api; service permissions) ── IdP
Orders API ── Token S ──▶ Payments API
```

Payments API authenticates Orders API as a **service principal**. Token S does not inherently represent `user-842`; Orders API must verify the user's permissions itself before issuing internal commands. If Payments API also needs to know which user authorized the action, design a verifiable delegation mechanism rather than arbitrarily attaching `X-User-Id: user-842`.

A secure design typically separates scopes: `payments.create.internal` reserved for authorized services; `payments.read` for external APIs if needed. Service permissions must stay narrow, tokens must have appropriate lifetimes, and client secrets must never appear in source code/logs.

### 4.2. "Confused deputy" when an intermediary API holds broad privileges

A *confused deputy* occurs when a privileged service is tricked into performing an action the requester is not authorized for. Example:

1. User A is allowed to view A's orders, and calls Orders API with B's `orderId`.
2. Orders API validates the token yet **does not check permission on `orderId`**.
3. Orders API uses a service token carrying `payments.refund.internal` to ask Payments API to refund B's order.
4. Payments API only sees the call came from Orders API holding refund privileges; the system has granted access beyond intent.

Defense combines both boundaries: Orders API checks the user's permission on the exact order before making the call, while Payments API checks service permissions, operation type, and payment rules (status, limits, order/payment validity). For sensitive operations, consider verifiable authorization proofs, idempotency, and auditing.

## 5. Do gateways, proxies, and internal networks change the boundary?

A gateway can validate JWTs at the edge, blocking many invalid requests early. However, two distinct architectures exist:

**Each Resource Server verifies tokens itself:** the gateway forwards valid bearer tokens to each API; each API checks its own issuer, audience, and permissions. This keeps boundaries crisp when there are multiple call paths, many services, or any risk of bypassing the gateway.

**Delegating authentication to the gateway:** downstream APIs trust authentication results passed from the gateway over a protected internal channel. If choosing this pattern, ensure the API **can only receive traffic from the trusted gateway/source**, connections are authenticated (e.g. mTLS or equivalent), the gateway strips/overwrites client-supplied identity headers, and the API authorizes based on the protected identity data. If an external caller can connect directly and set `X-User-Id`, `X-Roles`, or `X-Tenant-Id`, the boundary is broken.

Dangerous example:

```http
GET /internal/payments HTTP/1.1
X-User-Id: admin
X-Roles: SUPER_ADMIN
```

These headers **are not authentication proof** if they arrive straight from a client or can be forged on any hop. Internally propagated identity must have an explicit source-trust contract, tamper/spoof protection on the wire, and privilege separation.

Never equate:

- **Network trust**: is a network connection to the service allowed?
- **Service authentication**: which workload/service is actually calling?
- **User/delegation authentication**: which user or party is the service acting on behalf of?
- **Authorization**: is this specific action on this specific object allowed?

An mTLS connection can answer "the connecting workload is Orders API," yet cannot by itself answer "user-842 is allowed to refund payment-777."

## 6. Common pitfalls across boundaries

| Scenario | Why it is dangerous | How to address |
|---|---|---|
| Orders API accepts any JWT signed by the same IdP | Tokens issued for another API can be replayed at Orders API (*token substitution*) | Validate `iss` **and `aud` for Orders API** |
| API reads issuer or `jku` from an unverified token to fetch keys | Caller controls the key source and can trigger unintended URL fetches | Configure an allowlist of issuers and key endpoints; never follow arbitrary URLs from tokens |
| Using an ID token as a bearer access token | ID tokens target OIDC clients, with different target semantics | Accept only access tokens satisfying the Resource Server contract |
| Seeing `SCOPE_orders.read` and returning all orders | Scopes do not determine ownership/tenant | Check permissions at the resource and business levels |
| Orders API forwards a token with `aud=orders-api` to Payments API | Payments API is not in the token's audience | Use token exchange or appropriate credentials; Payments API verifies the token it receives |
| Payments API trusts `X-User-Id` alone | Header can be forged by clients or misrouted by gateways | Trust identity only from guaranteed sources over authenticated channels |
| Accepting tokens from any tenant/issuer | A valid token in one domain gets applied to another | Restrict issuer/tenant per route, match tenant against resource |
| Assuming a JWT loses permissions immediately on logout | Offline JWTs can remain valid until `exp` | Tune TTL and implement revocation/status checks when business requires |
| Putting bearer tokens in URLs or logs | Tokens leak via logs, history, and monitoring tools | Pass in Authorization header; scrub tokens from telemetry |
| Relying solely on "service is inside the VPC" | Internal routing proves neither identity nor authorization | Authenticate workloads and enforce policies at every receiver |

### 6.1. Multi-tenant and multiple issuers

In SaaS, an API may accept tokens from multiple tenants or multiple issuers. That is no reason to blindly trust whatever `iss` appears in a JWT.

A multi-issuer design requires:

1. An administratively managed allowlist/registry of trusted issuers; select the matching validator from that registry.
2. Validating **every** token for the right issuer, signature, audience, and time constraints.
3. Mapping subject and tenant according to contract; never take a client-supplied `tenant_id` as the source of truth.
4. Binding all data queries and business operations to the verified tenant; never rely solely on ID prefixes or route paths.

For instance, `sub=user-1` issued by two different issuers may be two different people. Even under the same issuer, roles and permissions may vary by tenant; all tenant privileges must be evaluated against explicit policy.

### 6.2. Trust validity over time

Accepting a JWT at time T only proves that validation conditions and active policies matched at T. User deletion, role changes, or permission revocation are not always reflected immediately in already-issued tokens. Sensitive systems may therefore need a combination of:

- Short-lived access tokens with tight audience/scope bounds.
- Business permission checks against live data in the API.
- Introspection or status/revocation mechanisms where policy demands.
- Key rotation governance and incident response for compromised signing keys.

Choosing a short TTL reduces the exposure window of a leaked token, yet does not replace token protection and authorization controls.

## 7. Analyzing three end-to-end scenarios

### Scenario A — User views their own order

```text
1. Client obtains access token:
   iss   = https://idp.example.com/realms/shop
   aud   = orders-api
   sub   = user-842
   scope = orders.read

2. Client calls GET /api/orders/ord-123 with Bearer token.

3. Orders API:
   - verifies signature / issuer / timestamps / audience;
   - derives authority SCOPE_orders.read;
   - loads the order and checks user-842 is the owner in the right tenant.

4. If all conditions pass: returns permitted data.
```

Expected outputs vary when changing one condition:

| Change | Expected design outcome |
|---|---|
| Invalid token signature | 401 |
| Validly signed token but `aud=payments-api` | 401 |
| Expired token | 401 |
| Valid token without `orders.read` | 403 |
| Valid token with `orders.read`, order belongs to someone else | 403 or 404 per resource-hiding policy |
| Both token and permission on the specific order are valid | Process request and return only permitted fields |

### Scenario B — Placing an order needs to create a payment request

```text
Client -> Orders API:
  access token A: aud=orders-api, scope=orders.create

Orders API:
  verifies A, checks order creation permission and order data
  obtains Token B appropriate for Payments API

Orders API -> Payments API:
  access token B: aud=payments-api,
                  scope=payments.create or corresponding service permission

Payments API:
  verifies B, checks payment creation permission and payment rules
```

If using token exchange, Token B can carry user context according to IdP capabilities. If using client credentials, Token B authenticates Orders API and Payments API must enforce policies tailored to that service. In **both** cases, Payments API does not skip checks just because the call originates from the internal network.

### Scenario C — Periodic reconciliation job

A scheduled job has no logged-in user:

```text
Reconciliation Job
  -> Authorization Server: client_credentials
  <- Token R: aud=payments-api, scope=payments.reconcile
  -> Payments API: Authorization: Bearer Token R
```

Payments API authenticates the service principal and allows only the reconciliation endpoint. Never invent a user `sub` to "mimic" an interactive flow. If the job genuinely requires user authority, design an appropriate authorization flow.

## 8. Designing boundaries in code and infrastructure

A practical way not to lose track of boundaries is to **place each decision with the party that owns the resource**:

| Decision | Primary responsible party |
|---|---|
| Who may log in, and which clients may request tokens? | IdP/Authorization Server |
| Was the token issued by a trusted issuer, unexpired, for the right audience? | Receiving Resource Server |
| Which scopes/authorities does an endpoint require? | Resource Server |
| Does the user/tenant have access to this record? | Service owning the business logic and data |
| May service A obtain credentials to call B? | IdP / workload identity infrastructure / service grant policy |
| Does service B accept credentials from A, and what may A do? | Service B |
| Are transport channels, secrets, and logs secure? | Channel, service, and platform operators |

When building a new flow, be able to answer these questions with concrete configuration and code:

1. **Which issuers are trusted?** Does the API have a stable allowlist or multi-issuer registry? Where do verification keys come from?
2. **Who is the token for?** Which `aud` does the API actually enforce? Could an ID token be accepted by mistake?
3. **Who can do what?** Scopes/authorities open only the right endpoints—where are object and tenant permissions checked?
4. **With what identity does the next hop proceed?** Relay, token exchange, or client credentials? Are permissions, audience, and lifetime narrow enough?
5. **What if a token/header is stolen or forged?** How are TLS/mTLS, header sanitization, secrets, logging, expiration, and revocation handled?
6. **If one layer is bypassed, how does the next layer respond?** Does the downstream API still independently verify authentication and authorization?

## 9. Remembering the trust model

A secure OAuth 2.0/OIDC system keeps three answers separate:

> **The IdP asserts** who the token represents, under what conditions it was issued, and which resources it targets.  
> **The Resource Server verifies** whether that token is trustworthy and intended for it.  
> **The service owning the business domain decides** whether an operation on specific data is permitted.

Whenever a Resource Server calls another service, the process restarts at a new boundary. **Sharing an IdP, an internal network, or a JWT signature does not merge two APIs into a single permission domain.**

### Standards for deeper reference

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
