# AuthenticationManagerResolver in Servlet applications

When a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server** trusts only a single Authorization Server, JWT configuration is relatively straightforward: set `issuer-uri`, verify the signature and claims, and then authorize by scope/role. However, an application serving **multiple tenants** may need to accept access tokens from **multiple issuers**, each using its own JWKS, audience, naming convention, and policies. Some systems also need to select authentication behavior based on a registered **tenant path or host**.

In the **Spring Security Servlet stack**, `AuthenticationManagerResolver<HttpServletRequest>` is the extension point that lets you **select an `AuthenticationManager` per HTTP request**, instead of forcing the entire API to use a single authentication manager. For Bearer Resource Servers, Spring Security provides `JwtIssuerAuthenticationManagerResolver` for scenarios with **multiple trusted JWT issuers**.

Example:

~~~text
Orders API
  ├── Tenant A -> https://id.example.test/realms/acme
  ├── Tenant B -> https://id.partner.test/tenant/blue
  └── Tenant C -> https://login.example.test/realms/gamma

Each Bearer token:
  -> determine the permitted authentication profile
  -> use the tenant-specific AuthenticationManager/JwtDecoder
  -> verify JWT + issuer + audience + token lifetime
  -> map scopes/roles per profile
  -> check authorization against the actual tenant resource
~~~

Crucially, **choosing where to authenticate** is not the same as **trusting the token contents**: the issuer, tenant ID, or host read from the request **may be unverified** when the resolver makes its decision. The resolver may only use that input to **pick from a trusted set of configurations**, while the selected manager must verify the token and enforce all required constraints.

> **Core principle:** **`AuthenticationManagerResolver` selects the authentication mechanism; it does not authenticate the token itself and does not grant tenant access.** Never build a `JwtDecoder` from an arbitrary client-supplied `iss` or JWKS URL. Only select from a vetted set of issuers/tenants, always validate issuer, audience, expiration, and signature in the corresponding manager, and enforce **tenant/resource authorization** in the business layer.

## 1. The multi-tenant problem: what must be kept separate?

Suppose an Orders API serves multiple organizations:

| Tenant | Access token issuer | Audience for Orders API | Example scope | User identifier |
| --- | --- | --- | --- | --- |
| Acme | `https://id.example.test/realms/acme` | `orders-api-acme` | `orders.read` | `(iss, sub)` |
| Blue | `https://id.partner.test/tenant/blue` | `orders-api-blue` | `orders.read` | `(iss, sub)` |
| Gamma | `https://login.example.test/realms/gamma` | `orders-api-gamma` | `orders.read` | `(iss, sub)` |

A valid JWT issued by Acme **does not automatically grant permission** to call Blue's endpoints. Likewise, two issuers can both emit `sub = "user-842"` while representing two completely different people.

### 1.1. There are several kinds of "tenant"

The word "tenant" can refer to distinct concepts:

1. **Issuer tenant**: each organization has its own Authorization Server or issuer.
2. **Resource tenant**: data/orders are partitioned by organization.
3. **Client tenant**: the OAuth2 Client registration or calling application belongs to an organization.
4. **Route tenant**: the URL/host specifies an organization's workspace.
5. **Business membership**: a user can belong to multiple organizations with different roles in each.

A system may use **one shared issuer for all resource tenants**. In that case, `JwtIssuerAuthenticationManagerResolver` will not separate data because every token shares the same `iss`. You must check `tenant_id` or membership **in business authorization**, rather than trying to invent multiple fake issuers to solve tenancy.

### 1.2. Authentication is not authorization

Two separate questions:

- **Authentication:** Was the access token actually issued by a trusted issuer, signed with the right key, still valid, and intended for this API?
- **Authorization:** Does the authenticated subject/client have the `orders.read` permission on **Order 42 belonging to Blue**?

Even when `JwtIssuerAuthenticationManagerResolver` picks the Blue issuer and the manager verifies the JWT successfully, the API must still check scopes, roles, tenant membership, owner/assignment, and order state.

## 2. What is `AuthenticationManagerResolver<HttpServletRequest>`?

The interface in Spring Security:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.AuthenticationManagerResolver;

AuthenticationManagerResolver<HttpServletRequest> resolver;
~~~

Conceptually, it has one operation:

~~~java
AuthenticationManager resolve(HttpServletRequest request);
~~~

The **input** is the current Servlet request; the **output** is an `AuthenticationManager` suitable for handling the request's credentials. This interface **does not return an `Authentication`**, does not verify a JWS, and does not perform a data authorization query.

### 2.1. Role in a Servlet Bearer Resource Server

~~~mermaid
flowchart TD
    A["HTTP request with Authorization: Bearer ..."]
    B["SecurityFilterChain / BearerTokenAuthenticationFilter"]
    C["BearerTokenResolver extracts Bearer token"]
    D["AuthenticationManagerResolver<HttpServletRequest>"]
    E{"Permitted manager selected?"}
    F["Authentication failure / rejected"]
    G["Tenant-specific AuthenticationManager"]
    H["JwtAuthenticationProvider + JwtDecoder"]
    I{"Valid signature, iss, aud, exp/nbf?"}
    J["JwtAuthenticationToken + authorities"]
    K["authorizeHttpRequests / method security"]
    L["Data policy: tenant, owner, assignment"]
    M["Allow resource processing"]

    A --> B --> C --> D --> E
    E -->|No| F
    E -->|Yes| G --> H --> I
    I -->|No| F
    I -->|Yes| J --> K --> L --> M
~~~

The resolver **picks the manager**. The `AuthenticationManager` (for example, a `ProviderManager` with `JwtAuthenticationProvider`) is responsible for invoking the decoder/provider to verify the token. Only then do you have an authenticated principal and authorities for authorization.

Internal processing details can vary across versions/filter setups, but the trust boundary must hold: **never create an authenticated principal before the token is verified**.

### 2.2. Comparison with single-issuer JWT configuration

Single issuer:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()))
~~~

Multi-issuer:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver))
~~~

In the second configuration, the resolver determines the manager. You do not add this line alongside a single-JWT configuration and hope Spring Security guesses which manager to use per request. Define **one primary authentication path** for the filter chain and test that it actually executes.

### 2.3. Do not confuse Servlet with WebFlux

