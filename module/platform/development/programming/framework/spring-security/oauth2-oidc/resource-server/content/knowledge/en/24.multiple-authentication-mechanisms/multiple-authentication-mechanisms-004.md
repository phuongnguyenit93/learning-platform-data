# Separating Endpoints, Issuers, or Tenants for Clear Strategy Selection

## 1. The Problem When an Application Has Multiple Authentication Mechanisms

A **Spring Security OAuth 2.0 / OIDC Resource Server** may receive requests from multiple caller groups. Not every group uses the same credential type or holds the same trust level:

- Mobile apps send **JWT access tokens** to the Orders API.
- Partners send **opaque access tokens**, which the Resource Server verifies via introspection.
- Staff access the admin portal via **OIDC Login and session/cookies**.
- Internal microservices send JWTs issued by a dedicated issuer for service accounts.
- Multiple organizations (**tenants**) use different Authorization Servers or share an issuer while requiring data-permission isolation.

If you simply "try every authentication method for every endpoint", the system easily suffers from **authentication confusion**, **token substitution**, **downgrade**, or **cross-tenant access**. A validly signed token may not be intended for this API; an authenticated principal may not be allowed to read another tenant's data.

This lesson explains three independent separation dimensions:

| Dimension | Question | Role |
|---|---|---|
| **Endpoint** | Which URL group is the request entering? | Selects the authentication mechanism per API contract |
| **Issuer** | Which Authorization Server did the access token come from? | Selects a trusted manager/decoder and checks `iss`, signature, `aud` |
| **Tenant** | Which organization is the caller asking to operate on? | Enforces data boundaries, membership, entitlements, and ACLs |

**Overarching principle:** information used for **routing** does not automatically become information for **granting permissions**. URLs, headers, Hosts, or unverified `iss`/`tenant_id` claims can all be controlled by the caller.

## 2. Choosing Strategy by Purpose, Not by Trial-and-Error

A clear design might stipulate:

