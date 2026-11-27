# Identifying the Target API, Trusted Issuer, and Access Purpose

An **OAuth 2.0 Resource Server** should not accept an access token merely because the token has a valid signature or was issued by a familiar login system. Before processing a request, the API must clearly establish the three elements of the **access token contract**:

1. **Which API is allowed to receive the token?** This is the **target audience** (audience/resource), typically expressed via the `aud` claim in a JWT or equivalent information from an introspection mechanism.
2. **Which issuer is trusted?** This is the **issuer** (issuing authority), typically expressed via the `iss` claim, bound to a preconfigured key set and validation rules.
3. **What is the token used for?** This is the **purpose and permission scope**, expressed by `scope`/`scp`, resource-level policies, and sometimes agreed-upon custom claims.

These three questions correspond to **the right recipient**, **the right source**, and **the right purpose**. Separating them prevents a token that is cryptographically valid—but issued for a different system—from being used to access the current API.

This lesson is set in the context of the **Spring Security OAuth 2.0 OIDC Resource Server** module. The endpoints, issuers, audiences, scopes, and tokens appearing below are illustrative examples; replace them with the values agreed upon by your Authorization Server and API administration teams.

## 1. Position of the Resource Server in OAuth 2.0 and OIDC Flows

A client obtains an access token from an **Authorization Server** and sends it to a **Resource Server** to access resources. If the Authorization Server also provides OpenID Connect, it acts as an **OpenID Provider** for the OIDC client. This does not change the core rule: the API uses an **access token**, never substituting an **ID token**.

~~~mermaid
sequenceDiagram
    participant Client as OAuth 2.0 Client
    participant AS as Authorization Server / OIDC Provider
    participant Orders as Orders API (Resource Server)
    Client->>AS: Request token using the appropriate grant
    Note over AS: Validate client, permissions, and requested resource
    AS-->>Client: access_token with issuer, audience, scope
    Client->>Orders: Authorization: Bearer <access_token>
    Orders->>Orders: 1. Is the issuer trusted?
    Orders->>Orders: 2. Is the audience intended for Orders API?
    Orders->>Orders: 3. Does scope/policy allow the operation?
    Orders-->>Client: 2xx or 401/403
~~~

The request might look like:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

The `Authorization: Bearer ...` header only **transports the credential**. It does not indicate whether the token is valid, whether it was issued for the Orders API, or whether it has permission to read order 42. Those conditions must be verified at the Resource Server according to the defined contract.

## 2. Distinguishing Issuer, Audience, Scope, and Principal

| Component | Question to Answer | Example | Security Condition |
|---|---|---|---|
| `iss` — issuer | **Who** issued the token? | `https://login.example.test/realms/company` | Must belong to the API's trusted issuer list, match exactly, and have its signature/token source verified |
| `aud` — audience | **Which API/resource** is the token intended for? | `orders-api` | Must contain an audience identifier accepted by this API |
| `scope` / `scp` | **Which group of actions** is the token allowed to perform? | `orders.read orders.create` | Scopes must be mapped and checked for the specific operation |
| `sub` — subject | **Who/what** does the token represent? | `user-123` or service principal | Only use after the token is authenticated; do not assume it is a human user account |
| `client_id` or equivalent client claim | **Which client** was issued the token? | `web-orders-client` | Useful when policy requires restricting the client, but does not replace audience |
| `exp` / `nbf` / `iat` | **Within what time window** is the token valid? | Unix timestamp | Check expiration and not-before time; account for clock skew |
| `azp` (if present) | Authorized party per token profile/provider | `web-orders-client` | Must be interpreted per specific issuer/profile; not guaranteed in every access token |
| Tenant/organization claim (if present) | **Which organization** does the data belong to? | `tenant-42` | Enforce tenant and business-object binding according to your design |

A JWT may contain the claims above, but that does not mean **every access token must have all of them**. Required claims are determined by the token profile, the Authorization Server conventions, and the API's requirements. With an **opaque token**, equivalent attributes may come from the introspection response or policies guaranteed between the systems.

### Three Conditions Commonly Mistaken for One

Suppose there are two APIs in the same system:

~~~text
Authorization Server: https://login.example.test/realms/company

Orders API:
    Audience = orders-api
    Scope    = orders.read, orders.create

Billing API:
    Audience = billing-api
    Scope    = invoices.read, invoices.pay
~~~

A token with `iss` equal to `https://login.example.test/realms/company` and `aud = ["billing-api"]` must still **not** be accepted by the Orders API, even though both APIs trust the same issuer. Similarly, a token with `aud = ["orders-api"]` is not sufficient to call the create-order endpoint if it only carries the `orders.read` scope.

**Issuer identifies the issuing source; audience identifies where it may be used; scope identifies the kind of action.** Knowing the client ID or subject does not substitute for any of those three conditions.

