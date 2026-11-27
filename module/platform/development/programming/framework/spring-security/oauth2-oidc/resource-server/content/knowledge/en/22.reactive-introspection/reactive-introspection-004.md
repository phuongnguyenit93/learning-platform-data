# Checking active, Metadata, and Scope Mapping

In a **Spring Security OAuth 2.0 / OIDC Resource Server** running on **Spring WebFlux**, validating an **opaque access token** is usually performed by sending the token to the **Authorization Server** via the **OAuth 2.0 Token Introspection** endpoint. The Authorization Server's response not only indicates whether the token is active through the `active` field, but can also include **metadata** such as `scope`, `sub`, `client_id`, `aud`, `iss`, `exp`, and custom attributes. Spring Security uses this verified data to build an `OAuth2AuthenticatedPrincipal`, map scopes to authorities, and construct an `Authentication` for the request.

In a reactive system, this process follows the pipeline:

```text
Authorization: Bearer <opaque-access-token>
    |
    v
ServerBearerTokenAuthenticationConverter
    |
    v
AuthenticationWebFilter
    |
    v
Reactive authentication manager for opaque tokens
    |
    v
ReactiveOpaqueTokenIntrospector.introspect(token)
    |
    +---- HTTPS POST to Authorization Server -----+
    |                                             |
    |                      active=true + metadata | active=false / error
    |                                             |
    v                                             v
OAuth2AuthenticatedPrincipal                 REJECT AUTHENTICATION
    |
    v
BearerTokenAuthentication + SCOPE_* authorities
    |
    v
Reactor SecurityContext
    |
    v
authorizeExchange / reactive method security
    |
    v
Resource policy: tenant, ownership, business state
```

**Lesson goal:** understand exactly how to read and use `active`, distinguish metadata included vs. omitted in RFC 7662, identify the trust boundary of introspection data, map `scope` to `GrantedAuthority` in WebFlux, customize `ReactiveOpaqueTokenIntrospector` safely, and test **authentication**, **scope authorization**, and **business authorization** separately.

> **Example context:** The Orders API uses Spring Boot 3.x, Spring Security 6.x, and WebFlux. The Authorization Server at `https://login.example.com` exposes `https://login.example.com/oauth2/introspect`. Valid tokens for the Orders API carry resource/audience `orders-api`, scope `orders.read` or `orders.write`, and optionally `tenant_id`. All URLs, client IDs, tokens, and timestamps in this lesson are illustrative. Builder/constructor APIs can vary across minor versions, so consult the Javadoc matching your project's actual version.

## 1. Three Concepts to Distinguish from the Start

### 1.1. `active` Answers Whether the Authorization Server Recognizes the Token

`active` is a **boolean** field defined by RFC 7662. With a valid response:

```json
{
  "active": true
}
```

The Authorization Server confirms that the token is active under its policy at introspection time, within the scope that the **Resource Server is permitted to query**.

If:

```json
{
  "active": false
}
```

the Resource Server **must not** create a valid Authentication from that token.

### 1.2. Metadata Describes the Token and Its Subject

Example of a richer response:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "storefront-web",
  "token_type": "Bearer",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "iss": "https://login.example.com",
  "exp": 2000000000,
  "iat": 1999996400,
  "nbf": 1999996400,
  "tenant_id": "tenant-a"
}
```

These fields serve different roles. They are **not all required** in an RFC 7662 response, and **do not automatically share the same data types across all providers** when providers use extensions. The Resource Server must agree on a **metadata contract** with the Authorization Server rather than guessing.

### 1.3. Scope Is Functional Permission, Not Permission Over Every Object

From the string:

```json
{
  "scope": "orders.read orders.write"
}
```

Spring Security typically produces authorities:

```text
SCOPE_orders.read
SCOPE_orders.write
```

This helps the API verify whether the token was granted the **read** or **write orders** action class. However, a token with `SCOPE_orders.read` is **not automatically** allowed to read another tenant's or another user's orders. Scope authorization and object-level authorization are two separate steps.

## 2. Why Is It Called Token Introspection?

**RFC 7662 — OAuth 2.0 Token Introspection** defines an interface for an authorized party to query the Authorization Server about a token's status and attributes.

When the API receives:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_FROM_CALLER
Accept: application/json
```

it calls the introspection endpoint over HTTPS, for example:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.com
Authorization: Basic BASE64_INTROSPECTION_ID_COLON_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=ACCESS_TOKEN_FROM_CALLER&token_type_hint=access_token
```

In the second request:

- `token` is the **token to be inspected**.
- `token_type_hint` is an **optional hint**, not proof that the token is genuinely an access token.
- HTTP Basic represents the **Resource Server/introspection client's credentials**, not the credentials of the user calling the Orders API.
- The Authorization Server authenticates the introspection client and enforces policies governing which token details it is allowed to read.

### 2.1. Two Client IDs Are Not the Same

Suppose the Orders API configures:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

In the environment, `ORDERS_INTROSPECTION_CLIENT_ID` might be `orders-api-introspector`. Meanwhile, the response contains:

```json
{
  "active": true,
  "client_id": "storefront-web"
}
```

| Value | Meaning |
|---|---|
| `orders-api-introspector` | Identity the **Orders API** uses to call the introspection endpoint |
| `storefront-web` | OAuth client **that was issued the access token** being inspected |

They may match in some deployments, but **there is no rule requiring them to match**. Never use `client_id` from the response in place of introspection credentials or treat it as the end-user ID.

### 2.2. Introspection Is Not Local JWT Verification

| Aspect | Opaque token + introspection | Local JWT verification |
|---|---|---|
| Source of truth | Authorization Server returns `active` | JWT signature/claims are verified locally |
| Network calls | Typically needed on introspection, unless intentionally cached | Typically needed for metadata/JWKS at startup or key rotation |
| Principal | `OAuth2AuthenticatedPrincipal` | `Jwt` |
| Common Authentication | `BearerTokenAuthentication` | `JwtAuthenticationToken` |
| Scope mapping | From introspection metadata | From verified JWT claims |
| Revocation | Can be reflected on subsequent introspection | Cannot revoke individual JWTs before `exp` with offline verification alone |

Opaque tokens do not mean **skipping authorization checks**. The Authorization Server says the token is active; the Resource Server still decides whether the token may access the **Orders API and the specific order**.

## 3. `active=true`: Understanding the Exact Level of Guarantee

An `active=true` response means the Authorization Server considers the token active within the introspection context. Internal checks may include token existence, non-expiration, non-revocation, or other policies.

Per RFC 7662, `active` is required and reports token status. However, **how the AS computes `active`** and **which metadata the Resource Server is permitted to see** can vary by provider.

**Never infer from `active=true` alone that:**

1. The token is definitely meant for the Orders API without an audience/resource policy.
2. The token is definitely an OAuth **access token**, rather than a refresh token or another token type.
3. `sub` is always an end-user ID; tokens from `client_credentials` can represent a service.
4. `scope` grants access to every record in the system.
5. The token will not be revoked in the future.
6. A user's tenant membership and roles never change.
7. The Resource Server can skip issuer/client allowlist checks or domain authorization.

### 3.1. Conditions Should Be Layered

An illustrative resource policy:

```text
ALLOW_READ_ORDER =
    introspection_result.active == true