| Servlet stack | Reactive WebFlux stack |
| --- | --- |
| `HttpServletRequest` | `ServerWebExchange` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthenticationManagerResolver<HttpServletRequest>` | `ReactiveAuthenticationManagerResolver<ServerWebExchange>` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `JwtAuthenticationProvider` | `JwtReactiveAuthenticationManager` |

Do not pass a `ReactiveAuthenticationManagerResolver` into Servlet `HttpSecurity`, and do not use a blocking Servlet manager in WebFlux just because both deal with "authentication."

## 3. Two common strategies to select a tenant

### Strategy A — Based on the JWT issuer

Issuer inside the JWT after verification:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "sub": "user-842",
  "aud": ["orders-api-acme"],
  "scope": "orders.read"
}
~~~

With multiple issuers, the resolver can **read the unverified `iss` solely to select a manager**. The chosen manager must then verify the signature, `iss`, and required claims. Spring Security provides `JwtIssuerAuthenticationManagerResolver` for this use case.

**Pros:** you do not necessarily need separate URLs per issuer; the Client presents a token and the framework selects the matching manager.

**Risk to control:** `iss` during selection is caller-modifiable data. **Never** trust an arbitrary issuer URL, fetch metadata/JWKS from it on the fly, and accept signatures as an API issuer. You must maintain an allowlist/trusted issuer registry.

### Strategy B — Based on a registered tenant route/host

Example:

~~~text
GET /api/tenants/acme/orders/42
GET /api/tenants/blue/orders/17
~~~

The resolver uses a tenant identifier from the route to pick a pre-registered configuration. Acme's manager only accepts Acme's issuer/audience; Blue's manager only accepts Blue's issuer/audience.

**Pros:** the binding between tenant route and issuer is explicit, making it easy to verify that an Acme token cannot be used on Blue's paths.

**Risk:** the route/host can be chosen by the caller; it is **only a selector**, not proof that the caller belongs to the tenant. You must still verify the token with the corresponding manager and check membership/resource permissions.

### 3.1. Which strategy should you choose?

| Requirement | Select issuer from JWT | Select tenant from route/host |
| --- | --- | --- |
| Single shared endpoint accepting tokens from multiple issuers | Suitable | Requires route/host convention |
| Each tenant has its own URL | Possible | Usually clearer |
| Must reject issuer A's token on route B | Requires post-authentication route-to-issuer check | Can be enforced directly in the manager |
| One issuer serves multiple business tenants | Does not distinguish data tenants on its own | Can select tenant, still needs membership check |
| Dynamic management of new issuers | Requires a secure trusted registry | Requires a secure tenant configuration registry |
| SSRF/discovery risk | High if arbitrary `iss` is trusted | Still present if route/header is used directly as JWKS URL |

An application can combine both with clear rules—for instance, selecting the tenant route from the URL and then requiring the JWT issuer to match the issuer registered for that route. However, never combine two tenant sources **without enforcing compatibility checks**.

## 4. `JwtIssuerAuthenticationManagerResolver`: the standard approach for multiple trusted issuers

When each tenant has an independent issuer and the issuer list is pre-approved, Spring Security provides:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
        .JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://id.example.test/realms/acme",
        "https://id.partner.test/tenant/blue",
        "https://login.example.test/realms/gamma");
~~~

This snippet uses the `fromTrustedIssuers(...)` factory from Spring Security 6 versions that support this API. If your project uses an older version, map to the corresponding API for that version while keeping the same **trusted issuers only** principle.

### 4.1. Configuring a `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers
        .AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerSecurityConfiguration {

    @Bean
    JwtIssuerAuthenticationManagerResolver issuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            "https://id.example.test/realms/acme",
            "https://id.partner.test/tenant/blue");
    }

    @Bean
    SecurityFilterChain apiChain(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver issuerResolver)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(issuerResolver))
            .build();
    }
}
~~~

This example includes only **two trusted issuers**, while tenant Gamma in the opening table illustrates that the configuration can grow. If a Gamma JWT arrives without being in the allowlist, the request **is not authenticated**.

**Why `anyRequest().denyAll()`?** It blocks any URLs under `/api/**` without an explicit rule. If the application serves paths outside `/api/**`, another `SecurityFilterChain` or fallback policy is needed; this chain alone does not protect them.

The example assumes `/api/**` is a REST API **using only Bearer tokens in the Authorization header** and not authenticating via session/cookies. CSRF is therefore disabled **under that threat model**, not because multi-tenancy or JWTs magically eliminate CSRF. If the API uses cookie authentication, CSRF must be handled differently.

### 4.2. What happens when a token arrives?

Acme token:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "aud": ["orders-api-acme"],
  "sub": "user-842",
  "scope": "orders.read"
}
~~~

Conceptual flow:

1. The Bearer filter receives the JWT string.
2. `JwtIssuerAuthenticationManagerResolver` reads the issuer to select **a manager from the trusted issuers set**.
3. The manager configured for Acme verifies the JWT against Acme's issuer/keys configuration.
4. If the signature was tampered with or the issuer does not match the decoder, authentication fails.
5. If the token is valid, authorities such as `SCOPE_orders.read` are created by the converter and HTTP rules are evaluated.
6. The service still checks whether the caller is authorized on **Order 42 belonging to tenant Acme**.

Reading `iss` in step 2 **is not an authentication result**; that value only selects a candidate verification mechanism. Never assign roles or internal users from `iss`/`sub` before steps 3–4.

### 4.3. A trusted issuer does not replace audience validation

Suppose the Acme issuer also issues access tokens for `billing-api`:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

The token may be **validly signed by Acme**, yet **not meant for Orders API**. Selecting a trusted issuer does not automatically prove `aud` is correct. You must add per-issuer audience validation or another reliable resource-binding mechanism.

**Never assume `issuer-uri` alone checks all application-specific audiences.** In Spring Security, standard issuer/timestamp validation and audience policy are separate conditions that must be configured and verified against your version and contract.

## 5. Trust boundary: how far can an unverified `iss` claim be used?

A compact JWT typically has the form:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Before signature verification, the payload is **attacker-modifiable data**. Thus a forged token can claim:

~~~json
{
  "iss": "https://attacker.example.test/jwks",
  "sub": "admin",
  "scope": "orders.write"
}
~~~

If the application writes:

~~~java
// DANGEROUS MISTAKE — do not trust an arbitrary issuer URL.
String issuer = parseWithoutVerifying(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
// ... using the new decoder as if the issuer had been approved ...
~~~

it becomes vulnerable to **issuer trust injection**. Beyond accepting tokens signed by an unauthorized party, automatically calling caller-supplied metadata/JWKS URLs can cause **SSRF**, connections to internal networks, DNS rebinding, timeouts, or resource exhaustion.

### 5.1. Allow unverified claims only as a "lookup key"

A sound design works as follows:

~~~text
Unverified iss = "https://id.example.test/realms/acme"
  -> lookup in server-managed trusted registry
  -> find approved Acme manager
  -> decoder verifies signature + expected issuer + expected audience
  -> authentication is only trusted afterward
~~~

If `iss` is absent from the registry, the resolver must **reject** the token. Never insert a new issuer into the registry based solely on a request.

### 5.2. Requirements for a trusted issuer registry

- Issuer URIs are approved via a **tenant configuration/onboarding workflow**, not unauthenticated requests.
- Issuers are matched **strictly** per contract, including scheme, path, and trailing slash.
- JWKS/metadata URLs belong to a trusted endpoint set; restrict redirects, internal IPs, and risky DNS per architecture.
- HTTPS/TLS is verified.
- Timeouts, pooling, caching, and bounds on the number of created managers/decoders are enforced.
- Issuer/key changes can be updated or revoked through a controlled process.
- Never log raw access tokens or Client secrets when debugging.

An `X-Issuer` header sent by a browser **is not a trusted source on its own**. If a header selects a tenant, it can only act as a selector into the registry, and the token must still be validated against the selected tenant/issuer.

## 6. Discovery/JWKS mechanics when using the issuer resolver

With `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)`, Spring Security can **initialize each issuer's decoder/manager on demand** rather than requiring every issuer to be reachable at application startup. This is commonly called **lazy initialization**.

### 6.1. Advantages

- The API can start up even if a rarely used tenant issuer is temporarily unavailable, depending on configuration.
- Only tenants receiving actual traffic incur initial discovery/key retrieval.
- Managers/decoders can be separated per issuer instead of sharing one global configuration.

### 6.2. Trade-offs

- The **first request** for a tenant may incur discovery/JWKS latency.
- If a tenant's AS/JWKS is down, that request can fail even though the API itself started up cleanly.
- During key rotation, the decoder must locate the matching key from JWKS/caches.
- An infrequently used tenant can trigger "only this tenant gets 401/5xx" incidents due to trust, metadata, or network issues.

**Never treat lazy discovery as fail-open.** If trusted key material cannot be obtained to verify the signature, the token must not be accepted. A still-valid JWKS cache can support offline verification per policy; never skip signature validation when the AS is down.

### 6.3. When to avoid runtime discovery

A system can configure a **static JWKS URI and expected issuer/audience** per tenant, building `NimbusJwtDecoder` from pre-approved values. This helps when:

- You want to avoid depending on discovery URLs during the first request.
- The AS does not expose standard discovery metadata.
- You need custom timeouts, algorithms, validators, and authority mappings.
- You want configuration controlled by a registry rather than inferred endpoints.

Even with a static JWKS URI, **you must still check issuer and audience**; a public key URL does not imply that every token signed with that key is meant for your API.

## 7. Building a custom Servlet resolver by tenant route

This example goes deeper: each `/api/tenants/{tenant}/...` path uses a manager registered for that tenant. It illustrates **`AuthenticationManagerResolver<HttpServletRequest>`** instead of the built-in issuer resolver.

### 7.1. Route–issuer–audience contract

| Route prefix | Tenant | Expected issuer | Expected audience |
| --- | --- | --- | --- |
| `/api/tenants/acme` | Acme | `https://id.example.test/realms/acme` | `orders-api-acme` |
| `/api/tenants/blue` | Blue | `https://id.partner.test/tenant/blue` | `orders-api-blue` |

**The tenant in the path only selects the manager.** The token must still be validated for the right issuer/audience. Missing tokens or tokens from another tenant must not enter the route just because the tenant name appears in the URL.

### 7.2. Creating a `JwtDecoder` with an audience validator

~~~java
import java.util.List;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

public final class TenantJwtDecoderFactory {

    public static NimbusJwtDecoder create(
            String issuer,
            String jwkSetUri,
            String expectedAudience) {

        // Passed values must come from a trusted registry/config.
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            List<String> audiences = jwt.getAudience();
            if (audiences != null
                    && audiences.contains(expectedAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for this resource server",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return decoder;
    }

    private TenantJwtDecoderFactory() {}
}
~~~

This function uses `JwtValidators.createDefaultWithIssuer(issuer)` to apply Spring Security's standard issuer and timestamp validators, then adds an audience check for the expected resource. If a system requires token type/profile checks, signing algorithms, `azp`, tenant claims, or custom clock skew, declare those additionally per contract **without replacing** the core validators.

**Configuration source:** `issuer`, `jwkSetUri`, and `expectedAudience` passed into the factory must originate from server configuration or a trusted tenant registry. Never take `jwkSetUri` from a query string or an unapproved issuer.

### 7.3. Creating an `AuthenticationManager` per tenant

~~~java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationProvider;

public final class TenantAuthenticationManagerFactory {

    public static AuthenticationManager create(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusJwtDecoder decoder =
            TenantJwtDecoderFactory.create(
                issuer, jwkSetUri, audience);

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        return new ProviderManager(provider);
    }

    private TenantAuthenticationManagerFactory() {}
}
~~~

`JwtAuthenticationProvider` accepts `BearerTokenAuthenticationToken` from the Bearer authentication flow, uses the decoder to validate the token, and creates a `JwtAuthenticationToken`. `ProviderManager` delegates to the configured provider.

**This is a configuration pattern**, not something you have to write by hand when `JwtIssuerAuthenticationManagerResolver` already fits the problem. A custom factory is useful when each tenant has distinct audiences, JWKS settings, or validation rules.

### 7.4. Resolver selecting a manager from the Servlet path

~~~java
import jakarta.servlet.http.HttpServletRequest;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;

@Configuration
public class TenantRouteResolverConfiguration {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
    tenantRouteAuthenticationManagerResolver() {

        Map<String, AuthenticationManager> managers =
                new LinkedHashMap<>();

        managers.put(
            "/api/tenants/acme",
            TenantAuthenticationManagerFactory.create(
                "https://id.example.test/realms/acme",
                "https://id.example.test/realms/acme/protocol/openid-connect/certs",
                "orders-api-acme"));

        managers.put(
            "/api/tenants/blue",
            TenantAuthenticationManagerFactory.create(
                "https://id.partner.test/tenant/blue",
                "https://id.partner.test/tenant/blue/jwks",
                "orders-api-blue"));

        // No valid tenant -> never grant Authentication.
        AuthenticationManager rejectUnknownTenant =
            authentication -> {
                throw new BadCredentialsException(
                    "Unknown tenant route");
            };

        Map<String, AuthenticationManager> trustedManagers =
            Map.copyOf(managers);

        return request -> {
            // getServletPath typically does not include the context path.
            String path = request.getServletPath();
            for (Map.Entry<String, AuthenticationManager> entry
                    : trustedManagers.entrySet()) {
                String prefix = entry.getKey();
                if (path.equals(prefix)
                        || path.startsWith(prefix + "/")) {
                    return entry.getValue();
                }
            }
            return rejectUnknownTenant;
        };
    }
}
~~~

The URLs/JWKS here are **illustrative only**, not real connection details. For production, move trusted manager registrations into a managed configuration/registry and never hardcode secrets in source code.

**Important path notes:**

- `getServletPath()` typically omits the context path, though behavior can be affected by Servlet mappings and gateway rewrites.
- Check `path.equals(prefix) || path.startsWith(prefix + "/")` to prevent prefix collisions: `/api/tenants/acme-evil` must not match Acme.
- URL encoding, path separators, trailing slashes, matrix variables, proxy normalization, and the Servlet firewall must be tested for your deployment.
- For complex routes, prefer **explicitly configured Spring Security `RequestMatcher`s** instead of hand-rolled parsers on arbitrary tenant names.
- The tenant ID in the URL remains an **untrusted selector**; the chosen manager must verify the JWT's origin and audience.

**Do not return `null` for an unknown tenant hoping the framework will politely reject it.** In this example, a fail-closed manager throws `BadCredentialsException`. You can design an exception handler to return 401/404 per contract, but never return a manager that "permits everything."

### 7.5. Wiring the resolver into `SecurityFilterChain`

~~~java
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers
        .AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class TenantRouteResourceServerSecurity {

    @Bean
    SecurityFilterChain tenantApi(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        return http
            .securityMatcher("/api/tenants/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST,
                    "/api/tenants/*/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

This is **an alternative variant** to using `JwtIssuerAuthenticationManagerResolver` in section 4, not two configurations meant to be registered together on the same URLs. If multiple chains must coexist, set explicit `securityMatcher` and `@Order` values so converter/resolver beans do not conflict.

### 7.6. Each tenant must have an independent JWT policy

If `/api/tenants/blue/orders` receives an Acme JWT, Blue's manager:

1. Verifies the signature with Blue's trusted keys.
2. Checks Blue's `iss`.
3. Checks `aud` is `orders-api-blue`.
4. Checks `exp`/`nbf`.
5. Only then creates an authentication and evaluates scopes.

An Acme JWT must not be accepted for Blue even if the `scope` string matches. **Signature verification with Blue's keys alone may not be enough**, for example if two tenants share signing infrastructure; `iss` and `aud` must still be checked.

## 8. Multi-tenant validation: issuer, audience, token type, and claims

### 8.1. Issuer must match exactly

If the expected issuer is:

~~~text
https://id.example.test/realms/acme
~~~

then:

~~~text
https://id.example.test/realms/acme/
https://id.example.test/realms/blue
http://id.example.test/realms/acme
~~~

are not automatically considered the same issuer. Only apply normalization if the IdP and API contract explicitly allow it; normally match against the exact official issuer URI published by the AS.

### 8.2. Audience is the Resource Server boundary

A token may be valid at the issuer yet issued for Billing API:

~~~json
{
  "iss": "https://id.example.test/realms/acme",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Orders API must reject this token if the contract requires `aud = orders-api-acme`. **A matching scope does not substitute for audience.**

### 8.3. Token type/profile

An OIDC **ID token** is intended for the OIDC Client, not as an API Bearer access token. When the same issuer produces multiple JWT types, the Resource Server may need token type/`typ`/claims profile validation per standard/contract. Never accept an ID token in place of an access token just because its signature is valid or it contains `sub` and `email`.

### 8.4. `azp`/`client_id` and client allowlists

Some AS implementations return `client_id`, `azp`, or client-specific claims in the token profile. These claims can help restrict which Clients may call a tenant API, but **do not use them in place of `aud`** or resource authorization unless the contract defines them as equivalent. An OAuth2 Client ID granted a token does not automatically give that Client permission to read orders across all tenants.

### 8.5. Subject is not globally unique

Example:

~~~text
(iss=acme, sub=user-842) -> local user 42
(iss=blue, sub=user-842) -> local user 91
~~~

If the API uses `sub` alone as a global key, it can link the wrong account or leak data. The `(iss, sub)` pair is a common linking key when issuer and subject have a stable contract. For Client Credentials, `sub` may represent a service Client and must not be treated as a human order owner.

### 8.6. Tenant claims must not be trusted before verification

A JWT might contain:

~~~json
{
  "tenant_id": "acme",
  "roles": ["TENANT_ADMIN"]
}
~~~

Only once the JWT is accepted by the decoder **and** the claims match the expected issuer/profile may they be used as authorization inputs. Even then, `tenant_id` in the token does not guarantee the user is still a member of the tenant at request time; dynamic authorization policies may require checking current membership.

## 9. Selecting a tenant from hostname: where are the risks?

Another architecture uses:

~~~text
https://acme.api.example.test/orders/42
https://blue.api.example.test/orders/42
~~~

A resolver can pick a manager based on a host mapped in the tenant registry, but **the HTTP Host header can be spoofed by a Client** if the gateway/server does not constrain it. `X-Forwarded-Host` should never be trusted arbitrarily without a trusted reverse proxy and proper forwarded-header configuration.

### 9.1. Do not build JWKS URLs from an unverified Host header

Wrong:

~~~java
// WRONG: host is request data and cannot serve as a trust anchor.
String host = request.getHeader("Host");
String jwksUrl = "https://" + host + "/.well-known/jwks.json";
JwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUrl).build();
~~~

An attacker can control the host/URL in such deployments and trigger SSRF or make the API trust keys from an unauthorized source.

Instead:

~~~text
Host after trusted proxy validation
  -> exact-match host to trusted tenant registration
  -> retrieve pre-configured issuer/JWKS/audience
  -> select manager
  -> decoder verifies JWT
  -> check tenant membership/resource permissions
~~~

### 9.2. A tenant selection header is only a selector

`X-Tenant-Id: acme` can be useful for a gateway or workspace-aware app, but a caller-supplied header **must never grant permissions on its own**. If the API receives:

~~~http
X-Tenant-Id: blue
Authorization: Bearer <valid-token-for-acme>
~~~

it must reject the request or allow it only if **both the token and membership** permit Blue per contract. Never switch the Authentication to Blue just because the header asks for it.

## 10. Multiple issuers sharing one signing key?

Some organizations operate multiple logical tenants on a single Authorization Server or share JWKS signing infrastructure. In that case, **a valid signature is not enough to distinguish tenants**.

Suppose the same public key verifies both Acme and Blue JWTs:

~~~text
JWT Acme: iss=.../acme, aud=orders-api-acme
JWT Blue: iss=.../blue, aud=orders-api-blue
~~~

If the decoder only verifies the signature without **checking expected issuer/audience**, an Acme token could be accepted for Blue. That is why `JwtValidators.createDefaultWithIssuer(...)` and the audience validator in the custom manager example are mandatory under the contract.

If a shared issuer mints tokens for multiple resource tenants:

~~~text
iss = https://identity.example.test
aud = orders-api
tenant_id = acme or blue
~~~

then a single manager may suffice for authentication. Data tenant isolation must then rely on the verified `tenant_id` and membership/owner permissions. **Do not force a multi-issuer resolver when the real problem is multi-tenant authorization.**

## 11. Tenant authorization: scopes are not enough for object permissions

A JWT has `scope = "orders.read"`. The Resource Server produces:

~~~text
SCOPE_orders.read
~~~

HTTP rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/tenants/*/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

This rule only confirms the caller is allowed to perform a **read action type**. It does not prove that the user:

- Belongs to the tenant in the URL.
- Has permission to view order 42.
- Is the order owner or an assigned support agent.
- Is authorized to read sensitive data belonging to another tenant.

### 11.1. Enforcing checks right at the data query

A service can use a tenant **verified/enforced by policy** and subject/user mapping:

~~~java
@Service
public class OrderQueryService {

    private final OrdersRepository orders;
    private final TenantAccessPolicy policy;

    public OrderQueryService(
            OrdersRepository orders,
            TenantAccessPolicy policy) {
        this.orders = orders;
        this.policy = policy;
    }

    public OrderDto getOrder(
            Authentication authentication,
            String tenant,
            String orderId) {

        policy.assertCanRead(authentication, tenant, orderId);
        return orders.findVisibleByTenantAndId(
                tenant, orderId);
    }
}
~~~

`OrdersRepository`, `TenantAccessPolicy`, and `OrderDto` are illustrative domain classes, not built into Spring. In production, design data access and transactions to avoid **time-of-check/time-of-use** issues when permissions or orders change, and ensure database queries include appropriate tenant/owner predicates.

### 11.2. The tenant in the URL is caller-chosen input

For example, a user authorized in Acme sends:

~~~http
GET /api/tenants/blue/orders/42
Authorization: Bearer <valid-acme-token>
~~~

Even if the route manager rejects the token at authentication, the API still needs a business policy because a shared-issuer token or service token may be valid across **multiple tenants**. Never omit `TenantAccessPolicy` just because a route resolver is in place.

### 11.3. Tenant-scoped roles need context

If a user has `ROLE_ADMIN` in Acme but is only a reader in Blue, a global `ROLE_ADMIN` authority can be misused. Therefore:

- Only use global authorities when they genuinely grant system-wide privileges.
- Check membership/roles against the requested tenant.
- If the token contains tenant-specific claims, validate their exact schema and namespace.
- Map roles per **issuer + tenant** using an allowlist rather than trusting every arbitrary role string emitted by an IdP.

## 12. Multi-tenancy and `JwtAuthenticationConverter`

Each issuer may return scopes differently:

~~~json
{"scope": "orders.read orders.write"}
~~~

or:

~~~json
{"scp": ["orders.read", "orders.write"]}
~~~

Spring Security supports common scope claims by default, while some AS implementations use custom role structures such as `realm_access.roles` or `permissions`. When tenants have different schemas, configure a **separate `JwtAuthenticationConverter` inside each tenant's `JwtAuthenticationProvider`**.

### 12.1. Converters only read verified claims

Standard scope configuration example:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter scopeAuthorities =
        new JwtGrantedAuthoritiesConverter();
scopeAuthorities.setAuthorityPrefix("SCOPE_");

JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(scopeAuthorities);
converter.setPrincipalClaimName("sub");

provider.setJwtAuthenticationConverter(converter);
~~~

This snippet belongs to the step **configuring `JwtAuthenticationProvider provider`** in the factory. The converter should only map claims matching the tenant's token profile after the decoder accepts the JWT. Never let a `roles=["ADMIN"]` claim from an untrusted or unauthorized issuer turn into Orders API privileges.

### 12.2. Do not merge identically named scopes across issuers without a contract

Acme's `SCOPE_orders.read` and Blue's `SCOPE_orders.read` may mean the same thing **at the HTTP action level**, yet data access must remain bound to the tenant. If a partner issuer defines `orders.read` with a different semantic, the API needs an explicit mapping contract or adapter rather than assuming identical strings represent identical permissions.

### 12.3. `Authentication.getName()` across multiple issuers

By default, a JWT Resource Server commonly uses `sub` as the name. If two issuers both emit `sub="user-842"`, logging and services must not treat `authentication.getName()` alone as a global user ID.

You can:

- Use `(iss, sub)` when mapping to a local account.
- Use a custom converter and set the principal name to the internal user ID when a trusted link exists.
- Include the issuer in the audit context.
- Avoid using email/username as a global identity key unless backed by a strong contract.

## 13. Dynamic issuer registration: how to avoid opening the trust boundary?

In SaaS, tenants may be onboarded after the API has already started. You may need to update the trusted issuer list or manager registry.

**Mistake:** accepting any new `iss` from a request and treating it as a valid tenant.

**Proper flow:**

1. An authenticated admin/onboarding service requests tenant registration.
2. The system checks the admin's permissions and organizational constraints.
3. Verify issuer metadata/JWKS using URL policies, TLS, allowed hosts/ports, and an approval workflow.
4. Define expected audience, allowed algorithms, authority mapping, token profile, and tenant ID.
5. Persist the configuration into the **trusted tenant registry**.
6. Update the manager/decoder cache safely with respect to concurrent requests.
7. Run integration tests and monitor for errors.
8. Only after the tenant is enabled should tokens from that issuer be accepted.

### 13.1. Using a trusted issuers predicate

In Spring Security versions providing the predicate overload, you can model:

~~~java
// Illustrative: the registry is updated only through a trusted admin workflow.
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        issuer -> trustedTenantRegistry.isAllowedIssuer(issuer));
~~~

`trustedTenantRegistry` is an **application-built component**, not a built-in Spring class. It must query or read a cache backed by a trusted configuration source, and never auto-add an issuer on a lookup miss. If registry checks perform blocking I/O, design appropriate caching and timeouts because this runs on the Servlet request authentication path.

### 13.2. Bounded caching of managers and decoders

Creating a decoder/JWKS client on **every request** is both slow and an avenue for resource exhaustion. Instead of:

~~~java
// Do not instantiate a new decoder on every request.
return request -> createManager(
    issuerFromRequest(request));
~~~

you should:

- Use an issuer resolver with caching as supported by the framework.
- Or keep an in-memory `Map<TrustedTenantKey, AuthenticationManager>`/registry keyed by config version.
- Bound per-tenant manager creation and prevent concurrent duplicate initialization.
- Ensure invalidation/replacement mechanisms when a tenant is revoked or metadata changes.
- Cap tenant count, JWKS fetches, and timeouts to mitigate DoS.

**A cached manager does not mean permanent trust.** When a tenant loses access or an issuer is no longer trusted, the system must have a plan to remove the issuer/manager from the registry and block subsequent requests per policy.

### 13.3. Atomic updates under concurrent requests

If the registry changes while requests are in flight, use immutable snapshots or thread-safe update mechanisms:

~~~text
config version 17 -> trusted issuers {Acme, Blue}
config version 18 -> trusted issuers {Acme, Gamma}
~~~

Never mutate a shared `HashMap` across threads without synchronization. Requests started during transitions need deliberate behavior, especially when Blue is revoked.

## 14. Comparison with multiple `SecurityFilterChain`s

Two commonly confused design patterns:

### 14.1. One chain, multiple managers

~~~text
SecurityFilterChain /api/**
  -> AuthenticationManagerResolver
     -> manager Acme
     -> manager Blue
     -> manager Gamma
~~~

Fits well when **HTTP rules are largely shared**, while authentication varies by issuer/tenant.

### 14.2. Multiple chains, one authentication profile per chain

~~~text
@Order(1) /api/tenants/acme/** -> JwtDecoder Acme
@Order(2) /api/tenants/blue/** -> JwtDecoder Blue
@Order(3) /api/**              -> denyAll/fallback
~~~

Fits well when **HTTP rules, CSRF, or authentication transports** differ significantly, the tenant count is small, and routes are cleanly separated. With hundreds of dynamically onboarded tenants, maintaining hundreds of filter chains is cumbersome; a resolver is usually easier to manage.

**Do not assume one chain covers every URL.** `securityMatcher` and `@Order` ordering can cause a request to miss the expected chain; unmatched paths must be handled by a fallback/default-deny policy.

### 14.3. Fallback chain example

If the tenant route chain only matches `/api/tenants/**`, another chain can block everything else:

~~~java
@Bean
@Order(99)
SecurityFilterChain denyUnknownPaths(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

This is **a design option** when the application only serves explicitly listed APIs. If you have Actuator, public pages, or `oauth2Login`, build explicit rules to match product requirements. Never drop this fallback in blindly and accidentally lock out needed health checks.

## 15. JWT Resource Server vs. OAuth2/OIDC Client

One application can act both as an OAuth2 Client to log users in via OIDC and as a Resource Server receiving access tokens. However, the two roles are distinct:

| Role | Typical APIs/concepts | Responsibility |
| --- | --- | --- |
| OAuth2/OIDC Client | `oauth2Login()`, `ClientRegistration`, `OidcUser` | Drive browser login, manage authorized client/session |
| Resource Server | `oauth2ResourceServer()`, `JwtDecoder`, `AuthenticationManagerResolver` | Verify Bearer access tokens to protect APIs |
| Authorization Server | Token endpoint, JWKS, issuer, signing keys | Issue tokens and publish metadata |

`AuthenticationManagerResolver<HttpServletRequest>` in this lesson serves **selecting an authentication manager for a Servlet Bearer Resource Server**. It does not turn the API into an OIDC Client, generate authorization codes, or replace session/login cookie management.

An OIDC Client's **ID token** normally has the Client ID as its audience and serves Client-side login authentication. It is not a default accepted credential for Orders API. Define the exact **access token profile** for each tenant.

## 16. Opaque tokens and combining multiple token types

Multi-tenancy does not require signed JWTs everywhere. Some tenants use **opaque access tokens** with introspection.

Example:

~~~text
Tenant Acme -> signed JWT -> JwtAuthenticationProvider
Tenant Blue -> opaque access token -> OpaqueTokenAuthenticationProvider
~~~

Architecturally, `AuthenticationManagerResolver<HttpServletRequest>` can choose different managers, provided the contract is clear:

1. Route/issuer/tenant is chosen from the **trusted registry**.
2. The JWT manager uses `JwtDecoder` to verify JWS and claims.
3. The opaque manager uses `OpaqueTokenIntrospector` to check `active`, audience/resource binding, and metadata.
4. Each provider constructs the appropriate principal and authorities.
5. Authorization and resource policies stay consistent on the API side.

Do not guess a token's trusted type simply by checking whether the string contains two dots. An opaque token can have its own format, and a JWT can also be validated via introspection if required by contract.

### 16.1. Never "try JWT, and if it fails, accept as opaque"

An uncontrolled fallback:

~~~text
JWT signature invalid
  -> try arbitrary introspection
  -> if an AS says active, accept it
~~~

can break issuer and resource boundaries. If two token profiles are supported, enforce explicit selection rules, trusted AS mappings, audiences, and token purposes. A JWT with an invalid signature **must never be converted into a credential for another tenant**.

### 16.2. Per-tenant introspection credentials

If Blue uses introspection, the Resource Server may need its own `client-id`/`client-secret` to call the endpoint. These are **Orders API's credentials with AS Blue**, not the OAuth2 Client ID inside the token. Store secrets in a secret manager and rotate them per tenant.

## 17. Error handling: 401, 403, and dependency failures

| Scenario | Detecting layer | Desired outcome |
| --- | --- | --- |
| Protected request without Bearer token | Bearer filter/entry point | Usually **401 Unauthorized** |
| JWT `iss` not in trusted allowlist | Issuer resolver | Not authenticated |
| JWT issuer in allowlist but bad signature | JWT decoder/provider | Not authenticated, usually 401 |
| JWT valid issuer/signature but wrong audience | JWT validator | Not authenticated, usually 401 |
| Expired JWT | JWT validator | Not authenticated, usually 401 |
| Acme route receiving Blue token | Route manager/validator | Not authenticated |
| Valid token missing `orders.read` | HTTP/method authorization | Usually **403 Forbidden** |
| Valid token with scope, wrong tenant/order | Business policy | 403/404 per contract |
| Unknown tenant route | Resolver/fallback policy | Fail closed, status per exception handler |
| Discovery/JWKS timeout | Authentication dependency | Do not produce valid authentication |
| Introspection AS down | Opaque authentication dependency | Do not produce valid authentication |

**Do not hardcode a single HTTP status for every discovery/network failure.** Framework and exception handling may map dependency exceptions to 401 or 5xx depending on the case. The mandatory security requirement is **never executing the protected operation when authentication is incomplete**.

### 17.1. Bearer entry point and access denied handler

Spring Security Resource Server provides:

~~~java
BearerTokenAuthenticationEntryPoint entryPoint =
    new BearerTokenAuthenticationEntryPoint();

BearerTokenAccessDeniedHandler deniedHandler =
    new BearerTokenAccessDeniedHandler();
~~~

`BearerTokenAuthenticationEntryPoint` typically handles authentication failures with a 401/Bearer challenge. `BearerTokenAccessDeniedHandler` typically handles insufficient permissions with a 403, potentially including `insufficient_scope` per RFC 6750. Neither replaces validators or fixes tenant binding.

### 17.2. Do not leak internal tenant structure through errors

Example error response to a Client:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "The supplied access token could not be accepted."
}
~~~

Never return raw JWTs, signing keys, introspection secrets, internal network paths, or the full issuer list to an unauthenticated caller. For debugging, rely on controlled logging with a correlation ID.

### 17.3. `WWW-Authenticate`

Per the Bearer protocol (RFC 6750), responses may include:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

or when the token authenticated but lacks a scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

When customizing JSON error handlers, preserve the Bearer challenge if required by contract/protocol. Lack of tenant membership is sometimes a business authorization failure rather than a missing OAuth scope; avoid assuming every 403 means a missing `scope`.

## 18. Testing the resolver: from unit tests to real signed JWTs

**A `MockMvc` test using `SecurityMockMvcRequestPostProcessors.jwt()` can bypass both the resolver and the JWT decoder**, because it injects a mock authentication onto the request. Such tests are useful for verifying HTTP authorization after Authentication exists, **not for proving tenant manager selection or signature verification**.

You need at least three levels of testing:

1. **Resolver unit tests**: request route/host/issuer selects only the intended manager from the trusted registry.
2. **HTTP Bearer integration tests**: actually signed tokens flowing through the decoder/manager, covering valid and invalid issuer/audience/expiry.
3. **Business authorization tests**: scope/owner/tenant checks and side effects.

### 18.1. Route resolver unit test

JUnit Jupiter example:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;

class RouteResolverTest {

    @Test
    void selectsTheSameRegisteredManagerForAcmeRoutes() {
        AuthenticationManagerResolver<HttpServletRequest> resolver =
            new TenantRouteResolverConfiguration()
                .tenantRouteAuthenticationManagerResolver();

        var first = new MockHttpServletRequest(
                "GET", "/api/tenants/acme/orders/42");
        first.setServletPath("/api/tenants/acme/orders/42");

        var second = new MockHttpServletRequest(
                "GET", "/api/tenants/acme/orders/99");
        second.setServletPath("/api/tenants/acme/orders/99");

        AuthenticationManager firstManager =
                resolver.resolve(first);
        AuthenticationManager secondManager =
                resolver.resolve(second);

        assertNotNull(firstManager);
        assertSame(firstManager, secondManager);
    }
}
~~~

This test only confirms that **two Acme routes select the same manager** and that the manager exists; it **does not yet verify** that the manager enforces Acme's expected issuer/audience, that a Blue token is rejected, or that unknown routes are blocked. You must add negative cases and integration tests.

For production tests, the decoder factory may need test-specific mocks/configs instead of initializing external JWK clients outside the test environment; the goal is never to hit a production IdP.

### 18.2. Real JWT and route matrix

| # | Route | Test token | Expected outcome |
| --- | --- | --- | --- |
| T1 | `/api/tenants/acme/orders/42` | Acme JWT, valid signature/issuer/audience, `orders.read` | Authenticates; still requires data policy |
| T2 | `/api/tenants/blue/orders/42` | Blue JWT, valid issuer/audience, `orders.read` | Authenticates; still requires data policy |
| T3 | Acme route | Blue JWT even with `orders.read` | Rejected at authentication |
| T4 | Blue route | Acme JWT | Rejected at authentication |
| T5 | Acme route | Self-signed JWT with non-Acme key | Rejected |
| T6 | Acme route | Acme-signed JWT with `aud=billing-api` | Rejected |
| T7 | Acme route | Expired JWT | Rejected |
| T8 | Acme route | Valid JWT missing `orders.read` | Authentication succeeds, authorization 403 |
| T9 | Acme route | Valid JWT, sufficient scope, order belongs to Blue | Rejected by business policy |
| T10 | `/api/tenants/unknown/orders` | Any JWT | No fallback manager accepts it |
| T11 | `acme-evil` route | Acme JWT | Does not mistakenly match Acme prefix |
| T12 | Acme route | Spoofed Host header | Does not alter trusted issuer/JWKS |
| T13 | Issuer outside allowlist | Attacker-signed JWT | Resolver rejects, no arbitrary discovery |
| T14 | Acme route | Missing Bearer token | Blocked from protected endpoint |
| T15 | Acme route | Acme JWT, DB membership error | Blocked from business action when permission cannot be verified |

### 18.3. Setting up mock JWKS and signing real JWTs

An integration test should:

1. Generate **two test-only RSA/EC key pairs**, one for Acme and one for Blue.
2. Run WireMock/MockWebServer as the JWKS endpoint for each tenant.
3. Build real signed JWTs with `kid`, `iss`, `aud`, `sub`, `exp`, and `scope` matching the test profile.
4. Point the tenant resolver at the **mock JWKS**, never calling a real IdP.
5. Send HTTP requests with `Authorization: Bearer <signed-JWT>` via `MockMvc` or a test server.
6. Verify T1–T15 and confirm no business side effects occur when rejected.

**Never commit production private keys into the test repo.** Use test-only keys with a bounded lifetime that cannot issue tokens for any real environment.

### 18.4. What Spring Security Test's `jwt()` checks

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/tenants/acme/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

This is a **test body snippet** assuming appropriate imports, `MockMvc`, controller, and service fixtures. `jwt()` mocks authentication and is suitable for testing `hasAuthority` rules or business methods. **Do not use a 200 result from this test to conclude that the resolver, JWT signature, JWKS, issuer, or audience work properly.**

### 18.5. Testing 401 and 403 separately

A plan:

~~~text
No token -> authentication entry point
Invalid issuer/signature/audience -> authentication failure
Valid token, missing SCOPE_orders.read -> authorization denied
Valid token, scope allowed, wrong owner/tenant -> data policy denied
~~~

Do not assert only on HTTP status codes; a test for an order cancellation endpoint should verify that **`OrderService.cancel` is never invoked, the database is unchanged, and no events are emitted** when the request is blocked.

## 19. Testing in code: introspection/issuer registry and dependency outages

### 19.1. When a tenant is added or revoked

Verify:

~~~text
New unapproved issuer
  -> all JWTs from that issuer are rejected

Approved issuer
  -> only valid JWTs matching aud/profile are accepted

Revoked issuer
  -> subsequent requests must not treat the old manager as valid trust
~~~

If the system updates the registry at runtime, test concurrent requests during updates and confirm there is no race condition for a revoked issuer.

### 19.2. When JWKS/AS is down

Verify:

- Does API startup depend on discovery for all issuers?
- How can a previously unused tenant be affected on its first request?
- If the cache still holds valid public keys, can the decoder keep verifying tokens?
- Do key rotation and an unknown `kid` trigger a JWKS refresh or fail closed?
- Could a network error accidentally cause the system to allow `permitAll()`?
- Is there a retry storm when many requests hit a failing JWKS endpoint?

**Mandatory outcome:** a request without sufficient trusted authentication evidence **must not execute protected operations**. It may return 401 or 5xx per exception strategy, but never turn an outage into an authentication bypass.

### 19.3. Monitoring latency and scale

In the Servlet stack, JWT decoding and JWK discovery network calls consume request threads and HTTP client resources. With many issuers and cold starts, monitor:

- Discovery/JWKS latency and failure rate per tenant.
- Cache hits/misses and the number of created managers.
- Thread pools, HTTP connection pools, and timeouts.
- Decoder validation failures broken down by issuer/audience/expired/signature.
- Unexpected-issuer attempts (without logging raw tokens).
- Authorization denials by tenant and endpoint.

**Avoid creating a new manager on every request.** Controlled caching reduces overhead, provided you have an update strategy when an issuer loses trust.

## 20. Logging and auditing in multi-tenant applications

A multi-organization system needs enough audit data to answer "who accessed which tenant's data," without exposing credentials.

After verification, you can record:

~~~text
request_id
route_tenant
verified_issuer
verified_subject or internal_user_id (per PII policy)
verified_client_id if part of the contract
http_method
normalized_route
authorization_outcome
resource_tenant
policy_reason_category
~~~

**Do not log:**

- Full `Authorization` headers or JWTs.
- Signing private keys or introspection client secrets.
- Unverified claims as if they were trusted identity.
- Unnecessary sensitive email/PII.
- Unbounded issuer/tenant inputs as metric labels causing cardinality explosion.

### 20.1. The issuer in the resolver is not yet a verified issuer

When `JwtIssuerAuthenticationManagerResolver` reads `iss` to pick a manager, a log field:

~~~text
requested_issuer=<unverified value>
~~~

can help security diagnostics if sanitized and rate-limited; **do not** label it `authenticated_issuer` until the decoder accepts the token. Distinguish untrusted input from authenticated identity.

### 20.2. Tenant from URL is not membership

An audit log stating "user accessed tenant Blue" must reflect both the route tenant and the authorization outcome. Just because the URL contains Blue does not mean the caller is a member of Blue. Audits should record the **outcome**: denied at authentication, denied at authorization, or allowed.

## 21. Common implementation mistakes

### 21.1. Trusting any issuer self-declared by the JWT

Wrong:

~~~text
Any JWT iss
  -> API fetches discovery/JWKS from that URL
  -> token signed by that issuer is accepted
~~~

This blows open the issuer trust boundary and introduces SSRF risk. Use a managed trusted issuers list/registry.

### 21.2. Skipping per-tenant audience validation

A token validly signed by Acme but issued for Billing API **must not** call Orders API. Add an audience validator or equivalent resource binding.

### 21.3. Resolver reading a tenant header and granting access

`X-Tenant-Id: blue` sent by a caller is just input; it proves neither membership nor audience. Pick the manager from a trusted registry, then verify both the token and data policy.

### 21.4. Using `sub` alone as a global user ID

Two issuers can share the same `sub`. Use `(iss, sub)` for external identity, mapping to an internal user ID when needed.

### 21.5. Confusing AuthN with AuthZ

`AuthenticationManagerResolver` does not replace ownership of Order 42. Check tenant, owner, assignment, and scopes.

### 21.6. Creating a new decoder on every request

This generates unnecessary discovery/JWKS traffic and risks resource exhaustion. Cache managers/decoders by trusted issuer/tenant with proper invalidation.

### 21.7. Sharing a manager across tenant routes while forgetting issuer checks

If Blue's route uses a decoder without an issuer validator, an Acme JWT could be accepted under shared-key setups. Every manager must validate its expected issuer and audience.

### 21.8. Accepting an OIDC login Client's ID token as an API access token

ID tokens must not replace Resource Server access tokens. Validate the proper token profile and API audience.

### 21.9. Disabling CSRF simply because of "multi-tenant JWT"

CSRF may only be disabled for chains that **do not authenticate using ambient browser credentials**, after evaluating the threat model. Cookie-carried stateless JWTs still carry CSRF risk.

### 21.10. Assuming one `SecurityFilterChain` covers all URLs

`securityMatcher("/api/**")` does not protect `/admin/**` or `/internal/**` unless another chain handles them. Use a fallback policy and test path boundaries.

### 21.11. Using untrusted Host/Forwarded headers to locate JWKS

This creates SSRF and issuer confusion risks. Only use a host after trusted proxy validation as a lookup key into approved registrations.

### 21.12. Treating MockMvc `jwt()` as a multi-issuer authentication test

`jwt()` typically bypasses the decoder and resolver. Signed-token integration tests are required.

### 21.13. Updating the issuer registry without refreshing caches

Old cached managers may keep trusting a newly revoked issuer. Version/invalidate caches and handle concurrency intentionally.

### 21.14. Treating `ROLE_ADMIN` in one tenant as admin everywhere

This is an authorization boundary bug; roles need proper tenant namespacing/binding and resource policies.

### 21.15. Disabling authentication on JWKS errors to preserve availability

Failing open is dangerous. When tokens cannot be verified, do not execute protected operations. Improve availability through issuer/JWKS infrastructure, caching, and safe timeouts.

### 21.16. Using a multi-issuer resolver for a single-issuer system

If one issuer serves multiple resource tenants, the problem belongs in tenant claims, membership, and authorization—not authentication manager selection. Avoid unnecessary complexity.

## 22. Design and handoff checklist

1. Does tenant mean a separate issuer, resource tenant, route tenant, or a combination?
2. Do you genuinely need multiple authentication managers, or is one issuer plus resource authorization enough?
3. Is the issuer/tenant registry managed from a trusted source?
4. Does the resolver ever trust an unverified `iss`, host, or header as a trust anchor?
5. Is `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` used where appropriate?
6. With a custom resolver, does each manager validate signature, issuer, audience, and timestamps individually?
7. Do you verify the access token profile instead of accepting OIDC ID tokens?
8. Does `JwtAuthenticationProvider` use an authority converter matching each issuer's schema?
9. Is external identity keyed by `(iss, sub)` to prevent collisions?
10. Are tenant-specific roles and memberships checked against the resource tenant?
11. Are route prefixes, URL encoding, hosts, and forwarded headers tested?
12. Do unknown tenants/issuers fail closed?
13. Is there a fallback `SecurityFilterChain` protecting unmatched paths?
14. Are decoders/managers cached with appropriate bounds and refresh behavior?
15. When an issuer is revoked, do caches and trust state update promptly?
16. Can a JWKS/discovery outage lead to authentication bypass?
17. Do Client Credentials/service tokens have separate policies from user tokens?
18. Do missing-scope requests yield 403 and invalid-token requests fail at authentication?
19. Do signed-JWT tests cover cross-tenant token substitution?
20. Are rejected requests guaranteed to produce no database or event side effects?

## 23. Scenario exercises

**Scenario A:** The API trusts Acme and Blue. A forged token claims `iss=https://attacker.example.test` with a JWT signed by the attacker. What should the resolver do?

**Do not select a manager for this issuer** if it is not in the trusted registry. Never use the attacker's URL to fetch JWKS and auto-add a new issuer.

**Scenario B:** Acme's JWT has a valid signature but `aud=["billing-api"]`. Should Orders API accept it if the scope contains `orders.read`?

**No.** Audience must match Orders API per contract; a matching scope name does not fix a wrong audience.

**Scenario C:** Request `/api/tenants/blue/orders/42` carries a verified Acme token. Which manager does the route resolver pick?

**Blue's manager** per the route. That manager must reject the Acme token due to mismatched issuer/audience (and potentially signing keys). Never fall back to Acme's manager just to make the request succeed.

**Scenario D:** A shared issuer mints JWTs for both Acme and Blue, with a `tenant_id` claim. Is `JwtIssuerAuthenticationManagerResolver` strictly required?

**No.** With a shared authentication issuer, you can use one manager and check tenant membership/ownership during authorization. Multi-tenant resources do not imply multiple issuers.

**Scenario E:** Two issuers both emit `sub="user-842"`. Can `authentication.getName()` alone serve as a system-wide user key?

**Not by default.** You must use issuer + subject or map to an internal user ID through a trusted link.

**Scenario F:** A browser sends `X-Tenant-Id: blue` while the token is only for Acme. Is the header enough to switch the user to Blue?

**No.** The header can be a selector but grants no permissions; both the token contract and business membership are required.

**Scenario G:** `JwtIssuerAuthenticationManagerResolver` reads the issuer before verifying the token. Is that a security violation?

**Not necessarily**, as long as the issuer is only an **allowlist lookup key** and the selected manager proceeds to verify the signature, issuer, and claims. It becomes dangerous if an unverified claim is used as an arbitrary trust anchor.

**Scenario H:** Valid token, sufficient scope, but Order 42 belongs to another tenant. The resolver succeeded—can the API return the order?

**No.** The resolver only chooses the manager; data authorization must check tenant, owner, and assignment.

**Scenario I:** A unit test using `mockMvc.with(jwt())` returns 200 with scope `orders.read`. Does that prove the resolver picks Acme's JWKS properly?

**No.** Mock authentication tests typically skip the resolver and decoder. You need real JWTs signed with test keys passing through the filter chain, decoder, and manager.

**Scenario J:** A JWT issuer is in the allowlist, but JWKS is down on the tenant's first API call. Should you accept the token based on its payload and scope?

**No.** Without trusted keys or a valid cached verifier to check the signature, authentication must fail safely.

**Scenario K:** Tenant Blue has been de-registered, yet Blue's manager remains in cache. What must the system watch out for?

You must **revoke trust in the registry and invalidate/version the manager cache** per policy; never let the cache keep accepting a disallowed issuer.

**Scenario L:** JWTs from two issuers both include scope `orders.read`. Can we conclude a user in either tenant can view all orders?

**No.** Scopes indicate operation types; resource access still depends on tenant membership, subject, owner, and business policies.

---

## Conclusion

In a **Servlet-based Spring Security OAuth2 Resource Server**, `AuthenticationManagerResolver<HttpServletRequest>` enables selecting an **`AuthenticationManager` per request**, which is valuable when an API serves multiple tenants with **different issuers, signing keys, audiences, or authentication profiles**. When the problem is simply multiple trusted JWT issuers, `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` offers a concise configuration. When you need tenant binding by URL/host or specialized rules, a custom resolver can pick from pre-registered `JwtAuthenticationProvider`/`JwtDecoder` instances.

The security boundary never changes: **an issuer or tenant before verification is only selector data for choosing a manager, never proof of identity**; only a trusted registry defines issuers and JWKS. Managers must validate signature, issuer, audience, expiration, and token profile; afterward, HTTP/method security and business policies must enforce scopes, roles, **tenant membership, ownership, and per-resource permissions**. Test both positive and negative paths, especially tenant A's token used on route B, untrusted issuers, wrong audiences, and JWKS outages. **The resolver picks how to authenticate; actual authorization must still be proven and enforced at the Resource Server.**