## 3. Identifying the Target API: Audience and Resource Identity

First, the API design team needs to agree on a stable **resource identifier** for the API itself. For example:

~~~text
Orders API identifier: orders-api
Billing API identifier: billing-api
~~~

Or using a URI identifier:

~~~text
Orders API identifier: https://api.example.test/orders
Billing API identifier: https://api.example.test/billing
~~~

There is no mandatory rule forcing every system to use the exact same string style for `aud`. What matters is that **the Authorization Server actually emits the audience claim according to the contract**, and the Resource Server checks the exact agreed value. If the audience is a URI, that URI serves as an identifier; it does not necessarily have to be the URL that every request calls or an endpoint that can be fetched over HTTP.

Example JWT token properly issued for the Orders API:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

An access token should only be issued with an audience matching the Resource Servers permitted to process it. A token with an overly broad audience or one shared across all APIs can lead to **token substitution / confused deputy**: one API accepts a token that was originally issued for another API.

### Audience Is Not the URL of Each Endpoint

For example, the following requests can use the same `orders-api` audience:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Content-Type: application/json
~~~

`aud = "orders-api"` identifies **the entire API resource allowed to receive the token**. Whether the request hits `GET /api/orders/42` or `POST /api/orders` is resolved next by **scopes and authorization rules**, without forcing each URL to have a separate audience.

Conversely, if an API gateway shares a single hostname across multiple backends, do not assume that `aud = api.example.test` is always enough to distinguish all downstream services. A clear resource boundary is needed for each data group or service that has an independent access policy.

### Audience Can Be an Array

In a JWT, `aud` can be represented as a single string or an array of strings per the JWT specification. For example:

~~~json
{
  "aud": ["orders-api", "reporting-api"]
}
~~~

The Resource Server must verify that **its own allowed audience is present** in the audience set. Just because a token contains multiple audiences does not mean every multi-audience case should be accepted; issuance policy may require a token to target only a single API, or an approved set of resources. Control multi-audience token issuance to limit token exposure.

### Resource Indicators in Token Requests

OAuth 2.0 Resource Indicators (RFC 8707) allow the client to specify the **target resource** using the `resource` parameter if the Authorization Server supports it. Example form-encoded `client_credentials` request:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic <BASE64_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read&resource=https%3A%2F%2Fapi.example.test%2Forders
~~~

The `resource` value is properly form-encoded. The server may use the resource indicator to determine the token's audience; **do not assume `resource` and `aud` will be the exact same literal string** if the system applies identifier mapping. RFC 8707 is an Authorization Server capability: sending the `resource` parameter does not guarantee it is supported or that the token will always have the exact expected `aud`. Always read the contract and inspect actual issued tokens.

## 4. Identifying the Trusted Issuer: Issuer

The **issuer** is the identity of the Authorization Server that issued the token. In a JWT, the `iss` claim is typically a URI and must match **exactly** the value configured on the API:

~~~text
Trusted issuer: https://login.example.test/realms/company
JWT "iss":      https://login.example.test/realms/company   → match
JWT "iss":      https://login.example.test/realms/personal  → mismatch
JWT "iss":      https://login.evil.test/realms/company      → mismatch
~~~

Do not use naive checks like checking whether a string contains `login.example.test`, ignoring the tenant/realm, or automatically trusting every issuer with a similar domain name. Trailing slashes in URIs, realm paths, and normalization can alter the issuer value; configuration must match the actual metadata and issued tokens.

### Metadata, JWK Set, and Signatures

For a signed JWT access token, the Resource Server must verify:

1. **Trusted issuer**: `iss` matches the configured issuer.
2. **Appropriate and trusted key**: the signature is verified using a key from the JWK Set or key source **bound to the trusted issuer**.
3. **Allowed signing algorithms**: restrict the algorithm list according to policy; do not delegate trust decisions to unverified data inside the token.
4. **Time validity**: the token is not expired, is not used before `nbf`, and any additional time limits are enforced.
5. **Audience and API policy**: check application-level conditions; do not stop at signature verification.

For an OpenID Provider or an Authorization Server with metadata, the application can retrieve configuration through the discovery endpoint derived from the issuer. The `jwks_uri` field in the metadata describes the JWK Set used for signature verification. **A JWK Set does not define which issuer is trusted**: fetching keys solely from a URL indicated by an unverified token could direct the API to an attacker's key source.

~~~mermaid
flowchart TD
    A["Preconfigured trusted issuer"] --> B["Discovery / metadata"]
    B --> C["Issuer's JWK Set"]
    D["JWT received from client"] --> E["Read header + claims as untrusted data"]
    C --> F["Verify signature with allowed algorithm"]
    E --> F
    F --> G["Validate exp, nbf, iss"]
    G --> H["Validate API's aud"]
    H --> I["Check scope, policy, resource ownership"]
    I --> J["Allow request processing"]