AND token_type_is_accepted_as_access_token
AND token_was_issued_by_trusted_AS
AND audience_or_resource_contract_is_orders_api
AND token_has_scope("orders.read")
AND actor_is_allowed_to_read_orders
AND actor_tenant == order_tenant
AND (actor_owns_order OR actor_has_explicit_delegation)
```

This is an **illustrative application policy formula**, not an RFC 7662 expression. Some conditions may be guaranteed by the AS through introspection client policy, while others are verified directly by the RS from metadata and the database.

### 3.2. `active` and Current Time

The Authorization Server may compute `active` using `exp`, `nbf`, and revocation policies. If the RS contract also requires checking `exp` or token age, add an appropriate validator.

Example:

```json
{
  "active": true,
  "scope": "orders.read",
  "exp": 2000000000,
  "nbf": 1999996400,
  "iat": 1999996400
}
```

`exp`, `nbf`, and `iat` typically follow **NumericDate** semantics: seconds since the Unix epoch. Do not treat these numbers as milliseconds when converting with `Instant.ofEpochSecond(...)`. Do not configure overly generous clock skew just to mask clock drift between environments.

## 4. `active=false` and Fail-Closed Behavior

An inactive response typically looks like:

```json
{
  "active": false
}
```

Per RFC 7662, for inactive tokens the Authorization Server typically omits sensitive metadata. `active=false` does not necessarily reveal the reason:

- Token does not exist.
- Token has expired.
- Token was revoked.
- Current introspection client is not authorized to inspect this token.
- Token is rejected by issuer policy.

**The only outcome required on the Resource Server:** do not construct an authenticated principal from this token.

### 4.1. HTTP 200 Can Still Mean an Invalid Token

This is a common point of confusion. The introspection endpoint can return:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":false}
```

HTTP `200` indicates the **introspection HTTP request was processed**; it **does not** guarantee the bearer token is active. Never write a custom client like:

```java
// INTENTIONALLY WRONG: never use this logic to grant Authentication.
if (introspectionHttpStatus == 200) {
    return authenticatedPrincipalFor(token);
}
```

Instead, use the standard `ReactiveOpaqueTokenIntrospector` or a strict parser that verifies `active` is **boolean true** along with any additional checks.

### 4.2. Introspection HTTP 401 Differs from HTTP 401 Returned to the API Caller

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="introspection"
```

From the Authorization Server, this can indicate **the Resource Server's introspection client-id/client-secret is wrong**. This is an outbound error between the Resource Server and the AS, **not** proof that the user just sent an expired token.

Classify clearly:

- `active=false`: bearer token rejected.
- `401/403` from the introspection endpoint: **Resource Server** credential or permission issue.
- `429`/`5xx`/timeout/TLS: dependency unavailable or network error.
- Malformed JSON / missing `active`: no valid verification result.

All cases lacking proof must **fail closed**. However, the inbound response to the caller (401 vs. 503) and operational alerts depend on how the application maps errors; never assume every timeout is `invalid_token`.

## 5. Introspection Metadata Under RFC 7662

A valid response can contain several standardized claims. The table below separates **standard semantics** from **what the API must decide**:

| Name | Typical meaning | Rule for use on the Resource Server |
|---|---|---|
| **`active`** | Token status, boolean | Must be true before considering authentication |
| **`scope`** | Granted scopes, usually space-delimited string | Map to authorities and enforce on endpoints |
| `client_id` | OAuth client issued the token | Can check against a client allowlist; do not infer an end-user |
| `username` | Display name of the resource owner when present | Do not use as a stable security ID unless guaranteed by contract |
| `token_type` | Token type declared by the AS | Accept only token types supported by the API |
| `exp` | Token expiration time | Enforce per policy and evaluate clock behavior |
| `iat` | Issued-at timestamp | Enforce token age if required by business rules |
| `nbf` | Not-before timestamp | Reject before valid time per policy |
| `sub` | Subject | Can be a user or a service depending on grant/profile |
| `aud` | Audience/resource | Bind token to the Orders API |
| `iss` | Issuer | Match against trusted AS/realm if disclosed |
| `jti` | Token identifier | Can support audit/revocation policy; protect PII |
| `tenant_id` | Provider extension | Trust only if committed by AS; still enforce object policy |
| `roles`/`permissions` | Provider-specific extension | Never map blindly to admin privileges without a contract |

Not every AS returns every field. The Resource Server must agree with the AS on **which fields are required**, **which may be omitted**, **which formats are supported**, and **which fields may drive authorization**.

### 5.1. Metadata Must Come from the Trusted Source

`sub=customer-42` inside an **introspection response received over a trusted channel** means something entirely different from:

```http
X-User: customer-42
X-Tenant: tenant-a
```

sent by the API caller. The latter **is not authentication proof**. Never use headers, query parameters, JSON body fields, or unverified text inside an opaque token to build a privileged principal.

### 5.2. Do Not Confuse Metadata with a Verified User Database Identity

`sub` is typically a subject managed by the Authorization Server. Depending on architecture, an application user identity may be keyed by the pair:

```text
(issuer, subject)
```

rather than `subject` alone. This prevents collisions when multiple issuers/realms issue identical `sub` values.

If tenancy applies, verify tenant membership and the subject–tenant relationship against a trusted source; a `tenant_id` string appearing in an introspection response does not by itself prove the actor can access **every resource** in that tenant.

## 6. Metadata Can Be Omitted: Designing a Required Contract

RFC 7662 does not mandate that every active response include `scope`, `aud`, `iss`, or `sub`. Yet the Orders API may require them.

For example, an API protecting per-customer orders:

```text
Required:
  active = true
  scope includes orders.read / orders.write as appropriate
  aud includes orders-api, OR trusted AS policy equivalent
  iss == https://login.example.com, if issuer is supplied/required
  sub = stable user or service identity according to token class
  tenant_id = nonblank trusted tenant under domain contract