~~~text
/api/orders/**     -> JWT Resource Server, Orders issuer
/api/partners/**   -> Opaque token Resource Server, partner introspection
/console/**        -> Browser OIDC Login + session
/actuator/health   -> Dedicated health policy
unmatched paths    -> Deny
~~~

Another system might let **the same endpoint** accept JWTs from two trusted issuers. In that case, you need a **multi-issuer resolver** inside the JWT chain, rather than mechanically splitting URLs by issuer.

### 2.1. Architectural Decision Tree

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Endpoint group"}
    B -->|"/api/partners/**"| C["Opaque introspection"]
    B -->|"/api/orders/**"| D["JWT / trusted issuer resolver"]
    B -->|"/console/**"| E["OIDC session login"]
    B -->|"Unknown"| X["Fallback deny"]
    C --> F["Token active + token contract"]
    D --> G["Verify signature + issuer + audience + time"]
    E --> H["Session authentication"]
    F --> I["Authenticated principal"]
    G --> I
    H --> I
    I --> J{"Action scope / role?"}
    J -->|No| K["403 or policy response"]
    J -->|Yes| L{"Tenant + owner + ACL?"}
    L -->|No| K
    L -->|Yes| M["Business handler"]
~~~

**Never** conclude that an API is protected simply because a valid branch was found. Each branch must have proper validators and authorization policies.

### 2.2. Four Security Requirements for Every Branch

1. **Trust** — accept only approved issuers/providers.
2. **Intended audience** — the token must be issued for the right Resource Server.
3. **Authority semantics** — scopes/roles must be interpreted accurately according to the issuer's profile.
4. **Resource isolation** — still verify tenant, owner, membership, and ACLs on the resource.

Each part can fail independently. A token with a valid signature but wrong audience must still be rejected; a token with the right audience and read scope can still be denied if it does not belong to that tenant.

## 3. Spring Security Servlet: Two Layers of Policy Selection

In **Spring MVC / Servlet**, `FilterChainProxy` walks through the configured `SecurityFilterChain` beans. A request attaches to **the first matching chain**; it does not run sequentially through every chain to accumulate or pick the easiest policy.

~~~text
Servlet request
    |
    v
DelegatingFilterProxy
    |
    v
FilterChainProxy
    |
    +-- @Order(1): /api/partners/**  -> opaqueToken()
    +-- @Order(2): /api/orders/**    -> jwt()
    +-- @Order(3): /console/**       -> oauth2Login()
    +-- @Order(99): /**             -> denyAll()
~~~

Foundational class names:

~~~java
org.springframework.security.web.SecurityFilterChain
org.springframework.security.config.annotation.web.builders.HttpSecurity
org.springframework.security.web.FilterChainProxy
~~~

### 3.1. `securityMatcher` Differs from `requestMatchers`

~~~java
http.securityMatcher("/api/partners/**");
~~~

defines: **which URL group does this chain apply to?**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/partners/reports/**")
        .hasAuthority("SCOPE_partner.reports.read")
    .anyRequest().denyAll()
);
~~~

defines: **inside the selected chain, which authorities are required?**

A `securityMatcher("/api/**")` chain ordered before a `securityMatcher("/api/admin/**")` chain can prevent the admin chain from **ever being selected**. Never rely on a strict rule in a later chain if an earlier chain already matches the request.

### 3.2. When to Separate by Endpoint?

Appropriate when URL zones genuinely have **different credential contracts**, such as:

- Bearer JWT vs. opaque introspection.
- Machine API vs. browser OIDC login.
- Public health vs. internal API.
- Presence/absence of sessions/cookies and CSRF policy.
- Bearer JSON 401/403 errors vs. browser redirects.

If all endpoints use one JWT issuer and differ only in scopes per HTTP method, **one chain with multiple `requestMatchers`** is usually simpler and less risky than multiple chains.

## 4. Example: Separating JWT and Opaque Tokens Across Two Endpoint Groups

Assumed contract:

~~~text
/api/orders/**:
    JWT access token
    issuer = https://id.example.test/realms/orders
    audience = orders-api

/api/partners/**:
    opaque access token
    introspection endpoint = https://partner-id.example.test/oauth2/introspect
    scopes = partner.reports.read, partner.reports.write
~~~

Both mechanisms are Resource Server authentication, but **selected by URL** with no fallback to the other mechanism when a token fails.

### 4.1. Gradle Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

If adding OIDC browser login, you may also need:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
~~~

Do not add OAuth2 Client just to verify access tokens on an API; those are two different capabilities.

### 4.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/orders
          audiences:
            - orders-api
        opaquetoken:
          introspection-uri: https://partner-id.example.test/oauth2/introspect
          client-id: orders-partner-introspector
          client-secret: ${PARTNER_INTROSPECTION_CLIENT_SECRET}
~~~

URLs are illustrative. Secrets must come from environment variables or a secret manager, never committed to Git or exposed to browsers. The `audiences` property requires a supporting Spring Boot version; if creating a custom decoder bean, ensure audience validation is not lost.

### 4.3. Three Chains with Fixed Ordering

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class EndpointSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain partnerApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/partners/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/partners/reports/**")
                    .hasAuthority("SCOPE_partner.reports.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/orders/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(99)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

This is an **alternative architecture** to a typical single-chain setup. Do not register an additional `/**` chain with higher precedence that accidentally shadows these chains.

Notes:

- Both API chains assume **Bearer-only, no cookie/session authentication**, so disabling CSRF can fit after evaluating the threat model. Do not apply that to a browser login chain.
- `/api/orders/**` and `/api/partners/**` should be tested on exact root paths like `/api/orders` or `/api/partners` if controllers map at root; path matcher behavior can vary by version/trailing slash.
- Fallback `denyAll` ensures undeclared paths are not left open accidentally. If you need health, actuator, API docs, or OIDC callbacks, add explicit policies.
- The fallback response does not always have to be 401; the goal is **deny** per contract.
- Scopes only check action-level permissions; tenant, owner, and ACLs must be verified in the business service.

### 4.4. Request Matrix

| URL | Token | Required strategy |
|---|---|---|
| `GET /api/orders/42` | Valid Orders JWT | JWT validation + `orders.read` |
| `POST /api/orders/42` | Orders JWT with only `orders.read` | 403 for missing write scope |
| `GET /api/orders/42` | Partner opaque token | No fallback to opaque introspection |
| `GET /api/partners/reports/2026` | Active partner opaque | Introspection + partner scope |
| `GET /api/partners/reports/2026` | Orders JWT | No fallback to JWT decoding |
| `GET /api/unlisted` | Any token | Fallback deny |
| Partner introspection timeout | Partner token | Never fail open |

Passing through the filter chain does not guarantee the controller returns HTTP 200; the service may return 404, 409, or deny due to business policy.

## 5. Do Not Guess Strategy from Access Token Shape

An easy mistake:

~~~java
if (token.split("\\.").length == 3) {
    // Try JWT
} else {
    // Try opaque token
}
~~~

It is unsafe to treat this as an authentication contract:

- Opaque tokens can contain dots.
- A three-part string does not prove a valid JWS.
- JWT/JWE can have various different token profiles.
- Attackers control the entire token string.
- Providers may change token formats without changing the API contract.

**Avoid "if JWT verify fails, try opaque and accept if it works" logic**. That turns a signature failure into an opportunity to try another mechanism, potentially leading to a downgrade. If an endpoint genuinely must accept multiple formats, use an `AuthenticationManagerResolver<HttpServletRequest>` or equivalent with a **predefined routing policy, allowlisted providers, and separate validators**.

Never use a caller-supplied query parameter or header like:

~~~http
X-Authentication-Mode: bypass-jwt
~~~

to switch to a weaker branch. If a gateway forwards security metadata, protect the trust boundary with TLS/mTLS, header stripping, and block direct external access to the backend.

## 6. When the Same Endpoint Accepts Multiple JWT Issuers

Suppose `GET /api/orders/**` allows tokens from two Authorization Servers:

~~~text
Retail issuer:
https://id.example.test/realms/retail

Enterprise issuer:
https://id.example.test/realms/enterprise
~~~

If only one `issuer-uri` is configured, the other issuer is normally rejected. If you remove `iss` checking to "accept both", the API may accept tokens from uncontracted sources.

The solution is **multi-issuer authentication with a trusted issuers allowlist**.

### 6.1. `JwtIssuerAuthenticationManagerResolver`

In Servlet Spring Security:

~~~java
org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver
~~~

The resolver picks an appropriate `AuthenticationManager` from the issuer claim to route to a decoder with the corresponding trust profile.

**Critical security point:** the `iss` read from the token **before** verifying the signature must be used strictly as an **untrusted routing hint**. It does not prove the token was issued by that issuer. The resolver must select only from a trusted allowlist, and then the decoder must verify signature, issuer, expiry, and audience.

### 6.2. Explicit Issuer Configuration

With Spring Security's `fromTrustedIssuers(...)` API, for example:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

@Configuration
public class TrustedIssuerConfig {

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            "https://id.example.test/realms/retail",
            "https://id.example.test/realms/enterprise"
        );
    }
}
~~~

Attach it to the chain accepting multiple issuers:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersMultiIssuerSecurity {

    @Bean
    SecurityFilterChain ordersJwtChain(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver resolver)
            throws Exception {

        return http
            .securityMatcher("/api/orders/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

This is an **alternative configuration** to the single-issuer JWT chain in section 4. When using it, do not declare both chains with the same matcher without defining precedence.

`fromTrustedIssuers` and its overloads may differ between Spring Security 6.x and 7.x; use the exact version-matched API in real projects. The core idea is **trusted issuer registry + manager verifying the exact issuer**.

### 6.3. An Issuer Allowlist Does Not Imply Audience Validation

A token:

~~~json
{
  "iss": "https://id.example.test/realms/retail",
  "aud": ["billing-api"],
  "scope": "invoices.read"
}
~~~

might be validly signed by a **trusted issuer** yet still **not intended for the Orders API**. You must check that `aud` contains `orders-api` or an equivalent token audience contract.

Do not assume the factory issuer resolver automatically attaches every **custom audience/profile validator**. When multiple profiles are needed, each issuer manager can be configured with its own decoder and corresponding validators.

### 6.4. Creating a Decoder with Issuer + Audience Validators

~~~java
package com.example.orders.security;

import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public final class OrdersDecoders {

    private OrdersDecoders() {}

    public static NimbusJwtDecoder forIssuer(
            String trustedJwksUri,
            String trustedIssuer,
            String requiredAudience) {

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(trustedJwksUri).build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(trustedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(requiredAudience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Incorrect access token audience",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
~~~

This is a **factory creating one decoder for one issuer**. Simply creating a decoder bean does not mean a multi-issuer resolver automatically uses it; you must wire the corresponding manager/decoder into the registry. When customizing `JwtDecoder`, preserve signature/algorithm/trust, issuer, expiry/not-before, audience, and token profile validators.

### 6.5. Manager Registry per Issuer

An explicit pattern on Spring Security 6.x versions offering a constructor accepting `AuthenticationManagerResolver<String>`:

~~~java
package com.example.orders.security;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

@Configuration
public class ManagerRegistryConfig {

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {

        AuthenticationManager retail = manager(
            "https://id.example.test/realms/retail",
            "https://id.example.test/realms/retail/protocol/openid-connect/certs",
            "orders-api"
        );

        AuthenticationManager enterprise = manager(
            "https://id.example.test/realms/enterprise",
            "https://id.example.test/realms/enterprise/protocol/openid-connect/certs",
            "orders-api"
        );

        Map<String, AuthenticationManager> trusted = Map.of(
            "https://id.example.test/realms/retail", retail,
            "https://id.example.test/realms/enterprise", enterprise
        );

        return new JwtIssuerAuthenticationManagerResolver(trusted::get);
    }

    private static AuthenticationManager manager(
            String issuer,
            String jwksUri,
            String audience) {

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(
                OrdersDecoders.forIssuer(jwksUri, issuer, audience)
            );

        return provider::authenticate;
    }
}
~~~

This constructor/API pattern may be deprecated or replaced in newer versions; use the version-matched equivalent if needed. Never enable two `issuerResolver` beans of the same type simultaneously in one configuration without explicit wiring.

Security highlights of this pattern:

- The map contains only preconfigured issuers.
- Unknown issuer → no manager to authenticate.
- JWKS URI is a server-decided value, **never taken from the `jku` claim or a request header**.
- The selected manager still verifies the signature and `iss`/`aud`.
- Never read `iss` and treat it as proof of token validity.

### 6.6. Performance and Availability Notes

Multi-issuer setups can involve multiple JWKS caches, DNS/TLS dependencies, key rotation schedules, and differing token profiles. You need dedicated timeouts, metrics, and key-fetch failure policies.

If the AS is unavailable when new keys are needed, **never fail open**. Distinguish `invalid_token` from infrastructure `jwks_unavailable` errors in telemetry so you don't force clients to re-login repeatedly during a key-service outage.

## 7. Tenant Is a Data Scope, Not Authentication Proof

Suppose a request arrives:

~~~http
GET /tenants/tenant-b/orders/42 HTTP/1.1
Authorization: Bearer <TOKEN>
X-Tenant-Id: tenant-b
~~~

The caller can modify the path or header to another tenant. Those are only **requested tenant context**, not valid permissions.

Verified JWT:

~~~json
{
  "iss": "https://id.example.test/realms/retail",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

A `tenant-a` token must not read `tenant-b` merely because the path contains `tenant-b`.

### 7.1. Sources of Tenant Information

| Source | Initial trust level | Proper use |
|---|---|---|
| `/tenants/{tenant}/...` | Client-controlled | Select requested tenant; bind after auth |
| `X-Tenant-Id` | Client-controlled unless gateway-protected | Never use as an authority |
| Host/subdomain | Needs normalization and trusted proxy policy | Route only within allowlist |
| JWT `tenant_id` before signature verification | Untrusted | Never grant permissions |
| JWT `tenant_id` after validation | Confirmed by issuer per contract | Bind to URL and resource |
| Database membership | Internal data | Check current permissions |
| Server-side tenant-to-issuer registry | Trusted policy | Select managers/validators; never grant access directly |

### 7.2. Binding Request Tenant to the Authenticated Principal

A policy bean can be used with `@PreAuthorize` in Servlet Resource Server:

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component("tenantAccess")
public class TenantAccessPolicy {

    private final OrderAccessRepository access;

    public TenantAccessPolicy(OrderAccessRepository access) {
        this.access = access;
    }

    public boolean canRead(
            Authentication authentication,
            String requestedTenant,
            long orderId) {

        if (authentication == null ||
                !(authentication.getPrincipal() instanceof Jwt jwt)) {
            return false;
        }

        Object tenantClaim = jwt.getClaims().get("tenant_id");
        String subject = jwt.getSubject();

        if (!(tenantClaim instanceof String tokenTenant)
                || tokenTenant.isBlank()
                || subject == null
                || subject.isBlank()) {
            return false;
        }

        if (!tokenTenant.equals(requestedTenant)) {
            return false;
        }

        // Must check entitlement, owner, and that order belongs to tenant.
        return access.canReadOrder(subject, tokenTenant, orderId);
    }
}
~~~

`OrderAccessRepository` is a domain interface implemented by the application.

Service:

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class TenantOrdersService {

    private final OrderRepository orders;

    public TenantOrdersService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @tenantAccess.canRead(authentication, #tenant, #orderId)"
    )
    public OrderDto load(String tenant, long orderId) {
        return orders.findDtoByTenantAndId(tenant, orderId);
    }
}
~~~

Controller calling through the Spring-managed service proxy:

~~~java
@RestController
@RequestMapping("/tenants/{tenant}/orders")
public class TenantOrdersController {

    private final TenantOrdersService orders;

    public TenantOrdersController(TenantOrdersService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    public OrderDto load(
            @PathVariable String tenant,
            @PathVariable long orderId) {
        return orders.load(tenant, orderId);
    }
}
~~~

Corresponding controller imports belong to `org.springframework.web.bind.annotation.*`. Enable `@EnableMethodSecurity` and ensure `@PreAuthorize` is invoked **through the AOP proxy**, not bypassed via `this.load(...)` inside the same target bean.

Additionally, `#tenant` and `#orderId` in SpEL require parameter names to resolve accurately (e.g., Java compiler `-parameters`). Checking policy in the service does not replace database query isolation; repositories must also filter by tenant/owner.

### 7.3. When One User Is Authorized for Multiple Tenants

If business rules require cross-tenant access, do not simply write:

~~~java
if (hasRole("ADMIN")) return true;
~~~

Instead, require an **explicit delegation policy**:

~~~text
(trusted issuer, subject)
  -> membership/delegation record
  -> allowed tenant set
  -> allowed action set
  -> expiry and approval state
  -> audit
~~~

A token with `tenant_id=tenant-a` must not automatically access every tenant via an unverified global role. Cross-tenant admin support requires independent approval and auditing policies.

## 8. When the Tenant Determines the Issuer

Example server registry:

~~~text
tenant-a -> https://id.example.test/realms/retail
tenant-b -> https://id.example.test/realms/enterprise
~~~

The tenant from the URL or Host can serve as a **routing hint to an issuer**, yet it is still caller-selected. Safe flow:

1. Read the requested tenant and normalize syntax.
2. Check that the tenant exists in the **server-managed** registry.
3. Look up the exact trusted issuer and JWKS URI from the registry.
4. Select the corresponding manager/decoder; never run dynamic discovery against an arbitrary host.
5. Verify token signature, `iss`, `aud`, expiry/not-before.
6. Bind the authenticated tenant claim and subject to the requested tenant.
7. Check current DB membership, owner, ACL, and action scope.
8. Only then process the tenant resource.

**Dangerous example:**

~~~java
String issuer = "https://" + tenantFromRequest + "/oauth2";
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

If an attacker controls `tenantFromRequest`, the code can fetch metadata/JWKS from an untrusted URL, leading to **SSRF or trust expansion**.

**Explicit registry:**

~~~java
Map<String, String> tenantIssuers = Map.of(
    "tenant-a", "https://id.example.test/realms/retail",
    "tenant-b", "https://id.example.test/realms/enterprise"
);

String issuer = tenantIssuers.get(requestedTenant);
if (issuer == null) {
    // Reject unknown tenant.
}
~~~

This snippet only selects a registered issuer. The token must still be **verified** by the corresponding manager. Never treat `issuer != null` as successful authorization.

### 8.1. When Multiple Tenants Share One Issuer

If every tenant uses:

~~~text
issuer = https://id.example.test/realms/common
tenant_id = tenant-a, tenant-b, tenant-c
~~~

you do not need separate decoders per tenant when signature, issuer, audience, and profile are identical. Verify the JWT with one decoder and enforce tenant membership/ACLs in the service.

Do not add multi-issuer complexity solely because a system is multi-tenant. **Multi-tenant data isolation** and **multi-issuer credential trust** are two separate concerns.

### 8.2. When One Tenant Accepts Multiple Issuers

Enterprise federation may let one tenant trust both a corporate issuer and a partner issuer. The registry then needs a **set of trusted issuers for that tenant**. A token is accepted only if its issuer is in the approved set, its audience is right, and the principal actually holds an entitlement in that tenant.

Never use a tenant claim value as a guarantee that all issuers are trusted.

## 9. Preventing Token Substitution and Identity Collision

### 9.1. Valid `iss` with Wrong `aud`

Token:

~~~json
{
  "iss": "https://id.example.test/realms/retail",
  "aud": ["billing-api"],
  "scope": "invoices.read"
}
~~~

Must not be accepted on `/api/orders/**`, even if signed by the same issuer and unexpired. The Resource Server must check the intended audience.

### 9.2. Identical `sub` Across Two Issuers

Two issuers can issue:

~~~text
Retail issuer:     sub = 123
Enterprise issuer: sub = 123
~~~

They are **not necessarily** the same person or service account. Using a bare `sub` as a global key in the database is a bug.

Safer:

~~~text
identity key = (validated issuer, subject)
~~~

or map that pair to an internal account ID via a trusted registry.

Omitting the issuer allows an enterprise token with `sub=123` to access data belonging to retail subject `123`. This is **cross-issuer identity collision**.

### 9.3. Same Role Name with Different Meanings

Two issuers can emit:

~~~json
{"roles": ["ADMIN"]}
~~~

Yet `ADMIN` in Retail may mean store manager, while in Enterprise it means HR admin. Never blindly map both to `ROLE_GLOBAL_ADMIN`.

A mapping contract should specify:

| Issuer | Claim | Authority that may be granted | Limits |
|---|---|---|---|
| Retail | `scope` | `SCOPE_orders.read` | Token intended for Orders |
| Enterprise | `scp` | `SCOPE_orders.read` if same scope contract | Matches enterprise profile |
| Retail | `app_roles` | `ROLE_STORE_MANAGER` via allowlist | Never becomes global admin |
| Enterprise | `groups` | Only via approved mapping | Never use raw group name as role |
| Any | `tenant_id` | Never becomes global authority | Used inside tenant policy |

**Identical scope strings across two issuers** carry the same meaning only when both ASes have agreed to **the same API permission contract**. Otherwise, namespace them or enforce explicit policies.

## 10. OIDC Login/Session and Bearer Resource Server Are Not the Same Flow

### 10.1. Browser OIDC Login

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

The application acts as an **OAuth2/OIDC Client**, typically involving browser login redirects, session cookies, and principals like `OidcUser`.

### 10.2. API Bearer Resource Server

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()));
~~~

The application acts as a **Resource Server**, accepting OAuth access tokens and typically returning **401 Bearer challenges** on authentication failure.

| Aspect | Browser OIDC Login | Bearer Resource Server |
|---|---|---|
| Request credential | Session/cookie | Bearer access token |
| Missing authentication | Login redirect/session flow | 401 `WWW-Authenticate: Bearer` |
| CSRF protection | Critical when using cookies | Bearer-only APIs may consider disabling |
| Principal | `OidcUser`/login Authentication | `JwtAuthenticationToken` or `BearerTokenAuthentication` |
| Token scope | ID Token serving the OIDC Client | Access Token intended for the API |

**An ID Token is not an API access token.** Never let the Resource Server accept an ID Token just because it is a JWT validly signed by the same issuer; audience, token type, and profile differ.

### 10.3. Browser Chains Need Both Authorization Redirects and Callbacks

A configuration that looks reasonable:

~~~java
@Bean
@Order(3)
SecurityFilterChain console(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/console/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("SUPPORT"))
        .oauth2Login(Customizer.withDefaults())
        .build();
}
~~~

**This is not a complete login configuration to copy verbatim.** OIDC Login typically uses endpoints like:

~~~text
/oauth2/authorization/{registrationId}
/login/oauth2/code/{registrationId}
~~~

They sit **outside `/console/**` by default**. If the console chain does not match the callback, the fallback chain may deny it, breaking login.

Solution: design matchers covering authorization/callback endpoints or customize login paths under the console area, and register the matching redirect URI with the IdP. Test the full login redirect, callback, logout, and CSRF—not just `GET` on the console page.

## 11. mTLS and API Keys in a Multi-Mechanism System

Example contract:

~~~text
/internal/jobs/** -> mTLS/service identity
/api/orders/**    -> JWT access token
/console/**       -> OIDC session
~~~

A service-to-service API can use mTLS client certificates, provided:

- Certificates are verified by the TLS stack/trusted CA with proper client usage and certificate policies.
- When a gateway terminates TLS, the backend may trust forwarded identity only if the gateway strips client-forged headers, the gateway→backend channel is secured, and the backend cannot be reached directly around the gateway.
- API keys have their own lifecycle/rate limits and revocation; never turn them into OAuth scopes.
- Service identity is not equivalent to end-user identity when a service performs delegated actions.

**Never enable "if mTLS is missing, accept an arbitrary `X-Client-Cert` header"**. That is a downgrade path.

## 12. Avoid "Try Every Provider Until Success"

An anti-pattern:

~~~text
JWT verification fails
    -> try opaque introspection
    -> if that fails, try browser session
    -> if that fails, try API key
    -> whichever succeeds grants access
~~~

Do not implement this by default because:

1. A JWT signature failure can become an opportunity to pass through another mechanism.
2. A token intended for another audience might be accepted by a lenient provider.
3. Scope/role semantics of the resulting principal become unclear.
4. 401/403 responses become inconsistent.
5. It can increase introspection load or create side channels.
6. Clients can deliberately choose the weaker authentication path.

An endpoint supporting multiple mechanisms is not always wrong. However, it requires an **explicit routing policy**, an approved provider list, handling of conflicting credentials, and negative tests proving downgrades are impossible. Without a strong reason, **separating endpoints** is easier to audit.

## 13. Do Not Overlook HTTP Method Authorization

A JWT chain containing:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
)
~~~

can expose undeclared `POST` endpoints to any authenticated token; that is dangerous if the API has mutation endpoints.

Specify action-specific scopes:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        HttpMethod.POST, "/api/orders/*/approve"
    ).hasAuthority("SCOPE_orders.approve")
    .requestMatchers(
        HttpMethod.POST, "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .requestMatchers(
        HttpMethod.GET, "/api/orders/**"
    ).hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