~~~

A JWT header may contain `kid` to hint at a key within the trusted key set. `kid` **is not a URL to be fetched automatically**; parameters such as `jku` or `x5u`, if supported at all, must follow strict trust policies. Never enable acceptance of the `none` algorithm, and never rely on the token's self-declared algorithm to bypass the Resource Server's allowlist.

### Key Rotation and Availability

The Authorization Server can rotate signing keys. The Resource Server typically needs a mechanism to fetch and cache the JWK Set, refresh when new keys are published, and handle network failures according to policy. Old keys may need to be retained while previously issued tokens remain valid. Designing rotation is an **operational contract** between the Authorization Server and API teams, not a reason to temporarily skip signature verification.

### An API Trusting Multiple Issuers

In multi-tenant or multi-environment systems, an API may trust multiple **approved** issuers. In that case:

- Define the list of issuers and their corresponding key sets; never register a new issuer simply because the `iss` claim in a token has an unfamiliar value.
- Select the authenticator based on an allowlisted issuer, then verify the signature and `iss` using that authenticator.
- Validate **audience, scope, and tenant** per issuer if contracts differ.
- Avoid applying identical authorization rules across all issuers if the same scope name carries different semantics.

Spring Security provides `AuthenticationManagerResolver` or reactive resolver mechanisms to select an authentication manager in multi-issuer setups. Regardless of the mechanism used, the trust decision must originate from trusted configuration, never from unverified claims.

## 5. Defining the Access Purpose: Scope and Policy

Issuer and audience confirm that the token comes from the right issuer and is meant for the right API. The Resource Server must still decide **what the token is allowed to do**.

A simple permission table for the Orders API:

| API operation | HTTP endpoint | Required scope | Additional business checks |
|---|---|---|---|
| List own orders | `GET /api/orders` | `orders.read` | Filter by subject/tenant |
| View a specific order | `GET /api/orders/{id}` | `orders.read` | Order owner or authorized viewer |
| Create an order | `POST /api/orders` | `orders.create` | Active customer; valid products |
| Cancel an order | `POST /api/orders/{id}/cancel` | `orders.cancel` | Order status and ownership rights |
| View all orders for administration | `GET /api/admin/orders` | `orders.admin.read` | Administrative role, tenant, and policy |

This is an **example permission contract**, not a list of scopes standardized by OAuth 2.0. Scope names and semantics are designed by your system and approved by the Authorization Server.

### Scope Is Not Identical to Role

Example claim:

~~~json
{
  "scope": "orders.read orders.create"
}
~~~

In a typical Spring Security JWT Resource Server configuration, `scope` or `scp` is mapped to authorities prefixed with `SCOPE_`, such as `SCOPE_orders.read` and `SCOPE_orders.create`. This is different from a role like `ROLE_ADMIN`.

Holding the `orders.read` scope does not automatically grant permission to view **every** order. It only permits that category of read operation under the contract; the API must then verify ownership, tenant, data state, and business rules. In particular, never treat `sub` in the token as proof that the `/orders/{id}` path parameter belongs to that subject without querying and checking the data.

### Scope Must Match the Grant and Principal

In user-delegated flows (such as Authorization Code + PKCE), the token may represent a user and the permissions that user granted to the client. In `client_credentials`, the token usually represents an **application/service**, not a specific human user.

~~~text
Authorization Code:
  client = web-orders
  subject = user-123
  scope = orders.read
  purpose = view orders belonging to user-123

Client Credentials:
  client = inventory-sync
  subject = service principal (depends on token profile)
  scope = orders.read
  purpose = sync according to permissions granted to the service
~~~

Do not infer that every `sub` claim is a real human account. If an endpoint only permits access **on behalf of a user**, there must be a policy checking the principal type, grant type, or guaranteed claims in the token profile; checking a generic scope alone may not be enough.

### Transaction Purpose Goes Beyond Scope Alone

A `payments.execute` scope may only permit initiating a payment request, while **maximum amount, beneficiary account, timing, and approval status** are still governed by business policy. Some architectures use authorization details, rich authorization requests, or a policy engine. Additional fields are only meaningful when the Authorization Server and Resource Server agree on how they are issued, verified, and interpreted.

## 6. Sample Access Token Contract for the Orders API

Before writing code, both teams should maintain a contract document independent of framework configuration:

| Item | Illustrative Value | Responsible Party |
|---|---|---|
| Resource Server | Orders API | API team |
| Resource identifier / expected audience | `orders-api` | API team + Authorization Server |
| Trusted issuer | `https://login.example.test/realms/company` | Security/identity team |
| Token type | OAuth 2.0 access token; signed JWT per agreed profile | Authorization Server |
| JWK source | Trusted issuer's metadata pointing to a controlled JWK Set | Authorization Server + API |
| Allowed signing algorithms | Approved list in the deployment | Security team |
| Required audience | `aud` contains `orders-api` | API |
| Validity | `exp`, `nbf`, `iss`, and max token age if specified by contract | API + Authorization Server |
| Scopes | `orders.read`, `orders.create`, `orders.cancel`, `orders.admin.read` | Product/security + API |
| Principal | End user or service principal depending on grant, clearly distinguished | Authorization Server + API |
| Tenant boundary | Token's tenant must match the resource's tenant | API |
| Token transport | `Authorization: Bearer <token>` over HTTPS | Client + API |
| Failure responses | `401` for invalid/missing credentials; `403` for insufficient permissions | API |
| Key rotation | Policy for publishing new keys and retaining old keys while tokens remain valid | Authorization Server + operations |
| Observability | Request ID and error code; never log raw tokens | API + gateway |

Such a document answers questions that a few Spring Boot properties cannot fully describe: **which issuer is valid, which audience is valid, which scope maps to which action, and what data may be returned to the principal**.

### Example JWT Under the Contract

Illustrative payload:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "web-orders-client",
  "scope": "orders.read orders.create",
  "iat": 1924988400,
  "nbf": 1924988400,
  "exp": 1924992000
}
~~~

This is an **illustrative payload**, not a signed JWT that can be used to call an API. In real issuance, the Authorization Server must sign the token with an algorithm and key trusted by the Resource Server. The timestamps are for example purposes only and do not imply the token is valid at the time of reading.

To handle `GET /api/orders/42`, the API validates step by step:

1. Bearer credential is present and parseable.
2. Signature/algorithm/key are valid according to the trusted issuer.
3. The `iss` claim matches the trusted issuer.
4. The token is within its validity window.
5. `aud` contains `orders-api`.
6. Mapped authorities include `SCOPE_orders.read`.
7. Order 42 belongs to an authorized subject/tenant, or the principal has valid read permission under policy.

No later step may be used to skip a mandatory earlier validation step.

## 7. Enforcing the Issuer + Audience Contract with Spring Security Resource Server

### 7.1. Basic JWT Configuration

With Spring Boot and Spring MVC, the commonly used dependencies are:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

If you only configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

Spring Boot can configure a `JwtDecoder` for the issuer; Spring Security will check the signature, validity timestamps, and issuer according to appropriate defaults. **That alone does not guarantee the token carries the Orders API's audience.** A policy requiring `aud = orders-api` must be declared and enforced separately, or configured using the official audience setting of the framework version in use if available.

To illustrate the contract clearly and transparently, the following example defines a custom decoder bean with explicit validators for both issuer and audience.

### 7.2. Centralized Configuration Without Duplicating the Source of Truth

In `application.yml`:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/company
      audience: orders-api
~~~

This is an **application-defined** configuration namespace, not a built-in Spring Boot auto-configuration property. The bean below consumes these two values directly. When defining your own `JwtDecoder`, you do not need to maintain a second, potentially out-of-sync issuer under `spring.security.oauth2.resourceserver.jwt.issuer-uri`.

### 7.3. `JwtDecoder` Bean Validating Issuer and Audience

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
class OrdersJwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(issuer)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> targetAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Access token was not issued for this API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                targetAudience
            )
        );
        return decoder;
    }
}
~~~

How to read this:

- `withIssuerLocation(issuer)` uses the **preconfigured** issuer to build the decoder and locate the appropriate metadata/JWK; it never takes an arbitrary issuer from the token and trusts it.
- `JwtValidators.createDefaultWithIssuer(issuer)` creates the appropriate default timestamp and issuer validators.
- `targetAudience` confirms that `jwt.getAudience()` contains the `orders-api` audience.
- `DelegatingOAuth2TokenValidator` requires all validators to pass together, not just one.
- When the audience does not match, the decoder rejects the token at the **authentication step**. Scope rules in controllers never even need to run.

The example API assumes **only one issuer and one audience**. If there are multiple issuers, you need a resolver and an explicit trust policy per issuer; never simply remove the `iss` validator or allow any audience.

The snippet also assumes a JWT type whose signing algorithm is compatible with the decoder configuration. In production, you must specify the **allowed JWS algorithms** alongside the trusted JWK source. Do not rely on self-declared `alg` or `jku` headers in the token to expand the trust source.

### 7.4. Defining URL Permissions with `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersHttpSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Note that this example assumes a **pure stateless Bearer API without cookie/session browser authentication**, so CSRF can be disabled for the API. If the same application also uses cookie/session-based login, CSRF and security filter chains must be designed around the at-risk endpoints; never copy `csrf.disable()` across the entire system.