```

If `aud` is absent and the application requires audience isolation, do not assume the token is intended for the Orders API. There are two primary architectural options:

1. **The AS returns `aud` metadata** and the Resource Server validates it.
2. **The AS restricts the introspection client** so it can only introspect tokens belonging to this resource, backed by an audited contract guaranteeing that restriction.

Option 2 must be an **actual guarantee enforced by the Authorization Server**, not a guess made because the client ID contains "orders-api".

### 6.1. Example Response Containing Only `active=true`

```json
{
  "active": true
}
```

For an endpoint that only needs proof the token is recognized by the AS, a specialized architecture might accept this response. But for an API requiring scope/issuer/audience/tenant, that metadata is **insufficient** to authorize the action. Deny by default rather than automatically granting `SCOPE_orders.read` to every active token.

### 6.2. Machine-to-Machine Tokens Differ from User Tokens

A token issued under `client_credentials` might return:

```json
{
  "active": true,
  "client_id": "nightly-reports",
  "sub": "nightly-reports",
  "scope": "orders.export",
  "aud": ["orders-api"],
  "iss": "https://login.example.com"
}
```

Here `sub` may be a service/client identity rather than a customer. If `OrderService` uses `authentication.getName()` as the customer owner ID, the system can confuse identities. Service accounts need their own **client allowlist, workload scopes, and tenant/resource policies**.

## 7. `scope`: RFC Standard Is a Space-Delimited String

For OAuth scopes, a typical response is:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

`scope` is a string of scope tokens separated by **spaces** per OAuth 2.0 semantics. Each scope represents a granted permission under the Authorization Server contract.

Examples:

```text
orders.read
orders.write
orders.cancel
orders.export
```

These are functional permission names for the **Orders API**, not database roles or permissions assigned directly to individual orders by default.

### 7.1. Scopes Differ from Roles, Permissions, and Ownership

| Concept | Example | Question answered |
|---|---|---|
| OAuth scope | `orders.read` | Which category of operation was the token granted? |
| Spring Security authority | `SCOPE_orders.read` | Which authority does Spring check on the Authentication? |
| Application role | `ROLE_ORDER_MANAGER` | What business role does the actor hold? |
| Fine-grained permission | `PERMISSION_orders.refund` | Which specific capability is the actor allowed by policy? |
| Object ownership | Order has owner `customer-42` | Can the actor access this specific resource? |
| Tenant isolation | `tenant-a` vs `tenant-b` | Can the actor cross tenant boundaries? |

An active token with `scope=orders.read` may allow reading the order resource class, yet the service must still verify subject, tenant, resource assignment, and business state.

### 7.2. The `SCOPE_` Prefix Is a Spring Security Convention

In a typical Spring Security Resource Server configuration, response scopes:

```text
orders.read orders.write
```

are mapped to authorities:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Consequently, WebFlux configuration can use:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Do not use `hasRole("orders.read")` by default because `hasRole` applies the `ROLE_` convention, which is not equivalent to `SCOPE_`.

### 7.3. Is the List-Shaped `scp` Format Standard?

Some Authorization Servers return an extension:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.write"]
}
```

This is **not the standard RFC 7662 space-delimited `scope` string**. Some providers/frameworks have special rules, but never assume `ReactiveOpaqueTokenIntrospector` automatically reads `scp` like `scope` across all versions.

If a provider actually returns a `scp` array, build an **explicit mapping adapter** or ask the AS to return standard metadata per contract. Never rely on luck that an authority mapper understands arbitrary custom fields.

## 8. How Spring Security Maps Metadata to Authentication

In WebFlux, the participating components are:

| Component | Role |
|---|---|
| `ServerBearerTokenAuthenticationConverter` | Extracts the Bearer token from `ServerWebExchange` |
| `AuthenticationWebFilter` | Orchestrates reactive authentication |
| Reactive opaque authentication manager | Calls the introspector and constructs Authentication |
| `ReactiveOpaqueTokenIntrospector` | Returns `Mono<OAuth2AuthenticatedPrincipal>` or an error |
| `OAuth2AuthenticatedPrincipal` | Holds attributes and granted authorities from the introspection result |
| `BearerTokenAuthentication` | Authentication representing the verified token |
| `ReactiveSecurityContextHolder` | Exposes authentication in the Reactor Context |
| `authorizeExchange` | Checks scope/role at the HTTP boundary |
| `@EnableReactiveMethodSecurity` | Protects reactive service/method calls |
| Domain policy | Enforces permissions by object, tenant, and business state |

### 8.1. Reactive Flow with an Active Response

```mermaid
sequenceDiagram
    autonumber
    participant Caller as API Caller
    participant RS as WebFlux Resource Server
    participant Filter as AuthenticationWebFilter
    participant Introspector as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    participant Authz as AuthorizationWebFilter
    Caller->>RS: GET /api/orders/42 + Bearer opaque-token
    RS->>Filter: Exchange
    Filter->>Introspector: introspect(token) -> Mono<Principal>
    Introspector->>AS: POST /oauth2/introspect (HTTPS + client authentication)
    AS-->>Introspector: 200 active=true; scope=orders.read
    Introspector-->>Filter: OAuth2AuthenticatedPrincipal + SCOPE_orders.read
    Filter->>RS: BearerTokenAuthentication in Reactor Context
    RS->>Authz: Check hasAuthority(SCOPE_orders.read)
    Authz->>RS: Allow
    RS->>RS: Service checks owner, tenant
    RS-->>Caller: 200 or resource permission error
```

### 8.2. Reactor Context Is Not Servlet ThreadLocal

In Spring MVC/Servlet, code often reads:

```java
SecurityContextHolder.getContext().getAuthentication();
```

In WebFlux, the security context flows through the **Reactor Context**. When reading from a reactive pipeline:

```java
Mono<Authentication> currentActor =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
```

Never call `block()` to wait for authentication on the event loop, and never self-`subscribe()` separately to extract the principal and run mutations outside the pipeline. Detaching subscriptions can lose context or break authorization ordering.

## 9. Configuring a WebFlux Resource Server with Opaque Tokens

### 9.1. Dependencies

Gradle Groovy DSL example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

This is the reactive WebFlux stack. If the application has both Spring MVC and WebFlux on the classpath, verify which web application type actually runs; never copy Servlet `SecurityFilterChain` code into an application running `SecurityWebFilterChain`.

### 9.2. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Both environment variables must be supplied via a secret manager or secure deployment mechanism. Never commit real client secrets; never log HTTP Basic Authorization headers or `token=...` request bodies.

### 9.3. SecurityWebFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain ordersApiChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new BearerTokenServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenServerAccessDeniedHandler()
                )
            )
            .build();
    }
}
```

Explanation:

1. The OAuth2 Resource Server DSL configures the reactive Bearer opaque-token authentication path.
2. The introspector queries the AS to confirm `active` and fetch attributes.
3. `BearerTokenAuthentication` carries the principal and authorities for the request.
4. `authorizeExchange` checks `SCOPE_*` authorities per HTTP method and path.
5. `oauth2Login` and `formLogin` are not configured as default entry points for the Bearer API.
6. `NoOpServerSecurityContextRepository` avoids storing authentication in a session; callers must send the Bearer token on every request.
7. The service continues checking object-level authorization.

**Note:** this example uses a single chain protecting all paths; if you have public APIs, Actuator, management endpoints, or web login, define authorization rules and multiple chains as required. CSRF must also match your credential model: pure bearer-only APIs can disable it per policy, whereas cookie/session credentials require proper CSRF protection.

### 9.4. Using JWT Instead of Opaque

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults())
)
```

is a **different** authentication path using `ReactiveJwtDecoder`. Never enable multiple mechanisms simultaneously on the same Bearer request without explicit routing/manager design. In this lesson we choose **opaque introspection**, not decoding or parsing opaque tokens as JWTs.

## 10. `ReactiveOpaqueTokenIntrospector`: The Core Contract

The interface conceptually looks like:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

- Input `token` is an unverified Bearer string.
- Success output is an `OAuth2AuthenticatedPrincipal` containing attributes and authorities.
- Inactive or unacceptable tokens must produce an **authentication error signal**.
- Network, client-authentication, or JSON errors must never become a valid principal.
- Processing must remain purely reactive, never calling `block()` inside filters or on the event loop.

### 10.1. Standard Implementations Check `active`

An implementation such as `NimbusReactiveOpaqueTokenIntrospector` (in Spring Security 6.x versions that support it) performs HTTP introspection and processes the response per Spring Security conventions. When `active=false`, it does not return an authenticated principal as it does for `active=true`.