Put specific rules before broad rules, and check root paths, trailing slashes, and all HTTP methods. `hasAuthority` performs exact string matching; never use `contains("read")` or map `orders.read.all` to `orders.read`.

Local entitlements and owner/tenant ACLs may still need to hold **simultaneously** with scopes:

~~~text
ALLOW_APPROVE =
    valid token with correct issuer/audience
    AND SCOPE_orders.approve
    AND current local entitlement APPROVE
    AND tenant and order ACL allow action
~~~

Never turn this into `SCOPE_orders.approve OR LOCAL_APPROVE` when the contract requires both.

## 14. Mechanism-Appropriate Error Responses

| Scenario | Typical HTTP | Notes |
|---|---|---|
| No Bearer sent to protected API | 401 | Bearer challenge, typically no error code |
| Invalid JWT signature or expired | 401 | `invalid_token` when appropriate per RFC 6750 |
| Untrusted JWT issuer | 401 | Never dynamically trust issuer |
| Wrong JWT audience | 401 | Token not intended for this API |
| Opaque token `active:false` | 401 | Reject token |
| Opaque introspection timeout | Infrastructure error per config | Never fail open |
| Valid token missing scope | 403 | `insufficient_scope` if applicable |
| Valid scope but wrong tenant | 403/404 per policy | Do not claim missing OAuth scope |
| Unauthenticated browser | Redirect or browser policy | Do not force Bearer API JSON |
| Unknown route | Fallback deny | Never leave open by default |