These rules verify scopes after the decoder has already validated the issuer and audience. `anyRequest().denyAll()` intentionally closes paths outside the illustrative contract; a real application must explicitly define health endpoints, CORS, and other required endpoints.

**Actual execution order:** receive request → `BearerTokenAuthenticationFilter` extracts Bearer token → `AuthenticationManager`/`JwtAuthenticationProvider` authenticates via `JwtDecoder` → converts scopes to authorities → `AuthorizationFilter` and policies check permissions → controller/service.

### 7.5. If Using WebFlux

For Spring WebFlux, the **issuer/audience/scope** goals remain unchanged; however, the HTTP stack and decoder use reactive interfaces:

| Capability | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| Security chain builder | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| JWT implementation | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| URL rules | `authorizeHttpRequests` / `requestMatchers` | `authorizeExchange` / `pathMatchers` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

Equivalent HTTP rule declaration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain ordersChain(ServerHttpSecurity http) {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .pathMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Disabling CSRF here likewise applies only to a pure Bearer API under the same assumptions as Servlet. With WebFlux, the custom decoder bean must be a `ReactiveJwtDecoder` and use reactive APIs; do not place a Servlet `JwtDecoder` where a reactive interface is required. The audience validation example from Servlet can be ported equivalently using `NimbusReactiveJwtDecoder`'s validator, with the same trusted issuer and agreed audience list.

## 8. Contracts with Opaque Tokens and Introspection

Not every access token exposes readable claims directly like a JWT. With an **opaque token**, the Resource Server typically calls the Authorization Server's **introspection endpoint** (RFC 7662) to retrieve the token's status and attributes.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Orders API
    participant AS as Trusted Authorization Server
    C->>API: Authorization: Bearer opaque-token
    API->>AS: Introspect token via trusted endpoint
    AS-->>API: active + scope + subject + audience (if provided)
    API->>API: Validate resource and permission policies
    API-->>C: 2xx / 401 / 403
~~~

An example introspection response might look like:

~~~json
{
  "active": true,
  "iss": "https://login.example.test/realms/company",
  "aud": ["orders-api"],
  "client_id": "web-orders-client",
  "sub": "user-123",
  "scope": "orders.read",
  "exp": 1924992000
}
~~~

In RFC 7662, `active` is an important signal, **but it does not automatically prove the token has the right audience**. Fields like `iss` and `aud` may or may not be returned depending on the Authorization Server and profile. Therefore, clarify the following with the Identity team:

1. **Which introspection endpoint is trusted**, how does the Resource Server authenticate to the endpoint, and how is TLS enforced?
2. Does introspection return `active: true` only for tokens valid for the calling resource, or does it return a generic status for any token from the issuer?
3. If multiple Resource Servers share the same endpoint, how are tokens meant for the Orders API distinguished from those for the Billing API?
4. Do the returned scope and principal carry the same semantics as with JWT?
5. When timeouts or introspection outages occur, how does the system **fail closed safely**; is caching used, and how does caching affect token revocation latency?

If the introspection response does not contain an audience, **do not infer that the token is implicitly meant for the API**. The contract must guarantee resource binding through Authorization Server/introspection policy, reliable associated metadata, or an API-controlled validation step.

Example Spring Boot properties for using opaque tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: ${ORDERS_INTROSPECTION_SECRET}
~~~

`ORDERS_INTROSPECTION_SECRET` is an illustrative environment variable name. Never commit secret values into the repository. Servlet provides `OpaqueTokenIntrospector`, while WebFlux provides `ReactiveOpaqueTokenIntrospector`. If custom audience validation is needed when introspection returns additional attributes, perform it via an appropriate custom introspector/policy mechanism before accepting the principal.

## 9. Distinguishing `aud`, `client_id`, `azp`, and `sub` in Access Decisions

Client and subject claims are frequently misused as audience:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "mobile-shop",
  "azp": "mobile-shop",
  "scope": "orders.read"
}
~~~

Contractual meanings:

- `aud = orders-api`: identifies the **API permitted to receive** the token.
- `client_id = mobile-shop`: identifies the **client that requested/holds the token**, if the token profile guarantees this claim.
- `azp = mobile-shop`: **authorized party** claim if emitted by the issuer, interpreted according to the specific profile (very common in OIDC ID tokens, though not required in every OAuth access token).
- `sub = user-123`: the principal represented by the token as defined by the Authorization Server.
- `scope = orders.read`: read permission granted within the token.

If policy states "Only the `mobile-shop` client may call this endpoint," the API needs **client identity validation** in addition to issuer, audience, and scope. If policy states "Users may only view their own orders," the API must verify `sub` against the actual owner of the order. You cannot use `client_id` to infer the target resource, nor use `aud` to infer data ownership.