When standard `application.yml` configuration suffices, **do not write your own `active` parser**. Rely on Spring Boot auto-configuration and the `opaqueToken(...)` DSL.

### 10.2. Why Be Careful When Writing a Custom Introspector?

When you register a `ReactiveOpaqueTokenIntrospector` bean yourself, Spring Boot may use it in place of the default configuration.

If a custom introspector does this:

```java
// INTENTIONALLY WRONG: bypasses all token validation.
return token -> Mono.just(
    new DefaultOAuth2AuthenticatedPrincipal(
        "somebody",
        Map.of("sub", "somebody"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.admin"))
    )
);
```

then **any Bearer token** is treated as valid with admin scope. Returning a `Mono` does not make this code safe.

**Proper approach:** retain a **standard delegate introspector** to verify `active` and fetch metadata; the wrapper only adds mandatory policies or explicit mappings. If policy fails, return `Mono.error(...)` so the filter rejects the request.

## 11. Customizing the Introspector to Check Audience

Suppose the Authorization Server must return `aud` for Orders API tokens. We want to reject an active token issued for the Billing API.

### 11.1. Decorator Adds Validation Only Without Replacing Introspection

```java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class AudienceCheckingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String requiredAudience;

    public AudienceCheckingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String requiredAudience) {
        this.delegate = delegate;
        this.requiredAudience = requiredAudience;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .flatMap(principal -> {
                Object rawAudience = principal.getAttribute("aud");

                boolean matched = false;

                if (rawAudience instanceof String audience) {
                    matched = requiredAudience.equals(audience);
                } else if (rawAudience instanceof Collection<?> audiences) {
                    matched = audiences.contains(requiredAudience);
                }

                if (!matched) {
                    return Mono.error(
                        new BadOpaqueTokenException(
                            "Token audience is not accepted"
                        )
                    );
                }

                return Mono.just(principal);
            });
    }
}
```

Explanation:

- `delegate.introspect(token)` remains responsible for **HTTP introspection and `active` checking**.
- The wrapper checks `aud` from the response already accepted by the delegate.
- If `aud` is missing or lacks `orders-api`, it rejects—**never** infer audience from the endpoint URL the caller invoked.
- No Authentication is built from the raw token; it only returns the principal confirmed by the AS and accepted by additional policy.
- `BadOpaqueTokenException` is an appropriate token error for the opaque-token flow, ensuring the pipeline does not turn policy failures into success.

### 11.2. Registering the Wrapper as a Spring Bean

Example for Spring Security versions supporting `NimbusReactiveOpaqueTokenIntrospector`:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.oauth2.server.resource.introspection.NimbusReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfiguration {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
            new NimbusReactiveOpaqueTokenIntrospector(
                uri,
                clientId,
                clientSecret
            );

        return new AudienceCheckingIntrospector(
            delegate,
            "orders-api"
        );
    }
}
```

**Version note:** when using a Spring Security version with a different reactive introspector implementation or builder, apply the corresponding API from its Javadoc; the essence is **standard HTTP introspection + metadata validation**. Once you register a custom bean, do not assume Boot's other property-based defaults still apply automatically, especially application-specific checks.

### 11.3. Limits of the Audience Example

The decorator above checks only `aud`. A real contract may also require:

- `iss` matching an allowlisted issuer.
- `token_type` matching bearer access token.
- `client_id` belonging to an allowed OAuth client group.
- `sub` matching user or service actor classification.
- `tenant_id` having a valid value.
- `scope` containing policy-required permissions.
- `exp` and `nbf` validity, if guaranteed in the AS response and required by the RS.

Not all metadata checks must live inside the introspector. Responsibilities can be split across authentication, endpoint authorization, and service policy—just **never omit a truly mandatory constraint**.

## 12. Mapping Scopes Strictly per Contract

### 12.1. Common Spring Security Behavior

Given response:

```json
{
  "active": true,
  "scope": "orders.read orders.write"
}
```

the introspector/resource-server support typically maps those two scopes into `SCOPE_orders.read` and `SCOPE_orders.write` on the principal/Authentication. Those authorities can then be checked:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

**Do not assume every metadata extension is mapped automatically.** If the AS returns `permissions`/`roles`/`scp` with a custom schema, define an explicit converter.

### 12.2. Do Not Blindly Map Scopes to Global Roles

Example to avoid:

```text
scope = "orders.read admin"
           |
           v
hasRole("ADMIN") allowed across all services
```

An `admin` scope might only apply internally to one resource; turning it into an application-wide `ROLE_ADMIN` without a contract opens privileges beyond the intended scope.

A clear convention:

```text
OAuth scope           -> SCOPE_orders.read
Application role      -> ROLE_ORDER_MANAGER
Business permission   -> PERMISSION_orders.refund
```

Each namespace should have its own policy and trusted data source.

### 12.3. How Should Missing Scope Be Handled?

If metadata is:

```json
{
  "active": true,
  "sub": "customer-42"
}
```

never grant `SCOPE_orders.read` automatically. On an endpoint requiring `SCOPE_orders.read`, authentication may succeed, yet authorization must reject due to missing authority, unless the AS–RS contract uses another verified permission source.

**Never turn "active token" into "token has all scopes."**

## 13. Handling List-Shaped Scope Extensions

An Authorization Server might return:

```json
{
  "active": true,
  "scp": ["orders.read", "orders.export"],
  "sub": "customer-42",
  "aud": ["orders-api"]
}
```

If a provider omits standard `scope` and only sends the `scp` extension, a decorator can add authorities from `scp` using an allowlist.

### 13.1. Allowlist-Based Mapping Helper

```java
package com.example.orders.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

public final class OpaqueScopeMapping {

    private static final Set<String> SUPPORTED_SCOPES = Set.of(
        "orders.read",
        "orders.write",
        "orders.export"
    );

    private OpaqueScopeMapping() {}

    public static Collection<GrantedAuthority> mapScp(Object rawScp) {
        if (!(rawScp instanceof Collection<?> source)) {
            return List.of();
        }

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>();

        for (Object item : source) {
            if (!(item instanceof String value)) {
                continue;
            }

            if (SUPPORTED_SCOPES.contains(value)) {
                authorities.add(
                    new SimpleGrantedAuthority("SCOPE_" + value)
                );
            }
        }

        return new ArrayList<>(authorities);
    }
}
```

This is an **illustrative policy matching a provider contract**. In a real system:

- Enable `scp` mapping only when the trusted issuer genuinely uses this schema.
- Never map arbitrary unbounded strings from custom claims.
- Define behavior for wrong types, duplicates, whitespace, or nulls per contract.
- If the API requires a scope and metadata is missing or malformed, let authorization deny or have the introspector fail closed per contract.
- Never grant broader privileges than what the Authorization Server disclosed.

### 13.2. Adding Authorities Without Losing Standard Scopes

A wrapper can preserve `principal.getAuthorities()` (already containing `SCOPE_*` from standard `scope` if supported by the delegate), then add scopes from `scp` when the extension is permitted.

```java
package com.example.orders.security;