In Servlet Resource Server, Spring Security provides `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` to support RFC 6750. When adding JSON Problem Details, **do not drop `WWW-Authenticate`**, and ensure the actual HTTP status matches `body.status`.

Do not apply Bearer handlers globally to browser login flows, and do not apply login redirect entry points to machine API clients.

## 15. Testing with MockMvc and JWT Test

### 15.1. Four Required Test Groups

- **Chain selection:** which URLs enter JWT, opaque, browser, or fallback chains.
- **Authentication:** signature, issuer, audience, expiry, and introspection status.
- **Authorization:** scopes, role mapping, tenant/ACL.
- **End-to-end through gateway:** URL rewrites, host headers, CORS, redirects, mTLS forwarding.

Testing only with valid credentials misses trust-domain confusion. **Negative tests** are the centerpiece of a multi-mechanism system.

### 15.2. Testing Scopes with Spring Security Test

With Servlet `MockMvc`, the `jwt()` helper constructs a mock Authentication:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;

import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void missingReadScopeIsForbidden() throws Exception {
    mvc.perform(
        get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            ))
    )
        .andExpect(status().isForbidden());
}
~~~

`mvc` is a `MockMvc` initialized in the test context. The `jwt()` helper **does not verify signatures, issuers, audiences, or JWKS**. It is useful solely for testing authorization rules.