### Client Permissions and User Permissions Are Two Separate Layers

Consider an administrative application:

~~~text
Client: admin-console
User:   analyst-17
Scope:  orders.admin.read
Aud:    orders-api
~~~

The API may simultaneously require that the client is on an allowlist, the user holds administrative permissions in the organization, the scope is valid, and the tenant matches. If only `scope` is checked, the endpoint risks accepting a service token or delegated token that does not match the actor type required by business rules.

## 10. A Token Crossing Multiple APIs: Never Automatically "Forward" It

Suppose the Client calls Orders API, and Orders API then needs to call Billing API:

~~~mermaid
flowchart LR
    C["Client"] -->|"Access token A: aud=orders-api"| O["Orders API"]
    O -->|"Access token B: aud=billing-api"| B["Billing API"]
~~~

If Orders API receives a token with audience `orders-api` and forwards **that exact same token** to Billing API, Billing API must reject it because `aud` is not intended for it. Two APIs trusting the same issuer does not mean they share token usage rights.

Valid design options depending on the scenario:

| Scenario | Approach |
|---|---|
| Orders API calls Billing API using its own service identity | Obtain a new access token via client credentials targeting `billing-api` |
| Orders API needs to call on behalf of the user | Consider OAuth 2.0 Token Exchange (RFC 8693) or an Authorization Server-supported flow to obtain a new token with the proper audience/scope |
| API gateway protects multiple backends | Clarify whether the gateway is the final Resource Server or each backend is its own Resource Server; design trust and audiences accordingly |
| A single token must be used across multiple resources by policy | Explicitly define multi-audience rules and the blast radius if one resource leaks the token |

Never "fix" an audience mismatch by disabling the validator on Billing API. Doing so destroys the boundary between resources.

## 11. Multi-Tenant: A Trusted Issuer Is Not Always Enough to Determine the Tenant

In a multi-tenant SaaS application, two requests may share the same issuer, audience, and scope while belonging to **different tenants**:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "tenant_id": "tenant-A",
  "scope": "orders.read"
}
~~~

If a request calls `GET /tenants/tenant-B/orders/42`, the API must enforce that **the principal's tenant matches the requested resource**, or that valid cross-tenant permission exists. Never use a client-supplied path tenant to pick "the tenant permission" without cross-checking against trusted data.

Two common tenant identification models:

- **Per-tenant issuer**: each tenant has its own issuer. The API needs an allowlist/registry of issuers per tenant and must map the tenant accurately after authentication.
- **Shared issuer across multiple tenants**: the tenant is carried in a claim or other contract-defined data. The API requires a validator and tenant authorization policy.

A claim such as `tenant_id` is not part of the universal mandatory claim set of JWT access tokens. Its name, semantics, and source of trust must be explicitly agreed upon, including rules for when the claim is missing, invalid, or duplicated across issuers.

## 12. Rules for Handling HTTP 401 and 403 Under the Token Contract

| Scenario | Classification | Typical Response |
|---|---|---|
| No Bearer token on an endpoint requiring authentication | Missing credential | `401 Unauthorized` |
| Invalid JWT signature or untrusted algorithm/key | Authentication failure | `401 Unauthorized` |
| `iss` not in trusted issuers | Authentication failure | `401 Unauthorized` |
| `aud` does not contain Orders API identifier | Authentication failure | `401 Unauthorized` |
| Expired token or before `nbf` | Authentication failure | `401 Unauthorized` |
| Opaque token has `active: false` | Authentication failure | `401 Unauthorized` |
| Valid token, missing `orders.read` | Authorization failure | `403 Forbidden` |
| Valid token, has scope, but requests order from another tenant | Authorization failure | `403 Forbidden`, or a resource-hiding policy may return `404` |
| Valid token, proper scope, data owned by principal | Business logic executed | `2xx` or business-determined status |

Sample responses per Bearer Token Usage (RFC 6750):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

These are **examples**. Exact headers depend on Spring Security, gateways, and custom policies. Do not let the API leak tokens, key configuration details, or unnecessary internal information in error responses.

## 13. Pass/Fail Scenarios: Same Issuer Is Not Enough

Assume the Orders API has the following contract:

~~~text
TRUSTED_ISSUER = https://login.example.test/realms/company
EXPECTED_AUD   = orders-api
READ_SCOPE     = orders.read
~~~