import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class ScpMappingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;

    public ScpMappingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
            .map(principal -> {
                Set<GrantedAuthority> authorities =
                    new LinkedHashSet<>(
                        principal.getAuthorities()
                    );

                authorities.addAll(
                    OpaqueScopeMapping.mapScp(
                        principal.getAttribute("scp")
                    )
                );

                return new DefaultOAuth2AuthenticatedPrincipal(
                    principal.getName(),
                    principal.getAttributes(),
                    authorities
                );
            });
    }
}
```

**Key points:**

1. The delegate must have already verified the token is active before the wrapper runs.
2. `principal.getAuthorities()` is retained so standard scopes mapped by Spring are not accidentally wiped out.
3. Only allowlisted `scp` values are added.
4. Never build authorities from unverified claims or caller-supplied request headers.
5. If the principal name is missing per schema, design explicit identity validation—never use `null` as a user identity or fall back all tokens to a single default username.

### 13.3. Decorator Ordering

When both checking audience and mapping scopes:

```text
NimbusReactiveOpaqueTokenIntrospector
    |
    v
AudienceCheckingIntrospector
    |
    v
ScpMappingIntrospector
    |
    v
Accepted OAuth2AuthenticatedPrincipal
```

The outermost decorator executes only after inner delegates succeed. If you add issuer or expiration checks, create the corresponding policy decorator and define order and conditions explicitly. Never declare `active=true` before the delegate runs.

## 14. Mapping Roles/Permissions: Separate Policy Is Required

Not all `roles`/`permissions` metadata from an Authorization Server can be used directly as system-wide Spring authorities.

Example:

```json
{
  "active": true,
  "scope": "orders.read",
  "roles": ["ORDER_VIEWER"],
  "permissions": ["orders.export"]
}
```

The system should decide:

| Metadata input | Approved mapping candidate | What to guard against |
|---|---|---|
| `scope=orders.read` | `SCOPE_orders.read` | Ensure the scope is intended for this API |
| `roles=["ORDER_VIEWER"]` | `ROLE_ORDER_VIEWER` | Role must be issued by AS under the right tenant/resource contract |
| `permissions=["orders.export"]` | `PERMISSION_orders.export` | Do not convert every permission into a global authority |
| `tenant_id=tenant-a` | Actor attribute | Do not turn directly into permission to read every order in `tenant-a` |
| `client_id=nightly-worker` | Client identity | Do not treat automatically as an end-user or admin |

An Authorization Server can act as a Policy Decision Point for certain permissions, yet the Resource Server must still understand each field's **semantics and scope**. Never assume a role string inside an active token bypasses domain-level checks.

### 14.1. Why Per-Issuer/Provider Mapping Is Necessary

Two providers can both return `roles=["ADMIN"]` with completely different meanings:

- Provider A: `ADMIN` of a specific application.
- Provider B: `ADMIN` of an entire realm.
- Provider C: `ADMIN` within a selected tenant.

A global converter blindly mapping that to `ROLE_ADMIN` easily opens incompatible privileges. Scope/role mapping must be tied to the **issuer contract, audience, tenant, and trust level**.

## 15. The Principal in WebFlux: How to Retrieve Metadata

After opaque introspection succeeds, a controller can receive `OAuth2AuthenticatedPrincipal` if the API uses that principal type.

```java
package com.example.orders.api;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CurrentCallerController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal
            OAuth2AuthenticatedPrincipal principal) {

        String subject = principal.getAttribute("sub");
        String clientId = principal.getAttribute("client_id");

        Map<String, String> response = new LinkedHashMap<>();
        response.put("subject", subject != null ? subject : "unspecified");
        response.put(
            "clientId",
            clientId != null ? clientId : "unspecified"
        );

        return Mono.just(response);
    }
}
```

This is an illustrative endpoint when security already protects `/api/me`; never assume a public API should expose metadata or PII like subject/client ID. Production contracts typically return only the minimum data needed by the caller.

### 15.1. Reading Authentication from the Reactor Context

In a reactive service:

```java
package com.example.orders.security;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public final class ReactiveActorProvider {

    public Mono<Authentication> current() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication is required"
                )
            ));
    }
}
```

Do not use:

```java
SecurityContextHolder.getContext().getAuthentication();
```

as the default identity lookup in a WebFlux reactive pipeline. Servlet-style `ThreadLocal` storage does not reliably carry context across `flatMap`/`publishOn`/async callbacks.

### 15.2. Never Self-`subscribe()` to Read the Subject

Wrong:

```java
reactiveActorProvider.current()
    .subscribe(authentication -> {
        // Store authentication in a shared field.
    });
```

This creates a **detached subscription** and can lose context, break authorization ordering, or leak identities across requests if stored in a singleton field.

Instead, compose within the pipeline:

```java
public Mono<OrderDto> getOrder(String id) {
    return reactiveActorProvider.current()
        .flatMap(authentication ->
            loadAuthorizedOrder(id, authentication)
        );
}
```

`loadAuthorizedOrder(...)` is a reactive application-service operation that checks scopes and object policy.

## 16. The Service Must Enforce Per-Resource Permissions

Suppose introspection returns:

```json
{
  "active": true,
  "scope": "orders.read",
  "sub": "customer-42",
  "iss": "https://login.example.com",
  "tenant_id": "tenant-a",
  "aud": ["orders-api"]
}
```

After Spring creates `SCOPE_orders.read`, a `GET /api/orders/order-9001` request may pass `authorizeExchange`. Yet if `order-9001` belongs to `customer-99` or `tenant-b`, the service must still deny it.

### 16.1. Data Model

```java
package com.example.orders.domain;

public record Order(
    String id,
    String tenantId,
    String ownerIssuer,
    String ownerSubject,
    String status
) {}
```

Reactive repository port:

```java
package com.example.orders.domain;

import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository {
    Mono<Order> findByIdAndTenantId(
        String orderId,
        String tenantId
    );
}
```

Ensure the adapter enforces the tenant filter directly in the query, rather than naming the method that way while omitting the SQL constraint.

### 16.2. Service Combining Verified Authorities and Metadata

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import com.example.orders.domain.ReactiveOrderRepository;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderQueryService {

    private final ReactiveOrderRepository repository;

    public ReactiveOrderQueryService(
            ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> read(
            String orderId,
            Authentication authentication) {

        if (!authentication.isAuthenticated()) {
            return Mono.error(
                new AccessDeniedException("Not authenticated")
            );
        }

        boolean hasReadScope = authentication.getAuthorities()
            .stream()
            .anyMatch(a ->
                "SCOPE_orders.read".equals(a.getAuthority())
            );

        if (!hasReadScope) {
            return Mono.error(
                new AccessDeniedException("Missing orders.read")
            );
        }

        if (!(authentication.getPrincipal()
                instanceof OAuth2AuthenticatedPrincipal principal)) {
            return Mono.error(
                new AccessDeniedException(
                    "Opaque token principal required"
                )
            );
        }

        String subject = principal.getAttribute("sub");
        String issuer = principal.getAttribute("iss");
        String tenant = principal.getAttribute("tenant_id");

        if (subject == null || subject.isBlank()
                || issuer == null || issuer.isBlank()
                || tenant == null || tenant.isBlank()) {
            return Mono.error(
                new AccessDeniedException("Identity metadata missing")
            );
        }

        return repository.findByIdAndTenantId(orderId, tenant)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                boolean allowed =
                    tenant.equals(order.tenantId())
                    && issuer.equals(order.ownerIssuer())
                    && subject.equals(order.ownerSubject());

                return allowed
                    ? Mono.just(order)
                    : Mono.error(
                        new AccessDeniedException(
                            "Order is not accessible"
                        )
                    );
            });
    }
}
```