### 15.3. Testing Unknown Issuers

~~~text
Route: /api/orders/42
iss: https://untrusted.example.test
aud: orders-api
Signature: valid against the untrusted issuer's key
Expected: Reject, never fetch metadata/JWKS from unknown issuer
~~~

A token validly signed by an issuer not in the allowlist must still be rejected.

### 15.4. Testing Right Issuer with Wrong Audience

~~~text
Route: /api/orders/42
iss: trusted retail issuer
aud: billing-api
Expected: Reject
~~~

If this test passes, audience validation is likely missing. This is one way to catch **token substitution**.

### 15.5. Testing Two Issuers with the Same `sub`

~~~text
Retail issuer: sub=123
Enterprise issuer: sub=123
Expected: identity mapping does not merge two principals into one
~~~

You can test database ownership using the `(iss, sub)` identity key instead of `sub` alone.

### 15.6. Cross-Tenant Tests

~~~text
URL tenant: tenant-b
JWT tenant_id: tenant-a
JWT scope: orders.read
Expected: Deny
~~~

Variants:

- Token tenant matches, but database membership was revoked → deny.
- Token tenant matches, but the order actually belongs to another tenant → deny.
- Tenant issuer registry permits only Retail; JWT from Enterprise → deny.
- Valid cross-tenant delegation → allow only the exact granted tenants/actions.
- Caller modifies `X-Tenant-Id` header → no privilege escalation.