| Access token | Outcome on `GET /api/orders/42` | Reason |
|---|---|---|
| Correct issuer, correct audience, unexpired, `orders.read` scope, valid resource ownership | Accepted by API security | Right source, right recipient, right permission |
| Correct issuer, audience `billing-api`, `orders.read` scope | Rejected at authentication | Token intended for a different API |
| Issuer `https://login.evil.test`, audience `orders-api`, `orders.read` scope | Rejected at authentication | Untrusted issuer |
| Correct issuer, correct audience, only `orders.create` | Rejected at authorization | Lacks read permission |
| Correct issuer, correct audience, read scope, expired token | Rejected at authentication | Token is no longer valid |
| Correct issuer, correct audience, read scope, invalid signature | Rejected at authentication | Cannot prove integrity/token origin |
| ID token with `aud = web-orders-client` | Rejected as an API access token | Wrong token type and audience |
| Correct issuer, correct audience, read scope, order belongs to another user/tenant | Rejected at authorization | Business authorization check fails |

**Evaluation order matters:** the API only uses claims for authorization after they come from a token authenticated against a trusted issuer and mandatory constraints. Before that point, the JWT header/payload is merely unverified data carried by the request.

## 14. Common Contract Design Mistakes

### 14.1. Configuring Only `issuer-uri` and Assuming the API Already "Picks the Right Token"

Spring Security can verify the signature, issuer, and expiration thanks to `issuer-uri`. If the API requires `aud = orders-api`, audience validation must still be explicitly declared/checked. When one Authorization Server issues tokens for multiple APIs, checking the issuer alone does not distinguish the target recipient.

### 14.2. Overly Broad Issuer Matching

Do not use substring checks, arbitrary suffix matching, or accept every realm just because the hostname looks similar. Issuers under the same identity system may serve tenants or environments with different trust policies. **A valid key from issuer A** does not automatically make issuer B trusted.

### 14.3. Trusting Key URLs Embedded Inside the JWT

Information such as `kid`, `jku`, `x5u`, and `alg` in the initial JOSE header is still data from an **unverified** token. Never allow a token to choose its own JWK Set or algorithm outside the configured/approved allowlist. The key source must be bound to the trusted issuer.

### 14.4. Using Scope Instead of Audience

If a token was issued for the Billing API and happens to carry `scope = orders.read`, the Orders API must still reject it if `aud` does not match. Scope defines the **action**, not the **intended recipient** of the token.

### 14.5. Using Audience Instead of Business Permissions

`aud = orders-api` does not say the token is allowed to read, create, or cancel orders; it only identifies the right Resource Server. Authorizing operations requires checking scopes/authorities and policies applied to the resource.

### 14.6. Using an ID Token as an Access Token

In OIDC, an ID token is issued to inform the client of the user's authentication details. An ID token may have a valid signature and the right `sub` and `iss`, but its audience usually targets the client rather than the Resource Server. The API must validate an **access token** matching its profile.

### 14.7. Assuming `client_credentials` Tokens Always Have an End User

Client credentials tokens usually represent a service/client. Mapping that token to a specific user solely based on `sub` is not guaranteed to be valid. The contract must describe the difference between application permissions and user permissions.

### 14.8. Trusting `active: true` as Satisfying Every Condition

In introspection, `active: true` reflects the token's status according to the Authorization Server. It may not be enough to prove the Orders API's audience/scope/tenant requirements. Resource binding policies and corresponding permission checks are still needed.

### 14.9. Forwarding the Same Raw Token to Every Downstream Service

A token meant for the Orders API cannot automatically be used by the Billing API. When calling another API, obtain a token matching the destination and an approved delegation mechanism.

### 14.10. Treating `jti` as an Automatic Token Revocation Mechanism

`jti` can serve as a token identifier, but a Resource Server does not automatically know a token was revoked just because this claim exists. With locally verified JWTs, you must design token lifetime, revocation strategy, event propagation, or another check aligned with system risk.

## 15. End-to-End Integration Scenario Across Client, Authorization Server, and Orders API

Suppose the product requires users to view their own orders:

**Step 1 — The API team publishes the contract:**

~~~text
API:               Orders API
Audience:          orders-api
Trusted issuer:    https://login.example.test/realms/company
Required scope:    orders.read
Protected route:   GET /api/orders/{id}
Principal:         end user, per agreed token profile
Additional rule:   order.ownerId == authenticatedPrincipal.subject
~~~

**Step 2 — The Authorization Server team configures resources and permissions:**

- Client `web-orders-client` is allowed to request `orders.read` under the appropriate grant and consent/policy.
- Tokens issued for the Orders API must contain the `orders-api` audience.
- Access tokens carry the agreed issuer, an appropriate lifetime, and a signature using a public key the API is permitted to verify.
- Claims identifying the user/client and tenant are documented in the profile so the API never has to guess their meaning.

**Step 3 — The Client obtains a token and calls the API:**

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_FOR_ORDERS_API>
Accept: application/json
~~~

**Step 4 — The Resource Server validates:**

~~~text
Extract Bearer token
    ↓
Verify signature + algorithm + key source
    ↓