`OrderNotFoundException` is an application-defined domain exception mapped to 404 per contract. The example also assumes `iss` and `tenant_id` are supplied by the AS as agreed-upon strings; if a provider returns another type, use a safe adapter instead of blind casting.

Security highlights:

1. The service never takes the owner from caller-supplied headers or path parameters.
2. `Authentication` must be valid and carry `SCOPE_orders.read`.
3. The principal was produced after introspection, not from unverified Bearer data.
4. Tenant/issuer/subject are used according to the accepted metadata contract.
5. The repository filters by tenant, and the service verifies ownership.
6. Unauthorized access emits `Mono.error(...)`, never returning data.
7. `active=true` does not replace object-level permission checks.

This example models **user-owned orders**; machine-to-machine tokens require their own use cases and policies rather than assuming `sub` is always a customer.

## 17. Method Security for WebFlux

For reactive method security, enable:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {}
```

Example:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderDto> getOrder(String id) {
    return repository.findAuthorizedOrder(id);
}
```

`OrderDto`/`repository` are hypothetical application components. The annotation protects calls passing through a Spring-managed proxy when a reactive security context is present.

However:

- `@PreAuthorize` checks scopes; it does not automatically know who owns an order.
- When a service is invoked from a message consumer or scheduler with no HTTP request, there is no Resource Server Reactor authentication context by default.
- Self-invocation within the same bean can bypass the proxy.
- For mutations, object policies and state must be checked within the appropriate transaction/concurrency boundary.
- Never rely on `@PostAuthorize` as the sole defense after side effects have already occurred.

## 18. Changing Metadata: Caching and Revocation

One advantage of introspection is that the Authorization Server can return `active=false` once a token is revoked. However, this depends on when the RS **actually re-introspects**.

### 18.1. Without Caching

```text
Request 1 -> AS introspection -> active=true
Request 2 -> AS introspection -> active=true
Admin revokes token
Request 3 -> AS introspection -> active=false
```

This is the logical model without caching when the AS reflects revocation. Even so, the AS may have replication lag or internal policies, so millisecond-exact guarantees cannot be promised.

### 18.2. With Caching

```text
Request 1 -> AS -> active=true -> cache 3 minutes
Admin revokes token
Request 2 -> cache hit -> still sees active=true
Cache expires
Request 3 -> AS -> active=false
```

Caching reduces network traffic and latency, but creates a **revocation delay**. Metadata such as roles, tenant membership, and scopes can also become stale during the cache window.

A guiding rule:

```text
effectiveCacheTTL <= min(
  configuredMaxTTL,
  remainingTokenLifetimeFromExp,
  acceptableRevocationDelay
)
```

This is a design guideline, not a default Spring Security TTL. Do not assume `ReactiveOpaqueTokenIntrospector` caches results by default. If you add a custom caching decorator, bound TTL, size, keys, concurrency, and invalidation rules.

### 18.3. Token Cache Keys Are Sensitive Data

An opaque token is a Bearer credential. Never expose raw tokens in logs, metric labels, trace baggage, or cache admin UIs. A cache must protect its keys and values and avoid persisting tokens in uncontrolled systems.

You can use a properly designed hash/HMAC key to reduce raw-token exposure in keys, but do not assume hashing alone is sufficient if cache payloads or request logs still retain tokens.

## 19. Reactive WebFlux and HTTP Introspection

### 19.1. Never Use a Blocking HTTP Client on the Event Loop

A custom introspector written like this is an anti-pattern:

```java
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    // INTENTIONALLY WRONG: blocking I/O inside a reactive path.
    String json = restTemplate.postForObject(
        introspectionUri,
        token,
        String.class
    );

    return Mono.just(buildTrustedPrincipalWithoutValidation(json));
}
```

Dual problem:

- A blocking HTTP call can stall the Netty event loop.
- Parsing JSON manually without thoroughly checking `active`/metadata can create invalid authentications.

Prefer the official `ReactiveOpaqueTokenIntrospector` implementation backed by a proper reactive HTTP client; if custom transport is needed, preserve HTTP authentication, TLS, form encoding, `active` verification, and error semantics.

### 19.2. Timeouts and Connection Pools

An introspection call can experience:

- Waiting to acquire a connection from the pool.
- DNS resolution.
- TCP connect.
- TLS handshake.
- Waiting for the AS HTTP response.
- Reading and parsing JSON.

`responseTimeout` does not necessarily cover every phase; enforce an explicit overall deadline to bound total latency. When the AS is slow, WebFlux requests remain live in the pipeline longer even without tying up OS threads—still consuming memory, connection pool slots, and in-flight concurrency.

Design for:

1. Connect/read/overall timeouts matching SLAs.
2. Bounded connection pools and pending-acquire limits.
3. Concurrency limits, rate limits, and DoS protection.
4. Conditional retries with small attempt counts; never retry `active=false`.
5. **Fail-closed** circuit breakers that never convert errors into `active=true`.
6. Telemetry by outcome/latency/error class without logging tokens or secrets.

### 19.3. A Malformed 200 Response Must Be Rejected

If an AS or proxy returns:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active":"true"}
```

the `active` field is a **string**, not a boolean as required by the RFC. A strict parser must not treat arbitrary "truthy" values or the string `"true"` as boolean true outside the contract. Use the standard implementation/parser or validate the schema.

Similarly, a response missing `active` does not default to `active=true`.

## 20. Bearer 401 and 403 Error Responses

Distinguish the primary failure modes:

| Scenario | Authentication | Typical API response |
|---|---|---|
| No token sent to a protected endpoint | Unauthenticated | **401**, `WWW-Authenticate: Bearer` |
| Introspection returns `active=false` | Invalid | **401 invalid_token** |
| Malformed token or invalid credential format | Invalid | **400 invalid_request** or 401 per RFC/policy context |
| Active token missing `orders.read` | Authenticated, insufficient scope | **403 insufficient_scope** |
| Active token with scope, wrong owner/tenant | Object policy denies | **403** or **404** per policy |
| Wrong introspection client ID/secret | RS → AS failure | Fail closed; classify dependency error |
| AS timeout / 5xx / TLS error | No trusted decision | Fail closed; map 5xx/503 per config |
| Metadata missing required `aud` | Token fails contract | Do not construct an accepted Authentication |
| Metadata has wrong types | Fails schema/policy | Reject; never "fix" into default privileges |

### 20.1. Do Not Redirect APIs to an HTML Login Page

A WebFlux Resource Server receiving Bearer tokens must respond with a Bearer challenge per RFC 6750. Never configure `oauth2Login` or `formLogin` as the default entry point for an API.

In an API, `401` is normally a signal for the **OAuth client** to handle the access token and run the appropriate refresh or login flow. The Resource Server does not exchange refresh tokens itself or redirect API callers to HTML login pages.

### 20.2. System Errors Are Not Scope Errors

If the AS times out, it is impossible to know whether the token is active or what scopes it holds. Never return `403 insufficient_scope` simply because the AS was unreachable; that is an **unverifiable state** caused by a dependency failure, not proof of a valid token lacking privileges.

If clients should receive `503` during an AS outage, configure and test explicit exception handling; Spring does not automatically return 503 for every error type across all versions.

## 21. Testing Scope Mapping with WebTestClient

`WebTestClient` fits WebFlux. Spring Security Test provides a helper to simulate an opaque authentication for testing authorization.

Dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

### 21.1. Testing Permissions with `mockOpaqueToken()`

Example test fragment using a `WebTestClient` bound to Spring Security:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

client.mutateWith(
        mockOpaqueToken()
            .attributes(attrs -> {
                attrs.put("sub", "customer-42");
                attrs.put("tenant_id", "tenant-a");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
    )
    .get()
    .uri("/api/orders/order-42")
    .exchange()
    .expectStatus().isOk();
```