### 15.7. Endpoint Token Crossover Tests

~~~text
Partner opaque token -> /api/orders/**
Expected: no fallback to partner introspection

Orders JWT -> /api/partners/**
Expected: no fallback to Orders JWT decoder
~~~

### 15.8. Browser and Fallback Tests

~~~text
Unauthenticated GET /api/orders/42
Expected: 401 Bearer challenge

Unauthenticated GET /console/orders
Expected: Browser login policy/redirect

OIDC callback /login/oauth2/code/...
Expected: enters the login chain properly

Unknown URL matching no specific chains
Expected: fallback deny
~~~

### 15.9. Consolidated Test Matrix

| Case | Security outcome |
|---|---|
| JWT with right issuer, aud, scope, and tenant | Passes authentication/authorization |
| JWT issuer outside allowlist | 401 |
| JWT right issuer, wrong audience | 401 |
| JWT expired / invalid signature | 401 |
| Valid JWT missing scope | 403 |
| JWT with `orders.read` but wrong tenant | Deny |
| Enterprise JWT using same `sub` as Retail | No identity collision |
| Partner opaque token calling JWT route | No fallback |
| Orders JWT calling opaque route | No fallback |
| Partner AS outage | Fail closed |
| Cross-tenant delegation without grant | Deny |
| JWT custom `roles=["ADMIN"]` from issuer unauthorized for global admin | Does not create `ROLE_GLOBAL_ADMIN` |
| API request missing token | Bearer challenge |
| Browser login callback | Does not fall into fallback deny |
| Unknown endpoint | Default deny |
| Valid CORS preflight | Follows CORS policy without forcing spurious Bearer auth |
| Gateway URL rewrite | Hits the right chain and right scope |

**Do not equate "passes authorization" with HTTP 200**: the controller may still return 404/409 from business logic.

## 16. Operations: Managing Trusted Issuers and Tenant Registry

A registry might contain:

~~~yaml
trusted-issuers:
  retail:
    issuer: https://id.example.test/realms/retail
    jwks-uri: https://id.example.test/realms/retail/protocol/openid-connect/certs
    allowed-audiences:
      - orders-api
    allowed-tenants:
      - tenant-a
  enterprise:
    issuer: https://id.example.test/realms/enterprise
    jwks-uri: https://id.example.test/realms/enterprise/protocol/openid-connect/certs
    allowed-audiences:
      - orders-api
    allowed-tenants:
      - tenant-b
~~~

**This is an application-defined format**, not a built-in Spring Boot property. The registry is **security configuration** and must be managed as a trust anchor.

Operational requirements:

1. Only approved people/roles can add or modify a trusted issuer.
2. Do not let a tenant admin register an arbitrary internet JWKS endpoint and have it implicitly trusted.
3. Validate every issuer/JWKS URI to prevent SSRF.
4. Maintain an audit trail and review process for tenant-to-issuer mapping changes.
5. Monitor key rotation, JWKS fetch failures, and introspection timeouts.
6. Apply caching policies and timeouts per provider.
7. Run regression tests when issuers/tenants are removed or modified.
8. Do not cache principal/tenant entitlements too long when rapid permission revocation is required.

### 16.1. Metrics Should Distinguish Chains and Issuers

Useful dimensions:

| Dimension | Why it is needed |
|---|---|
| `security_chain` | Shows whether request hit JWT/opaque/browser/fallback |
| `trusted_issuer_alias` | Tracks verified issuers |
| `tenant_alias` | Diagnoses tenant policies with bounded cardinality |
| `authentication_failure` | Signature, expired, wrong issuer/audience, inactive |
| `authorization_failure` | Scope, role, tenant, ACL |
| `jwks_latency` | Key service dependency |
| `introspection_latency` | Partner Authorization Server dependency |
| `fallback_deny_rate` | Detects undeclared routes |
| `cross_tenant_deny_rate` | Detects permission bugs and cross-tenant access attempts |

Never log or place raw Bearer tokens, refresh tokens, ID Tokens, or client secrets in logs/traces/metric labels. Never use self-asserted issuer URIs from tokens as unbounded metric labels; use verified registry aliases instead.

## 17. Common Design Mistakes

### Mistake 1 — Broad Chain Ordered Before Protected Chain

`/api/**` with `permitAll` ordered before `/api/admin/**` prevents the admin chain from ever running. Fix `securityMatcher` and `@Order`, and add negative tests.

### Mistake 2 — Looking Only at `iss` to Grant Access

`iss` before JWS verification is untrusted data. Use it only as a hint inside a trusted allowlist; the manager must verify signature and issuer.

### Mistake 3 — Forgetting Audience

A token for `billing-api` can be validly signed by the same issuer yet must not be usable on `orders-api`.

### Mistake 4 — Deriving JWKS URI from JWT or Tenant String

Opens SSRF and trust expansion. JWKS/issuer must come from a trusted server-side registry, never arbitrary requests.

### Mistake 5 — Using `sub` as a Global Identity Key

`sub` can collide across issuers. Use `(issuer, subject)` or a trusted internal mapping.

### Mistake 6 — Treating Same-Named Scopes/Roles Across Issuers as Equivalent by Default

They are equivalent only when a shared authorization contract is defined; never arbitrarily map them to global admin.

### Mistake 7 — Treating a Tenant Header as Proof of Permission

`X-Tenant-Id`/path/Host can be spoofed by callers. Bind it against verified tokens and DB membership.

### Mistake 8 — Trying Every Provider on Every Endpoint

Creates downgrade risks, cross-audience token substitution, and confusing 401/403 errors. Split routes or use an explicitly designed resolver.

### Mistake 9 — Accepting OIDC ID Tokens as API Access Tokens

ID Tokens are meant for OIDC clients; APIs need access tokens with the right audience and profile.

### Mistake 10 — Too-Narrow Browser Login Chain

`/console/**` misses default OAuth2 authorization/callback endpoints; login can fall into fallback deny. Redesign matchers/paths and test callbacks.

### Mistake 11 — `anyRequest().authenticated()` Accidentally Opening Mutation Routes

If `POST` lacks a write scope rule, any authenticated token can pass the URL policy. Set action-specific scopes and deny by default when appropriate.

### Mistake 12 — Letting Authentication Replace Object-Level Authorization

A token with `orders.read` does not allow reading across all tenants. Services/repositories must still check owner, tenant, current entitlements, and ACLs.

## 18. Production Checklist

- [ ] Define the credential contract for each endpoint group.
- [ ] Security chains have non-overlapping or properly ordered matchers and `@Order`.
- [ ] Fallback deny exists for out-of-contract paths.
- [ ] Strategy is not chosen from client-supplied headers/queries without a trust boundary.
- [ ] No out-of-contract fallback to opaque/session when JWT verification fails.
- [ ] Static issuer allowlist or securely governed registry.
- [ ] JWT manager verifies signature, issuer, audience, exp/nbf, and token profile.
- [ ] No dynamic JWKS fetching from arbitrary issuer URIs/`jku`.
- [ ] Identity key distinguishes issuers rather than relying on `sub` alone.
- [ ] Authority mapping is per issuer without minting global admin.
- [ ] Requested tenant is bound to validated principal and membership.
- [ ] Repositories filter by tenant/owner, not only checking scope.
- [ ] Browser OIDC login covers authorization/callback routes in the right chain.
- [ ] CSRF/session policy fits each chain, never disabled globally without care.
- [ ] 401/403/redirect responses match Bearer vs. browser client types.
- [ ] Negative tests cover unknown issuers, wrong `aud`, tenant mismatch, crossover, and downgrades.
- [ ] Secrets, tokens, and trust registry details do not leak into logs.
- [ ] Monitoring covers issuer/JWKS/introspection/fallback/tenant denials.

## 19. Conclusion

In a multi-mechanism authentication system, **separating endpoints, issuers, and tenants** addresses three distinct concerns:

- **Endpoint** selects the right **authentication mechanism**: JWT, opaque introspection, browser session, or an internal protocol.
- **Issuer** selects the **trusted decoder/manager and validator set**. Unverified `iss` may act only as a routing hint inside an allowlist.
- **Tenant** defines **data scope and entitlements**, which must be checked against the authenticated principal and business data.

In Spring Security Servlet, use **`SecurityFilterChain` + `securityMatcher`/`@Order`** to separate endpoints. Use **`JwtIssuerAuthenticationManagerResolver` with trusted issuers** when the same API accepts JWTs from multiple Authorization Servers. Use **tenant/ACL policies** in services/repositories when the difference lies in data permissions.

The goal is not to support as many login methods as possible, but to ensure **each request passes through one intentional strategy, every credential is fully verified, and there is no path bypassing the trust boundary**.

### References

- [Spring Security Reference — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security Reference — Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Multi-tenancy for Resource Servers](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security API — AuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManagerResolver.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