Check iss == trusted issuer
    ↓
Check exp/nbf and time constraints
    ↓
Check aud contains orders-api
    ↓
Build Authentication from principal and authorities
    ↓
Check orders.read scope
    ↓
Load order 42, verify ownerId/tenant per business rules
    ↓
Return resource or deny
~~~

**Step 5 — When the contract changes:** If the Authorization Server changes the issuer, audience identifier, scope structure, or token profile, the API must be updated in a controlled manner. If the issuer rotates signing keys, operations must ensure JWK discovery/caching and rotation policies work properly; never disable validation to avoid disruption.

## 16. Decisions to Confirm Before Real Integration

| Topic | Questions to Answer Explicitly in the Specification |
|---|---|
| Resource identity | What is the official audience of the API? Are there multi-audience cases? |
| Issuer trust | Which issuers does the API permit in production/staging? Is trust separated per tenant? |
| Token format | JWT or opaque? If JWT, which token profile, algorithms, and JWK Set? |
| Token validity | Max TTL, clock skew, `nbf`, `exp`, revocation policy, and key rotation? |
| Client profile | Which grants are permitted? How are delegated users distinguished from service principals? |
| Access rights | Which scope applies to each HTTP operation? Are there subject, tenant, or ownership policies? |
| Custom claims | Where do client, tenant, organization, and role claims come from, and what are their exact meanings? |
| Introspection | Which endpoint verifies opaque tokens; how does the endpoint guarantee resource binding? |
| Multi-API calls | Is token exchange or fresh token acquisition used for downstream calls? |
| Failure contract | Which 401/403 status and error codes are returned; are `WWW-Authenticate`/`scope` required? |
| Transport | Only Bearer headers over HTTPS, or are any protocol exceptions approved? |
| Logging | Which fields are logged; how are tokens, secrets, and identifying data masked? |
| Ownership | Who owns changes to the issuer, audience, scopes, keys, and integration docs? |

The specification should state **concrete values, provisioning sources, and owners** for each rule. Vague statements like "valid JWT" or "authorized client" are rarely enough for two teams to implement the exact same contract.

## 17. Suggested Contract Test Scenarios

For the Orders API example, the integration test suite could include:

| Scenario | Condition | Expected Result |
|---|---|---|
| Valid issuer/audience/scope | Validly signed, unexpired JWT, `aud = orders-api`, has `orders.read` | Enters business layer |
| Wrong issuer | JWT issued by another issuer | Authentication rejected |
| Wrong audience | JWT issued for `billing-api` | Authentication rejected |
| Missing required audience | JWT lacks `aud` or has empty audience | Authentication rejected per contract |
| Expired token | `exp` is in the past | Authentication rejected |
| Token not yet valid | `nbf` is past the valid timestamp | Authentication rejected |
| Invalid signature | Payload/signature tampered with, or signed by untrusted key | Authentication rejected |
| Disallowed algorithm | Token uses a JWS algorithm outside the allowlist | Authentication rejected |
| Missing scope | Valid token has only `orders.create` when calling GET | Authorization rejected |
| Wrong tenant | Valid token for tenant A accesses tenant B's data | Rejected by policy |
| Service token calling user-only endpoint | Lacks end-user context required by contract | Rejected by policy |
| Inactive opaque token | Introspection returns `active: false` | Authentication rejected |
| Endpoint with no token | Protected endpoint missing `Authorization` | Authentication required |
| Token for API A forwarded to API B | `aud` is not for B | B rejects authentication |

When using `spring-security-test`, **mock JWTs** are convenient for testing controller scope/authority rules. However, mock JWTs typically bypass the real decoder and therefore **do not prove** that issuer discovery, signatures, audience validators, or introspection work properly. Those conditions require integration testing through the real decoder/token or a dedicated token test setup.

## 18. Summary of the Access Token Acceptance Contract

A Resource Server should treat token acceptance as a chain of mandatory conditions:

~~~text
Token accepted for request
  =
  Correct access token type per contract
  AND Trusted signature / introspection
  AND Issuer in trusted list
  AND Token still within validity window
  AND Audience targeted at current API
  AND Scope/authority matches operation
  AND Subject, tenant, and resource policies satisfied
~~~

**The target API** is identified by audience/resource identity. **The trusted issuer** is determined by the approved issuer, metadata, keys, and algorithms. **The access purpose** is enforced through scopes, authorities, and business data checks. All three layers must exist simultaneously; omitting any one layer can cause the API to accept a token in the wrong context even when the other layers appear valid.

With Spring Security Resource Server, `issuer-uri` is a useful foundation for JWT validation, but the real-world contract must extend to **audience validation**, operation permissions, and per-resource access control. That is how you implement the principle that **a token is issued for the right API, by the right issuer, and to perform the right job**.

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