Prerequisites: test fixtures include `order-42` owned by `customer-42`/`tenant-a` and the endpoint is configured appropriately. If domain policy denies, the test may return 403/404; that reflects fixture/authorization setup rather than a flaw in `mockOpaqueToken`.

**Important limitation:** `mockOpaqueToken()` injects a fake Authentication into the test. It **does not send a real Bearer token through HTTP introspection**, does not check `active=false`, and does not prove HTTP Basic credentials, TLS, or AS metadata handling are correct.

### 21.2. Testing Missing Scope

```java
client.mutateWith(
        mockOpaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_unrelated")
        )
    )
    .get()
    .uri("/api/orders/order-42")
    .exchange()
    .expectStatus().isForbidden();
```

This test proves the route requires `SCOPE_orders.read`, not the parsing logic for RFC `scope` strings from AS responses. To test actual mapping, integrate a delegate introspector or fake AS.

### 21.3. Testing Missing Token

```java
client.get()
    .uri("/api/orders/order-42")
    .exchange()
    .expectStatus().isUnauthorized();
```

Also verify `WWW-Authenticate: Bearer` and the absence of `Location: /login` if the app has a web login chain.

## 22. Integration Testing with a Fake Authorization Server

To test **`active`, HTTP metadata, and real scope mapping**, send a Bearer header through the filter chain and configure a **fake introspection endpoint** in the test environment. The fake AS must accept proper form POSTs and authenticate the introspection client per the registered method.

### 22.1. Key Scenarios

| Test | Fake introspection response | Expected outcome |
|---|---|---|
| Active token, read scope | `200 {"active":true,"scope":"orders.read",...}` | Creates authentication with `SCOPE_orders.read` |
| Active token, read+write scopes | `200 {"active":true,"scope":"orders.read orders.write"}` | Has both corresponding authorities |
| Inactive token | `200 {"active":false}` | Unauthenticated, Bearer 401 |
| Active without scope | `200 {"active":true}` | No auto-granted scopes; scoped routes deny |
| Active missing write scope | `200 {"active":true,"scope":"orders.read"}` | POST requiring write returns 403 |
| Active, wrong audience | `200 ... "aud":["billing-api"]` | Audience policy/decorator rejects |
| Active, wrong issuer | `200 ... "iss":"https://other.example"` | Issuer policy rejects if required |
| Active, wrong tenant/owner | Valid metadata, resource belongs to another actor | Service denies |
| String `active` | `200 {"active":"true"}` | Not treated as valid active |
| Missing `active` | `200 {"scope":"orders.read"}` | No valid authentication result |
| Wrong `scope` type | `200 {"active":true,"scope":42}` | Does not fabricate `SCOPE_*`; handled per contract |
| `scp` array extension | `200 ... "scp":["orders.read"]` | Mapped only when custom adapter is configured |
| AS returns 401 | Basic client authentication error | Fail closed, classify config error |
| AS returns 503 | Dependency outage | Fail closed, no principal granted |
| AS timeout / invalid TLS | No trusted response | Fail closed, reflect infrastructure error properly |
| M2M token | `client_id=nightly-worker`, service `sub` | Enforce client/workload policy, do not assume user |

### 22.2. Structuring Tests to Truly Exercise Introspection

1. Start a local fake server with a POST introspection endpoint.
2. Point the test `introspection-uri` to the fake server.
3. Provide harmless test client ID/secret values (never production secrets).
4. Send `Authorization: Bearer TEST_OPAQUE_TOKEN` via `WebTestClient`.
5. Let `AuthenticationWebFilter`, the manager, and `ReactiveOpaqueTokenIntrospector` execute end to end.
6. Have the fake AS return `active`/metadata per test case.
7. Assert 401/403/200 responses and, if needed, inspect authorities/principal in a protected test handler.
8. Assert the fake AS received `Content-Type: application/x-www-form-urlencoded`, the `token` field, and proper client authentication.
9. Test timeouts, malformed JSON, and TLS in a controlled environment.
10. Never log raw test secrets or tokens if CI artifacts share logs.

Never cite `mockOpaqueToken()` as proof that real HTTP metadata handling works; that helper intentionally bypasses the network layer.

### 22.3. Testing Scope Mapping at the Introspector Level

You can use a **fake delegate** returning a test principal assumed to have passed `active` validation, then invoke `ScpMappingIntrospector` directly to test the custom `scp` extension:

```java
ReactiveOpaqueTokenIntrospector delegate = token ->
    Mono.just(new DefaultOAuth2AuthenticatedPrincipal(
        "customer-42",
        Map.of(
            "sub", "customer-42",
            "scp", List.of("orders.read", "orders.export")
        ),
        List.of()
    ));

ReactiveOpaqueTokenIntrospector mapper =
    new ScpMappingIntrospector(delegate);

StepVerifier.create(mapper.introspect("test-token"))
    .assertNext(principal -> {
        Set<String> names = principal.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());

        assertThat(names).contains(
            "SCOPE_orders.read",
            "SCOPE_orders.export"
        );
    })
    .verifyComplete();
```

This is a **test fragment**; add imports for `Mono`, `DefaultOAuth2AuthenticatedPrincipal`, `List`, `Map`, `Set`, `Collectors`, `StepVerifier`, and your assertion library.

It tests only the **scope-mapping adapter**, not RFC `active` handling or the HTTP client. Full fake-AS tests are still necessary.

## 23. Classifying Errors by Layer for Reliable Operations

When a request returns 401/403, pinpoint which layer triggered the failure.

| Layer | Symptom | How to diagnose |
|---|---|---|
| Inbound HTTP | Missing Bearer token | Check request headers and security matchers |
| Authentication converter | Malformed Bearer header | Check Bearer syntax per RFC 6750 |
| Introspection transport | TLS/DNS/connect/timeout | Check egress, AS URL, HTTP client |
| Introspection client auth | AS returns HTTP 401/403 | Check client ID/secret and permissions |
| Token status | AS returns `active=false` | Token is rejected |
| Metadata schema | `active=true` but missing/wrong `aud`, `iss`, `scope` | Verify AS–RS contract |
| Authority mapping | Active principal lacks `SCOPE_*` | Check introspector and extension converter |
| Endpoint authz | Scope fails `authorizeExchange` | Check route and authority policy |
| Method/object authz | Wrong owner/tenant/state | Check service policy and database state |

### 23.1. Never Log Credentials While Debugging

Never log:

```text
Authorization: Bearer <raw token>
Authorization: Basic <base64 client-id:secret>
body: token=<raw token>
introspection_response=<full PII claims>
```

Log error codes, timestamps, endpoint group, allowlisted AS host, and request correlation ID instead. If subject/client auditing is required, define minimal data, retention limits, and access controls.

### 23.2. Useful Metrics

Consider measuring:

- `introspection.requests` broken down by outcome `active|inactive|error`.
- `introspection.duration` p50/p95/p99.
- `introspection.http.status` and client-authentication failures.
- `introspection.timeout` / `tls.error`.
- `opaque.scope_mapping.error` when metadata breaks schema.
- `authorization.insufficient_scope`.
- `authorization.object_denied`.
- `connection.pool.active/pending`.
- `cache.hit/miss` and revocation lag if a caching decorator is used.

Metric names are suggestions only. **Never use raw tokens, `sub`, or arbitrary caller `client_id` values as metric labels**, as that both leaks data and causes high cardinality.

## 24. Anti-Patterns to Avoid

### 24.1. "HTTP 200 Means Active"

Wrong. You must inspect boolean `active`. `200 {"active":false}` is an inactive token.

### 24.2. "Missing `active` Defaults to True"

Wrong. A response lacking `active` provides no proof the token is active under RFC 7662.

### 24.3. "`active=true` Grants Admin Access"

Wrong. `active` only confirms token status; scopes and domain permissions must be evaluated independently.

### 24.4. "If Scope Is Present, the Actor Owns Every Order"

Wrong. Scopes gate action classes; the service enforces tenant, ownership, delegation, and resource state.

### 24.5. "`client_id` in the Response Is the Introspecting Client ID"

Wrong. `client_id` identifies the client that received the token; introspection credentials belong to the Resource Server.

### 24.6. "`sub` Is Always a User ID"

Wrong. In machine-to-machine flows, `sub` can hold a service/client identity or a provider-specific identifier per the AS contract.

### 24.7. "All Providers Format Scopes Identically"

Wrong. RFC 7662 specifies a `scope` string; extensions such as `scp` arrays need an explicit provider-specific converter.

### 24.8. "Map Every `roles` Claim to `ROLE_ADMIN`"

Wrong. Roles and permissions require clear semantics, issuer/audience/tenant constraints, and an allowlist.

### 24.9. "Build a `DefaultOAuth2AuthenticatedPrincipal` When the AS Is Unreachable"

Wrong. That is an authentication bypass. When the AS fails, fail closed or rely only on an approved cache with explicit TTL/revocation risk bounds.

### 24.10. "Reactive Means Wrapping `RestTemplate` in `Mono.just`"

Wrong. `Mono.just(...)` does not make blocking HTTP I/O non-blocking. Use a proper reactive transport.

### 24.11. "A `mockOpaqueToken` Test Proves `active=false` Works"

Wrong. It injects a mock principal and skips HTTP introspection; use an integration test with a fake AS.

### 24.12. "The Introspection Client Has a Secret, So TLS Verification Is Unnecessary"

Wrong. HTTP Basic/Base64 is not encrypted on the wire; enforce HTTPS and verify certificates and hostnames.

### 24.13. "The Resource Server Can Read the Introspection URL from the Token"

Wrong. That creates SSRF and credential-exfiltration risks. The introspection URI must come from trusted configuration or an allowlist, never from unverified headers or JWT claims.

### 24.14. "Cache `active=true` Forever for Speed"

Wrong. That defeats revocation, preserves stale scopes/roles, and risks accepting expired tokens. TTLs must be bounded by `exp` and revocation policy.

## 25. Adoption Workflow for an Orders API

### Step 1 — Align on the Contract with the Authorization Server

At minimum, establish:

- Exact introspection endpoint and client authentication method.
- Token types permitted for introspection and accepted by the Orders API.
- Whether `active` is returned as a boolean per RFC 7662.
- Whether `scope` is a standard string or a provider extension.
- Whether `aud`/`iss` are returned and their semantics.
- Whether `sub` represents a user or a service per grant type.
- What `tenant_id`/roles/permissions extensions can be trusted for.
- Revocation policy, max token lifetime, rate limits, and caching constraints.
- Which metadata fields the introspection client is allowed to see.

### Step 2 — Configure HTTPS and Client Credentials

```yaml
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri:
  https://login.example.com/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id:
  ${ORDERS_INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret:
  ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Never commit real secrets; configure CA/truststore, proxy/egress rules, and timeouts per environment.

### Step 3 — Enable the Reactive Resource Server

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

Use `SecurityWebFilterChain` instead of Servlet `SecurityFilterChain`.

### Step 4 — Add Mandatory Metadata Validators

Use a `ReactiveOpaqueTokenIntrospector` decorator to check `aud`, `iss`, token type, or other contract claims. Ensure the delegate still enforces `active` and network error handling.

### Step 5 — Map Scopes Transparently

Preserve `SCOPE_*` from standard `scope`. If the AS uses a `scp` extension, add an explicit allowlist-based mapping; never elevate privileges to admin automatically.

### Step 6 — Separate Endpoint Authorization from Domain Policy

`hasAuthority("SCOPE_orders.read")` gates action types; the service also checks the specific order, tenant/owner, and business rules.

### Step 7 — Test Across Three Tiers

1. **Unit tests** for mapping/policy with synthetic principals.
2. **`WebTestClient`** tests for 401/403 and error handlers.
3. **Integration tests** with a fake introspection server covering `active`, metadata schemas, HTTP Basic, TLS, timeouts, and permissions.

### Step 8 — Operate Fail-Closed

Monitor AS latency, rate limits, client-secret rotation, TLS errors, and cache/revocation trade-offs. Whenever the AS cannot prove a token is active, **never grant speculative access**.

## 26. References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, introspection endpoint, metadata responses, and endpoint protection policies.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens, client authentication, and scopes.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, 401/403, `invalid_token`, and `insufficient_scope`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): AS discovery metadata, introspection endpoint, and client auth methods.
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): configuring `ReactiveOpaqueTokenIntrospector` and opaque authentication.
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): Bearer authentication in WebFlux.
- [Spring Security — WebFlux Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange` and request-level policies.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` and service-layer authorization.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context propagation mechanics.
- [OWASP API Security Top 10 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): why scopes are insufficient for per-object authorization.

**Conclusion:** In reactive introspection, `ReactiveOpaqueTokenIntrospector` turns an untrusted Bearer string into an `OAuth2AuthenticatedPrincipal` **only after the Authorization Server confirms the token is active**. Response metadata communicates scope, subject, client, issuer, audience, and other contract attributes. Spring Security WebFlux maps standard scopes into `SCOPE_*` authorities for `authorizeExchange` and method security, yet **neither `active` nor scopes replace audience, tenant, ownership, or business-state checks**. When metadata is missing or malformed, a token is inactive, or the Authorization Server is unreachable, the Resource Server must **fail closed** and never fabricate a privileged principal.
